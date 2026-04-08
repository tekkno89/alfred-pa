"""User repository registry API."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.schemas.user_repository import (
    UserRepoCreate,
    UserRepoList,
    UserRepoResponse,
    UserRepoUpdate,
)
from app.services.repo_registry import RepoRegistryService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=UserRepoList)
async def list_user_repos(
    db: DbSession,
    user: CurrentUser,
) -> UserRepoList:
    """List all registered repositories for the current user."""
    service = RepoRegistryService(db)
    repos = await service.list_repos(user.id)
    return UserRepoList(
        items=[UserRepoResponse.model_validate(r) for r in repos],
        total=len(repos),
    )


@router.post("", response_model=UserRepoResponse, status_code=status.HTTP_201_CREATED)
async def add_user_repo(
    data: UserRepoCreate,
    db: DbSession,
    user: CurrentUser,
) -> UserRepoResponse:
    """Register a new repository."""
    service = RepoRegistryService(db)
    try:
        entry = await service.add_repo(
            user_id=user.id,
            owner=data.owner,
            repo_name=data.repo_name,
            alias=data.alias,
            github_account_label=data.github_account_label,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This repository is already registered",
        )
    return UserRepoResponse.model_validate(entry)


# --- Available repos + import (must come BEFORE /{repo_id} routes) ---


class AvailableRepo(BaseModel):
    owner: str
    repo_name: str
    full_name: str
    private: bool
    account_label: str
    already_registered: bool
    permissions: dict[str, str]
    permission_source: str  # "app" | "pat" | "oauth"


class AvailableRepoList(BaseModel):
    items: list[AvailableRepo]


@router.get("/available", response_model=AvailableRepoList)
async def list_available_repos(
    db: DbSession,
    user: CurrentUser,
) -> AvailableRepoList:
    """List repos accessible via GitHub App installations.

    Returns repos the user's GitHub connections can access,
    with a flag indicating which are already registered.
    """
    from app.services.github import GitHubService

    github_service = GitHubService(db)
    try:
        gh_repos = await github_service.get_accessible_repos(user.id)
    except Exception as e:
        logger.warning(f"Failed to fetch available repos: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch repos from GitHub",
        )

    # Get already-registered repos for comparison
    registry = RepoRegistryService(db)
    registered = await registry.list_repos(user.id)
    registered_set = {f"{r.owner}/{r.repo_name}".lower() for r in registered}

    items = [
        AvailableRepo(
            owner=r["owner"],
            repo_name=r["repo_name"],
            full_name=r["full_name"],
            private=r["private"],
            account_label=r["account_label"],
            already_registered=r["full_name"].lower() in registered_set,
            permissions=r.get("permissions", {}),
            permission_source=r.get("permission_source", "unknown"),
        )
        for r in gh_repos
    ]

    return AvailableRepoList(items=items)


class BulkImportRequest(BaseModel):
    repos: list[UserRepoCreate]


class BulkImportResponse(BaseModel):
    imported: int
    skipped: int


@router.post("/import", response_model=BulkImportResponse)
async def bulk_import_repos(
    data: BulkImportRequest,
    db: DbSession,
    user: CurrentUser,
) -> BulkImportResponse:
    """Bulk-import repos from GitHub into the registry."""
    service = RepoRegistryService(db)
    imported = 0
    skipped = 0

    for repo in data.repos:
        try:
            await service.add_repo(
                user_id=user.id,
                owner=repo.owner,
                repo_name=repo.repo_name,
                alias=repo.alias,
                github_account_label=repo.github_account_label,
            )
            imported += 1
        except (ValueError, IntegrityError):
            skipped += 1

    return BulkImportResponse(imported=imported, skipped=skipped)


# --- Single-repo operations (parameterized routes) ---


@router.put("/{repo_id}", response_model=UserRepoResponse)
async def update_user_repo(
    repo_id: str,
    data: UserRepoUpdate,
    db: DbSession,
    user: CurrentUser,
) -> UserRepoResponse:
    """Update a registered repository (alias or account label)."""
    service = RepoRegistryService(db)
    try:
        entry = await service.update_repo(
            user_id=user.id,
            repo_id=repo_id,
            alias=data.alias,
            github_account_label=data.github_account_label,
        )
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=detail)
    return UserRepoResponse.model_validate(entry)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_repo(
    repo_id: str,
    db: DbSession,
    user: CurrentUser,
) -> None:
    """Remove a registered repository."""
    service = RepoRegistryService(db)
    deleted = await service.remove_repo(user.id, repo_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
