import textwrap

from app.analyzers.python_analyzer import PythonAnalyzer
from app.quality.code_smells import detect_smells


def analyze(code: str):
    return PythonAnalyzer().analyze("sample.py", textwrap.dedent(code))


def test_extracts_structure():
    result = analyze(
        """
        import os
        from typing import Any
        from . import sibling

        # a comment

        class Base:
            pass

        class Repo(Base):
            @staticmethod
            def build():
                return Repo()

            async def fetch(self, key, *, limit=10):
                def inner():
                    yield 1
                return inner

        def top(a, b):
            return a + b
        """
    )
    assert result.parse_error is None
    assert result.imports == ["os", "typing", "."]
    assert [c.name for c in result.classes] == ["Base", "Repo"]
    repo = result.classes[1]
    assert repo.bases == ["Base"] and repo.methods == ["build", "fetch"]

    functions = {f.qualified_name: f for f in result.functions}
    assert set(functions) == {"Repo.build", "Repo.fetch", "Repo.fetch.inner", "top"}
    assert functions["Repo.build"].decorators == ["staticmethod"]
    assert functions["Repo.fetch"].is_async
    assert functions["Repo.fetch"].parameters == 2  # self excluded
    assert not functions["Repo.fetch"].is_generator  # the yield belongs to inner
    assert functions["Repo.fetch.inner"].is_generator
    assert functions["top"].parameters == 2
    assert result.comment_lines == 1
    assert result.total_lines == result.code_lines + result.blank_lines + result.comment_lines


def test_complexity():
    result = analyze(
        """
        def simple():
            return 1

        def branchy(items, flag):
            total = 0
            for item in items:              # cyc +1, cog +1
                if item > 0 and flag:       # cyc +2, cog +2 (nested) +1 (and)
                    total += item
                elif item < -10:            # cyc +1, cog +1
                    total -= 1
                else:                       # cog +1
                    while total > 100:      # cyc +1, cog +3
                        total //= 2
            return total
        """
    )
    simple, branchy = result.functions
    assert (simple.cyclomatic_complexity, simple.cognitive_complexity) == (1, 0)
    assert branchy.cyclomatic_complexity == 6
    assert branchy.cognitive_complexity == 9
    assert branchy.max_nesting == 3


def test_syntax_error_is_reported_not_raised():
    result = analyze("def broken(:\n    pass\n")
    assert result.parse_error.startswith("SyntaxError")
    assert result.total_lines == 2


def test_code_smells():
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    nested = (
        "def deep(a):\n"
        + "".join("    " * (depth + 1) + "if a:\n" for depth in range(5))
        + "    " * 6
        + "return a\n"
    )
    methods = "\n".join(f"    def m{i}(self): pass" for i in range(21))
    code = (
        f"def long_one():\n{body}\n\n"
        "def many(a, b, c, d, e, f):\n    return a\n\n"
        f"{nested}\n"
        f"class Everything:\n{methods}\n"
    )
    smells = {(s.type, s.symbol) for s in detect_smells(PythonAnalyzer().analyze("s.py", code))}
    assert smells == {
        ("long_method", "long_one"),
        ("too_many_parameters", "many"),
        ("deep_nesting", "deep"),
        ("god_class", "Everything"),
    }
