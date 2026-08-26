from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, playlists, sync
from .state import AppState


def create_app() -> FastAPI:
    app = FastAPI(title="Spotidal", version="0.2.0")
    app.state.spotidal = AppState()
    app.include_router(auth.router)
    app.include_router(playlists.router)
    app.include_router(sync.router)
    # Spotify's registered local callback is fixed by the existing CLI setup.
    app.get("/callback", include_in_schema=False)(auth.spotify_callback)
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()


def main():
    import os

    reload = os.environ.get("SPOTIDAL_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("spotidal.web.server:app", host="127.0.0.1", port=8888, reload=reload)


if __name__ == "__main__":
    main()
