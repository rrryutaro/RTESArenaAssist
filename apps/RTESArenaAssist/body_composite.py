"""body_composite.py — ステータス画面の全身図合成（320×200）を生成する。

レイアウト（OpenTESArena CharacterSheetUiMVC.cpp / ArenaPortraitUtils.cpp 準拠）:

  base       : CHARBK0{race}.IMG (male) / CHRBKF0{race}.IMG (female)
               320×200、埋込パレット付き
  body       : (BODY06.IMG / DEADBODY.IMG など特殊 race のみ、通常は base に
               含まれているので不要)
  pants      : MPANTS.IMG / FPANTS.IMG
  shirt      : MRSHIRT.IMG (magic) / MSSHIRT.IMG (non-magic) / FRSHIRT / FSSHIRT
               class 定義の castsMagic で切替（簡易版では non-magic 固定）
  head       : FACES{F?}1{race}.CIF frame[face_idx]
               各フレームに x/y オフセットが埋め込み済み（CIFFile.cpp 準拠）

各 IMG の x/y オフセットはファイルヘッダー、CIF の x/y オフセットは
各フレームヘッダーから読み取る（OpenTESArena getShirtOffset 等は
ハードコード冗長で IMG ヘッダー値と一致）。
"""
from __future__ import annotations

import os

from cif_decoder import decode_cif_frames_with_offsets, load_col
from img_decoder import decode_img

_HERE          = os.path.dirname(os.path.abspath(__file__))
_CIF_DIR       = os.path.normpath(os.path.join(_HERE, "..", "..", "docs", "ARENA-data", "CIF"))
_OTHER_CIF_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "docs", "ARENA-data", "Other", "CIF"))
_IMG_DIR       = os.path.normpath(os.path.join(_HERE, "..", "..", "docs", "ARENA-data", "IMG"))
_CHAR_COL      = os.path.normpath(os.path.join(_HERE, "..", "..", "docs", "ARENA-data", "Other", "CHARSHT.COL"))

W, H = 320, 200

# 全身像のキャンバス内 bbox。CHARBK0{race}.IMG / CHRBKF0{race}.IMG の
# 非透過ピクセル領域を全 8 種族 × 2 性別で確認した最大外接矩形。
# pants/shirt/face のオフセット (IMG/CIF ヘッダー埋込) もこの bbox 内に収まる。
# ステータス画面のうち全身像「だけ」を切り出す用途に使う (build_body_image)。
BODY_X = 170
BODY_Y = 0
BODY_W = 150
BODY_H = 200

# EQUIP.CIF フレーム番号マッピング
# 武器 (weapon, hands=1/2): slot_id 0-17 → frame slot_id
# 防具 (armor, hands=0, slot 0-6):
#   Plate  (armor_material_id=2): frame = slot_id + 18  (frames 18-24)
#   Chain  (armor_material_id=1): frame = slot_id + 29  (frames 29-35)
#   Leather(armor_material_id=0): frame = slot_id + 36  (frames 36-42)
# 盾 (shield, hands=0, slot 7-10): frame = slot_id + 18 (frames 25-28)
# アクセサリ・スペルキャスティング: EQUIP.CIF フレームなし → None

# 描画 Z オーダー優先度（小さいほど先に描画 = 奥側）
_EQUIP_Z: dict[str, int] = {
    "armor":  10,   # Cuirass / Gauntlets / Greaves / Pauldrons / Helm / Boots
    "shield": 20,   # Buckler / Round Shield / Kite / Tower
    "weapon": 30,   # 武器全種
}

# armor_material_id → EQUIP.CIF フレームセット基底インデックス
_ARMOR_FRAME_BASE: dict[int, int] = {
    2: 18,  # Plate
    1: 29,  # Chain
    0: 36,  # Leather
}


