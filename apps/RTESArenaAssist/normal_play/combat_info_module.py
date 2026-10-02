from __future__ import annotations
import logging
import assist_settings as settings
import i18n_helper as i18n
from assist_log import recog as _recog
from combat_info import CombatEvent, CombatTracker, CombatView, read_combat_snapshot_detailed
from combat_text_ja import COMBAT_MESSAGE_TEMPLATE_SETTINGS, english_enemy_name_from_item, localized_enemy_name_from_item, format_combat_message, text as combat_ja
from combat_widgets import CombatOverlay
from display_intent import DisplayIntent
from player_class_reader import class_en_of, class_index_of
_log = logging.getLogger(__name__)

def _enemy_names(enemy) -> tuple[str, str]:
    if enemy.name:
        class_index = class_index_of(enemy.class_id)
        if class_index is not None:
            en = class_en_of(class_index)
            localized = localized_enemy_name_from_item(55 + class_index)
            if en:
                return (en, localized or en)
            if localized:
                return (f'Enemy {enemy.slot + 1}', localized)
    else:
        creature_id = int(enemy.race_id)
        item_index = 73 if creature_id == 24 else 31 + creature_id if 1 <= creature_id <= 23 else None
        creature_index = creature_id - 1
        source_id = f'aexe:entities:creature_names:{creature_index}'
        if item_index is not None:
            en = 'Jagar Tharn' if creature_id == 24 else i18n.original_by_source_id(source_id, category='monsters') or english_enemy_name_from_item(item_index)
            localized = localized_enemy_name_from_item(item_index)
            if en:
                return (en, localized or en)
            if localized:
                return (f'Enemy {enemy.slot + 1}', localized)
    fallback = combat_ja('combat.enemy_number', n=enemy.slot + 1)
    return (f'Enemy {enemy.slot + 1}', fallback)

def _enemy_key(enemy) -> tuple[int, tuple[int, int, int, int]]:
    return (enemy.slot, enemy.identity)

def _enemy_name_resolver(view: CombatView, *, identifiers_enabled: bool, identifier_style: str):
    enemies = []
    seen = set()
    sources = list(view.snapshot.enemies)
    sources.extend((event.enemy for event in view.history if event.enemy is not None))
    sources.extend(view.defeated)
    for enemy in sources:
        key = _enemy_key(enemy)
        if key not in seen:
            seen.add(key)
            enemies.append(enemy)
    base_names = {_enemy_key(enemy): _enemy_names(enemy) for enemy in enemies}
    groups: dict[str, list] = {}
    for enemy in enemies:
        groups.setdefault(base_names[_enemy_key(enemy)][1], []).append(enemy)
    resolved = dict(base_names)
    if identifiers_enabled:
        numeric = identifier_style == 'number'
        for same_names in groups.values():
            if len(same_names) < 2:
                continue
            same_names.sort(key=lambda enemy: (enemy.slot, enemy.identity))
            for index, enemy in enumerate(same_names):
                marker = str(index + 1) if numeric else chr(ord('A') + index)
                en, ja = base_names[_enemy_key(enemy)]
                resolved[_enemy_key(enemy)] = (f'{en} {marker}', f'{ja}{marker}')

    def resolve(enemy) -> tuple[str, str]:
        return resolved.get(_enemy_key(enemy), _enemy_names(enemy))
    return resolve

def _message(kind: str, **values) -> str:
    template = settings.get(COMBAT_MESSAGE_TEMPLATE_SETTINGS[kind], '')
    return format_combat_message(kind, template, **values)

