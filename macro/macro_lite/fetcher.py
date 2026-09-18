"""매크로 데이터 수집 (macro_lite 추출본).

원본: 이 프로젝트 `stock/macro_fetcher.py` 중 경기사이클/체제, 수익률곡선, 신용스프레드,
환율, 원자재 섹션에 필요한 함수·상수만 복사. 함수 본문은 원본과 동일하며 다음만 교체:
- 캐시 모듈 import: 원 프로젝트 `stock/cache.py` → 패키지 내부 `.cache`
- OAS 누적 store import: 원 프로젝트 `stock/oas_history_store.py` → `.oas_history_store`
- FRED_API_KEY: 원 프로젝트 `config.py` 상수 → `os.getenv("FRED_API_KEY", "")`
제외: INDICES/뉴스/RSS/투자자/KR 섹터/factor model.

캐시 TTL 은 원본 값 그대로 (VIX 스팟 0.17h 고정 상향 금지, 환율/원자재 0.17h,
금리차/사이클 입력/F&G/섹터 1h, 버핏 24h, credit_spread 24h, FRED stale 7일).
"""
from __future__ import annotations

import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
        return None if (math.isnan(fv) or math.isinf(fv)) else fv
    except (TypeError, ValueError):
        return None


# ── VIX ──────────────────────────────────────────────────────────────────────

def get_vix_spot() -> Optional[float]:
    """VIX 스팟 스칼라 단일 진입점 (F-6, 2026-07-04 macro-sentinel CAUTION 승인).

    공유 캐시 TTL 10분(0.17h) 고정 — VIX>35 체제 오버라이드의 '즉각 반응' 설계
    의도 유지를 위해 상향 금지 (macro-sentinel 제약).
    실패 시 None 반환 + 캐시 미저장 — 폴백값(예: fear_greed의 20)을 실측치로
    저장하면 체제 오버라이드가 오염되므로 폴백은 소비처 로컬에서만 적용할 것.

    소비처: fetch_vix(표시용 dict 조립) / calc_fear_greed(vix_score) /
    stock.yf_client.fetch_macro_indicators(vix 필드).
    시계열 용도(services/macro_factor_model의 ^VIX logret)는 용도가 달라
    통합 대상이 아님 — 현행 유지.
    """
    key = "macro:vix_spot"
    cached = get_cached(key)
    if cached is not None:
        return _safe(cached)

    try:
        import yfinance as yf
        fi = yf.Ticker("^VIX").fast_info
        value = _safe(fi.last_price) or _safe(fi.previous_close)
        if value is None:
            return None
        value = round(float(value), 2)
        set_cached(key, value, ttl_hours=0.17)
        return value
    except Exception as e:
        logger.warning("VIX 스팟 조회 실패: %s", e)
        return None


def fetch_vix() -> Optional[dict]:
    """VIX 현재값 + 변동 + 레벨 + 1개월 스파크라인.

    스팟 값은 get_vix_spot() 공유 캐시 위임 (F-6). prev/스파크라인 등
    표시용 부가 데이터만 본 함수에서 조회.
    """
    key = "macro:vix"
    cached = get_cached(key)
    if cached is not None:
        return cached or None

    try:
        value = get_vix_spot()
        if value is None:
            return None

        import yfinance as yf
        t = yf.Ticker("^VIX")
        fi = t.fast_info

        prev = _safe(fi.previous_close) or value
        change = round(value - prev, 2)

        if value < 15:
            level = "low"
        elif value < 25:
            level = "normal"
        elif value < 35:
            level = "high"
        else:
            level = "extreme"

        hist = t.history(period="1mo", interval="1d")
        sparkline = (
            [round(float(v), 2) for v in hist["Close"].dropna().tolist()]
            if not hist.empty
            else []
        )

        result = {
            "value": round(value, 2),
            "prev": round(prev, 2),
            "change": change,
            "level": level,
            "sparkline": sparkline,
        }
        set_cached(key, result, ttl_hours=0.17)
        return result
    except Exception as e:
        logger.warning("VIX 조회 실패: %s", e)
        return None


# ── 버핏 지수 ────────────────────────────────────────────────────────────────

def calc_buffett_indicator() -> Optional[dict]:
    """Buffett Indicator = US Total Market Cap / GDP (근사)."""
    key = "macro:buffett"
    cached = get_cached(key)
    if cached is not None:
        return cached or None

    try:
        import yfinance as yf

        # Wilshire 5000 으로 전체 시장 시가총액 근사
        w5 = yf.Ticker("^W5000")
        w5_fi = w5.fast_info
        w5_val = _safe(w5_fi.last_price) or _safe(w5_fi.previous_close)

        if w5_val is not None:
            market_cap_t = w5_val / 1000  # 지수 → 조 달러 근사
        else:
            # fallback: S&P 500 기반 추정
            sp = yf.Ticker("^GSPC")
            sp_val = _safe(sp.fast_info.last_price) or _safe(sp.fast_info.previous_close)
            if sp_val is None:
                return None
            market_cap_t = sp_val * 10 * 1.4 / 1000

        # US GDP 연환산 (하드코딩, 분기별 수동 업데이트)
        gdp_t = 29.0  # 2025 추정

        ratio = round(market_cap_t / gdp_t * 100, 1) if gdp_t else 0

        if ratio < 80:
            level, desc = "undervalued", "저평가"
        elif ratio < 100:
            level, desc = "fair", "적정"
        elif ratio < 130:
            level, desc = "overvalued", "고평가"
        else:
            level, desc = "significantly_overvalued", "상당히 고평가"

        result = {
            "ratio": ratio,
            "market_cap_t": round(market_cap_t, 1),
            "gdp_t": gdp_t,
            "level": level,
            "description": f"{ratio}% — {desc}",
        }
        set_cached(key, result, ttl_hours=24)
        return result
    except Exception as e:
        logger.warning("버핏지수 계산 실패: %s", e)
        return None


