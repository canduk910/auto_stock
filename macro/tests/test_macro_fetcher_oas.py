"""HY OAS 하워드 막스 시계추 — 백분위 5단계 + 전 기간 baseline + 안전장치.

원본: tests/unit/test_macro_fetcher_oas.py — `from stock import macro_fetcher`를
`from macro_lite import fetcher as macro_fetcher`로 교체 (요건서 REQ-PKG-01/03).
본문은 원본 그대로 유지 (patch 대상은 macro_fetcher 모듈 객체 직접 참조라 무변경).

R1 (P0): _classify_oas_sentiment + _fetch_fred_oas 통계 강화 검증.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from macro_lite import fetcher as macro_fetcher


# ── _classify_oas_sentiment ───────────────────────────────────

class TestClassifyOasSentiment:
    def _stats_from(self, history: list[float]) -> dict:
        """히스토리에서 stats dict 생성 (테스트 헬퍼)."""
        if not history:
            return {}
        sorted_v = sorted(history)
        n = len(sorted_v)

        def _pct(p):
            idx = int(round((p / 100) * (n - 1)))
            return round(sorted_v[idx], 2)

        mean = sum(history) / n
        return {
            "mean": round(mean, 2),
            "median": _pct(50),
            "std": round((sum((v - mean) ** 2 for v in history) / n) ** 0.5, 2),
            "p10": _pct(10),
            "p25": _pct(25),
            "p50": _pct(50),
            "p75": _pct(75),
            "p90": _pct(90),
            "p95": _pct(95),
            "max": round(max(history), 2),
            "max_date": "1900-01-01",
        }

    def test_extreme_greed_below_p10(self):
        # 100 데이터, p10=2.0이라면 1.5는 percentile<10
        history = [float(i) / 10.0 for i in range(10, 110)]  # 1.0 ~ 10.9
        stats = self._stats_from(history)
        result = macro_fetcher._classify_oas_sentiment(1.5, stats)
        assert result["sentiment"] == "extreme_greed"
        assert result["percentile"] is not None
        assert result["percentile"] < 10

    def test_greed_p10_to_p30(self):
        history = [float(i) / 10.0 for i in range(10, 110)]
        stats = self._stats_from(history)
        # p25=3.4 정도 → 2.5는 percentile≈15
        result = macro_fetcher._classify_oas_sentiment(2.5, stats)
        assert result["sentiment"] == "greed"
        assert 10 <= result["percentile"] < 30

    def test_normal_p30_to_p70(self):
        history = [float(i) / 10.0 for i in range(10, 110)]
        stats = self._stats_from(history)
        # 중앙값 근처 → 5.5는 percentile≈45
        result = macro_fetcher._classify_oas_sentiment(5.5, stats)
        assert result["sentiment"] == "normal"

    def test_fear_p70_to_p90(self):
        history = [float(i) / 10.0 for i in range(10, 110)]
        stats = self._stats_from(history)
        # p70=7.7~7.8 / p90=9.9 → 8.5는 그 사이
        result = macro_fetcher._classify_oas_sentiment(8.5, stats)
        assert result["sentiment"] == "fear"

    def test_extreme_fear_above_p90(self):
        history = [float(i) / 10.0 for i in range(10, 110)]
        stats = self._stats_from(history)
        # 9.95는 percentile>90
        result = macro_fetcher._classify_oas_sentiment(9.95, stats)
        assert result["sentiment"] == "extreme_fear"

    def test_absolute_safeguard_above_10(self):
        """OAS > 10% 절대 안전장치: 백분위 무관 extreme_fear."""
        # 매우 높은 baseline에서도 10% 초과는 강제 extreme_fear
        history = [12.0, 13.0, 14.0, 15.0, 20.0]  # 모두 10 이상
        stats = macro_fetcher._compute_oas_stats(history) if hasattr(
            macro_fetcher, "_compute_oas_stats"
        ) else self._stats_from(history)
        result = macro_fetcher._classify_oas_sentiment(10.5, stats)
        assert result["sentiment"] == "extreme_fear"

    def test_empty_stats_returns_normal(self):
        result = macro_fetcher._classify_oas_sentiment(5.0, {})
        assert result["sentiment"] == "normal"
        assert result["percentile"] is None


# ── _fetch_fred_oas 빈 응답 가드 ──────────────────────────────

class TestFetchFredOasGuards:
    def test_empty_response_returns_empty_dict(self, monkeypatch):
        """FRED 빈 응답 시 {} 반환, ZeroDivisionError 발생 금지."""
        class FakeResp:
            text = "DATE,BAMLH0A0HYM2\n"  # header만, rows 없음

            def raise_for_status(self):
                pass

        # _fetch_fred_oas 내부에서 `import requests as _requests` 후 사용 → 전역 requests를 patch
        import requests as _req_mod

        def fake_get(*args, **kwargs):
            return FakeResp()

        monkeypatch.setattr(_req_mod, "get", fake_get)
        try:
            result = macro_fetcher._fetch_fred_oas()
            assert result == {} or result.get("oas_current") is None
        except Exception as e:
            pytest.fail(f"_fetch_fred_oas raised on empty: {e}")

    def test_zerodivision_guard_on_zero_history(self):
        """all_oas가 빈 리스트일 때 ZeroDivisionError 발생 금지."""
        # _classify_oas_sentiment는 stats가 비어있어도 안전해야 함
        result = macro_fetcher._classify_oas_sentiment(5.0, {})
        # zscore는 None이거나 안전한 값
        assert result.get("zscore") is None or isinstance(result["zscore"], (int, float))


# ── _compute_oas_stats (전 기간 통계) ─────────────────────────

class TestOasStats:
    def test_basic_stats(self):
        """알려진 시계열에서 mean/median/percentile 정확."""
        if not hasattr(macro_fetcher, "_compute_oas_stats"):
            pytest.skip("_compute_oas_stats not implemented yet")
        rows = [{"date": f"2020-01-{d:02d}", "oas": float(d)} for d in range(1, 11)]  # 1~10
        stats = macro_fetcher._compute_oas_stats(rows)
        assert abs(stats["mean"] - 5.5) < 0.01
        assert stats["max"] == 10.0
        # p50 ≈ 5 또는 6
        assert 5.0 <= stats["p50"] <= 6.0

    def test_empty_rows_returns_empty(self):
        if not hasattr(macro_fetcher, "_compute_oas_stats"):
            pytest.skip("_compute_oas_stats not implemented yet")
        assert macro_fetcher._compute_oas_stats([]) == {}
