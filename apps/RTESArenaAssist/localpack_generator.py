from __future__ import annotations
import i18n_bundle as _bundle
import spell_effect_structure as _spell_effect

class GeneratorError(Exception):
    pass

def _provider_spell_effect(entries: list[dict]) -> dict[int, dict]:
    return _spell_effect.build_originals(entries)
_PROVIDERS = {'spell_effect_structure': _provider_spell_effect}

def generate_originals(bundle: _bundle.Bundle) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    originals: dict[int, str] = {}
    audit: dict[str, dict] = {}
    warnings: list[str] = []
    for name, meta in bundle.categories.items():
        if meta.get('source_policy') != 'arena_generated':
            continue
        provider = meta.get('source_provider')
        fn = _PROVIDERS.get(provider) if provider else None
        if fn is None:
            warnings.append(f'category {name}: no provider for {provider!r} (skipped)')
            continue
        produced = fn(meta.get('entries') or [])
        covered = set(produced.keys())
        for entry in meta.get('entries') or []:
            eid = int(entry['id'])
            if eid not in covered:
                warnings.append(f'category {name}: id {eid} produced no surface (degraded)')
        for eid, info in produced.items():
            originals[eid] = info['text']
            audit[str(eid)] = {'status': info.get('status', 'verified'), 'category': name, 'provider': provider}
    return (originals, audit, warnings)

def verified_count(audit: dict[str, dict]) -> int:
    return sum((1 for v in audit.values() if v.get('status') == 'verified'))
__all__ = ['generate_originals', 'verified_count', 'GeneratorError']
