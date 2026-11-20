from pathlib import Path

import pytest

from tts_stt_tool.device.adb import Adb, AdbError, parse_wm_size
from tts_stt_tool.device.ui_tree import UiNode, find, new_bubble, parse_dump, right_bubbles

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(name: str) -> list[UiNode]:
    return parse_dump((FIX / f"{name}.xml").read_text(encoding="utf-8"))


def test_find_home_mic():
    mic = find(load("ui_home"), "Nói để tạo việc")
    assert mic is not None
    assert mic.center == (360, 1471)
    assert mic.cls == "android.widget.Button"


def test_find_prefix_and_missing():
    nodes = load("ui_home")
    assert find(nodes, "Vita đề xuất") is not None  # multi-line desc, prefix match
    assert find(nodes, "Không có nút này") is None


def test_listening_sheet_has_stop_button():
    assert find(load("ui_listening"), "Dừng nghe") is not None


def test_right_bubbles_only_user_side():
    labels = [n.label for n in right_bubbles(load("ui_stopped"), 720)]
    assert labels == ["chỉnh nhiệt độ ghế lái lên 24 độ"]


def test_new_bubble_after_stop():
    b = new_bubble(load("ui_listening"), load("ui_stopped"), 720)
    assert b is not None
    assert b.label == "chỉnh nhiệt độ ghế lái lên 24 độ"


def _bubble(text: str, y: int) -> UiNode:
    return UiNode(text="", desc=text, cls="android.view.View", bounds=(300, y, 680, y + 40), clickable=False)


def test_repeated_identical_bubble_is_detected():
    """Review #2: same sentence twice -> detect by count/position, not by text set."""
    before = [_bubble("bật đèn", 900)]
    after = [_bubble("bật đèn", 900), _bubble("bật đèn", 1000)]
    b = new_bubble(before, after, 720)
    assert b is not None and b.bounds[1] == 1000
    assert new_bubble(before, list(before), 720) is None


def test_left_bubble_not_counted():
    left = UiNode(text="", desc="Chưa nghe rõ. Thử lại hoặc gõ.", cls="android.view.View",
                  bounds=(32, 836, 624, 876), clickable=False)
    assert new_bubble([], [left], 720) is None


class FlakyAdb(Adb):
    def __init__(self, fails: int):
        super().__init__(path=Path("adb.exe"))
        self.fails = fails
        self.calls = 0

    def _run(self, *args: str) -> bytes:
        if args[-1].startswith("/sdcard/") and "cat" in args:
            self.calls += 1
            if self.calls <= self.fails:
                return b"ERROR: could not get idle state."
            return (FIX / "ui_home.xml").read_bytes()
        return b"UI hierchary dumped to: /sdcard/tts_stt_ui.xml"


async def test_dump_ui_retries_flaky_dump():
    """Review #3."""
    xml = await FlakyAdb(fails=2).dump_ui("serial")
    assert "<hierarchy" in xml


async def test_dump_ui_gives_up_after_three():
    with pytest.raises(AdbError, match="uiautomator"):
        await FlakyAdb(fails=3).dump_ui("serial")


def test_parse_wm_size_prefers_override():
    assert parse_wm_size("Physical size: 720x1650\n") == (720, 1650)
    assert parse_wm_size("Physical size: 720x1650\nOverride size: 1080x2400\n") == (1080, 2400)
