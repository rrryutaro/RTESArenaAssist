from __future__ import annotations
import logging
import math
from dataclasses import dataclass
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QPolygon, QWheelEvent
from PySide6.QtWidgets import QMenu, QToolButton, QWidget
from assist_log import RECOGNITION_LEVEL as _RECOG_LEVEL
_log = logging.getLogger('common_draw.automap_canvas')
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
_CELL_COLORS_ARENA: dict[str, QColor] = {'wall': QColor(130, 89, 48), 'diagonal': QColor(130, 89, 48), 'raised': QColor(97, 85, 60), 'door': QColor(146, 0, 0), 'hidden_door': QColor(168, 85, 212), 'wall_chasm': QColor(74, 107, 130), 'wall_passage': QColor(45, 74, 72), 'wall_lava': QColor(160, 74, 24), 'level_up': QColor(0, 105, 0), 'level_down': QColor(0, 0, 255), 'wet_chasm': QColor(109, 138, 174), 'dry_chasm': QColor(20, 40, 40), 'lava_chasm': QColor(255, 0, 0), 'wild_wall': QColor(109, 69, 32), 'wild_door': QColor(255, 0, 0), 'wild_road': QColor(199, 154, 90), 'wild_corn': QColor(181, 161, 58), 'wild_farm': QColor(181, 161, 58), 'wild_field': QColor(181, 161, 58)}
_WILD_FIELD_FLOOR_ID = 2
_CELL_COLORS_MAPVIEWER: dict[str, QColor] = {'wall': QColor(130, 89, 48), 'diagonal': QColor(130, 89, 48), 'raised': QColor(120, 120, 112), 'door': QColor(146, 0, 0), 'hidden_door': QColor(168, 85, 212), 'exit_door': QColor(146, 0, 0), 'level_up': QColor(0, 105, 0), 'level_down': QColor(0, 0, 255), 'wet_chasm': QColor(109, 138, 174), 'wall_chasm': QColor(74, 107, 130), 'wall_passage': QColor(45, 74, 72), 'wall_lava': QColor(160, 74, 24), 'dry_chasm': QColor(20, 40, 40), 'lava_chasm': QColor(255, 0, 0), 'wild_wall': QColor(109, 69, 32), 'wild_door': QColor(255, 0, 0), 'wild_road': QColor(199, 154, 90)}
_CELL_COLOR_UNKNOWN = QColor(204, 68, 255)
_PIPE_WIDTH_RATIO = 0.22

