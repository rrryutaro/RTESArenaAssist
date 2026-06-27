from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPolygon, QWheelEvent
from PySide6.QtWidgets import QWidget
_BG_DARK = QColor(26, 26, 46)
_PARCHMENT = QColor(170, 130, 81)
_NOTE_COLOR = QColor(233, 69, 96)
_FLAT_MARK_COLORS = {'tree': QColor(63, 143, 79), 'bush': QColor(143, 178, 74), 'rock': QColor(154, 149, 140), 'grave': QColor(207, 199, 182), 'ruin': QColor(176, 152, 120), 'den': QColor(176, 96, 192), 'other': QColor(138, 130, 118)}
_FLAT_MARK_EDGE = QColor(26, 20, 10)
_NOTE_BG = QColor(31, 20, 18, 200)
_PLAYER_COLOR = QColor(255, 255, 0)
_GRID_LINE = QColor(85, 58, 32, 80)
_CHUNK_LINE = QColor(30, 90, 168, 200)
_CHUNK_COORD_TEXT = QColor(13, 42, 85, 235)
_CHUNK_CELLS = 64
_RECENTER_LINE = QColor(58, 111, 174, 130)
_EDGE_LINE_COLORS = {'fence': QColor(138, 90, 43), 'hedge': QColor(47, 122, 63), 'garden': QColor(157, 184, 85)}
_CROP_FILL_COLORS = {'corn': QColor(181, 161, 58), 'farm': QColor(194, 164, 90)}
_CROP_MARK_COLORS = {'corn': QColor(35, 77, 18), 'farm': QColor(94, 60, 24)}
_CELL_COLORS_ARENA: dict[str, QColor] = {'wall': QColor(130, 89, 48), 'raised': QColor(97, 85, 60), 'door': QColor(146, 0, 0), 'level_up': QColor(0, 105, 0), 'level_down': QColor(0, 0, 255), 'wet_chasm': QColor(109, 138, 174), 'dry_chasm': QColor(20, 40, 40), 'lava_chasm': QColor(255, 0, 0), 'wild_wall': QColor(109, 69, 32), 'wild_door': QColor(255, 0, 0), 'wild_road': QColor(199, 154, 90), 'wild_corn': QColor(181, 161, 58), 'wild_farm': QColor(181, 161, 58), 'wild_field': QColor(181, 161, 58)}
_WILD_FIELD_FLOOR_ID = 2
_CELL_COLORS_MAPVIEWER: dict[str, QColor] = {'wall': QColor(130, 89, 48), 'raised': QColor(120, 120, 112), 'door': QColor(146, 0, 0), 'hidden_door': QColor(168, 85, 212), 'exit_door': QColor(146, 0, 0), 'level_up': QColor(0, 105, 0), 'level_down': QColor(0, 0, 255), 'wet_chasm': QColor(109, 138, 174), 'wall_chasm': QColor(92, 200, 190), 'dry_chasm': QColor(20, 40, 40), 'lava_chasm': QColor(255, 0, 0), 'wild_wall': QColor(109, 69, 32), 'wild_door': QColor(255, 0, 0), 'wild_road': QColor(199, 154, 90)}
_CELL_COLOR_UNKNOWN = QColor(204, 68, 255)
_VIS_ALPHA: dict[int, int] = {1: 100, 2: 180, 3: 255}
_REVEAL_ALL_ALPHA = 255

@dataclass
class CanvasData:
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
    flat_marks: tuple[tuple[int, int, str], ...] = ()
    edge_marks: tuple[tuple[int, int, str], ...] = ()
    crop_marks: tuple[tuple[int, int, str], ...] = ()
    wild_show_crops: bool = True
    is_wilderness: bool = False
    wilderness_compact_view: bool = False
    wild_distinguish_road: bool = True
    wild_show_edge: bool = True
    hidden_door_ids: frozenset[int] = frozenset()
    menu_texture_indices: frozenset[int] = frozenset()
    hidden_door_gating: bool = False
    discovered_hidden_door_cells: frozenset[tuple[int, int]] = frozenset()
    chunk_origin: tuple[int, int] | None = None

