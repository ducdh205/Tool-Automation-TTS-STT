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

Mặc định VieNeu chạy CPU (~1–2 giây/câu). Nếu máy có card NVIDIA, chọn **GPU** trong bảng
**Thiết bị kiểm thử** (chân sidebar): app kiểm tra PyTorch CUDA, nếu chưa có thì hỏi rồi tự cài
(~2.5 GB) ở nền và chuyển sang GPU khi xong. Driver NVIDIA phải cài sẵn. Cài tay (dự phòng):

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

1. **Nạp file** (xlsx/csv) → chọn các sheet tính năng, dòng header và cột câu nói (tool tự gợi ý theo tên cột).
   Tool giữ một bản sao file gốc để xuất kết quả.
2. Dòng không đọc được (dòng Hệ thống, chú thích trong ngoặc, ký tự lạ như `…`, `→`, `<script>`) tự chuyển
   **Không áp dụng**. Nhấp đúp ô *Câu đọc* để sửa và bật lại; nút **⏻** cuối dòng (hiện khi rê chuột) tạm loại / bật lại một câu.
   Biểu tượng ✎ cạnh câu đọc nghĩa là câu đọc khác câu gốc — rê chuột để xem câu gốc.
   "Hey Vita / Hey Vi" ở đầu câu được bỏ trước khi sinh audio.
3. **Chọn case** bằng ô vuông đầu dòng (Shift+click chọn một dải; ô ở tiêu đề chọn mọi dòng đang hiển thị
   theo bộ lọc). Không chọn gì = các nút áp dụng cho tất cả.
4. **Sinh audio** → sinh audio cho các câu chưa có audio (trạng thái *Đã sinh audio*).
5. **Verify** → wyoming nghe lại: khớp (WER = 0) là **Đạt**, không khớp là **Audio không đạt** (không tự sinh lại).
6. **Sinh lại** (hoặc **⟳** trên từng dòng, hiện khi rê chuột) → sinh audio mới với seed khác cho câu không đạt, rồi bấm **Verify** lại.
   Khi đang chạy, thanh tiến độ và nút **Dừng** hiện dưới thanh thao tác — bấm chạy lại sẽ làm tiếp các câu chưa xong.
7. **Xuất ▾ → Excel** (5 sheet: Tổng quan, Khối 1 – Verify, Audio không đạt, Không áp dụng, Lỗi) hoặc **CSV**.
8. **Lưu và nạp lại bộ audio** (để lần sau test tiếp mà không sinh / verify lại): nút **⭳** ở mỗi bộ audio (hiện khi rê chuột)
   tải về một file `.zip` gồm `manifest.json` (câu, trạng thái, WER, sheet và dòng gốc) và thư mục `audio/*.wav`. Zip **không** kèm
   bản sao file input gốc: kết quả Bước 2 của bộ nạp lại được xuất dạng bảng thường thay vì ghi vào file gốc.
   Nút **Nạp** cạnh tiêu đề *Bộ audio* nhận file zip đó và tạo một bộ **mới** (trùng tên thì thêm ` (2)`, ` (3)`…;
   không ghi đè bộ có sẵn). Câu **Đạt** vẫn **Đạt**, dùng được ngay ở Bước 2. Câu thiếu file audio trong zip quay về **Chờ**
   và tool báo số câu cần sinh lại. Zip không kèm kết quả test trên điện thoại (dùng **Zip phiên** của Bước 2 cho phần đó).
   Cả hai nút bị khóa khi đang chạy job.

**Cài đặt chạy** là nút tóm tắt bên phải thanh thao tác Bước 1 (vd. `Ngọc Huyền · WER ≤ 0% · 30s`). Bấm vào để sửa
giọng VieNeu cho bộ audio mới, ngưỡng WER (%), thời gian chờ STT (giây) và ngưỡng cảnh báo tỉ lệ loại (mặc định 10%).
Tỉ lệ Đạt / Loại hiện cạnh tên bộ audio; Loại chuyển đỏ khi vượt ngưỡng cảnh báo.

## Khối 2 — test trên điện thoại

Không cài gì lên điện thoại (chỉ dùng `adb` có sẵn của Android).

