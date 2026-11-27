# Khối 2 chạy song song 2 thiết bị — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một lần bấm chạy Khối 2 trên 2 máy; mỗi câu phát loa 1 lần, cả hai máy cùng nghe; mỗi máy là một lần test riêng (log, ảnh, Excel riêng); giao diện có tab chuyển giữa 2 máy.

**Architecture:** Tách thao tác một câu (`_run_one`) thành 3 pha (prepare / phát+baseline / read_result). Vòng lặp mới `run_block2_multi` chạy các pha song song cho các "lane" (lần test + driver), áp luật thử lại riêng từng lane; `run_block2` cũ = 1 lane. DB nối 2 lần test bằng `pair_run_id`; API tạo/tiếp tục cặp; frontend giữ log theo `run_id` và hiện tab chuyển máy.

**Tech Stack:** Python 3 / asyncio / FastAPI / SQLite (pytest, `asyncio_mode=auto`); React + TypeScript (vitest + Testing Library).

**Spec:** `docs/superpowers/specs/2026-11-27-dual-device-block2-design.md`

## Global Constraints

- Không phát âm thanh ra loa thật, không gửi lệnh tới máy thật trong mọi bước kiểm thử: chỉ `FakeApp` / loa giả.
- Chạy 1 máy giữ nguyên hành vi, trừ: lỗi thao tác được thử lại 1 lần (`OP_ERROR_RETRIES = 1`).
- `NOT_HEARD_RETRIES = 1`, `MAX_CONSECUTIVE_OP_ERRORS = 5`, `RETRY_PAUSE_S = 1.0` giữ giá trị hiện tại.
- Lane chạm 5 lỗi thao tác liên tiếp → dừng cả hai; `cancel` → dừng cả hai.
- Mic của máy nhanh mở ≤ ~1,5 s trước khi phát (trường hợp bình thường).
- Chuỗi hiển thị bằng tiếng Việt, theo giọng văn log hiện có.
- Không file Excel gộp; xuất theo lần test như hiện nay.

## Review Focus

1. Máy thứ hai rút cáp giữa chừng → lane đó lỗi thao tác liên tiếp → sau 5 câu dừng cả hai, câu chưa chạy của **cả hai** lần test vẫn `Chờ`. (Test ở Task 2: `test_one_lane_five_op_errors_stops_both`.)
2. Tiếp tục một cặp mà hai lần test có số câu chờ khác nhau → mỗi lane chỉ chạy câu của nó, không phát loa cho câu không lane nào cần. (Task 2: `test_resume_lanes_with_different_pending`.)
3. Xóa một lần test trong cặp → lần còn lại vẫn mở/tiếp tục được như lần test đơn. (Task 3: `test_delete_one_of_pair_unlinks_other`; Task 4: `test_resume_pair_when_partner_deleted`.)
4. Tạo cặp với `serial2 == serial` → 422, không tạo lần test nào. (Task 4: `test_pair_same_serial_rejected`.)
5. Event log của job cặp đến trong khi đang xem máy kia → không lẫn vào log máy đang xem. (Task 6: `logs are kept per run`.)

---

## File Structure

- Modify `backend/tts_stt_tool/pipeline/block2.py` — 3 pha, `Lane`, `run_block2_multi`, luật thử lại.
- Modify `backend/tts_stt_tool/jobs/runner.py` — `ProgressEvent.run_id`.
- Modify `backend/tts_stt_tool/store/db.py` — cột `pair_run_id`, `link_pair`, xóa gỡ liên kết.
- Modify `backend/tts_stt_tool/api/app.py`, `api/routes.py` — `busy_serials`, tạo/tiếp tục cặp.
- Create `backend/tests/pipeline/test_block2_multi.py`; modify `tests/pipeline/test_block2_one.py`, `test_block2_run.py`, `tests/api/test_block2_routes.py`, store test file hiện có cho app_runs.
- Modify `frontend/src/api.ts`, `App.tsx`, `components/AppRunPanel.tsx`, `components/DevicePanel.tsx` + test tương ứng; có thể tạo `components/PairTabs.tsx`.

---

### Task 1: Tách `_run_one` thành 3 pha

**Files:**
- Modify: `backend/tts_stt_tool/pipeline/block2.py` (`_run_one`, ~dòng 223-321)
- Test: `backend/tests/pipeline/test_block2_one.py`

