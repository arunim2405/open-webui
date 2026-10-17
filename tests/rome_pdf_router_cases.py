"""Cases for GET /api/v1/rome/pdf (sign-on-click corpus links).

Run in a fresh interpreter by test_rome_pdf_router.py: importing the auth layer loads
Open WebUI's persistent config, which must not share a process with other test modules.
"""

import logging
import os
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import quote

# Importing the auth layer loads persistent config, so give it a throwaway migrated SQLite file.
# Session sharing keeps other test modules (e.g. test_signup_codes.py) on their own sessions.
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='rome-pdf-test-')
os.environ['DATABASE_URL'] = f'sqlite:///{os.environ["DATA_DIR"]}/webui.db'
os.environ['DATABASE_ENABLE_SESSION_SHARING'] = 'true'
os.environ['ENABLE_DB_MIGRATIONS'] = 'true'  # may be inherited as 'false' from the parent test process

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from open_webui.routers import rome
from open_webui.utils.auth import get_current_user
from open_webui.utils.rate_limit import RateLimiter

BUCKET = 'corpus-b'
SIGNED = f'https://storage.googleapis.com/{BUCKET}/raw/x.pdf?X-Goog-Signature=s'


class FakeSigner:
    def __init__(self, result=SIGNED, error=None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, bucket, object_path, ttl_minutes, signer_email='', credentials_json=''):
        self.calls.append(SimpleNamespace(bucket=bucket, object_path=object_path, ttl_minutes=ttl_minutes))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def signer(monkeypatch):
    fake = FakeSigner()
    monkeypatch.setattr(rome, 'sign_object_url', fake)
    monkeypatch.setattr(rome, 'ROME_GCS_BUCKET', BUCKET)
    monkeypatch.setattr(rome, 'ROME_PDF_PREFIX', 'raw/')
    monkeypatch.setattr(rome, 'ROME_PDF_URL_TTL_MINUTES', 2880)
    monkeypatch.setattr(rome, 'rate_limiter', RateLimiter(redis_client=None, limit=60, window=60))
    RateLimiter._memory_store.clear()
    return fake


def make_client(role='user', signed_in=True):
    app = FastAPI()
    app.include_router(rome.router, prefix='/api/v1/rome')
    if signed_in:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id='u1', role=role)
    return TestClient(app, follow_redirects=False)


def get(url, **kw):
    return make_client(**kw).get(url)


def test_valid_path_redirects_to_signed_url_with_page(signer):
    r = get('/api/v1/rome/pdf?path=raw/x.pdf&page=12')
    assert r.status_code == 302
    assert r.headers['location'] == f'{SIGNED}#page=12'
    assert signer.calls[0].bucket == BUCKET and signer.calls[0].ttl_minutes == 2880


def test_no_page_no_fragment(signer):
    assert '#' not in get('/api/v1/rome/pdf?path=raw/x.pdf').headers['location']


def test_redirect_is_not_cacheable(signer):
    assert get('/api/v1/rome/pdf?path=raw/x.pdf').headers['cache-control'] == 'no-store'


def test_signed_out_is_401(signer):
    assert get('/api/v1/rome/pdf?path=raw/x.pdf', signed_in=False).status_code == 401
    assert signer.calls == []


def test_pending_user_is_401(signer):
    assert get('/api/v1/rome/pdf?path=raw/x.pdf', role='pending').status_code == 401
    assert signer.calls == []


def test_path_outside_prefix_is_400_and_not_signed(signer):
    assert get('/api/v1/rome/pdf?path=secrets/x.pdf').status_code == 400
    assert signer.calls == []


@pytest.mark.parametrize('query', ['', f'?path=raw/x.pdf&src={quote(SIGNED, safe="")}'])
def test_both_or_neither_param_is_400(signer, query):
    assert get(f'/api/v1/rome/pdf{query}').status_code == 400
    assert signer.calls == []


def test_bad_page_is_rejected(signer):
    assert get('/api/v1/rome/pdf?path=raw/x.pdf&page=0').status_code == 422
    assert get('/api/v1/rome/pdf?path=raw/x.pdf&page=abc').status_code == 422


def test_legacy_src_is_resigned(signer):
    expired = f'https://storage.googleapis.com/{BUCKET}/raw/c/x.pdf?X-Goog-Expires=604800&X-Goog-Signature=old'
    r = get(f'/api/v1/rome/pdf?src={quote(expired, safe="")}&page=3')
    assert r.status_code == 302 and r.headers['location'] == f'{SIGNED}#page=3'
    assert signer.calls[0].object_path == 'raw/c/x.pdf'


def test_legacy_uploads_bucket_is_400(signer):
    old = 'https://storage.googleapis.com/stackguardian-nonprod-rome-uploads/markdown_output/x.pdf?a=1'
    assert get(f'/api/v1/rome/pdf?src={quote(old, safe="")}').status_code == 400
    assert signer.calls == []


def test_awkward_name_round_trip(signer):
    key = 'raw/rome-v/Bowel Disorders_Document C (FINAL), é.pdf'
    assert get(f'/api/v1/rome/pdf?path={quote(key, safe="")}').status_code == 302
    assert signer.calls[0].object_path == key


def test_signing_failure_is_502_without_console_link(signer):
    signer.error = RuntimeError('denied')
    r = get('/api/v1/rome/pdf?path=raw/x.pdf')
    assert r.status_code == 502
    assert 'storage.cloud.google.com' not in r.text and 'location' not in r.headers


def test_rate_limit_is_429(signer, monkeypatch):
    monkeypatch.setattr(rome, 'rate_limiter', RateLimiter(redis_client=None, limit=2, window=60))
    client = make_client()
    codes = [client.get('/api/v1/rome/pdf?path=raw/x.pdf').status_code for _ in range(3)]
    assert codes == [302, 302, 429]


def test_unconfigured_bucket_is_503(signer, monkeypatch):
    monkeypatch.setattr(rome, 'ROME_GCS_BUCKET', '')
    assert get('/api/v1/rome/pdf?path=raw/x.pdf').status_code == 503
    assert signer.calls == []


def test_log_never_contains_signed_url(signer, caplog):
    with caplog.at_level(logging.INFO, logger=rome.log.name):
        get('/api/v1/rome/pdf?path=raw/x.pdf')
    assert 'X-Goog-Signature' not in caplog.text
    assert 'user_id=u1' in caplog.text and 'outcome=redirect' in caplog.text
