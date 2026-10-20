# Project Guide: what was built and how

This guide records exactly what was done in this project, in order, so a new reader can understand it, reproduce it
and judge how far it can be trusted. For day-to-day usage, see `README.md`.

## 1. The assignment

The source requirements are in `Task1-EN.docx`. In short:

- Research how open-source "Claude Code" style projects work (references: `ultraworkers/clawcode`,
  `Windy3f3f3f3f/howclaudecodeworks`, `anthropics/claudecode`) and implement a **simplified Code Agent**.
- The LLM must be **DeepSeek V4 Pro through the official API** (no local weights).
- Deliver a **double-click Windows `.exe`** that needs no preinstalled Python, with a minimal GUI for: DeepSeek API key,
  input-file selection, task trigger and output-directory selection. (A CLI-launched web app is an allowed fallback with
  a points penalty; it was not needed.)
- Agent **inputs**: `Architecture_Documentation.md` (preprocessing to structured JSON recommended) and
  `Architecture_View.md` (PlantUML views).
- Agent **outputs** (non-exhaustive): project layout and full source, dependency manifest, optional Dockerfile, README, tests.

> Note: the reference repositories were **not** cloned or read during this work. The agent design (tool-calling loop,
> sandboxed file tools, self-check) follows the general pattern of such agents; it is not a port of any of them.

## 2. The input files

| File | Content |
| --- | --- |
| `Architecture_Documentation.md` | Sections A-L: summary, traceability, components, tech stack, API/proto/SQL snippets, k8s, security, SRE, testing, migration, trade-offs, deliverables |
| `Architecture_View.md` | 13 PlantUML diagrams in 5 views (Scenario, Logic, Process, Development, Physical) for the "Space Fractions" fraction-learning game |

Quirks found in the inputs (the agent is told to reconcile them and record the choices in the generated README):

- `sql/game_ddl.sql` is listed as a deliverable, but the traceability row cites `sql/question_ddl.sql`.
- The test matrix (section H) has empty cells.
- `AdminComponent` appears in the diagrams but not in the document's component list.
- Only four requirement IDs exist: FR-1, NFR-1, ASR-1, ASR-2.
- The document's "Recommended default stack" is Node.js/Express, but its own API snippets are language-neutral.

## 3. DeepSeek API facts used

Taken from the official docs (`https://api-docs.deepseek.com/`) during this work:

- Base URL `https://api.deepseek.com`, endpoint `/chat/completions` (OpenAI-compatible), model id `deepseek-v4-pro`.
- Tool calling uses OpenAI-style `tools` / `tool_choice` and returns `message.tool_calls`; `arguments` is a JSON string that
  may be invalid, so it is validated before use.
- `thinking` can be `enabled` or `disabled`. This project **disables it by default**, which avoids having to round-trip
  `reasoning_content` between tool-calling turns (the docs did not clearly specify that behaviour).

## 4. What was built

Everything lives in `code_agent/`.

```
app.py                     exe entry point (GUI; with arguments it runs the CLI)
codeagent/
  preprocess_doc.py        Architecture_Documentation.md -> structured JSON
  preprocess_views.py      Architecture_View.md (PlantUML) -> structured JSON
  llm.py                   DeepSeek client: retries, error classes, tool calling
  tools.py                 sandboxed tools: write_file, read_file, list_files, check_syntax, finish
  agent.py                 the agent loop
  gui.py                   Tkinter GUI
  cli.py, __main__.py      headless entry point
  config.py                optional settings persistence
tests/test_all.py          12 offline tests (scripted fake model, no network)
build_exe.bat              PyInstaller build
Dockerfile                 optional CLI image
requirements.txt           requests (runtime); pyinstaller, pytest (build/test)
```

### 4.1 Preprocessing

- The documentation parser splits by heading and extracts prose, bullets, tables and fenced code blocks per section, plus the
  requirement IDs (`FR-/NFR-/ASR-n`), `*Component` names and artifact filenames. Headings inside code fences are ignored.
- The views parser extracts, per diagram: name, title, elements (actor, usecase, class, participant, state, package,
  artifact, node, ...), class attributes and methods, relations with arrows and labels, notes, and the raw PlantUML source.
- Both JSON files are also saved into `<output>/docs/` for traceability.

### 4.2 Agent loop (`agent.py`)

1. Parse both inputs and build one prompt: system rules + task + the two JSON documents.
2. Call the model with the tool schemas. Execute every returned tool call and append the results as `tool` messages.
3. Repeat until the model calls `finish`, the user cancels, or **60 steps** are used.
4. Each model call allows up to 16,384 output tokens.

