# Signup Invite Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the public email/password signup form behind single-use 9-character invite codes stored in a new `signup_code` table, with an admin-only API to generate, list, and revoke codes.

**Architecture:** A new SQLAlchemy model + table-methods class (`SignupCodes`) follows the repo's existing model pattern (`Base` class, Pydantic v2 model, methods that accept an optional injected `Session` via `get_db_context`). The signup endpoint claims a code atomically (guarded UPDATE on `used_at IS NULL`) *before* creating the user and releases it if user creation fails. An admin router exposes generate/list/revoke. The frontend adds one input field and one API-client parameter.

**Tech Stack:** Python 3.11+/FastAPI/SQLAlchemy/Alembic/Pydantic v2 (backend), SvelteKit 5/TypeScript (frontend), pytest + Hypothesis (tests).

**Spec:** `docs/superpowers/specs/2026-07-18-signup-invite-codes-design.md`

## Global Constraints

- Branch: all work happens on `feat/signup-invite-codes` (created in Task 1).
- Python style: single quotes, 120-char lines (ruff/black config in `pyproject.toml`).
- Frontend style: tabs + single quotes (repo Prettier config).
- Commit format: `<type>: <description>` (types: feat, fix, refactor, docs, test, chore). **No attribution footers** (disabled via user settings).
- Code alphabet is exactly `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no `I`, `O`, `0`, `1`), length exactly 9, stored uppercase.
- Rejection message is exactly `Invalid or already used signup code` with HTTP 400 for missing, malformed, unknown, and already-used codes alike (prevents probing).
- First-user bootstrap (`has_users == False`) is exempt; OAuth/LDAP/trusted-header/admin-created flows are untouched (`signup_handler` itself is NOT modified).
- Admin endpoints all require `Depends(get_admin_user)`.
- Test environment: **system `python3` has NO backend deps.** All Python tests run with `.venv/bin/python` created in Task 1. Test command: `.venv/bin/python -m pytest tests/ -v`.
- Test isolation: tests must set `DATABASE_URL='sqlite:///:memory:'`, `DATABASE_ENABLE_SESSION_SHARING='true'`, and `ENABLE_DB_MIGRATIONS='false'` **before importing any `open_webui` module**. (`get_db_context` only honors an injected session when `DATABASE_ENABLE_SESSION_SHARING` is true; `ENABLE_DB_MIGRATIONS=false` skips peewee migrations at import.)

---

### Task 1: Test environment + SignupCode model & table methods (TDD)

**Files:**
- Create: `backend/open_webui/models/signup_codes.py`
- Test: `tests/test_signup_codes.py`
- Environment: `.venv/` at repo root (gitignored — `.gitignore` line 143 already lists `.venv`)

**Interfaces:**
- Consumes: `Base`, `get_db_context` from `open_webui.internal.db`.
- Produces (used by Tasks 3 & 4):
  - `SIGNUP_CODE_ALPHABET: str`, `SIGNUP_CODE_LENGTH: int` (module constants)
  - `SignupCode` (SQLAlchemy class, `__tablename__ = 'signup_code'`)
  - `SignupCodeModel` (Pydantic: `code: str`, `created_at: int`, `used_by: Optional[str]`, `used_at: Optional[int]`)
  - Singleton `SignupCodes` with methods (every method takes `db: Optional[Session] = None` as its last arg):
    - `generate_codes(count: int, db=None) -> list[SignupCodeModel]`
    - `get_codes(db=None) -> list[SignupCodeModel]`
    - `get_code(code: str, db=None) -> Optional[SignupCodeModel]`
    - `claim_code(code: str, db=None) -> bool`
    - `assign_code_user(code: str, user_id: str, db=None) -> bool`
    - `release_code(code: str, db=None) -> bool`
    - `delete_code(code: str, db=None) -> bool`

- [ ] **Step 1: Create the branch**

```bash
cd /Users/arunimchaudhary/Desktop/other/open-webui
git checkout -b feat/signup-invite-codes
```

Expected: `Switched to a new branch 'feat/signup-invite-codes'`

- [ ] **Step 2: Create the test virtualenv**

System `python3` lacks every backend dependency, and there is no synced project venv. Create a minimal one with `uv` (installed at `~/.local/bin/uv`):

```bash
cd /Users/arunimchaudhary/Desktop/other/open-webui
uv venv .venv --python 3.12
uv pip install -p .venv/bin/python \
  pytest pytest-asyncio hypothesis \
  sqlalchemy alembic pydantic typing-extensions \
  typer uvicorn cryptography markdown beautifulsoup4 \
  peewee peewee-migrate python-mimeparse \
  aiohttp pyyaml requests
