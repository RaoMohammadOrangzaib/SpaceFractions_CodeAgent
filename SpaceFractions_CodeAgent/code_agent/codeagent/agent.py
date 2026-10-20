"""The agent loop: preprocess inputs -> LLM tool-calling loop -> project files."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Protocol

from .preprocess_doc import parse_architecture_doc
from .preprocess_views import parse_architecture_views
from .tools import TOOL_SCHEMAS, Toolbox

Log = Callable[[str], None]

SYSTEM_PROMPT = """You are a Code Agent that turns software architecture documentation and UML views \
into a complete, runnable project. You work only through tools: write_file, read_file, list_files, \
check_syntax and finish. All paths are relative to the project root.

Rules:
1. First reason about the inputs (structured JSON of the architecture document and PlantUML views). \
Where the document is inconsistent or incomplete (e.g. mismatched artifact filenames, empty test matrices, \
components in diagrams missing from the document), choose a sensible resolution, and record it in README.md \
under "Assumptions & discrepancies".
2. Produce: full source code for every component, a dependency manifest (requirements.txt or package.json), \
a Dockerfile, README.md (setup, run, layout, traceability), and test cases that cover the requirement IDs (FR/NFR/ASR).
3. Also emit the contract artifacts the document lists (openapi.yaml, internal.proto, SQL DDL, k8s manifest, \
traceability_matrix.csv) when present.
4. Keep the code simple, consistent and runnable. Prefer Python/FastAPI unless the document mandates otherwise.
5. After writing each source file, run check_syntax on it and fix errors.
6. Write complete files; never leave placeholders such as 'TODO: implement'.
7. The full structured inputs are already in the first message; do not re-read docs/*.json with read_file.
8. When done, call list_files to verify, then call finish with a short summary."""

DEFAULT_TASK = ("Implement the system described by the architecture documentation and views as a complete "
                "project in the project root. This is a user-facing web game, so build BOTH the backend services "
                "and a browser frontend: an introductory screen, a main menu, interactive fraction questions with "
                "feedback, a score view, a help view, an admin screen to update questions, and an ending screen. "
                "Write the frontend as plain HTML/CSS/JavaScript (no build tooling) served by the backend at '/', "
                "calling the backend API, and include frontend-facing tests.")


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = ...,
             max_tokens: int = ...) -> dict[str, Any]: ...


def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build_inputs(doc_path: Path, views_path: Path) -> tuple[dict, dict]:
    doc = parse_architecture_doc(Path(doc_path).read_text(encoding="utf-8"))
    views = parse_architecture_views(Path(views_path).read_text(encoding="utf-8"))
    return doc, views


def run_agent(client: ChatClient, doc_path: Path, views_path: Path, out_dir: Path,
              task: str = DEFAULT_TASK, log: Log = print, max_steps: int = 60,
              cancel: threading.Event | None = None,
              progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    out_dir = Path(out_dir)
    doc, views = build_inputs(doc_path, views_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Persist the structured agent input alongside the project for traceability.
    inputs_dir = out_dir / "docs"
    inputs_dir.mkdir(exist_ok=True)
    (inputs_dir / "architecture_doc.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    (inputs_dir / "architecture_views.json").write_text(json.dumps(views, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Parsed inputs: {len(doc['requirement_ids'])} requirement ids, "
        f"{len(doc['components'])} components, {views['diagram_count']} diagrams.")

    tb = Toolbox(out_dir)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"TASK: {task}\n\nARCHITECTURE_DOCUMENTATION_JSON:\n{_compact(doc)}\n\n"
            f"ARCHITECTURE_VIEWS_JSON:\n{_compact(views)}")},
    ]
    steps = 0
    for steps in range(1, max_steps + 1):
        if cancel is not None and cancel.is_set():
            log("Cancelled by user.")
            return {"status": "cancelled", "steps": steps - 1, "files": tb.t_list_files().splitlines()}
        if progress is not None:
            progress(steps - 1, max_steps)
        log(f"[step {steps}] calling model...")
        msg = client.chat(messages, tools=TOOL_SCHEMAS)
        assistant: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("reasoning_content"):
            assistant["reasoning_content"] = msg["reasoning_content"]
        calls = msg.get("tool_calls") or []
        if calls:
            assistant["tool_calls"] = calls
        messages.append(assistant)
        if msg.get("content"):
            log(f"agent: {msg['content'][:300]}")
        if not calls:
            if tb.finished:
                break
            messages.append({"role": "user", "content": "Continue using tools. Call finish when the project is complete."})
            continue
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
                result = tb.call(name, args)
            except (json.JSONDecodeError, ValueError) as e:
                result = f"ERROR: invalid tool arguments: {e}"
            log(f"  tool {name}: {result.splitlines()[0][:120] if result else ''}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        if tb.finished:
            break
    status = "finished" if tb.finished else "max_steps_reached"
    files = tb.t_list_files().splitlines()
    log(f"Done: {status}, {len(files)} files written to {out_dir}")
    return {"status": status, "steps": steps, "summary": tb.summary, "files": files}