The system prompt tells the model to: reconcile input inconsistencies and record them in the README ("Assumptions &
discrepancies"); produce source, dependency manifest, Dockerfile, README and tests that cover the requirement IDs; emit the
contract artifacts listed in the document; prefer Python/FastAPI unless mandated; run `check_syntax` after writing files;
never leave placeholder code; not re-read the structured inputs it was already given; and `list_files` then `finish` when done.

**The default task** (editable in the GUI's Task box) asks for both the backend services and a browser frontend: an intro
screen, main menu, interactive fraction questions with feedback, a score view, a help view, an admin screen to update
questions and an ending screen, written as plain HTML/CSS/JavaScript with no build tooling and served by the backend at `/`.
This was not the original default: see section 6, "Run 1" versus "Run 2".

### 4.3 Tools and safety (`tools.py`)

- All paths are resolved against the output directory; `..` and absolute paths outside it are rejected (tested).
- There is **no shell or command execution**, only file tools. This keeps the agent safe and lets it work inside the frozen exe.
- `check_syntax` validates `.py` (via `ast`), `.json`, basic `.yaml` (tab check; full parse only if PyYAML is installed, and it is
  **not** bundled in the exe), `.proto` and `.sql` (brace/parenthesis balance only). It does **not** run the generated code.

### 4.4 GUI (`gui.py`)

API key (masked, with Show and an optional "Remember key on this PC"), model name, documentation and views pickers,
output folder picker, editable task text, Run / Cancel / Open output folder, a determinate progress bar with step status,
a live file tree of the output folder (double-click opens a file), the agent log, and a post-run summary (status, steps,
files and size, elapsed time, agent summary, errors). Cancel takes effect after the current model call.

### 4.5 Packaging

`python -m PyInstaller --noconfirm --clean --onefile --windowed --name CodeAgent app.py` produces `dist/CodeAgent.exe`
(about 15.9 MB, single file). `build_exe.bat` does the same after installing the requirements.

## 5. How to reproduce

```
cd code_agent
python -m pip install -r requirements.txt
python -m pytest -q                      # 12 tests, no network or key needed
build_exe.bat                            # builds dist\CodeAgent.exe
```

Run the agent from the command line (needs Python and a key in the environment):

```
set DEEPSEEK_API_KEY=your-key
python -m codeagent --doc ..\Architecture_Documentation.md --views ..\Architecture_View.md --out ..\output_v2
```

To run the generated game (Run 2) in a virtual environment:

```
cd ..\output_v2
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                      # 36 Python tests
node tests\test_frontend.js              # frontend logic tests (needs Node.js)
set SPACE_ADMIN_USERNAME=teacher         # needed only for the Admin screen
set SPACE_ADMIN_PASSWORD=choose-a-long-password
python -m uvicorn app.main:app --port 8000
```

Then open http://127.0.0.1:8000/ for the game and http://127.0.0.1:8000/docs for the API. Without the two `SPACE_ADMIN_*`
variables the game works but no admin exists (see "Manual fixes to Run 2" in section 6).

Or double-click `dist\CodeAgent.exe` and fill in the form.

## 6. What was verified, and what was not

Verified:

- The 12 offline tests pass: both parsers (on synthetic and the real input files), the path sandbox, syntax checks, the agent
  loop with a scripted model (including malformed tool arguments and cancellation), the progress callback, the summary text
  and the GUI file-tree logic.
- The PyInstaller exe builds and starts and stays running.
- **Two real end-to-end runs** against `deepseek-v4-pro`, both through the command line (same agent code as the GUI).

  **Run 1 (backend only), folder `output/`.** The original default task said only "implement the system", and the prompt
  preferred Python/FastAPI, so the model built just the three backend services. 12 model steps, 27 files (including the two
  JSON inputs): a FastAPI app (game, question and user routers/services), `openapi.yaml`, `internal.proto`, two SQL DDL files,
  a Kubernetes manifest, `traceability_matrix.csv`, Dockerfile, README and tests. In a clean virtual environment it installed
  and its **19 tests passed**. This does not match the architecture document's description of a web game with an intro,
  menu, questions and ending, so a second run was made.

  **Run 2 (backend + frontend), folder `output_v2/`.** After changing the default task and prompt (section 4.2): 29 model
  steps, 22 files including `static/index.html`, `static/app.js` and `static/style.css`, plus the same contract artifacts.
  - As the model wrote it, the **7 Python tests passed** in a clean virtual environment.
  - The generated **frontend JS test file failed on its first run** ("showScreen deactivates the intro screen"). The app code was
    correct; the test's fake DOM returned no `.screen` elements. The agent cannot run code, so it could not catch the flaw itself.
  - The app was **started and played in a browser**: intro, main menu, a question with correct-answer feedback and score,
    the score screen and the ending screen all worked, with no console errors. The game was clicked through quickly rather
    than played carefully, and the Help screen was not opened.

  **Manual fixes to Run 2.** `output_v2/` is therefore *the model's output plus two sets of fixes written by hand afterwards*,
  not the unmodified output of the agent:
  1. **Frontend test shim:** the fake DOM's `querySelectorAll` in `tests/test_frontend.js` now returns the `screen-*` elements.
  2. **Authentication (security).** The model's code let anyone register as `admin` (`POST /api/users` with `role: "admin"`),
     and the create/update/delete/list question endpoints checked no credentials; the "admin login" only sent a username, and
     `GET /api/questions` also exposed every correct answer to anyone. This was fixed by hand with the Python standard library
     only (no new dependencies): scrypt password hashing (`app/auth.py`), HMAC-signed expiring bearer tokens, `POST /api/login`
     with a per-username lockout, `GET /api/users/me`, an admin-only guard on all five question endpoints (role re-read from the
     store on each request), registration that always creates a *player*, the admin account created only from
     `SPACE_ADMIN_USERNAME` / `SPACE_ADMIN_PASSWORD`, input validation on questions (e.g. `correct_index` in range), a password
     field and logout in the frontend (token held in memory), and updates to `openapi.yaml`, the Kubernetes manifest (secrets
     for the signing key and admin account), the README and the traceability matrix.
     After the fix: the **36 Python tests pass** (including every question endpoint with no token and with a player token, a
     forged and an expired token, the old register-as-admin exploit, lockout, and passwords not stored in plain text) and all
     frontend tests pass. One test was checked to be meaningful by removing the guard from one endpoint, which made it fail.
     The fixed app was also exercised with real HTTP requests and in the browser (wrong password, admin login, add and delete
     a question, an out-of-range question rejected with a readable error, logout).

Not verified:

- The **latest rebuilt exe could not be launched** on the development machine: Windows Application Control blocked it ("An
  Application Control policy has blocked this file"). Earlier builds of the same source did launch there. The exe is unsigned,
  so the same block may happen on other machines. If it does, run the app from source with `python app.py` (needs Python)
  or sign the exe with a code-signing certificate.
- The **GUI with the real API** (both real runs used the CLI). The GUI window was not inspected visually.
- The exe on a **clean machine without Python** (it was only run on the development machine).
- The generated projects' **Docker images and Kubernetes manifests** were never built or applied (including the new Secret
  references); neither app has been load-tested against its NFR-1 performance target.
- The authentication fix has **not had an independent security review or penetration test**. It was written and tested by the
  same assistant, and it is not a substitute for a review before real use.
- Only two real runs were done, and model output varies between runs.

Known weaknesses of the generated projects:

- **The agent produced insecure authentication in Run 2** (details in "Manual fixes to Run 2"). The fix is manual and lives only
  in `output_v2/`; **running the agent again can reproduce the original flaw**, because nothing in its prompt requires secure
  authentication yet.
- Remaining limits of the fixed `output_v2/` auth: no HTTPS in the app itself (terminate TLS in front of it), the login
  lockout is in memory and per process (so a username can also be locked out by someone else's failed attempts), and JSON-file
  storage means several replicas do not share users or question edits.
- Run 2 stores data in JSON files under `./data` (set `SPACE_DATA_DIR` to change); the SQL DDL files exist but nothing connects
  to PostgreSQL. Run 1 held its data in memory.
- Run 1 hashed passwords with salted SHA-256, which is weak. A real system should use bcrypt or argon2. Run 2 originally had no passwords; the manual fix uses scrypt.
- Run 2 uses a single FastAPI service instead of separate microservices, and its README says so.
- Run 1's README refers to "Rule 5" of the brief; the prompt's actual rule is 4. This is cosmetic.

Observed agent behaviour: in Run 1 the model spent a couple of steps re-reading the JSON it had already been given. After the
prompt fix, Run 2 no longer did, but it tried `read_file` with `offset` and `limit` arguments, which the tool does not
support, and got an error twice before continuing. Adding those optional arguments would be a small improvement.

Known weaknesses of the agent itself:

- It is a simplified agent: single model, no planning stage, no code execution or test running, and no resume if cancelled.
- The whole structured input is sent in the first message; very large inputs could exceed the model's context window.
- Syntax checks are shallow, so a generated file can pass them and still fail at runtime.

## 7. Security notes before sharing

- **Never commit or send an API key.** The key is entered at run time. The CLI reads it from the `DEEPSEEK_API_KEY` environment
  variable. The GUI stores it in `%APPDATA%\CodeAgent\settings.json` (plain text) only if "Remember key" is ticked; nothing in
  this folder contains a key.
- This project's key was set as a user environment variable with `setx`. If it was ever pasted anywhere else, rotate it in the
  DeepSeek console.
- `build/`, `dist/`, `CodeAgent.spec` and `__pycache__/` are build artifacts and can be omitted from a source share; share the
  exe separately if needed. The exe is unsigned, so Windows SmartScreen may warn on first run.
- The agent sends the contents of the two input files to DeepSeek's servers. Do not use confidential documents unless that is acceptable.

## 8. Suggested next steps

1. Run the GUI exe once with a real key and on a machine without Python.
2. Improve generated output and tools: wire PostgreSQL in (the SQL DDL files are currently unused), and support
   `offset`/`limit` in the `read_file` tool.
3. Add a security rule to the agent's system prompt (privileged endpoints must require authentication; roles must never be
   client-supplied; passwords hashed with a slow hash) so the auth flaw is not regenerated, then rebuild the exe.
4. Add a code-execution tool (for example running the generated tests) so the agent can fix runtime errors, not just syntax errors.
5. Initialise a git repository and add a `.gitignore` for `build/`, `dist/`, `__pycache__/` and generated output folders (`output/`, `output_v2/`, or commit the one you want to keep as a sample).
