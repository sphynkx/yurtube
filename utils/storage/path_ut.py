# Helper for storage mech. Instead of deprecated..

def build_video_storage_rel(video_id: str) -> str:
    """
    Returns rel path to video dir:
    ab/abc123456789
    """
    prefix = (video_id or "")[:2]
    return f"{prefix}/{video_id}"


def join_rel(*parts: str) -> str:
    """
    Combine rel paths and normalize.
    """
    norm = []
    for p in parts:
        if not p:
            continue
        s = str(p).replace("\\", "/").strip("/")
        if s:
            norm.append(s)
    return "/".join(norm)