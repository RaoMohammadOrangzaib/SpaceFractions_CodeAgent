"""Space Fractions main application entrypoint."""
from fastapi import FastAPI

from app.services.game_service import GameService
from app.services.question_repository import QuestionRepository
from app.services.user_service import UserService
from app.routers import game, questions, users

# Application-wide service singletons (composition root)
question_repository = QuestionRepository()
game_service = GameService(question_repository)
user_service = UserService()

app = FastAPI(
    title="Space Fractions API",
    description="API for the Space Fractions interactive fraction-learning game",
    version="1.0.0",
)

app.include_router(game.router)
app.include_router(questions.router)
app.include_router(users.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
