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


# --- real-device findings: long user bubbles start at x=156; history may persist ---
def test_long_user_bubble_counts_but_assistant_does_not():
    long_user = UiNode("", "đang làm cái gì đấy Đang làm cái gì cũng được", "android.view.View", (156, 880, 660, 960), False)
    assistant = UiNode("", "Câu này chưa phải một việc cần làm.", "android.view.View", (32, 1004, 624, 1084), False)
    assert [n.label for n in right_bubbles([long_user, assistant], 720)] == [long_user.label]


def test_new_bubble_by_labels_history_kept():
    from tts_stt_tool.device.ui_tree import new_bubble_after
    after = [_bubble("câu cũ", 700), _bubble("câu mới", 900)]
    assert new_bubble_after(["câu cũ"], after, 720).label == "câu mới"
    assert new_bubble_after(["câu cũ"], [_bubble("câu cũ", 700)], 720) is None


def test_new_bubble_by_labels_history_reset():
    from tts_stt_tool.device.ui_tree import new_bubble_after
    assert new_bubble_after(["a", "b"], [_bubble("c", 700)], 720).label == "c"
    assert new_bubble_after(["a", "b"], [], 720) is None


def test_parse_mic_active():
    from tts_stt_tool.device.adb import parse_mic_active

    active = ("RecordActivityMonitor dump time: 14:41:14\n  riid 2799; active? true\n"
              "  session:4009 -- source client=VOICE_RECOGNITION, dev=1ch 16000Hz\n")
    idle = ("RecordActivityMonitor dump time: 14:41:13\nAudio event log: recording activity received by AudioService\n"
            "11-20 14:09:00:945 rec stop riid:2199 uid:10211 session:3385 src:VOICE_RECOGNITION\n")
    assert parse_mic_active(active) is True
    assert parse_mic_active(idle) is False
    assert parse_mic_active("  riid 12; active? false\n") is False
