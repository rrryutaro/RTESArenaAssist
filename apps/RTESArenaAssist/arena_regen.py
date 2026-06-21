"""arena_regen.py — Arena 資産からの決定論生成コア（アプリ側・公開版で使用）。

building_entry（TEMPLATE.DAT #0000-#0004・全 tileset copy）を
`source_id`/`source_hash` 付きで決定論再生成する純粋コア。**公開版は tools/ を同梱しない**ため、
アプリが初回起動生成（ユーザー Arena 資産→単一データパック）で使う生成ロジックは本モジュール
（apps/ 配下）に置く。CLI ツール `tools/i18n_regen_and_diff.py` も本モジュールを再利用する。

本モジュール自体に Arena 原文は含まれない（生成規則のみ）。公開物に同梱してよい。
EXE 由来（A.EXE）カテゴリは後続フェーズ。本モジュールは TEMPLATE.DAT 由来 building_entry のみ。
"""
from __future__ import annotations

import hashlib
import re

import i18n_source_address as sa

GENERATOR_VERSION = "be-2"  # building_entry 生成器バージョン（全 copy 対応）
CATEGORY = "template_dat_building_entry"
KEY_PREFIX = f"{CATEGORY}."

TARGET_BLOCKS = ("0000", "0001", "0002", "0003", "0004")
_KEY_RE = re.compile(r"^#([0-9]+)([a-zA-Z]?)$")
_PLACEHOLDER_RE = re.compile(r"%([a-zA-Z][a-zA-Z0-9]*)")


def parse_template_dat_bytes(raw: bytes) -> list[dict]:
    """TEMPLATE.DAT（バイト列）を #<num><letter> 単位に分解する。

    本文を '&' で変種に分割し空白を畳む。同 (key, letter) 再出現順に tileset copy
    index 0,1,2... を割り当てる（OpenTESArena entryLists[index] と整合）。
    行末ハイフン折返し `-\\n` は空白へ畳む（plain 正規化）。現 _original は #1314 等で
    `-\\n` の扱いが手作業で不統一なため、決定論変換では結合せず faithful に保つ（結合が
    正しいかは実機観測待ち＝推測でルール化しない）。
    """
    text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    entries: list[dict] = []
    seen_count: dict[tuple[str, str], int] = {}
    i = 0
    while i < len(lines):
        m = _KEY_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        key, letter = m.group(1), m.group(2) or ""
        buf: list[str] = []
        j = i + 1
        while j < len(lines) and not _KEY_RE.match(lines[j].strip()):
            buf.append(lines[j])
            j += 1
        body = "\n".join(buf)
        values = [" ".join(part.split()) for part in body.split("&")]
        values = [v for v in values if v]
        copy_idx = seen_count.get((key, letter), 0)
        seen_count[(key, letter)] = copy_idx + 1
        entries.append({"key": key, "letter": letter,
                        "copy": copy_idx, "values": values})
        i = j
    return entries


def _placeholders(value: str) -> list[str]:
    seen: list[str] = []
    for m in _PLACEHOLDER_RE.finditer(value):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def regenerate_building_entry_bytes(raw: bytes) -> dict[str, dict]:
    """建物入店メッセージを**全 copy**で再構築する（TEMPLATE.DAT バイト列版）。

    Returns {app_id: entry}。app_id=template_dat_building_entry.<block>.copy<c>.<variant>、
    source_id=template:<block>:<copy>:<variant>。
    """
    entries = parse_template_dat_bytes(raw)
    out: dict[str, dict] = {}
    for e in entries:
        if e["key"] not in TARGET_BLOCKS:
            continue
        block = f"{e['key']}_{e['letter']}" if e["letter"] else e["key"]
        copy = e["copy"]
        for vi, value in enumerate(e["values"]):
            app_id = f"{KEY_PREFIX}{block}.copy{copy}.{vi}"
            out[app_id] = {
                "original": value,
                "source_id": sa.template_id(block, vi, copy=copy),
                "source_hash": sa.source_hash(value),
                "key": e["key"],
                "letter": e["letter"] or None,
                "copy": copy,
                "placeholders": _placeholders(value),
            }
    return out


def build_original_json(new_entries: dict[str, dict]) -> dict:
    """新 _original/<cat>.json の内容（id 昇順・決定論）。"""
    out: dict[str, dict] = {}
    for app_id in sorted(new_entries):
        e = new_entries[app_id]
        out[app_id] = {
            "original": e["original"],
            "source_id": e["source_id"],
            "source_hash": e["source_hash"],
            "key": e["key"],
            "letter": e["letter"],
            "copy": e["copy"],
            "placeholders": e["placeholders"],
        }
    return out


# ---------------------------------------------------------------------------
# npc_dialog（TEMPLATE.DAT #NNNN・NPC 会話/ルーラー依頼/うわさ 等）の決定論再生成
# ---------------------------------------------------------------------------
# building_entry（#0000-#0004・tileset copy 軸あり）とは別カテゴリ。npc_dialog 系
# block は全て **単一 copy**（複数 copy を持つのは building_entry のみ）。本生成器は
# Arena から決定論再現できる範囲のみを返し、Assist 自作（A-key 等）・手動クリーンアップ
# override・glossary terms 等の curation は呼び出し側（curation 資産）が合成する。
#
# 再現規則（検証で確定）:
#   1. generic = bare 数値 block `#NNNN`（letter 無し）の copy0 variant を plain 正規化。
#   2. special = `#0014a`〜`#0014l`（ルーラー依頼文・letter 12 種・各 plain 正規化）を
#      出現順に集めて first-seen 重複除去 → 単一 block "0014" に平坦化（現 _original 一致）。
#   plain 正規化 = '&' 分割後に空白（改行含む）を 1 個へ畳む（building_entry と同一）。

NPC_DIALOG_GENERATOR_VERSION = "npcd-1"
NPC_DIALOG_CATEGORY = "npc_dialog"
NPC_DIALOG_KEY_PREFIX = f"{NPC_DIALOG_CATEGORY}."

# ルーラー依頼文（#0014a..l）→ 単一 block "0014" への平坦化対象 letter（出現順）。
_NPC_DIALOG_FLATTEN = {"0014": tuple("abcdefghijkl")}


def _npc_block_label(key: str) -> str:
    """TEMPLATE.DAT の数値 key を _original 互換の 4 桁 block ラベルにする。"""
    return f"{int(key):04d}"


def _npc_emit(out: dict[str, dict], block: str, values: list[str]) -> None:
    """block ラベルと variant 列から app_id 付きエントリを out へ追加する。"""
    for vi, value in enumerate(values):
        app_id = f"{NPC_DIALOG_KEY_PREFIX}{block}.{vi}"
        out[app_id] = {
            "original": value,
            "source_id": sa.template_id(block, vi),
            "source_hash": sa.source_hash(value),
            # 現 _original は placeholders を昇順ソートで保持する（出現順でない）。
            "placeholders": sorted(set(_placeholders(value))),
        }


