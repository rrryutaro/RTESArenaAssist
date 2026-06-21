"""shop_popup_detector.py — 店主メニュー / 店アイテム一覧の状態判定。

判定原則:
  shop_menu と shop_buy で **判定経路を分ける**:

  - **shop_menu**: `anchor + 0xA844` u16 LE pointer が `+0x725F` span 内を
    指すとき active。current pointer が「現在 active なメニュー項目」を
    示すため、buffer 残留に騙されずに済む。
  - **shop_buy**: `IMG == NEWPOP.IMG` + `+0xB7C4 == 0x00`
    (= NEWPOP popup foreground open gate) + `+0x1040` parser が drinks を
    返す + shop context。**current pointer は使わない**:
    酒一覧 foreground 中も current_ptr は背景の "Buy Drinks" メニュー項目
    (`0x72A2` 等) に残ったまま動かないため。

判定順は shop_buy > shop_menu (= 酒一覧は店主メニューの前景に表示される)。

`+0x725F` / `+0x1040` の buffer は起動時から残留しうるため、shop_menu は
current pointer、shop_buy は NEWPOP foreground gate を併用し、「buffer に
parseable data がある」だけでは active と認めない。

`+0xA845` (= ptr の上位 byte) を phase byte として使ってはいけない
(`+0xA845 == 0x72` は `ptr = 0x72xx` の上位 byte であって、phase signal
ではない)。

API:
  read_current_text_pointer(analyzer, anchor) -> int | None
  detect_shop_popup_state(analyzer, anchor, *, top_level_state, img_name,
                          in_interior, screen_id="",
                          allow_yesno_menu_recovery=False,
                          active_facility_name="") -> ShopPopupState
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from arena_bridge import ArenaMemoryAnalyzer

from shop_menu_reader import (
    SHOP_MENU_BUFFER_OFFSET,
    SHOP_MENU_BUFFER_MAXLEN,
    parse_menu_groups,
    select_menu_group_by_ptr,
    MenuGroup,
)


# 現在表示中項目テキストへのポインタ (u16 LE、anchor 相対)
# popup11_list_detector の ASK ABOUT? と共通の信号
CURRENT_TEXT_PTR_OFFSET = 0xA844

# NEWPOP popup open gate (shop_buy 判定に流用)
NEWPOP_GATE_OFFSET = 0xB7C4
# NEWPOP item count (shop_buy では使わないが log のため読む)
NEWPOP_COUNT_OFFSET = 0x0FF2

# popup 種別 cache 領域 (観測):
# drinks popup 表示中は ASCII "200\0" (= drink 価格 prefix のキャッシュ)。
# rooms popup 表示中は binary (例: 0x38 0x00 0x0a 0x00)。
# signature 値 (drinks 判定) は宿屋固有のため TavernNode が所有する
# (分離化)。ここは cache 領域の読取 offset (中枢信号) のみを持つ。
POPUP_PRICE_CACHE_OFFSET = 0xA836

# response buffer (NPC 応答 / 入店メッセージ等) の代表的 pointer 値。
# current_ptr がこれらのいずれかなら shop popup ではなく response state。
_RESPONSE_BUFFER_PTRS = frozenset({0x1044, 0x929E, 0x9A9E})

# メニュー帯 span (= +0x725F buffer の範囲)。current_ptr がここを指す場合は
# 従来どおり +0x725F buffer の group を解析する。
_MENU_SPAN = (SHOP_MENU_BUFFER_OFFSET,
              SHOP_MENU_BUFFER_OFFSET + SHOP_MENU_BUFFER_MAXLEN)
# 一部の施設はメニュー項目を +0x725F span の外側の別バッファに置く。その場合
# current_ptr は span 外の項目を指す。ptr 近傍に窓を取り直して同じ parser で
# 解析するための窓 (ptr が指す項目を含む group 全体を覆うよう前後に取る)。
_PTR_MENU_WINDOW_BACK = 0x200
_PTR_MENU_WINDOW_LEN = 0x400

# shop 経路を発火させない top_level_state / screen_id
_SHOP_BLOCKED_TOP_LEVELS = frozenset({"pregame", "chargen"})
_SHOP_BLOCKED_IMGS = frozenset({
    "OP.IMG", "LOADSAVE.IMG", "MENU.IMG",
    "SCROLL01.IMG", "SCROLL02.IMG", "QUOTE.IMG",
})
_SHOP_BLOCKED_SCREEN_IDS = frozenset({
    "system_menu", "loadsave",
    "status_page", "equipment", "spellbook", "spell_detail",
    "bonus_screen", "local_map", "world_map", "logbook",
})


@dataclass
class ShopPopupState:
    """Shop popup の現在状態。"""
    # kind: "none" | "shop_menu" | "shop_buy" | "shop_rooms" |
    #       "shop_rumor_type" | "equipment_list"
    # (shop_rumor_type を含む)
    # 表示 surface の種類。施設の identity (= 所有者) は owner_kind を別途参照。
    kind: str = "none"
    # owner_kind: "" | "tavern" | "temple" | "equipment" | "mages_guild"
    # 同じ kind=shop_menu でも所有施設は owner_kind で区別する。
    # session start / owner gate は owner_kind を使い、kind は表示処理が使う。
    owner_kind: str = ""
    reason: str = ""
    ptr: Optional[int] = None
    ptr_hi: Optional[int] = None
    menu_span: Optional[tuple[int, int]] = None  # (start, end) anchor 相対
    buy_span: Optional[tuple[int, int]] = None
    menu_items: list[str] = field(default_factory=list)
    # ショートカット文字 (頭文字ハイライト) を並列 list で保持。
    # 翻訳タブで [<頭文字>] 接頭辞表記に使う。
    menu_item_hotkeys: list[str] = field(default_factory=list)
    # active group の items 組合せから推定したタイトル英語。
    #   items={Buy Drinks, ..., Exit} → "MENU OPTIONS"
    #   items={General, Work}         → "Rumor Type"
    # 未知パターンは空文字。
    menu_title_en: str = ""
    buy_items: list[dict] = field(default_factory=list)
    room_items: list[dict] = field(default_factory=list)
    # 補助信号
    b7c4: Optional[int] = None  # NEWPOP popup gate (0x00 = open)
    ff2: Optional[int] = None   # NEWPOP item count (診断のみ)
    price_cache: Optional[bytes] = None  # +0xA836-A839 (popup 種別 signal)
    # shop_menu group 診断用
    menu_group_count: Optional[int] = None
    active_menu_group_index: Optional[int] = None
    active_menu_item_spans: Optional[tuple[tuple[int, int], ...]] = None
    # 補助情報
    img_name: str = ""
    top_level_state: str = ""
    screen_id: str = ""
    in_interior: bool = False


# control button group (Yes/No, ACCEPT/COUNTER/REJECT 等) は shop_menu kind
# として MENU OPTIONS 表示せず、negotiation / active_template 経路に委ねる。
_CONTROL_GROUP_TEXTS: frozenset[frozenset[str]] = frozenset({
    frozenset({"Yes", "No"}),
    frozenset({"Yes", "No", "Cancel"}),
    frozenset({"YES", "NO"}),
    frozenset({"YES", "NO", "CANCEL"}),
    frozenset({"ACCEPT", "COUNTER", "REJECT"}),
    frozenset({"Accept", "Counter", "Reject"}),
})


def _is_control_group(items: list[str]) -> bool:
    """Yes/No 等の制御ボタン group か判定 (= shop_menu 表示対象外)。"""
    if not items:
        return False
    return frozenset(items) in _CONTROL_GROUP_TEXTS


# shop_menu buffer 内の active group items 組合せから
# (kind, owner_kind, title_en) 分類表。各施設のメニュー署名を detector に
# 直書きする集中を避け、各施設ノードが自分の ``menu_signatures`` を宣言し、
# ここでは registry 横断で再構築する
# (owner_kind は宣言元ノード名)。未登録の組合せは ("shop_menu", "", "") に
# フォールバック (= 表示は出るが所有不明、ad-hoc 拡張禁止)。
#
# 初回 _classify_menu_group 呼び出し時に遅延構築する (= 全モジュール import 完了後
# に eager import で全ノード登録を保証してから集約)。「再構築 dict == 旧直書き」は
# tests/test_shop_popup_detector の guard が固定する (= 退行防止)。
_MENU_GROUP_KIND_TITLE_CACHE: Optional[dict] = None


def _menu_group_table() -> dict:
    """施設ノードの ``menu_signatures`` 宣言を集約した分類表 (遅延構築・キャッシュ)。"""
    global _MENU_GROUP_KIND_TITLE_CACHE
    if _MENU_GROUP_KIND_TITLE_CACHE is None:
        # eager import: 全施設ノードを登録してから registry を集約する
        # (= 登録漏れによる誤フォールバックを防ぐ)。
        from session import facility_nodes as _fn  # noqa: F401
        from session.facility_node import build_menu_signature_table
        _MENU_GROUP_KIND_TITLE_CACHE = build_menu_signature_table()
    return _MENU_GROUP_KIND_TITLE_CACHE


def _classify_menu_group(items: list[str]) -> tuple[str, str, str]:
    """active group の items 組合せから (kind, owner_kind, title_en) を返す。

    B-2 ③(分離化): 分類表は各施設ノードの ``menu_signatures`` 宣言を registry
    横断で集約したもの (= detector への front-door 集中を解消)。owner_kind は
    宣言元ノード名。未登録パターンは ("shop_menu", "", "") にフォールバック。
    """
    key = frozenset(items)
    return _menu_group_table().get(key, ("shop_menu", "", ""))


def read_current_text_pointer(analyzer: "ArenaMemoryAnalyzer",
                              anchor: int) -> Optional[int]:
    """`anchor + 0xA844` u16 LE pointer を読む。失敗時 None。"""
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        if len(raw) < 2:
            return None
        return raw[0] | (raw[1] << 8)
    except (OSError, AttributeError):
        return None


def _parse_shop_menu_groups(analyzer, anchor) -> list[MenuGroup]:
    """shop_menu buffer (+0x725F) から全 group を抽出する。"""
    try:
        raw = analyzer.read_bytes(
            anchor + SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_menu_groups(raw, base_offset=SHOP_MENU_BUFFER_OFFSET)


def _parse_menu_groups_near_ptr(analyzer, anchor,
                                ptr: int) -> tuple[list[MenuGroup], int]:
    """current_ptr 近傍のメニュー帯を読み (groups, base_offset) を返す。

    メニュー項目を +0x725F span の外側に置く施設 (current_ptr が span 外を指す)
    向け。base_offset は窓先頭の anchor 相対 offset で、parse_menu_groups の
    item span が anchor 相対で揃うように渡す。
    """
    base = ptr - _PTR_MENU_WINDOW_BACK
    try:
        raw = analyzer.read_bytes(anchor + base, _PTR_MENU_WINDOW_LEN)
    except (OSError, AttributeError):
        return [], base
    return parse_menu_groups(raw, base_offset=base), base


def _in_span(ptr: Optional[int], span: Optional[tuple[int, int]]) -> bool:
    if ptr is None or span is None:
        return False
    lo, hi = span
    return lo <= ptr < hi


def _read_u8(analyzer, addr) -> Optional[int]:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return None


def detect_shop_popup_state(
    analyzer: "ArenaMemoryAnalyzer",
    anchor: int,
    *,
    top_level_state: str,
    img_name: str,
    in_interior: bool,
    screen_id: str = "",
    allow_yesno_menu_recovery: bool = False,
    interior_mif_name: str = "",
    active_facility_name: str = "",
) -> ShopPopupState:
    """shop popup 状態を決定的に判定する。

    判定順:
      1. coarse gate: top_level=normal-play, in_interior, img/screen が
         shop を許容するか
      2. **shop_buy** (= 酒一覧 NEWPOP foreground):
         IMG == NEWPOP.IMG AND `+0xB7C4 == 0x00` (NEWPOP popup open gate)
         AND `+0x1040` parser が drinks を返す → kind="shop_buy"
         (current pointer は使わない。酒一覧 foreground 中も
         ptr が背景の Buy Drinks=0x72A2 に残るため)
      3. **shop_menu** (= 店主メニュー):
         current_ptr (+0xA844) が `+0x725F` span 内を指す AND parse 成功
         → kind="shop_menu"
      4. response buffer ptr (0x1044/0x929E/0x9A9E) は shop_menu 候補から除外
      5. いずれにも該当しなければ none
    """
    state = ShopPopupState(
        kind="none",
        img_name=img_name,
        top_level_state=top_level_state,
        screen_id=screen_id,
        in_interior=in_interior,
    )

    # 1. coarse gate: shop は normal-play 中のみ。
    if top_level_state in _SHOP_BLOCKED_TOP_LEVELS:
        state.reason = f"blocked top_level={top_level_state}"
        return state
    if img_name in _SHOP_BLOCKED_IMGS:
        state.reason = f"blocked img={img_name}"
        return state
    if screen_id in _SHOP_BLOCKED_SCREEN_IDS:
        state.reason = f"blocked screen={screen_id}"
        return state
    if not in_interior:
        state.reason = "not in_interior"
        return state

    # 補助信号読み (診断 + shop_buy/shop_rooms gate のため)
    state.b7c4 = _read_u8(analyzer, anchor + NEWPOP_GATE_OFFSET)
    state.ff2 = _read_u8(analyzer, anchor + NEWPOP_COUNT_OFFSET)
    try:
        state.price_cache = analyzer.read_bytes(
            anchor + POPUP_PRICE_CACHE_OFFSET, 4)
    except (OSError, AttributeError):
        state.price_cache = None

    # parser を全て走らせる (span / payload を state に詰める)。
    # 施設固有の読取・signature は各施設ノード所有 (分離化)。判定順序と
    # 相互排他 (中枢固有) は本 detector が単一所有する。lazy import は
    # session 側の lazy detector import と相互で module-level 循環なし。
    from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
    buy_items, buy_span = _TAVERN_NODE.read_shop_buy_span(analyzer, anchor)
    state.buy_span = buy_span
    state.buy_items = buy_items
    # shop_menu groups は全 group + 各 item span を抽出
    menu_groups = _parse_shop_menu_groups(analyzer, anchor)
    state.menu_group_count = len(menu_groups)
    # 後方互換: menu_span は buffer 全長で広く設定 (旧 code 互換、診断用)
    if menu_groups:
        state.menu_span = (SHOP_MENU_BUFFER_OFFSET,
                           SHOP_MENU_BUFFER_OFFSET + SHOP_MENU_BUFFER_MAXLEN)

    # current pointer は shop_rooms より先に解析する。武具店 Sell/Repair の
    # NEWPOP は宿屋部屋データが残留していても、背景メニュー ptr が
    # owner=equipment を示すため、この信号を L4 分離境界として優先する。
    ptr = read_current_text_pointer(analyzer, anchor)
    state.ptr = ptr
    if ptr is not None:
        state.ptr_hi = (ptr >> 8) & 0xFF

    active_group = None
    active_group_list = menu_groups
    active_items_text: list[str] = []
    active_kind = ""
    active_owner = ""
    active_title_en = ""

    if ptr is not None and ptr not in _RESPONSE_BUFFER_PTRS:
        # ptr が item span 内の group を active として選択。group なら
        # menu_items に確定する。group が見つからない場合は first group
        # fallback しない (= hotkey string / pointer table / stale を指す状況で
        # first group 強制表示する誤動作を防ぐ)。
        active_group = select_menu_group_by_ptr(menu_groups, ptr)
        # メニュー項目を +0x725F span の外側に置く施設 (= current_ptr が span 外の
        # 項目を指す) を取りこぼさないための加算的 fallback。span 内で group が
        # 見つかった場合や、ptr が応答帯 / 極端に小さい (= ダイアログ ptr 0x001E /
        # EXIT 0x0054 等) 場合は発火しないため、既存施設 (宿屋 / 神殿) の判定経路は
        # 一切変わらない。fallback は none を検出に変えるだけで既存検出を上書きしない。
        if (active_group is None
                and not _in_span(ptr, _MENU_SPAN)
                and ptr >= _PTR_MENU_WINDOW_BACK):
            near_groups, _near_base = _parse_menu_groups_near_ptr(
                analyzer, anchor, ptr)
            near_active = select_menu_group_by_ptr(near_groups, ptr)
            if near_active is not None:
                active_group = near_active
                active_group_list = near_groups
        if active_group is not None:
            active_items_text = [it.text for it in active_group.items]
            active_kind, active_owner, active_title_en = _classify_menu_group(
                active_items_text)

    room_items_raw = _TAVERN_NODE.read_room_items(analyzer, anchor)
    state.room_items = room_items_raw

    # NEWPOP foreground 共通条件
    _newpop_fg = (img_name == "NEWPOP.IMG"
                  and state.b7c4 == 0x00
                  and (state.ff2 or 0) == 0)
    # drinks signature: +0xA836-A839 == "200\0"。
    # signature 値は宿屋所有 (分離化)。
    _is_drinks_sig = (state.price_cache
                      == _TAVERN_NODE.DRINKS_PRICE_CACHE_SIG)

    # 2. shop_buy 判定 (NEWPOP foreground + drinks signature + buy_items)
    #    drinks signature を厳密に要求 (drinks data stale でも
    #    rooms popup と区別できるように)
    if _newpop_fg and _is_drinks_sig and buy_items:
        state.kind = "shop_buy"
        state.owner_kind = "tavern"  # shop_buy は宿屋の酒一覧のみ
        state.reason = (
            f"NEWPOP fg + drinks_sig + buy_count={len(buy_items)}")
        return state

    # 2-2. 武具店 Sell/Repair 一覧判定。
    # NEWPOP 中に宿屋 room 領域の stale data が残っていると、
    # shop_rooms/tavern が先に確定して武具店 L4 分離境界を破る。背景 ptr が
    # 武具店メニューを示し、かつ Sell/Repair 所持品一覧 (+0x9A6E) が読める
    # 場合は、宿屋 rooms fallback より先に equipment_list として確定する。
    if _newpop_fg and not _is_drinks_sig and active_owner == "equipment":
        try:
            from session.equipment_node import EQUIPMENT_NODE
            equipment_items = EQUIPMENT_NODE.read_sell_repair_items(
                analyzer, anchor)
        except Exception:  # noqa: BLE001
            equipment_items = []
        if equipment_items:
            state.kind = "equipment_list"
            state.owner_kind = "equipment"
            state.menu_items = active_items_text
            state.menu_item_hotkeys = [it.hotkey for it in active_group.items]
            state.active_menu_group_index = active_group_list.index(
                active_group)
            state.active_menu_item_spans = tuple(
                (it.start, it.end) for it in active_group.items)
            state.menu_title_en = active_title_en
            state.reason = (
                f"NEWPOP fg + equipment menu ptr=0x{ptr:04X} "
                f"+ sell_items={len(equipment_items)}")
            return state

    # 3. shop_rooms 判定 (NEWPOP foreground + drinks signature 不在 +
    #    static room data 妥当)。
    # room_items は宿屋の static room area (+0x2892) 由来で、他施設 (武具店
    # Sell/Repair/Steal, 魔術師ギルド Detect/Steal, 神殿 Cure 等) の NEWPOP 一覧でも
    # stale data が残り得る。宿屋以外で shop_rooms=tavern に落とすと施設横断の判定
    # 描画干渉になる (= 売却一覧が宿屋部屋一覧として誤描画)。よって interior_mif が
    # 宿屋であると判る場合のみ tavern 部屋一覧として確定し、それ以外の既知 interior
    # では「未実装の施設 NEWPOP 一覧」として none を返す (= _facility_tavern へ流さ
    # ない)。interior_mif 未指定 (= 後方互換の呼出) は従来どおり tavern とみなす。
    # ただし active_facility_name が非宿屋を示す場合は、後方互換 fallback より
    # 施設 L4 分離境界を優先し、宿屋 shop_rooms として採用しない。
    if _newpop_fg and not _is_drinks_sig and room_items_raw:
        _mif_u = (interior_mif_name or "").upper()
        _active_facility = (active_facility_name or "").lower()
        # 宿屋部屋一覧として確定してよい文脈かは宿屋ノード所有の判定
        # (分離化)。
        _tavern_room_ctx = _TAVERN_NODE.is_room_list_context(
            interior_mif_name=interior_mif_name,
            active_facility_name=active_facility_name)
        if _tavern_room_ctx:
            state.kind = "shop_rooms"
            state.owner_kind = "tavern"  # shop_rooms は宿屋の部屋一覧のみ
            state.reason = (
                f"NEWPOP fg + no drinks_sig (cache=%r) + rooms=%d"
                % (state.price_cache, len(room_items_raw)))
            return state
        # 非宿屋文脈の NEWPOP 一覧 (= 未実装の施設一覧)。宿屋部屋として描画しない。
        state.kind = "none"
        state.owner_kind = ""
        state.reason = (
            f"NEWPOP fg + no drinks_sig but non-tavern interior "
            f"(mif={_mif_u!r} active={_active_facility!r}); "
            f"facility list unimplemented")
        return state

    # 4. shop_menu 判定 (current pointer が item span 内)
    if ptr is None:
        state.reason = "ptr read failed"
        return state

    if ptr in _RESPONSE_BUFFER_PTRS:
        state.reason = f"ptr=0x{ptr:04X} is response buffer"
        return state

    if active_group is not None:
        if _is_control_group(active_items_text):
            state.reason = (
                f"ptr=0x{ptr:04X} in control group "
                f"items={active_items_text}, defer to negotiation/active_template")
            return state
        # YESNO.IMG は宿屋の忍び込み確認 / 価格確認などでも使われる。
        # current_ptr が背景の店主メニューに残る poll があるため、既定では
        # active_template / negotiation へ委譲する。結果表示後の menu 復帰など、
        # 呼び出し側が文脈で安全と判断した場合だけ採用する。
        if (img_name or "").upper() == "YESNO.IMG" and not allow_yesno_menu_recovery:
            state.reason = (
                f"ptr=0x{ptr:04X} in non-control group "
                f"items={active_items_text}, defer YESNO.IMG to active_template")
            return state
        state.menu_items = active_items_text
        state.menu_item_hotkeys = [it.hotkey for it in active_group.items]
        state.active_menu_group_index = active_group_list.index(active_group)
        state.active_menu_item_spans = tuple(
            (it.start, it.end) for it in active_group.items)
        # items 組合せから (kind, owner_kind, title_en) を決定
        state.kind = active_kind
        state.owner_kind = active_owner
        state.menu_title_en = active_title_en
        state.reason = (
            f"ptr=0x{ptr:04X} in group[{state.active_menu_group_index}] "
            f"({len(active_items_text)} items) kind={active_kind} "
            f"owner={active_owner!r} title={active_title_en!r}")
        return state

    state.reason = (
        f"no shop active "
        f"(img={img_name!r} b7c4={state.b7c4} ptr="
        f"{'0x%04X' % ptr if ptr is not None else '?'} "
        f"menu_groups={len(menu_groups)} buy_items={len(buy_items)} "
        f"room_items={len(room_items_raw)})")
    return state


__all__ = [
    "CURRENT_TEXT_PTR_OFFSET",
    "ShopPopupState",
    "read_current_text_pointer",
    "detect_shop_popup_state",
]
