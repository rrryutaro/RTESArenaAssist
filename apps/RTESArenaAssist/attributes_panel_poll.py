from __future__ import annotations
from typing import Optional
import arena_data
import i18n_helper as i18n
from attributes_panel import OFF_BONUS_PTS_U8, OFF_DAMAGE_I16, OFF_EXP_U32, OFF_FATIGUE_U16, OFF_GOLD_U32, OFF_HEALTH_CURR_U16, OFF_FACE_INDEX, OFF_HEALTH_MAX_U16, OFF_IS_FEMALE, OFF_LEVEL_U8, OFF_NAME, OFF_PRIMARY_1, OFF_PRIMARY_2, OFF_RACE_INDEX, OFF_SPELL_PTS_CURR, OFF_SPELL_PTS_MAX, PRIMARY_LEN, UNKNOWN, _signed, class_names
from player_condition import read_fields as read_condition_fields
from player_condition import sheet_values as condition_sheet_values
from attribute_formulas import calc_bonus_to_health, calc_bonus_to_health_256, calc_bonus_to_hit, calc_damage_bonus, calc_magic_defense, calc_max_kilos, calc_max_stamina, calc_max_stamina_256
_SHEET_ATTR_KEYS = ('str', 'int', 'wil', 'agi', 'spd', 'end', 'per', 'luc')

