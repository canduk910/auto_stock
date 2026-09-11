"""cycle276 Red — DB 계층: 마이그레이션 043 · `llm_buy_evaluations` CRUD · `get_trade_pairs` 확장.

명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §1-C (C31~C36·C41) · §2 · §3 · §4 · §9.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 세 덩어리

1. **마이그레이션 043** — 가산형(신규 테이블 + 인덱스 + COMMENT). `deploy.yml` 이 매 push 마다
   전 마이그레이션을 재적용하고 `ON_ERROR_STOP=0 + || true` 로 오류를 삼키므로
   `IF NOT EXISTS` 가 **필수**다 — 없으면 두 번째 배포부터 조용히 실패하고 운영에는
   테이블이 없는 채로 남는다(031·042 선례).
2. **`src/db/llm_buy_evaluations.py`** — asyncpg 바인딩 규약(C34). DATE 은 `to_date()`,
   TIMESTAMPTZ 은 **aware `datetime`**, JSONB 는 **raw dict**(`json.dumps` 금지).
   ⚠️ `now_kst_iso()`(str)를 TIMESTAMPTZ 에 넘기면 mock 은 전건 초록인데 실 PG 에서만
   `DataError` 다(cycle273a HIGH#1 재현 경로) — 그래서 이 파일은 **바인딩 인자의 타입**을 잰다.
3. **`get_trade_pairs`** — 기존 15키·페어링 알고리즘 불변 + `buy_order_nos`/`sell_order_nos`/
   `pair_key` 3키 추가. 운영 DB 실측에서 **한 페어가 매수 주문 2건 이상**인 사례가 9건이라
   단수 필드로는 못 담는다(명세 §8).

## 모듈 부재 정책

`src.db.llm_buy_evaluations` 는 아직 없다. `pytest.importorskip` 을 쓰지 않는다 — skip 은
Red 가 아니다. 각 테스트 본문에서 `importlib` 로 열어 `ModuleNotFoundError` 로 정직하게 FAILED.
"""

from __future__ import annotations

import ast
import importlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_ROOT = Path(__file__).resolve().parents[3]
_MIGRATIONS = _ROOT / "supabase" / "migrations"
_MIGRATION_043 = _MIGRATIONS / "043_llm_buy_evaluations.sql"
_PG_HARNESS = _ROOT / "tests" / "integration" / "pg_harness.py"
_TRADE_HISTORY_SRC = _ROOT / "src" / "db" / "trade_history.py"

_DB_MOD = "src.db.llm_buy_evaluations"

_TABLE = "llm_buy_evaluations"
_ORDER_NO = "0000123456"
_TICKER = "005930"
_ACCOUNT = "12345678"
_TRADE_DATE_STR = "2026-09-11"
_TRADE_DATE = date(2026, 9, 11)
_ORDER_KST = datetime(2026, 9, 11, 9, 1, 31, tzinfo=KST)

# 명세 §2 CREATE TABLE 의 열 전수(53). 이름 하나라도 빠지면 회고분석이 사후 복원 불가해진다.
_COLUMNS = (
    "trade_date", "account_no", "ticker", "order_no",
    "eval_kind", "account_product", "strategy_id", "mode", "result", "reason",
    "score", "min_score", "would_block", "rationale", "key_risks", "invalidations",
    "model", "tokens_in", "tokens_out", "cost_usd", "latency_ms", "verdict_lag_ms",
    "eval_to_order_lag_ms", "order_kst", "evaluated_at",
    "order_price_won", "ordered_qty", "order_notional_won", "order_division",
    "order_path", "exchange", "board", "current_price_won",
    "signal_matched", "signal_price_won", "signal_time_local", "strategy_board",
    "target_won", "k", "breakout_excess_bp",
    "post_order_drift_bp", "drift_price_won", "tick_age_s",
    "budget_total_won", "budget_remaining_after_won", "open_positions_n",
    "prompt_version", "feature_version", "bars_count", "input_payload", "raw_response",
    "created_at", "updated_at",
)

