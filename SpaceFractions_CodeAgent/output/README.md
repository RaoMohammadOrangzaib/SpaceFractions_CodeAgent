# Space Fractions System

A web-based, interactive learning tool that improves fraction-solving skills for
sixth-grade students. Implements the microservices architecture described in the
architecture documentation and the 13 PlantUML views (Scenario, Logic, Process,
Development, Physical).

## Overview

The system is composed of three logical components:

- **GameComponent** — game logic and user interaction, owns game state.
- **QuestionComponent** — question management and data persistence.
- **UserComponent** — user authentication and authorization (incl. Admin role).

## Project Layout

```
├── app/
│   ├── main.py                          # FastAPI app + composition root
│   ├── models/domain.py                 # Game, Question, User, Admin (Class/State diagrams)
│   ├── routers/
│   │   ├── game.py                      # FR-1 game endpoints
│   │   ├── questions.py                 # Question + admin endpoints
│   │   └── users.py                     # Login / create user (ASR-2)
│   └── services/
│       ├── game_service.py              # Game orchestration (SequenceDiagram1)
│       ├── question_repository.py       # Question persistence (ASR-1)
│       └── user_service.py              # Authn/authz (ASR-2)
├── tests/
│   ├── test_domain.py                   # Unit: models + state transitions
│   ├── test_services.py                 # Unit/Integration: services
│   └── test_api.py                      # Contract/E2E: API endpoints
├── openapi.yaml                         # External API contract
├── internal.proto                       # Internal RPC contract (GameService)
├── sql/game_ddl.sql                     # Game data schema
├── sql/question_ddl.sql                 # Question data schema
├── k8s/spacefractions-deployment.yaml   # Kubernetes deployment
├── traceability_matrix.csv              # Requirement -> component/artifact mapping
├── requirements.txt
├── Dockerfile
└── README.md
```

## Setup & Run

### Local (no container)

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker build -t spacefractions:latest .
docker run -p 8000:8000 spacefractions:latest
```

### Run tests

```bash
pytest -q
```

## API Quick Reference

| Method | Path | Purpose | Requirement |
|--------|------|---------|-------------|
| GET    | `/play` | Start a game session | FR-1 |
| POST   | `/games` | Start a game with question selection | FR-1 |
| GET    | `/games/{id}/prompt` | Current question prompt | FR-1 |
| POST   | `/games/{id}/answer` | Submit an answer | FR-1 |
| GET    | `/games/{id}/score` | View score | FR-1 |
| GET    | `/questions` | List questions | — |
| POST   | `/questions` | Create question (admin) | ASR-2 |
| PUT    | `/questions/{id}` | Update question (admin) | ASR-2 |
| POST   | `/login` | Authenticate | ASR-2 |
| POST   | `/users` | Create user | ASR-2 |

## Traceability

See `traceability_matrix.csv` for the full requirement-to-component/artifact
mapping. Summary:

- **FR-1** (Play game) → `GameComponent`, `openapi.yaml`, `app/routers/game.py`
- **NFR-1** (Performance) → `GameComponent`, `internal.proto`
- **ASR-1** (Data durability) → `QuestionComponent`, `sql/question_ddl.sql`, `sql/game_ddl.sql`
- **ASR-2** (Security) → `UserComponent`, `app/services/user_service.py`, role-based admin access

## Assumptions & Discrepancies

The following resolutions were made where the architecture document was
inconsistent or incomplete:

1. **Language/runtime** — The document recommends Node.js/Express, but Rule 5 of
   the implementation brief prefers Python/FastAPI unless mandated. The
   document lists Node.js as an *option* (among several), not a mandate, so the
   implementation uses **Python/FastAPI**. All component responsibilities,
   APIs, and schemas are preserved.
2. **`UserComponent` missing from SQL artifacts** — The artifacts list does not
   include a `sql/user_ddl.sql`, and UserComponent has no data model in Section D.
   Users are held in an in-memory `UserService` with salted SHA-256 password
   hashing (ASR-2). No user DDL was emitted because none was specified.
3. **`AdminComponent`** — Present in the Component/Container/Package diagrams but
   *not* in the document's `components` list (`GameComponent`,
   `QuestionComponent`, `UserComponent`). It is modeled as the admin role within
   `UserComponent` (admin question management endpoints with authorization).
4. **`sql/question_ddl.sql` and `sql/game_ddl.sql` naming** — `game_ddl.sql` is
   listed in `artifacts` as a deliverable, and `question_ddl.sql` is referenced
   by the traceability matrix, but only the `games` DDL body appears in the
   document. Both DDL files are emitted; `question_ddl.sql` was authored to match
   the `Question` model (id, prompt, options JSONB, correct_answer).
5. **Empty test matrices** — The Unit/Integration/Contract/E2E/Chaos test matrix
   has empty cells. A sensible set of tests was authored covering FR-1, NFR-1,
   ASR-1, and ASR-2 (domain unit tests, service integration tests, API contract
   tests). Chaos tests are out of scope for a local runnable project and are
   documented as such in Section H.
6. **`NFR-1` only maps to GameComponent** — The traceability matrix maps NFR-1
   to `internal.proto`/`GameComponent`. The internal gRPC-like contract
   (`GameService.Play`) is emitted as `internal.proto` for the
   Game↔Question interaction implied by `SequenceDiagram1`.
7. **`internal.proto` content** — Only a minimal `Play` RPC was specified; it is
   emitted verbatim. No gRPC server is generated (the runnable service uses
   REST/HTTP), but the contract artifact is preserved.
8. **Persistence technology** — The document lists PostgreSQL, Redis, RabbitMQ,
   Elasticsearch, etc. To keep the project simple and runnable without external
   services, the runnable implementation uses in-memory repositories behind
   stable interfaces, while the PostgreSQL DDL files (`sql/*.sql`) define the
   production schema.
9. **Kubernetes manifest** — Emitted verbatim from the document (`containerPort:
   80`). The Dockerfile exposes port 8000 with uvicorn; the k8s snippet is
   preserved as specified and can be adjusted to map port 80 → 8000 in
   production ingress/Service configuration.
