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
from open_webui.internal.db import Base
from open_webui.models.signup_codes import (
    SIGNUP_CODE_ALPHABET,
    SIGNUP_CODE_LENGTH,
    SignupCode,
    SignupCodes,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
