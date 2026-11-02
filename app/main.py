"""multi-clip web app.

A small API for saving and listing text and image clips, plus a web page that
uses it. Clips are stored in DynamoDB on AWS, or in memory when running
locally (see store.py); image files are in S3 (see images.py).
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.images import KEEP_DAYS, MAX_BYTES, TYPES, image_key, make_bucket
from app.store import ID_PATTERN, make_store, new_id

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="multi-clip")


class ClipIn(BaseModel):
    """What a client sends to create a text clip."""

    text: str = Field(min_length=1, max_length=10_000)


class Clip(BaseModel):
    """A saved clip, as the API returns it."""

    id: str
    kind: str  # "text" or "image"
    created_at: datetime
    text: str | None = None  # text clips
    content_type: str | None = None  # image clips
    expires_at: datetime | None = None  # image clips


class UploadIn(BaseModel):
    """What a client sends to start uploading an image."""

    content_type: str


class Upload(BaseModel):
    """A signed form for sending one image straight to S3."""

    id: str
    url: str
    fields: dict[str, str]


class ImageClipIn(BaseModel):
    """What a client sends once the image is in S3."""

    id: str = Field(pattern=ID_PATTERN)


store = make_store()
bucket = make_bucket()


def need_bucket():
    if bucket is None:
        raise HTTPException(status_code=503, detail="Image clips aren't set up here (no IMAGES_BUCKET)")
    return bucket


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


@app.get("/api/clips", response_model_exclude_none=True)
def list_clips() -> list[Clip]:
    """Return all clips, newest first. DynamoDB can take a day or two to
    delete expired clips, so hide them here."""
    now = time.time()
    return [c for c in store.list() if c.get("expires_at", now + 1) > now]


@app.post("/api/clips", status_code=201, response_model_exclude_none=True)
def create_clip(clip_in: ClipIn) -> Clip:
    clip = {
        "id": new_id(),
        "kind": "text",
        "text": clip_in.text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.add(clip)
    return clip


@app.post("/api/uploads", status_code=201)
def start_upload(upload_in: UploadIn) -> Upload:
    """Step 1 of saving an image: a signed form the browser uses to send the
    image straight to S3. The new clip's ID is decided here."""
    images = need_bucket()
    if upload_in.content_type not in TYPES:
        raise HTTPException(status_code=415, detail="Images must be PNG, JPEG, GIF or WebP")
    clip_id = new_id()
    form = images.upload_form(image_key(clip_id), upload_in.content_type)
    return {"id": clip_id, **form}


@app.post("/api/image-clips", status_code=201, response_model_exclude_none=True)
def create_image_clip(image_in: ImageClipIn) -> Clip:
    """Step 2: once the image is in S3, save the clip that points to it."""
    images = need_bucket()
    key = image_key(image_in.id)
    found = images.details(key)
    if found is None:
        raise HTTPException(status_code=400, detail="Upload the image first")
    # S3 already enforces these through the signed form; check again in case
    # the form's conditions are ever loosened by mistake.
    if found["size"] > MAX_BYTES or found["content_type"] not in TYPES:
        images.delete(key)
        raise HTTPException(status_code=400, detail="Images must be PNG, JPEG, GIF or WebP, up to 5 MB")
    now = datetime.now(timezone.utc)
    clip = {
        "id": image_in.id,
        "kind": "image",
        "image_key": key,
        "content_type": found["content_type"],
        "created_at": now.isoformat(),
        "expires_at": int((now + timedelta(days=KEEP_DAYS)).timestamp()),
    }
    store.add(clip)
    return clip


@app.get("/api/clips/{clip_id}/image")
def get_image(clip_id: str = PathParam(pattern=ID_PATTERN)) -> RedirectResponse:
    """Send the browser to a short-lived S3 link for the image."""
    return RedirectResponse(need_bucket().link(image_key(clip_id)), status_code=307)


@app.delete("/api/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: str) -> None:
    clip = store.delete(clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip["kind"] == "image":
        need_bucket().delete(clip["image_key"])
