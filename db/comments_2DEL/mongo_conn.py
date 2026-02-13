from typing import Optional
import motor.motor_asyncio ## TODO: will deprecated!!
from pymongo.errors import PyMongoError
from config.comments_cfg import comments_settings

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None


def _build_uri() -> str:
    host = comments_settings.MONGO_HOST
    port = comments_settings.MONGO_PORT
    user = comments_settings.MONGO_USER
    pwd = comments_settings.MONGO_PASSWORD
    auth_src = comments_settings.MONGO_AUTH_SOURCE

    if user and pwd:
        return f"mongodb://{user}:{pwd}@{host}:{port}/?authSource={auth_src}"
    return f"mongodb://{host}:{port}"


def get_mongo_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client:
        return _client
    uri = _build_uri()
    _client = motor.motor_asyncio.AsyncIOMotorClient(uri)
    return _client


def get_db():
    return get_mongo_client()[comments_settings.MONGO_DB_NAME]


def root_coll():
    return get_db().video_comments_root


def chunk_coll():
    return get_db().video_comments_chunks