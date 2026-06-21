from __future__ import annotations

import hashlib
import json
import logging
import os

logger = logging.getLogger("RTESArenaAssist")


def _read_owned_text(disk_path: str, rel: str) -> "str | None":
    try:
        with open(disk_path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    try:
        import app_resources
        return app_resources.read_text(rel)
    except Exception:  # noqa: BLE001
        return None


_REQUIRED_ANY_EXE = ("A.EXE", "ACD.EXE")
_REQUIRED_BSA = "GLOBAL.BSA"

_FINGERPRINT_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "arena_fingerprints.json")
_FINGERPRINT_FILES = ("ACD.EXE", "A.EXE", "GLOBAL.BSA")
_META_ASSET_SET = "arena_asset_set"
_META_ASSET_HASHES = "arena_asset_hashes"
_META_EXE_HARVEST = "exe_harvest_enabled"

_GOLDEN_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "arena_golden_manifest.json")
GOLDEN_VERSION = 1

_BASE_CONTENT_VERSION = "be+npcd+atrade+atradeshop+akeyrepair+inf+nnc+chrgnq2+wmap+loc/10"
_AEXE_CONTENT_VERSION = "be+npcd+atrade+atradeshop+akeyrepair+inf+nnc+chrgnq2+aexe4+chargenui+akeyui2+aexeman+wmap+chgnprov+loc+citygen+itemmat+monsters+partial2+items+reclass+srcback27+v2pak28+askchrome29+keymat30+citygennames31/31"
_META_CONTENT_VERSION = "content_version"

_AEXE_CATEGORIES = ("races", "calendar", "titles", "location_types",
                    "classes", "protect_locations", "spells",
                    "item_enchantments", "equipment_suffixes",
                    "chargen_provinces",
                    "item_materials",
                    "monsters",
                    "equipment", "character", "mages", "dungeon",
                    "items",
                    "settlement_types", "chargen_race_descriptions",
                    "pronouns", "relations", "ask_about_menu",
                    "status_buffer_text",
                    "descriptors", "status_terms", "npc_traits")
_AEXE_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "i18n", "_aexe_template")

_V2_LOCALPACK_NAME = "RTESArenaAssist.localpack"
_SOURCE_ID_MAP_PATH = os.path.join(os.path.dirname(__file__), "i18n", "source_id_map.json")
_BUNDLE_PATH = os.path.join(os.path.dirname(__file__), "i18n", "i18n_bundle.json")

_V2_BUILDER_VERSION = 2


def v2_localpack_path(user_dir: str) -> str:
    return os.path.join(user_dir, _V2_LOCALPACK_NAME)


_USER_OBS_NAME = "live_surface_observations.json"


def user_observations_path(user_dir: str) -> str:
    return os.path.join(user_dir, _USER_OBS_NAME)


def load_user_observations(user_dir: str) -> dict[int, str]:
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
    if not arena_dir or not os.path.isdir(arena_dir):
        return False
    names = _loose_names_upper(arena_dir)
    has_exe = any(e in names for e in _REQUIRED_ANY_EXE)
    return has_exe and _REQUIRED_BSA in names


_STEAM_REL = os.path.join("steamapps", "common", "The Elder Scrolls Arena")
_GOG_REL = "The Elder Scrolls Arena"


def detect_arena_dirs() -> list[str]:
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
    dosbox_dir = os.path.dirname(exe_path)
    bases = [os.path.dirname(dosbox_dir), dosbox_dir,
             os.path.dirname(os.path.dirname(dosbox_dir))]
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
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
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _arena_asset_hashes(arena_dir: str) -> dict:
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
    base = {"status": "invalid", "set_id": None, "label": None, "exe_kind": None,
            "hashes": {}, "supports_aexe_offsets": False, "supports_akey_acd_offsets": False}
    if not is_valid_arena_dir(arena_dir):
        return base
    h = hashes if hashes is not None else _arena_asset_hashes(arena_dir)
    base["hashes"] = h
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
    from arena_vfs import Vfs
    import arena_regen
    raw = Vfs(arena_dir).read("TEMPLATE.DAT")
    if raw is None:
        return None, None
    return raw, arena_regen.fingerprint_bytes(raw)


