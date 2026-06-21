"""神殿神官会話の応答候補読み取り(神殿分離内・自前バッファ走査)。

神官メニュー自体は shop_menu 経路、寄付額入力/費用確認は temple_cost 経路が担当する。
本モジュールは Bless/Cure/Heal の結果文やコスト確認文が応答バッファ領域に出た時を
扱う reader として神殿分離内に閉じる。

完全分離(L4): 応答バッファの読み取りは神殿が自前で行い、共有 popup11_response_reader
には依存しない。結果文は固定 offset ではなく **領域走査** で全 run を拾う。
理由(probe確定): 神官の解決済み結果本文(名前埋込済み)は応答バッファの
0x1044〜0x10C0 に **種別で可変 offset** で載り(回復 "%fn, thou art healed..." = 0x10A8、
"%fn is in perfect condition..." = 0x10B0 等)、先頭固定 offset 0x1044 だけを最初の run まで
読む方式では 0x1044 の詠唱一時文 "Curing ..." を拾って後続の結果文をマスクしていた。
全 run を走査すれば結果本文も候補化でき、辞書 lookup と一時文判定で正しく選別できる。

共有してよいのは翻訳辞書 lookup(npc_dialog_lookup)のみ(= 翻訳資源)。
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional


class TempleResponseCandidate(NamedTuple):
    text: str            # canonical (書式コード除去済の本文)
    lookup_hit: bool
    source_offset: int
    raw_text: str = ""   # 診断用の生テキスト (書式コード等を含むまま)


# 書式コード接頭辞 (TAB + 3桁ゼロ埋め + 本文) の検出。武具店一覧と同源の書式コードが
# 神官応答本文の先頭に混入する (例: "200R is in perfect condition")。
_FMT_PREFIX_RE = re.compile(r"^([0-9]{3})([A-Za-z].*)$", re.S)

# 回復申し出テンプレ ("... Can I give you some of our healing ...") の応答バッファに、
# 回復結果文 ("%fn is in perfect condition..." / "%fn, thou art healed...") が
# 上書き混入し、結果コアの前に申し出前置きが残る (実機: "Brotherhood of Mercy.
# Can I give you some of R is in perfect condition...")。この前置きが残ると
# lookup の %fn (= プレイヤー名) が前置きごと貪欲捕捉され、JA に英語前置きが
# 漏れる。申し出句 "Can I give you some of " 以降を結果本文として切り出す。
_HEAL_OFFER_CONTAM_RE = re.compile(
    r"Can I give you some of\s+"
    r"(.+?(?:is in perfect condition|thou art healed).*)$",
    re.S,
)

_HEALED_RESULT_RE = re.compile(
    r"^(?P<subject>.+?)(?P<suffix>,\s*thou art healed.*)$",
    re.S,
)
_PERFECT_RESULT_RE = re.compile(
    r"^(?P<subject>.+?)(?P<suffix>\s+is in perfect condition.*)$",
    re.S,
)


def _strip_heal_offer_prefix(text: str) -> str:
    """回復申し出前置きが混入した結果文から結果コアだけを切り出す。

    申し出前置きが無い、または結果コアを含まない文は変更しない (= 申し出文
    そのものや他の結果文を壊さない)。
    """
    s = text or ""
    if "Can I give you some of" not in s:
        return s
    m = _HEAL_OFFER_CONTAM_RE.search(s)
    if m:
        return " ".join(m.group(1).split())
    return s


def _last_subject_token(prefix: str) -> str:
    """混入前置きの末尾から、結果本文の主語らしい最後の名前 token を切り出す。"""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'_-]*", prefix or "")
    if not tokens:
        return ""
    token = tokens[-1]
    if token[:1].islower():
        for idx, ch in enumerate(token):
            if ch.isupper():
                return token[idx:]
    return token


def _repair_result_subject_prefix(text: str) -> str:
    """結果本文の前に残った古い NPC 文を、主語部分だけに切り詰める。

    応答バッファ run が前回 NPC 文と連結し、
    "Lord ... Giants, thaR, thou art healed..." のように lookup の %fn が
    前置き全体を貪欲捕捉していた。結果本文の構文は「名前 + 結果句」なので、
    主語に空白/句読点を含む場合だけ最後の名前 token へ正規化する。
    """
    s = text or ""
    for rx in (_HEALED_RESULT_RE, _PERFECT_RESULT_RE):
        m = rx.match(s)
        if not m:
            continue
        subject = " ".join((m.group("subject") or "").split()).strip()
        if not subject:
            continue
        if not re.search(r"[\s,.;:]", subject):
            return s
        repaired = _last_subject_token(subject)
        if repaired:
            return repaired + m.group("suffix")
    return s


def canonicalize_priest_text(text: str, prev_byte: Optional[int] = None) -> str:
    """本文先頭の書式コード (3桁) / 回復申し出前置きを除去した canonical 本文を返す。

    判定:
      - run 直前 byte が TAB(0x09) かつ run が ^[0-9]{3}[A-Za-z] → 3桁を落とす
        (= 実メモリの TAB+3桁+本文 書式)。
      - 直前 byte が取れない場合も、3桁を落とした文が神官テンプレ文として成立する
        なら canonical を採用する (lookup/表示は canonical を使う)。
      - 回復結果に申し出前置きが残る場合は結果コアだけを採る。
    lookup / owner 判定 / is_temple_priest_text / is_transient / display は canonical を
    使い、raw_text は診断用に別途保持する。
    """
    s = text or ""
    m = _FMT_PREFIX_RE.match(s)
    if m:
        rest = m.group(2)
        if prev_byte == 0x09:
            s = rest
        elif is_temple_priest_text(rest):
            s = rest
    # 回復申し出/古い NPC 文の混入除去 (3桁除去後の本文に対しても適用)。
    return _repair_result_subject_prefix(_strip_heal_offer_prefix(s))


class TempleResponseRead(NamedTuple):
    candidates: list
    current_ptr: int | None


# 応答バッファ領域 (anchor 相対, (offset, length))。
#  - 0x929E: 費用確認 (This service will cost N) 等の応答本文
#  - 0x1040〜: 0x1044 "Curing ..." 詠唱一時文 + 0x10A8 結果本文 (X, thou art healed /
#    is in perfect condition) + 0x11E8 治療失敗本文 (We humbly beg ... cannot cure X)。
#    結果本文は種別で可変 offset。治療失敗文が 0x11E8 に出るため、窓を 0x200 まで広げ
#    取りこぼさない (ライブ実読で確認した所在に合わせる)。
_RESPONSE_REGIONS: tuple[tuple[int, int], ...] = ((0x929E, 512), (0x1040, 0x200))
_MIN_RESPONSE_LEN = 5

# 現在表示中テキストへの anchor 相対 pointer (u16 LE)。神殿では前景の種別判定
# (メニュー群 span 内かどうか)に使う。値そのものはバッファ内 offset ではない。
_CURRENT_TEXT_PTR_OFFSET = 0xA844

# 神殿メニュー群 span(probe確定の仮説): メニュー前景時の 0xA844 = 0x7593。
# この範囲を指す間はメニュー前景(= 詠唱一時文 "Curing" もメニュー ptr のまま出る)。
TEMPLE_MENU_PTR_LO = 0x725F
TEMPLE_MENU_PTR_HI = 0x765F

# popup/ダイアログ「開いているか」ゲート(probe + ライブ観測, 仮説):
#  +0x8F74 (1 byte) = 0x51 : メニュー前景(popup 無し)
#                   = 0x00 : popup/ダイアログ/一覧が前景(開いている)
# 宿屋の NEWPOP ゲート(0xB7C4) と同じ「popup 開」概念に見えたが、
# 実機ログで神殿メニュー表示中も 0x51↔0x00 に振動することが判明した。
# そのため神殿結果の前景証拠として単独使用しない。menu/popup の粗い
# ヒントと診断ログに限って使う。
# 回復結果は popup 表示中も 0xA844 がメニュー値(0x7593)のまま残るため、
# 「結果ダイアログが今画面に出ているか」を 0xA844 でも区別できない。
_POPUP_GATE_OFFSET = 0x8F74
_GATE_MENU_FOREGROUND = 0x51
_GATE_POPUP_OPEN = 0x00


def read_popup_gate(analyzer, anchor: int) -> int | None:
    """popup 開ゲート(+0x8F74)を読む。失敗時 None。"""
    try:
        raw = analyzer.read_bytes(anchor + _POPUP_GATE_OFFSET, 1)
    except (OSError, AttributeError):
        return None
    if not raw:
        return None
    return raw[0]


def gate_menu_foreground(gate: int | None) -> bool:
    """ゲート値がメニュー前景(popup 無し)を示すか。"""
    return gate == _GATE_MENU_FOREGROUND


def gate_popup_open(gate: int | None) -> bool:
    """ゲート値が popup/ダイアログ前景(開いている)を示すか。"""
    return gate == _GATE_POPUP_OPEN


# gate ヒステリシス閾値(poll)。単発の振動を無視して安定値で前景を確定する。
_GATE_HYSTERESIS_POLLS = 2


def temple_gate_foreground(w, analyzer, anchor: int) -> tuple[bool, bool, int]:
    """+0x8F74 ゲートをヒステリシス付きで読み、(menu_fg, popup_fg, gate) を返す。

    ゲート (menu=0x51 / popup=0x00) はメニュー中にも振動するため、結果前景の
    単独根拠には使えない。ここでは facility_render / temple_dialog が共有する
    粗い menu/popup ヒントとして、単発振動だけをヒステリシスで吸収する。

    状態は w._temple_gate_stable_value / _temple_gate_stable_count に保持する。
    """
    gate = read_popup_gate(analyzer, anchor)
    prev_val = getattr(w, "_temple_gate_stable_value", None)
    prev_cnt = int(getattr(w, "_temple_gate_stable_count", 0) or 0)
    if gate == prev_val:
        cnt = prev_cnt + 1
    else:
        cnt = 1
    w._temple_gate_stable_value = gate
    w._temple_gate_stable_count = cnt
    stable = cnt >= _GATE_HYSTERESIS_POLLS
    menu_fg = bool(stable and gate == _GATE_MENU_FOREGROUND)
    popup_fg = bool(stable and gate == _GATE_POPUP_OPEN)
    return menu_fg, popup_fg, (gate if gate is not None else -1)


# L4 段判定用アドレス (観測ベース, 仮説)。単一バイト等値に
# 依存せず、呼出側で img / shop_popup / 既存 latch と冗長化して使うこと。
#  - 0xA845 (npc_phase, = 0xA844 ptr 上位byte): 会話中(メニュー/結果段)で 0x75。
#  - 0xA83B: 施術選択/入力中で 0x75 (メニューでは 0x00)。
#  - 0x8F74 (gate): メニュー前景で 0x51。
_PHASE_NPC_OFFSET = 0xA845
_PHASE_AUX_OFFSET = 0xA847
_PHASE_MODE_OFFSET = 0xA84D
_PHASE_SELECT_OFFSET = 0xA83B
_PHASE_ACTIVE_VALUE = 0x75
_RESULT_VIEW_PTR_OFFSET = 0x8F6E
_RESULT_INTENT_HINT_OFFSET = 0xADB6
_BLESS_RESULT_INTENT_VALUE = 0x77
_BLESS_RESULT_VIEW_LO_BYTES = frozenset({0x59, 0x5A})
_LEGACY_BLESS_RESULT_PTR = 0x1D5A


class TempleViewState(NamedTuple):
    """神殿 L4 の前景 view を 1 つに確定した結果。"""

    kind: str
    phase: str
    values: dict


def _read_u8(analyzer, anchor: int, off: int) -> int | None:
    try:
        b = analyzer.read_bytes(anchor + off, 1)
        return b[0] if b else None
    except (OSError, AttributeError):
        return None


def _read_u16(analyzer, anchor: int, off: int) -> int | None:
    try:
        b = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if not b or len(b) < 2:
        return None
    return b[0] | (b[1] << 8)


def classify_temple_view(analyzer, anchor: int) -> TempleViewState:
    """神殿 L4 の前景 view を単一結論へ分類する。

    判定軸は神殿分離内で完結する観測信号:
    +0x8F74 / +0xA83B / +0xA845 / +0xA847 / +0x8F6E / +0xADB6。
    呼び出し側はこの ``kind`` を主軸に描画 owner を決め、個別候補や
    hold 状態を前景分類の代替軸にしない。
    """
    gate = _read_u8(analyzer, anchor, _POPUP_GATE_OFFSET)
    npc = _read_u8(analyzer, anchor, _PHASE_NPC_OFFSET)
    sel = _read_u8(analyzer, anchor, _PHASE_SELECT_OFFSET)
    aux = _read_u8(analyzer, anchor, _PHASE_AUX_OFFSET)
    mode = _read_u8(analyzer, anchor, _PHASE_MODE_OFFSET)
    result_ptr = _read_u16(analyzer, anchor, _RESULT_VIEW_PTR_OFFSET)
    intent = _read_u8(analyzer, anchor, _RESULT_INTENT_HINT_OFFSET)
    result_lo = (result_ptr & 0xFF) if isinstance(result_ptr, int) else None
    values = {
        "gate": gate,
        "npc": npc,
        "sel": sel,
        "aux": aux,
        "mode": mode,
        "result_ptr": result_ptr,
        "result_lo": result_lo,
        "intent": intent,
    }

    if gate == _GATE_MENU_FOREGROUND:
        return TempleViewState("menu", "menu", values)

    if (
        sel == _PHASE_ACTIVE_VALUE
        and npc == 0x00
        and aux == 0x00
        and (
            result_ptr == _LEGACY_BLESS_RESULT_PTR
            or (
                intent == _BLESS_RESULT_INTENT_VALUE
                and result_lo in _BLESS_RESULT_VIEW_LO_BYTES
            )
        )
    ):
        return TempleViewState("donation_blessing", "select_input", values)

    if sel == _PHASE_ACTIVE_VALUE:
        return TempleViewState("select_input", "select_input", values)

    if npc == _PHASE_ACTIVE_VALUE:
        return TempleViewState("service_result", "result", values)

    return TempleViewState("out", "out", values)

# 神殿_05(回復 YES) memdiff で結果本文 +0x10A8 と同時に変化したゲート近傍
# フラグ群。+0x8F74 はメニュー中にも振動するため前景証拠に使えないが、
# この小さな signature は「結果生成 edge」の補助信号として使う。
_RESULT_EDGE_OFFSETS = (0x8F7C, 0x8F7E, 0x8F92, 0x8F94)


def classify_temple_phase(analyzer, anchor: int) -> tuple[str, dict]:
    """互換 API: ``classify_temple_view`` の phase だけを返す。

    新規コードは view の単一結論 (``kind`` / ``phase`` / ``values``) を保持する
    ``classify_temple_view`` を使う。ここは既存 caller 向けに phase 文字列だけを
    戻す薄いラッパー。
    """
    view = classify_temple_view(analyzer, anchor)
    return view.phase, view.values


def read_temple_result_edge_signature(analyzer, anchor: int
                                      ) -> tuple[int, ...] | None:
    """結果生成 edge の補助 signature を読む。

    未解決の観測課題で挙がった +0x8F7C 帯を、同一結果文の
    再表示を検出するための補助信号として扱う。値そのものの意味は未確定なので
    4 byte の signature としてだけ比較し、表示判定の単独根拠にはしない。
    """
    try:
        vals = []
        for off in _RESULT_EDGE_OFFSETS:
            b = analyzer.read_bytes(anchor + off, 1)
            if not b:
                return None
            vals.append(b[0])
        return tuple(vals)
    except (OSError, AttributeError):
        return None


def is_temple_priest_text(text: str) -> bool:
    """神殿の神官会話テンプレ由来の文かを EN 本文から判定する。"""
    s = " ".join((text or "").split())
    if not s:
        return False
    if s.startswith("Receive our blessings"):
        return True
    if "thou art healed" in s:
        return True
    if "is in perfect condition" in s:
        return True
    if s.startswith("How much do you wish to donate?"):
        return True
    if s.startswith("Curing "):
        return True
    if s.startswith("We humbly beg your forgivness"):
        return True
    if s.startswith("This service will cost"):
        return True
    if s.startswith("Can't you afford it"):
        return True
    return False


def is_transient_priest_text(text: str) -> bool:
    """詠唱中の一時メッセージ(= 結果ではない)か。

    0x1044 "Curing ..." は施術中に出る一時文で、神官の結果(治療成否/回復)ではない。
    これを結果と誤読しないため、結果本文より優先度を下げて選別する(probe確定)。
    """
    return " ".join((text or "").split()).startswith("Curing ")


def lookup_temple_priest_text(text: str):
    """神殿神官会話として辞書 lookup できる場合だけ結果を返す。"""
    if not is_temple_priest_text(text):
        return None
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        return None
    try:
        return ndl.lookup(text)
    except Exception:  # noqa: BLE001
        return None


def format_temple_priest_text(text: str) -> str | None:
    """神殿神官会話の日本語文を返す。lookup miss 時は None。"""
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        return None
    result = lookup_temple_priest_text(text)
    if result is None:
        return None
    ja_tmpl, placeholders = result
    try:
        return ndl.format_japanese(ja_tmpl, placeholders)
    except Exception:  # noqa: BLE001
        return None


def read_current_text_pointer(analyzer, anchor: int) -> int | None:
    """0xA844 u16 LE を読む(前景種別判定用、神殿自前読み)。"""
    try:
        raw = analyzer.read_bytes(anchor + _CURRENT_TEXT_PTR_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if not raw or len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def pointer_in_menu_group(ptr: int | None) -> bool:
    """0xA844 ptr が神殿メニュー群 span 内か(= メニュー前景)。"""
    return ptr is not None and TEMPLE_MENU_PTR_LO <= ptr <= TEMPLE_MENU_PTR_HI


def _scan_runs(analyzer, anchor: int) -> list[tuple[int, str, Optional[int]]]:
    """応答バッファ領域から printable run を全列挙する。

    各領域を読み、0x20-0x7E の printable 連続を 1 run とし、
    (offset, text, prev_byte) を返す。prev_byte は run 直前の 1 byte
    (書式コード TAB=0x09 の検出用。run が領域先頭なら None)。
    非 printable(NUL / バイナリ / \\r 等)で run を区切るため、0x1044 "Curing\\0...0x10A8
    結果文" のように 1 領域内に複数 run が並んでも漏れなく拾える。
    """
    out: list[tuple[int, str, Optional[int]]] = []
    for base, length in _RESPONSE_REGIONS:
        try:
            raw = analyzer.read_bytes(anchor + base, length)
        except (OSError, AttributeError):
            continue
        if not raw:
            continue
        n = len(raw)
        i = 0
        while i < n:
            if not (0x20 <= raw[i] <= 0x7E):
                i += 1
                continue
            j = i
            while j < n and 0x20 <= raw[j] <= 0x7E:
                j += 1
            text = raw[i:j].decode("ascii", errors="replace").strip()
            if len(text) >= _MIN_RESPONSE_LEN:
                prev_b = raw[i - 1] if i > 0 else None
                out.append((base + i, text, prev_b))
            i = j + 1
    return out


def read_temple_response_candidates(analyzer, anchor: int
                                    ) -> TempleResponseRead:
    """応答バッファ領域を走査し、神官会話の lookup hit 候補を全て返す。"""
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        ndl = None
    candidates: list[TempleResponseCandidate] = []
    seen: set[tuple[int, str]] = set()
    for off, raw_text, prev_b in _scan_runs(analyzer, anchor):
        # 書式コード接頭辞を除去した canonical で判定・lookup する。
        canon = canonicalize_priest_text(raw_text, prev_b)
        if not is_temple_priest_text(canon):
            continue
        key = (off, canon)
        if key in seen:
            continue
        seen.add(key)
        hit = False
        if ndl is not None:
            try:
                hit = ndl.lookup(canon) is not None
            except Exception:  # noqa: BLE001
                hit = False
        if not hit:
            continue
        candidates.append(TempleResponseCandidate(
            text=canon, lookup_hit=True, source_offset=off,
            raw_text=raw_text))
    try:
        current_ptr = read_current_text_pointer(analyzer, anchor)
    except Exception:  # noqa: BLE001
        current_ptr = None
    return TempleResponseRead(candidates, current_ptr)


def has_temple_response_surface(analyzer, anchor: int) -> bool:
    """応答バッファ領域に神官会話の lookup hit 候補が居るか。

    神殿では 0xA844 はバッファ内 offset ではない(0x001E 等)ため、pointer 一致では
    判定できない。候補(神官 priest 文)が領域に存在するか否かで判定する。
    """
    read = read_temple_response_candidates(analyzer, anchor)
    return bool(read.candidates)


__all__ = [
    "TempleResponseCandidate",
    "TempleResponseRead",
    "TempleViewState",
    "canonicalize_priest_text",
    "classify_temple_phase",
    "classify_temple_view",
    "temple_gate_foreground",
    "format_temple_priest_text",
    "gate_menu_foreground",
    "gate_popup_open",
    "has_temple_response_surface",
    "is_temple_priest_text",
    "is_transient_priest_text",
    "lookup_temple_priest_text",
    "pointer_in_menu_group",
    "read_current_text_pointer",
    "read_popup_gate",
    "read_temple_result_edge_signature",
    "read_temple_response_candidates",
]
