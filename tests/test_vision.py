import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from google.genai import types

from app.schemas.image_metadata import ImageMetadataSchema
from app.services.vision import VISION_RESPONSE_SCHEMA, VisionResponseError, VisionService


def _make_service(
    image_path: Path,
    responses: list[str | None],
    *,
    max_attempts: int = 3,
) -> tuple[VisionService, MagicMock]:
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text=response_text) for response_text in responses
    ]
    service = VisionService(client=client, model_name="mock-vision-model", max_attempts=max_attempts)
    image_path.write_bytes(b"mock image bytes")
    return service, client


def _metadata_json(*, confidence: float = 0.92) -> str:
    return json.dumps(
        {
            "subject": "red fox",
            "category": "wildlife",
            "attributes": ["red fur", "outdoors"],
            "caption": "A red fox standing outdoors.",
            "confidence": confidence,
        }
    )


def test_valid_response_requests_structured_json_and_flags_low_confidence(tmp_path: Path) -> None:
    image_path = tmp_path / "fox.jpg"
    service, client = _make_service(image_path, [_metadata_json(confidence=0.69)])

    result = service.analyze_image(image_path)

    assert isinstance(result.metadata, ImageMetadataSchema)
    assert result.metadata.subject == "red fox"
    assert result.needs_review is True
    request = client.models.generate_content.call_args.kwargs
    assert request["model"] == "mock-vision-model"
    assert request["config"].response_mime_type == "application/json"
    assert request["config"].response_schema is VISION_RESPONSE_SCHEMA
    assert request["config"].response_schema.additional_properties is None
    assert request["config"].response_schema.required == [
        "subject",
        "category",
        "attributes",
        "caption",
        "confidence",
    ]


def test_gemini_request_schema_does_not_include_unsupported_additional_properties() -> None:
    assert isinstance(VISION_RESPONSE_SCHEMA, types.Schema)
    assert VISION_RESPONSE_SCHEMA.additional_properties is None


def test_malformed_response_is_retried_then_validated(tmp_path: Path) -> None:
    image_path = tmp_path / "fox.jpg"
    service, client = _make_service(image_path, ["not JSON", _metadata_json()])

    result = service.analyze_image(image_path)

    assert result.metadata.confidence == 0.92
    assert result.needs_review is False
    assert client.models.generate_content.call_count == 2


def test_invalid_schema_output_is_retried_and_never_returned(tmp_path: Path) -> None:
    image_path = tmp_path / "fox.jpg"
    invalid_response = _metadata_json(confidence=1.5)
    service, client = _make_service(image_path, [invalid_response, invalid_response], max_attempts=2)

    with pytest.raises(VisionResponseError):
        service.analyze_image(image_path)

    assert client.models.generate_content.call_count == 2


def test_metadata_schema_rejects_confidence_outside_range() -> None:
    with pytest.raises(ValidationError):
        ImageMetadataSchema.model_validate(
            {
                "subject": "fox",
                "category": "wildlife",
                "attributes": [],
                "caption": "A fox.",
                "confidence": -0.1,
            }
        )


def test_service_uses_gemini_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("GEMINI_VISION_MODEL", "configured-vision-model")
    monkeypatch.setenv("GEMINI_VISION_MAX_ATTEMPTS", "4")
    mock_client = MagicMock()
    client_factory = MagicMock(return_value=mock_client)
    monkeypatch.setattr("app.services.vision.genai.Client", client_factory)

    service = VisionService()

    client_factory.assert_called_once_with(api_key="test-api-key")
    assert service.model_name == "configured-vision-model"
    assert service.max_attempts == 4


def test_zero_max_attempts_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        VisionService(client=MagicMock(), max_attempts=0)