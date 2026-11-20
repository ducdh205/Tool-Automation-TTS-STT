# Kế hoạch 2 — Khối 2: test trên app Android thật

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Với một bộ audio đã verify (Khối 1), tool tự bấm mic trên app Android, phát audio qua loa máy tính, đọc câu app nhận được, so sánh WER/CER với câu gốc và báo cáo tỉ lệ đúng của app.

**Architecture:** Chỉ dùng công cụ có sẵn của Android qua `adb` (máy công ty khóa, không cài APK): `uiautomator dump` đọc cây giao diện, `input tap/keyevent` thao tác, `screencap` cho màn hình mirror. Logic một câu (`run_one`) nói chuyện với thiết bị qua interface `DeviceDriver` để test bằng thiết bị giả mô phỏng app. Job Khối 2 dùng chung `JobRunner`, `compare` và báo cáo của Kế hoạch 1.

**Tech Stack:** Python 3.12 (uv), adb (vendor/platform-tools), `winsound` (stdlib) phát WAV, FastAPI, React; Playwright + Microsoft Edge để test giao diện trên trình duyệt.

**Spec:** `docs/superpowers/specs/2026-11-20-tts-stt-automation-design.md` (§5.3, §5.5, §5.6, §5.7)

## Phát hiện trên máy thật (2026-11-20, Xiaomi 22120RN86G, Android 13, 720×1650)

App `com.vita.suite.dev` ("Work"). Giao diện đọc được qua `content-desc` trong `uiautomator dump`:
- Màn hình chính: nút mic `content-desc="Nói để tạo việc"` (Button, bounds `[304,1436][416,1507]`).
- Bấm mic → bảng **"Tạo việc"** mở và **tự bắt đầu nghe**; nút giữa thành `"Dừng nghe"`; `EditText` hiện text tạm.
- Bấm `"Dừng nghe"` → nút thành `"Bấm để nói"`; câu nhận được xuất hiện thành **bong bóng căn phải** (ví dụ `content-desc="chỉnh nhiệt độ ghế lái lên 24 độ"` bounds `[244,920][660,960]`); app tự gửi cho trợ lý, trợ lý trả lời bằng bong bóng **căn trái** (x1 = 32). Nhận không được: app hiện "Chưa nghe rõ. Thử lại hoặc gõ." (căn trái) và không có bong bóng phải mới.
- Nút `"Đóng"` (X) đóng bảng, về màn hình chính.
- Đã đo: audio VieNeu "Chỉnh nhiệt độ ghế lái lên hai mươi tư độ" phát qua loa PC → app nhận `chỉnh nhiệt độ ghế lái lên 24 độ` (khớp sau chuẩn hóa).
- Đã có sẵn (chưa commit, từ phiên trước): `backend/tts_stt_tool/device/adb.py` (devices, screencap, tap, swipe, key, text), API `/api/device`, `/api/device/{serial}/screen`, `/api/device/{serial}/input`, `DevicePanel` mirror bằng screencap. Kế hoạch này nhận và mở rộng phần đó.

## Global Constraints

- Không cài gì lên điện thoại; chỉ `adb` gốc. Không dùng uiautomator2/APK.
- Một điện thoại mỗi lần chạy; loa mặc định của máy tính phát audio.
- Chỉ test các câu **Đạt** ở Khối 1 (spec §5.2).
- Mỗi câu: mở mic → chờ `pre_delay_s` (mặc định **0.5**) → phát WAV → chờ `post_delay_s` (mặc định **1.0**) → dừng → đọc kết quả → đóng (spec §5.3).
- Lỗi thao tác → trạng thái **"Lỗi thao tác"**, không tính vào tỉ lệ đúng/sai; thử khôi phục rồi chạy câu tiếp.
- So sánh bằng `compare()` của Kế hoạch 1, cùng `wer_threshold`.
- Trạng thái kết quả app: `Chờ`, `Đúng`, `Sai`, `Lỗi thao tác`.
- Báo cáo: thêm sheet **"Khối 2 – App"** và **"Lỗi thao tác"** vào file Excel; Tổng quan có **tỉ lệ đúng của app** = Đúng / (Đúng + Sai) và theo từng sheet.
- Một bộ audio dùng lại được cho nhiều lần test app (spec §5.6).
- Lệnh adb trên Git Bash cần `MSYS_NO_PATHCONV=1` (code Python không bị ảnh hưởng).