_INDEXES = (
    "idx_llm_eval_trade_date",
    "idx_llm_eval_strategy_date",
    "idx_llm_eval_ticker_date",
    "idx_llm_eval_order_no",
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _sql() -> str:
    assert _MIGRATION_043.exists(), (
        "supabase/migrations/043_llm_buy_evaluations.sql 이 없다 — 명세 §2 미이행(Red)"
    )
    return _MIGRATION_043.read_text(encoding="utf-8")


def _norm(sql: str) -> str:
    """대소문자·공백을 눌러 문장 패턴만 남긴다(서식 차이로 가드가 붉어지지 않게)."""
    return re.sub(r"\s+", " ", sql.lower())


def _strip_comments(sql: str) -> str:
    """`--` 줄 주석 제거 — 주석 안의 `drop`/`alter` 어휘가 파괴 문장으로 오판되지 않게."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _mod():
    """`src.db.llm_buy_evaluations` — 부재면 `ModuleNotFoundError`(= 정직한 Red)."""
    return importlib.import_module(_DB_MOD)


def _sample_kwargs(**over) -> dict:
    """`upsert_evaluation` 최소 호출 인자(명세 §4 시그니처의 필수 키)."""
    kw = dict(
        trade_date=_TRADE_DATE_STR,
        account_no=_ACCOUNT,
        ticker=_TICKER,
        order_no=_ORDER_NO,
        strategy_id="volatility_breakout",
        mode="shadow",
        result="ok",
        min_score=70,
        order_kst=_ORDER_KST,
        order_price_won=71_800,
        ordered_qty=3,
        order_notional_won=215_400,
        order_division="MARKET",
        order_path="market",
        board="main",
        input_payload={"payload": {"ticker": _TICKER}, "tech": {}, "bars30": []},
    )
    kw.update(over)
    return kw


# ===========================================================================
# 마이그레이션 043 (C31~C33)
# ===========================================================================
def test_m1_file_exists_and_number_is_043() -> None:
    """§2 — 번호 재배정: cycle276 이 043, cycle275(입출금 T+2)는 044 로 밀린다.

    두 사이클이 같은 번호를 쓰면 늦게 병합된 쪽이 조용히 덮인다.
    """
    assert _MIGRATION_043.exists(), "043_llm_buy_evaluations.sql 이 없다(Red)"
    others = [
        p.name for p in _MIGRATIONS.glob("043_*.sql") if p.name != _MIGRATION_043.name
    ]
    assert not others, f"043 번호를 쓰는 다른 파일이 있다: {others}"


def test_m2_create_table_if_not_exists() -> None:
    """C31 (뮤테이션 M13) — `CREATE TABLE IF NOT EXISTS`.

    `deploy.yml` 이 매 push 마다 전 마이그레이션을 재적용하고 오류를 삼킨다 —
    idempotent 가 아니면 **두 번째 배포부터** 조용히 실패한다.
    """
    assert f"create table if not exists {_TABLE}" in _norm(_sql())


def test_m3_primary_key_is_four_columns() -> None:
    """C32 (뮤테이션 M11) — PK `(trade_date, account_no, ticker, order_no)`.

    KIS ODNO 는 **하루 단위로만** 유일하다(`reset_daily_state` docstring) — 날짜가
    PK 선두에서 빠지면 다음 날 같은 주문번호가 어제 행을 덮는다.
    """
    assert "primary key (trade_date, account_no, ticker, order_no)" in _norm(_sql())


@pytest.mark.parametrize("col", _COLUMNS)
def test_m4_all_53_columns_present(col: str) -> None:
    """§3 — 열 전수. 회고분석 전제(버전 고정·예산·원문·payload)는 사후 복원이 불가하다."""
    norm = _norm(_sql())
    assert re.search(rf"(?<![a-z_]){re.escape(col)}\s", norm), f"열 `{col}` 이 없다"


def test_m5_column_count_is_53() -> None:
    """§3 — 열 개수 53. 명세 표와 SQL 이 갈라지는 것을 막는다."""
    assert len(_COLUMNS) == 53


def test_m6_order_no_is_not_null_default_empty() -> None:
    """C32 (뮤테이션 M12) — `order_no text not null default ''`.

    NULL 을 허용하면 PK 가 통째로 사라지고(NULL 은 유일성 판정 밖) 같은 주문이 여러 행이 된다.
    """
    assert re.search(r"order_no\s+text\s+not null\s+default\s+''", _norm(_sql())), (
        "`order_no TEXT NOT NULL DEFAULT ''` 선언을 찾지 못했다"
    )


def test_m7_eval_kind_defaults_to_order() -> None:
    """C33 (자문 R2) — `eval_kind` 가 처음부터 있다.

    운영 DB 에 이미 있는 `order_no=''` 수기 체결 행과 미래의 "차단되어 주문이 없는 평가"가
    같은 PK 공간을 쓰는 충돌을 **지금** 분리한다.
    """
    assert re.search(r"eval_kind\s+text\s+not null\s+default\s+'order'", _norm(_sql()))


@pytest.mark.parametrize("idx", _INDEXES)
def test_m8_four_indexes_if_not_exists(idx: str) -> None:
    """§2 (뮤테이션 M13) — 인덱스 4개 전부 `CREATE INDEX IF NOT EXISTS`."""
    assert f"create index if not exists {idx}" in _norm(_sql()), f"인덱스 `{idx}` 누락"


def test_m9_order_no_index_is_partial() -> None:
    """§2 — `order_no` 인덱스는 `WHERE order_no <> ''` 부분 인덱스.

    PK 선두가 `trade_date` 라 UI 의 `order_no` 단독 조회를 PK 인덱스가 커버하지 못한다.
    빈 값 행은 조회 대상이 아니므로 인덱스에서 뺀다.
    """
    norm = _norm(_sql())
    m = re.search(r"create index if not exists idx_llm_eval_order_no(.*?);", norm, re.S)
    assert m, "`idx_llm_eval_order_no` 정의를 찾지 못했다"
    assert "where order_no <> ''" in m.group(1), "부분 인덱스 조건이 없다"


def test_m10_no_destructive_statements() -> None:
    """C31 — `ALTER`/`DROP`/`UPDATE`/`DELETE`/`TRUNCATE` 0건(가산형 증명).

    기존 테이블을 건드리는 문장이 하나라도 있으면 재적용마다 운영 데이터가 흔들린다.
    """
    body = _norm(_strip_comments(_sql()))
    bad = [kw for kw in ("alter table", "drop table", "drop index", "truncate",
                         "update ", "delete from") if kw in body]
    assert not bad, f"파괴적 문장 발견: {bad}"


def test_m11_pg_harness_docstrings_mention_043() -> None:
    """§11 — `pg_harness.py` 문면 3곳이 043 을 반영한다(적용 로직은 glob 이라 변경 0).

    문면과 실제 적용 범위가 갈라지면 다음 사이클이 "042까지만 적용된다" 는 전제로 얹인다.
    """
    text = _PG_HARNESS.read_text(encoding="utf-8")
    assert "043" in text, "`pg_harness.py` 문면이 아직 042 를 말한다"
    assert "001~042" not in text, "`001~042` 문면이 남아 있다"


# ===========================================================================
# `src/db/llm_buy_evaluations.py` — 바인딩 규약 (C34~C36)
# ===========================================================================
async def test_d1_upsert_binds_date_via_to_date() -> None:
    """C34 (M6 사고 재발 방지) — `trade_date` 는 **`date` 객체**로 바인딩된다.

    asyncpg 는 DATE 컬럼에 `str` 을 받으면 `'str' object has no attribute 'toordinal'`
    로 즉시 실패한다. 호출자가 문자열을 줘도 db 모듈이 `to_date()` 로 강제한다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs(trade_date=_TRADE_DATE_STR))

    args = pg.fetchrow.await_args.args[1:]
    assert _TRADE_DATE in args, f"`date` 객체 바인딩이 없다: {[type(a).__name__ for a in args]}"
    assert _TRADE_DATE_STR not in args, "`trade_date` 를 문자열로 바인딩했다"


