"""parse_wda_source on real WebDriverAgent dumps of Vita Work Dev (iOS 26, 393x852 pt)."""

from pathlib import Path

from tts_stt_tool.device.ui_tree import bubble_labels, find, new_bubble_after, parse_wda_source

FIX = Path(__file__).resolve().parents[1] / "fixtures"
W = 393


def load(name: str):
    return parse_wda_source((FIX / name).read_text(encoding="utf-8"))


def test_home_has_mic_button_with_point_bounds():
    nodes = load("ios_home.xml")
    mic = find(nodes, "Nói để tạo việc")  # label is "Nói để tạo việc\nNói để tạo việc"
    assert mic is not None
    assert mic.cls == "XCUIElementTypeButton" and mic.clickable
    assert mic.bounds == (168, 758, 225, 814)
    assert mic.center == (196, 786)


def test_hidden_zero_size_nodes_are_dropped():
    nodes = load("ios_home.xml")
    assert all(n.bounds[2] > n.bounds[0] and n.bounds[3] > n.bounds[1] for n in nodes)
    assert find(nodes, "Hôm nay không còn việc nào khác") is None  # width/height 0 in the dump


def test_application_root_is_not_a_node():
    assert all(n.cls != "XCUIElementTypeApplication" for n in load("ios_home.xml"))


def test_listening_sheet_controls():
    nodes = load("ios_listening.xml")
    assert find(nodes, "Dừng nghe") is not None
    assert find(nodes, "Đóng") is not None
    assert find(nodes, "Nói để tạo việc") is None
    assert bubble_labels(nodes, W) == []  # counter, buttons, the sheet-wide TextField are not bubbles


def test_user_bubble_after_stop():
    listening = load("ios_listening.xml")
    stopped = load("ios_stopped.xml")
    assert find(stopped, "Bấm để nói") is not None
    # the left-aligned server error and the "Còn lại … ký tự" counter are not user bubbles
    assert bubble_labels(stopped, W) == ["Nộp báo nộp báo cáo ngân sách"]
    bubble = new_bubble_after(bubble_labels(listening, W), stopped, W)
    assert bubble is not None and bubble.label == "Nộp báo nộp báo cáo ngân sách"


def test_static_text_falls_back_to_value():
    xml = ('<?xml version="1.0"?><XCUIElementTypeApplication type="XCUIElementTypeApplication" x="0" y="0" '
           'width="393" height="852"><XCUIElementTypeStaticText type="XCUIElementTypeStaticText" value="xin chào" '
           'visible="true" x="200" y="500" width="160" height="20"/></XCUIElementTypeApplication>')
    (n,) = parse_wda_source(xml)
    assert n.label == "xin chào"


def test_invisible_nodes_are_dropped():
    xml = ('<?xml version="1.0"?><XCUIElementTypeApplication type="XCUIElementTypeApplication" x="0" y="0" '
           'width="393" height="852"><XCUIElementTypeButton type="XCUIElementTypeButton" name="Đóng" label="Đóng" '
           'visible="false" x="300" y="500" width="40" height="40"/></XCUIElementTypeApplication>')
    assert parse_wda_source(xml) == []


# --- Vita Work UAT (com.vita.suite.stg): the task form opened by speaking ----
def test_uat_home_has_mic():
    assert find(load("ios_uat_home.xml"), "Nói để tạo việc") is not None


def test_uat_task_form_heard_text():
    from tts_stt_tool.device.ui_tree import heard_text

    nodes = load("ios_uat_form.xml")
    assert heard_text(nodes, "Bạn nói: ") == "Chức năng hóa không khí"
    assert find(nodes, "Đóng") is not None and find(nodes, "Bấm để nói") is not None


def test_uat_discard_dialog():
    nodes = load("ios_uat_discard.xml")
    assert find(nodes, "Bỏ thay đổi?") is not None
    assert find(nodes, "Bỏ thay đổi").clickable
    assert find(nodes, "Giữ nháp") is not None


def test_uat_not_a_task_reply_is_not_a_bubble():
    # "Câu này chưa phải một việc cần làm…" is the app's (left-aligned) answer
    assert bubble_labels(load("ios_uat_not_task.xml"), W) == ["Mở"]
