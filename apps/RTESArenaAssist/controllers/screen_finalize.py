"""screen_finalize.py — キャラクター画面の確定処理 pure helper。

レベルアップ中のキャラクター画面 (= ボーナス割り振り画面 = bonus_screen) の
保持 (hold) 判定を、window / analyzer の時系列状態に触れない pure helper に
切り出す (char_screen_page / spell_view と同方針)。

ボーナス割り振り画面は通常のステータス画面と同じ img (CHARSTAT.IMG 等) を
使うため、レベルアップ進行中か (in_levelup) で区別する。画面を開いている間
(flag_status==1) は保持し、内部の img 循環で装備一覧・魔法一覧等へ一瞬倒れ
ないようにする。割り振り完了 (bonus_pts==0) しても画面を閉じるまで保持する。

副作用 (ログ出力 / 魔法詳細 marker クリア / window state への代入) は持たず、
何をすべきかをフラグで返す。呼出側がそのフラグに従って副作用を適用する。
"""
from __future__ import annotations

from dataclasses import dataclass

# 保持中にボーナス画面で上書きするキャラクター画面ページ。
_HOLD_OVERRIDE_PAGES = ("equipment", "spellbook", "spell_detail", "status_page")


@dataclass
class BonusScreenResolve:
    """resolve_bonus_screen の結果。

    screen_id_stable:    補正後の画面 id。
    hold_active:         新しいボーナス画面 hold 状態 (_bonus_screen_hold)。
    log_start:           hold 開始ログを出すべきか。
    log_end:             hold 終了ログを出すべきか。
    log_override:        hold 上書きログ (debug) を出すべきか。
    clear_spell_markers: 魔法詳細 marker をクリアすべきか。
    """
    screen_id_stable: str
    hold_active: bool
    log_start: bool
    log_end: bool
    log_override: bool
    clear_spell_markers: bool


def resolve_bonus_screen(screen_id_stable: str, in_levelup: bool,
                         flag_status: int,
                         hold_active: bool) -> BonusScreenResolve:
    """ボーナス画面 hold の遷移と画面 id 上書きを判定する pure helper。

    現行 poll_controller のインライン判定 (突入 / 保持 / 離脱 / 上書き) を
    挙動同一で関数化したもの。判定順序は現行と同一:

      1. 突入: in_levelup かつ flag_status==1 → hold 開始 (page を問わず保持)。
         初回のみ開始ログ。保持中は毎回 marker クリアを要求する。
      2. レベルアップ外で screen が bonus_screen → status_page へ落とす。
      3. 離脱: hold 中に flag_status==0 または レベルアップ完了 → hold 解除。
      4. 上書き: hold 中はキャラシート系ページを bonus_screen に上書きする。

    Args:
      screen_id_stable: 確定途中の画面 id。
      in_levelup:       レベルアップ進行中か (_level_up_active)。
      flag_status:      キャラポップアップ active フラグ (+0x12BA, 1=開いている)。
      hold_active:      現在の bonus_screen hold 状態 (_bonus_screen_hold)。

    Returns:
      BonusScreenResolve。
    """
    log_start = False
    log_end = False
    log_override = False
    clear_spell_markers = False

    if in_levelup and flag_status == 1:
        # レベルアップ中のキャラクター画面 = ボーナス画面。CHARSTAT 検出を
        # 待たず flag_status==1 の間 page を問わず保持する。
        if not hold_active:
            log_start = True
        hold_active = True
        clear_spell_markers = True
    elif screen_id_stable == "bonus_screen" and not in_levelup:
        # レベルアップ外の CHARSTAT = 通常ステータス画面。
        screen_id_stable = "status_page"

    # 離脱条件: 画面を閉じた (flag_status==0) / レベルアップ完了。
    # bonus_pts==0 では離脱しない (= 割り振り完了後も画面が開いている間は保持)。
    if hold_active and (flag_status == 0 or not in_levelup):
        log_end = True
        hold_active = False

    # hold 中はキャラシート系の他判定を bonus_screen に上書き。
    if hold_active and screen_id_stable in _HOLD_OVERRIDE_PAGES:
        log_override = True
        screen_id_stable = "bonus_screen"

    return BonusScreenResolve(
        screen_id_stable=screen_id_stable,
        hold_active=hold_active,
        log_start=log_start,
        log_end=log_end,
        log_override=log_override,
        clear_spell_markers=clear_spell_markers,
    )


__all__ = [
    "resolve_bonus_screen",
    "BonusScreenResolve",
    "_HOLD_OVERRIDE_PAGES",
]
