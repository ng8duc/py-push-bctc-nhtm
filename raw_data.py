from src.data_readers import read_multiple_file
from pyprojroot.here import here
from src.config import *
import polars as pl

frames = []

for company in TOPNH:

    try:
        df_q = read_multiple_file(folder=here('data/data-quarterly'), company_name=company)
    except Exception:
        df_q = pl.DataFrame()

    if not df_q.is_empty():
        frames.append(df_q)

df = pl.concat(frames, how='diagonal_relaxed')

df.write_excel('raw_data.xlsx')