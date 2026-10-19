from unittest.mock import MagicMock

import pytest

from app.api.posts import rank_post_images
from app.models.image import Image
from app.models.post import Post
from app.services.matcher import (
    ImageMatcher,
    PostEmbeddingNotFoundError,
    PostNotFoundError,
    rank_image_embeddings,
)


def _image(image_id: int, filename: str) -> Image:
    return Image(id=image_id, filename=filename, path=f"data/images/{filename}")


def test_red_fox_ranks_above_wolf_and_dog() -> None:
    candidates = [
        (_image(3, "wolf.jpg"), [0.2, 0.8]),
        (_image(2, "dog.jpg"), [0.7, 0.7]),
        (_image(1, "red_fox.jpg"), [0.99, 0.01]),
    ]

    ranked_images = rank_image_embeddings([1.0, 0.0], candidates)

    assert [candidate.filename for candidate in ranked_images] == [
        "red_fox.jpg",
        "dog.jpg",
        "wolf.jpg",
    ]
    assert ranked_images[0].similarity_score > ranked_images[1].similarity_score
    assert ranked_images[1].similarity_score > ranked_images[2].similarity_score


def test_ranking_skips_candidates_without_embeddings_and_limits_results() -> None:
    candidates = [
        (_image(1, "fox.jpg"), [1.0, 0.0]),
        (_image(2, "no-embedding.jpg"), None),
        (_image(3, "dog.jpg"), [0.0, 1.0]),
    ]

    ranked_images = rank_image_embeddings([1.0, 0.0], candidates, limit=1)

    assert len(ranked_images) == 1
    assert ranked_images[0].filename == "fox.jpg"


def test_matcher_loads_post_and_available_image_embeddings() -> None:
    post = Post(id=42, title="Fox", content="A fox post", embedding=[1.0, 0.0])
    rows = [
        (
            _image(1, "fox.jpg"),
            MagicMock(subject="fox", category="wildlife", confidence=0.95),
            [0.99, 0.01],
        ),
        (
            _image(2, "wolf.jpg"),
            MagicMock(subject="wolf", category="wildlife", confidence=0.95),
            [0.1, 0.9],
        ),
    ]
    database_session = MagicMock()
    database_session.get.return_value = post
    database_session.execute.return_value.all.return_value = rows

    ranked_images = ImageMatcher().rank_post_images(database_session, post_id=42)

    database_session.get.assert_called_once_with(Post, 42)
    assert ranked_images.status == "matched"
    assert ranked_images.suggestions[0].filename == "fox.jpg"
    assert ranked_images.suggestions[0].similarity_score > 0.99


def test_matcher_reports_missing_post_or_post_embedding() -> None:
    database_session = MagicMock()
    database_session.get.return_value = None
    matcher = ImageMatcher()

    with pytest.raises(PostNotFoundError):
        matcher.rank_post_images(database_session, post_id=404)

    database_session.get.return_value = Post(id=42, title="Fox", content="No vector")
    with pytest.raises(PostEmbeddingNotFoundError):
        matcher.rank_post_images(database_session, post_id=42)


def test_post_images_endpoint_returns_ranked_candidate_schemas() -> None:
    database_session = MagicMock()
    database_session.get.return_value = Post(
        id=42, title="Fox", content="Fox article", embedding=[1.0, 0.0]
    )
    database_session.execute.return_value.all.return_value = [
        (
            _image(1, "fox.jpg"),
            MagicMock(subject="fox", category="wildlife", confidence=0.95),
            [1.0, 0.0],
        )
    ]

    result = rank_post_images(post_id=42, limit=5, database_session=database_session)

    assert result.status == "matched"
    assert len(result.suggestions) == 1
    assert result.suggestions[0].image_id == 1
    assert result.suggestions[0].similarity_score == pytest.approx(1.0)