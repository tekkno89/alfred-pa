"""Docker Sandbox runtime provider.

Wraps the alfred-sandbox sidecar HTTP API. The sidecar owns the Docker socket
and handles container lifecycle — this provider translates RuntimeProvider
calls into sandbox HTTP requests.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import logging

import httpx

from app.core.config import get_settings
from app.core.runtime.provider import (
    JobHandle,
    JobRuntimeStatus,
    JobSpec,
    RuntimeProvider,
)

logger = logging.getLogger(__name__)

RUNTIME_TYPE = "docker_sandbox"


class DockerSandboxProvider(RuntimeProvider):
    """Runtime provider backed by the alfred-sandbox sidecar."""

    async def launch(self, spec: JobSpec) -> JobHandle:
        settings = get_settings()

        environment = dict(spec.environment)

        # --- Completion reporting env vars ---
        environment["JOB_ID"] = spec.job_id

        completion_method = settings.coding_completion_method
        environment["COMPLETION_METHOD"] = completion_method

        if completion_method == "callback":
            callback_base = settings.coding_callback_base_url
            if callback_base:
                environment["CALLBACK_URL"] = (
                    f"{callback_base.rstrip('/')}/api/coding-jobs/callback"
                )
                environment["CALLBACK_TOKEN"] = _generate_callback_token(
                    spec.job_id
                )
        elif completion_method == "redis":
            if settings.redis_url:
                environment["REDIS_URL"] = settings.redis_url
        # For gcp_pubsub, the container uses its GCP credentials + REST API

        if completion_method in ("redis", "gcp_pubsub"):
            environment["COMPLETION_TOPIC"] = _completion_topic(
                environment.get("MODE", "unknown")
            )

        # --- Claude Code LLM provider ---
        volumes: list[dict[str, str]] = []

        if settings.claude_code_provider == "api":
            # Direct Anthropic API — just needs an API key
            if settings.claude_code_api_key:
                environment["ANTHROPIC_API_KEY"] = settings.claude_code_api_key
        else:
            # Vertex AI — needs CLAUDE_CODE_USE_VERTEX + project/region + GCP creds
            environment["CLAUDE_CODE_USE_VERTEX"] = "1"

            if settings.claude_code_vertex_project:
                environment["ANTHROPIC_VERTEX_PROJECT_ID"] = (
                    settings.claude_code_vertex_project
                )
                environment["ANTHROPIC_VERTEX_REGION"] = (
                    settings.claude_code_vertex_region
                )

            # GCP credentials (3 options, priority order)
            if settings.claude_code_gcp_sa_json:
                # Option 1: SA JSON as env var — container writes to /tmp on startup
                environment["GCP_SA_JSON"] = settings.claude_code_gcp_sa_json
            elif settings.claude_code_gcp_credentials_file:
                # Option 2: SA file path — mount read-only into container
                volumes.append(
                    {
                        "host_path": settings.claude_code_gcp_credentials_file,
                        "container_path": "/credentials/gcp.json",
                    }
                )
                environment["GOOGLE_APPLICATION_CREDENTIALS"] = "/credentials/gcp.json"
            elif settings.claude_code_gcp_adc_path:
                # Option 3: gcloud ADC directory — mount read-only
                volumes.append(
                    {
                        "host_path": settings.claude_code_gcp_adc_path,
                        "container_path": "/home/coder/.config/gcloud",
                    }
                )

        # --- Call sandbox sidecar ---
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.sandbox_url}/jobs",
                json={
                    "image": settings.claude_code_image,
                    "environment": environment,
                    "volumes": volumes,
                    **({"network_mode": settings.sandbox_docker_network}
                       if settings.sandbox_docker_network else {}),
                },
                headers={"X-API-Key": settings.sandbox_api_key},
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Sandbox launch failed ({resp.status_code}): {resp.text}"
            )

        container_id = resp.json()["container_id"]
        return JobHandle(
            job_id=spec.job_id,
            runtime_id=container_id,
            runtime_type=RUNTIME_TYPE,
        )

    async def get_status(self, handle: JobHandle) -> JobRuntimeStatus:
        settings = get_settings()

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.sandbox_url}/jobs/{handle.runtime_id}",
                headers={"X-API-Key": settings.sandbox_api_key},
            )

        if resp.status_code == 404:
            return JobRuntimeStatus(
                runtime_id=handle.runtime_id,
                state="failed",
                logs="Container not found (may have been removed)",
            )

        if resp.status_code != 200:
            return JobRuntimeStatus(
                runtime_id=handle.runtime_id,
                state="unknown",
                logs=f"Sandbox returned {resp.status_code}: {resp.text[:500]}",
            )

        data = resp.json()
        container_status = data.get("status", "unknown")

        if container_status == "running":
            return JobRuntimeStatus(
                runtime_id=handle.runtime_id, state="running"
            )
        elif container_status == "exited":
            exit_code = data.get("exit_code", -1)
            state = "succeeded" if exit_code == 0 else "failed"

            # Fetch logs on failure
            logs = None
            if state == "failed":
                logs = await self._fetch_logs(handle)

            return JobRuntimeStatus(
                runtime_id=handle.runtime_id,
                state=state,
                exit_code=exit_code,
                logs=logs,
            )
        else:
            return JobRuntimeStatus(
                runtime_id=handle.runtime_id, state="unknown"
            )

    async def cancel(self, handle: JobHandle) -> None:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                f"{settings.sandbox_url}/jobs/{handle.runtime_id}",
                headers={"X-API-Key": settings.sandbox_api_key},
            )

    async def cleanup(self, handle: JobHandle) -> None:
        # For Docker sandbox, cancel and cleanup are the same operation —
        # DELETE removes the container and its workspace.
        await self.cancel(handle)

    async def _fetch_logs(self, handle: JobHandle) -> str | None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.sandbox_url}/jobs/{handle.runtime_id}/logs",
                    headers={"X-API-Key": settings.sandbox_api_key},
                )
            if resp.status_code == 200:
                return resp.json().get("logs", "")
        except Exception:
            pass
        return None


def _generate_callback_token(job_id: str) -> str:
    """Generate an HMAC-SHA256 token for callback auth.

    Stateless — can be verified by recomputing from jwt_secret + job_id.
    """
    settings = get_settings()
    return hmac_mod.new(
        settings.jwt_secret.encode(),
        job_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_callback_token(job_id: str, token: str) -> bool:
    """Verify an HMAC callback token."""
    expected = _generate_callback_token(job_id)
    return hmac_mod.compare_digest(expected, token)


def _completion_topic(mode: str) -> str:
    """Map container mode to event bus topic."""
    topic_map = {
        "plan": "coding.plan_complete",
        "implement": "coding.impl_complete",
        "review": "coding.review_complete",
        "explore": "coding.explore_complete",
    }
    return topic_map.get(mode, f"coding.{mode}_complete")
