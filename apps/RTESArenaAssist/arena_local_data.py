"""arena_local_data.py — 公開版のローカルデータ provider（初回/版差時に再生成）。

ユーザーの Arena ディレクトリから VFS で資産を読み、決定論生成器（arena_regen）で
provider surface を再構築し、整数 ID 経路で v2 localpack（RTESArenaAssist.localpack）へ
集約する。起動時に「localpack が存在し Arena 版指紋一致かつ整合 OK」なら再利用、そう
でなければ再生成する。v2 localpack が唯一の Arena 由来 local provider である。

公開ビルドは Arena 原文を同梱せず、Arena 由来データ（原文アンカー surface・翻訳外生成
資産）はこの localpack から読む。dev では i18n/_original/ のディスク直読みを使う。

現フェーズの対象カテゴリは building_entry / npc_dialog / inf_text / npc_name_chunks
（いずれも Arena 資産由来分のみ）。inf_text の _CHARGEN_ 質問本文（Q_1〜Q_40）は
QUESTION.TXT（loose）由来としてパックに収録する。npc_dialog の A-key・inf_text の
_CHARGEN_ UI/結果系（ChooseClassCreation/SuggestedClass 等）・npc_name_chunks の
literals（いずれも A.EXE 由来）はパックに含めない（EXE 由来カテゴリ）。
inf_text の TEMPLATE_DAT_（main quest）は別経路。他は EXE 由来/未確定。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os

logger = logging.getLogger("RTESArenaAssist")


def _read_owned_text(disk_path: str, rel: str) -> "str | None":
    """Assist 所有データ（fingerprints/golden/_aexe_template 等）を読む。

    disk（dev/テスト）を優先し、無ければ exe 内 seed（app_resources）へフォールバックする。
    公開 frozen ではこれらを `_internal` に置かず seed から読む（pak 生成の入力でもあるため
    pak からは読めず、seed 直読みが必須）。無ければ None。
    """
    try:
        with open(disk_path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    try:
        import app_resources
        return app_resources.read_text(rel)
    except Exception:  # noqa: BLE001 - seed 不在等は None
        return None


# Arena ディレクトリの妥当性に要るファイル（DOS 大小無視・loose）。
_REQUIRED_ANY_EXE = ("A.EXE", "ACD.EXE")
_REQUIRED_BSA = "GLOBAL.BSA"

# ─────────────────────────────────────────────────────────────────────────
# 対応指紋（SHA-256）による対象版判定。
# EXE 由来の固定 offset 採取（arena_aexe.AKEY_ACD_OFFSETS / AEXE_TABLES）は、特定環境で
# 実測した image_base 相対 offset を固定表として適用するもの。よって適用前に「固定 offset を
# 当ててよい同一ファイルか」を実ファイル SHA-256 で機械確認する。対応しない版は黙って誤値を
# 出さず unknown 扱い＝EXE 固定 offset 採取を抑止し警告する（DAT/TEMPLATE/VFS 由来は継続）。
# Steam appmanifest/build id は補助情報で、最終判定は実ファイルハッシュ（本実装）で行う。
_FINGERPRINT_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "arena_fingerprints.json")
# 指紋採取対象（EXE 由来 offset は EXE に、資産セット同一性は EXE＋BSA に依存）。
_FINGERPRINT_FILES = ("ACD.EXE", "A.EXE", "GLOBAL.BSA")
# localpack meta キー（資産セット id・実ファイル指紋・EXE 採取有効化状態）。
_META_ASSET_SET = "arena_asset_set"
_META_ASSET_HASHES = "arena_asset_hashes"
_META_EXE_HARVEST = "exe_harvest_enabled"

# 公開ゴールデンマニフェスト（原文なし・公開同梱可）。生成器がローカル生成した
# カテゴリ別 manifest(source_id+source_hash)を参照として配置し、ユーザー環境の生成結果と
# 突合せて欠落/余剰/本文ズレを検出する（Assist 使用範囲で不足が生じないことを仕組みで
# 担保する）。tools/gen_golden_manifest.py が検証済み Arena から生成。
_GOLDEN_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "arena_golden_manifest.json")
GOLDEN_VERSION = 1

# パック収録カテゴリ集合のバージョン。**生成器の対象カテゴリを増やしたら必ず上げる**。
# Arena 版指紋が同じでも、旧パック（少ないカテゴリ）を再利用させないための staleness 鍵。
#   1: building_entry のみ
#   2: +npc_dialog / 3: +inf_text / 4: +npc_name_chunks
#   5: +chrgnq（_CHARGEN_ 質問本文・QUESTION.TXT 由来を inf_text へマージ）
#   chrgnq2: 質問エントリに text_display/text_panel（全文＝説明＋a/b/c 選択肢）を付与
#   atrade: +A-key A500台（宿屋の部屋提示・TAVERN.DAT を npc_dialog へマージ）
#   atradeshop: +A-key A600台 値切り本文 A601-A618（EQUIP/SELLING/MUGUILD.DAT・offline）
#   akeyrepair: +A-key A180台 修理屋値切り A182-A188（TEMPLATE.DAT #1417/#1418/#1424-1428・offline）
# EXE 由来（A.EXE）カテゴリはライブメモリ採取が必須のため、採取できたかで content_version を分ける:
#   BASE = EXE 由来抜き（DOSBox 未起動/採取不可時）/ AEXE = EXE 由来第1陣込み（races/calendar/titles/location_types）。
#   wmap: +world_map（CITYDATA.NN 由来・翻訳外 Arena 資産）
#   loc: +location _original（CITYDATA 由来 280 件）
_BASE_CONTENT_VERSION = "be+npcd+atrade+atradeshop+akeyrepair+inf+nnc+chrgnq2+wmap+loc/10"
#   aexe1: races/calendar/titles/location_types
#   aexe2: +classes/protect_locations
#   aexe3: +spells（category 内出現順写像）
#   aexe4: +item_enchantments/equipment_suffixes（全テーブル横断 値逆引き）
#   chargenui: +_CHARGEN_ UI/結果系（A.EXE CharacterCreation＋TEMPLATE 種族説明・analyzer 時のみ）
#   akeyui: +A-key UI（A0/A100-A400/A600 UI・純 A.EXE UI/ポップアップ・analyzer かつ ACD.EXE 時のみ）
#   akeyui2: +鑑定/魔術師ギルド呪文購入 3件（A191/A213_mages・複数行レコード join_ws）
#   aexeman: EXE 由来（A.EXE）カテゴリにも manifest を収録（golden 突合せ対象化）
#   chgnprov: +chargen_provinces（char_creation_province_names(8) 由来）
#   citygen: +city_generation（[CityGeneration] 構造・ACD.EXE 採取）
#   srcback27: +consumed3 source-back surfaces（spellsg65/spell_effect/magic_item/
#     material_item/effect_sub_cause/armor_prefix/public_builtin）。生成器に新 collector を追加した
#     ので content_version を上げ、既存 localpack を再生成させる（mages/item_materials enable の前提）。
#   v2pak28: 公開リソースモデルで _internal/i18n を撤去した際、v2 localpack 生成が
#     source_id_map/bundle を _internal 直読みして失敗していた（公開ビルドで RTESArenaAssist.localpack
#     未生成→v2 無効→v1 後退で mages 等が原文/混訳）。seed フォールバック化で是正。既存 srcback27
#     localpack には v2 pak が無いため content_version を上げて再生成させる。
#   askchrome29: ask_about_menu の見出し/選択肢（chrome）を anchor+0x8525 の固定常駐テンプレ
#     から採取し source-back。従来は place_* のみ採取で chrome が公開 pak に未登録のため
#     ASK ABOUT?/Who are you? 等が英語のままだった。新採取を反映するため content_version を上げる。
_AEXE_CONTENT_VERSION = "be+npcd+atrade+atradeshop+akeyrepair+inf+nnc+chrgnq2+aexe4+chargenui+akeyui2+aexeman+wmap+chgnprov+loc+citygen+itemmat+monsters+partial2+items+reclass+srcback27+v2pak28+askchrome29+keymat30+citygennames31/31"
_META_CONTENT_VERSION = "content_version"

# EXE 由来 curation テンプレート（i18n/_aexe_template/<cat>.json・Arena 原文を含まない）。
# 第1陣=races/calendar/titles/location_types、第2陣=classes/protect_locations、
# 第3陣=spells、第4陣=item_enchantments/equipment_suffixes。
_AEXE_CATEGORIES = ("races", "calendar", "titles", "location_types",
                    "classes", "protect_locations", "spells",
                    "item_enchantments", "equipment_suffixes",
                    # chargen_provinces: char_creation_province_names(8) 由来の
                    # キャラ作成画面州名（direct-id 撤回の再構築）。
                    "chargen_provinces",
                    # item_materials: material_names(8) 由来の素材名（ライブ採取で
                    # content 照合・8/14 部分カバレッジ・残6は非テーブル源）。
                    "item_materials",
                    # monsters: creature_names(23)＋classes.names(9・classes と
                    # source_id 共有 fan-out) 由来。32/54 部分・残22は非テーブル源
                    # （combat phrase 等）。ライブ採取 content 照合。
                    "monsters",
                    # F案部分カテゴリ第2陣（arena_generated・ライブ採取 content 照合・
                    # 訳違い重複0＝value() 曖昧なし・部分カバレッジ・表共有 fan-out）。
                    "equipment", "character", "mages", "dungeon",
                    # items: 全 equipment テーブル由来。**訳違い重複(Gold/Iron/Silver)
                    # は除外**=value() 曖昧回避(section 依存訳・items のみ該当)。103/153。
                    # 多 consumer(value()＋_item_names section last-wins)の enable は後段。
                    "items",
                    # source-backed 再分類（live_surface→arena_generated）：
                    # settlement_types→location_types(3/4)・chargen_race_descriptions→
                    # races.singular(8/8)。fan-out 共有。
                    "settlement_types", "chargen_race_descriptions",
                    # ACD.EXE 固定テーブル由来の live_surface→arena_generated 再分類
                    # （クリーン ACD.EXE 採取 content 照合・partial）：
                    # pronouns→entities.pronoun_names(5/6)・relations→entities.relation_names(9/14)。
                    # ask_about_menu→目的地2表(11/20・見出し/optは非クリーンでunmatched)。
                    "pronouns", "relations", "ask_about_menu",
                    # status_buffer_text→既存 calendar 表共有(day=weekday_names 7・
                    # month=month_names 12・19/35・value 照合・fan-out)。era(数値)/part/
                    # health は非テーブル源で unmatched。
                    "status_buffer_text",
                    # 小 resolver(partial)：descriptors man/woman(person_names)・
                    # status_terms war/peace(war_peace)・npc_traits Mad(title_names)。
                    # 残(old man/young woman/lad/lass・truce/treaty/alliance・
                    # highly aggressive)は ACD 非単独で synthetic/D。
                    "descriptors", "status_terms", "npc_traits")
_AEXE_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "i18n", "_aexe_template")

# v2 localpack（整数 ID・source_id 経路）。公開派生 source_id_map（原文非含）で provider
# surface を整数 ID へ解決して生成する、唯一の Arena 由来 local provider。legacy_id_map 非依存。
_V2_LOCALPACK_NAME = "RTESArenaAssist.localpack"
_SOURCE_ID_MAP_PATH = os.path.join(os.path.dirname(__file__), "i18n", "source_id_map.json")
_BUNDLE_PATH = os.path.join(os.path.dirname(__file__), "i18n", "i18n_bundle.json")

# 辞書（v2 localpack）生成ロジック版。**Assist 本体バージョン・content_version・bundle の
# registry_version と独立**。localpack 生成ロジックが「bundle 不変でも出力を変える」形で変わったら
# 上げる（例: _aexe_template の seed フォールバック化で aexe 表面が解決するようになった = 生成出力が
# 変わる）。起動時に localpack.builder_version < この値なら更新対象（採取なし再写像）。
_V2_BUILDER_VERSION = 2


def v2_localpack_path(user_dir: str) -> str:
    """v2 localpack（RTESArenaAssist.localpack）のパス（build_local_pack の生成先）。"""
    return os.path.join(user_dir, _V2_LOCALPACK_NAME)


# user-env runtime 観測ストア（記録側）。公開物に**含めない**
# user-env 専用ファイル＝整数 ID → 観測 surface（id 確定後の保存先・surface-only bootstrap 不可）。
_USER_OBS_NAME = "live_surface_observations.json"


def user_observations_path(user_dir: str) -> str:
    """user-env runtime 観測ストア（live_surface_observations.json）のパス。"""
    return os.path.join(user_dir, _USER_OBS_NAME)


def load_user_observations(user_dir: str) -> dict[int, str]:
    """user-env 観測ストアを {整数 ID: surface} で読む（不在/破損は空）。"""
    p = user_observations_path(user_dir)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {int(k): v for k, v in raw.items() if isinstance(v, str) and v}
    except (OSError, ValueError):
        return {}


def append_user_observation(user_dir: str, id: int, surface: str) -> bool:
    """user-env 観測ストアへ {整数 ID: surface} を追記保存する（既存 id は更新）。

    **id は呼び側で公開安全 context から確定済**であること（surface-only bootstrap 禁止＝
    ）。ガード（allowlist/未 provision/非 retired）は i18n_helper.register_observation 側。
    """
    if not surface:
        return False
    obs = load_user_observations(user_dir)
    obs[int(id)] = surface
    try:
        os.makedirs(user_dir, exist_ok=True)
        with open(user_observations_path(user_dir), "w", encoding="utf-8") as fh:
            json.dump({str(k): v for k, v in obs.items()}, fh, ensure_ascii=False)
        return True
    except OSError:
        return False


def _loose_names_upper(arena_dir: str) -> set[str]:
    try:
        return {n.upper() for n in os.listdir(arena_dir)
                if os.path.isfile(os.path.join(arena_dir, n))}
    except OSError:
        return set()


def is_valid_arena_dir(arena_dir: str) -> bool:
    """Arena ディレクトリ妥当性（A.EXE か ACD.EXE ＋ GLOBAL.BSA の存在・大小無視）。"""
    if not arena_dir or not os.path.isdir(arena_dir):
        return False
    names = _loose_names_upper(arena_dir)
    has_exe = any(e in names for e in _REQUIRED_ANY_EXE)
    return has_exe and _REQUIRED_BSA in names


# Steam/GOG の定番インストール先（"The Elder Scrolls Arena" フォルダ）。配下の ARENA に
# ACD.EXE/GLOBAL.BSA がある。初回実行ウィザードの自動検出候補に使う。
_STEAM_REL = os.path.join("steamapps", "common", "The Elder Scrolls Arena")
_GOG_REL = "The Elder Scrolls Arena"


def detect_arena_dirs() -> list[str]:
    """インストール済み Arena の ARENA フォルダ候補を妥当性検証して返す（重複なし・先頭優先）。

    走査対象: 各ドライブの Steam ライブラリ（``<drive>:\\Steam`` / ``<drive>:\\SteamLibrary`` /
    ``Program Files (x86)\\Steam``）と GOG 既定。``是 The Elder Scrolls Arena\\ARENA`` を
    ``is_valid_arena_dir`` で確認する。見つからなければ空リスト（ウィザードは手動選択に誘導）。
    """
    import string

    roots: list[str] = []
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    drives = [f"{d}:\\" for d in string.ascii_uppercase
              if os.path.isdir(f"{d}:\\")]
    steam_bases = [os.path.join(pf86, "Steam"), os.path.join(pf, "Steam")]
    for dr in drives:
        steam_bases.append(os.path.join(dr, "Steam"))
        steam_bases.append(os.path.join(dr, "SteamLibrary"))
    for base in steam_bases:
        roots.append(os.path.join(base, _STEAM_REL))
    for dr in drives:
        roots.append(os.path.join(dr, "GOG Games", _GOG_REL))
        roots.append(os.path.join(dr, "GOG", _GOG_REL))

    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        cand = os.path.join(root, "ARENA")
        try:
            key = os.path.normcase(os.path.normpath(cand))
        except (OSError, ValueError):
            continue
        if key in seen:
            continue
        seen.add(key)
        if is_valid_arena_dir(cand):
            found.append(cand)
    return found


def detect_running_arena_dir() -> str | None:
    """起動中の Arena（DOSBox.exe）プロセスから Arena フォルダを推定して返す。

    DOSBox.exe のフルパス（例 ``…\\The Elder Scrolls Arena\\DOSBox-0.74\\DOSBox.exe``）から
    上位フォルダを辿り、``<root>\\ARENA`` 等の妥当な Arena フォルダを探す。プロセスが
    無い・推定不能なら None（呼び出し側は手動選択や「再確認」へ誘導する）。
    """
    try:
        from arena_bridge import ArenaMemoryAnalyzer
    except Exception:  # noqa: BLE001
        return None
    try:
        an = ArenaMemoryAnalyzer()
        exe_path = an.get_image_path()
    except Exception:  # noqa: BLE001
        return None
    if not exe_path or not os.path.isfile(exe_path):
        return None
    # DOSBox.exe のあるフォルダから 1〜2 階層上を探索し、配下/同階層の妥当 ARENA を探す。
    dosbox_dir = os.path.dirname(exe_path)
    bases = [os.path.dirname(dosbox_dir), dosbox_dir,
             os.path.dirname(os.path.dirname(dosbox_dir))]
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        # base 直下が妥当 / base/ARENA が妥当 / base の子で妥当なものを順に。
        if is_valid_arena_dir(base):
            return base
        for sub in ("ARENA", "arena"):
            cand = os.path.join(base, sub)
            if is_valid_arena_dir(cand):
                return cand
        try:
            for name in os.listdir(base):
                cand = os.path.join(base, name)
                if os.path.isdir(cand) and is_valid_arena_dir(cand):
                    return cand
        except OSError:
            pass
    return None


def _sha256_file(path: str) -> str:
    """ファイルの SHA-256（hex）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _arena_asset_hashes(arena_dir: str) -> dict:
    """存在する指紋対象 loose ファイルの SHA-256 を {大文字名: hex} で返す（大小無視）。"""
    out: dict[str, str] = {}
    try:
        real = {n.upper(): n for n in os.listdir(arena_dir)
                if os.path.isfile(os.path.join(arena_dir, n))}
    except OSError:
        return out
    for fn in _FINGERPRINT_FILES:
        rn = real.get(fn)
        if rn:
            try:
                out[fn] = _sha256_file(os.path.join(arena_dir, rn))
            except OSError:
                pass
    return out


