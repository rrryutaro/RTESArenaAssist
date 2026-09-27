from __future__ import annotations
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Callable, Optional
PACK_FORMAT = 2
SOURCE_LANG = 'en'
DOCS_PDFS: dict[str, tuple[str, str]] = {'player_guide': ('Player Guide.pdf', '084d850d63fa3d43faff96a324b3602ade8a36505460c475f4246f87954a66b2'), 'quick_reference': ('Quick Reference Card.pdf', 'df42a63ee426bdaea8735c8a880dd86dba386b34996057b9a10ad7bcd871c97a')}
_LANG_RE = re.compile('^[a-z]{2}(-[A-Za-z]{2,4})?$')
_DATE_RE = re.compile('^\\d{4}-\\d{2}-\\d{2}$')
_SHA_RE = re.compile('^[0-9a-f]{64}$')
_CHAPTER_RE = re.compile('^\\d\\d_[a-z_]+$')
_IMAGE_RE = re.compile('^\\d\\d_[a-z_]+_p\\d+_img\\d+\\.(png|jpeg)$')
_MAX_PACK_BYTES = 16 * 1024 * 1024
_MAX_HTML_BYTES = 4 * 1024 * 1024
_MAX_CHAPTERS = 64
_MAX_IMAGES = 512
IMAGES_OK = 'ok'
IMAGES_NO_PDF = 'no_pdf'
IMAGES_PDF_MISMATCH = 'pdf_mismatch'
ProgressFn = Optional[Callable[[str, int, int], None]]

class PackError(Exception):

    def __init__(self, code: str, detail: str='') -> None:
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code
        self.detail = detail

def pack_file_name(lang: str) -> str:
    return f'RTESArenaAssist-manual-{lang}.zip'

def offers_pack(lang: str) -> bool:
    return bool(lang) and lang != SOURCE_LANG

def user_dir() -> Optional[Path]:
    try:
        from assist_settings import _settings_path
    except Exception:
        return None
    return Path(_settings_path).parent if _settings_path else None

def manual_root() -> Optional[Path]:
    base = user_dir()
    return base / 'manual_full' if base is not None else None

def _cache_path(lang: str) -> Optional[Path]:
    root = manual_root()
    return root / pack_file_name(lang) if root is not None else None

def installed_state(lang: str) -> Optional[dict]:
    root = manual_root()
    if root is None:
        return None
    try:
        state = json.loads((root / lang / 'installed.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or state.get('format') != PACK_FORMAT:
        return None
    return state

def list_installed_docs(lang: str) -> list[tuple[str, str]]:
    state = installed_state(lang)
    root = manual_root()
    if state is None or root is None:
        return []
    out = []
    for stem in state.get('chapters', []):
        p = root / lang / f'{stem}.html'
        if is_safe_chapter(stem) and p.is_file():
            out.append((stem, str(p)))
    return out

def docs_dir() -> Optional[Path]:
    try:
        import assist_settings as settings
        cands = [settings.get('arena_dir') or '', settings.get('save_dir') or '']
    except Exception:
        return None
    for raw in cands:
        raw = raw.strip()
        if not raw:
            continue
        base = Path(raw)
        for d in (base.parent / 'Docs', base / 'Docs'):
            try:
                if d.is_dir():
                    return d
            except OSError:
                continue
    return None

def _find_pdf(name: str, sha: str) -> tuple[Optional[Path], bool]:
    d = docs_dir()
    if d is None:
        return (None, False)
    p = d / name
    if not p.is_file():
        return (None, False)
    try:
        same = hashlib.sha256(p.read_bytes()).hexdigest() == sha
    except OSError:
        return (None, False)
    return (p, same)

def find_docs_pdf(key: str) -> tuple[Optional[Path], bool]:
    name, sha = DOCS_PDFS[key]
    return _find_pdf(name, sha)

def is_safe_chapter(stem: str) -> bool:
    return bool(_CHAPTER_RE.match(stem or ''))

def is_safe_image(name: str) -> bool:
    return bool(_IMAGE_RE.match(name or ''))

def _is_int(v) -> bool:
    return isinstance(v, int) and (not isinstance(v, bool))

def _valid_image_spec(spec) -> bool:
    if not isinstance(spec, dict):
        return False
    size = spec.get('size')
    return _is_int(spec.get('page')) and spec['page'] >= 0 and _is_int(spec.get('index')) and (spec['index'] >= 0) and isinstance(spec.get('xobject'), str) and isinstance(spec.get('invert'), bool) and isinstance(size, list) and (len(size) == 2) and all((_is_int(x) and x > 0 for x in size))

def verify_pack(data: bytes) -> tuple[zipfile.ZipFile, dict]:

    def bad(detail: str) -> PackError:
        return PackError('invalid', detail)
    if not data or len(data) > _MAX_PACK_BYTES:
        raise bad('size')
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as exc:
        raise bad(str(exc)) from exc
    if not isinstance(manifest, dict) or manifest.get('format') != PACK_FORMAT:
        raise bad('format')
    lang = manifest.get('lang')
    if not isinstance(lang, str) or not _LANG_RE.match(lang) or (not offers_pack(lang)):
        raise bad('lang')
    if not isinstance(manifest.get('updated'), str) or not _DATE_RE.match(manifest['updated']):
        raise bad('updated')
    chapters = manifest.get('chapters')
    if not isinstance(chapters, list) or not chapters or len(chapters) > _MAX_CHAPTERS or (len(set(chapters)) != len(chapters)) or (not all((isinstance(s, str) and is_safe_chapter(s) for s in chapters))):
        raise bad('chapters')
    files = manifest.get('files')
    expected = {f'html/{s}.html' for s in chapters}
    if not isinstance(files, dict) or set(files) != expected:
        raise bad('files')
    if set(zf.namelist()) != expected | {'manifest.json'}:
        raise bad('members')
    for name, sha in files.items():
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            raise bad(f'sha {name}')
        info = zf.getinfo(name)
        if info.file_size > _MAX_HTML_BYTES:
            raise bad(f'size {name}')
        try:
            body = zf.read(name)
        except (zipfile.BadZipFile, OSError) as exc:
            raise bad(str(exc)) from exc
        if hashlib.sha256(body).hexdigest() != sha:
            raise bad(f'sha {name}')
        try:
            body.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise bad(f'utf-8 {name}') from exc
    images = manifest.get('images')
    if not isinstance(images, dict) or len(images) > _MAX_IMAGES or (not all((is_safe_image(n) and _valid_image_spec(s) for n, s in images.items()))):
        raise bad('images')
    pdf = manifest.get('source_pdf')
    if not isinstance(pdf, dict) or not isinstance(pdf.get('file'), str) or Path(pdf['file']).name != pdf['file'] or (not isinstance(pdf.get('sha256'), str)) or (not _SHA_RE.match(pdf['sha256'])):
        raise bad('source_pdf')
    return (zf, manifest)

def build_images(pdf_path: Path, images: dict, out_dir: Path, progress: ProgressFn=None) -> int:
    from PIL import Image, ImageOps
    from pypdf import PdfReader
    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf_path))
    total = len(images)
    written = 0
    for i, name in enumerate(sorted(images)):
        spec = images[name]
        if not 0 <= int(spec['page']) < len(reader.pages):
            continue
        page = reader.pages[int(spec['page'])]
        found = None
        page_images = list(page.images)
        for img in page_images:
            if img.name.rsplit('.', 1)[0] == spec.get('xobject'):
                found = img
                break
        if found is None and 0 <= int(spec.get('index', -1)) < len(page_images):
            found = page_images[int(spec['index'])]
        if found is None:
            continue
        pil = Image.open(io.BytesIO(found.data))
        pil.load()
        if list(pil.size) != list(spec.get('size', pil.size)):
            continue
        dest = out_dir / name
        if spec.get('invert'):
            ImageOps.invert(pil.convert('L')).save(dest, format='PNG')
        elif name.endswith('.jpeg') and found.name.lower().endswith(('.jpg', '.jpeg')):
            dest.write_bytes(found.data)
        else:
            pil.save(dest, format='PNG' if name.endswith('.png') else 'JPEG')
        written += 1
        if progress is not None:
            progress('images', i + 1, total)
    return written

