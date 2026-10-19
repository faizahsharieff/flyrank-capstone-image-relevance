from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.models.suggestion import Suggestion
from app.services.mismatch_guard import MismatchGuard
from app.utils.similarity import cosine_similarity


class PostNotFoundError(LookupError):
    pass


class PostEmbeddingNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class RankedImage:
    image_id: int
    filename: str
    path: str
    similarity_score: float
    suggestion_id: int | None = None


@dataclass(frozen=True)
class ImageMatchResult:
    status: str
    suggestions: list[RankedImage]
    reason: str | None


def rank_image_embeddings(
    post_embedding: Sequence[float],
    image_rows: Iterable[tuple[Image, Sequence[float] | None]],
    *,
    limit: int = 5,
) -> list[RankedImage]:
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    ranked_images = [
        RankedImage(
            image_id=image.id,
            filename=image.filename,
            path=image.path,
            similarity_score=cosine_similarity(post_embedding, image_embedding),
        )
        for image, image_embedding in image_rows
        if image_embedding is not None
    ]
    ranked_images.sort(key=lambda candidate: (-candidate.similarity_score, candidate.image_id))
    return ranked_images[:limit]


class ImageMatcher:
    def __init__(self, mismatch_guard: MismatchGuard | None = None) -> None:
        self._mismatch_guard = mismatch_guard or MismatchGuard()

    def rank_post_images(
        self,
        database_session: Session,
        post_id: int,
        *,
        limit: int = 5,
    ) -> ImageMatchResult:
        post = database_session.get(Post, post_id)
        if post is None:
            raise PostNotFoundError(f"Post {post_id} was not found.")
        if post.embedding is None:
            raise PostEmbeddingNotFoundError(f"Post {post_id} has no embedding yet.")

        image_rows = list(database_session.execute(
            select(Image, ImageMetadata, ImageMetadata.caption_embedding)
            .join(ImageMetadata, ImageMetadata.image_id == Image.id)
            .where(ImageMetadata.caption_embedding.is_not(None))
        ).all())
        if not image_rows:
            return ImageMatchResult(
                status="no_confident_match",
                suggestions=[],
                reason="No image candidates with embeddings are available.",
            )

        ranked_images = rank_image_embeddings(
            post.embedding,
            [(image, embedding) for image, _, embedding in image_rows],
            limit=len(image_rows),
        )
        metadata_by_image_id = {image.id: metadata for image, metadata, _ in image_rows}
        accepted_images: list[RankedImage] = []
        rejected_reasons: list[str] = []

        for candidate in ranked_images:
            metadata = metadata_by_image_id[candidate.image_id]
            guard_result = self._mismatch_guard.evaluate(
                post_title=post.title,
                post_content=post.content,
                image_subject=metadata.subject,
                image_category=metadata.category,
                similarity_score=candidate.similarity_score,
                confidence=metadata.confidence,
            )
            suggestion_id = _upsert_suggestion(
                database_session,
                post_id=post.id,
                image_id=candidate.image_id,
                similarity_score=candidate.similarity_score,
                guard_status="accepted" if guard_result.accepted else "rejected",
                guard_reason=guard_result.reason,
            )
            if guard_result.accepted:
                accepted_images.append(
                    RankedImage(
                        image_id=candidate.image_id,
                        filename=candidate.filename,
                        path=candidate.path,
                        similarity_score=candidate.similarity_score,
                        suggestion_id=suggestion_id,
                    )
                )
            elif guard_result.reason is not None:
                rejected_reasons.append(guard_result.reason)

        database_session.commit()

        if not accepted_images:
            reason = rejected_reasons[0] if rejected_reasons else "No candidate passed the mismatch guard."
            return ImageMatchResult(
                status="no_confident_match",
                suggestions=[],
                reason=f"No confident image match. {reason}",
            )

        return ImageMatchResult(
            status="matched",
            suggestions=accepted_images[:limit],
            reason=(
                f"Rejected {len(rejected_reasons)} candidate(s): "
                + " ".join(rejected_reasons)
                if rejected_reasons
                else None
            ),
        )


def _upsert_suggestion(
    database_session: Session,
    *,
    post_id: int,
    image_id: int,
    similarity_score: float,
    guard_status: str,
    guard_reason: str | None,
) -> int:
    insert_statement = postgresql_insert(Suggestion).values(
        post_id=post_id,
        image_id=image_id,
        similarity_score=similarity_score,
        guard_status=guard_status,
        guard_reason=guard_reason,
    )
    upsert_statement = insert_statement.on_conflict_do_update(
        constraint="uq_suggestions_post_image",
        set_={
            "similarity_score": insert_statement.excluded.similarity_score,
            "guard_status": insert_statement.excluded.guard_status,
            "guard_reason": insert_statement.excluded.guard_reason,
        },
    ).returning(Suggestion.id)
    return database_session.execute(upsert_statement).scalar_one()