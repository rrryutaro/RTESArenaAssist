from __future__ import annotations
import logging
from typing import Iterable, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
import body_composite
import cif_decoder
_log = logging.getLogger('RTESArenaAssist')
SCALE_X = 2.0
SCALE_Y = 2.4
FACE_SIZE = (40, 29)
BODY_SIZE = (body_composite.BODY_W, body_composite.BODY_H)

def _asset(name: str) -> Optional[bytes]:
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            return vfs.read(name)
    except Exception:
        pass
    return None

def _to_qimage(pixels: bytes, palette: list, width: int, height: int, *, transparent_zero: bool) -> QImage:
    rgba = bytearray(width * height * 4)
    for i, index in enumerate(pixels):
        r, g, b = palette[index] if index < len(palette) else (0, 0, 0)
        alpha = 0 if transparent_zero and index == 0 else 255
        rgba[i * 4:i * 4 + 4] = bytes((r, g, b, alpha))
    return QImage(bytes(rgba), width, height, width * 4, QImage.Format.Format_RGBA8888).copy()

def scaled_size(size: tuple[int, int]) -> tuple[int, int]:
    return (round(size[0] * SCALE_X), round(size[1] * SCALE_Y))

def _scale(image: QImage) -> QImage:
    width, height = scaled_size((image.width(), image.height()))
    return image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)

def blank(size: tuple[int, int]) -> QImage:
    width, height = scaled_size(size)
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    return image

def build_face(race: int, is_female: bool, face: int) -> Optional[QImage]:
    if not 0 <= race <= 7:
        return None
    data = _asset(f"FACES{('F' if is_female else '')}0{race}.CIF")
    palette_data = _asset('PAL.COL')
    if data is None or palette_data is None:
        return None
    try:
        frames = cif_decoder.decode_cif_frames_bytes(data)
        palette = cif_decoder.load_col_bytes(palette_data)
    except Exception:
        _log.debug('charsheet face decode failed', exc_info=True)
        return None
    if not 0 <= face < len(frames):
        return None
    width, height, pixels = frames[face]
    return _scale(_to_qimage(pixels, palette, width, height, transparent_zero=True))

def build_body(race: int, is_female: bool, face: int, is_magic: bool, equipped: Optional[list[dict]]) -> Optional[QImage]:
    if not 0 <= race <= 7:
        return None
    try:
        pixels, palette, width, height = body_composite.build_body_image(race=race, is_female=is_female, face_idx=face, is_magic_class=is_magic, equipped_items=equipped)
    except Exception:
        _log.debug('charsheet body build failed', exc_info=True)
        return None
    return _scale(_to_qimage(pixels, palette, width, height, transparent_zero=False))

def _int(values: dict, key: str) -> Optional[int]:
    try:
        return int(values.get(key, ''))
    except (TypeError, ValueError):
        return None

def _number(value, default: int=-1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def equipment_key(equipped: Optional[Iterable[dict]]) -> tuple:
    if not equipped:
        return ()
    return tuple(sorted(((str(item.get('item_type')), _number(item.get('slot_id')), _number(item.get('hands'), 0), _number(item.get('armor_material_id'))) for item in equipped if item.get('equipped'))))

class SheetImages:

    def __init__(self) -> None:
        self._keys: dict[str, tuple] = {}
        self._images: dict[str, QImage] = {}
        self._versions: dict[str, int] = {'face': 0, 'body': 0}

    def update(self, values: dict, equipped: Optional[list[dict]]) -> None:
        race = _int(values, 'race_index')
        female = _int(values, 'is_female')
        face = _int(values, 'face_index')
        magic = values.get('is_magic') == '1'
        ready = race is not None and female is not None and (face is not None)
        face_key = (race, female, face) if ready else ()
        body_key = (race, female, face, magic, equipment_key(equipped)) if ready else ()
        if face_key != self._keys.get('face'):
            self._keys['face'] = face_key
            self._images['face'] = (build_face(race, bool(female), face) if ready else None) or blank(FACE_SIZE)
            self._versions['face'] += 1
        if body_key != self._keys.get('body'):
            self._keys['body'] = body_key
            self._images['body'] = (build_body(race, bool(female), face, magic, equipped) if ready else None) or blank(BODY_SIZE)
            self._versions['body'] += 1

    def urls(self) -> dict[str, str]:
        return {name: f'charsheet:{name}?v={self._versions[name]}' for name in self._versions}

    def image(self, name: str) -> Optional[QImage]:
        if name not in self._images:
            self._images[name] = blank(FACE_SIZE if name == 'face' else BODY_SIZE)
        return self._images.get(name)
__all__ = ['SCALE_X', 'SCALE_Y', 'FACE_SIZE', 'BODY_SIZE', 'SheetImages', 'build_face', 'build_body', 'blank', 'scaled_size', 'equipment_key']
