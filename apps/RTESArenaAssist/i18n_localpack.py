"""i18n_localpack.py — Arena 生成 localpack（originals）の読み書き。

ユーザー Arena 環境から生成する単一ファイル `RTESArenaAssist.localpack`。物理表現は
`arena_pack`（SQLite+zlib）を踏襲し、ユーザーから見れば 1 ファイル・生 JSON を散らかさない。

section（arena_pack の files/meta 上に実装）:
  - meta: schema / pack_version / registry_hash / arena_fingerprint。
  - originals.json: { "<id>": "<text>" } の単一 blob（整数 ID → Arena 原文 surface）。
  - audit.json（任意）: { "<id>": {"hash":.., "status":..} } 等の検証メタ。
  - rich_meta.json（任意）: consumer 移行 rich メタ（id→構造キー/表示変種）。
  - live_surface_observations.json（任意）: { "<id>": "<surface>" }（整数 ID → runtime 観測 surface）。
    live_surface カテゴリ（runtime NPC dialog 観測の固定語彙）の surface→id 逆引き用。**localpack.originals
    とは別 section**＝source/golden と live-surface curation を再混在させない。user-env 専用で
    公開 bundle へは同梱しない。
  - generated_assets/*（任意）: map/city_generation 等の非翻訳生成資産。

fail（読み込み拒否＝例外）:
  - schema 未知 / pack_version がサポート版より新しい / 必須 section（originals）欠落 /
    arena_pack の整合エラー（破損）。
registry_hash 不一致・一部 ID 欠落は fail でなく resolver 側で warning/degraded として扱う。
"""
from __future__ import annotations

import json

import arena_pack as ap

SCHEMA = "rtesaa.localpack"
SUPPORTED_PACK_VERSION = 1

META_SCHEMA = "schema"
META_PACK_VERSION = "pack_version"
META_REGISTRY_HASH = "registry_hash"
META_ARENA_FINGERPRINT = "arena_fingerprint"
# 辞書(v2 localpack)の版記録（Assist 本体バージョンとは独立）。起動時の更新判定に使う:
#   - registry_version: 同梱 bundle の ID 登録構造版（公開リリースの辞書版・人向けラベル）。
#   - registry_hash   : ID 登録構造のハッシュ（開発中の自動更新検出に使う・どの byte 変化も拾う）。
#   - builder_version : localpack 生成ロジック版（bundle 不変でも出力が変わる修正＝_aexe_template 等）。
# 判定: dev=registry_hash 不一致 or builder 不一致／release=registry_version 上昇 or builder 不一致。
# 未記録(旧 localpack)は registry_version=0 / builder_version=0 扱い＝必ず更新対象。
META_REGISTRY_VERSION = "registry_version"
META_BUILDER_VERSION = "builder_version"

_ORIGINALS_NAME = "originals.json"
_AUDIT_NAME = "audit.json"
_RICH_META_NAME = "rich_meta.json"
_LIVE_SURFACE_OBS_NAME = "live_surface_observations.json"
# 再写像キャッシュ（source_id→Arena surface / source_id→rich メタ）。bundle/registry が変わったとき
# localpack 単独で辞書を再写像するための入力（採取をやり直さない）。source_id キーは registry の
# ID 変更に依存しないため再写像で安定。
_V2_SURFACES_NAME = "v2/surface_by_source_id.json"
_V2_RICH_NAME = "v2/rich_by_source_id.json"


class LocalpackError(Exception):
    """localpack が読み取り不能（schema 非互換・必須欠落・破損）。fail 相当。"""


class Localpack:
    """読み込み済み localpack の originals 索引。"""

    def __init__(self, originals: dict[int, str], meta: dict[str, str],
                 audit: dict[str, dict] | None = None,
                 rich_meta: dict[int, dict] | None = None,
                 live_surface_obs: dict[int, str] | None = None,
                 generated_assets: dict[str, bytes] | None = None,
                 v2_surfaces: dict[str, str] | None = None,
                 v2_rich: dict[str, dict] | None = None):
        self._originals = originals
        self.meta = meta
        self.audit = audit or {}
        # 再写像キャッシュ（source_id→surface / source_id→rich・localpack 単独再写像の入力）。
        self.v2_surfaces = v2_surfaces or {}
        self.v2_rich = v2_rich or {}
        # consumer 移行 rich メタ（id→{構造キー/表示変種}・原文隣接で user-env 限定・任意 section）。
        self.rich_meta = rich_meta or {}
        # live_surface 観測 surface（id→surface・originals とは別 section・user-env 専用）。
        self.live_surface_obs = live_surface_obs or {}
        # 翻訳外 Arena 生成資産（name→bytes・world_map/city_generation 等）。公開版では
        # 本セクションが翻訳外 Arena 由来 provider の唯一入口になる。
        self.generated_assets = generated_assets or {}
        self.registry_hash = meta.get(META_REGISTRY_HASH, "")
        self.arena_fingerprint = meta.get(META_ARENA_FINGERPRINT, "")

        def _int(key: str) -> int:
            try:
                return int(meta.get(key, "0") or "0")
            except (TypeError, ValueError):
                return 0
        self.registry_version = _int(META_REGISTRY_VERSION)
        self.builder_version = _int(META_BUILDER_VERSION)

    def original(self, id: int) -> str | None:
        return self._originals.get(int(id))

    def rich(self, id: int) -> dict | None:
        return self.rich_meta.get(int(id))

    def live_surface(self, id: int) -> str | None:
        """live_surface カテゴリの観測 surface（id→surface）。未観測は None。"""
        return self.live_surface_obs.get(int(id))

    def generated_asset(self, name: str) -> bytes | None:
        """翻訳外 Arena 生成資産（world_map.json 等）を bytes で返す。未収録は None。"""
        return self.generated_assets.get(name)

    def has(self, id: int) -> bool:
        return int(id) in self._originals

    def ids(self) -> list[int]:
        return list(self._originals.keys())


