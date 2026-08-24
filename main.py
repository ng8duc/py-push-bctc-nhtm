# các biến môi trường

from concurrent.futures import ThreadPoolExecutor, as_completed

import xlsxwriter

from src.config import *
from src.data_readers import read_multiple_file
from src.data_wranglers import *
from src.d1_pusher import push_dataframe_to_d1
from pyprojroot.here import here
from src.janitorvn import make_clean_names_vn

# Đọc full data
frames = []

for company in TOPNH:
    cum_list = []

    try:
        df_q = read_multiple_file(folder=here('data/data-quarterly'), company_name=company)
    except Exception:
        df_q = pl.DataFrame()

    try:
        df_y = read_multiple_file(folder=here('data/data-yearly'), company_name=company, freq='yearly')
    except Exception:
        df_y = pl.DataFrame()

    try:
        df_cum = read_multiple_file(folder=here('data/data-cumulative'), company_name=company, freq='cumulative')
    except Exception:
        df_cum = pl.DataFrame()

    if not df_cum.is_empty():
        df_cum = (df_cum
               .select(cs.exclude('chi_tieu'))
               .unpivot(index=['rowid', 'cong_ty'], variable_name='yq', value_name='value')
               .pivot(index=['cong_ty', 'yq'], on='rowid', values='value'))

        cum_list = df_cum.select('yq').to_series().to_list()

        frames.append(df_cum)

    if not df_q.is_empty():
        for year in range(2020,2027):
            for quarter in range(3): # Luôn để range = 3 vì chỉ lấy 3 quý đầu năm
                try:
                    df1 = gen_cumulative_data(df_q, year=year, quarter=quarter+1)
                except Exception:
                    continue

                df1 = (df1
                    .select(cs.exclude('chi_tieu'))
                    .unpivot(index=['rowid', 'cong_ty'], variable_name='yq', value_name='value')
                    .pivot(index=['cong_ty', 'yq'], on='rowid', values='value'))

                if f'{year}_q{quarter+1}' not in cum_list:
                    frames.append(df1)

    if not df_y.is_empty():
        df_y = (df_y
               .select(cs.exclude('chi_tieu'))
               .unpivot(index=['rowid', 'cong_ty'], variable_name='yq', value_name='value')
               .pivot(index=['cong_ty', 'yq'], on='rowid', values='value'))

        frames.append(df_y)


# Đây là bảng full
df2 = pl.concat(frames, how='diagonal_relaxed').unique()
df3 = summarize_by_group(df2)
df4 = gen_average_columns(df3)



df_formula = pl.read_csv('input_formulas.csv')
sheet_name = dict(df_formula.select('Chỉ tiêu', 'Tên sheet').iter_rows())
d1_table_name = dict(df_formula
                     .with_columns(
                         pl.col('Chỉ tiêu').make_clean_names_vn().alias('chi_tieu')
                     ).select('Chỉ tiêu', 'chi_tieu').iter_rows())

def _run_formula(row):
    col_name = row['Chỉ tiêu']                                                                                                                                                                       
    try:
        return col_name, gen_data_by_formula(df=df4, formula=row['Công thức tính']).with_columns(pl.lit(col_name).alias('chi_tieu'))
    except Exception as e:
        return col_name, e

results = {}

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(_run_formula, row) for row in df_formula.iter_rows(named=True)]
    for f in as_completed(futures):
        col_name, result = f.result()
        results[col_name] = result


errors = {}
to_excel = {}
to_d1 = {}

for col_name, result in results.items():
    if isinstance(result, Exception):
        errors[col_name] = result
    else:
        to_excel[sheet_name[col_name]] = result
        to_d1[d1_table_name[col_name]] = (result
                                          .select(cs.exclude('chi_tieu'))
                                          .unpivot(
                                              index = ['yq'],
                                              variable_name = 'name',
                                              value_name = 'value'
                                          ).with_columns(
                                              pl.format(
                                                  '{}-{}-01',
                                                  pl.col('yq').str.extract(r'(\d{4})_q(\d)', 1),
                                                  (pl.col('yq').str.extract(r'(\d{4})_q(\d)', 2).cast(pl.Int32) * 3 - 2)
                                                      .cast(pl.Utf8).str.zfill(2)
                                              ).alias('yq')
                                          ))

if errors:
    print('Các công thức bị lỗi:')
    for col_name, err in errors.items():
        print(f'  - {col_name}: {err}')

workbook = xlsxwriter.Workbook('output.xlsx', {'nan_inf_to_errors': True})
for sheet, df in to_excel.items():
    df.write_excel(workbook=workbook, worksheet=sheet)
workbook.close()

d1_errors = {}
for table_name, df in to_d1.items():
    try:
        push_dataframe_to_d1(df, table=table_name)
    except Exception as e:
        d1_errors[table_name] = e

if d1_errors:
    print('Các bảng bị lỗi khi đẩy lên D1:')
    for table_name, err in d1_errors.items():
        print(f'  - {table_name}: {err}')
