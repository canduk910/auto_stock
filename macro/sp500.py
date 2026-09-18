"""S&P 500 주간 종가 시계열 — `GET /api/macro/sp500`.

🔴 이 파일은 **vendor 가 아니다.** `macro_lite/` 는 stock-manager 에서 무수정으로 들여오는
패키지라 손대지 않고, 우리가 필요해서 더하는 것은 이 파일과 `main.py` 에만 둔다. 재이식 때
`macro_lite/` 를 통째로 덮어써도 이 엔드포인트는 살아남는다.

왜 필요한가 — 사용자 요청(2026-09-18): 장단기 금리차·10년물 추이 차트와 하이일드 스프레드
차트에 **S&P500 가격선을 겹쳐** 매크로 지표와 주가의 관계를 한눈에 보려는 것이다.
`macro_lite` 의 다섯 섹션 응답 어디에도 S&P500 **시계열**은 없다(`fetcher.py` 가 `^GSPC` 를
쓰는 곳은 버핏지수 근사와 공포탐욕 모멘텀뿐이고 둘 다 **단일 스칼라**다).

설계 결정 셋:
1. **주간(`1wk`)** 으로 받는다. 금리차 history 자체가 주간 3,377포인트(1962~)라 일간을
   받으면 겹칠 상대가 없으면서 응답만 15배가 된다.
2. **`period="max"`** — 금리차는 1962년부터, 하이일드는 3년치라 둘의 범위가 크게 다르다.
   한 번 받아 두고 화면이 필요한 구간만 잘라 쓰는 편이 호출 수가 적다.
3. **24시간 캐시** — 원본 패키지의 다른 지표와 같은 TTL 이다(`macro_lite/cache.py`).
   주간 종가라 하루에 한 번보다 자주 받을 이유가 없다.

실패는 **절대 던지지 않는다** — 이 화면은 관찰 전용이고, S&P500 을 못 받았다고 금리차·하이일드
본선이 사라지면 안 된다. 못 받으면 `history: []` + `errors` 로 돌려주고 화면은 붉은 선만 뺀다.
"""
from __future__ import annotations

import logging
from typing import Any

from macro_lite.cache import get_cached, now_kst_iso, set_cached

logger = logging.getLogger(__name__)

_CACHE_KEY = "macro:sp500_weekly_v1"
_CACHE_TTL_HOURS = 24


def _fetch_weekly_closes() -> list[dict[str, Any]]:
    """`^GSPC` 주간 종가를 `[{date, close}, ...]` 오름차순으로 돌려준다."""
    import yfinance as yf

    df = yf.Ticker("^GSPC").history(period="max", interval="1wk", auto_adjust=False)
    if df is None or df.empty or "Close" not in df.columns:
        return []

    out: list[dict[str, Any]] = []
    for idx, close in df["Close"].items():
        try:
            v = float(close)
        except (TypeError, ValueError):
            continue
        if v != v or v <= 0:  # NaN·비정상 종가는 버린다
            continue
        out.append({"date": idx.strftime("%Y-%m-%d"), "close": round(v, 2)})
    return out


def get_sp500() -> dict:
    """캐시 우선. 실패해도 예외를 올리지 않고 빈 시계열 + errors 로 돌려준다."""
    errors: list[str] = []

    cached = get_cached(_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("history"):
        return {"sp500": cached, "updated_at": now_kst_iso(), "errors": errors}

    history: list[dict[str, Any]] = []
    try:
        history = _fetch_weekly_closes()
    except Exception as e:  # 네트워크·yfinance 스키마 변경 등 전부 흡수
        logger.warning("S&P500 주간 종가 조회 실패: %s", e)
        errors.append(f"sp500: {e}")

    payload = {
        "history": history,
        "symbol": "^GSPC",
        "interval": "1wk",
        "first": history[0]["date"] if history else None,
        "last": history[-1]["date"] if history else None,
        "count": len(history),
    }
    if history:
        try:
            set_cached(_CACHE_KEY, payload, ttl_hours=_CACHE_TTL_HOURS)
        except Exception as e:  # 캐시 쓰기 실패가 응답을 죽이면 안 된다
            logger.warning("S&P500 캐시 저장 실패: %s", e)

    return {"sp500": payload, "updated_at": now_kst_iso(), "errors": errors}
