"""
Internal storage diagnostics routes (optional).
- GET /internal/storage/health
- GET /internal/storage/stat?path=...
Avoid conflict with static /storage by using /internal/storage prefix.
"""
from typing import Any
import inspect
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/internal/storage", tags=["storage"])

@router.get("/health")
async def storage_health(request: Request) -> Any:
    storage = request.app.state.storage
    try:
        fn = getattr(storage, "health", None)
        if callable(fn):
            res = fn()
            if inspect.isawaitable(res):
                res = await res
            return JSONResponse({"ok": True, "health": res})
        return JSONResponse({"ok": True, "health": {"status": "local"}})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.get("/stat")
async def storage_stat(request: Request, path: str = Query(...)) -> Any:
    storage = request.app.state.storage
    try:
        fn = getattr(storage, "stat", None)
        if callable(fn):
            res = fn(path)
            if inspect.isawaitable(res):
                res = await res
            return JSONResponse({"ok": True, "stat": res})
        return JSONResponse({"ok": False, "error": "stat not supported"}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)