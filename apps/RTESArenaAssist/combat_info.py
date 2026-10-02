from __future__ import annotations
from collections import deque
from dataclasses import dataclass, replace
from typing import Optional
from attribute_formulas import calc_max_stamina_256
from viewer_constants import RT_ANGLE_MASK as PLAYER_ANGLE_MASK, RT_ANGLE_NORTH_RAW as PLAYER_ANGLE_NORTH, RT_ANGLE_OFFSET as PLAYER_ANGLE_OFFSET, RT_COORD_X_OFFSET as PLAYER_X_OFFSET, RT_COORD_Z_OFFSET as PLAYER_Z_OFFSET
PLAYER_HP_OFFSET = 509
PLAYER_MAX_HP_OFFSET = 511
PLAYER_EXP_OFFSET = 1453
PLAYER_BLOCK_END = PLAYER_EXP_OFFSET + 4
ENEMY_BASE_OFFSET = 177856
ENEMY_COUNT = 8
ENEMY_STRIDE = 1054
ENEMY_HP_OFFSET = 89
ENEMY_MAX_HP_OFFSET = 91
ENEMY_STAMINA_OFFSET = 93
ENEMY_SPELL_POINTS_OFFSET = 102
ENEMY_MAX_SPELL_POINTS_OFFSET = 104
ENEMY_CURRENT_ATTRIBUTES_OFFSET = 41
ENEMY_EXP_OFFSET = 1033
ENEMY_STATUS_OFFSET = 1037
ENEMY_DEAD_FLAG = 256
ENEMY_NAME_OFFSET = 9
ENEMY_NAME_SIZE = 32
SPRITE_BASE_OFFSET = 3159
SPRITE_STRIDE = 28
SPRITE_FLAT_OFFSET = 12
SPRITE_FLAGS_OFFSET = 15
SPRITE_DATA_OFFSET = 18
SPRITE_UNUSED_FLAG = 16384

@dataclass(frozen=True)
class EnemySnapshot:
    slot: int
    identity: tuple[int, int, int, int]
    race_id: int
    class_id: int
    level: int
    name: str
    sprite_flat: int
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    spell_points: int
    max_spell_points: int
    experience: int
    status_flags: int
    x: int
    y: int
    z: int
    sprite_flags: int

    @property
    def dead(self) -> bool:
        return self.hp <= 0 or bool(self.status_flags & ENEMY_DEAD_FLAG)

@dataclass(frozen=True)
class CombatSnapshot:
    player_hp: int
    player_max_hp: int
    player_experience: int
    player_x: int
    player_z: int
    player_angle_deg: float
    enemies: tuple[EnemySnapshot, ...]

@dataclass(frozen=True)
class CombatReadDiagnostics:
    status: str
    detail: str

@dataclass(frozen=True)
class CombatReadResult:
    snapshot: Optional[CombatSnapshot]
    diagnostics: CombatReadDiagnostics

@dataclass(frozen=True)
class PlayerDamageObservation:
    serial: int
    amount: int
    hp: int
    max_hp: int

class PlayerHealthObserver:

    def __init__(self) -> None:
        self._serial = 0
        self._effective_hp: Optional[int] = None
        self._max_hp: Optional[int] = None
        self._observations: deque[PlayerDamageObservation] = deque(maxlen=64)

    @property
    def latest_serial(self) -> int:
        return self._serial

    def reset(self) -> None:
        self._effective_hp = None
        self._max_hp = None
        self._observations.clear()

    def observe(self, hp: int, max_hp: int, *, effective_hp: Optional[int]=None) -> None:
        hp = int(hp)
        max_hp = int(max_hp)
        after = hp if effective_hp is None else int(effective_hp)
        if not (0 <= hp <= max_hp <= 32767 and 0 <= after <= max_hp):
            self.reset()
            return
        if self._effective_hp is None or self._max_hp != max_hp:
            self._effective_hp = after
            self._max_hp = max_hp
            return
        if hp < self._effective_hp:
            self._serial += 1
            self._observations.append(PlayerDamageObservation(serial=self._serial, amount=self._effective_hp - hp, hp=hp, max_hp=max_hp))
        self._effective_hp = after
        self._max_hp = max_hp

    def observations_after(self, serial: int) -> tuple[PlayerDamageObservation, ...]:
        return tuple((observation for observation in self._observations if observation.serial > int(serial)))

@dataclass(frozen=True)
class CombatEvent:
    serial: int
    kind: str
    amount: int
    enemy: Optional[EnemySnapshot] = None
    player_hp: int = 0
    player_max_hp: int = 0
    experience_gain: int = 0

