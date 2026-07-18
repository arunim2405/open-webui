# Signup Invite Codes — Design

**Date:** 2026-07-18
**Status:** Approved

## Goal

Users may sign up via the public signup form only if they present a unique 9-character
alphanumeric invite code that matches an unused code stored in the backend database.
Each code is single-use: once a signup consumes it, it can never be used again.

## Scope

- **In scope:** the email/password signup form (`POST /api/v1/auths/signup`), a new
  `signup_code` table, and an admin-only API to generate, list, and revoke codes.
- **Out of scope:** OAuth, LDAP, trusted-header auto-registration, and admin-created
  users — these paths are unchanged. No admin UI page (API only). No config toggle:
  the gate is always on for non-first users.
- **First-user exemption:** the very first signup (which becomes admin and may occur
  via `ENABLE_INITIAL_ADMIN_SIGNUP`) does not require a code, so deployments can
  bootstrap.

## Data model

New file `backend/open_webui/models/signup_codes.py`, following the existing model
pattern (SQLAlchemy `Base` class + Pydantic model + table-methods class using
`get_db_context`):

| Column       | Type            | Notes                                  |
| ------------ | --------------- | -------------------------------------- |
| `code`       | String, PK      | 9 chars, stored uppercase              |
| `created_at` | BigInteger      | epoch seconds                          |
| `used_by`    | String, nullable| `user.id` of the consumer              |
| `used_at`    | BigInteger, nullable | epoch seconds                     |

`SignupCodesTable` methods (all accept an optional injected `Session`, matching the
repo convention):

- `generate_codes(count)` — creates `count` codes using `secrets.choice` over the
  unambiguous alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no `I`, `O`, `0`, `1`),
  9 characters each. Retries on primary-key collision. Returns the created codes.
- `get_codes()` — all codes with usage status.
- `delete_code(code)` — deletes only if unused (`used_at IS NULL`); used rows are
  kept as audit history.
- `claim_code(code)` — single guarded
  `UPDATE signup_code SET used_at=:now WHERE code=:code AND used_at IS NULL`;
  returns `True` iff exactly one row was updated. `used_at IS NULL` is the
  definition of "unused", which makes double-spending impossible under concurrent
  signups.
- `assign_code_user(code, user_id)` — fills in `used_by` after the user is created
  (audit only).
- `release_code(code)` — clears `used_at` (compensation when user creation fails
  after a successful claim).

Note: table methods commit in their own sessions (`DATABASE_ENABLE_SESSION_SHARING`
defaults to `False`), so the claim and the user insert are separate transactions.
Correctness comes from ordering + compensation, not a shared transaction — see below.

An Alembic migration in `backend/open_webui/migrations/versions/` creates the table.

## Signup validation (backend)

- `SignupForm` (`backend/open_webui/models/auths.py`) gains
  `signup_code: Optional[str] = None`.
- In the `signup` endpoint (`backend/open_webui/routers/auths.py`), after the email
  format/duplicate checks and before `signup_handler`:
  - Skip validation entirely when `has_users` is `False` (first-user bootstrap).
  - Otherwise: normalize the code (strip whitespace, uppercase); reject with
    `400 "Invalid or already used signup code"` when the code is missing, is not
    exactly 9 alphanumeric characters, or `claim_code` returns `False`.
- Ordering guarantees "no user is ever created without consuming a code":
  1. `claim_code(code)` — atomically marks the code used; `False` → `400`.
  2. `signup_handler(...)` — creates the user.
  3. On success: `assign_code_user(code, user.id)`.
  4. On failure of step 2: best-effort `release_code(code)`, then re-raise.
  If the process dies between steps 1 and 3, the code is burned (row with `used_at`
  set but `used_by` empty) — rare, visible in the admin listing, and the admin can
  generate a replacement.
- `signup_handler` itself is not modified; other flows that call it are unaffected.

## Admin API

New router `backend/open_webui/routers/signup_codes.py`, registered in
`backend/open_webui/main.py` under `/api/v1/signup_codes`. Every endpoint requires
`Depends(get_admin_user)`:

- `POST /generate` — body `{count: int}` (1–1000); generates codes and returns them.
- `GET /` — lists all codes with `used_by` / `used_at` status.
- `DELETE /{code}` — revokes an unused code. `404` if the code does not exist,
  `400` if it has been used (audit rows are immutable).

## Frontend

- `src/routes/auth/+page.svelte`: add an "Invite code" text input, shown only when
  `mode === 'signup'` and `$config?.onboarding` is falsy (the page already
  distinguishes first-admin setup). The field is required in that state and its value
  is passed to `userSignUp`.
- `src/lib/apis/auths/index.ts`: `userSignUp` gains a `signup_code` parameter
  included in the POST body. Backend `400` responses surface through the page's
  existing toast error handling.

## Error handling

- Invalid and already-used codes return the same `400` message so callers cannot
  probe which codes exist.
- Format validation happens before any DB lookup.
- No rate limiting added: 9 characters over a 32-symbol alphabet gives ~3.5×10¹³
  combinations, making brute force impractical.

## Testing

New `tests/test_signup_codes.py`, following the repo's pytest + Hypothesis
conventions (in-memory SQLite session injected into the table methods):

- **Unit:** generated codes are 9 chars from the expected alphabet and unique;
  `claim_code` succeeds once and fails on the second attempt; `release_code` makes a
  claimed code claimable again; `delete_code` refuses used codes; claiming is
  case-insensitive (input normalized to uppercase).
- **Property (Hypothesis):** every generated code matches `^[A-HJ-NP-Z2-9]{9}$`;
  for any sequence of claim attempts on a code (without release), at most one
  succeeds.
- **Endpoint-level:** signup rejection paths (missing / malformed / used code) via
  FastAPI TestClient if the existing test setup supports it; otherwise the
  validation logic is tested directly against the table methods.

## Files touched

1. `backend/open_webui/models/signup_codes.py` (new)
2. `backend/open_webui/migrations/versions/<rev>_add_signup_code_table.py` (new)
3. `backend/open_webui/models/auths.py` (SignupForm field)
4. `backend/open_webui/routers/auths.py` (signup validation)
5. `backend/open_webui/routers/signup_codes.py` (new admin router)
6. `backend/open_webui/main.py` (router registration)
7. `src/lib/apis/auths/index.ts` (userSignUp parameter)
8. `src/routes/auth/+page.svelte` (invite-code input)
9. `tests/test_signup_codes.py` (new)
