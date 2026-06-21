#!/usr/bin/env python3
"""Pre-publish contamination check (safety gate).

Checks that public build artifacts contain no Arena-derived data, game original-text
dictionaries, decoded assets, or local absolute paths. Run this as the **first safety
gate** on every build.

検査対象を分け、コード内の正当な拡張子文字列（`.MIF` 等）と
「資産ファイルの実体混入」を区別する。判定は path / 実ファイル単位で行い、
PYZ に取り込まれた Python バイトコード（拡張子文字列を含むコード）は対象外にする。

判定区分:
  DENY    … Arena 由来。公開物に入れてはならない（検出＝検査失敗・exit!=0）。
  REVIEW  … 由来要確認。人間が公開可否を判断するまで警告（exit は失敗にしない）。
  ALLOW   … アプリ所有。公開可。

使い方:
  python tools/check_public_build.py                 # 既定: ./RTESArenaAssist.spec + build/ + dist/
  python tools/check_public_build.py --build-dir build/RTESArenaAssist --dist dist
  python tools/check_public_build.py --json          # 機械可読出力
  python tools/check_public_build.py --strict-review # REVIEW も失敗扱いにする

exit code: DENY が 1 件でもあれば 2、（--strict-review 時は REVIEW でも 2）、
           検査対象が見つからない等の実行時問題は 1、混入なしは 0。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

# ---------------------------------------------------------------------------
# 判定ポリシー（データ分類）
# ---------------------------------------------------------------------------

DENY = "DENY"
REVIEW = "REVIEW"
ALLOW = "ALLOW"

# Arena 資産ファイルの拡張子（実ファイルとして混入していれば判定）。
# 注意: これらは「ファイル実体」に適用する。コード内文字列リテラルには適用しない。
#
# 高確信 Arena 拡張子（他用途で稀・実体混入なら DENY）。
ARENA_ASSET_EXTS_DENY = {
    ".mif", ".inf", ".rmd", ".bsa", ".cfa", ".dfa", ".cif",
    ".voc", ".xmi", ".ci2", ".65",
}
# 汎用的で誤検出し得る拡張子（Arena でも一般でも使われる）→ REVIEW 止まり。
# 例: .dat は ICU の icudtl.dat 等と衝突する。Arena 由来は path / 既知ファイル名で DENY。
ARENA_ASSET_EXTS_REVIEW = {
    ".img", ".set", ".col", ".xfm", ".dat",
}
# 既知の Arena ファイル名（拡張子が汎用でも実体ならば DENY）。
ARENA_ASSET_FILENAMES_DENY = {
    "template.dat", "namechnk.dat", "spellmkr.txt", "citydata.65",
    "global.bsa", "a.exe", "acd.exe",
}

# パスにこのセグメントを含む dest は Arena 由来として DENY。
# （区切りは正規化済みの "/" 前提で部分一致判定する）
DENY_PATH_SEGMENTS = (
    "arena-data/",          # decoded Arena assets
    "i18n/_original",       # game original text (holds source_text)
    "i18n/en",              # game original en (locally generated, not publishable; dir mount/file both)
    "manual/full",          # full Arena manual extraction
)

# dest がこの正確名（正規化済み）なら DENY。
DENY_EXACT = {
    "i18n/en.json",         # ゲーム原文 en（ルート集約版）
    "aexe_strings.json",    # A.EXE 抽出物（dev 専用・Arena 原文を含む）。公開版は
                            # ユーザー起動中メモリから採取するため同梱不可。
    "i18n/i18n_id_registry.json",   # 採番台帳（dev-only）。legacy_id に原文断片を含む。
    "i18n/legacy_id_map.json",      # 旧 ID→整数 ID の派生 map（dev-only・移行 adapter 用）。
    "i18n/location_citydata_map.json",  # app_id(slug)→citydata source_id（dev-only・slug 原文断片）。
    "i18n/placeholder_values_oc_source.json",  # %oc legacy_id(slug)→#0262 index（dev-only・slug 原文断片）。
    "i18n/placeholder_values_derived_map.json",  # derived placeholder legacy_id(slug)→target ID（dev-only・slug 原文断片）。
}

# 由来要確認（REVIEW）。Arena 由来の可能性があり機械的に断定しないもの。
REVIEW_PATH_SEGMENTS = (
    "services/data/",       # world_map.json は CITYDATA.65 由来と自己申告 → 要確認
    "manual/simple",        # Assist 独自要約のはずだが原文翻案でないことの確認が要る
)

# 明示的にアプリ所有として ALLOW（誤検出回避の許可リスト）。
ALLOW_PATH_SEGMENTS = (
    "i18n/ja/",
    "i18n/es/",
    "i18n/ui",
    "i18n/_aexe_template",   # curation テンプレート（src 写像＋メタのみ・原文非含）
    "assets/",
    # Assist 自身の UI 文言の en（Arena 原文ではない・公開可）。dist は _internal/ プレフィックスが
    # 付くため exact でなく部分一致で許可（i18n/en dir 一律 DENY の例外・対象 3 ファイルのみ）。
    "i18n/en/ui_app.json",
    "i18n/en/ui.json",
    "i18n/en/setup.json",
)
ALLOW_EXACT = {
    "i18n/_meta.json",
    "i18n/_template.json",
    "arena_fingerprints.json",       # 対応版指紋(SHA-256)。原文非含・公開同梱可。
    "arena_golden_manifest.json",    # 公開ゴールデンマニフェスト。原文非含・公開同梱可。
    "i18n/i18n_bundle.json",         # 公開 bundle。legacy_id/Arena 原文非含。
    "i18n/source_id_map.json",       # source_id→整数ID（bundle 派生・原文非含・公開同梱可）。
    "i18n/spell_effect_entries.json",  # 効果構造の正規データ（原文非含・ja/es 訳）。
}

# 絶対パス検出用パターン（ビルドログ/TOC/exe 文字列に残ってはならない）。
_DRIVE_PATH_RE = re.compile(rb"[A-Za-z]:\\\\?[^\x00\"'<>|]*", re.ASCII)
_USERS_PATH_RE = re.compile(rb"[/\\]Users[/\\][^\x00\"'<>|/\\]+", re.IGNORECASE)


@dataclass
class Finding:
    verdict: str          # DENY / REVIEW
    category: str         # 検査対象（spec.datas / toc / dist / abspath）
    dest: str             # 成果物内の相対パス・または対象識別子
    reason: str
    source: str = ""      # 由来（TOC のソースパス等。abspath 検査では伏せる）


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    @property
    def denies(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict == DENY]

    @property
    def reviews(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict == REVIEW]


# ---------------------------------------------------------------------------
# 分類
# ---------------------------------------------------------------------------

def _norm(dest: str) -> str:
    """dest を小文字・スラッシュ区切りに正規化（先頭の ./ や \\ を吸収）。"""
    d = dest.replace("\\", "/").lstrip("./").lower()
    return d


def classify_dest(dest: str) -> tuple[str, str]:
    """成果物内 dest パスを DENY / REVIEW / ALLOW に分類する。

    優先順位: ALLOW 明示 > DENY（パス・拡張子）> REVIEW > ALLOW（既定）。
    DENY を取りこぼさないため、ALLOW 明示のみ先に確定させ、それ以外は
    Arena 由来の判定を先に評価する。
    """
    d = _norm(dest)

    if d in ALLOW_EXACT:
        return ALLOW, "allow-list (exact)"
    for seg in ALLOW_PATH_SEGMENTS:
        if seg in d:
            return ALLOW, f"allow-list segment '{seg}'"

    if d in DENY_EXACT:
        return DENY, "game-original (exact dest)"
    for seg in DENY_PATH_SEGMENTS:
        if seg in d:
            return DENY, f"Arena-derived path segment '{seg}'"

    base = d.rsplit("/", 1)[-1]
    if base in ARENA_ASSET_FILENAMES_DENY:
        return DENY, f"known Arena asset filename '{base}'"

    ext = os.path.splitext(d)[1]
    if ext in ARENA_ASSET_EXTS_DENY:
        return DENY, f"Arena asset file extension '{ext}'"

    for seg in REVIEW_PATH_SEGMENTS:
        if seg in d:
            return REVIEW, f"possibly Arena-derived segment '{seg}'"

    if ext in ARENA_ASSET_EXTS_REVIEW:
        return REVIEW, f"generic ext '{ext}' (Arena-or-common) — verify origin"

    return ALLOW, "app-owned (default)"


# ---------------------------------------------------------------------------
# 1) .spec の datas 静的検査
# ---------------------------------------------------------------------------

def check_spec(spec_path: str, report: Report) -> None:
    """`.spec` ソースから datas の dest（同梱先）リテラルを抽出し分類する。

    .spec は Python ロジックを含むため完全実行はせず、文字列リテラルとして
    現れる「同梱先」(各 datas タプルの第2要素) を AST から拾って静的に評価する。
    あくまで早期警告であり、権威ある判定は TOC / dist 検査（後段）が行う。
    """
    if not os.path.isfile(spec_path):
        report.notes.append(f"[skip] spec が見つからない: {spec_path}")
        return
    report.checked.append(f"spec.datas ({spec_path})")
    with open(spec_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:  # pragma: no cover - 異常系
        report.notes.append(f"[warn] spec を解析できない: {exc}")
        return

    def _last_str_const(node) -> str | None:
        """ノード内の最後の文字列定数を返す（datas src の basename 推定用）。

        例: ``str(APP_DIR / "i18n" / "en" / "ui_app.json")`` → ``"ui_app.json"``。
        src がファイル指定なら dest(=dir)+basename でフル dest を作り精密判定する。
        Name 等で文字列定数が無ければ None（＝dir mount とみなし dest のみで判定）。
        """
        # ソース上で最も右（最大 lineno,col_offset）の文字列定数＝パス式の basename。
        # ast.walk は BFS のため出現順に頼れない。位置で最右を選ぶ。
        best_pos = None
        best_val = None
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                pos = (getattr(sub, "lineno", 0), getattr(sub, "col_offset", 0))
                if best_pos is None or pos > best_pos:
                    best_pos = pos
                    best_val = sub.value
        return best_val

    # (src, dest) 形式の 2 要素タプル/リストから「実効 dest」を収集。
    # src がファイル(拡張子あり)なら dest_dir + basename、それ以外は dest_dir。
    dests: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 2:
            second = node.elts[1]
            if isinstance(second, ast.Constant) and isinstance(second.value, str):
                dest_dir = second.value
                base = _last_str_const(node.elts[0])
                if base and os.path.splitext(base)[1] and "/" not in base \
                        and "\\" not in base:
                    dests.add(dest_dir.rstrip("/\\") + "/" + base)
                else:
                    dests.add(dest_dir)

    # ディレクトリ丸ごと同梱で Arena 由来サブツリーを巻き込む典型パターンを警告。
    # 例: `(APP_DIR/"i18n", "i18n")` は _original/en を含むのに dest は "i18n" だけ。
    # ただし同一 datas に明示サブ mount（i18n/ja 等）があれば、bare "i18n" は単一
    # ファイル(_meta.json 等)の mount とみなし警告しない（公開 spec の正当パターン）。
    MIXED_DIR_MOUNTS = {
        "i18n": "i18n ツリー全体を同梱（_original/en を含む）。ja/es/ui/_meta のみ明示同梱に分割せよ",
    }
    norm_dests = {_norm(d).rstrip("/") for d in dests}
    for dest in sorted(dests):
        nd = _norm(dest).rstrip("/")
        if nd in MIXED_DIR_MOUNTS:
            has_explicit_subdir = any(
                other != nd and other.startswith(nd + "/") for other in norm_dests)
            if has_explicit_subdir:
                continue  # 明示サブ mount あり → bare は単一ファイル mount とみなす
            report.add(Finding(REVIEW, "spec.datas", dest, MIXED_DIR_MOUNTS[nd],
                               source=spec_path))
            continue
        verdict, reason = classify_dest(dest)
        if verdict in (DENY, REVIEW):
            report.add(Finding(verdict, "spec.datas", dest, reason, source=spec_path))


# ---------------------------------------------------------------------------
# 2) PyInstaller TOC（Analysis / PKG）検査 — 権威ある収集物
# ---------------------------------------------------------------------------

def _iter_toc_entries(toc_path: str):
    """TOC ファイルから (dest, source, typecode) のタプルを取り出す。

    TOC は Python リテラル（ネストした list/tuple）。ast.literal_eval で
    安全に評価し、3 要素タプル (name, path, typecode) を再帰的に拾う。
    """
    with open(toc_path, "r", encoding="utf-8") as fh:
        data = ast.literal_eval(fh.read())

    def walk(obj):
        if isinstance(obj, (list, tuple)):
            if (
                len(obj) == 3
                and isinstance(obj[0], str)
                and isinstance(obj[1], (str, type(None)))
                and isinstance(obj[2], str)
            ):
                yield obj[0], obj[1], obj[2]
            else:
                for item in obj:
                    yield from walk(item)

    yield from walk(data)


def check_toc(build_dir: str, report: Report) -> None:
    """build_dir 内の Analysis-*.toc / PKG-*.toc を検査する。

    typecode が 'DATA'/'BINARY' 等の **収集ファイル** のみ分類する。
    'PYMODULE' / 'PYSOURCE' （Python コード）は拡張子文字列を含み得ても
    資産混入ではないため対象外（コード文字列と資産混入の区別）。
    """
    if not os.path.isdir(build_dir):
        report.notes.append(f"[skip] build ディレクトリが見つからない: {build_dir}")
        return
    toc_files = [
        os.path.join(build_dir, n)
        for n in sorted(os.listdir(build_dir))
        if n.lower().endswith(".toc")
    ]
    if not toc_files:
        report.notes.append(f"[skip] TOC が build ディレクトリに無い: {build_dir}")
        return

    code_typecodes = {"PYMODULE", "PYSOURCE", "PYZ", "DEPENDENCY"}
    for toc in toc_files:
        report.checked.append(f"toc ({os.path.basename(toc)})")
        try:
            entries = list(_iter_toc_entries(toc))
        except (ValueError, SyntaxError) as exc:
            report.notes.append(f"[warn] TOC を解析できない: {toc}: {exc}")
            continue
        for dest, src, typecode in entries:
            if typecode.upper() in code_typecodes:
                continue
            verdict, reason = classify_dest(dest)
            if verdict in (DENY, REVIEW):
                report.add(
                    Finding(verdict, "toc", dest,
                            f"{reason} [{typecode}]", source=src or "")
                )


# ---------------------------------------------------------------------------
# 3) dist ツリー（出力された実ファイル）検査 + シグネチャ
# ---------------------------------------------------------------------------

# 実体検出（best-effort）: 拡張子を偽装しても中身で Arena 形式を疑うためのマーカ。
_INF_MARKERS = (b"*TEXT", b"@FLAT", b"#GENERAL")
_BSA_HINT_NAME = re.compile(r"global\.bsa$", re.IGNORECASE)


def sniff_signature(path: str) -> str | None:
    """ファイル先頭を覗いて Arena 由来らしさを返す（best-effort, 拡張子偽装対策）。

    None = 判定材料なし。確証検出ではなく「疑い」を返す補助。
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    if not head:
        return None
    if any(m in head for m in _INF_MARKERS):
        return "INF-like markers (*TEXT/@FLAT)"
    if _BSA_HINT_NAME.search(os.path.basename(path)):
        return "GLOBAL.BSA by name"
    return None


