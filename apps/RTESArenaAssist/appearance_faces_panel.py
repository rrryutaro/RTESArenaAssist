"""appearance_faces_panel.py — chargen 外見選択時の顔候補表示パネル。

レイアウト (左右分割):
  左側:
    - 補足説明 (i18n: appearance.help_text)
    - 顔候補グリッド (クリック可、金枠=ゲーム側現選択 / 青枠=プレビュー)
      ※ 列数は左側の利用可能幅から動的算出
  右側:
    - 全身像プレビュー (face_idx に応じて body_composite で生成)

  ※ 訳文は翻訳パネル側で表示されるため当パネルでは表示しない (顔表示領域を確保)。

スケール:
  ゲームウィンドウ (DOSBox) の client area を取得し、
  水平 sx = client_w / 320, 垂直 sy = client_h / 200 の float で算出。
  これにより、アスペクト補正・非整数倍率を含むあらゆる解像度で
  「ゲーム画面と同じピクセルサイズ」で描画する。

スクロール: 縦のみ。横は AlwaysOff (パネル幅が狭くても本体は画面サイズ維持)。

memory offsets:
- 0x1AB: is_female (0=男, 1=女)
- 0x1A8: race_index (0-7) — chargen 中も最新の選択値を保持
- 0x129A: chargen 中の face クリックカウンタ (1 クリック=+1, 表示 face = count % num_faces)
- 0x20C: max spell points u16 (> 0 なら magic class → robe shirt)

race source は +0x1A8 を用いる。+0x214 は前回 chargen の残留値を持つことがあり、
最新の選択値を反映しないため使わない。
"""
from __future__ import annotations

import ctypes
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

import i18n_helper as i18n

# CIF/IMG デコーダ（Assist 配下に取り込み済み・他アプリ非依存）。
_HERE = os.path.dirname(os.path.abspath(__file__))
import cif_decoder
import body_composite

_CIF_DIR = os.path.normpath(os.path.join(
    _HERE, "..", "..", "docs", "ARENA-data", "CIF"))
_PAL_PATH = os.path.normpath(os.path.join(
    _HERE, "..", "..", "docs", "ARENA-data", "Other", "PAL.COL"))


def _read_asset_bytes(loose_path: str, vfs_name: str) -> bytes | None:
    """画像 blob を loose（開発時のローカルディレクトリ）優先→ユーザー Arena install の VFS
    （GLOBAL.BSA・CIF/COL は非暗号）の順で読む（公開版対応・無ければ None）。"""
    try:
        if os.path.isfile(loose_path):
            with open(loose_path, "rb") as f:
                return f.read()
    except OSError:
        pass
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            return vfs.read(vfs_name)
    except Exception:  # noqa: BLE001
        pass
    return None

OFF_IS_FEMALE              = 0x1AB
OFF_RACE_INDEX             = 0x1A8   # chargen 中も最新の選択値を保持 (+0x214 は残留値を持つ)
OFF_CHARGEN_FACE_CLICK     = 0x129A  # chargen Appearance: クリックカウンタ
OFF_SPELL_PTS_MAX_U16      = 0x20C   # max spell points (> 0 で magic class 判定)

# Arena native canvas (= scale 1.0)
ARENA_WIDTH = 320
ARENA_HEIGHT = 200
FACE_WIDTH = 40
FACE_HEIGHT = 29

# ゲームウィンドウ未検出時の fallback scale (整数倍、視認可能な値)
DEFAULT_SX = 3.0
DEFAULT_SY = 3.0

POLL_INTERVAL_MS = 200
GRID_SPACING = 4
FACE_BORDER_PAD = 6      # ボタン枠分の余白
LEFT_RIGHT_MARGIN = 16   # 左右余白合算
HBOX_SPACING = 12        # 左右コンテナ間のスペース


