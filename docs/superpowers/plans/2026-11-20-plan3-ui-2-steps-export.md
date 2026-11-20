# UI 2 bước, chọn case, theme, xuất phiên — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Block 1 into Generate / Verify / Regenerate on selected cases, reorganize the UI into Step 1 / Step 2 with a light/dark theme, capture screenshots on failures in Block 2, and export a session as a testcase-form Excel plus a per-testcase zip.

**Architecture:** Backend keeps one job at a time (`jobs/runner.py`); the three Block 1 jobs and the Block 2 job take an optional `item_ids` list. Screenshots are written during the run to `data/app_runs/<run_id>/<result_id>.png`; the form Excel and the zip are built on demand from SQLite. Frontend keeps the single-page React app; `App.tsx` switches between two steps, selection lives in the UI.

**Tech Stack:** Python 3.12 · FastAPI · SQLite · openpyxl · zipfile · React 18 + TypeScript · Vite · vitest · @tanstack/react-virtual.

**Spec:** `docs/superpowers/specs/2026-11-20-ui-2-buoc-va-xuat-phien-design.md`

## Global Constraints

- All user-visible copy is Vietnamese, matching the existing tone (e.g. "Sinh audio", "Verify", "Sinh lại", "Xuất zip phiên").
- Item statuses (`ItemStatus`) and app statuses (`AppStatus`) keep their current Vietnamese values; no new status values.
- Verify never regenerates audio. `Settings.max_regen` stays in `config.py`/`SettingsIn` (old settings files and the settings round-trip keep working) but is no longer read by any pipeline and is hidden from the Settings UI.
- No item is selected = "all eligible" for every action. API parameter name everywhere: `item_ids: list[int] | None` (None = all).
- Form header colors: A–O `FFDDEBF7`, P–W and Y–AB `FFFFF2CC`, X and AC–AJ `FFD9D9D9`.
- Form column values: S = `Pass` / `Fail` / empty; X = `Fail` only when the app result is `Sai`, otherwise empty.
- Zip folder prefixes, by worst turn: `FAIL_` (Sai) > `LOI_` (Lỗi thao tác) > `CHUA_` (Chờ) > `PASS_` (Đúng).
- Text files in the zip are UTF-8 with BOM (`encoding="utf-8-sig"`).
- WAV and PNG entries use `ZIP_STORED`; others `ZIP_DEFLATED`. The zip is written to a file on disk, never assembled in memory.
- Frontend dependency versions stay as pinned in `frontend/package.json`; no new dependencies (backend or frontend).
- Commit after each task; messages in the existing style (`feat(block1): …`, `feat(ui): …`), ending with the attribution line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

Test commands: backend `uv run pytest backend/tests -q` (from repo root); frontend `npm test` and `npm run build` (from `frontend/`).

## Review Focus

1. **Selected item has no audio when Verify runs** (it was edited after selection, which resets it to "Chờ"): it must be left untouched, not marked "Lỗi". → Task 2 `test_verify_selected_without_audio_is_untouched`.
2. **Real sheet names end with a space** (`'Unlock Charging Port via Voice '`) and TC_IDs may contain `/` or `:`: zip folders must still be valid Windows paths, and the Excel Z column must point at exactly the folder written. → Task 5 `test_case_folders_sanitize_trailing_space_and_slash`, Task 6 `test_zip_paths_match_form_evidence`.
3. **Same TC_ID across turns vs. a genuinely duplicated TC_ID:** turns 1, 2 share one folder; a second row with the same TC_ID *and* same turn goes to `<TC>_2`. → Task 5 `test_case_folders_turns_share_folder_duplicates_split`.
4. **`screencap` fails on the phone** (locked device, adb hiccup): the sentence result must still be recorded with its status; only the screenshot is missing. → Task 3 `test_screencap_failure_keeps_result`.
5. **Audio set imported before this change** (no `form_json`): form export must still produce a row with the columns the DB has (A, B, E, H, I, L, M, N) and leave the rest blank. → Task 5 `test_form_export_without_form_json`.

---

### Task 1: Store — selection queries, full form row, screenshot column

**Files:**
- Modify: `backend/tts_stt_tool/models.py` (InputItem)
- Modify: `backend/tts_stt_tool/input/testcase_form.py` (`_iter_items` reads 36 columns)
- Modify: `backend/tts_stt_tool/store/db.py`
- Test: `backend/tests/store/test_db.py`, `backend/tests/store/test_app_runs.py`, `backend/tests/input/test_testcase_form.py`

**Interfaces:**
- Produces:
  - `InputItem.form: list[str] = field(default_factory=list)` — texts of columns A..AJ (36 entries, `cell_text`), empty for generic/csv input.
  - `items.form_json TEXT` column (migration via `ALTER TABLE` like `text_tts_snap`); `_item_row` drops `form_json` so the API payload does not grow.
  - `Store.form_cells(audio_set_id: int) -> dict[int, list[str]]` (item id → 36 cells; items without form omitted).
  - `Store.items_for_generate(audio_set_id: int, item_ids: list[int] | None) -> list[dict]` — enabled, `text_tts` not null, `audio_path IS NULL`, status in (Chờ, Lỗi).
  - `Store.items_for_regenerate(audio_set_id: int, item_ids: list[int] | None) -> list[dict]` — enabled, `text_tts` not null, `audio_path` not null; when `item_ids is None` additionally status = "Audio không đạt".
  - `Store.items_for_verify(audio_set_id: int, item_ids: list[int] | None) -> list[dict]` — enabled, `text_tts` not null, `audio_path` not null; when `item_ids is None` additionally status in (Đã sinh audio, Lỗi).
  - All three: ordered by id; `item_ids` restricted to the given set id.
  - `record_generated(...)` now also clears `ref_text, wer, cer, ops_json`.
  - `create_app_run(audio_set_id, serial, device_model, profile_name, app_version, item_ids: list[int] | None = None) -> int` — restricts the inserted results to those ids (still only Đạt + enabled + audio).
  - `app_results.screenshot_path TEXT` (migration); `record_app_result(..., log: str, screenshot_path: str | None = None)`.
  - `_RESULT_SELECT` additionally selects `i.source_row, i.speaker, i.region, i.expected`.
  - Remove `pending_for_block1` and `_BLOCK1_TODO` (Task 2 removes its only caller).

