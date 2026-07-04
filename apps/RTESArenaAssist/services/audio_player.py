from __future__ import annotations
import json
import os
import sys
import threading
import time

def run_player() -> int:
    if os.name != 'nt':
        return 0
    try:
        import faulthandler
        faulthandler.enable()
    except Exception:
        pass
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    import ctypes
    import queue
    winmm = ctypes.windll.winmm
    debug = bool(os.environ.get('RTES_AUDIO_DEBUG'))

    def mci(command: str) -> tuple[int, str]:
        buf = ctypes.create_unicode_buffer(256)
        err = winmm.mciSendStringW(ctypes.c_wchar_p(command), buf, 256, None)
        return (int(err), buf.value)
    out_lock = threading.Lock()

    def emit(obj: dict) -> None:
        try:
            with out_lock:
                sys.stdout.write(json.dumps(obj) + '\n')
                sys.stdout.flush()
        except Exception:
            pass
    cmd_q: 'queue.Queue' = queue.Queue()
    active: dict[int, dict] = {}

    def alias_for(sid: int) -> str:
        return f's{sid}'

    def cleanup(info: dict) -> None:
        alias = info['alias']
        mci(f'stop {alias}')
        mci(f'close {alias}')
        path = info.get('path')
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    def do_play(sid: int, path: str) -> None:
        old = active.pop(sid, None)
        if old is not None:
            cleanup(old)
        alias = alias_for(sid)
        err, _ = mci(f'open "{path}" type waveaudio alias {alias}')
        if err:
            emit({'ev': 'error', 'id': sid, 'msg': f'open err={err}'})
            try:
                os.unlink(path)
            except OSError:
                pass
            return
        mci(f'play {alias}')
        active[sid] = {'alias': alias, 'path': path, 'started': False, 'polls': 0}
        emit({'ev': 'started', 'id': sid})

    def do_stop(sid: int) -> None:
        info = active.pop(sid, None)
        if info is not None:
            cleanup(info)

    def do_stop_all() -> None:
        for info in list(active.values()):
            cleanup(info)
        active.clear()

    def poll_finished() -> None:
        finished: list[int] = []
        for sid, info in active.items():
            err, mode = mci(f"status {info['alias']} mode")
            if debug:
                sys.stderr.write(f"poll sid={sid} alias={info['alias']} err={err} mode={mode!r} polls={info['polls']}\n")
                sys.stderr.flush()
            if mode in ('playing', 'paused'):
                info['started'] = True
            info['polls'] += 1
            done = mode in ('stopped', '')
            if done and (info['started'] or info['polls'] >= 12):
                finished.append(sid)
        for sid in finished:
            info = active.pop(sid, None)
            if info is not None:
                cleanup(info)
                emit({'ev': 'finished', 'id': sid})
    stop_flag = threading.Event()

    def mci_worker() -> None:
        while not stop_flag.is_set():
            try:
                msg = cmd_q.get(timeout=0.03)
            except queue.Empty:
                msg = None
            if msg is not None:
                cmd = msg.get('cmd')
                try:
                    if cmd == 'play':
                        do_play(int(msg['id']), str(msg['path']))
                    elif cmd == 'pause':
                        mci(f"pause {alias_for(int(msg['id']))}")
                    elif cmd == 'resume':
                        mci(f"resume {alias_for(int(msg['id']))}")
                    elif cmd == 'stop':
                        do_stop(int(msg['id']))
                    elif cmd == 'stop_all':
                        do_stop_all()
                    elif cmd == 'shutdown':
                        stop_flag.set()
                        break
                except Exception:
                    pass
            poll_finished()
        do_stop_all()
    worker = threading.Thread(target=mci_worker, daemon=True)
    worker.start()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except (ValueError, TypeError):
                continue
            cmd_q.put(msg)
            if msg.get('cmd') == 'shutdown':
                break
    except Exception:
        pass
    finally:
        cmd_q.put({'cmd': 'shutdown'})
        stop_flag.set()
        worker.join(timeout=2.0)
    return 0