async def test_d2_upsert_binds_timestamptz_as_aware_datetime() -> None:
    """C34 (cycle273a HIGH#1) — TIMESTAMPTZ 3열은 **aware `datetime`** 이다.

    `now_kst_iso()`(str)를 넘기면 mock 은 전건 초록인데 실 PG 에서만 `DataError` 가 난다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs())

    args = pg.fetchrow.await_args.args[1:]
    dts = [a for a in args if isinstance(a, datetime)]
    assert len(dts) >= 3, (
        f"aware datetime 바인딩 {len(dts)}건 (order_kst + created_at + updated_at ≥ 3)"
    )
    assert all(d.tzinfo is not None for d in dts), "naive datetime 이 섞였다 — KST 강제 위반"
    assert _ORDER_KST in dts, "`order_kst` 인자가 그대로 바인딩되지 않았다"
    assert not [a for a in args if isinstance(a, str) and a.endswith("+09:00")], (
        "ISO 문자열이 TIMESTAMPTZ 자리에 바인딩됐다(str 금지)"
    )


async def test_d2a_str_timestamptz_arg_is_coerced_to_datetime() -> None:
    """C34 — 호출자가 TIMESTAMPTZ 를 **ISO 문자열**로 줘도 `datetime` 으로 강제된다.

    이 케이스가 없으면 `_to_dt` 의 `isinstance(value, str)` 분기를 지워도(뮤테이션)
    전건 초록이다 — mock 은 무엇이든 받아 주고, 실 PG 만 `DataError` 로 죽는다
    (cycle273a HIGH#1 재현 경로). 그래서 **str 을 실제로 넣어** 바인딩 타입을 잰다.
    실 PG 왕복은 `tests/integration/test_cycle276_llm_eval_pg_roundtrip.py::test_i14`.
    """
    mod = _mod()
    iso = "2026-09-11T09:01:31.032000+09:00"
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs(order_kst=iso, evaluated_at=iso))

    args = pg.fetchrow.await_args.args[1:]
    assert iso not in args, "ISO 문자열이 TIMESTAMPTZ 자리에 그대로 바인딩됐다(실 PG 에서 DataError)"
    coerced = datetime.fromisoformat(iso)
    assert args.count(coerced) >= 2, (
        f"`order_kst`/`evaluated_at` 이 datetime 으로 강제되지 않았다: "
        f"{[type(a).__name__ for a in args]}"
    )


async def test_d2b_unsupported_timestamptz_type_raises_typeerror() -> None:
    """C34 — TIMESTAMPTZ 에 미지 타입(int 등)이 오면 **TypeError 로 시끄럽게** 죽는다.

    조용히 통과시키면(뮤테이션: `raise TypeError` → `return value`) asyncpg 가 던지는
    `DataError` 로 대체되는데, 그 예외는 `_persist_evaluation` 이 흡수해
    `[llm_eval_persist] result=error reason=DataError` 한 줄로만 남는다 — 어느 열이
    문제인지 잃는다. 여기서 던지면 값·열 이름이 메시지에 남는다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        with pytest.raises(TypeError) as exc:
            await mod.upsert_evaluation(**_sample_kwargs(evaluated_at=5))

    assert "TIMESTAMPTZ" in str(exc.value), f"예상과 다른 메시지: {exc.value!r}"
    assert pg.fetchrow.await_count == 0, "타입 위반인데 DB 를 두드렸다"


async def test_d3_upsert_binds_jsonb_as_raw_dict() -> None:
    """C34/C35 — JSONB 4열은 **raw dict/list** 로 바인딩된다(`json.dumps` 사전 적용 금지).

    `pg._init_conn` 의 codec 이 왕복을 책임진다 — 호출부가 문자열로 미리 말아 넣으면
    읽을 때 `str` 이 돌아와 `isinstance(x, dict)` 분기가 전부 조용히 폴백한다.
    """
    mod = _mod()
    payload = {"payload": {"ticker": _TICKER}, "tech": {"rsi14": 61.2}, "bars30": []}
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs(
            input_payload=payload,
            key_risks=["되돌림"],
            invalidations=["목표가 이탈"],
            raw_response={"content": "{\"score\": 62}"},
        ))

    args = pg.fetchrow.await_args.args[1:]
    assert payload in args, "`input_payload` 가 raw dict 로 바인딩되지 않았다"
    assert ["되돌림"] in args and ["목표가 이탈"] in args
    assert {"content": "{\"score\": 62}"} in args
    assert not [a for a in args if isinstance(a, str) and a.startswith("{\"payload\"")], (
        "JSONB 를 `json.dumps` 로 미리 말아 넣었다"
    )