**Interfaces:**
- Produces (trong `block2.py`):
  - `async def prepare(dev: DeviceDriver, p: AppProfile, log: list[str], sleep: Sleep) -> None` — `ensure_home`, bấm `open_label`, `_wait_mic`, `sleep(p.pre_delay_s)`.
  - `async def speak(devs: list[DeviceDriver], wav: Path, player: AudioPlayer, logs: list[list[str]]) -> list[list[UiNode] | BaseException]` — tạo task `dev.nodes()` cho từng máy, `await asyncio.sleep(0)`, ghi `Phát <tên>` vào từng log, `await asyncio.to_thread(player.play, wav)` **một lần**, rồi gather baseline với `return_exceptions=True`.
  - `async def read_result(dev: DeviceDriver, p: AppProfile, base: list[UiNode], log: list[str], sleep: Sleep, is_correct: Callable[[str], bool] | None) -> AppCapture` — phần từ `if not _sheet_open(base, p)` tới hết `_run_one`.
  - `run_one(...)` giữ nguyên chữ ký; thân = `prepare` → `speak([dev], …)` (baseline lỗi thì raise) → `read_result`.

- [ ] **Step 1: Viết test hỏng** trong `test_block2_one.py`:
  - `test_speak_plays_once_for_two_devices`: hai `FakeApp` ở trạng thái đã `prepare`; loa giả là object có `play(path)` gọi `a.play(path); b.play(path)` và đếm số lần; `await speak([a, b], wav, spk, [[], []])` → `spk.calls == 1`, `a.played == [wav]`, `b.played == [wav]`, hai phần tử trả về là list node.
  - `test_phases_compose_like_run_one`: một `FakeApp()`; `log=[]`; `await prepare(app, prof, log, no_sleep)`; `[base] = await speak([app], wav, app, [log])`; `cap = await read_result(app, prof, base, log, no_sleep, None)` → `cap.text == app.transcript` và `app.taps` bằng đúng chuỗi tap khi gọi `run_one` trên một `FakeApp()` mới.
- [ ] **Step 2:** `cd backend && uv run pytest tests/pipeline/test_block2_one.py -q` → FAIL (`ImportError: cannot import name 'prepare'`).
- [ ] **Step 3:** Hiện thực 3 hàm như Interfaces; `_run_one` chỉ còn là hàm nối 3 pha.
- [ ] **Step 4:** `uv run pytest tests/pipeline -q` → PASS (toàn bộ test cũ của `run_one` vẫn qua).
- [ ] **Step 5: Commit** `refactor(block2): split one sentence into prepare/speak/read phases`.

---

### Task 2: `run_block2_multi` — lane, luật thử lại, độ trễ, `run_id` trên event

**Files:**
- Modify: `backend/tts_stt_tool/pipeline/block2.py` (`run_block2`, ~dòng 337-421)
- Modify: `backend/tts_stt_tool/jobs/runner.py` (`ProgressEvent`)
- Create: `backend/tests/pipeline/test_block2_multi.py`
- Modify: `backend/tests/pipeline/test_block2_run.py`

**Interfaces:**
- Consumes: `prepare`, `speak`, `read_result` (Task 1).
- Produces:
  - `ProgressEvent.run_id: int | None = None` (thêm sau `message`, trước `lane`).
  - `@dataclass class Lane: run_id: int; dev: DeviceDriver; shots_dir: Path | None = None` (+ state nội bộ tùy ý: đếm lỗi liên tiếp, thời gian prepare đo được).
  - `Attempt = Callable[[list[Lane], Path, AudioPlayer, list[Callable[[str], bool] | None]], Awaitable[list[AppCapture | BaseException]]]` — chạy **một lượt** câu này cho các lane cho trước, trả kết quả theo đúng thứ tự lane. Lỗi mang `.log` như hiện nay.
  - `async def run_block2_multi(store: Store, lanes: list[Lane], profile: AppProfile, player: AudioPlayer, settings: Settings, emit: Emit, cancel: asyncio.Event, attempt: Attempt | None = None, pause=pause_unless_cancelled) -> None`
  - `run_block2(...)` giữ chữ ký cũ (kể cả `run_one=`); dựng `Lane(app_run_id, dev, shots_dir)` và một `attempt` 1-lane gọi `run_one(dev, profile, wav, player, **kw)` (kw chỉ có `is_correct` khi có `shots_dir`, như hiện nay), rồi gọi `run_block2_multi`.
  - `OP_ERROR_RETRIES = 1`.

