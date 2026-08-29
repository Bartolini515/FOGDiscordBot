"""Text formatting helpers for Discord message limits."""


def split_response(content: str, limit: int = 2_000) -> list[str]:
    """Split newline-delimited content without exceeding ``limit`` characters."""

    chunks: list[str] = []
    current = ""
    for line in content.splitlines() or [""]:
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = line
    if current or not chunks:
        chunks.append(current)
    return chunks
