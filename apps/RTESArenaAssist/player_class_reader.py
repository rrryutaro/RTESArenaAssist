from __future__ import annotations
PLAYER_CLASS_NUMBER_OFFSET = 425
CLASS_INDEX_MASK = 31
CLASS_COUNT = 18

def class_index_of(class_number: int) -> int | None:
    index = int(class_number) & CLASS_INDEX_MASK
    return index if index < CLASS_COUNT else None

def read_class_index(analyzer, anchor: int) -> int | None:
    if analyzer is None:
        return None
    try:
        raw = analyzer.read_bytes(anchor + PLAYER_CLASS_NUMBER_OFFSET, 1)[0]
    except (OSError, AttributeError, IndexError):
        return None
    return class_index_of(raw)

def read_class_en(analyzer, anchor: int) -> str | None:
    index = read_class_index(analyzer, anchor)
    if index is None:
        return None
    return class_en_of(index)

def class_en_of(index: int) -> str | None:
    try:
        import arena_data
        entry = arena_data.get_class_by_id(int(index))
    except (ImportError, AttributeError):
        entry = None
    if entry and entry.get('en'):
        return entry['en']
    try:
        from experience_calc import class_en_from_id
    except ImportError:
        return None
    return class_en_from_id(int(index))
__all__ = ['PLAYER_CLASS_NUMBER_OFFSET', 'CLASS_INDEX_MASK', 'CLASS_COUNT', 'class_index_of', 'read_class_index', 'read_class_en', 'class_en_of']
