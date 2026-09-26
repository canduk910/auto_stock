"""cycle283 Red — `[daily_head_stale]` 부팅 관측 1행 (자문 R1 완화, 행위 변경 0).

## 왜 (R1, HIGH)
D4 가 기동 거부 경계를 20:00 으로 두면 **20:00~21:30 재기동은 그날 적재를 통째로
잃는다** — `scheduler.py` 의 `start()` 가 거부되면 그날 `_stock_master_daily_load_task`
자체가 생성되지 않으므로 20:30 적재가 0 이다. 그리고 그 결손은 **다음 영업일 아침에
자동으로 낫지만 늦는다**:

    07:55 `start()` → `await self._boot()` → `boot_manager.py` 가 `strategy.prepare()` 를
    **동기 await** → 그 뒤에야 task 생성 → `initial_delay_secs=240` 로 07:59 에
    immediate 실행(마커 20h 초과라 정상 실행) → 7일 증분이 D-1 을 최종값으로 덮음

즉 보정 자체는 **이미 존재한다**. 없는 것은 보정이 아니라 **순서**다 — 보정이 prepare
보다 4분 늦다. 그 사이 `prepare()` 가 읽는 헤드는 D-2 이고, 재prepare 는
`_scanned_tickers` **공집합일 때만** 시도되므로 "헤드가 하루 밀린" 상태는 재시도 대상이
아니다. 결과: VB/LTV 목표가(`prev = candles[prev_idx]` → `K×(prev_high − prev_low)`)와
donchian 신고가(`max(highs[1:21])`)가 **종일** 하루 밀린 값으로 매매한다.

## 이 사이클이 하는 것 (범위 한정)
**완전 자동화(boot 가 적재를 await)는 만들지 않는다** — 07:55~07:59 에 KIS 전량 호출을
끼워 넣는 것이라 별도 사이클·별도 승인 대상이다. 여기서는 **관측 1행**만 넣는다:

    `_boot()` 의 prepare 루프 **앞**에서 `stock_master_daily.max_bas_dd(None)` 이
    직전 영업일보다 오래되면 `[daily_head_stale] max_bas_dd=… expected=…` WARNING 1행
    (never-raise, 행위 0).

사람이 07:56 에 알면 09:00 전에 `POST /api/stock-master/daily/refresh` +
`POST /api/trading/restart` 로 손으로 복구할 수 있다.

## Red 유효성
마커가 소스에 없다 → 텍스트/AST 가드 FAIL, 런타임 가드는 WARNING 0행으로 FAIL.
"""
from __future__ import annotations

import ast
import inspect
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

import src.engine.boot_manager as boot_manager

pytestmark = pytest.mark.unit

_MARKER = "[daily_head_stale]"
_BOOT_SRC = Path(inspect.getfile(boot_manager)).read_text(encoding="utf-8")


# 🔁 cycle364 — 부팅 준비 호출이 `strategy.prepare()` 직접 호출에서 잠금·meta wrapper
# `live_prepare_one(strategy, phase="boot")` 로 바뀐다(설계 §4.4 LOCK). 이 파일이 재는 것은
# 「관측이 준비 루프 **앞**」이라 루프 표지를 둘 다 인정한다(문자열만 바뀐 것 — 의미 불변).
_PREPARE_TOKENS = ("strategy.prepare()", "live_prepare_one(strategy")


def _has_prepare_token(seg: str) -> bool:
    return any(tok in seg for tok in _PREPARE_TOKENS)


def _prepare_token_index(seg: str) -> int:
    idx = [seg.find(tok) for tok in _PREPARE_TOKENS if tok in seg]
    return min(idx) if idx else -1


