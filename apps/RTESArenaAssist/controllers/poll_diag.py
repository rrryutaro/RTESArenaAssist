from __future__ import annotations
import time

def _phase_start() -> float:
    return time.perf_counter()

def _phase_record(w, name: str, t0: float) -> None:
    try:
        w._poll_phase_times[name] = (time.perf_counter() - t0) * 1000.0
    except (AttributeError, TypeError):
        pass

def _checkpoint(w, name: str) -> None:
    try:
        w._poll_checkpoints.append((name, (time.perf_counter() - w._poll_t0) * 1000.0))
    except (AttributeError, TypeError):
        pass
__all__ = ['_phase_start', '_phase_record', '_checkpoint']
