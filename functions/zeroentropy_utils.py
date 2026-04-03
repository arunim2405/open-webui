"""
Shared utilities for ZeroEntropy integration.

Provides helper functions used by both the Retrieval Filter and Search Tool
for page extraction and snippet formatting.
"""

import re


def format_snippets(results: list) -> str:
    """Format a list of ZeroEntropy snippet results into numbered context blocks.

    Each result is formatted as::

        [N] Source: {document_path}, Page: {page}
        {snippet_text}

    Blocks are joined with double newlines.

    Args:
        results: A list of result objects, each with ``document_path`` (str)
            and ``snippet`` (str) fields.

    Returns:
        A single string containing all formatted context blocks.
    """
    blocks = []
    for i, result in enumerate(results, start=1):
        document_path = result.get('document_path', '')
        snippet_text = result.get('snippet', '')
        page = extract_page_number(snippet_text)
        blocks.append(f'[{i}] Source: {document_path}, Page: {page}\n{snippet_text}')
    return '\n\n'.join(blocks)


def extract_page_number(snippet_text: str) -> str:
    """Extract the page number from the nearest preceding ``<!-- page: N -->`` marker.

    Scans *snippet_text* for all HTML comment page markers and returns the
    page number from the **last** (i.e. nearest preceding) match.

    Args:
        snippet_text: The raw snippet text that may contain page markers.

    Returns:
        The page number as a string, or ``"N/A"`` when no marker is found.
    """
    matches = re.findall(r'<!-- page: (\d+) -->', snippet_text)
    if matches:
        return matches[-1]
    return 'N/A'
