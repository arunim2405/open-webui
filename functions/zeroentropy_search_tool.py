"""
ZeroEntropy Search Tool for Open WebUI.

An Open WebUI Tool function that the LLM can invoke on-demand to perform
targeted follow-up searches against the medical literature via ZeroEntropy.

Requirements covered: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import aiohttp
from pydantic import BaseModel

from functions.zeroentropy_utils import extract_page_number, format_snippets


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
                "collection": self.valves.COLLECTION_NAME,
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
                    doc_path = result.get("document_path", "")
                    snippet_text = result.get("snippet", "")
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
