# サードパーティ ライセンス表記

RTESArenaAssist 本体は MIT License です（[LICENSE](LICENSE)）。配布している実行ファイル
（`RTESArenaAssist.exe`）には以下の第三者ソフトウェアが同梱されています。それぞれの
ライセンス条件は各プロジェクトの配布物に含まれる原文が正となります。

| ソフトウェア | ライセンス | 配布元 |
|---|---|---|
| Qt / PySide6 | LGPL v3（Qt は商用ライセンスとのデュアルライセンス） | https://www.qt.io/ / https://pypi.org/project/PySide6/ |
| NumPy | BSD 3-Clause | https://numpy.org/ |
| Pillow | MIT-CMU | https://python-pillow.org/ |
| pywin32 | PSF-2.0 系 | https://github.com/mhammond/pywin32 |
| CPython ランタイム | PSF License | https://www.python.org/ |
| PyInstaller ブートローダ | GPL v2 以降（ブートローダには例外条項があり、生成した実行ファイルを任意のライセンスで配布できます） | https://pyinstaller.org/ |

## Qt / PySide6（LGPL v3）について

本実行ファイルは Qt を LGPL v3 の条件で動的リンクして同梱しています。LGPL v3 の要求に従い、
以下を明示します。

- 利用者は、同梱されている Qt を**改変版の Qt に差し替えて本アプリケーションを再リンク**できます。
  本アプリケーションは Python + PySide6 で実装されており、ソースコードは
  https://github.com/rrryutaro/RTESArenaAssist で公開しています。取得したソースを
  任意の PySide6 を導入した Python 環境で実行すること、および同梱の
  `RTESArenaAssist-public.spec` で再ビルドすることで、差し替えが可能です。
- Qt 本体および PySide6 のソースコードは、上記の配布元から取得できます。
- ライセンス原文（LGPL v3）は https://www.gnu.org/licenses/lgpl-3.0.html を参照してください。

## The Elder Scrolls: Arena について

本ツールはゲームの実行ファイルやデータファイルを書き換えません。また **Arena のデータ・
テキスト・画像を同梱していません**。
翻訳表示に必要なデータは、利用者の環境にインストールされた Arena から実行時に読み出して
生成します。The Elder Scrolls: Arena および関連する名称・意匠は ZeniMax Media Inc. および
Bethesda Softworks LLC に帰属します。本ツールは非公式のファンメイドであり、これらの企業とは
一切関係がありません。
