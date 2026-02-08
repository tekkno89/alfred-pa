"""Service for managing Slack linking codes."""

import secrets
import string

from app.core.redis import get_redis

# Linking code configuration
CODE_LENGTH = 6
CODE_TTL_SECONDS = 600  # 10 minutes
CODE_PREFIX = "slack_link:"


class LinkingService:
    """Service for managing Slack account linking codes."""

    @staticmethod
    def _generate_code() -> str:
        """Generate a 6-character alphanumeric code."""
        alphabet = string.ascii_uppercase + string.digits
        # Remove confusing characters (0, O, I, 1, L)
        alphabet = alphabet.replace("0", "").replace("O", "")
        alphabet = alphabet.replace("I", "").replace("1", "").replace("L", "")
        return "".join(secrets.choice(alphabet) for _ in range(CODE_LENGTH))

    async def create_code(self, slack_user_id: str) -> str:
        """
        Create a linking code for a Slack user.

        Args:
            slack_user_id: The Slack user ID to associate with the code

        Returns:
            The generated 6-character linking code
        """
        redis_client = await get_redis()

        # Generate unique code
        code = self._generate_code()

        # Ensure code doesn't already exist (unlikely but possible)
        while await redis_client.exists(f"{CODE_PREFIX}{code}"):
            code = self._generate_code()

        # Store code -> slack_user_id mapping with TTL
        await redis_client.setex(
            f"{CODE_PREFIX}{code}",
            CODE_TTL_SECONDS,
            slack_user_id,
        )

        return code

    async def validate_code(self, code: str) -> str | None:
        """
        Validate a linking code and return the associated Slack user ID.

        Args:
            code: The linking code to validate

        Returns:
            The Slack user ID if code is valid, None if invalid/expired
        """
        redis_client = await get_redis()

        # Normalize code (uppercase, strip whitespace)
        code = code.upper().strip()

        # Get and delete atomically (code can only be used once)
        slack_user_id = await redis_client.getdel(f"{CODE_PREFIX}{code}")

        return slack_user_id


# Singleton instance
_linking_service: LinkingService | None = None


def get_linking_service() -> LinkingService:
    """Get or create LinkingService singleton."""
    global _linking_service
    if _linking_service is None:
        _linking_service = LinkingService()
    return _linking_service
