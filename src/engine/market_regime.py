"""시장 레짐 필터 + 매수 가드 (사이클 2, 2026-05-17).

dkstock.cloud 매크로 데이터를 기반으로:
1. **복합 임계 매수 가드** (1b): regime=defensive OR vix>25 OR fear_greed>85 OR fear_greed<15
2. **cash_usage_ratio 자동 산출** (2b): clamp((100 - cash_min) / 100, 0.0, 1.0)

매도/손절은 영향 없음 — 보유 종목 청산은 정상 작동 (risk.on_tick exit 분기 무관).

graceful fallback:
- 외부 fetch 실패/timeout/토큰 만료 시 ``MarketRegime.empty()`` 반환 → 매수 가드 비활성
  (기존 동작 유지). ``is_buy_allowed()`` 는 항상 True.
- ``DKSTOCK_REGIME_ENABLED=false`` 면 refresh() 가 즉시 empty 반환.

**사이클 8 (2026-05-18)** — 4 모드(OFF/WARN/SOFT/HARD) + 4 임계값 운영자 조정:
- ``get_buy_block_state()`` async 메서드가 DB 모드+임계 조회 후 BuyBlockState 반환
- ``is_buy_allowed()`` 동기 API 는 보존 — 하드코딩 임계로 평가 (회귀 가드)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 사이클 11 (2026-05-18) — buy_block_state 60s TTL 캐시
# ---------------------------------------------------------------------------
# 매수 신호 평가 직전 `get_buy_block_state()` 호출이 매번 supabase 5 키를 fetch 하던
# 결함(분당 ~1,800 DB 쿼리) 차단. 운영 UI 토글(`PUT /api/integrations/buy-block`) 시
# `invalidate_buy_block_cache()` 로 즉시 무효화. TTL 60s 는 운영 반영 지연 허용
# 범위 + DB 부하 180배 감소의 균형점.
BUY_BLOCK_CACHE_TTL = 60.0


# ---------------------------------------------------------------------------
# 사이클 8 (2026-05-18) — DB 헬퍼 위임 (단위 테스트 monkeypatch 진입점)
# ---------------------------------------------------------------------------
async def _db_get_buy_block_mode() -> str:
    """`src.db.system_config.get_buy_block_mode` 위임. 테스트에서 monkeypatch."""
    from src.db.system_config import get_buy_block_mode

    return await get_buy_block_mode()


async def _db_get_buy_block_thresholds():
    """`src.db.system_config.get_buy_block_thresholds` 위임. 테스트에서 monkeypatch."""
    from src.db.system_config import get_buy_block_thresholds

    return await get_buy_block_thresholds()


@dataclass
class BuyBlockState:
    """사이클 8 (2026-05-18) — 매수 가드 현재 상태.

    risk.on_tick 의 매수 분기가 본 객체로 4 모드별 행동 분기:
    - mode=HARD + blocked=True → execute_buy skip
    - mode=WARN + blocked=True → execute_buy 발사 + WARNING 로그
    - mode=SOFT + blocked=True → execute_buy 발사 + soft_multiplier 전달 (수량 ×0.5)
    - mode=OFF → blocked 평가 자체 안 함 (reasons=[], blocked=False)

    UI/로그 표시용으로 `reasons` 에 모든 발동 사유 수집 (HARD/WARN/SOFT 공통).
    """

    mode: str
    blocked: bool
    soft_multiplier: float
    reasons: List[str] = field(default_factory=list)
    # 사이클 D (2026-07-31) — 레짐 가드 silent inert 가시화 (관찰성 전용).
    # 매크로 데이터 실제 유입 여부. False 여도 blocked/soft_multiplier 는 fail-open
    # 보존(변경 없음) — 데이터 없을 때 매수 차단 전환(fail-safe)은 범위 외 인계.
    data_available: bool = True


# 복합 임계 (사용자 확정 옵션 1b)
_VIX_BLOCK_THRESHOLD = 25.0
_FEAR_GREED_GREED_THRESHOLD = 85.0  # > 85 극도 탐욕
_FEAR_GREED_FEAR_THRESHOLD = 15.0   # < 15 극도 공포

# ---------------------------------------------------------------------------
# 사이클 4 (2026-05-17) — OpenAI 자문 user_payload 용 정량 분류 임계
# ---------------------------------------------------------------------------
# VIX 임계: low(<15) / normal(15~25) / elevated(25~35) / high(>=35)
_VIX_LOW_MAX = 15.0
_VIX_NORMAL_MAX = 25.0
_VIX_ELEVATED_MAX = 35.0
# Fear & Greed 임계: 극공포(<15) / 공포(15~35) / 중립(35~65) / 탐욕(65~85) / 극탐욕(>=85)
_FG_EXTREME_FEAR_MAX = 15.0
_FG_FEAR_MAX = 35.0
_FG_NEUTRAL_MAX = 65.0
_FG_GREED_MAX = 85.0


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

    # 사이클 11 (2026-05-18) — buy_block_state 60s TTL 캐시 (인스턴스 단위)
    # dataclass `__eq__` / `__hash__` / 직렬화에는 영향 없음 (compare=False, repr=False).
    _buy_block_cache: Optional["BuyBlockState"] = field(
        default=None, compare=False, repr=False,
    )
    _buy_block_cache_expires_at: float = field(
        default=0.0, compare=False, repr=False,
    )

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

        **사이클 8 보존**: 본 동기 API 는 하드코딩 임계 평가 — DB 미설정 시 회귀 가드
        + 매크로 자문 user_payload(``to_advisor_dict``) 내 ``buy_blocked`` 필드 호환.
        4 모드 분기는 ``get_buy_block_state()`` 비동기 메서드 + risk.on_tick 사용.
        """
        return not self.buy_blocked

    # ------------------------------------------------------------------
    # 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계 조정
    # ------------------------------------------------------------------
    def _collect_reasons(self, *, vix_thr: float, fg_high_thr: float,
                         fg_low_thr: float, defensive_enabled: bool) -> List[str]:
        """4 임계 OR 평가 — 발동 사유 모두 수집 (사이클 2 의 `block_reason` 단일과 다름).

        OFF 모드는 본 함수 호출하지 않음 (가드 평가 자체 비활성).
        """
        reasons: List[str] = []
        # 1) regime=defensive (defensive_enabled 토글)
        if defensive_enabled and self.regime == "defensive":
            reasons.append(
                f"regime=defensive ({self.regime_desc or '방어 (공포 현금)'})"
            )
        # 2) VIX
        if self.vix is not None and self.vix > vix_thr:
            reasons.append(f"vix={self.vix:.2f} > {vix_thr:.2f}")
        # 3) Fear & Greed 고/저
        if self.fear_greed_score is not None:
            if self.fear_greed_score > fg_high_thr:
                reasons.append(
                    f"fear_greed_score={self.fear_greed_score:.2f} > "
                    f"{fg_high_thr:.2f} (극도 탐욕)"
                )
            if self.fear_greed_score < fg_low_thr:
                reasons.append(
                    f"fear_greed_score={self.fear_greed_score:.2f} < "
                    f"{fg_low_thr:.2f} (극도 공포)"
                )
        return reasons

    @property
    def has_regime_data(self) -> bool:
        """사이클 D (2026-07-31) — 실제 매크로 데이터 보유 여부.

        `regime`/`vix`/`fear_greed_score` 중 1개라도 not None 이거나 `raw` 가
        비어있지 않으면 True. `empty()` 폴백(외부 fetch 실패/비활성)은 전부 None +
        raw={} 라서 False — `persist_snapshot` 의 `regime is None` empty 판정과 정합.

        `get_buy_block_state()` 가 `BuyBlockState.data_available` 세팅에 사용
        (관찰성 전용 — blocked/soft_multiplier 평가 로직과 무관).
        """
        return (
            self.regime is not None
            or self.vix is not None
            or self.fear_greed_score is not None
            or bool(self.raw)
        )

    def invalidate_buy_block_cache(self) -> None:
        """캐시 즉시 무효화 — 운영 UI Settings PUT 시 호출.

        `PUT /api/integrations/buy-block` 응답 끝에서 호출되면 운영자 변경이 다음 매수
        신호부터 즉시 반영. 호출 안 하면 TTL 만료(60s) 까지 캐시된 옛 모드/임계 사용.
        """
        self._buy_block_cache = None
        self._buy_block_cache_expires_at = 0.0

    async def get_buy_block_state(self) -> "BuyBlockState":
        """DB 모드+임계 조회 후 4 모드 분기로 매수 가드 상태 결정.

        - mode=OFF: 가드 평가 자체 비활성 (reasons=[], blocked=False, multiplier=1.0)
        - mode=HARD + reasons 있음: blocked=True (매수 차단), multiplier=1.0
        - mode=WARN + reasons 있음: blocked=False (매수 허용), multiplier=1.0 (로그만)
        - mode=SOFT + reasons 있음: blocked=False (매수 허용), multiplier=0.5
        - reasons 없음(empty regime / 모든 임계 미발동): blocked=False, multiplier=1.0

        외부 fetch 실패 시 empty regime — 모든 모드에서 reasons=[], blocked=False (graceful).
        DB 미설정 → HARD + 기본 임계 (현재 동작 회귀 보존).

        **사이클 11 (2026-05-18) — 60s TTL 캐시**: 매수 신호 평가 직전 DB 5 키 fetch
        하던 결함(분당 ~1,800 쿼리) 차단. 캐시 hit 시 DB 호출 0 회 + 즉시 반환.
        TTL 만료/명시 무효화 시 정상 fetch. **DB 폴백 분기는 캐시 미저장** — 운영
        UI 가 정상 갱신 후에도 폴백 결과 영구 캐시되어 새 임계 미반영되는 결함 차단.
        """
        # 캐시 hit — TTL 유효
        now = time.monotonic()
        if (
            self._buy_block_cache is not None
            and now < self._buy_block_cache_expires_at
        ):
            return self._buy_block_cache

        # DB fetch — 예외 시 폴백 분기 (캐시 저장 안 함)
        db_ok = True
        try:
            mode = await _db_get_buy_block_mode()
        except Exception:
            logger.exception("[buy_block_state] mode 조회 실패 — HARD fallback")
            mode = "HARD"
            db_ok = False

        # OFF 모드는 임계 조회 skip (DB 쿼리 1회 절약)
        if mode == "OFF":
            state = BuyBlockState(
                mode="OFF",
                blocked=False,
                soft_multiplier=1.0,
                reasons=[],
                data_available=self.has_regime_data,
            )
            # OFF 는 DB ok 만 캐시 (모드 fetch 실패 폴백 시 다음 호출에서 재시도)
            if db_ok:
                self._buy_block_cache = state
                self._buy_block_cache_expires_at = now + BUY_BLOCK_CACHE_TTL
            return state

        try:
            thresholds = await _db_get_buy_block_thresholds()
        except Exception:
            logger.exception(
                "[buy_block_state] thresholds 조회 실패 — 기본 25/85/15/true fallback"
            )
            from src.db.system_config import BuyBlockThresholds
            thresholds = BuyBlockThresholds()
            db_ok = False

        reasons = self._collect_reasons(
            vix_thr=thresholds.vix_threshold,
            fg_high_thr=thresholds.fg_high_threshold,
            fg_low_thr=thresholds.fg_low_threshold,
            defensive_enabled=thresholds.defensive_enabled,
        )

        triggered = len(reasons) > 0
        if mode == "HARD":
            state = BuyBlockState(
                mode="HARD",
                blocked=triggered,
                soft_multiplier=1.0,
                reasons=reasons,
                data_available=self.has_regime_data,
            )
        elif mode == "WARN":
            # 매수 허용 + WARNING 로그 (risk.on_tick 책임)
            state = BuyBlockState(
                mode="WARN",
                blocked=False,
                soft_multiplier=1.0,
                reasons=reasons,
                data_available=self.has_regime_data,
            )
        elif mode == "SOFT":
            state = BuyBlockState(
                mode="SOFT",
                blocked=False,
                soft_multiplier=0.5 if triggered else 1.0,
                reasons=reasons,
                data_available=self.has_regime_data,
            )
        else:
            # 알 수 없는 mode — 안전 fallback HARD
            logger.warning(
                "[buy_block_state] unknown mode=%r — HARD fallback", mode,
            )
            state = BuyBlockState(
                mode="HARD",
                blocked=triggered,
                soft_multiplier=1.0,
                reasons=reasons,
                data_available=self.has_regime_data,
            )

        # 사이클 11 — DB ok 만 캐시 (폴백 분기 결과는 영구 캐시 오염 차단)
        if db_ok:
            self._buy_block_cache = state
            self._buy_block_cache_expires_at = now + BUY_BLOCK_CACHE_TTL
        return state

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

    # ------------------------------------------------------------------
    # 사이클 4 (2026-05-17) — OpenAI 자문 user_payload 통합
    # ------------------------------------------------------------------
    def is_empty(self) -> bool:
        """현재 인스턴스가 empty 상태인지 — 모든 핵심 필드가 None 이면 True.

        클래스메소드 ``MarketRegime.empty()`` (팩토리) 와 이름 충돌 회피를 위해
        ``is_empty()`` 로 분리. 외부 호출자는 ``regime.is_empty()`` 로 graceful 판정.
        ``regime.regime is None`` 단독 판정과 동치 (다른 필드들도 None 인 경우만 empty).
        """
        return (
            self.regime is None
            and self.regime_desc is None
            and self.cycle_phase is None
            and self.vix is None
            and self.fear_greed_score is None
            and self.buffett_ratio is None
            and self.cash_min is None
        )

    def _classify_vix(self) -> Optional[str]:
        """VIX 정성 분류 — low/normal/elevated/high. vix=None 이면 None."""
        if self.vix is None:
            return None
        if self.vix < _VIX_LOW_MAX:
            return "low"
        if self.vix < _VIX_NORMAL_MAX:
            return "normal"
        if self.vix < _VIX_ELEVATED_MAX:
            return "elevated"
        return "high"

    def _classify_fear_greed(self) -> Optional[str]:
        """Fear & Greed 정성 분류 — 극공포/공포/중립/탐욕/극탐욕. score=None 이면 None."""
        if self.fear_greed_score is None:
            return None
        if self.fear_greed_score < _FG_EXTREME_FEAR_MAX:
            return "극공포"
        if self.fear_greed_score < _FG_FEAR_MAX:
            return "공포"
        if self.fear_greed_score < _FG_NEUTRAL_MAX:
            return "중립"
        if self.fear_greed_score < _FG_GREED_MAX:
            return "탐욕"
        return "극탐욕"

    def to_advisor_dict(self) -> dict[str, Any]:
        """OpenAI 자문 user_payload 용 정량+정성 컨텍스트 dict.

        raw / raw_response / 원본 cash_min 같은 내부·대용량 필드는 제외.
        cash_min 은 ``cash_min_recommended`` 키명으로 노출하고,
        ``raw.regime.params.stock_max`` 가 있으면 ``stock_max_recommended`` 로 함께.

        Returns 11+1 = 12 키 dict:
            regime / regime_desc / cycle_phase / vix / vix_level /
            fear_greed_score / fear_greed_label / buffett_ratio /
            buy_blocked / block_reason /
            cash_min_recommended / stock_max_recommended
        """
        stock_max: Optional[int] = None
        try:
            stock_max_raw = (
                (self.raw or {}).get("regime", {}).get("params", {}).get("stock_max")
            )
            if stock_max_raw is not None:
                stock_max = int(stock_max_raw)
        except (TypeError, ValueError, AttributeError):
            stock_max = None

        return {
            "regime": self.regime,
            "regime_desc": self.regime_desc,
            "cycle_phase": self.cycle_phase,
            "vix": self.vix,
            "vix_level": self._classify_vix(),
            "fear_greed_score": self.fear_greed_score,
            "fear_greed_label": self._classify_fear_greed(),
            "buffett_ratio": self.buffett_ratio,
            "buy_blocked": self.buy_blocked,
            "block_reason": self.block_reason,
            "cash_min_recommended": self.cash_min,
            "stock_max_recommended": stock_max,
        }


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


