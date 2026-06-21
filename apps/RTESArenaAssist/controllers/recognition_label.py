"""recognition_label.py — 接続バー（画面認識）の表示名生成 pure helper。

画面名は安定化済み `_screen_id_stable`（bounce / bonus hold / char page settle 後）
から一元的に生成する。raw 検出名は安定化前の値なので、stable が raw と変わった
場合は stable id の画面名を使う。

window / analyzer の時系列状態に触れない pure helper にして単体テストできる
ようにする（map_safe_coord / char_screen_page と同方針）。
"""
from __future__ import annotations

from typing import Callable


_FACILITY_PREFIX_KEYS: tuple[tuple[str, str], ...] = (
    ("TAVERN", "recognition.facility_tavern"),
    ("TEMPLE", "recognition.facility_temple"),
    ("EQUIPMENT", "recognition.facility_equipment"),
    ("ARMORS", "recognition.facility_equipment"),
    ("EQUIP", "recognition.facility_equipment"),
    ("MAGES", "recognition.facility_mages"),
    ("MAGE", "recognition.facility_mages"),
    # フィールド施設（C3 配下 L3）。TOWNPAL/VILPAL より前に置く必要は
    # ないが、WCRYPT/TOWER は他 prefix と重ならない。
    ("WCRYPT", "recognition.facility_crypt"),
    ("TOWER", "recognition.facility_tower"),
    # フィールドの家（door→MIF prefix は "BS"）。
    ("BS", "recognition.facility_house"),
    ("PALACE", "recognition.facility_palace"),
    ("TOWNPAL", "recognition.facility_palace"),
    ("VILPAL", "recognition.facility_palace"),
)

_SESSION_FACILITY_KEYS = {
    "tavern": "recognition.facility_tavern",
    "temple": "recognition.facility_temple",
    "equipment": "recognition.facility_equipment",
    "mages_guild": "recognition.facility_mages",
    "palace": "recognition.facility_palace",
}


def resolve_stable_screen_name(stable_id: str, raw_id: str, raw_name: str,
                               tr: Callable[[str], str]) -> str:
    """接続バー用の画面名を、安定化済み画面 ID から返す。

    Args:
      stable_id: 安定化済み画面 ID（bounce / bonus / settle 後の確定値）。
      raw_id:    detect_screen 直後の生画面 ID。
      raw_name:  生画面名（game_screen の area suffix / loading 等の加工済み）。
      tr:        i18n 翻訳関数（"screen.<id>" を渡す）。

    Returns:
      stable_id == raw_id のときは raw_name（加工済みの生名）を使う。
      異なるときは stable_id に対応する画面名を tr から取得する。
    """
    if stable_id == raw_id:
        return raw_name
    return tr(f"screen.{stable_id}")


def format_recognition_label(screen_name: str, indicator: str,
                             facility_label: str, conv_label: str) -> str:
    """接続バー文字列を合成する。

    屋内施設認識時（facility_label 有り）は screen_name を抑止し、
    indicator + facility + conv のみを表示する。屋外 / 施設未認識時は
    indicator + screen_name + conv を表示する。
    """
    if facility_label:
        return (f"{indicator}{facility_label}{conv_label}"
                if indicator else f"{facility_label}{conv_label}")
    return (f"{indicator} {screen_name}{conv_label}"
            if indicator else f"{screen_name}{conv_label}")


# 宿屋店主会話の L4 サブ画面 → 接続バー表示用 i18n key。
# 接続バーに「いま実際に翻訳パネルへ描画している経路 (= panel_owner)」を出して、
# 人間が実画面・翻訳表示と突き合わせられるようにするためのデバッグ表示。
# 方針: 実描画 owner を最優先にする (= 翻訳表示と一致させる)。img 名は
#       メニューでも NEWPOP/FACES/YESNO と揺れて識別に使えないため owner 基準。
#   - active_template owner は surface kind で確認/結果/入力を細分する。
#   - shop_buy owner は酒一覧/部屋一覧の両方で使うため shop_kind で振り分ける。
# owner がいずれの tavern 描画経路でもなければ「サブ状態なし」(= 探索中など) と
# みなして "" を返す (= 接続バーには何も足さない)。
_TAVERN_SURFACE_SUB_KEYS = {
    "tavern_stay_days": "recognition.tavern_sub_stay_days",
    "tavern_sneak_confirm": "recognition.tavern_sub_sneak_confirm",
    "tavern_sneak_result": "recognition.tavern_sub_sneak_result",
    "tavern_room_contract": "recognition.tavern_sub_room_contract",
    "tavern_cost_show": "recognition.tavern_sub_cost_show",
    "tavern_cost_confirm": "recognition.tavern_sub_cost_confirm",
}


