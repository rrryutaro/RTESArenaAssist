
import os
import sys
import struct
import ctypes
import zlib

_ROOT = os.path.dirname(os.path.abspath(__file__))

from memory_core import (
    ArenaMemoryAnalyzer,
    MEMORY_BASIC_INFORMATION,
    MEM_COMMIT,
    PAGE_NOACCESS,
    PAGE_GUARD,
)
from viewer_constants import (
    GAMESTATE_OFFSET, GS_DEFS,
    TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ,
    TRIGGER_FLAG_OFFSET, TRIGGER_INDEX_OFFSET,
    FLAGS4_BITS, INF_PREFIXES,
    LIVE_MIF_OFFSET, LIVE_MIF_MAXLEN,
    MAP_NAME_OFFSET, MAP_NAME_MAXLEN,
    CHARGEN_STATE_OFFSET,
    RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK,
    RT_ANGLE_RANGE, RT_ANGLE_NORTH_RAW,
)

_LOG_BASE = (os.path.dirname(os.path.abspath(sys.executable))
             if getattr(sys, "frozen", False) else _ROOT)
LOG_DIR = os.path.join(_LOG_BASE, "output")
os.makedirs(LOG_DIR, exist_ok=True)

ANCHOR_PATTERN = b"BethesdaSoftworkRun-TimeLibrary"

