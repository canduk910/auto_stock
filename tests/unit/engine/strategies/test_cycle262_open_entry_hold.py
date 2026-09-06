"""cycle262 Red — 09:00 직후 매수 보류 `open_entry_hold_secs` (VB + LTV).

자문 정본 = `_workspace/consult/2026-09-06_open_entry_hold.md`
조사 근거 = `_workspace/analysis/entry_price_0900_20260906/{code_trace.md,forensic.md}`
사용자 결정(2026-09-06) = 카드 ② "조사와 임시 매수 보류 함께" · 범위 = **VB + LTV 둘 다**.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 왜

VB 목표가의 기준 시가가 KRX 09:00 시가가 아니라 통합 채널 `H0UNCNT0` `fields[7]`
(세션 시가 = 프리장 체결이 있었으면 프리장 시가)다. 09:00~09:01:30 코호트는
"체결가 ≥ KRX시가+offset" 을 **20/20 전부 위반**(이후 구간 53/93=57%), Fisher p=6.4e-5.
이 보류는 **근본 시정이 아니라 지혈**이다 — 오염된 `[7]` 은 일-스코프 상수라 90초 뒤에도
값이 그대로다. 근본은 `[7]` 에 `[24] OPRC_HOUR` 스코프 필터(`src/realtime/**` = 8영역,
별도 승인 + 별도 자문).

## 계약 12항 ↔ 이 파일의 가드

| 항 | 내용 | 테스트 |
|---|---|---|
| C1 | 신규 키 `open_entry_hold_secs`, 기본 **90**, VB·LTV `DEFAULT_PARAMS` | `test_c1_*` |
| C2 | `int(get(k,0) or 0)` + `[0,600]` 클램프, **키 부재·None·파싱 실패 = 0 = OFF(fail-open)** | `test_c2_*` |
| C3 | KST `09:00:00 <= now < 09:00:00+hold` → `Signal.NONE`, **tz-aware 필수** | `test_c3_*` |
| C4 | 판정 자리 = 발사점(VB 는 계좌 게이트 **뒤**), 최상단 금지 | `test_c4_*` + AST |
| C5 | 보드 무관 — 시간창만으로 판정. 08:00~09:00 LTV 프리장 매수 무접촉 | `test_c5_*` |
| C6 | **보류 중에도 `_prev_price` baseline 갱신 계속** (해제 후 거짓 돌파 금지) | `test_c6_*` |
| C7 | `[open_entry_hold_config]` 1회/전략/일 INFO | `test_c7_*` |
| C8 | `[open_entry_hold_blocked]` 1회/(ticker,전략)/일 INFO = **would_buy 정본** | `test_c8_*` |
| C9 | `KstDailyEmitCap` 재사용(신규 cap 클래스 금지), 날짜 자기 리셋 | `test_c7_5` · `test_c8_5` + AST |
| C10 | 관측 실패는 매수 판정을 **절대** 바꾸지 않는다 | `test_c10_*` |
| C11 | `PARAM_RANGES`/`INT_PARAMS` 미편입 | `test_c11_*` + AST |
| C12 | 8영역·scheduler·타 전략 5파일 diff 0 | ~~`test_c12_*`~~ — **cycle262 커밋(92bc140) 후 삭제됨**(cycle263) |

⚠️ C12 는 `git diff HEAD` 로 범위를 재는 **사이클 한정** 가드였다. cycle262 가 커밋되는
순간 공허해졌고(diff 소멸), 그대로 두면 그 뒤 *무관한* 사이클의 diff 를 재서 무조건
붉어진다 — 실제로 cycle263 워킹트리를 "허용 밖 src 파이썬 파일 변경" 으로 잡았다
(cycle240 A11b · cycle252 G-252-5b 와 같은 고아 가드 사고). 2026-09-06 cycle263 이
`test_c12_1`/`test_c12_2` + `_ALLOWED_SRC_PY`/`_FORBIDDEN_PATHS` 를 삭제했다.
8영역의 **영구** 가드는 `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` 가 계속
들고 있으므로 이 삭제로 잃는 커버리지는 없다.

## freezegun 과 타임존 — 이 파일의 모든 시각 표기 규약

freezegun 은 naive 문자열을 **UTC** 로 동결한다. 이 파일의 `freeze_time` 인자는 전부 UTC 이고
KST = UTC + 9h 다. 마침 **KST 09:00 == UTC 00:00** 이라 대응이 읽기 쉽다.

    freeze_time("2026-09-06 23:59:59.9")  →  KST 2026-09-07 08:59:59.9
    freeze_time("2026-09-07 00:00:00")    →  KST 2026-09-07 09:00:00
    freeze_time("2026-09-07 00:01:30")    →  KST 2026-09-07 09:01:30
    freeze_time("2026-09-07 09:00:30")    →  KST 2026-09-07 18:00:30  ← naive 역방향 검출

**naive 구현 검출 양방향**: 창 안(KST 09:00:30 = 벽시계 00:00:30) 테스트는 naive 면
"컷을 놓친다"(BUY 가 나와 FAIL). `test_c3_7_*` 는 벽시계 09:00:30(KST 18:00:30)에서
"naive 면 엉뚱한 때 막는다"(NONE 이 나와 FAIL). 둘 중 하나만으로는 naive 가 절반을 우연히 통과한다.

2026-09-07 은 월요일(발효 첫 영업일), 2026-09-08 은 화요일(날짜 리셋 검증용)이다.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

KEY = "open_entry_hold_secs"
_M_CONFIG = "[open_entry_hold_config]"
_M_BLOCKED = "[open_entry_hold_blocked]"

_VB_LOGGER = "src.engine.strategies.volatility_breakout"
_LTV_LOGGER = "src.engine.strategies.long_tail_volatility"

_TICKER = "005930"
_TICKER2 = "000660"
_PRDY = 70000          # 전일종가 — LTV `min_prdy_rate=5.0` 필터를 통과시키는 값
_OPEN = 80000          # 보드 시가
_OFFSET = 500          # prev_range 1000 × k 0.5
_TARGET = _OPEN + _OFFSET   # 80,500
_PRIME_PX = 80200      # 목표가 아래 baseline
_K = 0.5
_PREV_RANGE = 1000

# ── UTC 동결 시각 ↔ KST (위 docstring 규약) ────────────────────────────────
_KST_0830 = "2026-09-06 23:30:00"        # KST 08:30:00 (프리장 한복판)
_KST_085900 = "2026-09-06 23:59:00"      # KST 08:59:00
_KST_08595990 = "2026-09-06 23:59:59.900000"  # KST 08:59:59.9 (창 시작 0.1초 전)
_KST_090000 = "2026-09-07 00:00:00"      # KST 09:00:00.0 (창 시작, 경계 포함)
_KST_090005 = "2026-09-07 00:00:05"      # KST 09:00:05 (그날 첫 평가 모사)
_KST_090030 = "2026-09-07 00:00:30"      # KST 09:00:30
_KST_090100 = "2026-09-07 00:01:00"      # KST 09:01:00
_KST_090129 = "2026-09-07 00:01:29"      # KST 09:01:29 (hold−1s)
_KST_090130 = "2026-09-07 00:01:30"      # KST 09:01:30 (정확히 09:00:00+hold, 창 밖)
_KST_090135 = "2026-09-07 00:01:35"      # KST 09:01:35 (해제 후 재돌파)
_KST_090959 = "2026-09-07 00:09:59"      # KST 09:09:59 (클램프 600 창 안)
_KST_091000 = "2026-09-07 00:10:00"      # KST 09:10:00 (클램프 600 경계 = 창 밖)
_KST_1000 = "2026-09-07 01:00:00"        # KST 10:00:00
_KST_1500 = "2026-09-07 06:00:00"        # KST 15:00:00
_WALL_090030_KST_1800 = "2026-09-07 09:00:30"   # 벽시계 09:00:30 = KST 18:00:30
_KST_090030_NEXT_DAY = "2026-09-08 00:00:30"    # 화요일 KST 09:00:30

_ABSENT = object()   # "키 자체가 없다" 센티널


# ===========================================================================
# 리그 — cycle229 `test_cycle229_vb_buy_cutoff.py` 픽스처 패턴 재사용
# ===========================================================================
def _seed_target(strategy, ticker: str) -> None:
    """prepare() 결과 모사 — `_targets` 직접 시드 (base = prev_range × k)."""
    base = int(_PREV_RANGE * _K)
    strategy._targets[ticker] = {
        "k": _K,
        "prev_range": _PREV_RANGE,
        "target_offset_base": base,
        "target_offset": base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _activate(board: str) -> None:
    session_tracker._active = frozenset({MarketBoard(board)})


def _armed(
    kind: str,
    monkeypatch,
    *,
    board: str = "main",
    boards: tuple[str, ...] | None = None,
    hold=_ABSENT,
    tickers: tuple[str, ...] = (_TICKER,),
):
    """돌파 1틱이면 BUY 가 나오는 최소 rig.

    open 80,000 / offset 500 / target 80,500 / 전일종가 70,000.
    `hold` 를 주면 `config.params[KEY]` 를 그 값으로 강제(`_ABSENT` = DEFAULT_PARAMS 그대로).
    """
    from src.engine import scanner

    monkeypatch.setattr(
        scanner, "ticker_names", {_TICKER: "삼성전자", _TICKER2: "SK하이닉스"},
    )
    monkeypatch.setattr(
        scanner, "ticker_prev_close", {t: _PRDY for t in tickers},
    )
    monkeypatch.setattr(session_tracker, "_active", frozenset())

    if kind == "vb":
        s = VolatilityBreakoutStrategy(
            StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
        )
    else:
        s = LongTailVolatilityStrategy(
            StrategyConfig(strategy_id="long_tail_volatility", name="롱테일 변동성", weight=0.3)
        )

    if boards is not None:
        s.config.params["tradable_boards"] = list(boards)
    if hold is not _ABSENT:
        s.config.params[KEY] = hold

    for t in tickers:
        _seed_target(s, t)
        for b in (boards or (board,)):
            s.on_open_price_confirmed(t, open_price=_OPEN, board=b)
    _activate(board)
    return s


def _logger_name(kind: str) -> str:
    return _VB_LOGGER if kind == "vb" else _LTV_LOGGER


def _module(kind: str):
    from src.engine.strategies import long_tail_volatility as ltv_mod
    from src.engine.strategies import volatility_breakout as vb_mod
    return vb_mod if kind == "vb" else ltv_mod


def _prime(s, ticker: str = _TICKER, px: int = _PRIME_PX) -> Signal:
    """baseline 기록 틱 — 목표가 아래라 어떤 구현에서도 NONE."""
    return s.check_buy_signal(ticker, px, _OPEN)


def _breakout(s, ticker: str = _TICKER, px: int = _TARGET) -> Signal:
    return s.check_buy_signal(ticker, px, _OPEN)


def _marker_lines(caplog, marker: str, logger_name: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정.

    ⚠️ CI 루트 로거는 DEBUG 라 무한정 세면 `observer_trace` 의 debug 흔적까지 잡힌다.
    실패 흔적(`... observer_failed key=...`)은 **정상 관측이 아니므로** 제외한다 —
    C10 이 그 분리를 직접 검정한다.
    """
    out = []
    for r in caplog.records:
        if r.name != logger_name or r.levelno < logging.INFO:
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


