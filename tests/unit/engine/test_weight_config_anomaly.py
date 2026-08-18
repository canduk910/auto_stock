"""전략 비중 단위 계약 — `[weight_config_anomaly]` 오염 감지 회귀 가드 (B3 봉인).

배경 (2026-08-18): `strategy_config.weight` 는 **비율(0~1)** 계약인데 운영 DB 에
퍼센트 값(VB/LTV weight=1.0 이 아니라 100 의미로 저장 등)이 섞여 Σ=2.98 로 오염된
사례가 나왔다. 시정 산출물은 3종 —
  B1: `PUT /api/strategies/weights` validator (비율 범위 + Σ≤1, 422 한글 안내)
  B2: 프론트 배너/저장 차단
  B3: `scheduler._load_strategy_config` 부팅 시 오염 감지 WARNING

B3 은 **관찰 전용**이다. 자동 클램프·정규화를 절대 하지 않는다 (오염된 값을 조용히
그럴듯하게 만들면 운영자가 실측할 근거가 사라진다). 이 파일은 그 계약 전부를 봉인한다.

R-LOW-1 (적대적 리뷰) 시정 동반: 집계 범위를 **레지스트리 등록 전략 행**으로 좁혔다.
DB 에 은퇴 전략 stale row 가 남아도 실제 배분 Σ 와 무관하게 오탐하지 않아야 한다.
`enabled=False` 행은 계속 집계 대상 (weight>0 & enabled=False 도 오염 신호).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit

_SCHED_LOGGER = "src.engine.scheduler"
_MARKER = "[weight_config_anomaly]"


def _cfg(weight, enabled: bool = True, params: dict | None = None) -> dict:
    return {"enabled": enabled, "weight": weight, "params": params or {}}


def _clean_configs() -> dict[str, dict]:
    """정상 비율 계약 Σ=1.00 (등록 7 전략 전부)."""
    return {
        "kojiro": _cfg(0.60),
        "donchian_swing": _cfg(0.18),
        "bull_flag_breakout": _cfg(0.10),
        "vcp_breakout": _cfg(0.10),
        "volatility_breakout": _cfg(0.01),
        "long_tail_volatility": _cfg(0.01),
        "momentum": _cfg(0.0, enabled=False),
    }


def _polluted_configs() -> dict[str, dict]:
    """2026-08-18 실측 오염 — VB/LTV 가 퍼센트 오해로 1.0 저장, Σ=2.98."""
    cfgs = _clean_configs()
    cfgs["volatility_breakout"] = _cfg(1.0)
    cfgs["long_tail_volatility"] = _cfg(1.0)
    return cfgs


async def _load(configs: dict[str, dict], caplog) -> TradingScheduler:
    """`_load_strategy_config` 을 configs 로 1회 실행하고 scheduler 를 돌려준다."""
    sched = TradingScheduler()
    with patch("src.db.strategy_config.load_all", AsyncMock(return_value=configs)):
        with caplog.at_level(logging.WARNING, logger=_SCHED_LOGGER):
            await sched._load_strategy_config()
    return sched


def _anomaly_records(caplog) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records
        if r.name == _SCHED_LOGGER
        and r.levelno >= logging.WARNING
        and _MARKER in r.getMessage()
    ]


# ---------------------------------------------------------------------------
# 1 — 오염(Σ=2.98) 시 WARNING 발화 + 합계 노출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_anomaly_warning_emitted_when_sum_exceeds_one(caplog):
    await _load(_polluted_configs(), caplog)

    recs = _anomaly_records(caplog)
    assert len(recs) == 1, f"{_MARKER} WARNING 1회 기대, 실제 {len(recs)}회"
    msg = recs[0].getMessage()
    assert "sum=2.98" in msg, f"오염 합계 sum=2.98 노출 기대, 실제 메시지: {msg}"


# ---------------------------------------------------------------------------
# 2 — 정상(Σ=1.00) 시 미발화 (오탐 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_warning_when_sum_normal(caplog):
    await _load(_clean_configs(), caplog)

    recs = _anomaly_records(caplog)
    assert recs == [], f"정상 Σ=1.00 에서 오탐 금지, 실제: {[r.getMessage() for r in recs]}"


# ---------------------------------------------------------------------------
# 3 — 단일 전략 weight>1.0 이면 over_one 목록에 그 strategy_id 노출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_over_one_listed_when_single_strategy_exceeds(caplog):
    configs = _clean_configs()
    configs["kojiro"] = _cfg(1.5)

    await _load(configs, caplog)

    recs = _anomaly_records(caplog)
    assert len(recs) == 1, f"{_MARKER} WARNING 1회 기대, 실제 {len(recs)}회"
    msg = recs[0].getMessage()
    assert "kojiro" in msg, f"over_one 목록에 kojiro 기대, 실제 메시지: {msg}"


# ---------------------------------------------------------------------------
# 4 — 자동 클램프/정규화 절대 금지 (관찰 전용 계약)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_auto_clamp_weight_preserved(caplog):
    sched = await _load(_polluted_configs(), caplog)

    assert sched.registry.get("volatility_breakout").config.weight == 1.0, (
        "오염 weight 를 클램프/정규화하면 운영자가 실측할 근거가 사라진다 (관찰 전용 계약)"
    )
    assert sched.registry.get("long_tail_volatility").config.weight == 1.0
    assert sched.registry.get("kojiro").config.weight == 0.60
    assert sched.registry.get("donchian_swing").config.weight == 0.18


# ---------------------------------------------------------------------------
# 5 — R-LOW-1 회귀 가드: 레지스트리 미등록 stale row 는 집계 제외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unregistered_strategy_row_not_counted(caplog):
    """은퇴 전략 stale row(weight=1.0)가 DB 에 남아도 오탐 금지.

    적용 루프(`if not strategy: continue`)·`allocate_funds`(등록 전략만) 와 정합.
    """
    configs = _clean_configs()
    configs["retired_strategy"] = _cfg(1.0)
    assert TradingScheduler().registry.get("retired_strategy") is None, (
        "전제 위반 — retired_strategy 가 레지스트리에 등록되어 있으면 이 가드가 무의미"
    )

    await _load(configs, caplog)

    recs = _anomaly_records(caplog)
    assert recs == [], (
        f"미등록 stale row 는 실제 배분 Σ 에 기여하지 않으므로 오탐 금지, "
        f"실제: {[r.getMessage() for r in recs]}"
    )


# ---------------------------------------------------------------------------
# 6 — fail-open: 감지 블록이 로드 자체를 깨뜨리지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_survives_malformed_weight(caplog):
    """weight 가 숫자로 변환 불가한 문자열이어도 예외 전파 없이 로드 완료.

    감지 블록 내부 `float(...)` 이 ValueError 를 던지는 경로 = 신규 try/except 봉인.
    """
    configs = _clean_configs()
    configs["kojiro"] = _cfg("abc")

    sched = await _load(configs, caplog)

    assert sched._config_loaded is True, (
        "오염 감지는 관찰 부가물 — 파싱 실패가 전략 설정 로드를 무산시키면 안 된다"
    )


@pytest.mark.asyncio
async def test_none_weight_falls_back_to_defaults_documented(caplog):
    """weight=None 은 **적용 루프**(신규 블록 이전)에서 걸려 기본값 폴백 — 기존 계약 봉인.

    `logger.info(..., cfg["weight"] * 100)` 이 TypeError → 바깥 except 가 흡수해
    `_config_loaded=False` (다음 호출 재시도) + 기본값 사용. 이 폴백을 완화하면
    None weight 가 `allocate_funds` 까지 흘러가 더 나빠지므로 **의도적으로 유지**한다.
    신규 감지 블록은 이 지점에 도달조차 하지 않는다.
    """
    configs = _clean_configs()
    configs["kojiro"] = _cfg(None)

    sched = await _load(configs, caplog)

    assert sched._config_loaded is False, "None weight 는 기본값 폴백 (부분 적용 상태 재시도)"
    recs = _anomaly_records(caplog)
    assert recs == [], "적용 루프에서 이미 이탈 — 감지 블록 미도달"