```

Verify the import chain works (this is the exact chain the tests use):

```bash
cd backend && DATABASE_URL='sqlite:///:memory:' DATABASE_ENABLE_SESSION_SHARING=true ENABLE_DB_MIGRATIONS=false \
  ../.venv/bin/python -c "from open_webui.internal.db import Base, get_db_context; print('ok')" && cd ..
```

Expected: `ok`. If a `ModuleNotFoundError` names another package, `uv pip install -p .venv/bin/python <package>` and re-run.

Confirm the venv is invisible to git: `git status --short` must not list `.venv`.

Also confirm the pre-existing medical-RAG suite passes in this venv (baseline before any change):

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all existing tests pass (≈89). If any fail for missing modules, install the missing module and re-run; do not touch the tests.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_signup_codes.py` with exactly:

```python
"""Unit and property-based tests for the signup invite-code table methods."""

import os
import sys

# Configure an isolated in-memory backend BEFORE any open_webui import.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DATABASE_ENABLE_SESSION_SHARING'] = 'true'
os.environ['ENABLE_DB_MIGRATIONS'] = 'false'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from open_webui.internal.db import Base
from open_webui.models.signup_codes import (
    SIGNUP_CODE_ALPHABET,
    SIGNUP_CODE_LENGTH,
    SignupCode,
    SignupCodes,
)

CODE_PATTERN = re.compile(r'^[A-HJ-NP-Z2-9]{9}$')


def make_session():
    """Fresh in-memory SQLite session holding only the signup_code table."""
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[SignupCode.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture()
def db():
    session = make_session()
    yield session
    session.close()


class TestGenerateCodes:
    def test_codes_are_9_chars_from_alphabet(self, db):
        codes = SignupCodes.generate_codes(10, db=db)
        assert len(codes) == 10
        for code in codes:
            assert CODE_PATTERN.match(code.code)

    def test_codes_are_unique(self, db):
        codes = SignupCodes.generate_codes(50, db=db)
        assert len({c.code for c in codes}) == 50

    def test_new_codes_are_unused(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert code.used_by is None
        assert code.used_at is None

    def test_alphabet_excludes_ambiguous_characters(self):
        assert SIGNUP_CODE_LENGTH == 9
        for ambiguous in 'IO01':
            assert ambiguous not in SIGNUP_CODE_ALPHABET


class TestGetCode:
    def test_get_code_returns_model(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        stored = SignupCodes.get_code(code.code, db=db)
        assert stored is not None
        assert stored.code == code.code

    def test_get_code_unknown_returns_none(self, db):
        assert SignupCodes.get_code('ZZZZZZZZZ', db=db) is None

    def test_get_code_is_case_insensitive(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.get_code(code.code.lower(), db=db) is not None


class TestClaimCode:
    def test_claim_succeeds_once(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.claim_code(code.code, db=db) is True

    def test_second_claim_fails(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.claim_code(code.code, db=db) is True
        assert SignupCodes.claim_code(code.code, db=db) is False

    def test_claim_unknown_code_fails(self, db):
        assert SignupCodes.claim_code('ZZZZZZZZZ', db=db) is False

    def test_claim_is_case_insensitive(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.claim_code(code.code.lower(), db=db) is True

    def test_claim_sets_used_at(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        SignupCodes.claim_code(code.code, db=db)
        stored = SignupCodes.get_code(code.code, db=db)
        assert stored.used_at is not None


class TestReleaseAndAssign:
    def test_release_makes_code_claimable_again(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.claim_code(code.code, db=db) is True
        assert SignupCodes.release_code(code.code, db=db) is True
        assert SignupCodes.claim_code(code.code, db=db) is True

    def test_assign_code_user_records_consumer(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        SignupCodes.claim_code(code.code, db=db)
        assert SignupCodes.assign_code_user(code.code, 'user-123', db=db) is True
        stored = SignupCodes.get_code(code.code, db=db)
        assert stored.used_by == 'user-123'
        assert stored.used_at is not None


class TestDeleteCode:
    def test_delete_unused_code(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        assert SignupCodes.delete_code(code.code, db=db) is True
        assert SignupCodes.get_codes(db=db) == []

    def test_delete_refuses_used_code(self, db):
        [code] = SignupCodes.generate_codes(1, db=db)
        SignupCodes.claim_code(code.code, db=db)
        assert SignupCodes.delete_code(code.code, db=db) is False
        assert len(SignupCodes.get_codes(db=db)) == 1

    def test_delete_unknown_code(self, db):
        assert SignupCodes.delete_code('ZZZZZZZZZ', db=db) is False


# Feature: signup-invite-codes, Property 1: every generated code matches ^[A-HJ-NP-Z2-9]{9}$
@given(count=st.integers(min_value=1, max_value=20))
@settings(max_examples=100, deadline=None)
def test_property_generated_codes_match_pattern(count):
    session = make_session()
    try:
        codes = SignupCodes.generate_codes(count, db=session)
        assert len(codes) == count
        for code in codes:
            assert CODE_PATTERN.match(code.code)
    finally:
        session.close()


# Feature: signup-invite-codes, Property 2: without a release, at most one claim of a code succeeds
@given(attempts=st.integers(min_value=1, max_value=10))
@settings(max_examples=100, deadline=None)
def test_property_at_most_one_claim_succeeds(attempts):
    session = make_session()
    try:
        [code] = SignupCodes.generate_codes(1, db=session)
        results = [SignupCodes.claim_code(code.code, db=session) for _ in range(attempts)]
        assert results.count(True) == 1
        assert results[0] is True
    finally:
        session.close()
```