## Review Focus

1. **App tự dừng nghe trước khi tool bấm dừng** → không được bấm vào nút (lúc đó là "Bấm để nói", bấm sẽ mở lượt nghe mới); vẫn đọc kết quả bình thường (Task 4).
2. **Câu lặp lại giống hệt câu trước** (cùng text bong bóng) → phải nhận ra bong bóng mới theo vị trí/số lượng, không theo tập text (Task 1).
3. **`uiautomator dump` lỗi chập chờn** ("could not get idle state" khi đang animation) → thử lại tối đa 3 lần rồi mới báo lỗi thao tác (Task 1).
4. **App không ở màn hình chính** (đang mở bảng cũ, đang ở tab khác, bị đẩy xuống nền) → khôi phục: bấm "Đóng" / Back tối đa 3 lần, rồi mở lại app bằng `monkey -p <package> 1`; vẫn không thấy nút mic → Lỗi thao tác có thông báo rõ (Task 4).
5. **Rút cáp giữa chừng** → 5 lỗi thao tác liên tiếp thì dừng job với thông báo rõ; kết quả đã có giữ nguyên, chạy tiếp được (Task 6).

---

## Cấu trúc file

```
backend/tts_stt_tool/device/adb.py        # (có sẵn) + dump_ui, launch, app_version
backend/tts_stt_tool/device/ui_tree.py    # parse dump, tìm node, phát hiện bong bóng mới
backend/tts_stt_tool/device/profile.py    # AppProfile + lưu/đọc JSON
backend/tts_stt_tool/device/player.py     # phát WAV
backend/tts_stt_tool/pipeline/block2.py   # run_one + run_block2
backend/tts_stt_tool/store/db.py          # + app_runs, app_results
backend/tts_stt_tool/report/excel.py      # + sheet Khối 2
backend/tts_stt_tool/api/routes.py        # + profiles, app-runs, node-at
frontend/src/components/{AppRunPanel,DevicePanel,ItemTable}.tsx
frontend/src/devicePoint.ts               # đổi toạ độ ảnh → toạ độ máy
tests/e2e/browser_e2e.py                  # Playwright + Edge
```

---

### Task 1: Đọc cây giao diện

**Files:** Create `backend/tts_stt_tool/device/ui_tree.py`; Modify `device/adb.py`; Test `backend/tests/device/test_ui_tree.py` (fixture XML lấy từ dump thật, lưu ở `backend/tests/fixtures/ui_*.xml`).

**Interfaces — Produces:**
- `@dataclass UiNode: text: str; desc: str; cls: str; bounds: tuple[int,int,int,int]; clickable: bool` + `label` (desc hoặc text), `center -> tuple[int,int]`
- `parse_dump(xml: str) -> list[UiNode]` (thứ tự tài liệu; bỏ node không có text/desc trừ EditText)
- `find(nodes, label: str) -> UiNode | None` — khớp `label` chính xác, sau đó khớp tiền tố
- `right_bubbles(nodes, screen_w: int) -> list[UiNode]` — node không phải Button/EditText, có label, `x1 > screen_w*0.25` và `x2 > screen_w*0.75`, sắp theo `y1`
- `new_bubble(before: list[UiNode], after: list[UiNode], screen_w: int) -> UiNode | None` — nếu số bong bóng phải tăng thì trả bong bóng cuối (theo y), ngược lại None
- `Adb.dump_ui(serial) -> str` — `shell uiautomator dump /sdcard/tts_stt_ui.xml` rồi `exec-out cat /sdcard/tts_stt_ui.xml`; thử lại 3 lần nếu output không chứa `<hierarchy`
- `Adb.screen_size(serial) -> tuple[int,int]` (parse `wm size`, ưu tiên "Override size")

- [ ] **Step 1: Test** — `parse_dump` trên fixture màn hình chính tìm được `find(nodes,"Nói để tạo việc").center == (360,1471)`; fixture sau khi dừng: `right_bubbles(...)[-1].label == "chỉnh nhiệt độ ghế lái lên 24 độ"`, bong bóng trái "Câu này chưa phải…" không bị tính; `new_bubble(before=fixture_listening, after=fixture_stopped, 720).label == "chỉnh nhiệt độ ghế lái lên 24 độ"`; **Review #2:** hai danh sách có bong bóng phải cùng text "bật đèn" (1 cái trước, 2 cái sau) → `new_bubble` trả node thứ hai; cùng số lượng → None. **Review #3:** `Adb.dump_ui` với `_run` giả trả lỗi 2 lần rồi XML → trả XML; lỗi 3 lần → `AdbError`. `wm size` "Physical size: 720x1650\nOverride size: 1080x2400" → (1080,2400).
- [ ] **Step 2–4:** FAIL → implement → PASS (`uv run python -m pytest backend/tests/device -q`).
- [ ] **Step 5:** Commit (gồm phần adb có sẵn): `feat(device): adb wrapper, UI tree parsing, bubble detection`.

