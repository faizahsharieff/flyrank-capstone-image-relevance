from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.models.review import Review
from app.models.suggestion import Suggestion
from app.services.reviews import record_review


def _suggestion() -> Suggestion:
    image = Image(id=8, filename="fox.jpg", path="data/images/fox/fox.jpg")
    image.image_metadata = ImageMetadata(
        id=9,
        image_id=image.id,
        subject="red fox",
        category="wildlife",
        attributes=["red fur"],
        caption="A red fox outdoors.",
        confidence=0.92,
        needs_review=False,
    )
    return Suggestion(
        id=4,
        post_id=2,
        image_id=image.id,
        similarity_score=0.91,
        guard_status="accepted",
        guard_reason=None,
        image=image,
        post=Post(id=2, title="Foxes", content="About foxes."),
    )


def _client_for(database_session: MagicMock) -> TestClient:
    app.dependency_overrides[get_db] = lambda: database_session
    return TestClient(app)


def test_inspection_returns_image_post_metadata_and_guard_details() -> None:
    database_session = MagicMock()
    database_session.get.return_value = _suggestion()
    client = _client_for(database_session)

    try:
        response = client.get("/suggestions/4")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "suggestion_id": 4,
        "image": {"id": 8, "filename": "fox.jpg", "path": "data/images/fox/fox.jpg"},
        "post": {"id": 2, "title": "Foxes", "content": "About foxes."},
        "similarity_score": 0.91,
        "image_confidence": 0.92,
        "detected_subject": "red fox",
        "detected_category": "wildlife",
        "guard_result": "accepted",
        "guard_explanation": None,
    }


def test_approve_persists_review_row() -> None:
    database_session = MagicMock()
    database_session.get.return_value = _suggestion()

    def add_review(review: Review) -> None:
        review.id = 15

    def refresh_review(review: Review) -> None:
        review.created_at = datetime.now(UTC)

    database_session.add.side_effect = add_review
    database_session.refresh.side_effect = refresh_review
    client = _client_for(database_session)

    try:
        response = client.post("/suggestions/4/approve")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == 15
    assert response.json()["suggestion_id"] == 4
    assert response.json()["decision"] == "approve"
    database_session.commit.assert_called_once()


def test_reject_persists_review_row() -> None:
    database_session = MagicMock()
    database_session.get.return_value = _suggestion()
    database_session.add.side_effect = lambda review: setattr(review, "id", 16)
    database_session.refresh.side_effect = lambda review: setattr(review, "created_at", datetime.now(UTC))
    client = _client_for(database_session)

    try:
        response = client.post("/suggestions/4/reject")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["decision"] == "reject"
    database_session.commit.assert_called_once()


def test_invalid_decision_is_rejected() -> None:
    database_session = MagicMock()

    try:
        record_review(database_session, suggestion_id=4, decision="maybe")
    except ValueError as error:
        assert str(error) == "Decision must be 'approve' or 'reject'."
    else:
        raise AssertionError("Expected an invalid review decision to be rejected.")

    database_session.add.assert_not_called()
    database_session.commit.assert_not_called()


def test_decision_mismatching_action_path_returns_422() -> None:
    database_session = MagicMock()
    client = _client_for(database_session)

    try:
        response = client.post("/suggestions/4/approve", json={"decision": "reject"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    database_session.add.assert_not_called()


def test_invalid_decision_body_returns_422() -> None:
    database_session = MagicMock()
    client = _client_for(database_session)

    try:
        response = client.post("/suggestions/4/approve", json={"decision": "maybe"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    database_session.add.assert_not_called()


def test_nonexistent_suggestion_returns_404() -> None:
    database_session = MagicMock()
    database_session.get.return_value = None
    client = _client_for(database_session)

    try:
        inspection = client.get("/suggestions/404")
        review = client.post("/suggestions/404/approve")
    finally:
        app.dependency_overrides.clear()

    assert inspection.status_code == 404
    assert review.status_code == 404
    assert review.json()["detail"] == "Suggestion 404 was not found."