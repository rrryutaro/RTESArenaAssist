"""map/base.py — マップ session の共通基底 + Context dataclass。

判定 + 描画は閉じたセット / UI 更新は UiRouter 経由、
という方針を踏まえ、各 map session の共通契約を定義する:

  - is_active()        : 現在 active か
  - start(ctx)         : active 化 + 初期化
  - stop(ctx)          : 非 active 化 + 必要に応じてキャッシュ保持
  - update(ctx)        : active 中の state 更新 (= MIF ロード / AUTOMAP 取込 等)
  - get_canvas_data()  : 描画用 CanvasData を返す (= 副作用なし)

各 session は CanvasData を直接 widget に渡さず、本基底経由で
MapDispatcher が active session の結果を取得して widget に渡す。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from common_draw.automap_canvas import CanvasData


@dataclass
class MapContext:
    """各 map session に渡される入力 context。

    poll_controller / tab_map から組み立てて MapDispatcher.poll() に渡す。
    session は本 context だけを使い、他 session の state や window 経由の
    値には依存しない (= 判定 + 描画は閉じたセット)。

    軸選択 (どの L2/L3 session が active か) は単一分類器
    ``classify_map_axis`` が決定し、dispatcher がその結論を消費する
    (= classify→dispatch・1軸化。旧「各 session が try_start で自前判定」
    は並列評価+選定モデルのため是正)。in_interior は poll 確定値を注入する
    (単一の真実=判定の二重実行を持たない)。
    """
    # MIF / location
    mif_name:           Optional[str]        # display_mif_name (= dungeon/city MIF)
    interior_mif_name:  Optional[str]        # 店 MIF (= TAVERN1.MIF 等、屋内時)
    location_name:      Optional[str]        # 街/フィールド地域名 (= "Moonguard" 等)
    player_floor:       int
    # player 状態
    player_tile_x: Optional[float]           # rt_x (= タイル単位)
    player_tile_y: Optional[float]           # rt_z
    angle_deg:     Optional[float]
    # メモリ参照 (= 描画データ読取に使う)
    analyzer:      Any                       # ArenaMemoryAnalyzer
    anchor:        Optional[int]
    # UI / 設定
    place_text:    Optional[str]             # マップ上部ラベル
    save_dir:      str                       # AUTOMAP.NN ファイル探索用
    # 屋内在室 (poll 確定値の注入。None なら classify_map_axis が互換
    # fallback として自前 read する)
    in_interior:   Optional[bool] = None
    # L2 場所種別 (poll 確定の単一保持 area = "city"/"wilderness"/"dungeon")。
    # 全消費者が同じ保持値を参照する 1軸化のための注入。None のときだけ
    # classify_map_axis が互換 fallback として detect_play_area を自前で呼ぶ。
    area:          Optional[str] = None
    # マップ用拡張データストア (= 隠し扉の発見状態。None で無効)
    ext_store:     Any = None                # services.map_ext_store.MapExtStore
    # 描画オプション
    wall_los_enabled:         bool = False   # 壁の見通し OFF
    reveal_all:               bool = False   # cheat: マップ全 reveal
    show_unexplored_floor:    bool = False
    center_on_player:         bool = True
    show_grid:                bool = True
    wilderness_compact_view:  bool = False   # [非推奨] 旧フィールド簡潔表示
    # フィールド(C3)拡張表示の実効値（= master AND 個別。tab_map で算出済を注入）。
    # 全 False ＝ ゲーム自動マップ同一。
    wild_distinguish_road:    bool = True    # 道(通行可)を壁と別色に
    wild_show_edge:           bool = True    # 壁の輪郭(edge voxel)を描画
    wild_distinguish_edge:    bool = True    # フェンス/生垣/庭を接続線で区別
    wild_show_crops:          bool = True    # 作物(トウモロコシ/畑)を面塗り＋マーク
    wild_show_all_entrances:  bool = True    # 家/酒場/神殿入口も赤(ゲームは非表示)
    wild_show_static_flats:   bool = True    # 木/茂み/岩等の地物マークを表示


class MapSessionBase:
    """マップ session の共通基底。

    サブクラスは少なくとも以下を実装する:
      - update(ctx)           : active 中の state 更新
      - get_canvas_data()     : 描画用 CanvasData を返す
      - reset_progress()      : 探索状態リセット (= ロード時等)

    軸選択 (どの session が active か) は ``classify_map_axis`` が単一決定
    し dispatcher が消費する (= session は判定を持たない)。
    is_active / start / stop は基底側で提供 (デフォルト挙動: active フラグ
    の切替 + start で update() 呼出)。
    """

    def __init__(self) -> None:
        self._active: bool = False

    def is_active(self) -> bool:
        return self._active

    def start(self, ctx: MapContext) -> None:
        """active 化 + 初期化。"""
        self._active = True

    def stop(self, ctx: MapContext) -> None:
        """非 active 化。state は保持して構わない (= 再進入時にキャッシュとして再利用)。"""
        self._active = False

    def update(self, ctx: MapContext) -> None:
        """active 中の state 更新。"""
        raise NotImplementedError

    def get_canvas_data(self) -> CanvasData:
        """描画用 CanvasData を返す。副作用なし。"""
        raise NotImplementedError

    def reset_progress(self) -> None:
        """探索状態のリセット (= AUTOMAP / seen_cells 等)。MIF / grid は保持。"""
        pass


__all__ = ["MapContext", "MapSessionBase"]
