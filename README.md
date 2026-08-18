# push-bctc

Pipeline xử lý báo cáo tài chính (BCTC) của các ngân hàng niêm yết và đẩy dữ liệu
lên Cloudflare D1.

## Tính năng chính

- Đọc nhiều file Excel BCTC (quý/năm/lũy kế) cho danh sách ngân hàng khai báo trong
  `src/config.py` (`TOPNH`, `TOPNHNN`, `TOPNHTM`).
- Chuẩn hoá tên cột tiếng Việt có dấu (`src/janitorvn.py`).
- Tự tính lũy kế theo quý (`gen_cumulative_data`), tổng hợp theo nhóm ngân hàng
  (`summarize_by_group`), tính cột trung bình phục vụ các chỉ số như ROA/ROE/NIM
  (`gen_average_columns`).
- Tính chỉ tiêu tài chính thứ cấp từ công thức khai báo trong `input_formulas.csv`
  (`gen_data_by_formula`), chạy song song bằng `ThreadPoolExecutor`.
- Xuất kết quả ra `output.xlsx` (nhiều sheet) và đẩy từng bảng lên Cloudflare D1
  (`src/d1_pusher.py`, dùng `npx wrangler d1 execute`).
- `src/data_validators.py` và `src/formula_validators.py` kiểm tra tính nhất quán
  của form BCTC và tính phù hợp của công thức trước khi chạy pipeline chính.

## Chiến lược nhánh: một nguồn dữ liệu = một nhánh

Dữ liệu thô BCTC có thể xuất từ hai nguồn khác nhau — **FiinX** hoặc **WiData** —
và hai nguồn này không chỉ khác tên cột mà có thể khác cả cấu trúc file (vị trí sheet,
cách đọc ngày xuất dữ liệu...). Vì phần khác biệt này khó gói gọn bằng một biến cấu
hình duy nhất, repo dùng 3 nhánh:

- **`main`** — nhánh gốc, chứa toàn bộ logic dùng chung (đọc file, tính toán, đẩy D1,
  validator...). Không tự chạy được pipeline vì `src/config.py` chỉ mang giá trị mặc
  định, chưa khớp nguồn dữ liệu cụ thể nào.
- **`fiinx`** — rẽ từ `main`, đã tinh chỉnh để khớp mẫu Excel do FiinX xuất.
- **`widata`** — rẽ từ `main`, đã tinh chỉnh để khớp mẫu Excel do WiData xuất.

Muốn chạy pipeline cho nguồn nào thì `git switch` sang đúng nhánh đó
(`git switch fiinx` hoặc `git switch widata`), mọi cấu hình đã sẵn sàng — không
cần sửa `config.py` thủ công mỗi lần chạy nữa.

### File khác nhau giữa các nhánh `fiinx` / `widata`

| File | Khác nhau ở đâu |
|---|---|
| `src/config.py` | `SHEETS` (tên tab Excel khớp nguồn) và `CUM_CONST` (rowid tiền mặt đầu/cuối kỳ, khoảng rowid thuyết minh) được tinh chỉnh riêng cho từng nguồn. |
| `input_formulas.csv.example` | Công thức mẫu tính chỉ tiêu, tham chiếu đúng rowid của nguồn dữ liệu trên nhánh đó. File này được commit riêng trên từng nhánh (không bị `.gitignore` vì không có đuôi `.csv`). |
| `input_formulas.csv` | Copy ra từ `input_formulas.csv.example` của nhánh hiện tại, dùng để chạy pipeline thật. File này bị `.gitignore` (xem `*.csv`) nên không commit, mỗi lần checkout nhánh khác phải tạo lại — xem mục Cách sử dụng. |
| `src/data_readers.py` | Có thể khác nhau nếu logic đọc file (`_read_file_data`, `_extract_export_date`) không dùng chung được giữa hai nguồn (khác vị trí ô ngày xuất dữ liệu, khác cách bố trí sheet...). Cần xác nhận thực tế khi làm việc với file mẫu của từng nguồn — nếu chỉ khác tên sheet thì không cần tách file này. |

### File giữ nguyên, dùng chung trên mọi nhánh

`main.py`, `src/data_wranglers.py`, `src/data_validators.py`,
`src/formula_validators.py`, `src/d1_pusher.py`, `src/janitorvn.py`,
`requirements.txt`, `.env.example`, `.gitignore`. Sửa các file này nên thực hiện
trên `main` rồi merge xuống `fiinx`/`widata`, để tránh hai nhánh bị trôi (drift)
so với nhau.

## Cấu trúc thư mục

- `main.py` — entry point, chạy toàn bộ pipeline từ đọc dữ liệu đến đẩy lên D1.
- `raw_data.py`, `to_sankey.py` — script phụ trợ để khám phá/kiểm tra dữ liệu.
- `src/config.py` — hằng số cấu hình (danh sách ngân hàng, tên sheet, `CUM_CONST`...),
  giá trị `SHEETS`/`CUM_CONST` khác nhau giữa nhánh `fiinx`/`widata` (xem trên).
