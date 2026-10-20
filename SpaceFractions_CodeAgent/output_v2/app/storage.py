"""In-memory + JSON-file-backed persistence.

This is a lightweight storage layer that provides durability (ASR-1) by
persisting data to a JSON file on disk. It is intentionally simple and
synchronous so the whole project stays runnable without external services,
while still honouring the data-durability requirement. The SQL DDL in
sql/ describes the equivalent production schema.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import uuid
from typing import Dict, List, Optional

from app import auth
from app.models import Game, Question, User

log = logging.getLogger("spacefractions.storage")

DATA_DIR = os.environ.get("SPACE_DATA_DIR", "./data")
SECRET_FILE = os.path.join(DATA_DIR, "secret.key")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
GAMES_FILE = os.path.join(DATA_DIR, "games.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

_lock = threading.Lock()


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _default_questions() -> List[dict]:
    return [
        {
            "id": "q1",
            "prompt": "What is 1/2 + 1/4?",
            "options": ["2/6", "3/4", "1/8", "1/4"],
            "correct_index": 1,
            "explanation": "1/2 = 2/4, so 2/4 + 1/4 = 3/4.",
        },
        {
            "id": "q2",
            "prompt": "What is 1/3 + 1/6?",
            "options": ["2/9", "1/6", "1/2", "2/3"],
            "correct_index": 2,
            "explanation": "1/3 = 2/6, so 2/6 + 1/6 = 3/6 = 1/2.",
        },
        {
            "id": "q3",
            "prompt": "What is 3/4 - 1/2?",
            "options": ["1/4", "1/2", "2/4", "1/8"],
            "correct_index": 0,
            "explanation": "1/2 = 2/4, so 3/4 - 2/4 = 1/4.",
        },
        {
            "id": "q4",
            "prompt": "What is 2/5 x 3/4 (simplify)?",
            "options": ["6/20", "3/10", "5/20", "6/9"],
            "correct_index": 1,
            "explanation": "2*3 / 5*4 = 6/20 = 3/10.",
        },
        {
            "id": "q5",
            "prompt": "What is 1/4 represented as a percentage?",
            "options": ["40%", "4%", "25%", "14%"],
            "correct_index": 2,
            "explanation": "1/4 = 0.25 = 25%.",
        },
    ]


class Storage:
    """Thread-safe store backed by JSON files on disk."""

    def __init__(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _lock:
            self._questions: Dict[str, Question] = {
                q["id"]: Question(**q)
                for q in _load(QUESTIONS_FILE, _default_questions())
            }
            self._games: Dict[str, Game] = {
                k: Game(**v) for k, v in _load(GAMES_FILE, {}).items()
            }
            self._users: Dict[str, User] = {
                k: User(**v) for k, v in _load(USERS_FILE, {}).items()
            }
        # Persist defaults on first run so durability is explicit.
        self._save_all()
        self.secret_key = self._load_secret()
        self._bootstrap_admin()

    # ---- Auth bootstrap ----
    @staticmethod
    def _load_secret() -> str:
        """Token-signing secret: SPACE_SECRET_KEY, else a random key persisted in the data dir."""
        env = os.environ.get("SPACE_SECRET_KEY", "")
        if env:
            if len(env) < 32:
                raise RuntimeError("SPACE_SECRET_KEY must be at least 32 characters")
            return env
        if os.path.exists(SECRET_FILE):
            with open(SECRET_FILE, "r", encoding="ascii") as f:
                return f.read().strip()
        key = secrets.token_hex(32)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(key)
        return key

    def _bootstrap_admin(self) -> None:
        """Create/refresh the admin account from SPACE_ADMIN_USERNAME / SPACE_ADMIN_PASSWORD.

        There is no way to become admin through the API. With neither variable set, no admin
        exists and the admin screen cannot be used.
        """
        username = os.environ.get("SPACE_ADMIN_USERNAME", "")
        password = os.environ.get("SPACE_ADMIN_PASSWORD", "")
        if not username and not password:
            if not any(u.role == "admin" for u in self._users.values()):
                log.warning("No admin account: set SPACE_ADMIN_USERNAME and SPACE_ADMIN_PASSWORD "
                            "to enable the admin screen.")
            return
        if not (username and password):
            raise RuntimeError("Set both SPACE_ADMIN_USERNAME and SPACE_ADMIN_PASSWORD, or neither")
        try:
            auth.validate_username(username)
            auth.validate_password(password)
        except ValueError as e:
            raise RuntimeError(f"Invalid admin credentials: {e}") from None
        with _lock:
            user = self._find_user(username)
            if user is None:
                user = User(id="u" + uuid.uuid4().hex[:8], username=username, role="admin",
                            password_hash=auth.hash_password(password))
                self._users[user.id] = user
            else:
                user.role = "admin"
                if not auth.verify_password(password, user.password_hash):
                    user.password_hash = auth.hash_password(password)
            self._save_users()

    def _save_all(self) -> None:
        with _lock:
            _save(
                QUESTIONS_FILE,
                [q.dict() for q in self._questions.values()],
            )
            _save(GAMES_FILE, {k: v.dict() for k, v in self._games.items()})
            _save(USERS_FILE, {k: v.dict() for k, v in self._users.items()})

    # ---- Questions ----
    def list_questions(self) -> List[Question]:
        with _lock:
            return list(self._questions.values())

    def get_question(self, question_id: str) -> Optional[Question]:
        with _lock:
            return self._questions.get(question_id)

    def create_question(self, data: dict) -> Question:
        with _lock:
            qid = "q" + uuid.uuid4().hex[:8]
            q = Question(id=qid, **data)
            self._questions[qid] = q
            self._save_questions()
            return q

    def update_question(self, question_id: str, data: dict) -> Optional[Question]:
        with _lock:
            existing = self._questions.get(question_id)
            if existing is None:
                return None
            updated = Question(id=question_id, **data)
            self._questions[question_id] = updated
            self._save_questions()
            return updated

    def delete_question(self, question_id: str) -> bool:
        with _lock:
            if question_id not in self._questions:
                return False
            del self._questions[question_id]
            self._save_questions()
            return True

    def _save_questions(self) -> None:
        _save(QUESTIONS_FILE, [q.dict() for q in self._questions.values()])

    # ---- Games ----
    def create_game(self, question_ids: List[str]) -> Game:
        with _lock:
            gid = "g" + uuid.uuid4().hex[:8]
            game = Game(id=gid, question_ids=question_ids)
            self._games[gid] = game
            self._save_games()
            return game

    def get_game(self, game_id: str) -> Optional[Game]:
        with _lock:
            return self._games.get(game_id)

    def save_game(self, game: Game) -> None:
        with _lock:
            self._games[game.id] = game
            self._save_games()

    def _save_games(self) -> None:
        _save(GAMES_FILE, {k: v.dict() for k, v in self._games.items()})

    # ---- Users ----
    def _find_user(self, username: str) -> Optional[User]:
        """Case-insensitive lookup. Caller must hold _lock."""
        wanted = username.lower()
        for u in self._users.values():
            if u.username.lower() == wanted:
                return u
        return None

    def find_user(self, username: str) -> Optional[User]:
        with _lock:
            return self._find_user(username)

    def create_player(self, username: str, password_hash: str) -> Optional[User]:
        """Create a *player*. Returns None if the username is taken. Admins cannot be created here."""
        with _lock:
            if self._find_user(username) is not None:
                return None
            user = User(id="u" + uuid.uuid4().hex[:8], username=username, role="player",
                        password_hash=password_hash)
            self._users[user.id] = user
            self._save_users()
            return user

    def is_admin(self, username: str) -> bool:
        with _lock:
            u = self._find_user(username)
            return u is not None and u.role == "admin"

    def _save_users(self) -> None:
        _save(USERS_FILE, {k: v.dict() for k, v in self._users.items()})
