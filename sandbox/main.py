"""
Alfred Sandbox Orchestrator — lightweight FastAPI sidecar that owns the Docker socket.

Launches, monitors, and tears down ephemeral containers on behalf of the Alfred backend.
Only allowlisted images may be run. Every request is authenticated via API key.
"""

from __future__ import annotations

import logging
import os

import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import docker
import docker.errors
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from pydantic import BaseModel

logger = logging.getLogger("alfred-sandbox")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SIDECAR_API_KEY = os.environ.get("SIDECAR_API_KEY", "")
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspaces"))
ORPHAN_MAX_AGE_SECONDS = int(os.environ.get("ORPHAN_MAX_AGE_SECONDS", "3600"))  # 1 hr

# Only these images may be launched. Reject everything else.
ALLOWED_IMAGES: set[str] = {
    "alfred-claude-code:latest",
}

# Container resource defaults (can be overridden per-request within these ceilings)
MAX_MEMORY = "4g"
MAX_CPUS = 2.0
DEFAULT_STOP_TIMEOUT = 1800  # 30 min

# Label used to identify containers managed by this sidecar
MANAGED_LABEL = "alfred-sandbox.managed"

# ---------------------------------------------------------------------------
# Docker client (lazy singleton)
# ---------------------------------------------------------------------------

_docker_client: docker.DockerClient | None = None


def get_docker() -> docker.DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


def _cleanup_orphans(client: docker.DockerClient) -> None:
    """Remove containers managed by this sidecar that are older than ORPHAN_MAX_AGE_SECONDS."""
    try:
        containers = client.containers.list(
            all=True, filters={"label": MANAGED_LABEL}
        )
    except Exception:
        logger.exception("Failed to list containers for orphan cleanup")
        return

    now = time.time()
    for c in containers:
        try:
            # created is ISO 8601 — docker SDK exposes attrs
            import dateutil.parser

            created = dateutil.parser.isoparse(c.attrs["Created"]).timestamp()
            age = now - created
            if age > ORPHAN_MAX_AGE_SECONDS:
                logger.info("Removing orphan container %s (age=%.0fs)", c.short_id, age)
                c.remove(force=True)
        except Exception:
            logger.exception("Failed to remove orphan container %s", c.short_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("alfred-sandbox starting up")
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        client = get_docker()
        _cleanup_orphans(client)
    except Exception:
        logger.exception("Docker client init failed — will retry on first request")
    yield
    logger.info("alfred-sandbox shutting down")


app = FastAPI(title="Alfred Sandbox Orchestrator", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def verify_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    if not SIDECAR_API_KEY:
        raise HTTPException(500, "SIDECAR_API_KEY not configured")
    if x_api_key != SIDECAR_API_KEY:
        raise HTTPException(403, "Invalid API key")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class VolumeMount(BaseModel):
    host_path: str
    container_path: str
    mode: str = "ro"  # read-only by default for security


class JobCreateRequest(BaseModel):
    image: str
    environment: dict[str, str] = {}
    network_mode: str | None = None
    memory_limit: str = MAX_MEMORY
    cpu_limit: float = MAX_CPUS
    stop_timeout: int = DEFAULT_STOP_TIMEOUT
    volumes: list[VolumeMount] = []


class JobCreateResponse(BaseModel):
    container_id: str


class JobStatusResponse(BaseModel):
    container_id: str
    status: str  # "running", "exited", "created", etc.
    exit_code: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobOutputResponse(BaseModel):
    files: dict[str, str]  # filename -> content


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check — also verifies Docker socket is reachable."""
    try:
        client = get_docker()
        client.ping()
        return {"status": "healthy", "docker": "connected"}
    except Exception as exc:
        raise HTTPException(503, f"Docker unavailable: {exc}")


@app.post("/jobs", response_model=JobCreateResponse, dependencies=[Depends(verify_api_key)])
async def create_job(req: JobCreateRequest):
    """Launch a new container from an allowlisted image."""

    # --- Image allowlist ---
    if req.image not in ALLOWED_IMAGES:
        raise HTTPException(
            403,
            f"Image '{req.image}' is not in the allowlist. Allowed: {sorted(ALLOWED_IMAGES)}",
        )

    # --- Enforce resource ceilings ---
    cpu_limit = min(req.cpu_limit, MAX_CPUS)
    # Parse memory — just pass through since Docker validates it
    memory_limit = req.memory_limit

    client = get_docker()

    # Build volume mounts — only extra mounts (read-only enforced).
    # Container writes output to /output internally; we retrieve via docker cp.
    volume_mounts = {}
    for vol in req.volumes:
        volume_mounts[vol.host_path] = {
            "bind": vol.container_path,
            "mode": "ro",  # Always enforce read-only for extra mounts
        }

    try:
        container = client.containers.run(
            image=req.image,
            detach=True,
            user="1000:1000",
            mem_limit=memory_limit,
            nano_cpus=int(cpu_limit * 1e9),
            environment=req.environment,
            network_mode=req.network_mode,
            volumes=volume_mounts or None,
            labels={
                MANAGED_LABEL: "true",
            },
            remove=False,  # Keep for log/output retrieval; cleaned up on DELETE
        )
    except docker.errors.ImageNotFound:
        raise HTTPException(404, f"Image '{req.image}' not found locally. Build it first.")
    except Exception as exc:
        logger.exception("Failed to launch container")
        raise HTTPException(500, f"Container launch failed: {exc}")

    logger.info("Launched container %s (image=%s)", container.short_id, req.image)
    return JobCreateResponse(container_id=container.id)


@app.get("/jobs/{container_id}", response_model=JobStatusResponse, dependencies=[Depends(verify_api_key)])
async def get_job(container_id: str):
    """Get container status and exit code."""
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(404, "Container not found")

    # Verify this is a managed container
    if container.labels.get(MANAGED_LABEL) != "true":
        raise HTTPException(404, "Container not found")

    container.reload()
    state = container.attrs.get("State", {})

    return JobStatusResponse(
        container_id=container.id,
        status=state.get("Status", "unknown"),
        exit_code=state.get("ExitCode") if state.get("Status") == "exited" else None,
        started_at=state.get("StartedAt"),
        finished_at=state.get("FinishedAt") if state.get("Status") == "exited" else None,
    )



@app.get("/jobs/{container_id}/logs", dependencies=[Depends(verify_api_key)])
async def get_job_logs(container_id: str, tail: int = 200):
    """Get container stdout/stderr logs."""
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(404, "Container not found")

    if container.labels.get(MANAGED_LABEL) != "true":
        raise HTTPException(404, "Container not found")

    try:
        logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(500, f"Failed to read logs: {exc}")

    return {"container_id": container_id, "logs": logs}


@app.delete("/jobs/{container_id}", dependencies=[Depends(verify_api_key)])
async def delete_job(container_id: str):
    """Force-kill and remove a container."""
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(404, "Container not found")

    if container.labels.get(MANAGED_LABEL) != "true":
        raise HTTPException(404, "Container not found")

    try:
        container.remove(force=True)
        logger.info("Removed container %s", container_id[:12])
    except Exception as exc:
        logger.exception("Failed to remove container %s", container_id[:12])
        raise HTTPException(500, f"Failed to remove container: {exc}")

    return {"deleted": True}
