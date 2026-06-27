from __future__ import annotations
from typing import Optional
import i18n_helper as i18n
from attributes_panel import OFF_BONUS_PTS_U8, OFF_CLASS_INDEX, OFF_DAMAGE_I16, OFF_EXP_U32, OFF_FATIGUE_U16, OFF_GOLD_U16, OFF_HEALTH_CURR_U16, OFF_HEALTH_MAX_U16, OFF_LEVEL_U8, OFF_NAME, OFF_PRIMARY_1, OFF_RACE_INDEX, OFF_SPELL_PTS_CURR, OFF_SPELL_PTS_MAX, PRIMARY_LEN, RACE_INDEX_TO_DISPLAY, UNKNOWN, _signed
from attribute_formulas import calc_bonus_to_health, calc_bonus_to_hit, calc_damage_bonus, calc_magic_defense, calc_max_kilos, calc_max_stamina

def poll_attributes(panel) -> None:
    if panel._analyzer is None or panel._anchor == 0:
        return
    if panel._freeze_updates:
        return
    try:
        raw = panel._analyzer.read_bytes(panel._anchor + OFF_NAME, 26)
        name = raw.split(b'\x00', 1)[0].decode('ascii', errors='replace')
        if name:
            panel._name_lbl.setText(name)
    except OSError:
        pass
    try:
        race_idx = panel._analyzer.read_bytes(panel._anchor + OFF_RACE_INDEX, 1)[0]
        if panel._chargen_mode and panel._race_label:
            panel._race_lbl.setText(panel._race_label)
        else:
            disp = RACE_INDEX_TO_DISPLAY.get(race_idx)
            if disp:
                en, ja = disp
                panel._race_lbl.setText(f'{ja} ({en})')
            elif panel._race_label:
                panel._race_lbl.setText(panel._race_label)
    except OSError:
        if panel._race_label:
            panel._race_lbl.setText(panel._race_label)
    try:
        cls_idx = panel._analyzer.read_bytes(panel._anchor + OFF_CLASS_INDEX, 1)[0]
        ja_text = panel._lookup_class_display(cls_idx)
        if ja_text:
            panel._class_lbl.setText(ja_text)
        elif panel._class_label:
            panel._class_lbl.setText(panel._class_label)
    except OSError:
        if panel._class_label:
            panel._class_lbl.setText(panel._class_label)
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
    for idx, sb in enumerate(panel._spinboxes):
        if sb.hasFocus() and panel._cheat_enabled:
            continue
        new_val = data[idx]
        if sb.value() != new_val:
            sb.blockSignals(True)
            sb.setValue(new_val)
            sb.blockSignals(False)
    STR, INT, WIL, AGI, SPD, END, PER, LUC = data
    try:
        d_raw = panel._analyzer.read_bytes(panel._anchor + OFF_DAMAGE_I16, 2)
        damage = d_raw[0] | d_raw[1] << 8
        if damage & 32768:
            damage -= 65536
    except OSError:
        damage = calc_damage_bonus(STR)
    panel._derived['damage'].setText(_signed(damage))
    panel._derived['max_kilos'].setText(str(calc_max_kilos(STR)))
    panel._derived['magic_def'].setText(_signed(calc_magic_defense(WIL)))
    bth = calc_bonus_to_hit(AGI)
    panel._derived['to_hit'].setText(_signed(bth))
    panel._derived['to_defend'].setText(_signed(bth))
    bh = calc_bonus_to_health(END)
    panel._derived['health'].setText(_signed(bh))
    panel._derived['heal_mod'].setText(_signed(bh))
    panel._derived['charisma'].setText(_signed(calc_bonus_to_hit(PER)))
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
    except OSError:
        panel._derived['spell_pts'].setText(UNKNOWN)
    if panel._chargen_mode or panel._is_bonus_screen:
        try:
            bonus = panel._analyzer.read_bytes(panel._anchor + OFF_BONUS_PTS_U8, 1)[0]
            if not panel._bp_spin.hasFocus():
                panel._bp_spin.blockSignals(True)
                panel._bp_spin.setValue(bonus)
                panel._bp_spin.blockSignals(False)
        except OSError:
            pass
    try:
        hc = panel._read_u16(panel._anchor + OFF_HEALTH_CURR_U16)
        hm = panel._read_u16(panel._anchor + OFF_HEALTH_MAX_U16)
        if panel._health_max_enabled and _cheat_can_write and (hc < hm) and (hm > 0):
            try:
                panel._analyzer.write_bytes(panel._anchor + OFF_HEALTH_CURR_U16, bytes([hm & 255, hm >> 8 & 255]))
                hc = hm
            except (OSError, AttributeError):
                pass
        if panel._is_bonus_screen and hm > 0:
            hc = hm
        panel._stats['hp'].setText(f'{hc}/{hm}')
    except OSError:
        panel._stats['hp'].setText(UNKNOWN)
    fat_max_256 = raw_data[0] + raw_data[5]
    fat_max = calc_max_stamina(STR, END)
    if panel._chargen_mode:
        panel._stats['fatigue'].setText(f'{fat_max}/{fat_max}')
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
        except OSError:
            panel._stats['fatigue'].setText(f'—/{fat_max}')
    try:
        gold = panel._read_u16(panel._anchor + OFF_GOLD_U16)
        if 0 <= gold <= 50000:
            panel._stats['gold'].setText(str(gold))
        else:
            panel._stats['gold'].setText(UNKNOWN)
    except OSError:
        panel._stats['gold'].setText(UNKNOWN)
    current_level: Optional[int] = None
    if panel._chargen_mode:
        panel._stats['level'].setText('1')
        current_level = 1
    else:
        try:
            lvl_byte = panel._analyzer.read_bytes(panel._anchor + OFF_LEVEL_U8, 1)[0]
            lvl = lvl_byte + 1
            if 1 <= lvl <= 50:
                panel._stats['level'].setText(str(lvl))
                current_level = lvl
            else:
                panel._stats['level'].setText(UNKNOWN)
        except OSError:
            panel._stats['level'].setText(UNKNOWN)
    try:
        xp_raw = panel._analyzer.read_bytes(panel._anchor + OFF_EXP_U32, 4)
        xp = xp_raw[0] | xp_raw[1] << 8 | xp_raw[2] << 16 | xp_raw[3] << 24
        if 0 <= xp <= 99999999:
            next_thresh = panel._next_exp_threshold(current_level)
            if next_thresh is not None:
                panel._stats['experience'].setText(f'{xp} / {next_thresh}')
            else:
                panel._stats['experience'].setText(str(xp))
        else:
            panel._stats['experience'].setText(UNKNOWN)
    except OSError:
        panel._stats['experience'].setText(UNKNOWN)
__all__ = ['poll_attributes']
