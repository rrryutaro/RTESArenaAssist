"""interior_id.py — Arena 店内 (Interior) 識別候補の定義と仮説評価ヘルパー (Probe)。

このモジュールは「現状判明している candidate オフセット」と「それぞれの候補に
ついて立てた仮説」を集約する。**いかなる候補も確定扱いしない**。値は観測中の
状態に応じて変化するため、Probe 上で複数状態のスナップショットを取り、各仮説の
妥当性を併存表示で確認する設計。

仮説の取り扱い方針:
- 各候補オフセットには「仮説 (hypothesis)」が複数紐づきうる
- 仮説には「マッピング (raw 値 → 解釈)」と「観測回数 / 整合観測数 / 反証観測数」
- 反証が出ても仮説は **削除せず保留** し、追加観測で再評価する
- 表示は「現在 raw 値 → 各仮説で解釈するとこうなる」を全候補・全仮説について並列
"""
from __future__ import annotations


# ══════════════════════════════════════════════════════════════
# 候補オフセット定義
# ══════════════════════════════════════════════════════════════
# CANDIDATE_OFFSETS[key] = {
#     "offset": int,
#     "size":   1 or 2,
#     "label":  str,
#     "note":   str,
#     "history": [ "観測 N: 状態タグ → raw=0xXX", ... ]
# }
CANDIDATE_OFFSETS: dict[str, dict] = {
    "bc8e": {
        "offset": 0x0BC8E, "size": 1,
        "label": "店内 在室判定 + MIF 識別 (+0x0BC8E) [強い仮説、主判別]",
        "note":  "0=街路, 非0=店内在室。値そのものは入店した Interior MIF を一意に示す "
                 "(BC8E_TO_INTERIOR_MIF 参照)。観測で 4 "
                 "Interior 一致。主判別大表示で扱うため仮説一覧からは除外。",
        "history": [
            "obs: 街路 → 0x00",
            "obs: 2 階建て宿屋 1F → 0x0A (TAVERN1.MIF)",
            "obs: 2 階建て宿屋 2F → 0x12 (TAVERN8.MIF)",
            "obs: 平屋宿屋 → 0x12 (TAVERN8.MIF)",
            "obs: 寺院 → 0x0E (TEMPLE2.MIF)",
            "obs: もう片方の寺院 → 0x06 (TEMPLE6.MIF)",
            "user: ダンジョン・各店の出入りで IN/OUT 判定はかなり正確、強い仮説",
        ],
    },
    "ccbd": {
        "offset": 0x0CCBD, "size": 1,
        "label": "階数判定候補 (+0x0CCBD) [反証あり、観測継続]",
        "note":  "宿屋 1F/2F メモリ差分 1 サンプルで 0x01→0x02 を観測 → 1-indexed floor "
                 "の有力候補と推測したが、ユーザー実機検証で階数判定として機能しない "
                 "ことが判明。1 サンプルの観測差分で確定扱いした分析が誤り "
                 "(feedback_detection_is_hypothesis 違反)。要追加観測。",
        "history": [
            "obs: 宿屋 1F → 0x01",
            "obs: 宿屋 2F → 0x02 (1 サンプル差分のみ)",
            "user: 実機検証で階数判定として機能していない (反証)",
        ],
    },
    "angle_7a4c": {
        "offset": 0x07A4C, "size": 1,
        "label": "方角候補 (+0x07A4C) [観測継続]",
        "note":  "124KB 4 方角 dump で N=9 / E=12 / S=13 / W=14。+0x07A4E と "
                 "N↔S 対称性あり。dx 成分 or cos 候補だが、線形マッピングは未確定。"
                 "要 8 方角 / 360° スイープ追加観測。",
        "history": [
            "obs: ほぼ N → 9",
            "obs: ほぼ E → 12",
            "obs: ほぼ S → 13",
            "obs: ほぼ W → 14",
        ],
    },
    "angle_7a4e": {
        "offset": 0x07A4E, "size": 1,
        "label": "方角候補 (+0x07A4E) [観測継続]",
        "note":  "124KB 4 方角 dump で N=13 / E=12 / S=9 / W=8。+0x07A4C と "
                 "対称、dy 成分 or sin 候補。要追加観測。",
        "history": [
            "obs: ほぼ N → 13",
            "obs: ほぼ E → 12",
            "obs: ほぼ S → 9",
            "obs: ほぼ W → 8",
        ],
    },
    "angle_7a50": {
        "offset": 0x07A50, "size": 2,
        "label": "方角候補 (+0x07A50, 2B LE) [観測継続]",
        "note":  "124KB 4 方角 dump で N=0x03A4 / E=0x000B / S=0x0425 / W=0x02A7 を観測。"
                 "全方角ユニーク値、連続値の可能性。要 360° スイープ観測で確定。",
        "history": [
            "obs: ほぼ N → 0x03A4",
            "obs: ほぼ E → 0x000B",
            "obs: ほぼ S → 0x0425",
            "obs: ほぼ W → 0x02A7",
        ],
    },
    "angle_afb1": {
        "offset": 0x0AFB1, "size": 1,
        "label": "方角候補 (+0x0AFB1) [反証あり]",
        "note":  "124KB 4 方角 dump で N=154 / E=5 / S=109 / W=66 と各方角ユニーク値だったが、"
                 "ユーザー実機検証で「その場回転で値変動、同方角でも違う値」が観測され、"
                 "方角を示しているとは思えない動作と判明。観測継続。",
        "history": [
            "obs: ほぼ N → 0x9A(154)",
            "obs: ほぼ E → 0x05(5)",
            "obs: ほぼ S → 0x6D(109)",
            "obs: ほぼ W → 0x42(66)",
            "user: その場回転で値変動するが、同方角で違う値が出る (反証)",
        ],
    },
    "rt_x": {
        "offset": 0xA854, "size": 2,
        "label": "rt_x (+0xA854、既知)",
        "note":  "プレイヤー現在位置 X (タイル単位)。確定済み",
        "history": [],
    },
    "rt_z": {
        "offset": 0xA856, "size": 2,
        "label": "rt_z (+0xA856、既知)",
        "note":  "プレイヤー現在位置 Z (タイル単位)。確定済み",
        "history": [],
    },
    "a845": {
        "offset": 0xA845, "size": 1,
        "label": "NPC_PHASE (+0xA845、既知)",
        "note":  "ダイアログ表示中フラグ。0x9A=入店メッセージ表示中、0x00=待機、他",
        "history": [],
    },
}


