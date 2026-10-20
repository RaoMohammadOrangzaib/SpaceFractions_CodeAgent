"""Convert Architecture_View.md (PlantUML views) into structured JSON."""
from __future__ import annotations

import re
from typing import Any

VIEW_RE = re.compile(r"^##\s+(\w+View)\s*$")
TITLE_RE = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
START_RE = re.compile(r"^@startuml\s*(\S*)")

ELEMENT_KEYWORDS = ("actor", "usecase", "rectangle", "participant", "state", "package",
                    "artifact", "node", "class", "component", "database")
# A -- B, A --> B : label, A->>B: msg, A --* B ...
REL_RE = re.compile(r"^(?P<a>[\w\[\]*]+)\s*(?P<arrow>[-.<>*o|]{2,}[>*]?)\s*(?P<b>\(?[\w\]]+\)?)\s*(?::\s*(?P<label>.*))?$")


def _parse_diagram(name: str, body: list[str]) -> dict[str, Any]:
    elements: list[dict[str, str]] = []
    relations: list[dict[str, str]] = []
    classes: dict[str, dict[str, list[str]]] = {}
    notes: list[str] = []
    current_class: str | None = None
    for raw in body:
        line = raw.strip()
        if not line or line in ("left to right direction",):
            continue
        if current_class is not None:
            if line == "}":
                current_class = None
            else:
                kind = "methods" if "(" in line else "attributes"
                classes[current_class][kind].append(line)
            continue
        m = re.match(r"^class\s+(\w+)\s*\{$", line)
        if m:
            current_class = m.group(1)
            classes[current_class] = {"attributes": [], "methods": []}
            elements.append({"kind": "class", "name": current_class})
            continue
        if line.startswith("note"):
            notes.append(line)
            continue
        m = re.match(r"^(%s)\s+(.*?)(?:\s*\{)?$" % "|".join(ELEMENT_KEYWORDS), line)
        if m and not REL_RE.match(line):
            kind, rest = m.group(1), m.group(2)
            alias = re.search(r'"([^"]*)"\s+as\s+\(?(\w+)\)?', rest)
            alias2 = re.search(r'^(\w+)\s+as\s+"([^"]*)"', rest)
            if alias:
                elements.append({"kind": kind, "name": alias.group(2), "label": alias.group(1)})
            elif alias2:
                elements.append({"kind": kind, "name": alias2.group(1), "label": alias2.group(2)})
            else:
                elements.append({"kind": kind, "name": rest.strip().strip('"')})
            continue
        m = REL_RE.match(line)
        if m:
            relations.append({"from": m["a"], "arrow": m["arrow"], "to": m["b"].strip("()"),
                              "label": (m["label"] or "").strip()})
    return {"name": name, "elements": elements, "classes": classes,
            "relations": relations, "notes": notes}


def parse_architecture_views(markdown: str) -> dict[str, Any]:
    """Return {"views": [{"view","diagrams":[{"title","type","diagrams..."}]}]}."""
    views: list[dict[str, Any]] = []
    view: dict[str, Any] | None = None
    title = ""
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = VIEW_RE.match(line)
        if m:
            view = {"view": m.group(1), "diagrams": []}
            views.append(view)
        else:
            t = TITLE_RE.match(line)
            if t:
                title = t.group(2)
            elif line.startswith("```plantuml") and view is not None:
                i += 1
                buf: list[str] = []
                while i < len(lines) and not lines[i].startswith("```"):
                    buf.append(lines[i])
                    i += 1
                name = "Unnamed"
                body: list[str] = []
                for b in buf:
                    s = START_RE.match(b.strip())
                    if s:
                        name = s.group(1) or name
                    elif not b.strip().startswith("@enduml"):
                        body.append(b)
                diagram = _parse_diagram(name, body)
                diagram["title"] = title
                diagram["source"] = "\n".join(buf)
                view["diagrams"].append(diagram)
        i += 1
    count = sum(len(v["diagrams"]) for v in views)
    return {"source": "Architecture_View.md", "diagram_count": count, "views": views}
