from __future__ import annotations

import re
import math
from dataclasses import dataclass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "dog": ("dog", "dogs"),
    "fox": ("fox", "foxes"),
    "hyena": ("hyena", "hyenas"),
    "jackal": ("jackal", "jackals"),
    "wolf": ("wolf", "wolves"),
}
ALL_SUPPORTED_SUBJECTS = frozenset(SUBJECT_ALIASES)
CATEGORY_SUBJECTS: dict[str, frozenset[str]] = {
    "animal": ALL_SUPPORTED_SUBJECTS,
    "animals": ALL_SUPPORTED_SUBJECTS,
    "canid": frozenset({"dog", "fox", "jackal", "wolf"}),
    "canine": frozenset({"dog", "fox", "jackal", "wolf"}),
    "mammal": ALL_SUPPORTED_SUBJECTS,
    "mammals": ALL_SUPPORTED_SUBJECTS,
    "wildlife": ALL_SUPPORTED_SUBJECTS,
}


class MismatchGuardSettings(BaseSettings):
    min_similarity: float = Field(default=0.75, ge=-1, le=1, validation_alias="MIN_SIMILARITY")
    min_confidence: float = Field(default=0.70, ge=0, le=1, validation_alias="MIN_CONFIDENCE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@dataclass(frozen=True)
class MismatchGuardResult:
    accepted: bool
    reason: str | None


class MismatchGuard:
    def __init__(
        self,
        min_similarity: float | None = None,
        min_confidence: float | None = None,
    ) -> None:
        settings = MismatchGuardSettings()
        self.min_similarity = min_similarity if min_similarity is not None else settings.min_similarity
        self.min_confidence = min_confidence if min_confidence is not None else settings.min_confidence

        if not -1 <= self.min_similarity <= 1:
            raise ValueError("min_similarity must be between -1 and 1.")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1.")

    def evaluate(
        self,
        *,
        post_title: str,
        post_content: str,
        image_subject: str,
        image_category: str,
        similarity_score: float,
        confidence: float,
    ) -> MismatchGuardResult:
        if not math.isfinite(similarity_score) or not -1 <= similarity_score <= 1:
            return MismatchGuardResult(
                accepted=False,
                reason="Invalid similarity score: expected a finite value between -1 and 1.",
            )
        if similarity_score < self.min_similarity:
            return MismatchGuardResult(
                accepted=False,
                reason=(
                    f"Similarity {similarity_score:.3f} is below the minimum "
                    f"{self.min_similarity:.3f}."
                ),
            )

        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            return MismatchGuardResult(
                accepted=False,
                reason="Invalid image confidence: expected a finite value between 0 and 1.",
            )
        if confidence < self.min_confidence:
            return MismatchGuardResult(
                accepted=False,
                reason=(
                    f"Image confidence {confidence:.3f} is below the minimum "
                    f"{self.min_confidence:.3f}."
                ),
            )

        expected_subjects = _find_subjects(post_title) or _find_subjects(post_content)
        detected_subjects = _find_subjects(image_subject)
        if not expected_subjects:
            return MismatchGuardResult(
                accepted=False,
                reason="Subject mismatch: could not identify a supported subject in the post.",
            )
        if not detected_subjects:
            return MismatchGuardResult(
                accepted=False,
                reason=f"Subject mismatch: detected subject '{image_subject}' is unsupported.",
            )
        if expected_subjects.isdisjoint(detected_subjects):
            expected_text = _format_subjects(expected_subjects)
            detected_text = _format_subjects(detected_subjects)
            return MismatchGuardResult(
                accepted=False,
                reason=f"Subject mismatch: expected {expected_text}, detected {detected_text}.",
            )

        category = image_category.strip().casefold()
        compatible_subjects = CATEGORY_SUBJECTS.get(category)
        if compatible_subjects is None or detected_subjects.isdisjoint(compatible_subjects):
            return MismatchGuardResult(
                accepted=False,
                reason=(
                    f"Category mismatch: category '{image_category}' is not compatible "
                    f"with subject '{image_subject}'."
                ),
            )

        return MismatchGuardResult(accepted=True, reason=None)


def _find_subjects(text: str) -> set[str]:
    normalized_text = text.casefold()
    return {
        subject
        for subject, aliases in SUBJECT_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_text) for alias in aliases)
    }


def _format_subjects(subjects: set[str]) -> str:
    return " or ".join(sorted(subjects))