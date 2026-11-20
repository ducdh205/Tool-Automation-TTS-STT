from tts_stt_tool.device.adb import parse_devices


def test_parse_devices():
    out = """* daemon started successfully
List of devices attached
cqqcoz49dmsspjnr       unauthorized usb:1-1 transport_id:1
abc123 device usb:1-2 product:ruby model:22120RN86G device:ruby transport_id:2

"""
    ds = parse_devices(out)
    assert [(d.serial, d.state, d.model) for d in ds] == [
        ("cqqcoz49dmsspjnr", "unauthorized", None),
        ("abc123", "device", "22120RN86G"),
    ]


def test_parse_devices_empty():
    assert parse_devices("List of devices attached\n\n") == []


def test_escape_input_text():
    import pytest

    from tts_stt_tool.device.adb import AdbError, escape_input_text

    assert escape_input_text("mua sua 2") == "mua%ssua%s2"
    assert escape_input_text("a&b'c") == r"a\&b\'c"
    with pytest.raises(AdbError):
        escape_input_text("sữa")
