"""Domain models for the Space Fractions system.

Maps to the Class Diagram (Logic View):
  - Game: id, score; play(), viewScore()
  - Question: id, prompt, options; getPrompt(), getOptions()
  - User: id, username; playGame(), viewScore()
  - Admin: id, username; updateQuestions()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class GameState(str, Enum):
    """Mirrors the State Diagram: Playing -> Paused -> Playing -> GameOver."""

    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


@dataclass
class Question:
    """A fraction question prompt with selectable options."""

    id: str
    prompt: str
    options: List[str]
    correct_answer: str

    def get_prompt(self) -> str:
        return self.prompt

    def get_options(self) -> List[str]:
        return self.options

    def check_answer(self, answer: str) -> bool:
        return answer.strip().lower() == self.correct_answer.strip().lower()


@dataclass
class Game:
    """A single play session. Owns its state and score."""

    id: str
    score: int = 0
    state: GameState = GameState.PLAYING
    questions: List[Question] = field(default_factory=list)
    current_index: int = 0
    correct_count: int = 0
    answered_count: int = 0

    def play(self) -> None:
        if self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def pause(self) -> None:
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED

    def resume(self) -> None:
        if self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def game_over(self) -> None:
        self.state = GameState.GAME_OVER

    def view_score(self) -> int:
        return self.score

    def current_question(self) -> Optional[Question]:
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    def submit_answer(self, answer: str) -> bool:
        question = self.current_question()
        if question is None:
            self.game_over()
            return False
        correct = question.check_answer(answer)
        self.answered_count += 1
        if correct:
            self.correct_count += 1
            self.score += 1
        self.current_index += 1
        if self.current_index >= len(self.questions):
            self.game_over()
        return correct

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "score": self.score,
            "state": self.state.value,
            "correct_count": self.correct_count,
            "answered_count": self.answered_count,
            "total_questions": len(self.questions),
        }


@dataclass
class User:
    """A student (end user) of the game."""

    id: str
    username: str

    def play_game(self, game: Game) -> None:
        game.play()

    def view_score(self, game: Game) -> int:
        return game.view_score()


@dataclass
class Admin:
    """An administrator who maintains the question bank."""

    id: str
    username: str

    def update_questions(self, questions: List[Question]) -> None:
        self._updated_questions = list(questions)

    @property
    def updated_questions(self) -> List[Question]:
        return getattr(self, "_updated_questions", [])