### Task 2: Hồ sơ app

**Files:** Create `device/profile.py`; Test `backend/tests/device/test_profile.py`.

**Interfaces — Produces:** `@dataclass AppProfile: name="Vita Work (dev)"; package="com.vita.suite.dev"; open_label="Nói để tạo việc"; stop_label="Dừng nghe"; idle_label="Bấm để nói"; close_label="Đóng"; sheet_label="Tạo việc"; pre_delay_s=0.5; post_delay_s=1.0; listen_timeout_s=6.0; result_timeout_s=10.0`; `list_profiles(dir) -> list[AppProfile]` (luôn có hồ sơ mặc định); `save_profile(dir, p)`; `get_profile(dir, name) -> AppProfile` (`KeyError` nếu không có). File `data/profiles/<slug>.json`.

- [ ] Test: mặc định có trong danh sách khi thư mục trống; lưu hồ sơ tên "App B" rồi đọc lại đúng; JSON hỏng bị bỏ qua (không ném lỗi); khóa lạ bị bỏ qua. → FAIL → implement → PASS → commit `feat(device): app profiles`.

### Task 3: Phát audio

**Files:** Create `device/player.py`; Test `backend/tests/device/test_player.py`.

**Interfaces — Produces:** `class AudioPlayer(Protocol): def play(self, path: Path) -> None` (chặn tới khi phát xong); `class WinSoundPlayer` dùng `winsound.PlaySound(str(path), winsound.SND_FILENAME)`; file không tồn tại → `FileNotFoundError`.

- [ ] Test: file thiếu → `FileNotFoundError`; (đánh dấu `live`) phát WAV 0.3 s mất ≥ 0.25 s. → FAIL → implement → PASS → commit `feat(device): wav player`.

### Task 4: Một câu trên app (`run_one`)

**Files:** Create `backend/tts_stt_tool/pipeline/block2.py`; Test `backend/tests/pipeline/test_block2_one.py` với `FakeApp` mô phỏng app (trạng thái home / sheet-listening / sheet-idle / background, sinh XML theo trạng thái; `tap` theo toạ độ đổi trạng thái; tùy chọn `auto_stop`, `transcript=None` để mô phỏng "Chưa nghe rõ").

