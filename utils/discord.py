"""Pure helpers for Discord-shaped input and permission values."""


def parse_user_mentions(value: str | None) -> list[str]:
    """Extract mention payloads using the bot's existing token semantics."""

    if not value:
        return []
    return [token[2:-1] for token in value.split() if token.startswith("<@") and token.endswith(">")]
