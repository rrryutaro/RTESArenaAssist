"""
mif_trigger.py  ―  MIF TRIG 座標照合モジュール（Step2-3-2-5）

プレイヤーのリアルタイム座標と MIF ファイルの TRIG レコードを照合し、
表示すべきテキストインデックスを特定する。

TRIG レコード構造（MIF ファイル, 4バイト固定）:
    x (1B) | y (1B) | textIndex (1B) | soundIndex (1B)

照合ロジック:
    トリガー発動時（TRIGGER_FLAG 0→非0 遷移）にキャッシュした RT座標と
    TRIG レコードの (x, y) を完全一致で比較 → textIndex を取得
    → TRIGGER_BLOCK の texts[textIndex] を表示テキストとする

データソース優先順位（b26）:
    1. バンドル済み JSON テーブル (RTESArenaAssist/dictionary/trig_table.json)
       - 全 MIF の全レベル TRIG をプリパース済み
    2. ランタイム MIF パース (legacy)
       - JSON が無い MIF / 環境では従来通り mif_dir から読む
       - parse_mif_trigs は最初の TRIG チャンクしか拾わないため multi-level MIF で
         漏れる懸念があるが、JSON が利用できる場合は問題にならない
"""

import json
import os
import struct
import sys


def parse_mif_trigs(path: str) -> list[tuple[int, int, int, int]]:
    """
    MIFファイルをパースして TRIG レコードを返す。
    戻り値: [(x, y, textIndex, soundIndex), ...]
    """
    with open(path, "rb") as f:
        data = f.read()
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


def extract_trigger_texts(raw_block: bytes) -> list[str]:
    """TRIGGER_BLOCK（NUL区切り）からテキストリストを生成する。"""
    texts = []
    for chunk in raw_block.split(b"\x00"):
        text  = chunk.decode("ascii", errors="replace").strip().lstrip("~")
        ratio = sum(32 <= ord(c) <= 126 for c in text) / max(len(text), 1)
        if text and ratio >= 0.7:
            texts.append(text.replace("\r", " ").replace("\n", " "))
    return texts


def get_trigger_text_by_index(raw_block: bytes, text_index: int) -> str:
    """
    TRIGGER_BLOCK から text_index 番目のテキストを返す。
    範囲外の場合は texts[0] にフォールバック。
    """
    texts = extract_trigger_texts(raw_block)
    if not texts:
        return ""
    if 0 <= text_index < len(texts):
        return texts[text_index]
    return texts[0]


def _load_bundled_trig_table() -> dict[str, list[tuple[int, int, int]]]:
    """RTESArenaAssist/dictionary/trig_table.json をロード（b26）。

    sibling アプリ（Probe）からも参照できるように、相対パスで Assist 側を指す。
    存在しなければ空 dict を返す（フォールバックで legacy 動作）。
    """
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
    """
    MIF TRIG レコードとプレイヤー座標を照合してテキストインデックスを特定するクラス。
    マップ変更時に自動的に TRIG レコードを再ロードする。

    使い方:
        matcher = MifTriggerMatcher(mif_dir=settings.get("mif_dir", ""))
        # マップ変更時（毎ポーリング）
        matcher.update_map(mif_name)
        # トリガー発動時
        ti = matcher.find_text_index(cached_rt_x, cached_rt_y)
        if ti is not None:
            text = get_trigger_text_by_index(raw_block, ti)
    """

    def __init__(self, mif_dir: str = ""):
        self._mif_dir = mif_dir
        self._loaded_mif: str = ""
        self._trigs: list[tuple[int, int, int, int]] = []
        self._last_status: str = "unknown"
        self._last_mif_entry: tuple[int, int, int, int] | None = None
        self._source: str = "none"  # b26: 'bundled' or 'mif_file' or 'none'

    def update_map(self, mif_name: str) -> bool:
        """
        マップ変更時に TRIG を再ロード。
        同じマップ名であれば何もしない。
        戻り値: TRIG ロード済みなら True

        b26: バンドル JSON を最初に試し、そこに無ければ legacy MIF パース。
        """
        if not mif_name or mif_name == self._loaded_mif:
            return bool(self._trigs)

        key = mif_name.upper()
        bundled = _bundled_table().get(key)
        if bundled:
            # JSON は (x, y, text_index) の 3 タプル → 4 タプルに拡張（sound_index は 0 詰め）
            self._trigs = [(x, y, ti, 0) for (x, y, ti) in bundled]
            self._loaded_mif = mif_name
            self._source = "bundled"
            self._last_status = "unknown"
            return True

        if not self._mif_dir:
            self._loaded_mif = mif_name
            self._trigs = []
            self._source = "none"
            self._last_status = "mif_not_loaded"
            return False
        path = os.path.join(self._mif_dir, key)
        if not os.path.isfile(path):
            self._loaded_mif = mif_name
            self._trigs = []
            self._source = "none"
            self._last_status = "mif_not_loaded"
            return False
        self._trigs      = parse_mif_trigs(path)
        self._loaded_mif = mif_name
        self._source = "mif_file"
        self._last_status = "mif_trig_not_found" if not self._trigs else "unknown"
        return bool(self._trigs)

    def find_text_index(self, rt_x: int, rt_y: int) -> int | None:
        """
        RT座標が TRIG に一致する textIndex を返す。
        複数ある場合は最初の一致を返す。一致なしは None。
        """
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
        """b26: トリガーデータの出所 ('bundled' / 'mif_file' / 'none')"""
        return self._source
