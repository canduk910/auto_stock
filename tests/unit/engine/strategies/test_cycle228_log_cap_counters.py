"""cycle228-A (RED) — 진동 로그 상태 전이화(A5) + 마커·카운터 승계(A6).

## A5 — 로그가 진단을 덮은 실측

2026-08-26 하루: **"BFB 돌파 1차 감지" 247행 + "BFB 돌파 후퇴" 226행 = 473행**,
그런데 **고유 종목은 4개**다. 종목당 118행. 257720 한 종목이 142회 진동했다.
P1-3 이 기록한 대로 이 로그가 실제로 진단을 방해했다.

시정은 **cap 이지 문구 변경이 아니다** — `"BFB 돌파 1차 감지"` / `"BFB 돌파 후퇴"`
한글 리터럴은 **byte 보존**한다(운영자 grep 이력 단절 차단, H-1 F4 `_HIGH_RECOVER_LABEL`
선례). cap 만 씌우고 총량은 무cap `_scan_stats` 카운터로 보존한다.

⚠️ **cap 키에 전이 종류를 포함**해야 한다 — cycle225 교훈: 키가 `ticker` 단독이면
먼저 발생한 전이가 나중 전이를 삼켜, 원인이 다른 사건이 같은 침묵으로 뭉개진다.

## A6 — 관측 훅 은퇴

`[*_vol_gate_observe]` 는 **은퇴**한다. 같은 마커에서 `would_pass=True` 의 매매
귀결이 정반대로 뒤집히기 때문이다:

| | cycle227 | cycle228 |
|---|---|---|
| `would_pass=True` | "고쳤다면 샀을 것" = **안 샀다** | **샀다** |

마커를 유지하면 경계일을 모르는 사람이 과거 로그를 grep 해서 **없던 체결을 있었다고
읽는다.** 연속성이 보존할 이력은 로그 5행뿐이라 오독 위험이 훨씬 비싸다.
"""

from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

BFB_LOGGER = "src.engine.strategies.bull_flag_breakout"
VCP_LOGGER = "src.engine.strategies.vcp_breakout"

TICKER = "001450"
FLAG_HIGH = 51_000
FLAG_LOW = 48_000
FLAG_AVG_VOLUME = 202_133.0
BFB_THRESHOLD = 404_266

BASE_HIGH = 12_000
BASE_LOW = 10_500
VCP_THRESHOLD = 450_000

_NEW_COUNTERS = (
    "vol_gate_pass",
    "vol_gate_reject_ext",
    "vol_gate_no_data",
    "latch_armed_count",
    "breakout_seen_count",
    "breakout_retreat_count",
)
_RETIRED_COUNTERS = (
    "vol_gate_observe_pass",
    "vol_gate_observe_fail",
    "vol_gate_observe_no_obs",
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _bfb(retention_minutes: int = 0) -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15)
    )
    s.config.params["breakout_retention_minutes"] = retention_minutes
    s._candidates[TICKER] = {
        "pole_start": 40_000, "pole_high": 50_000,
        "flag_high": FLAG_HIGH, "flag_low": FLAG_LOW,
        "flag_avg_volume": FLAG_AVG_VOLUME,
        "pole_len": 5, "flag_len": 3, "atr14": 900, "prev_close": 50_600,
    }
    return s


def _vcp() -> VcpBreakoutStrategy:
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.10)
    )
    s._candidates[TICKER] = {
        "base_high": BASE_HIGH, "base_low": BASE_LOW, "last_pullback_pct": 0.05,
        "atr14": 200, "ema50": 11_500, "ema150": 11_000, "ema200": 10_800,
        "prev_close": 11_900, "avg_volume_20": 300_000,
    }
    return s


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ###########################################################################
# A5 — 진동 로그 cap + 한글 문구 byte 보존
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_a5_oscillation_logs_capped_but_counters_keep_total(caplog):
    """A5 — 100회 왕복 → 로그 각 **1행**, 카운터는 **100**.

    8/26 실측 473행이 여기 대응한다. cap 이 총량까지 지우면 진동 규모를 다시는
    측정할 수 없으므로 카운터는 무cap 이다(cycle227 `vol_gate_observe_*` 선례).
    """
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(retention_minutes=3)

    for _ in range(100):
        strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)   # 감지
        strat.check_buy_signal(TICKER, FLAG_HIGH - 500, 50_600)   # 후퇴

    assert len(_lines(caplog, "BFB 돌파 1차 감지")) == 1, "감지 로그 cap 미작동"
    assert len(_lines(caplog, "BFB 돌파 후퇴")) == 1, "후퇴 로그 cap 미작동"

    stats = strat.get_scan_stats()
    assert stats["breakout_seen_count"] == 100
    assert stats["breakout_retreat_count"] == 100


