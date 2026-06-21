"""翻訳タブの panel_mode を flush で1回だけ確定する純ロジック。

表示モード単一権威化の中核。
panel_mode を書く経路を poll 末尾の flush 1 か所へ収束させるため、
「flush の勝者 intent が運ぶ mode を、emulate / fallback 設定に従って
実適用 mode へ確定する」判定を副作用なしの純関数として切り出す。

mode は owner ではなく intent の種別が運ぶ (owner `npc_dialog` が
place_list と translate の双方で使われるため owner→mode は写像にできない)。
本モジュールは値だけを受け取り window を参照しない。

mode 文字列は tabs/tab_translate.py の _MODE_* と一致させること。
"""
from __future__ import annotations

from typing import Optional


# tab_translate._MODE_* と一致させる (単一の真実は tab_translate 側だが、
# 純ロジックを GUI 依存なしに単体テストするためここにも定義する)。
MODE_TRANSLATE = "translate"
MODE_FALLBACK_MAP = "fallback_map"
MODE_FALLBACK_STATUS = "fallback_status"

# 前景 list / 全画面 screen 系 mode。勝者がこれらなら床 (fallback) より
# 優先してそのまま通す。
FOREGROUND_MODES = frozenset({
    "item_pickup",
    "shop_buy",
    "facility_list",
    "equipment",
    "spell_detail",
    "place_list",
    "load_screen",
    "choose_attributes",
    "class_list",
    "race_list",
    "appearance_faces",
})

# 翻訳系 / 不在。fallback 床判定の対象。
_TRANSLATE_FAMILY = frozenset({
    MODE_TRANSLATE,
    MODE_FALLBACK_MAP,
    MODE_FALLBACK_STATUS,
})

# assist_settings "translate_fallback_screen" の値 → mode。
_FALLBACK_SETTING_TO_MODE = {
    "map": MODE_FALLBACK_MAP,
    "status": MODE_FALLBACK_STATUS,
}


def resolve_flush_mode(*, winner_mode: Optional[str],
                       top_level: str,
                       emulate: bool,
                       winner_has_content: bool,
                       winner_is_tab_owner: bool,
                       fallback_setting: str) -> str:
    """flush で実際に適用する tab mode を1回で決める。

    引数:
      winner_mode: flush の勝者 intent が運ぶ mode (None=mode 指定なし=翻訳系扱い)。
      top_level: "pregame" / "chargen" / "normal-play"。
      emulate: settings "translate_tab_emulate_panel_hidden" (検証モード)。
      winner_has_content: 勝者が空でない翻訳本文を持つか。
      winner_is_tab_owner: 勝者 owner が会話/tab表示 owner か
        (hierarchy_state.CONVERSATION_PANEL_OWNERS。NPC/施設会話は tab に本文を
        出すため fallback 床を発動しない。現 _apply_translation の
        suppress_fallback=True 経路と同義)。
      fallback_setting: settings "translate_fallback_screen" ("map"/"status"/...)。

    規則:
      1. winner_mode が前景 list/screen 系 → そのまま (前景表示が床に優先)。
      2. 翻訳系/不在:
         - normal-play 以外 → translate (フォールバック非発動)。
         - 会話/tab owner → translate (本文を tab に表示・床を発動しない)。
         - emulate かつ本文あり → translate (tab にも翻訳を出す)。
         - それ以外 → fallback_setting 写像 (map/status / なければ translate)。
    """
    if winner_mode in FOREGROUND_MODES:
        return winner_mode

    # ここに来るのは translate / fallback_* / None (翻訳系・不在)。
    if top_level != "normal-play":
        return MODE_TRANSLATE
    if winner_is_tab_owner:
        return MODE_TRANSLATE
    if emulate and winner_has_content:
        return MODE_TRANSLATE
    return _FALLBACK_SETTING_TO_MODE.get(fallback_setting, MODE_TRANSLATE)


__all__ = [
    "resolve_flush_mode",
    "FOREGROUND_MODES",
    "MODE_TRANSLATE",
    "MODE_FALLBACK_MAP",
    "MODE_FALLBACK_STATUS",
]
