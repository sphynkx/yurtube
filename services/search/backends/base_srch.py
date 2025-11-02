from typing import Any, Dict, List, Protocol

class BaseSearchBackend(Protocol):
    async def search_videos(self, q: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        ...

    async def suggest_titles(self, prefix: str, limit: int = 10) -> List[Dict[str, Any]]:
        ...

    async def index_video(self, video: Dict[str, Any]) -> None:
        ...

    async def delete_video(self, video_id: str) -> None:
        ...