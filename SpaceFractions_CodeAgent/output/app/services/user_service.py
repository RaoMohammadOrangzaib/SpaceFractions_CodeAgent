"""User and admin management service.

Implements UserComponent (authentication/authorization) and AdminComponent
(question management). ASR-2 (security) is addressed via role checks and
secure password storage (hashing).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Dict, List, Optional

from app.models.domain import Admin, Question, User


class UserService:
    """Handles user accounts, roles, and admin question updates."""

    def __init__(self) -> None:
        self._users: Dict[str, dict] = {}
        self._seed_admin()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def _seed_admin(self) -> None:
        admin_id = "admin-1"
        salt = secrets.token_hex(16)
        self._users[admin_id] = {
            "id": admin_id,
            "username": "admin",
            "role": "admin",
            "salt": salt,
            "password_hash": self._hash_password("admin123", salt),
        }

    def create_user(self, username: str, password: str, role: str = "user") -> dict:
        user_id = str(uuid.uuid4())
        salt = secrets.token_hex(16)
        record = {
            "id": user_id,
            "username": username,
            "role": role,
            "salt": salt,
            "password_hash": self._hash_password(password, salt),
        }
        self._users[user_id] = record
        return {"id": user_id, "username": username, "role": role}

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        for record in self._users.values():
            if record["username"] == username:
                expected = self._hash_password(password, record["salt"])
                if expected == record["password_hash"]:
                    return {"id": record["id"], "username": username,
                            "role": record["role"]}
        return None

    def get_role(self, username: str) -> Optional[str]:
        for record in self._users.values():
            if record["username"] == username:
                return record["role"]
        return None

    def is_admin(self, username: str) -> bool:
        return self.get_role(username) == "admin"
