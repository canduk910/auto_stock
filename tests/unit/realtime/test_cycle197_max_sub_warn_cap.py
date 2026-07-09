"""사이클 197 — 41-cap 구독 WARNING DailyEmitCap Red 가드.

명세 (작업지시서): `_workspace/red/cycle197_max_sub_warn_dailyemitcap.md`

배경:
- `src/realtime/websocket.py::subscribe` L463-464 — LOW(`bypass_limit=False`) 구독이
  41슬롯(`MAX_SUBSCRIPTIONS`) 초과 시 드롭(`return`) + `logger.warning("최대 구독 수...")`.
- 5분 scan 재시도가 실패한 동일 키(주로 H0UNMKO0 장운영정보 후보)를 매 사이클 재전송
  → 7/3 저녁 NXT 애프터 단일 버스트 ~22종목 × ~32회 = ~640건/일 WARNING 스팸.

시정 (log-only, 드롭 행위 byte 불변):
- WARNING 을 `DailyEmitCap[(tr_id, tr_key)]` 로 게이트 (1회/키/일, KST 자기리셋).
- 드롭 `return`·`bypass_limit` 분기·OPSP backoff·add/ack 전부 불변.

Green 이 강제될 production (메인 세션 구현):
- `from src.engine.daily_emit_cap import DailyEmitCap` + 모듈 상수 `_KST_TZ` 재사용.
- `__init__`: `self._max_sub_warn_cap: DailyEmitCap[tuple[str, str]]` + `self._max_sub_warn_date: str = ""`.
- L463 분기: `_today = datetime.now(_KST_TZ).date().isoformat()` 자기리셋 +
  `should_emit((tr_id, tr_key))` 게이트 + `mark_emitted`. `return`(드롭) 불변.

Red 유효성 (production 미변경 상태):
- **FAIL**: G-1(반복 warning=5 ≠ 1) / G-3(동일 키 반복 미cap) / G-6(should_emit/mark_emitted 부재).
- **PASS(불변식)**: G-2(키당 1회) / G-4(bypass 미진입) / G-5(드롭 byte 불변) / G-6 self-test(탐지기 검증).

함정:
- freezegun 금지 (사이클 187 asyncio.sleep monotonic 동결 hang 교훈). 날짜 전진은
  `_max_sub_warn_date` 필드 직접 세팅으로 시뮬레이션.
- `_subscriptions` 는 `set[tuple[str, str]]` — 41개 dummy 튜플로 채워 41-cap 진입.
- G-1/G-5 는 `_send_subscribe` AsyncMock patch 로 "드롭 시 미호출" 단언.

의미 전환 (사이클 66 K-2): grep "최대 구독 수" / "구독 건너뜀" over tests/ = 0건 →
기존 테스트가 이 WARNING 을 "매 호출 발생" 으로 단언하는 케이스 부재 → 회귀 0.
"""

from __future__ import annotations

import ast
import logging
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.realtime.websocket import KisWebSocket, MAX_SUBSCRIPTIONS
from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
_WS_PY = REPO_ROOT / "src" / "realtime" / "websocket.py"

_WS_LOGGER = "src.realtime.websocket"


# ---------------------------------------------------------------------------
# 공통 헬퍼 — 41-cap 채운 WS + _send_subscribe spy
# ---------------------------------------------------------------------------
def _make_full_ws() -> KisWebSocket:
    """`_subscriptions` 를 41개(MAX_SUBSCRIPTIONS) dummy 로 채운 KisWebSocket.

    - `_ws = object()` (truthy) — 드롭이 *안* 될 경우 `if self._ws:` 진입 가능하게
      두어 `_send_subscribe` 미호출 단언이 의미를 갖게 함.
    - `_send_subscribe` = AsyncMock — 드롭 byte 불변(미호출) 검증용.
    """
    ws = KisWebSocket()
    ws._subscriptions = {(f"TR{i:03d}", f"K{i:03d}") for i in range(MAX_SUBSCRIPTIONS)}
    ws._ws = object()  # truthy
    ws._send_subscribe = AsyncMock()
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS
    return ws


def _count_max_sub_warnings(caplog: pytest.LogCaptureFixture) -> int:
    """caplog 에서 '최대 구독 수' WARNING 레코드 개수."""
    return sum(
        1
        for r in caplog.records
        if r.levelno == logging.WARNING and "최대 구독 수" in r.getMessage()
    )


