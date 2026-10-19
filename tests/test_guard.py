from unittest.mock import MagicMock

from app.api.posts import rank_post_images
from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.services.matcher import ImageMatcher
from app.services.mismatch_guard import MismatchGuard


def test_correct_fox_candidate_passes() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="red fox",
        image_category="wildlife",
        similarity_score=0.92,
        confidence=0.94,
    )

    assert result.accepted is True
    assert result.reason is None


def test_wolf_rejected_for_fox_post() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="gray wolf",
        image_category="wildlife",
        similarity_score=0.91,
        confidence=0.93,
    )

    assert result.accepted is False
    assert result.reason == "Subject mismatch: expected fox, detected wolf."


def test_low_similarity_rejected() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="red fox",
        image_category="wildlife",
        similarity_score=0.74,
        confidence=0.93,
    )

    assert result.accepted is False
    assert "Similarity 0.740 is below the minimum 0.750" in result.reason


def test_low_confidence_rejected() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="red fox",
        image_category="wildlife",
        similarity_score=0.93,
        confidence=0.69,
    )

    assert result.accepted is False
    assert "Image confidence 0.690 is below the minimum 0.700" in result.reason


def test_incompatible_category_rejected() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="red fox",
        image_category="vehicles",
        similarity_score=0.93,
        confidence=0.95,
    )

    assert result.accepted is False
    assert "Category mismatch" in result.reason


def test_non_finite_similarity_is_rejected() -> None:
    result = MismatchGuard().evaluate(
        post_title="Red foxes in winter",
        post_content="How foxes adapt to snow.",
        image_subject="red fox",
        image_category="wildlife",
        similarity_score=float("nan"),
        confidence=0.95,
    )

    assert result.accepted is False
    assert "Invalid similarity score" in result.reason


def test_guard_thresholds_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MIN_SIMILARITY", "0.82")
    monkeypatch.setenv("MIN_CONFIDENCE", "0.88")

    guard = MismatchGuard()

    assert guard.min_similarity == 0.82
    assert guard.min_confidence == 0.88


def test_no_confident_match() -> None:
    post = Post(
        id=42,
        title="Red foxes in winter",
        content="How foxes adapt to snow.",
        embedding=[1.0, 0.0],
    )
    image = Image(id=5, filename="wolf.jpg", path="data/images/wolf/wolf.jpg")
    metadata = ImageMetadata(
        id=6,
        image_id=image.id,
        subject="gray wolf",
        category="wildlife",
        confidence=0.95,
        caption="A gray wolf.",
        attributes=[],
        caption_embedding=[0.99, 0.01],
    )
    database_session = MagicMock()
    database_session.get.return_value = post
    database_session.execute.return_value.all.return_value = [(image, metadata, [0.99, 0.01])]

    result = ImageMatcher().rank_post_images(database_session, post_id=42)

    assert result.status == "no_confident_match"
    assert result.suggestions == []
    assert "Subject mismatch: expected fox, detected wolf" in result.reason


def test_no_confident_match_endpoint_returns_required_shape() -> None:
    post = Post(
        id=42,
        title="Red foxes in winter",
        content="How foxes adapt to snow.",
        embedding=[1.0, 0.0],
    )
    image = Image(id=5, filename="wolf.jpg", path="data/images/wolf/wolf.jpg")
    metadata = ImageMetadata(
        id=6,
        image_id=image.id,
        subject="wolf",
        category="wildlife",
        confidence=0.95,
        caption="A wolf.",
        attributes=[],
        caption_embedding=[0.99, 0.01],
    )
    database_session = MagicMock()
    database_session.get.return_value = post
    database_session.execute.return_value.all.return_value = [(image, metadata, [0.99, 0.01])]

    response = rank_post_images(post_id=42, limit=5, database_session=database_session)

    assert response.model_dump() == {
        "status": "no_confident_match",
        "suggestions": [],
        "reason": "No confident image match. Subject mismatch: expected fox, detected wolf.",
    }


def test_mixed_results_include_accepted_images_and_rejection_reason() -> None:
    post = Post(
        id=42,
        title="Red foxes in winter",
        content="How foxes adapt to snow.",
        embedding=[1.0, 0.0],
    )
    fox = Image(id=1, filename="fox.jpg", path="data/images/fox/fox.jpg")
    fox_metadata = ImageMetadata(
        id=1,
        image_id=fox.id,
        subject="red fox",
        category="wildlife",
        confidence=0.95,
        caption="A fox.",
        attributes=[],
        caption_embedding=[1.0, 0.0],
    )
    wolf = Image(id=2, filename="wolf.jpg", path="data/images/wolf/wolf.jpg")
    wolf_metadata = ImageMetadata(
        id=2,
        image_id=wolf.id,
        subject="wolf",
        category="wildlife",
        confidence=0.95,
        caption="A wolf.",
        attributes=[],
        caption_embedding=[0.99, 0.01],
    )
    database_session = MagicMock()
    database_session.get.return_value = post
    database_session.execute.return_value.all.return_value = [
        (fox, fox_metadata, [1.0, 0.0]),
        (wolf, wolf_metadata, [0.99, 0.01]),
    ]

    response = rank_post_images(post_id=42, limit=5, database_session=database_session)

    assert response.status == "matched"
    assert [suggestion.filename for suggestion in response.suggestions] == ["fox.jpg"]
    assert "Subject mismatch: expected fox, detected wolf" in response.reason