- [ ] **Step 1: Write the failing tests**

```python
# test_testcase_form.py
def test_form_cells_are_kept(mini_form):
    items = read_testcase_items(mini_form, [FORM_SHEET])
    assert len(items[0].form) == 36
    assert items[0].form[0] == "TC-SYN-001" and items[0].form[12] == "Đồng bộ nhiệt độ tất cả các vùng"
    assert items[0].form[35] == ""

# test_db.py
def test_selection_queries(store_with_items):  # 3 items: A no audio, B generated, C audio failed
    s, set_id, (a, b, c) = store_with_items
    assert [i["id"] for i in s.items_for_generate(set_id, None)] == [a]
    assert [i["id"] for i in s.items_for_generate(set_id, [b, c])] == []
    assert [i["id"] for i in s.items_for_verify(set_id, None)] == [b]
    assert [i["id"] for i in s.items_for_verify(set_id, [a, c])] == [c]
    assert [i["id"] for i in s.items_for_regenerate(set_id, None)] == [c]
    assert [i["id"] for i in s.items_for_regenerate(set_id, [b])] == [b]

def test_record_generated_clears_verify(store_with_items):
    s, set_id, (_, _, c) = store_with_items
    s.record_generated(c, "x.wav", 2)
    it = s.get_item(c)
    assert it["status"] == "Đã sinh audio" and it["ref_text"] is None and it["wer"] is None and it["ops"] == []

def test_form_cells_and_payload(store):  # create a set from items with form=[...36]
    ...
    assert store.form_cells(set_id)[item_id][12] == "Bật ionizer"
    assert "form_json" not in store.get_item(item_id)

# test_app_runs.py
def test_create_app_run_with_item_ids(passed_set):
    s, set_id, ids = passed_set  # 3 Đạt items
    run = s.create_app_run(set_id, "SER", None, "p", None, item_ids=[ids[1]])
    assert [r["item_id"] for r in s.app_results(run)] == [ids[1]]

def test_screenshot_path_roundtrip(passed_set):
    ...
    s.record_app_result(rid, AppStatus.FAILED, "x", None, None, "log", screenshot_path="C:/shots/1.png")
    assert s.get_app_result(rid)["screenshot_path"] == "C:/shots/1.png"
```

Build the `store_with_items` / `passed_set` fixtures in the test files with `record_generated` / `record_verify` calls (pattern already used in `test_app_runs.py`). Also add a migration test: open a DB file created with the old schema (create tables without `form_json` / `screenshot_path`, then `Store(path)`) and assert both columns exist.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/store backend/tests/input -q`
Expected: FAIL (`AttributeError: 'Store' object has no attribute 'items_for_generate'`, `InputItem` has no `form`).

- [ ] **Step 3: Implement the interfaces above** in `models.py`, `testcase_form.py` (`max_col=36`, keep `_IDX` lookups), `store/db.py`.

- [ ] **Step 4: Run the whole backend suite**

Run: `uv run pytest backend/tests -q`
Expected: new tests PASS; only tests that call `run_block1` / `pending_for_block1` / `/block1` fail (fixed in Tasks 2 and 4).

- [ ] **Step 5: Commit** — `feat(store): selection queries, full form row, screenshot path`

---

### Task 2: Block 1 split — generate, verify, regenerate

**Files:**
- Modify: `backend/tts_stt_tool/pipeline/block1.py` (replace `run_block1` / `_verify_item`)
- Test: `backend/tests/pipeline/test_block1.py` (rewrite the `run` helper and tests)

**Interfaces:**
- Consumes: Task 1 `items_for_generate / items_for_regenerate / items_for_verify`, `record_generated`, `record_verify`, `record_error`.
- Produces:
  - `async def run_generate(store, audio_set_id: int, tts: TtsEngine, cache: AudioCache, settings: Settings, emit: Emit, cancel: asyncio.Event, *, item_ids: list[int] | None = None, regenerate: bool = False) -> None`
    - attempt index = `item["attempts"]` when `regenerate`, else `0`; stores `attempts = attempt + 1`.
    - Voice: audio set's voice, else `settings.voice`.
    - Per-item TTS exception → `record_error`, continue. Uses the existing `_audio_for` (cache by text+voice+attempt+engine version).
  - `async def run_verify(store, audio_set_id: int, stt: SttEngine, settings: Settings, emit: Emit, cancel: asyncio.Event, *, item_ids: list[int] | None = None) -> None`
    - Reads WAV from `item["audio_path"]` (`sf.read(..., dtype="float32")` in a thread); missing file → `record_error("Không tìm thấy file audio — bấm Sinh lại")`.
    - `compare(text_tts, hyp, settings.wer_threshold)` → `PASSED` or `AUDIO_FAILED`. No regeneration.
    - Stops with an `error` event after `MAX_CONSECUTIVE_ERRORS = 3` consecutive `SttError`s (existing message).
  - Both: build the queue once, re-read each item before processing and skip it if it no longer qualifies (edited/disabled since), write with the `text_tts` guard, emit `item` / `progress` / `cancelled` / `done` exactly as `run_block1` did.

- [ ] **Step 1: Write the failing tests** (reuse `FakeTts`, `ScriptedStt`, `make_set`)

```python
async def test_generate_only_items_without_audio(env): # 2 items; generate; generate again
    assert [a for _, a in tts.calls] == [0, 0]        # second run synthesizes nothing
    assert all(i["status"] == "Đã sinh audio" and i["attempts"] == 1 for i in store.get_items(set_id))

async def test_generate_selected_only(env):            # item_ids=[second]
    assert [i["status"] for i in store.get_items(set_id)] == ["Chờ", "Đã sinh audio"]

async def test_verify_fail_does_not_regenerate(env):   # STT answers wrong text
    calls_before = len(tts.calls); await verify(...)
    assert len(tts.calls) == calls_before
    it = store.get_items(set_id)[0]
    assert it["status"] == "Audio không đạt" and it["attempts"] == 1 and it["wer"] > 0

