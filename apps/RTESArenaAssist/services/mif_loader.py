
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import struct

from runtime_paths import resolve_arena_data_dir, resolve_arena_install_dir

DEFAULT_ARENA_DATA_DIR = resolve_arena_data_dir()
DEFAULT_MIF_DIR = DEFAULT_ARENA_DATA_DIR / "MIF"
DEFAULT_INF_DIR = DEFAULT_ARENA_DATA_DIR / "INF"
KNOWN_CHUNKS = {
    "FLAT", "FLOR", "INFO", "INNS", "LEVL", "LOCK", "LOOT", "MAP1", "MAP2",
    "MHDR", "NAME", "NUMF", "STOR", "TARG", "TRIG",
}


@dataclass(frozen=True)
class TriggerRecord:
    x: int
    y: int
    text_index: int
    sound_index: int
    order: int


@dataclass(frozen=True)
class TargetRecord:
    x: int
    y: int
    order: int


@dataclass(frozen=True)
class LockRecord:
    x: int
    y: int
    level: int
    order: int


@dataclass(frozen=True)
class EntityRecord:
    x: int
    y: int
    flat_index: int
    source: str = "map1"


@dataclass(frozen=True)
class InfFlatEntry:
    index: int
    name: str
    item_number: int | None


@dataclass(frozen=True)
class MifMap:
    path: Path
    flor: list[int] = field(default_factory=list)
    map1: list[int] = field(default_factory=list)
    trigs: list[TriggerRecord] = field(default_factory=list)
    targs: list[TargetRecord] = field(default_factory=list)
    locks: list[LockRecord] = field(default_factory=list)
    entities: list[EntityRecord] = field(default_factory=list)
    chunks: list[tuple[str, int]] = field(default_factory=list)
    width: int = 24
    height: int = 18
    level_index: int = 0
    level_count: int = 1
    raw_map1_size: int = 0
    mif_name: str = ""
    info_name: str = ""

    @property
    def name(self) -> str:
        return self.path.name


def _read_chunk_size(data: bytes, offset: int) -> int | None:
    if offset + 6 > len(data):
        return None
    size = struct.unpack_from("<H", data, offset + 4)[0]
    if offset + 6 + size > len(data):
        return None
    return size


def parse_mif(path: str | Path,
              level_index_override: int | None = None,
              player_floor: int | None = None) -> MifMap:
    mif_path = Path(path)
    return parse_mif_bytes(mif_path.read_bytes(), mif_path,
                           level_index_override, player_floor)


def parse_mif_bytes(data: bytes, path: str | Path = "<memory>",
                    level_index_override: int | None = None,
                    player_floor: int | None = None) -> MifMap:
    mif_path = Path(path)
    parsed = _parse_mif_structured(data, mif_path,
                                    level_index_override, player_floor)
    if parsed is not None:
        return parsed

    return _parse_mif_scan_fallback(data, mif_path)


def _parse_mif_structured(data: bytes, mif_path: Path,
                           level_index_override: int | None = None,
                           player_floor: int | None = None) -> MifMap | None:
    if data[:4] != b"MHDR":
        return None
    header_size = _read_chunk_size(data, 0)
    if header_size is None or header_size < 25:
        return None
    header = data[6 : 6 + header_size]
    starting_level = header[18]
    level_count_hint = header[19]
    width = struct.unpack_from("<H", header, 21)[0]
    height = struct.unpack_from("<H", header, 23)[0]
    if width <= 0 or height <= 0:
        return None

    levels: list[MifMap] = []
    offset = 6 + header_size
    level_index = 0
    while offset + 6 <= len(data):
        if data[offset : offset + 4] != b"LEVL":
            break
        level_size = _read_chunk_size(data, offset)
        if level_size is None:
            break
        level_end = min(len(data), offset + 6 + level_size)
        level = _parse_level(data[offset + 6 : level_end], mif_path, width, height, level_index)
        levels.append(level)
        offset = level_end
        level_index += 1

    if not levels:
        return None

    if (level_index_override is not None
            and 0 <= level_index_override < len(levels)):
        selected_index = level_index_override
    elif player_floor is not None and 0 <= starting_level < len(levels):
        adj = starting_level - player_floor
        if 0 <= adj < len(levels):
            selected_index = adj
        else:
            selected_index = starting_level
    elif 0 <= starting_level < len(levels):
        selected_index = starting_level
    else:
        selected_index = 0
    selected = levels[selected_index]
    return MifMap(
        path=mif_path,
        flor=selected.flor,
        map1=selected.map1,
        trigs=selected.trigs,
        targs=selected.targs,
        locks=selected.locks,
        entities=selected.entities,
        chunks=[("MHDR", header_size), *selected.chunks],
        width=width,
        height=height,
        level_index=selected_index,
        level_count=max(len(levels), level_count_hint),
        raw_map1_size=selected.raw_map1_size,
        mif_name=selected.mif_name,
        info_name=selected.info_name,
    )


