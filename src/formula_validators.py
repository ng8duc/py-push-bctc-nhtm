import polars as pl
import re
from .data_validators import _write_csv_utf8


# Trích các rowid dùng trong 1 công thức. Tiền tố avg_ (giá trị trung bình) được bỏ
# vì vẫn tham chiếu cùng 1 định nghĩa chi_tieu. Hàm SQL (abs, round,...) và biến quarter
# (dùng để annualize) đều viết thường nên không trùng pattern rowid viết hoa, khỏi cần lọc riêng.
def _extract_rowids(formula: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'(?:avg_)?([A-Z]+_\d+)', formula)))


# Với mỗi công thức trong input_formulas.csv, liệt kê các chi_tieu (định nghĩa) mà nó dùng.
def list_formula_definitions(formula_csv: str = 'input_formulas.csv', data_dict_csv: str = 'data_dict.csv') -> pl.DataFrame:
    data_dict = (pl.read_csv(data_dict_csv)
                 .with_columns(pl.col('chi_tieu').str.strip_prefix("'")))

    df_formula = pl.read_csv(formula_csv)

    rows = []
    for row in df_formula.iter_rows(named=True):
        for rowid in _extract_rowids(row['Công thức tính']):
            rows.append({
                'Chỉ tiêu': row['Chỉ tiêu'],
                'Công thức tính': row['Công thức tính'],
                'rowid': rowid,
            })

    return (pl.DataFrame(rows)
            .join(data_dict, on='rowid', how='left'))


# rowid dùng trong công thức nhưng không có trong data_dict.csv.
def missing_definitions(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(pl.col('chi_tieu').is_null())


# Gộp mỗi công thức về 1 dòng, cột chi_tieu dạng "rowid:chi_tieu | rowid:chi_tieu | ...".
def collapse_definitions(df: pl.DataFrame) -> pl.DataFrame:
    return (df
            .with_columns((pl.col('rowid') + pl.lit(':') + pl.col('chi_tieu')).alias('_pair'))
            .group_by('Chỉ tiêu', 'Công thức tính', maintain_order=True)
            .agg(pl.col('_pair').str.join(' | ').alias('Định nghĩa')))


if __name__ == '__main__':
    result = list_formula_definitions()

    missing = missing_definitions(result)
    if not missing.is_empty():
        print('CẢNH BÁO: rowid dùng trong công thức nhưng không có trong data_dict.csv:')
        print(missing)
        print()

    collapsed = collapse_definitions(result)
    _write_csv_utf8(collapsed, 'formula_definitions.csv')
    print('Đã ghi formula_definitions.csv')
    print(f"Số công thức: {collapsed.height}")
