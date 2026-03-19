"""add updated_at to reminder

Revision ID: 9f3c7e21b6ad
Revises: 4b1f8f1d4a5b
Create Date: 2026-03-19 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3c7e21b6ad"
down_revision: Union[str, Sequence[str], None] = "4b1f8f1d4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "reminder",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
    )

    # Keep existing rows migration-safe by backfilling from created_at where available.
    op.execute("UPDATE reminder SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("reminder", recreate="always") as batch_op:
            batch_op.drop_column("updated_at")
    else:
        op.drop_column("reminder", "updated_at")
