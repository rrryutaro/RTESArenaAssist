from __future__ import annotations
import logging
import i18n_helper as i18n
_log = logging.getLogger(__name__)
_CC_TITLE = (9, 96)
_CC_HOTKEY = (9, 192)
_CC_NORMAL = (9, 212)
_CC_NEWLINE = (13, 0)
_ITEM_STARTERS = frozenset([_CC_HOTKEY, _CC_NORMAL])

def _extract_hotkey(data: bytes) -> tuple[str, str]:
    hotkey = ''
    chars: list[str] = []
    i = 0
    while i < len(data):
        if i + 1 < len(data):
            pair = (data[i], data[i + 1])
            if pair == _CC_TITLE:
                i += 2
                continue
            if pair == _CC_HOTKEY:
                i += 2
                if i < len(data) and data[i] not in (0, 13):
                    hotkey = chr(data[i])
                    chars.append(chr(data[i]))
                    i += 1
                continue
            if pair == _CC_NORMAL:
                i += 2
                continue
            if pair == _CC_NEWLINE:
                break
        if data[i] == 0:
            break
        chars.append(chr(data[i]))
        i += 1
    return (hotkey, ''.join(chars).strip())

def _scan_items_in_range(raw: bytes, start: int, end: int) -> tuple[list[str], list[str]]:
    options: list[str] = []
    hotkeys: list[str] = []
    pos = start
    while pos < end - 1:
        pair = (raw[pos], raw[pos + 1])
        if pair in _ITEM_STARTERS:
            line_end = raw.find(b'\r\x00', pos, end)
            if line_end == -1:
                break
            hk, text = _extract_hotkey(raw[pos:line_end + 2])
            if text:
                options.append(text)
                hotkeys.append(hk)
            pos = line_end + 2
        else:
            pos += 1
    return (options, hotkeys)

def parse_menu(raw: bytes) -> dict:
    try:
        return _parse_menu_impl(raw)
    except Exception as exc:
        _log.warning('parse_menu failed: %s', exc)
        return {'parse_error': str(exc), 'raw_len': len(raw)}

def _parse_menu_impl(raw: bytes) -> dict:
    result: dict = {'title': '', 'options': [], 'hotkeys': [], 'sub_menus': [], 'place_list_where_is': [], 'place_list_work': [], 'fallback_no_rumor': '', 'fallback_not_sure': ''}
    TITLE_SEQ = bytes([_CC_TITLE[0], _CC_TITLE[1]])
    first_nl = raw.find(b'\r\x00', 0)
    if first_nl <= 0:
        _log.debug('parse_menu: main title line not found')
        return result
    main_title = raw[0:first_nl].decode('ascii', errors='replace').strip()
    result['title'] = main_title
    main_content_start = first_nl + 2
    next_section = raw.find(TITLE_SEQ, main_content_start)
    main_end = next_section if next_section != -1 else len(raw)
    opts, hks = _scan_items_in_range(raw, main_content_start, main_end)
    result['options'] = opts
    result['hotkeys'] = hks
    pos = next_section
    while pos != -1 and pos < len(raw):
        line_end = raw.find(b'\r\x00', pos)
        if line_end == -1:
            break
        sm_title = _extract_hotkey(raw[pos:line_end + 2])[1]
        sm_start = line_end + 2
        sm_next = raw.find(TITLE_SEQ, sm_start)
        sm_end = sm_next if sm_next != -1 else len(raw)
        sm_opts, sm_hks = _scan_items_in_range(raw, sm_start, sm_end)
        result['sub_menus'].append({'title': sm_title, 'options': sm_opts, 'hotkeys': sm_hks})
        pos = sm_next
    not_sure = b"I'm not sure."
    ns_pos = raw.find(not_sure)
    if ns_pos != -1:
        ns_end = raw.find(b'\x00', ns_pos)
        if ns_end == -1:
            ns_end = len(raw)
        result['fallback_not_sure'] = raw[ns_pos:ns_end].decode('ascii', errors='replace').strip()
    no_rumor = b"I don't deal in rumors"
    nr_pos = raw.find(no_rumor)
    if nr_pos != -1:
        nr_end = raw.find(b'\x00', nr_pos)
        cr_end = raw.find(b'\r', nr_pos)
        if cr_end != -1 and (nr_end == -1 or cr_end < nr_end):
            nr_end = cr_end
        if nr_end == -1:
            nr_end = len(raw)
        result['fallback_no_rumor'] = raw[nr_pos:nr_end].decode('ascii', errors='replace').strip()
    inn_marker = b'Inn\x00'
    inn_pos = raw.find(inn_marker)
    if inn_pos != -1:
        result['place_list_where_is'] = _split_nul_strings(raw, inn_pos, 128)
        second_inn = raw.find(inn_marker, inn_pos + 4)
        if second_inn != -1:
            result['place_list_work'] = _split_nul_strings(raw, second_inn, 128)
    return result