# ── 공포탐욕 지수 ────────────────────────────────────────────────────────────

def calc_fear_greed() -> Optional[dict]:
    """VIX + S&P 500 모멘텀 기반 공포탐욕 종합점수 (0=극공포, 100=극탐욕)."""
    key = "macro:fear_greed"
    cached = get_cached(key)
    if cached is not None:
        return cached or None

    try:
        import yfinance as yf

        # 1) VIX 점수 (VIX 낮을수록 탐욕)
        # F-6: 공유 스팟 위임. 폴백 20은 로컬에서만 적용 (공유 캐시 오염 금지).
        vix_val = get_vix_spot() or 20
        vix_score = max(0, min(100, round((40 - vix_val) / 30 * 100)))

        # 2) S&P 500 모멘텀 (현재가 vs 125일 MA)
        sp = yf.Ticker("^GSPC")
        hist = sp.history(period="6mo", interval="1d")
        if hist.empty or len(hist) < 20:
            momentum_score = 50
        else:
            closes = hist["Close"]
            current = float(closes.iloc[-1])
            ma125 = float(closes.tail(125).mean()) if len(closes) >= 125 else float(closes.mean())
            pct_diff = (current - ma125) / ma125 * 100
            momentum_score = max(0, min(100, round(50 + pct_diff * 5)))

        # 3) 시장폭 (최근 20일 양봉 비율)
        if not hist.empty and len(hist) >= 20:
            recent = hist.tail(20)
            up_days = sum(1 for _, row in recent.iterrows() if row["Close"] > row["Open"])
            breadth_score = round(up_days / 20 * 100)
        else:
            breadth_score = 50

        # 종합 (가중 평균)
        score = round(vix_score * 0.4 + momentum_score * 0.35 + breadth_score * 0.25)

        if score >= 80:
            label = "극심한 탐욕"
        elif score >= 60:
            label = "탐욕"
        elif score >= 40:
            label = "중립"
        elif score >= 20:
            label = "공포"
        else:
            label = "극심한 공포"

        result = {
            "score": score,
            "label": label,
            "components": {
                "vix_score": vix_score,
                "momentum_score": momentum_score,
                "breadth_score": breadth_score,
            },
        }
        set_cached(key, result, ttl_hours=1)
        return result
    except Exception as e:
        logger.warning("공포탐욕지수 계산 실패: %s", e)
        return None


# ── 수익률곡선 ──────────────────────────────────────────────────────────────

_YIELD_SYMBOLS = [
    ("^IRX", "3m"),
    ("^FVX", "5y"),
    ("^TNX", "10y"),
    ("^TYX", "30y"),
]


def fetch_yield_curve_data() -> dict:
    """미국 국채 수익률곡선 — 현재값 + 장기 시계열(주봉, 최대 30년) + 역전 여부."""
    key = "macro:yield_curve"
    cached = get_cached(key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        current: dict[str, Optional[float]] = {}
        histories: dict[str, list] = {}

        def _fetch_yield(sym: str, label: str):
            try:
                t = yf.Ticker(sym)
                fi = t.fast_info
                val = _safe(fi.last_price) or _safe(fi.previous_close)
                hist = t.history(period="max", interval="1wk")
                ts_list = []
                if not hist.empty:
                    for ts, row in hist.iterrows():
                        close = _safe(row["Close"])
                        if close is not None:
                            ts_list.append({
                                "date": ts.strftime("%Y-%m-%d"),
                                "value": round(close, 3),
                            })
                return label, val, ts_list
            except Exception as e:
                logger.warning("수익률곡선 %s 조회 실패: %s", sym, e)
                return label, None, []

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(_fetch_yield, sym, label) for sym, label in _YIELD_SYMBOLS]
            for fut in as_completed(futs):
                label, val, ts_list = fut.result()
                current[label] = round(val, 3) if val is not None else None
                histories[label] = ts_list

        # 10Y-3M 스프레드
        y10 = current.get("10y")
        y3m = current.get("3m")
        spread = round(y10 - y3m, 3) if (y10 is not None and y3m is not None) else None

        # 시계열 스프레드 (날짜 정렬 — 3m과 10y 교차 매핑)
        h3m_map = {d["date"]: d["value"] for d in histories.get("3m", [])}
        h10y_map = {d["date"]: d["value"] for d in histories.get("10y", [])}
        all_dates = sorted(set(h3m_map.keys()) & set(h10y_map.keys()))
        history = []
        for dt in all_dates:
            v3m = h3m_map[dt]
            v10y = h10y_map[dt]
            history.append({
                "date": dt,
                "y3m": v3m,
                "y10y": v10y,
                "spread": round(v10y - v3m, 3),
            })

        result = {
            "current": current,
            "spread_10y_3m": spread,
            "history": history,
            "inverted": spread < 0 if spread is not None else False,
        }
        set_cached(key, result, ttl_hours=1)
        return result
    except Exception as e:
        logger.warning("수익률곡선 데이터 조회 실패: %s", e)
        return {
            "current": {"3m": None, "5y": None, "10y": None, "30y": None},
            "spread_10y_3m": None,
            "history": [],
            "inverted": False,
        }


# ── 신용스프레드 ────────────────────────────────────────────────────────────

