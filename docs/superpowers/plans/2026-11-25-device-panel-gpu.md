# Bảng "Thiết bị kiểm thử" + chọn CPU/GPU — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay 3 chip ở chân sidebar bằng bảng checklist "Thiết bị kiểm thử" (mọi điện thoại ADB, STT, TTS CPU|GPU) và cho chọn CPU/GPU, tự cài PyTorch CUDA khi cần.

**Architecture:** Backend thêm `tts/gpu.py` (`GpuSetup`: dò NVIDIA, dò torch CUDA, chạy cài ở nền — mọi việc qua subprocess với lệnh tiêm được để test), `VieneuEngine` nhận `device` + `set_device`, `Settings.tts_device`, 3 route `/api/tts/device` & `/api/tts/install-cuda`. Frontend thêm `TestbenchPanel` (tự poll `/api/tts/device`) thay `side-footer` trong `Sidebar`.

**Tech Stack:** FastAPI, asyncio subprocess, pytest; React 18 + vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-25-device-panel-gpu-design.md`

## Global Constraints
- Lệnh cài: `<uv> pip install --python <sys.executable> torch --index-url https://download.pytorch.org/whl/cu128`; `uv` tìm bằng `shutil.which("uv")`, không có → lỗi "Không tìm thấy uv".
- Không cài driver NVIDIA; không có NVIDIA → GPU bị khóa.
- Đổi thiết bị bị từ chối (409) khi `ctx.runner.current()` không phải `None`.
- `/api/health` giữ nguyên trường `gpu`.
- Chữ trên giao diện bằng tiếng Việt, theo đúng câu chữ trong plan.
- `VieneuEngine.version` giữ `"vieneu-v3turbo"` (audio cache CPU dùng lại được cho GPU — quyết định của builder).
- Chạy test: `uv run python -m pytest` (backend), `cd frontend && npx vitest run` (frontend).

## Review Focus
1. `settings.json` ghi `tts_device: "cuda"` nhưng máy không còn torch CUDA → app vẫn sinh audio bằng CPU, GET báo `active: "cpu"` (Task 1 `test_cuda_load_failure_falls_back_to_cpu`).
2. Bấm cài hai lần liên tiếp → chỉ một tiến trình cài (Task 2 `test_install_twice_runs_once`).
3. Lệnh cài thoát mã ≠ 0 → state `failed`, có `error`, `tts_device` vẫn `cpu` (Task 2 `test_install_failure_keeps_cpu`).
4. Cài xong nhưng torch vẫn không thấy CUDA (driver cũ) → `failed` với lý do, giữ CPU (Task 2 `test_install_ok_but_no_cuda`).
5. Đổi CPU/GPU khi đang có job → 409, settings không đổi (Task 3 `test_put_device_while_job_running_409`).

---

### Task 1: `Settings.tts_device` + `VieneuEngine` chọn thiết bị

**Files:**
- Modify: `backend/tts_stt_tool/config.py` (thêm field), `backend/tts_stt_tool/tts/vieneu_engine.py`, `backend/tts_stt_tool/api/app.py:105-108`
- Test: `backend/tests/tts/test_vieneu_engine.py`, `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.tts_device: str = "cpu"`; `VieneuEngine(mode="v3turbo", device: str = "cpu")`; `VieneuEngine.set_device(device: str) -> None` (bỏ model đã nạp dưới `_lock`, lần gọi sau nạp lại); thuộc tính `VieneuEngine.active_device: str | None` (`None` khi chưa nạp, sau nạp là `"cpu"` hoặc `"cuda"`); `VieneuEngine.load_error: str | None`.

- [ ] **Step 1: Write failing tests** — monkeypatch `sys.modules["vieneu"]` bằng module giả có `Vieneu(mode, device)` ghi lại tham số (và raise `RuntimeError("no cuda")` khi `device == "cuda"` trong test fallback):
  - `test_device_passed_to_model`: `VieneuEngine(device="cuda")._model()` → giả nhận `device="cuda"`, `active_device == "cuda"`.
  - `test_set_device_reloads`: nạp với cpu, `set_device("cuda")`, gọi `_model()` lại → giả được tạo 2 lần, lần 2 `device="cuda"`.
  - `test_cuda_load_failure_falls_back_to_cpu`: giả raise với cuda → `_model()` trả model cpu, `active_device == "cpu"`, `load_error` chứa `"no cuda"`.
  - `test_config.py::test_tts_device_default_and_roundtrip`: mặc định `"cpu"`; save/load giữ `"cuda"`.
