from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CostLog(Base):
    __tablename__ = "cost_logs"
    __table_args__ = (
        CheckConstraint("estimated_cost >= 0", name="ck_cost_logs_estimated_cost_nonnegative"),
        Index("ix_cost_logs_operation_model", "operation", "model_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True, index=True
    )
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    image: Mapped[Image | None] = relationship("Image", back_populates="cost_logs")
    post: Mapped[Post | None] = relationship("Post", back_populates="cost_logs")