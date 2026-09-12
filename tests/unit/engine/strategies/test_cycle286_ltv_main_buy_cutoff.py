"""cycle286 Red — C2-a: LTV `main` 보드 신규 매수 15:20 KST 컷.

자문 정본 = cycle286 도메인 자문 §1 + §명세 S1 (2026-09-12).
사용자 지적(2026-09-12) = "15:30~16:00 에 LTV 시각컷이 없다, 기존설계가 남은 것 같다".

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 결함 (실측 재현 완료)

`session._BOARD_SCHEDULE` 의 MAIN 구간은 **09:00~15:39:59** 다(15:20~15:30 종가 단일가 +
15:30~15:40 종가 흡수 마진 포함 — 그 15:40 은 **청산** 마진으로 정해진 값이다). LTV 는
`DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main", "post_nxt")` 이고 15:20 컷이 **없어서**,
KRX 연속체결이 끝난 뒤인 15:20~15:39:59 에도 `board="main"` 으로 신규 매수 신호를 낸다.
2026-09-12 15:31 벽시계 실측에서 `Signal.BUY` 가 재현됐다.

피해는 두 구간이 다르다:

- **15:20~15:30 (종가 단일가, market_state K4, `order_divisions=("00","01")`)** — 시장가가
  **접수된다**. 거부라는 우연한 안전판이 없고, 15:20 `_force_clear_main_only` 는 이미
  지나가 있으므로 그 체결은 **당일 모드 그대로 오버나이트로 남는다**(`NEXT_DAY_CLEAR`·
  `gap_up_threshold`·트레일링은 전부 `_limit_up_reached` 분기 전용). 즉 오버나이트 리스크
  프레임이 0인 오버나이트 포지션이 생긴다.
- **15:30~15:40 (K5 장후 시간외 종가 `06` 전용 / N5 NXT 애프터 단일가)** — KRX 는 체결가가
  당일 종가로 **고정**이라 가격 정보량이 0 이고, NXT 프린트가 통합 채널로 섞여 들어오면
  KRX 기준 목표가를 타 시장 가격으로 대조한다. 게다가 우리 `OrderDivision` 은 `00`/`01`
  뿐이라 그 신호로 낸 주문은 **체결될 수 없다**(cycle229 가 VB 에서 실측한 APBK3013 →
  예외 전파 → 매일 15:30 WS 재연결).

그리고 `long_tail_volatility.py:76` 의 자기 주석은 이미 **`MAIN(09:00~15:20) 매수 가능`**
이라고 선언해 왔다. 이 사이클은 새 규칙을 만드는 게 아니라 그 계약을 코드로 만든다.

## Green 계약 (자문 §명세 S1)

| 항 | 내용 | 테스트 |
|---|---|---|
| S1-1 | `from datetime import ... time ...` 보강 (LTV 만 `time` 미import 였다) | `test_s1_*` |
| S1-2 | **모듈 상수** `MAIN_BUY_CUTOFF_KST = time(15, 20)` — `DEFAULT_PARAMS`/`PARAM_RANGES` **미편입** | `test_s1_*` · `test_s6_*` |
| S1-3 | 헬퍼 `_main_buy_cutoff_blocked(board, now)` — 보드 스코프 판정, hold 토큰 미참조 | `test_s2_*` |
| S1-4 | cap `KstDailyEmitCap` 1회/ticker/일, 날짜 자기 리셋 | `test_s5_*` |
| S1-5 | 게이트 = **발사점 안, cycle262 hold 블록 직후** → `Signal.NONE` | `test_s3_*` · `test_s4_*` |
| — | `board == "main"` 전용 — `pre_nxt`/`post_nxt` **무접촉** | `test_s3_5`~`test_s3_8` |
| — | baseline `_prev_price` 는 컷 구간에도 **계속 갱신**(동결 금지) | `test_s4_1`~`test_s4_3` |
| — | 청산·강제청산·수량 무접촉 | `test_s7_*` |
| — | 관측은 **행위 밖** (never-raise) | `test_s5_5`~`test_s5_6` |
| — | 신규 `DEFAULT_PARAMS` 킬스위치 키 **없음**(모듈 상수 = DB override 불가) | `test_s6_*` |

## 왜 킬스위치 파라미터를 만들지 않는가

이건 **매수를 막는** 통제다. cycle245 `max_lot_ratio_mult` 관례("키 부재 = OFF")를 따르면
*"설정이 없으면 오버나이트 진입이 열린다"* 가 정상 동작이 되고, 반대로 "키 부재 = ON" 은
P0-1 유령 키 사고 방향이다. **두 선례가 모두 부적합한 것이 곧 "키를 만들지 말라"는 신호**다.
게다가 `PUT /api/strategies/{id}/params` 는 미지 키를 조용히 버리고 `params` JSONB 를 통째로
덮으므로, 한 번의 PUT 이 컷을 조용히 죽인다. cycle229 G-2 가 VB 에서 같은 판단을 했다
(*"OVERNIGHT 금지는 DB 토글 하나로 뚫려선 안 되는 규칙"*).
장중 긴급 롤백 수단은 이미 있다 — `PUT {"tradable_boards": ["pre_nxt","post_nxt"]}`
(컷보다 **더 강한** 안전측 조작). 영구 롤백 = 1커밋 revert.

## freezegun 과 타임존 — 이 파일의 모든 시각 표기 규약

freezegun 은 naive 문자열을 **UTC** 로 동결한다. 따라서 이 파일의 `freeze_time` 인자는 전부
UTC 이고 KST = UTC + 9h 다(cycle229 `test_cycle229_vb_buy_cutoff.py` 규약 복제).

    freeze_time("2026-09-14 06:19:59")  →  KST 15:19:59  /  naive now().time() = 06:19:59
    freeze_time("2026-09-14 06:20:00")  →  KST 15:20:00  /  naive now().time() = 06:20:00
    freeze_time("2026-09-14 15:20:00")  →  KST 09-15 00:20 /  naive now().time() = 15:20:00

**naive 검출 양방향** — 창 안(KST 15:2x = 벽시계 06:2x) 테스트는 naive 면 "컷을 **놓친다**"
(BUY 가 나와 FAIL). `test_s3_9` 는 벽시계 15:20(KST 익일 00:20)에서 "naive 면 **엉뚱한 때
컷한다**"(NONE 이 나와 FAIL). 둘 중 하나만으로는 naive 구현이 절반을 우연히 통과한다.

2026-09-14(월)는 KRX 애프터마켓 시행 첫 영업일, 2026-09-15 는 화요일(날짜 리셋 검증용)이다.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_LTV_LOGGER = "src.engine.strategies.long_tail_volatility"
_MARKER = "[ltv_main_buy_cutoff]"
_CONST = "MAIN_BUY_CUTOFF_KST"

_TICKER = "005930"
_TICKER2 = "000660"
_PRDY = 70000               # 전일종가 — `min_prdy_rate=5.0` 을 통과시키는 값
_OPEN = 80000               # 보드 시가
_K = 0.5
_PREV_RANGE = 1000
_OFFSET = int(_PREV_RANGE * _K)     # 500
_TARGET = _OPEN + _OFFSET           # 80,500
_PRIME_PX = 80200                   # 목표가 아래 baseline

# ── UTC 동결 시각 ↔ KST (위 docstring 규약) ────────────────────────────────
_KST_1000 = "2026-09-14 01:00:00"          # KST 10:00:00 (창 밖, 정상 매수)
_KST_151959 = "2026-09-14 06:19:59"        # KST 15:19:59 (컷 1초 전)
_KST_152000 = "2026-09-14 06:20:00"        # KST 15:20:00 (경계 — 포함)
_KST_152001 = "2026-09-14 06:20:01"        # KST 15:20:01
_KST_152500 = "2026-09-14 06:25:00"        # KST 15:25:00 (컷 창 한복판)
_KST_152959 = "2026-09-14 06:29:59"        # KST 15:29:59 (종가 단일가 끝)
_KST_153500 = "2026-09-14 06:35:00"        # KST 15:35:00 (장후 시간외 종가)
_KST_153959 = "2026-09-14 06:39:59"        # KST 15:39:59 (MAIN 보드 마지막 초)
_KST_154100 = "2026-09-14 06:41:00"        # KST 15:41:00 (post_nxt 구간)
_KST_180000 = "2026-09-14 09:00:00"        # KST 18:00:00 (post_nxt 야간)
_KST_083000 = "2026-09-13 23:30:00"        # KST 08:30:00 (pre_nxt 프리장)
_WALL_1520_KST_0020 = "2026-09-14 15:20:00"   # 벽시계 15:20 = KST 09-15 00:20
_KST_152500_NEXT_DAY = "2026-09-15 06:25:00"  # 화요일 KST 15:25 (날짜 리셋)


# ===========================================================================
# 리그 — cycle262 `test_cycle262_open_entry_hold.py` 픽스처 패턴 재사용
# ===========================================================================
def _seed_target(strategy, ticker: str) -> None:
    """prepare() 결과 모사 — `_targets` 직접 시드 (base = prev_range × k)."""
    strategy._targets[ticker] = {
        "k": _K,
        "prev_range": _PREV_RANGE,
        "target_offset_base": _OFFSET,
        "target_offset": _OFFSET,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _activate(board: str) -> None:
    session_tracker._active = frozenset({MarketBoard(board)})


def _armed(
    monkeypatch,
    *,
    board: str = "main",
    boards: tuple[str, ...] | None = None,
    tickers: tuple[str, ...] = (_TICKER,),
) -> LongTailVolatilityStrategy:
    """돌파 1틱이면 BUY 가 나오는 최소 LTV rig.

    open 80,000 / offset 500 / target 80,500 / 전일종가 70,000.
    cycle272 — `board="main"` 확정은 `source="rest"` 없이는 게이트가 거부한다(기본 enforce).
    """
    from src.engine import scanner

    monkeypatch.setattr(
        scanner, "ticker_names", {_TICKER: "삼성전자", _TICKER2: "SK하이닉스"},
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {t: _PRDY for t in tickers})
    monkeypatch.setattr(session_tracker, "_active", frozenset())

    s = LongTailVolatilityStrategy(
        StrategyConfig(
            strategy_id="long_tail_volatility", name="롱테일 변동성", weight=0.3,
        )
    )
    if boards is not None:
        s.config.params["tradable_boards"] = list(boards)
    for tk in tickers:
        _seed_target(s, tk)
        for b in (boards or (board,)):
            s.on_open_price_confirmed(tk, open_price=_OPEN, board=b, source="rest")
    _activate(board)
    return s


def _prime(s, ticker: str = _TICKER, px: int = _PRIME_PX) -> Signal:
    """baseline 기록 틱 — 목표가 아래라 어떤 구현에서도 NONE."""
    return s.check_buy_signal(ticker, px, _OPEN)


def _breakout(s, ticker: str = _TICKER, px: int = _TARGET) -> Signal:
    return s.check_buy_signal(ticker, px, _OPEN)


def _marker_lines(caplog, marker: str = _MARKER) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정.

    ⚠️ CI 루트 로거는 DEBUG 라 무한정 세면 `observer_trace` 의 debug 흔적까지 잡힌다
    (`feedback_caplog_debug_level`). 실패 흔적은 정상 관측이 아니므로 제외한다.
    """
    out = []
    for r in caplog.records:
        if r.name != _LTV_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker) and "observer_failed" not in msg:
            out.append(msg)
    return out


