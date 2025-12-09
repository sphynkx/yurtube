from typing import AsyncIterator
from fastapi import APIRouter, Request, Query, HTTPException, Path
from fastapi.responses import StreamingResponse
import os

from services.storage.base_srv import StorageClient

router = APIRouter(prefix="/internal/storage", tags=["storage"])

async def _stream_from_storage(storage: StorageClient, rel_path: str) -> StreamingResponse:
    rel = rel_path.lstrip("/")

    async def _aiter() -> AsyncIterator[bytes]:
        # Поддержка async и sync reader'ов
        try:
            reader = await storage.open_reader(rel)  # async версия (remote)
            async for chunk in reader:
                if chunk:
                    yield chunk
        except TypeError:
            reader = storage.open_reader(rel)        # sync версия (local)
            for chunk in reader:
                if chunk:
                    yield chunk

    # Контент-тайпы (минимум)
    ct = "application/octet-stream"
    low = rel.lower()
    if low.endswith(".png"): ct = "image/png"
    elif low.endswith(".jpg") or low.endswith(".jpeg"): ct = "image/jpeg"
    elif low.endswith(".webp"): ct = "image/webp"
    elif low.endswith(".gif"): ct = "image/gif"
    elif low.endswith(".vtt"): ct = "text/vtt; charset=utf-8"
    elif low.endswith(".webm"): ct = "video/webm"

    return StreamingResponse(_aiter(), media_type=ct)

@router.get("/file")
async def storage_file_query(request: Request, path: str = Query(...)) -> StreamingResponse:
    """
    Вариант 1: /internal/storage/file?path=Fx/Fx8.../sprites.vtt
    """
    if not path:
        raise HTTPException(status_code=400, detail="missing_path")
    storage: StorageClient = request.app.state.storage
    return await _stream_from_storage(storage, path)

@router.get("/file/{path:path}")
async def storage_file_path(request: Request, path: str = Path(...)) -> StreamingResponse:
    """
    Вариант 2 (для относительных ссылок из VTT): /internal/storage/file/Fx/Fx8.../sprites/sprite_0001.jpg
    """
    if not path:
        raise HTTPException(status_code=400, detail="missing_path")
    storage: StorageClient = request.app.state.storage
    return await _stream_from_storage(storage, path)