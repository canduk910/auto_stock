"""F-6 (2026-07-04): VIX 스팟 스칼라 단일 진입점 get_vix_spot 회귀 가드.

원본: tests/unit/test_macro_vix_spot.py — `from stock import macro_fetcher as mf`를
`from macro_lite import fetcher as mf`로 교체 (요건서 REQ-PKG-01/03). 본문은
원본 그대로 유지 (patch 대상은 mf 모듈 객체 직접 참조라 무변경).

macro-sentinel CAUTION 제약 검증:
- 공유 캐시 TTL 10분(0.17h) — 상향 금지
- 실패 시 None + 캐시 미저장 (폴백값 오염 방지)
- fetch_vix / calc_fear_greed / yf_client.fetch_macro_indicators 위임 소비
- macro_factor_model의 시계열(^VIX logret)은 통합 대상 아님 (현행 유지)
"""
from unittest.mock import MagicMock, patch

from macro_lite import fetcher as mf


class _FakeFastInfo:
    def __init__(self, last_price=None, previous_close=None):
        self.last_price = last_price
        self.previous_close = previous_close


def _fake_vix_ticker(last=32.5, prev=30.0):
    t = MagicMock()
    t.fast_info = _FakeFastInfo(last_price=last, previous_close=prev)
    return t


class TestGetVixSpot:
    def test_success_caches_with_10min_ttl(self):
        """성공 시 값 반환 + TTL 0.17h(10분)로 캐시 — 상향 금지 (macro-sentinel)."""
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "set_cached") as mock_set, \
             patch("yfinance.Ticker", return_value=_fake_vix_ticker(32.5)):
            assert mf.get_vix_spot() == 32.5
        mock_set.assert_called_once()
        args, kwargs = mock_set.call_args
        assert args[0] == "macro:vix_spot"
        assert args[1] == 32.5
        assert kwargs.get("ttl_hours") == 0.17

    def test_cache_hit_skips_yfinance(self):
        with patch.object(mf, "get_cached", return_value=28.1), \
             patch("yfinance.Ticker", side_effect=AssertionError("must not call")):
            assert mf.get_vix_spot() == 28.1

    def test_failure_returns_none_without_caching(self):
        """조회 실패 → None. 캐시 미저장 (폴백값이 실측치로 저장되면 오버라이드 오염)."""
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "set_cached") as mock_set, \
             patch("yfinance.Ticker", side_effect=RuntimeError("yf down")):
            assert mf.get_vix_spot() is None
        mock_set.assert_not_called()

    def test_no_price_returns_none_without_caching(self):
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "set_cached") as mock_set, \
             patch("yfinance.Ticker", return_value=_fake_vix_ticker(None, None)):
            assert mf.get_vix_spot() is None
        mock_set.assert_not_called()


class TestConsumersDelegate:
    def test_fetch_vix_delegates_spot(self):
        """fetch_vix의 value는 get_vix_spot 위임 (prev/스파크라인만 자체 조회)."""
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "set_cached"), \
             patch.object(mf, "get_vix_spot", return_value=36.0) as mock_spot, \
             patch("yfinance.Ticker") as mock_ticker:
            t = _fake_vix_ticker(36.0, 33.0)
            hist = MagicMock()
            hist.empty = True
            t.history.return_value = hist
            mock_ticker.return_value = t
            result = mf.fetch_vix()
        mock_spot.assert_called_once()
        assert result["value"] == 36.0
        assert result["level"] == "extreme"  # >= 35

    def test_fetch_vix_spot_none_returns_none(self):
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "get_vix_spot", return_value=None):
            assert mf.fetch_vix() is None

    def test_fear_greed_uses_spot_with_local_fallback(self):
        """calc_fear_greed는 get_vix_spot 위임. None이면 로컬 폴백 20 (캐시 무관)."""
        with patch.object(mf, "get_cached", return_value=None), \
             patch.object(mf, "set_cached"), \
             patch.object(mf, "get_vix_spot", return_value=None) as mock_spot, \
             patch("yfinance.Ticker") as mock_ticker:
            t = MagicMock()
            hist = MagicMock()
            hist.empty = True
            t.history.return_value = hist
            mock_ticker.return_value = t
            result = mf.calc_fear_greed()
        mock_spot.assert_called_once()
        # vix_val=20 폴백 → vix_score = (40-20)/30*100 = 67
        assert result is not None
        assert result["components"]["vix_score"] == 67
