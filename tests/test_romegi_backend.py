"""Tests for RomeGI backend branding: product name and the simplified-UI flag."""

import os
import subprocess
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')


def _load_env(**overrides: str) -> tuple[str, str]:
    """Import open_webui.env in a fresh interpreter and return (WEBUI_NAME, ROMEGI_SIMPLIFIED_UI)."""
    env = {k: v for k, v in os.environ.items() if k not in ('WEBUI_NAME', 'ROMEGI_SIMPLIFIED_UI')}
    env.update(
        {
            'DATABASE_URL': 'sqlite:///:memory:',
            'ENABLE_DB_MIGRATIONS': 'false',
            **overrides,
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from open_webui import env; print(env.WEBUI_NAME); print(env.ROMEGI_SIMPLIFIED_UI)',
        ],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    name, flag = result.stdout.strip().splitlines()[-2:]
    return name, flag


def test_custom_name_has_no_suffix():
    assert _load_env(WEBUI_NAME='RomeGI')[0] == 'RomeGI'


def test_default_name_unchanged():
    assert _load_env()[0] == 'Open WebUI'


def test_simplified_ui_defaults_off():
    assert _load_env()[1] == 'False'


def test_simplified_ui_true():
    assert _load_env(ROMEGI_SIMPLIFIED_UI='true')[1] == 'True'


def test_simplified_ui_case_insensitive():
    assert _load_env(ROMEGI_SIMPLIFIED_UI='TRUE')[1] == 'True'


def test_simplified_ui_other_value_off():
    assert _load_env(ROMEGI_SIMPLIFIED_UI='yes')[1] == 'False'
