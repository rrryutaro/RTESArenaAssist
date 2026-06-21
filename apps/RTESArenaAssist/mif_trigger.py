
import json
import os
import struct
import sys


def parse_mif_trigs_bytes(data: bytes) -> list[tuple[int, int, int, int]]:
    i = 0
    while i < len(data) - 6:
        if data[i:i+4] == b"TRIG":
            size      = struct.unpack_from("<H", data, i + 4)[0]
            rec_count = size // 4
            offset    = i + 6
            return [
                struct.unpack_from("4B", data, offset + r * 4)
                for r in range(rec_count)
            ]
        i += 1
    return []


def parse_mif_trigs(path: str) -> list[tuple[int, int, int, int]]:
    data = None
    try:
        from services.mif_loader import read_mif_bytes
        data = read_mif_bytes(path)
    except ImportError:  # pragma: no cover - 直接スクリプト実行時の保険
        data = None
    if data is None:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return []
    return parse_mif_trigs_bytes(data)


def extract_trigger_texts(raw_block: bytes) -> list[str]:
    texts = []
    for chunk in raw_block.split(b"\x00"):
        text  = chunk.decode("ascii", errors="replace").strip().lstrip("~")
        ratio = sum(32 <= ord(c) <= 126 for c in text) / max(len(text), 1)
        if text and ratio >= 0.7:
            texts.append(text.replace("\r", " ").replace("\n", " "))
    return texts


def get_trigger_text_by_index(raw_block: bytes, text_index: int) -> str:
    texts = extract_trigger_texts(raw_block)
    if not texts:
        return ""
    if 0 <= text_index < len(texts):
        return texts[text_index]
    return texts[0]


def _load_bundled_trig_table() -> dict[str, list[tuple[int, int, int]]]:
    if getattr(sys, "frozen", False):
        base_dir = getattr(
            sys,
            "_MEIPASS",
            os.path.dirname(os.path.abspath(sys.executable)),
        )
        json_path = os.path.join(base_dir, "dictionary", "trig_table.json")
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.normpath(
            os.path.join(
                here,
                "..",
                "RTESArenaAssist",
                "dictionary",
                "trig_table.json",
            )
        )
    if not os.path.isfile(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {
        k.upper(): [tuple(v) for v in vs]
        for k, vs in raw.items()
    }


_BUNDLED_TABLE: dict[str, list[tuple[int, int, int]]] | None = None


def _bundled_table() -> dict[str, list[tuple[int, int, int]]]:
    global _BUNDLED_TABLE
    if _BUNDLED_TABLE is None:
        _BUNDLED_TABLE = _load_bundled_trig_table()
    return _BUNDLED_TABLE


class MifTriggerMatcher:

    def __init__(self, mif_dir: str = ""):
        self._mif_dir = mif_dir
        self._loaded_mif: str = ""
        self._trigs: list[tuple[int, int, int, int]] = []
        self._last_status: str = "unknown"
        self._last_mif_entry: tuple[int, int, int, int] | None = None
        self._source: str = "none"

    def update_map(self, mif_name: str) -> bool:
        if not mif_name or mif_name == self._loaded_mif:
            return bool(self._trigs)

        key = mif_name.upper()
        bundled = _bundled_table().get(key)
        if bundled:
            self._trigs = [(x, y, ti, 0) for (x, y, ti) in bundled]
            self._loaded_mif = mif_name
            self._source = "bundled"
            self._last_status = "unknown"
            return True

        path = os.path.join(self._mif_dir, key) if self._mif_dir else key
        self._trigs      = parse_mif_trigs(path)
        self._loaded_mif = mif_name
        self._source = "mif_file" if self._trigs else "none"
        self._last_status = "mif_trig_not_found" if not self._trigs else "unknown"
        return bool(self._trigs)

    def find_text_index(self, rt_x: int, rt_y: int) -> int | None:
        self._last_mif_entry = None
        if not self._trigs:
            self._last_status = (
                "mif_not_loaded" if not self._loaded_mif else "mif_trig_not_found"
            )
            return None
        for entry in self._trigs:
            x, y, ti, _si = entry
            if x == rt_x and y == rt_y:
                self._last_mif_entry = entry
                self._last_status = "matched"
                return ti
        self._last_status = "mif_coord_not_found"
        return None

    @property
    def trig_count(self) -> int:
        return len(self._trigs)

    @property
    def loaded_mif(self) -> str:
        return self._loaded_mif

    @property
    def last_status(self) -> str:
        return self._last_status

    @property
    def last_mif_entry(self) -> tuple[int, int, int, int] | None:
        return self._last_mif_entry

    @property
    def source(self) -> str:
        return self._source
