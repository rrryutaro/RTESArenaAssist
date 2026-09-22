from __future__ import annotations
from typing import Any, NamedTuple, Optional, Tuple
Coord = Tuple[Optional[int], Optional[int]]

class TransitionGateResult(NamedTuple):
    in_transition: bool
    pre_coord: Optional[Coord]
    shown: bool
    pre_loc: Any = None
    load_pending: bool = False
_RELEASED = TransitionGateResult(in_transition=False, pre_coord=None, shown=True)

def resolve_coord_transition(*, loc, prev_loc, in_transition: bool, pre_coord: Optional[Coord], coord: Coord, prev_coord: Optional[Coord]=None, is_loading: bool=False, arrival_coord: Optional[Coord]=None, pre_loc: Any=None, load_pending: bool=False, load_started: bool=False) -> TransitionGateResult:
    coord_valid = None not in coord
    arrival_match = arrival_coord is not None and coord_valid and (coord == arrival_coord)
    if load_started and arrival_coord is not None:
        same_place = not in_transition and prev_loc is not None and (loc == prev_loc)
        if arrival_match and (not is_loading or same_place):
            return _RELEASED
        return TransitionGateResult(in_transition=True, pre_coord=coord, shown=False, pre_loc=prev_loc, load_pending=True)
    if in_transition:
        if load_pending:
            background_current = not is_loading or loc == pre_loc
            moved_after_load = not is_loading and coord_valid and (pre_coord is not None) and (coord != pre_coord)
            if arrival_match and background_current or moved_after_load:
                return _RELEASED
            return TransitionGateResult(in_transition=True, pre_coord=pre_coord, shown=False, pre_loc=pre_loc, load_pending=True)
        arrival_confirmed = arrival_match and (not is_loading)
        if pre_coord is None or coord != pre_coord or arrival_confirmed:
            return _RELEASED
        if pre_loc is not None and loc == pre_loc:
            return _RELEASED
        return TransitionGateResult(in_transition=True, pre_coord=pre_coord, shown=False, pre_loc=pre_loc)
    if prev_loc is not None and loc != prev_loc:
        if arrival_match and (not is_loading):
            return _RELEASED
        if not is_loading and prev_coord is not None and (None not in prev_coord) and coord_valid and (coord != prev_coord):
            return _RELEASED
        return TransitionGateResult(in_transition=True, pre_coord=coord, shown=False, pre_loc=prev_loc)
    return _RELEASED

def arrival_consumption_due(*, arrival_supplied: bool, is_loading: bool, gate_in_transition: bool, gate_was_in_transition: bool, loc, prev_loc) -> bool:
    if not arrival_supplied or is_loading or gate_in_transition:
        return False
    return gate_was_in_transition or (prev_loc is not None and loc != prev_loc)
