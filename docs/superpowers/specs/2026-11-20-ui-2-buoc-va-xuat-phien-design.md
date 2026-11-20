# UI 2 bước, chọn case, theme sáng/tối, xuất phiên test — Thiết kế

Ngày: 2026-11-20 · Trạng thái: đã duyệt · Nền: [thiết kế gốc](2026-11-20-tts-stt-automation-design.md)

## 1. Mục đích

Tool đã chạy được Khối 1 (sinh audio + verify) và Khối 2 (test app trên điện thoại). Thay đổi này làm cho
luồng làm việc rõ ràng hơn và tạo ra bằng chứng test dùng được ngay:

- Giao diện chỉ còn **2 bước** theo đúng thứ tự người dùng làm: Bước 1 Audio, Bước 2 Test app.
- Người dùng **chọn được case** để chạy thay vì luôn phải chạy cả bộ.
- **Sinh audio và Verify tách thành 2 thao tác riêng**; audio không đạt thì người dùng tự quyết sinh lại.
- Sau mỗi phiên test app, xuất được **Excel theo form testcase tính năng** và **một file zip theo phiên**,
  mỗi testcase một folder chứa mọi thứ liên quan, case sai có ảnh chụp màn hình.
- Theme sáng / tối cho toàn bộ UI.

## 2. Mục tiêu / Không làm / Thất bại nếu

**Mục tiêu**
- Sidebar trái: Bước 1, Bước 2, danh sách Bộ audio, trạng thái (ADB + tên máy, wyoming, GPU), Cài đặt, nút theme.
- Bước 1: Nạp file → Sinh audio → Verify → (Sinh lại) → xem bảng / xuất Excel Khối 1 như hiện tại.
- Bước 2: chạy app trên case chọn hoặc tất cả → xuất Excel theo form → xuất zip phiên.

**Không làm**
- Không điền ngược vào file testcase gốc, không lấy file gốc làm khuôn (người dùng chọn hướng B, §4).
- Không đo độ trễ (cột Q) và không chấm Wake/NLU/Hành động/Phản hồi (R, T, U, V, W) — tool chỉ đo ASR.
- Không tự sinh lại khi verify sai (bỏ vòng lặp sinh lại tự động hiện có).

**Thất bại dù vẫn chạy được nếu**
- Ảnh chụp không phải màn hình lúc case sai (ví dụ chụp sau khi đã Back).
- Folder trong zip không tìm lại được dòng tương ứng trong Excel (và ngược lại).
- Kết quả trong Excel/zip khác kết quả trên bảng (phải lấy cùng một nguồn: SQLite của phiên).
- Zip phiên vài nghìn câu làm treo backend hoặc hết RAM.

## 3. Ràng buộc

- Giữ stack hiện có: FastAPI + SQLite + React/Vite, một job nặng mỗi lúc (`jobs/runner.py`).
- Form testcase 36 cột, header dòng 4, nhóm cột dòng 3 (THÔNG TIN CHUNG A, ĐẦU VÀO J, MONG ĐỢI N, THỰC TẾ P,
  ĐÁNH GIÁ THEO TẦNG R, THEO DÕI Y, LANGFUSE AE). Màu header: xanh `DDEBF7` (người thiết kế điền),
  vàng `FFF2CC` (tester điền), xám `D9D9D9` (tự tính).
- Hiện DB chỉ lưu một phần cột của form (sheet, tc_id, turn, feature, priority, region, speaker, expected,
  text_raw, source_row) và **không** lưu liên kết tới file đã tải lên.
- Ảnh chụp: `adb exec-out screencap` (~0.5–1 s/lần, đã có `Adb.screencap`, có khóa chống chụp song song).
- WAV ~48 kHz: 4.000 câu ≈ 1 GB.

## 4. Các hướng đã cân nhắc (xuất Excel theo form)

