# Sign-on-Click Citation Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Citation links in RomeGI never expire. Chats store a stable `/api/v1/rome/pdf?...` link, and the backend signs a fresh GCS URL only when a signed-in user clicks it.

**Architecture:**
- A new authenticated FastAPI router in the fork validates the requested corpus object, signs a V4 URL keylessly through IAM `signBlob`, and answers `302`.
- The Rome filter and tool stop signing at answer time and emit the stable link instead.
- A small frontend helper sends both new links and old stored `storage.googleapis.com` links through the endpoint on click.
- Terraform grants the Cloud Run service account the right to sign as itself and to read the corpus bucket.

**Tech Stack:** FastAPI, `google-cloud-storage` / `google-auth` (already in `backend/requirements.txt`), SvelteKit 5 + TypeScript, vitest, pytest, Terraform (Google provider).

**Spec:** PRD "Sign-on-click citation links for RomeGI": https://claude.ai/code/artifact/94563d1f-562e-40ad-84ce-50ec23247f0a (read it with the Claude Docs tools). Requirement IDs R1–R12 below refer to it.

## Global Constraints

- **Stable link format (R1):** `/api/v1/rome/pdf?path=<object path>&page=<n>`. It is relative, with no signature, expiry or domain. Omit `page` unless it is all digits.
- **Endpoint:** `GET /api/v1/rome/pdf`, with exactly one of `path` or `src`, plus an optional `page` (int, 1–100000).
- **Signed URL lifetime:** 2 days, from `ROME_PDF_URL_TTL_MINUTES`, default `2880`.
- **One bucket only:** `ROME_GCS_BUCKET`, the corpus bucket (nonprod: `stackguardian-nonprod-rome-corpus`). Allowed prefix `ROME_PDF_PREFIX`, default `raw/`.
- **Auth:** `open_webui.utils.auth.get_verified_user`. Ruling: `pending` users get **401**, Open WebUI's existing behaviour, not the PRD's 403. Flag at handoff.
- **Allowed file types:** `.pdf` and `.md`. Ruling: the corpus holds both kinds (`rome-ingestion-search/src/rome_search/gcp/storage.py:79`, `kind = "pdf" | "md"`). PDF-only (the PRD's R4) would break Markdown citations. Flag at handoff.
- **Rate limit:** 60 clicks per user per minute (`ROME_PDF_RATE_LIMIT_PER_MINUTE`, default `60`) using the existing `open_webui.utils.rate_limit.RateLimiter`. Over the limit → `429`.
- **Signing:** keyless through IAM `signBlob` as the runtime service account (`ROME_PDF_SIGNER_EMAIL`, default = the runtime account's email). `ROME_PDF_SIGNER_CREDENTIALS_JSON` (env only, never a valve) is a fallback.
- **Failure handling:** a signing failure returns **502** with a plain error page. Never fall back to a `storage.cloud.google.com` console link (R7).
- **Logging (R10):** one `log.info` per click with `user_id`, `path` and `outcome`. Never log the signed URL or tokens.
- **Backend:** the in-house GCP search backend is the only one. Remove the ZeroEntropy branch and its valves from `functions/rome_search_filter.py` and `functions/rome_search_tool.py`. Links from the ZeroEntropy era (uploads bucket) stay broken by decision: the endpoint refuses them with 400.
- **Out of scope:** the old `functions/zeroentropy_*.py` plugins and their tests, Terraform's `RETRIEVAL_BACKEND` and ZeroEntropy secrets, and deleting the `rome-pdf-signer` key (a post-rollout step).
- **Existing tests:** `tests/` must gain no new failures. `main` already has 11 failing tests, in `test_docker_compose.py` (2), `test_retrieval_filter.py` (4) and `test_search_tool.py` (5).

## Review Focus

1. **Corpus file names with spaces, parentheses, commas and non-ASCII** (e.g. `raw/rome-v/Bowel Disorders_Document C_FINAL READY FOR COPYEDITING.pdf`) must survive the round trip: link → endpoint → signed URL. Tests: Task 4 `test_citation_link_encodes_awkward_names`, Task 3 `test_awkward_name_round_trip`.
2. **Markdown corpus documents** must open, not return 400. Test: Task 1 `test_normalize_accepts_markdown`.
3. **Legacy URLs with percent-encoded keys** (`%20`, `%28`) must resolve to the real object key. Test: Task 1 `test_legacy_url_decodes_object_key`.
4. **The redirect must not be cached.** A cached 302 would hand out a signed URL after it expires and keep it in shared caches. Test: Task 3 `test_redirect_is_not_cacheable` asserts `Cache-Control: no-store`.
5. **A page of `"N/A"` or a missing page** gives a link with no page that opens at page 1, never an error. Tests: Task 4 `test_citation_link_omits_non_numeric_page`, Task 3 `test_no_page_no_fragment`.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/open_webui/env.py` | New `ROME_*` settings (env-only) |
| `backend/open_webui/utils/rome_pdf.py` (new) | Pure validation and legacy-URL parsing, plus the GCS signer |
| `backend/open_webui/routers/rome.py` (new) | `GET /pdf`: auth, rate limit, validate, sign, redirect, log |
| `backend/open_webui/main.py` | Mount the router at `/api/v1/rome` |
| `functions/rome_search_filter.py`, `functions/rome_search_tool.py` | Emit stable links; drop ZeroEntropy and signing |
| `src/lib/utils/citationLinks.ts` (new) | Map a stored `source.url` to the href to open |
| `src/lib/components/chat/Messages/Citations/CitationModal.svelte` | Use the helper for both citation links |
| `terraform/main.tf`, `terraform/iam.tf`, `terraform/cloudrun.tf`, `terraform/variables.tf` | Enable the IAM credentials API, let the service account sign as itself, set the env vars |
| `../rome-ingestion-search/infra/iam.tf` | Grant Open WebUI's service account read access to the corpus bucket (separate repo, separate PR) |
| `tests/test_rome_pdf_utils.py`, `tests/test_rome_pdf_router.py` (new), `tests/test_rome_search_tool.py` | Backend and plugin tests |

Backend tests import `open_webui` the way `tests/test_signup_codes.py` does: set `DATABASE_URL=sqlite:///:memory:` and `ENABLE_DB_MIGRATIONS=false` before importing, and put `backend/` on `sys.path`.

---

### Task 1: Settings and path validation

**Files:**
- Modify: `backend/open_webui/env.py` (next to `WEBUI_NAME`)
- Create: `backend/open_webui/utils/rome_pdf.py`
- Test: `tests/test_rome_pdf_utils.py`

**Interfaces:**
- Produces, in `open_webui.env`:
  - `ROME_GCS_BUCKET: str` (default `''`)
  - `ROME_PDF_PREFIX: str` (`'raw/'`)
  - `ROME_PDF_URL_TTL_MINUTES: int` (`2880`)
  - `ROME_PDF_SIGNER_EMAIL: str` (`''`)
  - `ROME_PDF_SIGNER_CREDENTIALS_JSON: str` (`''`)
  - `ROME_PDF_RATE_LIMIT_PER_MINUTE: int` (`60`)
- Produces, in `open_webui.utils.rome_pdf`:
  - `class InvalidPdfRequest(ValueError)`
  - `ALLOWED_EXTENSIONS = ('.pdf', '.md')`
  - `normalize_object_path(path: str, prefix: str) -> str`: returns the path unchanged when valid, else raises `InvalidPdfRequest`
  - `object_path_from_legacy_url(url: str, bucket: str) -> str`: returns the decoded object key, else raises `InvalidPdfRequest`
  - `redirect_target(signed_url: str, page: int | None) -> str`

- [ ] **Step 1: Write the failing tests**

```python
P = 'raw/'
def test_normalize_accepts_pdf(): assert normalize_object_path('raw/rome-v/a b (1).pdf', P) == 'raw/rome-v/a b (1).pdf'
def test_normalize_accepts_markdown(): assert normalize_object_path('raw/rome-v/notes.md', P) == 'raw/rome-v/notes.md'
@pytest.mark.parametrize('bad', ['', 'other/x.pdf', '/raw/x.pdf', 'raw/../secret.pdf', 'raw/a/../../x.pdf',
    'raw\\x.pdf', 'raw//x.pdf', 'raw/%2e%2e/x.pdf', 'raw/x.exe', 'raw/x.pdf\n', 'raw/' + 'a' * 1100 + '.pdf'])
def test_normalize_rejects(bad):
    with pytest.raises(InvalidPdfRequest): normalize_object_path(bad, P)

B = 'stackguardian-nonprod-rome-corpus'
def test_legacy_path_style(): assert object_path_from_legacy_url(f'https://storage.googleapis.com/{B}/raw/c/x.pdf?X-Goog-Signature=a', B) == 'raw/c/x.pdf'
def test_legacy_virtual_host(): assert object_path_from_legacy_url(f'https://{B}.storage.googleapis.com/raw/c/x.pdf?X-Goog-Expires=1', B) == 'raw/c/x.pdf'
def test_legacy_console_host(): assert object_path_from_legacy_url(f'https://storage.cloud.google.com/{B}/raw/c/x.pdf', B) == 'raw/c/x.pdf'
def test_legacy_url_decodes_object_key(): assert object_path_from_legacy_url(f'https://storage.googleapis.com/{B}/raw/c/A%20B%20%281%29.pdf?x=1', B) == 'raw/c/A B (1).pdf'
@pytest.mark.parametrize('bad', [
    'https://storage.googleapis.com/stackguardian-nonprod-rome-uploads/x.pdf?a=1',  # ZeroEntropy era: stays broken
    'https://evil.example.com/stackguardian-nonprod-rome-corpus/raw/x.pdf',
    'http://storage.googleapis.com/stackguardian-nonprod-rome-corpus/raw/x.pdf',
    'javascript:alert(1)', ''])
def test_legacy_rejects(bad):
    with pytest.raises(InvalidPdfRequest): object_path_from_legacy_url(bad, B)

def test_redirect_target_adds_page(): assert redirect_target('https://s/x?sig=1', 12) == 'https://s/x?sig=1#page=12'
def test_redirect_target_without_page(): assert redirect_target('https://s/x?sig=1', None) == 'https://s/x?sig=1'

# load_env_value(name): a test helper that runs `python -c "from open_webui import env; print(env.<name>)"`
# in a subprocess with cwd=backend/ and none of the ROME_* vars set, then returns stdout stripped.
def test_settings_defaults():
    assert load_env_value('ROME_PDF_URL_TTL_MINUTES') == '2880' and load_env_value('ROME_PDF_PREFIX') == 'raw/'
    assert load_env_value('ROME_PDF_RATE_LIMIT_PER_MINUTE') == '60'
```

- [ ] **Step 2: Run them and verify they fail**

Run: `python3 -m pytest tests/test_rome_pdf_utils.py -v`
Expected: collection error, `ModuleNotFoundError: open_webui.utils.rome_pdf`.

- [ ] **Step 3: Implement the settings and the three functions.**
  - **`normalize_object_path`** checks, in order: non-empty; length ≤ 1024; no `%`, `\`, `//`, control characters or leading `/`; no `..` path segment; starts with `prefix`; lower-cased name ends with one of `ALLOWED_EXTENSIONS`.
  - **`object_path_from_legacy_url`** uses `urllib.parse.urlsplit`. Require `https`. Accept host `storage.googleapis.com` or `storage.cloud.google.com` with path `/<bucket>/<key>`, or host `<bucket>.storage.googleapis.com` with path `/<key>`. The bucket must equal `bucket`. Return `unquote(key)` and ignore the query.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python3 -m pytest tests/test_rome_pdf_utils.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/env.py backend/open_webui/utils/rome_pdf.py tests/test_rome_pdf_utils.py
git commit -m "feat: corpus PDF path validation and legacy link parsing"
```

---

### Task 2: Keyless signer

**Files:**
- Modify: `backend/open_webui/utils/rome_pdf.py`
- Test: `tests/test_rome_pdf_utils.py`

**Interfaces:**
- Produces: `sign_object_url(bucket: str, object_path: str, ttl_minutes: int, signer_email: str = '', credentials_json: str = '') -> str`. It is blocking, so callers run it in `asyncio.to_thread`. It raises on any failure and has no fallback URL.

- [ ] **Step 1: Write the failing tests.** Patch `google.auth.default` and `google.cloud.storage.Client`, at the library boundary only.
  - `fake_default_creds`: `google.auth.default` returns creds with `service_account_email='runtime@p.iam.gserviceaccount.com'`, and a `refresh()` that sets `token='tok'`.
  - `fake_storage`: the `Client(...).bucket(...).blob(...)` chain ends in a mock whose `generate_signed_url` returns `'https://signed'`.

```python
def test_sign_keyless_uses_iam_signblob(fake_default_creds, fake_storage):
    url = sign_object_url('b', 'raw/x.pdf', 2880)
    kw = fake_storage.blob.generate_signed_url.call_args.kwargs
    assert url == 'https://signed'
    assert kw['version'] == 'v4' and kw['method'] == 'GET'
    assert kw['expiration'] == datetime.timedelta(minutes=2880)
    assert kw['service_account_email'] == 'runtime@p.iam.gserviceaccount.com'   # from the default creds
    assert kw['access_token'] == 'tok'                                          # creds refreshed first
def test_sign_uses_explicit_signer_email(...): assert kw['service_account_email'] == 'signer@p.iam.gserviceaccount.com'
def test_sign_with_key_json_does_not_call_default(...): # credentials_json given -> service_account.Credentials.from_service_account_info, no access_token kwarg
def test_sign_failure_raises(...):
    fake_storage.blob.generate_signed_url.side_effect = Exception('denied')
    with pytest.raises(Exception): sign_object_url('b', 'raw/x.pdf', 2880)
```

- [ ] **Step 2: Run and verify they fail**

Run: `python3 -m pytest tests/test_rome_pdf_utils.py -k sign -v`
Expected: `ImportError` on `sign_object_url`.

- [ ] **Step 3: Implement `sign_object_url`.**
  - **Keyless path:** `google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])`, then `creds.refresh(google.auth.transport.requests.Request())`. Call `blob.generate_signed_url(version='v4', expiration=timedelta(minutes=ttl_minutes), method='GET', service_account_email=signer_email or creds.service_account_email, access_token=creds.token)`.
  - **Key path:** `service_account.Credentials.from_service_account_info(json.loads(credentials_json))`, then sign without `access_token`.

- [ ] **Step 4: Run and verify they pass**

Run: `python3 -m pytest tests/test_rome_pdf_utils.py -v`
Expected: all pass.

- [ ] **Step 5: Commit** with `feat: keyless GCS signer for corpus PDFs`.

---

### Task 3: `GET /api/v1/rome/pdf` router

**Files:**
- Create: `backend/open_webui/routers/rome.py`
- Modify: `backend/open_webui/main.py`. Import `rome` with the other routers, and add `app.include_router(rome.router, prefix='/api/v1/rome', tags=['rome'])` next to `signup_codes` (~line 1515).
- Test: `tests/test_rome_pdf_router.py`

**Interfaces:**
- Consumes: Task 1 settings and functions; Task 2 `sign_object_url`.
- Produces: `router: APIRouter` and `async def open_corpus_pdf(request: Request, path: str | None = None, src: str | None = None, page: int | None = Query(None, ge=1, le=100000), user=Depends(get_verified_user)) -> Response` at `GET /pdf`.

Behaviour, in order:
1. Auth through the dependency.
2. Rate limit: `RateLimiter(redis_client=get_redis_client(), limit=ROME_PDF_RATE_LIMIT_PER_MINUTE, window=60)`, key `f'rome_pdf:{user.id}'` → `429`.
3. `ROME_GCS_BUCKET` empty → `503`.
4. Exactly one of `path` / `src`, else `400`. For `src`, call `object_path_from_legacy_url(src, ROME_GCS_BUCKET)`. Then `normalize_object_path(..., ROME_PDF_PREFIX)`. `InvalidPdfRequest` → `400`.
5. `await asyncio.to_thread(sign_object_url, ...)`. Any exception → `502`, as an `HTMLResponse` with the body `This document could not be opened. Please try again later.`
6. `RedirectResponse(redirect_target(signed, page), status_code=302, headers={'Cache-Control': 'no-store'})`.

Every exit logs `log.info('rome_pdf user_id=%s path=%s outcome=%s', ...)`.

- [ ] **Step 1: Write the failing tests.** Build a test app: `FastAPI()` + `include_router(rome.router, prefix='/api/v1/rome')`, with a `TestClient(follow_redirects=False)`. Override `get_current_user` with a fake user (`id='u1'`, `role='user'`). Monkeypatch `rome.ROME_GCS_BUCKET='corpus-b'` and `rome.sign_object_url` with a fake that returns `'https://storage.googleapis.com/corpus-b/raw/x.pdf?X-Goog-Signature=s'`. Clear `RateLimiter._memory_store` between tests.

```python
def test_valid_path_redirects_to_signed_url_with_page(): r = get('/api/v1/rome/pdf?path=raw/x.pdf&page=12'); assert r.status_code == 302 and r.headers['location'].endswith('X-Goog-Signature=s#page=12')
def test_no_page_no_fragment(): assert '#' not in get('/api/v1/rome/pdf?path=raw/x.pdf').headers['location']
def test_redirect_is_not_cacheable(): assert get('/api/v1/rome/pdf?path=raw/x.pdf').headers['cache-control'] == 'no-store'
def test_signed_out_is_401(): # no override of get_current_user, no cookie -> 401, signer never called
def test_pending_user_is_401(): # fake user role='pending' -> 401
def test_path_outside_prefix_is_400_and_not_signed(): # path=secrets/x.pdf -> 400, fake signer call count 0
def test_both_or_neither_param_is_400(): # ?path=..&src=.. -> 400 ; no params -> 400
def test_legacy_src_is_resigned(): # src=<expired corpus URL> -> 302 to fresh fake URL; signer got 'raw/c/x.pdf'
def test_legacy_uploads_bucket_is_400(): # src on stackguardian-nonprod-rome-uploads -> 400
def test_awkward_name_round_trip(): # path='raw/rome-v/Bowel Disorders_Document C (FINAL).pdf' url-encoded in the query -> signer receives the exact decoded key
def test_signing_failure_is_502_without_console_link(): # fake raises -> 502, 'storage.cloud.google.com' not in body
def test_rate_limit_is_429(): # monkeypatch limit to 2 -> third call 429
def test_unconfigured_bucket_is_503(): # rome.ROME_GCS_BUCKET = '' -> 503
def test_log_never_contains_signed_url(caplog): # 'X-Goog-Signature' not in caplog.text; 'user_id=u1' and 'outcome=' are
```

- [ ] **Step 2: Run and verify they fail**

Run: `python3 -m pytest tests/test_rome_pdf_router.py -v`
Expected: `ModuleNotFoundError: open_webui.routers.rome`.

- [ ] **Step 3: Implement the router and mount it in `main.py`.** Import the settings into `rome.py` as module-level names so the tests can monkeypatch them.

- [ ] **Step 4: Run and verify they pass, then check that `main.py` still imports**

Run: `python3 -m pytest tests/test_rome_pdf_router.py tests/test_rome_pdf_utils.py -v && python3 -m py_compile backend/open_webui/main.py`
Expected: all pass, no compile error.

- [ ] **Step 5: Commit** with `feat: sign corpus PDFs on click via /api/v1/rome/pdf`.

---

### Task 4: Plugins emit stable links; ZeroEntropy removed

**Files:**
- Modify: `functions/rome_search_filter.py`, `functions/rome_search_tool.py`
- Test: `tests/test_rome_search_tool.py`

**Interfaces:**
- Produces, in both plugin files: `build_citation_link(object_path: str, page: str) -> str`. Plugins are pasted into the Admin Panel as single files and cannot share code, so each file keeps its own copy. Returns `'/api/v1/rome/pdf?' + urlencode(params, quote_via=quote)`, where `params = {'path': object_path}` plus `'page': page` when `page.isdigit()`. Returns `''` when `object_path` is empty.
- Removed from both files:
  - functions: `build_signed_url`, `search_zeroentropy`, `normalize_zeroentropy_results`, `md_path_to_pdf_path`, `extract_page_number`, and the `RETRIEVAL_BACKEND` dispatch
  - valves: `RETRIEVAL_BACKEND`, `ROME_GCS_BUCKET`, `ZEROENTROPY_API_KEY`, `ZEROENTROPY_BASE_URL`, `COLLECTION_NAME`, `GCS_BUCKET`, `GCS_CREDENTIALS_JSON`, `SIGNED_URL_TTL_MINUTES`
  - `search_rome` and the citation event shape are otherwise unchanged; `source.url` is now `build_citation_link(snippet['object_path'], snippet['page'])`.
- Update the frontmatter `description:` lines so they no longer mention ZeroEntropy or signed URLs.

- [ ] **Step 1: Update the tests first**
  - Delete the tests that exercise the ZeroEntropy branch or `build_signed_url` in `tests/test_rome_search_tool.py`.
  - Change the citation-URL assertions to the stable link.
  - Add, for both `functions.rome_search_filter` and `functions.rome_search_tool`:

```python
def test_citation_link_with_page(): assert build_citation_link('raw/rome-v/x.pdf', '12') == '/api/v1/rome/pdf?path=raw%2Frome-v%2Fx.pdf&page=12'
def test_citation_link_omits_non_numeric_page(): assert 'page=' not in build_citation_link('raw/rome-v/x.pdf', 'N/A')
def test_citation_link_encodes_awkward_names():
    link = build_citation_link('raw/rome-v/Bowel Disorders_Document C (FINAL), é.pdf', '3')
    assert parse_qs(urlsplit(link).query)['path'] == ['raw/rome-v/Bowel Disorders_Document C (FINAL), é.pdf']
