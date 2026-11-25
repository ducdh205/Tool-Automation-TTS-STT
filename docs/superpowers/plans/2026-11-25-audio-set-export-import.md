# Xuất / nạp bộ audio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xuất một bộ audio (kèm WAV và trạng thái verify) ra file zip và nạp lại thành bộ mới trong chính tool này.

**Architecture:** `Store` có hai hàm thô đọc/ghi hàng của bộ audio. Module mới `report/audio_set_zip.py` lo định dạng zip (`manifest.json` + `audio/*.wav`) và kiểm tra file nạp. Hai route mới dùng lại cơ chế token một lần `/exports/{token}`. Giao diện thêm nút **Xuất** mỗi bộ và nút **Nạp bộ audio** ở thanh trái.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, zipfile, pytest; React + TypeScript, vitest.

**Spec:** [docs/superpowers/specs/2026-11-25-audio-set-export-import-design.md](../specs/2026-11-25-audio-set-export-import-design.md)

> Lưu ý: working tree đang có thay đổi chưa commit ở `backend/tts_stt_tool/api/routes.py`, `backend/tts_stt_tool/store/db.py`, `backend/tests/api/test_routes.py`, `backend/tests/store/test_db.py`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/App.test.tsx` (của người dùng, không thuộc kế hoạch này). Các task dưới đây sửa chồng lên những file đó: chỉ `git add` đúng hunk của mình (`git add -p`), không commit phần dở của người dùng.

## Global Constraints

- `manifest.json`: `{"format": "tts-stt-audio-set", "version": 1, ...}`; `format` hoặc `version` lạ → HTTP 422, thông báo tiếng Việt.
- Zip: `manifest.json` ở gốc; WAV là entry `audio/<tên>.wav` (không thư mục con, không `..`); mỗi item có `audio` = `"audio/<tên>.wav"` hoặc `null`.
- Nạp luôn tạo bộ **mới**; trùng tên → hậu tố ` (2)`, ` (3)`…; không ghi đè bộ có sẵn.
- Không kèm kết quả test điện thoại (`app_runs`, `app_results`).
- Thiếu WAV trong zip → câu về trạng thái `Chờ` chưa có audio (dùng `_RESET_SQL`: `audio_path=NULL, attempts=0, ref_text=NULL, wer=NULL, cer=NULL, ops_json=NULL, error=NULL`); trả `missing_audio` = số câu bị vậy.
- Nạp bị chặn bằng 409 khi đang chạy job (như xóa bộ).
- Chỉ nhận entry WAV có tên khớp `^[A-Za-z0-9_\-]+\.wav$`; chép vào `ctx.cache.root`, tên đã tồn tại thì bỏ qua (cache đánh địa chỉ theo nội dung).
- Mọi thông báo cho người dùng bằng tiếng Việt.

## Review Focus

- Zip có entry `audio/../x.wav` hoặc `../x.wav` hoặc đường dẫn tuyệt đối: không được ghi ra ngoài `data/audio/`, và nạp bị từ chối (422).
- File upload không phải zip, hoặc zip thiếu `manifest.json`, hoặc `manifest.json` không phải JSON: 422, không tạo bộ nào.
- Manifest có item trỏ `audio` tới entry không có trong zip: câu đó về `Chờ`, `missing_audio` đúng số, các câu khác giữ nguyên `Đạt`.
- Xuất bộ rồi xóa bộ gốc, nạp lại: câu **Đạt** vẫn **Đạt**, `form_json` còn nguyên (Excel theo form dùng được), WAV nghe lại được qua `/items/{id}/audio`.
- Nạp cùng một file hai lần liên tiếp: hai bộ khác tên (`X`, `X (2)`), WAV không bị chép đè hay nhân đôi.

---

### Task 1: Store — đọc và ghi thô một bộ audio

**Files:**
- Modify: `backend/tts_stt_tool/store/db.py` (thêm hai method vào `Store`, sau `delete_all_audio_sets`)
- Test: `backend/tests/store/test_db.py`

**Interfaces:**
- Produces:
  - `Store.export_audio_set(audio_set_id: int) -> dict[str, Any] | None` — `None` nếu không có bộ; ngược lại `{"audio_set": {"name","source_file","sheets": list[str],"voice","voice_trung","voice_nam","created_at"}, "items": list[dict]}`. Mỗi item gồm mọi cột của `items` trừ `id` và `audio_set_id` (giữ `ops_json`, `form_json` là chuỗi thô, `audio_path` là chuỗi tuyệt đối hoặc `None`), sắp theo `id`.
  - `Store.import_audio_set(audio_set: dict[str, Any], items: list[dict[str, Any]]) -> int` — chèn bộ mới (tên làm duy nhất bằng hậu tố ` (n)`), chèn các item bằng đúng các cột có trong dict (khóa lạ bị bỏ qua, `id`/`audio_set_id` bị bỏ qua), trả `id` bộ mới. Không chạy lại `classify`.

- [ ] **Step 1: Write the failing tests** trong `test_db.py` (dùng fixture `store`, `set_id`, `_item`):
  - `test_export_audio_set_roundtrip_keeps_state(store, set_id)`: ghi `record_generated` cho một item, `record_verify(..., ItemStatus.PASSED)` cho nó; `data = store.export_audio_set(set_id)`; `new_id = store.import_audio_set(data["audio_set"], data["items"])`; assert `new_id != set_id`, `store.get_items(new_id)` có cùng `tc_id`, `status`, `audio_path`, `wer`, `ops`, `enabled`, `skip_reason` với `store.get_items(set_id)` theo thứ tự, và `store.get_audio_set(new_id)["sheets"] == ["S1"]`, `["voice"] == "Ngọc Huyền"`.
  - `test_import_audio_set_makes_name_unique(store, set_id)`: nạp hai lần cùng `data`; assert tên các bộ mới là `"bộ 1 (2)"` và `"bộ 1 (3)"`.
  - `test_export_audio_set_keeps_form_cells(store)`: tạo bộ có `InputItem(..., form=[...])` (xem `test_form_cells_kept_but_not_in_payload`), xuất rồi nạp, assert `store.form_cells(new_id)` bằng `store.form_cells(set_id)` (theo thứ tự item).
  - `test_export_unknown_audio_set_returns_none(store)`: `store.export_audio_set(999) is None`.
  - `test_import_does_not_copy_app_runs(store, set_id)`: tạo `create_app_run(set_id, ...)`, xuất+nạp, assert `store.list_app_runs(new_id) == []`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest backend/tests/store/test_db.py -k "export or import" -v`
