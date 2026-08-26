import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..model.model import Model
from ..model import auth
from ..model.helpers.type.file import Files


@dataclass
class SyncJob:
    id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: bool = False


class AppState:
    """Process-local state. Credentials remain persisted by the existing model."""

    def __init__(self):
        self.model = Model()
        self.jobs: dict[str, SyncJob] = {}
        self.tidal_login: dict[str, Any] | None = None
        self.restore_lock = asyncio.Lock()

    async def restore_sessions(self):
        """Reopen sessions saved by a previous web or CLI run."""
        async with self.restore_lock:
            credentials = Files.CREDENTIALS.load() or {}
            sessions = self.model.sessions or {"sp": None, "td": None}
            if credentials.get("spotify") and sessions["sp"] is None:
                sessions["sp"] = await asyncio.to_thread(auth.open_sp_session)
            if credentials.get("tidal") and sessions["td"] is None:
                sessions["td"] = await asyncio.to_thread(auth.get_td_session)
            self.model.sessions = sessions

    @property
    def spotify(self):
        return self.model.sessions["sp"] if self.model.sessions else None

    @property
    def tidal(self):
        return self.model.sessions["td"] if self.model.sessions else None

    def new_job(self) -> SyncJob:
        job = SyncJob(uuid.uuid4().hex)
        self.jobs[job.id] = job
        return job

    async def publish(self, job: SyncJob, event: dict):
        await job.queue.put(event)
