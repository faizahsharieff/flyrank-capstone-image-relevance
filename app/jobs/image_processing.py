import logging
from collections.abc import Callable, Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.cost_log import CostLog
from app.models.image import Image, ImageMetadata
from app.models.job import Job
from app.schemas.image_metadata import ImageMetadataSchema
from app.services.vision import VisionConfigurationError, VisionResponseError, VisionService

MAX_IMAGE_ATTEMPTS = 3
logger = logging.getLogger(__name__)


def process_image_batch(
    job_id: int,
    image_ids: Sequence[int],
    *,
    session_factory: Callable[[], Session] | None = None,
    vision_service_factory: Callable[[], VisionService] | None = None,
) -> None:
    if session_factory is None:
        if SessionLocal is None:
            raise RuntimeError("DATABASE_URL must be configured before processing images.")
        session_factory = SessionLocal

    database_session = session_factory()
    try:
        job = database_session.get(Job, job_id)
        if job is None:
            return

        job.status = "running"
        database_session.commit()
        pending_images: list[Image] = []

        for image_id in image_ids:
            image = database_session.get(Image, image_id)
            if image is None:
                _record_progress(job, failed=True)
                database_session.commit()
            elif image.image_metadata is not None:
                image.processing_status = "completed"
                _record_progress(job)
                database_session.commit()
            else:
                pending_images.append(image)

        if pending_images:
            factory = vision_service_factory or VisionService
            try:
                vision_service = factory()
            except Exception:
                logger.exception("Could not initialize vision service for job %s", job_id)
                for image in pending_images:
                    image.processing_status = "failed"
                    _record_progress(job, failed=True)
                database_session.commit()
            else:
                for image in pending_images:
                    _process_image(
                        database_session,
                        job,
                        image,
                        vision_service,
                    )

        job.status = "failed" if job.failed_items == job.total_items and job.total_items else "completed"
        database_session.commit()
    except Exception:
        database_session.rollback()
        job = database_session.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            database_session.commit()
        raise
    finally:
        database_session.close()


def _process_image(
    database_session: Session,
    job: Job,
    image: Image,
    vision_service: VisionService,
) -> None:
    def log_vision_call(model_name: str) -> None:
        database_session.add(
            CostLog(
                operation="vision",
                model_name=model_name,
                estimated_cost=Decimal("0"),
                image_id=image.id,
            )
        )
        database_session.commit()

    for attempt in range(MAX_IMAGE_ATTEMPTS):
        try:
            result = vision_service.analyze_image(image.path, on_call=log_vision_call)
            metadata = ImageMetadataSchema.model_validate(result.metadata)
        except VisionResponseError:
            logger.exception("Invalid vision response for image %s", image.id)
            break
        except (VisionConfigurationError, FileNotFoundError, ValueError):
            logger.exception("Permanent image processing failure for image %s", image.id)
            break
        except Exception:
            logger.exception(
                "Vision attempt %s/%s failed for image %s",
                attempt + 1,
                MAX_IMAGE_ATTEMPTS,
                image.id,
            )
            if attempt + 1 < MAX_IMAGE_ATTEMPTS:
                continue
            break

        image.image_metadata = ImageMetadata(
            image_id=image.id,
            subject=metadata.subject,
            category=metadata.category,
            attributes=metadata.attributes,
            caption=metadata.caption,
            confidence=metadata.confidence,
            needs_review=metadata.confidence < 0.70,
        )
        database_session.add(image.image_metadata)
        image.processing_status = "completed"
        _record_progress(job)
        database_session.commit()
        return

    image.processing_status = "failed"
    _record_progress(job, failed=True)
    database_session.commit()


def _record_progress(job: Job, *, failed: bool = False) -> None:
    job.processed_items += 1
    if failed:
        job.failed_items += 1