"""cycle301 (2026-09-18) — VCP `DEFAULT_PARAMS` 3키를 운영 DB 실측값에 맞춘다.

무엇을 바꾸는가
===============
`src/engine/strategies/vcp_breakout.py` 의 `DEFAULT_PARAMS` **값 3개**뿐이다.

    ema_mid            60  → 150      (:147)
    ema_long          120  → 200      (:148)
    min_swing_atr_mult 0.5 → 1.0      (:167)

왜 값을 올리는가 — 완화가 아니라 결함 시정
==========================================
`50/150/200` 이 미너비니 Trend Template 원설계다. 코드의 `50/60/120` 은 일봉을
100행까지만 읽던 시절의 임시 회피책이고, `vcp_breakout.py:136-144` 주석이 스스로
그렇게 적고 있다("KIS 100일 한도로 계산 가능한 값으로 하향", "분할 fetch 로 진짜
120 을 계산하게 될 때의 목표값 의미로 보존"). cycle299(적재 깊이 225영업일)와
cycle300(읽기 클램프 400 + `daily_fetch_depth_mode`)이 그 한도를 걷어냈으므로
지금은 **운영 DB(150/200)가 맞고 코드가 낡았다**.

`min_swing_atr_mult` 은 0.5 쪽이 결함이다 — 임계를 낮추면 ZigZag 반전 회수가 2~4배가
되어 상한 `pullback_count_max=4` 를 넘고, 점진 수축 strict 단조(통과율 1/n!)가 무너져
Pullback 단계가 사실상 막힌다.

이 사이클의 핵심 주장 = **지금 운영의 매매 행위는 0 만큼 바뀐다**
=================================================================
`VcpBreakoutStrategy.__init__` 이 `merged = {**self.DEFAULT_PARAMS, **config.params}`
(`vcp_breakout.py:242`)이고 운영 DB `strategy_config.params` 에 세 키가 **전부**
존재한다(2026-09-15 실측 `ema_mid=150 ema_long=200 min_swing_atr_mult=1.0`).
따라서 코드 기본값은 DB 값에 완전히 가려져 실효가 0 이다 — G-301-1 이 그 merge 순서를
봉인하고(지금도 초록 = 회귀 가드), G-301-2 가 이 사이클이 실제로 바꾸는 유일한
표면(신규 배포·테스트 픽스처 = DB 키가 없을 때)을 잰다.

가드 매트릭스
=============
- G-301-1   DB 키가 있으면 DB 값이 이긴다 (merge 순서 봉인, 지금도 Green)
- G-301-1b  운영 DB 실측 3값이 그대로 인스턴스에 실린다 (실효 0 주장의 직접 표현)
- G-301-2   `DEFAULT_PARAMS` 가 150 / 200 / 1.0
- G-301-2b  DB 키 부재 시 인스턴스가 그 새 기본값을 쓴다
- G-301-3   새 기본값에서 `effective_ema_long` 이 보유 행 수를 따라간다 (225→200 · 100→75)
- G-301-3b  `full` 모드 요청 깊이가 새 `ema_long` 을 따라간다 (285봉, 클램프 400 이하)
- G-301-4   실효 장기선 200 에서 정렬 3선이 50/150/200 (중기선 재축소 미발동)

헬퍼는 cycle300 의 픽스처를 그대로 재사용한다
(`tests/unit/middleware/test_cycle249_reporter_scope.py` 가 같은 방식으로
`test_cycle243_api_auth` 를 import 하는 선례를 따른다).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.unit.engine.strategies.test_cycle300_daily_depth_switch import (
    _capture_prepare_fetch,
    _kis_candles,
    _make_vcp,
)

pytestmark = pytest.mark.unit

#: 운영 DB 의 VCP 값(2026-09-15 실측표). cycle301 이 코드 기본값을 여기에 맞춘다.
_LIVE_EMA_SHORT = 50
_LIVE_EMA_MID = 150
_LIVE_EMA_LONG = 200
_LIVE_MIN_SWING_ATR_MULT = 1.0

#: `prepare()` 본문의 `long_ema_uptrend_days` (이 사이클에서 바뀌지 않는다).
_UPTREND_DAYS = 20

#: cycle301 이 손대는 3키.
_KEYS = ("ema_mid", "ema_long", "min_swing_atr_mult")


# ===========================================================================
# G-301-1 — DB 키가 있으면 DB 값이 이긴다 (merge 순서 봉인)
# ===========================================================================
def test_g301_1_db_params_win_over_code_defaults():
    """무엇을 재는가: `config.params` 의 세 키가 `DEFAULT_PARAMS` 를 **이긴다**.

    `VcpBreakoutStrategy.__init__` 의 `merged = {**self.DEFAULT_PARAMS, **config.params}`
    순서가 이 사이클의 "운영 행위 변화 0" 주장의 전제다. 뒤집히면 코드 기본값이 운영
    DB 값을 덮어써 **배포 순간 진입 규칙이 바뀐다**.

    센티널 값(111 / 222 / 3.5)은 **현재 코드 기본값(60/120/0.5)과도, 이 사이클의 목표
    기본값(150/200/1.0)과도 다르다** — 목표값을 쓰면 Green 이후 단언이 공허해져
    merge 순서가 뒤집혀도 초록이 된다.
    """
    strat = _make_vcp(ema_mid=111, ema_long=222, min_swing_atr_mult=3.5)

    got = {k: strat.config.params[k] for k in _KEYS}
    assert got == {"ema_mid": 111, "ema_long": 222, "min_swing_atr_mult": 3.5}, (
        f"DB(config.params) 값이 코드 기본값에 덮였다: {got} — "
        "merge 순서 `{**DEFAULT_PARAMS, **config.params}` 가 뒤집혔다"
    )


def test_g301_1b_live_db_values_mask_code_defaults():
    """무엇을 재는가: 운영 DB 실측 3값이 그대로 인스턴스 파라미터가 된다(실효 0).

    운영 DB `strategy_config.vcp_breakout.params` 에 세 키가 전부 있으므로, 코드
    기본값이 60/120/0.5 이든 150/200/1.0 이든 살아 있는 전략이 읽는 값은 150/200/1.0
    하나다. 이 사이클의 배포가 **오늘 매매를 바꾸지 않는다**는 문장을 그대로 옮긴 것이다.
    """
    strat = _make_vcp(
        ema_short=_LIVE_EMA_SHORT,
        ema_mid=_LIVE_EMA_MID,
        ema_long=_LIVE_EMA_LONG,
        min_swing_atr_mult=_LIVE_MIN_SWING_ATR_MULT,
    )

    got = {k: strat.config.params[k] for k in _KEYS}
    assert got == {
        "ema_mid": _LIVE_EMA_MID,
        "ema_long": _LIVE_EMA_LONG,
        "min_swing_atr_mult": _LIVE_MIN_SWING_ATR_MULT,
    }, f"운영 DB 값이 인스턴스에 실리지 않았다: {got}"


# ===========================================================================
# G-301-2 — 새 기본값 (이 사이클이 실제로 바꾸는 유일한 표면)
# ===========================================================================
def test_g301_2_default_params_are_minervini_aligned():
    """무엇을 재는가: `DEFAULT_PARAMS` 세 값이 150 / 200 / 1.0 인가.

    DB 키가 없는 환경(신규 배포·테스트 픽스처·새 계정)에서 전략이 실제로 쓰는 값이다.
    `ema_short` 는 이 사이클의 범위 밖이므로 50 그대로임을 함께 확인해 변경 범위가
    정확히 3키임을 봉인한다.
    """
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    p = VcpBreakoutStrategy.DEFAULT_PARAMS
    got = {
        "ema_short": p["ema_short"],
        "ema_mid": p["ema_mid"],
        "ema_long": p["ema_long"],
        "min_swing_atr_mult": p["min_swing_atr_mult"],
    }
    assert got == {
        "ema_short": _LIVE_EMA_SHORT,
        "ema_mid": _LIVE_EMA_MID,
        "ema_long": _LIVE_EMA_LONG,
        "min_swing_atr_mult": _LIVE_MIN_SWING_ATR_MULT,
    }, (
        f"DEFAULT_PARAMS={got} — cycle301 은 ema_mid 60→150 · ema_long 120→200 · "
        "min_swing_atr_mult 0.5→1.0 (ema_short 는 무변경 50)"
    )


def test_g301_2b_absent_db_keys_use_new_defaults():
    """무엇을 재는가: `config.params` 에 세 키가 **없을 때** 인스턴스가 새 기본값을 쓴다.

    G-301-2 가 클래스 dict 를 보는 반면 이 테스트는 `__init__` 의 merge 를 통과한
    **인스턴스**를 본다 — 기본값이 실제로 전략에 도달하는지가 별개의 사실이기 때문이다.
    """
    overrides = {"max_scan_stocks": 10}
    assert set(overrides) & set(_KEYS) == set(), (
        "전제 붕괴 — 이 테스트의 오버라이드에 3키가 섞이면 기본값을 재지 못한다"
    )
    strat = _make_vcp(**overrides)

    got = {k: strat.config.params[k] for k in _KEYS}
    assert got == {
        "ema_mid": _LIVE_EMA_MID,
        "ema_long": _LIVE_EMA_LONG,
        "min_swing_atr_mult": _LIVE_MIN_SWING_ATR_MULT,
    }, f"DB 키 부재 시 인스턴스 값={got} (기대 150/200/1.0)"


# ===========================================================================
# G-301-3 — 새 기본값에서 effective_ema_long 이 보유 행 수를 따라간다
# ===========================================================================
@pytest.mark.asyncio
async def test_g301_3_effective_ema_long_follows_available_rows():
    """무엇을 재는가: 새 기본값으로 보유 225행 → 200, 보유 100행 → 75 인가.

    **측정 방식과 그 근거**: 산식을 테스트에 복제하지 않는다. 실제 `prepare()` 를
    돌리고 `_check_trend_filter` 를 스파이로 감싸 **prepare 본문(`vcp_breakout.py:429`)이
    계산해 넘긴 `effective_ema_long` 인자 자체**를 읽는다. 즉 여기서 재는 값은 정의상
    코드가 쓰는 값과 같고, 산식(`min(ema_long, available_len - uptrend_days - 5)`)이
    바뀌면 이 테스트가 함께 움직인다.

    `daily_fetch_depth_mode="full"` 을 주는 이유 = 225행은 `cap100` 모드(요청 100봉)로는
    실제로 도달할 수 없는 깊이라, full 모드가 이 표가 성립하는 유일한 현실 경로다
    (cycle300 이 연 스위치 — 세 키와는 무관한 별개 파라미터다).

    `_kis_candles(n)` 은 오늘 날짜 봉을 만들지 않으므로 `prev_idx=0`,
    `available_len == n` 이다.
    """
    observed: dict[int, int | None] = {}

    for rows in (225, 100):
        strat = _make_vcp(
            base_max_days=75,
            max_scan_stocks=10,
            daily_fetch_depth_mode="full",
        )
        seen_eff: list[int | None] = []
        real_filter = type(strat)._check_trend_filter

        # 기본 인자로 묶어 루프 변수 late-binding 을 차단한다.
        def _spy(self, candles, *, effective_ema_long=None,
                 _sink=seen_eff, _real=real_filter):
            _sink.append(effective_ema_long)
            return _real(self, candles, effective_ema_long=effective_ema_long)

        with patch.object(type(strat), "_check_trend_filter", new=_spy):
            await _capture_prepare_fetch(strat, _kis_candles(rows))

        assert seen_eff, f"보유 {rows}행에서 _check_trend_filter 가 불리지 않았다"
        observed[rows] = seen_eff[0]

    assert observed == {225: 200, 100: 75}, (
        f"effective_ema_long 표={observed} (기대 {{225: 200, 100: 75}}) — "
        "ema_long 기본값이 120 이면 225행에서도 120 에 묶인다"
    )


@pytest.mark.asyncio
async def test_g301_3b_full_mode_fetch_days_follows_new_default():
    """무엇을 재는가: `full` 모드 요청 깊이가 새 `ema_long` 을 따라 285봉이 되는가.

    `fetch_days = ema_long + base_max_days + 10` 이므로 200 + 75 + 10 = 285 다.
    cycle300 G-300-2 가 이미 "클램프 상한(`_MAX_DAILY_ROWS`)이 ema_long=200 의 full
    요청보다 크다" 를 봉인해 두었으므로, 기본값이 200 으로 올라가도 읽기 관문이 조용히
    자르지 않는다. `min_required` 는 두 모드 다 100 그대로다(KIS 폴백은 한 호출 100봉이
    상한이라 문턱을 올리면 더 얕은 응답으로 퇴보한다).
    """
    strat = _make_vcp(
        base_max_days=75,
        max_scan_stocks=10,
        daily_fetch_depth_mode="full",
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(240))

    assert seen["days"] == _LIVE_EMA_LONG + 75 + 10, (
        f"full 모드 fetch_days={seen['days']} (기대 285 = ema_long 200 + base_max 75 + 10)"
    )
    assert seen["min_required"] == 100, (
        f"min_required={seen['min_required']} (기대 100 — 이 사이클은 폴백 문턱을 건드리지 않는다)"
    )


# ===========================================================================
# G-301-4 — 실효 장기선 200 에서 정렬 3선이 50/150/200
# ===========================================================================
def test_g301_4_alignment_triplet_at_new_defaults():
    """무엇을 재는가: `effective_ema_long=200` 에서 실제 EMA 기간이 50/150/200 인가.

    `_check_trend_filter` 는 `ema_mid >= ema_long` 이면 중기선을
    `max(ema_short + 1, ema_long - 10)` 으로 재축소한다. 기본값 `ema_mid=150` 은
    200 보다 작으므로 그 재축소가 **발동하지 않고** 미너비니 원설계 정렬이 그대로 산다.
    기본값이 60 이면 같은 자리에서 50/60/200 이 되어 중기선이 장기선에서 140 이나
    떨어진 다른 전략이 된다.

    측정은 실제 `_check_trend_filter` 가 `_ema(...)` 에 넘긴 period 로 한다(cycle300
    G-300-7b 와 같은 방식). 호출 순서는 단기 → 중기 → 장기 → 장기(과거)이므로 앞 3개를 본다.
    """
    strat = _make_vcp(long_ema_uptrend_days=_UPTREND_DAYS)
    periods: list[int] = []

    def _spy_ema(series, period):
        periods.append(period)
        return 0.0

    with patch.object(strat, "_ema", new=_spy_ema):
        strat._check_trend_filter(
            _kis_candles(_LIVE_EMA_LONG + _UPTREND_DAYS + 5),
            effective_ema_long=_LIVE_EMA_LONG,
        )

    assert tuple(periods[:3]) == (_LIVE_EMA_SHORT, _LIVE_EMA_MID, _LIVE_EMA_LONG), (
        f"실효 정렬 {tuple(periods[:3])} (기대 (50, 150, 200))"
    )
