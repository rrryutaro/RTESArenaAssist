"""rmd_loader.py — Arena wilderness chunk (RMD) parser。

OpenTESArena `Assets/RMDFile.cpp` + `Assets/Compression.cpp::decodeRLEWords`
を Python 移植。

RMD ファイル構造:
  - 先頭 2 byte: uncompLen (LE16)
    - == 0 → 非圧縮、ファイル全体 24576 byte (= 8192 × 3 = 64*64*2 × 3 floors)
    - != 0 → RLE word 圧縮、展開後 uncompLen × 2 byte (= ファイル末尾まで圧縮データ)
  - 展開後構成: FLOR (8192 byte) + MAP1 (8192 byte) + MAP2 (8192 byte)
  - 各 floor は 64×64 個の uint16 (LE) voxel ID

WILD001-004.RMD は街中央 4 chunks 用 (= Arena が街 MIF 変換結果を動的に書き出す、
Arena インストールフォルダ側を参照)。WILD005-070.RMD は静的 default
(= ローカルの RMD データディレクトリ配下)。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from runtime_paths import resolve_arena_data_dir, resolve_arena_install_dir


RMD_WIDTH = 64
RMD_DEPTH = 64
RMD_BYTES_PER_FLOOR = RMD_WIDTH * RMD_DEPTH * 2  # 8192
RMD_UNCOMPRESSED_SIZE = RMD_BYTES_PER_FLOOR * 3  # 24576

# RMD 探索パス。優先順:
#   1. ユーザー Arena インストール先 (= 街中央 4 chunks WILD001-004.RMD が動的書き出し)
#      ＝設定 save_dir から実行時解決（ハードコード絶対パスは使わない）。
#   2. ローカルの RMD データディレクトリ (= WILD005-070.RMD の静的 default)
DEFAULT_RMD_DIR = resolve_arena_data_dir() / "RMD"


@dataclass(frozen=True)
class RmdChunk:
    """1 wilderness chunk (= 64×64 voxel × 3 floors)。"""
    flor: np.ndarray  # (64, 64) uint16
    map1: np.ndarray  # (64, 64) uint16
    map2: np.ndarray  # (64, 64) uint16


def _decode_rle_words(src: bytes, stop_count: int) -> bytes:
    """RLE word decompression (= OpenTESArena Compression::decodeRLEWords)。

    src の先頭から int16 (LE) sample を読む:
      - sample > 0 → 直後の sample 個 word をリテラルとして出力
      - sample <= 0 → 直後の 1 word を |sample| 回繰り返し出力

    stop_count word 数だけ出力したら終了。戻り値は stop_count*2 byte。
    """
    out = bytearray(stop_count * 2)
    i = 0
    o = 0  # 出力した word 数
    src_len = len(src)
    while o < stop_count:
        if i + 2 > src_len:
            raise ValueError(f"RLE words: src underrun at i={i}")
        # sample は signed 16-bit LE
        sample = int.from_bytes(src[i:i + 2], "little", signed=True)
        i += 2
        if sample > 0:
            need = sample * 2
            if i + need > src_len:
                raise ValueError(f"RLE words: literal underrun (need={need})")
            end = o + sample
            if end > stop_count:
                raise ValueError(f"RLE words: literal overrun (o={o} end={end})")
            out[o * 2:end * 2] = src[i:i + need]
            i += need
            o = end
        else:
            if i + 2 > src_len:
                raise ValueError("RLE words: repeat value underrun")
            count = -sample
            value = src[i:i + 2]
            i += 2
            end = o + count
            if end > stop_count:
                raise ValueError(f"RLE words: repeat overrun (o={o} end={end})")
            for j in range(o, end):
                out[j * 2:j * 2 + 2] = value
            o = end
    return bytes(out)


def parse_rmd_bytes(data: bytes) -> RmdChunk:
    """RMD ファイル bytes を parse して RmdChunk を返す。"""
    if len(data) < 2:
        raise ValueError("RMD too short")
    uncomp_len = int.from_bytes(data[:2], "little")
    if uncomp_len == 0:
        # 非圧縮 (= WILD001-004.RMD の old default 形式想定)
        if len(data) != RMD_UNCOMPRESSED_SIZE:
            raise ValueError(
                f"RMD uncompressed size mismatch: {len(data)} != "
                f"{RMD_UNCOMPRESSED_SIZE}")
        body = data
    else:
        # RLE words 圧縮。stop_count = uncomp_len word
        body = _decode_rle_words(data[2:], uncomp_len)
        if len(body) != uncomp_len * 2:
            raise ValueError(
                f"RMD decompressed size mismatch: {len(body)} != "
                f"{uncomp_len * 2}")

    if len(body) < RMD_UNCOMPRESSED_SIZE:
        raise ValueError(
            f"RMD body too short: {len(body)} < {RMD_UNCOMPRESSED_SIZE}")

    # FLOR / MAP1 / MAP2 を切り出して (64, 64) uint16 配列に
    floor_size = RMD_BYTES_PER_FLOOR
    flor = np.frombuffer(body[0:floor_size], dtype=np.uint16).reshape(
        RMD_DEPTH, RMD_WIDTH).copy()
    map1 = np.frombuffer(body[floor_size:2 * floor_size],
                         dtype=np.uint16).reshape(
        RMD_DEPTH, RMD_WIDTH).copy()
    map2 = np.frombuffer(body[2 * floor_size:3 * floor_size],
                         dtype=np.uint16).reshape(
        RMD_DEPTH, RMD_WIDTH).copy()
    return RmdChunk(flor=flor, map1=map1, map2=map2)


def parse_rmd_file(path: str | Path) -> RmdChunk:
    """RMD ファイルパスから RmdChunk を返す。"""
    return parse_rmd_bytes(Path(path).read_bytes())


def resolve_rmd_path(
    wild_block_id: int,
    steam_dir: Path | None = None,
    fallback_dir: Path = DEFAULT_RMD_DIR,
) -> Optional[Path]:
    """wild_block_id (1-70) → RMD ファイル絶対パス。

    探索順:
      1. wild_block_id 1-4 → ユーザー Arena インストール先 (= 動的書き出し、現在街専用)
      2. それ以外 + install にもなければローカルの RMD データディレクトリ (= 静的 default)

    `steam_dir` 未指定（None）なら設定 save_dir から実行時解決する。解決できなければ
    （公開版で save_dir 未設定等）その候補を飛ばす。見つからなければ None。
    """
    if wild_block_id <= 0:
        return None
    if steam_dir is None:
        steam_dir = resolve_arena_install_dir()
    filename = f"WILD{wild_block_id:03d}.RMD"
    candidates: list[Path] = []
    if 1 <= wild_block_id <= 4:
        if steam_dir is not None:
            candidates.append(steam_dir / filename)
        candidates.append(fallback_dir / filename)
    else:
        candidates.append(fallback_dir / filename)
        if steam_dir is not None:
            candidates.append(steam_dir / filename)
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def load_rmd_chunk(wild_block_id: int,
                   steam_dir: Path | None = None,
                   fallback_dir: Path = DEFAULT_RMD_DIR
                   ) -> Optional[RmdChunk]:
    """wild_block_id から RmdChunk をロード。失敗時 None。

    loose（install dir の WILD001-004 動的・ローカルの WILD005-070 静的）→ ユーザー Arena
    install の VFS（GLOBAL.BSA・RMD 非暗号）の順で解決する（公開版対応）。
    """
    path = resolve_rmd_path(wild_block_id, steam_dir, fallback_dir)
    if path is not None:
        try:
            return parse_rmd_file(path)
        except (OSError, ValueError):
            return None
    # loose 不在（公開版でローカル RMD データ非同梱等）→ GLOBAL.BSA から読む。
    if wild_block_id <= 0:
        return None
    from runtime_paths import install_vfs
    vfs = install_vfs()
    if vfs is not None:
        data = vfs.read(f"WILD{wild_block_id:03d}.RMD")
        if data is not None:
            try:
                return parse_rmd_bytes(data)
            except (OSError, ValueError):
                return None
    return None


__all__ = [
    "RmdChunk",
    "RMD_WIDTH", "RMD_DEPTH", "RMD_BYTES_PER_FLOOR", "RMD_UNCOMPRESSED_SIZE",
    "DEFAULT_RMD_DIR",
    "parse_rmd_bytes", "parse_rmd_file",
    "resolve_rmd_path", "load_rmd_chunk",
]
