from __future__ import annotations

import json
import os

import i18n_v2

_LOCALE_TAG = {"ja": "ja-JP", "en": "en-US", "es": "es-ES"}


def _to_tag(lang: str) -> str:
    return _LOCALE_TAG.get((lang or "").lower(), lang)


class V2Compat:
    def __init__(self, v2: i18n_v2.I18nV2, legacy_map: dict[str, int],
                 default_locale: str = "ja-JP"):
        self.v2 = v2
        self.legacy_map = legacy_map
        self.default_locale = default_locale

    @classmethod
    def load(cls, *, bundle_path: str, legacy_map_path: str,
             localpack_path: str | None = None,
             mods_dir: str | None = None,
             default_locale: str = "ja-JP") -> "V2Compat":
        v2 = i18n_v2.I18nV2.load(
            bundle_path=bundle_path, localpack_path=localpack_path,
            mods_dir=mods_dir)
        with open(legacy_map_path, "r", encoding="utf-8") as fh:
            legacy_map = json.load(fh).get("map", {})
        return cls(v2, legacy_map, default_locale)

    def id_of(self, legacy_id: str) -> int | None:
        return self.legacy_map.get(legacy_id)

    def text_opt(self, legacy_id: str, locale: str | None = None) -> str | None:
        nid = self.legacy_map.get(legacy_id)
        if nid is None:
            return None
        return self.v2.resolve_text(nid, _to_tag(locale or self.default_locale))

    def original(self, legacy_id: str) -> str | None:
        nid = self.legacy_map.get(legacy_id)
        if nid is None:
            return None
        return self.v2.resolve_original_surface(nid)


__all__ = ["V2Compat"]
