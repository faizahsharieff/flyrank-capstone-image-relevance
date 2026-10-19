"""Make match suggestions idempotent and support full cosine scores.

Revision ID: 0004_persist_match_suggestions
Revises: 0003_semantic_embeddings
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_persist_match_suggestions"
down_revision: Union[str, None] = "0003_semantic_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_suggestions_similarity_score", "suggestions", type_="check")
    op.create_check_constraint(
        "ck_suggestions_similarity_score",
        "suggestions",
        "similarity_score >= -1 AND similarity_score <= 1",
    )
    op.create_unique_constraint(
        "uq_suggestions_post_image",
        "suggestions",
        ["post_id", "image_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_suggestions_post_image", "suggestions", type_="unique")
    op.drop_constraint("ck_suggestions_similarity_score", "suggestions", type_="check")
    op.create_check_constraint(
        "ck_suggestions_similarity_score",
        "suggestions",
        "similarity_score >= 0 AND similarity_score <= 1",
    )