async def test_verify_all_only_generated_selected_reverifies(env):
    # item 1 Đạt already, item 2 Đã sinh audio: verify(None) touches only item 2;
    # verify([item1]) re-verifies item 1 (STT called once more)

async def test_regenerate_uses_next_attempt_and_clears_verify(env):
    # item verified as "Audio không đạt" with attempts=1; regenerate(None)
    assert tts.calls[-1][1] == 1
    it = store.get_item(item_id)
    assert it["status"] == "Đã sinh audio" and it["attempts"] == 2 and it["ref_text"] is None

async def test_verify_selected_without_audio_is_untouched(env):   # Review Focus 1
    # item edited (set_item_text) after generation -> Chờ, no audio; verify([item_id])
    assert store.get_item(item_id)["status"] == "Chờ" and store.get_item(item_id)["error"] is None

async def test_verify_stops_after_three_stt_errors(env):  # 4 items, STT raises SttError
    assert events[-1].kind == "error" and sum(i["status"] == "Lỗi" for i in store.get_items(set_id)) == 3

async def test_cancel_generate(env):  # cancel set before second item -> last event "cancelled", second still Chờ
```

Delete the old regen-loop tests (`max_regen` behaviour) and keep the edit-during-processing (`_Superseded`) test adapted to `run_verify`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/pipeline/test_block1.py -q`
Expected: FAIL with `ImportError: cannot import name 'run_generate'`.

- [ ] **Step 3: Implement `run_generate` and `run_verify`; delete `run_block1` and `_verify_item`.**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/pipeline/test_block1.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `feat(block1): separate generate / verify / regenerate jobs, no auto regen`

---

### Task 3: Block 2 — screenshot on wrong text and on operation errors

**Files:**
- Modify: `backend/tts_stt_tool/pipeline/block2.py`
- Modify: `backend/tests/pipeline/fake_app.py` (add `screencap`)
- Test: `backend/tests/pipeline/test_block2_one.py`, `backend/tests/pipeline/test_block2_run.py`

