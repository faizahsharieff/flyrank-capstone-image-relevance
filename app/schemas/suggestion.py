from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RankedImageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    suggestion_id: int
    image_id: int
    filename: str
    path: str
    similarity_score: float = Field(ge=-1, le=1)
    accepted: bool = True
    reason: str | None = None


class ImageMatchResponse(BaseModel):
    status: Literal["matched", "no_confident_match"]
    suggestions: list[RankedImageSchema]
    reason: str | None = None