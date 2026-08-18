from src.data_readers import read_multiple_file
from src.data_wranglers import gen_cumulative_data
from pyprojroot.here import here


df = read_multiple_file(folder=here('data/data-quarterly'), company_name='BID')

print(df)

df_cum = gen_cumulative_data(df=df, year=2026, quarter=2)

print(df_cum)