def _get_dosbox_client_size(hwnd: int) -> tuple[int, int] | None:
    """ゲームウィンドウの client area サイズ (w, h) を取得。失敗時 None。"""
    if not hwnd:
        return None
    try:
        class _RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        r = _RECT()
        if not ctypes.windll.user32.GetClientRect(int(hwnd), ctypes.byref(r)):
            return None
        return (r.right - r.left, r.bottom - r.top)
    except (AttributeError, OSError):
        return None


class AppearanceFacesPanel(QWidget):
    """chargen 外見選択時の顔候補 + 全身像プレビューパネル。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._analyzer = None
        self._anchor = 0
        self._window = None  # AssistWindow 参照 (DOSBox サイズ取得用)
        self._palette: list[tuple[int, int, int]] = []
        try:
            pal_data = _read_asset_bytes(_PAL_PATH, "PAL.COL")
            self._palette = (cif_decoder.load_col_bytes(pal_data)
                             if pal_data else [(0, 0, 0)] * 256)
        except Exception:  # noqa: BLE001
            self._palette = [(0, 0, 0)] * 256
        self._frames: list[tuple[int, int, bytes]] = []
        self._current_race = -1
        self._current_is_female = -1
        self._current_face_idx = -1   # ゲーム側の現選択
        self._preview_face_idx = -1   # Assist プレビュー選択
        self._current_is_magic = False
        self._current_sx = DEFAULT_SX
        self._current_sy = DEFAULT_SY
        self._face_buttons: list[QPushButton] = []
        self._current_cols = 0

        # ── レイアウト構築 ─────────────────────────────────────
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

        # ── 左側 ────────────────────────────────────────────────
        self._left = QWidget()
        left_lay = QVBoxLayout(self._left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)

        # 補足説明 (i18n)
        # 訳文は翻訳パネル側で表示されるため当パネルでは表示しない
        self._help_lbl = QLabel(i18n.tr("appearance.help_text"))
        self._help_lbl.setWordWrap(True)
        self._help_lbl.setStyleSheet(
            "color:#9cf; font-size:11px; padding:4px 8px; "
            "background:#1a2533; border:1px solid #2e4a66; border-radius:3px;")
        left_lay.addWidget(self._help_lbl)

        # 顔候補グリッド
        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(GRID_SPACING)
        self._grid.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._grid_widget, 0, Qt.AlignLeft | Qt.AlignTop)
        left_lay.addStretch(1)

        # 左は伸縮可
        self._left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        hbox.addWidget(self._left, 1)

        # ── 右側: 全身像プレビュー (常時表示・サイズ固定) ────────
        self._body_lbl = QLabel()
        self._body_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._body_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hbox.addWidget(self._body_lbl, 0, Qt.AlignTop)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ポーリング
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    # ------------------------------------------------------------------
    # 外部 API
    # ------------------------------------------------------------------

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
        """AssistWindow 参照を保持 (DOSBox サイズ取得用)。"""
        self._window = window

    def set_translation_message(self, original: str, translated: str) -> None:
        """互換 API。翻訳パネル側で表示されるため当パネルでは何もしない。"""
        del original, translated

    # ------------------------------------------------------------------
    # ポーリング
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        if self._analyzer is None or self._anchor == 0:
            return
        try:
            race_idx = self._analyzer.read_bytes(
                self._anchor + OFF_RACE_INDEX, 1)[0]
            is_female = self._analyzer.read_bytes(
                self._anchor + OFF_IS_FEMALE, 1)[0]
            face_click = self._analyzer.read_bytes(
                self._anchor + OFF_CHARGEN_FACE_CLICK, 1)[0]
            max_sp_raw = self._analyzer.read_bytes(
                self._anchor + OFF_SPELL_PTS_MAX_U16, 2)
            max_sp = max_sp_raw[0] | (max_sp_raw[1] << 8)
        except (OSError, AttributeError):
            return

        is_magic = max_sp > 0

        # ゲーム画面サイズ追従: sx, sy を更新
        sx, sy = self._compute_scales()
        scale_changed = (
            abs(sx - self._current_sx) > 0.01
            or abs(sy - self._current_sy) > 0.01
        )
        if scale_changed:
            self._current_sx = sx
            self._current_sy = sy
            if self._frames:
                self._rebuild_grid()
            self._update_body_preview()

        # race / gender 変化で CIF 再ロード
        if (race_idx, is_female) != (
                self._current_race, self._current_is_female):
            self._current_race = race_idx
            self._current_is_female = is_female
            self._load_faces(race_idx, is_female)
            # 再ロード後、現在の click counter から face_idx を再計算
            face_idx = self._face_idx_from_click(face_click)
            self._current_face_idx = face_idx
            self._preview_face_idx = face_idx
            self._update_highlight()
            self._update_body_preview()
            return

        # face クリックカウンタの変化 → highlight + body 更新
        face_idx = self._face_idx_from_click(face_click)
        if face_idx != self._current_face_idx:
            self._current_face_idx = face_idx
            self._preview_face_idx = face_idx
            self._update_highlight()
            self._update_body_preview()

        # is_magic 変化 (= 服装変更) → body のみ再描画
        if is_magic != self._current_is_magic:
            self._current_is_magic = is_magic
            self._update_body_preview()

    def _face_idx_from_click(self, click_count: int) -> int:
        """chargen クリックカウンタを表示 face index に変換。

        ゲーム側はカウンタを単調増加させ、表示 face は num_faces で剰余を取る。
        frames 未ロード時は click_count をそのまま (highlight 抑止用に -1 ではない値)。
        """
        n = len(self._frames)
        if n <= 0:
            return -1
        return click_count % n

    def _compute_scales(self) -> tuple[float, float]:
        """ゲームウィンドウ client area から (sx, sy) を float で算出。

        sx = client_w / 320, sy = client_h / 200
        失敗時は (DEFAULT_SX, DEFAULT_SY)。
        """
        if self._window is None:
            return (DEFAULT_SX, DEFAULT_SY)
        try:
            layout_mgr = getattr(self._window, "_layout_mgr", None)
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
        if not (0 <= race <= 7):
            self._frames = []
            self._rebuild_grid()
            return
        prefix = "F" if is_female else ""
        cif_name = f"FACES{prefix}0{race}.CIF"
        cif_path = os.path.join(_CIF_DIR, cif_name)
        cif_data = _read_asset_bytes(cif_path, cif_name)
        if cif_data is None:
            self._frames = []
            self._rebuild_grid()
            return
        try:
            self._frames = cif_decoder.decode_cif_frames_bytes(cif_data)
        except Exception:  # noqa: BLE001
            self._frames = []
        self._rebuild_grid()

    def _compute_cols(self) -> int:
        """左側の利用可能幅から、顔ボタンを何列並べられるか算出。

        全身像の幅 (= BODY_W * sx) を右側に確保し、残りを左に割り当てる。
        """
        face_btn_w = int(FACE_WIDTH * self._current_sx) + FACE_BORDER_PAD
        panel_w = max(self.width(), 0)
        body_w = int(body_composite.BODY_W * self._current_sx)
        # hbox margins(8+8) + hbox spacing
        consumed = LEFT_RIGHT_MARGIN + HBOX_SPACING + body_w
        avail_left = panel_w - consumed
        if avail_left < face_btn_w:
            return 1
        cols = avail_left // (face_btn_w + GRID_SPACING)
        return max(1, int(cols))

    def _rebuild_grid(self) -> None:
        # 既存ボタン破棄
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
            pm = self._pixmap_for(w, h, pix,
                                  self._current_sx, self._current_sy)
            btn.setIcon(pm)
            btn.setIconSize(pm.size())
            btn.setFixedSize(pm.size().width() + FACE_BORDER_PAD,
                             pm.size().height() + FACE_BORDER_PAD)
            btn.setFlat(True)
            btn.clicked.connect(
                lambda _c=False, idx=i: self._on_face_clicked(idx))
            self._grid.addWidget(btn, i // cols, i % cols)
            self._face_buttons.append(btn)
        self._update_highlight()

    def _on_face_clicked(self, idx: int) -> None:
        """顔候補クリック → preview 切替 → 全身像更新。"""
        if idx == self._preview_face_idx:
            return
        self._preview_face_idx = idx
        self._update_highlight()
        self._update_body_preview()

    def _update_highlight(self) -> None:
        """枠色更新。金=ゲーム現選択 / 青=プレビュー / 灰=その他。"""
        for i, btn in enumerate(self._face_buttons):
            if i == self._current_face_idx:
                btn.setStyleSheet(
                    "QPushButton{border:3px solid #ffcc00; "
                    "background:#332200; padding:0;}")
            elif i == self._preview_face_idx:
                btn.setStyleSheet(
                    "QPushButton{border:3px solid #4499ff; "
                    "background:#1a2a44; padding:0;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{border:1px solid #333; padding:0;}")

    def _update_body_preview(self) -> None:
        """preview_face_idx に基づき全身像 (body-only crop) を再描画。

        サイズ: (BODY_W * sx, BODY_H * sy)
          ※ ARENA_WIDTH/HEIGHT (320×200) 全体ではなく、CharacterSheet 側で
            body のみを切り出したサブ画像 (150×200) を ゲーム画面比率と
            同じ sx/sy で拡縮する。これによりステータス表示領域の黒い
            余白を出さずに全身像のみを表示する。
        """
        race = self._current_race
        is_female = bool(self._current_is_female)
        face_idx = (self._preview_face_idx
                    if self._preview_face_idx >= 0
                    else self._current_face_idx)
        body_w = body_composite.BODY_W
        body_h = body_composite.BODY_H
        tgt_w = max(1, int(body_w * self._current_sx))
        tgt_h = max(1, int(body_h * self._current_sy))
        if not (0 <= race <= 7) or face_idx < 0:
            self._body_lbl.clear()
            self._body_lbl.setFixedSize(tgt_w, tgt_h)
            return
        try:
            pixels, palette, w, h = body_composite.build_body_image(
                race=race, is_female=is_female, face_idx=face_idx,
                is_magic_class=self._current_is_magic, equipped_items=None)
        except Exception:  # noqa: BLE001
            self._body_lbl.clear()
            return
        rgba = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            if p < len(palette):
                r, g, b = palette[p]
            else:
                r, g, b = 0, 0, 0
            rgba[i * 4:i * 4 + 4] = bytes((r, g, b, 255))
        img = QImage(bytes(rgba), w, h, w * 4,
                     QImage.Format_RGBA8888).copy()
        if (tgt_w, tgt_h) != (w, h):
            img = img.scaled(tgt_w, tgt_h,
                             Qt.IgnoreAspectRatio, Qt.FastTransformation)
        pm = QPixmap.fromImage(img)
        self._body_lbl.setPixmap(pm)
        self._body_lbl.setFixedSize(pm.size())

    def _pixmap_for(self, w: int, h: int, pixels: bytes,
                    sx: float, sy: float) -> QPixmap:
        rgba = bytearray(w * h * 4)
        for i, p in enumerate(pixels):
            if p < len(self._palette):
                r, g, b = self._palette[p]
            else:
                r, g, b = 0, 0, 0
            a = 0 if p == 0 else 255
            rgba[i * 4:i * 4 + 4] = bytes((r, g, b, a))
        img = QImage(bytes(rgba), w, h, w * 4,
                     QImage.Format_RGBA8888).copy()
        tgt_w = max(1, int(w * sx))
        tgt_h = max(1, int(h * sy))
        if (tgt_w, tgt_h) != (w, h):
            img = img.scaled(tgt_w, tgt_h,
                             Qt.IgnoreAspectRatio, Qt.FastTransformation)
        return QPixmap.fromImage(img)

    # ------------------------------------------------------------------
    # リサイズ → 列数再計算
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if self._frames:
            new_cols = self._compute_cols()
            if new_cols != self._current_cols:
                self._rebuild_grid()


__all__ = ["AppearanceFacesPanel"]
