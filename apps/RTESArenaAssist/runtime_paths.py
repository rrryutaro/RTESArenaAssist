"""Runtime resource path helpers for source and PyInstaller builds."""
from __future__ import annotations

import sys
from pathlib import Path


def app_resource_root() -> Path:
    """Return the root that contains bundled runtime resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """Return the repository root for source-tree execution."""
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return app_resource_root().joinpath(*parts)


def _source_arena_data_candidates() -> list[Path]:
    root = repo_root()
    candidates = [root / "docs" / "ARENA-data"]

    # Worktree checkouts may be nested below ".claude"; keep the fallback
    # to the main repo root for that layout.
    parts = root.parts
    if ".claude" in parts:
        idx = parts.index(".claude")
        if idx > 0:
            candidates.append(Path(*parts[:idx]) / "docs" / "ARENA-data")
    return candidates


def resolve_arena_data_dir() -> Path:
    """Resolve ARENA-data for frozen exe first, source docs second."""
    candidates = [resource_path("ARENA-data")]
    candidates.extend(_source_arena_data_candidates())
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return candidates[0]


def resolve_arena_install_dir() -> Path | None:
    """ユーザーが設定した Arena インストール（セーブ）フォルダを返す。

    公開版は固定パスを持たない。`A.EXE`/`ACD.EXE`＋`GLOBAL.BSA`・
    `WILD001-004.RMD` の動的書き出し先・loose MIF 等を持つユーザー環境ディレクトリを、
    設定 `save_dir` から**実行時に**解決する。未設定・不正・設定未初期化なら None
    （呼び出し側は None を候補から除外する）。
    """
    try:
        import assist_settings  # 関数内 import（循環回避・設定未初期化でも安全）
        raw = (assist_settings.get("save_dir") or "").strip()
    except Exception:  # noqa: BLE001 - 設定未初期化等でも解決失敗で None
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
    """ユーザー Arena install 上の VFS（loose→GLOBAL.BSA）。無ければ None。

    `resolve_arena_install_dir()` の指す dir に対する `arena_vfs.Vfs` を返す（dir 変化時
    のみ再構築してキャッシュ）。MIF/INF/RMD など個別ファイルの公開版 fallback 読取に使う。
    install dir 未設定や VFS 構築失敗時は None（呼び出し側は loose のみで継続）。
    """
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
            except Exception:  # noqa: BLE001 - VFS 構築失敗は loose のみで継続
                _install_vfs_cache = None
    return _install_vfs_cache


__all__ = [
    "app_resource_root",
    "repo_root",
    "resource_path",
    "resolve_arena_data_dir",
    "resolve_arena_install_dir",
    "install_vfs",
]
