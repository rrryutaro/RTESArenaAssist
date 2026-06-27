from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
from runtime_paths import resolve_arena_data_dir, resolve_arena_install_dir
RMD_WIDTH = 64
RMD_DEPTH = 64
RMD_BYTES_PER_FLOOR = RMD_WIDTH * RMD_DEPTH * 2
RMD_UNCOMPRESSED_SIZE = RMD_BYTES_PER_FLOOR * 3
DEFAULT_RMD_DIR = resolve_arena_data_dir() / 'RMD'

@dataclass(frozen=True)
class RmdChunk:
    flor: np.ndarray
    map1: np.ndarray
    map2: np.ndarray

def _decode_rle_words(src: bytes, stop_count: int) -> bytes:
    out = bytearray(stop_count * 2)
    i = 0
    o = 0
    src_len = len(src)
    while o < stop_count:
        if i + 2 > src_len:
            raise ValueError(f'RLE words: src underrun at i={i}')
        sample = int.from_bytes(src[i:i + 2], 'little', signed=True)
        i += 2
        if sample > 0:
            need = sample * 2
            if i + need > src_len:
                raise ValueError(f'RLE words: literal underrun (need={need})')
            end = o + sample
            if end > stop_count:
                raise ValueError(f'RLE words: literal overrun (o={o} end={end})')
            out[o * 2:end * 2] = src[i:i + need]
            i += need
            o = end
        else:
            if i + 2 > src_len:
                raise ValueError('RLE words: repeat value underrun')
            count = -sample
            value = src[i:i + 2]
            i += 2
            end = o + count
            if end > stop_count:
                raise ValueError(f'RLE words: repeat overrun (o={o} end={end})')
            for j in range(o, end):
                out[j * 2:j * 2 + 2] = value
            o = end
    return bytes(out)

def parse_rmd_bytes(data: bytes) -> RmdChunk:
    if len(data) < 2:
        raise ValueError('RMD too short')
    uncomp_len = int.from_bytes(data[:2], 'little')
    if uncomp_len == 0:
        if len(data) != RMD_UNCOMPRESSED_SIZE:
            raise ValueError(f'RMD uncompressed size mismatch: {len(data)} != {RMD_UNCOMPRESSED_SIZE}')
        body = data
    else:
        body = _decode_rle_words(data[2:], uncomp_len)
        if len(body) != uncomp_len * 2:
            raise ValueError(f'RMD decompressed size mismatch: {len(body)} != {uncomp_len * 2}')
    if len(body) < RMD_UNCOMPRESSED_SIZE:
        raise ValueError(f'RMD body too short: {len(body)} < {RMD_UNCOMPRESSED_SIZE}')
    floor_size = RMD_BYTES_PER_FLOOR
    flor = np.frombuffer(body[0:floor_size], dtype=np.uint16).reshape(RMD_DEPTH, RMD_WIDTH).copy()
    map1 = np.frombuffer(body[floor_size:2 * floor_size], dtype=np.uint16).reshape(RMD_DEPTH, RMD_WIDTH).copy()
    map2 = np.frombuffer(body[2 * floor_size:3 * floor_size], dtype=np.uint16).reshape(RMD_DEPTH, RMD_WIDTH).copy()
    return RmdChunk(flor=flor, map1=map1, map2=map2)

def parse_rmd_file(path: str | Path) -> RmdChunk:
    return parse_rmd_bytes(Path(path).read_bytes())

def resolve_rmd_path(wild_block_id: int, steam_dir: Path | None=None, fallback_dir: Path=DEFAULT_RMD_DIR) -> Optional[Path]:
    if wild_block_id <= 0:
        return None
    if steam_dir is None:
        steam_dir = resolve_arena_install_dir()
    filename = f'WILD{wild_block_id:03d}.RMD'
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

def load_rmd_chunk(wild_block_id: int, steam_dir: Path | None=None, fallback_dir: Path=DEFAULT_RMD_DIR) -> Optional[RmdChunk]:
    path = resolve_rmd_path(wild_block_id, steam_dir, fallback_dir)
    if path is not None:
        try:
            return parse_rmd_file(path)
        except (OSError, ValueError):
            return None
    if wild_block_id <= 0:
        return None
    from runtime_paths import install_vfs
    vfs = install_vfs()
    if vfs is not None:
        data = vfs.read(f'WILD{wild_block_id:03d}.RMD')
        if data is not None:
            try:
                return parse_rmd_bytes(data)
            except (OSError, ValueError):
                return None
    return None
__all__ = ['RmdChunk', 'RMD_WIDTH', 'RMD_DEPTH', 'RMD_BYTES_PER_FLOOR', 'RMD_UNCOMPRESSED_SIZE', 'DEFAULT_RMD_DIR', 'parse_rmd_bytes', 'parse_rmd_file', 'resolve_rmd_path', 'load_rmd_chunk']
