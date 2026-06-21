"""normal_play/shop_render_common.py — 店主/施設メニュー描画の共通レイヤ。

施設会話 (宿屋 / 神殿 / 装備品店 / 魔術師ギルド) のメニュー表示テキスト生成を
**副作用なしの pure 関数**として 1 か所に集約する (共通描画レイヤ)。

副作用なし契約:
- `panel_owner` / window 状態を一切書き換えない。
- `UiRouter` 等の UI を直接叩かない。
- memory も読まない (= 呼出側が読み取り済みの値だけを受け取る)。
- 戻り値は表示テキスト 4 種 (タブ EN/JA・パネル EN/JA) のみ。

どの owner で `UiRouter.update_translation()` を呼ぶかは、施設ごとの描画
オーナー (例: `tavern_render_module`) が決める。本モジュールは「何を表示するか」
だけを返し、「いつ・どの owner で描くか」には関与しない。
"""
from __future__ import annotations

from typing import Sequence


def build_menu_display(
    menu_tr: Sequence[tuple[str, str]],
    menu_hotkeys: Sequence[str],
    title_en: str,
    title_ja: str,
) -> tuple[str, str, str, str]:
    """店主/施設メニューの翻訳タブ・パネル表示テキストを生成する pure 関数。

    表示規約:
      - 翻訳タブ: タイトル + 空行 + 2 スペースインデント +
        `[<頭文字>]` 接頭辞付き選択肢。
      - パネル: タイトル + 空行 + 選択肢 (インデント・接頭辞なし)。
      - タイトルが空の場合はタイトル行・空行を省略する。

    引数:
      menu_tr: 各メニュー項目の (英語, 日本語) ペア。日本語が空なら英語を表示。
      menu_hotkeys: 各項目のホットキー文字 (頭文字)。menu_tr と同順・同数想定。
      title_en / title_ja: メニュータイトル (空可)。

    戻り値: (tab_en, tab_ja, panel_en, panel_ja)
    """
    tab_en_lines: list[str] = []
    tab_ja_lines: list[str] = []
    panel_en_lines: list[str] = []
    panel_ja_lines: list[str] = []

    if title_en:
        tab_en_lines.extend([title_en, ""])
        tab_ja_lines.extend([title_ja, ""])
        panel_en_lines.extend([title_en, ""])
        panel_ja_lines.extend([title_ja, ""])

    for _i, (_en, _ja) in enumerate(menu_tr):
        _hk = menu_hotkeys[_i] if _i < len(menu_hotkeys) else ""
        _ja_disp = _ja or _en
        _prefix = f"[{_hk}] " if _hk else ""
        tab_en_lines.append(f"  {_prefix}{_en}")
        tab_ja_lines.append(f"  {_prefix}{_ja_disp}")
        panel_en_lines.append(_en)
        panel_ja_lines.append(_ja_disp)

    return (
        "\n".join(tab_en_lines),
        "\n".join(tab_ja_lines),
        "\n".join(panel_en_lines),
        "\n".join(panel_ja_lines),
    )


__all__ = ["build_menu_display"]
