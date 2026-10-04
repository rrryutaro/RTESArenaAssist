from __future__ import annotations
import math
import time
from dataclasses import dataclass
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget
from combat_text_ja import text as combat_ja
_ARENA_NATIVE_HEIGHT = 200
_ARENA_EXPLORATION_HEIGHT = 147
_ARENA_DAMAGE_MARGIN = 2
_ARENA_DAMAGE_SECONDS = 5.0

def _hp_text(current: int, maximum: int) -> str:
    return f'{max(0, current)} / {maximum}'

def _set_meter(bar: QProgressBar, label: str, current: int, maximum: int) -> None:
    maximum = max(0, int(maximum))
    current = max(0, int(current))
    bar_maximum = max(1, maximum)
    bar.setRange(0, bar_maximum)
    bar.setValue(min(current, bar_maximum))
    bar.setFormat(f'{label}  {current} / {maximum}')

@dataclass
class _ExperiencePopup:
    serial: int
    expires_at: float
    label: QLabel

class _CompactEnemyRow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)
        self.name = QLabel('')
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hp = QProgressBar()
        self.hp.setObjectName('rightHp')
        self.stamina = QProgressBar()
        self.stamina.setObjectName('rightStamina')
        self.spell_points = QProgressBar()
        self.spell_points.setObjectName('rightSpell')
        for meter in (self.hp, self.stamina, self.spell_points):
            meter.setTextVisible(True)
            meter.setFixedHeight(11)
            root.addWidget(meter)
        root.insertWidget(0, self.name)
        self.setFixedWidth(172)

    def update_enemy(self, enemy, *, name: str) -> None:
        self.name.setText(f'{name}  Lv {enemy.level}')
        _set_meter(self.hp, combat_ja('combat.hp'), enemy.hp, enemy.max_hp)
        _set_meter(self.stamina, combat_ja('combat.stamina'), enemy.stamina, enemy.max_stamina)
        _set_meter(self.spell_points, combat_ja('combat.spell_points'), enemy.spell_points, enemy.max_spell_points)

class CombatPanel(QWidget):

    def __init__(self, *, compact: bool=False, parent=None):
        super().__init__(parent)
        self._compact = compact
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)
        top = QHBoxLayout()
        self._title = QLabel(combat_ja('combat.title'))
        self._title.setStyleSheet('font-weight: 700;')
        self._target = QLabel('—')
        self._target.setStyleSheet('font-weight: 700;')
        self._enemy_hp = QProgressBar()
        self._enemy_hp.setTextVisible(True)
        self._enemy_hp.setMinimumWidth(130)
        top.addWidget(self._title)
        top.addSpacing(8)
        top.addWidget(self._target)
        top.addWidget(self._enemy_hp, 1)
        root.addLayout(top)
        self._enemy_rows = []
        for _index in range(8):
            row_widget = QWidget(self)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            name = QLabel('')
            name.setMinimumWidth(110)
            hp = QProgressBar()
            hp.setTextVisible(True)
            hp.setMinimumWidth(130)
            row.addWidget(name)
            row.addWidget(hp, 1)
            row_widget.hide()
            root.addWidget(row_widget)
            self._enemy_rows.append((row_widget, name, hp))
        self._player = QLabel('—')
        root.addWidget(self._player)
        self._message = QLabel('')
        self._message.setWordWrap(True)
        self._message.setStyleSheet('color:#f2e3a6; background:rgba(255,255,255,18); border-radius:4px; padding:4px;')
        self._message.hide()
        root.addWidget(self._message)
        self._detail = QLabel('')
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self._detail, 1 if not compact else 0)
        if compact:
            self._detail.setMaximumHeight(70)
            self.setMaximumHeight(140)

    def update_combat(self, *, target_name: str, target_hp: int, target_max_hp: int, player_hp: int, player_max_hp: int, detail: str, message: str='', result: bool=False, display_format: str='meters', enemies: list[dict] | None=None) -> None:
        self._title.setText(combat_ja('combat.result') if result else combat_ja('combat.title'))
        meters = display_format == 'meters'
        enemy_rows = list(enemies or [])
        self._target.setVisible(meters and (not enemy_rows) and bool(target_name))
        self._enemy_hp.setVisible(meters and (not enemy_rows) and bool(target_name))
        self._target.setText(target_name or combat_ja('combat.enemy'))
        maximum = max(1, target_max_hp)
        self._enemy_hp.setRange(0, maximum)
        self._enemy_hp.setValue(max(0, min(target_hp, maximum)))
        self._enemy_hp.setFormat(_hp_text(target_hp, maximum))
        for index, (row_widget, name, hp) in enumerate(self._enemy_rows):
            if meters and index < len(enemy_rows):
                enemy = enemy_rows[index]
                current = int(enemy.get('hp', 0))
                maximum = max(1, int(enemy.get('max_hp', 1)))
                name.setText(str(enemy.get('name', '')))
                hp.setRange(0, maximum)
                hp.setValue(max(0, min(current, maximum)))
                hp.setFormat(_hp_text(current, maximum))
                row_widget.show()
            else:
                row_widget.hide()
        self._player.setText(f"{combat_ja('combat.player_hp')}: {_hp_text(player_hp, player_max_hp)}")
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self._message.setText(message)
        self._message.setVisible(bool(message))
        if self._compact:
            self._detail.setMaximumHeight(104 if result else 70)
            if message:
                self._message.setMaximumHeight(108)
                self.setMaximumHeight(360 if meters else 266)
            else:
                meter_height = min(len(enemy_rows), 8) * 27
                self.setMaximumHeight(120 + meter_height if meters else 180 if result else 140)

    def clear_combat(self) -> None:
        self._target.setText('—')
        self._enemy_hp.setRange(0, 1)
        self._enemy_hp.setValue(0)
        self._enemy_hp.setFormat('—')
        self._player.setText('—')
        self._message.clear()
        self._message.hide()
        self._detail.clear()
        for row_widget, _name, _hp in self._enemy_rows:
            row_widget.hide()

