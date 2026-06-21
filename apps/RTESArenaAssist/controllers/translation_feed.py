"""controllers/translation_feed.py — 翻訳反映を読み上げ(＋将来ログ)へ分配する。

ui_router の単一オブザーバー（翻訳が実反映された時・変化時のみ）から呼ばれる。

発生源宣言化: 何を読むかの判定は、表示を組む発生源が DisplayIntent
へ宣言する（読み上げ役割 speech_role / 読み上げ本文 speech_text）。受け手である
本クラスは宣言を消費するだけで、出どころ名の再分類・メニュー形状の推測・価格交渉
の行分けといった再判定は一切行わない（classify→consume）。

読み上げ役割（意味ベース3分類）:
  "situation"     … 状況説明（トリガー/入店/ダンジョンの出来事/各種ダイアログ/
                    導入ストーリー/ビジョン/キャラ作成の説明 等）
  "conversation"  … 会話（街中NPC応答/施設NPC・店主のセリフ/宮殿会話/価格交渉応答）
  None            … 宣言なし＝システム/メニュー扱い＝読まない（安全側）

読み上げ役割の宣言が唯一のゲート。タイトル/キャラ作成中(pregame/chargen)でも、
発生源が役割を宣言した表示（導入ナレーション・ビジョン・キャラ作成の説明）は読む。
タイトルメニュー等のシステム表示は宣言しないので構造的に読まれない。
"""
from __future__ import annotations

import assist_settings as settings
import i18n_helper as i18n

# 読み上げ役割 → 読み上げ対象設定キー（既定 True＝読む）。
_ROLE_SETTING = {
    "situation":    "tts_target_situation",
    "conversation": "tts_target_conversation",
}