def check_dist(dist_dir: str, report: Report, exe_names: tuple[str, ...] = ()) -> None:
    """dist 配下の実ファイルを走査して分類する（onedir 想定の権威検査）。

    onefile ビルドでは exe 1 本に同梱が畳まれるため dist ツリー上に資産は
    現れない（埋め込みは TOC 検査が担保する）。両形態で本検査は無害。
    実行時生成物（logs/output/saves_backup/設定/ログ）は成果物ではないため除外。
    """
    if not os.path.isdir(dist_dir):
        report.notes.append(f"[skip] dist が見つからない: {dist_dir}")
        return
    report.checked.append(f"dist tree ({dist_dir})")

    runtime_dirs = {"logs", "output", "saves_backup"}
    runtime_files = {"assist_debug.log", "assist_settings.json"}

    for root, dirs, files in os.walk(dist_dir):
        rel_root = os.path.relpath(root, dist_dir)
        top = rel_root.split(os.sep)[0] if rel_root != "." else ""
        if top in runtime_dirs:
            dirs[:] = []
            continue
        for name in files:
            if rel_root == "." and name in runtime_files:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, dist_dir).replace("\\", "/")
            verdict, reason = classify_dest(rel)
            if verdict in (DENY, REVIEW):
                report.add(Finding(verdict, "dist", rel, reason, source=full))
                continue
            # ALLOW でもシグネチャで Arena 形式を疑えば REVIEW で拾う。
            sig = sniff_signature(full)
            if sig:
                report.add(Finding(REVIEW, "dist:signature", rel,
                                   f"content looks Arena-derived: {sig}", source=full))
            # 公開 bundle の内容安全（原文非漏洩を内容検査）。
            if name == "i18n_bundle.json":
                check_bundle_public_safe(full, report, dest=rel)


