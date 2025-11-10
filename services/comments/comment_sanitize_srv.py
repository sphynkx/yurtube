import re
from typing import List, Tuple
from config.comments_config import comments_settings

URL_RE = re.compile(r"https?://", re.I)
TIME_LINK_RE = re.compile(r"#t=(\d+)", re.I)


def sanitize_comment(raw: str) -> Tuple[str, List[str]]:
    errors: List[str] = []
    text = (raw or "").strip()

    if len(text) > comments_settings.COMMENT_MAX_LEN:
        errors.append("too_long")

    if URL_RE.search(text):
        errors.append("contains_url")

    if not comments_settings.COMMENTS_ALLOW_TIME_LINKS and TIME_LINK_RE.search(text):
        errors.append("time_link_forbidden")

    if comments_settings.COMMENTS_STOP_WORDS:
        lowered = text.lower()
        for w in comments_settings.COMMENTS_STOP_WORDS:
            if w and w in lowered:
                errors.append(f"stop_word:{w}")

    # Min.escaping
    safe = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
    )

    return safe, errors