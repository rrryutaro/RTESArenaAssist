"""POPUP11.IMG 下位状態の判別。"""

from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger(__name__)
_LAST_STATE_LOG: dict = {}

POPUP11_ITEM_COUNT_OFFSET = 0x512B
POPUP11_DYN_COUNT_OFFSET  = 0xA860
# ASK ABOUT? sub-state 判定用フィールド（0xA840-0xA858 の NPC dialog context 構造体内）
ASK_ABOUT_ACTIVE_OFFSET   = 0xA847   # NPC dialog active flag (0x3D = active, 0x00 = inactive)
ASK_ABOUT_CURRENT_PTR     = 0xA844   # 現在表示中項目テキストへのポインタ (u16 LE, anchor 相対)
NPC_RESPONSE_BUFFER_PTR   = 0x1044   # 0xA844 がこの値なら response state
MENU_TEMPLATE_RANGE       = (0x8000, 0x9000)  # ASK ABOUT? menu template が存在する範囲


def _read_u8(analyzer, addr: int) -> Optional[int]:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return None


def _decode_arena_menu_item(raw: bytes) -> str:
    """Arena メニュー項目バイト列から表示テキストを抽出する。

    フォーマット: `NN C0 <hotkey_char> NN D4 <rest_chars> 00 ...`
    （NN は 0x00 含む任意の制御バイト）

    例:
      `00 c0 45 00 d4 78 69 74 00 ...` → "Exit"
      `00 c0 57 00 d4 6f 72 6b 00 ...` → "Work"

    0xC0 直後の 1 バイトをホットキー文字とし、続く 0xD4 直後から次の 0x00
    までを残りの文字として連結する。
    """
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 0xC0 and i + 1 < n:
            ch = raw[i + 1]
            if 0x20 <= ch <= 0x7E:
                out.append(chr(ch))
            i += 2
            continue
        if b == 0xD4 and i + 1 < n:
            j = i + 1
            while j < n and raw[j] != 0x00:
                cj = raw[j]
                if 0x20 <= cj <= 0x7E:
                    out.append(chr(cj))
                else:
                    break
                j += 1
            return "".join(out).strip()
        i += 1
    return "".join(out).strip()


def read_active_menu_marker(analyzer, anchor: int) -> str:
    """ASK ABOUT? 文脈で現在表示中メニューの最後の項目テキストを返す。

    機構: anchor + 0xA844 (u16 LE) は「現在表示中項目テキストへの anchor 相対
    ポインタ」を保持する。これは 場所一覧/詳細場所一覧 で 0x5127 が「現在
    表示中項目への ptr」だったのと同じ構造的役割を ASK ABOUT? 系で担う。

    ポインタの指し先（anchor + ptr）は Arena メニュー制御バイト形式
    （NN C0 <hk> NN D4 <rest> 00）で項目バイト列が静的に格納されており、
    _decode_arena_menu_item で表示テキストを抽出できる。

    値（再現を複数回の観測で確認済）:
      ASK ABOUT? main: 0xA844 = 0x8571 → "Exit"
      Rumor Type sub:  0xA844 = 0x859F → "Work"
      NPC 応答:        0xA844 = 0x1044 → "" (menu 項目ではないので空を返す)

    0x929E 直読み版は Arena 描画時の転写コピーで stale リスクが
    あったため、ここでは menu template 内の静的位置を指すポインタを使う。
    """
    try:
        ptr_raw = analyzer.read_bytes(anchor + ASK_ABOUT_CURRENT_PTR, 2)
        if len(ptr_raw) < 2:
            _log_marker_once("ptr_raw_short", None, None, b"")
            return ""
        ptr = ptr_raw[0] | (ptr_raw[1] << 8)
        if ptr == NPC_RESPONSE_BUFFER_PTR:
            _log_marker_once("response_ptr", ptr, None, b"")
            return ""
        lo, hi = MENU_TEMPLATE_RANGE
        if not (lo <= ptr < hi):
            _log_marker_once("ptr_out_of_range", ptr, None, b"")
            return ""
        raw = analyzer.read_bytes(anchor + ptr, 16)
    except (OSError, AttributeError, IndexError) as exc:
        _log_marker_once("read_error", None, None, b"")
        return ""
    decoded = _decode_arena_menu_item(raw)
    _log_marker_once("ok", ptr, decoded, raw)
    return decoded


