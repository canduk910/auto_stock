"""cycle268 Red — `[kojiro_gap_observe]` **leaf 관측기** 행위 가드.

정본 명세 = `_workspace/specs/cycle268_kojiro_gap_observe.md`
배경 정본 = `_workspace/consult/2026-09-07_kojiro_gap_contamination.md`
자매 파일 = `tests/unit/engine/strategies/test_cycle268_kojiro_gap_behavior.py`(행위 보존) ·
            `tests/unit/ast/test_cycle268_ast_gap_observe.py`(구조)

**Red 단계 — 테스트만. `src/` 미변경.** 이 파일 전체가 지금 RED 다(leaf 모듈 부재).

## Green 이 만족해야 하는 계약 (이 파일이 정본)

신규 leaf `src/engine/kojiro_gap_observe.py` 가 다음을 공개한다::

    def observe_gap(
        ticker: str,
        verdict: str,
        *,
        arg_open,          # 판정에 **실제로 쓰인** open_price (마커의 정본 값)
        prev_close,        # info["prev_close"] (DB 일봉, 깨끗)
        current_price,     # 붕괴 가드 사후 재구성용
        params,            # `self.config.params` — **읽기만** 한다
        depth: int = 2,    # sys._getframe 깊이 (leaf → check_buy_signal → 실제 호출자)
    ) -> None: ...

    def reset_kojiro_gap_observe_cap() -> None: ...   # 테스트·운영 훅

- 반환값은 **항상 `None`** — 호출부는 반환값을 쓰지 않는다.
- **never-raise** — 어떤 내부 실패도 호출부로 새지 않고
  `observer_trace.trace_observer_failure("[kojiro_gap_observe]", ticker, cap)` 흔적만 남긴다.
- cap = `KstDailyEmitCap[tuple[str, str, str]]`, 키 = `(ticker, caller, verdict)`.
- **비용 순서**(명세 §3-4) = caller 해석 → 키 조립 → cap peek → (False 면 즉시 return) →
  그 **뒤에야** WS 캐시 조회·갭 산술·문자열 포맷. `test_cost_order_*` 가 이것을 잰다.

## 서식 (필드 **순서 고정** — 이후 사이클에서도 이름·순서를 바꾸지 않는다)

    [kojiro_gap_observe] ticker= verdict= caller= ws_cmp= arg_open= ws_open= prev_close=
                         gap_rate= ws_gap= ws_verdict= cur= gap_up= gap_down=

## 왜 `caller` 를 문자열로 주입하지 않는가

`caller` 는 경로 A/B 판별의 **정본**이다. 테스트가 문자열을 주입하면 "그 문자열이
그대로 찍힌다" 만 재고 `sys._getframe(depth=2)` 전제는 한 번도 검증되지 않는다 —
그래서 이 파일은 실제로 `on_tick` / `_swing_buy_poll_loop` 라는 이름의 **진짜 함수**를
만들어 그 프레임을 통해 부른다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
MARKER = "[kojiro_gap_observe]"

# 명세 §2.1 표 순서 그대로 — 이 튜플이 서식 계약의 정본이다.
FIELD_ORDER = (
    "ticker", "verdict", "caller", "ws_cmp", "arg_open", "ws_open", "prev_close",
    "gap_rate", "ws_gap", "ws_verdict", "cur", "gap_up", "gap_down",
)

VERDICTS = ("candidate", "no_data", "skip_up", "skip_down", "collapse", "pass")

PARAMS = {"gap_up_skip_pct": 5.0, "gap_down_skip_pct": -4.0}

# 131290 재현 케이스 (조사 §2 실측) — 프리장 시가 == 전일종가라 갭이 0 으로 보인다.
T_131290 = "131290"
PREV_131290 = 236500
WS_131290 = 236500      # 오염된 WS 캐시 시가(= 프리장 기준가)
KRX_131290 = 252500     # KRX 09:00 확정 시가 (경로 A 가 REST 로 읽는 값)


# ---------------------------------------------------------------------------
# 픽스처 / 헬퍼
# ---------------------------------------------------------------------------
@pytest.fixture
def observe():
    """leaf 진입점 — Green 이전에는 여기서 ImportError(= 의도된 RED)."""
    from src.engine.kojiro_gap_observe import observe_gap, reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    yield observe_gap
    reset_kojiro_gap_observe_cap()


@pytest.fixture
def ws_cache():
    """`scanner.ticker_prices` 를 테스트 스코프로 격리(전역 dict 오염 차단)."""
    from src.engine import scanner

    saved = dict(scanner.ticker_prices)
    scanner.ticker_prices.clear()
    yield scanner.ticker_prices
    scanner.ticker_prices.clear()
    scanner.ticker_prices.update(saved)


def rows(caplog):
    """캡처된 `[kojiro_gap_observe]` 행(포맷 완료 문자열) 목록."""
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


# --- 실제 호출자 shim (문자열 주입 금지 — 진짜 프레임을 만든다) -----------------
# leaf 를 **직접** 부르는 shim 은 depth=1 이 실제 호출자다
# (프로덕션은 leaf → check_buy_signal → 호출자 = depth 2).
def on_tick(observe, **kw):
    """risk.on_tick 경로(경로 B, 오염) 재현 shim."""
    return observe(depth=1, **kw)


def _swing_buy_poll_loop(observe, **kw):
    """scheduler._swing_buy_poll_loop 경로(경로 A, 깨끗) 재현 shim."""
    return observe(depth=1, **kw)


def call(observe, *, ticker=T_131290, verdict="pass", arg_open=10050,
         prev_close=10000, current_price=10100, params=None, depth=1):
    return observe(
        ticker, verdict,
        arg_open=arg_open, prev_close=prev_close, current_price=current_price,
        params=PARAMS if params is None else params, depth=depth,
    )


# ===========================================================================
# 1. 서식 — 마커 · 필드 순서 · 레벨
# ===========================================================================
def test_marker_prefix_and_field_order_are_fixed(observe, ws_cache, caplog):
    """§2.1 — 마커 접두 + 13개 필드가 **명세 순서 그대로** 나온다."""
    with caplog.at_level(logging.INFO):
        call(observe)
    got = rows(caplog)
    assert len(got) == 1, f"1행이어야 한다 — {got}"
    assert keys_in_order(got[0]) == FIELD_ORDER, (
        "필드 이름/순서는 과거 로그 대조 가능성 계약이다 — 실측 "
        f"{keys_in_order(got[0])}"
    )


def test_marker_level_is_info(observe, ws_cache, caplog):
    """§2.1 — INFO 다. WARNING 이면 20:10 `_aggregate_log_patterns` 가 패턴으로 집계해
    '경보' 로 오독되고, DEBUG 면 `_DbLogHandler`(INFO 컷)를 못 넘어 `system_logs` 에
    도달하지 못한다(cycle237 C237-L2-1)."""
    with caplog.at_level(logging.DEBUG):
        call(observe)
    recs = [r for r in caplog.records if r.getMessage().startswith(MARKER + " ")]
    assert recs and all(r.levelno == logging.INFO for r in recs), (
        f"레벨 실측 {[r.levelname for r in recs]}"
    )


def test_returns_none(observe, ws_cache, caplog):
    """반환값은 항상 None — 호출부는 바 statement 로만 쓴다."""
    with caplog.at_level(logging.INFO):
        assert call(observe) is None


# ===========================================================================
# 2. 131290 재현 — 뒤집힘이 **한 행 안에서** 보인다 (명세 §6.1 필수)
# ===========================================================================
def test_131290_path_a_shows_flip_within_one_row(observe, ws_cache, caplog):
    """경로 A(REST 252500) — `verdict=skip_up` 인데 `ws_verdict=pass`.

    "깨끗한 경로는 걸렀는데 오염 경로였으면 놓쳤을 종목" 이 grep 한 번에 나와야 한다.
    """
    ws_cache[T_131290] = {"current_price": 253000, "open_price": WS_131290}
    with caplog.at_level(logging.INFO):
        _swing_buy_poll_loop(
            observe, ticker=T_131290, verdict="skip_up", arg_open=KRX_131290,
            prev_close=PREV_131290, current_price=253000, params=PARAMS,
        )
    f = one(caplog)
    assert f["caller"] == "_swing_buy_poll_loop"
    assert f["verdict"] == "skip_up"
    assert f["arg_open"] == str(KRX_131290)
    assert f["ws_open"] == str(WS_131290)
    assert f["prev_close"] == str(PREV_131290)
    assert f["gap_rate"] == "6.77", "arg_open 기준 갭률, 소수 2자리"
    assert f["ws_gap"] == "0.00", "오염된 WS 시가 기준 반사실 갭률"
    assert f["ws_verdict"] == "pass", "같은 임계로 재판정 — 여기서 뒤집힘이 보인다"
    assert f["ws_cmp"] == "ws_ne"


def test_131290_path_b_ws_eq(observe, ws_cache, caplog):
    """경로 B(오염 236500) — `verdict=pass ws_cmp=ws_eq`.

    이 행만으로는 오염이 드러나지 않는다(그래서 §5 오프라인 조인이 필요하다) —
    대신 `arg_open`·`prev_close`·임계가 전부 있어 반사실 재계산이 **완결**된다.
    """
    ws_cache[T_131290] = {"current_price": 237000, "open_price": WS_131290}
    with caplog.at_level(logging.INFO):
        on_tick(
            observe, ticker=T_131290, verdict="pass", arg_open=WS_131290,
            prev_close=PREV_131290, current_price=237000, params=PARAMS,
        )
    f = one(caplog)
    assert f["caller"] == "on_tick"
    assert f["verdict"] == "pass"
    assert f["ws_cmp"] == "ws_eq"
    assert f["arg_open"] == str(WS_131290)
    assert f["gap_rate"] == "0.00"
    # 오프라인 조인에 필요한 재료가 전부 행에 있다
    for k in ("arg_open", "prev_close", "gap_up", "gap_down"):
        assert f[k] not in ("", "-"), f"{k} 결측 — 경로 B 반사실 재계산이 불가능해진다"


# ===========================================================================
# 3. verdict · ws_cmp · 임계
# ===========================================================================
@pytest.mark.parametrize("verdict", VERDICTS)
def test_all_six_verdicts_are_carried_verbatim(observe, ws_cache, caplog, verdict):
    with caplog.at_level(logging.INFO):
        call(observe, verdict=verdict)
    assert one(caplog)["verdict"] == verdict


def test_ws_cmp_absent_when_cache_missing(observe, ws_cache, caplog):
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000001")
    f = one(caplog)
    assert f["ws_cmp"] == "ws_absent"
    assert f["ws_open"] == "-"
    assert f["ws_gap"] == "-"
    assert f["ws_verdict"] == "-", "대조가 성립하지 않은 행 — '일치' 로 세면 안 된다"


def test_ws_cmp_eq_and_ne(observe, ws_cache, caplog):
    ws_cache["000002"] = {"open_price": 10050}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000002", arg_open=10050)
    assert one(caplog)["ws_cmp"] == "ws_eq"

    caplog.clear()
    ws_cache["000003"] = {"open_price": 10200}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000003", arg_open=10050)
    f = one(caplog)
    assert f["ws_cmp"] == "ws_ne"
    assert f["ws_open"] == "10200"


@pytest.mark.parametrize("arg_open,prev_close", [(0, 10000), (10050, 0), (0, 0)])
def test_gap_rate_dash_when_not_computable(observe, ws_cache, caplog, arg_open, prev_close):
    """`no_data` 코호트 — 산출 불가는 `-` 이지 `0.00` 이 아니다."""
    with caplog.at_level(logging.INFO):
        call(observe, verdict="no_data", arg_open=arg_open, prev_close=prev_close)
    f = one(caplog)
    assert f["gap_rate"] == "-", "0.00 으로 찍으면 '갭 없음' 과 '못 쟀음' 이 뭉개진다"


@pytest.mark.parametrize("ws_open,expected", [
    (10500, "skip_up"),    # 정확히 +5.00% == gap_up  → 경계 포함(>=)
    (10501, "skip_up"),
    (9600, "skip_down"),   # 정확히 -4.00% == gap_down → 경계 포함(<=)
    (9599, "skip_down"),
    (10050, "pass"),
])
def test_ws_verdict_uses_same_thresholds_inclusive(observe, ws_cache, caplog,
                                                   ws_open, expected):
    """`>=` / `<=` 경계 포함 — 부등호를 `>` / `<` 로 뒤집으면 이 테스트가 붉어진다."""
    ws_cache["000004"] = {"open_price": ws_open}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000004", arg_open=10050, prev_close=10000)
    assert one(caplog)["ws_verdict"] == expected


def test_ws_verdict_ignores_collapse_guard(observe, ws_cache, caplog):
    """§2.1 — `ws_verdict` 는 **갭 게이트만** 재현한다(붕괴 가드 제외).

    현재가가 시가보다 낮아도(붕괴) `ws_verdict` 는 여전히 `pass` 다.
    """
    ws_cache["000005"] = {"open_price": 10050}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000005", verdict="collapse",
             arg_open=10050, prev_close=10000, current_price=9000)
    f = one(caplog)
    assert f["verdict"] == "collapse"
    assert f["ws_verdict"] == "pass"
    assert f["cur"] == "9000", "붕괴 가드 사후 재구성용 현재가"


def test_thresholds_reflect_live_params_not_defaults(observe, ws_cache, caplog):
    """§2.1 — 임계는 **그 순간 실제 적용된** 값이다(장중 PUT 변경 추적).

    두 값을 서로 바꿔치기하는 뮤테이션도 여기서 잡힌다.
    """
    with caplog.at_level(logging.INFO):
        call(observe, params={"gap_up_skip_pct": 7.5, "gap_down_skip_pct": -2.5})
    f = one(caplog)
    assert float(f["gap_up"]) == 7.5
    assert float(f["gap_down"]) == -2.5


def test_arg_open_and_ws_open_are_not_swapped(observe, ws_cache, caplog):
    """정본 값 혼동은 판독을 통째로 뒤집는다 — 두 필드를 바꿔치기하면 붉어진다."""
    ws_cache["000006"] = {"open_price": 11111}
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000006", arg_open=22222, prev_close=10000)
    f = one(caplog)
    assert f["arg_open"] == "22222", "판정에 실제로 쓰인 값"
    assert f["ws_open"] == "11111", "WS 캐시 대조군"


# ===========================================================================
# 4. cap — 키 = (ticker, caller, verdict)
# ===========================================================================
def test_cap_same_triple_emits_once(observe, ws_cache, caplog):
    with caplog.at_level(logging.INFO):
        on_tick(observe, ticker="000007", verdict="pass", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
        on_tick(observe, ticker="000007", verdict="pass", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
    assert len(rows(caplog)) == 1


def test_cap_key_includes_caller(observe, ws_cache, caplog):
    """caller 를 키에서 빼면 '같은 ticker 가 경로 A·B 양쪽에서 심사받은 사실' 이
    지워진다 — 그게 이 사이클이 재려는 바로 그 값이다(명세 §2.3)."""
    kw = dict(ticker="000008", verdict="pass", arg_open=10050,
              prev_close=10000, current_price=10100, params=PARAMS)
    with caplog.at_level(logging.INFO):
        on_tick(observe, **kw)
        _swing_buy_poll_loop(observe, **kw)
    got = rows(caplog)
    assert len(got) == 2, "caller 만 달라도 발화해야 한다"
    assert {fields(g)["caller"] for g in got} == {"on_tick", "_swing_buy_poll_loop"}


def test_cap_key_includes_verdict_and_ticker(observe, ws_cache, caplog):
    with caplog.at_level(logging.INFO):
        on_tick(observe, ticker="000009", verdict="candidate", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
        on_tick(observe, ticker="000009", verdict="pass", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
        on_tick(observe, ticker="000010", verdict="pass", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
    assert len(rows(caplog)) == 3


def test_cap_resets_on_kst_date_rollover(observe, ws_cache, caplog):
    """날짜 리셋은 `KstDailyEmitCap` 자기 리셋에 맡긴다(호출부 날짜 블록 금지)."""
    kw = dict(ticker="000011", verdict="pass", arg_open=10050,
              prev_close=10000, current_price=10100, params=PARAMS)
    with caplog.at_level(logging.INFO):
        with freeze_time(datetime(2026, 9, 7, 9, 10, tzinfo=KST)):
            on_tick(observe, **kw)
            on_tick(observe, **kw)
        assert len(rows(caplog)) == 1
        with freeze_time(datetime(2026, 9, 8, 9, 10, tzinfo=KST)):
            on_tick(observe, **kw)
    assert len(rows(caplog)) == 2, "KST 날짜가 바뀌면 다시 1행"


def test_cap_does_not_reset_within_same_kst_day(observe, ws_cache, caplog):
    """23:00 → 익일 00:30 이 아닌 **같은 KST 날짜** 안에서는 리셋되지 않는다."""
    kw = dict(ticker="000012", verdict="pass", arg_open=10050,
              prev_close=10000, current_price=10100, params=PARAMS)
    with caplog.at_level(logging.INFO):
        with freeze_time(datetime(2026, 9, 7, 9, 5, tzinfo=KST)):
            on_tick(observe, **kw)
        with freeze_time(datetime(2026, 9, 7, 23, 59, tzinfo=KST)):
            on_tick(observe, **kw)
    assert len(rows(caplog)) == 1


# ===========================================================================
# 5. caller 해석 (§3.1)
# ===========================================================================
def test_caller_is_read_from_the_real_frame(observe, ws_cache, caplog):
    """문자열 주입이 아니라 실제 호출자 함수명이다."""
    with caplog.at_level(logging.INFO):
        on_tick(observe, ticker="000013", verdict="candidate", arg_open=10050,
                prev_close=10000, current_price=10100, params=PARAMS)
    assert one(caplog)["caller"] == "on_tick"


def test_unknown_caller_is_kept_verbatim(observe, ws_cache, caplog):
    """미지 호출자는 **원문 그대로** — 화이트리스트 정규화 금지.

    새 호출 경로가 생기면 그 사실이 로그에 드러나야 한다.

    ⚠️ 2026-09-07 테스트 결함 시정 — 이 테스트는 `depth=1` 로 "호출자 = 이 테스트
    함수" 를 기대했으나, `call()` **자신이 프레임 하나**라 `depth=1` 은 항상 `call`
    이다(실측 `caller=call`). 구현이 아니라 테스트가 틀렸다. 계약("미지 호출자
    원문 보존")은 그대로 지키되 깊이를 **2** 로 바로잡는다 — 프로덕션의
    `observe_gap` → `check_buy_signal` → 실제 호출자와 같은 프레임 수다.
    """
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000014", depth=2)   # 0=leaf, 1=call, 2=이 테스트 함수
    assert one(caplog)["caller"] == "test_unknown_caller_is_kept_verbatim", (
        "화이트리스트(`on_tick`/`_swing_buy_poll_loop`)에 없는 호출자 이름이 "
        "정규화되거나 `?` 로 뭉개졌다 — 새 호출 경로가 로그에서 보이지 않게 된다"
    )


def test_unknown_caller_is_not_normalized_to_a_known_label(observe, ws_cache, caplog):
    """정규화 금지의 **음성** 축 — 미지 호출자가 알려진 라벨로 둔갑하지 않는다."""
    def _kojiro_probe_zzz():
        observe("000025", "candidate", arg_open=10050, prev_close=10000,
                current_price=10100, params=PARAMS, depth=1)

    with caplog.at_level(logging.INFO):
        _kojiro_probe_zzz()
    caller = one(caplog)["caller"]
    assert caller == "_kojiro_probe_zzz", f"실측 caller={caller!r}"
    assert caller not in ("on_tick", "_swing_buy_poll_loop", "?", "unknown")


def test_caller_resolution_failure_is_question_mark(observe, ws_cache, caplog):
    """프레임 해석 실패는 `?` — 그리고 **행은 여전히 나온다**(침묵 금지)."""
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000015", depth=9999)
    f = one(caplog)
    assert f["caller"] == "?"
    assert f["ticker"] == "000015", "caller 실패가 행 전체를 삼키면 안 된다"


def test_depth_default_is_two(observe, ws_cache, caplog):
    """기본 depth=2 — leaf → `check_buy_signal` → 실제 호출자.

    kojiro 가 래퍼 메서드를 끼우면 이 전제가 어긋난다(AST 가드가 직접 호출을 강제).
    여기서는 프레임을 하나 더 쌓아 기본값이 실제로 2 임을 잰다.
    """
    def _outer():                      # depth 2 에서 보여야 할 이름
        def _inner():                  # depth 1
            observe("000016", "pass", arg_open=10050, prev_close=10000,
                    current_price=10100, params=PARAMS)
        _inner()

    with caplog.at_level(logging.INFO):
        _outer()
    assert one(caplog)["caller"] == "_outer"


# ===========================================================================
# 6. 비용 순서 (§3-4) — cap 을 통과한 뒤에만 일한다
# ===========================================================================
class _CountingPrices(dict):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.reads = 0

    def get(self, key, default=None):
        self.reads += 1
        return super().get(key, default)

    def __getitem__(self, key):
        self.reads += 1
        return super().__getitem__(key)


def test_cost_order_ws_cache_untouched_when_cap_blocks(observe, monkeypatch, caplog):
    """cap 이 막은 2회차는 `scanner.ticker_prices` 를 **읽지도 않는다**.

    틱당 수십~수백 회 도는 경로다 — cap 뒤 작업을 앞에 두면 관측이 비용이 된다.
    """
    from src.engine import scanner

    counting = _CountingPrices({"000017": {"open_price": 10050}})
    monkeypatch.setattr(scanner, "ticker_prices", counting)
    kw = dict(ticker="000017", verdict="pass", arg_open=10050,
              prev_close=10000, current_price=10100, params=PARAMS)
    with caplog.at_level(logging.INFO):
        on_tick(observe, **kw)
        after_first = counting.reads
        on_tick(observe, **kw)
    assert after_first >= 1, "1회차는 WS 캐시를 읽어야 한다(가드 비공허성)"
    assert counting.reads == after_first, (
        f"cap 차단 후에도 WS 캐시를 {counting.reads - after_first}회 읽었다 — "
        "cap peek 가 가장 먼저여야 한다"
    )


def test_cost_order_params_untouched_when_cap_blocks(observe, ws_cache, caplog):
    """cap 이 막은 2회차는 `params` 도 건드리지 않는다."""
    class _CountingParams(dict):
        reads = 0

        def get(self, key, default=None):
            type(self).reads += 1
            return super().get(key, default)

        def __getitem__(self, key):
            type(self).reads += 1
            return super().__getitem__(key)

    p = _CountingParams(PARAMS)
    kw = dict(ticker="000018", verdict="pass", arg_open=10050,
              prev_close=10000, current_price=10100, params=p)
    with caplog.at_level(logging.INFO):
        on_tick(observe, **kw)
        after_first = _CountingParams.reads
        on_tick(observe, **kw)
    assert after_first >= 1
    assert _CountingParams.reads == after_first


# ===========================================================================
# 7. never-raise + 무흔적 금지 (§3-1)
# ===========================================================================
def test_never_raises_when_params_is_hostile(observe, ws_cache, caplog):
    class _Boom(dict):
        def get(self, *a, **kw):
            raise RuntimeError("boom")

        def __getitem__(self, k):
            raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG):
        assert call(observe, ticker="000019", params=_Boom()) is None


def test_observer_failure_leaves_a_trace(observe, ws_cache, caplog):
    """무흔적 `pass` 금지(cycle258 카드 #5) — WARNING 1회/(marker,key)/일."""
    class _Boom(dict):
        def get(self, *a, **kw):
            raise RuntimeError("boom")

        def __getitem__(self, k):
            raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG):
        call(observe, ticker="000020", params=_Boom())
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING
             and r.getMessage().startswith(MARKER + " observer_failed")]
    assert warns, (
        "관측기 자기 실패가 흔적 없이 사라졌다 — "
        "`observer_trace.trace_observer_failure(marker, ticker, cap)` 를 쓴다. "
        f"실측 레코드: {[r.getMessage() for r in caplog.records]}"
    )
    assert "key=000020" in warns[0]