def _percentile_from_sorted(sorted_values: list[float], p: float) -> float:
    """0~100 백분위에 해당하는 값 (정렬된 리스트 인덱스 보간).

    p=10 → 10%ile. n=1 가드.
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return round(sorted_values[0], 2)
    idx = max(0, min(n - 1, int(round((p / 100.0) * (n - 1)))))
    return round(sorted_values[idx], 2)


def _compute_oas_stats(rows: list[dict]) -> dict:
    """OAS 시계열에서 분포 통계.

    Args:
        rows: [{"date": "YYYY-MM-DD", "oas": float}, ...] (정렬 무관)

    Returns:
        {mean, median, std, p10, p25, p50, p75, p90, p95, max, max_date} 또는 {}.
    """
    if not rows:
        return {}
    try:
        values = [float(r["oas"]) for r in rows if r.get("oas") is not None]
        if not values:
            return {}
        sorted_v = sorted(values)
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        std = variance ** 0.5

        # max + max 날짜
        max_v = max(values)
        max_row = next((r for r in rows if float(r.get("oas", 0)) == max_v), None)
        max_date = max_row["date"] if max_row else None

        return {
            "mean": round(mean, 2),
            "median": _percentile_from_sorted(sorted_v, 50),
            "std": round(std, 2),
            "p10": _percentile_from_sorted(sorted_v, 10),
            "p25": _percentile_from_sorted(sorted_v, 25),
            "p50": _percentile_from_sorted(sorted_v, 50),
            "p75": _percentile_from_sorted(sorted_v, 75),
            "p90": _percentile_from_sorted(sorted_v, 90),
            "p95": _percentile_from_sorted(sorted_v, 95),
            "max": round(max_v, 2),
            "max_date": max_date,
        }
    except Exception as e:
        logger.warning("OAS stats 계산 실패: %s", e)
        return {}


def _classify_oas_sentiment(current: float, stats: dict) -> dict:
    """OAS 현재값을 백분위 5단계 + 절대 안전장치로 분류 (하워드 막스 시계추).

    백분위 5단계 (전 기간 baseline 기반):
      <10  → extreme_greed
      <30  → greed
      <70  → normal
      <90  → fear
      >=90 → extreme_fear

    절대 안전장치: current > 10.0 → 백분위 무관 extreme_fear (역사적 단절 감지).

    Args:
        current: 현재 OAS (%)
        stats: _compute_oas_stats() 반환값

    Returns:
        {"sentiment": str, "percentile": float | None, "zscore": float | None}
    """
    # 1) 절대 안전장치 (OAS > 10% 패닉)
    if current is not None and current > 10.0:
        # percentile/zscore도 가능하면 계산
        pct = None
        zscore = None
        if stats:
            try:
                mean = stats.get("mean")
                std = stats.get("std")
                if mean is not None and std and std > 0:
                    zscore = round((current - mean) / std, 2)
            except Exception:
                pass
        return {"sentiment": "extreme_fear", "percentile": pct, "zscore": zscore}

    # 2) stats 없으면 normal 폴백
    if not stats:
        return {"sentiment": "normal", "percentile": None, "zscore": None}

    # 3) 백분위 계산 (stats의 분위 임계 사용)
    # current가 p_X 기준 어느 단계인지 결정
    try:
        p10 = stats.get("p10")
        p25 = stats.get("p25")
        p75 = stats.get("p75")
        p90 = stats.get("p90")
        mean = stats.get("mean")
        std = stats.get("std")

        # 백분위 (선형 보간 — 분위 임계 사이 위치)
        # 간단화: 분위 임계 5점 사이의 선형 보간
        bps = [(0.0, 0.0), (10.0, p10), (25.0, p25), (50.0, stats.get("p50")),
               (75.0, p75), (90.0, p90), (95.0, stats.get("p95")),
               (100.0, stats.get("max"))]
        bps = [(p, v) for p, v in bps if v is not None]
        bps.sort(key=lambda x: x[1])
        # current 위치 찾기
        if current <= bps[0][1]:
            pct = 0.0
        elif current >= bps[-1][1]:
            pct = 100.0
        else:
            pct = 50.0
            for i in range(1, len(bps)):
                p_lo, v_lo = bps[i - 1]
                p_hi, v_hi = bps[i]
                if v_lo <= current <= v_hi:
                    if v_hi == v_lo:
                        pct = p_hi
                    else:
                        pct = p_lo + (current - v_lo) / (v_hi - v_lo) * (p_hi - p_lo)
                    break
        pct = round(pct, 1)

        # zscore
        zscore = None
        if mean is not None and std and std > 0:
            zscore = round((current - mean) / std, 2)

        # 5단계 분류
        if pct < 10:
            sentiment = "extreme_greed"
        elif pct < 30:
            sentiment = "greed"
        elif pct < 70:
            sentiment = "normal"
        elif pct < 90:
            sentiment = "fear"
        else:
            sentiment = "extreme_fear"

        return {"sentiment": sentiment, "percentile": pct, "zscore": zscore}
    except Exception as e:
        logger.warning("OAS sentiment 분류 실패: %s", e)
        return {"sentiment": "normal", "percentile": None, "zscore": None}


# ── FRED HTTP 핫픽스 (2026-05-04, R1) ─────────────────────────────────────────
# 사용자 신고: hy_oas/ig_oas partial_failure 빈번. 운영 IP에서 FRED `fredgraph.csv`
# 응답이 가끔 HTML 차단 페이지로 돌아오거나 timeout. 대응:
#  1) Mozilla UA로 변경
#  2) timeout 25초 + 1회 재시도(2초 간격)
#  3) Content-Type 검증 (text/csv 또는 text/plain만 허용)
#  4) 7일 stale 캐시 fallback — 신선 fetch 실패 시 마지막 성공 응답 재활용
_FRED_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# 원본 기본값 25s. 이식 환경에서 FRED CSV가 간헐 차단될 때 대기 시간을 줄이려면 환경변수로 조정
# (I/O 재시도 정책 — 투자 로직·캐시 TTL과 무관). 예: MACRO_LITE_FRED_TIMEOUT=8
def _env_timeout(name: str, default: float) -> float:
    """환경변수 timeout 파싱. 빈 값·비숫자·0 이하는 default (오타 하나로 하이일드 섹션이 죽지 않게)."""
    raw = os.getenv(name, "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


_FRED_TIMEOUT = _env_timeout("MACRO_LITE_FRED_TIMEOUT", 25)
_FRED_STALE_TTL_HOURS = 24 * 7  # 7일


def _http_get_fred_csv(url: str) -> Optional[str]:
    """FRED `fredgraph.csv` 요청을 안전하게 수행한다.

    UA + timeout + Content-Type 검증 + 1회 재시도. 실패 시 None.
    """
    import time as _time
    import requests as _requests

    headers = {"User-Agent": _FRED_BROWSER_UA, "Accept": "text/csv,*/*"}
    for attempt in (1, 2):
        try:
            resp = _requests.get(url, timeout=_FRED_TIMEOUT, headers=headers)
            resp.raise_for_status()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype.startswith("text/csv") or ctype.startswith("text/plain"):
                return resp.text
            logger.error(
                "FRED 비-CSV 응답 (attempt %d): status=%s ctype=%r body_head=%r url=%s",
                attempt, resp.status_code, ctype, resp.text[:200], url,
            )
        except Exception as e:
            logger.warning("FRED 요청 실패 (attempt %d) %s: %s", attempt, url, e)
        if attempt == 1:
            _time.sleep(2)
    return None


def _fetch_fred_via_api(series_id: str) -> Optional[list[dict]]:
    """FRED 공식 JSON API 폴백 (FRED_API_KEY 필요).

    https://fred.stlouisfed.org/docs/api/fred/series_observations.html
    실패 또는 키 미설정 시 None.
    """
    FRED_API_KEY = os.getenv("FRED_API_KEY", "")
    if not FRED_API_KEY:
        return None
    import requests as _requests
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        # 2026-05-10: realtime_start/end 기본값(today)이 vintage 필터로 작용해
        # ~3년치만 반환되던 결함. '1776-07-04'~'9999-12-31'로 전 vintage 활성화.
        # FRED API docs: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "observation_start": "1996-12-31",
            "realtime_start": "1776-07-04",
            "realtime_end": "9999-12-31",
        }
        resp = _requests.get(
            url, params=params, timeout=_FRED_TIMEOUT,
            headers={"User-Agent": _FRED_BROWSER_UA},
        )
        resp.raise_for_status()
        data = resp.json()
        rows: list[dict] = []
        for obs in data.get("observations", []):
            v = obs.get("value", ".")
            if v == "." or v is None:
                continue
            try:
                rows.append({"date": obs["date"], "value": round(float(v), 2)})
            except (ValueError, KeyError):
                continue
        if rows:
            logger.info("FRED API 폴백 성공: %s (%d rows)", series_id, len(rows))
        return rows or None
    except Exception as e:
        logger.warning("FRED API 폴백 실패 (%s): %s", series_id, e)
        return None


def _parse_fred_csv(text: str, value_key: str) -> list[dict]:
    """FRED CSV(date,value) → [{date, <value_key>}]."""
    rows: list[dict] = []
    for line in text.strip().split("\n")[1:]:
        parts = line.strip().split(",")
        if len(parts) == 2 and parts[1] != ".":
            try:
                rows.append({"date": parts[0], value_key: round(float(parts[1]), 2)})
            except ValueError:
                continue
    return rows


def _fetch_fred_oas() -> dict:
    """FRED에서 HY OAS(BAMLH0A0HYM2) 공식 스프레드 수집 (API 키 불필요).

    하워드 막스의 하이일드 스프레드 프레임워크 — 백분위 5단계:
    - 백분위 < 10: extreme_greed (위험 둔감 정점)
    - < 30:        greed
    - < 70:        normal
    - < 90:        fear
    - >= 90:       extreme_fear (패닉, 매집 기회)
    + OAS > 10% 절대 안전장치 (역사적 단절 감지) → extreme_fear 강제

    전 기간 baseline (1996-12-31 ~ 현재, 약 28년) 사용 — 신용 사이클 7~10년.

    R1 (2026-05-04): 신선 fetch 실패 시 7일 stale 캐시(`macro:credit_spread_fred_hy_stale`) 재활용.
    응답에 `_stale_used: bool` 표시.

    Returns: {oas_current, oas_history_5y, oas_history_full, oas_stats,
              oas_percentile, oas_zscore, sentiment, oas_history(=alias),
              percentile(=alias), _stale_used} 또는 빈 dict.
    """
    from datetime import date, timedelta

    stale_key = "macro:credit_spread_fred_hy_stale"
    try:
        start = "1996-12-31"
        end = date.today().strftime("%Y-%m-%d")
        url = (
            f"https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id=BAMLH0A0HYM2&cosd={start}&coed={end}"
        )
        text = _http_get_fred_csv(url)
        rows: list[dict] = []
        if text:
            rows = _parse_fred_csv(text, "oas")
        if not rows:
            # CSV 실패 → JSON API 폴백 (FRED_API_KEY 있을 때만 작동)
            api_rows = _fetch_fred_via_api("BAMLH0A0HYM2")
            if api_rows:
                rows = [{"date": r["date"], "oas": r["value"]} for r in api_rows]
        if not rows:
            logger.error(
                "FRED HY OAS 신선 fetch 실패 (CSV + JSON API 모두). body_head=%r",
                (text or "")[:200],
            )
            stale = get_cached(stale_key)
            if stale:
                logger.warning("FRED HY OAS stale fallback 사용")
                return {**stale, "_stale_used": True}
            return {}

        current = rows[-1]["oas"]
        stats = _compute_oas_stats(rows)
        clf = _classify_oas_sentiment(current, stats)

        # 2026-05-10: ICE BofA 라이센스 정책으로 FRED API가 ~3년치만 반환.
        # 자체 누적 store(stock.oas_history_store)에 매일 1일치 머지 + FIFO 10년 유지.
        # FRED 신규 데이터(rows)를 store에 머지 + 누적된 전체 시계열 사용.
        try:
            from .oas_history_store import merge_and_persist, slice_history
            persist_rows = [{"date": r["date"], "value": r["oas"]} for r in rows]
            merge_stats = merge_and_persist("BAMLH0A0HYM2", persist_rows)
            logger.info("OAS HY 누적: +%d rows, total=%d (%s ~ %s)",
                        merge_stats["added"], merge_stats["total"],
                        merge_stats["first_date"], merge_stats["last_date"])
            # 누적 store에서 10년/5년 슬라이스 (FRED 직접 슬라이스 X)
            persist_10y = slice_history("BAMLH0A0HYM2", 10)
            persist_5y = slice_history("BAMLH0A0HYM2", 5)
            oas_history_10y = [{"date": r["date"], "oas": r["value"]} for r in persist_10y]
            oas_history_5y = [{"date": r["date"], "oas": r["value"]} for r in persist_5y]
        except Exception as e:
            # 누적 store 실패 시 FRED 직접 슬라이스 fallback (이전 동작)
            logger.warning("OAS 누적 store 실패, FRED 직접 슬라이스 fallback: %s", e)
            ten_year_start = (date.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
            oas_history_10y = [r for r in rows if r["date"] >= ten_year_start]
            five_year_start = (date.today() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
            oas_history_5y = [r for r in rows if r["date"] >= five_year_start]

        result = {
            "oas_current": current,
            "oas_history_10y": oas_history_10y,
            "oas_history_5y": oas_history_5y,
            "oas_history_full": rows,
            "oas_stats": stats,
            "oas_percentile": clf.get("percentile"),
            "oas_zscore": clf.get("zscore"),
            "sentiment": clf.get("sentiment"),
            # 후방호환 alias — 10y 우선 (5y는 fallback)
            "oas_history": oas_history_10y,
            "percentile": clf.get("percentile"),
            "_stale_used": False,
        }
        # 7일 stale 캐시에도 저장
        set_cached(stale_key, result, ttl_hours=_FRED_STALE_TTL_HOURS)
        return result
    except Exception as e:
        logger.warning("FRED HY OAS 조회 실패: %s", e)
        stale = get_cached(stale_key)
        if stale:
            logger.warning("FRED HY OAS stale fallback (예외)")
            return {**stale, "_stale_used": True}
        return {}


def _fetch_fred_ig_oas() -> dict:
    """FRED에서 IG OAS(BAMLC0A0CM, Investment Grade Corporate OAS) 수집.

    R1 (2026-05-04): 7일 stale 캐시(`macro:credit_spread_fred_ig_stale`) fallback.

    Returns: {ig_current, ig_history_5y, ig_stats, _stale_used} 또는 {}.
    """
    from datetime import date, timedelta

    stale_key = "macro:credit_spread_fred_ig_stale"
    try:
        start = "1996-12-31"
        end = date.today().strftime("%Y-%m-%d")
        url = (
            f"https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id=BAMLC0A0CM&cosd={start}&coed={end}"
        )
        text = _http_get_fred_csv(url)
        rows: list[dict] = []
        if text:
            rows = _parse_fred_csv(text, "ig")
        if not rows:
            api_rows = _fetch_fred_via_api("BAMLC0A0CM")
            if api_rows:
                rows = [{"date": r["date"], "ig": r["value"]} for r in api_rows]
        if not rows:
            logger.error(
                "FRED IG OAS 신선 fetch 실패 (CSV + JSON API 모두). body_head=%r",
                (text or "")[:200],
            )
            stale = get_cached(stale_key)
            if stale:
                logger.warning("FRED IG OAS stale fallback 사용")
                return {**stale, "_stale_used": True}
            return {}

        rows_for_stats = [{"date": r["date"], "oas": r["ig"]} for r in rows]
        stats = _compute_oas_stats(rows_for_stats)

        # 2026-05-10: 자체 누적 store + FIFO 10년 유지 (HY OAS와 동일 정책).
        try:
            from .oas_history_store import merge_and_persist, slice_history
            persist_rows = [{"date": r["date"], "value": r["ig"]} for r in rows]
            merge_and_persist("BAMLC0A0CM", persist_rows)
            persist_10y = slice_history("BAMLC0A0CM", 10)
            persist_5y = slice_history("BAMLC0A0CM", 5)
            ig_history_10y = [{"date": r["date"], "ig": r["value"]} for r in persist_10y]
            ig_history_5y = [{"date": r["date"], "ig": r["value"]} for r in persist_5y]
        except Exception as e:
            logger.warning("IG OAS 누적 store 실패, FRED 직접 슬라이스 fallback: %s", e)
            ten_year_start = (date.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
            ig_history_10y = [r for r in rows if r["date"] >= ten_year_start]
            five_year_start = (date.today() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
            ig_history_5y = [r for r in rows if r["date"] >= five_year_start]

        result = {
            "ig_current": rows[-1]["ig"],
            "ig_history_10y": ig_history_10y,
            "ig_history_5y": ig_history_5y,  # 후방호환
            "ig_stats": stats,
            "_stale_used": False,
        }
        set_cached(stale_key, result, ttl_hours=_FRED_STALE_TTL_HOURS)
        return result
    except Exception as e:
        logger.warning("FRED IG OAS 조회 실패: %s", e)
        stale = get_cached(stale_key)
        if stale:
            logger.warning("FRED IG OAS stale fallback (예외)")
            return {**stale, "_stale_used": True}
        return {}


def fetch_credit_spread() -> dict:
    """HY OAS(FRED) + IG OAS 기반 신용스프레드.

    1순위: FRED HY OAS 백분위 5단계 (하워드 막스 프레임워크, 전 기간 baseline)
    보조: FRED IG OAS + HY-IG 스프레드(정크 디스카운트)
    """
    # v8 (2026-05-10): HYG 프록시 제거. FRED 라이센스 정책으로 ~3년만 표시.
    # 자체 oas_history_store(FRED 데이터만) FIFO 누적 → 7년 후 자연스럽게 10년 도달.
    key = "macro:credit_spread_v8"
    cached = get_cached(key)
    if cached is not None:
        return cached

    partial_failure: list[str] = []

    # FRED HY OAS (전 기간 + 5단계)
    fred_data = _fetch_fred_oas()
    if not fred_data:
        partial_failure.append("hy_oas")
    elif fred_data.get("_stale_used"):
        partial_failure.append("hy_oas_stale_used")

    # FRED IG OAS (보조 카드용)
    ig_data = _fetch_fred_ig_oas()
    if not ig_data:
        partial_failure.append("ig_oas")
    elif ig_data.get("_stale_used"):
        partial_failure.append("ig_oas_stale_used")

    # HY-IG 스프레드 + 5년 시계열
    hy_current = fred_data.get("oas_current") if fred_data else None
    ig_current = ig_data.get("ig_current") if ig_data else None
    hy_ig_spread = (
        round(hy_current - ig_current, 2)
        if hy_current is not None and ig_current is not None
        else None
    )
    # 2026-05-10: HY-IG 스프레드 시계열 5y → 10y 확대.
    # FRED CSV 매일 자동 갱신 + 24h 캐시 → FIFO rolling 자연 발생.
    hy_ig_history_10y = []
    hy_ig_history_5y = []  # 후방호환
    try:
        hy_10y = fred_data.get("oas_history_10y", []) if fred_data else []
        ig_10y = ig_data.get("ig_history_10y", []) if ig_data else []
        if hy_10y and ig_10y:
            ig_map = {r["date"]: r["ig"] for r in ig_10y}
            for r in hy_10y:
                ig_v = ig_map.get(r["date"])
                if ig_v is not None:
                    hy_ig_history_10y.append({
                        "date": r["date"],
                        "spread": round(r["oas"] - ig_v, 2),
                    })
            # 5y는 10y의 슬라이스
            from datetime import date as _d, timedelta as _td
            five_year_start = (_d.today() - _td(days=365 * 5)).strftime("%Y-%m-%d")
            hy_ig_history_5y = [r for r in hy_ig_history_10y if r["date"] >= five_year_start]
    except Exception as e:
        logger.debug("HY-IG 시계열 매칭 실패: %s", e)

    result = {
        # FRED HY OAS (전 기간 baseline + 5단계, 10년 시계열)
        "oas_current": fred_data.get("oas_current") if fred_data else None,
        "oas_history_10y": fred_data.get("oas_history_10y", []) if fred_data else [],
        "oas_history_5y": fred_data.get("oas_history_5y", []) if fred_data else [],  # 후방호환
        "oas_history": fred_data.get("oas_history_10y", []) if fred_data else [],  # alias 10y 우선
        "oas_stats": fred_data.get("oas_stats", {}) if fred_data else {},
        "oas_percentile": fred_data.get("oas_percentile") if fred_data else None,
        "oas_zscore": fred_data.get("oas_zscore") if fred_data else None,
        "oas_sentiment": fred_data.get("sentiment") if fred_data else None,
        "percentile": fred_data.get("oas_percentile") if fred_data else None,  # 후방호환
        # FRED IG OAS + HY-IG 스프레드 (10년)
        "ig_current": ig_current,
        "ig_history_10y": ig_data.get("ig_history_10y", []) if ig_data else [],
        "ig_history_5y": ig_data.get("ig_history_5y", []) if ig_data else [],  # 후방호환
        "hy_ig_spread": hy_ig_spread,
        "hy_ig_spread_history_10y": hy_ig_history_10y,
        "hy_ig_spread_history_5y": hy_ig_history_5y,  # 후방호환
        # 부분 실패 메타
        "partial_failure": partial_failure,
    }
    if fred_data or ig_data:
        set_cached(key, result, ttl_hours=24)
    return result



# ── 환율 ────────────────────────────────────────────────────────────────────

_CURRENCY_SYMBOLS = [
    ("USDKRW=X", "USD/KRW"),
    ("USDJPY=X", "USD/JPY"),
    ("EURUSD=X", "EUR/USD"),
    ("DX-Y.NYB", "달러인덱스"),
]


def fetch_currency_quotes() -> list[dict]:
    """주요 환율 현재가 + 1개월 스파크라인."""
    key = "macro:currencies"
    cached = get_cached(key)
    if cached is not None:
        return cached

    def _fetch_one(sym: str, name: str) -> Optional[dict]:
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            fi = t.fast_info

            price = _safe(fi.last_price) or _safe(fi.previous_close)
            if price is None:
                return None

            prev = _safe(fi.previous_close) or price
            change = round(price - prev, 4)
            change_pct = round((price - prev) / prev * 100, 2) if prev else 0

            hist = t.history(period="1mo", interval="1d")
            sparkline = []
            if not hist.empty:
                for ts, row in hist.iterrows():
                    close = _safe(row["Close"])
                    if close is not None:
                        sparkline.append({"date": ts.strftime("%Y-%m-%d"), "v": round(close, 4)})

            return {
                "symbol": sym,
                "name": name,
                "price": round(price, 4),
                "prev_close": round(prev, 4),
                "change": change,
                "change_pct": change_pct,
                "sparkline": sparkline,
            }
        except Exception as e:
            logger.warning("환율 조회 실패 (%s): %s", sym, e)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_fetch_one, sym, name): (sym, name) for sym, name in _CURRENCY_SYMBOLS}
        for fut in as_completed(futs):
            sym, name = futs[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception:
                pass

    # 원래 순서 유지
    order_map = {sym: i for i, (sym, _) in enumerate(_CURRENCY_SYMBOLS)}
    results.sort(key=lambda x: order_map.get(x["symbol"], 99))

    if results:
        set_cached(key, results, ttl_hours=0.17)  # ~10분
    return results


# ── 원자재 ──────────────────────────────────────────────────────────────────

_COMMODITY_SYMBOLS = [
    ("CL=F", "WTI 원유"),
    ("URA", "우라늄 ETF"),
    ("GC=F", "금"),
    ("ZC=F", "옥수수"),
    ("ZW=F", "밀"),
    ("ZS=F", "대두"),
]


def fetch_commodity_quotes() -> list[dict]:
    """주요 원자재 현재가 + 1개월 스파크라인."""
    key = "macro:commodities"
    cached = get_cached(key)
    if cached is not None:
        return cached

    def _fetch_one(sym: str, name: str) -> Optional[dict]:
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            fi = t.fast_info

            price = _safe(fi.last_price) or _safe(fi.previous_close)
            if price is None:
                return None

            prev = _safe(fi.previous_close) or price
            change = round(price - prev, 2)
            change_pct = round((price - prev) / prev * 100, 2) if prev else 0

            hist = t.history(period="1mo", interval="1d")
            sparkline = []
            if not hist.empty:
                for ts, row in hist.iterrows():
                    close = _safe(row["Close"])
                    if close is not None:
                        sparkline.append({"date": ts.strftime("%Y-%m-%d"), "v": round(close, 2)})

            return {
                "symbol": sym,
                "name": name,
                "price": round(price, 2),
                "prev_close": round(prev, 2),
                "change": change,
                "change_pct": change_pct,
                "sparkline": sparkline,
            }
        except Exception as e:
            logger.warning("원자재 조회 실패 (%s): %s", sym, e)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(_fetch_one, sym, name): (sym, name) for sym, name in _COMMODITY_SYMBOLS}
        for fut in as_completed(futs):
            sym, name = futs[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception:
                pass

    order_map = {sym: i for i, (sym, _) in enumerate(_COMMODITY_SYMBOLS)}
    results.sort(key=lambda x: order_map.get(x["symbol"], 99))

    if results:
        set_cached(key, results, ttl_hours=0.17)  # ~10분
    return results


# ── 섹터 수익률 ─────────────────────────────────────────────────────────────

_SECTOR_ETFS = [
    ("XLK", "Technology", "기술"),
    ("XLF", "Financials", "금융"),
    ("XLE", "Energy", "에너지"),
    ("XLV", "Health Care", "헬스케어"),
    ("XLY", "Consumer Discretionary", "경기소비"),
    ("XLP", "Consumer Staples", "필수소비"),
    ("XLI", "Industrials", "산업재"),
    ("XLU", "Utilities", "유틸리티"),
    ("XLRE", "Real Estate", "부동산"),
    ("XLC", "Communication Services", "커뮤니케이션"),
    ("XLB", "Materials", "소재"),
]


def _calc_return(closes: list[float], n_days: int) -> Optional[float]:
    """n_days 기간 수익률(%). 데이터 부족 시 None."""
    if len(closes) < n_days + 1:
        return None
    try:
        return round((closes[-1] / closes[-n_days - 1] - 1) * 100, 2)
    except (ZeroDivisionError, IndexError):
        return None


# ── R3 (2026-05-04): 섹터 상대평가 산점도 입력 헬퍼 ──────────────────────────
# 도메인 자문(MacroSentinel/ValueScreener) 합의:
#   x축 = SMA20 cross 기준 추세 시작점 경과일(부호 포함, ±365 cap)
#   y축 = 1Y 누적수익률을 모든 섹터 분포 기준 z-score(±3 cap)로 표준화

def _compute_sma20_trend_days(closes: list[float]) -> int:
    """현재 가격이 20일 이동평균선과 마지막으로 cross한 시점부터 경과일.

    부호: 현재 종가 > SMA20이면 양수(상승추세), 아래면 음수(하락추세).
    범위: ±365 cap. 데이터 부족(<25일) 시 0.
    """
    if not closes or len(closes) < 25:
        return 0
    cap = 365

    # 일별 SMA20 시계열
    sma20: list[Optional[float]] = []
    for i in range(len(closes)):
        if i < 19:
            sma20.append(None)
        else:
            window = closes[i - 19 : i + 1]
            sma20.append(sum(window) / 20)

    # 현재 부호
    last_close = closes[-1]
    last_sma = sma20[-1]
    if last_sma is None:
        return 0
    sign = 1 if last_close > last_sma else -1

    # 끝에서 역순으로 부호가 다른 첫 시점 찾기 → 그 다음 일이 cross 직후
    days = 0
    for i in range(len(closes) - 1, -1, -1):
        s = sma20[i]
        if s is None:
            break
        cur_sign = 1 if closes[i] > s else -1
        if cur_sign != sign:
            break
        days += 1
    days = min(days, cap)
    return sign * days


def _compute_intensity_zscore(returns_1y: list[Optional[float]]) -> list[float]:
    """1Y 수익률 리스트를 z-score(±3 cap)로 표준화.

    None은 입력 위치 그대로 0.0으로 반환. std=0 또는 유효 데이터 <2 시 모두 0.
    """
    valid = [r for r in returns_1y if isinstance(r, (int, float))]
    n = len(valid)
    if n < 2:
        return [0.0] * len(returns_1y)
    mean = sum(valid) / n
    var = sum((r - mean) ** 2 for r in valid) / n
    std = var ** 0.5
    if std == 0:
        return [0.0] * len(returns_1y)
    out: list[float] = []
    for r in returns_1y:
        if not isinstance(r, (int, float)):
            out.append(0.0)
            continue
        z = (r - mean) / std
        z = max(-3.0, min(3.0, z))
        out.append(round(z, 3))
    return out


def fetch_sector_returns() -> list[dict]:
    """11개 섹터 ETF 1M/3M/6M/1Y/3Y 수익률 + R3 산점도 입력(trend_days, intensity_z)."""
    # v4 (2026-05-05): period 3y → 5y 변경. 3y는 거래일 ~755로 3Y 수익률
    # 계산(756+1일 필요)이 항상 데이터 부족으로 None 반환되던 버그 해소.
    key = "macro:sector_returns_v4"
    cached = get_cached(key)
    if cached is not None:
        return cached

    def _fetch_one(sym: str, name: str, name_ko: str) -> Optional[dict]:
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            hist = t.history(period="5y", interval="1d")
            if hist.empty:
                return None

            closes = [_safe(v) for v in hist["Close"].tolist()]
            closes = [c for c in closes if c is not None]
            if not closes:
                return None

            return {
                "symbol": sym,
                "name": name,
                "name_ko": name_ko,
                "return_1m": _calc_return(closes, 21),
                "return_3m": _calc_return(closes, 63),
                "return_6m": _calc_return(closes, 126),
                "return_1y": _calc_return(closes, 252),
                "return_3y": _calc_return(closes, 756),
                "trend_days": _compute_sma20_trend_days(closes),
            }
        except Exception as e:
            logger.warning("섹터 수익률 조회 실패 (%s): %s", sym, e)
            return None

    results = []
    with ThreadPoolExecutor(max_workers=11) as pool:
        futs = {pool.submit(_fetch_one, sym, name, name_ko): sym for sym, name, name_ko in _SECTOR_ETFS}
        for fut in as_completed(futs):
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception:
                pass

    order_map = {sym: i for i, (sym, _, _) in enumerate(_SECTOR_ETFS)}
    results.sort(key=lambda x: order_map.get(x["symbol"], 99))

    # 1Y z-score 일괄 산출 (전체 섹터 분포 기준)
    zs = _compute_intensity_zscore([r.get("return_1y") for r in results])
    for r, z in zip(results, zs):
        r["intensity_z"] = z

    if results:
        set_cached(key, results, ttl_hours=1)
    return results


# ── 경기사이클 입력 ─────────────────────────────────────────────────────────

def fetch_cycle_inputs() -> dict:
    """경기 사이클 판단에 필요한 6개 지표 수집."""
    key = "macro:cycle_inputs"
    cached = get_cached(key)
    if cached is not None:
        return cached

    result: dict = {
        "yield_spread": None,
        "yield_direction": "stable",
        "credit_direction": "stable",
        "vix_value": None,
        "vix_level": "normal",
        "sector_rotation": "mixed",
        "dollar_strength": "stable",
    }

    # 1) 수익률곡선
    try:
        yc = fetch_yield_curve_data()
        result["yield_spread"] = yc.get("spread_10y_3m")
        # 방향 판단: 최근 20일 스프레드 추세
        hist = yc.get("history", [])
        if len(hist) >= 20:
            recent = [h["spread"] for h in hist[-20:]]
            older = [h["spread"] for h in hist[-40:-20]] if len(hist) >= 40 else recent
            avg_recent = sum(recent) / len(recent)
            avg_older = sum(older) / len(older)
            diff = avg_recent - avg_older
            if diff > 0.1:
                result["yield_direction"] = "steepening"
            elif diff < -0.1:
                result["yield_direction"] = "flattening"
            else:
                result["yield_direction"] = "stable"
    except Exception as e:
        logger.warning("수익률곡선 입력 실패: %s", e)

    # 2) 신용스프레드 — OAS 백분위 변화로 방향 추론(HYG/LQD 폐기 후)
    #    oas_momentum_6m이 음수=축소(narrowing), 양수=확대(widening)
    try:
        cs = fetch_credit_spread()
        mom = cs.get("oas_momentum_6m")
        if mom is None:
            result["credit_direction"] = "stable"
        elif mom > 0.5:
            result["credit_direction"] = "widening"
        elif mom < -0.5:
            result["credit_direction"] = "narrowing"
        else:
            result["credit_direction"] = "stable"
    except Exception as e:
        logger.warning("신용스프레드 입력 실패: %s", e)

    # 3) VIX
    try:
        vix = fetch_vix()
        if vix:
            result["vix_value"] = vix["value"]
            result["vix_level"] = vix["level"]
    except Exception as e:
        logger.warning("VIX 입력 실패: %s", e)

    # 4) 섹터 로테이션
    try:
        sectors = fetch_sector_returns()
        if sectors:
            sector_map = {s["symbol"]: s for s in sectors}
            cyclical_syms = ["XLY", "XLK", "XLF", "XLI"]
            defensive_syms = ["XLP", "XLU", "XLV"]

            cyclical_ret = []
            for sym in cyclical_syms:
                s = sector_map.get(sym)
                if s and s.get("return_3m") is not None:
                    cyclical_ret.append(s["return_3m"])

            defensive_ret = []
            for sym in defensive_syms:
                s = sector_map.get(sym)
                if s and s.get("return_3m") is not None:
                    defensive_ret.append(s["return_3m"])

            if cyclical_ret and defensive_ret:
                avg_cyc = sum(cyclical_ret) / len(cyclical_ret)
                avg_def = sum(defensive_ret) / len(defensive_ret)
                if avg_cyc - avg_def > 2:
                    result["sector_rotation"] = "cyclical"
                elif avg_def - avg_cyc > 2:
                    result["sector_rotation"] = "defensive"
                else:
                    result["sector_rotation"] = "mixed"
    except Exception as e:
        logger.warning("섹터 로테이션 입력 실패: %s", e)

    # 5) 달러 강도
    try:
        import yfinance as yf
        dx = yf.Ticker("DX-Y.NYB")
        hist = dx.history(period="2mo", interval="1d")
        if not hist.empty and len(hist) >= 20:
            closes = [_safe(v) for v in hist["Close"].tolist()]
            closes = [c for c in closes if c is not None]
            if len(closes) >= 20:
                current = closes[-1]
                ma20 = sum(closes[-20:]) / 20
                pct_diff = (current - ma20) / ma20 * 100
                if pct_diff > 1:
                    result["dollar_strength"] = "strengthening"
                elif pct_diff < -1:
                    result["dollar_strength"] = "weakening"
                else:
                    result["dollar_strength"] = "stable"
    except Exception as e:
        logger.warning("달러 강도 입력 실패: %s", e)

    set_cached(key, result, ttl_hours=1)
    return result