- [ ] **Step 4: Run the tests — they must fail on import**

```bash
.venv/bin/python -m pytest tests/test_signup_codes.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'open_webui.models.signup_codes'`.

- [ ] **Step 5: Implement the model**

Create `backend/open_webui/models/signup_codes.py` with exactly:

```python
import logging
import secrets
import time
from typing import Optional

from open_webui.internal.db import Base, get_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Unambiguous alphabet: no I, O, 0, or 1.
SIGNUP_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
SIGNUP_CODE_LENGTH = 9

####################
# DB MODEL
####################


class SignupCode(Base):
    __tablename__ = 'signup_code'

    code = Column(String, primary_key=True, unique=True)
    created_at = Column(BigInteger, nullable=False)
    used_by = Column(String, nullable=True)
    used_at = Column(BigInteger, nullable=True)


class SignupCodeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    created_at: int  # timestamp in epoch seconds
    used_by: Optional[str] = None
    used_at: Optional[int] = None  # timestamp in epoch seconds


####################
# Table
####################


class SignupCodesTable:
    def generate_codes(self, count: int, db: Optional[Session] = None) -> list[SignupCodeModel]:
        with get_db_context(db) as db:
            created = []
            batch = set()
            for _ in range(count):
                # Retry until the code collides with neither this batch nor the table.
                while True:
                    code = ''.join(secrets.choice(SIGNUP_CODE_ALPHABET) for _ in range(SIGNUP_CODE_LENGTH))
                    if code not in batch and db.query(SignupCode).filter_by(code=code).first() is None:
                        break
                row = SignupCode(code=code, created_at=int(time.time()))
                db.add(row)
                batch.add(code)
                created.append(row)
            db.commit()
            return [SignupCodeModel.model_validate(row) for row in created]

    def get_codes(self, db: Optional[Session] = None) -> list[SignupCodeModel]:
        with get_db_context(db) as db:
            rows = db.query(SignupCode).order_by(SignupCode.created_at.desc()).all()
            return [SignupCodeModel.model_validate(row) for row in rows]

    def get_code(self, code: str, db: Optional[Session] = None) -> Optional[SignupCodeModel]:
        with get_db_context(db) as db:
            row = db.query(SignupCode).filter_by(code=code.strip().upper()).first()
            return SignupCodeModel.model_validate(row) if row else None

    def claim_code(self, code: str, db: Optional[Session] = None) -> bool:
        # Guarded UPDATE: `used_at IS NULL` defines "unused", so under concurrent
        # signups at most one caller can flip it and double-spending is impossible.
        with get_db_context(db) as db:
            result = (
                db.query(SignupCode)
                .filter(SignupCode.code == code.strip().upper(), SignupCode.used_at.is_(None))
                .update({'used_at': int(time.time())}, synchronize_session=False)
            )
            db.commit()
            return result == 1

    def assign_code_user(self, code: str, user_id: str, db: Optional[Session] = None) -> bool:
        with get_db_context(db) as db:
            result = db.query(SignupCode).filter_by(code=code.strip().upper()).update({'used_by': user_id})
            db.commit()
            return result == 1

    def release_code(self, code: str, db: Optional[Session] = None) -> bool:
        with get_db_context(db) as db:
            result = (
                db.query(SignupCode).filter_by(code=code.strip().upper()).update({'used_at': None, 'used_by': None})
            )
            db.commit()
            return result == 1

    def delete_code(self, code: str, db: Optional[Session] = None) -> bool:
        # Used rows are audit history and must never be deleted.
        with get_db_context(db) as db:
            result = (
                db.query(SignupCode)
                .filter(SignupCode.code == code.strip().upper(), SignupCode.used_at.is_(None))
                .delete(synchronize_session=False)
            )
            db.commit()
            return result == 1


SignupCodes = SignupCodesTable()
```