def _debug_name_unsafe(dn: str) -> bool:
    """非 assist_bundled の debug_name が原文/旧 string-ID 型で公開不可か。

    構造名（source-backed は `:`／spell_effect は `effect_<n>_sub_<m>` 等／
    owner/context 構造名）は安全。旧 string-ID 型（`category.<原文語>` ＝ `.` を含み `:` を
    含まない）と、空白を含む原文断片は公開不可。
    """
    s = str(dn)
    if any(c.isspace() for c in s):
        return True                       # 原文文/語（空白含み）
    if "." in s and ":" not in s:
        return True                       # 旧 string-ID 型（mages.Acid 等）
    return False


def check_bundle_public_safe(bundle_path: str, report: Report,
                             *, dest: str = "i18n_bundle.json") -> None:
    """公開 bundle が原文非漏洩で安全か内容検査する。

    - en locale は assist_bundled の entry にのみ載る（Arena 原文 en 非漏洩）。
    - 非 assist_bundled の `debug_name` は None か構造名のみ（原文断片・旧 string-ID 型を禁止）。
    検出は DENY（公開不可）。`dest` は成果物内の相対パス（報告用）。
    """
    report.checked.append(f"bundle ({dest})")
    try:
        with open(bundle_path, "r", encoding="utf-8") as fh:
            bundle = json.load(fh)
    except (OSError, ValueError) as exc:
        report.add(Finding(REVIEW, "bundle", dest, f"読み取り/解析失敗: {exc}"))
        return
    assist_ids: set = set()
    nonassist_ids: set = set()
    for cat in bundle.get("categories", []):
        ids = {e.get("id") for e in cat.get("entries", [])}
        if cat.get("source_policy") == "assist_bundled":
            assist_ids |= ids
        else:
            nonassist_ids |= ids
        # debug_name の構造性（非 assist_bundled のみ厳格・assist は人間可読可）。
        if cat.get("source_policy") != "assist_bundled":
            for e in cat.get("entries", []):
                dn = e.get("debug_name")
                if dn and _debug_name_unsafe(dn):
                    report.add(Finding(
                        DENY, "bundle", dest,
                        f"non-structural debug_name (原文/旧ID 疑い) id={e.get('id')}: {dn!r}"))
    # en locale が非 assist_bundled の id に載っていないこと（Arena 原文 en 非漏洩）。
    for loc in bundle.get("locales", []):
        if loc.get("locale") not in ("en", "en-US"):
            continue
        for t in loc.get("texts", []):
            tid = t.get("id") if isinstance(t, dict) else (t[0] if t else None)
            if tid in nonassist_ids:
                report.add(Finding(
                    DENY, "bundle", dest,
                    f"en text on non-assist_bundled id={tid}（Arena 原文 en 漏洩）"))


