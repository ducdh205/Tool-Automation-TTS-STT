import asyncio
import sys

from tts_stt_tool.tts.gpu import GpuSetup

PY = sys.executable


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def exits(code: int) -> list[str]:
    return py(f"import sys; sys.exit({code})")


def flag_check(path) -> list[str]:
    """torch check stand-in: CUDA 'available' once the flag file exists."""
    return py(f"import os, sys; sys.exit(0 if os.path.exists({str(path)!r}) else 1)")


async def wait_install(gpu: GpuSetup, timeout: float = 10) -> dict:
    for _ in range(int(timeout / 0.05)):
        st = gpu.install_state()
        if st["state"] != "running":
            return st
        await asyncio.sleep(0.05)
    raise AssertionError("install did not finish")


async def test_probe_nvidia_present():
    gpu = GpuSetup(nvidia_cmd=py("print('NVIDIA GeForce RTX 3060')"), torch_cmd=exits(1))
    p = await gpu.probe()
    assert p.nvidia is True
    assert p.gpu_name == "NVIDIA GeForce RTX 3060"
    assert p.torch_cuda is False


async def test_probe_nvidia_missing():
    gpu = GpuSetup(nvidia_cmd=["khong-co-lenh-nay"], torch_cmd=exits(0))
    p = await gpu.probe()
    assert p.nvidia is False
    assert p.gpu_name is None


async def test_probe_cached_until_refresh(tmp_path):
    flag = tmp_path / "cuda"
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=flag_check(flag))
    assert (await gpu.probe()).torch_cuda is False
    flag.touch()
    assert (await gpu.probe()).torch_cuda is False
    assert (await gpu.probe(refresh=True)).torch_cuda is True


async def test_install_success_calls_on_done(tmp_path):
    flag = tmp_path / "cuda"
    done = []
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=flag_check(flag),
                   install_cmd=py(f"import pathlib; print('Downloading torch'); print('Installed');"
                                  f" pathlib.Path({str(flag)!r}).touch()"))
    assert gpu.start_install(lambda: done.append(1)) is True
    st = await wait_install(gpu)
    assert st["state"] == "done", st
    assert st["log_tail"] == ["Downloading torch", "Installed"]
    assert st["error"] is None
    assert done == [1]


async def test_install_failure_keeps_cpu():
    done = []
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=exits(1), install_cmd=exits(3))
    gpu.start_install(lambda: done.append(1))
    st = await wait_install(gpu)
    assert st["state"] == "failed"
    assert "mã 3" in st["error"]
    assert done == []


async def test_install_ok_but_no_cuda():
    done = []
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=exits(1), install_cmd=exits(0))
    gpu.start_install(lambda: done.append(1))
    st = await wait_install(gpu)
    assert st["state"] == "failed"
    assert "driver NVIDIA" in st["error"]
    assert done == []


async def test_install_twice_runs_once(tmp_path):
    count = tmp_path / "count"
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=exits(0),
                   install_cmd=py(f"import time; open({str(count)!r}, 'a').write('x'); time.sleep(0.5)"))
    assert gpu.start_install(lambda: None) is True
    assert gpu.start_install(lambda: None) is False
    await wait_install(gpu)
    assert count.read_text() == "x"


async def test_install_without_uv_fails():
    gpu = GpuSetup(nvidia_cmd=py("print('RTX')"), torch_cmd=exits(1), install_cmd=None)
    gpu.start_install(lambda: None)
    st = await wait_install(gpu)
    assert st["state"] == "failed"
    assert st["error"] == "Không tìm thấy uv"
