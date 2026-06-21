"""
controllers/chargen_helpers.py — chargen 検出用の定数 + 純粋関数

含まれるもの:
  - chargen 関連のモジュール定数（_CHARGEN_OPENING_*, _CHARGEN_GOYENOW_*,
    _CHARGEN_NAME_RE, _CHARGEN_CLASS_JA, _CHARGEN_PEOPLE_JA,
    _CHARGEN_RACE_INF_TO_JA, _CHARGEN_DYNAMIC_PATTERNS）
  - garbage NPC バッファ判定パターン（_GARBAGE_NPC_PATTERNS）
  - 純粋関数 _is_garbage_npc_buffer / _looks_like_cinematic
"""

import re

import i18n_helper as i18n


def _load_chargen_class_ja() -> dict[str, str]:
    """クラス名 en→ja を i18n コアから取得する。

    クラス名（原文）と訳は `classes` カテゴリに収録されている。`classes` は v2
    公開 enable-set に含まれるため、**公開安全な v2 経路（`v2_category_entries`・
    original=en / text=ja）を優先**し、v2 未有効（dev）時のみ `originals` へ
    フォールバックする。`originals` は公開で空のため、これがないと公開で
    クラス名が英語のまま残る（ASK ABOUT/ステータス表示と同一バグクラス）。
    """
    out: dict[str, str] = {}
    for e in i18n.v2_category_entries("classes"):
        en = e.get("original")
        ja = e.get("text")
        if en and ja and en not in out:
            out[en] = ja
    if out:
        return out
    # dev フォールバック（v2 未有効・disk _original 直読み）。
    for id_, entry in i18n.originals("classes").items():
        en = entry.get("original") if isinstance(entry, dict) else None
        if not en:
            continue
        ja = i18n.text_opt(id_)
        if ja and en not in out:
            out[en] = ja
    return out


class _LazyClassJaMap(dict):
    """クラス名 en→ja の遅延構築マップ。

    モジュール import 時は v2 公開 runtime が未有効のことがあり（`enable_v2_public`
    は本マップ構築後に走る）、その時点で構築すると公開で空になる。空のあいだは
    アクセス毎に再構築を試み、非空で確定したらキャッシュする。
    """

    def _ensure(self) -> None:
        if not self:
            loaded = _load_chargen_class_ja()
            if loaded:
                self.update(loaded)

    def get(self, key, default=None):  # noqa: A003
        self._ensure()
        return super().get(key, default)

    def items(self):
        self._ensure()
        return super().items()

    def __contains__(self, key) -> bool:
        self._ensure()
        return super().__contains__(key)


# ────────────────────────────────────────────────────────────────
# post-chargen cinematic 関連
# ────────────────────────────────────────────────────────────────
# post-chargen cinematic（TEMPLATE.DAT エントリ 1400 / DreamGood）の本文を
# 検出する手がかり。当該文字列はプロセス空間内に存在するが、
# session/タイミングで address は変動する可能性があるため、
# (1) 既知 hint アドレスでまず読む（高速パス）
# (2) 失敗時は scan_string で prefix 検索（堅牢パス）
# の二段構え。prefix は Silmane の冒頭セリフで、AS-IS の Arena/OpenTESArena
# どちらでも cinematic の最初に書き込まれる。
_CHARGEN_OPENING_HINT_ADDR = 0x10764C10
_CHARGEN_OPENING_MAXLEN = 1024
# 全ページ読取用の大きめチャンク（4KB / メモリ 1 ページ分）
_CHARGEN_OPENING_FULLREAD = 4096
# scan_string の探索範囲（DOSBox 内ヒープ典型 32MB ウィンドウ）
_CHARGEN_OPENING_SCAN_START = 0x10000000
_CHARGEN_OPENING_SCAN_END   = 0x12000000
_CHARGEN_OPENING_PREFIXES = (
    "Do not fear for it is I",  # MainQuest TEMPLATE.DAT 1400 冒頭
)


