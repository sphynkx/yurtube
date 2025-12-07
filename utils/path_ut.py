import os
import shutil


def build_video_storage_dir(root: str, video_id: str) -> str:
    """
    Returns absolute path like: {root}/ab/abc123456789/
    NOTE: Deprecated in routes after migration to StorageClient.
    Prefer using utils.storage.path_ut.build_video_storage_rel(video_id)
    and StorageClient.join()/to_abs() for absolute paths.
    """
    prefix = video_id[:2]
    return os.path.join(root, prefix, video_id)


def build_user_storage_dir(root: str, user_uid: str) -> str:
    """
    Returns absolute path like: {root}/users/{user_uid}/
    NOTE: Deprecated in routes after migration to StorageClient.
    Prefer using relative path f"{user_uid[:2]}/{user_uid}" and StorageClient.to_abs().
    """
    return os.path.join(root, "users", user_uid)


def safe_remove_storage_relpath(root: str, rel_path: str) -> bool:
    """
    Remove directory at APP_STORAGE_FS_ROOT/rel_path safely if it exists.
    Ensures we do not traverse outside storage root.
    Returns True if removed, False otherwise.

    Usage with StorageClient:
      abs_root = storage_client.to_abs("")
      safe_remove_storage_relpath(abs_root, rel_user_dir)
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