def build_localpack(path: str,
                    originals: dict[int, str],
                    *,
                    registry_hash: str,
                    arena_fingerprint: str = "",
                    audit: dict[str, dict] | None = None,
                    rich_meta: dict[int, dict] | None = None,
                    live_surface_obs: dict[int, str] | None = None,
                    generated_assets: dict[str, bytes] | None = None,
                    v2_surfaces: dict[str, str] | None = None,
                    v2_rich: dict[str, dict] | None = None,
                    pack_version: int = SUPPORTED_PACK_VERSION) -> None:
    """originals（id→text）から localpack を構築する。"""
    with ap.ArenaPack.create(path) as pack:
        pack.set_meta(META_SCHEMA, SCHEMA)
        pack.set_meta(META_PACK_VERSION, str(pack_version))
        pack.set_meta(META_REGISTRY_HASH, registry_hash)
        if arena_fingerprint:
            pack.set_meta(META_ARENA_FINGERPRINT, arena_fingerprint)
        # 整数 ID は JSON object key で文字列化される（読取時に int 復元）。
        pack.put_text(_ORIGINALS_NAME,
                      json.dumps({str(k): v for k, v in originals.items()},
                                 ensure_ascii=False))
        if audit:
            pack.put_text(_AUDIT_NAME,
                          json.dumps({str(k): v for k, v in audit.items()},
                                     ensure_ascii=False))
        if rich_meta:
            pack.put_text(_RICH_META_NAME,
                          json.dumps({str(k): v for k, v in rich_meta.items()},
                                     ensure_ascii=False))
        if live_surface_obs:
            pack.put_text(_LIVE_SURFACE_OBS_NAME,
                          json.dumps({str(k): v for k, v in
                                      live_surface_obs.items()},
                                     ensure_ascii=False))
        if v2_surfaces:
            pack.put_text(_V2_SURFACES_NAME,
                          json.dumps(v2_surfaces, ensure_ascii=False))
        if v2_rich:
            pack.put_text(_V2_RICH_NAME,
                          json.dumps(v2_rich, ensure_ascii=False))
        for name, data in (generated_assets or {}).items():
            pack.put("generated_assets/" + name, data)


def open_localpack(path: str) -> Localpack:
    """localpack を開く（schema/version 検証つき・fail は例外）。"""
    try:
        pack = ap.ArenaPack.open(path)
    except ap.PackError as exc:
        raise LocalpackError(f"localpack open failed: {exc}") from exc
    try:
        meta = pack.all_meta()
        schema = meta.get(META_SCHEMA)
        if schema != SCHEMA:
            raise LocalpackError(f"unknown localpack schema: {schema!r}")
        ver = int(meta.get(META_PACK_VERSION, "0") or "0")
        if ver > SUPPORTED_PACK_VERSION:
            raise LocalpackError(
                f"localpack pack_version {ver} newer than supported "
                f"{SUPPORTED_PACK_VERSION}")
        try:
            raw = pack.get_text(_ORIGINALS_NAME)
        except ap.PackError as exc:
            raise LocalpackError(f"localpack corrupt: {exc}") from exc
        if raw is None:
            raise LocalpackError("localpack missing originals section")
        originals = {int(k): str(v) for k, v in json.loads(raw).items()}
        audit_raw = None
        if pack.exists(_AUDIT_NAME):
            audit_raw = json.loads(pack.get_text(_AUDIT_NAME) or "{}")
        rich_raw = None
        if pack.exists(_RICH_META_NAME):
            rich_raw = {int(k): v for k, v in
                        json.loads(pack.get_text(_RICH_META_NAME) or "{}").items()}
        lso_raw = None
        if pack.exists(_LIVE_SURFACE_OBS_NAME):
            lso_raw = {int(k): str(v) for k, v in
                       json.loads(pack.get_text(_LIVE_SURFACE_OBS_NAME)
                                  or "{}").items()}
        # 翻訳外生成資産（generated_assets/<name>）を bytes で読み戻す（公開 v2 単独動作）。
        gen_assets: dict[str, bytes] = {}
        _ga_prefix = "generated_assets/"
        for name in pack.names():
            if name.startswith(_ga_prefix):
                data = pack.get(name)
                if data is not None:
                    gen_assets[name[len(_ga_prefix):]] = data
        # 再写像キャッシュ（source_id→surface / source_id→rich）を読み戻す（pak 非依存の再写像入力）。
        v2_surf = None
        if pack.exists(_V2_SURFACES_NAME):
            v2_surf = {str(k): str(v) for k, v in
                       json.loads(pack.get_text(_V2_SURFACES_NAME) or "{}").items()}
        v2_rich = None
        if pack.exists(_V2_RICH_NAME):
            v2_rich = {str(k): v for k, v in
                       json.loads(pack.get_text(_V2_RICH_NAME) or "{}").items()}
        return Localpack(originals, meta, audit_raw, rich_raw, lso_raw, gen_assets,
                         v2_surf, v2_rich)
    finally:
        pack.close()


__all__ = ["Localpack", "LocalpackError", "build_localpack", "open_localpack",
           "SCHEMA", "SUPPORTED_PACK_VERSION"]
