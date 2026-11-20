"""Parse ``uiautomator dump`` XML and find the controls / chat bubbles of the app."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_EDIT = "android.widget.EditText"
_NOT_BUBBLE = ("android.widget.Button", _EDIT, "android.widget.ImageView")


@dataclass
class UiNode:
    text: str
    desc: str
    cls: str
    bounds: tuple[int, int, int, int]
    clickable: bool

    @property
    def label(self) -> str:
        return self.desc or self.text

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    def contains(self, x: int, y: int) -> bool:
        x1, y1, x2, y2 = self.bounds
        return x1 <= x < x2 and y1 <= y < y2

    def to_json(self) -> dict:
        return {"label": self.label, "cls": self.cls, "bounds": list(self.bounds), "clickable": self.clickable}


def parse_dump(xml: str) -> list[UiNode]:
    root = ET.fromstring(xml[xml.index("<"):])
    out: list[UiNode] = []
    for el in root.iter("node"):
        text, desc, cls = el.get("text", ""), el.get("content-desc", ""), el.get("class", "")
        if not (text or desc or cls == _EDIT):
            continue
        m = _BOUNDS.match(el.get("bounds", ""))
        if not m:
            continue
        b = (int(m[1]), int(m[2]), int(m[3]), int(m[4]))
        out.append(UiNode(text, desc, cls, b, el.get("clickable") == "true"))
    return out


def find(nodes: list[UiNode], label: str) -> UiNode | None:
    """Exact label match first, then prefix (multi-line content-desc)."""
    for n in nodes:
        if n.label == label:
            return n
    for n in nodes:
        if n.label.startswith(label):
            return n
    return None


def node_at(nodes: list[UiNode], x: int, y: int) -> UiNode | None:
    """Smallest labelled node containing the point."""
    hits = [n for n in nodes if n.contains(x, y)]
    return min(hits, key=lambda n: (n.bounds[2] - n.bounds[0]) * (n.bounds[3] - n.bounds[1]), default=None)


def right_bubbles(nodes: list[UiNode], screen_w: int) -> list[UiNode]:
    """User-side chat bubbles: right-aligned labelled views above the input box, top to bottom."""
    edits = [n.bounds[1] for n in nodes if n.cls == _EDIT]
    limit = min(edits) if edits else 10**9  # the char counter etc. sit below/inside the input
    out = [
        n for n in nodes
        if n.label and n.cls not in _NOT_BUBBLE and n.bounds[3] <= limit
        and n.bounds[0] > screen_w * 0.25 and n.bounds[2] > screen_w * 0.75
    ]
    return sorted(out, key=lambda n: n.bounds[1])


def new_bubble(before: list[UiNode], after: list[UiNode], screen_w: int) -> UiNode | None:
    """The transcript bubble added between two dumps (by count, so repeated text still counts)."""
    old, new = right_bubbles(before, screen_w), right_bubbles(after, screen_w)
    return new[-1] if len(new) > len(old) else None
