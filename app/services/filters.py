from datetime import date

def parse_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None