"""cycle273-pre — `[kojiro_gap_observe]` 붕괴 가드 반사실 필드 `ws_collapse=` 단위 테스트.

자문 = `_workspace/domain_consult/cycle273_kojiro_gap_gate_20260910.md` §3.4(다) —
"WS 값으로 붕괴 가드가 어떻게 판정했을지" 를 기존 판독 페이로드에 1개 필드로
추가한다. **행위 변경 0** — `check_buy_signal` 의 반환 Signal·`_bought_today`·
`state.buy_signals` 는 이 사이클에서 한 글자도 바뀌지 않는다(그 계약은
`tests/unit/engine/strategies/test_cycle268_kojiro_gap_behavior.py` 가 이미 지킨다
— cycle273-pre 는 `kojiro.py` 를 만지지 않으므로 그 골든 매트릭스는 diff 0 로
byte 불변이다).

기존 `ws_verdict` 가 **갭 게이트만**(붕괴 가드 제외) 재현하는 것과 대칭으로,
`ws_collapse` 는 **붕괴 가드만**(갭 게이트 제외) 재현한다 — 실 코드
(`kojiro.py:891` `if open_price > 0 and current_price < open_price:`)를
`ws_open` 에 대해 그대로 반복한 것이 유일한 산식이다(`_collapse_verdict_for_ws`).

## 값 토큰 = `blocked` | `allowed` | `-` (team-leader `kojiro-gap-observe` 판정, 2026-09-10)

`collapse`/`pass` 는 **쓰지 않는다** — `verdict=pass`/`ws_verdict=pass` 와 값 레벨에서
섞여 앵커 없는 grep 을 더 모호하게 만든다(§2.1 판독표의 `verdict=`↔`ws_verdict=`
접두 함정과 동형). `clear` 도 기각됐다 — 이 리포에서 `clear` 는 "청산"의 고정
의미(`NEXT_DAY_CLEAR`/`_execute_next_day_clear`/`_force_clear_main_only`)라, 판독자가
"붕괴 가드에 안 걸렸다" 를 "청산했다" 로 **반대로** 읽는다. ⇒ `blocked`(붕괴 가드에
걸렸을 것) / `allowed`(안 걸렸을 것) / `-`(WS 캐시 부재·해석 불가).

배경 실측 = `_workspace/analysis/2026-09-10_kojiro_gap_readout.md` §4-b —
09-10 `005490`(POSCO홀딩스) 행이 오염된 `ws_open`(프리장 340,000)으로는 실제
붕괴 가드에 걸렸지만(`blocked`) 그 자리에 "깨끗한" 값(331,500)을 넣으면 안 걸린다
(`allowed`). 그동안 이 반사실은 로그 밖에서 **손으로** 계산해야 했다 — 이 필드가
그 수작업을 로그 한 행 안으로 들여온다.

## 경로 B 동어반복 (읽기 전 필수)

`caller=on_tick` 행은 `risk.on_tick` 이 `check_buy_signal` **전에**
`ticker_prices[t]["open_price"]` 를 그 틱의 `open_price` 로 덮으므로 `ws_open ≡
arg_open` 이 항상 성립하고, `ws_collapse` 는 **실제 붕괴 판정과 구조적으로 항상
일치**한다(기존 `ws_cmp`/`ws_gap`/`ws_verdict` 3필드와 같은 함정). 그 계약은 실
프로덕션 호출 스택으로 `tests/unit/engine/test_cycle268_tester_real_call_paths.py`
`test_path_b_ws_collapse_is_self_referential` 이 봉인한다 — 이 파일은 **leaf 단위
계산**(경로 무관, `ws_open`/`current_price` 값만으로 산식 자체를 검정)만 다룬다.

자매 파일 = `tests/unit/engine/test_cycle268_kojiro_gap_observe.py`
            (`FIELD_ORDER` 에 `ws_collapse` 14번째 원소로 이미 반영, 나머지
            13필드 byte 불변) · `tests/unit/ast/test_cycle268_ast_gap_observe.py`
            (이 사이클 무접촉 — 새 import·async·verdict·삽입 지점 0건이라 그대로 GREEN) ·
            `tests/unit/engine/test_cycle268_tester_real_call_paths.py`
            (경로 B 동어반복의 실경로 봉인).
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit

MARKER = "[kojiro_gap_observe]"

PARAMS = {"gap_up_skip_pct": 5.0, "gap_down_skip_pct": -4.0}


# ---------------------------------------------------------------------------
# 픽스처 / 헬퍼 (cycle268 자매 파일과 동형 — 독립 파일 원칙, 공유 conftest 없음)
# ---------------------------------------------------------------------------
@pytest.fixture
def observe():
    from src.engine.kojiro_gap_observe import observe_gap, reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    yield observe_gap
    reset_kojiro_gap_observe_cap()


@pytest.fixture
def ws_cache():
    from src.engine import scanner

    saved = dict(scanner.ticker_prices)
    scanner.ticker_prices.clear()
    yield scanner.ticker_prices
    scanner.ticker_prices.clear()
    scanner.ticker_prices.update(saved)


def rows(caplog):
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith(MARKER + " ")]


def fields(line: str) -> dict[str, str]:
    body = line.split(MARKER + " ", 1)[1]
    return dict(kv.split("=", 1) for kv in body.split(" "))


def keys_in_order(line: str) -> tuple[str, ...]:
    body = line.split(MARKER + " ", 1)[1]
    return tuple(kv.split("=", 1)[0] for kv in body.split(" "))


def one(caplog) -> dict[str, str]:
    got = rows(caplog)
    assert len(got) == 1, f"정확히 1행이어야 한다 — 실측 {len(got)}행: {got}"
    return fields(got[0])


def call(observe, *, ticker="000001", verdict="collapse", arg_open=10050,
         prev_close=10000, current_price=9800, params=None, depth=1):
    return observe(
        ticker, verdict,
        arg_open=arg_open, prev_close=prev_close, current_price=current_price,
        params=PARAMS if params is None else params, depth=depth,
    )


# ===========================================================================
# 1. `ws_collapse` 산출 — 붕괴 가드만(갭 게이트 제외) 재현, 값 토큰 = blocked/allowed/-
# ===========================================================================
def test_ws_collapse_is_blocked_when_current_below_ws_open(observe, ws_cache, caplog):
    """실 코드(`kojiro.py:891`) 그대로: `ws_open>0 and current<ws_open` → `blocked`.

    `arg_open`(정본 판정값)과 `ws_open`(WS 캐시)이 달라도, `ws_collapse` 는
    오직 `ws_open` 기준으로만 판정한다 — 005490 사례(자문 §4-b)와 동형.
    """
    ws_cache["000001"] = {"open_price": 340000}  # 오염된 프리장 시가
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000001", verdict="collapse",
             arg_open=340000, prev_close=331000, current_price=335500)
    f = one(caplog)
    assert f["ws_collapse"] == "blocked"


@pytest.mark.parametrize("ws_open,current_price", [
    (331500, 335500),   # 위 초과
    (335500, 335500),   # 정확히 경계 — 엄격 부등호 `<` 라 붕괴 아님
])
def test_ws_collapse_is_allowed_when_current_at_or_above_ws_open(
    observe, ws_cache, caplog, ws_open, current_price,
):
    """`current >= ws_open` (경계 포함) → `allowed`.

    실 코드의 `<` 를 `<=` 로 뒤집는 뮤테이션은 경계 케이스(두 번째 파라미터)에서
    `allowed`→`blocked` 로 갈라져 여기서 잡힌다.
    """
    ticker = f"ws_open_{ws_open}_{current_price}"
    ws_cache[ticker] = {"open_price": ws_open}
    with caplog.at_level(logging.INFO):
        call(observe, ticker=ticker, verdict="pass",
             arg_open=ws_open, prev_close=ws_open - 500, current_price=current_price)
    f = one(caplog)
    assert f["ws_collapse"] == "allowed", (
        f"{current_price} >= {ws_open} — 붕괴가 아니다(자문 §4-b 005490 재판정과 동일 산술)"
    )


def test_ws_collapse_is_dash_when_ws_cache_absent(observe, ws_cache, caplog):
    """WS 캐시가 없으면(`ws_cmp=ws_absent`) `ws_collapse` 도 `-` — '붕괴 아님' 을
    단정하면 안 된다(대조 자체가 성립하지 않은 행)."""
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000003", verdict="collapse",
             arg_open=10050, prev_close=10000, current_price=9800)
    f = one(caplog)
    assert f["ws_cmp"] == "ws_absent"
    assert f["ws_collapse"] == "-"


@pytest.mark.parametrize("ws_open", [0, -100])
def test_ws_collapse_is_dash_when_ws_open_not_positive(observe, ws_cache, caplog, ws_open):
    """`ws_open<=0` 은 실 코드의 `open_price > 0` 전제 자체가 성립하지 않는 값이다 —
    붕괴 가드가 "재현조차 안 되는" 입력이므로 `allowed` 로 단정하지 않고 `-`.

    (실 `check_buy_signal` 에서도 `open_price<=0` 이면 그 이전 갭 게이트가
    `no_data` 로 빠지는 코호트이지 "붕괴 아님이 확정된" 코호트가 아니다.)
    """
    ticker = f"ws_open_nonpos_{ws_open}"
    ws_cache[ticker] = {"open_price": ws_open}
    with caplog.at_level(logging.INFO):
        call(observe, ticker=ticker, verdict="no_data",
             arg_open=0, prev_close=10000, current_price=9800)
    assert one(caplog)["ws_collapse"] == "-"


# ===========================================================================
# 2. 서식 — 기존 13필드 byte 불변 + `ws_collapse` 는 **끝**에 추가
# ===========================================================================
def test_ws_collapse_is_appended_after_existing_13_fields(observe, ws_cache, caplog):
    """기존 필드 순서를 조금도 흔들지 않는다 — 새 필드는 `gap_down` **뒤**에만 붙는다
    (cycle264 `truth_confirmed`/`truth_total` 추가 선례와 동형, 과거 로그 대조 유지)."""
    ws_cache["000004"] = {"open_price": 10200}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000004", verdict="pass",
             arg_open=10050, prev_close=10000, current_price=10100)
    keys = keys_in_order(rows(caplog)[0])
    assert keys[:13] == (
        "ticker", "verdict", "caller", "ws_cmp", "arg_open", "ws_open", "prev_close",
        "gap_rate", "ws_gap", "ws_verdict", "cur", "gap_up", "gap_down",
    ), f"기존 13필드 순서가 흔들렸다 — 실측 {keys[:13]}"
    assert keys[13] == "ws_collapse", f"14번째(마지막) 필드가 아니다 — 실측 {keys}"
    assert len(keys) == 14


def test_ws_collapse_token_never_collides_with_other_verdict_tokens(observe, ws_cache, caplog):
    """`blocked`/`allowed` 는 `verdict`(6종)·`ws_cmp`(3종)·`ws_verdict`(3종+`-`) 의
    어떤 값과도 겹치지 않는다 — grep 앵커 모호성이 이 필드로 재발하지 않는다는
    회귀 가드(§2.1 판독표 `verdict=`↔`ws_verdict=` 접두 함정의 재발 방지)."""
    ws_cache["000007"] = {"open_price": 9000}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000007", verdict="collapse",
             arg_open=10050, prev_close=10000, current_price=8000)
    f = one(caplog)
    other_tokens = {f["verdict"], f["ws_cmp"], f["ws_verdict"]}
    assert f["ws_collapse"] not in other_tokens, (
        f"ws_collapse={f['ws_collapse']!r} 가 다른 필드 값과 겹친다: {other_tokens}"
    )
    assert f["ws_collapse"] not in ("clear", "collapse", "pass"), (
        "기각된 토큰(clear) 또는 기존 verdict 토큰을 재사용했다"
    )


# ===========================================================================
# 3. never-raise — 적대 입력에도 던지지 않는다(§3-1 계약 상속)
# ===========================================================================
def test_ws_collapse_never_raises_on_hostile_ws_open(observe, ws_cache, caplog):
    """WS 캐시의 `open_price` 가 산술 불가(문자열 쓰레기)여도 행 전체가 살아남고
    `ws_collapse` 는 `-` 로 떨어진다 — 관측기가 죽으면 매수 경로가 끊긴다(§3-1)."""
    ws_cache["000005"] = {"open_price": "garbage"}
    with caplog.at_level(logging.DEBUG):
        assert call(observe, ticker="000005", verdict="pass",
                    arg_open=10050, prev_close=10000, current_price=10100) is None
    f = one(caplog)
    assert f["ws_collapse"] == "-"


def test_ws_collapse_never_raises_when_current_price_is_none(observe, ws_cache, caplog):
    """`current_price=None` 이어도(§ 기존 `test_never_raises_on_none_and_odd_inputs`
    동계열) 행이 나오고 `ws_collapse` 는 `-`."""
    ws_cache["000006"] = {"open_price": 10050}
    with caplog.at_level(logging.DEBUG):
        assert call(observe, ticker="000006", verdict="pass",
                    arg_open=10050, prev_close=10000, current_price=None) is None
    f = one(caplog)
    assert f["ws_collapse"] == "-"


# ===========================================================================
# 4. leaf 헬퍼 `_collapse_verdict_for_ws` 직접 단위 테스트 (뮤테이션 정밀 타격)
# ===========================================================================
def test_collapse_verdict_helper_matches_real_guard_formula():
    """`_collapse_verdict_for_ws` 가 `kojiro.py:891` 의 부등호(`<`, 등호 미포함)를
    정확히 재현한다 — `<=` 로 뒤집는 뮤테이션은 `current_price == ws_open` 케이스에서
    여기서 즉시 잡힌다."""
    from src.engine.kojiro_gap_observe import _collapse_verdict_for_ws

    assert _collapse_verdict_for_ws(10000, 9999) == "blocked"
    assert _collapse_verdict_for_ws(10000, 10000) == "allowed", "경계 포함 — 엄격 부등호"
    assert _collapse_verdict_for_ws(10000, 10001) == "allowed"
    assert _collapse_verdict_for_ws(None, 9999) is None
    assert _collapse_verdict_for_ws(0, 9999) is None, "open<=0 은 재현 불가 — allowed 로 단정 금지"
    assert _collapse_verdict_for_ws(10000, None) is None, "current_price 해석 불가"
    assert _collapse_verdict_for_ws("garbage", 9999) is None