@freeze_time("2026-08-27 10:00:00")
def test_a5_korean_literals_are_byte_preserved(caplog):
    """A5 — 한글 문구 **byte 보존**. 운영자 grep 이력이 끊기면 안 된다."""
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(retention_minutes=3)

    strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)
    strat.check_buy_signal(TICKER, FLAG_HIGH - 500, 50_600)

    seen = _lines(caplog, "BFB 돌파 1차 감지")[0]
    retreat = _lines(caplog, "BFB 돌파 후퇴")[0]
    assert seen.startswith("BFB 돌파 1차 감지(retention 대기 시작): 001450 flag_high(51000)")
    assert retreat.startswith("BFB 돌파 후퇴(retention 대기 종료): 001450")


@freeze_time("2026-08-27 10:00:00")
def test_a5_cap_key_separates_transition_kinds(caplog):
    """A5 — cap 키에 **전이 종류**가 들어가야 한다 (cycle225 교훈).

    키가 `ticker` 단독이면 먼저 난 감지가 나중의 후퇴를 삼켜, 원인이 다른 두 사건이
    같은 침묵으로 뭉개진다.
    """
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(retention_minutes=3)

    strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)
    strat.check_buy_signal(TICKER, FLAG_HIGH - 500, 50_600)

    assert len(_lines(caplog, "BFB 돌파 1차 감지")) == 1
    assert len(_lines(caplog, "BFB 돌파 후퇴")) == 1, (
        "감지가 후퇴를 삼켰다 — cap 키가 ticker 단독이다"
    )


def test_a5_oscillation_log_cap_resets_on_date_change(caplog):
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(retention_minutes=3)

    with freeze_time("2026-08-27 10:00:00"):
        strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)
    with freeze_time("2026-08-28 10:00:00"):
        strat._prev_price[TICKER] = FLAG_HIGH - 100
        strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)

    assert len(_lines(caplog, "BFB 돌파 1차 감지")) == 2


# ###########################################################################
# A6 — `_scan_stats` 키 교체 + `_empty_scan_stats` 동기
# ###########################################################################

@pytest.mark.parametrize("factory", [_bfb, _vcp], ids=["bfb", "vcp"])
def test_a6_new_counters_present_from_fresh_instance(factory):
    stats = factory().get_scan_stats()
    for key in _NEW_COUNTERS:
        assert key in stats, f"`{key}` 카운터 부재 — `_empty_scan_stats()` 미동기"
        assert stats[key] == 0


@pytest.mark.parametrize("factory", [_bfb, _vcp], ids=["bfb", "vcp"])
def test_a6_retired_counters_are_gone(factory):
    """A6 — cycle227 관측 카운터는 **은퇴**한다 (의미가 뒤집혔다)."""
    stats = factory().get_scan_stats()
    leftovers = [k for k in _RETIRED_COUNTERS if k in stats]
    assert leftovers == [], (
        f"은퇴 대상 카운터 잔존: {leftovers}. `would_pass` 의 매매 귀결이 반전됐으므로 "
        "같은 키를 유지하면 과거 집계와 뒤섞인다"
    )


@pytest.mark.parametrize("factory", [_bfb, _vcp], ids=["bfb", "vcp"])
def test_a6_observe_hook_is_retired(factory):
    assert not hasattr(factory(), "_observe_vol_gate"), (
        "`_observe_vol_gate` 잔존 — 게이트 본체가 직접 로그하므로 관측 훅은 은퇴한다"
    )


# ###########################################################################
# A6 — 신규 마커 cap + 카운터 증가
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_a6_no_data_marker_capped_and_counted(caplog):
    """A6 — `[bfb_vol_gate_no_data]` 는 1회/(ticker)/일, 카운터는 전량."""
    caplog.set_level(logging.DEBUG, logger=BFB_LOGGER)
    strat = _bfb()

    for _ in range(5):
        strat._prev_price[TICKER] = FLAG_HIGH - 100
        strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)

    assert len(_lines(caplog, "[bfb_vol_gate_no_data]")) == 1
    assert strat.get_scan_stats()["vol_gate_no_data"] == 5


@freeze_time("2026-08-27 10:00:00")
def test_a6_no_data_also_arms_latch():
    """A6 — **미관측도 래치를 무장한다.**

    래치가 기억하는 것은 자문의 정의대로 *"오늘 retention 을 이미 통과했다"* 이지
    거래량 판정 결과가 아니다. 무장하지 않으면 edge-crossing 이 소진된 뒤
    다음 틱에 관측이 도착해도 재평가 기회가 없어, 이번 사이클이 없애려는
    역선택이 미관측 경로로 되살아난다.

    ⚠️ 명세 A1/A2 가 "미달 → 래치 등록" 만 적고 미관측 경우를 명시하지 않았다.
    자문의 래치 정의에서 도출한 것이므로 결과 문서에 판정 요청으로 기재한다.
    """
    strat = _bfb()
    strat._prev_price[TICKER] = FLAG_HIGH - 100
    assert strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600) == Signal.NONE
    assert TICKER in strat._vol_latch