| Hướng | Mô tả | Đánh đổi |
|---|---|---|
| A. Điền vào bản sao file gốc | Mở file `.xlsx` gốc, điền cột THỰC TẾ vào đúng dòng | Giữ màu, sheet "Tổng hợp" và công thức; cần lưu liên kết tới file gốc; openpyxl làm rơi ảnh/biểu đồ nhúng. |
| **B. Dựng file mới theo form** ✅ | File mới cùng 36 cột / header như form, chỉ chứa case đã test | Gọn, không phụ thuộc file gốc; không có sheet "Tổng hợp" gốc, định dạng do tool dựng lại. |

**Người dùng chọn B.**

Các phần khác chỉ có một cách hợp lý trong code hiện tại: ảnh chụp/log lưu ngay khi chạy, zip dựng lúc bấm xuất;
chọn case giữ ở giao diện và gửi danh sách `item_ids` xuống API.

## 5. Thiết kế

### 5.1 Bố cục và theme

```
┌─────────────┬────────────────────────────────────────────────────────┐
│ ① Bước 1    │ [Nạp file] [Sinh audio] [Verify] [Sinh lại] │ [Excel]  │
│   Audio     │  ↳ chạy trên 12 case đã chọn (bỏ chọn = tất cả)        │
│ ② Bước 2    │ ☐ │TC_ID│Câu nói    │▶│STT tham chiếu│WER│Trạng thái   │
│   Test app  │ ☑ │TC01 │Bật điều hòa│▶│bật điều hòa │0% │Đạt          │
│             │ ☑ │TC02 │Mở cửa sổ   │▶│mở cửa số    │25%│Không đạt ⟳  │
│ Bộ audio …  │ ☐ │TC03 │Tắt đèn     │·│—            │ — │Chờ          │
│ ADB ● máy…  │ Tiến độ ▓▓▓░░ 40/120 · Đạt 87% · Loại 13%              │
│ ☀/☾ · Cài đặt│                                                       │
└─────────────┴────────────────────────────────────────────────────────┘
```

- Sidebar chỉ có 2 mục điều hướng **Bước 1 — Audio** và **Bước 2 — Test app** (bỏ "Dữ liệu", "Báo cáo" — các nút đó
  chuyển vào thanh công cụ của từng bước). Giữ danh sách Bộ audio, khối trạng thái (ADB + tên máy từ commit
  `f3c3878`, wyoming, GPU), Cài đặt.
- Bước 2 khóa (disabled, có gợi ý) khi bộ audio chưa có câu nào "Đạt".
- Cột phải (màn hình điện thoại, ghim nút, log) **chỉ hiện ở Bước 2**; Bước 1 bảng chiếm phần đó.
- Trạng thái rỗng (chưa có bộ audio): chỉ có ô "Nạp file testcase (.xlsx / .csv) để bắt đầu" + nút Nạp file (đã có).
- **Theme:** nút chọn Sáng / Tối / Theo hệ thống ở chân sidebar. CSS đã dùng biến màu (`styles.css :root`) và
  khối `prefers-color-scheme: dark`; thêm `:root[data-theme="dark"]` / `[data-theme="light"]` để ép theme, nhớ
  lựa chọn trong `localStorage`. Rà các màu viết cứng còn lại (~38 mã hex trong `styles.css`) sang biến.

### 5.2 Chọn case (dùng chung cho cả 2 bước)

- Bảng có cột checkbox; ô checkbox ở header chọn / bỏ chọn **toàn bộ các dòng đang hiển thị theo bộ lọc**
  (lọc trạng thái + ô tìm kiếm). Shift+click chọn một dải.
- Thanh công cụ hiện "Đang chọn N case · Bỏ chọn". **Không chọn gì = các nút chạy áp dụng cho tất cả** (nhãn nút
  đổi theo: "Sinh audio (tất cả)" / "Sinh audio (12)").
- Lựa chọn tách riêng cho mỗi bước và xóa khi đổi bộ audio. Dòng bị loại ("Không áp dụng", tắt) không chọn được.
- API nhận `item_ids: list[int] | None` (None = tất cả các câu hợp lệ của thao tác đó).

### 5.3 Bước 1: Sinh audio, Verify, Sinh lại

Trạng thái câu: **Chờ → Đã sinh audio → Đạt / Audio không đạt**, cùng "Lỗi" và "Không áp dụng" như hiện tại.

