import math

import pytest

from tools.evaluation.stats import (
    DEFAULT_BANDS,
    agreement,
    auc,
    band,
    pearson,
    ranks,
    spearman,
    weighted_kappa,
)  # fmt: skip


def test_pearson_and_spearman_known_values():
    x, y = [1, 2, 3, 4, 5], [2, 4, 5, 4, 5]
    assert pearson(x, y) == pytest.approx(0.7745966, abs=1e-6)  # textbook example
    assert pearson(x, [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert pearson(x, [5, 5, 5, 5, 5]) is None
    # Spearman only cares about order: any increasing transform gives 1.
    assert spearman(x, [math.exp(v) for v in x]) == pytest.approx(1.0)
    assert ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_weighted_kappa():
    assert weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3], 4) == pytest.approx(1.0)
    # Systematically reversed ratings: worse than chance.
    assert weighted_kappa([0, 1, 2, 3], [3, 2, 1, 0], 4) == pytest.approx(-1.0)
    assert weighted_kappa([1, 1, 1], [1, 1, 1], 4) is None


def test_auc_is_mann_whitney():
    assert auc([90, 80, 70], [10, 20, 30]) == 1.0
    assert auc([10, 20], [30, 40]) == 0.0
    assert auc([50], [50]) == 0.5
    assert auc([], [1]) is None


def test_bands():
    labels = [DEFAULT_BANDS[band(s, DEFAULT_BANDS)][1] for s in (95, 90, 89.9, 70, 50, 10)]
    assert labels == ["ممتاز", "ممتاز", "جيد جداً", "جيد", "مقبول", "ضعيف"]


def test_agreement_summary():
    faculty = [92, 85, 78, 66, 55, 88, 73, 61]
    system = [f + d for f, d in zip(faculty, [3, -2, 4, 1, -5, 2, 6, -1], strict=True)]
    result = agreement(system, faculty)
    assert result.n == 8 and result.bias == pytest.approx(1.0)
    assert result.mae == pytest.approx(3.0)
    assert result.within_5 == pytest.approx(7 / 8) and result.within_10 == 1.0
    assert result.pearson > 0.95 and result.kappa > 0.8
    low, high = result.pearson_ci
    assert low <= result.pearson <= high
    assert sum(map(sum, result.confusion)) == 8
    with pytest.raises(ValueError):
        agreement([1, 2], [1])