_LOCATION_JP: dict[str, str] = {
    "Imperial Dungeons": "帝都牢獄",
    "Imperial City": "インペリアル・シティ",
    "North Point": "ノースポイント", "Daggerfall": "ダガーフォール",
    "Camlorn": "キャムルーン", "Shornhelm": "ショーンヘルム",
    "Wayrest": "ウェイレスト", "Evermore": "エバモア",
    "Farrun": "ファーラン", "Jehanna": "ジェハンナ",
    "Old Gate": "オールドゲート", "Meir Darguard": "メイル・ダーガード",
    "Kings Guard": "キングスガード", "Ilessen Hills": "イレッセン丘陵",
    "Portdun Creek": "ポートダン・クリーク", "Vermeir Wastes": "ヴェルメイル荒野",
    "Raven Spring": "レイヴン・スプリング", "Cloud Spring": "クラウド・スプリング",
    "Reich Gradkeep": "ライヒ・グラドキープ", "Glenpoint": "グレンポイント",
    "Ebon Wastes": "エボン荒野", "Moonguard": "ムーンガード",
    "Eagle Brook": "イーグル・ブルック", "Meir Thorvale": "メイル・ソルヴェイル",
    "White Haven": "ホワイト・ヘイヴン", "Normar Heights": "ノルマー高地",
    "Thorkan Park": "ソーカン・パーク", "Markwasten Moor": "マークワステン・ムーア",
    "Norvulk Hills": "ノーヴルク丘陵", "Wind Keep": "ウィンド・キープ",
    "Black Wastes": "ブラック荒野", "Dunkarn Haven": "ダンカーン・ヘイヴン",
    "Karthgran Vale": "カースグラン渓谷", "Dunlain Falls": "ダンレイン滝",
    "Mines of Khuras": "クーラスの鉱山", "Crypt of Hearts": "ハーツの地下墓地",
    "Sentinel": "センティネル", "Hegathe": "ヘガス",
    "Gilane": "ジレイン", "Taneth": "タネス",
    "Rihad": "リハド", "Dragonstar": "ドラゴンスター",
    "Elinhir": "エリンヒル", "Skaven": "スカーヴェン",
    "Sunkeep": "サン・キープ", "Lainebon Place": "レインボン集落",
    "Vulnim Gate": "ヴルニム門", "Heldorn Mount": "ヘルドーン山",
    "Riverpoint": "リバーポイント", "Roseguard": "ローズガード",
    "North Hall": "ノース・ホール", "Belkarth Guard": "ベルカース・ガード",
    "Dragon Grove": "ドラゴン・グローヴ", "Chasetown": "チェイス・タウン",
    "Shadymarch": "シェイディ・マーチ", "Lainlyn": "レインリン",
    "Riverview": "リバービュー", "Thorstad Place": "ソルスタッド集落",
    "Verkarth City": "ヴェルカース市", "Karnver Falls": "カーンヴェル滝",
    "Corten Mont": "コルテン・モン", "Chaseguard": "チェイス・ガード",
    "Stonemoor": "ストーン・ムーア", "Vulkneu Town": "ヴルクニュー町",
    "Stonedale": "ストーンデイル", "Nimbel Moor": "ニンベル・ムーア",
    "Dragon Gate": "ドラゴン門", "Cliff Keep": "崖の砦",
    "Stonekeep": "ストーンキープ", "Fang Lair": "ファング・レア",
    "Solitude": "ソリチュード", "Dawnstar": "ドーンスター",
    "Winterhold": "ウィンターホールド", "Snowhawk": "スノーホーク",
    "Riften": "リフテン", "Falcrenth": "ファルクレンス",
    "Whiterun": "ホワイトラン", "Windhelm": "ウィンドヘルム",
    "Karthwasten Hall": "カーズウェステン館", "Dragon Bridge": "ドラゴン橋",
    "Granitehall": "グラナイト館", "Oakwood": "オークウッド",
    "Stonehills": "ストーン丘陵", "Amol": "アモル",
    "Sunguard": "サン・ガード", "Vernim Wood": "ヴェルニム森",
    "Amber Guard": "アンバー・ガード", "Markarth Side": "マルカルス辺境",
    "Lainalten": "レインアルテン", "North Keep": "ノース・キープ",
    "Dunstad Grove": "ダンスタッド森", "Neugrad Watch": "ノイグラード見張所",
    "Black Moor": "ブラック・ムーア", "Greenwall": "グリーンウォール",
    "Dunpar Wall": "ダンパー城壁", "Riverwood": "リヴァーウッド",
    "Helarchen Creek": "ヘラーケン・クリーク", "Nimalten City": "ニマルテン市",
    "Laintar Dale": "レインタール渓谷", "Pargran Village": "パーグラン村",
    "Reich Corigate": "ライヒ・コリゲート", "Dragon Wood": "ドラゴン森",
    "Fortress of Ice": "氷の要塞", "Labyrinthian": "ラビリンシアン",
    "Ebonheart": "エボンハート", "Narsis": "ナーシス",
    "Blacklight": "ブラックライト", "Firewatch": "ファイアウォッチ",
    "Necrom": "ネクロム", "Mournhold": "モーンホールド",
    "Tear": "ティア", "Kragenmoor": "クラーゲンムーア",
    "Silgrad Tower": "シルグラッド塔", "Stoneforest": "ストーン森",
    "Karththor Dale": "カースソル渓谷", "Oaktown": "オーク町",
    "Eagle Moor": "イーグル・ムーア", "Silnim Dale": "シルニム渓谷",
    "Dragon Glade": "ドラゴン林", "Glen Haven": "グレン・ヘイヴン",
    "Cormar View": "コルマール眺望", "Reich Parkeep": "ライヒ・パーキープ",
    "Markgran Forest": "マークグラン森", "Verarchen Hall": "ヴェラーケン館",
    "Riverbridge": "リバーブリッジ", "Stonefalls": "ストーンフォールズ",
    "Old Run": "オールドラン", "Old Keep": "オールド・キープ",
    "Heimlyn Keep": "ハイムリン・キープ", "Darnim Watch": "ダーニム見張所",
    "Corkarth Run": "コルカース小道", "Amber Forest": "アンバー森",
    "Sailen Vulgate": "サイレン・ヴルゲート", "Greenheights": "グリーン高地",
    "Helnim Wall": "ヘルニム城壁", "Karththor Heights": "カースソル高地",
    "Black Gate": "黒門", "Dagoth-Ur": "ダゴス・ウル",
    "Dusk": "ダスク", "Sunhold": "サンホールド",
    "Alinor": "アリノール", "Shimmerene": "シマレーン",
    "Lillandril": "リランドリル", "Firsthold": "ファーストホールド",
    "Skywatch": "スカイウォッチ", "Cloudrest": "クラウドレスト",
    "Sea Keep": "海の砦", "Corgrad Wastes": "コルグラッド荒野",
    "Riverfield": "リバーフィールド", "Marnor Keep": "マーノル・キープ",
    "Archen Grangrove": "アーケン・グラングローヴ", "Vulkhel Guard": "ヴルケル・ガード",
    "Belport Run": "ベルポート小道", "West Guard": "ウェスト・ガード",
    "Karnwasten Moor": "カーンワステン・ムーア", "Wasten Coridale": "ワステン・コリデイル",
    "White Guard": "ホワイト・ガード", "Marbruk Brook": "マーブルック小川",
    "Graddun Spring": "グラダン泉", "Ebon Stadmont": "エボン・スタッドモン",
    "Glenview": "グレンビュー", "Holly Falls": "ホリー滝",
    "Rosefield": "ローズフィールド", "Old Falls": "オールド滝",
    "Kings Haven": "キングス・ヘイヴン", "Karndar Watch": "カーンダル見張所",
    "Thorheim Guard": "ソーハイム・ガード", "Silsailen Point": "シルサイレン岬",
    "Silver Wood": "シルバー森", "Riverwatch": "リバー見張所",
    "Temple of Mad God": "狂神の神殿", "Crystal Tower": "クリスタルの塔",
    "Eldenroot": "エルデンルート", "Silvenar": "シルヴェナール",
    "Woodhearth": "ウッドハース", "Falinesti": "ファリネスティ",
    "Greenheart": "グリーンハート", "Arenthia": "アレンシア",
    "Haven": "ヘイヴン", "Southpoint": "サウスポイント",
    "Thormar Keep": "ソーマル・キープ", "Vulkwasten Wood": "ヴルクワステン森",
    "Emperors Run": "皇帝の道", "Longvale": "ロング渓谷",
    "Longhaven": "ロング・ヘイヴン", "Karthdar Square": "カースダル広場",
    "Wasten Brukbrook": "ワステン・ブルックブルック", "Eagle Vale": "イーグル渓谷",
    "Vullain Haven": "ヴラン・ヘイヴン", "Cori Silmoor": "コリ・シルムーア",
    "Marbruk Field": "マーブルック野原", "Black Park": "ブラック・パーク",
    "Meadow Run": "メドウ小道", "Tarlain Heights": "タールレイン高地",
    "Archen Cormount": "アーケン・コーモン", "Moonmont": "ムーンモン",
    "Stone Fell": "ストーン・フェル", "Ebon Ro": "エボン・ロ",
    "Lynpar March": "リンパル・マーチ", "Stonesquare": "ストーン広場",
    "Green Hall": "グリーン館", "Heimdar City": "ハイムダル市",
    "Cormeir Spring": "コルメイル泉",
    "Selene's Web": "セレーネの巣", "Elden Grove": "エルデン森",
    "Corinth": "コリンス", "Alabaster": "アラバスター",
    "Senchal": "センシャル", "Rimmen": "リメン",
    "Torval": "トルヴァル", "Dune": "デューン",
    "Orcrest": "オークレスト", "Riverhold": "リバーホールド",
    "Seaplace": "シー集落", "Meir Lynmount": "メイル・リンマウント",
    "Ein Meirvale": "アイン・メイルヴェイル", "Greenhall": "グリーン館",
    "Brukreich Bridge": "ブルックライヒ橋", "Portneu View": "ポートニュー眺望",
    "Tenmar Forest": "テンマール森", "Darvulk Haven": "ダーヴルク・ヘイヴン",
    "Verkarth Hills": "ヴェルカース丘陵", "Cori Darglade": "コリ・ダーグレイド",
    "Tardorn Wood": "タードーン森", "Kings Walk": "キングスウォーク",
    "Chasemoor": "チェイス・ムーア", "Neumar Walk": "ノイマール小道",
    "Heimthor Mount": "ハイムソル山", "Helkarn Land": "ヘルカーン地方",
    "River Keep": "リバー・キープ", "Valley Guard": "渓谷の守備隊",
    "Darkarn Place": "ダーカーン集落", "Duncori Walk": "ダンコリ小道",
    "Chasegrove": "チェイス・グローヴ", "Black Heights": "ブラック高地",
    "Markgran Brook": "マークグラン小川", "South Guard": "サウス・ガード",
    "Temple of Agamanus": "アガマヌスの神殿", "Halls of Colossus": "コロッサスの大廊",
    "Stormhold": "ストームホールド", "Thorn": "ソーン",
    "Helstrom": "ヘルストロム", "Gideon": "ギデオン",
    "Soulrest": "ソウルレスト", "Blackrose": "ブラックローズ",
    "Lilmoth": "リルモス", "Archon": "アーコン",
    "Riverwalk": "リバーウォーク", "Tenmar Wall": "テンマール城壁",
    "Greenglade": "グリーン林", "Greenspring": "グリーン泉",
    "Rockgrove": "ロック・グローヴ", "Moonmarch": "ムーン・マーチ",
    "Seaspring": "シー泉", "Rockpark": "ロック・パーク",
    "Chasecreek": "チェイス・クリーク", "Alten Corimont": "アルテン・コリモン",
    "Branchmont": "ブランチ・モン", "Rockguard": "ロック・ガード",
    "Rockpoint": "ロックポイント", "Alten Markmont": "アルテン・マークモン",
    "Glenbridge": "グレン橋", "Stonewastes": "ストーン荒野",
    "Rockspring": "ロック泉", "Portdun Mont": "ポートダン・モン",
    "Branchgrove": "ブランチ・グローヴ", "Seafalls": "シー滝",
    "Longmont": "ロング・モン", "Alten Meirhall": "アルテン・メイル館",
    "Chasepoint": "チェイスポイント",
    "Vaults of Gemin": "ジェミンの保管庫", "Murkwood": "マーク森",
}

