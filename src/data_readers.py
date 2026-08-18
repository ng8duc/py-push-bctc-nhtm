from .config import *
import polars as pl
import polars.selectors as cs
import fastexcel
from .janitorvn import *
from pathlib import Path
import re
from datetime import date, datetime
from typing import Literal


# Đọc ô ngày xuất dữ liệu ("Ngày trích xuất") nằm ở cột B, dòng 2 của mỗi sheet.
# Dùng row/col index (không phải số dòng/cột Excel tuyệt đối), vì fastexcel/calamine
# chỉ đọc theo "used range" - nếu các dòng đầu sheet trống, chúng bị bỏ qua
# và việc đánh số lại bắt đầu từ dòng có dữ liệu đầu tiên.
def _extract_export_date(reader: fastexcel.ExcelReader, sheet_name: str) -> date:
    raw = reader.load_sheet(sheet_name, header_row=None).to_polars()
    value = raw.row(1)[1]
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f').date()

def _extract_consolidate_type(reader: fastexcel.ExcelReader, sheet_name: str) -> str:
    raw = reader.load_sheet(sheet_name, header_row=None).to_polars()
    value = raw.row(4)[1]
    if isinstance(value, str):
        return value


# Dòng tiêu đề cột ("Chỉ tiêuTỷ VND", "Q1/2016", ...) nằm ở row index 6 của mỗi sheet.
# fastexcel's header_row cho kết quả lệch dòng khi có các dòng trống xen giữa
# (như row 2 và row 5 ở trên), nên phải tự dựng header từ dữ liệu thô thay vì
# dùng tham số header_row.
def load_sheet(reader: fastexcel.ExcelReader, sheet_name: str, header_row_idx: int = 6) -> pl.DataFrame:
    raw = reader.load_sheet(sheet_name, header_row=None).to_polars()
    headers = raw.row(header_row_idx)
    new_names = [h if isinstance(h, str) and h else f'__UNNAMED__{i}' for i, h in enumerate(headers)]
    data = raw.slice(header_row_idx + 1)

    # Cuối mỗi sheet luôn có một khối "rác" cố định (dòng trống, rồi "Contact",
    # địa chỉ công ty, hotline, email...) do FiinPro chèn vào footer file export.
    # Cắt bỏ mọi thứ từ dòng "Contact" trở đi.
    first_col = data.columns[0]
    contact_row = data.with_row_index('__idx').filter(pl.col(first_col) == 'Contact')
    if contact_row.height > 0:
        data = data.head(contact_row.item(0, '__idx'))

    return data.rename(dict(zip(raw.columns, new_names)))


def _read_file_data(file_path:str, company_name:str, freq:Literal['quarterly', 'cumulative', 'yearly'] = 'quarterly') -> pl.DataFrame:

    reader = fastexcel.read_excel(file_path)

    first_sheet_name = f'{next(iter(SHEETS.values()))}'
    export_date = _extract_export_date(reader, first_sheet_name)
    consolidate_type = _extract_consolidate_type(reader, first_sheet_name)

    frames = []
    for key, sheet in SHEETS.items():
        sheet_name = f'{sheet}'

        df = (load_sheet(reader, sheet_name)
              .clean_names_vn()
              .rename({'chi_tieuty_vnd':'chi_tieu'})
              .with_columns(pl.col('chi_tieu').str.strip_chars())
              .filter(~pl.col('chi_tieu').str.contains('kiểm toán'))
              .with_columns(cs.exclude('chi_tieu').cast(pl.Float64, strict=False))
              .with_row_index('rowid', offset = 1)
              .with_columns(
                  (pl.lit(f'{key}_') + pl.col('rowid').cast(pl.Utf8)).alias('rowid')
              )
              )

        if freq == 'yearly':
            cols = [c for c in df.columns if len(c) == 4 and c[:2] == '20']
            df = df.rename({c:f'{c}_q4' for c in cols})

        if freq == 'cumulative':
            cols = [c for c in df.columns if re.match(r'\d{1,2}m_\d{4}', c)]
            df = df.rename({c: f'{c.split('_')[1]}_q{int(c.split('m_')[0]) // 3}' for c in cols})

        frames.append(df)

    return (
        pl.concat(frames, how='diagonal_relaxed')
        .with_columns(
            pl.lit(company_name).alias('cong_ty'),
            pl.lit(export_date).alias('ngay_xuat_du_lieu'),
            pl.lit(consolidate_type).alias('loai_bao_cao')
        )
    )

def read_multiple_file(folder:str , company_name:str, freq:Literal['quarterly', 'cumulative', 'yearly'] = 'quarterly') -> pl.DataFrame:
    files = sorted([f for f in Path(folder).glob(f'*{company_name}*') if not f.name.startswith('~$')])

    frames = []
    for file in files:
        df = _read_file_data(file_path=file, company_name=company_name, freq=freq)

        df = (df.unpivot(index=['rowid', 'chi_tieu', 'cong_ty', 'ngay_xuat_du_lieu', 'loai_bao_cao'], variable_name='period', value_name='value')
              .with_columns(pl.col('period').str.replace(r'(q\d)_(\d{4})', '${2}_${1}'))
        )

    frames.append(df)

    data = pl.concat(frames)
    data_rieng_le = (data.filter(pl.col('loai_bao_cao') == 'Riêng lẻ'))
    rieng_le_entries = data_rieng_le['period'].unique().to_list()

    data_hop_nhat = data.filter((pl.col('loai_bao_cao') == 'Hợp nhất') & ~pl.col('period').is_in(rieng_le_entries))

    return (pl.concat([data_rieng_le, data_hop_nhat])
           .sort('ngay_xuat_du_lieu', descending=True)
           .unique(subset=['rowid', 'chi_tieu', 'cong_ty', 'period'], keep = 'first', maintain_order = True)
           .drop('ngay_xuat_du_lieu')
           .pivot(index = ['rowid', 'chi_tieu', 'cong_ty'], on = 'period', values = 'value', maintain_order = True, sort_columns = True)
           )
