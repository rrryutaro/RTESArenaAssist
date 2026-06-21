"""tts_service.py — テキスト読み上げ(TTS)サービス。

Arena 用に整形:
  - SAPI5 (win32com / pywin32) による in-process 読み上げ。pywin32 未導入時は
    PowerShell フォールバック（非推奨）。
  - キュー + デーモンスレッドで UI をブロックしない。
  - 切り上げ(interrupt)対応: ON のとき新しいテキストで進行中の読み上げを中止して
    新内容を読む(非同期 Speak + PURGE)。OFF は順次（前を最後まで読んでから次）。
  - 将来のエンジン差し替えに備え本クラスに抽象化。

本サービスは「与えられたテキストを読む」ことに専念する。どのカテゴリを読むか
(トリガー/ダイアログ/NPC 等)の判定は呼び出し側(設定参照)が行う。
"""
from __future__ import annotations

import queue
import re
import threading

# SAPI SpeechVoiceSpeakFlags
_SVSF_ASYNC = 1
_SVSF_PURGE_BEFORE_SPEAK = 2

_URL_RE = re.compile(r"https?://\S+")


class TTSService:
    """テキスト読み上げサービス（SAPI5 バックエンド・キュー+ワーカースレッド）。"""

    def __init__(self, *, start_worker: bool = True) -> None:
        self._enabled = False
        self._interrupt = False        # True=切り上げ ON（新規で中止して読む）
        self._volume = 100             # 0..100
        self._rate = 0                 # SAPI Rate -10..10
        self._voice_desc = ""          # 音声の説明文字列（"" = 既定）
        self._engine = "sapi5"         # "sapi5" / "voicevox"
        self._vv_speaker = 0           # VOICEVOX スタイル id

        # キューエントリ: (text, force) または None（終了）
        self._queue: queue.Queue = queue.Queue()
        self._worker = None
        if start_worker:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    # ── 設定 ──────────────────────────────────────────────
    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_interrupt(self, value: bool) -> None:
        self._interrupt = bool(value)

    def set_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))

    def set_rate(self, value: int) -> None:
        self._rate = max(-10, min(10, int(value)))

    def set_voice(self, desc: str) -> None:
        self._voice_desc = desc or ""

    def set_engine(self, value: str) -> None:
        self._engine = "voicevox" if str(value) == "voicevox" else "sapi5"

    def set_vv_speaker(self, value: int) -> None:
        try:
            self._vv_speaker = int(value)
        except (TypeError, ValueError):
            self._vv_speaker = 0

    # ── 投入 ──────────────────────────────────────────────
    def speak(self, text: str) -> None:
        """自動読み上げ用（master ON のときのみ読む）。"""
        if not self._enabled:
            return
        self._enqueue(text)

    def speak_now(self, text: str) -> None:
        """明示読み上げ用（スピーカーアイコン/右クリック）。master OFF でも読む。"""
        self._enqueue(text)

    def stop_speaking(self) -> None:
        """進行中＋保留中をすべて破棄（無音化）。"""
        self._drain()
        self._stop_playback()          # VOICEVOX 再生（winsound）の中止
        self._queue.put(("", True))   # SAPI PURGE 用の空 speak

    def _stop_playback(self) -> None:
        """winsound で再生中の VOICEVOX 音声を中止する（SAPI には無影響）。"""
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        """ワーカー終了（アプリ終了時）。"""
        self._drain()
        self._queue.put(None)

    def _enqueue(self, text: str) -> None:
        t = self._sanitize(text)
        if not t:
            return
        if self._interrupt:
            # 切り上げ: 保留中を捨て最新だけ残す
            self._drain()
            if self._engine == "voicevox":
                # 進行中の VOICEVOX 同期再生を中断して最新を読む（SAPI は別経路で
                # ワーカー側の非同期 PURGE が担う）。
                self._stop_playback()
        self._queue.put((t, False))

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    # 読み上げ時に除去する文字: アポストロフィ類。SAPI がこれらを「無駄に長く」
    # 読む / スペルアウトすることがあるため、読み上げテキストからのみ取り除く
    # (表示・ログ・翻訳データには一切影響しない。除去は _enqueue 経由の TTS 専用)。
    # ' (U+0027) / ' (U+2019) / ' (U+2018) / ` (U+0060)。
    _APOSTROPHES = ("'", "’", "‘", "`")

    @classmethod
    def _sanitize(cls, text: str) -> str:
        if not text:
            return ""
        t = _URL_RE.sub("", str(text))
        for _ap in cls._APOSTROPHES:
            t = t.replace(_ap, "")
        return t.strip()

    # ── ワーカー ──────────────────────────────────────────
    def _run(self) -> None:
        # 読み上げは SAPI5(win32com・インプロセス)のみ。外部プロセス(PowerShell
        # 等)は一切起動しない。SAPI5 が使えない環境では読み上げを行わず、理由を
        # ログに残すだけ（ユーザーの知らない裏プロセス起動を厳に避ける）。
        speaker = self._init_sapi5()
        had_sapi = speaker is not None
        import logging as _logging
        _tlog = _logging.getLogger("poll_controller")
        if had_sapi:
            # 既定ログ(RECOG)で見えるように warning 相当で残す（稼働インスタンスが
            # 外部プロセスを使わない SAPI5 であることを 1 行で確認できるように）。
            _tlog.warning("TTS backend: SAPI5 (win32com, in-process・外部プロセス無し)")
        else:
            _tlog.warning(
                "TTS unavailable: SAPI5(win32com) を初期化できないため読み上げを"
                "行いません（外部プロセスは起動しません）。pywin32 を確認して"
                "ください（上の SAPI5 init エラーを参照）")
        while True:
            entry = self._queue.get()
            if entry is None:
                break
            text, _force = entry
            if self._engine == "voicevox":
                # VOICEVOX 経路。合成/再生に失敗したら SAPI5 へフォールバック
                # （無音化を防ぐ。VOICEVOX 自体は外部プロセスを起動せず、起動済み
                #  ローカルサーバーへ接続するだけ）。
                if self._speak_voicevox(text):
                    continue
            if speaker is not None:
                self._speak_sapi5(speaker, text)
            # SAPI 不可なら何もしない（外部プロセス起動・窓表示は一切しない）
        # COM オブジェクト参照を CoUninitialize 前に解放（終了時警告の抑制）
        speaker = None
        if had_sapi:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass

    def _speak_sapi5(self, speaker, text: str) -> None:
        try:
            speaker.Volume = self._volume
            speaker.Rate = self._rate
            self._apply_voice(speaker)
            if self._interrupt:
                # 非同期 + 直前を PURGE → 進行中を中止して新内容を読む
                speaker.Speak(text, _SVSF_ASYNC | _SVSF_PURGE_BEFORE_SPEAK)
            else:
                speaker.Speak(text)   # 同期（最後まで読んでから次へ）
        except Exception:  # noqa: BLE001
            pass

    def _speak_voicevox(self, text: str) -> bool:
        """VOICEVOX で text を合成・再生する。成功で True、不達/失敗で False。"""
        t = (text or "").strip()
        if not t:
            # 空（stop_speaking の PURGE 用）は何もせず成功扱い（SAPI へ流さない）
            return True
        try:
            import voicevox_client as vv
            # SAPI Rate(-10..10) を VOICEVOX speedScale(0.5..1.5) へ写像。
            speed = max(0.5, min(2.0, 1.0 + self._rate / 20.0))
            volume = max(0.0, min(2.0, self._volume / 100.0))
            data = vv.synthesize(t, self._vv_speaker,
                                 speed=speed, volume=volume)
        except Exception:  # noqa: BLE001
            return False
        if not data:
            return False
        self._play_wav(data)
        return True

    def _play_wav(self, data: bytes) -> None:
        """WAV バイト列を再生する（VOICEVOX 用）。

        winsound は SND_MEMORY|SND_ASYNC（メモリからの非同期）を許可しないため
        （"Cannot play asynchronously from memory"・services/sound_effect.py 参照）、
        SND_MEMORY（同期）で再生する。本メソッドはデーモンのワーカースレッドから
        呼ばれるため UI はブロックしない。切り上げは _enqueue / stop_speaking 側の
        PURGE（進行中の同期再生を中断）で実現する。
        """
        try:
            import winsound
        except Exception:  # noqa: BLE001
            return
        try:
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:  # noqa: BLE001
            pass

    def _apply_voice(self, speaker) -> None:
        if not self._voice_desc:
            return
        try:
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                tok = voices.Item(i)
                if tok.GetDescription() == self._voice_desc:
                    speaker.Voice = tok
                    return
        except Exception:  # noqa: BLE001
            pass

    def _init_sapi5(self):
        # win32com の dynamic.Dispatch を使う（makepy/gen_py のコード生成を介さ
        # ない＝余計なファイル生成・プロセス起動を避ける純インプロセス経路）。
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client.dynamic
            return win32com.client.dynamic.Dispatch("SAPI.SpVoice")
        except Exception as exc:  # noqa: BLE001
            # 失敗理由を必ず残す（読み上げが無音になる原因の特定用）。
            try:
                import logging as _logging
                _logging.getLogger("poll_controller").warning(
                    "TTS SAPI5 init failed: %s: %s",
                    type(exc).__name__, exc)
            except Exception:  # noqa: BLE001
                pass
            return None

    # ── 音声一覧（設定 UI 用）────────────────────────────
    @staticmethod
    def list_voices() -> list[str]:
        """利用可能な音声の説明一覧を返す（SAPI 不在時は空）。"""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            voices = sp.GetVoices()
            out = []
            for i in range(voices.Count):
                try:
                    out.append(voices.Item(i).GetDescription())
                except Exception:  # noqa: BLE001
                    pass
            return out
        except Exception:  # noqa: BLE001
            return []


__all__ = ["TTSService"]
