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
)
from src.db.trade_history import get_trades_in_range
from src.engine.market_regime import get_current_regime
from src.engine.recommendation_metrics import compute_metrics

# refactor B3 (2026-08-18) — 백테스트 오케스트레이션(5 함수 + 3 전역/상수) 이관.
# module-level 재export 로 기존 import 경로 전부 보존 (scheduler.py:3760 등).
# ⚠️ 재export 는 반드시 동일 객체 참조 — `_backtest_poll_loop_running` 같은 가변
# 컨테이너는 복사하면 scheduler `_reset_daily_state` 의 `.clear()` 가 무력화된다.
from src.engine.backtest_orchestration import (
    _backtest_poll_loop_running,
    _BACKTEST_POLL_INTERVAL_SECS,
    _BACKTEST_POLL_TIMEOUT_HOURS,
    _get_backtest_engine,
    _spawn_backtest_poll_task,
    _enqueue_backtest_jobs,
    _backtest_poll_loop,
    _emit_pending_summaries,
    # 기존 consumer 호환 (예: test_kojiro_wiring.py) — 이관 前엔 recommendation_engine.py
    # 에 직접 정의되어 있었다.
    _SUPPORTED_STRATEGIES,
    _FALLBACK_STRATEGIES,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 파라미터별 허용 범위 — LLM 출력 검증용
# 2026-05-17 Phase B: 5/15 첫 자문 code_review_notes 권고 반영 — VB/LTV 보드별 K값,
# donchian_swing 의 기간/거래량/ATR 트레일 등 8 키 화이트리스트 확장
# (min_prdy_rate 는 사이클 이전부터 등록되어 있어 중복 추가하지 않음).
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "stop_loss_rate": (-15.0, 0.0),
    "gap_up_threshold": (0.0, 30.0),
    "trailing_stop_rate": (-10.0, 0.0),
    "position_ratio": (0.01, 1.0),
    # `max_positions` 제외 (2026-08-03) — 동시보유 슬롯 수는 **리스크 정체성 상수**.
    # 키별 독립 범위만 검증하고 `position_ratio` 와의 곱을 교차검증하지 않아
    # 라이브에서 kojiro 10×0.20 / LTV 4×0.50 = 예산 200% 조합 사고가 났다
    # (계좌 전체 122.5% 초과 청약). 진입 임계를 AI 튜닝에서 뺀 선례와 동일 논리
    # (사이클 208 box 2키 / 209 max_breakout_extension_pct / 212 buy_threshold·donchian_period).
    "daily_loss_limit": (-20.0, 0.0),
    "k_period": (5, 60),
    "min_market_cap": (10_000_000_000, 10_000_000_000_000),
    "min_trade_amount": (1_000_000_000, 1_000_000_000_000),
    # cycle365 P5b — 상한 500 은 kojiro/BFB/VCP 운영 기본값 4000 을 못 담아
    # AI 자문이 그 3전략에 매일 500(유니버스 87% 축소)을 권고했다(도메인 자문
    # `_workspace/reports/2026-09-25_daily_and_advice_review.md` §5 P5).
    # 운영값(400~4000)을 전부 담도록 상한을 4000 으로 올린다.
    "max_scan_stocks": (10, 4000),
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
    "long_ma_period": (20, 120),
    "volume_multiplier": (1.0, 5.0),
    # `atr_trail_mult` 제외 (사이클 223, 2026-08-21) — 청산 임계는 전략의
    # **보유기간 정체성 상수**. 같은 청산축의 `breakeven_promote_atr`·`channel_exit_period`
    # 는 이미 미편입인데 이 키만 남아 코드 기본값 2.0 → 라이브 1.8 로 "더 타이트" 이탈했다.
    # 단기 손실을 목적함수로 삼는 튜너는 구조적으로 청산을 조여 추세추종을 데이트레이딩으로
    # 변태시킨다 (사이클 208 box 2키 / 209 max_breakout_extension_pct / 212 buy_threshold·
    # donchian_period 선례). 샹들리에는 19건 중 0회 발화 — 실행된 적 없는 파라미터를
    # 관측치로 맞추는 것은 튜닝이 아니다. 근거: `_workspace/domain_consult/donchian_exit_retune.md` C9.
    #
    # ⚠️ **적용 범위 = 3전략 공유 키** (사이클 223 F3, 리뷰 지적). `atr_trail_mult` 은
    # donchian 전용이 아니라 `donchian_swing` · `vcp_breakout` · `bull_flag_breakout`
    # 세 전략의 DEFAULT_PARAMS(전부 2.0)와 샹들리에 청산 분기가 **공유**한다. 따라서 이
    # 제거는 VCP·BFB 의 트레일링 배수까지 AI 튜닝에서 함께 뺀다 — 자문 이력에 두 전략의
    # `atr_trail_mult` 권고가 다수 존재한다. 오늘은 무해하다(VCP/BFB 체결 0건 = 튜닝할
    # 표본 자체가 없다). 다만 위 근거는 **donchian 실측(19왕복)만** 이므로, VCP/BFB 는
    # "자기 근거로 제외된" 것이 아니라 "표본이 없어 donchian 근거에 함께 묶인" 상태다.
    # **재검토 조건**: VCP 또는 BFB 의 청산 표본이 쌓이면(첫 체결 후 왕복 ≥20) 그 전략에
    # 한해 재편입 여부를 독립 판정한다 — donchian 표본만으로 두 전략의 청산 규약을
    # 영구 고정하지 않는다. 키 분리(전략 고유명)가 필요하면 `kojiro.py:151`
    # "atr_trail_mult 재사용 금지" 선례(`stop_atr`/`trail_atr` 고유명)를 따른다.
    # ↓ 사이클 23 — VCP 핵심 진입 품질 4 키
    "base_depth_pct": (0.10, 0.50),
    "volume_contraction_ratio": (0.30, 1.00),
    "breakout_volume_mult": (1.0, 5.0),  # BFB 도 동일 키 — VCP/BFB 공용
    "last_pullback_max": (0.03, 0.15),
    # ↓ 사이클 23 — P2 신규 가드/필터 5 키
    "breakout_retention_minutes": (1, 30),
    # `breakout_fail_n_days` 제외 (사이클 223, 2026-08-21) — 위 `atr_trail_mult` 와 동일
    # 논리. 라이브 값 2 는 구 범위 (2, 20) 의 **하한에 정확히** 붙어 있어 사이클 209
    # (`max_breakout_extension_pct` 3.0→하한 0.5 과튜닝) 와 동형 서명이다. 보유일수 임계를
    # 하한으로 밀면 20일 신고가 추세추종이 1~2일 데이트레이딩이 된다.
    # 적용 범위: `breakout_fail_n_days` 는 `donchian_swing` **단독** 키다
    # (위 `atr_trail_mult` 과 달리 공유 없음 — 제거가 다른 전략에 걸리지 않는다).
}