def _field(line: str, name: str) -> str:
    """`name=value` 토큰 추출 (value 는 공백 전까지)."""
    m = re.search(rf"(?:^|\s){re.escape(name)}=(\S+)", line)
    assert m is not None, f"필드 `{name}=` 이 로그에 없다: {line!r}"
    return m.group(1)


#: cycle286 **이전** 의 LTV 인스턴스 emit cap 이름 전수(실측). 이 목록과의 차집합이
#: 곧 이 사이클이 새로 만든 cap 이다 — "개수 >= N" 단정은 이미 7개가 있어 공허하다.
_PREEXISTING_CAPS = frozenset({
    "_budget_clamp_logged",        # strategy_base — 예산 클램프
    "_account_gate_logged",        # cycle233 — 계좌 SOFT 게이트
    "_oversized_logged",           # cycle242 — 1주 폴백 과대 랏
    "_lot_cap_logged",             # cycle242 — K축 유닛 캡
    "_ratio_cap_logged",           # cycle245 — ρ축 명목 캡
    "_open_entry_hold_config_logged",   # cycle262
    "_open_entry_hold_blocked_logged",  # cycle262
})


def _new_caps(strategy) -> dict:
    """cycle286 이 새로 추가한 emit cap 만 (이름 → 인스턴스)."""
    from src.engine.daily_emit_cap import DailyEmitCap

    return {
        name: value
        for name, value in vars(strategy).items()
        if isinstance(value, DailyEmitCap) and name not in _PREEXISTING_CAPS
    }


