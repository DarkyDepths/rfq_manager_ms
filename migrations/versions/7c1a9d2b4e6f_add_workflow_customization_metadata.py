"""add workflow customization metadata

Revision ID: 7c1a9d2b4e6f
Revises: 5f3a1b8c9d0e
Create Date: 2026-04-09 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1a9d2b4e6f"
down_revision: Union[str, Sequence[str], None] = "5f3a1b8c9d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("workflow", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("selection_mode", sa.String(length=20), nullable=False, server_default="fixed")
            )
            batch_op.add_column(sa.Column("base_workflow_id", sa.UUID(), nullable=True))
            batch_op.create_index("ix_workflow_base_workflow_id", ["base_workflow_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_workflow_base_workflow_id",
                "workflow",
                ["base_workflow_id"],
                ["id"],
            )
        with op.batch_alter_table("stage_template", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false())
            )
    else:
        op.add_column(
            "workflow",
            sa.Column("selection_mode", sa.String(length=20), nullable=False, server_default="fixed"),
        )
        op.add_column("workflow", sa.Column("base_workflow_id", sa.UUID(), nullable=True))
        op.create_index(
            "ix_workflow_base_workflow_id",
            "workflow",
            ["base_workflow_id"],
            unique=False,
        )
        op.create_foreign_key(
            "fk_workflow_base_workflow_id",
            "workflow",
            "workflow",
            ["base_workflow_id"],
            ["id"],
        )
        op.add_column(
            "stage_template",
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    op.execute("UPDATE workflow SET selection_mode = 'fixed' WHERE selection_mode IS NULL")
    op.execute("UPDATE stage_template SET is_required = FALSE WHERE is_required IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("stage_template", recreate="always") as batch_op:
            batch_op.drop_column("is_required")
        with op.batch_alter_table("workflow", recreate="always") as batch_op:
            batch_op.drop_constraint("fk_workflow_base_workflow_id", type_="foreignkey")
            batch_op.drop_index("ix_workflow_base_workflow_id")
            batch_op.drop_column("base_workflow_id")
            batch_op.drop_column("selection_mode")
    else:
        op.drop_column("stage_template", "is_required")
        op.drop_constraint("fk_workflow_base_workflow_id", "workflow", type_="foreignkey")
        op.drop_index("ix_workflow_base_workflow_id", table_name="workflow")
        op.drop_column("workflow", "base_workflow_id")
        op.drop_column("workflow", "selection_mode")
