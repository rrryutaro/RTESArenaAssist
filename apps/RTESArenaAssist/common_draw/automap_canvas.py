"""automap_canvas.py — AUTOMAP visibility overlay 描画 QWidget。

機能:
- MIF MAP1 / FLOR から cell タイプを判定し、Arena 原作色 (AutomapUiMVC.h 互換) で描画
- AUTOMAP visibility (= 2-bit 値) で 3 段階の濃度表現
- プレイヤー位置 + 方角矢印
- プレイヤー中心追従モード (= デフォルト ON、手動パン中はキャラ移動で再追従)
- 「未判明領域に床を表示」設定: ON で canvas widget 全体を巻物地色化 (= MIF 端を見せない)
- 「グリッド線」設定: ON で判明 cell の境界にグリッド線を描く
- 「マップを明らかにする」ON 時は Map Viewer 拡張表現で MIF 構造を全表示
  (= 隠し扉 / 壁下水路 (wall_chasm) / 出口 (exit_door) を別色で識別)
- 「マップでの壁の見通し」は stencil 適用側で処理する (= 描画時 LoS フィルタなし)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import (
    QColor, QFont, QMouseEvent, QPainter, QPen, QPolygon, QWheelEvent)
from PySide6.QtWidgets import QWidget


_BG_DARK = QColor(0x1a, 0x1a, 0x2e)
_PARCHMENT = QColor(0xaa, 0x82, 0x51)
_NOTE_COLOR = QColor(0xe9, 0x45, 0x60)

# フィールド(C3)の地物(flat)マーク色（wild_flats の FLAT_* と対応）。
_FLAT_MARK_COLORS = {
    "tree":  QColor(0x3f, 0x8f, 0x4f),
    "bush":  QColor(0x8f, 0xb2, 0x4a),
    "rock":  QColor(0x9a, 0x95, 0x8c),
    "grave": QColor(0xcf, 0xc7, 0xb6),
    "ruin":  QColor(0xb0, 0x98, 0x78),
    "den":   QColor(0xb0, 0x60, 0xc0),
    "other": QColor(0x8a, 0x82, 0x76),
}
_FLAT_MARK_EDGE = QColor(0x1a, 0x14, 0x0a)
_NOTE_BG = QColor(0x1f, 0x14, 0x12, 200)
_PLAYER_COLOR = QColor(0xff, 0xff, 0x00)
_GRID_LINE = QColor(0x55, 0x3a, 0x20, 80)
# chunk(64 cell) 境界の強調線。通常グリッド線より濃く太く、青系で区別する。
_CHUNK_LINE = QColor(0x1e, 0x5a, 0xa8, 200)
_CHUNK_COORD_TEXT = QColor(0x0d, 0x2a, 0x55, 235)
_CHUNK_CELLS = 64
# 再センタ境界（チャンク中央の4分割線）。チャンク境界より控えめな青系の破線。
_RECENTER_LINE = QColor(0x3a, 0x6f, 0xae, 130)
# フィールド edge マーク（フェンス/生垣/庭）の線色（wild_edges の EDGE_* と対応）。
_EDGE_LINE_COLORS = {
    "fence":  QColor(0x8a, 0x5a, 0x2b),   # 木柵=茶
    "hedge":  QColor(0x2f, 0x7a, 0x3f),   # 生垣=濃緑
    "garden": QColor(0x9d, 0xb8, 0x55),   # 庭=黄緑
}
# フィールド作物（面で塗る＋マーク）。塗り色。
_CROP_FILL_COLORS = {
    "corn": QColor(0xb5, 0xa1, 0x3a),     # トウモロコシ=実り金緑（色3）
    "farm": QColor(0xc2, 0xa4, 0x5a),     # 畑=黄土（色2）
}
# 作物マークの線色（塗りの上に重ねる・濃色）。
_CROP_MARK_COLORS = {
    "corn": QColor(0x23, 0x4d, 0x12),     # 穂=濃緑（マークC）
    "farm": QColor(0x5e, 0x3c, 0x18),     # 横畝=濃茶（マークA）
}

# Arena 原作色 (AutomapUiMVC.h:58-69 互換)
# 通常モード (= reveal_all=False) で使用
_CELL_COLORS_ARENA: dict[str, QColor] = {
    "wall":        QColor(130,  89,  48),    # #825930
    "raised":      QColor( 97,  85,  60),    # #61553c
    "door":        QColor(146,   0,   0),    # #920000
    "level_up":    QColor(  0, 105,   0),    # #006900
    "level_down":  QColor(  0,   0, 255),    # #0000ff
    "wet_chasm":   QColor(109, 138, 174),    # #6d8aae
    "dry_chasm":   QColor( 20,  40,  40),    # #142828
    "lava_chasm":  QColor(255,   0,   0),    # #ff0000
    # wilderness 用 (OpenTESArena AutomapUiMVC.h):
    "wild_wall":   QColor(109,  69,  32),    # #6d4520 ColorWildWall (= 壁/建物)
    "wild_door":   QColor(255,   0,   0),    # #ff0000 ColorWildDoor
    "wild_road":   QColor(199, 154,  90),    # #c79a5a 道(通行可)を壁と区別(拡張表示)
    "wild_corn":   QColor(0xb5, 0xa1, 0x3a),  # トウモロコシ(面塗り)
    "wild_farm":   QColor(0xb5, 0xa1, 0x3a),  # 畑(互換・現在未使用＝トウモロコシと同色)
    "wild_field":  QColor(0xb5, 0xa1, 0x3a),  # 畑の地面(tznfield 床)＝トウモロコシと同色で統一
}
# 畑の地面 FLOR テクスチャ id（@FLOORS index 2 = tznfield）。floor_id=(flor>>8)&0xFF。
# climate(TWN/MWN/DWN)で @FLOORS 順が共通の前提（road=1 を使う既存ロジックと同基準）。
_WILD_FIELD_FLOOR_ID = 2

# Map Viewer 拡張表現 (= reveal_all=True 時に使う)
# 隠し扉 / 壁下水路 / 出口 を追加識別する
_CELL_COLORS_MAPVIEWER: dict[str, QColor] = {
    "wall":        QColor(130,  89,  48),    # #825930
    "raised":      QColor(120, 120, 112),    # #787870 (MapViewer 灰)
    "door":        QColor(146,   0,   0),    # #920000
    "hidden_door": QColor(168,  85, 212),    # #a855d4 (隠し扉)
    "exit_door":   QColor(146,   0,   0),    # #920000 (= door と同色だが意味別)
    "level_up":    QColor(  0, 105,   0),    # #006900
    "level_down":  QColor(  0,   0, 255),    # #0000ff
    "wet_chasm":   QColor(109, 138, 174),    # #6d8aae
    "wall_chasm":  QColor( 92, 200, 190),    # #5cc8be (壁下水路)
    "dry_chasm":   QColor( 20,  40,  40),    # #142828
    "lava_chasm":  QColor(255,   0,   0),    # #ff0000
    "wild_wall":   QColor(109,  69,  32),    # #6d4520 (= 壁/建物)
    "wild_door":   QColor(255,   0,   0),    # #ff0000
    "wild_road":   QColor(199, 154,  90),    # #c79a5a 道(通行可)を壁と区別(拡張表示)
}

_CELL_COLOR_UNKNOWN = QColor(0xcc, 0x44, 0xff)

# visibility 段階 alpha (= 巻物地色に向けて blend)
_VIS_ALPHA: dict[int, int] = {1: 100, 2: 180, 3: 255}
_REVEAL_ALL_ALPHA = 255


@dataclass
class CanvasData:
    """キャンバスに描画するデータ一式。"""
    walkable: np.ndarray | None = None
    map1: np.ndarray | None = None
    flor: np.ndarray | None = None
    bitmap_grid: np.ndarray | None = None
    notes: list | None = None
    player_x: int | None = None
    player_y: int | None = None
    player_angle_deg: float | None = None
    level_up_index: int | None = None
    level_down_index: int | None = None
    entrance_cells: tuple[tuple[int, int], ...] = ()
    # 街マップ用: 建物入口 (= MENU voxel) の (x, z) リスト。
    # 街以外 (= ダンジョン / 店内 / フィールド) では空。
    # フィールド(C3)の地物(flat)マーク (x, y, 種別キー)。種別は wild_flats の
    # FLAT_* (tree/bush/rock/grave/ruin/den/other)。塗りつぶさず小マークで描く。
    flat_marks: tuple[tuple[int, int, str], ...] = ()
    # フィールド(C3)のフェンス/生垣/庭のセル (x, z, 区分キー)。区分は wild_edges の
    # EDGE_* (fence/hedge/garden)。塗りつぶさず、隣接フェンスセルと線で繋いで描く
    # （直線/角/T字が自動で出る）。populate 時は当該セルの塗りをスキップする。
    edge_marks: tuple[tuple[int, int, str], ...] = ()
    # フィールド(C3)の作物セル (x, z, 区分=corn/farm)。フェンスと違い「面」なので、
    # セルを作物色で塗り（wild_corn/wild_farm）＋マーク（穂/横畝）を重ねる。
    crop_marks: tuple[tuple[int, int, str], ...] = ()
    # 作物表示 ON のとき畑の地面(tznfield 床)も土色でタイントする。
    wild_show_crops: bool = True
    is_wilderness: bool = False
    # wilderness 描画モード切替: True なら OpenTESArena
    # `AutomapUiView::getWildPixelColor` 互換の wilderness 色テーブル
    # (= 道は壁色 / 普通の地面は透過) で描画する。
    # wilderness compact view: True で edge voxel を非表示にしゲーム自動マップ
    # 互換の簡潔表示にする。False で RMD 全 voxel 描画 (= 詳細モード)。
    wilderness_compact_view: bool = False
    # フィールド(C3)表示拡張トグル（既定 ON＝拡張、OFF＝ゲーム同一）。
    #  wild_distinguish_road: 道(通行可)を建物/壁と別色(wild_road)で描画。
    #  wild_show_edge: 壁の輪郭(edge voxel)を描画（OFF=非表示=ゲーム互換）。
    wild_distinguish_road: bool = True
    wild_show_edge: bool = True
    hidden_door_ids: frozenset[int] = frozenset()
    menu_texture_indices: frozenset[int] = frozenset()
    # 旧 widget 直接 set ではなく CanvasData 経由で
    # 渡せるよう field 化 (= 各 map session が自前の値を返せる)。
    # 隠し扉の発見状態ゲート。hidden_door_gating=True のとき、
    # 隠し扉セルは discovered_hidden_door_cells に含まれる場合のみ紫 (hidden_door)、
    # 含まれなければ壁 (wall) として描画する (= 開けるまでは壁表示)。
    hidden_door_gating: bool = False
    discovered_hidden_door_cells: frozenset[tuple[int, int]] = frozenset()
    # フィールド(C3)の grid NW corner の chunk 座標 (= origin_chunk)。
    # チャンク境界/座標ラベル描画で各 chunk の絶対座標を出すのに使う。
    chunk_origin: tuple[int, int] | None = None


def _map1_kind(value: int) -> str:
    if value == 0:
        return "none"
    high = (value >> 12) & 0x0F
    if high == 0x8:
        return "entity"
    if (value & 0x8000) == 0:
        most = (value & 0x7F00) >> 8
        least = value & 0x007F
        return "wall" if most == least else "raised"
    if high == 0x9:
        return "transparent"
    if high == 0xA:
        return "edge"
    if high == 0xB:
        return "door"
    if high == 0xC:
        return "none"
    if high == 0xD:
        return "diagonal"
    return "wall"


def _is_hidden_door_cell(map1_val: int) -> bool:
    """隠し扉セルか (= door voxel かつ bit7=0x0080 セット)。"""
    return _map1_kind(map1_val) == "door" and (map1_val & 0x0080) != 0


def _floor_kind(floor: int) -> str:
    texture_id = (floor >> 8) & 0xFF
    if texture_id == 0x0C:
        return "dry_chasm"
    if texture_id == 0x0D:
        return "wet_chasm"
    if texture_id == 0x0E:
        return "lava_chasm"
    return "floor"


def _wall_texture_index(value: int, kind: str) -> int:
    if kind == "edge":
        least = value & 0x007F
        return (least & 0x3F) - 1
    most = (value & 0x7F00) >> 8
    return most - 1


def _is_wild_wall_colored_floor_id(floor_id: int) -> bool:
    """OpenTESArena `ArenaVoxelUtils::isFloorWildWallColored` の wilderness 版。

    wilderness では floorID ∈ {0, 2, 3, 4} 以外の floor は wild wall 色
    (= 道/特殊地形) で描画する。chasm (12, 13, 14) は別経路で処理されるので
    ここでは触れない (= chasm を含めても結果は同じだが意味的に分離)。
    """
    return floor_id not in (0, 2, 3, 4)


def _classify_cell(
    map1_val: int, flor_val: int,
    level_up_index: int | None = None,
    level_down_index: int | None = None,
    *,
    extended: bool = False,
    menu_texture_indices: set[int] | None = None,
    is_wilderness: bool = False,
    wilderness_compact: bool = False,
    wild_distinguish_road: bool = False,
    wild_show_field: bool = False,
) -> str:
    """MIF cell タイプを分類する。

    extended=True のとき Map Viewer 拡張表現 (= 隠し扉 / 壁下水路 / 出口) を判定する。
    extended=False (= 既定) のときは Arena 原作互換分類のみ。
    is_wilderness=True のとき OpenTESArena `getWildPixelColor` 互換の
    wilderness 色テーブルに切替 (= wall/door は wild_wall/wild_door 色、
    floor は floorID で wild_wall (= 道) と透過 (= 地面) を分ける)。
    wilderness_compact=True (is_wilderness 時のみ有効) で edge voxel を
    非表示扱い (= ゲーム自動マップ互換)。
    """
    floor_kind = _floor_kind(flor_val)
    wall_kind = _map1_kind(map1_val)
    floor_id = (flor_val >> 8) & 0xFF

    if floor_kind == "wet_chasm":
        if wall_kind == "wall":
            return "wall_chasm" if extended else "raised"
        if wall_kind == "raised":
            return "raised"
        return "wet_chasm"
    if floor_kind == "dry_chasm":
        if wall_kind == "wall":
            return "raised"
        return "dry_chasm"
    if floor_kind == "lava_chasm":
        if wall_kind == "raised":
            return "raised"
        return "lava_chasm"

    if wall_kind in ("none", "entity", "diagonal"):
        # wilderness: 壁が無くても FLOR が wild-wall-colored (= 道/特殊地形)
        # なら描画する。これは「通行可能な道」（壁が無い＝walkable）。
        #  - wild_distinguish_road=True: 道として別色(wild_road)で建物/壁と区別（拡張表示）。
        #  - False: ゲーム同様に壁と同色(wild_wall)。
        # (= OpenTESArena getWildPixelColor は両者とも ColorWildWall で区別しない)
        if is_wilderness:
            # 畑の地面(tznfield)は耕した土色でタイント（作物表示の一部）。
            if wild_show_field and floor_id == _WILD_FIELD_FLOOR_ID:
                return "wild_field"
            if _is_wild_wall_colored_floor_id(floor_id):
                return "wild_road" if wild_distinguish_road else "wild_wall"
        return "floor"
    if wall_kind == "raised":
        return "wild_wall" if is_wilderness else "raised"
    if wall_kind == "door":
        if extended and (map1_val & 0x0080) != 0:
            return "hidden_door"
        return "wild_door" if is_wilderness else "door"
    if wall_kind == "transparent":
        if (map1_val & 0x0100) == 0:
            return "wild_wall" if is_wilderness else "wall"
        return "floor"
    if wall_kind in ("wall", "edge"):
        # wilderness compact view: edge voxel は描画しない (= ゲーム互換)
        if wall_kind == "edge" and is_wilderness and wilderness_compact:
            return "floor"
        tex = _wall_texture_index(map1_val, wall_kind)
        if level_up_index is not None and tex == level_up_index:
            return "level_up"
        if level_down_index is not None and tex == level_down_index:
            return "level_down"
        if extended and menu_texture_indices and tex in menu_texture_indices:
            return "exit_door"
        return "wild_wall" if is_wilderness else "wall"
    return "floor"


def _blend_color(base: QColor, vis: int, reveal_all: bool) -> QColor:
    alpha = _REVEAL_ALL_ALPHA if reveal_all else _VIS_ALPHA.get(vis, 255)
    col = QColor(base)
    col.setAlpha(alpha)
    return col


class AutomapCanvas(QWidget):
    """MIF 構造 + AUTOMAP visibility overlay 描画 widget。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = CanvasData()
        self._x_flip = True
        self._show_notes = True
        self._show_grid = True
        self._show_chunk_grid = True
        self._show_chunk_coords = True
        # 再センタ境界（チャンク中央の4分割破線）。既定 OFF（地図を見やすく）。
        self._show_recenter_lines = False
        self._chunk_coord_font_size = 10
        self._chunk_coord_font = QFont("Consolas", self._chunk_coord_font_size)
        self._reveal_all = False
        self._show_unexplored_floor = False
        self._center_on_player = True
        self._hidden_door_ids: set[int] = set()
        self._menu_texture_indices: set[int] = set()

        self._zoom: float = 12.0
        self._pan: QPointF = QPointF(0, 0)
        self._drag_last: QPointF | None = None
        self._user_panned = False

        self.setMouseTracking(True)
        self.setMinimumSize(420, 420)
        self.setStyleSheet("background-color: #1a1a2e;")

    # ── 公開 API ──────────────────────────────────────────

    def set_data(self, data: CanvasData) -> None:
        prev_x, prev_y = self._data.player_x, self._data.player_y
        self._data = data
        # CanvasData 経由で widget 内 state も更新する
        # (= session 側が hidden_door_ids / menu_texture_indices を所有し、
        # widget は受け取った値をそのまま使う)
        if data.hidden_door_ids:
            self._hidden_door_ids = set(data.hidden_door_ids)
        else:
            self._hidden_door_ids = set()
        if data.menu_texture_indices:
            self._menu_texture_indices = set(data.menu_texture_indices)
        else:
            self._menu_texture_indices = set()
        if (data.player_x is not None and data.player_y is not None
                and (data.player_x != prev_x or data.player_y != prev_y)):
            self._user_panned = False
        self.update()

    def set_hidden_door_ids(self, ids: set[int]) -> None:
        self._hidden_door_ids = set(ids) if ids else set()
        self.update()

    def set_menu_texture_indices(self, indices: set[int]) -> None:
        self._menu_texture_indices = set(indices) if indices else set()
        self.update()

    def set_x_flip(self, flip: bool) -> None:
        if flip == self._x_flip:
            return
        self._x_flip = flip
        self.update()

    def set_show_notes(self, show: bool) -> None:
        if show == self._show_notes:
            return
        self._show_notes = show
        self.update()

    def set_show_grid(self, show: bool) -> None:
        if show == self._show_grid:
            return
        self._show_grid = show
        self.update()

    def set_show_chunk_grid(self, show: bool) -> None:
        if show == self._show_chunk_grid:
            return
        self._show_chunk_grid = show
        self.update()

    def set_show_chunk_coords(self, show: bool) -> None:
        if show == self._show_chunk_coords:
            return
        self._show_chunk_coords = show
        self.update()

    def set_show_recenter_lines(self, show: bool) -> None:
        if show == self._show_recenter_lines:
            return
        self._show_recenter_lines = show
        self.update()

    def set_chunk_coord_font_size(self, size: int) -> None:
        size = max(5, min(48, int(size)))
        if size == self._chunk_coord_font_size:
            return
        self._chunk_coord_font_size = size
        self._chunk_coord_font = QFont("Consolas", size)
        self.update()

    def set_reveal_all(self, enabled: bool) -> None:
        if enabled == self._reveal_all:
            return
        self._reveal_all = enabled
        self.update()

    def set_show_unexplored_floor(self, enabled: bool) -> None:
        if enabled == self._show_unexplored_floor:
            return
        self._show_unexplored_floor = enabled
        self.update()

    def set_center_on_player(self, enabled: bool) -> None:
        if enabled == self._center_on_player:
            return
        self._center_on_player = enabled
        if enabled:
            self._user_panned = False
        self.update()

    def reset_view(self) -> None:
        self._zoom = 12.0
        self._pan = QPointF(0, 0)
        self._user_panned = False
        self.update()

    # ── 描画 ──────────────────────────────────────────────

    def _transform_x(self, x: int, width: int) -> int:
        return (width - 1 - x) if self._x_flip else x

    def _apply_player_centering(self, W: int, H: int) -> None:
        if not self._center_on_player or self._user_panned:
            return
        d = self._data
        if d.player_x is None or d.player_y is None:
            return
        if not (0 <= d.player_x < W and 0 <= d.player_y < H):
            return
        px = self._transform_x(d.player_x, W)
        py = d.player_y
        canvas_w = W * self._zoom
        canvas_h = H * self._zoom
        target_pan_x = canvas_w / 2 - (px + 0.5) * self._zoom
        target_pan_y = canvas_h / 2 - (py + 0.5) * self._zoom
        self._pan = QPointF(target_pan_x, target_pan_y)

    def _palette(self) -> dict[str, QColor]:
        return _CELL_COLORS_MAPVIEWER if self._reveal_all else _CELL_COLORS_ARENA

    def _draw_edge_lines(self, painter: QPainter, d: CanvasData,
                         ox: float, oy: float, W: int, H: int) -> None:
        """フィールドのフェンス/生垣/庭を接続性ベースの線で描く（塗りつぶさない）。

        各セルから、同区分の隣接フェンスセル（上下左右）へ向けてセル中央から共有境界
        まで線を引く。隣接の双方が共有境界まで引くので直線が連結し、縦横の出会いは
        角(L)・三方は T 字として自動的に表現される（facing ビット非依存・x_flip 安全）。
        孤立セルは短い十字で見えるようにする。座標は cell と同じ x_flip + zoom 変換。
        """
        z = self._zoom
        painter.setBrush(Qt.BrushStyle.NoBrush)
        width = max(2.0, z * 0.30)   # 細線(z*0.18)より太く
        # 区分ごとのセル集合（接続は同区分のみ繋ぐ）。
        cells_by_cat: dict[str, set[tuple[int, int]]] = {}
        for x, y, cat in d.edge_marks:
            cells_by_cat.setdefault(cat, set()).add((x, y))

        def cx_cy(x: int, y: int) -> tuple[float, float]:
            dx = self._transform_x(x, W)
            return ox + (dx + 0.5) * z, oy + (y + 0.5) * z

        for cat, cells in cells_by_cat.items():
            color = _EDGE_LINE_COLORS.get(cat)
            if color is None:
                continue
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for x, y in cells:
                if not (0 <= x < W and 0 <= y < H):
                    continue
                cx, cy = cx_cy(x, y)
                neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                drawn = False
                for nx, ny in neighbors:
                    if (nx, ny) not in cells:
                        continue
                    ncx, ncy = cx_cy(nx, ny)
                    # セル中央 → 共有境界(両中央の中点)。隣接も同点まで引き連結。
                    painter.drawLine(int(cx), int(cy),
                                     int((cx + ncx) / 2), int((cy + ncy) / 2))
                    drawn = True
                if not drawn:
                    # 孤立: 短い十字で存在を示す。
                    r = max(1.5, z * 0.28)
                    painter.drawLine(int(cx - r), int(cy), int(cx + r), int(cy))
                    painter.drawLine(int(cx), int(cy - r), int(cx), int(cy + r))

    def _draw_crop_marks(self, painter: QPainter, d: CanvasData,
                         ox: float, oy: float, W: int, H: int) -> None:
        """作物マークを塗りの上に重ねる。トウモロコシ=穂 / 畑=横畝。

        畑の横畝は隣接セルで線が揃い、畑全体に連続した畝として見える。
        座標は cell と同じ x_flip + zoom 変換。grid 同一なら位置はキャッシュ済。
        """
        z = self._zoom
        corn_pen = QPen(_CROP_MARK_COLORS["corn"], max(1.2, z * 0.13))
        corn_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        ear_brush = _CROP_MARK_COLORS["corn"]
        furrow_pen = QPen(_CROP_MARK_COLORS["farm"], max(1.0, z * 0.10))
        for x, y, cat in d.crop_marks:
            if not (0 <= x < W and 0 <= y < H):
                continue
            dx = self._transform_x(x, W)
            left = ox + dx * z
            top = oy + y * z
            cx = left + 0.5 * z
            if cat == "corn":
                # 穂（マークC）: 縦の茎＋上に房（楕円）。
                painter.setPen(corn_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(int(cx), int(top + z * 0.82),
                                 int(cx), int(top + z * 0.42))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(ear_brush)
                rx = max(1.2, z * 0.13)
                ry = max(2.0, z * 0.24)
                painter.drawEllipse(QPointF(cx, top + z * 0.30), rx, ry)
            else:
                # 横畝（マークA）: セル幅いっぱいの平行線（隣接で連結）。
                painter.setPen(furrow_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for fy in (0.28, 0.5, 0.72):
                    yy = top + z * fy
                    painter.drawLine(int(left), int(yy), int(left + z), int(yy))

    def _draw_flat_marks(self, painter: QPainter, d: CanvasData,
                         ox: float, oy: float, W: int, H: int) -> None:
        """フィールド地物(flat)を種別ごとの簡略マークで描く（塗りつぶさない）。

        木=緑▲ / 茂み=黄緑● / 岩=灰◆ / 墓=十字 / 廃墟=□ / 巣穴=紫◇ / その他=点。
        座標は cell と同じ x_flip + zoom 変換。
        """
        z = self._zoom
        s = max(1.6, z * 0.42)        # マークの基準半径
        edge_w = max(0.4, z * 0.06)   # 縁取り幅
        edge_pen = QPen(_FLAT_MARK_EDGE, edge_w)
        no_pen = QPen(Qt.PenStyle.NoPen)
        for x, y, cat in d.flat_marks:
            if not (0 <= x < W and 0 <= y < H):
                continue
            color = _FLAT_MARK_COLORS.get(cat, _FLAT_MARK_COLORS["other"])
            dx = self._transform_x(x, W)
            cx = ox + (dx + 0.5) * z
            cy = oy + (y + 0.5) * z
            icx, icy = int(cx), int(cy)
            if cat == "tree":
                painter.setPen(edge_pen if z >= 5 else no_pen)
                painter.setBrush(color)
                tri = QPolygon([
                    QPoint(icx, int(cy - s)),
                    QPoint(int(cx - s * 0.85), int(cy + s * 0.7)),
                    QPoint(int(cx + s * 0.85), int(cy + s * 0.7)),
                ])
                painter.drawPolygon(tri)
            elif cat == "bush":
                painter.setPen(no_pen)
                painter.setBrush(color)
                painter.drawEllipse(QPoint(icx, icy),
                                    max(1, int(s * 0.75)), max(1, int(s * 0.75)))
            elif cat == "rock":
                painter.setPen(no_pen)
                painter.setBrush(color)
                dia = QPolygon([
                    QPoint(icx, int(cy - s * 0.8)),
                    QPoint(int(cx + s * 0.8), icy),
                    QPoint(icx, int(cy + s * 0.8)),
                    QPoint(int(cx - s * 0.8), icy),
                ])
                painter.drawPolygon(dia)
            elif cat == "grave":
                gp = QPen(color, max(1.2, z * 0.16))
                gp.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(gp)
                painter.drawLine(icx, int(cy - s), icx, int(cy + s))
                painter.drawLine(int(cx - s * 0.7), int(cy - s * 0.25),
                                 int(cx + s * 0.7), int(cy - s * 0.25))
            elif cat == "ruin":
                painter.setPen(QPen(color, max(1.0, z * 0.12)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = int(s * 0.8)
                painter.drawRect(icx - r, icy - r, r * 2, r * 2)
            elif cat == "den":
                painter.setPen(QPen(color, max(1.0, z * 0.14)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                dia = QPolygon([
                    QPoint(icx, int(cy - s)),
                    QPoint(int(cx + s), icy),
                    QPoint(icx, int(cy + s)),
                    QPoint(int(cx - s), icy),
                ])
                painter.drawPolygon(dia)
            else:  # other
                painter.setPen(no_pen)
                painter.setBrush(color)
                painter.drawEllipse(QPoint(icx, icy),
                                    max(1, int(s * 0.45)), max(1, int(s * 0.45)))

    def paintEvent(self, event):  # noqa: D401
        painter = QPainter(self)

        # 未判明領域に床を表示 ON: canvas widget 全体を巻物地色で塗る
        # (= MIF 範囲だけ塗ると端が見えるため、widget 全体を埋める)
        if self._show_unexplored_floor or self._reveal_all:
            painter.fillRect(self.rect(), _PARCHMENT)
        else:
            painter.fillRect(self.rect(), _BG_DARK)

        d = self._data
        if d.walkable is None:
            return

        H, W = d.walkable.shape
        self._apply_player_centering(W, H)

        canvas_w = W * self._zoom
        canvas_h = H * self._zoom
        ox = (self.width() - canvas_w) / 2 + self._pan.x()
        oy = (self.height() - canvas_h) / 2 + self._pan.y()

        has_map1 = d.map1 is not None
        has_flor = d.flor is not None

        palette = self._palette()
        cells_drawn: list[tuple[int, int, QRect]] = []
        # 街マップ用: 入口 (= MENU voxel) cell を高速に判定するための set。
        # MAP1 voxel 自体は wall として分類されているため、ここでは
        # cell_kind を "door" に上書きして Arena 原作色 (#920000) で塗る。
        entrance_set: set[tuple[int, int]] = (
            set(d.entrance_cells) if d.entrance_cells else set()
        )
        # 隠し扉の発見済みセル集合 (= 紫表示対象)。
        discovered_hd: set[tuple[int, int]] = (
            set(d.discovered_hidden_door_cells)
            if d.discovered_hidden_door_cells else set()
        )
        # フィールド edge マーク(フェンス/生垣/庭)のセルは塗らず線で描く。
        # その分のセル塗りをスキップする(柵らしい表示・塗りつぶしブロックにしない)。
        edge_set: set[tuple[int, int]] = (
            {(x, z) for x, z, _c in d.edge_marks} if d.edge_marks else set()
        )
        # 作物セル: フェンスと違い「面」なので作物色で塗る（後段でマークを重ねる）。
        crop_kind: dict[tuple[int, int], str] = (
            {(x, z): ("wild_corn" if c == "corn" else "wild_farm")
             for x, z, c in d.crop_marks} if d.crop_marks else {}
        )

        for y in range(H):
            for x in range(W):
                _is_entrance = (x, y) in entrance_set
                if self._reveal_all:
                    vis = 3
                else:
                    vis = 0
                    if d.bitmap_grid is not None and y < d.bitmap_grid.shape[0] and x < d.bitmap_grid.shape[1]:
                        vis = int(d.bitmap_grid[y, x])
                    # 出口/入口セル (= MENU voxel) は未踏でも常に表示する
                    # (ゲーム画面の地図と同様に出口を必ず描く)。
                    if _is_entrance:
                        vis = max(vis, 3)
                    elif vis == 0:
                        continue

                dx_screen = self._transform_x(x, W)
                rx = ox + dx_screen * self._zoom
                ry = oy + y * self._zoom
                rect = QRect(int(rx), int(ry),
                             int(self._zoom + 1), int(self._zoom + 1))

                # 判明 cell の床塗り (= canvas 全体塗り済の場合は不要)
                if not self._show_unexplored_floor and not self._reveal_all:
                    painter.fillRect(rect, _PARCHMENT)

                if has_map1 and has_flor:
                    cell_kind = _classify_cell(
                        int(d.map1[y, x]), int(d.flor[y, x]),
                        d.level_up_index, d.level_down_index,
                        extended=self._reveal_all,
                        menu_texture_indices=self._menu_texture_indices,
                        is_wilderness=d.is_wilderness,
                        # 壁の輪郭(edge)は wild_show_edge=False で非表示(=ゲーム互換)。
                        wilderness_compact=(not d.wild_show_edge),
                        wild_distinguish_road=d.wild_distinguish_road,
                        wild_show_field=d.wild_show_crops,
                    )
                else:
                    cell_kind = "floor" if d.walkable[y, x] else "wall"

                # 入口 (= MENU voxel) は door 色(赤)で上書き (= ゲーム画面と同じ表現)。
                # フィールドは wild_door(#ff0000)、街/屋内は door(#920000)。
                if (x, y) in entrance_set:
                    cell_kind = "wild_door" if d.is_wilderness else "door"

                # フェンス/生垣/庭のセルは塗らず、後段で接続線として描く。
                if (x, y) in edge_set:
                    cell_kind = "floor"

                # 作物セルは作物色で塗る（後段でマークを重ねる）。
                ck = crop_kind.get((x, y))
                if ck is not None:
                    cell_kind = ck

                # 隠し扉の発見状態ゲート (= 開けるまでは壁、開けたら紫)。
                # reveal_all (= マップ全表示チート) は発見扱いで紫表示する。
                if (d.hidden_door_gating and has_map1
                        and _is_hidden_door_cell(int(d.map1[y, x]))):
                    if self._reveal_all or (x, y) in discovered_hd:
                        cell_kind = "hidden_door"
                    else:
                        cell_kind = "wall"

                if cell_kind == "floor":
                    cells_drawn.append((x, y, rect))
                    continue

                base_color = palette.get(cell_kind, _CELL_COLOR_UNKNOWN)
                painter.fillRect(
                    rect, _blend_color(base_color, vis, self._reveal_all)
                )
                cells_drawn.append((x, y, rect))

        # グリッド線: 描画された cell の境界に枠を引く
        # 未判明領域に床表示 ON の場合は MIF 範囲全体にも引く
        if self._show_grid and self._zoom >= 6:
            painter.setPen(QPen(_GRID_LINE))
            if self._show_unexplored_floor or self._reveal_all:
                for yi in range(H + 1):
                    ry = oy + yi * self._zoom
                    painter.drawLine(int(ox), int(ry),
                                     int(ox + W * self._zoom), int(ry))
                for xi in range(W + 1):
                    rx = ox + xi * self._zoom
                    painter.drawLine(int(rx), int(oy),
                                     int(rx), int(oy + H * self._zoom))
            else:
                # 判明 cell の枠だけにグリッド線を引く (= MIF 端を見せない)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for _x, _y, rect in cells_drawn:
                    painter.drawRect(rect)

        # chunk(64 cell) 境界線＋座標ラベル: フィールド(C3)のみ。最大縮小でも
        # 見えるよう、通常グリッドの zoom>=6 ゲートには依存しない。
        # grid origin は chunk 整列なので等間隔の境界線は x_flip でも位置不変。
        if d.is_wilderness and (self._show_chunk_grid or self._show_chunk_coords):
            if self._show_chunk_grid:
                cpen = QPen(_CHUNK_LINE)
                cpen.setWidth(2)
                painter.setPen(cpen)
                for yi in range(0, H + 1, _CHUNK_CELLS):
                    ry = oy + yi * self._zoom
                    painter.drawLine(int(ox), int(ry),
                                     int(ox + W * self._zoom), int(ry))
                for xi in range(0, W + 1, _CHUNK_CELLS):
                    rx = ox + xi * self._zoom
                    painter.drawLine(int(rx), int(oy),
                                     int(rx), int(oy + H * self._zoom))
            # 各 chunk の絶対座標を、その chunk の 4 角に表示（x_flip を考慮）。
            if self._show_chunk_coords and d.chunk_origin is not None:
                painter.setPen(QPen(_CHUNK_COORD_TEXT))
                painter.setFont(self._chunk_coord_font)
                fm = painter.fontMetrics()
                asc = fm.ascent()
                ocx, ocy = d.chunk_origin
                nx = max(1, W // _CHUNK_CELLS)
                ny = max(1, H // _CHUNK_CELLS)
                cell_px = _CHUNK_CELLS * self._zoom
                for gy in range(ny):
                    for gx in range(nx):
                        # 画面左→右の chunk 列 gx は、x_flip 時 data 列が反転する。
                        data_gx = (nx - 1 - gx) if self._x_flip else gx
                        label = "%d,%d" % (ocx + data_gx, ocy + gy)
                        tw = fm.horizontalAdvance(label)
                        left = int(ox + gx * cell_px)
                        top = int(oy + gy * cell_px)
                        right = int(ox + (gx + 1) * cell_px)
                        bottom = int(oy + (gy + 1) * cell_px)
                        # 4 角に inset 表示（NW / NE / SW / SE）
                        painter.drawText(left + 2, top + asc + 1, label)
                        painter.drawText(right - tw - 2, top + asc + 1, label)
                        painter.drawText(left + 2, bottom - 2, label)
                        painter.drawText(right - tw - 2, bottom - 2, label)

        # 再センタ境界線: 各チャンク中央(cell +32)の縦横破線。フィールド時のみ。
        # 2×2 窓がここを越えると 1 チャンク分ずれて再センタする境界。
        # チャンク整列の grid なので位置は x_flip でも不変。
        if (d.is_wilderness and self._show_recenter_lines
                and self._zoom >= 4):
            rpen = QPen(_RECENTER_LINE)
            rpen.setWidth(1)
            rpen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(rpen)
            half = _CHUNK_CELLS // 2
            for yi in range(half, H, _CHUNK_CELLS):
                ry = oy + yi * self._zoom
                painter.drawLine(int(ox), int(ry),
                                 int(ox + W * self._zoom), int(ry))
            for xi in range(half, W, _CHUNK_CELLS):
                rx = ox + xi * self._zoom
                painter.drawLine(int(rx), int(oy),
                                 int(rx), int(oy + H * self._zoom))

        # フィールド edge マーク(フェンス/生垣/庭)を接続線で描く。
        if d.edge_marks:
            self._draw_edge_lines(painter, d, ox, oy, W, H)

        # フィールド作物(トウモロコシ/畑)のマークを塗りの上に重ねる。
        if d.crop_marks and self._zoom >= 5:
            self._draw_crop_marks(painter, d, ox, oy, W, H)

        if self._show_notes and d.notes:
            painter.setFont(QFont("Consolas", max(7, int(self._zoom * 0.6))))
            for note in d.notes:
                nx, ny, text = note
                if nx >= W or ny >= H or nx < 0 or ny < 0:
                    continue
                dx_screen = self._transform_x(nx, W)
                rx = ox + dx_screen * self._zoom
                ry = oy + ny * self._zoom
                text_rect = QRect(int(rx), int(ry),
                                  max(60, len(text) * 7), int(self._zoom))
                painter.fillRect(text_rect, _NOTE_BG)
                painter.setPen(_NOTE_COLOR)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    f" {text}"
                )

        # フィールド地物(flat)マーク（木/茂み/岩/墓/廃墟）。塗りつぶさず小マークで
        # 重ねる。プレイヤーより下、cell より上。
        if d.flat_marks:
            self._draw_flat_marks(painter, d, ox, oy, W, H)

        if d.player_x is not None and d.player_y is not None:
            px = self._transform_x(d.player_x, W)
            py = d.player_y
            if 0 <= px < W and 0 <= py < H:
                cx = ox + (px + 0.5) * self._zoom
                cy = oy + (py + 0.5) * self._zoom
                radius = max(3, int(self._zoom * 0.35))
                painter.setPen(QPen(_PLAYER_COLOR, 2))
                painter.setBrush(_PLAYER_COLOR)
                painter.drawEllipse(QPoint(int(cx), int(cy)), radius, radius)

                if d.player_angle_deg is not None:
                    a_rad = math.radians(d.player_angle_deg)
                    arrow_len = radius * 1.8
                    sin_a = math.sin(a_rad)
                    if not self._x_flip:
                        sin_a = -sin_a
                    ex = cx + sin_a * arrow_len
                    ey = cy - math.cos(a_rad) * arrow_len
                    pen2 = QPen(QColor(0x10, 0x10, 0x10),
                                max(1.5, self._zoom * 0.10))
                    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen2)
                    painter.drawLine(int(cx), int(cy), int(ex), int(ey))
                    head = max(3.0, self._zoom * 0.25)
                    left_rad = a_rad + math.radians(150)
                    right_rad = a_rad - math.radians(150)
                    ls = math.sin(left_rad)
                    rs = math.sin(right_rad)
                    if not self._x_flip:
                        ls = -ls
                        rs = -rs
                    lx = ex + ls * head
                    ly = ey - math.cos(left_rad) * head
                    rxh = ex + rs * head
                    ryh = ey - math.cos(right_rad) * head
                    painter.drawLine(int(ex), int(ey), int(lx), int(ly))
                    painter.drawLine(int(ex), int(ey), int(rxh), int(ryh))

    # ── マウス操作 ────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_last is not None:
            cur = event.position()
            delta = cur - self._drag_last
            self._pan += delta
            self._drag_last = cur
            if delta.x() != 0 or delta.y() != 0:
                self._user_panned = True
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1 / 1.15)
        new_zoom = max(2.0, min(48.0, self._zoom * factor))
        if self._user_panned:
            pos = event.position()
            center = QPointF(self.width() / 2, self.height() / 2) + self._pan
            offset = pos - center
            scale = new_zoom / self._zoom
            self._pan += offset - offset * scale
        self._zoom = new_zoom
        self.update()
