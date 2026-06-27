class ArenaCoordMapper:
    ARENA_W = 320
    ARENA_H = 200

    def __init__(self, client_w: int, client_h: int):
        self._client_w = client_w
        self._client_h = client_h
        self._sx = client_w / self.ARENA_W
        self._sy = client_h / self.ARENA_H

    @property
    def scale_x(self) -> float:
        return self._sx

    @property
    def scale_y(self) -> float:
        return self._sy

    def arena_to_client(self, ax: int, ay: int) -> tuple[int, int]:
        return (round(ax * self._sx), round(ay * self._sy))

    def arena_rect_to_client(self, ax: int, ay: int, aw: int, ah: int) -> tuple[int, int, int, int]:
        cx, cy = self.arena_to_client(ax, ay)
        cw = round(aw * self._sx)
        ch = round(ah * self._sy)
        return (cx, cy, cw, ch)

    def client_to_arena(self, cx: int, cy: int) -> tuple[int, int]:
        return (round(cx / self._sx), round(cy / self._sy))
