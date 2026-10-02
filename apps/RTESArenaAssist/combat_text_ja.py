from __future__ import annotations
from string import Formatter
import i18n_helper as i18n
DEFAULT_COMBAT_MESSAGE_TEMPLATES = {'encounter': '{name}が あらわれた！', 'enemy_damage': '{name}に {damage}の ダメージ！', 'player_damage': '{damage}の ダメージを うけた！', 'defeated': '{name}を たおした！', 'experience': '{xp}ポイントの けいけんちを かくとく！'}
COMBAT_MESSAGE_TEMPLATE_SETTINGS = {kind: f'combat_message_template_{kind}' for kind in DEFAULT_COMBAT_MESSAGE_TEMPLATES}
COMBAT_MESSAGE_TEMPLATE_FIELDS = {'encounter': frozenset(('name', 'hp', 'max_hp', 'level')), 'enemy_damage': frozenset(('name', 'damage', 'hp', 'max_hp', 'level')), 'player_damage': frozenset(('damage', 'hp', 'max_hp')), 'defeated': frozenset(('name', 'damage', 'xp', 'level')), 'experience': frozenset(('xp',))}
_CREATURE_TYPES = (('rat', 'ラット'), ('goblin', 'ゴブリン'), ('lizard_man', 'リザードマン'), ('wolf', 'ウルフ'), ('snow_wolf', 'スノーウルフ'), ('orc', 'オーク'), ('skeleton', 'スケルトン'), ('minotaur', 'ミノタウロス'), ('spider', 'スパイダー'), ('ghoul', 'グール'), ('hell_hound', 'ヘルハウンド'), ('ghost', 'ゴースト'), ('zombie', 'ゾンビ'), ('troll', 'トロール'), ('wraith', 'レイス'), ('homunculus', 'ホムンクルス'), ('ice_golem', 'アイスゴーレム'), ('stone_golem', 'ストーンゴーレム'), ('iron_golem', 'アイアンゴーレム'), ('fire_daemon', 'ファイアーデーモン'), ('medusa', 'メデューサ'), ('vampire', '吸血鬼'), ('lich', 'リッチ'))
_HUMAN_ENEMY_NAMES_JA = ('魔法使い', '魔法剣士', '戦闘魔術師', '妖術師', '治療師', 'ナイトブレイド', '吟遊詩人', '強盗', 'ならず者', '軽業師', '盗賊', '暗殺者', '修道士', '弓兵', 'レンジャー', '野蛮人', '戦士', '騎士')

def enemy_name_from_item(item_index: int) -> str | None:
    item_index = int(item_index)
    if 32 <= item_index <= 54:
        return _CREATURE_TYPES[item_index - 32][1]
    if item_index == 73:
        return 'ジャガー・サーン'
    if 55 <= item_index <= 72:
        return _HUMAN_ENEMY_NAMES_JA[item_index - 55]
    return None

def localized_enemy_name_from_item(item_index: int) -> str | None:
    if i18n.text_opt('combat.title') is None or i18n.current_lang() == 'ja':
        return enemy_name_from_item(item_index)
    item_index = int(item_index)
    if 32 <= item_index <= 54:
        slug = _CREATURE_TYPES[item_index - 32][0]
        return i18n.text_opt(f'monsters.{slug}.0') or slug.replace('_', ' ').title()
    if 55 <= item_index <= 72:
        return i18n.text_opt(f'classes.{item_index - 55}.0')
    if item_index == 73:
        return 'Jagar Tharn'
    return None

def english_enemy_name_from_item(item_index: int) -> str | None:
    item_index = int(item_index)
    if 32 <= item_index <= 54:
        return _CREATURE_TYPES[item_index - 32][0].replace('_', ' ').title()
    if item_index == 73:
        return 'Jagar Tharn'
    return None
