"""Unit tests for sign-on-click corpus PDF helpers (validation, legacy links, signing)."""

import os
import subprocess
import sys

# Configure an isolated in-memory backend BEFORE any open_webui import.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['ENABLE_DB_MIGRATIONS'] = 'false'

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, BACKEND_DIR)

import pytest
from open_webui.utils.rome_pdf import (
    InvalidPdfRequest,
    normalize_object_path,
    object_path_from_legacy_url,
    redirect_target,
)

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
        'raw/%2e%2e/x.pdf',
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
