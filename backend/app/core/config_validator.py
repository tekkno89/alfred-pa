"""Startup config validation.

Checks that the settings needed for each service are present and consistent.
Logs warnings/errors at startup but does NOT prevent the app from starting —
services degrade gracefully when config is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ConfigIssue:
    service: str  # "coding_assistant", "slack", "github", etc.
    severity: str  # "error" | "warning"
    field: str  # config field / env var name
    message: str


@dataclass
class ServiceStatus:
    name: str
    enabled: bool
    details: dict[str, str] = field(default_factory=dict)
    issues: list[ConfigIssue] = field(default_factory=list)


def validate_config(settings: Settings) -> list[ConfigIssue]:
    """Return a list of config issues for the current settings."""
    issues: list[ConfigIssue] = []

    # --- Coding assistant ---
    if settings.coding_runtime_provider == "docker_sandbox":
        if not settings.sandbox_url:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "SANDBOX_URL",
                    "Required for docker_sandbox runtime",
                )
            )
        if not settings.sandbox_api_key:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "warning",
                    "SANDBOX_API_KEY",
                    "No API key set for sandbox — requests will be unauthenticated",
                )
            )
    elif settings.coding_runtime_provider == "kubernetes":
        if not settings.coding_k8s_namespace:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "CODING_K8S_NAMESPACE",
                    "Required for kubernetes runtime",
                )
            )
    elif settings.coding_runtime_provider == "cloudrun":
        if not settings.coding_cloudrun_project:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "CODING_CLOUDRUN_PROJECT",
                    "Required for cloudrun runtime",
                )
            )
        if not settings.coding_cloudrun_region:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "CODING_CLOUDRUN_REGION",
                    "Required for cloudrun runtime",
                )
            )

    # Claude Code provider auth
    if settings.claude_code_provider == "api":
        if not settings.claude_code_api_key:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "CLAUDE_CODE_API_KEY",
                    "Direct API provider selected but no API key configured",
                )
            )
    elif settings.claude_code_provider == "vertex":
        if not settings.claude_code_vertex_project:
            issues.append(
                ConfigIssue(
                    "coding_assistant",
                    "error",
                    "CLAUDE_CODE_VERTEX_PROJECT",
                    "Vertex provider selected but no project configured",
                )
            )

    # Completion method
    if (
        settings.coding_completion_method == "callback"
        and not settings.coding_callback_base_url
    ):
        issues.append(
            ConfigIssue(
                "coding_assistant",
                "warning",
                "CODING_CALLBACK_BASE_URL",
                "Callback completion method requires a base URL — containers won't be able to report completion",
            )
        )

    # Event bus
    if (
        settings.coding_event_bus_provider == "gcp_pubsub"
        and not settings.coding_gcp_pubsub_project
    ):
        issues.append(
            ConfigIssue(
                "coding_assistant",
                "error",
                "CODING_GCP_PUBSUB_PROJECT",
                "Required for gcp_pubsub event bus",
            )
        )

    # --- Slack ---
    if settings.slack_bot_token and not settings.slack_signing_secret:
        issues.append(
            ConfigIssue(
                "slack",
                "error",
                "SLACK_SIGNING_SECRET",
                "Bot token set but signing secret is missing — Slack event verification will fail",
            )
        )

    # --- GitHub ---
    if settings.github_app_id and not settings.github_client_id:
        issues.append(
            ConfigIssue(
                "github",
                "warning",
                "GITHUB_CLIENT_ID",
                "GitHub App ID set but client ID missing — OAuth flow won't work",
            )
        )

    return issues


def get_service_statuses(settings: Settings) -> list[ServiceStatus]:
    """Build service status summaries for the admin API."""
    issues = validate_config(settings)

    def issues_for(service: str) -> list[ConfigIssue]:
        return [i for i in issues if i.service == service]

    services = [
        ServiceStatus(
            name="coding_assistant",
            enabled=bool(
                settings.sandbox_url
                or settings.coding_runtime_provider != "docker_sandbox"
            ),
            details={
                "runtime": settings.coding_runtime_provider,
                "llm_provider": settings.claude_code_provider,
                "completion_method": settings.coding_completion_method,
                "event_bus": settings.coding_event_bus_provider,
            },
            issues=issues_for("coding_assistant"),
        ),
        ServiceStatus(
            name="slack",
            enabled=bool(settings.slack_bot_token),
            details={},
            issues=issues_for("slack"),
        ),
        ServiceStatus(
            name="github",
            enabled=bool(settings.github_app_id),
            details={},
            issues=issues_for("github"),
        ),
    ]
    return services


def log_config_issues(settings: Settings) -> None:
    """Log config issues at startup."""
    issues = validate_config(settings)
    if not issues:
        logger.info("Config validation: all checks passed")
        return

    for issue in issues:
        msg = f"Config [{issue.service}] {issue.field}: {issue.message}"
        if issue.severity == "error":
            logger.error(msg)
        else:
            logger.warning(msg)
