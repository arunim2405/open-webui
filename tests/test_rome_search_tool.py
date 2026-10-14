"""Unit tests for the rome Search Tool and Retrieval Filter.

Covers the ``RETRIEVAL_BACKEND`` dispatch, the ID-token Authorization header
sent to the rome search API, and the ``[N] Source: …, Page: …`` context format.
"""

import importlib
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the functions directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

import functions.rome_search_tool
from functions.rome_search_filter import Filter
from functions.rome_search_tool import Tools

SEARCH_API_URL = 'https://rome-search-api-3lziri3uha-uc.a.run.app'
ID_TOKEN = 'test-id-token'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(results):
    """Create a mock aiohttp response returning the given results."""
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


def _rome_result(document_path='rome-v/rome_v_criteria.pdf', page_start=12, text='snippet text',
                 title='Rome V', doi=None):
    return {
        'chunk_id': 'c1',
        'doc_id': 'd1',
        'document_path': document_path,
        'title': title,
        'doi': doi,
        'heading_path': ['Chapter 1'],
        'page_start': page_start,
        'page_end': page_start,
        'snippet': text,
        'text': text,
        'score': 0.9,
        'scores': {'bm25': 1.0, 'vector': 0.8, 'rrf': 0.03, 'rerank': 0.9},
    }


def _post_kwargs(mock_session):
    call = mock_session.post.call_args
    return call.kwargs or call[1]


def _post_url(mock_session):
    call = mock_session.post.call_args
    return call.args[0] if call.args else call[0][0]


# ---------------------------------------------------------------------------
# Search Tool — rome backend
# ---------------------------------------------------------------------------

