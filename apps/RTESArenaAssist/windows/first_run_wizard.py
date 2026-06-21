"""初回実行ウィザード。

公開ビルドは Arena 原文を同梱せず、起動時にユーザーの Arena データから翻訳パック
（``RTESArenaAssist.localpack``）を再生成する。本ウィザードは初回起動（Arena フォルダ
未設定 or localpack 未生成）で表示し、次の 3 ページで案内する:

  1. 表示言語の選択（既定＝システム言語）。選択で即 UI を切替える。
  2. ゲームの場所（Arena 起動が前提）。起動中の Arena プロセスからインストール先を
     自動検出。未起動なら「再確認」で再検出（起動するまで先へ進めない）。
  3. 翻訳ファイルの生成（プログレスバー・ワーカースレッド）。

UI 文言は assist-UI の翻訳キー（``setup.*`` / i18n.tr）。原文と翻訳は i18n 層で分離する。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import arena_local_data as ald
import assist_settings as settings
import i18n_helper as i18n
from arena_aexe import GenerationCancelled


class _GenerateWorker(QThread):
    """翻訳パック生成をバックグラウンドで実行する（Arena 起動中ならメモリ採取も行う）。

    キャンセル要求（`cancel()`）は生成のフェーズ境界・メモリ走査で検査され、
    `GenerationCancelled` で即中断する。これによりウィザードを閉じた瞬間にワーカーが
    止まり、プロセスが速やかに終了してミューテックスを解放する。
    """

    progress = Signal(float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, arena_dir: str, user_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._arena_dir = arena_dir
        self._user_dir = user_dir
        self._cancel = False

    def cancel(self) -> None:
        """生成のキャンセルを要求する（フェーズ境界/テーブル走査で中断）。"""
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        analyzer = None
        try:
            try:
                from arena_bridge import ArenaMemoryAnalyzer
                a = ArenaMemoryAnalyzer()
                if a.attach():
                    analyzer = a
            except Exception:  # noqa: BLE001
                analyzer = None
            cls = ald.classify_arena_dir(self._arena_dir)
            # localpack を生成する（唯一の Arena 由来 local provider）。
            fp = ald.build_local_pack(
                self._arena_dir, self._user_dir, analyzer,
                classification=cls,
                progress=lambda f, lbl: self.progress.emit(float(f), str(lbl)),
                cancel_check=lambda: self._cancel)
            ok = bool(fp) and os.path.isfile(ald.v2_localpack_path(self._user_dir))
            if ok:
                self.finished_ok.emit(ald.v2_localpack_path(self._user_dir))
            else:
                self.failed.emit("INVALID_ARENA")  # 文言はダイアログ側 _t で解決
        except GenerationCancelled:
            pass  # ユーザーキャンセル: 何も emit せず静かに終了（ダイアログは閉じる）
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            if analyzer is not None:
                try:
                    analyzer.detach()
                except Exception:  # noqa: BLE001
                    pass


class FirstRunWizard(QDialog):
    """言語選択＋ゲーム検出＋翻訳生成の初回ウィザード。"""

    def __init__(self, user_dir: str, resource_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._user_dir = user_dir
        self._resource_dir = resource_dir
        self._worker: _GenerateWorker | None = None
        self._force_quit = False
        self._accepted = False  # 生成成功で accept 済み（成功時の closeEvent で誤って即終了しない）
        # プログレスの「見かけの停滞」対策: 実進捗(_target)へ向け表示(_disp)を毎 tick わずかに
        # 前進させ、実値より少し先(+マージン)まで滑らかに動かす（単調 op の無更新区間でも止めない）。
        self._disp = 0.0
        self._target = 0.0
        self._stall = 0
        self._creep = QTimer(self)
        self._creep.setInterval(80)
        self._creep.timeout.connect(self._tick)
        self._arena_dir = ""
        self._folder_valid = False
        self._arena_running = False
        # 初期言語: 保存済み ui_language → OS 言語に一致するもの → 英語（対象外時の既定）。
        self._lang = self._initial_lang()
        self._strings = self._load_setup(self._lang)
        if not self._strings:  # 読込失敗（パス不正等）の診断用。通常は発生しない。
            import logging
            logging.getLogger("RTESArenaAssist").warning(
                "first_run_wizard: setup.json 読込0件 resource=%r lang=%s",
                resource_dir, self._lang)
        self.setModal(True)
        self.setMinimumWidth(580)
        self._build_ui()
        self._retranslate()
        self._refresh_arena()  # 起動中 Arena を初回検出

    # ---- 言語ロード（グローバル i18n 非依存・setup.json 直読み＝frozen で堅牢） ----
    _LANGS = ("ja", "en", "es")

    def _initial_lang(self) -> str:
        saved = (settings.get("ui_language") or "").lower()
        if saved in self._LANGS:
            return saved
        import locale
        try:
            loc = (locale.getdefaultlocale()[0] or "")
        except Exception:  # noqa: BLE001
            loc = ""
        code = (loc.split("_")[0].split("-")[0] or "").lower()
        return code if code in self._LANGS else "en"

    def _load_setup(self, lang: str) -> dict:
        """setup.json を直接読む（指定言語→en フォールバック）。生キー表示を防ぐ。

        公開版は i18n を _internal に置かず exe 内 seed から読む。disk
        （_resource_dir）を優先し、無ければ app_resources（seed）へフォールバックする。
        """
        import json
        out: dict = {}
        for L in (lang, "en"):
            text = None
            p = os.path.join(self._resource_dir, "i18n", L, "setup.json")
            try:
                with open(p, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                try:
                    import app_resources
                    text = app_resources.read_text(f"i18n/{L}/setup.json")
                except Exception:  # noqa: BLE001 - seed 不在等は None
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

    # ---- 構築 ----
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
        self._lang_title.setStyleSheet("font-weight:bold;font-size:14px;")
        self._lang_prompt = QLabel()
        self._lang_prompt.setWordWrap(True)
        self._lang_combo = QComboBox()
        # 言語名は各言語の自称で固定表示。システム項目は出さず、OS 言語に一致するものを選択。
        self._lang_combo.addItem("日本語", "ja")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Español", "es")
        idx = max(0, self._lang_combo.findData(self._lang))
        self._lang_combo.setCurrentIndex(idx)
        # 初期 index 設定後に接続（構築時の誤発火を避ける）。変更で即時に画面へ反映。
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
        self._arena_title.setStyleSheet("font-weight:bold;font-size:14px;")
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
        # 「あとで設定する」ボタンは廃止: 実体は単に終了で、右上の × と重複し、本体へ
        # スキップできるかのように誤解させていた点を是正する。
        # セットアップ未完了で抜けるのは × のみとする（完了まで本体非表示の要件は不変）。
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

    # ---- 文言適用（self._t＝setup.json 直読み・生キー表示しない） ----
    def _retranslate(self) -> None:
        self.setWindowTitle(self._t("setup.window_title"))
        self._lang_title.setText(self._t("setup.lang.title"))
        self._lang_prompt.setText(self._t("setup.lang.prompt"))
        self._lang_next.setText(self._t("setup.btn.next"))
        self._arena_title.setText(self._t("setup.arena.title"))
        self._arena_intro.setText(self._t("setup.arena.intro"))
        self._folder_label.setText(self._t("setup.arena.folder_label"))
        self._browse_btn.setText(self._t("setup.arena.browse"))
        self._refresh_btn.setText(self._t("setup.arena.refresh"))
        self._arena_back.setText(self._t("setup.btn.back"))
        self._gen_btn.setText(self._t("setup.btn.generate"))
        self._update_arena_status()

    # ---- 言語ページ ----
    def _on_lang_changed(self, _idx: int) -> None:
        """コンボで選んだ言語を即座に適用し、その場で全文言を切替える。"""
        code = self._lang_combo.currentData() or "en"
        self._lang = code
        self._strings = self._load_setup(code)   # 文言を再ロード（自己完結）
        # 本体アプリ用にグローバル ui_language も更新（best-effort・ウィザード表示は _t で独立）。
        try:
            settings.set_val("ui_language", code)
            i18n.init(self._resource_dir, code)
        except Exception:  # noqa: BLE001
            pass
        self._retranslate()

    def _on_lang_next(self) -> None:
        # 言語は _on_lang_changed で適用済み。Arena ページへ。
        self._stack.setCurrentIndex(1)
        self._refresh_arena()

    # ---- Arena ページ ----
    def _refresh_arena(self) -> None:
        """起動中 Arena プロセスを再検出してフォルダ自動入力＋状態更新。"""
        detected = None
        try:
            detected = ald.detect_running_arena_dir()
        except Exception:  # noqa: BLE001
            detected = None
        self._arena_running = bool(detected)
        if detected:
            # 自動検出したフォルダを入力（手動編集済みで妥当ならそのまま尊重）。
            if not (self._path_edit.text().strip()
                    and ald.is_valid_arena_dir(self._path_edit.text().strip())):
                self._path_edit.setText(detected)
        self._update_arena_status()

    def _on_path_changed(self, text: str) -> None:
        path = text.strip()
        self._folder_valid = bool(path) and ald.is_valid_arena_dir(path)
        if self._folder_valid:
            self._arena_dir = path
        self._update_arena_status()

    def _update_arena_status(self) -> None:
        # 「Arena 起動が前提」: 未起動なら起動案内＋生成不可。
        if not self._arena_running:
            self._arena_status.setText(self._t("setup.arena.running_required"))
            if hasattr(self, "_gen_btn"):
                self._gen_btn.setEnabled(False)
            return
        if not self._folder_valid:
            self._arena_status.setText(self._t("setup.arena.invalid"))
            self._gen_btn.setEnabled(False)
            return
        self._arena_status.setText(
            self._t("setup.arena.detected") + "\n" + self._t("setup.arena.ok"))
        self._gen_btn.setEnabled(True)

    def _browse(self) -> None:
        start = self._path_edit.text().strip() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(
            self, self._t("setup.arena.folder_label"), start)
        if path:
            self._path_edit.setText(path)

    # ---- 生成ページ ----
    def _start_generate(self) -> None:
        if not (self._arena_running and self._folder_valid and self._arena_dir):
            return
        try:
            settings.set_val("save_dir", self._arena_dir)
        except Exception:  # noqa: BLE001
            pass
        self._stack.setCurrentIndex(2)
        self._disp = 0.0
        self._target = 0.0
        self._stall = 0
        self._bar.setValue(0)
        self._gen_status.setText(self._t("setup.gen.running"))
        self._worker = _GenerateWorker(self._arena_dir, self._user_dir, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._creep.start()  # 単調 op の無更新区間でもバーを動かし続ける

    def _tick(self) -> None:
        """実進捗の更新が来ない区間でも表示を少しずつ前進させる（停滞に見せない）。

        上限＝実値＋マージン。無更新が続くほど上限を緩やかに引き上げ、長い単調 op
        （メモリ署名探索等）でも完全停止しないようにする（最大 0.985・100%手前）。
        """
        self._stall += 1
        ceil = min(0.985, self._target + 0.08 + min(0.12, self._stall * 0.0008))
        if self._disp < ceil:
            self._disp = min(ceil, self._disp + 0.0025)
            self._bar.setValue(int(self._disp * 100))

    def _on_progress(self, frac: float, label: str) -> None:
        # 実進捗が来たら即反映（後退はしない）。バーの実描画は creep tick と共有。
        f = max(0.0, min(1.0, frac))
        self._stall = 0  # 実更新が来たので停滞カウンタをリセット
        self._target = max(self._target, f)
        self._disp = max(self._disp, f)
        self._bar.setValue(int(self._disp * 100))
        self._prog_label.setText(label)

    def _on_done(self, pack_path: str) -> None:
        self._creep.stop()
        self._accepted = True  # 成功確定。以後の closeEvent で即終了させない。
        self._disp = self._target = 1.0
        self._bar.setValue(100)
        self._gen_status.setText(self._t("setup.gen.done"))
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._creep.stop()
        m = self._t("setup.arena.invalid") if msg == "INVALID_ARENA" else msg
        self._gen_status.setText(self._t("setup.gen.failed", msg=m))
        self._stack.setCurrentIndex(1)  # Arena ページへ戻して再試行

    # ---- 終了処理（キャンセル時にワーカーを確実に止める） ----
    def _stop_worker(self) -> None:
        """生成ワーカーを止める。生成中キャンセルなら確実なプロセス終了を予約する。

        まず協調キャンセル（フェーズ境界/テーブル走査で中断）を要求し短時間待つ。止まら
        なければ terminate（書込は .tmp への原子的書込＝本番パック無傷・中途 .tmp は次回掃除）。
        **生成が走っていた場合は `_force_quit` を立て、reject/closeEvent で確実に即終了させる**
        （terminate でも OS スレッドが syscall で止まり切らずプロセスが居座り、ミューテックスを
        握ったまま「閉じても再起動できず後でまとめて起動」になる不具合を断つ）。
        """
        self._creep.stop()
        w = self._worker
        # 成功(accept)後の closeEvent では止めない（完走済みワーカーを誤って強制終了しない）。
        if not self._accepted and w is not None and w.isRunning():
            self._force_quit = True  # 生成中キャンセル＝アプリ終了意図。確実に解放する。
            w.cancel()
            if not w.wait(1200):
                w.terminate()
                w.wait(1500)
        self._worker = None

    def _hard_exit_if_needed(self) -> None:
        """生成中キャンセル時はミューテックスを解放し即時プロセス終了する（再起動を保証）。"""
        if self._accepted or not self._force_quit:
            return
        try:
            import single_instance
            single_instance.release()
        except Exception:  # noqa: BLE001
            pass
        import os
        os._exit(0)  # スレッド/Qt の後始末を待たず即終了（.tmp 原子書込で本番パック無傷）

    def reject(self) -> None:  # noqa: D401 - QDialog override
        self._stop_worker()
        self._hard_exit_if_needed()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: D401 - QWidget override
        # × ボタン/ウィンドウクローズでも確実にワーカーを止め、生成中なら即終了する。
        self._stop_worker()
        self._hard_exit_if_needed()
        super().closeEvent(event)

    @property
    def arena_dir(self) -> str:
        return self._arena_dir


def needs_first_run(user_dir: str) -> bool:
    """初回ウィザードを出すべきか（Arena フォルダ未設定 or localpack 未生成）。

    生成対象は `RTESArenaAssist.localpack`（唯一の Arena 由来 local provider）。
    """
    try:
        arena_dir = settings.get("save_dir") or settings.get("arena_dir") or ""
    except Exception:  # noqa: BLE001
        arena_dir = ""
    if not arena_dir or not ald.is_valid_arena_dir(arena_dir):
        return True
    return not os.path.isfile(ald.v2_localpack_path(user_dir))
