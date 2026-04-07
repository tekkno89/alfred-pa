"""Coding job service — orchestrates the full lifecycle of coding assistant jobs.

Manages proposal creation, planning/implementation/review container launches via
a pluggable RuntimeProvider, Slack thread notifications, and SSE event publishing.
"""

import json
import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.runtime import JobHandle, JobSpec, get_runtime_provider
from app.db.models.coding_job import CodingJob
from app.db.repositories.coding_job import CodingJobRepository, TERMINAL_STATUSES
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)


class CodingJobService:
    """Orchestrates coding job lifecycle: propose → plan → implement → review."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CodingJobRepository(db)
        self.runtime = get_runtime_provider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_planning(self, job_id: str) -> CodingJob:
        """Start planning phase — called by API endpoint on button click."""
        job = await self._get_job(job_id)
        if job.status != "pending_plan_approval":
            raise ValueError(
                f"Cannot start planning: job is '{job.status}', expected 'pending_plan_approval'"
            )

        # Get a GitHub token for the repo
        github_token = await self._get_github_token(job)

        # Launch planning container
        container_id = await self._launch_container(
            job_id=job.id,
            mode="plan",
            repo=job.repo_full_name,
            github_token=github_token,
            task_description=job.task_description,
        )

        # Update job
        job = await self.repo.update_status(job, "planning", mode="plan")
        job = await self.repo.mark_started(
            job, container_id, datetime.now(UTC),
            runtime_type=get_settings().coding_runtime_provider,
        )
        await self.db.commit()

        # Notify
        await self._publish_update(job, "planning")
        await self._post_slack_update(job, "Planning in progress...")

        # Enqueue polling


        return job

    async def start_implementation(self, job_id: str) -> CodingJob:
        """Start implementation phase — called by API endpoint on button click."""
        job = await self._get_job(job_id)
        if job.status != "plan_ready":
            raise ValueError(
                f"Cannot start implementation: job is '{job.status}', expected 'plan_ready'"
            )

        github_token = await self._get_github_token(job)

        # Generate branch name if not set
        if not job.branch_name:
            short_id = str(uuid.uuid4())[:8]
            branch = f"alfred/coding-{short_id}"
            job = await self.repo.update(job, branch_name=branch)

        container_id = await self._launch_container(
            job_id=job.id,
            mode="implement",
            repo=job.repo_full_name,
            github_token=github_token,
            task_description=job.task_description,
            plan_content=job.plan_content or "",
            branch=job.branch_name or "",
        )

        job = await self.repo.update_status(
            job, "implementing", mode="implement"
        )
        job = await self.repo.mark_started(
            job, container_id, datetime.now(UTC),
            runtime_type=get_settings().coding_runtime_provider,
        )
        await self.db.commit()

        await self._publish_update(job, "implementing")
        await self._post_slack_update(job, "Implementation in progress...")


        return job

    async def start_review(self, job_id: str) -> CodingJob:
        """Start adversarial review — called automatically after implementation."""
        job = await self._get_job(job_id)

        github_token = await self._get_github_token(job)

        container_id = await self._launch_container(
            job_id=job.id,
            mode="review",
            repo=job.repo_full_name,
            github_token=github_token,
            task_description=job.task_description,
            plan_content=job.plan_content or "",
            branch=job.branch_name or "",
        )

        job = await self.repo.update_status(job, "reviewing", mode="review")
        job = await self.repo.mark_started(
            job, container_id, datetime.now(UTC),
            runtime_type=get_settings().coding_runtime_provider,
        )
        await self.db.commit()

        await self._publish_update(job, "reviewing")
        await self._post_slack_update(job, "Reviewing changes...")


        return job

    async def start_exploration(self, job_id: str) -> CodingJob:
        """Start codebase exploration — called by tool directly."""
        job = await self._get_job(job_id)

        github_token = await self._get_github_token(job)

        container_id = await self._launch_container(
            job_id=job.id,
            mode="explore",
            repo=job.repo_full_name,
            github_token=github_token,
            question=job.task_description,
        )

        job = await self.repo.mark_started(
            job, container_id, datetime.now(UTC),
            runtime_type=get_settings().coding_runtime_provider,
        )
        await self.db.commit()



        return job

    async def handle_container_complete(
        self, job_id: str, output: dict[str, str]
    ) -> CodingJob:
        """Handle container completion — called by callback, event bus, or polling."""
        job = await self._get_job(job_id)

        # Idempotency: skip if already in a terminal state (e.g. callback
        # and polling both fired, or job was cancelled while running).
        if job.status in TERMINAL_STATUSES:
            logger.info(f"Job {job_id} already {job.status}, skipping completion")
            return job

        if job.mode == "plan":
            plan_content = output.get("plan.md", "")
            conversation_log = output.get("conversation.log", "")
            job = await self.repo.update_status(
                job,
                "plan_ready",
                plan_content=plan_content,
                conversation_log=conversation_log,
            )
            await self.db.commit()

            await self._publish_update(job, "plan_ready")
            await self._post_slack_plan_ready(job)

        elif job.mode == "implement":
            result_json = output.get("result.json", "{}")
            try:
                result = json.loads(result_json)
            except json.JSONDecodeError:
                result = {}

            conversation_log = output.get("conversation.log", "")
            job = await self.repo.update_status(
                job,
                "reviewing",
                pr_url=result.get("pr_url"),
                pr_number=result.get("pr_number"),
                branch_name=result.get("branch", job.branch_name),
                conversation_log=conversation_log,
            )
            await self.db.commit()

            # Auto-launch adversarial review
            await self.start_review(job_id)

        elif job.mode == "review":
            review_content = output.get("review.md", "")
            job = await self.repo.mark_completed(
                job,
                completed_at=datetime.now(UTC),
                review_content=review_content,
            )
            await self.db.commit()

            await self._publish_update(job, "complete")
            await self._post_slack_complete(job)

        elif job.mode == "explore":
            answer = output.get("answer.md", "")
            job = await self.repo.mark_completed(
                job,
                completed_at=datetime.now(UTC),
                plan_content=answer,  # store answer in plan_content field
            )

            # Save the answer as a new assistant message in the chat session
            if answer and job.session_id:
                from app.db.repositories.message import MessageRepository
                msg_repo = MessageRepository(self.db)
                await msg_repo.create_message(
                    session_id=job.session_id,
                    role="assistant",
                    content=answer,
                )

            await self.db.commit()

            await self._publish_update(job, "complete")
            # Notify frontend to refresh messages
            if job.session_id:
                await NotificationService.publish_to_sse(
                    job.user_id, "messages.new", {"session_id": job.session_id}
                )

        return job

    async def handle_container_failed(
        self, job_id: str, error: str, logs: str | None = None
    ) -> CodingJob:
        """Handle container failure — called by callback, event bus, or polling."""
        job = await self._get_job(job_id)

        # Idempotency: skip if already terminal
        if job.status in TERMINAL_STATUSES:
            logger.info(f"Job {job_id} already {job.status}, skipping failure")
            return job

        error_details = error
        if logs:
            error_details += f"\n\nContainer logs:\n{logs[:2000]}"

        job = await self.repo.update_status(
            job,
            "failed",
            error_details=error_details,
            completed_at=datetime.now(UTC),
        )
        await self.db.commit()

        await self._publish_update(job, "failed")
        await self._post_slack_update(
            job, f"Job failed: {error[:200]}"
        )

        return job

    async def cancel_job(self, job_id: str) -> CodingJob:
        """Cancel a job, killing the container if running."""
        job = await self._get_job(job_id)
        if job.status in TERMINAL_STATUSES:
            raise ValueError(f"Job is already {job.status}")

        # Kill container if running
        try:
            await self._cancel_container(job)
        except Exception as e:
            logger.warning(f"Failed to kill container {job.container_id}: {e}")

        job = await self.repo.update_status(job, "cancelled")
        await self.db.commit()

        await self._publish_update(job, "cancelled")
        await self._post_slack_update(job, "Job cancelled.")

        return job

    async def request_revision(
        self, job_id: str, change_description: str
    ) -> CodingJob:
        """Create a new revision job linked to the original."""
        original = await self._get_job(job_id)

        new_job = await self.repo.create_job(
            user_id=original.user_id,
            session_id=original.session_id,
            repo_full_name=original.repo_full_name,
            task_description=change_description,
            github_account_label=original.github_account_label,
            revision_of_job_id=original.id,
            branch_name=original.branch_name,
            pr_url=original.pr_url,
            pr_number=original.pr_number,
        )
        await self.db.commit()

        await self._publish_update(new_job, "pending_plan_approval")

        return new_job

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_job(self, job_id: str) -> CodingJob:
        """Fetch a job by ID, raising ValueError if not found."""
        job = await self.repo.get(job_id)
        if not job:
            raise ValueError(f"Coding job {job_id} not found")
        return job

    async def _get_github_token(self, job: CodingJob) -> str:
        """Get a GitHub token for the job's repo.

        Tries installation token first (for GitHub App installs),
        falls back to user's OAuth/PAT token.
        """
        from app.services.github import GitHubService

        github_service = GitHubService(self.db)

        # Try installation token first
        try:
            token = await github_service.get_installation_token_for_repo(
                job.user_id, job.repo_full_name
            )
            if token:
                return token
        except Exception as e:
            logger.debug(f"Installation token not available: {e}")

        # Fall back to user's OAuth/PAT
        account_label = job.github_account_label
        if account_label:
            token = await github_service.get_valid_token(job.user_id, account_label)
        else:
            # No label specified — try "default", then fall back to first available
            token = await github_service.get_valid_token(job.user_id, "default")
            if not token:
                from app.db.repositories.oauth_token import OAuthTokenRepository
                token_repo = OAuthTokenRepository(self.db)
                all_tokens = await token_repo.get_all_by_user_and_provider(
                    job.user_id, "github"
                )
                if all_tokens:
                    token = await github_service.get_valid_token(
                        job.user_id, all_tokens[0].account_label
                    )

        if not token:
            label_msg = f" for account '{account_label}'" if account_label else ""
            raise ValueError(
                f"No valid GitHub token found{label_msg}. "
                "The user needs to reconnect their GitHub account."
            )
        return token

    async def _launch_container(
        self,
        job_id: str,
        mode: str,
        repo: str,
        github_token: str,
        task_description: str = "",
        plan_content: str = "",
        branch: str = "",
        question: str = "",
    ) -> str:
        """Launch a container via the RuntimeProvider. Returns runtime_id."""
        settings = get_settings()

        environment: dict[str, str] = {
            "MODE": mode,
            "REPO": repo,
            "GITHUB_TOKEN": github_token,
        }

        if task_description:
            environment["TASK_DESCRIPTION"] = task_description
        if plan_content:
            environment["PLAN_CONTENT"] = plan_content
        if branch:
            environment["BRANCH"] = branch
        if question:
            environment["QUESTION"] = question

        # Sensitive paths for pre-commit hook
        if mode == "implement" and settings.coding_sensitive_paths:
            environment["SENSITIVE_PATHS"] = settings.coding_sensitive_paths

        # The RuntimeProvider handles: completion env vars, GCP credentials,
        # Vertex AI config, and runtime-specific launch details.
        spec = JobSpec(
            job_id=job_id,
            image=settings.claude_code_image,
            environment=environment,
            timeout_seconds=settings.coding_job_timeout_minutes * 60,
        )
        handle = await self.runtime.launch(spec)
        return handle.runtime_id

    async def _cancel_container(self, job: CodingJob) -> None:
        """Cancel and clean up a container via the RuntimeProvider."""
        if not job.container_id:
            return
        handle = JobHandle(
            job_id=job.id,
            runtime_id=job.container_id,
            runtime_type=job.runtime_type or "docker_sandbox",
        )
        await self.runtime.cancel(handle)

    async def _cleanup_container(self, job: CodingJob) -> None:
        """Clean up container resources after completion."""
        if not job.container_id:
            return
        handle = JobHandle(
            job_id=job.id,
            runtime_id=job.container_id,
            runtime_type=job.runtime_type or "docker_sandbox",
        )
        try:
            await self.runtime.cleanup(handle)
        except Exception:
            pass  # Best-effort cleanup

    async def _publish_update(self, job: CodingJob, status: str) -> None:
        """Publish SSE event for a job status change."""
        payload = {
            "job_id": job.id,
            "status": status,
            "repo": job.repo_full_name,
            "mode": job.mode,
        }
        if job.plan_content and status == "plan_ready":
            payload["plan_content"] = job.plan_content
        if job.pr_url and status == "complete":
            payload["pr_url"] = job.pr_url
        if job.review_content and status == "complete":
            payload["review_content"] = job.review_content
        if job.error_details and status == "failed":
            payload["error_details"] = job.error_details

        await NotificationService.publish_to_sse(
            job.user_id, "coding_job_update", payload
        )

    # ------------------------------------------------------------------
    # Slack thread helpers
    # ------------------------------------------------------------------

    async def _get_slack_service(self):
        """Get the Slack service (lazy import to avoid circular deps)."""
        from app.services.slack import get_slack_service

        return get_slack_service()

    async def _post_slack_update(self, job: CodingJob, text: str) -> None:
        """Post a status update to the job's Slack thread."""
        if not job.slack_channel_id or not job.slack_thread_ts:
            return
        try:
            slack = await self._get_slack_service()
            await slack.post_message(
                channel=job.slack_channel_id,
                text=text,
                thread_ts=job.slack_thread_ts,
            )
        except Exception as e:
            logger.warning(f"Failed to post Slack update for job {job.id}: {e}")

    async def _post_slack_plan_ready(self, job: CodingJob) -> None:
        """Post plan-ready message with approval buttons to Slack thread."""
        if not job.slack_channel_id or not job.slack_thread_ts:
            return

        plan_preview = (job.plan_content or "")[:2000]
        if len(job.plan_content or "") > 2000:
            plan_preview += "\n... (truncated)"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Plan Ready* for `{job.repo_full_name}`\n```{plan_preview}```",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Implement"},
                        "action_id": "coding_approve_impl",
                        "value": job.id,
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "action_id": "coding_cancel",
                        "value": job.id,
                    },
                ],
            },
        ]

        try:
            slack = await self._get_slack_service()
            await slack.post_message(
                channel=job.slack_channel_id,
                text=f"Plan ready for {job.repo_full_name}",
                thread_ts=job.slack_thread_ts,
                blocks=blocks,
            )
        except Exception as e:
            logger.warning(f"Failed to post Slack plan-ready for job {job.id}: {e}")

    async def _post_slack_complete(self, job: CodingJob) -> None:
        """Post completion message with PR link and review to Slack thread."""
        if not job.slack_channel_id or not job.slack_thread_ts:
            return

        review_preview = (job.review_content or "No review available")[:1500]
        if len(job.review_content or "") > 1500:
            review_preview += "\n... (truncated)"

        pr_text = f"<{job.pr_url}|View PR>" if job.pr_url else "No PR created"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Implementation Complete* for `{job.repo_full_name}`\n"
                        f"PR: {pr_text}\n\n"
                        f"*Review:*\n{review_preview}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Request Changes",
                        },
                        "action_id": "coding_request_revision",
                        "value": job.id,
                    },
                ],
            },
        ]

        try:
            slack = await self._get_slack_service()
            await slack.post_message(
                channel=job.slack_channel_id,
                text=f"Implementation complete for {job.repo_full_name}",
                thread_ts=job.slack_thread_ts,
                blocks=blocks,
            )
        except Exception as e:
            logger.warning(f"Failed to post Slack completion for job {job.id}: {e}")