class TestRomeSearchTool:
    """The tool calls the rome search API with an ID token when RETRIEVAL_BACKEND=rome."""

    def _tool(self, **valve_overrides):
        tool = Tools()
        tool.valves.RETRIEVAL_BACKEND = 'rome'
        tool.valves.SEARCH_API_URL = SEARCH_API_URL
        for name, value in valve_overrides.items():
            setattr(tool.valves, name, value)
        return tool

    async def _run(self, tool, results, query='rome criteria', k=5):
        mock_session = _make_mock_session(_make_mock_response(results))
        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN) as mock_token:
            output = await tool.search_medical_literature(query=query, k=k)
        return output, mock_session, mock_token

    @pytest.mark.asyncio
    async def test_posts_to_top_snippets_endpoint(self):
        """The request goes to {SEARCH_API_URL}/v1/top-snippets."""
        _, mock_session, _ = await self._run(self._tool(), [_rome_result()])

        assert _post_url(mock_session) == f'{SEARCH_API_URL}/v1/top-snippets'

    @pytest.mark.asyncio
    async def test_authorization_header_carries_id_token(self):
        """The Authorization header is a bearer ID token minted for the API's URL."""
        _, mock_session, mock_token = await self._run(self._tool(), [_rome_result()])

        headers = _post_kwargs(mock_session)['headers']
        assert headers['Authorization'] == f'Bearer {ID_TOKEN}'
        assert headers['Content-Type'] == 'application/json'
        mock_token.assert_called_once_with(SEARCH_API_URL)

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped_from_audience_and_url(self):
        """A trailing slash on the valve does not leak into the URL or the token audience."""
        tool = self._tool(SEARCH_API_URL=f'{SEARCH_API_URL}/')
        _, mock_session, mock_token = await self._run(tool, [_rome_result()])

        assert _post_url(mock_session) == f'{SEARCH_API_URL}/v1/top-snippets'
        mock_token.assert_called_once_with(SEARCH_API_URL)

    @pytest.mark.asyncio
    async def test_payload_contains_query_and_k(self):
        """The payload carries exactly the query and k when no collection is configured."""
        _, mock_session, _ = await self._run(self._tool(), [_rome_result()], query='IBS', k=7)

        payload = _post_kwargs(mock_session)['json']
        assert payload == {'query': 'IBS', 'k': 7}

    @pytest.mark.asyncio
    async def test_payload_includes_collection_when_configured(self):
        """ROME_COLLECTION, when set, scopes the search to one collection."""
        tool = self._tool(ROME_COLLECTION='rome-v')
        _, mock_session, _ = await self._run(tool, [_rome_result()])

        assert _post_kwargs(mock_session)['json']['collection'] == 'rome-v'

    @pytest.mark.asyncio
    async def test_formats_results_with_title_and_page_start(self):
        """Results render as [N] Source: {title}, Page: {page_start}\\n{text}."""
        results = [
            _rome_result(document_path='rome-v/a.pdf', page_start=12, text='first', title='Bowel Disorders'),
            _rome_result(document_path='rome-v-md/b.md', page_start=3, text='second', title=None),
        ]
        output, _, _ = await self._run(self._tool(), results)

        assert output == (
            '[1] Source: Bowel Disorders, Page: 12\nfirst\n\n'
            '[2] Source: rome-v-md/b.md, Page: 3\nsecond'
        )

    @pytest.mark.asyncio
    async def test_context_line_carries_doi_when_known(self):
        """A result with a DOI names it after the page, so the model can cite it."""
        result = _rome_result(
            document_path='rome-v-refs/10.1053_j.gastro.2016.02.031.pdf', page_start=4,
            text='body', title='Bowel disorders', doi='10.1053/j.gastro.2016.02.031',
        )
        output, _, _ = await self._run(self._tool(), [result])

        assert output == '[1] Source: Bowel disorders, Page: 4, DOI: 10.1053/j.gastro.2016.02.031\nbody'

    @pytest.mark.asyncio
    async def test_missing_page_start_renders_na(self):
        """A result without a page span still renders, with Page: N/A."""
        output, _, _ = await self._run(
            self._tool(), [_rome_result(page_start=None, text='body')]
        )

        assert output == '[1] Source: Rome V, Page: N/A\nbody'

    @pytest.mark.asyncio
    async def test_emits_citation_per_result(self):
        """One citation event per snippet, carrying the one-based page number."""
        emitter = AsyncMock()
        tool = self._tool()
        mock_session = _make_mock_session(_make_mock_response([_rome_result(page_start=12)]))
        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN):
            await tool.search_medical_literature(query='q', k=1, __event_emitter__=emitter)

        citations = [
            call.args[0] for call in emitter.call_args_list
            if call.args[0]['type'] == 'citation'
        ]
        assert len(citations) == 1
        assert citations[0]['data']['metadata'][0]['page'] == '12'

    async def _citation_names(self, results):
        emitter = AsyncMock()
        mock_session = _make_mock_session(_make_mock_response(results))
        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN):
            await self._tool().search_medical_literature(query='q', k=len(results), __event_emitter__=emitter)
        return [
            call.args[0]['data']['source']['name'] for call in emitter.call_args_list
            if call.args[0]['type'] == 'citation'
        ]

    @pytest.mark.asyncio
    async def test_citation_name_is_the_document_title(self):
        """A reference stored under its DOI shows its title, not the file name."""
        names = await self._citation_names([_rome_result(
            document_path='rome-v-refs/10.1053_j.gastro.2016.02.031.pdf', page_start=4,
            title='Bowel disorders', doi='10.1053/j.gastro.2016.02.031',
        )])

        assert names == ['Bowel disorders (p. 4)']

    @pytest.mark.asyncio
    async def test_citation_name_falls_back_to_file_name_without_title(self):
        """With no title from the API the badge keeps the humanized file name."""
        names = await self._citation_names([_rome_result(
            document_path='rome-v/11_Bowel_Disorders.pdf', page_start=7, title='  ',
        )])

        assert names == ['Bowel Disorders (p. 7)']

    @pytest.mark.asyncio
    async def test_long_title_is_shortened_at_a_word_boundary(self):
        """Badges stay readable: titles past 90 characters end in an ellipsis."""
        title = 'Efficacy and safety of a very long named intervention ' * 3
        names = await self._citation_names([_rome_result(page_start=2, title=title)])

        label = names[0].removesuffix(' (p. 2)')
        assert len(label) <= 90
        assert label.endswith('…')
        assert title.startswith(label[:-1])
        assert not label[:-1].endswith(' ')

    @pytest.mark.asyncio
    async def test_network_failure_returns_graceful_message(self):
        """A transport error is reported as a message, not raised."""
        tool = self._tool()
        with patch('functions.rome_search_tool.aiohttp.ClientSession', side_effect=RuntimeError('boom')), \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN):
            output = await tool.search_medical_literature(query='q', k=1)

        assert output.startswith('Error searching medical literature: boom')

    @pytest.mark.asyncio
    async def test_http_error_response_returns_graceful_message(self):
        """A non-200 (e.g. 403 from the IAM front end) is reported, not raised."""
        tool = self._tool()
        mock_resp = _make_mock_response([])
        mock_resp.raise_for_status = MagicMock(
            side_effect=RuntimeError('403, message=\'Forbidden\'')
        )
        mock_session = _make_mock_session(mock_resp)

        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN):
            output = await tool.search_medical_literature(query='q', k=1)

        assert output.startswith('Error searching medical literature: 403')
        assert 'could not be completed' in output

    @pytest.mark.asyncio
    async def test_request_timeout_is_applied(self):
        """REQUEST_TIMEOUT_SECONDS is passed to aiohttp as a total client timeout."""
        tool = self._tool(REQUEST_TIMEOUT_SECONDS=12)
        mock_session = _make_mock_session(_make_mock_response([_rome_result()]))

        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session) as mock_cls, \
                patch('functions.rome_search_tool.fetch_id_token', return_value=ID_TOKEN):
            await tool.search_medical_literature(query='q', k=1)

        timeout = (mock_cls.call_args.kwargs or mock_cls.call_args[1])['timeout']
        assert timeout.total == 12

    @pytest.mark.asyncio
    async def test_backend_value_is_normalized(self):
        """Whitespace and casing in the valve still select the rome backend."""
        tool = self._tool(RETRIEVAL_BACKEND=' Rome\n')
        _, mock_session, _ = await self._run(tool, [_rome_result()])

        assert _post_url(mock_session) == f'{SEARCH_API_URL}/v1/top-snippets'

    @pytest.mark.asyncio
    async def test_unconfigured_url_returns_graceful_message(self):
        """An empty SEARCH_API_URL fails with a message rather than an unauthenticated call."""
        tool = self._tool(SEARCH_API_URL='')
        output = await tool.search_medical_literature(query='q', k=1)

        assert 'SEARCH_API_URL is not configured' in output


