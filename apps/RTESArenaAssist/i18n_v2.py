from __future__ import annotations

import i18n_bundle as _bundle
import i18n_localpack as _localpack
import i18n_mods as _mods


def _is_english(locale: str) -> bool:
    return (locale or "").lower().split("-")[0] == "en"


class I18nV2:
    def __init__(self, bundle: _bundle.Bundle,
                 localpack: _localpack.Localpack | None = None,
                 modset: _mods.ModSet | None = None):
        self.bundle = bundle
        self.localpack = localpack
        self.mods = modset
        self.warnings: list[str] = []
        self.warnings.extend(bundle.warnings)
        if modset is not None:
            self.warnings.extend(modset.warnings)
        self._check_registry_compat()

    @classmethod
    def load(cls, *,
             bundle_path: str | None = None,
             bundle_obj: dict | None = None,
             localpack_path: str | None = None,
             mods_dir: str | None = None) -> "I18nV2":
        if bundle_obj is not None:
            bundle = _bundle.load_bundle_obj(bundle_obj)
        elif bundle_path is not None:
            bundle = _bundle.load_bundle(bundle_path)
        else:
            raise ValueError("load requires bundle_path or bundle_obj")

        lp = None
        if localpack_path is not None:
            lp = _localpack.open_localpack(localpack_path)

        ms = None
        if mods_dir is not None:
            ms = _mods.load_mods(mods_dir)

        return cls(bundle, lp, ms)

    def _check_registry_compat(self) -> None:
        bhash = self.bundle.registry_hash
        if self.localpack is not None and bhash and self.localpack.registry_hash:
            if self.localpack.registry_hash != bhash:
                self.warnings.append(
                    "registry_hash mismatch: localpack vs bundle "
                    "(continuing, ids applied partially)")
        if self.mods is not None:
            known = set(self.bundle.all_ids())
            for mod in self.mods.mods:
                if bhash and mod.registry_hash and mod.registry_hash != bhash:
                    self.warnings.append(
                        f"registry_hash mismatch: mod {mod.filename} vs bundle "
                        "(continuing)")
                unknown = [i for i in mod.texts if i not in known]
                if unknown:
                    self.warnings.append(
                        f"mod {mod.filename} has {len(unknown)} id(s) not in "
                        "registry (ignored)")

    def resolve_text(self, id: int, locale: str) -> str | None:
        id = int(id)
        target = self.bundle.redirect_of(id)
        if target is not None:
            id = target
        if self.mods is not None:
            hit = self.mods.text(id, locale)
            if hit is not None:
                return hit
        hit = self.bundle.locale_text(id, locale)
        if hit is not None:
            return hit
        if _is_english(locale) and self.localpack is not None:
            if self.bundle.source_policy_of(id) == "arena_generated":
                orig = self.localpack.original(id)
                if orig is not None:
                    return orig
        return None

    def resolve_original_surface(self, id: int) -> str | None:
        if self.localpack is None:
            return None
        return self.localpack.original(int(id))

    def rich_meta(self, id: int) -> dict | None:
        if self.localpack is None:
            return None
        return self.localpack.rich(int(id))

    def resolve_live_surface(self, id: int) -> str | None:
        if self.localpack is None:
            return None
        return self.localpack.live_surface(int(id))

    def category_of(self, id: int) -> dict | None:
        return self.bundle.category_of(id)

    def debug_resolve(self, id: int, locale: str) -> dict:
        return {
            "id": int(id),
            "locale": locale,
            "mod": self.mods.text(id, locale) if self.mods else None,
            "bundle": self.bundle.locale_text(id, locale),
            "original": self.resolve_original_surface(id),
            "display": self.resolve_text(id, locale),
            "source_policy": self.bundle.source_policy_of(id),
        }


__all__ = ["I18nV2"]
