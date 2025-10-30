import os
import shutil


def build_video_storage_dir(root: str, video_id: str) -> str:
    """
    Returns absolute path like: {root}/ab/abc123456789/
    """
    prefix = video_id[:2]
    return os.path.join(root, prefix, video_id)


def safe_remove_storage_relpath(root: str, rel_path: str) -> bool:
    """
    Remove directory at STORAGE_ROOT/rel_path safely if it exists.
    Ensures we do not traverse outside storage root.
    Returns True if removed, False otherwise.
    """
    root_real = os.path.realpath(root)
    target = os.path.join(root, rel_path)
    target_real = os.path.realpath(target)

    if target_real == root_real:
        return False
    if not target_real.startswith(root_real + os.sep):
        return False

    if os.path.isdir(target_real):
        shutil.rmtree(target_real, ignore_errors=True)
        return True
    return False