**Hành vi `run_block2_multi`** (theo spec mục 2):
- Câu chờ của mỗi lane = `store.pending_for_block2(lane.run_id)`; ghép theo `item_id`, thứ tự `item_id` tăng; mỗi câu chỉ chạy cho lane có câu đó. `total` = số `item_id` khác nhau; `done` đếm theo câu.
- Mỗi lượt: gọi `attempt(các lane cần chạy, wav, player, is_correct từng lane)`. Lane có kết quả `not_heard and not text` và còn lượt `NOT_HEARD_RETRIES` → chạy lại; lane có exception và còn lượt `OP_ERROR_RETRIES` → chạy lại; các lane chạy lại đi **cùng một lượt**; `pause(RETRY_PAUSE_S)` trước lượt thử lại. Log nối: `— Phát lại lần N —` / `— Thử lại sau lỗi thao tác —`.
- Chốt từng lane: thành công → `compare` với ngưỡng đọc từ `store.get_app_run(lane.run_id)` mỗi câu → ghi PASSED/FAILED + ảnh `cap.screenshot`; lỗi cuối → `_try_screencap(lane.dev, log)` rồi ghi OP_ERROR (giữ hàm `save_shot` hiện có theo `lane.shots_dir`).
- Mọi event `log`/`item` của lane mang `run_id=lane.run_id`; với >1 lane, tiền tố dòng log tổng `"[i/n] tc_id"` giữ nguyên.
- Lane chạm 5 lỗi liên tiếp → emit `error` `"Dừng sau 5 lỗi thao tác liên tiếp trên máy <serial hoặc run_id>: <msg>"` (với 1 lane giữ đúng chuỗi cũ chứa `"5 lỗi thao tác"`) và return.
- `between_delay_s`, `cancel` như hiện nay.
- `attempt` mặc định (nhiều lane): `prepare` song song (`gather(return_exceptions=True)`) với **độ trễ khởi động**: lane có thời gian `prepare` đo được ở lượt trước ngắn hơn lane chậm nhất bắt đầu trễ đúng phần chênh (lượt đầu trễ 0); sau `prepare`, lane có `await dev.mic_active() is False` → `OperationError("Mic đã tắt trước khi phát")`; `speak` cho các lane còn lại; `read_result` song song.

- [ ] **Step 1: Viết test hỏng** `test_block2_multi.py`. Fixture: store với 3 câu có WAV (như `env` của `test_block2_run.py`), hai lần test `A`,`B`. Hai helper:
  - `scripted_attempt(answers)` — `answers[(run_id, wav.name)]` là list theo lượt: `str | None | "NOT_HEARD" | Exception`; ghi lại `calls: list[tuple[str, tuple[int, ...]]]` = (tên wav, các run_id trong lượt).
  - `two_apps()` — hai `FakeApp(transcript=…)` + `Speaker` đếm `calls` và chuyển `play` cho cả hai app.

  Các test (giá trị cụ thể):
  - `test_each_sentence_plays_once_for_both`: `two_apps`, `attempt` mặc định, profile nhanh (delay 0, `listen_timeout_s=0.1`, `result_timeout_s=0.1`, `monkeypatch POLL_S=0.001`) → `speaker.calls == 3`; cả hai lần test `{"Sai": 3}` hoặc `"Đúng"` tùy transcript; kết quả mỗi `app_run` có `app_text` của app tương ứng (dùng transcript khác nhau cho A, B).
  - `test_not_heard_retries_only_that_lane`: A câu 1 `["NOT_HEARD", "bật đèn"]` → `calls` câu 1 = `[(w1,(A,B)), (w1,(A,))]`; A câu 1 PASSED; câu 2 lại `(A,B)`.
  - `test_op_error_retries_once_alone`: B câu 1 `[OperationError("x"), "bật đèn"]` → lượt 2 chỉ `(B,)`; B câu 1 PASSED; log chứa `"— Thử lại sau lỗi thao tác —"`.
  - `test_both_fail_retry_together`: A `["NOT_HEARD","bật đèn"]`, B `[OperationError("x"),"bật đèn"]` → lượt 2 `(A,B)`.
  - `test_op_error_twice_records_op_error`: B câu 1 `[OperationError("x"), OperationError("y")]` → OP_ERROR, error `"y"`; A câu 1 không bị ảnh hưởng.
  - `test_one_lane_five_op_errors_stops_both`: 7 câu; B luôn `OperationError` → event cuối `kind=="error"`, `"5 lỗi thao tác"` trong message; B `{OP_ERROR:5, PENDING:2}`; A `PENDING == 2`.
  - `test_cancel_stops_both`: set `cancel` ở event `item` đầu tiên → event cuối `cancelled`; cả hai còn `PENDING`.
  - `test_resume_lanes_with_different_pending`: A câu 1 đã PASSED trước → câu 1 chỉ `(B,)`, câu 2-3 `(A,B)`; `len(calls) == 3`.
  - `test_events_carry_run_id`: mọi event `item` có `run_id == item["app_run_id"]`.
  - `test_mic_off_before_play_is_op_error`: `two_apps`, A có `silence_dumps=0` + prepare chậm giả lập sao cho `mic_active()` trả False khi tới pha phát → lượt đầu A là op error, `speaker` vẫn phát cho B; A thử lại lượt 2 một mình.
  - `test_fast_lane_starts_later`: `attempt` mặc định với hai driver giả có `prepare` mất 0,05 s và 0,25 s (`nodes()`/`mic_active` có `await asyncio.sleep`), ghi thời điểm mic bật và thời điểm `play` → từ câu 2, khoảng mic-bật→phát của lane nhanh `< 0.1` s.
  - Trong `test_block2_run.py` thêm `test_op_error_retried_once_then_passes` (1 lane: câu 1 lần đầu `OperationError`, lần hai text đúng → PASSED, `len(fake.seen_prev) == 8` cho 7 câu).
