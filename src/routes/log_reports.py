"""일일 로그 분석 리포트 라우트: /api/log-reports/*"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.db._kst import KST
from src.db.log_reports import get_log_report, list_log_reports, upsert_external_report
from src.engine.log_analysis_engine import _validate_report, collect_daily_log_metrics, generate_daily_log_report
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/log-reports", tags=["log-reports"])

#: `/api/log-reports/bundle` 이 노출하는 `api_metrics`/`strategy_funnel`/
#: `portfolio_risk_snapshot` 은 프로세스의 **현재** 스냅샷이다 — 과거 날짜를
#: 조회해도 "그 날의 값" 이 아니다(`portfolio_risk_snapshot` 은 현재 보유·잔고를
#: 읽는 `compute_portfolio_risk_snapshot` 호출 결과라 특히 그렇다 — 과거 영업일
#: 번들에 실려도 "그날의 리스크"가 아니라 "지금의 리스크"다). 20:20 클라우드
#: 루틴이 과거 번들을 그날의 사실로 읽고 거짓 인과를 리포트에 쓰지 않도록 응답에
#: 그 사실을 명시한다.
_PROCESS_SCOPED_KEYS = ["api_metrics", "strategy_funnel", "portfolio_risk_snapshot"]


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


@router.post("/run", response_model=ApiResponse)
async def run_now():
    """수동 트리거 — 즉시 일일 로그 분석을 실행한다 (정산을 기다리지 않고 임의 시점에 호출 가능)."""
    try:
        row = await generate_daily_log_report()
    except Exception:
        logger.exception("로그 분석 수동 실행 실패")
        return ApiResponse(success=False, message="분석 실행 실패")
    if not row:
        return ApiResponse(
            success=False,
            message="분석 결과 없음(이미 오늘 리포트가 있거나 OPENAI_API_KEY 미설정)",
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