Expected: FAIL với `AttributeError: 'Store' object has no attribute 'export_audio_set'`.

- [ ] **Step 3: Implement both methods in `db.py`.** Xuất: `SELECT * FROM items WHERE audio_set_id=? ORDER BY id`, bỏ `id`, `audio_set_id`; `sheets` lấy từ `get_audio_set`. Nạp: một transaction (`with self._conn()`), lấy tên bộ mới bằng vòng lặp kiểm tra `SELECT 1 FROM audio_sets WHERE name=?`; cột item lấy từ danh sách cố định (các cột của bảng `items` trừ `id`, `audio_set_id`) giao với khóa của dict; `created_at` của bộ mới là `_now()`; `updated_at` item giữ giá trị trong file nếu có, ngược lại `_now()`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest backend/tests/store/test_db.py -v`
Expected: PASS (cả test cũ).

- [ ] **Step 5: Commit** (chỉ hunk của task này)

```bash
git add -p backend/tts_stt_tool/store/db.py backend/tests/store/test_db.py
git commit -m "feat(store): export and import a whole audio set's rows"
```

---

### Task 2: Module zip — dựng và đọc gói bộ audio

**Files:**
- Create: `backend/tts_stt_tool/report/audio_set_zip.py`
- Test: `backend/tests/report/test_audio_set_zip.py` (tạo; nếu thư mục `backend/tests/report/` chưa có `__init__.py` thì làm giống các thư mục test anh em)

**Interfaces:**
- Consumes: `Store.export_audio_set`, `Store.import_audio_set` (Task 1), `Store.get_audio_set`.
- Produces:
  - `class PackError(ValueError)` — lỗi file nạp; message tiếng Việt, hiển thị thẳng cho người dùng.
  - `pack_name(audio_set: dict[str, Any]) -> str` — tên file tải: `"<tên an toàn>_<yyyy-mm-dd>.zip"` (ngày hôm nay).
  - `build_audio_set_zip(store: Store, audio_set_id: int, out: Path) -> None` — ghi zip vào `out` (WAV lưu `ZIP_STORED`, manifest `ZIP_DEFLATED`). Item có `audio_path` nhưng file không còn trên đĩa → `audio: null` trong manifest (không làm hỏng việc xuất). Hai item cùng WAV chỉ ghi một entry. Raise `KeyError` nếu không có bộ.
  - `import_audio_set_zip(store: Store, zip_path: Path, audio_dir: Path) -> dict[str, int]` — trả `{"id": int, "missing_audio": int}`; raise `PackError` khi: không phải zip, thiếu `manifest.json`, manifest không phải JSON object, `format`/`version` sai, entry audio có tên không khớp `^[A-Za-z0-9_\-]+\.wav$`. Ghi WAV vào `audio_dir` qua file tạm rồi `os.replace`; tên đã tồn tại thì bỏ qua. `audio_path` của item = `str(audio_dir / tên)`.

- [ ] **Step 1: Write the failing tests** (tạo store thật trong `tmp_path`, WAV giả bằng bytes bất kỳ ghi ra `tmp_path/"audio"/"aaaa.wav"`):
  - `test_roundtrip_restores_passed_state_and_audio`: bộ có 2 item (một `Đạt` có WAV, một `Chờ`); `build_audio_set_zip` → `store.delete_audio_set` → xóa file WAV → `import_audio_set_zip(store, zip, new_audio_dir)`; assert `missing_audio == 0`, item Đạt vẫn `Đạt`, `Path(item["audio_path"]).read_bytes()` bằng bytes ban đầu, `Path(...).parent == new_audio_dir`.
  - `test_zip_has_manifest_and_audio_entries`: `zipfile.ZipFile(out).namelist()` chứa `manifest.json` và `audio/aaaa.wav`; manifest có `format == "tts-stt-audio-set"`, `version == 1`.
  - `test_missing_wav_on_disk_exports_as_null_audio`: xóa WAV trước khi xuất → xuất thành công, item đó `audio: null`; nạp lại → item đó `Chờ`, `audio_path is None`, `missing_audio == 1`.
  - `test_missing_entry_in_zip_resets_row_and_counts` (Review Focus): tự dựng zip có manifest trỏ `audio/x.wav` nhưng không có entry đó; item `Đạt` → sau nạp là `Chờ`, `wer is None`, `missing_audio == 1`; item khác không đổi.
  - `test_rejects_path_traversal_entries` (Review Focus): zip có entry `audio/../evil.wav`, `../evil.wav`, `/abs.wav`, `audio/sub/x.wav` và manifest trỏ tới nó → mỗi trường hợp raise `PackError`, `store.list_audio_sets()` rỗng, không có file nào bị ghi ngoài `audio_dir` (kiểm tra `tmp_path` không có `evil.wav`).
  - `test_rejects_bad_files` (Review Focus): bytes không phải zip; zip không có `manifest.json`; `manifest.json` = `"[]"`; `format` sai; `version: 2` → mỗi cái raise `PackError`, không tạo bộ.
  - `test_import_twice_gives_two_sets_and_one_wav` (Review Focus): nạp cùng zip hai lần → tên `X`, `X (2)`; `audio_dir` chỉ có một file WAV đó, không có `.tmp` sót.
  - `test_pack_name_is_filesystem_safe`: tên bộ `'a/b:c*"d'` → tên file không chứa `/ : * "` và kết thúc `.zip`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest backend/tests/report/test_audio_set_zip.py -v`