def test_never_raises_when_ws_cache_lookup_explodes(observe, monkeypatch, caplog):
    """WS 캐시 조회가 터져도 호출부로 새지 않는다."""
    from src.engine import scanner

    class _Boom(dict):
        def get(self, *a, **kw):
            raise RuntimeError("boom")

    monkeypatch.setattr(scanner, "ticker_prices", _Boom())
    with caplog.at_level(logging.DEBUG):
        assert call(observe, ticker="000021") is None


def test_never_raises_on_none_and_odd_inputs(observe, ws_cache, caplog):
    with caplog.at_level(logging.DEBUG):
        assert observe("000022", "pass", arg_open=None, prev_close=None,
                       current_price=None, params={}, depth=1) is None
        assert observe(None, "pass", arg_open=10050, prev_close=10000,
                       current_price=10100, params=PARAMS, depth=1) is None


# ===========================================================================
# 8. read-only (§3-2) — 어떤 dict 도 생성·변경하지 않는다
# ===========================================================================
def test_does_not_mutate_ws_cache_or_params(observe, ws_cache, caplog):
    ws_cache["000023"] = {"current_price": 10100, "open_price": 10050}
    ws_snapshot = {k: dict(v) for k, v in ws_cache.items()}
    params = dict(PARAMS)
    params_snapshot = dict(params)

    with caplog.at_level(logging.INFO):
        call(observe, ticker="000023", params=params)

    assert {k: dict(v) for k, v in ws_cache.items()} == ws_snapshot, (
        "`scanner.ticker_prices` 를 읽기만 해야 한다(cycle242 G-242-8 동형)"
    )
    assert params == params_snapshot, "`config.params` 를 읽기만 해야 한다"


