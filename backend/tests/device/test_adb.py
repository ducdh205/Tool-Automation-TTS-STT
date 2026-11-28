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


# --- speed: one adb call per UI dump, raw screencap encoded on the PC ---------
import struct
import zlib
from pathlib import Path

from tts_stt_tool.device.adb import Adb, raw_to_png

FIX = Path(__file__).resolve().parents[1] / "fixtures"
HOME = (FIX / "ui_home.xml").read_bytes()


class TtyAdb(Adb):
    """``exec-out uiautomator dump /dev/tty`` prints the XML, then the "dumped to" line."""

    def __init__(self, tty_out: list[bytes]):
        super().__init__(path=Path("adb.exe"))
        self.tty_out = tty_out  # what each /dev/tty dump prints, in turn
        self.calls: list[tuple[str, ...]] = []

    def _run(self, *args: str) -> bytes:
        self.calls.append(args)
        if "/dev/tty" in args:
            return self.tty_out.pop(0) if self.tty_out else b"ERROR: null root node returned by UiTestAutomationBridge."
        if "dump" in args:
            return b"UI hierchary dumped to: /sdcard/x.xml"
        if "cat" in args:
            return HOME
        return b""


async def test_dump_ui_uses_one_call_through_tty():
    adb = TtyAdb([HOME + b"UI hierchary dumped to: /dev/tty\r\n"] * 2)
    xml = await adb.dump_ui("s")
    assert xml.startswith("<?xml") and xml.rstrip().endswith("</hierarchy>")
    await adb.dump_ui("s")
    assert len(adb.calls) == 2  # no rm / cat round trips


async def test_dump_ui_falls_back_to_file_when_tty_unsupported():
    adb = TtyAdb([])
    assert "<hierarchy" in await adb.dump_ui("s")
    n = len(adb.calls)
    await adb.dump_ui("s")
    assert not any("/dev/tty" in c for c in adb.calls[n:])  # not tried again on this phone


async def test_dump_ui_tty_retries_a_flaky_dump_once_it_has_worked():
    good = HOME + b"UI hierchary dumped to: /dev/tty\n"
    adb = TtyAdb([good, b"ERROR: could not get idle state.", good])
    await adb.dump_ui("s")
    assert "<hierarchy" in await adb.dump_ui("s")
    assert all("/dev/tty" in c for c in adb.calls)


def _raw(w: int, h: int, px: bytes, header: int = 16) -> bytes:
    head = struct.pack("<III", w, h, 1) + (b"\0\0\0\0" if header == 16 else b"")
    return head + px * (w * h)


def _png_pixels(png: bytes) -> tuple[int, int, bytes]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    w, h = struct.unpack(">II", png[16:24])
    pos, data = 8, b""
    while pos < len(png):
        n = struct.unpack(">I", png[pos:pos + 4])[0]
        kind = png[pos + 4:pos + 8]
        if kind == b"IDAT":
            data += png[pos + 8:pos + 8 + n]
        pos += 12 + n
    rows = zlib.decompress(data)
    stride = w * 4 + 1
    return w, h, b"".join(rows[i * stride + 1:(i + 1) * stride] for i in range(h))


def test_raw_to_png_round_trips_pixels_and_forces_opaque():
    for header in (12, 16):
        w, h, px = _png_pixels(raw_to_png(_raw(3, 2, b"\x10\x20\x30\x00", header)))
        assert (w, h) == (3, 2)
        assert px == b"\x10\x20\x30\xff" * 6


def test_raw_to_png_rejects_garbage():
    import pytest

    with pytest.raises(ValueError):
        raw_to_png(b"\x89PNG not raw")
    with pytest.raises(ValueError):
        raw_to_png(struct.pack("<III", 1000, 1000, 1) + b"\0" * 10)


class ShotAdb(Adb):
    def __init__(self, raw: bytes):
        super().__init__(path=Path("adb.exe"))
        self.raw, self.calls = raw, []

    def _run(self, *args: str) -> bytes:
        self.calls.append(args)
        return b"\x89PNG-from-phone" if "-p" in args else self.raw


async def test_screencap_raw_is_encoded_on_the_pc():
    adb = ShotAdb(_raw(2, 2, b"\1\2\3\4"))
    png = await adb.screencap("s")
    assert png.startswith(b"\x89PNG\r\n") and adb.calls == [("-s", "s", "exec-out", "screencap")]


async def test_screencap_falls_back_to_phone_png():
    adb = ShotAdb(b"weird")
    assert await adb.screencap("s") == b"\x89PNG-from-phone"
