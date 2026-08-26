import asyncio
import json
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...model.helpers.sync.playlists_handler import get_user_playlist_mappings
from ...model.helpers.synchronizer import sync_playlist
from ...model.helpers.td_downloader import download_playlist

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncRequest(BaseModel):
    playlist_ids: list[str]
    config: dict = Field(default_factory=dict)


class DownloadRequest(BaseModel):
    playlist_ids: list[str]


async def _run(state, job, requested, config):
    try:
        await state.publish(job, {"type": "started", "total": len(requested)})
        mappings = await asyncio.to_thread(get_user_playlist_mappings, state.spotify, state.tidal, config)
        selected = [(sp, td) for sp, td in mappings if sp["id"] in requested]
        for index, (sp, td) in enumerate(selected, 1):
            await state.publish(job, {"type": "playlist", "name": sp["name"], "current": index, "total": len(selected)})
            await sync_playlist(
                state.spotify, state.tidal, sp, td, config,
                progress_callback=lambda event: state.publish(job, event),
            )
        await state.publish(job, {"type": "complete"})
    except Exception as exc:
        await state.publish(job, {"type": "error", "message": str(exc)})
    finally:
        job.done = True


@router.post("")
async def start_sync(payload: SyncRequest, request: Request):
    state = request.app.state.spotidal
    if not state.spotify or not state.tidal:
        raise HTTPException(401, "Connect both accounts first")
    job = state.new_job()
    asyncio.create_task(_run(state, job, payload.playlist_ids, payload.config))
    return {"job_id": job.id, "events_url": f"/api/sync/{job.id}/events"}


@router.post("/download")
async def start_download(payload: DownloadRequest, request: Request):
    state = request.app.state.spotidal
    if not state.tidal:
        raise HTTPException(401, "Connect Tidal first")
    job = state.new_job()

    async def run():
        try:
            loop = asyncio.get_running_loop()

            def output(line):
                match = re.search(r"https://link\.tidal\.com/\S+", line)
                event = {"type": "download_output", "message": line}
                if match:
                    event["authorize_url"] = match.group(0)
                asyncio.run_coroutine_threadsafe(state.publish(job, event), loop)

            await state.publish(job, {"type": "download_started", "total": len(payload.playlist_ids)})
            for index, playlist_id in enumerate(payload.playlist_ids, 1):
                await state.publish(job, {"type": "download", "current": index, "total": len(payload.playlist_ids)})
                await asyncio.to_thread(download_playlist, playlist_id, output_callback=output)
            await state.publish(job, {"type": "download_complete"})
        except Exception as exc:
            await state.publish(job, {"type": "error", "message": str(exc)})
        finally:
            job.done = True

    asyncio.create_task(run())
    return {"job_id": job.id, "events_url": f"/api/sync/{job.id}/events"}


@router.get("/{job_id}/events")
async def events(job_id: str, request: Request):
    job = request.app.state.spotidal.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Sync job not found")

    async def stream():
        while not job.done or not job.queue.empty():
            event = await job.queue.get()
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
