import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config.config import settings
from routes import register_routes

app = FastAPI(title="YurTube", version="0.1.0")

# Static and storage mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
# Expose storage via app in MVP; later serve via nginx/X-Accel
if os.path.isdir(settings.STORAGE_ROOT):
  app.mount("/storage", StaticFiles(directory=settings.STORAGE_ROOT), name="storage")

# Minimal session middleware (used for flashing, etc.)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register routes
register_routes(app)