def regenerate_npc_dialog_bytes(raw: bytes) -> dict[str, dict]:
    """npc_dialog の **Arena 再現可能分のみ** を再構築する（TEMPLATE.DAT バイト列版）。

    Returns {app_id: entry}。app_id=npc_dialog.<block>.<variant>、
    source_id=template:<block>:<variant>（copy 次元なし＝npc_dialog 系は単一 copy）。
    Assist 自作・override・terms 等の curation は含まない（呼び出し側が合成）。
    全 TEMPLATE 数値 block を網羅出力し、どの app_id を採用するかは curation 側の選択に委ねる。
    """
    entries = parse_template_dat_bytes(raw)
    # letter ごとに values を引けるよう索引化（copy0 のみ・npc_dialog 系は単一 copy）。
    by_key_letter: dict[tuple[str, str], list[str]] = {}
    for e in entries:
        if e["copy"] != 0:
            continue
        by_key_letter[(e["key"], e["letter"])] = e["values"]

    out: dict[str, dict] = {}
    # generic: bare 数値 block（letter 無し）。building_entry（#0000-#0004）は別カテゴリ
    # なので明示除外する（通常 bare を持たないが念のため）。
    for (key, letter), values in by_key_letter.items():
        if letter or key in TARGET_BLOCKS:
            continue
        _npc_emit(out, _npc_block_label(key), values)
    # special: #0014a..l を平坦化（first-seen 重複除去）。lookup は parse が保持する
    # 生のキー文字列（先頭ゼロ込み）で行う。
    for block, letters in _NPC_DIALOG_FLATTEN.items():
        flat: list[str] = []
        seen: set[str] = set()
        for letter in letters:
            for v in by_key_letter.get((block, letter), []):
                if v not in seen:
                    seen.add(v)
                    flat.append(v)
        if flat:
            _npc_emit(out, block, flat)
    return out


def build_npc_dialog_original_json(new_entries: dict[str, dict]) -> dict:
    """npc_dialog の _original 内容（id 昇順・決定論）。

    消費側（npc_dialog_lookup）が参照する original/placeholders を保持し、住所
    source_id/source_hash を付す。building_entry と違い copy/letter 次元は持たない。
    """
    out: dict[str, dict] = {}
    for app_id in sorted(new_entries):
        e = new_entries[app_id]
        out[app_id] = {
            "original": e["original"],
            "source_id": e["source_id"],
            "source_hash": e["source_hash"],
            "placeholders": e["placeholders"],
        }
    return out


def fingerprint_bytes(raw: bytes) -> str:
    """対象バイト列の sha256 hex 先頭 16 桁（版指紋）。"""
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_manifest(new_entries: dict[str, dict], fingerprint: str,
                    category: str, generator_version: str) -> dict:
    """ゴールデンマニフェスト共通ビルダー（原文なし・情報最小化）。"""
    entries = {e["source_id"]: e["source_hash"] for e in new_entries.values()}
    return {
        sa.MANIFEST_VERSION: generator_version,
        sa.MANIFEST_GENERATOR: f"arena_regen/{generator_version}",
        sa.MANIFEST_FINGERPRINT: fingerprint,
        sa.MANIFEST_DIGEST: sa.manifest_digest(entries),
        "category": category,
        sa.MANIFEST_ENTRIES: entries,
    }


def build_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    """building_entry のゴールデンマニフェスト。"""
    return _build_manifest(new_entries, fingerprint, CATEGORY, GENERATOR_VERSION)


