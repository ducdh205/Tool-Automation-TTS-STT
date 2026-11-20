# Tool Automation Test TTS → STT trên Android — Thiết kế

Ngày: 2026-11-20 · Trạng thái: chờ duyệt

## 1. Mục đích

Đo **tỉ lệ nhận dạng giọng nói đúng (speech-to-text)** của một app Android bên ngoài (không kiểm soát mã nguồn).
Để con số này đáng tin, audio đầu vào phải "chuẩn". Vì vậy tool có 2 khối:

- **Khối 1 — Cổng chất lượng audio:** text (từ xlsx/csv) → VieNeu-TTS sinh audio → wyoming-vietnamese
  (STT tham chiếu) nghe lại → so với text gốc. Chỉ audio qua được verify mới được dùng ở Khối 2.
  Nhờ đó khi app nhận sai, lỗi thuộc về app chứ không phải audio.
- **Khối 2 — Test trên app thật:** loa máy tính phát audio, điện thoại (cắm USB) thu bằng micro thật
  qua app; tool tự thao tác app, đọc text app hiển thị và so với text gốc.

Kết quả cuối cùng: báo cáo Excel với tỉ lệ đúng của app.

## 2. Mục tiêu / Không làm / Thất bại nếu

**Mục tiêu**
- Chạy được bộ test **hàng nghìn câu** không cần người ngồi trông; dừng/tiếp tục được.
- Một giao diện duy nhất 3 cột: thanh quản lý trái · bảng giữa · màn hình điện thoại phải (live).
- Báo cáo Excel nhiều sheet.

**Không làm (phiên bản này)**
- Không bơm audio qua ADB vào micro (Android không cho phép trên máy thật không root) — đã loại.
- Không test nhiều điện thoại song song (loa phát cho 1 máy, các máy khác sẽ nghe lẫn).
- Không đóng gói .exe ở bản đầu: chạy từ mã nguồn, mở trình duyệt `localhost`.
  Kiến trúc không được cản việc đóng gói .exe sau này.
- Không dùng nhiều giọng: một giọng VieNeu cố định cho mỗi lần chạy.
- Không chấm "đúng ý định" (intent) — chỉ so sánh text.

**Thất bại dù vẫn chạy được nếu**
- Tỉ lệ đúng bị sai lệch do lỗi của tool (đọc nhầm ô kết quả, cắt mất đuôi câu khi bấm dừng sớm,
  audio hỏng lọt qua verify, chuẩn hóa text khác nhau giữa Khối 1 và Khối 2).
- Chạy nghìn câu bị treo/đứt giữa chừng mà mất kết quả đã chạy.

## 3. Ràng buộc

- Máy hiện **chưa cài Python** (chỉ có stub Microsoft Store), nhưng đã có **uv** và Node.js →
  dùng uv để cài Python và quản lý môi trường (đồng bộ với cách wyoming-vietnamese được quản lý).
- Windows 11, Python, máy có **GPU NVIDIA** (VieNeu chạy GPU; CPU vẫn phải chạy được nhưng chậm).
- **VieNeu-TTS** (Apache-2.0): `pip install vieneu`, SDK Python `Vieneu(mode="v3turbo")`, ~25 giọng mẫu,
  48 kHz. GPU cần torch CUDA (cu128) cài trước.