async def test_d4_upsert_normalizes_none_order_no_to_empty() -> None:
    """§4 — `order_no=None` → `""`(NULL 로 PK 가 사라지는 사고 차단)."""
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": ""})
        await mod.upsert_evaluation(**_sample_kwargs(order_no=None))

    args = pg.fetchrow.await_args.args[1:]
    assert "" in args, "`order_no=None` 이 빈 문자열로 정규화되지 않았다"
    assert None not in args[:4], "PK 자리에 NULL 이 바인딩됐다"


async def test_d5_upsert_sql_on_conflict_targets_pk() -> None:
    """§4 (뮤테이션 M11) — `ON CONFLICT (trade_date, account_no, ticker, order_no)`."""
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs())

    sql = _norm(pg.fetchrow.await_args.args[0])
    assert "on conflict (trade_date, account_no, ticker, order_no) do update" in sql
    assert "returning *" in sql


async def test_d6_upsert_do_update_excludes_created_at() -> None:
    """§4 — `DO UPDATE SET` 에 `created_at` 이 없다(최초 기록 시각 보존).

    갱신마다 `created_at` 이 밀리면 "언제 처음 기록됐나" 가 사라진다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.upsert_evaluation(**_sample_kwargs())

    sql = _norm(pg.fetchrow.await_args.args[0])
    set_clause = sql.split("do update set", 1)[1].split("returning", 1)[0]
    assert "created_at" not in set_clause, "`DO UPDATE SET` 이 `created_at` 을 덮는다"
    assert "updated_at" in set_clause, "`updated_at` 갱신이 없다"


async def test_d7_get_by_order_returns_latest_when_no_date() -> None:
    """§5.1 — `trade_date` 미지정이면 **가장 최근** 1건.

    KIS ODNO 는 날짜별로만 유일하므로 같은 번호가 여러 날짜에 존재할 수 있다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO, "trade_date": _TRADE_DATE})
        row = await mod.get_by_order(_ORDER_NO)

    assert row is not None and row["order_no"] == _ORDER_NO
    sql = _norm(pg.fetchrow.await_args.args[0])
    assert "order by trade_date desc" in sql, "최신 우선 정렬이 없다"
    assert "limit 1" in sql


