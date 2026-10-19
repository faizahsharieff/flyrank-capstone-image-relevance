import json

import pytest

from app.services.matcher import ImageMatchResult, RankedImage
from scripts.evaluate import (
    EvaluationExample,
    evaluate_examples,
    format_report,
    load_evaluation_examples,
)


class StubMatcher:
    def __init__(self, results: dict[int, ImageMatchResult]) -> None:
        self.results = results

    def rank_post_images(self, database_session, post_id: int, *, limit: int = 5) -> ImageMatchResult:
        assert limit == 1
        return self.results[post_id]


def test_evaluation_calculates_top1_precision_and_reports_failures() -> None:
    examples = [
        EvaluationExample(post_id=1, correct_image_id=101),
        EvaluationExample(post_id=2, correct_image_id=202),
        EvaluationExample(post_id=3, correct_image_id=303),
    ]
    matcher = StubMatcher(
        {
            1: ImageMatchResult(
                status="matched",
                suggestions=[RankedImage(101, "fox.jpg", "fox.jpg", 0.95)],
                reason=None,
            ),
            2: ImageMatchResult(
                status="matched",
                suggestions=[RankedImage(999, "wolf.jpg", "wolf.jpg", 0.90)],
                reason="Rejected one candidate: subject mismatch.",
            ),
            3: ImageMatchResult(
                status="no_confident_match",
                suggestions=[],
                reason="No confident image match. Similarity is too low.",
            ),
        }
    )

    report = evaluate_examples(examples, database_session=None, matcher=matcher)

    assert report.examples == 3
    assert report.correct_top1 == 1
    assert report.top1_precision == 1 / 3
    assert [failure.post_id for failure in report.failures] == [2, 3]
    assert report.failures[0].top_image_id == 999
    assert report.failures[1].top_image_id is None


def test_report_format_includes_summary_and_incorrect_posts() -> None:
    examples = [EvaluationExample(post_id=1, correct_image_id=5)]
    matcher = StubMatcher(
        {
            1: ImageMatchResult(
                status="matched",
                suggestions=[RankedImage(6, "wolf.jpg", "wolf.jpg", 0.81)],
                reason="Subject mismatch: expected fox, detected wolf.",
            )
        }
    )

    output = format_report(evaluate_examples(examples, None, matcher))

    assert "Evaluation examples: 1" in output
    assert "Correct top-1: 0" in output
    assert "Top-1 precision: 0.00" in output
    assert "post_id=1, expected_image_id=5, top_image_id=6" in output
    assert "Subject mismatch: expected fox, detected wolf." in output


def test_empty_evaluation_set_has_no_division_by_zero() -> None:
    report = evaluate_examples([], database_session=None, matcher=StubMatcher({}))

    assert report.top1_precision is None
    assert format_report(report).endswith(
        "No labeled examples. Add post_id and correct_image_id entries to data/eval.json."
    )


def test_invalid_evaluation_json_has_clear_error(tmp_path) -> None:
    evaluation_path = tmp_path / "eval.json"
    evaluation_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        load_evaluation_examples(evaluation_path)


def test_evaluation_examples_validate_positive_ids(tmp_path) -> None:
    evaluation_path = tmp_path / "eval.json"
    evaluation_path.write_text(
        json.dumps({"examples": [{"post_id": 0, "correct_image_id": -2}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Evaluation data is invalid"):
        load_evaluation_examples(evaluation_path)