"""cycle386 Red — `condition.fetch_daily_chart_ranged_with_summary` + `[prev_close_overwrite]` 관측.

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8-4 ④ · §8-5 · §8-9 마커표.

## 1. `fetch_daily_chart_ranged_with_summary(ticker, start_yyyymmdd, end_yyyymmdd) -> (output1, output2)`
- 원천 = 지금 쓰는 TR 그대로(FHKST03010100, 시장 `J`, 일봉 `D`, `FID_ORG_ADJ_PRC="0"` 수정주가) — 신규 KIS API 0.
  형제 `fetch_daily_candles_ranged` 와 같은 파라미터·6자리 가드·빈 날짜 placeholder 제거. 그 형제는 **무변경**
  (반환형 `list` 그대로 — 호출자 영향 0).
- 차이는 하나 — `output1`(단건 요약, `stck_prdy_clpr` = 오늘 기준 전일종가)을 함께 돌려준다. 교차검증에 쓴다
  (`docs/kis/domestic-stock-quote.md` FHKST03010100 Response `output1`).
- 캐시·single-flight 없음(부팅 1회 호출용) — 두 번 부르면 KIS 두 번.
- KIS 호출은 `kis_get_quote` 경유(Rate Limit·재시도·메트릭 — 루트 CLAUDE.md 코딩 컨벤션).

## 2. `[prev_close_overwrite] ticker= old= new= diff_pct=` (INFO, 종목당 하루 1회, 행위 0)
09:30 `fetch_rising_stocks` 가 등락률 15% 이상 종목의 `ticker_prev_close` 를 `stck_sdpr`(기준가)로 덮을 때,
기존 값이 0 보다 크고 **다르면** 1행. 확정 뒤에는 권리락·배당락 종목 말고 0 이어야 한다(§8-9 성공 서명) —
이 설계가 실패한 종목을 운영 중에 보여 주는 두 번째 눈이다. 값 대입(`ticker_prev_close[t] = 기준가`)은 그대로다.

## HEAD 기준
1 은 함수 부재로 RED. 2 는 마커 부재로 RED(행위 보존 대조군 `test_p0_*` 은 HEAD 초록).
"""
from __future__ import annotations

import logging
import re
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


def _candle(bas_dd: str, close: int = 5800) -> dict:
    return {"stck_bsop_date": bas_dd, "stck_clpr": str(close), "stck_oprc": str(close - 100),
            "stck_hgpr": str(close + 300), "stck_lwpr": str(close - 500), "acml_vol": "100"}


# ===========================================================================
# 1. fetch_daily_chart_ranged_with_summary
# ===========================================================================
@pytest.mark.asyncio
async def test_s1_returns_output1_and_filtered_output2(monkeypatch):
    from src.api import condition

    mock = AsyncMock(return_value={
        "output1": {"stck_prdy_clpr": "5800", "stck_mxpr": "7540"},
        "output2": [_candle("20260923"), _candle("20260922", 5700), {"stck_bsop_date": "", "stck_clpr": "0"}],
    })
    monkeypatch.setattr(condition, "kis_get_quote", mock)

    out1, out2 = await condition.fetch_daily_chart_ranged_with_summary("394800", "20260913", "20260923")

    assert out1.get("stck_prdy_clpr") == "5800", "output1 을 돌려주지 않으면 교차검증을 할 수 없다"
    assert [c["stck_bsop_date"] for c in out2] == ["20260923", "20260922"], "빈 날짜 placeholder 제거"
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_s2_same_tr_and_params_as_the_existing_ranged_fetch(monkeypatch):
    from src.api import condition

    mock = AsyncMock(return_value={"output1": {}, "output2": []})
    monkeypatch.setattr(condition, "kis_get_quote", mock)

    await condition.fetch_daily_chart_ranged_with_summary("394800", "20260913", "20260923")

    args = mock.await_args.args
    assert args[0] == condition.DAILY_PRICE_URL
    assert args[1] == "FHKST03010100"
    assert args[2] == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "394800",
        "FID_INPUT_DATE_1": "20260913",
        "FID_INPUT_DATE_2": "20260923",
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }, "시장 J · 수정주가 0 — UN/NX 는 정규장 종가가 없다(§4-1 C17)"


@pytest.mark.asyncio
async def test_s3_missing_blocks_are_empty_not_errors(monkeypatch):
    from src.api import condition

    monkeypatch.setattr(condition, "kis_get_quote", AsyncMock(return_value={}))

    out1, out2 = await condition.fetch_daily_chart_ranged_with_summary("394800", "20260913", "20260923")

    assert out1 == {} and out2 == []


