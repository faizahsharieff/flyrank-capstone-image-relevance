from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from google import genai
from google.genai import types
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    model_name: str = Field(
        default="gemini-embedding-001", min_length=1, validation_alias="GEMINI_EMBEDDING_MODEL"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingResponseError(RuntimeError):
    pass


class EmbeddingValue(Protocol):
    values: Sequence[float] | None


class EmbeddingResponse(Protocol):
    embeddings: Sequence[EmbeddingValue | None] | None


class GeminiEmbeddingClient(Protocol):
    def embed_content(
        self,
        *,
        model: str,
        contents: str,
        config: types.EmbedContentConfig,
    ) -> EmbeddingResponse: ...


class GeminiClient(Protocol):
    models: GeminiEmbeddingClient


@dataclass(frozen=True)
class EmbeddingResult:
    values: list[float]
    model_name: str


class EmbeddingService:
    def __init__(
        self,
        client: GeminiClient | None = None,
        model_name: str | None = None,
    ) -> None:
        settings = EmbeddingSettings()
        self.model_name = model_name if model_name is not None else settings.model_name
        if not self.model_name.strip():
            raise ValueError("model_name must not be empty.")

        if client is None:
            api_key = settings.api_key.get_secret_value().strip() if settings.api_key else ""
            if not api_key:
                raise EmbeddingConfigurationError(
                    "GEMINI_API_KEY must be set to generate embeddings."
                )
            client = genai.Client(api_key=api_key)

        self._client = client

    def generate_embedding(
        self,
        text: str,
        *,
        on_call: Callable[[str], None],
    ) -> EmbeddingResult:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("Embedding source text must not be empty.")

        on_call(self.model_name)
        response = self._client.models.embed_content(
            model=self.model_name,
            contents=normalized_text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        if not response.embeddings or not response.embeddings[0]:
            raise EmbeddingResponseError("Gemini returned no embedding values.")

        values = response.embeddings[0].values
        if not values:
            raise EmbeddingResponseError("Gemini returned an empty embedding.")

        embedding = [float(value) for value in values]
        if not all(math.isfinite(value) for value in embedding):
            raise EmbeddingResponseError("Gemini returned non-finite embedding values.")

        return EmbeddingResult(values=embedding, model_name=self.model_name)