def _parse_level(data: bytes, mif_path: Path, width: int, height: int, level_index: int) -> MifMap:
    flor: list[int] = []
    map1: list[int] = []
    trigs: list[TriggerRecord] = []
    targs: list[TargetRecord] = []
    locks: list[LockRecord] = []
    chunks: list[tuple[str, int]] = []
    raw_map1_size = 0
    mif_name_val = ""
    info_name_val = ""

    offset = 0
    while offset + 6 <= len(data):
        tag = data[offset : offset + 4].decode("ascii", errors="replace")
        size = _read_chunk_size(data, offset)
        if tag not in KNOWN_CHUNKS or size is None:
            break
        body = data[offset + 6 : offset + 6 + size]
        chunks.append((tag, size))
        if tag == "TRIG":
            trigs.extend(_parse_trigs(body, len(trigs)))
        elif tag == "TARG":
            targs.extend(_parse_targs(body, len(targs)))
        elif tag == "LOCK":
            locks.extend(_parse_locks(body, len(locks)))
        elif tag == "FLOR":
            flor = _decode_mif_layer(data[offset : offset + 6 + size], width, height)
        elif tag == "MAP1":
            raw_map1_size = size
            map1 = _decode_mif_layer(data[offset : offset + 6 + size], width, height)
        elif tag == "NAME":
            mif_name_val = body.split(b"\x00")[0].decode("ascii", errors="replace")
        elif tag == "INFO":
            info_name_val = body.split(b"\x00")[0].decode("ascii", errors="replace")
        offset += 6 + size

    entities = _extract_entities(map1, flor, width, height)
    return MifMap(
        path=mif_path,
        flor=flor,
        map1=map1,
        trigs=trigs,
        targs=targs,
        locks=locks,
        entities=entities,
        chunks=chunks,
        width=width,
        height=height,
        level_index=level_index,
        raw_map1_size=raw_map1_size,
        mif_name=mif_name_val,
        info_name=info_name_val,
    )


def _parse_mif_scan_fallback(data: bytes, mif_path: Path) -> MifMap:
    trigs: list[TriggerRecord] = []
    targs: list[TargetRecord] = []
    locks: list[LockRecord] = []
    chunks: list[tuple[str, int]] = []
    map1_raw: bytes | None = None

    i = 0
    while i < len(data) - 6:
        tag_bytes = data[i : i + 4]
        tag = tag_bytes.decode("ascii", errors="replace")
        if tag not in KNOWN_CHUNKS:
            i += 1
            continue
        size = _read_chunk_size(data, i)
        if size is None:
            i += 1
            continue
        body = data[i + 6 : i + 6 + size]
        chunks.append((tag, size))

        if tag == "TRIG":
            trigs.extend(_parse_trigs(body, len(trigs)))
        elif tag == "TARG":
            targs.extend(_parse_targs(body, len(targs)))
        elif tag == "LOCK":
            locks.extend(_parse_locks(body, len(locks)))
        elif tag == "MAP1" and map1_raw is None:
            map1_raw = body
        i += 6 + size

    width, height = detect_dimensions(None, trigs, targs, locks)
    return MifMap(
        path=mif_path,
        map1=list(map1_raw or b""),
        trigs=trigs,
        targs=targs,
        locks=locks,
        chunks=chunks,
        width=width,
        height=height,
        raw_map1_size=len(map1_raw or b""),
    )


