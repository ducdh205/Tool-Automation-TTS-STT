import asyncio
import struct

import pytest

from tts_stt_tool.api.ws import frame_message, oriented
from tts_stt_tool.device.scrcpy import (
    CODEC_H264, Packet, ScrcpyError, Session, merge_config, read_handshake, read_stream, server_args,
)


def feed(data: bytes) -> asyncio.StreamReader:
    r = asyncio.StreamReader()
    r.feed_data(data)
    r.feed_eof()
    return r


def session(w: int, h: int) -> bytes:
    return struct.pack(">III", 0x8000_0000, w, h)


def media(data: bytes, pts: int = 0, key: bool = False, config: bool = False) -> bytes:
    flags = (1 << 62 if config else 0) | (1 << 61 if key else 0)
    return struct.pack(">QI", (pts if not config else 0) | flags, len(data)) + data


async def collect(it):
    return [x async for x in it]


def test_server_args_keep_the_phone_untouched():
    args = server_args("0abc1234")
    assert args[:5] == ["CLASSPATH=/data/local/tmp/tts-stt-scrcpy.jar", "app_process", "/",
                        "com.genymobile.scrcpy.Server", "5.0.1"]
    for opt in ("audio=false", "control=false", "clipboard_autosync=false", "power_on=false",
                "tunnel_forward=true", "video_codec=h264", "scid=0abc1234"):
        assert opt in args


async def test_handshake_reads_name_and_checks_codec():
    name = b"Pixel 7".ljust(64, b"\0")
    assert await read_handshake(feed(name + struct.pack(">I", CODEC_H264))) == "Pixel 7"
    with pytest.raises(ScrcpyError):
        await read_handshake(feed(name + struct.pack(">I", 1)))


async def test_read_stream_sessions_and_packets():
    raw = session(480, 1024) + media(b"SPS", config=True) + media(b"IDR", pts=5, key=True) + media(b"P", pts=40)
    items = await collect(read_stream(feed(raw)))
    assert items == [Session(480, 1024), Packet(b"SPS", 0, False, True),
                     Packet(b"IDR", 5, True, False), Packet(b"P", 40, False, False)]


async def test_read_stream_stops_on_truncated_packet():
    raw = media(b"IDR", pts=5, key=True) + struct.pack(">QI", 9, 100) + b"short"
    assert await collect(read_stream(feed(raw))) == [Packet(b"IDR", 5, True, False)]


async def test_merge_config_glues_sps_to_next_frame():
    raw = session(480, 1024) + media(b"SPS", config=True) + media(b"IDR", pts=5, key=True) + media(b"P", pts=40)
    items = await collect(merge_config(read_stream(feed(raw))))
    assert items == [Session(480, 1024), Packet(b"SPSIDR", 5, True, True), Packet(b"P", 40, False, False)]


def test_frame_message_layout():
    msg = frame_message(Packet(b"\x00\x00\x00\x01e", 1234, True, True))
    assert msg[0] == 3 and struct.unpack(">Q", msg[1:9])[0] == 1234 and msg[9:] == b"\x00\x00\x00\x01e"
    assert frame_message(Packet(b"x", 1, False, False))[0] == 0


def test_oriented_follows_stream_rotation():
    assert oriented((1080, 2400), Session(464, 1024)) == (1080, 2400)
    assert oriented((1080, 2400), Session(1024, 464)) == (2400, 1080)