def _equip_frame_index(item: dict) -> int | None:
    """装備アイテムの EQUIP.CIF フレーム番号を返す。対応なし=None。

    アクセサリ・スペルキャスティングは EQUIP.CIF に視覚表現がないため None。
    防具は素材種別（Plate/Chain/Leather）に応じてフレームセットを選択する。
    """
    item_type = item.get("item_type", "")
    if item_type not in ("weapon", "armor", "shield"):
        return None
    hands   = item.get("hands", 0)
    slot_id = item.get("slot_id", 0)
    if item_type == "weapon" and hands in (1, 2) and 0 <= slot_id <= 17:
        return slot_id
    if item_type == "shield" and 7 <= slot_id <= 10:
        return slot_id + 18  # Buckler(7)→25, Round(8)→26, Kite(9)→27, Tower(10)→28
    if item_type == "armor" and 0 <= slot_id <= 6:
        mat = item.get("armor_material_id", 2)
        base = _ARMOR_FRAME_BASE.get(mat, 18)
        return slot_id + base
    return None


def _equip_render_priority(item: dict) -> int:
    """描画優先度 (小=奥、大=手前)。item_type が不明なら最後。"""
    return _EQUIP_Z.get(item.get("item_type", ""), 99)


def _img_with_header(filename: str) -> tuple[int, int, int, int, bytes]:
    """IMG のヘッダー xOffset/yOffset を保ったまま (w, h, x, y, pixels) を返す。"""
    path = os.path.join(_IMG_DIR, filename)
    with open(path, "rb") as f:
        data = f.read()
    x_off  = data[0] | (data[1] << 8)
    y_off  = data[2] | (data[3] << 8)
    w, h, pixels, _pal = decode_img(path)
    return w, h, x_off, y_off, pixels


def _blit(dst: bytearray, dst_w: int, dst_h: int,
          src: bytes, src_w: int, src_h: int,
          x: int, y: int, transparent: int = 0) -> None:
    """src を dst に (x, y) で alpha=transparent_index で blit。"""
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


