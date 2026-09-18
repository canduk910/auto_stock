"""R1 (2026-05-04): FRED OAS partial_failure 핫픽스 단위 테스트.

원본: tests/unit/test_macro_fetcher_fred_fallback.py — `from stock import macro_fetcher`를
`from macro_lite import fetcher as macro_fetcher`로 교체 (요건서 REQ-PKG-01/03).
patch 대상(`requests.get`/`time.sleep`/`macro_fetcher` 객체 속성)은 원본 그대로 유지.
"""

from unittest.mock import patch, MagicMock

import pytest

from macro_lite import fetcher as macro_fetcher


def _mk_resp(status=200, ctype="text/csv", text="observation_date,BAMLH0A0HYM2\n2024-01-01,3.45\n"):
    r = MagicMock()
    r.status_code = status
    r.headers = {"Content-Type": ctype}
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_uses_browser_ua():
    """브라우저 UA + _FRED_TIMEOUT(기본 25s, 환경변수로 조정) 사용."""
    captured = {}

    def fake_get(url, timeout=None, headers=None):
        captured["timeout"] = timeout
        captured["headers"] = headers
        return _mk_resp()

    with patch("requests.get", side_effect=fake_get):
        macro_fetcher._http_get_fred_csv("https://example.com/x.csv")

    assert captured["timeout"] == macro_fetcher._FRED_TIMEOUT
    ua = captured["headers"]["User-Agent"]
    assert "Mozilla" in ua and "Chrome" in ua


def test_content_type_html_treated_as_failure():
    """text/html 응답은 실패 처리하고 None 반환 (재시도 후에도)."""
    with patch("requests.get", return_value=_mk_resp(ctype="text/html", text="<html>blocked</html>")):
        with patch("time.sleep"):  # retry sleep skip
            result = macro_fetcher._http_get_fred_csv("https://example.com/x.csv")
    assert result is None


def test_retry_once_on_failure():
    """첫 호출 실패 → 2초 sleep 후 1회 재시도. 두 번째 성공이면 반환."""
    call_count = {"n": 0}

    def fake_get(url, timeout=None, headers=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("network down")
        return _mk_resp(text="observation_date,V\n2024-01-01,1.0\n")

    with patch("requests.get", side_effect=fake_get):
        with patch("time.sleep") as mock_sleep:
            result = macro_fetcher._http_get_fred_csv("https://example.com/x.csv")

    assert call_count["n"] == 2
    assert result is not None
    mock_sleep.assert_called_once_with(2)


def test_stale_fallback_when_fresh_fails():
    """신선 fetch 실패 + stale 캐시 있으면 stale 반환 + _stale_used=True."""
    stale_data = {
        "oas_current": 4.5,
        "oas_history_5y": [{"date": "2024-01-01", "oas": 4.5}],
        "oas_stats": {"mean": 5.0},
        "oas_percentile": 50.0,
        "sentiment": "normal",
    }

    def fake_cached(key):
        if "stale" in key:
            return stale_data
        return None

    with patch.object(macro_fetcher, "_http_get_fred_csv", return_value=None):
        with patch.object(macro_fetcher, "get_cached", side_effect=fake_cached):
            result = macro_fetcher._fetch_fred_oas()

    assert result.get("_stale_used") is True
    assert result.get("oas_current") == 4.5


def test_no_stale_no_fresh_returns_empty():
    """신선 + stale 둘 다 없으면 빈 dict."""
    with patch.object(macro_fetcher, "_http_get_fred_csv", return_value=None):
        with patch.object(macro_fetcher, "get_cached", return_value=None):
            result = macro_fetcher._fetch_fred_oas()
    assert result == {}


def test_parse_fred_csv_skips_invalid_rows():
    """CSV 파서가 결측치('.')와 형식 오류 행을 안전하게 건너뛴다."""
    text = (
        "observation_date,BAMLH0A0HYM2\n"
        "2024-01-01,3.45\n"
        "2024-01-02,.\n"           # 결측
        "2024-01-03,not_a_number\n"  # 파싱 실패
        "2024-01-04,4.10\n"
    )
    rows = macro_fetcher._parse_fred_csv(text, "oas")
    assert len(rows) == 2
    assert rows[0] == {"date": "2024-01-01", "oas": 3.45}
    assert rows[1] == {"date": "2024-01-04", "oas": 4.10}


# ── MACRO_LITE_FRED_TIMEOUT 환경변수 (I/O 정책, 투자 로직 무관) ────────────

def test_env_timeout_override_and_invalid_values():
    from macro_lite.fetcher import _env_timeout
    import os
    key = "MACRO_LITE_FRED_TIMEOUT_TEST"
    try:
        os.environ[key] = "8"
        assert _env_timeout(key, 25) == 8.0
        for bad in ("", "0", "-3", "abc", " "):
            os.environ[key] = bad
            assert _env_timeout(key, 25) == 25, bad
    finally:
        os.environ.pop(key, None)
    assert _env_timeout("MACRO_LITE_FRED_TIMEOUT_UNSET_XYZ", 25) == 25
