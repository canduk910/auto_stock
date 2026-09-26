"""일일 로그 분석 리포트 라우트: /api/log-reports/*"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.db._kst import KST
from src.db.log_reports import get_log_report, list_log_reports, upsert_external_report
from src.engine.log_analysis_engine import (
    OPENAI_EMPTY_RESPONSE_SUMMARY,
    _validate_report,
    collect_daily_log_metrics,
    generate_daily_log_report,
)
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/log-reports", tags=["log-reports"])

#: `/api/log-reports/bundle` 이 노출하는 `api_metrics`/`strategy_funnel`/
#: `portfolio_risk_snapshot` 은 `collect_daily_log_metrics` 안에서 프로세스의
#: **현재** 상태로 채워진다 — 과거 날짜를 그냥 넘겨도 호출 시점(오늘)의 값이다.
#: **과거 날짜 조회는 그날 저장된 `daily_log_reports.metrics` 값으로 이 3키만
#: 덮어쓴다**(`_overlay_process_scoped_from_db`) — 20:05 1차 스냅샷·21:30 완전판이
#: 그날 정확히 채워 이미 저장해 둔 값이 정본이다. 저장 행이 없거나(아직 그날
#: 리포트가 안 만들어짐)·조회가 실패하면 fail-open 으로 프로세스 값을 그대로 둔다
#: (번들 전체가 죽으면 안 된다). **오늘 날짜 조회는 이 오버레이를 시도하지 않는다**
#: (byte 동일 — 20:20 클라우드 루틴의 매일 호출 경로 무변경). 그래도 이 목록은
#: "이 3키는 본질적으로 프로세스에서 나온다" 는 표식으로 응답에 남긴다 —
#: `portfolio_risk_snapshot` 은 과거 조회에서도 "그날 21:30 시점의 지금" 일 뿐
#: 그날 전체의 리스크 이력이 아니다.
_PROCESS_SCOPED_KEYS = ["api_metrics", "strategy_funnel", "portfolio_risk_snapshot"]


async def _overlay_process_scoped_from_db(metrics: dict, target: date) -> dict:
    """과거 날짜 조회 시 `_PROCESS_SCOPED_KEYS` 3키를 그날 저장값으로 덮어쓴다.

    `metrics` 는 `collect_daily_log_metrics(target)` 가 방금 만든 dict 다 — 로그·거래·
    funnel 단계별 등 나머지 키는 이미 `target` 로 필터링돼 정확하므로 손대지 않는다.
    이 3키만 `daily_log_reports` 의 그날 행(`get_log_report`)에서 가져와 in-place 로
    바꾼다. 행이 없거나 `metrics` 컬럼 모양이 dict 가 아니거나 조회 자체가 실패하면
    **fail-open**(프로세스 값 유지) — 과거 값 복원 실패가 번들 전체를 죽이면 안 된다.
    """
    try:
        stored = await get_log_report(target)
    except Exception:
        logger.exception(
            "[log_reports_bundle_overlay] target_date=%s DB 조회 실패 — 프로세스 값 유지",
            target,
        )
        return metrics
    if not stored:
        return metrics
    stored_metrics = stored.get("metrics")
    if not isinstance(stored_metrics, dict):
        return metrics
    for key in _PROCESS_SCOPED_KEYS:
        if key in stored_metrics:
            metrics[key] = stored_metrics[key]
    return metrics


def _parse_date_strict(raw: str) -> date:
    """`YYYY-MM-DD` 엄격 파싱.

    `date.fromisoformat` 은 Python 3.11+ 부터 `"20260904"`(구분자 없는 기본 형식)
    까지 조용히 받아들인다 — 인터넷 노출면인 이 라우트에서는 그게 "형식 오류를
    형식 정상으로 오판"하는 결함이 된다. `strptime` 은 리터럴 대시를 요구해 그
    변형을 거부한다.
    """
    return datetime.strptime(raw, "%Y-%m-%d").date()


class ExternalReportIn(BaseModel):
    """`POST /api/log-reports/{date}/external` 바디 — 리포터 스코프의 유일한 쓰기.

    이 경로는 nginx `map $remote_user` 가 리포터 Basic 사용자에게 주입하는 키
    하나로만 도달 가능하다(`src/middleware/api_auth.py`). 검증 없는 저장은 인증을
    통과한 뒤의 유일한 남은 방어선을 없애는 것과 같다.
    """

    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=4000)
    findings: list[dict] = Field(default_factory=list, max_length=50)
    report_md: str | None = Field(default=None, max_length=200_000)


@router.get("/bundle", response_model=ApiResponse)
async def get_bundle(date: str | None = None):
    """분석 입력 번들 — 20:20 KST 클라우드 루틴이 읽는다.

    **`/{target_date}` 보다 앞에 선언한다** — FastAPI 는 선언 순서로 매칭하므로
    뒤에 두면 `bundle` 이 날짜 파라미터로 잡혀 "날짜 형식 오류" 라는 그럴듯한 200 을
    돌려주고, 루틴은 매일 빈손으로 재시도조차 못 한다.
    """
    now = datetime.now(KST)
    if date:
        try:
            target = _parse_date_strict(date)
        except ValueError:
            return ApiResponse(success=False, message="날짜 형식 오류 (YYYY-MM-DD)")
    else:
        target = now.date()

    if target > now.date():
        return ApiResponse(success=False, message="미래 날짜는 조회할 수 없습니다")

    try:
        metrics = await collect_daily_log_metrics(target)
        if target < now.date():
            metrics = await _overlay_process_scoped_from_db(metrics, target)
    except Exception:
        logger.exception("[log_reports_bundle] 수집 실패")
        return ApiResponse(success=False, message="번들 수집 실패")

    return ApiResponse(
        success=True,
        data={
            "target_date": target.isoformat(),
            "collected_at": datetime.now(KST).isoformat(),
            "metrics": metrics,
            "process_scoped_keys": _PROCESS_SCOPED_KEYS,
        },
    )


@router.get("", response_model=ApiResponse)
async def list_reports(days: int = 30):
    """최근 N일치 일일 로그 분석 리포트를 신규순으로 반환한다."""
    rows = await list_log_reports(days=days)
    return ApiResponse(success=True, data=rows)


@router.get("/{target_date}", response_model=ApiResponse)
async def get_report(target_date: str):
    """단일 영업일 리포트를 반환한다 (YYYY-MM-DD)."""
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        return ApiResponse(success=False, message="날짜 형식 오류 (YYYY-MM-DD)")
    row = await get_log_report(d)
    if not row:
        return ApiResponse(success=False, message="리포트가 없습니다")
    return ApiResponse(success=True, data=row)


def _is_complete_report(existing: dict | None) -> bool:
    """그 행이 **덮어쓰면 손해인 완성본**인가 (cycle283 C9-b 재실행 가드의 유일한 판정).

    네 축을 **모두** 만족해야 완성본이다. 한 축이라도 빠지면 재실행을 허용한다 —
    이 가드의 목적은 "재실행 금지" 가 아니라 "완성본 파괴 방지" 이기 때문이다.

    1. 행이 있다.
    2. **1차 스냅샷이 아니다** — `metrics["snapshot_pass"]` 센티널
       (`daily_metrics_snapshot.SNAPSHOT_SUMMARY` 는 비어 있지 않으므로 `summary` 축
       만으로는 20:05~21:30 구간을 통째로 막아 버린다. 그래서 이 축이 따로 있다).
    3. `summary` 가 비어 있지 않고 **OpenAI 실패 placeholder 가 아니다**
       (`OPENAI_EMPTY_RESPONSE_SUMMARY` — 그 행은 `model` 이 채워져 있어 종전 판정에서
       '완성본' 으로 오분류됐고, 정작 수동 복구가 필요한 유일한 날이 막혔다).
    4. `model` 이 채워져 있다(= LLM 경로가 실제로 돌았다).
    """
    if not existing:
        return False
    metrics = existing.get("metrics")
    if isinstance(metrics, dict) and metrics.get("snapshot_pass"):
        return False
    summary = (existing.get("summary") or "").strip()
    if not summary or summary == OPENAI_EMPTY_RESPONSE_SUMMARY:
        return False
    return bool(existing.get("model"))


@router.post("/run", response_model=ApiResponse)
async def run_now(force: bool = False):
    """수동 트리거 — 즉시 일일 로그 분석을 실행한다 (정산을 기다리지 않고 임의 시점 호출).

    🔴 cycle283 C9-b — **기본은 비파괴**다. `insert_log_report` 가 upsert 로 바뀌면서
    (cycle283 D6) 이 라우트의 재실행이 처음으로 **파괴적**이 됐다: 21:30 정산은
    `reset_request_metrics()` 와 `_reset_daily_state()` 를 돌린 뒤이므로, 그 뒤에 다시
    실행하면 `collect_daily_log_metrics` 가 `api_metrics` 0 · `strategy_funnel` 0 을
    새로 만들어 **그날 완성 리포트를 통째로 덮어쓴다**. 종전 순수 INSERT 에서는 UNIQUE
    충돌로 무해한 no-op 이었다.

    그래서 **완성 리포트**(`_is_complete_report` 판정)가 이미 있으면 재분석 자체를
    **실행하지 않고** 거부한다. 덮어쓰려면 `?force=1`.
    막지 않는 세 경우 = 행이 아예 없음 · 1차 스냅샷만 있는 20:05~21:30 구간 ·
    **OpenAI 가 실패한 날의 행**. 마지막 하나가 이 라우트의 존재 이유다.

    ⚠️ `?force=1` 은 21:30 이후에는 여전히 파괴적이다(그 시점엔 `reset_request_metrics()`
    와 `_reset_daily_state()` 가 이미 돌아 `api_metrics`/`strategy_funnel` 이 0 이다).
    거부 메시지가 그 사실과 플래그를 함께 말한다 — 운영자가 모르고 누르지 않게.
    """
    if not force:
        try:
            existing = await get_log_report(datetime.now(KST).date())
        except Exception:
            logger.exception("[log_report_rerun_guard] 기존 리포트 조회 실패 — graceful 진행")
            existing = None
        if _is_complete_report(existing):
            return ApiResponse(
                success=False,
                message=(
                    "오늘 완성 리포트가 이미 있습니다 — 재실행하면 api_metrics/"
                    "strategy_funnel 이 0 으로 덮어써집니다. 덮어쓰려면 ?force=1"
                ),
            )
    try:
        row = await generate_daily_log_report()
    except Exception:
        logger.exception("로그 분석 수동 실행 실패")
        return ApiResponse(success=False, message="분석 실행 실패")
    if not row:
        return ApiResponse(
            success=False,
            message="분석 결과 없음(OPENAI_API_KEY 미설정이거나 저장 실패)",
        )
    return ApiResponse(success=True, data=row)


@router.post("/{target_date}/external", response_model=ApiResponse)
async def post_external_report(target_date: str, body: ExternalReportIn):
    """20:20 KST 클라우드 루틴의 분석 결과 저장 — 리포터 스코프의 유일한 쓰기 경로.

    findings 는 기존 OpenAI 경로와 **같은 정규화기**(`_validate_report`)를 거친다 —
    두 벌이 되면 병행 기간의 비교가 성립하지 않는다.
    """
    try:
        d = _parse_date_strict(target_date)
    except ValueError:
        return ApiResponse(success=False, message="날짜 형식 오류 (YYYY-MM-DD)")

    _, findings = _validate_report({"findings": body.findings})

    try:
        row = await upsert_external_report(
            target_date=d,
            provider=body.provider,
            model=body.model,
            summary=body.summary,
            findings=findings,
            report_md=body.report_md,
        )
    except Exception:
        logger.exception("[log_reports_external] 저장 실패")
        return ApiResponse(success=False, message="저장 실패")

    return ApiResponse(success=True, data=row)
