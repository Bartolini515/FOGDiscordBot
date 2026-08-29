"""Helpers for checking the database dependency exposed by the bot."""

def has_database(bot: object) -> bool:
    """Return whether ``bot`` exposes a non-null database object.

    This intentionally mirrors the existing cog checks.  It does not inspect
    the database connection itself so callers retain their current behavior.
    """

    return hasattr(bot, "db") and getattr(bot, "db", None) is not None
