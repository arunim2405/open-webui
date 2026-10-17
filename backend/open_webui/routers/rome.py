"""Sign-on-click links for Rome corpus documents.

Citations store ``/api/v1/rome/pdf?path=<object>&page=<n>``; this route signs a fresh
GCS URL for a signed-in user at click time and redirects to it.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from open_webui.env import (
    ROME_GCS_BUCKET,
    ROME_PDF_PREFIX,
    ROME_PDF_RATE_LIMIT_PER_MINUTE,
    ROME_PDF_SIGNER_CREDENTIALS_JSON,
    ROME_PDF_SIGNER_EMAIL,
    ROME_PDF_URL_TTL_MINUTES,
)
from open_webui.utils.auth import get_verified_user
from open_webui.utils.rate_limit import RateLimiter
from open_webui.utils.redis import get_redis_client
from open_webui.utils.rome_pdf import (
    InvalidPdfRequest,
    normalize_object_path,
    object_path_from_legacy_url,
    redirect_target,
    sign_object_url,
)

log = logging.getLogger(__name__)

router = APIRouter()

rate_limiter = RateLimiter(redis_client=get_redis_client(), limit=ROME_PDF_RATE_LIMIT_PER_MINUTE, window=60)

_UNAVAILABLE = 'This document could not be opened. Please try again later.'


def _loggable(text: str, limit: int = 300) -> str:
    """Make user-supplied text safe for a single audit log line (no newlines, bounded)."""
    return ''.join(c if c.isprintable() else '?' for c in text)[:limit]


def _done(user_id: str, path: str, outcome: str, response: Response) -> Response:
    log.info('rome_pdf user_id=%s path=%s outcome=%s', user_id, _loggable(path), _loggable(outcome))
    return response


@router.get('/pdf')
async def open_corpus_pdf(
    path: str | None = None,
    src: str | None = None,
    page: int | None = Query(None, ge=1, le=100000),
    user=Depends(get_verified_user),
) -> Response:
    requested = path or src or ''

    if rate_limiter.is_limited(f'rome_pdf:{user.id}'):
        return _done(user.id, requested, 'rate_limited', HTMLResponse('Too many requests.', status_code=429))

    if not ROME_GCS_BUCKET:
        return _done(user.id, requested, 'not_configured', HTMLResponse(_UNAVAILABLE, status_code=503))

    try:
        if bool(path) == bool(src):
            raise InvalidPdfRequest('exactly one of path or src is required')
        object_path = path if path else object_path_from_legacy_url(src, ROME_GCS_BUCKET)
        object_path = normalize_object_path(object_path, ROME_PDF_PREFIX)
    except InvalidPdfRequest as e:
        return _done(user.id, requested, f'rejected:{e}', HTMLResponse('Invalid document link.', status_code=400))

    try:
        signed_url = await asyncio.to_thread(
            sign_object_url,
            ROME_GCS_BUCKET,
            object_path,
            ROME_PDF_URL_TTL_MINUTES,
            ROME_PDF_SIGNER_EMAIL,
            ROME_PDF_SIGNER_CREDENTIALS_JSON,
        )
    except Exception as e:
        # Google auth/API errors name the cause (e.g. a missing IAM permission) and carry no tokens.
        log.warning(
            'rome_pdf signing failed for path=%s: %s: %s',
            _loggable(object_path),
            type(e).__name__,
            _loggable(str(e), 500),
        )
        return _done(user.id, object_path, 'sign_failed', HTMLResponse(_UNAVAILABLE, status_code=502))

    return _done(
        user.id,
        object_path,
        'redirect',
        RedirectResponse(redirect_target(signed_url, page), status_code=302, headers={'Cache-Control': 'no-store'}),
    )
