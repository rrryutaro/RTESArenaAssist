from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
DEFAULT_WINDOW_START = 0
DEFAULT_WINDOW_SIZE = 49152
REPORT_DETAIL_MAX = 24

class ViewSignalHunter:

    def __init__(self, *, window_start: int=DEFAULT_WINDOW_START, window_size: int=DEFAULT_WINDOW_SIZE, name: str='view') -> None:
        self._start = window_start
        self._size = window_size
        self._name = name
        self._prev: bytes | None = None
        self._prev_view: str | None = None
        self._candidates: dict[int, dict[str, int]] | None = None
        self._edges = 0
        self._reported: int | None = None

    @property
    def edges(self) -> int:
        return self._edges

    def candidates(self) -> dict[int, dict[str, int]]:
        return dict(self._candidates or {})

    def observe(self, analyzer, anchor: int, view: str) -> None:
        try:
            cur = analyzer.read_bytes(anchor + self._start, self._size)
        except (OSError, AttributeError):
            return
        if len(cur) < self._size:
            return
        prev, prev_view = (self._prev, self._prev_view)
        self._prev, self._prev_view = (cur, view)
        if prev is None or prev_view is None or prev_view == view:
            return
        self._edges += 1
        changed = {i for i in range(self._size) if prev[i] != cur[i]}
        if self._candidates is None:
            self._candidates = {i: {prev_view: prev[i], view: cur[i]} for i in changed}
        else:
            kept: dict[int, dict[str, int]] = {}
            for i, seen in self._candidates.items():
                if i not in changed:
                    continue
                if seen.get(prev_view, prev[i]) != prev[i]:
                    continue
                if seen.get(view, cur[i]) != cur[i]:
                    continue
                seen[prev_view] = prev[i]
                seen[view] = cur[i]
                kept[i] = seen
            self._candidates = kept
        self._report()

    def _report(self) -> None:
        count = len(self._candidates or {})
        if count == self._reported:
            return
        self._reported = count
        if count and count <= REPORT_DETAIL_MAX:
            detail = ' '.join((f"+0x{i:04X}{''.join((f'[{k}={v:02X}]' for k, v in sorted(s.items())))}" for i, s in sorted((self._candidates or {}).items())))
            _log.warning('signal hunt[%s]: 切替 %d 回 / 候補 %d 件  %s', self._name, self._edges, count, detail)
        else:
            _log.warning('signal hunt[%s]: 切替 %d 回 / 候補 %d 件', self._name, self._edges, count)
        if not count and self._edges >= 2:
            _log.warning('signal hunt[%s]: この範囲のメモリに判別できる値は無い（切替 %d 回で候補が尽きた）', self._name, self._edges)
__all__ = ['ViewSignalHunter', 'DEFAULT_WINDOW_START', 'DEFAULT_WINDOW_SIZE']
