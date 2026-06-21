# -*- mode: python ; coding: utf-8 -*-
"""Public build PyInstaller spec (Arena assets are not bundled).

Difference from the dev `RTESArenaAssist.spec`: **all Arena-derived data is excluded
from datas**:
  - Not bundled: Arena source files (MIF/INF/RMD), i18n original text, i18n English
    source text, the legacy root i18n/en.json and i18n/ja.json, the full Arena manual
    extraction, and Arena-derived service data (e.g. world_map.json).
  - Bundled (app-owned): assets, i18n/ja, i18n/es, i18n/_meta.json, i18n/_template.json,
    i18n/_aexe_template (curation templates — no Arena source text, mapping metadata only),
    manual/simple.

[Important runtime premise] The public build ships no Arena assets, so the Arena original
text (required for matching in-game text at runtime) and world map are **regenerated
locally from the user's Arena directory** (asset generator + virtual file system + single
data pack + first-run generation). Until those are produced, this build's output has empty
game-text translation / facility data (the app itself still starts). **The role of this
spec is to mechanically guarantee a layout that contains no Arena assets.**

Build forms (two variants, both non-bundling):
  - Default = onefile (single exe, all files embedded). Set environment variable
    RTESA_ONEFILE=0 for onedir (zip + DLL).

Pre-publish contamination check (safety gate):
  - After building, run `python tools/check_public_build.py --build-dir
    build/RTESArenaAssist-public --dist dist/RTESArenaAssist-public` and confirm DENY 0.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path.cwd()
APP_DIR = ROOT / "apps" / "RTESArenaAssist"
# Assist は完全自己完結（他アプリ非依存）。memory_core/arena_logic/mif_trigger/
# viewer_constants/interior_id（旧 Probe）と cif_decoder/img_decoder/body_composite
# （旧 CharacterSheet）は Assist 配下へ取り込み済みのため pathex は APP_DIR のみ。

ONEFILE = os.environ.get("RTESA_ONEFILE", "1") == "1"

# --- Embed app-owned data into an in-exe seed pack ------------------------------
# `_internal` holds Python/PySide dependencies only. App-owned data
# (translations, assets, manual/simple, _aexe_template, fingerprints/golden) is not put
# in datas; tools/build_seed.py bundles it into a single seed zip embedded as
# `apps/RTESArenaAssist/_seed_data.py` (included in the PYZ). At runtime `app_resources`
# reads directly from the in-exe seed.
import importlib.util as _ilu
_bs_spec = _ilu.spec_from_file_location("build_seed", str(ROOT / "tools" / "build_seed.py"))
_bs = _ilu.module_from_spec(_bs_spec)
_bs_spec.loader.exec_module(_bs)
_seed_out = _bs.build(APP_DIR)
print(f"[public spec] seed 生成: {_seed_out}")

pyside_datas, pyside_binaries, pyside_hiddenimports = collect_all("PySide6")

# --- datas holds PySide/Python dependencies only (app-owned data goes to the seed) ------
# Do not add app-owned data (i18n/assets/manual etc.) or Arena-derived data here.
# Such additions are flagged DENY by tools/check_public_build.py.
datas = list(pyside_datas)

hiddenimports = pyside_hiddenimports + [
    "arena_logic",
    "body_composite",
    "cif_decoder",
    "img_decoder",
    "interior_id",
    "memory_core",
    "mif_trigger",
    "viewer_constants",
    "PySide6.QtMultimedia",
    # exe 内 seed パック（Assist 所有データ・ビルド時生成）＋その読込層。動的 import のため明示。
    "_seed_data",
    "app_resources",
]

a = Analysis(
    [str(APP_DIR / "assist_main.py")],
    pathex=[
        str(APP_DIR),
    ],
    binaries=pyside_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="RTESArenaAssist",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="RTESArenaAssist",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="RTESArenaAssist",
    )
