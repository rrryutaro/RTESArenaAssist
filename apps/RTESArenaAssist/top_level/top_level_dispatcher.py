"""トップレベル状態 (pregame / chargen / normal-play) の dispatch 補助。

SessionContext と分離階層 snapshot を構築し、L1 判定を表示所有者から
分離して各 session/module に渡す。poll_controller.py 本体の分割は段階的に
進めるが、L1 の読み取り経路と context 境界は本モジュールに集約する。

TopLevelDispatcher reader 経路の一元化:
  L1 は表示 owner ではなく判定 state である。`current_state()` は
  ``w._top_level_state`` を読む唯一の判定 helper として導入する (= pure
  read helper)。書き手は ``AssistWindow._transition_top_level()`` を
  正とし、本 helper は writer を変更しない。reader 群は ``w._top_level_state``
  直 read から ``current_state(w)`` へファイル単位で段階移管する。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hierarchy_state import SeparationHierarchy
from session.session_base import SessionContext

# 有効なトップレベル状態。
TOP_LEVEL_STATES = ("pregame", "chargen", "normal-play")


@dataclass(frozen=True)
class TopLevelDispatchScope:
    """現在 poll で有効な L1 dispatch state。

    L1 は panel owner ではなく、pregame / chargen / normal-play のうち
    1 つだけを有効化する判定軸として扱う。
    """

    state: str
    is_pregame: bool
    is_chargen: bool
    is_normal_play: bool


def current_state(w, default: str = "pregame") -> str:
    """現在のトップレベル状態を返す pure read helper。

    ``w._top_level_state`` を読むだけで、owner 主張 / 状態変更は行わない
    (= L1 は判定 state であり表示 owner ではない)。属性が無い /
    未設定の場合は ``default`` を返す (= 既存 reader の
    ``getattr(w, "_top_level_state", "pregame")`` と同義)。

    Args:
      w:       AssistWindow (または互換の属性を持つオブジェクト)。
      default: ``_top_level_state`` 未設定時の既定値。

    Returns:
      "pregame" / "chargen" / "normal-play" のいずれか (= 既存値をそのまま返す)。
    """
    return getattr(w, "_top_level_state", default)


def dispatch_scope(w, default: str = "pregame") -> TopLevelDispatchScope:
    """現在の top-level state を 1 本の dispatch 軸として返す。"""
    state = current_state(w, default=default)
    return TopLevelDispatchScope(
        state=state,
        is_pregame=(state == "pregame"),
        is_chargen=(state == "chargen"),
        is_normal_play=(state == "normal-play"),
    )


def build_session_context(
    w,
    *,
    img_name: Optional[str] = None,
    screen_id: Optional[str] = None,
    top_level_state: Optional[str] = None,
    in_interior: Optional[bool] = None,
    npc_phase: Optional[int] = None,
    npc_active: Optional[bool] = None,
    c_area: Optional[str] = None,
    mif_name: Optional[str] = None,
    interior_mif_name: Optional[str] = None,
    facility_kind: Optional[str] = None,
    hierarchy: Optional[SeparationHierarchy] = None,
    extras: Optional[dict] = None,
) -> SessionContext:
    """window と既読ローカル値から SessionContext を構築する。

    poll_controller 内で個別に組み立てていた L1/L3 判定入力をここへ集約し、
    通常プレイ系 session は同じ context 境界だけを参照する。
    """
    resolved_top = (
        top_level_state if top_level_state is not None else current_state(w))
    resolved_interior = bool(
        in_interior if in_interior is not None
        else getattr(w, "_in_interior", False))
    resolved_npc_phase = (
        npc_phase if npc_phase is not None else getattr(w, "_npc_phase", None))
    resolved_hierarchy = (
        hierarchy if hierarchy is not None
        else SeparationHierarchy.from_window(
            w,
            top_level_state=resolved_top,
            in_interior=resolved_interior,
            npc_active=npc_active,
            c_area=c_area,
        )
    )
    return SessionContext(
        analyzer=getattr(w, "_analyzer", None),
        anchor=getattr(w, "_anchor", 0),
        img_name=(img_name if img_name is not None
                  else getattr(w, "_img_name_prev", "")),
        screen_id=(screen_id if screen_id is not None
                   else getattr(w, "_screen_id_prev", "")),
        top_level_state=resolved_top,
        in_interior=resolved_interior,
        npc_phase=resolved_npc_phase,
        mif_name=(mif_name if mif_name is not None
                  else getattr(w, "_active_mif", "")),
        interior_mif_name=(
            interior_mif_name if interior_mif_name is not None
            else getattr(w, "_interior_mif_name", None)),
        facility_kind=(facility_kind if facility_kind is not None else ""),
        hierarchy=resolved_hierarchy,
        extras=(extras if extras is not None else {"window": w}),
    )


__all__ = [
    "TopLevelDispatchScope",
    "build_session_context",
    "current_state",
    "dispatch_scope",
    "TOP_LEVEL_STATES",
]