def build_npc_dialog_manifest(new_entries: dict[str, dict],
                              fingerprint: str) -> dict:
    """npc_dialog のゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, NPC_DIALOG_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# inf_text（INF @TEXT・ダンジョン銘板/うわさ/リドル/鍵）の決定論再生成
# ---------------------------------------------------------------------------
# 出典 = 各 INF ファイルの @TEXT セクション（OpenTESArena 準拠の *TEXT N パーサ）。
# 現フェーズ対象は **INF @TEXT 由来のみ**。`_CHARGEN_*`（キャラ作成 10 質問・非 INF・
# A.EXE/CLASSES.DAT 系で出典未確定）は EXE 由来カテゴリ。`TEMPLATE_DAT_*`（main quest メッセージ・
# TEMPLATE.DAT 由来）は別経路（本生成器の対象外）。
#
# 消費側（inf_text_lookup）は parent を (inf, idx) で索引し、riddle は
# `<base>.question/.correct/.wrong` のサブ id を束ねる。よって parent＋サブを再現する。
# type/key_id/params/answers は parser から決定論導出（検証で 387/387・mismatch 0）。

INF_TEXT_GENERATOR_VERSION = "inf-1"
INF_TEXT_CATEGORY = "inf_text"


def _parse_inf_text_section(raw: bytes, inf_name: str) -> list[dict]:
    """1 INF ファイル（バイト列）の @TEXT を *TEXT N 単位に分解する。

    build_inf_text_db の parse_inf_file と同一規則（公開コアへ移植・tools/ 非依存）。
    Returns 各 (inf, idx) の構造化 dict（type/text/key_id/params/question/answers/
    correct/wrong）。
    """
    lines = raw.decode("latin-1", errors="replace").splitlines()

    def new_cur() -> dict:
        return {"inf": inf_name, "idx": None, "type": None, "key_id": None,
                "text_lines": [], "params": None, "riddle_lines": [],
                "answers": [], "correct_lines": [], "wrong_lines": [],
                "riddle_mode": None}

    out: list[dict] = []
    cur = new_cur()
    in_text = False

    def flush() -> None:
        nonlocal cur
        if cur["idx"] is None:
            return
        t = cur["type"]
        e: dict = {"inf": cur["inf"], "idx": cur["idx"]}
        if t == "key":
            if cur["text_lines"]:
                e.update(type="key_lore", key_id=cur["key_id"],
                         text="\n".join(cur["text_lines"]))
            else:
                e.update(type="key", key_id=cur["key_id"])
        elif t == "lore_once":
            e.update(type="lore_once", text="\n".join(cur["text_lines"]))
        elif t == "riddle":
            e.update(type="riddle", params=cur["params"],
                     question="\n".join(cur["riddle_lines"]),
                     answers=cur["answers"],
                     correct="\n".join(cur["correct_lines"]),
                     wrong="\n".join(cur["wrong_lines"]))
        else:
            if not cur["text_lines"]:
                return
            e.update(type="lore", text="\n".join(cur["text_lines"]))
        out.append(e)

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if line.startswith("@"):
            sec = line.strip()
            if sec == "@TEXT":
                flush(); cur = new_cur(); in_text = True
            elif in_text:
                flush(); cur = new_cur(); in_text = False
            continue
        if not in_text:
            continue
        if line.startswith("*TEXT"):
            flush(); cur = new_cur()
            parts = line.split()
            if len(parts) >= 2:
                try:
                    cur["idx"] = int(parts[1])
                except ValueError:
                    pass
            continue
        if cur["idx"] is None:
            continue
        stripped = line.strip()
        if stripped == "":
            if cur["type"] == "riddle" and cur["riddle_mode"] == "riddle":
                cur["riddle_lines"].append("")
            continue
        if cur["type"] == "riddle":
            if stripped.startswith(":"):
                cur["answers"].append(stripped[1:])
            elif stripped.startswith("`CORRECT"):
                cur["riddle_mode"] = "correct"
            elif stripped.startswith("`WRONG"):
                cur["riddle_mode"] = "wrong"
            elif cur["riddle_mode"] == "riddle":
                cur["riddle_lines"].append(line)
            elif cur["riddle_mode"] == "correct":
                cur["correct_lines"].append(line)
            elif cur["riddle_mode"] == "wrong":
                cur["wrong_lines"].append(line)
            continue
        if cur["type"] == "lore_once":
            cur["text_lines"].append(line); continue
        if cur["type"] == "key":
            cur["text_lines"].append(line); continue
        if cur["type"] is None:
            if stripped.startswith("+"):
                try:
                    cur["key_id"] = int(stripped[1:].strip())
                    cur["type"] = "key"; continue
                except ValueError:
                    pass
            elif stripped.startswith("^"):
                parts = stripped[1:].split()
                if len(parts) >= 2:
                    try:
                        cur["params"] = [int(parts[0]), int(parts[1])]
                        cur["type"] = "riddle"; cur["riddle_mode"] = "riddle"
                        continue
                    except ValueError:
                        pass
            elif stripped.startswith("~"):
                cur["type"] = "lore_once"
                rest = line[line.find("~") + 1:]
                if rest:
                    cur["text_lines"].append(rest)
                continue
        if cur["type"] is None:
            cur["type"] = "lore"
        cur["text_lines"].append(line)

    if in_text:
        flush()
    return out


def _inf_entry(original: str, source_id: str, extra: dict) -> dict:
    """inf_text の 1 エントリ（original/source_id/source_hash＋type 別 extra）。"""
    e = {"original": original, "source_id": source_id,
         "source_hash": sa.source_hash(original)}
    e.update(extra)
    return e


def regenerate_inf_text_bytes(inf_files: dict[str, bytes]) -> dict[str, dict]:
    """inf_text の **INF @TEXT 由来分のみ** を再構築する。

    inf_files = {INF ファイル名(大文字・拡張子込み): バイト列}。複数 INF を VFS で
    読んで渡す。Returns {app_id: entry}。app_id=inf_text.<INF>_<idx>.0（parent）/
    inf_text.<INF>_<idx>.<field>（riddle サブ）。
    _CHARGEN_* / TEMPLATE_DAT_* は対象外（EXE 由来 / 別経路）。
    """
    out: dict[str, dict] = {}
    for inf_name in sorted(inf_files):
        if not inf_name.upper().endswith(".INF"):
            continue
        for pe in _parse_inf_text_section(inf_files[inf_name], inf_name.upper()):
            inf, idx, t = pe["inf"], pe["idx"], pe["type"]
            base = f"{INF_TEXT_CATEGORY}.{inf}_{idx}.0"
            sid = sa.inf_id(inf, idx)
            common = {"inf": inf, "idx": idx, "type": t}
            if t in ("lore", "lore_once"):
                out[base] = _inf_entry(pe["text"], sid,
                                       {**common, "text": pe["text"]})
            elif t == "key_lore":
                out[base] = _inf_entry(pe["text"], sid,
                                       {**common, "key_id": pe["key_id"],
                                        "text": pe["text"]})
            elif t == "key":
                out[base] = _inf_entry("", sid,
                                       {**common, "key_id": pe["key_id"]})
            elif t == "riddle":
                out[base] = _inf_entry("", sid, {
                    **common, "params": pe["params"], "question": pe["question"],
                    "answers": pe["answers"], "correct": pe["correct"],
                    "wrong": pe["wrong"]})
                # サブエントリ（翻訳 id 解決用）。本文が空の field は出さない（現 _original 一致）。
                for field in ("question", "correct", "wrong"):
                    text = pe[field]
                    if not text:
                        continue
                    out[f"{INF_TEXT_CATEGORY}.{inf}_{idx}.{field}"] = _inf_entry(
                        text, f"{sid}:{field}", {"type": "riddle", "field": field})
    return out


def build_inf_text_original_json(new_entries: dict[str, dict]) -> dict:
    """inf_text の _original 内容（id 昇順・決定論・消費フィールドを保持）。"""
    return {app_id: new_entries[app_id] for app_id in sorted(new_entries)}


def build_inf_text_manifest(new_entries: dict[str, dict],
                            fingerprint: str) -> dict:
    """inf_text のゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           INF_TEXT_CATEGORY, INF_TEXT_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# _CHARGEN_ キャラ作成質問（QUESTION.TXT）の決定論再生成
# ---------------------------------------------------------------------------
# 出典 = QUESTION.TXT（loose テキストファイル）。OpenTESArena
# TextAssetLibrary::initQuestionTxt 準拠の行モードパーサで 40 問（各 description ＋
# a/b/c 選択肢）に分解する。生成カテゴリは inf_text（既存 _CHARGEN_Q_* と同じ住所）:
#   inf_text._CHARGEN_Q_<n>__0.0      … 質問エントリ（type=lore）。
#       original/text = description のみ（消費側 lookup_by_text の前方一致キー）、
#       text_display/text_panel = 全文（description＋a/b/c・パネル/タブ EN 表示）。
#   inf_text._CHARGEN_Q_<n>__0.display … 補足訳タブ用の翻訳キーアンカー（field=display）。
#       original = 全文（description＋a/b/c）。
# 消費側（inf_text_lookup）は (inf="_CHARGEN_Q_<n>_", idx=0) で索引し、
# get_text_panel/get_text_display で text_display/text_panel（全文）を表示する。
#
# 行モード（OTA 準拠）: 先頭が数字の行=新しい問の description 開始（前問を flush）、
# 先頭が a/b/c の行=その選択肢モードへ切替、それ以外=現モードへ継続。
# curation: description=先頭 "N. " 番号を除去、選択肢=末尾の "(5l/c/v)" カテゴリ標識を
# 除去（a)/b)/c) 接頭辞は残す）。いずれも改行・インデントを含む空白連続を 1 個へ畳む。

CHARGEN_QUESTION_GENERATOR_VERSION = "question-2"
_CHARGEN_QUESTION_NUMBER_RE = re.compile(r"^\s*\d+\.\s*")
_CHARGEN_CATEGORY_MARKER_RE = re.compile(r"\s*\(5[lcv]\)\s*")


