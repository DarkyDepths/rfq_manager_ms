"""Add missing Phase 2 indices for owner and dates

Revision ID: phase2_filter_indexes
Revises:
Create Date: 2026-03-08 19:28:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'phase2_filter_indexes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy no-op revision kept for compatibility with previously stamped databases.
    # Authoritative schema creation begins in revision: bc8fe52aaace.
    pass


def downgrade() -> None:
    # No downgrade action for legacy compatibility revision.
    pass