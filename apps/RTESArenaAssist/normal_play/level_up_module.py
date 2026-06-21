"""レベルアップ全工程の検出と翻訳表示。

確定オフセット:
  +0x1AA  (u8)     Level - 1 (実 Level = 値 + 1)
  +0x129C (u8)     BONUS PTS (ステータス画面表示中のみ有意)
  +0x5AD  (u32 LE) Experience

フロー:
  1. Level が N → N+1 に変化 → _level_up_active = True
  2. ダイアログ表示中 → "レベルアップ" メッセージ
  3. ダイアログを閉じた後、ボーナス割り振り画面を待つ
  4. ボーナス割り振り画面 (= 別分離) 中 → _level_up_saw_bonus = True
  5. ボーナス画面を閉じた (= 別分離から離脱) → 完了 → _level_up_active = False

ボーナス割り振り画面はアイテム一覧 / 魔法一覧への遷移を持たない別分離であり、
bonus_pts が 0 になっても画面を閉じるまでは完了とせず、その間に他画面 (魔法一覧
等) の表示へ倒れないようにする。

window 側状態: _player_level_prev / _level_up_active / _level_up_from /
_level_up_to / _player_bonus_prev / _level_up_saw_bonus /
_level_up_waiting_for_bonus / _panel_owner

P2-1b (画面確定処理の段階分割):
  レベルアップ処理を 2 段に分ける。
    - produce_level_up_state(): 画面確定 (screen finalizer) が必要とする
      レベル変化検出と _level_up_active 更新だけを行う state producer。
      翻訳描画・owner claim・表示 cleanup は行わない。ロード境界の state
      seed / 破棄もここで扱う。
    - consume_level_up_display(): 画面確定済みの画面 id を受け取り、翻訳
      表示・owner claim・完了/cleanup を行う leaf consumer。
  poll_level_up() は両者を順に呼ぶ後方互換ラッパー (= 現行呼出位置・挙動を
  そのまま維持)。consumer を画面確定の後段へ移し current stable を引数で渡す
  移管は P2-2 で行う (= 本段階では画面 id 引数に従来と同じ _screen_id_prev を
  渡し挙動同一を保つ)。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")


def produce_level_up_state(w, *, loading_active: bool = False,
                           load_edge_start: bool = False,
                           loading_post_settle: bool = False) -> bool:
    """レベル変化検出と _level_up_active 更新を行う state producer。

    画面確定 (screen finalizer) が _level_up_active を bonus_screen hold の
    入力に使うため、確定より前に呼ぶ。翻訳描画・owner claim はしない。

    課題2:
      - load_edge_start: ロード開始エッジ。level_up state を破棄 + UI 所有解除
      - loading_active or loading_post_settle: prev_level を current で seed
        するだけで比較しない (= ロード前後の値で false level-up 発火を防ぐ)

    Returns:
      consumer (表示処理) を続行すべきなら True、ロード境界等で打ち切るべきなら
      False。例外時も False (= 現行の try/except 打ち切りと同義)。
    """
    try:
        import player_reader as _pr
        _player = _pr.read_all(w._analyzer, w._anchor)
        _cur_level = _player["level"]
        _cur_exp   = _player["experience"]

        # ロード開始エッジで level_up state を完全破棄
        if load_edge_start:
            if w._level_up_active or getattr(w, "_panel_owner", "") == "level_up":
                _log.info(
                    "LEVEL UP: load edge detected → state cleared "
                    "(prev_level=%s, cur_level=%s)",
                    w._player_level_prev, _cur_level)
            w._level_up_active = False
            w._level_up_from = None
            w._level_up_to = None
            w._player_bonus_prev = None
            w._level_up_saw_bonus = False
            w._level_up_waiting_for_bonus = False
            # panel_owner が level_up の場合のみ解除 (= ロード境界の state 破棄に
            # 伴う既存 cleanup。意味を変えずここで保持する)
            try:
                if (getattr(w, "_ui_router", None) is not None
                        and w._ui_router.is_owner("level_up")):
                    w._ui_router.clear_if_owner("level_up")
            except (AttributeError, RuntimeError):
                pass
            # current level を seed して比較を抑止
            w._player_level_prev = _cur_level
            return False

        # ロード中 / post-load settle 中は seed のみ (= 比較しない)
        if loading_active or loading_post_settle:
            if _cur_level is not None:
                w._player_level_prev = _cur_level
            return False

        if w._player_level_prev is None and _cur_level is not None:
            w._player_level_prev = _cur_level

        if (_cur_level is not None
                and w._player_level_prev is not None
                and _cur_level > w._player_level_prev):
            _log.info("LEVEL UP detected: %d → %d (Exp=%s)",
                      w._player_level_prev, _cur_level, _cur_exp)
            w._level_up_from   = w._player_level_prev
            w._level_up_to     = _cur_level
            w._level_up_active = True
            w._level_up_waiting_for_bonus = True
        w._player_level_prev = _cur_level
        return True
    except (ImportError, AttributeError, OSError):
        return False


def consume_level_up_display(w, *, screen_id_stable: str | None,
                             b30_dialog_active: bool,
                             b30_dialog_active_prev: bool,
                             b30_red_changed: bool,
                             npc_dialog_changed: bool) -> None:
    """確定済み画面 id を入力に、翻訳表示・owner claim・完了/cleanup を行う。

    Args:
      screen_id_stable: 画面確定後の画面 id (= ボーナス画面か否かの判定に使う)。
        P2-1b では呼出側が従来と同じ前回値を渡し挙動同一を保つ。P2-2 で current
        stable へ移管する。
    """
    try:
        # 翻訳パネル/タブの表示分離ルール:
        #   - 翻訳パネル JA: 原文翻訳のみ (補足情報禁止)
        #   - 翻訳タブ JA: 補足情報・バイリンガル表記許容
        _is_bonus_screen = (screen_id_stable == "bonus_screen")
        _is_dialog_only  = b30_dialog_active and not _is_bonus_screen

        if w._level_up_active:
            # ダイアログ表示 (= ボーナス画面より前) のみ「経験値が上がった」を出す。
            # ボーナス画面 (= 別分離) に入ったら、その分離が表示を所有するため
            # level_up 側からは push しない (= 単一所有)。
            if _is_dialog_only:
                _en_panel = "You have gained a level of experience!"
                _ja_panel = "経験値レベルが上がった！"
                _en_tab = "You have gained a level of experience!"
                _ja_tab = (f"レベルアップ! Level {w._level_up_from} → "
                           f"{w._level_up_to} に上がった。")
                w._ui_router.update_translation(
                    "level_up", _en_tab, _ja_tab,
                    panel_en=_en_panel, panel_ja=_ja_panel,
                    speech_role="situation")

            if _is_bonus_screen:
                # BONUS PTS は表示中のみ有意。bonus 画面の間だけ読む。
                import player_reader as _pr
                _cur_bonus = _pr.read_all(w._analyzer, w._anchor)["bonus_pts"]
                if _cur_bonus is not None and 0 <= _cur_bonus <= 30:
                    w._player_bonus_prev = _cur_bonus
                    w._level_up_saw_bonus = True
                    w._level_up_waiting_for_bonus = False

            # 完了判定: ボーナス画面 (= 別分離) を実際に閉じた時点で完了する。
            # ボーナス画面に入っていた場合はその離脱 (= _is_bonus_screen が False へ
            # 戻る) を完了条件とし、画面が開いている間は bonus_pts が 0 でも完了させ
            # ない。Level up 通知ダイアログが閉じても、Arena はその後に
            # ボーナス割り振り画面を開くため、_level_up_waiting_for_bonus 中は
            # 完了させない。
            _saw_bonus     = getattr(w, "_level_up_saw_bonus", False)
            _waiting_bonus = getattr(w, "_level_up_waiting_for_bonus", False)
            _bonus_closed  = _saw_bonus and not _is_bonus_screen
            _dialog_closed = (b30_dialog_active_prev and not b30_dialog_active)
            if _bonus_closed or (
                    not _saw_bonus and not _waiting_bonus and _dialog_closed):
                _log.info("LEVEL UP: complete (saw_bonus=%s)", _saw_bonus)
                w._level_up_active   = False
                w._player_bonus_prev = None
                w._level_up_saw_bonus = False
                w._level_up_waiting_for_bonus = False
                # 真1軸化: 完了時の clear は単一前景 (c1_dialog_foreground) のみで
                # 判定する。C1 ダイアログ面 (red_text/gold_drop/c1_runtime_dialog)
                # が前景の poll はその面が表示を所有するため clear しない。旧
                # 防御ガード `not (red_changed or npc_dialog_changed)` の生イベント
                # フラグ再導出 (1軸化未達シグナル) を撤去 (npc_dialog_changed は
                # classify が c1_runtime_dialog 前景へ吸収済=同義・走る主体の再配置)。
                _c1_fg = getattr(w, "_c1_dialog_foreground", "")
                if _c1_fg == "" and w._ui_router.is_owner("level_up"):
                    w._ui_router.clear_if_owner("level_up")
    except (ImportError, AttributeError, OSError):
        pass


def poll_level_up(w, *, b30_dialog_active: bool,
                  b30_dialog_active_prev: bool,
                  b30_red_changed: bool,
                  npc_dialog_changed: bool,
                  loading_active: bool = False,
                  load_edge_start: bool = False,
                  loading_post_settle: bool = False) -> None:
    """レベルアップ検出 + 翻訳表示 (producer → consumer の後方互換ラッパー)。

    現行呼出位置 (画面確定より前) でそのまま呼ぶことを想定し、consumer には
    従来と同じ前回画面 id (_screen_id_prev) を渡して挙動同一を保つ。
    """
    _continue = produce_level_up_state(
        w,
        loading_active=loading_active,
        load_edge_start=load_edge_start,
        loading_post_settle=loading_post_settle,
    )
    if not _continue:
        return
    consume_level_up_display(
        w,
        screen_id_stable=getattr(w, "_screen_id_prev", None),
        b30_dialog_active=b30_dialog_active,
        b30_dialog_active_prev=b30_dialog_active_prev,
        b30_red_changed=b30_red_changed,
        npc_dialog_changed=npc_dialog_changed,
    )


__all__ = [
    "poll_level_up",
    "produce_level_up_state",
    "consume_level_up_display",
]
