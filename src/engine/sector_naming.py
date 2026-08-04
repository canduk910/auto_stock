"""보유 종목 섹터명 해석 — 단일 진실원.

`routes/portfolio.py` 와 `log_analysis_engine.py` 가 동일 로직을 각자 들고 있었고,
잔고 응답(`routes/balance.py`)에도 섹터가 필요해지면서 세 번째 복사본이 생길
상황이라 한 곳으로 모은다. 행위는 사이클 H Phase 2a + 사이클 I 후속에서 확정된
우선순위 그대로 보존한다.

우선순위:
  1. `bstp_kor_isnm` — basics raw(CTPF1002R). 전 종목에 채워지는 **사람이 읽는**
     업종 한글명("유통"/"금융"/"전기·전자").
  2. `_kojiro_sector_key(master_raw)` — KRX 산업지수 플래그(반도체/바이오 등,
     프로그램 basket = 실 상관구조) → 업종 대분류코드 → 중분류.
     kojiro 섹터 캡과 **동일 소스**(함수 무변경).
  3. `미분류-{ticker}` — 독립 키. 클러스터에 포함시키지 않는 fail-open.

⚠️ `idx_bztp_lcls_cd_name`("시가총액규모중")은 섹터가 아니다 — 사용 금지.
⚠️ `get_master_raw` 는 16:30 배치 적재분만 있고 lazy fallback 이 없다. 미적재
   종목은 None → `미분류-{ticker}` (kojiro 섹터 캡과 동일한 fail-open).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from src.db import stock_master
from src.engine.strategies.kojiro import _kojiro_sector_key

logger = logging.getLogger(__name__)

_UNSET = object()


def _isnm_from_raw(raw: Any) -> str:
    """basics raw 에서 업종 한글명 추출 (공백만이면 부재 취급)."""
    if isinstance(raw, dict):
        return str(raw.get("bstp_kor_isnm", "") or "").strip()
    return ""


async def resolve_sector_name(ticker: str, *, basics_raw: Any = _UNSET) -> str:
    """단일 ticker 의 섹터명. 어떤 실패도 `미분류-{ticker}` 로 흡수한다.

    `basics_raw` 를 주면 `stock_master.get` 재조회를 생략한다 — 잔고 라우트처럼
    이미 basics 를 들고 있는 호출자의 중복 fetch 방지용.
    """
    try:
        if basics_raw is _UNSET:
            basics = await stock_master.get(ticker)
            raw = getattr(basics, "raw", None) if basics is not None else None
        else:
            raw = basics_raw
        name = _isnm_from_raw(raw)
        if name:
            return name
        master_raw = await stock_master.get_master_raw(ticker)
        return _kojiro_sector_key(
            master_raw if isinstance(master_raw, dict) else None, ticker
        )
    except Exception:
        logger.debug("[sector_naming] 섹터 조회 실패 graceful: %s", ticker, exc_info=True)
        return f"미분류-{ticker}"


async def resolve_sector_names(tickers: Iterable[str]) -> dict[str, str]:
    """복수 ticker → 섹터명 사전. 보유 종목 수는 통상 10 미만이라 순차 조회."""
    return {ticker: await resolve_sector_name(ticker) for ticker in tickers}
