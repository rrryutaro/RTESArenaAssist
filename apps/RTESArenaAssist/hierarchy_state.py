from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


L1_TO_CODE_NAME = {
    "pregame": ("A", "起動中"),
    "chargen": ("B", "キャラクター作成中"),
    "normal-play": ("C", "通常ゲーム中"),
}

AREA_TO_BASE_KEY = {
    "dungeon": "dungeon",
    "city": "city",
    "wilderness": "wilderness",
}

BASE_KEY_TO_AREA = {
    "dungeon": "dungeon",
    "city": "city",
    "wilderness": "wilderness",
}

AREA_TO_C_CODE_NAME = {
    "dungeon": ("C1", "ダンジョン"),
    "city": ("C2", "街"),
    "wilderness": ("C3", "フィールド"),
}

CONVERSATION_SESSION_NAMES = frozenset({
    "npc_chat",
    "tavern",
    "temple",
    "equipment",
    "mages_guild",
})

FACILITY_CONVERSATION_SESSION_NAMES = frozenset({
    "tavern",
    "temple",
    "equipment",
    "mages_guild",
})

CONVERSATION_PANEL_OWNERS = frozenset({
    "npc_dialog",
    "npc_conversation",
    "npc_message",
    "active_template",
    "temple_active_template",
    "temple_menu",
    "temple_cost",
    "temple_prompt",
    "temple_priest_reply",
    "negotiation",
    "tavern_yesno",
    "tavern_rumor_type",
    "tavern_negotiation",
    "shop_menu",
    "shop_rumor_type",
    "shop_buy",
    "shop_rooms",
    "equipment_menu",
    "equipment_list",
    "equipment_negotiation",
    "equipment_reply",
    "mages_menu",
    "mages_list",
    "mages_spellmaker",
    "mages_effect_menu",
    "mages_spelldetail",
    "mages_prompt",
    "mages_confirm",
    "mages_negotiation",
    "mages_reply",
})

_TAVERN_L4_MODULE_OWNERS = frozenset({
    "negotiation", "active_template", "npc_dialog",
})
FACILITY_OWNER_SETS_BY_SESSION = {
    "tavern": frozenset({
        "shop_menu", "shop_rumor_type", "shop_buy", "shop_rooms",
        "tavern_yesno", "tavern_rumor_type", "tavern_negotiation",
    }) | _TAVERN_L4_MODULE_OWNERS,
    "temple": frozenset({
        "temple_menu", "temple_active_template",
        "temple_priest_reply",
        "temple_cost", "temple_prompt",
    }),
    "equipment": frozenset({
        "equipment_menu", "equipment_list",
        "equipment_negotiation",
        "equipment_reply",
    }),
    "mages_guild": frozenset({
        "mages_menu", "mages_list", "mages_spellmaker",
        "mages_effect_menu",
        "mages_spelldetail", "mages_prompt", "mages_confirm",
        "mages_negotiation",
        "mages_reply",
    }),
}

FACILITY_CONVERSATION_PANEL_OWNERS = frozenset().union(
    *FACILITY_OWNER_SETS_BY_SESSION.values())


def facility_owners_for_session(session_name: str) -> frozenset:
    return FACILITY_OWNER_SETS_BY_SESSION.get(session_name or "", frozenset())


def area_from_base_location_key(key: Optional[str]) -> str:
    return BASE_KEY_TO_AREA.get(key or "", "")


def base_location_key_from_area(area: Optional[str]) -> str:
    return AREA_TO_BASE_KEY.get(area or "", "")


def active_session_name(window, *, require_active: bool = True) -> str:
    try:
        session = window._session_manager.active_session()
    except (AttributeError, RuntimeError):
        return ""
    if session is None:
        return ""
    if require_active:
        try:
            if not session.is_active():
                return ""
        except AttributeError:
            pass
        except RuntimeError:
            return ""
    return getattr(session, "name", "") if session is not None else ""


def active_facility_session_name(window, *, require_active: bool = True) -> str:
    name = active_session_name(window, require_active=require_active)
    return name if name in FACILITY_CONVERSATION_SESSION_NAMES else ""


def is_facility_conversation_owner(owner: str) -> bool:
    return (owner or "") in FACILITY_CONVERSATION_PANEL_OWNERS


def _base_location_key_from_window(window) -> str:
    return base_location_key_from_area(
        getattr(window, "_last_non_interior_area", "") or "")