# ---------------------------------------------------------------------------
# 사이클 E-1 (2026-07-31) — 지수ETF 고지로 스테이지 레짐 신호 (관찰 전용 다크런치)
# ---------------------------------------------------------------------------
# 자문: `_workspace/domain_consult/cycle_etf_kojiro_regime_20260731.md` (GO).
# dkstock 매크로와 별개로 지수ETF(KODEX200/코스닥150)의 고지로 대순환 스테이지를
# 관찰 — E-1 범위는 계산 + 로그 + API 노출까지. block_reason 통합/SOFT 상한/reasons
# 태깅은 E-2(2주 관찰 후) 인계 — 매수 가드 행위(blocked/soft_multiplier/reasons)는
# 본 절과 무관하게 완전 보존.

# 방어집합 = 하락 사분면 전체 (자문 §Q2 정본). kojiro_indicators._STAGE_MAP 참조:
# 1 안정상승 / 2 상승후조정 / 3 하락전환 / 4 안정하락 / 5 하락후반등 / 6 상승전환.
DEFENSIVE_STAGES = frozenset({3, 4, 5})

ETF_KOSPI_TICKER = "069500"    # KODEX 200
ETF_KOSDAQ_TICKER = "229200"   # KODEX 코스닥150

# stock_master_daily 조회 lookback — EMA40 안정화에 충분한 여유 (kojiro 5/20/40 답습)
_ETF_STAGE_LOOKBACK_DAYS = 90
# 최신 bas_dd 가 이보다 오래되면(달력일) stale — 주말+공휴일 안전 마진
ETF_STALE_MAX_CALENDAR_DAYS = 10