class TranslationFeed:
    """翻訳反映を TTS（＋将来ログ）へ分配する。

    判定は発生源が DisplayIntent へ宣言済み。本クラスは宣言を消費し、横断条件
    （通常プレイ中か・設定ゲート）だけを適用する。
    """

    def __init__(self, tts, window=None, log_store=None) -> None:
        self._tts = tts
        self._window = window
        self._log_store = log_store
        # 直近に読み上げた本文。描画の往復（例: 応答↔メニューの再アサート）で
        # 同一内容が再通知されても重複発声しないための演出側の冪等ガード。
        self._last_spoken: str | None = None
        # 冪等ガードの有効範囲は「同一文脈内」。文脈が変わったら（タイトルへ復帰・
        # ロード等）クリアし、同一テキストでも改めて読む。top_level の変化で検出。
        self._last_top_level: str | None = None

    def on_translation(self, panel_owner: str, original: str, text: str,
                       speech_role: str | None = None,
                       speech_text: str | None = None) -> None:
        # 文脈（top_level）が変わったら冪等ガードをクリアする。タイトルへ復帰や
        # 画面遷移で文脈が変わったら、直前と同一テキストでも改めて読む。
        # （未宣言の画面=タイトルメニュー等でも on_translation は呼ばれるため、
        #  speech_role の有無に関わらず先に文脈変化を検出する。ロードは別途
        #  reset_spoken で lifecycle から明示クリアする。）
        self._reset_guard_on_context_change()
        # 宣言なし＝読まない（安全側）。受け手は役割を推測しない。
        # 読み上げ役割の宣言が唯一のゲート（pregame/chargen でも宣言があれば読む）。
        if speech_role is None:
            return
        # 読み上げ本文は発生源の宣言を優先（無指定なら表示訳）。
        read_text = speech_text if speech_text is not None else text
        if not read_text:
            return
        # 翻訳ログへ追記（TTS の有効/無効に依存しない）。
        # ログは「読み上げ対象として宣言された内容」を時系列で記録する。
        if self._log_store is not None:
            self._append_log(speech_role, read_text, original)
        if not settings.get("tts_enabled", False):
            return
        key = _ROLE_SETTING.get(speech_role)
        if not (key and bool(settings.get(key, True))):
            return
        # 演出は描画の確定結果に追従する。同一本文の再アサート（描画往復）は
        # 読まない（直前に読んだ本文と一致したら無視）。読まれない宣言
        # （メニュー等）は _last_spoken を更新しないので、応答↔メニュー往復でも
        # 応答の再読みが起きない。
        if read_text == self._last_spoken:
            return
        self._last_spoken = read_text
        # 読み上げのみキャラクター名を指定の読みへ置換（表示/ログは元の名前のまま）。
        self._tts.speak(self._apply_name_reading(read_text))

    def _reset_guard_on_context_change(self) -> None:
        """top_level（文脈）が変わったら重複読み上げガードをクリアする。

        さらにセッション境界（タイトル復帰=pregame / 新規キャラ作成=chargen への
        進入）では未保存ログ（アクティブ層）もクリアする。システムメニューからの
        ニューゲームで前セッションのログが残らないようにする（ロードは lifecycle
        が別途差し替える）。
        """
        w = self._window
        if w is None:
            return
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:  # noqa: BLE001
            return
        if tl != self._last_top_level:
            prev = self._last_top_level
            self._last_top_level = tl
            self._last_spoken = None
            # セッション境界で未保存ログをクリア（起動直後 prev=None は除く）。
            if prev is not None and tl in ("pregame", "chargen") \
                    and self._log_store is not None:
                try:
                    self._log_store.reset_active()
                except Exception:  # noqa: BLE001
                    pass

    def reset_spoken(self) -> None:
        """重複読み上げガードを明示クリアする（ロード/タイトル復帰時に呼ぶ）。"""
        self._last_spoken = None
        self._last_top_level = None

    def _apply_name_reading(self, text: str) -> str:
        """テンプレートで置換されたキャラクター名を、読み上げ用の読みへ差し替える。

        キャラクター名はゲーム内データから自動取得する（テンプレートの [名前] が
        置換される実名と同一）。設定 tts_name_reading（読み）が空なら何もしない。
        表示・ログには影響しない（発声テキストのみ）。
        """
        reading = settings.get("tts_name_reading", "") or ""
        if not reading:
            return text
        name = self._player_name()
        if name and name in text:
            return text.replace(name, reading)
        return text

    def _player_name(self) -> str:
        """ゲーム内のプレイヤーキャラクター名を読み取る（anchor+0x1AD・26B ASCII）。"""
        w = self._window
        if w is None:
            return ""
        try:
            from spell_reader import PLAYER_NAME_OFFSET
            raw = w._analyzer.read_bytes(w._anchor + PLAYER_NAME_OFFSET, 26)
            return raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _resolve_location(self) -> str:
        """記録する場所を決める。

        通常プレイは `_log_location_hint`（マップと同じフル表記＝都市 - 施設(種別)
        NF）。タイトル画面(pregame)/キャラクター作成(chargen)はゲーム内の場所が
        無いため、それぞれを場所として扱い記録する。
        """
        w = self._window
        if w is None:
            return ""
        try:
            from top_level.top_level_dispatcher import current_state
            tl = current_state(w)
        except Exception:  # noqa: BLE001
            tl = ""
        if tl == "chargen":
            return i18n.tr("log.location.chargen", default="キャラクター作成")
        if tl == "pregame":
            return i18n.tr("log.location.title", default="タイトル画面")
        return getattr(w, "_log_location_hint", "") or ""

    def _append_log(self, category: str, text: str, original: str) -> None:
        """LogStore へ1件追記する（記録時刻=epoch・場所は best-effort）。"""
        try:
            from datetime import datetime
            ts = datetime.now().timestamp()
        except Exception:  # noqa: BLE001
            ts = 0.0
        location = self._resolve_location()
        try:
            self._log_store.append(
                ts=ts, category=category, text=text,
                original=original, location=location)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["TranslationFeed"]
