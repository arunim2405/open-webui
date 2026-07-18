import logging
import secrets
import time

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
    used_by: str | None = None
    used_at: int | None = None  # timestamp in epoch seconds


####################
# Table
####################


class SignupCodesTable:
    def generate_codes(self, count: int, db: Session | None = None) -> list[SignupCodeModel]:
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

    def get_codes(self, db: Session | None = None) -> list[SignupCodeModel]:
        with get_db_context(db) as db:
            rows = db.query(SignupCode).order_by(SignupCode.created_at.desc()).all()
            return [SignupCodeModel.model_validate(row) for row in rows]

    def get_code(self, code: str, db: Session | None = None) -> SignupCodeModel | None:
        with get_db_context(db) as db:
            row = db.query(SignupCode).filter_by(code=code.strip().upper()).first()
            return SignupCodeModel.model_validate(row) if row else None

    def claim_code(self, code: str, db: Session | None = None) -> bool:
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

    def assign_code_user(self, code: str, user_id: str, db: Session | None = None) -> bool:
        with get_db_context(db) as db:
            result = db.query(SignupCode).filter_by(code=code.strip().upper()).update({'used_by': user_id})
            db.commit()
            return result == 1

    def release_code(self, code: str, db: Session | None = None) -> bool:
        with get_db_context(db) as db:
            result = (
                db.query(SignupCode).filter_by(code=code.strip().upper()).update({'used_at': None, 'used_by': None})
            )
            db.commit()
            return result == 1

    def delete_code(self, code: str, db: Session | None = None) -> bool:
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
