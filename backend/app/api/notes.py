"""Notes API endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories.dashboard import FeatureAccessRepository
from app.db.repositories.note import NoteRepository
from app.schemas.note import NoteCreate, NoteList, NoteResponse, NoteUpdate
from app.schemas.session import DeleteResponse

router = APIRouter()


async def _check_notes_access(user: CurrentUser, db: DbSession) -> None:
    """Check that the user has card:notes feature access."""
    if user.role == "admin":
        return
    repo = FeatureAccessRepository(db)
    if not await repo.is_enabled(user.id, "card:notes"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Notes access not enabled",
        )


@router.get("", response_model=NoteList)
async def list_notes(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 50,
    sort_by: Annotated[str, Query()] = "updated_at",
    archived: Annotated[bool, Query()] = False,
    favorited: Annotated[bool | None, Query()] = None,
) -> NoteList:
    """List notes for the current user."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    skip = (page - 1) * size

    notes = await repo.get_user_notes(
        user_id=user.id,
        archived=archived,
        favorited=favorited,
        skip=skip,
        limit=size,
        sort_by=sort_by,
    )
    total = await repo.count_user_notes(
        user_id=user.id,
        archived=archived,
        favorited=favorited,
    )

    return NoteList(
        items=[NoteResponse.model_validate(n) for n in notes],
        total=total,
        page=page,
        size=size,
    )


@router.get("/recent", response_model=list[NoteResponse])
async def get_recent_notes(
    db: DbSession,
    user: CurrentUser,
) -> list[NoteResponse]:
    """Get 5 most recent non-archived notes (for dashboard card)."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    notes = await repo.get_recent_notes(user_id=user.id, limit=5)
    return [NoteResponse.model_validate(n) for n in notes]


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    db: DbSession,
    user: CurrentUser,
) -> NoteResponse:
    """Get a specific note by ID."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.get(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    if note.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this note",
        )

    return NoteResponse.model_validate(note)


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    note_data: NoteCreate,
    db: DbSession,
    user: CurrentUser,
) -> NoteResponse:
    """Create a new note."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.create_note(
        user_id=user.id,
        title=note_data.title,
        body=note_data.body,
        is_favorited=note_data.is_favorited,
        tags=note_data.tags,
    )

    return NoteResponse.model_validate(note)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    note_data: NoteUpdate,
    db: DbSession,
    user: CurrentUser,
) -> NoteResponse:
    """Update a note's title, body, or favorite status."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.get(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    if note.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this note",
        )

    updates = note_data.model_dump(exclude_none=True)
    if updates:
        note = await repo.update_note(note, **updates)

    return NoteResponse.model_validate(note)


@router.patch("/{note_id}/archive", response_model=NoteResponse)
async def archive_note(
    note_id: str,
    db: DbSession,
    user: CurrentUser,
) -> NoteResponse:
    """Archive a note."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.get(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    if note.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to archive this note",
        )

    note = await repo.update_note(note, is_archived=True)
    return NoteResponse.model_validate(note)


@router.patch("/{note_id}/restore", response_model=NoteResponse)
async def restore_note(
    note_id: str,
    db: DbSession,
    user: CurrentUser,
) -> NoteResponse:
    """Restore an archived note."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.get(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    if note.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to restore this note",
        )

    note = await repo.update_note(note, is_archived=False)
    return NoteResponse.model_validate(note)


@router.delete("/{note_id}", response_model=DeleteResponse)
async def delete_note(
    note_id: str,
    db: DbSession,
    user: CurrentUser,
) -> DeleteResponse:
    """Permanently delete a note."""
    await _check_notes_access(user, db)

    repo = NoteRepository(db)
    note = await repo.get(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    if note.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this note",
        )

    await repo.delete(note)
    return DeleteResponse(success=True)