| Thao tác | Áp dụng cho | Kết quả |
|---|---|---|
| **Sinh audio** | câu chọn (hoặc tất cả) **chưa có audio** (Chờ, Lỗi khi sinh) | Sinh WAV với lần sinh hiện tại → "Đã sinh audio". Câu đã có audio bị bỏ qua. |
| **Verify** | câu chọn có audio; "tất cả" = các câu "Đã sinh audio" | Gửi wyoming, so sánh (§5.4 thiết kế gốc) → "Đạt" hoặc "Audio không đạt". **Không tự sinh lại.** Chọn tay một câu đã Đạt/Không đạt rồi bấm Verify = verify lại. |
| **Sinh lại** | câu chọn có audio (thường là "Audio không đạt"); nút ⟳ trên từng dòng | Sinh WAV mới với **lần sinh kế tiếp** (`attempts + 1` → seed/tham số khác, khóa cache khác) → "Đã sinh audio", xóa kết quả verify cũ. Người dùng verify lại sau. |

- Câu "Lỗi" được xếp theo có/không có audio: chưa có audio → thuộc Sinh audio; đã có audio (lỗi STT) → thuộc Verify.
- Ba thao tác là 3 job riêng (một job mỗi lúc), dừng được; bấm lại thì làm tiếp phần chưa xong.
- Wyoming chỉ được khởi động / kiểm tra ở job Verify.
- Dừng sau 3 lỗi STT liên tiếp (giữ hành vi hiện có) ở Verify; lỗi TTS từng câu → "Lỗi", chạy tiếp.
- Sửa câu đọc trên bảng vẫn đưa câu về "Chờ" và xóa audio (giữ hành vi `_RESET_SQL`).
- Cài đặt "số lần sinh lại tối đa" (`max_regen`) không còn dùng cho vòng lặp tự động; ẩn khỏi Cài đặt.
- Xuất Excel / CSV Khối 1 giữ nguyên như hiện tại (cột "Số lần sinh" = `attempts`).

### 5.4 Bước 2: Phiên test app

- **Mỗi lần bấm "Chạy" tạo một phiên mới** (bảng `app_runs` hiện có) chỉ gồm các câu đã chọn (hoặc tất cả câu
  "Đạt"). Phiên dừng giữa chừng → nút **Tiếp tục** (đã có). Danh sách phiên để xem lại phiên cũ giữ nguyên
  (`AppRunPanel`).
- Bảng ở Bước 2 chỉ hiện câu "Đạt" (như hiện tại) cùng cột kết quả app của phiên đang chọn.
- **Ảnh chụp màn hình tại thời điểm lỗi** (sửa `pipeline/block2.py`):
  - Case **Sai**: trong `run_one`, sau khi đọc được text app (hoặc hết thời gian chờ) và **trước** khi Back đóng
    bảng, so sánh với câu gốc; nếu sai thì `screencap`. Vì vậy `run_one` cần biết câu gốc + hàm so sánh
    (ví dụ truyền vào một hàm `is_correct(text) -> bool`). Case đúng không chụp (tránh +0.5–1 s × hàng nghìn câu).
  - Case **Lỗi thao tác**: chụp ngay trong nhánh xử lý lỗi, trước khi khôi phục (Back / mở lại app).
  - Lỗi khi chụp không được làm hỏng kết quả của câu: ghi log "Không chụp được màn hình" và chạy tiếp.
- Mỗi phiên có thư mục `data/app_runs/<run_id>/`; ảnh lưu `<result_id>.png`. Thêm cột `screenshot_path` vào
  `app_results` (migration nhẹ như cách `text_tts_snap` đã được thêm). Log thao tác đã lưu ở cột `log`.

### 5.5 Xuất Excel theo form (hướng B)

**Lưu đủ cột lúc nạp file:** khi nạp form testcase, lưu toàn bộ 36 ô của dòng (A..AJ) vào cột mới `form_json`
của `items`, để Excel xuất ra có đủ cột C, D, F, G, J, K, O… Bộ audio nạp trước thay đổi này không có
`form_json` → các cột không có trong DB để trống. File csv / xlsx không đúng form: chỉ có TC_ID (nếu ánh xạ) và
Câu nói.