# ===========================================================================
# S1 — 모듈 상수 (값 · 위치 · 타입)
# ===========================================================================
def test_s1_1_module_constant_exists_with_1520() -> None:
    """S1-2 (RED): `MAIN_BUY_CUTOFF_KST = time(15, 20)` 이 **모듈 레벨**에 존재.

    모듈 레벨이어야 하는 이유(cycle229 G-2) — 클래스 속성이나 `DEFAULT_PARAMS` 안으로
    들어가면 `{**DEFAULT_PARAMS, **config.params}` 머지를 타서 **DB 로 덮인다**.
    """
    from src.engine.strategies import long_tail_volatility as ltv_mod

    assert hasattr(ltv_mod, _CONST), (
        f"모듈 상수 `{_CONST}` 부재 — 컷 시각의 단일 출처가 없다"
    )
    got = getattr(ltv_mod, _CONST)
    assert isinstance(got, time), f"`{_CONST}` 는 `datetime.time` 이어야 한다 (실제 {got!r})"
    assert got == time(15, 20), (
        f"컷은 15:20 이다 — KRX 연속체결 종료(market_state K3.end)이고 "
        f"`TIME_KRX_MAIN_BUY_STOP`·`_force_clear_main_only` 와 같은 경계라야 "
        f"'청산한 종목을 1분 뒤 다시 사는' 모순이 원천 봉쇄된다. 실제 {got!r}"
    )


