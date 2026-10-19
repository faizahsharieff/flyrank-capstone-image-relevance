from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.services.matcher import (
    ImageMatchResult,
    ImageMatcher,
    PostEmbeddingNotFoundError,
    PostNotFoundError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION_FILE = PROJECT_ROOT / "data" / "eval.json"


class EvaluationExample(BaseModel):
    post_id: int = Field(gt=0)
    correct_image_id: int = Field(gt=0)


class EvaluationDataset(BaseModel):
    examples: list[EvaluationExample]


class Matcher(Protocol):
    def rank_post_images(
        self,
        database_session: Session,
        post_id: int,
        *,
        limit: int = 5,
    ) -> ImageMatchResult: ...


@dataclass(frozen=True)
class EvaluationFailure:
    post_id: int
    correct_image_id: int
    top_image_id: int | None
    reason: str


@dataclass(frozen=True)
class EvaluationReport:
    examples: int
    correct_top1: int
    top1_precision: float | None
    failures: tuple[EvaluationFailure, ...]


def load_evaluation_examples(path: Path = DEFAULT_EVALUATION_FILE) -> list[EvaluationExample]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(EvaluationDataset).validate_python(payload).examples
    except FileNotFoundError as error:
        raise ValueError(f"Evaluation file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Evaluation file is not valid JSON: {error.msg}") from error
    except ValidationError as error:
        raise ValueError(f"Evaluation data is invalid: {error}") from error


def evaluate_examples(
    examples: list[EvaluationExample],
    database_session: Session,
    matcher: Matcher | None = None,
) -> EvaluationReport:
    image_matcher = matcher or ImageMatcher()
    failures: list[EvaluationFailure] = []
    correct_top1 = 0

    for example in examples:
        try:
            match_result = image_matcher.rank_post_images(
                database_session,
                example.post_id,
                limit=1,
            )
            top_image_id = (
                match_result.suggestions[0].image_id if match_result.suggestions else None
            )
            reason = match_result.reason or "The top accepted image did not match the label."
        except (PostNotFoundError, PostEmbeddingNotFoundError) as error:
            top_image_id = None
            reason = str(error)

        if top_image_id == example.correct_image_id:
            correct_top1 += 1
        else:
            failures.append(
                EvaluationFailure(
                    post_id=example.post_id,
                    correct_image_id=example.correct_image_id,
                    top_image_id=top_image_id,
                    reason=reason,
                )
            )

    precision = correct_top1 / len(examples) if examples else None
    return EvaluationReport(
        examples=len(examples),
        correct_top1=correct_top1,
        top1_precision=precision,
        failures=tuple(failures),
    )


def format_report(report: EvaluationReport) -> str:
    precision = f"{report.top1_precision:.2f}" if report.top1_precision is not None else "N/A"
    lines = [
        f"Evaluation examples: {report.examples}",
        f"Correct top-1: {report.correct_top1}",
        f"Top-1 precision: {precision}",
    ]

    if report.examples == 0:
        lines.append("No labeled examples. Add post_id and correct_image_id entries to data/eval.json.")

    for failure in report.failures:
        top_image = str(failure.top_image_id) if failure.top_image_id is not None else "no match"
        lines.append(
            f"Failure: post_id={failure.post_id}, expected_image_id={failure.correct_image_id}, "
            f"top_image_id={top_image}; {failure.reason}"
        )

    return "\n".join(lines)


def main() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL must be configured before running evaluation.")

    try:
        examples = load_evaluation_examples()
    except ValueError as error:
        raise SystemExit(f"Evaluation input error: {error}") from error
    database_session = SessionLocal()
    try:
        report = evaluate_examples(examples, database_session)
    finally:
        database_session.close()

    print(format_report(report))


if __name__ == "__main__":
    main()