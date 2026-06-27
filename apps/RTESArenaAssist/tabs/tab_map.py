from __future__ import annotations
import logging
from pathlib import Path
from typing import Literal, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
LocationType = Literal['dungeon', 'city', 'interior', 'wilderness', 'unknown']
import assist_settings as settings
from common_draw.automap_canvas import AutomapCanvas, CanvasData
from controllers.map_ext_lifecycle import get_lifecycle
from normal_play.map import MapContext
from normal_play.map.dispatcher import MapDispatcher
from services.map_ext_store import get_store
_log = logging.getLogger('tab_map')

class TabMap(QWidget):

    def __init__(self, parent: Optional[QWidget]=None, name: str='map') -> None:
        super().__init__(parent)
        self._name = name
        self._place_label = QLabel('', self)
        self._place_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._place_label.setObjectName('mapPlaceLabel')
        self._place_label.setStyleSheet('QLabel#mapPlaceLabel {  padding: 4px 8px;  color: #c9d1e0;  font-weight: bold;  background: #1a2635;  border-bottom: 1px solid #2a4258;}')
        self._canvas = AutomapCanvas(self)
        self._canvas.setObjectName('AssistMapCanvas')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._place_label, 0)
        layout.addWidget(self._canvas, 1)
        self._dispatcher = MapDispatcher()
        self._wall_los_enabled: bool = False
        self.apply_settings()

    def apply_settings(self) -> None:
        self._wall_los_enabled = bool(settings.get('map_wall_line_of_sight', False))
        cheat = bool(settings.get('cheat_enabled', False))
        reveal = bool(settings.get('cheat_reveal_map', False))
        self._canvas.set_reveal_all(cheat and reveal)
        self._canvas.set_show_unexplored_floor(bool(settings.get('map_show_unexplored_floor', False)))
        self._canvas.set_center_on_player(bool(settings.get('map_center_on_player', True)))
        self._canvas.set_show_grid(bool(settings.get('map_show_grid', True)))
        self._canvas.set_show_chunk_grid(bool(settings.get('map_show_chunk_grid', True)))
        self._canvas.set_show_chunk_coords(bool(settings.get('map_show_chunk_coords', True)))
        self._canvas.set_show_recenter_lines(bool(settings.get('map_show_recenter_lines', False)))
        self._canvas.set_chunk_coord_font_size(int(settings.get('map_chunk_coord_font_size', 10)))

    def reset_progress(self) -> None:
        self._dispatcher.reset_progress()
        try:
            get_lifecycle().on_load()
        except Exception:
            _log.exception('map_ext on_load failed')

    def poll_automap_file(self) -> bool:
        return self._dispatcher.poll_automap_file()

    def update_map_state(self, mif_name: Optional[str], player_tile_x: Optional[float], player_tile_y: Optional[float], angle_deg: Optional[float], player_floor: int=0, place_text: Optional[str]=None, location_name: Optional[str]=None, analyzer=None, anchor: Optional[int]=None, interior_mif_name: Optional[str]=None, in_interior: Optional[bool]=None, area: Optional[str]=None) -> None:
        _save_dir = str(settings.get('save_dir', ''))
        try:
            get_lifecycle().poll(analyzer, anchor, _save_dir)
        except Exception:
            _log.exception('map_ext lifecycle poll failed')
        ctx = MapContext(mif_name=mif_name, interior_mif_name=interior_mif_name, in_interior=in_interior, area=area, location_name=location_name, player_floor=player_floor, player_tile_x=player_tile_x, player_tile_y=player_tile_y, angle_deg=angle_deg, analyzer=analyzer, anchor=anchor, ext_store=get_store(), place_text=place_text, save_dir=_save_dir, wall_los_enabled=self._wall_los_enabled, reveal_all=bool(settings.get('cheat_enabled', False)) and bool(settings.get('cheat_reveal_map', False)), show_unexplored_floor=bool(settings.get('map_show_unexplored_floor', False)), center_on_player=bool(settings.get('map_center_on_player', True)), show_grid=bool(settings.get('map_show_grid', True)), wilderness_compact_view=bool(settings.get('wilderness_compact_view', False)), wild_distinguish_road=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_distinguish_road', True)), wild_show_edge=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_show_edge', True)), wild_distinguish_edge=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_distinguish_edge', True)), wild_show_crops=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_show_crops', True)), wild_show_all_entrances=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_show_all_entrances', True)), wild_show_static_flats=bool(settings.get('map_extended_display', True)) and bool(settings.get('wild_show_static_flats', True)))
        try:
            self._dispatcher.poll(ctx)
        except Exception:
            _log.exception('MapDispatcher.poll failed')
            return
        if place_text is not None:
            self._place_label.setText(place_text)
        _cd = self._dispatcher.get_canvas_data()
        self._canvas.set_data(_cd)
        _w = None if _cd.walkable is None else _cd.walkable.shape
        _diag = (self._dispatcher.active_key(), _w, self.isVisible(), self._canvas.isVisible(), (self._canvas.width(), self._canvas.height()))
        if getattr(self, '_diag_prev', None) != _diag:
            self._diag_prev = _diag
            _log.warning('tabmap[%s]: active=%s walkable=%s tab_visible=%s canvas_visible=%s canvas_size=%s', self._name, _diag[0], _w, _diag[2], _diag[3], _diag[4])

    def clear_map(self) -> None:
        try:
            self._canvas.set_data(CanvasData())
            self._canvas.setVisible(False)
            self._place_label.setVisible(False)
        except (AttributeError, RuntimeError):
            pass

    def restore_map(self) -> None:
        try:
            self._canvas.setVisible(True)
            self._place_label.setVisible(True)
        except (AttributeError, RuntimeError):
            pass

    def set_display_active(self, active: bool) -> None:
        if active:
            self.restore_map()
        else:
            self.clear_map()
