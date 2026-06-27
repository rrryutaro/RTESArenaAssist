from __future__ import annotations
import os
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget
import arena_local_data as ald
import assist_settings as settings
import i18n_helper as i18n
from arena_aexe import GenerationCancelled

class _GenerateWorker(QThread):
    progress = Signal(float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, arena_dir: str, user_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._arena_dir = arena_dir
        self._user_dir = user_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        analyzer = None
        try:
            try:
                from arena_bridge import ArenaMemoryAnalyzer
                a = ArenaMemoryAnalyzer()
                if a.attach():
                    analyzer = a
            except Exception:
                analyzer = None
            cls = ald.classify_arena_dir(self._arena_dir)
            fp = ald.build_local_pack(self._arena_dir, self._user_dir, analyzer, classification=cls, progress=lambda f, lbl: self.progress.emit(float(f), str(lbl)), cancel_check=lambda: self._cancel)
            ok = bool(fp) and os.path.isfile(ald.v2_localpack_path(self._user_dir))
            if ok:
                self.finished_ok.emit(ald.v2_localpack_path(self._user_dir))
            else:
                self.failed.emit('INVALID_ARENA')
        except GenerationCancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if analyzer is not None:
                try:
                    analyzer.detach()
                except Exception:
                    pass

class FirstRunWizard(QDialog):

    def __init__(self, user_dir: str, resource_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._user_dir = user_dir
        self._resource_dir = resource_dir
        self._worker: _GenerateWorker | None = None
        self._force_quit = False
        self._accepted = False
        self._disp = 0.0
        self._target = 0.0
        self._stall = 0
        self._creep = QTimer(self)
        self._creep.setInterval(80)
        self._creep.timeout.connect(self._tick)
        self._arena_dir = ''
        self._folder_valid = False
        self._arena_running = False
        self._lang = self._initial_lang()
        self._strings = self._load_setup(self._lang)
        if not self._strings:
            import logging
            logging.getLogger('RTESArenaAssist').warning('first_run_wizard: setup.json 読込0件 resource=%r lang=%s', resource_dir, self._lang)
        self.setModal(True)
        self.setMinimumWidth(580)
        self._build_ui()
        self._retranslate()
        self._refresh_arena()
    _LANGS = ('ja', 'en', 'es')

    def _initial_lang(self) -> str:
        saved = (settings.get('ui_language') or '').lower()
        if saved in self._LANGS:
            return saved
        import locale
        try:
            loc = locale.getdefaultlocale()[0] or ''
        except Exception:
            loc = ''
        code = (loc.split('_')[0].split('-')[0] or '').lower()
        return code if code in self._LANGS else 'en'

    def _load_setup(self, lang: str) -> dict:
        import json
        out: dict = {}
        for L in (lang, 'en'):
            text = None
            p = os.path.join(self._resource_dir, 'i18n', L, 'setup.json')
            try:
                with open(p, encoding='utf-8') as f:
                    text = f.read()
            except OSError:
                try:
                    import app_resources
                    text = app_resources.read_text(f'i18n/{L}/setup.json')
                except Exception:
                    text = None
            if text is None:
                continue
            try:
                d = json.loads(text)
            except ValueError:
                continue
            for k, v in d.items():
                out.setdefault(k, v)
        return out

    def _t(self, key: str, **kw) -> str:
        s = self._strings.get(key, key)
        if kw:
            try:
                s = s.format(**kw)
            except (KeyError, ValueError, IndexError):
                pass
        return s

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._stack = QStackedWidget()
        root.addWidget(self._stack)
        self._stack.addWidget(self._build_lang_page())
        self._stack.addWidget(self._build_arena_page())
        self._stack.addWidget(self._build_gen_page())

    def _build_lang_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._lang_title = QLabel()
        self._lang_title.setStyleSheet('font-weight:bold;font-size:14px;')
        self._lang_prompt = QLabel()
        self._lang_prompt.setWordWrap(True)
        self._lang_combo = QComboBox()
        self._lang_combo.addItem('日本語', 'ja')
        self._lang_combo.addItem('English', 'en')
        self._lang_combo.addItem('Español', 'es')
        idx = max(0, self._lang_combo.findData(self._lang))
        self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        v.addWidget(self._lang_title)
        v.addWidget(self._lang_prompt)
        v.addWidget(self._lang_combo)
        v.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._lang_next = QPushButton()
        self._lang_next.setDefault(True)
        self._lang_next.clicked.connect(self._on_lang_next)
        row.addWidget(self._lang_next)
        v.addLayout(row)
        return w

    def _build_arena_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._arena_title = QLabel()
        self._arena_title.setStyleSheet('font-weight:bold;font-size:14px;')
        self._arena_intro = QLabel()
        self._arena_intro.setWordWrap(True)
        v.addWidget(self._arena_title)
        v.addWidget(self._arena_intro)
        self._folder_label = QLabel()
        v.addWidget(self._folder_label)
        row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.textChanged.connect(self._on_path_changed)
        self._browse_btn = QPushButton()
        self._browse_btn.clicked.connect(self._browse)
        self._refresh_btn = QPushButton()
        self._refresh_btn.clicked.connect(self._refresh_arena)
        row.addWidget(self._path_edit, 1)
        row.addWidget(self._browse_btn)
        row.addWidget(self._refresh_btn)
        v.addLayout(row)
        self._arena_status = QLabel()
        self._arena_status.setWordWrap(True)
        v.addWidget(self._arena_status)
        v.addStretch(1)
        row2 = QHBoxLayout()
        self._arena_back = QPushButton()
        self._arena_back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        row2.addWidget(self._arena_back)
        row2.addStretch(1)
        self._gen_btn = QPushButton()
        self._gen_btn.setDefault(True)
        self._gen_btn.clicked.connect(self._start_generate)
        row2.addWidget(self._gen_btn)
        v.addLayout(row2)
        return w

    def _build_gen_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._gen_status = QLabel()
        self._gen_status.setWordWrap(True)
        self._prog_label = QLabel()
        v.addWidget(self._gen_status)
        v.addWidget(self._bar)
        v.addWidget(self._prog_label)
        v.addStretch(1)
        return w

    def _retranslate(self) -> None:
        self.setWindowTitle(self._t('setup.window_title'))
        self._lang_title.setText(self._t('setup.lang.title'))
        self._lang_prompt.setText(self._t('setup.lang.prompt'))
        self._lang_next.setText(self._t('setup.btn.next'))
        self._arena_title.setText(self._t('setup.arena.title'))
        self._arena_intro.setText(self._t('setup.arena.intro'))
        self._folder_label.setText(self._t('setup.arena.folder_label'))
        self._browse_btn.setText(self._t('setup.arena.browse'))
        self._refresh_btn.setText(self._t('setup.arena.refresh'))
        self._arena_back.setText(self._t('setup.btn.back'))
        self._gen_btn.setText(self._t('setup.btn.generate'))
        self._update_arena_status()

    def _on_lang_changed(self, _idx: int) -> None:
        code = self._lang_combo.currentData() or 'en'
        self._lang = code
        self._strings = self._load_setup(code)
        try:
            settings.set_val('ui_language', code)
            i18n.init(self._resource_dir, code)
        except Exception:
            pass
        self._retranslate()

    def _on_lang_next(self) -> None:
        self._stack.setCurrentIndex(1)
        self._refresh_arena()

    def _refresh_arena(self) -> None:
        detected = None
        try:
            detected = ald.detect_running_arena_dir()
        except Exception:
            detected = None
        self._arena_running = bool(detected)
        if detected:
            if not (self._path_edit.text().strip() and ald.is_valid_arena_dir(self._path_edit.text().strip())):
                self._path_edit.setText(detected)
        self._update_arena_status()

    def _on_path_changed(self, text: str) -> None:
        path = text.strip()
        self._folder_valid = bool(path) and ald.is_valid_arena_dir(path)
        if self._folder_valid:
            self._arena_dir = path
        self._update_arena_status()

    def _update_arena_status(self) -> None:
        if not self._arena_running:
            self._arena_status.setText(self._t('setup.arena.running_required'))
            if hasattr(self, '_gen_btn'):
                self._gen_btn.setEnabled(False)
            return
        if not self._folder_valid:
            self._arena_status.setText(self._t('setup.arena.invalid'))
            self._gen_btn.setEnabled(False)
            return
        self._arena_status.setText(self._t('setup.arena.detected') + '\n' + self._t('setup.arena.ok'))
        self._gen_btn.setEnabled(True)

    def _browse(self) -> None:
        start = self._path_edit.text().strip() or os.path.expanduser('~')
        path = QFileDialog.getExistingDirectory(self, self._t('setup.arena.folder_label'), start)
        if path:
            self._path_edit.setText(path)

    def _start_generate(self) -> None:
        if not (self._arena_running and self._folder_valid and self._arena_dir):
            return
        try:
            settings.set_val('save_dir', self._arena_dir)
        except Exception:
            pass
        self._stack.setCurrentIndex(2)
        self._disp = 0.0
        self._target = 0.0
        self._stall = 0
        self._bar.setValue(0)
        self._gen_status.setText(self._t('setup.gen.running'))
        self._worker = _GenerateWorker(self._arena_dir, self._user_dir, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._creep.start()

    def _tick(self) -> None:
        self._stall += 1
        ceil = min(0.985, self._target + 0.08 + min(0.12, self._stall * 0.0008))
        if self._disp < ceil:
            self._disp = min(ceil, self._disp + 0.0025)
            self._bar.setValue(int(self._disp * 100))

    def _on_progress(self, frac: float, label: str) -> None:
        f = max(0.0, min(1.0, frac))
        self._stall = 0
        self._target = max(self._target, f)
        self._disp = max(self._disp, f)
        self._bar.setValue(int(self._disp * 100))
        self._prog_label.setText(label)

    def _on_done(self, pack_path: str) -> None:
        self._creep.stop()
        self._accepted = True
        self._disp = self._target = 1.0
        self._bar.setValue(100)
        self._gen_status.setText(self._t('setup.gen.done'))
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._creep.stop()
        m = self._t('setup.arena.invalid') if msg == 'INVALID_ARENA' else msg
        self._gen_status.setText(self._t('setup.gen.failed', msg=m))
        self._stack.setCurrentIndex(1)

    def _stop_worker(self) -> None:
        self._creep.stop()
        w = self._worker
        if not self._accepted and w is not None and w.isRunning():
            self._force_quit = True
            w.cancel()
            if not w.wait(1200):
                w.terminate()
                w.wait(1500)
        self._worker = None

    def _hard_exit_if_needed(self) -> None:
        if self._accepted or not self._force_quit:
            return
        try:
            import single_instance
            single_instance.release()
        except Exception:
            pass
        import os
        os._exit(0)

    def reject(self) -> None:
        self._stop_worker()
        self._hard_exit_if_needed()
        super().reject()

    def closeEvent(self, event) -> None:
        self._stop_worker()
        self._hard_exit_if_needed()
        super().closeEvent(event)

    @property
    def arena_dir(self) -> str:
        return self._arena_dir

def needs_first_run(user_dir: str) -> bool:
    try:
        arena_dir = settings.get('save_dir') or settings.get('arena_dir') or ''
    except Exception:
        arena_dir = ''
    if not arena_dir or not ald.is_valid_arena_dir(arena_dir):
        return True
    return not os.path.isfile(ald.v2_localpack_path(user_dir))
