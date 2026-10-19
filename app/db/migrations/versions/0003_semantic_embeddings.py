"""Add source-aware semantic embedding columns.

Revision ID: 0003_semantic_embeddings
Revises: 0002_attr_array_default
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_semantic_embeddings"
down_revision: Union[str, None] = "0002_attr_array_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("image_metadata", sa.Column("caption_embedding", postgresql.JSONB(), nullable=True))
    op.add_column(
        "image_metadata", sa.Column("caption_embedding_source_hash", sa.String(length=64), nullable=True)
    )
    op.add_column("posts", sa.Column("embedding", postgresql.JSONB(), nullable=True))
    op.add_column("posts", sa.Column("embedding_source_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "embedding_source_hash")
    op.drop_column("posts", "embedding")
    op.drop_column("image_metadata", "caption_embedding_source_hash")
    op.drop_column("image_metadata", "caption_embedding")