_KINDS = ("vb", "ltv")


# ===========================================================================
# C1 — 신규 키 + 기본값 90 (VB·LTV 양쪽)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
def test_c1_1_default_params_has_key_with_90(kind: str) -> None:
    """C1 (RED): `open_entry_hold_secs` 가 두 전략 `DEFAULT_PARAMS` 에 **90** 으로 존재.

    `DEFAULT_PARAMS` 키여야 하는 이유(자문 §2.4) — 이건 **임시** 조치라 근거가 뒤집히면
    장중에 꺼야 하는데, 모듈 상수는 재배포가 필요하고 cycle232 D6 가 보유 중 장중 push 를
    금지한다 ⇒ 되돌릴 수 없는 임시 조치가 된다. 파라미터 키여야 `PUT` 한 번으로 즉시 끈다.

    그리고 `_load_strategy_config`/`PUT /params` 는 **`if key in params` 오버레이**라
    DEFAULT_PARAMS 에 없는 키는 DB 에서 조용히 버려진다 = 배포 전 DB 선반영은 무음 실패다.
    """
    cls = VolatilityBreakoutStrategy if kind == "vb" else LongTailVolatilityStrategy
    assert KEY in cls.DEFAULT_PARAMS, (
        f"{cls.__name__}.DEFAULT_PARAMS 에 `{KEY}` 부재 — DB 오버레이가 이 키를 버린다"
    )
    assert cls.DEFAULT_PARAMS[KEY] == 90, (
        f"기본값은 90 초여야 한다 (자문 §2.2 — 위반율 100%→83% 절벽). "
        f"실제 {cls.DEFAULT_PARAMS[KEY]!r}"
    )


@pytest.mark.parametrize("kind", _KINDS)
def test_c1_2_key_survives_merge(monkeypatch, kind: str) -> None:
    """C1: `__init__` 머지(`{**DEFAULT_PARAMS, **config.params}`) 후에도 런타임에 존재."""
    s = _armed(kind, monkeypatch)
    assert s.config.params.get(KEY) == 90


# ===========================================================================
# C2 — fail-open 격자 (키 부재·None·""·"abc"·-5·0 = OFF)
# ===========================================================================
_OFF_GRID = [
    pytest.param(_ABSENT, id="absent"),
    pytest.param(None, id="none"),
    pytest.param("", id="empty-string"),
    pytest.param("abc", id="garbage-string"),
    pytest.param(-1, id="negative-1"),
    pytest.param(-5, id="negative-5"),
    pytest.param(-600, id="negative-600"),
    pytest.param(0, id="explicit-zero"),
    # ── 적대 검증 HIGH (2026-09-06): `int(float("inf"))` 는 `OverflowError` 다.
    # `1e400` 은 **표준 유효 JSON** 이라 starlette `json.loads`/pydantic 파서가
    # 둘 다 `inf` 로 만들고, `ParamsRequest.params` 는 float 를 그대로 통과시키며
    # `update_params` 는 검증 없이 기존 키를 덮는다 — 즉 자문 §5 가 "장중 유일
    # 실효 롤백 수단" 으로 지정한 바로 그 PUT 경로가 주입구다. 좁은 튜플
    # `(TypeError, ValueError)` 로 잡으면 이 예외가 `check_buy_signal` 최상단에서
    # 전파돼 `risk.on_tick`(전략별 try 없음) → `handler.py` re-raise → **WS 재연결
    # 루프**가 된다. 여기는 관측이 아니라 행위 입력이라 C10 의 try/except 로도
    # 안 덮인다.
    pytest.param(float("inf"), id="json-1e400-inf-overflowerror"),
    pytest.param(float("-inf"), id="negative-inf-overflowerror"),
    pytest.param(float("nan"), id="nan-valueerror"),
]

