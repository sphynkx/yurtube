import urllib.parse


def build_storage_url(rel_path: str | None) -> str | None:
    """
    Build an application URL for serving a file stored in ytstorage.

    NOTE:
    - local storage mode is deprecated
    - we always serve via internal proxy route: /internal/storage/file/<rel_path>
    """
    if not rel_path:
        return None
    rel = rel_path.lstrip("/")

    # Use path-form (works well for VTT and avoids query escaping issues)
    return f"/internal/storage/file/{urllib.parse.quote(rel)}"