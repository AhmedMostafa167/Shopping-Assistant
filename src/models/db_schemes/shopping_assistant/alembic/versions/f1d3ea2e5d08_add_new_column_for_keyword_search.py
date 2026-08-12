"""add new column for keyword search

Revision ID: f1d3ea2e5d08
Revises: 2003314c8a15
Create Date: 2026-08-04 17:40:11.332354

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1d3ea2e5d08'
down_revision: Union[str, Sequence[str], None] = '2003314c8a15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "products",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR,
            sa.Computed(
                "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,'') || ' ' || coalesce(store,''))",
                persisted=True
            )
        )
    )
    op.create_index(
        "ix_products_search_vector",
        "products",
        ["search_vector"],
        postgresql_using="gin"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
