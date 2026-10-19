import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.jobs.embedding_processing import ensure_post_embedding
from app.models.post import Post
from app.schemas.post import PostCreateSchema, PostResponseSchema
from app.schemas.suggestion import ImageMatchResponse
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    EmbeddingService,
)
from app.services.matcher import (
    ImageMatcher,
    PostEmbeddingNotFoundError,
    PostNotFoundError,
)

router = APIRouter(prefix="/posts", tags=["posts"])
image_matcher = ImageMatcher()
logger = logging.getLogger(__name__)


@router.post("", response_model=PostResponseSchema, status_code=status.HTTP_201_CREATED)
def create_post(
    post_input: PostCreateSchema,
    database_session: Session = Depends(get_db),
) -> Post:
    try:
        embedding_service = EmbeddingService()
    except EmbeddingConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Post creation requires a configured Gemini embedding service.",
        ) from error

    post = Post(title=post_input.title, content=post_input.content)
    database_session.add(post)

    try:
        database_session.flush()
        ensure_post_embedding(database_session, post, embedding_service)
        database_session.refresh(post)
    except (EmbeddingResponseError, ValueError) as error:
        logger.exception("Embedding generation failed for post %s", post.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Post {post.id} was saved, but its embedding could not be generated.",
        ) from error
    except Exception as error:
        logger.exception("Embedding provider failed for post %s", post.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Post {post.id} was saved, but its embedding could not be generated.",
        ) from error

    return post


@router.get("/{post_id}/images", response_model=ImageMatchResponse)
def rank_post_images(
    post_id: int,
    limit: int = Query(default=5, ge=1, le=50),
    database_session: Session = Depends(get_db),
) -> ImageMatchResponse:
    try:
        result = image_matcher.rank_post_images(database_session, post_id, limit=limit)
        return ImageMatchResponse(
            status=result.status,
            suggestions=[
                {
                    "suggestion_id": image.suggestion_id,
                    "image_id": image.image_id,
                    "filename": image.filename,
                    "path": image.path,
                    "similarity_score": image.similarity_score,
                    "accepted": True,
                }
                for image in result.suggestions
            ],
            reason=result.reason,
        )
    except PostNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except PostEmbeddingNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error