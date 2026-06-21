"""
controllers/screen_judge_controller.py — screen_judge subsystem ブリッジ

ObsRegistry 組み込み・aspect=true 警告ログ・Registry 配線・ダイアログ rect 判定を担う。

設定 screen_judge_enabled が True のとき AssistWindow.__init__ から
ロードされる。False のときはモジュール自体ロードしない（プラグイン的扱い）。
"""

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
    """screen_judge subsystem 上位コントローラ。"""

    def __init__(self, window):
        self._w = window
        self._last_capture: Optional[Image.Image] = None
        self._last_mapper: Optional[ArenaCoordMapper] = None
        self._registry = ObsRegistry()
        self._aspect_warned = False
        _log.info("ScreenJudgeController initialized (%d obs points)", len(self._registry))

    # ------------------------------------------------------------------
    # キャプチャ
    # ------------------------------------------------------------------

    def capture_now(self) -> Optional[Image.Image]:
        """現在の DOSBox クライアント領域を 1 枚キャプチャして返す。
        失敗時 None。成功時は _last_capture / _last_mapper も更新。"""
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

    # ------------------------------------------------------------------
    # 観測点レジストリ
    # ------------------------------------------------------------------

    def get_registry(self) -> ObsRegistry:
        return self._registry

    # ------------------------------------------------------------------
    # ダイアログ検出
    # ------------------------------------------------------------------

    def detect_npc_dialog(
        self,
        purpose_filter: Optional[str] = None,
        threshold: float = 0.75,
        capture_first: bool = False,
    ) -> DetectionResult:
        """NPC ダイアログ枠の表示状態を判定して返す。

        Args:
            purpose_filter: 指定した purpose の観測点のみ使用（None = 全て）
            threshold:      ヒット率閾値（デフォルト 0.75）
            capture_first:  True の場合は判定前に新規キャプチャを取得する
        """
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