- **wyoming-vietnamese** (MIT, https://github.com/luuquangvu/wyoming-vietnamese): server giao thức
  Wyoming TCP cổng 10300; STT sherpa-onnx Zipformer (CPU), 1–2 GB RAM; model tải lần đầu.
  README chỉ hướng dẫn Docker; repo quản lý bằng uv.
- App test là **app bên ngoài**, không có resource-id ổn định.
- **Điện thoại test là máy công ty bị khóa: không được cài thêm app.** → Không dùng uiautomator2
  (vì nó cài APK agent lên máy). Chỉ dùng công cụ có sẵn của Android qua ADB:
  `adb shell uiautomator dump`, `adb shell input tap/keyevent`, `adb exec-out screencap`.
  **Điều kiện tiên quyết:** máy phải bật USB debugging (không có thì Khối 2 không chạy được).
- Ô "Công việc hôm nay" chứa **toàn bộ câu app nghe được** → so sánh trực tiếp với cả câu gốc.
- Nút voice: **bấm để bắt đầu, bấm lần nữa để dừng**; sau mỗi lần dừng app mở form mới.
- **File input mẫu:** `public/DieuKhienXe_Pre.xlsx` (bộ testcase điều khiển xe VF6, form 36 cột).
  - Mỗi sheet một tính năng (ví dụ "ONOFFTemperature Synchronizatio"); 14 sheet có dữ liệu,
    tổng ~3.986 dòng. Các sheet "Tổng hợp", "Hướng dẫn", "00_Smoke", "01_All" và sheet trống bị bỏ qua.
  - Dòng 1–3 là tiêu đề/nhóm cột, **header ở dòng 4**, dữ liệu từ dòng 5.
  - Cột dùng: **A TC_ID**, **B Cụm tính năng**, **E Mức ưu tiên**, **H Vùng miền**, **I Bước/Lượt**,
    **L Người nói**, **M Câu nói (utterance)** ← text để sinh audio, **N Kết quả mong đợi** (chỉ hiển thị).
  - Có hội thoại nhiều lượt (cùng TC_ID, cột I = 2, 3, …; có cả dạng "Bước 1").

## 4. Các hướng đã cân nhắc

| Hướng | Mô tả | Đánh đổi |
|---|---|---|
| **1. Web localhost + stream màn hình trong trang** ✅ | FastAPI backend, giao diện web; luồng video scrcpy giải mã trong trình duyệt (WebCodecs) | Đúng bố cục 3 cột, bảng lớn dễ làm, đóng gói .exe sau được. Phần stream màn hình tốn công nhất. |
| 2. Desktop Qt | Một app PySide6 tự giải mã scrcpy | Đóng gói đơn giản nhất; không phải localhost, bảng nghìn dòng + nghe audio cồng kềnh hơn. |
| 3. Web localhost + cửa sổ scrcpy riêng | Cột phải chỉ là ảnh chụp 1–2s/lần | Nhanh nhất; không phải "một giao diện". |

**Người dùng chọn Hướng 1.**

## 5. Thiết kế

### 5.1 Kiến trúc

```
Trình duyệt (UI 3 cột) ⇄ HTTP + WebSocket ⇄ Backend FastAPI (Python)
                                              ├─ Input: đọc xlsx/csv (pandas/openpyxl)
                                              ├─ TTS: VieNeu SDK (GPU)
                                              ├─ STT tham chiếu: Wyoming client → wyoming-vietnamese :10300
                                              ├─ So sánh: chuẩn hóa + jiwer (WER/CER)
                                              ├─ Thiết bị: adb (uiautomator dump, input tap, screencap) + scrcpy-server (stream, tùy chọn)
                                              ├─ Phát audio: loa mặc định của máy tính
                                              ├─ Hàng đợi job chạy nền (1 job mỗi lúc)
                                              └─ Lưu trữ: SQLite + thư mục audio cache
```

- **wyoming-vietnamese** chạy như tiến trình Python riêng (uv), không Docker; backend tự khởi động
  và kiểm tra sức khỏe. *Rủi ro:* chưa kiểm chứng trên Windows → việc đầu tiên khi build là spike
  chạy nó trên Windows; nếu thất bại, fallback sang Docker image `ghcr.io/luuquangvu/wyoming-vietnamese`.
  Backend chỉ nói chuyện qua Wyoming TCP nên không phụ thuộc cách chạy.

### 5.2 Luồng Khối 1

1. **Nạp dữ liệu:** người dùng chọn file → chọn **một hoặc nhiều sheet tính năng** (sheet trống/tổng hợp
   tự ẩn). Tool nhận diện form testcase 36 cột (header dòng 4) và đọc sẵn theo **mẫu form** ở §3.
   File csv hoặc xlsx khác form → bước ánh xạ cột thủ công (bắt buộc cột Text, tùy chọn ID),
   lưu lại làm mẫu mới.
   - **Mỗi dòng "Người dùng" là một câu test độc lập**, kể cả lượt 2, 3 của hội thoại nhiều lượt
     (mục tiêu đo nhận dạng giọng nói, không đo hội thoại). Khóa câu = `sheet + TC_ID + lượt`.
   - **Tự loại** (trạng thái "Không áp dụng", liệt kê trong báo cáo; người dùng có thể bật lại
     hoặc sửa text từng dòng trên bảng):
     dòng có Người nói "🚗 Hệ thống (sự kiện)"; câu có chú thích trong ngoặc như
     "(không nói gì, chờ quá 8 giây)", "(lặp 20 lần …)"; câu chứa ký tự/thẻ không đọc được
     (ví dụ `<script>`), dấu "…", "→"; ô trống.
   - **Bỏ từ đánh thức** "Hey Vita" / "Hey Vi" (kèm dấu phẩy) ở đầu câu **trước khi sinh audio
     và khi so sánh** — app được kích hoạt bằng nút mic. Text gốc vẫn được giữ để hiển thị.
2. **Sinh audio:** VieNeu, giọng cố định chọn trong Cài đặt. Lưu WAV vào cache theo khóa
   `hash(text đã chuẩn hóa nhẹ + giọng + tham số)` → chạy lại không sinh lại.
3. **Verify:** gửi WAV tới wyoming (resample về định dạng wyoming yêu cầu, thường 16 kHz mono),
   nhận text, so sánh (5.4).
   - Đạt nếu WER = 0 (ngưỡng chỉnh được trong Cài đặt).
   - Không đạt → tự sinh lại tối đa **N lần** (mặc định 3), mỗi lần thay đổi tham số sinh
     (seed / tốc độ đọc trong phạm vi giọng cố định). Vẫn không đạt → trạng thái **"Audio không đạt"**,
     loại khỏi Khối 2, vẫn có trong báo cáo.
4. Có thể xuất kết quả Khối 1 riêng ra xlsx/csv (text gốc, text STT tham chiếu, WER, CER, số lần sinh, trạng thái).

### 5.3 Luồng Khối 2 (mỗi câu đã đạt verify)

Một điện thoại mỗi lần, chọn ở thanh trái.

1. Tap nút **voice** (vị trí đã ghim trong Hồ sơ app).
2. Chờ độ trễ khởi động mic (cấu hình, mặc định ~0.5s), phát WAV qua loa máy tính.
3. Hết audio + chờ thêm **X giây** (cấu hình, mặc định ~1s) → tap nút **voice** lần hai để dừng.
4. Chờ form mới xuất hiện (timeout cấu hình) → đọc text ô **"Công việc hôm nay"**:
   - Ưu tiên: `adb shell uiautomator dump` (có sẵn trong Android, không cài gì) lấy cây giao diện,
     tìm phần tử theo nhãn "Công việc hôm nay" rồi lấy ô nhập/text gần nhất (anh em/kế tiếp) —
     selector cấu hình được trong Hồ sơ app. Dump mất ~1–2s và có thể lỗi khi màn hình đang
     chuyển động → thử lại vài lần.
   - Nếu app viết bằng Flutter/WebView khiến dump không có text, OCR trở thành cách chính;
     việc kiểm tra app thuộc loại nào là bước đầu tiên của Khối 2 khi có máy.
   - Dự phòng: OCR vùng màn hình đã ghim (chỉ khi dump không ra text) — ghi chú rõ "đọc bằng OCR"
     trong kết quả vì độ tin cậy thấp hơn.
5. Tap **Hủy / Back** để quay về màn hình có nút voice. Kiểm tra đã về đúng màn hình trước câu tiếp.
6. So sánh text app với text gốc (5.4), ghi kết quả ngay vào SQLite.

Lỗi thao tác (không thấy form, không đọc được text, không về được màn hình chính) → đánh dấu
**"Lỗi thao tác"** (không tính là app nhận sai), thử khôi phục (Back nhiều lần / mở lại app) rồi chạy câu tiếp.

**Hồ sơ app** (lưu thành file JSON, có thể có nhiều hồ sơ): package name, vị trí/selector nút voice,
selector ô kết quả, nút Hủy/Back, các độ trễ. Người dùng tạo bằng cách click trên màn hình mirror
ở cột phải ("ghim").

### 5.4 So sánh text

Dùng chung một hàm cho Khối 1 và Khối 2 (để tránh sai lệch giữa hai khối):

1. Chuẩn hóa: Unicode NFC; chữ thường; bỏ dấu câu; gộp khoảng trắng; số → chữ tiếng Việt
   (`25` → `hai mươi lăm`); giữ nguyên dấu thanh tiếng Việt.
   Theo file mẫu, bản đầu phải xử lý: số + đơn vị (`24 độ` = `hai mươi tư độ`),
   phần trăm (`20%` = `20 phần trăm` = `hai mươi phần trăm`), giờ (`9h` = `9 giờ` = `chín giờ`).
   Bộ chuẩn hóa là một **bảng luật mở rộng được** (luật + bảng từ tương đương, ví dụ
   `SĐT` = `số điện thoại`, cách viết từ tiếng Anh như `ionizer`, `ADAS`), có test riêng.
   Lưu ý: câu chứa từ tiếng Anh dễ rớt verify ở Khối 1 — báo cáo cần cho thấy rõ.
2. Tính **WER** và **CER** bằng `jiwer`; liệt kê từ thay thế / thiếu / thừa.
3. **Đúng** khi WER = 0 sau chuẩn hóa. Báo cáo vẫn giữ WER/CER để biết sai nhiều hay ít.

Text gốc và text nhận dạng thô (chưa chuẩn hóa) đều được lưu.

### 5.5 Giao diện

```
┌──────────────┬──────────────────────────────────────┬─────────────┐
│ ▸ Dữ liệu    │ [Nạp file] [Sinh audio] [Verify]     │  ┌───────┐  │
│ ▸ Sinh audio │ [Chạy trên app] [Dừng]  [Xuất Excel] │  │ màn   │  │
│ ▸ Verify     │──────────────────────────────────────│  │ hình  │  │
│ ▸ Test app   │ # │Text gốc│▶│Verify│Text app│WER│KQ  │  │ điện  │  │
│ ▸ Báo cáo    │ 1 │Họp 9h  │▶│ ✔ 0% │Họp 9h  │0% │✔   │  │ thoại │  │
│──────────────│ 2 │Gọi anh…│▶│ ✘ 2x │   —    │ — │bỏ  │  │(live) │  │
│ Thiết bị: ●  │ 3 │Mua sữa │▶│ ✔ 0% │Mua sửa │50%│✘   │  └───────┘  │
│ Hồ sơ app    │                                      │ [ghim nút]  │
│ Cài đặt      │ Tiến độ: 1240/3000 ▓▓▓▓░░░  Đúng 87% │ log thao tác│
└──────────────┴──────────────────────────────────────┴─────────────┘
```

- **Trái:** các bước (Dữ liệu, Sinh audio, Verify, Test app, Báo cáo), trạng thái thiết bị,
  Hồ sơ app, Cài đặt (giọng, N lần sinh lại, ngưỡng WER, độ trễ).
- **Giữa:** bảng dữ liệu (cuộn ảo, chịu được hàng nghìn dòng): lọc theo trạng thái, nút ▶ nghe audio,
  tô màu từ sai; thanh tiến độ và tỉ lệ đúng cập nhật trực tiếp qua WebSocket.
- **Phải:** màn hình điện thoại live (scrcpy-server → H.264 → WebCodecs trong trình duyệt).
  scrcpy không cài app: nó đẩy tạm một file `.jar` vào `/data/local/tmp` qua ADB và xóa khi ngắt.
  Nếu chính sách máy công ty không cho cả việc này, tự chuyển sang chế độ ảnh chụp
  (`adb exec-out screencap`, ~1–2 hình/giây) — vẫn đủ để ghim nút và theo dõi.
  Chế độ ghim nút (click lên hình → tool ghi vị trí/phần tử UI tương ứng), log thao tác thời gian thực.
  Chỉ cần xem + click để ghim; không cần điều khiển điện thoại đầy đủ từ trình duyệt.

### 5.6 Chạy dài & khôi phục

- Dữ liệu tách 2 tầng: **Bộ audio** (kết quả Khối 1 của một file input + giọng) và **Lần test app**
  (Khối 2 trên một máy/phiên bản app). Một bộ audio đã verify dùng lại được cho nhiều lần test app
  (máy khác, bản app mới, chạy lại riêng các câu "Lỗi thao tác").
- Mỗi câu có trạng thái theo từng bước, lưu trong SQLite.
- Dừng/tắt giữa chừng → mở lại có thể **tiếp tục** từ câu chưa xong. Audio đã sinh được tái dùng.
- Một job nặng chạy mỗi lúc (GPU và loa chỉ có một).

### 5.7 Báo cáo Excel

Một file .xlsx nhiều sheet:
- **Tổng quan:** thông tin run (file input, giọng, thiết bị, hồ sơ app, thời gian), số câu,
  số audio không đạt, số lỗi thao tác, **tỉ lệ đúng của app** (trên các câu test hợp lệ),
  WER/CER trung bình. **Tỉ lệ audio bị loại** hiển thị nổi bật; vượt ngưỡng (mặc định 10%,
  chỉnh được) thì tô đỏ và cảnh báo rằng kết quả có thể không đại diện cho toàn bộ file input.
- **Khối 1 – Verify:** từng câu: text gốc, text STT tham chiếu, WER, CER, số lần sinh, trạng thái.
- **Khối 2 – App:** từng câu: text gốc, text app, WER, CER, từ sai, Đúng/Sai, cách đọc (UI/OCR), thời gian.
- **Audio không đạt**, **Lỗi thao tác** và **Không áp dụng** (dòng bị tự loại, kèm lý do): danh sách riêng.
- Tổng quan có thêm bảng **tỉ lệ đúng theo từng sheet tính năng**.
- Các cột định danh của file input (sheet, TC_ID, cụm tính năng, mức ưu tiên, lượt) được giữ kèm theo.
- **Không ghi ngược vào file testcase gốc** (người dùng chọn chỉ xuất báo cáo riêng).

## 6. Để người build quyết định

- Thư viện cụ thể cho frontend (framework, bảng cuộn ảo), cách giải mã stream scrcpy.
- Thư viện chuyển số → chữ tiếng Việt, thư viện OCR dự phòng.
- Cấu trúc thư mục, schema SQLite, định dạng file hồ sơ app.
- Thư viện phát audio trên Windows.

## 7. Các quyết định Claude tự đưa ra (người dùng chưa xác nhận riêng)

- Đọc form testcase 36 cột theo mẫu cố định; ánh xạ cột thủ công chỉ cho file khác form.
- Mỗi lượt hội thoại là một câu test độc lập.
- Danh sách quy tắc tự loại dòng (ngoặc, ký tự lạ, "…", "→", dòng Hệ thống).
- Chạy wyoming bằng Python trực tiếp, Docker là dự phòng; spike Windows trước tiên.
- Câu "Lỗi thao tác" không tính vào tỉ lệ đúng/sai của app.
- Chế độ ghim nút bằng click trên màn hình mirror; hồ sơ app lưu JSON.
- Mặc định: sinh lại tối đa 3 lần; chờ 0.5s trước khi phát, 1s sau khi hết audio.
- Khi sinh lại, thay đổi seed/tốc độ đọc trong cùng một giọng.
- Vì máy bị khóa: chỉ dùng công cụ có sẵn của Android (uiautomator dump, input tap, screencap);
  scrcpy là tùy chọn, tự rơi về chế độ ảnh chụp nếu không chạy được.
- Tách "Bộ audio" và "Lần test app" để tái dùng audio đã verify.
- Tỉ lệ audio bị loại hiển thị nổi bật, cảnh báo khi > 10%.
- Bộ chuẩn hóa dạng bảng luật mở rộng được, hoàn thiện khi có file input thật.
