from __future__ import annotations


def split_message_chunks(header: str, sections: list[str], max_len: int = 2000) -> list[str]:
    """Split sections into Discord messages that fit within max_len characters."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = len(header) + 2  # +2 for trailing "\n\n"

    for section in sections:
        section_len = len(section) + 1  # +1 for "\n" separator
        if current_len + section_len > max_len and current:
            chunks.append(header + "\n\n" + "\n".join(current))
            current = []
            current_len = len(header) + 2
        current.append(section)
        current_len += section_len

    if current:
        chunks.append(header + "\n\n" + "\n".join(current))

    return chunks
