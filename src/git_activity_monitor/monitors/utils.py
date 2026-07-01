from __future__ import annotations


def split_message_chunks(
    header: str,
    sections: list[str],
    max_len: int = 2000,
    cont_header: str | None = None,
) -> list[str]:
    """Split sections into Discord messages that fit within max_len characters.

    cont_header, if provided, is used for the second and subsequent chunks instead
    of repeating the full header.
    """
    if not sections:
        return [header]

    chunks: list[str] = []
    current_hdr = header
    current: list[str] = []
    current_len = len(current_hdr) + 2  # +2 for trailing "\n\n"
    # Maximum characters available for a single section in a fresh chunk
    max_section = max_len - len(header) - 3  # header + "\n\n" + section

    for section in sections:
        # Truncate sections that can never fit even alone
        if len(section) > max_section:
            section = section[: max_section - 3] + "..."

        section_len = len(section) + 1  # +1 for "\n" separator
        if current_len + section_len > max_len and current:
            chunks.append(current_hdr + "\n\n" + "\n".join(current))
            current = []
            current_hdr = cont_header if cont_header is not None else header
            current_len = len(current_hdr) + 2
        current.append(section)
        current_len += section_len

    if current:
        chunks.append(current_hdr + "\n\n" + "\n".join(current))

    return chunks