@dataclass(frozen=True)
class SeparationHierarchy:

    l1_state: str = "pregame"
    l1_code: str = "A"
    l1_name: str = "起動中"
    l2_code: str = ""
    l2_name: str = ""
    l3_code: str = ""
    l3_name: str = ""
    l4_code: str = ""
    l4_name: str = ""

    @classmethod
    def from_parts(
        cls,
        *,
        top_level_state: str = "pregame",
        c_area: Optional[str] = None,
        base_location_key: Optional[str] = None,
        in_interior: bool = False,
        npc_active: bool = False,
    ) -> "SeparationHierarchy":
        l1_code, l1_name = L1_TO_CODE_NAME.get(
            top_level_state, ("", top_level_state or ""))
        if top_level_state != "normal-play":
            return cls(
                l1_state=top_level_state,
                l1_code=l1_code,
                l1_name=l1_name,
            )

        area = c_area or area_from_base_location_key(base_location_key)
        if in_interior and not area:
            area = "city"
        l2_code, l2_name = AREA_TO_C_CODE_NAME.get(area or "", ("", ""))
        l3_code = l3_name = l4_code = l4_name = ""
        if in_interior and l2_code in ("C2", "C3"):
            l3_code = "L3"
            l3_name = "店内"
            if npc_active:
                l4_code = "L4"
                l4_name = "NPC会話系"
        elif npc_active and l2_code in ("C2", "C3"):
            l3_code = "L3"
            l3_name = "NPC会話系"

        return cls(
            l1_state=top_level_state,
            l1_code=l1_code,
            l1_name=l1_name,
            l2_code=l2_code,
            l2_name=l2_name,
            l3_code=l3_code,
            l3_name=l3_name,
            l4_code=l4_code,
            l4_name=l4_name,
        )

    @classmethod
    def from_window(
        cls,
        window,
        *,
        top_level_state: Optional[str] = None,
        in_interior: Optional[bool] = None,
        npc_active: Optional[bool] = None,
        c_area: Optional[str] = None,
        base_location_key: Optional[str] = None,
    ) -> "SeparationHierarchy":
        top = (top_level_state if top_level_state is not None
               else getattr(window, "_top_level_state", "pregame"))
        interior = bool(
            in_interior if in_interior is not None
            else getattr(window, "_in_interior", False))
        if npc_active is None:
            session_name = active_session_name(window)
            npc_active = (
                bool(getattr(window, "_npc_conversation_active", False))
                or session_name in CONVERSATION_SESSION_NAMES
            )
        key = (base_location_key if base_location_key is not None
               else _base_location_key_from_window(window))
        return cls.from_parts(
            top_level_state=top,
            c_area=c_area,
            base_location_key=key,
            in_interior=interior,
            npc_active=bool(npc_active),
        )

    @property
    def indicator(self) -> str:
        code = self.l2_code or self.l1_code
        return f"[{code}]" if code else ""

    @property
    def path_codes(self) -> tuple[str, ...]:
        return tuple(
            code for code in (
                self.l1_code, self.l2_code, self.l3_code, self.l4_code)
            if code)

    @property
    def path_names(self) -> tuple[str, ...]:
        return tuple(
            name for name in (
                self.l1_name, self.l2_name, self.l3_name, self.l4_name)
            if name)


@dataclass(frozen=True)
class HierarchyRecognitionInput:

    top_level_state: str = "pregame"
    c_area: str = ""
    in_interior: bool = False
    npc_active: bool = False
    npc_phase: Optional[int] = None
    mif_name: str = ""
    img_name: str = ""
    screen_id: Optional[str] = None
    panel_owner: str = ""
    active_session: str = ""
    interior_mif_name: str = ""
    interior_raw: Optional[int] = None

    def transition_key(
            self,
            hierarchy: SeparationHierarchy) -> tuple[tuple[str, ...],
                                                     tuple[str, ...]]:
        return hierarchy.path_codes, hierarchy.path_names

    def anomaly_key(self) -> tuple:
        if (self.top_level_state == "normal-play"
                and self.c_area == "dungeon"
                and self.in_interior):
            return (
                "dungeon_interior_rejected",
                self.top_level_state,
                self.c_area,
                self.mif_name,
                self.img_name,
                self.screen_id,
            )
        if self.top_level_state == "normal-play" and not self.c_area:
            return (
                "normal_play_area_unknown",
                self.top_level_state,
                self.mif_name,
                self.img_name,
                self.screen_id,
            )
        return ()

    def anomaly_kind(self) -> str:
        key = self.anomaly_key()
        return key[0] if key else ""

    def values_for_log(self) -> dict:
        return {
            "top": self.top_level_state,
            "area": self.c_area or "",
            "interior": self.in_interior,
            "npc_active": self.npc_active,
            "npc_phase": self.npc_phase,
            "mif": self.mif_name or "",
            "img": self.img_name or "",
            "screen": self.screen_id or "",
            "owner": self.panel_owner or "",
            "session": self.active_session or "",
            "interior_mif": self.interior_mif_name or "",
            "interior_raw": self.interior_raw,
        }


__all__ = [
    "AREA_TO_C_CODE_NAME",
    "BASE_KEY_TO_AREA",
    "CONVERSATION_PANEL_OWNERS",
    "CONVERSATION_SESSION_NAMES",
    "FACILITY_CONVERSATION_PANEL_OWNERS",
    "FACILITY_CONVERSATION_SESSION_NAMES",
    "FACILITY_OWNER_SETS_BY_SESSION",
    "facility_owners_for_session",
    "HierarchyRecognitionInput",
    "L1_TO_CODE_NAME",
    "SeparationHierarchy",
    "active_facility_session_name",
    "active_session_name",
    "area_from_base_location_key",
    "base_location_key_from_area",
    "is_facility_conversation_owner",
]
