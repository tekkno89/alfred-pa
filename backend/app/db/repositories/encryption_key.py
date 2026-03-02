"""Repository for encryption key operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EncryptionKey
from app.db.repositories.base import BaseRepository


class EncryptionKeyRepository(BaseRepository[EncryptionKey]):
    """Repository for EncryptionKey CRUD operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(EncryptionKey, db)

    async def get_by_name(self, key_name: str) -> EncryptionKey | None:
        """Get an encryption key by its name."""
        result = await self.db.execute(
            select(EncryptionKey).where(EncryptionKey.key_name == key_name)
        )
        return result.scalar_one_or_none()

    async def get_active_by_name(self, key_name: str) -> EncryptionKey | None:
        """Get an active encryption key by its name."""
        result = await self.db.execute(
            select(EncryptionKey)
            .where(EncryptionKey.key_name == key_name)
            .where(EncryptionKey.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def create_key(
        self,
        key_name: str,
        encrypted_dek: bytes,
        kek_provider: str,
        kek_reference: str | None = None,
    ) -> EncryptionKey:
        """Create a new encryption key entry."""
        key = EncryptionKey(
            key_name=key_name,
            encrypted_dek=encrypted_dek,
            kek_provider=kek_provider,
            kek_reference=kek_reference,
            is_active=True,
        )
        return await self.create(key)
