
import logging
import os
import sys
from datetime import datetime

_logger_initialized = False

RECOGNITION_LEVEL = 25
logging.addLevelName(RECOGNITION_LEVEL, "RECOG")

_HISTORY_KEEP = 0


def recog(logger: logging.Logger, msg: str, *args) -> None:
    if logger.isEnabledFor(RECOGNITION_LEVEL):
        logger.log(RECOGNITION_LEVEL, msg, *args)


def _debug_env_value() -> str:
    return (
        os.environ.get("RTES_ARENA_ASSIST_LOG_LEVEL")
        or os.environ.get("RTES_ARENA_ASSIST_DEBUG_LOG")
        or ""
    ).strip().upper()


_DEBUG_ENV_ENABLED = frozenset(
    {"1", "TRUE", "YES", "ON", "DEBUG", "INFO", "WARNING", "ERROR", "RECOG"})


def _resolve_level() -> int:
    raw = _debug_env_value()
    if raw in ("1", "TRUE", "YES", "ON"):
        return logging.DEBUG
    if raw in ("DEBUG", "INFO", "WARNING", "ERROR"):
        return getattr(logging, raw)
    if raw == "RECOG":
        return RECOGNITION_LEVEL
    return RECOGNITION_LEVEL


def _should_write_log_files(frozen: bool, debug_env: str) -> bool:
    if not frozen:
        return True
    return debug_env in _DEBUG_ENV_ENABLED


def _prune_history(history_dir: str) -> None:
    if _HISTORY_KEEP <= 0:
        return
    try:
        files = sorted(
            f for f in os.listdir(history_dir)
            if f.startswith("assist_") and f.endswith(".log")
        )
    except OSError:
        return
    if len(files) <= _HISTORY_KEEP:
        return
    for old in files[:-_HISTORY_KEEP]:
        try:
            os.remove(os.path.join(history_dir, old))
        except OSError:
            pass


def init(app_dir: str) -> None:
    global _logger_initialized
    if _logger_initialized:
        return
    _logger_initialized = True

    level = _resolve_level()

    frozen = bool(getattr(sys, "frozen", False))
    if not _should_write_log_files(frozen, _debug_env_value()):
        root = logging.getLogger()
        root.setLevel(level)
        root.addHandler(logging.NullHandler())
        return

    log_path = os.path.join(app_dir, "assist_debug.log")

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    history_fh = None
    try:
        history_dir = os.path.join(app_dir, "logs")
        os.makedirs(history_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        history_path = os.path.join(
            history_dir, f"assist_{stamp}_{os.getpid()}.log")
        history_fh = logging.FileHandler(
            history_path, encoding="utf-8", mode="w")
        history_fh.setLevel(level)
        history_fh.setFormatter(fmt)
        _prune_history(history_dir)
    except OSError:
        history_fh = None

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(fh)
    if history_fh is not None:
        root.addHandler(history_fh)
    root.addHandler(sh)

    try:
        from version import version_string as _vs
        _ver = _vs()
    except Exception:  # noqa: BLE001
        _ver = "unknown"
    logging.warning(
        "=== RTESArenaAssist %s started (log: %s) ===", _ver, log_path)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
