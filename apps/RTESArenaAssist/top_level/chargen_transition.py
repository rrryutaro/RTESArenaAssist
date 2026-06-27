from __future__ import annotations

def normal_play_entry_reason(*, top_level_state: str, mif_name: str, img_name: str, post_chargen_reached: bool, chargen_done: int) -> str:
    if top_level_state != 'chargen':
        return ''
    mif = (mif_name or '').strip()
    if not mif:
        return ''
    mif_lower = mif.lower()
    if mif_lower == 'start.mif' and post_chargen_reached:
        return 'start.mif in chargen (post-chargen)'
    return ''
__all__ = ['normal_play_entry_reason']
