from __future__ import annotations

def _key(location_name: str, x: int, y: int) -> tuple[str, int, int] | None:
    try:
        location = str(location_name).strip()
        if not location:
            return None
        return (location, int(x), int(y))
    except (TypeError, ValueError):
        return None

class FacilityNameStore:

    def __init__(self) -> None:
        self._names: dict[tuple[str, int, int], str] = {}

    def name_for(self, location_name: str, x: int, y: int) -> str | None:
        key = _key(location_name, x, y)
        return self._names.get(key) if key is not None else None

    def note_name(self, location_name: str, x: int, y: int, display_name: str) -> bool:
        key = _key(location_name, x, y)
        name = str(display_name or '').strip()
        if key is None or not name or self._names.get(key) == name:
            return False
        self._names[key] = name
        return True

    def clear(self) -> None:
        self._names = {}
_SHARED: FacilityNameStore | None = None

def get_store() -> FacilityNameStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = FacilityNameStore()
    return _SHARED
__all__ = ['FacilityNameStore', 'get_store']