# ---------------------------------------------------------------------------
# 3b) _internal=Python依存のみ検査 — Assist 所有データの非設置を保証
# ---------------------------------------------------------------------------

# 公開 dist の `_internal`（および dist 直下）に在ってはならない Assist 所有データの root。
# これらは exe 内 seed に埋め込み、_internal は Python/PySide 依存のみとする。
APP_OWNED_ROOTS = ("i18n", "assets", "manual")


def check_internal_deps_only(dist_dir: str, report: Report) -> None:
    """公開 dist に Assist 所有データ（i18n/assets/manual）が在らないことを保証する。

    onedir の `_internal` は Python/PySide 依存のみ。Assist データを `datas` に戻して同梱すると
    `_internal/<root>` が出現するため、その直下に owned root があれば DENY（exit!=0）。
    PySide 由来（`_internal/PySide6/...`）等は対象外（owned root の直下出現のみを見る）。
    """
    if not os.path.isdir(dist_dir):
        return
    report.checked.append("internal-deps-only")
    owned = {r.lower() for r in APP_OWNED_ROOTS}
    # 検査する親ディレクトリ: dist 直下、各 onedir フォルダの `_internal`、dist 直下の `_internal`。
    parents: list[str] = [dist_dir]
    try:
        for name in os.listdir(dist_dir):
            p = os.path.join(dist_dir, name)
            if not os.path.isdir(p):
                continue
            if name == "_internal":
                parents.append(p)
            internal = os.path.join(p, "_internal")
            if os.path.isdir(internal):
                parents.append(internal)
    except OSError:
        return
    for parent in parents:
        try:
            for name in os.listdir(parent):
                if name.lower() in owned and os.path.isdir(os.path.join(parent, name)):
                    rel = os.path.relpath(os.path.join(parent, name),
                                          dist_dir).replace("\\", "/")
                    report.add(Finding(
                        DENY, "internal-deps-only", rel,
                        "Assist 所有データが _internal/dist に在る"
                        "（_internal は Python 依存のみ・exe 内 seed へ移すこと）"))
        except OSError:
            continue


