from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.jobs.image_processing import process_image_batch
from app.models.image import Image
from app.models.job import Job
from app.schemas.job import JobSchema

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/process-images", response_model=JobSchema, status_code=status.HTTP_202_ACCEPTED)
def enqueue_image_processing(
    background_tasks: BackgroundTasks,
    database_session: Session = Depends(get_db),
) -> Job:
    images = list(
        database_session.scalars(
            select(Image)
            .where(Image.processing_status == "pending")
            .order_by(Image.id)
            .with_for_update(skip_locked=True)
        ).all()
    )
    image_ids = [image.id for image in images]
    job = Job(
        job_type="image_processing",
        status="queued" if image_ids else "completed",
        total_items=len(image_ids),
        processed_items=0,
        failed_items=0,
    )
    database_session.add(job)

    for image in images:
        image.processing_status = "processing"

    database_session.commit()
    database_session.refresh(job)

    if image_ids:
        background_tasks.add_task(process_image_batch, job.id, image_ids)

    return job


@router.get("/{job_id}", response_model=JobSchema)
def get_job(job_id: int, database_session: Session = Depends(get_db)) -> Job:
    job = database_session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job