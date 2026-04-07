"""Runtime provider interface for coding job container orchestration.

Abstracts the container runtime so coding jobs can run on Docker (via sandbox
sidecar), Kubernetes, Cloud Run, or other platforms without changing the
CodingJobService.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class JobSpec:
    """Runtime-agnostic job specification passed to RuntimeProvider.launch()."""

    job_id: str
    image: str
    environment: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 1800
    memory_limit: str = "4g"
    cpu_limit: float = 2.0


@dataclass
class JobHandle:
    """Opaque handle returned after launching a job.

    Contains the runtime-specific identifier needed to query status, cancel,
    or clean up the job later.
    """

    job_id: str
    runtime_id: str  # container_id, k8s job name, cloud run execution id, etc.
    runtime_type: str  # "docker_sandbox", "kubernetes", "cloudrun"


@dataclass
class JobRuntimeStatus:
    """Runtime-agnostic job status returned by RuntimeProvider.get_status()."""

    runtime_id: str
    state: str  # "running", "succeeded", "failed", "unknown"
    exit_code: int | None = None
    logs: str | None = None


class RuntimeProvider(ABC):
    """Abstract base for container runtime providers.

    Each implementation handles launching, monitoring, and cleaning up jobs
    on a specific runtime. The provider is also responsible for injecting
    completion-reporting env vars and GCP credentials appropriate for its
    runtime.
    """

    @abstractmethod
    async def launch(self, spec: JobSpec) -> JobHandle:
        """Launch a job. Returns an opaque handle for subsequent operations."""
        ...

    @abstractmethod
    async def get_status(self, handle: JobHandle) -> JobRuntimeStatus:
        """Query job status (e.g. for admin inspection)."""
        ...

    @abstractmethod
    async def cancel(self, handle: JobHandle) -> None:
        """Cancel/kill a running job."""
        ...

    @abstractmethod
    async def cleanup(self, handle: JobHandle) -> None:
        """Remove resources (container, workspace, pod, etc.) after completion."""
        ...
