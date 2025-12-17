import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, Literal

try:
    import grpc  # type: ignore
except Exception:
    grpc = None  # lazy optional

from config.config import settings

# Public DTOs

@dataclass
class CommentDTO:
    id: str
    video_id: str
    user_uid: str
    username: Optional[str]
    channel_id: Optional[str]
    parent_id: Optional[str]
    content_raw: str
    content_html: Optional[str]
    is_deleted: bool
    edited: bool
    created_at_ms: int
    updated_at_ms: int
    reply_count: int

@dataclass
class ListPage:
    items: List[CommentDTO]
    next_page_token: str
    total_count: int

SortOrder = Literal["newest_first", "oldest_first"]

@dataclass
class UserContext:
    user_uid: Optional[str] = None
    username: Optional[str] = None
    channel_id: Optional[str] = None
    is_video_owner: bool = False
    is_moderator: bool = False
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class YtCommentsClient(Protocol):
    async def list_top(
        self,
        video_id: str,
        page_size: int = 20,
        page_token: str = "",
        sort: SortOrder = "newest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage: ...

    async def list_replies(
        self,
        parent_id: str,
        page_size: int = 20,
        page_token: str = "",
        sort: SortOrder = "oldest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage: ...

    async def create(
        self,
        video_id: str,
        content_raw: str,
        parent_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO: ...

    async def edit(
        self,
        comment_id: str,
        content_raw: str,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO: ...

    async def delete(
        self,
        comment_id: str,
        hard_delete: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO: ...

    async def restore(
        self,
        comment_id: str,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO: ...

    async def get_counts(self, video_id: str, ctx: Optional[UserContext] = None) -> Dict[str, int]: ...


# Local (legacy) implementation placeholder.
# Later: wire up to existing db/comments/* utils.
class LocalMongoClient:
    def __init__(self) -> None:
        # Lazy-initialize any underlying connections if needed
        pass

    async def list_top(
        self,
        video_id: str,
        page_size: int = 20,
        page_token: str = "",
        sort: SortOrder = "newest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.list_top is not implemented yet")

    async def list_replies(
        self,
        parent_id: str,
        page_size: int = 20,
        page_token: str = "",
        sort: SortOrder = "oldest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.list_replies is not implemented yet")

    async def create(
        self,
        video_id: str,
        content_raw: str,
        parent_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.create is not implemented yet")

    async def edit(
        self,
        comment_id: str,
        content_raw: str,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.edit is not implemented yet")

    async def delete(
        self,
        comment_id: str,
        hard_delete: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.delete is not implemented yet")

    async def restore(
        self,
        comment_id: str,
        ctx: Optional[UserContext] = None,
    ) -> CommentDTO:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.restore is not implemented yet")

    async def get_counts(self, video_id: str, ctx: Optional[UserContext] = None) -> Dict[str, int]:
        # TODO: implement via db/comments/* utils
        raise NotImplementedError("LocalMongoClient.get_counts is not implemented yet")


# gRPC stub client (skeleton)
class GrpcCommentsClient:
    def __init__(self, target: str, tls_enabled: bool = False, timeout_ms: int = 3000) -> None:
        if grpc is None:
            raise RuntimeError("grpc is not installed. Install grpcio and grpcio-tools.")
        self._target = target
        self._timeout = max(1, int(timeout_ms))
        # Lazy import of generated stubs to avoid runtime errors before codegen
        # from services.ytcomments.ytcomments_proto import ytcomments_pb2, ytcomments_pb2_grpc
        self._channel = None
        self._stub = None

    async def _ensure_channel(self):
        if self._channel:
            return
        self._channel = grpc.aio.insecure_channel(self._target)  # type: ignore
        # self._stub = ytcomments_pb2_grpc.YtCommentsStub(self._channel)  # type: ignore

    async def list_top(self, *args, **kwargs) -> ListPage:
        await self._ensure_channel()
        # TODO: implement mapping between DTOs and protobuf
        raise NotImplementedError("GrpcCommentsClient.list_top not implemented yet")

    async def list_replies(self, *args, **kwargs) -> ListPage:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.list_replies not implemented yet")

    async def create(self, *args, **kwargs) -> CommentDTO:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.create not implemented yet")

    async def edit(self, *args, **kwargs) -> CommentDTO:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.edit not implemented yet")

    async def delete(self, *args, **kwargs) -> CommentDTO:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.delete not implemented yet")

    async def restore(self, *args, **kwargs) -> CommentDTO:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.restore not implemented yet")

    async def get_counts(self, *args, **kwargs) -> Dict[str, int]:
        await self._ensure_channel()
        raise NotImplementedError("GrpcCommentsClient.get_counts not implemented yet")


# Factory + caching
_client_singleton: Optional[YtCommentsClient] = None

def get_ytcomments_client() -> YtCommentsClient:
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton

    transport = (settings.YTCOMMENTS_TRANSPORT or "local").strip().lower()
    enabled = bool(settings.YTCOMMENTS_ENABLED)

    if not enabled:
        # Keep legacy DB flow outside this client; return local stub to make calls explicit where used.
        _client_singleton = LocalMongoClient()
        return _client_singleton

    if transport == "grpc":
        _client_singleton = GrpcCommentsClient(
            target=settings.YTCOMMENTS_ADDR,
            tls_enabled=bool(getattr(settings, "YTCOMMENTS_TLS_ENABLED", False)),
            timeout_ms=int(getattr(settings, "YTCOMMENTS_TIMEOUT_MS", 3000) or 3000),
        )
    else:
        _client_singleton = LocalMongoClient()

    return _client_singleton