# 위 격자에서 "실효값이 0" 임을 계약 레벨(마커)로 읽을 수 있는 행 — `_ABSENT` 는
# `source` 가 `db` 로 나오지만 `hold_secs`/`until` 은 동일하다.
_OFF_UNTIL = "09:00:00"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("raw", _OFF_GRID)
@freeze_time(_KST_090030)
def test_c2_1_fail_open_grid_means_off(monkeypatch, kind: str, raw, caplog) -> None:
    """C2 (RED): 결측·None·파싱 실패·음수·`inf`·`nan`·0 은 전부 **OFF = 현행 행위(BUY)**.

    `int(params.get(KEY, 0) or 0)` 후 `[0, 600]` 클램프 — 어떤 결측도 매수를 막지 않는다.
    **fail-closed 절대 금지**: 키가 사라졌을 때 조용히 매수를 막는 방향은 P0-1 유령 키
    (`ticker_prices["acml_vol"]` 대입부 0)가 BFB/VCP 를 전 기간 체결 0건으로 만든 바로 그
    경로다. 코드 기본값 90 은 `DEFAULT_PARAMS` 가 제공하고, 폴백 0 은 **계약**이다.

    ⚠️ 키를 지우는 것(`absent`)은 `params.pop` 으로 재현한다 — 머지 후 dict 이므로
    "DB 가 키를 지웠다" 가 아니라 "코드 기본값까지 사라진 최악" 을 모사한다.

    ⚠️ **`Signal.BUY` 만으로는 부족하다**(적대 검증 LOW). 그 단언은 `hold_secs <= 0`
    인 **어떤** 값에서도 참이라, 하한 클램프(`if secs < 0: return 0`)를 통째로 지워
    `-5` 가 그대로 흘러도 초록이다. 그러면 D+1 로그에
    `[open_entry_hold_config] hold_secs=-5 until=08:59:55` — 개장 **5초 전**에 끝나는
    창 — 이 찍혀 이 마커의 존재 이유(실효값 노출, 자문 §2.5)가 무너진다. 그래서
    **실효값을 마커로 읽어** 0 임을 못 박는다(상한 클램프 `test_c2_3` 과 대칭).
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch)
    if raw is _ABSENT:
        s.config.params.pop(KEY, None)
    else:
        s.config.params[KEY] = raw

    _prime(s)
    assert _breakout(s) == Signal.BUY, (
        f"`{KEY}={raw!r}` 는 OFF 여야 한다 (fail-open). 매수가 막혔다면 fail-closed 구현 — "
        "P0-1 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이다"
    )

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, f"OFF 상태에서도 config 카나리아 1행이어야 한다: {lines}"
    assert _field(lines[0], "hold_secs") == "0", (
        f"`{KEY}={raw!r}` 의 **실효값**이 0 이 아니다: {lines[0]!r} — 클램프가 빠졌다. "
        "매매 행위는 등가여도(창 길이 ≤ 0 → 항상 창 밖) 마커가 거짓말을 하면 "
        "운영자가 보류의 on/off 를 판정할 수 없다"
    )
    assert _field(lines[0], "until") == _OFF_UNTIL, (
        f"창 끝이 09:00:00 이 아니다: {lines[0]!r} — 음수가 그대로 흘러 개장 **이전**을 "
        "가리키는 창이 만들어졌다"
    )


@pytest.mark.parametrize("kind", _KINDS)
def test_c2_2_ninety_holds_then_releases(monkeypatch, kind: str) -> None:
    """C2 (RED): 90 = 창 [09:00:00, 09:01:30). 09:01:29 보류 / 09:01:30 매수."""
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090129):
        assert _breakout(s) == Signal.NONE
    with freeze_time(_KST_090130):
        # 보류 틱이 baseline 을 80,500 으로 올렸으므로 같은 가격은 재돌파가 아니다 →
        # 해제 확인은 baseline 을 되돌린 뒤(가격 후퇴) 재돌파로 한다.
        assert _breakout(s, px=80100) == Signal.NONE
        assert _breakout(s) == Signal.BUY, "09:01:30 정각은 창 밖 — 정상 매수"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("raw", [601, 10000])
def test_c2_3_upper_clamp_600(monkeypatch, kind: str, raw: int) -> None:
    """C2 (RED): 601·10000 은 **600 으로 클램프**된다.

    09:09:59 = 창 안(보류) / **09:10:00 정각 = 창 밖(매수)**. 09:10:00 이 판별점이다 —
    클램프가 없으면 601 은 09:10:01 까지, 10000 은 11:46:40 까지 막는다(오전 전체 무매매).
    """
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=raw)
        _prime(s)
    with freeze_time(_KST_090959):
        assert _breakout(s) == Signal.NONE, f"{raw}s → 600s 클램프 창 안이어야 한다"
    with freeze_time(_KST_091000):
        assert _breakout(s, px=80100) == Signal.NONE   # baseline 되돌리기
        assert _breakout(s) == Signal.BUY, (
            f"`{KEY}={raw}` 가 600 으로 클램프되지 않았다 — 상한 없는 값이 오전을 통째로 막는다"
        )


# ===========================================================================
# C3 — 시각 경계 + tz-aware
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_08595990)
def test_c3_1_before_window_buys(monkeypatch, kind: str) -> None:
    """C3 (보존 대조군): KST 08:59:59.9 = 창 시작 0.1초 전 → **매수**.

    이 케이스가 깨지면 창이 위로 새어 08:00~09:00 프리장 매수(LTV)를 잠식한 것이다.
    """
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    assert datetime.now(KST).hour == 8
    assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize("kind", _KINDS)
def test_c3_2_window_open_boundary_is_closed(monkeypatch, kind: str) -> None:
    """C3 (RED): KST 09:00:00.000 **정각부터** 보류 (하한 경계 포함, `<=`)."""
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090000):
        assert datetime.now(KST).strftime("%H:%M:%S") == "09:00:00"
        assert _breakout(s) == Signal.NONE, "09:00:00 정각은 창 안(경계 포함)"


@pytest.mark.parametrize("kind", _KINDS)
def test_c3_3_mid_window_holds(monkeypatch, kind: str) -> None:
    """C3 (RED): KST 09:00:30 (실측 조기 코호트 중앙 시각대) → 보류.

    naive `datetime.now()` 구현이면 벽시계 00:00:30 이라 창 밖으로 읽혀 BUY → FAIL.
    """
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE


@pytest.mark.parametrize("kind", _KINDS)
def test_c3_4_exact_hold_boundary_is_open(monkeypatch, kind: str) -> None:
    """C3 (RED): 정확히 `09:00:00 + hold` = **창 밖** (상한 경계 배타, `<`)."""
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090130):
        assert datetime.now(KST).strftime("%H:%M:%S") == "09:01:30"
        assert _breakout(s) == Signal.BUY, "상한 경계는 배타 — 09:01:30 은 정상 매수창"


@pytest.mark.parametrize("kind", _KINDS)
def test_c3_5_after_window_buys(monkeypatch, kind: str) -> None:
    """C3 (보존): KST 10:00 → 매수 (창 밖)."""
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_1000):
        assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize("kind", _KINDS)
def test_c3_6_afternoon_buys(monkeypatch, kind: str) -> None:
    """C3 (보존): KST 15:00 → 매수 (VB 는 15:20 컷 이전이라 여전히 매수창)."""
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_1500):
        assert _breakout(s) == Signal.BUY


def test_c3_7_naive_wallclock_does_not_block(monkeypatch) -> None:
    """C3 (RED, TZ 역방향): 벽시계 09:00:30 = **KST 18:00:30** → 매수.

    naive `datetime.now()` 구현이면 벽시계 09:00:30 이 창 안으로 읽혀 NONE → FAIL.
    `test_c3_3` 과 짝: c3_3 = "naive 면 컷을 놓친다" / c3_7 = "naive 면 엉뚱한 때 컷한다".

    VB 는 `BUY_CUTOFF_KST=15:20` 때문에 KST 18:00 에 어차피 NONE 이라 이 축을 못 잰다 →
    **LTV(post_nxt 15:40~19:50 매수 가능) 단독**으로 검정한다.
    """
    with freeze_time("2026-09-07 08:59:00"):   # KST 17:59
        s = _armed("ltv", monkeypatch, board="post_nxt", boards=("main", "post_nxt"))
        s.config.params[KEY] = 90
        _prime(s)
    with freeze_time(_WALL_090030_KST_1800):
        assert datetime.now(KST).strftime("%H:%M:%S") == "18:00:30"
        assert datetime.now().strftime("%H:%M:%S") == "09:00:30"   # naive = UTC 벽시계
        assert _breakout(s) == Signal.BUY, (
            "KST 18:00:30 은 보류 창이 아니다. FAIL 이면 게이트가 naive 벽시계를 읽고 있다 "
            "(cycle229 AST 가드가 잡는 그 결함)"
        )


# ===========================================================================
# C4 — 판정 자리 (계좌 게이트가 먼저)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c4_1_account_gate_evaluated_first(monkeypatch, kind: str, caplog) -> None:
    """C4 (RED): 계좌 SOFT 게이트가 **먼저** 평가된다 — 보류 마커는 찍히지 않는다.

    VB 는 발사점 블록 안에서 `_account_soft_gate_blocked` **바로 뒤**, LTV 는 계좌 게이트가
    함수 최상단이라 그보다 뒤. 어느 쪽이든 계좌 게이트가 서면 보류 판정에 도달하지 않는다.

    이 순서를 뒤집으면 `[open_entry_hold_blocked]`(would_buy 정본)가 **계좌 차단 사건까지**
    would_buy 로 기록해 이 사이클의 핵심 산출물이 오염된다.
    """
    caplog.set_level(logging.INFO)
    from src.engine import account_risk_watcher
    monkeypatch.setattr(account_risk_watcher, "is_soft_gated", lambda: True)

    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    assert _breakout(s) == Signal.NONE

    blocked = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert blocked == [], (
        f"계좌 게이트로 차단된 사건이 `{_M_BLOCKED}` 에 would_buy 로 섞였다: {blocked}"
    )
    gate = [r.getMessage() for r in caplog.records if "[account_gate_skip]" in r.getMessage()]
    assert gate, "계좌 게이트가 평가되지 않았다 — rig 전제 붕괴"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c4_2_hold_is_not_at_function_top(monkeypatch, kind: str, caplog) -> None:
    """C4 (RED): 보류는 **발사점**이다 — 목표가 미달 틱에는 아무 마커도 찍지 않는다.

    함수 최상단에 두면 (a) `_prev_price` baseline 이 동결되고(C233-F1 = C6)
    (b) 목표가·baseline 이 안 잡혀 **would_buy 를 기록할 수 없다** = 결함의 증거를
    스스로 지운다(자문 §2.3-2 · §4.2).

    창 안이지만 돌파가 아닌 틱(80,200)에서 `[open_entry_hold_blocked]` 가 찍히면
    판정이 위로 올라간 것이다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    assert _prime(s) == Signal.NONE           # 첫 틱(baseline 기록)
    assert _prime(s, px=80300) == Signal.NONE  # 창 안, 목표가 미달

    blocked = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert blocked == [], (
        f"목표가 미달 틱에 `{_M_BLOCKED}` 가 찍혔다 ({len(blocked)}행) — 판정이 발사점이 "
        "아니라 함수 최상단에 있다. would_buy 가 아니라 'tick 이 있었다' 를 기록하는 셈이다"
    )


