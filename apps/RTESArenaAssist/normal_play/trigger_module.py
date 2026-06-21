"""ダンジョン / ゲームプレイ中のメッセージ系: トリガー / 赤文字 / 金貨ドロップ / ダイアログ close。

normal_play/trigger_module.py に該当。
window 側状態を参照・更新し、UiRouter 経由で翻訳タブ・パネルを更新する。
"""
from __future__ import annotations

import logging

from arena_bridge import (
    SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN,
    TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ,
    get_trigger_text_by_index,
)
import inf_text_lookup as itl
import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.c1_cinematic_module import _current_hp_is_zero

_log = logging.getLogger("RTESArenaAssist")

_DEATH_RED_TEXTS = frozenset({
    "You are dead",
    "You have been slain",
})


def _entry_to_payload(entry: dict) -> tuple[str, str, str, str]:
    """trigger entry を ``(tab_en, tab_ja, panel_en, panel_ja)`` に分解する。

    riddle entry は question 単独で tab / panel 共に同じ表示にする。
    非 riddle entry は 3-layer schema に従う。
    """
    if entry.get("type") == "riddle":
        en = entry.get("question", "") or ""
        trans = itl.get_translation(entry)
        ja = trans.get("question", "") if isinstance(trans, dict) else ""
        return en, ja, en, ja
    en = itl.get_text_display(entry) or ""
    ja_disp = itl.get_translation_display(entry)
    ja = ja_disp if isinstance(ja_disp, str) else ""
    panel_en = itl.get_text_panel(entry) or ""
    panel_ja_raw = itl.get_translation(entry)
    panel_ja = panel_ja_raw if isinstance(panel_ja_raw, str) else ""
    return en, ja, panel_en, panel_ja


def _render_trigger_entry(w, entry: dict) -> None:
    """trigger entry hit 経路: chargen UI 状態を非 chargen に同期してから
    ``UiRouter.update_translation`` を ``trigger`` owner で呼ぶ。

    trigger entry は normal-play の非 chargen entry のため、汎用 entry
    描画路 (_update_translate_tab) の chargen 同期副作用と同等の
    ``_set_chargen_ui_state(False)`` を維持する。
    """
    try:
        w._set_chargen_ui_state(False)
    except (AttributeError, RuntimeError):
        pass
    en, ja, panel_en, panel_ja = _entry_to_payload(entry)
    _store_last_trigger_display(w, en, ja, panel_en, panel_ja)
    w._ui_router.update_translation(
        "trigger", en, ja, panel_en=panel_en, panel_ja=panel_ja,
        speech_role="situation")


def _store_last_trigger_display(
        w, en: str, ja: str, panel_en: str | None = None,
        panel_ja: str | None = None) -> None:
    w._last_trigger_display = (en, ja, panel_en, panel_ja)
    w._last_trigger_active = True


def restore_last_trigger_display(w) -> bool:
    """item_pickup 等の一時 owner 終了後に、継続中 trigger 表示を戻す。"""
    if not getattr(w, "_last_trigger_active", False):
        return False
    payload = getattr(w, "_last_trigger_display", None)
    if not payload:
        return False
    en, ja, panel_en, panel_ja = payload
    w._ui_router.update_translation(
        "trigger", en, ja, panel_en=panel_en, panel_ja=panel_ja,
        speech_role="situation")
    return True


def _is_death_red_text(text: str) -> bool:
    return (text or "").strip() in _DEATH_RED_TEXTS


