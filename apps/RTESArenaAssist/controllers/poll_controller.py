"""controllers/poll_controller.py — メインポーリングループ

assist_window.AssistWindow から `_poll()` を切り出したコントローラ。
振る舞いは一切変更していない（mechanical な self → w 置換のみ）。

window 側の状態（_chargen_*, _b30_*, _b32_* 等のフラグ群）は従来通り
AssistWindow が保持し、本コントローラからは self._w 経由で参照する。
"""
from __future__ import annotations

import os
import struct
import time
import logging

import assist_settings as settings
from assist_log import recog as _recog
import i18n_helper as i18n
import inf_text_lookup as itl
from display_intent import PollFrame
from hierarchy_state import (
    facility_owners_for_session,
    HierarchyRecognitionInput,
    SeparationHierarchy,
)
from normal_play.base_location.base_location_view import (
    resolve_area_with_indoor_fallback as _resolve_area_with_indoor_fallback,
)
from controllers.chargen_helpers import (
    _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN,
    _CHARGEN_GOYENOW_PREFIX,
    _CHARGEN_GOYENOW_SCAN_START, _CHARGEN_GOYENOW_SCAN_END,
    _is_garbage_npc_buffer,
)
from top_level.normal_play_state import poll_sessions as _poll_normal_play_sessions
from top_level.top_level_dispatcher import (
    build_session_context as _build_session_context,
    current_state as _current_top_level,
)
from controllers.poll_diag import (
    _checkpoint,
    _phase_record,
    _phase_start,
)

_log = logging.getLogger("poll_controller")
_wild_diag_log = logging.getLogger("wild_diag")


def _restore_chargen_cleared_maps(w, tab_map) -> None:
    """chargen clear で非表示にした map 表示シェルを normal-play で戻す。"""
    try:
        tab_map.restore_map()
    except (AttributeError, RuntimeError):
        _log.exception("tab_map.restore_map failed")
    try:
        w._tab_translate.fallback_map_tab().restore_map()
    except (AttributeError, RuntimeError):
        _log.exception("fallback_map.restore_map failed")


# wilderness 座標診断: 1 voxel 移動で chunks が完全変化する症状
# (= rt_x/rt_z 絶対 voxel 仮説の破綻) の原因特定用。複数 offset 候補を
# u16/u32 で読み、変化時のみ log する。
#
# GAMESTATE_OFFSET + 0x08CA 経由の PlayerX/Y/Z 読み出しは **撤回**。分析により
# `GAMESTATE_OFFSET` は ASCII アセット名領域を指しており、観測値
# (= 17998/13312) は座標ではなくアセット名断片 (= 'NF' 等の u16 解釈) だった。
# 本リストは anchor 直 offset のみに戻し、`GAMESTATE_OFFSET + 0x08CA` を
# 座標根拠にする実装は禁止。正規対応は別観測で wilderness 絶対
# voxel の正しい source を memdiff で探索する。
_WILD_DIAG_CANDIDATES = [
    # (offset, label)
    (0xA854, "rt_x"),
    (0xA856, "rt_z"),
    (0xA858, "rt_a858"),
    (0xA85A, "rt_a85a"),
    (0xA84C, "rt_a84c"),
    (0xA84E, "rt_a84e"),
    (0xA850, "rt_a850"),
    (0xA852, "rt_a852"),
]

_wild_diag_prev: dict[int, tuple[int, int]] = {}
_wild_diag_hex_dumped: bool = False


def _dump_wild_diag_hex(analyzer, anchor: int) -> None:
    """wilderness 進入時 1 回だけ player 座標周辺の hex dump を log。

    GAMESTATE_OFFSET 領域は ASCII アセット名のため hex dump 対象から外す。
    anchor + 0xA840..0xA870 (= rt_x/z 周辺 48 byte)
    のみを 16 byte 行で出力。
    """
    global _wild_diag_hex_dumped
    if _wild_diag_hex_dumped or anchor is None:
        return
    if analyzer is None:
        return
    _wild_diag_hex_dumped = True
    try:
        raw = analyzer.read_bytes(anchor + 0xA840, 48)
    except OSError:
        return
    for line_off in range(0, len(raw), 16):
        chunk = raw[line_off:line_off + 16]
        _wild_diag_log.info(
            "wild_diag hex around_rt_xz +0x%04X: %s",
            0xA840 + line_off,
            " ".join(f"{b:02X}" for b in chunk))


def _poll_wild_diagnostic(analyzer, anchor: int) -> None:
    """wilderness 中の player 座標候補を全 offset 読んで変化時のみ log。

    GAMESTATE_OFFSET 経由の読み出しは撤回。
    anchor 直 offset のみで観測する。正規 wilderness 座標 source は別観測で
    探索予定 (= 本リストは現状の候補確認用)。
    """
    if analyzer is None or anchor is None:
        return
    for off, label in _WILD_DIAG_CANDIDATES:
        try:
            raw = analyzer.read_bytes(anchor + off, 4)
        except OSError:
            continue
        if not raw or len(raw) < 4:
            continue
        u16 = int.from_bytes(raw[:2], "little")
        u32 = int.from_bytes(raw, "little")
        prev = _wild_diag_prev.get(off)
        cur = (u16, u32)
        if prev == cur:
            continue
        _wild_diag_prev[off] = cur
        delta_u16 = (u16 - prev[0]) if prev else None
        _wild_diag_log.info(
            "wild_diag ax+0x%04X %-12s u16=%5d (Δ%s) u32=%d hex=%s",
            off, label, u16,
            f"{delta_u16:+d}" if delta_u16 is not None else "?",
            u32, raw.hex())


# 画面確定 (_screen_id_stable) 駆動の panel_mode 提案の優先度。
# 背景翻訳 push (priority=0) に勝たせ、防御的再アサートを不要にする。
# img_screen_controller の equipment/spell 画面提案 (priority=30) と同一ティア。
_SCREEN_PANEL_PRIORITY = 30


def _normal_play_idle_panel_mode() -> str:
    """通常プレイの翻訳なし idle 時に戻すパネル mode。"""
    fallback = settings.get("translate_fallback_screen", "map")
    if fallback == "map":
        return "fallback_map"
    if fallback == "status":
        return "fallback_status"
    return "translate"


def _detect_save_file_write(w) -> bool:
    """SAVEGAME.0N / SAVEENGN.0N の mtime 進行 (= セーブ確定) を検知する。

    セーブ画面表示中(確定前)は書込が無く False。スロットへ保存を確定した瞬間に
    のみ True を返す(同名上書きも mtime で拾える)。
    """
    save_dir = str(settings.get("save_dir", ""))
    if not save_dir or not os.path.isdir(save_dir):
        return False
    sig: dict[str, int] = {}
    try:
        for f in os.listdir(save_dir):
            up = f.upper()
            if up.startswith("SAVEGAME.0") or up.startswith("SAVEENGN.0"):
                try:
                    sig[up] = os.stat(os.path.join(save_dir, f)).st_mtime_ns
                except OSError:
                    pass
    except OSError:
        return False
    prev = getattr(w, "_loadscreen_save_mtimes", None)
    w._loadscreen_save_mtimes = sig
    if prev is None:
        return False
    return sig != prev


def _release_completed_load_screen_owner(
        w, *, img_name: str, save_detected: bool, loading_active: bool,
        loading_post_settle: bool) -> None:
    """セーブ/ロード画面終了後に残った load_screen owner だけを解放する。

    L2/L3 の汎用 reconcile ではなく、ロード画面表示単位の終了処理。
    セーブ/ロード画面表示中(img=LOADSAVE.IMG)と post-load settle 中は維持する。

    残留対策: SCREEN_IMG(img_name) はセーブ後にダンジョン
    3D 表示へ戻っても LOADSAVE.IMG が残留する(3D 表示は IMG を持たない)。一方
    セーブ画面表示中とセーブ後はどちらも img=LOADSAVE / menu_active バウンスで
    区別できない。確実に区別できるのは「セーブ確定(*.0N 書込)」であり、これを
    検知したら img が LOADSAVE のまま残留していても解放する。
    """
    if _current_top_level(w) != "normal-play":
        return
    if (getattr(w, "_panel_owner", "") or "") != "load_screen":
        return
    # セーブ画面表示中(確定前)は維持。セーブ確定を検知したら残留 img でも解放。
    if (img_name or "").upper() == "LOADSAVE.IMG" and not save_detected:
        return
    if loading_active or loading_post_settle:
        return
    try:
        w._ui_router.claim_owner("", mode=_normal_play_idle_panel_mode())
    except (AttributeError, RuntimeError) as exc:
        _log.debug("load_screen owner release skipped: %s", exc)


# Interior MIF 名から店種別ラベルを返す。未対応の MIF は空文字。
_SHOP_KIND_LABELS_JA: dict[str, str] = {
    "TAVERN":  "宿屋",
    "TEMPLE":  "神殿",
    "EQUIP":   "武具屋",
    "MAGES":   "魔法ギルド",
    "PALACE":  "宮殿",
    "TOWNPAL": "宮殿",
    "VILPAL":  "宮殿",
    "NOBLE":   "貴族邸",
    "HOUSE":   "家",
    # フィールド施設（C3 配下 L3）。
    "WCRYPT":  "地下室",
    "TOWER":   "塔",
    "BS":      "家",      # フィールドの家（door→MIF prefix は "BS"）。
}


def _interior_kind_label(interior_mif_name: str | None) -> str:
    if not interior_mif_name:
        return ""
    u = interior_mif_name.upper()
    for prefix, label in _SHOP_KIND_LABELS_JA.items():
        if u.startswith(prefix):
            return label
    return ""


def _format_place_text(
    state: dict,
    in_interior: bool,
    interior_mif_name: str | None,
    area: str,
    player_floor: int,
    interior_facility_name: str | None = None,
    include_weather: bool = True,
) -> str:
    """マップタブ上部に表示する場所テキストを生成する。

    形式:
      - ダンジョン: "場所名  NF" (= N は 1 始まり)
      - 街:         "街名  天気"
      - 店内 (固有名あり): "街名 - 固有名 (店種別)  NF"
      - 店内 (固有名なし): "街名 - 店種別  NF" (= 貴族邸 / 家 / 宮殿 等)
      - フィールド: "地域  天気"

    include_weather=False は翻訳ログの場所表記用。天候は時々刻々変わり同じ場所が
    別表記になりフィルタが分断されるため、街/フィールドの天候付与を抑止する。
    """
    location = state.get("location") or ""
    weather = (state.get("weather") or "") if include_weather else ""
    try:
        floor_n = int(player_floor) + 1
    except (TypeError, ValueError):
        floor_n = None
    floor_s = f"  {floor_n}F" if floor_n is not None and floor_n > 0 else ""

    if in_interior:
        kind = _interior_kind_label(interior_mif_name)
        name = (interior_facility_name or "").strip()
        if name and kind:
            return f"{location} - {name} ({kind}){floor_s}".strip()
        if name:
            return f"{location} - {name}{floor_s}".strip()
        if kind:
            return f"{location} - {kind}{floor_s}".strip()
        return f"{location}{floor_s}".strip()

    if area == "dungeon":
        return f"{location}{floor_s}".strip()
    if weather:
        return f"{location}  {weather}".strip()
    return location


# 純粋関数 (= MIF 名 + 補助 memory read で area 判定) は play_area_classifier
# に集約済み。本ファイルからは re-export で互換維持。
from play_area_classifier import detect_play_area as _detect_play_area  # noqa: E402

# wilderness 判定用 1 byte フラグ (= anchor 相対オフセット、indicator/suffix
# 経路の互換のため残す)。
_WILDERNESS_FLAG_OFFSET = 0x4BD0

# 宿屋サブ画面のフォアグラウンド判別子 (実機 memdiff 観測、忍び込み 3 capture)。
#   +0x8F6E u16 LE = 現在前景ビュー記述子 (= screen_detector.SPELL_VIEW_OFFSET と
#       同一領域)。店主メニュー前景と確認/結果ポップアップ前景で値が変わる。
#       絶対値はロード毎に変わるため base 差で解釈する想定 (= spell_view と同方式)。
#       観測: メニュー=0x179C / ポップアップ(確認・結果)=0x1D24。
#   +0x8F74 u8 = 同領域フラグ。観測: メニュー=0x51 / ポップアップ=0x00。
# 現状は値の収集と認識状態の可視化のためのデバッグ計測のみ。判定本体は
# まだ IMG 名 / current_ptr 経路のまま (= 値の汎用性を実機ログで確認してから接続)。
_TAVERN_VIEW_DESC_OFFSET = 0x8F6E
_TAVERN_VIEW_FLAG_OFFSET = 0x8F74


def _fmt_hex_byte(value) -> str:
    if value is None:
        return "None"
    try:
        return f"0x{int(value) & 0xFF:02X}"
    except (TypeError, ValueError):
        return repr(value)


def _active_session_name_for_log(w) -> str:
    try:
        active = w._session_manager.active_session()
    except (AttributeError, RuntimeError):
        return ""
    return getattr(active, "name", "") if active is not None else ""


def _clear_stopped_facility_display(w, session_name: str) -> None:
    """L3 施設会話終了時だけ、施設 L4 表示 owner を片付ける。"""
    try:
        owner = w._ui_router.current_owner()
    except (AttributeError, RuntimeError):
        owner = getattr(w, "_panel_owner", "") or ""
    if owner not in facility_owners_for_session(session_name):
        return
    key = (
        session_name,
        owner,
        getattr(w, "_screen_id_prev", None),
        getattr(w, "_img_name_prev", "") or "",
    )
    if key != getattr(w, "_b351_facility_stop_clear_key", None):
        w._b351_facility_stop_clear_key = key
        _log.info(
            "facility session stopped -> clearing L4 display "
            "(session=%s owner=%r screen=%r img=%r)",
            session_name, owner,
            getattr(w, "_screen_id_prev", None),
            getattr(w, "_img_name_prev", "") or "")
    try:
        w._ui_router.clear_if_owner(
            owner,
            mode="translate",
            # owner 分離: ② 道案内一覧(npc_conversation)・③ 一方向msg
            # (npc_message) も place_list クリア条件に含める (npc_dialog と同等)。
            clear_place_list=(owner in (
                "npc_dialog", "npc_conversation", "npc_message")))
    except (AttributeError, RuntimeError) as exc:
        _log.debug("facility stop display clear skipped: %s", exc)


def _poll_update_npc_conversation_latch(
        w, *, _facility_active_now, _facility_just_started, _npc_phase_early):
    """通常 NPC 会話 latch を更新する (poll god-method から純抽出・挙動不変)。

    施設会話 latch on / loading 中は更新を抑止し、NPC_PHASE に応じて
    w._npc_conversation_active を遷移させる。True→False 遷移時に NPC dialog
    表示をクリアする。副作用は w.* のみで出力ローカルは無い
    (ブロックローカル _npc_state_freeze/_npc_state_prev は関数内に閉じる)。
    """
    from arena_bridge import (
        NPC_PHASE_ASKING, NPC_PHASE_IDLE, NPC_PHASE_RESPONDING,
    )
    # 通常 NPC 会話 latch の更新 — 施設会話 latch on 中は抑止
    # (tavern だけでなく facility (tavern/temple) 共通の gate に汎用化)
    # ロード中状態判定抑止も従来通り。
    #
    # +0xA845 は施設会話中に pointer 上位 byte として振る舞う場面がある。
    # ただし通常 poll 中に panel_owner から別判定軸を freeze するのは
    # 分離原則に反するため、実状態である loading /
    # facility active だけを抑止条件にする。
    _npc_state_freeze = (
        w._loading_state_active
        or _facility_active_now
    )
    _npc_state_prev = w._npc_conversation_active
    if (_facility_just_started
            and w._npc_conversation_active):
        # 施設会話 latch on 切替時に残置した NPC latch を off
        _log.info(
            "facility session started → NPC conversation latch "
            "forced to False")
        w._npc_conversation_active = False
        _npc_state_prev = False
    if not _npc_state_freeze and _npc_phase_early is not None:
        if _npc_phase_early == NPC_PHASE_ASKING:
            if not _npc_state_prev:
                _log.info(
                    "NPC conversation state: False → True "
                    "(ASKING observed)")
            w._npc_conversation_active = True
        elif _npc_phase_early == NPC_PHASE_IDLE:
            if _npc_state_prev:
                _log.info(
                    "NPC conversation state: True → False "
                    "(IDLE observed)")
            w._npc_conversation_active = False
        elif _npc_phase_early != NPC_PHASE_RESPONDING:
            if w._npc_phase_unknown_prev != _npc_phase_early:
                _log.warning(
                    "NPC_PHASE unknown value: 0x%02X",
                    _npc_phase_early)
                w._npc_phase_unknown_prev = _npc_phase_early
    # NPC 会話状態 True → False 遷移時のクリア (= 既存の表示クリアと同等)。
    # 表示経路より前で行うことで、
    # 同 poll 内の後段の表示処理に正しい状態が反映される。
    if _npc_state_prev and not w._npc_conversation_active:
        try:
            w._img_screen._reset_npc_dialog_display()
        except (AttributeError, RuntimeError) as exc:
            _log.debug(
                "NPC state transition reset failed: %s", exc)


def _poll_log_hierarchy_recognition_post_session(
        w, *, _resolved_area, in_interior, _npc_phase_early, mif_name,
        _img_name_early, interior_mif_name, interior_raw):
    """post_session 段階の階層認識診断ログを出力する (poll から純抽出・挙動不変)。

    _hierarchy_* は post_session 診断ログ専用の snapshot で、出力ローカルは
    無い (ブロックローカルは関数内に閉じる)。
    """
    _hierarchy_area_now = _resolved_area
    _hierarchy_session_name = _active_session_name_for_log(w)
    _hierarchy_npc_active = (
        bool(getattr(w, "_npc_conversation_active", False))
        or bool(_hierarchy_session_name)
    )
    _hierarchy_now = SeparationHierarchy.from_parts(
        top_level_state=_current_top_level(w),
        c_area=_hierarchy_area_now,
        in_interior=in_interior,
        npc_active=_hierarchy_npc_active,
    )
    # _hierarchy_now は post_session 診断ログ専用 snapshot。dead store 撤去。
    _log_hierarchy_recognition(
        w,
        stage="post_session",
        hierarchy=_hierarchy_now,
        decision=HierarchyRecognitionInput(
            top_level_state=_current_top_level(w),
            c_area=_hierarchy_area_now,
            in_interior=in_interior,
            npc_active=_hierarchy_npc_active,
            npc_phase=_npc_phase_early,
            mif_name=mif_name,
            img_name=_img_name_early,
            screen_id=getattr(w, "_screen_id_prev", None),
            panel_owner=getattr(w, "_panel_owner", "") or "",
            active_session=_hierarchy_session_name,
            interior_mif_name=interior_mif_name or "",
            interior_raw=interior_raw,
        ),
    )


def _poll_reset_temple_keys_on_img_transition(
        w, *, _img_name_early, _temple_active_now):
    """神殿 YESNO.IMG→MENU_RT.IMG 遷移時に owner key 群を reset する
    (poll から純抽出・挙動不変)。

    出力ローカルは無い (ブロックローカル _temple_img_* は関数内に閉じ、
    副作用は w._temple_*/_negot_*/_active_tmpl_* の書込のみ)。
    """
    # YESNO.IMG → MENU_RT.IMG 遷移時に
    # temple owner の key 群を reset してメニュー再描画を許可する。
    # TempleSession の直前 IMG を取得し変化を検出する。
    _temple_img_now = (_img_name_early or "").upper()
    _temple_img_prev = (w._temple_last_img_prev or "").upper()
    _temple_img_transition_to_menu = (
        _temple_active_now
        and _temple_img_prev == "YESNO.IMG"
        and _temple_img_now == "MENU_RT.IMG"
    )
    if _temple_img_transition_to_menu:
        # neg / active_template / shop_menu の前 poll キーを clear し、
        # 同 poll 内の menu / negotiation 表示を再描画させる
        w._negot_key_prev = None
        w._active_tmpl_key_prev = None
        w._active_tmpl_ctx_prev = None
        w._negot_prompts_ctx_prev = None
        # 神殿メニューは temple_menu owner (temple_render_module) へ
        # 移管したため、再描画許可は temple_menu のキーを reset する。
        w._temple_menu_key_prev = None
        w._temple_dialog_current_key = None
        w._temple_dialog_current_text = None
        w._temple_dialog_hold_polls = 0
        _log.info(
            "temple IMG transition YESNO.IMG -> MENU_RT.IMG: "
            "owner keys reset for menu redraw")
    w._temple_last_img_prev = _temple_img_now