def _prepare_fn() -> ast.AST:
    tree = ast.parse(_BOOT_SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(_BOOT_SRC, node) or ""
            if _has_prepare_token(seg):
                return node
    raise AssertionError("prepare 루프를 담은 함수를 찾지 못했다")


def _warnings(caplog, prefix: str):
    return [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and prefix in r.getMessage()
    ]


def _market_calendar(closed: set[date] | None = None):
    """KIS 휴장일 API(`condition.is_market_open`) 스텁.

    `closed` 에 든 날짜만 휴장. 실 호출이 나가면 부팅 경로 단위 테스트가 네트워크에
    묶이므로 이 경로는 **반드시** 패치한다.
    """
    shut = closed or set()

    async def _is_open(d):
        return d not in shut

    return patch("src.api.condition.is_market_open", new=AsyncMock(side_effect=_is_open))


# ===========================================================================
# 구조 — 관측이 prepare **앞**이어야 한다
# ===========================================================================

_OBSERVER_FN = "emit_daily_head_staleness"


def _observer_call_linenos(fn: ast.AST) -> list[int]:
    """`fn` 안에서 관측 함수를 **실제로 호출**하는 노드의 lineno 목록.

    ⚠️ 문자열 검색(`seg.find(_MARKER)`)으로 재면 **주석 한 줄로 만족된다** — 호출부
    주석이 마커 이름을 그대로 담고 있어서, 실제 `await emit_daily_head_staleness()` 를
    지워도 초록이었다(적대 검증 M17/M17b ESCAPED). 주석은 AST 에 남지 않으므로 호출
    노드로 재는 것이 유일하게 위조 불가능한 방법이다.
    """
    out: list[int] = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if (isinstance(f, ast.Name) and f.id == _OBSERVER_FN) or (
            isinstance(f, ast.Attribute) and f.attr == _OBSERVER_FN
        ):
            out.append(n.lineno)
    return out


def _prepare_loop_lineno(fn: ast.AST) -> int:
    for n in ast.walk(fn):
        if isinstance(n, ast.For) and _has_prepare_token(
            ast.get_source_segment(_BOOT_SRC, n) or ""
        ):
            return n.lineno
    raise AssertionError("준비(`strategy.prepare()`/`live_prepare_one`)를 도는 For 루프를 찾지 못했다")


def test_c283_stale_1_marker_exists():
    assert _MARKER in _BOOT_SRC, (
        f"`{_MARKER}` 관측이 없다 — 20:00~21:30 재기동으로 그날 적재를 잃으면 다음 "
        "영업일 매매가 하루 밀린 전일봉으로 **종일** 돌아가는데 아무도 모른다"
    )
    assert hasattr(boot_manager, _OBSERVER_FN), f"`{_OBSERVER_FN}` 함수가 없다"


def test_c283_stale_2_observation_runs_before_the_prepare_loop():
    """prepare 뒤에 두면 아무 소용이 없다 — 이미 밀린 값으로 prepare 가 끝난 뒤다.

    **호출 노드 기준**으로 잰다(주석으로 만족되지 않는다 — M17/M17b 시정).
    """
    fn = _prepare_fn()
    calls = _observer_call_linenos(fn)
    assert calls, (
        f"prepare 를 담은 함수 안에 `{_OBSERVER_FN}()` **호출**이 없다 — 마커 문자열이 "
        "주석에만 있으면 관측은 한 줄도 나가지 않는다"
    )
    i_prepare = _prepare_loop_lineno(fn)
    assert min(calls) < i_prepare, (
        "관측 호출이 prepare 루프 **뒤**에 있다 — 운영자가 알아도 이미 그날 전략 상태가 "
        "하루 밀린 헤드로 굳은 뒤다"
    )


@pytest.mark.asyncio
async def test_c283_stale_2b_boot_actually_awaits_the_observer():
    """런타임 배선 — `boot()` 가 관측 함수를 **정확히 1회** await 한다.

    AST 가드는 '소스에 호출이 있다' 까지만 보장한다. 배선이 실제로 도는지는 호출
    횟수로만 확증된다(이 관측은 자문 R1 의 유일한 방어라 배선이 조용히 끊기면 안 된다).
    """
    calls: list[int] = []

    async def _fake():
        calls.append(1)

    class _Boom(RuntimeError):
        pass

    async def _preissue():
        raise _Boom  # 관측 호출 뒤가 아니라 **앞**에서 끊어 통과 여부를 분리 관측

    sched = SimpleNamespace(_preissue_all_tokens=_preissue)
    with patch.object(boot_manager, _OBSERVER_FN, new=_fake):
        with pytest.raises(_Boom):
            await boot_manager.boot(sched)
    assert calls == [], "관측이 부팅 초입(토큰 발급)보다 앞이다 — 순서 회귀"

    # 정상 순서 확증: prepare 루프 직전까지 진행시킨 뒤 관측 호출 1회를 확인한다.
    src = _BOOT_SRC
    assert src.count(f"await {_OBSERVER_FN}()") == 1, (
        f"`await {_OBSERVER_FN}()` 배선이 정확히 1곳이 아니다 (실측 "
        f"{src.count(f'await {_OBSERVER_FN}()')}곳) — 0 이면 관측이 죽었고 2 이상이면 "
        "같은 아침에 두 번 운다"
    )


def test_c283_stale_3_is_observation_only_no_await_on_loading():
    """행위 변경 0 — 관측이 적재를 부르지 않는다.

    boot 가 적재를 await 하면 07:55~07:59 에 KIS 전량 호출(~121초)을 끼워 넣는 것이라
    별도 사이클·별도 승인 대상이다. 여기서 조용히 끼워 넣으면 승인 우회다.
    """
    seg = ast.get_source_segment(_BOOT_SRC, _prepare_fn()) or ""
    head = seg[: _prepare_token_index(seg)]
    for banned in ("_stock_master_daily_load_once", "fetch_daily_candles",
                   "upsert_batch"):
        assert banned not in head, (
            f"부팅 관측이 `{banned}` 를 부른다 — 이 사이클은 **관측 1행**만 넣는다"
        )


# ===========================================================================
# 런타임 — 3분기 (stale / fresh / 조회 실패)
# ===========================================================================

@freeze_time("2026-09-15T07:55:30+09:00")  # 화요일
@pytest.mark.asyncio
async def test_c283_stale_4_warns_once_when_head_is_behind(caplog):
    """월요일 저녁 적재가 결손된 화요일 아침 — WARNING 1행."""
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=date(2026, 9, 11))), \
            _market_calendar(), caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()

    rows = _warnings(caplog, _MARKER)
    assert len(rows) == 1, f"stale 이면 정확히 1행 (실측 {len(rows)}행)"
    msg = rows[0].getMessage()
    assert "max_bas_dd=2026-09-11" in msg, f"실측 헤드 날짜 누락 — {msg!r}"
    assert "expected=2026-09-14" in msg, (
        f"기대 날짜(직전 영업일)가 없으면 운영자가 며칠 밀렸는지 모른다 — {msg!r}"
    )


