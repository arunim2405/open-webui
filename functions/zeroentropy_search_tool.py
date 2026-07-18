"""
title: ZeroEntropy Search Tool
description: LLM-invokable medical literature search via ZeroEntropy with signed GCS URLs for citations.
requirements: aiohttp, google-cloud-storage
version: 0.2.0
"""

import datetime
import html
import json
import re

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

# Tells Open WebUI to use this tool's manually emitted citations instead of
# auto-generating a single source from the tool's return value.
citation = True


def humanize_document_name(path: str) -> str:
    """Convert a document path into a human-friendly title."""
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


def md_path_to_pdf_path(path: str) -> str:
    """Map a markdown reference path to the original PDF path."""
    if not path:
        return ""
    return re.sub(r"\.md$", ".pdf", path, flags=re.IGNORECASE)


def build_signed_url(
    path: str,
    bucket: str,
    credentials_json: str,
    ttl_minutes: int = 60,
) -> str:
    """Generate a V4 signed URL for a GCS object.

    Falls back to the GCS console URL if signing fails.
    """
    if not path or not bucket:
        return ""

    try:
        from google.cloud import storage
        from google.oauth2 import service_account

        if credentials_json:
            info = json.loads(credentials_json)
            creds = service_account.Credentials.from_service_account_info(info)
            client = storage.Client(credentials=creds, project=info.get("project_id"))
        else:
            client = storage.Client()

        blob = client.bucket(bucket).blob(path)
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=ttl_minutes),
            method="GET",
        )
    except Exception:
        return f"https://storage.cloud.google.com/{bucket}/{path}"


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
        cleaned = clean_snippet_content(snippet_text)
        blocks.append(f"[{i}] Source: {document_path}, Page: {page}\n{cleaned}")
    return "\n\n".join(blocks)


class Tools:
    """Open WebUI Tool that searches ZeroEntropy medical literature on demand."""

    class Valves(BaseModel):
        ZEROENTROPY_API_KEY: str = ""
        ZEROENTROPY_BASE_URL: str = "https://api.zeroentropy.dev/v1"
        COLLECTION_NAME: str = "markdown_output"
        GCS_BUCKET: str = "stackguardian-nonprod-rome-uploads"
        GCS_CREDENTIALS_JSON: str = ""
        SIGNED_URL_TTL_MINUTES: int = 10080  # 7 days (max for V4 signed URLs)

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

                used_names: set = set()
                for idx, result in enumerate(results):
                    doc_path = result.get("path", "")
                    snippet_text = result.get("content", "")
                    page_span = result.get("page_span")
                    if page_span:
                        page = str(page_span[0] + 1) if len(page_span) > 0 else "N/A"
                    else:
                        page = extract_page_number(snippet_text)
                    friendly_name = humanize_document_name(doc_path)
                    # Make the display name unique per snippet so the frontend's
                    # name-based de-duplication doesn't collapse same-document
                    # snippets and render later citations as "undefined".
                    citation_name = build_unique_citation_name(friendly_name, page, used_names)
                    pdf_path = md_path_to_pdf_path(doc_path)
                    pdf_url = build_signed_url(
                        pdf_path,
                        self.valves.GCS_BUCKET,
                        self.valves.GCS_CREDENTIALS_JSON,
                        self.valves.SIGNED_URL_TTL_MINUTES,
                    )
                    cleaned_snippet = clean_snippet_content(snippet_text)
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
                                    }
                                ],
                            },
                        }
                    )

            return formatted

        except Exception as e:
            error_message = str(e)
            return f"Error searching medical literature: {error_message}. The search could not be completed."
