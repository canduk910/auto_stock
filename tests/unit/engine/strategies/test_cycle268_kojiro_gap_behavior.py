"""cycle268 Red — kojiro `check_buy_signal` **행위 보존**(최우선) + 관측 호출 지점 6곳.

정본 명세 = `_workspace/specs/cycle268_kojiro_gap_observe.md` §6.1
자매 파일 = `tests/unit/engine/test_cycle268_kojiro_gap_observe.py`(leaf) ·
            `tests/unit/ast/test_cycle268_ast_gap_observe.py`(구조)

## 이 파일의 두 얼굴

1. **골든 매트릭스**(§6.1) — 지금 HEAD 에서 **초록**이다. 관측 도입 뒤에도 초록이어야
   한다. 여기 박힌 기대값은 명세의 추론이 아니라 **HEAD 실측**이다(2026-09-07,
   `check_buy_signal` 을 6 시나리오 × 3 WS 캐시 = 18 조합으로 직접 돌려 채취).
   - 특히 **WS 캐시 유무·값이 결과를 전혀 바꾸지 않는다**는 것이 이 매트릭스의 핵심이다.
     kojiro 는 `scanner.ticker_prices` 를 읽지 않으며, cycle268 이 그 사실을 바꾸면 안 된다.
2. **관측 발화 가드** — 지금 **RED** 다(leaf 부재). 6개 호출 지점을 하나씩 지우면
   각각 최소 1개가 붉어진다(§6.3 뮤테이션 계약).

## 관측기 폭사 내성

leaf 를 `side_effect=Exception` 으로 만든 상태에서 같은 매트릭스가 **동일 결과**를 낸다
(cycle262 fail-open 계약 동계열). 관측 실패가 매수 판정을 바꾸면 이 사이클의 제1 계약
"행위 변경 0" 이 깨진 것이다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
MARKER = "[kojiro_gap_observe]"
TICKER = "131290"
BUY_WINDOW = datetime(2026, 5, 8, 9, 10, tzinfo=KST)

# 131290 재현 (조사 §2 실측)
PREV_131290 = 236500
WS_131290 = 236500       # 오염된 WS 캐시(프리장 기준가)
KRX_131290 = 252500      # KRX 09:00 확정 시가


# ---------------------------------------------------------------------------
# 시나리오 정의 + **HEAD 실측** 골든
# ---------------------------------------------------------------------------
SCENARIOS = {
    #                 prev_close  open    cur     기대 verdict
    "gap_up":       (10000,     10600,  10700,  "skip_up"),
    "gap_down":     (10000,      9500,   9550,  "skip_down"),
    "collapse":     (10000,     10050,   9900,  "collapse"),
    "pass":         (10000,     10050,  10100,  "pass"),
    "no_data_open": (10000,         0,  10100,  "no_data"),
    "no_data_prev": (    0,     10050,  10100,  "no_data"),
}

# HEAD 실측 (2026-09-07). (signal, bought_today, buy_signals 존재 여부)
GOLDEN = {
    "gap_up":       (Signal.NONE, {TICKER}, False),
    "gap_down":     (Signal.NONE, {TICKER}, False),
    "collapse":     (Signal.NONE, set(),    False),
    "pass":         (Signal.BUY,  {TICKER}, True),
    "no_data_open": (Signal.BUY,  {TICKER}, True),
    "no_data_prev": (Signal.BUY,  {TICKER}, True),
}

WS_VARIANTS = ("absent", "eq", "ne")
MATRIX = [(s, w) for s in SCENARIOS for w in WS_VARIANTS]
MATRIX_IDS = [f"{s}-ws_{w}" for s, w in MATRIX]


# ---------------------------------------------------------------------------
# 픽스처 / 헬퍼
# ---------------------------------------------------------------------------
@pytest.fixture
def kojiro():
    return KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로 대순환", weight=0.2)
    )


@pytest.fixture(autouse=True)
def clean_observer_state():
    """`ticker_prices`/`ticker_names` + 관측 cap 격리.

    ⚠️ cap 리셋은 **테스트 위생이지 프로덕션 관심사가 아니다.** 한때
    `KojiroStrategy.__init__` 이 `reset_kojiro_gap_observe_cap()` 을 불러 이 격리를
    대신했으나 그건 장중에 두 번째 인스턴스가 생기는 경로(백테스트·재등록·향후
    리팩터)에서 **그날 cap 을 조용히 비워** 같은 종목을 재발화시킨다 — 행 수의
    신뢰성이 곧 이 사이클이 재려는 값이므로 관측이 스스로를 오염시키는 셈이다.
    격리는 여기서 한다.
    """
    from src.engine import scanner
    from src.engine.kojiro_gap_observe import reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    saved_p, saved_n = dict(scanner.ticker_prices), dict(scanner.ticker_names)
    scanner.ticker_prices.clear()
    scanner.ticker_names.clear()
    yield
    reset_kojiro_gap_observe_cap()
    scanner.ticker_prices.clear()
    scanner.ticker_prices.update(saved_p)
    scanner.ticker_names.clear()
    scanner.ticker_names.update(saved_n)


def seed(strategy, ticker=TICKER, *, prev_close=10000, stage=1, atr=200.0,
         sector=None):
    strategy._candidates[ticker] = {
        "prev_close": prev_close, "atr": atr, "stage": stage,
        "ema_s": 9900.0, "ema_m": 9800.0, "ema_l": 9700.0,
        "atr_ratio": 0.02, **({"sector": sector} if sector else {}),
    }


def set_ws(ticker, open_price, current_price=0):
    from src.engine import scanner

    scanner.ticker_prices[ticker] = {
        "current_price": current_price, "open_price": open_price,
    }


def apply_ws_variant(variant, ticker, arg_open, cur):
    if variant == "absent":
        return
    set_ws(ticker, arg_open if variant == "eq" else arg_open + 1234, cur)


def rows(caplog):
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith(MARKER + " ")]


def fields(line):
    body = line.split(MARKER + " ", 1)[1]
    return dict(kv.split("=", 1) for kv in body.split(" "))


def verdicts(caplog):
    return [fields(r)["verdict"] for r in rows(caplog)]


def snapshot(strategy, signal):
    """행위 3축 — 반환 Signal · `_bought_today` · `state.buy_signals`."""
    return (
        signal,
        set(strategy._bought_today),
        [dict(s) for s in strategy.state.buy_signals],
    )


def run(strategy, scenario, ws_variant, *, at=BUY_WINDOW):
    prev_close, open_price, cur, _ = SCENARIOS[scenario]
    seed(strategy, prev_close=prev_close)
    apply_ws_variant(ws_variant, TICKER, open_price, cur)
    with freeze_time(at):
        sig = strategy.check_buy_signal(TICKER, cur, open_price)
    return snapshot(strategy, sig)


def break_observer(monkeypatch):
    """leaf 관측 함수를 폭사시킨다 — 두 네임스페이스 모두 덮는다.

    kojiro 가 `from ... import observe_gap` 로 쓰든 `mod.observe_gap` 로 쓰든
    같은 효과여야 한다.
    """
    import src.engine.kojiro_gap_observe as obs
    import src.engine.strategies.kojiro as kmod

    def boom(*a, **kw):
        raise RuntimeError("boom — 관측기 폭사 내성 검정")

    monkeypatch.setattr(obs, "observe_gap", boom)
    if hasattr(kmod, "observe_gap"):
        monkeypatch.setattr(kmod, "observe_gap", boom)
    if hasattr(kmod, "kojiro_gap_observe"):
        monkeypatch.setattr(kmod.kojiro_gap_observe, "observe_gap", boom)


# ===========================================================================
# 1. 골든 매트릭스 — 행위 보존 (§6.1 최우선). HEAD 에서 이미 초록.
# ===========================================================================
@pytest.mark.parametrize("scenario,ws_variant", MATRIX, ids=MATRIX_IDS)
def test_golden_matrix_head_behavior(kojiro, scenario, ws_variant):
    """18 조합 전수 — 반환 Signal · `_bought_today` · `buy_signals` 가 HEAD 실측과 같다."""
    sig, bought, signals = run(kojiro, scenario, ws_variant)
    exp_sig, exp_bought, exp_has_signal = GOLDEN[scenario]
    prev_close, open_price, cur, _ = SCENARIOS[scenario]

    assert sig is exp_sig, f"{scenario}/{ws_variant} 반환 Signal 변경"
    assert bought == exp_bought, f"{scenario}/{ws_variant} `_bought_today` 래치 변경"
    if not exp_has_signal:
        assert signals == [], f"{scenario}/{ws_variant} buy_signals 오염"
    else:
        assert signals == [{
            "ticker": TICKER, "name": "", "price": cur, "stage": 1,
            "atr": 200, "change_rate": 0, "time": "09:10:00",
        }], f"{scenario}/{ws_variant} buy_signals 내용 변경"


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_ws_cache_does_not_influence_behavior(kojiro, scenario):
    """WS 캐시 유무·값이 결과를 **전혀** 바꾸지 않는다.

    kojiro 는 `scanner.ticker_prices` 를 읽지 않는다 — 관측이 그 사실을 바꾸면
    (예: 관측 값을 판정에 되먹이면) 여기서 붉어진다.
    """
    results = []
    for ws_variant in WS_VARIANTS:
        fresh = KojiroStrategy(
            StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2)
        )
        from src.engine import scanner as _sc
        _sc.ticker_prices.clear()
        results.append(run(fresh, scenario, ws_variant))
    assert results[0] == results[1] == results[2], (
        f"{scenario}: WS 캐시 변형이 행위를 갈랐다 — {results}"
    )


# ===========================================================================
# 2. 관측기 폭사 내성 (§6.1) — cycle262 fail-open 계약 동계열. **RED**
# ===========================================================================
@pytest.mark.parametrize("scenario,ws_variant", MATRIX, ids=MATRIX_IDS)
def test_golden_matrix_survives_observer_explosion(kojiro, monkeypatch, scenario,
                                                   ws_variant):
    break_observer(monkeypatch)
    sig, bought, signals = run(kojiro, scenario, ws_variant)
    exp_sig, exp_bought, exp_has_signal = GOLDEN[scenario]
    prev_close, open_price, cur, _ = SCENARIOS[scenario]

    assert sig is exp_sig, "관측기가 터졌다고 매수 판정이 바뀌면 안 된다"
    assert bought == exp_bought, "관측기가 터졌다고 래치가 바뀌면 안 된다"
    assert (signals != []) is exp_has_signal
    if exp_has_signal:
        assert signals[0]["price"] == cur


def test_observer_explosion_does_not_propagate(kojiro, monkeypatch):
    """예외가 `check_buy_signal` 밖으로 새면 `_swing_buy_poll_loop` 가 그 종목을
    통째로 건너뛴다(매매 행위 변경)."""
    break_observer(monkeypatch)
    seed(kojiro, prev_close=10000)
    with freeze_time(BUY_WINDOW):
        assert kojiro.check_buy_signal(TICKER, 10100, 10050) is Signal.BUY


# ===========================================================================
# 3. 6개 호출 지점이 각각 발화한다 (§6.3 뮤테이션 계약). **RED**
# ===========================================================================
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_each_scenario_emits_its_verdict(kojiro, caplog, scenario):
    """지점 2~6 — 시나리오마다 대응 verdict 가 정확히 나온다.

    호출 지점 하나를 지우면 그 시나리오가 붉어진다.
    """
    expected = SCENARIOS[scenario][3]
    with caplog.at_level(logging.INFO):
        run(kojiro, scenario, "absent")
    got = verdicts(caplog)
    assert expected in got, f"{scenario}: verdict={expected} 행이 없다 — 실측 {got}"


def test_candidate_verdict_is_emitted_for_every_scenario(kojiro, caplog):
    """지점 1 — `candidate` 는 A/B 비율의 **분모**다. 매 평가마다 나와야 한다."""
    with caplog.at_level(logging.INFO):
        run(kojiro, "pass", "absent")
    assert "candidate" in verdicts(caplog)


def test_candidate_fires_before_sector_cap(kojiro, caplog):
    """지점 1 은 **섹터캡 판정 전**이다 — 섹터캡에 걸려도 분모에는 잡힌다.

    이게 없으면 "candidate 행은 있는데 판정 행이 없는 ticker" 를 섹터캡으로
    귀속시키는 §1 판독 절차가 성립하지 않는다.
    """
    kojiro.config.params["max_positions_per_sector"] = 1
    seed(kojiro, prev_close=10000, sector="반도체")
    kojiro._candidates["000660"] = {
        "prev_close": 10000, "atr": 200.0, "stage": 1, "ema_s": 1.0,
        "ema_m": 1.0, "ema_l": 1.0, "atr_ratio": 0.02, "sector": "반도체",
    }
    kojiro.state.positions["000660"] = Position(
        ticker="000660", buy_price=10000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=BUY_WINDOW.date(),
    )
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            sig = kojiro.check_buy_signal(TICKER, 10100, 10050)
    assert sig is Signal.NONE, "섹터캡 행위가 바뀌었다"
    assert "candidate" in verdicts(caplog), (
        "섹터캡에 걸린 후보가 분모에서 사라졌다 — 지점 1 이 섹터캡 뒤로 밀렸다"
    )
    assert "pass" not in verdicts(caplog)


def test_candidate_fires_before_time_window_gate(kojiro, caplog):
    """지점 1 은 **시간창 판정 전**이다 — 09:05 이전에도 분모에는 잡힌다."""
    with caplog.at_level(logging.INFO):
        run(kojiro, "pass", "absent", at=datetime(2026, 5, 8, 9, 4, tzinfo=KST))
    got = verdicts(caplog)
    assert "candidate" in got, "지점 1 이 시간창 게이트 뒤로 밀렸다"
    assert "pass" not in got, "시간창 밖인데 갭 게이트가 평가됐다 — 행위 변경"


# ⚠️ 아래 두 개는 **음성 가드**다 — Red 시점에는 공허하게 통과한다(관측이 아예 없으니).
#    짝이 되는 양성 가드(`test_candidate_verdict_is_emitted_for_every_scenario`)가
#    지금 RED 라 기준선은 확보돼 있고, Green 이후에는 "분모 오염" 뮤테이션을 잡는다.
def test_no_observation_when_stage_not_one(kojiro, caplog):
    """지점 1 은 `info`/`stage != 1` 통과 **직후**다 — 후보가 아니면 아무 행도 없다."""
    seed(kojiro, prev_close=10000, stage=3)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            assert kojiro.check_buy_signal(TICKER, 10100, 10050) is Signal.NONE
    assert rows(caplog) == []


def test_no_observation_when_early_gate_blocks(kojiro, caplog):
    """보유·매도완료 등 상단 게이트에 막히면 관측도 없다(분모 오염 차단)."""
    seed(kojiro, prev_close=10000)
    kojiro.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=10000, quantity=1, order_no="O1",
        strategy_id="kojiro", buy_date=BUY_WINDOW.date(),
    )
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            assert kojiro.check_buy_signal(TICKER, 10100, 10050) is Signal.NONE
    assert rows(caplog) == []


# ===========================================================================
# 4. caller — 실제 호출 shim (문자열 주입 금지). **RED**
# ===========================================================================
def on_tick(strategy, ticker, cur, open_price):
    """risk.on_tick 경로(경로 B) 재현 — 함수 **이름**이 검정 대상이다."""
    return strategy.check_buy_signal(ticker, cur, open_price)


def _swing_buy_poll_loop(strategy, ticker, cur, open_price):
    """scheduler._swing_buy_poll_loop 경로(경로 A) 재현."""
    return strategy.check_buy_signal(ticker, cur, open_price)


def test_caller_field_distinguishes_path_a_and_b(kojiro, caplog):
    seed(kojiro, prev_close=10000)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            on_tick(kojiro, TICKER, 10100, 10050)
    assert {fields(r)["caller"] for r in rows(caplog)} == {"on_tick"}

    caplog.clear()
    k2 = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    seed(k2, prev_close=10000)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            _swing_buy_poll_loop(k2, TICKER, 10100, 10050)
    assert {fields(r)["caller"] for r in rows(caplog)} == {"_swing_buy_poll_loop"}


def test_same_ticker_judged_on_both_paths_is_visible(kojiro, caplog):
    """004020 코호트 — 같은 종목이 경로 A·B 양쪽에서 심사받은 사실이 로그에 남는다.

    (kojiro 는 `_bought_today` 래치가 있어 2회차 판정이 상단에서 끊긴다.
     그래서 이 케이스는 **서로 다른 전략 인스턴스**가 아니라 서로 다른 경로의
     `candidate` 행 2개로 확인한다.)
    """
    seed(kojiro, prev_close=10000)
    with caplog.at_level(logging.INFO):
        with freeze_time(datetime(2026, 5, 8, 9, 4, tzinfo=KST)):  # 창 밖 = 래치 없음
            on_tick(kojiro, TICKER, 10100, 10050)
            _swing_buy_poll_loop(kojiro, TICKER, 10100, 10050)
    callers = [fields(r)["caller"] for r in rows(caplog)
               if fields(r)["verdict"] == "candidate"]
    assert sorted(callers) == ["_swing_buy_poll_loop", "on_tick"], (
        f"경로별 분리가 지워졌다 — 실측 {callers}"
    )


# ===========================================================================
# 5. 131290 재현 — 경로 A/B (§6.1 필수). **RED**
# ===========================================================================
def test_131290_path_a_flip_is_visible_in_one_row(kojiro, caplog):
    """경로 A(KRX 252500) — `verdict=skip_up ws_gap=0.00 ws_verdict=pass`."""
    seed(kojiro, prev_close=PREV_131290)
    set_ws(TICKER, WS_131290, 253000)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            sig = _swing_buy_poll_loop(kojiro, TICKER, 253000, KRX_131290)
    assert sig is Signal.NONE and TICKER in kojiro._bought_today

    hit = [fields(r) for r in rows(caplog) if fields(r)["verdict"] == "skip_up"]
    assert hit, f"skip_up 행이 없다 — 실측 {rows(caplog)}"
    f = hit[0]
    assert f["caller"] == "_swing_buy_poll_loop"
    assert f["arg_open"] == str(KRX_131290)
    assert f["ws_open"] == str(WS_131290)
    assert f["gap_rate"] == "6.77"
    assert f["ws_gap"] == "0.00"
    assert f["ws_verdict"] == "pass", "뒤집힘이 한 행에서 보여야 한다"
    assert f["ws_cmp"] == "ws_ne"


def test_131290_path_b_pass_with_ws_eq(kojiro, caplog):
    """경로 B(오염 236500) — `verdict=pass ws_cmp=ws_eq`. 매수까지 간다."""
    seed(kojiro, prev_close=PREV_131290)
    set_ws(TICKER, WS_131290, 237000)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            sig = on_tick(kojiro, TICKER, 237000, WS_131290)
    assert sig is Signal.BUY, "경로 B 는 오염된 시가로 '통과' 한다(=조사의 결론)"

    hit = [fields(r) for r in rows(caplog) if fields(r)["verdict"] == "pass"]
    assert hit, f"pass 행이 없다 — 실측 {rows(caplog)}"
    f = hit[0]
    assert f["caller"] == "on_tick"
    assert f["ws_cmp"] == "ws_eq"
    assert f["arg_open"] == str(WS_131290)
    assert f["gap_rate"] == "0.00"


# ===========================================================================
# 6. 기존 스킵 로그 보존 (§6.2 — 과거 로그 대조 유지)
# ===========================================================================
def test_existing_skip_logs_still_emitted(kojiro, caplog):
    with caplog.at_level(logging.INFO):
        run(kojiro, "gap_up", "absent")
    assert any("고지로 갭업 스킵: 131290 갭률 6.0% ≥ 5.0%" in r.getMessage()
               for r in caplog.records), "갭업 스킵 로그가 바뀌었다"

    caplog.clear()
    k2 = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    with caplog.at_level(logging.INFO):
        run(k2, "gap_down", "absent")
    assert any("고지로 갭다운 스킵: 131290 갭률 -5.0% ≤ -4.0%" in r.getMessage()
               for r in caplog.records), "갭다운 스킵 로그가 바뀌었다"


# ===========================================================================
# 7. cap — 실전 폭주 방지 (틱마다 도는 경로). **RED**
# ===========================================================================
def test_repeated_candidate_evaluations_emit_once_per_path(kojiro, caplog):
    """창 밖 반복 평가(틱마다)에도 `candidate` 는 경로당 1행이다."""
    seed(kojiro, prev_close=10000)
    with caplog.at_level(logging.INFO):
        with freeze_time(datetime(2026, 5, 8, 9, 4, tzinfo=KST)):
            for _ in range(50):
                on_tick(kojiro, TICKER, 10100, 10050)
    cands = [r for r in rows(caplog) if fields(r)["verdict"] == "candidate"]
    assert len(cands) == 1, f"cap 미작동 — {len(cands)}행"


# ===========================================================================
# 8. 호출 지점의 예외 흡수 — 흔적을 남기되 매수는 산다 (팀장 판정 ①②)
# ===========================================================================
def test_call_site_failure_leaves_a_trace_not_silence(kojiro, monkeypatch, caplog):
    """6개 호출 지점의 `except` 는 **무흔적 `pass` 가 아니다**(cycle258 카드 #5).

    관측 호출이 통째로 터졌는데 로그가 침묵하면, 이 마커의 결측을 "오염이 없었다"
    로 오독하게 된다(명세 §1 판독 표 5행이 막으려던 바로 그것).
    """
    break_observer(monkeypatch)
    seed(kojiro, prev_close=10000)
    with caplog.at_level(logging.DEBUG):
        with freeze_time(BUY_WINDOW):
            assert kojiro.check_buy_signal(TICKER, 10100, 10050) is Signal.BUY
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING
             and r.getMessage().startswith(MARKER + " observer_failed")]
    assert warns, (
        "관측 호출이 폭사했는데 흔적이 없다 — 호출 지점의 `except Exception: pass` 를 "
        "`absorb_call_failure(ticker)` 로 바꾼다"
    )


def test_buy_survives_when_the_absorber_itself_explodes(kojiro, monkeypatch):
    """흡수기 **자신**이 터져도 매수가 살아야 한다.

    `absorb_call_failure` 는 호출 지점의 `except` 절에서 불린다 — 거기서 던지면
    그 예외가 `check_buy_signal` 밖으로 나가 매수 경로가 끊긴다. 2차 예외까지
    흡수하는 것이 계약이다(cycle258 J-3 "가장 안쪽은 어떤 경우에도 조용히 통과").
    """
    import src.engine.kojiro_gap_observe as obs

    def boom(*a, **kw):
        raise RuntimeError("boom")

    break_observer(monkeypatch)
    monkeypatch.setattr(obs, "trace_observer_failure", boom)   # 흡수기 내부 폭사
    seed(kojiro, prev_close=10000)
    with freeze_time(BUY_WINDOW):
        assert kojiro.check_buy_signal(TICKER, 10100, 10050) is Signal.BUY
    assert TICKER in kojiro._bought_today


def test_strategy_init_does_not_reset_the_observation_cap(caplog):
    """`KojiroStrategy()` 생성이 그날 cap 을 비우지 않는다 (팀장 판정 ②).

    비우면 장중 두 번째 인스턴스 생성 경로에서 같은 종목이 재발화해 행 수가
    부풀고, 그 행 수가 곧 이 사이클이 재려는 값이다.
    """
    k1 = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    seed(k1, prev_close=10000)
    with caplog.at_level(logging.INFO):
        with freeze_time(BUY_WINDOW):
            on_tick(k1, TICKER, 10100, 10050)
        first = len(rows(caplog))
        assert first >= 1, "기준선 부재"

        k2 = KojiroStrategy(
            StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2)
        )
        seed(k2, prev_close=10000)
        with freeze_time(BUY_WINDOW):
            on_tick(k2, TICKER, 10100, 10050)
    assert len(rows(caplog)) == first, (
        "두 번째 인스턴스 생성이 cap 을 리셋해 같은 (ticker,caller,verdict) 가 "
        f"재발화했다 — {first}행 → {len(rows(caplog))}행"
    )
