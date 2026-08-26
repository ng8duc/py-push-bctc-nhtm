import json
import logging
import os
import shutil
import subprocess
import tempfile

import polars as pl
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _escape_sql_literal(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _normalize_temporal_columns(df: pl.DataFrame) -> pl.DataFrame:
    exprs = []
    for name, dtype in df.schema.items():
        if dtype == pl.Date:
            exprs.append(pl.col(name).dt.strftime('%Y-%m-%d'))
        elif isinstance(dtype, pl.Datetime):
            exprs.append(pl.col(name).dt.strftime('%Y-%m-%d %H:%M:%S'))
    return df.with_columns(exprs) if exprs else df


def _sql_type_for_dtype(dtype: pl.DataType) -> str:
    if dtype == pl.Boolean or dtype.is_integer():
        return 'INTEGER'
    if dtype.is_float():
        return 'REAL'
    return 'TEXT'


def _build_create_table_statement(df: pl.DataFrame, table: str) -> str:
    cols_sql = ', '.join(f'"{name}" {_sql_type_for_dtype(dtype)}' for name, dtype in df.schema.items())
    return f'CREATE TABLE "{table}" ({cols_sql});'


def _build_insert_statements(df: pl.DataFrame, table: str, batch_size: int) -> list[str]:
    columns = df.columns
    col_list = ', '.join(f'"{c}"' for c in columns)

    statements = []
    rows = df.rows()
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        values_sql = ', '.join(
            '(' + ', '.join(_escape_sql_literal(v) for v in row) + ')'
            for row in chunk
        )
        statements.append(f'INSERT INTO "{table}" ({col_list}) VALUES {values_sql};')

    return statements


def _run_wrangler(args: list[str], env: dict) -> str:
    npx_path = shutil.which('npx') or 'npx'
    result = subprocess.run(
        [npx_path, 'wrangler', 'd1', 'execute', *args],
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if result.returncode != 0:
        raise RuntimeError(f'wrangler d1 execute thất bại:\n{result.stdout}\n{result.stderr}')
    return result.stdout


def _table_exists(database: str, table: str, env: dict) -> bool:
    command = f"SELECT name FROM sqlite_master WHERE type='table' AND name={_escape_sql_literal(table)};"
    stdout = _run_wrangler([database, '--remote', '--command', command, '--json'], env=env)
    payload = json.loads(stdout)
    return len(payload[0]['results']) > 0


def push_dataframe_to_d1(df: pl.DataFrame, table: str, *, batch_size: int = 200) -> None:
    load_dotenv()

    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
    api_token = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    database = os.environ.get('D1_DATABASE', '')

    if not account_id or not api_token or not database:
        logger.warning(
            'Bỏ qua đẩy bảng "%s" lên D1: thiếu CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN/D1_DATABASE trong .env',
            table,
        )
        return

    if df.is_empty():
        return

    df = _normalize_temporal_columns(df)

    env = os.environ.copy()
    env['CLOUDFLARE_ACCOUNT_ID'] = account_id
    env['CLOUDFLARE_API_TOKEN'] = api_token

    logger.info('Đang đẩy bảng "%s" lên D1 (%d dòng)...', table, df.height)

    statements = []
    if _table_exists(database, table, env):
        statements.append(f'DROP TABLE "{table}";')
    statements.append(_build_create_table_statement(df, table))
    statements.extend(_build_insert_statements(df, table=table, batch_size=batch_size))

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write('\n'.join(statements))
        sql_path = f.name

    try:
        _run_wrangler([database, '--remote', '--file', sql_path], env=env)
    finally:
        os.remove(sql_path)

    logger.info('Đã đẩy xong bảng "%s" lên D1.', table)
