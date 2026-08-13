"""Add signup_code table

Revision ID: d4f8a1c92e7b
Revises: b2c3d4e5f6a7
Create Date: 2026-07-18 00:00:00.000000

Single-use invite codes required for public signups. `used_at IS NULL`
defines "unused"; used rows are kept as audit history.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from open_webui.migrations.util import get_existing_tables

revision: str = 'd4f8a1c92e7b'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
