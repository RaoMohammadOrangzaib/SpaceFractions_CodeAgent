"""Backend API tests covering FR-1, NFR-1, ASR-1, ASR-2."""
from __future__ import annotations

import os
import shutil

# Ensure a dedicated, clean data directory for tests before importing app code.
os.environ["SPACE_DATA_DIR"] = os.path.join(os.getcwd(), "data_test")
ADMIN_USER, ADMIN_PASS = "admin", "correct-horse-battery"
os.environ["SPACE_ADMIN_USERNAME"] = ADMIN_USER
os.environ["SPACE_ADMIN_PASSWORD"] = ADMIN_PASS

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app import auth  # noqa: E402
from app.storage import Storage  # noqa: E402


@pytest.fixture(autouse=True)
def clean_data():
    """Reset test data directory between tests for isolation."""
    d = os.environ["SPACE_DATA_DIR"]
    if os.path.exists(d):
        shutil.rmtree(d)
    main.storage = Storage()
    main.throttle = auth.LoginThrottle()
    yield
    if os.path.exists(d):
        shutil.rmtree(d)


@pytest.fixture()
def client():
    return TestClient(main.app)


def _login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


@pytest.fixture()
def admin_headers(client):
    r = _login(client, ADMIN_USER, ADMIN_PASS)
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def player_headers(client):
    assert client.post("/api/users", json={"username": "kid_1", "password": "rocket-science"}).status_code == 201
    r = _login(client, "kid_1", "rocket-science")
    return {"Authorization": "Bearer " + r.json()["token"]}


QUESTION = {
    "prompt": "What is 1/2 + 1/2?",
    "options": ["1", "1/2", "1/4", "2"],
    "correct_index": 0,
    "explanation": "Halves add to a whole.",
}


def test_list_questions_returns_defaults(client, admin_headers):
    """QuestionComponent serves the default question set (ASR-1 data) to admins."""
    r = client.get("/api/questions", headers=admin_headers)
    assert r.status_code == 200
    questions = r.json()["questions"]
    assert len(questions) >= 5
    for q in questions:
        assert "id" in q and "prompt" in q
        assert isinstance(q["options"], list) and len(q["options"]) >= 2
        assert 0 <= q["correct_index"] < len(q["options"])


