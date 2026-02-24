"""System-wide settings model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SystemSetting(Base, TimestampMixin):
    """Key-value store for system-wide settings controlled by admins."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(
        String(100), primary_key=True, nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<SystemSetting(key={self.key}, value={self.value})>"
