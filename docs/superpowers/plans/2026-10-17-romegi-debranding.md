# RomeGI De-branding and Simplified UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Open WebUI fork read as an in-house product called RomeGI, and hide power-user features from non-admin users behind one environment variable.

**Architecture:** The backend drops the forced " (Open WebUI)" name suffix and exposes a new boolean `features.romegi_simplified_ui` in `/api/config`. The frontend derives one store, `simplifiedUI` (true only when the flag is on **and** the user is not an admin), and each hidden feature adds `!$simplifiedUI` to its existing `{#if}`. Branding is plain string/asset replacement on user-reachable screens; admin-only screens are not touched.

**Tech Stack:** SvelteKit 5 (legacy store syntax) + TypeScript + Tailwind 4, FastAPI, pytest, vitest, ImageMagick (`magick`) for placeholder assets.

**Spec:** `docs/superpowers/specs/2026-10-17-romegi-debranding-design.md`

## Global Constraints

- Product name: `RomeGI` (exact casing). The model name stays `Rome Medical Assistant`. Do not rename it.
- Env var: `ROMEGI_SIMPLIFIED_UI`. Default **off** (`false`). Config key: `features.romegi_simplified_ui`.
- Admins (`role === 'admin'`) always see everything, flag or not.
- Hide, never delete: hidden features stay in code behind `!$simplifiedUI`. The only deletions allowed are upstream-branding links/text (Task 5).
- No layout, color or typography changes. No renames of internal identifiers (`open_webui` package, env var names, API paths).
- Don't edit admin-only screens (`src/lib/components/admin/**`, `src/routes/(app)/admin/**`, workspace editors).
- Keep the diff small; don't reformat files you touch beyond the lines you change.
- Existing `tests/` suite must pass. Only `tests/test_docker_compose.py` assertions for `image`, `WEBUI_NAME`, `DEFAULT_MODELS` may change.

## Review Focus

1. **A user whose saved default is the bare `gpt-5.4` model.** With the picker hidden, they must still land on `Rome Medical Assistant`. Covered by the base-model visibility step in Rollout and the check in Task 8, step 4.
2. **The production DB already holds `DEFAULT_MODELS=gpt-5.4`.** The env var is ignored under persistent config, so users must still get the Rome model after the manual Admin Panel step. Covered by Task 8, step 4.
3. **An admin with the flag on.** They still see the model picker, Controls, Workspace, all settings tabs and all fields. Covered by Task 2's unit test and Task 8, step 3.
4. **A `pending` or any non-`admin` role.** Treat it as simplified. Covered by Task 2's unit test.
5. **The flag off or unset.** Non-admins get stock behaviour except branding. Covered by the unit tests in Task 1 and Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/open_webui/env.py` | Remove the name suffix; add `ROMEGI_SIMPLIFIED_UI` |
| `backend/open_webui/main.py` | Expose the flag in `/api/config`; FastAPI title and PWA description use the product name |
| `tests/test_romegi_backend.py` (new) | Backend name and flag parsing tests |
| `src/lib/utils/romegi.ts` (new) | `isSimplifiedUser()`, the single rule for "hide this from this user" |
| `src/lib/utils/romegi.test.ts` (new) | Unit tests for the rule |
| `src/lib/stores/index.ts` | `simplifiedUI` derived store |
| Chat-screen Svelte files (Task 3) | Gate model picker, Controls, Integrations/tools, Workspace |
| Settings Svelte files (Task 4) | Gate tabs and fields |
| Branding files (Task 5, 6) | Strings, links, icons |
| `docker-compose.medical.yaml`, `terraform/cloudrun.tf`, `tests/test_docker_compose.py` (Task 7) | Deploy config |

---

### Task 1: Backend: product name without suffix, flag in `/api/config`

**Files:**
- Modify: `backend/open_webui/env.py:128-130`
- Modify: `backend/open_webui/main.py` (FastAPI `title=` ~line 713; `get_app_config` `features` dict ~line 2049; `get_manifest_json` description ~line 2465)
- Test: `tests/test_romegi_backend.py`

**Interfaces:**
- Produces: `open_webui.env.ROMEGI_SIMPLIFIED_UI: bool`. `/api/config` returns `features.romegi_simplified_ui: bool` (in the unconditional part of `features`, next to `enable_version_update_check`).

- [ ] **Step 1: Write the failing tests** in `tests/test_romegi_backend.py`. Each test runs `python -c "from open_webui import env; print(env.WEBUI_NAME, env.ROMEGI_SIMPLIFIED_UI)"` in a **subprocess** with `cwd=backend/` and these env vars set: `DATABASE_URL=sqlite:///:memory:`, `ENABLE_DB_MIGRATIONS=false`, plus the case's vars. A subprocess is needed so module-level env parsing reruns per case.