def _parse_question_txt(raw: bytes) -> list[tuple[str, str, str, str]]:
    """QUESTION.TXT（バイト列）を 40 問の (description, a, b, c) 生文字列に分解する。"""
    text = raw.decode("latin-1", errors="replace")
    questions: list[tuple[str, str, str, str]] = []
    desc = a = b = c = ""
    mode = "D"  # D=description / A,B,C=選択肢
    for line in text.split("\n"):
        first = line[0] if line else ""
        if first.isalpha():
            if first == "a":
                mode = "A"
            elif first == "b":
                mode = "B"
            elif first == "c":
                mode = "C"
        elif first.isdigit():
            if mode != "D":
                questions.append((desc, a, b, c))
                desc = a = b = c = ""
            mode = "D"
        nl = line + "\n"
        if mode == "D":
            desc += nl
        elif mode == "A":
            a += nl
        elif mode == "B":
            b += nl
        elif mode == "C":
            c += nl
    questions.append((desc, a, b, c))
    return questions


def _curate_question(desc: str) -> str:
    """description を _original 互換へ整形（先頭番号除去＋空白畳み）。"""
    s = _CHARGEN_QUESTION_NUMBER_RE.sub("", desc)
    return re.sub(r"\s+", " ", s).strip()


def _curate_answer(ans: str) -> str:
    """選択肢を _original 互換へ整形（空白畳み＋末尾 "(5x)" カテゴリ標識除去）。"""
    s = re.sub(r"\s+", " ", ans).strip()
    return _CHARGEN_CATEGORY_MARKER_RE.sub("", s).strip()


def regenerate_chargen_questions(raw: bytes) -> dict[str, dict]:
    """_CHARGEN_ キャラ作成質問本文を再構築する（QUESTION.TXT バイト列版）。

    Returns {app_id: entry}。app_id=inf_text._CHARGEN_Q_<n>__0.0（質問エントリ）/
    inf_text._CHARGEN_Q_<n>__0.display（補足訳タブ用キーアンカー）。
    """
    out: dict[str, dict] = {}
    for i, (desc, a, b, c) in enumerate(_parse_question_txt(raw), start=1):
        text = _curate_question(desc)
        if not text:
            continue
        answers = [_curate_answer(x) for x in (a, b, c) if x.strip()]
        full = "\n".join([text, *answers])
        inf = f"_CHARGEN_Q_{i}_"
        sid = sa.question_id(i)
        base = f"{INF_TEXT_CATEGORY}.{inf}_0.0"
        out[base] = _inf_entry(text, sid,
                               {"inf": inf, "idx": 0, "type": "lore", "text": text,
                                "text_display": full, "text_panel": full})
        out[f"{INF_TEXT_CATEGORY}.{inf}_0.display"] = _inf_entry(
            full, f"{sid}:display", {"type": "lore", "field": "display"})
    return out


def build_chargen_questions_manifest(new_entries: dict[str, dict],
                                     fingerprint: str) -> dict:
    """_CHARGEN_ 質問のゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           INF_TEXT_CATEGORY, CHARGEN_QUESTION_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# npc_dialog A-key トレード会話（TAVERN.DAT 等・loadTradeText）の決定論再生成
# ---------------------------------------------------------------------------
# 出典 = トレード会話 DAT（TAVERN/SELLING/EQUIP/MUGUILD.DAT）。OTA
# TextAssetLibrary::loadTradeText が null 終端文字列の array（各 75）で読む。
# 現フェーズ対象は **A500台（宿屋の部屋提示）= TAVERN.DAT**（A500+i ↔ TAVERN[i]）。
# Assist curation = プレースホルダ改名（DAT の %i→%nr / %mm→%a）。placeholders は
# 出現順（A-key は出現順保持・TEMPLATE.DAT 系の sorted とは異なる）。
# 残バンド（A100/A300/A400/A600＝A.EXE 由来）は EXE 由来採取の別サブフェーズ。

ATRADE_GENERATOR_VERSION = "atrade-1"
# A-key 番号帯 → (DAT ファイル名小文字, 開始 A 番号)。
_ATRADE_TAVERN_BASE = 500
_ATRADE_PLACEHOLDER_REMAP = (("%i", "%nr"), ("%mm", "%a"))


def _atrade_remap(s: str) -> str:
    # DAT 内のタブ（行折返し制御）は空白へ正規化（短い行＝大半はタブ無しで無影響）。
    s = s.replace("\t", " ")
    for src, dst in _ATRADE_PLACEHOLDER_REMAP:
        s = s.replace(src, dst)
    return s


def _read_dat_strings(raw: bytes) -> list[str]:
    """トレード DAT を null 終端文字列の array に分解（loadTradeText 準拠）。"""
    return [s.decode("latin-1", errors="replace") for s in raw.split(b"\x00") if s]


def regenerate_atrade_tavern(raw: bytes) -> dict[str, dict]:
    """A-key A500台（宿屋の部屋提示）を TAVERN.DAT から再構築する。

    Returns {app_id: entry}。app_id=npc_dialog.A<500+i>.0。placeholders は出現順。
    """
    out: dict[str, dict] = {}
    for i, s in enumerate(_read_dat_strings(raw)):
        text = _atrade_remap(s).rstrip()  # DAT 末尾の余分な空白を除去（表示・突合の安定化）
        app_id = f"{NPC_DIALOG_KEY_PREFIX}A{_ATRADE_TAVERN_BASE + i}.0"
        out[app_id] = {
            "original": text,
            "source_id": sa.tradetext_id("tavern", i),
            "source_hash": sa.source_hash(text),
            # A-key は placeholders を出現順で保持（TEMPLATE 系の sorted と異なる）。
            "placeholders": _placeholders(text),
        }
    return out


def build_atrade_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    """A-key トレードのゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, ATRADE_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# npc_dialog A-key A600台（店/ギルド値切り）= EQUIP/SELLING/MUGUILD.DAT（loadTradeText）
# ---------------------------------------------------------------------------
# trade text 構造 = [5 function][5 personality][3 random]=75・flat=f*15+p*3+r（OTA loadTradeText）。
# A600台の配列対応（実データ突合で確定・195/195 一致）:
#   A604+f .v(0-14) = EQUIP[f*15+v]                       （買い・全 personality）
#   A609+f .v(0-14) = SELLING[f*15+v]                     （売り・全 personality）
#   A614+f .v(0-8)  = MUGUILD[f*15+(v//3+2)*3+v%3]        （ギルド・personality 2,3,4 のみ）
# 単一: A601=EQUIP#9 / A602=EQUIP#39 / A603=EQUIP#41（特定 personality 文の流用）。
# A600.0/.1・A619.0 は A.EXE UI（akey.json 側＝regenerate_akey_ui）で別途配線。
# curation: \s+ を1空白へ畳む・placeholder 改名 %i→%ni（item）/%mm→%a（gold）。**特殊1件**:
#   SELLING#2(=A609.2) は %i を金額用法で持つため "%i gold"→"%a gold" を先に適用（他に出現せず安全）。

