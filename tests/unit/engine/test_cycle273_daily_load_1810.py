"""cycle273 D8 — 일봉 적재 16:00 → **18:10** 이동 (Red).

정본 = `_workspace/red/cycle273f_daily_load_1810_spec.md` ·
조사 `_workspace/analysis/2026-09-10_cycle273_UD_load_and_ui.md` §D8.

변경 규모 = `src/engine/scheduler.py:66` **리터럴 1개**(라인 증감 0).
`data_load_tasks` 는 `wait_time` 을 인자로만 받으므로 모듈 안에 시각 리터럴이 없다.

## 왜 지금인가 (조건 충족 실측)
워크리스트가 걸어 둔 조건("화 09-08 cycle263 D+1 확인 후")은 **4거래일 연속**으로
충족됐다 — `stock_master_daily` 의 `min(updated_at)` 이 09-07/08/09/10 각각
그날 **16:00** 이다(1,197 / 1,130 / 1,088 / 1,003행).

## 얻는 것 / 잃는 것
- 얻는다: 16:00~18:00 시간외 단일가 물량이 **그날 봉**에 들어온다.
- 부수 효과(문서화 필수): 유니버스 판정이 **어제치 `raw` → 오늘치 `raw`** 로 바뀐다
  (16:10 basics refresh 뒤이므로). 회전의 **위상만 하루 당겨지고** 회전 자체는 남는다.
  ⇒ **D8 은 D5 를 대체하지 못한다.** 004690 처럼 임계 근처 보유 종목은
  그날 거래대금이 9억이면 18:10 로 옮겨도 여전히 빠진다.
- 미확인 1건: NXT 애프터(~20:00) 물량이 이 일봉에 잡히는지는 **여전히 미확인**.

⚠️ `scheduler.py` 는 8영역은 아니지만 **라인 상한(<3,900L)** 때문에 같은 승인 대상이다.
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

import src.engine.scheduler as sched

pytestmark = pytest.mark.unit

_NEW = time(18, 10)


# ===========================================================================
# G-273F-1 — 상수 이동 (본 계약)
# ===========================================================================

def test_g273f_1_daily_load_time_moved_to_1810():
    """`TIME_STOCK_MASTER_DAILY_LOAD = time(18, 10)`.

    RED = 현행 `time(16, 0)`. 이 단언이 초록이 되는 순간
    `tests/unit/engine/test_cycle122_daily_load_task.py::test_sched1_*`
    (`== time(16, 0)`)가 RED 가 된다 — **같은 커밋에서 갱신**한다(spec §6).
    """
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD == _NEW, (
        f"실측 {sched.TIME_STOCK_MASTER_DAILY_LOAD}"
    )


def test_g273f_1b_wiring_still_passes_the_constant():
    """배선은 여전히 상수를 넘긴다 — 시각 리터럴이 facade 로 새지 않는다."""
    src = Path(inspect.getfile(sched)).read_text(encoding="utf-8")
    assert "stock_master_daily_load_task_loop(self, wait_time=TIME_STOCK_MASTER_DAILY_LOAD)" in src

    import src.engine.data_load_tasks as dlt
    dsrc = Path(inspect.getfile(dlt)).read_text(encoding="utf-8")
    tree = ast.parse(dsrc)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "stock_master_daily_load_task_loop")
    body = ast.get_source_segment(dsrc, fn)
    assert "time(" not in body, "facade 에 시각 리터럴이 생겼다(정본 이원화)"
    assert "16:00" not in body, (
        "주석의 `16:00` 이 남아 있다 — 시각 이동 사이클은 주석도 함께 옮긴다"
    )


# ===========================================================================
# G-273F-2 — 겹침 0 (전수 대조)
# ===========================================================================

def test_g273f_2_no_scheduled_work_collides_with_the_load_window():
    """적재 창(18:10~18:12, 실측 소요 ~2분 + 여유 10분)과 겹치는 예정 작업 0건.

    실측 = 09-10 16:00~16:02 에 1,003종목 완료. 다음 예정 작업(19:50)까지 1시간 38분 여유.
    """
    lo = _NEW
    hi = (datetime(2026, 9, 10, _NEW.hour, _NEW.minute) + timedelta(minutes=10)).time()
    collisions = sorted(
        name for name, val in vars(sched).items()
        if name.startswith("TIME_") and isinstance(val, time)
        and name != "TIME_STOCK_MASTER_DAILY_LOAD" and lo <= val <= hi
    )
    assert collisions == [], f"적재 창 {lo}~{hi} 와 겹치는 예정 작업: {collisions}"


def test_g273f_2b_data_layer_order_is_preserved():
    """16:10 basics · 16:15 purge · 16:20 funnel · 16:30 master · 16:40 재무는 **그대로**다.

    이 사이클이 옮기는 것은 일봉 적재 하나뿐이며, 나머지 데이터 층의 순서를 건드리지 않는다.
    """
    assert sched.TIME_STOCK_MASTER_BASICS_REFRESH == time(16, 10)
    assert sched.TIME_STOCK_MASTER_DAILY_PURGE == time(16, 15)
    assert sched.TIME_EVENING_FUNNEL_CAPTURE == time(16, 20)
    assert sched.TIME_STOCK_MASTER_MASTER_LOAD == time(16, 30)
    assert sched.TIME_STOCK_MASTER_FINANCIAL_LOAD == time(16, 40)


def test_g273f_2c_side_effect_is_explicit_universe_uses_todays_raw():
    """부수 효과의 **성립 조건**을 테스트로 못 박는다 — 적재가 basics 갱신 **뒤**다.

    이것이 이 이동의 문서화되지 않은 진짜 변화다(유니버스 판정이 어제치 → 오늘치 raw).
    좋은 쪽·나쁜 쪽이 **양방향**이라 배포 D+1 판독은 이동 전후를 **합산하지 않는다**.
    """
    assert sched.TIME_STOCK_MASTER_BASICS_REFRESH < sched.TIME_STOCK_MASTER_DAILY_LOAD, (
        "적재가 basics 앞이면 여전히 어제치 raw 로 판정한다 = 이동의 효과 절반 소실"
    )


def test_g273f_2d_still_after_market_close_and_before_settlement():
    """장중 침범 0 · 정산 전 완료 — 시각 이동의 바깥 울타리."""
    assert sched.TIME_KRX_MAIN_CLOSE < sched.TIME_STOCK_MASTER_DAILY_LOAD
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < sched.TIME_NXT_POST_BUY_STOP
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < sched.TIME_SETTLEMENT


# ===========================================================================
# G-273F-3 — cycle269 C9 불변식 회귀 (토큰 강제 재발급 21:30 가정)
# ===========================================================================

def test_g273f_3_quote_token_refresh_window_still_clear():
    """`TIME_STOCK_MASTER_DAILY_LOAD < TIME_QUOTE_TOKEN_REFRESH` 유지 + 창 겹침 0.

    `test_cycle269_quote_token_refresh.py::test_c9_schedule_time_invariants` 가
    `scheduler.TIME_*` 전수를 `[T−10분, T+8분]` 창으로 훑는다. 18:10 은 21:30 기준
    그 창 밖이지만, **T 를 옮기는 후속 사이클은 반드시 이 창을 다시 계산해야 한다**
    — `T ∈ [18:02, 18:20]` 은 이제 금지 구간이다.
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T

    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < T
    base = datetime(2026, 9, 10)
    t_dt = base.replace(hour=T.hour, minute=T.minute)
    lo = (t_dt - timedelta(minutes=10)).time()
    hi = (t_dt + timedelta(minutes=8)).time()
    assert not (lo <= sched.TIME_STOCK_MASTER_DAILY_LOAD <= hi), (
        f"일봉 적재가 토큰 재발급 직렬화 창 {lo}~{hi} 안이다"
    )


