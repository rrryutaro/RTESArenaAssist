"""normal-play 状態の session dispatch。

normal-play 状態の session_manager 呼び出しを L1 境界に閉じる。描画候補の
最終反映は UiRouter の DisplayIntent 1 軸が担当し、本モジュールは
親状態としての C 通常ゲーム中だけを扱う。

1. session_manager.poll(ctx) — 全 session の latch + poll() 実行
2. shop_state 検出 (= shop_popup_detector)
3. shop_buy / shop_rooms / shop_menu / shop_rumor_type 描画
4. normal_play/active_template_module.poll_active_template() 呼出
5. normal_play/building_entry_module.poll_building_entry() 呼出
6. normal_play/npc_dialog_module.poll_npc_dialog() 呼出
7. normal_play/trigger_module の trigger / red_text / gold_drop / a845 close
8. normal_play/journal_module.poll_journal() 呼出
9. normal_play/level_up_module.poll_level_up() 呼出
10. normal_play/item_pickup_module.poll_item_pickup() 呼出

各 module は window 参照経由で UiRouter / analyzer / state vars にアクセス
する。session_manager が複数 session の active 状態を相互排他し、
panel_owner 競合は UiRouter の所有権モデルで管理される。
"""
from __future__ import annotations

from session.session_base import SessionContext
from top_level.top_level_dispatcher import build_session_context


def poll_sessions(w, ctx: SessionContext) -> None:
    """normal-play session 群を L1 normal-play 境界内で poll する。

    active session がある場合だけ、L1 離脱直後の終了時整理のために
    1 回以上 poll を通す。active が無い非 normal-play では開始判定自体を
    呼ばない。
    """
    if ctx.top_level_state != "normal-play":
        try:
            if not w._session_manager.is_any_active():
                return None
        except AttributeError:
            return None
    w._session_manager.poll(ctx)
    return None


def poll(w, ctx: SessionContext | None = None) -> None:
    """normal-play 状態の session dispatch を実行する。"""
    if ctx is None:
        ctx = build_session_context(w)
    poll_sessions(w, ctx)


__all__ = ["poll", "poll_sessions"]