**Interfaces:**
- Consumes: Task 1 `record_app_result(..., screenshot_path=...)`.
- Produces:
  - `DeviceDriver.screencap(self) -> Awaitable[bytes]`; `AdbDriver.screencap` → `self.adb.screencap(self.serial)`.
  - `AppCapture.screenshot: bytes | None = None`.
  - `run_one(dev, p, wav, player, sleep=asyncio.sleep, prev_bubbles=None, is_correct: Callable[[str], bool] | None = None) -> AppCapture` — after the result poll and **before** the closing Back: if `is_correct` is given and `is_correct(text or "")` is False, capture. A capture failure appends `"Không chụp được màn hình: <err>"` to the log and leaves `screenshot=None`.
  - `run_block2(store, app_run_id, dev, profile, player, settings, emit, cancel, run_one=run_one, shots_dir: Path | None = None)` — passes `is_correct=lambda heard: compare(row["text_tts"], heard, settings.wer_threshold).correct`; on any exception from `run_one` captures the screen in the `except` branch (before the next item's recovery); writes bytes to `shots_dir / f"{row['id']}.png"` (mkdir parents) and stores the absolute path. `shots_dir=None` → no capture at all.
  - `FakeApp.screencap()` returns `b"\x89PNG-fake"` and records `self.state` at capture time in `self.shots: list[str]`; `FakeApp.screencap_error: Exception | None = None` makes it raise.

- [ ] **Step 1: Write the failing tests**

```python
# test_block2_one.py
async def test_wrong_text_screenshot_taken_while_sheet_open():
    app = FakeApp(transcript="sai hoàn toàn")
    cap = await run_one(app, PROFILE, WAV, app, no_sleep, is_correct=lambda t: False)
    assert cap.screenshot == b"\x89PNG-fake" and app.shots == ["sheet"]   # before Back
    assert app.state == "home"

async def test_correct_text_no_screenshot():
    app = FakeApp()
    cap = await run_one(app, PROFILE, WAV, app, no_sleep, is_correct=lambda t: True)
    assert cap.screenshot is None and app.shots == []

async def test_screencap_failure_keeps_result():                          # Review Focus 4
    app = FakeApp(transcript="sai"); app.screencap_error = RuntimeError("adb")
    cap = await run_one(app, PROFILE, WAV, app, no_sleep, is_correct=lambda t: False)
    assert cap.text == "sai" and cap.screenshot is None
    assert any("Không chụp được màn hình" in line for line in cap.log)

# test_block2_run.py
async def test_failed_and_op_error_screenshots_saved(env, tmp_path):
    # scripted answers: correct, wrong, OperationError; shots_dir=tmp_path/"shots"
    rows = by_text(store, run_id)
    assert rows[<correct>]["screenshot_path"] is None
    assert Path(rows[<wrong>]["screenshot_path"]).read_bytes().startswith(b"\x89PNG")
    assert Path(rows[<op error>]["screenshot_path"]).is_file()
```

Use whatever state name `FakeApp` uses for the open sheet (read `fake_app.py`); update the scripted `fake` in `test_block2_run.py` to accept `**kwargs` and return `AppCapture(..., screenshot=b"\x89PNG-fake")` when its answer is wrong.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/pipeline/test_block2_one.py backend/tests/pipeline/test_block2_run.py -q`
Expected: FAIL (`unexpected keyword argument 'is_correct'`).

- [ ] **Step 3: Implement the interfaces above.**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests/pipeline -q`
Expected: PASS (all existing block 2 tests still pass).

- [ ] **Step 5: Commit** — `feat(block2): screenshot on wrong text / operation error before closing the sheet`

---

### Task 4: API — Block 1 jobs with selection, app runs with selection

**Files:**
- Modify: `backend/tts_stt_tool/api/routes.py`, `backend/tts_stt_tool/api/app.py`
- Test: `backend/tests/api/test_routes.py`, `backend/tests/api/test_block2_routes.py`

**Interfaces:**
- Consumes: Task 2 `run_generate`, `run_verify`; Task 1 selection queries, `create_app_run(item_ids=)`; Task 3 `run_block2(shots_dir=)`.
- Produces:
  - `class ItemIdsIn(BaseModel): item_ids: list[int] | None = None`
  - `POST /api/audio-sets/{set_id}/generate`, `/verify`, `/regenerate` — body `ItemIdsIn` (optional) → `{"job_id": str}`; 404 unknown set; 409 job busy; **422** when the matching `items_for_*` query is empty, with detail `"Không có câu nào cần sinh audio"` / `"Không có câu nào có audio để verify"` / `"Không có câu nào để sinh lại"`. Job names: `"Sinh audio – bộ {id}"`, `"Verify – bộ {id}"`, `"Sinh lại – bộ {id}"`. Only `/verify` calls `ctx.wyoming.ensure_running()`.
  - `AppRunIn.item_ids: list[int] | None = None` passed to `create_app_run`; 422 `"Không có câu Đạt nào trong các case đã chọn"` when the new run has zero results (delete that run).
  - `AppContext.run_dir(run_id: int) -> Path` = `settings.data_dir / "app_runs" / str(run_id)`; `_start_block2` passes `shots_dir=ctx.run_dir(run_id)`.
  - Remove `POST /audio-sets/{set_id}/block1`.
  - Test helpers: in `test_routes.py` add `verify_all(client, set_id)` = POST generate, `wait_job_end`, POST verify, `wait_job_end`; use it everywhere `/block1` was posted (including `verified_set` in `test_block2_routes.py`).

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_verify_regenerate_flow(client, tmp_path):
    set_id = create_set(client, tmp_path)
    assert client.post(f"/api/audio-sets/{set_id}/verify").status_code == 422      # nothing generated yet
    ids = [i["id"] for i in client.get(f"/api/audio-sets/{set_id}/items").json() if i["enabled"]]
    assert client.post(f"/api/audio-sets/{set_id}/generate", json={"item_ids": ids[:1]}).status_code == 200
    wait_job_end(client)
    st = {i["id"]: i["status"] for i in client.get(f"/api/audio-sets/{set_id}/items").json()}
    assert st[ids[0]] == "Đã sinh audio" and st[ids[1]] == "Chờ"
    client.post(f"/api/audio-sets/{set_id}/verify"); wait_job_end(client)
    assert {i["id"]: i["status"] for i in client.get(f"/api/audio-sets/{set_id}/items").json()}[ids[0]] == "Đạt"
    r = client.post(f"/api/audio-sets/{set_id}/regenerate", json={"item_ids": [ids[0]]})
    assert r.status_code == 200

def test_block1_endpoint_removed(client):
    assert client.post("/api/audio-sets/1/block1").status_code in (404, 405)

def test_app_run_selected_items_and_shots_dir(ctx):
    # verified set; POST app-runs with item_ids=[one id] -> results list has exactly that item
    # POST with item_ids of a non-Đạt item -> 422
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/api -q`
Expected: FAIL (404 on `/generate`).

- [ ] **Step 3: Implement the endpoints and helper changes.**

- [ ] **Step 4: Run the whole backend suite**

Run: `uv run pytest backend/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit** — `feat(api): generate/verify/regenerate jobs and app runs on selected items`

---

### Task 5: Form Excel export (hướng B)

**Files:**
- Create: `backend/tts_stt_tool/report/layout.py` (folder naming shared with the zip)
- Create: `backend/tts_stt_tool/report/form_export.py`
- Modify: `backend/tts_stt_tool/api/routes.py` (endpoint)
- Test: `backend/tests/report/test_layout.py`, `backend/tests/report/test_form_export.py`, `backend/tests/api/test_block2_routes.py`

**Interfaces:**
- Consumes: Task 1 `form_cells`, `app_results` (with `source_row`, `screenshot_path`), `get_app_run`, `get_audio_set`; `report.excel._app_overview`, `report.excel.format_ops`.
- Produces (`layout.py`):
  - `safe_component(name: str) -> str` — replace `<>:"/\|?*` and control chars with `_`, strip trailing spaces and dots, prefix `_` for reserved names (CON, PRN, AUX, NUL, COM1–9, LPT1–9), empty → `_`.
  - `DEFAULT_SHEET = "Dữ liệu"` (sets without sheet names).
  - `case_folders(results: list[dict]) -> dict[int, str]` — result id → `"<safe sheet>/<PREFIX><safe tc_id>[_2…]"` (POSIX separators, no trailing slash). Group by (sheet, tc_id) in `source_row` order; a row goes into the first copy (`TC`, `TC_2`, `TC_3`…) whose turns do not yet contain its turn. Prefix from the worst status in the final group (Global Constraints). Empty tc_id → `dong<source_row>`.
  - `turn_prefix(turn: str) -> str` — first integer in `turn` → `f"luot{n}_"`; no integer → `"luot1_"`.
- Produces (`form_export.py`):
  - `FORM_HEADERS: list[str]` — the 36 row-4 headers, verbatim from the sample (`TC_ID`, `Cụm tính năng`, … `Langfuse: cảnh báo`).
  - `FORM_GROUPS = [("A","I","THÔNG TIN CHUNG"), ("J","M","ĐẦU VÀO"), ("N","O","MONG ĐỢI"), ("P","Q","THỰC TẾ"), ("R","X","ĐÁNH GIÁ THEO TẦNG"), ("Y","AD","THEO DÕI"), ("AE","AJ","LANGFUSE (tool tự điền sau khi 🔄 Đồng bộ Langfuse)")]` — merged on row 3.
  - `form_values(result: dict, run: dict, folder: str, original_note: str) -> dict[str, str]` — column letter → value for P, S, X, Z, AA, AB:
    - P: Đúng/Sai → `app_text`, or `"(app không trả câu)"` if empty; Lỗi thao tác → `f"Lỗi thao tác: {error}"`; Chờ → `""`.
    - S: `"Pass"` / `"Fail"` / `""`. X: `"Fail"` only for Sai.
    - Z: `folder + "/"`.
    - AA: `f"Phiên #{run['id']} · {run['device_model'] or run['serial']} · {run['profile_name']}"` + `f" v{app_version}"` if set + `f" · {created_at[:16].replace('T', ' ')}"`.
    - AB: `original_note`, then on a new line (only for Đúng/Sai) `f"WER {wer*100:.0f}% · CER {cer*100:.0f}%"` + `f" · sai: {format_ops(ops)}"` if any non-equal op + `f" · câu đã đọc: {text_tts}"` if `text_tts != text_raw`.
  - `build_form_report(store: Store, run_id: int, out_path: Path) -> Path` — first sheet `"Tổng hợp phiên"` (audio set name + source file, then `_app_overview`); then one sheet per source sheet in `audio_set["sheets"]` order (only sheets with results; `DEFAULT_SHEET` when empty) with row 1 title `f"{set name} · Phiên #{run_id} — kết quả test ASR tự động"` (merged A1:AJ1), row 2 the color legend copied from the form (merged A2:AJ2), row 3 groups, row 4 headers filled per Global Constraints, data from row 5 in `source_row` order; base cells from `form_cells` or, without form, A tc_id, B feature, E priority, H region, I turn, L speaker, M text_raw, N expected; then `form_values` overrides. Freeze panes `A5`, auto-filter `A4:AJ{last}`, widths A 13, C 28, D 42, J 44, K 50, M 38, N 50, P 38, Z 29, AB 40, others 13. Wrap text on M, N, P, AB.
  - `POST /api/app-runs/{run_id}/form-report` → `FileResponse` xlsx named `f"KetQua_{safe set name}_Phien{run_id}.xlsx"` in `ctx.reports`.

- [ ] **Step 1: Write the failing tests**

```python
# test_layout.py
def test_case_folders_turns_share_folder_duplicates_split():          # Review Focus 3
    rs = [r(1, "S", "TC1", "1", "Đúng", 5), r(2, "S", "TC1", "2", "Sai", 6), r(3, "S", "TC1", "1", "Đúng", 9)]
    assert case_folders(rs) == {1: "S/FAIL_TC1", 2: "S/FAIL_TC1", 3: "S/PASS_TC1_2"}

def test_case_folders_sanitize_trailing_space_and_slash():            # Review Focus 2
    rs = [r(1, "Unlock Charging Port via Voice ", "TC/01:a", "1", "Lỗi thao tác", 5)]
    assert case_folders(rs) == {1: "Unlock Charging Port via Voice/LOI_TC_01_a"}

def test_prefix_precedence_and_pending():
    # (Đúng, Chờ) -> CHUA_ ; (Lỗi thao tác, Sai) -> FAIL_ ; empty sheet -> "Dữ liệu/..."

def test_turn_prefix():
    assert [turn_prefix(t) for t in ("2", "Bước 3", "", "1.0")] == ["luot2_", "luot3_", "luot1_", "luot1_"]

# test_form_export.py
def test_form_values_wrong_text():
    v = form_values(res(status="Sai", app_text="mở cửa số", wer=0.25, cer=0.08,
                        ops=[{"op": "sub", "ref": "sổ", "hyp": "số"}], text_tts="mở cửa sổ", text_raw="Hey Vita, mở cửa sổ"),
                    RUN, "S/FAIL_TC1", "ghi chú gốc")
    assert v["P"] == "mở cửa số" and v["S"] == "Fail" and v["X"] == "Fail" and v["Z"] == "S/FAIL_TC1/"
    assert v["AB"] == "ghi chú gốc\nWER 25% · CER 8% · sai: sổ→số · câu đã đọc: mở cửa sổ"

def test_form_values_pass_and_op_error():
    assert form_values(res(status="Đúng", app_text="", ...), RUN, "f", "")["P"] == "(app không trả câu)"
    v = form_values(res(status="Lỗi thao tác", error="Mic không bật"), RUN, "f", "")
    assert v["P"] == "Lỗi thao tác: Mic không bật" and v["S"] == "" and v["X"] == ""

def test_build_form_report_layout(tmp_path, run_with_results):        # set from mini_form, 2 results
    wb = openpyxl.load_workbook(build_form_report(store, run_id, tmp_path / "f.xlsx"))
    assert wb.sheetnames == ["Tổng hợp phiên", FORM_SHEET]
    ws = wb[FORM_SHEET]
    assert [ws.cell(4, c).value for c in range(1, 37)] == FORM_HEADERS
    assert ws["P4"].fill.fgColor.rgb == "FFFFF2CC" and ws["X4"].fill.fgColor.rgb == "FFD9D9D9"
    assert ws["A5"].value == "TC-SYN-001" and ws["C5"].value == "UC" and ws["S5"].value in ("Pass", "Fail")
    assert ws.freeze_panes == "A5"

def test_form_export_without_form_json(tmp_path, ...):                # Review Focus 5
    # set created from InputItems with form=[] -> row 5 has A, M filled, C empty, no exception
```

Add an API test: `POST /api/app-runs/{id}/form-report` returns 200 with the xlsx content type; 404 for an unknown run.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/report -q`
Expected: FAIL (`ModuleNotFoundError: tts_stt_tool.report.layout`).

- [ ] **Step 3: Implement `layout.py`, `form_export.py`, the endpoint.**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `feat(report): testcase-form Excel for an app run`

---

### Task 6: Session zip export

**Files:**
- Create: `backend/tts_stt_tool/report/session_zip.py`
- Modify: `backend/tts_stt_tool/api/routes.py`
- Test: `backend/tests/report/test_session_zip.py`, `backend/tests/api/test_block2_routes.py`

**Interfaces:**
- Consumes: Task 5 `case_folders`, `turn_prefix`, `safe_component`, `build_form_report`; `report.excel.build_block1_report`, `format_ops`.
- Produces:
  - `AudioChoice = Literal["failed", "all", "selected"]`
  - `session_root_name(run: dict) -> str` — `f"Phien{id}_{YYYY-MM-DD}_{HHMM}_{safe_component(device_model or serial)}"` from `created_at`.
  - `build_session_zip(store: Store, run_id: int, settings: Settings, out_path: Path, audio: AudioChoice = "failed", selected_item_ids: set[int] | None = None, profile: dict | None = None) -> Path`
    - Root folder `session_root_name(run)` containing `KetQua_<safe set name>_Phien<id>.xlsx` (Task 5), `TongQuan.xlsx` (`build_block1_report(..., app_run_id=run_id)`), `thong_tin_phien.txt`, then per result in `case_folders`: `<turn_prefix>ketqua.txt`, `<turn_prefix>log.txt` (only if `log`), `<turn_prefix>manhinh.png` (if `screenshot_path` is an existing file), `<turn_prefix>audio.wav` per `audio`: failed → status Sai or Lỗi thao tác; all → every result; selected → `item_id in selected_item_ids`. Missing audio file → skipped, noted in `ketqua.txt` ("Không tìm thấy file audio").
    - `ketqua.txt` lines: `TC_ID`, `Sheet`, `Lượt`, `Câu gốc`, `Câu đã đọc`, `Câu app nghe`, `Kết quả`, `WER`, `CER`, `Từ sai` (`format_ops`), `Lỗi` (if any), `Thời gian` (`updated_at`) as `"Nhãn: giá trị"`.
    - `thong_tin_phien.txt`: bộ audio, file nguồn, giọng, thiết bị (model + serial), hồ sơ app (name + `json.dumps(profile, ensure_ascii=False, indent=2)` if given), phiên bản app, bắt đầu (`created_at`), kết thúc (max `updated_at`), ngưỡng WER, số câu theo trạng thái, tùy chọn audio (`"Chỉ case Sai / Lỗi thao tác"` / `"Tất cả"` / `"Các case đang chọn (N)"`).
    - Intermediate xlsx files go into a `tempfile.TemporaryDirectory()`; the zip is opened on `out_path` directly.
  - `class ExportZipIn(BaseModel): audio: Literal["failed","all","selected"] = "failed"; item_ids: list[int] | None = None` — `"selected"` with empty/None ids → 422 `"Chưa chọn case nào"`.
  - `POST /api/app-runs/{run_id}/export-zip` → `FileResponse` (`application/zip`, filename `f"{session_root_name(run)}.zip"`) built in `ctx.reports`, deleted after sending via `BackgroundTask(path.unlink, missing_ok=True)`. Profile from `get_profile(ctx.profiles_dir, run["profile_name"])` as dict, `None` if missing. Build inside `asyncio.to_thread`.

- [ ] **Step 1: Write the failing tests**

```python
def test_zip_layout_default_audio_failed(tmp_path, run_with_results):  # results: Đúng, Sai(+png), Lỗi thao tác
    z = zipfile.ZipFile(build_session_zip(store, run_id, settings, tmp_path / "s.zip"))
    names = set(z.namelist()); root = session_root_name(store.get_app_run(run_id))
    assert f"{root}/thong_tin_phien.txt" in names and f"{root}/TongQuan.xlsx" in names
    assert f"{root}/S/FAIL_TC2/luot1_manhinh.png" in names and f"{root}/S/FAIL_TC2/luot1_audio.wav" in names
    assert f"{root}/S/PASS_TC1/luot1_ketqua.txt" in names and f"{root}/S/PASS_TC1/luot1_audio.wav" not in names
    assert z.read(f"{root}/S/PASS_TC1/luot1_ketqua.txt").startswith(b"\xef\xbb\xbf")
    assert z.getinfo(f"{root}/S/FAIL_TC2/luot1_audio.wav").compress_type == zipfile.ZIP_STORED

def test_zip_audio_all_and_selected(...):
    # "all" -> 3 wav entries; "selected" with {item of TC1} -> only TC1 wav

def test_zip_paths_match_form_evidence(tmp_path, run_with_results):   # Review Focus 2
    # read KetQua xlsx from the zip: every Z value + "ketqua.txt" prefix exists as a folder in namelist()
```

API test: `POST /export-zip` with `{"audio": "selected"}` and no ids → 422; default → 200, `content-type` `application/zip`, and the file in `ctx.reports` is gone after the response.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest backend/tests/report/test_session_zip.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `session_zip.py` and the endpoint.**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `feat(report): session zip with one folder per testcase`

---

### Task 7: Theme sáng / tối

**Files:**
- Create: `frontend/src/theme.ts`, `frontend/src/theme.test.ts`, `frontend/src/components/ThemeSwitch.tsx`
- Modify: `frontend/src/main.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Produces:
  - `type ThemeMode = "system" | "light" | "dark"`; storage key `"tts-stt-theme"`.
  - `loadTheme(): ThemeMode` (invalid / throwing storage → `"system"`).
  - `applyTheme(mode: ThemeMode, root: HTMLElement = document.documentElement): void` — `"system"` removes `data-theme`, otherwise sets it; saves (ignore storage errors).
  - `nextTheme(mode: ThemeMode): ThemeMode` — system → light → dark → system.
  - `<ThemeSwitch />` — one button in the sidebar footer, label `"◐ Theo hệ thống"` / `"☀ Sáng"` / `"☾ Tối"`, click = `applyTheme(nextTheme(current))`.
  - CSS: the dark variable block applies under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` and again under `:root[data-theme="dark"] {…}`. Hard-coded colors in `styles.css` that differ between themes become variables: `.phone` border/background (`--phone-frame`, `--phone-bg`), `.dot-label.ok/.warn` → `var(--ok)` / `var(--warn)`, modal backdrop and shadows may stay. `#fff` on `.btn.primary` stays.

- [ ] **Step 1: Write the failing tests**

```ts
test("system removes the attribute, dark sets it and persists", () => {
  applyTheme("dark"); expect(document.documentElement.dataset.theme).toBe("dark");
  expect(loadTheme()).toBe("dark");
  applyTheme("system"); expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
});
test("cycle", () => { expect(["system","light","dark"].map((m) => nextTheme(m as ThemeMode))).toEqual(["light","dark","system"]); });
test("storage that throws falls back to system", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(loadTheme()).toBe("system");
});
```

- [ ] **Step 2: Run to verify they fail** — `npm test -- theme` → FAIL (module not found).
- [ ] **Step 3: Implement**; call `applyTheme(loadTheme())` in `main.tsx` before rendering.
- [ ] **Step 4: Run** — `npm test` and `npm run build` → PASS / build succeeds.
- [ ] **Step 5: Commit** — `feat(ui): light/dark theme switch`

---

### Task 8: Case selection in the table

**Files:**
- Create: `frontend/src/selection.ts`, `frontend/src/selection.test.ts`
- Modify: `frontend/src/components/ItemTable.tsx`, `frontend/src/components/ItemTable.test.tsx`, `frontend/src/styles.css` (`.row` grid)

**Interfaces:**
- Produces (`selection.ts`):
  - `interface Selection { ids: ReadonlySet<number>; anchor: number | null }`, `const emptySelection: Selection`.
  - `clickRow(sel: Selection, visibleIds: number[], index: number, shift: boolean): Selection` — no shift: toggle `visibleIds[index]`, anchor = index. Shift with an anchor: add every id between anchor and index (inclusive), anchor unchanged.
  - `toggleAllVisible(sel: Selection, visibleIds: number[]): Selection` — all visible selected → remove them; else add them all.
  - `prune(sel: Selection, allowed: ReadonlySet<number>): Selection` — drop ids not allowed (called when items reload).
- Produces (`ItemTable` props, added):
  - `selected: ReadonlySet<number>`, `isSelectable: (it: Item) => boolean`, `onRowSelect: (index: number, shift: boolean) => void`, `onToggleAll: () => void`, `onRegenerate?: (id: number) => void`.
  - Column order: `[☐ select] [#] [Sheet] [TC_ID] [Lượt] [Câu gốc] [Câu đọc] [▶] [STT/app] [WER] [CER] [Trạng thái] [actions]`. Header checkbox: checked when every selectable visible row is selected, `indeterminate` when some are. Non-selectable rows: disabled checkbox.
  - The old enabled checkbox moves to the actions column as an `icon-btn` `⏻` (title `"Bật/tắt câu này"`, class `off` when disabled, same `onPatch(id, {enabled})`, same disabled rule `!text_tts`). `⟳` (`title="Sinh lại audio"`) shows in the actions column when `onRegenerate` is given and the item has audio.

- [ ] **Step 1: Write the failing tests**

```ts
test("click toggles, shift adds range", () => {
  let s = clickRow(emptySelection, [10, 11, 12, 13], 1, false);
  s = clickRow(s, [10, 11, 12, 13], 3, true);
  expect([...s.ids].sort()).toEqual([11, 12, 13]);
  expect([...clickRow(s, [10, 11, 12, 13], 2, false).ids].sort()).toEqual([11, 13]);
});
test("toggle all visible", () => {
  const s = toggleAllVisible(emptySelection, [1, 2]); expect(s.ids.size).toBe(2);
  expect(toggleAllVisible(s, [1, 2]).ids.size).toBe(0);
});
// ItemTable.test.tsx
test("row checkbox calls onRowSelect with shift flag; ⏻ still patches enabled; ⟳ calls onRegenerate", ...)
```

- [ ] **Step 2: Run to verify they fail** — `npm test` → FAIL.
- [ ] **Step 3: Implement** (adapt existing `ItemTable.test.tsx` cases that clicked the enabled checkbox).
- [ ] **Step 4: Run** — `npm test` → PASS.
- [ ] **Step 5: Commit** — `feat(ui): select cases in the table, shift-click range`

---

### Task 9: Two-step layout and Step 1 actions

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/Sidebar.test.tsx`, `frontend/src/components/RunBar.tsx`, `frontend/src/components/SettingsPanel.tsx`, `frontend/src/jobState.ts` (comment), `frontend/src/styles.css`
- Test: `frontend/src/components/Sidebar.test.tsx`, create `frontend/src/components/RunBar.test.tsx`

**Interfaces:**
- Consumes: Task 4 endpoints; Task 7 `ThemeSwitch`; Task 8 selection.
- Produces:
  - `api.generate / api.verify / api.regenerate: (setId: number, itemIds: number[] | null) => Promise<{ job_id: string }>`; remove `startBlock1`. Extract the blob download in `downloadReport` into `downloadFile(url: string, body?: unknown, fallbackName: string): Promise<void>` for Task 10.
  - `type Section = "step1" | "step2"`; Sidebar NAV: `{ id: "step1", label: "Bước 1 — Audio", hint: "Nạp file · Sinh audio · Verify" }`, `{ id: "step2", label: "Bước 2 — Test app", hint: "Chạy trên điện thoại · Xuất phiên" }`. New prop `step2Ready: boolean` → step 2 disabled with title `"Cần ít nhất một câu Đạt ở Bước 1"`. Footer keeps the ADB / wyoming / GPU lines and Cài đặt, adds `<ThemeSwitch />`.
  - `RunBar` props: replace `onRun` with `onGenerate`, `onVerify`, `onRegenerate`; add `mode: "step1" | "step2"`, `selectedCount: number`, `onClearSelection: () => void`. Step 1 toolbar: `Nạp file`, `Sinh audio (N | tất cả)`, `Verify (N | tất cả)`, `Sinh lại (N | tất cả không đạt)`, `Dừng`, spacer, `Xuất Excel`, `CSV`, plus `"Đang chọn N case · Bỏ chọn"` when N > 0. Step 2: no action buttons (they live in `AppRunPanel`), filters + progress only.
  - `App`: state `section` default `"step1"`; two `Selection`s (step 1, step 2) reset on set change and pruned on items reload; step-1 selectable = `enabled && text_tts`; step-2 rows = items with status Đạt (as today). After a 422 from an action, show its detail as an info toast. The device column renders only in step 2: `.layout` gets class `no-device` in step 1 (`grid-template-columns: 230px minmax(0, 1fr)`). Header row-click on a set still works as today; "Dữ liệu" and "Báo cáo" nav entries are gone (Nạp file and Xuất Excel buttons cover them). Row `⟳` calls `api.regenerate(setId, [id])`.
  - `SettingsPanel`: remove the `max_regen` field (value still round-trips in the PUT body).

- [ ] **Step 1: Write the failing tests**

```ts
// Sidebar.test.tsx
test("two steps, step 2 disabled until something passed", () => {
  render(<Sidebar section="step1" step2Ready={false} ... />);
  expect(screen.getByText("Bước 1 — Audio")).toBeTruthy();
  expect(screen.getByText("Bước 2 — Test app").closest("button")!.disabled).toBe(true);
});
// RunBar.test.tsx
test("labels follow the selection", () => {
  render(<RunBar mode="step1" selectedCount={0} ... />);
  expect(screen.getByText("Sinh audio (tất cả)")).toBeTruthy();
  rerender(<RunBar mode="step1" selectedCount={12} ... />);
  expect(screen.getByText("Verify (12)")).toBeTruthy();
  expect(screen.getByText(/Đang chọn 12 case/)).toBeTruthy();
});
test("step 2 has no Block 1 buttons", () => { /* queryByText("Sinh audio (tất cả)") === null */ });
```

- [ ] **Step 2: Run to verify they fail** — `npm test` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — `npm test` and `npm run build` → PASS.
- [ ] **Step 5: Commit** — `feat(ui): two-step layout, generate/verify/regenerate on selected cases`

---

### Task 10: Step 2 — run selected cases, export form Excel and zip

**Files:**
- Create: `frontend/src/components/ExportZipDialog.tsx`, `frontend/src/components/ExportZipDialog.test.tsx`
- Modify: `frontend/src/components/AppRunPanel.tsx`, `frontend/src/components/AppRunPanel.test.tsx`, `frontend/src/api.ts`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 4 `AppRunIn.item_ids`; Task 5 `/form-report`; Task 6 `/export-zip`; Task 9 `downloadFile`, step-2 `Selection`.
- Produces:
  - `api.startAppRun(setId, serial, profile, itemIds: number[] | null)`; `api.downloadFormReport(runId: number)`; `api.downloadSessionZip(runId: number, audio: "failed" | "all" | "selected", itemIds: number[] | null)`.
  - `AppRunPanel` props added: `selectedCount: number`, `onExportForm: () => void`, `onExportZip: () => void`. Run button label `Chạy trên app (N | tất cả)`. Buttons `Xuất Excel (form)` and `Xuất zip phiên` disabled when no run is selected.
  - `ExportZipDialog` props: `{ totalCount: number; failedCount: number; selectedCount: number; onClose: () => void; onExport: (audio: "failed" | "all" | "selected") => void }`. Radios: `"Chỉ case Sai / Lỗi thao tác (N)"` (default), `"Tất cả (N) — ~X"` with `X = formatSize(totalCount * AVG_WAV_BYTES)`, `AVG_WAV_BYTES = 300_000`, `"Các case đang chọn (N)"` disabled when `selectedCount === 0`. Note under the radios: `"Ảnh chụp, kết quả và log luôn có cho mọi case."` Export button shows `"Đang tạo zip…"` while the download promise is pending.
  - `formatSize(bytes: number): string` in `format.ts` → `"1,1 GB"`, `"350 MB"` (vi-VN decimal comma).

- [ ] **Step 1: Write the failing tests**

```ts
test("default is failed-only, selected disabled without a selection", () => {
  render(<ExportZipDialog totalCount={4000} failedCount={12} selectedCount={0} onClose={vi.fn()} onExport={onExport} />);
  expect(screen.getByLabelText(/Các case đang chọn/)).toHaveProperty("disabled", true);
  expect(screen.getByText(/~1,1 GB/)).toBeTruthy();
  fireEvent.click(screen.getByText("Xuất zip")); expect(onExport).toHaveBeenCalledWith("failed");
});
test("formatSize", () => { expect(formatSize(1_200_000_000)).toBe("1,1 GB"); expect(formatSize(350_000_000)).toBe("334 MB"); });
// AppRunPanel.test.tsx: label "Chạy trên app (3)" when selectedCount=3; export buttons disabled with runId=null
```

(`formatSize` uses binary units: 1 GB = 1024³ bytes, 1 MB = 1024² — the expected strings above follow that.)

- [ ] **Step 2: Run to verify they fail** — `npm test` → FAIL.
- [ ] **Step 3: Implement** and wire in `App.tsx` (step-2 selection ids → `startAppRun` and `downloadSessionZip`; failed count = run summary `Sai` + `Lỗi thao tác`; total = run result count).
- [ ] **Step 4: Run** — `npm test` and `npm run build` → PASS.
- [ ] **Step 5: Commit** — `feat(ui): step 2 runs selected cases, exports form Excel and session zip`

---

### Task 11: End-to-end check and docs

**Files:**
- Modify: `tests/e2e/browser_e2e.py` (button texts / endpoints changed), `README.md` (usage section: 2 steps, export zip layout)

- [ ] **Step 1: Update `tests/e2e/browser_e2e.py`** to click `Sinh audio (tất cả)`, wait, `Verify (tất cả)`, switch to `Bước 2 — Test app`, run, then click `Xuất zip phiên` → `Xuất zip`.
- [ ] **Step 2: Full automated suite** — `uv run pytest backend/tests -q` and `cd frontend && npm test && npm run build` → all PASS.
- [ ] **Step 3: Manual run in the browser** (use the `run` skill to launch backend + frontend): import `public/DieuKhienXe_Pre.xlsx` (one sheet), select 3 rows, Sinh audio → Verify → ⟳ on one row → Verify again; toggle theme through all three modes (check the table, modals, phone panel in dark); with a phone attached, run Step 2 on 2 selected cases, export the form Excel and open it in Excel, export the zip and check one `FAIL_` folder has `manhinh.png` showing the open sheet. Without a phone, check Step 2 export on an existing run.
- [ ] **Step 4: Update README** usage section (two steps, selection, Sinh lại, zip layout tree from the spec §5.6).
- [ ] **Step 5: Commit** — `test(e2e): two-step flow and session export; docs`
