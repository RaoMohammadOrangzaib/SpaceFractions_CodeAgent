"""Domain models for the Space Fractions game.

Mirrors the class diagram from the Logic View:
  - Game: id, score
  - Question: id, prompt, options (list), correct answer
  - User: id, username, role (player/admin)
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Question(BaseModel):
    """A single fraction question.

    - prompt: the text of the question (e.g. "1/2 + 1/4 = ?")
    - options: list of possible answers as strings
    - correct_index: index into options that is the right answer
    - explanation: short feedback shown after answering
    """

    id: str
    prompt: str
    options: List[str]
    correct_index: int
    explanation: str = ""

    def get_prompt(self) -> str:
        return self.prompt

    def get_options(self) -> List[str]:
        return self.options


class Game(BaseModel):
    """A game session with its own score and question list."""

    id: str
    score: int = 0
    total_answered: int = 0
    question_ids: List[str] = Field(default_factory=list)
    current_question_index: int = 0
    finished: bool = False

    def play(self) -> None:
        """Mark the game as playable/reset if needed."""
        if self.finished:
            self.finished = False

    def view_score(self) -> int:
        return self.score

    def record_answer(self, correct: bool) -> None:
        self.total_answered += 1
        if correct:
            self.score += 1


class User(BaseModel):
    """A player or admin of the game (UserComponent, AdminComponent)."""

    id: str
    username: str
    role: str = "player"
    # scrypt hash (see app/auth.py). Stored on disk, never returned by the API.
    password_hash: str = ""
