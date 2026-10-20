"""API integration tests using FastAPI TestClient (contract/E2E)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_play_endpoint_fr1():
    # FR-1: Play game
    resp = client.get("/play")
    assert resp.status_code == 200
    data = resp.json()
    assert "gameId" in data
    assert data["state"] == "playing"


def test_full_game_flow_via_api():
    resp = client.get("/play")
    game_id = resp.json()["gameId"]

    prompt = client.get(f"/games/{game_id}/prompt")
    assert prompt.status_code == 200
    body = prompt.json()
    assert "prompt" in body

    answer = client.post(f"/games/{game_id}/answer", json={"answer": "3/4"})
    assert answer.status_code == 200
    assert answer.json()["score"] == 1

    score = client.get(f"/games/{game_id}/score")
    assert score.status_code == 200
    assert score.json()["score"] == 1


def test_questions_list_endpoint():
    resp = client.get("/questions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 4


def test_admin_only_question_management_asr2():
    # Without authorization -> 401
    resp = client.post("/questions", json={
        "id": "qx", "prompt": "p", "options": ["a"], "correct_answer": "a"
    })
    assert resp.status_code == 401

    # With admin bearer (username "admin") -> success
    resp = client.post(
        "/questions",
        json={"id": "qx", "prompt": "p", "options": ["a"], "correct_answer": "a"},
        headers={"Authorization": "Bearer admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "qx"


def test_login_endpoint_asr2():
    resp = client.post("/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    resp = client.post("/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 401


def test_create_user_endpoint():
    resp = client.post("/users", json={"username": "newuser", "password": "p"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "newuser"