# ===========================================================================
# C5 — 보드 무관 + 프리장 무접촉
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("board", ["main", "pre_nxt", "post_nxt"])
def test_c5_1_board_independent(monkeypatch, kind: str, board: str) -> None:
    """C5 (RED): 같은 시각이면 보드가 무엇이든 판정이 같다 (시간창 단독).

    09:00:00~09:00:30 은 세션 트래커 30초 주기 때문에 보드가 아직 `pre_nxt` 로 잡힐 수
    있는데(`session.py` `_session_loop`), 그건 설계 의도가 아니라 **stale 캐시 산물**이다.
    보드로 분기하면 그 30초가 통째로 구멍이 된다.
    """
    all_boards = ("main", "pre_nxt", "post_nxt")
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, board=board, boards=all_boards, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE, (
            f"board={board} 에서 보류가 안 걸렸다 — 판정이 보드에 결합돼 있다"
        )


def test_c5_2_ltv_pre_market_buy_untouched(monkeypatch, caplog) -> None:
    """C5 (보존): LTV 의 진짜 프리장 매수(KST 08:30, pre_nxt)는 **창 밖 = 무접촉**.

    프리장 구간의 `[7]` 은 그 보드의 올바른 기준가다(오염이 아니다 — 자문 §2.1).
    이 사이클이 08:00~09:00 매수를 건드리면 범위를 넘은 것이다.
    """
    caplog.set_level(logging.INFO)
    with freeze_time(_KST_0830):
        s = _armed("ltv", monkeypatch, board="pre_nxt", hold=90)
        _prime(s)
        assert _breakout(s) == Signal.BUY
        assert _marker_lines(caplog, _M_BLOCKED, _LTV_LOGGER) == []
        assert _marker_lines(caplog, _M_CONFIG, _LTV_LOGGER) == [], (
            "09:00 이전에 config 마커가 찍혔다 — 마커는 '09:00 이후 첫 평가' 계약이다"
        )


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_0830)
def test_c5_3_no_marker_before_open(monkeypatch, kind: str, caplog) -> None:
    """C5·C7 (RED): 09:00 **이전**에는 두 마커 모두 0행 — VB·LTV **양쪽**.

    ⚠️ 이 가드가 `test_c5_2`(LTV 단독)와 별도로 필요한 이유(적대 검증 LOW): config
    카나리아의 `if now < start: return` 게이트를 **VB 에서만** 지우는 뮤테이션이
    LTV 픽스처만 쓰는 c5_2 를 통과한다. 지금 프로덕션에서 VB 가 09:00 이전에 평가되지
    않는 것은 `tradable_boards=("main",)` 라는 **DB 설정** 덕이지 코드 계약이 아니다 —
    운영자가 `pre_nxt` 를 넣거나(사이클 26 이전 형상) 리팩터가 그 한 줄을 지우면 VB
    카나리아가 프리장 틱마다 `until` 이 아직 오지 않은 창을 찍고, 정작 09:00 이후의
    진짜 카나리아는 cap 에 막혀 사라진다.

    그래서 리그로 보드 게이트를 우회해(`_armed` 는 `check_buy_signal` 을 직접 부른다)
    **마커 0행만** 단언한다 — 매수 성립 여부는 묻지 않으므로 VB 의 프리장 매수 정책
    (사이클 26)과 충돌하지 않는다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, board="pre_nxt", hold=90)
    _prime(s)
    _breakout(s)

    name = _logger_name(kind)
    assert _marker_lines(caplog, _M_CONFIG, name) == [], (
        f"{kind}: 09:00 이전에 config 마커가 찍혔다 — '09:00 이후 첫 평가' 게이트가 없다"
    )
    assert _marker_lines(caplog, _M_BLOCKED, name) == [], (
        f"{kind}: 09:00 이전에 blocked 마커가 찍혔다 — 창 밖에서 보류가 걸렸다"
    )


# ===========================================================================
# C6 — baseline 갱신 (이 사이클에서 가장 중요한 회귀 가드)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
def test_c6_1_baseline_updates_during_hold(monkeypatch, kind: str) -> None:
    """C6 (RED): 보류된 틱도 `_prev_price` 를 갱신한다.

    보류 코드가 baseline 갱신(`self._prev_price[t][board] = current_price`) **뒤**에
    와야만 성립한다 = C4 배치의 직접 검정.
    """
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
        assert s._prev_price[_TICKER]["main"] == _PRIME_PX
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE
    assert s._prev_price[_TICKER]["main"] == _TARGET, (
        "보류 틱이 baseline 을 갱신하지 않았다 — 판정이 baseline 갱신보다 **앞**에 있다. "
        "cycle233 C233-F1 이 계좌 게이트를 최상단에서 내린 바로 그 결함이다"
    )


@pytest.mark.parametrize("kind", _KINDS)
def test_c6_2_no_false_breakout_after_release(monkeypatch, kind: str) -> None:
    """C6 (RED, 핵심): 창 해제 뒤 첫 틱이 **거짓 돌파**가 되지 않는다.

    창 안에서 이미 목표가를 넘었다면 baseline 도 그 값이므로 해제 후 `prev < target` 이
    거짓 → 매수 없음. 최상단 배치면 baseline 이 80,200 에 동결돼 09:01:30 의 **95,000원**
    틱이 `80,200 < 80,500 <= 95,000` 으로 읽혀 **진입가 상한 없는 추격 매수**가 된다
    (VB 는 추격 상한이 없고 당일 15:20 청산이다 = 하루 중 손익비가 가장 나쁜 진입).
    """
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE
    with freeze_time(_KST_090130):
        assert s.check_buy_signal(_TICKER, 95000, _OPEN) == Signal.NONE, (
            "해제 후 첫 틱이 거짓 돌파로 읽혔다 — 보류 구간에 baseline 이 동결됐다. "
            "보류가 '90초 뒤 훨씬 비싼 가격에 사는 장치' 로 변질된다"
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_c6_3_genuine_recross_after_release_buys(monkeypatch, kind: str) -> None:
    """C6 (RED): 해제 뒤 **진짜** 재돌파는 정상 매수한다 (자문 §후속검증 합성 시리즈).

    09:00:20 첫 MAIN 틱 → 09:00:30 돌파(보류) → 09:01:00 후퇴(baseline 하강) →
    09:01:35 재돌파 → BUY. 보류가 그 종목을 하루 종일 죽이면 안 된다.
    """
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE
    with freeze_time(_KST_090100):
        assert _prime(s, px=80100) == Signal.NONE     # 후퇴 — baseline 80,100
    with freeze_time(_KST_090135):
        assert _breakout(s) == Signal.BUY, (
            "해제 후 재돌파가 막혔다 — 보류가 종목을 영구 차단하고 있다"
        )


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c6_4_exit_path_untouched(monkeypatch, kind: str) -> None:
    """C6 (보존): 보류는 **매수 전용** — 창 안에서도 청산은 정상 평가된다.

    `tradable_boards` 독트린과 같은 계약. 창 안 90초 동안 손절이 멈추면 개장 직후
    급락 구간이 통째로 무방비가 된다.
    """
    s = _armed(kind, monkeypatch, hold=90)
    if kind == "vb":
        s.config.params["stop_loss_main"] = -3.0
    s.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=_OPEN, quantity=1,
        order_no="O-262", strategy_id=s.strategy_id,
    )
    assert s.check_exit_signal(_TICKER, 70000, _OPEN) == Signal.STOP_LOSS


# ===========================================================================
# C7 — `[open_entry_hold_config]`
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_1_config_fields(monkeypatch, kind: str, caplog) -> None:
    """C7 (RED): config 마커 필드 = `strategy` · `hold_secs` · `until` · `source`.

    `[ratio_cap_config]`(cycle245) 선례 — **실제 적용값 노출**이 목적이다. 자문 §2.5 가
    "fail-open 이되 침묵은 안 된다" 고 못 박은 그 채널이고, 이게 없으면 "꺼져 있는데
    아무도 모르는" 상태가 생긴다.

    `source` 규약(이 Red 가 정의) — 적용값이 코드 기본값(`DEFAULT_PARAMS[KEY]`)과 다르면
    `db`(DB/PUT 오버레이가 실효 중), 같으면 `default`.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    _breakout(s)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, f"config 마커 1행이어야 한다. 실제 {len(lines)}행: {lines}"
    line = lines[0]
    assert _field(line, "strategy") == s.strategy_id
    assert _field(line, "hold_secs") == "90"
    assert _field(line, "until") == "09:01:30"
    assert _field(line, "source") == "default"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_2_config_source_db_on_override(monkeypatch, kind: str, caplog) -> None:
    """C7 (RED): 오버레이 값이 실효 중이면 `source=db` + 그 값·창 끝이 반영된다."""
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=60)
    _prime(s)
    _breakout(s)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1
    assert _field(lines[0], "hold_secs") == "60"
    assert _field(lines[0], "until") == "09:01:00"
    assert _field(lines[0], "source") == "db"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_3_config_emitted_even_when_off(monkeypatch, kind: str, caplog) -> None:
    """C7 (RED): **OFF 여도 config 는 찍힌다** — 침묵 차단이 이 마커의 존재 이유다.

    hold=0 이면 매수는 정상(BUY)이지만 "오늘 이 전략의 보류는 꺼져 있다" 가 로그에 남아야
    한다. 안 남기면 자문 §2.5 의 fail-open 이 곧 무성한 침묵이 된다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=0)
    _prime(s)
    assert _breakout(s) == Signal.BUY

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, f"OFF 상태의 config 마커가 없다: {lines}"
    assert _field(lines[0], "hold_secs") == "0"
    assert "until=" in lines[0]


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_4_config_capped_once_per_day(monkeypatch, kind: str, caplog) -> None:
    """C7 (RED): 1회/전략/일 — 같은 날 평가가 여러 번이어도 1행."""
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90, tickers=(_TICKER, _TICKER2))
    for t in (_TICKER, _TICKER2):
        _prime(s, ticker=t)
        _breakout(s, ticker=t)
        _breakout(s, ticker=t, px=80600)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, f"config 는 전략당 하루 1행. 실제 {len(lines)}행"


@pytest.mark.parametrize("kind", _KINDS)
def test_c7_5_config_cap_resets_next_day(monkeypatch, kind: str, caplog) -> None:
    """C7·C9 (RED): 날짜 경계에서 **훅 없이** 스스로 풀린다 (`KstDailyEmitCap`).

    `_reset_daily_state()` 훅에 의존하면 서브클래스 override 하나로 관측이 영구 침묵한다.
    """
    caplog.set_level(logging.INFO)
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        _breakout(s)
        assert len(_marker_lines(caplog, _M_CONFIG, _logger_name(kind))) == 1
    with freeze_time(_KST_090030_NEXT_DAY):
        _breakout(s, px=80100)
        _breakout(s)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 2, f"날짜 경계 자기 리셋 실패 (총 {len(lines)}행)"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_6_config_reemits_on_value_change(monkeypatch, kind: str, caplog) -> None:
    """C7 (RED): 같은 날 **값이 바뀌면** config 가 한 행 더 나온다 (cap 키 값-민감).

    cap 키는 `cfg|<초>` 다 — 단일 키(`"cfg"`)로 바꾸는 뮤테이션은 정상 경로 테스트
    (같은 값 반복 평가)를 전부 통과하지만 **장중 롤백 확인 채널을 없앤다**:

      09:00:05  `[open_entry_hold_config] hold_secs=90 until=09:01:30 source=default`
      09:00:20  운영자가 `PUT /params {"open_entry_hold_secs": 0}` — 보유 중 장중에는
                이 PUT 이 **유일한** 롤백 수단이다(cycle232 D6 가 재시작을 금지하고
                `strategy_config` SQL UPDATE 는 다음 재시작에서만 반영된다).
      09:00:25  값-민감이면 `hold_secs=0 until=09:00:00 source=db` **2행째**가 남고,
                단일 키면 1행에서 멈춰 운영자는 PUT 이 실제로 in-memory 에 먹혔는지
                (cycle245 가 겪은 무음 실패인지) 로그로 확인할 길이 없다.

    라우트는 `strategy.config.params[key]` 를 제자리에서 덮으므로 그 대입이 PUT 모사다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1 and _field(lines[0], "hold_secs") == "90"

    s.config.params[KEY] = 0          # ← PUT /params 모사 (in-memory 즉시 반영)
    _prime(s)

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 2, (
        f"값이 바뀌었는데 config 재발화가 없다 (총 {len(lines)}행) — cap 키가 값-비민감이다. "
        "장중 PUT 롤백이 먹혔는지 확인할 유일한 채널이 사라진다"
    )
    assert [_field(x, "hold_secs") for x in lines] == ["90", "0"]
    assert _field(lines[1], "until") == "09:00:00"
    assert _field(lines[1], "source") == "db"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c7_7_config_survives_one_shot_log_failure(monkeypatch, kind: str, caplog) -> None:
    """C7·D-3 (RED): config 는 **peek → 로그 → mark** 순서다 (cycle226 D-3).

    `mark_emitted` 를 `logger.info` **앞**으로 옮기는 뮤테이션은 정상 경로에서 완전히
    무증상이다. 유일한 렌즈 = 로깅 핸들러가 그날 딱 한 번 실패하고 곧 복구되는 경우
    (`_DbLogHandler` 의 DB 쓰기 스파이크가 실제 형태다):

      - 올바른 순서: log 가 던졌으니 mark 안 함 → 복구 후 재평가에서 **1행**
      - mark 선행:   이미 cap 소진 → 그날 `[open_entry_hold_config]` **영영 0행**
                     = "보류가 켜졌는지 꺼졌는지 아무도 모르는" 상태(자문 §2.5 가
                     막으려던 바로 그 침묵)

    ⚠️ 폭발기를 `_prime` **전에** 설치한다 — 뒤에 설치하면 그 prime 이 이미 cap 을
    소진해 emit 이 실행조차 안 된다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    disarm = _explode_hold_emits(monkeypatch, kind, once=True)

    assert _prime(s) == Signal.NONE          # 첫 평가에서 config emit 1회 폭발
    assert disarm() == 1, "config emit 이 실행되지 않았다 — 리그 전제 붕괴"
    assert _marker_lines(caplog, _M_CONFIG, _logger_name(kind)) == []

    _prime(s)                                 # 핸들러 복구 후 재평가
    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, (
        f"복구 후 config 마커가 {len(lines)}행 — 0 이면 `mark_emitted` 가 `logger.info` "
        "보다 앞이다(로그 자기실패 1회가 그날의 카나리아를 통째로 지웠다)"
    )
    assert _field(lines[0], "hold_secs") == "90"


@freeze_time(_KST_090030)
def test_c7_8_canary_vs_account_gate_asymmetry(monkeypatch, caplog) -> None:
    """C7 (봉인): 계좌 SOFT 게이트 활성일의 카나리아 — **VB 는 남고 LTV 는 안 남는다**.

    적대 검증(LOW)이 "LTV 카나리아를 게이트 앞으로 올려 비대칭을 없애라" 고 권고했으나
    **그 이동은 cycle233 M6 계약과 충돌한다** — LTV 는 `GATE_FIRST_FILES` 멤버라
    `_account_soft_gate_blocked` If 가 `check_buy_signal` 의 **첫 문장**이어야 하고
    (`test_cycle233_ast_account_risk.py::test_gate_first_strategies_have_gate_as_first_statement`),
    로그 emit 은 부작용이라 그 앞에 올 수 없다. 실측으로 확인했다(옮기면 그 가드 RED).
    VB 는 `GATE_PRE_BUY_FILES` 라 게이트가 발사 직전이고, 카나리아는 그보다 위 →
    게이트 활성일에도 남는다.

    그래서 권고 대신 **현상을 계약으로 못 박고 문서화**한다(권고의 대안 경로 그대로):
    "계좌 게이트 활성일에는 LTV config 마커가 없다" 를 판독 문서
    (`_workspace/00_leader_trading_rules.md` §5)에 명시했고, 게이트 배치 자체를 바꾸는
    시정은 후속 F-6 이다. 이 테스트는 그 비대칭이 **의도**임을 고정해, 누군가 LTV
    카나리아를 올려 cycle233 가드를 깨거나 VB 카나리아를 내려 관측을 잃으면 붉어진다.

    ⚠️ 양쪽 공통 계약 = **게이트가 막은 틱은 would_buy 가 아니다** → blocked 마커 0행.
    """
    caplog.set_level(logging.INFO)
    from src.engine import account_risk_watcher
    monkeypatch.setattr(account_risk_watcher, "is_soft_gated", lambda: True)

    seen: dict[str, tuple[int, int]] = {}
    for kind in _KINDS:
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
        assert _breakout(s) == Signal.NONE
        name = _logger_name(kind)
        seen[kind] = (
            len(_marker_lines(caplog, _M_CONFIG, name)),
            len(_marker_lines(caplog, _M_BLOCKED, name)),
        )

    assert seen["vb"][0] == 1, (
        f"VB config 카나리아가 {seen['vb'][0]}행 — VB 는 게이트가 발사 직전이라 "
        "게이트 활성일에도 그날 적용값 증거가 남아야 한다"
    )
    assert seen["ltv"][0] == 0, (
        f"LTV config 카나리아가 {seen['ltv'][0]}행 — 게이트보다 앞으로 올라갔다면 "
        "cycle233 M6(게이트 = check_buy_signal 첫 문장) 계약 위반이다"
    )
    for kind in _KINDS:
        assert seen[kind][1] == 0, (
            f"{kind}: 계좌 게이트가 막은 틱이 would_buy 로 기록됐다 — blocked 마커 오염"
        )


# ===========================================================================
# C8 — `[open_entry_hold_blocked]` (would_buy 정본)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c8_1_blocked_fields(monkeypatch, kind: str, caplog) -> None:
    """C8 (RED): would_buy 정본의 필드 10종.

    `ticker, board, current_price, target, board_open, prev, k, offset, elapsed_secs,
    prdy_close` — 진입 다리(무엇을·언제·얼마에 살 뻔했나)를 전부 보존해야 청산 다리를
    시뮬레이션할 수 있다(자문 §4.2 — 실현 손익은 어떤 로그로도 못 되살리므로 **추정**만
    가능하고, 그 시뮬레이터 정확도는 상관 0.79 로 이미 측정돼 있다).

    ⚠️ `prev` 는 **갱신 전** baseline 이다. 갱신 후 값(= current_price)을 실으면
    "이전가 = 현재가" 인 무의미한 기록이 된다.
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    assert _breakout(s) == Signal.NONE

    lines = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert len(lines) == 1, f"blocked 마커 1행이어야 한다. 실제 {len(lines)}행: {lines}"
    line = lines[0]
    assert _field(line, "ticker") == _TICKER
    assert _field(line, "board") == "main"
    assert _field(line, "current_price") == str(_TARGET)
    assert _field(line, "target") == str(_TARGET)
    assert _field(line, "board_open") == str(_OPEN)
    assert _field(line, "prev") == str(_PRIME_PX)
    assert re.match(r"^0\.5", _field(line, "k")), f"k 필드가 0.5 가 아니다: {line}"
    assert _field(line, "offset") == str(_OFFSET)
    assert _field(line, "elapsed_secs") == "30"
    assert _field(line, "prdy_close") == str(_PRDY)


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c8_2_blocked_capped_per_ticker(monkeypatch, kind: str, caplog) -> None:
    """C8 (RED): 1회/(ticker,전략)/일 — 같은 종목 2회 차단 → 1행."""
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    assert _breakout(s) == Signal.NONE
    assert _breakout(s, px=80100) == Signal.NONE   # baseline 되돌리기
    assert _breakout(s) == Signal.NONE             # 두 번째 차단

    lines = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert len(lines) == 1, f"ticker cap 미적용 — {len(lines)}행"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c8_3_blocked_cap_is_per_ticker_not_global(monkeypatch, kind: str, caplog) -> None:
    """C8 (RED): 다른 종목은 별도 1행 — 전략 단위 cap 이면 would_buy 표본이 통째로 사라진다."""
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90, tickers=(_TICKER, _TICKER2))
    for t in (_TICKER, _TICKER2):
        _prime(s, ticker=t)
        assert _breakout(s, ticker=t) == Signal.NONE

    lines = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert len(lines) == 2, f"종목별 cap 이 아니다 — {len(lines)}행: {lines}"
    assert {_field(x, "ticker") for x in lines} == {_TICKER, _TICKER2}


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c8_4_no_blocked_marker_when_off(monkeypatch, kind: str, caplog) -> None:
    """C8 (RED): OFF 면 blocked 마커 0행 (차단이 없으니 would_buy 도 없다)."""
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=0)
    _prime(s)
    assert _breakout(s) == Signal.BUY
    assert _marker_lines(caplog, _M_BLOCKED, _logger_name(kind)) == []


