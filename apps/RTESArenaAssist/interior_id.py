from __future__ import annotations


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

PRIMARY_HYPOTHESIS_KEY = None




def estimate_floor(entry_raw: int | None,
                   current_raw: int | None,
                   level_count: int | None) -> int | None:
    if entry_raw is None or current_raw is None:
        return None
    if level_count is None or level_count <= 1:
        return 0
    if current_raw == entry_raw:
        return 0
    return 1


BC8E_OBSERVED_EXAMPLES: dict[int, str] = {
    0x06: "TEMPLE6.MIF (寺院 別建物)",
    0x0A: "TAVERN1.MIF (2 階建て宿屋 1F)",
    0x0E: "TEMPLE2.MIF (寺院)",
    0x12: "TAVERN8.MIF (平屋宿屋) / TAVERN1.MIF 2F の両方で観測",
}


KNOWN_STATE_TAGS = [
    "city_road",
    "city_automap",
    "interior_tavern_1F",
    "interior_tavern_2F",
    "interior_temple",
    "interior_equipment",
    "interior_mages_guild",
    "interior_noble",
    "interior_palace",
    "interior_automap",
    "facing_north",
    "facing_east",
    "facing_south",
    "facing_west",
    "city_inn",
    "dungeon_normal",
    "wilderness",
    "menu_systemmenu",
    "menu_inventory",
    "menu_status",
]


def evaluate_hypothesis(hyp_key: str, raw_value: int) -> str:
    hyp = HYPOTHESES.get(hyp_key)
    if hyp is None:
        return "?"
    return hyp["mapping"].get(raw_value, hyp["default"])