@dataclass(frozen=True)
class CombatView:
    snapshot: CombatSnapshot
    events: tuple[CombatEvent, ...]
    history: tuple[CombatEvent, ...]
    target: Optional[EnemySnapshot]
    show_active: bool
    show_result: bool
    damage_dealt: int = 0
    damage_received: int = 0
    experience_gained: int = 0
    defeated: tuple[EnemySnapshot, ...] = ()

    @property
    def latest_event(self) -> Optional[CombatEvent]:
        return self.events[-1] if self.events else None

def _u16(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset:offset + 2], 'little', signed=False)

def _i16(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset:offset + 2], 'little', signed=True)

def _u32(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset:offset + 4], 'little', signed=False)

def _stamina_display_value(raw: int) -> int:
    return round((int(raw) >> 6) * 100 / 256)

def _enemy_record_name(raw: bytes) -> str:
    field = bytes(raw[ENEMY_NAME_OFFSET:ENEMY_NAME_OFFSET + ENEMY_NAME_SIZE])
    end = field.find(b'\x00')
    if end <= 0:
        return ''
    candidate = field[:end]
    if not all((32 <= value <= 126 for value in candidate)):
        return ''
    name = candidate.decode('ascii').strip()
    if len(name) < 2 or not any((char.isalpha() for char in name)) or (not all((char.isalpha() or char in " '-." for char in name))):
        return ''
    return name

def read_combat_snapshot_detailed(analyzer, anchor: int) -> CombatReadResult:
    if analyzer is None or not anchor:
        return CombatReadResult(None, CombatReadDiagnostics('detached', 'analyzer/anchor unavailable'))
    try:
        player = analyzer.read_bytes(anchor + PLAYER_HP_OFFSET, PLAYER_BLOCK_END - PLAYER_HP_OFFSET)
        enemy_raw = analyzer.read_bytes(anchor + ENEMY_BASE_OFFSET, ENEMY_COUNT * ENEMY_STRIDE)
        sprite_raw = analyzer.read_bytes(anchor + SPRITE_BASE_OFFSET, ENEMY_COUNT * SPRITE_STRIDE)
        coord_span = PLAYER_Z_OFFSET - PLAYER_X_OFFSET + 2
        coord_raw = analyzer.read_bytes(anchor + PLAYER_X_OFFSET, coord_span)
        angle_bytes = analyzer.read_bytes(anchor + PLAYER_ANGLE_OFFSET, 2)
    except Exception as exc:
        return CombatReadResult(None, CombatReadDiagnostics('read_error', f'{type(exc).__name__}'))
    if len(player) != PLAYER_BLOCK_END - PLAYER_HP_OFFSET or len(enemy_raw) != ENEMY_COUNT * ENEMY_STRIDE or len(sprite_raw) != ENEMY_COUNT * SPRITE_STRIDE or (len(coord_raw) != PLAYER_Z_OFFSET - PLAYER_X_OFFSET + 2) or (len(angle_bytes) != 2):
        return CombatReadResult(None, CombatReadDiagnostics('short_read', f'player={len(player)} enemy={len(enemy_raw)} sprite={len(sprite_raw)} coord={len(coord_raw)} angle={len(angle_bytes)}'))
    php = _u16(player, 0)
    pmax = _u16(player, PLAYER_MAX_HP_OFFSET - PLAYER_HP_OFFSET)
    pexp = _u32(player, PLAYER_EXP_OFFSET - PLAYER_HP_OFFSET)
    if not (1 <= pmax <= 32767 and php <= pmax):
        return CombatReadResult(None, CombatReadDiagnostics('invalid_player', f'hp={php}/{pmax} exp={pexp}'))
    px = _u16(coord_raw, 0)
    pz = _u16(coord_raw, PLAYER_Z_OFFSET - PLAYER_X_OFFSET)
    angle_raw = _u16(angle_bytes, 0)
    angle_deg = ((angle_raw & PLAYER_ANGLE_MASK) - PLAYER_ANGLE_NORTH) * 360.0 / 512.0 % 360.0
    enemies: list[EnemySnapshot] = []
    slot_details: list[str] = []
    for slot in range(ENEMY_COUNT):
        roff = slot * ENEMY_STRIDE
        soff = slot * SPRITE_STRIDE
        rec = enemy_raw[roff:roff + ENEMY_STRIDE]
        sprite = sprite_raw[soff:soff + SPRITE_STRIDE]
        sprite_data = _u16(sprite, SPRITE_DATA_OFFSET)
        sprite_flat = sprite[SPRITE_FLAT_OFFSET]
        sprite_flags = _u16(sprite, SPRITE_FLAGS_OFFSET)
        if sprite_flags & SPRITE_UNUSED_FLAG:
            slot_details.append(f'{slot}:unused anim_flat={sprite_flat} flags=0x{sprite_flags:04X} data={sprite_data}')
            continue
        race_id = rec[4]
        class_id = rec[5]
        level = rec[6]
        name = _enemy_record_name(rec)
        hp = _i16(rec, ENEMY_HP_OFFSET)
        max_hp = _u16(rec, ENEMY_MAX_HP_OFFSET)
        stamina = _stamina_display_value(_u16(rec, ENEMY_STAMINA_OFFSET))
        max_stamina = calc_max_stamina_256(rec[ENEMY_CURRENT_ATTRIBUTES_OFFSET], rec[ENEMY_CURRENT_ATTRIBUTES_OFFSET + 5])
        spell_points = _u16(rec, ENEMY_SPELL_POINTS_OFFSET)
        max_spell_points = _u16(rec, ENEMY_MAX_SPELL_POINTS_OFFSET)
        status = _u16(rec, ENEMY_STATUS_OFFSET)
        if not (1 <= level <= 100 and 1 <= max_hp <= 32767 and (hp <= max_hp)):
            slot_details.append(f'{slot}:shape race={race_id} class={class_id} level={level} hp={hp}/{max_hp} flags=0x{sprite_flags:04X} data={sprite_data}')
            continue
        seed = _u32(rec, 0)
        x = _u16(sprite, 0)
        z = _u16(sprite, 2)
        y = _u16(sprite, 4)
        enemies.append(EnemySnapshot(slot=slot, identity=(seed, race_id, class_id, max_hp), race_id=race_id, class_id=class_id, level=level, name=name, sprite_flat=sprite_flat, hp=hp, max_hp=max_hp, stamina=stamina, max_stamina=max_stamina, spell_points=spell_points, max_spell_points=max_spell_points, experience=_u32(rec, ENEMY_EXP_OFFSET), status_flags=status, x=x, y=y, z=z, sprite_flags=sprite_flags))
        slot_details.append(f'{slot}:live name={name!r} anim_flat={sprite_flat} race={race_id} class={class_id} level={level} hp={hp}/{max_hp} stamina={stamina}/{max_stamina} spell={spell_points}/{max_spell_points} status=0x{status:04X} flags=0x{sprite_flags:04X} data={sprite_data}')
    snapshot = CombatSnapshot(player_hp=php, player_max_hp=pmax, player_experience=pexp, player_x=px, player_z=pz, player_angle_deg=angle_deg, enemies=tuple(enemies))
    detail = f'player={php}/{pmax} exp={pexp} enemies={len(enemies)}; ' + '; '.join(slot_details)
    return CombatReadResult(snapshot, CombatReadDiagnostics('ok', detail))

