# TTS → STT Automation Test

Công cụ đo tỉ lệ nhận dạng giọng nói (speech-to-text) của app trợ lý giọng nói tiếng Việt.

- **Khối 1 (đã có):** nạp file testcase → sinh audio bằng **VieNeu-TTS** → **wyoming-vietnamese** nghe lại để
  kiểm tra audio chuẩn → so sánh WER/CER → xuất báo cáo Excel/CSV.
- **Khối 2 (đã có):** loa máy tính phát audio đã verify, điện thoại Android (cắm USB) nghe bằng micro thật
  qua app; tool tự bấm mic, đọc câu app nhận được, so sánh WER/CER và báo cáo tỉ lệ đúng của app.

Thiết kế: [docs/superpowers/specs/2026-11-20-tts-stt-automation-design.md](docs/superpowers/specs/2026-11-20-tts-stt-automation-design.md)

## Cài đặt (Windows, một lần)

Cần: [uv](https://docs.astral.sh/uv/), Node.js 20+, Git.

```bash
# 1. Môi trường Python của tool (Python 3.12 do uv tự tải)
uv sync

# 2. wyoming-vietnamese (STT tham chiếu) — chạy riêng, Python 3.14.8
git clone --depth 1 https://github.com/luuquangvu/wyoming-vietnamese vendor/wyoming-vietnamese
cd vendor/wyoming-vietnamese
uv sync --no-dev --python 3.14.8
cd ../..

# 3. Giao diện
cd frontend
npm install
npm run build
cd ..
```

Lần chạy đầu sẽ tải model từ Hugging Face (cần mạng): VieNeu ~2–3 phút, wyoming ~1 phút.

> **Vì sao Python 3.14.8?** Trên máy có bật Windows Application Control (Smart App Control),
> bản 3.14.10 bị chặn khi nạp `ssl`. Chi tiết: [docs/spikes/2026-11-20-runtime-spike.md](docs/spikes/2026-11-20-runtime-spike.md).
> Vì lý do tương tự, chạy test bằng `uv run python -m pytest` (file `pytest.exe` bị chặn).

### GPU (tùy chọn)

Mặc định VieNeu chạy CPU (~1–2 giây/câu). Nếu máy có GPU NVIDIA, cài torch CUDA để nhanh hơn:

```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

## Chạy

```bash
uv run python -m tts_stt_tool
```

(Trên máy không bật Application Control có thể gõ gọn `uv run tts-stt-tool`; máy này chặn file `.exe` đó.)

Tool mở `http://127.0.0.1:8765` trong trình duyệt và **tự khởi động wyoming** (cổng 10300).
Tham số: `--port 9000`, `--no-browser`, `--data-dir <thư mục>`.

Thanh trái có 2 bước. Nút **◐ / ☀ / ☾** ở chân thanh trái đổi giao diện: theo hệ thống, sáng, tối.

### Bước 1 — Audio

1. **Nạp file** → chọn các sheet tính năng (form testcase 36 cột, header ở dòng 4, câu nói ở cột M).
   File csv/xlsx khác form: chọn cột câu nói.
2. Dòng không đọc được (dòng Hệ thống, chú thích trong ngoặc, ký tự lạ như `…`, `→`, `<script>`) tự chuyển
   **Không áp dụng**. Nhấp đúp ô *Câu đọc* để sửa và bật lại; nút **⏻** cuối dòng tạm loại / bật lại một câu.
   "Hey Vita / Hey Vi" ở đầu câu được bỏ trước khi sinh audio.
3. **Chọn case** bằng ô vuông đầu dòng (Shift+click chọn một dải; ô ở tiêu đề chọn mọi dòng đang hiển thị
   theo bộ lọc). Không chọn gì = các nút áp dụng cho tất cả.
4. **Sinh audio** → sinh audio cho các câu chưa có audio (trạng thái *Đã sinh audio*).
5. **Verify** → wyoming nghe lại: khớp (WER = 0) là **Đạt**, không khớp là **Audio không đạt** (không tự sinh lại).
6. **Sinh lại** (hoặc **⟳** trên từng dòng) → sinh audio mới với seed khác cho câu không đạt, rồi bấm **Verify** lại.
   **Dừng** bất cứ lúc nào — bấm lại sẽ làm tiếp các câu chưa xong.
7. **Xuất Excel** (5 sheet: Tổng quan, Khối 1 – Verify, Audio không đạt, Không áp dụng, Lỗi) hoặc **CSV**.

**Thanh thao tác Bước 1** có giọng VieNeu cho bộ audio mới, ngưỡng WER theo phần trăm và thời gian chờ STT tính theo giây.
Ngưỡng cảnh báo tỉ lệ audio bị loại (mặc định 10%) nằm trong **Cài đặt** ở thanh trái.

## Khối 2 — test trên điện thoại

Không cài gì lên điện thoại (chỉ dùng `adb` có sẵn của Android).

1. Tải [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) và giải nén vào
   `vendor/platform-tools/` (cần `adb.exe`).
2. Trên điện thoại: bật **Tùy chọn nhà phát triển → Gỡ lỗi USB**, cắm cáp, bấm **Cho phép**.
   Cột phải của tool hiện màn hình điện thoại (chạm/vuốt được).
3. Mở app cần test ở **màn hình chính**. Đặt âm lượng loa máy tính ~70%, điện thoại cách loa 20–40 cm,
   phòng yên tĩnh (app bắt cả tiếng nói xung quanh).
4. Chạy Bước 1 trước — chỉ câu **Đạt** mới được test trên app (Bước 2 bị khóa khi chưa có câu Đạt).
5. Thanh trái → **Bước 2 — Test app** → chọn case (hoặc không chọn = tất cả câu Đạt), thiết bị, hồ sơ app →
   **Chạy trên app**. Mỗi lần bấm là **một phiên test mới**. Mỗi câu khoảng 13–20 giây.
   Kết quả: **Đúng / Sai / Lỗi thao tác** (lỗi do tool không điều khiển được app, không tính vào tỉ lệ đúng).
   Câu **Sai** và **Lỗi thao tác** được chụp màn hình ngay lúc đó (trước khi đóng bảng).
   **Chạy tiếp** chạy lại các câu Chờ và Lỗi thao tác của phiên đang chọn.
6. Xuất kết quả của phiên đang chọn:
   - **Xuất Excel (form)** — file theo form testcase 36 cột, chỉ các case đã test: cột P *Kết quả thực tế*,
     S *KQ ASR* (Pass/Fail), X *KẾT QUẢ TỔNG* (chỉ điền `Fail` khi app nghe sai), Z *Bằng chứng* (folder trong zip),
     AA *Thông tin lần chạy*, AB *Ghi chú* (WER/CER, từ sai). File gốc không bị sửa.
   - **Xuất zip phiên** — chọn audio kèm theo: chỉ case Sai / Lỗi thao tác (mặc định), tất cả, hoặc các case đang chọn:

     ```
     Phien12_2026-11-20_1530_<máy>/
     ├── KetQua_<bộ audio>_Phien12.xlsx   (Excel theo form ở trên)
     ├── TongQuan.xlsx                    (báo cáo nhiều sheet: Khối 1 + Khối 2)
     ├── thong_tin_phien.txt              (máy, hồ sơ app, phiên bản app, giờ chạy, cài đặt)
     └── <Tên sheet>/
         ├── FAIL_TC-ON-002/  luot1_ketqua.txt · luot1_log.txt · luot1_manhinh.png · luot1_audio.wav
         ├── LOI_TC-ON-007/ …
         └── PASS_TC-ON-001/ …
     ```

     Tiền tố folder theo lượt tệ nhất: `FAIL_` > `LOI_` > `CHUA_` (còn lượt chưa chạy) > `PASS_`.
     Các lượt hội thoại cùng TC_ID nằm chung một folder (`luot1_`, `luot2_`…).

**Hồ sơ app** (mặc định *Vita Work (dev)*, `com.vita.suite.dev`): nhãn các nút trên app — mở mic
"Nói để tạo việc", dừng "Dừng nghe", mic chờ "Bấm để nói", đóng "Đóng". App khác hoặc đổi giao diện:
bấm **Ghim nút cho hồ sơ app** ở cột phải, chạm lên nút trên màn hình mirror, chọn vai trò để lưu.
Hồ sơ lưu ở `data/profiles/`.

Cách tool chạy một câu: bấm mic → chờ mic thật sự thu (`dumpsys audio`) → 0,3 s → phát audio → 1 s →
bấm "Dừng nghe" (nếu app chưa tự dừng) → đọc bong bóng chat mới bên phải (`uiautomator dump`) → bấm "Đóng".

Test trên trình duyệt (Edge, cần server và điện thoại): `uv run python tests/e2e/browser_e2e.py --items 5`
(không có điện thoại: thêm `--no-phone` để chỉ chạy Bước 1 và kiểm tra theme).

## Dữ liệu

Tất cả nằm trong `data/` (không commit): `settings.json`, `tool.db` (SQLite), `audio/` (WAV đã sinh, dùng lại
khi chạy lại), `reports/`, `uploads/`, `app_runs/<phiên>/` (ảnh chụp màn hình khi Sai / Lỗi thao tác),
`wyoming/` (model + log `server.log`).

Thêm từ tương đương cho so sánh (ví dụ `SĐT` = `số điện thoại`):
[backend/tts_stt_tool/compare/rules.json](backend/tts_stt_tool/compare/rules.json).

## Phát triển

```bash
uv run python -m pytest            # test backend (bỏ qua test cần model thật)
uv run python -m pytest -m gpu     # test VieNeu thật
uv run python -m pytest -m live    # test wyoming thật
cd frontend && npx vitest run      # test giao diện
cd frontend && npm run dev         # dev server (proxy /api, /ws → 8765)
```