# ---------------------------------------------------------------------------
# G-1 (핵심 cap) — 41 채운 뒤 동일 키 5회 반복 → WARNING 정확히 1회 + 드롭 유지
# Red: production 미변경 → 5회 warning → FAIL (assert == 1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g1_repeated_same_key_over_cap_warns_once(caplog):
    caplog.set_level(logging.WARNING, logger=_WS_LOGGER)
    ws = _make_full_ws()
    caplog.clear()

    key = ("H0UNMKO0", "005930")
    for _ in range(5):
        await ws.subscribe(*key)  # bypass_limit=False (기본)

    # 5회 모두 드롭 (_subscriptions 미증가)
    assert key not in ws._subscriptions, "41-cap LOW 구독은 드롭되어 add 되지 않아야 함"
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS

    # WARNING 정확히 1회 (DailyEmitCap 1회/키/일)
    n = _count_max_sub_warnings(caplog)
    assert n == 1, (
        f"41-cap 동일 키 5회 반복 subscribe → WARNING 은 키당 1회여야 함 (실제 {n}회 = "
        f"DailyEmitCap 미적용 스팸)"
    )


# ---------------------------------------------------------------------------
# G-2 (per-key 불변식) — 41 채운 뒤 서로 다른 키 3개 → WARNING 3회(키당 1회)
# Red & Green 모두 3회 → PASS (불변식)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g2_distinct_keys_over_cap_warn_per_key(caplog):
    caplog.set_level(logging.WARNING, logger=_WS_LOGGER)
    ws = _make_full_ws()
    caplog.clear()

    keys = [
        ("H0UNMKO0", "005930"),
        ("H0UNMKO0", "000660"),
        ("H0UNCNT0", "035720"),
    ]
    for k in keys:
        await ws.subscribe(*k)

    for k in keys:
        assert k not in ws._subscriptions, "서로 다른 LOW 키 전부 드롭"

    n = _count_max_sub_warnings(caplog)
    assert n == 3, f"서로 다른 키 3개 → 키당 1회 = WARNING 3회여야 함 (실제 {n}회)"


# ---------------------------------------------------------------------------
# G-3 (KST 자기리셋) — 동일 키 same-day 반복 = 1회 cap, 날짜 롤오버 후 재발화
# Red: same-day 반복이 cap 안 됨 → 2회 → FAIL (assert == 1)
# freezegun 금지 — `_max_sub_warn_date` 직접 세팅으로 날짜 전진 시뮬레이션.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g3_kst_self_reset_re_warns_after_date_rollover(caplog):
    caplog.set_level(logging.WARNING, logger=_WS_LOGGER)
    ws = _make_full_ws()
    key = ("H0UNMKO0", "005930")

    caplog.clear()
    await ws.subscribe(*key)  # day1 첫 발화
    await ws.subscribe(*key)  # day1 재시도 — cap 억제 (Red 에서는 억제 안 됨)
    assert _count_max_sub_warnings(caplog) == 1, (
        "동일 날 동일 키 반복 = WARNING 1회 cap 이어야 함 (Red: 미적용 시 2회)"
    )

    # 날짜 전진 시뮬레이션 — 전일로 강제 (freezegun 금지, 사이클 187 hang 교훈)
    ws._max_sub_warn_date = "2020-01-01"

    await ws.subscribe(*key)  # 날짜 롤오버 감지 → reset_daily → 재발화
    assert _count_max_sub_warnings(caplog) == 2, (
        "KST 자기리셋(_max_sub_warn_date 전일) 후 동일 키 재발화 = 누적 2회"
    )


# ---------------------------------------------------------------------------
# G-4 (SAFETY, HIGH 보존) — 41 채운 뒤 bypass_limit=True → WARNING 0 + _subscriptions 증가
# Red & Green 모두 PASS (bypass 는 L463 분기 미진입, 사이클 32 R4 보유 절대 보호)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g4_bypass_limit_true_adds_and_no_warning(caplog):
    caplog.set_level(logging.WARNING, logger=_WS_LOGGER)
    ws = _make_full_ws()
    caplog.clear()

    key = ("H0STCNT0", "005930")  # 보유 종목 HIGH
    await ws.subscribe(*key, bypass_limit=True)

    assert key in ws._subscriptions, (
        "bypass_limit=True 는 41-cap 무시하고 add — 보유/익일청산 절대 보호"
    )
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS + 1
    assert _count_max_sub_warnings(caplog) == 0, (
        "bypass_limit=True 는 L463 `not bypass_limit` 분기 미진입 → WARNING 0회"
    )


# ---------------------------------------------------------------------------
# G-5 (SAFETY, 드롭 byte 불변) — LOW at 41-cap → _subscriptions 미증가 + _send_subscribe 미호출
# Red & Green 모두 PASS (WARNING 게이트는 드롭 행위와 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g5_low_at_cap_drops_without_send():
    ws = _make_full_ws()
    key = ("H0UNMKO0", "005930")

    for _ in range(3):
        await ws.subscribe(*key)  # bypass_limit=False

    # 드롭 byte 불변: _subscriptions 미증가 + _send_subscribe 미호출 (return 이 두 사이트 *전*)
    assert key not in ws._subscriptions
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS
    ws._send_subscribe.assert_not_awaited()