def test_s1_2_time_class_is_imported() -> None:
    """S1-1 (RED): LTV 가 `datetime.time` 을 import 한다 (7전략 중 LTV 만 예외였다)."""
    from src.engine.strategies import long_tail_volatility as ltv_mod

    assert getattr(ltv_mod, "time", None) is time, (
        "`from datetime import time` 보강 누락 — 모듈 상수를 선언할 수 없다"
    )


def test_s1_3_constant_is_not_a_param_key(monkeypatch) -> None:
    """S1-2 (RED): 컷 시각이 `config.params` 로 흘러들어가지 않는다(DB override 불가)."""
    s = _armed(monkeypatch)
    for key, value in s.config.params.items():
        assert not isinstance(value, time), (
            f"params[{key!r}] 가 `time` 값이다 — 컷 시각이 DB override 경로에 노출됐다"
        )


# ===========================================================================
# S2 — 헬퍼 `_main_buy_cutoff_blocked(board, now)`
# ===========================================================================
def test_s2_1_helper_exists_and_is_board_scoped(monkeypatch) -> None:
    """S1-3 (RED): 헬퍼가 `main` + 컷 이후에만 True.

    `check_buy_signal` 안에 보드 리터럴을 두면 cycle262 `G-262-5`
    (`test_g262_5_hold_has_no_board_coupling[ltv]`)가 즉시 RED 다 — 그 함수는
    hold 토큰을 참조하므로 `_hold_funcs` 멤버다. 리터럴은 헬퍼 안(또는
    `MarketBoard.MAIN.value`)에 둔다.
    """
    s = _armed(monkeypatch)
    assert hasattr(s, "_main_buy_cutoff_blocked"), "헬퍼 `_main_buy_cutoff_blocked` 부재"

    at = datetime(2026, 9, 14, 15, 25, 0, tzinfo=KST)
    before = datetime(2026, 9, 14, 15, 19, 59, tzinfo=KST)

    assert s._main_buy_cutoff_blocked("main", at) is True
    assert s._main_buy_cutoff_blocked("main", before) is False
    assert s._main_buy_cutoff_blocked("post_nxt", at) is False, (
        "post_nxt(15:40~19:50) 야간 매수는 스코프 밖 — 연속 상한가 종목 익일청산 모드 진입"
    )
    assert s._main_buy_cutoff_blocked("pre_nxt", at) is False, (
        "pre_nxt(08:00~08:50) 프리장 매수는 스코프 밖"
    )


def test_s2_2_helper_boundary_is_inclusive(monkeypatch) -> None:
    """S1-3 (RED): 경계 15:20:00 은 **포함**(`>=`) — VB `:894` 와 대칭."""
    s = _armed(monkeypatch)
    assert s._main_buy_cutoff_blocked(
        "main", datetime(2026, 9, 14, 15, 20, 0, tzinfo=KST)
    ) is True
    assert s._main_buy_cutoff_blocked(
        "main", datetime(2026, 9, 14, 15, 19, 59, 999999, tzinfo=KST)
    ) is False


# ===========================================================================
# S3 — 행위: 경계 전수 + 보드 스코프 + naive 역방향
# ===========================================================================
@freeze_time(_KST_1000)
def test_s3_1_before_cutoff_1000_then_buy(monkeypatch) -> None:
    """S1-5: KST 10:00 정상 매수 — 컷이 과도 차단하지 않는다(회귀 가드)."""
    s = _armed(monkeypatch)
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@freeze_time(_KST_151959)
def test_s3_2_at_151959_then_buy(monkeypatch) -> None:
    """S1-5 (경계 −1s): KST 15:19:59 은 아직 연속매매다 → BUY."""
    s = _armed(monkeypatch)
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize(
    "frozen, label",
    [
        (_KST_152000, "15:20:00 경계(포함)"),
        (_KST_152001, "15:20:01"),
        (_KST_152959, "15:29:59 종가 단일가 — 시장가가 접수되는 구간"),
        (_KST_153500, "15:35:00 장후 시간외 종가 — 체결가 고정"),
        (_KST_153959, "15:39:59 MAIN 보드 마지막 초"),
    ],
)
def test_s3_3_cut_window_main_then_none(monkeypatch, frozen: str, label: str) -> None:
    """S1-5 (RED): 컷 창 전수 — `main` 보드 신규 매수 차단."""
    with freeze_time(frozen):
        s = _armed(monkeypatch)
        assert _prime(s) == Signal.NONE
        got = _breakout(s)
    assert got == Signal.NONE, f"{label} 에 main 신규 매수가 발사됐다 (실제 {got})"


