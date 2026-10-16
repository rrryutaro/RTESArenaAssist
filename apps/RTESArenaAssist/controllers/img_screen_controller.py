import logging
import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from top_level import pregame_render as _pregame_render
from normal_play import char_screen_module as _char_screen
from normal_play import npc_conversation_module as _npc_conversation
from ui_router import SCREEN_CHANGE_CLEAR_PRIORITY
from screen_img_signals import EQUIP_TOGGLE_IMGS, LOADSAVE_IMG, MAIN_MENU_IMG, MRSHIRT_IMG, NPC_POPUP_IMG, PARCHMENT_IMG, TITLE_INTRO_IMGS, is_newgame_intro_img, is_spell_detail_img
_log = logging.getLogger('img_screen_controller')

class ImgScreenController:

    def __init__(self, window):
        self._w = window

    def _set_panel_mode(self, mode: str) -> None:
        self._w._ui_router.set_panel_mode(mode)

    def on_img_name_changed(self, img_name: str) -> None:
        _log.info('img_name changed: %r', img_name)
        img_upper = (img_name or '').upper()
        top = _current_top_level(self._w)
        prev_screen = getattr(self._w, '_screen_id_prev', None)
        from top_level.top_level_node import classify_top_level
        _l1_next, _ = classify_top_level(top, img_upper)
        if _l1_next == 'pregame' and top != 'pregame':
            try:
                via = 'system_menu' if prev_screen == 'system_menu' else top
                self._w._transition_top_level('pregame', f'{via} → {img_upper}')
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass
        elif _l1_next == 'chargen' and top == 'pregame':
            try:
                self._w._transition_top_level('chargen', 'EVLINTRO.XMI')
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass
        if img_upper == LOADSAVE_IMG and _current_top_level(self._w) == 'pregame':
            try:
                self._w._pregame_loadsave_seen = True
            except AttributeError:
                pass
        if img_upper.endswith('.XMI'):
            if _current_top_level(self._w) == 'chargen':
                self._w._chargen_opening_text_prev = ''
            try:
                self._w._ui_router.clear_display('', priority=SCREEN_CHANGE_CLEAR_PRIORITY)
            except AttributeError:
                pass
            return
        if img_name == MAIN_MENU_IMG:
            self._show_menu_screen()
        elif img_name == LOADSAVE_IMG:
            self._show_load_screen()
        elif is_newgame_intro_img(img_name):
            self._show_newgame_slide(img_name)
        elif img_name == PARCHMENT_IMG:
            self._w._set_chargen_ui_state(True)
        elif img_name in TITLE_INTRO_IMGS:
            self._show_startup_intro(img_name)
        elif img_name == MRSHIRT_IMG:
            return
        elif img_name in EQUIP_TOGGLE_IMGS:
            return
        elif img_name == NPC_POPUP_IMG:
            return
        elif is_spell_detail_img(img_name):
            return
        else:
            self._w._newgame_layout_pushed = False
            self._w._startup_layout_pushed = False
            try:
                self._w._ui_router.reset_panel_mode_if(('load_screen',))
            except AttributeError:
                pass
            self._w._set_chargen_ui_state(False)
    _NPC_DIALOG_RELATED_SCREENS = frozenset({'npc_dialog'})

    def on_screen_id_changed(self, screen_id: str) -> None:
        _log.info('screen_id changed: %r', screen_id)
        if _current_top_level(self._w) == 'normal-play' and screen_id not in self._NPC_DIALOG_RELATED_SCREENS:
            _npc_conversation.reset_npc_dialog_display(self._w, clear_display=False)
        _char_screen.on_screen_id_changed(self._w, screen_id)

    def _show_startup_intro(self, img_name: str) -> None:
        _pregame_render.show_startup_intro(self._w, img_name)

    def _show_menu_screen(self) -> None:
        _pregame_render.show_menu_screen(self._w)

    def _show_load_screen(self) -> None:
        _pregame_render.show_load_screen(self._w)

    def _show_newgame_slide(self, img_name: str) -> None:
        _pregame_render.show_newgame_slide(self._w, img_name)
