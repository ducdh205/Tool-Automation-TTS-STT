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
    """Exact label match first, then the first line of a multi-line content-desc.

    A plain prefix is not enough: "Đóng" must not match a task card "Đóng cửa sổ…".
    """
    for n in nodes:
        if n.label == label:
            return n
    for n in nodes:
        if n.label.split("\n", 1)[0] == label:
            return n
    return None


def node_at(nodes: list[UiNode], x: int, y: int) -> UiNode | None:
    """Smallest labelled node containing the point."""
    hits = [n for n in nodes if n.contains(x, y)]
    return min(hits, key=lambda n: (n.bounds[2] - n.bounds[0]) * (n.bounds[3] - n.bounds[1]), default=None)


def right_bubbles(nodes: list[UiNode], screen_w: int) -> list[UiNode]:
    """User-side chat bubbles: right-aligned labelled views above the input box, top to bottom.

    Assistant messages start at the left margin (x1 = 32 on a 720 px screen); long user
    bubbles can start as far left as x1 = 156, so the left edge test is 10 % of the width.
    """
    edits = [n.bounds[1] for n in nodes if n.cls == _EDIT]
    limit = min(edits) if edits else 10**9  # the char counter etc. sit below/inside the input
    out = [
        n for n in nodes
        if n.label and n.cls not in _NOT_BUBBLE and n.bounds[3] <= limit
        and n.bounds[0] > screen_w * 0.1 and n.bounds[2] > screen_w * 0.75
    ]
    return sorted(out, key=lambda n: n.bounds[1])


def new_bubble(before: list[UiNode], after: list[UiNode], screen_w: int) -> UiNode | None:
    """The transcript bubble added between two dumps (by count, so repeated text still counts)."""
    old, new = right_bubbles(before, screen_w), right_bubbles(after, screen_w)
    return new[-1] if len(new) > len(old) else None


def bubble_labels(nodes: list[UiNode], screen_w: int) -> list[str]:
    return [n.label for n in right_bubbles(nodes, screen_w)]


def new_bubble_after(prev: list[str], after: list[UiNode], screen_w: int) -> UiNode | None:
    """New user bubble compared with the labels seen before.

    The app sometimes keeps the chat when its sheet is reopened and sometimes clears it:
    a list that is a contiguous slice of ``prev`` -> nothing new (same chat, maybe scrolled);
    any other list (extended, or history was cleared) -> its last bubble is new.
    """
    bubbles = right_bubbles(after, screen_w)
    labels = [b.label for b in bubbles]
    if not bubbles or _is_slice(labels, prev):
        return None  # same chat, possibly scrolled (e.g. a failure message pushed the top bubble out)
    return bubbles[-1]


def _is_slice(part: list[str], whole: list[str]) -> bool:
    n = len(part)
    return any(whole[i : i + n] == part for i in range(len(whole) - n + 1))
