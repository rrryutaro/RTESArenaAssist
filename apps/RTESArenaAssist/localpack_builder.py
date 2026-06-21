from __future__ import annotations

import i18n_localpack as _ilp
import legacy_adapter as _adapter
import spell_effect_structure as _ses


def build_originals(registry: dict,
                    original_by_cat: dict[str, dict[str, dict]],
                    ) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    originals, audit, warnings = _adapter.migrate_originals(
        registry, original_by_cat)
    for cat in registry.get("categories", []):
        if cat.get("category") != "spell_effect":
            continue
        for eid, info in _ses.build_originals(cat.get("entries", [])).items():
            originals[eid] = info["text"]
            audit[str(eid)] = {
                "status": info.get("status", "verified"),
                "category": "spell_effect",
                "provider": "spell_effect_structure",
            }
    return originals, audit, warnings


def _as_ids(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [int(x) for x in value]
    return [int(value)]


def ids_for_source_id(source_id_map: dict, source_id: str) -> list[int]:
    return _as_ids(source_id_map.get(source_id))


def single_id_for_source_id(source_id_map: dict, source_id: str) -> int:
    ids = ids_for_source_id(source_id_map, source_id)
    if len(ids) != 1:
        raise ValueError(
            f"source_id {source_id!r} maps to {len(ids)} ids (expected 1)")
    return ids[0]


def build_originals_by_source_id(
        source_id_map: dict,
        surface_by_source_id: dict[str, str],
        *,
        provider: str = "",
        status: str = "generated",
        category_by_id: dict[int, str] | None = None,
        ) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    originals: dict[int, str] = {}
    audit: dict[str, dict] = {}
    warnings: list[str] = []
    cat_by_id = category_by_id or {}
    for source_id, surface in surface_by_source_id.items():
        ids = ids_for_source_id(source_id_map, source_id)
        if not ids:
            warnings.append(f"source_id not in map (degraded): {source_id}")
            continue
        if not surface:
            warnings.append(f"empty surface (degraded): {source_id}")
            continue
        for nid in ids:
            originals[nid] = surface
            entry = {"status": status, "source_id": source_id,
                     "provider": provider}
            if nid in cat_by_id:
                entry["target_category"] = cat_by_id[nid]
            audit[str(nid)] = entry
    return originals, audit, warnings


def write_localpack(out_path: str,
                    registry: dict,
                    original_by_cat: dict[str, dict[str, dict]],
                    *,
                    registry_hash: str,
                    arena_fingerprint: str = "") -> dict:
    originals, audit, warnings = build_originals(registry, original_by_cat)
    _ilp.build_localpack(
        out_path, originals,
        registry_hash=registry_hash,
        arena_fingerprint=arena_fingerprint,
        audit=audit)
    return {"originals": len(originals), "warnings": warnings}


def rich_meta_by_id(source_id_map: dict,
                    rich_by_source_id: dict[str, dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for source_id, meta in rich_by_source_id.items():
        if not isinstance(meta, dict):
            continue
        for nid in ids_for_source_id(source_id_map, source_id):
            out[nid] = meta
    return out


def write_localpack_by_source_id(out_path: str,
                                 source_id_map: dict,
                                 surface_by_source_id: dict[str, str],
                                 *,
                                 registry_hash: str,
                                 spell_effect_entries: list[dict] | None = None,
                                 rich_by_source_id: dict[str, dict] | None = None,
                                 arena_fingerprint: str = "",
                                 generated_assets: dict[str, bytes] | None = None,
                                 provider: str = "") -> dict:
    originals, audit, warnings = build_originals_by_source_id(
        source_id_map, surface_by_source_id, provider=provider)
    for entry in (spell_effect_entries or []):
        src = entry.get("source") or {}
        result = _ses.surface_for(
            int(src.get("effect_id", _ses.NONE)),
            int(src.get("sub_effect_id", 0)),
            int(src.get("affected_attr_id", 0)),
        )
        if result is None:
            continue
        text, status = result
        eid = int(entry["id"])
        originals[eid] = text
        audit[str(eid)] = {"status": status, "category": "spell_effect",
                           "provider": "spell_effect_structure"}
    rich = rich_meta_by_id(source_id_map, rich_by_source_id or {})
    _ilp.build_localpack(
        out_path, originals,
        registry_hash=registry_hash,
        arena_fingerprint=arena_fingerprint,
        audit=audit,
        rich_meta=rich or None,
        generated_assets=generated_assets or None,
        v2_surfaces=dict(surface_by_source_id) or None,
        v2_rich=dict(rich_by_source_id) if rich_by_source_id else None)
    return {"originals": len(originals), "warnings": warnings,
            "rich_meta": len(rich),
            "generated_assets": len(generated_assets or {})}


__all__ = ["build_originals", "write_localpack", "write_localpack_by_source_id",
           "build_originals_by_source_id", "ids_for_source_id", "rich_meta_by_id"]
