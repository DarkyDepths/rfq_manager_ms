"""merge reminder source and rfq code counter heads

Revision ID: 5f3a1b8c9d0e
Revises: 2d98d9a8b8a4, e2b7d4f5a1c2
Create Date: 2026-04-08 22:05:00.000000

"""
from typing import Sequence, Union


revision: str = "5f3a1b8c9d0e"
down_revision: Union[str, Sequence[str], None] = ("2d98d9a8b8a4", "e2b7d4f5a1c2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge two valid schema branches into a single head."""


def downgrade() -> None:
    """Undo merge marker only."""
