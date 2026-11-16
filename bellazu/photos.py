"""Photo collection helpers. Preserve galleries; never fetch images or listing APIs."""
import re
from urllib.parse import urlsplit

_REALTOR_SIZE = re.compile(r'(-m\d+)(?:[a-z]|(?:rd|od)-w\d+_h\d+)\.jpg$', re.I)


def identity(url):
    parts = urlsplit(url)
    path = _REALTOR_SIZE.sub(r'\1.jpg', parts.path) if parts.hostname and parts.hostname.endswith('rdcpix.com') else parts.path
    return parts.netloc.lower(), path, parts.query


def unique(*groups):
    out, seen = [], set()
    for group in groups:
        for url in group or []:
            if not isinstance(url, str) or urlsplit(url).scheme not in ('https', 'http'):
                continue
            key = identity(url)
            if key not in seen:
                out.append(url)
                seen.add(key)
    return out


def collection(row, detail=None, loaded=None):
    """Return (known URLs, available/advertised count); a partial row remains expandable."""
    row_urls = unique(row.get('photos'), [row.get('photo')])
    try:
        advertised = max(0, int(row.get('photo_count') or 0))
    except (ValueError, TypeError):
        advertised = 0
    if loaded is not None:
        photos = unique(loaded, row_urls)
        return photos, len(photos)
    if detail and detail.get('ok') and detail.get('photos'):
        photos = unique(detail['photos'], row_urls)
        total = max(len(photos), advertised) if detail.get('photos_complete') is not True else len(photos)
        return photos, total
    return row_urls, max(len(row_urls), advertised)
