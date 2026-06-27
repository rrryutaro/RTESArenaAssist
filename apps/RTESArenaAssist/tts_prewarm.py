from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')

def prewarm_dungeon_inf(w, inf_name: str) -> None:
    inf = (inf_name or '').upper()
    if not inf:
        return
    if inf == getattr(w, '_tts_prewarmed_inf', None):
        return
    w._tts_prewarmed_inf = inf
    tts = getattr(w, '_tts', None)
    if tts is None or not hasattr(tts, 'prewarm'):
        return
    try:
        import inf_text_lookup as itl
        texts: list[str] = []
        for entry in itl.all_entries_for_inf(inf):
            ja = itl.get_translation_display(entry)
            if isinstance(ja, str) and ja.strip():
                texts.append(ja)
        if texts:
            tts.prewarm(texts)
            _log.debug('tts prewarm: inf=%s texts=%d', inf, len(texts))
    except Exception:
        _log.debug('tts prewarm dungeon inf failed', exc_info=True)

def prewarm_fixed_sequence(w, texts, flag_attr: str) -> None:
    if getattr(w, flag_attr, False):
        return
    setattr(w, flag_attr, True)
    tts = getattr(w, '_tts', None)
    if tts is None or not hasattr(tts, 'prewarm'):
        return
    try:
        clean = [t for t in texts if isinstance(t, str) and t.strip()]
        if clean:
            tts.prewarm(clean)
            _log.debug('tts prewarm sequence: %s texts=%d', flag_attr, len(clean))
    except Exception:
        _log.debug('tts prewarm sequence failed', exc_info=True)

def reset_prewarm_state(w) -> None:
    for attr in ('_tts_prewarmed_inf', '_startup_intro_prewarmed', '_newgame_intro_prewarmed'):
        try:
            setattr(w, attr, None if attr == '_tts_prewarmed_inf' else False)
        except Exception:
            pass
__all__ = ['prewarm_dungeon_inf', 'prewarm_fixed_sequence', 'reset_prewarm_state']