# ══════════════════════════════════════════════════════════════
# 仮説定義 — 副次的な仮説 (主判別は別途、+0x0BC8E + MIF 名識別で扱う)
# ══════════════════════════════════════════════════════════════
HYPOTHESES: dict[str, dict] = {
    "ccbd_floor": {
        "candidate_key": "ccbd",
        "label": "階数判定 (1-indexed) [反証あり]",
        "description": "+0x0CCBD = 1-indexed Interior floor 番号と推測したが、"
                       "ユーザー実機検証で機能していない。要追加観測",
        "mapping": {0x00: "(屋外?)", 0x01: "1F", 0x02: "2F",
                    0x03: "3F", 0x04: "4F"},
        "default": "?",
        "expected_states": ["interior_tavern_1F", "interior_tavern_2F"],
    },
}

# 主判別 (+0x0BC8E + MIF 識別) は仮説一覧と独立して扱うため、PRIMARY_HYPOTHESIS_KEY
# 経由の仮説評価対象には含めない。arena_viewer.py が CANDIDATE_OFFSETS["bc8e"] と
# BC8E_TO_INTERIOR_MIF を直接参照して大表示する。
PRIMARY_HYPOTHESIS_KEY = None


# ══════════════════════════════════════════════════════════════
# 階数判定仮説 (= 入店時 raw 値からの状態遷移ベース) [通常仮説]
# ══════════════════════════════════════════════════════════════
# +0x0BC8E の値そのもので階数を 一意化はできないが、「入店時の raw」と「現在 raw」
# の比較で「入店時の階」か「別の階」かは判別可能。これを通常仮説として扱う。
#
# ロジック:
#   入店遷移 (OUT→IN) 時点の raw 値を entry_raw に保存
#   入店中、current_raw == entry_raw → 入店時の階 (= 1F として扱う)
#   入店中、current_raw != entry_raw → 別の階 (= 2F 以上、通常は 2F)
#   level_count==1 の Interior (= 平屋) では raw 変化なし → 常に 1F
#
# 注意: 3 階以上の Interior があれば current_raw の値ごとに floor を割り当てるが、
# Arena では基本的に 1F-2F のみ観測なので、この単純判別で十分なはず (要観測継続)。


