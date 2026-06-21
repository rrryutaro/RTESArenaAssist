"""Assist 所有データの読込層（公開版リソースモデル）。

frozen 公開ビルドでは Assist 所有データ（翻訳 i18n・assets・manual/simple・_aexe_template・
fingerprints/golden 等）を **exe 内 seed パック**（PYZ 同梱の ``_seed_data`` モジュール＝zip
バイト列）から**直接**読む。これにより ``_internal`` には Python/PySide 依存のみが入り、
Assist データは exe 内に在る（``_internal`` を更新せず exe 入替だけで反映する）。

dev / 非 frozen / seed 不在時は ``runtime_paths.app_resource_root()`` 起点でディスク直読み
（従来挙動と等価）。本層は **相対パス（"/" 区切り）** を受け、seed→ディスクの順で解決する。

API:
  has_seed()                     seed パックを使うか（frozen かつ ``_seed_data`` あり）
  read_bytes(rel) / read_text    バイト列 / テキスト（無ければ None）
  exists(rel) / is_dir(rel)      存在・ディレクトリ判定
  listdir(rel)                   rel 直下の名前一覧（seed/disk 共通）
  resource_fs_path(rel)          filesystem パス（path 必須 consumer 用＝seed 時は temp 抽出）
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

from runtime_paths import app_resource_root

_zip: "zipfile.ZipFile | None" = None
_zip_loaded = False
_extract_dir: str | None = None


def _seed_zip() -> "zipfile.ZipFile | None":
    """exe 内 seed zip を返す（frozen かつ ``_seed_data`` 存在時のみ・それ以外 None）。"""
    global _zip, _zip_loaded
    if _zip_loaded:
        return _zip
    _zip_loaded = True
    if getattr(sys, "frozen", False):
        try:
            import _seed_data  # ビルド時生成（dev には存在しない）
            _zip = zipfile.ZipFile(io.BytesIO(_seed_data.DATA))
        except Exception:  # noqa: BLE001 - seed 不在/破損はディスク読みへフォールバック
            _zip = None
    return _zip


def _norm(rel: str) -> str:
    return rel.replace("\\", "/").strip("/")


def has_seed() -> bool:
    return _seed_zip() is not None


def read_bytes(rel: str) -> "bytes | None":
    z = _seed_zip()
    if z is not None:
        try:
            return z.read(_norm(rel))
        except KeyError:
            return None
    try:
        with open(os.path.join(app_resource_root(), *_norm(rel).split("/")), "rb") as f:
            return f.read()
    except OSError:
        return None


def read_text(rel: str, encoding: str = "utf-8") -> "str | None":
    b = read_bytes(rel)
    return b.decode(encoding) if b is not None else None


def exists(rel: str) -> bool:
    z = _seed_zip()
    if z is not None:
        n = _norm(rel)
        names = z.namelist()
        return n in names or (n + "/") in names or any(x.startswith(n + "/") for x in names)
    return os.path.exists(os.path.join(app_resource_root(), *_norm(rel).split("/")))


def is_dir(rel: str) -> bool:
    z = _seed_zip()
    if z is not None:
        base = _norm(rel) + "/"
        return any(x.startswith(base) for x in z.namelist())
    return os.path.isdir(os.path.join(app_resource_root(), *_norm(rel).split("/")))


def listdir(rel: str) -> list[str]:
    """rel 直下のエントリ名（ファイル/サブフォルダ）を返す（seed/disk 共通）。"""
    z = _seed_zip()
    if z is not None:
        base = (_norm(rel) + "/") if _norm(rel) else ""
        out: set[str] = set()
        for name in z.namelist():
            if base and not name.startswith(base):
                continue
            rest = name[len(base):].split("/", 1)[0]
            if rest:
                out.add(rest)
        return sorted(out)
    d = os.path.join(app_resource_root(), *_norm(rel).split("/")) if _norm(rel) else str(app_resource_root())
    try:
        return sorted(os.listdir(d))
    except OSError:
        return []


def resource_fs_path(rel: str) -> str:
    """filesystem パスを返す（QTextBrowser/winsound 等 path 必須 consumer 用）。

    seed 使用時は当該ファイルを**一時フォルダへ遅延抽出**して実パスを返す（exe 内 seed が
    データ源・temp は実行中のみの揮発材で配布物には含まれない）。dist/dev はディスク実パス。
    """
    z = _seed_zip()
    if z is None:
        return os.path.join(app_resource_root(), *_norm(rel).split("/"))
    global _extract_dir
    if _extract_dir is None:
        import tempfile
        _extract_dir = tempfile.mkdtemp(prefix="rtesa_res_")
    target = os.path.join(_extract_dir, *_norm(rel).split("/"))
    if not os.path.exists(target):
        data = read_bytes(rel)
        if data is None:
            return target  # 無い→存在しないパス（呼び側はフォールバック）
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    return target