- [ ] **Step 2:** `uv run pytest tests/pipeline/test_block2_multi.py tests/pipeline/test_block2_run.py -q` → FAIL (import `Lane`/`run_block2_multi`).
- [ ] **Step 3:** Thêm `run_id` vào `ProgressEvent`; hiện thực `Lane`, `run_block2_multi`, `attempt` mặc định, viết lại `run_block2` thành wrapper.
- [ ] **Step 4:** `uv run pytest tests -q` → PASS toàn bộ (sửa test cũ chỉ nơi hành vi chủ ý đổi: lỗi thao tác giờ gọi `run_one` 2 lần — ví dụ đếm cuộc gọi).
- [ ] **Step 5: Commit** `feat(block2): run sentences on several devices with one playback`.

---

### Task 3: DB — nối cặp lần test

**Files:**
- Modify: `backend/tts_stt_tool/store/db.py` (schema ~dòng 80-86, migration ~dòng 166, `delete_app_run` ~dòng 451)
- Test: file test store hiện có cho app_runs (tìm `create_app_run` trong `backend/tests/store/`)

**Interfaces:**
- Produces: cột `app_runs.pair_run_id INTEGER NULL`; `Store.link_pair(a: int, b: int) -> None` (đặt hai chiều); `get_app_run` / `list_app_runs` tự có `pair_run_id` (SELECT *); `delete_app_run(run_id)` đặt `pair_run_id=NULL` cho lần còn lại.

- [ ] **Step 1: Test hỏng:** `test_link_pair_sets_both` (`get_app_run(a)["pair_run_id"] == b` và ngược lại); `test_delete_one_of_pair_unlinks_other` (xóa `a` → `get_app_run(b)["pair_run_id"] is None`); `test_old_db_gets_pair_column` (DB tạo bằng schema cũ không có cột — dùng mẫu test migration `wer_threshold` hiện có nếu có — mở lại `Store` → cột tồn tại, giá trị NULL).
- [ ] **Step 2:** chạy test store → FAIL.
- [ ] **Step 3:** Thêm cột vào `CREATE TABLE` + migration `ALTER TABLE app_runs ADD COLUMN pair_run_id INTEGER` cạnh migration `wer_threshold`; `link_pair`; gỡ liên kết trong `delete_app_run` (cùng transaction).
- [ ] **Step 4:** `uv run pytest tests/store -q` → PASS.
- [ ] **Step 5: Commit** `feat(store): link the two runs of a paired block 2 job`.

---

### Task 4: API — `busy_serials`, tạo cặp, tiếp tục cặp

**Files:**
- Modify: `backend/tts_stt_tool/api/app.py` (`busy_serial` dòng 52)
- Modify: `backend/tts_stt_tool/api/routes.py` (`_require_free` ~51, `/device` ~597, ios disconnect ~621, `AppRunIn`/`_start_block2`/`create_app_run`/`resume_app_run` ~754-810)
- Test: `backend/tests/api/test_block2_routes.py`