# ---------------------------------------------------------------------------
# 4) 絶対パス残存検査（dist の exe / TOC テキスト）
# ---------------------------------------------------------------------------

def check_absolute_paths(targets: list[str], report: Report) -> None:
    """成果物バイナリ/テキストにローカル絶対パスが残っていないか検査する。

    ユーザー名やドライブを含む絶対パスは公開物に残してはならない。
    誤検出があり得るため REVIEW（警告）として報告する。
    """
    home = os.path.expanduser("~").replace("\\", "/")
    user = os.path.basename(home) if home else ""
    for path in targets:
        if not os.path.isfile(path):
            continue
        report.checked.append(f"abspath ({os.path.basename(path)})")
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except OSError:
            continue
        hits: set[str] = set()
        if user:
            for m in _USERS_PATH_RE.finditer(blob):
                seg = m.group(0).decode("latin-1", "replace")
                if user.lower() in seg.lower():
                    hits.add(seg)
        # Users\<name> を含むものに限定（ドライブ単体は誤検出が多いので絞る）。
        for h in sorted(hits):
            report.add(Finding(REVIEW, "abspath", os.path.basename(path),
                               f"local user path embedded: {h}"))


# ---------------------------------------------------------------------------
# レポート出力
# ---------------------------------------------------------------------------

