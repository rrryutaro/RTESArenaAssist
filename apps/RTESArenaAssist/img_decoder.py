"""img_decoder.py — Arena .IMG ファイルデコーダー。

OpenTESArena `OpenTESArena/src/Assets/IMGFile.cpp` の移植版。
12B ヘッダー + flags 下位バイトで決まる圧縮方式（Type00/04/08）。
flags & 0x0100 で埋込パレット 768B が末尾に付く。

cif_decoder の _decode_type04 / _decode_type08 を共用する。
"""
from __future__ import annotations

import os
import struct

from cif_decoder import _decode_type04, _decode_type08

# OpenTESArena RawImgOverride（ヘッダーレスで寸法ハードコード）
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
    """IMG ファイルをデコードして (width, height, pixels, embedded_palette) を返す。

    pixels はパレットインデックスのバイト列 (width × height バイト)。
    embedded_palette は flags & 0x0100 のとき 256 色 RGB タプル、なければ None。
    """
    with open(img_path, "rb") as f:
        data = f.read()

    filename = os.path.basename(img_path).upper()

    # ヘッダーレス IMG（OpenTESArena RawImgOverride）
    if filename in _RAW_IMG_OVERRIDE:
        w, h = _RAW_IMG_OVERRIDE[filename]
        return w, h, data[:w * h], None

    # 4096 バイト固定 = 64×64 wall texture（ヘッダー無し、flags 値はガベージ）
    if len(data) == 4096:
        return 64, 64, data, None

    # 通常 IMG: 12B ヘッダー
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
        # 非圧縮（ヘッダー付き）
        pixels = data[payload_start:payload_start + out_size]
    elif compression == 0x04:
        pixels = _decode_type04(data[payload_start:payload_end], out_size)
    elif compression == 0x08:
        # Type08 は payload 先頭 2B が展開長プレフィックス、スキップ
        pixels = _decode_type08(data[payload_start + 2:payload_end], out_size)
    else:
        raise ValueError(
            f"unknown IMG compression: flags=0x{flags:04X} ({img_path})")

    embedded_palette = None
    if has_palette:
        # 末尾 768B が埋込パレット（VGA 6bit → 8bit 換算は呼出側で行う場合あり）
        pal_data = data[payload_end:payload_end + 768]
        if len(pal_data) == 768:
            # 0..63 を 0..255 へ拡張（IMGFile::readPalette 準拠）
            embedded_palette = []
            for i in range(256):
                r = min(pal_data[i * 3 + 0], 63) * 255 // 63
                g = min(pal_data[i * 3 + 1], 63) * 255 // 63
                b = min(pal_data[i * 3 + 2], 63) * 255 // 63
                embedded_palette.append((r, g, b))

    return width, height, bytes(pixels), embedded_palette
