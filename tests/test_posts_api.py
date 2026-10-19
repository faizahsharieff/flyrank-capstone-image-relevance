from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.cost_log import CostLog
from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.models.suggestion import Suggestion
from app.services.embeddings import EmbeddingResult, EmbeddingService


class InMemorySession:
    def __init__(self, image_rows: list[tuple[Image, ImageMetadata, list[float]]] | None = None):
        self.posts: dict[int, Post] = {}
        self.added: list[object] = []
        self.image_rows = image_rows or []
        self.suggestions: dict[tuple[int, int], Suggestion] = {}
        self.commit_count = 0
        self._next_post_id = 101
        self._next_suggestion_id = 201

    def add(self, record: object) -> None:
        self.added.append(record)
        if isinstance(record, Post):
            record.id = self._next_post_id
            record.created_at = datetime.now(UTC)
            self.posts[record.id] = record
            self._next_post_id += 1

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, record: object) -> None:
        pass

    def get(self, model: type[object], record_id: int) -> object | None:
        if model is Post:
            return self.posts.get(record_id)
        return None

    def execute(self, statement: object) -> SimpleNamespace:
        if getattr(statement, "is_insert", False):
            values = statement.compile().params
            key = (values["post_id"], values["image_id"])
            suggestion = self.suggestions.get(key)
            if suggestion is None:
                suggestion = Suggestion(
                    id=self._next_suggestion_id,
                    post_id=values["post_id"],
                    image_id=values["image_id"],
                    similarity_score=values["similarity_score"],
                    guard_status=values["guard_status"],
                    guard_reason=values["guard_reason"],
                )
                self.suggestions[key] = suggestion
                self._next_suggestion_id += 1
            return SimpleNamespace(scalar_one=lambda: suggestion.id)
        return SimpleNamespace(all=lambda: self.image_rows)


def _client_for(database_session: InMemorySession) -> TestClient:
    app.dependency_overrides[get_db] = lambda: database_session
    return TestClient(app)


def _mock_embedding_service() -> MagicMock:
    embedding_service = MagicMock(spec=EmbeddingService)

    def generate_embedding(text: str, *, on_call) -> EmbeddingResult:
        on_call("mock-embedding-model")
        return EmbeddingResult(values=[1.0, 0.0], model_name="mock-embedding-model")

    embedding_service.generate_embedding.side_effect = generate_embedding
    return embedding_service


def test_create_post_persists_and_embeds_with_existing_cost_tracking(monkeypatch) -> None:
    database_session = InMemorySession()
    embedding_service = _mock_embedding_service()
    monkeypatch.setattr("app.api.posts.EmbeddingService", lambda: embedding_service)
    client = _client_for(database_session)

    try:
        response = client.post(
            "/posts",
            json={
                "title": "The Behavior of Red Foxes",
                "content": "Red foxes are adaptable wild animals.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    created_post = response.json()
    post = database_session.posts[created_post["id"]]
    cost_logs = [record for record in database_session.added if isinstance(record, CostLog)]

    assert created_post["title"] == "The Behavior of Red Foxes"
    assert post.embedding == [1.0, 0.0]
    assert post.embedding_source_hash is not None
    embedding_service.generate_embedding.assert_called_once_with(
        "The Behavior of Red Foxes\n\nRed foxes are adaptable wild animals.",
        on_call=embedding_service.generate_embedding.call_args.kwargs["on_call"],
    )
    assert len(cost_logs) == 1
    assert cost_logs[0].operation == "embedding"
    assert cost_logs[0].post_id == post.id
    assert cost_logs[0].estimated_cost == Decimal("0")


def test_empty_title_returns_422_without_saving(monkeypatch) -> None:
    database_session = InMemorySession()
    embedding_service_factory = MagicMock()
    monkeypatch.setattr("app.api.posts.EmbeddingService", embedding_service_factory)
    client = _client_for(database_session)

    try:
        response = client.post("/posts", json={"title": "   ", "content": "An article."})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert database_session.posts == {}
    embedding_service_factory.assert_not_called()


def test_empty_content_returns_422_without_saving(monkeypatch) -> None:
    database_session = InMemorySession()
    embedding_service_factory = MagicMock()
    monkeypatch.setattr("app.api.posts.EmbeddingService", embedding_service_factory)
    client = _client_for(database_session)

    try:
        response = client.post("/posts", json={"title": "Foxes", "content": "  "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert database_session.posts == {}
    embedding_service_factory.assert_not_called()


def test_created_post_can_immediately_use_existing_matcher(monkeypatch) -> None:
    image = Image(id=9, filename="fox_01.jpg", path="data/images/fox/fox_01.jpg")
    metadata = ImageMetadata(
        id=10,
        image_id=image.id,
        subject="red fox",
        category="wildlife",
        attributes=["red fur"],
        caption="A red fox outdoors.",
        confidence=0.95,
        needs_review=False,
        caption_embedding=[1.0, 0.0],
    )
    database_session = InMemorySession(image_rows=[(image, metadata, [1.0, 0.0])])
    embedding_service = _mock_embedding_service()
    monkeypatch.setattr("app.api.posts.EmbeddingService", lambda: embedding_service)
    client = _client_for(database_session)

    try:
        create_response = client.post(
            "/posts",
            json={"title": "The Behavior of Red Foxes", "content": "Red foxes are adaptable."},
        )
        post_id = create_response.json()["id"]
        match_response = client.get(f"/posts/{post_id}/images")
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    assert match_response.status_code == 200
    assert match_response.json()["status"] == "matched"
    assert match_response.json()["suggestions"][0]["image_id"] == image.id