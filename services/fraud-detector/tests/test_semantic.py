import httpx
import numpy as np
import pytest

from app.analyzers import embeddings
from app.analyzers.units import file_units
from app.config import get_settings
from tests.conftest import analyze, zip_files
from tests.samples import (
    DIFFERENT_JAVA,
    FEES_CSHARP,
    FEES_ORIGINAL,
    FEES_REWRITTEN,
    LIBRARY,
    LIBRARY_DISGUISED,
)  # fmt: skip


def test_rewritten_function_is_found_although_tokens_differ(client):
    analyze(client, "original", zip_files(FEES_ORIGINAL))
    result = analyze(client, "suspect", zip_files(FEES_REWRITTEN))
    # Token fingerprints only catch the untouched lines; the structure gives it away.
    token = result["similarity"]["max_similarity"]
    semantic = result["semantic"]
    (source,) = semantic["sources"]
    assert source["document_id"] == "original" and source["similarity"] > 0.9 > token
    (match,) = source["functions"]
    assert (match["name"], match["other_name"]) == ("computePenalty", "lateFees")
    assert match["other_file"] == "src/Library.java" and match["other_lines"] == [3, 16]
    # Only the untouched block matched token by token: most of the function was rewritten.
    assert match["token_coverage"] < 0.7 and match["methods"] == ["structural"]


def test_translation_to_a_similar_language(client):
    analyze(client, "java", zip_files(FEES_ORIGINAL))
    (source,) = analyze(client, "csharp", zip_files(FEES_CSHARP))["semantic"]["sources"]
    assert source["functions"][0]["similarity"] >= 0.85


def test_different_code_of_the_same_size_does_not_match(client):
    analyze(client, "library", zip_files(FEES_ORIGINAL))
    result = analyze(client, "shop", zip_files(DIFFERENT_JAVA))["semantic"]
    assert result["sources"] == [] and result["functions_compared"] == 2


def test_plain_copies_are_not_reported_as_rewritten(client):
    analyze(client, "original", zip_files(LIBRARY))
    result = analyze(client, "copy", zip_files(LIBRARY_DISGUISED))
    assert result["similarity"]["sources"]
    for source in result["semantic"]["sources"]:
        same_files = [f for f in source["functions"] if not f["rewritten"]]
        assert same_files, "functions also caught by tokens are marked as such"


def test_common_patterns_are_ignored(client):
    for i in range(6):
        analyze(
            client, f"p{i}", zip_files({f"p{i}/Library.java": FEES_ORIGINAL["src/Library.java"]})
        )
    result = analyze(client, "new", zip_files(FEES_REWRITTEN))["semantic"]
    assert result["ignored_common_patterns"] == 1 and result["sources"] == []


def test_forget_removes_functions(client):
    from tests.conftest import token

    analyze(client, "original", zip_files(FEES_ORIGINAL))
    assert client.delete("/api/v1/documents/original", headers=token()).status_code == 204
    assert analyze(client, "suspect", zip_files(FEES_REWRITTEN))["semantic"]["sources"] == []


@pytest.mark.parametrize(
    ("path", "source", "names"),
    [
        ("a.py", "def f(x):\n    for i in x:\n        if i: print(i)\n    return x\n", ["f"]),
        (
            "a.js",
            "const g = (a) => { for (const x of a) { if (x) console.log(x); } return a; };",
            ["g"],
        ),
        (
            "a.ts",
            "class C { m(a: number[]): number { let s = 0; for (const x of a) s += x; return s; } }",
            ["m"],
        ),
        (
            "a.cpp",
            "int Shape::area(int w) { for (int i=0;i<w;i++) { if (i) w--; } return w; }",
            ["Shape::area"],
        ),
        (
            "a.php",
            "<?php function h($a) { foreach ($a as $x) { if ($x) echo strlen($x); } return $a; }",
            ["h"],
        ),
    ],
)
def test_functions_in_every_language(path, source, names):
    assert [u.name for u in file_units(path, source, 3)] == names


def test_embedding_model_adds_a_second_opinion(client, monkeypatch):
    calls = []

    def server(request: httpx.Request):
        body = request.read().decode()
        calls.append(body)
        import json

        texts = json.loads(body)["input"]
        # A fake "model": the same vector for any code about late fees / penalties.
        vectors = [[1.0, 0.0, 0.0] if "Late" in t or "Overdue" in t else [0.0, 1.0, 0.0]
                   for t in texts]  # fmt: skip
        return httpx.Response(200, json={"data": [{"index": i, "embedding": v}
                                                  for i, v in enumerate(vectors)]})  # fmt: skip

    monkeypatch.setattr(get_settings(), "embedding_url", "http://embed:11434")
    monkeypatch.setattr(embeddings, "transport", httpx.MockTransport(server))
    analyze(client, "original", zip_files(FEES_ORIGINAL))
    result = analyze(client, "suspect", zip_files(FEES_REWRITTEN))["semantic"]
    assert result["methods"] == ["embedding", "structural"]
    assert result["sources"][0]["functions"][0]["methods"] == ["embedding", "structural"]
    assert '"model":"nomic-embed-text"' in calls[0]


def test_embedding_server_down_keeps_the_structural_result(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_url", "http://embed:11434")
    monkeypatch.setattr(embeddings, "transport", httpx.MockTransport(lambda r: httpx.Response(503)))
    analyze(client, "original", zip_files(FEES_ORIGINAL))
    result = analyze(client, "suspect", zip_files(FEES_REWRITTEN))["semantic"]
    assert result["embedding_error"] and result["methods"] == ["structural"]
    assert result["sources"]


def test_vectors_are_normalized():
    from app.analyzers.vectors import from_bytes, structural_vector, to_bytes

    (unit,) = file_units("A.java", FEES_ORIGINAL["src/Library.java"], 1)
    vector = structural_vector(unit.shape)
    assert abs(float(np.linalg.norm(vector)) - 1) < 1e-5
    assert np.allclose(from_bytes(to_bytes(vector)), vector, atol=1e-3)