def test_emitted_citation_url_is_stable_link(): # run inlet/tool with search_rome mocked -> every emitted source.url startswith '/api/v1/rome/pdf?path=raw%2F'
def test_plugins_do_not_import_google_cloud(): # 'google.cloud' not in the source text of either file
```

- [ ] **Step 2: Run and verify the new tests fail**

Run: `python3 -m pytest tests/test_rome_search_tool.py -v`
Expected: `ImportError` on `build_citation_link`, and the stable-link assertions fail.

- [ ] **Step 3: Implement the change in both plugin files.**

- [ ] **Step 4: Run the plugin tests and the full suite**

Run: `python3 -m pytest tests/test_rome_search_tool.py -v && python3 -m pytest tests/ -q --tb=no -rf`
Expected: the plugin tests all pass. The full suite shows only the 11 failures already on `main` (Global Constraints).

- [ ] **Step 5: Commit** with `feat: rome plugins store stable citation links; drop ZeroEntropy path`.

---

### Task 5: Frontend opens citations through the endpoint

**Files:**
- Create: `src/lib/utils/citationLinks.ts`
- Create: `src/lib/utils/citationLinks.test.ts`
- Modify: `src/lib/components/chat/Messages/Citations/CitationModal.svelte`. Change the title link (~lines 103–118) and `getTextFragmentUrl` (~line 66) / the "Content" link (~line 163).

**Interfaces:**
- Produces:
  - `export const ROME_PDF_PATH = '/api/v1/rome/pdf'`
  - `isCorpusCitationUrl(url: string | null | undefined): boolean`: true for a stable link, or for an `https` URL whose host is `storage.googleapis.com`, `*.storage.googleapis.com` or `storage.cloud.google.com`
  - `resolveCitationHref(url: string | null | undefined, page: unknown, baseUrl: string): string | null`:
    - stable link → `baseUrl + url`
    - legacy GCS link → `` `${baseUrl}${ROME_PDF_PATH}?src=${encodeURIComponent(url)}` `` plus `&page=<n>` when `String(page)` is all digits
    - any other URL containing `http` → returned unchanged
    - otherwise `null`

- [ ] **Step 1: Write the failing tests**

```ts
const B = 'https://romegi.example';
it('prefixes stable links', () => expect(resolveCitationHref('/api/v1/rome/pdf?path=raw%2Fx.pdf&page=2', '2', B)).toBe(`${B}/api/v1/rome/pdf?path=raw%2Fx.pdf&page=2`));
it('rewrites legacy signed links with page', () => expect(resolveCitationHref('https://storage.googleapis.com/c/raw/x.pdf?X-Goog-Signature=a', '7', B)).toBe(`${B}/api/v1/rome/pdf?src=${encodeURIComponent('https://storage.googleapis.com/c/raw/x.pdf?X-Goog-Signature=a')}&page=7`));
it('rewrites console links', () => expect(resolveCitationHref('https://storage.cloud.google.com/c/raw/x.pdf', 'N/A', B)).toBe(`${B}/api/v1/rome/pdf?src=${encodeURIComponent('https://storage.cloud.google.com/c/raw/x.pdf')}`));
it('rewrites virtual-host links', () => expect(isCorpusCitationUrl('https://c.storage.googleapis.com/raw/x.pdf?a=1')).toBe(true));
it('leaves web links alone', () => expect(resolveCitationHref('https://pubmed.ncbi.nlm.nih.gov/1/', 1, B)).toBe('https://pubmed.ncbi.nlm.nih.gov/1/'));
it('ignores look-alike hosts', () => expect(isCorpusCitationUrl('https://storage.googleapis.com.evil.com/x.pdf')).toBe(false));
it('returns null for empty', () => expect(resolveCitationHref(undefined, null, B)).toBeNull());
```

- [ ] **Step 2: Run and verify they fail**

Run: `npx vitest run src/lib/utils/citationLinks.test.ts`
Expected: FAIL, cannot resolve `./citationLinks`.

- [ ] **Step 3: Implement the helper and wire it in.**
  - In `CitationModal.svelte`, when `isCorpusCitationUrl(source.url)` is true, both links use `resolveCitationHref(source.url, metadata?.page, WEBUI_BASE_URL)`, and the text-fragment suffix is skipped.
  - The `{#if … includes('http')}` conditions also accept `isCorpusCitationUrl(...)`, so relative stable links render as links.
  - The `file_id` branch and non-corpus URLs keep today's behaviour exactly.
  - The read-only shared view (`src/routes/s/[id]/+page.svelte`) uses the same component, so it needs no separate change (R12).

- [ ] **Step 4: Run and verify, then lint and type-check against baseline**

Run: `npx vitest run src/lib/utils/citationLinks.test.ts && npm run check 2>&1 | grep COMPLETED && npx eslint src/lib/utils/citationLinks.ts src/lib/components/chat/Messages/Citations/CitationModal.svelte`
Expected:
- vitest: all pass.
- svelte-check: the error count is no higher than `main`'s (run it on `main` first to record the baseline).
- ESLint: no new errors in `CitationModal.svelte` compared with `main`; `citationLinks.ts` is clean.

- [ ] **Step 5: Commit** with `feat: open corpus citations through the sign-on-click endpoint`.

---

### Task 6: Terraform for the Open WebUI service (this repo)

**Files:**
- Modify: `terraform/main.tf`: add `"iamcredentials.googleapis.com"` to `google_project_service.apis`
- Modify: `terraform/iam.tf`: add `google_service_account_iam_member.cloud_run_self_token_creator` with `service_account_id = google_service_account.cloud_run.name`, `role = "roles/iam.serviceAccountTokenCreator"`, `member = "serviceAccount:${google_service_account.cloud_run.email}"`
- Modify: `terraform/variables.tf`: add `variable "rome_corpus_bucket"` (string, default `"stackguardian-nonprod-rome-corpus"`)
- Modify: `terraform/cloudrun.tf`: add `env` blocks `ROME_GCS_BUCKET = var.rome_corpus_bucket` and `ROME_PDF_URL_TTL_MINUTES = "2880"`, in the existing block style
- Leave the `pdf_signer` resources alone; they are retired after rollout.

- [ ] **Step 1: Make the edits.**
- [ ] **Step 2: Verify**

Run: `cd terraform && terraform fmt -check && TF_DATA_DIR=/tmp/tf-sign terraform init -backend=false -input=false >/dev/null && TF_DATA_DIR=/tmp/tf-sign terraform validate`
Expected: no `fmt` output; `Success! The configuration is valid.`

- [ ] **Step 3: Commit** with `infra: let Cloud Run sign corpus URLs keylessly`.

---

### Task 7: Corpus bucket read access (rome-ingestion-search repo, separate PR)

**Files:**
- Modify: `../rome-ingestion-search/infra/iam.tf`. Next to `pdf_signer_corpus`, add `google_storage_bucket_iam_member.openwebui_corpus_reader` with `bucket = google_storage_bucket.corpus.name`, `role = "roles/storage.objectViewer"`, `member = local.openwebui_sa`. `local.openwebui_sa` is already defined in `infra/data.tf`.

That repo is checked out on `feat/rome-v-refs-ingest` with an untracked `scripts/upload_pdfs.sh`. Create a new branch from its `main` and leave the untracked file alone.

- [ ] **Step 1: Make the edit on a new branch.**
- [ ] **Step 2: Verify**

Run: `cd ../rome-ingestion-search/infra && terraform fmt -check && TF_DATA_DIR=/tmp/tf-corpus terraform init -backend=false -input=false >/dev/null && TF_DATA_DIR=/tmp/tf-corpus terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit** with `infra: let the Open WebUI service account read the corpus`.

---

### Task 8: End-to-end verification

No new code; this checks the PRD's acceptance tests against a running build.

- [ ] **Step 1: Local run.**
  - Start the backend from source with `STATIC_DIR` pointed at a temp directory. Without it, startup wipes the committed `backend/open_webui/static/` files (upstream `config.py:836`).
  - Set `ROME_GCS_BUCKET=<corpus bucket>` and `ROME_PDF_SIGNER_CREDENTIALS_JSON=<a nonprod key>`; local machines can't use keyless signing.
  - Start `npm run dev` for the frontend.
- [ ] **Step 2: With Playwright, record the result of each check:**
  1. Ask a question and click a citation: the PDF opens at the cited page (R1, R5, R6).
  2. Open a chat whose stored `source.url` is an expired `storage.googleapis.com` corpus link (seed one through the chat API): clicking opens the PDF (R8).
  3. Open the stable link in a fresh, signed-out context: 401, no PDF (R2).
  4. Open a chat with many citations and record network requests: no `/api/v1/rome/pdf` calls until a click (R9).
  5. Share a chat, open `/s/<id>` as a second signed-in user and click a citation: the PDF opens (R12).
  6. Click a Markdown corpus citation: it opens, not a 400 (Review Focus 2).
- [ ] **Step 3:** After deploying to nonprod, repeat checks 1, 2 and 5 against Cloud Run, where signing is keyless.

---

## Rollout (production)

1. Apply Task 7 (rome-ingestion-search infra), then Task 6 (this repo's infra).
2. Deploy the image (Tasks 1–3, 5). From this point every old corpus link works again through the legacy rewrite.
3. In the Admin Panel, paste the updated `rome_search_filter.py` (**Workspace → Functions**) and `rome_search_tool.py` (**Workspace → Tools**). New answers then store stable links.
4. Monitoring (PRD): in Cloud Logging, create log-based metrics on the `rome_pdf … outcome=` lines (clicks, 4xx by outcome, 5xx), plus an alert when 5xx exceeds 1% over 15 minutes. That alert most likely means a lost IAM permission. This is a console step; the repos don't manage monitoring in Terraform today.
5. Watch the endpoint's 5xx count. After a week with no signing errors, clear the `GCS_CREDENTIALS_JSON` valve values, delete the `rome-pdf-signer` key, and remove the `pdf_signer` Terraform resources in both repos.
