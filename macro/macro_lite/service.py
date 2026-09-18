"""매크로 서비스 레이어 (macro_lite 추출본).

원본: 이 프로젝트 `services/macro_service.py` 중 5개 섹션(환율/원자재/수익률곡선/신용스프레드/
경기사이클+체제) + `get_sentiment` + `_events_for_history` 를 본문 그대로 복사.
교체: `macro_fetcher.` → `fetcher.`, `stock.macro_store` 일일 DB 캐시 → `.cache` daily 함수.
제외: 지수/뉴스/투자자 코멘트/섹터 히트맵/factor model/summary/prewarm/GPT 헬퍼.

- 부분 실패는 `errors` 배열로 반환 (HTTPException raise 없음).
- credit_spread 의 partial_failure(hy_oas/ig_oas) 캐시 폐기 로직 보존.
- determine_regime 에 previous_regime 을 전달하지 않는다 (원본 동일).
"""
from __future__ import annotations

import logging

from . import fetcher
from .cache import (
    get_today as get_macro_today,
    save_today as save_macro_today,
    delete_today as delete_macro_today,
    now_kst_iso,
)
from .cycle import determine_cycle_phase
from .events import get_events_in_range
from .regime import determine_regime

logger = logging.getLogger(__name__)


# ── 심리 지표 ────────────────────────────────────────────────────────────────

def get_sentiment() -> dict:
    """VIX + 버핏지수 + 공포탐욕 종합."""
    errors = []

    vix = None
    try:
        vix = fetcher.fetch_vix()
    except Exception as e:
        errors.append(f"VIX: {e}")

    buffett = None
    try:
        buffett = fetcher.calc_buffett_indicator()
    except Exception as e:
        errors.append(f"버핏지수: {e}")

    fear_greed = None
    try:
        fear_greed = fetcher.calc_fear_greed()
    except Exception as e:
        errors.append(f"공포탐욕: {e}")

    now = now_kst_iso()
    return {
        "vix": vix,
        "buffett_indicator": buffett,
        "fear_greed": fear_greed,
        "updated_at": now,
        "errors": errors,
    }


# ── 수익률곡선 ──────────────────────────────────────────────────────────────

def _events_for_history(history: list[dict]) -> dict:
    """history 시계열의 첫·끝 날짜로 NBER 침체 + S&P 약세장 이벤트 임베드.

    R2 (2026-05-04): 차트 ReferenceArea 음영 표시용.
    """
    if not history:
        return {"recessions": [], "bear_markets": []}
    try:
        dates = [r.get("date") for r in history if r.get("date")]
        if not dates:
            return {"recessions": [], "bear_markets": []}
        return get_events_in_range(min(dates), max(dates))
    except Exception as e:
        logger.debug("events 임베드 실패: %s", e)
        return {"recessions": [], "bear_markets": []}


def get_yield_curve() -> dict:
    """미국 국채 수익률곡선 — 현재값 + 시계열 + 역전 여부 + 침체/약세장 음영 데이터."""
    errors = []
    now = now_kst_iso()

    data = None
    try:
        data = fetcher.fetch_yield_curve_data()
    except Exception as e:
        errors.append(f"수익률곡선: {e}")

    # R2: 침체/약세장 이벤트 임베드 (차트 ReferenceArea 음영용)
    if isinstance(data, dict):
        history = data.get("history") or data.get("spread_history") or []
        data["events"] = _events_for_history(history)

    return {
        "yield_curve": data,
        "updated_at": now,
        "errors": errors,
    }


# ── 신용스프레드 ────────────────────────────────────────────────────────────

