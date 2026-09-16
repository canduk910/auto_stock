"""cycle273 D8 — 일봉 적재 16:00 → 18:10 이동 / **cycle283 재기준선: 18:10 → 20:30**.

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

⚠️ `scheduler.py` 는 8영역은 아니지만 **라인 상한(<3,900L — cycle257 영구 상한이 정본, 4,000 은 구 상한)** 때문에 같은 승인 대상이다.

────────────────────────────────────────────────────────────────────────────
🔁 cycle283 재기준선 (2026-09-11, 사용자 결정 D2) — 적재 18:10 → **20:30**
────────────────────────────────────────────────────────────────────────────
위 "미확인 1건: NXT 애프터(~20:00) 물량이 이 일봉에 잡히는지" 가 09-11 에 **실측으로
해소**됐다 — 일봉 OHLC 는 15:30 확정이지만 **거래량·거래대금은 시간외 거래 동안 계속
증가**한다. 게다가 09-14(월)부터 KRX 애프터마켓(16:00~20:00 실시간 체결)이 신설돼
그날 거래가 20:00 에 끝난다 ⇒ 18:10 적재는 **매일** 부분 거래량을 담는다.

이 파일의 단언 중 **의도를 재표현**한 것 둘:
- `test_g273f_2d` 의 `DAILY_LOAD < TIME_NXT_POST_BUY_STOP(19:50)` — 원 의도는
  "장중 침범 0 · 정산 전 완료" 였고 19:50 은 그 시절의 *매매 종료 프록시*였다.
  매매는 이제 20:00(`TIME_NXT_POST_CLOSE`)에 끝나므로 20:30 은 침범이 아니다.
  ⇒ `TIME_NXT_POST_CLOSE <= DAILY_LOAD < TIME_SETTLEMENT` 로 재표현한다.
- `test_g273f_3` 의 `DAILY_LOAD < TIME_QUOTE_TOKEN_REFRESH` — 원 의도는
  "토큰 재발급 직렬화 창과 겹치지 않는다" 이고, 그것을 **정확히** 재는 것은 바로
  아래 줄의 창 검사(`not (T−10분 <= DAILY_LOAD <= T+8분)`)다. 부등식은 그 의도보다
  넓게 잡힌 프록시였을 뿐이라 창 검사에 **흡수**한다(삭제 사유 = 중복 프록시).
  🔁 cycle296(2026-09-17) 이 T 를 19:00 → **20:45** 로 옮겨 그 창은 `[20:35, 20:53]`
  이 됐다 — 적재 20:30 은 창 **앞**이라 여전히 침범 0 이고, 부등식이 남아 있었다면
  (20:30 < 20:45) 우연히 통과했을 뿐 의도를 재지 못했을 것이다.
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

import src.engine.scheduler as sched

pytestmark = pytest.mark.unit

_NEW = time(20, 30)  # cycle283 (구 18:10 — cycle273f)


# ===========================================================================
# G-273F-1 — 상수 이동 (본 계약)
# ===========================================================================

def test_g273f_1_daily_load_time_moved_to_1810():
    """`TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` (cycle283 재기준선).

    RED = 현행 `time(18, 10)`. 이 단언이 초록이 되는 순간
    `tests/unit/engine/test_cycle122_daily_load_task.py::test_g_sched1_*`
    도 함께 갱신돼야 한다 — **같은 커밋에서** (cycle273f 때와 같은 규약).
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
    for stale in ("16:00", "18:10"):
        assert stale not in body, (
            f"주석의 `{stale}` 이 남아 있다 — 시각 이동 사이클은 주석도 함께 옮긴다"
        )


# ===========================================================================
# G-273F-2 — 겹침 0 (전수 대조)
# ===========================================================================

def test_g273f_2_no_scheduled_work_collides_with_the_load_window():
    """적재 창(20:30~20:40, 실측 전량 ~121초 + 여유)과 겹치는 예정 작업 0건.

    실측 = 09-10 16:00~16:02 에 1,003종목 완료(전량 스윕은 ~121초). 창 `[20:30, 20:40]`
    안에 다른 `TIME_*` 가 하나도 없어야 하고, 정산(21:30)까지 50분 여유가 남는다.
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
    """장중 침범 0 · 정산 전 완료 — 시각 이동의 바깥 울타리(cycle283 재표현).

    종전 단언은 `DAILY_LOAD < TIME_NXT_POST_BUY_STOP(19:50)` 이었다. 19:50 은 "NXT
    애프터 **신규 매수** 중단" 시각이고, 그 시절엔 그게 곧 '거래가 끝나는 시각' 의
    프록시였다. 09-14 제도 변경 이후 거래는 `TIME_NXT_POST_CLOSE(20:00)` 에 끝나므로
    프록시를 **진짜 경계**로 바꾼다 — 20:30 은 19:50 보다 뒤지만 침범이 아니다.
    """
    assert sched.TIME_KRX_MAIN_CLOSE < sched.TIME_STOCK_MASTER_DAILY_LOAD
    assert sched.TIME_NXT_POST_CLOSE <= sched.TIME_STOCK_MASTER_DAILY_LOAD, (
        "적재가 매매 종료(20:00)보다 앞이면 그날 봉을 장중에 긁는 것이다"
    )
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < sched.TIME_SETTLEMENT, (
        "정산(= 루프 수명 상한) 전에 끝나지 않으면 매일 0회 발화한다"
    )


# ===========================================================================
# G-273F-3 — cycle269 C9 불변식 회귀 (토큰 강제 재발급 21:30 가정)
# ===========================================================================

def test_g273f_3_quote_token_refresh_window_still_clear():
    """일봉 적재가 토큰 재발급 **직렬화 창**과 겹치지 않는다 (cycle283 재표현).

    종전에는 `DAILY_LOAD < TIME_QUOTE_TOKEN_REFRESH` 부등식이 함께 있었다. 그 부등식의
    *의도*는 "직렬화 창 침범 금지" 이고, 그것을 **정확히** 재는 것은 아래 창 검사다
    (부등식은 그보다 넓게 잡힌 프록시라 20:30 처럼 창 **뒤**인 값도 기각한다).
    ⇒ 부등식은 창 검사에 흡수하고 삭제했다. `test_cycle269::test_c9` 의 쌍둥이
    단언도 같은 사유로 같이 재표현한다.

    `test_cycle269_quote_token_refresh.py::test_c9_schedule_time_invariants` 가
    `scheduler.TIME_*` 전수를 `[T−10분, T+8분]` 창으로 훑는다 — **T 를 옮기는 후속
    사이클은 반드시 이 창을 다시 계산해야 한다.** cycle296 이 그렇게 했다
    (19:00 → 20:45 ⇒ 창 [20:35, 20:53]; 적재 20:30 은 창 앞 5분).
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T

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
    assert "TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)" in text, (
        "`src/engine/CLAUDE.md` 시각 표가 옛 값(16:00/18:10)을 말한다 — 문서가 코드보다 "
        "성기면 다음 포팅이 또 어긋난다(D3 가 그 사례다)"
    )
    assert "time(18, 10)" not in text, (
        "옛 18:10 서술이 남아 있다 — 같은 문서 안에 두 값이 공존하면 `:209`/`:496` 이 "
        "서로 어긋났던 cycle273f 의 상태로 되돌아간다"
    )


# ===========================================================================
# 🔴 별건 HIGH — 채택은 **사용자·팀장 결정** (spec §OQ-D8-1)
# ===========================================================================
