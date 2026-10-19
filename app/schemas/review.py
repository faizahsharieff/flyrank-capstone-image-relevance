from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ReviewDecision = Literal["approve", "reject"]


class ReviewDecisionRequest(BaseModel):
    decision: ReviewDecision


class ReviewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suggestion_id: int
    decision: ReviewDecision
    created_at: datetime


class InspectionImageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    path: str


class InspectionPostSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str


class SuggestionInspectionSchema(BaseModel):
    suggestion_id: int
    image: InspectionImageSchema
    post: InspectionPostSchema
    similarity_score: float
    image_confidence: float | None
    detected_subject: str | None
    detected_category: str | None
    guard_result: str
    guard_explanation: str | None