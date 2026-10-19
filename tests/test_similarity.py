import pytest

from app.utils.similarity import cosine_similarity


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_similarity_of_opposite_vectors_is_negative_one() -> None:
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_cosine_similarity_returns_zero_for_zero_vector() -> None:
    assert cosine_similarity([0, 0], [1, 1]) == 0.0


@pytest.mark.parametrize(
    ("vector_a", "vector_b"),
    [([], []), ([1], [1, 2]), ([[1, 2]], [1, 2]), ([float("nan")], [1])],
)
def test_cosine_similarity_rejects_invalid_vectors(
    vector_a: list[object], vector_b: list[object]
) -> None:
    with pytest.raises(ValueError):
        cosine_similarity(vector_a, vector_b)