STARTUP_TEXT_QUERIES = [
    "The Elder Scrolls",
    "Chapter One",
    "The Arena",
    "The best techniques",
    "Gaiden Shinji",
    "For centuries",
    "different factions",
    "Start new game",
    "Load game",
    "Drop to Dos",
    "Load Saved Game",
    "Start New Game",
    "Exit",
]



def find_anchor(analyzer: ArenaMemoryAnalyzer) -> int | None:
    k = analyzer._kernel32
    CHUNK = 4 * 1024 * 1024
    addr = 0
    mbi  = MEMORY_BASIC_INFORMATION()
    candidates = []
    while addr < 0x7FFFFFFF:
        ret = k.VirtualQueryEx(
            analyzer.handle, ctypes.c_void_p(addr),
            ctypes.byref(mbi), ctypes.sizeof(mbi),
        )
        if not ret:
            break
        base = mbi.BaseAddress or 0
        sz   = mbi.RegionSize
        prot = mbi.Protect
        if (mbi.State == MEM_COMMIT
                and (prot & PAGE_NOACCESS == 0)
                and (prot & PAGE_GUARD   == 0)):
            offset = 0
            while offset < sz:
                chunk = min(CHUNK, sz - offset)
                try:
                    data = analyzer.read_bytes(base + offset, chunk)
                except OSError:
                    offset += chunk
                    continue
                idx = data.find(ANCHOR_PATTERN)
                if idx != -1:
                    candidates.append(base + offset + idx)
                offset += chunk
        addr = base + sz
    return max(candidates) if candidates else None



