from .config import *
import polars as pl
import polars.selectors as cs
import fastexcel
from .janitorvn import *
from .data_readers import load_sheet
from pathlib import Path
import re


# Đọc "vân tay" cấu trúc của 1 file: chỉ rowid + chi_tieu, không cast số liệu.
# rowid được đánh y hệt cách _read_file_data làm, để phản ánh đúng pipeline thật.
def _read_file_structure(file_path: str, company_name: str) -> pl.DataFrame:
    reader = fastexcel.read_excel(file_path)

    frames = []
    for key, sheet in SHEETS.items():
        sheet_name = f'{sheet}'

        df = (load_sheet(reader, sheet_name)
              .clean_names_vn()
              .rename({'chi_tieuty_vnd': 'chi_tieu'})
              .with_columns(pl.col('chi_tieu').str.strip_chars())
              .filter(~pl.col('chi_tieu').str.contains('kiểm toán'))
              .select('chi_tieu')
              .with_row_index('rowid', offset=1)
              .with_columns(
                  (pl.lit(f'{key}_') + pl.col('rowid').cast(pl.Utf8)).alias('rowid'),
                  pl.lit(key).alias('sheet'),
                  pl.lit(Path(file_path).name).alias('file'),
              )
              )

        frames.append(df)

    return pl.concat(frames)


# Cấu trúc rowid <-> chi_tieu cho tất cả các file của 1 công ty trong 1 thư mục.
def get_company_structure(folder: str, company_name: str) -> pl.DataFrame:
    files = sorted([f for f in Path(folder).glob(f'*{company_name}*') if not f.name.startswith('~$')])

    if not files:
        return pl.DataFrame()

    frames = [_read_file_structure(file_path=f, company_name=company_name) for f in files]

    return (pl.concat(frames)
            .with_columns(pl.lit(company_name).alias('cong_ty')))


# So sánh cấu trúc giữa các file của 1 công ty, trả về báo cáo lệch cấu trúc.
def compare_structure(df: pl.DataFrame) -> pl.DataFrame:
    row_count_diff = (
        df.with_columns(pl.col('rowid').str.extract(r'_(\d+)$', 1).cast(pl.Int64).alias('row_num'))
        .group_by('cong_ty', 'sheet', 'file')
        .agg(pl.col('row_num').max().alias('row_count'))
        .with_columns(
            (pl.col('row_count').n_unique().over('cong_ty', 'sheet') > 1).alias('_flag'),
            pl.lit('row_count_diff').alias('check_type'),
        )
        .filter(pl.col('_flag'))
        .drop('_flag')
    )

    chi_tieu_drift = (
        df.group_by('cong_ty', 'sheet', 'rowid')
        .agg(
            pl.col('chi_tieu').n_unique().alias('n_variants'),
            pl.col('chi_tieu').unique().alias('chi_tieu_variants'),
            pl.col('file').unique().alias('files'),
        )
        .filter(pl.col('n_variants') > 1)
        .with_columns(pl.lit('chi_tieu_drift').alias('check_type'))
    )

    rowid_drift = (
        df.filter(pl.col('chi_tieu').is_not_null() & (pl.col('chi_tieu').str.strip_chars() != ''))
        .group_by('cong_ty', 'sheet', 'chi_tieu')
        .agg(
            pl.col('rowid').n_unique().alias('n_variants'),
            pl.col('rowid').unique().alias('rowid_variants'),
            pl.col('file').unique().alias('files'),
        )
        .filter(pl.col('n_variants') > 1)
        .with_columns(pl.lit('rowid_drift').alias('check_type'))
    )

    return pl.concat([row_count_diff, chi_tieu_drift, rowid_drift], how='diagonal_relaxed')


# Audit toàn bộ công ty x thư mục, trả về báo cáo lệch cấu trúc gộp chung.
def audit_all(companies: list[str] = TOPNH, folders: dict[str, str] = None) -> pl.DataFrame:
    if folders is None:
        folders = {'quarterly': DATA_DIR / 'data-quarterly', 'yearly': DATA_DIR / 'data-yearly'}

    reports = []
    for folder_key, folder_path in folders.items():
        for company in companies:
            try:
                structure = get_company_structure(folder=folder_path, company_name=company)
            except Exception as e:
                print(f'Bỏ qua {company} ({folder_key}): {e}')
                continue

            if structure.is_empty():
                continue

            report = compare_structure(structure).with_columns(pl.lit(folder_key).alias('folder'))
            reports.append(report)

    if not reports:
        return pl.DataFrame()

    return pl.concat(reports, how='diagonal_relaxed')


