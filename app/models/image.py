from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy import String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (UniqueConstraint("path", name="uq_images_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    image_metadata: Mapped[ImageMetadata | None] = relationship(
        "ImageMetadata", back_populates="image", cascade="all, delete-orphan", uselist=False
    )
    suggestions: Mapped[list[Suggestion]] = relationship("Suggestion", back_populates="image")
    cost_logs: Mapped[list[CostLog]] = relationship("CostLog", back_populates="image")


class ImageMetadata(Base):
    __tablename__ = "image_metadata"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_image_metadata_confidence"),
        Index("ix_image_metadata_subject_category", "subject", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    attributes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    caption: Mapped[str] = mapped_column(String(2000), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    caption_embedding: Mapped[list[float] | None] = mapped_column(JSONB)
    caption_embedding_source_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    image: Mapped[Image] = relationship("Image", back_populates="image_metadata")