@pytest.mark.parametrize("kind", _KINDS)
def test_c8_5_blocked_cap_resets_next_day(monkeypatch, kind: str, caplog) -> None:
    """C8·C9 (RED): 날짜 경계 자기 리셋 — 같은 종목이 이틀 차단되면 총 2행."""
    caplog.set_level(logging.INFO)
    with freeze_time(_KST_085900):
        s = _armed(kind, monkeypatch, hold=90)
        _prime(s)
    with freeze_time(_KST_090030):
        assert _breakout(s) == Signal.NONE
        assert len(_marker_lines(caplog, _M_BLOCKED, _logger_name(kind))) == 1
    with freeze_time(_KST_090030_NEXT_DAY):
        assert _breakout(s, px=80100) == Signal.NONE
        assert _breakout(s) == Signal.NONE

    lines = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert len(lines) == 2, f"날짜 경계 자기 리셋 실패 (총 {len(lines)}행)"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c8_6_blocked_survives_one_shot_log_failure(monkeypatch, kind: str, caplog) -> None:
    """C8·D-3 (RED): blocked 도 **peek → 로그 → mark** 다 (cycle226 D-3).

    `mark_emitted` 선행 뮤테이션은 정상 경로에서 무증상이지만, 로그가 그날 한 번
    실패하면 **그 종목의 would_buy 정본이 하루치 통째로 사라진다** — 이 사이클의
    핵심 산출물(자문 §4.2)이 "로그 한 번 실패" 로 소실되는데 예외는 조용히 흡수되므로
    아무 신호도 남지 않는다.

    ⚠️ `_prime` 으로 config cap 을 먼저 소진시킨 **뒤** 폭발기를 설치해 blocked emit
    만 겨냥한다(두 마커가 한 폭발을 나눠 갖지 않게).
    """
    caplog.set_level(logging.INFO)
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)                                  # config 카나리아 소진 (정상 발화)
    disarm = _explode_hold_emits(monkeypatch, kind, once=True)

    assert _breakout(s) == Signal.NONE          # blocked emit 1회 폭발 (행위는 불변)
    assert disarm() == 1, "blocked emit 이 실행되지 않았다 — 리그 전제 붕괴"
    assert _marker_lines(caplog, _M_BLOCKED, _logger_name(kind)) == []

    _breakout(s, px=80100)                      # baseline 되돌리기
    assert _breakout(s) == Signal.NONE          # 복구 후 재차단
    lines = _marker_lines(caplog, _M_BLOCKED, _logger_name(kind))
    assert len(lines) == 1, (
        f"복구 후 blocked 마커가 {len(lines)}행 — 0 이면 `mark_emitted` 가 `logger.info` "
        "보다 앞이다(그 종목의 would_buy 정본이 하루치 사라졌다)"
    )
    assert _field(lines[0], "ticker") == _TICKER


