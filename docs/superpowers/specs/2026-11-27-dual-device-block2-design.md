# Khối 2 chạy song song 2 thiết bị — thiết kế

Ngày: 2026-11-27 · Nhánh: `ios`

## Mục đích

Giảm thời gian chạy test Khối 2: cắm 2 máy (thường là 1 Android + 1 iPhone), bấm chạy một lần, mỗi câu
được phát từ loa PC **một lần duy nhất** và cả hai máy cùng nghe. Mỗi máy vẫn là một lần test độc lập
(log, ảnh lỗi, WER, Excel riêng).

## Mục tiêu

- Một lần bấm chạy tạo 2 lần test (`app_runs`), một cho mỗi máy, cùng bộ audio, cùng danh sách câu,
  cùng hồ sơ app, cùng ngưỡng WER khởi tạo.
- Mỗi câu: cả hai máy cùng mở mic → phát WAV một lần → mỗi máy tự đọc kết quả.
- Excel / ZIP / báo cáo xuất riêng từng lần test như hiện nay (không có file gộp).
- Giao diện: khi đang xem một cặp lần test, có nút chuyển qua lại giữa màn của 2 máy (kết quả, log,
  KPI, màn hình máy).
- Chạy 1 máy giữ nguyên như hiện nay.

## Không làm

- Không có Excel gộp / so sánh hai máy cạnh nhau.
- Không hỗ trợ hơn 2 máy.
- Không đổi Khối 1.

## Anti-goal (coi như thất bại dù chạy được)

- Âm thanh phát chồng (hai lần phát cùng lúc) hoặc một máy nghe câu khi mic chưa bật / đã tự tắt.
- Một máy lỗi làm kết quả của máy kia bị ghi sai (sai câu, sai lần test).
- Chạy 1 máy chậm hơn hoặc hành vi khác đi ngoài thay đổi nêu ở "Thử lại lỗi thao tác".

## Ràng buộc

- Phát âm thanh chỉ có một loa (`AudioPlayer.play` chặn tới khi phát xong) → không thể phát đồng thời 2 file.
- App tự dừng nghe sau ~3 s im lặng → máy chuẩn bị xong trước không được giữ mic mở chờ quá lâu.
- Android biết mic bật qua `dumpsys` (~0,1 s); iPhone phải chờ thấy nút "Dừng nghe" qua UI dump → iPhone chậm hơn.
- App không phát tiếng trợ lý → không có nhiễu âm thanh chéo giữa hai máy.
- **Phát triển/kiểm thử chỉ dùng loa giả + máy giả** (`tests/pipeline/fake_app.py`); không phát ra loa,
  không gửi lệnh tới máy thật khi chưa hỏi người dùng.

## Các cách đã cân nhắc

- **A. Một job điều phối cả hai máy theo từng câu (đã chọn).** Tách `_run_one` thành 3 pha (chuẩn bị /
  phát / đọc kết quả); một vòng lặp chạy các pha song song cho các máy cần chạy câu đó. Mọi luật (chờ,
  thử lại, dừng) nằm một chỗ, test được bằng máy giả. Chạy 1 máy là trường hợp danh sách có 1 máy.
- B. Hai job riêng + loa dùng chung có điểm hẹn. Ít sửa vòng lặp nhưng máy đi trước sẽ mở mic ở câu sau
  khi máy kia đang thử lại → mic tự tắt; luật "dừng cả hai" phải đồng bộ qua hai job. Bỏ.
- C. Phát luân phiên cho từng máy. Không tiết kiệm thời gian — trái mục đích. Bỏ.

## Thiết kế

### 1. Pipeline: 3 pha cho một câu (`pipeline/block2.py`)

Tách `_run_one` hiện tại thành:

1. `prepare(dev, p, log, sleep)` — `ensure_home`, bấm nút mic, `_wait_mic`, `pre_delay_s`. Lỗi → `OperationError`.
2. Phát: với **mỗi** máy đang chạy câu này, tạo task baseline `dev.nodes()`; rồi `player.play(wav)` **một lần**;
   rồi chờ các baseline. (Giữ nguyên ý nghĩa baseline hiện tại: dump lấy trong lúc app đang nghe.)
