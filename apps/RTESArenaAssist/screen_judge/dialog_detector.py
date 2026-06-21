"""
screen_judge/dialog_detector.py — NPC ダイアログ枠検出

Arena のダイアログ枠は画面中央付近に表示され、枠の縁が特徴的な色
（明るいシアン/水色系）をもつ。

検出戦略:
  Lv1 / Lv2（本モジュール）:
    - ObsRegistry に登録された観測点群をサンプリングする
    - 各観測点の実際のピクセル色を expected_rgb と比較し、
      tolerance 以内ならヒット判定
    - ヒット率が threshold 以上 → 枠表示中と判定

  detect_dialog() は観測点が 1 件もなければ UNKNOWN を返す。
  観測点をどの座標に置くかはユーザーが ScreenJudge タブで登録する。

コーナーロール（role フィールド）:
  "dialog_corner_tl" / "dialog_corner_tr" / "dialog_corner_bl" / "dialog_corner_br"
  これらがヒットした場合、外接矩形を arena_rect / client_rect として返す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image
    from screen_judge.registry import ObsRegistry
    from screen_judge.coord_mapper import ArenaCoordMapper


class DialogState(Enum):
    OPEN    = "open"     # ダイアログ枠が表示中
    CLOSED  = "closed"   # 表示されていない
    UNKNOWN = "unknown"  # 観測点未登録、またはキャプチャなし


@dataclass
class DetectionResult:
    state:        DialogState
    hit_count:    int    # マッチした観測点数
    total_count:  int    # 判定に使った観測点数
    hit_ratio:    float  # hit_count / total_count（0.0 なら判定不能）
    detail:       str    # デバッグ用の説明文
    # 検出した枠の Arena 矩形（None = コーナーヒット 2 件未満で範囲不明）
    arena_rect:   Optional[tuple[int, int, int, int]] = field(default=None)
    client_rect:  Optional[tuple[int, int, int, int]] = field(default=None)


def _color_match(actual: tuple[int, int, int],
                 expected: list[int],
                 tolerance: int) -> bool:
    """各チャンネルの差分が全て tolerance 以内なら True。"""
    r, g, b = actual
    er, eg, eb = expected
    return (
        abs(r - er) <= tolerance and
        abs(g - eg) <= tolerance and
        abs(b - eb) <= tolerance
    )


def detect_dialog(
    img: "Image.Image",
    mapper: "ArenaCoordMapper",
    registry: "ObsRegistry",
    purpose_filter: Optional[str] = None,
    threshold: float = 0.75,
) -> DetectionResult:
    """
    観測点群を使って NPC ダイアログ枠の表示状態を判定する。

    Args:
        img:            DOSBox クライアント領域の PIL Image
        mapper:         Arena ↔ クライアント座標変換器
        registry:       観測点レジストリ
        purpose_filter: 指定した場合、purpose が一致する観測点のみ使用
        threshold:      ヒット率の閾値（デフォルト 0.75 = 75%）

    Returns:
        DetectionResult（arena_rect / client_rect はコーナーヒット 2 件以上で設定）
    """
    points = registry.all()
    if purpose_filter:
        points = [p for p in points if p.get("purpose") == purpose_filter]

    if not points:
        return DetectionResult(
            state=DialogState.UNKNOWN,
            hit_count=0,
            total_count=0,
            hit_ratio=0.0,
            detail="no observation points registered",
        )

    img_w, img_h = img.size
    hit = 0
    checked = 0
    missed_detail: list[str] = []
    corner_hits: list[tuple[int, int]] = []  # ヒットしたコーナー観測点の Arena 座標

    for obs in points:
        ax, ay = obs["arena_xy"]
        cx, cy = mapper.arena_to_client(ax, ay)

        # 範囲外はスキップ（キャプチャサイズが想定外の場合）
        if cx < 0 or cy < 0 or cx >= img_w or cy >= img_h:
            continue

        actual = img.getpixel((cx, cy))[:3]
        tol = obs.get("tolerance", 20)
        matched = _color_match(actual, obs["expected_rgb"], tol)

        if matched:
            hit += 1
            if obs.get("role", "").startswith("dialog_corner_"):
                corner_hits.append((ax, ay))
        else:
            missed_detail.append(
                f"{obs['name']}@({ax},{ay}): "
                f"got {actual} exp {tuple(obs['expected_rgb'])} tol {tol}"
            )
        checked += 1

    if checked == 0:
        return DetectionResult(
            state=DialogState.UNKNOWN,
            hit_count=0,
            total_count=0,
            hit_ratio=0.0,
            detail="all observation points out of bounds",
        )

    ratio = hit / checked
    state = DialogState.OPEN if ratio >= threshold else DialogState.CLOSED
    detail = (
        f"hit {hit}/{checked} ({ratio:.0%})"
        + (f" | misses: {'; '.join(missed_detail)}" if missed_detail else "")
    )

    # コーナーヒット 2 件以上で外接矩形を計算
    arena_rect = None
    client_rect = None
    if len(corner_hits) >= 2:
        xs = [p[0] for p in corner_hits]
        ys = [p[1] for p in corner_hits]
        ax_min, ax_max = min(xs), max(xs)
        ay_min, ay_max = min(ys), max(ys)
        arena_rect = (ax_min, ay_min, ax_max - ax_min, ay_max - ay_min)
        cx0, cy0, cw, ch = mapper.arena_rect_to_client(*arena_rect)
        client_rect = (cx0, cy0, cw, ch)

    return DetectionResult(
        state=state,
        hit_count=hit,
        total_count=checked,
        hit_ratio=ratio,
        detail=detail,
        arena_rect=arena_rect,
        client_rect=client_rect,
    )