Expected: FAIL với `ModuleNotFoundError: tts_stt_tool.report.audio_set_zip`.

- [ ] **Step 3: Implement the module.** Dùng `safe_component` từ `tts_stt_tool.report.layout` cho `pack_name`. Khi nạp: đọc manifest bằng `ZipFile.read`, kiểm tra tên của **mọi** entry bắt đầu bằng `audio/` trước khi ghi bất cứ thứ gì (kiểm tra xong mới ghi → lỗi không để lại file nửa vời); chỉ chép các entry mà manifest tham chiếu; đặt `audio_path`/reset theo Global Constraints rồi gọi `store.import_audio_set` một lần ở cuối.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest backend/tests/report/test_audio_set_zip.py backend/tests/store/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tts_stt_tool/report/audio_set_zip.py backend/tests/report
git commit -m "feat(report): audio set zip with manifest and WAVs"
```

---

### Task 3: API — route xuất và nạp

**Files:**
- Modify: `backend/tts_stt_tool/api/routes.py` (thêm import `from tts_stt_tool.report.audio_set_zip import PackError, build_audio_set_zip, import_audio_set_zip, pack_name`; thêm hai route cạnh `delete_audio_set`; route `POST /audio-sets/import` **phải đặt trước** mọi route có `{set_id}` để không bị nuốt)
- Test: `backend/tests/api/test_routes.py`

**Interfaces:**
- Consumes: `build_audio_set_zip`, `import_audio_set_zip`, `pack_name`, `PackError` (Task 2); `_sweep_exports`, `ctx.exports`, `ctx.exports_dir`, `ctx.cache.root`, `ctx.uploads`, `_require_set`.
- Produces:
  - `POST /api/audio-sets/{set_id}/export` → `{"download_url": "/api/exports/<token>"}`; 404 nếu không có bộ; 409 khi đang chạy job (xuất khi đang ghi WAV sẽ thiếu file).
  - `POST /api/audio-sets/import` (multipart, trường `file`) → `{"id": int, "missing_audio": int}`; 422 với message của `PackError`; 409 khi đang chạy job.

- [ ] **Step 1: Write the failing tests** (dùng `client`, `create_set`, `wait_job_end`, `verify_all`, `statuses` có sẵn):
  - `test_export_then_import_restores_a_verified_set`: `create_set` + `verify_all`; `r = client.post(f"/api/audio-sets/{sid}/export")`; tải `client.get(r.json()["download_url"])` → bytes zip; `client.delete(f"/api/audio-sets/{sid}")`; `client.post("/api/audio-sets/import", files={"file": ("x.zip", bytes)})` → 200, `missing_audio == 0`; `statuses(client, new_id)` có cùng tập giá trị trạng thái trước khi xóa (có `Đạt`); `client.get(f"/api/items/{item_id}/audio")` của một item Đạt trả 200.
  - `test_import_keeps_form_cells_for_excel_report`: sau nạp, `client.post(f"/api/audio-sets/{new_id}/report?format=xlsx")` trả 200 (hoặc dùng cách kiểm tra `form_cells` mà test `test_create_set_keeps_form_cells` đang dùng).
  - `test_import_rejects_non_zip_with_422`: upload `b"not a zip"` → 422, `client.get("/api/audio-sets").json() == []`.
  - `test_export_unknown_set_is_404`: `client.post("/api/audio-sets/999/export").status_code == 404`.
  - `test_export_and_import_while_job_runs_are_409`: theo mẫu `test_delete_audio_set_while_job_runs_is_409` (SlowStt, verify đang chạy) → export 409 và import (kèm zip hợp lệ đã dựng trước đó) 409.
  - `test_import_twice_names_second_set_with_suffix`: nạp cùng zip hai lần → tên bộ mới `bộ 1 (2)` rồi `bộ 1 (3)` trong `GET /api/audio-sets` (bộ gốc vẫn còn tên `bộ 1`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest backend/tests/api/test_routes.py -k "export_then or import or export_unknown or export_and_import" -v`