3. `read_result(dev, p, base, log, sleep, is_correct)` — phần còn lại của `_run_one` (kiểm tra sheet mở,
   `post_delay_s`, bấm dừng, poll kết quả, chờ form iOS, chụp ảnh nếu sai, Back, bỏ form) → `AppCapture`.

`run_one` (1 máy) giữ chữ ký cũ và gọi 3 pha nối tiếp, để test cũ và đường chạy 1 máy không đổi.

Lỗi của một máy ở bất kỳ pha nào chỉ ảnh hưởng máy đó: dùng `asyncio.gather(..., return_exceptions=True)`
và gắn log của máy đó vào lỗi như hiện nay (`e.log`).

**Lệch thời gian chuẩn bị:** máy chuẩn bị nhanh không được giữ mic mở quá lâu trước khi phát.
Yêu cầu: thời gian từ lúc mic của một máy bật tới lúc bắt đầu phát ≤ ~1,5 s trong trường hợp bình thường.
Cách làm (người viết code chọn chi tiết): đo thời gian `prepare` của từng máy ở câu trước, cho máy nhanh
bắt đầu `prepare` trễ hơn đúng khoảng chênh đó (câu đầu: không trễ). Ngay trước khi phát, nếu máy báo
được trạng thái mic (`mic_active()` không phải `None`) và mic đã tắt → coi máy đó lỗi thao tác ở lượt này
(đi theo luật thử lại bên dưới), không phát cho nó.

### 2. Vòng lặp nhiều máy và luật thử lại

Hàm mới `run_block2_multi(store, lanes, player, settings, emit, cancel, ...)`, mỗi `lane` = (lần test, driver,
hồ sơ, thư mục ảnh). `run_block2` hiện tại trở thành `run_block2_multi` với 1 lane.

- Hai lần test có cùng danh sách câu chờ chạy theo thứ tự `item_id` khi bắt đầu cặp. Khi tiếp tục (resume)
  một cặp, mỗi lane chỉ chạy câu còn chờ/lỗi của nó; câu chỉ một lane cần thì lane kia đứng chờ.
- Mỗi câu, lượt đầu chạy cho tất cả lane còn cần câu đó.
- Sau mỗi lượt, mỗi lane có một trong: **xong** (có text hoặc hết lượt thử), **Chưa nghe rõ** (`not_heard`
  và không có text), **lỗi thao tác**.
- Lane cần thử lại: Chưa nghe rõ → tối đa `NOT_HEARD_RETRIES` (=1) lần; lỗi thao tác → tối đa 1 lần
  (hằng mới `OP_ERROR_RETRIES = 1`). Các lane cần thử lại chạy lượt tiếp **cùng nhau** (một lần phát);
  lane đã xong đứng yên ở màn hình chính, không thao tác. Nghỉ `RETRY_PAUSE_S` trước lượt thử lại.
- Log của các lượt được nối như hiện nay (`— Phát lại lần 2 —`; với lỗi thao tác: `— Thử lại sau lỗi thao tác —`).
- Ảnh lỗi thao tác chỉ chụp ở lượt cuối cùng còn lỗi (lượt thử lại thành công thì không chụp).
- Ghi kết quả + phát event cho từng lane ngay khi lane đó chốt câu.
- Ngưỡng WER đọc riêng theo từng lần test, mỗi câu đọc lại (như hiện nay) — người dùng có thể đổi ngưỡng
  của một máy giữa chừng.
- `between_delay_s` của hồ sơ: nghỉ giữa hai câu (dùng chung vì hai máy dùng một hồ sơ).
- **Đếm lỗi thao tác liên tiếp theo từng lane.** Lane nào chạm `MAX_CONSECUTIVE_OP_ERRORS` (=5) → **dừng cả
  hai**, event `error` nêu máy nào. Câu chưa chạy giữ trạng thái chờ để tiếp tục sau.
- Hủy (`cancel`): dừng cả hai như hiện nay.

Thay đổi hành vi chạy 1 máy (quyết định của Claude, để một đường code): lỗi thao tác cũng được thử lại 1 lần.

### 3. Dữ liệu (`store/db.py`)

- Thêm cột `pair_run_id INTEGER NULL` vào `app_runs` (migration kiểu `ALTER TABLE` như các cột trước), hai
  lần test trong cặp trỏ vào nhau. (Quyết định của Claude: cần để tiếp tục cặp đã dừng và để hiện nút chuyển
  màn sau khi tải lại trang.)
