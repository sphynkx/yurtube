import urllib.parse
from config.storage.storage_remote_cfg import STORAGE_PROVIDER
from config.storage.storage_cfg import STORAGE_PUBLIC_BASE_URL

def build_storage_url(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    rel = rel_path.lstrip("/")
    provider = (STORAGE_PROVIDER or "").strip().lower()

    if provider == "remote":
        # Serve via proxy route (FastAPI), which uses RemoteStorageClient
        q = urllib.parse.urlencode({"path": rel})
        #return f"/internal/storage/file?{q}"
        # Use path-form - for VTT
        return f"/internal/storage/file/{urllib.parse.quote(rel)}"
        
    # local: use public base if provided, else default to /storage
    base = (STORAGE_PUBLIC_BASE_URL or "").strip()
    if base:
        return f"{base.rstrip('/')}/{rel}"
    return f"/storage/{rel}"