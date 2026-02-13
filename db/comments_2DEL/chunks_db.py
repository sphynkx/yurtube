from bson import ObjectId
from typing import Any, Dict
from .mongo_conn import chunk_coll, root_coll
from utils.comments.size_ut import text_size_bytes


async def create_chunk(video_id: str) -> ObjectId:
    doc = {
        "video_id": video_id,
        "texts": {},          # local_id -> text
        "approx_size": 0,     # bytes
        "schema_version": 1
    }
    res = await chunk_coll().insert_one(doc)
    chunk_id = res.inserted_id
    await root_coll().update_one(
        {"video_id": video_id},
        {"$push": {"chunks": {"chunk_id": chunk_id, "count": 0, "approx_size": 0}}}
    )
    return chunk_id


async def append_text(video_id: str, chunk_id: ObjectId, local_id: str, text: str):
    sz = text_size_bytes(text)
    # Refresh chunk
    await chunk_coll().update_one(
        {"_id": chunk_id},
        {"$set": {f"texts.{local_id}": text}, "$inc": {"approx_size": sz}}
    )
    # Refresh record in root.chunks
    await root_coll().update_one(
        {"video_id": video_id, "chunks.chunk_id": chunk_id},
        {"$inc": {"chunks.$.count": 1, "chunks.$.approx_size": sz}}
    )