- [ ] **Step 6: Run the new tests — they must pass**

```bash
.venv/bin/python -m pytest tests/test_signup_codes.py -v
```

Expected: all ~19 tests PASS.

- [ ] **Step 7: Run the whole suite (no regressions)**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: everything passes.

- [ ] **Step 8: Lint and commit**

```bash
uvx ruff check backend/open_webui/models/signup_codes.py tests/test_signup_codes.py
uvx ruff format --check backend/open_webui/models/signup_codes.py tests/test_signup_codes.py
git add backend/open_webui/models/signup_codes.py tests/test_signup_codes.py
git commit -m "feat: add signup_code model and table methods"
```

Expected: ruff clean (if `ruff format --check` complains, run `uvx ruff format` on those two files and re-run the tests before committing).

---

### Task 2: Alembic migration for the signup_code table

**Files:**
- Create: `backend/open_webui/migrations/versions/d4f8a1c92e7b_add_signup_code_table.py`

**Interfaces:**
- Consumes: current migration head `b2c3d4e5f6a7` (verified: no other revision revises it).
- Produces: revision `d4f8a1c92e7b` creating table `signup_code` matching the `SignupCode` model in Task 1.

- [ ] **Step 1: Write the migration**

Create `backend/open_webui/migrations/versions/d4f8a1c92e7b_add_signup_code_table.py` with exactly:

```python
"""Add signup_code table

Revision ID: d4f8a1c92e7b
Revises: b2c3d4e5f6a7
Create Date: 2026-07-18 00:00:00.000000

Single-use invite codes required for public signups. `used_at IS NULL`
defines "unused"; used rows are kept as audit history.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = 'd4f8a1c92e7b'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(get_existing_tables())

    if 'signup_code' not in existing_tables:
        op.create_table(
            'signup_code',
            sa.Column('code', sa.String(), nullable=False, primary_key=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('used_by', sa.String(), nullable=True),
            sa.Column('used_at', sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table('signup_code')
```

- [ ] **Step 2: Verify there is a single head and it is ours**

```bash
cd /Users/arunimchaudhary/Desktop/other/open-webui/backend/open_webui
DATABASE_URL='sqlite:///:memory:' ENABLE_DB_MIGRATIONS=false ../../.venv/bin/python -m alembic heads
```

Expected output contains exactly one head: `d4f8a1c92e7b (head)`. (Alembic reads `alembic.ini` from this directory; `script_location = migrations`.) If this fails with `ModuleNotFoundError`, install the named package into `.venv` with `uv pip install -p ../../.venv/bin/python <package>` and re-run — the alembic env imports `open_webui.models.auths`, which pulls a wider import chain than the tests.

- [ ] **Step 3: Run the migration against a scratch database**

