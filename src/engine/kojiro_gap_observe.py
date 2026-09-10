"""cycle268 (2026-09-07) — `[kojiro_gap_observe]` 갭 판정 shadow 관측 leaf. **행위 변경 0.**

정본 명세 = `_workspace/specs/cycle268_kojiro_gap_observe.md` ·
배경 조사 = `_workspace/consult/2026-09-07_kojiro_gap_contamination.md`

`kojiro.check_buy_signal` 의 갭 게이트가 **그 순간 실제로 무엇을 읽었는지**를 하루
수십 행으로 남긴다. 판정(매수/스킵)·당일 매수 완료 래치·수량·시점은 어떤 경우에도
바뀌지 않는다 — 이 모듈은 **읽기만** 한다.

## 왜 이 관측이 필요한가

`check_buy_signal` 은 두 경로에서 불린다 — `risk.on_tick`(경로 B, 통합 채널 WS 프레임의
`open_price` 를 그대로 받는다 = 09:00 이후에도 프리장 기준가가 남아 있을 수 있는 오염
가능 경로) · `scheduler._swing_buy_poll_loop`(경로 A, KIS REST 로 새로 읽은 시가 = 깨끗).
두 경로가 **같은 함수를 같은 인자 이름(`open_price`)으로** 부르기 때문에, 어느 값이
실제로 판정에 쓰였는지가 로그만으로는 지금까지 보이지 않았다. 이 마커는 그 값(`arg_open`)
과 `scanner.ticker_prices` 의 WS 캐시 시가(`ws_open`)를 **한 행에** 나란히 남겨, 같은
임계로 반사실 재판정(`ws_verdict`)까지 계산한다 — grep 한 번으로 "깨끗한 경로는 걸렀는데
오염 경로였으면 놓쳤을 종목" 이 드러난다.

cycle273-pre(자문 cycle273_kojiro_gap_gate_20260910.md §3.4(다)) — `ws_verdict` 는
**갭 게이트만**(붕괴 가드 제외) 재현하므로, 판독에서 실제로 뒤집힌 유일한 관문인
붕괴 가드(`kojiro.py:891`)는 관측 밖이었다. `ws_collapse` 가 그 직교 반사실을 같은
행에 마저 남긴다 — "WS 값이었으면 붕괴 가드에 걸렸을지"(`blocked`/`allowed`/`-`).

⚠️ **경로 B(`caller=on_tick`) 행에서는 이 필드도 동어반복이다** — `risk.on_tick`
이 `check_buy_signal` **전에** `ticker_prices[t]["open_price"]` 를 그 틱의
`open_price` 로 덮으므로(`risk.py:495`) 경로 B 행은 항상 `ws_open ≡ arg_open` 이고,
`ws_collapse` 는 **실제 붕괴 판정과 구조적으로 항상 일치**한다(기존 `ws_cmp`/
`ws_gap`/`ws_verdict` 3필드와 같은 함정, cycle264 `used_src=rest → delta_bp=0`
동형). **오염 판정에 쓸 수 있는 것은 `caller=_swing_buy_poll_loop`(경로 A) 행뿐**
— 경로 B 오염 판정은 명세 §5 오프라인 조인만이 유일 경로다.

## leaf 계약 (cycle264 `open_price_observe.py` 선례)

- **never-raise** — 본체 전체가 `try`/`except Exception` 하나. 실패는
  `observer_trace.trace_observer_failure` 로 흔적만 남기고 삼킨다(무흔적 `pass` 금지,
  cycle258 카드 #5). 반환값은 항상 `None`.
- **read-only** — `scanner.ticker_prices` · `params` 를 읽기만 한다. 어떤 dict 도
  생성·변경하지 않는다(cycle242 G-242-8 동형).
- **`await`/DB/HTTP 0건** — `check_buy_signal` 은 동기 hot path 다.
- **비용 순서** — `caller` 해석(`sys._getframe`) → 키 조립 → cap peek → (막히면 즉시
  return) → 그 뒤에야 WS 캐시 조회·갭 산술·문자열 포맷. 틱마다 수십~수백 회 도는
  경로라 cap 뒤 작업을 앞에 두면 관측 자체가 비용이 된다.
- cap = `KstDailyEmitCap[tuple[str, str, str]]`, 키 = `(ticker, caller, verdict)` —
  `caller` 를 키에 넣는 이유는 "같은 종목이 경로 A·B 양쪽에서 심사받은 사실" 이
  ticker 단독 키로는 지워지기 때문이다(명세 §2.3).

## `caller` 해석 — `sys._getframe(depth)`, 기본 `depth=2`

`observe_gap` 은 `check_buy_signal` 안에서 **직접** 불린다(래퍼 메서드 금지) — 그래야
`sys._getframe(2)` 가 `observe_gap` → `check_buy_signal` → 실제 호출자(`on_tick` /
`_swing_buy_poll_loop`) 순으로 정확히 실제 호출자에 도달한다. 미지 호출자는 화이트리스트
정규화 없이 **원문 그대로** 남긴다 — 새 호출 경로가 생기면 그 사실이 로그에 드러나야
한다. 프레임 해석 실패는 `?`(행 자체는 여전히 나온다 — 침묵 금지).
"""
from __future__ import annotations

