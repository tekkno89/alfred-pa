"""Admin API endpoints."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.db.models import User
from app.db.repositories.dashboard import FeatureAccessRepository
from app.schemas.dashboard import (
    AdminUserList,
    AdminUserResponse,
    FeatureAccessResponse,
    FeatureAccessUpdate,
    RoleUpdate,
)

router = APIRouter()


@router.get("/users", response_model=AdminUserList)
async def list_users(
    admin: AdminUser,
    db: DbSession,
) -> AdminUserList:
    """List all users with roles."""
    result = await db.execute(select(User).order_by(User.created_at))
    users = list(result.scalars().all())
    return AdminUserList(
        items=[AdminUserResponse.model_validate(u) for u in users]
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role(
    user_id: str,
    data: RoleUpdate,
    admin: AdminUser,
    db: DbSession,
) -> AdminUserResponse:
    """Change a user's role."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user.role = data.role
    await db.flush()
    await db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.get("/users/{user_id}/features", response_model=list[FeatureAccessResponse])
async def list_user_features(
    user_id: str,
    admin: AdminUser,
    db: DbSession,
) -> list[FeatureAccessResponse]:
    """List feature access for a user."""
    repo = FeatureAccessRepository(db)
    entries = await repo.get_all_for_user(user_id)
    return [FeatureAccessResponse.model_validate(e) for e in entries]


@router.put(
    "/users/{user_id}/features/{feature_key}",
    response_model=FeatureAccessResponse,
)
async def set_feature_access(
    user_id: str,
    feature_key: str,
    data: FeatureAccessUpdate,
    admin: AdminUser,
    db: DbSession,
) -> FeatureAccessResponse:
    """Set feature access for a user."""
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    repo = FeatureAccessRepository(db)
    access = await repo.set_access(user_id, feature_key, data.enabled, admin.id)
    return FeatureAccessResponse.model_validate(access)


@router.delete(
    "/users/{user_id}/features/{feature_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feature_access(
    user_id: str,
    feature_key: str,
    admin: AdminUser,
    db: DbSession,
) -> None:
    """Remove a feature access override for a user."""
    repo = FeatureAccessRepository(db)
    deleted = await repo.delete_access(user_id, feature_key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature access not found",
        )
