"""Measure the plan's performance targets (NFR-01) on a running stack.

    python tools/local-stack/perf.py [--base http://localhost:8080] [--concurrent 10]

1. A real ~10,000-line project (taken from this repository's own services) is
   analyzed end to end: target under 5 minutes.
2. Viva answers are timed: target under 3 seconds.
3. N projects submitted at once: all must finish; total time is reported.
Prints a table and writes the numbers as JSON (--out).
"""

import argparse
import concurrent.futures
import io
import json
import statistics
import time
import uuid
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def project_zip(target_lines: int, salt: str = "") -> tuple[bytes, int]:
    """A real project; `salt` makes each archive different so no result comes from cache."""
    buffer, lines = io.BytesIO(), 0
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("student.py", f"STUDENT = {salt!r}\n")
        for path in sorted((ROOT / "services").rglob("app/**/*.py")):
            if "migrations" in path.parts or lines >= target_lines:
                continue
            text = path.read_text(encoding="utf-8")
            bundle.writestr(str(path.relative_to(ROOT)), text)
            lines += text.count("\n")
    return buffer.getvalue(), lines


class Stack:
    def __init__(self, base: str, auth: str):
        self.http = httpx.Client(base_url=base + "/svc", timeout=600)
        # Logins go straight to auth-service: the gateway limits them to 10 a minute
        # per address (protection against password guessing), too few for a load test.
        self.auth = httpx.Client(base_url=auth, timeout=60)

    def token(self, username, password):
        r = self.auth.post("/api/v1/auth/login", json={"username": username, "password": password})
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def setup(self, students: int):
        run = uuid.uuid4().hex[:6]
        admin = self.token("admin", "admin-password-1")
        self.http.post(
            "/auth/api/v1/users",
            headers=admin,
            json={
                "username": f"pf{run}",
                "email": f"pf{run}@su.edu.ye",
                "password": "faculty-pass-1",
                "full_name": "perf",
                "role": "faculty",
            },
        ).raise_for_status()
        faculty = self.token(f"pf{run}", "faculty-pass-1")
        course = self.http.post(
            "/projects/api/v1/courses",
            headers=faculty,
            json={"name": "perf", "code": f"PF{run[:3]}"},
        ).json()
        heads, ids = [], []
        for i in range(students):
            name = f"ps{run}{i}"
            user = self.http.post(
                "/auth/api/v1/auth/register",
                json={
                    "username": name,
                    "email": f"{name}@su.edu.ye",
                    "password": "student-pass-1",
                    "full_name": name,
                },
            ).json()
            ids.append(user["id"])
            heads.append(self.token(name, "student-pass-1"))
        self.http.post(
            f"/projects/api/v1/courses/{course['id']}/students",
            headers=faculty,
            json={"student_ids": ids},
        ).raise_for_status()
        return course, heads

    def submit_and_wait(self, course, headers, archive: bytes) -> tuple[str, float, str]:
        start = time.perf_counter()
        while True:
            r = self.http.post(
                "/projects/api/v1/projects",
                headers=headers,
                data={"title": "perf", "course_id": course["id"]},
                files={"code": ("code.zip", archive, "application/zip")},
            )
            if r.status_code != 429:
                break
            time.sleep(1)
        r.raise_for_status()
        pid = r.json()["id"]
        while True:
            r = self.http.get(f"/projects/api/v1/projects/{pid}/status", headers=headers)
            if r.status_code == 429:  # the gateway's per-address limit: all clients share one here
                time.sleep(1)
                continue
            status = r.json()
            if status["status"] != "analyzing":
                return pid, time.perf_counter() - start, status["status"]
            time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--auth", default="http://127.0.0.1:8001", help="auth-service, for logins")
    parser.add_argument("--concurrent", type=int, default=10)
    parser.add_argument("--lines", type=int, default=10_000)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    stack = Stack(args.base, args.auth)
    archive, lines = project_zip(args.lines, salt=uuid.uuid4().hex)
    course, students = stack.setup(args.concurrent)
    results = {"project_lines": lines}

    print(f"1. analysis of a {lines}-line project")
    pid, seconds, status = stack.submit_and_wait(course, students[0], archive)
    results["analysis_seconds"] = round(seconds, 1)
    results["analysis_status"] = status
    print(f"   {status} in {seconds:.1f} s (target < 300 s)")

    print("2. viva answer latency")
    viva = stack.http.post(f"/projects/api/v1/viva/start/{pid}", headers=students[0], json={})
    viva.raise_for_status()
    sid = viva.json()["session_id"]
    timings = []
    for number in range(1, 6):
        t = time.perf_counter()
        r = stack.http.post(
            f"/viva/api/v1/viva/{sid}/answer",
            headers=students[0],
            json={
                "answer": "The function validates the input, queries the table with a "
                "parameterized "
                "statement and returns the result.",
                "question_number": number,
            },
        )
        timings.append(time.perf_counter() - t)
        if r.json().get("status") != "in_progress":
            break
    results["viva_answer_seconds"] = {
        "median": round(statistics.median(timings), 3),
        "max": round(max(timings), 3),
        "n": len(timings),
    }
    print(f"   median {statistics.median(timings):.2f} s, max {max(timings):.2f} s (target < 3 s)")

    print(f"3. {args.concurrent} projects submitted at the same time")
    archives = [project_zip(2_000, salt=uuid.uuid4().hex) for _ in students]
    small_lines = archives[0][1]
    t = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(args.concurrent) as pool:
        outcomes = list(
            pool.map(
                lambda pair: stack.submit_and_wait(course, pair[0], pair[1][0]),
                zip(students, archives, strict=True),
            )
        )
    wall = time.perf_counter() - t
    finished = sum(1 for _, _, s in outcomes if s == "analyzed")
    per = [s for _, s, _ in outcomes]
    results["concurrent"] = {
        "projects": args.concurrent,
        "lines_each": small_lines,
        "finished": finished,
        "wall_seconds": round(wall, 1),
        "slowest_seconds": round(max(per), 1),
    }
    print(
        f"   {finished}/{args.concurrent} analyzed, all done in {wall:.1f} s "
        f"(slowest {max(per):.1f} s)"
    )
    print(f"4. {args.concurrent} viva sessions at the same time")

    def viva_session(pair):
        (pid, _, _), headers = pair
        r = stack.http.post(f"/projects/api/v1/viva/start/{pid}", headers=headers, json={})
        r.raise_for_status()
        sid, times = r.json()["session_id"], []
        for number in range(1, 4):
            t = time.perf_counter()
            while True:
                r = stack.http.post(
                    f"/viva/api/v1/viva/{sid}/answer",
                    headers=headers,
                    json={
                        "answer": "It validates the input and uses a parameterized query.",
                        "question_number": number,
                    },
                )
                if r.status_code != 429:
                    break
                time.sleep(0.5)
            r.raise_for_status()
            times.append(time.perf_counter() - t)
        return times

    with concurrent.futures.ThreadPoolExecutor(args.concurrent) as pool:
        latencies = sorted(
            x for ts in pool.map(viva_session, zip(outcomes, students, strict=True)) for x in ts
        )
    p95 = latencies[int(0.95 * (len(latencies) - 1))]
    results["concurrent_viva"] = {
        "sessions": args.concurrent,
        "answers": len(latencies),
        "median_seconds": round(statistics.median(latencies), 3),
        "p95_seconds": round(p95, 3),
    }
    print(
        f"   {len(latencies)} answers: median {statistics.median(latencies):.2f} s, "
        f"p95 {p95:.2f} s (target < 3 s)"
    )
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