def read_combat_snapshot(analyzer, anchor: int) -> Optional[CombatSnapshot]:
    return read_combat_snapshot_detailed(analyzer, anchor).snapshot

class CombatTracker:
    ACTIVE_HOLD_POLLS = 40
    RESULT_HOLD_POLLS = 50

    def __init__(self) -> None:
        self._previous: Optional[CombatSnapshot] = None
        self._serial = 0
        self._history: deque[CombatEvent] = deque(maxlen=64)
        self._active_left = 0
        self._result_left = 0
        self._target_slot: Optional[int] = None
        self._damage_dealt = 0
        self._damage_received = 0
        self._experience_gained = 0
        self._defeated: list[EnemySnapshot] = []

    def reset(self) -> None:
        self._previous = None
        self._history.clear()
        self._active_left = 0
        self._result_left = 0
        self._target_slot = None
        self._clear_encounter()

    def _clear_encounter(self) -> None:
        self._history.clear()
        self._damage_dealt = 0
        self._damage_received = 0
        self._experience_gained = 0
        self._defeated.clear()

    def update(self, snapshot: Optional[CombatSnapshot], *, enabled: bool, player_damage_observations: Optional[tuple[PlayerDamageObservation, ...]]=None) -> Optional[CombatView]:
        if not enabled:
            return None
        if snapshot is None:
            self.reset()
            return None
        previous = self._previous
        self._previous = snapshot
        alive_enemies = [enemy for enemy in snapshot.enemies if not enemy.dead]
        previous_alive = bool(previous and any((not enemy.dead for enemy in previous.enemies)))
        prev_by_slot = {enemy.slot: enemy for enemy in previous.enemies} if previous is not None else {}
        events: list[CombatEvent] = []
        deaths: list[int] = []
        newly_live = [enemy for enemy in snapshot.enemies if not enemy.dead and (enemy.slot not in prev_by_slot or prev_by_slot[enemy.slot].identity != enemy.identity)]
        if newly_live:
            enemy = newly_live[0]
            self._serial += 1
            events.append(CombatEvent(serial=self._serial, kind='enemy_encountered', amount=0, enemy=enemy))
            self._target_slot = enemy.slot
        for enemy in snapshot.enemies:
            old = prev_by_slot.get(enemy.slot)
            if old is None or old.identity != enemy.identity:
                if enemy.slot == self._target_slot:
                    self._target_slot = enemy.slot if not enemy.dead else None
                continue
            if enemy.hp < old.hp:
                self._serial += 1
                amount = old.hp - enemy.hp
                events.append(CombatEvent(serial=self._serial, kind='enemy_damage', amount=amount, enemy=enemy))
                self._target_slot = enemy.slot
            if enemy.dead and (not old.dead):
                self._serial += 1
                deaths.append(len(events))
                events.append(CombatEvent(serial=self._serial, kind='enemy_defeated', amount=max(0, old.hp - enemy.hp), enemy=enemy))
                self._target_slot = enemy.slot
        if player_damage_observations is not None:
            if alive_enemies or previous_alive:
                for observation in player_damage_observations:
                    self._serial += 1
                    events.append(CombatEvent(serial=self._serial, kind='player_damage', amount=observation.amount, player_hp=observation.hp, player_max_hp=observation.max_hp))
        elif previous is not None and snapshot.player_hp < previous.player_hp:
            self._serial += 1
            events.append(CombatEvent(serial=self._serial, kind='player_damage', amount=previous.player_hp - snapshot.player_hp, player_hp=snapshot.player_hp, player_max_hp=snapshot.player_max_hp))
        xp_gain = max(0, snapshot.player_experience - previous.player_experience) if previous is not None else 0
        if deaths and xp_gain:
            index = deaths[0]
            events[index] = replace(events[index], experience_gain=xp_gain)
        elif xp_gain:
            self._serial += 1
            events.append(CombatEvent(serial=self._serial, kind='experience', amount=xp_gain, experience_gain=xp_gain))
        if events:
            new_encounter = any((event.kind == 'enemy_encountered' for event in events))
            if new_encounter and (not previous_alive) or (self._active_left == 0 and self._result_left == 0):
                self._clear_encounter()
                if new_encounter:
                    self._result_left = 0
            self._active_left = self.ACTIVE_HOLD_POLLS
            if any((e.kind == 'enemy_defeated' for e in events)):
                self._result_left = self.RESULT_HOLD_POLLS
            for event in events:
                self._history.append(event)
                if event.kind == 'enemy_damage':
                    self._damage_dealt += event.amount
                elif event.kind == 'player_damage':
                    self._damage_received += event.amount
                elif event.kind == 'enemy_defeated' and event.enemy is not None:
                    self._defeated.append(event.enemy)
                if event.experience_gain:
                    self._experience_gained += event.experience_gain
        else:
            self._active_left = max(0, self._active_left - 1)
            self._result_left = max(0, self._result_left - 1)
        if alive_enemies:
            self._active_left = self.ACTIVE_HOLD_POLLS
            current_target = next((enemy for enemy in snapshot.enemies if enemy.slot == self._target_slot), None)
            if current_target is None:
                self._target_slot = alive_enemies[0].slot
        elif previous_alive and (not events) and (self._result_left == 0):
            self._active_left = 0
            self._target_slot = None
        target = next((e for e in snapshot.enemies if e.slot == self._target_slot), None)
        return CombatView(snapshot=snapshot, events=tuple(events), history=tuple(self._history), target=target, show_active=bool(alive_enemies) or self._active_left > 0, show_result=self._result_left > 0, damage_dealt=self._damage_dealt, damage_received=self._damage_received, experience_gained=self._experience_gained, defeated=tuple(self._defeated))
__all__ = ['CombatEvent', 'CombatReadDiagnostics', 'CombatReadResult', 'CombatSnapshot', 'CombatTracker', 'CombatView', 'EnemySnapshot', 'PlayerDamageObservation', 'PlayerHealthObserver', 'read_combat_snapshot', 'read_combat_snapshot_detailed']
