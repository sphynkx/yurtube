from fastapi import FastAPI

from .account_rout import router as account_router
from .auth_rout import router as auth_router
from .browse_rout import router as browse_router
from .channel_rout import router as channel_router
from .history_rout import router as history_router
from .root_rout import router as root_router
from .static_rout import router as static_router
from .upload_rout import router as upload_router
from .watch_rout import router as watch_router
from .edit_rout import router as edit_router
from .search_rout import router as search_router
from .account_password_rout import router as account_password_router
from .auth_google_rout import router as auth_google_router
from .auth_twitter_rout import router as auth_twitter_router

from routes.comments.create_rout import router as comments_create_router
from routes.comments.list_rout import router as comments_list_router
from routes.comments.like_rout import router as comments_like_router
from routes.comments.vote_rout import router as comments_vote_router
from routes.comments.update_rout import router as comments_update_router

from .manage_comments import router as manage_comments_router  # added

def register_routes(app: FastAPI) -> None:
    app.include_router(root_router)
    app.include_router(auth_router, prefix="/auth")
    app.include_router(upload_router)
    app.include_router(watch_router)
    app.include_router(browse_router)
    app.include_router(channel_router)
    app.include_router(history_router)
    app.include_router(account_router)
    app.include_router(account_password_router)
    app.include_router(auth_google_router)
    app.include_router(auth_twitter_router)
    app.include_router(static_router)
    app.include_router(edit_router)
    app.include_router(search_router)

    app.include_router(comments_create_router)
    app.include_router(comments_list_router)
    app.include_router(comments_like_router)
    app.include_router(comments_vote_router)
    app.include_router(comments_update_router)

    app.include_router(manage_comments_router)  # added