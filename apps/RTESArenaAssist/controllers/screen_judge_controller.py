
import logging
from typing import Optional

import assist_settings as settings
import dosbox_conf as dc
from PIL import Image

from screen_judge.capture import capture_client_area
from screen_judge.coord_mapper import ArenaCoordMapper
from screen_judge.dialog_detector import DetectionResult, DialogState, detect_dialog
from screen_judge.registry import ObsRegistry

_log = logging.getLogger("screen_judge_controller")


class ScreenJudgeController:

    def __init__(self, window):
        self._w = window
        self._last_capture: Optional[Image.Image] = None
        self._last_mapper: Optional[ArenaCoordMapper] = None
        self._registry = ObsRegistry()
        self._aspect_warned = False
        _log.info("ScreenJudgeController initialized (%d obs points)", len(self._registry))


    def capture_now(self) -> Optional[Image.Image]:
        if not self._aspect_warned:
            try:
                conf_path = settings.get("dosbox_conf_path", "") or dc.DEFAULT_CONF_PATH
                aspect_str = (dc.get_aspect(conf_path) or "false").lower()
                if aspect_str == "true":
                    _log.warning(
                        "DOSBox aspect=true detected — coord_mapper does not "
                        "compensate letterbox; observation points may be off"
                    )
            except Exception:
                pass
            self._aspect_warned = True

        hwnd = self._w._layout_mgr.get_dosbox_hwnd()
        if not hwnd:
            return None
        img = capture_client_area(hwnd)
        if img is None:
            return None
        cw, ch = img.size
        self._last_capture = img
        self._last_mapper = ArenaCoordMapper(cw, ch)
        return img

    def get_last_capture(self) -> Optional[Image.Image]:
        return self._last_capture

    def get_last_mapper(self) -> Optional[ArenaCoordMapper]:
        return self._last_mapper


    def get_registry(self) -> ObsRegistry:
        return self._registry


    def detect_npc_dialog(
        self,
        purpose_filter: Optional[str] = None,
        threshold: float = 0.75,
        capture_first: bool = False,
    ) -> DetectionResult:
        if capture_first:
            self.capture_now()

        img = self._last_capture
        mapper = self._last_mapper

        if img is None or mapper is None:
            return DetectionResult(
                state=DialogState.UNKNOWN,
                hit_count=0,
                total_count=0,
                hit_ratio=0.0,
                detail="no capture available",
            )

        result = detect_dialog(
            img=img,
            mapper=mapper,
            registry=self._registry,
            purpose_filter=purpose_filter,
            threshold=threshold,
        )
        _log.debug("detect_npc_dialog: %s — %s", result.state.value, result.detail)
        return result
