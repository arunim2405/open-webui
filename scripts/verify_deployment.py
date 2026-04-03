#!/usr/bin/env python3
"""
Post-deployment verification script for the Rome Medical Assistant.

Validates that the ZeroEntropy API is accessible and the document collection
is properly configured. Also prints manual verification instructions for
UI-level checks that cannot be automated.

Requirements covered: 7.1, 7.2, 7.3, 7.4, 7.5

Usage:
    export ZEROENTROPY_API_KEY="your-api-key"
    python scripts/verify_deployment.py
"""

import os
import sys

import requests

ZEROENTROPY_BASE_URL = "https://api.zeroentropy.dev/v1"
EXPECTED_COLLECTION = "markdown_output"
TEST_QUERY = "What are the Rome V diagnostic criteria for IBS?"
TEST_K = 3


def get_api_key() -> str:
    """Read the ZeroEntropy API key from the environment."""
    api_key = os.environ.get("ZEROENTROPY_API_KEY", "")
    if not api_key:
        print("FAIL: ZEROENTROPY_API_KEY environment variable is not set.")
        sys.exit(1)
    return api_key


def verify_collection_exists(api_key: str) -> bool:
    """Verify that the 'markdown_output' collection exists in ZeroEntropy."""
    url = f"{ZEROENTROPY_BASE_URL}/collections/get-collection-list"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"Checking collection list at {url} ...")
    try:
        response = requests.post(url, headers=headers, json={}, timeout=30)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        print(f"FAIL: Could not connect to ZeroEntropy API — {exc}")
        return False
    except requests.Timeout:
        print("FAIL: Request to ZeroEntropy API timed out.")
        return False
    except requests.HTTPError as exc:
        print(f"FAIL: ZeroEntropy API returned an error — {exc}")
        return False

    data = response.json()
    collections = data.get("collections", [])
    collection_names = [
        c.get("collection_name", c) if isinstance(c, dict) else c
        for c in collections
    ]

    if EXPECTED_COLLECTION in collection_names:
        print(f"PASS: Collection '{EXPECTED_COLLECTION}' exists.")
        return True
    else:
        print(
            f"FAIL: Collection '{EXPECTED_COLLECTION}' not found. "
            f"Available collections: {collection_names}"
        )
        return False


def verify_snippet_retrieval(api_key: str) -> bool:
    """Verify that a test query returns at least one snippet."""
    url = f"{ZEROENTROPY_BASE_URL}/queries/top-snippets"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": TEST_QUERY,
        "collection": EXPECTED_COLLECTION,
        "k": TEST_K,
    }

    print(f"Querying top snippets with: \"{TEST_QUERY}\" (k={TEST_K}) ...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        print(f"FAIL: Could not connect to ZeroEntropy API — {exc}")
        return False
    except requests.Timeout:
        print("FAIL: Request to ZeroEntropy API timed out.")
        return False
    except requests.HTTPError as exc:
        print(f"FAIL: ZeroEntropy API returned an error — {exc}")
        return False

    data = response.json()
    results = data.get("results", [])

    if len(results) >= 1:
        print(f"PASS: Received {len(results)} snippet(s) for the test query.")
        for i, result in enumerate(results, 1):
            doc = result.get("document_path", "unknown")
            snippet_preview = result.get("snippet", "")[:120]
            print(f"  [{i}] {doc}: {snippet_preview}...")
        return True
    else:
        print("FAIL: No snippets returned for the test query.")
        return False


def print_manual_verification_instructions() -> None:
    """Print instructions for manual UI-level verification checks."""
    print(
        "\n"
        "=" * 70 + "\n"
        "  MANUAL VERIFICATION INSTRUCTIONS\n"
        "=" * 70 + "\n"
        "\n"
        "The following checks must be performed manually in the browser:\n"
        "\n"
        "1. CITATION DISPLAY (Requirement 7.3)\n"
        "   - Open the Rome Medical Assistant chat in your browser.\n"
        "   - Send: \"What are the Rome IV diagnostic criteria for IBS?\"\n"
        "   - Verify the response includes cited source references with\n"
        "     document names and page numbers (e.g., [Source: file.md, Page: 42]).\n"
        "\n"
        "2. DISCLAIMER FOOTER (Requirement 7.4)\n"
        "   - After any message, verify the assistant's response ends with:\n"
        '     "---\\n⚕️ *This response was generated from indexed medical\n'
        "     literature and does not constitute medical advice. Always verify\n"
        "     findings against primary sources and consult qualified healthcare\n"
        '     professionals for clinical decisions.*"\n'
        "\n"
        "3. NON-DISMISSIBLE BANNER (Requirement 7.5)\n"
        "   - Open the Open WebUI interface in your browser.\n"
        "   - Verify a warning banner is visible at the top of the page with:\n"
        '     "⚕️ Research Tool Only — Responses are generated from indexed\n'
        "     medical literature and do not constitute medical advice. Always\n"
        "     consult qualified healthcare professionals for clinical decisions.\"\n"
        "   - Confirm the banner has NO dismiss/close button.\n"
        "\n"
        "=" * 70
    )


if __name__ == "__main__":
    print("=" * 70)
    print("  Rome Medical Assistant — Post-Deployment Verification")
    print("=" * 70)
    print()

    api_key = get_api_key()

    passed = 0
    failed = 0

    if verify_collection_exists(api_key):
        passed += 1
    else:
        failed += 1

    print()

    if verify_snippet_retrieval(api_key):
        passed += 1
    else:
        failed += 1

    print_manual_verification_instructions()

    print()
    print(f"Automated checks: {passed} passed, {failed} failed.")
    if failed > 0:
        print("Some checks FAILED. Review the output above for details.")
        sys.exit(1)
    else:
        print("All automated checks PASSED.")
        sys.exit(0)
