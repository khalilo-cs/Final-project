from pathlib import Path

from app.analyzers.style import analyze_style
from tests.conftest import analyze, git, token, zip_dir, zip_files
from tests.samples import LIBRARY, LIBRARY_DISGUISED, UNRELATED


def test_renamed_copy_is_detected_with_matching_files(client):
    assert analyze(client, "original", zip_files(LIBRARY))["similarity"]["sources"] == []
    result = analyze(client, "copy", zip_files(LIBRARY_DISGUISED))["similarity"]
    (source,) = result["sources"]
    assert source["document_id"] == "original"
    assert source["similarity"] >= 0.8
    pairs = {(m["file"], m["other_file"]) for m in source["matched_files"]}
    assert ("src/borrowing.py", "library/loans.py") in pairs
    assert ("src/finder.py", "library/search.py") in pairs


def test_unrelated_projects_do_not_match(client):
    analyze(client, "library", zip_files(LIBRARY))
    result = analyze(client, "shop", zip_files(UNRELATED))["similarity"]
    assert result["sources"] == [] and result["max_similarity"] == 0.0


def test_same_students_resubmission_is_excluded(client):
    analyze(client, "v1", zip_files(LIBRARY))
    assert analyze(client, "v2", zip_files(LIBRARY), exclude=["v1"])["similarity"]["sources"] == []


def test_shared_framework_template_is_not_plagiarism(client):
    template = LIBRARY_DISGUISED["src/finder.py"]  # everyone starts from the same scaffold
    for i in range(6):
        analyze(
            client, f"p{i}", zip_files({"scaffold.py": template, **(LIBRARY if i == 0 else {})})
        )
    result = analyze(client, "new", zip_files({"scaffold.py": template, **UNRELATED}))["similarity"]
    assert result["ignored_boilerplate"] > 0
    assert result["sources"] == []


def test_reanalysis_replaces_own_entry_and_forget(client):
    analyze(client, "a", zip_files(LIBRARY))
    assert analyze(client, "a", zip_files(LIBRARY))["similarity"]["sources"] == []
    analyze(client, "b", zip_files(LIBRARY), index=False)
    assert client.delete("/api/v1/documents/a", headers=token()).status_code == 204
    assert analyze(client, "c", zip_files(LIBRARY))["similarity"]["sources"] == []


def test_git_single_commit_is_flagged(client, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in LIBRARY.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
    git(repo, "init")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "final project", date="2026-05-30T23:10:00")
    result = analyze(client, "one", zip_dir(repo))["git"]
    assert result["available"] and result["total_commits"] == 1
    assert [f["type"] for f in result["flags"]] == ["single_commit"]
    assert result["score"] == 60


def test_git_natural_history_is_clean(client, tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "library").mkdir(parents=True)
    git(repo, "init")
    content = LIBRARY["library/loans.py"].splitlines(keepends=True)
    for day in range(1, 8):
        part = content[: len(content) * day // 7]
        (repo / "library" / "loans.py").write_text("".join(part))
        (repo / "library" / f"notes{day}.md").write_text(f"day {day}")
        git(repo, "add", ".")
        git(repo, "commit", "-m", f"work day {day}", date=f"2026-04-{day * 2:02d}T18:00:00")
    result = analyze(client, "natural", zip_dir(repo))["git"]
    assert result["total_commits"] == 7 and result["span_days"] == 12.0
    assert result["flags"] == [] and result["score"] == 100
    assert result["authors"] == [{"author": "Sara <sara@example.com>", "commits": 7}]


def test_no_git_folder_means_no_history(client):
    assert analyze(client, "plain", zip_files(LIBRARY))["git"] is None


def test_style_outlier_file(tmp_path: Path):
    snake = "\n".join(
        f"def load_item_{i}(item_id, item_store):\n    found_item = item_store.get(item_id)\n"
        f"    return found_item\n" for i in range(8)
    )  # fmt: skip
    camel = "\n".join(
        f"# fetch the record\ndef fetchRecord{i}(recordId, recordStore):\n  # look it up\n"
        f"  foundRecord = recordStore.get(recordId)\n  # done\n  return foundRecord\n"
        for i in range(8)
    )  # fmt: skip
    for i in range(4):
        (tmp_path / f"module{i}.py").write_text(snake)
    (tmp_path / "copied.py").write_text(camel)
    result = analyze_style(tmp_path)
    assert result["project_style"]["python"]["naming"] == "snake"
    (outlier,) = result["outliers"]
    assert outlier["file"] == "copied.py"
    assert {"naming", "indent"} <= set(outlier["differs"])
    assert 0 < result["style_consistency_score"] < 100


def test_service_token_required(client):
    response = client.post(
        "/api/v1/fraud/analyze",
        files={"file": ("c.zip", zip_files(LIBRARY))},
        data={"document_id": "x"},
        headers=token("admin"),
    )
    assert response.status_code == 403


def test_editing_every_file_each_commit_is_not_a_dump(client, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    for day in range(1, 7):
        for i in range(6):
            (repo / f"m{i}.py").write_text(f"# version {day}\nx = {day}\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", f"day {day}", date=f"2026-04-{day * 3:02d}T18:00:00")
    # The first commit creates all 6 files, as every project starts, and they are then
    # developed over two weeks: a normal history, nothing to flag.
    assert analyze(client, "edits", zip_dir(repo))["git"]["flags"] == []


def test_dumping_a_finished_project_is_flagged(client, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / "README.md").write_text("start")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "init", date="2026-04-01T10:00:00")
    for i in range(8):
        (repo / f"module{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "add project", date="2026-05-20T23:00:00")
    flags = {f["type"]: f for f in analyze(client, "dump", zip_dir(repo))["git"]["flags"]}
    assert "8 of 9 files" in flags["bulk_commit"]["evidence"]
