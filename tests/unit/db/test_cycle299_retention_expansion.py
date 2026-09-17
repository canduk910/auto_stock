"""cycle299 (2026-09-17) — 일봉 retention 230 → 390 달력일 확장 + 행위 무변경 봉인.

목적
====
실효 장기선이 정확히 200 이 되려면 일봉이 225 영업일 필요하다. KIS `FHKST03010100` 의 100일은
**호출당** 한도이지 총량 한도가 아니고, `condition.fetch_daily_candles_backfill(
ticker, total_days, *, window=100)` 이 이미 날짜 윈도우를 `ceil(total_days/window)` 개로
쪼개 순차 호출·병합한다. 총량을 막고 있던 것은 우리 상수 둘뿐이다:

  src/db/stock_master_daily.py  DAILY_RETENTION_DAYS        230 → 390 (달력일)
  src/engine/scanner.py         _DAILY_LOAD_VCP_BACKFILL_DAYS 120 → 225 (영업일)

🔴 **두 값은 반드시 함께 간다.** target 이 retention 이 보유할 수 있는 영업일 수를 넘으면
`existing_count` 가 영원히 target 에 못 닿아 매일 밤 전량 재backfill(churn) 이 된다 —
사이클 196 이 시정한 바로 그 결함이다. 이 파일의 G-299-3 계열이 그 커플링을 잰다.

⚠️ **cycle299 자신은 매매 행위를 바꾸지 않았다.** 적재만 넓히고 읽기는 100봉에 두었다:
  - `stock_master_daily.get_recent_daily` 의 `min(days, 상한)` 하드 클램프를 행을 돌려주는
    모든 읽기(`get_donchian_high` · `get_atr` · `get_recent_daily_with_fallback` ·
    `get_recent_daily_normalized`)가 경유한다 → 소비처가 상한을 넘겨 읽을 수 없다.
  - `vcp_breakout.py` 의 `KIS_DAILY_CANDLES_MAX = 100` 이 `fetch_days` 를 cap 한다.
  - 나머지 소비처(`max_bas_dd`·`count_all`·`count_by_ticker`·`routes/market_ops.py` 의
    max/min/count)는 전부 스칼라 집계라 행 수 무관.
  G-299-7 이 그 두 겹의 존재를 봉인한다.

🔁 **cycle300 이 그 두 겹을 열었다**(사용자 명시 승인). 클램프 상한은 `_MAX_DAILY_ROWS`(400)
로 올랐고, VCP 는 `daily_fetch_depth_mode` 스위치로 `full` 일 때만 깊이를 요청한다
(기본 `cap100` = 행위 byte 동일). 그래서 G-299-7a 는 **상한 숫자가 아니라 클램프 구조**를
재고, G-299-7b 는 기본 분기의 cap 표현이 그대로 남아 있는지를 잰다. 숫자의 근거는
`tests/unit/engine/strategies/test_cycle300_daily_depth_switch.py` 가 잰다.

가드 매트릭스 (이 파일)
======================
- G-299-1  DAILY_RETENTION_DAYS == 390                                   → Red FAIL
- G-299-3a 실측 윈도우 도달 달력일 < DAILY_RETENTION_DAYS (커플링)         → 불변식
- G-299-3b 실측 도달 + 30 달력일 ≤ DAILY_RETENTION_DAYS (마진)            → 불변식
- G-299-3c 정상상태 churn 자유 — retained_trading(retention) ≥ target + 30 → 불변식
- G-299-7a get_recent_daily 본체에 min(days, 상한) 클램프 구조 존재 (+self-test) → 불변식
- G-299-7b vcp_breakout 소스에 KIS_DAILY_CANDLES_MAX = 100 리터럴 존재     → 불변식

"불변식" 은 Red(230/120)·Green(390/225) 양쪽에서 PASS 한다는 뜻이다. 이들의 일은 값을
끌어오는 것이 아니라 **두 상수 중 하나만 움직인 반쪽 Green 을 붉게 만드는 것**이다
(구체적 반쪽 시나리오는 각 테스트 docstring 에 적었다).

날짜 검증 방식: 사이클 196 `tests/unit/api/test_cycle196_backfill_window_clamp.py` 의
`_capture_windows` 패턴을 그대로 답습한다 — 윈도우 `(start,end)` 를 캡처하고
윈도우 0 의 `end_offset=0` 덕에 `today = _parse(calls[0][1])` 로 함수 내부 today 를
정확히 복원한다(외부 시계 의존 0, freezegun 불필요). 비율 리터럴(1.479 등)을 테스트에
박지 않는다 — **실측 도달값**과 **두 프로덕션 상수**만 비교한다.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# 영업일 환산 앵커 — 사이클 196 실측 (retention 230 달력일 ⇄ 154 영업일)
# ---------------------------------------------------------------------------
# 이 두 수는 사이클 196 이 운영 DB 에서 잰 값이다(`test_cycle196_vcp_backfill_convergence`
# 모듈 docstring). 요일/공휴일 모델을 테스트에 새로 만들지 않고 **실측 앵커 하나**로
# 선형 환산한다 — 한국 공휴일은 해마다 다르고, 테스트가 달력을 흉내 내기 시작하면
# 그 모델 자체가 결함원이 된다.
_ANCHOR_RETENTION_CAL = 230
_ANCHOR_RETENTION_TRADING = 154


def trading_days_in(cal_days: int) -> int:
    """달력일 → 영업일 (사이클 196 실측 앵커 230cal ⇄ 154영업일 선형 환산, 내림)."""
    return int(cal_days * _ANCHOR_RETENTION_TRADING / _ANCHOR_RETENTION_CAL)


# 정상상태 churn 자유 마진 (영업일).
# 사이클 196: retained(230)=154 − target 120 = 34.
# cycle299 : retained(390)=261 − target 225 = 36.  ← 마진이 **늘어난다**.
# 30 은 그 34·36 아래에 둔 하한이다(마진을 약화시키지 않으면서 반올림 흔들림을 허용).
MIN_CONVERGENCE_MARGIN_TRADING = 30

# backfill 최고 도달점과 retention 사이의 달력일 마진 하한.
# 사이클 196: 178cal 도달 vs 230 retention = 52.  cycle299: 347 vs 390 = 43.
# 30 은 둘 다 아래에 두는 하한 — 도달점이 retention 에 닿으면 갓 채운 행이 그날 밤
# purge 에 잘려 영원히 target 에 못 닿는다.
MIN_REACH_HEADROOM_CAL = 30


def _parse(yyyymmdd: str):
    """캡처된 YYYYMMDD 문자열 → date."""
    return datetime.strptime(yyyymmdd, "%Y%m%d").date()


async def _capture_backfill_reach_cal(monkeypatch, total_days: int) -> int:
    """`fetch_daily_candles_backfill(total_days=...)` 의 **가장 깊은 윈도우 도달 달력일**.

    사이클 196 `_capture_windows` 패턴 답습:
      1) `fetch_daily_candles_ranged` 를 대체해 윈도우 `(start, end)` 를 캡처
      2) 윈도우 0 의 `end_offset = 0` → `win_end == today` 이므로 캡처된 첫 윈도우의
         end 가 곧 함수 내부 `today` = 외부 시계 의존 0
      3) 모든 윈도우 start 를 `(today - start).days` 로 환산 → 최댓값 = 도달 달력일

    도달값을 **실측**으로 뽑는 것이 핵심이다 — `int(n*7/5)+10` 수식을 테스트에 복제하면
    프로덕션이 수식을 바꿔도 테스트가 같이 틀려서 아무것도 못 잡는다.
    """
    from src.api import condition

    calls: list[tuple[str, str]] = []

    async def fake_ranged(ticker, start, end):
        calls.append((start, end))
        return []  # 반환값 무관 — 호출 인자만 검증

    monkeypatch.setattr(condition, "fetch_daily_candles_ranged", fake_ranged)
    # 윈도우 간 sleep 실호출 회피 (사이클 172/196 패턴, freezegun 금지)
    monkeypatch.setattr(condition.asyncio, "sleep", AsyncMock())

    await condition.fetch_daily_candles_backfill(
        "005930", total_days=total_days, window=100
    )

    assert calls, "윈도우가 하나도 호출되지 않았다 (캡처 실패)"
    today = _parse(calls[0][1])
    return max((today - _parse(start)).days for start, _end in calls)


# ---------------------------------------------------------------------------
# G-299-1 — DAILY_RETENTION_DAYS == 390
# ---------------------------------------------------------------------------
def test_g299_1_retention_days():
    """DAILY_RETENTION_DAYS == 390 달력일 (≈261 영업일 보유 = VCP target 225 + 36 마진).

    무엇을 재는 테스트인가: 일봉 보존 기간의 정본 값.
    왜 390 인가: target 225 영업일을 담으려면 225 × (230/154) ≈ 336 달력일이 최소이고
    (3c 하한 30 을 얹은 최소 retention 은 381 이다), 사이클 196 이 세운 34 영업일 마진
    이상을 확보하면 390 이다. 실제로 trading_days_in(390) = 261 이라 261 − 225 = 36 으로
    사이클 196 의 34 를 넘어선다.

    Red (230): FAIL.  Green (390): PASS.
    """
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS

    assert DAILY_RETENTION_DAYS == 390, (
        "cycle299 — 실효 장기선 200(= 225 영업일) 보존을 위해 230 → 390 달력일. "
        "🔴 scanner._DAILY_LOAD_VCP_BACKFILL_DAYS(=225) 와 반드시 함께 간다"
    )


# ---------------------------------------------------------------------------
# G-299-3a (핵심 부등식 / 커플링) — 실측 도달 달력일 < retention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g299_3a_backfill_reach_inside_retention(monkeypatch):
    """backfill 최고 도달 달력일 < DAILY_RETENTION_DAYS — churn 무발생의 직접 증거.

    무엇을 재는 테스트인가: "우리가 KIS 에서 끌어오는 가장 깊은 날짜가 우리가 보관하는
    기간 안에 있는가". 밖이면 매일 밤 끌어온 행을 그날 purge 가 잘라내고, `existing_count`
    는 target 에 영원히 못 닿아 전량 재backfill 이 반복된다(사이클 192 → 196 결함).

    측정: `_capture_backfill_reach_cal` 실측(수식 복제 없음).
    비교: 두 **프로덕션 상수**끼리 — 테스트 안에 비율 리터럴을 두지 않는다.

    불변식 (Red 230/120 · Green 390/225 양쪽 PASS). 이 테스트의 진짜 일은
    **반쪽 Green 차단**이다:
      - scanner 만 225 로 올리고 retention 230 방치 → 도달 347 > 230 → FAIL ✅
      - retention 만 390 으로 올리고 target 120 유지 → 178 < 390 → PASS (무해 방향)
    """
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS
    from src.engine import scanner

    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    reach_cal = await _capture_backfill_reach_cal(monkeypatch, target)

    assert reach_cal < DAILY_RETENTION_DAYS, (
        f"backfill 도달 {reach_cal}cal 이 retention {DAILY_RETENTION_DAYS}cal 밖이다 "
        f"(target={target}) — 끌어온 행이 그날 purge 에 잘려 전량 재backfill churn 이 된다. "
        f"두 상수는 반드시 함께 간다"
    )


# ---------------------------------------------------------------------------
# G-299-3b (여유 마진) — 실측 도달 + 30cal ≤ retention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g299_3b_backfill_reach_headroom(monkeypatch):
    """backfill 도달 달력일 + 30 ≤ retention — 경계에 붙지 않는다.

    무엇을 재는 테스트인가: G-299-3a 의 부등식이 *간신히* 성립하는 상태를 막는다.
    도달점이 retention 에 근접하면 공휴일 배치가 나쁜 해에 갓 채운 가장 오래된 행이
    그날 밤 purge 에 잘려 `existing_count` 가 target 바로 아래에서 진동한다.

    왜 30 인가 (실측 근거):
      - 사이클 196 현행: 도달 178cal vs retention 230 → 여유 52cal
      - cycle299 목표  : 도달 347cal vs retention 390 → 여유 43cal
      30 은 그 둘 **아래**에 둔 하한이라 어느 쪽 마진도 약화시키지 않는다.

    불변식 — Red(178+30=208 ≤ 230) · Green(347+30=377 ≤ 390) 양쪽 PASS.
    반쪽 Green(target 225 + retention 230)에서 347+30 > 230 으로 FAIL.
    """
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS
    from src.engine import scanner

    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    reach_cal = await _capture_backfill_reach_cal(monkeypatch, target)

    assert reach_cal + MIN_REACH_HEADROOM_CAL <= DAILY_RETENTION_DAYS, (
        f"여유 마진 부족: 도달 {reach_cal}cal + {MIN_REACH_HEADROOM_CAL} > "
        f"retention {DAILY_RETENTION_DAYS}cal (target={target}). "
        f"참고 실측 — 사이클196 178/230(여유 52) · cycle299 347/390(여유 43)"
    )


# ---------------------------------------------------------------------------
# G-299-3c (정상상태 churn 자유) — retained 영업일 ≥ target + 30
# ---------------------------------------------------------------------------
def test_g299_3c_retained_trading_days_cover_target():
    """retention 이 보유하는 영업일 ≥ VCP target + 30 — 사이클 196 34일 마진의 계승.

    무엇을 재는 테스트인가: G-299-3a/3b 가 "KIS 에서 얼마나 깊이 긁어오나"를 잰다면
    이것은 "DB 가 정상상태에서 얼마나 들고 있나"를 잰다. 후자가 target 보다 작으면
    `existing_count < target` 이 영구히 참이 되어 매일 밤 전량 재backfill 이다 —
    사이클 196 이 실제로 밟은 결함(retention 230cal=154영업일 < target 220).

    왜 이 값으로 옮기는가 (마진 정확 보존):
      사이클 196 — trading_days_in(230)=154, target 120 → 마진 34
      cycle299  — trading_days_in(390)=261, target 225 → 마진 36
      하한 30 은 그 34·36 아래라 어느 쪽도 약화시키지 않는다.

    불변식 — Red/Green 양쪽 PASS. 반쪽 Green(retention 230 + target 225)에서
    154 < 255 으로 FAIL ✅ (이 파일에서 커플링을 가장 직접적으로 잡는 가드).
    """
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS
    from src.engine import scanner

    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    retained = trading_days_in(DAILY_RETENTION_DAYS)

    assert retained >= target + MIN_CONVERGENCE_MARGIN_TRADING, (
        f"정상상태 churn 위험: retention {DAILY_RETENTION_DAYS}cal 는 약 {retained} 영업일만 "
        f"보유하는데 VCP target 은 {target} 영업일이다 "
        f"(요구 마진 {MIN_CONVERGENCE_MARGIN_TRADING}). "
        f"환산 앵커 = 사이클196 실측 {_ANCHOR_RETENTION_CAL}cal ⇄ "
        f"{_ANCHOR_RETENTION_TRADING}영업일"
    )


# ---------------------------------------------------------------------------
# G-299-7a (행위 무변경 봉인) — get_recent_daily 본체 min(days, 100) 클램프 존재
# ---------------------------------------------------------------------------
def _has_min_clamp_on_days(func_node: ast.AST) -> bool:
    """함수 서브트리에 `min(days, <상한>)` 형태(인자 순서 무관) 호출 존재 여부.

    `days` 라는 이름의 변수/인자를 인자로 갖는 `min()` 호출을 찾는다.
    `max(1, min(days, _MAX_DAILY_ROWS))` 처럼 감싸여 있어도 잡힌다.
    """
    for sub in ast.walk(func_node):
        if not (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "min"
        ):
            continue
        for arg in sub.args:
            for inner in ast.walk(arg):
                if isinstance(inner, ast.Name) and inner.id == "days":
                    return True
    return False


def test_g299_7a_get_recent_daily_keeps_days_clamp():
    """`get_recent_daily` 본체의 `min(days, …)` 하드 클램프 **구조** 존속 의무.

    무엇을 재는 테스트인가: 행을 돌려주는 모든 읽기 — `get_donchian_high` · `get_atr` ·
    `get_recent_daily_with_fallback` · `get_recent_daily_normalized` — 가 이 함수를
    경유하므로, **어느 소비처도 상한을 넘겨 읽을 수 없다**는 구조적 보장이다.

    ⚠️ cycle299 시점에는 그 상한이 리터럴 100 이었고, 이 가드가 "cycle299 는 읽기 깊이를
    건드리지 않았다" 를 봉인했다. cycle300 이 사용자 명시 승인 하에 그 상한을 명명 상수
    `_MAX_DAILY_ROWS`(=400) 로 올렸다 — **올린 것은 상한이고 클램프 자체는 남는다**
    (없애면 오염된 값이 그대로 `LIMIT` 에 실려 폭주한다). 그래서 이 가드는 숫자가 아니라
    구조를 재는 쪽으로 옮겼고, 숫자의 근거는
    `tests/unit/engine/strategies/test_cycle300_daily_depth_switch.py` 가 잰다.

    불변식 — 클램프가 통째로 사라지면 FAIL.
    """
    src_path = _REPO_ROOT / "src" / "db" / "stock_master_daily.py"
    source = read_module_source(src_path)
    node = find_function_def(source, "get_recent_daily")
    assert node is not None, "get_recent_daily 함수 정의 존재 의무"

    assert _has_min_clamp_on_days(node), (
        "get_recent_daily 본체에 min(days, 상한) 클램프 존재 의무 — "
        "상한 값은 사이클마다 바뀔 수 있어도 클램프 구조는 폭주 방어선이라 지우지 않는다"
    )


def test_g299_7a_selftest_detector():
    """G-299-7a detector self-test (사이클 196 A-4 self-test 패턴 답습)."""
    yes_tree = ast.parse(
        "def f(days):\n"
        "    clamped = max(1, min(days, 100))\n"
    )
    yes_named = ast.parse(
        "def f(days):\n"
        "    clamped = max(1, min(days, _MAX_DAILY_ROWS))\n"
    )
    yes_swapped = ast.parse(
        "def f(days):\n"
        "    clamped = min(100, days)\n"
    )
    no_tree = ast.parse(
        "def f(days):\n"
        "    clamped = max(1, days)\n"
    )

    def _fn(tree):
        return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    assert _has_min_clamp_on_days(_fn(yes_tree)) is True, "리터럴 상한 → True"
    assert _has_min_clamp_on_days(_fn(yes_named)) is True, "명명 상수 상한 → True"
    assert _has_min_clamp_on_days(_fn(yes_swapped)) is True, "인자 순서 무관 → True"
    assert _has_min_clamp_on_days(_fn(no_tree)) is False, "클램프 부재 → False"


# ---------------------------------------------------------------------------
# G-299-7b (행위 무변경 봉인) — vcp_breakout KIS_DAILY_CANDLES_MAX = 100 리터럴 존속
# ---------------------------------------------------------------------------
def test_g299_7b_vcp_prepare_keeps_100_cap():
    """`vcp_breakout.prepare` 의 `KIS_DAILY_CANDLES_MAX = 100` cap 존속 의무.

    무엇을 재는 테스트인가: VCP `prepare()` 가 여전히 100일만 읽는다는 봉인.
    `fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)` 이므로
    이 상수가 100 인 한 DB/KIS 어느 쪽에서도 100일 초과를 요청하지 않는다.

    사이클 173 `test_cycle173_prepare_db_equivalence.py::test_*` 가 이미 같은 두 줄을
    재고 있다. 여기서 다시 세우는 이유는 **소유권**이다 — cycle299 는 "일봉을 225일
    보관하게 만드는" 사이클이라, 225 를 실제로 *읽게* 만들려는 유혹이 바로 이 줄에 닿는다.
    그 변경은 매매 행위(전략 신호)를 바꾸므로 승인 + domain-consult 선행 대상이고,
    cycle299 의 Green 에 섞여 들어오면 안 된다.

    불변식 — Red/Green 양쪽 PASS.
    """
    src_path = _REPO_ROOT / "src" / "engine" / "strategies" / "vcp_breakout.py"
    source = read_module_source(src_path)

    assert "KIS_DAILY_CANDLES_MAX = 100" in source, (
        "vcp_breakout 의 KIS_DAILY_CANDLES_MAX = 100 리터럴 존속 의무 — "
        "cycle299 는 prepare 의 100일 cap 을 바꾸지 않는다"
    )
    assert "min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)" in source, (
        "fetch_days cap 표현 존속 의무 (사이클 33 KIS 한도 인식 + 사이클 173 동등성 게이트)"
    )
