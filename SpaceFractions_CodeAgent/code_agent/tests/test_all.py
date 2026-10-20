import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codeagent.agent import run_agent  # noqa: E402
from codeagent.preprocess_doc import parse_architecture_doc  # noqa: E402
from codeagent.preprocess_views import parse_architecture_views  # noqa: E402
from codeagent.tools import Toolbox  # noqa: E402

DOC = """# A. Summary
Intro text.

| ASR/NFR ID | Test Type |
| --- | --- |
| ASR-1 (data durability) | Unit testing |

# B. Trace
* FR-1 play game via GameComponent
```yml
openapi: 3.0.0
```
"""

VIEWS = """## ScenarioView
1. UseCase — Scenario View: Use Case Diagram
```plantuml
@startuml UseCaseDiagram
actor EndUser as "End User"
usecase "Play Game" as (PlayGame)
EndUser -- (PlayGame)
@enduml
```
## LogicView
2. Class — Logic View: Class Diagram
```plantuml
@startuml ClassDiagram
class Game {
  - id: string
  + play(): void
}
class Question {
  - id: string
}
Game --* Question
@enduml
```
```plantuml
@startuml Seq
participant User
participant Game
User->>Game: play()
@enduml
```
"""


def test_doc_parser():
    d = parse_architecture_doc(DOC)
    assert d["requirement_ids"] == ["ASR-1", "FR-1"]
    assert "GameComponent" in d["components"]
    sec = {s["title"]: s for s in d["sections"]}
    assert sec["A. Summary"]["tables"][0]["rows"][0]["Test Type"] == "Unit testing"
    assert sec["B. Trace"]["code_blocks"][0]["lang"] == "yml"
    assert sec["B. Trace"]["bullets"]


def test_doc_parser_ignores_heading_inside_fence():
    d = parse_architecture_doc("# T\n```markdown\n# not a heading\n```\n")
    assert [s["title"] for s in d["sections"]] == ["T"]


def test_views_parser():
    v = parse_architecture_views(VIEWS)
    assert v["diagram_count"] == 3
    uc = v["views"][0]["diagrams"][0]
    assert uc["name"] == "UseCaseDiagram"
    assert {"kind": "usecase", "name": "PlayGame", "label": "Play Game"} in uc["elements"]
    assert uc["relations"][0]["from"] == "EndUser"
    cls = v["views"][1]["diagrams"][0]
    assert cls["classes"]["Game"]["methods"] == ["+ play(): void"]
    assert cls["classes"]["Game"]["attributes"] == ["- id: string"]
    assert cls["relations"][0]["to"] == "Question"
    seq = v["views"][1]["diagrams"][1]
    assert seq["relations"][0]["label"] == "play()"


def test_real_inputs_parse_if_present():
    root = Path(__file__).resolve().parents[2]
    doc, views = root / "Architecture_Documentation.md", root / "Architecture_View.md"
    if not (doc.exists() and views.exists()):
        pytest.skip("sample inputs not present")
    d = parse_architecture_doc(doc.read_text(encoding="utf-8"))
    v = parse_architecture_views(views.read_text(encoding="utf-8"))
    assert {"FR-1", "NFR-1", "ASR-1", "ASR-2"} <= set(d["requirement_ids"])
    assert v["diagram_count"] == 13  # 11 numbered diagrams; sequence + collaboration have two scenarios each


def test_toolbox_sandbox(tmp_path):
    tb = Toolbox(tmp_path)
    assert tb.call("write_file", {"path": "a/b.py", "content": "x = 1\n"}).startswith("wrote")
    assert (tmp_path / "a" / "b.py").read_text() == "x = 1\n"
    assert tb.call("write_file", {"path": "../evil.txt", "content": "x"}).startswith("ERROR")
    assert tb.call("write_file", {"path": "C:/Windows/evil.txt", "content": "x"}).startswith("ERROR")
    assert not (tmp_path.parent / "evil.txt").exists()
    assert tb.call("nope", {}).startswith("ERROR")
    assert tb.call("read_file", {"path": "missing"}).startswith("ERROR")


def test_check_syntax(tmp_path):
    tb = Toolbox(tmp_path)
    tb.call("write_file", {"path": "ok.py", "content": "x = 1\n"})
    tb.call("write_file", {"path": "bad.py", "content": "def (:\n"})
    tb.call("write_file", {"path": "bad.json", "content": "{"})
    assert tb.call("check_syntax", {"path": "ok.py"}).startswith("OK")
    assert "SYNTAX ERROR" in tb.call("check_syntax", {"path": "bad.py"})
    assert "SYNTAX ERROR" in tb.call("check_syntax", {"path": "bad.json"})


