from datetime import datetime

_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y")


def normalise_date(text: str) -> str | None:
    """Return an ISO date, or None if the text is not a date we understand."""
    text = (text or "").strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None