async def test_d8_get_by_order_with_trade_date_narrows() -> None:
    """§5.1 — `trade_date` 를 주면 그 날짜로 좁히고, `date` 객체로 바인딩한다."""
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.get_by_order(_ORDER_NO, trade_date=_TRADE_DATE_STR)

    args = pg.fetchrow.await_args.args[1:]
    assert _ORDER_NO in args and _TRADE_DATE in args, (
        f"주문번호·날짜 바인딩 누락: {args!r}"
    )


async def test_d9_list_by_order_nos_uses_any_text_array() -> None:
    """§4 — 배치 조회는 `= ANY($1::text[])`(IN 목록 문자열 조립 금지)."""
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetch = AsyncMock(return_value=[{"order_no": _ORDER_NO}])
        rows = await mod.list_by_order_nos([_ORDER_NO, "0000123457"])

    assert len(rows) == 1
    sql = _norm(pg.fetch.await_args.args[0])
    assert "= any($1::text[])" in sql, "`= ANY($1::text[])` 바인딩이 아니다"
    assert [_ORDER_NO, "0000123457"] in pg.fetch.await_args.args[1:]


async def test_d10_list_by_order_nos_empty_input_skips_query() -> None:
    """§4 — 빈 목록이면 **쿼리 없이** `[]`(빈 배치가 전체 스캔이 되지 않게)."""
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetch = AsyncMock(return_value=[])
        rows = await mod.list_by_order_nos([])

    assert rows == []
    assert pg.fetch.await_count == 0, "빈 입력에도 DB 를 두드렸다"


async def test_d10b_list_by_order_nos_keeps_every_date_row() -> None:
    """B-2 (cycle276 후속) — 같은 주문번호의 **여러 날짜 행을 접지 않는다**.

    종전 구현은 `trade_date DESC` 첫 등장만 남겨 주문번호당 1행으로 접었다. KIS ODNO 는
    하루 단위로만 유일하므로 그 접기는 오래된 날짜의 평가를 응답에서 지운다 — 그 날짜의
    거래 행은 "평가 기록 없음"(버튼 비활성)이 되는데, 상세 조회(`get_by_order(...,
    trade_date=…)`)로는 멀쩡히 읽힌다. 배치와 상세의 날짜 축 비대칭이 화면의 거짓말이다.
    """
    mod = _mod()
    rows_in = [
        {"order_no": _ORDER_NO, "trade_date": date(2026, 9, 11)},
        {"order_no": _ORDER_NO, "trade_date": date(2026, 9, 8)},
        {"order_no": "0000123457", "trade_date": date(2026, 9, 11)},
    ]
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetch = AsyncMock(return_value=rows_in)
        rows = await mod.list_by_order_nos([_ORDER_NO, "0000123457"])

    assert len(rows) == 3, f"행을 접었다 — {len(rows)}행(기대 3)"
    assert [(r["order_no"], r["trade_date"]) for r in rows] == [
        (_ORDER_NO, date(2026, 9, 11)),
        (_ORDER_NO, date(2026, 9, 8)),
        ("0000123457", date(2026, 9, 11)),
    ], "정렬(trade_date DESC)이 보존되지 않았다"


