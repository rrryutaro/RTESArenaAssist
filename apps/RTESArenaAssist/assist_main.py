"""
assist_main.py — RTESArenaAssist エントリポイント
"""

import logging
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))


def _runtime_user_dir() -> str:
    """frozen 時は設定・ログを exe と同じ場所に永続化する。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE


def _runtime_resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", _runtime_user_dir())
    return _HERE


_USER_DIR = _runtime_user_dir()
_RESOURCE_DIR = _runtime_resource_dir()


def _owned_i18n_path(rel: str) -> str:
    """Assist 所有 i18n リソースの実 fs パス（disk 優先・無ければ exe 内 seed から抽出）。

    公開 frozen では _internal/i18n を撤去し seed へ集約したため、disk 直読みは失敗する。
    bundle/source_id_map/degraded_accepted は bundle 同階層前提で読まれるので、resource_fs_path で
    同一 temp ディレクトリへ抽出して整合させる（degraded は呼出側で共抽出する）。
    """
    disk = os.path.join(_RESOURCE_DIR, *rel.split("/"))
    if os.path.exists(disk):
        return disk
    try:
        import app_resources
        return app_resources.resource_fs_path(rel)
    except Exception:  # noqa: BLE001 - seed 不在は disk パスを返し呼出側でフォールバック
        return disk

# ログ・i18n・設定を初期化
import assist_log
import i18n_helper as i18n
import assist_settings as settings

assist_log.init(_USER_DIR)

# 設定を先に読み、保存済み表示言語を i18n に渡す（未設定="" → system locale→英語既定）。
settings.init(_USER_DIR)

# 公開版データ基盤: Arena ディレクトリ（既存の「ゲームフォルダ」設定 save_dir を再利用。
# A.EXE/GLOBAL.BSA のある所）が妥当なら、ユーザー資産から再生成した v2 localpack
# （RTESArenaAssist.localpack）が唯一の Arena 由来 local provider になる（公開物に Arena 原文を
# 同梱しない）。arena_dir を明示設定すればそれを優先（ゲームフォルダと別を指したい場合の上書き）。
# 対象版判定の結果（verified/unknown/invalid）。未検証版なら起動後に UI 警告を出す。
_arena_classification = None
_arena_dir = settings.get("arena_dir") or settings.get("save_dir") or ""
if not _arena_dir:
    # Arena フォルダ未設定（初回起動で設定前など）。翻訳は Arena 資産からの再生成に依存
    # するため、未設定だと localpack を生成できず翻訳が出ない。設定後の再起動で生成される。
    logging.getLogger("RTESArenaAssist").warning(
        "Arena フォルダ（save_dir）が未設定のため翻訳パックを生成しません。"
        "設定で Arena/ARENA フォルダを指定し再起動してください。")
else:
    # 対象版判定のみ実施（起動後の警告用）。localpack は別途 v2 runtime 有効化で読む。
    try:
        import arena_local_data
        _arena_classification = arena_local_data.classify_arena_dir(_arena_dir)
    except Exception:  # noqa: BLE001 - 起動を妨げない
        logging.getLogger("RTESArenaAssist").warning(
            "Arena 版判定に失敗（起動は継続）", exc_info=True)
# 原文アンカー(_original)は開発時のみディスク直読み（公開ビルドは非同梱）。
i18n.init(_RESOURCE_DIR, settings.get("ui_language") or None)

# 公開 v2 runtime: 生成済み v2 localpack を公開安全経路（source_id→source_id_map→整数ID）で
# 読込む。consumer は移行済カテゴリ（設定 i18n_v2_categories）だけ source_id で解決する。
try:
    import arena_local_data as _ald
    # カテゴリ未指定（既定）時は検証済み安全 enable-set（訳落ちゼロを
    # test_phase5_enable_integration で機械保証）を使う。明示指定があればそれを優先。
    _cfg_cats = settings.get("i18n_v2_categories")
    _v2_cats = set(_cfg_cats) if _cfg_cats else set(i18n.PHASE5_ENABLE_SET)
    # 辞書(v2 localpack)更新は**裏で起動時に実行しない**。更新要否は main() で判定し、本体表示前に
    # ダイアログでユーザーに選ばせる。ここでは現状の localpack のまま v2 を有効化する。
    # degraded_accepted.json は bundle 同階層から読まれるため、seed 時は bundle と同一 temp へ共抽出。
    _owned_i18n_path("i18n/degraded_accepted.json")
    i18n.enable_v2_public_if_available(
        bundle_path=_owned_i18n_path("i18n/i18n_bundle.json"),
        source_id_map_path=_owned_i18n_path("i18n/source_id_map.json"),
        localpack_path=_ald.v2_localpack_path(_USER_DIR) if _arena_dir else None,
        enabled=bool(settings.get("i18n_v2_runtime")),
        categories=_v2_cats,
        user_dir=_USER_DIR)
except Exception:  # noqa: BLE001 - 起動を妨げない
    logging.getLogger("RTESArenaAssist").warning(
        "起動時の v2 公開 runtime 有効化に失敗（v1 継続）", exc_info=True)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from assist_window import AssistWindow


def _reinit_translation_after_wizard(arena_dir: str) -> None:
    """初回ウィザード完了後: 生成済み localpack で翻訳を再初期化する（再起動不要にする）。"""
    try:
        import arena_local_data as _ald
        # v2 localpack が唯一の Arena provider。生成済み localpack を v2 runtime で読み直す。
        i18n.init(_RESOURCE_DIR, settings.get("ui_language") or None)
        _cfg = settings.get("i18n_v2_categories")
        _cats = set(_cfg) if _cfg else set(i18n.PHASE5_ENABLE_SET)
        _owned_i18n_path("i18n/degraded_accepted.json")
        i18n.enable_v2_public_if_available(
            bundle_path=_owned_i18n_path("i18n/i18n_bundle.json"),
            source_id_map_path=_owned_i18n_path("i18n/source_id_map.json"),
            localpack_path=_ald.v2_localpack_path(_USER_DIR),
            enabled=bool(settings.get("i18n_v2_runtime")),
            categories=_cats, user_dir=_USER_DIR)
    except Exception:  # noqa: BLE001 - 起動を妨げない
        logging.getLogger("RTESArenaAssist").warning(
            "ウィザード後の翻訳再初期化に失敗（再起動で反映されます）", exc_info=True)


def _maybe_update_dictionary() -> None:
    """本体表示前の辞書更新フロー（裏で自動更新せず明示確認後に実行）。

    辞書(v2 localpack)が古い時だけ、本体を出す前にダイアログで [更新する]／[更新せず起動] を
    選ばせる。更新は localpack 内の再写像キャッシュからの**採取なし再写像**で一瞬。
    更新後は v2 を再有効化して新しい辞書を反映する（再起動不要）。
    """
    if not _arena_dir:
        return
    try:
        import arena_local_data as _ald
        status = _ald.v2_localpack_update_status(_USER_DIR)
        if not status or not status.get("needed"):
            return
        if status.get("is_dev"):
            detail = i18n.tr("dict_update.detail_dev")
        else:
            detail = i18n.tr("dict_update.detail_release").format(
                frm=status.get("from"), to=status.get("to"))
        box = QMessageBox(None)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(i18n.tr("dict_update.title"))
        box.setText(i18n.tr("dict_update.message"))
        box.setInformativeText(detail)
        btn_update = box.addButton(i18n.tr("dict_update.update"), QMessageBox.AcceptRole)
        box.addButton(i18n.tr("dict_update.skip"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_update:
            return  # 更新せず起動（既存辞書のまま）
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # localpack 内の再写像キャッシュから作り直す（採取なし・一瞬）。キャッシュ未保存の
            # 古い localpack は単独再写像不可＝重い再生成フロー（_maybe_regen_localpack）へ委ねる。
            _ald.rebuild_v2_localpack_standalone(_USER_DIR)
        finally:
            QApplication.restoreOverrideCursor()
        # 新しい辞書を反映（再有効化）。
        _cfg = settings.get("i18n_v2_categories")
        _cats = set(_cfg) if _cfg else set(i18n.PHASE5_ENABLE_SET)
        _owned_i18n_path("i18n/degraded_accepted.json")
        i18n.enable_v2_public_if_available(
            bundle_path=_owned_i18n_path("i18n/i18n_bundle.json"),
            source_id_map_path=_owned_i18n_path("i18n/source_id_map.json"),
            localpack_path=_ald.v2_localpack_path(_USER_DIR),
            enabled=bool(settings.get("i18n_v2_runtime")),
            categories=_cats, user_dir=_USER_DIR)
    except Exception:  # noqa: BLE001 - 更新失敗は起動を妨げない（既存辞書で継続）
        logging.getLogger("RTESArenaAssist").warning(
            "辞書更新フローに失敗（既存辞書で継続）", exc_info=True)


def _maybe_regen_localpack() -> None:
    """本体表示前の**重い辞書再生成**フロー（裏で再生成しない・明示確認後に実行）。

    localpack が古く再生成（EXE 由来メモリ採取込み）が要る時だけ、本体を出す前にダイアログで
    [更新する]／[更新せず起動] を選ばせる。更新時は進捗バーを出して再生成し（Arena 起動が必要）、
    完了後に翻訳を再初期化する。裏で勝手に走らせない。
    """
    if not _arena_dir:
        return
    analyzer = None
    try:
        import arena_local_data as _ald
        try:
            from arena_bridge import ArenaMemoryAnalyzer
            _a = ArenaMemoryAnalyzer()
            if _a.attach():
                analyzer = _a
        except Exception:  # noqa: BLE001 - DOSBox 未起動等
            analyzer = None
        cls = arena_local_data.classify_arena_dir(_arena_dir)
        # 判定も生成も localpack 基準（唯一の Arena 由来 local provider）。
        if not _ald.v2_localpack_needs_regen(_arena_dir, _USER_DIR,
                                             analyzer is not None, classification=cls):
            return
        box = QMessageBox(None)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(i18n.tr("dict_update.title"))
        box.setText(i18n.tr("dict_regen.message"))
        box.setInformativeText(i18n.tr("dict_regen.detail"))
        btn_update = box.addButton(i18n.tr("dict_update.update"), QMessageBox.AcceptRole)
        box.addButton(i18n.tr("dict_update.skip"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_update:
            return  # 更新せず起動（古い localpack のまま）
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QThread, QEventLoop, Signal
        dlg = QProgressDialog(i18n.tr("dict_regen.progress"), None, 0, 100, None)
        dlg.setWindowTitle(i18n.tr("dict_update.title"))
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.show()

        # localpack 生成（メモリ採取込みで重い）は **worker thread** で実行する。
        # UI スレッドで走らせると採取区間で processEvents の間隔が空き、ウィンドウが
        # 固まって OS が「応答なし」を表示する。worker 化＋メインの QEventLoop で
        # 常にイベントを回し、進捗はクロススレッド signal（queued）で受けて随時更新する。
        class _RegenWorker(QThread):
            progressed = Signal(float, str)

            def __init__(self, arena_dir, user_dir, analyzer, cls):
                super().__init__()
                self._arena_dir = arena_dir
                self._user_dir = user_dir
                self._analyzer = analyzer
                self._cls = cls
                self.failed = False

            def run(self):
                try:
                    _ald.build_local_pack(
                        self._arena_dir, self._user_dir, self._analyzer,
                        classification=self._cls,
                        progress=lambda f, l: self.progressed.emit(
                            float(f), str(l)))
                except Exception:  # noqa: BLE001 - 失敗は既存辞書で継続
                    self.failed = True

        worker = _RegenWorker(_arena_dir, _USER_DIR, analyzer, cls)

        def _on_prog(frac: float, label: str) -> None:
            dlg.setLabelText(label)
            dlg.setValue(max(0, min(100, int(frac * 100))))

        worker.progressed.connect(_on_prog)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()  # UI イベントを回し続ける＝固まらない（応答なし回避）
        dlg.setValue(100)
        dlg.close()
        if not worker.failed:
            _reinit_translation_after_wizard(_arena_dir)
    except Exception:  # noqa: BLE001 - 再生成失敗は起動を妨げない（既存の辞書で継続）
        logging.getLogger("RTESArenaAssist").warning(
            "辞書再生成フローに失敗（既存の辞書で継続）", exc_info=True)
    finally:
        if analyzer is not None:
            try:
                analyzer.detach()
            except Exception:  # noqa: BLE001
                pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RTESArenaAssist")

    # 多重起動の検出: 既に起動中なら、起動中インスタンスを終了させず（未保存の
    # 拡張データを失わないため）、警告を表示して起動中ウィンドウを前面化し、この
    # 新しいプロセスは起動を中止する。
    try:
        from single_instance import already_running, activate_existing_window
        if already_running():
            QMessageBox.information(
                None, i18n.tr("app.title"), i18n.tr("app.already_running"))
            activate_existing_window()
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass

    # 初回実行: Arena フォルダ未設定 or 翻訳パック未生成なら、フォルダ選択＋生成ウィザードを出す。
    # 完了後に翻訳を再初期化して再起動不要にする。スキップ時は v1（翻訳なし）で続行。
    try:
        from windows.first_run_wizard import FirstRunWizard, needs_first_run
        if needs_first_run(_USER_DIR):
            _wiz = FirstRunWizard(_USER_DIR, _RESOURCE_DIR)
            # 初回ウィザードの実描画を記録（生キー表示の切り分け用・サポート診断）。
            # title が "setup.window_title" 等の生キーなら setup.json 未ロード＝要調査。
            logging.getLogger("RTESArenaAssist").warning(
                "first_run_wizard 描画: lang=%s strings=%d title=%r lang_title=%r",
                _wiz._lang, len(_wiz._strings), _wiz.windowTitle(),
                _wiz._lang_title.text())
            if _wiz.exec():
                _reinit_translation_after_wizard(_wiz.arena_dir)
            else:
                # セットアップ未完了なら本体を表示せず終了する（要件: 完了まで本体非表示）。
                sys.exit(0)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - ウィザード失敗で起動を妨げない
        logging.getLogger("RTESArenaAssist").warning(
            "初回実行ウィザードの表示に失敗", exc_info=True)

    # 既存ユーザー（辞書 localpack 生成済み・初回でない）向け: 辞書が古ければ本体表示前にダイアログで
    # 更新可否を選ばせる（**裏で自動更新しない**）。新規ユーザーはウィザードで最新辞書を生成済み＝対象外。
    # ①重い再生成（EXE 由来メモリ採取込み・localpack content_version 変化）→ ダイアログ＋進捗。
    _maybe_regen_localpack()
    # ②軽い辞書再写像（v2 localpack の生成ロジック/registry 変化・採取なし）→ ダイアログ。
    _maybe_update_dictionary()

    win = AssistWindow()
    win.show()

    # 未検証の Arena データ（対応指紋セット不一致＝unknown）なら警告を表面化する。
    # 一部の実行ファイル由来テキストが生成されないため（DAT/VFS 由来の翻訳は継続）。
    # invalid（ディレクトリ不正）は別の既存条件なので対象外。verified なら何も出さない。
    if _arena_classification and _arena_classification.get("status") == "unknown":
        QMessageBox.warning(
            win, i18n.tr("app.title"), i18n.tr("app.unverified_arena"))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
