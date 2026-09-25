"""cycle366 (P6) — 리포트·지표 정확도 관측: by_ticker_pnl 절단 표시·확장 blind 초·휴장일 판정.

근거: `_workspace/reports/2026-09-25_daily_and_advice_review.md` §5 P6(사용자 결정
2026-09-25: 「휴장일 표시까지 포함해서 진행」). 관측 전용 — 매매 무변경, 8영역·
`scheduler.py` 무접촉.

이 파일이 지키는 것:
1. `_by_ticker_pnl_truncation`(log_metrics_collector) — `_aggregate_trades` 의
   `by_ticker_pnl` 상위 5개 절단 여부·전체 티커 수를 별도로 관측한다(그 함수의 반환
   dict 는 cycle351 골든 byte 계약 대상이라 손대지 않는다).
2. `_aggregate_extended_blind` — `[tick_blind_boot]` 로그의 애프터마켓(16:00~20:00)·
   NXT 프리마켓(08:00~08:50) 겹침 초를 `tick_blind`(기존 09:00~15:30 KRX 메인, cycle234)
   와 별도로 집계한다.
3. `uptime_monitor.after_market_blind_overlap_secs`/`pre_market_blind_overlap_secs` —
   새 시간창 겹침 계산 + 리팩토링(`_weekday_window_overlap_secs` 공용 코어 추출)이 기존
   `market_blind_overlap_secs` 의 값을 한 비트도 바꾸지 않았다.
4. `collect_daily_log_metrics` 가 맨 끝에 `"report_accuracy"` 키를 얹는다 —
   `trading_day`(`trading_calendar.is_open_day` 재사용, `bool | None`) ·
   `market_closed`(`trading_day is False`) · truncation 2필드 · 확장 blind 2필드.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

import src.engine.log_metrics_collector as collector
from src.engine import uptime_monitor as um

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _dt(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=KST)


# ===========================================================================
# 1. `_by_ticker_pnl_truncation`
# ===========================================================================
class TestByTickerPnlTruncation:
    def test_no_trades(self):
        assert collector._by_ticker_pnl_truncation([]) == {
            "by_ticker_pnl_total_tickers": 0,
            "by_ticker_pnl_truncated": False,
        }

    def test_at_or_under_top_n_not_truncated(self):
        trades = [{"trade_type": "SELL", "ticker": f"{i:06d}"} for i in range(5)]
        assert collector._by_ticker_pnl_truncation(trades) == {
            "by_ticker_pnl_total_tickers": 5,
            "by_ticker_pnl_truncated": False,
        }

    def test_over_top_n_truncated(self):
        trades = [{"trade_type": "SELL", "ticker": f"{i:06d}"} for i in range(7)]
        assert collector._by_ticker_pnl_truncation(trades) == {
            "by_ticker_pnl_total_tickers": 7,
            "by_ticker_pnl_truncated": True,
        }

    def test_buy_rows_and_missing_ticker_excluded(self):
        trades = [
            {"trade_type": "BUY", "ticker": "000001"},
            {"trade_type": "SELL", "ticker": "000002"},
            {"trade_type": "SELL", "ticker": ""},
            {"trade_type": "SELL"},
        ]
        out = collector._by_ticker_pnl_truncation(trades)
        assert out == {"by_ticker_pnl_total_tickers": 1, "by_ticker_pnl_truncated": False}

    def test_shares_cutoff_with_aggregate_trades(self):
        """상위 5개로 잘리는 `_aggregate_trades` 와 총 건수·잘림 여부가 일치해야 한다."""
        trades = [
            {
                "trade_type": "SELL", "ticker": f"{i:06d}", "status": "COMPLETED",
                "profit_loss": (i + 1) * 1000,
                "timestamp": "2026-10-19T10:00:00+09:00",
            }
            for i in range(6)
        ]
        agg = collector._aggregate_trades(trades)
        assert len(agg["by_ticker_pnl"]) == 5
        trunc = collector._by_ticker_pnl_truncation(trades)
        assert trunc == {"by_ticker_pnl_total_tickers": 6, "by_ticker_pnl_truncated": True}


# ===========================================================================
# 2. `_aggregate_extended_blind`
# ===========================================================================
class TestAggregateExtendedBlind:
    def test_new_fields_summed(self):
        logs = [
            {"message": (
                "[tick_blind_boot] downtime_secs=125 market_blind_secs=60 "
                "after_market_blind_secs=30 pre_market_blind_secs=10 last_alive=..."
            )},
            {"message": "무관 로그"},
            {"message": (
                "[tick_blind_boot] downtime_secs=300 market_blind_secs=0 "
                "after_market_blind_secs=15 pre_market_blind_secs=0 last_alive=..."
            )},
        ]
        assert collector._aggregate_extended_blind(logs) == {
            "after_market_blind_secs_total": 45,
            "pre_market_blind_secs_total": 10,
        }

    def test_old_format_without_new_fields_is_zero(self):
        """신규 필드가 없는(구버전 프로세스) 로그는 매치 실패 → 0 (하위호환)."""
        logs = [{"message": "[tick_blind_boot] downtime_secs=125 market_blind_secs=60 last_alive=..."}]
        assert collector._aggregate_extended_blind(logs) == {
            "after_market_blind_secs_total": 0,
            "pre_market_blind_secs_total": 0,
        }

    def test_first_boot_line_is_zero(self):
        assert collector._aggregate_extended_blind(
            [{"message": "[tick_blind_boot] first_boot"}]
        ) == {"after_market_blind_secs_total": 0, "pre_market_blind_secs_total": 0}

    def test_empty(self):
        assert collector._aggregate_extended_blind([]) == {
            "after_market_blind_secs_total": 0,
            "pre_market_blind_secs_total": 0,
        }

    def test_does_not_change_existing_tick_blind_aggregate(self):
        """`_aggregate_tick_blind`(cycle234) 의 반환 dict 는 여전히 3키뿐이다."""
        logs = [{"message": (
            "[tick_blind_boot] downtime_secs=125 market_blind_secs=60 "
            "after_market_blind_secs=30 pre_market_blind_secs=10 last_alive=..."
        )}]
        out = collector._aggregate_tick_blind(logs)
        assert set(out) == {"boot_count", "downtime_secs_total", "market_blind_secs_total"}
        assert out == {"boot_count": 1, "downtime_secs_total": 125, "market_blind_secs_total": 60}


# ===========================================================================
# 3. `uptime_monitor` 확장 blind 창 + 기존 함수 행위 보존
# ===========================================================================
class TestExtendedBlindWindows:
    def test_after_market_fully_inside(self):
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 31, 17, 0), _dt(2026, 8, 31, 18, 0)) == 3600

    def test_after_market_outside_krx_hours_is_zero(self):
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 31, 9, 30), _dt(2026, 8, 31, 10, 30)) == 0

    def test_after_market_weekend_zero(self):
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 29, 17, 0), _dt(2026, 8, 29, 18, 0)) == 0

    def test_after_market_boundary_partial(self):
        # 15:50 -> 16:10 = 16:00~16:10 만 겹침 = 600s
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 31, 15, 50), _dt(2026, 8, 31, 16, 10)) == 600

    def test_pre_market_fully_inside(self):
        assert um.pre_market_blind_overlap_secs(
            _dt(2026, 8, 31, 8, 10), _dt(2026, 8, 31, 8, 40)) == 1800

    def test_pre_market_boundary_partial(self):
        # 07:50 -> 08:10 = 08:00~08:10 만 겹침 = 600s
        assert um.pre_market_blind_overlap_secs(
            _dt(2026, 8, 31, 7, 50), _dt(2026, 8, 31, 8, 10)) == 600

    def test_pre_market_weekend_zero(self):
        assert um.pre_market_blind_overlap_secs(
            _dt(2026, 8, 29, 8, 10), _dt(2026, 8, 29, 8, 40)) == 0

    def test_multiday_after_market(self):
        # 금(08-28) 17:00 -> 월(08-31) 08:30 — 금 17:00~20:00(3h=10800) 만 겹치고
        # 월 창(16:00~20:00)은 종료 시각(08:30)이 그 전이라 닿지 않는다.
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 28, 17, 0), _dt(2026, 8, 31, 8, 30)) == 10800

    def test_inverted_range_zero(self):
        assert um.after_market_blind_overlap_secs(
            _dt(2026, 8, 31, 18, 0), _dt(2026, 8, 31, 17, 0)) == 0
        assert um.pre_market_blind_overlap_secs(
            _dt(2026, 8, 31, 9, 0), _dt(2026, 8, 31, 8, 0)) == 0

    def test_existing_market_overlap_unchanged_after_refactor(self):
        """공용 코어 추출(`_weekday_window_overlap_secs`)이 기존 함수 값을 바꾸지 않았다."""
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 9, 30), _dt(2026, 8, 31, 10, 30)) == 3600
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 29, 10, 0), _dt(2026, 8, 30, 14, 0)) == 0
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 10, 0), _dt(2026, 8, 31, 9, 0)) == 0


class TestBootReportLineHasExtendedFields:
    @pytest.fixture(autouse=True)
    def _reset(self):
        um.reset_state_for_test()
        yield
        um.reset_state_for_test()

    @pytest.mark.asyncio
    async def test_line_includes_after_and_pre_market_fields(self, monkeypatch, caplog):
        from src.db import system_config as sc

        now = datetime.now(KST)
        last = (now - timedelta(seconds=125)).isoformat()

        async def _get(label):
            return last

        async def _set(label, iso):
            pass

        monkeypatch.setattr(sc, "get_task_last_success", _get)
        monkeypatch.setattr(sc, "set_task_last_success", _set)
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            await um.report_boot_blind_gap()
        hits = [r for r in caplog.records if "[tick_blind_boot]" in r.message]
        assert len(hits) == 1
        assert "after_market_blind_secs=" in hits[0].message
        assert "pre_market_blind_secs=" in hits[0].message
        # 기존 필드도 여전히 남아 있다 (cycle234 회귀 보존).
        assert "downtime_secs=" in hits[0].message
        assert "market_blind_secs=" in hits[0].message


# ===========================================================================
# 4. `collect_daily_log_metrics` 배선 — `report_accuracy` 신규 키
# ===========================================================================
def _isolate(monkeypatch, *, trades=None, logs=None, trading_day_result=None):
    """cycle259 `_isolate_collector` 와 같은 패턴의 경량 대역 — DB/KIS/레지스트리 무접촉."""
    trades = trades if trades is not None else []
    logs = logs if logs is not None else []

    async def _fetch(start, end, limit=None):
        return list(logs)

    async def _high(start, end, *a, **k):
        return []

    async def _count(start, end):
        return {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    async def _trades(d1, d2):
        return list(trades)

    async def _funnel():
        return {}

    async def _stages(target_date):
        return {}

    async def _snapshot(now=None):
        return None

    async def _no_pyramid_shadow(target_date):
        return None

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fetch)
    monkeypatch.setattr(collector, "_fetch_high_severity_logs", _high)
    monkeypatch.setattr(collector, "_count_logs_by_level", _count)
    monkeypatch.setattr(collector, "get_trades_in_range", _trades)
    monkeypatch.setattr(collector, "get_request_metrics", lambda: {"total": 0})
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _funnel)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages)
    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _snapshot)
    monkeypatch.setattr(collector, "_collect_pyramid_shadow", _no_pyramid_shadow, raising=False)

    import src.engine.trading_calendar as tc

    async def _is_open_day(_d):
        return trading_day_result

    monkeypatch.setattr(tc, "is_open_day", _is_open_day)


@freeze_time("2026-09-04 05:00:00")  # KST 14:00, 금요일 — 평일
class TestReportAccuracyWiring:
    async def test_key_is_last_and_present(self, monkeypatch):
        _isolate(monkeypatch)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        assert list(metrics)[-1] == "report_accuracy"
        assert set(metrics["report_accuracy"]) == {
            "trading_day", "market_closed",
            "by_ticker_pnl_total_tickers", "by_ticker_pnl_truncated",
            "after_market_blind_secs_total", "pre_market_blind_secs_total",
        }

    async def test_trading_day_true_market_open(self, monkeypatch):
        _isolate(monkeypatch, trading_day_result=True)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["trading_day"] is True
        assert ra["market_closed"] is False

    async def test_trading_day_false_market_closed(self, monkeypatch):
        _isolate(monkeypatch, trading_day_result=False)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["trading_day"] is False
        assert ra["market_closed"] is True

    async def test_trading_day_unknown_is_not_closed(self, monkeypatch):
        """판정 불가(`None`)는 「휴장」이 아니다 — 「모름」으로 따로 남는다."""
        _isolate(monkeypatch, trading_day_result=None)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["trading_day"] is None
        assert ra["market_closed"] is False

    async def test_trading_day_lookup_exception_falls_back_to_unknown(self, monkeypatch):
        _isolate(monkeypatch)
        import src.engine.trading_calendar as tc

        async def _boom(_d):
            raise RuntimeError("KIS CTCA0903R down (test)")

        monkeypatch.setattr(tc, "is_open_day", _boom)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["trading_day"] is None
        assert ra["market_closed"] is False

    async def test_truncation_fields_propagate_from_trades(self, monkeypatch):
        trades = [
            {
                "trade_type": "SELL", "ticker": f"{i:06d}", "status": "COMPLETED",
                "profit_loss": (i + 1) * 1000,
                "timestamp": "2026-09-04T10:00:00+09:00",
            }
            for i in range(6)
        ]
        _isolate(monkeypatch, trades=trades)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["by_ticker_pnl_total_tickers"] == 6
        assert ra["by_ticker_pnl_truncated"] is True
        assert len(metrics["trades"]["by_ticker_pnl"]) == 5  # 기존 절단은 그대로

    async def test_extended_blind_fields_propagate_from_logs(self, monkeypatch):
        logs = [{"message": (
            "[tick_blind_boot] downtime_secs=125 market_blind_secs=0 "
            "after_market_blind_secs=30 pre_market_blind_secs=5 last_alive=..."
        )}]
        _isolate(monkeypatch, logs=logs)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        ra = metrics["report_accuracy"]
        assert ra["after_market_blind_secs_total"] == 30
        assert ra["pre_market_blind_secs_total"] == 5
        # 기존 tick_blind 키는 무변경.
        assert metrics["tick_blind"] == {
            "boot_count": 1, "downtime_secs_total": 125, "market_blind_secs_total": 0,
        }

    async def test_never_raises_and_other_keys_unaffected(self, monkeypatch):
        """휴장일 판정 실패가 나머지 10키(트레이드·로그 등)를 흔들지 않는다."""
        _isolate(monkeypatch)
        import src.engine.trading_calendar as tc

        async def _boom(_d):
            raise RuntimeError("boom")

        monkeypatch.setattr(tc, "is_open_day", _boom)
        metrics = await collector.collect_daily_log_metrics(date(2026, 9, 4))
        assert metrics["api_metrics"] == {"total": 0}
        assert metrics["trades"]["trades_total"] == 0


# ===========================================================================
# 5. 21:30 LLM 프롬프트 소비처 동기 — 휴장일 문구 안내
# ===========================================================================
class TestSystemPromptHolidayGuidance:
    def test_system_prompt_mentions_report_accuracy_market_closed(self):
        import src.engine.log_analysis_engine as lae

        assert "report_accuracy" in lae.SYSTEM_PROMPT
        assert "market_closed" in lae.SYSTEM_PROMPT