# 정수형 파라미터 — 캐스트 대상
# 2026-05-17 Phase B: donchian_period / long_ma_period 추가 (정수 일봉 개수)
INT_PARAMS = {
    "k_period",
    "max_scan_stocks",
    "exclude_consecutive_limit",
    "long_ma_period",
    # ↓ 사이클 23 — 정수 캐스트 대상
    "breakout_retention_minutes",
    # `breakout_fail_n_days` 는 사이클 223 에서 PARAM_RANGES 와 함께 제거 —
    # INT_PARAMS ⊆ PARAM_RANGES 규약 유지 (정체성 상수는 AI 튜닝 대상 아님).
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
    "- ⚠️ 레짐은 매매에 직접 개입하지 않는다(관찰 전용). buy_blocked 는 항상 false — 레짐이 defensive 여도 실제 매수는 차단되지 않으므로 매수 임계 튜닝은 유효하다. block_reason 은 우리 macro 컨테이너 레짐의 방어 '권고' 사유일 뿐이니, defensive 면 매수 파라미터를 보수적으로 권고하는 참고 신호로만 쓰고 매수 튜닝 자체를 스킵하지 마라\n"
    "- weight_reasoning 에 매크로 영향 (예: \"defensive 레짐 + buffett 1.45 → 보수적 비중\") 명시 권장\n"
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

    # ---- 교차 제약: position_ratio × max_positions ≤ 1.0 (전략 예산 불변식) ----
    # 키별 독립 범위 검증만으로는 조합 사고를 막지 못한다 (라이브 kojiro 0.20×10 /
    # LTV 0.50×4 = 예산 200%). `max_positions` 는 PARAM_RANGES 에서 제외됐으므로
    # 여기서 튜닝 가능한 축은 position_ratio 뿐 — 현재 슬롯 수 기준으로 거부한다.
    # 런타임 `_apply_budget_limit` 관문이 금전 피해는 이미 봉하지만, 초과 조합은
    # 마지막 슬롯이 상시 부분 매수로 잘리는 상태라 설정으로도 허용하지 않는다.
    if "position_ratio" in validated:
        try:
            max_pos = float(current_params.get("max_positions") or 0)
        except (TypeError, ValueError):
            max_pos = 0.0
        product = validated["position_ratio"] * max_pos
        if max_pos > 0 and product > 1.0 + 1e-9:
            logger.warning(
                "추천 거부 (전략 예산 초과 조합): position_ratio=%s × max_positions=%s "
                "= %.2f > 1.0",
                validated["position_ratio"], int(max_pos), product,
            )
            validated.pop("position_ratio")

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
# 사이클 23 P3-1+2 — AI 자문 자동 적용 (감액만 + 50% cap + 보수적 파라미터)
# ---------------------------------------------------------------------------
# 사이클 210 (2026-07-14) — auto_apply ratchet 차단: 손절/일일한도/비중 키를 자동적용 대상에서
# 전량 제외 → auto_apply 는 weight 감액만 잔존(param 단조 조임 방지, donchian 교살 재발 차단).
# 진입/청산 임계는 전략 정체성 상수 = 사람이 판단(208/209 선례). param 튜닝은 수동 apply 로만.
_CONSERVATIVE_KEYS: frozenset[str] = frozenset()

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
