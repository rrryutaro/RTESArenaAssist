"""active_template_reader.py — 直接描画モードのテンプレ ptr 読取り。

"How many days are you staying?" 入力プロンプトや "Enter counter offer :"
のように、Arena が静的テンプレ領域 (+0x4000..+0xC000) を直接描画して
NPC_DIALOG (+0x1044) などの render buffer に書かないケースを対象とする。

stale 排除設計: active slot を first-hit で採用すると、過去に表示された
slot 値 ("%s, thou art healed..." 等) が誤採用される場合がある。候補を
metadata 付きで返し、呼び出し側で stale 排除を判定する。

API:
  read_active_template_candidates(analyzer, anchor) -> list[ActiveTemplateCandidate]
    全候補を metadata 付きで返す:
      - +0xA844 current text pointer route (最優先候補、source="current_ptr")
      - +0xFAB8..+0xFAD6 active slot route (source="active_slot", ptr_slot 付き)
    呼び出し側で stale 排除 (前 poll との差分 / context key 一致 / current_ptr
    優先) を判定する。

互換 API (wide scan の first-hit 用):
  read_active_template(analyzer, anchor) -> str | None
  read_active_templates(analyzer, anchor) -> list[str]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arena_bridge import ArenaMemoryAnalyzer


# 現在表示中項目テキストへの u16 LE pointer (shop_popup_detector と共通)。
# active template の最優先候補として読む。
CURRENT_TEXT_PTR_OFFSET = 0xA844

# response/runtime buffer ptr (NPC 応答・trigger 経路に委ねる)。
# current_ptr / active_slot がこれらを指す場合は active_template ではなく、
# response buffer / runtime message 経路の管轄。
_RESPONSE_TEXT_BUFFER_RANGES = (
    (0x1044, 512),
    (0x929E, 512),
    (0x9A9E, 512),
)
_RUNTIME_MESSAGE_BUFFER_RANGES = (
    # Dungeon key / door / corpse / red text message buffer.
    # compute_b30_state() が +0x7979 から 68 bytes を読むため同範囲を除外。
    (0x7979, 68),
)


def is_runtime_message_buffer_pointer(ptr: int | None) -> bool:
    """trigger/red_text 系が所有する runtime message buffer ptr か。"""
    if ptr is None:
        return False
    return any(start <= ptr < start + length
               for start, length in _RUNTIME_MESSAGE_BUFFER_RANGES)


def is_response_text_buffer_pointer(ptr: int | None) -> bool:
    """npc_dialog / gold_drop 系が所有する response text buffer ptr か。"""
    if ptr is None:
        return False
    return any(start <= ptr < start + length
               for start, length in _RESPONSE_TEXT_BUFFER_RANGES)


def is_response_buffer_pointer(ptr: int | None) -> bool:
    """active_template ではなく専用 response/runtime 経路が所有する ptr か。"""
    if ptr is None:
        return False
    if is_response_text_buffer_pointer(ptr):
        return True
    return is_runtime_message_buffer_pointer(ptr)


# 直接描画テンプレ ptr の slot 列 (anchor 相対 u16 LE)。観測例:
#   +0xFACC = "How many days are you staying?"        (宿屋)
#   +0xFAC8 = "Enter counter offer:"                  (negotiation)
#   +0xFACE = "Are you trying to sneak into a room?"  (宿屋)
#   +0xFACE = "How much do you wish to donate?"       (神殿)
#   +0xFABC / +0xFAC2 = "%s, thou art healed..."      (神殿神官応答)
# +0xFAB8 から +0xFAD6 の u16 LE slot 列に並んでいる前提。
# Arena は施設や場面ごとに異なる slot に書き込むため、広範囲スキャンで
# 1 つでもヒットするテンプレを採用する。
# MIN_TEMPLATE_LEN + 範囲 filter + npc_dialog 辞書ヒット判定で noise を排除。
ACTIVE_TEMPLATE_PTR_OFFSETS = tuple(
    range(0xFAB8, 0xFAD8, 2)
)
# 単一 slot 用の互換定数。
ACTIVE_TEMPLATE_PTR_OFFSET = 0xFACC

# A.EXE memory テンプレ領域の範囲。
TEMPLATE_RANGE_LOW = 0x4000
TEMPLATE_RANGE_HIGH = 0xC000

# テンプレ最大長 (NUL 終端、trailing spaces 含む)
TEMPLATE_MAX_LEN = 256

# 短すぎる文字列の noise filter (+0xFAC8 = 0x85D5 が 'n' 1 文字を返す等の
# 事例に対応)。翻訳対象テンプレは最短でも数文字あるので 4 文字未満は noise。
MIN_TEMPLATE_LEN = 4


def _read_template_at(analyzer, anchor, ptr_offset) -> Optional[str]:
    """指定 ptr offset の u16 LE が指すテンプレ文字列を読み出す。"""
    try:
        raw = analyzer.read_bytes(anchor + ptr_offset, 2)
        if len(raw) < 2:
            return None
        ptr = raw[0] | (raw[1] << 8)
    except (OSError, AttributeError):
        return None
    if not (TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH):
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    if not text:
        return None
    # 末尾空白を除いた実体長で短さ判定 (noise filter)
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def read_active_template(analyzer: "ArenaMemoryAnalyzer",
                          anchor: int) -> Optional[str]:
    """互換 API: +0xFACC slot のみ読む。

    両 slot を扱いたい場合は read_active_templates を使う。
    """
    return _read_template_at(analyzer, anchor, ACTIVE_TEMPLATE_PTR_OFFSET)


def read_active_templates(analyzer: "ArenaMemoryAnalyzer",
                           anchor: int) -> list[str]:
    """全 slot を走査し、valid なテンプレ文字列を順序付きで返す。

    本文 + 入力プロンプトが同時に出る場合、両方含む。重複は除外。

    新規コードは read_active_template_candidates() を使い、stale 排除を
    呼び出し側で行うこと。本関数は wide scan の first-hit をそのまま返すため
    stale を拾いやすい。
    """
    seen: set[str] = set()
    out: list[str] = []
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        t = _read_template_at(analyzer, anchor, off)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


# metadata 付き candidate (current_ptr 優先 / stale 排除のため source 識別)
@dataclass(frozen=True)
class ActiveTemplateCandidate:
    """active template の candidate と由来情報。

    Attributes:
      source: "current_ptr" | "active_slot"
      ptr_slot: anchor 相対 slot offset (= active_slot の場合のみ)。
                current_ptr の場合は None。
      ptr: anchor 相対 template ptr (= テンプレ文字列の格納位置)
      text: テンプレ文字列 (trailing space 含む生のまま)
    """
    source: str
    ptr_slot: Optional[int]
    ptr: int
    text: str


def _read_template_from_ptr(analyzer, anchor, ptr: int) -> Optional[str]:
    """anchor 相対 ptr を template 範囲内として読み出す helper。"""
    if not (TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH):
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    if not text:
        return None
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def read_current_text_pointer(analyzer: "ArenaMemoryAnalyzer",
                              anchor: int) -> Optional[int]:
    """`anchor + 0xA844` u16 LE pointer を読む (= 現在表示中項目への ptr)。"""
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        if len(raw) < 2:
            return None
        return raw[0] | (raw[1] << 8)
    except (OSError, AttributeError):
        return None


def read_active_template_candidates(
    analyzer: "ArenaMemoryAnalyzer",
    anchor: int,
) -> list[ActiveTemplateCandidate]:
    """active template の候補を metadata 付きで返す。

    優先順 (= list 出力順):
      1. +0xA844 current text pointer が template 範囲を指す場合
         (= 「いま画面表示中」を意味する最強の手がかり)
      2. +0xFAB8 ~ +0xFAD6 の active slot 群 (= 各 slot の値が template
         範囲を指す場合のみ)

    response/runtime buffer (+0x1044/+0x7979/+0x929E/+0x9A9E) を指す ptr は除外。
    重複 (= 同一 ptr に複数 source から到達) は最初の source のみ残す。

    呼び出し側 (poll_controller 等) は本 list を受け取り、context key と
    前 poll 結果を見て stale 排除を行う。本 helper は判定を行わない。
    """
    out: list[ActiveTemplateCandidate] = []
    seen_ptrs: set[int] = set()

    # 1. current_ptr route
    cur_ptr = read_current_text_pointer(analyzer, anchor)
    if cur_ptr is not None and not is_response_buffer_pointer(cur_ptr):
        text = _read_template_from_ptr(analyzer, anchor, cur_ptr)
        if text is not None:
            out.append(ActiveTemplateCandidate(
                source="current_ptr",
                ptr_slot=None,
                ptr=cur_ptr,
                text=text,
            ))
            seen_ptrs.add(cur_ptr)

    # 2. active slot route
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = analyzer.read_bytes(anchor + off, 2)
            if len(raw) < 2:
                continue
            ptr = raw[0] | (raw[1] << 8)
        except (OSError, AttributeError):
            continue
        if is_response_buffer_pointer(ptr):
            continue
        if ptr in seen_ptrs:
            continue
        text = _read_template_from_ptr(analyzer, anchor, ptr)
        if text is None:
            continue
        out.append(ActiveTemplateCandidate(
            source="active_slot",
            ptr_slot=off,
            ptr=ptr,
            text=text,
        ))
        seen_ptrs.add(ptr)

    return out


def candidate_signature(
    c: "ActiveTemplateCandidate",
) -> tuple[str, Optional[int], int, str]:
    """candidate の正規 signature (= 「同一スロットに同一値」識別用)。

    stale 排除のため、candidate を「source / ptr_slot / ptr / text
    (末尾空白除く)」の 4-tuple で識別する。前 poll の signature set と
    比較して新規かどうかを判定する。
    """
    return (c.source, c.ptr_slot, c.ptr, c.text.rstrip())


# 既知の input prompt の anchor 相対 ptr (A.EXE memory)。
# response/result 系 (A152/A153/A154 等) は意図的に含めない。
# (= stale "%s, thou art healed..." を継続採用しないため)
# ptr は npc_dialog.json の _meta に「A.EXE memory +0xXXXX」と記載のあるものを集約。
#
# facility 別の分類:
#   - temple: A155 寺院 寄付金額入力
#   - tavern: A002 宿泊日数、A131 部屋忍び込み確認
#   - negotiation: A600 対案入力 (negotiation route で扱われる)
_INPUT_PROMPT_FACILITY: dict[int, str] = {
    0x75F7: "temple",       # A155 'How much do you wish to donate?'
    0x739E: "tavern",       # A002 'How many days are you staying?'
    0x7379: "tavern",       # A131 'Are you trying to sneak into a room?'
    0x65CA: "negotiation",  # A600 'Enter counter offer :'
}

# input prompt の種別分類 (= facility よりさらに細かい区分)。
# 同じ施設内でも prompt 種別が異なる場合 (= A002 宿泊日数 vs A131 忍び込み YESNO)、
# 表示文脈ごとに採用条件を分けるための識別子。
#
# 分類:
#   - "stay_days":      A002 宿屋 宿泊日数入力 (= 部屋契約後の入力プロンプト)
#   - "sneak_yesno":    A131 宿屋 忍び込み YESNO (= 「Are you trying...?」)
#   - "donate_amount":  A155 神殿 寄付金額入力
#   - "counter_offer":  A600 交渉 対案入力
_INPUT_PROMPT_KIND: dict[int, str] = {
    0x75F7: "donate_amount",
    0x739E: "stay_days",
    0x7379: "sneak_yesno",
    0x65CA: "counter_offer",
}


def input_prompt_facility(c: "ActiveTemplateCandidate") -> str:
    """candidate が input prompt なら facility 名 ('temple'/'tavern'/'negotiation')
    を返す。input prompt でなければ空文字。

    判定は anchor 相対 ptr の集合一致。本文文字列ではなく ptr で識別する
    (= 表示文字列が動的に変わっても安定)。
    """
    return _INPUT_PROMPT_FACILITY.get(c.ptr, "")


def input_prompt_kind(c: "ActiveTemplateCandidate") -> str:
    """candidate が既知 input prompt なら種別を返す。なければ空文字。

    facility よりさらに細かい区分。同じ施設の異なるプロンプトを区別する。
    例: tavern 内で stay_days (A002) と sneak_yesno (A131) を区別する。
    """
    return _INPUT_PROMPT_KIND.get(c.ptr, "")


# 施設表示 surface 種別 (= input prompt より広い概念、結果文や契約文も含む)。
# 同じ施設の異なる表示文脈を区別する。A.EXE memory テンプレ群に対応。
#
# 分類:
#   - "tavern_stay_days":     A002 宿屋 宿泊日数入力 (= 入力プロンプト)
#   - "tavern_sneak_confirm": A131 宿屋 忍び込み確認 YESNO
#   - "tavern_sneak_result":  A130/A132 宿屋 忍び込み成功/失敗結果
#   - "tavern_room_contract": A133 宿屋 部屋契約成立
#   - "tavern_cost_show":     A134 宿/治癒 価格表示
#   - "tavern_cost_confirm":  A135 宿/治癒 承諾確認
#   - "temple_donate_amount": A155 神殿 寄付金額入力
#   - "negotiation_counter":  A600 交渉 対案入力
_TEMPLATE_SURFACE_KIND: dict[int, str] = {
    # tavern
    0x739E: "tavern_stay_days",        # A002
    0x7361: "tavern_sneak_result",     # A130 失敗
    0x7379: "tavern_sneak_confirm",    # A131
    0x73C6: "tavern_sneak_result",     # A132 成功 (= A130 と同 surface)
    0x73EA: "tavern_room_contract",    # A133
    0x7420: "tavern_cost_show",        # A134
    0x7434: "tavern_cost_confirm",     # A135
    # temple
    0x75F7: "temple_donate_amount",    # A155
    # negotiation
    0x65CA: "negotiation_counter",     # A600
}


def template_surface_kind(c: "ActiveTemplateCandidate") -> str:
    """candidate が既知 template surface なら種別を返す。なければ空文字。

    施設表示 surface 種別を返す。`input_prompt_kind` は入力プロンプト専用
    だが、本関数は結果文・契約文・費用表示等も含む広範な分類を返す。
    """
    return _TEMPLATE_SURFACE_KIND.get(c.ptr, "")


def select_facility_surface_candidate(
    candidates: list["ActiveTemplateCandidate"],
    accepted_surface_kinds: set,
    lookup_hit: callable,
) -> tuple[Optional["ActiveTemplateCandidate"], list[tuple[str, str]]]:
    """施設会話の任意 surface を採用する純関数。

    `select_facility_yesno_candidate` を一般化し、複数の surface kind を
    許容するセレクタ。宿屋 YESNO のように「忍び込み確認」「費用承諾」等の
    複数 surface が同じ画面に出る可能性に対応する。

    優先順:
      1. source="current_ptr" で kind ∈ accepted + lookup_hit → 採用
      2. source="active_slot" で kind ∈ accepted + lookup_hit → 採用
      3. kind ∉ accepted の候補は採用しない (= stale 残置排除)

    複数候補が同優先度で hit する場合は最初に検出されたものを採用する
    (= source 内の順序依存、stale 排除は kind フィルタで担保)。

    Args:
      candidates: 候補リスト (source / ptr / text を持つ)
      accepted_surface_kinds: 採用する surface kind の set
      lookup_hit: 文字列を受け取り辞書 hit なら True を返す callable

    Returns:
      (採用 candidate or None, 各候補の (decision, reason) リスト)
      decision: 'selected' / 'rejected'
      reason:   'surface_mismatch' / 'no_lookup_hit' / 'priority_lower' / 'ok' /
                'lookup_error'
    """
    decisions: list[tuple[str, str]] = []
    selected: Optional["ActiveTemplateCandidate"] = None
    selected_priority = 999

    for c in candidates:
        kind = template_surface_kind(c)
        if kind not in accepted_surface_kinds:
            decisions.append(("rejected", "surface_mismatch"))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(("rejected", "no_lookup_hit"))
                continue
        except Exception:
            decisions.append(("rejected", "lookup_error"))
            continue
        if c.source == "current_ptr":
            prio = 0
        elif c.source == "active_slot":
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(("selected", "ok"))
        else:
            decisions.append(("rejected", "priority_lower"))
    return selected, decisions


def is_active_template_input_prompt(c: "ActiveTemplateCandidate") -> bool:
    """candidate が既知の input prompt か。"""
    return c.ptr in _INPUT_PROMPT_FACILITY


def select_facility_yesno_candidate(
    candidates: list["ActiveTemplateCandidate"],
    expected_prompt_kind: str,
    lookup_hit: callable,
) -> tuple[Optional["ActiveTemplateCandidate"], list[tuple[str, str]]]:
    """施設 YESNO 描画用の候補選択純関数。

    `select_active_template_candidate` と同じ stale 排除原則を取りつつ、
    期待する prompt kind に一致する候補だけを採用する。

    優先順:
      1. `source="current_ptr"` で kind 一致 + lookup_hit → 採用
      2. `source="active_slot"` で kind 一致 + lookup_hit → 採用
      3. kind 不一致の active_slot 候補は採用しない (= stale 残置を捨てる)

    Args:
      candidates: 候補リスト (source / ptr / text を持つ)
      expected_prompt_kind: 採用する prompt kind (例 'sneak_yesno')
      lookup_hit: 文字列を受け取り辞書 hit なら True を返す callable

    Returns:
      (採用 candidate or None, 各候補の (decision, reason) リスト)
      decision は 'selected' / 'rejected' のいずれか。
      reason は 'kind_mismatch' / 'no_lookup_hit' / 'priority_lower' / 'ok' 等。
      呼出側で診断ログ出力に使う。
    """
    decisions: list[tuple[str, str]] = []
    selected: Optional["ActiveTemplateCandidate"] = None
    selected_priority = 999  # 小さいほど優先

    for c in candidates:
        kind = input_prompt_kind(c)
        if kind != expected_prompt_kind:
            decisions.append(("rejected", "kind_mismatch"))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(("rejected", "no_lookup_hit"))
                continue
        except Exception:
            decisions.append(("rejected", "lookup_error"))
            continue
        # 優先度: current_ptr=0, active_slot=1, その他=2
        if c.source == "current_ptr":
            prio = 0
        elif c.source == "active_slot":
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(("selected", "ok"))
        else:
            decisions.append(("rejected", "priority_lower"))
    return selected, decisions


# IMG ごとに許可する input_prompt_kind / template_surface_kind を絞り込む。
# YESNO.IMG / NEWPOP.IMG / MENU_RT.IMG はそれぞれ異なる用途で使われるため、
# active_slot 残置 (= 直前 flow で load された stale ptr) を別 IMG 文脈で
# 誤採用しないようにする。
#
# 観測:
#   YESNO.IMG: A131 'sneak_yesno' / A135 'cost_confirm' YES/NO 確認
#   NEWPOP.IMG / MENU_RT.IMG: A002 'stay_days' / A155 'donate_amount' /
#       A600 'counter_offer' 入力プロンプト
#       A133 'room_contract' / A134 'cost_show' / A130/A132 'sneak_result' 結果文
#
# 不明 IMG (= 上記以外) では facility 一致のみで判定する。
_IMG_ALLOWED_INPUT_KINDS: dict[str, frozenset] = {
    "YESNO.IMG":   frozenset({"sneak_yesno"}),
    "NEWPOP.IMG":  frozenset({"stay_days", "donate_amount", "counter_offer"}),
    "MENU_RT.IMG": frozenset({"stay_days", "donate_amount", "counter_offer"}),
}
_IMG_ALLOWED_SURFACE_KINDS: dict[str, frozenset] = {
    "YESNO.IMG": frozenset({
        "tavern_sneak_confirm",     # A131
        "tavern_sneak_result",      # A130/A132 (= popup 残置 YESNO 跨ぎ)
        "tavern_cost_confirm",      # A135
    }),
    "NEWPOP.IMG": frozenset({
        "tavern_stay_days", "tavern_sneak_result", "tavern_room_contract",
        "tavern_cost_show", "temple_donate_amount", "negotiation_counter",
    }),
    "MENU_RT.IMG": frozenset({
        "tavern_stay_days", "tavern_sneak_result", "tavern_room_contract",
        "tavern_cost_show", "temple_donate_amount", "negotiation_counter",
    }),
}


def _allowed_input_kinds_for_img(img_name: str) -> Optional[frozenset]:
    """img_name に対して許可される input_prompt_kind の set。
    None なら制限なし (= 不明 IMG 用)。"""
    return _IMG_ALLOWED_INPUT_KINDS.get((img_name or "").upper())


def _allowed_surface_kinds_for_img(img_name: str) -> Optional[frozenset]:
    """img_name に対して許可される template_surface_kind の set。
    None なら制限なし (= 不明 IMG 用)。"""
    return _IMG_ALLOWED_SURFACE_KINDS.get((img_name or "").upper())


def select_active_template_candidate(
    candidates: list["ActiveTemplateCandidate"],
    ctx_key: tuple,
    prev_ctx_key: Optional[tuple],
    prev_signatures: frozenset,
    lookup_hit: callable,
    active_facility: str = "",
    img_name: str = "",
) -> Optional["ActiveTemplateCandidate"]:
    """active_template 候補の中から採用すべき candidate を選ぶ純関数。

    採用優先順:
      1. `source="current_ptr"` で `lookup_hit(text)` が True → 採用
         (= 「いま画面表示中」を意味する最強の手がかり)
      2. `source="active_slot"` かつ既知 input prompt で facility 一致 +
         IMG-許可 prompt kind → 採用
         (= A155 のような prompt は context 安定後も表示中であり、
            facility gate により他施設文脈の stale を排除。
            IMG ごとに許可する input_prompt_kind を絞り、前 flow 残置
            A002 stay_days を YESNO.IMG sneak 文脈で誤採用する症状を防ぐ)
      3. `source="active_slot"` template_surface_kind が facility 一致 +
         IMG-許可 surface kind → 採用
      4. その他 active_slot 候補 → **採用しない**
         (= response/result 系 active_slot は stale が普通に残るため、
            ctx_changed / signature 変化を根拠に表示すると flicker や
            誤翻訳になる。response/result の表示は current_ptr / response
            buffer / negotiation 等の正規経路に委ねる)

    Args:
      candidates: read_active_template_candidates() の結果
      ctx_key, prev_ctx_key, prev_signatures: 互換のため残置 (未使用)
      lookup_hit: 文字列を受け取り辞書 hit なら True を返す callable
      active_facility: 現在 active な facility session 名
                       ('temple' / 'tavern' / '' 等)
      img_name: 現在の IMG 名。
                YESNO.IMG / NEWPOP.IMG / MENU_RT.IMG などで surface kind を
                絞り込む。空文字なら制限なし。

    Returns:
      採用 candidate、なければ None
    """
    _allowed_input_kinds = _allowed_input_kinds_for_img(img_name)
    _allowed_surface_kinds = _allowed_surface_kinds_for_img(img_name)

    # 1. current_ptr 優先 (= ctx 変化や signature 変化を待たない)
    for c in candidates:
        if c.source != "current_ptr":
            continue
        try:
            if lookup_hit(c.text):
                return c
        except Exception:  # noqa: BLE001
            continue

    # 2. active_slot input prompt + facility 一致のみ採用。
    # facility gate により他施設文脈の stale prompt は採用しない。
    # IMG ごとに許可される input_prompt_kind を絞り込む。
    if active_facility:
        for c in candidates:
            if c.source != "active_slot":
                continue
            facility = input_prompt_facility(c)
            if not facility:
                continue
            if facility != active_facility:
                continue
            if _allowed_input_kinds is not None:
                if input_prompt_kind(c) not in _allowed_input_kinds:
                    continue
            try:
                if lookup_hit(c.text):
                    return c
            except Exception:  # noqa: BLE001
                continue

    # 3. active_slot template_surface_kind + facility 一致なら採用。
    # input_prompt_facility より広い surface 種別 (= 宿屋忍び込み結果/部屋契約/
    # 価格表示/承諾確認/神殿寄付プロンプト/交渉対案 等) を補足する。
    # _TEMPLATE_SURFACE_KIND の値は 'tavern_*' / 'temple_*' / 'negotiation_*'
    # 形式なので先頭セグメントから facility を抽出する。
    # IMG ごとに許可される template_surface_kind を絞り込む。
    if active_facility:
        for c in candidates:
            if c.source != "active_slot":
                continue
            kind = template_surface_kind(c)
            if not kind:
                continue
            kind_facility = kind.split("_", 1)[0]
            if kind_facility != active_facility:
                continue
            if _allowed_surface_kinds is not None:
                if kind not in _allowed_surface_kinds:
                    continue
            try:
                if lookup_hit(c.text):
                    return c
            except Exception:  # noqa: BLE001
                continue

    # 4. 上記いずれにも該当しない active_slot は採用しない。
    # current_ptr / response buffer / negotiation 経路に委ねる。
    # ctx_key / prev_ctx_key / prev_signatures は将来の診断や
    # 別 fallback 設計に残置 (現在は未使用)。
    _ = (ctx_key, prev_ctx_key, prev_signatures)
    return None


__all__ = [
    "ACTIVE_TEMPLATE_PTR_OFFSETS",
    "ACTIVE_TEMPLATE_PTR_OFFSET",
    "CURRENT_TEXT_PTR_OFFSET",
    "TEMPLATE_RANGE_LOW",
    "TEMPLATE_RANGE_HIGH",
    "ActiveTemplateCandidate",
    "candidate_signature",
    "input_prompt_facility",
    "is_active_template_input_prompt",
    "is_response_buffer_pointer",
    "is_response_text_buffer_pointer",
    "is_runtime_message_buffer_pointer",
    "read_active_template",
    "read_active_templates",
    "read_active_template_candidates",
    "read_current_text_pointer",
    "select_active_template_candidate",
]
