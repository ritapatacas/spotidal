import asyncio
import webbrowser

import spotipy as sp_api
import tidalapi as td_api
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ...model import auth
from ...model.helpers.type.file import Files

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SpotifyCredentials(BaseModel):
    username: str
    client_id: str
    client_secret: str


def _state(request: Request):
    return request.app.state.spotidal


async def _finish_tidal_login(state):
    if not state.tidal_login or not state.tidal_login["future"].done():
        return
    session = state.tidal_login["session"]
    await asyncio.to_thread(state.tidal_login["future"].result)
    state.model.sessions = {"sp": state.spotify, "td": session}
    auth.save_td_session(session)
    state.tidal_login = None


@router.get("/status")
async def status(request: Request):
    state = _state(request)
    if state.model.sessions is None:
        await state.restore_sessions()
    await _finish_tidal_login(state)
    return {"spotify": state.spotify is not None, "tidal": state.tidal is not None}


@router.post("/spotify")
async def save_spotify(credentials: SpotifyCredentials, request: Request):
    _state(request).model.setup_credentials(credentials.model_dump())
    return {"saved": True, "authorize_url": "/api/auth/spotify/login"}


@router.get("/spotify/login")
async def spotify_login(request: Request):
    credentials = (Files.CREDENTIALS.load() or {}).get("spotify")
    if not credentials:
        raise HTTPException(400, "Spotify credentials have not been configured")
    oauth = sp_api.SpotifyOAuth(
        username=credentials["username"], client_id=credentials["client_id"],
        client_secret=credentials["client_secret"], scope=auth.SPOTIFY_SCOPES,
        redirect_uri=auth.SPOTIFY_REDIRECT_URI,
        requests_timeout=2,
    )
    request.app.state.spotify_oauth = oauth
    return RedirectResponse(oauth.get_authorize_url())


@router.get("/spotify/callback")
@router.get("/callback", include_in_schema=False)
async def spotify_callback(code: str, request: Request):
    oauth = getattr(request.app.state, "spotify_oauth", None)
    if oauth is None:
        raise HTTPException(400, "Spotify login was not started")
    await asyncio.to_thread(oauth.get_access_token, code, as_dict=False)
    request.app.state.spotidal.model.sessions = {
        "sp": sp_api.Spotify(oauth_manager=oauth),
        "td": request.app.state.spotidal.tidal,
    }
    auth.save_sp_credentials(Files.CREDENTIALS.load()["spotify"])
    return RedirectResponse("/")


@router.post("/spotify/session")
async def open_spotify_session(request: Request):
    state = _state(request)
    state.model.sessions = {"sp": await asyncio.to_thread(state.model.open_sp_session), "td": state.tidal}
    return {"connected": state.spotify is not None}


@router.post("/tidal/login")
async def tidal_login(request: Request):
    state = _state(request)
    session = td_api.Session()
    login, future = await asyncio.to_thread(session.login_oauth)
    state.tidal_login = {"session": session, "future": future}
    if login.verification_uri_complete and not login.verification_uri_complete.startswith("https://"):
        url = "https://" + login.verification_uri_complete
    else:
        url = login.verification_uri_complete
    return {"authorize_url": url}


@router.get("/tidal/status")
async def tidal_status(request: Request):
    state = _state(request)
    pending = bool(state.tidal_login and not state.tidal_login["future"].done())
    await _finish_tidal_login(state)
    return {"connected": state.tidal is not None, "pending": pending}