# ────────────────────────────────────────────────────────────────
# GoYeNow 関連
# ────────────────────────────────────────────────────────────────
# GoYeNow テキストの観測仮説アドレス（仮説段階）。
# 観測値は限られており、複数セッション・複数キャラ名での再現は未確認。
# cinematic 同様、(1) hint addr 直読み → (2) 失敗時 scan_string の二段構え。
# scan_string 範囲は cinematic 用 32MB 流用ではなく hint 周辺 2MB に縮小。
_CHARGEN_GOYENOW_HINT_ADDR = 0x106D0930
_CHARGEN_GOYENOW_HINT_CHECKLEN = 32  # 先頭プレフィックス確認に十分な長さ
_CHARGEN_GOYENOW_PREFIX = b"Go ye now in peace"
_CHARGEN_GOYENOW_SCAN_START = 0x10600000
_CHARGEN_GOYENOW_SCAN_END   = 0x10800000


# ────────────────────────────────────────────────────────────────
# garbage NPC バッファ判定
# ────────────────────────────────────────────────────────────────
# garbage NPC バッファの追加パターン（Arena 内部 state file 参照等）
# WILD004.64 のような英数混合の resource filename を検出。
# rat@.cfa のような小文字 + @ を含む resource filename を検出。
#   RATS エリア進入時に NPC_DIALOG (+0x1044) へ "rat@.cfa"（ネズミ CFA
#   リソースファイル名）が書き込まれ、原文表示されることがあるため弾く。
_GARBAGE_NPC_PATTERNS = (
    re.compile(r"^[A-Z]+\.\d+$"),                                 # "STATES.65" 等
    re.compile(r"^[A-Z0-9_]+\.[A-Z]+$"),                          # "AUTOMAP.IMG" 等
    re.compile(r"^[a-zA-Z][a-zA-Z0-9_@]{0,7}\.[a-zA-Z0-9]{1,3}$"),# 8.3 風 filename（小文字 + @ も許容）
    re.compile(r"^\S{1,20}\.[a-zA-Z0-9]{1,3}$"),                  # スペースなし短文+拡張子
                                                                   # （""%@.cfa のような非英字始まり
                                                                   #   リソース参照を捕捉）
    re.compile(r"^[+-]?\d{1,3}$"),                                # "+1" / "-2" 等の
                                                                   # 短い stat 増減メッセージ
)


def _is_garbage_npc_buffer(text: str) -> bool:
    """Arena 内部 state file 参照や低印字率テキストを garbage として判定する。

    「同一文字 2 文字以上連続」フィルタは撤去済み。これは観測偏りに基づく
    誤った仮説で、正規のプレイヤー名入力（例: "RRR"）を garbage と誤判定して
    翻訳発火を抑止していたため。

    現状残しているのは以下の 2 種類のみ:
    - Arena 内部 state/asset file 参照パターン（"STATES.65" "AUTOMAP.64" 等）
    - 印字可能率が極端に低い文字列（NUL や制御文字主体）
    """
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    # Arena 内部 state/asset file 参照パターン
    for pat in _GARBAGE_NPC_PATTERNS:
        if pat.match(s):
            return True
    if len(s) < 4:
        return False
    # 印字可能率が極端に低い（NUL や制御文字主体）
    printable = sum(1 for c in s if 0x20 <= ord(c) < 0x7F)
    if printable / max(len(s), 1) < 0.5:
        return True
    return False


def _looks_like_cinematic(text: str) -> bool:
    """cinematic 本文として妥当か判定（短文・低印字率を弾く）。"""
    if not text or len(text) < 20:
        return False
    printable = sum(1 for c in text if 0x20 <= ord(c) < 0x7F or c in "\r\n\t")
    return (printable / max(len(text), 1)) >= 0.85


# ────────────────────────────────────────────────────────────────
# chargen 名前入力 / 種族 / クラス / プロヴィンス 辞書
# ────────────────────────────────────────────────────────────────
# chargen 名前入力画面: クラス名抽出用
_CHARGEN_NAME_RE = re.compile(r'will be thy name,\s+(\w+)\?', re.IGNORECASE)

_CHARGEN_CLASS_JA: dict[str, str] = _LazyClassJaMap()