def _poll_track_facility_latch(w):
    """施設 latch (active/edge) を session_manager 単一 active から導出し、
    stop エッジのクリーンアップ副作用を実行する (poll から純抽出・挙動不変)。

    局所入力は無い (全て w.* 参照)。副作用は w._*_active_prev の edge 更新と
    停止施設の表示クリーンアップ。下流で消費される 10 latch 値を返す
    (戻り順は呼び出し側 unpack と一致): active_facility_name / tavern/temple/
    equipment/mages の各 active_now / temple/equipment/mages の just_started /
    facility_active_now / facility_just_started。ブロックローカルの
    _active_facility_sess・各 just_stopped・_tavern_just_started は関数内に閉じる。
    """
    # 施設 latch は session_manager の単一 active を唯一の真実と
    # する (= 各 _X_session.is_active() 直読みによる二重管理を解消)。manager は
    # 単一 active 相互排他で、開始時 on_other_session_started が他を強制 off
    # する (基底/各 session が _active=False) ため、施設 session について
    # _X_session.is_active() ⟺ active_session().name == X が成立する (挙動等価)。
    _active_facility_sess = w._session_manager.active_session()
    _active_facility_name = (
        _active_facility_sess.name
        if _active_facility_sess is not None else "")
    _tavern_active_now = (_active_facility_name == "tavern")
    _tavern_just_started = (
        _tavern_active_now and not w._tavern_active_prev)
    _tavern_just_stopped = (
        w._tavern_active_prev and not _tavern_active_now)
    w._tavern_active_prev = _tavern_active_now

    # TempleSession の active/edge も同様に追跡
    _temple_active_now = (_active_facility_name == "temple")
    _temple_just_started = (
        _temple_active_now and not w._temple_active_prev)
    _temple_just_stopped = (
        w._temple_active_prev and not _temple_active_now)
    w._temple_active_prev = _temple_active_now

    # 武具店 / 魔術師ギルドの active/edge も同様に追跡。
    # 各セッションは自施設の owner_kind でのみ active になる独立 latch。
    _equipment_active_now = (_active_facility_name == "equipment")
    _equipment_just_started = (
        _equipment_active_now and not w._equipment_active_prev)
    _equipment_just_stopped = (
        w._equipment_active_prev and not _equipment_active_now)
    w._equipment_active_prev = _equipment_active_now

    _mages_active_now = (_active_facility_name == "mages_guild")
    _mages_just_started = (
        _mages_active_now and not w._mages_guild_active_prev)
    _mages_just_stopped = (
        w._mages_guild_active_prev and not _mages_active_now)
    w._mages_guild_active_prev = _mages_active_now

    # facility session (tavern/temple/equipment/mages) が
    # active かどうか汎用判定
    _facility_active_now = (
        _tavern_active_now or _temple_active_now
        or _equipment_active_now or _mages_active_now)
    _facility_just_started = (
        _tavern_just_started or _temple_just_started
        or _equipment_just_started or _mages_just_started)
    if _tavern_just_stopped:
        _clear_stopped_facility_display(w, "tavern")
    if _temple_just_stopped:
        _clear_stopped_facility_display(w, "temple")
    if _equipment_just_stopped:
        _clear_stopped_facility_display(w, "equipment")
        # 非active クリーンアップを stop エッジへ集約
        # (= reply 関数を active時のみの純責務へ分離)。初回非active
        # poll=just_stopped で baselined state を reset(冪等・等価)。
        if getattr(w, "_equipment_reply_baselined", False):
            from normal_play.equipment_reply_module import (
                reset_equipment_reply_state as _reset_equipment_reply,
            )
            _reset_equipment_reply(w)
    if _mages_just_stopped:
        _clear_stopped_facility_display(w, "mages_guild")
        if getattr(w, "_mages_reply_baselined", False):
            from normal_play.mages_reply_module import (
                reset_mages_reply_state as _reset_mages_reply,
            )
            _reset_mages_reply(w)
    return (
        _active_facility_name,
        _tavern_active_now,
        _temple_active_now,
        _temple_just_started,
        _equipment_active_now,
        _equipment_just_started,
        _mages_active_now,
        _mages_just_started,
        _facility_active_now,
        _facility_just_started,
    )


def _poll_resolve_yesno_menu_recovery(w, *, _shop_img_name, _temple_active_now):
    """YESNO.IMG 固着中の店主メニュー復帰可否を解決する
    (poll から純抽出・挙動不変)。

    入力は _shop_img_name/_temple_active_now。出力は _allow_yesno_menu_recovery
    の1値(return)。副作用は w._yesno_recovery_empty_polls/_yesno_menu_recovery_last
    の更新。ブロックローカル _popup_surface_active/_temple_phase_rec は関数内に閉じる。
    """
    # YESNO.IMG 中の店主メニュー復帰判定。
    # 実機観測: 忍び込み確認/結果を消してメニューへ戻っても画面 IMG は
    # YESNO.IMG のまま固着し、current_ptr も店主メニュー項目に戻る。
    # 「確認/結果ポップアップ表示中」と「メニュー復帰」は (img, ptr) では
    # 区別できないが、active_template の tavern_* surface 候補の有無で
    # 区別できる (= ポップアップ表示中のみ候補が存在する)。
    # よって候補が無い (= ポップアップ前景でない) ときだけメニュー復帰を
    # 許可する。panel_owner/surface 履歴による旧条件は、復帰成功時に
    # 自身の前提が崩れて自己消火するため置き換える。
    _allow_yesno_menu_recovery = False
    if _shop_img_name == "YESNO.IMG":
        _popup_surface_active = False
        try:
            from active_template_reader import (
                read_active_template_candidates as _ratc_rec,
                template_surface_kind as _tsk_rec,
                input_prompt_facility as _ipf_rec,
            )
            for _rc in _ratc_rec(w._analyzer, w._anchor):
                # surface kind か入力プロンプト facility を持つ候補 =
                # 確認/結果/入力ポップアップが前景にある (= メニューでない)。
                if (_tsk_rec(_rc) or "") or (_ipf_rec(_rc) or ""):
                    _popup_surface_active = True
                    break
        except Exception:  # noqa: BLE001
            _popup_surface_active = False
        # 確認表示中に active_template 候補が 1 poll だけ消える
        # フリッカがあり、それで即メニュー復帰すると owner が
        # active_template から外れ宿屋セッションが停止して画面が崩れる。
        # 候補なしが連続 2 poll 続いて初めて復帰を許可し誤発火を防ぐ。
        if _popup_surface_active:
            w._yesno_recovery_empty_polls = 0
        else:
            w._yesno_recovery_empty_polls = (
                getattr(w, "_yesno_recovery_empty_polls", 0) + 1)
        _allow_yesno_menu_recovery = (
            getattr(w, "_yesno_recovery_empty_polls", 0) >= 2)
        # 神殿の Heal 費用確認で NO/CANCEL を選ぶと、
        # 実画面は神官メニューへ戻るが SCREEN_IMG は YESNO.IMG のまま
        # 残ることがある。この時 active_template 候補ではなく
        # temple_cost の stale 本文が残るため、宿屋用の空候補ヒステリシス
        # だけでは menu recovery が成立しない。神殿 active 中かつ
        # temple phase が menu なら、YESNO.IMG 固着中でも detector に
        # 神殿メニュー復帰を許可する。
        if _temple_active_now:
            try:
                from temple_dialog_reader import classify_temple_phase
                _temple_phase_rec, _ = classify_temple_phase(
                    w._analyzer, w._anchor)
            except Exception:  # noqa: BLE001
                _temple_phase_rec = ""
            if _temple_phase_rec == "menu":
                _allow_yesno_menu_recovery = True
    else:
        w._yesno_recovery_empty_polls = 0
    # TavernSession が次 poll の継続判定で同じ復帰可否を使える
    # よう window に保存する (= 別軸再検出による不一致を防ぐ)。
    w._yesno_menu_recovery_last = _allow_yesno_menu_recovery
    return _allow_yesno_menu_recovery


def _poll_detect_shop_state(w, *, _shop_img_name, in_interior,
                            _active_facility_name, _allow_yesno_menu_recovery):
    """店内ポップアップ状態 (_shop_state) を検出する (poll から純抽出・挙動不変)。

    入力は _shop_img_name/in_interior/_active_facility_name/
    _allow_yesno_menu_recovery。出力は _shop_state の1値(return・失敗時 None)。
    ブロックローカル _active_facility_for_shop は関数内に閉じる。
    """
    try:
        from shop_popup_detector import (
            detect_shop_popup_state,
        )
        # latch if/elif 施設分岐を撤去。施設 active は単一 active
        # (active_session) が唯一の真実のため、非施設 (npc_chat 等) を
        # 除外して施設名をそのまま使う (= 旧 if/elif と等価)。
        _active_facility_for_shop = (
            _active_facility_name
            if _active_facility_name in (
                "equipment", "mages_guild", "temple", "tavern")
            else "")
        _shop_state = detect_shop_popup_state(
            w._analyzer, w._anchor,
            top_level_state=_current_top_level(w),
            img_name=_shop_img_name,
            in_interior=in_interior,
            screen_id=w._screen_id_prev,
            allow_yesno_menu_recovery=_allow_yesno_menu_recovery,
            # 非宿屋施設の NEWPOP 一覧を宿屋部屋一覧へ誤分類しない
            # ため interior_mif を渡す (= shop_rooms tavern 帰属を宿屋
            # 文脈に限定)。
            interior_mif_name=getattr(
                w, "_interior_mif_name", "") or "",
            active_facility_name=_active_facility_for_shop,
        )
    except Exception:  # noqa: BLE001
        _log.exception("shop_popup_detector failed")
        _shop_state = None
    return _shop_state


def _poll_classify_tavern_view_and_log(
        w, *, _shop_state, _shop_img_name, in_interior, _tavern_active_now):
    """店主会話の単一判定 (_tview classify) + 診断ログ (poll から純抽出・挙動不変)。

    入力は _shop_state/_shop_img_name/in_interior/_tavern_active_now。下流消費の
    (_tview, _tavern_l4_kind, _facility_tavern) を返す (戻り順は caller unpack と一致)。
    副作用は w._tavern_view/_tavern_view_l4_visible/_tview_log_key/_shop_kind_prev/
    _shop_img_prev の更新。ブロックローカル(_shop_kind/_kind_changed/_shop_owner_now 等)は
    関数内に閉じる。
    """
    _shop_kind = _shop_state.kind if _shop_state else "none"
    # poll 間の店内 surface 種別履歴 (本単位が所有する単一の真実)。
    # 店内ダイアログ単位が「一覧 → 応答」の正規遷移判定 (前 poll で
    # メニュー/一覧が前景だったか) に消費する。_shop_kind_prev (変化検出
    # ログ用・同 poll 内で更新される) とは別軸の純粋な前 poll 値。
    w._shop_kind_prev_poll = getattr(w, "_shop_kind_this_poll", "none")
    w._shop_kind_this_poll = _shop_kind
    _shop_kind_prev = getattr(w, "_shop_kind_prev", None)
    _shop_img_prev = getattr(w, "_shop_img_prev", None)
    _kind_changed = (_shop_kind != _shop_kind_prev)
    _img_changed = (_shop_img_name != _shop_img_prev)
    _newpop_unexpected = (
        _shop_img_name == "NEWPOP.IMG"
        and _shop_kind in ("none", "shop_menu")
    )
    # === 店主会話の単一判定 (1軸化中核) ============================
    # 店主会話分離化の判定材料を 1 か所で集め、単一分類器で「今の子画面」を
    # 1 つに確定する。描画 owner 振り分け・接続バー・latch 継続はすべて
    # この結論 (_tview) を見る。施設種別は結果を混ぜず仮説で判定する:
    # 宿屋 MIF / shop_owner==tavern / 宿屋 latch のいずれか。
    _shop_owner_now = (getattr(_shop_state, "owner_kind", "")
                       if _shop_state is not None else "")
    _interior_mif_u = (
        getattr(w, "_interior_mif_name", "") or "").upper()
    # 宿屋施設の前景は active_session() 単一の真実から導く (_tavern_active_now)。
    # 他施設 owner の poll では single-active 相互排他により _tavern_active_now が
    # False となり宿屋経路へ載らないため、owner_kind を再判定する防御的安全弁は
    # 不要 (単一ソースに置換され dead 化した相互排他ガードを撤去)。
    _facility_tavern = bool(_tavern_active_now)
    # 宿屋施設ノード (参照実装) が判定 (1軸) を所有する。
    # classify_view は gather_tavern_signals→classify_tavern_view へ委譲。
    try:
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
        _tview = _TAVERN_NODE.classify_view(
            w,
            shop_kind=_shop_kind, shop_owner=_shop_owner_now,
            img=_shop_img_name, in_interior=in_interior,
            facility_tavern=_facility_tavern,
            npc_phase=getattr(w, "_npc_phase", None))
    except Exception:  # noqa: BLE001
        _log.exception("tavern view classify failed")
        from session.tavern_view import TavernView as _TVErr
        _tview = _TVErr(
            l4_kind="none", render_owner="", bar_key="",
            l4_visible=False, l3_start=False, reason="error")
    w._tavern_view = _tview
    w._tavern_view_l4_visible = _tview.l4_visible
    _tavern_l4_kind = _tview.l4_kind  # 既存互換 (ログ等)
    _tview_log_key = (
        _tview.l4_kind, _tview.render_owner,
        _shop_kind, _shop_owner_now, _shop_img_name,
        _facility_tavern)
    if (_tview.l4_kind != "none"
            and _tview_log_key != getattr(w, "_tview_log_key", None)):
        w._tview_log_key = _tview_log_key
        _log.info(
            "tavern view l4=%s owner=%s reason=%s "
            "(shop_kind=%s shop_owner=%r img=%r fac_tav=%s)",
            _tview.l4_kind, _tview.render_owner, _tview.reason,
            _shop_kind, _shop_owner_now, _shop_img_name,
            _facility_tavern)
    if _shop_state is not None and (_kind_changed or _img_changed
                                    or _newpop_unexpected):
        _log.info(
            "shop_state kind=%s img=%r screen=%r interior=%s "
            "ptr=%s ptr_hi=%s b7c4=%s ff2=%s "
            "menu_span=%s buy_span=%s "
            "menu_items=%r buy_count=%d "
            "panel_owner=%r prev_kind=%r reason=%r",
            _shop_state.kind,
            _shop_state.img_name,
            _shop_state.screen_id,
            _shop_state.in_interior,
            (f"0x{_shop_state.ptr:04X}"
             if _shop_state.ptr is not None else "?"),
            (f"0x{_shop_state.ptr_hi:02X}"
             if _shop_state.ptr_hi is not None else "?"),
            (f"0x{_shop_state.b7c4:02X}"
             if _shop_state.b7c4 is not None else "?"),
            (f"0x{_shop_state.ff2:02X}"
             if _shop_state.ff2 is not None else "?"),
            (f"[0x{_shop_state.menu_span[0]:X},"
             f"0x{_shop_state.menu_span[1]:X})"
             if _shop_state.menu_span else "None"),
            (f"[0x{_shop_state.buy_span[0]:X},"
             f"0x{_shop_state.buy_span[1]:X})"
             if _shop_state.buy_span else "None"),
            _shop_state.menu_items[:8],
            len(_shop_state.buy_items),
            w._panel_owner,
            _shop_kind_prev,
            _shop_state.reason)
        w._shop_kind_prev = _shop_kind
        w._shop_img_prev = _shop_img_name
    return (_tview, _tavern_l4_kind, _facility_tavern)


def _poll_detect_dungeon_entry(w, *, mif_name):
    """start.mif 進入によるダンジョン突入(chargen→normal-play 遷移)を検出する
    (poll から純抽出・挙動不変)。

    入力は mif_name。出力ローカルは無い(ブロックローカル _post_chargen_reached は
    関数内に閉じ、副作用は top_level 遷移/chargen UI state/各フラグ更新)。
    """
    _post_chargen_reached = (
        w._chargen_opening_displayed
        or bool(w._chargen_opening_text_prev)
    )
    if (mif_name and mif_name.lower() == "start.mif"
            and not w._dungeon_entry_cleared):
        if (_current_top_level(w) == "chargen"
                and _post_chargen_reached):
            w._transition_top_level("normal-play",
                                       "start.mif in chargen (post-chargen)")
        if _post_chargen_reached:
            w._dungeon_entry_cleared = True
            w._chargen_opening_retry = 0
            w._chargen_opening_text_prev = ""
            w._set_chargen_ui_state(False)
            w._ui_router.clear_display("")
            # start.mif 進入 = キャラクター作成完了。サブ状態フラグを
            # 全リセットし、ヘッダー残置を防ぐ。1 ダンジョン進入 1 回限り。
            try:
                w._chargen._reset_chargen_state_for_restart(
                    reason="start.mif restart (dungeon entry, chargen end)")
            except (AttributeError, RuntimeError) as exc:
                _log.debug("chargen reset on start.mif skipped: %s", exc)
            _log.info("dungeon: start.mif entry detected, cinematic cleared")
    elif mif_name and mif_name.lower() != "start.mif":
        # ダンジョンを離れた場合に再度フラグを開ける (次回 cinematic 用)
        w._dungeon_entry_cleared = False


def _poll_compute_newpop_gate(w, *, npc_dialog):
    """NEWPOP popup OPEN ゲートと corpse loot 判定を算出する
    (poll から純抽出・挙動不変)。

    入力は npc_dialog。下流消費の (_newpop_gate, _is_corpse_loot) を返す
    (戻り順は caller unpack と一致)。ブロックローカル(_newpop_img_now/
    _newpop_gate_byte/_newpop_count_now)は関数内に閉じる。
    """
    try:
        _newpop_img_now = w._analyzer.read_bytes(
            w._anchor + 0x9176, 12).split(b"\x00",1)[0].decode(
            "ascii", errors="replace").upper()
        _newpop_gate_byte = w._analyzer.read_bytes(
            w._anchor + 0xB7C4, 1)[0]
        _newpop_gate = (_newpop_img_now == "NEWPOP.IMG"
                        and _newpop_gate_byte == 0x00)
    except (OSError, AttributeError):
        _newpop_gate = False
    try:
        _newpop_count_now = w._analyzer.read_bytes(
            w._anchor + 0xFF2, 1)[0]
    except (OSError, AttributeError):
        _newpop_count_now = 0
    # corpse 経路: +0x9209 ゲート ON かつ count==0 → NPC_DIALOG が単一アイテム名
    _is_corpse_loot = (_newpop_gate and _newpop_count_now == 0
                       and bool(npc_dialog)
                       and not _is_garbage_npc_buffer(npc_dialog))
    return (_newpop_gate, _is_corpse_loot)


