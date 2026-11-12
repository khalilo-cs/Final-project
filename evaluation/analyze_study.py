#!/usr/bin/env python3
"""تحليل دراسة المستخدمين (بلا مكتبات خارجية).

الأوامر:
  assign N            جدول توزيع عشوائي متوازن لـ N مشاركًا على المجموعتين أ/ب
  analyze FILE.csv    التحليل الكامل (انظر data_template.csv لصيغة الملف)
  selftest            التحقق من صحة الحسابات على قيم معروفة
"""
from __future__ import annotations

import csv
import math
import random
import statistics
import sys

SUS_COLS = [f"sus{i}" for i in range(1, 11)]
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def sus_score(answers: list[int]) -> float:
    """درجة SUS (٠–١٠٠) وفق Brooke: العبارات الفردية (ر-١)، والزوجية (٥-ر)، والمجموع × ٢٫٥."""
    if len(answers) != 10 or not all(1 <= a <= 5 for a in answers):
        raise ValueError("SUS يحتاج عشر إجابات من ١ إلى ٥")
    total = sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers))
    return total * 2.5


def welch_t(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """اختبار t لـ Welch: (t، درجات الحرية، p ثنائي الطرف)."""
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se2 = va / len(a) + vb / len(b)
    if se2 == 0:
        return 0.0, float(len(a) + len(b) - 2), 1.0
    t = (ma - mb) / math.sqrt(se2)
    df = se2**2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
    return t, df, 2 * student_t_sf(abs(t), df)


def student_t_sf(t: float, df: float) -> float:
    """دالة البقاء لتوزيع t عبر دالة بيتا غير المكتملة المنتظمة."""
    x = df / (df + t * t)
    return 0.5 * betainc(df / 2, 0.5, x)


def betainc(a: float, b: float, x: float) -> float:
    """دالة بيتا غير المكتملة المنتظمة I_x(a,b) بالكسر المستمر (Numerical Recipes)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1 - math.exp(lbeta) * _betacf(b, a, 1 - x) / b


def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(1 + aa / c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return h


def mann_whitney(a: list[float], b: list[float]) -> tuple[float, float]:
    """اختبار Mann–Whitney U بتقريب طبيعي وتصحيح الروابط: (U، p ثنائي الطرف)."""
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = [0.0] * len(combined)
    i = 0
    ties = 0.0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        n_t = j - i + 1
        ties += n_t**3 - n_t
        i = j + 1
    na, nb = len(a), len(b)
    ra = sum(r for r, (_, g) in zip(ranks, combined) if g == 0)
    u = ra - na * (na + 1) / 2
    n = na + nb
    sigma = math.sqrt(na * nb / 12 * ((n + 1) - ties / (n * (n - 1))))
    if sigma == 0:
        return u, 1.0
    z = (abs(u - na * nb / 2) - 0.5) / sigma
    return u, math.erfc(max(z, 0) / math.sqrt(2))


def cohens_d(a: list[float], b: list[float]) -> float:
    na, nb = len(a), len(b)
    pooled = math.sqrt(((na - 1) * statistics.variance(a) + (nb - 1) * statistics.variance(b)) / (na + nb - 2))
    return (statistics.mean(a) - statistics.mean(b)) / pooled if pooled else 0.0


def num(v: str) -> float:
    return float(str(v).strip().translate(DIGITS))


def analyze(path: str) -> None:
    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("المشارك")]
    if not rows:
        sys.exit("لا بيانات في الملف")
    for r in rows:
        r["sus"] = sus_score([int(num(r[c])) for c in SUS_COLS])
        r["تحسن"] = num(r["بعدي"]) - num(r["قبلي"])
    groups = {g: [r for r in rows if r["المجموعة"].strip() == g] for g in ("أ", "ب")}
    print(f"المشاركون: {len(rows)} (أ: {len(groups['أ'])}، ب: {len(groups['ب'])})\n")
    all_sus = [r["sus"] for r in rows]
    print(f"SUS للمنصة: المتوسط {statistics.mean(all_sus):.1f}، الوسيط {statistics.median(all_sus):.1f} "
          f"— {'≥' if statistics.mean(all_sus) >= 70 else '<'} ٧٠ (ف٣)\n")
    measures = [
        ("أخطاء_مصلحة", "الأخطاء المُصلَحة (ف١)", True),
        ("زمن_الإصلاح_ث", "زمن الإصلاح بالثواني (ف١)", False),
        ("تحسن", "تحسّن الفهم: بعدي − قبلي (ف٢)", True),
        ("sus", "SUS", True),
    ]
    print("| المقياس | متوسط أ | متوسط ب | t (Welch) | p | U | p (Mann–Whitney) | d |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for key, label, _higher_better in measures:
        a = [num(r[key]) if not isinstance(r[key], float) else r[key] for r in groups["أ"]]
        b = [num(r[key]) if not isinstance(r[key], float) else r[key] for r in groups["ب"]]
        if len(a) < 2 or len(b) < 2:
            print(f"| {label} | — | — | تحتاج مشاركَين على الأقل في كل مجموعة |")
            continue
        t, _, p = welch_t(b, a)
        u, pu = mann_whitney(b, a)
        print(f"| {label} | {statistics.mean(a):.2f} | {statistics.mean(b):.2f} | {t:.2f} | {p:.3f} | "
              f"{u:.1f} | {pu:.3f} | {cohens_d(b, a):.2f} |")
    print("\nملاحظة: d موجبة تعني قيمة أعلى في المجموعة ب. مستوى الدلالة المعتمد ٠٫٠٥.")


def assign(n: int, seed: int = 2026) -> None:
    groups = ["أ", "ب"] * (n // 2) + (["أ"] if n % 2 else [])
    random.Random(seed).shuffle(groups)
    print("المشارك,المجموعة")
    for i, g in enumerate(groups, 1):
        print(f"م{i:02d},{g}")


def selftest() -> None:
    assert sus_score([3] * 10) == 50.0
    assert sus_score([5, 1] * 5) == 100.0
    assert sus_score([1, 5] * 5) == 0.0
    assert sus_score([4, 2, 4, 2, 4, 2, 4, 2, 4, 2]) == 75.0
    # قيمة مرجعية لدالة البقاء: t=2.0 بدرجات حرية ١٠ ⇒ p ثنائي ≈ 0.0734
    assert abs(2 * student_t_sf(2.0, 10) - 0.07339) < 1e-4
    # t=2.228 بدرجات حرية ١٠ هو الحد الحرج عند ٠٫٠٥
    assert abs(2 * student_t_sf(2.228, 10) - 0.05) < 1e-3
    t, df, p = welch_t([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert t == 0 and abs(p - 1) < 1e-9
    a, b = [10, 11, 12, 13, 14], [1, 2, 3, 4, 5]
    t, df, p = welch_t(a, b)
    assert abs(t - 9.0) < 1e-9 and abs(df - 8) < 1e-9 and p < 0.001
    u, pu = mann_whitney(a, b)
    assert u == 25 and pu < 0.02
    assert abs(cohens_d(a, b) - 9 / math.sqrt(2.5)) < 1e-9
    print("✔ selftest: SUS، t لـ Welch وقيمها المرجعية، Mann–Whitney، Cohen's d")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "analyze":
        analyze(sys.argv[2])
    elif cmd == "assign":
        assign(int(sys.argv[2]))
    else:
        selftest()