- `get_app_run` / danh sách lần test trả thêm `pair_run_id`.
- Xóa một lần test: lần còn lại đặt `pair_run_id = NULL`.

### 4. API (`api/routes.py`, `api/app.py`)

- `ctx.busy_serial: str | None` → `ctx.busy_serials: set[str]`; `_require_free` và `/device` (`busy` thành
  danh sách) theo đó. iOS disconnect kiểm tra trong tập.
- `POST /audio-sets/{set_id}/app-runs` nhận thêm `serial2: str | None`. Có `serial2` (khác `serial`) → tạo 2 lần
  test, nối `pair_run_id`, khởi một job lane `block2` chạy cả hai. Trả `{id, pair_id, job_id}`.
  Model/phiên bản app đọc riêng cho từng máy.
- `POST /app-runs/{run_id}/resume`: nếu lần test có cặp và cả hai máy đang kết nối → chạy cả hai; thiếu máy
  kia → chạy riêng máy này (chỉ cần máy của lần test đang cắm).
- `POST /app-runs/{run_id}/rerun`: như hiện nay, chỉ máy đang xem.
- `ProgressEvent` thêm `run_id: int | None`; mọi event `log`/`item` của Khối 2 mang `run_id` của lane. Event
  tổng (`done`, `cancelled`, `error`) không cần `run_id`.

### 5. Giao diện (`frontend/src`)

- `AppRunPanel`: khi có ≥ 2 máy sẵn sàng, ô chọn thiết bị có thêm lựa chọn **"Cả 2 máy"** (liệt kê tên hai máy).
  Nếu cắm > 2 máy: chọn "Cả 2 máy" mở thêm ô chọn máy thứ hai. Nút chạy ghi "Chạy trên 2 máy (…)".
- Khi lần test đang xem có `pair_run_id`: thanh trên cùng có **nút chuyển** dạng 2 tab
  `[ Android · Pixel 7 ] [ iPhone 13 ]`; bấm = đổi `appRunId` sang lần kia. Mọi thứ theo `appRunId` (bảng
  kết quả, KPI, ngưỡng WER, xuất Excel/ZIP, Chạy lại) tự đi theo.
- Log: giữ log theo `run_id` (`Map<runId, string[]>`); `DevicePanel` hiện log + màn hình của máy đang xem.
  Event không có `run_id` hiện ở cả hai.
- Bắt đầu một cặp → tự chọn lần test của máy đầu tiên.

```
┌ Khối 2 ─ #41 · Pixel 7 ───────────── [ Android · Pixel 7 ][ iPhone 13 ] ┐
│ 92% Đúng · 3 Sai · 1 Lỗi thao tác      [Xuất Excel] [ZIP] [Chạy lại]   │
```

## Kiểm thử

- Toàn bộ bằng máy giả và loa giả (đếm số lần `play`, ghi thời điểm). Không phát loa, không dùng máy thật.
- Pipeline: hai máy giả → mỗi câu `play` đúng 1 lần; một máy "Chưa nghe rõ" → chỉ máy đó chạy lượt 2,
  máy kia không có thao tác nào trong lượt 2; cả hai lỗi → thử lại cùng nhau, 1 lần phát; lỗi thao tác thử
  lại 1 lần rồi ghi `Lỗi thao tác`; một lane 5 lỗi liên tiếp → dừng cả hai; hủy → dừng cả hai; kết quả mỗi
  máy ghi đúng lần test; máy mic tắt trước khi phát → lỗi thao tác cho máy đó.
- Test 1 máy hiện có vẫn qua (trừ chỗ chủ ý đổi: lỗi thao tác thử lại 1 lần).
- API: tạo cặp, `busy` là danh sách, resume cặp / resume thiếu máy, rerun chỉ máy đang xem.
- Frontend: lựa chọn "Cả 2 máy", nút chuyển màn, log tách theo máy.

## Để người viết code quyết định

- Cách đo và áp độ trễ giữa hai máy (miễn đạt yêu cầu ở mục 1).
- Tên hàm/kiểu dữ liệu nội bộ, cách tổ chức state log ở frontend.