class AudioPlayerClient:

    def __init__(self) -> None:
        import tempfile
        self._proc = None
        self._proc_lock = threading.RLock()
        self._reader = None
        self._stderr_reader = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._cur_tts_id = None
        self._fin_cond = threading.Condition()
        self._finished: set[int] = set()
        self._failed: set[int] = set()
        self._tmpdir = tempfile.mkdtemp(prefix='rtes_audio_')
        self._closed = False
        import atexit
        atexit.register(self.shutdown)

    def _spawn_argv(self) -> list[str]:
        if getattr(sys, 'frozen', False):
            return [sys.executable, '--audio-player']
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return [sys.executable, os.path.join(app_dir, 'assist_main.py'), '--audio-player']

    def _ensure_proc(self) -> bool:
        if os.name != 'nt' or self._closed:
            return False
        import subprocess
        with self._proc_lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            try:
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                if getattr(sys, 'frozen', False):
                    meipass = getattr(sys, '_MEIPASS', None)
                    if meipass:
                        env['_MEIPASS2'] = meipass
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                self._proc = subprocess.Popen(self._spawn_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True, encoding='utf-8', bufsize=1, creationflags=creationflags)
            except Exception:
                self._proc = None
                return False
            self._reader = threading.Thread(target=self._read_events, args=(self._proc,), daemon=True)
            self._reader.start()
            self._stderr_reader = threading.Thread(target=self._read_stderr, args=(self._proc,), daemon=True)
            self._stderr_reader.start()
            return True

    def _read_events(self, proc) -> None:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except (ValueError, TypeError):
                    continue
                ev_name = ev.get('ev')
                if ev_name in ('finished', 'error'):
                    with self._fin_cond:
                        sid = int(ev['id'])
                        if ev_name == 'finished':
                            self._finished.add(sid)
                        else:
                            self._failed.add(sid)
                        self._fin_cond.notify_all()
        except Exception:
            pass
        finally:
            with self._fin_cond:
                self._fin_cond.notify_all()

    def _read_stderr(self, proc) -> None:
        import logging
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    logging.getLogger('poll_controller').warning('audio_player: %s', line)
        except Exception:
            pass

    def _alloc_id(self) -> int:
        with self._id_lock:
            sid = self._next_id
            self._next_id += 1
            return sid

    def _write_temp(self, data: bytes) -> str:
        path = os.path.join(self._tmpdir, f'a{self._alloc_id()}.wav')
        with open(path, 'wb') as fp:
            fp.write(data)
        return path

    def _send(self, obj: dict) -> bool:
        if not self._ensure_proc():
            return False
        try:
            with self._proc_lock:
                self._proc.stdin.write(json.dumps(obj) + '\n')
                self._proc.stdin.flush()
            return True
        except Exception:
            return False

    def _proc_alive(self) -> bool:
        with self._proc_lock:
            return self._proc is not None and self._proc.poll() is None

    def play_effect(self, wav_bytes: bytes) -> None:
        if not wav_bytes or self._closed:
            return
        sid = self._alloc_id()
        try:
            path = self._write_temp(wav_bytes)
        except OSError:
            return
        if not self._send({'cmd': 'play', 'id': sid, 'path': path}):
            try:
                os.unlink(path)
            except OSError:
                pass

    def play_tts_and_wait(self, wav_bytes: bytes, *, should_continue, is_paused) -> bool:
        if not wav_bytes or self._closed:
            return False
        sid = self._alloc_id()
        try:
            path = self._write_temp(wav_bytes)
        except OSError:
            return False
        with self._fin_cond:
            self._finished.discard(sid)
            self._failed.discard(sid)
        self._cur_tts_id = sid
        if not self._send({'cmd': 'play', 'id': sid, 'path': path}):
            try:
                os.unlink(path)
            except OSError:
                pass
            return False
        paused = False
        try:
            while True:
                with self._fin_cond:
                    if sid in self._finished:
                        self._finished.discard(sid)
                        return True
                    if sid in self._failed:
                        self._failed.discard(sid)
                        return False
                    if not self._proc_alive():
                        return False
                    self._fin_cond.wait(timeout=0.05)
                if not should_continue():
                    self._send({'cmd': 'stop', 'id': sid})
                    return False
                want_pause = bool(is_paused())
                if want_pause and (not paused):
                    self._send({'cmd': 'pause', 'id': sid})
                    paused = True
                elif not want_pause and paused:
                    self._send({'cmd': 'resume', 'id': sid})
                    paused = False
        finally:
            if self._cur_tts_id == sid:
                self._cur_tts_id = None

    def stop_tts(self) -> None:
        sid = self._cur_tts_id
        if sid is not None:
            self._send({'cmd': 'stop', 'id': sid})

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._proc_lock:
            proc = self._proc
            self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write(json.dumps({'cmd': 'shutdown'}) + '\n')
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            import shutil
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass
_client: AudioPlayerClient | None = None
_client_lock = threading.Lock()

def get_client() -> AudioPlayerClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = AudioPlayerClient()
        return _client

def shutdown_client() -> None:
    global _client
    with _client_lock:
        client = _client
        _client = None
    if client is not None:
        client.shutdown()
__all__ = ['run_player', 'AudioPlayerClient', 'get_client', 'shutdown_client']