def _load_fingerprint_manifest() -> dict:
    """対応指紋 manifest（原文非含・SHA-256 のみ）を読む。無ければ空セット。"""
    txt = _read_owned_text(_FINGERPRINT_MANIFEST_PATH, "arena_fingerprints.json")
    if txt is not None:
        try:
            return json.loads(txt)
        except ValueError:
            pass
    logger.warning("arena_local_data: fingerprint manifest missing/invalid: %s",
                   _FINGERPRINT_MANIFEST_PATH)
    return {"asset_sets": []}


def classify_arena_dir(arena_dir: str, hashes: dict | None = None) -> dict:
    """Arena dir を対応指紋で verified / unknown / invalid に分類する。

    判定は実ファイル SHA-256（EXE 由来 offset は EXE 内容に依存するため）。manifest の資産
    セットの宣言ファイルが**全て一致**したら verified（その set の支援フラグを採用）。必須
    ファイルは在るが一致セットが無ければ unknown。必須ファイル不足/読取不能は invalid。
    Returns: {status, set_id, label, exe_kind, hashes,
              supports_aexe_offsets, supports_akey_acd_offsets}
    """
    base = {"status": "invalid", "set_id": None, "label": None, "exe_kind": None,
            "hashes": {}, "supports_aexe_offsets": False, "supports_akey_acd_offsets": False}
    if not is_valid_arena_dir(arena_dir):
        return base
    h = hashes if hashes is not None else _arena_asset_hashes(arena_dir)
    base["hashes"] = h
    # 必須＝GLOBAL.BSA ＋ いずれかの EXE が読めること。
    if "GLOBAL.BSA" not in h or not any(e in h for e in _REQUIRED_ANY_EXE):
        return base
    for s in _load_fingerprint_manifest().get("asset_sets", []):
        files = s.get("files") or {}
        if files and all(h.get(k) == v for k, v in files.items()):
            return {"status": "verified", "set_id": s.get("id"), "label": s.get("label"),
                    "exe_kind": s.get("exe_kind"), "hashes": h,
                    "supports_aexe_offsets": bool(s.get("supports_aexe_offsets")),
                    "supports_akey_acd_offsets": bool(s.get("supports_akey_acd_offsets"))}
    return {"status": "unknown", "set_id": None, "label": None, "exe_kind": None,
            "hashes": h, "supports_aexe_offsets": False, "supports_akey_acd_offsets": False}


