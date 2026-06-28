import logging
import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
_HERE = os.path.dirname(os.path.abspath(__file__))

def _runtime_user_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE

def _runtime_resource_dir() -> str:
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', _runtime_user_dir())
    return _HERE
_USER_DIR = _runtime_user_dir()
_RESOURCE_DIR = _runtime_resource_dir()
_PUBLIC_RUNTIME_I18N = True

def _owned_i18n_path(rel: str) -> str:
    disk = os.path.join(_RESOURCE_DIR, *rel.split('/'))
    if os.path.exists(disk):
        return disk
    try:
        import app_resources
        return app_resources.resource_fs_path(rel)
    except Exception:
        return disk
import assist_log
import i18n_helper as i18n
import assist_settings as settings
assist_log.init(_USER_DIR)
settings.init(_USER_DIR)
_arena_classification = None
_arena_dir = settings.get('arena_dir') or settings.get('save_dir') or ''
if not _arena_dir:
    logging.getLogger('RTESArenaAssist').warning('Arena フォルダ（save_dir）が未設定のため翻訳パックを生成しません。設定で Arena/ARENA フォルダを指定し再起動してください。')
else:
    try:
        import arena_local_data
        _arena_classification = arena_local_data.classify_arena_dir(_arena_dir)
    except Exception:
        logging.getLogger('RTESArenaAssist').warning('Arena 版判定に失敗（起動は継続）', exc_info=True)
i18n.init(_RESOURCE_DIR, settings.get('ui_language') or None, public_runtime=_PUBLIC_RUNTIME_I18N)
try:
    import arena_local_data as _ald
    _cfg_cats = settings.get('i18n_v2_categories')
    _v2_cats = set(_cfg_cats) if _cfg_cats else set(i18n.PHASE5_ENABLE_SET)
    _owned_i18n_path('i18n/degraded_accepted.json')
    i18n.enable_v2_public_if_available(bundle_path=_owned_i18n_path('i18n/i18n_bundle.json'), source_id_map_path=_owned_i18n_path('i18n/source_id_map.json'), localpack_path=_ald.v2_localpack_path(_USER_DIR) if _arena_dir else None, enabled=bool(settings.get('i18n_v2_runtime')), categories=_v2_cats, user_dir=_USER_DIR)
except Exception:
    logging.getLogger('RTESArenaAssist').warning('起動時の v2 公開 runtime 有効化に失敗（v1 継続）', exc_info=True)
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from assist_window import AssistWindow

def _reinit_translation_after_wizard(arena_dir: str) -> None:
    try:
        import arena_local_data as _ald
        i18n.init(_RESOURCE_DIR, settings.get('ui_language') or None, public_runtime=_PUBLIC_RUNTIME_I18N)
        _cfg = settings.get('i18n_v2_categories')
        _cats = set(_cfg) if _cfg else set(i18n.PHASE5_ENABLE_SET)
        _owned_i18n_path('i18n/degraded_accepted.json')
        i18n.enable_v2_public_if_available(bundle_path=_owned_i18n_path('i18n/i18n_bundle.json'), source_id_map_path=_owned_i18n_path('i18n/source_id_map.json'), localpack_path=_ald.v2_localpack_path(_USER_DIR), enabled=bool(settings.get('i18n_v2_runtime')), categories=_cats, user_dir=_USER_DIR)
    except Exception:
        logging.getLogger('RTESArenaAssist').warning('ウィザード後の翻訳再初期化に失敗（再起動で反映されます）', exc_info=True)