def _read_gs_val(analyzer, gs_base: int, off: int, typ: str):
    addr = gs_base + off
    try:
        if typ == "u8":
            return analyzer.read_bytes(addr, 1)[0]
        elif typ == "u16":
            return struct.unpack_from("<H", analyzer.read_bytes(addr, 2))[0]
        elif typ.startswith("str"):
            n   = int(typ[3:])
            raw = analyzer.read_bytes(addr, n)
            end = raw.find(b"\x00")
            return (raw[:end] if end >= 0 else raw).decode("ascii", errors="replace").strip()
    except OSError:
        return None


def read_game_state(analyzer, anchor: int) -> dict:
    gs_base = anchor + GAMESTATE_OFFSET
    result  = {"_gs_base": gs_base}
    for name, off, typ, _ in GS_DEFS:
        result[name] = _read_gs_val(analyzer, gs_base, off, typ)
    live_raw = read_live_buffer(analyzer, anchor + LIVE_MIF_OFFSET, LIVE_MIF_MAXLEN)
    result["LiveMifName"] = normalize_mif_name(live_raw)
    result["MapName"] = read_live_buffer(analyzer, anchor + MAP_NAME_OFFSET, MAP_NAME_MAXLEN)
    try:
        result["ChargenState"] = analyzer.read_bytes(anchor + CHARGEN_STATE_OFFSET, 1)[0]
    except OSError:
        result["ChargenState"] = None
    try:
        angle_bytes = analyzer.read_bytes(anchor + RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE)
        angle_u16 = int.from_bytes(angle_bytes, "little")
        result["PlayerAngle"] = (
            (angle_u16 & RT_ANGLE_MASK) - RT_ANGLE_NORTH_RAW
        ) % RT_ANGLE_RANGE
    except OSError:
        result["PlayerAngle"] = None
    return result



