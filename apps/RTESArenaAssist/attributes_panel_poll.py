"""attributes_panel_poll.py — キャラクター能力値パネルの poll 本体。

メモリ読取→各表示ウィジェット更新の poll ロジックを attributes_panel から
純抽出 (挙動不変)。定数/派生計算/表示 helper は本体・attribute_formulas の
単一住所から import する (本体側の委譲は関数ローカル import で循環回避)。
"""
from __future__ import annotations

from typing import Optional

import i18n_helper as i18n

from attributes_panel import (
    OFF_BONUS_PTS_U8, OFF_CLASS_INDEX, OFF_DAMAGE_I16, OFF_EXP_U32,
    OFF_FATIGUE_U16, OFF_GOLD_U16, OFF_HEALTH_CURR_U16,
    OFF_HEALTH_MAX_U16, OFF_LEVEL_U8, OFF_NAME, OFF_PRIMARY_1,
    OFF_RACE_INDEX, OFF_SPELL_PTS_CURR, OFF_SPELL_PTS_MAX, PRIMARY_LEN,
    RACE_INDEX_TO_DISPLAY, UNKNOWN, _signed,
)
from attribute_formulas import (
    calc_bonus_to_health,
    calc_bonus_to_hit,
    calc_damage_bonus,
    calc_magic_defense,
    calc_max_kilos,
    calc_max_stamina,
)


