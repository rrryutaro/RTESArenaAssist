"""top_level/top_level_node.py — L1 トップレベル状態ノード。

L1（A 起動中 / B 作成中 / C 通常プレイ）の単一判定 seam。**IMG 変化による遷移**
（T1 EVLINTRO→chargen / T2・T5 MENU・PERCNTRO→pregame）を 1 つの純 classifier
``classify_top_level`` に集約する（L1 の 1軸の単一ソース）。

MIF / フラグ駆動の遷移は別の純関数が担う:
  - T3 ロード完了 (pregame→normal-play): ``top_level.pregame_state.check_load_save_transition``
  - T4 chargen→normal-play (start.mif + post-chargen): ``top_level.chargen_transition.normal_play_entry_reason``

``TopLevelNode`` はこれらを束ねた L1 の単一所有 (owner) を表す（owner名前空間
"top_level"）。L1 は表示所有者 (panel_owner) ではなく判定 state。
"""
from __future__ import annotations

from typing import Tuple

from top_level.top_level_dispatcher import current_state as _current_state


# タイトル復帰を引き起こす IMG（システムメニュー / 死亡後タイトル）
_TITLE_IMGS = ("MENU.IMG", "PERCNTRO.XMI")


def classify_top_level(current_state: str, img: str) -> Tuple[str, str]:
    """IMG 変化による L1 遷移先を 1 つ返す。

    Args:
      current_state: 現在の L1（"pregame"/"chargen"/"normal-play"）。
      img:           変化後の画面 IMG 名。

    Returns:
      (next_state, reason)。遷移しない場合は (current_state, "")。
      - T2/T5: current != pregame ＆ img∈{MENU.IMG,PERCNTRO.XMI} → ("pregame", img)
      - T1   : current == pregame ＆ img==EVLINTRO.XMI         → ("chargen", "EVLINTRO.XMI")
    """
    iu = (img or "").upper()
    cur = current_state or "pregame"
    if cur != "pregame" and iu in _TITLE_IMGS:
        return ("pregame", iu)
    if cur == "pregame" and iu == "EVLINTRO.XMI":
        return ("chargen", "EVLINTRO.XMI")
    return (cur, "")


class TopLevelNode:
    """L1 トップレベル状態の単一所有ノード。"""

    name = "top_level"

    def owner_namespace(self) -> str:
        return self.name

    def current(self, w) -> str:
        """現在の L1 状態（pure read helper への委譲）。"""
        return _current_state(w)

    def classify_transition(self, w, img: str) -> Tuple[str, str]:
        """現在 L1 ＋ IMG から遷移先を返す（classify_top_level への委譲）。"""
        return classify_top_level(_current_state(w), img)


TOP_LEVEL_NODE = TopLevelNode()


__all__ = ["classify_top_level", "TopLevelNode", "TOP_LEVEL_NODE"]
