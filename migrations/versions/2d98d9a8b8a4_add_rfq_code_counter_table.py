"""add rfq_code_counter table for atomic code allocation

Revision ID: 2d98d9a8b8a4
Revises: 9f3c7e21b6ad
Create Date: 2026-03-22 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d98d9a8b8a4"
down_revision: Union[str, Sequence[str], None] = "9f3c7e21b6ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rfq_code_counter",
        sa.Column("prefix", sa.String(length=10), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("prefix"),
    )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            INSERT INTO rfq_code_counter (prefix, last_value)
            SELECT
                split_part(rfq_code, '-', 1) AS prefix,
                MAX(CAST(split_part(rfq_code, '-', 2) AS INTEGER)) AS last_value
            FROM rfq
            WHERE rfq_code ~ '^(IF|IB)-[0-9]+$'
            GROUP BY split_part(rfq_code, '-', 1)
            """
        )
    else:
        op.execute(
            """
            INSERT INTO rfq_code_counter (prefix, last_value)
            SELECT
                SUBSTR(rfq_code, 1, INSTR(rfq_code, '-') - 1) AS prefix,
                MAX(CAST(SUBSTR(rfq_code, INSTR(rfq_code, '-') + 1) AS INTEGER)) AS last_value
            FROM rfq
            WHERE rfq_code GLOB 'IF-[0-9]*' OR rfq_code GLOB 'IB-[0-9]*'
            GROUP BY SUBSTR(rfq_code, 1, INSTR(rfq_code, '-') - 1)
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("rfq_code_counter")
