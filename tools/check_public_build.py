#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath


DENY = "DENY"
REVIEW = "REVIEW"
ALLOW = "ALLOW"

ARENA_ASSET_EXTS_DENY = {
    ".mif", ".inf", ".rmd", ".bsa", ".cfa", ".dfa", ".cif",
    ".voc", ".xmi", ".ci2", ".65",
}
ARENA_ASSET_EXTS_REVIEW = {
    ".img", ".set", ".col", ".xfm", ".dat",
}
ARENA_ASSET_FILENAMES_DENY = {
    "template.dat", "namechnk.dat", "spellmkr.txt", "citydata.65",
    "global.bsa", "a.exe", "acd.exe",
}

DENY_PATH_SEGMENTS = (
    "arena-data/",
    "i18n/_original",
    "i18n/en",
    "manual/full",
)

DENY_EXACT = {
    "i18n/en.json",
    "aexe_strings.json",
    "i18n/i18n_id_registry.json",
    "i18n/legacy_id_map.json",
    "i18n/location_citydata_map.json",
    "i18n/placeholder_values_oc_source.json",
    "i18n/placeholder_values_derived_map.json",
}

REVIEW_PATH_SEGMENTS = (
    "services/data/",
    "manual/simple",
)

ALLOW_PATH_SEGMENTS = (
    "i18n/ja/",
    "i18n/es/",
    "i18n/ui",
    "i18n/_aexe_template",
    "assets/",
    "i18n/en/ui_app.json",
    "i18n/en/ui.json",
    "i18n/en/setup.json",
)
ALLOW_EXACT = {
    "i18n/_meta.json",
    "i18n/_template.json",
    "arena_fingerprints.json",
    "arena_golden_manifest.json",
    "i18n/i18n_bundle.json",
    "i18n/source_id_map.json",
    "i18n/spell_effect_entries.json",
}

_DRIVE_PATH_RE = re.compile(rb"[A-Za-z]:\\\\?[^\x00\"'<>|]*", re.ASCII)
_USERS_PATH_RE = re.compile(rb"[/\\]Users[/\\][^\x00\"'<>|/\\]+", re.IGNORECASE)


@dataclass
class Finding:
    verdict: str
    category: str
    dest: str
    reason: str
    source: str = ""


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



def _norm(dest: str) -> str:
    d = dest.replace("\\", "/").lstrip("./").lower()
    return d


def classify_dest(dest: str) -> tuple[str, str]:
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



def check_spec(spec_path: str, report: Report) -> None:
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
        best_pos = None
        best_val = None
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                pos = (getattr(sub, "lineno", 0), getattr(sub, "col_offset", 0))
                if best_pos is None or pos > best_pos:
                    best_pos = pos
                    best_val = sub.value
        return best_val

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
                continue
            report.add(Finding(REVIEW, "spec.datas", dest, MIXED_DIR_MOUNTS[nd],
                               source=spec_path))
            continue
        verdict, reason = classify_dest(dest)
        if verdict in (DENY, REVIEW):
            report.add(Finding(verdict, "spec.datas", dest, reason, source=spec_path))



def _iter_toc_entries(toc_path: str):
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



_INF_MARKERS = (b"*TEXT", b"@FLAT", b"#GENERAL")
_BSA_HINT_NAME = re.compile(r"global\.bsa$", re.IGNORECASE)


def sniff_signature(path: str) -> str | None:
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
            sig = sniff_signature(full)
            if sig:
                report.add(Finding(REVIEW, "dist:signature", rel,
                                   f"content looks Arena-derived: {sig}", source=full))
            if name == "i18n_bundle.json":
                check_bundle_public_safe(full, report, dest=rel)


def _debug_name_unsafe(dn: str) -> bool:
    s = str(dn)
    if any(c.isspace() for c in s):
        return True
    if "." in s and ":" not in s:
        return True
    return False


def check_bundle_public_safe(bundle_path: str, report: Report,
                             *, dest: str = "i18n_bundle.json") -> None:
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
        if cat.get("source_policy") != "assist_bundled":
            for e in cat.get("entries", []):
                dn = e.get("debug_name")
                if dn and _debug_name_unsafe(dn):
                    report.add(Finding(
                        DENY, "bundle", dest,
                        f"non-structural debug_name (原文/旧ID 疑い) id={e.get('id')}: {dn!r}"))
    for loc in bundle.get("locales", []):
        if loc.get("locale") not in ("en", "en-US"):
            continue
        for t in loc.get("texts", []):
            tid = t.get("id") if isinstance(t, dict) else (t[0] if t else None)
            if tid in nonassist_ids:
                report.add(Finding(
                    DENY, "bundle", dest,
                    f"en text on non-assist_bundled id={tid}（Arena 原文 en 漏洩）"))



APP_OWNED_ROOTS = ("i18n", "assets", "manual")


def check_internal_deps_only(dist_dir: str, report: Report) -> None:
    if not os.path.isdir(dist_dir):
        return
    report.checked.append("internal-deps-only")
    owned = {r.lower() for r in APP_OWNED_ROOTS}
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



def check_absolute_paths(targets: list[str], report: Report) -> None:
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
        for h in sorted(hits):
            report.add(Finding(REVIEW, "abspath", os.path.basename(path),
                               f"local user path embedded: {h}"))



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



def run(spec: str, build_dir: str, dist: str) -> Report:
    report = Report()
    check_spec(spec, report)
    check_toc(build_dir, report)
    check_dist(dist, report)
    check_internal_deps_only(dist, report)
    abspath_targets: list[str] = []
    if os.path.isdir(dist):
        for name in os.listdir(dist):
            if name.lower().endswith(".exe"):
                abspath_targets.append(os.path.join(dist, name))
    check_absolute_paths(abspath_targets, report)
    _dedup(report)
    return report


def _dedup(report: Report) -> None:
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
