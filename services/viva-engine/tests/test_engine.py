from app.knowledge.bm25 import BM25Index, jaccard
from app.providers.base import Question
from app.providers.template import TemplateProvider
from tests.conftest import CONTEXT

engine = TemplateProvider()


def question(**overrides):
    base = dict(key="k", type="technical", level=2, text="اشرح الدالة calculate_fine",
                expected_points=["calculate_fine", "days_late", "get_rate"])  # fmt: skip
    return Question(**{**base, **overrides})


def test_questions_come_from_the_projects_own_code():
    questions = engine.generate_questions(CONTEXT, "ar", 8, [], [])
    texts = " ".join(q.text for q in questions)
    assert "calculate_fine" in texts and "app/loans.py" in texts
    assert "SQL Injection" in texts and "app/db.py" in texts
    assert "loans" in texts and "books" in texts
    assert {q.type for q in questions} == {
        "understanding",
        "technical",
        "challenge",
        "verification",
    }
    assert {q.level for q in questions} == {1, 2, 3, 4}
    refactor = next(q for q in questions if q.key == "challenge:refactor")
    assert refactor.related_lines == "10-40" and refactor.code.startswith("def calculate_fine")
    english = engine.generate_questions(CONTEXT, "en", 8, [], [])
    assert english[0].text.startswith("What problem")


def test_good_answer_scores_high():
    answer = (
        "الدالة calculate_fine تحسب غرامة التأخير: تستدعي days_late لمعرفة عدد أيام التأخير "
        "ثم get_rate لجلب سعر اليوم من جدول settings، وتضرب الناتج وتُرجع المبلغ كرقم عشري. "
        "تُستدعى من LoanService.return_book عند إرجاع الكتاب."
    )
    result = engine.evaluate(question(), answer, "ar", [])
    assert result.verdict == "correct" and result.score >= 70


def test_vague_partial_and_evasive_answers():
    vague = engine.evaluate(
        question(), "هي تقريبا تحسب شيء ما بشكل عام للمستخدم في النظام وكذا", "ar", []
    )
    assert vague.score < 40
    partial = engine.evaluate(
        question(),
        "تحسب الغرامة باستخدام days_late لحساب الأيام ثم تضرب في رقم ثابت وترجع النتيجة للواجهة",
        "ar",
        [],
    )
    assert 40 <= partial.score < 70
    assert engine.evaluate(question(), "لا أعرف، زميلي كتبها", "ar", []).verdict == "evasive"
    assert engine.evaluate(question(), "I don't know", "en", []).verdict == "evasive"
    assert engine.evaluate(question(), "اشرح الدالة calculate_fine", "ar", []).verdict == "evasive"


def test_bm25_and_similarity():
    index = BM25Index(
        [("1", "Prepared statements prevent SQL injection"), ("2", "Flask routing basics")]
    )
    assert index.search("how to prevent sql injection")[0][0] == "1"
    assert index.search("nothing matches here") == []
    assert jaccard("الدالة تحسب الغرامة", "الدالة تحسب الغرامه") == 1.0
