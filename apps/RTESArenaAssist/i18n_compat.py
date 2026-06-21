"""i18n_compat.py — 移行中の v1→v2 互換 adapter（旧文字列 ID で v2 を引く）。

既存コードの `legacy_id`（`mages.Damage Health` 等）を `legacy_id_map` で整数 ID へ変換し、
v2 resolver（bundle/localpack/mod）で解決する薄い層。runtime の段階移行に使い、全カテゴリ
移行後に削除する（完成形は整数 ID 直参照）。

lang コードは v1 系（`ja`/`en`/`es`）でも v2 の locale tag（`ja-JP` 等）でも受ける。
"""
from __future__ import annotations

import json
import os

import i18n_v2

# v1 lang コード → v2 locale tag。
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
        """旧 ID の表示テキストを現在 locale で返す（未登録/未解決は None）。"""
        nid = self.legacy_map.get(legacy_id)
        if nid is None:
            return None
        return self.v2.resolve_text(nid, _to_tag(locale or self.default_locale))

    def original(self, legacy_id: str) -> str | None:
        """旧 ID のライブ照合 surface（localpack 原文）を返す。"""
        nid = self.legacy_map.get(legacy_id)
        if nid is None:
            return None
        return self.v2.resolve_original_surface(nid)


__all__ = ["V2Compat"]