- [ ] **Step 2: Run** `uv run python -m pytest backend/tests/tts/test_vieneu_engine.py backend/tests/test_config.py -v` → FAIL.
- [ ] **Step 3: Implement** — `Vieneu(mode=self._mode, device=self._device)`; với cuda bọc try/except `Exception` → ghi `load_error`, nạp lại với `"cpu"`. `create_app` tạo `VieneuEngine(device=settings.tts_device)`.
- [ ] **Step 4: Run** lại lệnh Step 2 → PASS.
- [ ] **Step 5: Commit** `feat(tts): pick CPU or CUDA for VieNeu, persisted in settings`

### Task 2: `GpuSetup` — dò NVIDIA, dò torch CUDA, cài ở nền

**Files:**
- Create: `backend/tts_stt_tool/tts/gpu.py`
- Test: `backend/tests/tts/test_gpu.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass
  class GpuProbe:
      nvidia: bool
      gpu_name: str | None
      torch_cuda: bool

  class GpuSetup:
      def __init__(self, *, nvidia_cmd: list[str] | None = None,
                   torch_cmd: list[str] | None = None,
                   install_cmd: list[str] | None = None) -> None: ...
      async def probe(self, refresh: bool = False) -> GpuProbe   # cache kết quả; refresh=True dò lại
      def install_state(self) -> dict  # {"state": "idle|running|done|failed", "log_tail": list[str] (<=20 dòng), "error": str | None}
      def start_install(self, on_done: Callable[[], None]) -> bool  # False nếu đang running; on_done gọi khi done
  ```
  Mặc định: `nvidia_cmd = ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]` (không tìm thấy lệnh/mã ≠ 0 → `nvidia=False`; dòng đầu stdout = `gpu_name`); `torch_cmd = [sys.executable, "-c", "import sys, torch; sys.exit(0 if torch.cuda.is_available() else 1)"]` (mã 0 → `torch_cuda=True`); `install_cmd` theo Global Constraints, `None` nếu không có uv.
- Luồng cài: state `running` → chạy `install_cmd` (asyncio subprocess, gộp stderr vào stdout, đọc từng dòng vào `log_tail`) → mã ≠ 0: `failed`, `error = "Cài PyTorch CUDA thất bại (mã N)"` → mã 0: `probe(refresh=True)`; `torch_cuda` False → `failed`, `error = "Đã cài PyTorch nhưng không dùng được CUDA — kiểm tra driver NVIDIA"`; True → `done`, gọi `on_done()`. `install_cmd is None` → `failed`, `error = "Không tìm thấy uv"`.

- [ ] **Step 1: Write failing tests** (dùng lệnh giả `[sys.executable, "-c", "..."]`):
  - `test_probe_nvidia_present`: nvidia_cmd in `"NVIDIA GeForce RTX 3060"` → `nvidia=True, gpu_name="NVIDIA GeForce RTX 3060"`.
  - `test_probe_nvidia_missing`: nvidia_cmd = `["khong-co-lenh-nay"]` → `nvidia=False, gpu_name=None`.
  - `test_probe_cached_until_refresh`: torch_cmd đọc 1 file cờ; đổi file → `probe()` vẫn cũ, `probe(refresh=True)` mới.
  - `test_install_success_calls_on_done`: install in 2 dòng, thoát 0; torch_cmd thoát 0 → state `done`, `log_tail` có 2 dòng, `on_done` gọi 1 lần.
  - `test_install_failure_keeps_cpu`: install thoát 3 → `failed`, error chứa `"mã 3"`, `on_done` không gọi.
  - `test_install_ok_but_no_cuda`: install thoát 0, torch_cmd thoát 1 → `failed`, error chứa `"driver NVIDIA"`.
  - `test_install_twice_runs_once`: install `time.sleep(0.5)`; `start_install` lần 2 trong lúc chạy trả `False`.
- [ ] **Step 2: Run** `uv run python -m pytest backend/tests/tts/test_gpu.py -v` → FAIL.
- [ ] **Step 3: Implement** `tts/gpu.py`; `start_install` tạo task bằng `asyncio.get_running_loop().create_task` và giữ tham chiếu trong instance.
- [ ] **Step 4: Run** lại → PASS.
- [ ] **Step 5: Commit** `feat(tts): detect NVIDIA/torch CUDA and install PyTorch CUDA in background`

### Task 3: Route `/api/tts/device` và `/api/tts/install-cuda`

**Files:**
- Modify: `backend/tts_stt_tool/api/app.py` (field `gpu: GpuSetup` trong `AppContext`, tham số `gpu: GpuSetup | None = None` cho `create_app`, mặc định `GpuSetup()`), `backend/tts_stt_tool/api/routes.py` (mục mới sau `# -- settings / health`)
- Test: `backend/tests/api/test_tts_device_routes.py`