def _map1_kind(value: int) -> str:
    if value == 0:
        return 'none'
    high = value >> 12 & 15
    if high == 8:
        return 'entity'
    if value & 32768 == 0:
        most = (value & 32512) >> 8
        least = value & 127
        return 'wall' if most == least else 'raised'
    if high == 9:
        return 'transparent'
    if high == 10:
        return 'edge'
    if high == 11:
        return 'door'
    if high == 12:
        return 'none'
    if high == 13:
        return 'diagonal'
    return 'wall'

def _is_hidden_door_cell(map1_val: int) -> bool:
    return _map1_kind(map1_val) == 'door' and map1_val & 128 != 0

def _floor_kind(floor: int) -> str:
    texture_id = floor >> 8 & 255
    if texture_id == 12:
        return 'dry_chasm'
    if texture_id == 13:
        return 'wet_chasm'
    if texture_id == 14:
        return 'lava_chasm'
    return 'floor'

def _wall_texture_index(value: int, kind: str) -> int:
    if kind == 'edge':
        least = value & 127
        return (least & 63) - 1
    most = (value & 32512) >> 8
    return most - 1

def _is_wild_wall_colored_floor_id(floor_id: int) -> bool:
    return floor_id not in (0, 2, 3, 4)

def _classify_cell(map1_val: int, flor_val: int, level_up_index: int | None=None, level_down_index: int | None=None, *, extended: bool=False, menu_texture_indices: set[int] | None=None, is_wilderness: bool=False, wilderness_compact: bool=False, wild_distinguish_road: bool=False, wild_show_field: bool=False) -> str:
    floor_kind = _floor_kind(flor_val)
    wall_kind = _map1_kind(map1_val)
    floor_id = flor_val >> 8 & 255
    if floor_kind == 'wet_chasm':
        if wall_kind == 'wall':
            return 'wall_chasm' if extended else 'raised'
        if wall_kind == 'raised':
            return 'raised'
        return 'wet_chasm'
    if floor_kind == 'dry_chasm':
        if wall_kind == 'wall':
            return 'raised'
        return 'dry_chasm'
    if floor_kind == 'lava_chasm':
        if wall_kind == 'raised':
            return 'raised'
        return 'lava_chasm'
    if wall_kind in ('none', 'entity', 'diagonal'):
        if is_wilderness:
            if wild_show_field and floor_id == _WILD_FIELD_FLOOR_ID:
                return 'wild_field'
            if _is_wild_wall_colored_floor_id(floor_id):
                return 'wild_road' if wild_distinguish_road else 'wild_wall'
        return 'floor'
    if wall_kind == 'raised':
        return 'wild_wall' if is_wilderness else 'raised'
    if wall_kind == 'door':
        if extended and map1_val & 128 != 0:
            return 'hidden_door'
        return 'wild_door' if is_wilderness else 'door'
    if wall_kind == 'transparent':
        if map1_val & 256 == 0:
            return 'wild_wall' if is_wilderness else 'wall'
        return 'floor'
    if wall_kind in ('wall', 'edge'):
        if wall_kind == 'edge' and is_wilderness and wilderness_compact:
            return 'floor'
        tex = _wall_texture_index(map1_val, wall_kind)
        if level_up_index is not None and tex == level_up_index:
            return 'level_up'
        if level_down_index is not None and tex == level_down_index:
            return 'level_down'
        if extended and menu_texture_indices and (tex in menu_texture_indices):
            return 'exit_door'
        return 'wild_wall' if is_wilderness else 'wall'
    return 'floor'

def _blend_color(base: QColor, vis: int, reveal_all: bool) -> QColor:
    alpha = _REVEAL_ALL_ALPHA if reveal_all else _VIS_ALPHA.get(vis, 255)
    col = QColor(base)
    col.setAlpha(alpha)
    return col

class AutomapCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = CanvasData()
        self._x_flip = True
        self._show_notes = True
        self._show_grid = True
        self._show_chunk_grid = True
        self._show_chunk_coords = True
        self._show_recenter_lines = False
        self._chunk_coord_font_size = 10
        self._chunk_coord_font = QFont('Consolas', self._chunk_coord_font_size)
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
        self.setStyleSheet('background-color: #1a1a2e;')

    def set_data(self, data: CanvasData) -> None:
        prev_x, prev_y = (self._data.player_x, self._data.player_y)
        self._data = data
        if data.hidden_door_ids:
            self._hidden_door_ids = set(data.hidden_door_ids)
        else:
            self._hidden_door_ids = set()
        if data.menu_texture_indices:
            self._menu_texture_indices = set(data.menu_texture_indices)
        else:
            self._menu_texture_indices = set()
        if data.player_x is not None and data.player_y is not None and (data.player_x != prev_x or data.player_y != prev_y):
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
        self._chunk_coord_font = QFont('Consolas', size)
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

    def _transform_x(self, x: int, width: int) -> int:
        return width - 1 - x if self._x_flip else x

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

    def _draw_edge_lines(self, painter: QPainter, d: CanvasData, ox: float, oy: float, W: int, H: int) -> None:
        z = self._zoom
        painter.setBrush(Qt.BrushStyle.NoBrush)
        width = max(2.0, z * 0.3)
        cells_by_cat: dict[str, set[tuple[int, int]]] = {}
        for x, y, cat in d.edge_marks:
            cells_by_cat.setdefault(cat, set()).add((x, y))

        def cx_cy(x: int, y: int) -> tuple[float, float]:
            dx = self._transform_x(x, W)
            return (ox + (dx + 0.5) * z, oy + (y + 0.5) * z)
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
                    painter.drawLine(int(cx), int(cy), int((cx + ncx) / 2), int((cy + ncy) / 2))
                    drawn = True
                if not drawn:
                    r = max(1.5, z * 0.28)
                    painter.drawLine(int(cx - r), int(cy), int(cx + r), int(cy))
                    painter.drawLine(int(cx), int(cy - r), int(cx), int(cy + r))

    def _draw_crop_marks(self, painter: QPainter, d: CanvasData, ox: float, oy: float, W: int, H: int) -> None:
        z = self._zoom
        corn_pen = QPen(_CROP_MARK_COLORS['corn'], max(1.2, z * 0.13))
        corn_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        ear_brush = _CROP_MARK_COLORS['corn']
        furrow_pen = QPen(_CROP_MARK_COLORS['farm'], max(1.0, z * 0.1))
        for x, y, cat in d.crop_marks:
            if not (0 <= x < W and 0 <= y < H):
                continue
            dx = self._transform_x(x, W)
            left = ox + dx * z
            top = oy + y * z
            cx = left + 0.5 * z
            if cat == 'corn':
                painter.setPen(corn_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(int(cx), int(top + z * 0.82), int(cx), int(top + z * 0.42))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(ear_brush)
                rx = max(1.2, z * 0.13)
                ry = max(2.0, z * 0.24)
                painter.drawEllipse(QPointF(cx, top + z * 0.3), rx, ry)
            else:
                painter.setPen(furrow_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for fy in (0.28, 0.5, 0.72):
                    yy = top + z * fy
                    painter.drawLine(int(left), int(yy), int(left + z), int(yy))

    def _draw_flat_marks(self, painter: QPainter, d: CanvasData, ox: float, oy: float, W: int, H: int) -> None:
        z = self._zoom
        s = max(1.6, z * 0.42)
        edge_w = max(0.4, z * 0.06)
        edge_pen = QPen(_FLAT_MARK_EDGE, edge_w)
        no_pen = QPen(Qt.PenStyle.NoPen)
        for x, y, cat in d.flat_marks:
            if not (0 <= x < W and 0 <= y < H):
                continue
            color = _FLAT_MARK_COLORS.get(cat, _FLAT_MARK_COLORS['other'])
            dx = self._transform_x(x, W)
            cx = ox + (dx + 0.5) * z
            cy = oy + (y + 0.5) * z
            icx, icy = (int(cx), int(cy))
            if cat == 'tree':
                painter.setPen(edge_pen if z >= 5 else no_pen)
                painter.setBrush(color)
                tri = QPolygon([QPoint(icx, int(cy - s)), QPoint(int(cx - s * 0.85), int(cy + s * 0.7)), QPoint(int(cx + s * 0.85), int(cy + s * 0.7))])
                painter.drawPolygon(tri)
            elif cat == 'bush':
                painter.setPen(no_pen)
                painter.setBrush(color)
                painter.drawEllipse(QPoint(icx, icy), max(1, int(s * 0.75)), max(1, int(s * 0.75)))
            elif cat == 'rock':
                painter.setPen(no_pen)
                painter.setBrush(color)
                dia = QPolygon([QPoint(icx, int(cy - s * 0.8)), QPoint(int(cx + s * 0.8), icy), QPoint(icx, int(cy + s * 0.8)), QPoint(int(cx - s * 0.8), icy)])
                painter.drawPolygon(dia)
            elif cat == 'grave':
                gp = QPen(color, max(1.2, z * 0.16))
                gp.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(gp)
                painter.drawLine(icx, int(cy - s), icx, int(cy + s))
                painter.drawLine(int(cx - s * 0.7), int(cy - s * 0.25), int(cx + s * 0.7), int(cy - s * 0.25))
            elif cat == 'ruin':
                painter.setPen(QPen(color, max(1.0, z * 0.12)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = int(s * 0.8)
                painter.drawRect(icx - r, icy - r, r * 2, r * 2)
            elif cat == 'den':
                painter.setPen(QPen(color, max(1.0, z * 0.14)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                dia = QPolygon([QPoint(icx, int(cy - s)), QPoint(int(cx + s), icy), QPoint(icx, int(cy + s)), QPoint(int(cx - s), icy)])
                painter.drawPolygon(dia)
            else:
                painter.setPen(no_pen)
                painter.setBrush(color)
                painter.drawEllipse(QPoint(icx, icy), max(1, int(s * 0.45)), max(1, int(s * 0.45)))

    def paintEvent(self, event):
        painter = QPainter(self)
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
        entrance_set: set[tuple[int, int]] = set(d.entrance_cells) if d.entrance_cells else set()
        discovered_hd: set[tuple[int, int]] = set(d.discovered_hidden_door_cells) if d.discovered_hidden_door_cells else set()
        edge_set: set[tuple[int, int]] = {(x, z) for x, z, _c in d.edge_marks} if d.edge_marks else set()
        crop_kind: dict[tuple[int, int], str] = {(x, z): 'wild_corn' if c == 'corn' else 'wild_farm' for x, z, c in d.crop_marks} if d.crop_marks else {}
        for y in range(H):
            for x in range(W):
                _is_entrance = (x, y) in entrance_set
                if self._reveal_all:
                    vis = 3
                else:
                    vis = 0
                    if d.bitmap_grid is not None and y < d.bitmap_grid.shape[0] and (x < d.bitmap_grid.shape[1]):
                        vis = int(d.bitmap_grid[y, x])
                    if _is_entrance:
                        vis = max(vis, 3)
                    elif vis == 0:
                        continue
                dx_screen = self._transform_x(x, W)
                rx = ox + dx_screen * self._zoom
                ry = oy + y * self._zoom
                rect = QRect(int(rx), int(ry), int(self._zoom + 1), int(self._zoom + 1))
                if not self._show_unexplored_floor and (not self._reveal_all):
                    painter.fillRect(rect, _PARCHMENT)
                if has_map1 and has_flor:
                    cell_kind = _classify_cell(int(d.map1[y, x]), int(d.flor[y, x]), d.level_up_index, d.level_down_index, extended=self._reveal_all, menu_texture_indices=self._menu_texture_indices, is_wilderness=d.is_wilderness, wilderness_compact=not d.wild_show_edge, wild_distinguish_road=d.wild_distinguish_road, wild_show_field=d.wild_show_crops)
                else:
                    cell_kind = 'floor' if d.walkable[y, x] else 'wall'
                if (x, y) in entrance_set:
                    cell_kind = 'wild_door' if d.is_wilderness else 'door'
                if (x, y) in edge_set:
                    cell_kind = 'floor'
                ck = crop_kind.get((x, y))
                if ck is not None:
                    cell_kind = ck
                if d.hidden_door_gating and has_map1 and _is_hidden_door_cell(int(d.map1[y, x])):
                    if self._reveal_all or (x, y) in discovered_hd:
                        cell_kind = 'hidden_door'
                    else:
                        cell_kind = 'wall'
                if cell_kind == 'floor':
                    cells_drawn.append((x, y, rect))
                    continue
                base_color = palette.get(cell_kind, _CELL_COLOR_UNKNOWN)
                painter.fillRect(rect, _blend_color(base_color, vis, self._reveal_all))
                cells_drawn.append((x, y, rect))
        if self._show_grid and self._zoom >= 6:
            painter.setPen(QPen(_GRID_LINE))
            if self._show_unexplored_floor or self._reveal_all:
                for yi in range(H + 1):
                    ry = oy + yi * self._zoom
                    painter.drawLine(int(ox), int(ry), int(ox + W * self._zoom), int(ry))
                for xi in range(W + 1):
                    rx = ox + xi * self._zoom
                    painter.drawLine(int(rx), int(oy), int(rx), int(oy + H * self._zoom))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for _x, _y, rect in cells_drawn:
                    painter.drawRect(rect)
        if d.is_wilderness and (self._show_chunk_grid or self._show_chunk_coords):
            if self._show_chunk_grid:
                cpen = QPen(_CHUNK_LINE)
                cpen.setWidth(2)
                painter.setPen(cpen)
                for yi in range(0, H + 1, _CHUNK_CELLS):
                    ry = oy + yi * self._zoom
                    painter.drawLine(int(ox), int(ry), int(ox + W * self._zoom), int(ry))
                for xi in range(0, W + 1, _CHUNK_CELLS):
                    rx = ox + xi * self._zoom
                    painter.drawLine(int(rx), int(oy), int(rx), int(oy + H * self._zoom))
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
                        data_gx = nx - 1 - gx if self._x_flip else gx
                        label = '%d,%d' % (ocx + data_gx, ocy + gy)
                        tw = fm.horizontalAdvance(label)
                        left = int(ox + gx * cell_px)
                        top = int(oy + gy * cell_px)
                        right = int(ox + (gx + 1) * cell_px)
                        bottom = int(oy + (gy + 1) * cell_px)
                        painter.drawText(left + 2, top + asc + 1, label)
                        painter.drawText(right - tw - 2, top + asc + 1, label)
                        painter.drawText(left + 2, bottom - 2, label)
                        painter.drawText(right - tw - 2, bottom - 2, label)
        if d.is_wilderness and self._show_recenter_lines and (self._zoom >= 4):
            rpen = QPen(_RECENTER_LINE)
            rpen.setWidth(1)
            rpen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(rpen)
            half = _CHUNK_CELLS // 2
            for yi in range(half, H, _CHUNK_CELLS):
                ry = oy + yi * self._zoom
                painter.drawLine(int(ox), int(ry), int(ox + W * self._zoom), int(ry))
            for xi in range(half, W, _CHUNK_CELLS):
                rx = ox + xi * self._zoom
                painter.drawLine(int(rx), int(oy), int(rx), int(oy + H * self._zoom))
        if d.edge_marks:
            self._draw_edge_lines(painter, d, ox, oy, W, H)
        if d.crop_marks and self._zoom >= 5:
            self._draw_crop_marks(painter, d, ox, oy, W, H)
        if self._show_notes and d.notes:
            painter.setFont(QFont('Consolas', max(7, int(self._zoom * 0.6))))
            for note in d.notes:
                nx, ny, text = note
                if nx >= W or ny >= H or nx < 0 or (ny < 0):
                    continue
                dx_screen = self._transform_x(nx, W)
                rx = ox + dx_screen * self._zoom
                ry = oy + ny * self._zoom
                text_rect = QRect(int(rx), int(ry), max(60, len(text) * 7), int(self._zoom))
                painter.fillRect(text_rect, _NOTE_BG)
                painter.setPen(_NOTE_COLOR)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f' {text}')
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
                    pen2 = QPen(QColor(16, 16, 16), max(1.5, self._zoom * 0.1))
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
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = max(2.0, min(48.0, self._zoom * factor))
        if self._user_panned:
            pos = event.position()
            center = QPointF(self.width() / 2, self.height() / 2) + self._pan
            offset = pos - center
            scale = new_zoom / self._zoom
            self._pan += offset - offset * scale
        self._zoom = new_zoom
        self.update()
