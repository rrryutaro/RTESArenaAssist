"""交渉ダイアログ描画モジュール (L4 module)。

NEGOTIATION_PROFILES に登録された IMG (NEGOTBUT.IMG / YESNO.IMG) が
表示中の間、本モジュールが交渉本文 (+0x929E 主信号 + +0x987A 従信号 の
テンプレ拘束 prefix match) + ボタン (NEGOTIATION_PROFILES の固定ラベル) +
active prompts を翻訳パネルに描画する。

設計: 交渉描画は session ではなく module として持つ。
理由:
- session_manager は単一 active 設計 (相互排他)。
- tavern_session が NEGOTBUT.IMG / YESNO.IMG 中も継続するため、session 方式
  では try_start が呼ばれず描画不能になる。
- L3 親状態 (tavern_session 等) と L4 子描画 (本モジュール) は
  並列で動作するのが正しい。

state は window インスタンス上に保持 (= window scope):
- w._negot_key_prev: 直近描画の key (重複描画抑止)
- w._negot_diag_key_prev: 診断ログ重複抑止
- w._negot_prompts_ctx_prev: prompts ctx 同一時の active_slot 抑止
- w._negot_empty_polls: 本文/プロンプト空 poll 連続カウンタ

呼び出し側は `poll_negotiation(w)` を呼び、戻り値が True なら本モジュールが
panel_owner='negotiation' を所有している。False の場合は `cleanup_if_owner(w)`
で所有権を解除する。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

# 本文/プロンプト両方が空の poll が連続したら交渉表示を解放する閾値。
_EMPTY_POLLS_THRESHOLD = 2


def compute_speech_diff(body_lines: list[str], prev_lines, *,
                        owner_taken: bool) -> list[str]:
    """読み上げ本文の差分を返す純関数（価格交渉の差分追跡）。

    body_lines はボタン行を除いた本文行（店主応答 + プロンプト）。前回表示
    (prev_lines) の続きとして body_lines が伸びていれば追加分だけを、そうで
    なければ全体を返す。owner を奪われた直後 (owner_taken) は全体を読む。
    受け手ではなく価格交渉の表示を組む本人が差分を算出するための核。
    """
    prev = [] if owner_taken else (prev_lines or [])
    if prev and body_lines[:len(prev)] == prev:
        return body_lines[len(prev):]
    return body_lines


def _get_profile(img_name: str):
    """IMG 名から negotiation profile (buttons_en/ja) を取得。"""
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return None
    return get_negotiation_profile((img_name or "").upper())


def _ensure_state(w) -> None:
    """w 上の交渉モジュール state を初期化 (= 不存在なら None で確保)。"""
    if not hasattr(w, "_negot_key_prev"):
        w._negot_key_prev = None
    if not hasattr(w, "_negot_diag_key_prev"):
        w._negot_diag_key_prev = None
    if not hasattr(w, "_negot_prompts_ctx_prev"):
        w._negot_prompts_ctx_prev = None
    if not hasattr(w, "_negot_empty_polls"):
        w._negot_empty_polls = 0
    if not hasattr(w, "_negot_counter_active"):
        w._negot_counter_active = False
    # 読み上げ済み本文行(ボタン行を除く)。追加分だけ読むための差分追跡。
    if not hasattr(w, "_negot_speech_prev"):
        w._negot_speech_prev = []


def _reset_state(w) -> None:
    """w 上の交渉モジュール state を初期値に戻す (= 退場時)。"""
    w._negot_key_prev = None
    w._negot_diag_key_prev = None
    w._negot_prompts_ctx_prev = None
    w._negot_empty_polls = 0
    w._negot_counter_active = False
    w._negot_speech_prev = []


def poll_negotiation(w, *, img_name: str, top_level_state: str,
                     owner: str = "negotiation") -> bool:
    """交渉ダイアログ描画 poll。

    戻り値: 本モジュールが panel_owner='negotiation' を所有して描画した場合 True、
    描画対象外 (= IMG が NEGOTIATION_PROFILES に無い / 本文・プロンプト空が
    連続 / top_level_state 不一致) で false の場合は False。

    呼び出し側で False のときは `cleanup_if_owner(w)` を呼んで所有権を解除する。
    """
    _ensure_state(w)
    # 既定は対案非表示。この poll で対案プロンプトを描画した時のみ True にする。
    w._negot_counter_active = False

    if top_level_state != "normal-play":
        return False

    profile = _get_profile(img_name)
    if profile is None:
        # NEGOTIATION_PROFILES 外の IMG → 交渉描画対象外
        return False

    # 宿屋 Rumors flow 中は negotiation_module を完全停止する。
    # NEGOTBUT.IMG は negotiation 完了後も残置されることがあり、噂応答 (= 同じ
    # 物理 buffer +0x929E に load される) を negotiation_reader が誤って
    # 「負債テンプレ」として match してしまう問題を防ぐ。
    # フラグは tavern_session.poll が Rumor Type サブメニュー検出時に True
    # にセットし、tavern_session.try_stop が shop_menu 主メニュー復帰検出時
    # に False に戻す。
    if getattr(w, "_tavern_rumor_flow_active", False):
        return False

    # active_template が tavern_* surface 候補を持っている場合は
    # 当該描画を譲る (= sneak YES/NO / sneak result / room contract /
    # cost show / cost confirm 等)。
    # YESNO.IMG は NEGOTIATION_PROFILES 登録 IMG だが、宿屋忍び込み確認や
    # 価格承諾 YES/NO にも使われる。これらの surface 中は negotiation_reader
    # が buffer +0x929E の sneak/cost text を trivial に prefix match して
    # しまい、'ACCEPT COUNTER REJECT\\n<sneak text>' と active_template の
    # 正しい描画とが交互上書きされチラ付くため。
    # negotiation_counter (= 'negotiation_*' prefix) は本モジュール側で
    # 統合描画する設計のためここでは defer しない。
    try:
        from active_template_reader import (
            read_active_template_candidates,
            template_surface_kind,
        )
        for _c in read_active_template_candidates(w._analyzer, w._anchor):
            _k = template_surface_kind(_c)
            if _k and _k.startswith("tavern_"):
                return False
    except Exception:  # noqa: BLE001
        pass

    # 本文取得
    try:
        from negotiation_reader import read_negotiation_diagnostic
        _raw, _canon, _rendered, _text = read_negotiation_diagnostic(
            w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("negotiation_reader failed")
        _raw = _canon = _rendered = _text = None

    # 診断ログ (template / rendered / matched が変化した時のみ)
    _diag_key = (_raw, _rendered, _text)
    if w._negot_diag_key_prev != _diag_key:
        w._negot_diag_key_prev = _diag_key
        _suffix = ""
        if _text and _rendered:
            _suffix = _rendered[len(_text):][:32]
        elif _rendered:
            _suffix = _rendered[:32]
        _log.info(
            "negotiation template raw=%r canonical=%r "
            "rendered=%r matched=%r suffix=%r",
            (_raw or "")[:80], (_canon or "")[:80],
            (_rendered or "")[:80], (_text or "")[:80], _suffix)

    # 本文の辞書 lookup
    try:
        import npc_dialog_lookup as _ndl
    except ImportError:
        _ndl = None
    _r = None
    if _text and _ndl is not None:
        try:
            _r = _ndl.lookup(_text)
        except Exception:  # noqa: BLE001
            _log.exception("negotiation lookup failed")
            _r = None
    _fallback_body = ""
    if _text and _r is None and owner == "equipment_negotiation":
        # 武具店 Buy 交渉は EQUIP.DAT の 75 文からランダムに出る。
        # 未登録テンプレートでも前景本文なら旧翻訳を保持せず、未登録表示へ
        # 更新して誤表示を避ける。
        _fallback_body = " ".join(_text.split())

    # active prompts 取得 (= 「Enter counter offer :」等の入力プロンプト)
    _active_prompts_pairs: list[tuple[str, str]] = []
    _counter_rendered = False
    if _ndl is not None:
        try:
            from active_template_reader import (
                read_active_template_candidates,
                template_surface_kind,
            )
            _ap_ctx_key = (img_name, top_level_state, "negot")
            _allow_slot = (_ap_ctx_key != w._negot_prompts_ctx_prev)
            w._negot_prompts_ctx_prev = _ap_ctx_key
            for c in read_active_template_candidates(
                    w._analyzer, w._anchor):
                # 対案入力 (negotiation_counter) は金額提示と同じ NEGOTBUT.IMG
                # を共有するため、img ベースの ctx 抑止では落ちてしまう。
                # 交渉自身の入力プロンプトなので stale 扱いせず常に採用する。
                try:
                    _is_counter = (
                        template_surface_kind(c) == "negotiation_counter")
                except Exception:  # noqa: BLE001
                    _is_counter = False
                if (c.source == "active_slot" and not _allow_slot
                        and not _is_counter):
                    continue
                _ap_clean = c.text.rstrip()
                if not _ap_clean:
                    continue
                _apr = _ndl.lookup(_ap_clean)
                if _apr is None:
                    continue
                _apja_tmpl, _apph = _apr
                _apja = _ndl.format_japanese(_apja_tmpl, _apph)
                _active_prompts_pairs.append((_ap_clean, _apja))
                if _is_counter:
                    _counter_rendered = True
        except Exception:  # noqa: BLE001
            _log.exception("negotiation prompts read failed")
    # 対案入力中フラグ (= 接続バーの [宿泊金額対案] 表示に使う)。
    w._negot_counter_active = _counter_rendered

    _has_body = _r is not None or bool(_fallback_body)
    _has_prompts = bool(_active_prompts_pairs)

    # 本文/プロンプト両方が空の poll を計上。閾値以上で離脱する。
    if _has_body or _has_prompts:
        w._negot_empty_polls = 0
    else:
        w._negot_empty_polls += 1

    if w._negot_empty_polls >= _EMPTY_POLLS_THRESHOLD:
        _log.info(
            "negotiation exit: empty body+prompts for %d polls (img=%r)",
            w._negot_empty_polls, img_name)
        return False

    if not (_has_body or _has_prompts):
        # まだ閾値に達していないが今 poll は本文も prompt もない。
        # 現在所有しているなら継続所有 (= 直近の表示を維持)。
        return w._ui_router.current_owner() == owner

    # 描画: ボタンラベル + 本文 + プロンプト
    _btn_en = "  ".join(profile["buttons_en"])
    _btn_ja = "  ".join(profile["buttons_ja"])
    _en_lines = [_btn_en]
    _ja_lines = [_btn_ja]
    if _r is not None:
        _ja_tmpl, _ph = _r
        _ja_body = _ndl.format_japanese(_ja_tmpl, _ph)
        _en_lines.append(_text or "")
        _ja_lines.append(_ja_body)
    elif _fallback_body:
        _ja_body = "（未登録テンプレート）"
        _en_lines.append(_fallback_body)
        _ja_lines.append(_ja_body)
    else:
        _ja_body = ""
    for _ap_en, _ap_ja in _active_prompts_pairs:
        _en_lines.append(_ap_en)
        _ja_lines.append(_ap_ja)
    _en_text = "\n".join(_en_lines)
    _ja_text = "\n".join(_ja_lines)
    _key = (_text or "", _ja_body, tuple(_active_prompts_pairs))
    _owner_taken = (w._ui_router.current_owner() != owner)
    if _key != w._negot_key_prev or _owner_taken:
        w._negot_key_prev = _key
        # 読み上げ本文 = ボタン行(先頭)を除いた本文(店主応答+プロンプト)
        # のうち、前回表示から追加された差分だけ。差分追跡は表示を組む本モジュール
        # が保持する(受け手は内部構造に依存しない)。owner を奪われた直後は全体を読む。
        _body_lines = [ln.strip() for ln in _ja_lines[1:] if ln.strip()]
        _new_lines = compute_speech_diff(
            _body_lines, w._negot_speech_prev, owner_taken=_owner_taken)
        w._negot_speech_prev = _body_lines
        _speech_text = "\n".join(_new_lines).strip()
        w._ui_router.update_translation(
            owner, _en_text, _ja_text,
            speech_role="conversation", speech_text=_speech_text)
        _log.info(
            "negotiation translated: owner=%s body=%r prompts=%d",
            owner, (_text or "")[:80], len(_active_prompts_pairs))
    return True


def cleanup_if_owner(w, *, owner: str = "negotiation") -> None:
    """negotiation 所有時に panel をクリアし state を reset する。"""
    _ensure_state(w)
    try:
        if w._ui_router.is_owner(owner):
            w._ui_router.clear_if_owner(owner)
            _log.info("negotiation exit (cleanup owner=%s)", owner)
    except AttributeError:
        pass
    _reset_state(w)


__all__ = ["poll_negotiation", "cleanup_if_owner", "compute_speech_diff"]
