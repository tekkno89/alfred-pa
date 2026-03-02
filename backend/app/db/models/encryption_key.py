"""Encryption key model for storing encrypted DEKs."""

from sqlalchemy import Boolean, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class EncryptionKey(Base, UUIDMixin, TimestampMixin):
    """Encrypted DEK (Data Encryption Key) storage."""

    __tablename__ = "encryption_keys"

    key_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    kek_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<EncryptionKey(key_name={self.key_name}, provider={self.kek_provider})>"