def install_pack(data: bytes, expected_lang: str, progress: ProgressFn=None) -> dict:
    zf, manifest = verify_pack(data)
    lang = manifest['lang']
    if lang != expected_lang:
        raise PackError('lang', lang)
    root = manual_root()
    if root is None:
        raise PackError('write', 'settings not initialized')
    lang_dir = root / lang
    try:
        lang_dir.mkdir(parents=True, exist_ok=True)
        for stem in manifest['chapters']:
            (lang_dir / f'{stem}.html').write_bytes(zf.read(f'html/{stem}.html'))
        cache = root / pack_file_name(lang)
        if not cache.is_file() or cache.read_bytes() != data:
            cache.write_bytes(data)
    except (OSError, KeyError) as exc:
        raise PackError('write', str(exc)) from exc
    src = manifest['source_pdf']
    pdf, same = _find_pdf(src['file'], src['sha256'])
    images = manifest['images']
    written = 0
    if pdf is None:
        status = IMAGES_NO_PDF
    elif not same:
        status = IMAGES_PDF_MISMATCH
    else:
        try:
            written = build_images(pdf, images, root / 'images', progress)
        except OSError as exc:
            raise PackError('write', str(exc)) from exc
        status = IMAGES_OK if written == len(images) else IMAGES_PDF_MISMATCH
    state = {'format': PACK_FORMAT, 'lang': lang, 'updated': manifest['updated'], 'pack_sha256': hashlib.sha256(data).hexdigest(), 'chapters': list(manifest['chapters']), 'images': status, 'images_written': written, 'images_total': len(images)}
    try:
        (lang_dir / 'installed.json').write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError as exc:
        raise PackError('write', str(exc)) from exc
    return state

def import_pack_file(path, lang: str, progress: ProgressFn=None) -> dict:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise PackError('unreadable', str(exc)) from exc
    return install_pack(data, lang, progress)

def rebuild_from_cache(lang: str, progress: ProgressFn=None) -> dict:
    cache = _cache_path(lang)
    if cache is None:
        raise PackError('unreadable', 'settings not initialized')
    return import_pack_file(cache, lang, progress)
__all__ = ['PACK_FORMAT', 'SOURCE_LANG', 'DOCS_PDFS', 'PackError', 'IMAGES_OK', 'IMAGES_NO_PDF', 'IMAGES_PDF_MISMATCH', 'pack_file_name', 'offers_pack', 'user_dir', 'manual_root', 'installed_state', 'list_installed_docs', 'docs_dir', 'find_docs_pdf', 'is_safe_chapter', 'is_safe_image', 'verify_pack', 'build_images', 'install_pack', 'import_pack_file', 'rebuild_from_cache']
