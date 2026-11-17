from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class FacilityView:
    l4_kind: str = 'none'
    render_owner: str = ''
    bar_key: str = ''
    l4_visible: bool = False
    message_source_owned: bool = False
    signals_snapshot: Any = None
    reason: str = 'seam'
    reply_kind: str = ''

class FacilityNode:
    name: str = '<facility>'
    menu_signatures: tuple = ()

    def __init__(self) -> None:
        self._parent: Any = None

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        return (shop_buy_active, shop_menu_visible)

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

    def suspend_for_story(self, w) -> None:
        return None

    def latch(self, w) -> tuple[bool, bool]:
        name = getattr(w, '_facility_latch_name', '') or ''
        started = getattr(w, '_facility_latch_started', '') or ''
        return (name == self.name, started == self.name)

    def poll_reply_unit(self, w, *, shop_state, entry_handled: bool, img_name: str, shop_menu_visible: bool, area: str='') -> tuple[bool, bool]:
        return (False, False)
    owns_shop_replies: bool = False
    has_conversation_session: bool = False
    panel_owners: frozenset = frozenset()
    story_kind: str = ''
    story_owner: str = ''
    outside_conversation_owners: frozenset = frozenset()

    def after_l3(self, w, *, img_name: str) -> None:
        return None

    def run_render_stage(self, w, *, shop_state, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, foreground_ptr, top_level_state: str):
        view = self.session_view(w, shop_state=shop_state, shop_img_name=shop_img_name, foreground_ptr=foreground_ptr)
        session_up = view is not None
        story = self.story_of(w, ptr=foreground_ptr, view=view)
        w._facility_story_kind_now = story
        w._facility_story_owner_now = self.story_owner if story else ''
        w._facility_story_ptr_now = foreground_ptr
        self.prepare_render(w)
        negot = tmpl = front = False
        if story:
            if session_up:
                self.suspend_for_story(w)
            front = True
        elif session_up:
            negot, tmpl, shop_menu_visible, shop_buy_active = self.render(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state)
            front = True
        else:
            shop_buy_active, shop_menu_visible = self.render_no_session_shop(w, shop_state=shop_state, shop_img_name=shop_img_name, shop_buy_active=shop_buy_active, shop_menu_visible=shop_menu_visible)
        return (story, session_up, negot, tmpl, shop_menu_visible, shop_buy_active, front)

    def poll_units_outside_conversation(self, w, *, outside: bool, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, area: str, top_level_state: str):
        if not outside:
            return (False, False)
        from normal_play.active_template_module import poll_template_outside_conversation
        return (False, poll_template_outside_conversation(w, shop_img_name=shop_img_name, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, area=area))

    def own_shop_state(self, w, *, area, in_interior: bool, interior_mif_name: str, top_level_state: str, img_name: str, screen_id, yesno_candidate_pointers: tuple):
        return None

    def bar_sub_label_key(self, w, *, active_session_name: str, screen_suppresses_conversation_label: bool, img_name: str) -> str:
        return ''

    def poll_own_session(self, w, ctx) -> None:
        return None

    def observe(self, w, *, shop_state, shop_img_name: str, in_interior: bool) -> None:
        return None

    def after_latch(self, w, *, img_name: str) -> None:
        return None

    def session_view(self, w, *, shop_state, shop_img_name: str, foreground_ptr):
        if not self.latch(w)[0]:
            return None
        return self.classify_view(w, shop_state=shop_state, shop_img_name=shop_img_name, foreground_ptr=foreground_ptr)

    def story_of(self, w, *, ptr, view) -> str:
        return ''

    def poll_story(self, w, *, active: bool, foreground_ptr=None) -> bool:
        return False

    def prepare_render(self, w) -> None:
        return None

    def on_l3_exit(self, w) -> None:
        self.poll_story(w, active=False)
        self.render_no_session_shop(w, shop_state=None, shop_img_name='', shop_buy_active=False, shop_menu_visible=False)

    def finish_exit_in_render_stage(self, w, *, outside: bool) -> bool:
        return True

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
    from hierarchy_state import register_conversation_panel_owners, register_facility_l4_panel_owners
    register_conversation_panel_owners(frozenset(node.panel_owners) | frozenset(node.outside_conversation_owners))
    if node.has_conversation_session:
        register_facility_l4_panel_owners(node.panel_owners)

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

def declared_template_groups() -> list[tuple]:
    return [tuple(getattr(node, 'template_declarations', ())) for node in _REGISTRY.values()]
__all__ = ['FacilityNode', 'FacilityView', 'SeamFacilityNode', 'register_facility_node', 'get_facility_node', 'registered_facility_names', 'build_menu_signature_table', 'declared_template_groups']
