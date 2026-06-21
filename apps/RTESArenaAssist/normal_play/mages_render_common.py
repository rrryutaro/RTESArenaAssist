"""normal_play/mages_render_common.py — 魔術師ギルド描画モジュール共有ヘルパー。

mages_guild_render_module から分離。挙動不変。
本モジュールは mages_guild_render_module / mages_spellmaker_render の
どちらも import してはならない（依存方向の最下層）。
"""
from __future__ import annotations

import re

# Casting Cost 描画文字列オフセット（anchor 相対）
_COST_STR_OFFSET = 0x929C

# NPC ダイアログ / プロンプト共通スキャンオフセット
_NPC_DIALOG_OFFSET = 0x1044
_PROMPT_EXTRA_SCAN_OFFSETS = (_COST_STR_OFFSET,)

# Spellmaker 詳細キャッシュキー属性名（本体 _cleanup でも参照）
_SPELLDETAIL_KEY = "_mages_spelldetail_key_prev"


def _translate_ui(en: str) -> str:
    """ui.json で UI 文字列を翻訳する（魔術師ギルド文脈・未登録は原文）。

    context-aware 直引き (`translate_ui_text("mages_guild", en)`)。
    未登録は旧 `_load_ui_dict()` fallback 経由で None になるため原文 (en) を返す。
    """
    try:
        from shop_menu_reader import translate_ui_text
        return translate_ui_text("mages_guild", en) or en
    except Exception:  # noqa: BLE001
        return en


def _read_cost_string(w):
    """描画文字列 "C=NNNN"(0x929C) から Casting Cost を読む（計算値・確定）。"""
    try:
        raw = w._analyzer.read_bytes(w._anchor + _COST_STR_OFFSET, 24)
    except (OSError, AttributeError):
        return None
    m = re.search(rb"C=(\d+)", raw)
    return int(m.group(1)) if m else None


def _casting_cost_divisor(player_level) -> int:
    """Arena の作成呪文 Casting Cost 変換に使うレベル依存除数。"""
    try:
        level = int(player_level or 0)
    except (TypeError, ValueError):
        level = 0
    return max(1, level + 2) if level > 0 else 4


def _casting_cost_from_spell_cost(spell_cost: int, player_level) -> int:
    return int(spell_cost) // _casting_cost_divisor(player_level)


def _buy_price_for(w, name: str):
    """アクティブ呪文一覧から、指定名の購入価格(int)を返す（無ければ None）。"""
    try:
        from mages_list_reader import read_active_priced_list
        for it in read_active_priced_list(w._analyzer, w._anchor):
            if it.get("en") == name:
                digits = "".join(c for c in it.get("price_display", "")
                                 if c.isdigit())
                return int(digits) if digits else None
    except Exception:  # noqa: BLE001
        pass
    return None
