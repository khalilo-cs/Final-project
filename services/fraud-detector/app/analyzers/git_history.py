"""What the Git history says about how the project was written (FR-08.5)."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings

_PENALTY = {"high": 40, "medium": 20, "low": 5}
BULK_MIN_FILES = 5


def _find_repository(root: Path) -> Path | None:
    for candidate in [root, *[p for p in root.iterdir() if p.is_dir()]]:
        if (candidate / ".git" / "HEAD").is_file():
            return candidate
    return None


def analyze_git(root: Path) -> dict | None:
    """None when the upload has no .git folder (history not provided)."""
    from dulwich.errors import NotGitRepository
    from dulwich.repo import Repo

    location = _find_repository(root)
    if location is None:
        return None
    try:
        repo = Repo(str(location))
        walker = repo.get_walker(max_entries=get_settings().max_commits)
        commits = []
        created: set[str] = set()
        for entry in walker:
            commit = entry.commit
            changed, added = set(), set()
            for change in entry.changes():
                # merges return lists of changes per parent
                for item in change if isinstance(change, list) else [change]:
                    for side in (item.old, item.new):
                        if side is not None and side.path:
                            changed.add(side.path.decode(errors="replace"))
                    if item.type == "add" and item.new is not None and item.new.path:
                        added.add(item.new.path.decode(errors="replace"))
            created |= added
            commits.append(
                {
                    "author": commit.author.decode(errors="replace"),
                    "time": datetime.fromtimestamp(commit.author_time, UTC),
                    "files": len(changed),
                    "added": len(added),
                    "added_paths": added,
                    "changed_paths": changed,
                    "message": commit.message.decode(errors="replace").strip()[:120],
                }
            )
    except (NotGitRepository, KeyError, ValueError, OSError) as exc:
        return {"available": False, "error": f"Unreadable Git history ({type(exc).__name__})"}
    if not commits:
        return {"available": False, "error": "The repository has no commits"}

    commits.sort(key=lambda c: c["time"])
    first, last = commits[0]["time"], commits[-1]["time"]
    span_hours = (last - first).total_seconds() / 3600
    authors = Counter(c["author"] for c in commits)
    per_day = Counter(c["time"].date() for c in commits)
    biggest = max(commits, key=lambda c: c["added"])
    flags = []

    def flag(kind, severity, evidence, evidence_ar):
        flags.append(
            {"type": kind, "severity": severity, "evidence": evidence, "evidence_ar": evidence_ar}
        )

    if len(commits) == 1:
        flag("single_commit", "high", "The whole project was committed at once",
             "رُفع المشروع كله في commit واحد")  # fmt: skip
    elif len(commits) < 5:
        flag("few_commits", "medium", f"Only {len(commits)} commits",
             f"عدد الـ commits قليل جداً: {len(commits)}")  # fmt: skip
    if len(commits) > 1 and span_hours < 48:
        flag("short_span", "medium", f"All commits within {span_hours:.1f} hours",
             f"كل العمل خلال {span_hours:.1f} ساعة فقط")  # fmt: skip
    # A dump: one commit creates most of the project and those files are hardly worked on
    # afterwards. A first commit that later gets developed is just how projects start.
    if (
        len(commits) > 1
        and len(created) >= BULK_MIN_FILES
        and biggest["added"] / len(created) >= 0.7
    ):
        later = set().union(*(c["changed_paths"] for c in commits if c["time"] > biggest["time"]))
        evolved = len(biggest["added_paths"] & later) / biggest["added"]
        if evolved < 0.5:
            evidence = (
                f"One commit added {biggest['added']} of {len(created)} files, and "
                f"{round(evolved * 100)}% of them were changed afterwards: "
                f"“{biggest['message']}”"
            )
            evidence_ar = (
                f"commit واحد أضاف {biggest['added']} من {len(created)} ملفات، ولم يُعدَّل "
                f"منها بعده إلا {round(evolved * 100)}%"
            )
            flag("bulk_commit", "medium", evidence, evidence_ar)
    if len(authors) > 1:
        flag("multiple_authors", "low", f"{len(authors)} different authors",
             f"{len(authors)} مؤلفين مختلفين في تاريخ Git")  # fmt: skip

    score = max(0, 100 - sum(_PENALTY[f["severity"]] for f in flags))
    return {
        "available": True,
        "total_commits": len(commits),
        "authors": [{"author": a, "commits": n} for a, n in authors.most_common()],
        "first_commit": first.isoformat(),
        "last_commit": last.isoformat(),
        "span_days": round(span_hours / 24, 1),
        "active_days": len(per_day),
        "max_commits_per_day": max(per_day.values()),
        "flags": flags,
        "score": score,
        "timeline": [{"date": day.isoformat(), "commits": n} for day, n in sorted(per_day.items())][
            -60:
        ],
    }
