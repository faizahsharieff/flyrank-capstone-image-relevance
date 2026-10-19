from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    status: str
    total_items: int
    processed_items: int
    failed_items: int
    created_at: datetime
    updated_at: datetime