import logging
import sys

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger(__name__)

MARKER = "[kojiro_gap_observe]"

# 키 = (ticker, caller, verdict) — 명세 §2.3. 날짜 리셋은 `KstDailyEmitCap` 자기
# 리셋에 맡긴다(호출부에 날짜 블록을 두지 않는다 — cycle258 표준).
_cap: "KstDailyEmitCap[tuple[str, str, str]]" = KstDailyEmitCap()


def reset_kojiro_gap_observe_cap() -> None:
    """cap 강제 초기화 (테스트·운영 훅 — cycle264 `reset_open_source_compare_cap` 선례)."""
    global _cap
    _cap = KstDailyEmitCap()


def absorb_call_failure(ticker) -> None:
    """호출 지점(`kojiro.check_buy_signal`)의 관측 호출 자체가 터졌을 때의 흔적. **never-raise.**

    `observe_gap` 은 스스로 never-raise 지만, 호출 지점의 `try/except` 는 그보다
    바깥의 사고(import 실패·monkeypatch·시그니처 불일치)까지 받는다. 그 자리를
    무흔적 `pass` 로 두면 관측기가 죽어도 아무도 모르고, 그러면 이 마커의 **결측이
    "오염이 없었다" 로 오독된다**(명세 §1 판독 표 5행이 막으려던 바로 그것).
    cycle258 카드 #5 가 금지한 형태이므로 흡수기를 공개 함수로 노출한다.

    cap 을 함께 넘기는 이유 = `logger.debug` 단독은 `src/main.py::_DbLogHandler`
    (INFO 컷)를 못 넘어 `system_logs` 에 도달하지 않는다(cycle237 C237-L2-1).
    `trace_observer_failure` 가 cap 을 받으면 WARNING 을 1회/(marker,key)/일 낸다 —
    그 WARNING 이 20:10 로그 분석이 보는 유일한 채널이다.

    ⚠️ 이 함수는 **어떤 경우에도 던지지 않는다** — 호출 지점의 `except` 절에서
    불리므로 여기서 던지면 그 예외가 `check_buy_signal` 밖으로 나가 매수 경로가
    끊긴다(= 관측이 매매를 죽인다 = 이 사이클의 제1 계약 위반).
    """
    try:
        trace_observer_failure(MARKER, str(ticker), _cap)
    except Exception:  # pragma: no cover — 2차 예외도 흡수(cycle258 J-3 계약)
        pass


def _gap_rate(open_v, base) -> "float | None":
    """`(open_v - base) / base * 100`. 산출 불가(0/None/음수/예외)는 `None`(= `-`)."""
    try:
        if open_v is None or base is None:
            return None
        open_f, base_f = float(open_v), float(base)
        if open_f == 0 or base_f == 0:
            return None
        return (open_f - base_f) / base_f * 100
    except Exception:
        return None


def _verdict_for_gap(gap: "float | None", gap_up, gap_down) -> "str | None":
    """`gap` 을 **갭 게이트만**(붕괴 가드 제외) 재현한 판정. 불가는 `None`(= `-`)."""
    if gap is None:
        return None
    try:
        up, down = float(gap_up), float(gap_down)
    except (TypeError, ValueError):
        return None
    if gap >= up:
        return "skip_up"
    if gap <= down:
        return "skip_down"
    return "pass"