def is_two_day_defensive(stages: "List[Optional[int]]") -> bool:
    """최근 2 스테이지(``stages[-2:]``) 가 모두 ``DEFENSIVE_STAGES`` 에 속하면 True.

    히스테리시스 확인 — 단일일 방어 진입은 미확정. ``len(stages) < 2`` 또는
    최근 2개 중 ``None`` 포함 시 False.
    """
    if len(stages) < 2:
        return False
    last_two = stages[-2:]
    if any(s is None for s in last_two):
        return False
    return all(s in DEFENSIVE_STAGES for s in last_two)


@dataclass(frozen=True)
class EtfStageSignal:
    """지수ETF 고지로 스테이지 관찰 신호 (사이클 E-1).

    ``etf_defensive`` 는 신선(non-stale) 지수들의 ``*_defensive_2d`` OR 결합.
    양쪽 모두 stale 이면 신호 없음(``None``).
    """

    kospi_stage: Optional[int]
    kosdaq_stage: Optional[int]
    kospi_defensive_2d: bool
    kosdaq_defensive_2d: bool
    etf_defensive: Optional[bool]
    stale_kospi: bool
    stale_kosdaq: bool


def _is_daily_row_stale(latest_bas_dd: Any, now: datetime) -> bool:
    """최신 ``bas_dd`` 가 ``ETF_STALE_MAX_CALENDAR_DAYS`` 초과 오래되면 stale.

    ``date``/``datetime``/ISO 문자열 모두 수용 (never-raise, 파싱 실패 → stale).
    """
    if latest_bas_dd is None:
        return True
    bas_dd = latest_bas_dd
    if isinstance(bas_dd, datetime):
        bas_dd = bas_dd.date()
    if not isinstance(bas_dd, date):
        try:
            bas_dd = date.fromisoformat(str(bas_dd)[:10])
        except (TypeError, ValueError):
            return True
    return (now.date() - bas_dd).days > ETF_STALE_MAX_CALENDAR_DAYS


