"""
ZeroEntropy Search Tool for Open WebUI.

An Open WebUI Tool function that the LLM can invoke on-demand to perform
targeted follow-up searches against the medical literature via ZeroEntropy.

Requirements covered: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import aiohttp
from pydantic import BaseModel

import re



def extract_page_number(snippet_text: str) -> str:
    """Extract the page number from the nearest preceding ``<!-- page: N -->`` marker.

    Scans *snippet_text* for all HTML comment page markers and returns the
    page number from the **last** (i.e. nearest preceding) match.

    Args:
        snippet_text: The raw snippet text that may contain page markers.

    Returns:
        The page number as a string, or ``"N/A"`` when no marker is found.
    """
    matches = re.findall(r"<!-- page: (\d+) -->", snippet_text)
    if matches:
        return matches[-1]
    return "N/A"


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
        document_path = result.get("path", "")
        snippet_text = result.get("content", "")
        page_span = result.get("page_span")
        if page_span:
            page = str(page_span[0] + 1) if len(page_span) > 0 else "N/A"
        else:
            page = extract_page_number(snippet_text)
        blocks.append(f"[{i}] Source: {document_path}, Page: {page}\n{snippet_text}")
    return "\n\n".join(blocks)


class Tools:
    """Open WebUI Tool that searches ZeroEntropy medical literature on demand."""

    class Valves(BaseModel):
        ZEROENTROPY_API_KEY: str = ""
        ZEROENTROPY_BASE_URL: str = "https://api.zeroentropy.dev/v1"
        COLLECTION_NAME: str = "markdown_output"

    def __init__(self):
        self.valves = self.Valves()

    async def search_medical_literature(
        self, query: str, k: int = 5, __event_emitter__=None
    ) -> str:
        """Search the medical literature collection via ZeroEntropy.

        Args:
            query: The search query string.
            k: Number of top snippets to retrieve (default 5).
            __event_emitter__: Open WebUI event emitter for status/citation events.

        Returns:
            Formatted search results as a string, or an error message on failure.
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": "Searching medical literature...",
                        "done": False,
                    },
                }
            )

        try:
            url = f"{self.valves.ZEROENTROPY_BASE_URL}/queries/top-snippets"
            headers = {
                "Authorization": f"Bearer {self.valves.ZEROENTROPY_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "query": query,
                "collection_name": self.valves.COLLECTION_NAME,
                "k": k,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            results = data.get("results", [])
            formatted = format_snippets(results)

            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": f"Found {len(results)} passages",
                            "done": True,
                        },
                    }
                )

                for result in results:
                    doc_path = result.get("path", "")
                    snippet_text = result.get("content", "")
                    page_span = result.get("page_span")
                    if page_span:
                        page = str(page_span[0] + 1) if len(page_span) > 0 else "N/A"
                    else:
                        page = extract_page_number(snippet_text)
                    await __event_emitter__(
                        {
                            "type": "source",
                            "data": {
                                "source": {"name": doc_path},
                                "document": [snippet_text],
                                "metadata": [
                                    {
                                        "source": doc_path,
                                        "name": doc_path,
                                        "page": page,
                                    }
                                ],
                            },
                        }
                    )

            return formatted

        except Exception as e:
            error_message = str(e)
            return f"Error searching medical literature: {error_message}. The search could not be completed."
