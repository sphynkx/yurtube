from typing import Optional
import asyncpg
from utils.idgen_ut import gen_id

async def username_exists(conn: asyncpg.Connection, uname: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM users WHERE lower(username)=lower($1) LIMIT 1",
        uname,
    )
    return bool(row)

async def generate_unique_username(conn: asyncpg.Connection, base: str) -> str:
    """
    Try base; then -g1..-g9; then random suffixed variants; finally fallback.
    All limited to 30 chars.
    """
    if not await username_exists(conn, base):
        return base
    for i in range(1, 10):
        candidate = f"{base}-g{i}"
        if len(candidate) > 30:
            candidate = candidate[:30]
        if not await username_exists(conn, candidate):
            return candidate
    for _ in range(20):
        cand = f"{base}-g{gen_id(4)}"
        if len(cand) > 30:
            cand = cand[:30]
        if not await username_exists(conn, cand):
            return cand
    return f"user-{gen_id(6)}"