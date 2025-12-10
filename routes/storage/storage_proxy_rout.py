from typing import AsyncIterator, Optional, Tuple
from fastapi import APIRouter, Request, Query, HTTPException, Path
from fastapi.responses import StreamingResponse
import os
import re

from services.storage.base_srv import StorageClient

router = APIRouter(prefix="/internal/storage", tags=["storage"])

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

def _content_type_for(path: str) -> str:
    low = path.lower()
    if low.endswith(".png"): return "image/png"
    if low.endswith(".jpg") or low.endswith(".jpeg"): return "image/jpeg"
    if low.endswith(".webp"): return "image/webp"
    if low.endswith(".gif"): return "image/gif"
    if low.endswith(".vtt"): return "text/vtt; charset=utf-8"
    if low.endswith(".webm"): return "video/webm"
    if low.endswith(".mp4"): return "video/mp4"
    return "application/octet-stream"

async def _get_size(storage: StorageClient, rel: str) -> Optional[int]:
    try:
        st = storage.stat(rel)
        if hasattr(st, "__await__"):  # async
            st = await st
        sz = int(st.get("size_bytes", -1))
        return sz if sz >= 0 else None
    except Exception:
        return None

def _parse_range(hval: Optional[str], size: Optional[int]) -> Optional[Tuple[int, int]]:
    """
    Parse Range: bytes=start-end. Returns (start, end) inclusive.
    Validates against total size when provided. Returns None if header missing/invalid.
    """
    if not hval:
        return None
    m = _RANGE_RE.match(hval.strip())
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        return None
    if size is None:
        # Can't validate, but return something only if start provided
        if start_s != "":
            s = int(start_s)
            e = int(end_s) if end_s != "" else s
            return (max(0, s), max(s, e))
        return None
    # With size known
    if start_s != "":
        s = max(0, int(start_s))
        e = int(end_s) if end_s != "" else (size - 1)
        e = min(e, size - 1)
        if s > e:
            return None
        return (s, e)
    else:
        # suffix range: bytes=-N
        n = int(end_s)
        if n <= 0:
            return None
        s = max(size - n, 0)
        e = size - 1
        return (s, e)

async def _stream_full(storage: StorageClient, rel: str, ct: str, size: Optional[int]) -> StreamingResponse:
    async def _aiter() -> AsyncIterator[bytes]:
        # Support both async and sync readers
        try:
            reader = await storage.open_reader(rel)  # async
            async for chunk in reader:
                if chunk:
                    yield chunk
        except TypeError:
            reader = storage.open_reader(rel)        # sync
            for chunk in reader:
                if chunk:
                    yield chunk
    headers = {}
    if size is not None:
        headers["Content-Length"] = str(size)
    headers["Accept-Ranges"] = "bytes"
    return StreamingResponse(_aiter(), media_type=ct, headers=headers, status_code=200)

async def _stream_range(storage: StorageClient, rel: str, ct: str, size: int, rng: Tuple[int, int]) -> StreamingResponse:
    start, end = rng
    length = end - start + 1

    async def _aiter() -> AsyncIterator[bytes]:
        try:
            reader = await storage.open_reader(rel, offset=start, length=length)  # async
            async for chunk in reader:
                if chunk:
                    yield chunk
        except TypeError:
            reader = storage.open_reader(rel, offset=start, length=length)        # sync
            for chunk in reader:
                if chunk:
                    yield chunk

    headers = {
        "Content-Type": ct,
        "Content-Length": str(length),
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Accept-Ranges": "bytes",
    }
    return StreamingResponse(_aiter(), media_type=ct, headers=headers, status_code=206)

async def _serve(request: Request, raw_path: str) -> StreamingResponse:
    if not raw_path:
        raise HTTPException(status_code=400, detail="missing_path")
    rel = raw_path.lstrip("/")
    storage: StorageClient = request.app.state.storage
    ct = _content_type_for(rel)

    size = await _get_size(storage, rel)
    # Parse Range if present and we know size
    rng_hdr = request.headers.get("range") or request.headers.get("Range")
    rng = _parse_range(rng_hdr, size)

    if rng and size is not None:
        return await _stream_range(storage, rel, ct, size, rng)

    # Fallback: full stream
    return await _stream_full(storage, rel, ct, size)

@router.get("/file")
async def storage_file_query(request: Request, path: str = Query(...)) -> StreamingResponse:
    """
    Form-1: /internal/storage/file?path=Fx/Fx8.../original.webm
    """
    return await _serve(request, path)

@router.get("/file/{path:path}")
async def storage_file_path(request: Request, path: str = Path(...)) -> StreamingResponse:
    """
    Form-2: /internal/storage/file/Fx/Fx8.../sprites/sprite_0001.jpg
    """
    return await _serve(request, path)