- `src/data_readers.py` — đọc và pivot dữ liệu Excel thô.
- `src/data_wranglers.py` — các hàm biến đổi và tính toán dữ liệu.
- `src/janitorvn.py` — wrapper của `pyjanitor`, tinh chỉnh cho phù hợp với tiếng Việt.
- `src/d1_pusher.py` — đẩy DataFrame lên Cloudflare D1.
- `src/data_validators.py` — audit tính nhất quán cấu trúc form BCTC giữa các
  file/kỳ/công ty, sinh từ điển `data_dict.csv` (rowid <-> chi_tieu).
- `src/formula_validators.py` — đối chiếu rowid dùng trong `input_formulas.csv` với
  `data_dict.csv` để phát hiện công thức tham chiếu rowid không tồn tại.
- `data/data-quarterly`, `data/data-yearly`, `data/data-cumulative` — dữ liệu Excel
  BCTC đầu vào, mỗi file tương ứng một ngân hàng.
- `input_formulas.csv.example` — công thức mẫu cho nguồn dữ liệu của nhánh hiện tại,
  được commit trong git (khác nội dung giữa nhánh `fiinx`/`widata`, xem trên).

## Yêu cầu & cài đặt

- Python 3.13+
- Node.js + `npx wrangler` (Cloudflare Wrangler CLI) đã đăng nhập hoặc có API token,
  dùng để đẩy dữ liệu lên D1.

```bash
pip install -r requirements.txt
```

Sao chép `.env.example` thành `.env` và điền các biến môi trường:

```
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
D1_DATABASE=
```

## Cách sử dụng

1. Switch sang đúng nhánh của nguồn dữ liệu đang dùng: `git switch fiinx` hoặc
   `git switch widata`. `src/config.py` trên nhánh đó đã khớp sẵn với nguồn dữ liệu.
2. Đặt file Excel BCTC vào đúng thư mục `data/data-quarterly`, `data/data-yearly`
   hoặc `data/data-cumulative`, tên file phải chứa mã ngân hàng (ví dụ
   `Báo cáo tài chính VCB.xlsx`) vì `read_multiple_file` lọc file theo mã này.
   Đa phần các ngân hàng đều có BCTC theo quý và theo năm, riêng Agribank (AGRB)
   không có BCTC quý mà chỉ có BCTC lũy kế 6 tháng, đưa vào `data/data-cumulative`.
3. Sao chép `input_formulas.csv.example` của nhánh hiện tại thành `input_formulas.csv`
   (file này bị `.gitignore`, không tự có sẵn sau khi switch nhánh):

   ```bash
   cp input_formulas.csv.example input_formulas.csv
   ```
4. Chạy `python -m src.data_validators` để audit tính nhất quán cấu trúc form BCTC
   giữa các file/công ty (số dòng, tên `chi_tieu`, `rowid` có bị lệch giữa các kỳ
   không). Nếu không có lỗi cấu trúc (`chi_tieu_drift`, `row_count_diff`), lệnh này
   ghi ra `structure_audit_report.csv` và từ điển `data_dict.csv` (rowid <->
   chi_tieu). Nếu phát hiện lệch cấu trúc ở rowid dùng trong công thức tính, sẽ có
   cảnh báo riêng.
5. Nếu đây là lần đầu thiết lập nhánh cho nguồn dữ liệu này: dựa vào `data_dict.csv`
   vừa sinh ra, tinh chỉnh `CUM_CONST` trong `src/config.py` cho khớp rowid thực tế
   (rowid tiền mặt đầu kỳ/cuối kỳ trên sheet lưu chuyển tiền tệ, khoảng rowid tối đa
   của sheet thuyết minh) rồi commit lại trên nhánh đó — chỉ cần làm một lần, các lần
   chạy sau không cần lặp lại bước này.
6. Chạy `python -m src.formula_validators` để kiểm tra tính phù hợp của công thức
   trong `input_formulas.csv`: đối chiếu từng rowid được tham chiếu trong công thức
   với `data_dict.csv` để phát hiện rowid không tồn tại/không có định nghĩa, đồng
   thời xuất `formula_definitions.csv` liệt kê chi_tieu tương ứng của từng công thức
   để rà soát thủ công.
7. Chỉnh sửa thêm công thức tính chỉ tiêu trong `input_formulas.csv` nếu cần.
8. Chạy pipeline chính:

```bash
python main.py
```

Kết quả được ghi ra `output.xlsx` (mỗi chỉ tiêu một sheet) và đẩy lên các bảng
tương ứng trên Cloudflare D1. Lỗi khi tính công thức hoặc khi đẩy D1 sẽ được in ra
console theo từng mục, không làm dừng toàn bộ pipeline.

## Ghi chú

- `input_formulas.csv`, `data_dict.csv`, `structure_audit_report.csv`,
  `formula_definitions.csv`, `output.xlsx` đều là file sinh ra/tạo cục bộ
  (`.gitignore` loại trừ `*.csv` và `*.xlsx`) — không commit các file này.
- `push_dataframe_to_d1` sẽ `DROP TABLE` nếu bảng đã tồn tại trước khi tạo lại —
  tức là mỗi lần chạy `main.py` là một lần cập nhật mới toàn bộ dữ liệu Cloudflare D1
  từ dữ liệu local.
- Sửa code dùng chung (không thuộc `src/config.py`/`src/data_readers.py`) nên làm
  trên `main` rồi merge xuống `fiinx` và `widata`, tránh sửa trực tiếp trên từng
  nhánh con rồi quên đồng bộ ngược lại.