Expected: FAIL (404/405 vì route chưa có).

- [ ] **Step 3: Implement the routes.** Xuất: theo đúng khuôn `export_zip` (gọi `_sweep_exports`, `token = uuid.uuid4().hex`, ghi vào `ctx.exports_dir / f"{token}.zip"` trong `asyncio.to_thread`, xóa file nếu lỗi, `ctx.exports[token] = (out, pack_name(set))`; nhớ `ctx.exports_dir.mkdir(parents=True, exist_ok=True)` nếu thư mục chưa tồn tại). Nạp: kiểm tra job trước (409, cùng câu chữ với `delete_audio_set`), ghi upload ra file tạm trong `ctx.uploads` (xóa sau khi xong, kể cả khi lỗi), gọi `import_audio_set_zip(ctx.store, tmp, ctx.cache.root)` trong `asyncio.to_thread`, đổi `PackError` thành `HTTPException(422, str(e))`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run python -m pytest backend/tests -q`
Expected: PASS toàn bộ (bỏ qua test cần model thật).

- [ ] **Step 5: Commit** (chỉ hunk của task này)

```bash
git add -p backend/tts_stt_tool/api/routes.py backend/tests/api/test_routes.py
git commit -m "feat(api): export and import an audio set as a zip"
```

---

### Task 4: Giao diện — nút Xuất và Nạp bộ audio

**Files:**
- Modify: `frontend/src/api.ts` (thêm hai hàm vào object `api`)
- Modify: `frontend/src/components/Sidebar.tsx` (props mới + hai nút)
- Modify: `frontend/src/App.tsx` (hai handler, truyền props vào `<Sidebar>` quanh dòng 351–362)
- Test: `frontend/src/components/Sidebar.test.tsx`, `frontend/src/App.test.tsx`

**Interfaces:**
- Produces:
  - `api.exportSet(setId: number): Promise<void>` — `POST /api/audio-sets/${setId}/export`, rồi bấm link `download_url` như `downloadSessionZip`.
  - `api.importSet(file: File): Promise<{ id: number; missing_audio: number }>` — `POST /api/audio-sets/import` với `FormData` trường `file`, qua `req`.
  - `Sidebar` props mới: `onExportSet?: (id: number) => void` (không truyền → ẩn nút Xuất); `onImportSet?: (file: File) => void` (không truyền → ẩn nút Nạp). Nút Xuất mỗi bộ: `aria-label={`Xuất bộ ${s.name}`}`, `className="icon-btn set-export"`. Cả nút Xuất và nút Nạp bị khóa (`disabled` + `title`) khi `deleteLocked` có giá trị, vì server trả 409 cho cả hai khi đang chạy job. Nút Nạp: `aria-label="Nạp bộ audio"`, mở `<input type="file" accept=".zip" hidden>` bằng ref; chọn xong gọi `onImportSet(file)` rồi xóa `value` để chọn lại cùng file được.

- [ ] **Step 1: Write the failing tests** trong `Sidebar.test.tsx` (khối "Sidebar audio sets", dùng `set`/`base` có sẵn):
  - `exports a set without confirmation`: render với `onExportSet`, click `getByRole("button", {name: "Xuất bộ E2E Climate Sync"})` → `onExportSet` gọi với `3`.
  - `imports the chosen zip`: render với `onImportSet`; `fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } })` với `file = new File(["x"], "bo.zip")` → `onImportSet` gọi với `file`.
  - `locks export and import while a job runs`: `deleteLocked="Đang chạy job"` → cả hai nút `disabled` và `title === "Đang chạy job"`.
  - `hides export and import without handlers`: không truyền handler → không có hai nút.
  
  Trong `App.test.tsx` (theo mẫu test xóa bộ có sẵn trong file, mock `fetch`/`api` giống các test cạnh đó): `after importing, the new set is opened and a missing-audio warning is shown` — mock `api.importSet` trả `{ id: 9, missing_audio: 2 }`, assert danh sách được tải lại, bộ 9 được chọn, và thông báo chứa `"2 câu thiếu audio"`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/components/Sidebar.test.tsx src/App.test.tsx`
