"""normal_play/map — 分離階層 L3 屋内 session + 共通基底。

分離階層モデルで再構築。L2 (= dungeon / city /
wilderness) は `normal_play/base_location/` へ移管された。本パッケージは
L3 屋内 session と共通基底 (MapContext / MapSessionBase) を保持する。

  - InteriorMapSession (= L3 屋内) — 単一 interior MIF + 全 cell 判明
  - MapDispatcher — L2 + L3 屋内 を統括 (= base_location dispatcher と
    interior の 2 経路を排他選択)

各 session が判定 (try_start/stop) + 描画 (get_canvas_data) + state を
所有し、他 session の state には触らない (「判定 + 描画の
閉じたセット」)。
"""
from __future__ import annotations

# 注意: dispatcher は循環 import 回避のため __init__ で先行 import しない。
# 利用側 (= tabs/tab_map.py 等) は `from normal_play.map.dispatcher import
# MapDispatcher` で直接 import する。
from .base import MapContext, MapSessionBase

__all__ = [
    "MapContext",
    "MapSessionBase",
]
