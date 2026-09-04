"""cycle249 Red (D) — `upsert_external_report` 는 **기존 컬럼을 절대 덮지 않는다**.

명세: `_workspace/red/cycle249_reporter_scope_spec.md` §D · §H(DB)

## 이 함수가 존재하는 이유와 유일한 위험

병행 기간 동안 하루의 `daily_log_reports` 한 행에 **두 분석**이 공존한다 —
20:10 OpenAI 경로가 쓴 `summary/findings/metrics/model` + 토큰 5컬럼(비교 기준선)과,
20:20 클라우드 루틴이 쓰는 `ext_*` 6컬럼. 그래서 upsert 의 `DO UPDATE SET` 이
`ext_*` 밖으로 한 컬럼이라도 새면 **비교 대상이 지워진다** — 그날의 OpenAI 리포트는
어디에도 복구본이 없다(재실행하면 그 시점 로그로 다시 만들어야 하고, `api_metrics`
같은 프로세스 스코프 값은 이미 다르다). 이 파일의 중심 가드가 그 한 줄이다.

동시에 **행이 아직 없는 날**(20:10 이 실패했거나 병행 종료 후)에도 저장돼야 한다 —
그래서 INSERT 경로가 필요하고, 그 INSERT 는 NOT NULL 컬럼을 빈 값(또는 DB DEFAULT)으로
채우되 **호출자 데이터를 기존 컬럼에 심지 않는다**.

## 봉인하는 seam

`src/db/log_reports.py::upsert_external_report(*, target_date, provider, model,
summary, findings, report_md) -> dict`
  * `INSERT … ON CONFLICT (target_date) DO UPDATE SET <ext_* 6개만> RETURNING *`
  * DB 규약(`src/db/CLAUDE.md`): JSONB=raw dict/list 바인딩(`::jsonb` 캐스트),
    TIMESTAMPTZ=`datetime.fromisoformat(now_kst_iso())`, DATE=`to_date()`
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest

import src.db.log_reports as lr

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

#: 이 upsert 가 갱신해도 되는 **유일한** 컬럼 집합.
EXT_COLUMNS = {
    "ext_provider",
    "ext_model",
    "ext_summary",
    "ext_findings",
    "ext_report_md",
    "ext_created_at",
}

#: 한 컬럼이라도 SET 절에 들어오면 병행 비교 기준선이 파괴된다.
PROTECTED_COLUMNS = {
    "id",
    "target_date",
    "summary",
    "findings",
    "metrics",
    "model",
    "created_at",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "latency_ms",
    "cost_estimate_usd",
}

FINDINGS = [
    {
        "category": "trading",
        "severity": "high",
        "title": "매도 거부 반복",
        "detail": "APBK0918 3회",
        "suggestion": "익일 청산 전환 확인",
    }
]


def _fn():
    fn = getattr(lr, "upsert_external_report", None)
    if fn is None:  # pragma: no cover - Red 경로
        pytest.fail("Red — src/db/log_reports.py::upsert_external_report 미구현")
    return fn


@pytest.fixture
def captured(monkeypatch):
    """`pg.fetchrow` 를 가로채 (sql, args) 를 기록한다."""
    calls: list[tuple[str, tuple]] = []

    async def _fetchrow(sql, *args):
        calls.append((sql, args))
        return {"target_date": "2026-09-04", "ext_provider": "claude-code"}

    monkeypatch.setattr(lr.pg, "fetchrow", _fetchrow)
    return calls


async def _run(target_date=date(2026, 9, 4), **over):
    kwargs = {
        "target_date": target_date,
        "provider": "claude-code",
        "model": "claude-opus-5",
        "summary": "외부 분석 요약",
        "findings": FINDINGS,
        "report_md": "# 리포트\n본문",
    }
    kwargs.update(over)
    return await _fn()(**kwargs)


# ---------------------------------------------------------------------------
# SQL 파서 — 컬럼명을 텍스트 substring 이 아니라 **토큰**으로 다룬다
# (`ext_summary` 가 `summary` 를 포함하므로 substring 검사는 공허하다)
# ---------------------------------------------------------------------------
def _set_columns(sql: str) -> set[str]:
    m = re.search(r"DO\s+UPDATE\s+SET\s+(.*?)(?:\bRETURNING\b|\bWHERE\b|$)", sql, re.S | re.I)
    assert m, f"ON CONFLICT … DO UPDATE SET 절을 찾지 못했다:\n{sql}"
    body = m.group(1)
    cols = set()
    for chunk in body.split(","):
        lhs = chunk.split("=")[0].strip()
        if lhs:
            cols.add(lhs.strip('"').lower())
    return cols


def _insert_value_tokens(sql: str) -> dict[str, str]:
    """`INSERT INTO daily_log_reports (…) VALUES (…)` → {컬럼명: 원본 VALUES 토큰}.

    토큰을 **원문 그대로** 보존한다(`::jsonb` 캐스트 포함) — "SQL 전체에 `::jsonb`
    문자열이 존재한다" 는 검사는 다른 컬럼의 리터럴 기본값(`'[]'::jsonb`/`'{}'::jsonb`)
    만으로도 항상 참이 되는 공허한 가드다(cycle249 위생 시정). 이 헬퍼는 "그 컬럼의
    바인드가 정확히 어떤 형태인가" 를 컬럼 단위로 직접 검사할 수 있게 한다.
    """
    cols_m = re.search(
        r"INSERT\s+INTO\s+daily_log_reports\s*\(([^)]*)\)", sql, re.S | re.I
    )
    vals_m = re.search(r"VALUES\s*\(([^)]*)\)", sql, re.S | re.I)
    assert cols_m and vals_m, f"INSERT 컬럼/VALUES 절 파싱 실패:\n{sql}"
    cols = [c.strip().strip('"').lower() for c in cols_m.group(1).split(",") if c.strip()]
    vals = [v.strip() for v in vals_m.group(1).split(",") if v.strip()]
    assert len(cols) == len(vals), f"컬럼 {len(cols)} vs VALUES {len(vals)} 불일치:\n{sql}"
    return dict(zip(cols, vals))


def _insert_column_binds(sql: str) -> dict[str, int]:
    """`_insert_value_tokens` 위임 — {컬럼명: 1-based 바인드 번호}(캐스트는 버린다)."""
    out: dict[str, int] = {}
    for col, val in _insert_value_tokens(sql).items():
        m = re.search(r"\$(\d+)", val)
        if m:
            out[col] = int(m.group(1))
    return out


# ---------------------------------------------------------------------------
# D-1 ~ D-3 — upsert 형태
# ---------------------------------------------------------------------------
async def test_upsert_when_called_then_on_conflict_target_date(captured):
    """D-1 — `ON CONFLICT (target_date) DO UPDATE` + `RETURNING *`.

    `(target_date)` UNIQUE 가 유일한 충돌 축이다. `DO NOTHING` 이면 재실행이 조용히
    무시돼 루틴 재시도가 영원히 반영되지 않는다.
    """
    await _run()

    sql, _ = captured[0]
    flat = " ".join(sql.split())
    assert re.search(r"ON\s+CONFLICT\s*\(\s*target_date\s*\)\s*DO\s+UPDATE", flat, re.I), flat
    assert re.search(r"RETURNING\s+\*", flat, re.I), flat


async def test_upsert_when_conflict_then_only_ext_columns_updated(captured):
    """D-2 — **핵심 가드**: `DO UPDATE SET` 은 `ext_*` 6컬럼 정확 일치.

    여기에 `summary` 한 줄이 더해지는 순간, 20:20 루틴이 매일 20:10 OpenAI 리포트를
    덮어쓰고 병행 비교가 성립하지 않게 된다(그리고 아무도 즉시 알아채지 못한다 —
    화면에는 여전히 요약이 하나 보인다).
    """
    await _run()

    cols = _set_columns(captured[0][0])
    assert cols == EXT_COLUMNS, f"SET 절 컬럼 불일치: {sorted(cols)}"
    leaked = cols & PROTECTED_COLUMNS
    assert not leaked, f"기존 컬럼이 SET 절에 있다(병행 비교 기준선 파괴): {sorted(leaked)}"


async def test_upsert_when_row_absent_then_insert_fills_defaults(captured):
    """D-3 — 행이 없는 날에도 저장된다 + 기존 컬럼에 호출자 데이터를 심지 않는다.

    20:10 이 실패한 날(OpenAI 타임아웃·키 만료)이야말로 외부 분석이 가장 필요한 날이다.
    동시에 그 INSERT 가 `summary` 에 외부 요약을 넣어 버리면, 나중에 20:10 이 복구
    실행될 때 "이미 행이 있다" 로 INSERT 가 튕겨(`insert_log_report` 는 중복 시 None)
    **OpenAI 리포트가 영구 소실**된다. 기존 컬럼은 비운 채 둔다(또는 DB DEFAULT).
    """
    await _run()

    sql, args = captured[0]
    binds = _insert_column_binds(sql)

    assert EXT_COLUMNS <= set(binds), f"INSERT 에 ext_* 컬럼 누락: {sorted(binds)}"

    empty_defaults = {"summary": "", "findings": [], "metrics": {}, "model": None}
    for col, expected in empty_defaults.items():
        if col in binds:
            value = args[binds[col] - 1]
            assert value == expected, (
                f"INSERT 가 기존 컬럼 `{col}` 에 호출자 데이터를 심었다: {value!r} "
                f"(기대 {expected!r} 또는 컬럼 생략 후 DB DEFAULT)"
            )
    # 외부 findings 는 반드시 ext_findings 쪽에 실려야 한다.
    assert args[binds["ext_findings"] - 1] == FINDINGS


# ---------------------------------------------------------------------------
# D-4 ~ D-6 — 바인딩 타입 (src/db/CLAUDE.md 규약)
# ---------------------------------------------------------------------------
async def test_upsert_when_bound_then_date_is_date_object(captured):
    """D-4 — DATE 컬럼은 `to_date()` 로 강제(문자열 입력도 date 로).

    asyncpg 는 DATE 파라미터에 str 을 주면 타입 오류를 낸다. `insert_log_report` 와
    같은 패턴이어야 호출자가 형식을 신경 쓰지 않는다.
    """
    await _run(target_date="2026-09-04")

    _, args = captured[0]
    dates = [a for a in args if type(a) is date]
    assert dates == [date(2026, 9, 4)], f"date 바인딩이 정확히 1개가 아니다: {args!r}"


async def test_upsert_when_bound_then_findings_is_raw_list_with_jsonb_cast(captured):
    """D-5 — JSONB 는 **raw list/dict 바인딩** + `ext_findings` 바인드 토큰이 정확히
    `$n::jsonb`.

    `json.dumps` 로 문자열을 넣으면 codec 이 다시 감싸 **문자열 JSON** 이 저장된다
    (사이클 168 의 `hts_avls` 문자열 저장 = UI 숫자 비교 0건 결함과 같은 계열).

    cycle249 위생 시정 — 종전 검사는 `"::jsonb" in sql` 만 봤는데, 이 INSERT 문에는
    `ext_findings` 와 무관한 리터럴 기본값(`'[]'::jsonb`/`'{}'::jsonb`, 행이 없는 날의
    기존 컬럼 채움)도 `::jsonb` 를 포함한다 — 그래서 `ext_findings` 바인드 자체에서
    캐스트가 빠지는 뮤테이션도 이 substring 검사만으로는 **초록**이었다. 컬럼별 원본
    토큰(`_insert_value_tokens`)을 직접 대조해 이 공허함을 닫는다.
    """
    await _run()

    sql, args = captured[0]

    lists = [a for a in args if isinstance(a, list)]
    assert lists == [FINDINGS], f"findings raw list 바인딩 아님: {args!r}"

    tokens = _insert_value_tokens(sql)
    findings_token = tokens.get("ext_findings")
    assert findings_token is not None, f"INSERT VALUES 에 ext_findings 가 없다:\n{sql}"
    assert re.fullmatch(r"\$\d+::jsonb", findings_token), (
        "ext_findings 바인드가 `$n::jsonb` 형태가 아니다(다른 컬럼의 리터럴 `::jsonb` "
        f"로 공허하게 통과하지 않는다): {findings_token!r}"
    )
    assert not any(isinstance(a, str) and a.lstrip().startswith("[{") for a in args), (
        "findings 가 직렬화 문자열로 바인딩됐다(codec 이중 인코딩)"
    )


async def test_upsert_when_bound_then_created_at_is_kst_datetime(captured):
    """D-6 — `ext_created_at` 은 KST aware datetime(`datetime.fromisoformat(now_kst_iso())`).

    naive datetime 을 넣으면 asyncpg 가 UTC 로 해석해 **9시간 어긋난** 생성 시각이
    저장된다. 모든 시각 데이터 KST 강제(루트 CLAUDE.md).
    """
    await _run()

    _, args = captured[0]

    stamps = [a for a in args if isinstance(a, datetime)]
    assert stamps, f"datetime 바인딩이 없다: {args!r}"
    for stamp in stamps:
        assert stamp.tzinfo is not None, f"naive datetime 바인딩: {stamp!r}"
        assert stamp.utcoffset() == timedelta(hours=9), stamp


async def test_upsert_when_bound_then_payload_values_present(captured):
    """D-7 — provider/model/summary/report_md 가 그대로 바인딩된다(누락 무음 금지)."""
    await _run()

    _, args = captured[0]
    for value in ("claude-code", "claude-opus-5", "외부 분석 요약"):
        assert value in args, f"{value!r} 가 바인딩되지 않았다: {args!r}"
    assert any(isinstance(a, str) and a.startswith("# 리포트") for a in args), args


async def test_upsert_when_report_md_none_then_bound_as_none(captured):
    """D-8 — `report_md=None` 은 NULL 로 저장된다(빈 문자열로 둔갑 금지).

    "본문 없음"(루틴이 요약만 보냄)과 "본문이 빈 문자열"(생성 실패)은 다른 사실이다.
    """
    await _run(report_md=None)

    _, args = captured[0]
    assert None in args, f"None 바인딩이 없다: {args!r}"


async def test_upsert_when_row_returned_then_passthrough(captured):
    """D-9 — `RETURNING *` 행을 그대로 돌려준다(라우트가 응답 data 로 쓴다)."""
    row = await _run()
    assert row == {"target_date": "2026-09-04", "ext_provider": "claude-code"}


# ---------------------------------------------------------------------------
# D-10 — 기존 읽기 함수가 ext_* 를 자동 포함
# ---------------------------------------------------------------------------
def test_read_functions_when_select_star_then_ext_columns_visible():
    """D-10 — `get_log_report`/`list_log_reports` 가 `SELECT *` 라 ext_* 가 자동 노출된다.

    명시 컬럼 목록으로 바뀌어 있으면 ext_* 를 추가해야 한다 — 안 그러면 저장은 되는데
    화면·API 어디에도 보이지 않는 "쓰기 전용 컬럼" 이 된다.
    """
    import inspect

    for fn in (lr.get_log_report, lr.list_log_reports):
        src = inspect.getsource(fn)
        assert re.search(r"SELECT\s+\*", src, re.I) or "ext_" in src, (
            f"{fn.__name__} 이 명시 컬럼 SELECT 인데 ext_* 를 포함하지 않는다"
        )
