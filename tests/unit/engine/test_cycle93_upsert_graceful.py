"""사이클 93 G-CC4 (HIGH) — scanner upsert chain 실패 시 graceful 영속 의무.

Red 명세 (`_workspace/red/cycle93_call_chain_broken.md`):

scheduler 본체 `_universe_eager_refresh_loop` self method 에 추가될 scanner upsert chain
호출이 예외를 던질 경우 (KIS Rate Limit / Supabase 일시 장애 / 부분 실패) 다음 단계
(`flush_universe_collector` 등) 가 영향 받지 않고 정상 진행해야 한다.

Red 상태 (사이클 93 시점):
- production 코드 0 (chain 자체 부재) → 다음 단계 graceful 검증 의미 없음 → FAIL

Green (backend-dev 인계 후):
- scheduler 본체에 다음 패턴 추가:
  ```
  try:
      await _scanner_upsert_loop(tickers)
      logger.info("[universe_eager_refresh] stock_master upsert 완료")
  except Exception:
      logger.exception("[universe_eager_refresh] stock_master upsert 실패 graceful")
  ```
- 예외 발생 시: chain 진행 + logger.exception ERROR 1건 + 다음 단계 도달 → PASS

영속 의무:
- 사이클 17 KIS LMS chain 영역 답습 (graceful 영구 보장)
- 사이클 78/79 graceful 영속 (lifecycle 영역 동일 패턴)
- 매매 안전성 무영향 (stock_master 영역 graceful)
- 운영 가시화 — `[universe_eager_refresh] stock_master upsert 실패 graceful` ERROR 영구 발화
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


_MOCK_TICKERS = ["005930", "402340"]


@pytest.mark.asyncio
async def test_g_cc4_scheduler_upsert_failure_does_not_break_chain(
    monkeypatch, caplog
):
    """G-CC4: scanner upsert chain 실패 시 chain 진행 + logger.exception ERROR 영구.

    검증 매트릭스:
    1. mock fetch_top_500_universe → 2 ticker 반환
    2. mock scanner module `_universe_eager_refresh_loop` → `raise RuntimeError("upsert 실패")`
    3. mock flush_universe_collector → 호출 카운트 (영향 X 확인)
    4. scheduler `_universe_eager_refresh_loop()` 호출 (_running=False 분기)
    5. 의무:
       - 전체 호출 예외 미전파 (테스트 fail 없이 통과)
       - caplog 에 ERROR 레벨 ≥ 1건 + `[universe_eager_refresh]` prefix 포함
       - upsert 예외에도 fetch + (개장 전 1회 분기 한정) 정상 완료

    Red 상태: production 코드 0 → 검증 의미 없음 → FAIL.

    Green: try/except graceful 추가 → 예외 흡수 + ERROR 로그 → PASS.

    영속: silent 결함 영구 차단 + 운영 가시화 동시 보장
    (사이클 17 KIS LMS chain graceful 패턴 답습).
    """
    from src.engine import scanner as _scanner_mod
    from src.engine import stock_master_metrics as _sm_metrics
    from src.engine.scheduler import TradingScheduler

    fetch_mock = AsyncMock(return_value=list(_MOCK_TICKERS))
    upsert_mock = AsyncMock(side_effect=RuntimeError("upsert 실패 (KIS Rate Limit 등)"))

    monkeypatch.setattr(_scanner_mod, "fetch_top_500_universe", fetch_mock, raising=False)
    monkeypatch.setattr(
        _scanner_mod, "_universe_eager_refresh_loop", upsert_mock, raising=False
    )
    monkeypatch.setattr(
        _sm_metrics, "flush_universe_collector", lambda: None, raising=False
    )

    sched = TradingScheduler()
    sched._running = False  # 5분 주기 차단 (개장 전 1회만)

    # caplog: src.engine.scheduler logger (사이클 60 I1 영속)
    caplog.set_level(logging.ERROR, logger="src.engine.scheduler")

    # 의무 1: 예외 미전파 (graceful 보장)
    try:
        await sched._universe_eager_refresh_loop()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"\n사이클 93 G-CC4 위반 — scanner upsert chain 실패가 외부 전파됨:\n\n"
            f"  예외: {type(exc).__name__}: {exc}\n\n"
            f"  결함 원인: scheduler 본체에 try/except graceful 누락\n"
            f"             → 사용자 결정 의무 (Q34=A graceful 영속) 위반\n"
            f"             → 운영 중 KIS Rate Limit / Supabase 일시 장애 시 task 영구 중단\n\n"
            f"  시정 (Green):\n"
            f"    try:\n"
            f"        await _scanner_upsert_loop(tickers)\n"
            f"        logger.info('[universe_eager_refresh] stock_master upsert 완료')\n"
            f"    except Exception:\n"
            f"        logger.exception('[universe_eager_refresh] stock_master upsert 실패 graceful')"
        )

    # 의무 2: upsert 가 호출은 됐어야 함 (chain 자체 연결)
    assert upsert_mock.call_count >= 1, (
        f"\n사이클 93 G-CC4 위반 — scanner upsert chain 호출 누락:\n"
        f"  실제 호출 {upsert_mock.call_count}회 (최소 1회 의무)\n"
        f"  → chain 자체가 부재 (Red 상태 = 시정 전, G-CC1 PASS 후 본 테스트도 PASS)"
    )

    # 의무 3: ERROR 로그 발화 (운영 가시화)
    error_records = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR
        and "[universe_eager_refresh]" in r.message
    ]
    assert error_records, (
        f"\n사이클 93 G-CC4 위반 — `[universe_eager_refresh]` ERROR 로그 누락:\n\n"
        f"  caplog records (level ≥ ERROR): {len(error_records)}건 (의무 ≥ 1)\n"
        f"  전체 caplog records: {len(caplog.records)}건\n\n"
        f"  결함 원인: `logger.exception(...)` 호출 누락\n"
        f"  → 운영 가시화 손실 (silent 결함 답습)\n\n"
        f"  시정 (Green): except 블록 안에 `logger.exception('[universe_eager_refresh] "
        f"stock_master upsert 실패 graceful')` 추가"
    )
