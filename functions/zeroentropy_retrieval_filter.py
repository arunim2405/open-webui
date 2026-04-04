"""
ZeroEntropy Retrieval Filter for Open WebUI.

An Open WebUI Filter function that automatically retrieves relevant medical
literature passages from ZeroEntropy for every user query (inlet) and appends
a medical disclaimer to every assistant response (outlet).

Requirements covered: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 6.2
"""

from typing import Optional
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




MEDICAL_DISCLAIMER = (
    "---\n"
    "⚕️ *This response was generated from indexed medical literature "
    "and does not constitute medical advice. Always verify findings "
    "against primary sources and consult qualified healthcare "
    "professionals for clinical decisions.*"
)


class Filter:
    """Open WebUI Filter that retrieves ZeroEntropy context and appends disclaimers."""

    class Valves(BaseModel):
        ZEROENTROPY_API_KEY: str = ""
        ZEROENTROPY_BASE_URL: str = "https://api.zeroentropy.dev/v1"
        COLLECTION_NAME: str = "markdown_output"
        SNIPPET_COUNT: int = 5
        priority: int = 0

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(self, body: dict, __event_emitter__=None) -> dict:
        """Pre-process: retrieve ZeroEntropy snippets and inject as context.

        1. Extract the last user message.
        2. POST to ZeroEntropy /queries/top-snippets.
        3. Format snippets and prepend as a system message.
        4. Emit citation events for each snippet.
        5. On failure, emit error status and return body unmodified.
        """
        messages = body.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return body

        last_user_message = user_messages[-1].get("content", "")

        try:
            url = f"{self.valves.ZEROENTROPY_BASE_URL}/queries/top-snippets"
            headers = {
                "Authorization": f"Bearer {self.valves.ZEROENTROPY_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "query": last_user_message,
                "collection_name": self.valves.COLLECTION_NAME,
                "k": self.valves.SNIPPET_COUNT,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            results = data.get("results", [])

            if results:
                context_text = format_snippets(results)
                system_message = {
                    "role": "system",
                    "content": f"Retrieved medical literature context:\n\n{context_text}",
                }
                body["messages"] = [system_message] + body["messages"]

                # Emit citation events
                if __event_emitter__:
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
                                "type": "citation",
                                "data": {
                                    "source": {
                                        "name": doc_path,
                                        "id": doc_path,
                                    },
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

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": f"Error retrieving context: {e}",
                            "done": True,
                        },
                    }
                )

        import json
        print("=== INLET FINAL MESSAGES ===")
        for m in body.get("messages", []):
            print(f"[{m.get('role')}] {m.get('content', '')[:200]}")
        print("=== END INLET ===")

        return body

    async def outlet(self, body: dict, __event_emitter__=None) -> dict:
        """Post-process: append medical disclaimer to the last assistant message."""
        messages = body.get("messages", [])

        for message in reversed(messages):
            if message.get("role") == "assistant":
                message["content"] = (
                    message.get("content", "") + "\n\n" + MEDICAL_DISCLAIMER
                )
                break

        return body