1. Tải [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) và giải nén vào
   `vendor/platform-tools/` (cần `adb.exe`).
2. Trên điện thoại: bật **Tùy chọn nhà phát triển → Gỡ lỗi USB**, cắm cáp, bấm **Cho phép**.
   Cột phải của tool hiện màn hình điện thoại (chạm/vuốt được).
3. Mở app cần test ở **màn hình chính**. Đặt âm lượng loa máy tính ~70%, điện thoại cách loa 20–40 cm,
   phòng yên tĩnh (app bắt cả tiếng nói xung quanh).
4. Chạy Bước 1 trước — chỉ câu **Đạt** mới được test trên app (Bước 2 bị khóa khi chưa có câu Đạt).
5. Thanh trái → **Bước 2 — Test app** → chọn case (hoặc không chọn = tất cả câu Đạt), hồ sơ app (và thiết bị nếu cắm nhiều máy) →
   **Chạy trên app**. Mỗi lần bấm là **một phiên test mới**. Mỗi câu khoảng 13–20 giây.
   Kết quả: **Đúng / Sai / Lỗi thao tác** (lỗi do tool không điều khiển được app, không tính vào tỉ lệ đúng).
   Câu **Sai** và **Lỗi thao tác** được chụp màn hình ngay lúc đó (trước khi đóng bảng).
   **Chạy tiếp** chạy lại các câu Chờ và Lỗi thao tác của phiên đang chọn. Ở Bước 2, bộ lọc trạng thái lọc theo
   kết quả app của phiên đang chọn; tỉ lệ Đúng hiện cạnh tên bộ audio.
6. Xuất kết quả của phiên đang chọn (nút **Xuất ▾**):
   - **Excel kết quả** — bản sao file input giữ nguyên định dạng, chỉ còn các sheet đã chọn; sheet đầu
     *Tổng hợp phiên*; mỗi sheet thêm 4 cột sau cột cuối: *Text app nghe được*, *Kết quả* (Pass / Fail /
     Lỗi thao tác), *Ghi chú* (WER, CER, từ sai), *Ảnh màn hình* (ảnh thu nhỏ của câu Fail / Lỗi thao tác). Sheet không chọn nhưng có dropdown / công thức
     trỏ tới được giữ lại ở dạng ẩn. Bộ audio tạo trước khi có tính năng này hoặc input csv: bảng đơn giản.
     File gốc không bị sửa.
   - **Zip phiên** — chọn audio kèm theo: chỉ case Sai / Lỗi thao tác (mặc định), tất cả, hoặc các case đang chọn:

     ```
     Phien12_2026-11-20_1530_<máy>/
     ├── KetQua_<bộ audio>_Phien12.xlsx   (Excel kết quả ở trên)
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

### iPhone (WebDriverAgent, không cần Mac)

Cần: `vendor/go-ios/ios.exe` (+ `wintun.dll`), iTunes / Apple Mobile Device Support, iPhone bật
**Developer Mode**, WebDriverAgent đã ký và cài lên máy (`vendor/wda/WDA.ipa`, ký bằng Sideloadly; Apple ID
thường hết hạn sau 7 ngày — ký lại). Mỗi lần test, mở 3 cửa sổ PowerShell:

```powershell
# 1. Nạp developer disk image (lại sau mỗi lần khởi động lại iPhone)
uv tool run --python 3.12 --from pymobiledevice3 python -m pymobiledevice3 mounter auto-mount
# 2. Chạy WebDriverAgent (để cửa sổ mở)
uv tool run --python 3.12 --from pymobiledevice3 python -m pymobiledevice3 developer dvt xcuitest <bundle id WDA>.xctrunner --userspace
# 3. Chuyển cổng (để cửa sổ mở)
vendor\go-ios\ios.exe forward 8100 8100
```

Tool tự nhận iPhone (qua go-ios) — bảng Thiết bị báo *Chưa chạy WebDriverAgent* nếu bước 2–3 chưa chạy.
Cùng hồ sơ app (bundle id = package). Khác Android: tool chờ nút "Dừng nghe" hiện ra thay cho `dumpsys audio`,
"Back" = chạm "Đóng" (không có thì vuốt từ mép trái), gõ được chữ có dấu; không có phím Đa nhiệm / Nguồn.
Một WebDriverAgent (cổng 8100) điều khiển một iPhone; đổi cổng: `wda_url` trong `data/settings.json`.

Test trên trình duyệt (Edge, cần server và điện thoại): `uv run python tests/e2e/browser_e2e.py --items 5`
(không có điện thoại: thêm `--no-phone` để chỉ chạy Bước 1 và kiểm tra theme).

## Dữ liệu

Tất cả nằm trong `data/` (không commit): `settings.json`, `tool.db` (SQLite), `audio/` (WAV đã sinh, dùng lại
khi chạy lại), `reports/`, `uploads/`, `app_runs/<phiên>/` (ảnh chụp màn hình khi Sai / Lỗi thao tác),
`wyoming/` (model + log `server.log`).

Nút **Xóa tất cả** cạnh tiêu đề *Bộ audio* ở thanh trái xóa toàn bộ dữ liệu output: mọi bộ audio, các lần test app,
`audio/`, `reports/`, `uploads/`, `app_runs/`. Giữ lại `settings.json`, `profiles/`, `wyoming/` và giọng nghe thử.
Không hoàn tác được; bị khóa khi đang chạy job. Muốn giữ lại một bộ audio trước khi xóa, hãy **Xuất** nó trước
(xem Bước 1, mục 8) rồi **Nạp** lại sau.

Thêm từ tương đương cho so sánh (ví dụ `SĐT` = `số điện thoại`):
[backend/tts_stt_tool/compare/rules.json](backend/tts_stt_tool/compare/rules.json).

## Đóng gói bản portable offline (folder + .bat)

Tạo thư mục `dist\TTS-STT-Tool\` chứa đủ mọi thứ (2 Python, thư viện, giao diện, adb, model VieNeu + wyoming)
và file chạy `TTS-STT-Tool.bat`. Máy đích **không cần mạng, không cần cài Python/uv/Node/Git**, không cần
quyền admin, không cần cài đặt — copy cả thư mục là chạy.

Trên máy build (đã làm bước *Cài đặt* ở trên):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip
```