def _current_template_fingerprint(arena_dir: str):
    """Arena dir の TEMPLATE.DAT を VFS で読み (raw, fingerprint) を返す。無ければ (None, None)。"""
    from arena_vfs import Vfs
    import arena_regen
    raw = Vfs(arena_dir).read("TEMPLATE.DAT")
    if raw is None:
        return None, None
    return raw, arena_regen.fingerprint_bytes(raw)


def _load_aexe_templates() -> dict[str, dict]:
    """EXE 由来第1陣の curation テンプレートをディスクから読む（無い分はスキップ）。"""
    out: dict[str, dict] = {}
    for cat in _AEXE_CATEGORIES:
        path = os.path.join(_AEXE_TEMPLATE_DIR, f"{cat}.json")
        txt = _read_owned_text(path, f"i18n/_aexe_template/{cat}.json")
        if txt is not None:
            try:
                out[cat] = json.loads(txt)
                continue
            except ValueError:
                pass
        logger.warning("arena_local_data: aexe template missing/invalid: %s", path)
    return out


# ask_about_menu chrome（見出し/選択肢）の構造位置 → legacy_id 写像（固定テンプレ＝順序不変）。
_ASK_ABOUT_OPT_IDS = ("opt_who_are_you", "opt_where_is", "opt_rumors", "opt_exit")


def _harvest_ask_about_chrome(analyzer) -> dict:
    """anchor+0x8525 の ASK ABOUT 常駐テンプレを採取し chrome を {legacy_id: {original}} で返す。

    制御バイト形式（NN C0 <hk> NN D4 <rest> 00）を既存パーサ `parse_menu` でデコードし、構造位置で
    legacy_id へ写像する。テンプレが ASK ABOUT 状態でない/読めない時は空 dict（採取しない）。
    """
    try:
        import arena_bridge as _ab
        import ask_about_menu_parser as _aamp
        anchor = _ab.find_anchor(analyzer)
        if not anchor:
            return {}
        parsed = _aamp.parse_menu(_ab.read_ask_about_menu(analyzer, anchor))
    except Exception:  # noqa: BLE001 - 採取不能は空（既存 place_* のみ）
        return {}
    title = parsed.get("title")
    if not (isinstance(title, str) and "ASK ABOUT" in title):
        return {}  # ガード: ASK ABOUT テンプレが常駐していない状態では採取しない
    out: dict = {}

    def _put(key: str, surface) -> None:
        if isinstance(surface, str) and surface:
            out[f"ask_about_menu.{key}.0"] = {"original": surface}

    _put("title_ask_about", title)
    opts = parsed.get("options") or []
    for i, key in enumerate(_ASK_ABOUT_OPT_IDS):
        if i < len(opts):
            _put(key, opts[i])
    for sm in parsed.get("sub_menus") or []:
        if "Rumor" in (sm.get("title") or ""):
            _put("title_rumor_type", sm.get("title"))
            sub_opts = sm.get("options") or []
            if sub_opts:
                _put("opt_general", sub_opts[0])
    _put("fallback_no_rumor", parsed.get("fallback_no_rumor"))
    _put("fallback_not_sure", parsed.get("fallback_not_sure"))
    return out


def _harvest_aexe(analyzer, supports: bool = True, progress=None,
                  scan_progress=None, cancel_check=None):
    """起動中メモリから EXE 由来テーブルを採取し (version, {cat: original_json}, tables) を返す。

    tables は採取生テーブル（char_creation.* など chargen_ui 合成に使う）。失敗時 None。
    supports=False（未検証版＝対応指紋不一致）のときは EXE 固定 offset 採取を抑止する。
    progress（callable(done,total)）はカテゴリ構築ごと、scan_progress はメモリテーブル走査
    （最重量フェーズ）ごとに進捗を通知する（停滞回避）。cancel_check が True なら走査を中断する。
    """
    if analyzer is None or not supports:
        return None
    try:
        import arena_aexe
    except ImportError:
        return None
    result = arena_aexe.harvest(analyzer, progress=scan_progress, cancel_check=cancel_check)
    if result is None:
        return None
    version, tables = result
    templates = _load_aexe_templates()
    if not templates:
        return None
    out: dict[str, dict] = {}
    total = len(templates)
    for i, (cat, template) in enumerate(templates.items()):
        try:
            out[cat] = arena_aexe.build_aexe_original_json(template, tables)
        except (KeyError, IndexError) as e:
            logger.warning("arena_local_data: aexe build failed for %s: %s", cat, e)
            return None
        if progress is not None:
            try:
                progress(i + 1, total)
            except Exception:  # noqa: BLE001 - 進捗通知失敗は採取を妨げない
                pass
    return version, out, tables


