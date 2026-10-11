"""20:00 AI 자문 주간 실행일 판정 leaf (cycle445, D8 — 사용자 결정 2026-10-11).

매일 20:00 돌던 전략수정 AI 자문(+ 거기 딸린 외부 백테스트 enqueue, fire-and-forget)을
주간 자문일(기본 목요일)에만 돌린다. 근거 = `_workspace/domain_consult/weekly_advice_2026-10-08.md`
§5.3 — 30일 589:2(99.7% 조임)·반영 0건인데 매일 OpenAI 호출·`parameter_recommendations`
130행이 쌓였다. **20:05 metrics 1차 스냅샷·20:30 일봉 적재·21:30 정산은 이 결정과
무관하게 그대로 매일 돈다**(이 모듈이 손대는 호출부는 `recommendation_engine.generate_recommendations`
하나뿐).

요일 판정은 시각을 인자로 받는 순수 함수(`is_weekly_advisory_day`)이고, 설정 조회는
별도 async 헬퍼(`should_run_weekly_advisory`)로 나눈다 — freezegun 벽시계 테스트가
DB 를 타지 않게, 그리고 호출부가 한 번의 await 로 결정을 받게 한다.

🔴 **공휴일 판정은 이 모듈의 책임이 아니다.** `src.engine.scheduler.TradingScheduler.run_daily()`
가 이미 KIS `chk-holiday` 로 주말·공휴일인 날 전체(08:00~21:30, 이 20:00 블록 포함)를
건너뛴다. 그래서 목요일이 공휴일이면 이 모듈의 판정에 도달하기 전에 그날 스케줄 전체가
스킵되어, "그 주 자문을 건너뛴다"가 추가 코드 없이 성립한다. 반대로 "직전 영업일로
당긴다"를 고르면 이 모듈이 `trading_calendar`로 평일-but-휴장과 주말을 가르고, 당겨진
날의 `target_date`가 그 전 주 자문과 `(target_date, strategy_id)` UNIQUE 를 다투지
않는지까지 책임져야 한다 — 끊기지 않는 캐던스의 이득이 그 복잡도·회귀 범위보다 크지
않다고 판단해 **그 주 건너뜀**을 택했다.
"""

from __future__ import annotations

from datetime import datetime

_WEEKDAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

#: 키 없음·오타·DB 장애 시 낙하하는 요일 — 목요일(클라우드 「주간 자문 목 20:30 KST」
#: 루틴이 그 직전 20:00 행을 읽는다, `reference_claude_routines`).
DEFAULT_WEEKDAY_CODE = "thu"


def normalize_weekday(raw: object) -> tuple[str, bool]:
    """`system_config` 원값 → `(코드, 유효 여부)`.

    `raw` 가 `_WEEKDAY_CODES` 안의 문자열(대소문자·앞뒤 공백 무시)일 때만 유효하다.
    그 밖(키 없음 `None`·malformed marker·숫자·dict·오타 문자열)은 전부
    `(DEFAULT_WEEKDAY_CODE, False)` — "키 없음"과 "모양이 틀린 값"을 구분하지
    않는다(둘 다 운영자가 요일을 명시하지 않은 것으로 본다).
    """
    if isinstance(raw, str):
        code = raw.strip().lower()
        if code in _WEEKDAY_CODES:
            return code, True
    return DEFAULT_WEEKDAY_CODE, False


def is_weekly_advisory_day(
    now_kst: datetime, *, weekday_code: str = DEFAULT_WEEKDAY_CODE,
) -> bool:
    """`now_kst.weekday()`(월=0 … 일=6)가 `weekday_code` 와 같은가.

    순수 함수 — 벽시계를 읽지 않는다(`now_kst` 는 호출자가 넘긴다, freezegun 없이도
    고정 시각으로 테스트할 수 있게). 공휴일 여부는 보지 않는다(모듈 docstring).
    `weekday_code` 가 `_WEEKDAY_CODES` 밖이면 `DEFAULT_WEEKDAY_CODE` 로 낙하한다 —
    오타가 "항상 False"(무기한 멈춤)가 아니라 "기본값"이 되게 한다.
    """
    try:
        idx = _WEEKDAY_CODES.index(weekday_code)
    except ValueError:
        idx = _WEEKDAY_CODES.index(DEFAULT_WEEKDAY_CODE)
    return now_kst.weekday() == idx


async def should_run_weekly_advisory(now_kst: datetime) -> dict:
    """오늘 20:00 AI 자문을 돌릴지 — 설정 조회 + 요일 판정을 한 호출로 묶는다.

    반환 = `{"run": bool, "weekday_code": str, "configured_valid": bool}`.

    **never-raise** — DB 조회 실패는 "키 없음"과 같게 다뤄 기본 요일(목)로
    판정한다. 기본값이 실제 목요일과 일치하므로, 요일을 바꾼 적 없는 운영에서는
    DB 장애가 있어도 그 주 목요일 자문이 그대로 돈다. 요일을 다른 값으로 바꾼
    운영에서만 장애가 난 그 날의 판정이 기본값(목)으로 떨어진다 — 비용 절감이
    목적인 기능이라 "원인을 모른 채 이번 주도 돈다" 쪽이 "원인을 모른 채 건너뛴다"
    보다 싸다(매주 한 번뿐이라 되돌리기도 쉽다).
    """
    try:
        from src.db.system_config import get_weekly_advisory_weekday_raw
        raw = await get_weekly_advisory_weekday_raw()
    except Exception:
        raw = None
    code, valid = normalize_weekday(raw)
    return {
        "run": is_weekly_advisory_day(now_kst, weekday_code=code),
        "weekday_code": code,
        "configured_valid": valid,
    }