# ===========================================================================
# G-273F-4 — 16:20 저녁 funnel 캡처 무영향 (두 겹)
# ===========================================================================

def test_g273f_4_evening_funnel_does_not_depend_on_todays_bar():
    """(a) 대기 폴링이 `count_all()`(테이블 전체 행수)이라 헤드 날짜와 무관하고,
    (b) 전략 7종의 오늘봉 절단이 **날짜 비교**라 오늘 행이 없으면 같은 전일 봉을 쓴다.

    ⇒ 18:10 이동으로 16:20 캡처가 새로 깨지는 것이 없다.
    """
    src = Path(inspect.getfile(sched)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_evening_funnel_capture_once")
    body = ast.get_source_segment(src, fn)
    assert "count_all" in body
    assert "max_bas_dd" not in body, (
        "캡처가 헤드 날짜를 보게 되면 18:10 이동이 이 경로를 깬다"
    )
    # F-D8-a — 주석 정직화: `count_all()` 은 '빈 테이블' 만 막는다
    assert "일봉 적재 완료 대기" not in body or "빈 테이블" in body, (
        "docstring 이 '적재 완료 대기' 라고 적는데 실제로는 빈 테이블만 막는다 — "
        "시각을 옮기는 사이클에서 이 문구를 정직화한다(F-D8-a)"
    )


def test_g273f_4b_strategies_cut_today_bar_by_date_comparison():
    """전략의 `prev_idx` 가 **날짜 비교**라는 사실을 소스로 고정한다."""
    root = Path(inspect.getfile(sched)).resolve().parent / "strategies"
    checked = 0
    for name in ("volatility_breakout", "long_tail_volatility", "kojiro",
                 "donchian_swing", "bull_flag_breakout"):
        text = (root / f"{name}.py").read_text(encoding="utf-8")
        assert "stck_bsop_date" in text and "today_str" in text, name
        checked += 1
    assert checked == 5


# ===========================================================================
# G-273F-5 — 문서 동기화 (Phase 4.8)
# ===========================================================================

def test_g273f_5_engine_claude_md_states_the_new_time():
    root = Path(inspect.getfile(sched)).resolve().parent
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "TIME_STOCK_MASTER_DAILY_LOAD = time(18, 10)" in text, (
        "`src/engine/CLAUDE.md` 시각 표가 옛 16:00 을 말한다 — 문서가 코드보다 "
        "성기면 다음 포팅이 또 어긋난다(D3 가 그 사례다)"
    )


# ===========================================================================
# 🔴 별건 HIGH — 채택은 **사용자·팀장 결정** (spec §OQ-D8-1)
# ===========================================================================
