"""Sandboxed tools the agent can call. All paths are confined to the output directory."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

MAX_READ = 20000

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file in the output project. Path is relative to the project root.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file previously written to the output project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List all files currently in the output project.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "check_syntax",
        "description": "Validate syntax of a written file (.py, .json, .proto basic, .yaml/.yml basic, .sql basic).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call when the project is complete. Provide a short summary.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]


class ToolError(Exception):
    pass


class Toolbox:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.finished = False
        self.summary = ""

    def _resolve(self, rel: str) -> Path:
        if not rel or not isinstance(rel, str):
            raise ToolError("path is required")
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise ToolError(f"path escapes the output directory: {rel}")
        return p

    def call(self, name: str, args: dict[str, Any]) -> str:
        try:
            fn = getattr(self, f"t_{name}", None)
            if fn is None:
                return f"ERROR: unknown tool {name}"
            return fn(**args)
        except ToolError as e:
            return f"ERROR: {e}"
        except TypeError as e:
            return f"ERROR: bad arguments for {name}: {e}"

    # --- tools ---
    def t_write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        return f"wrote {path} ({len(content)} chars)"

    def t_read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:MAX_READ] + ("\n...[truncated]" if len(text) > MAX_READ else "")

    def t_list_files(self) -> str:
        files = sorted(str(p.relative_to(self.root)).replace("\\", "/")
                       for p in self.root.rglob("*") if p.is_file())
        return "\n".join(files) or "(empty)"

    def t_check_syntax(self, path: str) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"no such file: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        suffix = p.suffix.lower()
        try:
            if suffix == ".py":
                ast.parse(text)
            elif suffix == ".json":
                json.loads(text)
            elif suffix in (".yaml", ".yml"):
                self._check_yaml(text)
            elif suffix == ".proto":
                if text.count("{") != text.count("}") or 'syntax' not in text:
                    raise ValueError("unbalanced braces or missing syntax statement")
            elif suffix == ".sql":
                if text.count("(") != text.count(")") or ";" not in text:
                    raise ValueError("unbalanced parentheses or missing ';'")
            else:
                return f"OK (no checker for {suffix or 'this file type'})"
        except Exception as e:  # SyntaxError, ValueError, yaml.YAMLError, ...
            return f"SYNTAX ERROR in {path}: {e}"
        return f"OK {path}"

    @staticmethod
    def _check_yaml(text: str) -> None:
        if "\t" in text:
            raise ValueError("tab characters are not allowed in YAML indentation")
        try:
            import yaml  # optional
        except ImportError:
            return
        list(yaml.safe_load_all(text))

    def t_finish(self, summary: str) -> str:
        self.finished = True
        self.summary = summary
        return "Finished."