@freeze_time(_KST_152500_NEXT_DAY)
def test_s3_4_cut_holds_on_next_business_day(monkeypatch) -> None:
    """S1-5: 컷은 날짜에 의존하지 않는다 — 다음 영업일 15:25 도 차단."""
    s = _armed(monkeypatch)
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.NONE


@freeze_time(_KST_154100)
def test_s3_5_post_nxt_at_1541_then_buy(monkeypatch) -> None:
    """S1-5 (RED, 보드 스코프): 15:41 `post_nxt` 매수는 **무접촉**.

    `post_nxt`(15:40~19:50) 는 LTV 설계가 연속 상한가 종목 익일청산 모드 진입에
    쓰는 보드다(`long_tail_volatility.py:76-78`). 시계 단독 컷은 이걸 죽인다.
    """
    s = _armed(monkeypatch, board="post_nxt", boards=("pre_nxt", "main", "post_nxt"))
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@freeze_time(_KST_180000)
def test_s3_6_post_nxt_at_1800_then_buy(monkeypatch) -> None:
    """S1-5 (보드 스코프): 야간 18:00 `post_nxt` 매수 무접촉."""
    s = _armed(monkeypatch, board="post_nxt", boards=("pre_nxt", "main", "post_nxt"))
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@freeze_time(_KST_083000)
def test_s3_7_pre_nxt_at_0830_then_buy(monkeypatch) -> None:
    """S1-5 (보드 스코프): 08:30 `pre_nxt` 프리장 매수 무접촉."""
    s = _armed(monkeypatch, board="pre_nxt", boards=("pre_nxt", "main", "post_nxt"))
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@freeze_time(_KST_153500)
def test_s3_8_post_nxt_inside_cut_clock_then_buy(monkeypatch) -> None:
    """S1-5 (RED, 결정적): **컷 시각 안인데 보드가 post_nxt** 면 통과.

    시계 단독 컷(보드 무결합)이면 이 테스트가 죽는다 — 그것이 보드 스코프가 계약인 이유다.
    실제 운영에서 15:35 에 post_nxt 가 잡히는 일은 없지만, 이 단정이 시계 단독 구현을
    기계적으로 배제한다.
    """
    s = _armed(monkeypatch, board="post_nxt", boards=("pre_nxt", "main", "post_nxt"))
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@freeze_time(_WALL_1520_KST_0020)
def test_s3_9_naive_clock_does_not_block(monkeypatch) -> None:
    """S1-5 (RED, naive 역방향): 벽시계 15:20 = **KST 익일 00:20** → 컷 밖 → BUY.

    naive `datetime.now().time()` 구현은 여기서 NONE 을 돌려 FAIL 한다.
    `test_s3_3` 은 "naive 면 컷을 놓친다", 이 테스트는 "naive 면 엉뚱한 때 컷한다" 를 잡는다.
    """
    s = _armed(monkeypatch)
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


# ===========================================================================
# S4 — baseline 계약: 컷 구간에도 `_prev_price` 는 **계속 갱신**
# ===========================================================================
@freeze_time(_KST_152500)
def test_s4_1_baseline_keeps_updating_under_cut(monkeypatch) -> None:
    """S1-5 (RED): 컷 틱도 `_prev_price[ticker]["main"]` 을 갱신한다.

    게이트가 baseline 쓰기 **앞**에 있으면 baseline 이 동결돼 해제 후 첫 틱이 stale
    baseline 대비 거짓 돌파로 읽힌다(cycle233 C233-F1 / cycle262 주석). 발사점 배치의
    의도를 여기서 명시 고정한다 — 어느 쪽이든 **침묵은 금지**다.
    """
    s = _armed(monkeypatch)
    _prime(s)
    assert s._prev_price[_TICKER]["main"] == _PRIME_PX
    assert _breakout(s, px=_TARGET + 300) == Signal.NONE
    assert s._prev_price[_TICKER]["main"] == _TARGET + 300, (
        "컷 구간에서 baseline 이 동결됐다 — 게이트가 `_prev_price` 쓰기보다 앞에 있다"
    )


@freeze_time(_KST_152500)
def test_s4_2_baseline_dict_is_board_scoped(monkeypatch) -> None:
    """S1-5: 컷이 `post_nxt` baseline 을 오염시키지 않는다(보드별 키)."""
    s = _armed(monkeypatch, board="main", boards=("main", "post_nxt"))
    _prime(s)
    _breakout(s)
    assert "post_nxt" not in s._prev_price[_TICKER], (
        "컷 경로가 다른 보드의 baseline 을 건드렸다"
    )


