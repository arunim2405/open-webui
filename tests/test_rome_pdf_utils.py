"""Unit tests for sign-on-click corpus PDF helpers (validation, legacy links, signing)."""

import datetime as dt
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# Configure an isolated in-memory backend BEFORE any open_webui import.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['ENABLE_DB_MIGRATIONS'] = 'false'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from open_webui.utils.rome_pdf import (
    InvalidPdfRequest,
    normalize_object_path,
    object_path_from_legacy_url,
    redirect_target,
    sign_object_url,
)

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
P = 'raw/'
B = 'stackguardian-nonprod-rome-corpus'


def load_env_value(name: str) -> str:
    """Import open_webui.env in a fresh interpreter (no ROME_* vars set) and print one setting."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('ROME_')}
    result = subprocess.run(
        [sys.executable, '-c', f'from open_webui import env; print(env.{name})'],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_normalize_accepts_pdf():
    assert normalize_object_path('raw/rome-v/a b (1).pdf', P) == 'raw/rome-v/a b (1).pdf'


def test_normalize_accepts_literal_percent_in_name():
    assert normalize_object_path('raw/rome-v/100% response.pdf', P) == 'raw/rome-v/100% response.pdf'


def test_normalize_accepts_markdown():
    assert normalize_object_path('raw/rome-v/notes.md', P) == 'raw/rome-v/notes.md'


@pytest.mark.parametrize(
    'bad',
    [
        '',
        'other/x.pdf',
        '/raw/x.pdf',
        'raw/../secret.pdf',
        'raw/a/../../x.pdf',
        'raw\\x.pdf',
        'raw//x.pdf',
        'raw/x.exe',
        'raw/x.pdf\n',
        'raw/' + 'a' * 1100 + '.pdf',
    ],
)
def test_normalize_rejects(bad):
    with pytest.raises(InvalidPdfRequest):
        normalize_object_path(bad, P)


def test_legacy_path_style():
    url = f'https://storage.googleapis.com/{B}/raw/c/x.pdf?X-Goog-Signature=a'
    assert object_path_from_legacy_url(url, B) == 'raw/c/x.pdf'


def test_legacy_virtual_host():
    url = f'https://{B}.storage.googleapis.com/raw/c/x.pdf?X-Goog-Expires=1'
    assert object_path_from_legacy_url(url, B) == 'raw/c/x.pdf'


def test_legacy_console_host():
    url = f'https://storage.cloud.google.com/{B}/raw/c/x.pdf'
    assert object_path_from_legacy_url(url, B) == 'raw/c/x.pdf'


def test_legacy_url_decodes_object_key():
    url = f'https://storage.googleapis.com/{B}/raw/c/A%20B%20%281%29.pdf?x=1'
    assert object_path_from_legacy_url(url, B) == 'raw/c/A B (1).pdf'


@pytest.mark.parametrize(
    'bad',
    [
        'https://storage.googleapis.com/stackguardian-nonprod-rome-uploads/x.pdf?a=1',  # ZeroEntropy era: stays broken
        f'https://evil.example.com/{B}/raw/x.pdf',
        f'http://storage.googleapis.com/{B}/raw/x.pdf',
        f'https://storage.googleapis.com.evil.com/{B}/raw/x.pdf',
        'javascript:alert(1)',
        '',
    ],
)
def test_legacy_rejects(bad):
    with pytest.raises(InvalidPdfRequest):
        object_path_from_legacy_url(bad, B)


def test_redirect_target_adds_page():
    assert redirect_target('https://s/x?sig=1', 12) == 'https://s/x?sig=1#page=12'


def test_redirect_target_without_page():
    assert redirect_target('https://s/x?sig=1', None) == 'https://s/x?sig=1'


def test_settings_defaults():
    assert load_env_value('ROME_PDF_URL_TTL_MINUTES') == '2880'
    assert load_env_value('ROME_PDF_PREFIX') == 'raw/'
    assert load_env_value('ROME_PDF_RATE_LIMIT_PER_MINUTE') == '60'


# --- Signer (patched at the google-auth / google-cloud-storage boundary) ---


@pytest.fixture
def fake_storage(monkeypatch):
    import google.cloud.storage as gcs_storage

    blob = MagicMock()
    blob.generate_signed_url.return_value = 'https://signed'
    client = MagicMock()
    client.bucket.return_value.blob.return_value = blob
    client_cls = MagicMock(return_value=client)
    monkeypatch.setattr(gcs_storage, 'Client', client_cls)
    return SimpleNamespace(blob=blob, client_cls=client_cls)


@pytest.fixture
def fake_default_creds(monkeypatch):
    import google.auth

    creds = MagicMock()
    creds.service_account_email = 'runtime@p.iam.gserviceaccount.com'
    creds.token = None

    def _refresh(_request):
        creds.token = 'tok'

    creds.refresh.side_effect = _refresh
    default = MagicMock(return_value=(creds, 'p'))
    monkeypatch.setattr(google.auth, 'default', default)
    return SimpleNamespace(creds=creds, default=default)


def test_sign_keyless_uses_iam_signblob(fake_default_creds, fake_storage):
    url = sign_object_url('b', 'raw/x.pdf', 2880)
    kw = fake_storage.blob.generate_signed_url.call_args.kwargs
    assert url == 'https://signed'
    assert kw['version'] == 'v4' and kw['method'] == 'GET'
    assert kw['expiration'] == dt.timedelta(minutes=2880)
    assert kw['service_account_email'] == 'runtime@p.iam.gserviceaccount.com'
    assert kw['access_token'] == 'tok'
    fake_storage.client_cls.return_value.bucket.assert_called_with('b')
    fake_storage.client_cls.return_value.bucket.return_value.blob.assert_called_with('raw/x.pdf')


def test_sign_uses_explicit_signer_email(fake_default_creds, fake_storage):
    sign_object_url('b', 'raw/x.pdf', 2880, signer_email='signer@p.iam.gserviceaccount.com')
    kw = fake_storage.blob.generate_signed_url.call_args.kwargs
    assert kw['service_account_email'] == 'signer@p.iam.gserviceaccount.com'


def test_sign_with_key_json_does_not_call_default(fake_default_creds, fake_storage, monkeypatch):
    from google.oauth2 import service_account

    from_info = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(service_account.Credentials, 'from_service_account_info', from_info)
    sign_object_url('b', 'raw/x.pdf', 2880, credentials_json='{"project_id": "p"}')
    kw = fake_storage.blob.generate_signed_url.call_args.kwargs
    from_info.assert_called_once_with({'project_id': 'p'})
    fake_default_creds.default.assert_not_called()
    assert 'access_token' not in kw


def test_sign_failure_raises(fake_default_creds, fake_storage):
    fake_storage.blob.generate_signed_url.side_effect = Exception('denied')
    with pytest.raises(Exception, match='denied'):
        sign_object_url('b', 'raw/x.pdf', 2880)
