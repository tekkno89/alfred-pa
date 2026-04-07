"""User repository registry API."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.schemas.user_repository import (
    UserRepoCreate,
    UserRepoList,
    UserRepoResponse,
    UserRepoUpdate,
)
from app.services.repo_registry import RepoRegistryService

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
