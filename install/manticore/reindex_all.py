import sys
from pathlib import Path
import asyncio
from typing import List, Dict, Any

'''
Force reindex manticore DB. Usage:
source ../../.venv/bin/activate
python3 reindex_all.py
deactivate
'''

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import get_conn, release_conn  # noqa: E402
from services.search.indexer_srch import reindex_video  # noqa: E402


async def _fetch_all_ids(conn) -> List[str]:
    rows = await conn.fetch("SELECT video_id FROM videos ORDER BY created_at ASC")
    return [r["video_id"] for r in rows]


async def main() -> None:
    conn = await get_conn()
    try:
        ids = await _fetch_all_ids(conn)
    finally:
        await release_conn(conn)

    print(f"Reindexing {len(ids)} videos...")
    ok_cnt = 0
    for i, vid in enumerate(ids, 1):
        ok, msg = await reindex_video(vid)
        if not ok:
            print(f"[{i}/{len(ids)}] FAIL {vid}: {msg}")
        else:
            if i % 200 == 0:
                print(f"[{i}/{len(ids)}] ok...")
            ok_cnt += 1
    print(f"Done. OK={ok_cnt}, TOTAL={len(ids)}")


if __name__ == "__main__":
    asyncio.run(main())