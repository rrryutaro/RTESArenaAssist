from __future__ import annotations
from functools import lru_cache
import logging
from arena_vfs import BsaError
from img_decoder import decode_img_bytes
from runtime_paths import install_vfs
from screen_detector import SCREEN_BUFFER_OFFSET, SCREEN_ROW_BYTES
PATCH_SIZE = 32
MIN_MATCH = 0.95
_log = logging.getLogger('RTESArenaAssist')

@lru_cache(maxsize=2)
def _reference_patch(vfs) -> bytes | None:
    if vfs is None:
        _log.warning('system menu visual: Arena VFS unavailable')
        return None
    try:
        raw = vfs.read('OP.IMG')
        if raw is None:
            _log.warning('system menu visual: OP.IMG unavailable')
            return None
        width, height, pixels, _ = decode_img_bytes(raw, 'OP.IMG')
        if width != SCREEN_ROW_BYTES or height < PATCH_SIZE or len(pixels) < width * height:
            _log.warning('system menu visual: OP.IMG has invalid dimensions')
            return None
        return b''.join((pixels[row * width:row * width + PATCH_SIZE] for row in range(PATCH_SIZE)))
    except (OSError, ValueError, IndexError, TypeError, BsaError):
        _log.exception('system menu visual: failed to load OP.IMG')
        return None

def _matches_patch(screen_rows: bytes, reference: bytes) -> bool:
    if not isinstance(screen_rows, (bytes, bytearray)) or len(screen_rows) != SCREEN_ROW_BYTES * PATCH_SIZE or len(reference) != PATCH_SIZE * PATCH_SIZE:
        return False
    matched = sum((actual == expected for row in range(PATCH_SIZE) for actual, expected in zip(screen_rows[row * SCREEN_ROW_BYTES:row * SCREEN_ROW_BYTES + PATCH_SIZE], reference[row * PATCH_SIZE:(row + 1) * PATCH_SIZE])))
    return matched >= PATCH_SIZE * PATCH_SIZE * MIN_MATCH

def system_menu_art_visible(analyzer, anchor: int) -> bool:
    reference = _reference_patch(install_vfs())
    if reference is None:
        return False
    try:
        rows = analyzer.read_bytes(anchor + SCREEN_BUFFER_OFFSET, SCREEN_ROW_BYTES * PATCH_SIZE)
    except (OSError, ValueError, IndexError, TypeError, AttributeError):
        return False
    return _matches_patch(rows, reference)
