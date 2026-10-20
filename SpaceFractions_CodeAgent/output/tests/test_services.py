"""Unit and integration tests for services (component-level)."""
from app.services.game_service import GameService
from app.services.question_repository import QuestionRepository
from app.services.user_service import UserService
from app.models.domain import Question


def test_question_repository_persistence():
    # ASR-1: data durability - repository retains data across reads/lists
    repo = QuestionRepository()
    initial = len(repo.list_questions())
    assert initial >= 4
    q = Question(id="q-extra", prompt="p", options=["a"], correct_answer="a")
    repo.add(q)
    assert repo.get("q-extra") is not None
    assert len(repo.list_questions()) == initial + 1
    repo.delete("q-extra")
    assert repo.get("q-extra") is None


def test_question_repository_update():
    repo = QuestionRepository()
    q = Question(id="q1", prompt="new prompt", options=["x"], correct_answer="x")
    repo.update(q)
    assert repo.get("q1").prompt == "new prompt"


def test_game_service_full_flow():
    repo = QuestionRepository()
    service = GameService(repo)
    game = service.start_game()
    assert game.id is not None

    prompt = service.get_prompt(game.id)
    assert prompt is not None
    assert prompt["prompt"] != ""
    assert isinstance(prompt["options"], list)

    # Answer with the known correct answer for q1 (3/4)
    result = service.submit_answer(game.id, "3/4")
    assert result is not None
    assert "correct" in result
    assert result["score"] == 1

    score = service.view_score(game.id)
    assert score == 1


def test_game_service_pause_resume():
    repo = QuestionRepository()
    service = GameService(repo)
    game = service.start_game()
    service.pause(game.id)
    assert service.get_game(game.id).state.value == "paused"
    service.resume(game.id)
    assert service.get_game(game.id).state.value == "playing"


def test_user_service_authentication():
    service = UserService()
    # Seeded admin can authenticate
    auth = service.authenticate("admin", "admin123")
    assert auth is not None
    assert auth["role"] == "admin"

    # Wrong password fails
    assert service.authenticate("admin", "wrong") is None

    # New user creation + auth
    service.create_user("student", "pass123")
    user_auth = service.authenticate("student", "pass123")
    assert user_auth is not None
    assert user_auth["role"] == "user"


def test_user_service_role_checks_asr2():
    service = UserService()
    assert service.is_admin("admin") is True
    service.create_user("student", "pass")
    assert service.is_admin("student") is False
    assert service.is_admin("nobody") is False
