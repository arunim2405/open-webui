"""Property-based tests for context injection in the Retrieval Filter.

# Feature: medical-rag-chatbot, Property 4: Context injection as system message
# Validates: Requirements 2.5
"""

import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the functions directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import aiohttp
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from functions.zeroentropy_retrieval_filter import Filter
from functions.zeroentropy_utils import format_snippets


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe text that won't accidentally contain page markers
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',), blacklist_characters='<'),
    min_size=1,
    max_size=80,
)

_page_number = st.integers(min_value=1, max_value=99999)

_document_path = st.from_regex(r'[a-z][a-z0-9_]{0,20}\.md', fullmatch=True)


def _make_marker(page: int) -> str:
    return f'<!-- page: {page} -->'


# A snippet result object with a page marker
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

# A single message with a given role
_user_message = st.builds(
    lambda content: {'role': 'user', 'content': content},
    content=_safe_text,
)

_assistant_message = st.builds(
    lambda content: {'role': 'assistant', 'content': content},
    content=_safe_text,
)

# A conversation: at least one user message, possibly interleaved with assistant messages
_conversation = st.lists(
    st.one_of(_user_message, _assistant_message),
    min_size=1,
    max_size=8,
).filter(lambda msgs: any(m['role'] == 'user' for m in msgs))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(results):
    """Create a mock aiohttp response that returns the given results."""
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={'results': results})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


def _make_mock_session(mock_resp):
    """Create a mock aiohttp.ClientSession that returns the given response on post."""
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 4: Context injection as system message
# Validates: Requirements 2.5
# ---------------------------------------------------------------------------

class TestContextInjectionProperty:
    """Property-based tests for inlet context injection (Property 4)."""

    # -- Property 4a: system message is prepended with all context blocks ---
    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_system_message_prepended_with_context(self, messages, snippets):
        """After inlet, the first message should be a system message containing all formatted context."""
        original_messages = [dict(m) for m in messages]

        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            result = await f.inlet(body, __event_emitter__=AsyncMock())

        result_messages = result['messages']

        # First message must be a system message
        assert result_messages[0]['role'] == 'system'

        # System message content must contain the formatted context
        expected_context = format_snippets(snippets)
        assert expected_context in result_messages[0]['content']

    # -- Property 4b: original messages remain intact and in order ----------
    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_original_messages_preserved_in_order(self, messages, snippets):
        """After inlet, all original messages should follow the system message in their original order."""
        original_messages = [dict(m) for m in messages]

        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            result = await f.inlet(body, __event_emitter__=AsyncMock())

        result_messages = result['messages']

        # Everything after the first (system) message should match originals
        remaining = result_messages[1:]
        assert len(remaining) == len(original_messages)
        for orig, actual in zip(original_messages, remaining):
            assert orig['role'] == actual['role']
            assert orig['content'] == actual['content']

    # -- Property 4c: result has exactly len(original) + 1 messages ---------
    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_message_count_increases_by_one(self, messages, snippets):
        """After inlet, the messages array should have exactly one more message than the original."""
        original_count = len(messages)

        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            result = await f.inlet(body, __event_emitter__=AsyncMock())

        assert len(result['messages']) == original_count + 1


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 5: Citation event emission
# Validates: Requirements 2.6, 3.5
# ---------------------------------------------------------------------------

class TestCitationEventEmissionProperty:
    """Property-based tests for citation event emission (Property 5).

    **Validates: Requirements 2.6, 3.5**
    """

    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_citation_event_count_equals_snippet_count(self, messages, snippets):
        """Exactly N citation events should be emitted for N snippets."""
        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        # Collect only source-type calls (citation events)
        citation_calls = [
            call for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'source'
        ]
        assert len(citation_calls) == len(snippets)

    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_citation_events_have_correct_type(self, messages, snippets):
        """Every citation event must have type 'source'."""
        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        citation_calls = [
            call for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'source'
        ]
        for call in citation_calls:
            assert call.args[0]['type'] == 'source'

    @settings(max_examples=100)
    @given(
        messages=_conversation,
        snippets=st.lists(_snippet_with_marker, min_size=1, max_size=6),
    )
    @pytest.mark.asyncio
    async def test_citation_events_contain_correct_source_and_page(self, messages, snippets):
        """Each citation event must contain the correct source filename and page number from the corresponding snippet."""
        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [dict(m) for m in messages]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        citation_calls = [
            call for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'source'
        ]

        from functions.zeroentropy_utils import extract_page_number as _extract

        for i, snippet in enumerate(snippets):
            event_data = citation_calls[i].args[0]
            expected_source = snippet['document_path']
            expected_page = _extract(snippet['snippet'])

            assert event_data['data']['source']['name'] == expected_source
            assert event_data['data']['metadata'][0]['page'] == expected_page


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 6: Outlet disclaimer appending
# Validates: Requirements 2.7, 6.2
# ---------------------------------------------------------------------------

