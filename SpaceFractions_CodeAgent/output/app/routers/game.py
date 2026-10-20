"""Game API routes (FR-1: Play game, NFR-1: Performance)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.game_service import GameService

router = APIRouter(tags=["game"])


class StartGameRequest(BaseModel):
    question_ids: Optional[List[str]] = None


class SubmitAnswerRequest(BaseModel):
    answer: str


def get_game_service() -> GameService:
    from app.main import game_service
    return game_service


@router.get("/play")
def play() -> dict:
    """Start a new game session (FR-1)."""
    game = get_game_service().start_game()
    return {"gameId": game.id, "state": game.state.value, "score": 0}


@router.post("/games")
def start_game(request: StartGameRequest) -> dict:
    game = get_game_service().start_game(request.question_ids)
    return {"gameId": game.id, "state": game.state.value, "score": 0}


@router.get("/games/{game_id}/prompt")
def get_prompt(game_id: str) -> dict:
    prompt = get_game_service().get_prompt(game_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Game not found or completed")
    return prompt


@router.post("/games/{game_id}/answer")
def submit_answer(game_id: str, request: SubmitAnswerRequest) -> dict:
    result = get_game_service().submit_answer(game_id, request.answer)
    if result is None:
        raise HTTPException(status_code=404, detail="Game not found or completed")
    return result


@router.post("/games/{game_id}/pause")
def pause(game_id: str) -> dict:
    game = get_game_service().pause(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"gameId": game.id, "state": game.state.value}


@router.post("/games/{game_id}/resume")
def resume(game_id: str) -> dict:
    game = get_game_service().resume(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"gameId": game.id, "state": game.state.value}


@router.get("/games/{game_id}/score")
def view_score(game_id: str) -> dict:
    score = get_game_service().view_score(game_id)
    if score is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"gameId": game_id, "score": score}
