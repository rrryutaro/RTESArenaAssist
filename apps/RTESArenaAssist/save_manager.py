"""
save_manager.py — Arena セーブデータバックアップ管理

仕様: docs/arena_save_spec.md 参照
  - セーブファイルは拡張子 .00〜.09 でスロット番号を区別
  - 共通ファイル: NAMES.DAT
  - バックアップ先はゲームフォルダとは別フォルダ
"""

import json
import os
import re
import shutil
from datetime import datetime

import save_reader

_META_FILE = "backup_meta.json"

# スロットファイル: 拡張子 .00〜.09
_SLOT_EXT_RE = re.compile(r'\.0[0-9]$', re.IGNORECASE)

# スロット共通ファイル
_SHARED_FILES = frozenset({"NAMES.DAT"})

# 拡張データ: バックアップ folder 内に同梱するサブフォルダ名
_EXT_DATA_SUBDIR = "ext_data"


# ------------------------------------------------------------------
# 拡張データ (map_ext.0N) のバックアップ同梱・復元
# ------------------------------------------------------------------

def _ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir
    return ext_data_dir()


def _ext_slot_filename(slot: int) -> str:
    from services.map_ext_store import slot_filename
    return slot_filename(slot)


def _backup_ext_data(backup_path: str, slots: list[int]) -> None:
    """アクティブの ext_data/map_ext.0N (slots) を backup_path/ext_data/ へ複製。"""
    src_dir = _ext_data_dir()
    if not os.path.isdir(src_dir):
        return
    dest_dir = os.path.join(backup_path, _EXT_DATA_SUBDIR)
    for s in slots:
        fn = _ext_slot_filename(s)
        src = os.path.join(src_dir, fn)
        if os.path.isfile(src):
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(dest_dir, fn))


def _restore_ext_data(backup_path: str, slots: list[int]) -> None:
    """backup_path/ext_data/ の map_ext.0N (slots) をアクティブへ書き戻す。
    バックアップ側に無いスロットは復元先を削除する（= その時点で未発見状態）。"""
    src_dir = os.path.join(backup_path, _EXT_DATA_SUBDIR)
    dest_dir = _ext_data_dir()
    for s in slots:
        fn = _ext_slot_filename(s)
        src = os.path.join(src_dir, fn)
        dst = os.path.join(dest_dir, fn)
        if os.path.isfile(src):
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            try:
                os.remove(dst)
            except OSError:
                pass


def _restore_ext_data_to_slot(
    backup_path: str, source_slot: int, target_slot: int
) -> None:
    """個別リストア: backup の source_slot 拡張データを active target_slot へ。"""
    src = os.path.join(
        backup_path, _EXT_DATA_SUBDIR, _ext_slot_filename(source_slot))
    dest_dir = _ext_data_dir()
    dst = os.path.join(dest_dir, _ext_slot_filename(target_slot))
    if os.path.isfile(src):
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        try:
            os.remove(dst)
        except OSError:
            pass


# ------------------------------------------------------------------
# ゲームフォルダ操作
# ------------------------------------------------------------------

def list_slots(game_dir: str) -> list[int]:
    """ゲームフォルダ内に存在するセーブスロット番号のリストを返す (0〜9)。"""
    if not os.path.isdir(game_dir):
        return []
    slots = set()
    for f in os.listdir(game_dir):
        m = _SLOT_EXT_RE.search(f)
        if m:
            slot = int(f[-1])  # 拡張子の末尾1桁がスロット番号
            slots.add(slot)
    return sorted(slots)


def _collect_save_files(game_dir: str, slots: list[int] | None = None) -> list[str]:
    """
    ゲームフォルダからバックアップ対象ファイル名リストを返す。
    slots=None のとき全スロット対象。slots=[0,1] のときそのスロットのみ。
    NAMES.DAT は常に含む（存在する場合）。
    """
    if not os.path.isdir(game_dir):
        raise FileNotFoundError(f"ゲームフォルダが見つかりません: {game_dir}")

    targets = []
    for f in os.listdir(game_dir):
        upper = f.upper()
        if upper in _SHARED_FILES:
            targets.append(f)
            continue
        m = _SLOT_EXT_RE.search(f)
        if m:
            slot = int(f[-1])
            if slots is None or slot in slots:
                targets.append(f)

    if not targets:
        raise FileNotFoundError(
            f"セーブファイル (*.00〜*.09) が見つかりません: {game_dir}"
        )
    return sorted(targets)