from functions.zeroentropy_retrieval_filter import MEDICAL_DISCLAIMER

# Strategy: random assistant response content (non-empty, no surrogate chars)
_response_content = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',)),
    min_size=1,
    max_size=200,
)

# Strategy: non-assistant messages (user or system) that should remain untouched
_non_assistant_message = st.builds(
    lambda role, content: {'role': role, 'content': content},
    role=st.sampled_from(['user', 'system']),
    content=_safe_text,
)


class TestOutletDisclaimerAppendingProperty:
    """Property-based tests for outlet disclaimer appending (Property 6).

    **Validates: Requirements 2.7, 6.2**
    """

    @settings(max_examples=100)
    @given(content=_response_content)
    @pytest.mark.asyncio
    async def test_outlet_result_ends_with_disclaimer(self, content):
        """After outlet, the last assistant message content must end with the MEDICAL_DISCLAIMER."""
        body = {
            'messages': [
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': content},
            ]
        }

        f = Filter()
        result = await f.outlet(body)

        # Find the last assistant message
        assistant_msgs = [m for m in result['messages'] if m['role'] == 'assistant']
        assert len(assistant_msgs) > 0
        assert assistant_msgs[-1]['content'].endswith(MEDICAL_DISCLAIMER)

    @settings(max_examples=100)
    @given(content=_response_content)
    @pytest.mark.asyncio
    async def test_outlet_preserves_original_content(self, content):
        """After outlet, the original assistant response content must appear before the disclaimer."""
        body = {
            'messages': [
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': content},
            ]
        }

        f = Filter()
        result = await f.outlet(body)

        assistant_msgs = [m for m in result['messages'] if m['role'] == 'assistant']
        modified_content = assistant_msgs[-1]['content']

        # The content should start with the original text followed by separator and disclaimer
        expected = content + "\n\n" + MEDICAL_DISCLAIMER
        assert modified_content == expected

    @settings(max_examples=100)
    @given(
        prefix_msgs=st.lists(_non_assistant_message, min_size=0, max_size=4),
        content=_response_content,
        suffix_msgs=st.lists(_non_assistant_message, min_size=0, max_size=4),
    )
    @pytest.mark.asyncio
    async def test_outlet_does_not_modify_non_assistant_messages(self, prefix_msgs, content, suffix_msgs):
        """Non-assistant messages must remain unchanged after outlet processing."""
        prefix = [dict(m) for m in prefix_msgs]
        suffix = [dict(m) for m in suffix_msgs]
        assistant_msg = {'role': 'assistant', 'content': content}

        # Snapshot originals before outlet
        original_prefix = [dict(m) for m in prefix]
        original_suffix = [dict(m) for m in suffix]

        body = {'messages': prefix + [assistant_msg] + suffix}

        f = Filter()
        result = await f.outlet(body)

        result_msgs = result['messages']

        # Prefix messages should be unchanged
        for i, orig in enumerate(original_prefix):
            assert result_msgs[i]['role'] == orig['role']
            assert result_msgs[i]['content'] == orig['content']

        # Suffix messages (after the assistant message) should be unchanged
        offset = len(prefix) + 1  # skip prefix + assistant
        for i, orig in enumerate(original_suffix):
            assert result_msgs[offset + i]['role'] == orig['role']
            assert result_msgs[offset + i]['content'] == orig['content']


# ---------------------------------------------------------------------------
# Unit tests for Retrieval Filter edge cases
# Validates: Requirements 2.9, 2.10
# ---------------------------------------------------------------------------