_CHARGEN_PEOPLE_JA: dict[str, str] = {
    "Bretons": "ブレトン", "Redguards": "レッドガード", "Nords": "ノルド",
    "Dark Elves": "ダークエルフ", "High Elves": "ハイエルフ", "Wood Elves": "ウッドエルフ",
    "Khajiit": "カジート", "Argonians": "アルゴニアン", "Imperials": "インペリアル",
}

# inf キーの種族部分（_CHARGEN_RACE_*）→ 日本語名
_CHARGEN_RACE_INF_TO_JA: dict[str, str] = {
    "BRETON":    "ブレトン",
    "REDGUARD":  "レッドガード",
    "NORD":      "ノルド",
    "DARK_ELF":  "ダークエルフ",
    "HIGH_ELF":  "ハイエルフ",
    "WOOD_ELF":  "ウッドエルフ",
    "KHAJIIT":   "カジート",
    "ARGONIAN":  "アルゴニアン",
}


# 通常綴り州名で location カテゴリに無いものの direct-id alias。
# 例: "Summerset Isle"（通常綴り）は location に無いが、Arena キャラ作成実文は "Summurset"
# 系で location 直引きできる。通常綴りのみ glossary の alias で明示的に解決する。
_PROVINCE_ALIASES = {"summerset isle": "glossary.summerset_isle.0"}


def _translate_province(en: str) -> str:
    """州名 en の現在言語訳を返す（未解決は en）。

    州名は `location_lookup`（direct-id・原文スラッグ直引き）で解決し、通常綴りで
    location に無いもの（Summerset Isle）のみ `_PROVINCE_ALIASES` の direct-id
    alias で解決する。
    """
    if not en:
        return en
    from location_lookup import lookup as _loc_lookup
    ja = _loc_lookup(en)
    if ja:
        return ja
    alias_id = _PROVINCE_ALIASES.get(en.strip().lower())
    if alias_id:
        ja = i18n.text_opt(alias_id)
        if ja:
            return ja
    return en


# ────────────────────────────────────────────────────────────────
# chargen 動的テキストパターン
# ────────────────────────────────────────────────────────────────
# (検出regex, inf_key, 抽出regex, 代入関数, 原文サフィックス_or_None)
# 代入関数: re.Match → {プレースホルダー: 代入値} を返す
# 原文サフィックス: 原文表示テキストの末尾に付加する文字列（Yes/No 等）
_CHARGEN_DYNAMIC_PATTERNS: list[tuple] = [
    (
        re.compile(r'From where dost thou hail', re.IGNORECASE),
        "_CHARGEN_PROVINCE_",
        re.compile(r'From where dost thou hail,\s+(.+?)\s+the\s+(\w+)\?', re.IGNORECASE),
        lambda m: {"[name]": m.group(1),
                   "[クラス]": _CHARGEN_CLASS_JA.get(m.group(2), m.group(2))},
        None,
    ),
    (
        re.compile(r'Thou hast chosen .+?, land of the', re.IGNORECASE),
        "_CHARGEN_PROVINCE_CONFIRM_",
        re.compile(r'Thou hast chosen (.+?), land of the (.+?)\.', re.IGNORECASE),
        lambda m: {"[プロヴィンス]": _translate_province(m.group(1)),
                   "[種族]": _CHARGEN_PEOPLE_JA.get(m.group(2), m.group(2))},
        "\n\nYes\nNo",
    ),
    (
        re.compile(r'Then thou wilt be known as the', re.IGNORECASE),
        "_CHARGEN_COMPLETE_",
        re.compile(
            r'Then thou wilt be known as the (\w+) (.+?), who wouldst call (.+?), land of the (.+?), h(?:er|is) home\.',
            re.IGNORECASE),
        lambda m: {"[クラス]": _CHARGEN_CLASS_JA.get(m.group(1), m.group(1)),
                   "[name]": m.group(2),
                   "[プロヴィンス]": _translate_province(m.group(3)),
                   "[種族]": _CHARGEN_PEOPLE_JA.get(m.group(4), m.group(4))},
        None,
    ),
]
