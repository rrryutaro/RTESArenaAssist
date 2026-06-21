"""分離階層 L1-L4 の読み取り専用モデル。

L1 は A/B/C のトップレベル状態、C 配下 L2 は C1/C2/C3 の基本居場所を
表す。親状態は表示所有者 (`panel_owner`) へ入れず、判定や接続バー表示の
入力として別管理する。
"""
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
    "equipment",     # 武具店会話セッション
    "mages_guild",   # 魔術師ギルド会話セッション
})

FACILITY_CONVERSATION_SESSION_NAMES = frozenset({
    "tavern",
    "temple",
    "equipment",     # 武具店 (L4 owner clear/dialog close 保護対象)
    "mages_guild",   # 魔術師ギルド (同上)
})

CONVERSATION_PANEL_OWNERS = frozenset({
    "npc_dialog",
    # V6 ②③ owner 分離: ②街中NPC会話/ASK ABOUT/道案内/NPC応答=npc_conversation、
    # ③一方向msg(状況/ダンジョンメッセージ/到着)=npc_message。npc_dialog と同じく
    # 会話パネル owner として扱う (behavior-preserving)。
    "npc_conversation",
    "npc_message",
    "active_template",
    "temple_active_template",
    "temple_menu",
    # 完全分離: 神殿の費用確認 / 寄付入力 / 神官応答の自施設 owner
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
    # 武具店 / 魔術師ギルドの自施設 L4 owner 名前空間 (完全分離)
    "equipment_menu",
    "equipment_list",
    "equipment_negotiation",
    # 完全分離(内製化): 武具店店主応答は武具店専用 owner (共有 npc_dialog から撤廃)
    "equipment_reply",
    "mages_menu",
    "mages_list",
    "mages_spellmaker",
    "mages_effect_menu",
    "mages_spelldetail",
    "mages_prompt",
    "mages_confirm",
    "mages_negotiation",
    # 完全分離(内製化): ギルド応答はギルド専用 owner (共有 npc_dialog から撤廃)
    "mages_reply",
})

# 完全分離: active な施設 session ごとに「保護してよい L4 owner」を限定する。
# 全 facility owner を一括で見ると、equipment active 中に宿屋 shop_menu を保護する等
# 施設横断の干渉が起きるため、session 名ごとに自施設 owner のみを許可する。
#
# negotiation / active_template / npc_dialog は宿屋由来の汎用 L4 module
# owner。神殿/武具店/ギルドはこれらへの相乗りを撤廃し各施設専用 owner を内製化済み
# のため、本集合から除去した。これらの owner は現在 **宿屋専用** (= 他施設は参照
# しない) であり、宿屋の集合にのみ残す。
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
        # 完全分離(内製化済み): 神官応答 / 費用確認 / 寄付入力は神殿専用 owner
        "temple_priest_reply",
        "temple_cost", "temple_prompt",
    }),
    "equipment": frozenset({
        "equipment_menu", "equipment_list",
        "equipment_negotiation",
        # 完全分離(内製化済み): 店主応答は武具店専用 owner
        "equipment_reply",
    }),
    "mages_guild": frozenset({
        "mages_menu", "mages_list", "mages_spellmaker",
        "mages_effect_menu",
        # 呪文購入詳細(spell_detail) / 入力・見積りプロンプト / 確認ダイアログ /
        # 価格交渉も ギルド分離内の L4 描画 owner。施設 owner として保護対象に含める。
        "mages_spelldetail", "mages_prompt", "mages_confirm",
        "mages_negotiation",
        # 完全分離(内製化済み): 応答はギルド専用 owner
        "mages_reply",
    }),
}

FACILITY_CONVERSATION_PANEL_OWNERS = frozenset().union(
    *FACILITY_OWNER_SETS_BY_SESSION.values())


def facility_owners_for_session(session_name: str) -> frozenset:
    """active 施設 session 名に対し、保護/継続を許可する L4 owner 集合を返す。

    未知 session は空集合 (= 何も保護しない)。これにより施設横断の owner 保護
    (例: equipment active 中に shop_menu を保護) を構造的に排除する。
    """
    return FACILITY_OWNER_SETS_BY_SESSION.get(session_name or "", frozenset())


def area_from_base_location_key(key: Optional[str]) -> str:
    """MapDispatcher の key を C 配下 area 名へ正規化する。"""
    return BASE_KEY_TO_AREA.get(key or "", "")


def base_location_key_from_area(area: Optional[str]) -> str:
    """C 配下 area 名を BaseLocationDispatcher の key へ正規化する。"""
    return AREA_TO_BASE_KEY.get(area or "", "")


def active_session_name(window, *, require_active: bool = True) -> str:
    """現在 active な session 名を返す。

    SessionManager.active_session() は try_stop 中に「active を落とした直後だが
    manager 側の参照はまだ残っている」瞬間があるため、既定では
    SessionBase.is_active() も見る。
    """
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
    """L3 施設会話 session 名 (tavern / temple) を返す。該当なしは空文字。"""
    name = active_session_name(window, require_active=require_active)
    return name if name in FACILITY_CONVERSATION_SESSION_NAMES else ""


def is_facility_conversation_owner(owner: str) -> bool:
    """owner が施設内 L4 会話/メニュー表示を所有する leaf か判定する。"""
    return (owner or "") in FACILITY_CONVERSATION_PANEL_OWNERS


def _base_location_key_from_window(window) -> str:
    """window から直近の C 配下 L2 key を副作用なしで読む。

    単一ソース = poll 確定の親保持 area (`w._last_non_interior_area`・
    L2 単一軸 `resolve_area_with_indoor_fallback` の出力で、屋内中は
    入店時の親 L2 を保持する)。旧実装は map タブ内部
    (`window._tab_map._dispatcher` の active/last_known key) を第一候補に
    読む二重ソース調停だった (S6-2 で撤去: 階層認識が UI タブ内部へ越境
    せず、map 軸は描画経路専用に閉じる)。
    """
    return base_location_key_from_area(
        getattr(window, "_last_non_interior_area", "") or "")


@dataclass(frozen=True)
class SeparationHierarchy:
    """L1-L4 の親子関係を表す immutable snapshot。"""

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
        """既読値から分離階層を構築する。

        A/B は現状 L2 以降を未展開として扱う。C の場合だけ C1/C2/C3 と
        その配下 L3/L4 を入れ子で表す。
        """
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
            # 中途接続で屋外親をまだ持たない屋内は、
            # 暫定方針として街配下の店内に置く。
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
        """window の現在値から分離階層 snapshot を作る。副作用は持たない。"""
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
        """接続バー用の [A] / [B] / [C] / [C1-C3] 表示を返す。"""
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
    """分離階層認識時に使った判定値のログ用 snapshot。"""

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
        """ログ連発防止用。階層パスが変わった時だけ変化する key。"""
        return hierarchy.path_codes, hierarchy.path_names

    def anomaly_key(self) -> tuple:
        """矛盾・拒否系ログの抑制 key。該当なしなら空 tuple。"""
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
        """ログ出力する判定値。None はそのまま残して原因追跡に使う。"""
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
