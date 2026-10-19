from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostCreateSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)


class PostResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    created_at: datetime