"""OpenAI 기반 파라미터 추천 엔진.

매일 16:00에 generate_recommendations()가 호출되어
전략별 통계 + 현재 파라미터를 OpenAI에 전달하고
JSON 응답을 화이트리스트 검증한 뒤 parameter_recommendations에 저장한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any

from src.config import settings
from src.db.daily_performance import get_performance
from src.db.parameter_recommendations import (
    expire_pending_before,
    insert_recommendation,
    list_recommendations_pending_backtest as _db_list_pending_backtest,
    update_backtest_summary as _db_update_backtest_summary,
)
from src.db.backtest_runs import (
    insert_run as _db_insert_run,
    list_by_date as _db_list_by_date,
    update_status as _db_update_status,
)
from src.db.trade_history import get_trades_in_range
from src.engine.market_regime import get_current_regime
from src.engine.recommendation_metrics import compute_metrics
from src.models.backtest import COMPARE_METRIC_KEYS, compute_metric_diff
from src.services.exceptions import (
    BacktestNotSupportedError,
    ConfigError,
    ExternalAPIError,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Phase 3 백테스트 통합 상수
# ---------------------------------------------------------------------------
# (a) 외부 MCP YAML DSL 지원 전략 — submit 대상
_SUPPORTED_STRATEGIES: frozenset[str] = frozenset(
    {"momentum", "volatility_breakout", "donchian_swing"}
)
# (b) 폴백 전략 — 즉시 skipped 마킹
_FALLBACK_STRATEGIES: frozenset[str] = frozenset(
    {"long_tail_volatility", "bull_flag_breakout", "vcp_breakout"}
)

# 폴 루프 주기 (테스트는 monkeypatch 로 0 으로 단축)
_BACKTEST_POLL_INTERVAL_SECS: int = 60
# 폴 루프 timeout — 24h 경과 시 미완료 row failed
_BACKTEST_POLL_TIMEOUT_HOURS: int = 24

# 중복 task 가드 — 동일 target_date 에 대해 폴 루프 task 중첩 차단
_backtest_poll_loop_running: set[date] = set()

# 파라미터별 허용 범위 — LLM 출력 검증용
# 2026-05-17 Phase B: 5/15 첫 자문 code_review_notes 권고 반영 — VB/LTV 보드별 K값,
# donchian_swing 의 기간/거래량/ATR 트레일 등 8 키 화이트리스트 확장
# (min_prdy_rate 는 사이클 이전부터 등록되어 있어 중복 추가하지 않음).
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "buy_threshold": (0.0, 30.0),
    "stop_loss_rate": (-15.0, 0.0),
    "gap_up_threshold": (0.0, 30.0),
    "trailing_stop_rate": (-10.0, 0.0),
    "position_ratio": (0.01, 1.0),
    "max_positions": (1, 20),
    "daily_loss_limit": (-20.0, 0.0),
    "k_period": (5, 60),
    "min_market_cap": (10_000_000_000, 10_000_000_000_000),
    "min_trade_amount": (1_000_000_000, 1_000_000_000_000),
    "max_scan_stocks": (10, 500),
    "min_prdy_rate": (0.0, 30.0),
    "exclude_consecutive_limit": (0, 5),
    "limit_up_threshold": (15.0, 30.0),
    "intraday_stop_loss": (-15.0, 0.0),
    "overnight_stop_loss": (-15.0, 0.0),
    # ↓ 2026-05-17 사이클 3 — VB 보드별 손절 분리 (PRE_NXT 노이즈 흡수 / KRX MAIN
    # 본격 변동성 수용). stop_loss_post_nxt 는 VB POST_NXT 미사용이라 제외 —
    # 사이클 3-B (LTV 보드 × 시간 모드 매트릭스) 에서 재검토.
    "stop_loss_main": (-15.0, 0.0),
    "stop_loss_pre_nxt": (-15.0, 0.0),
    # ↓ 2026-05-17 Phase B 확장 (VB/LTV/donchian_swing 권고 반영)
    "k_value_krx_main": (0.5, 2.0),
    "k_value_nxt_pre": (0.5, 2.0),
    "k_value_nxt_post": (0.5, 2.0),
    "donchian_period": (10, 60),
    "long_ma_period": (20, 120),
    "volume_multiplier": (1.0, 5.0),
    "atr_trail_mult": (1.0, 5.0),
    # ↓ 사이클 23 — VCP 핵심 진입 품질 4 키
    "base_depth_pct": (0.10, 0.50),
    "volume_contraction_ratio": (0.30, 1.00),
    "breakout_volume_mult": (1.0, 5.0),  # BFB 도 동일 키 — VCP/BFB 공용
    "last_pullback_max": (0.03, 0.15),
    # ↓ 사이클 23 — P2 신규 가드/필터 5 키
    "breakout_retention_minutes": (1, 30),
    "breakout_fail_n_days": (2, 20),
}

# 정수형 파라미터 — 캐스트 대상
# 2026-05-17 Phase B: donchian_period / long_ma_period 추가 (정수 일봉 개수)
INT_PARAMS = {
    "max_positions",
    "k_period",
    "max_scan_stocks",
    "exclude_consecutive_limit",
    "donchian_period",
    "long_ma_period",
    # ↓ 사이클 23 — 정수 캐스트 대상
    "breakout_retention_minutes",
    "breakout_fail_n_days",
}


SYSTEM_PROMPT = (
    "너는 한국 주식 자동매매 전략의 파라미터 튜닝을 보조하는 트레이더다.\n"
    "주어진 통계, 현재 파라미터, 그리고 다른 전략들의 자산배정(weight) + 성과를\n"
    "종합해 다음 4가지를 권고하라:\n"
    "1) 변경이 필요한 파라미터 키만 (필요 없으면 빈 객체)\n"
    "2) 자기 전략의 자산배정 weight 변경 권고 (0.0~1.0 범위, 변경 없으면 null).\n"
    "   다른 전략 weight + 성과를 함께 고려한다. 합계 1.0 정규화는 운영자가 apply 시점에 책임.\n"
    "3) weight 변경 권고 시 별도 사유 (weight_reasoning, 최대 1000자, 한국어).\n"
    "   recommended_weight 가 null 이면 null. 예: \"peer momentum 우수해 본 전략 비중 축소\",\n"
    "   \"최근 30일 손절률 증가로 보수적 비중 권고\". 통합 `reasoning` 과 별개로 명시.\n"
    "4) PARAM_RANGES 화이트리스트 외 신규 파라미터 도입 또는 폐기 자유 텍스트 자문\n"
    "   (code_review_notes, 최대 2000자, 변경 없으면 null). 코드 자동 변경 없이 운영자 수동 검토용.\n"
    "출력은 다음 JSON 스키마만 사용한다:\n"
    '{\n'
    '  "recommended_params": {<key>: <number>, ...},\n'
    '  "reasoning": "<2~4문장>",\n'
    '  "recommended_weight": <number 0.0~1.0> | null,\n'
    '  "weight_reasoning": "<최대 1000자>" | null,\n'
    '  "code_review_notes": "<최대 2000자>" | null\n'
    '}\n'
    "키는 반드시 현재 파라미터에 있는 키여야 하며, 허용 범위를 벗어나지 마라.\n"
    "\n"
    "시장 매크로 컨텍스트 활용 (user_payload 에 market_regime 가 있을 때만):\n"
    "- regime=defensive (현금 권고, VIX 25↑, 공포지수 극단): 손절률을 더 보수적으로 (절대값 작게) 조정,"
    " position_ratio 축소, daily_loss_limit 강화 권고\n"
    "- regime=neutral: 기존 파라미터 유지 또는 미세 조정\n"
    "- regime=aggressive (확장기, 낮은 VIX, 적정 fear_greed): 진입 임계 완화 또는 position_ratio 확대 가능"
    " (단, 변동성 큰 모멘텀류는 신중)\n"
    "- buy_blocked=True: 모든 전략 매수 차단된 상태. 매수 임계 변경 권고 무용 — 손절·청산·트레일링 파라미터만 권고\n"
    "- weight_reasoning 에 매크로 영향 (예: \"defensive 레짐 + VIX 28 → 보수적 비중\") 명시 권장\n"
    "- code_review_notes 에 매크로 의존 로직 도입 제안 가능 (예: VIX 25↑ 시 자동 매수 중단)"
)

NOTES_MAX_LEN = 2000
# 사이클 1 (2026-05-17) — weight_reasoning 최대 길이
WEIGHT_REASONING_MAX_LEN = 1000
# 사이클 1 (2026-05-17) — weight 있는데 weight_reasoning 누락 시 fallback
WEIGHT_REASONING_FALLBACK = "(사유 미제공)"


def _validate_recommendations(
    raw: dict,
    current_params: dict,
) -> tuple[dict, str, float | None, str | None, str | None]:
    """LLM 응답을 화이트리스트로 검증한다.

    Phase J4 (2026-05-12) — recommended_weight + code_review_notes 도입.
    사이클 1 (2026-05-17) — weight_reasoning 분리:
      - recommended_weight: float, [0.0, 1.0] 범위. 범위 외/비숫자면 None + WARNING
      - code_review_notes: str, NOTES_MAX_LEN(2000)자 초과 시 자름. 비-str 이면 None
      - weight_reasoning: str, WEIGHT_REASONING_MAX_LEN(1000)자 초과 시 자름.
          weight 가 null 이면 자동 null (정리)
          weight 있는데 weight_reasoning 누락/null/빈문자열/비-str → fallback `(사유 미제공)` + WARNING

    Returns:
        (검증된 recommended_params, reasoning, recommended_weight,
         code_review_notes, weight_reasoning)
    """
    rec = raw.get("recommended_params") or {}
    reasoning = str(raw.get("reasoning") or "").strip()
    validated: dict[str, Any] = {}
    if not isinstance(rec, dict):
        rec = {}

    for key, val in rec.items():
        if key not in current_params:
            logger.debug("추천 키 무시 (현재 params에 없음): %s", key)
            continue
        if key not in PARAM_RANGES:
            logger.debug("추천 키 무시 (허용 키 아님): %s", key)
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            logger.debug("추천 값 변환 실패: %s=%r", key, val)
            continue

        lo, hi = PARAM_RANGES[key]
        if num < lo or num > hi:
            logger.warning("추천 값 범위 초과: %s=%s (허용 [%s, %s])", key, num, lo, hi)
            continue

        # 정수 파라미터 캐스트
        if key in INT_PARAMS:
            num = int(round(num))

        # 변경 없는 값(현재값과 동일)은 의미 없음 — 단, 그대로 두면 프론트에서
        # 차이 표시 시 "변경 없음" 처리. 일단 포함시킨 뒤 클라이언트가 거른다.
        validated[key] = num

    # ---- recommended_weight 검증 ----
    raw_weight = raw.get("recommended_weight")
    weight: float | None = None
    if raw_weight is not None:
        try:
            w = float(raw_weight)
        except (TypeError, ValueError):
            logger.warning("추천 weight 변환 실패: %r — None 으로 무시", raw_weight)
            w = None
        if w is not None:
            if 0.0 <= w <= 1.0:
                weight = w
            else:
                logger.warning("추천 weight 범위 초과: %s (허용 [0.0, 1.0]) — None 으로 무시", w)

    # ---- code_review_notes 검증 ----
    raw_notes = raw.get("code_review_notes")
    notes: str | None = None
    if isinstance(raw_notes, str):
        if len(raw_notes) > NOTES_MAX_LEN:
            logger.warning(
                "code_review_notes %d자 → %d자로 자름", len(raw_notes), NOTES_MAX_LEN,
            )
            notes = raw_notes[:NOTES_MAX_LEN]
        else:
            notes = raw_notes
    elif raw_notes is not None:
        logger.debug("code_review_notes 비-str 무시: %r", type(raw_notes).__name__)

    # ---- weight_reasoning 검증 (사이클 1, 2026-05-17) ----
    raw_weight_reasoning = raw.get("weight_reasoning")
    weight_reasoning: str | None = None
    if weight is None:
        # weight 가 null 이면 weight_reasoning 도 무조건 null (자동 정리)
        weight_reasoning = None
    else:
        # weight 가 있는 경우 — 사유 필수
        if isinstance(raw_weight_reasoning, str) and raw_weight_reasoning.strip():
            if len(raw_weight_reasoning) > WEIGHT_REASONING_MAX_LEN:
                logger.warning(
                    "weight_reasoning %d자 → %d자로 자름",
                    len(raw_weight_reasoning), WEIGHT_REASONING_MAX_LEN,
                )
                weight_reasoning = raw_weight_reasoning[:WEIGHT_REASONING_MAX_LEN]
            else:
                weight_reasoning = raw_weight_reasoning
        else:
            # 누락/null/빈문자열/비-str → fallback + WARNING
            logger.warning(
                "weight_reasoning 누락 또는 형식 불일치 (raw=%r) — fallback %r 적용",
                raw_weight_reasoning, WEIGHT_REASONING_FALLBACK,
            )
            weight_reasoning = WEIGHT_REASONING_FALLBACK

    return validated, reasoning, weight, notes, weight_reasoning


async def _call_openai(
    strategy_name: str,
    strategy_description: str,
    current_params: dict,
    metrics: dict,
    current_weight: float | None = None,
    peer_weights: dict[str, float] | None = None,
    peer_metrics: dict[str, dict] | None = None,
) -> dict:
    """OpenAI API를 호출하여 JSON 응답을 받는다.

    Phase J4 (2026-05-12): 자기 전략 weight + 다른 전략 weight/성과 컨텍스트 추가 —
    자산배정 자문(`recommended_weight`) + 로직 자문(`code_review_notes`) 생성용.

    실패 시 빈 dict 반환.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다")
        return {}

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # 각 파라미터의 허용 범위(현재 params에 있는 키만)
    relevant_ranges = {
        k: PARAM_RANGES[k] for k in current_params.keys() if k in PARAM_RANGES
    }

    user_payload = {
        "strategy_name": strategy_name,
        "strategy_description": strategy_description,
        "current_params": current_params,
        "metrics": metrics,
        "param_ranges": {
            k: {"min": v[0], "max": v[1]} for k, v in relevant_ranges.items()
        },
        # Phase J4 — 자산배정 자문 컨텍스트
        "current_weight": current_weight,
        "peer_weights": peer_weights or {},
        "peer_metrics": peer_metrics or {},
    }

    # 사이클 4 (2026-05-17) — 매크로 레짐 → AI 자문 통합
    # graceful: 싱글톤이 None/empty 면 키 자체 미포함 → 사이클 1 8 필드 회귀 보존
    try:
        regime = get_current_regime()
    except Exception:
        logger.exception("get_current_regime 호출 실패 — market_regime 미포함")
        regime = None
    if regime is not None and not regime.is_empty():
        try:
            user_payload["market_regime"] = regime.to_advisor_dict()
        except Exception:
            logger.exception("to_advisor_dict 변환 실패 — market_regime 미포함")

    user_msg = (
        "아래는 전략 정보, 현재 파라미터, 최근 통계, 각 파라미터의 허용 범위,\n"
        "현재 자기 전략 weight, 다른 전략 weight + 성과다.\n"
        "이를 바탕으로 ①변경이 필요한 파라미터 키, ②자기 전략 weight 변경 권고,\n"
        "③화이트리스트 외 신규/폐기 파라미터 자유 텍스트 자문(최대 2000자) 을 JSON 으로 권고하라.\n\n"
        + json.dumps(user_payload, ensure_ascii=False, indent=2)
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_recommend_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        logger.exception("OpenAI API 호출 실패: %s", strategy_name)
        return {}

    try:
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except (json.JSONDecodeError, IndexError, AttributeError):
        logger.exception("OpenAI 응답 파싱 실패: %s", strategy_name)
        return {}


async def generate_recommendations() -> list[dict]:
    """매일 16:00에 호출. 전략별로 추천 생성·DB 저장.

    Returns:
        생성된(또는 이미 존재하는) 레코드 목록.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY 미설정 — 추천 건너뜀")
        return []

    target_date = datetime.now(KST).date()
    inserted: list[dict] = []

    # 어제 이전의 pending 추천을 expired로 마킹
    try:
        await expire_pending_before(target_date)
    except Exception:
        logger.exception("expire_pending_before 실패")

    # 순환 import 방지를 위해 함수 내부에서 import
    from src.engine.scheduler import trading_scheduler

    registry = trading_scheduler.registry

    # Phase J4 — peer 정보 사전 수집: 모든 enabled 전략의 weight + metrics 캐시
    peer_metrics_cache: dict[str, dict] = {}
    peer_weights_full: dict[str, float] = {}
    for s in registry.enabled():
        try:
            peer_weights_full[s.strategy_id] = float(s.config.weight)
            start_date = target_date - timedelta(days=30)
            p_trades = await get_trades_in_range(
                start_date, target_date, strategy=s.strategy_id,
            )
            p_perf = await get_performance(days=20, strategy=s.strategy_id)
            peer_metrics_cache[s.strategy_id] = compute_metrics(
                p_trades, p_perf, dict(s.config.params),
            )
        except Exception:
            logger.exception("peer metrics 수집 실패: %s", s.strategy_id)
            peer_metrics_cache[s.strategy_id] = {}

    for strategy in registry.enabled():
        strategy_id = strategy.strategy_id
        current_params: dict = {}
        metrics: dict = {}
        recommended_params: dict = {}
        reasoning = ""
        recommended_weight: float | None = None
        code_review_notes: str | None = None
        # 사이클 1 (2026-05-17) — 비중조절 사유 분리
        weight_reasoning: str | None = None
        try:
            current_params = dict(strategy.config.params)
            current_weight = float(strategy.config.weight)
            # 자기 전략 제외한 peer 만 전달
            peer_weights = {
                k: v for k, v in peer_weights_full.items() if k != strategy_id
            }
            peer_metrics = {
                k: v for k, v in peer_metrics_cache.items() if k != strategy_id
            }
            metrics = peer_metrics_cache.get(strategy_id) or {}
            if not metrics:
                # peer 캐시에 없으면(예외 등) 재계산
                start_date = target_date - timedelta(days=30)
                trades = await get_trades_in_range(
                    start_date, target_date, strategy=strategy_id,
                )
                performance = await get_performance(days=20, strategy=strategy_id)
                metrics = compute_metrics(trades, performance, current_params)
            logger.info(
                "추천 통계 [%s]: 거래 %d건, 승률 %.1f%%, 누적 %.2f%%",
                strategy_id,
                metrics.get("trades_count", 0),
                metrics.get("win_rate", 0) * 100,
                metrics.get("cumulative_return", 0),
            )

            # OpenAI 호출 (30초 타임아웃)
            try:
                raw = await asyncio.wait_for(
                    _call_openai(
                        strategy_name=strategy.config.name,
                        strategy_description=getattr(strategy, "__doc__", "") or strategy.config.name,
                        current_params=current_params,
                        metrics=metrics,
                        current_weight=current_weight,
                        peer_weights=peer_weights,
                        peer_metrics=peer_metrics,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("OpenAI 호출 타임아웃: %s", strategy_id)
                raw = {}

            (
                recommended_params,
                reasoning,
                recommended_weight,
                code_review_notes,
                weight_reasoning,
            ) = _validate_recommendations(raw, current_params)
        except Exception as e:
            logger.exception("파라미터 추천 생성 실패: %s", strategy_id)
            # 예외 발생 시에도 빈 자문 INSERT — 신규 탭에 누락 사실을 노출
            reasoning = f"자문 생성 중 예외 발생: {type(e).__name__}: {e}"

        # 모든 경로에서 INSERT 시도 (UNIQUE 충돌 시 None 반환 — 재실행 안전)
        try:
            row = await insert_recommendation(
                target_date=target_date,
                strategy_id=strategy_id,
                current_params=current_params,
                recommended_params=recommended_params,
                reasoning=reasoning,
                metrics=metrics,
                recommended_weight=recommended_weight,
                code_review_notes=code_review_notes,
                weight_reasoning=weight_reasoning,
            )
            if row:
                inserted.append(row)
        except Exception:
            logger.exception("파라미터 추천 INSERT 실패: %s", strategy_id)

    logger.info("파라미터 추천 생성 완료: %d/%d 전략", len(inserted), len(registry.enabled()))

    # Phase 3 (2026-05-16) — 자문 INSERT 직후 백테스트 enqueue (동기 await).
    # _enqueue_backtest_jobs 내부에서 fire-and-forget 으로 폴 루프 task 발화.
    # 예외 발생 시 자문 INSERT 보존 — 외부 try/except 로 분리 보호.
    if inserted:
        try:
            await _enqueue_backtest_jobs(target_date, inserted)
        except Exception:
            logger.exception("백테스트 enqueue 실패 — 자문 INSERT 는 보존")

    return inserted


# ---------------------------------------------------------------------------
# Phase 3 백테스트 통합 — enqueue + 폴 루프
# ---------------------------------------------------------------------------
def _get_backtest_engine():
    """싱글톤 lazy import. 테스트는 monkeypatch 로 치환."""
    from src.engine.backtest_engine import get_backtest_engine

    return get_backtest_engine()


def _spawn_backtest_poll_task(target_date: date) -> None:
    """폴 루프를 백그라운드 task 로 발화 — fire-and-forget.

    `asyncio.create_task` 가 안전한 이벤트 루프 안에서 호출되어야 하므로 호출자는
    이미 async 컨텍스트에 있어야 한다 (`_enqueue_backtest_jobs` 가 await 되는 동안).
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.error("백테스트 폴 루프 발화 실패 — 이벤트 루프 없음")
        return

    task = loop.create_task(_backtest_poll_loop(target_date))
    # 좀비 task 차단 — 완료 시 자동 로깅
    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            logger.warning("[backtest_poll] cancelled: target_date=%s", target_date)
            return
        exc = t.exception()
        if exc:
            logger.error("[backtest_poll] task failure: target_date=%s err=%r", target_date, exc)

    task.add_done_callback(_on_done)


async def _enqueue_backtest_jobs(
    target_date: date,
    inserted_recs: list[dict],
) -> None:
    """6 전략 × 2 kind = 12 backtest_runs row INSERT + (a) 전략은 BacktestEngine submit.

    매 row 의 lifecycle:
        queued → (a) running (submit 성공) | (b) skipped (YAML DSL 미지원) | failed (외부 오류)

    호출 순서:
    1. 모든 12 row INSERT (status=queued, params_snapshot 영속화).
    2. (b) 폴백 전략은 status='skipped' + 사유 영속화.
    3. KIS_MCP_ENABLED=false 면 (a) 도 즉시 'skipped' + '비활성' 사유.
    4. (a) 전략은 BacktestEngine.run_for_strategy 호출 → mcp_job_id 받아 'running' 전이.
       - BacktestNotSupportedError → 'skipped' (방어적 — _SUPPORTED_STRATEGIES 갱신 누락 대비)
       - ExternalAPIError / 기타 → 'failed' + error_message
    5. (a) submit 성공이 1건 이상이면 폴 루프 task 발화 (fire-and-forget).

    자문 INSERT 와 race 무관 — 본 함수는 enqueue 만 책임.
    """
    engine = _get_backtest_engine()
    enabled = bool(getattr(engine, "enabled", False))

    pending_run_jobs: list[tuple[dict, str]] = []  # (run_row, kind) for (a) submit

    for rec in inserted_recs:
        strategy_id = rec.get("strategy_id")
        if not strategy_id:
            continue
        current_params = dict(rec.get("current_params") or {})
        recommended_params = dict(rec.get("recommended_params") or {})

        for kind, snapshot in (
            ("current", current_params),
            ("recommended", recommended_params),
        ):
            try:
                run_row = await _db_insert_run(
                    target_date=target_date,
                    strategy_id=strategy_id,
                    params_kind=kind,
                    params_snapshot=snapshot,
                )
            except Exception:
                logger.exception(
                    "backtest_runs INSERT 실패: strategy=%s kind=%s", strategy_id, kind,
                )
                continue
            if not run_row:
                # UNIQUE 충돌 — 동일 사이클 재진입. 기존 row 가 있으니 skip.
                logger.info(
                    "backtest_runs INSERT skip (중복): strategy=%s kind=%s",
                    strategy_id, kind,
                )
                continue

            run_id = run_row["id"]

            # (b) 폴백 전략 — 즉시 skipped
            if strategy_id in _FALLBACK_STRATEGIES:
                try:
                    await _db_update_status(
                        run_id, "skipped",
                        error_message="YAML DSL 미지원 (Phase 4-bis 로컬 어댑터 대기)",
                    )
                except Exception:
                    logger.exception(
                        "backtest_runs skipped 갱신 실패: run_id=%s", run_id,
                    )
                continue

            # KIS_MCP_ENABLED=false — (a) 도 즉시 skipped
            if not enabled:
                try:
                    await _db_update_status(
                        run_id, "skipped",
                        error_message="MCP 비활성 (KIS_MCP_ENABLED=false)",
                    )
                except Exception:
                    logger.exception(
                        "backtest_runs MCP 비활성 skipped 갱신 실패: run_id=%s", run_id,
                    )
                continue

            # (a) 전략 — submit 대기 큐에 push
            pending_run_jobs.append((run_row, kind))

    # (a) submit 단계
    submit_success = 0
    for run_row, kind in pending_run_jobs:
        strategy_id = run_row["strategy_id"]
        snapshot = dict(run_row.get("params_snapshot") or {})
        try:
            job_id = await engine.run_for_strategy(
                strategy_id, snapshot, days=90, kind=kind,
            )
        except BacktestNotSupportedError as e:
            try:
                await _db_update_status(
                    run_row["id"], "skipped",
                    error_message=f"BacktestNotSupportedError: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs NotSupported skipped 갱신 실패: run_id=%s",
                    run_row["id"],
                )
            continue
        except (ExternalAPIError, ConfigError) as e:
            try:
                await _db_update_status(
                    run_row["id"], "failed",
                    error_message=f"{type(e).__name__}: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs failed 갱신 실패: run_id=%s", run_row["id"],
                )
            continue
        except Exception as e:
            try:
                await _db_update_status(
                    run_row["id"], "failed",
                    error_message=f"{type(e).__name__}: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs unexpected failed 갱신 실패: run_id=%s",
                    run_row["id"],
                )
            continue

        # running 전이 + mcp_job_id 매핑
        try:
            await _db_update_status(
                run_row["id"], "running", mcp_job_id=job_id,
            )
            submit_success += 1
        except Exception:
            logger.exception(
                "backtest_runs running 갱신 실패: run_id=%s", run_row["id"],
            )

    if submit_success > 0:
        _spawn_backtest_poll_task(target_date)
        logger.info(
            "[backtest_enqueue] target=%s submitted=%d (a)전략=%d (b)전략=%d enabled=%s",
            target_date, submit_success,
            len([r for r in inserted_recs if r.get("strategy_id") in _SUPPORTED_STRATEGIES]),
            len([r for r in inserted_recs if r.get("strategy_id") in _FALLBACK_STRATEGIES]),
            enabled,
        )
    else:
        logger.info(
            "[backtest_enqueue] target=%s submit=0 — 폴 루프 발화 skip (enabled=%s)",
            target_date, enabled,
        )


async def _backtest_poll_loop(target_date: date) -> None:
    """백그라운드 폴 루프 — `_BACKTEST_POLL_INTERVAL_SECS` 주기로 미완료 row 폴링.

    종료 조건:
    - 모든 target_date 의 backtest_runs row 가 종료 상태(completed/failed/skipped) + 모든
      6 전략 backtest_summary 동봉 완료.
    - 시작 후 `_BACKTEST_POLL_TIMEOUT_HOURS` 경과 — 미완료 row failed 마킹 후 종료.

    중복 task 가드: `_backtest_poll_loop_running` set 에 target_date 있으면 즉시 종료.
    """
    if target_date in _backtest_poll_loop_running:
        logger.info(
            "[backtest_poll] 이미 진행중 — skip duplicate: target=%s", target_date,
        )
        return

    _backtest_poll_loop_running.add(target_date)
    started_at = datetime.now(KST)
    summarized_rec_ids: set[str] = set()

    try:
        engine = _get_backtest_engine()

        while True:
            # 1) 미완료 backtest_runs row 폴링
            try:
                rows = await _db_list_by_date(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_by_date 실패")
                rows = []

            running_rows = [r for r in rows if r.get("status") == "running"]
            for row in running_rows:
                job_id = row.get("mcp_job_id")
                if not job_id:
                    # mcp_job_id 누락 — 비정상. failed 처리.
                    try:
                        await _db_update_status(
                            row["id"], "failed", error_message="mcp_job_id 누락",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] running mcp_job_id 누락 처리 실패: %s",
                            row["id"],
                        )
                    continue
                try:
                    metrics = await engine.poll(job_id)
                except (ExternalAPIError, ConfigError) as e:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=f"{type(e).__name__}: {e!s}",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] failed 갱신 실패: %s", row["id"],
                        )
                    continue
                except Exception as e:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=f"{type(e).__name__}: {e!s}",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] unexpected failed 갱신 실패: %s",
                            row["id"],
                        )
                    continue

                if metrics is None:
                    # 여전히 running — 다음 iteration 대기
                    continue
                # completed
                try:
                    await _db_update_status(
                        row["id"], "completed",
                        metrics=metrics.model_dump(exclude_none=False),
                    )
                except Exception:
                    logger.exception(
                        "[backtest_poll] completed 갱신 실패: %s", row["id"],
                    )

            # 2) 종료 상태 row 기반 backtest_summary 동봉
            await _emit_pending_summaries(target_date, summarized_rec_ids)

            # 3) 종료 조건 확인
            try:
                rows_after = await _db_list_by_date(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_by_date 재조회 실패")
                rows_after = rows

            terminal_states = {"completed", "failed", "skipped"}
            all_terminal = rows_after and all(
                r.get("status") in terminal_states for r in rows_after
            )

            try:
                pending_recs = await _db_list_pending_backtest(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_pending_backtest 실패")
                pending_recs = []

            # 이미 summary 동봉 완료된 rec_id 는 제외 (fake/실DB 동작 차이 둘 다 안전).
            active_pending = [
                r for r in pending_recs if r.get("id") not in summarized_rec_ids
            ]

            if all_terminal and not active_pending:
                logger.info(
                    "[backtest_poll] 모든 row 종료 + summary 동봉 완료 — exit: target=%s",
                    target_date,
                )
                return

            # 4) timeout 확인
            elapsed = datetime.now(KST) - started_at
            if elapsed >= timedelta(hours=_BACKTEST_POLL_TIMEOUT_HOURS):
                # 미완료 running/queued row 를 failed 로 마킹
                still_pending = [
                    r for r in rows_after
                    if r.get("status") in ("running", "queued")
                ]
                for row in still_pending:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=(
                                f"Timeout (>{_BACKTEST_POLL_TIMEOUT_HOURS}h)"
                            ),
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] timeout failed 갱신 실패: %s",
                            row["id"],
                        )
                # 마지막 한 번 더 summary 동봉 시도
                await _emit_pending_summaries(target_date, summarized_rec_ids)
                logger.warning(
                    "[backtest_poll] timeout — exit: target=%s pending=%d",
                    target_date, len(still_pending),
                )
                return

            # 5) 대기 후 재폴링
            await asyncio.sleep(_BACKTEST_POLL_INTERVAL_SECS)

    finally:
        _backtest_poll_loop_running.discard(target_date)


