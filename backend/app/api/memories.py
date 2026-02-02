"""Memory management API endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.embeddings import get_embedding_provider
from app.db.repositories import MemoryRepository
from app.schemas import (
    DeleteResponse,
    MemoryCreate,
    MemoryList,
    MemoryResponse,
    MemoryUpdate,
)


router = APIRouter()


@router.get("", response_model=MemoryList)
async def list_memories(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    type: Annotated[str | None, Query()] = None,
) -> MemoryList:
    """
    List memories for the current user.

    Optional filter by type: 'preference', 'knowledge', or 'summary'.
    """
    repo = MemoryRepository(db)
    skip = (page - 1) * size

    memories = await repo.get_user_memories(
        user_id=user.id,
        type=type,
        skip=skip,
        limit=size,
    )
    total = await repo.count_user_memories(user_id=user.id, type=type)

    return MemoryList(
        items=[MemoryResponse.model_validate(m) for m in memories],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    db: DbSession,
    user: CurrentUser,
) -> MemoryResponse:
    """Get a specific memory by ID."""
    repo = MemoryRepository(db)
    memory = await repo.get(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    if memory.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this memory",
        )

    return MemoryResponse.model_validate(memory)


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    memory_data: MemoryCreate,
    db: DbSession,
    user: CurrentUser,
) -> MemoryResponse:
    """
    Manually create a new memory.

    The content will be automatically embedded for semantic search.
    """
    repo = MemoryRepository(db)

    # Generate embedding for the content
    embedding_provider = get_embedding_provider()
    embedding = embedding_provider.embed(memory_data.content)

    memory = await repo.create_memory(
        user_id=user.id,
        type=memory_data.type,
        content=memory_data.content,
        embedding=embedding,
    )

    return MemoryResponse.model_validate(memory)


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    memory_data: MemoryUpdate,
    db: DbSession,
    user: CurrentUser,
) -> MemoryResponse:
    """
    Update a memory's content.

    The content will be re-embedded for semantic search.
    """
    repo = MemoryRepository(db)
    memory = await repo.get(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    if memory.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this memory",
        )

    # Re-generate embedding for the new content
    embedding_provider = get_embedding_provider()
    embedding = embedding_provider.embed(memory_data.content)

    updated_memory = await repo.update_memory(
        memory=memory,
        content=memory_data.content,
        embedding=embedding,
    )

    return MemoryResponse.model_validate(updated_memory)


@router.delete("/{memory_id}", response_model=DeleteResponse)
async def delete_memory(
    memory_id: str,
    db: DbSession,
    user: CurrentUser,
) -> DeleteResponse:
    """Delete a memory."""
    repo = MemoryRepository(db)
    memory = await repo.get(memory_id)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    if memory.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this memory",
        )

    await repo.delete(memory)
    return DeleteResponse(success=True)
