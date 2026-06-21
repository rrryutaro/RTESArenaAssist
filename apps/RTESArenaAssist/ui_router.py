from __future__ import annotations

from dataclasses import replace
import logging
from typing import Optional

import assist_settings as settings
import i18n_helper as i18n
from assist_log import recog as _recog
from display_intent import DisplayIntent, PollFrame
from hierarchy_state import (
    active_facility_session_name,
    facility_owners_for_session,
    CONVERSATION_PANEL_OWNERS,
)
from panel_mode_resolver import resolve_flush_mode

_log = logging.getLogger("RTESArenaAssist")

_CONVERSATION_TAB_OWNERS = CONVERSATION_PANEL_OWNERS

class UiRouter:
    def __init__(self, window) -> None:
        self._window = window
        self._poll_frame: Optional[PollFrame] = None
        self._pending_display: Optional[DisplayIntent] = None
        self._pending_order = 0
        self._pending_display_order = 0
        self._translation_observer = None
        self._obs_last_key = None

    def set_translation_observer(self, callback) -> None:
        self._translation_observer = callback

    def begin_poll_frame(self, frame: PollFrame) -> None:
        self._poll_frame = frame
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0

    def propose_display(self, intent: DisplayIntent) -> None:
        if self._poll_frame is None:
            self.apply_display(intent)
            self._apply_flush_panel_mode(intent)
            return
        resolved = self._resolve_proposed_intent(intent)
        if resolved is None:
            return
        self._pending_order += 1
        current = self._pending_display
        merged = self._merge_compatible_intents(current, resolved)
        if merged is not None:
            self._pending_display = merged
            self._pending_display_order = self._pending_order
            self._apply_logical_display(merged)
            return
        if (current is None or
                (resolved.priority, self._pending_order) >=
                (current.priority, self._pending_display_order)):
            self._pending_display = resolved
            self._pending_display_order = self._pending_order
            self._apply_logical_display(resolved)

    def _merge_compatible_intents(
            self,
            current: Optional[DisplayIntent],
            resolved: DisplayIntent) -> Optional[DisplayIntent]:
        if current is None or current.priority != resolved.priority:
            return None
        if current.kind == "panel_mode" and resolved.kind == "translation":
            if (current.mode is not None
                    and (resolved.mode is None
                         or resolved.mode == current.mode)):
                return replace(resolved, mode=current.mode)
        if current.kind == "translation" and resolved.kind == "panel_mode":
            if (resolved.mode is not None
                    and (current.mode is None
                         or current.mode == resolved.mode)):
                return replace(current, mode=resolved.mode)
        if current.kind == "translation" and resolved.kind == "translation":
            if (current.mode is not None
                    and (resolved.mode is None
                         or resolved.mode == current.mode)):
                return replace(resolved, mode=current.mode)
        return None

    def pending_display(self) -> Optional[DisplayIntent]:
        return self._pending_display

    def flush_poll_display(self) -> None:
        intent = self._pending_display
        frame = self._poll_frame
        self._poll_frame = None
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0
        if intent is not None:
            self.apply_display(intent)
        self._apply_flush_panel_mode(intent)
        self._log_flush_winner(intent, frame)
        self._log_facility_display_invariant(frame)

    def _winner_has_content(self, intent: Optional[DisplayIntent]) -> bool:
        if intent is None or intent.kind != "translation":
            return False
        en = (intent.en or "").strip()
        try:
            nd = i18n.tr("translate.no_data")
        except Exception:  # noqa: BLE001
            nd = ""
        return bool(en) and en not in ("—", nd)

    def _apply_flush_panel_mode(self, intent: Optional[DisplayIntent]) -> None:
        if intent is None or intent.kind == "release_if_owner":
            return
        w = self._window
        tab = getattr(w, "_tab_translate", None)
        if tab is None:
            return
        try:
            cur = tab.panel_mode()
        except AttributeError:
            return
        winner_mode = intent.mode if intent.mode is not None else cur
        is_tab_owner = bool(
            intent.kind == "translation"
            and (intent.panel_owner or "") in _CONVERSATION_TAB_OWNERS)
        try:
            emulate = bool(settings.get(
                "translate_tab_emulate_panel_hidden", False))
            fb = settings.get("translate_fallback_screen", "map")
        except Exception:  # noqa: BLE001
            emulate, fb = False, "map"
        target = resolve_flush_mode(
            winner_mode=winner_mode,
            top_level=getattr(w, "_top_level_state", "pregame"),
            emulate=emulate,
            winner_has_content=self._winner_has_content(intent),
            winner_is_tab_owner=is_tab_owner,
            fallback_setting=fb)
        if target is not None and target != cur:
            tab.set_panel_mode(target)

    def _log_flush_winner(self, intent: Optional[DisplayIntent],
                          frame: Optional[PollFrame]) -> None:
        if intent is None:
            key = ("<none>", "", "", 0)
        else:
            key = (intent.kind, intent.panel_owner or "",
                   intent.mode or "", intent.priority)
        prev = getattr(self, "_winner_key", None)
        if key == prev:
            return
        self._winner_key = key
        def _idle(k) -> bool:
            return k is not None and k[0] in ("<none>", "clear") and not k[1]
        if _idle(key) and _idle(prev):
            return
        try:
            tab_mode = self._window._tab_translate.panel_mode()
        except (AttributeError, RuntimeError):
            tab_mode = "?"
        _recog(
            _log,
            "flush winner: kind=%s owner=%r mode=%r prio=%d tab_mode=%r "
            "owner_now=%r reason=%r",
            key[0], key[1], key[2], key[3], tab_mode,
            self.current_owner(),
            (intent.reason if intent is not None else ""))

    def _resolve_proposed_intent(
            self, intent: DisplayIntent) -> Optional[DisplayIntent]:
        current = self.current_owner()
        if (intent.allowed_current_owners is not None
                and current not in intent.allowed_current_owners):
            _log.debug(
                "ui_router.propose_display skipped "
                "(kind=%s owner=%r current=%r allowed=%r)",
                intent.kind, intent.panel_owner, current,
                intent.allowed_current_owners)
            return None
        if intent.allowed_current_owners is not None:
            intent = replace(intent, allowed_current_owners=None)
        if intent.kind == "clear":
            return intent
        if intent.kind == "clear_if_owner":
            if current != intent.panel_owner:
                return None
            return DisplayIntent.clear(
                "",
                mode=intent.mode,
                clear_place_list=intent.clear_place_list,
                priority=intent.priority,
                reason=intent.reason,
            )
        if intent.kind == "release_if_owner":
            if current != intent.panel_owner:
                return None
            return DisplayIntent.claim_owner(
                "",
                priority=intent.priority,
                reason=intent.reason,
            )
        return intent

    def _apply_logical_display(self, intent: DisplayIntent) -> None:
        if intent.kind == "translation":
            if not intent.keep_owner:
                self._window._panel_owner = intent.panel_owner
            return
        if intent.kind in (
            "clear",
            "claim_owner",
            "shop_buy_list",
            "facility_list",
            "item_pickup_list",
            "load_screen_slots",
            "equipment_list",
            "spell_detail",
            "place_list",
        ):
            self._window._panel_owner = intent.panel_owner

    def update_translation(self, panel_owner: str, en: str, ja: str,
                           *, mode: Optional[str] = "translate",
                           panel_en: Optional[str] = None,
                           panel_ja: Optional[str] = None,
                           update_panel: bool = True,
                           update_tab: bool = True,
                           keep_owner: bool = False,
                           priority: int = 0,
                           reason: str = "",
                           speech_role: Optional[str] = None,
                           speech_text: Optional[str] = None) -> None:
        self.propose_display(DisplayIntent.translation(
            panel_owner, en, ja, mode=mode,
            panel_en=panel_en, panel_ja=panel_ja,
            update_panel=update_panel, update_tab=update_tab,
            keep_owner=keep_owner,
            priority=priority, reason=reason,
            speech_role=speech_role, speech_text=speech_text))

    def propose_translation(self, panel_owner: str, en: str, ja: str,
                            *, mode: Optional[str] = "translate",
                            panel_en: Optional[str] = None,
                            panel_ja: Optional[str] = None,
                            update_panel: bool = True,
                            update_tab: bool = True,
                            keep_owner: bool = False,
                            priority: int = 0,
                            reason: str = "",
                            speech_role: Optional[str] = None,
                            speech_text: Optional[str] = None) -> None:
        self.propose_display(DisplayIntent.translation(
            panel_owner, en, ja, mode=mode,
            panel_en=panel_en, panel_ja=panel_ja,
            update_panel=update_panel, update_tab=update_tab,
            keep_owner=keep_owner,
            priority=priority,
            reason=reason,
            speech_role=speech_role, speech_text=speech_text))

    def apply_display(self, intent: DisplayIntent) -> None:
        if intent.allowed_current_owners is not None:
            current = self.current_owner()
            if current not in intent.allowed_current_owners:
                _log.debug(
                    "ui_router.apply_display skipped "
                    "(kind=%s owner=%r current=%r allowed=%r)",
                    intent.kind, intent.panel_owner, current,
                    intent.allowed_current_owners)
                return
        w = self._window

        if intent.kind == "translation":
            self._apply_translation(intent)
            return

        if intent.kind == "clear":
            w._tab_translate.update_translation("", "", suppress_fallback=True)
            if intent.clear_place_list:
                try:
                    w._tab_translate.update_place_list([])
                except AttributeError:
                    pass
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "clear_if_owner":
            current = self.current_owner()
            if current != intent.panel_owner:
                return
            w._tab_translate.update_translation("", "", suppress_fallback=True)
            if intent.clear_place_list:
                try:
                    w._tab_translate.update_place_list([])
                except AttributeError:
                    pass
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = ""
            return

        if intent.kind == "release_if_owner":
            if self.current_owner() == intent.panel_owner:
                w._panel_owner = ""
            return

        if intent.kind == "claim_owner":
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "panel_mode":
            return

        if intent.kind == "shop_buy_list":
            w._tab_translate.update_shop_buy_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "facility_list":
            try:
                w._tab_translate.set_facility_list_title(
                    intent.panel_ja or intent.panel_en or "")
            except AttributeError:
                pass
            w._tab_translate.update_facility_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "item_pickup_list":
            w._tab_translate.update_item_pickup_list(
                intent.items, intent.remaining or 0)
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "load_screen_slots":
            w._tab_translate.update_load_screen_slots(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "equipment_list":
            w._tab_translate.set_equipment_panel_title(intent.title)
            w._tab_translate.update_equipment_list(intent.items)
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "spell_detail":
            w._tab_translate.update_spell_detail(intent.items)
            if (w._layout_translate_panel is not None
                    and (intent.panel_en or intent.panel_ja)):
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "place_list":
            w._tab_translate.set_place_list_title(intent.title)
            w._tab_translate.update_place_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        raise ValueError(f"unknown display intent kind: {intent.kind!r}")

    def _apply_translation(self, intent: DisplayIntent) -> None:
        w = self._window
        _prev_key = getattr(self, "_applied_prev_key", None)
        _mode = intent.mode
        _mode_key = _mode if _mode is not None else "<keep>"
        _now_key = (intent.panel_owner, _mode_key, intent.en[:160], intent.ja[:160])
        if _prev_key != _now_key:
            self._applied_prev_key = _now_key
            _recog(
                _log,
                "panel applied: owner=%r mode=%r en=%r ja=%r",
                intent.panel_owner, _mode_key,
                intent.en[:120], intent.ja[:120])
        if intent.update_tab:
            w._tab_translate.update_translation(
                intent.en, intent.ja, suppress_fallback=True)
        if intent.update_panel and w._layout_translate_panel is not None:
            _pen = intent.panel_en if intent.panel_en is not None else intent.en
            _pja = intent.panel_ja if intent.panel_ja is not None else intent.ja
            w._layout_translate_panel.update_translation(_pen, _pja)
        if not intent.keep_owner:
            w._panel_owner = intent.panel_owner

        if self._translation_observer is not None:
            _obs_en = intent.en or (intent.panel_en or "")
            _obs_ja = intent.ja or (intent.panel_ja or "")
            _obs_owner = intent.panel_owner or self.current_owner()
            _obs_key = (_obs_owner, _obs_en, _obs_ja)
            if self._obs_last_key != _obs_key:
                self._obs_last_key = _obs_key
                try:
                    self._translation_observer(
                        _obs_owner, _obs_en, _obs_ja,
                        intent.speech_role, intent.speech_text)
                except Exception:  # noqa: BLE001
                    _log.exception("translation_observer failed")

    def _log_facility_display_invariant(
            self, frame: Optional[PollFrame]) -> None:
        w = self._window
        session_name = active_facility_session_name(w)
        if not session_name:
            return
        owner = self.current_owner()
        if owner and owner in facility_owners_for_session(session_name):
            return
        key = (
            session_name, owner,
            getattr(w, "_screen_id_prev", None),
            getattr(w, "_img_name_prev", "") or "",
            frame.top_level if frame is not None else "",
        )
        if key == getattr(self, "_facility_empty_owner_key", None):
            return
        self._facility_empty_owner_key = key
        _log.warning(
            "facility display invariant warning: active L3 session L4 owner "
            "is %s (session=%s screen=%r img=%r frame_top=%r)",
            ("empty" if not owner else f"non-facility {owner!r}"),
            session_name, getattr(w, "_screen_id_prev", None),
            getattr(w, "_img_name_prev", "") or "",
            frame.top_level if frame is not None else "")

    def current_owner(self) -> str:
        return getattr(self._window, "_panel_owner", "") or ""

    def is_owner(self, panel_owner: str) -> bool:
        return self.current_owner() == panel_owner

    def clear_if_owner(self, panel_owner: str,
                       *, mode: Optional[str] = None,
                       clear_place_list: bool = False) -> None:
        self.propose_display(
            DisplayIntent.clear_if_owner(
                panel_owner, mode=mode,
                clear_place_list=clear_place_list))

    def clear_display(self, panel_owner: str = "",
                      *, mode: Optional[str] = "translate",
                      clear_place_list: bool = False,
                      allowed_current_owners:
                          Optional[tuple] = None) -> None:
        self.propose_display(
            DisplayIntent.clear(
                panel_owner, mode=mode,
                clear_place_list=clear_place_list,
                allowed_current_owners=allowed_current_owners))

    def update_panel_translation(self, panel_en: str, panel_ja: str,
                                 *, speech_role: Optional[str] = None,
                                 speech_text: Optional[str] = None,
                                 priority: int = 0) -> None:
        self.propose_display(
            DisplayIntent.panel_translation(
                panel_en, panel_ja, priority=priority,
                speech_role=speech_role, speech_text=speech_text))

    def release_if_owner(self, panel_owner: str) -> None:
        self.propose_display(DisplayIntent.release_if_owner(panel_owner))

    def claim_owner(self, panel_owner: str,
                    *, mode: Optional[str] = None) -> None:
        self.propose_display(
            DisplayIntent.claim_owner(panel_owner, mode=mode))

    def set_panel_mode(self, mode: str, *, priority: int = 0,
                       reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.panel_mode(mode, priority=priority, reason=reason))

    def update_shop_buy_list(self, panel_owner: str, items: list,
                             panel_en: str, panel_ja: str) -> None:
        self.propose_display(
            DisplayIntent.shop_buy_list(panel_owner, items, panel_en, panel_ja))

    def update_facility_list(self, panel_owner: str, items: list,
                             panel_en: str, panel_ja: str,
                             *, priority: int = 0,
                             reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.facility_list(
                panel_owner, items, panel_en, panel_ja,
                priority=priority, reason=reason))

    def update_item_pickup_list(self, panel_owner: str, items: list,
                                remaining: int) -> None:
        self.propose_display(
            DisplayIntent.item_pickup_list(panel_owner, items, remaining))

    def update_load_screen_slots(self, panel_owner: str,
                                 slot_data: list) -> None:
        self.propose_display(
            DisplayIntent.load_screen_slots(panel_owner, slot_data))

    def propose_load_screen_slots(self, panel_owner: str,
                                  slot_data: list,
                                  *, priority: int = 0,
                                  reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.load_screen_slots(
                panel_owner, slot_data,
                priority=priority, reason=reason))

    def update_equipment_list(self, panel_owner: str, title: str,
                              items: list) -> None:
        self.propose_display(
            DisplayIntent.equipment_list(panel_owner, title, items))

    def propose_equipment_list(self, panel_owner: str, title: str,
                               items: list,
                               *, priority: int = 0,
                               reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.equipment_list(
                panel_owner, title, items,
                priority=priority, reason=reason))

    def update_spell_detail(self, panel_owner: str, data: dict,
                            *, panel_en: str = "",
                            panel_ja: str = "") -> None:
        self.propose_display(DisplayIntent.spell_detail(
            panel_owner, data, panel_en=panel_en, panel_ja=panel_ja))

    def propose_spell_detail(self, panel_owner: str, data: dict,
                             *, panel_en: str = "", panel_ja: str = "",
                             priority: int = 0,
                             reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.spell_detail(
                panel_owner, data, panel_en=panel_en, panel_ja=panel_ja,
                priority=priority, reason=reason))

    def update_place_list(self, panel_owner: str, items: list,
                          *, title: str = "", panel_en: str = "",
                          panel_ja: str = "") -> None:
        self.propose_display(DisplayIntent.place_list(
            panel_owner, items, title=title,
            panel_en=panel_en, panel_ja=panel_ja))


__all__ = ["UiRouter"]