Expected: FAIL (không tìm thấy nút / `api.importSet` chưa có).

- [ ] **Step 3: Implement.** `Icon` dùng icon có sẵn trong [Icon.tsx](../../frontend/src/components/Icon.tsx) (đọc file để chọn tên; nếu chưa có icon tải xuống/tải lên thì thêm hai icon theo cùng kiểu SVG của file). `App.tsx`: `exportSet(id)` gọi `api.exportSet` và `notifyError` khi lỗi; `importSet(file)` gọi `api.importSet`, rồi `await loadSets()`, `setSetId(r.id)`, `notify(\`Đã nạp bộ audio.\`)` — nếu `r.missing_audio > 0` thì thông báo `\`Đã nạp bộ audio. ${r.missing_audio} câu thiếu audio, cần sinh lại.\`` (kiểu `"warn"` nếu `notify` hỗ trợ, ngược lại thông báo thường); lỗi → `notify((e as Error).message, "error")`. CSS: thêm `.set-export` vào cùng quy tắc hiện/ẩn khi rê chuột như `.set-delete` trong file CSS chung (tìm bằng `grep -rn "set-delete" frontend/src`).

- [ ] **Step 4: Run to verify they pass**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS, không lỗi kiểu.

- [ ] **Step 5: Commit** (chỉ hunk của task này)