**Interfaces:**
- Consumes: `Lane`, `run_block2_multi` (Task 2); `link_pair`, `pair_run_id` (Task 3).
- Produces:
  - `AppContext.busy_serials: set[str]` (thay `busy_serial`).
  - `GET /api/device` → `"busy": list[str]` (sắp xếp).
  - `AppRunIn.serial2: str | None = None`. `POST /audio-sets/{id}/app-runs` với `serial2` → `{"id": a, "pair_id": b, "job_id": …}`; không có → `{"id", "job_id"}` như cũ (`pair_id` vắng hoặc `None`).
  - `_start_block2(ctx, set_id, runs: list[tuple[int, str]], profile) -> str` — `runs` = [(run_id, serial)]; job thêm tất cả serial vào `busy_serials`, dựng `Lane` cho từng cặp (`ctx.device(serial)`, `ctx.run_dir(run_id)`), gọi `run_block2_multi`, `finally` gỡ serial. Tên job: 1 lane `"Khối 2 – lần test {id}"`, 2 lane `"Khối 2 – lần test {a} + {b}"`.
  - `resume`: nếu `pair_run_id` trỏ tới lần test còn tồn tại và serial của nó có trong danh sách máy đang kết nối (`/device` logic; với `device_factory` trong test coi mọi serial là kết nối) → chạy cả hai; ngược lại chỉ lần này.
  - `rerun`: không đổi (1 lane).

- [ ] **Step 1: Test hỏng** (fixture `ctx` hiện có; `factory(serial)` trả `FakeApp` riêng theo serial — mở rộng fixture: `fakes: dict[str, FakeApp]`, `player` là loa giả phát tới mọi fake):
  - `test_pair_run_end_to_end`: POST `{"serial":"SER","serial2":"SER2","profile":name}` → 200, có `pair_id`; sau `wait_job_end`, mỗi lần test có 2 kết quả; `runs` liệt kê cả hai với `pair_run_id` trỏ nhau; loa giả `calls == 2` (2 câu).
  - `test_pair_same_serial_rejected`: `serial2 == serial` → 422; số lần test không đổi.
  - `test_busy_lists_both_phones`: như `test_manual_input_and_pin_blocked…` nhưng cặp → `busy == ["SER","SER2"]`; input tới `SER2` → 409; sau khi xong `busy == []`. Sửa test cũ đó: `busy == ["SER"]` rồi `[]`.
  - `test_resume_pair_runs_both`: tạo cặp, hủy job sau item đầu (`POST /jobs/{id}/cancel`), resume `a` → cả hai lần test hết `Chờ`.
  - `test_resume_pair_when_partner_deleted`: xóa `b`, resume `a` → 200, chạy 1 lane.
- [ ] **Step 2:** `uv run pytest tests/api/test_block2_routes.py -q` → FAIL.
- [ ] **Step 3:** Hiện thực như Interfaces; đọc model/phiên bản riêng cho từng máy; tạo 2 lần test với cùng `item_ids` và `wer_threshold`; nếu lần test nào rỗng → xóa cả hai, 422 như hiện nay.
- [ ] **Step 4:** `uv run pytest tests -q` → PASS.
- [ ] **Step 5: Commit** `feat(api): start and resume block 2 on two phones`.

---

### Task 5: Frontend — chọn "Cả 2 máy" và gọi API cặp

**Files:**
- Modify: `frontend/src/api.ts` (`DeviceStatus.busy`, `AppRun`, `ProgressEvent`, `startAppRun`)
- Modify: `frontend/src/components/AppRunPanel.tsx` (+ `AppRunPanel.test.tsx`)
- Modify: `frontend/src/components/DevicePanel.tsx:161` (`busy` là mảng) + test (`busy: ["S"]`)

**Interfaces:**
- Produces:
  - `DeviceStatus.busy?: string[]`; `AppRun.pair_run_id: number | null`; `ProgressEvent.run_id?: number | null`.
  - `api.startAppRun(setId, serial, profile, itemIds, serial2?: string | null) => Promise<{ id: number; pair_id?: number | null; job_id: string }>` (gửi `serial2` chỉ khi có).
  - `AppRunPanel` prop `onStart: (serial: string, profile: string, serial2?: string) => void`.

