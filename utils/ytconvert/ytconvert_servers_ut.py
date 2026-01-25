from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class YtconvertServer:
    hostport: str          # "IP:PORT"
    token: Optional[str]   # token or None


def parse_servers(raw: str) -> List[YtconvertServer]:
    raw = (raw or "").strip()
    if not raw:
        return []
    out: List[YtconvertServer] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "@" in part:
            hp, tok = part.split("@", 1)
            hp = hp.strip()
            tok = tok.strip() or None
        else:
            hp, tok = part, None
        if hp:
            out.append(YtconvertServer(hostport=hp, token=tok))
    return out