**Interfaces:**
- Consumes: Task 1 `set_device`, `active_device`, `load_error`; Task 2 `GpuSetup`.
- Produces (JSON cho frontend):
  - `GET /api/tts/device` → `{"device": "cpu"|"cuda", "active": "cpu"|"cuda"|null, "load_error": str|null, "nvidia": bool, "gpu_name": str|null, "torch_cuda": bool, "uv": bool, "install": {state, log_tail, error}}`. `active`/`load_error` lấy bằng `getattr(ctx.tts, ..., None)`.
  - `PUT /api/tts/device {"device": "cpu"|"cuda"}` → 409 `"Đang có tác vụ chạy, đợi xong rồi đổi"` khi có job; `cuda` + `nvidia=False` → 409 `"Máy không có GPU NVIDIA"`; `cuda` → luôn `probe(refresh=True)` trước (người dùng có thể đã tự cài), `torch_cuda=False` → 409 `"Chưa có PyTorch CUDA"`; hợp lệ → lưu `settings.tts_device`, `save_settings`, gọi `ctx.tts.set_device` nếu có, trả như GET.
  - `POST /api/tts/install-cuda` → 400 `"Máy không có GPU NVIDIA"` khi `nvidia=False`; ngược lại `start_install(on_done)` với `on_done` = đặt `tts_device="cuda"` + save + `set_device("cuda")`; trả như GET (state `running`). Gọi khi đang chạy → vẫn 200, không chạy lần 2.

- [ ] **Step 1: Write failing tests** — fixture như `test_routes.client` nhưng truyền `gpu=GpuSetup(nvidia_cmd=..., torch_cmd=..., install_cmd=...)` bằng lệnh giả; FakeTts thêm `set_device` ghi lại:
  - `test_get_device_reports_probe`: không NVIDIA → `nvidia False`, `device "cpu"`.
  - `test_put_cuda_without_nvidia_409`
  - `test_put_cuda_without_torch_409`: có NVIDIA, torch thoát 1 → 409 `"Chưa có PyTorch CUDA"`.
  - `test_put_cuda_reprobes`: torch giả đọc file cờ; GET (cờ chưa có → `torch_cuda False`), tạo cờ, PUT cuda → 200 không cần cài.
  - `test_put_cuda_ok_persists`: cả hai có → 200, `settings.json` có `"tts_device": "cuda"`, FakeTts nhận `set_device("cuda")`.
  - `test_put_device_while_job_running_409`: chạy job generate chậm (FakeTts sleep) rồi PUT → 409, settings vẫn `cpu`.
  - `test_install_cuda_then_device_is_cuda`: install giả thoát 0, torch giả đọc file cờ do install tạo → poll GET tới `install.state == "done"` (≤5s) → `device == "cuda"`.
  - `test_install_cuda_without_nvidia_400`
- [ ] **Step 2: Run** `uv run python -m pytest backend/tests/api/test_tts_device_routes.py -v` → FAIL.
- [ ] **Step 3: Implement** routes + context wiring.
- [ ] **Step 4: Run** toàn bộ `uv run python -m pytest` → PASS (gồm `test_settings_roundtrip_and_health`).
- [ ] **Step 5: Commit** `feat(api): TTS device selection and CUDA install routes`

### Task 4: `TestbenchPanel` thay chân sidebar

**Files:**
- Modify: `frontend/src/api.ts` (type `TtsDevice`, `api.ttsDevice()`, `api.setTtsDevice(device)`, `api.installCuda()`)
- Create: `frontend/src/components/TestbenchPanel.tsx`, `frontend/src/components/TestbenchPanel.test.tsx`
- Modify: `frontend/src/components/Sidebar.tsx` (bỏ `StatusChip`, `adbShort`, khối `side-footer` cũ; render `<TestbenchPanel health={health} device={device} jobRunning={!!health?.job} />` + `ThemeSwitch` ở hàng tiêu đề panel), `frontend/src/components/Sidebar.test.tsx` (xóa block "Sidebar status row" và `adbStatus`), `frontend/src/styles.css` (thay `.status-row/.status-chip` bằng `.testbench*`)

**Interfaces:**
- Consumes: JSON của Task 3; `Health`, `DeviceStatus` có sẵn trong `api.ts`.
- Produces: `export function readiness(health: Health | null, device: DeviceStatus | null): { ready: boolean; hint: string | null }` và `export function TestbenchPanel(props: { health: Health | null; device: DeviceStatus | null; jobRunning: boolean })`.