def _poll_handle_triggers(w, *, rt_x, rt_z, inf_name):
    """トリガー検出 (check_trigger_flag) と発火処理 (poll_trigger) を行う
    (poll から純抽出・挙動不変)。

    入力は rt_x/rt_z/inf_name。出力ローカルは無い(ブロックローカル body/
    trigger_flag/trigger_idx/trigger_slot/_new_trigger/_trig_fell/old_flag は
    関数内に閉じ、副作用は w._cached_*/_trigger_flag_prev 更新 + poll_trigger)。
    """
    from arena_bridge import check_trigger_flag
    body, trigger_flag, trigger_idx, _n, trigger_slot = check_trigger_flag(
        w._analyzer, w._anchor,
        w._trigger_flag_prev,
        w._trigger_indices,
        w._cached_trig_idx,
    )

    # 新規トリガー検出: flag が前回値より大きい場合（観測ベース）
    # 観測（monitor_trigger.py 60s ログ）:
    #   TRIGGER_FLAG は 40 frame の countdown timer（初期値 0x28 = 40）。
    #   新規トリガー発火 → flag = 0x28 にリセット
    #   約 100ms 毎に -1 で減算（0x27, 0x26, ... 0x10, ...）
    #   countdown 中に次のトリガーが発火すると flag が再び 0x28 へジャンプ。
    # 旧コードの `(old_flag == 0 and trigger_flag != 0)` は「0→非0」しか
    # 検出できず、「flag 0x10 → 0x28」のような非0→大きい非0
    # 連続発火を完全に取り逃していた。
    # 正しくは flag 値が前回より大きい (= reset/jump) で判定する。
    old_flag = w._trigger_flag_prev
    # トリガーメッセージは NPC会話 = False スコープ専用。NPC会話中は新規発火を
    # 抑止する。trigger_flag の前回値更新自体は維持し、NPC会話終了後の状態が
    # 不整合にならないようにする。
    _new_trigger = (trigger_flag > old_flag
                    and not getattr(w, "_npc_conversation_active", False))
    _trig_fell   = (old_flag != 0 and trigger_flag == 0)
    if _new_trigger:
        w._cached_rt_x     = rt_x
        w._cached_rt_z     = rt_z
        w._cached_trig_idx = trigger_idx

    w._trigger_flag_prev = trigger_flag

    from normal_play.trigger_module import (
        poll_trigger as _poll_trigger,
    )
    _poll_trigger(
        w,
        new_trigger=_new_trigger,
        trig_fell=_trig_fell,
        trigger_flag=trigger_flag,
        trigger_idx=trigger_idx,
        trigger_slot=trigger_slot,
        body=body,
        inf_name=inf_name,
    )


def _poll_status_template_parse(w, *, _entry_handled):
    """状態テンプレート(FILLED)パース + popup 閉じ検出 + 翻訳パネル更新を行う
    (poll から純抽出・挙動不変)。

    入力は _entry_handled。出力ローカルは無い(ブロックローカル _parsed/_vkey/
    _popup_active 等は関数内に閉じ、副作用は w._b21_*/_last_status_vkey 更新と
    翻訳パネル更新)。
    """
    # 状態テンプレート (FILLED) パース・サマリ更新・popup 閉じる検出
    # FILLED バッファ（絶対 0x1070486E）はアイコン4 クリック時にのみ更新される
    # ため「常時監視」は現状不可（要追加調査）。代わりに以下の動作:
    #   - 上部サマリ: 毎 poll で render_status の summary を反映（最終既知値表示）
    #   - 翻訳パネル(原文/和訳): popup 表示中かつ値が変化した時のみ _push_translation
    #     で main + layout 両方更新
    #   - popup 閉じる時（u8_0x7924 1→0）かつ本ハンドラが最後にパネルを書いていた場合のみ
    #     _push_translation("","") でクリア。他ハンドラの内容は壊さない
    try:
        from template_parser import parse_filled, render_status
        try:
            _flag_popup = w._analyzer.read_bytes(w._anchor + 0x7924, 1)[0]
        except (OSError, AttributeError):
            _flag_popup = 0
        _popup_active = (_flag_popup == 1)
        _popup_was    = getattr(w, "_b21_popup_was_open", False)

        # popup 閉じる遷移検出: 本ハンドラが所有していた時のみクリア
        if _popup_was and not _popup_active and getattr(w, "_b21_owns_panel", False):
            w._ui_router.clear_if_owner("status")
            w._b21_owns_panel = False
            w._last_status_vkey = None
        w._b21_popup_was_open = _popup_active

        _parsed = parse_filled(w._analyzer, w._anchor)
        if _parsed is not None:
            _vkey = (_parsed.get("location",""), _parsed.get("time",""),
                     _parsed.get("date",""), _parsed.get("weight",""),
                     _parsed.get("weight_max",""), _parsed.get("health",""))
            _full_en, _full_ja, _ = render_status(_parsed)
            # 上部サマリ表示は撤去。翻訳パネルは popup 表示中かつ値変化時のみ更新
            # この poll で施設会話/NPC 応答エントリを描画済み
            # (_entry_handled) の場合は status で上書きしない。UiRouter は
            # 同優先度なら後勝ちのため、施術で health 等が変化した結果 poll で
            # status 更新が temple_priest_reply 等の会話表示を奪う問題を防ぐ。
            if (_popup_active and not _entry_handled
                    and _vkey != getattr(w, "_last_status_vkey", None)):
                w._last_status_vkey = _vkey
                w._ui_router.update_translation(
                    "status", _full_en, _full_ja)
                w._b21_owns_panel = w._ui_router.is_owner("status")
    except (ImportError, AttributeError, OSError):
        pass


