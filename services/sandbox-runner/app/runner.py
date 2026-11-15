"""One performance run: detect, build, start, measure, clean up."""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.profiler import http_profiler as profiler
from app.sandbox.backend import Backend, BuildFailed
from app.sandbox.detect import UnsupportedProject, detect

log = logging.getLogger(__name__)

RUNS: dict[str, dict] = {}  # in memory: a restart forgets runs (callers then retry)
_SLOTS = threading.Semaphore(2)  # at most two student projects run at once


def new_run() -> str:
    run_id = uuid.uuid4().hex[:16]
    RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
    }
    return run_id


def score(result: dict) -> tuple[float, list[dict]]:
    """0-100 with the reasons; starting weights, to be calibrated on real projects."""
    flags = []

    def flag(kind, severity, evidence, penalty):
        flags.append({"type": kind, "severity": severity, "evidence": evidence})
        return penalty

    if not result.get("runs_successfully"):
        return 0.0, [
            {
                "type": "does_not_run",
                "severity": "High",
                "evidence": result.get("error") or "The project did not start",
            }
        ]
    penalty = 0
    if (startup := result.get("startup_seconds") or 0) > 20:
        penalty += flag("slow_startup", "Low", f"Startup took {startup}s", 10)
    if levels := result.get("load_test"):
        worst = levels[-1]
        if worst["p95_ms"] is not None and worst["p95_ms"] > 1000:
            penalty += flag(
                "slow_under_load",
                "Medium",
                f"p95 {worst['p95_ms']} ms with {worst['concurrent_users']} users",
                20,
            )
        elif worst["p95_ms"] is not None and worst["p95_ms"] > 300:
            penalty += flag(
                "slow_under_load",
                "Low",
                f"p95 {worst['p95_ms']} ms with {worst['concurrent_users']} users",
                10,
            )
        if worst["error_rate"] > 0:
            penalty += flag(
                "errors_under_load",
                "Medium",
                f"{round(worst['error_rate'] * 100)}% failed requests with "
                f"{worst['concurrent_users']} users",
                min(40, worst["error_rate"] * 100),
            )
    if result.get("unresponsive_under_load"):
        penalty += flag(
            "unresponsive", "High", "Most requests timed out under load (possible deadlock)", 30
        )
    if result.get("memory_leak_suspected"):
        penalty += flag("memory_growth", "Medium", "Memory kept growing across load rounds", 15)
    if (memory := result.get("memory_peak_mb") or 0) > 400:
        penalty += flag("high_memory", "Low", f"Peak memory {memory} MB", 10)
    if any(e["status"] >= 500 for e in result.get("endpoints", [])):
        penalty += flag("server_errors", "Medium", "Some pages return HTTP 5xx", 15)
    return max(0.0, 100.0 - penalty), flags


def execute(run_id: str, project: Path, backend: Backend) -> None:
    settings = get_settings()
    run = RUNS[run_id]
    handle = None
    with _SLOTS:
        run["status"] = "running"
        try:
            plan = detect(project)
            run["stack"], run["notes"] = plan.stack, plan.notes
            run["phase"] = "building"
            handle = backend.prepare(run_id, plan, project)
            run["phase"] = "starting"
            base = backend.start(handle, plan)
            startup = profiler.wait_until_ready(
                base, settings.startup_timeout_seconds, lambda: backend.running(handle)
            )
            if startup is None:
                raise BuildFailed("The project did not answer HTTP requests", backend.logs(handle))
            run.update(runs_successfully=True, startup_seconds=startup, phase="measuring")
            idle = backend.stats(handle)
            paths = profiler.discover_paths(base)
            run["endpoints"] = profiler.measure_endpoints(base, paths)
            memory = [idle["memory_mb"]]
            cpu = [idle["cpu_percent"]]
            levels = []
            for users in settings.load_levels:
                level = profiler.load_test(base, "/", users, settings.requests_per_level)
                levels.append(level)
                sample = backend.stats(handle)
                memory.append(sample["memory_mb"])
                cpu.append(sample["cpu_percent"])
            run["load_test"] = levels
            run["memory_mb_samples"] = memory
            run["memory_peak_mb"] = max(memory)
            run["cpu_peak_percent"] = max(cpu)
            grew = all(b >= a for a, b in zip(memory, memory[1:], strict=False))
            run["memory_leak_suspected"] = bool(
                grew and memory[-1] > 1.5 * max(memory[0], 1) and memory[-1] - memory[0] > 50
            )
            heavy = levels[-1] if levels else None
            run["unresponsive_under_load"] = bool(
                heavy and heavy["timeouts"] / heavy["requests"] >= 0.5 and backend.running(handle)
            )
        except UnsupportedProject as exc:
            run.update(runs_successfully=False, error=str(exc))
        except BuildFailed as exc:
            run.update(runs_successfully=False, error=str(exc), logs=exc.logs[-4000:])
        except Exception as exc:  # noqa: BLE001 - any failure is reported, never crashes
            log.exception("run %s failed", run_id)
            run.update(runs_successfully=False, error=f"Sandbox error ({type(exc).__name__})")
        finally:
            if handle is not None:
                backend.cleanup(handle)
        run["overall_performance_score"], run["flags"] = score(run)
        run["status"] = "done"
        run["finished_at"] = datetime.now(UTC).isoformat()
        run.pop("phase", None)


def start_in_background(run_id: str, project_dir_holder, backend: Backend) -> None:
    def work():
        with project_dir_holder as root:
            execute(run_id, Path(root) / "project", backend)

    threading.Thread(target=work, daemon=True).start()
    time.sleep(0)  # let the thread start
