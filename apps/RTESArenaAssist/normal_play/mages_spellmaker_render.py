"""normal_play/mages_spellmaker_render.py — 魔術師ギルド Spellmaker 描画サブモジュール。

mages_guild_render_module から分離。挙動不変。
本モジュールは mages_render_common を import してよいが、
mages_guild_render_module は import してはならない（循環 import 防止）。
"""
from __future__ import annotations

from normal_play.mages_render_common import (
    _NPC_DIALOG_OFFSET,
    _PROMPT_EXTRA_SCAN_OFFSETS,
    _casting_cost_from_spell_cost,
)

# Spellmaker 専用定数
_SPELLMAKER_LIVE_COST_HALF_OFFSET = 0xFAA4
_SPELLMAKER_COST_CACHE_ATTR = "_mages_spellmaker_cost_cache"
_SPELLMAKER_RECORD_OFFSET = 0x57E6
_SPELLMAKER_RECORD_COST_KEY_LEN = 0x34
_SPELL_KEY = "_mages_spellmaker_key_prev"
_PROMPT_KEY = "_mages_prompt_key_prev"
_SPELLMAKER_PROMPT_LIST_FLAG = 0x01
_SPELLMAKER_PROMPT_HOLD_FLAG = 0x03
_SPELLMAKER_TEMPLATE_PTR_START = 0x5A00
_SPELLMAKER_TEMPLATE_PTR_END = 0x5B00
_ACTIVE_TEMPLATE_PTR_OFFSETS = tuple(range(0xFAB8, 0xFAD8, 2))
_SPELLMAKER_PROMPT_LITERALS = (
    "You must name this spell!",
    "You do not have enough money to purchase this spell",
    "The spell has been inscribed in your spellbook",
    "Not enough room to store spell.",
    "You must choose an effect first!",
)
_SPELLMAKER_PROMPT_FRAGMENT_LITERALS = (
    (("money", "to purchase this spell"),
     "You do not have enough money to purchase this spell"),
    (("inscribed", "spellbook"),
     "The spell has been inscribed in your spellbook"),
    (("not enough room", "store spell"),
     "Not enough room to store spell."),
    (("choose", "effect", "first"),
     "You must choose an effect first!"),
)
_SPELLMAKER_REFRESH_DETAIL_PROMPTS = frozenset({
    "The spell has been inscribed in your spellbook",
})
_SPELLMAKER_LIST_TITLES = frozenset({
    "Targets", "Effects", "Effect Options",
})


def _read_spellmaker_live_spell_cost(
        w, *, casting_cost: int | None = None,
        player_level=None) -> int | None:
    """Spellmaker 編集中のワーク領域 half-cost から Spell Cost を読む。

    SpellData +0x32 が 0 だが、anchor+0xFAA4 に画面表示
    Spell Cost の半分値が残る。残留値誤認を避けるため、C= とレベルから
    導ける Casting Cost と整合する場合だけ採用する。
    """
    if casting_cost is None or casting_cost <= 0:
        return None
    try:
        raw = w._analyzer.read_bytes(
            w._anchor + _SPELLMAKER_LIVE_COST_HALF_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    half_cost = raw[0] | (raw[1] << 8)
    if half_cost <= 0:
        return None
    spell_cost = half_cost * 2
    expected = _casting_cost_from_spell_cost(spell_cost, player_level)
    if expected != casting_cost:
        return None
    return spell_cost


def _spellmaker_cost_cache_key(w, data: dict,
                               casting_cost: int | None) -> tuple:
    """Spellmaker の同一入力状態だけで live cost を再利用するための署名。"""
    try:
        raw_record = w._analyzer.read_bytes(
            w._anchor + _SPELLMAKER_RECORD_OFFSET,
            _SPELLMAKER_RECORD_COST_KEY_LEN)
    except (OSError, AttributeError):
        raw_record = b""
    return (
        raw_record,
        data.get("target_id"),
        data.get("element_id"),
        tuple(data.get("effects", [])),
        tuple(data.get("sub_effects", [])),
        tuple(data.get("affected_attrs", [])),
        data.get("player_level"),
        casting_cost,
    )


def _resolve_spellmaker_spell_cost(
        w, data: dict, *, casting_cost: int | None) -> int:
    """Spellmaker の Spell Cost を、安定レコード優先で決定する。

    通常のステータス/購入詳細と違い、Spellmaker 編集中は +0x5818 が 0 の
    ままになるため live half-cost を使う。ただし live 領域は描画中に揺れるので、
    C= と整合した値だけを同一入力レコードのキャッシュへ保存し、無効な poll で
    表示済みの正しい値を消さない。
    """
    try:
        record_cost = int(data.get("cost") or 0)
    except (TypeError, ValueError):
        record_cost = 0
    if all(x == 0xFF for x in data.get("effects", [])):
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, None)
        return 0
    key = _spellmaker_cost_cache_key(w, data, casting_cost)
    if record_cost > 0:
        spell_cost = record_cost * 2
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, (key, spell_cost))
        return spell_cost

    live_spell_cost = _read_spellmaker_live_spell_cost(
        w, casting_cost=casting_cost, player_level=data.get("player_level"))
    if live_spell_cost:
        setattr(w, _SPELLMAKER_COST_CACHE_ATTR, (key, live_spell_cost))
        return live_spell_cost

    cached = getattr(w, _SPELLMAKER_COST_CACHE_ATTR, None)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_key, cached_cost = cached
        if cached_key == key:
            try:
                return int(cached_cost)
            except (TypeError, ValueError):
                return 0
    return 0


