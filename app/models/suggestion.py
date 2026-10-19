from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint(
            "similarity_score >= -1 AND similarity_score <= 1",
            name="ck_suggestions_similarity_score",
        ),
        UniqueConstraint("post_id", "image_id", name="uq_suggestions_post_image"),
        Index("ix_suggestions_post_guard_status", "post_id", "guard_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    similarity_score: Mapped[float] = mapped_column(nullable=False)
    guard_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    guard_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    post: Mapped[Post] = relationship("Post", back_populates="suggestions")
    image: Mapped[Image] = relationship("Image", back_populates="suggestions")
    reviews: Mapped[list[Review]] = relationship(
        "Review", back_populates="suggestion", cascade="all, delete-orphan"
    )