def _split_nul_strings(data: bytes, start: int, max_len: int) -> list[str]:
    results: list[str] = []
    pos = start
    end = min(start + max_len, len(data))
    while pos < end:
        nul = data.find(b'\x00', pos, end)
        chunk = data[pos:nul] if nul != -1 else data[pos:end]
        text = chunk.decode('ascii', errors='replace').strip()
        if not text:
            break
        results.append(text)
        pos = nul + 1 if nul != -1 else end
    return results
_TITLE_LEGACY_ID = 'ask_about_menu.title_ask_about.0'
_OPT_LEGACY_IDS = ('ask_about_menu.opt_who_are_you.0', 'ask_about_menu.opt_where_is.0', 'ask_about_menu.opt_rumors.0', 'ask_about_menu.opt_exit.0')
_CHROME_SURFACE_LEGACY_IDS = {'ASK ABOUT ?': 'ask_about_menu.title_ask_about.0', 'Who are you?': 'ask_about_menu.opt_who_are_you.0', 'Where is...': 'ask_about_menu.opt_where_is.0', 'Rumors': 'ask_about_menu.opt_rumors.0', 'Exit': 'ask_about_menu.opt_exit.0', 'Rumor Type': 'ask_about_menu.title_rumor_type.0', 'General': 'ask_about_menu.opt_general.0', 'Work': 'ask_about_menu.opt_work.0', 'Inn': 'ask_about_menu.place_inn.0', 'Temple': 'ask_about_menu.place_temple.0', 'Equipment Store': 'ask_about_menu.place_equipment_store.0', 'Mages Guild': 'ask_about_menu.place_mages_guild.0', 'Palace': 'ask_about_menu.place_palace.0', 'City gates': 'ask_about_menu.place_city_gates.0', 'Nearest Inn': 'ask_about_menu.place_nearest_inn.0', 'Nearest Temple': 'ask_about_menu.place_nearest_temple.0', 'Nearest Store': 'ask_about_menu.place_nearest_store.0', 'Nearest Dungeon': 'ask_about_menu.place_nearest_dungeon.0'}

def translate(en_text: str, lang: str='ja', legacy_id: str | None=None) -> str:
    s = en_text.strip()
    ja = i18n.value('ask_about_menu', s)
    if ja is not None:
        return ja
    ja = i18n.value_by_surface('ask_about_menu', s)
    if ja is not None:
        return ja
    direct_id = legacy_id or _CHROME_SURFACE_LEGACY_IDS.get(s)
    if direct_id:
        direct = i18n.text_opt(direct_id)
        if direct:
            return direct
    return en_text

def _opt_legacy_id(index: int) -> str | None:
    return _OPT_LEGACY_IDS[index] if 0 <= index < len(_OPT_LEGACY_IDS) else None

def detect_active_sub_menu_title(parsed: dict, marker: str) -> str:
    if not marker:
        return ''
    if 'parse_error' in parsed:
        return ''
    if marker in parsed.get('options', []):
        return ''
    for sub in parsed.get('sub_menus', []):
        if marker in sub.get('options', []):
            return sub.get('title', '')
    return ''

def build_panel_display_sub(parsed: dict, sub_title: str='Rumor Type', lang: str='ja') -> tuple[str, str]:
    if 'parse_error' in parsed:
        return (sub_title, translate(sub_title))
    target_sub = None
    for sub in parsed.get('sub_menus', []):
        if sub.get('title', '').strip() == sub_title:
            target_sub = sub
            break
    if target_sub is None:
        return (sub_title, translate(sub_title))
    en_lines: list[str] = [sub_title, '']
    ja_lines: list[str] = [translate(sub_title), '']
    for opt_en in target_sub.get('options', []):
        opt_ja = translate(opt_en)
        en_lines.append(opt_en)
        ja_lines.append(opt_ja)
    return ('\n'.join(en_lines), '\n'.join(ja_lines))