# ===========================================================================
# C10 — 관측 실패 격리 (행위는 cap 밖)
# ===========================================================================
def _explode_hold_emits(monkeypatch, kind: str, *, once: bool = False):
    """`[open_entry_hold*` 로 시작하는 INFO 만 폭발시킨다. 해제 콜백을 반환한다.

    구현 헬퍼 이름을 모른 채 emit 만 정확히 겨냥하기 위해 **로거 레벨**에서 터뜨린다.
    기존 매수 신호 로그("변동성돌파 매수 신호 …")는 살려 둬야 정상 경로가 검정된다.

    Args:
        once: True 면 **첫 마커 INFO 한 번만** 던지고 그 뒤로는 정상 통과한다
            (로깅 핸들러가 그날 딱 한 번 스파이크로 실패하고 곧 복구되는 실제 형태 —
            `_DbLogHandler` 의 DB 쓰기 스파이크가 대표적이다). peek→로그→mark 순서
            회귀(`mark` 선행)를 재는 유일한 렌즈다.

    Returns:
        `disarm()` — 폭발을 끄고 원래 `logger.info` 동작으로 되돌린다.
        `monkeypatch.undo()` 는 `_armed` 가 깐 scanner/session 패치까지 되돌려
        리그를 무너뜨리므로 쓰지 않는다.
    """
    mod = _module(kind)
    orig = mod.logger.info
    state = {"armed": True, "fired": 0}

    def _boom(msg, *args, **kwargs):
        rendered = str(msg)
        if args:
            try:
                rendered = str(msg) % args
            except Exception:
                pass
        hit = "[open_entry_hold" in str(msg) or "[open_entry_hold" in rendered
        if hit and state["armed"] and not (once and state["fired"] >= 1):
            state["fired"] += 1
            raise RuntimeError("관측기 폭발 (cycle262 C10)")
        return orig(msg, *args, **kwargs)

    monkeypatch.setattr(mod.logger, "info", _boom)

    def _disarm() -> int:
        state["armed"] = False
        return state["fired"]

    return _disarm


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c10_1_emit_failure_keeps_hold(monkeypatch, kind: str) -> None:
    """C10 (RED): 보류 상태에서 emit 이 터져도 반환은 `Signal.NONE` (예외 전파 금지).

    관측 예외가 `check_buy_signal` 을 뚫고 나가면 `risk.on_tick` 이 그 종목의 나머지
    평가를 잃는다 — 관측 시정이 아니라 **결함 주입**이다(cycle237 TE-2 선례).
    """
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    _explode_hold_emits(monkeypatch, kind)
    assert _breakout(s) == Signal.NONE
    assert s._prev_price[_TICKER]["main"] == _TARGET, "emit 실패가 baseline 갱신까지 삼켰다"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_c10_2_emit_failure_keeps_buy(monkeypatch, kind: str) -> None:
    """C10 (RED): 창 **밖** 정상 매수 상태에서 config emit 이 터져도 `Signal.BUY` 유지.

    관측이 매수를 삼키면 그 자체가 무증상 매매 중단이다.
    """
    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    _explode_hold_emits(monkeypatch, kind)
    assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_c10_3_trace_failure_also_absorbed(monkeypatch, kind: str) -> None:
    """C10 (RED): 흡수기(`observer_trace.trace_observer_failure`)까지 터져도 행위 불변.

    2차 예외 흡수 = `observer_trace` 의 never-raise 계약(cycle258). 보류 판정은
    관측 스택 전체가 무너져도 그대로 수행된다 = "행위는 cap 밖".
    """
    from src.engine import observer_trace

    def _boom_trace(*a, **kw):
        raise RuntimeError("흡수기 폭발 (cycle262 C10)")

    s = _armed(kind, monkeypatch, hold=90)
    _prime(s)
    _explode_hold_emits(monkeypatch, kind)
    monkeypatch.setattr(observer_trace, "trace_observer_failure", _boom_trace)
    # 전략 모듈이 이름을 최상단에서 바인딩했을 수 있다(`from ... import trace_observer_failure`)
    # — 그 바인딩까지 같이 터뜨려야 실제 2차 예외 경로가 실행된다.
    monkeypatch.setattr(
        _module(kind), "trace_observer_failure", _boom_trace, raising=False,
    )
    assert _breakout(s) == Signal.NONE


