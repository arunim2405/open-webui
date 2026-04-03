"""Unit and property-based tests for the extract_page_number utility function."""

import sys
import os

# Ensure the functions directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from functions.zeroentropy_utils import extract_page_number


class TestExtractPageNumber:
    """Unit tests for extract_page_number."""

    def test_single_marker(self):
        text = '<!-- page: 42 -->Some content here'
        assert extract_page_number(text) == '42'

    def test_multiple_markers_returns_last(self):
        text = '<!-- page: 10 -->First section<!-- page: 20 -->Second section'
        assert extract_page_number(text) == '20'

    def test_no_marker_returns_na(self):
        text = 'Just some plain text without any markers.'
        assert extract_page_number(text) == 'N/A'

    def test_empty_string_returns_na(self):
        assert extract_page_number('') == 'N/A'

    def test_marker_with_large_page_number(self):
        text = '<!-- page: 9999 -->Content on a high page'
        assert extract_page_number(text) == '9999'

    def test_marker_at_end_of_text(self):
        text = 'Content before<!-- page: 7 -->'
        assert extract_page_number(text) == '7'

    def test_marker_with_surrounding_content(self):
        text = 'Before<!-- page: 3 -->Middle<!-- page: 5 -->After'
        assert extract_page_number(text) == '5'

    def test_single_page_number(self):
        text = '<!-- page: 1 -->First page content'
        assert extract_page_number(text) == '1'


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 1: Page marker extraction
# Validates: Requirements 2.4, 3.8
# ---------------------------------------------------------------------------

# Strategy: generate plain text that does NOT contain the marker pattern
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',), blacklist_characters='<'),
    min_size=0,
    max_size=80,
)

# Strategy: a single page marker with a random page number
_page_number = st.integers(min_value=1, max_value=99999)


def _make_marker(page: int) -> str:
    """Build a ``<!-- page: N -->`` marker string."""
    return f'<!-- page: {page} -->'


class TestPageMarkerExtractionProperty:
    """Property-based tests for extract_page_number (Property 1)."""

    # -- Property 1a: single marker embedded at a random position -----------
    @settings(max_examples=100)
    @given(
        prefix=_safe_text,
        suffix=_safe_text,
        page=_page_number,
    )
    def test_single_marker_returns_correct_page(self, prefix, suffix, page):
        """Any snippet with exactly one marker should return that page number."""
        snippet = prefix + _make_marker(page) + suffix
        assert extract_page_number(snippet) == str(page)

    # -- Property 1b: multiple markers – last one wins ----------------------
    @settings(max_examples=100)
    @given(
        parts=st.lists(_safe_text, min_size=2, max_size=6),
        pages=st.lists(_page_number, min_size=2, max_size=6),
    )
    def test_multiple_markers_returns_last_page(self, parts, pages):
        """When multiple markers exist, the last marker's page is returned."""
        # Interleave: text0 marker0 text1 marker1 ... textN
        # Ensure we have matching counts
        n = min(len(parts), len(pages))
        assume(n >= 2)
        parts = parts[:n]
        pages = pages[:n]

        # Build snippet: part[0] + marker[0] + part[1] + marker[1] + ...
        snippet = ''
        for text_chunk, pg in zip(parts, pages):
            snippet += text_chunk + _make_marker(pg)

        expected_last_page = str(pages[-1])
        assert extract_page_number(snippet) == expected_last_page

    # -- Property 1c: no markers → default "N/A" ---------------------------
    @settings(max_examples=100)
    @given(text=_safe_text)
    def test_no_markers_returns_na(self, text):
        """Snippets without any page marker should return 'N/A'."""
        assert extract_page_number(text) == 'N/A'
