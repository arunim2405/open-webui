# Rome Medical Assistant — Deployment Guide

A RAG-powered medical research chatbot built on Open WebUI. It retrieves passages from ~3,700 medical documents via ZeroEntropy and uses GPT-5.4 to generate grounded, cited answers about DGBI and Rome Foundation diagnostic criteria.

## Prerequisites

- Docker and Docker Compose
- An OpenAI API key (with access to `gpt-5.4`)
- A ZeroEntropy API key (with the `markdown_output` collection already indexed)

## Project Structure

```
├── docker-compose.medical.yaml          # Docker Compose for the medical chatbot
├── .env.medical.example                 # Template for required API keys
├── functions/
│   ├── zeroentropy_utils.py             # Shared utilities (page extraction, snippet formatting)
│   ├── zeroentropy_retrieval_filter.py  # Filter plugin — auto-retrieves context for every query
│   └── zeroentropy_search_tool.py       # Tool plugin — LLM-invokable follow-up search
├── config/
│   └── workspace_model.json             # Workspace Model definition (Rome Medical Assistant)
├── scripts/
│   └── verify_deployment.py             # Post-deployment verification script
└── tests/                               # Unit + property-based tests (89 total)
```

## Quick Start

### 1. Set up environment variables

```bash
cp .env.medical.example .env
```

Edit `.env` and fill in your actual keys:

```
OPENAI_API_KEY=sk-your-actual-key
ZEROENTROPY_API_KEY=ze-your-actual-key
```

### 2. Start the container

```bash
docker compose -f docker-compose.medical.yaml --env-file .env up -d
```

Open WebUI will be available at **http://localhost:3000**.

### 3. Create your admin account

On first launch, Open WebUI prompts you to create an admin account. Complete the signup — this is required since `WEBUI_AUTH=true`.

### 4. Install the Filter function

1. Go to **Workspace → Functions** in the admin panel.
2. Click **Create a new function** and select type **Filter**.
3. Set the function ID to `zeroentropy-retrieval-filter`.
4. Paste the contents of `functions/zeroentropy_retrieval_filter.py` into the code editor.
   - Note: you'll need to inline the shared utilities from `functions/zeroentropy_utils.py` (the `extract_page_number` and `format_snippets` functions) at the top of the file, since Open WebUI functions are self-contained.
5. Save and enable the function.
6. Click the **Valves** (⚙️) icon and configure:
   - `ZEROENTROPY_API_KEY`: your ZeroEntropy API key
   - `ZEROENTROPY_BASE_URL`: `https://api.zeroentropy.dev/v1` (default)
   - `COLLECTION_NAME`: `markdown_output` (default)
   - `SNIPPET_COUNT`: `5` (default)

### 5. Install the Tool function

1. Go to **Workspace → Functions** and create another function, type **Tool**.
2. Set the function ID to `zeroentropy-search-tool`.
3. Paste the contents of `functions/zeroentropy_search_tool.py` (again inlining the shared utils).
4. Save and enable.
5. Configure Valves with the same ZeroEntropy API key and settings.

### 6. Create the Workspace Model

1. Go to **Workspace → Models** and click **Create a new model**.
2. Configure it manually using the values in `config/workspace_model.json`:
   - Name: `Rome Medical Assistant`
   - Base Model: `gpt-5.4`
   - Temperature: `0.2`, Max Tokens: `1024`
   - System prompt: copy from the JSON file
   - Attach the filter (`zeroentropy-retrieval-filter`) and tool (`zeroentropy-search-tool`)
   - Disable vision, image generation, code interpreter, web search
   - Enable tool use
   - Add the 6 prompt suggestions from the JSON file

Alternatively, you can use the Open WebUI API to import the model configuration programmatically.

## Verification

### Automated checks

Verify the ZeroEntropy API connection and collection:

```bash
export ZEROENTROPY_API_KEY=ze-your-actual-key
python3 scripts/verify_deployment.py
```

This checks that the `markdown_output` collection exists and returns snippets for a test query.

### Manual checks

After deployment, verify in the browser:

1. The warning banner appears at the top of the UI (non-dismissible)
2. Send a question like "What are the Rome V diagnostic criteria for IBS?"
3. Confirm the response includes citations with document names and page numbers
4. Confirm every response ends with the medical disclaimer footer

## Running Tests

Install test dependencies:

```bash
pip install pytest pytest-asyncio hypothesis pyyaml aiohttp pydantic
```

Run the full test suite:

```bash
python3 -m pytest tests/ -v
```

The suite includes 89 tests: unit tests for configuration validation and property-based tests (using Hypothesis) that verify 7 correctness properties across all components.

## Architecture

```
User → Open WebUI → Retrieval Filter (inlet) → ZeroEntropy API
                                                      ↓
                   GPT-5.4 ← context-augmented messages
                      ↓
                   Retrieval Filter (outlet) → response + disclaimer → User
                      ↓ (optional)
                   Search Tool → ZeroEntropy API → additional context
```

Every user message automatically triggers the Retrieval Filter, which fetches relevant passages and injects them as context before GPT-5.4 sees the query. The Search Tool is available for the LLM to invoke when it needs additional context for complex questions. Every response gets a medical disclaimer appended by the outlet.

## Configuration Reference

| Setting | Value | Where |
|---|---|---|
| OpenAI API Key | `sk-...` | `.env` → Docker env var |
| ZeroEntropy API Key | `ze-...` | Open WebUI Valves (admin panel) |
| Collection Name | `markdown_output` | Valves (default) |
| Snippet Count | `5` | Filter Valves (default) |
| Base Model | `gpt-5.4` | Workspace Model config |
| Temperature | `0.2` | Workspace Model config |
| Max Tokens | `1024` | Workspace Model config |
| Port | `3000` | `docker-compose.medical.yaml` |
