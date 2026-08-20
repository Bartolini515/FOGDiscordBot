"""Pure and ticket-local workflow helpers."""

import html
from typing import Any


def is_ticket_admin(user: Any, channel: Any) -> bool:
    """Return whether a user may manage messages in a ticket channel."""

    if user.guild_permissions.administrator:
        return True
    if channel is None:
        return False
    return channel.permissions_for(user).manage_messages


def parse_category_selection(raw_categories: str) -> list[str]:
    """Normalize the semicolon-delimited category command argument."""

    return [category.strip() for category in raw_categories.split(";") if category.strip()]


def ticket_create_custom_id(mode: str, message_id: int) -> str:
    """Build the persistent create-view custom ID used by the cog."""

    return f"ticket_create_{mode}_{message_id}"


async def generate_transcript_html(channel: Any) -> str:
    """Render a channel history using the existing transcript markup."""

    lines = [
        "<!DOCTYPE html>",
        "<html lang='pl'>",
        "<head><meta charset='UTF-8'><title>Transcript</title>",
        "<style>body{font-family:Arial, sans-serif;} .msg{margin:8px 0;} .meta{color:#666;font-size:12px;}</style>",
        "</head><body>",
        f"<h2>Transcript kanału {html.escape(channel.name)}</h2>",
    ]

    async for message in channel.history(limit=None, oldest_first=True):
        author = html.escape(message.author.display_name)
        created = message.created_at.strftime("%Y-%m-%d %H:%M")
        content = html.escape(message.content) if message.content else ""
        attachments = ""
        if message.attachments:
            links = " ".join(f"<a href='{att.url}'>{html.escape(att.filename)}</a>" for att in message.attachments)
            attachments = f"<div>Załączniki: {links}</div>"
        lines.append("<div class='msg'>")
        lines.append(f"<div class='meta'>{created} | {author}</div>")
        if content:
            lines.append(f"<div>{content}</div>")
        if attachments:
            lines.append(attachments)
        lines.append("</div>")

    lines.extend(["</body></html>"])
    return "\n".join(lines)