# ---------------------------------------------------------------------------
# G-6 (AST) — L463 41-cap 분기 본체에 should_emit + mark_emitted + return 동반 존재.
#   구조 단언 (production): Red = should_emit/mark_emitted 부재 → FAIL.
#   self-test (탐지기 검증): 항상 PASS.
# 미래 무한 emit 재도입 영구 차단 (`_ast_helpers.py` 재사용).
# ---------------------------------------------------------------------------
def _find_subscribe_max_branch(source: str) -> ast.If | None:
    """`subscribe` 정의 안에서 `... >= MAX_SUBSCRIPTIONS` 41-cap `ast.If` 분기 반환.

    분기 판별 = If.test 서브트리에 Name 'MAX_SUBSCRIPTIONS' 존재.
    docstring/주석/문자열 리터럴은 AST 노드가 아니므로 자연 무시 (사이클 167 교훈).
    """
    func = find_function_def(source, "subscribe")
    if func is None:
        return None
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if isinstance(sub, ast.Name) and sub.id == "MAX_SUBSCRIPTIONS":
                return node
    return None


def _branch_has_return(branch: ast.If) -> bool:
    """분기 본체(body) 에 Return 문 존재 여부 (test 절 제외)."""
    for stmt in branch.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Return):
                return True
    return False


def test_g6_ast_max_sub_branch_gated_by_daily_emit_cap():
    """41-cap 분기 본체에 DailyEmitCap 게이트 3요소(should_emit/mark_emitted/return) 동반.

    Red: production 미변경 → 분기 본체 = logger.warning + return 만 →
    should_emit/mark_emitted 부재 → FAIL (무한 emit = 스팸 상태).
    """
    source = read_module_source(_WS_PY)
    branch = _find_subscribe_max_branch(source)
    assert branch is not None, "subscribe 의 MAX_SUBSCRIPTIONS 41-cap 분기를 찾지 못함"

    n_should = count_function_calls_in_node(branch, "should_emit")
    n_mark = count_function_calls_in_node(branch, "mark_emitted")
    has_return = _branch_has_return(branch)

    assert n_should >= 1, (
        "41-cap 분기에 should_emit 게이트 부재 — WARNING 이 무제한 emit (스팸 재도입)"
    )
    assert n_mark >= 1, (
        "41-cap 분기에 mark_emitted 부재 — cap 미기록 → 동일 키 재발화"
    )
    assert has_return, "41-cap 분기 return(드롭) 불변 위반 — 드롭 행위 훼손"


def test_g6_self_test_detects_capped_vs_uncapped_branch():
    """탐지기 self-test — 게이트 분기/무한 emit 분기를 정확히 구분 (항상 PASS)."""
    good = textwrap.dedent(
        '''
        async def subscribe(self, tr_id, tr_key, *, bypass_limit=False):
            if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
                _today = "x"
                if _today != self._max_sub_warn_date:
                    self._max_sub_warn_date = _today
                    self._max_sub_warn_cap.reset_daily()
                if self._max_sub_warn_cap.should_emit((tr_id, tr_key)):
                    logger.warning("최대 구독 수")
                    self._max_sub_warn_cap.mark_emitted((tr_id, tr_key))
                return
            self._subscriptions.add((tr_id, tr_key))
        '''
    )
    bad = textwrap.dedent(
        '''
        async def subscribe(self, tr_id, tr_key, *, bypass_limit=False):
            if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
                logger.warning("최대 구독 수")
                return
            self._subscriptions.add((tr_id, tr_key))
        '''
    )
    gb = _find_subscribe_max_branch(good)
    bb = _find_subscribe_max_branch(bad)
    assert gb is not None and bb is not None, "탐지기가 41-cap 분기를 찾지 못함"

    # good(게이트 존재) — 3요소 검출
    assert count_function_calls_in_node(gb, "should_emit") >= 1
    assert count_function_calls_in_node(gb, "mark_emitted") >= 1
    assert _branch_has_return(gb)

    # bad(무한 emit) — should_emit/mark_emitted 부재를 정확히 포착 (재도입 차단 신호)
    assert count_function_calls_in_node(bb, "should_emit") == 0
    assert count_function_calls_in_node(bb, "mark_emitted") == 0
    assert _branch_has_return(bb)  # return(드롭) 자체는 양쪽 공통