Lần đầu khoảng 10–20 phút. Script tự smoke test bản đóng gói ở chế độ offline (sinh audio, wyoming nghe lại).
Tham số: `-Zip` (nén thêm `dist\TTS-STT-Tool-<version>.zip`, không kèm `data\`, tiện copy qua USB/mạng),
`-SkipFrontend` (dùng `frontend\dist` sẵn có), `-SkipSmokeTest`. Thư mục `models\` và `data\` trong
`dist\TTS-STT-Tool` được giữ lại giữa các lần build.

Trên máy đích: copy/giải nén thư mục vào chỗ ghi được (vd. `D:\TTS-STT-Tool`, **không** để trong
`Program Files`), bấm đúp **`TTS-STT-Tool.bat`** (muốn có shortcut thì *Send to → Desktop*). Một cửa sổ console
hiện ra, trình duyệt tự mở; **đóng cửa sổ console là tắt tool** (wyoming tắt theo). Chạy lại `.bat` khi tool
đang chạy chỉ mở lại trình duyệt. Có thể truyền tham số như khi chạy dev: `TTS-STT-Tool.bat --port 9000`.

Dữ liệu (db, audio, báo cáo, hồ sơ app) nằm trong `data\` ngay trong thư mục tool. Lên bản mới: copy `data\`
từ thư mục cũ sang thư mục mới. Muốn để dữ liệu chỗ khác: đặt biến môi trường `TTS_STT_DATA_DIR`.

Lưu ý: Python đóng kèm **không có chữ ký số**. Máy bật Smart App Control có thể chặn `python.exe` — cần
tắt Smart App Control trên máy đó. Bản đóng gói chạy VieNeu bằng CPU.

## Phát triển

```bash
uv run python -m pytest            # test backend (bỏ qua test cần model thật)
uv run python -m pytest -m gpu     # test VieNeu thật
uv run python -m pytest -m live    # test wyoming thật
cd frontend && npx vitest run      # test giao diện
cd frontend && npm run dev         # dev server (proxy /api, /ws → 8765)
```
