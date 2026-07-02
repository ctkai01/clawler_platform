from __future__ import annotations

import unicodedata


def fold(text: str | None) -> str:
    """Normalize text for keyword/entity matching: NFC + lowercase."""
    return unicodedata.normalize("NFC", text or "").lower()
