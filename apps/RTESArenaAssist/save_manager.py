
import json
import os
import re
import shutil
from datetime import datetime

import save_reader

_META_FILE = "backup_meta.json"

_SLOT_EXT_RE = re.compile(r'\.0[0-9]$', re.IGNORECASE)

_SHARED_FILES = frozenset({"NAMES.DAT"})

_EXT_DATA_SUBDIR = "ext_data"



def _ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir
    return ext_data_dir()


def _ext_slot_filename(slot: int) -> str:
    from services.map_ext_store import slot_filename
    return slot_filename(slot)


def _backup_ext_data(backup_path: str, slots: list[int]) -> None:
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



def list_slots(game_dir: str) -> list[int]:
    if not os.path.isdir(game_dir):
        return []
    slots = set()
    for f in os.listdir(game_dir):
        m = _SLOT_EXT_RE.search(f)
        if m:
            slot = int(f[-1])
            slots.add(slot)
    return sorted(slots)


def _collect_save_files(game_dir: str, slots: list[int] | None = None) -> list[str]:
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



def list_backups(backup_dir: str) -> list[dict]:
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



def create_backup(
    game_dir: str,
    backup_dir: str,
    name: str = "",
    tags=None,
    memo: str = "",
    slots: list[int] | None = None,
) -> dict:
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

    slot_set = set()
    for fname in copied:
        m = _SLOT_EXT_RE.search(fname)
        if m:
            slot_set.add(int(fname[-1]))

    slot_names: dict[str, str] = {}
    for s in sorted(slot_set):
        name_val = save_reader.read_save_name(game_dir, s)
        if name_val:
            slot_names[str(s)] = name_val

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

    _backup_ext_data(backup_path, sorted(slot_set))

    return meta



def restore_backup(
    game_dir: str,
    backup_dir: str,
    backup_id: str,
    slots: list[int] | None = None,
) -> None:
    backup_path = os.path.join(backup_dir, backup_id)
    if not os.path.isdir(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_id}")

    all_backup_files = [
        f for f in os.listdir(backup_path)
        if f != _META_FILE and f != _EXT_DATA_SUBDIR
    ]

    if slots is not None:
        restore_files = [
            f for f in all_backup_files
            if _SLOT_EXT_RE.search(f) and int(f[-1]) in slots
        ]
        restore_shared = False
    else:
        restore_files = all_backup_files
        restore_shared = True

    slots_to_clean = set()
    for f in restore_files:
        m = _SLOT_EXT_RE.search(f)
        if m:
            slots_to_clean.add(int(f[-1]))

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

    os.makedirs(game_dir, exist_ok=True)
    for fname in restore_files:
        shutil.copy2(
            os.path.join(backup_path, fname),
            os.path.join(game_dir, fname),
        )

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
            game_name = backup_slot_names.get(s_key)
            if game_name is None:
                game_name = save_reader.read_save_name(backup_path, s)
            if game_name is not None:
                current_notes.setdefault(s_key, {})["game_save_name"] = game_name
        save_slot_notes(backup_dir, current_notes)
    except Exception:
        pass

    _restore_ext_data(backup_path, sorted(slots_to_clean))



def restore_backup_to_slot(
    game_dir: str,
    backup_dir: str,
    backup_id: str,
    source_slot: int,
    target_slot: int,
) -> None:
    backup_path = os.path.join(backup_dir, backup_id)
    if not os.path.isdir(backup_path):
        raise FileNotFoundError(f"バックアップが見つかりません: {backup_id}")

    src_ext_re = re.compile(rf'\.0{source_slot}$', re.IGNORECASE)
    source_files = [
        f for f in os.listdir(backup_path)
        if f != _META_FILE and src_ext_re.search(f)
    ]
    if not source_files:
        raise FileNotFoundError(
            f"バックアップ内にスロット {source_slot} のファイルが見つかりません: {backup_id}"
        )

    if os.path.isdir(game_dir):
        tgt_ext_re = re.compile(rf'\.0{target_slot}$', re.IGNORECASE)
        for f in os.listdir(game_dir):
            if tgt_ext_re.search(f):
                os.remove(os.path.join(game_dir, f))

    os.makedirs(game_dir, exist_ok=True)
    for fname in source_files:
        new_fname = fname[:-1] + str(target_slot)
        shutil.copy2(
            os.path.join(backup_path, fname),
            os.path.join(game_dir, new_fname),
        )

    try:
        with open(os.path.join(backup_path, _META_FILE), encoding="utf-8") as f:
            backup_meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        backup_meta = {}

    source_name = backup_meta.get("slot_names", {}).get(str(source_slot))
    if source_name is None:
        source_name = save_reader.read_save_name(backup_path, source_slot)
    if source_name is not None:
        save_reader.write_save_name(game_dir, target_slot, source_name)

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

    _restore_ext_data_to_slot(backup_path, source_slot, target_slot)



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



def default_backup_dir() -> str:
    from assist_settings import _settings_path
    if _settings_path:
        return os.path.join(os.path.dirname(_settings_path), "saves_backup")
    return os.path.join(os.path.expanduser("~"), "RTESArenaAssist_saves_backup")



_SLOT_NOTES_FILE = "slot_notes.json"


def load_slot_notes(backup_dir: str) -> dict:
    path = os.path.join(backup_dir, _SLOT_NOTES_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_slot_notes(backup_dir: str, notes: dict) -> None:
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(backup_dir, _SLOT_NOTES_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


def update_backup_slot_note(
    backup_dir: str, backup_id: str, slot: int, name: str, memo: str
) -> dict:
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