def pipe_fill_color(base: QColor) -> QColor:
    out = base.lighter(150)
    if out.rgb() == base.rgb():
        out = QColor((base.red() * 3 + 255) // 4, (base.green() * 3 + 255) // 4, (base.blue() * 3 + 255) // 4)
    return out
_TREASURE_MARK = QColor(255, 210, 74)
_TREASURE_MARK_EDGE = QColor(74, 51, 0)

def default_color_hex(key: str) -> str:
    if key == 'treasure':
        return _TREASURE_MARK.name()
    col = _CELL_COLORS_ARENA.get(key)
    return col.name() if col is not None else _CELL_COLOR_UNKNOWN.name()
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
    treasure_pile_cells: frozenset = frozenset()
    hidden_door_ids: frozenset[int] = frozenset()
    menu_texture_indices: frozenset[int] = frozenset()
    discovered_hidden_door_cells: frozenset[tuple[int, int]] = frozenset()
    discovered_wall_passage_cells: frozenset[tuple[int, int]] = frozenset()
    map_key: str | None = None
    cache_index: int | None = None
    suppress_map: bool = False
    suppress_reason: str = ''
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
_DOOR_TEXTURE_MASK = 63

def diagonal_shape(map1_val: int, north: int, south: int, east: int, west: int) -> tuple[bool, str | None]:
    is_slash = map1_val & 256 != 0

    def _wall(v: int) -> bool:
        return _map1_kind(v) in ('wall', 'raised')
    if is_slash:
        pa, pb = ((north, west), (south, east))
    else:
        pa, pb = ((north, east), (south, west))
    a = sum((1 for v in pa if _wall(v)))
    b = sum((1 for v in pb if _wall(v)))
    if a > b:
        return (is_slash, 'a')
    if b > a:
        return (is_slash, 'b')
    return (is_slash, None)

def diagonal_polygon(rect, is_slash: bool, side: str):
    from PySide6.QtCore import QPoint
    l, t = (rect.left(), rect.top())
    r, b = (rect.left() + rect.width(), rect.top() + rect.height())
    if is_slash:
        pts = ((l, t), (r, t), (l, b)) if side == 'a' else ((r, t), (r, b), (l, b))
    else:
        pts = ((l, t), (r, t), (r, b)) if side == 'a' else ((l, t), (l, b), (r, b))
    return [QPoint(int(x), int(y)) for x, y in pts]

def facing_delta(angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return (-math.sin(a), -math.cos(a))

def facing_target_cell(player_x, player_y, angle_deg, candidates) -> tuple[int, int] | None:
    if player_x is None or player_y is None or angle_deg is None:
        return None
    fx, fy = facing_delta(angle_deg)
    ix, iy = (int(player_x), int(player_y))
    best: tuple[int, int] | None = None
    best_score = -2.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cell = (ix + dx, iy + dy)
            if cell not in candidates:
                continue
            if dx == 0 and dy == 0:
                score = 0.35
            else:
                norm = math.hypot(dx, dy)
                score = (dx * fx + dy * fy) / norm
                if score < 0.5:
                    continue
            if score > best_score:
                best, best_score = (cell, score)
    return best

def _is_hidden_door_cell(map1_val: int, hidden_door_ids: frozenset | set | None=None) -> bool:
    if not hidden_door_ids:
        return False
    return _map1_kind(map1_val) == 'door' and map1_val & _DOOR_TEXTURE_MASK in hidden_door_ids

def _floor_kind(floor: int) -> str:
    texture_id = floor >> 8 & 255
    if texture_id == 12:
        return 'dry_chasm'
    if texture_id == 13:
        return 'wet_chasm'
    if texture_id == 14:
        return 'lava_chasm'
    return 'floor'

def _is_wall_passage_cell(map1_val: int, flor_val: int) -> bool:
    return _map1_kind(map1_val) in ('wall', 'raised') and _floor_kind(flor_val) in ('wet_chasm', 'dry_chasm', 'lava_chasm')

def pipe_under_kind(map1_val: int, flor_val: int, *, express_wall_chasm: bool=False, express_wall_passage: bool=False, express_wall_lava: bool=False, wall_passage_discovered: bool=False) -> str | None:
    wall_kind = _map1_kind(map1_val)
    if wall_kind not in ('wall', 'raised'):
        return None
    floor_kind = _floor_kind(flor_val)
    if floor_kind == 'wet_chasm':
        if wall_kind == 'raised':
            return None
        if express_wall_chasm and (not wall_passage_discovered):
            return None
        return 'wet_chasm'
    if floor_kind == 'dry_chasm':
        if wall_kind == 'raised':
            if express_wall_passage and (not wall_passage_discovered):
                return None
            return 'dry_chasm'
        if not express_wall_passage or not wall_passage_discovered:
            return None
        return 'dry_chasm'
    if floor_kind == 'lava_chasm':
        if wall_kind == 'raised':
            return None
        if express_wall_lava and (not wall_passage_discovered):
            return None
        return 'lava_chasm'
    return None

def pipe_block_origin(pipe_cells, x: int, y: int) -> bool:
    return all(((x + dx, y + dy) in pipe_cells for dx in (0, 1) for dy in (0, 1)))

def pipe_edge_hidden(pipe_cells, x: int, y: int, dx: int, dy: int) -> bool:
    if dx:
        bx = min(x, x + dx)
        return pipe_block_origin(pipe_cells, bx, y - 1) and pipe_block_origin(pipe_cells, bx, y)
    by = min(y, y + dy)
    return pipe_block_origin(pipe_cells, x - 1, by) and pipe_block_origin(pipe_cells, x, by)

def _wall_texture_index(value: int, kind: str) -> int:
    if kind == 'edge':
        least = value & 127
        return (least & 63) - 1
    most = (value & 32512) >> 8
    return most - 1

def _is_wild_wall_colored_floor_id(floor_id: int) -> bool:
    return floor_id not in (0, 2, 3, 4)

def _classify_cell(map1_val: int, flor_val: int, level_up_index: int | None=None, level_down_index: int | None=None, *, extended: bool=False, express_wall_chasm: bool=False, express_wall_passage: bool=False, express_wall_lava: bool=False, express_hidden_door: bool=True, hidden_door_ids: frozenset | set | None=None, hidden_door_discovered: bool=False, wall_passage_discovered: bool=False, pipe_under: bool=False, menu_texture_indices: set[int] | None=None, is_wilderness: bool=False, wilderness_compact: bool=False, wild_distinguish_road: bool=False, wild_show_field: bool=False) -> str:
    floor_kind = _floor_kind(flor_val)
    wall_kind = _map1_kind(map1_val)
    floor_id = flor_val >> 8 & 255
    if pipe_under and wall_kind in ('wall', 'raised') and (floor_kind in ('wet_chasm', 'dry_chasm', 'lava_chasm')):
        return 'wall' if wall_kind == 'wall' else 'raised'
    if floor_kind == 'wet_chasm':
        if wall_kind == 'raised':
            return 'raised'
        if wall_kind == 'wall':
            if express_wall_chasm:
                return 'wall_chasm' if wall_passage_discovered else 'wall'
            return 'wet_chasm'
        return 'wet_chasm'
    if floor_kind == 'dry_chasm':
        if wall_kind == 'wall':
            if express_wall_passage:
                return 'wall_passage' if wall_passage_discovered else 'wall'
            return 'raised'
        if wall_kind == 'raised':
            if express_wall_passage and (not wall_passage_discovered):
                return 'raised'
            return 'dry_chasm'
        return 'dry_chasm'
    if floor_kind == 'lava_chasm':
        if wall_kind == 'wall':
            if express_wall_lava:
                return 'wall_lava' if wall_passage_discovered else 'wall'
            return 'lava_chasm'
        if wall_kind == 'raised':
            return 'raised'
        return 'lava_chasm'
    if wall_kind == 'diagonal' and (not is_wilderness):
        return 'diagonal'
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
        if express_hidden_door and _is_hidden_door_cell(map1_val, hidden_door_ids):
            return 'hidden_door' if hidden_door_discovered else 'wall'
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
_DEFAULT_ZOOM = 12.0
_MIN_ZOOM = 2.0
_MAX_ZOOM = 48.0

def _ui_text(key: str) -> str:
    try:
        import i18n_helper
        return i18n_helper.tr(key)
    except Exception:
        return key

class AutomapCanvas(QWidget):
    refresh_requested = Signal()

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
        self._express_hidden_door = True
        self._express_wall_chasm = True
        self._express_wall_passage = True
        self._express_wall_lava = True
        self._express_treasure = True
        self._pipe_under = True
        self._pipe_opacity = 100
        self._color_overrides: dict = {}
        self._treasure_mark: str = ''
        self._menu_texture_indices: set[int] = set()
        self._zoom: float = _DEFAULT_ZOOM
        self._pan: QPointF = QPointF(0, 0)
        self._drag_last: QPointF | None = None
        self._user_panned = False
        self._fit_mode = False
        self._data_view_key: tuple | None = None
        self._diag_prev_paint: tuple = ()
        self.setMouseTracking(True)
        self.setMinimumSize(420, 420)
        self.setStyleSheet('background-color: #1a1a2e;')
        self._build_overlay_buttons()

    def set_data(self, data: CanvasData) -> None:
        prev_x, prev_y = (self._data.player_x, self._data.player_y)
        prev_key = self._canvas_data_view_key(self._data)
        next_key = self._canvas_data_view_key(data)
        data_changed = prev_key != next_key
        self._data = data
        if data_changed and (not self._fit_mode):
            self._data_view_key = next_key
            if self._center_on_player:
                self._user_panned = False
                if data.player_x is None or data.player_y is None:
                    self._pan = QPointF(0, 0)
        elif data_changed:
            self._data_view_key = next_key
        if data.hidden_door_ids:
            self._hidden_door_ids = set(data.hidden_door_ids)
        else:
            self._hidden_door_ids = set()
        if data.menu_texture_indices:
            self._menu_texture_indices = set(data.menu_texture_indices)
        else:
            self._menu_texture_indices = set()
        if not self._fit_mode and data.player_x is not None and (data.player_y is not None) and (data.player_x != prev_x or data.player_y != prev_y):
            self._user_panned = False
        self.update()

    def _canvas_data_view_key(self, data: CanvasData) -> tuple:
        shape = None if data.walkable is None else tuple(data.walkable.shape)
        bitmap_shape = None if data.bitmap_grid is None else tuple(data.bitmap_grid.shape)
        return (data.map_key, shape, bitmap_shape, data.is_wilderness, data.chunk_origin, id(data.walkable), id(data.map1), id(data.flor), id(data.bitmap_grid))

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
        self._fit_mode = False
        self._zoom = _DEFAULT_ZOOM
        self._pan = QPointF(0, 0)
        self._user_panned = False
        self._sync_overlay_buttons()
        self.update()

    def fit_to_map(self) -> None:
        self._fit_mode = True
        self._sync_overlay_buttons()
        self.update()

    def _build_overlay_buttons(self) -> None:
        style = 'QToolButton {  color: #dbe4f0; background: rgba(26,38,53,0.86);  border: 1px solid #3a5876; border-radius: 3px;  padding: 2px 6px; font-size: 12px;}QToolButton:hover { background: rgba(42,66,88,0.95); }QToolButton:checked { background: #2f5d86; border-color: #6fa8dc; }'
        self._btn_refresh = QToolButton(self)
        self._btn_refresh.setText('⟳')
        self._btn_refresh.clicked.connect(self.refresh_requested.emit)
        self._btn_fit = QToolButton(self)
        self._btn_fit.setText('⛶')
        self._btn_fit.setCheckable(True)
        self._btn_fit.clicked.connect(lambda: self.fit_to_map())
        self._btn_actual = QToolButton(self)
        self._btn_actual.setText('1:1')
        self._btn_actual.clicked.connect(lambda: self.reset_view())
        self._overlay_buttons = [self._btn_refresh, self._btn_fit, self._btn_actual]
        for b in self._overlay_buttons:
            b.setStyleSheet(style)
            b.setCursor(Qt.CursorShape.ArrowCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.retranslate_ui()
        self._sync_overlay_buttons()

    def retranslate_ui(self) -> None:
        for b, key in ((self._btn_refresh, 'map.action.refresh'), (self._btn_fit, 'map.action.fit'), (self._btn_actual, 'map.action.actual_size')):
            b.setToolTip(_ui_text(key))

    def _sync_overlay_buttons(self) -> None:
        self._btn_fit.setChecked(self._fit_mode)

    def _layout_overlay_buttons(self) -> None:
        margin, gap = (6, 4)
        x = self.width() - margin
        for b in reversed(self._overlay_buttons):
            size = b.sizeHint()
            x -= size.width()
            b.setGeometry(x, margin, size.width(), size.height())
            b.raise_()
            x -= gap

    def build_view_menu(self) -> QMenu:
        menu = QMenu(self)
        for key, slot in (('map.action.refresh', self.refresh_requested.emit), ('map.action.fit', self.fit_to_map), ('map.action.actual_size', self.reset_view)):
            act = QAction(_ui_text(key), menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        return menu

    def contextMenuEvent(self, event) -> None:
        self.build_view_menu().exec(event.globalPos())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_overlay_buttons()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._layout_overlay_buttons()

    def _transform_x(self, x: int, width: int) -> int:
        return width - 1 - x if self._x_flip else x

    def _apply_fit(self, W: int, H: int) -> None:
        if W <= 0 or H <= 0:
            return
        zoom = min(self.width() / float(W), self.height() / float(H))
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, zoom))
        self._pan = QPointF(0, 0)

    def _apply_player_centering(self, W: int, H: int) -> None:
        if self._fit_mode:
            self._apply_fit(W, H)
            return
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

    def _view_center_cell(self, W: int, H: int) -> tuple[float, float]:
        canvas_w = W * self._zoom
        canvas_h = H * self._zoom
        ox = (self.width() - canvas_w) / 2 + self._pan.x()
        oy = (self.height() - canvas_h) / 2 + self._pan.y()
        screen_x = (self.width() / 2 - ox) / self._zoom - 0.5
        screen_y = (self.height() / 2 - oy) / self._zoom - 0.5
        data_x = W - 1 - screen_x if self._x_flip else screen_x
        return (data_x, screen_y)

    def _log_paint_diag(self, W: int, H: int, *, suppressed: bool=False, suppress_reason: str='') -> None:
        if not _log.isEnabledFor(_RECOG_LEVEL):
            return
        d = self._data
        reason = suppress_reason or (d.suppress_reason if d.suppress_map else '')
        vcx, vcy = self._view_center_cell(W, H)
        diag = (self.objectName(), d.map_key, d.cache_index, W, H, d.player_x, d.player_y, round(self._pan.x(), 1), round(self._pan.y(), 1), round(vcx, 2), round(vcy, 2), self._center_on_player, self._user_panned, suppressed, reason, self.isVisible(), self.width(), self.height())
        if diag == self._diag_prev_paint:
            return
        self._diag_prev_paint = diag
        _log.log(_RECOG_LEVEL, 'canvas paint[%s]: map_key=%r cache=#%s walkable=(%d,%d) player=(%s,%s) pan=(%.1f,%.1f) view_center=(%.2f,%.2f) center_on=%s user_panned=%s suppressed=%s reason=%r visible=%s size=(%d,%d)', diag[0], d.map_key, d.cache_index, W, H, d.player_x, d.player_y, self._pan.x(), self._pan.y(), vcx, vcy, self._center_on_player, self._user_panned, suppressed, reason, self.isVisible(), self.width(), self.height())

    def _map_suppression_reason(self) -> str:
        d = self._data
        if d.suppress_map:
            return d.suppress_reason or 'upstream'
        if self._center_on_player and (not self._user_panned) and (d.player_x is None or d.player_y is None):
            return 'unpositioned_center_follow'
        return ''

    def _should_suppress_unpositioned_map(self) -> bool:
        return self._map_suppression_reason() == 'unpositioned_center_follow'

    def set_map_expression(self, *, hidden_door: bool, wall_chasm: bool, wall_passage: bool, wall_lava: bool, treasure: bool) -> None:
        self._express_hidden_door = bool(hidden_door)
        self._express_wall_chasm = bool(wall_chasm)
        self._express_wall_passage = bool(wall_passage)
        self._express_wall_lava = bool(wall_lava)
        self._express_treasure = bool(treasure)
        self.update()

    def set_pipe_under(self, *, enabled: bool, opacity: int) -> None:
        self._pipe_under = bool(enabled)
        self._pipe_opacity = max(0, min(100, int(opacity)))
        self.update()

    def set_color_overrides(self, overrides: dict | None) -> None:
        self._color_overrides = dict(overrides or {})
        self.update()

    def set_treasure_mark(self, mark: str) -> None:
        self._treasure_mark = (mark or '')[:1]
        self.update()

    def _paint_diagonal(self, painter, rect, map1_val, map1, x, y, vis) -> None:
        h, w = map1.shape

        def _at(cx, cy):
            if 0 <= cx < w and 0 <= cy < h:
                return int(map1[cy, cx])
            return 0
        is_slash, side = diagonal_shape(map1_val, _at(x, y - 1), _at(x, y + 1), _at(x + 1, y), _at(x - 1, y))
        if self._x_flip:
            is_slash = not is_slash
        wall_color = _blend_color(self._palette().get('wall', _CELL_COLOR_UNKNOWN), vis, self._reveal_all)
        if side is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(wall_color)
        painter.drawPolygon(diagonal_polygon(rect, is_slash, side))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_pipes(self, painter, pipe_cells, hole_cells, rect_by_cell) -> None:
        opacity = self._pipe_opacity / 100.0
        if opacity <= 0.0:
            return
        if opacity >= 1.0:
            self._draw_pipe_layer(painter, pipe_cells, hole_cells, rect_by_cell)
            return
        dpr = self.devicePixelRatioF()
        layer = QPixmap(QSize(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))))
        layer.setDevicePixelRatio(dpr)
        layer.fill(Qt.GlobalColor.transparent)
        sub = QPainter(layer)
        try:
            self._draw_pipe_layer(sub, pipe_cells, hole_cells, rect_by_cell)
        finally:
            sub.end()
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, layer)
        painter.setOpacity(1.0)

    def _draw_pipe_layer(self, painter, pipe_cells, hole_cells, rect_by_cell) -> None:
        palette = self._palette()
        width = max(2.0, self._zoom * _PIPE_WIDTH_RATIO)
        smooth_before = painter.testRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            self._draw_pipes(painter, pipe_cells, hole_cells, rect_by_cell, palette, width)
        finally:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, smooth_before)

    def _draw_pipes(self, painter, pipe_cells, hole_cells, rect_by_cell, palette, width) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for (x, y), (kind, vis) in pipe_cells.items():
            if not pipe_block_origin(pipe_cells, x, y):
                continue
            near = rect_by_cell.get((x, y))
            far = rect_by_cell.get((x + 1, y + 1))
            if near is None or far is None:
                continue
            base = pipe_fill_color(palette.get(kind, _CELL_COLOR_UNKNOWN))
            painter.setBrush(_blend_color(base, vis, self._reveal_all))
            painter.drawRect(QRect(near.center(), far.center()).normalized())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for (x, y), (kind, vis) in pipe_cells.items():
            rect = rect_by_cell.get((x, y))
            if rect is None:
                continue
            color = _blend_color(palette.get(kind, _CELL_COLOR_UNKNOWN), vis, self._reveal_all)
            center = QPointF(rect.center())
            ends = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (x + dx, y + dy)
                if nb in pipe_cells:
                    if pipe_edge_hidden(pipe_cells, x, y, dx, dy):
                        continue
                elif nb not in hole_cells:
                    continue
                nrect = rect_by_cell.get(nb)
                if nrect is None:
                    continue
                nc = QPointF(nrect.center())
                ends.append(QPointF((center.x() + nc.x()) / 2.0, (center.y() + nc.y()) / 2.0))
            if not ends:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(center, width / 2.0, width / 2.0)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                continue
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            if len(ends) == 2:
                path.moveTo(ends[0])
                path.lineTo(center)
                path.lineTo(ends[1])
            else:
                for end in ends:
                    path.moveTo(center)
                    path.lineTo(end)
            painter.drawPath(path)

    def _palette(self) -> dict[str, QColor]:
        base = _CELL_COLORS_MAPVIEWER if self._reveal_all else _CELL_COLORS_ARENA
        overrides = self._color_overrides
        if not overrides:
            return base
        merged = dict(base)
        for key, hexval in overrides.items():
            if key == 'treasure' or not hexval:
                continue
            col = QColor(hexval)
            if col.isValid():
                merged[key] = col
        return merged

    def _treasure_color(self) -> QColor:
        col = QColor(self._color_overrides.get('treasure', ''))
        return col if col.isValid() else _TREASURE_MARK

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
        _suppress_reason = self._map_suppression_reason()
        if _suppress_reason:
            self._log_paint_diag(W, H, suppressed=True, suppress_reason=_suppress_reason)
            return
        self._apply_player_centering(W, H)
        self._log_paint_diag(W, H)
        canvas_w = W * self._zoom
        canvas_h = H * self._zoom
        ox = (self.width() - canvas_w) / 2 + self._pan.x()
        oy = (self.height() - canvas_h) / 2 + self._pan.y()
        has_map1 = d.map1 is not None
        has_flor = d.flor is not None
        palette = self._palette()
        cells_drawn: list[tuple[int, int, QRect]] = []
        pipe_cells: dict[tuple[int, int], tuple[str, int]] = {}
        hole_cells: set[tuple[int, int]] = set()
        entrance_set: set[tuple[int, int]] = set(d.entrance_cells) if d.entrance_cells else set()
        discovered_hd: set[tuple[int, int]] = set(d.discovered_hidden_door_cells) if d.discovered_hidden_door_cells else set()
        discovered_wp: set[tuple[int, int]] = set(d.discovered_wall_passage_cells) if d.discovered_wall_passage_cells else set()
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
                    cell_kind = _classify_cell(int(d.map1[y, x]), int(d.flor[y, x]), d.level_up_index, d.level_down_index, extended=self._reveal_all, express_wall_chasm=self._reveal_all or self._express_wall_chasm, express_wall_passage=self._reveal_all or self._express_wall_passage, express_wall_lava=self._reveal_all or self._express_wall_lava, express_hidden_door=self._express_hidden_door, hidden_door_ids=self._hidden_door_ids, hidden_door_discovered=self._reveal_all or (x, y) in discovered_hd, wall_passage_discovered=self._reveal_all or (x, y) in discovered_wp, pipe_under=self._pipe_under, menu_texture_indices=self._menu_texture_indices, is_wilderness=d.is_wilderness, wilderness_compact=not d.wild_show_edge, wild_distinguish_road=d.wild_distinguish_road, wild_show_field=d.wild_show_crops)
                else:
                    cell_kind = 'floor' if d.walkable[y, x] else 'wall'
                if self._pipe_under and has_map1 and has_flor:
                    if cell_kind in ('wet_chasm', 'dry_chasm', 'lava_chasm'):
                        hole_cells.add((x, y))
                    else:
                        pk = pipe_under_kind(int(d.map1[y, x]), int(d.flor[y, x]), express_wall_chasm=self._reveal_all or self._express_wall_chasm, express_wall_passage=self._reveal_all or self._express_wall_passage, express_wall_lava=self._reveal_all or self._express_wall_lava, wall_passage_discovered=self._reveal_all or (x, y) in discovered_wp)
                        if pk is not None:
                            pipe_cells[x, y] = (pk, vis)
                if (x, y) in entrance_set:
                    cell_kind = 'wild_door' if d.is_wilderness else 'door'
                if (x, y) in edge_set:
                    cell_kind = 'floor'
                ck = crop_kind.get((x, y))
                if ck is not None:
                    cell_kind = ck
                if cell_kind == 'floor':
                    cells_drawn.append((x, y, rect))
                    continue
                if cell_kind == 'diagonal':
                    self._paint_diagonal(painter, rect, int(d.map1[y, x]), d.map1, x, y, vis)
                    cells_drawn.append((x, y, rect))
                    continue
                base_color = palette.get(cell_kind, _CELL_COLOR_UNKNOWN)
                painter.fillRect(rect, _blend_color(base_color, vis, self._reveal_all))
                cells_drawn.append((x, y, rect))
        if pipe_cells:
            self._paint_pipes(painter, pipe_cells, hole_cells, {(cx, cy): crect for cx, cy, crect in cells_drawn})
        treasure_cells = d.treasure_pile_cells or frozenset() if self._express_treasure else frozenset()
        mark = self._treasure_mark[:1]
        if treasure_cells and mark and (self._zoom >= 4):
            font = QFont()
            font.setPointSizeF(max(6.0, self._zoom * 0.72))
            font.setBold(True)
            painter.setFont(font)
            mark_color = self._treasure_color()
            for tx, ty, trect in cells_drawn:
                if (tx, ty) not in treasure_cells:
                    continue
                painter.setPen(QPen(_TREASURE_MARK_EDGE))
                for ox2, oy2 in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(trect.translated(ox2, oy2), Qt.AlignmentFlag.AlignCenter, mark)
                painter.setPen(QPen(mark_color))
                painter.drawText(trect, Qt.AlignmentFlag.AlignCenter, mark)
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
                drawn_at = {(self._transform_x(_x, W), _y) for _x, _y, _r in cells_drawn}
                for _x, _y, rect in cells_drawn:
                    col = self._transform_x(_x, W)
                    x0, y0 = (rect.x(), rect.y())
                    x1 = int(ox + (col + 1) * self._zoom)
                    y1 = int(oy + (_y + 1) * self._zoom)
                    painter.drawLine(x0, y0, x0, y1)
                    painter.drawLine(x0, y0, x1, y0)
                    if (col + 1, _y) not in drawn_at:
                        painter.drawLine(x1, y0, x1, y1)
                    if (col, _y + 1) not in drawn_at:
                        painter.drawLine(x0, y1, x1, y1)
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
                if self._fit_mode:
                    self._fit_mode = False
                    self._sync_overlay_buttons()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        if self._fit_mode:
            self._fit_mode = False
            self._sync_overlay_buttons()
        if self._user_panned:
            pos = event.position()
            center = QPointF(self.width() / 2, self.height() / 2) + self._pan
            offset = pos - center
            scale = new_zoom / self._zoom
            self._pan += offset - offset * scale
        self._zoom = new_zoom
        self.update()
