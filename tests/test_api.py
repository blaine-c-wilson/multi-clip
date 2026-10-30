import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def empty_store():
    """Start every test with no clips, so tests don't affect each other."""
    main.clips.clear()
    main.next_id = 1


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "multi-clip" in response.text


def test_create_and_list_clips():
    client.post("/api/clips", json={"text": "first"})
    client.post("/api/clips", json={"text": "second"})

    clips = client.get("/api/clips").json()

    assert [c["text"] for c in clips] == ["second", "first"]


def test_create_returns_new_clip():
    response = client.post("/api/clips", json={"text": "hello"})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["text"] == "hello"
    assert "created_at" in body


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