async def test_d11_read_functions_project_iso_aliases() -> None:
    """§4 — 읽기 SQL 은 `+09:00` ISO 별칭 3개를 함께 사영한다.

    프론트가 `Intl.DateTimeFormat(timeZone:'Asia/Seoul')` 로 그리는 계약의 원천이고,
    `new Date(iso).getHours()` 로컬타임 추출 금지 규약과 짝을 이룬다.
    """
    mod = _mod()
    with patch.object(mod, "pg", create=True) as pg:
        pg.fetchrow = AsyncMock(return_value={"order_no": _ORDER_NO})
        await mod.get_by_order(_ORDER_NO)

    sql = _norm(pg.fetchrow.await_args.args[0])
    for alias in ("order_kst_iso", "evaluated_at_iso", "created_at_iso"):
        assert alias in sql, f"ISO 별칭 `{alias}` 사영 누락"
    assert "+09:00" in sql, "`to_char(..., '+09:00')` 렌더가 없다"


def test_d12_module_uses_kst_helpers_not_raw_strings() -> None:
    """C34 — db 모듈이 `_kst` 헬퍼(`to_date`/`now_kst_iso`)를 import 한다.

    G-10b 계열 규약 — 헬퍼 미사용은 곧 시각·날짜 바인딩이 손으로 조립됐다는 뜻이다.
    """
    src = (_ROOT / "src" / "db" / "llm_buy_evaluations.py")
    assert src.exists(), "`src/db/llm_buy_evaluations.py` 가 없다(Red)"
    text = src.read_text(encoding="utf-8")
    assert "from src.db._kst import" in text, "`src.db._kst` 헬퍼를 쓰지 않는다"
    assert "to_date" in text and "now_kst_iso" in text


# ===========================================================================
# `get_trade_pairs` 확장 (C41)
# ===========================================================================
def _trade(ttype: str, price: int, qty: int, ts: str, *, order_no: str,
           ticker: str = _TICKER, strategy: str = "volatility_breakout") -> dict:
    """`SELECT t.*` 한 행 — `_TS_SELECT` 가 timestamp 를 `+09:00` ISO 로 렌더한다."""
    return {
        "ticker": ticker,
        "ticker_name": "삼성전자",
        "trade_type": ttype,
        "price": price,
        "quantity": qty,
        "status": "COMPLETED",
        "strategy": strategy,
        "order_no": order_no,
        "timestamp": ts,
    }


async def _pairs(rows: list[dict]) -> list[dict]:
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg:
        pg.fetch = AsyncMock(return_value=rows)
        return await th.get_trade_pairs()


# ⚠️ 명세 §9.1 은 "기존 15키" 라고 적었으나 `emit_closed` 가 실제로 내보내는 키는 **14개**다
# (아래 집합이 실측 정본). 개수 문면 하나가 어긋나면 다음 사이클이 "하나가 사라졌다" 고 오판한다.
_BASE_KEYS = {
    "buy_date", "buy_time", "sell_date", "sell_time", "ticker", "ticker_name",
    "buy_price", "buy_qty", "sell_price", "sell_qty",
    "profit_loss", "profit_rate", "status", "strategy",
}


