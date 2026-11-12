#!/usr/bin/env python3
"""تحليل التقييم البشري: متوسط كل معيار لكل مزود، واتفاق المقيّمَين (كابا كوهين الموزونة تربيعيًا).

الاستخدام: python3 eval/score_ratings.py مقيم١.csv مقيم٢.csv [--key eval/results/rating_key.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

CRITERIA = ["الدقة (١-٥)", "البساطة (١-٥)", "سلامة العربية (١-٥)"]
EASTERN = str.maketrans("١٢٣٤٥", "12345")


def read(path: str) -> dict[int, dict[str, int]]:
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            scores = {c: int(str(row[c]).strip().translate(EASTERN)) for c in CRITERIA if str(row.get(c, "")).strip()}
            if len(scores) == len(CRITERIA):
                out[int(row["المعرف"])] = scores
    return out


def weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float:
    """كابا كوهين الموزونة تربيعيًا لتقديرات ترتيبية من ١ إلى k."""
    n = len(a)
    if n == 0:
        return float("nan")
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    ra = [sum(obs[i]) for i in range(k)]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * ra[i] * rb[j] / n for i in range(k) for j in range(k))
    return 1 - num / den if den else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rater1")
    ap.add_argument("rater2")
    ap.add_argument("--key", default=str(Path(__file__).parent / "results" / "rating_key.json"))
    args = ap.parse_args()
    key = {int(k): v for k, v in json.loads(Path(args.key).read_text(encoding="utf-8")).items()}
    r1, r2 = read(args.rater1), read(args.rater2)
    common = sorted(set(r1) & set(r2))
    print(f"عناصر مقيَّمة من الاثنين: {len(common)}\n")
    print("| المزود | " + " | ".join(CRITERIA) + " |")
    print("|---|" + "---:|" * len(CRITERIA))
    by = defaultdict(lambda: defaultdict(list))
    for i in common:
        for c in CRITERIA:
            by[key[i]][c].append((r1[i][c] + r2[i][c]) / 2)
    for prov, crit in sorted(by.items()):
        print(f"| {prov} | " + " | ".join(f"{statistics.mean(crit[c]):.2f}" for c in CRITERIA) + " |")
    print("\nاتفاق المقيّمَين (κ الموزونة):")
    for c in CRITERIA:
        print(f"- {c}: {weighted_kappa([r1[i][c] for i in common], [r2[i][c] for i in common]):.2f}")


if __name__ == "__main__":
    main()