def test_create_and_update_question(client, admin_headers):
    """Admin can create and update questions (QuestionComponent)."""
    r = client.post("/api/questions", json=QUESTION, headers=admin_headers)
    assert r.status_code == 201
    q = r.json()
    assert q["prompt"] == "What is 1/2 + 1/2?"

    r2 = client.put(
        f"/api/questions/{q['id']}",
        json={
            "prompt": "What is 1/2 + 1/2?",
            "options": ["1", "1/2", "1/4", "2"],
            "correct_index": 0,
            "explanation": "Updated.",
        },
        headers=admin_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["explanation"] == "Updated."

    r3 = client.delete(f"/api/questions/{q['id']}", headers=admin_headers)
    assert r3.status_code == 200
    assert client.get(f"/api/questions/{q['id']}", headers=admin_headers).status_code == 404


def test_play_game_full_flow(client):
    """FR-1: a user can play the game and view the score."""
    r = client.post("/api/games")
    assert r.status_code == 200
    game = r.json()
    game_id = game["id"]
    assert game["score"] == 0

    total = len(game["question_ids"])
    answered = 0
    while True:
        qr = client.get(f"/api/games/{game_id}/question")
        data = qr.json()
        if data.get("finished"):
            break
        qid = data["question"]["id"]
        q = main.storage.get_question(qid)
        ar = client.post(
            f"/api/games/{game_id}/answer",
            json={"answer_index": q.correct_index},
        )
        assert ar.status_code == 200
        answered += 1
        if ar.json()["finished"]:
            break

    assert answered == total
    sr = client.get(f"/api/games/{game_id}/score")
    assert sr.status_code == 200
    assert sr.json()["score"] == total
    assert sr.json()["finished"] is True


def test_answer_incorrect_reduces_score(client):
    """Wrong answers are not counted toward the score."""
    r = client.post("/api/games")
    game_id = r.json()["id"]
    qdata = client.get(f"/api/games/{game_id}/question").json()
    qid = qdata["question"]["id"]
    q = main.storage.get_question(qid)
    wrong = (q.correct_index + 1) % len(q.options)
    ar = client.post(f"/api/games/{game_id}/answer", json={"answer_index": wrong})
    assert ar.status_code == 200
    assert ar.json()["correct"] is False
    assert ar.json()["score"] == 0


def test_game_not_found_404(client):
    """NFR/robustness: unknown game returns 404."""
    assert client.get("/api/games/nonexistent").status_code == 404
    assert client.get("/api/games/nonexistent/score").status_code == 404


# ---------------------------------------------------------------- ASR-2: security
QUESTION_ENDPOINTS = [
    ("get", "/api/questions", None),
    ("get", "/api/questions/q1", None),
    ("post", "/api/questions", QUESTION),
    ("put", "/api/questions/q1", QUESTION),
    ("delete", "/api/questions/q1", None),
]


def _call(client, method, path, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", QUESTION_ENDPOINTS)
def test_question_endpoints_require_a_token(client, method, path, body):
    r = _call(client, method, path, body)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method,path,body", QUESTION_ENDPOINTS)
def test_question_endpoints_reject_players(client, player_headers, method, path, body):
    assert _call(client, method, path, body, player_headers).status_code == 403


@pytest.mark.parametrize("bad", ["Bearer", "Bearer abc", "Basic abc", "abc.def", "Bearer a.b.c", ""])
def test_malformed_authorization_headers_rejected(client, bad):
    assert client.get("/api/questions", headers={"Authorization": bad}).status_code == 401


def test_tampered_token_rejected(client, admin_headers):
    token = admin_headers["Authorization"].split(" ")[1]
    body, sig = token.split(".")
    forged = {"Authorization": f"Bearer {body}.{'A' * len(sig)}"}
    assert client.get("/api/questions", headers=forged).status_code == 401
    # a token signed with a different secret is also rejected
    other = auth.make_token("x" * 40, ADMIN_USER, 3600)
    assert client.get("/api/questions", headers={"Authorization": "Bearer " + other}).status_code == 401


def test_expired_token_rejected(client):
    expired = auth.make_token(main.storage.secret_key, ADMIN_USER, 60, now=0)
    assert client.get("/api/questions", headers={"Authorization": "Bearer " + expired}).status_code == 401


def test_cannot_register_as_admin(client):
    """The old API let anyone POST role=admin. The role field must now be ignored."""
    r = client.post("/api/users", json={"username": "mallory", "password": "hunter2-hunter2", "role": "admin"})
    assert r.status_code == 201
    assert r.json()["role"] == "player"
    token = _login(client, "mallory", "hunter2-hunter2").json()["token"]
    assert client.get("/api/questions", headers={"Authorization": "Bearer " + token}).status_code == 403
    assert main.storage.is_admin("mallory") is False


def test_cannot_take_over_the_admin_username(client):
    r = client.post("/api/users", json={"username": "ADMIN", "password": "hunter2-hunter2"})
    assert r.status_code == 409  # case-insensitive uniqueness


def test_login_success_and_failure(client):
    ok = _login(client, ADMIN_USER, ADMIN_PASS)
    assert ok.status_code == 200
    data = ok.json()
    assert data["role"] == "admin" and data["token_type"] == "bearer" and data["expires_in"] > 0
    assert "password_hash" not in data
    wrong = _login(client, ADMIN_USER, "not-the-password")
    unknown = _login(client, "nobody-here", "whatever-pass")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no user enumeration


def test_admin_can_manage_questions_with_token(client, admin_headers):
    assert client.post("/api/questions", json=QUESTION, headers=admin_headers).status_code == 201
    assert client.get("/api/users/me", headers=admin_headers).json()["role"] == "admin"


def test_passwords_are_hashed_on_disk_and_never_returned(client):
    pw = "a-very-secret-pw"
    r = client.post("/api/users", json={"username": "alice", "password": pw})
    assert pw not in r.text and "hash" not in r.text
    with open(os.path.join(os.environ["SPACE_DATA_DIR"], "users.json"), encoding="utf-8") as f:
        raw = f.read()
    assert pw not in raw and ADMIN_PASS not in raw
    assert "scrypt$" in raw
    user = main.storage.find_user("alice")
    assert auth.verify_password(pw, user.password_hash)
    assert not auth.verify_password("wrong-password", user.password_hash)
    token = _login(client, "alice", pw).json()["token"]
    me = client.get("/api/users/me", headers={"Authorization": "Bearer " + token})
    assert me.json() == {"id": user.id, "username": "alice", "role": "player"}


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert _login(client, ADMIN_USER, "bad-bad-bad").status_code == 401
    locked = _login(client, ADMIN_USER, ADMIN_PASS)  # even the right password is refused while locked
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_registration_and_question_input_validation(client, admin_headers):
    bad_users = [{"username": "ab", "password": "long-enough-pw"},
                 {"username": "has space", "password": "long-enough-pw"},
                 {"username": "okname", "password": "short"}]
    for body in bad_users:
        assert client.post("/api/users", json=body).status_code == 422
    bad_questions = [dict(QUESTION, correct_index=9), dict(QUESTION, correct_index=-1),
                     dict(QUESTION, options=["only one"]), dict(QUESTION, prompt="")]
    for body in bad_questions:
        assert client.post("/api/questions", json=body, headers=admin_headers).status_code == 422


def test_no_admin_exists_without_env_credentials(client, monkeypatch):
    monkeypatch.delenv("SPACE_ADMIN_USERNAME")
    monkeypatch.delenv("SPACE_ADMIN_PASSWORD")
    shutil.rmtree(os.environ["SPACE_DATA_DIR"])
    main.storage = Storage()
    assert _login(client, ADMIN_USER, ADMIN_PASS).status_code == 401
    assert not any(u.role == "admin" for u in main.storage._users.values())


def test_half_configured_admin_env_fails_fast(monkeypatch):
    monkeypatch.delenv("SPACE_ADMIN_PASSWORD")
    with pytest.raises(RuntimeError):
        Storage()
    monkeypatch.setenv("SPACE_ADMIN_PASSWORD", "short")
    with pytest.raises(RuntimeError):
        Storage()


def test_players_cannot_read_answers_through_the_game_api(client):
    """The public game endpoint must not leak correct_index (answers stay admin-only)."""
    game = client.post("/api/games").json()
    q = client.get(f"/api/games/{game['id']}/question").json()["question"]
    assert "correct_index" not in q and "explanation" not in q


# ----------------------------------------------------------- auth unit tests
def test_hash_and_verify_unit():
    h = auth.hash_password("pw-12345678")
    assert h != auth.hash_password("pw-12345678")  # random salt
    assert auth.verify_password("pw-12345678", h)
    assert not auth.verify_password("pw-12345679", h)
    for junk in ["", "plaintext", "scrypt$1$2", "md5$a$b$c$d$e", "scrypt$x$y$z$a$b"]:
        assert not auth.verify_password("pw-12345678", junk)


def test_token_roundtrip_unit():
    t = auth.make_token("s" * 40, "bob", 100, now=1000)
    assert auth.parse_token("s" * 40, t, now=1050) == "bob"
    assert auth.parse_token("s" * 40, t, now=1100) is None  # expired exactly at exp
    assert auth.parse_token("z" * 40, t, now=1050) is None


def test_throttle_unit():
    now = [0.0]
    th = auth.LoginThrottle(max_failures=3, window_seconds=100, lock_seconds=30, clock=lambda: now[0])
    for _ in range(3):
        th.record_failure("u")
    assert th.locked_for("u") > 0
    now[0] = 31
    assert th.locked_for("u") == 0
    th.record_failure("u")
    th.reset("u")
    assert th.locked_for("u") == 0
