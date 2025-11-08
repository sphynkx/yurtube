def sanitize_username_base(display_name: str | None, email_fallback: str | None) -> str:
    """
    Produce a safe base string from display name or email local-part:
    - Trim
    - Replace spaces with hyphen
    - Keep only alnum + . _ -
    - Ensure non-empty
    - Truncate to 30 chars
    """
    src = (display_name or (email_fallback.split("@", 1)[0] if email_fallback else "") or "user").strip()
    src = src.replace(" ", "-")
    allowed = []
    for ch in src:
        if ch.isalnum() or ch in "._-":
            allowed.append(ch)
    cleaned = "".join(allowed) or "user"
    return cleaned[:30]