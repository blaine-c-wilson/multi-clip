"""Where clips are kept.

On AWS, clips live in a DynamoDB table named by the CLIPS_TABLE environment
variable. Without it (running locally, or in CI's smoke test) they're kept in
memory and disappear when the app restarts.

Each clip is a dict with "id", "kind" and "created_at". A "text" clip has
"text"; an "image" clip has "image_key" and "content_type" (the image itself
is in S3, see images.py) and "expires_at", when DynamoDB's time-to-live
deletes it, in seconds since 1970.
"""

import os
import secrets
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

# Every clip belongs to "public" until users can log in (issue #10).
OWNER = "public"

# What new_id() makes. Checked before an ID from a browser goes into an S3 key.
ID_PATTERN = r"^\d{20}-[0-9a-f]{8}$"

_last_ns = 0


def new_id() -> str:
    """A unique ID that sorts by creation time: nanoseconds, then random hex.

    The time part never repeats within one process, so clips created in the
    same instant still sort in order; the random part keeps IDs from different
    Lambda instances apart.
    """
    global _last_ns
    _last_ns = max(time.time_ns(), _last_ns + 1)
    return f"{_last_ns:020d}-{secrets.token_hex(4)}"


class MemoryStore:
    def __init__(self) -> None:
        self.clips: dict[str, dict] = {}

    def add(self, clip: dict) -> None:
        self.clips[clip["id"]] = clip

    def list(self) -> list[dict]:
        """All clips, newest first."""
        return sorted(self.clips.values(), key=lambda c: c["id"], reverse=True)

    def delete(self, clip_id: str) -> dict | None:
        """Delete a clip and return it; None if it didn't exist."""
        return self.clips.pop(clip_id, None)


class DynamoStore:
    """Table keys: partition key "owner", sort key "id" (both strings)."""

    def __init__(self, table_name: str) -> None:
        self.table = boto3.resource("dynamodb").Table(table_name)

    def add(self, clip: dict) -> None:
        self.table.put_item(Item={"owner": OWNER, **clip})

    def list(self) -> list[dict]:
        """All clips, newest first. A query returns at most 1 MB, so keep
        asking for the next page until there isn't one."""
        query = {"KeyConditionExpression": Key("owner").eq(OWNER), "ScanIndexForward": False}
        items = []
        while True:
            page = self.table.query(**query)
            items += page["Items"]
            if "LastEvaluatedKey" not in page:
                break
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return [_from_item(item) for item in items]

    def delete(self, clip_id: str) -> dict | None:
        """Delete a clip and return it; None if it didn't exist."""
        try:
            response = self.table.delete_item(
                Key={"owner": OWNER, "id": clip_id},
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_OLD",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return None
        return _from_item(response["Attributes"])


def _from_item(item: dict) -> dict:
    """A table item as a clip: without "owner", and with DynamoDB's numbers
    (which boto3 reads as Decimal) as plain ints."""
    return {
        k: int(v) if isinstance(v, Decimal) else v for k, v in item.items() if k != "owner"
    }


def make_store() -> MemoryStore | DynamoStore:
    table_name = os.environ.get("CLIPS_TABLE")
    return DynamoStore(table_name) if table_name else MemoryStore()