**Interfaces:**
- Produces: `class DeviceDriver(Protocol): async def nodes(self) -> list[UiNode]; async def tap(self, x: int, y: int) -> None; async def back(self) -> None; async def launch(self, package: str) -> None; screen_w: int`; `class AdbDriver(DeviceDriver)` (bọc `Adb` + serial).
- `@dataclass AppCapture: text: str | None; error: str | None; log: list[str]`
- `class OperationError(Exception)`
- `async def run_one(dev: DeviceDriver, profile: AppProfile, wav: Path, player: AudioPlayer, sleep=asyncio.sleep) -> AppCapture`
  1. `ensure_home`: tối đa 3 lần — có `open_label` thì xong; có `close_label` thì bấm; không thì `back()`. Sau đó vẫn không thấy → `launch(package)` + chờ 2 s → kiểm tra lại → `OperationError("Không thấy nút mic '<open_label>'")`.
  2. Bấm `open_label`; chờ (poll ≤ `listen_timeout_s`) thấy `stop_label`; ghi lại `before = nodes`.
  3. `sleep(pre_delay_s)`; `player.play(wav)` qua `asyncio.to_thread`; `sleep(post_delay_s)`.
  4. Dump; nếu còn `stop_label` thì bấm; **không có thì không bấm** (Review #1).
  5. Poll ≤ `result_timeout_s` tới khi `new_bubble(before, nodes)` khác None → text. Hết thời gian → `text=None` (app không nhận được câu nào; **không phải** lỗi thao tác — tính là Sai với text rỗng).
  6. Bấm `close_label` nếu có. Mỗi bước thêm 1 dòng vào `log`.
- [ ] Test: luồng chuẩn trả `"chỉnh nhiệt độ ghế lái lên 24 độ"` và FakeApp nhận các tap mở/dừng/đóng đúng thứ tự; **Review #1** `auto_stop=True` → không có tap vào vị trí nút giữa lần hai; `transcript=None` → `text is None`, `error is None`; **Review #4** bắt đầu ở sheet-idle → tự đóng rồi chạy; bắt đầu ở background → `launch` được gọi; không bao giờ thấy nút mic → `OperationError`; sheet không mở trong `listen_timeout_s` → `OperationError`. Dùng `sleep` giả để test chạy nhanh. → FAIL → implement → PASS → commit `feat(block2): drive one utterance on the app`.

### Task 5: Lưu kết quả Khối 2

**Files:** Modify `store/db.py`; Test `backend/tests/store/test_app_runs.py`.

**Interfaces — Produces:**
- `AppStatus(StrEnum)`: `PENDING="Chờ"`, `PASSED="Đúng"`, `FAILED="Sai"`, `OP_ERROR="Lỗi thao tác"`
- Bảng `app_runs(id, audio_set_id, serial, device_model, profile_name, app_version, created_at)`; `app_results(id, app_run_id, item_id, status, app_text, wer, cer, ops_json, error, log, updated_at)`
- `create_app_run(audio_set_id, serial, device_model, profile_name, app_version) -> int` — một dòng `Chờ` cho mỗi item **Đạt** của bộ audio
- `list_app_runs(audio_set_id) -> list[dict]` (kèm `summary`); `get_app_run(id)`; `app_results(run_id) -> list[dict]` (join item: sheet, tc_id, turn, feature, priority, text_raw, text_tts, audio_path; `ops` đã parse)
- `pending_for_block2(run_id)` — status ∈ {Chờ, Lỗi thao tác}
- `record_app_result(result_id, status, app_text, result: CompareResult | None, error, log)`; `app_summary(run_id) -> dict[str,int]`
- [ ] Test: set 3 item (2 Đạt, 1 Audio không đạt) → run có 2 kết quả Chờ; ghi Đúng/Lỗi thao tác → summary đúng; `pending_for_block2` trả lại dòng Lỗi thao tác; hai run trên cùng bộ audio độc lập. → FAIL → implement → PASS → commit `feat(store): app runs and results`.

### Task 6: Job Khối 2

**Files:** Modify `pipeline/block2.py`, `jobs/runner.py` (thêm kind `"log"`); Test `backend/tests/pipeline/test_block2_run.py`.

**Interfaces — Produces:** `async def run_block2(store, app_run_id, dev: DeviceDriver, profile, player, settings, emit, cancel, run_one=run_one) -> None` — mỗi kết quả chờ: `run_one` → nếu `text is None` thì `Sai` với text "" (`compare(text_tts, "")`); có text → `compare(text_tts, text, settings.wer_threshold)` → `Đúng`/`Sai`; `OperationError` → `Lỗi thao tác` + error; emit `"log"` cho từng dòng log và `"item"` với dòng kết quả; **5** lỗi thao tác liên tiếp → `error` "Dừng sau 5 lỗi thao tác liên tiếp: …" (Review #5); hủy giữa các câu.
- [ ] Test (run_one giả): Đúng/Sai/text None/Lỗi thao tác ghi đúng; 5 lỗi liên tiếp dừng job, 2 câu sau vẫn Chờ; chạy lại chỉ xử lý Chờ + Lỗi thao tác; hủy sau câu đầu. → FAIL → implement → PASS → commit `feat(block2): app test job`.

### Task 7: API Khối 2

**Files:** Modify `api/routes.py`, `api/app.py` (ctx.player, ctx.profiles_dir); Test `backend/tests/api/test_block2_routes.py` (Adb/driver/player giả qua `create_app(..., device_factory=, player=)`).

**Interfaces — Produces:** `GET /api/profiles`; `PUT /api/profiles/{name}`; `GET /api/device/{serial}/node-at?x=&y=` → node nhỏ nhất chứa điểm `{label, cls, bounds}`; `POST /api/audio-sets/{id}/app-runs {serial, profile}` → `{id, job_id}` (409 khi có job; 422 nếu bộ audio không có câu Đạt); `POST /api/app-runs/{id}/resume` → `{job_id}`; `GET /api/audio-sets/{id}/app-runs`; `GET /api/app-runs/{id}/results`. `Adb.app_version(serial, package)` (parse `versionName=` từ `dumpsys package`).
- [ ] Test: tạo run + chạy với FakeApp tới hết → results có Đúng; 409 khi đang chạy job khác; node-at trả label nút mic tại (360,1471) từ fixture. → FAIL → implement → PASS → commit `feat(api): block2 endpoints`.

### Task 8: Báo cáo Khối 2

**Files:** Modify `report/excel.py`, route report nhận `app_run_id`; Test `backend/tests/report/test_excel_block2.py`.

**Interfaces — Produces:** `build_block1_report(..., app_run_id=N)` thêm: Tổng quan mục "KHỐI 2 – APP" (thiết bị, hồ sơ, phiên bản app, số câu test, Đúng, Sai, Lỗi thao tác, **Tỉ lệ đúng của app** = Đúng/(Đúng+Sai), WER/CER trung bình) + bảng theo sheet; sheet **"Khối 2 – App"** (Sheet, TC_ID, Lượt, Cụm tính năng, Ưu tiên, Câu gốc, Câu đọc, Text app, WER, CER, Từ sai, Kết quả); sheet **"Lỗi thao tác"** (câu, lỗi, log). `POST /api/audio-sets/{id}/report?app_run_id=`.
- [ ] Test: run 4 kết quả (2 Đúng, 1 Sai, 1 Lỗi thao tác) → tỉ lệ đúng = 2/3; đủ sheet; không truyền app_run_id → không có sheet Khối 2. → FAIL → implement → PASS → commit `feat(report): block2 sheets`.

### Task 9: Giao diện Khối 2

**Files:** Create `frontend/src/components/AppRunPanel.tsx`, `frontend/src/devicePoint.ts`; Modify `App.tsx`, `Sidebar.tsx` (bật mục "Test app"), `ItemTable.tsx` (cột Text app / WER app / KQ app khi chọn lần test), `DevicePanel.tsx` (log thao tác từ WS `"log"`, chế độ ghim), `api.ts`; Test `frontend/src/devicePoint.test.ts`, `AppRunPanel.test.tsx`.

- `toDevicePoint(clickX, clickY, imgW, imgH, devW, devH) -> {x, y}` (làm tròn, kẹp trong màn hình).
- AppRunPanel: chọn thiết bị (từ `/api/device`), hồ sơ, nút **Chạy trên app** (tạo run) / **Chạy tiếp**, danh sách lần test của bộ audio, chọn lần test để xem kết quả; nhắc "Đặt âm lượng loa máy tính ~70%, điện thoại cách loa 20–40 cm".
- Ghim: bật "Ghim nút" → click lên ảnh màn hình → gọi node-at → hiện label → chọn vai trò (Mở mic / Dừng / Đóng) → lưu hồ sơ.
- [ ] Test: `toDevicePoint(180, 412, 360, 825, 720, 1650)` = `{x:360,y:824}`; điểm ngoài ảnh bị kẹp; AppRunPanel vô hiệu nút chạy khi chưa có thiết bị. → FAIL → implement → PASS → `npm run build` → commit `feat(ui): block2 app run panel, pin mode, device log`.

### Task 10: Test trên trình duyệt + README

**Files:** Create `tests/e2e/browser_e2e.py`; Modify `README.md`.

- Playwright (`uv add --dev playwright`), `chromium.launch(channel="msedge")` (Edge có sẵn, không tải trình duyệt).
- Kịch bản (server thật + điện thoại thật): mở `http://127.0.0.1:8765` → chụp màn hình → nạp `public/DieuKhienXe_Pre.xlsx`, chọn 1 sheet → tạo bộ audio → tắt bớt còn 5 câu → Sinh audio + Verify → chờ xong → mục Test app → chọn thiết bị → Chạy trên app → chờ xong → Xuất Excel; mỗi bước lưu ảnh `data/e2e/*.png` để xem lại.
- [ ] Chạy script, xem ảnh chụp, sửa lỗi phát hiện (mỗi lỗi kèm test ở task tương ứng). README: mục Khối 2 (bật USB debugging, adb trong `vendor/platform-tools`, âm lượng, hồ sơ app, ghim nút). Commit `test(e2e): browser run of block1+block2; docs`.
