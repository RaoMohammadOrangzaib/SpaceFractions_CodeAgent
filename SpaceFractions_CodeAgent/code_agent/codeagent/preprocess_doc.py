"""Convert Architecture_Documentation.md into structured JSON."""
from __future__ import annotations

import re
from typing import Any

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^```\s*([\w+-]*)\s*$")
REQ_RE = re.compile(r"\b(?:FR|NFR|ASR)-\d+\b")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _parse_table(lines: list[str]) -> dict[str, Any]:
    header = _split_row(lines[0])
    rows = [_split_row(l) for l in lines[2:]]
    return {"columns": header, "rows": [dict(zip(header, r)) for r in rows]}


def _parse_body(lines: list[str]) -> dict[str, Any]:
    """Split a section body into prose, bullets, tables and code blocks."""
    prose: list[str] = []
    bullets: list[str] = []
    tables: list[dict[str, Any]] = []
    code_blocks: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if m:
            lang = m.group(1) or "text"
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            code_blocks.append({"lang": lang, "code": "\n".join(buf)})
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1].strip()):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            tables.append(_parse_table(lines[i:j]))
            i = j
            continue
        stripped = line.strip()
        if re.match(r"^([*-]|\d+\.)\s+", stripped):
            bullets.append(re.sub(r"^([*-]|\d+\.)\s+", "", stripped))
        elif stripped:
            prose.append(stripped)
        i += 1
    return {"text": " ".join(prose), "bullets": bullets, "tables": tables, "code_blocks": code_blocks}


def parse_architecture_doc(markdown: str) -> dict[str, Any]:
    """Return {"sections": [...], "requirement_ids": [...], "components": [...], "artifacts": [...]}."""
    lines = markdown.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line) or (in_fence and line.startswith("```")):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            current = {"level": len(m.group(1)), "title": m.group(2), "lines": []}
            sections.append(current)
        else:
            if current is None:
                current = {"level": 0, "title": "_preamble", "lines": []}
                sections.append(current)
            current["lines"].append(line)

    out_sections = []
    for s in sections:
        body = _parse_body(s.pop("lines"))
        out_sections.append({**s, **body})

    req_ids = sorted(set(REQ_RE.findall(markdown)), key=lambda x: (x.split("-")[0], int(x.split("-")[1])))
    components = sorted(set(re.findall(r"\b([A-Z][A-Za-z]+Component)\b", markdown)))
    artifacts = sorted(set(re.findall(r"\b((?:[\w-]+/)*[\w-]+\.(?:yaml|yml|proto|sql|csv|md))\b", markdown)))
    return {
        "source": "Architecture_Documentation.md",
        "requirement_ids": req_ids,
        "components": components,
        "artifacts": artifacts,
        "sections": out_sections,
    }