```bash
git add -p frontend/src
git commit -m "feat(ui): export and import audio sets from the sidebar"
```

---

### Task 5: Tài liệu và kiểm tra thực tế

**Files:**
- Modify: `README.md` (mục "Bước 1 — Audio" và mục "Dữ liệu")

**Interfaces:** không.

- [ ] **Step 1: Cập nhật README.** Thêm bước vào danh sách Bước 1: **Xuất** (nút ở mỗi bộ, hiện khi rê chuột) tạo zip gồm `manifest.json` + `audio/*.wav`; **Nạp bộ audio** (cạnh tiêu đề *Bộ audio*) tạo bộ mới, giữ trạng thái Đạt, thiếu WAV thì câu về Chờ và có báo; không kèm kết quả test điện thoại. Ở mục *Dữ liệu*, ghi rằng đây là cách giữ lại một bộ trước khi bấm **Xóa tất cả**.

- [ ] **Step 2: Chạy toàn bộ test**

Run: `uv run python -m pytest -q` và `cd frontend && npx vitest run`
Expected: PASS cả hai.

- [ ] **Step 3: Chạy thử trên app thật** (theo skill `run`): nạp một file nhỏ, sinh audio, verify, **Xuất**, **Xóa bộ**, **Nạp bộ audio** bằng zip vừa tải; kiểm tra bộ mới có cùng số câu Đạt và nghe được audio một câu; thử nạp một file `.txt` đổi tên thành `.zip` → thấy thông báo lỗi, không có bộ mới. Ghi lại kết quả (đạt/không) khi báo cáo.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: how to export and import an audio set"
```

---

## Self-review

- **Spec coverage:** định dạng zip → Task 2; `POST …/export` + token tải → Task 3; `POST …/import`, tên trùng, 409, thiếu WAV, chặn path → Task 2–3; `Store` hai hàm → Task 1; nút Xuất/Nạp + thông báo `missing_audio` → Task 4; `version` trong manifest → Global Constraints + Task 2 test. Không kèm kết quả Bước 2 → Task 1 test `test_import_does_not_copy_app_runs`.
- **Quyết định thêm so với spec (có thể sửa):** tên WAV bị giới hạn `^[A-Za-z0-9_\-]+\.wav$` (khớp tên cache `<16 hex>.wav`); xuất cũng bị 409 khi đang chạy job; WAV mất trên đĩa lúc xuất thì xuất tiếp với `audio: null` thay vì báo lỗi.
- **Nhất quán tên:** `export_audio_set`/`import_audio_set` (Store), `build_audio_set_zip`/`import_audio_set_zip`/`pack_name`/`PackError` (module), `exportSet`/`importSet` (api.ts), `onExportSet`/`onImportSet` (Sidebar) dùng thống nhất ở các task.