async def test_p1_existing_keys_and_values_unchanged() -> None:
    """C41 (회귀) — 기존 키의 이름·타입·값이 그대로다. 추가는 3키뿐."""
    rows = [
        _trade("BUY", 10_000, 2, "2026-09-11T09:01:31.000000+09:00", order_no="B1"),
        _trade("SELL", 11_000, 2, "2026-09-11T15:20:02.000000+09:00", order_no="S1"),
    ]
    pairs = await _pairs(rows)

    assert len(pairs) == 1
    p = pairs[0]
    assert len(_BASE_KEYS) == 14, "기존 키 정본이 14개라는 전제가 깨졌다"
    assert _BASE_KEYS <= set(p), f"기존 키가 사라졌다: {sorted(_BASE_KEYS - set(p))}"
    added = set(p) - _BASE_KEYS
    assert added == {"buy_order_nos", "sell_order_nos", "pair_key"}, (
        f"추가 키가 계약과 다르다 — 실제 {sorted(added)}"
    )
    assert p["buy_price"] == 10_000.0 and p["sell_price"] == 11_000.0
    assert p["buy_qty"] == 2 and p["sell_qty"] == 2
    assert p["profit_loss"] == 2_000.0
    assert p["status"] == "closed"


async def test_p2_buy_order_nos_are_time_ascending() -> None:
    """§9.1 — 분할 매수 2건 → `buy_order_nos` 가 **시간 오름차순** 2개.

    첫 매수 주문번호가 그 사이클을 유일하게 식별하므로 순서가 곧 의미다.
    """
    rows = [
        _trade("BUY", 10_000, 1, "2026-09-11T09:01:31.000000+09:00", order_no="B1"),
        _trade("BUY", 10_200, 1, "2026-09-11T10:11:02.000000+09:00", order_no="B2"),
        _trade("SELL", 11_000, 2, "2026-09-11T15:20:02.000000+09:00", order_no="S1"),
    ]
    pairs = await _pairs(rows)

    assert len(pairs) == 1
    assert pairs[0]["buy_order_nos"] == ["B1", "B2"]
    assert pairs[0]["sell_order_nos"] == ["S1"]


async def test_p3_empty_order_no_excluded_but_row_kept() -> None:
    """§9.1 — 주문번호 없는 체결(수기 매매 등)은 **목록에서만** 빠지고 행은 그대로다.

    운영 DB 실측 9행이 빈 `order_no` 다 — 그 페어를 통째로 지우면 손익 화면에서
    거래가 사라진다.
    """
    rows = [
        _trade("BUY", 10_000, 1, "2026-09-11T09:01:31.000000+09:00", order_no=""),
        _trade("BUY", 10_200, 1, "2026-09-11T10:11:02.000000+09:00", order_no="B2"),
        _trade("SELL", 11_000, 2, "2026-09-11T15:20:02.000000+09:00", order_no="S1"),
    ]
    pairs = await _pairs(rows)

    assert len(pairs) == 1, "빈 주문번호 때문에 페어가 사라졌다"
    assert pairs[0]["buy_order_nos"] == ["B2"]
    assert pairs[0]["buy_qty"] == 2, "체결 수량 집계는 빈 주문번호와 무관하게 유지된다"


async def test_p4_pair_key_is_strategy_ticker_first_buy() -> None:
    """§9.1 — `pair_key = f"{strategy}:{ticker}:{첫 매수 order_no}"`.

    페어는 어디에도 저장되지 않으므로(매번 계산) 안정적 식별자가 필요하다.
    """
    rows = [
        _trade("BUY", 10_000, 1, "2026-09-11T09:01:31.000000+09:00", order_no="B1"),
        _trade("SELL", 11_000, 1, "2026-09-11T15:20:02.000000+09:00", order_no="S1"),
    ]
    pairs = await _pairs(rows)

    assert pairs[0]["pair_key"] == f"volatility_breakout:{_TICKER}:B1"


async def test_p5_pair_key_is_none_when_no_order_no() -> None:
    """§9.1 — 매수 주문번호가 하나도 없으면 `pair_key=None`(UI 버튼 비활성 근거)."""
    rows = [
        _trade("BUY", 10_000, 1, "2026-09-11T09:01:31.000000+09:00", order_no=""),
        _trade("SELL", 11_000, 1, "2026-09-11T15:20:02.000000+09:00", order_no=""),
    ]
    pairs = await _pairs(rows)

    assert pairs[0]["buy_order_nos"] == []
    assert pairs[0]["pair_key"] is None


