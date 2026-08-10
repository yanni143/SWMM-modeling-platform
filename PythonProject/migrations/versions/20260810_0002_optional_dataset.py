"""make legacy dataset reference optional

Revision ID: 20260810_0002
Revises: 20260810_0001
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_0002"
down_revision: Union[str, None] = "20260810_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "swmm_models",
        "dataset_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "swmm_models",
        "dataset_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )
