"""metrics 1차 스냅샷 — 20:05 KST (cycle283 D5, leaf).

## 왜
`daily_log_reports.metrics` 의 두 축 `api_metrics`(`src/api/base.py::get_request_metrics`)
와 `strategy_funnel`(레지스트리 메모리 카운터)은 **프로세스 메모리 전용**이다 — 프로세스가
죽으면 DB 로 복구할 길이 없다. cycle283 이 정산을 20:10 → 21:30 으로 미루면서 그 유실
노출이 10분 → **90분**이 됐다. 20:05 에 한 번 저장해 5분으로 줄인다.

## 계약
- 수집은 `collect_daily_log_metrics` **재사용** — 새 수집 코드를 만들지 않는다(두 벌이 되면
  21:30 완전판과의 비교가 성립하지 않는다).
- **OpenAI 를 호출하지 않는다** — 비용·지연 0. `model` 과 토큰 5컬럼은 전부 `None`.
- 🔴 **`reset_request_metrics()` 를 부르지 않는다.** 부르면 `api_metrics` 가 0부터 다시
  세어 21:30 완전판이 저녁 90분치만 보게 된다. 리셋은 **마지막 패스(21:30)에서만**.
- never-raise. 실패는 WARNING 1행 + 정산 경로 무영향(반환 `None`).
- 관측 마커 `[daily_metrics_snapshot] target_date=… pass=1 saved=1|0 elapsed_ms=…`
  **실행당 1행**. `saved=0`(WARNING) = 저장이 조용히 비었다 = D+1 판독의 성공 서명은
  "마커 1행" 이 아니라 **`saved=1` 1행**이다.

## 1차 행을 알아볼 수 있게 두는 이유
`upsert_external_report` 의 placeholder INSERT 도 `summary=''` 를 쓴다. 1차 스냅샷이 같은
빈 값을 쓰면 읽는 쪽이 "1차 스냅샷" 과 "20:20 루틴 placeholder" 를 구분할 수 없고, UI 는
`report.summary || '요약이 없습니다.'` 로 렌더해 20:05~21:30 사이 운영자에게 **분석
실패처럼 보인다**. 그래서 사람용 문구(`summary`)와 기계용 센티널(`metrics["snapshot_pass"]`)
을 **둘 다** 남긴다. 21:30 완전판이 upsert 로 두 값을 모두 덮어쓴다.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime

from src.db.log_reports import insert_log_report
from src.engine.log_metrics_collector import KST, collect_daily_log_metrics

logger = logging.getLogger(__name__)

#: 20:05~21:30 사이 UI/운영자가 이 행을 "분석 실패" 로 오독하지 않게 하는 사람용 문구.
SNAPSHOT_SUMMARY = "1차 스냅샷(20:05) — 최종 분석은 21:30 에 덮어씁니다."

__all__ = ["run_daily_metrics_snapshot", "SNAPSHOT_SUMMARY"]


async def run_daily_metrics_snapshot(target_date: date | None = None) -> dict | None:
    """당일 metrics 를 수집해 `daily_log_reports` 에 1차 저장한다 (OpenAI 미호출).

    Returns:
        저장된 row. 수집·저장 어느 쪽이 실패해도 `None`(never-raise).
    """
    started = _time.monotonic()
    day = target_date if target_date is not None else datetime.now(KST).date()
    try:
        metrics = await collect_daily_log_metrics(day)
        # 기계용 센티널 — **in-place** 로 심는다. 사본을 만들면 "수집 결과를 그대로
        # 저장한다"는 계약이 사본 여부에 따라 흔들린다(21:30 완전판은 이 키 없이 덮어쓴다).
        if isinstance(metrics, dict):
            metrics["snapshot_pass"] = 1
        row = await insert_log_report(
            target_date=day,
            summary=SNAPSHOT_SUMMARY,
            findings=[],
            metrics=metrics,
            model=None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            latency_ms=None,
            cost_estimate_usd=None,
        )
    except Exception:
        logger.warning(
            "[daily_metrics_snapshot_failed] target_date=%s — 1차 저장 실패 graceful "
            "(정산 21:30 완전판은 그대로 진행)",
            day, exc_info=True,
        )
        return None

    # `insert_log_report` 는 예상 밖 23505 를 만나면 **예외 없이 `None`** 을 돌려준다
    # (`[log_report_unexpected_conflict]`). 그때까지 `pass=1` 만 찍으면 D+1 판독이
    # "마커 1행 = 1차 저장 성공" 을 거짓으로 읽는다 — 저장 여부를 `saved=` 로 분리한다.
    elapsed_ms = int((_time.monotonic() - started) * 1000)
    if row is None:
        logger.warning(
            "[daily_metrics_snapshot] target_date=%s pass=1 saved=0 elapsed_ms=%d — "
            "저장 결과가 비었다(ON CONFLICT 타깃 확인). 21:30 완전판은 그대로 진행",
            day, elapsed_ms,
        )
        return None

    logger.info(
        "[daily_metrics_snapshot] target_date=%s pass=1 saved=1 elapsed_ms=%d",
        day, elapsed_ms,
    )
    return row
