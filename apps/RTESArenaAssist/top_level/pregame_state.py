"""pregame 状態 (MENU.IMG / LOADSAVE.IMG / OP.IMG / QUOTE / SCROLL 等) の管理。

pregame 関連 IMG 別の翻訳描画は
pregame L1 node 所有の ``top_level/pregame_render.py`` に集約した (描画所有
の node 化 = 分離化)。controllers/img_screen_controller.py の IMG 変化
ハンドラは pregame_render へ委譲する。本モジュールは pregame 状態固有の
遷移ロジック (Load Save 完了 → normal-play 遷移) を扱う。

window 側状態: _pregame_loadsave_seen / _top_level_state /
_transition_top_level
"""
from __future__ import annotations

from top_level.top_level_dispatcher import current_state as _current_top_level


_PREGAME_IMGS = frozenset({
    "QUOTE.IMG", "SCROLL01.IMG", "SCROLL02.IMG", "MENU.IMG", "LOADSAVE.IMG",
})


def check_load_save_transition(w, *, mif_name: str, img_name: str) -> None:
    """LOADSAVE.IMG 経由のロード完了を検出して normal-play へ遷移する。

    pregame 状態 + LOADSAVE.IMG 経過 (_pregame_loadsave_seen=True) +
    ゲーム内 MIF 出現 + pregame 系 IMG 以外 + XMI でない、を全て満たした時
    のみ遷移する。

    New Game は LOADSAVE.IMG を経由しないため _pregame_loadsave_seen=False
    のまま → 誤遷移しない。
    PARCH.CIF + CITYW3.MIF (2 回目 chargen 直行) でも誤遷移しない。
    """
    if (_current_top_level(w) == "pregame"
            and w._pregame_loadsave_seen
            and mif_name
            and img_name not in _PREGAME_IMGS
            and not img_name.endswith(".XMI")):
        w._transition_top_level("normal-play",
                                f"loadsave+mif:{mif_name}")


__all__ = ["check_load_save_transition"]
