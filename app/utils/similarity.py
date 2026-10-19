from collections.abc import Sequence

import numpy as np


def cosine_similarity(vector_a: Sequence[float], vector_b: Sequence[float]) -> float:
    values_a = np.asarray(vector_a, dtype=np.float64)
    values_b = np.asarray(vector_b, dtype=np.float64)

    if values_a.ndim != 1 or values_b.ndim != 1:
        raise ValueError("Cosine similarity requires one-dimensional vectors.")
    if values_a.size == 0 or values_b.size == 0:
        raise ValueError("Cosine similarity requires non-empty vectors.")
    if values_a.shape != values_b.shape:
        raise ValueError("Cosine similarity requires vectors of equal length.")
    if not np.isfinite(values_a).all() or not np.isfinite(values_b).all():
        raise ValueError("Cosine similarity requires finite vector values.")

    norm_product = np.linalg.norm(values_a) * np.linalg.norm(values_b)
    if norm_product == 0:
        return 0.0

    similarity = float(np.dot(values_a, values_b) / norm_product)
    return float(np.clip(similarity, -1.0, 1.0))