def build_panel_display(parsed: dict, lang: str='ja') -> tuple[str, str]:
    if 'parse_error' in parsed:
        return ('ASK ABOUT ?', translate('ASK ABOUT ?'))
    en_lines: list[str] = []
    ja_lines: list[str] = []
    title_en = parsed.get('title', 'ASK ABOUT ?')
    title_ja = translate(title_en, legacy_id=_TITLE_LEGACY_ID)
    en_lines.append(title_en)
    ja_lines.append(title_ja)
    en_lines.append('')
    ja_lines.append('')
    for i, opt_en in enumerate(parsed.get('options', [])):
        opt_ja = translate(opt_en, legacy_id=_opt_legacy_id(i))
        en_lines.append(opt_en)
        ja_lines.append(opt_ja)
    return ('\n'.join(en_lines), '\n'.join(ja_lines))

def build_display_sub(parsed: dict, sub_title: str='Rumor Type', lang: str='ja') -> tuple[str, str]:
    if 'parse_error' in parsed:
        return (sub_title, translate(sub_title))
    target_sub = None
    for sub in parsed.get('sub_menus', []):
        if sub.get('title', '').strip() == sub_title:
            target_sub = sub
            break
    if target_sub is None:
        return (sub_title, translate(sub_title))
    title_ja = translate(sub_title)
    en_lines: list[str] = [sub_title]
    ja_lines: list[str] = [title_ja]
    sm_opts = target_sub.get('options', [])
    sm_hks = target_sub.get('hotkeys', [])
    if sm_opts:
        en_lines.append('')
        ja_lines.append('')
    for j, sm_opt_en in enumerate(sm_opts):
        sm_hk = sm_hks[j] if j < len(sm_hks) else ''
        sm_opt_ja = translate(sm_opt_en)
        prefix = f'[{sm_hk}] ' if sm_hk else '  '
        en_lines.append(f'  {prefix}{sm_opt_en}')
        ja_lines.append(f'  {prefix}{sm_opt_ja}')
    return ('\n'.join(en_lines), '\n'.join(ja_lines))

def build_display(parsed: dict, lang: str='ja', include_sub: bool=True) -> tuple[str, str]:
    if 'parse_error' in parsed:
        return ('ASK ABOUT ?', '質問する')
    en_lines: list[str] = []
    ja_lines: list[str] = []
    title_en = parsed.get('title', 'ASK ABOUT ?')
    title_ja = translate(title_en, legacy_id=_TITLE_LEGACY_ID)
    en_lines.append(title_en)
    ja_lines.append(title_ja)
    options = parsed.get('options', [])
    hotkeys = parsed.get('hotkeys', [])
    if options:
        en_lines.append('')
        ja_lines.append('')
    for i, opt_en in enumerate(options):
        hk = hotkeys[i] if i < len(hotkeys) else ''
        opt_ja = translate(opt_en, legacy_id=_opt_legacy_id(i))
        prefix = f'[{hk}] ' if hk else '  '
        en_lines.append(f'  {prefix}{opt_en}')
        ja_lines.append(f'  {prefix}{opt_ja}')
    if include_sub:
        for sub in parsed.get('sub_menus', []):
            en_lines.append('')
            ja_lines.append('')
            sm_title_en = sub.get('title', '')
            sm_title_ja = translate(sm_title_en)
            en_lines.append(sm_title_en)
            ja_lines.append(sm_title_ja)
            sm_opts = sub.get('options', [])
            sm_hks = sub.get('hotkeys', [])
            if sm_opts:
                en_lines.append('')
                ja_lines.append('')
            for j, sm_opt_en in enumerate(sm_opts):
                sm_hk = sm_hks[j] if j < len(sm_hks) else ''
                sm_opt_ja = translate(sm_opt_en)
                prefix = f'[{sm_hk}] ' if sm_hk else '  '
                en_lines.append(f'  {prefix}{sm_opt_en}')
                ja_lines.append(f'  {prefix}{sm_opt_ja}')
    return ('\n'.join(en_lines), '\n'.join(ja_lines))
