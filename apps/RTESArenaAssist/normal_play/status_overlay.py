"""normal_play/status_overlay.py — ステータス系 overlay の単一前景 authority (萌芽)。

ステータスパネル (AttributesPanel) の解釈状態 (chargen 中 / ボーナス画面中) を、
poll ごとに1回・純判定で確定するための単一 classify を提供する。

従来、この解釈状態は 2 つの別権威・別駆動様式で供給されていた:
  - `_chargen_mode`     … top_level 軸・**トップレベル遷移イベント駆動**
  - `_is_bonus_screen`  … screen_id 軸・**毎poll駆動**
両者が同一 poll で整合する保証がなく、chargen→通常プレイ遷移の過渡で chargen_mode が
stale になり、ステータスパネルが誤った文脈で経験値/レベル/属性スケールを読む温床だった
(= 多権威・無調停 = 原則1/原則3 違反)。

本モジュールは判定描画セット分離の「判定」側 (純関数・副作用なし) を担い、消費側
(poll_controller→AttributesPanel) は結論を消費するだけにする。後続増分で C1 ダイアログ
前景と統合した「直接描画 overlay の単一前景 authority」へ拡張する余地を残す。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusPanelState:
    """ステータスパネルの解釈状態 (poll ごとに1回確定する単一の真実)。"""

    chargen_mode: bool
    is_bonus_screen: bool


def classify_status_panel_state(
    *, top_level: str, screen_id_stable: str | None
) -> StatusPanelState:
    """ステータスパネルの解釈状態を単一の純判定で確定する (副作用なし)。

    chargen_mode    : トップレベルが chargen のとき True (属性は 0-100 直値・
                      race/level は chargen 検出値優先)。
    is_bonus_screen : 確定画面が bonus_screen のとき True (CHARSTAT.IMG・
                      属性 0-100 直値・BONUS PTS 表示)。

    判定式そのものは従来の 2 箇所 (assist_window `_sync_attributes_chargen_mode` /
    poll_controller の bonus 伝達) と同値。差分は「同一 poll・同一箇所で両者を
    確定する」ことによる駆動様式の統一のみ (検出信号は不変)。
    """
    return StatusPanelState(
        chargen_mode=(top_level == "chargen"),
        is_bonus_screen=(screen_id_stable == "bonus_screen"),
    )


__all__ = ["StatusPanelState", "classify_status_panel_state"]
