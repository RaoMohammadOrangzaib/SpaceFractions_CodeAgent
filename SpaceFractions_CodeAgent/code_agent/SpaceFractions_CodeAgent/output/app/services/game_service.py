"""Game service coordinating game sessions and question flow.

Implements the interaction captured in SequenceDiagram1:
  User -> Game: play()
  Game -> Question: getPrompt()
  ...
  Game -> Question: check answer
  Game -> User: display result
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from app.models.domain import Game, GameState, Question
from app.services.question_repository import QuestionRepository


class GameService:
    """Manages game sessions and orchestrates question flow."""

    def __init__(self, question_repository: QuestionRepository) -> None:
        self._question_repository = question_repository
        self._games: Dict[str, Game] = {}

    def start_game(self, question_ids: Optional[List[str]] = None) -> Game:
        game_id = str(uuid.uuid4())
        questions = self._question_repository.list_questions()
        if question_ids:
            questions = [q for q in questions if q.id in question_ids]
        game = Game(id=game_id, questions=questions)
        self._games[game_id] = game
        return game

    def get_game(self, game_id: str) -> Optional[Game]:
        return self._games.get(game_id)

    def get_prompt(self, game_id: str) -> Optional[dict]:
        game = self._games.get(game_id)
        if game is None:
            return None
        question = game.current_question()
        if question is None:
            return None
        return {"question_id": question.id, "prompt": question.get_prompt(),
                "options": question.get_options()}

    def submit_answer(self, game_id: str, answer: str) -> Optional[dict]:
        game = self._games.get(game_id)
        if game is None:
            return None
        question = game.current_question()
        if question is None:
            return None
        correct = game.submit_answer(answer)
        return {
            "correct": correct,
            "score": game.view_score(),
            "state": game.state.value,
        }

    def pause(self, game_id: str) -> Optional[Game]:
        game = self._games.get(game_id)
        if game is not None:
            game.pause()
        return game

    def resume(self, game_id: str) -> Optional[Game]:
        game = self._games.get(game_id)
        if game is not None:
            game.resume()
        return game

    def view_score(self, game_id: str) -> Optional[int]:
        game = self._games.get(game_id)
        if game is None:
            return None
        return game.view_score()

    def list_games(self) -> List[Game]:
        return list(self._games.values())
