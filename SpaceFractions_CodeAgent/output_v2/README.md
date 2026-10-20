# Space Fractions

A web-based, interactive game to improve fraction-solving skills for sixth-grade
students. The system includes an introductory screen, a main menu, fraction questions
with feedback, a score view, a help view, an admin screen to update questions, and an
ending screen.

## Architecture

The system follows a microservices-inspired design with three logical components:

| Component          | Responsibility                                   | API prefix       |
|--------------------|--------------------------------------------------|------------------|
| `GameComponent`    | Game logic, scoring, user interaction            | `/api/games`     |
| `QuestionComponent`| Question management & data persistence           | `/api/questions` |
| `UserComponent`    | Player registration, login, tokens, admin role   | `/api/users`, `/api/login` |

The backend is a single FastAPI service that also serves the frontend at `/`
to keep the whole project runnable without external orchestration. The component
boundaries are preserved through clear module/route separation and contracts
(`openapi.yaml`, `internal.proto`).

## Setup & Run

### Local (recommended)

```bash
python -m venv .venv && source .venv/bin/activate   # or .\.venv\Scripts\activate on Windows
pip install -r requirements.txt

# Optional but needed for the Admin screen: create the admin account (see "Security")
export SPACE_ADMIN_USERNAME=teacher            # PowerShell: $env:SPACE_ADMIN_USERNAME = "teacher"
export SPACE_ADMIN_PASSWORD='choose-a-long-password'

uvicorn app.main:app --reload --port 8000
```

Then open <http://localhost:8000>. Playing the game needs no login; the Admin screen needs the
admin credentials above.

### Docker

```bash
docker build -t spacefractions:latest .
docker run -p 8080:80 \
  -e SPACE_ADMIN_USERNAME=teacher -e SPACE_ADMIN_PASSWORD='choose-a-long-password' \
  -e SPACE_SECRET_KEY="$(openssl rand -hex 32)" \
  spacefractions:latest
```

Open <http://localhost:8080>.

### Kubernetes (reference)

```bash
kubectl apply -f k8s/spacefractions-deployment.yaml
```

## Security (ASR-2)

- **Admin accounts cannot be created through the API.** The single admin account is created or refreshed at startup from
  `SPACE_ADMIN_USERNAME` and `SPACE_ADMIN_PASSWORD` (password 8-128 characters). If neither is set, no admin exists and the
  Admin screen cannot be used; setting only one of them stops the app at startup.
- `POST /api/users` registers **players only**; any `role` in the request is ignored.
- Passwords are hashed with scrypt (random salt) and never returned or stored in plain text. Login errors are identical for
  an unknown user and a wrong password, and 5 failed attempts lock that username for 60 seconds (HTTP 429).
- `POST /api/login` returns a signed bearer token that expires after `SPACE_TOKEN_TTL_SECONDS` (default 3600). The role is
  re-read from the user store on every request.
- **All question endpoints are admin-only** (401 without a valid token, 403 for a player). Answers are therefore not readable
  by players; the game API never returns them.
- The signing key is `SPACE_SECRET_KEY` (at least 32 characters) or, if unset, a random key stored in `data/secret.key`.
  **With several replicas, set `SPACE_SECRET_KEY` identically on all of them.**
- The frontend keeps the token in memory only, so reloading the page logs the admin out.

Kubernetes secret for the reference manifest:

```bash
kubectl create secret generic spacefractions-secrets \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  --from-literal=admin-username=teacher \
  --from-literal=admin-password='choose-a-long-password'
```

Known limits: there is no HTTPS in the app itself (terminate TLS in front of it, otherwise the token and password cross the
network in clear text), no CSRF concern because tokens are sent in a header rather than a cookie, the login lockout is
per process and in memory, usernames can be locked out by repeated failures, and data lives in local JSON files, so several
replicas do not share users, games or question edits.

## Running tests

Backend API tests:

```bash
pytest tests/test_api.py -q
```

Frontend logic tests (no browser required, uses a DOM shim):

```bash
node tests/test_frontend.js
```

## Project layout

