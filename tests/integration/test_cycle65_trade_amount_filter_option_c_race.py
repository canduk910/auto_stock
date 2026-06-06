"""사이클 65 (2026-06-06) Red — I 카테고리: integration 자문 신규 (2 케이스, Q6 자문).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 11)
> **자문 응답**: Q2 옵션 C 통합 폴백 정합성 + Q6-1 09:00 race graceful 영속

요구 행위 (Red 단계 모두 AssertionError / AttributeError 정답):

- I-1 [MEDIUM]: `ticker_market_info` 에 `trade_amount_raw` 키 보강 정합성
  (scanner.py:453 변경: 기존 `trade_amount` 보존 + 신규 `trade_amount_raw` 추가)
- I-2 [LOW]: Q6-1 09:00 race 영속 검증 — 양쪽 0 → graceful 통과 + emit 0

위험 등급:
- I-1 MEDIUM (옵션 C 통합 폴백 정합성)
- I-2 LOW (Q6-1 HIGH 영속 — 시스템 매매 무용 위험 차단)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset."""
    from src.engine import scanner

    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
        scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_count_today"):
        for k in list(scanner._trade_amount_filter_scanner_skip_count_today):
            scanner._trade_amount_filter_scanner_skip_count_today[k] = 0
    yield


# ---------------------------------------------------------------------------
# I-1: 옵션 C 통합 폴백 정합성 — ticker_market_info["trade_amount_raw"] 키 보강
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I1_scanner_populates_trade_amount_raw_key(monkeypatch):
    """I-1 (MEDIUM 자문 신규): `scanner.scan_stocks` 가 `ticker_market_info` 에
    `trade_amount_raw` 키 보강 검증.

    scanner.py L453 변경 정합성:
    - 기존 키 `trade_amount` (억 단위 반올림) 보존 — UI/API 응답 호환 영속
    - 신규 키 `trade_amount_raw` (원 단위 정밀값) 추가 — Q2 옵션 C 1순위

    KIS 호출 0건 추가 — scanner 가 이미 fetch_rising_stocks 호출 + acml_tr_pbmn 보강 중.
    """
    from src.engine import scanner

    # mock fetch_rising_stocks → 후보 1건 (acml_tr_pbmn=300억, 시총=5,000억)
    fake_raw = [{
        "stck_shrn_iscd": "A001",
        "hts_kor_isnm": "테스트종목",
        "prdy_ctrt": "20.0",
        "stck_prpr": "5000",
        "lstn_stcn": "100000000",  # 1억주
        "acml_tr_pbmn": "30000000000",  # 300억 (원 단위)
    }]

    # ticker_market_info 사전 clear (테스트 격리)
    scanner.ticker_market_info.clear()

    monkeypatch.setattr(
        "src.engine.scanner.fetch_rising_stocks",
        AsyncMock(return_value=fake_raw),
    )

    await scanner.scan_stocks()

    info = scanner.ticker_market_info.get("A001")
    assert info is not None, (
        "scan 후 ticker_market_info[A001] 누락 — fetch_rising_stocks → 후보 1건 보강 결함"
    )

    # 신규 키 trade_amount_raw — 원 단위 정밀값
    assert "trade_amount_raw" in info, (
        f"사이클 65 Q2 옵션 C 위반 — `trade_amount_raw` 신규 키 누락 (실제 키: {list(info.keys())})"
    )
    assert info["trade_amount_raw"] == 30_000_000_000, (
        f"trade_amount_raw 정밀값 결함 — 300억 (30_000_000_000) 의무 (실제 {info['trade_amount_raw']})"
    )

    # 기존 키 trade_amount 보존 — 억 단위 반올림 (UI/API 호환 영속)
    assert "trade_amount" in info, "기존 키 `trade_amount` 폐기 — UI/API 호환 결함"
    assert info["trade_amount"] == 300, (
        f"기존 키 `trade_amount` 호환 결함 — 300 (억) 의무 (실제 {info['trade_amount']})"
    )


# ---------------------------------------------------------------------------
# I-2: Q6-1 09:00 race 영속 검증 — 양쪽 0 → graceful 통과 + emit 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I2_q6_1_09am_race_graceful_no_emit(monkeypatch):
    """I-2 (LOW 자문 신규, Q6-1 HIGH 영속): 09:00 직후 양쪽 데이터 0 → graceful 통과 + emit 0.

    시나리오:
    - scanner 1순위 `trade_amount_raw=0` (09:00 누적 미반영)
    - stock_master 2순위 `acml_tr_pbmn=0` (장중 reset 가정)
    - `_get_acml_tr_pbmn` 0 반환 → `_apply_trade_amount_filter` graceful 통과

    검증:
    - survivors = 후보 그대로 (차단 X)
    - `[trade_amount_filter_scanner_skip]` emit 0 (filter pass — skip emit 미발화)

    Q6-1 HIGH 영속 — 09:00 race 잘못 처리 시 09:00~09:30 후보 전체 차단 = 시스템 매매 무용 위험.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    write_log_mock = AsyncMock()

    async def _stub_get_taf():
        return TradeAmountFilter(min_amount=1_000_000_000)  # 10억 활성
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get_taf,
        raising=False,
    )

    # scanner 1순위 — trade_amount_raw=0 (09:00 직후 누적 미반영)
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 0}},
        raising=False,
    )

    # stock_master 2순위 — acml_tr_pbmn=0 (장중 reset 가정)
    basics = MagicMock()
    basics.raw = {"acml_tr_pbmn": "0"}

    with patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", write_log_mock):
        # Red: `_apply_trade_amount_filter` 미존재 → AttributeError 정답
        survivors = await scanner._apply_trade_amount_filter(
            ["A001"], protected_tickers=set(),
        )

    # 1) graceful 통과 — 차단 X
    assert survivors == ["A001"], (
        f"Q6-1 09:00 race graceful 통과 위반 — 양쪽 0 시 graceful 통과 의무 (실제 {survivors})"
    )

    # 2) skip emit 0 — filter pass 시 [trade_amount_filter_scanner_skip] 미발화
    skip_calls = [
        c for c in write_log_mock.call_args_list
        if "[trade_amount_filter_scanner_skip]" in str(c)
    ]
    assert len(skip_calls) == 0, (
        f"Q6-1 09:00 race emit 0 위반 — graceful 통과 시 skip emit 미발화 의무 "
        f"(실제 {len(skip_calls)}건)"
    )
