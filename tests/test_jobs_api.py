from unittest.mock import MagicMock

from fastapi import BackgroundTasks

from app.api.jobs import enqueue_image_processing, get_job
from app.jobs.image_processing import process_image_batch
from app.models.image import Image
from app.models.job import Job


def test_process_images_endpoint_schedules_background_work() -> None:
    image = Image(
        id=7,
        filename="fox.jpg",
        path="data/images/fox/fox.jpg",
        processing_status="pending",
    )
    database_session = MagicMock()
    database_session.scalars.return_value.all.return_value = [image]
    database_session.add.side_effect = lambda job: setattr(job, "id", 23)
    background_tasks = BackgroundTasks()

    job = enqueue_image_processing(background_tasks, database_session)

    assert job.id == 23
    assert job.status == "queued"
    assert job.total_items == 1
    assert image.processing_status == "processing"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is process_image_batch
    assert background_tasks.tasks[0].args == (23, [7])


def test_get_job_returns_not_found_for_unknown_id() -> None:
    from fastapi import HTTPException

    database_session = MagicMock()
    database_session.get.return_value = None

    try:
        get_job(404, database_session)
    except HTTPException as error:
        assert error.status_code == 404
    else:
        raise AssertionError("Expected an unknown job ID to return 404.")


def test_get_job_returns_existing_job() -> None:
    job = Job(
        id=23,
        job_type="image_processing",
        status="running",
        total_items=3,
        processed_items=1,
        failed_items=0,
    )
    database_session = MagicMock()
    database_session.get.return_value = job

    result = get_job(23, database_session)

    assert result is job