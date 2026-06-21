"""
assist_settings.py — 設定のロード/保存
"""

import json
import os

_DEFAULTS: dict = {
    "save_dir": "",       # Arena ゲームフォルダ（セーブファイルの在処）
    "backup_dir": "",     # バックアップ先フォルダ（空 = ツール設定ファイル横の saves_backup/）
    "capture_dir": "",    # キャプチャ保存先（空 = backup_dir を使用）
    "dosbox_conf_path": "",  # DOSBox arena.conf パス（空 = デフォルトパス使用）
    "mif_dir": "",        # MIF ファイルディレクトリ（空 = 自動モードの MIF照合無効）
    "layout_track_mode": "none",
    "layout_corner": "top_left",
    "layout_form": "form_2",
    "layout_size_w": 1920,
    "layout_size_h": 1080,
    "panel_translate_font_family_ja": "",   # 空 = アプリデフォルト
    "panel_translate_font_size_ja": 14,
    "panel_translate_font_family_en": "",
    "panel_translate_font_size_en": 12,
    "panel_translate_font_sync": False,     # True = 右側を左側の設定に合わせる
    "capture_delete_confirm": True,         # False = 削除前確認ダイアログを省略
    "capture_se_enabled": True,             # スクリーンショット時のシャッターSE 有効
    "capture_se_volume": 0.3,               # 0.0〜1.0（控えめデフォルト）
    "capture_se_kind": "phone_camera",      # se_<kind>.wav を使用（assets/ 配下）
                                            # 候補: phone_camera / phone_short /
                                            #       phone_double / phone_bright /
                                            #       phone_soft
    "theme": "dark",
    "ui_language": "",                      # 表示言語 BCP47 タグ。""=自動（system locale→英語既定）
    # Phase5 既定 flip（挙動変更）。True = 起動時に
    # 公開 v2 runtime を有効化（localpack がある場合のみ・無ければ v1 継続）。対象カテゴリは
    # i18n_v2_categories 未指定時に検証済み安全 enable-set（PHASE5_ENABLE_SET 13-set）
    # のみ。live_surface/partial は含めない（test_phase5_enable_integration 保証）。
    "i18n_v2_runtime": True,
    "i18n_v2_categories": None,             # None=既定で 13-set。明示 list 指定で上書き可。
    "always_on_top": False,
    "auto_backup_before_restore": True,
    "window_geometry": "",
    "settings_dialog_geometry": "",         # 設定ダイアログの位置・サイズ (Base64 QByteArray)
    "poll_interval_ms": 100,                # 通常 poll 間隔。短命メッセージ取得のため 100ms 既定
    # 接続バー表示の ON/OFF
    "show_recognition_screen": True,        # 認識画面の名前 (接続中文言の screen 部分)
    "show_img_info": True,                  # IMG: 情報 (anchor_lbl)
    "show_version": True,                   # バージョン表示 (接続バー右 + ステータスバー)
    # 翻訳タブ拡張設定 (ハードコード解消)
    "translate_tab_emulate_panel_hidden": False,  # 翻訳パネル表示中でもタブをパネル非表示時挙動で動かす検証用設定
    "cheat_enabled": False,                 # チートタブの親スイッチ。サブ設定が両方 OFF なら何も変えない
    "cheat_consent_acknowledged": False,    # チート有効化の初回確認に同意済み (はい選択後 True・以後は再確認しない)
    "cheat_status_change": False,           # True かつ cheat_enabled ON で能力値書き換え可
    "cheat_reveal_map": False,              # True かつ cheat_enabled ON でマップを全表示 (= AUTOMAP cache を直接描画)
    "map_wall_line_of_sight": False,        # マップでの壁の見通し。False = 未確認領域への reveal を壁でブロック (= マップに記録した分は維持)
    "map_show_unexplored_floor": False,     # False = 判明済 cell だけ床表示。True = canvas widget 全体を巻物地色化
    "map_center_on_player": True,           # True = キャラ移動でキャラ中心追従、停止中は自由パン
    "map_show_grid": True,                  # True = 判明 cell の境界にグリッド線
    "map_show_chunk_grid": True,            # True = フィールドで chunk(64) 境界を強調線表示
    "map_show_chunk_coords": True,          # True = フィールドで各 chunk の座標を表示
    "map_show_recenter_lines": False,       # True = チャンク中央の4分割線(2×2窓の再センタ境界)を破線表示。既定OFF(任意ON)
    "map_chunk_coord_font_size": 10,        # チャンク座標ラベルのフォントサイズ(pt)
    "wilderness_compact_view": False,       # [非推奨・後方互換] 旧フィールド簡潔表示。新設定 wild_* へ移行
    # フィールド(C3)マップの拡張表示。master が OFF（またはマスター ON でも全項目 OFF）の
    # 場合はゲーム自動マップと同一表示になる。各項目の実効値 = master AND 個別。
    # ※ クリプト/塔/ダンジョン入口(赤)はゲームでも表示されるため、拡張に関わらず常時赤。
    "map_extended_display": True,           # マスター: フィールド拡張表示の有効/無効
    "wild_distinguish_road": True,          # ON = 道(通行可)を別色、建物/壁(通行不可)と区別。OFF = 同色(ゲーム同様)
    "wild_show_edge": True,                 # ON = 壁の輪郭(edge voxel)を描画。OFF = 非表示(ゲーム同様)
    "wild_distinguish_edge": True,          # ON = フェンス/生垣/庭を接続線で区別(壁の輪郭の下位)。OFF = 一律 edge 塗り
    "wild_show_crops": True,                # ON = 作物(トウモロコシ/畑)を作物色で塗り＋マーク表示。OFF = 壁色塗り
    "wild_show_all_entrances": True,        # ON = 家/酒場/神殿の入口も赤表示(ゲームは非表示)。OFF = ゲーム同様(クリプト/塔/ダンジョンのみ赤)
    "wild_show_static_flats": False,        # ON = 木/茂み/岩/墓/廃墟等の地物を簡略マークで表示。既定OFF(数が多く地図が見づらいため任意ON)
    "translate_fallback_screen": "map",     # 翻訳情報なし時に翻訳タブ全域に表示する画面: "map" / "status" / "none"
    # 常時 MAX 系チート。cheat_enabled (親) ON のみで有効 = ステータス変更 ON は不要。
    # ON の間、毎 poll で現在値 < 最大値なら最大値に書き戻す。
    "cheat_health_max": False,              # 体力 (HP) 常時 MAX
    "cheat_fatigue_max": False,             # 疲労 (Fatigue) 常時 MAX
    "cheat_spell_max": False,               # 呪文ポイント (Spell Pts) 常時 MAX
    "keep_trigger_on_panel": False,         # True = トリガー/オブジェクト対話メッセージを次のメッセージまで表示し続ける
    # chargen 時のクラスインデックス（anchor+0x217）→ canonical 英名。
    # chargen で class が判明するたびに自動で蓄積される。
    # 確認済み: 6=Healer, 12=Archer
    "arena_class_id_map": {
        "6":  "Healer",
        "12": "Archer",
    },
    # 通常プレイ時のクラスインデックス（anchor+0x1A9）→ canonical 英名。
    # chargen IDとは異なるエンコーディング。
    # 仮説: 36=Healer（1点観測）
    "arena_play_class_id_map": {
        "36": "Healer",
    },
    # アイテム一覧 列0 装備状態マーク（各 1 文字、設定で変更可）
    "equipment_mark_equipped":     "Ｅ",
    "equipment_mark_equippable":   "",
    "equipment_mark_unequippable": "✕",
    # アイテム一覧 列表示 ON/OFF（True=表示）
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
    # ── 読み上げ(TTS) Phase1 ──────────────────────────
    "tts_enabled":   False,                 # 読み上げ全体の ON/OFF
    "tts_engine":    "sapi5",               # 読み上げエンジン "sapi5" / "voicevox"
    "tts_voice":     "",                    # SAPI 音声の説明文字列（"" = 既定）
    "tts_vv_speaker": 0,                    # VOICEVOX スタイル id（キャラ＋スタイルで一意）
    "tts_rate":      0,                     # 速度 SAPI Rate -10..10
    "tts_volume":    100,                   # 音量 0..100
    "tts_interrupt": True,                  # True=切り上げ ON（表示切替で前を中止）
    # 読み上げ対象は意味ベース2分類（状況説明／会話）。システム/メニューは
    # 発生源が役割を宣言しない＝構造的に対象外（除外一覧不要・誤読事故が起きない）。
    "tts_target_situation":    True,        # 状況説明（トリガー/入店/出来事/各種ダイアログ）
    "tts_target_conversation": True,        # 会話（NPC応答/店主のセリフ/宮殿/価格交渉応答）
    "tts_speaker_icon": False,              # テキスト横スピーカーアイコン表示（Phase3）
    # キャラクター名の読み替え（読み上げのみ。表示/ログは元の名前のまま）。
    # 名前はゲーム内データから自動取得。読みだけ設定する（空=無効）。
    "tts_name_reading": "",                 # 読み上げ時に使う読み（空=無効）
    # ── 翻訳ログ Phase2 ──────────────────────────────
    "log_show_original": False,             # ログに原文も併記（False=訳のみ）
    "log_show_datetime": True,              # ログに記録日時を表示
    "log_datetime_format": "yyyy/MM/dd(aaa) HH:mm:ss",  # 日時表示フォーマット
    "log_max_entries": 2000,                # ログ保存上限（件・超過は古い順に切捨）
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
