"""Property-based tests for the format_snippets utility function."""

# Feature: medical-rag-chatbot, Property 3: Snippet formatting
# Validates: Requirements 2.3, 3.3

import re
import sys
import os

# Ensure the functions directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from functions.zeroentropy_utils import format_snippets, extract_page_number


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe text that won't accidentally contain page markers
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',), blacklist_characters='<'),
    min_size=0,
    max_size=80,
)

_page_number = st.integers(min_value=1, max_value=99999)

# A document path: simple filename-like string
_document_path = st.from_regex(r'[a-z][a-z0-9_]{0,20}\.md', fullmatch=True)


def _make_marker(page: int) -> str:
    return f'<!-- page: {page} -->'


# Strategy: a single snippet object with document_path and snippet fields
_snippet_with_marker = st.builds(
    lambda path, prefix, suffix, page: {
        'document_path': path,
        'snippet': prefix + _make_marker(page) + suffix,
    },
    path=_document_path,
    prefix=_safe_text,
    suffix=_safe_text,
    page=_page_number,
)

_snippet_without_marker = st.builds(
    lambda path, text: {
        'document_path': path,
        'snippet': text,
    },
    path=_document_path,
    text=_safe_text,
)

_snippet_object = st.one_of(_snippet_with_marker, _snippet_without_marker)


# ---------------------------------------------------------------------------
# Property 3: Snippet formatting
# ---------------------------------------------------------------------------

class TestSnippetFormattingProperty:
    """Property-based tests for format_snippets (Property 3)."""

    # -- Property 3a: output contains exactly N numbered entries for N snippets
    @settings(max_examples=100)
    @given(snippets=st.lists(_snippet_object, min_size=1, max_size=10))
    def test_output_has_one_entry_per_snippet(self, snippets):
        """Formatted output should contain exactly N numbered entries [1]..[N]."""
        output = format_snippets(snippets)
        for i in range(1, len(snippets) + 1):
            assert f'[{i}]' in output

    # -- Property 3b: each entry contains the correct source filename
    @settings(max_examples=100)
    @given(snippets=st.lists(_snippet_object, min_size=1, max_size=10))
    def test_each_entry_contains_source_filename(self, snippets):
        """Each formatted entry should include the source document_path."""
        output = format_snippets(snippets)
        for snippet in snippets:
            assert f"Source: {snippet['document_path']}" in output

    # -- Property 3c: each entry contains a page number (extracted or N/A)
    @settings(max_examples=100)
    @given(snippets=st.lists(_snippet_object, min_size=1, max_size=10))
    def test_each_entry_contains_page_number(self, snippets):
        """Each entry should have a Page: field with a number or N/A."""
        output = format_snippets(snippets)
        for snippet in snippets:
            expected_page = extract_page_number(snippet['snippet'])
            assert f"Page: {expected_page}" in output

    # -- Property 3d: numbering starts at 1 and is sequential
    @settings(max_examples=100)
    @given(snippets=st.lists(_snippet_object, min_size=1, max_size=10))
    def test_numbering_is_sequential_from_one(self, snippets):
        """Numbered entries should start at [1] and increment sequentially."""
        output = format_snippets(snippets)
        # Find all numbered markers in order
        found_numbers = re.findall(r'\[(\d+)\] Source:', output)
        expected = [str(i) for i in range(1, len(snippets) + 1)]
        assert found_numbers == expected

    # -- Property 3e: empty list produces empty string
    @settings(max_examples=10)
    @given(data=st.just([]))
    def test_empty_list_returns_empty_string(self, data):
        """An empty snippet list should produce an empty string."""
        assert format_snippets(data) == ''