def _short_text(event: CombatEvent, *, translated: bool, enemy_names=_enemy_names) -> str:
    if event.enemy is not None:
        en, ja = enemy_names(event.enemy)
        name = ja if translated else en
    else:
        name = ''
    if event.kind == 'enemy_encountered':
        hp = max(0, event.enemy.hp)
        if translated:
            return _message('encounter', name=name, hp=hp, max_hp=event.enemy.max_hp, level=event.enemy.level)
        return f'Encountered {name}  {hp}/{event.enemy.max_hp} HP'
    if event.kind == 'enemy_damage':
        hp = max(0, event.enemy.hp)
        if translated:
            return _message('enemy_damage', name=name, damage=event.amount, hp=hp, max_hp=event.enemy.max_hp, level=event.enemy.level)
        return f'{name}  -{event.amount} HP  {hp}/{event.enemy.max_hp}'
    if event.kind == 'player_damage':
        if translated:
            return _message('player_damage', damage=event.amount, hp=event.player_hp, max_hp=event.player_max_hp)
        return f'Damage received  -{event.amount} HP  {event.player_hp}/{event.player_max_hp}'
    if event.kind == 'enemy_defeated':
        suffix = f'  +{event.experience_gain} XP' if event.experience_gain else ''
        if translated:
            parts = []
            if event.amount:
                parts.append(_message('enemy_damage', name=name, damage=event.amount, hp=0, max_hp=event.enemy.max_hp, level=event.enemy.level))
            parts.append(_message('defeated', name=name, damage=event.amount, xp=event.experience_gain, level=event.enemy.level))
            if event.experience_gain:
                parts.append(_message('experience', xp=event.experience_gain))
            return '  '.join(parts)
        damage = f'  -{event.amount} HP' if event.amount else ''
        return f'{name}{damage}  defeated{suffix}'
    if event.kind == 'experience':
        return _message('experience', xp=event.experience_gain) if translated else f'Experience +{event.experience_gain}'
    return ''

def _sentence_text(event: CombatEvent, *, translated: bool, enemy_names=_enemy_names) -> str:
    if event.enemy is not None:
        en, ja = enemy_names(event.enemy)
        name = ja if translated else en
    else:
        name = ''
    if not translated:
        if event.kind == 'enemy_encountered':
            return f'You encountered {name}.'
        if event.kind == 'enemy_damage':
            return f'You dealt {event.amount} damage to {name}. It has {max(0, event.enemy.hp)} health remaining.'
        if event.kind == 'player_damage':
            return f'You received {event.amount} damage.'
        if event.kind == 'enemy_defeated':
            xp = f' You gained {event.experience_gain} experience.' if event.experience_gain else ''
            return f'You defeated {name}.{xp}'
        return f'You gained {event.experience_gain} experience.'
    if event.kind == 'enemy_encountered':
        return _message('encounter', name=name, hp=max(0, event.enemy.hp), max_hp=event.enemy.max_hp, level=event.enemy.level)
    if event.kind == 'enemy_damage':
        return _message('enemy_damage', name=name, damage=event.amount, hp=max(0, event.enemy.hp), max_hp=event.enemy.max_hp, level=event.enemy.level)
    if event.kind == 'player_damage':
        return _message('player_damage', damage=event.amount, hp=event.player_hp, max_hp=event.player_max_hp)
    if event.kind == 'enemy_defeated':
        defeated = _message('defeated', name=name, damage=event.amount, xp=event.experience_gain, level=event.enemy.level)
        if event.experience_gain:
            return '\n'.join((defeated, _message('experience', xp=event.experience_gain)))
        return defeated
    return _message('experience', xp=event.experience_gain)

def _compact_events(events) -> list[CombatEvent]:
    source = list(events)
    compact: list[CombatEvent] = []
    for index, event in enumerate(source):
        following = source[index + 1] if index + 1 < len(source) else None
        same_killing_blow = bool(event.kind == 'enemy_damage' and following is not None and (following.kind == 'enemy_defeated') and (event.enemy is not None) and (following.enemy is not None) and (event.enemy.slot == following.enemy.slot) and (event.amount == following.amount))
        if not same_killing_blow:
            compact.append(event)
    return compact

