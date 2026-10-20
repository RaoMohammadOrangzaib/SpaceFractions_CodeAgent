/* Space Fractions frontend logic (plain JS, no build tooling). */

const SpaceFractions = (function () {
  // ---------- State ----------
  let state = {
    gameId: null,
    currentQuestion: null,
    questionIndex: 0,
    totalQuestions: 0,
    score: 0,
    username: null,
    token: null, // bearer token, kept in memory only (never localStorage)
    isAdmin: false,
    editingQuestionId: null,
  };

  // ---------- Screen management ----------
  function showScreen(name) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
    const target = document.getElementById("screen-" + name);
    if (target) target.classList.add("active");
  }

  // ---------- API helpers ----------
  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    const res = await fetch(path, { ...options, headers });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      let detail = body.detail;
      if (Array.isArray(detail)) {
        // FastAPI validation errors: [{loc, msg, ...}] -> readable text
        detail = detail.map((d) => String(d.msg || "").replace(/^Value error, /, "")).filter(Boolean).join("; ");
      }
      const err = new Error(typeof detail === "string" && detail ? detail : "Request failed (" + res.status + ")");
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  // ---------- Game flow ----------
  async function startGame() {
    const game = await api("/api/games", { method: "POST" });
    state.gameId = game.id;
    state.score = 0;
    state.totalQuestions = game.question_ids.length;
    await loadQuestion();
    showScreen("game");
  }

  async function loadQuestion() {
    const data = await api("/api/games/" + state.gameId + "/question");
    if (data.finished) {
      finishGame();
      return;
    }
    state.currentQuestion = data.question;
    state.questionIndex = data.question_index;
    state.totalQuestions = data.total_questions;

    document.getElementById("question-prompt").textContent = data.question.prompt;
    document.getElementById("hud-score").textContent = "Score: " + state.score;
    document.getElementById("hud-progress").textContent =
      "Question " + (state.questionIndex + 1) + "/" + state.totalQuestions;

    const optionsEl = document.getElementById("question-options");
    optionsEl.innerHTML = "";
    data.question.options.forEach((opt, i) => {
      const btn = document.createElement("button");
      btn.textContent = opt;
      btn.dataset.index = i;
      btn.addEventListener("click", () => submitAnswer(i));
      optionsEl.appendChild(btn);
    });

    const feedback = document.getElementById("feedback");
    feedback.classList.add("hidden");
    feedback.textContent = "";
    document.getElementById("next-button").classList.add("hidden");
  }

  async function submitAnswer(index) {
    const res = await api("/api/games/" + state.gameId + "/answer", {
      method: "POST",
      body: JSON.stringify({ answer_index: index }),
    });
    state.score = res.score;

    document.getElementById("hud-score").textContent = "Score: " + state.score;

    const feedback = document.getElementById("feedback");
    feedback.classList.remove("hidden");
    if (res.correct) {
      feedback.textContent = "✅ Correct! " + res.explanation;
      feedback.className = "feedback correct";
    } else {
      feedback.textContent =
        "❌ Not quite. Correct answer: " + res.correct_answer + ". " + res.explanation;
      feedback.className = "feedback wrong";
    }

    // Highlight options: mark the correct answer and the user's wrong pick.
    const optionsEl = document.getElementById("question-options");
    const correctIndex = state.currentQuestion.options.indexOf(res.correct_answer);
    Array.from(optionsEl.children).forEach((btn, i) => {
      btn.disabled = true;
      if (i === correctIndex) {
        btn.classList.add("correct");
      } else if (i === index && !res.correct) {
        btn.classList.add("wrong");
      }
    });

    if (res.finished) {
      document.getElementById("next-button").textContent = "See Score ▶";
      document.getElementById("next-button").classList.remove("hidden");
      document.getElementById("next-button").dataset.nextAction = "finish";
    } else {
      document.getElementById("next-button").textContent = "Next ▶";
      document.getElementById("next-button").classList.remove("hidden");
      document.getElementById("next-button").dataset.nextAction = "next";
    }
  }

  function handleNext() {
    const btn = document.getElementById("next-button");
    if (btn.dataset.nextAction === "finish") {
      finishGame();
    } else {
      loadQuestion();
    }
  }

  async function finishGame() {
    const res = await api("/api/games/" + state.gameId + "/score");
    document.getElementById("final-score").textContent = res.score;
    document.getElementById("final-detail").textContent =
      "You answered " + res.total_answered + " question(s).";
    showScreen("score");
  }

  function showEnding() {
    const score = parseInt(document.getElementById("final-score").textContent, 10);
    const total = state.totalQuestions;
    let msg;
    if (score === total) msg = "Perfect score! You're a fraction master of the galaxy! 🏅";
    else if (score >= total / 2) msg = "Great work! Keep practicing to reach the stars! 🌠";
    else msg = "Good effort! Review the help screen and try again, cadet! 🛸";
    document.getElementById("ending-message").textContent = msg;
    showScreen("ending");
  }

  // ---------- Admin flow ----------
  async function adminLogin() {
    const username = document.getElementById("admin-username").value.trim();
    const password = document.getElementById("admin-password").value;
    const status = document.getElementById("admin-status");
    if (!username || !password) {
      status.textContent = "Enter your username and password.";
      return;
    }
    try {
      const data = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ username: username, password: password }),
      });
      document.getElementById("admin-password").value = "";
      if (data.role !== "admin") {
        status.textContent = "This account is not an administrator.";
        return;
      }
      state.token = data.token;
      state.username = data.username;
      state.isAdmin = true;
      status.textContent = "";
      document.getElementById("admin-login").classList.add("hidden");
      document.getElementById("admin-panel").classList.remove("hidden");
      await loadAdminQuestions();
    } catch (e) {
      status.textContent = "Login failed: " + e.message;
    }
  }

  function logout(message) {
    state.token = null;
    state.username = null;
    state.isAdmin = false;
    document.getElementById("admin-panel").classList.add("hidden");
    document.getElementById("admin-login").classList.remove("hidden");
    document.getElementById("admin-status").textContent = message || "";
  }

  // Run an admin action; on 401/403 return to the login form, otherwise show the error.
  async function adminCall(fn) {
    try {
      await fn();
    } catch (e) {
      if (e.status === 401 || e.status === 403) {
        logout("Your session has ended. Please log in again.");
      } else {
        document.getElementById("admin-message").textContent = "Error: " + e.message;
      }
    }
  }

  async function loadAdminQuestions() {
    document.getElementById("admin-message").textContent = "";
    const data = await api("/api/questions");
    const listEl = document.getElementById("admin-question-list");
    listEl.innerHTML = "";
    data.questions.forEach((q) => {
      const div = document.createElement("div");
      div.className = "q-item";
      const label = document.createElement("span");
      label.textContent = q.id + ": " + q.prompt;
      div.appendChild(label);

      const actions = document.createElement("span");
      const edit = document.createElement("button");
      edit.textContent = "Edit";
      edit.addEventListener("click", () => editQuestion(q));
      const del = document.createElement("button");
      del.textContent = "Delete";
      del.addEventListener("click", () => deleteQuestion(q.id));
      actions.appendChild(edit);
      actions.appendChild(del);
      div.appendChild(actions);
      listEl.appendChild(div);
    });
  }

  function editQuestion(q) {
    document.getElementById("q-id").value = q.id;
    document.getElementById("q-prompt").value = q.prompt;
    document.getElementById("q-options").value = q.options.join(", ");
    document.getElementById("q-correct").value = q.correct_index;
    document.getElementById("q-explanation").value = q.explanation || "";
    state.editingQuestionId = q.id;
  }

  function saveQuestion() {
    return adminCall(doSaveQuestion);
  }

  async function doSaveQuestion() {
    const qid = document.getElementById("q-id").value;
    const payload = {
      prompt: document.getElementById("q-prompt").value,
      options: document
        .getElementById("q-options")
        .value.split(",")
        .map((s) => s.trim()),
      correct_index: parseInt(document.getElementById("q-correct").value, 10),
      explanation: document.getElementById("q-explanation").value,
    };

    if (qid) {
      await api("/api/questions/" + qid, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/api/questions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    resetQuestionForm();
    await loadAdminQuestions();
  }

  function deleteQuestion(id) {
    return adminCall(async () => {
      await api("/api/questions/" + id, { method: "DELETE" });
      await loadAdminQuestions();
    });
  }

  function resetQuestionForm() {
    document.getElementById("q-id").value = "";
    document.getElementById("q-prompt").value = "";
    document.getElementById("q-options").value = "";
    document.getElementById("q-correct").value = "";
    document.getElementById("q-explanation").value = "";
    state.editingQuestionId = null;
  }

  // ---------- Event wiring ----------
  function bind() {
    document.querySelectorAll("[data-action]").forEach((el) => {
      el.addEventListener("click", () => {
        const action = el.dataset.action;
        if (action === "go-menu") {
          showScreen("menu");
        } else if (action === "start-game") {
          startGame();
        } else if (action === "show-help") {
          showScreen("help");
        } else if (action === "show-admin") {
          showScreen("admin");
        } else if (action === "admin-login") {
          adminLogin();
        } else if (action === "admin-logout") {
          logout();
        } else if (action === "save-question") {
          saveQuestion();
        } else if (action === "next-question") {
          handleNext();
        } else if (action === "show-ending") {
          showEnding();
        }
      });
    });
  }

  return {
    init: function () {
      bind();
      showScreen("intro");
    },
    // Expose internals for testing.
    _state: state,
    showScreen: showScreen,
    _api: api,
    adminLogin: adminLogin,
    logout: logout,
  };
})();

document.addEventListener("DOMContentLoaded", function () {
  SpaceFractions.init();
});
