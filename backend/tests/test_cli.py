from pathlib import Path

from tts_stt_tool.cli import parse_args


def test_defaults():
    a = parse_args([])
    assert a.data_dir == Path("data")
    assert a.port is None
    assert a.no_browser is False


def test_overrides():
    a = parse_args(["--data-dir", "x", "--port", "9000", "--no-browser"])
    assert a.data_dir == Path("x")
    assert a.port == 9000
    assert a.no_browser is True


def test_utf8_console_reconfigures_cp1252_stream():
    import io

    from tts_stt_tool.cli import utf8_console

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    utf8_console(stream)
    stream.write("Ctrl+C để dừng")
    stream.flush()
    assert raw.getvalue().decode("utf-8") == "Ctrl+C để dừng"
