import random
from pathlib import Path

from app.challenge.mutations import candidates, make_challenges, mask, normalize
from app.services.project_analyzer import analyze_files
from tests.test_api import auth, client, make_zip

LOANS = '''class LoanService:
    def late_fee(self, loan, today):
        """Fee for a late book: 50 per day, at most 1000."""
        days = (today - loan.due).days
        if days <= 0:
            return 0
        fee = days * 50  # per day < limit
        if fee > 1000 and not loan.waived:
            fee = 1000
        message = "late: " + str(days)
        self.notify(loan.student, message)
        return fee
'''


def test_strings_and_comments_are_never_mutated():
    lines = LOANS.splitlines()[1:]
    found = candidates(lines, 2, body_from=1)
    kinds = {(m.line, m.kind) for m in found}
    assert (5, "boundary") in kinds and (8, "boundary") in kinds and (8, "logic") in kinds
    assert (5, "constant") in kinds  # days <= 0  ->  days <= 1
    # Line 7's "<" is in a comment, line 10's "+" joins strings, line 3 is a docstring.
    assert not any(m.line in (3, 7, 10) for m in found)
    assert all(m.original_line != m.mutated_line for m in found)
    assert mask('x = "a < b"  # c > d') == "x =" + " " * 17


def test_each_mutation_changes_exactly_one_token():
    for mutation in candidates(LOANS.splitlines()[1:], 2, body_from=1):
        before, after = mutation.original_line.split(), mutation.mutated_line.split()
        assert len(before) == len(after)
        assert sum(a != b for a, b in zip(before, after, strict=True)) == 1


def test_challenges_come_from_the_students_own_functions(tmp_path: Path):
    (tmp_path / "loans.py").write_text(LOANS)
    (tmp_path / "tiny.py").write_text("def f(a, b):\n    return a < b\n")
    (tmp_path / "test_loans.py").write_text(LOANS)
    challenges = make_challenges(tmp_path, analyze_files(tmp_path), 3, random.Random(7))
    (challenge,) = challenges  # tiny functions and tests are not used
    assert (challenge.file, challenge.function) == ("loans.py", "LoanService.late_fee")
    shown = challenge.code.splitlines()
    original = LOANS.splitlines()[1:]
    changed = [i for i, (a, b) in enumerate(zip(shown, original, strict=True)) if a != b]
    assert changed == [challenge.mutation.line - challenge.start_line]
    assert normalize(challenge.mutation.original_line) == normalize(original[changed[0]])
    again = make_challenges(tmp_path, analyze_files(tmp_path), 3, random.Random(7))
    assert again[0].mutation == challenge.mutation  # reproducible with a seed


def test_api_is_for_services_only():
    archive = make_zip({"loans.py": LOANS, "Shop.java": """
class Shop {
  double total(java.util.List<Item> items, boolean member) {
    double sum = 0;
    for (Item item : items) {
      if (item.stock > 0 && item.price >= 1) {
        sum += item.price;
      }
    }
    if (member) { sum = sum - 5; }
    return sum;
  }
}
"""})  # fmt: skip
    files = {"file": ("code.zip", archive, "application/zip")}
    assert (
        client.post("/api/v1/challenge/mutations", files=files, headers=auth()).status_code == 403
    )
    response = client.post(
        "/api/v1/challenge/mutations", files=files, data={"count": 2, "seed": 1},
        headers=auth(role="service"),
    )  # fmt: skip
    assert response.status_code == 200
    challenges = response.json()["challenges"]
    assert {c["language"] for c in challenges} == {"python", "java"}
    for challenge in challenges:
        assert challenge["mutation"]["mutated_line"] in challenge["code"]
        assert challenge["mutation"]["description_ar"]