_TEXT = {'settings.tab_combat': '戦闘情報', 'settings.group_arena_screen': 'Arena画面', 'settings.group_translate_tab': '翻訳タブ', 'settings.group_translate_panel': '翻訳パネル', 'settings.group_combat_common': '共通設定', 'settings.combat_dosbox': '戦闘情報を表示する', 'settings.combat_dosbox_note': '直近攻撃した敵を画面上部、他の敵を右側に表示します。', 'settings.combat_arena_xp_seconds': '獲得経験値の表示時間', 'settings.combat_tab_mode': '表示方法', 'settings.combat_tab_mode_none': '表示なし（通常表示を維持）', 'settings.combat_tab_mode_both': '戦闘情報と通常表示の両方', 'settings.combat_tab_mode_full': '戦闘情報を全面表示', 'settings.combat_tab_format': '戦闘情報の形式', 'settings.combat_tab_format_text': '文字情報', 'settings.combat_tab_format_meters': '敵のメーター表示', 'settings.combat_panel': '戦闘メッセージを表示する', 'settings.combat_panel_history': '直近履歴の表示件数', 'settings.combat_log': '戦闘ログを保存する', 'settings.combat_tts': '新しい戦闘メッセージを読み上げる', 'settings.combat_enemy_identifier': '同名の敵に識別子を付ける', 'settings.combat_enemy_identifier_style': '識別子の種類', 'settings.combat_enemy_identifier_alphabet': 'アルファベット（A、B…）', 'settings.combat_enemy_identifier_number': '数字（1、2…）', 'settings.group_combat_messages': '戦闘メッセージのテンプレート', 'settings.combat_template_encounter': '会敵', 'settings.combat_template_enemy_damage': '敵へのダメージ', 'settings.combat_template_player_damage': '自分へのダメージ', 'settings.combat_template_defeated': '撃破', 'settings.combat_template_experience': '経験値', 'settings.combat_template_note': '{name}=敵名、{damage}=ダメージ、{hp}=残りHP、{max_hp}=最大HP、{level}=レベル、{xp}=経験値。空欄または使えない置換指定は、既定の文へ戻します。', 'settings.combat_info_note': '翻訳パネルでは、既存のメッセージ・会話・一覧を戦闘情報より優先します。戦闘メッセージは設定件数の直近履歴として表示します。', 'combat.title': '戦闘', 'combat.result': '戦闘結果', 'combat.enemy': '敵', 'combat.enemy_number': '敵{n}', 'combat.player_hp': '自分の体力', 'combat.damage_received': '受けたダメージ', 'combat.defeated': '撃破', 'combat.c_encounter': '{name}と会敵  {hp}/{max_hp} HP', 'combat.c_damage_enemy': '{name}  -{damage} HP  {hp}/{max_hp}', 'combat.c_damage_player': '受けたダメージ  -{damage} HP  {hp}/{max_hp}', 'combat.c_defeated': '{name}を撃破  +{xp} XP', 'combat.c_defeated_no_xp': '{name}を撃破', 'combat.c_defeated_damage': '{name}  -{damage} HP  撃破  +{xp} XP', 'combat.c_defeated_damage_no_xp': '{name}  -{damage} HP  撃破', 'combat.c_experience': '経験値 +{xp}', 'combat.c3_encounter': '{name}と会敵した。', 'combat.c3_damage_enemy': '{name}に{damage}ダメージ。残り体力は{hp}。', 'combat.c3_damage_player': '{damage}ダメージを受けた。', 'combat.c3_defeated': '{name}を倒し、経験値{xp}を得た。', 'combat.c3_defeated_no_xp': '{name}を倒した。', 'combat.c3_experience': '経験値{xp}を得た。', 'combat.summary_defeated': '倒した敵：{names}', 'combat.summary_damage_dealt': '与えたダメージ：{value}', 'combat.summary_damage_received': '受けたダメージ：{value}', 'combat.summary_experience': '獲得経験値：+{value}', 'combat.hp': '体力', 'combat.stamina': '疲労', 'combat.spell_points': '呪文P', 'combat.experience_popup': '経験値  +{xp}', 'settings.group_spell_effect': 'Arena画面・持続魔法', 'settings.spell_effect_enabled': '画面左上に持続魔法を表示', 'settings.spell_effect_style': '表示方式', 'settings.spell_effect_style_A': 'A｜名前＋残り値', 'settings.spell_effect_style_B': 'B｜名前＋横メーター', 'settings.spell_effect_style_C': 'C｜アイコン＋横メーター', 'settings.spell_effect_style_D': 'D｜アイコン＋時計回りの暗転', 'settings.spell_effect_style_E': 'E｜アイコン＋名前＋残り値＋細メーター（推奨）', 'settings.spell_effect_style_F': 'F｜小型チップ', 'settings.spell_effect_time_unit': '時間型の更新', 'settings.spell_effect_rounds': 'ラウンド（従来）', 'settings.spell_effect_seconds': '秒（実測ペースによる概算・1秒ごと）', 'settings.spell_effect_note': '秒は初期値から概算し、連続するゲーム内ラウンドの実測間隔で補正します。シールドは残り防御量、筋力強化は上昇量です。途中接続など最大値が不明な時はメーターを省きます。', 'settings.seconds_suffix': ' 秒', 'settings.entries_suffix': ' 件', 'spell_effect.name.light': 'ライト', 'spell_effect.name.shield': 'シールド', 'spell_effect.name.strength': '筋力強化', 'spell_effect.name.fire': '火炎耐性', 'spell_effect.name.levitate': 'レビテート', 'spell_effect.remaining_points': '残り{value}点', 'spell_effect.active': '効果中', 'spell_effect.remaining_seconds': '約{value}秒', 'spell_effect.remaining_rounds': '残り{value}R'}

def text(key: str, **values) -> str:
    value = i18n.text_opt(key) or _TEXT[key]
    return value.format(**values) if values else value

def default_combat_template(kind: str) -> str:
    return i18n.text_opt(f'combat.template.{kind}') or DEFAULT_COMBAT_MESSAGE_TEMPLATES[kind]

def is_builtin_combat_template(kind: str, template: object) -> bool:
    if not isinstance(template, str) or not template:
        return True
    if template == DEFAULT_COMBAT_MESSAGE_TEMPLATES[kind]:
        return True
    key = f'combat.template.{kind}'
    return any((template == i18n.lang_value_in(key, lang) for lang in ('en', 'ja', 'es', 'de', 'fr', 'it', 'ru')))

def format_combat_message(kind: str, template: object, **values) -> str:
    default = default_combat_template(kind)
    candidate = default if is_builtin_combat_template(kind, template) else template
    try:
        for _literal, field_name, format_spec, conversion in Formatter().parse(candidate):
            if field_name is None:
                continue
            if field_name not in COMBAT_MESSAGE_TEMPLATE_FIELDS[kind] or format_spec or conversion:
                raise ValueError('unsupported combat message placeholder')
        return candidate.format(**values)
    except (KeyError, IndexError, ValueError):
        return default.format(**values)
__all__ = ['COMBAT_MESSAGE_TEMPLATE_FIELDS', 'COMBAT_MESSAGE_TEMPLATE_SETTINGS', 'DEFAULT_COMBAT_MESSAGE_TEMPLATES', 'enemy_name_from_item', 'english_enemy_name_from_item', 'localized_enemy_name_from_item', 'default_combat_template', 'format_combat_message', 'is_builtin_combat_template', 'text']