def tavern_sub_state_key(
    shop_kind: str,
    active_template_surface: str,
    panel_owner: str,
    img_name: str = "",
    negot_counter_active: bool = False,
) -> str:
    """宿屋店主会話のサブ画面を接続バー表示用 i18n key に分類する pure helper。

    実描画 owner (panel_owner) を最優先にして、いま翻訳パネルへ出ている内容と
    一致するサブ状態 key を返す。どの tavern 描画経路でもなければ "" を返す
    (= 探索中等。接続バーにはサブ状態を足さない)。

    宿泊交渉 (= owner=negotiation) は img で細分する (実機ログ観測):
      - NEGOTBUT.IMG = 金額提示 (ACCEPT/COUNTER/REJECT)
      - YESNO.IMG    = 最終確認 (YES/NO/CANCEL)
    対案入力 (= 'Enter counter offer :') は surface=negotiation_counter で判定。
    """
    owner = panel_owner or ""
    img = (img_name or "").upper()
    surface = active_template_surface or ""

    # 対案入力 (A600 'Enter counter offer :') は owner に依らず最優先判定する。
    # negotiation_module が対案プロンプトを描画中 (= negot_counter_active) か、
    # active_template surface が negotiation_counter のどちらかで判定する。
    if negot_counter_active or surface == "negotiation_counter":
        return "recognition.tavern_sub_amount_counter"
    if owner == "active_template":
        # 確認 / 結果 / 入力は surface kind で細分。surface 不明なら無表示。
        return _TAVERN_SURFACE_SUB_KEYS.get(surface, "")
    if owner == "shop_buy":
        # 同じ owner で酒一覧と部屋一覧を共用するため shop_kind で振り分け。
        if shop_kind == "shop_rooms":
            return "recognition.tavern_sub_rooms"
        return "recognition.tavern_sub_drinks"
    if owner == "shop_menu":
        return "recognition.tavern_sub_menu"
    if owner in ("shop_rumor_type", "tavern_rumor_type"):
        return "recognition.tavern_sub_rumor_type"
    if owner == "negotiation":
        # 宿泊交渉: img で金額提示 / 最終確認を分ける。
        if img == "YESNO.IMG":
            return "recognition.tavern_sub_final_confirm"
        return "recognition.tavern_sub_amount_present"
    if owner == "npc_dialog":
        return "recognition.tavern_sub_response"
    return ""


# 神殿神官会話の L4 サブ画面 → 接続バー表示用 i18n key。
# 宿屋と同じく「実際に翻訳パネルへ描画している owner」を最優先し、画面表示と
# 接続バーの認識状態を突き合わせやすくする。
_TEMPLE_SURFACE_SUB_KEYS = {
    "temple_donate_amount": "recognition.temple_sub_donate_amount",
    "tavern_cost_show": "recognition.temple_sub_cost_show",
    "tavern_cost_confirm": "recognition.temple_sub_cost_confirm",
}


def temple_sub_state_key(
    active_template_surface: str,
    panel_owner: str,
    img_name: str = "",
    current_text: str = "",
) -> str:
    """神殿神官会話のサブ画面を接続バー表示用 i18n key に分類する。

    実描画 owner (panel_owner) を最優先にし、`temple_priest_reply` だけは
    表示本文から祝福/治療結果を分ける。owner が神殿描画経路でなければ ""
    を返す (= 接続バーにはサブ状態を足さない)。
    """
    owner = panel_owner or ""
    img = (img_name or "").upper()
    surface = active_template_surface or ""
    text = " ".join((current_text or "").split())

    if owner == "temple_menu":
        return "recognition.temple_sub_menu"
    if owner == "temple_prompt":
        return "recognition.temple_sub_donate_amount"
    if owner == "temple_cost":
        if surface == "tavern_cost_confirm" or img == "YESNO.IMG":
            return "recognition.temple_sub_cost_confirm"
        return "recognition.temple_sub_cost_show"
    if owner == "temple_priest_reply":
        if text.startswith("Receive our blessings"):
            return "recognition.temple_sub_bless_result"
        if text.startswith("Curing "):
            return "recognition.temple_sub_curing"
        if "thou art healed" in text or "is in perfect condition" in text:
            return "recognition.temple_sub_heal_result"
        if text.startswith("We humbly beg your forgivness"):
            return "recognition.temple_sub_cure_result"
        return "recognition.temple_sub_response"
    if owner == "active_template":
        return _TEMPLE_SURFACE_SUB_KEYS.get(surface, "")
    return ""