def _collapse_verdict_for_ws(ws_open, current_price) -> "str | None":
    """`ws_open` 으로 **붕괴 가드만**(갭 게이트 제외) 재현한 판정 — `_verdict_for_gap`
    의 반대짝(직교). 실 코드(`kojiro.py:891`)와 동일한 `open_price > 0 and
    current_price < open_price` 를 `ws_open` 에 대해 재현한다. `ws_open` 부재/해석
    불가는 `None`(= `-`) — WS 캐시가 없는 행에서 "붕괴 아님" 을 단정하면 안 된다.

    자문 cycle273_kojiro_gap_gate_20260910.md §3.4(다) 는 필드명·재현식만 확정했고
    (문면 = "WS 값이었으면 붕괴 가드에 걸렸을지" · 재현식 `ws_open>0 and
    current_price<ws_open`), 값 토큰은 명시하지 않았다. `pass` 를 값으로 재사용하면
    `verdict=pass`/`ws_verdict=pass` 와 값 레벨에서 섞여 앵커 없는 grep 이 더
    모호해진다(§2.1 판독표가 이미 `verdict=`↔`ws_verdict=` 접두 함정을 경고).
    `clear` 도 기각됐다 — 이 리포에서 `clear` 는 "청산"(`NEXT_DAY_CLEAR`/
    `_execute_next_day_clear`/`_force_clear_main_only` 등)의 고정 의미라, 판독자가
    "붕괴 가드에 안 걸렸다" 가 아니라 "청산했다" 로 **반대로** 읽는다(team-leader
    kojiro-gap-observe 판정, 2026-09-10). ⇒ `blocked`/`allowed`/`-` 로 확정.

    `ws_open<=0` 은 `None`(= `-`) — `_gap_rate` 가 `open_f == 0` 을 "산출 불가" 로
    다루는 같은 파일 선례(L97-98)를 따른다. 실 코드의 불리언은 `open_price<=0`
    이면 기계적으로 "붕괴 아님" 이 되지만, 그 값은 애초에 재무적으로 무의미한
    시가라 `allowed` 로 찍으면 "붕괴 가드를 안전하게 통과했을 것" 이라는 **거짓
    확신**을 준다 — 여기선 "재현 자체가 불가능하다" 는 `-` 가 더 정직하다.
    """
    if ws_open is None:
        return None
    try:
        ws_open_f = float(ws_open)
        cur_f = float(current_price)
    except (TypeError, ValueError):
        return None
    if ws_open_f <= 0:
        return None
    if cur_f < ws_open_f:
        return "blocked"
    return "allowed"


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def _fmt_gap(v: "float | None") -> str:
    return "-" if v is None else f"{v:.2f}"


def observe_gap(
    ticker,
    verdict: str,
    *,
    arg_open,
    prev_close,
    current_price,
    params,
    depth: int = 2,
) -> None:
    """`[kojiro_gap_observe]` 1행 — cap 1회/(ticker,caller,verdict)/일. **never-raise.**

    서식(기존 13필드 순서 고정 — cycle268 정본, 과거 로그 대조 유지)::

        [kojiro_gap_observe] ticker= verdict= caller= ws_cmp= arg_open= ws_open=
                             prev_close= gap_rate= ws_gap= ws_verdict= cur= gap_up= gap_down=

    cycle273-pre — 붕괴 가드 반사실 `ws_collapse=`(`blocked`/`allowed`/`-`) 를
    **끝에 추가**(기존 13필드는 byte 불변, cycle264 `truth_confirmed`/
    `truth_total` 추가 선례와 동형)::

        ... gap_down= ws_collapse=

    ⚠️ `ws_collapse` 도 경로 B(`caller=on_tick`) 행에서는 **동어반복**이다 — 모듈
    상단 docstring 경로 B 경고 참조. 오염 판정에 쓸 수 있는 것은 경로 A
    (`caller=_swing_buy_poll_loop`) 행뿐이다.
    """
    try:
        try:
            # depth=0 은 이 프레임 자신 — depth=1 이 직접 호출자, depth=2 는
            # `check_buy_signal` 을 부른 실제 호출자(§3.1 전제).
            caller = sys._getframe(depth).f_code.co_name
        except Exception:
            caller = "?"
        key = (str(ticker), caller, str(verdict))
        if not _cap.should_emit(key):
            return

        # --- 여기부터는 cap 을 통과한 뒤에만 한다(비용 순서 계약) ---------------
        from src.engine.scanner import ticker_prices as _ticker_prices

        ws_entry = _ticker_prices.get(ticker)
        if isinstance(ws_entry, dict) and "open_price" in ws_entry:
            ws_open = ws_entry.get("open_price")
            ws_cmp = "ws_eq" if ws_open == arg_open else "ws_ne"
        else:
            ws_open, ws_cmp = None, "ws_absent"

        gap_up = params.get("gap_up_skip_pct")
        gap_down = params.get("gap_down_skip_pct")

        gap_rate = _gap_rate(arg_open, prev_close)
        ws_gap = _gap_rate(ws_open, prev_close) if ws_open is not None else None
        ws_verdict = _verdict_for_gap(ws_gap, gap_up, gap_down)
        ws_collapse = _collapse_verdict_for_ws(ws_open, current_price)

        logger.info(
            "%s ticker=%s verdict=%s caller=%s ws_cmp=%s arg_open=%s ws_open=%s "
            "prev_close=%s gap_rate=%s ws_gap=%s ws_verdict=%s cur=%s gap_up=%s gap_down=%s "
            "ws_collapse=%s",
            MARKER, ticker, verdict, caller, ws_cmp,
            _fmt(arg_open), _fmt(ws_open), _fmt(prev_close),
            _fmt_gap(gap_rate), _fmt_gap(ws_gap), _fmt(ws_verdict),
            _fmt(current_price), _fmt(gap_up), _fmt(gap_down),
            _fmt(ws_collapse),
        )
        _cap.mark_emitted(key)
    except Exception:
        trace_observer_failure(MARKER, str(ticker), _cap)