class CombatOverlay(QWidget):

    def __init__(self, owner=None):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput
        super().__init__(owner, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._top = QFrame(self)
        self._top.setStyleSheet('QFrame { color:#fff; background:rgba(10,10,14,205); border:1px solid rgba(255,255,255,100); border-radius:6px; padding:5px 10px; }QLabel { color:#fff; background:transparent; border:0; font-weight:700; }QProgressBar { color:#fff; background:rgba(0,0,0,120); border:1px solid rgba(255,255,255,120); border-radius:3px; text-align:center; min-height:17px; }QProgressBar#topHp::chunk { background:#d8404f; border-radius:2px; }QProgressBar#topStamina::chunk { background:#d4a62a; border-radius:2px; }QProgressBar#topSpell::chunk { background:#4679d8; border-radius:2px; }')
        top_layout = QVBoxLayout(self._top)
        top_layout.setContentsMargins(8, 4, 8, 5)
        top_layout.setSpacing(2)
        self._top_name = QLabel('')
        self._top_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top_event = QLabel('')
        self._top_event.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_head = QHBoxLayout()
        top_head.setContentsMargins(0, 0, 0, 0)
        top_head.setSpacing(8)
        top_head.addStretch(1)
        top_head.addWidget(self._top_name)
        top_head.addWidget(self._top_event)
        top_head.addStretch(1)
        self._top_hp = QProgressBar()
        self._top_hp.setObjectName('topHp')
        self._top_hp.setTextVisible(True)
        self._top_hp.setMinimumWidth(190)
        self._top_stamina = QProgressBar()
        self._top_stamina.setObjectName('topStamina')
        self._top_stamina.setTextVisible(True)
        self._top_stamina.setMinimumWidth(145)
        self._top_spell_points = QProgressBar()
        self._top_spell_points.setObjectName('topSpell')
        self._top_spell_points.setTextVisible(True)
        self._top_spell_points.setMinimumWidth(145)
        top_meters = QHBoxLayout()
        top_meters.setContentsMargins(0, 0, 0, 0)
        top_meters.setSpacing(5)
        top_meters.addWidget(self._top_hp)
        top_meters.addWidget(self._top_stamina)
        top_meters.addWidget(self._top_spell_points)
        top_layout.addLayout(top_head)
        top_layout.addLayout(top_meters)
        self._right = QFrame(self)
        self._right.setObjectName('combatRight')
        self._right.setStyleSheet('QFrame#combatRight { color:#fff; background:rgba(10,10,14,190); border-radius:6px; padding:5px; }QLabel { color:#fff; background:transparent; border:0; font-size:10px; font-weight:700; }QProgressBar { color:#fff; background:rgba(0,0,0,130); border:0; border-radius:2px; text-align:center; font-size:8px; }QProgressBar#rightHp::chunk { background:#d8404f; }QProgressBar#rightStamina::chunk { background:#d4a62a; }QProgressBar#rightSpell::chunk { background:#4679d8; }')
        right_layout = QVBoxLayout(self._right)
        right_layout.setContentsMargins(5, 4, 5, 4)
        right_layout.setSpacing(4)
        self._right_rows = []
        for _index in range(8):
            row = _CompactEnemyRow(self._right)
            row.hide()
            right_layout.addWidget(row)
            self._right_rows.append(row)
        self._bottom = QLabel(self)
        self._bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bottom.setStyleSheet('QLabel { color:#ffb8b8; background:rgba(40,4,4,205); border-radius:6px; padding:6px 12px; font-weight:700; }')
        self._xp_style = 'QLabel { color:#ffd36b; background:rgba(40,28,4,215); border-radius:6px; padding:6px 12px; font-weight:700; }'
        self._xp_popups: list[_ExperiencePopup] = []
        self._last_xp_serial = 0
        self._clock = time.monotonic
        self._low_hp_effect = False
        self._low_hp_top = 0
        self._last_damage_serial = 0
        self._damage_expires_at = 0.0
        self._damage_timer = QTimer(self)
        self._damage_timer.setInterval(100)
        self._damage_timer.timeout.connect(self._refresh_damage)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(80)
        self._pulse_timer.timeout.connect(self.update)
        self._xp_timer = QTimer(self)
        self._xp_timer.setInterval(100)
        self._xp_timer.timeout.connect(self._refresh_xp)
        self.hide()

    def record_xp(self, events, *, duration_seconds: int=5) -> None:
        self._expire_xp()
        duration = max(1, min(60, int(duration_seconds)))
        for event in events:
            if event.serial <= self._last_xp_serial:
                continue
            self._last_xp_serial = event.serial
            if event.experience_gain <= 0:
                continue
            label = QLabel(combat_ja('combat.experience_popup', xp=event.experience_gain), self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(self._xp_style)
            self._xp_popups.append(_ExperiencePopup(event.serial, self._clock() + duration, label))
        if self._xp_popups and (not self._xp_timer.isActive()):
            self._xp_timer.start()

    def _expire_xp(self) -> None:
        now = self._clock()
        live = []
        for popup in self._xp_popups:
            if now < popup.expires_at:
                live.append(popup)
            else:
                popup.label.hide()
                popup.label.deleteLater()
        self._xp_popups = live
        if not live:
            self._xp_timer.stop()

    def has_active_xp(self) -> bool:
        self._expire_xp()
        return bool(self._xp_popups)

    def _layout_xp(self, exploration_bottom: int, bottom_margin: int) -> None:
        right_edge = self.width() - 12
        for popup in reversed(self._xp_popups):
            label = popup.label
            label.adjustSize()
            x = right_edge - label.width()
            if x < 8:
                label.hide()
                continue
            label.move(x, max(10, exploration_bottom - label.height() - bottom_margin))
            label.show()
            right_edge = x - 6

    def _refresh_xp(self) -> None:
        self._expire_xp()
        if self.isHidden():
            return
        if not self._has_visible_content():
            self.hide()
            return
        exploration_bottom = round(self.height() * _ARENA_EXPLORATION_HEIGHT / _ARENA_NATIVE_HEIGHT)
        bottom_margin = max(2, round(self.height() * _ARENA_DAMAGE_MARGIN / _ARENA_NATIVE_HEIGHT))
        self._layout_xp(exploration_bottom, bottom_margin)

    def _has_visible_content(self) -> bool:
        return self._low_hp_effect or any((not widget.isHidden() for widget in (self._top, self._right, self._bottom))) or any((not popup.label.isHidden() for popup in self._xp_popups))

    def _refresh_damage(self) -> None:
        if self._damage_expires_at and self._clock() < self._damage_expires_at:
            return
        self._damage_expires_at = 0.0
        self._damage_timer.stop()
        self._bottom.hide()
        if not self._has_visible_content():
            self.hide()

    def render(self, view, *, name_of, rect: tuple[int, int, int, int], show_combat: bool=True, xp_seconds: int=5, show_xp: bool=True, low_hp_effect: bool=False, low_hp_top: int=0) -> None:
        if show_xp:
            self.record_xp(view.events, duration_seconds=xp_seconds)
        elif self._xp_popups:
            self._xp_timer.stop()
            for popup in self._xp_popups:
                popup.label.hide()
                popup.label.deleteLater()
            self._xp_popups.clear()
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            self.hide()
            return
        self.setGeometry(left, top, right - left, bottom - top)
        width, height = (self.width(), self.height())
        target = view.target
        last_enemy = next((event for event in reversed(view.history) if event.enemy is not None and event.kind == 'enemy_damage'), None)
        last_defeat = next((event for event in reversed(view.history) if event.enemy is not None and event.kind == 'enemy_defeated'), None)
        new_player_damage = next((event for event in reversed(view.events) if event.kind == 'player_damage' and event.serial > self._last_damage_serial), None)
        self._top.hide()
        self._right.hide()
        self._bottom.hide()
        effect_top = min(height, max(0, int(low_hp_top)))
        if self._low_hp_effect != low_hp_effect or self._low_hp_top != effect_top:
            self._low_hp_effect = low_hp_effect
            self._low_hp_top = effect_top
            self.update()
        if low_hp_effect:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
        exploration_bottom = round(height * _ARENA_EXPLORATION_HEIGHT / _ARENA_NATIVE_HEIGHT)
        bottom_margin = max(2, round(height * _ARENA_DAMAGE_MARGIN / _ARENA_NATIVE_HEIGHT))
        if show_combat and target is not None:
            self._top_name.setText(f'{name_of(target)}  Lv {target.level}')
            _set_meter(self._top_hp, combat_ja('combat.hp'), target.hp, target.max_hp)
            _set_meter(self._top_stamina, combat_ja('combat.stamina'), target.stamina, target.max_stamina)
            _set_meter(self._top_spell_points, combat_ja('combat.spell_points'), target.spell_points, target.max_spell_points)
            if last_defeat is not None and last_defeat.enemy.slot == target.slot and (last_defeat.serial >= (last_enemy.serial if last_enemy else 0)):
                self._top_event.setText(f"-{last_defeat.amount}  {combat_ja('combat.defeated')}")
            elif last_enemy is not None and last_enemy.enemy.slot == target.slot:
                self._top_event.setText(f'-{last_enemy.amount}')
            else:
                self._top_event.clear()
            self._top_event.setVisible(bool(self._top_event.text()))
            self._top.adjustSize()
            self._top.move((width - self._top.width()) // 2, max(10, height // 30))
            self._top.show()
        others = [enemy for enemy in view.known_enemies if show_combat and (not enemy.dead) and (enemy is not target)]
        for index, row in enumerate(self._right_rows):
            if index < len(others):
                enemy = others[index]
                row.update_enemy(enemy, name=name_of(enemy))
                row.show()
            else:
                row.hide()
        if others:
            self._right.adjustSize()
            self._right.move(max(8, width - self._right.width() - 12), max(10, (exploration_bottom - self._right.height()) // 2))
            self._right.show()
        if new_player_damage is not None and show_combat:
            self._last_damage_serial = new_player_damage.serial
            self._bottom.setText(f"{combat_ja('combat.damage_received')}  -{new_player_damage.amount}  {_hp_text(new_player_damage.player_hp, new_player_damage.player_max_hp)}")
            self._damage_expires_at = self._clock() + _ARENA_DAMAGE_SECONDS
            self._damage_timer.start()
        if not show_combat or (view.show_result and (not any((not enemy.dead for enemy in view.known_enemies)))):
            self._damage_expires_at = 0.0
            self._damage_timer.stop()
        if show_combat and self._damage_expires_at and (self._clock() < self._damage_expires_at):
            self._bottom.adjustSize()
            self._bottom.move((width - self._bottom.width()) // 2, max(10, exploration_bottom - self._bottom.height() - bottom_margin))
            self._bottom.show()
        else:
            self._bottom.hide()
        self._layout_xp(exploration_bottom, bottom_margin)
        if self._has_visible_content():
            self.show()
            self.raise_()
        else:
            self.hide()

    def clear(self) -> None:
        self._low_hp_effect = False
        self._damage_expires_at = 0.0
        self._damage_timer.stop()
        self._pulse_timer.stop()
        self._bottom.hide()
        self.hide()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._low_hp_effect:
            return
        bottom = round(self.height() * _ARENA_EXPLORATION_HEIGHT / _ARENA_NATIVE_HEIGHT)
        top = self._low_hp_top
        if bottom <= top:
            return
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        pulse = 0.725 + 0.275 * math.sin(self._clock() * math.pi)
        for offset, alpha in ((0, 104), (4, 88), (8, 72), (12, 56), (16, 40), (20, 24)):
            color = QColor(190, 20, 38, round(alpha * pulse))
            thickness = 4
            painter.fillRect(offset, top + offset, max(0, self.width() - 2 * offset), thickness, color)
            painter.fillRect(offset, max(top + offset, bottom - offset - thickness), max(0, self.width() - 2 * offset), thickness, color)
            painter.fillRect(offset, top + offset, thickness, max(0, bottom - top - 2 * offset), color)
            painter.fillRect(max(offset, self.width() - offset - thickness), top + offset, thickness, max(0, bottom - top - 2 * offset), color)
        painter.end()

    def header_visible(self) -> bool:
        return not self.isHidden() and (not self._top.isHidden())

    def reset(self) -> None:
        self.clear()
        self._xp_timer.stop()
        for popup in self._xp_popups:
            popup.label.hide()
            popup.label.deleteLater()
        self._xp_popups.clear()
        self._last_xp_serial = 0
        self._last_damage_serial = 0
__all__ = ['CombatOverlay', 'CombatPanel']
