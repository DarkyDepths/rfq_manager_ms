"""add stage_template_id to rfq_stage

Revision ID: 4b1f8f1d4a5b
Revises: bc8fe52aaace
Create Date: 2026-03-19 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b1f8f1d4a5b"
down_revision: Union[str, Sequence[str], None] = "bc8fe52aaace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAME = "fk_rfq_stage_stage_template_id"


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("rfq_stage", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("stage_template_id", sa.UUID(), nullable=True))
            batch_op.create_foreign_key(
                FK_NAME,
                "stage_template",
                ["stage_template_id"],
                ["id"],
            )
    else:
        op.add_column("rfq_stage", sa.Column("stage_template_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            FK_NAME,
            "rfq_stage",
            "stage_template",
            ["stage_template_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("rfq_stage", recreate="always") as batch_op:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
            batch_op.drop_column("stage_template_id")
    else:
        op.drop_constraint(FK_NAME, "rfq_stage", type_="foreignkey")
        op.drop_column("rfq_stage", "stage_template_id")
