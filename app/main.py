"""multi-clip web app.

A small API for saving and listing text clips, plus a web page that uses it.
Clips are stored in DynamoDB on AWS, or in memory when running locally
(see store.py).
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.store import make_store, new_id

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="multi-clip")


class ClipIn(BaseModel):
    """What a client sends to create a clip."""

    text: str = Field(min_length=1, max_length=10_000)


class Clip(ClipIn):
    """A saved clip, as the API returns it."""

    id: str
    kind: str
    created_at: datetime


store = make_store()


@app.get("/health")
def health() -> dict:
    """Lets monitoring and the deploy pipeline check that the app is running."""
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    """The icon in the browser tab (linked from index.html)."""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/clips")
def list_clips() -> list[Clip]:
    """Return all clips, newest first."""
    return store.list()


@app.post("/api/clips", status_code=201)
def create_clip(clip_in: ClipIn) -> Clip:
    clip = {
        "id": new_id(),
        "kind": "text",
        "text": clip_in.text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.add(clip)
    return clip


@app.delete("/api/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: str) -> None:
    if not store.delete(clip_id):
        raise HTTPException(status_code=404, detail="Clip not found")