def _load_aexe_templates() -> dict[str, dict]:
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


_ASK_ABOUT_OPT_IDS = ("opt_who_are_you", "opt_where_is", "opt_rumors", "opt_exit")


def _harvest_ask_about_chrome(analyzer) -> dict:
    try:
        import arena_bridge as _ab
        import ask_about_menu_parser as _aamp
        anchor = _ab.find_anchor(analyzer)
        if not anchor:
            return {}
        parsed = _aamp.parse_menu(_ab.read_ask_about_menu(analyzer, anchor))
    except Exception:  # noqa: BLE001
        return {}
    title = parsed.get("title")
    if not (isinstance(title, str) and "ASK ABOUT" in title):
        return {}
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
            except Exception:  # noqa: BLE001
                pass
    return version, out, tables


_AKEY_TEMPLATE_PATH = os.path.join(_AEXE_TEMPLATE_DIR, "akey.json")


def _harvest_akey_ui(analyzer, supports: bool = True) -> dict:
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
    import arena_regen
    cc = {k.split(".", 1)[1]: v for k, v in tables.items()
          if k.startswith("char_creation.")}
    class_names = tables.get("classes.names") or []
    pref_attrs = tables.get("classes.preferred_attributes") or []
    if not cc or not class_names:
        return {}
    race_descs: list[str] = []
    ents = {e["key"]: e for e in arena_regen.parse_template_dat_bytes(template_raw)}
    for i in range(8):
        e = ents.get(str(1409 + i))
        vals = e.get("values") if e else None
        race_descs.append(str(vals[0]) if vals else "")
    return arena_regen.regenerate_chargen_ui(cc, class_names, pref_attrs, race_descs)