# Tập rowid được tham chiếu trực tiếp trong input_formulas.csv hoặc CUM_CONST.
# Đây là các rowid mà nếu lệch cấu trúc sẽ làm sai kết quả tính công thức.
def critical_rowids(formula_csv: str = 'input_formulas.csv') -> set[str]:
    df_formula = pl.read_csv(formula_csv)

    rowids = set()
    for formula in df_formula['Công thức tính']:
        for match in re.findall(r'(?:avg_)?([A-Z]+_\d+)', formula):
            rowids.add(match)

    rowids.add(CUM_CONST['cash_dau_ky'])
    rowids.add(CUM_CONST['cash_cuoi_ky'])
    rowids.update(CUM_CONST['notes_max'])

    return rowids


# Từ điển rowid <-> chi_tieu gộp từ mọi công ty/file, chỉ nên dùng khi audit không có lỗi.
def build_data_dict(companies: list[str] = TOPNH, folders: dict[str, str] = None) -> pl.DataFrame:
    if folders is None:
        folders = {'quarterly': DATA_DIR / 'data-quarterly', 'yearly': DATA_DIR / 'data-yearly'}

    frames = []
    for _, folder_path in folders.items():
        for company in companies:
            try:
                structure = get_company_structure(folder=folder_path, company_name=company)
            except Exception:
                continue

            if structure.is_empty():
                continue

            frames.append(structure.select('rowid', 'chi_tieu'))

    if not frames:
        return pl.DataFrame()

    sheet_order = {key: i for i, key in enumerate(SHEETS.keys())}

    return (pl.concat(frames)
            .unique()
            .with_columns(
                pl.col('rowid').str.extract(r'^([A-Z]+)_', 1).replace_strict(sheet_order).alias('_sheet_order'),
                pl.col('rowid').str.extract(r'_(\d+)$', 1).cast(pl.Int64).alias('_num'),
            )
            .sort('_sheet_order', '_num')
            .drop('_sheet_order', '_num'))


# Ghi CSV bằng UTF-8 kèm BOM để Excel hiển thị đúng tiếng Việt.
# quote_style='non_numeric' để mọi cột dạng chuỗi được quote nhất quán.
# Thêm dấu ' phía trước các giá trị bắt đầu bằng = + - @ để Excel không hiểu nhầm thành công thức.
def _write_csv_utf8(df: pl.DataFrame, path: str) -> None:
    string_cols = [c for c, dt in zip(df.columns, df.dtypes) if dt == pl.Utf8]

    df = df.with_columns([
        pl.when(pl.col(c).str.contains(r'^[=+\-@]').fill_null(False))
        .then(pl.lit("'") + pl.col(c))
        .otherwise(pl.col(c))
        .alias(c)
        for c in string_cols
    ])

    with open(path, 'wb') as f:
        f.write(b'\xef\xbb\xbf')
        df.write_csv(f, quote_style='non_numeric')


if __name__ == '__main__':
    report = audit_all()

    if report.is_empty():
        print('Không tìm thấy lệch cấu trúc nào.')
    else:
        _write_csv_utf8(report.with_columns(cs.by_dtype(pl.List(pl.Utf8)).list.join(' | ')),
                         'structure_audit_report.csv')
        print('Đã ghi báo cáo vào structure_audit_report.csv')
        print(report.group_by('check_type').len())

        critical = critical_rowids()
        critical_hits = report.filter(pl.col('rowid').is_in(critical))
        if not critical_hits.is_empty():
            print('\nCẢNH BÁO: lệch cấu trúc ở các rowid dùng trong công thức tính:')
            print(critical_hits)

    if report.is_empty():
        errors = report
    else:
        errors = report.filter(pl.col('check_type').is_in(['chi_tieu_drift', 'row_count_diff']))

    if errors.is_empty():
        data_dict = build_data_dict()
        dup = data_dict.filter(pl.col('rowid').is_duplicated())

        if dup.is_empty():
            _write_csv_utf8(data_dict, 'data_dict.csv')
            print('Đã ghi từ điển rowid <-> chi_tieu vào data_dict.csv')
        else:
            print('\nrowid bị trùng chi_tieu khác nhau khi gộp toàn bộ công ty, không xuất data_dict.csv:')
            print(dup)
    else:
        print('\nCó lỗi cấu trúc (chi_tieu_drift/row_count_diff), không xuất data_dict.csv.')