```python
def test_custom_name_has_no_suffix():        # WEBUI_NAME=RomeGI          -> 'RomeGI'
def test_default_name_unchanged():           # WEBUI_NAME unset           -> 'Open WebUI'
def test_simplified_ui_defaults_off():       # ROMEGI_SIMPLIFIED_UI unset -> False
def test_simplified_ui_true():               # ROMEGI_SIMPLIFIED_UI=true  -> True
def test_simplified_ui_case_insensitive():   # ROMEGI_SIMPLIFIED_UI=TRUE  -> True
def test_simplified_ui_other_value_off():    # ROMEGI_SIMPLIFIED_UI=yes   -> False
```

- [ ] **Step 2: Run them and verify they fail**

Run: `python3 -m pytest tests/test_romegi_backend.py -v`
Expected: `test_custom_name_has_no_suffix` fails (`'RomeGI (Open WebUI)'`), and the flag tests fail with `AttributeError` on `ROMEGI_SIMPLIFIED_UI`.

- [ ] **Step 3: Implement**
  - In `env.py`, delete the two-line `if WEBUI_NAME != 'Open WebUI': ... += ' (Open WebUI)'` block. Add `ROMEGI_SIMPLIFIED_UI = os.environ.get('ROMEGI_SIMPLIFIED_UI', 'false').lower() == 'true'` right after `WEBUI_NAME`.
  - In `main.py`, import `ROMEGI_SIMPLIFIED_UI` from `open_webui.env` with the other env imports. Add `'romegi_simplified_ui': ROMEGI_SIMPLIFIED_UI,` to the unconditional part of `features`.
  - Change the FastAPI `title='Open WebUI'` to `title=WEBUI_NAME`.
  - Change the manifest description to `f'{app.state.WEBUI_NAME} research assistant'`.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python3 -m pytest tests/test_romegi_backend.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/env.py backend/open_webui/main.py tests/test_romegi_backend.py