```
.
├── app/                    # FastAPI backend
│   ├── main.py             # Routes (Game/Question/User components)
│   ├── models.py           # Pydantic domain models
│   └── storage.py          # JSON-file persistence layer (durability)
├── static/                 # Frontend (plain HTML/CSS/JS, no build step)
│   ├── index.html          # All screens (intro, menu, game, score, help, admin, ending)
│   ├── style.css
│   └── app.js              # Frontend logic (SpaceFractions module)
├── tests/
│   ├── test_api.py         # Backend API tests (FR-1, NFR-1, ASR-1, ASR-2)
│   └── test_frontend.js    # Frontend logic tests
├── sql/                    # SQL DDL contracts
│   ├── game_ddl.sql
│   └── question_ddl.sql
├── k8s/spacefractions-deployment.yaml
├── openapi.yaml            # REST API contract
├── internal.proto          # Internal gRPC contract
├── traceability_matrix.csv
├── requirements.txt
├── Dockerfile
└── README.md
```

## Traceability

Requirements → components/artifacts are mapped in
[`traceability_matrix.csv`](traceability_matrix.csv). Key mappings:

- **FR-1 (Play game)** → `GameComponent` → `openapi.yaml`, `internal.proto`
- **NFR-1 (Performance)** → `GameComponent` → `internal.proto`, k8s replicas
- **ASR-1 (Data durability)** → `QuestionComponent`/`GameComponent` → SQL DDLs,
  JSON-file persistence in `storage.py`
- **ASR-2 (Security)** → `UserComponent` → scrypt password hashing, signed expiring tokens, admin-only question
  endpoints, login lockout (`app/auth.py`, `app/main.py`, covered by `tests/test_api.py` and `tests/test_frontend.js`)

## Assumptions & discrepancies

The architecture document and views were incomplete or inconsistent in a few places;
the following resolutions were applied:

1. **Single deployable service**: The doc lists many infrastructure options
   (Node/Express, PostgreSQL, Redis, RabbitMQ, Elasticsearch, etc.) but no complete
   runnable contracts. To keep the project runnable and reviewable, the component
   responsibilities are implemented as one FastAPI service with clean route/module
   boundaries and a JSON-file persistence layer. The SQL DDLs (`sql/*.sql`) describe
   the equivalent production schemas.

2. **GameComponent data model**: The doc's `game_ddl.sql` shows only a `games(id,
   game_state JSONB)` table. A richer `game_sessions` table was added to back score
   tracking required by the `View Score` use case and the `Game` class (score attribute).

3. **Question schema expansion**: `ClassDiagram` lists `Question` with `prompt` and
   `options` only, but answering requires a correct answer. Added `correct_index` and
   `explanation` fields.

4. **UserComponent/AdminComponent**: The doc lists `UserComponent` (auth) while the
   views add `AdminComponent` and an `Admin` class. Both are unified in `UserComponent`
   via a `role` field (`player` vs `admin`), preserving the admin "Update Questions"
   use case. The admin role cannot be self-assigned; it comes from environment configuration (see "Security").

5. **ASR-2 mapping**: The traceability table in the doc omits an ASR-2 row even though
   the doc references "ASR-2 (security)" elsewhere. `traceability_matrix.csv` adds the
   ASR-2 → `UserComponent` row.

6. **Empty test matrix**: The testing-strategy matrix (Unit/Integration/Contract/E2E/
   Chaos) was empty. Backend API + frontend tests were implemented to cover FR-1,
   NFR-1, ASR-1, ASR-2 at the unit/integration level.

7. **Frontend screens**: The task's screen requirements (intro, menu, questions,
   score, help, admin, ending) were derived from the use-case diagram (Play Game,
   View Score, Update Questions, View Help) plus the stated end-user flow.

8. **State diagram**: `Paused` was implemented as an implicit concept (game progress
   is preserved server-side) rather than an explicit pause button; pause/resume is
   represented by navigating to the menu without losing state.

9. **Sequence diagram answer-checking**: `Question.check answer` leaks the correct
   option to the backend only; the frontend never receives `correct_index` during
   play (only after an answer, via `correct_answer`). The test suite introspects the
   storage layer to verify correct answers deterministically.