@freeze_time(_KST_152500)
def test_s4_3_gate_comes_after_prdy_rate_filter(monkeypatch, caplog) -> None:
    """S1-5: 컷은 `min_prdy_rate` 필터보다 **뒤**다 = 게이트가 최상단이 아니다.

    전일대비 미달 종목은 컷 마커를 남기지 않는다 — 마커가 남으면 게이트가 발사점보다
    위로 올라갔다는 신호(would_buy 정본이 오염된다). caplog 검사가 없으면 "게이트를
    prdy 필터 위(= baseline 갱신보다도 앞)로 올린" 구현도 같은 `Signal.NONE` 을 내
    이 테스트를 통과시킨다 — 그 회귀는 `test_s4_1` baseline 계약이 전이적으로 잡지만,
    이 테스트 자체가 자신의 docstring 이 약속한 것(마커 부재)을 직접 검증해야 한다.
    """
    from src.engine import scanner

    s = _armed(monkeypatch)
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: 80000})  # prdy 0.6% < 5%
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        _prime(s)
        assert _breakout(s) == Signal.NONE
    assert _marker_lines(caplog) == [], (
        "prdy 필터로 탈락한 틱에 컷 마커가 남았다 — 게이트가 발사점보다 위로 올라갔다"
    )


@freeze_time(_KST_152500)
def test_s4_4_account_gate_remains_first_statement(monkeypatch, caplog) -> None:
    """cycle233 M6: 계좌 SOFT 게이트가 **첫 문장**이라 컷보다 먼저 차단한다.

    컷을 최상단에 넣으면 이 순서가 뒤집혀 `GATE_FIRST_FILES` AST 가드가 RED 다.
    게이트 활성일에는 컷 마커도 0행이어야 한다(알려진 비대칭 — LTV 는 계좌 게이트가
    첫 문장이라 그 뒤의 모든 관측이 함께 침묵한다).
    """
    from src.engine import account_risk_watcher

    s = _armed(monkeypatch)
    _prime(s)
    monkeypatch.setattr(account_risk_watcher, "is_soft_gated", lambda: True)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        assert _breakout(s) == Signal.NONE
    assert _marker_lines(caplog) == [], (
        "계좌 게이트가 막은 틱에 컷 마커가 남았다 — 컷이 게이트 앞으로 올라갔다"
    )


# ===========================================================================
# S5 — 관측 `[ltv_main_buy_cutoff]`: would_buy 정본 · cap · never-raise
# ===========================================================================
@freeze_time(_KST_152500)
def test_s5_1_marker_carries_would_buy_evidence(monkeypatch, caplog) -> None:
    """S1-5 (RED): 마커가 **무엇을 살 뻔했는지** 를 담는다.

    발사점 배치의 산출물이다 — `board`·`current_price`·`target`·`board_open`·`prev` 가
    전부 손에 있는 자리라야 D+1 판독이 성립한다.
    """
    s = _armed(monkeypatch)
    _prime(s)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        assert _breakout(s) == Signal.NONE
    lines = _marker_lines(caplog)
    assert len(lines) == 1, f"마커 1행이어야 한다 (실제 {len(lines)}행): {lines}"
    line = lines[0]
    assert _field(line, "ticker") == _TICKER
    assert _field(line, "board") == "main"
    assert int(_field(line, "current_price")) == _TARGET
    assert int(_field(line, "target")) == _TARGET
    assert int(_field(line, "board_open")) == _OPEN
    assert int(_field(line, "prev")) == _PRIME_PX


@freeze_time(_KST_152500)
def test_s5_2_marker_cap_is_one_per_ticker_per_day(monkeypatch, caplog) -> None:
    """S1-4 (RED): 같은 ticker 반복 돌파 → 마커 1행 (15:20~15:30 예상체결가 폭주 방어)."""
    s = _armed(monkeypatch)
    _prime(s)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        for px in (_TARGET, _TARGET + 100, _TARGET + 200, _TARGET + 300):
            assert s.check_buy_signal(_TICKER, px, _OPEN) == Signal.NONE
    assert len(_marker_lines(caplog)) == 1, "cap 미작동 — 로그 폭주(cycle237 계열)"


@freeze_time(_KST_152500)
def test_s5_3_cap_key_is_per_ticker(monkeypatch, caplog) -> None:
    """S1-4 (RED): cap 키는 ticker 단위 — 두 종목이면 2행."""
    s = _armed(monkeypatch, tickers=(_TICKER, _TICKER2))
    _prime(s, _TICKER)
    _prime(s, _TICKER2)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        assert _breakout(s, _TICKER) == Signal.NONE
        assert _breakout(s, _TICKER2) == Signal.NONE
    lines = _marker_lines(caplog)
    assert len(lines) == 2, f"종목별 cap 이 아니다 (실제 {len(lines)}행)"
    assert {_field(x, "ticker") for x in lines} == {_TICKER, _TICKER2}