git commit -m "feat: drop forced Open WebUI name suffix and add ROMEGI_SIMPLIFIED_UI flag"
```

---

### Task 2: Frontend: `isSimplifiedUser` rule and `simplifiedUI` store

**Files:**
- Create: `src/lib/utils/romegi.ts`
- Create: `src/lib/utils/romegi.test.ts`
- Modify: `src/lib/stores/index.ts`

**Interfaces:**
- Consumes: `features.romegi_simplified_ui` from Task 1.
- Produces:
  - `isSimplifiedUser(config: { features?: { romegi_simplified_ui?: boolean } } | null | undefined, user: { role?: string } | null | undefined): boolean`. Returns true only if the flag is exactly `true` **and** `user` exists **and** `user.role !== 'admin'`. `romegi.ts` has no imports, which avoids import cycles with the stores.
  - `simplifiedUI: Readable<boolean>`, exported from `$lib/stores`, defined as `derived([config, user], ([$c, $u]) => isSimplifiedUser($c, $u))`. Tasks 3 and 4 use `$simplifiedUI`.

- [ ] **Step 1: Write the failing test** `src/lib/utils/romegi.test.ts` (vitest):

```ts
const on = { features: { romegi_simplified_ui: true } };
const off = { features: { romegi_simplified_ui: false } };
it('hides for regular user when flag on', () => expect(isSimplifiedUser(on, { role: 'user' })).toBe(true));
it('hides for pending user when flag on', () => expect(isSimplifiedUser(on, { role: 'pending' })).toBe(true));
it('never hides for admin', () => expect(isSimplifiedUser(on, { role: 'admin' })).toBe(false));
it('does nothing when flag off', () => expect(isSimplifiedUser(off, { role: 'user' })).toBe(false));
it('does nothing when flag missing', () => expect(isSimplifiedUser({}, { role: 'user' })).toBe(false));
it('does nothing without config', () => expect(isSimplifiedUser(undefined, { role: 'user' })).toBe(false));
it('does nothing without user', () => expect(isSimplifiedUser(on, null)).toBe(false));
```

- [ ] **Step 2: Run it and verify it fails**

Run: `npx vitest run src/lib/utils/romegi.test.ts`
Expected: FAIL, cannot resolve `./romegi`.

- [ ] **Step 3: Implement** `isSimplifiedUser` in `romegi.ts`. Add `simplifiedUI` to `src/lib/stores/index.ts`, adding `derived` to the existing `svelte/store` import.

- [ ] **Step 4: Run the test and type-check, and verify both pass**

Run: `npx vitest run src/lib/utils/romegi.test.ts && npm run check`
Expected: 7 passed, and no new `svelte-check` errors compared with `main` (run `npm run check` on `main` first to record the baseline count).

- [ ] **Step 5: Commit**

```bash
git add src/lib/utils/romegi.ts src/lib/utils/romegi.test.ts src/lib/stores/index.ts
git commit -m "feat: add simplifiedUI store for non-admin users"
```

---

### Task 3: Hide power-user features on the chat screen and sidebar

**Files (each: add `!$simplifiedUI` to the existing condition and import `simplifiedUI` from `$lib/stores`):**
- Modify: `src/lib/components/chat/Navbar.svelte`
  - ~line 114 `{#if showModelSelector}` → `{#if showModelSelector && !$simplifiedUI}` (model picker)
  - ~line 215, the Controls button condition: wrap it in `!$simplifiedUI && (...)`
- Modify: `src/lib/components/chat/MessageInput.svelte`
  - ~line 1625, the `IntegrationsMenu` block condition (tools/integrations in the input bar)
  - ~line 1685, the `(selectedToolIds ?? []).length > 0` "Available Tools" button
- Modify: `src/lib/components/layout/Sidebar.svelte`, both Workspace entries (~line 794 collapsed, ~line 1025 expanded)

**Interfaces:**
- Consumes: `simplifiedUI` from Task 2.

- [ ] **Step 1: Apply the four gates above.** Keep the "+" `InputMenu` (file upload, notes) untouched. The spec keeps it.

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: no new errors compared with the Task 2 baseline.

- [ ] **Step 3: Verify in the browser.** Start the backend with `ROMEGI_SIMPLIFIED_UI=true` (`cd backend && ROMEGI_SIMPLIFIED_UI=true bash dev.sh`) and the frontend (`npm run dev`).
  - Log in as a regular user. Model picker, Controls button, integrations/tools button and Workspace are absent. The "+" menu, voice, temporary chat, share and search are present.
  - Log in as an admin. Everything is present.

- [ ] **Step 4: Commit**

```bash
git add src/lib/components/chat/Navbar.svelte src/lib/components/chat/MessageInput.svelte src/lib/components/layout/Sidebar.svelte
git commit -m "feat: hide model picker, controls, tools and workspace in simplified UI"
```

---

### Task 4: Hide settings tabs and fields

**Files:**
- Modify: `src/lib/components/chat/SettingsModal.svelte`, `getAvailableSettings()` (~line 481):
  - When `$simplifiedUI`, return only `general` and `account`.
  - Separately, the `about` tab returns `$user?.role === 'admin'`. This is **unconditional**, because About is upstream branding (spec goal 1).
- Modify: `src/lib/components/chat/Settings/General.svelte`. With `!$simplifiedUI`, gate the Notifications row (~line 262), the System Prompt block (~line 285) and the Advanced Parameters block (~line 302). Theme and Language stay.
- Modify: `src/lib/components/chat/Settings/Account.svelte`. With `!$simplifiedUI`, gate Bio, Gender and Birth Date (~lines 159-227), Notification Webhook (~line 230) and the API keys section (~line 257). Name, profile image and `UpdatePassword` stay.

**Interfaces:**
- Consumes: `simplifiedUI` from Task 2.

- [ ] **Step 1: Apply the gates above.**

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: no new errors.

- [ ] **Step 3: Verify in the browser** (same setup as Task 3).
  - **Regular user:** Settings shows only General (Theme, Language) and Account (name, photo, password). The settings search box finds nothing for "about", "system prompt" or "api".
  - **Admin:** all tabs and fields are present, including About.

- [ ] **Step 4: Commit**

```bash
git add src/lib/components/chat/SettingsModal.svelte src/lib/components/chat/Settings/General.svelte src/lib/components/chat/Settings/Account.svelte
git commit -m "feat: reduce user settings to theme, language and account basics"
```

---

### Task 5: Replace user-visible Open WebUI strings and links

**Files:**
- Modify: `src/lib/constants.ts:4` → `APP_NAME = 'RomeGI'`. This is the `WEBUI_NAME` store default shown before `/api/config` loads.
- Modify: `src/app.html:106` → `<title>RomeGI</title>`
- Modify: `src/routes/+layout.svelte:457,660`. Change the notification titles' `• Open WebUI` to `• ${$WEBUI_NAME}` (`WEBUI_NAME` is already in `$lib/stores`).
- Modify: `src/routes/error/+page.svelte:34-43`. Delete the GitHub readme and Discord links, plus the `{$i18n.t('or')}` between them.
- Modify: `src/lib/components/chat/Settings/General.svelte:243-260`. Delete the "Help us translate Open WebUI!" block.
- Modify: `static/static/site.webmanifest` and `backend/open_webui/static/site.webmanifest`. Set `name` and `short_name` to `RomeGI`.
- Modify: `static/opensearch.xml`. Set `ShortName` to `RomeGI` and `Description` to `Search RomeGI`.
- Modify: `static/manifest.json` only if it contains a name. It is `{}` today, so it is normally untouched.

Already handled upstream, so no change is needed:
- The changelog modal, update toast, and the Documentation/Releases links in the user menu are admin-only today (`src/routes/(app)/+layout.svelte:319,334`, `UserMenu.svelte:290`).
- The remaining i18n strings containing "Open WebUI" sit only in admin screens, the community-sharing UI (disabled by `ENABLE_COMMUNITY_SHARING=false`), the About tab and tool servers. Task 4 hides the last two for users, so no i18n edits are needed.

- [ ] **Step 1: Apply the edits above.**

- [ ] **Step 2: Verify that no user-reachable Open WebUI text remains**

Run:
```bash
grep -rIn -i "open webui\|openwebui\.com\|github.com/open-webui\|discord" \
  src/app.html src/lib/constants.ts src/routes/+layout.svelte src/routes/error src/routes/auth \
  src/lib/components/chat/Settings/General.svelte src/lib/components/chat/Settings/Account.svelte \
  src/lib/components/chat/Navbar.svelte src/lib/components/layout/Sidebar.svelte \
  static/static/site.webmanifest static/opensearch.xml backend/open_webui/static/site.webmanifest
```
Expected: the only hit is the `openwebui.com` origin check in `src/routes/+layout.svelte` (~line 760). It's a postMessage allowlist, not visible text. Leave it.

- [ ] **Step 3: Run `npm run check`.** Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add src/app.html src/lib/constants.ts src/routes/+layout.svelte src/routes/error/+page.svelte src/lib/components/chat/Settings/General.svelte static/static/site.webmanifest static/opensearch.xml backend/open_webui/static/site.webmanifest
git commit -m "feat: replace user-visible Open WebUI name and links with RomeGI"
```

---

### Task 6: RomeGI placeholder logo and icons

**Files (replace in place; same names and pixel sizes):**

| File (in `static/static/`, and copied to `backend/open_webui/static/`) | Size | Content |
|---|---|---|
| `favicon.svg` | 500×500 viewBox | Hand-written SVG: "RG" monogram, bold sans, `#111` on a white rounded square |
| `favicon.png`, `logo.png` | 500×500 | Render of `favicon.svg` |
| `favicon-dark.png` | 500×500 | "RG" in white on transparent (used as the login logo in dark mode) |
| `favicon-96x96.png` | 96×96 | Render of `favicon.svg` |
| `favicon.ico` | 48×48 | Render of `favicon.svg` |
| `apple-touch-icon.png` | 180×180 | Render of `favicon.svg` |
| `web-app-manifest-192x192.png`, `web-app-manifest-512x512.png` | 192, 512 | Render of `favicon.svg` |
| `splash.png` | 500×500 | "RomeGI" wordmark, `#111`, transparent background |
| `splash-dark.png` | 500×500 | "RomeGI" wordmark, white, transparent background |

Also replace `static/favicon.png` (500×500) with the same image as `favicon.png`.

- [ ] **Step 1: Create the assets.** Hand-write `favicon.svg` and generate the rest with `magick`. Use a system font file such as `/System/Library/Fonts/Helvetica.ttc` so rendering doesn't depend on SVG text support. Copy every file to both `static/static/` and `backend/open_webui/static/`. The backend copies `static/` from the frontend build at startup, but its committed copies are served in dev.

- [ ] **Step 2: Verify the sizes**

Run: `magick identify static/static/*.png static/static/favicon.ico static/favicon.png | awk '{print $1, $3}'`
Expected: each size matches the table above. Open `favicon.png`, `favicon-dark.png` and `splash.png` and confirm "RG" / "RomeGI" is legible.

- [ ] **Step 3: Check it in the browser** (dev servers from Task 3). Confirm the login page logo in light and dark mode, the browser tab icon, and the splash screen on a hard reload.

- [ ] **Step 4: Commit**

```bash
git add static/favicon.png static/static backend/open_webui/static
git commit -m "feat: RomeGI placeholder logo and icons"
```

---

### Task 7: Deploy config and compose tests

**Files:**
- Modify: `docker-compose.medical.yaml`
  - Replace `image: ghcr.io/open-webui/open-webui:main` with `build: .`
  - Set `WEBUI_NAME=RomeGI` and `DEFAULT_MODELS=rome-medical-assistant`
  - Add `ENABLE_VERSION_UPDATE_CHECK=false` and `ROMEGI_SIMPLIFIED_UI=true`
- Modify: `terraform/cloudrun.tf`. Set `WEBUI_NAME` (~line 125) to `RomeGI` and `DEFAULT_MODELS` (~line 130) to `rome-medical-assistant`. Add `env` blocks for `ENABLE_VERSION_UPDATE_CHECK=false` and `ROMEGI_SIMPLIFIED_UI=true`, matching the existing block style.
- Modify: `tests/test_docker_compose.py`

- [ ] **Step 1: Update the tests first**
  - `test_image`: rename it to `test_builds_from_fork` and assert `service["build"] == "."` and `"image" not in service`.
  - `test_webui_name`: assert `"RomeGI"`.
  - `test_default_models`: assert `"rome-medical-assistant"`.
  - Add `test_version_update_check_disabled` (asserts `"false"`) and `test_simplified_ui_enabled` (asserts `"true"`).

- [ ] **Step 2: Run them and verify they fail**

Run: `python3 -m pytest tests/test_docker_compose.py -v`
Expected: the 5 tests above fail; all others pass.

- [ ] **Step 3: Edit `docker-compose.medical.yaml` and `terraform/cloudrun.tf` as listed.**

- [ ] **Step 4: Run the full suite and validate Terraform**

Run: `python3 -m pytest tests/ -v && (cd terraform && terraform fmt -check && terraform validate)`
Expected: all tests pass. `terraform validate` reports success (run `terraform init -backend=false` first if needed).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.medical.yaml terraform/cloudrun.tf tests/test_docker_compose.py
git commit -m "chore: deploy as RomeGI with simplified UI and Rome model as default"
```

---

### Task 8: End-to-end verification on a local build of the fork

No code. This task checks the Review Focus list against a real build.

- [ ] **Step 1: Build and run the fork.** Run `docker compose -f docker-compose.medical.yaml --env-file .env up -d --build`, then open `http://localhost:3000`. Create the first account (the admin). Then create a regular user and import/create the Rome model from `config/workspace_model.json`, following existing practice.

- [ ] **Step 2: Branding sweep as a regular user.** Check login, signup, chat (empty and with an answer), the sidebar, the user menu, Settings, browser tab title and favicon, and dark mode.
  Expected: no "Open WebUI" text, no "OI" logo, no openwebui.com, GitHub or Discord links. `curl -s localhost:3000/api/config | jq '.name, .features.romegi_simplified_ui'` prints `"RomeGI"` and `true`.

- [ ] **Step 3: Check the admin view** (Review Focus 3). Logged in as admin: model picker, Controls, Workspace, all settings tabs including About, and the Admin Panel are present.

- [ ] **Step 4: Check model pinning** (Review Focus 1 and 2).
  1. As admin, perform the Rollout manual steps below.
  2. As the regular user, open Settings and confirm there is no way to change models.
  3. Start a new chat. The header/greeting says "Rome Medical Assistant", and an answer carries numbered citation badges and the disclaimer.
  4. Repeat after first saving `gpt-5.4` as that user's default *before* enabling the flag. The user must still land on the Rome model.

- [ ] **Step 5: Check the flag off** (Review Focus 5). Restart with `ROMEGI_SIMPLIFIED_UI=false`. The regular user sees the stock picker, Controls and settings tabs except About, and the branding is still RomeGI.

- [ ] **Step 6: Report** the results of steps 2-5. Note any surface that still shows Open WebUI branding, with its file and line, so it can be fixed or deferred.

---

## Rollout (production, one time)

`DEFAULT_MODELS` and model visibility are persistent DB settings, so the Terraform env change alone does not apply them to the existing production database. Once the picker is hidden, users can't switch models themselves. The order below therefore matters: do the Admin Panel steps **before** `ROMEGI_SIMPLIFIED_UI=true` goes live.

1. Deploy the code (Tasks 1-6). `ROMEGI_SIMPLIFIED_UI` defaults to off, so this changes branding only.
2. **Admin Panel → Settings → Models:** set the default model to **Rome Medical Assistant** (`rome-medical-assistant`).
3. **Admin Panel → Models → `gpt-5.4`:** make sure regular users cannot see it (Private / admins only). By default, base models with no saved model entry are already hidden from non-admins. Check that nobody has made it public.
4. Log in as a regular user with the setting still off. Confirm the model picker offers only Rome Medical Assistant.
5. Only now apply the deploy config (Task 7: Terraform with `ROMEGI_SIMPLIFIED_UI=true`).
6. Run the regular-user part of Task 8, steps 2-4, against production.
