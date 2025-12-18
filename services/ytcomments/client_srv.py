import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal
import logging

from config.config import settings

log = logging.getLogger("ytcomments_client")

try:
    import grpc
    from services.ytcomments import ytcomments_pb2 as pb
    from services.ytcomments import ytcomments_pb2_grpc as pbg
    log.info("client: gRPC stubs imported from services.ytcomments")
    print("ytcomments_client: stubs imported from services.ytcomments")
except Exception as e:
    grpc = None
    pb = None
    pbg = None
    log.error("client: stubs import failed: %s", e)
    print(f"ytcomments_client: stubs import failed: {e}")


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


class GrpcCommentsClient:
    def __init__(self, target: str, timeout_ms: int = 3000, tls_enabled: bool = False) -> None:
        self._target = target
        self._timeout = max(1, int(timeout_ms))
        self._tls_enabled = bool(tls_enabled)
        self._channel = None
        self._stub = None

    async def _ensure(self):
        if grpc is None or pb is None or pbg is None:
            raise RuntimeError("ytcomments gRPC stubs not available")
        if self._channel and self._stub:
            return
        if self._tls_enabled:
            creds = grpc.ssl_channel_credentials()  # type: ignore
            self._channel = grpc.aio.secure_channel(self._target, creds)  # type: ignore
        else:
            self._channel = grpc.aio.insecure_channel(self._target)  # type: ignore
        self._stub = pbg.YtCommentsStub(self._channel)  # type: ignore
        log.info("client: channel opened to %s", self._target)
        print(f"ytcomments_client: channel opened to {self._target}")

    def _to_pb_sort(self, sort: SortOrder) -> int:
        if pb is None:
            return 0
        return pb.NEWEST_FIRST if sort == "newest_first" else pb.OLDEST_FIRST

    def _ctx_to_pb(self, ctx: Optional[UserContext]):
        if pb is None:
            return None
        ctx = ctx or UserContext()
        return pb.UserContext(
            user_uid=ctx.user_uid or "",
            username=ctx.username or "",
            channel_id=ctx.channel_id or "",
            is_video_owner=bool(ctx.is_video_owner),
            is_moderator=bool(ctx.is_moderator),
            ip=ctx.ip or "",
            user_agent=ctx.user_agent or "",
        )

    def _to_dto(self, c) -> CommentDTO:
        return CommentDTO(
            id=c.id,
            video_id=c.video_id,
            user_uid=c.user_uid,
            username=c.username or None,
            channel_id=c.channel_id or None,
            parent_id=(c.parent_id or None) if getattr(c, "parent_id", "") else None,
            content_raw=c.content_raw or "",
            content_html=c.content_html or None,
            is_deleted=bool(c.is_deleted),
            edited=bool(c.edited),
            created_at_ms=int(c.created_at),
            updated_at_ms=int(c.updated_at),
            reply_count=int(c.reply_count),
        )

    async def list_top(
        self,
        video_id: str,
        page_size: int = 20,
        page_token: str = "",
        sort: SortOrder = "newest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage:
        try:
            await self._ensure()
        except Exception as e:
            print(f"ytcomments_client: ensure failed in list_top: {e}")
            return ListPage(items=[], next_page_token="", total_count=0)
        req = pb.ListTopRequest(  # type: ignore
            video_id=video_id,
            page_size=int(page_size),
            page_token=page_token or "",
            sort=self._to_pb_sort(sort),
            include_deleted=bool(include_deleted),
            ctx=self._ctx_to_pb(ctx),
        )
        try:
            print("ytcomments_client: invoking ListTop")
            res = await asyncio.wait_for(self._stub.ListTop(req), timeout=self._timeout / 1000.0)  # type: ignore
        except Exception as e:
            print(f"ytcomments_client: ListTop failed: {e}")
            return ListPage(items=[], next_page_token="", total_count=0)
        items = [self._to_dto(c) for c in res.items]
        return ListPage(items=items, next_page_token=res.next_page_token or "", total_count=int(res.total_count))

    async def list_replies(
        self,
        parent_id: str,
        page_size: int = 50,
        page_token: str = "",
        sort: SortOrder = "oldest_first",
        include_deleted: bool = False,
        ctx: Optional[UserContext] = None,
    ) -> ListPage:
        try:
            await self._ensure()
        except Exception as e:
            print(f"ytcomments_client: ensure failed in list_replies: {e}")
            return ListPage(items=[], next_page_token="", total_count=0)
        req = pb.ListRepliesRequest(  # type: ignore
            parent_id=parent_id,
            page_size=int(page_size),
            page_token=page_token or "",
            sort=self._to_pb_sort(sort),
            include_deleted=bool(include_deleted),
            ctx=self._ctx_to_pb(ctx),
        )
        try:
            print("ytcomments_client: invoking ListReplies")
            res = await asyncio.wait_for(self._stub.ListReplies(req), timeout=self._timeout / 1000.0)  # type: ignore
        except Exception as e:
            print(f"ytcomments_client: ListReplies failed: {e}")
            return ListPage(items=[], next_page_token="", total_count=0)
        items = [self._to_dto(c) for c in res.items]
        return ListPage(items=items, next_page_token=res.next_page_token or "", total_count=int(res.total_count))

    async def get_counts(self, video_id: str, ctx: Optional[UserContext] = None) -> Dict[str, int]:
        try:
            await self._ensure()
        except Exception as e:
            print(f"ytcomments_client: ensure failed in get_counts: {e}")
            return {"top_level_count": 0, "total_count": 0}
        req = pb.GetCountsRequest(video_id=video_id, ctx=self._ctx_to_pb(ctx))  # type: ignore
        try:
            print("ytcomments_client: invoking GetCounts")
            res = await asyncio.wait_for(self._stub.GetCounts(req), timeout=self._timeout / 1000.0)  # type: ignore
        except Exception as e:
            print(f"ytcomments_client: GetCounts failed: {e}")
            return {"top_level_count": 0, "total_count": 0}
        return {"top_level_count": int(res.top_level_count), "total_count": int(res.total_count)}


_client_singleton: Optional[GrpcCommentsClient] = None

def get_ytcomments_client() -> GrpcCommentsClient:
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    if not bool(getattr(settings, "YTCOMMENTS_ENABLED", False)):
        raise RuntimeError("YTCOMMENTS_ENABLED is false; ytcomments client disabled")
    transport = (getattr(settings, "YTCOMMENTS_TRANSPORT", "grpc") or "grpc").strip().lower()
    if transport != "grpc":
        raise RuntimeError(f"Unsupported transport for ytcomments: {transport}")
    _client_singleton = GrpcCommentsClient(
        target=getattr(settings, "YTCOMMENTS_ADDR", "127.0.0.1:9093"),
        timeout_ms=int(getattr(settings, "YTCOMMENTS_TIMEOUT_MS", 3000) or 3000),
        tls_enabled=bool(getattr(settings, "YTCOMMENTS_TLS_ENABLED", False)),
    )
    print(f"ytcomments_client: singleton created, target={getattr(settings, 'YTCOMMENTS_ADDR', '127.0.0.1:9093')}")
    return _client_singleton