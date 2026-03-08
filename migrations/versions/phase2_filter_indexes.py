"""Add missing Phase 2 indices for owner and dates

Revision ID: phase2_filter_indexes
Revises: 
Create Date: 2026-03-08 19:28:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'phase2_filter_indexes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # owner index
    op.create_index(op.f('ix_rfq_owner'), 'rfq', ['owner'], unique=False)
    # priority index
    op.create_index(op.f('ix_rfq_priority'), 'rfq', ['priority'], unique=False)
    # created_at index
    op.create_index(op.f('ix_rfq_created_at'), 'rfq', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_rfq_created_at'), table_name='rfq')
    op.drop_index(op.f('ix_rfq_priority'), table_name='rfq')
    op.drop_index(op.f('ix_rfq_owner'), table_name='rfq')