def poll_attributes(panel) -> None:
    if panel._analyzer is None or panel._anchor == 0:
        return
    if panel._freeze_updates:
        return
    sheet: dict[str, str] = {}
    try:
        raw = panel._analyzer.read_bytes(panel._anchor + OFF_NAME, 26)
        name = raw.split(b'\x00', 1)[0].decode('ascii', errors='replace')
        if name:
            panel._name_lbl.setText(name)
            sheet['name'] = name
    except OSError:
        pass
    try:
        race_idx = panel._analyzer.read_bytes(panel._anchor + OFF_RACE_INDEX, 1)[0]
        sheet['race_index'] = str(race_idx)
        if panel._chargen_mode and panel._race_label:
            panel._race_lbl.setText(panel._race_label)
            sheet['race'] = panel._race_label
        else:
            en = arena_data.race_en(race_idx)
            disp = arena_data.race_display_name(race_idx)
            if en and disp:
                panel._race_lbl.setText(f'{disp} ({en})' if disp != en else en)
                sheet['race'] = disp
                sheet['race_en'] = en
            elif panel._race_label:
                panel._race_lbl.setText(panel._race_label)
                sheet['race'] = panel._race_label
    except OSError:
        if panel._race_label:
            panel._race_lbl.setText(panel._race_label)
            sheet['race'] = panel._race_label
    try:
        from player_class_reader import read_class_index
        cls_idx = read_class_index(panel._analyzer, panel._anchor)
        ja_text = panel._lookup_class_display(cls_idx) if cls_idx is not None else None
        if ja_text:
            panel._class_lbl.setText(ja_text)
            names = class_names(cls_idx)
            if names is not None:
                sheet['class'], sheet['class_en'] = names
        elif panel._class_label:
            panel._class_lbl.setText(panel._class_label)
            sheet['class'] = panel._class_label
    except OSError:
        if panel._class_label:
            panel._class_lbl.setText(panel._class_label)
            sheet['class'] = panel._class_label
    try:
        raw_data = panel._analyzer.read_bytes(panel._anchor + OFF_PRIMARY_1, PRIMARY_LEN)
    except OSError:
        return
    if len(raw_data) != PRIMARY_LEN:
        return
    if panel._chargen_mode or panel._is_bonus_screen:
        data = raw_data
    else:
        data = bytes((round(b * 100 / 256) for b in raw_data))
    base_data = None
    if not panel._chargen_mode and (not panel._is_bonus_screen):
        try:
            raw_base = panel._analyzer.read_bytes(panel._anchor + OFF_PRIMARY_2, PRIMARY_LEN)
            if len(raw_base) == PRIMARY_LEN:
                base_data = bytes((round(b * 100 / 256) for b in raw_base))
        except OSError:
            pass
    for idx, sb in enumerate(panel._spinboxes):
        if sb.hasFocus() and panel._cheat_enabled:
            continue
        new_val = data[idx]
        if sb.value() != new_val:
            sb.blockSignals(True)
            sb.setValue(new_val)
            sb.blockSignals(False)
    STR, INT, WIL, AGI, SPD, END, PER, LUC = data
    for idx, (key, value) in enumerate(zip(_SHEET_ATTR_KEYS, data)):
        sheet[key] = str(value)
        if base_data is not None:
            base = base_data[idx]
            change = value - base
            if change:
                sheet[f'{key}_base'] = str(base)
                sheet[f'{key}_change'] = _signed(change)
    if panel._is_bonus_screen:
        damage = calc_damage_bonus(STR)
    else:
        try:
            d_raw = panel._analyzer.read_bytes(panel._anchor + OFF_DAMAGE_I16, 2)
            damage = d_raw[0] | d_raw[1] << 8
            if damage & 32768:
                damage -= 65536
        except OSError:
            damage = calc_damage_bonus(STR)
    sheet['damage'] = _signed(damage)
    sheet['max_kilos'] = str(calc_max_kilos(STR))
    sheet['magic_def'] = _signed(calc_magic_defense(WIL))
    bth = calc_bonus_to_hit(AGI)
    sheet['to_hit'] = sheet['to_defend'] = _signed(bth)
    for key in ('damage', 'max_kilos', 'magic_def', 'to_hit', 'to_defend'):
        panel._derived[key].setText(sheet[key])
    if panel._chargen_mode or panel._is_bonus_screen:
        bh = calc_bonus_to_health(END)
    else:
        bh = calc_bonus_to_health_256(raw_data[5])
    sheet['health'] = sheet['heal_mod'] = _signed(bh)
    sheet['charisma'] = _signed(calc_bonus_to_hit(PER))
    for key in ('health', 'heal_mod', 'charisma'):
        panel._derived[key].setText(sheet[key])
    _always_max_on = panel._health_max_enabled or panel._spell_max_enabled or panel._fatigue_max_enabled
    _cheat_can_write = bool(getattr(panel._analyzer, 'can_write', False))
    if _always_max_on and (not _cheat_can_write):
        panel._cheat_note_lbl.setText(i18n.tr('status.no_write_permission'))
        panel._cheat_note_lbl.setVisible(True)
    try:
        sp_curr = panel._read_u16(panel._anchor + OFF_SPELL_PTS_CURR)
        sp_max = panel._read_u16(panel._anchor + OFF_SPELL_PTS_MAX)
        if panel._spell_max_enabled and _cheat_can_write and (sp_curr < sp_max) and (sp_max > 0):
            try:
                panel._analyzer.write_bytes(panel._anchor + OFF_SPELL_PTS_CURR, bytes([sp_max & 255, sp_max >> 8 & 255]))
                sp_curr = sp_max
            except (OSError, AttributeError):
                pass
        panel._derived['spell_pts'].setText(f'{sp_curr}/{sp_max}')
        sheet['spell_pts'] = f'{sp_curr}/{sp_max}'
        sheet['spell_pts_curr'] = str(sp_curr)
        sheet['spell_pts_max'] = str(sp_max)
        sheet['is_magic'] = '1' if sp_max > 0 else '0'
    except OSError:
        panel._derived['spell_pts'].setText(UNKNOWN)
    if panel._chargen_mode or panel._is_bonus_screen:
        try:
            bonus = panel._analyzer.read_bytes(panel._anchor + OFF_BONUS_PTS_U8, 1)[0]
            sheet['bonus_pts'] = str(bonus)
            if not panel._bp_spin.hasFocus():
                panel._bp_spin.blockSignals(True)
                panel._bp_spin.setValue(bonus)
                panel._bp_spin.blockSignals(False)
        except OSError:
            pass
    try:
        from combat_info import read_player_health_sample
        try:
            hc, hm, damage_source = read_player_health_sample(panel._analyzer, panel._anchor)
        except (OSError, RuntimeError, ValueError):
            hc = panel._read_u16(panel._anchor + OFF_HEALTH_CURR_U16)
            hm = panel._read_u16(panel._anchor + OFF_HEALTH_MAX_U16)
            damage_source = None
        raw_hc = hc
        if panel._health_max_enabled and _cheat_can_write and (hc < hm) and (hm > 0):
            try:
                panel._analyzer.write_bytes(panel._anchor + OFF_HEALTH_CURR_U16, bytes([hm & 255, hm >> 8 & 255]))
                hc = hm
            except (OSError, AttributeError):
                pass
        panel._health_observer.observe(raw_hc, hm, effective_hp=hc, source=damage_source)
        if panel._is_bonus_screen and hm > 0:
            hc = hm
        panel._stats['hp'].setText(f'{hc}/{hm}')
        sheet['hp'] = f'{hc}/{hm}'
        sheet['hp_curr'] = str(hc)
        sheet['hp_max'] = str(hm)
    except OSError:
        panel._stats['hp'].setText(UNKNOWN)
    fat_max_256 = raw_data[0] + raw_data[5]
    if panel._chargen_mode or panel._is_bonus_screen:
        fat_max = calc_max_stamina(STR, END)
    else:
        fat_max = calc_max_stamina_256(raw_data[0], raw_data[5])
    sheet['fatigue_max'] = str(fat_max)
    if panel._chargen_mode:
        panel._stats['fatigue'].setText(f'{fat_max}/{fat_max}')
        sheet['fatigue'] = f'{fat_max}/{fat_max}'
        sheet['fatigue_curr'] = str(fat_max)
    else:
        try:
            u16 = panel._read_u16(panel._anchor + OFF_FATIGUE_U16)
            if panel._fatigue_max_enabled and _cheat_can_write and (not panel._is_bonus_screen) and (fat_max_256 > 0):
                fat_u16_max = min(65535, fat_max_256 << 6)
                if u16 < fat_u16_max:
                    try:
                        panel._analyzer.write_bytes(panel._anchor + OFF_FATIGUE_U16, bytes([fat_u16_max & 255, fat_u16_max >> 8 & 255]))
                        u16 = fat_u16_max
                    except (OSError, AttributeError):
                        pass
            fat_curr = round((u16 >> 6) * 100 / 256)
            panel._stats['fatigue'].setText(f'{fat_curr}/{fat_max}')
            sheet['fatigue'] = f'{fat_curr}/{fat_max}'
            sheet['fatigue_curr'] = str(fat_curr)
        except OSError:
            panel._stats['fatigue'].setText(f'—/{fat_max}')
    try:
        gold = panel._read_u32(panel._anchor + OFF_GOLD_U32)
        panel._stats['gold'].setText(str(gold))
        sheet['gold'] = str(gold)
    except OSError:
        panel._stats['gold'].setText(UNKNOWN)
    current_level: Optional[int] = None
    if panel._chargen_mode:
        panel._stats['level'].setText('1')
        current_level = 1
        sheet['level'] = '1'
    else:
        try:
            lvl_byte = panel._analyzer.read_bytes(panel._anchor + OFF_LEVEL_U8, 1)[0]
            lvl = lvl_byte + 1
            if 1 <= lvl <= 50:
                panel._stats['level'].setText(str(lvl))
                current_level = lvl
                sheet['level'] = str(lvl)
            else:
                panel._stats['level'].setText(UNKNOWN)
        except OSError:
            panel._stats['level'].setText(UNKNOWN)
    try:
        xp_raw = panel._analyzer.read_bytes(panel._anchor + OFF_EXP_U32, 4)
        xp = xp_raw[0] | xp_raw[1] << 8 | xp_raw[2] << 16 | xp_raw[3] << 24
        if 0 <= xp <= 99999999:
            next_thresh = panel._next_exp_threshold(current_level)
            sheet['experience'] = str(xp)
            if next_thresh is not None:
                panel._stats['experience'].setText(f'{xp} / {next_thresh}')
                sheet['experience_next'] = str(next_thresh)
                start = panel._next_exp_threshold(current_level - 1) if current_level > 1 else 0
                if start is not None:
                    sheet['experience_start'] = str(start)
            else:
                panel._stats['experience'].setText(str(xp))
        else:
            panel._stats['experience'].setText(UNKNOWN)
    except OSError:
        panel._stats['experience'].setText(UNKNOWN)
    try:
        sheet['is_female'] = str(panel._analyzer.read_bytes(panel._anchor + OFF_IS_FEMALE, 1)[0])
        sheet['face_index'] = str(panel._analyzer.read_bytes(panel._anchor + OFF_FACE_INDEX, 1)[0])
    except OSError:
        pass
    if not panel._chargen_mode:
        fields = read_condition_fields(panel._analyzer, panel._anchor)
        if fields is not None:
            sheet.update(condition_sheet_values(fields, i18n.text('charsheet.list_separator')))
            panel._condition_log.observe(fields, hp=sheet.get('hp_curr'), hp_max=sheet.get('hp_max'))
    panel._publish_sheet_values(sheet)
__all__ = ['poll_attributes']
