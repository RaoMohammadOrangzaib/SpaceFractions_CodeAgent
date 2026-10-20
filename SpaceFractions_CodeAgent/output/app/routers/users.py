"""User authentication API routes (ASR-2: security)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["users"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    id: str
    username: str
    role: str


def get_user_service():
    from app.main import user_service
    return user_service


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    result = get_user_service().authenticate(request.username, request.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(**result)


@router.post("/users", response_model=AuthResponse)
def create_user(request: CreateUserRequest) -> AuthResponse:
    result = get_user_service().create_user(request.username, request.password)
    return AuthResponse(**result)