class TestRetrievalFilterErrorHandling:
    """Unit tests: API failure returns unmodified body and emits error status event."""

    @pytest.mark.asyncio
    async def test_api_failure_returns_unmodified_body(self):
        """When aiohttp raises ClientError, inlet should return the body unmodified."""
        original_messages = [
            {'role': 'user', 'content': 'What are the Rome V criteria?'},
        ]
        body = {'messages': [dict(m) for m in original_messages]}

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("connection failed"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        emitter = AsyncMock()
        f = Filter()

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            result = await f.inlet(body, __event_emitter__=emitter)

        # Messages should be unchanged
        assert len(result['messages']) == len(original_messages)
        for orig, actual in zip(original_messages, result['messages']):
            assert orig['role'] == actual['role']
            assert orig['content'] == actual['content']

    @pytest.mark.asyncio
    async def test_api_failure_emits_error_status_event(self):
        """When aiohttp raises ClientError, inlet should emit an error status event with done=True."""
        body = {'messages': [{'role': 'user', 'content': 'test query'}]}

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        emitter = AsyncMock()
        f = Filter()

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        # Should have emitted exactly one status event
        status_calls = [
            call for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'status'
        ]
        assert len(status_calls) == 1
        event = status_calls[0].args[0]
        assert event['type'] == 'status'
        assert event['data']['done'] is True
        assert 'Error' in event['data']['description'] or 'error' in event['data']['description'].lower()


class TestRetrievalFilterEmptyMessages:
    """Unit tests: empty messages array returns body unmodified without API calls."""

    @pytest.mark.asyncio
    async def test_empty_messages_returns_unmodified(self):
        """When body has an empty messages list, inlet should return body as-is."""
        body = {'messages': []}
        f = Filter()
        result = await f.inlet(body, __event_emitter__=AsyncMock())
        assert result['messages'] == []

    @pytest.mark.asyncio
    async def test_no_user_messages_returns_unmodified(self):
        """When messages contain only assistant/system roles, inlet should return body unmodified."""
        original_messages = [
            {'role': 'assistant', 'content': 'Hello!'},
            {'role': 'system', 'content': 'You are helpful.'},
        ]
        body = {'messages': [dict(m) for m in original_messages]}
        f = Filter()

        # No API call should be made, so no patching needed
        result = await f.inlet(body, __event_emitter__=AsyncMock())

        assert len(result['messages']) == len(original_messages)
        for orig, actual in zip(original_messages, result['messages']):
            assert orig['role'] == actual['role']
            assert orig['content'] == actual['content']


class TestRetrievalFilterSnippetsWithoutPageMarkers:
    """Unit tests: snippets without page markers use default page value 'N/A'."""

    @pytest.mark.asyncio
    async def test_snippets_without_markers_use_default_page(self):
        """When snippets lack <!-- page: N --> markers, context should show 'N/A' as page."""
        snippets = [
            {'document_path': 'doc1.md', 'snippet': 'Some text without any page marker.'},
            {'document_path': 'doc2.md', 'snippet': 'Another snippet, also no marker here.'},
        ]
        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [{'role': 'user', 'content': 'test query'}]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            result = await f.inlet(body, __event_emitter__=emitter)

        # System message should contain "Page: N/A" for each snippet
        system_msg = result['messages'][0]
        assert system_msg['role'] == 'system'
        assert 'Page: N/A' in system_msg['content']

    @pytest.mark.asyncio
    async def test_citation_events_use_default_page_for_markerless_snippets(self):
        """Citation events for snippets without page markers should have page='N/A'."""
        snippets = [
            {'document_path': 'no_pages.md', 'snippet': 'Plain text snippet.'},
        ]
        mock_resp = _make_mock_response(snippets)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [{'role': 'user', 'content': 'query'}]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        citation_calls = [
            call for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'source'
        ]
        assert len(citation_calls) == 1
        assert citation_calls[0].args[0]['data']['metadata'][0]['page'] == 'N/A'


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Bugfix: unique citation names
# Ensures same-document snippets get distinct display names so the frontend's
# name-based Set de-duplication cannot collapse them and render later inline
# citation markers (e.g. [2][3]) as "undefined".
# ---------------------------------------------------------------------------

from functions.zeroentropy_retrieval_filter import (
    build_unique_citation_name,
    humanize_document_name,
)


class TestHumanizeDocumentName:
    """The humanized title must NOT append a trailing ellipsis.

    The frontend's getDisplayTitle already truncates long names with its own
    "...", so an ellipsis from our side stacked on top of it, producing the
    "Alterations in ...... (p. 3)" double-ellipsis in citation pills.
    """

    def test_no_trailing_ellipsis(self):
        name = humanize_document_name('2_Foo_references/0003_Irritable_bowel_syndrome.md')
        assert name == 'Irritable bowel syndrome'
        assert not name.endswith('...')

    def test_empty_path_returns_empty(self):
        assert humanize_document_name('') == ''


def _simulate_frontend_source_ids(citation_events):
    """Reproduce ContentRenderer.getSourceIds: one entry per source document,
    keyed on metadata.name, then de-duplicated the way JS ``new Set`` does
    (order-preserving). Returns the positional list the inline ``[N]`` badge
    indexes into via ``sourceIds[N - 1]``.
    """
    result = []
    for event in citation_events:
        data = event['data']
        for index in range(len(data.get('document', []))):
            metadata = data['metadata'][index]
            result.append(metadata.get('name'))
    return list(dict.fromkeys(result))  # dict preserves insertion order like Set


class TestUniqueCitationName:
    """Unit tests for the build_unique_citation_name helper."""

    def test_page_is_appended_when_known(self):
        used = set()
        assert build_unique_citation_name('Doc...', '3', used) == 'Doc... (p. 3)'

    def test_no_page_leaves_name_unchanged(self):
        used = set()
        assert build_unique_citation_name('Doc...', 'N/A', used) == 'Doc...'

    def test_same_document_same_page_gets_ordinal_suffix(self):
        used = set()
        first = build_unique_citation_name('Doc...', '3', used)
        second = build_unique_citation_name('Doc...', '3', used)
        third = build_unique_citation_name('Doc...', '3', used)
        assert [first, second, third] == ['Doc... (p. 3)', 'Doc... (p. 3, #2)', 'Doc... (p. 3, #3)']

    def test_collision_without_page_uses_bare_ordinal(self):
        used = set()
        first = build_unique_citation_name('Doc...', 'N/A', used)
        second = build_unique_citation_name('Doc...', 'N/A', used)
        assert [first, second] == ['Doc...', 'Doc... (#2)']

    def test_empty_name_falls_back(self):
        used = set()
        assert build_unique_citation_name('', 'N/A', used) == 'Source'


class TestCitationNamesUniqueInResponse:
    """Integration: inlet must emit distinct names for same-document snippets."""

    @pytest.mark.asyncio
    async def test_same_document_snippets_get_unique_names(self):
        """Reproduces the real bug: 5 snippets from one paper, pages [1,3,4,3,3].

        Before the fix all five shared one name, the frontend Set collapsed them
        to length 1, and markers [2]..[5] rendered "undefined". After the fix the
        names are distinct and the positional lookup resolves for every marker.
        """
        doc = '8_Psychosocial Aspects of DGBI_references/0211_Alterations_in_fecal_SCFA.md'
        pages = [1, 3, 4, 3, 3]
        # Current filter contract reads `path` / `content` (not document_path/snippet)
        results = [
            {'path': doc, 'content': f'chunk {i} <!-- page: {p} -->'}
            for i, p in enumerate(pages)
        ]
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        emitter = AsyncMock()
        f = Filter()
        body = {'messages': [{'role': 'user', 'content': 'evidence for SCFA in IBS'}]}

        with patch('functions.zeroentropy_retrieval_filter.aiohttp.ClientSession', return_value=mock_session):
            await f.inlet(body, __event_emitter__=emitter)

        citation_events = [
            call.args[0] for call in emitter.call_args_list
            if call.args and call.args[0].get('type') == 'citation'
        ]
        assert len(citation_events) == len(pages)

        names = [e['data']['metadata'][0]['name'] for e in citation_events]
        # Every emitted display name must be distinct
        assert len(set(names)) == len(names), names
        # source.name and metadata.name must agree (both drive frontend display)
        for e in citation_events:
            assert e['data']['source']['name'] == e['data']['metadata'][0]['name']

        # End-to-end: the frontend's Set-dedup keeps all entries, so every
        # inline marker [1]..[N] resolves to a real name (no "undefined").
        source_ids = _simulate_frontend_source_ids(citation_events)
        assert len(source_ids) == len(pages)
        for marker in range(1, len(pages) + 1):
            assert source_ids[marker - 1] is not None
