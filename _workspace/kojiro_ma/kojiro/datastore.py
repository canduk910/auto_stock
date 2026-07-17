"""종목마스터DB 접근 어댑터.

이미 보유한 DB가 무엇이든 DataStore 프로토콜(list_codes / get_daily / get_master)만
구현하면 스크리너·러너가 그대로 동작한다. 기본 구현은 sqlite.

기대 스키마 (sqlite 기본 구현 기준 — 컬럼명이 다르면 SQL만 수정):
    stock_master(code TEXT PK, name TEXT, market_cap REAL, per REAL, pbr REAL, sector TEXT)
    daily_price(code TEXT, date TEXT(YYYYMMDD), open REAL, high REAL, low REAL,
                close REAL, volume INTEGER, PRIMARY KEY(code, date))
"""
import sqlite3
from typing import Protocol

import pandas as pd


class DataStore(Protocol):
    def list_codes(self) -> list[str]: ...
    def get_daily(self, code: str, n_bars: int = 150) -> pd.DataFrame:
        """날짜 오름차순 OHLCV. index=date, columns=open/high/low/close/volume."""
        ...
    def get_master(self, code: str) -> dict:
        """{'name':…, 'market_cap':…, 'per':…, 'pbr':…, 'sector':…} — 없는 값은 None."""
        ...


class SqliteStore:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def list_codes(self) -> list[str]:
        rows = self.conn.execute("SELECT code FROM stock_master").fetchall()
        return [r["code"] for r in rows]

    def get_daily(self, code: str, n_bars: int = 150) -> pd.DataFrame:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM daily_price "
            "WHERE code = ? ORDER BY date DESC LIMIT ?",
            self.conn, params=(code, n_bars),
        )
        return df.sort_values("date").set_index("date")

    def get_master(self, code: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM stock_master WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else {}
