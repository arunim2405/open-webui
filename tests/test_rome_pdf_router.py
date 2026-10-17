"""Runs the /api/v1/rome/pdf cases in their own interpreter so DB/config setup can't leak between modules."""

import os
import subprocess
import sys

CASES = os.path.join(os.path.dirname(__file__), 'rome_pdf_router_cases.py')


def test_rome_pdf_router_cases():
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', CASES, '-q', '-p', 'no:cacheprovider'],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