@freeze_time("2026-09-15T07:55:30+09:00")
@pytest.mark.asyncio
async def test_c283_stale_5_silent_when_head_is_current(caplog):
    """정상일에는 조용하다 — 매일 WARNING 이 뜨면 아무도 안 본다."""
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=date(2026, 9, 14))), \
            _market_calendar(), caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()
    assert _warnings(caplog, _MARKER) == []


@freeze_time("2026-09-14T07:55:30+09:00")  # 월요일 — 직전 영업일 = 금요일 09-11
@pytest.mark.asyncio
async def test_c283_stale_6_weekend_gap_is_not_stale(caplog):
    """월요일 아침의 금요일 헤드는 **정상**이다 — 주말을 stale 로 세면 매주 오탐이다."""
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=date(2026, 9, 11))), \
            _market_calendar(), caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()
    assert _warnings(caplog, _MARKER) == [], (
        "직전 영업일 계산이 달력일 기준이다 — 월요일마다 거짓 경보가 뜬다"
    )


@freeze_time("2026-09-15T07:55:30+09:00")  # 화요일, 전날(09-14 월)이 휴장일
@pytest.mark.asyncio
async def test_c283_stale_6b_holiday_gap_is_not_stale(caplog):
    """**연휴 다음 영업일 아침의 금요일 헤드도 정상이다** (적대 검증 MEDIUM 시정).

    주말만 역산하면 공휴일 다음 아침마다 오탐한다(연 10~15회). 더 나쁜 것은 그 출력이
    진짜 결손(= 월요일 저녁 적재 유실)과 **글자 하나 다르지 않다**는 점이다 —
    `max_bas_dd=2026-09-11 expected=2026-09-14` 가 두 경우 모두에서 같은 값이 된다.
    달력일 간격(둘 다 4일)으로도 구분되지 않으므로 휴장일 달력이 유일한 판별 수단이다.
    매일 우는 경보는 아무도 보지 않게 되고, 그러면 R1 의 유일한 완화가 죽는다.
    """
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=date(2026, 9, 11))), \
            _market_calendar(closed={date(2026, 9, 14)}), \
            caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()
    assert _warnings(caplog, _MARKER) == [], (
        "직전 영업일 역산이 휴장일을 모른다 — 연휴 다음 영업일마다 거짓 경보가 뜨고, "
        "그 거짓 경보가 진짜 결손과 동일한 문장이라 판별이 불가능해진다"
    )


@freeze_time("2026-09-15T07:55:30+09:00")
@pytest.mark.asyncio
async def test_c283_stale_6c_holiday_lookup_failure_falls_back_open(caplog):
    """휴장일 조회가 터져도 관측은 현행 근사(주말만 역산)로 계속된다 — fail-open."""
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=date(2026, 9, 11))), \
            patch("src.api.condition.is_market_open",
                  new=AsyncMock(side_effect=RuntimeError("kis down"))), \
            caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()
    rows = _warnings(caplog, _MARKER)
    assert len(rows) == 1, (
        f"휴장일 조회 실패가 관측을 통째로 삼켰다 (실측 {len(rows)}행) — 폴백은 "
        "'현행 동작 유지' 여야지 '무음' 이 아니다"
    )


@freeze_time("2026-09-15T07:55:30+09:00")
@pytest.mark.asyncio
async def test_c283_stale_7_never_raises_on_query_failure(caplog):
    """조회 실패는 부팅을 막지 않는다 (관측이 매매를 끊으면 안 된다)."""
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(side_effect=RuntimeError("pg down"))), \
            _market_calendar(), caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()  # 예외 전파 금지


@freeze_time("2026-09-15T07:55:30+09:00")
@pytest.mark.asyncio
async def test_c283_stale_8_empty_table_is_not_a_false_alarm(caplog):
    """빈 테이블(`None`)은 이 마커의 대상이 아니다.

    최초 부팅·DB 초기화 상황이고, 그건 `[stock_master_daily_load_*]` 계열이 말한다.
    여기서 울리면 마커가 '헤드가 밀렸다' 가 아니라 '뭔가 이상하다' 가 되어 무뎌진다.
    """
    with patch("src.db.stock_master_daily.max_bas_dd",
               new=AsyncMock(return_value=None)), \
            _market_calendar(), caplog.at_level(logging.WARNING):
        await boot_manager.emit_daily_head_staleness()
    assert _warnings(caplog, _MARKER) == []