# ---------------------------------------------------------------------------
# Search Tool — ZeroEntropy backend (default)
# ---------------------------------------------------------------------------

class TestZeroEntropyBackendDispatch:
    """The default backend keeps the existing ZeroEntropy behaviour."""

    def test_default_backend_is_zeroentropy(self, monkeypatch):
        """With no RETRIEVAL_BACKEND in the environment the valve default is zeroentropy.

        The default is read at import time, so the module is reloaded with the
        variable unset — otherwise a shell that exports it fails this test.
        """
        monkeypatch.delenv('RETRIEVAL_BACKEND', raising=False)
        module = importlib.reload(functions.rome_search_tool)
        try:
            assert module.Tools().valves.RETRIEVAL_BACKEND == 'zeroentropy'
        finally:
            importlib.reload(module)

    @pytest.mark.asyncio
    async def test_zeroentropy_request_uses_api_key(self):
        """The ZeroEntropy path posts to its own endpoint with the API key."""
        tool = Tools()
        tool.valves.RETRIEVAL_BACKEND = 'zeroentropy'
        tool.valves.ZEROENTROPY_API_KEY = 'ze-test-key'
        mock_session = _make_mock_session(_make_mock_response([]))

        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session):
            await tool.search_medical_literature(query='q', k=3)

        assert _post_url(mock_session) == 'https://api.zeroentropy.dev/v1/queries/top-snippets'
        kwargs = _post_kwargs(mock_session)
        assert kwargs['headers']['Authorization'] == 'Bearer ze-test-key'
        assert kwargs['json'] == {
            'query': 'q',
            'collection_name': 'markdown_output',
            'k': 3,
        }

    @pytest.mark.asyncio
    async def test_zeroentropy_page_span_is_one_based_in_output(self):
        """ZeroEntropy's zero-based page_span still renders as a one-based page."""
        tool = Tools()
        tool.valves.RETRIEVAL_BACKEND = 'zeroentropy'
        results = [{'path': 'docs/a.md', 'content': 'body', 'page_span': [10, 11]}]
        mock_session = _make_mock_session(_make_mock_response(results))

        with patch('functions.rome_search_tool.aiohttp.ClientSession', return_value=mock_session):
            output = await tool.search_medical_literature(query='q', k=1)

        assert output == '[1] Source: docs/a.md, Page: 11\nbody'


# ---------------------------------------------------------------------------
# Retrieval Filter
# ---------------------------------------------------------------------------

