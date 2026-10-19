from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.jobs.embedding_processing import ensure_caption_embedding, ensure_post_embedding
from app.models.image import Image, ImageMetadata
from app.models.post import Post
from app.services.embeddings import EmbeddingService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = PROJECT_ROOT / "data" / "images"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SAMPLE_POSTS = (
    (
        "Red foxes in the wild",
        "Red foxes are adaptable wild canids. This article explores fox behavior, habitat, and survival.",
    ),
    (
        "Understanding domestic dogs",
        "Dogs are domesticated canids. This article discusses dog behavior, activity, and care.",
    ),
    (
        "Hyenas and their habitats",
        "Hyenas are distinctive mammals living in varied habitats. This article describes hyena behavior and ecology.",
    ),
    (
        "Jackals of the wild",
        "Jackals are wild canids. This article covers jackal habitats, behavior, and adaptation.",
    ),
    (
        "Wolves and pack behavior",
        "Wolves are wild canids known for social packs. This article explores wolf behavior and habitat.",
    ),
)


def discover_image_paths(image_root: Path = IMAGE_ROOT) -> list[Path]:
    return sorted(
        path
        for path in image_root.rglob("*")
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
    )


def seed_records(database_session: Session, image_root: Path = IMAGE_ROOT) -> tuple[int, int]:
    if not image_root.is_dir():
        raise FileNotFoundError(f"Image directory not found: {image_root}")

    images_added = 0
    for image_path in discover_image_paths(image_root):
        stored_path = image_path.relative_to(PROJECT_ROOT).as_posix()
        existing_image = database_session.scalar(select(Image).where(Image.path == stored_path))
        if existing_image is None:
            database_session.add(
                Image(
                    filename=image_path.name,
                    path=stored_path,
                    processing_status="pending",
                )
            )
            images_added += 1

    posts_added = 0
    for title, content in SAMPLE_POSTS:
        existing_post = database_session.scalar(select(Post).where(Post.title == title))
        if existing_post is None:
            database_session.add(Post(title=title, content=content))
            posts_added += 1

    database_session.commit()
    return images_added, posts_added


def generate_missing_embeddings(database_session: Session) -> tuple[int, int]:
    embedding_service = EmbeddingService()
    posts = database_session.scalars(select(Post).order_by(Post.id)).all()
    metadata_rows = database_session.scalars(select(ImageMetadata).order_by(ImageMetadata.id)).all()

    post_embeddings = sum(
        ensure_post_embedding(database_session, post, embedding_service) for post in posts
    )
    image_embeddings = sum(
        ensure_caption_embedding(database_session, metadata, embedding_service)
        for metadata in metadata_rows
    )
    return post_embeddings, image_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local images and sample posts.")
    parser.add_argument(
        "--embeddings",
        action="store_true",
        help="also generate missing embeddings for posts and processed image metadata",
    )
    arguments = parser.parse_args()

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL must be configured before running the seed script.")

    database_session = SessionLocal()
    try:
        try:
            images_added, posts_added = seed_records(database_session)
        except FileNotFoundError as error:
            raise SystemExit(f"Seed input error: {error}") from error
        print(f"Images added: {images_added}")
        print(f"Sample posts added: {posts_added}")

        if arguments.embeddings:
            posts_embedded, images_embedded = generate_missing_embeddings(database_session)
            print(f"Post embeddings generated: {posts_embedded}")
            print(f"Image caption embeddings generated: {images_embedded}")
    finally:
        database_session.close()


if __name__ == "__main__":
    main()