_AKEY_TEMPLATE_PATH = os.path.join(_AEXE_TEMPLATE_DIR, "akey.json")


def _harvest_akey_ui(analyzer, supports: bool = True) -> dict:
    """A-key UI（A0/A100-A400・純 A.EXE UI）を起動中メモリから採取して npc_dialog エントリへ。

    ACD.EXE 版のみ採取可（A.EXE では空）。失敗時 {}。原文はメモリ由来でコード非埋込。
    supports=False（対応指紋 supports_akey_acd_offsets でない）のときは AKEY_ACD_OFFSETS の
    適用を抑止する（実測 offset は同一 ACD.EXE 指紋にのみ妥当）。
    """
    if analyzer is None or not supports:
        return {}
    try:
        import arena_aexe
        import arena_regen
    except ImportError:
        return {}
    result = arena_aexe.harvest_akey(analyzer)
    if result is None:
        return {}
    _version, raw_map = result
    txt = _read_owned_text(_AKEY_TEMPLATE_PATH, "i18n/_aexe_template/akey.json")
    if txt is None:
        logger.warning("arena_local_data: akey template missing/invalid: %s",
                       _AKEY_TEMPLATE_PATH)
        return {}
    try:
        template = json.loads(txt)
    except ValueError:
        logger.warning("arena_local_data: akey template missing/invalid: %s",
                       _AKEY_TEMPLATE_PATH)
        return {}
    return arena_regen.regenerate_akey_ui(raw_map, template)


def _build_chargen_ui(tables: dict, template_raw: bytes) -> dict:
    """採取テーブル（char_creation.*/classes.*）＋ TEMPLATE.DAT 種族説明から
    _CHARGEN_ UI/結果系（inf_text エントリ）を合成する。失敗時 {}。"""
    import arena_regen
    cc = {k.split(".", 1)[1]: v for k, v in tables.items()
          if k.startswith("char_creation.")}
    class_names = tables.get("classes.names") or []
    pref_attrs = tables.get("classes.preferred_attributes") or []
    if not cc or not class_names:
        return {}
    # TEMPLATE.DAT #1409-1416（標準種族順）の種族説明。
    race_descs: list[str] = []
    ents = {e["key"]: e for e in arena_regen.parse_template_dat_bytes(template_raw)}
    for i in range(8):
        e = ents.get(str(1409 + i))
        vals = e.get("values") if e else None
        race_descs.append(str(vals[0]) if vals else "")
    return arena_regen.regenerate_chargen_ui(cc, class_names, pref_attrs, race_descs)


def load_golden_manifest(path: str | None = None) -> dict | None:
    """公開ゴールデンマニフェスト（原文なし）を読む。無ければ/壊れていれば None。"""
    if path is not None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
    else:
        txt = _read_owned_text(_GOLDEN_MANIFEST_PATH, "arena_golden_manifest.json")
        if txt is None:
            return None
        try:
            data = json.loads(txt)
        except ValueError:
            return None
    if not isinstance(data, dict) or not isinstance(data.get("categories"), dict):
        return None
    return data


def verify_against_golden(local_manifests: dict[str, dict], golden: dict,
                          local_exe_harvest: bool) -> dict:
    """ローカル生成のカテゴリ別 manifest をゴールデンと突合せる（不足検出）。

    各カテゴリで compare_manifests を用い、欠落(missing)/本文ズレ(drift)/余剰(extra) を集計。
    原文は一切扱わず source_id + source_hash のみで判定する。
      - missing = ゴールデンにありローカルに無い（生成が足りない＝原則②違反の疑い）。
      - drift   = 両方にあるが hash 不一致（版差/本文ズレ）。
      - extra   = ローカルにのみ（EXE 由来採取の有無で増減＝警告でなく情報）。
    ゴールデンが EXE 採取込み(exe_harvest=true)でローカルが未採取のときは、欠落が EXE 由来か
    区別できないため missing を情報扱いに格下げする（誤警告回避）。

    Returns {ok, categories:{cat:{missing,drift,extra,...}}, missing, drift, summary,
             soften_missing}。
    """
    import i18n_source_address as sa
    golden_cats = golden.get("categories") or {}
    soften_missing = bool(golden.get("exe_harvest")) and not local_exe_harvest
    per_cat: dict[str, dict] = {}
    total_missing = total_drift = 0
    for cat, gman in golden_cats.items():
        g_entries = (gman or {}).get(sa.MANIFEST_ENTRIES) or {}
        l_entries = (local_manifests.get(cat) or {}).get(sa.MANIFEST_ENTRIES) or {}
        res = sa.compare_manifests(g_entries, l_entries)
        counted_missing = 0 if soften_missing else res["counts"]["missing"]
        per_cat[cat] = {
            "missing": res["counts"]["missing"], "drift": res["counts"]["drift"],
            "extra": res["counts"]["extra"],
            "missing_ids": res["missing"][:20], "drift_ids": res["drift"][:20]}
        total_missing += counted_missing
        total_drift += res["counts"]["drift"]
    ok = (total_missing == 0 and total_drift == 0)
    return {"ok": ok, "categories": per_cat, "missing": total_missing,
            "drift": total_drift, "summary": f"missing={total_missing},drift={total_drift}",
            "soften_missing": soften_missing}


def _run_golden_check(local_manifests: dict[str, dict], asset_set: str | None,
                      exe_harvest: bool) -> str:
    """ローカル manifest 群をゴールデンと突合せ、結果を起動時ログへ残す。

    返り値は pack meta `golden_check` 用の文字列（none/skip/ok/"missing=..,drift=.."）。
    一致は RECOG（既定で見える）、不一致は WARNING。突合せは**起動ごとに 1 回だけ**
    （毎 poll でない）。golden 不在は none、別版 golden は skip。
    """
    golden = load_golden_manifest()
    if not golden:
        return "none"
    if golden.get("asset_set") not in (asset_set, None):
        return "skip"
    gres = verify_against_golden(local_manifests, golden, exe_harvest)
    if gres["ok"]:
        try:
            import assist_log
            assist_log.recog(
                logger, "arena_local_data: ゴールデンマニフェスト突合せ一致 "
                "(%d カテゴリ・%s)", len(gres["categories"]),
                golden.get("asset_set") or "-")
        except Exception:  # noqa: BLE001 - ログ失敗で起動を妨げない
            pass
        return "ok"
    logger.warning(
        "arena_local_data: ゴールデンマニフェスト突合せ不一致 (%s)。欠落/本文ズレの"
        "あるカテゴリ: %s", gres["summary"],
        {c: v for c, v in gres["categories"].items() if v["missing"] or v["drift"]})
    return gres["summary"]


