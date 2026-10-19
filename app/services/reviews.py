from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.suggestion import Suggestion
from app.schemas.review import ReviewDecision


class SuggestionNotFoundError(LookupError):
    pass


class InvalidReviewDecisionError(ValueError):
    pass


def get_suggestion(database_session: Session, suggestion_id: int) -> Suggestion:
    suggestion = database_session.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise SuggestionNotFoundError(f"Suggestion {suggestion_id} was not found.")
    return suggestion


def record_review(
    database_session: Session,
    suggestion_id: int,
    decision: str,
) -> Review:
    if decision not in ("approve", "reject"):
        raise InvalidReviewDecisionError("Decision must be 'approve' or 'reject'.")

    get_suggestion(database_session, suggestion_id)
    review = Review(suggestion_id=suggestion_id, decision=decision)
    database_session.add(review)
    database_session.commit()
    database_session.refresh(review)
    return review