```bash
MIGDB=$(mktemp -d)/migtest.db
DATABASE_URL="sqlite:///$MIGDB" ENABLE_DB_MIGRATIONS=false ../../.venv/bin/python -m alembic upgrade head
sqlite3 "$MIGDB" '.schema signup_code'
cd ../..
```

Expected: `upgrade` completes without error and the schema shows the `signup_code` table with columns `code` (PK), `created_at`, `used_by`, `used_at`.

- [ ] **Step 4: Commit**

```bash
git add backend/open_webui/migrations/versions/d4f8a1c92e7b_add_signup_code_table.py
git commit -m "feat: add signup_code table migration"
```

---

### Task 3: SignupForm field + signup endpoint gate

**Files:**
- Modify: `backend/open_webui/models/auths.py:72-83` (SignupForm)
- Modify: `backend/open_webui/routers/auths.py:730-749` (signup endpoint) and its imports (~line 30)

**Interfaces:**
- Consumes: `SignupCodes.claim_code / assign_code_user / release_code` from Task 1.
- Produces: `SignupForm.signup_code: Optional[str]` accepted by `POST /api/v1/auths/signup` (Task 5's frontend sends it).

- [ ] **Step 1: Add the form field**

In `backend/open_webui/models/auths.py`, the current class reads:

```python
class SignupForm(BaseModel):
    name: str
    email: str
    password: str
    profile_image_url: Optional[str] = '/user.png'
```

Add one field so it becomes:

```python
class SignupForm(BaseModel):
    name: str
    email: str
    password: str
    profile_image_url: Optional[str] = '/user.png'
    signup_code: Optional[str] = None
```

(Keep the existing `check_profile_image_url` validator below it untouched.)

- [ ] **Step 2: Gate the signup endpoint**

In `backend/open_webui/routers/auths.py`, add this import after line 30 (`from open_webui.models.oauth_sessions import OAuthSessions`):

```python
from open_webui.models.signup_codes import SignupCodes
```

(`import re` already exists at the top of the file.)

Then in the `signup` endpoint, replace this block:

```python
    try:
        try:
            validate_password(form_data.password)
        except Exception as e:
            raise HTTPException(400, detail=str(e))

        user = await signup_handler(
            request,
            form_data.email,
            form_data.password,
            form_data.name,
            form_data.profile_image_url,
            db=db,
        )
        return create_session_response(request, user, db, response, set_cookie=True)
    except HTTPException:
        raise
    except Exception as err:
        log.error(f'Signup error: {str(err)}')
        raise HTTPException(500, detail='An internal error occurred during signup.')
```

with:

```python
    try:
        try:
            validate_password(form_data.password)
        except Exception as e:
            raise HTTPException(400, detail=str(e))

        # Every non-first signup must consume an unused invite code. The claim is
        # an atomic guarded UPDATE, so a code can never be spent twice. Missing,
        # malformed, unknown, and used codes share one message to prevent probing.
        signup_code = None
        if has_users:
            signup_code = (form_data.signup_code or '').strip().upper()
            if not re.fullmatch(r'[A-Z0-9]{9}', signup_code) or not SignupCodes.claim_code(signup_code, db=db):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail='Invalid or already used signup code',
                )

        try:
            user = await signup_handler(
                request,
                form_data.email,
                form_data.password,
                form_data.name,
                form_data.profile_image_url,
                db=db,
            )
        except Exception:
            # Compensation: the code was claimed but no user exists; free it again.
            if signup_code:
                try:
                    SignupCodes.release_code(signup_code, db=db)
                except Exception as release_err:
                    log.error(f'Failed to release signup code after failed signup: {release_err}')
            raise

        if signup_code:
            SignupCodes.assign_code_user(signup_code, user.id, db=db)

        return create_session_response(request, user, db, response, set_cookie=True)
    except HTTPException:
        raise
    except Exception as err:
        log.error(f'Signup error: {str(err)}')
        raise HTTPException(500, detail='An internal error occurred during signup.')
```

Ordering notes (from the spec): the claim happens after email/password validation (so bad requests never burn codes) and immediately before `signup_handler` (so no user is ever created without consuming a code). If the process dies between claim and assign, the code is burned — visible in the admin listing as `used_at` set with empty `used_by`.

- [ ] **Step 3: Verify syntax and lint**

```bash
.venv/bin/python -m py_compile backend/open_webui/models/auths.py backend/open_webui/routers/auths.py
uvx ruff check backend/open_webui/models/auths.py backend/open_webui/routers/auths.py
```

Expected: no output from py_compile; ruff reports no NEW errors in the edited regions (pre-existing warnings elsewhere in these files, if any, are out of scope).

- [ ] **Step 4: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass (endpoint rejection paths are covered at the table-method level per the spec — the repo has no runnable FastAPI TestClient scaffolding; `backend/open_webui/test/` references a missing `AbstractPostgresTest` util).

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/models/auths.py backend/open_webui/routers/auths.py
git commit -m "feat: require invite code for non-first signups"
```

---

### Task 4: Admin router + registration

**Files:**
- Create: `backend/open_webui/routers/signup_codes.py`
- Modify: `backend/open_webui/main.py:71-100` (router import list) and `:1513` (registration, after the skills router)

**Interfaces:**
- Consumes: `SignupCodeModel`, `SignupCodes` (Task 1); `get_admin_user` from `open_webui.utils.auth`; `get_session` from `open_webui.internal.db`.
- Produces: `POST /api/v1/signup_codes/generate`, `GET /api/v1/signup_codes/`, `DELETE /api/v1/signup_codes/{code}`.

- [ ] **Step 1: Write the router**

Create `backend/open_webui/routers/signup_codes.py` with exactly:

```python
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.signup_codes import SignupCodeModel, SignupCodes
from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)