def load_golden_manifest(path: str | None = None) -> dict | None:
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
        except Exception:  # noqa: BLE001
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
    import arena_regen

    def _p(frac: float, label: str) -> None:
        if progress is not None:
            try:
                progress(frac, label)
            except Exception:  # noqa: BLE001
                pass

    def _ck() -> None:
        if cancel_check is not None and cancel_check():
            from arena_aexe import GenerationCancelled
            raise GenerationCancelled()

    _ck()
    _p(0.02, "Arena データを確認中…")
    raw, fp = _current_template_fingerprint(arena_dir)
    if raw is None:
        logger.warning("arena_local_data: TEMPLATE.DAT not found under %s", arena_dir)
        return None
    cls = classification if classification is not None else classify_arena_dir(arena_dir)
    exe_ok = cls.get("status") == "verified" and cls.get("supports_aexe_offsets")
    akey_ok = cls.get("status") == "verified" and cls.get("supports_akey_acd_offsets")
    if cls.get("status") != "verified":
        logger.warning(
            "arena_local_data: 未検証の Arena データです（status=%s・対応指紋セット不一致）。"
            "一部 EXE 由来文字列（A.EXE テーブル / A-key UI）は生成されません。"
            "DAT/TEMPLATE/VFS 由来の再生成は継続します。", cls.get("status"))
    _p(0.06, "テキストデータを再生成中…")
    be = arena_regen.regenerate_building_entry_bytes(raw)
    npcd = arena_regen.regenerate_npc_dialog_bytes(raw)
    _ck()
    _p(0.12, "INF テキストを読込中…")
    inft = arena_regen.regenerate_inf_text_bytes(_read_inf_files(
        arena_dir,
        progress=lambda done, total: _p(
            0.12 + 0.10 * (done / max(1, total)), "INF テキストを読込中…")))
    from arena_vfs import Vfs
    question_raw = Vfs(arena_dir).read("QUESTION.TXT")
    chargen_q = (arena_regen.regenerate_chargen_questions(question_raw)
                 if question_raw is not None else {})
    inft.update(chargen_q)
    tavern_raw = Vfs(arena_dir).read("TAVERN.DAT")
    atrade = (arena_regen.regenerate_atrade_tavern(tavern_raw)
              if tavern_raw is not None else {})
    npcd.update(atrade)
    _vfs = Vfs(arena_dir)
    eq, se, mu = (_vfs.read("EQUIP.DAT"), _vfs.read("SELLING.DAT"), _vfs.read("MUGUILD.DAT"))
    atrade_shop = (arena_regen.regenerate_atrade_shops(eq, se, mu)
                   if (eq and se and mu) else {})
    npcd.update(atrade_shop)
    akey_repair = arena_regen.regenerate_akey_repair(raw)
    npcd.update(akey_repair)
    _p(0.24, "地名・名前データを処理中…")
    citydata_raw = _read_citydata(arena_dir)
    world_map_json = None
    location_orig = None
    if citydata_raw:
        try:
            from services import citydata_reader
            world_map_json = citydata_reader.build_world_map(citydata_raw)
            location_orig = citydata_reader.build_location_originals(citydata_raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("arena_local_data: world_map/location 生成失敗: %s", e)
    namechnk_raw = Vfs(arena_dir).read("NAMECHNK.DAT")
    nnc = (arena_regen.regenerate_npc_name_chunks_bytes(namechnk_raw)
           if namechnk_raw is not None else {})
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
    if analyzer is not None and exe_ok:
        try:
            chrome = _harvest_ask_about_chrome(analyzer)
            if chrome:
                aexe_cats.setdefault("ask_about_menu", {}).update(chrome)
        except Exception as e:  # noqa: BLE001
            logger.warning("arena_local_data: ask_about chrome 採取失敗: %s", e)
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
        except Exception as e:  # noqa: BLE001
            logger.warning("arena_local_data: city_generation 採取失敗: %s", e)
    chargen_ui = _build_chargen_ui(aexe[2], raw) if aexe else {}
    inft.update(chargen_ui)
    _p(0.66, "メモリからデータを採取中…")
    akey_ui = _harvest_akey_ui(analyzer, akey_ok)
    npcd.update(akey_ui)
    exe_harvested = bool(aexe_cats) or bool(akey_ui)
    content_version = _AEXE_CONTENT_VERSION if aexe_cats else _BASE_CONTENT_VERSION
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
    aexe_manifests = {cat: arena_regen.build_aexe_manifest(cat, oj, fp)
                      for cat, oj in aexe_cats.items()}
    local_manifests.update(aexe_manifests)
    m_world_map = None
    m_location = None
    if citydata_raw:
        from services import citydata_reader
        m_world_map = citydata_reader.build_world_map_manifest(citydata_raw, fp)
        local_manifests[citydata_reader.WORLD_MAP_CATEGORY] = m_world_map
        if location_orig:
            m_location = citydata_reader.build_location_manifest(location_orig, fp)
            local_manifests[citydata_reader.LOCATION_CATEGORY] = m_location
    m_city_gen = None
    if city_gen_json is not None:
        from services import citydata_reader
        m_city_gen = citydata_reader.build_city_generation_manifest(
            city_gen_json["data"], fp)
        local_manifests[citydata_reader.CITY_GENERATION_CATEGORY] = m_city_gen
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
    surface_by_sid = _collect_surface_by_source_id(be, npcd, inft, nnc, location_orig)
    surface_by_sid.update(_collect_aexe_surfaces(aexe_cats))
    surface_by_sid.update(_collect_spellsg65_surfaces(arena_dir))
    try:
        import category_source_id as _csid
        surface_by_sid.update(_csid.public_builtin_surfaces())
        surface_by_sid.update(_csid.spell_effect_surfaces())
    except ImportError:
        pass
    if aexe:
        surface_by_sid.update(_collect_armor_prefix_surfaces(aexe[2]))
        try:
            import category_source_id as _csid2
            surface_by_sid.update(_csid2.magic_item_surfaces(aexe[2]))
            surface_by_sid.update(_csid2.material_item_surfaces(aexe[2]))
        except ImportError:
            pass
    inf_rich = _collect_inf_text_rich(inft)
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


_INF_RICH_FIELDS = ("inf", "idx", "text", "text_panel", "text_display", "question")


def _collect_inf_text_rich(inft: dict) -> dict[str, dict]:
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
    try:
        import localpack_builder
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
        try:
            from arena_pack import ArenaPack
            import i18n_localpack as _ilp
            with ArenaPack.open(tmp_out) as _lpk:
                _lpk.set_meta(_ilp.META_REGISTRY_VERSION,
                              str(int(bundle.get("registry_version", 0) or 0)))
                _lpk.set_meta(_ilp.META_BUILDER_VERSION, str(_V2_BUILDER_VERSION))
                if content_version is not None:
                    _lpk.set_meta(_META_CONTENT_VERSION, content_version)
                if asset_set_id is not None:
                    _lpk.set_meta(_META_ASSET_SET, asset_set_id)
                if asset_hashes is not None:
                    _lpk.set_meta(_META_ASSET_HASHES, asset_hashes)
                if exe_harvested is not None:
                    _lpk.set_meta(_META_EXE_HARVEST, "1" if exe_harvested else "0")
        except Exception:  # noqa: BLE001
            pass
        os.replace(tmp_out, out_path)
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
    except Exception as e:  # noqa: BLE001
        logger.warning("arena_local_data: v2 localpack 生成失敗: %s", e)


def rebuild_v2_localpack_standalone(user_dir: str) -> bool:
    lp_path = v2_localpack_path(user_dir)
    if not os.path.isfile(lp_path):
        return False
    try:
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("arena_local_data: localpack 再写像の読込に失敗: %s", e)
        return False
    surface = dict(lp.v2_surfaces)
    if not surface:
        logger.info("arena_local_data: localpack に再写像キャッシュが無い（heavy regen が必要）")
        return False
    rich = dict(lp.v2_rich) or None
    gen_assets = dict(lp.generated_assets) or None
    _write_v2_localpack(lp_path, surface, lp.arena_fingerprint, rich,
                        generated_assets=gen_assets)
    return True


def v2_localpack_update_status(user_dir: str) -> dict | None:
    lp_path = v2_localpack_path(user_dir)
    if not os.path.isfile(lp_path):
        return None
    try:
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
    except Exception:  # noqa: BLE001
        return {"needed": True, "axis": "unreadable", "from": 0, "to": _V2_BUILDER_VERSION,
                "is_dev": _is_dev_build()}
    bundle = _load_owned_bundle()
    if bundle is None:
        return None
    if lp.builder_version < _V2_BUILDER_VERSION:
        return {"needed": True, "axis": "builder", "from": lp.builder_version,
                "to": _V2_BUILDER_VERSION, "is_dev": _is_dev_build()}
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
    except Exception:  # noqa: BLE001
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
            except Exception:  # noqa: BLE001
                pass
    return out


def v2_localpack_needs_regen(arena_dir: str, user_dir: str, analyzer_available: bool,
                             classification: dict | None = None) -> bool:
    try:
        raw, fp = _current_template_fingerprint(arena_dir)
        if raw is None:
            return False
        cls = classification if classification is not None else classify_arena_dir(arena_dir)
        cur_hashes = json.dumps(cls.get("hashes") or {}, sort_keys=True)
        lp_path = v2_localpack_path(user_dir)
        if not os.path.isfile(lp_path):
            return False
        import i18n_localpack as _ilp
        lp = _ilp.open_localpack(lp_path)
        meta = lp.meta
        if meta.get(_ilp.META_ARENA_FINGERPRINT) != fp:
            return True
        if meta.get(_META_ASSET_HASHES) != cur_hashes:
            return True
        cv = meta.get(_META_CONTENT_VERSION)
        if cv == _AEXE_CONTENT_VERSION:
            return False
        if cv == _BASE_CONTENT_VERSION and not analyzer_available:
            return False
        return True
    except Exception:  # noqa: BLE001
        return True


__all__ = [
    "v2_localpack_path", "is_valid_arena_dir", "detect_arena_dirs",
    "detect_running_arena_dir", "classify_arena_dir", "build_local_pack",
    "v2_localpack_needs_regen", "rebuild_v2_localpack_standalone",
    "v2_localpack_update_status",
    "load_golden_manifest", "verify_against_golden",
]