def test_s5_4_cap_resets_next_kst_day(monkeypatch, caplog) -> None:
    """S1-4 (RED): 날짜 자기 리셋 — `KstDailyEmitCap`(cycle258) 재사용.

    `_reset_daily_state` 훅에 의존하면 서브클래스 override 하나로 관측이 영구 침묵한다.
    """
    with freeze_time(_KST_152500):
        s = _armed(monkeypatch)
        _prime(s)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
            assert _breakout(s) == Signal.NONE
        assert len(_marker_lines(caplog)) == 1

    with freeze_time(_KST_152500_NEXT_DAY):
        # 다음 영업일에는 `prepare()` 가 `_prev_price` 를 비운다(`:222`) — 그 상태를 모사한다.
        # 비우지 않으면 baseline 이 전일 돌파가(= target)에 머물러 `prev < target` 이
        # 거짓이 되고 돌파 자체가 성립하지 않는다(= cap 이 아니라 rig 가 침묵시킨다).
        s._prev_price.clear()
        _prime(s)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
            assert _breakout(s) == Signal.NONE
        assert len(_marker_lines(caplog)) == 1, "다음 KST 날짜에 cap 이 리셋되지 않았다"


@freeze_time(_KST_152500)
def test_s5_5_cap_uses_kst_daily_emit_cap(monkeypatch) -> None:
    """S1-4 (RED): 신규 cap 은 정확히 1개이고 `KstDailyEmitCap` 이다.

    신규 cap 클래스를 만들지 않는다(cycle258 카드 #4 표준 진입점). 그리고 cycle262 cap 과
    **슬롯을 공유하지 않는다** — 같은 슬롯을 다투면 config 1행이 그날의 blocked 표본을
    통째로 침묵시킨다(cycle236 '별개 cap 가드' / donchian OB-11 선례).
    """
    from src.engine.daily_emit_cap import KstDailyEmitCap

    s = _armed(monkeypatch)
    fresh = _new_caps(s)
    assert len(fresh) == 1, (
        f"cycle286 신규 emit cap 은 정확히 1개여야 한다 (실제 {sorted(fresh)}) — "
        "cap 부재이거나 cycle262 cap 을 재사용했다"
    )
    (name, cap), = fresh.items()
    assert isinstance(cap, KstDailyEmitCap), (
        f"`{name}` 이 `KstDailyEmitCap` 이 아니다 — 날짜 자기 리셋을 잃는다"
    )


@freeze_time(_KST_152500)
def test_s5_6_observation_failure_does_not_change_behavior(monkeypatch, caplog) -> None:
    """S1-5 (RED, never-raise): 관측이 터져도 `Signal.NONE` 은 그대로 수행된다.

    관측 예외가 `check_buy_signal` 을 뚫으면 `risk.on_tick` 이 그 종목의 나머지 평가를
    잃는다(cycle237 TE-2). **관측은 행위 밖**이다.
    """
    s = _armed(monkeypatch)
    _prime(s)

    def _boom(*_a, **_kw):
        raise RuntimeError("관측 폭발")

    fresh = _new_caps(s)
    assert fresh, "cycle286 신규 cap 인스턴스를 찾지 못했다"
    for cap in fresh.values():
        monkeypatch.setattr(cap, "should_emit", _boom)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        assert _breakout(s) == Signal.NONE, "관측 예외가 매수 판정을 바꿨다"


# ===========================================================================
# S6 — 킬스위치 파라미터 **금지** (모듈 상수 = DB override 불가)
# ===========================================================================
def test_s6_1_no_new_default_params_key() -> None:
    """S1-2 (RED): `DEFAULT_PARAMS` 키 집합이 cycle276 시점과 동일하다.

    매수를 **막는** 통제라 "키 부재 = OFF"(cycle245) 도 "키 부재 = ON"(cycle272) 도
    부적합하다. 두 선례가 모두 맞지 않는 것이 곧 "키를 만들지 말라"는 신호다.
    새 키 1개는 `param_catalog` 99→100 + 프론트 골든 픽스처 2개 재생성 +
    `DEFAULT_PARAMS` 세그먼트 sha 재핀까지 끌고 온다.
    """
    expected = {
        "tradable_boards", "k_period", "min_prdy_rate",
        "k_value_krx_main", "k_value_nxt_pre", "k_value_nxt_post", "exchange",
        "min_market_cap", "min_trade_amount", "max_scan_stocks",
        "exclude_consecutive_limit", "reentry_cooldown_days",
        "intraday_stop_loss", "limit_up_threshold", "overnight_stop_loss",
        "gap_up_threshold", "trailing_stop_rate",
        "position_ratio", "max_positions", "daily_loss_limit",
        "max_lot_ratio_mult", "open_entry_hold_secs", "open_price_scope_mode",
        "llm_gate_mode", "llm_gate_min_score", "llm_gate_daily_call_cap",
        "llm_gate_timeout_secs",
    }
    got = set(LongTailVolatilityStrategy.DEFAULT_PARAMS)
    assert got == expected, (
        f"신규 {sorted(got - expected)} / 삭제 {sorted(expected - got)} — "
        "cycle286 은 `DEFAULT_PARAMS` 무접촉이다(킬스위치 키 금지)"
    )


