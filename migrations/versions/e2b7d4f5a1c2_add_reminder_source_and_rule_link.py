"""add reminder source and rule link

Revision ID: e2b7d4f5a1c2
Revises: 9f3c7e21b6ad
Create Date: 2026-04-08 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b7d4f5a1c2"
down_revision: Union[str, Sequence[str], None] = "9f3c7e21b6ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAME = "fk_reminder_rule_id"
IDX_RULE = "ix_reminder_reminder_rule_id"
IDX_SOURCE = "ix_reminder_source"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("reminder", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("reminder_rule_id", sa.UUID(), nullable=True)
            )
            batch_op.add_column(
                sa.Column("source", sa.String(length=20), nullable=True, server_default="manual")
            )
            batch_op.create_index(IDX_RULE, ["reminder_rule_id"], unique=False)
            batch_op.create_index(IDX_SOURCE, ["source"], unique=False)
            batch_op.create_foreign_key(
                FK_NAME,
                "reminder_rule",
                ["reminder_rule_id"],
                ["id"],
            )
        op.execute("UPDATE reminder SET source = 'manual' WHERE source IS NULL")
    else:
        op.add_column("reminder", sa.Column("reminder_rule_id", sa.UUID(), nullable=True))
        op.add_column(
            "reminder",
            sa.Column("source", sa.String(length=20), nullable=True, server_default="manual"),
        )
        op.create_index(IDX_RULE, "reminder", ["reminder_rule_id"], unique=False)
        op.create_index(IDX_SOURCE, "reminder", ["source"], unique=False)
        op.create_foreign_key(
            FK_NAME,
            "reminder",
            "reminder_rule",
            ["reminder_rule_id"],
            ["id"],
        )
        op.execute("UPDATE reminder SET source = 'manual' WHERE source IS NULL")

    if bind.dialect.name != "sqlite":
        op.alter_column("reminder", "source", nullable=False, server_default="manual")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("reminder", recreate="always") as batch_op:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
            batch_op.drop_index(IDX_RULE)
            batch_op.drop_index(IDX_SOURCE)
            batch_op.drop_column("reminder_rule_id")
            batch_op.drop_column("source")
    else:
        op.drop_constraint(FK_NAME, "reminder", type_="foreignkey")
        op.drop_index(IDX_RULE, table_name="reminder")
        op.drop_index(IDX_SOURCE, table_name="reminder")
        op.drop_column("reminder", "reminder_rule_id")
        op.drop_column("reminder", "source")
