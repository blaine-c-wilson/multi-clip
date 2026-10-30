"""multi-clip web app.

A small API for saving and listing text clips, plus a web page that uses it.
Clips are stored in memory for now, so they disappear when the app restarts.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="multi-clip")


class ClipIn(BaseModel):
    """What a client sends to create a clip."""

    text: str = Field(min_length=1, max_length=10_000)


class Clip(ClipIn):
    """A saved clip, as the API returns it."""

    id: int
    created_at: datetime


# In-memory storage. Replaced by a real database in a later phase.
clips: list[Clip] = []
next_id = 1


@app.get("/health")
def health() -> dict:
    """Lets monitoring and the deploy pipeline check that the app is running."""
    return {"status": "okay"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/clips")
def list_clips() -> list[Clip]:
    """Return all clips, newest first."""
    return list(reversed(clips))


@app.post("/api/clips", status_code=201)
def create_clip(clip_in: ClipIn) -> Clip:
    global next_id
    clip = Clip(id=next_id, text=clip_in.text, created_at=datetime.now(timezone.utc))
    clips.append(clip)
    next_id += 1
    return clip


@app.delete("/api/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: int) -> None:
    for i, clip in enumerate(clips):
        if clip.id == clip_id:
            del clips[i]
            return
    raise HTTPException(status_code=404, detail="Clip not found")
