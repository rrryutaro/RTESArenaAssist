"""NEWPOP アイテム取得一覧の検出と翻訳タブ表示。

オフセット:
  +0xFF2    = NEWPOP 内の残りアイテム数 (0=閉じている / N=開いている)
  +0x9302   = null 区切りアイテム名リスト (N 個連続)

動作:
  open  : count 0→N で +0x9302 から全名前を読んで一覧表示
  taken : count 減少 → +0x9302 を再読して消えた名前を TAKEN(✓) にする
  close : NEWPOP gate (+0xB7C4) close で翻訳モードへ戻る

count / name buffer は閉じた後も stale に残るため、表示 lifecycle には使わない。

window 側状態: _b32_newpop_open / _b32_seen_items / _b32_was_corpse /
_b32_pending_close_count / _b32_count_prev / _b32_seen_cache_age /
_panel_owner / _tab_translate
"""
from __future__ import annotations

import logging

from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("RTESArenaAssist")


def _read_names(w, count: int) -> list[str]:
    if count <= 0:
        return []
    try:
        raw = w._analyzer.read_bytes(w._anchor + 0x9302, count * 48)
    except (OSError, AttributeError):
        return []
    names, pos = [], 0
    for _ in range(count):
        end = raw.find(b"\x00", pos)
        if end == -1:
            break
        nm = raw[pos:end].decode("ascii", errors="replace").strip()
        if nm:
            names.append(nm)
        pos = end + 1
    return names


def _filter_suffix_fragments(names: list[str]) -> list[str]:
    """同一 list 内で他の name の word-boundary 外 suffix となる断片を除外する。

    stale buffer に残った前回 name の途中位置から始まる文字列
    (例: 'Plate Helm' の末尾断片 'te Helm') を捨てるためのフィルタ。
    """
    if not names:
        return []
    filtered: list[str] = []
    for n in names:
        if not n:
            continue
        is_fragment = False
        for m in names:
            if m is n or m == n or len(m) <= len(n):
                continue
            if m.endswith(n):
                prefix_idx = len(m) - len(n)
                if prefix_idx > 0 and m[prefix_idx - 1] != " ":
                    is_fragment = True
                    break
        if not is_fragment:
            filtered.append(n)
    return filtered


_BLOCKED_SCREENS = ("equipment", "spellbook", "spell_detail",
                    "status_page", "bonus_screen")
_BLOCKED_IMGS = (
    "MRSHIRT.IMG", "EQUIP.IMG", "MPANTS.IMG", "PAGE2.IMG", "CHARSTAT.IMG"
)
_CACHE_TTL = 10

# NEWPOP gate (+0xB7C4 / IMG=NEWPOP.IMG) が poll 間で
# 単発の読み取りノイズにより一時的に閉に見えることがある。その poll で
# item_pickup が自分自身を clear → fallback_map へ戻し、次 poll で再オープンする
# = お宝一覧表示中の cross-poll チラツキの原因。確定クローズは gate が連続して
# 閉のときのみとし、単発ノイズの間は表示を維持する (ヒステリシス)。
_CLOSE_DEBOUNCE_POLLS = 2


def _show_item_pickup(w, items: list[dict], remaining: int) -> None:
    w._ui_router.update_item_pickup_list("item_pickup", items, remaining)


def _clear_item_pickup_owner(w, *, restore_trigger: bool = False) -> None:
    w._ui_router.clear_if_owner("item_pickup", mode="translate")
    if restore_trigger:
        try:
            from normal_play.trigger_module import restore_last_trigger_display
            restore_last_trigger_display(w)
        except (ImportError, AttributeError, RuntimeError) as exc:
            _log.debug("NEWPOP trigger restore skipped: %s", exc)


def _claim_item_pickup_owner(w) -> None:
    w._ui_router.claim_owner("item_pickup", mode="item_pickup")