class TestRomeRetrievalFilter:
    """The filter dispatches on the same valve and injects context as a system message."""

    def _filter(self, backend='rome'):
        filt = Filter()
        filt.valves.RETRIEVAL_BACKEND = backend
        filt.valves.SEARCH_API_URL = SEARCH_API_URL
        return filt

    @pytest.mark.asyncio
    async def test_rome_context_prepended_as_system_message(self):
        """Retrieved snippets are prepended to the conversation as a system message."""
        filt = self._filter()
        body = {'messages': [{'role': 'user', 'content': 'what is IBS'}]}
        mock_session = _make_mock_session(
            _make_mock_response([_rome_result(document_path='rome-v/a.pdf', page_start=5, text='ctx')])
        )

        with patch('functions.rome_search_filter.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_filter.fetch_id_token', return_value=ID_TOKEN):
            result = await filt.inlet(body)

        assert result['messages'][0]['role'] == 'system'
        assert result['messages'][0]['content'] == (
            'Retrieved medical literature context:\n\n'
            '[1] Source: Rome V, Page: 5\nctx'
        )
        assert result['messages'][1]['content'] == 'what is IBS'

    @pytest.mark.asyncio
    async def test_filter_sends_id_token_and_snippet_count(self):
        """The filter authenticates with an ID token and asks for SNIPPET_COUNT results."""
        filt = self._filter()
        filt.valves.SNIPPET_COUNT = 8
        mock_session = _make_mock_session(_make_mock_response([_rome_result()]))

        with patch('functions.rome_search_filter.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_filter.fetch_id_token', return_value=ID_TOKEN):
            await filt.inlet({'messages': [{'role': 'user', 'content': 'q'}]})

        kwargs = _post_kwargs(mock_session)
        assert kwargs['headers']['Authorization'] == f'Bearer {ID_TOKEN}'
        assert kwargs['json'] == {'query': 'q', 'k': 8}

    @pytest.mark.asyncio
    async def test_filter_citation_name_is_the_document_title(self):
        """The filter's citation badges use the API title, the same as the tool's."""
        filt = self._filter()
        emitter = AsyncMock()
        mock_session = _make_mock_session(_make_mock_response([_rome_result(
            document_path='rome-v-articles/All Global Epi Studies/PIIS0016508521037306.pdf',
            page_start=2, title='Global Prevalence and Impact of Rumination Syndrome',
            doi='10.1053/j.gastro.2021.11.008',
        )]))

        with patch('functions.rome_search_filter.aiohttp.ClientSession', return_value=mock_session), \
                patch('functions.rome_search_filter.fetch_id_token', return_value=ID_TOKEN), \
                patch('functions.rome_search_filter.build_signed_url', return_value='https://signed'):
            await filt.inlet({'messages': [{'role': 'user', 'content': 'q'}]}, __event_emitter__=emitter)

        names = [
            call.args[0]['data']['source']['name'] for call in emitter.call_args_list
            if call.args[0]['type'] == 'citation'
        ]
        assert names == ['Global Prevalence and Impact of Rumination Syndrome (p. 2)']

    @pytest.mark.asyncio
    async def test_filter_defaults_to_zeroentropy(self):
        """With the default valve the filter keeps calling ZeroEntropy."""
        filt = self._filter(backend='zeroentropy')
        mock_session = _make_mock_session(_make_mock_response([]))

        with patch('functions.rome_search_filter.aiohttp.ClientSession', return_value=mock_session):
            await filt.inlet({'messages': [{'role': 'user', 'content': 'q'}]})

        assert _post_url(mock_session) == 'https://api.zeroentropy.dev/v1/queries/top-snippets'

    @pytest.mark.asyncio
    async def test_retrieval_failure_leaves_body_unchanged(self):
        """A backend failure reports status and passes the conversation through untouched."""
        filt = self._filter()
        emitter = AsyncMock()
        body = {'messages': [{'role': 'user', 'content': 'q'}]}

        with patch('functions.rome_search_filter.aiohttp.ClientSession', side_effect=RuntimeError('boom')), \
                patch('functions.rome_search_filter.fetch_id_token', return_value=ID_TOKEN):
            result = await filt.inlet(body, __event_emitter__=emitter)

        assert result['messages'] == [{'role': 'user', 'content': 'q'}]
        statuses = [
            call.args[0] for call in emitter.call_args_list
            if call.args[0]['type'] == 'status'
        ]
        assert 'boom' in statuses[-1]['data']['description']