def _history_text(view: CombatView, count: int, *, enemy_names=_enemy_names) -> tuple[str, str]:
    if not view.history:
        return ('', '')
    limit = max(1, min(50, int(count)))
    events = _compact_events(view.history)[-limit:]
    return ('', '\n'.join((_short_text(event, translated=True, enemy_names=enemy_names) for event in events)))

def _detail_text(view: CombatView, *, count: int=10, enemy_names=_enemy_names) -> str:
    return '\n'.join((_short_text(event, translated=True, enemy_names=enemy_names) for event in _compact_events(view.history)[-max(1, count):]))

def _summary_text(view: CombatView, *, enemy_names=_enemy_names) -> str:
    defeated = ', '.join((enemy_names(enemy)[1] for enemy in view.defeated))
    rows = [combat_ja('combat.summary_damage_dealt', value=view.damage_dealt), combat_ja('combat.summary_damage_received', value=view.damage_received), combat_ja('combat.summary_experience', value=view.experience_gained)]
    if defeated:
        rows.insert(0, combat_ja('combat.summary_defeated', names=defeated))
    return '\n'.join(rows)

def _full_detail_text(view: CombatView, *, result: bool, enemy_names=_enemy_names) -> str:
    summary = _summary_text(view, enemy_names=enemy_names)
    if result:
        return summary
    alive = [f'{enemy_names(enemy)[1]}  {max(0, enemy.hp)}/{enemy.max_hp}' for enemy in view.snapshot.enemies if not enemy.dead and enemy is not view.target]
    sections = [_detail_text(view, enemy_names=enemy_names)]
    if alive:
        sections.append('\n'.join(alive))
    sections.append(summary)
    return '\n\n'.join((section for section in sections if section))

