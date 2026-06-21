"""session/facility_node.py — 施設分離ノードの共通基底。

施設会話（宿屋 / 神殿 / 装備品店 / 魔術師ギルド / 宮殿）の L3/L4 を「判定描画
セット」として**同じ形**に揃えるための共通基底。完全階層化・分離化の
不変条件のうち、施設ノードが満たすべき形を 1 か所に定義する。

各ノードが持つ形（不変条件）:
  ① 単一所有者     : 本ノードが判定・描画・終了時整理を所有する。
  ② 1軸classifier  : ``classify_view()`` で前景の子画面 (L4) を 1 つだけ確定。
  ⑤ owner名前空間  : ``owner_namespace()``（フラットな衝突を避ける接頭辞）。

親参照（③）・退出時の親復帰（④）は SessionManager / 上位 dispatcher と連携して
統合する。本基底では ``on_exit()`` フックのみ用意する。

宿屋（``TavernNode``）を**参照実装**とし、他施設は同じ形の seam として実装する
（中身の判定はフロー観測後に充足する）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FacilityView:
    """施設の単一判定 (1軸) の汎用結論。

    宿屋は専用の ``TavernView`` を使うが、フロー未解明の施設は本汎用 view を
    seam として用いる（前景なし＝render_owner空）。観測後に各施設が専用 view と
    classifier を実装して充足する。
    """
    l4_kind: str = "none"
    render_owner: str = ""          # '' = 何も描かない
    bar_key: str = ""
    l4_visible: bool = False
    reason: str = "seam"


class FacilityNode:
    """施設分離ノードの共通基底（共通の形）。

    サブクラスは ``name`` を施設識別子（小文字 = owner名前空間の接頭辞）に
    上書きし、``classify_view`` / ``render`` を実装する。中身が未確定の施設は
    最小の seam（前景なし）を返す実装でよい（形だけ先に満たす）。
    """

    #: 施設識別子。owner名前空間の接頭辞、かつ registry のキー。
    name: str = "<facility>"

    #: 本施設が所有する店主メニュー署名 (分離化)。各要素は
    #: (frozenset(items), kind, title_en)。owner_kind は ``name`` で確定する
    #: ため宣言に含めない (= 施設が自分の署名だけを所有・front-door 集中を解消)。
    #: detector はこの宣言を registry 横断で集約して分類表を再構築する。
    menu_signatures: tuple = ()

    def __init__(self) -> None:
        # ③ 親参照（push 時に親ノード/親状態キーを記録）。SessionManager
        #    / 上位 dispatcher と統合する。既定 None（未接続）。
        self._parent: Any = None

    # ------------------------------------------------------------------
    # ③④ 親参照 / 退出時の親復帰
    # ------------------------------------------------------------------
    def set_parent(self, parent: Any) -> "FacilityNode":
        """本ノードの親（親 L2 コード等）を記録する。チェーン用に self を返す。"""
        self._parent = parent
        return self

    @property
    def parent(self) -> Any:
        """記録済みの親（未接続なら None）。"""
        return self._parent

    def exit_to_parent(self, w) -> Any:
        """退出時整理 (on_exit) を行い、復帰先の親を返す（④ 退出復帰の形）。"""
        self.on_exit(w)
        return self._parent

    # ------------------------------------------------------------------
    # ⑤ owner名前空間
    # ------------------------------------------------------------------
    def owner_namespace(self) -> str:
        """本ノードが UiRouter で用いる owner 名前空間の接頭辞を返す。

        親状態名は含めない。既定は ``name``。
        """
        return self.name

    # ------------------------------------------------------------------
    # ② 1軸 classifier（seam）
    # ------------------------------------------------------------------
    def classify_view(self, w, **signals) -> Any:
        """本施設の前景子画面 (L4) を 1 つだけ確定して返す単一判定 (1軸)。

        宿屋は確定実装。フロー未解明の施設は「前景なし」を返す seam を実装
        する（中身は観測後に充足）。戻り値の型は施設ごとの view オブジェクト。
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # ① 所有描画
    # ------------------------------------------------------------------
    def render(self, w, *, view, **ctx):
        """``classify_view`` の結論 (view) に従って本施設の描画を所有実行する。

        下流（poll_controller の後段）が参照するフラグ等を返してよい。
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # ④ 退出時整理（フック。親復帰と統合）
    # ------------------------------------------------------------------
    def on_exit(self, w) -> None:
        """本施設から離脱した poll の終了時整理 seam。

        自分の owner 名前空間だけを閉じる（他 owner を壊さない）。既定 no-op。
        """
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


class SeamFacilityNode(FacilityNode):
    """フロー未解明の施設の seam 実装。

    形（owner名前空間／1軸classifier／所有描画／退出整理）は満たすが、中身は
    最小（前景なし）。実機フロー観測後に ``classify_view`` / ``render`` を宿屋
    (``TavernNode``) と同じ手順で override して充足する。

    現状、神殿/装備品店/魔術師ギルド/宮殿の実描画は poll_controller の共有経路が
    担っているため、本 seam の ``render`` は何も描かず既定フラグを返す（順次
    各施設 owner へ描画を移管する）。
    """

    def classify_view(self, w, **signals) -> FacilityView:
        """seam: 前景なしの汎用 view を返す（観測後に専用 classifier へ）。"""
        return FacilityView(reason=f"seam:{self.name}")

    def render(self, w, *, view, **ctx):
        """seam: 何も描かない。戻り値は poll_controller 後段互換の 4 フラグ。

        (negot_handled, active_tmpl_handled, shop_menu_visible, shop_buy_active)
        """
        return (False, False, False, False)


# ----------------------------------------------------------------------
# 施設ノード レジストリ（facility_kind / name → ノード）
# ----------------------------------------------------------------------
_REGISTRY: Dict[str, FacilityNode] = {}


def register_facility_node(node: FacilityNode) -> None:
    """施設ノードを登録する（name をキーにする）。重複登録は上書き。"""
    _REGISTRY[node.name] = node


def get_facility_node(name: str) -> Optional[FacilityNode]:
    """登録済み施設ノードを取得する。未登録なら None。"""
    return _REGISTRY.get(name or "")


def registered_facility_names() -> list[str]:
    """登録済み施設ノード名の一覧（検査・テスト用）。"""
    return sorted(_REGISTRY.keys())


def build_menu_signature_table() -> Dict[frozenset, tuple]:
    """登録済み施設ノードの ``menu_signatures`` 宣言を横断集約し、
    ``{frozenset(items): (kind, owner_kind, title_en)}`` を返す (分離化)。

    owner_kind は宣言元ノードの ``name``。各施設が自分の署名だけを所有し、
    detector はこの集約結果を front-door 分類表として使う (= 全施設署名を
    detector に直書きする集中を解消)。呼び出し側は事前に全ノードを import 済み
    であること (``session.facility_nodes`` の eager import が保証)。
    """
    table: Dict[frozenset, tuple] = {}
    for node in _REGISTRY.values():
        for sig, kind, title in getattr(node, "menu_signatures", ()):
            table[frozenset(sig)] = (kind, node.name, title)
    return table


__all__ = [
    "FacilityNode",
    "FacilityView",
    "SeamFacilityNode",
    "register_facility_node",
    "get_facility_node",
    "registered_facility_names",
    "build_menu_signature_table",
]