def build_local_pack(arena_dir: str, user_dir: str, analyzer=None,
                     classification: dict | None = None,
                     progress=None, cancel_check=None) -> str | None:
    """Arena dir から provider surface を再生成し v2 localpack を構築する。

    生成先は ``user_dir`` 配下の ``RTESArenaAssist.localpack``（唯一の Arena 由来 local
    provider）。analyzer（ArenaMemoryAnalyzer 互換）を渡すと EXE 由来（A.EXE）カテゴリも
    起動中メモリから採取して収録する。ただし EXE 固定 offset 採取は**対応指紋が verified
    のときだけ**有効化する（classification）。

    progress（callable(fraction: float 0..1, label: str) または None）を渡すと、生成の
    主要段階で進捗を通知する（初回実行ウィザードのプログレスバー用）。

    **原子的書込（クラッシュ安全）**: localpack は ``.tmp`` へ書き、成功後に ``os.replace``
    で原子的に差し替える（`_write_v2_localpack`）。生成途中でクラッシュしても既存の本番
    localpack は無傷（user_dir 内・temp 汚染なし）。

    Returns 版指紋（成功）/ None（TEMPLATE.DAT が読めない等）。
    """
    import arena_regen

    def _p(frac: float, label: str) -> None:
        if progress is not None:
            try:
                progress(frac, label)
            except Exception:  # noqa: BLE001 - 進捗通知失敗は生成を妨げない
                pass

    def _ck() -> None:
        # フェーズ境界でユーザーキャンセルを検査し、クリーンに中断する（プロセス即終了用）。
        if cancel_check is not None and cancel_check():
            from arena_aexe import GenerationCancelled
            raise GenerationCancelled()

    _ck()
    _p(0.02, "Arena データを確認中…")
    raw, fp = _current_template_fingerprint(arena_dir)
    if raw is None:
        logger.warning("arena_local_data: TEMPLATE.DAT not found under %s", arena_dir)
        return None
    # 対象版判定（対応指紋 SHA-256）。EXE 固定 offset 採取の可否を決める。
    cls = classification if classification is not None else classify_arena_dir(arena_dir)
    exe_ok = cls.get("status") == "verified" and cls.get("supports_aexe_offsets")
    akey_ok = cls.get("status") == "verified" and cls.get("supports_akey_acd_offsets")
    if cls.get("status") != "verified":
        logger.warning(
            "arena_local_data: 未検証の Arena データです（status=%s・対応指紋セット不一致）。"
            "一部 EXE 由来文字列（A.EXE テーブル / A-key UI）は生成されません。"
            "DAT/TEMPLATE/VFS 由来の再生成は継続します。", cls.get("status"))
    # 現フェーズの TEMPLATE.DAT 由来カテゴリ（TEMPLATE.DAT 出典）。
    # npc_dialog は TEMPLATE.DAT 分のみ（A-key=A.EXE 由来は EXE 由来カテゴリ・パックに含めない）。
    _p(0.06, "テキストデータを再生成中…")
    be = arena_regen.regenerate_building_entry_bytes(raw)
    npcd = arena_regen.regenerate_npc_dialog_bytes(raw)
    # inf_text = 各 INF ファイルの @TEXT（VFS で全 INF を読む）。_CHARGEN_ UI/結果系(EXE 由来)/
    # TEMPLATE_DAT_(別経路) は含めない。
    _ck()
    _p(0.12, "INF テキストを読込中…")
    inft = arena_regen.regenerate_inf_text_bytes(_read_inf_files(
        arena_dir,
        progress=lambda done, total: _p(
            0.12 + 0.10 * (done / max(1, total)), "INF テキストを読込中…")))
    # _CHARGEN_ キャラ作成質問本文（QUESTION.TXT 由来）を inf_text へマージ（同一カテゴリ）。
    from arena_vfs import Vfs
    question_raw = Vfs(arena_dir).read("QUESTION.TXT")
    chargen_q = (arena_regen.regenerate_chargen_questions(question_raw)
                 if question_raw is not None else {})
    inft.update(chargen_q)
    # A-key A500台（宿屋の部屋提示）= TAVERN.DAT（loose・loadTradeText）を npc_dialog へマージ。
    # 他の A-key 帯（A.EXE 由来）は EXE 由来カテゴリ。
    tavern_raw = Vfs(arena_dir).read("TAVERN.DAT")
    atrade = (arena_regen.regenerate_atrade_tavern(tavern_raw)
              if tavern_raw is not None else {})
    npcd.update(atrade)
    # A-key A600台（店/ギルド値切り・A601-A618）= EQUIP/SELLING/MUGUILD.DAT（loose・loadTradeText）。
    # A600.0/.1・A619.0 は A.EXE UI（akey UI 経路）で別途。
    _vfs = Vfs(arena_dir)
    eq, se, mu = (_vfs.read("EQUIP.DAT"), _vfs.read("SELLING.DAT"), _vfs.read("MUGUILD.DAT"))
    atrade_shop = (arena_regen.regenerate_atrade_shops(eq, se, mu)
                   if (eq and se and mu) else {})
    npcd.update(atrade_shop)
    # A-key A180台（修理屋の値切り A182-A188）= TEMPLATE.DAT #1417/#1418/#1424-1428（offline）。
    akey_repair = arena_regen.regenerate_akey_repair(raw)
    npcd.update(akey_repair)
    # npc_name_chunks = NAMECHNK.DAT の名前部品（VFS で読む）。literals は curation で非収録。
    # world_map（CITYDATA.NN 由来・翻訳外 Arena 資産）。CITYDATA.65 を
    # arena_dir 直下(VFS) → arena_dir/save/ の順で解決し、見つかれば world_map を生成する。
    _p(0.24, "地名・名前データを処理中…")
    citydata_raw = _read_citydata(arena_dir)
    world_map_json = None
    location_orig = None
    if citydata_raw:
        try:
            from services import citydata_reader
            world_map_json = citydata_reader.build_world_map(citydata_raw)
            # location カテゴリの CITYDATA 由来分（280件相当・地名）。建物種別/方角/lore 等の
            # 非 CITYDATA 由来（59件）は別出典（調査未了）で生成しない。
            location_orig = citydata_reader.build_location_originals(citydata_raw)
        except Exception as e:  # noqa: BLE001 - 生成失敗で起動を妨げない
            logger.warning("arena_local_data: world_map/location 生成失敗: %s", e)
    namechnk_raw = Vfs(arena_dir).read("NAMECHNK.DAT")
    nnc = (arena_regen.regenerate_npc_name_chunks_bytes(namechnk_raw)
           if namechnk_raw is not None else {})
    # EXE 由来（A.EXE）= 起動中メモリから採取（**verified かつ supports_aexe_offsets のときだけ**）。
    # 最重量フェーズ。テーブル走査 [0.30,0.50]＋カテゴリ構築 [0.50,0.62] を件数で連続更新する
    # （メモリ走査が無計装で 30% に固まっていた停滞を解消）。cancel_check で即中断可。
    _ck()
    _p(0.30, "メモリからデータを採取中…")
    aexe = _harvest_aexe(
        analyzer, exe_ok, cancel_check=cancel_check,
        scan_progress=lambda done, total: _p(
            0.30 + 0.20 * (done / max(1, total)), "メモリからデータを採取中…"),
        progress=lambda done, total: _p(
            0.50 + 0.12 * (done / max(1, total)), "メモリからデータを採取中…"))
    aexe_version = aexe[0] if aexe else None
    aexe_cats = aexe[1] if aexe else {}
    # ask_about_menu の見出し/選択肢（chrome）= anchor+0x8525 の固定常駐テンプレから採取。
    # 項目は Arena 制御バイト形式（NN C0 <hk> NN D4 <rest> 00）で格納されるため、
    # 生文字列照合では見つからず、既存パーサ（ask_about_menu_parser.parse_menu）でデコードして
    # legacy_id へ写像する。place_*（目的地表・A.EXE 0x43FD3）は別経路で採取済。analyzer 必須。
    if analyzer is not None and exe_ok:
        try:
            chrome = _harvest_ask_about_chrome(analyzer)
            if chrome:
                aexe_cats.setdefault("ask_about_menu", {}).update(chrome)
        except Exception as e:  # noqa: BLE001 - chrome 採取失敗は他カテゴリ採取を妨げない
            logger.warning("arena_local_data: ask_about chrome 採取失敗: %s", e)
    # city_generation（[CityGeneration] 構造・ACD.EXE メモリ採取）。
    # 開発時 JSON は A.EXE Floppy offset 由来だが、データは版非依存（Steam ACD 採取で一致確認）。
    # analyzer かつ verified（exe_ok）時のみ採取（EXE 由来カテゴリと同条件）。
    city_gen_json = None
    if analyzer is not None and exe_ok:
        _p(0.62, "メモリからデータを採取中…")
        try:
            import arena_aexe as _ax
            cg = _ax.harvest_city_generation(analyzer)
            if cg:
                city_gen_json = {
                    "source": "ACD.EXE (Steam・memory harvest)",
                    "data": cg[1],
                }
        except Exception as e:  # noqa: BLE001 - 採取失敗で起動を妨げない
            logger.warning("arena_local_data: city_generation 採取失敗: %s", e)
    # _CHARGEN_ UI/結果系（A.EXE CharacterCreation＋TEMPLATE.DAT 種族説明）を inf_text へマージ。
    # %s 実行時置換を含む単一(NAME/PROVINCE/ConfirmRace/ConfirmedRace1)は対象外（disk 維持）。
    chargen_ui = _build_chargen_ui(aexe[2], raw) if aexe else {}
    inft.update(chargen_ui)
    # A-key UI（A0/A100-A400・純 A.EXE UI/ポップアップ）を起動中メモリ採取で npc_dialog へマージ。
    # **verified かつ supports_akey_acd_offsets のときだけ**（実測 offset は同一 ACD.EXE 指紋に限り妥当）。
    _p(0.66, "メモリからデータを採取中…")
    akey_ui = _harvest_akey_ui(analyzer, akey_ok)
    npcd.update(akey_ui)
    exe_harvested = bool(aexe_cats) or bool(akey_ui)
    content_version = _AEXE_CONTENT_VERSION if aexe_cats else _BASE_CONTENT_VERSION
    # カテゴリ別 manifest（原文なし・id+hash）を先に作り、ゴールデン突合せに使う。
    m_be = arena_regen.build_manifest(be, fp)
    m_npcd = arena_regen.build_npc_dialog_manifest(npcd, fp)
    m_inft = arena_regen.build_inf_text_manifest(inft, fp)
    m_nnc = arena_regen.build_npc_name_chunks_manifest(nnc, fp) if nnc else None
    local_manifests = {
        arena_regen.CATEGORY: m_be,
        arena_regen.NPC_DIALOG_CATEGORY: m_npcd,
        arena_regen.INF_TEXT_CATEGORY: m_inft,
    }
    if m_nnc:
        local_manifests[arena_regen.NPC_NAME_CHUNKS_CATEGORY] = m_nnc
    # EXE 由来（A.EXE）カテゴリの manifest（採取できたカテゴリのみ・golden 突合せ対象）。
    aexe_manifests = {cat: arena_regen.build_aexe_manifest(cat, oj, fp)
                      for cat, oj in aexe_cats.items()}
    local_manifests.update(aexe_manifests)
    # 翻訳外/CITYDATA 由来カテゴリの manifest（world_map・location）。
    m_world_map = None
    m_location = None
    if citydata_raw:
        from services import citydata_reader
        m_world_map = citydata_reader.build_world_map_manifest(citydata_raw, fp)
        local_manifests[citydata_reader.WORLD_MAP_CATEGORY] = m_world_map
        if location_orig:
            m_location = citydata_reader.build_location_manifest(location_orig, fp)
            local_manifests[citydata_reader.LOCATION_CATEGORY] = m_location
    # city_generation（ACD 採取・analyzer 時のみ）の manifest（構造）。
    m_city_gen = None
    if city_gen_json is not None:
        from services import citydata_reader
        m_city_gen = citydata_reader.build_city_generation_manifest(
            city_gen_json["data"], fp)
        local_manifests[citydata_reader.CITY_GENERATION_CATEGORY] = m_city_gen
    # ゴールデンマニフェスト（公開物）との突合せで不足検出を仕組みで担保。golden が無ければ
    # no-op（"none"）。資産セット一致時のみ突合せる（別版 golden は skip）。
    _ck()
    _p(0.70, "整合性を検証中…")
    golden_check = _run_golden_check(local_manifests, cls.get("set_id"), exe_harvested)

    def _J(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2)

    _asset_hashes_json = json.dumps(cls.get("hashes") or {}, sort_keys=True)
    _asset_set_id = cls.get("set_id") or "unknown"
    logger.info("arena_local_data: built local data (fp=%s, building_entry=%d, "
                "npc_dialog=%d[atrade=%d,atradeshop=%d,akeyrepair=%d,akeyui=%d], "
                "inf_text=%d[chargen_q=%d,chargen_ui=%d], npc_name_chunks=%d, aexe=%s[%s], "
                "golden=%s)",
                fp, len(be), len(npcd), len(atrade), len(atrade_shop),
                len(akey_repair), len(akey_ui), len(inft), len(chargen_q), len(chargen_ui),
                len(nnc), len(aexe_cats), aexe_version or "-", golden_check)
    # v2 localpack を生成する（唯一の Arena 由来 local provider）。source_id を持つ provider
    # （building_entry/npc_dialog/inf_text/npc_name_chunks/location）の surface を集約。
    surface_by_sid = _collect_surface_by_source_id(be, npcd, inft, nnc, location_orig)
    # EXE 由来 ACD テーブル（calendar/classes/races 等）は entry に source_id を持たないため、
    # source_id_map と同一導出（category_source_id.aexe_source_id・_aexe_template のみ参照＝公開安全）で
    # surface を加える。共有テーブル（spells/equipment_suffixes/item_enchantments）は同 source_id を
    # 共有し localpack 側で fan-out される。
    surface_by_sid.update(_collect_aexe_surfaces(aexe_cats))
    # mages 標準呪文名（SPELLSG.65 由来）の surface を加える。
    # save slot 非依存の固定マスタを読む（A.EXE harvest 外＝analyzer 不要）。
    surface_by_sid.update(_collect_spellsg65_surfaces(arena_dir))
    # public_builtin_literal（Yes/No 等）を注入（Arena 資産非依存の generic literal）。
    try:
        import category_source_id as _csid
        surface_by_sid.update(_csid.public_builtin_surfaces())
        # mages 合成効果名（FULL）を spell effect 構造から決定論再構成。
        surface_by_sid.update(_csid.spell_effect_surfaces())
    except ImportError:
        pass
    # item_materials の Leather/Chain/Plate = composite armor name
    # table 由来 prefix を A.EXE harvest（aexe[2]=tables）から導出（verified+analyzer 時のみ）。
    if aexe:
        surface_by_sid.update(_collect_armor_prefix_surfaces(aexe[2]))
        # mages 魔法アイテム名 = item+enchantment を harvest table から合成。
        try:
            import category_source_id as _csid2
            surface_by_sid.update(_csid2.magic_item_surfaces(aexe[2]))
            # 素材+装身具名（Mithril Belt 等）も harvest table から合成。
            surface_by_sid.update(_csid2.material_item_surfaces(aexe[2]))
        except ImportError:
            pass
    # inf_text consumer rich メタ（user-env 限定・公開非含）を localpack へ載せる。
    inf_rich = _collect_inf_text_rich(inft)
    # 翻訳外 Arena 生成資産（world_map/city_generation）も v2 localpack の generated_assets へ
    # 収録する（provider が localpack から読む唯一入口になる）。
    gen_assets: dict[str, bytes] = {}
    if world_map_json is not None:
        gen_assets["world_map.json"] = _J(world_map_json).encode("utf-8")
    if city_gen_json is not None:
        gen_assets["city_generation.json"] = _J(city_gen_json).encode("utf-8")
    _p(0.98, "データパックを書込中…")
    _write_v2_localpack(v2_localpack_path(user_dir), surface_by_sid, fp, inf_rich,
                        generated_assets=gen_assets or None,
                        content_version=content_version,
                        asset_set_id=_asset_set_id,
                        asset_hashes=_asset_hashes_json,
                        exe_harvested=exe_harvested)
    _p(1.0, "完了")
    return fp


