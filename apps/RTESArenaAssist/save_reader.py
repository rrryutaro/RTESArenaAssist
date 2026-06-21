"""
save_reader.py — Arena セーブスロット情報読み取り（ベストエフォート）

■ 解析結果まとめ (OpenTESArena Wiki / GameSAS Forum 調査)
  - SAVEGAME.NN / SAVEENGN.NN : XOR ローテーション暗号化 → 直接解析不可
  - NAMES.DAT                  : 非暗号化テキスト / 48バイト×スロット数
                                  offset = slot * 48 でスロット表示名を取得可能
  - 最終更新日時               : OS のファイル更新日時から取得（信頼性高）
"""

import os
import re
from datetime import datetime

# NAMES.DAT: 1スロット当たり 48 バイト (ASCII, null-terminated)
_NAMES_SLOT_SIZE = 48


def read_slot_info(game_dir: str, slot: int) -> dict:
    """
    指定スロットの基本情報を返す（ベストエフォート）。

    Returns
    -------
    dict with keys:
        slot       : int
        save_name  : str | None   — NAMES.DAT から読み取り（セーブスロット表示名）
        modified   : str | None   — "YYYY-MM-DD HH:MM"
        file_count : int
    """
    result: dict = {
        "slot":       slot,
        "save_name":  None,
        "modified":   None,
        "file_count": 0,
    }

    if not os.path.isdir(game_dir):
        return result

    # スロットファイル一覧 (.0N 形式)
    ext_re = re.compile(rf'\.0{slot}$', re.IGNORECASE)
    try:
        slot_files = [f for f in os.listdir(game_dir) if ext_re.search(f)]
    except OSError:
        return result

    result["file_count"] = len(slot_files)

    # 最終更新日時: SAVEENGN.0N → SAVEGAME.0N → その他スロットファイル
    mtime_path = (
        _find_file(game_dir, "SAVEENGN", slot)
        or _find_file(game_dir, "SAVEGAME", slot)
        or (os.path.join(game_dir, slot_files[0]) if slot_files else None)
    )
    if mtime_path:
        try:
            mtime = os.path.getmtime(mtime_path)
            result["modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            pass

    # セーブスロット表示名: NAMES.DAT (非暗号化)
    result["save_name"] = read_save_name(game_dir, slot)

    return result


def _find_file(game_dir: str, prefix: str, slot: int) -> str | None:
    """<prefix>.0<slot> のファイルパスを大文字小文字問わず返す。"""
    target = f"{prefix}.0{slot}".upper()
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == target:
                return os.path.join(game_dir, fname)
    except OSError:
        pass
    return None


def read_save_name(game_dir: str, slot: int) -> str | None:
    """
    NAMES.DAT からセーブスロット表示名を読み取る。

    NAMES.DAT 構造:
      各スロットの表示名が _NAMES_SLOT_SIZE バイトずつ格納。
      null-terminated ASCII。スロット N の名前は offset = N * _NAMES_SLOT_SIZE。
    """
    names_path = None
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == "NAMES.DAT":
                names_path = os.path.join(game_dir, fname)
                break
    except OSError:
        return None

    if not names_path:
        return None

    try:
        with open(names_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    offset = slot * _NAMES_SLOT_SIZE
    if offset + _NAMES_SLOT_SIZE > len(data):
        return None

    chunk = data[offset : offset + _NAMES_SLOT_SIZE]
    null_idx = chunk.find(b"\x00")
    if null_idx <= 0:
        return None

    raw = chunk[:null_idx]
    if len(raw) < 2:
        return None

    # 印字可能 ASCII (0x20–0x7E) のみ許可
    if not all(0x20 <= b <= 0x7E for b in raw):
        return None

    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def write_save_name(game_dir: str, slot: int, name: str) -> bool:
    """
    NAMES.DAT の指定スロット表示名を書き換える。

    1 スロットの 48 バイト領域全体を name (ASCII) + null + 0x00 詰めで上書きする。
    NAMES.DAT が存在しない / slot が範囲外の場合は False を返す。
    """
    names_path = None
    try:
        for fname in os.listdir(game_dir):
            if fname.upper() == "NAMES.DAT":
                names_path = os.path.join(game_dir, fname)
                break
    except OSError:
        return False

    if not names_path:
        return False

    try:
        with open(names_path, "rb") as f:
            data = bytearray(f.read())
    except OSError:
        return False

    offset = slot * _NAMES_SLOT_SIZE
    if offset + _NAMES_SLOT_SIZE > len(data):
        return False

    # name を ASCII 印字可能範囲に限定し、最大 _NAMES_SLOT_SIZE - 1 バイトに切り詰める
    encoded = bytearray()
    for ch in name:
        b = ord(ch)
        if 0x20 <= b <= 0x7E:
            encoded.append(b)
        if len(encoded) >= _NAMES_SLOT_SIZE - 1:
            break

    chunk = bytearray(_NAMES_SLOT_SIZE)
    chunk[: len(encoded)] = encoded
    data[offset : offset + _NAMES_SLOT_SIZE] = chunk

    try:
        with open(names_path, "wb") as f:
            f.write(bytes(data))
    except OSError:
        return False

    return True
