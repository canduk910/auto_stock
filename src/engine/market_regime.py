"""시장 레짐 필터 + 매수 가드 (사이클 2, 2026-05-17).

dkstock.cloud 매크로 데이터를 기반으로:
1. **복합 임계 매수 가드** (1b): regime=defensive OR vix>25 OR fear_greed>85 OR fear_greed<15
2. **cash_usage_ratio 자동 산출** (2b): clamp((100 - cash_min) / 100, 0.0, 1.0)

매도/손절은 영향 없음 — 보유 종목 청산은 정상 작동 (risk.on_tick exit 분기 무관).

graceful fallback:
- 외부 fetch 실패/timeout/토큰 만료 시 ``MarketRegime.empty()`` 반환 → 매수 가드 비활성
  (기존 동작 유지). ``is_buy_allowed()`` 는 항상 True.
- ``DKSTOCK_REGIME_ENABLED=false`` 면 refresh() 가 즉시 empty 반환.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 복합 임계 (사용자 확정 옵션 1b)
_VIX_BLOCK_THRESHOLD = 25.0
_FEAR_GREED_GREED_THRESHOLD = 85.0  # > 85 극도 탐욕
_FEAR_GREED_FEAR_THRESHOLD = 15.0   # < 15 극도 공포


def cash_usage_ratio_from_regime(cash_min: int | float) -> float:
    """레짐 ``cash_min`` (현금 최소 비중 %, 0~100) → ``cash_usage_ratio`` 산출.

    공식: ``clamp((100 - cash_min) / 100, 0.0, 1.0)``.

    예시:
    - defensive (cash_min=75) → 0.25 (75% 현금 보유 권고 → 25% 매매 가용)
    - neutral (cash_min=50) → 0.50
    - aggressive (cash_min=20) → 0.80

    범위 외 입력은 clamp:
    - cash_min < 0 → 1.0
    - cash_min > 100 → 0.0
    """
    try:
        v = float(cash_min)
    except (TypeError, ValueError):
        return 1.0  # 안전 폴백 — 운영자 수동값 보존되도록 호출자가 결정
    ratio = (100.0 - v) / 100.0
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


@dataclass
class MarketRegime:
    """현재 시장 레짐 + 매수 가드 결정.

    빈 레짐(``empty()``)은 외부 fetch 실패 시 graceful 폴백 — 매수 가드 비활성.
    """

    regime: Optional[str] = None
    regime_desc: Optional[str] = None
    cycle_phase: Optional[str] = None
    vix: Optional[float] = None
    fear_greed_score: Optional[float] = None
    buffett_ratio: Optional[float] = None
    cash_min: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "MarketRegime":
        """외부 fetch 실패 / DKSTOCK 비활성 시 graceful 폴백."""
        return cls()

    @classmethod
    def from_macro_cycle(cls, macro: dict[str, Any]) -> "MarketRegime":
        """dkstock.cloud ``/api/macro/macro-cycle`` 응답 dict → MarketRegime.

        파싱 실패 키는 None 으로 채움 (부분 응답 graceful).
        """
        regime_obj = (macro or {}).get("regime") or {}
        cycle_obj = (macro or {}).get("cycle") or {}
        params_obj = regime_obj.get("params") or {}

        def _f(v) -> Optional[float]:
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def _i(v) -> Optional[int]:
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        return cls(
            regime=regime_obj.get("regime"),
            regime_desc=regime_obj.get("regime_desc"),
            cycle_phase=cycle_obj.get("phase"),
            vix=_f(regime_obj.get("vix")),
            fear_greed_score=_f(regime_obj.get("fear_greed_score")),
            buffett_ratio=_f(params_obj.get("pbr_max")) if params_obj.get("pbr_max") not in (None, 0) else None,
            cash_min=_i(params_obj.get("cash_min")),
            raw=dict(macro or {}),
        )

    # ------------------------------------------------------------------
    # 매수 가드 (1b) — 복합 임계 OR
    # ------------------------------------------------------------------
    @property
    def block_reason(self) -> Optional[str]:
        """매수 차단 사유 (복합 임계 OR). 안전 상태면 None."""
        # 1) regime defensive
        if self.regime == "defensive":
            return f"regime=defensive ({self.regime_desc or '방어 (공포 현금)'})"
        # 2) VIX > 25
        if self.vix is not None and self.vix > _VIX_BLOCK_THRESHOLD:
            return f"vix={self.vix:.2f} > {_VIX_BLOCK_THRESHOLD}"
        # 3) Fear & Greed 극단
        if self.fear_greed_score is not None:
            if self.fear_greed_score > _FEAR_GREED_GREED_THRESHOLD:
                return (
                    f"fear_greed_score={self.fear_greed_score:.2f} > "
                    f"{_FEAR_GREED_GREED_THRESHOLD} (극도 탐욕)"
                )
            if self.fear_greed_score < _FEAR_GREED_FEAR_THRESHOLD:
                return (
                    f"fear_greed_score={self.fear_greed_score:.2f} < "
                    f"{_FEAR_GREED_FEAR_THRESHOLD} (극도 공포)"
                )
        return None

    @property
    def buy_blocked(self) -> bool:
        return self.block_reason is not None

    def is_buy_allowed(self, strategy_id: str) -> bool:
        """전략 무관 매수 허용 여부. 차단 사유 1개 이상 → False.

        매도/손절은 본 결정 무관 — 호출자는 ``check_exit_signal`` 분기는 가드하지 않음.
        """
        return not self.buy_blocked

    # ------------------------------------------------------------------
    # 직렬화 (프론트 + DB)
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "regime_desc": self.regime_desc,
            "cycle_phase": self.cycle_phase,
            "vix": self.vix,
            "fear_greed_score": self.fear_greed_score,
            "buffett_ratio": self.buffett_ratio,
            "cash_min": self.cash_min,
            "buy_blocked": self.buy_blocked,
            "block_reason": self.block_reason,
        }

    def computed_cash_usage_ratio(self) -> Optional[float]:
        """레짐 ``cash_min`` 으로 자동 산출한 cash_usage_ratio. cash_min 없으면 None."""
        if self.cash_min is None:
            return None
        return cash_usage_ratio_from_regime(self.cash_min)


# ---------------------------------------------------------------------------
# 싱글톤 + 외부 fetch + DB INSERT 통합 헬퍼
# ---------------------------------------------------------------------------
_current_regime: MarketRegime = MarketRegime.empty()


def get_current_regime() -> MarketRegime:
    """현재 메모리 레짐. _boot 이전엔 empty() — 매수 가드 비활성."""
    return _current_regime


def set_current_regime(regime: MarketRegime) -> None:
    """_boot / 테스트 / API 가 호출. 동시성 단순화 — _boot 1회 호출 가정."""
    global _current_regime
    _current_regime = regime


async def refresh_from_dkstock() -> MarketRegime:
    """dkstock.cloud 매크로 fetch → MarketRegime 생성.

    외부 호출 실패 / 비활성 / 토큰 만료 시 ``MarketRegime.empty()`` 반환.
    호출자(scheduler._boot)는 결과 무관 graceful 진행.

    동작:
    1. ``DKSTOCK_REGIME_ENABLED=false`` → empty
    2. dkstock_client.get_macro_cycle() → from_macro_cycle 로 파싱
    3. 예외 (ExternalAPIError/ConfigError 등) → empty + WARNING 로그
    """
    from src.config import settings
    from src.services.dkstock_client import get_dkstock_client
    from src.services.exceptions import ConfigError, ExternalAPIError

    if not settings.dkstock_regime_enabled:
        logger.debug("[market_regime] DKSTOCK_REGIME_ENABLED=false → empty")
        return MarketRegime.empty()

    try:
        client = get_dkstock_client()
        macro = await client.get_macro_cycle()
    except (ConfigError, ExternalAPIError) as e:
        logger.warning(
            "[market_regime] dkstock.cloud fetch 실패 — 매수 가드 비활성: %s", e
        )
        return MarketRegime.empty()
    except Exception:
        logger.exception("[market_regime] 매크로 fetch 예외 — 매수 가드 비활성")
        return MarketRegime.empty()

    regime = MarketRegime.from_macro_cycle(macro)
    logger.info(
        "[market_regime] fetched regime=%s vix=%s fg=%s cash_min=%s buy_blocked=%s",
        regime.regime, regime.vix, regime.fear_greed_score,
        regime.cash_min, regime.buy_blocked,
    )
    return regime


async def persist_snapshot(regime: MarketRegime, target_date: date) -> None:
    """DB ``market_regime_snapshots`` 1행 INSERT. UNIQUE 충돌은 graceful skip."""
    # empty 레짐은 fetch 실패 폴백 → DB 저장 안 함 (감사 추적 의미 없음)
    if regime.regime is None:
        return
    from src.db import market_regime_snapshots as mrs

    try:
        await mrs.insert_snapshot(
            snapshot_date=target_date,
            regime=regime.regime,
            regime_desc=regime.regime_desc,
            cycle_phase=regime.cycle_phase,
            vix=regime.vix,
            fear_greed_score=regime.fear_greed_score,
            buffett_ratio=regime.buffett_ratio,
            raw_response=regime.raw,
            computed_cash_usage_ratio=regime.computed_cash_usage_ratio(),
            buy_blocked=regime.buy_blocked,
            block_reason=regime.block_reason,
        )
    except Exception:
        logger.exception("[market_regime] snapshot INSERT 실패 — 메모리 레짐은 유효")
