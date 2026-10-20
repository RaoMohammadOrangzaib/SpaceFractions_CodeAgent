"""Space Fractions API — FastAPI backend.

Implements the GameComponent, QuestionComponent, and UserComponent
responsibilities as REST endpoints described in openapi.yaml.

Components:
  - GameComponent: /api/games (create/play/answer/score)
  - QuestionComponent: /api/questions (list/create/update/delete) -- ADMIN ONLY
  - UserComponent:   /api/users (register a player), /api/login, /api/users/me

Security (ASR-2): passwords are scrypt-hashed, /api/login issues a signed expiring bearer
token, and every question-management endpoint requires an admin token. Nobody can become
admin through the API; the admin account comes from SPACE_ADMIN_USERNAME / SPACE_ADMIN_PASSWORD.

The frontend (HTML/CSS/JS) is served at '/' by this same service.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from app import auth
from app.models import User
from app.storage import Storage

app = FastAPI(
    title="Space Fractions API",
    description="API for the Space Fractions game",
    version="1.0.0",
)

storage = Storage()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------
class AnswerRequest(BaseModel):
    answer_index: int


class RegisterRequest(BaseModel):
    """Player registration. A `role` field, if sent, is ignored: registrants are always players."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return auth.validate_username(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return auth.validate_password(v)


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=auth.MAX_PASSWORD_LEN)


class UpdateQuestionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    options: List[str] = Field(min_length=2, max_length=8)
    correct_index: int
    explanation: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _index_in_range(self) -> "UpdateQuestionRequest":
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError("correct_index must be a valid index into options")
        return self


# --------------------------------------------------------------------------
# Authentication / authorization
# --------------------------------------------------------------------------
TOKEN_TTL_SECONDS = int(os.environ.get("SPACE_TOKEN_TTL_SECONDS", "3600"))
throttle = auth.LoginThrottle()


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    """Resolve the bearer token to a user (401 if missing, invalid, expired or the user is gone)."""
    scheme, _, token = (authorization or "").partition(" ")
    username = auth.parse_token(storage.secret_key, token) if scheme.lower() == "bearer" and token else None
    user = storage.find_user(username) if username else None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """The role is read from the store on every request, not from the token."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# --------------------------------------------------------------------------
# Root / frontend
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------------------------------
# UserComponent
# --------------------------------------------------------------------------
def _public(user: User) -> dict:
    """Public view of a user: never includes the password hash."""
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/api/users", tags=["UserComponent"], status_code=201)
def register_player(body: RegisterRequest):
    """Register a player account. The role is always 'player'."""
    user = storage.create_player(body.username, auth.hash_password(body.password))
    if user is None:
        raise HTTPException(status_code=409, detail="Username already taken")
    return _public(user)


@app.post("/api/login", tags=["UserComponent"])
def login(body: LoginRequest):
    key = body.username.strip().lower()
    wait = throttle.locked_for(key)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.",
                            headers={"Retry-After": str(wait)})
    user = storage.find_user(body.username.strip())
    # Always run one scrypt verification so unknown users cost the same as wrong passwords.
    ok = auth.verify_password(body.password, user.password_hash if user else auth.DUMMY_HASH)
    if user is None or not ok:
        throttle.record_failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    throttle.reset(key)
    token = auth.make_token(storage.secret_key, user.username, TOKEN_TTL_SECONDS)
    return {"token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS, **_public(user)}


@app.get("/api/users/me", tags=["UserComponent"])
def whoami(user: User = Depends(current_user)):
    return _public(user)


# --------------------------------------------------------------------------
# QuestionComponent
# --------------------------------------------------------------------------
@app.get("/api/questions", tags=["QuestionComponent"])
def list_questions(_admin: User = Depends(require_admin)):
    return {"questions": [q.dict() for q in storage.list_questions()]}


@app.get("/api/questions/{question_id}", tags=["QuestionComponent"])
def get_question(question_id: str, _admin: User = Depends(require_admin)):
    q = storage.get_question(question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return q.dict()


@app.post("/api/questions", tags=["QuestionComponent"], status_code=201)
def create_question(body: UpdateQuestionRequest, _admin: User = Depends(require_admin)):
    q = storage.create_question(body.dict())
    return q.dict()


@app.put("/api/questions/{question_id}", tags=["QuestionComponent"])
def update_question(question_id: str, body: UpdateQuestionRequest, _admin: User = Depends(require_admin)):
    q = storage.update_question(question_id, body.dict())
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return q.dict()


@app.delete("/api/questions/{question_id}", tags=["QuestionComponent"])
def delete_question(question_id: str, _admin: User = Depends(require_admin)):
    if not storage.delete_question(question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"deleted": question_id}


# --------------------------------------------------------------------------
# GameComponent
# --------------------------------------------------------------------------
@app.post("/api/games", tags=["GameComponent"])
def create_game():
    """Start a game (FR-1: Play Game)."""
    question_ids = [q.id for q in storage.list_questions()]
    if not question_ids:
        raise HTTPException(status_code=400, detail="No questions available")
    game = storage.create_game(question_ids)
    return game.dict()


@app.get("/api/games/{game_id}", tags=["GameComponent"])
def get_game(game_id: str):
    game = storage.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game.dict()


@app.get("/api/games/{game_id}/question", tags=["GameComponent"])
def get_current_question(game_id: str):
    """Return the current question prompt + options (SequenceDiagram1)."""
    game = storage.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.finished:
        return {"finished": True, "score": game.score}
    idx = game.current_question_index
    qid = game.question_ids[idx]
    q = storage.get_question(qid)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    # Do not leak the correct answer to the client.
    return {
        "finished": False,
        "question_index": idx,
        "total_questions": len(game.question_ids),
        "question": {
            "id": q.id,
            "prompt": q.prompt,
            "options": q.options,
        },
    }


@app.post("/api/games/{game_id}/answer", tags=["GameComponent"])
def submit_answer(game_id: str, body: AnswerRequest):
    """Check an answer and record the score."""
    game = storage.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.finished:
        raise HTTPException(status_code=400, detail="Game already finished")

    idx = game.current_question_index
    q = storage.get_question(game.question_ids[idx])
    correct = body.answer_index == q.correct_index

    game.record_answer(correct)
    game.current_question_index += 1
    if game.current_question_index >= len(game.question_ids):
        game.finished = True
    storage.save_game(game)

    return {
        "correct": correct,
        "explanation": q.explanation,
        "correct_answer": q.options[q.correct_index],
        "score": game.score,
        "total_answered": game.total_answered,
        "finished": game.finished,
    }


@app.get("/api/games/{game_id}/score", tags=["GameComponent"])
def view_score(game_id: str):
    """View the current score (use case: View Score)."""
    game = storage.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "score": game.score,
        "total_answered": game.total_answered,
        "total_questions": len(game.question_ids),
        "finished": game.finished,
    }


# --------------------------------------------------------------------------
# Static assets (CSS + JS)
# --------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
