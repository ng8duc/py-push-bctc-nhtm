from .config import *
import polars as pl
import polars.selectors as cs
from . import data_readers

# Hàm này tính lũy kế theo quý, chỉ dùng cho dữ liệu đọc theo quý từ quý 1 đến 3
# Cấu trúc trả về là rowid, chi_tieu, cong_ty, period
def gen_cumulative_data(df: pl.DataFrame, year:int, quarter:int) -> pl.DataFrame:

    df = (df
          .select('rowid', 'chi_tieu', 'cong_ty', cs.contains(f'{year}'))
          )

    quarter_list = (df
                    .select(cs.contains(f'{year}'))
                    .columns
                    )

    quarter_list = [c for c in quarter_list if int(c[-1]) <= quarter]


    df = df.select('rowid', 'chi_tieu', 'cong_ty', cs.by_name(quarter_list))


    df = df.with_columns(
        pl.when(pl.col('rowid').str.contains('BS')).then(pl.col(max(quarter_list)))
        .when(pl.col('rowid') == CUM_CONST['cash_dau_ky']).then(pl.col(min(quarter_list)))
        .when(pl.col('rowid') == CUM_CONST['cash_cuoi_ky']).then(pl.col(max(quarter_list)))
        .when(pl.col('rowid').is_in(CUM_CONST['notes_max'])).then(pl.col(max(quarter_list)))
        .otherwise(pl.sum_horizontal(pl.col(quarter_list)))
        .alias(max(quarter_list))   
    )

    return (df.select('rowid', 'chi_tieu', 'cong_ty', max(quarter_list)))


# Hàm này sinh dữ liệu theo nhóm ngân hàng, chỉ thực hiện được khi đã nạp đủ dữ liệu
# Vì dữ liệu đầu vào bị group theo yq, nên chỉ nạp được 1 chỉ tiêu duy nhất
def summarize_by_group(df: pl.DataFrame, avg:bool = True) -> pl.DataFrame:
    n_nhnn = df.filter(pl.col('cong_ty').is_in(TOPNHNN))['cong_ty'].n_unique()
    n_nhtm_large = df.filter(pl.col('cong_ty').is_in(TOPNHTM))['cong_ty'].n_unique()
    n_nh = df.filter(pl.col('cong_ty').is_in(TOPNH))['cong_ty'].n_unique()

    nhtm_nn = (df
               .filter(pl.col('cong_ty').is_in(TOPNHNN))
               .group_by('yq')
               .agg(cs.exclude('cong_ty').mean())
               .with_columns(pl.lit(f'BQ {n_nhnn} NHTM nhà nước').alias('cong_ty')))

    nhtm_large = (df
               .filter(pl.col('cong_ty').is_in(TOPNHTM))
               .group_by('yq')
               .agg(cs.exclude('cong_ty').mean())
               .with_columns(pl.lit(f'BQ {n_nhtm_large} NHTM lớn').alias('cong_ty')))

    nhtm_mean = (df
               .filter(pl.col('cong_ty').is_in(TOPNH))
               .group_by('yq')
               .agg(cs.exclude('cong_ty').mean())
               .with_columns(pl.lit(f'BQ {n_nh} NHTM').alias('cong_ty')))

    nhtm_sum = (df
               .filter(pl.col('cong_ty').is_in(TOPNH))
               .group_by('yq')
               .agg(cs.exclude('cong_ty').sum())
               .with_columns(pl.lit(f'Tổng {n_nh} NHTM').alias('cong_ty')))

    if avg == True:
        return(pl.concat([df, nhtm_nn, nhtm_large, nhtm_mean, nhtm_sum], how='diagonal_relaxed'))
    else:
        return(pl.concat([df, nhtm_sum], how='diagonal_relaxed'))

# Hàm này dùng để tạo giá trị trung bình trên BS, phục vụ cho việc tính các chỉ số phức tạp như ROA, ROE, NIM,...
def gen_average_columns(df:pl.DataFrame, agg:bool = True) -> pl.DataFrame:

    df = (df
          .with_columns(
              pl.col('yq').str.extract(r'(\d{4})_q(\d)', 1).cast(pl.Int32).alias('year'),
              pl.col('yq').str.extract(r'(\d{4})_q(\d)', 2).cast(pl.Int32).alias('quarter')
          ).with_columns(
              (pl.col('year') - 1).alias('year_prev'),
          ))

    cols = (df
            .select(cs.contains('BS') | cs.by_name(CUM_CONST['notes_max']))
            .columns)

    df_q4 = (df
             .filter(pl.col('yq').str.extract(r'(\d{4})_q(\d)', 2) == '4')
             .with_columns(
                 pl.col('yq').str.extract(r'(\d{4})_q(\d)', 1).cast(pl.Int32).alias('year_prev')
             ).rename({c:f'{c}_q4' for c in cols})
             .select('cong_ty', 'year_prev', cs.contains('_q4')))

    df_agg_true = (df
          .join(df_q4, on=['cong_ty', 'year_prev'], how='left')
          .with_columns(
              [((pl.col(c) + pl.col(f'{c}_q4'))/2).alias(f'avg_{c}') for c in cols]
          ).drop(
              [f'{c}_q4' for c in cols] + ['year_prev', 'year']
          ))

    df_agg_false = (df
                    .sort(by='yq')
                    .with_columns(
                        [((pl.col(c)+pl.col(c).shift(1))/2).alias(f'avg_{c}') for c in cols]
                    ).drop(['year', 'year_prev']))

    if agg == True:
        return(df_agg_true)

    if agg == False:
        return(df_agg_false)


# Hàm này tính các chỉ tiêu thứ cấp theo công thức đã định sẵn, nạp vào từ 1 file csv
# Các cột của hàm này phải được pivot rồi
def gen_data_by_formula(df: pl.DataFrame, formula: str, agg:bool = True, col_name: str = 'new_col') -> pl.DataFrame:
    # Nếu False thì sẽ tính theo quý và annualize (sẽ cập nhật dần)
    if agg == False:
        try:
            formula = formula.replace('quarter', '1')
        except Exception:
            formula = formula

    df = (df
          .with_columns(pl.sql_expr(formula).alias(col_name)))

    df_result = (df
                 .select(['cong_ty', 'yq', col_name])
                 .pivot(
                     index=['yq'],
                     on='cong_ty',
                     values=col_name
                 )
                 )

    col_order = (df_result
                 .filter(pl.col('yq') == pl.col('yq').max())
                 .unpivot(
                     index=['yq'],
                     value_name='value',
                     variable_name='cong_ty'
                 ).filter(pl.col('cong_ty').is_in(TOPNHNN) | pl.col('cong_ty').is_in(TOPNHTM))
                 .sort('value', descending=True))
    
    col_order1 = col_order.get_column('cong_ty').to_list()
    col_order2 = [i for i in df_result.columns if i not in ['yq'] + TOPNH]

    df_result = (df_result
                 .select(
                     'yq',
                     cs.by_name(col_order1),
                     cs.by_name(col_order2)
                 ))

    return(df_result.sort(by='yq', descending=False))