def get_credit_spread() -> dict:
    """HY OAS(FRED) + IG OAS 통합 신용스프레드. 일일 영속 캐시.

    하워드 막스 시계추 — 백분위 5단계 + OAS>10% 절대 안전장치 + 전 기간 baseline.
    """
    errors = []
    now = now_kst_iso()

    # 1) 일일 영속 캐시 (DB) — 같은 날 두 번째 호출은 외부 API 미호출
    cached = get_macro_today("credit_spread")
    if cached is not None:
        # 2026-05-05 fix: 캐시된 응답에 hy_oas/ig_oas partial_failure가 있으면
        # FRED_API_KEY 등록 후 새 fetch 시도하도록 캐시 폐기.
        cached_pf = set((cached or {}).get("partial_failure") or [])
        if any(p in cached_pf for p in ("hy_oas", "ig_oas")):
            logger.warning("credit_spread 캐시에 partial_failure 발견 → 폐기 후 재조회")
            try:
                delete_macro_today("credit_spread")
            except Exception as e:
                logger.warning("credit_spread 캐시 삭제 실패: %s", e)
            cached = None
        else:
            logger.debug("credit_spread 일일 캐시 hit")
            # R2: 캐시 응답에도 events 매번 재주입(정적 상수라 비용 0)
            cached["events"] = _events_for_history(cached.get("oas_history_5y") or cached.get("history") or [])
            return {
                "credit_spread": cached,
                "updated_at": now,
                "errors": [],
            }

    data = None
    try:
        data = fetcher.fetch_credit_spread()
    except Exception as e:
        errors.append(f"신용스프레드: {e}")

    # R2: 침체/약세장 이벤트 임베드
    if isinstance(data, dict):
        data["events"] = _events_for_history(data.get("oas_history_5y") or data.get("history") or [])

    # 캐시 저장 — 정상 응답이면서 핵심 데이터(hy_oas/ig_oas)가 빠지지 않은 경우만
    # (2026-05-05 fix: partial_failure 응답이 일일 캐시에 박혀 자정까지 잘못된 데이터
    #  표시되던 문제. FRED_API_KEY 등록 직후 즉시 새 fetch 시도하도록 변경.)
    pf = set((data or {}).get("partial_failure") or [])
    has_core_failure = any(p in pf for p in ("hy_oas", "ig_oas"))
    if data is not None and not errors and not has_core_failure:
        try:
            save_macro_today("credit_spread", data)
        except Exception as e:
            logger.warning("credit_spread 캐시 저장 실패: %s", e)

    return {
        "credit_spread": data,
        "updated_at": now,
        "errors": errors,
    }


# ── 환율 ────────────────────────────────────────────────────────────────────

def get_currencies() -> dict:
    """주요 환율 현재가 + 스파크라인. 병렬 수집."""
    errors = []
    now = now_kst_iso()

    currencies = []
    try:
        currencies = fetcher.fetch_currency_quotes()
    except Exception as e:
        errors.append(f"환율: {e}")

    return {
        "currencies": currencies,
        "updated_at": now,
        "errors": errors,
    }


# ── 원자재 ──────────────────────────────────────────────────────────────────

def get_commodities() -> dict:
    """주요 원자재 현재가 + 스파크라인. 병렬 수집."""
    errors = []
    now = now_kst_iso()

    commodities = []
    try:
        commodities = fetcher.fetch_commodity_quotes()
    except Exception as e:
        errors.append(f"원자재: {e}")

    return {
        "commodities": commodities,
        "updated_at": now,
        "errors": errors,
    }


# ── 매크로 사이클 ───────────────────────────────────────────────────────────

def get_macro_cycle() -> dict:
    """경기 사이클 국면 판단 (5지표 가중합산) + 투자 체제 판단.

    신용 통합 (2026-05-04):
    - cycle 입력에 oas_momentum_6m 자동 주입 (credit_spread 응답에서)
    - regime 판정에 hy_oas_percentile/value 자동 주입 → F&G 보정 + 신용 오버라이드
    """
    errors = []
    now = now_kst_iso()

    # credit_spread를 먼저 조회하여 cycle/regime 양쪽에 입력으로 주입
    hy_oas_percentile = None
    hy_oas_value = None
    oas_momentum_6m = None
    try:
        cs_resp = get_credit_spread()
        cs = cs_resp.get("credit_spread") or {}
        hy_oas_percentile = cs.get("oas_percentile")
        hy_oas_value = cs.get("oas_current")
        # 6개월 모멘텀: history_5y 마지막 값 vs 6개월 전 값 변화율(%)
        history_5y = cs.get("oas_history_5y") or cs.get("oas_history") or []
        if len(history_5y) >= 130:  # 약 6개월(주 단위 26 * 5 ≈ 130)
            cur = history_5y[-1].get("oas")
            past = history_5y[-130].get("oas")
            if cur and past and past != 0:
                oas_momentum_6m = round((cur - past) / past * 100, 1)
    except Exception as e:
        logger.debug("credit_spread 입력 주입 실패: %s", e)

    cycle = None
    try:
        inputs = fetcher.fetch_cycle_inputs()
        if oas_momentum_6m is not None:
            inputs["oas_momentum_6m"] = oas_momentum_6m
        cycle = determine_cycle_phase(inputs)
    except Exception as e:
        errors.append(f"경기사이클: {e}")

    regime = None
    try:
        sentiment = get_sentiment()
        regime = determine_regime(
            sentiment,
            hy_oas_percentile=hy_oas_percentile,
            hy_oas_value=hy_oas_value,
        )
    except Exception as e:
        errors.append(f"투자체제: {e}")

    return {
        "cycle": cycle,
        "regime": regime,
        "updated_at": now,
        "errors": errors,
    }
