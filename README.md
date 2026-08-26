# RTESArenaAssist

*The Elder Scrolls: Arena*（DOSBox 上で動作する Steam 版）をプレイ中に、別ウィンドウで
ゲーム内テキストの翻訳・マップ・ステータス等をリアルタイム表示する補助ツールです。

**ゲームの実行ファイルやデータファイルを書き換えません。**インストール先へ手を入れない外部
ツールで、DOSBox のメモリを読み取って表示します。

- バージョン: **v0.1.27（アルファ版）**
- 動作環境: Windows
- 対応言語: 日本語 / English / Español / Deutsch / Français / Italiano / Русский

## 主な機能

- **翻訳**: 会話・メッセージ・メニューなどのゲーム内テキストを翻訳して表示
- **マップ**: 探索済みの範囲、現在地、階層を表示
- **ステータス**: 能力値・装備・習得呪文の表示
- **ジャーナル / ログ / 辞書 / マニュアル**: クエスト記録、表示した翻訳の履歴、用語辞書、操作説明
- **読み上げ**: 表示した翻訳の音声読み上げ
- **セーブ**: セーブデータのバックアップと復元
- 設定から任意で有効にできる補助機能（既定は OFF）として、ゲーム内の値やマップ表示を
  変更する項目があります

## アルファ版について

まだアルファ版です。ゲームをクリアするまでの全体を確認できておらず、翻訳の抜けや表示の
不具合が残っています。遊びながら気づいた点は Issues か
[Nexus Mods のページ](https://www.nexusmods.com/tesarena/mods/94)でお知らせください。
日本語・英語どちらでも構いません。

## 導入

1. [Releases](https://github.com/rrryutaro/RTESArenaAssist/releases) または
   [Nexus Mods](https://www.nexusmods.com/tesarena/mods/94) から
   `RTESArenaAssist.exe` をダウンロードします（どちらも同じファイルです）。
2. Arena（DOSBox）を先に起動します。
3. `RTESArenaAssist.exe` を実行します。初回は表示言語の選択と、翻訳データの生成が行われます。
   生成には数分かかることがあります。
4. 生成が終わると本体ウィンドウが開き、Arena に接続して表示を開始します。

詳しい使い方は [基本操作ガイド](docs/assist_basic_guide.md)、設定項目は
[設定ダイアログ詳細ガイド](docs/assist_settings_dialog.md) を参照してください。

### ウイルス対策ソフトの誤検知について

配布している実行ファイルは PyInstaller で 1 ファイルにまとめたものです。この形式は
ウイルス対策ソフトに誤検知されることがあります。誤検知が起きた場合は、除外設定を
行うか、後述の「ソースから実行する」方法をお試しください。

## ゲームのデータについて

本ツールは **Arena のデータ・テキスト・画像を一切同梱していません。**
翻訳表示に必要なデータは、初回起動時にお使いの環境へインストールされている Arena から
読み出して生成します。そのため、Arena を別途入手しておく必要があります。

## ソースから実行する

```
pip install -r requirements-build-assist.txt
python apps/RTESArenaAssist/assist_main.py
```

同梱の `RTESArenaAssist-public.spec` で実行ファイルを再ビルドすることもできます。

## ライセンス

本ツールは MIT License です（[LICENSE](LICENSE)）。
実行ファイルに同梱している第三者ソフトウェアの表記は
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) を参照してください。

## 免責

本ツールは非公式のファンメイドであり、ZeniMax Media Inc. および Bethesda Softworks LLC
とは一切関係がありません。The Elder Scrolls: Arena および関連する名称・意匠は各権利者に
帰属します。本ツールの利用によって生じたいかなる損害についても、作者は責任を負いません。
