import httpx
from typing import Optional, Dict, Any
from config.ytms_config import YTMS_BASE_URL, APP_BASE_URL, YTMS_CALLBACK_SECRET

async def create_thumbnails_job(
    video_id: str,
    src_path: Optional[str],
    out_base_path: str,
    src_url: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not src_path and not src_url:
        raise ValueError("src_path or src_url required")
    payload: Dict[str, Any] = {
        "video_id": video_id,
        "out_base_path": out_base_path,
        "callback_url": f"{APP_BASE_URL.rstrip('/')}/internal/ytms/thumbnails/callback",
        "auth_token": YTMS_CALLBACK_SECRET,
    }
    if src_path:
        payload["src_path"] = src_path
    if src_url:
        payload["src_url"] = src_url
    if extra:
        payload.update(extra)
    url = f"{YTMS_BASE_URL.rstrip('/')}/api/jobs/thumbnails"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()