def _has_spellmaker_prompt_slot(w) -> bool:
    """Spellmaker 表示中に併走する 0x5Axx テンプレ slot を検出する。"""
    for off in _ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = w._analyzer.read_bytes(w._anchor + off, 2)
        except (OSError, AttributeError):
            continue
        if len(raw) < 2:
            continue
        ptr = raw[0] | (raw[1] << 8)
        if _SPELLMAKER_TEMPLATE_PTR_START <= ptr < _SPELLMAKER_TEMPLATE_PTR_END:
            return True
    return False


def _is_spellmaker_prompt_foreground(w, sig: dict) -> bool:
    """Spellmaker 応答プロンプトが前景表示中かを L4 信号だけで判定する。"""
    if not (
        sig.get("view") == 0x00
        and sig.get("type") == 0xC7
        and sig.get("dialog") == 0x3D
    ):
        return False
    list_flag = sig.get("list")
    if list_flag == _SPELLMAKER_PROMPT_LIST_FLAG:
        return True
    if list_flag == _SPELLMAKER_PROMPT_HOLD_FLAG:
        return _has_spellmaker_prompt_slot(w)
    return False


def _resolve_spellmaker_prompt(w, sig: dict):
    """Spellmaker 背景上に重なる Spellmaker 専用プロンプトだけを解決する。

    `0x1044` には Detect Magic の見積り/結果が残留する。Spellmaker 画面では
    それらを overlay として採用せず、呪文作成・購入完了系の文だけに限定する。
    `0x5AAB` 等の A.EXE 固定テンプレは閉じた後も current ptr に残るため、
    L4 の前景信号と Spellmaker 0x5Axx active slot が表示中を示す時だけ読む。
    """
    if not _is_spellmaker_prompt_foreground(w, sig):
        return None
    try:
        raw = w._analyzer.read_bytes(w._anchor + _NPC_DIALOG_OFFSET, 512)
    except (OSError, AttributeError):
        raw = b""
    extra_chunks: list[bytes] = []
    for off in _PROMPT_EXTRA_SCAN_OFFSETS:
        try:
            extra_chunks.append(w._analyzer.read_bytes(w._anchor + off, 160))
        except (OSError, AttributeError):
            extra_chunks.append(b"")
    text = "".join(
        c if 0x20 <= ord(c) <= 0x7E else " "
        for c in raw.decode("ascii", errors="replace"))
    literal_text = text + " " + " ".join(
        "".join(
            c if 0x20 <= ord(c) <= 0x7E else " "
            for c in chunk.decode("ascii", errors="replace"))
        for chunk in extra_chunks)
    normalized_text = " ".join(literal_text.split())
    try:
        from npc_dialog_lookup import lookup as _nd_lookup
        from npc_dialog_lookup import format_japanese as _nd_format
    except Exception:  # noqa: BLE001
        return None

    for literal in _SPELLMAKER_PROMPT_LITERALS:
        if literal not in normalized_text:
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                return literal, _nd_format(res[0], res[1])
            except Exception:  # noqa: BLE001
                return literal, literal

    lowered_text = normalized_text.lower()
    for needles, literal in _SPELLMAKER_PROMPT_FRAGMENT_LITERALS:
        if not all(needle in lowered_text for needle in needles):
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                return literal, _nd_format(res[0], res[1])
            except Exception:  # noqa: BLE001
                return literal, literal
    return None
