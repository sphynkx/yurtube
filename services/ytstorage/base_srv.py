from __future__ import annotations
from typing import Optional, Iterable, BinaryIO, Protocol, Tuple


class StorageError(Exception):
    pass


class StorageClient(Protocol):
    """
    Contract for work with storage
    Rel paths to logical storage root (storage/) - w/o leading '/').
    """

    def join(self, *parts: str) -> str: ...
    def norm(self, rel_path: str) -> str: ...

    # CRUD
    def exists(self, rel_path: str) -> bool: ...
    def stat(self, rel_path: str) -> Tuple[int, float]: ...
    def listdir(self, rel_dir: str) -> Iterable[str]: ...
    def mkdirs(self, rel_dir: str, exist_ok: bool = True) -> None: ...
    async def remove(self, rel_path: str) -> None: ...
    def rename(self, rel_src: str, rel_dst: str) -> None: ...

    # Read/Write
    def read_bytes(self, rel_path: str) -> bytes: ...
    def write_bytes(self, rel_path: str, data: bytes, overwrite: bool = True) -> None: ...
    def open_reader(self, rel_path: str) -> BinaryIO: ...
    def open_writer(self, rel_path: str, overwrite: bool = True) -> BinaryIO: ...

    # Abs path (for local client only)
    def to_abs(self, rel_path: str) -> str: ...


def ensure_rel_path(rel_path: str) -> str:
    """
    Normalize rel paths:
    - replaces '\' -> '/'
    - removes leading '/'
    """
    p = (rel_path or "").replace("\\", "/")
    if p.startswith("/"):
        p = p[1:]
    return p