"""
title: Rome Retrieval Filter
description: Retrieves medical literature context for every query from the rome search API. Citations carry stable links that RomeGI signs when clicked.
requirements: aiohttp, google-auth
version: 0.3.0
"""

import asyncio
import html
import os
import re
from urllib.parse import quote, urlencode

import aiohttp
from pydantic import BaseModel


def clean_snippet_content(text: str) -> str:
    """Clean snippet markdown for human-readable display in citations.

    - Strips YAML frontmatter (``---`` block at the start)
    - Removes HTML comments (e.g. ``<!-- page: 11 -->``)
    - Decodes HTML entities
    - Collapses excessive blank lines

    On any error (malformed input, regex failure, etc.) the original text
    is returned so that citation rendering never breaks.
    """
    if not text:
        return ""

    try:
        cleaned = re.sub(r"^---\s*\n.*?\n---\s*\n+", "", text, count=1, flags=re.DOTALL)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
    except Exception:
        return text


def humanize_document_name(path: str) -> str:
    """Convert a document path into a human-friendly title.

    Strips folder, leading numeric prefix, and ``.md``/``.pdf`` extension, then
    replaces underscores with spaces.
    """
    if not path:
        return ""
    filename = path.rsplit("/", 1)[-1]
    filename = re.sub(r"\.(md|pdf)$", "", filename, flags=re.IGNORECASE)
    filename = re.sub(r"^\d+[_-]", "", filename)
    return filename.replace("_", " ").strip()


def build_unique_citation_name(friendly_name: str, page: str, used_names: set) -> str:
    """Build a citation display name that is unique within a single response.

    The Open WebUI frontend de-duplicates inline citation badges by *name*
    (``[...new Set(names)]`` in ContentRenderer) and then indexes that list
    positionally by the ``[N]`` marker the model emits. When several snippets
    come from the same document they share ``friendly_name``, the Set collapses
    them, and every marker past the first renders as "undefined". Disambiguating
    by page keeps the label meaningful; an ordinal suffix guarantees uniqueness
    when the same document *and* page recur. The returned name is added to
    *used_names* so subsequent calls avoid it.
    """
    name = friendly_name or "Source"
    parts = []
    if page and page != "N/A":
        parts.append(f"p. {page}")

    label = f"{name} ({', '.join(parts)})" if parts else name
    counter = 2
    while label in used_names:
        extra = parts + [f"#{counter}"]
        label = f"{name} ({', '.join(extra)})"
        counter += 1

    used_names.add(label)
    return label


def shorten_title(title: str, limit: int = 90) -> str:
    """Cut *title* to at most *limit* characters at a word boundary, ending in an ellipsis."""
    if len(title) <= limit:
        return title
    cut = title[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{cut}…"


def citation_label(snippet: dict) -> str:
    """Badge name for a snippet: its document title when known, else the humanized file name."""
    title = snippet.get("title", "")
    return shorten_title(title) if title else humanize_document_name(snippet.get("path", ""))


def build_citation_link(object_path: str, page: str) -> str:
    """Stable sign-on-click link for a corpus object; RomeGI signs it when the user clicks.

    The link is relative and carries no signature or expiry, so it never goes stale.
    ``page`` is added only when it is a real page number (not ``"N/A"``).
    """
    if not object_path:
        return ""
    params = {"path": object_path}
    if page and str(page).isdigit():
        params["page"] = str(page)
    return f"/api/v1/rome/pdf?{urlencode(params, quote_via=quote)}"


def normalize_rome_results(results: list) -> list:
    """Normalize rome search API results into ``{path, content, page, object_path}`` dicts.

    ``page_start`` is already one-based, so it is used as-is (no page-marker
    parsing). ``document_path`` is ``<collection>/<path>``, which is exactly the
    corpus object key under ``raw/``.
    """
    snippets = []
    for result in results:
        document_path = result.get("document_path", "")
        page_start = result.get("page_start")
        snippets.append(
            {
                "path": document_path,
                "content": result.get("text", ""),
                "page": str(page_start) if page_start is not None else "N/A",
                "object_path": f"raw/{document_path}" if document_path else "",
                "title": (result.get("title") or "").strip(),
                "doi": result.get("doi") or "",
            }
        )
    return snippets


def format_snippets(snippets: list) -> str:
    """Format normalized snippets into numbered context blocks.

    Each snippet is formatted as::

        [N] Source: {title or path}, Page: {page}[, DOI: {doi}]
        {content}

    Blocks are joined with double newlines.
    """
    blocks = []
    for i, snippet in enumerate(snippets, start=1):
        cleaned = clean_snippet_content(snippet.get("content", ""))
        source = snippet.get("title") or snippet.get("path", "")
        doi = f", DOI: {snippet['doi']}" if snippet.get("doi") else ""
        blocks.append(
            f"[{i}] Source: {source}, "
            f"Page: {snippet.get('page', 'N/A')}{doi}\n{cleaned}"
        )
    return "\n\n".join(blocks)


def fetch_id_token(audience: str) -> str:
    """Mint a Google-signed ID token for *audience* (blocking).

    Uses the ambient service account on Cloud Run; the open-webui service
    account holds ``roles/run.invoker`` on the rome search API.
    """
    import google.auth.transport.requests
    from google.oauth2 import id_token

    return id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)


