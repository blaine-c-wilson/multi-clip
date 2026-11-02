import base64
import json
import time

import boto3
import pytest
import requests
from fastapi.testclient import TestClient
from moto import mock_aws

from app import images, main, store

client = TestClient(main.app)


@pytest.fixture(autouse=True, params=["memory", "dynamodb"])
def empty_store(request, monkeypatch):
    """Run every test against both stores, starting with no clips and an empty
    image bucket.

    The AWS parts talk to moto, a fake AWS inside the test process, so no real
    AWS account or network is needed.
    """
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("s3").create_bucket(
            Bucket="images", CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        monkeypatch.setattr(main, "bucket", images.ImageBucket("images"))
        if request.param == "memory":
            monkeypatch.setattr(main, "store", store.MemoryStore())
            yield
            return
        # Same keys as the real table (see README).
        boto3.client("dynamodb").create_table(
            TableName="clips",
            KeySchema=[
                {"AttributeName": "owner", "KeyType": "HASH"},
                {"AttributeName": "id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "owner", "AttributeType": "S"},
                {"AttributeName": "id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(main, "store", store.DynamoStore("clips"))
        yield


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "multi-clip" in response.text


def test_favicon_is_linked_and_served():
    # Browsers ask for /favicon.ico unless the page links an icon, so check both halves.
    assert '<link rel="icon" href="/favicon.svg"' in client.get("/").text
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert "paperclip" in response.text


def test_logo_follows_title():
    assert '<h1>multi-clip <img src="/favicon.svg"' in client.get("/").text


def test_create_and_list_clips():
    client.post("/api/clips", json={"text": "first"})
    client.post("/api/clips", json={"text": "second"})

    clips = client.get("/api/clips").json()

    assert [c["text"] for c in clips] == ["second", "first"]


def test_create_returns_new_clip():
    response = client.post("/api/clips", json={"text": "hello"})
    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "hello"
    assert body["kind"] == "text"
    assert body["id"]
    assert "created_at" in body
    assert client.get("/api/clips").json() == [body]


def test_empty_clip_is_rejected():
    response = client.post("/api/clips", json={"text": ""})
    assert response.status_code == 422


def test_delete_clip():
    clip_id = client.post("/api/clips", json={"text": "bye"}).json()["id"]

    response = client.delete(f"/api/clips/{clip_id}")

    assert response.status_code == 204
    assert client.get("/api/clips").json() == []


def test_delete_missing_clip_returns_404():
    response = client.delete("/api/clips/999")
    assert response.status_code == 404


def test_ids_sort_in_creation_order():
    ids = [store.new_id() for _ in range(1000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_store_is_chosen_by_environment(monkeypatch):
    monkeypatch.delenv("CLIPS_TABLE", raising=False)
    assert isinstance(store.make_store(), store.MemoryStore)
    monkeypatch.setenv("CLIPS_TABLE", "clips")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")  # Lambda sets this itself
    assert isinstance(store.make_store(), store.DynamoStore)


def upload_image(content_type="image/png", body=b"\x89PNG fake image"):
    """Do what the page does: get a signed form, send the image to (fake) S3
    with it, then save the clip."""
    response = client.post("/api/uploads", json={"content_type": content_type})
    assert response.status_code == 201
    form = response.json()
    sent = requests.post(form["url"], data=form["fields"], files={"file": body})
    assert sent.ok
    return client.post("/api/image-clips", json={"id": form["id"]})


def image_exists(clip_id):
    try:
        boto3.client("s3").head_object(Bucket="images", Key=f"images/{clip_id}")
    except boto3.client("s3").exceptions.ClientError:
        return False
    return True


def test_create_image_clip():
    response = upload_image()
    assert response.status_code == 201
    clip = response.json()
    assert clip["kind"] == "image"
    assert clip["content_type"] == "image/png"
    assert "text" not in clip
    assert client.get("/api/clips").json() == [clip]


def test_image_link_points_to_s3():
    clip_id = upload_image().json()["id"]
    response = client.get(f"/api/clips/{clip_id}/image", follow_redirects=False)
    assert response.status_code == 307
    link = response.headers["location"]
    assert link.startswith("https://images.s3.us-east-2.amazonaws.com/")
    assert requests.get(link).content == b"\x89PNG fake image"


def test_upload_form_limits_type_and_size():
    form = client.post("/api/uploads", json={"content_type": "image/jpeg"}).json()
    # The policy is the part S3 checks; it's base64-encoded JSON.
    conditions = json.loads(base64.b64decode(form["fields"]["policy"]))["conditions"]
    assert {"Content-Type": "image/jpeg"} in conditions
    assert ["content-length-range", 1, images.MAX_BYTES] in conditions
    assert form["fields"]["key"] == f"images/{form['id']}"


def test_unsupported_image_type_is_rejected():
    response = client.post("/api/uploads", json={"content_type": "image/svg+xml"})
    assert response.status_code == 415


def test_image_clip_needs_the_upload():
    response = client.post("/api/image-clips", json={"id": store.new_id()})
    assert response.status_code == 400
    assert client.get("/api/clips").json() == []


def test_oversized_image_is_rejected_and_removed():
    # Real S3 refuses this upload; the fake one doesn't, which lets us test
    # the app's own check.
    clip_id = store.new_id()
    boto3.client("s3").put_object(
        Bucket="images",
        Key=f"images/{clip_id}",
        Body=b"x" * (images.MAX_BYTES + 1),
        ContentType="image/png",
    )
    response = client.post("/api/image-clips", json={"id": clip_id})
    assert response.status_code == 400
    assert not image_exists(clip_id)


def test_clip_ids_from_browsers_are_checked():
    assert client.post("/api/image-clips", json={"id": "../secret"}).status_code == 422
    assert client.get("/api/clips/not-a-clip-id/image").status_code == 422


def test_deleting_image_clip_removes_the_image():
    clip_id = upload_image().json()["id"]
    assert image_exists(clip_id)
    assert client.delete(f"/api/clips/{clip_id}").status_code == 204
    assert not image_exists(clip_id)
    assert client.get("/api/clips").json() == []


def test_image_clips_expire():
    clip = upload_image().json()
    assert clip["expires_at"]
    main.store.add({"id": store.new_id(), "kind": "image", "image_key": "images/old",
                    "content_type": "image/png", "created_at": "2026-01-01T00:00:00+00:00",
                    "expires_at": int(time.time()) - 1})
    assert [c["id"] for c in client.get("/api/clips").json()] == [clip["id"]]


def test_images_unavailable_without_a_bucket(monkeypatch):
    monkeypatch.setattr(main, "bucket", None)
    response = client.post("/api/uploads", json={"content_type": "image/png"})
    assert response.status_code == 503


def test_bucket_is_chosen_by_environment(monkeypatch):
    monkeypatch.delenv("IMAGES_BUCKET", raising=False)
    assert images.make_bucket() is None
    monkeypatch.setenv("IMAGES_BUCKET", "images")
    assert images.make_bucket().name == "images"