# C1/runtime ダイアログ面の単一前景判定 (真1軸化)。各 owner が読む runtime
# バッファ (+0x7979 / +0x929E=死体クリック時の金貨有無メッセージ / npc_dialog 系
# +0x1044・+0x9A9E) は c1_dialog_axis.a845 (= 0xA845・1 poll に 1値) と fg ポインタ
# (= 0xA844・単一バッファを指す) によって相互排他に決まる。各 surface が ad-hoc に
# 前景を読み、防御的相互排他ガード (poll_red_text の `not npc_dialog_changed` /
# poll_dialog_close の new-event-skip 等) で競合回避していた並列評価を、単一の前景
# 判定へ構造化する基礎。
# slot キーは表示 owner と対応: runtime_msg→red_text(_dialog) / corpse_gold→gold_drop
# / dungeon_msg→c1_runtime_dialog。
_C1_DIALOG_A845_TO_SLOT = {
    0x79: "runtime_msg", 0x92: "corpse_gold", 0x10: "dungeon_msg",
}
_C1_DIALOG_BUFFER_RANGES = {
    "runtime_msg": ((0x7979, 68),),
    "corpse_gold": ((0x929E, 512),),
    "dungeon_msg": ((0x1044, 512), (0x9A9E, 512)),
}


def classify_c1_dialog_substate(w, b30, *,
                                npc_dialog_changed: bool = False) -> str:
    """C1/runtime ダイアログ面の単一前景 surface owner を返す (1軸・純判定・副作用なし)。

    返値: "red_text" / "red_text_dialog" / "gold_drop" / "c1_runtime_dialog" / ""
    (= 既存の表示 owner 識別子)。

    a845 値と fg ポインタが単一値であることから、これらの surface は構造的に
    相互排他であり、どれが前景かは「優先順という仮説」ではなく単一信号の
    順次判定で一意に確定する。a845 が既知 surface 値ならそれを採用し、未確定
    時のみ fg ポインタの指し先バッファで補完する。

    npc_dialog_changed 吸収 (真1軸化): npc_dialog バッファが変化した poll は
    ダンジョンメッセージ (c1_runtime_dialog) 系が前景を取りに来る遷移 poll で
    あり、a845/fg がまだ 0x10/dungeon を確定していない過渡でも runtime_msg
    (red) / 未確定を red より dungeon 前景として確定する。これにより
    `poll_red_text` 側に散在していた防御的相互排他ガード
    (`not npc_dialog_changed`) を単一前景判定へ集約する (走る主体の再配置・
    検出信号は不変・gold は固有ガードを持たないため override 対象外で挙動保存)。
    """
    axis = b30.get("c1_dialog_axis") if isinstance(b30, dict) else None
    a845 = getattr(axis, "a845", 0) if axis is not None else 0
    ptr = getattr(axis, "current_ptr", None) if axis is not None else None

    slot = _C1_DIALOG_A845_TO_SLOT.get(a845, "")
    if not slot and ptr is not None:
        for name, ranges in _C1_DIALOG_BUFFER_RANGES.items():
            if any(start <= ptr < start + length for start, length in ranges):
                slot = name
                break
    # npc_dialog 変化 poll は dungeon メッセージ前景を確定 (gold は固有ガード
    # を持たない=現挙動どおり gold を維持し override しない)。
    if npc_dialog_changed and slot != "corpse_gold":
        return "c1_runtime_dialog"
    if slot == "runtime_msg":
        dialog_active = bool(b30.get("dialog_active")) if isinstance(
            b30, dict) else False
        return "red_text_dialog" if dialog_active else "red_text"
    if slot == "corpse_gold":
        return "gold_drop"
    if slot == "dungeon_msg":
        return "c1_runtime_dialog"
    return ""


