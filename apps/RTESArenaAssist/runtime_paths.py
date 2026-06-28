from __future__ import annotations
import sys
from pathlib import Path

def app_resource_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent

def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def resource_path(*parts: str) -> Path:
    return app_resource_root().joinpath(*parts)

def resolve_arena_data_dir() -> Path:
    return resource_path('ARENA-data')

def resolve_arena_install_dir() -> Path | None:
    try:
        import assist_settings
        raw = (assist_settings.get('save_dir') or '').strip()
    except Exception:
        return None
    if not raw:
        return None
    try:
        p = Path(raw)
        return p if p.is_dir() else None
    except OSError:
        return None
_install_vfs_cache = None
_install_vfs_dir: str | None = None

def install_vfs():
    global _install_vfs_cache, _install_vfs_dir
    install = resolve_arena_install_dir()
    key = str(install) if install is not None else None
    if key != _install_vfs_dir:
        _install_vfs_dir = key
        if install is None:
            _install_vfs_cache = None
        else:
            try:
                from arena_vfs import Vfs
                _install_vfs_cache = Vfs(str(install))
            except Exception:
                _install_vfs_cache = None
    return _install_vfs_cache
__all__ = ['app_resource_root', 'repo_root', 'resource_path', 'resolve_arena_data_dir', 'resolve_arena_install_dir', 'install_vfs']