async def test_p6_open_pair_sell_order_nos_is_empty_list() -> None:
    """§9.1 — open 페어의 `sell_order_nos` 는 `[]`(`None` 아님).

    프론트가 `.some(...)` 로 읽으므로 `None` 이면 런타임에서 죽는다.
    """
    rows = [
        _trade("BUY", 10_000, 1, "2026-09-11T09:01:31.000000+09:00", order_no="B1"),
    ]
    pairs = await _pairs(rows)

    assert len(pairs) == 1 and pairs[0]["status"] == "open"
    assert pairs[0]["sell_order_nos"] == []
    assert pairs[0]["buy_order_nos"] == ["B1"]
    assert pairs[0]["pair_key"] == f"volatility_breakout:{_TICKER}:B1"


async def test_p7_multiple_cycles_do_not_leak_order_nos() -> None:
    """C41 — 같은 (종목, 전략) 3사이클 → 각 페어가 **자기 주문만** 갖는다.

    버퍼 리셋을 한 곳이라도 빠뜨리면 앞 사이클의 주문번호가 뒤 페어로 샌다
    (운영 실측 034020 VB 는 7사이클이다).
    """
    rows = []
    for i in (1, 2, 3):
        rows.append(_trade("BUY", 10_000 + i, 1, f"2026-09-1{i}T09:01:31.000000+09:00",
                           order_no=f"B{i}"))
        rows.append(_trade("SELL", 11_000 + i, 1, f"2026-09-1{i}T15:20:02.000000+09:00",
                           order_no=f"S{i}"))
    pairs = await _pairs(rows)

    assert len(pairs) == 3
    got = sorted((p["buy_order_nos"][0], p["sell_order_nos"][0]) for p in pairs)
    assert got == [("B1", "S1"), ("B2", "S2"), ("B3", "S3")], f"주문번호 누수: {got}"


def test_p8_buffer_tuple_arity_unchanged() -> None:
    """C41 (뮤테이션 M18) — `buy_buf`/`sell_buf` 튜플 요소 수 **3 유지**.

    4-튜플로 바꾸면 언패킹 지점 5곳 이상을 동시에 고쳐야 하고, 한 곳만 놓쳐도
    매매손익 뷰가 통째로 500 이 된다. 주문번호는 **병행 리스트**로 담는다.
    """
    src = _TRADE_HISTORY_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "get_trade_pairs"),
        None,
    )
    assert fn is not None, "`get_trade_pairs` 를 찾지 못했다"

    arities = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "append" \
                and isinstance(n.func.value, ast.Name) \
                and n.func.value.id in {"buy_buf", "sell_buf"}:
            assert len(n.args) == 1 and isinstance(n.args[0], ast.Tuple), (
                f"line {n.lineno}: 버퍼 append 인자가 튜플이 아니다"
            )
            arities.add(len(n.args[0].elts))
    assert arities == {3}, f"버퍼 튜플 arity {arities} (기대 {{3}})"


def test_p9_history_route_stays_untouched() -> None:
    """§9.4 — `src/routes/history.py` 는 **0줄 변경**.

    `pairs` 를 그대로 통과시키므로 새 키는 자동으로 응답에 실린다. 키를 명시 열거하는
    사영을 새로 넣으면 미래에 키가 늘 때 조용히 떨어지는 필터가 생긴다.
    """
    text = (_ROOT / "src" / "routes" / "history.py").read_text(encoding="utf-8")
    for key in ("buy_order_nos", "sell_order_nos", "pair_key"):
        assert key not in text, (
            f"`history.py` 가 `{key}` 를 명시 열거한다 — 통과 계약(§9.4) 위반"
        )


async def test_p10_numeric_price_types_survive(monkeypatch) -> None:
    """C41 — `price` 가 `Decimal` 로 와도 기존 float 사영이 유지된다(회귀).

    asyncpg 는 NUMERIC 을 `Decimal` 로 준다 — 주문번호 3키를 얹으면서 이 경로가
    깨지면 매매손익 화면이 흰 화면이 된다(cycle266 계열).
    """
    rows = [
        _trade("BUY", Decimal("10000.50"), 2, "2026-09-11T09:01:31.000000+09:00", order_no="B1"),
        _trade("SELL", Decimal("11000.25"), 2, "2026-09-11T15:20:02.000000+09:00", order_no="S1"),
    ]
    pairs = await _pairs(rows)

    assert isinstance(pairs[0]["buy_price"], float)
    assert isinstance(pairs[0]["profit_loss"], float)
    json.dumps(pairs[0])  # 직렬화 가능해야 한다
