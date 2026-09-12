"""야간작업 현황 라우트 — `GET /api/market-ops` (사이클 285).

`GET /api/market-state`(사이클 282)는 "지금 몇 시니까 어떤 상태여야 하는가" 를 코드
상수로만 답한다. 이 라우트는 그 옆에서 "실제로 무슨 일이 있었는가" 를 DB/메모리
산출물로 답한다 — 표가 "정규장" 이라고 말하는 순간에도 20:30 일봉 적재가 실패했는지,
20:00 AI 자문이 오늘 행을 남겼는지는 표만 봐서는 알 수 없다.

## 왜 별도 엔드포인트인가 (같은 `/api/market-state` 에 얹지 않은 이유)

1. `tests/unit/ast/test_cycle282_ast_purity.py::test_h6/h8` 이 `routes/market_state.py`
   안에서 시계 호출 **정확히 1회** + 시각 문자열 리터럴 **0건**을 강제한다. 이 라우트가
   같은 파일에 들어가면 그 두 가드와 정면으로 충돌한다.
2. `tests/unit/routes/test_cycle282_fixture_sync.py` 가 `/api/market-state` 응답을
   골든 픽스처(프론트 + E2E, 각 ~4,000줄) 와 byte 동일하게 강제한다. 응답에 필드를
   더하면 그 사슬 전체를 다시 생성해야 하고, 생성기가 DB 스텁을 더 떠안는다.
3. 성격이 다르다 — `/api/market-state` 는 코드 상수라 DB 장애와 무관하게 항상 살아
   있어야 하는 표다. 이 라우트는 DB/메모리 산출물이라 실패할 수 있고, 실패해도
   `/api/market-state` 의 200 계약을 물들이면 안 된다.

## 시각의 단일 출처

예정 시각은 전부 `src.engine.scheduler.TIME_*`(+ 보조 계좌 토큰 재발급 1건은
`src.engine.quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`, scheduler 밖 정본)에서
**읽기만** 한다 — 이 파일 안에 `HH:MM` 리터럴을 적으면 다음 사이클이 시각을 옮기는
순간 이 화면이 거짓을 보여준다(회귀 가드 = `tests/unit/routes/test_cycle285_market_ops_route.py`
의 텍스트 스캔).

## 상태 어휘 (`_finalize_status` 치환 전 원시값 8종 + 치환 후 2종)

`scheduled` · `running` · `done` · `failed` · `skipped_fresh` · `skipped_weekly` ·
`overwritten` · `not_fired` — 이 중 **`not_fired`/`scheduled` 만** `_finalize_status`
에서 `is_trading_day` 에 따라 `holiday`(휴장 확정) 또는 `unknown`(`not_fired` 이면서
확인 불가)으로 치환된다. 나머지(`running`/`done`/`failed`/`skipped_*`/`overwritten`)
는 "모른다" 때문에도, "휴장이다" 때문에도 깎이지 않는다 — 이미 증거로 증명된 사실을
숨기지 않는다.

⚠️ **cycle285 적대 검증 시정** — 초판은 `is_trading_day is False` 를 **모든** 상태에
무조건 적용했다(휴장이면 무조건 `holiday`). 그러면 20:20 클라우드 루틴이 그날 실제로
성공(`done`)했거나 재기동으로 `running` 인 행까지 "휴장일" 로 보였다 — §4-4 가
요구하는 건 "안 돈 작업을 실패로 그리지 않는 것" 이지 "이미 증명된 사실을 지우는
것" 이 아니다. 지금은 아직 증거가 없는 상태(`not_fired`/`scheduled`)만 승격한다.

## 마커가 없는 작업들 — 있는 그대로 노출한다

`task_loop_helper.run_periodic_task_loop` 의 `immediate_skip_if_fresh_hours` 게이트
안에서만 `system_config.set_task_last_success` 가 불린다(`src/engine/CLAUDE.md`
task_loop_helper.py 절) — 8개 `task_label` 중 **4개**(`stock_master_daily_load`·
`stock_master_basics_refresh`·`stock_master_master_load`·`stock_master_financial_load`)
만 실제로 마커를 남긴다. `full_universe_load`·`evening_funnel_capture`·
`stock_master_daily_purge`·`quote_token_refresh` 는 이 필드가 영구 결측이고, 이 화면은
그 결측을 "실패" 로 위장하지 않는다 — 산출물이 있으면 산출물로, 없으면 `unknown`
+ 이유를 적는다(never-raise 요구와 같은 정신: 없는 안전을 보여주지 않는다).

## `daily_log_reports` 의 4구간 (§4-4 확장, cycle285 적대 검증 시정으로 3→4)

20:05 metrics 1차 스냅샷의 `metrics.snapshot_pass` 는 **휘발성**이다 — 21:30 정산 뒤
완전판이 그 JSONB 컬럼을 통째로 덮어써 그 키를 지운다(`log_analysis_engine.py` +
`daily_metrics_snapshot.py` 계약, `src/db/log_reports.py::_UPSERT_SQL` SET 절이
`metrics = EXCLUDED.metrics`). 이 화면은 그 컬럼을 네 구간으로 읽는다 —
`snapshot_pass` truthy(20:05~21:30, 스냅샷 저장 성공 — 실제 값은 정수 `1` 이다,
`is True` 항등 비교 금지) → 그 키가 없는데 21:30 이 지났고 **실재하는 완전판**
(`_is_complete_report`, cycle283 재실행 가드와 같은 4축 판정기)이 있다 → `overwritten`
(정상, 최종본 존재) → 21:30 이 지났는데 완전판 증거가 없다(20:20 클라우드 루틴이
만드는 placeholder 행 `summary=""` 만 있거나 행 자체가 없는 경우) → `unknown`(판정
불가, `overwritten` 아님) → 그 외 → `scheduled`/`not_fired`.

⚠️ **cycle285 적대 검증 시정** — 초판은 "정산 시각이 지났고 행이 존재한다" 만으로
`overwritten` 을 단정했다. 그러면 20:05 스냅샷이 그날 아예 발화하지 않았어도
21:31 부터 영원히 "완료(최종반영)" 로 보였다 — 이 라우트가 존재하는 이유(§1 "표는
20:30 일봉 적재인데 마지막 성공이 어제다")를 정면으로 무력화하는 결함이었다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter

import src.db.pg as pg
from src.db import system_config
from src.db._kst import to_date
from src.db.log_reports import get_log_report
from src.engine import refresh_progress
from src.engine.log_analysis_engine import OPENAI_EMPTY_RESPONSE_SUMMARY
from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH
from src.engine.scheduler import (
    TIME_EVENING_FUNNEL_CAPTURE,
    TIME_FULL_UNIVERSE_LOAD,
    TIME_METRICS_SNAPSHOT,
    TIME_NXT_POST_BUY_STOP,
    TIME_RECOMMENDATION,
    TIME_SETTLEMENT,
    TIME_STOCK_MASTER_BASICS_REFRESH,
    TIME_STOCK_MASTER_DAILY_LOAD,
    TIME_STOCK_MASTER_DAILY_PURGE,
    TIME_STOCK_MASTER_FINANCIAL_LOAD,
    TIME_STOCK_MASTER_MASTER_LOAD,
    trading_scheduler,
)
from src.models.response import ApiResponse
from src.routes.log_reports import _is_complete_report
from src.routes.market_state import _resolve_trading_day

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-ops", tags=["market-ops"])

_KST = timezone(timedelta(hours=9))

#: 마커를 남기는 4 task + 마커가 영구 결측인 4 task — 전수 8개(`task_loop_helper` 계약).
_MARKER_TASK_LABELS = (
    "full_universe_load",
    "stock_master_daily_load",
    "stock_master_basics_refresh",
    "stock_master_master_load",
    "stock_master_financial_load",
    "evening_funnel_capture",
    "stock_master_daily_purge",
    "quote_token_refresh",
)
#: 60초 하트비트(`uptime_monitor.py`) — 프로세스 생존의 DB 측 증거, `running` 과 독립.
_HEARTBEAT_LABEL = "engine_alive_heartbeat"

#: 재무 적재는 주 1회 게이트(168h) — "오늘 안 돌았다" 가 정상일 수 있다.
_FINANCIAL_WEEKLY_GATE_HOURS = 168.0

#: 부팅 즉시실행(`immediate_first_run`)·수동 새로고침 라우트(`POST /api/stock-master/
#: {basics,master,daily}/refresh`)가 예정 시각과 무관하게 같은 마커/진행률 키를 쓴다.
#: `full_universe_load` 는 신선도 게이트 자체가 없어 **매일** 부팅 시 07:5x 경 완료
#: 증거를 남기고, 그 값이 예정(20:00:05) 훨씬 이전인데도 날짜만 같다는 이유로 "오늘
#: 이 행이 대표하는 실행" 으로 오인되면 하루 종일 거짓 완료가 뜬다(cycle285 검증
#: HIGH #2). daily_load 도 전날 20:30 실행이 실패해 다음날 catch-up 이 07:5x 에 쓴
#: 마커가 그날 20:30 행을 같은 방식으로 오분류한다(HIGH #3). 수동 새로고침을 스케줄
#: 시각보다 훨씬 이르게 눌러도 같은 함정이다(scope MEDIUM #2). 이 폭(2시간) 안의
#: 지연은 정상 지터로 보고 그대로 인정한다 — 실측 오탐 사례는 전부 몇 시간 단위
#: 격차였고, 정상 near-schedule 지연(수 분~수십 분)까지 걸러내면 안 된다.
_SCHEDULE_EVIDENCE_GRACE = timedelta(hours=2)

#: 한 왕복으로 묶는 산출물 집계 — 전량 Index (Only) Scan, 실측 ~3ms(사이클 285 조사).
#: `bas_dd`/`target_date`/`date` 는 DATE(타임존 무관), TIMESTAMPTZ 컬럼만 `to_char` 로
#: KST 고정 문자열로 뽑는다(루트 CLAUDE.md "TIMESTAMPTZ 읽기 = to_char(...,'+09:00')").
_TS = "'YYYY-MM-DD\"T\"HH24:MI:SS+09:00'"
#: ⚠️ `strategy_funnel_snapshots` 는 이 한 행(16:20 저녁 잠정 캡처)의 산출물만 담는
#: 테이블이 아니다 — 09:30 자동 캡처(`scheduler._auto_capture_funnel_snapshots`)와
#: 스캐너 가격/거래대금 필터 훅(step_no 97/98)도 같은 `(target_date, strategy_id,
#: step_no)` UNIQUE 에 UPSERT 한다. `is_provisional=TRUE` 는 16:20 캡처만 쓰는 값이라
#: (다른 세 생산자는 전부 `False`) 이 필터가 없으면 아침 자동 캡처 행이 저녁 캡처의
#: "성공" 으로 오인된다(cycle285 검증 HIGH #1 — 09:30 에 이미 "완료" 가 뜨고, 16:20
#: 캡처가 그날 완전히 실패해도 상태가 바뀌지 않았다).
_COMBINED_SQL = f"""
SELECT
  (SELECT count(*) FROM parameter_recommendations WHERE target_date = $1) AS rec_rows,
  (SELECT to_char(max(created_at), {_TS}) FROM parameter_recommendations) AS rec_last_at,
  (SELECT count(*) FROM daily_performance WHERE date = $1) AS perf_rows,
  (SELECT max(bas_dd) FROM stock_master_daily) AS daily_head,
  (SELECT count(*) FROM stock_master_daily WHERE bas_dd = $1) AS daily_today_rows,
  (SELECT min(bas_dd) FROM stock_master_daily) AS daily_tail,
  (SELECT count(*) FROM strategy_funnel_snapshots
     WHERE target_date = $1 AND is_provisional = TRUE) AS funnel_rows,
  (SELECT to_char(max(snapshot_at), {_TS}) FROM strategy_funnel_snapshots
     WHERE is_provisional = TRUE) AS funnel_last_at,
  (SELECT to_char(max(refreshed_at), {_TS}) FROM stock_master) AS sm_refreshed_last,
  (SELECT to_char(max(master_raw_updated_at), {_TS}) FROM stock_master) AS sm_master_last
