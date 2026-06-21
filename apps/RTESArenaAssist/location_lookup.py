"""location_lookup.py — 静的地名（州・都市・固有ダンジョン名）の原文→訳ルックアップ。

翻訳切替コア（i18n_helper）の location カテゴリをバックエンドに、州名・都市名・
メインクエストの固有ダンジョン名など「静的な地名」の現在言語訳を返す。

生成名（tavern / temple / equipment store の分解合成名）は
`dynamic_place_lookup` の管轄であり、本モジュールは扱わない。

公開版対応: 従来は `i18n.value("location", en)` で `_original` 逆引きしていたが、
公開版は `_original` 非同梱のため逆引きできなかった。location の app_id は原文の決定論
スラッグ（`location.<slug(原文)>.0`）であることを実データで確認（339/339 一致）したため、
**ライブ英語からスラッグを導出し app_id を直引き**する direct-id 解決へ改める。これにより
`_original` 不要で公開版でも解決でき、原文は同梱しない（スラッグは runtime で利用者の
ライブテキストから生成・公開物に原文を持たない）。dev でも結果は従来と同一
（en→id 索引が決定論スラッグと一致するため）。

API:
  lookup(en: str) -> str | None   # 未登録は None
"""

from __future__ import annotations

import re

import i18n_helper as i18n

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(en: str) -> str:
    """原文地名を app_id スラッグへ決定論変換する（生成器のキー規則と一致）。

    手順: 前後空白除去 → 小文字化 → アポストロフィ除去（"Selene's"→"selenes"）→
    英数字以外を `_` へ畳む → 前後の `_` を除去。location 全 339 件で
    `location.<slug>.0` が現 app_id と一致することを検証済み。
    """
    s = en.strip().lower().replace("'", "")
    return _NON_ALNUM.sub("_", s).strip("_")


def lookup(en: str) -> str | None:
    """en（原文地名）の現在言語訳を返す。未登録時は None。

    スラッグ直引き（`_original` 不要・公開版対応）。未登録のスラッグは i18n.text_opt が
    None を返す（言語/原文フォールバックは text_opt が従来の value() と同一に処理）。
    """
    if not en:
        return None
    return i18n.text_opt(f"location.{_slug(en.strip())}.0")