def read_live_buffer(analyzer, addr: int, maxlen: int) -> str:
    try:
        raw = analyzer.read_bytes(addr, maxlen)
        end = raw.find(b"\x00")
        if end >= 0:
            raw = raw[:end]
        start = 0
        while start < len(raw) and not (0x20 <= raw[start] <= 0x7E):
            start += 1
        text = raw[start:].decode("ascii", errors="replace").strip()
        if not text:
            return ""
        ratio = sum(32 <= ord(c) <= 126 for c in text) / len(text)
        return text if ratio >= 0.7 else ""
    except OSError:
        return ""


def normalize_mif_name(value: str | None) -> str:
    if not value:
        return ""
    name = value.strip()
    if not name:
        return ""
    if "." not in name:
        name = f"{name}.MIF"
    name = name.upper()
    if not name.endswith(".MIF"):
        return ""
    if len(name) > 13:
        return ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")
    if any(ch not in allowed for ch in name):
        return ""
    return name


def collect_startup_memory_diagnostics(
    analyzer: ArenaMemoryAnalyzer,
    anchor: int | None = None,
    start: int = 0x00000000,
    end: int = 0x7FFFFFFF,
    max_hits_per_query: int = 8,
) -> dict:
    queries = [(q, q.encode("ascii", errors="ignore")) for q in STARTUP_TEXT_QUERIES]
    hits: dict[str, list[dict]] = {q: [] for q, _ in queries}
    regions = []
    total_size = 0
    combined_crc = 0

    for base, size in analyzer._enum_readable_regions(start, end):
        try:
            data = analyzer.read_bytes(base, size)
        except OSError:
            continue

        region_crc = zlib.crc32(data) & 0xFFFFFFFF
        total_size += len(data)
        combined_crc = zlib.crc32(region_crc.to_bytes(4, "little"), combined_crc)
        combined_crc = zlib.crc32(len(data).to_bytes(8, "little"), combined_crc)
        regions.append({
            "base": f"0x{base:08X}",
            "size": len(data),
            "crc32": f"{region_crc:08X}",
            **({
                "offset_from_anchor": base - anchor,
                "offset_from_anchor_hex": f"0x{base - anchor:X}",
            } if anchor is not None else {}),
        })

        for query, needle in queries:
            if not needle or len(hits[query]) >= max_hits_per_query:
                continue
            offset = 0
            while len(hits[query]) < max_hits_per_query:
                idx = data.find(needle, offset)
                if idx < 0:
                    break
                ctx_start = max(0, idx - 24)
                ctx_end = min(len(data), idx + len(needle) + 56)
                ctx = data[ctx_start:ctx_end]
                item = {
                    "address": f"0x{base + idx:08X}",
                    "offset_from_region": idx,
                    "context_ascii": "".join(chr(b) if 32 <= b <= 126 else "." for b in ctx),
                }
                if anchor is not None:
                    item["offset_from_anchor"] = base + idx - anchor
                    item["offset_from_anchor_hex"] = f"0x{base + idx - anchor:X}"
                hits[query].append(item)
                offset = idx + 1

    return {
        "scan_range": {"start": f"0x{start:08X}", "end": f"0x{end:08X}"},
        "region_count": len(regions),
        "total_readable_bytes": total_size,
        "combined_crc32": f"{combined_crc & 0xFFFFFFFF:08X}",
        "regions": regions,
        "startup_text_hits": {
            query: {
                "hit_count_limited": len(items),
                "hits": items,
            }
            for query, items in hits.items()
        },
    }



