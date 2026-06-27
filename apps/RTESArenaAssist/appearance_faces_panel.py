from __future__ import annotations
import ctypes
import os
import sys
from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
import i18n_helper as i18n
_HERE = os.path.dirname(os.path.abspath(__file__))
import cif_decoder
import body_composite
_CIF_DIR = os.path.normpath(os.path.join(_HERE, '..', '..', 'docs', 'ARENA-data', 'CIF'))
_PAL_PATH = os.path.normpath(os.path.join(_HERE, '..', '..', 'docs', 'ARENA-data', 'Other', 'PAL.COL'))

def _read_asset_bytes(loose_path: str, vfs_name: str) -> bytes | None:
    try:
        if os.path.isfile(loose_path):
            with open(loose_path, 'rb') as f:
                return f.read()
    except OSError:
        pass
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            return vfs.read(vfs_name)
    except Exception:
        pass
    return None
OFF_IS_FEMALE = 427
OFF_RACE_INDEX = 424
OFF_CHARGEN_FACE_CLICK = 4762
OFF_SPELL_PTS_MAX_U16 = 524
ARENA_WIDTH = 320
ARENA_HEIGHT = 200
FACE_WIDTH = 40
FACE_HEIGHT = 29
DEFAULT_SX = 3.0
DEFAULT_SY = 3.0
POLL_INTERVAL_MS = 200
GRID_SPACING = 4
FACE_BORDER_PAD = 6
LEFT_RIGHT_MARGIN = 16
HBOX_SPACING = 12

def _get_dosbox_client_size(hwnd: int) -> tuple[int, int] | None:
    if not hwnd:
        return None
    try:

        class _RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
        r = _RECT()
        if not ctypes.windll.user32.GetClientRect(int(hwnd), ctypes.byref(r)):
            return None
        return (r.right - r.left, r.bottom - r.top)
    except (AttributeError, OSError):
        return None

