from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.jobs.embedding_processing import ensure_caption_embedding, ensure_post_embedding
from app.models.cost_log import CostLog
from app.models.image import ImageMetadata
from app.models.post import Post
from app.services.embeddings import EmbeddingResponseError, EmbeddingService


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        self.commit_count += 1


def _mock_embedding_service(values: list[float]) -> tuple[EmbeddingService, MagicMock]:
    client = MagicMock()
    client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=values)]
    )
    return EmbeddingService(client=client, model_name="mock-embedding-model"), client


def test_embedding_service_uses_gemini_and_logs_before_call() -> None:
    service, client = _mock_embedding_service([0.1, 0.2, 0.3])
    call_log = MagicMock()

    result = service.generate_embedding("red fox caption", on_call=call_log)

    call_log.assert_called_once_with("mock-embedding-model")
    request = client.models.embed_content.call_args.kwargs
    assert request["model"] == "mock-embedding-model"
    assert request["contents"] == "red fox caption"
    assert request["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert result.values == [0.1, 0.2, 0.3]


def test_empty_embedding_response_is_rejected() -> None:
    client = MagicMock()
    client.models.embed_content.return_value = SimpleNamespace(embeddings=[])
    service = EmbeddingService(client=client, model_name="mock-embedding-model")
    call_log = MagicMock()

    with pytest.raises(EmbeddingResponseError):
        service.generate_embedding("some text", on_call=call_log)

    call_log.assert_called_once_with("mock-embedding-model")


def test_caption_embedding_is_stored_and_unchanged_text_is_skipped() -> None:
    session = FakeSession()
    service, _ = _mock_embedding_service([0.4, 0.5])
    metadata = ImageMetadata(id=1, image_id=7, caption="A red fox in snow")

    generated = ensure_caption_embedding(session, metadata, service)
    generated_again = ensure_caption_embedding(session, metadata, service)

    cost_logs = [record for record in session.added if isinstance(record, CostLog)]
    assert generated is True
    assert generated_again is False
    assert metadata.caption_embedding == [0.4, 0.5]
    assert metadata.caption_embedding_source_hash is not None
    assert len(cost_logs) == 1
    assert cost_logs[0].operation == "embedding"
    assert cost_logs[0].image_id == 7
    assert cost_logs[0].estimated_cost == Decimal("0")


def test_changed_caption_generates_new_embedding() -> None:
    session = FakeSession()
    service, client = _mock_embedding_service([0.4, 0.5])
    metadata = ImageMetadata(id=1, image_id=7, caption="A red fox")

    ensure_caption_embedding(session, metadata, service)
    metadata.caption = "A red fox in snow"
    generated_again = ensure_caption_embedding(session, metadata, service)

    assert generated_again is True
    assert client.models.embed_content.call_count == 2
    assert len([record for record in session.added if isinstance(record, CostLog)]) == 2


def test_post_embedding_uses_title_and_content_and_logs_post_id() -> None:
    session = FakeSession()
    service, client = _mock_embedding_service([0.7, 0.8])
    post = Post(id=11, title="Foxes in winter", content="Red foxes adapt to snow.")

    generated = ensure_post_embedding(session, post, service)

    request = client.models.embed_content.call_args.kwargs
    cost_logs = [record for record in session.added if isinstance(record, CostLog)]
    assert generated is True
    assert request["contents"] == "Foxes in winter\n\nRed foxes adapt to snow."
    assert post.embedding == [0.7, 0.8]
    assert post.embedding_source_hash is not None
    assert len(cost_logs) == 1
    assert cost_logs[0].post_id == 11
    assert cost_logs[0].image_id is None


def test_unchanged_post_text_skips_regeneration() -> None:
    session = FakeSession()
    service, client = _mock_embedding_service([0.7, 0.8])
    post = Post(id=11, title="Foxes in winter", content="Red foxes adapt to snow.")

    ensure_post_embedding(session, post, service)
    generated_again = ensure_post_embedding(session, post, service)

    assert generated_again is False
    assert client.models.embed_content.call_count == 1
    assert len([record for record in session.added if isinstance(record, CostLog)]) == 1


def test_failed_provider_call_still_records_cost() -> None:
    session = FakeSession()
    service, client = _mock_embedding_service([0.1])
    client.models.embed_content.side_effect = RuntimeError("provider unavailable")
    metadata = ImageMetadata(id=1, image_id=7, caption="A red fox")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        ensure_caption_embedding(session, metadata, service)

    cost_logs = [record for record in session.added if isinstance(record, CostLog)]
    assert len(cost_logs) == 1
    assert cost_logs[0].image_id == 7


def test_source_text_must_not_be_empty() -> None:
    service, client = _mock_embedding_service([0.1])
    call_log: Callable[[str], None] = MagicMock()

    with pytest.raises(ValueError, match="must not be empty"):
        service.generate_embedding("  \n", on_call=call_log)

    client.models.embed_content.assert_not_called()
    call_log.assert_not_called()