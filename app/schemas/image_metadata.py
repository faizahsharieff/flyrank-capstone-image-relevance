from pydantic import BaseModel, ConfigDict, Field


class ImageMetadataSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(min_length=1)
    category: str = Field(min_length=1)
    attributes: list[str]
    caption: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1, strict=True)