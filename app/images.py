"""Where image files are kept.

The bytes of an image clip live in an S3 bucket named by the IMAGES_BUCKET
environment variable; the clip in the store only records the image's key.
Browsers upload straight to S3 with a short-lived signed form, because a
request to Lambda can't be larger than 6 MB. Without IMAGES_BUCKET (running
locally) there are no image clips.
"""

import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

MAX_BYTES = 5 * 1024 * 1024
# No SVG: it can carry scripts. These are the formats browsers show everywhere.
TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
# The app has no login yet, so images don't stay forever. The bucket's
# lifecycle rule deletes them a day later than this, as a backstop (see README).
KEEP_DAYS = 7
# How long a signed upload form or download link works.
LINK_SECONDS = 300


def image_key(clip_id: str) -> str:
    return f"images/{clip_id}"


class ImageBucket:
    def __init__(self, name: str) -> None:
        self.name = name
        # Signed URLs use S3's global address unless told otherwise, and for
        # a new bucket outside us-east-1 that address redirects for a while,
        # which breaks browser uploads. So name the region's address.
        region = boto3.session.Session().region_name
        self.s3 = boto3.client(
            "s3",
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )

    def upload_form(self, key: str, content_type: str) -> dict:
        """A signed form that lets a browser put one image at `key`. S3 itself
        refuses the upload if it's the wrong type or too big."""
        return self.s3.generate_presigned_post(
            self.name,
            key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, MAX_BYTES],
            ],
            ExpiresIn=LINK_SECONDS,
        )

    def details(self, key: str) -> dict | None:
        """Size and type of the image at `key`; None if nothing was uploaded."""
        try:
            head = self.s3.head_object(Bucket=self.name, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return None
            raise
        return {"size": head["ContentLength"], "content_type": head["ContentType"]}

    def link(self, key: str) -> str:
        """A short-lived URL to download the image (the bucket itself is private)."""
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.name, "Key": key}, ExpiresIn=LINK_SECONDS
        )

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.name, Key=key)


def make_bucket() -> ImageBucket | None:
    name = os.environ.get("IMAGES_BUCKET")
    return ImageBucket(name) if name else None