# ------------------------------------------------------------------
# バックアップ一覧
# ------------------------------------------------------------------

def list_backups(backup_dir: str) -> list[dict]:
    """バックアップ一覧を新しい順で返す。"""
    if not os.path.isdir(backup_dir):
        return []
    result = []
    for entry in sorted(os.listdir(backup_dir), reverse=True):
        meta_path = os.path.join(backup_dir, entry, _META_FILE)
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    result.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return result


# ------------------------------------------------------------------
# バックアップ作成
# ------------------------------------------------------------------

def create_backup(
    game_dir: str,
    backup_dir: str,
    name: str = "",
    tags=None,
    memo: str = "",
    slots: list[int] | None = None,
) -> dict:
    """
    game_dir のセーブファイルを backup_dir にコピーする。
    slots=None のとき全スロット対象。
    """
    if tags is None:
        tags = []

    save_files = _collect_save_files(game_dir, slots)

    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    display_name = name.strip() or ts
    folder_name = f"{ts}_{display_name}" if name.strip() else ts
    backup_path = os.path.join(backup_dir, folder_name)
    os.makedirs(backup_path, exist_ok=True)

    copied = []
    for fname in save_files:
        shutil.copy2(
            os.path.join(game_dir, fname),
            os.path.join(backup_path, fname),
        )
        copied.append(fname)

    # 含まれるスロット番号を解析
    slot_set = set()
    for fname in copied:
        m = _SLOT_EXT_RE.search(fname)
        if m:
            slot_set.add(int(fname[-1]))

    # バックアップ時点のスロット表示名を記録
    slot_names: dict[str, str] = {}
    for s in sorted(slot_set):
        name_val = save_reader.read_save_name(game_dir, s)
        if name_val:
            slot_names[str(s)] = name_val

    # バックアップ時点のユーザーラベル・メモを取り込む
    current_notes = load_slot_notes(backup_dir)
    slot_notes_capture: dict[str, dict] = {}
    for s in sorted(slot_set):
        note = current_notes.get(str(s), {})
        if note.get("name") or note.get("memo"):
            slot_notes_capture[str(s)] = {
                "name": note.get("name", ""),
                "memo": note.get("memo", ""),
            }

    meta = {
        "id": folder_name,
        "datetime": now.isoformat(timespec="seconds"),
        "name": display_name,
        "tags": tags,
        "memo": memo,
        "slots": sorted(slot_set),
        "slot_names": slot_names,
        "slot_notes": slot_notes_capture,
        "files": copied,
    }
    with open(os.path.join(backup_path, _META_FILE), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 拡張データ (map_ext.0N) を ext_data/ サブフォルダへ同梱
    _backup_ext_data(backup_path, sorted(slot_set))

    return meta


# ------------------------------------------------------------------
# リストア
# ------------------------------------------------------------------

def restore_backup(
    game_dir: str,
    backup_dir: str,
    backup_id: str,
    slots: list[int] | None = None,
) -> None:
    """
    バックアップを game_dir に復元する。

    slots=None のとき全ファイルを復元する。
    slots=[0,1] のとき指定スロットのファイルのみ復元する（NAMES.DAT は除外）。
    復元前に対象スロットの既存ファイルを削除する（余剰ファイル除去のため）。
    """
    backup_path = os.path.join(backup_dir, backup_id)
    if not os.path.isdir(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_id}")

    # バックアップに含まれる全ファイルを列挙（メタ・拡張データフォルダ除外）
    all_backup_files = [
        f for f in os.listdir(backup_path)
        if f != _META_FILE and f != _EXT_DATA_SUBDIR
    ]

    if slots is not None:
        # 部分リストア: 指定スロットのスロットファイルのみ（NAMES.DAT はスキップ）
        restore_files = [
            f for f in all_backup_files
            if _SLOT_EXT_RE.search(f) and int(f[-1]) in slots
        ]
        restore_shared = False
    else:
        # 全リストア: NAMES.DAT を含む全ファイル
        restore_files = all_backup_files
        restore_shared = True

    # 対象スロット番号を特定
    slots_to_clean = set()
    for f in restore_files:
        m = _SLOT_EXT_RE.search(f)
        if m:
            slots_to_clean.add(int(f[-1]))

    # ゲームフォルダの既存ファイルを削除
    if os.path.isdir(game_dir):
        for f in os.listdir(game_dir):
            upper = f.upper()
            m = _SLOT_EXT_RE.search(f)
            if m and int(f[-1]) in slots_to_clean:
                os.remove(os.path.join(game_dir, f))
            elif restore_shared and upper in _SHARED_FILES and any(
                fi.upper() in _SHARED_FILES for fi in restore_files
            ):
                os.remove(os.path.join(game_dir, f))

    # ファイルをコピー
    os.makedirs(game_dir, exist_ok=True)
    for fname in restore_files:
        shutil.copy2(
            os.path.join(backup_path, fname),
            os.path.join(game_dir, fname),
        )

    # リストアしたスロットのユーザーラベル・メモをバックアップのものに差し替える
    # 併せて game_save_name もバックアップ時点の slot_names で更新
    try:
        with open(os.path.join(backup_path, _META_FILE), encoding="utf-8") as f:
            backup_meta = json.load(f)
        backup_slot_notes = backup_meta.get("slot_notes", {})
        backup_slot_names = backup_meta.get("slot_names", {})
        current_notes = load_slot_notes(backup_dir)
        for s in slots_to_clean:
            s_key = str(s)
            if s_key in backup_slot_notes:
                current_notes[s_key] = dict(backup_slot_notes[s_key])
            else:
                current_notes.pop(s_key, None)
            # game_save_name はバックアップ時点の名前で更新
            game_name = backup_slot_names.get(s_key)
            if game_name is None:
                game_name = save_reader.read_save_name(backup_path, s)
            if game_name is not None:
                current_notes.setdefault(s_key, {})["game_save_name"] = game_name
        save_slot_notes(backup_dir, current_notes)
    except Exception:
        pass

    # 拡張データ (map_ext.0N) を復元
    _restore_ext_data(backup_path, sorted(slots_to_clean))


# ------------------------------------------------------------------
# 個別リストア（任意位置）
# ------------------------------------------------------------------

def restore_backup_to_slot(
    game_dir: str,
    backup_dir: str,
    backup_id: str,
    source_slot: int,
    target_slot: int,
) -> None:
    """
    バックアップの source_slot をゲーム側 target_slot に復元する（個別リストア任意位置）。

    - スロットファイル (*.0N): ファイル名末尾の slot 番号を target_slot に書き換えてコピー
    - NAMES.DAT: ゲーム側の target_slot エントリのみ、バックアップ側 source_slot の名前で書き換え
    - slot_notes.json: バックアップの source_slot の slot_notes を target_slot に上書き
                       game_save_name もバックアップ source の名前で同期
    """
    backup_path = os.path.join(backup_dir, backup_id)
    if not os.path.isdir(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_id}")

    # バックアップ内 source_slot のスロットファイル一覧
    src_ext_re = re.compile(rf'\.0{source_slot}$', re.IGNORECASE)
    source_files = [
        f for f in os.listdir(backup_path)
        if f != _META_FILE and src_ext_re.search(f)
    ]
    if not source_files:
        raise FileNotFoundError(
            f"バックアップ内にスロット {source_slot} のファイルが見つかりません: {backup_id}"
        )

    # ゲーム側 target_slot の既存スロットファイルを削除
    if os.path.isdir(game_dir):
        tgt_ext_re = re.compile(rf'\.0{target_slot}$', re.IGNORECASE)
        for f in os.listdir(game_dir):
            if tgt_ext_re.search(f):
                os.remove(os.path.join(game_dir, f))

    # スロットファイルをコピー（拡張子末尾を target_slot に置換）
    os.makedirs(game_dir, exist_ok=True)
    for fname in source_files:
        new_fname = fname[:-1] + str(target_slot)
        shutil.copy2(
            os.path.join(backup_path, fname),
            os.path.join(game_dir, new_fname),
        )

    # バックアップメタ読み込み
    try:
        with open(os.path.join(backup_path, _META_FILE), encoding="utf-8") as f:
            backup_meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        backup_meta = {}

    # NAMES.DAT の target_slot エントリをバックアップ側 source_slot の名前で書き換え
    source_name = backup_meta.get("slot_names", {}).get(str(source_slot))
    if source_name is None:
        source_name = save_reader.read_save_name(backup_path, source_slot)
    if source_name is not None:
        save_reader.write_save_name(game_dir, target_slot, source_name)

    # slot_notes.json の target_slot をバックアップ側 source_slot のノートで上書き
    try:
        backup_slot_notes = backup_meta.get("slot_notes", {})
        current_notes = load_slot_notes(backup_dir)
        src_key = str(source_slot)
        tgt_key = str(target_slot)
        if src_key in backup_slot_notes:
            current_notes[tgt_key] = dict(backup_slot_notes[src_key])
        else:
            current_notes.pop(tgt_key, None)
        if source_name is not None:
            current_notes.setdefault(tgt_key, {})["game_save_name"] = source_name
        save_slot_notes(backup_dir, current_notes)
    except Exception:
        pass

    # 拡張データ (map_ext.0N) を source→target で復元
    _restore_ext_data_to_slot(backup_path, source_slot, target_slot)


# ------------------------------------------------------------------
# 削除・更新
# ------------------------------------------------------------------

def delete_backup(backup_dir: str, backup_id: str) -> None:
    backup_path = os.path.join(backup_dir, backup_id)
    if os.path.isdir(backup_path):
        shutil.rmtree(backup_path)


def update_meta(
    backup_dir: str, backup_id: str, name: str, tags: list, memo: str
) -> dict:
    backup_path = os.path.join(backup_dir, backup_id)
    meta_path = os.path.join(backup_path, _META_FILE)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["name"] = name.strip()
    meta["tags"] = tags
    meta["memo"] = memo
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


# ------------------------------------------------------------------
# デフォルトパス
# ------------------------------------------------------------------

def default_backup_dir() -> str:
    """バックアップ先デフォルトパスを返す。"""
    from assist_settings import _settings_path
    if _settings_path:
        return os.path.join(os.path.dirname(_settings_path), "saves_backup")
    return os.path.join(os.path.expanduser("~"), "RTESArenaAssist_saves_backup")


# ------------------------------------------------------------------
# スロットメモ（ツール内表示用ラベル・メモ）
# ------------------------------------------------------------------

_SLOT_NOTES_FILE = "slot_notes.json"


def load_slot_notes(backup_dir: str) -> dict:
    """
    スロットメモを読み込む。

    Returns
    -------
    dict: {"0": {"name": str, "memo": str}, "1": {...}, ...}
    """
    path = os.path.join(backup_dir, _SLOT_NOTES_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_slot_notes(backup_dir: str, notes: dict) -> None:
    """スロットメモを保存する。"""
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(backup_dir, _SLOT_NOTES_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def update_backup_slot_note(
    backup_dir: str, backup_id: str, slot: int, name: str, memo: str
) -> dict:
    """
    バックアップメタの slot_notes を更新して、更新後のメタ dict を返す。

    name / memo がともに空のときはそのスロットのエントリを削除する。
    """
    backup_path = os.path.join(backup_dir, backup_id)
    meta_path = os.path.join(backup_path, _META_FILE)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    slot_notes = meta.setdefault("slot_notes", {})
    s_key = str(slot)
    if name or memo:
        slot_notes[s_key] = {"name": name, "memo": memo}
    else:
        slot_notes.pop(s_key, None)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta
