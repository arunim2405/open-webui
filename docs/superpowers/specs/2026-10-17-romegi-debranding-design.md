# RomeGI: remove Open WebUI branding and simplify user settings (iteration 1)

Date: 2026-10-17
Repo: `arunim2405/open-webui` fork (v0.8.12), deployed to Cloud Run via `cloudbuild.yaml` + `terraform/`

## Intent

The Rome medical research assistant runs on a fork of Open WebUI. Today it still looks and reads like Open WebUI: the "OI" logo, "Open WebUI" in the tab title, a forced " (Open WebUI)" suffix on the product name, release-notes popups, links to the upstream project, and a settings area full of power-user features. The users are clinicians and researchers asking questions about Rome V and disorders of gut-brain interaction (DGBI) and expecting cited answers. The goal is for the product to feel like an in-house product called **RomeGI**.

The project has a license agreement with Open WebUI that permits modifying and removing branding in this fork.

## Goals

1. A regular user never sees the words "Open WebUI", the OI logo, or links to the upstream project (openwebui.com, GitHub, Discord) on any screen they can reach. The main screens are **login, signup and chat**.
2. The product name is **RomeGI** everywhere it is shown: browser tab title, login and signup headings, PWA/web-app install name, OpenSearch name, and in-app references.
3. Regular users see a reduced settings area and UI. Admins see everything.
4. The reduction is controlled by configuration (an environment variable), not by deleting code.

## Non-goals

- **No visual redesign.** Layout, colors, typography and screen structure stay as they are. (The user considered login redesign directions and explicitly deferred them.)
- No renaming of internal identifiers users never see: the `open_webui` Python package, `WEBUI_*` / other env var names, API paths, the database, Docker service names.
- No changes to the Admin Panel's features.
- No real logo design. Real brand assets come later.

## Anti-goals (would be a failure even if it "works")

- Removing features outright instead of hiding them. The user requires that hidden features can come back by changing configuration alone.
- Hiding anything from admins.
- Broad renames or reformatting across the codebase that make pulling future upstream Open WebUI releases painful. Keep the diff small and focused.
- Breaking the existing Rome configuration: the Rome model, the ZeroEntropy retrieval filter and search tool, citation badges, and the non-dismissible medical disclaimer banner must work exactly as before.

## Decisions made with the user

| Topic | Decision |
|---|---|
| Base | The current fork (v0.8.12). No upstream rebase. |
| Product name | **RomeGI** |
| Logo | A simple text "RomeGI" placeholder (wordmark/monogram) for all logo, favicon, splash and app-icon slots, until real assets exist. |
| Scope | Branding removal + settings reduction only. No redesign. |
| Settings | Hidden behind an environment variable / feature flag, **not removed**. |
| Admins | Keep everything. |

## What regular users keep and lose (proposed by me, accepted by the user)

When the reduced mode is on, a non-admin user:

**Keeps:** chat (with the Rome model), the rest of the chat screen as-is (file upload in the "+" menu, voice input/call, temporary chat, share, folders, notes, search), chat history in the sidebar, and in settings: name, profile photo, password, light/dark theme, language.

**Loses (hidden):**
- Model picker. Users always chat with the Rome model (see "Model pinning" below).
- Chat controls side panel (system prompt, parameters, valves). It can change how the Rome model answers and cites.
- The tools / integrations part of the message-input "+" menu, for the same reason.
- Workspace (models, prompts, tools, knowledge)
- Settings tabs: Interface, Connections, Tools / Integrations, Personalization (memory), Audio, Data Controls, About
- Inside the tabs that stay (General, Account): the user System Prompt and Advanced Parameters (they are added to every request and can override the Rome model's citation behaviour), API keys, JWT token, notification webhook, and any other fields not in the "Keeps" list.
- The "What's new" changelog modal and the version-update toast
- Any remaining upstream links or version strings in user-reachable menus (e.g. user menu, error page)

**Deferred to a later iteration (user's decision):** hiding other chat-screen features such as voice, temporary chat, share, folders, notes and search.

**Mechanism (my call, revised after review):** the single new environment variable drives *all* of the hiding above in the frontend, gated on `role !== 'admin'`. Don't depend on Open WebUI's per-user permissions for this. Those are persistent DB settings that Terraform env vars can't reliably change once set, and the user asked for env-var control.

## Model pinning (my call)

Production currently sets `DEFAULT_MODELS=gpt-5.4`, the bare base model. `rome-medical-assistant` (from `config/workspace_model.json`) wraps it with the retrieval filter, search tool and disclaimer. If users land on the bare model, hiding the picker silently removes retrieval and citations, which breaks an anti-goal. So:

- Set `DEFAULT_MODELS=rome-medical-assistant` in `terraform/` and `docker-compose.medical.yaml`.
- Make the base `gpt-5.4` model not visible to regular users (model access control).
- Because `DEFAULT_MODELS` and model access are persistent DB settings (`ENABLE_PERSISTENT_CONFIG` defaults to true), the rollout includes a **documented one-time Admin Panel step** to set the default model and the base model's visibility in production. Write this step down in the plan's rollout notes.

The model's display name stays **"Rome Medical Assistant"** (user's decision). Don't rename it.

## Branding work

These apply to every screen a regular user can reach, plus shared surfaces (tab title, favicon, login/signup, popups). **Admin-only screens (Admin Panel, workspace editors, function editor) are left untouched (my call).** That keeps the diff small and upstream merges easy, and admins keep the upstream docs and community links that help them operate the product. For admins, the About tab, changelog modal and update toast stay as they are. They're hidden only for regular users when the flag is on.

1. **Forced suffix:** remove the logic at `backend/open_webui/env.py:129-130` that appends " (Open WebUI)" to `WEBUI_NAME`.
2. **Default name:** set `WEBUI_NAME=RomeGI` in deploy config (`terraform/` Cloud Run env, `docker-compose.medical.yaml`). Hard-coded "Open WebUI" strings shown in the UI should read from the configured name, not a new hard-coded "RomeGI", where practical.
3. **Static strings:** `src/app.html` `<title>`, `static/static/site.webmanifest`, `static/manifest.json`, `static/opensearch.xml`, FastAPI app title in `backend/open_webui/main.py` (shows on API docs pages).
4. **Assets:** replace `static/static/logo.png`, `favicon.*`, `apple-touch-icon.png`, `splash.png`, `splash-dark.png`, `web-app-manifest-*.png`, `static/favicon.png` with the RomeGI placeholder. Same file names and dimensions so no code has to change.
5. **Upstream links and popups:** the About tab, `ChangelogModal`, `UpdateInfoToast`, links to openwebui.com / GitHub / Discord in user-reachable places. Set `ENABLE_VERSION_UPDATE_CHECK=false` in deploy config so the server stops calling GitHub for releases.
6. **Translations:** user-visible "Open WebUI" strings in `src/lib/i18n` locales should show the product name too, at least for English.

A starting inventory of frontend files mentioning Open WebUI, GitHub or Discord (about 40 files outside i18n) can be regenerated with:
`grep -rIl -i "open webui\|openwebui\.com\|github.com/open-webui\|discord" src --exclude-dir=i18n`
Most are admin- or workspace-only. Prioritise what regular users can reach.

## Constraints

- Stack: SvelteKit 5 + TypeScript + Tailwind 4 frontend, FastAPI backend (see repo `CLAUDE.md`).
- Production image is built from this fork (`cloudbuild.yaml`, image in `terraform/variables.tf`). `docker-compose.medical.yaml` currently pulls the **stock** `ghcr.io/open-webui/open-webui:main` image, so it can't be used to verify these changes as-is.
- Existing tests in `tests/` (89 tests) must keep passing. **Exception (my call):** `tests/test_docker_compose.py` asserts the old `WEBUI_NAME` ("Rome Medical Assistant", ~line 94) and the stock image (~line 44). Update those assertions to the new values. `tests/test_workspace_model.py` stays unchanged because the model name is not changing.
- **Local verification (my call):** switch `docker-compose.medical.yaml` from the stock image to building this fork (`build: .`), so the changes can actually be seen locally.

## Left to the builder

- The flag's name and exact mechanism (one env var surfaced to the frontend via the existing `/api/config` payload is the expected shape), and its default (my call: default **off**, so stock behaviour is unchanged unless enabled; deploy config turns it on).
- The exact look of the placeholder logo, within "simple, text-based, legible at favicon size".
- How to verify. A reasonable bar: log in as a regular user and as an admin on a local build of the fork, and confirm no "Open WebUI" text, OI logo or upstream link on login, signup, chat, sidebar, user menu and settings. Confirm the admin still sees everything.
