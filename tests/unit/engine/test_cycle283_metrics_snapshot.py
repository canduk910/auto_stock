"""cycle283 Red — metrics 1차 스냅샷(20:05) + 21:30 완전판 (C7/C8).

## 왜 (D5)
`metrics` 의 두 축 `api_metrics`(= `src/api/base.py::get_request_metrics()`)와
`strategy_funnel`(레지스트리 메모리 카운터)은 **프로세스 메모리 전용**이다 — 프로세스가
죽으면 DB 로 복구할 길이 없다. 정산이 20:10 → 21:30 으로 밀리면 그 유실 노출이
10분 → **90분**이 된다. 20:05 에 한 번 저장해 5분으로 줄인다.

## 계약
- **C7** 1차 저장 함수:
  - `collect_daily_log_metrics(target_date)` **재사용** — 새 수집 코드를 만들지 않는다.
  - `insert_log_report(...)` 로 저장. 토큰 5컬럼 전부 `None`, `model=None`.
  - 🔴 **OpenAI 를 호출하지 않는다**(비용·지연 0).
  - 🔴 **`reset_request_metrics()` 를 호출하지 않는다** — 부르면 `api_metrics` 가 0부터
    다시 세어 21:30 패스가 20:05~21:30 **90분만** 보게 된다. 리셋은 마지막 패스에서만.
  - never-raise. 실패는 WARNING 1행 + 정산 경로 무영향.
  - 관측 마커 1행 `[daily_metrics_snapshot] target_date=… pass=1 elapsed_ms=…`.
- **C8** 21:30 `generate_daily_log_report` 는 **현행 그대로**(OpenAI 호출 + 완전판 저장 +
  `reset_request_metrics()`). C9 의 upsert 덕분에 1차 행을 덮어쓴다.

## 위치 (leaf 강제 — C6)
`scheduler.py` 는 3,872L 이고 실효 상한이 **3,900L**(cycle257) 다. 함수 본체는 **`src/engine/log_analysis_engine.py`
또는 신규 leaf** 에 둔다(구현자 판단). 이 파일은 두 곳 중 하나에서 **이름으로** 찾는다 —
위치는 자유롭게 두되 이름은 계약이다(scheduler 배선이 그 이름을 부른다).

## 비용 주의 (자문)
`collect_daily_log_metrics` 는 읽기 전용이라 두 번 불러도 **안전하다**(컬렉터 flush 없음).
다만 `_fetch_logs_in_range(limit=30000)` + `_fetch_high_severity_logs` + `get_trades_in_range`
DB 왕복과 `_build_portfolio_risk_snapshot` 안의 `get_balance()` **KIS 호출 1회**가 20:05 에
추가된다 — 마커의 `elapsed_ms` 로 감시한다.

## Red 유효성
함수 자체가 없다 → `_resolve_snapshot_fn()` 이 명시 실패. C8 계열은 현행 회귀(초록)다.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import logging
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_MARKER = "[daily_metrics_snapshot]"
_SNAPSHOT_FN_NAME = "run_daily_metrics_snapshot"
#: 구현자가 고를 수 있는 두 자리 (C7 — "log_analysis_engine.py 또는 신규 leaf").
_CANDIDATE_MODULES = (
    "src.engine.daily_metrics_snapshot",
    "src.engine.log_analysis_engine",
)


def _resolve_snapshot_module():
    tried = []
    for name in _CANDIDATE_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            tried.append(f"{name}(import 실패)")
            continue
        if hasattr(mod, _SNAPSHOT_FN_NAME):
            return mod
        tried.append(f"{name}(함수 부재)")
    raise AssertionError(
        f"1차 스냅샷 함수 `{_SNAPSHOT_FN_NAME}` 를 찾지 못했다 (C7). 후보: {tried}\n"
        "위치는 `src/engine/log_analysis_engine.py` 또는 신규 leaf 중 구현자 판단이지만, "
        "**이름은 계약**이다 — scheduler 배선이 이 이름을 부른다."
    )


def _snapshot_fn():
    return getattr(_resolve_snapshot_module(), _SNAPSHOT_FN_NAME)


def _records(caplog, prefix: str, *, min_level: int = logging.INFO):
    return [
        r for r in caplog.records
        if r.levelno >= min_level and r.getMessage().startswith(prefix)
    ]


# ===========================================================================
# C7 — 1차 스냅샷의 계약
# ===========================================================================

def test_c283_c7_1_snapshot_function_exists():
    """C7 — 함수가 있고 async 다."""
    fn = _snapshot_fn()
    assert inspect.iscoroutinefunction(fn), (
        "1차 스냅샷은 `collect_daily_log_metrics`(await) 를 부르므로 async 여야 한다"
    )


@pytest.mark.asyncio
async def test_c283_c7_2_saves_collected_metrics_without_openai(caplog):
    """C7 — 수집 계층을 **재사용**해 저장하고 OpenAI 는 부르지 않는다."""
    mod = _resolve_snapshot_module()
    metrics = {"logs": {"total_logs": 4242}, "api_metrics": {"total": 9}}
    insert = AsyncMock(return_value={"id": "row-1"})
    collect = AsyncMock(return_value=metrics)

    def _boom(*a, **k):  # pragma: no cover — 불리면 안 된다
        raise AssertionError("1차 패스는 OpenAI 를 호출하지 않는다 (비용·지연 0)")

    with patch.object(mod, "collect_daily_log_metrics", collect, create=True), \
            patch.object(mod, "insert_log_report", insert, create=True), \
            patch("openai.AsyncOpenAI", _boom):
        with caplog.at_level(logging.INFO):
            await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))

    assert collect.await_count == 1, (
        "수집은 `collect_daily_log_metrics` 재사용 의무 — 새 수집 코드를 만들면 "
        "21:30 패스와 두 벌이 되어 비교가 성립하지 않는다"
    )
    assert insert.await_count == 1, "1차 저장이 `insert_log_report` 를 부르지 않았다"
    kw = insert.await_args.kwargs
    assert kw["target_date"] == date(2026, 9, 14)
    assert kw["metrics"] == metrics, "수집 결과를 그대로 저장해야 한다"
    assert kw["model"] is None, "1차 패스는 OpenAI 미호출 — model 은 None"
    for tok in ("input_tokens", "output_tokens", "total_tokens",
                "latency_ms", "cost_estimate_usd"):
        assert kw.get(tok) is None, f"토큰 5컬럼은 전부 None 이어야 한다 (실측 {tok}={kw.get(tok)!r})"


@pytest.mark.asyncio
async def test_c283_c7_3_snapshot_row_is_distinguishable_from_routine_placeholder():
    """C7③ (자문 권고, 선택지) — 사람과 기계가 1차 행을 알아볼 수 있어야 한다.

    `upsert_external_report` 의 placeholder INSERT 도 `summary=''` 를 쓴다
    (`src/db/log_reports.py`). 1차 스냅샷이 `summary=""` 로 저장하면 읽는 쪽이
    "1차 스냅샷" 과 "20:20 루틴 placeholder" 를 **구분할 수 없고**, UI 는
    `report.summary || '요약이 없습니다.'`(`DailyReportTab.tsx`)로 렌더해
    20:05~21:30 사이 운영자에게 **"분석 실패"처럼 보인다**.

    구현은 **(a)+(b) 동시**다(자문 권고, Green 채택):
      (a) 사람용 문구 `summary` — UI `report.summary || '요약이 없습니다.'` 렌더 대상
      (b) 기계용 센티널 `metrics["snapshot_pass"] = 1` — 라우트 재실행 가드가 읽는 축

    ⚠️ 두 축을 `or` 로 한 테스트에 묶으면 **한 축이 사라져도 초록**이다(적대 검증
    M26·M27 각각 ESCAPED, 둘을 동시에 지워야만 붉었다). 그래서 아래 `_b` 로 분리해
    각각 독립 단언을 둔다 — 이 테스트는 "둘 다 있다" 만 본다.
    """
    kw = await _snapshot_insert_kwargs()
    assert (kw.get("summary") or "").strip(), (
        "사람용 문구가 비었다 — `upsert_external_report` 의 placeholder(summary='')와 "
        "구분되지 않아 UI 가 '요약이 없습니다' 로 렌더한다(운영자에겐 분석 실패로 보인다)"
    )
    assert (kw.get("metrics") or {}).get("snapshot_pass") == 1, (
        "기계용 센티널이 없다 — 라우트 재실행 가드가 1차 행을 완성본으로 오분류한다"
    )


async def _snapshot_insert_kwargs() -> dict:
    """1차 스냅샷 1회 실행 후 `insert_log_report` 에 넘어간 kwargs."""
    mod = _resolve_snapshot_module()
    insert = AsyncMock(return_value={"id": "row-1"})
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(return_value={"logs": {"total_logs": 1}}), create=True), \
            patch.object(mod, "insert_log_report", insert, create=True):
        await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))
    return insert.await_args.kwargs


@pytest.mark.asyncio
async def test_c283_c7_3b_human_summary_is_not_the_routine_placeholder():
    """(a) 축 단독 — 사람이 읽는 채널이 placeholder 와 **다른 문자열**이어야 한다."""
    kw = await _snapshot_insert_kwargs()
    summary = (kw.get("summary") or "").strip()
    assert summary, (
        "1차 행의 `summary` 가 비었다 — `upsert_external_report` 의 placeholder 와 "
        "구분되지 않는다"
    )
    mod = _resolve_snapshot_module()
    assert summary == getattr(mod, "SNAPSHOT_SUMMARY"), (
        "저장 문구가 모듈 상수 `SNAPSHOT_SUMMARY` 와 다르다 — 라우트 가드 테스트가 "
        "그 상수를 끌어다 쓰므로 두 벌이 되면 판정이 조용히 어긋난다"
    )


@pytest.mark.asyncio
async def test_c283_c7_3c_machine_sentinel_is_present():
    """(b) 축 단독 — 기계가 읽는 채널(`metrics["snapshot_pass"]`)."""
    kw = await _snapshot_insert_kwargs()
    assert (kw.get("metrics") or {}).get("snapshot_pass") == 1, (
        "`metrics[\"snapshot_pass\"]` 센티널이 없다 — `POST /api/log-reports/run` 의 "
        "재실행 가드가 1차 스냅샷 행을 완성본으로 보고 20:05~21:30 수동 복구를 막는다"
    )


@pytest.mark.asyncio
async def test_c283_c7_4_does_not_reset_request_metrics_runtime():
    """🔴 C7 — 1차 패스는 `reset_request_metrics()` 를 **부르지 않는다**(런타임).

    부르면 `api_metrics` 가 0부터 다시 세어 21:30 완전판이 **20:05~21:30 90분만** 보게
    된다. 그 순간 그날의 5xx/4xx/재시도 통계가 하루치가 아니라 저녁 90분치가 되고,
    아무도 그 사실을 눈치채지 못한다(숫자가 그럴듯하게 작아질 뿐이다).
    """
    import src.api.base as api_base

    mod = _resolve_snapshot_module()
    reset = MagicMock()
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(return_value={}), create=True), \
            patch.object(mod, "insert_log_report",
                         AsyncMock(return_value={"id": "x"}), create=True), \
            patch.object(api_base, "reset_request_metrics", reset):
        # 모듈이 `from ... import reset_request_metrics` 로 끌어 썼을 수도 있으니 양쪽 차단
        if hasattr(mod, "reset_request_metrics"):
            with patch.object(mod, "reset_request_metrics", reset):
                await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))
        else:
            await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))

    assert reset.call_count == 0, (
        f"1차 패스가 `reset_request_metrics()` 를 {reset.call_count}회 불렀다 — "
        "21:30 완전판이 저녁 90분치만 보게 된다"
    )


def test_c283_c7_5_does_not_reset_request_metrics_ast():
    """C7 — 소스에도 `reset_request_metrics` 호출이 0건이어야 한다(AST).

    런타임 가드만 두면 "어떤 분기에서만 부른다" 를 놓친다.
    """
    mod = _resolve_snapshot_module()
    src = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == _SNAPSHOT_FN_NAME
    )
    calls = [
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(fn) if isinstance(n, ast.Call)
    ]
    assert "reset_request_metrics" not in calls, (
        f"1차 패스 본체에 `reset_request_metrics` 호출이 있다 (실측 호출 {sorted(set(calls))})"
    )


@pytest.mark.asyncio
async def test_c283_c7_6_never_raises_and_logs_one_warning(caplog):
    """C7 — never-raise. 수집이 터져도 정산 경로는 그대로 간다."""
    mod = _resolve_snapshot_module()
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(side_effect=RuntimeError("DB down")), create=True), \
            patch.object(mod, "insert_log_report",
                         AsyncMock(return_value={"id": "x"}), create=True):
        with caplog.at_level(logging.WARNING):
            out = await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))

    assert out is None, "실패 시 None 반환 (호출부가 결과를 가드로 쓰지 않는다)"
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) >= 1, "실패를 조용히 삼켰다 — 관측 없는 graceful 은 결함 은폐다"


@pytest.mark.asyncio
async def test_c283_c7_7_insert_failure_is_also_absorbed():
    """C7 — 저장 실패도 흡수한다(정산 진행 의무)."""
    mod = _resolve_snapshot_module()
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(return_value={"logs": {}}), create=True), \
            patch.object(mod, "insert_log_report",
                         AsyncMock(side_effect=RuntimeError("pg closed")), create=True):
        assert await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14)) is None


@pytest.mark.asyncio
async def test_c283_c7_8_marker_emitted_exactly_once_with_fields(caplog):
    """C7 — `[daily_metrics_snapshot] target_date= pass=1 elapsed_ms=` **정확히 1행** INFO.

    D+1 판독: 0행 = C5 배선 실패(자문 예외가 `_wait_until` 앞에서 죽었는지 확인),
    2행 이상 = 루프 오배선, `elapsed_ms > 60,000` = `collect_daily_log_metrics` 중복
    호출 비용이 예상보다 큰 것(21:30 패스와 합쳐 하루 2회분 DB 부하 재평가).
    """
    mod = _resolve_snapshot_module()
    logger_name = mod.__name__
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(return_value={"logs": {"total_logs": 7}}), create=True), \
            patch.object(mod, "insert_log_report",
                         AsyncMock(return_value={"id": "x"}), create=True):
        with caplog.at_level(logging.INFO, logger=logger_name):
            await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))

    rows = _records(caplog, _MARKER)
    assert len(rows) == 1, f"마커는 실행당 정확히 1행 (실측 {len(rows)}행)"
    line = rows[0].getMessage()
    for field in ("target_date=2026-09-14", "pass=1", "saved=1", "elapsed_ms="):
        assert field in line, f"마커 필드 `{field}` 누락 — 실측 {line!r}"


@pytest.mark.asyncio
async def test_c283_c7_8b_marker_says_saved_zero_when_the_row_is_empty(caplog):
    """저장이 **조용히 비었을 때** 성공 서명을 찍지 않는다 (적대 검증 LOW 시정).

    `insert_log_report` 는 예상 밖 23505 를 만나면 예외 없이 `None` 을 돌려준다
    (`[log_report_unexpected_conflict]` WARNING 1행 후 return). 그 경우까지 `pass=1`
    만 찍으면 D+1 판독이 "마커 1행 = 1차 저장 성공" 이라는 거짓을 참으로 읽는다.
    """
    mod = _resolve_snapshot_module()
    with patch.object(mod, "collect_daily_log_metrics",
                      AsyncMock(return_value={"logs": {"total_logs": 7}}), create=True), \
            patch.object(mod, "insert_log_report",
                         AsyncMock(return_value=None), create=True):
        with caplog.at_level(logging.INFO, logger=mod.__name__):
            row = await getattr(mod, _SNAPSHOT_FN_NAME)(target_date=date(2026, 9, 14))

    assert row is None
    rows = _records(caplog, _MARKER)
    assert len(rows) == 1, f"마커는 실행당 정확히 1행 (실측 {len(rows)}행)"
    line = rows[0].getMessage()
    assert "saved=0" in line, f"저장 실패인데 `saved=0` 이 없다 — 실측 {line!r}"
    assert rows[0].levelno >= logging.WARNING, (
        "저장이 비었는데 INFO 로 찍는다 — 조용한 실패는 D+1 판독을 속인다"
    )


# ===========================================================================
# C8 — 21:30 완전판은 현행 그대로 (회귀)
# ===========================================================================

@pytest.mark.asyncio
async def test_c283_c8_1_settlement_path_still_resets_request_metrics():
    """C8 — 리셋은 **마지막 패스에서만**. `generate_daily_log_report` 는 현행 유지."""
    import src.engine.log_analysis_engine as lae

    reset = MagicMock()
    with patch.object(lae.settings, "openai_api_key", "sk-test"), \
            patch.object(lae, "collect_daily_log_metrics",
                         AsyncMock(return_value={"logs": {}})), \
            patch.object(lae, "insert_log_report", AsyncMock(return_value={"id": "x"})), \
            patch.object(lae, "reset_request_metrics", reset), \
            patch.object(lae, "_call_openai",
                         AsyncMock(return_value=({"summary": "s", "findings": []},
                                                 lae._OpenAIMeta()))):
        await lae.generate_daily_log_report()

    assert reset.call_count == 1, (
        "정산 경로가 `reset_request_metrics()` 를 부르지 않는다 — 그러면 `api_metrics` 가 "
        "날짜를 넘겨 영원히 누적된다"
    )


def test_c283_c8_2_openai_key_absent_still_returns_early():
    """C8 조건 분기(자문) — `openai_api_key` 부재면 `generate_daily_log_report` 는
    **맨 위에서 return** 한다: metrics 저장도 `reset_request_metrics()` 도 일어나지 않는다.

    C7+C9 이후 이 경우 **20:05 행이 그날의 유일한 행**으로 남는다(개선). 대신
    `reset_request_metrics()` 가 영원히 안 돌아 `api_metrics` 가 날짜를 넘겨 누적된다
    — 기존 결함이고 이번 범위 밖이지만 changelog 에 한 줄 남긴다. 이 테스트는 그
    구조(조기 return)가 유지되는지만 잠근다.
    """
    import src.engine.log_analysis_engine as lae

    src = Path(inspect.getfile(lae)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "generate_daily_log_report"
    )
    body = [n for n in fn.body if not isinstance(n, ast.Expr)]
    assert isinstance(body[0], ast.If), "키 검사가 함수 첫 문장이 아니다"
    assert "openai_api_key" in ast.dump(body[0].test)


@pytest.mark.asyncio
async def test_c283_c8_3_settlement_overwrites_the_snapshot_row():
    """C8 + C9 — 21:30 완전판은 1차 행을 **덮어쓴다**(같은 `target_date`).

    upsert 이전에는 `insert_log_report` 가 UNIQUE 충돌로 `None` 을 반환하고
    `log_analysis_engine.py` 가 `if row:` 뿐이라 **조용히 끝났다** — 그날 `metrics`
    JSONB 가 통째로 유실된다(OpenAI 텍스트만이 아니다).
    """
    import src.engine.log_analysis_engine as lae

    insert = AsyncMock(return_value={"id": "row-1", "summary": "완전판"})
    with patch.object(lae.settings, "openai_api_key", "sk-test"), \
            patch.object(lae, "collect_daily_log_metrics",
                         AsyncMock(return_value={"logs": {"total_logs": 100}})), \
            patch.object(lae, "insert_log_report", insert), \
            patch.object(lae, "reset_request_metrics", MagicMock()), \
            patch.object(lae, "_call_openai",
                         AsyncMock(return_value=({"summary": "완전판", "findings": []},
                                                 lae._OpenAIMeta()))):
        row = await lae.generate_daily_log_report()

    assert row is not None, (
        "완전판 저장이 None 을 돌려준다 — upsert 이후 정상 경로에서 None 은 없어야 한다"
    )
    kw = insert.await_args.kwargs
    assert kw["summary"], "완전판은 summary 를 채운다(1차 행을 덮어쓰는 증거)"
    assert kw["model"], "완전판은 model 을 채운다"


def test_c283_c8_4_not_saved_branch_rings_a_bell():
    """C9 ② — 반환 계약 변경의 관측.

    upsert 이후 `row` 가 falsy 인 것은 **정상 경로에서 도달 불가**하다. 그래서 그 분기는
    이제 "`ON CONFLICT` 타깃이 어긋났을 때만 울리는 종" 이다 — 종을 달아 둔다.
    현행은 `if row:` 로 로그만 찍고 else 가 없어 **아무 소리도 나지 않는다**.
    """
    import src.engine.log_analysis_engine as lae

    src = Path(inspect.getfile(lae)).read_text(encoding="utf-8")
    assert "[daily_log_report_not_saved]" in src, (
        "저장 실패(=ON CONFLICT 타깃 어긋남)의 유일한 감지기가 없다 — "
        "`if row:` 의 else 분기에 WARNING 1행"
    )