@freeze_time("2026-08-27 10:00:00")
def test_a6_latch_armed_marker_capped_but_counter_counts_rearm(caplog):
    """A6 — 무장 로그는 1행, `latch_armed_count` 는 재무장까지 센다.

    ⚠️ cycle228 구현 중 판명 — `flag_low` 이탈 해제 후 재무장은 **진짜
    edge-crossing** 이 있어야 한다(001450/280360 회귀 — "붕괴가 만든 거래량으로
    죽은 셋업을 사면 안 된다"). 해제 시점의 가격(`FLAG_LOW-1`)이 곧 `_prev_price`
    가 되므로(래치 재평가 경로는 `_prev_price` 를 갱신하지 않는다 — 그 갱신을
    허용하면 001450 회귀가 깨진다), `FLAG_HIGH+100` 로 곧장 돌아가는 것만으로는
    edge-crossing 이 성립하지 않는다(오히려 그 반례가 이 시나리오 자체다).
    재무장을 관찰하려면 flag_high 미만으로 한 틱을 거쳐 `_prev_price` 를 다시
    flag_high 아래로 내려놓아야 한다(=진짜 재접근).
    """
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb()
    tick_volume.record_acml_vol(TICKER, BFB_THRESHOLD - 1)

    strat._prev_price[TICKER] = FLAG_HIGH - 100
    strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)      # arm #1
    strat.check_buy_signal(TICKER, FLAG_LOW - 1, 50_600)          # release (stop_line)
    strat.check_buy_signal(TICKER, FLAG_HIGH - 500, 50_600)      # 재접근 준비 — flag_high 미만
    strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)      # arm #2 (진짜 edge-crossing)

    assert len(_lines(caplog, "[bfb_latch_armed]")) == 1, "무장 로그 cap 미작동"
    assert strat.get_scan_stats()["latch_armed_count"] == 2


@freeze_time("2026-08-27 10:00:00")
def test_a6_extension_reject_marker_capped_and_counted(caplog):
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb()
    tick_volume.record_acml_vol(TICKER, BFB_THRESHOLD + 1)

    for _ in range(4):
        strat._prev_price[TICKER] = FLAG_HIGH - 100
        strat.check_buy_signal(TICKER, int(FLAG_HIGH * 1.09), 50_600)

    assert len(_lines(caplog, "[bfb_vol_gate_reject]")) == 1
    assert strat.get_scan_stats()["vol_gate_reject_ext"] == 4


@freeze_time("2026-08-27 10:00:00")
def test_a6_pass_counter_increments_on_buy(caplog):
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb()
    tick_volume.record_acml_vol(TICKER, BFB_THRESHOLD + 1)
    strat._prev_price[TICKER] = FLAG_HIGH - 100

    assert strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600) == Signal.BUY
    assert strat.get_scan_stats()["vol_gate_pass"] == 1


# ###########################################################################
# A6 — grep 정밀성 (P2-7)
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_a6_markers_do_not_mention_other_markers(caplog):
    """P2-7 — 마커 본문에 다른 마커 이름을 넣지 말 것.

    2026-08-25 에 `[day_high_scope_skip]` 4건이 substring grep 으로 114건이 됐다.
    """
    caplog.set_level(logging.DEBUG, logger=BFB_LOGGER)
    strat = _bfb()
    strat._prev_price[TICKER] = FLAG_HIGH - 100
    strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 50_600)

    foreign = (
        "[vcp_vol_gate_no_data]", "[vcp_latch_armed]",
        "[bfb_vol_gate_observe]", "[vcp_vol_gate_observe]",
    )
    for msg in [r.getMessage() for r in caplog.records]:
        for f in foreign:
            assert f not in msg, f"로그 본문에 타 마커 `{f}` 포함: {msg}"


@freeze_time("2026-08-27 10:00:00")
def test_a6_vcp_markers_capped_and_counted(caplog):
    caplog.set_level(logging.DEBUG, logger=VCP_LOGGER)
    strat = _vcp()

    for _ in range(3):
        strat._prev_price[TICKER] = BASE_HIGH - 100
        strat.check_buy_signal(TICKER, BASE_HIGH + 100, 11_900)

    assert len(_lines(caplog, "[vcp_vol_gate_no_data]")) == 1
    assert strat.get_scan_stats()["vol_gate_no_data"] == 3
