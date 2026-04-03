# Requirements Document

## Introduction

This document specifies the requirements for configuring Open WebUI as a single-purpose RAG medical chatbot ("Rome V Medical Assistant") for a gastroenterology research team. The system retrieves relevant passages from a ZeroEntropy-hosted collection of ~3,700 medical documents covering DGBI, Rome V diagnostic criteria, and related GI literature, then uses GPT-5.4 to generate grounded, cited answers. All customization is achieved through Open WebUI's plugin system (Filter functions, Tool functions, Workspace Models) and environment variables — no core source code modifications.

## Glossary

- **Open_WebUI**: The open-source web interface application deployed via Docker that serves as the chat frontend and plugin host.
- **ZeroEntropy_API**: The hosted semantic search service at `https://api.zeroentropy.dev/v1` that indexes the medical document collection and provides snippet, page, and document retrieval endpoints.
- **Retrieval_Filter**: An Open WebUI Filter function (with `inlet` and `outlet` methods) that automatically intercepts every user message, retrieves context from ZeroEntropy_API, and injects it before the LLM generates a response.
- **Search_Tool**: An Open WebUI Tool function the LLM can invoke on-demand to perform a targeted sub-query against ZeroEntropy_API.
- **Workspace_Model**: An Open WebUI model configuration ("Rome V Medical Assistant") that binds a base LLM, system prompt, parameters, filters, and tools into a single selectable model.
- **Valves**: Open WebUI's configuration mechanism that exposes tunable parameters (API keys, collection names, retrieval count) on Filter and Tool functions via the admin UI.
- **Inlet**: The pre-processing hook in a Filter function, executed before the user's message reaches the LLM.
- **Outlet**: The post-processing hook in a Filter function, executed after the LLM generates a response.
- **DGBI**: Disorders of Gut-Brain Interaction, the primary medical domain covered by the document corpus.
- **Collection**: The ZeroEntropy_API index named `markdown_output` containing the ingested medical Markdown documents.
- **Page_Marker**: An HTML comment (`<!-- page: N -->`) embedded in each document that delineates page boundaries for citation purposes.
- **Docker_Compose_File**: The `docker-compose.yaml` configuration file that defines the Open_WebUI container, its environment variables, volumes, and port mappings.
- **GPT_5_4**: The OpenAI language model (`gpt-5.4`) used as the base LLM for generating responses.
- **Event_Emitter**: Open WebUI's mechanism for sending real-time status updates and citation events to the chat UI during function execution.

## Requirements

### Requirement 1: Docker Deployment Configuration

**User Story:** As a system administrator, I want to deploy Open WebUI via Docker with the correct environment variables, so that the application runs as a medical-only chatbot connected to OpenAI with unnecessary features disabled.

#### Acceptance Criteria

1. THE Docker_Compose_File SHALL define an Open_WebUI service using the `ghcr.io/open-webui/open-webui:main` image with a persistent volume mounted at `/app/backend/data`.
2. THE Docker_Compose_File SHALL configure the OpenAI API connection by setting `OPENAI_API_BASE_URL` to `https://api.openai.com/v1` and `OPENAI_API_KEY` to the provided API key environment variable.
3. THE Docker_Compose_File SHALL disable the Ollama integration by setting `ENABLE_OLLAMA_API` to `false`.
4. THE Docker_Compose_File SHALL set `WEBUI_NAME` to `Rome Medical Assistant`.
5. THE Docker_Compose_File SHALL set `DEFAULT_MODELS` to `gpt-5.4`.
6. THE Docker_Compose_File SHALL disable built-in image generation by setting `ENABLE_IMAGE_GENERATION` to `false`.
7. THE Docker_Compose_File SHALL disable community sharing by setting `ENABLE_COMMUNITY_SHARING` to `false`.
8. THE Docker_Compose_File SHALL disable web search by setting `ENABLE_WEB_SEARCH` to `false`.
9. THE Docker_Compose_File SHALL disable the code interpreter by setting `ENABLE_CODE_INTERPRETER` to `false`.
10. THE Docker_Compose_File SHALL configure a medical disclaimer banner using the `WEBUI_BANNERS` environment variable with a non-dismissible warning banner stating that responses are for research purposes only and do not constitute medical advice.
11. THE Docker_Compose_File SHALL set `WEBUI_AUTH` to `true` to require user authentication.
12. THE Docker_Compose_File SHALL expose port 3000 on the host mapped to port 8080 in the container.