def _poll_detect_img_name(w):
    """SCREEN_IMG 名を検出し、変化時に on_img_name_changed/POPUP11 後始末を
    行う (poll から純抽出・挙動不変)。

    出力は _img_name の1値(return)。ブロックローカル _raw_img は関数内に閉じ、
    副作用は w._img_name_lbl/_img_name_prev/_npc_dialog_text_prev/_popup11_* 更新
    + on_img_name_changed。
    """
    # img_name 検出（MENU.IMG / LOADSAVE.IMG / INTRO*.IMG 等）
    try:
        from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
        _raw_img = w._analyzer.read_bytes(
            w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        _img_name = _raw_img.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace").upper()
    except (OSError, ImportError):
        _img_name = ""
    # 接続バー右側に IMG 名（既存 _img_name_lbl は非表示化済み）
    w._img_name_lbl.setText(_img_name)
    if _img_name != w._img_name_prev:
        w._img_name_prev = _img_name
        if _img_name:
            # on_img_name_changed() の中で _transition_top_level() が呼ばれ得る
            # （MENU.IMG → pregame / INTRO*.IMG → chargen）ので detect_screen より先に実行
            w._img_screen.on_img_name_changed(_img_name)
        # NPC 会話ポップアップ中に表示される武器 CIF（MACE.CIF 等）は
        # POPUP11.IMG の直後に遷移するため、prev を維持して次 poll で再検出できる
        # ようにする。normal-play 以外への遷移では通常通りリセットする。
        if (_img_name != "POPUP11.IMG" and not (
            _img_name.endswith(".CIF") and _current_top_level(w) == "normal-play"
        )):
            w._npc_dialog_text_prev = ""
            # POPUP11 離脱時に list state キャッシュもクリアし、再進入時に
            # 必ず先頭から dispatch されるようにする。同時に、直前まで POPUP11
            # サブ状態だった場合は ASK ABOUT? メニュー文脈へ戻る可能性があるため
            # 後段の ASK ABOUT? 検出で再表示するフラグを立てる。
            if getattr(w, "_popup11_list_state_prev", ""):
                w._popup11_exit_pending_ask_about = True
            w._popup11_list_state_prev = ""
    return _img_name


def _poll_automap_files(w):
    """AUTOMAP.64 / fallback automap ファイルの独立 poll を行う
    (poll から純抽出・挙動不変)。出力ローカルなし(副作用のみ)。
    """
    # AUTOMAP.64 の独立 poll (= 画面遷移経路に依存せず確実に取り込む)
    # update_map_state からも呼ばれているが、chargen 中等で skip される
    # 経路を補うために最後でも一度走らせる。bitmap=None や save_dir 未設定
    # の場合は内部で early-return される。
    try:
        w._tab_map.poll_automap_file()
    except (AttributeError, RuntimeError):
        pass
    try:
        w._tab_translate.poll_fallback_automap_file()
    except (AttributeError, RuntimeError):
        pass


def _resolve_field_facility(w, interior_raw):
    """フィールド施設（地下室/神殿/塔）の「中」を単一判定で確定する
    (C3→L3。純判定は base_location_view へ委譲)。

    wilderness session が latch（入場で凍結）した入口 hint と、施設内信号
    (interior_flag / +0x4BD0) を組み合わせて (active, mif, label, facility_name)
    を返す。facility_name は神殿等の固有名（seed 生成・ja 優先 / 無名は None）。
    classify_map_axis には一切手を入れず、ここで解決した値を poll の場所解決
    単一ソースが in_interior/interior_mif_name/施設名として全消費者へ流す。

    スコープは入口 hint（フィールドのマップで扉種別＝クリプト/家/酒場/神殿/塔/
    ダンジョンを識別して latch・離れたら None）に閉じる。hint はフィールドの
    入口近傍でのみ立つため、これ自体が「フィールドにいる」ことの権威であり、
    別途の親 L2 area ゲートは持たない（不安定な area に依存して正当な施設を
    取りこぼさない）。
    """
    try:
        from normal_play.base_location.base_location_view import (
            resolve_field_facility_entry,
        )
    except ImportError:
        return (False, None, "", None)
    tab_map = getattr(w, "_tab_map", None)
    disp = getattr(tab_map, "_dispatcher", None) if tab_map is not None else None
    wild = getattr(disp, "wilderness", None) if disp is not None else None
    if wild is None:
        return (False, None, "", None)
    try:
        hint = wild.field_entrance_hint()
    except (AttributeError, RuntimeError):
        hint = None
    if hint is None:
        return (False, None, "", None)
    # +0x4BD0 補助フラグ読取（地下室=0x04 仮説／フィールド地表=0x01）。
    try:
        from play_area_classifier import _WILDERNESS_FLAG_OFFSET
        wild_flag = w._analyzer.read_bytes(
            w._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
    except (OSError, AttributeError):
        wild_flag = 0
    active, mif, label = resolve_field_facility_entry(
        hint,
        interior_flag_nonzero=bool(interior_raw),
        wild_flag=wild_flag,
    )
    # 固有名は seed 生成済み（hint に保持）。ja 優先・無名（クリプト/塔）は None。
    facility_name = None
    if active:
        facility_name = (getattr(hint, "name_ja", None)
                         or getattr(hint, "name_en", "") or None)
    return (active, mif, label, facility_name)


def _poll_resolve_interior_entry(
        w, *, in_interior, rt_x, rt_z, interior_raw, mif_name, gs):
    """入店遷移検知 + Interior MIF 名/施設名特定 + フィールド施設の単一ソース解決。

    入力は in_interior/rt_x/rt_z/interior_raw/mif_name/gs。下流消費の
    (display_mif_name, interior_mif_name, interior_facility_name,
    _just_entered_interior, effective_in_interior, field_facility_active) を返す
    (戻り順は caller unpack と一致)。effective_in_interior は街路屋内に加えフィールド
    施設（地下室/神殿/塔）の中も True にした実効値で、全消費者（認識階層/マップ/
    place_text）が同じ値を見る単一ソース。field_facility_active は area を C3
    (wilderness) に固定するためのフラグ。副作用は w._last_outside_rt/
    _entry_door_pos/_building_entry_pending/_in_interior_prev/_interior_mif_name/
    _interior_facility_name 等の更新。
    """
    # 入店遷移検知 + Interior MIF 名特定
    # 街路にいるときの最後の rt_x, rt_z を door 候補座標として保持し、
    # 街路→店内へ遷移したタイミングでそれを door_pos に確定する。
    # 店内在室中は CityViewer の facility 計算から Interior MIF (TAVERN8.MIF 等)
    # を求めて、街マップ MIF (LiveMifName) を上書きしてマップタブと
    # MIF 照合器 (店内トリガー検出) に渡す。
    #
    # ダイアログ系画像表示中は raw 座標を _last_outside_rt
    # に流入させない。プレイヤー停止中に raw が一時的に破損 (= X:3 Y:3 等)
    # するパターンによる door 位置誤確定や trigger 誤判定を防ぐ。
    try:
        from arena_bridge import (
            SCREEN_IMG_OFFSET as _SI_OFF_SAFE,
            SCREEN_IMG_MAXLEN as _SI_LEN_SAFE,
        )
        _img_raw_safe = w._analyzer.read_bytes(
            w._anchor + _SI_OFF_SAFE, _SI_LEN_SAFE)
        _img_safe = _img_raw_safe.split(b'\x00')[0].decode(
            'ascii', errors='ignore').upper()
    except Exception:  # noqa: BLE001
        _img_safe = ""
    _dialog_imgs_for_safe = {
        "YESNO.IMG", "NEGOTBUT.IMG", "NEWPOP.IMG",
        "POPUP11.IMG", "FACES00.CIF",
    }
    _safe_coord_gate = (_img_safe in _dialog_imgs_for_safe)
    if (not in_interior and rt_x is not None and rt_z is not None
            and not _safe_coord_gate):
        w._last_outside_rt = (rt_x, rt_z)
    prev_in_interior = getattr(w, "_in_interior_prev", False)
    _just_entered_interior = in_interior and not prev_in_interior
    if _just_entered_interior:
        w._entry_door_pos = getattr(w, "_last_outside_rt", None)
        w._interior_entry_raw = interior_raw
        w._interior_level_count = None
        # 入店メッセージ処理待ち latch: 0x9A / msg_buf が揃うまで
        # building_entry 経路を開けておく。表示成功 or entry phase exit で解除。
        w._building_entry_pending = True
        # 入店診断カウンタを reset (= 新規入店ごとに新たな
        # メモリダンプを記録するため)。
        w._b288_entry_diag_count = 0
        _log.info("interior entered, door_pos=%s map=%s entry_raw=%s",
                  getattr(w, "_entry_door_pos", None),
                  gs.get("MapName"), interior_raw)
    if not in_interior and prev_in_interior:
        _log.info("interior left")
        w._entry_door_pos = None
        w._interior_entry_raw = None
        w._interior_level_count = None
        w._instore_resp_prev = ""
        # pointer 優先方式の状態もリセット
        w._instore_resp_current_key = None
        w._instore_resp_text_by_offset = {}
        w._building_entry_pending = False
    w._in_interior_prev = in_interior

    display_mif_name = mif_name
    interior_mif_name: str | None = None
    interior_facility_name: str | None = None
    if in_interior:
        door_pos = getattr(w, "_entry_door_pos", None)
        location_name = gs.get("MapName") or ""
        if door_pos is not None and location_name:
            try:
                from city_viewer_bridge import (
                    lookup_interior_facility, get_mif_level_count,
                )
                facility_info = lookup_interior_facility(
                    location_name, door_pos[0], door_pos[1])
            except Exception:  # noqa: BLE001
                _log.exception("city_viewer_bridge lookup failed")
                facility_info = None
            if facility_info is not None and facility_info.mif_name:
                interior_mif_name = facility_info.mif_name
                # ja が無ければ en にフォールバック。両方無ければ None。
                interior_facility_name = (
                    facility_info.name_ja
                    or facility_info.name_en
                    or None
                )
                display_mif_name = interior_mif_name
                if getattr(w, "_interior_level_count", None) is None:
                    try:
                        w._interior_level_count = get_mif_level_count(
                            interior_mif_name)
                    except Exception:  # noqa: BLE001
                        _log.exception("get_mif_level_count failed")
        # 宮殿 door 非依存解決 (頑健化):
        # 入店直後〜入店メッセージ中は扉座標 (door_pos) が未確定で
        # lookup_interior_facility が呼べず施設 MIF が未解決のまま
        # マップが空表示になる。宮殿は街シードから door に依らず MIF を
        # 確定できるため、画面 img が PALACE.XMI (= 宮殿) の
        # ときは get_palace_mif_for_location で即解決し、扉座標確定を
        # 待たずにマップを描画する。店等は従来どおり扉座標で解決する
        # (= 本フォールバックは宮殿に限定し既存経路を変えない)。
        if (interior_mif_name is None and location_name
                and _img_safe == "PALACE.XMI"):
            try:
                from city_viewer_bridge import get_mif_level_count
                from services.city_lookup import (
                    get_palace_mif_for_location,
                )
                _palace_mif = get_palace_mif_for_location(location_name)
            except Exception:  # noqa: BLE001
                _log.exception("palace mif fallback failed")
                _palace_mif = None
            if _palace_mif:
                interior_mif_name = _palace_mif
                display_mif_name = _palace_mif
                if getattr(w, "_interior_level_count", None) is None:
                    try:
                        w._interior_level_count = get_mif_level_count(
                            _palace_mif)
                    except Exception:  # noqa: BLE001
                        pass
                _log.info(
                    "palace mif resolved door-free: %s (img=PALACE.XMI)",
                    _palace_mif)
    # フィールド施設（地下室/神殿/塔）の単一ソース解決（C3→L3）。
    # 街路 door 由来の lookup（上ブロック）とは独立に、入口 hint＋施設内信号から
    # 実 MIF を注入する。ここで in_interior を実効 True に引き上げることで、認識
    # 階層・マップ(classify_map_axis)・place_text の全消費者が同じ値を見る（消費者
    # ごとの別上書きをしない＝1軸化違反を再発させない）。
    effective_in_interior = in_interior
    field_active, field_mif, _field_label, field_name = (
        _resolve_field_facility(w, interior_raw))
    if field_active and field_mif:
        interior_mif_name = field_mif
        display_mif_name = field_mif
        # 固有名は seed 生成（神殿のみ・MIF と同じく seed 由来）。クリプト/塔は
        # 無名のため None＝place_text は種別ラベル（地下室/塔）のみになる。
        interior_facility_name = field_name
        effective_in_interior = True

    # 屋内中に一度確定した
    # 施設情報は、扉座標 None の poll で消さない (= L3 親状態保持)。
    # 起動時点で屋内 + 扉座標なしの場合、過去 poll の値が None なら
    # そのまま None だが、一度でも確定したら退店まで保持する。
    # in_interior=False (= 退店) では None でクリア (= 下の else 経路)。
    # フィールド施設（field_active）は hint が毎 poll 凍結値で MIF を供給するため、
    # 街路施設の stale 復元（_interior_facility_name 等）には乗せない。
    if effective_in_interior and not field_active:
        if interior_facility_name is None:
            interior_facility_name = getattr(
                w, "_interior_facility_name", None)
        if interior_mif_name is None:
            interior_mif_name = getattr(
                w, "_interior_mif_name", None)
            if interior_mif_name:
                display_mif_name = interior_mif_name
    w._interior_mif_name = interior_mif_name
    w._interior_facility_name = interior_facility_name
    # 翻訳ログの場所ヒント（best-effort）。屋内は施設名(ja優先)、
    # それ以外は地図名。ログ追記時に translation_feed が参照する。
    if interior_facility_name:
        w._log_location_hint = interior_facility_name
    else:
        try:
            _mn = gs.get("MapName") or ""
            if _mn:
                import location_lookup as _loc_ll
                w._log_location_hint = _loc_ll.lookup(_mn) or _mn
            else:
                w._log_location_hint = ""
        except Exception:  # noqa: BLE001
            pass
    _checkpoint(w, "interior_facility")
    return (display_mif_name, interior_mif_name,
            interior_facility_name, _just_entered_interior,
            effective_in_interior, field_active)


def _poll_chargen_normal_play_transition(w, *, mif_name, _img_name_early):
    """キャラクター作成中→通常プレイ中の遷移ガード (poll から純抽出・挙動不変)。

    入力は mif_name/_img_name_early。出力ローカルは無い(ブロックローカル
    _chargen_normal_reason/_post_chargen_reached_early/_chargen_done_live_for_top
    は関数内に閉じ、副作用は top_level 遷移/chargen state reset/UI クリア)。
    """
    from arena_bridge import CHARGEN_DONE_OFFSET
    # B -> C transition guard.
    # キャラクター作成中から通常プレイ中への離脱は、
    # 5 トリガー設計どおり「旅立ち表示済み + START.MIF」に限定する。
    # chargen_done / IMG / MIF の残留値だけでは C 系へ進ませない。
    try:
        from top_level.chargen_transition import (
            normal_play_entry_reason,
        )
        try:
            _chargen_done_live_for_top = w._analyzer.read_bytes(
                w._anchor + CHARGEN_DONE_OFFSET, 1)[0]
        except (OSError, AttributeError):
            _chargen_done_live_for_top = getattr(
                w, "_chargen_done_prev", 0)
        _post_chargen_reached_early = (
            getattr(w, "_chargen_opening_displayed", False)
            or bool(getattr(w, "_chargen_opening_text_prev", ""))
        )
        _chargen_normal_reason = normal_play_entry_reason(
            top_level_state=_current_top_level(w),
            mif_name=mif_name,
            img_name=_img_name_early,
            post_chargen_reached=_post_chargen_reached_early,
            chargen_done=_chargen_done_live_for_top,
        )
        if _chargen_normal_reason:
            w._transition_top_level(
                "normal-play", _chargen_normal_reason)
            w._chargen_opening_retry = 0
            w._chargen_opening_text_prev = ""
            w._set_chargen_ui_state(False)
            try:
                w._chargen._reset_chargen_state_for_restart(
                    reason="normal-play transition")
            except (AttributeError, RuntimeError) as exc:
                _log.debug(
                    "chargen reset on normal-play transition skipped: %s",
                    exc)
            try:
                w._ui_router.clear_display("")
            except (AttributeError, RuntimeError) as exc:
                _log.debug(
                    "chargen clear on normal-play transition skipped: %s",
                    exc)
            if (mif_name or "").lower() == "start.mif":
                w._dungeon_entry_cleared = True
            _log.info(
                "chargen: normal-play transition (%s, img=%r)",
                _chargen_normal_reason, _img_name_early)
    except Exception:  # noqa: BLE001
        _log.exception("chargen normal-play transition failed")


def _poll_resolve_loading_state(w, *, _img_name_early):
    """ロード中状態判定 + post-load settle + load edge エッジ処理
    (poll から純抽出・挙動不変)。

    入力は _img_name_early。下流消費の (_img_name_early_upper, _load_edge_start,
    _loading_post_settle) を返す (戻り順は caller unpack と一致)。副作用は
    w._loading_state_active/_post_remaining/_loadsave_seen_prev/
    _loading_post_settle_remaining/_map_rt_*_last/_loading_state_active_prev 更新。
    """
    # ロード中状態判定を map/level_up 更新より
    # 前で実施する。`w._loading_state_active`
    # 更新ロジックを早期実行し、同 poll 内の map freeze / level_up gate /
    # その他経路が一貫した値を参照できるようにする。
    # (= LOADSAVE 離脱直後の poll で map/level_up が古い loading 値を見て
    # 誤発火/誤 freeze するのを防ぐ)
    _img_name_early_upper = (_img_name_early or "").upper()
    _loadsave_now = (_img_name_early_upper == "LOADSAVE.IMG")
    _loadsave_prev = w._loading_loadsave_seen_prev
    if _loadsave_now:
        w._loading_state_active = False
        w._loading_state_post_remaining = 0
    elif _loadsave_prev:
        if _img_name_early_upper == "OP.IMG":
            w._loading_state_active = False
            w._loading_state_post_remaining = 0
        else:
            w._loading_state_active = True
            w._loading_state_post_remaining = 8
    elif w._loading_state_post_remaining > 0:
        w._loading_state_post_remaining -= 1
        w._loading_state_active = (
            w._loading_state_post_remaining > 0)
    else:
        w._loading_state_active = False
    w._loading_loadsave_seen_prev = _loadsave_now
    # post-load settle: ロード遷移直後の N poll では new MIF / GS / NPC_PHASE
    # 等が過渡値で安定しない。map / level_up はこの間 prev 値 seed のみで
    # 比較/freeze を抑止する。
    _load_edge_start = (
        w._loading_state_active
        and not getattr(w, "_loading_state_active_prev", False)
    )
    # 軽い settle window (= ロード完了直後の数 poll)
    _loading_post_settle_remaining = getattr(
        w, "_loading_post_settle_remaining", 0)
    if _load_edge_start:
        _loading_post_settle_remaining = 4
    elif _loading_post_settle_remaining > 0:
        _loading_post_settle_remaining -= 1
    w._loading_post_settle_remaining = _loading_post_settle_remaining
    _loading_post_settle = (_loading_post_settle_remaining > 0)
    # 早期エッジ検知: マップタブ探索状態リセット (= 元 line 1402-1411 相当)
    if _load_edge_start:
        try:
            w._tab_map.reset_progress()
        except (AttributeError, RuntimeError):
            pass
        try:
            w._tab_translate.fallback_map_tab().reset_progress()
        except (AttributeError, RuntimeError):
            pass
        # LOADSAVE 後の marker 固着を
        # 防ぐため、load edge で last 座標も None reset。freeze 中は
        # last が None なら marker 非表示、IDLE 復帰後に rt_x で再 seed。
        w._map_rt_x_last = None
        w._map_rt_z_last = None
        w._map_angle_last = None
    _release_completed_load_screen_owner(
        w,
        img_name=_img_name_early_upper,
        save_detected=_detect_save_file_write(w),
        loading_active=w._loading_state_active,
        loading_post_settle=_loading_post_settle)
    w._loading_state_active_prev = w._loading_state_active
    return (_img_name_early_upper, _load_edge_start,
            _loading_post_settle)


def _poll_resolve_area_and_frame(w, *, mif_name, in_interior, ui_router,
                                 field_facility_active=False):
    """L2 area を poll あたり1回確定(単一軸)し poll frame を開始する
    (poll から純抽出)。

    入力は mif_name/in_interior/ui_router/field_facility_active。下流消費の
    (_resolved_area, _poll_hierarchy_area) を返す (戻り順は caller unpack と一致)。
    ブロックローカル _poll_hierarchy は関数内に閉じる。副作用は
    w._last_non_interior_area 更新 + ui_router.begin_poll_frame。

    1軸化: area の確定は本関数の単一経路。フィールド施設(地下室/家/酒場/神殿/塔)の
    中は、フィールドのマップで扉種別を識別した入口検出 (field_facility_active) を
    フィールドの権威として area=wilderness(C3) に確定する。これは並列の再判定では
    なく、扉種別という確実な権威入力での単一determinerの分岐。入場で LiveMifName が
    stale な VILLAGE*.MIF へ化けても、また不安定な場所種別byteが一瞬 city に振れても、
    C2 誤認しない。
    """
    # L2 area を poll あたり1回だけ確定（単一軸）。
    _resolved_area = ""
    if field_facility_active:
        # 扉種別検出がフィールド施設を確定＝確実にフィールド(C3)の中。
        _resolved_area = "wilderness"
    elif _current_top_level(w) == "normal-play":
        _resolved_area, w._last_non_interior_area = (
            _resolve_area_with_indoor_fallback(
                w._analyzer, w._anchor, mif_name,
                in_interior=in_interior,
                last_non_interior_area=getattr(
                    w, "_last_non_interior_area", ""),
            )
        )
    _poll_hierarchy_area = _resolved_area
    _poll_hierarchy = SeparationHierarchy.from_parts(
        top_level_state=_current_top_level(w),
        c_area=_poll_hierarchy_area,
        in_interior=in_interior,
        npc_active=bool(getattr(
            w, "_npc_conversation_active", False)),
    )
    # _poll_hierarchy は begin_poll_frame(frame) 専用 snapshot。
    # w._separation_hierarchy への store は本番に reader が無い dead state
    # だったため撤去 (構築は各 local consumer 用で共有 mutable truth ではない)。
    if ui_router is not None:
        ui_router.begin_poll_frame(
            PollFrame.from_window(w, hierarchy=_poll_hierarchy))
    return (_resolved_area, _poll_hierarchy_area)


def _poll_read_game_state(w):
    """ゲーム状態/RT座標/Interior/翻訳タブ更新/INF・MIF名を読む
    (poll から純抽出・挙動不変)。

    下流消費の (gs, rt_x, rt_z, in_interior, interior_raw, state, inf_name,
    mif_name, player_floor) を返す (戻り順は caller unpack と一致)。
    副作用は w._in_interior/_interior_raw/_active_mif 更新 + 翻訳タブ更新。
    """
    from arena_bridge import (
        read_game_state, interpret_location,
        RT_COORD_X_OFFSET, RT_COORD_Z_OFFSET,
        read_interior_flag,
    )
    from play_area_classifier import resolve_in_interior
    gs = read_game_state(w._analyzer, w._anchor)

    # RT座標読み取り（翻訳タブ表示・トリガー照合の両方に使う）
    try:
        rt_x = struct.unpack_from(
            "<H", w._analyzer.read_bytes(w._anchor + RT_COORD_X_OFFSET, 2))[0]
        rt_z = struct.unpack_from(
            "<H", w._analyzer.read_bytes(w._anchor + RT_COORD_Z_OFFSET, 2))[0]
    except OSError:
        rt_x = rt_z = None

    # Interior 在室判定。0xBC8E(interior_raw) は夜に menuType で非0汚染される
    # ため、場所種別byte(+0x4BD0)を権威にして屋外(街路0x00/フィールド0x01)では
    # 屋内扱いしない（resolve_in_interior・ダンジョンは別軸で現状維持）。
    interior_raw = read_interior_flag(w._analyzer, w._anchor)
    try:
        place_byte = w._analyzer.read_bytes(
            w._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
    except (OSError, IndexError, AttributeError):
        place_byte = None
    _mif_for_interior = gs.get("LiveMifName") or gs.get("MifName") or ""
    in_interior = resolve_in_interior(
        interior_raw, place_byte, _mif_for_interior)
    w._in_interior = in_interior
    w._interior_raw = interior_raw
    _checkpoint(w, "gamestate")

    # 翻訳タブ更新（RT座標を優先使用）
    state = interpret_location(gs)
    if rt_x is not None:
        state["x"] = rt_x
        state["z"] = rt_z
    state["in_interior"] = in_interior
    state["interior_raw"] = interior_raw
    w._tab_translate.update_game_state(state)

    # INF名・MIF名取得（LiveMifName を優先使用）
    inf_name = (gs.get("InfName") or "").upper()
    mif_name = gs.get("LiveMifName") or gs.get("MifName") or ""
    player_floor = gs.get("PlayerFloor") or 0
    # 現 poll でアクティブな MIF を記録（XMI ハンドラで屋外 BGM 判定に使う）
    w._active_mif = mif_name
    return (gs, rt_x, rt_z, in_interior, interior_raw, state,
            inf_name, mif_name, player_floor)


def _poll_read_npc_phase_and_img(w):
    """NPC phase 信号 + SCREEN_IMG 名(早期)を読む (poll から純抽出・挙動不変)。

    下流消費の (_npc_phase_early, _img_name_early) を返す (戻り順は caller unpack
    と一致)。副作用は w._npc_phase 更新。ブロックローカル _img_raw_early は
    関数内に閉じる。
    """
    from arena_bridge import read_npc_phase
    try:
        _npc_phase_early = read_npc_phase(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _npc_phase_early = None
    w._npc_phase = _npc_phase_early

    # screen IMG 名を先に取得 (shop block より前で必要なため)
    try:
        from arena_bridge import (
            SCREEN_IMG_OFFSET as _SI_OFF_E,
            SCREEN_IMG_MAXLEN as _SI_LEN_E,
        )
        _img_raw_early = w._analyzer.read_bytes(
            w._anchor + _SI_OFF_E, _SI_LEN_E)
        _img_name_early = _img_raw_early.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace")
    except Exception:  # noqa: BLE001
        _img_name_early = ""
    return (_npc_phase_early, _img_name_early)


def _poll_run_session_manager(
        w, *, _img_name_early, _npc_phase_early, in_interior,
        _resolved_area, mif_name, interior_mif_name):
    """session context を構築し session_manager の poll を表示経路より前で
    実行する (poll から純抽出・挙動不変)。出力ローカルなし(ブロックローカル
    _session_ctx/_session_hierarchy_area/_t_l3 は関数内に閉じる)。
    """
    try:
        _session_hierarchy_area = _resolved_area
        _session_ctx = _build_session_context(
            w,
            img_name=_img_name_early,
            screen_id=w._screen_id_prev,
            top_level_state=_current_top_level(w),
            in_interior=in_interior,
            npc_phase=_npc_phase_early,
            npc_active=bool(getattr(
                w, "_npc_conversation_active", False)),
            c_area=_session_hierarchy_area,
            mif_name=mif_name,
            interior_mif_name=interior_mif_name or "",
            facility_kind="",  # 現状 CityViewer から取得未実装
            extras={"window": w},
        )
        _t_l3 = _phase_start()
        _poll_normal_play_sessions(w, _session_ctx)
        _phase_record(w, "L3_session", _t_l3)
        _checkpoint(w, "session")
    except Exception:  # noqa: BLE001
        _log.exception("session_manager.poll failed")


def _log_hierarchy_recognition(
    w,
    *,
    stage: str,
    hierarchy: SeparationHierarchy,
    decision: HierarchyRecognitionInput,
) -> None:
    """L1-L4 の認識変化と矛盾入力だけをログに残す。"""
    path = " > ".join(hierarchy.path_codes) or "(none)"
    names = " > ".join(hierarchy.path_names) or "(none)"
    transition_key = decision.transition_key(hierarchy)
    if transition_key != getattr(w, "_hierarchy_log_transition_key", None):
        w._hierarchy_log_transition_key = transition_key
        values = decision.values_for_log()
        _recog(
            _log,
            "hierarchy changed stage=%s path=%s names=%s indicator=%s "
            "top=%r area=%r interior=%s interior_raw=%s "
            "npc_active=%s npc_phase=%s mif=%r img=%r screen=%r "
            "owner=%r session=%r interior_mif=%r",
            stage, path, names, hierarchy.indicator,
            values["top"], values["area"], values["interior"],
            _fmt_hex_byte(values["interior_raw"]),
            values["npc_active"], _fmt_hex_byte(values["npc_phase"]),
            values["mif"], values["img"], values["screen"],
            values["owner"], values["session"], values["interior_mif"])

    anomaly_key = decision.anomaly_key()
    if anomaly_key and anomaly_key != getattr(
            w, "_hierarchy_log_anomaly_key", None):
        w._hierarchy_log_anomaly_key = anomaly_key
        values = decision.values_for_log()
        _log.warning(
            "hierarchy rejected stage=%s kind=%s path=%s names=%s "
            "top=%r area=%r interior=%s interior_raw=%s "
            "npc_active=%s npc_phase=%s mif=%r img=%r screen=%r "
            "owner=%r session=%r interior_mif=%r",
            stage, decision.anomaly_kind(), path, names,
            values["top"], values["area"], values["interior"],
            _fmt_hex_byte(values["interior_raw"]),
            values["npc_active"], _fmt_hex_byte(values["npc_phase"]),
            values["mif"], values["img"], values["screen"],
            values["owner"], values["session"], values["interior_mif"])


def _poll_map_update(
        w, in_interior, interior_raw, player_floor, display_mif_name,
        _resolved_area, interior_mif_name, interior_facility_name, state, gs,
        rt_x, rt_z, _img_name_early_upper, _loading_post_settle, _facility_active_now):
    """階数推定 + MIF照合器/マップタブ/フォールバックマップ更新を poll()
    から純粋抽出 (de-bloat・挙動不変)。全状態は w.* に保持し、入力ローカルのみ
    受け取る。arena_bridge 定数は poll() の local import だったため再 import。
    """
    from arena_bridge import (
        read_npc_phase, NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_IDLE,
        RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK,
        RT_ANGLE_NORTH_RAW, RT_ANGLE_RANGE,
    )
    # 階数判定仮説 (= 入店時 raw vs 現在 raw 比較、interior_id.estimate_floor)
    # PlayerFloor (anchor+GAMESTATE+2) は Interior の階数を反映しない
    # ことが観測済み (反証あり)。代替として +0x0BC8E の入店時 raw 値と
    # 現在 raw 値の比較 + MIF level_count で「入店時の階 (0F)」「別の階 (1F)」
    # を判別する仮説を導入。
    #   level_count <= 1 (平屋): 常に 0 (= 入店時の階)
    #   current == entry: 0 (= 入店時の階、1F 相当)
    #   current != entry: 1 (= 別の階、2F 相当)
    # 観測継続中の仮説のため、Interior 外では従来通り PlayerFloor を使う。
    interior_floor_hyp: int | None = None
    if in_interior:
        try:
            from interior_id import estimate_floor  # type: ignore
            interior_floor_hyp = estimate_floor(
                getattr(w, "_interior_entry_raw", None),
                interior_raw,
                getattr(w, "_interior_level_count", None),
            )
        except Exception:  # noqa: BLE001
            interior_floor_hyp = None
    w._interior_floor_hyp = interior_floor_hyp
    effective_floor = (interior_floor_hyp
                       if in_interior and interior_floor_hyp is not None
                       else int(player_floor))

    # MIF照合器のマップ更新 (店内在室中は Interior MIF で照合)
    if w._mif_matcher and _current_top_level(w) == "normal-play":
        w._mif_matcher.update_map(display_mif_name)

    # マップタブ更新（display_mif_name / rt_x / rt_z / player_angle）
    # 入店メッセージ表示中 (NPC_PHASE == 0x9A) は rt_x/rt_z が
    # Interior 内座標へ更新される前の過渡状態のため、プレイヤー位置の
    # 表示を抑制してマップ上の不正配置を防ぐ。
    # chargen 中は実プレイ MIF が無いためマップ更新を
    # 抑止。抑止だけでは前回 normal-play 時の map が残置
    # するため、chargen 中は clear_map() で明示的に消去する。
    tab_map = getattr(w, "_tab_map", None)
    if tab_map is not None and _current_top_level(w) == "chargen":
        # chargen 進入後 1 度だけ clear すれば十分 (= update_map_state を
        # 呼ばないので再 load されない)。is_chargen_cleared フラグで重複
        # 呼出を防ぐ。
        if not getattr(w, "_map_cleared_for_chargen", False):
            try:
                tab_map.clear_map()
            except (AttributeError, RuntimeError):
                _log.exception("tab_map.clear_map failed")
            try:
                w._tab_translate.fallback_map_tab().clear_map()
            except (AttributeError, RuntimeError):
                _log.exception("fallback_map.clear_map failed")
            w._map_cleared_for_chargen = True
    elif tab_map is not None and _current_top_level(w) == "normal-play":
        # chargen から抜けたら clear フラグを下ろし、次の chargen 進入で
        # 再度 clear できるようにする。canvas / status_label の表示も
        # 復元する。
        if getattr(w, "_map_cleared_for_chargen", False):
            w._map_cleared_for_chargen = False
            _restore_chargen_cleared_maps(w, tab_map)
        npc_phase = read_npc_phase(w._analyzer, w._anchor)
        is_building_entry_msg = (npc_phase == NPC_PHASE_BUILDING_ENTRY)
        # プレイヤー向き角度 (anchor + RT_ANGLE_OFFSET, u16 LE, 下位 9 bit)。
        # 512 step / 360°、真北 raw512 = 256 が 0°。時計回りで値増加。
        # 上位 7 bit は別情報のため RT_ANGLE_MASK で抽出する。
        try:
            _angle_bytes = w._analyzer.read_bytes(
                w._anchor + RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE)
            if _angle_bytes and len(_angle_bytes) == RT_ANGLE_BYTE_SIZE:
                _angle_u16 = int.from_bytes(_angle_bytes, "little")
                _angle_raw = _angle_u16 & RT_ANGLE_MASK
                _angle_deg = ((_angle_raw - RT_ANGLE_NORTH_RAW)
                              * 360.0 / RT_ANGLE_RANGE) % 360.0
            else:
                _angle_raw = None
                _angle_deg = None
        except OSError:
            _angle_raw = None
            _angle_deg = None
        # map freeze 条件は wide に戻す
        # (= 鍵入手/宝取得時の `+0xA845` 未知値で rt_x/rt_z が X:3 Y:3
        # に破損する症状を防ぐため)。NPC 会話 state 更新ロジックは
        # 別経路で扱う。本 freeze は意味論ではなく
        # 「overlay 中の座標保護」専用。
        #
        # LOADSAVE 後 marker 固着は別経路で防ぐ:
        # `_load_edge_start` で `_map_rt_x_last / _map_rt_z_last /
        # _map_angle_last` を None reset (= 早期ブロックで実施済)。
        # loading/post-load settle 中は last を seed/update しない。
        #
        # safe value 一元化。
        # 既存の +0xA845 偏重判定 (= npc_phase) は NEWPOP.IMG 中に
        # ptr_hi=0x00 で「ダイアログなし」と誤判定する。これを補強し、
        # 画像名 / facility / negotiation / shop_menu / shop_buy /
        # tavern_yesno 所有を unsafe 条件に追加する。
        #
        # _shop_img_name は本ブロックより後段で初期化されるため、
        # 前段の map block では参照禁止 (= UnboundLocalError
        # を起こした)。本 block では初期化済みの _img_name_early_upper
        # を `_current_img_for_map` として使う。
        # safe 判定自体は controllers.map_safe_coord.compute_map_safe_coord
        # pure helper に委譲し、変数寿命依存を排除する。
        from controllers.map_safe_coord import (
            compute_map_safe_coord as _compute_map_safe,
            INVALID_HELD_COORDS as _INVALID_MAP_HELD_COORDS,
        )
        _current_img_for_map = _img_name_early_upper
        _is_loading_for_map = bool(
            w._loading_state_active or _loading_post_settle)
        # 抑制中でも raw 座標が妥当 (初期化前の固定値 (0,0)/(3,3) で
        # ない) なら last を連続更新する。これにより、ロード直後の
        # NPC phase 抑制中でも player marker の初回表示と通常移動の
        # 反映を両立できる。
        # - last=None: 初回 seed (= ロード境界での None リセット直後)
        # - last あり: 前回値との距離が小さい (=±2 cell 以内) なら
        #   連続更新。離れた値はジャンプ扱いで除外する (= 別経路の
        #   load_edge 初期化に委ねる)。
        if (rt_x is not None and rt_z is not None
                and (rt_x, rt_z) not in ((0, 0), (3, 3))):
            _prev_last_x = getattr(w, "_map_rt_x_last", None)
            _prev_last_y = getattr(w, "_map_rt_z_last", None)
            if _prev_last_x is None and _prev_last_y is None:
                w._map_rt_x_last = rt_x
                w._map_rt_z_last = rt_z
                w._map_angle_last = _angle_deg
            elif (_prev_last_x is not None and _prev_last_y is not None
                    and abs(rt_x - _prev_last_x) <= 2
                    and abs(rt_z - _prev_last_y) <= 2):
                w._map_rt_x_last = rt_x
                w._map_rt_z_last = rt_z
                w._map_angle_last = _angle_deg
        # panel_owner は地図座標の unsafe 判定用 surface 入力
        # としてだけ読む。通常 NPC latch / 階層判定の入力に戻さない。
        _map_surface_owner = getattr(w, "_panel_owner", "") or ""
        _map_safe = _compute_map_safe(
            img_name=_current_img_for_map,
            npc_phase=npc_phase,
            is_building_entry_msg=is_building_entry_msg,
            facility_active=_facility_active_now,
            owner=_map_surface_owner,
            raw_x=rt_x,
            raw_y=rt_z,
            raw_angle=_angle_deg,
            last_x=getattr(w, "_map_rt_x_last", None),
            last_y=getattr(w, "_map_rt_z_last", None),
            last_angle=getattr(w, "_map_angle_last", None),
            npc_phase_idle_value=NPC_PHASE_IDLE,
        )
        _show_player_x = _map_safe.player_x
        _show_player_y = _map_safe.player_y
        # 方角はダイアログ表示中も破損しない（座標と異なり抑止不要）。raw 方角が
        # 読めていれば常にそれを使い、未取得時のみ safe 判定値へフォールバックする。
        # これにより入店メッセージ中など座標抑止時でも現在地マーカーの向きを出せる。
        _show_angle = _angle_deg if _angle_deg is not None else _map_safe.angle_deg
        _coord_source = _map_safe.source
        _unsafe_reasons = _map_safe.unsafe_reasons
        # loading 中/post-load settle 中は last を seed しない
        # (= ロード過渡値で last を上書きしないため。安定後に rt_x
        # で再 seed されて marker 復活)。
        # safe ("raw") のときのみ last を更新する。
        _show_pair = (
            (_show_player_x, _show_player_y)
            if _show_player_x is not None and _show_player_y is not None
            else None
        )
        if (_coord_source == "raw" and not _is_loading_for_map
                and _show_pair not in _INVALID_MAP_HELD_COORDS):
            if _show_player_x is not None:
                w._map_rt_x_last = _show_player_x
            if _show_player_y is not None:
                w._map_rt_z_last = _show_player_y
            if _show_angle is not None:
                w._map_angle_last = _show_angle
        # 診断ログ: 各 poll で raw/held/none のどれを使ったか、
        # unsafe 理由、画像名、+0xA845、宿屋/交渉 active を追跡。
        # 変化時のみ INFO 出力 (= 毎 poll 冗長化を避ける)。
        # 同一行に raw / held / final / origin /
        # visible surface を出力し、マップずれの単独原因を切り分ける。
        try:
            _a845_byte = w._analyzer.read_bytes(
                w._anchor + 0xA845, 1)[0]
        except (OSError, AttributeError):
            _a845_byte = 0
        _held_x_for_diag = getattr(w, "_map_rt_x_last", None)
        _held_y_for_diag = getattr(w, "_map_rt_z_last", None)
        _wild_origin_for_diag = getattr(
            w._wilderness_location, "_origin_chunk", None
        ) if hasattr(w, "_wilderness_location") else None
        _visible_surface_for_diag = (
            _map_surface_owner if _map_surface_owner else
            ("facility" if _facility_active_now else "none")
        )
        _map_safe_diag_key = (
            _coord_source, tuple(_unsafe_reasons),
            _current_img_for_map, _a845_byte,
            _facility_active_now, _map_surface_owner,
            rt_x, rt_z, _held_x_for_diag, _held_y_for_diag,
            _show_player_x, _show_player_y,
            _wild_origin_for_diag,
        )
        _map_safe_diag_prev = getattr(
            w, "_b271_map_safe_diag_prev", None)
        if _map_safe_diag_key != _map_safe_diag_prev:
            w._b271_map_safe_diag_prev = _map_safe_diag_key
            _log.info(
                "map coord: source=%s unsafe=%s img=%r "
                "a845=0x%02X surface=%r "
                "raw=(%s,%s) held=(%s,%s) final=(%s,%s) origin=%s",
                _coord_source,
                "|".join(_unsafe_reasons) or "none",
                _current_img_for_map, _a845_byte,
                _visible_surface_for_diag,
                rt_x, rt_z,
                _held_x_for_diag, _held_y_for_diag,
                _show_player_x, _show_player_y,
                _wild_origin_for_diag)
        try:
            place_text = _format_place_text(
                state, in_interior, interior_mif_name,
                _resolved_area, int(effective_floor),
                interior_facility_name=interior_facility_name,
            )
            # 翻訳ログの場所はマップと同じフル表記（都市 - 施設(種別) NF）を使う。
            # 天候は除外して同一場所の表記を安定させる（フィルタ分断防止）。
            w._log_location_hint = _format_place_text(
                state, in_interior, interior_mif_name,
                _resolved_area, int(effective_floor),
                interior_facility_name=interior_facility_name,
                include_weather=False,
            )
            # 場所種別の確定は各 map session が自前判定する。本ファイル
            # 内では wilderness 診断ログのために _detect_play_area を
            # 直接呼ぶが、結果は ctx に詰めず session に渡さない。
            diag_area = _detect_play_area(
                w._analyzer, w._anchor, display_mif_name)
            if diag_area == "wilderness":
                try:
                    _dump_wild_diag_hex(w._analyzer, w._anchor)
                    _poll_wild_diagnostic(w._analyzer, w._anchor)
                except Exception:  # noqa: BLE001
                    _log.exception("wild_diag failed")
            # 街全体 grid / wilderness grid 組立で必要な location 識別名
            # (= 街/フィールド地域名 "Moonguard" 等)。
            # city: wildSeed 不要だが街判別に MapName を使う。
            # wilderness: wildSeed = location.name 先頭 4 文字 LE32 で
            #   生成するため必須。
            wild_location_name = (
                gs.get("MapName") or ""
                if diag_area in ("city", "wilderness") else None
            )
            tab_map.update_map_state(
                display_mif_name or None,
                _show_player_x,
                _show_player_y,
                _show_angle,
                player_floor=int(effective_floor),
                place_text=place_text,
                location_name=wild_location_name,
                analyzer=w._analyzer,
                anchor=w._anchor,
                interior_mif_name=interior_mif_name,
                in_interior=in_interior,
                area=_resolved_area or None,
            )
            # 翻訳タブ全域に表示するフォールバック用マップにも同じ状態を反映
            try:
                w._tab_translate.update_fallback_map_state(
                    display_mif_name or None,
                    _show_player_x,
                    _show_player_y,
                    _show_angle,
                    player_floor=int(effective_floor),
                    place_text=place_text,
                    location_name=wild_location_name,
                    analyzer=w._analyzer,
                    anchor=w._anchor,
                    interior_mif_name=interior_mif_name,
                    in_interior=in_interior,
                    area=_resolved_area or None,
                )
            except AttributeError as _e:
                # メソッド未実装 (= 旧 UI) は無視。それ以外の AttributeError
                # はフォールバックマップ空表示の原因になりうるため可視化する。
                if "update_fallback_map_state" not in str(_e):
                    _log.warning(
                        "fallback_map update AttributeError: %s", _e)
            except Exception:  # noqa: BLE001
                _log.exception("fallback_map update failed")
        except Exception:  # noqa: BLE001
            _log.exception("tab_map update failed")


def _poll_screen_detect_and_label(
        w, _img_name, mif_name, _resolved_area, player_floor,
        in_interior, _shop_state, _shop_img_name, _level_up_continue,
        _b30_dialog_active, _b30_dialog_active_prev, _b30_red_changed, _npc_dialog_changed):
    """画面検出→接続バー(画面名/indicator/施設・会話ラベル)→bonus/char page/
    spell view→panel resync→level_up consume→journal を poll() から純粋抽出
    (de-bloat・挙動不変)。全状態は w.* に保持し、入力ローカルのみ受け取る。
    """
    # 画面検出 → 接続バー（画面名 + IMG）更新
    # 画面状態に応じた翻訳タブのパネルモード切替もここで実施
    try:
        from screen_detector import (
            detect_screen, get_chargen_subscreen, MENU_ACTIVE_OFFSET,
        )
        chargen_hint = get_chargen_subscreen(w)
        # chargen subscreen の最終検出値を追跡（subscreen 間 fallback 用）
        if chargen_hint is not None:
            w._chargen_subscreen_last = chargen_hint

        # system_menu 判定用の menu_active 連続観測
        # 単発 0 では探索画面 idle pulse と判別不可。直前 poll の値も 0 なら
        # 連続 2 ポーリング 0 で system_menu 確定とする（state observation、
        # 時間ベース debounce ではない）。
        try:
            _menu_raw = w._analyzer.read_bytes(
                w._anchor + MENU_ACTIVE_OFFSET, 2)
            _menu_active_now = _menu_raw[0] | (_menu_raw[1] << 8)
        except (OSError, AttributeError):
            _menu_active_now = 0xFFFF
        _menu_active_was_zero = (
            _menu_active_now == 0
            and getattr(w, "_menu_active_prev", 0xFFFF) == 0
        )
        w._menu_active_prev = _menu_active_now

        _screen_id, _screen_name = detect_screen(
            w._analyzer, w._anchor, _img_name, chargen_hint,
            menu_active_was_zero=_menu_active_was_zero,
            top_level_state=_current_top_level(w),
            last_chargen_subscreen=w._chargen_subscreen_last,
            mif_name=mif_name,
            area=_resolved_area or None)
        # 探索中の area suffix (街/ダンジョン/荒野) を付与。
        # area は poll 先頭で確定した _resolved_area を単一軸として使う。
        from play_area_classifier import area_suffix_ja
        _suffix_area = _resolved_area
        if _screen_id == "game_screen":
            _screen_name += area_suffix_ja(_suffix_area, player_floor)

        # ロードデータ選択中の判定
        # screen_detector が LOADSAVE.IMG + menu_active 連続 2 poll で
        # loadsave_in_play screen_id を返す。menu_active 変化に追随するため
        # SCREEN_IMG 残留に対応できる (キャンセル後の表示残留を解消)。
        w._loading_data_select_active = (_screen_id == "loadsave_in_play")

        # ロードデータ選択中 / ロード中状態の画面認識状態表示:
        # 画面名部分を「ロードデータ選択」または「ロード中」に置き換える。
        # 両状態は相互排他で同時に True にならない。トップレベル指示子
        # ([A] / [B] / [C] / [C1-3]) は維持する。
        if w._loading_data_select_active:
            _screen_name = i18n.tr("screen.loadsave_in_play")
        elif w._loading_state_active:
            _screen_name = i18n.tr("screen.loading_in_play")

        # トップレベル / サブ状態のインジケータを接続中表示に挿入する。
        #   タイトル中 = [A]
        #   キャラクター作成中 = [B]
        #   通常プレイ中 = [C] (ダンジョン中 = [C1] / 街中 = [C2] / フィールド = [C3])
        _top_state = _current_top_level(w)
        _area = _resolved_area
        _hierarchy_for_label = SeparationHierarchy.from_parts(
            top_level_state=_top_state,
            c_area=_area,
            in_interior=in_interior,
            npc_active=(
                bool(getattr(w, "_npc_conversation_active", False))
                or w._session_manager.active_session() is not None),
        )
        # _hierarchy_for_label は接続バー indicator 専用 snapshot。dead store 撤去。
        _indicator = _hierarchy_for_label.indicator

        _active_session_name_for_label = ""
        try:
            _active_session_for_label = (
                w._session_manager.active_session())
            if _active_session_for_label is not None:
                _active_session_name_for_label = (
                    _active_session_for_label.name)
        except (AttributeError, ImportError):
            pass

        # 中途接続では interior_mif_name が空でも、
        # active session / shop owner から施設種別を補完する。
        _facility_label = ""
        _facility_key = ""
        try:
            from controllers.recognition_label import (
                facility_recognition_key, known_facility_kind,
            )
            _shop_owner_for_label = (
                getattr(_shop_state, "owner_kind", "")
                if _shop_state is not None else "")
            # L3 施設識別の永続化（階層化の担保）: 途中接続では interior_mif_name が
            # 空のため、L4 会話中だけ施設種別が分かり、L4 を抜けると識別が失われて
            # 「施設」へ退行していた。屋内に居る間は一度確定した施設種別を L3 に保持し、
            # 屋内を出たらクリアする（屋内では MIF を最優先するため通常入店は不変）。
            if not in_interior:
                w._interior_facility_kind = ""
            else:
                _kind = known_facility_kind(
                    _active_session_name_for_label, _shop_owner_for_label)
                if _kind:
                    w._interior_facility_kind = _kind
            _facility_key = facility_recognition_key(
                getattr(w, "_interior_mif_name", None) or "",
                in_interior,
                active_session_name=_active_session_name_for_label,
                shop_owner_kind=_shop_owner_for_label,
                persisted_facility_kind=getattr(
                    w, "_interior_facility_kind", "") or "",
            )
            if _facility_key:
                _facility_label = i18n.tr(_facility_key)
        except (AttributeError, ImportError):
            pass

        # 会話中ラベル (= session_manager.active_session() で判定)
        _conv_label = ""
        try:
            if _active_session_name_for_label:
                if _active_session_name_for_label == "tavern":
                    _conv_label = i18n.tr(
                        "recognition.conv_shop_owner")
                elif _active_session_name_for_label == "temple":
                    _conv_label = i18n.tr(
                        "recognition.conv_priest")
                elif _active_session_name_for_label == "negotiation":
                    _conv_label = i18n.tr(
                        "recognition.conv_negotiation")
                elif _active_session_name_for_label == "npc_chat":
                    _conv_label = i18n.tr(
                        "recognition.conv_npc")
                elif _active_session_name_for_label == "equipment":
                    # 武具店の店主も shop owner (= 店主会話中)。
                    _conv_label = i18n.tr(
                        "recognition.conv_shop_owner")
                elif _active_session_name_for_label == "mages_guild":
                    # 魔術師ギルドの店主も shop owner (= 店主会話中)。
                    # これが無いと接続バーに L4 会話ラベルが出ない。
                    _conv_label = i18n.tr(
                        "recognition.conv_shop_owner")
            elif getattr(w, "_npc_conversation_active", False):
                _conv_label = i18n.tr("recognition.conv_npc")
        except (AttributeError, ImportError):
            pass

        # 武具店店主会話のサブ画面認識を接続バーへ併記する (= 宿屋と同型の
        # 可視化を武具店分離内で実装。tavern 経路には相乗りしない)。実描画
        # owner (= panel_owner) を見て、メニュー / 一覧 のサブ状態を出す。
        if (_facility_key == "recognition.facility_equipment"
                and _active_session_name_for_label == "equipment"):
            try:
                from controllers.recognition_label import (
                    equipment_sub_state_key,
                )
                _eq_owner = getattr(w, "_panel_owner", "") or ""
                _eq_surface = (
                    getattr(w, "_active_tmpl_surface_kind_prev", "")
                    or "")
                _eq_sub_key = equipment_sub_state_key(
                    _eq_surface, _eq_owner, _shop_img_name,
                    bool(getattr(w, "_negot_counter_active", False)))
                if _eq_sub_key:
                    _conv_label = _conv_label + i18n.tr(_eq_sub_key)
            except (AttributeError, ImportError):
                pass

        # 魔術師ギルド店主会話のサブ画面認識を接続バーへ併記する
        # (武具店と同型を魔術師ギルド分離内で実装。実描画 owner で
        # メニュー / 一覧 / 呪文作成 / 応答 を出す)。
        if (_facility_key == "recognition.facility_mages"
                and _active_session_name_for_label == "mages_guild"):
            try:
                from controllers.recognition_label import (
                    mages_sub_state_key,
                )
                _mg_owner = getattr(w, "_panel_owner", "") or ""
                _mg_sub_key = mages_sub_state_key(
                    _mg_owner, _shop_img_name,
                    getattr(w, "_mages_list_title_en", "") or "")
                if _mg_sub_key:
                    _conv_label = _conv_label + i18n.tr(_mg_sub_key)
            except (AttributeError, ImportError):
                pass

        # 神殿神官会話のサブ画面認識を接続バーへ表示する。
        # 宿屋と同じく、実描画 owner (= panel_owner) を主信号にして、
        # メニュー / 寄付額入力 / 費用確認 / 祝福結果 / 治療結果を
        # 人間が実画面と突き合わせられる状態として併記する。
        _is_temple_ctx = (_facility_key == "recognition.facility_temple")
        if _is_temple_ctx or getattr(
                w, "_temple_view_dbg_prev_ctx", False):
            try:
                from controllers.recognition_label import (
                    temple_sub_state_key,
                )
                _temple_owner = getattr(w, "_panel_owner", "") or ""
                _temple_surface = ""
                if _temple_owner in ("temple_cost", "temple_prompt"):
                    _temple_surface = (
                        getattr(w, "_temple_cost_current_surface", "")
                        or "")
                    _temple_text = (
                        getattr(w, "_temple_cost_current_text", "")
                        or "")
                elif _temple_owner == "temple_priest_reply":
                    _temple_text = (
                        getattr(w, "_temple_dialog_current_text", "")
                        or "")
                else:
                    _temple_surface = (
                        getattr(w, "_active_tmpl_surface_kind_prev", "")
                        or "")
                    _temple_text = ""
                _temple_sub_key = temple_sub_state_key(
                    _temple_surface, _temple_owner,
                    _shop_img_name, _temple_text)
            except (AttributeError, ImportError):
                _temple_owner = ""
                _temple_surface = ""
                _temple_text = ""
                _temple_sub_key = ""

            if (_is_temple_ctx
                    and _active_session_name_for_label == "temple"
                    and _temple_sub_key):
                try:
                    _conv_label = _conv_label + i18n.tr(
                        _temple_sub_key)
                except (AttributeError, ImportError):
                    pass

            try:
                _td_raw = w._analyzer.read_bytes(
                    w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
                _temple_view = _td_raw[0] | (_td_raw[1] << 8)
            except (OSError, AttributeError):
                _temple_view = None
            try:
                _temple_flag = w._analyzer.read_bytes(
                    w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
            except (OSError, AttributeError):
                _temple_flag = None
            try:
                from temple_dialog_reader import classify_temple_phase
                _temple_phase, _temple_phase_vals = (
                    classify_temple_phase(w._analyzer, w._anchor))
            except Exception:  # noqa: BLE001
                _temple_phase = ""
                _temple_phase_vals = {}
            try:
                from active_template_reader import (
                    read_active_template_candidates as _ratc,
                    template_surface_kind as _tsk,
                    input_prompt_facility as _ipf,
                )
                _temple_cand_descs = []
                for _c in _ratc(w._analyzer, w._anchor):
                    _ck = _tsk(_c) or ""
                    _cf = _ipf(_c) or ""
                    if _ck or _cf:
                        _temple_cand_descs.append(
                            f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
                _temple_cands = ",".join(_temple_cand_descs[:6])
            except Exception:  # noqa: BLE001
                _temple_cands = ""

            _temple_dbg_key = (
                _is_temple_ctx, _temple_sub_key, _temple_owner,
                _temple_surface, _shop_img_name, _temple_phase,
                _temple_cands,
            )
            if _temple_dbg_key != getattr(
                    w, "_temple_view_dbg_key", None):
                w._temple_view_dbg_key = _temple_dbg_key
                _log.warning(
                    "temple view dbg: sub=%s view(+0x8F6E)=%s "
                    "flag(+0x8F74)=%s phase=%s vals=%s "
                    "surface=%r owner=%r img=%r text=%r cands=[%s] "
                    "ctx_temple=%s",
                    (_temple_sub_key.rsplit(".", 1)[-1]
                     if _temple_sub_key else "none"),
                    (f"0x{_temple_view:04X}"
                     if _temple_view is not None else "None"),
                    (f"0x{_temple_flag:02X}"
                     if _temple_flag is not None else "None"),
                    _temple_phase, _temple_phase_vals,
                    _temple_surface, _temple_owner,
                    _shop_img_name, _temple_text[:48],
                    _temple_cands, _is_temple_ctx)
            w._temple_view_dbg_prev_ctx = _is_temple_ctx

        # 宿屋店主会話のサブ画面認識を接続バーへ表示 + デバッグ計測。
        # 目的: (1) 人間が実画面と認識サブ状態を突き合わせられるようにする、
        #       (2) フォアグラウンド判別子 (+0x8F6E / +0x8F74) の値を遷移時
        #          だけログ採取し、各サブ画面の base 差を確定する材料にする。
        # ここでは値の収集と可視化のみで、判定本体 (= IMG/ptr 経路) は変えない。
        _is_tavern_ctx = (_facility_key == "recognition.facility_tavern")
        if _is_tavern_ctx or getattr(
                w, "_tavern_view_dbg_prev_ctx", False):
            try:
                # 1軸化: 接続バーのサブ状態は単一判定 _tview の結論を使う。
                _tv_sub_key = getattr(
                    getattr(w, "_tavern_view", None), "bar_key",
                    "") or ""
                _tv_shop_kind = (
                    getattr(_shop_state, "kind", "none")
                    if _shop_state is not None else "none")
                _tv_owner_kind = (
                    getattr(_shop_state, "owner_kind", "")
                    if _shop_state is not None else "")
                _tv_surface = (
                    getattr(w, "_active_tmpl_surface_kind_prev", "")
                    or "")
                _tv_owner = getattr(w, "_panel_owner", "") or ""
            except (AttributeError, ImportError):
                _tv_sub_key = ""
                _tv_shop_kind = "none"
                _tv_owner_kind = ""
                _tv_surface = ""
                _tv_owner = ""

            # 対案 (Enter counter offer) など、どの owner にも採用され
            # ていない active_template 候補を診断するため、候補の
            # (surface:facility) を採取する (= 翻訳未表示の切り分け用)。
            _tv_cands = ""
            try:
                from active_template_reader import (
                    read_active_template_candidates as _ratc,
                    template_surface_kind as _tsk,
                    input_prompt_facility as _ipf,
                )
                _cand_descs = []
                for _c in _ratc(w._analyzer, w._anchor):
                    _ck = _tsk(_c) or ""
                    _cf = _ipf(_c) or ""
                    if _ck or _cf:
                        _cand_descs.append(
                            f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
                _tv_cands = ",".join(_cand_descs[:6])
            except Exception:  # noqa: BLE001
                _tv_cands = ""

            # フォアグラウンド判別子の生値 (= 選択状態側の信号)
            try:
                _vd_raw = w._analyzer.read_bytes(
                    w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
                _tv_view = _vd_raw[0] | (_vd_raw[1] << 8)
            except (OSError, AttributeError):
                _tv_view = None
            try:
                _tv_flag = w._analyzer.read_bytes(
                    w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
            except (OSError, AttributeError):
                _tv_flag = None
            try:
                _tv_ptr = (getattr(_shop_state, "ptr", None)
                           if _shop_state is not None else None)
            except AttributeError:
                _tv_ptr = None

            # 接続バーへサブ状態を併記 (= 認識状態の可視化)。
            if _is_tavern_ctx and _tv_sub_key:
                try:
                    _conv_label = _conv_label + i18n.tr(_tv_sub_key)
                except (AttributeError, ImportError):
                    pass

            # 遷移時のみログ: 認識状態 (sub_key/shop_kind/surface/owner)
            # または候補集合・img が切り替わった poll だけ出力する。
            # ptr は探索中に毎 poll 変動しノイズになるため dedup key から
            # 除外し、メッセージにのみ載せる。
            # 診断: 反復忍込で NPC 会話経路が忍込確認を奪う症状を
            # 追うため、NPC 会話状態と active session 名も採取する。
            _tv_npcconv = bool(
                getattr(w, "_npc_conversation_active", False))
            _tv_sess = _active_session_name_for_label or ""
            _tv_dbg_key = (
                _is_tavern_ctx, _tv_sub_key,
                _tv_shop_kind, _tv_owner_kind, _tv_surface, _tv_owner,
                _tv_cands, (_shop_img_name or ""),
                _tv_npcconv, _tv_sess,
            )
            if _tv_dbg_key != getattr(w, "_tavern_view_dbg_key", None):
                w._tavern_view_dbg_key = _tv_dbg_key
                # 計測ログは既定 WARNING レベルでも採取できるよう
                # warning で出す (= 遷移時のみ・低頻度の診断)。
                _log.warning(
                    "tavern view dbg: sub=%s view(+0x8F6E)=%s "
                    "flag(+0x8F74)=%s shop_kind=%s owner_kind=%r "
                    "surface=%r owner=%r ptr=%s img=%r cands=[%s] "
                    "npcconv=%s sess=%r recov=%s ctx_tavern=%s",
                    (_tv_sub_key.rsplit(".", 1)[-1]
                     if _tv_sub_key else "none"),
                    (f"0x{_tv_view:04X}" if _tv_view is not None
                     else "None"),
                    (f"0x{_tv_flag:02X}" if _tv_flag is not None
                     else "None"),
                    _tv_shop_kind, _tv_owner_kind, _tv_surface,
                    _tv_owner,
                    (f"0x{_tv_ptr:04X}" if _tv_ptr is not None
                     else "None"),
                    _shop_img_name, _tv_cands,
                    _tv_npcconv, _tv_sess,
                    getattr(w, "_yesno_menu_recovery_last", False),
                    _is_tavern_ctx)
            w._tavern_view_dbg_prev_ctx = _is_tavern_ctx

        # 接続バー（画面名）の描画は _screen_id_stable 確定後にまとめて
        # 行う（bounce / bonus hold / char page settle の結果を反映する
        # ため）。ここで算出した _indicator / _facility_label / _conv_label
        # / _screen_name は確定後の合成で使う。
        w._anchor_lbl.setText(
            i18n.tr("connection.img_info", img=_img_name or "—"))

        # 時間ベース debounce を完全に撤去（state-based 検出）。
        # 旧 IMG-family hold は新アルゴリズムで不要：
        #   - flag_status=1 + flag_equipment=1 → equipment（transient flag glitch
        #     も含めて式自体が抑える）
        #   - flag_status=0 ならキャラポップアップから抜けたとみなし、
        #     popup_open / img で automap/logbook/system_menu/game_world を判定
        _screen_id_stable = _screen_id

        # 旧 spell_detail bounce 保護は撤去。spellbook/spell_detail の弁別を
        # 不安定な flag_spell_detail (0x1AEA) から SPELL_VIEW_OFFSET (0x8F6E)
        # へ移したため、flag の bounce を補償する skip_n 機構は不要 (むしろ
        # 正しい spell_detail を抑制し得るため有害)。

        # ボーナス割り振り画面 = レベルアップ中のキャラクター画面。
        # 通常のステータス画面も CHARSTAT.IMG / PAGE2.IMG / MRSHIRT.IMG 等を
        # 使うため img だけでは区別できない。レベルアップ中か
        # (_level_up_active) で区別し、レベルアップ中だけボーナス画面として
        # 1 つの分離状態に保持する。
        #
        # 突入: レベルアップ中に CHARSTAT.IMG (= bonus_screen) を検出した時点。
        # 保持: 画面を閉じる (flag_status==0) まで継続。割り振りが完了
        #       (bonus_pts==0) しても画面が開いている間は保持し、内部の
        #       CHARSTAT→UPDOWN→MRSHIRT 循環で魔法一覧等へ倒れないようにする。
        # 離脱: flag_status==0 (= 画面を閉じた) / レベルアップ完了。
        # レベルアップ外の CHARSTAT は通常ステータス画面 (status_page) とする。
        #
        # 保持中は equipment / spellbook / spell_detail / status_page の
        # 判定をボーナス画面で上書きし、循環中の誤判定を防ぐ。
        try:
            # +0x12BA = flag_status (キャラポップアップ family active = 1)
            _b126_flag_status = w._analyzer.read_bytes(
                w._anchor + 0x12BA, 1)[0]
        except (OSError, AttributeError):
            _b126_flag_status = 0
        try:
            _b126_dialog_byte = w._analyzer.read_bytes(
                w._anchor + 0xA845, 1)[0]
        except (OSError, AttributeError):
            _b126_dialog_byte = 0
        try:
            # +0x129C = BONUS PTS (レベルアップ時に > 0、割り振り完了で 0)
            _b126_bonus_pts = w._analyzer.read_bytes(
                w._anchor + 0x129C, 1)[0]
        except (OSError, AttributeError):
            _b126_bonus_pts = 0

        # 突入 / 保持 / 離脱 / 上書きの判定は pure helper に集約 (P2-1a)。
        # 副作用 (ログ / marker クリア / hold state 代入) は本経路で適用し、
        # 挙動 (_screen_id_stable / hold の決定結果) は従来と同一に保つ。
        _in_levelup = bool(getattr(w, "_level_up_active", False))
        from controllers.screen_finalize import resolve_bonus_screen
        _bonus_pre_screen = _screen_id_stable
        _bonus_res = resolve_bonus_screen(
            _screen_id_stable, _in_levelup, _b126_flag_status,
            getattr(w, "_bonus_screen_hold", False))
        if _bonus_res.log_start:
            _log.info(
                "bonus_screen hold START (level-up character screen)")
        w._bonus_screen_hold = _bonus_res.hold_active
        if _bonus_res.clear_spell_markers:
            # ボーナス画面は別分離。その img 循環が魔法詳細の表示状態
            # (marker) を汚して持ち越さないようクリアする。
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        if _bonus_res.log_end:
            _log.info(
                "bonus_screen hold END (flag_status=%d in_levelup=%s bonus_pts=%d)",
                _b126_flag_status, _in_levelup, _b126_bonus_pts)
        if _bonus_res.log_override:
            _log.debug("bonus_screen hold OVERRIDE: %s → bonus_screen",
                       _bonus_pre_screen)
        # 接続バーは _screen_id_stable 確定後に一括描画するため、
        # ここでは個別更新しない。
        _screen_id_stable = _bonus_res.screen_id_stable

        # キャラクター画面 (ステータス画面) を開いた直後の page 過渡吸収。
        # ゲームが紙人形 img (0EQUIP.CIF) を先に出すため equipment が一瞬
        # 検出されチラつく。開いた直後はステータスページが現れるまで
        # status_page を表示し、ステータス画面を 1 つの分離として扱う。
        # レベルアップ中 (= ボーナス画面) は対象外。
        _CHAR_PAGES = ("status_page", "equipment",
                       "spellbook", "spell_detail")
        if _b126_flag_status == 1 and getattr(
                w, "_char_screen_flag_prev", 0) == 0:
            # flag_status 0→1 (= 画面を開いた瞬間) → 抑制開始
            w._char_screen_settling = True
            w._char_screen_budget = 20
        w._char_screen_flag_prev = _b126_flag_status
        if (_b126_flag_status == 1 and not _in_levelup
                and _screen_id_stable in _CHAR_PAGES):
            from normal_play.char_screen_page import settle_char_page
            (_screen_id_stable,
             w._char_screen_settling,
             w._char_screen_budget) = settle_char_page(
                _screen_id_stable,
                getattr(w, "_char_screen_settling", False),
                getattr(w, "_char_screen_budget", 0))
        elif _b126_flag_status != 1:
            w._char_screen_settling = False
            w._char_screen_budget = 0

        # 魔法画面 family (spellbook) の 一覧/詳細/名称変更 を SPELL_VIEW で判別。
        # base (=一覧値) はキャラクター画面を開いている間 (flag_status=1) 保持する。
        # 魔法画面の img は循環し一瞬 CHARSTAT 等で status_page へ倒れるため、
        # screen_id で active を判定すると base を詳細画面上で誤再捕捉してしまう。
        # そこで flag_status=1 の間は base を保持し、閉じた (=0) ら破棄する。
        if _b126_flag_status == 0:
            if getattr(w, "_spell_screen_active", False):
                w._spell_screen_active = False
                w._spell_view_base = None
        if _screen_id_stable == "spellbook":
            try:
                from screen_detector import (
                    FLAG_SPELL_DETAIL_OFFSET,
                    SPELL_VIEW_OFFSET,
                )
                _sv = w._analyzer.read_bytes(
                    w._anchor + SPELL_VIEW_OFFSET, 1)[0]
                _flag_spell_detail = w._analyzer.read_bytes(
                    w._anchor + FLAG_SPELL_DETAIL_OFFSET, 1)[0]
                _spell_name_for_class = w._analyzer.read_bytes(
                    w._anchor + 0x581A, 33
                ).split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").strip()
            except (OSError, AttributeError):
                _sv = None
                _flag_spell_detail = None
                _spell_name_for_class = ""
            if _sv is not None:
                if _flag_spell_detail == 0xFF:
                    w._spell_view_base = _sv
                    w._spell_screen_active = True
                elif (not getattr(w, "_spell_screen_active", False)
                      and _flag_spell_detail == 0x00):
                    w._spell_view_base = None
                    w._spell_screen_active = True
                elif not getattr(w, "_spell_screen_active", False):
                    w._spell_view_base = _sv
                    w._spell_screen_active = True
                from controllers.spell_view import (
                    classify_spell_screen,
                    classify_spell_view,
                )
                _spell_base = getattr(w, "_spell_view_base", None)
                _spell_before = _screen_id_stable
                _spell_by_delta = classify_spell_view(
                    _sv, _spell_base)
                _screen_id_stable = classify_spell_screen(
                    _screen_id_stable, _img_name, _sv,
                    _spell_base,
                    previous_screen_id=getattr(
                        w, "_screen_id_prev", None),
                    flag_spell_detail=_flag_spell_detail,
                    spell_name=_spell_name_for_class)
                if (_screen_id_stable != _spell_by_delta
                        and _screen_id_stable == "spell_detail"):
                    _delta = ((_spell_base - _sv) & 0xFF
                              if _spell_base is not None else None)
                    _diag_sig = (
                        _spell_before, _screen_id_stable, _img_name,
                        _sv, _spell_base, _delta,
                        getattr(w, "_screen_id_prev", None),
                        _flag_spell_detail, _spell_name_for_class,
                    )
                    if _diag_sig != getattr(
                            w, "_spell_screen_diag_prev", None):
                        w._spell_screen_diag_prev = _diag_sig
                        _log.warning(
                            "spell_detail fallback: raw=%s final=%s "
                            "img=%r sv=0x%02X base=%s delta=%s "
                            "prev=%r flag_detail=%s name=%r",
                            _spell_before, _screen_id_stable,
                            _img_name, _sv,
                            (f"0x{_spell_base:02X}"
                             if _spell_base is not None else "None"),
                            (f"0x{_delta:02X}"
                             if _delta is not None else "None"),
                            getattr(w, "_screen_id_prev", None),
                            (f"0x{_flag_spell_detail:02X}"
                             if _flag_spell_detail is not None
                             else "None"),
                            _spell_name_for_class[:48])

        # 接続バー（画面名）を確定済み _screen_id_stable から 1 回だけ描く。
        # raw 検出名は安定化前の値のため、stable が raw と変わった場合は
        # stable id の画面名を使う（開く途中の equipment 過渡 / bonus 補正を反映）。
        from controllers.recognition_label import (
            resolve_stable_screen_name, format_recognition_label,
        )
        if settings.get("show_recognition_screen", True):
            _stable_screen_name = resolve_stable_screen_name(
                _screen_id_stable, _screen_id, _screen_name, i18n.tr)
            # 原則 (判定と描画を層ごとに閉じる): 施設(L3/L4)/会話ラベルは
            # 親であるトップレベルが normal-play のときのみ合成する。
            # pregame/chargen 等では下層メモリ(interior_mif 等)が stale でも
            # 上位の描画 (= indicator + screen_name, 例 "[A] 起動中") を下層
            # 断片で上書きさせない。normal-play 時は従来と完全同一。
            _label_top_normal = (_current_top_level(w) == "normal-play")
            _recog_label = format_recognition_label(
                _stable_screen_name, _indicator,
                _facility_label if _label_top_normal else "",
                _conv_label if _label_top_normal else "")
            w._status_lbl.setText(
                i18n.tr("connection.status_connected",
                        screen=_recog_label))
        else:
            w._status_lbl.setText(
                i18n.tr("connection.status_connected_no_screen"))

        # chargen_ui_state の自動制御。
        # NPC 検出に依存せず、screen_id の分類で hide/show を切替。
        # 通常プレイ画面（status_page / equipment / spellbook / spell_detail /
        # automap / logbook / game_screen）以外では座標表示等を hide する。
        # 該当: chargen subscreen / boot 画面 / loading / unknown 等。
        # スクロール時の lookup 失敗で更新が止まる問題にも対応。
        _PLAY_SCREEN_IDS = {
            "game_screen", "status_page", "bonus_screen",
            "equipment", "spellbook", "spell_detail",
            "automap", "logbook",
        }
        _desired_chargen_ui = _screen_id_stable not in _PLAY_SCREEN_IDS
        if w._is_in_chargen != _desired_chargen_ui:
            w._set_chargen_ui_state(_desired_chargen_ui)

        # 通常プレイ中のステータス/ボーナス画面 →
        # 翻訳タブを AttributesPanel (choose_attributes) 表示へ。画面駆動で
        # 高優先 (= 背景翻訳 push に勝つ) に提案するため、flush の単一権威が
        # 確定し、旧来の「毎ポール panel_mode 読取→再 set」防御的再アサートは不要。
        # 画面を離れた最初の poll で translate を提案し、単一権威が床 (map/status)
        # へ確定する。
        # chargen 中の能力値画面 (= status_page/bonus_screen) は chargen の
        # 単一権威 render_chargen_view が所有する (panel 可視/モーダルで choose_attributes
        # と translate を判定)。ここで奪わないよう normal-play に限定する。
        # bonus_screen 中は AttributesPanel に scale 切替＋BONUS PTS 表示を伝える
        try:
            if (_screen_id_stable in ("status_page", "bonus_screen")
                    and _current_top_level(w) == "normal-play"):
                w._ui_router.set_panel_mode(
                    "choose_attributes", priority=_SCREEN_PANEL_PRIORITY,
                    reason="screen:status")
                w._b24_status_mode_active = True
            elif getattr(w, "_b24_status_mode_active", False):
                w._ui_router.set_panel_mode(
                    "translate", reason="screen:status_exit")
                w._b24_status_mode_active = False
        except (AttributeError, RuntimeError):
            pass

        # ステータスパネルの解釈状態 (_chargen_mode / _is_bonus_screen) を
        # 単一の純判定 classify_status_panel_state で poll ごとに1回確定し、
        # 同一 poll・同一軸・同一箇所で両フラグを供給する (= 混在駆動の解消)。
        # 旧構造: _is_bonus_screen は毎poll (screen_id 軸)・_chargen_mode は
        # トップレベル遷移イベント駆動 (top_level 軸) で別々に供給され、過渡で
        # 不整合 (chargen_mode stale) になり得た (= 多権威・無調停)。判定式は
        # 従来と同値で、駆動様式 (同一 poll での同期確定) のみ単一化する。
        # (翻訳 / ステータス両タブは同一 AttributesPanel インスタンスを共有)。
        from normal_play.status_overlay import classify_status_panel_state
        _status_panel_state = classify_status_panel_state(
            top_level=_current_top_level(w),
            screen_id_stable=_screen_id_stable,
        )
        try:
            w._tab_status.set_chargen_mode(_status_panel_state.chargen_mode)
            w._tab_status.set_is_bonus_screen(
                _status_panel_state.is_bonus_screen)
        except AttributeError:
            pass

        # screen_id 変化検出 → on_screen_id_changed 通知
        # MRSHIRT.IMG 内の equipment/spellbook タブ切り替えは img_name が変わらないため
        # screen_id（フラグベース）の変化で検出する。
        # デバウンス済みの _screen_id_stable を使用してチラつき防止。
        if _screen_id_stable != w._screen_id_prev:
            w._screen_id_prev = _screen_id_stable
            w._img_screen.on_screen_id_changed(_screen_id_stable)

        # パネル resync — 適切な panel_mode でない場合や
        # 詳細画面で表示中の呪文が変化した場合に再描画。
        #   spell_detail: Next/Previous Spell で表示が切り替わるため
        #                 spell name バッファ（+0x581A）を marker として
        #                 監視し、変化時に再描画。
        #   equipment / spellbook: panel_mode != "equipment" なら復帰。
        _poll_screen_panel_and_spell_detail(w, _screen_id_stable)

        # P2-2: レベルアップ表示 consumer。確定 _screen_id_stable を
        # 読み、producer が継続を許可した場合のみ実行する。これにより
        # bonus_screen 判定が前フレーム値 (_screen_id_prev) でなく現
        # フレームの確定値を参照する (= 1 フレーム遅れを解消)。
        if _level_up_continue:
            from normal_play.level_up_module import (
                consume_level_up_display as _consume_level_up_display,
            )
            _consume_level_up_display(
                w,
                screen_id_stable=_screen_id_stable,
                b30_dialog_active=_b30_dialog_active,
                b30_dialog_active_prev=_b30_dialog_active_prev,
                b30_red_changed=_b30_red_changed,
                npc_dialog_changed=_npc_dialog_changed,
            )

        # モーダル UI (階層外の一時的な重なり表示) の明示系統。
        # 種別はここで 1 回だけ確定し (classify_modal_overlay)、各モーダル
        # 表示単位はその結論を消費する (= 判定描画セット。階層状態は維持)。
        from normal_play.modal_overlay import (
            classify_modal_overlay as _classify_modal_overlay,
        )
        _modal_kind = _classify_modal_overlay(_screen_id_stable)

        # logbook (ジャーナル) 表示はモーダル系統の消費者。
        from normal_play.journal_module import (
            poll_journal as _poll_journal,
        )
        _poll_journal(w, modal_kind=_modal_kind)
    except (ImportError, OSError, AttributeError):
        pass  # 検出失敗時は前回表示を維持


# C1(ダンジョン)文脈の描画 surface ディスパッチと ② NPC popup
# (POPUP11/ASK ABOUT?) クラスタは normal-play 分離化単位
# (normal_play_render) が所有する。poll_controller は alias 経由で呼ぶ
# (= L1 描画所有の node 化・挙動不変の物理移管)。
from normal_play import normal_play_render as _normal_play_render  # noqa: E402
from normal_play.normal_play_render import (  # noqa: E402
    poll_c1_surface_dispatch as _poll_c1_surface_dispatch,
    _poll_npc_popup_display,
    _poll_facility_render_dispatch,
    _poll_l4_dialog_dispatch,
)

# テスト/外部互換の re-export (実体は normal_play_render が単一所有)。
_ASK_ABOUT_MAIN_RECOVERY_STATE = (
    _normal_play_render._ASK_ABOUT_MAIN_RECOVERY_STATE)
blocks_ask_about_main = _normal_play_render.blocks_ask_about_main
ask_about_main_display_allowed = (
    _normal_play_render.ask_about_main_display_allowed)
_render_ask_about_main_recovery = (
    _normal_play_render._render_ask_about_main_recovery)
_classify_popup11_substate = _normal_play_render._classify_popup11_substate
_render_popup11_substate = _normal_play_render._render_popup11_substate
_poll_npc_conversation_foreground = (
    _normal_play_render._poll_npc_conversation_foreground)
_unified_facility_node = _normal_play_render._unified_facility_node
_UNIFIED_DISPATCH_FACILITIES = (
    _normal_play_render._UNIFIED_DISPATCH_FACILITIES)
_poll_compute_temple_gate = _normal_play_render._poll_compute_temple_gate
_poll_shared_negotiation_and_template = (
    _normal_play_render._poll_shared_negotiation_and_template)


def _poll_screen_panel_and_spell_detail(w, _screen_id_stable):
    """画面確定(_screen_id_stable)駆動の翻訳タブ panel_mode 切替 +
    spell_detail(呪文詳細)描画を poll() から純粋抽出 (de-bloat・挙動不変)。
    spell_detail / spellbook / race_select / equipment 画面と、それ以外への
    復帰(translate)を扱う。全状態は w.* に保持し追加の戻り値はない。
    """
    try:
        panel = w._tab_translate.panel_mode()
        if _screen_id_stable == "spell_detail":
            # 呪文識別用 marker（先頭 16 bytes の name バッファ）
            try:
                marker = w._analyzer.read_bytes(
                    w._anchor + 0x581A, 16)
            except (OSError, AttributeError):
                marker = b""
            # 効果テキストは name より遅れて +0x1044 に書かれる。
            # bool(text_en) 判定だけでは、直前の呪文効果や呪文名の
            # 残留を「準備完了」と誤認するため、バッファ変化も再描画条件にする。
            try:
                text_marker = w._analyzer.read_bytes(
                    w._anchor + 0x1044, 96)
            except (OSError, AttributeError):
                text_marker = b""
            marker_prev = getattr(w, "_spell_detail_marker", None)
            text_marker_prev = getattr(w, "_spell_detail_text_marker", None)
            text_ready = getattr(w, "_spell_detail_text_ready", True)
            # panel 不一致 / spell marker 変化 / effect text 未書込み /
            # effect text buffer 変化 のいずれかで再描画。
            if (panel != "spell_detail"
                    or marker != marker_prev
                    or text_marker != text_marker_prev
                    or not text_ready):
                w._spell_detail_marker = marker
                w._spell_detail_text_marker = text_marker
                w._img_screen._show_spell_detail_screen()
        elif _screen_id_stable == "equipment":
            # インベントリメモリ変化検出 — 装備 ON/OFF を即時反映。
            # panel 不一致 or インベントリ変化のいずれかで再描画する。
            try:
                _inv_marker = w._analyzer.read_bytes(
                    w._anchor + 0x0212, 19 * 40)
            except (OSError, AttributeError):
                _inv_marker = None
            if (panel != "equipment"
                    or _inv_marker != w._equipment_marker):
                w._equipment_marker = _inv_marker
                w._img_screen._show_equipment_screen()
            # spell_detail を離れたので marker / text_ready をクリア
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        elif _screen_id_stable == "spellbook":
            if panel != "equipment":
                w._img_screen._show_spellbook_screen()
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        elif _screen_id_stable == "race_select":
            # 種族選択拡張。race_select は chargen 専用画面で
            # あり、panel_mode は chargen の単一権威 render_chargen_view が確定する
            # (種族一覧 race_list と説明ポップアップ translate を panel 可視/dlg flag で
            # 判定)。ここでは画面駆動の mode 設定を行わず marker のみクリアする。
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        else:
            # race_list / equipment / spell_detail 以外の画面に戻ったら translate を
            # 提案し、単一権威が床 (map/status・chargen は translate) へ確定する。
            if panel in ("race_list", "equipment", "spell_detail"):
                w._ui_router.set_panel_mode("translate", reason="screen:exit")
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
    except (AttributeError, RuntimeError):
        pass


class PollController:
    """メインポーリングループのハンドラ。AssistWindow を back-reference として保持する。"""

    def __init__(self, window):
        self._w = window

    def poll(self):
        w = self._w
        if not w._analyzer:
            return
        # フリーズ調査用: 状態遷移判断ごとの所要 (ms) を記録する受け皿。
        # poll 完了後に assist_window._poll() が総時間と内訳を 1 行で出力する。
        w._poll_phase_times = {}
        w._poll_t0 = time.perf_counter()
        w._poll_checkpoints = []
        ui_router = getattr(w, "_ui_router", None)
        try:
            from arena_bridge import (
                read_game_state, interpret_location,
                check_trigger_flag,
                get_trigger_text_by_index,
                TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ,
                RT_COORD_X_OFFSET, RT_COORD_Z_OFFSET,
                RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK,
                RT_ANGLE_RANGE, RT_ANGLE_NORTH_RAW,
                read_live_buffer, NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN,
                CHARGEN_STATE_OFFSET,
                CHARGEN_Q_SEQ_OFFSET, CHARGEN_Q_ARRAY_OFFSET,
                CHARGEN_DONE_OFFSET,
                NPC_PHASE_ASKING, NPC_PHASE_IDLE, NPC_PHASE_RESPONDING,
                NPC_PHASE_BUILDING_ENTRY,
                read_npc_phase,
                read_interior_flag, is_in_interior,
            )

            # ゲーム状態/RT座標/Interior/INF・MIF名 読取 (純抽出: 9出力・順序固定)
            (gs, rt_x, rt_z, in_interior, interior_raw, state,
             inf_name, mif_name, player_floor) = _poll_read_game_state(w)

            # L1 排他ゲート: 本 poll の L1 (pregame/chargen/normal-play) を
            # 冒頭で一度だけ確定する。normal-play 関心の helper はこのゲート
            # 内でのみ実行する (走る主体の再配置のみで検出信号・閾値は不変。
            # 呼び出し位置・順序も不変 = 検出タイミング保存)。
            _top_is_normal_play = (_current_top_level(w) == "normal-play")

            # 入店遷移検知 + Interior MIF 特定 (純抽出: 4出力・順序固定。
            # 第4値 _just_entered_interior は helper 内エッジで poll 未消費)。
            # L1 排他ゲート: 入店は normal-play 関心。chargen/pregame では
            # 既定値 (mif_name, None, None, False) = 非入店時の現挙動返値。
            _field_facility_active = False
            if _top_is_normal_play:
                (display_mif_name, interior_mif_name,
                 interior_facility_name, _,
                 _effective_in_interior, _field_facility_active) = (
                    _poll_resolve_interior_entry(
                        w,
                        in_interior=in_interior,
                        rt_x=rt_x,
                        rt_z=rt_z,
                        interior_raw=interior_raw,
                        mif_name=mif_name,
                        gs=gs,
                    ))
                # フィールド施設（地下室/神殿/塔）の中は単一ソースで in_interior を
                # 実効 True に引き上げ、以降の全消費者（area 確定/認識階層/マップ/
                # place_text）へ同一値を流す。w._in_interior も整合させる。
                in_interior = _effective_in_interior
                w._in_interior = in_interior
            else:
                (display_mif_name, interior_mif_name,
                 interior_facility_name) = (mif_name, None, None)

            # session_manager の poll を表示経路より前で実行し、active session を
            # 確定する。これにより後段の shop / active_template / negotiation /
            # npc_dialog 表示が active session の所有権を尊重できる。
            # TavernSession active == 店主会話 UI 中 (= shop_menu/shop_buy/
            # shop_rooms/shop_rumor_type のいずれかが進行中)。宿屋在室だけ
            # では active にならないため、宿屋内の一般 NPC との会話は通常の
            # NpcChatSession 経路に乗る。
            # 同じタイミングで NPC 会話判定信号 (+0xA845) を読んで
            # _npc_conversation_active を更新するが、active session が tavern
            # (= 店主会話中) の間は更新を抑止する。
            # NPC phase + SCREEN_IMG名(早期) 読取 (純抽出: 2出力・順序固定)
            (_npc_phase_early, _img_name_early) = (
                _poll_read_npc_phase_and_img(w))

            # L2 area 確定 + poll frame 開始 (純抽出: 2出力・順序固定)
            # 扉種別検出がフィールド施設を確定したら area=C3 を確定する
            # （field_facility_active=フィールドの権威入力・単一determiner分岐）。
            (_resolved_area, _poll_hierarchy_area) = (
                _poll_resolve_area_and_frame(
                    w, mif_name=mif_name, in_interior=in_interior,
                    ui_router=ui_router,
                    field_facility_active=_field_facility_active))

            # B->C 遷移ガード(chargen→normal-play) (純抽出: 出力ローカルなし)
            _poll_chargen_normal_play_transition(
                w, mif_name=mif_name, _img_name_early=_img_name_early)

            # ロード中状態判定 + settle/edge処理 (純抽出: 3出力・順序固定)
            (_img_name_early_upper, _load_edge_start,
             _loading_post_settle) = (
                _poll_resolve_loading_state(
                    w, _img_name_early=_img_name_early))

            # session context 構築 + session_manager poll (純抽出: 出力なし)
            _poll_run_session_manager(
                w,
                _img_name_early=_img_name_early,
                _npc_phase_early=_npc_phase_early,
                in_interior=in_interior,
                _resolved_area=_resolved_area,
                mif_name=mif_name,
                interior_mif_name=interior_mif_name,
            )

            # 施設 latch 追跡 + stop エッジ cleanup (純抽出: 局所入力なし・
            # 下流消費の 10 latch 値を返す。戻り順は helper の return と一致)。
            # L1 排他ゲート: 施設 session は normal-play 関心。chargen/pregame
            # では全 latch 非活性 (現挙動でも active_session なし=同値)。
            # normal_play_state 集約: L1 排他ゲート下の normal-play latch dispatch
            # (施設 latch 追跡 → 神殿 IMG key reset → NPC 会話 latch 更新) を
            # 単一ゲートの cohesive ブロックへ集約する。挙動不変=各 helper は
            # 元々 normal-play 限定 (個別 `if _top_is_normal_play`) で同順・
            # 非 normal-play では latch=既定値で 3 helper とも不走=同値。
            # 施設 session/神殿 key/NPC 会話 latch は normal-play 関心であり、
            # この単一ブロックが node 所有の単一軸 dispatch の足場となる。
            if _top_is_normal_play:
                (_active_facility_name,
                 _tavern_active_now,
                 _temple_active_now,
                 _temple_just_started,
                 _equipment_active_now,
                 _equipment_just_started,
                 _mages_active_now,
                 _mages_just_started,
                 _facility_active_now,
                 _facility_just_started) = _poll_track_facility_latch(w)
                # 神殿 IMG 遷移時の owner key reset。
                _poll_reset_temple_keys_on_img_transition(
                    w,
                    _img_name_early=_img_name_early,
                    _temple_active_now=_temple_active_now,
                )
                # 通常 NPC 会話 latch の更新。chargen 中の +0xA845 残留/転用値での
                # latch 反転と、True→False 遷移時の npc_dialog 表示クリアの誤発火を
                # 構造で遮断する。
                _poll_update_npc_conversation_latch(
                    w,
                    _facility_active_now=_facility_active_now,
                    _facility_just_started=_facility_just_started,
                    _npc_phase_early=_npc_phase_early,
                )
            else:
                (_active_facility_name,
                 _tavern_active_now,
                 _temple_active_now,
                 _temple_just_started,
                 _equipment_active_now,
                 _equipment_just_started,
                 _mages_active_now,
                 _mages_just_started,
                 _facility_active_now,
                 _facility_just_started) = (
                    "", False, False, False, False,
                    False, False, False, False, False)

            # post_session 階層認識診断ログ (純抽出: 出力ローカルなし)
            _poll_log_hierarchy_recognition_post_session(
                w,
                _resolved_area=_resolved_area,
                in_interior=in_interior,
                _npc_phase_early=_npc_phase_early,
                mif_name=mif_name,
                _img_name_early=_img_name_early,
                interior_mif_name=interior_mif_name,
                interior_raw=interior_raw,
            )

            _poll_map_update(
                w, in_interior, interior_raw, player_floor,
                display_mif_name, _resolved_area, interior_mif_name,
                interior_facility_name, state, gs, rt_x, rt_z,
                _img_name_early_upper, _loading_post_settle,
                _facility_active_now)

            # ジャーナル本文の反映は確定 _screen_id_stable の消費者として
            # 後段でまとめて行う (画面判定は screen_detector 側に閉じる)。

            # 店内 UI 翻訳経路:
            # 主信号: `+0xA844` u16 LE pointer (= 現在表示中項目テキストへの
            # anchor 相対 ptr)。指す位置が `+0x725F` span 内 → shop_menu、
            # `+0x1040` span 内 → shop_buy、その他 → none。
            # `+0x725F` / `+0x1040` の buffer 内容そのものは「いま画面に
            # 出ているか」の根拠にしない (= 起動時残留で誤発火する原因)。
            # `+0xA845` は ptr の上位 byte で phase byte ではない。
            # coarse gate: top_level=normal-play AND in_interior AND IMG が
            # OP/LOADSAVE/MENU 等の pregame/system 系でないこと。
            # _npc_conversation_active は変更しない。
            _shop_state = None
            _shop_menu_visible = False
            _shop_buy_active = False
            _shop_img_name = ""
            _tavern_l4_kind = ""
            try:
                from arena_bridge import (
                    SCREEN_IMG_OFFSET as _SI_OFF_S,
                    SCREEN_IMG_MAXLEN as _SI_LEN_S,
                )
                _img_raw_s = w._analyzer.read_bytes(
                    w._anchor + _SI_OFF_S, _SI_LEN_S)
                _shop_img_name = _img_raw_s.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").upper()
            except (OSError, AttributeError, ImportError):
                _shop_img_name = ""

            # YESNO.IMG 固着中の店主メニュー復帰可否 (純抽出: 出力1値)。
            # L1 排他ゲート: 店主メニューは normal-play 関心。非 normal-play
            # では False (消費先 detect_shop_state は coarse gate で不発)。
            if _top_is_normal_play:
                _allow_yesno_menu_recovery = (
                    _poll_resolve_yesno_menu_recovery(
                        w,
                        _shop_img_name=_shop_img_name,
                        _temple_active_now=_temple_active_now,
                    ))
            else:
                _allow_yesno_menu_recovery = False

            # 店内ポップアップ状態検出 (純抽出: 出力 _shop_state の1値)
            _shop_state = _poll_detect_shop_state(
                w,
                _shop_img_name=_shop_img_name,
                in_interior=in_interior,
                _active_facility_name=_active_facility_name,
                _allow_yesno_menu_recovery=_allow_yesno_menu_recovery,
            )

            # 観測ログ:
            #   - kind 変化時
            #   - img_name 変化時
            #   - IMG=NEWPOP.IMG なのに kind ∈ {shop_menu, none} の時
            #     (= 追跡用 hint)
            # 店主会話の単一判定 + 診断ログ (純抽出: 3出力・順序固定)。
            # L1 排他ゲート: 店主会話は normal-play 関心。非 normal-play では
            # 非宿屋既定値 (_tview は _facility_tavern=False のため下流で
            # 未消費・_tavern_l4_kind は shop kind 集合外の "" で等価)。
            if _top_is_normal_play:
                (_tview, _tavern_l4_kind, _facility_tavern) = (
                    _poll_classify_tavern_view_and_log(
                        w,
                        _shop_state=_shop_state,
                        _shop_img_name=_shop_img_name,
                        in_interior=in_interior,
                        _tavern_active_now=_tavern_active_now,
                    ))
            else:
                (_tview, _tavern_l4_kind, _facility_tavern) = (
                    None, "", False)

            # C1 ダイアログ軸の単一 authoritative read (1軸化)。施設 render
            # dispatch (active_template) より前に 1 回だけ読み、active_template /
            # compute_b30_state / c1_surface_dispatch が同一の単一前景を消費する。
            # a845/fg は 1 poll 1値で構造的に排他のため、読取位置を前へ寄せても
            # 前景判定は不変 (排他 = timing 非依存)。in_gameplay は compute_b30_state
            # と同一論理で算出する (_img_name_early は早期確定の SCREEN_IMG 名)。
            _c1_dialog_axis_now = None
            if _poll_hierarchy_area == "dungeon":
                try:
                    from normal_play.c1_dialog_axis import read_c1_dialog_axis
                    _b30_in_gameplay_now = (
                        getattr(w, "_screen_id_prev", None) in (
                            None, "game_screen", "combat", "npc_dialog",
                            "shop", "loading")
                        and (_img_name_early or "").upper() not in (
                            "MRSHIRT.IMG", "PAGE2.IMG", "CHARSTAT.IMG"))
                    _c1_dialog_axis_now = read_c1_dialog_axis(
                        w, c_area=_poll_hierarchy_area,
                        in_gameplay=_b30_in_gameplay_now, update_prev=True)
                except Exception:  # noqa: BLE001
                    _c1_dialog_axis_now = None
            w._c1_dialog_axis_now = _c1_dialog_axis_now

            # === 描画 owner 振り分け (1軸化, 判定描画セット分離) =======
            # 宿屋分離化が active な poll は、店主会話の各子画面の描画・終了時
            # 整理を tavern_render_module へ委譲する (= 描画が宿屋分離化に閉じる)。
            # 以降の shop / negotiation / active_template ブロックは非宿屋施設
            # (神殿等) 専用の共有経路として残す (今回は宿屋のみ移植、神殿は次
            # フェーズで同枠移植)。
            # 神殿 / 武具店 / 魔術師ギルドは自施設ノードが描画を所有する
            # 完全分離。宿屋経路 (poll_tavern_render) にも共有 shop route にも
            # 流さない (= メニュー等を各施設専用 owner に閉じる)。
            # active_session() 単一の真実から解決したノードを共有ゲートの
            # 根拠にする（_temple_active_now / _equipment_active_now /
            # _mages_active_now ラッチから逆算しない）。
            # 施設 render 単一ディスパッチ (4出力=当 poll の描画結論・順序固定)
            (_negot_handled, _active_tmpl_handled,
             _shop_menu_visible, _shop_buy_active) = (
                _poll_facility_render_dispatch(
                    w,
                    _shop_state=_shop_state,
                    _shop_img_name=_shop_img_name,
                    _facility_tavern=_facility_tavern,
                    _tview=_tview,
                    _temple_active_now=_temple_active_now,
                    _tavern_active_now=_tavern_active_now,
                    _tavern_l4_kind=_tavern_l4_kind,
                    _poll_hierarchy_area=_poll_hierarchy_area,
                    _shop_menu_visible=_shop_menu_visible,
                    _shop_buy_active=_shop_buy_active,
                ))


            # ダンジョン突入検出 (live_mif=start.mif):
            #   キャラクター作成中 → 通常プレイ中の遷移は、キャラクター作成完了
            #   (旅立ち画面表示済み = post-chargen 到達) と start.mif 進入の組合せで
            #   発火する。それ以外の残留値・サブ状態フラグには依存しない (5 トリガー
            #   設計)。
            # cinematic 表示中のままダンジョンに入ると残留テキストが出るため翻訳
            # パネルをクリアする。
            # ダンジョン突入(start.mif)検出 (純抽出: 出力ローカルなし)
            _poll_detect_dungeon_entry(w, mif_name=mif_name)

            # トリガー検出
            # トリガー検出 + 発火処理 (純抽出: 出力ローカルなし)。
            # L1 排他ゲート: トリガーは normal-play (C1/C2/C3) 関心。
            # chargen/pregame での残留 flag による誤発火を構造で遮断する。
            if _top_is_normal_play:
                _poll_handle_triggers(
                    w, rt_x=rt_x, rt_z=rt_z, inf_name=inf_name)

            # NPC会話バッファ（キャラ作成等、トリガーシステム外のダイアログ）
            npc_dialog = read_live_buffer(
                w._analyzer, w._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN)
            # NPC_DIALOG 変化フラグを後段の +0x7979 ダイアログハンドラで参照する
            _npc_dialog_changed = (npc_dialog != w._npc_dialog_prev)

            # メッセージバッファ (anchor+0x9A9E、512B)
            # 入店メッセージ / Where is 応答 / イベントメッセージが書き込まれる
            # (viewer_constants.LIVE_BUFFERS の「メッセージ」)。入店メッセージは
            # NPC_DIALOG (0x1044) ではなく必ずこちらに来る。
            try:
                msg_buf = read_live_buffer(w._analyzer, w._anchor + 0x9A9E, 512)
            except (OSError, AttributeError):
                msg_buf = ""
            _msg_buf_prev = getattr(w, "_msg_buf_prev", "")
            _msg_buf_changed = (msg_buf != _msg_buf_prev)
            w._msg_buf_prev = msg_buf

            # NEWPOP popup OPEN ゲート（観測 9 状態確定）。
            # +0xB7C4 == 0x00 で「NEWPOP item popup currently displayed」を直接判定。
            # IMG=NEWPOP.IMG と組み合わせて defense-in-depth で確定。
            #
            # 旧実装では +0x9209 を使用していたが、これは実質「システムメニュー
            # オーバーレイ表示中」フラグだったため、take 経由で探索中に直接戻った
            # 場合（システムメニュー未経由）に popup 閉じが検出されない不具合が
            # あった。+0xB7C4 はシステムメニュー経由か直接探索復帰かに
            # 依存しない真の popup フラグで、9 状態すべてで一貫。
            # NEWPOP ゲート + corpse loot 判定 (純抽出: 2出力・順序固定)。
            # L1 排他ゲート: NEWPOP popup は normal-play 関心。非 normal-play
            # では False 既定 (下流 item_pickup は内部 TOP ゲート済・
            # chargen handler の is_corpse_loot は NEWPOP gate 前提のため
            # 非 normal-play では計算値も False=同値)。未定義にはしない。
            if _top_is_normal_play:
                (_newpop_gate, _is_corpse_loot) = (
                    _poll_compute_newpop_gate(w, npc_dialog=npc_dialog))
            else:
                (_newpop_gate, _is_corpse_loot) = (False, False)

            # 入店メッセージ判定 (TEMPLATE.DAT #0000-#0004 経由)。
            # 入店メッセージは NPC_DIALOG (0x1044) ではなくメッセージバッファ
            # (0x9A9E) に書かれるため、両バッファを候補として lookup を試す。
            #
            # 発火条件 (厳密化): npc_phase == 0x9A (NPC_PHASE_BUILDING_ENTRY)
            # 中のみ。phase が抜けたら msg_buf に入店メッセージが残留しても
            # 反映しない (= NPC会話など他経路に明け渡す)。in_interior 単独では
            # 発火しない (= 店内にいる間ずっと入店翻訳を再適用するのを避ける)。
            try:
                _npc_phase_raw = read_npc_phase(w._analyzer, w._anchor)
            except Exception:  # noqa: BLE001
                _npc_phase_raw = None
            _entry_phase = (_npc_phase_raw == NPC_PHASE_BUILDING_ENTRY)
            _entry_phase_prev = getattr(w, "_entry_phase_prev", False)
            w._entry_phase_prev = _entry_phase

            # +0xA845 == 0x9A は入店メッセージ以外 (店内 NPC click の rebuff 表示中
            # など) でも観測される。entry phase の生値だけで building_entry 経路を
            # 確定させると店内 NPC 翻訳が止まるため、「実際に building_entry として
            # 処理してよい状態」を panel_owner / pending latch と組み合わせて限定する。
            # pending latch: 入店遷移の poll で 0x9A/msg_buf が揃わない場合に
            # 備え、interior enter から表示成功 or entry phase exit までの区間で
            # building_entry 経路を開けておく。1 poll 限定の _just_entered_interior
            # ではメモリ更新が poll をまたいだ場合に取りこぼす。
            _building_entry_pending = bool(
                getattr(w, "_building_entry_pending", False))
            try:
                from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
                _img_now_raw = w._analyzer.read_bytes(
                    w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
                _img_name_now = _img_now_raw.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").upper()
            except (OSError, AttributeError, ImportError):
                _img_name_now = ""
            from normal_play.building_entry_module import (
                should_poll_building_entry as _should_poll_building_entry,
            )
            _building_entry_active = _should_poll_building_entry(
                entry_phase=_entry_phase,
                panel_owner=w._panel_owner,
                pending=_building_entry_pending,
                img_name=_img_name_now,
            )

            # L4 (NPC会話系) claim chain は normal-play L1 系統のみ実行する
            # (L1 排他)。chargen/pregame では building_entry/palace/施設reply/
            # npc_dialog/C1 とも本来の対象状況が成立しないため、残留バッファ
            # への誤発火を構造で遮断する。
            _entry_handled = False
            _instore_resp_handled = False
            if _top_is_normal_play:
                _entry_handled, _instore_resp_handled = (
                    _poll_l4_dialog_dispatch(
                        w,
                        in_interior=in_interior,
                        msg_buf=msg_buf,
                        npc_dialog=npc_dialog,
                        _npc_dialog_changed=_npc_dialog_changed,
                        _npc_phase_raw=_npc_phase_raw,
                        _img_name_now=_img_name_now,
                        _building_entry_active=_building_entry_active,
                        _entry_phase_prev=_entry_phase_prev,
                        _shop_state=_shop_state,
                        _shop_img_name=_shop_img_name,
                        _shop_menu_visible=_shop_menu_visible,
                        _shop_buy_active=_shop_buy_active,
                        _facility_active_now=_facility_active_now,
                        _poll_hierarchy_area=_poll_hierarchy_area,
                        _temple_active_now=_temple_active_now,
                        _temple_just_started=_temple_just_started,
                        _equipment_active_now=_equipment_active_now,
                        _equipment_just_started=_equipment_just_started,
                        _mages_active_now=_mages_active_now,
                        _mages_just_started=_mages_just_started,
                        _negot_handled=_negot_handled,
                        _active_tmpl_handled=_active_tmpl_handled,
                    ))

            # chargen 中の NPC バッファ翻訳 (prologue / class advice /
            # method 選択画面 / 10Q intro 等) は L1=chargen 系統。活性所有は
            # handler 自身の冒頭 guard (top_level != "chargen" で no-op) に
            # あり、caller 側の二重活性判定は持たない (chargen_state.poll の
            # L1 dispatch と同形式)。normal-play の L4 chain からは物理分離。
            from top_level.chargen_state import (
                handle_npc_dialog as _chargen_handle_npc_dialog,
            )
            _chargen_handle_npc_dialog(
                w,
                npc_dialog=npc_dialog,
                entry_handled=False,
                is_corpse_loot=_is_corpse_loot,
            )

            # npc_dialog_prev 更新。
            # 本更新がないと _npc_dialog_changed が永久に True となり、
            # 各種「変化時のみ動作」する経路 (状態テンプレ popup owner reset / 短い
            # npc_dialog 診断ログ等) が連続発火する。
            if _npc_dialog_changed:
                w._npc_dialog_prev = npc_dialog
                w._b21_owns_panel = False

            # 状態テンプレート(FILLED)パース (純抽出: 出力ローカルなし)。
            # L1 排他ゲート: 状態ポップアップは normal-play 関心。chargen の
            # 能力値画面は chargen render が所有し、stale FILLED バッファでの
            # status 上書きを構造で遮断する。
            if _top_is_normal_play:
                _poll_status_template_parse(w, _entry_handled=_entry_handled)

            from normal_play.trigger_module import (
                compute_b30_state as _compute_b30_state,
            )
            # P2-3: in_gameplay 判定へ前回確定画面 id を明示的に渡す
            # (= trigger module 側の _screen_id_prev 直 read を撤去)。値は従来と
            # 同じ前回値のため挙動同一。
            _b30 = _compute_b30_state(
                w, screen_id=getattr(w, "_screen_id_prev", None),
                c_area=_poll_hierarchy_area,
                c1_axis=getattr(w, "_c1_dialog_axis_now", None))
            _b30_dialog_flag = _b30['dialog_flag']
            _b30_red_str = _b30['red_str']
            _b30_red_changed = _b30['red_changed']
            _b30_dialog_active = _b30['dialog_active']
            _b30_dialog_active_prev = _b30['dialog_active_prev']
            _b30_img_name = _b30['img_name']
            _b30_in_gameplay = _b30['in_gameplay']

            _poll_c1_surface_dispatch(
                w, _b30,
                npc_dialog_changed=_npc_dialog_changed,
                inf_name=inf_name, mif_name=mif_name,
                instore_resp_handled=_instore_resp_handled)

            # P2-2: レベルアップ処理を producer (画面確定前) / consumer
            # (画面確定後) に分離。ここでは producer だけ実行し、レベル変化
            # 検出と _level_up_active 更新を行う (= 画面確定の bonus_screen hold
            # 入力を先に用意する)。表示 consumer は確定 _screen_id_stable を読む
            # ため後段 (画面確定後) で呼ぶ。
            from normal_play.level_up_module import (
                produce_level_up_state as _produce_level_up_state,
            )
            _level_up_continue = _produce_level_up_state(
                w,
                loading_active=w._loading_state_active,
                load_edge_start=_load_edge_start,
                loading_post_settle=_loading_post_settle,
            )

            from normal_play.item_pickup_module import (
                poll_item_pickup as _poll_item_pickup,
            )
            # P2-3: 画面 id を明示的に渡す (= item_pickup 側の _screen_id_prev
            # 直 read を撤去)。値は従来と同じ前回値のため挙動同一。
            _poll_item_pickup(
                w,
                newpop_gate=_newpop_gate,
                b30_img_name=_b30_img_name,
                npc_dialog=npc_dialog,
                shop_buy_active=_shop_buy_active,
                shop_menu_visible=_shop_menu_visible,
                screen_id=getattr(w, "_screen_id_prev", None),
            )

            # SCREEN_IMG 名検出 + 変化処理 (純抽出: 出力1値)
            _img_name = _poll_detect_img_name(w)

            # ロード中状態の更新は早期実行ブロック
            # (= `_img_name_early` 直後) に移動済。
            # ここでは何もしない (= 二重計算回避)。同 poll 内で map/level_up が
            # 古い loading 値を参照する regression を防ぐため。
            pass

            # AUTOMAP 独立 poll (純抽出: 出力ローカルなし)。
            # L1 排他ゲート: AUTOMAP は normal-play (探索) 関心。ファイル
            # 取り込みは normal-play 復帰後の初回 poll で行われ内容は同一
            # (chargen/pregame 中に新規探索データは発生しない)。
            if _top_is_normal_play:
                _poll_automap_files(w)

            # NPC会話状態の更新
            # NPC会話判定信号 (+0xA845) を読み、観測値で NPC会話状態を更新する。
            #   0x85 (ASKING) 観測       → NPC会話状態 = True
            #   0x00 (IDLE) 観測         → NPC会話状態 = False
            #   0x10 (RESPONDING) 観測   → 現状値保持（NPC応答中／死体クリック中の二走意性）
            # ロード中状態判定抑止: ロード中状態 (上で更新) の期間は
            #   各種判定フラグが激しく変化するため、NPC会話状態の更新も行わず現状値を
            #   保持する。
            # NPC phase / session_manager.poll / _npc_conversation_active
            # 更新は早期ブロックで実施済。ここでは _npc_phase を
            # 既存変数名で参照可能にするだけ。
            _npc_phase = _npc_phase_early

            _poll_npc_popup_display(
                w, _img_name, _shop_menu_visible, _shop_buy_active)

            from top_level.pregame_state import check_load_save_transition
            check_load_save_transition(
                w, mif_name=mif_name, img_name=_img_name)

            _poll_screen_detect_and_label(
                w, _img_name, mif_name, _resolved_area, player_floor,
                in_interior, _shop_state, _shop_img_name,
                _level_up_continue, _b30_dialog_active,
                _b30_dialog_active_prev, _b30_red_changed,
                _npc_dialog_changed)

            # L1 dispatch (1軸化/階層化): 各 L1 ハンドラは自身の冒頭 guard で
            # 活性を所有する (handle_npc_dialog 同形式)。chargen_state.poll() は
            # top_level != "chargen" で no-op するため、ここでは無条件に呼び、
            # caller 側の活性判定 (top_level 比較) との二重活性判定を撤去する
            # (= 活性所有を L1 node 単一へ)。
            from top_level.chargen_state import poll as _poll_chargen
            _poll_chargen(w)

            if ui_router is not None:
                ui_router.flush_poll_display()

        except OSError:
            w._disconnect()
        except Exception as exc:
            # 抽出後の poll で握り潰されている例外を可視化する。
            _log.exception("Poll error: %s", exc)
            w._sb.showMessage(f"Poll error: {exc}", 5000)