- [ ] **Step 1: Test hỏng** trong `AppRunPanel.test.tsx`:
  - `offers both phones when two are ready`: 2 máy `state:"device"` (`M1` android, `M2` ios) → ô "Thiết bị" có option `"Cả 2 máy (M1 + M2)"`; chọn nó, bấm nút → `onStart("S1", profile, "S2")`; nhãn nút chứa `"2 máy"`.
  - `asks for the second phone when more than two`: 3 máy, chọn "Cả 2 máy" → hiện select `aria-label="Máy thứ hai"` không chứa máy đầu; `onStart` nhận máy được chọn.
  - `no pair option with one phone`: 1 máy → không có option "Cả 2 máy".
  - `DevicePanel.test.tsx`: `busy: ["S"]` vẫn khóa thao tác tay.
- [ ] **Step 2:** `cd frontend && npx vitest run src/components/AppRunPanel.test.tsx src/components/DevicePanel.test.tsx` → FAIL.
- [ ] **Step 3:** Hiện thực; giá trị select cho cặp dùng hằng `"__pair__"`; "Chạy lại" chỉ bật khi không chọn cặp (máy đang xem).
- [ ] **Step 4:** chạy lại → PASS; `npx tsc --noEmit` sạch.
- [ ] **Step 5: Commit** `feat(ui): start block 2 on both phones`.

---

### Task 6: Frontend — tab chuyển máy, log theo máy, màn hình theo máy

**Files:**
- Modify: `frontend/src/App.tsx` (state log ~dòng 62, event handler ~199-216, `startApp` ~253, KPI ~410, `<DevicePanel>` ~528)
- Create: `frontend/src/components/PairTabs.tsx`
- Modify: `frontend/src/components/DevicePanel.tsx` (prop `serial`)
- Test: `frontend/src/App.test.tsx`, `frontend/src/components/DevicePanel.test.tsx`

**Interfaces:**
- Consumes: `AppRun.pair_run_id`, `ProgressEvent.run_id`, `startAppRun(..., serial2)` (Task 5).
- Produces:
  - `PairTabs({ runs: [AppRun, AppRun], current: number, onSelect: (id: number) => void })` — 2 nút, nhãn `"<Android|iPhone> · <device_model ?? serial>"` (nền tảng lấy từ danh sách thiết bị nếu có, không có thì chỉ tên máy), nút đang chọn `aria-pressed="true"`.
  - `DevicePanel` prop `serial?: string | null` — khi đổi, chọn máy đó (ghi đè `picked`).
  - App: `jobLogs: Map<number | "all", string[]>`; event có `run_id` → vào khóa đó; không có → vào mọi khóa đang hiện + `"all"`; `DevicePanel` nhận log của `appRunId` (gộp dòng chung).

- [ ] **Step 1: Test hỏng:**
  - `App.test.tsx` `shows pair tabs and switches runs`: mock `appRuns` trả 2 lần test nối nhau (`pair_run_id`) → thấy 2 tab; bấm tab thứ hai → KPI hiện `#<id2>` và kết quả tải cho `id2`.
  - `App.test.tsx` `logs are kept per run`: phát 2 event `log` với `run_id` khác nhau (qua mock `connectEvents` hiện có trong test) → khi xem run 1 chỉ thấy dòng của run 1; chuyển tab → thấy dòng run 2.
  - `App.test.tsx` `starting a pair selects the first run`: `startAppRun` trả `{id: 7, pair_id: 8}` → `appRunId` = 7, tab hiện.
  - `DevicePanel.test.tsx` `follows the serial prop`: 2 máy, `serial="S2"` → màn hình/khóa theo S2.
- [ ] **Step 2:** `npx vitest run src/App.test.tsx src/components/DevicePanel.test.tsx` → FAIL.
- [ ] **Step 3:** Hiện thực; tab đặt cạnh KPI trên thanh trên cùng (spec mục 5 sketch); không có `pair_run_id` hoặc lần kia không có trong `appRuns` → không hiện tab.
- [ ] **Step 4:** `npx vitest run` toàn bộ + `npx tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** `feat(ui): switch between the two phones of a paired run`.

---

### Task 7: Kiểm tra cuối

- [ ] `cd backend && uv run pytest -q` → toàn bộ PASS.
- [ ] `cd frontend && npx vitest run && npx tsc --noEmit` → PASS.
- [ ] Không chạy app với máy thật / loa thật; báo người dùng phần cần thử trên máy thật (độ trễ khởi động thực tế giữa Android và iPhone).
