from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class FacilityView:
    l4_kind: str = 'none'
    render_owner: str = ''
    bar_key: str = ''
    l4_visible: bool = False
    reason: str = 'seam'

class FacilityNode:
    name: str = '<facility>'
    menu_signatures: tuple = ()

    def __init__(self) -> None:
        self._parent: Any = None

    def set_parent(self, parent: Any) -> 'FacilityNode':
        self._parent = parent
        return self

    @property
    def parent(self) -> Any:
        return self._parent

    def exit_to_parent(self, w) -> Any:
        self.on_exit(w)
        return self._parent

    def owner_namespace(self) -> str:
        return self.name

    def classify_view(self, w, **signals) -> Any:
        raise NotImplementedError

    def render(self, w, *, view, **ctx):
        raise NotImplementedError

    def on_exit(self, w) -> None:
        return None

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} name={self.name!r}>'

class SeamFacilityNode(FacilityNode):

    def classify_view(self, w, **signals) -> FacilityView:
        return FacilityView(reason=f'seam:{self.name}')

    def render(self, w, *, view, **ctx):
        return (False, False, False, False)
_REGISTRY: Dict[str, FacilityNode] = {}

def register_facility_node(node: FacilityNode) -> None:
    _REGISTRY[node.name] = node

def get_facility_node(name: str) -> Optional[FacilityNode]:
    return _REGISTRY.get(name or '')

def registered_facility_names() -> list[str]:
    return sorted(_REGISTRY.keys())

def build_menu_signature_table() -> Dict[frozenset, tuple]:
    table: Dict[frozenset, tuple] = {}
    for node in _REGISTRY.values():
        for sig, kind, title in getattr(node, 'menu_signatures', ()):
            table[frozenset(sig)] = (kind, node.name, title)
    return table
__all__ = ['FacilityNode', 'FacilityView', 'SeamFacilityNode', 'register_facility_node', 'get_facility_node', 'registered_facility_names', 'build_menu_signature_table']
