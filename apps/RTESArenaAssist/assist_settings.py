
import json
import os

_DEFAULTS: dict = {
    "save_dir": "",
    "backup_dir": "",
    "capture_dir": "",
    "dosbox_conf_path": "",
    "mif_dir": "",
    "layout_track_mode": "none",
    "layout_corner": "top_left",
    "layout_form": "form_2",
    "layout_size_w": 1920,
    "layout_size_h": 1080,
    "panel_translate_font_family_ja": "",
    "panel_translate_font_size_ja": 14,
    "panel_translate_font_family_en": "",
    "panel_translate_font_size_en": 12,
    "panel_translate_font_sync": False,
    "capture_delete_confirm": True,
    "capture_se_enabled": True,
    "capture_se_volume": 0.3,
    "capture_se_kind": "phone_camera",
    "theme": "dark",
    "ui_language": "",
    "i18n_v2_runtime": True,
    "i18n_v2_categories": None,
    "always_on_top": False,
    "auto_backup_before_restore": True,
    "window_geometry": "",
    "settings_dialog_geometry": "",
    "poll_interval_ms": 100,
    "show_recognition_screen": True,
    "show_img_info": True,
    "show_version": True,
    "translate_tab_emulate_panel_hidden": False,
    "cheat_enabled": False,
    "cheat_consent_acknowledged": False,
    "cheat_status_change": False,
    "cheat_reveal_map": False,
    "map_wall_line_of_sight": False,
    "map_show_unexplored_floor": False,
    "map_center_on_player": True,
    "map_show_grid": True,
    "map_show_chunk_grid": True,
    "map_show_chunk_coords": True,
    "map_show_recenter_lines": False,
    "map_chunk_coord_font_size": 10,
    "wilderness_compact_view": False,
    "map_extended_display": True,
    "wild_distinguish_road": True,
    "wild_show_edge": True,
    "wild_distinguish_edge": True,
    "wild_show_crops": True,
    "wild_show_all_entrances": True,
    "wild_show_static_flats": False,
    "translate_fallback_screen": "map",
    "cheat_health_max": False,
    "cheat_fatigue_max": False,
    "cheat_spell_max": False,
    "keep_trigger_on_panel": False,
    "arena_class_id_map": {
        "6":  "Healer",
        "12": "Archer",
    },
    "arena_play_class_id_map": {
        "36": "Healer",
    },
    "equipment_mark_equipped":     "Ｅ",
    "equipment_mark_equippable":   "",
    "equipment_mark_unequippable": "✕",
    "equipment_columns": {
        "equipped_mark": True,
        "identified": True,
        "slot":       True,
        "en":         True,
        "ja":         True,
        "weight":     True,
        "condition":  True,
        "effect":     True,
    },
    "tts_enabled":   False,
    "tts_engine":    "sapi5",
    "tts_voice":     "",
    "tts_vv_speaker": 0,
    "tts_rate":      0,
    "tts_volume":    100,
    "tts_interrupt": True,
    "tts_target_situation":    True,
    "tts_target_conversation": True,
    "tts_speaker_icon": False,
    "tts_name_reading": "",
    "log_show_original": False,
    "log_show_datetime": True,
    "log_datetime_format": "yyyy/MM/dd(aaa) HH:mm:ss",
    "log_max_entries": 2000,
}

_settings: dict = {}
_settings_path: str = ""


def init(base_dir: str) -> None:
    global _settings, _settings_path
    _settings_path = os.path.join(base_dir, "assist_settings.json")
    try:
        with open(_settings_path, encoding="utf-8") as f:
            loaded = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        loaded = {}
    _settings = {**_DEFAULTS, **loaded}


def get(key: str, default=None):
    return _settings.get(key, _DEFAULTS.get(key, default))


def set_val(key: str, value) -> None:
    _settings[key] = value
    _flush()


def _flush() -> None:
    if not _settings_path:
        return
    try:
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(_settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
