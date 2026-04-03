"""Property-based tests for ZeroEntropy Search Tool API request construction.

# Feature: medical-rag-chatbot, Property 2: ZeroEntropy API request construction
# Validates: Requirements 2.2, 3.2
"""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the functions directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from functions.zeroentropy_search_tool import Tools


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty query strings (no surrogates)
_query_text = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',)),
    min_size=1,
    max_size=200,
)

# Positive integer k values
_k_value = st.integers(min_value=1, max_value=100)

# Random base URLs for variety
_base_url = st.sampled_from([
    'https://api.zeroentropy.dev/v1',
    'https://custom.example.com/api',
    'http://localhost:8000',
])

# Random collection names
_collection_name = st.from_regex(r'[a-z][a-z0-9_]{2,20}', fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(results=None):
    """Create a mock aiohttp response returning the given results."""
    if results is None:
        results = []
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={'results': results})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


def _make_mock_session(mock_resp):
    """Create a mock aiohttp.ClientSession that captures post() call arguments."""
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 2: ZeroEntropy API request construction
# Validates: Requirements 2.2, 3.2
# ---------------------------------------------------------------------------

class TestAPIRequestConstructionProperty:
    """Property-based tests for ZeroEntropy API request construction (Property 2).

    **Validates: Requirements 2.2, 3.2**
    """

    @settings(max_examples=100)
    @given(query=_query_text, k=_k_value)
    @pytest.mark.asyncio
    async def test_payload_contains_exactly_three_fields(self, query, k):
        """The constructed payload must contain exactly the fields: query, collection, k."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        # Extract the JSON payload passed to session.post()
        post_call = mock_session.post.call_args
        payload = post_call.kwargs.get('json') or post_call[1].get('json')

        assert set(payload.keys()) == {'query', 'collection', 'k'}

    @settings(max_examples=100)
    @given(query=_query_text, k=_k_value)
    @pytest.mark.asyncio
    async def test_payload_query_matches_input(self, query, k):
        """The payload 'query' field must match the input query string."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        post_call = mock_session.post.call_args
        payload = post_call.kwargs.get('json') or post_call[1].get('json')

        assert payload['query'] == query

    @settings(max_examples=100)
    @given(query=_query_text, k=_k_value)
    @pytest.mark.asyncio
    async def test_payload_collection_matches_configured_valve(self, query, k):
        """The payload 'collection' field must match the configured COLLECTION_NAME valve."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        post_call = mock_session.post.call_args
        payload = post_call.kwargs.get('json') or post_call[1].get('json')

        assert payload['collection'] == tool.valves.COLLECTION_NAME

    @settings(max_examples=100)
    @given(query=_query_text, k=_k_value)
    @pytest.mark.asyncio
    async def test_payload_k_matches_input(self, query, k):
        """The payload 'k' field must match the input k value."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        post_call = mock_session.post.call_args
        payload = post_call.kwargs.get('json') or post_call[1].get('json')

        assert payload['k'] == k

    @settings(max_examples=100)
    @given(query=_query_text, k=_k_value)
    @pytest.mark.asyncio
    async def test_post_target_url_ends_with_top_snippets(self, query, k):
        """The POST target URL must be {base_url}/queries/top-snippets."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        post_call = mock_session.post.call_args
        url = post_call.args[0] if post_call.args else post_call.kwargs.get('url')

        expected_url = f"{tool.valves.ZEROENTROPY_BASE_URL}/queries/top-snippets"
        assert url == expected_url

    @settings(max_examples=100)
    @given(
        query=_query_text,
        k=_k_value,
        base_url=_base_url,
        collection=_collection_name,
    )
    @pytest.mark.asyncio
    async def test_custom_valves_reflected_in_request(self, query, k, base_url, collection):
        """With custom Valves, the URL and collection in the payload must reflect the configured values."""
        mock_resp = _make_mock_response()
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()
        tool.valves.ZEROENTROPY_BASE_URL = base_url
        tool.valves.COLLECTION_NAME = collection

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query=query, k=k, __event_emitter__=AsyncMock())

        post_call = mock_session.post.call_args
        url = post_call.args[0] if post_call.args else post_call.kwargs.get('url')
        payload = post_call.kwargs.get('json') or post_call[1].get('json')

        assert url == f"{base_url}/queries/top-snippets"
        assert payload['collection'] == collection
        assert payload['query'] == query
        assert payload['k'] == k


# ---------------------------------------------------------------------------
# Strategies for Property 7
# ---------------------------------------------------------------------------

# A single snippet result object
_snippet_result = st.fixed_dictionaries({
    'document_path': st.text(
        alphabet=st.characters(blacklist_categories=('Cs',)),
        min_size=1,
        max_size=60,
    ).map(lambda t: t + '.md'),
    'snippet': st.text(
        alphabet=st.characters(blacklist_categories=('Cs',)),
        min_size=0,
        max_size=200,
    ),
})

# A list of 0–10 snippet results
_snippet_results_list = st.lists(_snippet_result, min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# Feature: medical-rag-chatbot, Property 7: Status event emission for tool searches
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------

class TestStatusEventEmissionProperty:
    """Property-based tests for status event emission during tool searches (Property 7).

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100)
    @given(results=_snippet_results_list)
    @pytest.mark.asyncio
    async def test_at_least_two_status_events_emitted(self, results):
        """For any successful search returning N results, at least two status events
        are emitted: one for search initiation and one for completion."""
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()
        emitter = AsyncMock()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query='test', k=5, __event_emitter__=emitter)

        # Collect all status-type events
        status_events = [
            call.args[0] for call in emitter.call_args_list
            if call.args and isinstance(call.args[0], dict) and call.args[0].get('type') == 'status'
        ]

        assert len(status_events) >= 2

    @settings(max_examples=100)
    @given(results=_snippet_results_list)
    @pytest.mark.asyncio
    async def test_first_status_event_is_search_initiation(self, results):
        """The first status event must indicate search initiation with done=False."""
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()
        emitter = AsyncMock()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query='test', k=5, __event_emitter__=emitter)

        status_events = [
            call.args[0] for call in emitter.call_args_list
            if call.args and isinstance(call.args[0], dict) and call.args[0].get('type') == 'status'
        ]

        first = status_events[0]
        assert first['data']['description'] == 'Searching medical literature...'
        assert first['data']['done'] is False

    @settings(max_examples=100)
    @given(results=_snippet_results_list)
    @pytest.mark.asyncio
    async def test_second_status_event_has_correct_count(self, results):
        """The second status event must report 'Found N passages' with done=True,
        where N equals the number of results returned."""
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()
        emitter = AsyncMock()

        with patch('functions.zeroentropy_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query='test', k=5, __event_emitter__=emitter)

        status_events = [
            call.args[0] for call in emitter.call_args_list
            if call.args and isinstance(call.args[0], dict) and call.args[0].get('type') == 'status'
        ]

        second = status_events[1]
        expected_count = len(results)
        assert second['data']['description'] == f'Found {expected_count} passages'
        assert second['data']['done'] is True


# ---------------------------------------------------------------------------
# Unit tests for Search Tool
# Validates: Requirements 3.7, 3.8
# ---------------------------------------------------------------------------

class TestSearchToolUnit:
    """Unit tests for ZeroEntropy Search Tool error handling and page extraction.

    **Validates: Requirements 3.7, 3.8**
    """

    @pytest.mark.asyncio
    async def test_api_failure_returns_descriptive_error_message(self):
        """When aiohttp raises an exception, search_medical_literature should
        return a string starting with 'Error searching medical literature:'
        and ending with 'The search could not be completed.'

        Validates: Requirement 3.7
        """
        tool = Tools()

        with patch(
            'functions.zeroentropy_search_tool.aiohttp.ClientSession',
            side_effect=Exception('Connection refused'),
        ):
            result = await tool.search_medical_literature(
                query='test query', k=5, __event_emitter__=None
            )

        assert result.startswith('Error searching medical literature:')
        assert result.endswith('The search could not be completed.')
        assert 'Connection refused' in result

    @pytest.mark.asyncio
    async def test_snippets_with_page_markers_include_correct_page_numbers(self):
        """When snippets contain <!-- page: N --> markers, the formatted output
        should include the correct page numbers.

        Validates: Requirement 3.8
        """
        results = [
            {
                'document_path': 'rome_v_chapter.md',
                'snippet': '<!-- page: 42 -->IBS diagnostic criteria text',
            },
            {
                'document_path': 'dgbi_overview.md',
                'snippet': '<!-- page: 7 -->Brain-gut axis overview',
            },
        ]
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch(
            'functions.zeroentropy_search_tool.aiohttp.ClientSession',
            return_value=mock_session,
        ):
            output = await tool.search_medical_literature(
                query='IBS criteria', k=2, __event_emitter__=None
            )

        assert 'Page: 42' in output
        assert 'Page: 7' in output
        assert 'rome_v_chapter.md' in output
        assert 'dgbi_overview.md' in output

    @pytest.mark.asyncio
    async def test_snippets_without_page_markers_use_na(self):
        """When snippets lack page markers, the formatted output should use
        'N/A' as the page value.

        Validates: Requirement 3.8
        """
        results = [
            {
                'document_path': 'plain_doc.md',
                'snippet': 'Some text without any page markers at all.',
            },
        ]
        mock_resp = _make_mock_response(results)
        mock_session = _make_mock_session(mock_resp)

        tool = Tools()

        with patch(
            'functions.zeroentropy_search_tool.aiohttp.ClientSession',
            return_value=mock_session,
        ):
            output = await tool.search_medical_literature(
                query='general query', k=1, __event_emitter__=None
            )

        assert 'Page: N/A' in output
        assert 'plain_doc.md' in output