async def _compute_single_etf_stage(
    ticker: str, now: datetime,
) -> "tuple[Optional[int], bool, bool]":
    """단일 ETF 티커 → (최종 스테이지, 2일 방어 판정, stale 여부).

    일봉 소스 seam = ``stock_master_daily.get_recent_daily`` (테스트 monkeypatch
    진입점). 5/20/40 = kojiro 정체성 상수 — ETF 전용 파라미터화 금지.
    """
    from src.db import stock_master_daily as smd

    rows = await smd.get_recent_daily(ticker, _ETF_STAGE_LOOKBACK_DAYS)
    if not rows:
        return None, False, True

    if _is_daily_row_stale(rows[0].get("bas_dd"), now):
        return None, False, True

    import pandas as pd

    from src.engine import kojiro_indicators as ki

    rows_asc = sorted(rows, key=lambda r: r.get("bas_dd"))
    closes = pd.Series([float(r.get("close_price")) for r in rows_asc])

    cfg = ki.KojiroIndicatorConfig()
    ema_s = ki.ema(closes, cfg.ema_short)
    ema_m = ki.ema(closes, cfg.ema_mid)
    ema_l = ki.ema(closes, cfg.ema_long)

    stages: List[Optional[int]] = []
    prev: Optional[int] = None
    for s, m, l in zip(ema_s, ema_m, ema_l):
        prev = ki.stage_of(s, m, l, prev)
        stages.append(prev)

    final_stage = stages[-1] if stages else None
    defensive_2d = is_two_day_defensive(stages)
    return final_stage, defensive_2d, False


