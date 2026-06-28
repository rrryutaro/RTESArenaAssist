from __future__ import annotations
from cif_decoder import decode_cif_frames_with_offsets_bytes, load_col_bytes
from img_decoder import decode_img_bytes
W, H = (320, 200)
BODY_X = 170
BODY_Y = 0
BODY_W = 150
BODY_H = 200
_EQUIP_Z: dict[str, int] = {'armor': 10, 'shield': 20, 'weapon': 30}
_ARMOR_FRAME_BASE: dict[int, int] = {2: 18, 1: 29, 0: 36}

def _equip_frame_index(item: dict) -> int | None:
    item_type = item.get('item_type', '')
    if item_type not in ('weapon', 'armor', 'shield'):
        return None
    hands = item.get('hands', 0)
    slot_id = item.get('slot_id', 0)
    if item_type == 'weapon' and hands in (1, 2) and (0 <= slot_id <= 17):
        return slot_id
    if item_type == 'shield' and 7 <= slot_id <= 10:
        return slot_id + 18
    if item_type == 'armor' and 0 <= slot_id <= 6:
        mat = item.get('armor_material_id', 2)
        base = _ARMOR_FRAME_BASE.get(mat, 18)
        return slot_id + base
    return None

def _equip_render_priority(item: dict) -> int:
    return _EQUIP_Z.get(item.get('item_type', ''), 99)

def _read_asset_bytes(name: str) -> bytes | None:
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            return vfs.read(name)
    except Exception:
        pass
    return None

def _require_asset_bytes(name: str) -> bytes:
    data = _read_asset_bytes(name)
    if data is None:
        raise FileNotFoundError(name)
    return data

def _img_with_header(filename: str) -> tuple[int, int, int, int, bytes]:
    data = _require_asset_bytes(filename)
    x_off = data[0] | data[1] << 8
    y_off = data[2] | data[3] << 8
    w, h, pixels, _pal = decode_img_bytes(data, filename)
    return (w, h, x_off, y_off, pixels)

def _blit(dst: bytearray, dst_w: int, dst_h: int, src: bytes, src_w: int, src_h: int, x: int, y: int, transparent: int=0) -> None:
    for sy in range(src_h):
        dy = y + sy
        if dy < 0 or dy >= dst_h:
            continue
        for sx in range(src_w):
            dx = x + sx
            if dx < 0 or dx >= dst_w:
                continue
            p = src[sy * src_w + sx]
            if p == transparent:
                continue
            dst[dy * dst_w + dx] = p

def build_status_composite(race: int, is_female: bool, face_idx: int, is_magic_class: bool=False, equipped_items: list[dict] | None=None) -> tuple[bytes, list[tuple[int, int, int]]]:
    prefix_bk = 'CHRBKF' if is_female else 'CHARBK'
    bk_name = f'{prefix_bk}0{race}.IMG'
    bk_w, bk_h, bk_pix, bk_pal = decode_img_bytes(_require_asset_bytes(bk_name), bk_name)
    assert bk_w == W and bk_h == H, f'unexpected CHARBK size {bk_w}×{bk_h}'
    canvas = bytearray(bk_pix)
    palette = bk_pal if bk_pal else load_col_bytes(_require_asset_bytes('CHARSHT.COL'))
    head_name = f"FACES{('F' if is_female else '')}1{race}.CIF"
    head_data = _read_asset_bytes(head_name)
    if head_data is not None:
        head_frames = decode_cif_frames_with_offsets_bytes(head_data)
        if 0 <= face_idx < len(head_frames):
            hw, hh, hx, hy, hp = head_frames[face_idx]
            _blit(canvas, W, H, hp, hw, hh, hx, hy)
    p_name = 'FPANTS.IMG' if is_female else 'MPANTS.IMG'
    pw, ph, px, py, pp = _img_with_header(p_name)
    _blit(canvas, W, H, pp, pw, ph, px, py)
    if is_female:
        s_name = 'FRSHIRT.IMG' if is_magic_class else 'FSSHIRT.IMG'
    else:
        s_name = 'MRSHIRT.IMG' if is_magic_class else 'MSSHIRT.IMG'
    sw, sh, sx, sy, sp = _img_with_header(s_name)
    _blit(canvas, W, H, sp, sw, sh, sx, sy)
    if equipped_items:
        equip_name = '1EQUIP.CIF' if is_female else '0EQUIP.CIF'
        equip_data = _read_asset_bytes(equip_name)
        if equip_data is not None:
            equip_frames = decode_cif_frames_with_offsets_bytes(equip_data)
            sorted_items = sorted((it for it in equipped_items if it.get('equipped')), key=_equip_render_priority)
            for item in sorted_items:
                frame_idx = _equip_frame_index(item)
                if frame_idx is None or frame_idx >= len(equip_frames):
                    continue
                ew, eh, ex, ey, ep = equip_frames[frame_idx]
                _blit(canvas, W, H, ep, ew, eh, ex, ey)
    return (bytes(canvas), palette)

def build_body_image(race: int, is_female: bool, face_idx: int, is_magic_class: bool=False, equipped_items: list[dict] | None=None) -> tuple[bytes, list[tuple[int, int, int]], int, int]:
    full_pixels, palette = build_status_composite(race, is_female, face_idx, is_magic_class, equipped_items)
    cropped = bytearray(BODY_W * BODY_H)
    for y in range(BODY_H):
        src_off = (BODY_Y + y) * W + BODY_X
        dst_off = y * BODY_W
        cropped[dst_off:dst_off + BODY_W] = full_pixels[src_off:src_off + BODY_W]
    return (bytes(cropped), palette, BODY_W, BODY_H)

def composite_to_png_bytes(pixels: bytes, palette: list[tuple[int, int, int]]) -> bytes:
    import struct, zlib
    rgba = bytearray(W * H * 4)
    for i, p in enumerate(pixels):
        r, g, b = palette[p]
        rgba[i * 4:i * 4 + 4] = bytes((r, g, b, 255))

    def chunk(tag, payload):
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload) & 4294967295)
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += rgba[y * W * 4:(y + 1) * W * 4]
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(bytes(raw))) + chunk(b'IEND', b'')