def estimate_floor(entry_raw: int | None,
                   current_raw: int | None,
                   level_count: int | None) -> int | None:
    """入店時 raw + 現在 raw + MIF level_count から現在 floor を推定する (0-indexed)。

    Returns:
        0 = 入店時の階 (= 1F 相当)
        1 = 別の階 (= 2F 相当)
        None = 判定不能 (= raw 取れない、または平屋で意味なし)
    """
    if entry_raw is None or current_raw is None:
        return None
    if level_count is None or level_count <= 1:
        return 0  # 平屋: 常に 1F
    if current_raw == entry_raw:
        return 0  # 入店時の階
    return 1      # 別の階


# ══════════════════════════════════════════════════════════════
# +0x0BC8E 値の観測履歴 (= 表示用情報、MIF 名一意化には使わない)
# ══════════════════════════════════════════════════════════════
# 当初は raw 値から MIF 名を直接マッピング (0x0A → TAVERN1.MIF 等) しようとしたが、
# ユーザー観測「2 階建て宿屋 2F = 0x12」「平屋宿屋 (= 別の MIF ファイル) = 0x12」が
# 同じ raw 値を示すため、raw 単独では MIF を一意化できない。
#
# 正しい MIF 特定経路:
#   入店遷移 (bc8e: 0 → 非0) のタイミングで街路時の最後の rt_x/rt_z (= door 位置)
#   と街名から CityViewer の facility 検索で個別 facility を特定 → mif_name + 名称。
#
# 本ヒント表は「raw 値が出たら、その建物の例として何が観測されたか」を示すための
# 参考情報のみ。確定ロジックには使わない。
BC8E_OBSERVED_EXAMPLES: dict[int, str] = {
    0x06: "TEMPLE6.MIF (寺院 別建物)",
    0x0A: "TAVERN1.MIF (2 階建て宿屋 1F)",
    0x0E: "TEMPLE2.MIF (寺院)",
    0x12: "TAVERN8.MIF (平屋宿屋) / TAVERN1.MIF 2F の両方で観測",
}


# ══════════════════════════════════════════════════════════════
# 観測状態タグ (Probe 上のスナップショット保存で使う)
# ══════════════════════════════════════════════════════════════
KNOWN_STATE_TAGS = [
    "city_road",            # 街路通常
    "city_automap",         # 街路でオートマップ表示中
    "interior_tavern_1F",   # 宿屋 1F
    "interior_tavern_2F",   # 宿屋 2F
    "interior_temple",      # 神殿内通常
    "interior_equipment",   # 武具店内通常
    "interior_mages_guild", # 魔術師ギルド内通常
    "interior_noble",       # 貴族館内通常
    "interior_palace",      # 宮殿内通常
    "interior_automap",     # 店内でオートマップ表示中
    "facing_north",         # 北向き
    "facing_east",          # 東向き
    "facing_south",         # 南向き
    "facing_west",          # 西向き
    "city_inn",             # 宿に宿泊中
    "dungeon_normal",       # ダンジョン内通常
    "wilderness",           # 野外
    "menu_systemmenu",      # システムメニュー表示中
    "menu_inventory",       # 装備画面表示中
    "menu_status",          # ステータス画面表示中
]


def evaluate_hypothesis(hyp_key: str, raw_value: int) -> str:
    """raw 値を仮説マッピングで解釈した文字列を返す。"""
    hyp = HYPOTHESES.get(hyp_key)
    if hyp is None:
        return "?"
    return hyp["mapping"].get(raw_value, hyp["default"])
