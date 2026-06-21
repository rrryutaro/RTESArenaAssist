
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image
    from screen_judge.registry import ObsRegistry
    from screen_judge.coord_mapper import ArenaCoordMapper


class DialogState(Enum):
    OPEN    = "open"
    CLOSED  = "closed"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    state:        DialogState
    hit_count:    int
    total_count:  int
    hit_ratio:    float
    detail:       str
    arena_rect:   Optional[tuple[int, int, int, int]] = field(default=None)
    client_rect:  Optional[tuple[int, int, int, int]] = field(default=None)


def _color_match(actual: tuple[int, int, int],
                 expected: list[int],
                 tolerance: int) -> bool:
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
    corner_hits: list[tuple[int, int]] = []

    for obs in points:
        ax, ay = obs["arena_xy"]
        cx, cy = mapper.arena_to_client(ax, ay)

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
