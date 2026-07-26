from __future__ import annotations
from typing import NamedTuple, Optional, Tuple
Coord = Tuple[Optional[int], Optional[int]]

class TransitionGateResult(NamedTuple):
    in_transition: bool
    pre_coord: Optional[Coord]
    shown: bool

def resolve_coord_transition(*, loc, prev_loc, in_transition: bool, pre_coord: Optional[Coord], coord: Coord, prev_coord: Optional[Coord]=None, is_loading: bool=False, arrival_coord: Optional[Coord]=None) -> TransitionGateResult:
    arrival_confirmed = not is_loading and arrival_coord is not None and (None not in coord) and (coord == arrival_coord)
    if in_transition:
        if pre_coord is None or coord != pre_coord or arrival_confirmed:
            return TransitionGateResult(in_transition=False, pre_coord=None, shown=True)
        return TransitionGateResult(in_transition=True, pre_coord=pre_coord, shown=False)
    if prev_loc is not None and loc != prev_loc:
        if arrival_confirmed:
            return TransitionGateResult(in_transition=False, pre_coord=None, shown=True)
        if not is_loading and prev_coord is not None and (None not in prev_coord) and (None not in coord) and (coord != prev_coord):
            return TransitionGateResult(in_transition=False, pre_coord=None, shown=True)
        return TransitionGateResult(in_transition=True, pre_coord=coord, shown=False)
    return TransitionGateResult(in_transition=False, pre_coord=None, shown=True)
