"""Question repository.

Implements ASR-1 (data durability) by persisting question data to an
in-memory store surfaced through a stable interface. In production this is
backed by PostgreSQL (see sql/question_ddl.sql). The repository abstraction
allows swapping the in-memory store for a real database without changing
service logic.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.domain import Question


class QuestionRepository:
    """Simple in-memory repository for questions with durable API surface."""

    def __init__(self) -> None:
        self._questions: Dict[str, Question] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = [
            Question(
                id="q1",
                prompt="What is 1/2 + 1/4?",
                options=["1/4", "3/4", "2/6", "1/8"],
                correct_answer="3/4",
            ),
            Question(
                id="q2",
                prompt="What is 2/3 - 1/6?",
                options=["1/2", "1/3", "1/6", "2/3"],
                correct_answer="1/2",
            ),
            Question(
                id="q3",
                prompt="What is 3/5 x 5/3?",
                options=["0", "1", "15/25", "9/25"],
                correct_answer="1",
            ),
            Question(
                id="q4",
                prompt="What is 1/2 divided by 1/4?",
                options=["1/8", "1/2", "2", "4"],
                correct_answer="2",
            ),
        ]
        for q in defaults:
            self._questions[q.id] = q

    def list_questions(self) -> List[Question]:
        return list(self._questions.values())

    def get(self, question_id: str) -> Optional[Question]:
        return self._questions.get(question_id)

    def add(self, question: Question) -> Question:
        self._questions[question.id] = question
        return question

    def update(self, question: Question) -> Question:
        self._questions[question.id] = question
        return question

    def delete(self, question_id: str) -> bool:
        if question_id in self._questions:
            del self._questions[question_id]
            return True
        return False