### Requirement 2: ZeroEntropy Retrieval Filter Function

**User Story:** As a medical researcher, I want every question I ask to automatically retrieve relevant passages from the medical literature, so that the LLM's response is grounded in the actual document corpus without requiring manual search steps.

#### Acceptance Criteria

1. THE Retrieval_Filter SHALL implement an `inlet` method that intercepts the user's latest message before it reaches GPT_5_4.
2. WHEN the `inlet` method is invoked, THE Retrieval_Filter SHALL send a POST request to the ZeroEntropy_API `/queries/top-snippets` endpoint with the user's query, the configured collection name, and the configured `k` value.
3. WHEN ZeroEntropy_API returns snippets, THE Retrieval_Filter SHALL format each snippet as a numbered context block including the source document filename and extracted page number.
4. WHEN a snippet contains a Page_Marker (`<!-- page: N -->`), THE Retrieval_Filter SHALL extract the page number from the nearest preceding marker for citation attribution.
5. THE Retrieval_Filter SHALL inject the formatted context block as a system message prepended to the conversation messages array.
6. WHEN ZeroEntropy_API returns snippets, THE Retrieval_Filter SHALL emit citation events via the Event_Emitter containing source filename and page number for each retrieved passage.
7. THE Retrieval_Filter SHALL implement an `outlet` method that appends a medical disclaimer footer to every LLM response stating that the information is for research purposes only and does not constitute medical advice.
8. THE Retrieval_Filter SHALL expose Valves for: ZeroEntropy API key, ZeroEntropy base URL, collection name, and snippet count (`k`) with sensible defaults.
9. IF the ZeroEntropy_API request fails, THEN THE Retrieval_Filter SHALL emit an error status event via the Event_Emitter and allow the query to proceed to the LLM without retrieved context.
10. THE Retrieval_Filter SHALL use `aiohttp` for asynchronous HTTP requests to ZeroEntropy_API.
11. THE Retrieval_Filter SHALL set a priority valve defaulting to `0` so that it executes in the expected order relative to other filters.

### Requirement 3: ZeroEntropy Search Tool Function

**User Story:** As a medical researcher, I want the LLM to be able to perform targeted follow-up searches against the medical literature on its own, so that it can retrieve additional context for complex multi-part questions.

#### Acceptance Criteria

1. THE Search_Tool SHALL expose a `search_medical_literature` method callable by the LLM with parameters `query` (string) and `k` (integer, default 5).
2. WHEN `search_medical_literature` is invoked, THE Search_Tool SHALL send a POST request to the ZeroEntropy_API `/queries/top-snippets` endpoint with the provided query, configured collection name, and specified `k` value.
3. WHEN ZeroEntropy_API returns snippets, THE Search_Tool SHALL format results as numbered entries with source filename, page number, and snippet text.
4. THE Search_Tool SHALL emit status update events via the Event_Emitter indicating retrieval progress (e.g., "Searching medical literature..." and "Found N passages").
5. WHEN ZeroEntropy_API returns snippets, THE Search_Tool SHALL emit citation events via the Event_Emitter for each retrieved passage containing source filename and page number.
6. THE Search_Tool SHALL expose Valves for: ZeroEntropy API key, ZeroEntropy base URL, and collection name with sensible defaults.
7. IF the ZeroEntropy_API request fails, THEN THE Search_Tool SHALL return a descriptive error message indicating the failure reason.
8. THE Search_Tool SHALL extract page numbers from Page_Marker HTML comments in the retrieved snippet content.

### Requirement 4: Workspace Model Configuration

**User Story:** As a medical researcher, I want a pre-configured "Rome V Medical Assistant" model available in the chat interface, so that I can start asking clinical questions immediately with the correct system prompt, parameters, and retrieval pipeline attached.

#### Acceptance Criteria