def _parse_trigs(body: bytes, start_order: int) -> list[TriggerRecord]:
    return [
        TriggerRecord(*struct.unpack_from("4B", body, n * 4), start_order + n)
        for n in range(len(body) // 4)
    ]


def _parse_targs(body: bytes, start_order: int) -> list[TargetRecord]:
    return [
        TargetRecord(*struct.unpack_from("2B", body, n * 2), start_order + n)
        for n in range(len(body) // 2)
    ]


def _parse_locks(body: bytes, start_order: int) -> list[LockRecord]:
    return [
        LockRecord(*struct.unpack_from("3B", body, n * 3), start_order + n)
        for n in range(len(body) // 3)
    ]


def _decode_mif_layer(tag_data: bytes, width: int, height: int) -> list[int]:
    if len(tag_data) < 8:
        return []
    compressed_size = struct.unpack_from("<H", tag_data, 4)[0]
    uncompressed_size = struct.unpack_from("<H", tag_data, 6)[0]
    expected_size = width * height * 2
    if uncompressed_size < expected_size:
        return []
    compressed = tag_data[8 : 6 + compressed_size]
    decoded = _decode_type08(compressed, uncompressed_size)
    voxels: list[int] = []
    for index in range(width * height):
        voxels.append(struct.unpack_from("<H", decoded, index * 2)[0])
    return voxels


def _decode_type08(src: bytes, out_size: int) -> bytes:
    high_offset_bits = [0x00] * 0x20
    for value in range(0x01, 0x04):
        high_offset_bits.extend([value] * 0x10)
    for value in range(0x04, 0x0C):
        high_offset_bits.extend([value] * 0x08)
    for value in range(0x0C, 0x18):
        high_offset_bits.extend([value] * 0x04)
    for value in range(0x18, 0x30):
        high_offset_bits.extend([value] * 0x02)
    high_offset_bits.extend(range(0x30, 0x40))
    low_offset_bit_count = [
        *(0x03 for _ in range(0x20)),
        *(0x04 for _ in range(0x30)),
        *(0x05 for _ in range(0x40)),
        *(0x06 for _ in range(0x30)),
        *(0x07 for _ in range(0x30)),
        *(0x08 for _ in range(0x10)),
    ]
    history = [0x20] * 4096
    historypos = 0
    node_idx_map = [0] * 941
    for i in range(626):
        node_idx_map[i] = (i >> 1) + 314
    node_idx_map[626] = 0
    for i in range(627, 941):
        node_idx_map[i] = i - 627
    node_tree = [0] * 627
    for i in range(314):
        node_tree[i] = 627 + i
    for i in range(314, 627):
        node_tree[i] = (i - 314) * 2
    node_freq = [0] * 627
    for i in range(314):
        node_freq[i] = 1
    iter_idx = 0
    for i in range(314, 627):
        node_freq[i] = node_freq[iter_idx] + node_freq[iter_idx + 1]
        iter_idx += 2

    bitmask = 0
    validbits = 0
    src_pos = 0
    out = bytearray()

    def ensure_bits() -> tuple[int, int, int]:
        nonlocal bitmask, validbits, src_pos
        while validbits < 9:
            if src_pos < len(src):
                bitmask = (bitmask | (src[src_pos] << (8 - validbits))) & 0xFFFF
                src_pos += 1
            validbits += 8
        return bitmask, validbits, src_pos

    while len(out) < out_size:
        node = node_tree[626]
        while node < 627:
            ensure_bits()
            node = node_tree[node + ((bitmask >> 15) & 1)]
            bitmask = (bitmask << 1) & 0xFFFF
            validbits -= 1

        freqidx = node_idx_map[node]
        while True:
            node_freq[freqidx] += 1
            freq = node_freq[freqidx]
            nextidx = freqidx + 1
            if nextidx < len(node_freq) and node_freq[nextidx] < freq:
                while nextidx < len(node_freq) and node_freq[nextidx] < freq:
                    nextidx += 1
                nextidx -= 1
                node_freq[freqidx] = node_freq[nextidx]
                node_freq[nextidx] = freq
                node_tree[freqidx], node_tree[nextidx] = node_tree[nextidx], node_tree[freqidx]
                for idx in (nextidx, freqidx):
                    mapidx = node_tree[idx]
                    node_idx_map[mapidx] = idx
                    if mapidx < 627:
                        node_idx_map[mapidx + 1] = idx
                freqidx = nextidx
            freqidx = node_idx_map[freqidx]
            if freqidx == 0:
                break

        codeword = node - 627
        if codeword < 256:
            value = codeword & 0xFF
            history[historypos & 0x0FFF] = value
            historypos += 1
            out.append(value)
        else:
            ensure_bits()
            tableidx = bitmask >> 8
            bitmask = (bitmask << 8) & 0xFFFF
            validbits -= 8
            offset_high = high_offset_bits[tableidx] << 6
            bitcount = low_offset_bit_count[tableidx] - 2
            offset_low = tableidx
            for _ in range(bitcount):
                ensure_bits()
                offset_low = (offset_low << 1) | ((bitmask >> 15) & 1)
                bitmask = (bitmask << 1) & 0xFFFF
                validbits -= 1
            copypos = historypos - (offset_high | (offset_low & 0x003F)) - 1
            tocopy = codeword - 256 + 3
            for _ in range(tocopy):
                value = history[copypos & 0x0FFF]
                copypos += 1
                history[historypos & 0x0FFF] = value
                historypos += 1
                out.append(value)
                if len(out) >= out_size:
                    break
    return bytes(out)


def detect_dimensions(
    map1: bytes | None,
    trigs: list[TriggerRecord],
    targs: list[TargetRecord],
    locks: list[LockRecord],
) -> tuple[int, int]:
    coords = [(r.x, r.y) for r in trigs] + [(r.x, r.y) for r in targs] + [(r.x, r.y) for r in locks]
    min_w = max((x for x, _y in coords), default=23) + 2
    min_h = max((y for _x, y in coords), default=17) + 2

    if map1:
        size = len(map1)
        candidates: list[tuple[int, int]] = []
        for width in range(max(1, min_w), min(size, 128) + 1):
            if size % width == 0:
                height = size // width
                if height >= min_h and height <= 128:
                    candidates.append((width, height))
        if candidates:
            candidates.sort(key=lambda wh: (abs((wh[0] / max(wh[1], 1)) - 1.5), wh[0] * wh[1]))
            return candidates[0]

    return max(24, min_w), max(18, min_h)


def parse_inf_texts(path: str | Path) -> dict[int, str]:
    lines = _read_inf_lines(path)
    if not lines:
        return {}
    return parse_inf_text_lines(lines)


def parse_inf_text_lines(lines: list[str]) -> dict[int, str]:
    texts: dict[int, list[str]] = {}
    current: int | None = None
    in_text = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.upper() == "@TEXT":
            in_text = True
            current = None
            continue
        if stripped.startswith("@") and stripped.upper() != "@TEXT":
            if in_text:
                break
            continue
        if not in_text:
            continue
        upper = stripped.upper()
        if upper.startswith("*TEXT"):
            parts = stripped.split()
            current = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
            if current is not None:
                texts.setdefault(current, [])
            continue
        if current is not None:
            texts[current].append(stripped.lstrip("~"))

    return {idx: "\n".join(part for part in parts if part).strip() for idx, parts in texts.items()}


def matching_inf_path(mif_path: str | Path, inf_dir: str | Path) -> Path | None:
    stem = Path(mif_path).stem
    base = Path(inf_dir)
    for candidate in (base / f"{stem}.INF", base / f"{stem}.inf"):
        if candidate.is_file():
            return candidate
    if base.is_dir():
        stem_upper = stem.upper()
        for candidate in base.iterdir():
            if candidate.is_file() and candidate.suffix.upper() == ".INF" and candidate.stem.upper() == stem_upper:
                return candidate
    return None


def parse_mif_name(path: str | Path) -> str:
    mif_path = Path(path)
    try:
        data = mif_path.read_bytes()
    except OSError:
        return ""
    if data[:4] != b"MHDR":
        return ""
    header_size = _read_chunk_size(data, 0)
    if header_size is None:
        return ""
    offset = 6 + header_size
    if offset + 6 > len(data) or data[offset : offset + 4] != b"LEVL":
        return ""
    level_size = _read_chunk_size(data, offset)
    if level_size is None:
        return ""
    level_end = min(len(data), offset + 6 + level_size)
    level_data = data[offset + 6 : level_end]
    loff = 0
    while loff + 6 <= len(level_data):
        tag = level_data[loff : loff + 4].decode("ascii", errors="replace")
        sz = _read_chunk_size(level_data, loff)
        if sz is None:
            break
        if tag == "NAME":
            body = level_data[loff + 6 : loff + 6 + sz]
            return body.split(b"\x00")[0].decode("ascii", errors="replace")
        if tag not in KNOWN_CHUNKS:
            break
        loff += 6 + sz
    return ""


def _extract_entities(map1: list[int], flor: list[int], width: int, height: int) -> list[EntityRecord]:
    entities: list[EntityRecord] = []
    for sn in range(height):
        for we in range(width):
            idx = sn * width + we
            m1v = map1[idx] if idx < len(map1) else 0
            flv = flor[idx] if idx < len(flor) else 0

            if (m1v & 0xF000) >> 12 == 0x8:
                entities.append(EntityRecord(x=we, y=sn, flat_index=m1v & 0x00FF, source="map1"))

            floor_flat_id = flv & 0x00FF
            if floor_flat_id > 0:
                entities.append(EntityRecord(x=we, y=sn, flat_index=floor_flat_id - 1, source="flor"))
    return entities


def _install_vfs():
    from runtime_paths import install_vfs
    return install_vfs()


def read_inf_bytes(path: str | Path) -> bytes | None:
    inf_path = Path(path)
    try:
        if inf_path.is_file():
            return inf_path.read_bytes()
    except OSError:
        pass
    vfs = _install_vfs()
    if vfs is not None:
        data = vfs.read_inf(inf_path.name)
        if data is not None:
            return data
    return None


def _read_inf_lines(path: str | Path) -> list[str]:
    data = read_inf_bytes(path)
    if data is None:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def read_mif_bytes(path: str | Path) -> bytes | None:
    mif_path = Path(path)
    try:
        if mif_path.is_file():
            return mif_path.read_bytes()
    except OSError:
        pass
    vfs = _install_vfs()
    if vfs is not None:
        return vfs.read(mif_path.name)
    return None


def load_mif(mif_name: str, mif_dirs, *, player_floor: int = 0,
             level_index_override: int | None = None) -> "MifMap | None":
    for d in mif_dirs:
        dp = Path(d)
        try:
            if not dp.exists():
                continue
        except OSError:
            continue
        candidate = dp / mif_name
        if candidate.exists():
            return parse_mif(candidate, level_index_override, player_floor)
        try:
            for f in dp.iterdir():
                if f.is_file() and f.name.lower() == mif_name.lower():
                    return parse_mif(f, level_index_override, player_floor)
        except OSError:
            pass
    vfs = _install_vfs()
    if vfs is not None:
        data = vfs.read(mif_name)
        if data is not None:
            return parse_mif_bytes(data, mif_name, level_index_override, player_floor)
    return None


def _inf_available(name: str) -> bool:
    if not name:
        return False
    try:
        if (DEFAULT_INF_DIR / name).is_file():
            return True
    except OSError:
        pass
    vfs = _install_vfs()
    return bool(vfs is not None and vfs.exists(name))


def resolve_inf_for_mif(mif_name: str, info_name: str,
                        inf_dir: str | Path) -> Path | None:
    base = Path(inf_dir)
    stem = Path(mif_name).stem
    for name in (f"{stem}.INF", info_name):
        if name and _inf_available(name):
            return base / name
    return None


def parse_inf_flats(path: str | Path) -> list[InfFlatEntry]:
    lines = _read_inf_lines(path)
    if not lines:
        return []
    entries: list[InfFlatEntry] = []
    in_flats = False
    pending_item: int | None = None
    flat_index = 0
    for raw in lines:
        stripped = raw.strip()
        upper = stripped.upper()
        if upper.startswith("@FLATS"):
            in_flats = True
            continue
        if stripped.startswith("@") and not upper.startswith("@FLATS"):
            if in_flats:
                break
            continue
        if not in_flats or not stripped:
            continue
        if upper.startswith("*ITEM"):
            parts = stripped.split()
            if len(parts) >= 2 and parts[1].isdigit():
                pending_item = int(parts[1])
            continue
        name_part = stripped.split()[0]
        if name_part.startswith("*") or name_part.startswith("@"):
            continue
        entries.append(InfFlatEntry(index=flat_index, name=name_part.lower(), item_number=pending_item))
        flat_index += 1
        pending_item = None
    return entries


def parse_inf_walls_hidden_door_ids(path: str | Path) -> set[int]:
    lines = _read_inf_lines(path)
    if not lines:
        return set()
    hidden_ids: set[int] = set()
    in_walls = False
    idx = 0
    door_type: int | None = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        up = s.upper()
        if up == "@WALLS":
            in_walls = True
            continue
        if s.startswith("@") and in_walls:
            break
        if not in_walls:
            continue
        if up.startswith("*DOOR"):
            parts = s.split()
            door_type = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        elif up.startswith(("*BOXCAP", "*BOXSIDE", "*LEVELDOWN", "*LEVELUP",
                             "*LAVACHASM", "*WETCHASM", "*DRYCHASM", "*TRANS")):
            pass
        elif not s.startswith(("*", "@")):
            if door_type == 2:
                hidden_ids.add(idx)
            idx += 1
            door_type = None
    return hidden_ids


def parse_inf_menu_indices(path: str | Path) -> set[int]:
    lines = _read_inf_lines(path)
    if not lines:
        return set()

    voxel_count = 0
    menu_indices: set[int] = set()
    section: str | None = None
    pending_menu = False

    for line in lines:
        s = line.strip()
        if not s:
            continue
        up = s.upper()

        if s.startswith("@"):
            section = up.split()[0]
            continue

        if section not in ("@FLOORS", "@WALLS"):
            continue

        if s.startswith("*"):
            if up.startswith("*MENU"):
                pending_menu = True
            elif up.startswith(("*TRANS", "*DOOR", "*BOXCAP", "*BOXSIDE",
                                "*LAVACHASM", "*WETCHASM", "*DRYCHASM",
                                "*WALKTHRU", "*TRANSWALKTHRU",
                                "*LEVELUP", "*LEVELDOWN")):
                pass
            continue

        parts = s.split("#")
        set_count = int(parts[1].strip()) if len(parts) == 2 else 1
        if pending_menu:
            menu_indices.add(voxel_count)
            pending_menu = False
        voxel_count += set_count

    return menu_indices


def parse_inf_menu_texture_map(path: str | Path) -> dict[int, int]:
    lines = _read_inf_lines(path)
    if not lines:
        return {}

    voxel_count = 0
    menu_map: dict[int, int] = {}
    section: str | None = None
    pending_menu_id: int | None = None

    for line in lines:
        s = line.strip()
        if not s:
            continue
        up = s.upper()

        if s.startswith("@"):
            section = up.split()[0]
            continue

        if section not in ("@FLOORS", "@WALLS"):
            continue

        if s.startswith("*"):
            if up.startswith("*MENU"):
                tokens = s.split()
                if len(tokens) >= 2 and tokens[1].lstrip("-").isdigit():
                    pending_menu_id = int(tokens[1])
            continue

        parts = s.split("#")
        set_count = int(parts[1].strip()) if len(parts) == 2 else 1
        if pending_menu_id is not None:
            menu_map[pending_menu_id] = voxel_count
            pending_menu_id = None
        voxel_count += set_count

    return menu_map


def parse_inf_wall_texture_names(path: str | Path) -> dict[int, str]:
    lines = _read_inf_lines(path)
    if not lines:
        return {}

    voxel_count = 0
    names: dict[int, str] = {}
    section: str | None = None

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("@"):
            section = s.upper().split()[0]
            continue
        if section not in ("@FLOORS", "@WALLS"):
            continue
        if s.startswith("*"):
            continue
        parts = s.split("#")
        name = parts[0].strip()
        set_count = int(parts[1].strip()) if len(parts) == 2 else 1
        for k in range(set_count):
            names[voxel_count + k] = name
        voxel_count += set_count

    return names


def parse_inf_level_transitions(path: str | Path) -> tuple[int | None, int | None]:
    lines = _read_inf_lines(path)
    if not lines:
        return None, None

    voxel_count = 0
    level_up_index: int | None = None
    level_down_index: int | None = None
    section: str | None = None
    pending_mode: str | None = None

    for line in lines:
        s = line.strip()
        if not s:
            continue
        up = s.upper()

        if s.startswith("@"):
            section = up.split()[0]
            continue

        if section not in ("@FLOORS", "@WALLS"):
            continue

        if s.startswith("*"):
            if up.startswith("*LEVELUP"):
                pending_mode = "levelup"
            elif up.startswith("*LEVELDOWN"):
                pending_mode = "leveldown"
            elif up.startswith(("*TRANS", "*DOOR", "*BOXCAP", "*BOXSIDE",
                                "*LAVACHASM", "*WETCHASM", "*DRYCHASM",
                                "*WALKTHRU", "*TRANSWALKTHRU")):
                pass
            continue

        parts = s.split("#")
        set_count = int(parts[1].strip()) if len(parts) == 2 else 1
        idx = voxel_count

        if pending_mode == "levelup":
            level_up_index = idx
        elif pending_mode == "leveldown":
            level_down_index = idx

        voxel_count += set_count
        pending_mode = None

    return level_up_index, level_down_index


def list_mif_files(*roots: str | Path) -> list[Path]:
    files: dict[str, Path] = {}
    for root in roots:
        path = Path(root)
        if not path.is_dir():
            continue
        for mif in path.glob("*.MIF"):
            files.setdefault(mif.name.upper(), mif)
        for mif in path.glob("*.mif"):
            files.setdefault(mif.name.upper(), mif)
    return sorted(files.values(), key=lambda p: p.name.upper())
