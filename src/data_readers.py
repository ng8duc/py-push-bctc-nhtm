from .config import *
import polars as pl
import polars.selectors as cs
import fastexcel
from .janitorvn import *
from pathlib import Path
import re
from datetime import date, datetime
from typing import Literal


# Đọc ô "Ngày xuất dữ liệu: dd/mm/yyyy" nằm ở đầu mỗi sheet.
# Dùng row index 1 (không phải số dòng Excel tuyệt đối), vì fastexcel/calamine
# chỉ đọc theo "used range" - nếu các dòng đầu sheet trống, chúng bị bỏ qua
# và việc đánh số lại bắt đầu từ dòng có dữ liệu đầu tiên.
def _extract_export_date(reader: fastexcel.ExcelReader, sheet_name: str) -> date:
    raw = reader.load_sheet(sheet_name, header_row=None).to_polars()
    text = raw.row(1)[0]
    match = re.search(r'(\d{2})/(\d{2})/(\d{4})', text)
    return datetime.strptime(match.group(0), '%d/%m/%Y').date()


def _read_file_data(file_path:str, company_name:str, freq:Literal['quarterly', 'cumulative', 'yearly'] = 'quarterly') -> pl.DataFrame:

    reader = fastexcel.read_excel(file_path)

    first_sheet_name = f'{next(iter(SHEETS.values()))} - {company_name}'
    export_date = _extract_export_date(reader, first_sheet_name)

    frames = []
    for key, sheet in SHEETS.items():
        sheet_name = f'{sheet} - {company_name}'

        df = (reader
              .load_sheet(sheet_name, header_row=8)
              .to_polars()
              .clean_names_vn()
              .filter(pl.col('don_vi').is_not_null())
              .with_columns(cs.exclude('don_vi', 'chi_tieu').cast(pl.Float64, strict=False))
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
        pl.concat(frames)
        .drop('don_vi')
        .with_columns(
            pl.lit(company_name).alias('cong_ty'),
            pl.lit(export_date).alias('ngay_xuat_du_lieu')
        )
    )

def read_multiple_file(folder:str , company_name:str, freq:Literal['quarterly', 'cumulative', 'yearly'] = 'quarterly') -> pl.DataFrame:
    files = sorted([f for f in Path(folder).glob(f'*{company_name}*') if not f.name.startswith('~$')])

    frames = []
    for file in files:
        df = _read_file_data(file_path=file, company_name=company_name, freq=freq)

        df = (df.unpivot(index=['rowid', 'chi_tieu', 'cong_ty', 'ngay_xuat_du_lieu'], variable_name='period', value_name='value')
              .with_columns(pl.col('period').str.replace(r'(q\d)_(\d{4})', '${2}_${1}'))
        )

        frames.append(df)

    return (pl.concat(frames)
           .sort('ngay_xuat_du_lieu', descending=True)
           .unique(subset=['rowid', 'chi_tieu', 'cong_ty', 'period'], keep = 'first', maintain_order = True)
           .drop('ngay_xuat_du_lieu')
           .pivot(index = ['rowid', 'chi_tieu', 'cong_ty'], on = 'period', values = 'value', maintain_order = True, sort_columns = True)
           )
