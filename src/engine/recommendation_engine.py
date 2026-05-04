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
from src.engine.recommendation_metrics import compute_metrics

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 파라미터별 허용 범위 — LLM 출력 검증용
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
}

# 정수형 파라미터 — 캐스트 대상
INT_PARAMS = {
    "max_positions",
    "k_period",
    "max_scan_stocks",
    "exclude_consecutive_limit",
}


SYSTEM_PROMPT = (
    "너는 한국 주식 자동매매 전략의 파라미터 튜닝을 보조하는 트레이더다.\n"
    "주어진 통계와 현재 파라미터를 보고, 변경이 필요한 키만 권고하라.\n"
    "필요 없으면 빈 객체를 반환하라.\n"
    "출력은 다음 JSON 스키마만 사용한다:\n"
    '{"recommended_params": {<key>: <number>, ...}, "reasoning": "<2~4문장>"}\n'
    "키는 반드시 현재 파라미터에 있는 키여야 하며, 허용 범위를 벗어나지 마라."
)


def _validate_recommendations(
    raw: dict,
    current_params: dict,
) -> tuple[dict, str]:
    """LLM 응답을 화이트리스트로 검증한다.

    Returns:
        (검증된 recommended_params, reasoning)
    """
    rec = raw.get("recommended_params") or {}
    reasoning = str(raw.get("reasoning") or "").strip()
    if not isinstance(rec, dict):
        return {}, reasoning

    validated: dict[str, Any] = {}
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

    return validated, reasoning


async def _call_openai(
    strategy_name: str,
    strategy_description: str,
    current_params: dict,
    metrics: dict,
) -> dict:
    """OpenAI API를 호출하여 JSON 응답을 받는다.

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
    }

    user_msg = (
        "아래는 전략 정보, 현재 파라미터, 최근 통계, 각 파라미터의 허용 범위다.\n"
        "이를 바탕으로 변경이 필요한 키만 JSON으로 권고하라.\n\n"
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

    for strategy in registry.enabled():
        strategy_id = strategy.strategy_id
        current_params: dict = {}
        metrics: dict = {}
        recommended_params: dict = {}
        reasoning = ""
        try:
            current_params = dict(strategy.config.params)

            # 데이터 수집 (영업일 20일 ≈ 달력 30일 여유)
            start_date = target_date - timedelta(days=30)
            trades = await get_trades_in_range(
                start_date, target_date, strategy=strategy_id,
            )
            performance = await get_performance(days=20, strategy=strategy_id)

            metrics = compute_metrics(trades, performance, current_params)
            logger.info(
                "추천 통계 [%s]: 거래 %d건, 승률 %.1f%%, 누적 %.2f%%",
                strategy_id,
                metrics["trades_count"],
                metrics["win_rate"] * 100,
                metrics["cumulative_return"],
            )

            # OpenAI 호출 (30초 타임아웃)
            try:
                raw = await asyncio.wait_for(
                    _call_openai(
                        strategy_name=strategy.config.name,
                        strategy_description=getattr(strategy, "__doc__", "") or strategy.config.name,
                        current_params=current_params,
                        metrics=metrics,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("OpenAI 호출 타임아웃: %s", strategy_id)
                raw = {}

            recommended_params, reasoning = _validate_recommendations(
                raw, current_params,
            )
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
            )
            if row:
                inserted.append(row)
        except Exception:
            logger.exception("파라미터 추천 INSERT 실패: %s", strategy_id)

    logger.info("파라미터 추천 생성 완료: %d/%d 전략", len(inserted), len(registry.enabled()))
    return inserted
