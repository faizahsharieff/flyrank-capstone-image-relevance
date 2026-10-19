
from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.api.posts import router as posts_router
from app.api.reviews import router as reviews_router

app = FastAPI(title="AI Image Understanding & Content Matching Engine")
app.include_router(jobs_router)
app.include_router(posts_router)
app.include_router(reviews_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}