class FakeClient:
    """Scripted model: writes a file, then finishes."""

    def __init__(self):
        self.turn = 0

    def chat(self, messages, tools=None, max_tokens=0):
        self.turn += 1
        if self.turn == 1:
            return {"content": "writing", "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "write_file", "arguments": json.dumps({"path": "main.py", "content": "print(1)\n"})}}]}
        return {"content": "", "tool_calls": [{"id": "c2", "type": "function", "function": {
            "name": "finish", "arguments": json.dumps({"summary": "done"})}}]}


def test_agent_loop_with_fake_llm(tmp_path):
    root = tmp_path / "in"
    root.mkdir()
    (root / "d.md").write_text(DOC, encoding="utf-8")
    (root / "v.md").write_text(VIEWS, encoding="utf-8")
    logs = []
    res = run_agent(FakeClient(), root / "d.md", root / "v.md", tmp_path / "out", log=logs.append)
    assert res["status"] == "finished" and res["summary"] == "done"
    assert (tmp_path / "out" / "main.py").exists()
    assert (tmp_path / "out" / "docs" / "architecture_doc.json").exists()


def test_agent_handles_bad_tool_args(tmp_path):
    class Bad:
        turn = 0

        def chat(self, messages, tools=None, max_tokens=0):
            self.turn += 1
            if self.turn == 1:
                return {"content": "", "tool_calls": [{"id": "x", "type": "function", "function": {
                    "name": "write_file", "arguments": "{not json"}}]}
            return {"content": "", "tool_calls": [{"id": "y", "type": "function", "function": {
                "name": "finish", "arguments": '{"summary":"ok"}'}}]}

    (tmp_path / "d.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "v.md").write_text(VIEWS, encoding="utf-8")
    res = run_agent(Bad(), tmp_path / "d.md", tmp_path / "v.md", tmp_path / "o", log=lambda s: None)
    assert res["status"] == "finished"


def test_cancel(tmp_path):
    import threading
    ev = threading.Event()
    ev.set()
    (tmp_path / "d.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "v.md").write_text(VIEWS, encoding="utf-8")
    res = run_agent(FakeClient(), tmp_path / "d.md", tmp_path / "v.md", tmp_path / "o",
                    log=lambda s: None, cancel=ev)
    assert res["status"] == "cancelled"


def test_progress_callback(tmp_path):
    (tmp_path / "d.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "v.md").write_text(VIEWS, encoding="utf-8")
    seen = []
    run_agent(FakeClient(), tmp_path / "d.md", tmp_path / "v.md", tmp_path / "o",
              log=lambda s: None, progress=lambda s, t: seen.append((s, t)), max_steps=10)
    assert seen == [(0, 10), (1, 10)]


def test_format_summary(tmp_path):
    from codeagent.gui import format_summary, human_size
    (tmp_path / "a.py").write_text("x" * 2048)
    out = format_summary({"status": "finished", "steps": 3, "files": ["a.py"], "summary": "all good"},
                         tmp_path, 125)
    assert "Finished successfully" in out and "Files: 1 (2.0 KB)" in out
    assert "Time: 2m 05s" in out and "all good" in out
    assert "Error: boom" in format_summary({"status": "error", "error": "boom", "files": []}, tmp_path, 1)
    assert human_size(512) == "512 B"


def test_gui_smoke(tmp_path):
    import tkinter as tk
    from codeagent.gui import App
    try:
        app = App()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.withdraw()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "m.py").write_text("print(1)")
        (tmp_path / "README.md").write_text("hi")
        app.run_out = tmp_path
        app.refresh_tree()
        assert set(app.tree_nodes) == {"src", "src/m.py", "README.md"}
        child = app.tree.get_children(app.tree_nodes["src"])
        assert len(child) == 1
        (tmp_path / "new.txt").write_text("n")  # incremental refresh keeps existing nodes
        keep = app.tree_nodes["src"]
        app.refresh_tree()
        assert app.tree_nodes["src"] == keep and "new.txt" in app.tree_nodes
        app.running = True
        app.started_at = 0.0
        app._finish({"status": "finished", "steps": 2, "files": ["README.md"], "summary": "ok"})
        assert app.running is False
        assert "Finished successfully" in app.summary.get("1.0", "end")
        assert app.status.get() == "Done"
    finally:
        app.destroy()