**Cấu trúc file `KetQua_<tên bộ audio>_Phien<id>.xlsx`:**
- Mỗi sheet tính năng có case trong phiên → một sheet cùng tên (≤31 ký tự, giữ tên sheet gốc).
- Dòng 1: tiêu đề "<tên bộ audio> · Phiên #id — kết quả test ASR tự động"; dòng 2: chú thích màu cột như form;
  dòng 3: nhóm cột (gộp ô như form); **dòng 4: header 36 cột đúng tên và thứ tự form**; dữ liệu từ dòng 5.
- Tô màu header theo nhóm như form (xanh / vàng / xám), đóng băng 4 dòng đầu, bật lọc.
- Chỉ các dòng (lượt) có trong phiên, theo thứ tự dòng gốc (`source_row`).
- Bộ audio từ file csv (không có sheet): dùng một sheet tên "Dữ liệu"; trong zip folder sheet cũng tên "Dữ liệu".
- Thêm một sheet đầu **"Tổng hợp phiên"**: thông tin phiên (bộ audio, file nguồn, máy, hồ sơ app, phiên bản app,
  thời gian), số câu Đúng / Sai / Lỗi thao tác / Chưa chạy, tỉ lệ đúng tổng và theo từng sheet (tái dùng logic
  `_app_overview` trong `report/excel.py`).

**Các cột tool điền (nhóm THỰC TẾ / ĐÁNH GIÁ / THEO DÕI):**

| Cột | Nội dung |
|---|---|
| P Kết quả thực tế | Câu app nghe được (thô). Lỗi thao tác: "Lỗi thao tác: <thông báo>". App không trả câu: "(app không trả câu)". |
| S KQ ASR | `Pass` (Đúng) / `Fail` (Sai) / để trống (Lỗi thao tác, Chưa chạy). |
| X KẾT QUẢ TỔNG | `Fail` khi ASR Sai (nghe sai chữ thì cả lượt chắc chắn thất bại); để trống khi ASR Đúng / Lỗi thao tác / Chưa chạy — tester tự kết luận sau khi xem các tầng khác. |
| Z Bằng chứng | Đường dẫn tương đối tới folder của case trong zip, ví dụ `Ionizer via voice command/FAIL_TC-ON-002/`. |
| AA Thông tin lần chạy | `Phiên #12 · <model máy> · <hồ sơ app> v<phiên bản> · 2026-11-20 15:30` |
| AB Ghi chú | Giữ ghi chú gốc, nối thêm `WER 25% · CER 8% · sai: cửa sổ→cửa số` (và câu đã đọc nếu khác câu gốc do bỏ "Hey Vita" / sửa tay). |
| Q, R, T, U, V, W, Y, AC–AJ | Để trống. |

Nút **Xuất Excel** ở Bước 2 tải riêng file này cho phiên đang chọn.

### 5.6 Xuất zip phiên

Nút **Xuất zip phiên** ở Bước 2 (phiên đang chọn) mở hộp thoại nhỏ chọn **audio kèm theo**:
- (mặc định) **Chỉ case Sai / Lỗi thao tác**
- **Tất cả** (cảnh báo dung lượng ước tính, ví dụ "~1,1 GB")
- **Các case đang chọn** trên bảng Bước 2

Ảnh chụp, kết quả, log luôn có cho mọi case; tùy chọn chỉ ảnh hưởng tới file WAV.

```
Phien12_2026-11-20_1530_<model máy>.zip
└── Phien12_2026-11-20_1530_<model máy>/
    ├── KetQua_<bộ audio>_Phien12.xlsx   ← file §5.5
    ├── TongQuan.xlsx                    ← báo cáo nhiều sheet hiện có (Khối 1 + Khối 2 của phiên)
    ├── thong_tin_phien.txt              ← máy, serial, hồ sơ app (JSON), phiên bản app, giọng, ngưỡng WER,
    │                                      giờ bắt đầu/kết thúc, số câu theo trạng thái, tùy chọn audio đã chọn
    └── <Tên sheet>/
        ├── FAIL_TC-ON-002/
        │   ├── luot1_ketqua.txt   ← TC_ID, lượt, câu gốc, câu đã đọc, câu app nghe, Đúng/Sai, WER, CER, từ sai, thời gian
        │   ├── luot1_log.txt      ← log thao tác của tool cho câu này
        │   ├── luot1_manhinh.png  ← chỉ khi Sai / Lỗi thao tác
        │   └── luot1_audio.wav    ← theo tùy chọn audio
        ├── LOI_TC-ON-007/ …
        └── PASS_TC-ON-001/ …
```