def poll_attributes(panel) -> None:
    if panel._analyzer is None or panel._anchor == 0:
        return
    if panel._freeze_updates:
        return

    # name
    try:
        raw = panel._analyzer.read_bytes(panel._anchor + OFF_NAME, 26)
        name = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        if name:
            panel._name_lbl.setText(name)
    except OSError:
        pass

    # race（chargen 中は検出値優先、通常プレイはメモリ直読み）
    try:
        race_idx = panel._analyzer.read_bytes(panel._anchor + OFF_RACE_INDEX, 1)[0]
        if panel._chargen_mode and panel._race_label:
            # chargen 中: +0x214 は正確でないため chargen 検出値を優先
            panel._race_lbl.setText(panel._race_label)
        else:
            disp = RACE_INDEX_TO_DISPLAY.get(race_idx)
            if disp:
                en, ja = disp
                panel._race_lbl.setText(f"{ja} ({en})")
            elif panel._race_label:
                panel._race_lbl.setText(panel._race_label)
    except OSError:
        if panel._race_label:
            panel._race_lbl.setText(panel._race_label)

    # class（メモリから設定 + class_list_panel の表記マップで解決）
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

    # primary attrs
    # normal-play: メモリ +0x1CD は 256 スケール raw → round(b*100/256) で 0-100 に変換
    #              （>>8 切り捨てだと -1 ズレが発生するため四捨五入を使う）
    # chargen 中:  メモリ +0x1CD は 0-100 ダイレクト値（変換不要）
    #              （STR=39 raw=39、変換すると 15 になり誤り）
    try:
        raw_data = panel._analyzer.read_bytes(panel._anchor + OFF_PRIMARY_1, PRIMARY_LEN)
    except OSError:
        return
    if len(raw_data) != PRIMARY_LEN:
        return

    # ボーナス画面 (CHARSTAT.IMG) も chargen と同じく 0-100 ダイレクト値
    # （差分検証で確定: bonus 画面では 256→100 切替済み）
    if panel._chargen_mode or panel._is_bonus_screen:
        data = raw_data  # chargen / bonus_screen: 生バイト = 直接表示値
    else:
        data = bytes(round(b * 100 / 256) for b in raw_data)  # normal-play: 256→0-100（四捨五入）

    for idx, sb in enumerate(panel._spinboxes):
        if sb.hasFocus() and panel._cheat_enabled:
            continue
        new_val = data[idx]
        if sb.value() != new_val:
            sb.blockSignals(True)
            sb.setValue(new_val)
            sb.blockSignals(False)

    STR, INT, WIL, AGI, SPD, END, PER, LUC = data

    # Damage はメモリに直接 i16 で保存されているのでそれを優先。
    # 失敗時は公式 (calc_damage_bonus) でフォールバック。
    try:
        d_raw = panel._analyzer.read_bytes(panel._anchor + OFF_DAMAGE_I16, 2)
        damage = d_raw[0] | (d_raw[1] << 8)
        if damage & 0x8000:
            damage -= 0x10000
    except OSError:
        damage = calc_damage_bonus(STR)
    panel._derived["damage"].setText(_signed(damage))
    panel._derived["max_kilos"].setText(str(calc_max_kilos(STR)))
    panel._derived["magic_def"].setText(_signed(calc_magic_defense(WIL)))
    bth = calc_bonus_to_hit(AGI)
    panel._derived["to_hit"].setText(_signed(bth))
    panel._derived["to_defend"].setText(_signed(bth))
    bh = calc_bonus_to_health(END)
    panel._derived["health"].setText(_signed(bh))
    panel._derived["heal_mod"].setText(_signed(bh))
    panel._derived["charisma"].setText(_signed(calc_bonus_to_hit(PER)))

    # 常時 MAX 書込みの権限事前ガード。cheat 親 ON + いずれかの常時 MAX が
    # 有効なのに書込み不可なら、毎 poll の write 失敗を避けつつ権限エラーを表示。
    _always_max_on = (panel._health_max_enabled or panel._spell_max_enabled
                      or panel._fatigue_max_enabled)
    _cheat_can_write = bool(getattr(panel._analyzer, "can_write", False))
    if _always_max_on and not _cheat_can_write:
        panel._cheat_note_lbl.setText(i18n.tr("status.no_write_permission"))
        panel._cheat_note_lbl.setVisible(True)

    # 呪文ポイント（メモリから直接）
    try:
        sp_curr = panel._read_u16(panel._anchor + OFF_SPELL_PTS_CURR)
        sp_max  = panel._read_u16(panel._anchor + OFF_SPELL_PTS_MAX)
        # 呪文ポイント常時 MAX — curr < max なら max に書き戻し (cheat 親のみで有効)
        if (panel._spell_max_enabled and _cheat_can_write
                and sp_curr < sp_max and sp_max > 0):
            try:
                panel._analyzer.write_bytes(
                    panel._anchor + OFF_SPELL_PTS_CURR,
                    bytes([sp_max & 0xFF, (sp_max >> 8) & 0xFF])
                )
                sp_curr = sp_max
            except (OSError, AttributeError):
                pass
        panel._derived["spell_pts"].setText(f"{sp_curr}/{sp_max}")
    except OSError:
        panel._derived["spell_pts"].setText(UNKNOWN)

    # BONUS PTS: memory +0x129C (u8) から直読み
    # chargen 中または bonus_screen 中のみ意味あり（それ以外はゴミ値）
    # フォーカス中はユーザー編集中なので上書きしない。
    if panel._chargen_mode or panel._is_bonus_screen:
        try:
            bonus = panel._analyzer.read_bytes(panel._anchor + OFF_BONUS_PTS_U8, 1)[0]
            if not panel._bp_spin.hasFocus():
                panel._bp_spin.blockSignals(True)
                panel._bp_spin.setValue(bonus)
                panel._bp_spin.blockSignals(False)
        except OSError:
            pass

    # 下部ステータス
    try:
        hc = panel._read_u16(panel._anchor + OFF_HEALTH_CURR_U16)
        hm = panel._read_u16(panel._anchor + OFF_HEALTH_MAX_U16)
        # 体力常時 MAX — HP curr < max なら max に書き戻し (cheat 親のみで有効)
        if (panel._health_max_enabled and _cheat_can_write
                and hc < hm and hm > 0):
            try:
                panel._analyzer.write_bytes(
                    panel._anchor + OFF_HEALTH_CURR_U16,
                    bytes([hm & 0xFF, (hm >> 8) & 0xFF])
                )
                hc = hm
            except (OSError, AttributeError):
                pass
        # ボーナス画面中のみ HP curr = HP max として表示（ゲーム UI に合わせる）
        # Arena のレベルアップでは UI 上 "max/max" 表示となるが、メモリ +0x1FD は
        # 戦闘終了時のダメージ残値のまま（ゲーム側 UI は別途リストア表示している）。
        # bonus_screen を抜けるとゲーム表示も実 curr 値に戻る（ゲーム本体の挙動）。
        # この workaround はあくまで bonus_screen 期間中の表示同期目的。
        if panel._is_bonus_screen and hm > 0:
            hc = hm
        panel._stats["hp"].setText(f"{hc}/{hm}")
    except OSError:
        panel._stats["hp"].setText(UNKNOWN)

    # Fatigue: max = STR + END（確認済み）。
    # curr は anchor+0x201 の u16 LE 固定小数点（内部スケール = fat_max_256 × 64）。
    # formula: round((u16 >> 6) * 100 / 256)
    #   u16 >> 6 で 256 スケール値に戻し、scale256To100 と同じ変換（round）を適用。
    #   全 7 実測点で一致確認。
    # chargen 中は current = max。
    fat_max_256 = raw_data[0] + raw_data[5]  # STR_256 + END_256（normal-play は常に 256 スケール）
    fat_max = calc_max_stamina(STR, END)
    if panel._chargen_mode:
        panel._stats["fatigue"].setText(f"{fat_max}/{fat_max}")
    else:
        try:
            u16 = panel._read_u16(panel._anchor + OFF_FATIGUE_U16)
            # 疲労常時 MAX — 内部固定小数点の最大値 (= fat_max_256 << 6) に
            # 書き戻す (cheat 親のみで有効)。bonus_screen 中は raw_data が
            # 0-100 直値で fat_max_256 が誤るため書込みしない (normal-play 専用)。
            if (panel._fatigue_max_enabled and _cheat_can_write
                    and not panel._is_bonus_screen and fat_max_256 > 0):
                fat_u16_max = min(0xFFFF, fat_max_256 << 6)
                if u16 < fat_u16_max:
                    try:
                        panel._analyzer.write_bytes(
                            panel._anchor + OFF_FATIGUE_U16,
                            bytes([fat_u16_max & 0xFF,
                                   (fat_u16_max >> 8) & 0xFF]))
                        u16 = fat_u16_max
                    except (OSError, AttributeError):
                        pass
            fat_curr = round((u16 >> 6) * 100 / 256)
            panel._stats["fatigue"].setText(f"{fat_curr}/{fat_max}")
        except OSError:
            panel._stats["fatigue"].setText(f"—/{fat_max}")

    # Gold: 仮位置 +0x220 u16
    try:
        gold = panel._read_u16(panel._anchor + OFF_GOLD_U16)
        # 妥当性チェック: 0..65535 だが極端に大きい値は誤検出と判定
        if 0 <= gold <= 50000:
            panel._stats["gold"].setText(str(gold))
        else:
            panel._stats["gold"].setText(UNKNOWN)
    except OSError:
        panel._stats["gold"].setText(UNKNOWN)

    # Level: +0x1AA (u8) = Level - 1
    # chargen 中は +0x1AA が未確定なので 1 固定表示
    current_level: Optional[int] = None
    if panel._chargen_mode:
        panel._stats["level"].setText("1")
        current_level = 1
    else:
        try:
            lvl_byte = panel._analyzer.read_bytes(panel._anchor + OFF_LEVEL_U8, 1)[0]
            lvl = lvl_byte + 1   # 内部 0-indexed → 表示 1-indexed
            if 1 <= lvl <= 50:
                panel._stats["level"].setText(str(lvl))
                current_level = lvl
            else:
                panel._stats["level"].setText(UNKNOWN)
        except OSError:
            panel._stats["level"].setText(UNKNOWN)

    # Experience @ +0x5AD (u32 LE)
    # 通常プレイ時は次レベル必要経験値も併記する（"{現在値} / {次レベル閾値}"）。
    # 次レベル閾値は classes.json id（クラス種別）+ 現在レベルから算出。
    try:
        xp_raw = panel._analyzer.read_bytes(panel._anchor + OFF_EXP_U32, 4)
        xp = xp_raw[0] | (xp_raw[1] << 8) | (xp_raw[2] << 16) | (xp_raw[3] << 24)
        if 0 <= xp <= 99_999_999:
            next_thresh = panel._next_exp_threshold(current_level)
            if next_thresh is not None:
                panel._stats["experience"].setText(f"{xp} / {next_thresh}")
            else:
                panel._stats["experience"].setText(str(xp))
        else:
            panel._stats["experience"].setText(UNKNOWN)
    except OSError:
        panel._stats["experience"].setText(UNKNOWN)


__all__ = ["poll_attributes"]
