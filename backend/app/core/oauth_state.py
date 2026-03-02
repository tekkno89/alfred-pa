"""Shared OAuth state store for CSRF protection across OAuth flows."""

import time

# State token -> {user_id, account_label, created_at}
_oauth_states: dict[str, dict] = {}

# State tokens expire after 10 minutes
_STATE_TTL_SECONDS = 600


def store_oauth_state(
    state: str,
    user_id: str,
    account_label: str = "default",
    app_config_id: str | None = None,
) -> None:
    """Store an OAuth state token."""
    _cleanup_expired()
    _oauth_states[state] = {
        "user_id": user_id,
        "account_label": account_label,
        "app_config_id": app_config_id,
        "created_at": time.monotonic(),
    }


def consume_oauth_state(state: str) -> dict | None:
    """Consume and return the OAuth state data, or None if invalid/expired.

    Returns dict with user_id and account_label if valid.
    """
    _cleanup_expired()
    data = _oauth_states.pop(state, None)
    if not data:
        return None
    if time.monotonic() - data["created_at"] > _STATE_TTL_SECONDS:
        return None
    return data


def _cleanup_expired() -> None:
    """Remove expired state entries."""
    now = time.monotonic()
    expired = [
        k
        for k, v in _oauth_states.items()
        if now - v["created_at"] > _STATE_TTL_SECONDS
    ]
    for k in expired:
        del _oauth_states[k]
