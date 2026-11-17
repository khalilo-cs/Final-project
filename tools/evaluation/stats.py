"""Agreement statistics for the evaluation chapter (pure Python, no dependencies).

Small samples are expected (a few dozen projects), so every headline number comes
with a bootstrap 95% confidence interval.
"""

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Default grade bands (lower bound inclusive). Check them against the university's
# official regulations and pass --bands to change them.
DEFAULT_BANDS: list[tuple[float, str]] = [
    (90, "ممتاز"),
    (80, "جيد جداً"),
    (65, "جيد"),
    (50, "مقبول"),
    (0, "ضعيف"),
]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (n - 1)."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None  # one side is constant: correlation is undefined
    return sxy / math.sqrt(sxx * syy)


def ranks(values: Sequence[float]) -> list[float]:
    """Average ranks (1-based); ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return result


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    return pearson(ranks(x), ranks(y))


def band(score: float, bands: list[tuple[float, str]]) -> int:
    """Index of the band (0 = highest)."""
    for index, (lower, _) in enumerate(bands):
        if score >= lower:
            return index
    return len(bands) - 1


def weighted_kappa(a: Sequence[int], b: Sequence[int], categories: int) -> float | None:
    """Cohen's kappa with quadratic weights: disagreeing by two bands costs four times
    as much as by one."""
    n = len(a)
    if n == 0 or categories < 2:
        return None
    observed = [[0.0] * categories for _ in range(categories)]
    for i, j in zip(a, b, strict=True):
        observed[i][j] += 1
    row = [sum(r) for r in observed]
    col = [sum(observed[i][j] for i in range(categories)) for j in range(categories)]
    weight = [[((i - j) ** 2) / ((categories - 1) ** 2) for j in range(categories)]
              for i in range(categories)]  # fmt: skip
    num = sum(weight[i][j] * observed[i][j] for i in range(categories) for j in range(categories))
    den = sum(weight[i][j] * row[i] * col[j] / n
              for i in range(categories) for j in range(categories))  # fmt: skip
    if den == 0:
        return None  # everyone in one band: agreement beyond chance cannot be measured
    return 1 - num / den


def auc(positives: Sequence[float], negatives: Sequence[float]) -> float | None:
    """Probability that a random positive scores above a random negative (ties = 1/2).
    Equals the Mann-Whitney U statistic divided by n1 * n2."""
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for q in negatives:
            wins += 1.0 if p > q else 0.5 if p == q else 0.0
    return wins / (len(positives) * len(negatives))


def bootstrap(
    statistic: Callable[[list[int]], float | None], n: int, rounds: int = 2000, seed: int = 7
) -> tuple[float, float] | None:
    """95% percentile interval of `statistic` over resamples of the indices 0..n-1."""
    if n < 3:
        return None
    rng = random.Random(seed)  # noqa: S311 (statistics, not security: a fixed seed is the point)
    values = []
    for _ in range(rounds):
        sample = [rng.randrange(n) for _ in range(n)]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if len(values) < rounds // 2:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


@dataclass
class Agreement:
    n: int
    mean_system: float
    mean_faculty: float
    bias: float  # mean(system - faculty): positive = the system grades higher
    mae: float
    rmse: float
    limits: tuple[float, float]  # Bland-Altman 95% limits of agreement
    within_5: float
    within_10: float
    pearson: float | None
    spearman: float | None
    kappa: float | None
    exact_band: float
    pearson_ci: tuple[float, float] | None
    mae_ci: tuple[float, float] | None
    confusion: list[list[int]]  # [faculty band][system band]


def agreement(system: Sequence[float], faculty: Sequence[float],
              bands: list[tuple[float, str]] = DEFAULT_BANDS) -> Agreement:  # fmt: skip
    if len(system) != len(faculty) or not system:
        raise ValueError("need the same, non-zero number of system and faculty grades")
    n = len(system)
    diff = [s - f for s, f in zip(system, faculty, strict=True)]
    sd = stdev(diff)
    sb = [band(s, bands) for s in system]
    fb = [band(f, bands) for f in faculty]
    confusion = [[0] * len(bands) for _ in bands]
    for i, j in zip(fb, sb, strict=True):
        confusion[i][j] += 1

    def pearson_of(idx):
        return pearson([system[i] for i in idx], [faculty[i] for i in idx])

    def mae_of(idx):
        return mean([abs(diff[i]) for i in idx])

    return Agreement(
        n=n,
        mean_system=mean(system),
        mean_faculty=mean(faculty),
        bias=mean(diff),
        mae=mean([abs(d) for d in diff]),
        rmse=math.sqrt(mean([d * d for d in diff])),
        limits=(mean(diff) - 1.96 * sd, mean(diff) + 1.96 * sd),
        within_5=sum(abs(d) <= 5 for d in diff) / n,
        within_10=sum(abs(d) <= 10 for d in diff) / n,
        pearson=pearson(system, faculty),
        spearman=spearman(system, faculty),
        kappa=weighted_kappa(fb, sb, len(bands)),
        exact_band=sum(a == b for a, b in zip(fb, sb, strict=True)) / n,
        pearson_ci=bootstrap(pearson_of, n),
        mae_ci=bootstrap(mae_of, n),
        confusion=confusion,
    )