ATRADE_SHOP_GENERATOR_VERSION = "atradeshop-1"
# (app A番号, DATキー小文字, flat index)。配列は下の関数内で展開。
_ATRADE_SHOP_SINGLES = (("A601.0", "equip", 9), ("A602.0", "equip", 39),
                        ("A603.0", "equip", 41))


def _atrade_shop_curate(s: str) -> str:
    s = s.replace("%i gold", "%a gold")          # SELLING#2 の %i 金額用法（先に処理）
    s = s.replace("%i", "%ni").replace("%mm", "%a")  # item / gold プレースホルダ改名
    return re.sub(r"\s+", " ", s).strip()         # \n/\t→空白＋連続空白畳み


def regenerate_atrade_shops(equip_raw: bytes, selling_raw: bytes,
                            muguild_raw: bytes) -> dict[str, dict]:
    """A-key A600台（店/ギルド値切り・A601-A618）を 3 つの trade DAT から再構築する。

    A600.0/.1・A619.0 は含まない（A.EXE UI＝akey UI 経路）。Returns {app_id: entry}。
    """
    dats = {"equip": _read_dat_strings(equip_raw),
            "selling": _read_dat_strings(selling_raw),
            "muguild": _read_dat_strings(muguild_raw)}
    out: dict[str, dict] = {}

    def emit(app_id: str, datkey: str, idx: int) -> None:
        strs = dats[datkey]
        if idx >= len(strs):
            return
        text = _atrade_shop_curate(strs[idx])
        out[f"{NPC_DIALOG_KEY_PREFIX}{app_id}"] = {
            "original": text,
            "source_id": sa.tradetext_id(datkey, idx),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }

    for app_id, datkey, idx in _ATRADE_SHOP_SINGLES:
        emit(app_id, datkey, idx)
    for f in range(5):
        for v in range(15):
            emit(f"A{604 + f}.{v}", "equip", f * 15 + v)
            emit(f"A{609 + f}.{v}", "selling", f * 15 + v)
        for v in range(9):
            emit(f"A{614 + f}.{v}", "muguild", f * 15 + (v // 3 + 2) * 3 + v % 3)
    return out


def build_atrade_shop_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    """A-key 店/ギルド値切りのゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, ATRADE_SHOP_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# npc_dialog A-key A180台（修理屋の値切り）= TEMPLATE.DAT #1417/#1418/#1424-1428
# ---------------------------------------------------------------------------
# 修理屋の値切り会話は TEMPLATE.DAT ブロックに格納（B群型・loose）。A-key↔block は非連番。
# curation: %i→%ni（item）・金額系プレースホルダ(%t/%a/%mm)を**出現順で %a,%a2 へ位置 remap**
# （disk は名前でなく出現位置で %a/%a2 を割当・ブロックにより金額/日数の順が逆のため）・\s+ 畳み。
# Assist 正規化2件: #1426 の "gp"→"gold"(A185.0)・#1418 の "cost, but"→"cost but"(A188.1)。
# 採取検証 12/12（同一版 TEMPLATE.DAT）。

AKEY_REPAIR_GENERATOR_VERSION = "akeyrepair-1"
_AKEY_AMT_PH = re.compile(r"%(?:t|a|mm)\b")
# app A番号 → (TEMPLATE block, variant index, [(curation 置換 from, to)])。
_AKEY_REPAIR_MAP = {
    "A182.0": ("1424", 1, ()),
    "A183.0": ("1424", 0, ()),
    "A184.0": ("1425", 0, ()),
    "A185.0": ("1426", 0, (("gp", "gold"),)),
    "A185.1": ("1426", 0, ()),
    "A186.0": ("1427", 0, ()),
    "A186.1": ("1427", 1, ()),
    "A187.0": ("1428", 0, ()),
    "A187.1": ("1428", 1, ()),
    "A188.0": ("1417", 0, ()),
    "A188.1": ("1418", 0, (("cost, but", "cost but"),)),
    "A188.2": ("1418", 0, ()),
}


def _akey_repair_curate(s: str, subs) -> str:
    s = s.replace("%i", "%ni")                  # item プレースホルダ
    amt = iter(("%a", "%a2"))                    # 金額系を出現順で %a,%a2 へ位置 remap
    s = _AKEY_AMT_PH.sub(lambda m: next(amt, m.group(0)), s)
    s = re.sub(r"\s+", " ", s).strip()
    for a, b in subs:
        s = s.replace(a, b)
    return s


def regenerate_akey_repair(template_raw: bytes) -> dict[str, dict]:
    """A-key A180台（修理屋の値切り・A182-A188）を TEMPLATE.DAT から再構築する。

    Returns {app_id: entry}。app_id=npc_dialog.A18x。source_id=template:<block>:0:<variant>。
    """
    ents = {(e["key"], e["copy"]): e for e in parse_template_dat_bytes(template_raw)}
    out: dict[str, dict] = {}
    for akey, (block, vi, subs) in _AKEY_REPAIR_MAP.items():
        e = ents.get((block, 0))
        if not e or vi >= len(e["values"]):
            continue
        text = _akey_repair_curate(e["values"][vi], subs)
        out[f"{NPC_DIALOG_KEY_PREFIX}{akey}"] = {
            "original": text,
            "source_id": sa.template_id(block, vi, copy=0),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }
    return out


def build_akey_repair_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    """A-key 修理屋値切りのゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, AKEY_REPAIR_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# npc_dialog A-key 構造 source_id（純構造・Arena バイト不要）= 単一住所
# ---------------------------------------------------------------------------
# offline source_id_map（category_source_id）と user-env provider が共有する A-key→
# source_id の唯一の構造規則。各 A-key 帯を上の生成器と同じ静的写像で振り分ける:
#   - 修理屋 A18x = TEMPLATE.DAT（_AKEY_REPAIR_MAP）→ template:<block>:0:<variant>
#   - A.EXE UI    = akey.json テンプレ収録 → aexe:akey:<akey>
#   - トレード会話 = TAVERN/EQUIP/SELLING/MUGUILD.DAT → tradetext:<dat>:<idx>
# curation 除外: 同一ディスク source 位置（block,variant）から Assist 正規化で異 surface を
# 作る変種（_AKEY_REPAIR_MAP の subs 付きで raw 兄弟と source 位置衝突するもの＝A185.0/
# A188.1）は source_id を持たない（localpack 非収録・literals/cinematic と同じ curation 扱い・
# raw 兄弟が canonical 表面）。source_id は同一位置で 1 つ＝異 surface の不正 fan-out を防ぐ。


def _akey_repair_curation_excluded() -> frozenset:
    """_AKEY_REPAIR_MAP で同一 (block,variant) を共有し、curation(subs) を持つ変種の集合。"""
    pos: dict[tuple, list] = {}
    for akey, (block, vi, subs) in _AKEY_REPAIR_MAP.items():
        pos.setdefault((block, vi), []).append((akey, bool(subs)))
    excluded = set()
    for siblings in pos.values():
        if len(siblings) > 1:
            for akey, has_subs in siblings:
                if has_subs:
                    excluded.add(akey)
    return frozenset(excluded)


_AKEY_REPAIR_CURATION = _akey_repair_curation_excluded()
_AKEY_NUM_RE = re.compile(r"^A(\d+)\.(\d+)$")


def akey_structural_source_id(akey: str, aexe_akey_keys) -> str | None:
    """npc_dialog A-key（prefix 無し・例 'A604.9'）→ source_id（純構造・Arena バイト不要）。

    aexe_akey_keys = akey UI テンプレ（i18n/_aexe_template/akey.json）のキー集合＝A.EXE UI
    由来 A-key の権威的集合。返り値は aexe:akey:<akey> / tradetext:<dat>:<idx> /
    template:<block>:0:<variant>、対象外（curation 等）は None。
    """
    spec = _AKEY_REPAIR_MAP.get(akey)
    if spec is not None:
        if akey in _AKEY_REPAIR_CURATION:
            return None
        block, vi, _subs = spec
        return sa.template_id(block, vi, copy=0)
    if akey in aexe_akey_keys:
        return sa.aexe_id("akey", akey)
    for sid_akey, datkey, idx in _ATRADE_SHOP_SINGLES:
        if akey == sid_akey:
            return sa.tradetext_id(datkey, idx)
    m = _AKEY_NUM_RE.match(akey)
    if not m:
        return None
    num, sub = int(m.group(1)), int(m.group(2))
    if 500 <= num <= 599 and sub == 0:
        return sa.tradetext_id("tavern", num - _ATRADE_TAVERN_BASE)
    if 604 <= num <= 608:
        return sa.tradetext_id("equip", (num - 604) * 15 + sub)
    if 609 <= num <= 613:
        return sa.tradetext_id("selling", (num - 609) * 15 + sub)
    if 614 <= num <= 618:
        return sa.tradetext_id("muguild", (num - 614) * 15 + (sub // 3 + 2) * 3 + sub % 3)
    return None


# ---------------------------------------------------------------------------
# npc_dialog A-key UI（A0/A100-A400 帯＝純 A.EXE のハードコード UI/ポップアップ）の再構築
# ---------------------------------------------------------------------------
# 出典 = A.EXE 固定データ領域の UI 文字列。OTA aExeStrings には未ラベルのため、起動中メモリの
# 文字列サーチで offset を特定した（arena_aexe.AKEY_ACD_OFFSETS・ACD.EXE 版のみ・仮説）。
# 採取生レコードは内部に \r で複数セグメントを含みうる。curation（placeholder 改名/セグメント
# 結合/末尾空白）は i18n/_aexe_template/akey.json に分離（原文非含・公開同梱可）。
# A500台=TAVERN.DAT（loose・regenerate_atrade_tavern）／A600台=店ギルド値切り DAT は別経路。
# A.EXE 採取値（原文）はコードに埋め込まない（offset と curation 規則のみ）。

AKEY_UI_GENERATOR_VERSION = "akeyui-2"
# A.EXE の C プレースホルダ（%s/%d/%u・%lu 等の長さ修飾付き）。disk の意味プレースホルダ列で
# 出現順に置換する。
_AKEY_EXE_PH = re.compile(r"%l?[sduSDU]\d*")


def _akey_seg(raw: str) -> str:
    """採取レコードの先頭セグメント（最初の \\r まで／無ければ全体）。"""
    cut = raw.find("\r")
    return raw[:cut] if cut >= 0 else raw


def _akey_remap(text: str, phs: list) -> str:
    """EXE プレースホルダ(%s/%d/%u)を disk プレースホルダ列で出現順に置換する。"""
    it = iter(phs)
    return _AKEY_EXE_PH.sub(lambda m: next(it, m.group(0)), text)


def regenerate_akey_ui(raw_map: dict, template: dict) -> dict[str, dict]:
    """A-key UI（A0/A100-A400）を採取レコード＋curation テンプレで再構築する。

    raw_map  = {akey_id: 採取生レコード}（arena_aexe.harvest_akey 由来・原文非埋込）。
    template = i18n/_aexe_template/akey.json（{akey_id: {mode, ph, trail?, suffix?}}）。
    Returns {app_id: entry}。app_id=npc_dialog.<akey_id>。placeholders は出現順。
    """
    out: dict[str, dict] = {}
    for akey, spec in template.items():
        raw = raw_map.get(akey)
        if raw is None:
            continue
        mode = spec.get("mode", "seg")
        phs = spec.get("ph", [])
        if mode == "seg":
            text = _akey_remap(_akey_seg(raw), phs).rstrip(" ")
            text += " " * int(spec.get("trail", 0))
        elif mode == "seg_suffix":
            text = _akey_seg(raw).rstrip(" ") + spec.get("suffix", "")
        elif mode == "full":
            text = _akey_remap(raw.replace("\r", ""), phs).rstrip(" ")
        elif mode == "join_ws":
            # \r→空白・連続空白畳み（複数行レコードを1行へ）・placeholder remap・任意の末尾除去。
            joined = re.sub(r"\s+", " ", raw.replace("\r", " ")).strip()
            text = _akey_remap(joined, phs)
            rs = spec.get("rstrip")
            if rs:
                text = text.rstrip(rs + " ")
        else:
            continue
        app_id = f"{NPC_DIALOG_KEY_PREFIX}{akey}"
        out[app_id] = {
            "original": text,
            "source_id": sa.aexe_id("akey", akey),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }
    return out


def build_akey_ui_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    """A-key UI のゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, AKEY_UI_GENERATOR_VERSION)


# ---------------------------------------------------------------------------
# _CHARGEN_ UI/結果系（A.EXE CharacterCreation ＋ TEMPLATE.DAT 種族説明）の再構築
# ---------------------------------------------------------------------------
# 出典（OTA [CharacterCreation] 採取値・arena_aexe で harvest）:
#   RESULT_<CLASS>      = SuggestedClass 書式 "...as a %s..." ＋ ClassNames
#   CLASS_ADVICE_<CLASS>= ConfirmedRace3 書式 "...%s...as a %s." ＋ preferred_attributes ＋ ClassNames
#   RACE_<RACE>         = ConfirmedRace2 "Know ye this also:" ＋ TEMPLATE.DAT #1409-1416 種族説明
#   単一(%s 無し)       = 各 CharacterCreation 文字列（\r→空白畳み）
# %s 実行時置換を含む単一(NAME/PROVINCE/ConfirmRace/ConfirmedRace1)は assist_window の
# 置換ロジックに結びつくため本生成器の対象外（disk _original 維持＝部分カバレッジ・後続）。
# 採取値（原文）は analyzer 由来でコードに埋め込まない（offset のみ）。

CHARGEN_UI_GENERATOR_VERSION = "chargenui-1"

# クラス順（ClassNames テーブル順＝採取値の index）。RESULT_*/CLASS_ADVICE_* のキー語。
_CHARGEN_CLASS_ORDER = (
    "MAGE", "SPELLSWORD", "BATTLEMAGE", "SORCEROR", "HEALER", "NIGHTBLADE",
    "BARD", "BURGLAR", "ROGUE", "ACROBAT", "THIEF", "ASSASSIN", "MONK",
    "ARCHER", "RANGER", "BARBARIAN", "WARRIOR", "KNIGHT",
)
# 種族順（TEMPLATE.DAT #1409-1416＝標準種族順）。RACE_* のキー語。
_CHARGEN_RACE_ORDER = (
    "BRETON", "REDGUARD", "NORD", "DARK_ELF", "HIGH_ELF", "WOOD_ELF",
    "KHAJIIT", "ARGONIAN",
)
# %s を含まない単一文字列: _CHARGEN_<NAME> → char_creation テーブルキー。
# NAME は末尾 "_" を含めない（emit 側で付与）。"" は bare キー inf_text._CHARGEN__0.0。
_CHARGEN_UI_SINGLE = {
    "": "choose_class_creation",
    "10Q": "class_questions_intro",
    "CHOOSE_CLASS": "choose_class_list",
    "GENDER": "choose_gender",
    "CHOOSE_ATTRIBUTES": "choose_attributes",
    "BONUS_REMAINING": "choose_attributes_bonus_points_remaining",
    "APPEARANCE": "choose_appearance",
    "GOYENOW": "confirmed_race4",
}


def _chargen_norm(s: str) -> str:
    """CharacterCreation 文字列を表示形へ整形（\r→空白・空白連続畳み・strip）。"""
    return re.sub(r"\s+", " ", s.replace("\r", " ")).strip()


# _CHARGEN_ UI/結果の source_id（A.EXE/ACD CharacterCreation 採取系）。仕様ゲート3:
# 疑似 inf:_CHARGEN_ は公開 map に出さず aexe:char_creation:<table>:<key> を使う（EXE 由来 ACD と同形）。
# table=ui（単一・key=char_creation テーブルキー）/ result|advice|race（key=class/race index）。
def _chargen_ui_src(table: str, key) -> str:
    return sa._SEP.join((sa.KIND_AEXE, "char_creation", str(table), str(key)))


def _chargen_ui_emit(out: dict, name: str, text: str, src_id: str) -> None:
    """_CHARGEN_<name> の .0（lore・全文）と .display（翻訳キーアンカー）を出す。

    inf = "_CHARGEN_" ＋（name があれば "<name>_"）。name="" は bare（inf="_CHARGEN_"）。
    """
    inf = "_CHARGEN_" + (f"{name}_" if name else "")
    base = f"{INF_TEXT_CATEGORY}.{inf}_0.0"
    out[base] = _inf_entry(text, src_id,
                           {"inf": inf, "idx": 0, "type": "lore", "text": text,
                            "text_display": text, "text_panel": text})
    out[f"{INF_TEXT_CATEGORY}.{inf}_0.display"] = _inf_entry(
        text, f"{src_id}:display", {"type": "lore", "field": "display"})


def regenerate_chargen_ui(cc: dict, class_names: list, pref_attrs: list,
                          race_descs: list) -> dict[str, dict]:
    """_CHARGEN_ UI/結果系（%s 無し分）を再構築する。

    cc          = {char_creation 短縮キー: 採取文字列}（analyzer 由来・原文非埋込）。
    class_names = ClassNames（18・採取）／pref_attrs = preferred_attributes（18・採取）。
    race_descs  = TEMPLATE.DAT #1409-1416 の種族説明（8・full・未整形）。
    Returns {app_id: entry}。app_id=inf_text._CHARGEN_<NAME>__0.0/.display。
    """
    out: dict[str, dict] = {}
    # 単一（%s 無し）
    for name, key in _CHARGEN_UI_SINGLE.items():
        raw = cc.get(key)
        if not raw:
            continue
        _chargen_ui_emit(out, name, _chargen_norm(raw),
                         _chargen_ui_src("ui", key))
    # RESULT_<CLASS> = SuggestedClass 書式 ＋ ClassNames
    sc = cc.get("suggested_class")
    if sc:
        fmt = _chargen_norm(sc)
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            if i >= len(class_names):
                break
            text = fmt.replace("%s", class_names[i], 1)
            _chargen_ui_emit(out, f"RESULT_{cls}", text,
                             _chargen_ui_src("result", i))
    # CLASS_ADVICE_<CLASS> = ConfirmedRace3 書式 ＋ preferred_attributes ＋ ClassNames
    cr3 = cc.get("confirmed_race3")
    if cr3:
        fmt = _chargen_norm(cr3)
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            if i >= len(class_names) or i >= len(pref_attrs):
                break
            text = fmt.replace("%s", pref_attrs[i], 1).replace("%s", class_names[i], 1)
            _chargen_ui_emit(out, f"CLASS_ADVICE_{cls}", text,
                             _chargen_ui_src("advice", i))
    # RACE_<RACE> = ConfirmedRace2 "Know ye this also:" ＋ TEMPLATE.DAT 種族説明
    cr2 = cc.get("confirmed_race2")
    if cr2:
        prefix = _chargen_norm(cr2)
        for i, race in enumerate(_CHARGEN_RACE_ORDER):
            if i >= len(race_descs):
                break
            desc = _chargen_norm(race_descs[i])
            text = f"{prefix} {desc}".strip()
            _chargen_ui_emit(out, f"RACE_{race}", text,
                             _chargen_ui_src("race", i))
    return out


_chargen_ui_sid_cache: dict[str, str] | None = None


def _chargen_ui_source_id_map() -> dict[str, str]:
    """covered な _CHARGEN_ UI/結果 legacy rest → aexe:char_creation source_id（純構造）。

    regenerate_chargen_ui が生成する単一(ui)/RESULT/CLASS_ADVICE/RACE を網羅する。.0 と
    .display の両方を引けるよう登録する（.display を持たない entry の余剰キーは照会されない）。
    """
    global _chargen_ui_sid_cache
    if _chargen_ui_sid_cache is None:
        out: dict[str, str] = {}

        def emit(name: str, base: str) -> None:
            inf = "_CHARGEN_" + (f"{name}_" if name else "")
            out[f"{inf}_0.0"] = base
            out[f"{inf}_0.display"] = base + ":display"

        for name, key in _CHARGEN_UI_SINGLE.items():
            emit(name, _chargen_ui_src("ui", key))
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            emit(f"RESULT_{cls}", _chargen_ui_src("result", i))
            emit(f"CLASS_ADVICE_{cls}", _chargen_ui_src("advice", i))
        for i, race in enumerate(_CHARGEN_RACE_ORDER):
            emit(f"RACE_{race}", _chargen_ui_src("race", i))
        _chargen_ui_sid_cache = out
    return _chargen_ui_sid_cache


def chargen_ui_source_id(inf_rest: str) -> str | None:
    """inf_text の _CHARGEN_ UI/結果 legacy_id（'inf_text.' を除いた rest）→ aexe:char_creation source_id。

    covered（単一/RESULT/CLASS_ADVICE/RACE）のみ対応。%s 実行時置換系（NAME/PROVINCE/
    PROVINCE_CONFIRM）・未採取（CLASS_LIST/COMPLETE/OPENING/DISTRIBUTE_POINTS）は部分カバレッジ＝
    None（後続）。_CHARGEN_Q（質問）は question 経路で別途扱うため本関数の対象外。
    """
    if inf_rest.startswith("_CHARGEN_Q_"):
        return None
    return _chargen_ui_source_id_map().get(inf_rest)


# ---------------------------------------------------------------------------
# npc_name_chunks（NAMECHNK.DAT・生成 NPC 名の部品）の決定論再生成
# ---------------------------------------------------------------------------
# 出典 = NAMECHNK.DAT（OpenTESArena TextAssetLibrary::initNameChunks 準拠）。
#   各 chunk: uint16 LE chunkLength（3 byte ヘッダ込み総長）／uint8 stringCount／
#   stringCount 個の null 終端文字列。offset += chunkLength で次 chunk。
# 現フェーズ対象は chunk 部品のみ（789）。`literals.*`（名前合成規則の literal・1 件・
# A.EXE 由来の規則データ）は Assist curation＝パック非収録（EXE 由来/別経路、開発時は merge 保持）。

NPC_NAME_CHUNKS_GENERATOR_VERSION = "namechnk-1"
NPC_NAME_CHUNKS_CATEGORY = "npc_name_chunks"


def regenerate_npc_name_chunks_bytes(raw: bytes) -> dict[str, dict]:
    """npc_name_chunks の **chunk 部品のみ** を再構築する（NAMECHNK.DAT バイト列版）。

    Returns {app_id: entry}。app_id=npc_name_chunks.chunks.<chunk>.<idx>、
    source_id=namechnk:<chunk>:<idx>。literals は対象外（Assist curation）。
    """
    import struct
    out: dict[str, dict] = {}
    off = 0
    chunk_idx = 0
    n = len(raw)
    while off + 3 <= n:
        chunk_length = struct.unpack_from("<H", raw, off)[0]
        if chunk_length <= 0:
            break
        string_count = raw[off + 2]
        so = off + 3
        for si in range(string_count):
            end = raw.find(b"\x00", so)
            if end < 0:
                break
            value = raw[so:end].decode("latin-1")
            so = end + 1
            app_id = f"{NPC_NAME_CHUNKS_CATEGORY}.chunks.{chunk_idx}.{si}"
            out[app_id] = {
                "original": value,
                "source_id": sa.namechnk_id(chunk_idx, si),
                "source_hash": sa.source_hash(value),
            }
        off += chunk_length
        chunk_idx += 1
    return out


def build_npc_name_chunks_original_json(new_entries: dict[str, dict]) -> dict:
    """npc_name_chunks の _original 内容（id 昇順・決定論）。"""
    return {app_id: new_entries[app_id] for app_id in sorted(new_entries)}


def build_npc_name_chunks_manifest(new_entries: dict[str, dict],
                                   fingerprint: str) -> dict:
    """npc_name_chunks のゴールデンマニフェスト（原文なし）。"""
    return _build_manifest(new_entries, fingerprint,
                           NPC_NAME_CHUNKS_CATEGORY,
                           NPC_NAME_CHUNKS_GENERATOR_VERSION)


# EXE 由来（A.EXE）カテゴリのゴールデンマニフェスト（原文なし）。
AEXE_MANIFEST_GENERATOR_VERSION = "aexe-1"


def build_aexe_manifest(category: str, original_json: dict[str, dict],
                        fingerprint: str) -> dict:
    """EXE 由来（A.EXE）カテゴリのゴールデンマニフェスト（原文なし）。

    original_json は `{app_id: {original, ...}}`（arena_aexe.build_aexe_original_json 由来）。
    source_id = `aexe:<category>:<app_id>`、source_hash = 正規化原文の hash。原文は含めない。
    """
    entries = {sa.aexe_id(category, k): sa.source_hash(v.get("original", ""))
               for k, v in original_json.items()}
    return {
        sa.MANIFEST_VERSION: AEXE_MANIFEST_GENERATOR_VERSION,
        sa.MANIFEST_GENERATOR: f"arena_regen/{AEXE_MANIFEST_GENERATOR_VERSION}",
        sa.MANIFEST_FINGERPRINT: fingerprint,
        sa.MANIFEST_DIGEST: sa.manifest_digest(entries),
        "category": category,
        sa.MANIFEST_ENTRIES: entries,
    }


__all__ = [
    "GENERATOR_VERSION", "CATEGORY", "TARGET_BLOCKS",
    "parse_template_dat_bytes", "regenerate_building_entry_bytes",
    "build_original_json", "fingerprint_bytes", "build_manifest",
    "NPC_DIALOG_GENERATOR_VERSION", "NPC_DIALOG_CATEGORY",
    "regenerate_npc_dialog_bytes", "build_npc_dialog_original_json",
    "build_npc_dialog_manifest",
    "INF_TEXT_GENERATOR_VERSION", "INF_TEXT_CATEGORY",
    "regenerate_inf_text_bytes", "build_inf_text_original_json",
    "build_inf_text_manifest",
    "CHARGEN_QUESTION_GENERATOR_VERSION", "regenerate_chargen_questions",
    "build_chargen_questions_manifest",
    "CHARGEN_UI_GENERATOR_VERSION", "regenerate_chargen_ui",
    "ATRADE_GENERATOR_VERSION", "regenerate_atrade_tavern", "build_atrade_manifest",
    "ATRADE_SHOP_GENERATOR_VERSION", "regenerate_atrade_shops", "build_atrade_shop_manifest",
    "AKEY_REPAIR_GENERATOR_VERSION", "regenerate_akey_repair", "build_akey_repair_manifest",
    "AKEY_UI_GENERATOR_VERSION", "regenerate_akey_ui", "build_akey_ui_manifest",
    "NPC_NAME_CHUNKS_GENERATOR_VERSION", "NPC_NAME_CHUNKS_CATEGORY",
    "regenerate_npc_name_chunks_bytes", "build_npc_name_chunks_original_json",
    "build_npc_name_chunks_manifest",
    "AEXE_MANIFEST_GENERATOR_VERSION", "build_aexe_manifest",
]
