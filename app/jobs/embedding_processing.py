from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cost_log import CostLog
from app.models.image import ImageMetadata
from app.models.post import Post
from app.services.embeddings import EmbeddingService


def ensure_caption_embedding(
    database_session: Session,
    image_metadata: ImageMetadata,
    embedding_service: EmbeddingService,
) -> bool:
    source_text = image_metadata.caption
    source_hash = _source_hash(source_text)
    if image_metadata.caption_embedding and image_metadata.caption_embedding_source_hash == source_hash:
        return False

    result = embedding_service.generate_embedding(
        source_text,
        on_call=lambda model_name: _record_cost(
            database_session,
            model_name=model_name,
            image_id=image_metadata.image_id,
        ),
    )
    image_metadata.caption_embedding = result.values
    image_metadata.caption_embedding_source_hash = source_hash
    database_session.commit()
    return True


def ensure_post_embedding(
    database_session: Session,
    post: Post,
    embedding_service: EmbeddingService,
) -> bool:
    source_text = _post_embedding_text(post.title, post.content)
    source_hash = _source_hash(source_text)
    if post.embedding and post.embedding_source_hash == source_hash:
        return False

    result = embedding_service.generate_embedding(
        source_text,
        on_call=lambda model_name: _record_cost(
            database_session,
            model_name=model_name,
            post_id=post.id,
        ),
    )
    post.embedding = result.values
    post.embedding_source_hash = source_hash
    database_session.commit()
    return True


def _post_embedding_text(title: str, content: str) -> str:
    return f"{title.strip()}\n\n{content.strip()}"


def _source_hash(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _record_cost(
    database_session: Session,
    *,
    model_name: str,
    image_id: int | None = None,
    post_id: int | None = None,
) -> None:
    database_session.add(
        CostLog(
            operation="embedding",
            model_name=model_name,
            estimated_cost=Decimal("0"),
            image_id=image_id,
            post_id=post_id,
        )
    )
    database_session.commit()