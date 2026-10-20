"""Unit tests for domain models (Class/State diagram behavior)."""
from app.models.domain import Admin, Game, GameState, Question, User


def make_game():
    questions = [
        Question(id="q1", prompt="1/2 + 1/4?", options=["3/4", "1/4"],
                 correct_answer="3/4"),
        Question(id="q2", prompt="2/3 - 1/6?", options=["1/2", "1/3"],
                 correct_answer="1/2"),
    ]
    return Game(id="g1", questions=questions)


def test_question_getters():
    q = Question(id="q1", prompt="p", options=["a", "b"], correct_answer="b")
    assert q.get_prompt() == "p"
    assert q.get_options() == ["a", "b"]


def test_question_check_answer_is_case_insensitive():
    q = Question(id="q1", prompt="p", options=["3/4"], correct_answer="3/4")
    assert q.check_answer(" 3/4 ") is True
    assert q.check_answer("1/4") is False


def test_game_state_transitions():
    game = make_game()
    assert game.state == GameState.PLAYING
    game.pause()
    assert game.state == GameState.PAUSED
    game.resume()
    assert game.state == GameState.PLAYING
    game.game_over()
    assert game.state == GameState.GAME_OVER


def test_game_score_tracking_and_completion():
    game = make_game()
    # First answer correct
    assert game.submit_answer("3/4") is True
    assert game.view_score() == 1
    # Second answer incorrect -> game over
    assert game.submit_answer("1/3") is False
    assert game.state == GameState.GAME_OVER
    assert game.view_score() == 1


def test_user_play_and_view_score():
    game = make_game()
    user = User(id="u1", username="student")
    user.play_game(game)
    assert game.state == GameState.PLAYING
    assert user.view_score(game) == 0


def test_admin_update_questions():
    q1 = Question(id="q1", prompt="p", options=["a"], correct_answer="a")
    q2 = Question(id="q2", prompt="p2", options=["b"], correct_answer="b")
    admin = Admin(id="a1", username="admin")
    admin.update_questions([q1, q2])
    assert len(admin.updated_questions) == 2