def equipment_sub_state_key(
    active_template_surface: str,
    panel_owner: str,
    img_name: str = "",
    negot_counter_active: bool = False,
) -> str:
    """武具店店主会話のサブ画面を接続バー表示用 i18n key に分類する。"""
    owner = panel_owner or ""
    img = (img_name or "").upper()
    surface = active_template_surface or ""

    if negot_counter_active or surface == "negotiation_counter":
        return "recognition.equipment_sub_amount_counter"
    if owner == "equipment_menu":
        return "recognition.equipment_sub_menu"
    if owner == "equipment_list":
        return "recognition.equipment_sub_list"
    if owner == "equipment_negotiation":
        if img == "YESNO.IMG":
            return "recognition.equipment_sub_final_confirm"
        return "recognition.equipment_sub_amount_present"
    if owner == "equipment_reply":
        return "recognition.equipment_sub_response"
    return ""


def mages_sub_state_key(
        panel_owner: str,
        img_name: str = "",
        list_title: str = "") -> str:
    """魔術師ギルド店主会話のサブ画面を接続バー表示用 i18n key に分類する。

    武具店 (equipment_sub_state_key) と同型を魔術師ギルド分離内で実装したもの。
    """
    owner = panel_owner or ""
    if owner == "mages_menu":
        return "recognition.mages_sub_menu"
    if owner == "mages_list":
        title = (list_title or "").strip()
        if title == "Targets":
            return "recognition.mages_sub_spellmaker_targets"
        if title == "Effects":
            return "recognition.mages_sub_spellmaker_effects"
        if title == "Effect Options":
            return "recognition.mages_sub_spellmaker_effect_options"
        if title == "Spells":
            return "recognition.mages_sub_buy_spells"
        if title == "Potions":
            return "recognition.mages_sub_buy_potions"
        if title == "Magic Items":
            return "recognition.mages_sub_magic_items"
        if title == "Inventory":
            return "recognition.mages_sub_inventory"
        return "recognition.mages_sub_list"
    if owner == "mages_spellmaker":
        return "recognition.mages_sub_spellmaker"
    if owner == "mages_effect_menu":
        return "recognition.mages_sub_spellmaker_edit_effects"
    if owner == "mages_spelldetail":
        return "recognition.mages_sub_spelldetail"
    if owner == "mages_prompt":
        return "recognition.mages_sub_prompt"
    if owner == "mages_confirm":
        return "recognition.mages_sub_confirm"
    if owner == "mages_negotiation":
        return "recognition.mages_sub_negotiation"
    if owner == "mages_reply":
        return "recognition.mages_sub_response"
    return ""


def known_facility_kind(*hints: str) -> str:
    """ヒント（active session 名 / 店主種別 等）から既知の施設種別名を返す。

    `_SESSION_FACILITY_KEYS` に載る種別（tavern/temple/equipment/mages_guild/
    palace）を最初に見つけた順で返す。該当なしは ""。L3 施設識別の永続化
    （途中接続で MIF が無い場合）に使う。
    """
    for h in hints:
        if (h or "") in _SESSION_FACILITY_KEYS:
            return h
    return ""


def facility_recognition_key(
    interior_mif_name: str,
    in_interior: bool,
    *,
    active_session_name: str = "",
    shop_owner_kind: str = "",
    persisted_facility_kind: str = "",
) -> str:
    """屋内施設の接続バー表示に使う i18n key を返す。

    中途接続では CityViewer 由来の `interior_mif_name` がまだ無い場合が
    あるため、active session / shop owner から分かる施設種別を補助信号に
    する。さらに `persisted_facility_kind` は L4 会話中に一度確定した施設種別を
    L3 に保持したもので、L4 を抜けた後も（屋内に居る間は）施設識別を維持する
    （階層化: L3 で確定した識別が L4 離脱で失われないようにする）。屋内である
    こと自体が分かる場合は最低限「施設」を返す。
    """
    if not in_interior:
        return ""
    u = (interior_mif_name or "").upper()
    for prefix, key in _FACILITY_PREFIX_KEYS:
        if u.startswith(prefix):
            return key
    for hint in (active_session_name, shop_owner_kind, persisted_facility_kind):
        key = _SESSION_FACILITY_KEYS.get(hint or "")
        if key:
            return key
    return "recognition.facility_other"


__all__ = [
    "resolve_stable_screen_name",
    "format_recognition_label",
    "equipment_sub_state_key",
    "mages_sub_state_key",
    "facility_recognition_key",
    "known_facility_kind",
    "temple_sub_state_key",
    "tavern_sub_state_key",
]