- Folder theo **TC_ID**, các lượt hội thoại trong cùng folder, file đánh số `luot<n>_`.
- Tiền tố folder theo kết quả xấu nhất trong các lượt: `FAIL_` (có lượt Sai) > `LOI_` (có lượt Lỗi thao tác)
  > `CHUA_` (còn lượt chưa chạy) > `PASS_`. Tiền tố làm case sai nổi lên đầu khi sắp xếp theo tên.
- Tên folder/file được làm sạch ký tự Windows không cho phép; TC_ID trùng trong cùng sheet → thêm hậu tố `_2`.
- File `.txt` ghi UTF-8 có BOM để Notepad hiển thị đúng tiếng Việt.
- Dựng zip ra file tạm trên đĩa (không giữ cả zip trong RAM), WAV/PNG dùng `ZIP_STORED`, txt/xlsx nén;
  trả về bằng `FileResponse`, xóa file tạm sau khi gửi.

## 6. Để người build quyết định

- Tách `App.tsx` thành các view Bước 1 / Bước 2 và cách giữ state chọn case.
- Tên endpoint cụ thể (ví dụ `POST /audio-sets/{id}/generate|verify|regenerate`, `POST /app-runs/{id}/export-zip`),
  dạng tham số.
- Dựng zip đồng bộ trong thread hay thành job có tiến độ (nên làm job nếu đo thấy > vài giây với 4.000 câu).
- Kiểu hiển thị nút theme (một nút xoay vòng hay 3 lựa chọn).
- Test cho từng phần theo cách các test hiện có đang làm (pytest backend, vitest frontend).

## 7. Quyết định của người dùng

- Tách Sinh audio / Verify; verify sai không tự sinh lại, có nút Sinh lại.
- Có chọn case cho cả 2 bước.
- Excel theo form: hướng B (dựng file mới theo form).
- Zip: folder theo TC_ID, các lượt chung một folder; ảnh chụp khi sai; audio mặc định chỉ case sai, tùy chọn tất cả / các case đang chọn.
- Cột X: chỉ điền `Fail` khi ASR sai, còn lại để trống.

Trạng thái doc: **đã duyệt** (2026-11-20).

## 8. Các quyết định Claude tự đưa ra (người dùng chưa xác nhận riêng)

- Sinh audio bỏ qua câu đã có audio; Verify "tất cả" chỉ lấy câu "Đã sinh audio", chọn tay = verify lại được.
- Sinh lại dùng lần sinh kế tiếp (seed/tham số khác), không giới hạn số lần; ẩn `max_regen` khỏi Cài đặt.
- Mỗi lần "Chạy" ở Bước 2 là một phiên mới gồm đúng các case đã chọn.
- Bước 2 khóa khi chưa có câu "Đạt"; cột điện thoại chỉ hiện ở Bước 2.
- Chọn ở header = chọn các dòng đang hiển thị theo bộ lọc; Shift+click chọn dải.
- Chụp màn hình cả khi Lỗi thao tác; không chụp case đúng.
- Lưu đủ 36 cột của form lúc nạp (`form_json`) để Excel xuất ra đầy đủ.
- Bố cục file Excel theo form, giá trị `Pass`/`Fail` ở cột S, nội dung cột P/Z/AA/AB như bảng §5.5.
- Cấu trúc zip, tiền tố `FAIL_/LOI_/CHUA_/PASS_`, file `.txt` UTF-8 BOM, `thong_tin_phien.txt`.
- "Các case đang chọn" trong tùy chọn audio = đúng các case đang chọn, không tự cộng thêm case sai.
