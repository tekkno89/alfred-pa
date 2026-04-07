"""Repository registry service with Redis caching."""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.models.user_repository import UserRepo
from app.db.repositories.user_repo_registry import RepoRegistryRepository

logger = logging.getLogger(__name__)

CACHE_PREFIX = "repo_reg"
CACHE_TTL = 3600  # 1 hour


class RepoNotFoundError(Exception):
    def __init__(self, input_name: str):
        self.input_name = input_name
        super().__init__(f"Repository '{input_name}' not found in registry")


class AmbiguousRepoError(Exception):
    def __init__(self, input_name: str, matches: list[UserRepo]):
        self.input_name = input_name
        self.matches = matches
        super().__init__(
            f"Ambiguous repo '{input_name}': matches "
            + ", ".join(f"{m.owner}/{m.repo_name}" for m in matches)
        )


class RepoRegistryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RepoRegistryRepository(db)

    # ---- Resolution (with cache) ----

    async def resolve(self, user_id: str, input_name: str) -> tuple[str, str | None]:
        """Resolve a short name/alias to (full_name, github_account_label).

        Raises RepoNotFoundError or AmbiguousRepoError.
        """
        redis = await get_redis()
        cache_key = f"{CACHE_PREFIX}:{user_id}:{input_name.lower()}"

        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return data["full_name"], data["account_label"]

        result = await self.repo.resolve(user_id, input_name)

        if isinstance(result, list):
            if len(result) == 0:
                raise RepoNotFoundError(input_name)
            raise AmbiguousRepoError(input_name, result)

        # Single match — cache it
        value = {
            "full_name": result.full_name,
            "account_label": result.github_account_label,
        }
        await redis.set(cache_key, json.dumps(value), ex=CACHE_TTL)
        return result.full_name, result.github_account_label

    async def invalidate_cache(self, user_id: str) -> None:
        """Clear all cached resolutions for a user."""
        redis = await get_redis()
        pattern = f"{CACHE_PREFIX}:{user_id}:*"
        cursor = "0"
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0 or cursor == "0":
                break

    # ---- CRUD ----

    async def list_repos(self, user_id: str) -> list[UserRepo]:
        return await self.repo.get_all_by_user(user_id)

    async def add_repo(
        self,
        user_id: str,
        owner: str,
        repo_name: str,
        alias: str | None = None,
        github_account_label: str | None = None,
    ) -> UserRepo:
        if alias and await self.repo.check_alias_conflict(user_id, alias):
            raise ValueError(f"Alias '{alias}' is already in use")

        entry = UserRepo(
            user_id=user_id,
            owner=owner,
            repo_name=repo_name,
            alias=alias or None,
            github_account_label=github_account_label or None,
        )
        entry = await self.repo.create(entry)
        await self.invalidate_cache(user_id)
        return entry

    async def update_repo(
        self,
        user_id: str,
        repo_id: str,
        alias: str | None = ...,  # type: ignore[assignment]
        github_account_label: str | None = ...,  # type: ignore[assignment]
    ) -> UserRepo:
        entry = await self.repo.get_by_id_and_user(repo_id, user_id)
        if not entry:
            raise ValueError("Repository not found")

        updates: dict = {}
        if alias is not ...:
            if alias and await self.repo.check_alias_conflict(
                user_id, alias, exclude_id=repo_id
            ):
                raise ValueError(f"Alias '{alias}' is already in use")
            updates["alias"] = alias or None
        if github_account_label is not ...:
            updates["github_account_label"] = github_account_label or None

        if updates:
            entry = await self.repo.update(entry, **updates)
            await self.invalidate_cache(user_id)
        return entry

    async def remove_repo(self, user_id: str, repo_id: str) -> bool:
        deleted = await self.repo.delete_by_id_and_user(repo_id, user_id)
        if deleted:
            await self.invalidate_cache(user_id)
        return deleted
