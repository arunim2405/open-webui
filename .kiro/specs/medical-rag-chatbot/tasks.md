# Implementation Plan: Medical RAG Chatbot

## Overview

Configure Open WebUI as a single-purpose RAG medical chatbot by creating four artifacts: a `docker-compose.yaml` with environment variables, a ZeroEntropy Retrieval Filter function, a ZeroEntropy Search Tool function, and a Workspace Model configuration JSON. All property-based tests use Python `hypothesis`. No core Open WebUI source code is modified.

## Tasks

- [x] 1. Create Docker Compose configuration
  - [x] 1.1 Create `docker-compose.yaml` with Open WebUI service
    - Use image `ghcr.io/open-webui/open-webui:main`
    - Define persistent volume `open-webui` mounted at `/app/backend/data`
    - Map port `3000:8080`
    - Set all environment variables: `OPENAI_API_BASE_URL`, `OPENAI_API_KEY`, `ENABLE_OLLAMA_API=false`, `WEBUI_NAME=Rome Medical Assistant`, `DEFAULT_MODELS=gpt-5.4`, `ENABLE_IMAGE_GENERATION=false`, `ENABLE_COMMUNITY_SHARING=false`, `ENABLE_WEB_SEARCH=false`, `ENABLE_CODE_INTERPRETER=false`, `WEBUI_AUTH=true`
    - Set `WEBUI_BANNERS` with non-dismissible warning banner JSON containing the medical disclaimer text
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.3_

  - [x] 1.2 Write unit tests for Docker Compose validation
    - Parse `docker-compose.yaml` with PyYAML and assert every environment variable, port mapping, volume, image, and banner JSON structure
    - _Requirements: 1.1–1.12, 5.1–5.6, 6.1, 6.3_

- [x] 2. Implement shared utilities for ZeroEntropy integration
  - [x] 2.1 Create page extraction utility function
    - Implement `extract_page_number(snippet_text: str) -> str` that finds the nearest preceding `<!-- page: N -->` marker via regex
    - Return `"N/A"` when no marker is found
    - _Requirements: 2.4, 3.8_

  - [x] 2.2 Write property test for page marker extraction
    - **Property 1: Page marker extraction**
    - Generate random snippet texts with embedded `<!-- page: N -->` markers at random positions; verify extraction returns the correct nearest preceding page number; verify default for no markers
    - **Validates: Requirements 2.4, 3.8**

  - [x] 2.3 Create snippet formatting utility function
    - Implement `format_snippets(results: list) -> str` that produces numbered context blocks with source filename and page number
    - _Requirements: 2.3, 3.3_

  - [x] 2.4 Write property test for snippet formatting
    - **Property 3: Snippet formatting**
    - Generate random lists of snippet objects with `document_path` and `snippet` fields; verify formatted output contains one numbered entry per snippet with source and page
    - **Validates: Requirements 2.3, 3.3**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement ZeroEntropy Retrieval Filter Function
  - [x] 4.1 Create the Retrieval Filter Python file
    - Implement `Filter` class with `Valves` inner class (ZEROENTROPY_API_KEY, ZEROENTROPY_BASE_URL, COLLECTION_NAME, SNIPPET_COUNT, priority)
    - Implement `inlet(self, body: dict, __event_emitter__) -> dict`:
      - Extract last user message from `body["messages"]`
      - Return body unmodified if no user messages
      - POST to `{base_url}/queries/top-snippets` using `aiohttp` with query, collection, and k
      - Format snippets using shared utility, prepend as system message
      - Emit citation events for each snippet
      - On API failure, emit error status event and return unmodified body
    - Implement `outlet(self, body: dict, __event_emitter__) -> dict`:
      - Find last assistant message, append medical disclaimer footer
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 6.2_

  - [x] 4.2 Write property test for context injection
    - **Property 4: Context injection as system message**
    - Generate random message arrays and snippet lists; verify system message is prepended containing all context blocks and original messages remain intact and in order
    - **Validates: Requirements 2.5**

  - [x] 4.3 Write property test for citation event emission
    - **Property 5: Citation event emission**
    - Generate random snippet lists of size N ≥ 1; verify exactly N citation events are emitted, each with correct type, source filename, and page number
    - **Validates: Requirements 2.6, 3.5**

  - [x] 4.4 Write property test for outlet disclaimer appending
    - **Property 6: Outlet disclaimer appending**
    - Generate random assistant response strings; verify the result ends with the medical disclaimer footer and original content is preserved
    - **Validates: Requirements 2.7, 6.2**

  - [x] 4.5 Write unit tests for Retrieval Filter
    - Test error handling: API failure returns unmodified body and emits error status event
    - Test empty messages array returns body unmodified
    - Test snippets without page markers use default page value
    - _Requirements: 2.9, 2.10_