router = APIRouter()


############################
# GenerateCodes
############################


class GenerateCodesForm(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)


@router.post('/generate', response_model=list[SignupCodeModel])
async def generate_codes(
    form_data: GenerateCodesForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    return SignupCodes.generate_codes(form_data.count, db=db)


############################
# GetCodes
############################


@router.get('/', response_model=list[SignupCodeModel])
async def get_codes(user=Depends(get_admin_user), db: Session = Depends(get_session)):
    return SignupCodes.get_codes(db=db)


############################
# DeleteCode
############################


@router.delete('/{code}', response_model=bool)
async def delete_code(code: str, user=Depends(get_admin_user), db: Session = Depends(get_session)):
    existing = SignupCodes.get_code(code, db=db)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail='Signup code not found')
    if existing.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail='Used signup codes cannot be deleted')
    return SignupCodes.delete_code(code, db=db)
```

- [ ] **Step 2: Register it in main.py**

In `backend/open_webui/main.py`, inside the `from open_webui.routers import (` block (lines 71–100), add `signup_codes,` on its own line directly after `skills,`:

```python
    evaluations,
    skills,
    signup_codes,
    tools,
```

Then after line 1513 (`app.include_router(skills.router, prefix='/api/v1/skills', tags=['skills'])`), add:

```python
app.include_router(signup_codes.router, prefix='/api/v1/signup_codes', tags=['signup_codes'])
```

- [ ] **Step 3: Verify syntax and lint**

```bash
.venv/bin/python -m py_compile backend/open_webui/routers/signup_codes.py backend/open_webui/main.py
uvx ruff check backend/open_webui/routers/signup_codes.py
```

Expected: no output / no errors.

- [ ] **Step 4: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/open_webui/routers/signup_codes.py backend/open_webui/main.py
git commit -m "feat: add admin API for signup invite codes"
```

---

### Task 5: Frontend — API client parameter + invite-code input

**Files:**
- Modify: `src/lib/apis/auths/index.ts:289-308` (`userSignUp`)
- Modify: `src/routes/auth/+page.svelte` (~line 41 variable, ~line 88 call, ~line 296 markup)

**Interfaces:**
- Consumes: `POST /api/v1/auths/signup` accepting `signup_code` (Task 3).
- Produces: `userSignUp(name, email, password, profile_image_url, signup_code = null)`.

- [ ] **Step 1: Add the API-client parameter**

In `src/lib/apis/auths/index.ts`, `userSignUp` currently begins:

```ts
export const userSignUp = async (
	name: string,
	email: string,
	password: string,
	profile_image_url: string
) => {
```

and its body includes:

```ts
		body: JSON.stringify({
			name: name,
			email: email,
			password: password,
			profile_image_url: profile_image_url
		})
```

Change them to:

```ts
export const userSignUp = async (
	name: string,
	email: string,
	password: string,
	profile_image_url: string,
	signup_code: null | string = null
) => {
```

```ts
		body: JSON.stringify({
			name: name,
			email: email,
			password: password,
			profile_image_url: profile_image_url,
			signup_code: signup_code
		})
```

- [ ] **Step 2: Add the input field and wire it through**

In `src/routes/auth/+page.svelte`:

(a) After `let confirmPassword = '';` (~line 41), add:

```svelte
	let signupCode = '';
```

(b) In `signUpHandler` (~line 88), change the `userSignUp` call from:

```svelte
		const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);
```

to:

```svelte
		const sessionUser = await userSignUp(
			name,
			email,
			password,
			generateInitialsImage(name),
			signupCode ? signupCode : null
		).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
```

(c) In the form markup, directly after the closing `{/if}` of the Name-field block (the block that starts `{#if mode === 'signup'}` and contains the `id="name"` input, ~line 296), add a new block. It renders only for non-onboarding signups (the first-admin/onboarding signup is exempt from codes) and is required in that state; backend `400` responses surface through the page's existing toast error handling:

```svelte
										{#if mode === 'signup' && !($config?.onboarding ?? false)}
											<div class="mb-2">
												<label for="invite-code" class="text-sm font-medium text-left mb-1 block"
													>{$i18n.t('Invite Code')}</label
												>
												<input
													bind:value={signupCode}
													type="text"
													id="invite-code"
													class="my-0.5 w-full text-sm outline-hidden bg-transparent placeholder:text-gray-300 dark:placeholder:text-gray-600"
													autocomplete="off"
													placeholder={$i18n.t('Enter Your Invite Code')}
													required
												/>
											</div>
										{/if}
```

- [ ] **Step 3: Verify formatting and lint**

```bash
npx prettier --check src/lib/apis/auths/index.ts src/routes/auth/+page.svelte
npx eslint src/lib/apis/auths/index.ts src/routes/auth/+page.svelte
```

Expected: prettier clean (if not, run `npx prettier --write` on the two files); eslint reports no NEW errors (pre-existing warnings elsewhere in these files are out of scope).

- [ ] **Step 4: Confirm no other userSignUp callers broke**

```bash
grep -rn "userSignUp" src/ --include='*.svelte' --include='*.ts'
```

Expected: only the definition in `src/lib/apis/auths/index.ts` and the call in `src/routes/auth/+page.svelte` (the new parameter defaults to `null`, so any other caller would still compile).

- [ ] **Step 5: Commit**

```bash
git add src/lib/apis/auths/index.ts src/routes/auth/+page.svelte
git commit -m "feat: add invite code field to signup form"
```

---

### Task 6: Full verification sweep

**Files:** none new — verification only.

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: every test passes, including the ~19 new signup-code tests.

- [ ] **Step 2: Lint everything this branch touched**

```bash
uvx ruff check backend/open_webui/models/signup_codes.py backend/open_webui/routers/signup_codes.py \
  backend/open_webui/migrations/versions/d4f8a1c92e7b_add_signup_code_table.py tests/test_signup_codes.py
npx prettier --check src/lib/apis/auths/index.ts src/routes/auth/+page.svelte
```

Expected: clean.

- [ ] **Step 3: Review the branch diff against the spec's "Files touched" list**

```bash
git diff main...HEAD --stat
git status --short
```

Expected: exactly these files changed (plus this plan document if committed):

1. `backend/open_webui/models/signup_codes.py` (new)
2. `backend/open_webui/migrations/versions/d4f8a1c92e7b_add_signup_code_table.py` (new)
3. `backend/open_webui/models/auths.py`
4. `backend/open_webui/routers/auths.py`
5. `backend/open_webui/routers/signup_codes.py` (new)
6. `backend/open_webui/main.py`
7. `src/lib/apis/auths/index.ts`
8. `src/routes/auth/+page.svelte`
9. `tests/test_signup_codes.py` (new)

Working tree must be clean (no stray files; `.venv` must not appear).