def render_text(report: Report) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("公開前混入検査（安全柵）")
    lines.append("=" * 64)
    lines.append("検査した対象:")
    for c in report.checked:
        lines.append(f"  - {c}")
    if report.notes:
        lines.append("")
        lines.append("注記:")
        for n in report.notes:
            lines.append(f"  {n}")

    denies, reviews = report.denies, report.reviews
    lines.append("")
    if denies:
        lines.append(f"[NG] DENY（公開不可・混入）: {len(denies)} 件")
        for f in denies:
            lines.append(f"  [{f.category}] {f.dest}")
            lines.append(f"      理由: {f.reason}")
            if f.source:
                lines.append(f"      由来: {f.source}")
    else:
        lines.append("[OK] DENY（Arena 由来混入）: 0 件")

    lines.append("")
    if reviews:
        lines.append(f"[!!] REVIEW（要確認）: {len(reviews)} 件")
        for f in reviews:
            lines.append(f"  [{f.category}] {f.dest} — {f.reason}")
    else:
        lines.append("REVIEW（要確認）: 0 件")

    lines.append("")
    lines.append("=" * 64)
    if denies:
        lines.append("判定: 失敗（Arena 由来データが混入しています）")
    elif reviews:
        lines.append("判定: 要確認（DENY は無し。REVIEW を人間が確認のこと）")
    else:
        lines.append("判定: 合格（混入なし）")
    lines.append("=" * 64)
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(
        {
            "checked": report.checked,
            "notes": report.notes,
            "deny": [vars(f) for f in report.denies],
            "review": [vars(f) for f in report.reviews],
            "pass": len(report.denies) == 0,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run(spec: str, build_dir: str, dist: str) -> Report:
    report = Report()
    check_spec(spec, report)
    check_toc(build_dir, report)
    check_dist(dist, report)
    check_internal_deps_only(dist, report)
    # 絶対パス検査の対象: dist 内の exe と TOC テキスト。
    abspath_targets: list[str] = []
    if os.path.isdir(dist):
        for name in os.listdir(dist):
            if name.lower().endswith(".exe"):
                abspath_targets.append(os.path.join(dist, name))
    check_absolute_paths(abspath_targets, report)
    _dedup(report)
    return report


def _dedup(report: Report) -> None:
    """同一 (verdict, category, dest, reason) の重複（Analysis/PKG TOC 等）を畳む。"""
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[Finding] = []
    for f in report.findings:
        key = (f.verdict, f.category, _norm(f.dest), f.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    report.findings[:] = unique


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="公開前混入検査（安全柵）")
    ap.add_argument("--spec", default="RTESArenaAssist.spec")
    ap.add_argument("--build-dir", default=os.path.join("build", "RTESArenaAssist"))
    ap.add_argument("--dist", default="dist")
    ap.add_argument("--json", action="store_true", help="JSON 出力")
    ap.add_argument("--strict-review", action="store_true",
                    help="REVIEW も失敗扱いにする")
    args = ap.parse_args(argv)

    # cp932 コンソールでも UTF-8 で安定出力する（リダイレクト/Read 前提）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    report = run(args.spec, args.build_dir, args.dist)

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))

    if report.denies:
        return 2
    if args.strict_review and report.reviews:
        return 2
    if not report.checked:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
