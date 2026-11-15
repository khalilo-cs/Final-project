"""Authenticity score (FR-08.8): how likely the student really wrote this project.

Weights follow the project plan (week 19). A factor without data (no .git folder, no
viva yet) is left out instead of counted as zero, and `coverage` says how much was used.
"""

WEIGHTS = {"code_similarity": 30, "git_history": 20, "style": 15, "viva_gap": 25, "report": 10}
LABELS_AR = {
    "code_similarity": "تشابه الكود مع مشاريع أخرى",
    "git_history": "تاريخ Git",
    "style": "ثبات أسلوب الكتابة",
    "viva_gap": "تطابق المناقشة مع جودة الكود",
    "report": "أصالة التقرير",
}
SIMILARITY_ZERO = 0.6  # 60 % shared code or more scores 0
VIVA_GAP_TOLERANCE = 20


def compute(results) -> dict | None:
    fraud = results.fraud
    if fraud is None:
        return None
    parts: dict[str, float | None] = dict.fromkeys(WEIGHTS)
    flags = []

    # Similarity cannot say who copied whom; submission order can. A match with an earlier
    # project (or one no longer in the system, e.g. a previous year) is the serious case.
    # A later project copying this one suggests the code was shared: flagged, lighter.
    earlier = max(
        (s["similarity"] for s in fraud.similar_projects
         if s.get("document_id") not in results.later_projects),
        default=0.0,
    )  # fmt: skip
    later = max(
        (s["similarity"] for s in fraud.similar_projects
         if s.get("document_id") in results.later_projects),
        default=0.0,
    )  # fmt: skip
    score = 100 * max(0.0, 1 - earlier / SIMILARITY_ZERO)
    if later >= 0.3:
        score = min(score, 100 - later * 50)
    parts["code_similarity"] = round(score, 1)
    if earlier >= 0.3:
        flags.append({"type": "code_similarity", "severity": "High" if earlier >= 0.5 else "Medium",
                      "evidence": f"{round(earlier * 100)}% of the code matches a project "
                      "submitted earlier",
                      "evidence_ar": f"{round(earlier * 100)}% من الكود يطابق مشروعاً سُلِّم "
                      "قبله"})  # fmt: skip
    if later >= 0.3:
        flags.append({"type": "code_shared", "severity": "Medium",
                      "evidence": f"A project submitted later matches {round(later * 100)}% of "
                      "this code: it may have been shared",
                      "evidence_ar": f"مشروع سُلِّم بعده يطابق {round(later * 100)}% من هذا "
                      "الكود: ربما شارك الطالب كوده"})  # fmt: skip

    git = fraud.git_analysis or {}
    if git.get("available"):
        parts["git_history"] = float(git["score"])
        for flag in git.get("flags", []):
            if flag["severity"] != "low":
                flags.append(
                    {
                        "type": f"git_{flag['type']}",
                        "severity": "Medium",
                        "evidence": flag["evidence"],
                        "evidence_ar": flag.get("evidence_ar") or flag["evidence"],
                    }
                )

    style = fraud.style or {}
    if style.get("style_consistency_score") is not None:
        parts["style"] = style["style_consistency_score"]
        for outlier in style.get("outliers", [])[:3]:
            features = ", ".join(outlier["differs"])
            flags.append({"type": "style_outlier", "severity": "Low",
                          "evidence": f"{outlier['file']} is written in a different style "
                          f"({features})",
                          "evidence_ar": f"الملف {outlier['file']} مكتوب بأسلوب مختلف عن باقي "
                          f"المشروع ({features})"})  # fmt: skip

    if results.viva_score is not None and results.code is not None:
        gap = results.code.overall_quality_score - results.viva_score
        parts["viva_gap"] = round(max(0.0, 100 - max(0.0, gap - VIVA_GAP_TOLERANCE) * 2.5), 1)
        if gap > 40:
            quality = results.code.overall_quality_score
            evidence = (
                f"Code quality {quality:.0f} but viva {results.viva_score:.0f}: "
                "the student may not have written it"
            )
            evidence_ar = (
                f"جودة الكود {quality:.0f} لكن المناقشة {results.viva_score:.0f}: "
                "قد لا يكون الطالب كاتب الكود"
            )
            flags.append({"type": "viva_gap", "severity": "High", "evidence": evidence,
                          "evidence_ar": evidence_ar})  # fmt: skip

    if results.report is not None:
        parts["report"] = round(100 - results.report.plagiarism_percentage, 1)

    used = {k: v for k, v in parts.items() if v is not None}
    weight = sum(WEIGHTS[k] for k in used)
    score = round(sum(v * WEIGHTS[k] for k, v in used.items()) / weight, 1) if weight else None
    return {
        "authenticity_score": score,
        "coverage": round(100 * weight / sum(WEIGHTS.values()), 1),
        "components": [
            {"factor": k, "label_ar": LABELS_AR[k], "weight": WEIGHTS[k], "score": parts[k]}
            for k in WEIGHTS
        ],
        "flags": flags,
    }
