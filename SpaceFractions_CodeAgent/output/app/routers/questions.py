"""Question and admin API routes (Admin: Update Questions use case)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.models.domain import Question
from app.services.question_repository import QuestionRepository

router = APIRouter(tags=["questions"])


class QuestionIn(BaseModel):
    id: str
    prompt: str
    options: List[str]
    correct_answer: str


class QuestionOut(BaseModel):
    id: str
    prompt: str
    options: List[str]
    correct_answer: str


def get_repository() -> QuestionRepository:
    from app.main import question_repository
    return question_repository


def get_user_service():
    from app.main import user_service
    return user_service


def require_admin(authorization: Optional[str] = Header(None)) -> None:
    """Enforce ASR-2 (security): admin-only question management."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing credentials")
    username = authorization[len("Bearer "):]
    if not get_user_service().is_admin(username):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/questions", response_model=List[QuestionOut])
def list_questions() -> List[QuestionOut]:
    return [QuestionOut(**q.__dict__) for q in get_repository().list_questions()]


@router.post("/questions", response_model=QuestionOut,
             dependencies=[Depends(require_admin)])
def create_question(question: QuestionIn) -> QuestionOut:
    q = get_repository().add(Question(**question.model_dump()))
    return QuestionOut(**q.__dict__)


@router.put("/questions/{question_id}", response_model=QuestionOut,
            dependencies=[Depends(require_admin)])
def update_question(question_id: str, question: QuestionIn) -> QuestionOut:
    if question.id != question_id:
        raise HTTPException(status_code=400, detail="ID mismatch")
    q = get_repository().update(Question(**question.model_dump()))
    return QuestionOut(**q.__dict__)
