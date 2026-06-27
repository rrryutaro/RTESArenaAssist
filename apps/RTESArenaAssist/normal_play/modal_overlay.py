from __future__ import annotations
MODAL_NONE = 'none'
_SCREEN_ID_TO_MODAL = {'logbook': 'journal', 'system_menu': 'system_menu', 'automap': 'automap'}

def classify_modal_overlay(screen_id_stable: str) -> str:
    return _SCREEN_ID_TO_MODAL.get(screen_id_stable or '', MODAL_NONE)
__all__ = ['MODAL_NONE', 'classify_modal_overlay']