@freeze_time(_KST_152500)
def test_s6_2_params_cannot_disable_the_cut(monkeypatch) -> None:
    """S1-2 (RED): 어떤 `params` 주입으로도 컷이 꺼지지 않는다.

    `PUT /api/strategies/{id}/params` 가 미지 키를 조용히 버리므로, 컷이 파라미터에
    걸려 있으면 한 번의 PUT 이 오버나이트 금지를 조용히 죽인다.
    """
    s = _armed(monkeypatch)
    for key in (
        "main_buy_cutoff_enabled", "main_buy_cutoff_mode",
        "ltv_main_buy_cutoff", "main_buy_cutoff_kst", "buy_cutoff_enabled",
    ):
        s.config.params[key] = False
    s.config.params["main_buy_cutoff_mode"] = "off"
    _prime(s)
    assert _breakout(s) == Signal.NONE, "params 주입으로 컷이 꺼졌다 — DB 토글 경로 노출"


def test_s6_3_cut_not_in_param_ranges_or_int_params() -> None:
    """S1-2: 컷 관련 키가 `PARAM_RANGES`/`INT_PARAMS` 에 편입되지 않았다(AI 자문 자동적용 차단)."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    for key in tuple(PARAM_RANGES) + tuple(INT_PARAMS):
        assert "cutoff" not in key.lower(), (
            f"`{key}` 가 자동 튜닝 대상에 들어갔다 — 컷은 리스크 정체성 상수다"
        )


# ===========================================================================
# S7 — 청산 · 강제청산 · 수량 무접촉 (tradable_boards 는 매수 진입 전용)
# ===========================================================================
@freeze_time(_KST_152500)
def test_s7_1_intraday_stop_loss_still_fires_in_cut_window(monkeypatch) -> None:
    """루트 CLAUDE.md: 매도/손절은 어떤 보드·시각에서도 보드 가드 없이 작동."""
    s = _armed(monkeypatch)
    s.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=100_000, quantity=1,
        order_no="O-1", strategy_id="long_tail_volatility",
        buy_date=date(2026, 9, 14),
    )
    assert s.check_exit_signal(_TICKER, 96_000, _OPEN) == Signal.STOP_LOSS


@freeze_time(_KST_152500)
def test_s7_2_overnight_mode_exits_still_fire(monkeypatch) -> None:
    """S7: 상한가 모드(익일 청산) 손절도 컷 구간에서 그대로."""
    s = _armed(monkeypatch)
    s._limit_up_reached.add(_TICKER)
    s.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=100_000, quantity=1,
        order_no="O-2", strategy_id="long_tail_volatility",
        buy_date=date(2026, 9, 14),
    )
    assert s.check_exit_signal(_TICKER, 94_000, _OPEN) == Signal.STOP_LOSS


@freeze_time(_KST_152500)
def test_s7_3_force_clear_unchanged(monkeypatch) -> None:
    """S7: 15:20 강제청산 대상 산출은 컷과 무관 — 상한가 모드만 제외."""
    s = _armed(monkeypatch)
    for tk in (_TICKER, _TICKER2):
        s.state.positions[tk] = Position(
            ticker=tk, buy_price=100_000, quantity=1,
            order_no=f"O-{tk}", strategy_id="long_tail_volatility",
            buy_date=date(2026, 9, 14),
        )
    s._limit_up_reached.add(_TICKER2)
    assert s.check_force_clear() == [_TICKER]


@freeze_time(_KST_152500)
def test_s7_4_calc_buy_quantity_unchanged(monkeypatch) -> None:
    """S7: 수량 축 무접촉 — 컷은 신호만 막고 사이징을 건드리지 않는다."""
    s = _armed(monkeypatch)
    s.state.total_investment = 10_000_000
    assert s.calc_buy_quantity(_TARGET, _TICKER) > 0


@freeze_time(_KST_152500)
def test_s7_5_no_buy_signal_appended_when_cut(monkeypatch) -> None:
    """S1-5: 컷 틱은 `state.buy_signals` 에 아무것도 남기지 않는다(UI 오탐 차단)."""
    s = _armed(monkeypatch)
    _prime(s)
    before = list(s.state.buy_signals)
    assert _breakout(s) == Signal.NONE
    assert s.state.buy_signals == before, "차단된 신호가 buy_signals 에 적재됐다"