1. THE Workspace_Model SHALL be named "Rome Medical Assistant" with `gpt-5.4` as the base model.
2. THE Workspace_Model SHALL set temperature to `0.2` and max output tokens to `1024`.
3. THE Workspace_Model SHALL have the Retrieval_Filter attached in its filter IDs configuration.
4. THE Workspace_Model SHALL have the Search_Tool attached in its tool IDs configuration.
5. THE Workspace_Model SHALL disable Image Generation, Code Interpreter, and Web Search capabilities.
6. THE Workspace_Model SHALL enable Tool Use capability so the LLM can invoke the Search_Tool.
7. THE Workspace_Model SHALL include a system prompt that instructs the LLM to: act as a medical research assistant specializing in DGBI and the Rome Foundation diagnostic framework, cite sources with document name and page number for every factual claim, use only the retrieved context to answer questions, explicitly state when retrieved context is insufficient to answer a question, and decline questions outside the gastroenterology and DGBI scope.
8. THE Workspace_Model SHALL include at least six prompt suggestions covering: IBS diagnostic criteria, DGBI classification evolution, brain-gut axis mechanisms, diagnostic questionnaire validation, functional dyspepsia subtypes, and RFGES epidemiological findings.

### Requirement 5: UI Feature Restriction

**User Story:** As a system administrator, I want to hide chat features irrelevant to the medical research use case, so that the interface remains focused and researchers are not confused by unrelated capabilities.

#### Acceptance Criteria

1. THE Open_WebUI SHALL disable image generation functionality via the `ENABLE_IMAGE_GENERATION` environment variable set to `false`.
2. THE Open_WebUI SHALL disable web search functionality via the `ENABLE_WEB_SEARCH` environment variable set to `false`.
3. THE Open_WebUI SHALL disable community sharing functionality via the `ENABLE_COMMUNITY_SHARING` environment variable set to `false`.
4. THE Open_WebUI SHALL disable the code interpreter via the `ENABLE_CODE_INTERPRETER` environment variable set to `false`.
5. THE Open_WebUI SHALL set `DEFAULT_MODELS` to `gpt-5.4` so that the Workspace_Model is pre-selected for new conversations.
6. THE Open_WebUI SHALL disable Ollama API integration via the `ENABLE_OLLAMA_API` environment variable set to `false` to prevent display of local model options.

### Requirement 6: Medical Disclaimers

**User Story:** As a compliance officer, I want medical disclaimers displayed prominently in the UI and appended to every response, so that users understand the system's output does not constitute medical advice.

#### Acceptance Criteria

1. THE Open_WebUI SHALL display a persistent, non-dismissible banner at the top of the interface stating: "⚕️ Research Tool Only — Responses are generated from indexed medical literature and do not constitute medical advice. Always consult qualified healthcare professionals for clinical decisions."
2. THE Retrieval_Filter outlet SHALL append a disclaimer footer to every LLM response stating: "---\n⚕️ *This response was generated from indexed medical literature and does not constitute medical advice. Always verify findings against primary sources and consult qualified healthcare professionals for clinical decisions.*"
3. THE banner disclaimer SHALL be configured via the `WEBUI_BANNERS` environment variable as a `warning` type banner.

### Requirement 7: Post-Deployment Verification

**User Story:** As a system administrator, I want a set of verification steps to confirm the deployment is working end-to-end, so that I can validate the retrieval pipeline, citations, and disclaimers before handing the system to researchers.

#### Acceptance Criteria

1. WHEN a POST request is sent to ZeroEntropy_API `/collections/get-collection-list`, THE ZeroEntropy_API SHALL return a response containing the `markdown_output` collection.
2. WHEN a POST request is sent to ZeroEntropy_API `/queries/top-snippets` with query "What are the Rome V diagnostic criteria for IBS?" and k=3, THE ZeroEntropy_API SHALL return at least one snippet containing relevant content.
3. WHEN a user sends the message "What are the Rome IV diagnostic criteria for IBS?" through the Workspace_Model, THE system SHALL return a response that includes cited source references with document names and page numbers.
4. WHEN a user sends any message through the Workspace_Model, THE system SHALL display the medical disclaimer footer appended to the response.
5. WHEN a user opens the Open_WebUI interface, THE system SHALL display the non-dismissible medical disclaimer banner at the top of the page.
