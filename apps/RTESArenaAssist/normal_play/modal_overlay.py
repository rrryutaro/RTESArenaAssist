"""normal_play/modal_overlay.py — モーダル UI の明示系統。

ジャーナル / システムメニュー / オートマップ等のモーダル UI は、L1-L4 の
親子入れ子に組み込まない**一時的な重なり表示**で、開かれても階層状態は維持
される。本モジュールはその「検出は別系統で管理する」を明示の単一分類器と
して表す:

  - classify_modal_overlay: 確定済み screen_id からモーダル種別を 1 つだけ
    確定する純関数 (判定1回・1軸)
  - 各モーダルの表示単位 (journal 等) はこの結論を消費する (view 消費・
    内部で screen_id を再判定しない = 判定描画セット)

設定ダイアログはアプリ側 UI でゲーム内モーダルではない (対象外)。
system_menu / automap は現状専用の表示単位を持たない (種別の命名のみ)。
"""
from __future__ import annotations


#: モーダル非表示 (= 通常の階層表示のみ)
MODAL_NONE = "none"

#: 確定済み screen_id → モーダル種別 (単一の写像・ここ以外で判定しない)
_SCREEN_ID_TO_MODAL = {
    "logbook": "journal",
    "system_menu": "system_menu",
    "automap": "automap",
}


def classify_modal_overlay(screen_id_stable: str) -> str:
    """確定済み screen_id からモーダル種別を 1 つだけ確定する (純関数)。

    Returns: "journal" / "system_menu" / "automap" / MODAL_NONE
    """
    return _SCREEN_ID_TO_MODAL.get(screen_id_stable or "", MODAL_NONE)


__all__ = ["MODAL_NONE", "classify_modal_overlay"]