def _read_spellsg65(arena_dir: str) -> bytes | None:
    """SPELLSG.65（標準呪文マスタ）を解決して読む。

    user-env 所在差を吸収: arena_dir 直下（VFS・loose/BSA）→ arena_dir/save/SPELLSG.65 →
    arena_dir/save/Spellsg.65（開発時の loose 配置）。無ければ None。
    """
    from arena_vfs import Vfs
    raw = Vfs(arena_dir).read("SPELLSG.65")
    if raw:
        return raw
    for cand in (os.path.join(arena_dir, "save", "SPELLSG.65"),
                 os.path.join(arena_dir, "save", "Spellsg.65")):
        if os.path.isfile(cand):
            try:
                with open(cand, "rb") as f:
                    return f.read()
            except OSError:
                return None
    return None


def _collect_spellsg65_surfaces(arena_dir: str) -> dict[str, str]:
    """SPELLSG.65 標準呪文名の {source_id: surface} を集約する。

    `SpellData`（85 byte・name offset 0x34）の各 index → `spellsg65:standard:<index>`。
    source_id は `i18n_source_address.spellsg65_id` で導出（bundle/source_id_map と一致・
    原文非含）。localpack 側で source_id_map に在る index のみ採用される（fan-out）。
    """
    raw = _read_spellsg65(arena_dir)
    if not raw:
        return {}
    import i18n_source_address as addr
    _SIZE, _OFF, _LEN = 85, 0x34, 33
    out: dict[str, str] = {}
    for i in range(len(raw) // _SIZE):
        base = i * _SIZE
        nb = raw[base + _OFF: base + _OFF + _LEN]
        name = nb.split(b"\x00")[0].decode("ascii", errors="replace").strip()
        if name:
            out[addr.spellsg65_id(i)] = name
    return out


def _collect_armor_prefix_surfaces(tables: dict) -> dict[str, str]:
    """composite armor name table 由来の Leather/Chain/Plate prefix を導出。

    A.EXE harvest の `equipment.{leather,chain,plate}_armor_names` と base `equipment.armor_names`
    の差分（`category_source_id.derive_armor_prefix`）で prefix を作り {source_id: surface} を返す。
    `MaterialNames` とは別系統。tables が無い/未採取時は空。
    """
    out: dict[str, str] = {}
    if not tables:
        return out
    try:
        import category_source_id as csid
    except ImportError:
        return out
    base = tables.get("equipment.armor_names")
    for material in ("leather", "chain", "plate"):
        comp = tables.get(f"equipment.{material}_armor_names")
        prefix = csid.derive_armor_prefix(material, comp, base)
        if prefix:
            import i18n_source_address as addr
            out[addr.armor_prefix_id(material)] = prefix
    return out


def _collect_aexe_surfaces(aexe_cats: dict) -> dict[str, str]:
    """EXE 由来 ACD カテゴリの {source_id: surface} を集約する（source_id_map と同一導出）。

    aexe_cats = {category: {app_id: {original, ...}}}（arena_aexe.build_aexe_original_json 由来・
    entry は source_id 非保持）。source_id は category_source_id.aexe_source_id で導出する
    （`aexe:<group>:<table>:<index>`＝bundle/source_id_map と一致・原文非含）。
    """
    out: dict[str, str] = {}
    if not aexe_cats:
        return out
    try:
        import category_source_id as csid
    except ImportError:
        return out
    for cat, original_json in aexe_cats.items():
        if not isinstance(original_json, dict):
            continue
        for legacy_id, entry in original_json.items():
            if not isinstance(entry, dict):
                continue
            sid = csid.aexe_source_id(cat, legacy_id)
            surf = entry.get("original")
            if sid and surf:
                out[sid] = surf
    return out


def _collect_surface_by_source_id(*entry_dicts) -> dict[str, str]:
    """provider 生成 dict 群から {source_id: surface} を集約する（source_id を持つ entry のみ）。

    住所キーは provider により "source_id"（regenerate_*）または "src"（citydata location）。
    同一 source_id が複数 provider で同 surface（共有テーブル/文流用）の場合は後勝ちで同値。
    """
    out: dict[str, str] = {}
    for d in entry_dicts:
        if not isinstance(d, dict):
            continue
        for entry in d.values():
            if not isinstance(entry, dict):
                continue
            sid = entry.get("source_id") or entry.get("src")
            surf = entry.get("original")
            if sid and surf:
                out[sid] = surf
    return out


# inf_text consumer が読む rich メタ（_index entry の構造キー＋表示変種）。type は bundle kind
# から解決するため carry しない。text は v1 entry に存在した時のみ carry（presence を保つ）。
_INF_RICH_FIELDS = ("inf", "idx", "text", "text_panel", "text_display", "question")


def _collect_inf_text_rich(inft: dict) -> dict[str, dict]:
    """inf_text provider dict から {source_id: rich_meta} を集約する（_index entry のみ）。

    consumer 移行: (inf,idx) lookup・表示変種・riddle 候補本文は
    source_id＋単一 surface から導出できないため localpack へ carry（user-env 限定・公開非含）。
    inf/idx を持つ entry（_index 対象）かつ source_id 付きのみ収録。
    """
    out: dict[str, dict] = {}
    for entry in inft.values():
        if not isinstance(entry, dict):
            continue
        sid = entry.get("source_id")
        if not sid or entry.get("inf") is None or entry.get("idx") is None:
            continue
        out[sid] = {f: entry[f] for f in _INF_RICH_FIELDS if f in entry}
    return out


def _write_v2_localpack(out_path: str, surface_by_source_id: dict[str, str],
                        fp: str, rich_by_source_id: dict[str, dict] | None = None,
                        generated_assets: dict[str, bytes] | None = None,
                        content_version: str | None = None,
                        asset_set_id: str | None = None,
                        asset_hashes: str | None = None,
                        exe_harvested: bool | None = None) -> None:
    """v2 localpack（RTESArenaAssist.localpack）を ``out_path`` へ生成する（guarded・原子的）。

    公開派生 source_id_map で source_id→整数 ID を解決（legacy_id_map 非依存）。spell_effect は
    bundle の effect 構造から構造生成で追加。生成失敗は起動を妨げない。
    """
    try:
        import localpack_builder
        # 公開 frozen では _internal/i18n を撤去済のため disk 直読みは失敗する。
        # disk 優先＋seed フォールバック（_read_owned_text）で Assist 所有データを取得する。
        smap_txt = _read_owned_text(_SOURCE_ID_MAP_PATH, "i18n/source_id_map.json")
        bundle_txt = _read_owned_text(_BUNDLE_PATH, "i18n/i18n_bundle.json")
        if smap_txt is None or bundle_txt is None:
            raise FileNotFoundError("source_id_map.json/i18n_bundle.json (disk/seed 共に不在)")
        smap_obj = json.loads(smap_txt)
        bundle = json.loads(bundle_txt)
        smap = smap_obj.get("map", {})
        registry_hash = bundle.get("registry_hash", "")
        spell_effect_entries: list = []
        for cat in bundle.get("categories", []):
            if cat.get("category") == "spell_effect":
                spell_effect_entries = cat.get("entries", [])
                break
        # 原子的書込: .tmp へ書き成功後に os.replace（中途クラッシュで本番 localpack を壊さない）。
        tmp_out = out_path + ".tmp"
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        summary = localpack_builder.write_localpack_by_source_id(
            tmp_out, smap, surface_by_source_id,
            registry_hash=registry_hash,
            spell_effect_entries=spell_effect_entries,
            rich_by_source_id=rich_by_source_id,
            arena_fingerprint=fp,
            generated_assets=generated_assets,
            provider="arena_local_data")
        # 辞書の版を刻印（起動時の更新判定に使う・本体/pak バージョンと独立）。
        # registry_version=辞書データ版(bundle由来・公開リリースの人向け辞書版)／builder_version=生成
        # ロジック版。registry_hash は build_localpack が既に記録済み（開発中の自動検出に使う）。
        try:
            from arena_pack import ArenaPack
            import i18n_localpack as _ilp
            with ArenaPack.open(tmp_out) as _lpk:
                _lpk.set_meta(_ilp.META_REGISTRY_VERSION,
                              str(int(bundle.get("registry_version", 0) or 0)))
                _lpk.set_meta(_ilp.META_BUILDER_VERSION, str(_V2_BUILDER_VERSION))
                # staleness 判定メタ（公開 v2 単独動作で pak を介さず再生成要否を判定するため）:
                # content_version / 対象版資産セット / 資産ハッシュ / EXE 採取有無。
                if content_version is not None:
                    _lpk.set_meta(_META_CONTENT_VERSION, content_version)
                if asset_set_id is not None:
                    _lpk.set_meta(_META_ASSET_SET, asset_set_id)
                if asset_hashes is not None:
                    _lpk.set_meta(_META_ASSET_HASHES, asset_hashes)
                if exe_harvested is not None:
                    _lpk.set_meta(_META_EXE_HARVEST, "1" if exe_harvested else "0")
        except Exception:  # noqa: BLE001 - 刻印失敗でも localpack 自体は有効
            pass
        os.replace(tmp_out, out_path)
        # 入力 source 群の内訳（aexe/spellsg65 等の取りこぼし検知用・イベント駆動の単発）。
        _grp: dict = {}
        for _sid in surface_by_source_id:
            _key = ("aexe:" + _sid.split(":", 2)[1]) if _sid.startswith("aexe:") \
                else _sid.split(":", 1)[0]
            _grp[_key] = _grp.get(_key, 0) + 1
        logger.info(
            "arena_local_data: built v2 localpack %s (originals=%d, source_ids=%d, warnings=%d, "
            "registry_version=%s, builder_version=%d, groups=%s)",
            out_path, summary.get("originals", 0), len(surface_by_source_id),
            len(summary.get("warnings", [])),
            bundle.get("registry_version"), _V2_BUILDER_VERSION, _grp)
    except Exception as e:  # noqa: BLE001 - v2 生成失敗は起動を妨げない
        logger.warning("arena_local_data: v2 localpack 生成失敗: %s", e)


def rebuild_v2_localpack_standalone(user_dir: str) -> bool:
    """既存 localpack 内の再写像キャッシュから辞書を作り直す（採取なし・進捗バー不要）。

    localpack に保存済みの `v2_surfaces`（source_id→surface）／`v2_rich`／`generated_assets`
    を入力に、現在の bundle/source_id_map で再写像する。辞書バージョン更新（builder/registry
    変化）時に呼ぶ。成功で True。
    """
    lp_path = v2_localpack_path(user_dir)
    if not os.path.isfile(lp_path):
        return False
    try:
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
    except Exception as e:  # noqa: BLE001 - 読込失敗は更新せず継続（既存辞書のまま）
        logger.warning("arena_local_data: localpack 再写像の読込に失敗: %s", e)
        return False
    surface = dict(lp.v2_surfaces)
    if not surface:
        # 旧 localpack（キャッシュ未保存）は単独再写像不可＝heavy regen を要する（degraded）。
        logger.info("arena_local_data: localpack に再写像キャッシュが無い（heavy regen が必要）")
        return False
    rich = dict(lp.v2_rich) or None
    gen_assets = dict(lp.generated_assets) or None
    _write_v2_localpack(lp_path, surface, lp.arena_fingerprint, rich,
                        generated_assets=gen_assets)
    return True


def v2_localpack_update_status(user_dir: str) -> dict | None:
    """辞書(v2 localpack)の更新要否を判定する（**裏で再写像しない**・判定のみ）。

    呼び側（起動フロー）が本体表示前にこの結果でダイアログを出し、ユーザーが選んでから
    `rebuild_v2_localpack_standalone` を実行する（裏で自動更新せず明示確認後に実行）。

    判定軸:
      - dev（`version.__dev__=True`）: localpack.registry_hash ≠ bundle.registry_hash
        （= 辞書の写像構造が変わった・開発中の自動検出）または builder 不一致。
      - release（False）: localpack.registry_version < bundle.registry_version
        （= 公式辞書版が上がった）または builder 不一致。
    Returns: 更新不要/判定不能なら None。要更新なら
      {"needed": True, "axis": "registry"|"builder", "from": int, "to": int, "is_dev": bool}。
    """
    # 判定は localpack 基準（唯一の Arena 由来 local provider）。
    lp_path = v2_localpack_path(user_dir)
    if not os.path.isfile(lp_path):
        return None  # localpack 未生成（初回）。初回生成は wizard/first-run の責務。
    try:
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
    except Exception:  # noqa: BLE001 - 読めない localpack は更新対象
        return {"needed": True, "axis": "unreadable", "from": 0, "to": _V2_BUILDER_VERSION,
                "is_dev": _is_dev_build()}
    bundle = _load_owned_bundle()
    if bundle is None:
        return None  # bundle が読めない（seed/disk 双方不在）＝判定不能・現状維持
    # builder（生成ロジック）軸: dev/release 共通。
    if lp.builder_version < _V2_BUILDER_VERSION:
        return {"needed": True, "axis": "builder", "from": lp.builder_version,
                "to": _V2_BUILDER_VERSION, "is_dev": _is_dev_build()}
    # 辞書データ軸: dev=hash 自動／release=registry_version。
    if _is_dev_build():
        if lp.registry_hash != str(bundle.get("registry_hash", "")):
            return {"needed": True, "axis": "registry", "from": 0, "to": 0, "is_dev": True}
    else:
        bv = int(bundle.get("registry_version", 0) or 0)
        if lp.registry_version < bv:
            return {"needed": True, "axis": "registry", "from": lp.registry_version,
                    "to": bv, "is_dev": False}
    return None


def _is_dev_build() -> bool:
    try:
        import version
        return bool(getattr(version, "__dev__", True))
    except Exception:  # noqa: BLE001 - 判定不能時は dev 扱い（安全側=自動検出寄り）
        return True


def _load_owned_bundle() -> dict | None:
    txt = _read_owned_text(_BUNDLE_PATH, "i18n/i18n_bundle.json")
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except (ValueError, TypeError):
        return None


def _read_citydata(arena_dir: str) -> bytes | None:
    """CITYDATA.65（新規キャラ用テンプレート）を解決して読む。

    user-env での所在差を候補解決で吸収する: arena_dir 直下（VFS・loose/BSA）→
    arena_dir/save/CITYDATA.65（開発時の loose 配置）。どちらも無ければ None。
    """
    from arena_vfs import Vfs
    raw = Vfs(arena_dir).read("CITYDATA.65")
    if raw:
        return raw
    cand = os.path.join(arena_dir, "save", "CITYDATA.65")
    if os.path.isfile(cand):
        try:
            with open(cand, "rb") as f:
                return f.read()
        except OSError:
            return None
    return None


def _read_inf_files(arena_dir: str, progress=None) -> dict[str, bytes]:
    """Arena dir の VFS から全 INF ファイルを {大文字名: 平文バイト列} で読む。

    GLOBAL.BSA 内の INF は XOR 暗号化されているため `read_inf` で復号して返す
    （loose の INF は平文のまま）。これで @TEXT を持つ全 INF が再構築対象になる。
    progress（callable(done,total)）を渡すと復号ごとに進捗を通知する（停滞回避）。
    """
    from arena_vfs import Vfs
    vfs = Vfs(arena_dir)
    inf_names = [n for n in vfs.names() if n.upper().endswith(".INF")]
    total = len(inf_names)
    out: dict[str, bytes] = {}
    for i, name in enumerate(inf_names):
        data = vfs.read_inf(name)
        if data is not None:
            out[name.upper()] = data
        if progress is not None:
            try:
                progress(i + 1, total)
            except Exception:  # noqa: BLE001 - 進捗通知失敗は読込を妨げない
                pass
    return out


def v2_localpack_needs_regen(arena_dir: str, user_dir: str, analyzer_available: bool,
                             classification: dict | None = None) -> bool:
    """localpack が重い再生成（EXE 由来採取込み）を要するかを判定する（判定のみ・裏で再生成しない）。

    staleness メタ（arena_fingerprint / 資産ハッシュ / content_version）を localpack から
    読む。要再生成なら本体表示前にダイアログでユーザーに選ばせる。
    """
    try:
        raw, fp = _current_template_fingerprint(arena_dir)
        if raw is None:
            return False
        cls = classification if classification is not None else classify_arena_dir(arena_dir)
        cur_hashes = json.dumps(cls.get("hashes") or {}, sort_keys=True)
        lp_path = v2_localpack_path(user_dir)
        if not os.path.isfile(lp_path):
            return False  # localpack 無し＝初回（wizard/first-run の責務・ここでは判定しない）
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
        meta = lp.meta
        if meta.get(_ilp.META_ARENA_FINGERPRINT) != fp:
            return True  # 対象版（TEMPLATE.DAT 指紋）が変わった
        if meta.get(_META_ASSET_HASHES) != cur_hashes:
            return True  # EXE/BSA 等の資産が変わった
        cv = meta.get(_META_CONTENT_VERSION)
        if cv == _AEXE_CONTENT_VERSION:
            return False  # EXE 由来込み最新
        if cv == _BASE_CONTENT_VERSION and not analyzer_available:
            return False  # 採取不可で妥協
        return True  # 旧/未記録 content_version＝再生成が要る
    except Exception:  # noqa: BLE001 - 読めない＝再生成対象
        return True


__all__ = [
    "v2_localpack_path", "is_valid_arena_dir", "detect_arena_dirs",
    "detect_running_arena_dir", "classify_arena_dir", "build_local_pack",
    "v2_localpack_needs_regen", "rebuild_v2_localpack_standalone",
    "v2_localpack_update_status",
    "load_golden_manifest", "verify_against_golden",
]