def poll_item_pickup(w, *, newpop_gate: bool, b30_img_name: str,
                     npc_dialog: str, shop_buy_active: bool,
                     shop_menu_visible: bool,
                     screen_id: str | None = None) -> None:
    from controllers.chargen_helpers import _is_garbage_npc_buffer

    # P2-3: 画面 id は引数で受ける (= _screen_id_prev 直 read の撤去)。
    # 呼出側が確定値を渡せない過渡期は前回値を渡す (= 挙動同一)。未指定時も
    # 後方互換で前回値 _screen_id_prev へフォールバックする。
    _screen_id = (screen_id if screen_id is not None
                  else getattr(w, "_screen_id_prev", None))

    # 安全装置: top_level が normal-play でない場合は強制終了
    if _current_top_level(w) != "normal-play":
        if getattr(w, "_b32_newpop_open", False):
            _log.info(
                "NEWPOP state force-closed due to top_level=%s",
                _current_top_level(w))
            w._b32_newpop_open = False
            w._b32_was_corpse = False
            w._b32_pending_close_count = 0
            _clear_item_pickup_owner(w)
        if getattr(w, "_b32_seen_items", []):
            _log.info(
                "NEWPOP seen cache cleared (reason=top-level top_level=%s)",
                _current_top_level(w))
            w._b32_seen_items = []
            w._b32_seen_cache_age = 0
        return None

    try:
        _count = w._analyzer.read_bytes(w._anchor + 0xFF2, 1)[0]
    except (OSError, AttributeError):
        _count = 0

    _was_open = getattr(w, "_b32_newpop_open", False)
    _cnt_prev = getattr(w, "_b32_count_prev", 0)

    _blocked = (
        _screen_id in _BLOCKED_SCREENS
        or b30_img_name in _BLOCKED_IMGS
        or shop_buy_active
        or shop_menu_visible
    )

    try:
        _first = w._analyzer.read_bytes(w._anchor + 0x9302, 1)[0]
        _names_present = (0x41 <= _first <= 0x5A)
    except (OSError, AttributeError):
        _names_present = False
    _is_open = newpop_gate
    _content_chest_ready = (_count > 0 and _names_present)
    # corpse item として扱う条件を
    # 「`dungeon_msg_lookup.lookup_item(npc_dialog)` がヒットする item 名」
    # に限定。`count==0 && npc_dialog && not garbage` で文メッセージ
    # も corpse item として消費すると、通常の死体クリック / no-loot 文を
    # 翻訳パネルから奪う regression が起きるため。
    _corpse_item_name = False
    if _count == 0 and bool(npc_dialog) and not _is_garbage_npc_buffer(
            npc_dialog):
        try:
            import dungeon_msg_lookup as _dml_check
            _corpse_item_name = bool(_dml_check.lookup_item(npc_dialog))
        except Exception:  # noqa: BLE001
            _corpse_item_name = False
    _content_corpse_ready = _corpse_item_name

    # _b32_seen_items 短命 cache の lifetime 管理
    if not _was_open and getattr(w, "_b32_seen_items", []):
        _cache_age = getattr(w, "_b32_seen_cache_age", 0) + 1
        w._b32_seen_cache_age = _cache_age
        _cache_clear_reason = ""
        if _cache_age >= _CACHE_TTL:
            _cache_clear_reason = "ttl"
        elif _screen_id in _BLOCKED_SCREENS:
            _cache_clear_reason = "blocked-screen"
        if _cache_clear_reason:
            _log.info(
                "NEWPOP seen cache cleared "
                "(age=%d screen=%s reason=%s)",
                _cache_age, _screen_id, _cache_clear_reason)
            w._b32_seen_items = []
            w._b32_seen_cache_age = 0

    if (not _was_open and _is_open and not _blocked
            and (_content_chest_ready or _content_corpse_ready)):
        import dungeon_msg_lookup as _dml
        _is_corpse = _content_corpse_ready and not _content_chest_ready
        if _content_chest_ready:
            _raw_names = _read_names(w, _count)
            _filtered_names = _filter_suffix_fragments(_raw_names)
            _ignored_fragments = [
                n for n in _raw_names if n not in _filtered_names]
            _existing = getattr(w, "_b32_seen_items", []) or []
            _ex_untaken_set = {
                it["en"] for it in _existing if not it["taken"]}
            _known_names = [
                n for n in _filtered_names if n in _ex_untaken_set]
            _unknown_names = [
                n for n in _filtered_names if n not in _ex_untaken_set]
            _cache_valid_chest = (
                bool(_existing)
                and not getattr(w, "_b32_was_corpse", False)
            )
            if _cache_valid_chest and _known_names:
                # same chest: existing を保持、known_names に無い untaken を
                # taken 化、unknown_names は捨てる
                _seen = list(_existing)
                _new_known_set = set(_known_names)
                for it in _seen:
                    if not it["taken"] and it["en"] not in _new_known_set:
                        it["taken"] = True
                _remaining = sum(1 for it in _seen if not it["taken"])
                _log.info(
                    "NEWPOP re-OPEN (same chest): "
                    "known=%s unknown=%s ignored_fragments=%s remaining=%d",
                    _known_names, _unknown_names,
                    _ignored_fragments, _remaining)
            else:
                # 新規 chest: filtered_names を採用
                _seen = [
                    {"en": n, "ja": _dml.lookup_item(n), "taken": False}
                    for n in _filtered_names
                ]
                _remaining = len(_filtered_names)
                if _ignored_fragments or _existing:
                    _log.info(
                        "NEWPOP new chest "
                        "(raw=%s ignored_fragments=%s "
                        "ex_untaken=%d known=%d remaining=%d)",
                        _raw_names, _ignored_fragments,
                        len(_ex_untaken_set), len(_known_names),
                        _remaining)
        else:
            _seen = [
                {"en": npc_dialog,
                 "ja": _dml.lookup_item(npc_dialog) or "",
                 "taken": False}
            ]
            _remaining = 1
        w._b32_newpop_open = True
        w._b32_seen_items = _seen
        w._b32_was_corpse = _is_corpse
        w._b32_pending_close_count = 0
        w._b32_seen_cache_age = 0
        _show_item_pickup(w, _seen, _remaining)
        _log.info("NEWPOP popup OPEN (%s): %s",
                  "corpse" if _is_corpse else "chest",
                  [it["en"] for it in _seen])

    elif _was_open:
        # item_pickup の lifecycle 軸は
        # NEWPOP gate (+0xB7C4) のみ。count / names は閉じた後も stale に
        # 残るため、payload 残存で owner を維持してはいけない。
        _img_now_upper = (b30_img_name or "").upper()
        _no_content_close = (
            _count == 0 and not _names_present
            and not _corpse_item_name
        )
        _gate_closed = not _is_open

        if _gate_closed:
            # gate-close ヒステリシス: 単発の gate ノイズで
            # item_pickup が自分を閉じ→再オープンする cross-poll チラツキを抑える。
            # 連続クローズが _CLOSE_DEBOUNCE_POLLS に達するまでは表示を維持する。
            _pending = getattr(w, "_b32_pending_close_count", 0) + 1
            w._b32_pending_close_count = _pending
            if _pending < _CLOSE_DEBOUNCE_POLLS:
                # 単発ノイズの猶予中: 確定クローズせず表示を維持 (owner/mode 再アサート)。
                _log.info(
                    "NEWPOP gate transient-close ignored "
                    "(pending=%d/%d img=%r count=%d names_present=%s "
                    "corpse_item=%s)",
                    _pending, _CLOSE_DEBOUNCE_POLLS, _img_now_upper,
                    _count, _names_present, _corpse_item_name)
                _claim_item_pickup_owner(w)
            else:
                _close_reason = (
                    "no-content" if _no_content_close else "gate-closed")
                if _no_content_close:
                    _seen_final = getattr(w, "_b32_seen_items", []) or []
                    _final_changed = False
                    for _it in _seen_final:
                        if not _it["taken"]:
                            _it["taken"] = True
                            _final_changed = True
                    if _final_changed and _seen_final:
                        try:
                            _show_item_pickup(w, _seen_final, 0)
                        except AttributeError:
                            pass
                _log.info(
                    "NEWPOP popup CLOSE (img=%r count=%d names_present=%s "
                    "corpse_item=%s gate_open=%s pending=%d panel_mode=%s "
                    "panel_owner=%s reason=%s)",
                    _img_now_upper, _count, _names_present, _corpse_item_name,
                    _is_open, _pending,
                    getattr(w._tab_translate, "panel_mode", lambda: "?")(),
                    w._panel_owner, _close_reason)
                if getattr(w, "_b32_was_corpse", False):
                    w._b32_seen_items = []
                w._b32_newpop_open = False
                w._b32_was_corpse = False
                w._b32_pending_close_count = 0
                w._b32_seen_cache_age = 0
                if _screen_id not in (
                        "equipment", "spellbook", "spell_detail"):
                    _clear_item_pickup_owner(w, restore_trigger=True)
        else:
            # open 維持: pending counter リセット + panel_mode/owner 再アサート
            # (= 別 handler の一時更新で mode が戻るケースを潰す)
            w._b32_pending_close_count = 0
            _claim_item_pickup_owner(w)

        if (_is_open and not w._b32_was_corpse
                and _count < _cnt_prev
                and _content_chest_ready):
            # chest アイテム取得: 消えた名前を TAKEN にする
            _seen = getattr(w, "_b32_seen_items", [])
            _names_now = set(_read_names(w, _count))
            _changed = False
            for _it in _seen:
                if not _it["taken"] and _it["en"] not in _names_now:
                    _it["taken"] = True
                    _changed = True
            if _changed:
                _show_item_pickup(w, _seen, _count)
        elif (_is_open
              and w._b32_was_corpse
              and _content_corpse_ready
              and npc_dialog != (w._b32_seen_items[0]["en"]
                                 if w._b32_seen_items else "")):
            # corpse 次アイテム表示
            import dungeon_msg_lookup as _dml2
            _seen = [{"en": npc_dialog,
                      "ja": _dml2.lookup_item(npc_dialog) or "",
                      "taken": False}]
            w._b32_seen_items = _seen
            _show_item_pickup(w, _seen, 1)

    w._b32_count_prev = _count


__all__ = ["poll_item_pickup"]
