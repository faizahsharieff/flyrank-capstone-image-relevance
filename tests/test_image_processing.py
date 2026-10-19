from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.cost_log import CostLog
from app.models.image import Image, ImageMetadata
from app.models.job import Job
from app.schemas.image_metadata import ImageMetadataSchema
from app.services.vision import VisionResponseError, VisionResult, VisionService
from app.jobs.image_processing import process_image_batch


class FakeSession:
    def __init__(self, job: Job, images: list[Image]) -> None:
        self.records: dict[type[object], dict[int, object]] = {
            Job: {job.id: job},
            Image: {image.id: image for image in images},
        }
        self.added: list[object] = []

    def get(self, model: type[object], record_id: int) -> object | None:
        return self.records.get(model, {}).get(record_id)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_job_and_image(*, completed: bool = False) -> tuple[Job, Image]:
    job = Job(
        id=5,
        job_type="image_processing",
        status="queued",
        total_items=1,
        processed_items=0,
        failed_items=0,
    )
    image = Image(
        id=12,
        filename="fox.jpg",
        path="data/images/fox/fox.jpg",
        processing_status="completed" if completed else "processing",
    )
    if completed:
        image.image_metadata = ImageMetadata(
            id=31,
            image_id=image.id,
            subject="red fox",
            category="wildlife",
            attributes=["red fur"],
            caption="A fox outdoors.",
            confidence=0.9,
            needs_review=False,
        )
    return job, image


def _vision_result(confidence: float = 0.95) -> VisionResult:
    return VisionResult(
        metadata=ImageMetadataSchema(
            subject="red fox",
            category="wildlife",
            attributes=["red fur", "outdoors"],
            caption="A red fox standing outdoors.",
            confidence=confidence,
        ),
        needs_review=confidence < 0.70,
    )


def _run_job(
    job: Job,
    image: Image,
    vision_service: VisionService,
) -> FakeSession:
    session = FakeSession(job, [image])
    process_image_batch(
        job.id,
        [image.id],
        session_factory=lambda: session,
        vision_service_factory=lambda: vision_service,
    )
    return session


def test_successful_processing_saves_metadata_and_cost_log() -> None:
    job, image = _make_job_and_image()
    vision_service = MagicMock(spec=VisionService)
    vision_service.analyze_image.side_effect = lambda path, *, on_call: (
        on_call("mock-vision-model") or _vision_result()
    )

    session = _run_job(job, image, vision_service)

    saved_metadata = [record for record in session.added if isinstance(record, ImageMetadata)]
    cost_logs = [record for record in session.added if isinstance(record, CostLog)]
    assert image.processing_status == "completed"
    assert len(saved_metadata) == 1
    assert saved_metadata[0].attributes == ["red fur", "outdoors"]
    assert len(cost_logs) == 1
    assert cost_logs[0].image_id == image.id
    assert cost_logs[0].estimated_cost == Decimal("0")
    assert job.status == "completed"
    assert job.processed_items == 1
    assert job.failed_items == 0


def test_invalid_vision_output_marks_image_and_job_failed() -> None:
    job, image = _make_job_and_image()
    vision_service = MagicMock(spec=VisionService)

    def invalid_output(path: str, *, on_call: Callable[[str], None]) -> None:
        on_call("mock-vision-model")
        raise VisionResponseError("invalid structured output")

    vision_service.analyze_image.side_effect = invalid_output

    session = _run_job(job, image, vision_service)

    assert image.processing_status == "failed"
    assert not any(isinstance(record, ImageMetadata) for record in session.added)
    assert len([record for record in session.added if isinstance(record, CostLog)]) == 1
    assert job.status == "failed"
    assert job.failed_items == 1


def test_transient_failure_retries_and_logs_each_vision_call() -> None:
    job, image = _make_job_and_image()
    vision_service = MagicMock(spec=VisionService)
    attempts = 0

    def flaky_output(path: str, *, on_call: Callable[[str], None]) -> VisionResult:
        nonlocal attempts
        attempts += 1
        on_call("mock-vision-model")
        if attempts == 1:
            raise RuntimeError("temporary provider failure")
        return _vision_result()

    vision_service.analyze_image.side_effect = flaky_output

    session = _run_job(job, image, vision_service)

    assert attempts == 2
    assert len([record for record in session.added if isinstance(record, CostLog)]) == 2
    assert image.processing_status == "completed"
    assert job.processed_items == 1
    assert job.failed_items == 0


def test_low_confidence_metadata_is_flagged_for_review() -> None:
    job, image = _make_job_and_image()
    vision_service = MagicMock(spec=VisionService)
    vision_service.analyze_image.side_effect = lambda path, *, on_call: (
        on_call("mock-vision-model") or _vision_result(0.69)
    )

    session = _run_job(job, image, vision_service)

    saved_metadata = [record for record in session.added if isinstance(record, ImageMetadata)]
    assert len(saved_metadata) == 1
    assert saved_metadata[0].confidence == 0.69
    assert saved_metadata[0].needs_review is True


def test_completed_image_is_idempotently_skipped() -> None:
    job, image = _make_job_and_image(completed=True)
    vision_service_factory = MagicMock()
    session = FakeSession(job, [image])

    process_image_batch(
        job.id,
        [image.id],
        session_factory=lambda: session,
        vision_service_factory=vision_service_factory,
    )

    vision_service_factory.assert_not_called()
    assert not any(isinstance(record, (ImageMetadata, CostLog)) for record in session.added)
    assert image.processing_status == "completed"
    assert job.processed_items == 1
    assert job.failed_items == 0