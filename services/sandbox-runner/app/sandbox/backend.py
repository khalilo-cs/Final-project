"""Where student code runs. Production: Docker. Tests: a stand-in backend."""

import io
import logging
import tarfile
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings
from app.sandbox.detect import RunPlan

log = logging.getLogger(__name__)


class BuildFailed(Exception):
    def __init__(self, message: str, logs: str = "") -> None:
        super().__init__(message)
        self.logs = logs


class Backend(ABC):
    @abstractmethod
    def prepare(self, run_id: str, plan: RunPlan, project: Path) -> object:
        """Copy the project and run the build steps. Returns a handle."""

    @abstractmethod
    def start(self, handle: object, plan: RunPlan) -> str:
        """Start the app; returns its base URL (reachable by the runner only)."""

    @abstractmethod
    def running(self, handle: object) -> bool: ...

    @abstractmethod
    def stats(self, handle: object) -> dict:
        """{"memory_mb": float, "cpu_percent": float}"""

    @abstractmethod
    def logs(self, handle: object) -> str: ...

    @abstractmethod
    def cleanup(self, handle: object) -> None: ...


def _tar(project: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in sorted(project.rglob("*")):
            if path.is_symlink() or ".git" in path.relative_to(project).parts:
                continue
            archive.add(path, arcname=path.relative_to(project).as_posix(), recursive=False)
    return buffer.getvalue()


class DockerBackend(Backend):
    """Two containers per run, both resource-limited with all capabilities dropped:

    1. build: may reach package registries, runs the install steps, then is committed;
    2. run: started from that image on an *internal* network (no internet), where only
       the runner can reach it.
    """

    def __init__(self) -> None:
        import docker

        self.client = docker.from_env()

    def _limits(self) -> dict:
        settings = get_settings()
        return {
            "mem_limit": f"{settings.memory_mb}m",
            "memswap_limit": f"{settings.memory_mb}m",
            "nano_cpus": int(settings.cpus * 1e9),
            "pids_limit": settings.pids_limit,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
        }

    def _network(self) -> str:
        name = get_settings().sandbox_network
        if not self.client.networks.list(names=[name]):
            self.client.networks.create(name, driver="bridge", internal=True)
        return name

    def prepare(self, run_id, plan, project):
        settings = get_settings()
        self.client.images.pull(plan.image)
        steps = " && ".join(plan.build) or "true"
        container = self.client.containers.create(
            plan.image,
            command=["sh", "-c", f"cd /app/{plan.workdir} && {steps}"],
            working_dir="/app",
            labels={"aipe.run": run_id},
            **self._limits(),
        )
        try:
            container.put_archive("/app", _tar(project))
            container.start()
            try:
                result = container.wait(timeout=settings.build_timeout_seconds)
            except Exception as exc:  # noqa: BLE001 - requests timeout types vary
                raise BuildFailed(
                    "Build took too long", container.logs(tail=200).decode(errors="replace")
                ) from exc
            output = container.logs(tail=200).decode(errors="replace")
            if result.get("StatusCode", 1) != 0:
                raise BuildFailed("Build failed", output)
            image = container.commit(repository="aipe-sandbox", tag=run_id)
            return {"image": image.id, "container": None, "build_logs": output}
        finally:
            container.remove(force=True)

    def start(self, handle, plan):
        container = self.client.containers.run(
            handle["image"],
            command=["sh", "-c", f"cd /app/{plan.workdir} && {plan.start}"],
            network=self._network(),
            detach=True,
            # Inside the isolated container: the app must listen on the container's own
            # interface so the runner can reach it over the internal network.
            environment={"PORT": str(plan.port), "HOST": "0.0.0.0"},  # noqa: S104
            **self._limits(),
        )
        handle["container"] = container
        container.reload()
        address = container.attrs["NetworkSettings"]["Networks"][self._network()]["IPAddress"]
        return f"http://{address}:{plan.port}"

    def running(self, handle):
        container = handle.get("container")
        if container is None:
            return False
        container.reload()
        return container.status == "running"

    def stats(self, handle):
        raw = handle["container"].stats(stream=False)
        memory = raw.get("memory_stats", {}).get("usage", 0) / (1024 * 1024)
        cpu, pre = raw.get("cpu_stats", {}), raw.get("precpu_stats", {})
        cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get(
            "total_usage", 0
        )
        system_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
        cores = cpu.get("online_cpus", 1) or 1
        percent = (cpu_delta / system_delta) * cores * 100 if system_delta > 0 else 0.0
        return {"memory_mb": round(memory, 1), "cpu_percent": round(percent, 1)}

    def logs(self, handle):
        container = handle.get("container")
        return container.logs(tail=200).decode(errors="replace") if container else ""

    def cleanup(self, handle):
        try:
            if handle.get("container") is not None:
                handle["container"].remove(force=True)
            self.client.images.remove(handle["image"], force=True)
        except Exception:  # noqa: BLE001 - cleanup is best effort
            log.warning("sandbox cleanup failed", exc_info=True)
