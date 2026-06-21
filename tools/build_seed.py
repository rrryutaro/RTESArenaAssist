#!/usr/bin/env python3
from __future__ import annotations

import base64
import io
import os
import zipfile
from pathlib import Path

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
    ("i18n/i18n_bundle.json", "i18n/i18n_bundle.json"),
    ("i18n/source_id_map.json", "i18n/source_id_map.json"),
    ("i18n/degraded_accepted.json", "i18n/degraded_accepted.json"),
    ("arena_fingerprints.json", "arena_fingerprints.json"),
    ("arena_golden_manifest.json", "arena_golden_manifest.json"),
)


def build_zip_bytes(app_dir: Path) -> bytes:
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
