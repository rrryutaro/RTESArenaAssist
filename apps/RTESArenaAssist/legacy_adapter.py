from __future__ import annotations
import json
import os

def migrate_originals(registry: dict, original_by_category: dict[str, dict[str, dict]]) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    originals: dict[int, str] = {}
    audit: dict[str, dict] = {}
    warnings: list[str] = []
    for cat in registry.get('categories', []):
        name = cat.get('category')
        if cat.get('source_policy') != 'arena_generated':
            continue
        if name not in original_by_category:
            continue
        src = original_by_category.get(name, {})
        for entry in cat.get('entries', []):
            if entry.get('retired'):
                continue
            legacy = entry.get('legacy_id')
            if not legacy:
                continue
            rec = src.get(legacy)
            if rec is None:
                warnings.append(f"{name}: legacy '{legacy}' not in _original (degraded)")
                continue
            text = rec.get('original')
            if text is None or text == '':
                warnings.append(f"{name}: legacy '{legacy}' has empty original (degraded)")
                continue
            eid = int(entry['id'])
            originals[eid] = text
            ent = {'status': 'migrated', 'category': name}
            if rec.get('src_hash'):
                ent['src_hash'] = rec['src_hash']
            audit[str(eid)] = ent
    return (originals, audit, warnings)

def load_original_by_category(i18n_dir: str, categories: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cat in categories:
        path = os.path.join(i18n_dir, '_original', cat + '.json')
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
        out[cat] = {k: v for k, v in raw.items() if not k.startswith('_') and isinstance(v, dict)}
    return out
__all__ = ['migrate_originals', 'load_original_by_category']