def _maybe_update_dictionary() -> None:
    if not _arena_dir:
        return
    try:
        import arena_local_data as _ald
        status = _ald.v2_localpack_update_status(_USER_DIR)
        if not status or not status.get('needed'):
            return
        if status.get('is_dev'):
            detail = i18n.tr('dict_update.detail_dev')
        else:
            detail = i18n.tr('dict_update.detail_release').format(frm=status.get('from'), to=status.get('to'))
        box = QMessageBox(None)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(i18n.tr('dict_update.title'))
        box.setText(i18n.tr('dict_update.message'))
        box.setInformativeText(detail)
        btn_update = box.addButton(i18n.tr('dict_update.update'), QMessageBox.AcceptRole)
        box.addButton(i18n.tr('dict_update.skip'), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_update:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            _ald.rebuild_v2_localpack_standalone(_USER_DIR)
        finally:
            QApplication.restoreOverrideCursor()
        _cfg = settings.get('i18n_v2_categories')
        _cats = set(_cfg) if _cfg else set(i18n.PHASE5_ENABLE_SET)
        _owned_i18n_path('i18n/degraded_accepted.json')
        i18n.enable_v2_public_if_available(bundle_path=_owned_i18n_path('i18n/i18n_bundle.json'), source_id_map_path=_owned_i18n_path('i18n/source_id_map.json'), localpack_path=_ald.v2_localpack_path(_USER_DIR), enabled=bool(settings.get('i18n_v2_runtime')), categories=_cats, user_dir=_USER_DIR)
    except Exception:
        logging.getLogger('RTESArenaAssist').warning('辞書更新フローに失敗（既存辞書で継続）', exc_info=True)

def _maybe_regen_localpack() -> None:
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
        except Exception:
            analyzer = None
        cls = arena_local_data.classify_arena_dir(_arena_dir)
        if not _ald.v2_localpack_needs_regen(_arena_dir, _USER_DIR, analyzer is not None, classification=cls):
            return
        box = QMessageBox(None)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(i18n.tr('dict_update.title'))
        box.setText(i18n.tr('dict_regen.message'))
        box.setInformativeText(i18n.tr('dict_regen.detail'))
        btn_update = box.addButton(i18n.tr('dict_update.update'), QMessageBox.AcceptRole)
        box.addButton(i18n.tr('dict_update.skip'), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_update:
            return
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QThread, QEventLoop, Signal
        dlg = QProgressDialog(i18n.tr('dict_regen.progress'), None, 0, 100, None)
        dlg.setWindowTitle(i18n.tr('dict_update.title'))
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.show()

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
                    _ald.build_local_pack(self._arena_dir, self._user_dir, self._analyzer, classification=self._cls, progress=lambda f, l: self.progressed.emit(float(f), str(l)))
                except Exception:
                    self.failed = True
        worker = _RegenWorker(_arena_dir, _USER_DIR, analyzer, cls)

        def _on_prog(frac: float, label: str) -> None:
            dlg.setLabelText(label)
            dlg.setValue(max(0, min(100, int(frac * 100))))
        worker.progressed.connect(_on_prog)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()
        dlg.setValue(100)
        dlg.close()
        if not worker.failed:
            _reinit_translation_after_wizard(_arena_dir)
    except Exception:
        logging.getLogger('RTESArenaAssist').warning('辞書再生成フローに失敗（既存の辞書で継続）', exc_info=True)
    finally:
        if analyzer is not None:
            try:
                analyzer.detach()
            except Exception:
                pass

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('RTESArenaAssist')
    try:
        from single_instance import already_running, activate_existing_window
        if already_running():
            QMessageBox.information(None, i18n.tr('app.title'), i18n.tr('app.already_running'))
            activate_existing_window()
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    try:
        from windows.first_run_wizard import FirstRunWizard, needs_first_run
        if needs_first_run(_USER_DIR):
            _wiz = FirstRunWizard(_USER_DIR, _RESOURCE_DIR)
            logging.getLogger('RTESArenaAssist').warning('first_run_wizard 描画: lang=%s strings=%d title=%r lang_title=%r', _wiz._lang, len(_wiz._strings), _wiz.windowTitle(), _wiz._lang_title.text())
            if _wiz.exec():
                _reinit_translation_after_wizard(_wiz.arena_dir)
            else:
                sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        logging.getLogger('RTESArenaAssist').warning('初回実行ウィザードの表示に失敗', exc_info=True)
    _maybe_regen_localpack()
    _maybe_update_dictionary()
    win = AssistWindow()
    win.show()
    if _arena_classification and _arena_classification.get('status') == 'unknown':
        QMessageBox.warning(win, i18n.tr('app.title'), i18n.tr('app.unverified_arena'))
    sys.exit(app.exec())
if __name__ == '__main__':
    main()
