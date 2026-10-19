from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.suggestion import Suggestion
from app.schemas.review import (
    ReviewDecision,
    ReviewDecisionRequest,
    ReviewSchema,
    SuggestionInspectionSchema,
)
from app.services.reviews import (
    InvalidReviewDecisionError,
    SuggestionNotFoundError,
    get_suggestion,
    record_review,
)

router = APIRouter(prefix="/suggestions", tags=["reviews"])


@router.get("/{suggestion_id}", response_model=SuggestionInspectionSchema)
def inspect_suggestion(
    suggestion_id: int,
    database_session: Session = Depends(get_db),
) -> SuggestionInspectionSchema:
    try:
        suggestion = get_suggestion(database_session, suggestion_id)
    except SuggestionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    metadata = suggestion.image.image_metadata
    return SuggestionInspectionSchema(
        suggestion_id=suggestion.id,
        image=suggestion.image,
        post=suggestion.post,
        similarity_score=suggestion.similarity_score,
        image_confidence=metadata.confidence if metadata else None,
        detected_subject=metadata.subject if metadata else None,
        detected_category=metadata.category if metadata else None,
        guard_result=suggestion.guard_status,
        guard_explanation=suggestion.guard_reason,
    )


@router.post("/{suggestion_id}/approve", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
def approve_suggestion(
    suggestion_id: int,
    decision_request: ReviewDecisionRequest | None = Body(default=None),
    database_session: Session = Depends(get_db),
) -> ReviewSchema:
    return _create_review(
        database_session,
        suggestion_id,
        expected_decision="approve",
        decision_request=decision_request,
    )


@router.post("/{suggestion_id}/reject", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
def reject_suggestion(
    suggestion_id: int,
    decision_request: ReviewDecisionRequest | None = Body(default=None),
    database_session: Session = Depends(get_db),
) -> ReviewSchema:
    return _create_review(
        database_session,
        suggestion_id,
        expected_decision="reject",
        decision_request=decision_request,
    )


def _create_review(
    database_session: Session,
    suggestion_id: int,
    *,
    expected_decision: ReviewDecision,
    decision_request: ReviewDecisionRequest | None,
) -> ReviewSchema:
    if decision_request is not None and decision_request.decision != expected_decision:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This endpoint only accepts the '{expected_decision}' decision.",
        )

    try:
        review = record_review(database_session, suggestion_id, expected_decision)
    except SuggestionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidReviewDecisionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

    return ReviewSchema.model_validate(review)