async def search_rome(valves, query: str, k: int) -> list:
    """Query the rome search API's top-snippets endpoint and normalize the results."""
    base_url = valves.SEARCH_API_URL.rstrip("/")
    if not base_url:
        raise ValueError("SEARCH_API_URL is not configured")

    token = await asyncio.to_thread(fetch_id_token, base_url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "k": k}
    if valves.ROME_COLLECTION:
        payload["collection"] = valves.ROME_COLLECTION

    timeout = aiohttp.ClientTimeout(total=valves.REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{base_url}/v1/top-snippets", json=payload, headers=headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

    return normalize_rome_results(data.get("results", []))


MEDICAL_DISCLAIMER = (
    "---\n"
    "⚕️ *This response was generated from indexed medical literature "
    "and does not constitute medical advice. Always verify findings "
    "against primary sources and consult qualified healthcare "
    "professionals for clinical decisions.*"
)


class Filter:
    """Open WebUI Filter that retrieves context and appends disclaimers."""

    class Valves(BaseModel):
        SEARCH_API_URL: str = os.getenv("SEARCH_API_URL", "")
        ROME_COLLECTION: str = ""
        REQUEST_TIMEOUT_SECONDS: int = 30
        SNIPPET_COUNT: int = 5
        priority: int = 0

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(self, body: dict, __event_emitter__=None) -> dict:
        """Pre-process: retrieve snippets and inject them as context.

        1. Extract the last user message.
        2. Query the rome search API.
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
            snippets = await search_rome(
                self.valves, last_user_message, self.valves.SNIPPET_COUNT
            )

            if snippets:
                context_text = format_snippets(snippets)
                system_message = {
                    "role": "system",
                    "content": f"Retrieved medical literature context:\n\n{context_text}",
                }
                body["messages"] = [system_message] + body["messages"]

                # Emit citation events
                if __event_emitter__:
                    used_names: set = set()
                    for idx, snippet in enumerate(snippets):
                        doc_path = snippet["path"]
                        page = snippet["page"]
                        friendly_name = citation_label(snippet)
                        # Make the display name unique per snippet so the frontend's
                        # name-based de-duplication doesn't collapse same-document
                        # snippets and render later citations as "undefined".
                        citation_name = build_unique_citation_name(
                            friendly_name, page, used_names
                        )
                        pdf_url = build_citation_link(snippet["object_path"], page)
                        cleaned_snippet = clean_snippet_content(snippet["content"])
                        # Append snippet index so multiple snippets from the same
                        # document don't get deduped into one citation badge
                        unique_source_id = f"{doc_path}#{idx}"
                        await __event_emitter__(
                            {
                                "type": "citation",
                                "data": {
                                    "source": {
                                        "name": citation_name,
                                        "id": unique_source_id,
                                        "url": pdf_url,
                                    },
                                    "document": [cleaned_snippet],
                                    "metadata": [
                                        {
                                            "source": unique_source_id,
                                            "name": citation_name,
                                            "page": page,
                                            "html": False,
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
