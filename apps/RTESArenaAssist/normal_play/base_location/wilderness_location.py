"""base_location/wilderness_location.py — 分離階層 L2 (= 基本居場所) C3 フィールド。

データソース:
  - wildSeed (= location.name 先頭 4 char LE32) で 64×64 wild block ID grid を
    deterministic 生成 (= ArenaWildUtils::generateWildernessIndices 移植)
  - 周辺 2×2 chunks (= 128×128 voxel) の RMD ロード
    * 中央 4 chunks (= ID 1-4): Arena フォルダの WILD001-004.RMD
      (= Arena が reviseWildCityBlock 変換済を動的書出)
    * その他 (= ID 5-70): 抽出済み RMD アセットの WILD{NNN}.RMD

判定:
  - `location_type == "wilderness"` かつ `in_interior == False`
  - location_name (= 街名) 必須 (= wildSeed の元)

描画:
  - 3×3 chunks (= 192×192 voxel) ロード (= OpenTESArena ChunkDistance=1 と
    同じ規模)。player chunk を中央に配置し周辺 8 chunks を pre-load する。
  - 表示 origin は (chunk_x - 1, chunk_y - 1) (= 3×3 の NW corner)
  - player marker は rt_x / rt_z を 192 grid 内 local 座標として使う:
    * lx = chunk_x*64 + (rt_x-32) - origin_x*64 - 32 = rt_x (origin shift で
      -32 ハック効果が吸収される)
    * ly = chunk_y*64 + (rt_z-32) - origin_y*64 - 32 = rt_z (同上)
  - canvas 側で x_flip 適用 (= cartographic west-left)

既知の限界:
  - セーブロード途中フィールド着地時は初期 chunk seed が不正確 (= 街中央仮置き)
  - 5Hz poll で chunk 境界を 0.2 秒未満で跨ぐと transition 取りこぼし可能性

注意: `map/wilderness.py` から本 path へ移管。共通基底は当面
normal_play/map/base.py を再利用 (= 将来統合予定)。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from common_draw.automap_canvas import CanvasData
from services.arena_location_utils import get_wilderness_seed
from services.mif_loader import DEFAULT_INF_DIR, parse_inf_menu_texture_map
from services.wild_block_lists import get_block_lists, get_cache_source
from services.wild_flats import extract_flat_marks, get_wild_flat_category_map
from services.wild_chunk_tracker import WildChunkTracker
from services.wild_voxel_assembler import (
    CITY_ORIGIN_CHUNK_X, CITY_ORIGIN_CHUNK_Y,
    WILD_HEIGHT, WILD_WIDTH,
    build_wild_voxel_grid,
)

from normal_play.map.base import MapContext, MapSessionBase
from normal_play.base_location.base_location_view import FieldEntranceContext

_log = logging.getLogger("base_location.wilderness")


# 原典由来の座標モデル（OpenTESArena）:
#   rt_x/rt_z は「中心寄せ 128×128 表示窓」内の表示座標で、通常 32..95 を取る
#   （+32 = RMDFile::WIDTH/2 の半 chunk オフセット）。実 chunk-local voxel ではない。
#   tracker が追跡する chunk_x/chunk_y は実 player chunk ではなく centered origin
#   chunk o（getCenteredWildOrigin 相当）。
#     abs_original = o * 64 + rt
#     actual_chunk = o + (1 if rt >= 64 else 0)
#     actual_voxel = rt % 64
#   player-centered 3×3 表示: grid origin = actual_chunk - 1 で player を中央 chunk
#   （cell 64..127）に置く。
_CHUNK = 64
_HALF_CHUNK = _CHUNK // 2  # = 32（中心寄せ窓の半 chunk・seed 判定境界）
_N_CHUNKS = 3
_GRID_SIZE = _N_CHUNKS * _CHUNK  # = 192 cell
# マーカー表示用 rt の有効域。gate 着地の clamp 域 rt<32 を表示に含めるため 0..127。
# ※tracker の wrap 判定は別（clamp 域を弾く 30..97 のまま＝誤 wrap でマップを壊さない）。
_RT_MAX_DISPLAY = 2 * _CHUNK - 1  # = 127
# 施設/ダンジョン往復の判定。退出位置は突入位置とほぼ同一（同 voxel）なので、直前
# rt との差がこの許容内なら「往復＝chunk 保持」、それ以上なら「新規進入＝seed」。
_ROUNDTRIP_TOL = 8
# center_origin（wildBlockX/Y）受理域の grid 外マージン。プレイヤーは 64×64 grid の
# 外まで歩ける（実機観測: 教会を出て西へ center_origin=-2＝grid を 2 chunk 外）。
# 主検証は wildSeed 一致（同一アトミック読み）。本マージンは明らかな garbage（大きな
# i16）だけを弾く緩い sanity 範囲で、grid ±1 region 幅ぶんの徘徊を許す。
# 到達上限は観測ベースで未確定。さらに外側が出たら拡張する。
_WILD_ORIGIN_MARGIN = _CHUNK  # = 64（grid 1 枚ぶん）

# center_origin と rt の直読み元（OpenTESArena SaveEngine::PlayerData）。
# PlayerData がライブメモリに同一レイアウトで展開されている。基底 = anchor+0x5C2
# （= Gold オフセットと一致して確認）。rt と origin は必ず**同一アトミック読み**から取り、
# 両者の desync を防ぐ（独立読みすると origin が食い違いチャンク単位で破綻する）。
#   wildX      = anchor+0x600 (u16)  rt_x = wildX // 128（窓 local 0..127）
#   wildY      = anchor+0x602 (u16)  rt_z = wildY // 128
#   wildBlockX = anchor+0x608 (u16)  center_origin X（0..63）
#   wildBlockY = anchor+0x60A (u16)  center_origin Y（0..63）
#   wildSeed   = anchor+0x616 (u32)  get_wilderness_seed と一致（active 検証）
# abs = wildBlock*64 + (wild//128) は再センタリング境界でも連続（rt wrap を origin +1 が相殺）。
_PLAYERDATA_WILD_OFF = 0x600          # wildX の anchor 相対 offset（読み開始）
_PLAYERDATA_WILD_LEN = 0x61A - 0x600  # wildSeed 末尾までを 1 read で取る（= 26 byte）

# 荒地 *MENU voxel の texture index は INF から導出する（手書き値は持たない）。
#   texture index は @FLOORS→@WALLS 連結の full voxelTextures index（= MAP1 wall
#   voxel の mostSigByte-1 と同基準）。detect_menu_cells もこの基準で照合する。
#   ※以前のハードコード {3,8,45,46} は @WALLS 内相対値で基準が食い違っており、
#     塔/ダンジョンを取りこぼし街門を拾う誤りがあった。
# menuID の意味（OpenTESArena MapGeneration WildMenuMappings / ArenaWildUtils）:
#   0=なし 1=クリプト 2=家 3=酒場 4=神殿 5=塔 6,7=街門 8,9=ダンジョン
# vanilla 自動マップ表示 = menuIsDisplayedInWildAutomap = {1,5,8,9}（クリプト/塔/
#   ダンジョン）。家/酒場/神殿/街門は拡張表示でのみ追加する。
_WILD_GAME_MENU_IDS = frozenset({1, 5, 8, 9})        # 常時赤（クリプト/塔/ダンジョン）
_WILD_EXTENDED_MENU_IDS = frozenset({2, 3, 4, 6, 7})  # 拡張追加（家/酒場/神殿/街門）
# 荒地 INF（climate 違いでも MENU 写像は同一・テストで一致を保証）。
_WILD_INF_CANDIDATES = ("TWN.INF", "DWN.INF", "MWN.INF")
# INF 取得不可時の fallback（実 INF 実測値・テストで一致を検証）。
_WILD_MENU_MAP_FALLBACK = {
    0: 7, 1: 8, 2: 9, 3: 10, 4: 11, 5: 13, 6: 45, 7: 46, 8: 50, 9: 51,
}
# フィールド扉から MIF を解決して InteriorMapSession へ送る対象 menuID。
#   クリプト(1)/家(2)/酒場(3)/神殿(4)/塔(5)＝固定 prefix の MIF を扉座標で解決可
#   （get_door_voxel_mif_name: 1→WCRYPT/2→BS(家)/3→TAVERN/4→TEMPLE/5→TOWER）。
#   ダンジョン(8,9)＝ランダムで固定 MIF なし（NO_INDEX）→ city 誤認回避のみ。
#   ※神殿が扉種別で識別できる以上、酒場/家も同じ扉種別で識別できる（観測不要）。
#     酒場(3)/家(2)を列挙し漏れると、フィールドの酒場が街経路に
#     落ちて神殿(TEMPLE4)に誤解決する。
_WILD_ENTERABLE_MENU_IDS = frozenset({1, 2, 3, 4, 5, 8, 9})
_MENU_LABELS = {1: "crypt", 2: "house", 3: "tavern", 4: "temple",
                5: "tower", 8: "dungeon", 9: "dungeon"}
# menuID→full texture index 写像のモジュールキャッシュ（初回 INF パース後に確定）。
_wild_menu_map_cache: Optional[dict[int, int]] = None
# (game_set, extended_set) のモジュールキャッシュ。
_wild_menu_tex_sets: Optional[tuple[frozenset[int], frozenset[int]]] = None


def _get_wild_menu_map() -> dict[int, int]:
    """荒地 INF から menuID→full texture index 写像を解決（キャッシュ）。

    INF が読めない場合は実測 fallback を使う。

    INF 解決は loose（抽出済み INF）優先→ユーザー Arena install の VFS
    （GLOBAL.BSA 復号）fallback。`parse_inf_menu_texture_map` 内の `_read_inf_lines` が
    basename で loose→VFS を解決するため、loose 不在環境でも install VFS から読む
    （`path.is_file()` で gate すると VFS を読まず実測 fallback に落ちるため除去）。
    """
    global _wild_menu_map_cache
    if _wild_menu_map_cache is not None:
        return _wild_menu_map_cache
    menu_map: dict[int, int] = {}
    for name in _WILD_INF_CANDIDATES:
        # 構築パスは実在しなくてよい（parser が basename で loose→VFS 解決）。
        menu_map = parse_inf_menu_texture_map(DEFAULT_INF_DIR / name)
        if menu_map:
            break
    if not menu_map:
        menu_map = dict(_WILD_MENU_MAP_FALLBACK)
    _wild_menu_map_cache = menu_map
    return menu_map


def _wild_texture_to_menu_id() -> dict[int, int]:
    """full texture index → menuID の逆引き写像。"""
    return {tex: mid for mid, tex in _get_wild_menu_map().items()}


def _wild_menu_texture_sets() -> tuple[frozenset[int], frozenset[int]]:
    """荒地 INF から (常時赤 set, 拡張 set) を full texture index で解決する。

    常時赤 = menuID {1,5,8,9}（vanilla 自動マップ相当・クリプト/塔/ダンジョン）。
    拡張   = 常時赤 ∪ menuID {2,3,4,6,7}（家/酒場/神殿/街門）。
    INF が読めない場合は実測 fallback を使う。結果はモジュールキャッシュ。
    """
    global _wild_menu_tex_sets
    if _wild_menu_tex_sets is not None:
        return _wild_menu_tex_sets
    menu_map = _get_wild_menu_map()
    game = frozenset(menu_map[m] for m in _WILD_GAME_MENU_IDS if m in menu_map)
    extended = game | frozenset(
        menu_map[m] for m in _WILD_EXTENDED_MENU_IDS if m in menu_map)
    _wild_menu_tex_sets = (game, extended)
    return _wild_menu_tex_sets

# C3 認識時の座標 log で読む「絶対チャンク source 探索用」候補オフセット
# （観測 west で fixed-point 位置/voxel 候補と判明）。
_C3_ENTRY_CANDIDATES = [
    (0xA902, "a902"), (0xA900, "a900"), (0xA904, "a904"), (0xA908, "a908"),
    (0xA880, "a880"), (0xA84E, "a84e"), (0xA850, "a850"), (0xA852, "a852"),
    (0xA858, "a858"),
]


class WildernessMapSession(MapSessionBase):
    """C3 フィールドマップ。wildSeed + WILD{NNN}.RMD で 128×128 grid 組立。"""

    def __init__(self) -> None:
        super().__init__()
        self._wild_seed: Optional[int] = None
        self._origin_chunk: Optional[tuple[int, int]] = None
        self._walkable: Optional[np.ndarray] = None
        self._map1:     Optional[np.ndarray] = None
        self._flor:     Optional[np.ndarray] = None
        self._bitmap:   Optional[np.ndarray] = None
        # chunk_x/y 遷移追跡（fallback 用。本命は wildBlockX/Y 直読み）
        self._chunk_tracker = WildChunkTracker()
        # 採用中の center_origin chunk（mem 直読み or tracker fallback の結果）。
        self._center_origin: Optional[tuple[int, int]] = None
        # 現フィールドの live 2×2 window（PlayerData wildBlocks[4] / wildBlockX-Y）。
        # 実機が現在ロードしている 2×2 RMD block ID（row order TL,TR,BL,BR）と、
        # その左上 chunk（signed center_origin）。境界外側 virtual chunk を seed grid
        # ではなくこの一次情報で埋めるための overlay ソース。live read 成功時のみ有効。
        self._live_wild_blocks: Optional[tuple[int, ...]] = None
        self._live_origin: Optional[tuple[int, int]] = None
        # 直近 build に使った表示プラン（再構築判定の比較対象）。
        self._built_live_origin: Optional[tuple[int, int]] = None
        self._built_live_blocks: Optional[tuple[int, ...]] = None
        self._n_chunks: int = _N_CHUNKS
        self._grid_size: int = _GRID_SIZE
        # 表示
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle:    Optional[float] = None
        self._compact_view: bool = False
        self._distinguish_road: bool = True   # 道(通行可)を壁と別色に
        self._show_edge: bool = True          # 壁の輪郭(edge voxel)を描画
        self._distinguish_edge: bool = True   # フェンス/生垣/庭を接続線で区別
        self._show_crops: bool = True         # 作物(トウモロコシ/畑)を面塗り＋マーク
        self._show_all_entrances: bool = True  # 家/酒場/神殿入口も赤（OFFでゲーム同様）
        self._show_static_flats: bool = True   # 木/茂み/岩等の地物マークを表示
        # 入口(MENU voxel)セルのキャッシュ（grid 同一・toggle 同一なら再計算しない）。
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        self._entrance_key: Optional[tuple[int, bool]] = None
        # 地物(flat)マークのキャッシュ（grid 同一なら再計算しない）。
        self._flat_marks: tuple[tuple[int, int, str], ...] = ()
        self._flat_marks_key: Optional[int] = None
        # フェンス/生垣/庭セルのキャッシュ（grid 同一なら再計算しない）。
        self._edge_marks: tuple[tuple[int, int, str], ...] = ()
        self._edge_marks_key: Optional[int] = None
        # 作物(トウモロコシ/畑)セルのキャッシュ（grid 同一なら再計算しない）。
        self._crop_marks: tuple[tuple[int, int, str], ...] = ()
        self._crop_marks_key: Optional[int] = None
        # フィールド入口 hint（player が進入可能 MENU セルに乗った/隣接した時に latch）。
        # 入場で suspend されると get_canvas_data が呼ばれず凍結され、入場後の MIF
        # 解決/city 誤認補正に使う（単一ソースは poll_controller 側）。
        self._field_entrance_ctx: Optional[FieldEntranceContext] = None
        # 進入可能 MENU セル（menuID 付き）のキャッシュ。
        self._enterable_cells: tuple[tuple[int, int, int], ...] = ()
        self._enterable_key: Optional[int] = None
        # 較正ログの重複抑止（同一入口で1回だけ出す）。
        self._logged_entrance_mif: Optional[str] = None
        self._logged_temple_name: Optional[str] = None
        # C3_ENTRY ログは「チャンク(grid origin)が変化した時だけ」出す（常時出力禁止）。
        # start() 跨ぎで保持し、同チャンクへの再認識では再出力しない。
        self._last_logged_origin: Optional[tuple[int, int]] = None
        # C3 認識ごとに初回 rt で seed/保持を 1 回だけ決める（_seed_pending）。
        self._seed_pending: bool = False
        # 施設/ダンジョン往復の判定用に、直前の wilderness 状態を start() 跨ぎで保持。
        self._last_rt: Optional[tuple[int, int]] = None
        self._last_wild_seed: Optional[int] = None

    # 軸選択 (旧 try_start 自前判定: C3 かつ非屋内) は classify_map_axis が
    # 単一決定する (= 判定は session に置かない)。

    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        # 軸切替で grid は作り直す（必要に応じ update() で構築）。
        # ただし chunk_tracker は reset しない: 施設/ダンジョン往復で wilderness が
        # 一瞬 stop/start されても直前 chunk を保てるようにする。seed/保持の判定は
        # update() の初回 poll（_seed_pending）で行う。
        self._wild_seed = None
        self._origin_chunk = None
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        # live overlay は毎 poll の live read で再設定する（stale 2×2 を持ち越さない）。
        self._live_wild_blocks = None
        self._live_origin = None
        # この C3 認識契機の seed 判定をアームする（log は chunk 変化時のみ）。
        self._seed_pending = True

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)
        # state 保持 (= 再進入時に同 seed/origin ならキャッシュ再利用)

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._player_x = ctx.player_tile_x
        self._player_y = ctx.player_tile_y
        self._angle = ctx.angle_deg
        self._compact_view = ctx.wilderness_compact_view
        self._distinguish_road = ctx.wild_distinguish_road
        self._show_edge = ctx.wild_show_edge
        self._distinguish_edge = ctx.wild_distinguish_edge
        self._show_crops = ctx.wild_show_crops
        self._show_all_entrances = ctx.wild_show_all_entrances
        self._show_static_flats = ctx.wild_show_static_flats

        if not ctx.location_name:
            return
        wild_seed = get_wilderness_seed(ctx.location_name)
        if wild_seed == 0:
            _log.warning(
                "wild: location_name='%s' is too short for wildSeed",
                ctx.location_name)
            return

        # rt_x/rt_z 遷移を tracker に取り込み、chunk_x/y を最新化する。
        # 3×3 chunks の NW corner を origin として player chunk を中央に置く。
        #
        # player_tile_x/y が None の場合は「位置不明」または「ダイアログ抑止中」
        # として扱う。既に grid と origin が確立済みなら維持し、city origin
        # fallback には戻さない (= ダイアログ中にフィールド表示位置がずれる
        # 回帰を防止)。
        if ctx.player_tile_x is not None and ctx.player_tile_y is not None:
            # 【本命】rt と center_origin を PlayerData の単一アトミック読みから取る。
            #   rt = wild{X,Y}//128（窓 local 0..127）、center_origin = wildBlockX/Y。
            # 同一スナップショットなので abs = origin*64 + rt が再センタリング境界でも
            # 連続になり、ctx.player_tile_x の凍結（map_safe ジャンプ拒否）に起因する
            # rt/origin desync（チャンク破綻）を構造的に回避する。
            ws = self._read_wild_state(ctx, wild_seed)
            if ws is not None:
                rt_x, rt_z, bx, by, wild_blocks = ws
                self._center_origin = (bx, by)
                # live 2×2 overlay は live read 成功時のみ有効（=現フィールドの active
                # PlayerData と seed 一致を検証済）。fallback/別 state には適用しない。
                self._live_wild_blocks = wild_blocks
                self._live_origin = (bx, by)
                # 凍結し得る ctx 値ではなく PlayerData の rt をマーカーに使う。
                self._player_x = rt_x
                self._player_y = rt_z
                if (self._chunk_tracker.chunk_x,
                        self._chunk_tracker.chunk_y) != (bx, by):
                    self._chunk_tracker.reset(bx, by)
                self._seed_pending = False
            else:
                # PlayerData が読めない/不正 → live overlay を落とす（stale 禁止）。
                self._live_wild_blocks = None
                self._live_origin = None
                # 【fallback】PlayerData が読めない/不正/seed 不一致（遷移中・別 state）の
                # 時のみ、従来の ctx.player_tile_x + seed 規則 + wrap 追跡を使う。
                #  - 施設/ダンジョン往復（同フィールド・退出位置が直前とほぼ同一）→
                #    直前 chunk を保持（reset しない）。
                #  - それ以外（街出口・ロード・別フィールド＝位置が飛ぶ）→ seed 規則。
                rt_x = int(ctx.player_tile_x)
                rt_z = int(ctx.player_tile_y)
                if self._seed_pending:
                    self._seed_pending = False
                    same_field = (self._last_wild_seed is not None
                                  and self._last_wild_seed == wild_seed)
                    near = (self._last_rt is not None
                            and abs(rt_x - self._last_rt[0]) <= _ROUNDTRIP_TOL
                            and abs(rt_z - self._last_rt[1]) <= _ROUNDTRIP_TOL)
                    if not (same_field and near):
                        seed_x = (CITY_ORIGIN_CHUNK_X if rt_x >= _HALF_CHUNK
                                  else CITY_ORIGIN_CHUNK_X - 1)
                        seed_y = (CITY_ORIGIN_CHUNK_Y if rt_z >= _HALF_CHUNK
                                  else CITY_ORIGIN_CHUNK_Y - 1)
                        self._chunk_tracker.reset(seed_x, seed_y)
                self._chunk_tracker.update(rt_x, rt_z)
                self._center_origin = (self._chunk_tracker.chunk_x,
                                       self._chunk_tracker.chunk_y)
            self._last_rt = (rt_x, rt_z)
            # 表示プランを 1 つだけ決める（origin・n_chunks・live overlay）。
            origin, n_chunks, live_origin, live_blocks = \
                self._compute_display_plan(rt_x, rt_z)
            # grid origin が変化した時だけ C3_ENTRY を出す（常時出力禁止）。
            if origin != self._last_logged_origin:
                self._last_logged_origin = origin
                self._log_c3_entry_coords(ctx, rt_x, rt_z, origin)
        elif self._origin_chunk is not None:
            # 既存 origin/プランを維持 (= None 座標で fallback に戻さない)
            origin = self._origin_chunk
            n_chunks = self._n_chunks
            live_origin = self._built_live_origin
            live_blocks = self._built_live_blocks
        else:
            # grid 未初期化時のみ city origin fallback で seed 計算する
            origin = (CITY_ORIGIN_CHUNK_X - 1, CITY_ORIGIN_CHUNK_Y - 1)
            n_chunks = _N_CHUNKS
            live_origin = None
            live_blocks = None

        # 再構築判定 (= seed / origin / n_chunks / live overlay の変化 or 未ロード)。
        # 境界またぎは origin が同一でも live 2×2 内容が変わるため、live overlay の
        # 変化も必ず判定に含める（origin 変化のみでは境界先が更新されない）。
        if not (wild_seed != self._wild_seed
                or origin != self._origin_chunk
                or n_chunks != self._n_chunks
                or live_origin != self._built_live_origin
                or live_blocks != self._built_live_blocks
                or self._walkable is None):
            return

        blocks = get_block_lists(ctx.analyzer)
        try:
            grid = build_wild_voxel_grid(
                wild_seed=wild_seed,
                blocks=blocks,
                player_voxel_x=0,   # origin_chunk 指定時は未使用
                player_voxel_y=0,
                origin_chunk=origin,
                flip_x=False,
                n_chunks=n_chunks,
                live_origin_chunk=live_origin,
                live_wild_blocks=live_blocks,
            )
        except Exception:  # noqa: BLE001
            _log.exception(
                "build_wild_voxel_grid failed (loc=%s seed=0x%08X)",
                ctx.location_name, wild_seed)
            return

        self._map1 = grid.map1
        self._flor = grid.flor
        self._walkable = (grid.map1 == 0) | (
            (grid.map1 & 0xF000) == 0x8000)
        # 全 cell 判明扱い (= reveal stencil なし)
        self._bitmap = np.full((grid.depth, grid.width), 3, dtype=np.uint8)
        self._wild_seed = wild_seed
        self._last_wild_seed = wild_seed  # 往復判定用（start() 跨ぎで保持）
        self._origin_chunk = origin
        self._n_chunks = n_chunks
        self._grid_size = n_chunks * _CHUNK
        self._built_live_origin = live_origin
        self._built_live_blocks = live_blocks

        src = get_cache_source() or "unset"
        _log.info(
            "wild: grid built loc=%s seed=0x%08X origin=(%d,%d) "
            "chunks=%s block_lists=%s normal_count=%d "
            "rt=(%s,%s) chunk_track=(%d,%d)",
            ctx.location_name, wild_seed, origin[0], origin[1],
            grid.chunk_ids, src, len(blocks.normal),
            ctx.player_tile_x, ctx.player_tile_y,
            self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)

    def _read_wild_state(self, ctx: MapContext, wild_seed: int
                         ) -> Optional[tuple[int, int, int, int,
                                             tuple[int, ...]]]:
        """PlayerData を単一アトミック読みし
        (rt_x, rt_z, wildBlockX, wildBlockY, wildBlocks[4]) を返す。

        rt と origin を必ず同一スナップショットから取ることが本メソッドの要点
        （rt/origin desync によるチャンク破綻を構造的に防ぐ）。
            rt_x = wildX // 128 / rt_z = wildY // 128（窓 local 0..127）
            origin = (wildBlockX, wildBlockY)（centered origin chunk）
        検証: wildSeed 一致（= この PlayerData が現在の active フィールド state・主検証）・
        rt 0..127・origin が grid±_WILD_ORIGIN_MARGIN の sanity 域内。外れたら None を
        返し呼び側 ctx fallback（遷移中の garbage / 別 state / 未展開を弾く）。

        **wildBlockX/Y は signed i16 で読む（field_boundary_*.json）**: 境界を西/北へ
        越えると centered origin chunk は 0x0000→0xFFFF＝ signed -1、さらに外へ歩くと
        -2,-3...（実機: 教会を出て西へ center_origin=-2）。これを「-1 だけ valid /
        -2 以下は garbage」と狭く弾くと、境界外の正当な state を reject→fallback が
        in-grid 座標を捏造し全く別マップになる。grid 外もそのまま signed で返す。
        """
        if ctx.analyzer is None or ctx.anchor is None:
            return None
        try:
            raw = ctx.analyzer.read_bytes(
                ctx.anchor + _PLAYERDATA_WILD_OFF, _PLAYERDATA_WILD_LEN)
        except Exception:  # noqa: BLE001
            return None
        if len(raw) < _PLAYERDATA_WILD_LEN:
            return None
        wild_x = int.from_bytes(raw[0:2], "little")
        wild_y = int.from_bytes(raw[2:4], "little")
        # wildBlocks[4]（live 2×2 window の RMD block ID・row order TL,TR,BL,BR）。
        wild_blocks = tuple(raw[4:8])
        # centered origin chunk は signed i16（境界外側 -1 = 0xFFFF を保持）。
        block_x = int.from_bytes(raw[8:10], "little", signed=True)   # 0x608
        block_y = int.from_bytes(raw[10:12], "little", signed=True)  # 0x60A
        seed = int.from_bytes(raw[22:26], "little")      # 0x616 - 0x600
        if seed != wild_seed:
            return None
        rt_x = wild_x // 128
        rt_z = wild_y // 128
        if not (0 <= rt_x <= _RT_MAX_DISPLAY and 0 <= rt_z <= _RT_MAX_DISPLAY):
            return None
        # プレイヤーは grid(0..63)の外まで歩けるため、境界外の負値/64 以上も valid。
        # 実機: 教会を出て西へ center_origin=-2（grid を 2 chunk 外）。-1 だけを valid
        # とすると -2 を reject→fallback が in-grid 座標を捏造し全く別マップになる。
        # 主検証は上の wildSeed 一致。ここは大きな i16 garbage だけ弾く。
        lo = -_WILD_ORIGIN_MARGIN
        hi = WILD_WIDTH - 1 + _WILD_ORIGIN_MARGIN
        if not (lo <= block_x <= hi and lo <= block_y <= hi):
            return None
        return rt_x, rt_z, block_x, block_y, wild_blocks

    def _compute_origin(self, rt_x: int, rt_z: int) -> tuple[int, int]:
        """player-centered 3×3 表示の NW corner = (actual_chunk - 1) を返す（signed）。

        center_origin chunk o（wildBlockX/Y 直読み or tracker fallback）は実 player
        chunk ではない。実 chunk は rt が半 chunk 境界(64)を跨ぐ分を足す:
            actual_chunk = o + (1 if rt >= 64 else 0)
        grid origin = actual_chunk - 1 で player chunk を 3×3 の中央に置く。

        0..63 に clamp しない: 境界を西/北へ越えた直後は actual_chunk-1 が -1 等の
        負値になり、これを 0 へ潰すと境界外側 chunk が描けず marker が 64 cell ずれる。
        範囲外 origin の扱い（clamp/overlay/n_chunks）は _compute_display_plan が決める。
        """
        o = self._center_origin or (
            self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)
        actual_cx = o[0] + (1 if rt_x >= _CHUNK else 0)
        actual_cy = o[1] + (1 if rt_z >= _CHUNK else 0)
        return actual_cx - 1, actual_cy - 1

    def _compute_display_plan(self, rt_x: int, rt_z: int
                              ) -> tuple[tuple[int, int], int,
                                         Optional[tuple[int, int]],
                                         Optional[tuple[int, ...]]]:
        """表示プラン (origin_chunk, n_chunks, live_origin, live_blocks) を 1 つ返す。

        分離化のゲート: live 2×2 overlay と signed origin は live read 成功時
        （= self._live_wild_blocks/_live_origin が有効・現フィールドの active
        PlayerData と seed 一致を検証済）にのみ適用する。fallback では従来どおり
        0..(WILD-_N_CHUNKS) に clamp し overlay なし。

        live 時の UI 方針:
          - 完全に内側（3×3 が 0..63 に収まる）/ 境界またぎ（一部 grid 外）:
            中央寄せ 3×3（origin = actual_chunk-1, signed）。外側は live 2×2 overlay、
            内側は seed grid、いずれにも無い範囲外は空 chunk で埋める（非対称表示可）。
          - 完全に外側（3×3 が全部 grid 外）: player 中央化を諦め、live 2×2 を
            素のまま表示（origin = live center_origin, n_chunks=2）。
        """
        centered = self._compute_origin(rt_x, rt_z)
        live_blocks = self._live_wild_blocks
        live_origin = self._live_origin
        if live_blocks is None or live_origin is None:
            # fallback: 従来挙動（clamp・overlay なし）。
            gx = max(0, min(WILD_WIDTH - _N_CHUNKS, centered[0]))
            gy = max(0, min(WILD_HEIGHT - _N_CHUNKS, centered[1]))
            return (gx, gy), _N_CHUNKS, None, None
        gx, gy = centered
        # 完全に外側 = 3×3 の全 chunk が 0..63 の外。
        fully_outside = (
            gx + _N_CHUNKS - 1 < 0 or gx > WILD_WIDTH - 1
            or gy + _N_CHUNKS - 1 < 0 or gy > WILD_HEIGHT - 1)
        if fully_outside:
            return live_origin, 2, live_origin, live_blocks
        return (gx, gy), _N_CHUNKS, live_origin, live_blocks

    def _wild_entrance_cells(self) -> tuple[tuple[int, int], ...]:
        """フィールドの建物/ダンジョン入口セルを返す（赤描画用）。

        常時赤＝クリプト/塔/ダンジョン（menuID {1,5,8,9}・vanilla 自動マップ相当）。
        拡張表示(`_show_all_entrances`)時は家/酒場/神殿/街門（menuID {2,3,4,6,7}）も
        追加する。テクスチャ index は荒地 INF から導出した full voxelTextures index
        で、detect_menu_cells の `mostSigByte-1` と同基準。
        grid 同一・モード同一ならキャッシュを返す。
        """
        if self._map1 is None:
            return ()
        key = (id(self._map1), self._show_all_entrances)
        if key != self._entrance_key:
            from services.city_voxel_assembler import detect_menu_cells
            game, extended = _wild_menu_texture_sets()
            tex_set = extended if self._show_all_entrances else game
            self._entrance_cells = tuple(
                detect_menu_cells(self._map1, set(tex_set)))
            self._entrance_key = key
        return self._entrance_cells

    def _wild_flat_marks(self) -> tuple[tuple[int, int, str], ...]:
        """フィールドの地物(flat)マーク `(x, y, 種別)` を返す（木/茂み/岩/墓/廃墟等）。

        MAP1 の flat(上位ニブル 0x8)を荒地 INF @FLATS の名前で種別に分類する。
        トグル OFF 時は空。grid 不変ならキャッシュを返す。
        """
        if self._map1 is None or not self._show_static_flats:
            return ()
        key = id(self._map1)
        if key != self._flat_marks_key:
            cat_map = get_wild_flat_category_map()
            self._flat_marks = extract_flat_marks(self._map1, cat_map)
            self._flat_marks_key = key
        return self._flat_marks

    def _wild_edge_marks(self) -> tuple[tuple[int, int, str], ...]:
        """フィールドのフェンス/生垣/庭セル `(x, z, 区分)` を返す。

        edge/transparent/wall 等の全 voxel 種別を荒地 INF @WALLS 名で分類する。
        塗りつぶさず隣接接続で線描画する用（canvas が当該セルの塗りをスキップ）。
        「壁の輪郭を表示(show_edge)」かつ「区別(distinguish_edge)」の両 ON 時のみ。
        OFF 時は空＝従来どおりセル塗り（または非表示）。grid 不変ならキャッシュ。
        """
        if (self._map1 is None or not self._show_edge
                or not self._distinguish_edge):
            return ()
        key = id(self._map1)
        if key != self._edge_marks_key:
            from services.wild_edges import (
                get_wild_edge_category_map, extract_edge_marks)
            cat_map = get_wild_edge_category_map()
            self._edge_marks = extract_edge_marks(self._map1, cat_map)
            self._edge_marks_key = key
        return self._edge_marks

    def _wild_crop_marks(self) -> tuple[tuple[int, int, str], ...]:
        """フィールドの作物セル `(x, z, 区分=corn/farm)` を返す。

        トウモロコシ(edge `twcorn`)・畑(solid wall `twfarm`)を荒地 INF @WALLS 名で
        分類する。canvas が作物色で塗り＋マーク(穂/横畝)を重ねる。トグル OFF 時は空
        ＝従来どおり壁色塗り。grid 不変ならキャッシュ。
        """
        if self._map1 is None or not self._show_crops:
            return ()
        key = id(self._map1)
        if key != self._crop_marks_key:
            from services.wild_edges import (
                get_wild_crop_category_map, extract_crop_marks)
            cat_map = get_wild_crop_category_map()
            self._crop_marks = extract_crop_marks(self._map1, cat_map)
            self._crop_marks_key = key
        return self._crop_marks

    def _enterable_menu_cells(self) -> tuple[tuple[int, int, int], ...]:
        """進入可能 MENU セル `(x, z, menu_id)` を返す（クリプト/神殿/塔/ダンジョン）。

        各セルの texture index を荒地 INF の menuID へ逆引きする。grid 不変なら
        キャッシュを返す（_wild_entrance_cells と同じ texture 抽出規則）。
        """
        if self._map1 is None:
            return ()
        key = id(self._map1)
        if key != self._enterable_key:
            tex2menu = _wild_texture_to_menu_id()
            enter_tex = {tex: mid for tex, mid in tex2menu.items()
                         if mid in _WILD_ENTERABLE_MENU_IDS}
            cells: list[tuple[int, int, int]] = []
            m1 = self._map1
            h, w = m1.shape
            for z in range(h):
                for x in range(w):
                    v = int(m1[z, x])
                    if v == 0:
                        continue
                    high = (v >> 12) & 0x0F
                    most = (v >> 8) & 0xFF
                    least = v & 0xFF
                    if high == 0xA:
                        tex = (least & 0x3F) - 1
                    elif most == least and most != 0:
                        tex = most - 1
                    else:
                        continue
                    mid = enter_tex.get(tex)
                    if mid is not None:
                        cells.append((x, z, mid))
            self._enterable_cells = tuple(cells)
            self._enterable_key = key
        return self._enterable_cells

    def _resolve_field_door_mif(self, abs_x: int, abs_y: int,
                                menu_id: int) -> Optional[str]:
        """フィールド扉の絶対 wild voxel 座標から Interior MIF 名を解決する。

        ゲームと同じ door→MIF 計算（OTA getDoorVoxelMifName）。crypt/temple/tower は
        ruler_seed 不要・扉座標のみで variant 決定。dungeon は固定 MIF なし→None。

        座標基準は OTA MapGeneration.cpp の荒地ループで確定:
          levelX = map1Z, levelZ = map1X → worldVoxelToOriginalVoxel((levelX,levelZ))
          = (levelZ, levelX) = (map1X, map1Z) を getDoorVoxelMifName(x, y) へ渡す。
        本実装の abs_x は MAP1 列(map1X=WE)、abs_y は MAP1 行(map1Z=SN)なので、
        **noswap = get_door_voxel_mif_name(abs_x, abs_y)** が OTA 準拠（実機: 地下室
        cell=(74,110)→WCRYPT6。神殿は swap/noswap 同値で TEMPLE2＝判別不能だった）。
        実機での MIF 一致は引き続き観測ベースで較正する。
        """
        try:
            from services.arena_level_utils import get_door_voxel_mif_name
            from services.arena_voxel_utils import MapType
            from services.arena_types import ArenaCityType
            return get_door_voxel_mif_name(
                abs_x, abs_y, menu_id, 0, False,
                ArenaCityType.CITY_STATE, MapType.WILDERNESS)
        except Exception:  # noqa: BLE001
            _log.exception("field door mif resolve failed")
            return None

    def _update_field_entrance_hint(self, local_x: Optional[int],
                                    local_y: Optional[int]) -> None:
        """player が進入可能 MENU セルに乗った/隣接した時に入口 hint を latch する。

        フィールドのクリプト/神殿/塔/ダンジョンへ進入した直後は LiveMifName が
        stale な VILLAGE*.MIF になり city 誤認するため、進入直前に扉座標から MIF を
        解決して latch し、入場後の場所解決（poll_controller の単一ソース）へ渡す
        。距離4以内（5Hz poll 取りこぼし・間欠 routing 対策）で hint を
        立て、離れたら None に戻す。入場で suspend されると本メソッドは呼ばれず凍結。
        """
        if local_x is None or local_y is None or self._origin_chunk is None:
            return
        # 最も近い進入可能セルを採用。施設は街中心から離れているため、街進入前に
        # latch は clear され誤上書きは起きない。
        nearest = None
        best_d = 99
        for cx, cz, mid in self._enterable_menu_cells():
            d = max(abs(cx - local_x), abs(cz - local_y))
            if d <= 4 and d < best_d:
                best_d = d
                nearest = (cx, cz, mid)
        if nearest is None:
            self._field_entrance_ctx = None
            self._logged_entrance_mif = None
            return
        cx, cz, mid = nearest
        abs_x = self._origin_chunk[0] * _CHUNK + cx
        abs_y = self._origin_chunk[1] * _CHUNK + cz
        mif = self._resolve_field_door_mif(abs_x, abs_y, mid)
        name_en, name_ja = self._resolve_field_facility_name(abs_x, abs_y, mid)
        self._field_entrance_ctx = FieldEntranceContext(
            interior_mif_name=mif,
            menu_label=_MENU_LABELS.get(mid, str(mid)),
            name_en=name_en, name_ja=name_ja)
        # 較正ログ（同一入口で1回）。実機で実際にロードされた MIF と突き合わせる。
        if mif != self._logged_entrance_mif:
            self._logged_entrance_mif = mif
            self._log_field_entrance_calibration(abs_x, abs_y, cx, cz, mid, mif)

    def _resolve_field_facility_name(self, abs_x: int, abs_y: int,
                                     menu_id: int) -> tuple[str, Optional[str]]:
        """フィールド施設の固有名を生成する（命名対象は宿屋と神殿のみ）。

        宿屋(menu_id=3): **OpenTESArena 原典どおりの pure chunk seed** で生成する
          （実機 Moonguard "King's Skull" と一致）。
        神殿(menu_id=4): **実機観測優先の calibrated(wildSeed 加算) で生成する**
          （実機 "Brotherhood of Mercy" と一致するが OpenTESArena 原典ではない）。
        ※宿屋/神殿は同一チャンクでも別式でしか実機一致せず、正しい一般式は未確定。
        地下室/塔/ダンジョン/家は無名＝("", None)。block(we,sn)=abs voxel // 64。
        """
        we, sn = abs_x // _CHUNK, abs_y // _CHUNK
        try:
            if menu_id == 3:  # 宿屋: OpenTESArena 忠実(pure chunk seed)
                from services.building_name_generator import (
                    generate_wild_tavern_name_opentes,
                    make_wild_chunk_name_seed)
                from services.dynamic_translation import translate_tavern
                tav = generate_wild_tavern_name_opentes(we, sn)
                tr = translate_tavern(tav)
                if (tr.en or "") != getattr(self, "_logged_tavern_name", None):
                    self._logged_tavern_name = tr.en or ""
                    _log.warning(
                        "FIELD_TAVERN_NAME[OpenTES] block(WE=%d,SN=%d) "
                        "seed=0x%08X prefix=%d suf=%d en=%r ja=%r",
                        we, sn, make_wild_chunk_name_seed(we, sn),
                        tav.prefix_index, tav.suffix_index, tr.en, tr.ja)
                return (tr.en or "", tr.ja)
            if menu_id == 4:  # 神殿: 実機観測優先(calibrated/OpenTES原典ではない)
                wild_seed = self._wild_seed or 0
                from services.building_name_generator import (
                    generate_wild_temple_name_calibrated,
                    make_wild_temple_name_seed_calibrated)
                from services.dynamic_translation import translate_temple
                tname = generate_wild_temple_name_calibrated(we, sn, wild_seed)
                tr = translate_temple(tname)
                if (tr.en or "") != getattr(self, "_logged_temple_name", None):
                    self._logged_temple_name = tr.en or ""
                    _log.warning(
                        "FIELD_TEMPLE_NAME[calibrated] block(WE=%d,SN=%d) "
                        "wildSeed=0x%08X seed=0x%08X model=%d suf=%d en=%r ja=%r",
                        we, sn, wild_seed,
                        make_wild_temple_name_seed_calibrated(we, sn, wild_seed),
                        tname.model, tname.suffix_index, tr.en, tr.ja)
                return (tr.en or "", tr.ja)
            return ("", None)  # 地下室/塔/ダンジョン/家は無名
        except Exception:  # noqa: BLE001
            _log.exception("field facility name resolve failed")
            return ("", None)

    def _log_field_entrance_calibration(self, abs_x: int, abs_y: int,
                                        cx: int, cz: int, menu_id: int,
                                        mif: Optional[str]) -> None:
        """フィールド扉 MIF 解決の較正ログ（実機の実 MIF と突き合わせ用）。

        座標基準が未確定のため、複数候補基準での解決 MIF を併記する。実機で実際に
        ロードされた MIF と一致する基準を採用する（観測・仮説扱い）。
        """
        from services.arena_level_utils import get_door_voxel_mif_name
        from services.arena_voxel_utils import MapType
        from services.arena_types import ArenaCityType
        cand = {}
        for name, (x, y) in {
            "noswap(abs_x,abs_y)=OTA採用": (abs_x, abs_y),
            "swap(abs_y,abs_x)": (abs_y, abs_x),
        }.items():
            try:
                cand[name] = get_door_voxel_mif_name(
                    x, y, menu_id, 0, False,
                    ArenaCityType.CITY_STATE, MapType.WILDERNESS)
            except Exception:  # noqa: BLE001
                cand[name] = "<err>"
        _log.warning(
            "FIELD_ENTRANCE menu=%s(id=%d) cell=(%d,%d) abs=(%d,%d) "
            "mif=%s || cand: %s",
            _MENU_LABELS.get(menu_id, str(menu_id)), menu_id, cx, cz,
            abs_x, abs_y, mif,
            " / ".join(f"{k}={v}" for k, v in cand.items()))

    def field_entrance_hint(self) -> Optional[FieldEntranceContext]:
        """latch 済みのフィールド入口 hint を返す（suspend 中は凍結値）。"""
        return self._field_entrance_ctx

    def _log_c3_entry_coords(self, ctx: MapContext,
                             rt_x: int, rt_z: int,
                             origin: tuple[int, int]) -> None:
        """C3 認識時の初回座標スナップショットを log（観測・絶対チャンク解析用）。

        C2→C3 / ロード / 施設 L3 退出→C3 L2 の各契機で 1 回ずつ出力する。
        絶対チャンクをメモリ直読みできる source を 3 出口クロス差分で特定するための
        生 byte 候補も併記する。
        """
        o_x = self._chunk_tracker.chunk_x
        o_y = self._chunk_tracker.chunk_y
        ac_x = o_x + (1 if rt_x >= _CHUNK else 0)
        ac_y = o_y + (1 if rt_z >= _CHUNK else 0)
        mk_x = (o_x * _CHUNK + rt_x) - origin[0] * _CHUNK
        mk_y = (o_y * _CHUNK + rt_z) - origin[1] * _CHUNK
        cand = ""
        if ctx.analyzer is not None and ctx.anchor is not None:
            try:
                parts = []
                for off, name in _C3_ENTRY_CANDIDATES:
                    raw = ctx.analyzer.read_bytes(ctx.anchor + off, 4)
                    u16 = int.from_bytes(raw[:2], "little")
                    u32 = int.from_bytes(raw, "little")
                    parts.append("%s@0x%04X=u16:%d/u32:%d" % (name, off, u16, u32))
                cand = " | ".join(parts)
            except Exception:  # noqa: BLE001
                cand = "<cand read error>"
        # assist_debug.log は WARNING 以上のみ記録するため warning で出す（観測用）。
        _log.warning(
            "C3_ENTRY loc=%s rt=(%d,%d) hi=(%d,%d) center_origin=(%d,%d) "
            "actual_chunk=(%d,%d) voxel=(%d,%d) grid_origin=(%d,%d) "
            "marker=(%d,%d) || %s",
            ctx.location_name, rt_x, rt_z,
            (rt_x >> 8) & 0xFF, (rt_z >> 8) & 0xFF,
            o_x, o_y, ac_x, ac_y, rt_x % _CHUNK, rt_z % _CHUNK,
            origin[0], origin[1], mk_x, mk_y, cand)

    def get_canvas_data(self) -> CanvasData:
        # 原典由来モデル: rt は中心寄せ表示窓 local（32..95）なので
        #   abs_original = centered_origin_chunk * 64 + rt
        # で絶対 voxel を復元し、grid origin (= actual_chunk - 1) を引いて marker
        # local を得る。clamp が掛かった外周でも abs - origin*64 で正しく出る。
        local_x: Optional[int] = None
        local_y: Optional[int] = None
        if (self._player_x is not None and self._player_y is not None
                and self._origin_chunk is not None):
            rt_x = int(self._player_x)
            rt_z = int(self._player_y)
            # center_origin は wildBlockX/Y 直読み（本命）。未設定の低レベル経路では
            # tracker へ fallback（_compute_origin と同一の解決）。
            o = self._center_origin or (
                self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)
            if (0 <= rt_x <= _RT_MAX_DISPLAY
                    and 0 <= rt_z <= _RT_MAX_DISPLAY):
                abs_x = o[0] * _CHUNK + rt_x
                abs_y = o[1] * _CHUNK + rt_z
                lx = abs_x - self._origin_chunk[0] * _CHUNK
                ly = abs_y - self._origin_chunk[1] * _CHUNK
                # grid サイズは表示プランの n_chunks で変わる（完全外側時 128）。
                if 0 <= lx < self._grid_size and 0 <= ly < self._grid_size:
                    local_x = lx
                    local_y = ly

        # player が進入可能 MENU セル（クリプト/神殿/塔/ダンジョン）に乗った/
        # 隣接した時に入口 hint を latch（入場で suspend されると凍結）。
        self._update_field_entrance_hint(local_x, local_y)

        return CanvasData(
            walkable=self._walkable,
            map1=self._map1,
            flor=self._flor,
            bitmap_grid=self._bitmap,
            notes=[],
            player_x=local_x,
            player_y=local_y,
            player_angle_deg=self._angle,
            level_up_index=None,
            level_down_index=None,
            entrance_cells=self._wild_entrance_cells(),  # 建物/ダンジョン入口=赤
            flat_marks=self._wild_flat_marks(),  # 木/茂み/岩等の地物マーク
            edge_marks=self._wild_edge_marks(),  # フェンス/生垣/庭=接続線
            crop_marks=self._wild_crop_marks(),  # トウモロコシ/畑=面塗り＋マーク
            wild_show_crops=self._show_crops,    # 畑の地面(tznfield 床)も土色に
            is_wilderness=True,  # 道/特殊地形を wild_wall 色で描画
            chunk_origin=self._origin_chunk,
            wilderness_compact_view=self._compact_view,
            wild_distinguish_road=self._distinguish_road,
            wild_show_edge=self._show_edge,
            hidden_door_ids=frozenset(),
            menu_texture_indices=frozenset(),
        )

    def reset_progress(self) -> None:
        # wilderness は全 cell 判明扱い → bitmap 再構築のみ
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)


__all__ = ["WildernessMapSession"]