def poll_trigger(w, *, new_trigger: bool, trig_fell: bool,
                 trigger_flag: int, trigger_idx: int, trigger_slot: int,
                 body: str, inf_name: str) -> None:
    """トリガー検出時の翻訳表示・タブ更新。

    new_trigger: トリガー新規発火 (flag > prev かつ NPC会話中でない)
    trig_fell:   トリガー消滅 (非0 → 0)
    """
    # トリガー発火中: デバッグ表示 (継続中も更新)
    if trigger_flag != 0:
        w._sb.showMessage(
            f"Trigger: flag=0x{trigger_flag:02X}  INF={inf_name or '(none)'}  "
            f"idx={trigger_idx}  slot={trigger_slot}  body={body[:30]}",
            4000,
        )

    if new_trigger:
        text_index = None
        correct_body = body

        # 優先 1: MIF TRIG 座標照合 (INF 名不問)
        if (w._mif_matcher
                and w._cached_rt_x is not None
                and w._cached_rt_z is not None):
            text_index = w._mif_matcher.find_text_index(
                w._cached_rt_x, w._cached_rt_z)
            if text_index is not None:
                try:
                    raw_b = w._analyzer.read_bytes(
                        w._anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
                    correct_body = get_trigger_text_by_index(raw_b, text_index)
                except OSError:
                    pass

        # 優先 2: TRIGGER_INDEX slot 方式 (フォールバック)
        if text_index is None and trigger_slot > 0:
            text_index = trigger_slot

        if text_index is not None:
            entry = itl.lookup(inf_name, text_index)
            if entry is not None and entry.get("type") == "key":
                entry = None
            if entry is None and correct_body:
                entry = itl.lookup_by_text(inf_name, correct_body)
            if entry is None and correct_body and inf_name:
                entry = itl.lookup_by_substring(inf_name, correct_body)
            if entry is not None:
                _render_trigger_entry(w, entry)
            elif correct_body:
                _store_last_trigger_display(w, correct_body, "")
                w._ui_router.update_translation(
                    "trigger", correct_body, "", speech_role="situation")
        elif correct_body:
            # 優先 3: テキスト内容マッチ
            entry = itl.lookup_by_text(inf_name, correct_body)
            if entry is None and inf_name:
                entry = itl.lookup_by_substring(inf_name, correct_body)
            if entry is not None:
                _render_trigger_entry(w, entry)
            else:
                _store_last_trigger_display(w, correct_body, "")
                w._ui_router.update_translation(
                    "trigger", correct_body, "", speech_role="situation")

    # トリガー消滅時クリア (非0 → 0)。
    # clear_if_owner は内部で owner 一致を check するため、他 owner が
    # 表示中の場合は影響しない (= 他 owner を消さない)。
    if trig_fell and not settings.get("keep_trigger_on_panel", False):
        w._last_trigger_active = False
        w._ui_router.clear_if_owner("trigger")
    elif trig_fell:
        w._last_trigger_active = False


def compute_b30_state(w, *, screen_id: str | None = None,
                      c_area: str | None = None, c1_axis=None) -> dict:
    """b30 関連の状態 (0x127C / 0x7979 / 0xA845 / SCREEN_IMG) を計算する。

    戻り値: {dialog_flag, dialog_flag_prev, red_str, red_changed,
             dialog_active, dialog_active_prev, img_name, in_gameplay}
    window 側に _b30_*_prev を更新する副作用あり。

    P2-3: in_gameplay 判定の画面 id は引数で受ける (= _screen_id_prev 直 read の
    撤去)。呼出側が確定値を渡せない過渡期は前回値を渡す (= 挙動同一)。未指定時も
    後方互換で前回値 _screen_id_prev へフォールバックする。
    """
    _screen_id = (screen_id if screen_id is not None
                  else getattr(w, "_screen_id_prev", None))
    try:
        _dialog_flag_raw = w._analyzer.read_bytes(w._anchor + 0x127C, 2)
        _dialog_flag = int.from_bytes(_dialog_flag_raw, "little")
    except (OSError, AttributeError):
        _dialog_flag = getattr(w, "_b30_dialog_flag_prev", 0xa301)
    _dialog_flag_prev = getattr(w, "_b30_dialog_flag_prev", 0xa301)
    if _dialog_flag != _dialog_flag_prev:
        _log.debug("b30 0x127C %#06x → %#06x (idle pulse or dialog event)",
                   _dialog_flag_prev, _dialog_flag)
    w._b30_dialog_flag_prev = _dialog_flag

    try:
        _red_raw = w._analyzer.read_bytes(w._anchor + 0x7979, 68)
        _red_str = _red_raw.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace").strip()
    except (OSError, AttributeError):
        _red_str = ""
    _red_prev = getattr(w, "_b30_red_str_prev", "")
    _red_changed = (_red_str != _red_prev)
    if _red_changed:
        _log.debug("b30 0x7979 changed: %r → %r", _red_prev, _red_str)
    w._b30_red_str_prev = _red_str

    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0x00
    _dialog_active      = (_dialog_byte != 0x00)
    _dialog_active_prev = getattr(w, "_b30_dialog_active_prev", False)

    try:
        _img_raw = w._analyzer.read_bytes(
            w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        _img_name = _img_raw.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace").upper()
    except (OSError, AttributeError, ImportError):
        _img_name = ""
    _in_gameplay = (
        _screen_id in (
            None, "game_screen", "combat", "npc_dialog", "shop", "loading")
        and _img_name not in ("MRSHIRT.IMG", "PAGE2.IMG", "CHARSTAT.IMG")
    )

    # ゲームプレイ復帰時に prev state をシード (残留誤検出防止)
    _was_in_gameplay = getattr(w, "_b30_in_gameplay_prev", False)
    if _in_gameplay and not _was_in_gameplay:
        _log.info(
            "b30 gameplay entry: seeding prev state red=%r dialog_active=%s",
            _red_str, _dialog_active)
        w._b30_red_str_prev = _red_str
        w._b30_dialog_flag_prev = _dialog_flag
        _red_changed = False
        _dialog_active_prev = _dialog_active  # シード
    # C1 ダイアログ軸の単一読取 (1軸化): 呼出側が poll 前段で authoritative
    # read 済みの軸を渡せる (c1_axis 引数)。これにより active_template が自前で
    # 再読する二重ソース (1軸化未達ガード) を解消し、active_template /
    # compute_b30_state / c1_surface_dispatch が同一の単一前景を消費する。
    # a845/fg は 1 poll 1値で構造的に排他のため読取位置を前へ寄せても判定不変。
    # 後方互換: c1_axis 未指定 (= 旧呼出) はここで読む (update_prev=True)。
    _c1_axis = c1_axis
    if c_area == "dungeon":
        try:
            if _c1_axis is None:
                from normal_play.c1_dialog_axis import read_c1_dialog_axis
                _c1_axis = read_c1_dialog_axis(
                    w, c_area=c_area, in_gameplay=_in_gameplay,
                    update_prev=True)
            _dialog_active = _c1_axis.active
            _dialog_active_prev = _c1_axis.prev_active
        except Exception as exc:  # noqa: BLE001
            _log.debug("C1 dialog axis read failed: %s", exc)

    w._b30_in_gameplay_prev = _in_gameplay
    w._b30_dialog_active_prev = _dialog_active

    return {
        "dialog_flag": _dialog_flag,
        "dialog_flag_prev": _dialog_flag_prev,
        "red_str": _red_str,
        "red_changed": _red_changed,
        "dialog_byte": _dialog_byte,
        "dialog_active": _dialog_active,
        "dialog_active_prev": _dialog_active_prev,
        "c1_dialog_axis": _c1_axis,
        "c1_dialog_axis_active": bool(_c1_axis and _c1_axis.active),
        "img_name": _img_name,
        "in_gameplay": _in_gameplay,
    }


def poll_red_text(w, *, b30: dict, npc_dialog_changed: bool,
                  c1_fg: str = "") -> None:
    # 単一前景 (classify_c1_dialog_substate) が別の C1 ダイアログ面を指す poll
    # では「描画」しない (= 1軸: 同時に複数面が前景にならない事を制御フローで保証)。
    # 検出 (death_red prev 更新等) は従来どおり走らせ、描画のみ抑止する。
    # c1_fg=="" (未確定) や 自面を指す時は従来どおり描画 (common case 不変)。
    _c1_fg_blocks_render = bool(
        c1_fg and c1_fg not in ("red_text", "red_text_dialog"))
    _death_red_allowed = (
        _is_death_red_text(b30["red_str"])
        and _current_hp_is_zero(w)
    )
    if not _death_red_allowed:
        w._death_red_text_prev = ""
    _death_red_new = (
        _death_red_allowed
        and b30["red_str"] != getattr(w, "_death_red_text_prev", "")
    )
    # fg(+0xA844) がダイアログ本文バッファ(0x7979)を指す = そのダイアログメッセージが
    # 現在画面表示中。変化時(red_changed)の 1 回 push だけだと、他経路(active_template
    # の古い候補等)が後から上書きした際に翻訳が消える。画面表示中は
    # 「翻訳できた本文に限り」毎poll再アサートして維持する (辞書未登録は push せず、
    # active_template/gold_drop 等の既存経路や表示を一切壊さない)。
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
        _fg_ptr = _fg_raw[0] | (_fg_raw[1] << 8)
        try:
            from active_template_reader import (
                is_runtime_message_buffer_pointer,
            )
            _dlg_on_screen = is_runtime_message_buffer_pointer(_fg_ptr)
        except Exception:  # noqa: BLE001
            _dlg_on_screen = (0x7979 <= _fg_ptr < 0x7979 + 68)
    except (OSError, AttributeError):
        _dlg_on_screen = False
    _axis = b30.get("c1_dialog_axis")
    _c1_red_axis_active = bool(
        _axis
        and _axis.active
        and (
            _axis.a845 == 0x79
            or (
                _axis.current_ptr is not None
                and 0x7979 <= _axis.current_ptr < 0x7979 + 68
            )
        )
    )
    # 鍵取得 / 扉開けるダイアログメッセージは NPC会話 = False 専用。
    # npc_dialog 変化 poll での red 抑止は単一前景 classify_c1_dialog_substate が
    # c1_fg=c1_runtime_dialog を返すことで `_c1_fg_blocks_render` 経由に集約済
    # (旧 `not npc_dialog_changed` 防御ガードを撤去・走る主体の再配置=挙動保存)。
    if (not _c1_fg_blocks_render
            and _current_top_level(w) == "normal-play"
            and not w._npc_conversation_active
            and b30["in_gameplay"]
            and (b30["red_changed"] or _death_red_new or _dlg_on_screen
                 or _c1_red_axis_active)
            and b30["red_str"]):
        import dungeon_msg_lookup as _dml
        _b30_red_jpn = _dml.lookup(b30["red_str"])
        # dungeon_msg_lookup miss 時は npc_dialog テンプレ経路を試行
        # (鍵入手 / 扉解錠等は A232 / A233 テンプレで翻訳される)
        if not _b30_red_jpn:
            try:
                import npc_dialog_lookup as _ndl
                _ndl_result = _ndl.lookup(b30["red_str"])
                if _ndl_result is not None:
                    _ja_tmpl, _ph = _ndl_result
                    _b30_red_jpn = _ndl.format_japanese(_ja_tmpl, _ph)
            except Exception as exc:  # noqa: BLE001
                _log.debug("npc_dialog fallback failed: %s", exc)
        # 枠付きダイアログ (+0xA845 active) と枠なし赤文字を分類
        _red_owner = ("red_text_dialog" if b30["dialog_active"]
                      else "red_text")
        if b30["red_changed"] or _death_red_new:
            # 従来どおり: 変化時は未訳でも push (death / 未訳メッセージの原状維持)。
            w._ui_router.update_translation(
                _red_owner, b30["red_str"], _b30_red_jpn or "",
                speech_role="situation")
            w._dlg_keep_key = (b30["red_str"], _b30_red_jpn or "")
            _log.info("b30 red text accepted: %r → %r",
                      b30["red_str"], _b30_red_jpn)
        elif _b30_red_jpn:
            # 画面表示中の維持 (_dlg_on_screen 経由)。翻訳できた本文だけを毎poll
            # 再アサートし、他経路が古い候補で上書きしても翻訳を取り戻す。辞書未登録
            # (_b30_red_jpn が空) は push しない (= 既存表示/他経路を不破壊)。同一内容
            # かつ既に自 owner なら再 push を抑止 (flicker/ログ spam 抑止)。
            _keep = (b30["red_str"], _b30_red_jpn)
            if not (getattr(w, "_dlg_keep_key", None) == _keep
                    and w._ui_router.is_owner(_red_owner)):
                w._dlg_keep_key = _keep
                w._ui_router.update_translation(
                    _red_owner, b30["red_str"], _b30_red_jpn,
                    speech_role="situation")
        if _death_red_allowed:
            w._death_red_text_prev = b30["red_str"]
    elif b30["red_changed"] and b30["red_str"]:
        _reason = []
        if w._npc_conversation_active:
            _reason.append("npc-conversation-active")
        if not b30["in_gameplay"]:
            _reason.append("not-in-gameplay")
        if npc_dialog_changed:
            _reason.append("npc-dialog-changed")
        _log.info("b30 red text skipped (%s): %r",
                  ",".join(_reason) or "unknown", b30["red_str"])


def poll_dialog_close(w, *, b30: dict, npc_dialog_changed: bool,
                      instore_resp_handled: bool, c1_fg: str = "") -> None:
    """0xA845 ダイアログ close 検出 (非0 → 0)。

    C1 runtime dialog / gold drop / red_text owner の表示はこのタイミングで
    C1 runtime 軸の終了としてクリアする。施設や通常 NPC 会話の owner は
    ここでは扱わない。

    真1軸化: 「同 poll で新イベントが表示を奪うなら close clear しない」の判定を
    生イベントフラグ (red_changed/npc_dialog_changed) の再導出ではなく単一前景
    `c1_fg` で行う (C1 ダイアログ面が前景の poll はその面が所有=clear しない)。
    `instore_resp_handled` は C1 surface でない施設応答の cross-unit 信号のため
    別項として保持する。
    """
    def _owner_text_still_on_screen(owner: str) -> bool:
        try:
            _fg_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
            _fg_ptr = _fg_raw[0] | (_fg_raw[1] << 8)
        except (OSError, AttributeError):
            return False
        try:
            from active_template_reader import (
                is_response_text_buffer_pointer,
                is_runtime_message_buffer_pointer,
            )
            if owner in ("c1_runtime_dialog", "gold_drop"):
                return is_response_text_buffer_pointer(_fg_ptr)
            if owner == "red_text_dialog":
                return is_runtime_message_buffer_pointer(_fg_ptr)
        except Exception:  # noqa: BLE001
            if owner in ("c1_runtime_dialog", "gold_drop"):
                return any(start <= _fg_ptr < start + length
                           for start, length in (
                               (0x1044, 512),
                               (0x929E, 512),
                               (0x9A9E, 512),
                           ))
            if owner == "red_text_dialog":
                return 0x7979 <= _fg_ptr < 0x7979 + 68
        return False

    if (b30["in_gameplay"]
            and not w._npc_conversation_active
            and b30["dialog_active_prev"]
            and not b30["dialog_active"]):
        if c1_fg != "" or instore_resp_handled:
            _log.info(
                "b30 dialog close detected but C1 surface is foreground / "
                "instore resp this poll - skip clear (c1_fg=%r, "
                "instore_resp=%s, owner=%r)",
                c1_fg, instore_resp_handled, w._panel_owner)
        elif w._ui_router.current_owner() in (
                "c1_runtime_dialog", "gold_drop", "red_text_dialog"):
            _cur_owner = w._ui_router.current_owner()
            if _owner_text_still_on_screen(_cur_owner):
                _log.info(
                    "b30 dialog close detected but owner text still on "
                    "screen (owner=%s) - preserve display",
                    _cur_owner)
                return
            _log.info(
                "b30 dialog closed (0xA845 → 0x00, owner=%s) - clearing",
                _cur_owner)
            w._ui_router.clear_if_owner(_cur_owner)
        else:
            _log.info(
                "b30 dialog closed but owner=%r - preserve display",
                w._panel_owner)


__all__ = [
    "poll_trigger",
    "compute_b30_state",
    "poll_red_text",
    "poll_dialog_close",
    "restore_last_trigger_display",
    "classify_c1_dialog_substate",
]
