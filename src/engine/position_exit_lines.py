"""cycle339 — 보유 종목의 **청산선**(손절가·목표가)을 잔고 화면에 노출하기 위한 순수 leaf.

사용자 요청 = "잔고내역에 각 종목별로 전략별 진입할 때 설정한 손절가와 목표가
정보가 추가로 있었으면 좋겠는데".

## 이 파일이 지키는 것

🔴 **틀린 손절가는 없는 것보다 나쁘다.** 운영자가 이 숫자를 보고 "여기까지는
버틴다" 를 판단하는 화면이라, 값이 불확실하면 숫자를 지어내지 않고 `None` 으로
둔다. 그리고 **어디서 온 값인지**(`stop_source`)를 항상 함께 낸다 — 같은 칸에
서로 다른 정확도의 값이 섞이는데 그것을 화면이 구분하지 못하면 둘 다 못 믿는다.

## 두 출처의 정확도가 다르다

| `stop_source` | 뜻 | 정확도 |
|---|---|---|
| `effective` | 전략의 `get_effective_stop_price` — `check_exit_signal` 과 **동일 산식·동일 상태 소스** | 그 전략이 실제로 쓰는 선 |
| `hard_pct` | `buy_price × (1 + 하드손절% / 100)` | 고정% 손절 전략의 **근사**(트레일링·시간 청산은 못 담는다) |
| `None` | 판정 불가 | 화면은 `—` |

`get_effective_stop_price` 는 보유형 4전략(kojiro·donchian·VCP·BFB)만 override
하고 나머지는 base 가 `None` 을 돌려준다(`strategy_base.py:1225`) — 그것이
"프록시로 폴백하라" 는 신호다. 여기서 그 폴백이 `hard_pct` 다.

🔴 **가격 무관 청산은 어느 출처에도 안 담긴다** — VB 의 15:20 일괄매도, kojiro 의
stage3 추세종료, 익일청산이 그것이다. 손절가 칸이 비어 있지 않다고 해서 그 종목이
그 가격까지 안 팔리는 것은 아니다.

## 목표가는 거의 없다

🔴 **우리 7전략 중 목표가가 실재하는 것은 `bull_flag_breakout` 하나**이고, 그마저
전량 익절이 아니라 **부분 익절 트리거**(`measured_target` = flag_high + pole_width)다.
나머지는 트레일링·시간·스테이지로 나가므로 목표가라는 개념이 없다.

⚠️ **VB·LTV 의 `target_price` 를 목표가로 쓰지 않는다** — 그것은 **매수 트리거
가격**(시가 + K × 전일 Range)이지 익절가가 아니다. 이미 산 종목의 "목표가" 칸에
넣으면 완전한 거짓 정보가 된다.

## 계약

- **read-only** — 전략 상태를 하나도 바꾸지 않는다. 래치·`_stop_floor`·cap 무변조.
  (VCP/BFB 의 `_effective_setup(observe=False)` 독트린을 `get_effective_stop_price`
  가 이미 지키므로 여기서는 그 함수를 그대로 부른다.)
- **never-raise** — 어떤 예외도 흡수하고 `None` 으로 물러선다. 잔고 화면이 이
  계산 때문에 죽으면 안 된다.
- `await`/DB/HTTP **0** — 전부 in-memory 조회다.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

__all__ = ["ExitLines", "resolve_exit_lines", "build_exit_line_map"]

#: 목표가를 실제로 갖는 전략과 그 값의 성격.
_MEASURED_MOVE_STRATEGIES = frozenset({"bull_flag_breakout"})

#: 🔴 **하나의 고정% 로 접을 수 없는 전략** — `hard_pct` 근사를 쓰지 않는다.
#:
#: `long_tail_volatility` 는 보유 중 **모드가 갈린다** — 당일 모드는
#: `intraday_stop_loss`, 상한가 모드(`_limit_up_reached`)는 `overnight_stop_loss` 다.
#: 운영 DB 실측 = `intraday -5` · `overnight -3.5` 이고 `extract_hard_stop_pct` 는
#: **음수 min** 을 취하므로 항상 **−5** 를 낸다. 그런데 상한가 모드의 실제 임계는
#: **−3.5**(더 조인다) — 화면이 −5 를 가리키면 운영자가 **1.5%p 여유가 더 있다고
#: 오판**한다. 🔴 이 함정은 메모리에 이미 박제돼 있다(「LTV 상한가 전환은 −5→−3.5 로
#: **조여진다** — 코드만 보면 느슨해지는 것으로 읽혀 그렇게 보고했다가 틀렸다」).
#:
#: 모드는 `_limit_up_reached`(메모리 전용)라 leaf 가 밖에서 판정할 수 없다. 그래서
#: 근사를 내지 않고 **`—`(`stop_source="mode_dependent"`)** 로 둔다 — 틀린 손절가는
#: 없는 것보다 나쁘다. 정확히 내려면 그 전략에 `get_effective_stop_price` 미러를
#: 붙여야 하는데, 그러면 `account_risk_watcher` 의 계좌 SOFT 게이트 입력값이 바뀌어
#: **`domain-consult` 선행**이 필요하다(별건).
_MODE_DEPENDENT_STOP_STRATEGIES = frozenset({"long_tail_volatility"})


class ExitLines(dict):
    """`{strategy_id, stop_price, stop_source, target_price, target_source}` dict.

    dict 서브클래스로 둔 이유 = 라우트가 그대로 `payload.update(...)` 할 수 있고
    pydantic 직렬화 경로를 새로 타지 않는다.
    """


def _empty(strategy_id: str | None = None) -> ExitLines:
    return ExitLines(
        strategy_id=strategy_id,
        stop_price=None,
        stop_source=None,
        target_price=None,
        target_source=None,
    )


def _positive_int(value: Any) -> int | None:
    """양의 정수로 해석되면 그 값, 아니면 None. bool 은 거부한다."""
    if isinstance(value, bool):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _effective_stop(strategy: Any, ticker: str) -> int | None:
    fn = getattr(strategy, "get_effective_stop_price", None)
    if not callable(fn):
        return None
    try:
        return _positive_int(fn(ticker))
    except Exception:
        logger.debug("[exit_lines] get_effective_stop_price 실패 ticker=%s", ticker,
                     exc_info=True)
        return None


def _hard_pct_stop(strategy: Any, ticker: str) -> int | None:
    """고정% 손절 전략의 근사선 — `buy_price × (1 + 하드손절%/100)`.

    🔴 `extract_hard_stop_pct` 는 후보 7키 중 **음수만** 모아 min 을 취한다(가장
    보수적인 선). 결측이면 −7.0 으로 fail-open 하는데, 그 기본값으로 계산한
    숫자를 화면에 띄우면 **설정한 적 없는 손절가**가 보인다. 그래서 여기서는
    키가 실제로 있을 때만 값을 낸다 — 없으면 `None` 이다.
    """
    try:
        from src.engine.portfolio_risk import extract_hard_stop_pct
    except Exception:
        return None
    try:
        params = getattr(getattr(strategy, "config", None), "params", None)
        if not isinstance(params, dict):
            return None
        sentinel = -999.0
        pct = extract_hard_stop_pct(params, default=sentinel)
        if pct == sentinel or not isinstance(pct, (int, float)) or pct >= 0:
            return None
        pos = getattr(strategy, "state", None)
        positions = getattr(pos, "positions", None)
        if not isinstance(positions, dict):
            return None
        p = positions.get(ticker)
        buy_price = _positive_int(getattr(p, "buy_price", None))
        if buy_price is None:
            return None
        return _positive_int(round(buy_price * (1.0 + float(pct) / 100.0)))
    except Exception:
        logger.debug("[exit_lines] hard_pct 계산 실패 ticker=%s", ticker, exc_info=True)
        return None


def _measured_target(strategy: Any, strategy_id: str, ticker: str) -> tuple[int | None, bool]:
    """BFB 의 측정 목표가(부분 익절 트리거) `(target, already_hit)`. 그 밖은 `(None, False)`.

    🔴 **`get_targets_status()` 를 쓰지 않는다.** 그쪽은 `_candidates` 를 순회하는데
    `_candidates` 는 `prepare()` 마다 와이프되고 **보유 종목은 후보 자격을 잃는 것이
    정상**이라, 그 경로로는 화면이 **영구히 빈 칸**이다(funnel `step_no=99` 6영업일
    실측 — 보유 2종목이 하루도 후보에 없었다). 전략의 read-only 미러
    `get_effective_target_price` 가 `_effective_setup` stamp 폴백을 타므로 그것만 쓴다.
    """
    if strategy_id not in _MEASURED_MOVE_STRATEGIES:
        return None, False
    fn = getattr(strategy, "get_effective_target_price", None)
    if not callable(fn):
        return None, False
    try:
        result = fn(ticker)
        if isinstance(result, tuple) and len(result) == 2:
            return _positive_int(result[0]), bool(result[1])
        return _positive_int(result), False
    except Exception:
        logger.debug("[exit_lines] measured_target 실패 ticker=%s", ticker, exc_info=True)
        return None, False


def resolve_exit_lines(strategies: Iterable[Any], ticker: str) -> ExitLines:
    """`ticker` 를 보유한 전략을 찾아 그 청산선을 돌려준다.

    보유 전략이 없으면(수동 매매분·동기화 전) 전 필드 `None` 이다 — **추측하지
    않는다**. 두 전략이 같은 종목을 들고 있는 일은 `is_ticker_blocked_for_buy`
    가 막지만, 만약 그런 상태가 되면 **처음 찾은 전략**을 쓴다(순서는 registry
    등록 순이고, 그 상황 자체가 이미 다른 결함의 증상이다).
    """
    if not ticker:
        return _empty()
    try:
        for s in strategies:
            state = getattr(s, "state", None)
            positions = getattr(state, "positions", None)
            if not isinstance(positions, dict) or ticker not in positions:
                continue
            sid = getattr(s, "strategy_id", None) or getattr(
                getattr(s, "config", None), "strategy_id", None
            )
            sid = sid if isinstance(sid, str) else None

            stop = _effective_stop(s, ticker)
            source = "effective" if stop is not None else None
            if stop is None and sid in _MODE_DEPENDENT_STOP_STRATEGIES:
                # 🔴 근사를 내지 않는다 — 위 `_MODE_DEPENDENT_STOP_STRATEGIES` 주석.
                source = "mode_dependent"
            elif stop is None:
                stop = _hard_pct_stop(s, ticker)
                source = "hard_pct" if stop is not None else None

            target, target_hit = _measured_target(s, sid or "", ticker)
            return ExitLines(
                strategy_id=sid,
                stop_price=stop,
                stop_source=source,
                target_price=target,
                target_source=("measured_move_hit" if target_hit else "measured_move")
                if target is not None else None,
            )
    except Exception:
        logger.debug("[exit_lines] 전략 순회 실패 ticker=%s", ticker, exc_info=True)
    return _empty()


def build_exit_line_map(
    strategies: Iterable[Any],
    tickers: Iterable[str],
    *,
    engine_running: bool = True,
) -> dict:
    """여러 종목을 한 번에 — `{ticker: ExitLines}`. never-raise.

    🔴 `engine_running=False` 면 판정 불가를 **`stop_source="engine_idle"`** 로
    구분한다. 매매 엔진은 21:30 `_reset_daily_state` 가 메모리 포지션을 비우고
    07:45 `_boot()` 가 DB 에서 되살리므로, 그 사이(하루 ~10시간)에는 보유가 있어도
    청산선을 알 길이 없다 — **그것은 「손절선이 없다」가 아니라 「지금은 모른다」다.**
    둘을 같은 `—` 로 접으면 운영자가 아침에 화면을 보고 "손절이 안 걸려 있다" 로
    읽는다(실측: 2026-09-21 23:57 배포 직후 보유 9건 전부 `—`).

    ⚠️ 판정은 **엔진 상태**로 한다 — "메모리 포지션이 0 이다" 로 추론하면 수동
    매수분만 들고 있는 정상 상태가 「엔진 정지」로 잘못 찍힌다.
    """
    out: dict[str, ExitLines] = {}
    try:
        strategy_list = list(strategies)
    except Exception:
        strategy_list = []
    for t in tickers:
        try:
            lines = resolve_exit_lines(strategy_list, t)
        except Exception:
            lines = _empty()
        if (not engine_running
                and lines.get("stop_price") is None
                and lines.get("stop_source") is None):
            lines["stop_source"] = "engine_idle"
        out[t] = lines
    return out
