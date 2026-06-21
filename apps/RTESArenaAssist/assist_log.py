"""
assist_log.py — ログ設定

ログレベルの役割を明確化する:
  - DEBUG   : 常時大量出力する診断 (poll timing 等)。既定では出さない。
  - INFO    : 補助的な詳細。既定では出さない。
  - RECOG   : 画面認識状態の「遷移」と「判断」を参照値付きで記録する (= 既定で出す)。
              階層 (L1-L4) 変化 / 分離 (施設セッション・panel owner) 変化 / 分離内の
              判断 (メニュー表示・応答表示等) の時だけ出力し、遷移の正否を判断できる
              ようにする。常時出力ではなく「変化時のみ」。
  - WARNING : 異常 / 矛盾 (認識の reject、未知値 等)。
  - ERROR   : 例外。

既定レベル = RECOG。常時大量ログ (DEBUG/INFO) は既定で出さず、認識遷移ログ (RECOG) と
異常 (WARNING+) のみを既定で残す。詳細が要る時は環境変数で INFO/DEBUG へ下げる。

ログ出力先:
  - <アプリフォルダ>/assist_debug.log    : 最新 1 回分 (起動ごとに上書き)
  - <アプリフォルダ>/logs/assist_<時刻>_<pid>.log: 起動ごとの履歴 (上書きされない)
"""

import logging
import os
import sys
from datetime import datetime

_logger_initialized = False

# 画面認識状態の遷移・判断ログ用のカスタムレベル (INFO=20 と WARNING=30 の間)。
# 既定でこのレベル以上を出す = 認識遷移ログは見えるが常時 INFO/DEBUG は出さない。
RECOGNITION_LEVEL = 25
logging.addLevelName(RECOGNITION_LEVEL, "RECOG")

# 起動履歴ログ (logs/assist_<時刻>_<pid>.log) の保持本数。
# 0 以下なら無制限。実機失敗ログはユーザーが手動削除するまで保持する。
_HISTORY_KEEP = 0


def recog(logger: logging.Logger, msg: str, *args) -> None:
    """画面認識状態の遷移・判断を RECOG レベルで記録する。

    呼び出し側は「変化時のみ」呼ぶこと (常時呼ばない)。参照値 (判定に使った信号値) を
    併記し、遷移の正否を後から判断できるようにする。
    """
    if logger.isEnabledFor(RECOGNITION_LEVEL):
        logger.log(RECOGNITION_LEVEL, msg, *args)


def _debug_env_value() -> str:
    """デバッグログ制御の環境変数値（正規化済み・未指定は空文字）。

    既存ルール: RTES_ARENA_ASSIST_LOG_LEVEL=INFO/DEBUG/... または
    RTES_ARENA_ASSIST_DEBUG_LOG=1 を「デバッグログ有効化」の合図に使う。
    """
    return (
        os.environ.get("RTES_ARENA_ASSIST_LOG_LEVEL")
        or os.environ.get("RTES_ARENA_ASSIST_DEBUG_LOG")
        or ""
    ).strip().upper()


# 環境変数で「デバッグログ有効化」とみなす値。
_DEBUG_ENV_ENABLED = frozenset(
    {"1", "TRUE", "YES", "ON", "DEBUG", "INFO", "WARNING", "ERROR", "RECOG"})


def _resolve_level() -> int:
    """既定は RECOG (= 認識遷移ログ + 警告のみ)。調査時だけ環境変数で詳細化する。

    環境変数 RTES_ARENA_ASSIST_LOG_LEVEL=INFO / DEBUG または
    RTES_ARENA_ASSIST_DEBUG_LOG=1 で INFO/DEBUG まで下げる (= poll timing 等の
    常時ログも出す)。
    """
    raw = _debug_env_value()
    if raw in ("1", "TRUE", "YES", "ON"):
        return logging.DEBUG
    if raw in ("DEBUG", "INFO", "WARNING", "ERROR"):
        return getattr(logging, raw)
    if raw == "RECOG":
        return RECOGNITION_LEVEL
    return RECOGNITION_LEVEL


def _should_write_log_files(frozen: bool, debug_env: str) -> bool:
    """ログファイル (assist_debug.log / logs 履歴) を書き出すかを判定する（純関数）。

    公開ビルド (= frozen exe) では既定でデバッグログを出力しない。ただし既存
    ルールの環境変数 (RTES_ARENA_ASSIST_DEBUG_LOG / _LOG_LEVEL) が有効値で
    指定された時のみ書き出す (= QA 用の逃げ道。exe ビルドでも環境変数で診断
    ログを復活できる)。dev (非 frozen・ソース実行) は従来どおり常に書き出す。
    """
    if not frozen:
        return True
    return debug_env in _DEBUG_ENV_ENABLED


def _prune_history(history_dir: str) -> None:
    """履歴ログを新しい順に _HISTORY_KEEP 本だけ残す。0 以下なら削除しない。"""
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

    # 公開ビルド (frozen exe) では既定でデバッグログを出力しない。環境変数で
    # 明示有効化された時のみ書き出す（既存ルール）。dev は従来どおり常に出力。
    frozen = bool(getattr(sys, "frozen", False))
    if not _should_write_log_files(frozen, _debug_env_value()):
        root = logging.getLogger()
        root.setLevel(level)
        # ハンドラ未設定だと last-resort 出力が走るため NullHandler を置く。
        root.addHandler(logging.NullHandler())
        return

    log_path = os.path.join(app_dir, "assist_debug.log")

    # タイムスタンプはミリ秒まで出力する。チラツキ (同一描画フレーム内/100ms 級で
    # 表示が別物へ切り替わる = 1軸化違反の観測症状) を時間軸で判別するため必須。
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 最新 1 回分 (起動ごとに上書き)。
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setLevel(level)
    fh.setFormatter(fmt)

    # 起動ごとの履歴 (上書きされない、タイムスタンプ別ファイル)。
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
    # 起動バナーは WARNING で常に 1 行出す (= どのビルドが動いているか確認できる)。
    logging.warning(
        "=== RTESArenaAssist %s started (log: %s) ===", _ver, log_path)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