"""


# ---------------------------------------------------------------------------
# 순수 헬퍼 — 시각 파싱/포맷 (DB·시계 미접촉)
# ---------------------------------------------------------------------------
def _hms(t: "time | None") -> "str | None":
    if t is None:
        return None
    return t.strftime("%H:%M") if t.second == 0 else t.strftime("%H:%M:%S")


def _parse_iso(value) -> "datetime | None":
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _date_of(value) -> "date | None":
    """ISO 문자열이든 `datetime`이든 KST 날짜만 뽑는다. 실패는 `None`(fail-open)."""
    dt = _parse_iso(value) if isinstance(value, str) else value
    if isinstance(dt, datetime):
        try:
            return dt.astimezone(_KST).date() if dt.tzinfo else dt.date()
        except Exception:
            return dt.date()
    return None


def _iso_date(value: "date | None") -> "str | None":
    return value.isoformat() if value is not None else None


def _finalize_status(status: str, trading_day) -> str:
    """휴장 확정 → **아직 증거가 없는** 상태(`not_fired`/`scheduled`)만 `holiday` 로.
    확인 불가(`None`) + `not_fired` → `unknown`.

    ⚠️ cycle285 검증(honest 렌즈 MEDIUM #2) 시정 — 종전에는 `trading_day is False`
    이면 **모든** 상태를 무조건 `holiday` 로 덮었다. `is_trading_day` 판정은 KIS
    휴장일 조회에 의존하는 **별도 경로**라, 20:20 클라우드 루틴이 실제로 성공(`done`)
    했거나 재기동으로 `running` 인 행까지 "휴장일" 로 보이면 그 자체가 거짓 화면이다
    (실측 재현 = `_cloud_routine_status`가 `done` 을 반환해도 무조건 `holiday` 로
    뒤집혔다). §4-4 가 요구하는 건 "안 돈 작업을 실패로 그리지 않는 것" 이지 "이미
    증명된 사실을 지우는 것" 이 아니다. `scheduled`/`not_fired` 는 애초에 증거가
    없는(또는 아직 때가 안 된) 상태라 "휴장이라 안 돌았다" 로 승격해도 사실을 잃지
    않는다 — 나머지(`running`/`done`/`failed`/`skipped_*`/`overwritten`)는 증거가
    이긴다.
    """
    if trading_day is False and status in ("not_fired", "scheduled"):
        return "holiday"
    if trading_day is None and status == "not_fired":
        return "unknown"
    return status


def _evidence_after_schedule(value, today: date, scheduled: "time | None") -> bool:
    """오늘 날짜이고, `scheduled` 가 있으면 그 시각보다 `_SCHEDULE_EVIDENCE_GRACE`
    이상 이르지 않은 증거만 "오늘 이 행이 대표하는 예정 실행" 으로 인정한다.

    부팅 즉시실행·수동 새로고침이 같은 마커/진행률 키를 공유하므로, 예정 시각보다
    몇 시간이나 이른 오늘 날짜 증거는 이 행의 답이 아니라 다른 경로(catch-up·운영자
    트리거)의 결과일 수 있다(cycle285 검증 HIGH #2/#3 + scope MEDIUM #2). `scheduled`
    가 없는 행(예: 클라우드 루틴)은 날짜만 비교한다(종전 동작 보존).
    """
    dt = _parse_iso(value) if isinstance(value, str) else value
    if not isinstance(dt, datetime):
        return False
    dt_kst = dt.astimezone(_KST) if dt.tzinfo else dt.replace(tzinfo=_KST)
    if dt_kst.date() != today:
        return False
    if scheduled is None:
        return True
    scheduled_dt = datetime.combine(today, scheduled, tzinfo=_KST)
    return dt_kst >= scheduled_dt - _SCHEDULE_EVIDENCE_GRACE


def _degrade_on_error(status: str, *, errored: bool) -> str:
    """이 행의 유일한 산출물 소스가 실패했으면 `unknown` — "모른다" 를 "안 됐다" 로
    보여주지 않는다(cycle285 검증 honest 렌즈 MEDIUM #3). `scheduled` 는 증거가 아니라
    시계 판정이라 소스 실패와 무관하게 유지한다.
    """
    if errored and status != "scheduled":
        return "unknown"
    return status


def _task_row(
    task_id: str,
    label_ko: str,
    scheduled: "time | None",
    status: str,
    *,
    last_success_at: "str | None" = None,
    evidence: "dict | None" = None,
    note: "str | None" = None,
) -> dict:
    return {
        "id": task_id,
        "label_ko": label_ko,
        "scheduled_at": _hms(scheduled),
        "status": status,
        "last_success_at": last_success_at,
        "evidence": evidence or {},
        "note": note,
    }


# ---------------------------------------------------------------------------
# 순수 헬퍼 — 상태 판정 (진행률/마커/산출물 각 계열)
# ---------------------------------------------------------------------------
def _progress_status(
    *,
    progress: dict,
    marker_iso: "str | None",
    today: date,
    now_t: time,
    scheduled: "time | None",
    as_of: datetime,
    weekly_gate_hours: "float | None" = None,
) -> tuple[str, dict]:
    """`refresh_progress` 5키 진행률 + `system_config` 마커를 함께 읽는 공통 판정.

    진행률이 오늘 값이면 최우선 채택(가장 신선한 증거). 진행률이 어제 값째 남아
    있어도(`refresh_progress` 는 일일 초기화가 없다 — 사이클 285 조사 §3) 오늘
    날짜의 마커가 있으면 `done` 으로 승격한다(재시작으로 메모리만 비었을 뿐 성공은
    했을 수 있다). "오늘" 판정은 `_evidence_after_schedule` 이 한다 — 날짜만 보지
    않고 예정 시각보다 몇 시간 이상 이른 증거(부팅 catch-up·수동 트리거)는 걸러낸다.
    """
    status = progress.get("status")
    started_today = _evidence_after_schedule(progress.get("started_at"), today, scheduled)
    finished_today = _evidence_after_schedule(progress.get("finished_at"), today, scheduled)
    evidence = {
        "total": progress.get("total"),
        "processed": progress.get("processed"),
        "updated": progress.get("updated"),
        "skipped": progress.get("skipped"),
        "failed": progress.get("failed"),
        "elapsed_ms": progress.get("elapsed_ms"),
        "error_message": progress.get("error_message"),
    }
    if status == "running" and started_today:
        return "running", evidence
    if status == "completed" and finished_today:
        if (progress.get("skipped") or 0) > 0 and not progress.get("updated") and (
            progress.get("total") or 0
        ) > 0:
            return "skipped_fresh", evidence
        return "done", evidence
    if status == "failed" and finished_today:
        return "failed", evidence
    if _evidence_after_schedule(marker_iso, today, scheduled):
        return "done", evidence
    if weekly_gate_hours is not None:
        marker_dt = _parse_iso(marker_iso)
        if marker_dt is not None:
            age_h = (as_of - marker_dt).total_seconds() / 3600.0
            if 0 <= age_h < weekly_gate_hours:
                return "skipped_weekly", evidence
    if scheduled is not None and now_t < scheduled:
        return "scheduled", evidence
    return "not_fired", evidence


def _artifact_status(*, count: "int | None", now_t: time, scheduled: "time | None") -> str:
    if count:
        return "done"
    if scheduled is not None and now_t < scheduled:
        return "scheduled"
    return "not_fired"


def _no_evidence_status(*, now_t: time, scheduled: "time | None") -> str:
    """마커도 산출물도 없는 작업 — `scheduled` 아니면 항상 `unknown`(휴장 무관)."""
    if scheduled is not None and now_t < scheduled:
        return "scheduled"
    return "unknown"


def _milestone_status(*, now_t: time, scheduled: "time | None") -> str:
    """시계 하나로만 결정되는 마일스톤(예: 매수 중단 컷오프) — 산출물이 없다.

    `done` 은 "그 컷오프 시각이 지났다" 는 사실일 뿐, 그 작업이 실제로 수행됐다는
    증거가 아니다 — `note` 가 이 차이를 밝힌다.
    """
    if scheduled is not None and now_t < scheduled:
        return "scheduled"
    return "done"


def _metrics_snapshot_status(
    *, log_report: "dict | None", now_t: time, scheduled: "time | None"
) -> str:
    metrics = (log_report or {}).get("metrics")
    snapshot_pass = metrics.get("snapshot_pass") if isinstance(metrics, dict) else None
    # ⚠️ `daily_metrics_snapshot.py` 는 `metrics["snapshot_pass"] = 1`(정수)을 심는다
    # — bool `True` 가 아니다. `is True` 항등 비교는 항상 거짓이 되어 성공을 영원히
    # `not_fired`/`overwritten` 으로 오분류한다. truthy 로 판정한다.
    if snapshot_pass:
        return "done"
    if snapshot_pass is False or snapshot_pass == 0:
        return "failed"
    # 키 자체가 없다 — 21:30 완전판이 이미 통째로 덮어썼거나(정상, 최종본 존재),
    # 아직 아무 것도 안 남겼거나, 20:20 클라우드 루틴이 placeholder 행(summary="")만
    # 남겼을 수 있다. ⚠️ cycle285 검증(honest+test 렌즈 HIGH) 시정 — 종전에는
    # "정산 시각이 지났고 행이 존재한다" 만으로 `overwritten`(=완료 취급)을 단정해,
    # 20:05 스냅샷이 그날 아예 발화하지 않았어도 21:31 부터 영원히 "완료" 로 보였다.
    # `_is_complete_report` 는 cycle283 재실행 가드가 쓰는 것과 **같은** 4축 판정기라
    # (summary+model+비-placeholder+비-스냅샷) 21:30 완전판이 *실제로* 이 행을
    # 덮어썼다는 증거가 있을 때만 `overwritten` 을 준다 — 없으면 "판정 불가" 로 낮춘다.
    if now_t >= TIME_SETTLEMENT:
        if _is_complete_report(log_report):
            return "overwritten"
        return "unknown"
    if scheduled is not None and now_t < scheduled:
        return "scheduled"
    return "not_fired"


def _log_analysis_status(
    *, log_report: "dict | None", now_t: time, scheduled: "time | None"
) -> str:
    """cycle283 의 4축 판정기(`_is_complete_report`)를 **그대로 재사용**한다 — 새로
    쓰면 그 4축(1차 스냅샷 배제·OpenAI 빈 응답 배제·model 필수)을 다시 틀린다."""
    if log_report is not None:
        summary = (log_report.get("summary") or "").strip()
        if summary == OPENAI_EMPTY_RESPONSE_SUMMARY:
            return "failed"
        if _is_complete_report(log_report):
            return "done"
    if scheduled is not None and now_t < scheduled:
        return "scheduled"
    return "not_fired"


def _cloud_routine_status(*, log_report: "dict | None") -> str:
    if log_report and log_report.get("ext_created_at"):
        return "done"
    return "unknown"


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------
@router.get("", response_model=ApiResponse)
async def read_market_ops():
    """오늘 야간작업 현황 — 예정/진행/완료/실패/건너뜀/미발화/휴장/확인불가."""
    as_of = datetime.now(_KST)
    today = as_of.date()
    now_t = as_of.time()

    trading_day: "bool | None" = None
    trading_day_source = "unknown"
    errors: list[str] = []

    try:
        trading_day, trading_day_source = await _resolve_trading_day(today)
    except Exception:
        logger.exception("[market_ops] 휴장일 조회 실패")
        errors.append("trading_day")

    engine_running = False
    engine_phase = "idle"
    try:
        engine_running = bool(getattr(trading_scheduler, "is_running", False))
        engine_phase = str(getattr(trading_scheduler, "_phase", "idle"))
    except Exception:
        logger.exception("[market_ops] 엔진 상태 조회 실패")
        errors.append("engine")

    markers: dict = {}
    try:
        markers = await system_config.get_task_last_success_bulk(
            list(_MARKER_TASK_LABELS) + [_HEARTBEAT_LABEL]
        )
    except Exception:
        logger.exception("[market_ops] 마커 일괄 조회 실패")
        errors.append("markers")

    progress_all: dict = {}
    try:
        progress_all = refresh_progress.get_all_progress()
    except Exception:
        logger.exception("[market_ops] 진행률 조회 실패")
        errors.append("progress")

    combined: "dict | None" = None
    try:
        combined = await pg.fetchrow(_COMBINED_SQL, to_date(today))
    except Exception:
        logger.exception("[market_ops] 산출물 집계 쿼리 실패")
        errors.append("artifacts")
    combined = combined or {}

    log_report: "dict | None" = None
    try:
        log_report = await get_log_report(today)
    except Exception:
        logger.exception("[market_ops] daily_log_reports 조회 실패")
        errors.append("log_report")

    def marker(label: str) -> "str | None":
        return markers.get(label)

    def progress(key: str) -> dict:
        return progress_all.get(key) or {}

    tasks: list[dict] = []
    # 마커·진행률 소스가 **둘 다** 실패했을 때만 낮춘다 — 한쪽만 실패해도 다른 쪽
    # 증거로 정상 판정이 가능하다(부분 실패까지 unknown 으로 뭉개지 않는다).
    _markers_and_progress_failed = "markers" in errors and "progress" in errors
    _artifacts_failed = "artifacts" in errors
    _log_report_failed = "log_report" in errors

    # 1. 종목마스터 기본정보 보강 — TIME_STOCK_MASTER_BASICS_REFRESH
    status, evidence = _progress_status(
        progress=progress("basics"),
        marker_iso=marker("stock_master_basics_refresh"),
        today=today,
        now_t=now_t,
        scheduled=TIME_STOCK_MASTER_BASICS_REFRESH,
        as_of=as_of,
    )
    evidence["refreshed_at"] = combined.get("sm_refreshed_last")
    status = _degrade_on_error(status, errored=_markers_and_progress_failed)
    tasks.append(_task_row(
        "stock_master_basics_refresh", "종목마스터 기본정보 보강",
        TIME_STOCK_MASTER_BASICS_REFRESH, _finalize_status(status, trading_day),
        last_success_at=marker("stock_master_basics_refresh"), evidence=evidence,
    ))

    # 2. 일봉 retention 정리 — TIME_STOCK_MASTER_DAILY_PURGE. 마커·진행률 없음, retention 경계만 관측
    tasks.append(_task_row(
        "stock_master_daily_purge", "일봉 보관기간 정리",
        TIME_STOCK_MASTER_DAILY_PURGE,
        _finalize_status(_no_evidence_status(now_t=now_t, scheduled=TIME_STOCK_MASTER_DAILY_PURGE), trading_day),
        evidence={
            "retention_tail": None if _artifacts_failed else _iso_date(combined.get("daily_tail")),
        },
        note="이 작업은 성공 마커를 남기지 않는다 — 보관 경계값만으로는 오늘 실행 여부를 알 수 없다",
    ))

    # 3. 저녁 잠정 퍼널 캡처 — TIME_EVENING_FUNNEL_CAPTURE. `is_provisional=TRUE` 산출물로만 판정
    # (09:30 자동 캡처·스캐너 필터 훅은 `is_provisional=False` 라 여기 안 섞인다 — HIGH #1 시정)
    funnel_rows = combined.get("funnel_rows") or 0
    status = _degrade_on_error(
        _artifact_status(count=funnel_rows, now_t=now_t, scheduled=TIME_EVENING_FUNNEL_CAPTURE),
        errored=_artifacts_failed,
    )
    tasks.append(_task_row(
        "evening_funnel_capture", "저녁 잠정 퍼널 캡처",
        TIME_EVENING_FUNNEL_CAPTURE, _finalize_status(status, trading_day),
        last_success_at=combined.get("funnel_last_at"),
        evidence={"snapshot_rows_today": funnel_rows},
    ))

    # 4. 종목 마스터 파일(.mst) 적재 — TIME_STOCK_MASTER_MASTER_LOAD
    status, evidence = _progress_status(
        progress=progress("master"),
        marker_iso=marker("stock_master_master_load"),
        today=today,
        now_t=now_t,
        scheduled=TIME_STOCK_MASTER_MASTER_LOAD,
        as_of=as_of,
    )
    evidence["master_raw_updated_at"] = combined.get("sm_master_last")
    status = _degrade_on_error(status, errored=_markers_and_progress_failed)
    tasks.append(_task_row(
        "stock_master_master_load", "종목마스터 파일(.mst) 적재",
        TIME_STOCK_MASTER_MASTER_LOAD, _finalize_status(status, trading_day),
        last_success_at=marker("stock_master_master_load"), evidence=evidence,
    ))

    # 5. 재무 데이터 적재 — TIME_STOCK_MASTER_FINANCIAL_LOAD(주 1회 게이트)
    status, evidence = _progress_status(
        progress=progress("financial"),
        marker_iso=marker("stock_master_financial_load"),
        today=today,
        now_t=now_t,
        scheduled=TIME_STOCK_MASTER_FINANCIAL_LOAD,
        as_of=as_of,
        weekly_gate_hours=_FINANCIAL_WEEKLY_GATE_HOURS,
    )
    status = _degrade_on_error(status, errored=_markers_and_progress_failed)
    tasks.append(_task_row(
        "stock_master_financial_load", "재무 데이터 적재(주 1회)",
        TIME_STOCK_MASTER_FINANCIAL_LOAD, _finalize_status(status, trading_day),
        last_success_at=marker("stock_master_financial_load"), evidence=evidence,
        note=(
            "마지막 성공이 7일 이내다 — 오늘 이 시각 실행 여부는 이 증거만으로는"
            " 알 수 없다(주 1회 게이트, 매주 정상적으로 건너뛸 수 있다)"
        ) if status == "skipped_weekly" else None,
    ))

    # 6. 보조 시세계정 토큰 강제 재발급 — TIME_QUOTE_TOKEN_REFRESH. 마커 자체가 없다
    tasks.append(_task_row(
        "quote_token_refresh", "보조 시세계정 토큰 강제 재발급",
        TIME_QUOTE_TOKEN_REFRESH,
        _finalize_status(_no_evidence_status(now_t=now_t, scheduled=TIME_QUOTE_TOKEN_REFRESH), trading_day),
        note="이 작업은 성공 마커를 남기지 않는다 — 서버 로그(system_logs) 로만 확인 가능",
    ))

    # 7. NXT 애프터 신규 매수 중단 — TIME_NXT_POST_BUY_STOP. 시계 마일스톤, 산출물 없음
    tasks.append(_task_row(
        "nxt_post_buy_stop", "NXT 애프터 신규 매수 중단",
        TIME_NXT_POST_BUY_STOP,
        _finalize_status(_milestone_status(now_t=now_t, scheduled=TIME_NXT_POST_BUY_STOP), trading_day),
        note="시각 기준 컷오프 — 별도 산출물 없음(코드가 그 시각부터 매수를 막는다는 사실만 보장)",
    ))

    # 8. AI 매매자문 — TIME_RECOMMENDATION
    rec_rows = combined.get("rec_rows") or 0
    status = _degrade_on_error(
        _artifact_status(count=rec_rows, now_t=now_t, scheduled=TIME_RECOMMENDATION),
        errored=_artifacts_failed,
    )
    tasks.append(_task_row(
        "recommendation", "AI 매매자문",
        TIME_RECOMMENDATION, _finalize_status(status, trading_day),
        last_success_at=combined.get("rec_last_at"),
        evidence={"recommendation_rows_today": rec_rows},
    ))

    # 9. 전체 유니버스 적재 — TIME_FULL_UNIVERSE_LOAD. 마커 없음, progress 만
    status, evidence = _progress_status(
        progress=progress("universe"),
        marker_iso=None,
        today=today,
        now_t=now_t,
        scheduled=TIME_FULL_UNIVERSE_LOAD,
        as_of=as_of,
    )
    status = _degrade_on_error(status, errored="progress" in errors)
    tasks.append(_task_row(
        "full_universe_load", "전체 유니버스 적재",
        TIME_FULL_UNIVERSE_LOAD, _finalize_status(status, trading_day),
        evidence=evidence,
    ))

    # 10. metrics 1차 스냅샷 — TIME_METRICS_SNAPSHOT. daily_log_reports 휘발성 컬럼
    status = _degrade_on_error(
        _metrics_snapshot_status(log_report=log_report, now_t=now_t, scheduled=TIME_METRICS_SNAPSHOT),
        errored=_log_report_failed,
    )
    tasks.append(_task_row(
        "metrics_snapshot", "매매지표 1차 스냅샷",
        TIME_METRICS_SNAPSHOT, _finalize_status(status, trading_day),
        note=(
            f"정산({_hms(TIME_SETTLEMENT)}) 의 최종 분석이 이 값을 덮어쓴다 — "
            "정산 이후 'overwritten' 은 결함이 아니다(그 전에 완전판 증거가 없으면"
            " '확인 불가' 로 남긴다)"
        ),
    ))

    # 11. 클라우드 로그 분석 루틴 (외부, 예정 시각 상수 없음)
    status = _degrade_on_error(_cloud_routine_status(log_report=log_report), errored=_log_report_failed)
    tasks.append(_task_row(
        "cloud_report_routine", "클라우드 로그 분석 루틴(외부)",
        None, _finalize_status(status, trading_day),
        last_success_at=(log_report or {}).get("ext_created_at") if log_report else None,
        evidence={
            "ext_provider": (log_report or {}).get("ext_provider"),
            "ext_model": (log_report or {}).get("ext_model"),
        },
        note="이 코드베이스에 예정 시각 상수가 없다 — 외부 크론이 부른다",
    ))

    # 12. 일봉 적재 — TIME_STOCK_MASTER_DAILY_LOAD
    status, evidence = _progress_status(
        progress=progress("daily"),
        marker_iso=marker("stock_master_daily_load"),
        today=today,
        now_t=now_t,
        scheduled=TIME_STOCK_MASTER_DAILY_LOAD,
        as_of=as_of,
    )
    evidence["daily_head"] = None if _artifacts_failed else _iso_date(combined.get("daily_head"))
    evidence["daily_rows_today"] = combined.get("daily_today_rows") or 0
    status = _degrade_on_error(status, errored=_markers_and_progress_failed)
    tasks.append(_task_row(
        "stock_master_daily_load", "일봉(KIS) 적재",
        TIME_STOCK_MASTER_DAILY_LOAD, _finalize_status(status, trading_day),
        last_success_at=marker("stock_master_daily_load"), evidence=evidence,
        # ⚠️ `_artifacts_failed` 가드 없이 `combined.get("daily_head")` 만 보면(구
        # cycle285 배포) 집계 쿼리 실패로 `combined={}` 가 됐을 때도 "daily_head 가
        # 오늘이 아니다" 로 읽혀 근거 없는 경고가 붙는다(scope 렌즈 LOW #3).
        note=(
            "daily_head 가 오늘이 아니면 다음 영업일 아침 재기동 전까지 그대로다"
            if (not _artifacts_failed) and _iso_date(combined.get("daily_head")) != today.isoformat()
            else None
        ),
    ))

    # 13. 정산(_settle) — TIME_SETTLEMENT
    perf_rows = combined.get("perf_rows") or 0
    status = _degrade_on_error(
        _artifact_status(count=perf_rows, now_t=now_t, scheduled=TIME_SETTLEMENT),
        errored=_artifacts_failed,
    )
    tasks.append(_task_row(
        "settlement", "정산(전략별 실적 집계)",
        TIME_SETTLEMENT, _finalize_status(status, trading_day),
        evidence={"daily_performance_rows_today": perf_rows},
    ))

    # 14. 일일 로그 분석 — TIME_SETTLEMENT 직후, 같은 시각
    status = _degrade_on_error(
        _log_analysis_status(log_report=log_report, now_t=now_t, scheduled=TIME_SETTLEMENT),
        errored=_log_report_failed,
    )
    tasks.append(_task_row(
        "log_analysis", "일일 로그 분석(AI)",
        TIME_SETTLEMENT, _finalize_status(status, trading_day),
        evidence={
            "model": (log_report or {}).get("model") if log_report else None,
            "has_api_metrics": bool(
                isinstance((log_report or {}).get("metrics"), dict)
                and "api_metrics" in (log_report or {}).get("metrics", {})
            ),
        },
    ))

    data = {
        "as_of_kst": as_of.isoformat(),
        "is_trading_day": trading_day,
        "trading_day_source": trading_day_source,
        "engine": {
            "running": engine_running,
            "phase": engine_phase,
            "heartbeat_at": marker(_HEARTBEAT_LABEL),
        },
        "tasks": tasks,
        "evidence_errors": errors,
    }
    return ApiResponse(success=True, data=data)
