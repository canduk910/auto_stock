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
    """브라우저 UA + 25s timeout 사용."""
    captured = {}

    def fake_get(url, timeout=None, headers=None):
        captured["timeout"] = timeout
        captured["headers"] = headers
        return _mk_resp()

    with patch("requests.get", side_effect=fake_get):
        macro_fetcher._http_get_fred_csv("https://example.com/x.csv")

    # 값 리터럴이 아니라 상수와 대조한다 — 타임아웃은 `MACRO_LITE_FRED_TIMEOUT` 로
    # 환경마다 달라지므로(운영 8초), 25 를 박아 두면 운영 설정에서 이 테스트가 붉어진다.
    assert captured["timeout"] == macro_fetcher._FRED_TIMEOUT
    ua = captured["headers"]["User-Agent"]
    assert "Mozilla" in ua and "Chrome" in ua


def test_fred_timeout_env_override(monkeypatch):
    """`MACRO_LITE_FRED_TIMEOUT` 이 CSV 타임아웃을 정한다 — 잘못된 값은 기본값으로 살린다.

    0·음수·빈 문자열·비정수가 그대로 들어가면 requests 가 즉시 끊거나 무한 대기로
    해석해, 설정 오타 하나가 하이일드 섹션을 통째로 죽인다.
    """
    monkeypatch.setenv("MACRO_LITE_FRED_TIMEOUT", "8")
    assert macro_fetcher._env_int("MACRO_LITE_FRED_TIMEOUT", 25) == 8

    for bad in ("", "0", "-3", "abc", "8.5"):
        monkeypatch.setenv("MACRO_LITE_FRED_TIMEOUT", bad)
        assert macro_fetcher._env_int("MACRO_LITE_FRED_TIMEOUT", 25) == 25, bad

    monkeypatch.delenv("MACRO_LITE_FRED_TIMEOUT", raising=False)
    assert macro_fetcher._env_int("MACRO_LITE_FRED_TIMEOUT", 25) == 25


def test_fred_csv_worst_case_fits_nginx_read_timeout():
    """CSV 최악 소요가 nginx `/api/macro/` 의 `proxy_read_timeout 60s` 안에 들어야 한다.

    하이일드·경기사이클은 시리즈 2개(HY·IG)를 각각 2회(1회 재시도) 친다 —
    `timeout x 2회 x 2시리즈` 가 60초를 넘으면 화면이 504 를 받는다(2026-09-18 실측 104초).
    """
    import os

    effective = macro_fetcher._env_int("MACRO_LITE_FRED_TIMEOUT", macro_fetcher._FRED_TIMEOUT)
    worst = effective * 2 * 2
    if os.getenv("MACRO_LITE_FRED_TIMEOUT"):
        assert worst < 60, f"CSV 최악 {worst}초 — nginx 60s 를 넘는다"
    else:
        # 환경변수 미설정(패키지 기본 25)은 원본 그대로라 여기서 강제하지 않는다.
        assert effective == macro_fetcher._FRED_TIMEOUT


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