@pytest.mark.parametrize("bad", ["39480", "A94800", "3948000", "", None])
@pytest.mark.asyncio
async def test_s4_six_digit_guard(monkeypatch, bad):
    from src.api import condition

    mock = AsyncMock(return_value={"output1": {}, "output2": []})
    monkeypatch.setattr(condition, "kis_get_quote", mock)

    with pytest.raises(ValueError):
        await condition.fetch_daily_chart_ranged_with_summary(bad, "20260913", "20260923")
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_s5_no_cache(monkeypatch):
    from src.api import condition

    mock = AsyncMock(return_value={"output1": {}, "output2": [_candle("20260923")]})
    monkeypatch.setattr(condition, "kis_get_quote", mock)

    await condition.fetch_daily_chart_ranged_with_summary("394800", "20260913", "20260923")
    await condition.fetch_daily_chart_ranged_with_summary("394800", "20260913", "20260923")

    assert mock.await_count == 2, "캐시가 끼면 같은 아침에 두 번째 부팅이 옛 값을 본다"


@pytest.mark.asyncio
async def test_s6_existing_ranged_fetch_is_unchanged(monkeypatch):
    """형제 함수는 무변경 — 반환형 list 그대로(호출자 `fetch_daily_candles_backfill` 영향 0)."""
    from src.api import condition

    monkeypatch.setattr(condition, "kis_get_quote", AsyncMock(return_value={
        "output1": {"stck_prdy_clpr": "5800"}, "output2": [_candle("20260923")],
    }))
    rows = await condition.fetch_daily_candles_ranged("394800", "20260913", "20260923")
    assert isinstance(rows, list) and rows[0]["stck_bsop_date"] == "20260923"


# ===========================================================================
# 2. [prev_close_overwrite]
# ===========================================================================
def _overwrite_lines(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("[prev_close_overwrite] ")]


def _kv(rec) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S*)", rec.getMessage()))


async def _rising(monkeypatch, sdpr: dict[str, str]):
    from src.api import condition
    from src.config import settings

    monkeypatch.setattr(settings, "kis_env", "real")
    monkeypatch.setattr(condition, "_fetch_fluctuation_rank", AsyncMock(return_value=[
        {"stck_shrn_iscd": t, "prdy_ctrt": "22.9"} for t in sdpr
    ]))

    async def _detail(ticker):
        return {"stck_sdpr": sdpr[ticker], "lstn_stcn": "1000", "acml_tr_pbmn": "1000"}

    monkeypatch.setattr(condition, "fetch_stock_detail", _detail)
    return await condition.fetch_rising_stocks()


@pytest.mark.asyncio
async def test_p0_value_assignment_is_unchanged(monkeypatch):
    """행위 0 — 기준가 대입은 그대로(관측을 넣어도 값이 바뀌면 안 된다)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prev_close", {"394800": 5520})
    with freeze_time("2031-01-06 00:30:00"):
        await _rising(monkeypatch, {"394800": "5800"})
    assert scanner.ticker_prev_close["394800"] == 5800


@pytest.mark.asyncio
async def test_p1_logs_once_when_the_value_changes(monkeypatch, caplog):
    from src.engine import scanner

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"394800": 5520, "000100": 7000})
    with freeze_time("2031-01-07 00:30:00"):    # KST 09:30
        await _rising(monkeypatch, {"394800": "5800", "000100": "7000"})

    lines = _overwrite_lines(caplog)
    assert len(lines) == 1, f"값이 다른 종목만 1행 — {[r.getMessage() for r in lines]}"
    rec = lines[0]
    assert rec.levelno == logging.INFO
    kv = _kv(rec)
    assert kv.get("ticker") == "394800"
    assert kv.get("old") == "5520" and kv.get("new") == "5800"
    diff = float(kv["diff_pct"].rstrip("%"))
    assert diff > 0, "새 값이 크면 양수"
    assert min(abs(diff - 280 / 5520 * 100), abs(diff - 280 / 5800 * 100)) < 0.01


@pytest.mark.asyncio
async def test_p2_silent_when_there_was_no_previous_value(monkeypatch, caplog):
    from src.engine import scanner

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"394800": 0})
    with freeze_time("2031-01-08 00:30:00"):
        await _rising(monkeypatch, {"394800": "5800"})
    assert _overwrite_lines(caplog) == [], "덮을 값이 없으면(0·부재) 「덮어쓰기」 가 아니다"


@pytest.mark.asyncio
async def test_p3_once_per_ticker_per_day_and_again_next_day(monkeypatch, caplog):
    from src.engine import scanner

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"394800": 5520})
    with freeze_time("2031-01-09 00:30:00"):
        await _rising(monkeypatch, {"394800": "5800"})
        scanner.ticker_prev_close["394800"] = 5500      # 같은 날 다시 달라져도
        await _rising(monkeypatch, {"394800": "5800"})
    assert len(_overwrite_lines(caplog)) == 1, "종목당 하루 1회 — 5분 스캔마다 쌓이면 안 된다"

    caplog.clear()
    scanner.ticker_prev_close["394800"] = 5520
    with freeze_time("2031-01-10 00:30:00"):
        await _rising(monkeypatch, {"394800": "5800"})
    assert len(_overwrite_lines(caplog)) == 1, "다음 날에는 다시 1행"