async def _emit_pending_summaries(
    target_date: date,
    summarized_rec_ids: set[str],
) -> None:
    """전략별 (current/recommended) 두 row 가 모두 종료 상태에 도달한 자문에 대해
    `parameter_recommendations.backtest_summary` 갱신.

    이미 갱신된 rec_id 는 ``summarized_rec_ids`` set 으로 중복 호출 차단.
    """
    try:
        rows = await _db_list_by_date(target_date)
    except Exception:
        logger.exception("[backtest_poll] emit_summaries list_by_date 실패")
        return
    try:
        pending_recs = await _db_list_pending_backtest(target_date)
    except Exception:
        logger.exception("[backtest_poll] emit_summaries list_pending 실패")
        return

    if not pending_recs:
        return

    # rows: run_id -> row dict
    # strategy_id -> {kind: row}
    by_strategy: dict[str, dict[str, dict]] = {}
    for row in rows:
        sid = row.get("strategy_id")
        kind = row.get("params_kind")
        if not sid or not kind:
            continue
        by_strategy.setdefault(sid, {})[kind] = row

    terminal_states = {"completed", "failed", "skipped"}

    for rec in pending_recs:
        rec_id = rec.get("id")
        if not rec_id or rec_id in summarized_rec_ids:
            continue
        rec_sid = rec.get("strategy_id")
        if not rec_sid:
            continue

        # 전체 6 전략 메트릭을 한꺼번에 동봉 — UI 가 자기 전략 + peer 비교 가능
        current_map: dict[str, Any] = {}
        recommended_map: dict[str, Any] = {}
        diff_map: dict[str, Any] = {}

        all_terminal_for_this_rec = True
        for sid, kinds in by_strategy.items():
            cur_row = kinds.get("current")
            rec_row = kinds.get("recommended")
            # 두 kind 가 모두 종료 상태여야 본 자문의 summary 진행
            if not cur_row or not rec_row:
                continue
            if (
                cur_row.get("status") not in terminal_states
                or rec_row.get("status") not in terminal_states
            ):
                # 자기 전략의 두 kind 가 아직 안 끝났으면 본 rec 의 summary 유예
                if sid == rec_sid:
                    all_terminal_for_this_rec = False
                continue
            # current
            if cur_row.get("status") == "completed" and cur_row.get("metrics"):
                current_map[sid] = dict(cur_row["metrics"])
            else:
                current_map[sid] = None
            # recommended
            if rec_row.get("status") == "completed" and rec_row.get("metrics"):
                recommended_map[sid] = dict(rec_row["metrics"])
            else:
                recommended_map[sid] = None
            # diff
            d = compute_metric_diff(current_map[sid], recommended_map[sid])
            diff_map[sid] = d if d else {}

        if not all_terminal_for_this_rec:
            continue

        # 자기 전략의 두 row 가 by_strategy 에 없으면 (예: INSERT 실패) skip
        own = by_strategy.get(rec_sid, {})
        if "current" not in own or "recommended" not in own:
            continue
        if (
            own["current"].get("status") not in terminal_states
            or own["recommended"].get("status") not in terminal_states
        ):
            continue

        summary = {
            "current": current_map,
            "recommended": recommended_map,
            "diff": diff_map,
        }
        try:
            await _db_update_backtest_summary(rec_id, summary)
            summarized_rec_ids.add(rec_id)
        except Exception:
            logger.exception(
                "[backtest_poll] backtest_summary 갱신 실패: rec_id=%s", rec_id,
            )


