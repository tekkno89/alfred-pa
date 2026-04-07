"""Container runtime abstraction for coding job orchestration."""

from app.core.runtime.provider import (
    JobHandle,
    JobRuntimeStatus,
    JobSpec,
    RuntimeProvider,
)

_provider_instance: RuntimeProvider | None = None


def get_runtime_provider() -> RuntimeProvider:
    """Get or create the singleton runtime provider based on config."""
    global _provider_instance
    if _provider_instance is None:
        from app.core.config import get_settings

        settings = get_settings()
        provider = settings.coding_runtime_provider

        if provider == "docker_sandbox":
            from app.core.runtime.docker_sandbox import DockerSandboxProvider

            _provider_instance = DockerSandboxProvider()
        elif provider == "kubernetes":
            raise NotImplementedError(
                "Kubernetes runtime provider is not yet implemented. "
                "Set CODING_RUNTIME_PROVIDER=docker_sandbox"
            )
        elif provider == "cloudrun":
            raise NotImplementedError(
                "Cloud Run runtime provider is not yet implemented. "
                "Set CODING_RUNTIME_PROVIDER=docker_sandbox"
            )
        else:
            raise ValueError(
                f"Unknown runtime provider: {provider}. "
                "Valid options: docker_sandbox, kubernetes, cloudrun"
            )
    return _provider_instance


__all__ = [
    "RuntimeProvider",
    "JobSpec",
    "JobHandle",
    "JobRuntimeStatus",
    "get_runtime_provider",
]
