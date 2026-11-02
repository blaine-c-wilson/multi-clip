import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app import main, store

client = TestClient(main.app)


@pytest.fixture(autouse=True, params=["memory", "dynamodb"])
def empty_store(request, monkeypatch):
    """Run every test against both stores, starting with no clips.

    The DynamoDB store talks to moto, a fake AWS inside the test process, so no
    real AWS account or network is needed.
    """
    if request.param == "memory":
        monkeypatch.setattr(main, "store", store.MemoryStore())
        yield
        return
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
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
