"""normal_play/palace_dialog_module.py — 宮殿の統治者会話 (L4) 翻訳表示。

宮殿(PALACE*/TOWNPAL*/VILPAL*)在室中、統治者(女王/王)のメインクエスト会話本文を
翻訳パネルへ表示する。他施設(宿屋/神殿/武具店/ギルド)とは完全に分離した独立経路で、
共通の会話処理関数には相乗りしない (L4 は施設ごとに物理分離)。

観測 (Rihad 女王会話) で確定した経路:
- 会話本文は前景テキストポインタ `+0xA844` (u16 LE) が指すバッファに、複数の NUL で
  区切られて格納される。チャンクを順に連結すると全文になり npc_dialog_lookup で一致する。
  提示ページ fg=0x9622 / 応答ページ fg=0x9A9E (いずれも 0x9000-0xA000 帯)。
- Yes/No ページでは fg が選択肢オーバーレイ(帯外, 例 0x8268)を指すため、直前に確定した
  本文オフセットを保持して全文訳を出し続ける。
- 入店メッセージ(「You walk into the ... audience chamber」)は TEMPLATE.DAT 建物入店辞書
  (building_entry) の領分で、npc_dialog_lookup には無いためここでは拾わない (= 分離)。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

# 前景テキストポインタ (u16 LE)。指す先に現在表示中の本文がある。
_FG_PTR_OFFSET = 0xA844
# 会話本文バッファが収まるアンカー相対オフセット帯 (観測: 0x9000-0xA000)。
_DIALOG_OFF_MIN = 0x9000
_DIALOG_OFF_MAX = 0xA000
_OWNER = "palace_dialog"


def is_palace_interior_mif(interior_mif_name: str | None) -> bool:
    u = (interior_mif_name or "").upper()
    return u.startswith(("PALACE", "TOWNPAL", "VILPAL"))


def assemble_dialog_text(raw: bytes) -> str:
    """NUL 区切りの本文チャンクを連結して 1 つの全文にする (pure)。

    先頭から printable チャンクを拾い、最初のゴミ領域 (非 printable 連続) で打ち切る。
    改行 (\\n/\\r) は半角空白へ、連続空白は 1 つへ正規化する。
    """
    chunks: list[str] = []
    for seg in raw.split(b"\x00"):
        s = seg.decode("ascii", errors="replace").strip()
        if not s:
            continue
        printable = sum(1 for c in s if 0x20 <= ord(c) <= 0x7E)
        if len(s) >= 8 and printable / len(s) >= 0.85:
            chunks.append(s)
        elif chunks:
            break  # 本文の後のゴミ領域に達したら終端
    joined = " ".join(c.replace("\n", " ").replace("\r", " ") for c in chunks)
    return " ".join(joined.split())


def _read_full_text(w, off: int) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + off, 1200)
    except (OSError, AttributeError):
        return ""
    return assemble_dialog_text(raw)


def poll_palace_dialog(w, *, palace_active: bool) -> bool:
    """戻り値: 宮殿会話本文の表示を確定した場合 True。

    palace_active=False (退室/非宮殿) では owner を解放して False。
    """
    if not palace_active:
        if w._ui_router.is_owner(_OWNER):
            w._ui_router.release_if_owner(_OWNER)
        w._palace_dialog_last_off = None
        w._palace_dialog_prev_key = None
        return False

    # fg ptr が本文帯を指していれば現在表示中の本文。帯外 (= Yes/No 選択
    # オーバーレイ表示中) は直前に確定した本文オフセットへフォールバックする。
    try:
        fgraw = w._analyzer.read_bytes(w._anchor + _FG_PTR_OFFSET, 2)
        fg = fgraw[0] | (fgraw[1] << 8)
    except (OSError, AttributeError):
        fg = 0
    in_band_fg = _DIALOG_OFF_MIN <= fg <= _DIALOG_OFF_MAX

    try:
        import npc_dialog_lookup as _ndl
    except ImportError:
        return False

    def _emit(off: int, text: str, ja: str, *, yesno: bool) -> bool:
        """本文 (+ 任意で Yes/No) を翻訳パネルへ反映。再 push 抑止つき。"""
        if yesno:
            ja = f"{ja}\n\n  はい\n  いいえ"
        w._palace_dialog_last_off = off
        # 同一表示の連続 push (flicker) は抑止。ただし現在 owner でない
        # (= trigger 等に奪われた) 場合は同一本文でも再 push する。
        display_key = (text, yesno)
        if (getattr(w, "_palace_dialog_prev_key", None) == display_key
                and w._ui_router.is_owner(_OWNER)):
            return True
        w._palace_dialog_prev_key = display_key
        w._ui_router.update_translation(
            _OWNER, text, ja, speech_role="conversation")
        _log.info("panel_owner -> palace_dialog (off=0x%04X yesno=%s text=%r)",
                  off, yesno, text[:60])
        return True

    # 1) fg が本文帯内 = 現在画面に本文が出ている → そのまま表示 (Yes/No なし)。
    if in_band_fg:
        text = _read_full_text(w, fg)
        if text:
            result = _ndl.lookup(text)
            if result and result[0]:
                ja = _ndl.format_japanese(result[0], result[1])
                return _emit(fg, text, ja, yesno=False)

    # 2) fg が帯外 = Yes/No 選択オーバーレイ中のみ、直前本文を保持表示する。
    #    Yes/No ページの本文は必ず疑問文 (…?) で終わる。終端が疑問文でない
    #    (= 会話の最終文/通常文) ならフォールバックしない。これにより会話
    #    終了後 (= プレイヤーが本文を閉じて歩行に戻った) に前の会話文を
    #    再 push し続けてパネルが残る不具合を防ぐ。
    last_off = getattr(w, "_palace_dialog_last_off", None)
    if last_off is not None and last_off != fg:
        text = _read_full_text(w, last_off)
        if text and text.rstrip().endswith("?"):
            result = _ndl.lookup(text)
            if result and result[0]:
                ja = _ndl.format_japanese(result[0], result[1])
                return _emit(last_off, text, ja, yesno=True)

    # 3) 表示すべき会話本文なし (= 会話終了/歩行中) → owner を解放してパネルを
    #    クリアする (女王会話終了後にパネルが残らないようにする)。
    if w._ui_router.is_owner(_OWNER):
        w._ui_router.release_if_owner(_OWNER)
    w._palace_dialog_prev_key = None
    w._palace_dialog_last_off = None
    _log.debug("palace_dialog cleared (fg=0x%04X in_band=%s)", fg, in_band_fg)
    return False


__all__ = [
    "poll_palace_dialog",
    "is_palace_interior_mif",
    "assemble_dialog_text",
]
