"""base_location パッケージ — 分離階層 L2 (= 基本居場所)。

分離階層モデルで導入。通常プレイ中の基本居場所
(= C1 ダンジョン / C2 街 / C3 フィールド) を**最上位サブ状態**として
明示分離する。屋内 (= L3) は本 dispatcher の対象外 (= map/dispatcher.py
側で interior 経路として並列処理)。

公開クラス:
  - BaseLocationDispatcher: L2 3 軸の排他選択 + canvas 取得
  - DungeonMapSession / CityMapSession / WildernessMapSession: 各 L2 session

注意: 現状 MapSessionBase / MapContext (= normal_play/map/base.py) を共通基底
として再利用する。段階 8 で HierarchicalSessionBase へ統合予定。
"""
from .base_location_dispatcher import BaseLocationDispatcher
from .dungeon_location import DungeonMapSession
from .city_location import CityMapSession
from .wilderness_location import WildernessMapSession

__all__ = [
    "BaseLocationDispatcher",
    "DungeonMapSession",
    "CityMapSession",
    "WildernessMapSession",
]
