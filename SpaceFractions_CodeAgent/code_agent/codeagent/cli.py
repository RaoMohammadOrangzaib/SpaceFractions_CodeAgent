"""Headless CLI: python -m codeagent --doc X --views Y --out Z [--preprocess-only]."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent import DEFAULT_TASK, build_inputs, run_agent
from .llm import MODEL, DeepSeekClient


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="codeagent", description="Architecture docs -> code project via DeepSeek")
    ap.add_argument("--doc", required=True, help="Architecture_Documentation.md")
    ap.add_argument("--views", required=True, help="Architecture_View.md")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    ap.add_argument("--preprocess-only", action="store_true", help="only print the structured JSON inputs")
    a = ap.parse_args(argv)
    if a.preprocess_only:
        doc, views = build_inputs(Path(a.doc), Path(a.views))
        print(json.dumps({"doc": doc, "views": views}, indent=2, ensure_ascii=False))
        return 0
    if not a.api_key:
        print("error: set --api-key or DEEPSEEK_API_KEY", file=sys.stderr)
        return 2
    result = run_agent(DeepSeekClient(a.api_key, model=a.model), Path(a.doc), Path(a.views), Path(a.out), task=a.task)
    return 0 if result["status"] == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
