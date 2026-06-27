from __future__ import annotations
import json
import arena_pack as ap
SCHEMA = 'rtesaa.localpack'
SUPPORTED_PACK_VERSION = 1
META_SCHEMA = 'schema'
META_PACK_VERSION = 'pack_version'
META_REGISTRY_HASH = 'registry_hash'
META_ARENA_FINGERPRINT = 'arena_fingerprint'
META_REGISTRY_VERSION = 'registry_version'
META_BUILDER_VERSION = 'builder_version'
_ORIGINALS_NAME = 'originals.json'
_AUDIT_NAME = 'audit.json'
_RICH_META_NAME = 'rich_meta.json'
_LIVE_SURFACE_OBS_NAME = 'live_surface_observations.json'
_V2_SURFACES_NAME = 'v2/surface_by_source_id.json'
_V2_RICH_NAME = 'v2/rich_by_source_id.json'

class LocalpackError(Exception):
    pass

class Localpack:

    def __init__(self, originals: dict[int, str], meta: dict[str, str], audit: dict[str, dict] | None=None, rich_meta: dict[int, dict] | None=None, live_surface_obs: dict[int, str] | None=None, generated_assets: dict[str, bytes] | None=None, v2_surfaces: dict[str, str] | None=None, v2_rich: dict[str, dict] | None=None):
        self._originals = originals
        self.meta = meta
        self.audit = audit or {}
        self.v2_surfaces = v2_surfaces or {}
        self.v2_rich = v2_rich or {}
        self.rich_meta = rich_meta or {}
        self.live_surface_obs = live_surface_obs or {}
        self.generated_assets = generated_assets or {}
        self.registry_hash = meta.get(META_REGISTRY_HASH, '')
        self.arena_fingerprint = meta.get(META_ARENA_FINGERPRINT, '')

        def _int(key: str) -> int:
            try:
                return int(meta.get(key, '0') or '0')
            except (TypeError, ValueError):
                return 0
        self.registry_version = _int(META_REGISTRY_VERSION)
        self.builder_version = _int(META_BUILDER_VERSION)

    def original(self, id: int) -> str | None:
        return self._originals.get(int(id))

    def rich(self, id: int) -> dict | None:
        return self.rich_meta.get(int(id))

    def live_surface(self, id: int) -> str | None:
        return self.live_surface_obs.get(int(id))

    def generated_asset(self, name: str) -> bytes | None:
        return self.generated_assets.get(name)

    def has(self, id: int) -> bool:
        return int(id) in self._originals

    def ids(self) -> list[int]:
        return list(self._originals.keys())

def build_localpack(path: str, originals: dict[int, str], *, registry_hash: str, arena_fingerprint: str='', audit: dict[str, dict] | None=None, rich_meta: dict[int, dict] | None=None, live_surface_obs: dict[int, str] | None=None, generated_assets: dict[str, bytes] | None=None, v2_surfaces: dict[str, str] | None=None, v2_rich: dict[str, dict] | None=None, pack_version: int=SUPPORTED_PACK_VERSION) -> None:
    with ap.ArenaPack.create(path) as pack:
        pack.set_meta(META_SCHEMA, SCHEMA)
        pack.set_meta(META_PACK_VERSION, str(pack_version))
        pack.set_meta(META_REGISTRY_HASH, registry_hash)
        if arena_fingerprint:
            pack.set_meta(META_ARENA_FINGERPRINT, arena_fingerprint)
        pack.put_text(_ORIGINALS_NAME, json.dumps({str(k): v for k, v in originals.items()}, ensure_ascii=False))
        if audit:
            pack.put_text(_AUDIT_NAME, json.dumps({str(k): v for k, v in audit.items()}, ensure_ascii=False))
        if rich_meta:
            pack.put_text(_RICH_META_NAME, json.dumps({str(k): v for k, v in rich_meta.items()}, ensure_ascii=False))
        if live_surface_obs:
            pack.put_text(_LIVE_SURFACE_OBS_NAME, json.dumps({str(k): v for k, v in live_surface_obs.items()}, ensure_ascii=False))
        if v2_surfaces:
            pack.put_text(_V2_SURFACES_NAME, json.dumps(v2_surfaces, ensure_ascii=False))
        if v2_rich:
            pack.put_text(_V2_RICH_NAME, json.dumps(v2_rich, ensure_ascii=False))
        for name, data in (generated_assets or {}).items():
            pack.put('generated_assets/' + name, data)

def open_localpack(path: str) -> Localpack:
    try:
        pack = ap.ArenaPack.open(path)
    except ap.PackError as exc:
        raise LocalpackError(f'localpack open failed: {exc}') from exc
    try:
        meta = pack.all_meta()
        schema = meta.get(META_SCHEMA)
        if schema != SCHEMA:
            raise LocalpackError(f'unknown localpack schema: {schema!r}')
        ver = int(meta.get(META_PACK_VERSION, '0') or '0')
        if ver > SUPPORTED_PACK_VERSION:
            raise LocalpackError(f'localpack pack_version {ver} newer than supported {SUPPORTED_PACK_VERSION}')
        try:
            raw = pack.get_text(_ORIGINALS_NAME)
        except ap.PackError as exc:
            raise LocalpackError(f'localpack corrupt: {exc}') from exc
        if raw is None:
            raise LocalpackError('localpack missing originals section')
        originals = {int(k): str(v) for k, v in json.loads(raw).items()}
        audit_raw = None
        if pack.exists(_AUDIT_NAME):
            audit_raw = json.loads(pack.get_text(_AUDIT_NAME) or '{}')
        rich_raw = None
        if pack.exists(_RICH_META_NAME):
            rich_raw = {int(k): v for k, v in json.loads(pack.get_text(_RICH_META_NAME) or '{}').items()}
        lso_raw = None
        if pack.exists(_LIVE_SURFACE_OBS_NAME):
            lso_raw = {int(k): str(v) for k, v in json.loads(pack.get_text(_LIVE_SURFACE_OBS_NAME) or '{}').items()}
        gen_assets: dict[str, bytes] = {}
        _ga_prefix = 'generated_assets/'
        for name in pack.names():
            if name.startswith(_ga_prefix):
                data = pack.get(name)
                if data is not None:
                    gen_assets[name[len(_ga_prefix):]] = data
        v2_surf = None
        if pack.exists(_V2_SURFACES_NAME):
            v2_surf = {str(k): str(v) for k, v in json.loads(pack.get_text(_V2_SURFACES_NAME) or '{}').items()}
        v2_rich = None
        if pack.exists(_V2_RICH_NAME):
            v2_rich = {str(k): v for k, v in json.loads(pack.get_text(_V2_RICH_NAME) or '{}').items()}
        return Localpack(originals, meta, audit_raw, rich_raw, lso_raw, gen_assets, v2_surf, v2_rich)
    finally:
        pack.close()
__all__ = ['Localpack', 'LocalpackError', 'build_localpack', 'open_localpack', 'SCHEMA', 'SUPPORTED_PACK_VERSION']
