import os


def build_video_storage_dir(root: str, video_id: str) -> str:
    """
    Returns absolute path like: {root}/ab/abc123/
    """
    prefix = video_id[:2]
    return os.path.join(root, prefix, video_id)