"""Sign-on-click links for Rome corpus documents.

Citations store a stable ``/api/v1/rome/pdf?path=...`` link; the object is only signed
when a signed-in user clicks it. These helpers validate what may be signed.
"""

from urllib.parse import unquote, urlsplit

ALLOWED_EXTENSIONS = ('.pdf', '.md')
MAX_OBJECT_PATH_LENGTH = 1024

_PATH_STYLE_HOSTS = ('storage.googleapis.com', 'storage.cloud.google.com')
_VIRTUAL_HOST_SUFFIX = '.storage.googleapis.com'


class InvalidPdfRequest(ValueError):
    """The requested object may not be signed."""


def normalize_object_path(path: str, prefix: str) -> str:
    """Return ``path`` if it is a corpus object that may be signed, else raise InvalidPdfRequest."""
    if not path or len(path) > MAX_OBJECT_PATH_LENGTH:
        raise InvalidPdfRequest('invalid length')
    if path.startswith('/') or '\\' in path or '//' in path or '%' in path:
        raise InvalidPdfRequest('invalid characters')
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise InvalidPdfRequest('control characters')
    if '..' in path.split('/'):
        raise InvalidPdfRequest('path traversal')
    if not path.startswith(prefix):
        raise InvalidPdfRequest('outside allowed prefix')
    if not path.lower().endswith(ALLOWED_EXTENSIONS):
        raise InvalidPdfRequest('file type not allowed')
    return path


def object_path_from_legacy_url(url: str, bucket: str) -> str:
    """Extract the object key from an old signed or console GCS link to ``bucket``."""
    parts = urlsplit(url or '')
    if parts.scheme != 'https' or not bucket:
        raise InvalidPdfRequest('not an https GCS link')

    host = (parts.hostname or '').lower()
    if host in _PATH_STYLE_HOSTS:
        link_bucket, _, key = parts.path.lstrip('/').partition('/')
    elif host.endswith(_VIRTUAL_HOST_SUFFIX):
        link_bucket = host[: -len(_VIRTUAL_HOST_SUFFIX)]
        key = parts.path.lstrip('/')
    else:
        raise InvalidPdfRequest('not a GCS host')

    if link_bucket != bucket or not key:
        raise InvalidPdfRequest('not the corpus bucket')
    return unquote(key)


def redirect_target(signed_url: str, page: int | None) -> str:
    """Append ``#page=N`` so browser PDF viewers open at the cited page."""
    return f'{signed_url}#page={page}' if page else signed_url