def _log_marker_once(reason: str, ptr, decoded, raw: bytes) -> None:
    """同一引数で連続する INFO ログを抑止する診断ヘルパー。"""
    key = (reason, ptr, decoded, bytes(raw[:8]))
    if _LAST_STATE_LOG.get("marker") == key:
        return
    _LAST_STATE_LOG["marker"] = key
    if reason == "ok":
        _log.info(
            "read_active_menu_marker: ptr=0x%04X raw=%s decoded=%r",
            ptr or 0, raw.hex(' '), decoded)
    else:
        _log.info(
            "read_active_menu_marker: %s ptr=%s",
            reason, f"0x{ptr:04X}" if ptr is not None else "?")


def detect_popup11_list_state(analyzer, anchor: int) -> str:
    """
    POPUP11.IMG 表示中の下位状態を判別して返す。

    Returns:
        "rumor_type"         — ASK ABOUT? Rumor Type サブメニュー表示中
        "where_is_list"      — Where is... 静的リスト表示中
        "dynamic_place_list" — 動的場所リスト表示中
        "npc_response"       — NPC 応答テキスト（既存経路）

    Rumor Type 検出は 0x5127/0x512B では区別できない（Rumor Type 中も
    0x5127=0x85D3 / item_count=9 のまま）。代わりに 0xA844（現在表示中項目
    テキストへの anchor 相対 ポインタ、場所一覧での 0x5127 と同型の役割）の
    指し先項目テキストで判定する。詳細は read_active_menu_marker 参照。
    """
    item_count = _read_u8(analyzer, anchor + POPUP11_ITEM_COUNT_OFFSET)
    dyn_count  = _read_u8(analyzer, anchor + POPUP11_DYN_COUNT_OFFSET)

    if item_count is None or dyn_count is None:
        return "npc_response"

    # ASK ABOUT? サブメニュー判定（main "Exit" / Rumor Type "Work"）。
    # 0xA844 経由でメニューテンプレ内の項目バイト列にアクセスし decode する。
    # 観測:
    #   - rumor_type 表示中:                  sub_marker = 'Work'
    #   - リスト表示中 (where_is_list / dynamic_place_list / ASK_ABOUT_MAIN): sub_marker = 'Exit'
    #   - NPC 応答表示中:                     sub_marker = '' (項目を指していない)
    #   - 一時 marker (描画過渡期):           sub_marker = 'W' / 'Rumors' / etc
    #
    # メモリ残留問題:
    #   応答中も item_count/dyn_count が直前のメニュー値を保持し、応答後の状態遷移で
    #   どちらかが残留する。具体的には:
    #     - 応答後「どこにある？」: item_count=9 に更新されるが dyn_count=10 残留
    #     - 応答後 ASK_ABOUT_MAIN 復帰: item_count=10/dyn_count=10 のまま (recovery で別途対応)
    #   そのため、where_is_list 判定で dyn_count == 0 を厳格に要求すると場所一覧表示を
    #   見逃す。代わりに「dyn_count != item_count なら where_is_list」と緩める。
    sub_marker = read_active_menu_marker(analyzer, anchor)
    if sub_marker == "Work":
        result = "rumor_type"
    elif sub_marker != "Exit":
        # sub_marker == '' (応答中) or 'W'/'Rumors'/その他一時 marker
        result = "npc_response"
    elif item_count <= 0:
        result = "npc_response"
    elif dyn_count > 0 and dyn_count == item_count:
        # 動的場所一覧: dyn_count と item_count が一致 (応答後 ASK_ABOUT_MAIN 復帰時も
        # この条件にマッチするが、その場合は poll_controller 側の ask_main_recovery で
        # 別途扱う)
        result = "dynamic_place_list"
    else:
        # 場所一覧: item_count > 0 で動的ではない (dyn_count == 0 または残留値 != item_count)
        # dyn_count 残留に対応するため緩い判定にする
        result = "where_is_list"

    # 診断ログ: 同じ判定結果が連続する間は 1 回だけ INFO で出す（poll は 5Hz
    # なので冗長な再出力を抑止）。値が変わった瞬間に追跡できればよい。
    key = (item_count, dyn_count, sub_marker, result)
    if _LAST_STATE_LOG.get("key") != key:
        _LAST_STATE_LOG["key"] = key
        _log.info(
            "detect_popup11_list_state: item_count=%d dyn_count=%d "
            "sub_marker=%r -> %s",
            item_count, dyn_count, sub_marker, result)
    return result
