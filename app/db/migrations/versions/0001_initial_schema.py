"""Create the initial image matching schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("processing_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("path", name="uq_images_path"),
    )
    op.create_index("ix_images_processing_status", "images", ["processing_status"])
    op.create_index("ix_images_created_at", "images", ["created_at"])

    op.create_table(
        "image_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("caption", sa.String(length=2000), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_image_metadata_confidence"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("image_id"),
    )
    op.create_index("ix_image_metadata_needs_review", "image_metadata", ["needs_review"])
    op.create_index("ix_image_metadata_created_at", "image_metadata", ["created_at"])
    op.create_index("ix_image_metadata_subject_category", "image_metadata", ["subject", "category"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("total_items >= 0 AND processed_items >= 0 AND failed_items >= 0", name="ck_jobs_item_counts_nonnegative"),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("guard_status", sa.String(length=32), nullable=False),
        sa.Column("guard_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("similarity_score >= 0 AND similarity_score <= 1", name="ck_suggestions_similarity_score"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_suggestions_image_id", "suggestions", ["image_id"])
    op.create_index("ix_suggestions_guard_status", "suggestions", ["guard_status"])
    op.create_index("ix_suggestions_created_at", "suggestions", ["created_at"])
    op.create_index("ix_suggestions_post_guard_status", "suggestions", ["post_id", "guard_status"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("suggestion_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('approve', 'reject')", name="ck_reviews_decision"),
        sa.ForeignKeyConstraint(["suggestion_id"], ["suggestions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reviews_suggestion_id", "reviews", ["suggestion_id"])
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"])

    op.create_table(
        "cost_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("image_id", sa.Integer()),
        sa.Column("post_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_cost_logs_estimated_cost_nonnegative"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_cost_logs_image_id", "cost_logs", ["image_id"])
    op.create_index("ix_cost_logs_post_id", "cost_logs", ["post_id"])
    op.create_index("ix_cost_logs_created_at", "cost_logs", ["created_at"])
    op.create_index("ix_cost_logs_operation_model", "cost_logs", ["operation", "model_name"])


def downgrade() -> None:
    op.drop_index("ix_cost_logs_operation_model", table_name="cost_logs")
    op.drop_index("ix_cost_logs_created_at", table_name="cost_logs")
    op.drop_index("ix_cost_logs_post_id", table_name="cost_logs")
    op.drop_index("ix_cost_logs_image_id", table_name="cost_logs")
    op.drop_table("cost_logs")

    op.drop_index("ix_reviews_created_at", table_name="reviews")
    op.drop_index("ix_reviews_suggestion_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_suggestions_post_guard_status", table_name="suggestions")
    op.drop_index("ix_suggestions_created_at", table_name="suggestions")
    op.drop_index("ix_suggestions_guard_status", table_name="suggestions")
    op.drop_index("ix_suggestions_image_id", table_name="suggestions")
    op.drop_table("suggestions")

    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_posts_created_at", table_name="posts")
    op.drop_table("posts")

    op.drop_index("ix_image_metadata_subject_category", table_name="image_metadata")
    op.drop_index("ix_image_metadata_created_at", table_name="image_metadata")
    op.drop_index("ix_image_metadata_needs_review", table_name="image_metadata")
    op.drop_table("image_metadata")

    op.drop_index("ix_images_created_at", table_name="images")
    op.drop_index("ix_images_processing_status", table_name="images")
    op.drop_table("images")