class CombatInfoController:

    def __init__(self, window) -> None:
        self._w = window
        self._tracker = CombatTracker()
        self._overlay = CombatOverlay(window)
        self._diagnostic_key = None
        self._health_observation_serial = 0

    def arena_header_visible(self) -> bool:
        return self._overlay.header_visible()

    def _health_observer(self):
        try:
            return self._w._tab_status.health_observer()
        except (AttributeError, RuntimeError):
            return None

    def _combat_speech_pending(self) -> bool:
        tts = getattr(self._w, '_tts', None)
        if tts is None:
            return False
        try:
            return bool(tts.is_speaking('combat_info'))
        except TypeError:
            try:
                return bool(tts.is_speaking())
            except Exception:
                return False
        except Exception:
            return False

    def _append_combat_log(self, events, *, enemy_names) -> None:
        if not settings.get('combat_log_enabled', False):
            return
        store = getattr(self._w, '_combat_log_store', None)
        if store is None:
            return
        try:
            from datetime import datetime
            ts = datetime.now().timestamp()
        except Exception:
            ts = 0.0
        location = getattr(self._w, '_log_location_hint', '') or ''
        for event in _compact_events(events):
            text = _short_text(event, translated=True, enemy_names=enemy_names)
            if not text:
                continue
            try:
                store.append(ts=ts, category='combat', text=text, original='', location=location)
            except Exception:
                _log.exception('combat log append failed')

    @staticmethod
    def _meter_rows(view: CombatView, *, enemy_names) -> list[dict]:
        ordered = []
        seen = set()
        if view.target is not None:
            ordered.append(view.target)
            seen.add(_enemy_key(view.target))
        for enemy in view.snapshot.enemies:
            key = _enemy_key(enemy)
            if key not in seen and (not enemy.dead):
                ordered.append(enemy)
                seen.add(key)
        for enemy in reversed(view.defeated):
            key = _enemy_key(enemy)
            if key not in seen:
                ordered.append(enemy)
                seen.add(key)
        return [{'name': f'{enemy_names(enemy)[1]}  Lv {enemy.level}', 'hp': enemy.hp, 'max_hp': enemy.max_hp} for enemy in ordered[:8]]

    def reset(self) -> None:
        self._tracker.reset()
        self._overlay.reset()
        self._diagnostic_key = None
        observer = self._health_observer()
        self._health_observation_serial = observer.latest_serial if observer is not None else 0

    def poll(self, *, gameplay: bool) -> None:
        w = self._w
        dosbox_enabled = bool(settings.get('combat_dosbox_enabled', False))
        try:
            xp_seconds = max(1, min(60, int(settings.get('combat_arena_xp_seconds', 5))))
        except (TypeError, ValueError):
            xp_seconds = 5
        tab_mode = str(settings.get('combat_translate_tab_mode', 'none'))
        if tab_mode not in ('none', 'both', 'full'):
            tab_mode = 'none'
        tab_format = str(settings.get('combat_translate_tab_format', 'meters'))
        if tab_format not in ('text', 'meters'):
            tab_format = 'meters'
        panel_enabled = bool(settings.get('combat_translate_panel_enabled', False))
        try:
            panel_history_count = max(1, min(50, int(settings.get('combat_translate_panel_history_count', 10))))
        except (TypeError, ValueError):
            panel_history_count = 10
        tts_enabled = bool(settings.get('combat_tts_enabled', False))
        identifiers_enabled = bool(settings.get('combat_enemy_identifier_enabled', False))
        identifier_style = str(settings.get('combat_enemy_identifier_style', 'alphabet'))
        if identifier_style not in ('alphabet', 'number'):
            identifier_style = 'alphabet'
        enabled = bool(gameplay and (not getattr(w, '_loading_state_active', False)))
        observer = self._health_observer()
        if observer is not None:
            damage_observations = observer.observations_after(self._health_observation_serial)
            self._health_observation_serial = observer.latest_serial
        else:
            damage_observations = None
        if enabled:
            read_result = read_combat_snapshot_detailed(w._analyzer, w._anchor)
            snapshot = read_result.snapshot
            read_status = read_result.diagnostics.status
            read_detail = read_result.diagnostics.detail
        else:
            snapshot = None
            read_status = 'inactive'
            read_detail = f"gameplay={gameplay} loading={bool(getattr(w, '_loading_state_active', False))}"
        snapshot_key = None if snapshot is None else (snapshot.player_hp, snapshot.player_max_hp, tuple(((enemy.slot, enemy.identity, enemy.hp, enemy.max_hp, enemy.sprite_flat, enemy.status_flags, enemy.dead) for enemy in snapshot.enemies)))
        diagnostic_key = (enabled, read_status, snapshot_key, dosbox_enabled, tab_mode, tab_format, panel_enabled, panel_history_count, tts_enabled, identifiers_enabled, identifier_style)
        if diagnostic_key != self._diagnostic_key:
            self._diagnostic_key = diagnostic_key
            _recog(_log, 'combat_info read status=%s enabled=%s settings=DOSBox:%s tab:%s/%s panel:%s/%d TTS:%s ID:%s/%s detail=%s', read_status, enabled, dosbox_enabled, tab_mode, tab_format, panel_enabled, panel_history_count, tts_enabled, identifiers_enabled, identifier_style, read_detail)
        view = self._tracker.update(snapshot, enabled=enabled, player_damage_observations=damage_observations)
        enemy_names = _enemy_name_resolver(view, identifiers_enabled=identifiers_enabled, identifier_style=identifier_style) if view is not None else _enemy_names
        if view is not None and view.events:
            _recog(_log, 'combat_info events %s', ', '.join((f"{event.kind}:{event.amount}:slot={(event.enemy.slot if event.enemy is not None else '-')}" for event in view.events)))
            self._append_combat_log(view.events, enemy_names=enemy_names)
        alive = bool(view and any((not enemy.dead for enemy in view.snapshot.enemies)))
        speech_pending = self._combat_speech_pending()
        show_lifetime = bool(view and (view.show_active or view.show_result or (not alive and speech_pending)))
        if dosbox_enabled and view is not None:
            self._overlay.record_xp(view.events, duration_seconds=xp_seconds)
        if dosbox_enabled and view is not None and (show_lifetime or self._overlay.has_active_xp()):
            surface_active = bool(w._layout_mgr.is_dosbox_foreground())
            rect = w._layout_mgr.get_visible_dosbox_qt_rect() if surface_active else None
            if not isinstance(rect, (tuple, list)) or len(rect) != 4:
                rect = None
            if rect is not None:
                self._overlay.render(view, name_of=lambda enemy: enemy_names(enemy)[1], rect=rect, show_combat=show_lifetime, xp_seconds=xp_seconds)
            else:
                self._overlay.clear()
        else:
            self._overlay.clear()
        router = getattr(w, '_ui_router', None)
        if router is None:
            return
        target = view.target if view is not None else None
        show_tab = bool(tab_mode != 'none' and show_lifetime)
        show_panel = bool(panel_enabled and show_lifetime and view and view.history)
        latest = view.latest_event if view is not None else None
        speak = bool(latest is not None and tts_enabled)
        if not show_tab and (not show_panel) and (not speak):
            router.propose_display(DisplayIntent.clear_if_owner('combat_info', mode='translate', priority=-10, reason='combat_info_end'))
            return
        mode = 'combat_full' if show_tab and tab_mode == 'full' else 'combat_map' if show_tab else 'translate'
        panel_en, panel_ja = _history_text(view, panel_history_count, enemy_names=enemy_names) if show_panel else ('', '')
        if target is not None:
            target_name = enemy_names(target)[1]
            target_hp, target_max = (target.hp, target.max_hp)
        else:
            last_enemy = next((e.enemy for e in reversed(view.history) if e.enemy is not None), None)
            target_name = enemy_names(last_enemy)[1] if last_enemy else ''
            target_hp = last_enemy.hp if last_enemy else 0
            target_max = last_enemy.max_hp if last_enemy else 1
        show_result = bool(view and (not alive))
        text_history = _detail_text(view, count=panel_history_count, enemy_names=enemy_names)
        data = {'target_name': target_name, 'target_hp': target_hp, 'target_max_hp': target_max, 'player_hp': view.snapshot.player_hp, 'player_max_hp': view.snapshot.player_max_hp, 'display_format': tab_format, 'enemies': self._meter_rows(view, enemy_names=enemy_names), 'detail_full': text_history if tab_format == 'text' else _summary_text(view, enemy_names=enemy_names), 'detail_compact': text_history if tab_format == 'text' else _summary_text(view, enemy_names=enemy_names) if show_result else '', 'result': show_result, 'panel_enabled': show_panel}
        speech_text = None
        if speak:
            speech_text = '\n'.join((_short_text(event, translated=True, enemy_names=enemy_names) for event in _compact_events(view.events)))
        router.propose_display(DisplayIntent.combat_info(data, mode=mode, panel_en=panel_en, panel_ja=panel_ja, speech_role='situation' if speak else None, speech_text=speech_text, speech_event_id=latest.serial if speak else None))

def poll_combat_info(window, *, gameplay: bool) -> None:
    controller = getattr(window, '_combat_info_controller', None)
    if controller is None:
        controller = CombatInfoController(window)
        window._combat_info_controller = controller
    try:
        controller.poll(gameplay=gameplay)
    except Exception:
        _log.exception('combat info poll failed')
        controller.reset()
        router = getattr(window, '_ui_router', None)
        if router is not None:
            try:
                router.propose_display(DisplayIntent.clear_if_owner('combat_info', mode='translate', priority=-10, reason='combat_info_error'))
            except Exception:
                _log.exception('combat info error cleanup failed')

def reset_combat_info(window) -> None:
    controller = getattr(window, '_combat_info_controller', None)
    if controller is not None:
        controller.reset()
__all__ = ['CombatInfoController', 'poll_combat_info', 'reset_combat_info']