# ---------------------------------------------------------------------------
# 사이클 23 P3-1+2 — AI 자문 자동 적용 (감액만 + 50% cap + 보수적 파라미터)
# ---------------------------------------------------------------------------
# 보수적 파라미터 키 (자동 적용 허용 목록) — 손절/포지션 비율 계열만
_CONSERVATIVE_KEYS: frozenset[str] = frozenset({
    "stop_loss_rate",
    "position_ratio",
    "daily_loss_limit",
    "intraday_stop_loss",
    "overnight_stop_loss",
    "stop_loss_main",
    "stop_loss_pre_nxt",
})

# 음수 손절 키 — 절대값이 작을수록 보수적 (예: -7 → -5)
_STOP_LOSS_KEYS: frozenset[str] = frozenset({
    "stop_loss_rate",
    "intraday_stop_loss",
    "overnight_stop_loss",
    "stop_loss_main",
    "stop_loss_pre_nxt",
    "daily_loss_limit",
})

# 자동 적용 DB 함수
from src.db.strategy_config import save_weights, save_params


async def auto_apply_recommendations(target_date: date) -> dict:
    """20:00 AI 자문 직후 자동 적용 (감액만 + 50% cap + 보수적 파라미터만).

    사이클 23 P3-1+2. 핵심 안전 원칙:
    - auto_apply_enabled=False → 즉시 disabled 반환
    - recommended_weight < current_weight 만 자동 적용 (증액 SKIP)
    - 한 사이클 내 max 50% 감액 cap: new = max(recommended, current × 0.5)
    - PARAM_RANGES 화이트리스트 통과된 보수적 파라미터만 자동 적용
    - 영구 로그: [auto_weight_apply] / [auto_params_apply] /
                 [auto_apply_skip_increase] / [auto_apply_safeguard_skip]
    - status='applied_auto' (수동 'applied' 와 분리)

    Returns:
        {"applied": N, "skipped": M, "errors": [...]}
    """
    from src.db.parameter_recommendations import (
        list_pending_by_date,
        update_recommendation_status,
    )
    from src.db.system_config import get_auto_apply_enabled
    from src.db.system_logs import write_log

    # 1) 토글 확인
    enabled = await get_auto_apply_enabled()
    if not enabled:
        return {"applied": 0, "skipped": 0, "reason": "disabled"}

    # 2) target_date 의 pending 자문 목록 조회
    pending_recs = await list_pending_by_date(target_date)
    if not pending_recs:
        return {"applied": 0, "skipped": 0, "reason": "no_pending"}

    # 3) registry 에서 전략 객체 조회
    try:
        from src.engine.scheduler import trading_scheduler
        registry = trading_scheduler.registry
    except Exception as e:
        logger.exception("[auto_apply] registry 조회 실패")
        return {"applied": 0, "skipped": 0, "errors": [str(e)]}

    applied = 0
    skipped = 0
    errors: list[str] = []

    for rec in pending_recs:
        sid = rec.get("strategy_id") or ""
        rec_id = rec.get("id") or ""
        recommended_weight: float | None = rec.get("recommended_weight")
        recommended_params: dict = rec.get("recommended_params") or {}

        try:
            strategy = registry.get(sid)
            if strategy is None:
                logger.warning("[auto_apply] 전략 미발견: %s", sid)
                skipped += 1
                continue

            current_weight = float(strategy.config.weight)
            applied_weight: float | None = None
            auto_params: dict = {}

            # ① weight 자동 감액 (감액만, 증액 SKIP)
            if recommended_weight is not None:
                rw = float(recommended_weight)
                if rw >= current_weight:
                    # 증액 차단
                    await write_log(
                        "INFO",
                        f"[auto_apply_skip_increase] strategy={sid}"
                        f" recommended={rw} current={current_weight}",
                    )
                    skipped += 1
                    continue  # 이 자문 전체 skip (weight 증액이면 params 도 skip)

                # 50% cap 적용
                cap = current_weight * 0.5
                new_weight = max(rw, cap)

                await save_weights({sid: new_weight})
                strategy.config.weight = new_weight
                applied_weight = new_weight

                await write_log(
                    "INFO",
                    f"[auto_weight_apply] strategy={sid} prev={current_weight}"
                    f" new={new_weight} reason='recommended<current, cap={cap}'",
                )

            # ② params 보수적 자동 적용 (P3-2)
            for k, v in recommended_params.items():
                if k not in _CONSERVATIVE_KEYS:
                    continue  # 보수적 키만 처리
                if k not in PARAM_RANGES:
                    await write_log(
                        "INFO",
                        f"[auto_apply_safeguard_skip] key={k}"
                        f" reason='out_of_param_ranges'",
                    )
                    continue
                current_v = strategy.config.params.get(k)
                is_conservative = False
                if k in _STOP_LOSS_KEYS:
                    # 음수 키: 절대값 작아질수록 보수적 (예: -7 → -5: float(-5) > float(-7))
                    if current_v is not None and float(v) > float(current_v):
                        is_conservative = True
                elif k == "position_ratio":
                    # 양수 키: 작아질수록 보수적
                    if current_v is not None and float(v) < float(current_v):
                        is_conservative = True
                if is_conservative:
                    strategy.config.params[k] = v
                    auto_params[k] = v

            if auto_params:
                await save_params(sid, strategy.config.params)
                await write_log(
                    "INFO",
                    f"[auto_params_apply] strategy={sid}"
                    f" keys={list(auto_params.keys())} values={auto_params}",
                )

            # ③ status='applied_auto' 마킹
            await update_recommendation_status(
                rec_id,
                "applied_auto",
                applied_params=auto_params if auto_params else None,
                applied_weight=applied_weight,
            )
            applied += 1

        except Exception as e:
            logger.exception("[auto_apply] 처리 실패: strategy=%s", sid)
            errors.append(f"{sid}: {e!s}")

    return {"applied": applied, "skipped": skipped, "errors": errors}