- [x] 5. Implement ZeroEntropy Search Tool Function
  - [x] 5.1 Create the Search Tool Python file
    - Implement `Tools` class with `Valves` inner class (ZEROENTROPY_API_KEY, ZEROENTROPY_BASE_URL, COLLECTION_NAME)
    - Implement `search_medical_literature(self, query: str, k: int = 5, __event_emitter__) -> str`:
      - Emit status event "Searching medical literature..."
      - POST to `{base_url}/queries/top-snippets` using `aiohttp`
      - Extract page numbers, format results as numbered entries
      - Emit status event "Found N passages"
      - Emit citation events for each passage
      - On failure, return descriptive error message string
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 5.2 Write property test for API request construction
    - **Property 2: ZeroEntropy API request construction**
    - Generate random query strings and positive integer k values; verify constructed payload contains exactly `query`, `collection`, and `k` fields with correct values and POST target is `{base_url}/queries/top-snippets`
    - **Validates: Requirements 2.2, 3.2**

  - [x] 5.3 Write property test for status event emission
    - **Property 7: Status event emission for tool searches**
    - Generate random result counts N ≥ 0; verify at least two status events are emitted: one for search initiation and one for completion with correct count N
    - **Validates: Requirements 3.4**

  - [x] 5.4 Write unit tests for Search Tool
    - Test API failure returns descriptive error message
    - Test page extraction from snippets with and without markers
    - _Requirements: 3.7, 3.8_

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Create Workspace Model configuration
  - [x] 7.1 Create Workspace Model JSON configuration file
    - Define model with id `rome-medical-assistant`, name `Rome Medical Assistant`, base_model_id `gpt-5.4`
    - Set params: temperature `0.2`, max_tokens `1024`
    - Set capabilities: vision false, image_generation false, code_interpreter false, web_search false, tool_use true
    - Attach filter ID `zeroentropy-retrieval-filter` and tool ID `zeroentropy-search-tool`
    - Include the full medical system prompt (DGBI specialist, citation rules, scope restrictions)
    - Include 6 prompt suggestions: IBS criteria, DGBI classification, brain-gut axis, questionnaire validation, functional dyspepsia, RFGES epidemiology
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 7.2 Write unit tests for Workspace Model configuration
    - Validate JSON structure, all field values, system prompt content, prompt suggestion count and topics
    - _Requirements: 4.1–4.8_

- [x] 8. Wire components together and create verification scripts
  - [x] 8.1 Create post-deployment verification script
    - Write a Python script with curl-equivalent requests using `requests` or `aiohttp`:
      - Verify ZeroEntropy collection exists via POST to `/collections/get-collection-list`
      - Verify snippet retrieval via POST to `/queries/top-snippets` with test query
    - Include instructions for manual chat verification (citation display, disclaimer footer, banner visibility)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 8.2 Create `.env.example` for deployment secrets
    - Document required environment variables: `OPENAI_API_KEY`, `ZEROENTROPY_API_KEY`
    - _Requirements: 1.2, 2.8, 3.6_

- [x] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–7)
- Unit tests validate specific examples, edge cases, and structural correctness
- All Python code uses `aiohttp` for async HTTP and `hypothesis` for property-based testing
