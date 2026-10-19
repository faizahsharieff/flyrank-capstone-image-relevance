from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.image_metadata import ImageMetadataSchema

REVIEW_CONFIDENCE_THRESHOLD = 0.70
VISION_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "subject": types.Schema(type=types.Type.STRING, min_length=1),
        "category": types.Schema(type=types.Type.STRING, min_length=1),
        "attributes": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        ),
        "caption": types.Schema(type=types.Type.STRING, min_length=1),
        "confidence": types.Schema(type=types.Type.NUMBER, minimum=0, maximum=1),
    },
    required=["subject", "category", "attributes", "caption", "confidence"],
)


class VisionSettings(BaseSettings):
    api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    model_name: str = Field(
        default="gemini-2.5-flash", min_length=1, validation_alias="GEMINI_VISION_MODEL"
    )
    max_attempts: int = Field(
        default=3, ge=1, le=10, validation_alias="GEMINI_VISION_MAX_ATTEMPTS"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class VisionConfigurationError(RuntimeError):
    pass


class VisionResponseError(RuntimeError):
    pass


class GeminiResponse(Protocol):
    text: str | None


class GeminiModels(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: list[str | types.Part],
        config: types.GenerateContentConfig,
    ) -> GeminiResponse: ...


class GeminiClient(Protocol):
    models: GeminiModels


@dataclass(frozen=True)
class VisionResult:
    metadata: ImageMetadataSchema
    needs_review: bool


class VisionService:
    def __init__(
        self,
        client: GeminiClient | None = None,
        model_name: str | None = None,
        max_attempts: int | None = None,
    ) -> None:
        settings = VisionSettings()
        self.model_name = model_name if model_name is not None else settings.model_name
        self.max_attempts = max_attempts if max_attempts is not None else settings.max_attempts

        if not self.model_name.strip():
            raise ValueError("model_name must not be empty.")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10.")

        if client is None:
            api_key = settings.api_key.get_secret_value().strip() if settings.api_key else ""
            if not api_key:
                raise VisionConfigurationError("GEMINI_API_KEY must be set to use vision analysis.")
            client = genai.Client(api_key=api_key)

        self._client = client

    def analyze_image(
        self,
        image_path: str | Path,
        *,
        on_call: Callable[[str], None] | None = None,
    ) -> VisionResult:
        path = Path(image_path)
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type is None or not mime_type.startswith("image/"):
            raise ValueError(f"Unsupported image file type: {path.name}")

        image_part = types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=VISION_RESPONSE_SCHEMA,
        )
        last_error: Exception | None = None

        for attempt in range(self.max_attempts):
            prompt = self._prompt(retry=attempt > 0)
            if on_call is not None:
                on_call(self.model_name)
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[prompt, image_part],
                config=config,
            )
            try:
                response_text = response.text
                if not response_text:
                    raise ValueError("Gemini returned an empty response.")
                payload = json.loads(response_text)
                metadata = ImageMetadataSchema.model_validate(payload)
            except (ValidationError, ValueError, TypeError) as error:
                last_error = error
                continue

            return VisionResult(
                metadata=metadata,
                needs_review=metadata.confidence < REVIEW_CONFIDENCE_THRESHOLD,
            )

        raise VisionResponseError(
            f"Gemini returned invalid image metadata after {self.max_attempts} attempts."
        ) from last_error

    @staticmethod
    def _prompt(*, retry: bool) -> str:
        instruction = (
            "Analyze the image and identify its main subject, broad category, visible attributes, "
            "a concise caption, and confidence from 0 to 1. Return only the requested structured "
            "metadata. Do not infer details that are not visible."
        )
        if retry:
            instruction += " Your previous response was invalid; return valid JSON matching the schema."
        return instruction