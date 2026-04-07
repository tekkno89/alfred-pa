"""Coding assistant tool for the LLM agent.

Allows proposing coding tasks, asking questions about codebases,
checking job status, and cancelling jobs. Approvals (planning,
implementation) are handled deterministically via UI/Slack buttons —
this tool NEVER triggers those actions.
"""

import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext

logger = logging.getLogger(__name__)


class CodingAssistantTool(BaseTool):
    """Tool for managing coding tasks via ephemeral Claude Code containers."""

    name = "coding_assistant"
    description = (
        "Manage coding tasks on GitHub repositories. Actions: "
        '"propose" creates a coding task proposal for user approval (planning and implementation '
        "are triggered by the user via buttons, not by this tool), "
        '"ask_codebase" asks a question about a repo\'s code, '
        '"status" checks progress of active coding jobs, '
        '"cancel" cancels an active coding job. '
        "IMPORTANT: Always confirm which repo to work on before using this tool."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["propose", "ask_codebase", "status", "cancel"],
                "description": "The coding assistant action to perform.",
            },
            "repo": {
                "type": "string",
                "description": (
                    "GitHub repo in owner/repo format. "
                    "REQUIRED for propose and ask_codebase — always ask the user if not specified."
                ),
            },
            "task_description": {
                "type": "string",
                "description": "Description of the coding task (for propose action).",
            },
            "question": {
                "type": "string",
                "description": "Question to ask about the codebase (for ask_codebase action).",
            },
            "account_label": {
                "type": "string",
                "description": "GitHub account label to use (e.g. 'personal', 'work'). Optional.",
            },
            "job_id": {
                "type": "string",
                "description": "Coding job ID (for status or cancel actions on a specific job).",
            },
        },
        "required": ["action"],
    }

    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute a coding assistant action."""
        if not context or "user_id" not in context or "db" not in context:
            return "Error: Coding assistant requires an authenticated session."

        user_id = context["user_id"]
        db = context["db"]
        action = kwargs.get("action", "")

        session_id = context.get("session_id", "") if context else ""

        try:
            if action == "propose":
                return await self._handle_propose(db, user_id, session_id, kwargs)
            elif action == "ask_codebase":
                return await self._handle_ask_codebase(db, user_id, session_id, kwargs)
            elif action == "status":
                return await self._handle_status(db, user_id, kwargs)
            elif action == "cancel":
                return await self._handle_cancel(db, user_id, kwargs)
            else:
                return f"Error: Unknown action '{action}'. Use propose, ask_codebase, status, or cancel."
        except Exception as e:
            logger.error(f"Coding assistant error (action={action}): {e}", exc_info=True)
            return f"Error performing coding assistant action: {e}"

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_propose(
        self, db: Any, user_id: str, session_id: str, kwargs: dict
    ) -> str:
        """Create a coding task proposal. Does NOT start any work."""
        repo = kwargs.get("repo")
        task_description = kwargs.get("task_description")
        account_label = kwargs.get("account_label")

        if not repo:
            return (
                "Error: You must specify which repository to work on (repo parameter in owner/repo format). "
                "Ask the user which repo they want to work on."
            )
        if not task_description:
            return "Error: You must provide a task_description describing what to build/fix/change."

        # Validate repo format
        if "/" not in repo or repo.count("/") != 1:
            return f"Error: Invalid repo format '{repo}'. Use owner/repo format (e.g. 'myorg/myrepo')."

        from app.core.config import get_settings
        from app.db.repositories.coding_job import CodingJobRepository

        settings = get_settings()

        # Check concurrent job limit
        repo_jobs = CodingJobRepository(db)
        active_count = await repo_jobs.count_active_by_user(user_id)
        if active_count >= settings.coding_max_concurrent_jobs:
            return (
                f"Error: You already have {active_count} active coding job(s). "
                f"Maximum is {settings.coding_max_concurrent_jobs}. "
                "Cancel or wait for existing jobs to complete."
            )

        # Validate GitHub connection exists
        from app.db.repositories.oauth_token import OAuthTokenRepository

        token_repo = OAuthTokenRepository(db)
        tokens = await token_repo.get_multi(user_id=user_id, provider="github")
        if not tokens:
            return (
                "Error: No GitHub connection found. The user needs to connect their "
                "GitHub account in Settings → Integrations before using coding assistant."
            )

        # If account_label specified, verify it exists
        if account_label:
            matching = [t for t in tokens if t.account_label == account_label]
            if not matching:
                labels = [t.account_label for t in tokens]
                return (
                    f"Error: No GitHub connection with label '{account_label}'. "
                    f"Available labels: {', '.join(labels)}"
                )

        if not session_id:
            return "Error: Could not determine session ID. Please try again."

        # Create the job
        job = await repo_jobs.create_job(
            user_id=user_id,
            session_id=session_id,
            repo_full_name=repo,
            task_description=task_description,
            github_account_label=account_label,
        )

        # Store metadata for the frontend to render approval buttons
        self.last_execution_metadata = {
            "type": "coding_job_proposal",
            "job_id": job.id,
            "repo": repo,
            "task_description": task_description,
            "status": "pending_plan_approval",
        }

        return (
            f"Coding task proposal created (Job ID: {job.id}).\n"
            f"Repository: {repo}\n"
            f"Task: {task_description}\n\n"
            "Approval buttons will appear for the user to review and approve planning. "
            "You cannot start the work — only the user can approve via the buttons."
        )

    async def _handle_ask_codebase(
        self, db: Any, user_id: str, session_id: str, kwargs: dict
    ) -> str:
        """Launch a container to explore a codebase and answer a question."""
        repo = kwargs.get("repo")
        question = kwargs.get("question")
        account_label = kwargs.get("account_label")

        if not repo:
            return (
                "Error: You must specify which repository to query (repo parameter in owner/repo format). "
                "Ask the user which repo they want to explore."
            )
        if not question:
            return "Error: You must provide a question to ask about the codebase."

        if "/" not in repo or repo.count("/") != 1:
            return f"Error: Invalid repo format '{repo}'. Use owner/repo format."

        # Validate GitHub connection
        from app.db.repositories.oauth_token import OAuthTokenRepository

        token_repo = OAuthTokenRepository(db)
        tokens = await token_repo.get_multi(user_id=user_id, provider="github")
        if not tokens:
            return (
                "Error: No GitHub connection found. The user needs to connect their "
                "GitHub account in Settings → Integrations."
            )

        if not session_id:
            return "Error: Could not determine session ID."

        from app.db.repositories.coding_job import CodingJobRepository

        repo_jobs = CodingJobRepository(db)
        job = await repo_jobs.create_job(
            user_id=user_id,
            session_id=session_id,
            repo_full_name=repo,
            task_description=question,
            mode="explore",
            status="exploring",
            github_account_label=account_label,
        )

        # Launch exploration container
        try:
            from app.services.coding_job import CodingJobService

            service = CodingJobService(db)
            await service.start_exploration(job.id)
        except Exception as e:
            logger.error(f"Failed to start exploration: {e}", exc_info=True)
            # Job is created; exploration will be retried or user can cancel

        self.last_execution_metadata = {
            "type": "coding_job_exploration",
            "job_id": job.id,
            "repo": repo,
            "question": question,
            "status": "exploring",
        }

        return (
            f"Exploring the codebase at {repo} to answer your question (Job ID: {job.id}). "
            "I'll share what I find shortly."
        )

    async def _handle_status(
        self, db: Any, user_id: str, kwargs: dict
    ) -> str:
        """Check status of active coding jobs."""
        from app.db.repositories.coding_job import CodingJobRepository

        repo_jobs = CodingJobRepository(db)
        job_id = kwargs.get("job_id")

        if job_id:
            job = await repo_jobs.get(job_id)
            if not job or job.user_id != user_id:
                return f"Error: Coding job '{job_id}' not found."
            return self._format_job_status(job)

        # Show all active jobs
        active_jobs = await repo_jobs.get_active_by_user(user_id)
        if not active_jobs:
            return "No active coding jobs."

        parts = [f"Active coding jobs ({len(active_jobs)}):"]
        for job in active_jobs:
            parts.append(self._format_job_status(job))
        return "\n\n".join(parts)

    async def _handle_cancel(
        self, db: Any, user_id: str, kwargs: dict
    ) -> str:
        """Cancel an active coding job."""
        from app.db.repositories.coding_job import CodingJobRepository, TERMINAL_STATUSES

        job_id = kwargs.get("job_id")
        repo_jobs = CodingJobRepository(db)

        if job_id:
            job = await repo_jobs.get(job_id)
            if not job or job.user_id != user_id:
                return f"Error: Coding job '{job_id}' not found."
            if job.status in TERMINAL_STATUSES:
                return f"Job is already {job.status} and cannot be cancelled."

            try:
                from app.services.coding_job import CodingJobService

                service = CodingJobService(db)
                await service.cancel_job(job_id)
            except Exception as e:
                logger.warning(f"Service cancel failed, falling back: {e}")
                await repo_jobs.update_status(job, "cancelled")
            return f"Coding job {job_id} cancelled."

        # Cancel most recent active job
        active_jobs = await repo_jobs.get_active_by_user(user_id)
        if not active_jobs:
            return "No active coding jobs to cancel."
        if len(active_jobs) > 1:
            parts = ["Multiple active jobs found. Specify which to cancel:"]
            for job in active_jobs:
                parts.append(f"- Job {job.id}: {job.repo_full_name} ({job.status})")
            return "\n".join(parts)

        job = active_jobs[0]
        try:
            from app.services.coding_job import CodingJobService

            service = CodingJobService(db)
            await service.cancel_job(job.id)
        except Exception:
            await repo_jobs.update_status(job, "cancelled")
        return f"Coding job {job.id} ({job.repo_full_name}) cancelled."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_job_status(self, job: Any) -> str:
        """Format a coding job's status for display."""
        parts = [
            f"Job {job.id}:",
            f"  Repo: {job.repo_full_name}",
            f"  Status: {job.status}",
            f"  Task: {job.task_description[:200]}",
        ]
        if job.branch_name:
            parts.append(f"  Branch: {job.branch_name}")
        if job.pr_url:
            parts.append(f"  PR: {job.pr_url}")
        if job.error_details:
            parts.append(f"  Error: {job.error_details[:200]}")
        if job.plan_content:
            # Show first 500 chars of plan
            preview = job.plan_content[:500]
            if len(job.plan_content) > 500:
                preview += "..."
            parts.append(f"  Plan preview: {preview}")
        if job.review_content:
            preview = job.review_content[:500]
            if len(job.review_content) > 500:
                preview += "..."
            parts.append(f"  Review: {preview}")
        return "\n".join(parts)
