"""voicevox_client.py — VOICEVOX エンジン（ローカル HTTP サーバー）との通信。

VOICEVOX は 127.0.0.1:50021 で待ち受ける常駐 HTTP サーバー型の音声合成エンジン。
本モジュールは以下の薄いクライアントを提供する:
  - is_available():  エンジンが起動して応答するか（= 利用可否の判定）
  - list_speakers(): キャラクター＋スタイル一覧
  - synthesize():    テキスト → WAV バイト列

外部プロセスの起動は一切行わない（既に起動しているサーバーへ接続するだけ）。
依存追加を避けるため標準ライブラリ（urllib）のみを使う。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50021


def _base() -> str:
    return f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def is_available(timeout: float = 0.3) -> bool:
    """VOICEVOX エンジンが起動して応答するかを確認する（短 timeout）。"""
    try:
        req = urllib.request.Request(_base() + "/version", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200) == 200
    except Exception:  # noqa: BLE001
        return False


def list_speakers(timeout: float = 3.0) -> list[dict]:
    """話者一覧を返す。

    要素 = {"name": <キャラクター名>, "styles": [{"name": <スタイル名>, "id": int}, ...]}。
    取得できない場合は空リスト。
    """
    try:
        req = urllib.request.Request(_base() + "/speakers", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for sp in raw:
        try:
            styles = [
                {"name": st.get("name", ""), "id": int(st.get("id"))}
                for st in sp.get("styles", [])
                if st.get("id") is not None
            ]
            if styles:
                out.append({"name": sp.get("name", ""), "styles": styles})
        except Exception:  # noqa: BLE001
            continue
    return out


def synthesize(text: str, speaker_id: int, *,
               speed: float = 1.0, volume: float = 1.0,
               timeout: float = 15.0) -> bytes | None:
    """text を speaker_id（スタイル id）で合成し WAV バイト列を返す。失敗時 None。

    speed → speedScale, volume → volumeScale に反映する（基本パラメータのみ）。
    """
    t = (text or "").strip()
    if not t:
        return None
    try:
        # 1) audio_query（パラメータはクエリ文字列で渡す）
        q = urllib.parse.urlencode({"text": t, "speaker": int(speaker_id)})
        req = urllib.request.Request(
            _base() + "/audio_query?" + q, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            query = json.loads(resp.read().decode("utf-8"))
        # 2) 基本パラメータの反映（速度・音量）
        query["speedScale"] = float(speed)
        query["volumeScale"] = float(volume)
        # 3) synthesis（audio_query の結果を body に、WAV を受け取る）
        q2 = urllib.parse.urlencode({"speaker": int(speaker_id)})
        body = json.dumps(query).encode("utf-8")
        req2 = urllib.request.Request(
            _base() + "/synthesis?" + q2, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2, timeout=timeout) as resp:
            return resp.read()
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "is_available", "list_speakers", "synthesize",
    "DEFAULT_HOST", "DEFAULT_PORT",
]