class AppearanceFacesPanel(QWidget):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self._analyzer = None
        self._anchor = 0
        self._window = None
        self._palette: list[tuple[int, int, int]] = []
        try:
            pal_data = _read_asset_bytes(_PAL_PATH, 'PAL.COL')
            self._palette = cif_decoder.load_col_bytes(pal_data) if pal_data else [(0, 0, 0)] * 256
        except Exception:
            self._palette = [(0, 0, 0)] * 256
        self._frames: list[tuple[int, int, bytes]] = []
        self._current_race = -1
        self._current_is_female = -1
        self._current_face_idx = -1
        self._preview_face_idx = -1
        self._current_is_magic = False
        self._current_sx = DEFAULT_SX
        self._current_sy = DEFAULT_SY
        self._face_buttons: list[QPushButton] = []
        self._current_cols = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(self._scroll)
        self._content = QWidget()
        self._scroll.setWidget(self._content)
        hbox = QHBoxLayout(self._content)
        hbox.setContentsMargins(8, 8, 8, 8)
        hbox.setSpacing(HBOX_SPACING)
        self._left = QWidget()
        left_lay = QVBoxLayout(self._left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)
        self._help_lbl = QLabel(i18n.tr('appearance.help_text'))
        self._help_lbl.setWordWrap(True)
        self._help_lbl.setStyleSheet('color:#9cf; font-size:11px; padding:4px 8px; background:#1a2533; border:1px solid #2e4a66; border-radius:3px;')
        left_lay.addWidget(self._help_lbl)
        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(GRID_SPACING)
        self._grid.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._grid_widget, 0, Qt.AlignLeft | Qt.AlignTop)
        left_lay.addStretch(1)
        self._left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        hbox.addWidget(self._left, 1)
        self._body_lbl = QLabel()
        self._body_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._body_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hbox.addWidget(self._body_lbl, 0, Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    def set_memory_target(self, analyzer, anchor: int) -> None:
        self._analyzer = analyzer
        self._anchor = anchor
        if not self._timer.isActive():
            self._timer.start()
        self._poll()

    def clear_memory_target(self) -> None:
        self._analyzer = None
        self._anchor = 0
        self._timer.stop()

    def set_window(self, window) -> None:
        self._window = window

    def set_translation_message(self, original: str, translated: str) -> None:
        del original, translated

    def _poll(self) -> None:
        if self._analyzer is None or self._anchor == 0:
            return
        try:
            race_idx = self._analyzer.read_bytes(self._anchor + OFF_RACE_INDEX, 1)[0]
            is_female = self._analyzer.read_bytes(self._anchor + OFF_IS_FEMALE, 1)[0]
            face_click = self._analyzer.read_bytes(self._anchor + OFF_CHARGEN_FACE_CLICK, 1)[0]
            max_sp_raw = self._analyzer.read_bytes(self._anchor + OFF_SPELL_PTS_MAX_U16, 2)
            max_sp = max_sp_raw[0] | max_sp_raw[1] << 8
        except (OSError, AttributeError):
            return
        is_magic = max_sp > 0
        sx, sy = self._compute_scales()
        scale_changed = abs(sx - self._current_sx) > 0.01 or abs(sy - self._current_sy) > 0.01
        if scale_changed:
            self._current_sx = sx
            self._current_sy = sy
            if self._frames:
                self._rebuild_grid()
            self._update_body_preview()
        if (race_idx, is_female) != (self._current_race, self._current_is_female):
            self._current_race = race_idx
            self._current_is_female = is_female
            self._load_faces(race_idx, is_female)
            face_idx = self._face_idx_from_click(face_click)
            self._current_face_idx = face_idx
            self._preview_face_idx = face_idx
            self._update_highlight()
            self._update_body_preview()
            return
        face_idx = self._face_idx_from_click(face_click)
        if face_idx != self._current_face_idx:
            self._current_face_idx = face_idx
            self._preview_face_idx = face_idx
            self._update_highlight()
            self._update_body_preview()
        if is_magic != self._current_is_magic:
            self._current_is_magic = is_magic
            self._update_body_preview()

    def _face_idx_from_click(self, click_count: int) -> int:
        n = len(self._frames)
        if n <= 0:
            return -1
        return click_count % n

    def _compute_scales(self) -> tuple[float, float]:
        if self._window is None:
            return (DEFAULT_SX, DEFAULT_SY)
        try:
            layout_mgr = getattr(self._window, '_layout_mgr', None)
            if layout_mgr is None:
                return (DEFAULT_SX, DEFAULT_SY)
            hwnd = layout_mgr.get_dosbox_hwnd()
            if not hwnd:
                hwnd = layout_mgr.find_dosbox_hwnd()
            if not hwnd:
                return (DEFAULT_SX, DEFAULT_SY)
            size = _get_dosbox_client_size(hwnd)
            if size is None or size[0] <= 0 or size[1] <= 0:
                return (DEFAULT_SX, DEFAULT_SY)
            sx = size[0] / float(ARENA_WIDTH)
            sy = size[1] / float(ARENA_HEIGHT)
            return (sx, sy)
        except (AttributeError, OSError):
            return (DEFAULT_SX, DEFAULT_SY)

    def _load_faces(self, race: int, is_female: int) -> None:
        if not 0 <= race <= 7:
            self._frames = []
            self._rebuild_grid()
            return
        prefix = 'F' if is_female else ''
        cif_name = f'FACES{prefix}0{race}.CIF'
        cif_path = os.path.join(_CIF_DIR, cif_name)
        cif_data = _read_asset_bytes(cif_path, cif_name)
        if cif_data is None:
            self._frames = []
            self._rebuild_grid()
            return
        try:
            self._frames = cif_decoder.decode_cif_frames_bytes(cif_data)
        except Exception:
            self._frames = []
        self._rebuild_grid()

    def _compute_cols(self) -> int:
        face_btn_w = int(FACE_WIDTH * self._current_sx) + FACE_BORDER_PAD
        panel_w = max(self.width(), 0)
        body_w = int(body_composite.BODY_W * self._current_sx)
        consumed = LEFT_RIGHT_MARGIN + HBOX_SPACING + body_w
        avail_left = panel_w - consumed
        if avail_left < face_btn_w:
            return 1
        cols = avail_left // (face_btn_w + GRID_SPACING)
        return max(1, int(cols))

    def _rebuild_grid(self) -> None:
        for btn in self._face_buttons:
            btn.deleteLater()
        self._face_buttons = []
        if not self._frames:
            self._current_cols = 0
            return
        cols = self._compute_cols()
        self._current_cols = cols
        for i, (w, h, pix) in enumerate(self._frames):
            btn = QPushButton()
            pm = self._pixmap_for(w, h, pix, self._current_sx, self._current_sy)
            btn.setIcon(pm)
            btn.setIconSize(pm.size())
            btn.setFixedSize(pm.size().width() + FACE_BORDER_PAD, pm.size().height() + FACE_BORDER_PAD)
            btn.setFlat(True)
            btn.clicked.connect(lambda _c=False, idx=i: self._on_face_clicked(idx))
            self._grid.addWidget(btn, i // cols, i % cols)
            self._face_buttons.append(btn)
        self._update_highlight()

    def _on_face_clicked(self, idx: int) -> None:
        if idx == self._preview_face_idx:
            return
        self._preview_face_idx = idx
        self._update_highlight()
        self._update_body_preview()

    def _update_highlight(self) -> None:
        for i, btn in enumerate(self._face_buttons):
            if i == self._current_face_idx:
                btn.setStyleSheet('QPushButton{border:3px solid #ffcc00; background:#332200; padding:0;}')
            elif i == self._preview_face_idx:
                btn.setStyleSheet('QPushButton{border:3px solid #4499ff; background:#1a2a44; padding:0;}')
            else:
                btn.setStyleSheet('QPushButton{border:1px solid #333; padding:0;}')

    def _update_body_preview(self) -> None:
        race = self._current_race
        is_female = bool(self._current_is_female)
        face_idx = self._preview_face_idx if self._preview_face_idx >= 0 else self._current_face_idx
        body_w = body_composite.BODY_W
        body_h = body_composite.BODY_H
        tgt_w = max(1, int(body_w * self._current_sx))
        tgt_h = max(1, int(body_h * self._current_sy))
        if not 0 <= race <= 7 or face_idx < 0:
            self._body_lbl.clear()
            self._body_lbl.setFixedSize(tgt_w, tgt_h)
            return
        try:
            pixels, palette, w, h = body_composite.build_body_image(race=race, is_female=is_female, face_idx=face_idx, is_magic_class=self._current_is_magic, equipped_items=None)
        except Exception:
            self._body_lbl.clear()
            return
        rgba = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            if p < len(palette):
                r, g, b = palette[p]
            else:
                r, g, b = (0, 0, 0)
            rgba[i * 4:i * 4 + 4] = bytes((r, g, b, 255))
        img = QImage(bytes(rgba), w, h, w * 4, QImage.Format_RGBA8888).copy()
        if (tgt_w, tgt_h) != (w, h):
            img = img.scaled(tgt_w, tgt_h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        pm = QPixmap.fromImage(img)
        self._body_lbl.setPixmap(pm)
        self._body_lbl.setFixedSize(pm.size())

    def _pixmap_for(self, w: int, h: int, pixels: bytes, sx: float, sy: float) -> QPixmap:
        rgba = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            if p < len(self._palette):
                r, g, b = self._palette[p]
            else:
                r, g, b = (0, 0, 0)
            a = 0 if p == 0 else 255
            rgba[i * 4:i * 4 + 4] = bytes((r, g, b, a))
        img = QImage(bytes(rgba), w, h, w * 4, QImage.Format_RGBA8888).copy()
        tgt_w = max(1, int(w * sx))
        tgt_h = max(1, int(h * sy))
        if (tgt_w, tgt_h) != (w, h):
            img = img.scaled(tgt_w, tgt_h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        return QPixmap.fromImage(img)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._frames:
            new_cols = self._compute_cols()
            if new_cols != self._current_cols:
                self._rebuild_grid()
__all__ = ['AppearanceFacesPanel']