@pytest.mark.parametrize("kind", _KINDS)
def test_c10_4_config_emit_failure_absorbed(monkeypatch, kind: str, caplog) -> None:
    """C10 (RED): **config emit 흡수기**를 실제 예외로 검정한다.

    ⚠️ `test_c10_1~3` 은 폭발기를 `_prime()` **뒤**에 설치한다 — 그 prime 이 이미
    config cap(`cfg|90`)을 소진해 이후 `should_emit` 이 False 라 `logger.info` 에
    도달조차 못 한다. 그래서 실제로 검정되는 건 blocked 흡수기뿐이고, config 쪽
    `except Exception` 을 `except ZeroDivisionError` 로 좁히는 뮤테이션이 cycle262
    전용 125케이스와 광역 1,742케이스를 **전부 초록으로** 통과했다(적대 검증 HIGH).

    그 갭을 닫는다 — **prime 없이** 폭발기를 먼저 깔고 그날 첫 평가를 시킨다.
    config emit 이 던지면 예외는 `check_buy_signal` 최상단을 뚫고 나가고, 그러면
    (a) `risk.on_tick` 의 전략 루프에 전략별 try 가 **없어** 뒤 순번 전략들이 그 틱의
    청산·손절 평가를 통째로 잃고 (b) `handler.py` 가 `[callback_exception]` 을 찍고
    **`raise` 로 되던져 WS 재연결을 유발**한다. config emit 은 매 `check_buy_signal`
    마다 도는 경로라 핸들러 결함이 지속되면 그대로 재연결 폭주다.
    """
    caplog.set_level(logging.INFO)
    with freeze_time(_KST_090005):
        s = _armed(kind, monkeypatch, hold=90)
        disarm = _explode_hold_emits(monkeypatch, kind)   # ← prime **전** = cap 미소진

        # 예외가 새면 여기서 RuntimeError 로 실패한다 (그게 이 가드의 전부다)
        assert _prime(s) == Signal.NONE
        assert _breakout(s) == Signal.NONE
        assert s._prev_price[_TICKER]["main"] == _TARGET, (
            "emit 실패가 baseline 갱신까지 삼켰다 — 해제 후 첫 틱이 거짓 돌파가 된다"
        )

    fired = disarm()
    assert fired >= 2, (
        f"마커 emit 이 {fired}회만 폭발했다 — config·blocked 둘 다 실행되어야 리그가 성립한다"
    )

    # 실패한 emit 은 cap 을 소진하지 않았다 → 복구 후 정상 발화 + 창 밖 정상 매수
    with freeze_time(_KST_1000):
        assert _breakout(s, px=80100) == Signal.NONE      # baseline 되돌리기
        assert _breakout(s) == Signal.BUY, "복구 후에도 매수가 막혔다"

    lines = _marker_lines(caplog, _M_CONFIG, _logger_name(kind))
    assert len(lines) == 1, f"복구 후 config 카나리아 1행이어야 한다: {lines}"


# ===========================================================================
# C11 — AI 자동 튜닝 화이트리스트 미편입 (런타임 dict)
# ===========================================================================
def test_c11_1_not_in_param_ranges_or_int_params() -> None:
    """C11 (보존→봉인): `open_entry_hold_secs` 는 **진입 정체성 상수**다.

    최근 손실을 목적함수로 삼는 튜너는 n≤20 에 과적합해 "최근 손실 거래를 지우는 값"
    으로 수렴한다 — cycle223(`atr_trail_mult`·`breakout_fail_n_days`) · cycle209 ·
    cycle212 선례와 동형. `_validate_recommendations` 가 `PARAM_RANGES` 화이트리스트
    밖 키를 버리므로 미편입이 곧 자동 적용 차단이다.
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert KEY not in PARAM_RANGES, f"`{KEY}` 가 PARAM_RANGES 에 편입됐다"
    assert KEY not in INT_PARAMS, f"`{KEY}` 가 INT_PARAMS 에 편입됐다"
    hits = [
        k for k in set(PARAM_RANGES) | set(INT_PARAMS)
        if "open_entry" in k or "hold_secs" in k
    ]
    assert hits == [], f"보류 관련 키가 AI 튜닝 화이트리스트에 편입됨: {hits}"

