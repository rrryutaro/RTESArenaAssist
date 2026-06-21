from __future__ import annotations

import os
import struct

from cif_decoder import _decode_type04, _decode_type08

_RAW_IMG_OVERRIDE = {
    "ARENARW.IMG":  (16, 16),
    "CITY.IMG":     (16, 11),
    "DITHER.IMG":   (8, 100),
    "DITHER2.IMG":  (8, 100),
    "DUNGEON.IMG":  (14, 8),
    "DZTTAV.IMG":   (32, 34),
    "NOCAMP.IMG":   (25, 19),
    "NOSPELL.IMG":  (25, 19),
    "P1.IMG":       (320, 53),
    "POPTALK.IMG":  (320, 77),
    "S2.IMG":       (320, 36),
    "SLIDER.IMG":   (289, 7),
    "TOWN.IMG":     (9, 10),
    "UPDOWN.IMG":   (8, 16),
    "VILLAGE.IMG":  (8, 8),
}


def decode_img(img_path: str) -> tuple[int, int, bytes, list[tuple[int, int, int]] | None]:
    with open(img_path, "rb") as f:
        data = f.read()

    filename = os.path.basename(img_path).upper()

    if filename in _RAW_IMG_OVERRIDE:
        w, h = _RAW_IMG_OVERRIDE[filename]
        return w, h, data[:w * h], None

    if len(data) == 4096:
        return 64, 64, data, None

    if len(data) < 12:
        raise ValueError(f"IMG too short: {img_path}")

    x_off = data[0] | (data[1] << 8)
    y_off = data[2] | (data[3] << 8)
    width  = data[4] | (data[5] << 8)
    height = data[6] | (data[7] << 8)
    flags  = data[8] | (data[9] << 8)
    length = data[10] | (data[11] << 8)

    compression = flags & 0x00FF
    has_palette = (flags & 0x0100) != 0
    out_size = width * height

    payload_start = 12
    payload_end   = 12 + length

    if compression == 0x00:
        pixels = data[payload_start:payload_start + out_size]
    elif compression == 0x04:
        pixels = _decode_type04(data[payload_start:payload_end], out_size)
    elif compression == 0x08:
        pixels = _decode_type08(data[payload_start + 2:payload_end], out_size)
    else:
        raise ValueError(
            f"unknown IMG compression: flags=0x{flags:04X} ({img_path})")

    embedded_palette = None
    if has_palette:
        pal_data = data[payload_end:payload_end + 768]
        if len(pal_data) == 768:
            embedded_palette = []
            for i in range(256):
                r = min(pal_data[i * 3 + 0], 63) * 255 // 63
                g = min(pal_data[i * 3 + 1], 63) * 255 // 63
                b = min(pal_data[i * 3 + 2], 63) * 255 // 63
                embedded_palette.append((r, g, b))

    return width, height, bytes(pixels), embedded_palette