def build_status_composite(race: int, is_female: bool, face_idx: int,
                           is_magic_class: bool = False,
                           equipped_items: list[dict] | None = None,
                           ) -> tuple[bytes, list[tuple[int, int, int]]]:
    """指定キャラクターのステータス画面 320×200 合成画像を作る。

    戻り値: (palette-indexed pixels 64000B, palette 256色)
    パレットは CHARBK の埋込パレット（CHARSHT.COL と等価のはず）を使う。
    equipped_items: inventory_reader.read_equipment_items() の戻り値（equipped=True のみ使用）
    """
    # 描画順は OpenTESArena ChooseAttributesUiState / CharacterEquipmentUiState
    # の drawOrder 仕様に合わせる:
    #   0: 背景 (body silhouette = CHARBK)
    #   1: 顔 (head)        ← シャツより前に描画
    #   2: ズボン (pants)
    #   3: シャツ (shirt)   ← 最後に描画、襟元が顔の首/襟領域を覆う
    #   (装備品は最前面に追加)

    # 1) base: CHARBK / CHRBKF
    prefix_bk = "CHRBKF" if is_female else "CHARBK"
    bk_path = os.path.join(_IMG_DIR, f"{prefix_bk}0{race}.IMG")
    bk_w, bk_h, bk_pix, bk_pal = decode_img(bk_path)
    assert bk_w == W and bk_h == H, f"unexpected CHARBK size {bk_w}×{bk_h}"
    canvas = bytearray(bk_pix)
    palette = bk_pal if bk_pal else load_col(_CHAR_COL)

    # 2) head: FACES{F?}1{race}.CIF frame[face_idx]
    # ChooseAttributesUiState.drawOrder = 1 (body の直後、pants/shirt より前)
    head_cif = os.path.join(_CIF_DIR,
                            f"FACES{'F' if is_female else ''}1{race}.CIF")
    if os.path.isfile(head_cif):
        head_frames = decode_cif_frames_with_offsets(head_cif)
        if 0 <= face_idx < len(head_frames):
            hw, hh, hx, hy, hp = head_frames[face_idx]
            _blit(canvas, W, H, hp, hw, hh, hx, hy)

    # 3) pants
    p_name = "FPANTS.IMG" if is_female else "MPANTS.IMG"
    pw, ph, px, py, pp = _img_with_header(p_name)
    _blit(canvas, W, H, pp, pw, ph, px, py)

    # 4) shirt（class が magic なら *RSHIRT, それ以外は *SSHIRT を使う）
    # 注: OpenTESArena getShirtOffset(male, magic) と IMG ヘッダー値が一致
    # shirt は最後に描画され、襟元が顔の下端を自然に覆う
    if is_female:
        s_name = "FRSHIRT.IMG" if is_magic_class else "FSSHIRT.IMG"
    else:
        s_name = "MRSHIRT.IMG" if is_magic_class else "MSSHIRT.IMG"
    sw, sh, sx, sy, sp = _img_with_header(s_name)
    _blit(canvas, W, H, sp, sw, sh, sx, sy)

    # 5) equipment overlay: 0EQUIP.CIF (male) / 1EQUIP.CIF (female)
    # 装備品 (armor / shield / weapon) は最前面に追加。
    # 描画順内訳: armor(防具) → shield(盾) → weapon(武器)
    if equipped_items:
        equip_cif = (os.path.join(_CIF_DIR, "1EQUIP.CIF") if is_female
                     else os.path.join(_OTHER_CIF_DIR, "0EQUIP.CIF"))
        if os.path.isfile(equip_cif):
            equip_frames = decode_cif_frames_with_offsets(equip_cif)
            sorted_items = sorted(
                (it for it in equipped_items if it.get("equipped")),
                key=_equip_render_priority,
            )
            for item in sorted_items:
                frame_idx = _equip_frame_index(item)
                if frame_idx is None or frame_idx >= len(equip_frames):
                    continue
                ew, eh, ex, ey, ep = equip_frames[frame_idx]
                _blit(canvas, W, H, ep, ew, eh, ex, ey)

    return bytes(canvas), palette


def build_body_image(race: int, is_female: bool, face_idx: int,
                     is_magic_class: bool = False,
                     equipped_items: list[dict] | None = None,
                     ) -> tuple[bytes, list[tuple[int, int, int]], int, int]:
    """ステータス画面合成のうち、全身像 (BODY_W × BODY_H) のみを切り出して返す。

    build_status_composite は 320×200 のキャラクターシート全体を生成するが、
    左半分 (x < BODY_X) はステータス表示領域 (この関数の呼び出し元側で別 UI
    として描画する想定) であり、ここでは空 (palette idx 0 = 黒) になる。
    appearance 選択画面など「全身像だけが欲しい」ユースケース用にトリミング版
    を提供する。

    戻り値: (pixels BODY_W*BODY_H, palette, BODY_W, BODY_H)
    """
    full_pixels, palette = build_status_composite(
        race, is_female, face_idx, is_magic_class, equipped_items)
    cropped = bytearray(BODY_W * BODY_H)
    for y in range(BODY_H):
        src_off = (BODY_Y + y) * W + BODY_X
        dst_off = y * BODY_W
        cropped[dst_off:dst_off + BODY_W] = full_pixels[
            src_off:src_off + BODY_W]
    return bytes(cropped), palette, BODY_W, BODY_H


def composite_to_png_bytes(pixels: bytes, palette: list[tuple[int, int, int]]) -> bytes:
    """64000B のパレットインデックスから 320×200 PNG バイト列を生成。"""
    import struct, zlib
    rgba = bytearray(W * H * 4)
    for i, p in enumerate(pixels):
        r, g, b = palette[p]
        rgba[i * 4:i * 4 + 4] = bytes((r, g, b, 255))
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += rgba[y * W * 4:(y + 1) * W * 4]
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(bytes(raw)))
            + chunk(b'IEND', b''))
