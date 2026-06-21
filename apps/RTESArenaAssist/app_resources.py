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
    global _zip, _zip_loaded
    if _zip_loaded:
        return _zip
    _zip_loaded = True
    if getattr(sys, "frozen", False):
        try:
            import _seed_data
            _zip = zipfile.ZipFile(io.BytesIO(_seed_data.DATA))
        except Exception:  # noqa: BLE001
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
            return target
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    return target