Câu chữ cố định:
- Tiêu đề `Thiết bị kiểm thử`; nút thu gọn `aria-label="Thu gọn"`/`"Mở rộng"`, nhớ trong `localStorage["testbench.open"]` (bọc try/catch).
- Badge: `Sẵn sàng test` / `Chưa sẵn sàng test`. Ready = `health?.wyoming` và có thiết bị `state === "device"`.
- Hint ưu tiên: STT không chạy → `Chưa chạy STT tham chiếu — Verify sẽ không dùng được`; không có adb → `Không tìm thấy adb`; không thiết bị → `Cắm điện thoại qua USB và bật Gỡ lỗi USB`; thiết bị unauthorized → `Mở khóa điện thoại và bấm "Cho phép" gỡ lỗi USB`.
- Dòng `Điện thoại · ADB`: mỗi thiết bị một dòng `<model ?? serial>` + chấm (device=ok, unauthorized/offline=warn) + nhãn trạng thái (`Đã kết nối`/`Chưa cho phép`/`Mất kết nối`), tooltip là serial; không có → `Chưa có thiết bị` (bad).
- Dòng `STT tham chiếu`: `Sẵn sàng` (ok) / `Chưa chạy` (bad, tooltip `wyoming_error`).
- Dòng `Sinh audio (TTS)`: nút gạt `CPU | GPU` (`role="radiogroup"`, hai `button` `aria-pressed`). Cả hai disabled khi `jobRunning` hoặc install `running` (tooltip `Đang có tác vụ chạy`). GPU disabled khi `nvidia === false` (tooltip `Máy không có GPU NVIDIA`). Dưới nút: `GPU · <gpu_name>` hoặc `CPU`; nếu `load_error` → dòng warn `Không nạp được GPU, đang dùng CPU`.
- Bấm GPU: luôn gọi `setTtsDevice("cuda")` trước (backend dò lại CUDA). Thành công → xong, không hỏi gì. Chỉ khi trả 409 `"Chưa có PyTorch CUDA"` mới `window.confirm("Chưa có PyTorch CUDA. Tải và cài khoảng 2.5 GB? Trong lúc cài vẫn sinh audio bằng CPU được.")` → đồng ý gọi `installCuda`. Install `running` → `Đang cài PyTorch CUDA…` + dòng cuối `log_tail`; `failed` → `error` màu bad + nút `Thử lại`.
- Poll `/api/tts/device` mỗi 2s khi install `running`, còn lại 10s.

- [ ] **Step 1: Write failing tests** (mock `api` bằng `vi.spyOn`):
  - `readiness`: ready khi STT ok + 1 device; hint đúng thứ tự ưu tiên cho 4 trường hợp ở trên.
  - `lists every phone`: 2 thiết bị (`Pixel 7` device, `S2` unauthorized) → thấy cả `Pixel 7` và `S2`, `Chưa cho phép`.
  - `GPU locked without NVIDIA`: `nvidia:false` → nút `GPU` disabled, title `Máy không có GPU NVIDIA`.
  - `asks before installing`: `nvidia:true`, `setTtsDevice` reject 409 `"Chưa có PyTorch CUDA"`, `confirm` trả true → gọi `installCuda` 1 lần; trả false → không gọi.
  - `switches without asking when CUDA ready`: `setTtsDevice` thành công → `confirm` không được gọi, `installCuda` không được gọi.
  - `locked while job runs`: `jobRunning` → cả hai nút disabled.
  - `shows install failure with retry`: install `failed`, `error:"x"` → thấy `x` và nút `Thử lại`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/TestbenchPanel.test.tsx` → FAIL.
- [ ] **Step 3: Implement** api + component + Sidebar wiring + CSS (dùng token màu có sẵn `--ok/--warn/--bad/--muted/--border`).
- [ ] **Step 4: Run** `cd frontend && npx vitest run && npx tsc -b` → PASS, không lỗi kiểu.
- [ ] **Step 5: Commit** `feat(ui): test bench panel with device list and CPU/GPU switch`

### Task 5: README + kiểm tra trên app thật

**Files:** Modify `README.md` mục "GPU (tùy chọn)": thay hướng dẫn lệnh tay bằng "Chọn GPU trong bảng Thiết bị kiểm thử; app tự cài PyTorch CUDA (~2.5 GB) nếu máy có card NVIDIA", giữ lệnh tay làm phương án dự phòng.

- [ ] **Step 1:** Sửa README.
- [ ] **Step 2:** `cd frontend && npm run build`, chạy `uv run python -m tts_stt_tool`, mở trang: panel hiện, GPU bị khóa với tooltip `Máy không có GPU NVIDIA` trên máy không có NVIDIA, sinh 1 câu audio bằng CPU vẫn chạy.
- [ ] **Step 3: Commit** `docs: GPU setup through the test bench panel`
