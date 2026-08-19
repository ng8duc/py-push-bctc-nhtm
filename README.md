# push-bctc

Pipeline xử lý báo cáo tài chính (BCTC) của các ngân hàng niêm yết và đẩy dữ liệu
lên Cloudflare D1.

## Tính năng chính

- Đọc nhiều file Excel BCTC (quý/năm/lũy kế) cho danh sách ngân hàng khai báo trong
  `src/config.py`:
  - `TOPNHNN` — 4 ngân hàng gốc nhà nước (Agribank, BIDV, VietinBank, Vietcombank).
  - `TOPNHTM` — 7 ngân hàng TMCP tư nhân lớn (VPB, SHB, VIB, MBB, ACB, HDB, TCB).
  - `TOPNH` — toàn bộ ngân hàng niêm yết đang theo dõi (28 mã); không phải hợp của
    hai nhóm trên mà là danh sách độc lập, dùng để tính tổng/trung bình toàn ngành.
- Tính dữ liệu lũy kế từ dữ liệu quý (`gen_cumulative_data`), xử lý khác nhau theo
  loại chỉ tiêu — dựa vào `CUM_CONST` trong `src/config.py`:
  - Chỉ tiêu bảng cân đối (`rowid` bắt đầu bằng `BS`) và thuyết minh
    (`CUM_CONST['notes_max']`) là số dư tại một thời điểm, nên lấy giá trị của quý
    **cuối cùng** trong năm, không cộng dồn.
  - Tiền và tương đương tiền đầu kỳ (`CUM_CONST['cash_dau_ky']`) lấy giá trị quý
    **đầu tiên**, cuối kỳ (`CUM_CONST['cash_cuoi_ky']`) lấy quý **cuối cùng**.
  - Các chỉ tiêu còn lại (dạng flows — thu nhập, dòng tiền trên IS/CF) được
    **cộng dồn (sum)** qua các quý trong năm.
  - Nếu `CUM_CONST` khai sai rowid, các dòng thuyết minh/tiền mặt sẽ bị cộng dồn
    nhầm thay vì lấy đúng giá trị cuối kỳ — xem bước tinh chỉnh `CUM_CONST` ở mục
    [Cách sử dụng](#cách-sử-dụng).
- Tổng hợp chỉ tiêu theo nhóm ngân hàng (`summarize_by_group`): với mỗi nhóm
  `TOPNHNN`/`TOPNHTM`/`TOPNH` ở trên, sinh thêm các dòng dữ liệu tổng hợp theo kỳ
  (`yq`) — "BQ n NHTM nhà nước", "BQ n NHTM lớn", "BQ n NHTM" (giá trị trung bình)
  và "Tổng n NHTM" (giá trị tổng) — nối thêm vào dữ liệu gốc theo từng công ty.
- Tính chỉ tiêu tài chính thứ cấp từ công thức khai báo trong `input_formulas.csv`
  (`gen_data_by_formula`).
- Xuất kết quả ra `output.xlsx` (nhiều sheet) và đẩy từng bảng lên Cloudflare D1
  (`src/d1_pusher.py`, dùng `npx wrangler d1 execute`). Mỗi chỉ tiêu trong
  `input_formulas.csv` sinh ra một bảng D1 riêng, tên bảng lấy từ cột "Chỉ tiêu"
  làm sạch qua `make_clean_names_vn` (`src/janitorvn.py`) thành dạng snake_case
  không dấu — ví dụ chỉ tiêu "Tổng tài sản" → bảng `tong_tai_san`.
- `src/data_validators.py` và `src/formula_validators.py` kiểm tra tính nhất quán
  của form BCTC và tính phù hợp của công thức trước khi chạy pipeline chính.

## Mỗi nguồn dữ liệu sử dụng một nhánh khác nhau

Dữ liệu thô BCTC thu thập từ hai nguồn khác nhau — **FiinX** hoặc **WiData** — và
hai nguồn này không chỉ khác tên cột mà có thể khác cả cấu trúc file (tên sheet,
ngày xuất dữ liệu, loại báo cáo riêng lẻ hay hợp nhất...). Vì phần khác biệt này
khó gói gọn bằng một biến cấu hình duy nhất, repo dùng 3 nhánh:

- **`main`** — nhánh gốc, chứa toàn bộ logic dùng chung (đọc file, tính toán, đẩy
  D1, validator...). Không tự chạy được pipeline vì `src/config.py` chỉ mang giá
  trị mặc định, chưa khớp nguồn dữ liệu cụ thể nào.
- **`fiinx`** — rẽ từ `main`, đã tinh chỉnh để khớp mẫu Excel do FiinX xuất.
- **`widata`** — rẽ từ `main`, đã tinh chỉnh để khớp mẫu Excel do WiData xuất.

Muốn chạy pipeline cho nguồn nào thì `git switch` sang đúng nhánh đó
(`git switch fiinx` hoặc `git switch widata`).

### File khác nhau giữa các nhánh `fiinx` / `widata`

| File | Khác nhau ở đâu |
|---|---|
| `src/config.py` | `SHEETS` (tên tab Excel khớp nguồn) và `CUM_CONST` (rowid tiền và tương đương tiền đầu/cuối kỳ, khoảng rowid thuyết minh) được tinh chỉnh riêng cho từng nguồn. |
| `input_formulas.csv.example` | Công thức mẫu tính chỉ tiêu, tham chiếu đúng rowid của nguồn dữ liệu trên nhánh đó. File này được commit riêng trên từng nhánh (không bị `.gitignore` vì không có đuôi `.csv`). |
| `input_formulas.csv` | Copy ra từ `input_formulas.csv.example` của nhánh hiện tại, dùng để chạy pipeline thật. File này bị `.gitignore` (xem `*.csv`) nên không commit, mỗi lần checkout nhánh khác phải tạo lại — xem mục [Cách sử dụng](#cách-sử-dụng). |
| `src/data_readers.py` | Logic đọc từng file riêng lẻ (`_read_file_data`) không dùng chung được giữa hai nguồn (khác vị trí ô ngày xuất dữ liệu, tên sheet, loại báo cáo là hợp nhất hay riêng lẻ...). Dữ liệu của **FiinX** có cả BCTC riêng lẻ và BCTC hợp nhất, nên `read_multiple_file` dùng 2 logic lấy dữ liệu: ưu tiên dữ liệu có ngày xuất dữ liệu mới hơn, và ưu tiên dữ liệu BCTC riêng lẻ — nếu không có BCTC riêng lẻ thì fill bằng dữ liệu BCTC hợp nhất. Dữ liệu của **WiData** chỉ có BCTC hợp nhất nên chỉ dùng 1 logic: ưu tiên dữ liệu có ngày xuất dữ liệu mới hơn. |
| `src/data_validators.py` | Cách đọc dữ liệu của `_read_file_structure` tương tự `_read_file_data` trong `src/data_readers.py`, nên nếu cấu trúc file Excel dữ liệu thô của **FiinX** hay **WiData** thay đổi, cần điều chỉnh đồng thời với `src/data_readers.py`. |

### File giữ nguyên, dùng chung trên mọi nhánh

`main.py`, `src/data_wranglers.py`, `src/formula_validators.py`,
`src/d1_pusher.py`, `src/janitorvn.py`, `requirements.txt`, `.env.example`,
`.gitignore`. Sửa các file này nên thực hiện trên `main` rồi merge xuống
`fiinx`/`widata`, để tránh hai nhánh bị trôi (drift) so với nhau.

## Cấu trúc thư mục

- `main.py` — entry point, chạy toàn bộ pipeline từ đọc dữ liệu đến đẩy lên D1.
- `raw_data.py`, `to_sankey.py` — script phụ trợ để khám phá/kiểm tra dữ liệu.
- `src/config.py` — hằng số cấu hình (danh sách ngân hàng, tên sheet, `CUM_CONST`
  ...), giá trị `SHEETS`/`CUM_CONST` khác nhau giữa nhánh `fiinx`/`widata` (xem
  trên).
- `src/data_readers.py` — đọc và pivot dữ liệu Excel thô.
- `src/data_wranglers.py` — các hàm biến đổi và tính toán dữ liệu.
- `src/janitorvn.py` — wrapper của `pyjanitor`, tinh chỉnh cho phù hợp với tiếng
  Việt.
- `src/d1_pusher.py` — đẩy DataFrame lên Cloudflare D1.
- `src/data_validators.py` — audit tính nhất quán cấu trúc form BCTC giữa các
  file/kỳ/công ty, sinh từ điển `data_dict.csv` (rowid <-> chi_tieu).
- `src/formula_validators.py` — đối chiếu rowid dùng trong `input_formulas.csv`
  với `data_dict.csv` để phát hiện công thức tham chiếu rowid không tồn tại.
- `data/data-quarterly`, `data/data-yearly`, `data/data-cumulative` — dữ liệu
  Excel BCTC đầu vào, mỗi thư mục tương đương với một kiểu xuất dữ liệu.
- `input_formulas.csv.example` — công thức mẫu cho nguồn dữ liệu của nhánh hiện
  tại, được commit trong git (khác nội dung giữa nhánh `fiinx`/`widata`, xem
  trên).

## Yêu cầu & cài đặt

- Python 3.13+
- Node.js + `npx wrangler` (Cloudflare Wrangler CLI) đã đăng nhập hoặc có API
  token, dùng để đẩy dữ liệu lên D1.

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
   `git switch widata`. `src/config.py` trên nhánh đó đã khớp sẵn với nguồn dữ
   liệu.
2. Đặt file Excel BCTC vào đúng thư mục `data/data-quarterly`, `data/data-yearly`
   hoặc `data/data-cumulative`, tên file phải chứa mã ngân hàng (ví dụ
   `Báo cáo tài chính VCB.xlsx`) vì `read_multiple_file` lọc file theo mã này.
   Đa phần các ngân hàng đều có BCTC theo quý và theo năm, riêng Agribank (AGRB)
   không có BCTC quý mà chỉ có BCTC lũy kế 6 tháng, đưa vào `data/data-cumulative`.
3. Chạy `python -m src.data_validators` để audit tính nhất quán cấu trúc form
   BCTC giữa các file/công ty (số dòng, tên `chi_tieu`, `rowid` có bị lệch giữa
   các kỳ không). Nếu không có lỗi cấu trúc (`chi_tieu_drift`, `row_count_diff`),
   lệnh này ghi ra `structure_audit_report.csv` và từ điển `data_dict.csv`
   (rowid <-> chi_tieu). Nếu phát hiện lệch cấu trúc ở rowid dùng trong công thức
   tính, sẽ có cảnh báo riêng.
4. Nếu đây là lần đầu thiết lập nhánh cho nguồn dữ liệu này: dựa vào
   `data_dict.csv` vừa sinh ra, tinh chỉnh `CUM_CONST` trong `src/config.py` cho
   khớp rowid thực tế (rowid tiền mặt đầu kỳ/cuối kỳ trên sheet lưu chuyển tiền
   tệ, khoảng rowid tối đa của sheet thuyết minh) rồi commit lại trên nhánh đó —
   chỉ cần làm một lần, các lần chạy sau không cần lặp lại bước này.
5. Sao chép `input_formulas.csv.example` của nhánh hiện tại thành
   `input_formulas.csv` (file này bị `.gitignore`, không tự có sẵn sau khi
   switch nhánh):

   ```bash
   cp input_formulas.csv.example input_formulas.csv
   ```

   Đây chỉ là file mẫu; công thức có thực sự đúng với dữ liệu hiện tại hay không
   được rà soát ở bước tiếp theo (`formula_validators`) và bước chỉnh sửa thủ
   công sau đó.
6. Chạy `python -m src.formula_validators` để kiểm tra tính phù hợp của công
   thức trong `input_formulas.csv`: đối chiếu từng rowid được tham chiếu trong
   công thức với `data_dict.csv` để phát hiện rowid không tồn tại/không có định
   nghĩa, đồng thời xuất `formula_definitions.csv` liệt kê chi_tieu tương ứng của
   từng công thức để rà soát thủ công.
7. Chỉnh sửa thêm công thức tính chỉ tiêu trong `input_formulas.csv` nếu cần.
8. Chạy pipeline chính:

   ```bash
   python main.py
   ```

   Kết quả được ghi ra `output.xlsx` (mỗi chỉ tiêu một sheet) và đẩy lên các
   bảng tương ứng trên Cloudflare D1. Lỗi khi tính công thức hoặc khi đẩy D1 sẽ
   được in ra console theo từng mục, không làm dừng toàn bộ pipeline.

## Ghi chú

- `input_formulas.csv`, `data_dict.csv`, `structure_audit_report.csv`,
  `formula_definitions.csv`, `output.xlsx` đều là file sinh ra/tạo cục bộ
  (`.gitignore` loại trừ `*.csv` và `*.xlsx`) — không commit các file này.
- `push_dataframe_to_d1` sẽ `DROP TABLE` nếu bảng đã tồn tại trước khi tạo lại —
  tức là mỗi lần chạy `main.py` là một lần cập nhật mới toàn bộ dữ liệu Cloudflare
  D1 từ dữ liệu local.
- Sửa code dùng chung (không thuộc `src/config.py`/`src/data_readers.py`) nên
  làm trên `main` rồi merge xuống `fiinx` và `widata`, tránh sửa trực tiếp trên
  từng nhánh con rồi quên đồng bộ ngược lại.
