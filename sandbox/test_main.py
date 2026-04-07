"""Tests for the sandbox orchestrator service."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set env before importing app
os.environ["SIDECAR_API_KEY"] = "test-key"
os.environ["WORKSPACE_ROOT"] = "/tmp/sandbox-test-workspaces"
Path("/tmp/sandbox-test-workspaces").mkdir(exist_ok=True)

from main import ALLOWED_IMAGES, app  # noqa: E402

client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    @patch("main.get_docker")
    def test_health_ok(self, mock_docker):
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @patch("main.get_docker")
    def test_health_docker_down(self, mock_docker):
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("connection refused")
        mock_docker.return_value = mock_client
        resp = client.get("/health")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_missing_api_key(self):
        resp = client.post("/jobs", json={"image": "alfred-claude-code:latest"})
        assert resp.status_code == 422  # missing header

    def test_wrong_api_key(self):
        resp = client.post(
            "/jobs",
            json={"image": "alfred-claude-code:latest"},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 403

    def test_correct_api_key_passes(self):
        """Auth passes but request may fail for other reasons (no Docker)."""
        with patch("main.get_docker") as mock_docker:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_container.id = "abc123"
            mock_client.containers.run.return_value = mock_container
            mock_docker.return_value = mock_client
            resp = client.post(
                "/jobs",
                json={"image": "alfred-claude-code:latest"},
                headers=HEADERS,
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Image allowlist
# ---------------------------------------------------------------------------


class TestImageAllowlist:
    def test_disallowed_image_rejected(self):
        resp = client.post(
            "/jobs",
            json={"image": "ubuntu:latest"},
            headers=HEADERS,
        )
        assert resp.status_code == 403
        assert "allowlist" in resp.json()["detail"].lower()

    def test_allowed_image_accepted(self):
        with patch("main.get_docker") as mock_docker:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_container.id = "container-id-123"
            mock_client.containers.run.return_value = mock_container
            mock_docker.return_value = mock_client
            resp = client.post(
                "/jobs",
                json={"image": "alfred-claude-code:latest"},
                headers=HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["container_id"] == "container-id-123"

    def test_allowlist_contains_only_expected_images(self):
        assert ALLOWED_IMAGES == {"alfred-claude-code:latest"}


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


class TestJobLifecycle:
    @patch("main.get_docker")
    def test_create_job_passes_correct_params(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "c123"
        mock_client.containers.run.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.post(
            "/jobs",
            json={
                "image": "alfred-claude-code:latest",
                "environment": {"MODE": "plan", "REPO": "owner/repo"},
                "memory_limit": "2g",
                "cpu_limit": 1.0,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200

        call_kwargs = mock_client.containers.run.call_args
        assert call_kwargs.kwargs["user"] == "1000:1000"
        assert call_kwargs.kwargs["mem_limit"] == "2g"
        assert call_kwargs.kwargs["nano_cpus"] == int(1.0 * 1e9)
        assert call_kwargs.kwargs["detach"] is True
        assert call_kwargs.kwargs["remove"] is False
        env = call_kwargs.kwargs["environment"]
        assert env["MODE"] == "plan"
        assert env["REPO"] == "owner/repo"

    @patch("main.get_docker")
    def test_cpu_ceiling_enforced(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "c123"
        mock_client.containers.run.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.post(
            "/jobs",
            json={"image": "alfred-claude-code:latest", "cpu_limit": 99.0},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        call_kwargs = mock_client.containers.run.call_args
        # Should be capped at MAX_CPUS (2.0)
        assert call_kwargs.kwargs["nano_cpus"] == int(2.0 * 1e9)

    @patch("main.get_docker")
    def test_get_job_status_running(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "c123"
        mock_container.labels = {"alfred-sandbox.managed": "true"}
        mock_container.attrs = {
            "State": {"Status": "running", "StartedAt": "2026-01-01T00:00:00Z"},
        }
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/c123", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["exit_code"] is None

    @patch("main.get_docker")
    def test_get_job_status_exited(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "c123"
        mock_container.labels = {"alfred-sandbox.managed": "true"}
        mock_container.attrs = {
            "State": {
                "Status": "exited",
                "ExitCode": 0,
                "StartedAt": "2026-01-01T00:00:00Z",
                "FinishedAt": "2026-01-01T00:05:00Z",
            },
        }
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/c123", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "exited"
        assert data["exit_code"] == 0

    @patch("main.get_docker")
    def test_get_nonexistent_job(self, mock_docker):
        import docker.errors

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("not found")
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/nonexistent", headers=HEADERS)
        assert resp.status_code == 404

    @patch("main.get_docker")
    def test_unmanaged_container_rejected(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.labels = {}  # Not managed by us
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/some-id", headers=HEADERS)
        assert resp.status_code == 404

    @patch("main.get_docker")
    def test_delete_job(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.labels = {
            "alfred-sandbox.managed": "true",
            "alfred-sandbox.workspace": "/tmp/test-ws",
        }
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.delete("/jobs/c123", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        mock_container.remove.assert_called_once_with(force=True)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class TestJobOutput:
    @patch("main.get_docker")
    def test_get_output_files(self, mock_docker, tmp_path):
        # Create fake output files
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "plan.md").write_text("# Plan\nDo the thing")
        (workspace / "conversation.log").write_text("log content")

        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.labels = {
            "alfred-sandbox.managed": "true",
            "alfred-sandbox.workspace": str(workspace),
        }
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/c123/output", headers=HEADERS)
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert "plan.md" in files
        assert "conversation.log" in files
        assert "Do the thing" in files["plan.md"]

    @patch("main.get_docker")
    def test_get_output_no_workspace(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.labels = {
            "alfred-sandbox.managed": "true",
            # No workspace label
        }
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/c123/output", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class TestJobLogs:
    @patch("main.get_docker")
    def test_get_logs(self, mock_docker):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.labels = {"alfred-sandbox.managed": "true"}
        mock_container.logs.return_value = b"2026-01-01T00:00:00Z some log line\n"
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client

        resp = client.get("/jobs/c123/logs", headers=HEADERS)
        assert resp.status_code == 200
        assert "some log line" in resp.json()["logs"]
