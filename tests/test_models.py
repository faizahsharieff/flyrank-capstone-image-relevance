from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models import CostLog, Image, ImageMetadata, Job, Post, Review, Suggestion


def test_core_models_register_tables_and_relationships() -> None:
    configure_mappers()

    assert set(Base.metadata.tables) == {
        "images",
        "image_metadata",
        "posts",
        "suggestions",
        "reviews",
        "jobs",
        "cost_logs",
    }
    assert Image.image_metadata.property.uselist is False
    assert ImageMetadata.image.property.back_populates == "image_metadata"
    assert Suggestion.reviews.property.back_populates == "suggestion"
    assert Review.suggestion.property.back_populates == "reviews"
    assert CostLog.image.property.back_populates == "cost_logs"
    assert Post.suggestions.property.back_populates == "post"
    assert Job.__tablename__ == "jobs"