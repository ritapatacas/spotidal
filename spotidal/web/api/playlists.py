import asyncio

from fastapi import APIRouter, HTTPException, Request

from ...model.helpers.sync.playlists_handler import (
    get_playlists_from_sp,
    get_tracks_from_sp_playlist,
    get_user_playlist_mappings,
)
from ...model.helpers.tidalapi import get_all_playlists

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


def _state(request):
    state = request.app.state.spotidal
    if not state.spotify or not state.tidal:
        raise HTTPException(401, "Connect both accounts first")
    return state


@router.get("/spotify")
async def spotify_playlists(request: Request):
    state = _state(request)
    items = await get_playlists_from_sp(state.spotify, {})
    return [{"id": p["id"], "name": p["name"], "tracks": p.get("tracks", {}).get("total", 0)} for p in items]


@router.get("/tidal")
async def tidal_playlists(request: Request):
    state = _state(request)
    items = await get_all_playlists(state.tidal.user)
    return [{"id": p.id, "name": p.name, "tracks": getattr(p, "num_tracks", 0)} for p in items]


@router.get("/mappings")
async def mappings(request: Request):
    state = _state(request)
    items = await asyncio.to_thread(get_user_playlist_mappings, state.spotify, state.tidal, {})
    return [
        {
            "spotify": {
                "id": sp["id"],
                "name": sp["name"],
                "tracks": sp.get("tracks", {}).get("total", 0),
                "image": (sp.get("images") or [{}])[0].get("url"),
            },
            "tidal": ({"id": td.id, "name": td.name} if td else None),
        }
        for sp, td in items
    ]


@router.get("/folders")
async def playlist_folders():
    from ..spotify_folders import get_playlist_folders

    folders = await asyncio.to_thread(get_playlist_folders)
    return {"available": folders is not None, "folders": folders or {}}


@router.get("/{playlist_id}/tracks")
async def playlist_tracks(playlist_id: str, request: Request):
    state = _state(request)
    tracks = await get_tracks_from_sp_playlist(state.spotify, {"id": playlist_id, "name": playlist_id})
    return [
        {
            "name": t["name"],
            "artists": [a["name"] for a in t.get("artists", [])],
            "duration_ms": t.get("duration_ms", 0),
        }
        for t in tracks
    ]


@router.get("/{playlist_id}/duration")
async def playlist_duration(playlist_id: str, request: Request):
    state = _state(request)

    def total_ms():
        ms = 0
        offset = 0
        while True:
            r = state.spotify.playlist_items(
                playlist_id, fields="items(track(duration_ms)),next", limit=100, offset=offset
            )
            ms += sum(i["track"]["duration_ms"] for i in r["items"] if i.get("track"))
            if not r["next"]:
                break
            offset += 100
        return ms

    return {"duration_ms": await asyncio.to_thread(total_ms)}
