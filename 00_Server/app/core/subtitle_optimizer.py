"""Basic SRT normalization before AI Chinese subtitle optimization."""


def preprocess_srt(entries: list) -> tuple:
    """Normalize whitespace and line breaks while retaining original timing."""
    corrections = []

    for entry in entries:
        original_text = entry.text
        entry.text = entry.text.strip()
        entry.text = entry.text.replace("\r\n", "\n").replace("\r", "\n")
        entry.text = "\n".join(
            line.strip() for line in entry.text.split("\n") if line.strip()
        )
        if entry.text != original_text:
            corrections.append({
                "index": entry.index,
                "original": original_text,
                "corrected": entry.text,
            })

    return entries, corrections
