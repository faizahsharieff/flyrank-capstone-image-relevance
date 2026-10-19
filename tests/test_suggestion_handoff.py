from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql.dml import Insert

from app.db.database import get_db
from app.main import app
from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.models.review import Review
from app.models.suggestion import Suggestion


class MemoryResult:
    def __init__(self, *, rows=(), scalar=None) -> None:
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class SuggestionWorkflowSession:
    def __init__(self, *, post_title: str = "Red foxes in winter", image_subject: str = "red fox") -> None:
        self.post = Post(
            id=42,
            title=post_title,
            content="An article about red foxes.",
            embedding=[1.0, 0.0],
        )
        self.image = Image(id=7, filename="fox.jpg", path="data/images/fox/fox.jpg")
        self.metadata = ImageMetadata(
            id=8,
            image_id=self.image.id,
            subject=image_subject,
            category="wildlife",
            attributes=["red fur"],
            caption=f"A {image_subject} outdoors.",
            confidence=0.95,
            needs_review=False,
            caption_embedding=[0.99, 0.01],
        )
        self.image.image_metadata = self.metadata
        self.image_rows = [(self.image, self.metadata, self.metadata.caption_embedding)]
        self.suggestions_by_pair: dict[tuple[int, int], Suggestion] = {}
        self.suggestions_by_id: dict[int, Suggestion] = {}
        self.reviews: list[Review] = []
        self.commit_count = 0
        self._next_suggestion_id = 100
        self._next_review_id = 500

    def get(self, model: type[object], record_id: int):
        if model is Post and record_id == self.post.id:
            return self.post
        if model is Suggestion:
            return self.suggestions_by_id.get(record_id)
        return None

    def execute(self, statement):
        if not isinstance(statement, Insert):
            return MemoryResult(rows=self.image_rows)

        values = statement.compile().params
        pair = (values["post_id"], values["image_id"])
        suggestion = self.suggestions_by_pair.get(pair)
        if suggestion is None:
            suggestion = Suggestion(
                id=self._next_suggestion_id,
                post_id=values["post_id"],
                image_id=values["image_id"],
                similarity_score=values["similarity_score"],
                guard_status=values["guard_status"],
                guard_reason=values["guard_reason"],
                post=self.post,
                image=self.image,
            )
            self._next_suggestion_id += 1
            self.suggestions_by_pair[pair] = suggestion
            self.suggestions_by_id[suggestion.id] = suggestion
        else:
            suggestion.similarity_score = values["similarity_score"]
            suggestion.guard_status = values["guard_status"]
            suggestion.guard_reason = values["guard_reason"]

        return MemoryResult(scalar=suggestion.id)

    def add(self, record: object) -> None:
        if isinstance(record, Review):
            record.id = self._next_review_id
            record.created_at = datetime.now(UTC)
            self._next_review_id += 1
            self.reviews.append(record)

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, record: object) -> None:
        pass


def _client_for(session: SuggestionWorkflowSession) -> TestClient:
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def test_match_saves_suggestion_returns_id_and_review_endpoints_use_it() -> None:
    session = SuggestionWorkflowSession()
    client = _client_for(session)

    try:
        match_response = client.get("/posts/42/images")
        suggestion_id = match_response.json()["suggestions"][0]["suggestion_id"]
        inspection_response = client.get(f"/suggestions/{suggestion_id}")
        approval_response = client.post(f"/suggestions/{suggestion_id}/approve")
        rejection_response = client.post(f"/suggestions/{suggestion_id}/reject")
    finally:
        app.dependency_overrides.clear()

    assert match_response.status_code == 200
    assert match_response.json()["status"] == "matched"
    assert suggestion_id == 100
    assert len(session.suggestions_by_pair) == 1
    assert inspection_response.status_code == 200
    assert inspection_response.json()["suggestion_id"] == suggestion_id
    assert inspection_response.json()["image_confidence"] == 0.95
    assert inspection_response.json()["guard_result"] == "accepted"
    assert approval_response.status_code == 201
    assert approval_response.json()["suggestion_id"] == suggestion_id
    assert approval_response.json()["decision"] == "approve"
    assert rejection_response.status_code == 201
    assert rejection_response.json()["suggestion_id"] == suggestion_id
    assert rejection_response.json()["decision"] == "reject"


def test_repeated_matching_upserts_the_same_suggestion() -> None:
    session = SuggestionWorkflowSession()
    client = _client_for(session)

    try:
        first_response = client.get("/posts/42/images")
        second_response = client.get("/posts/42/images")
    finally:
        app.dependency_overrides.clear()

    first_id = first_response.json()["suggestions"][0]["suggestion_id"]
    second_id = second_response.json()["suggestions"][0]["suggestion_id"]
    assert first_id == second_id
    assert len(session.suggestions_by_pair) == 1


def test_guard_rejected_candidate_is_persisted_with_reason_and_no_match_shape() -> None:
    session = SuggestionWorkflowSession(image_subject="wolf")
    client = _client_for(session)

    try:
        response = client.get("/posts/42/images")
        rejected_suggestion = next(iter(session.suggestions_by_id.values()))
        inspection = client.get(f"/suggestions/{rejected_suggestion.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "no_confident_match"
    assert response.json()["suggestions"] == []
    assert rejected_suggestion.guard_status == "rejected"
    assert "Subject mismatch" in rejected_suggestion.guard_reason
    assert inspection.status_code == 200
    assert inspection.json()["guard_result"] == "rejected"
    assert inspection.json()["guard_explanation"] == rejected_suggestion.guard_reason