def test_does_not_create_entries_for_unknown_ticker(observe, ws_cache, caplog):
    """미지 ticker 조회가 `ticker_prices` 에 빈 항목을 심으면 안 된다."""
    with caplog.at_level(logging.INFO):
        call(observe, ticker="000024")
    assert "000024" not in ws_cache


# ===========================================================================
# 9. `absorb_call_failure` — 호출 지점의 무흔적 `pass` 대체 (cycle258 카드 #5)
# ===========================================================================
def test_absorb_call_failure_emits_warning_trace(observe, ws_cache, caplog):
    """호출 지점이 관측 호출 실패를 삼킬 때 **흔적을 남긴다**.

    무흔적 `pass` 면 관측기가 죽어도 아무도 모르고, 그러면 이 마커의 **결측이
    "오염이 없었다" 로 오독된다**(명세 §1 판독 표 5행).
    """
    from src.engine.kojiro_gap_observe import absorb_call_failure

    with caplog.at_level(logging.DEBUG):
        assert absorb_call_failure("000026") is None
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING
             and r.getMessage().startswith(MARKER + " observer_failed")]
    assert warns and "key=000026" in warns[0], (
        f"WARNING 흔적 부재 — `logger.debug` 단독은 `_DbLogHandler`(INFO 컷)를 못 넘어 "
        f"`system_logs` 에 도달하지 않는다(cycle237 L2-1). 실측 "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_absorb_call_failure_never_raises_when_trace_explodes(observe, ws_cache,
                                                              monkeypatch, caplog):
    """흡수기 **자신**이 터져도 던지지 않는다.

    이 함수는 호출 지점의 `except` 절에서 불린다 — 여기서 던지면 그 예외가
    `check_buy_signal` 밖으로 나가 매수 경로가 끊긴다(= 관측이 매매를 죽인다).
    """
    import src.engine.kojiro_gap_observe as mod

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "trace_observer_failure", boom)
    with caplog.at_level(logging.DEBUG):
        assert mod.absorb_call_failure("000027") is None