async def compute_etf_stage_signal(*, now: Optional[datetime] = None) -> EtfStageSignal:
    """KODEX200(069500) + KODEX코스닥150(229200) 일봉 → 고지로 스테이지 신호.

    사이클 E-1 (2026-07-31) — 관찰 전용. dkstock 성패와 무관하게 독립 계산
    (호출자 = ``scheduler._refresh_market_regime_and_persist``).
    """
    if now is None:
        from src.db._kst import KST
        now = datetime.now(KST)

    kospi_stage, kospi_def, stale_kospi = await _compute_single_etf_stage(
        ETF_KOSPI_TICKER, now,
    )
    kosdaq_stage, kosdaq_def, stale_kosdaq = await _compute_single_etf_stage(
        ETF_KOSDAQ_TICKER, now,
    )

    if stale_kospi and stale_kosdaq:
        etf_defensive: Optional[bool] = None
    else:
        etf_defensive = (
            (not stale_kospi and kospi_def) or (not stale_kosdaq and kosdaq_def)
        )

    return EtfStageSignal(
        kospi_stage=kospi_stage,
        kosdaq_stage=kosdaq_stage,
        kospi_defensive_2d=kospi_def,
        kosdaq_defensive_2d=kosdaq_def,
        etf_defensive=etf_defensive,
        stale_kospi=stale_kospi,
        stale_kosdaq=stale_kosdaq,
    )


_current_etf_signal: Optional[EtfStageSignal] = None


def get_current_etf_signal() -> Optional[EtfStageSignal]:
    """현재 메모리 ETF 스테이지 신호. boot 이전엔 None (관찰 전용 다크런치)."""
    return _current_etf_signal


def set_current_etf_signal(sig: Optional[EtfStageSignal]) -> None:
    """boot(``_refresh_market_regime_and_persist``) / 테스트 / API 가 호출."""
    global _current_etf_signal
    _current_etf_signal = sig
