"""cycle234 R4 — 20:10 리포트 tick_blind 집계 (`_aggregate_next_day_clear` 선례)."""

from __future__ import annotations

from src.engine.log_analysis_engine import _aggregate_tick_blind


def _row(msg):
    return {"message": msg}


class TestR4Aggregate:
    def test_sums_downtime_and_market_blind(self):
        logs = [
            _row("[tick_blind_boot] downtime_secs=125 market_blind_secs=60 last_alive=..."),
            _row("무관 로그"),
            _row("[tick_blind_boot] downtime_secs=300 market_blind_secs=0 last_alive=..."),
        ]
        out = _aggregate_tick_blind(logs)
        assert out == {
            "boot_count": 2,
            "downtime_secs_total": 425,
            "market_blind_secs_total": 60,
        }

    def test_first_boot_counts_boot_only(self):
        out = _aggregate_tick_blind([_row("[tick_blind_boot] first_boot")])
        assert out["boot_count"] == 1
        assert out["downtime_secs_total"] == 0

    def test_empty(self):
        assert _aggregate_tick_blind([]) == {
            "boot_count": 0, "downtime_secs_total": 0, "market_blind_secs_total": 0,
        }

    def test_metrics_wiring_exists(self):
        """generate_daily_log_report 의 metrics 조립에 tick_blind 키 배선."""
        from pathlib import Path
        src = Path("src/engine/log_analysis_engine.py").read_text(encoding="utf-8")
        assert '"tick_blind"' in src and "_aggregate_tick_blind(" in src
