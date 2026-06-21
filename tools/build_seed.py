#!/usr/bin/env python3
"""tools/build_seed.py — generate the in-exe seed pack (app-owned data) for public builds.

Run before a public build to generate `apps/RTESArenaAssist/_seed_data.py` (a base64-embedded
seed zip included in the PYZ). At runtime `app_resources` reads this module to load app-owned
data (translations, assets, manual/simple, _aexe_template, fingerprints/golden) **directly from
the exe**. This keeps `_internal` to Python/PySide dependencies only.

**Safe**: the seed contains only app-owned data (same set as the public spec datas). Arena
original text/assets (i18n original, original en, decoded Arena assets, derived service data,
etc.) are **not included**.

`_seed_data.py` は生成物。`.gitignore` 済でリポジトリに残さない（dev は frozen でないため
import されず無害）。公開 spec が解析前に本ビルダを呼んで生成する。
"""
from __future__ import annotations

import base64
import io
import os
import zipfile
from pathlib import Path

# 公開 spec datas と同一集合（Arena 原文/資産は含めない）。
_DIR_ENTRIES = (
    ("assets", "assets"),
    ("i18n/ja", "i18n/ja"),
    ("i18n/es", "i18n/es"),
    ("i18n/_aexe_template", "i18n/_aexe_template"),
    ("manual/simple", "manual/simple"),
)
_FILE_ENTRIES = (
    ("i18n/en/ui_app.json", "i18n/en/ui_app.json"),
    ("i18n/en/ui.json", "i18n/en/ui.json"),
    ("i18n/en/setup.json", "i18n/en/setup.json"),
    ("i18n/_meta.json", "i18n/_meta.json"),
    ("i18n/_template.json", "i18n/_template.json"),
    # v2 公開 runtime の Assist 所有データ（公開安全＝bundle は ja/es/en 訳＋整数 ID で
    # Arena 原文非含・source_id_map/degraded は整数 ID のみ）。_internal/i18n を置かないため
    # seed 同梱が必須（無いと v2 localpack 生成・v2 有効化が失敗し v1 後退する）。
    ("i18n/i18n_bundle.json", "i18n/i18n_bundle.json"),
    ("i18n/source_id_map.json", "i18n/source_id_map.json"),
    ("i18n/degraded_accepted.json", "i18n/degraded_accepted.json"),
    ("arena_fingerprints.json", "arena_fingerprints.json"),
    ("arena_golden_manifest.json", "arena_golden_manifest.json"),
)


def build_zip_bytes(app_dir: Path) -> bytes:
    """Assist 所有データを 1 つの zip（deflate）バイト列にまとめて返す。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in _FILE_ENTRIES:
            p = app_dir / src
            if p.is_file():
                z.write(str(p), arc)
        for src, arc in _DIR_ENTRIES:
            base = app_dir / src
            if not base.is_dir():
                continue
            for dirpath, _dirs, files in os.walk(base):
                for fn in sorted(files):
                    full = Path(dirpath) / fn
                    rel = full.relative_to(base).as_posix()
                    z.write(str(full), f"{arc}/{rel}")
    return buf.getvalue()


def build(app_dir: str | os.PathLike) -> str:
    """`<app_dir>/_seed_data.py` を生成し、そのパスを返す。"""
    app = Path(app_dir)
    data = build_zip_bytes(app)
    b64 = base64.b64encode(data).decode("ascii")
    out = app / "_seed_data.py"
    lines = [
        '"""Auto-generated seed pack (build-time only; not kept in the repo)."""',
        "import base64",
        "DATA = base64.b64decode(",
    ]
    for i in range(0, len(b64), 116):
        lines.append('    "%s"' % b64[i:i + 116])
    lines.append(")")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return str(out)


def _default_app_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "apps" / "RTESArenaAssist"


if __name__ == "__main__":
    app_dir = _default_app_dir()
    data = build_zip_bytes(app_dir)
    path = build(app_dir)
    print(f"seed: {len(data)} bytes (zip) -> {path}")
