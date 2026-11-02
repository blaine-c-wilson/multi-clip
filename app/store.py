"""Where clips are kept.

On AWS, clips live in a DynamoDB table named by the CLIPS_TABLE environment
variable. Without it (running locally, or in CI's smoke test) they're kept in
memory and disappear when the app restarts.

Each clip is a dict with "id", "kind", "text" and "created_at". "kind" is
"text" for now; image clips will add "image" with the image itself in S3.
"""

import os
import secrets
import time

import boto3
from boto3.dynamodb.conditions import Key

# Every clip belongs to "public" until users can log in (issue #10).
OWNER = "public"

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

    def delete(self, clip_id: str) -> bool:
        """Delete a clip; False if it didn't exist."""
        return self.clips.pop(clip_id, None) is not None


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
        return [{k: v for k, v in item.items() if k != "owner"} for item in items]

    def delete(self, clip_id: str) -> bool:
        """Delete a clip; False if it didn't exist."""
        try:
            self.table.delete_item(
                Key={"owner": OWNER, "id": clip_id},
                ConditionExpression="attribute_exists(id)",
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True


def make_store() -> MemoryStore | DynamoStore:
    table_name = os.environ.get("CLIPS_TABLE")
    return DynamoStore(table_name) if table_name else MemoryStore()
