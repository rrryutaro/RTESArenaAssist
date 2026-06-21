"""services/sound_effect.py — 短い効果音(WAV)の安定再生。

シャッターSE 等の短い WAV を **winsound(Windows 標準 PlaySound API)** で
非同期再生する。Qt の QSoundEffect(Qt Multimedia バックエンド)は SAPI5 読み上げ
など別の native 音声と同時再生すると native クラッシュするため使わない。winsound は
SAPI5 と問題なく共存できる。音量は in-memory で PCM をスケールして維持する。

Windows 以外 / winsound 不在 / 失敗時は無音(例外は飲み、機能停止させない)。
"""
from __future__ import annotations

import io
import logging
import threading

_log = logging.getLogger("poll_controller")


def _scale_wav_volume(wav_bytes: bytes, volume: float) -> bytes:
    """WAV(PCM) を音量 volume(0..1) でスケールした WAV バイト列を返す。

    非PCM/スケール失敗時は元のバイト列をそのまま返す(無加工で再生)。
    """
    v = max(0.0, min(1.0, float(volume)))
    if v >= 0.999:
        return wav_bytes
    try:
        import wave
        import audioop  # 3.13 で削除予定だが現行(3.11)は同梱
        with wave.open(io.BytesIO(wav_bytes), "rb") as wr:
            params = wr.getparams()
            frames = wr.readframes(wr.getnframes())
        scaled = audioop.mul(frames, params.sampwidth, v)
        out = io.BytesIO()
        with wave.open(out, "wb") as ww:
            ww.setparams(params)
            ww.writeframes(scaled)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return wav_bytes


def play_wav_async(wav_bytes: bytes, volume: float = 1.0) -> None:
    """WAV バイト列を winsound で再生する(UI を止めない・SAPI5 と共存可)。

    winsound は `SND_MEMORY|SND_ASYNC`(メモリからの非同期)を許可しない
    ("Cannot play asynchronously from memory")。そこで **デーモンスレッドで
    SND_MEMORY(同期)再生**し、UI スレッドはブロックしない。data はスレッドの
    クロージャが保持するため GC されない。Windows 以外/失敗時は無音。
    """
    if not wav_bytes:
        return
    try:
        import winsound
    except Exception:  # noqa: BLE001
        return  # Windows 以外
    data = _scale_wav_volume(wav_bytes, volume)

    def _worker() -> None:
        try:
            # SND_ASYNC は付けない(メモリからの非同期は不可)。同期再生だが
            # ワーカースレッドなので UI はブロックしない。
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:  # noqa: BLE001
            _log.exception("sound_effect: winsound play failed")

    threading.Thread(target=_worker, daemon=True).start()


def play_wav_file(path: str, volume: float = 1.0) -> None:
    """WAV ファイルを読み込んで winsound で非同期再生する(設定プレビュー等)。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return
    play_wav_async(data, volume)


__all__ = ["play_wav_async", "play_wav_file"]
