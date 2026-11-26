import polars as pl
from src.config import *
from src.d1_pusher import push_dataframe_to_d1
from pyprojroot.here import here
from src.janitorvn import clean_names_vn

from dotenv import load_dotenv
load_dotenv()

df_m2 = pl.read_excel(here('data/data-manual/data_manual.xlsx'), sheet_name='M2')
df_m2 = clean_names_vn(df_m2)

df_m2 = (
    df_m2.filter(pl.col('item').str.contains('Tiền gửi'))
    .with_columns(
        pl.date(pl.col('year'), pl.col('month'), 1).alias('ym')
    )
    .group_by(pl.col('ym'))
    .agg(
        pl.col('so_du').sum().alias('tien_gui')
    )
    .sort(pl.col('ym'))
)


df_credit = pl.read_excel(here('data/data-manual/data_manual.xlsx'), sheet_name='CREDIT')
df_credit = clean_names_vn(df_credit)

df_credit = (
    df_credit.filter(pl.col('item') == 'TỔNG CỘNG')
    .with_columns(
        pl.date(pl.col('year'), pl.col('month'), 1).alias('ym')
    )
    .group_by(pl.col('ym'))
    .agg(pl.col('so_du').sum().alias('tin_dung'))
    .sort(pl.col('ym'))
)


push_dataframe_to_d1(df=df_m2, table='tien_gui_total')
push_dataframe_to_d1(df=df_credit, table='tin_dung_total')