def check_trigger_flag(analyzer, anchor: int, prev_flag: int,
                       trigger_indices: list, cached_trig_idx: int = 0) -> tuple:
    try:
        curr_flag = analyzer.read_bytes(anchor + TRIGGER_FLAG_OFFSET, 1)[0]
    except OSError:
        return "", prev_flag, 0, 0, 0

    if curr_flag == 0:
        return "", curr_flag, 0, 0, 0

    trig_idx = cached_trig_idx

    try:
        raw = analyzer.read_bytes(anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
    except OSError:
        raw = b""
    texts = []
    for chunk in raw.split(b"\x00"):
        text  = chunk.decode("ascii", errors="replace").strip().lstrip("~")
        ratio = sum(32 <= ord(c) <= 126 for c in text) / max(len(text), 1)
        if text and ratio >= 0.7:
            texts.append(text.replace("\r", " ").replace("\n", " "))

    if not texts:
        return f"[0x{curr_flag:02X}]", curr_flag, trig_idx, 0, 0

    if trig_idx and trig_idx not in trigger_indices:
        trigger_indices.append(trig_idx)

    n = len(texts)
    if not trig_idx:
        slot = 0
        body = texts[0]
    else:
        slot = (trig_idx // 0x20) - 1
        if 0 <= slot < n:
            body = texts[slot]
        else:
            slot = 0
            body = texts[0]

    return body, curr_flag, trig_idx, n, slot



def interpret_location(gs: dict) -> dict:
    mif = gs.get("LiveMifName") or gs.get("MifName") or ""
    inf = gs.get("InfName") or ""
    f4  = gs.get("Flags4")  or 0

    level_name = (gs.get("LevelName") or "").strip()
    map_name   = (gs.get("MapName")   or "").strip()
    name_key   = level_name or map_name
    if name_key:
        loc = _LOCATION_JP.get(name_key, name_key)
    else:
        mu = mif.upper()
        if mu == "IMPERIAL.MIF":    loc = "帝都 (Imperial City)"
        elif mu.startswith("CITY"): loc = f"都市 ({mif})"
        elif mu.startswith("TOWN"): loc = f"町 ({mif})"
        elif "WILD" in mu:          loc = f"ワイルダネス ({mif})"
        elif mif:                   loc = f"ダンジョン/建物 ({mif})"
        else:                       loc = "不明"

    interior = INF_PREFIXES.get(inf[:2].upper(), "")
    if not interior:
        if "palace" in inf.lower() or "imppal" in inf.lower():
            interior = "宮殿"

    angle = gs.get("PlayerAngle")
    dirs  = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]
    direction = dirs[round(angle / 64) % 8] if angle is not None else "不明"

    wf = gs.get("WeatherFlags") or 0
    if wf & 0x80:
        weather = "雨" if (wf & 0x01) else "雪" if (wf & 0x02) else "降水"
    else:
        weather = "晴れ"

    flags = [desc for bit, desc in FLAGS4_BITS.items() if f4 & bit]
    return {
        "location":  loc,
        "interior":  interior,
        "mif_name":  mif,
        "inf_name":  inf,
        "level":     gs.get("LevelName") or "",
        "floor":     gs.get("PlayerFloor") or 0,
        "x":         gs.get("PlayerX"),
        "z":         gs.get("PlayerZ"),
        "y":         gs.get("PlayerY"),
        "angle":     angle,
        "direction": direction,
        "weather":   weather,
        "flags":     flags,
    }



def next_log_no() -> int:
    files = [f for f in os.listdir(LOG_DIR)
             if f.startswith("gs_log_") and f.endswith(".json")]
    nums = []
    for f in files:
        try:
            nums.append(int(f.replace("gs_log_", "").replace(".json", "")))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 1


def next_bin_no() -> int:
    files = [f for f in os.listdir(LOG_DIR)
             if f.startswith("mem_dump_") and f.endswith(".bin")]
    nums = []
    for f in files:
        try:
            nums.append(int(f.replace("mem_dump_", "").replace(".bin", "")))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 1
