from datetime import datetime
from typing import Optional


def fmt_dt(value: Optional[datetime]) -> str:
    """
    Format datetime as 'YYYY-MM-DD HH:MM'. If value is None, return empty string.
    The input is expected to be timezone-aware (UTC) or naive UTC from DB.
    """
    if not value:
        return ""
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)