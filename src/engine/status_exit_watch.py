"""cycle369 — 관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단(지정 첫날 포함).

명세 정본 = `_workspace/red/cycle369_status_exit_spec.md`
자문 정본 = `_workspace/domain_consult/cycle369_status_51_59_exit.md`

## 요약

- **청산(§3)**: `registry.all()` 전 전략(꺼진 전략 포함)의 보유 종목을 REST
  `FHKST01010100`(`condition.fetch_stock_detail`)으로 읽어, KRX 정규장 창
  `09:00:30 <= now < 15:28:00` 안에서 읽은 값이 관리(51)·단기과열(59)이면
  `order_engine.execute_sell(t, Signal.STATUS_EXIT, sid)` 를 시장가로 낸다.
  창 밖(프리장·15:28~·애프터)은 관측(arm)만 하고 발사하지 않는다.
- **당일 매수 차단(§4, 신규)**: 그날 라이브 조회가 관리·단기과열이면 그 종목의
  신규 매수 신호를 공통 게이트(`StrategyBase._status_buy_blocked`)로 막는다.
  판정은 매일 새로 하므로 지정 첫날(T+1)부터 막힌다. 판정 완료는 **장중**
  조회만 인정한다(장 전 값은 전날 것일 수 있다 — K16).
- **패스** — P0(08:45 또는 `pre_nxt` 전략이 있으면 07:59, `<09:00:00`) · P1(09:00:05,
  25초 상한) · INC(P1 뒤 60초마다, `<15:20`) · 청산 패스(09:00:30~15:28, 300초
  격자). 관측 훅(`condition._notify_status_observer`)이 스윙 폴·기준가 REST·
  급등 스캔의 기존 조회를 **추가 호출 0** 으로 레지스트리에 기록한다.
- **fail-open** — 못 읽은 종목은 막지 않는다(K15). 판정 예외·DB 예외도 fail-open.
- **8영역 접촉 0** — `order_engine.execute_sell`(공개) · `_selling`(읽기) ·
  `registry.all()`·`enabled()`·`is_ticker_blocked_for_buy`(호출) · `scanner.ticker_prev_close`·
  `ticker_prices`(읽기)만 쓴다. `src.realtime` import 0 ·
  구독 해제 식별자 0(K7·K12).

모듈 최상위 import 는 표준 라이브러리만 쓴다 — `condition.py`·`strategy_base.py`
가 이 모듈을 lazy import 하므로 최상위에서 `src.*` 를 끌어오면 순환이 생긴다.
`src.db.system_config` · `src.db.system_logs` · `src.api.condition` ·
`src.engine.scanner` · `src.engine.strategy_base` · `src.engine.market_operation_monitor`
는 전부 함수 안 지연 import 다.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time as _time_mod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# ── 청산 창 (자문 §4(b) · K4·K5) ─────────────────────────────────────────
FIRE_WINDOW_START = time(9, 0, 30)
FIRE_WINDOW_END = time(15, 28, 0)
# ── 매수 차단 패스 시각 (명세 §4.3) ──────────────────────────────────────
PRE_PASS_TIME = time(8, 45)
PRE_PASS_TIME_NXT = time(7, 59)
BUY_OPEN_TIME = time(9, 0)
INC_END_TIME = time(15, 20)  # BUY_CUTOFF_KST 과 동치 — momentum·VB·LTV 매수 컷

SELL_INTERVAL_S = 300
INC_INTERVAL_S = 60
MAX_FIRES_PER_DAY = 3
MAX_UNKNOWN_ATTEMPTS = 3
P1_WALL_CLOCK_MAX_S = 25.0
TICKER_SLEEP_S = 0.05  # open_price_rest._TICKER_SLEEP_S 선례
LOOP_TICK_S = 1.0

MODE_ENFORCE = "enforce"
MODE_OBSERVE = "observe"
MODE_OFF = "off"
VALID_MODES = (MODE_ENFORCE, MODE_OBSERVE, MODE_OFF)
DEFAULT_MODE = MODE_ENFORCE
SELL_MODE_KEY = "status_exit_mode"
BUY_MODE_KEY = "status_buy_block_mode"

# ── buy_targets 우선순위(명세 §4.2 P1 정렬) — 낮을수록 먼저 읽는다 ────────
# 🔁 cycle369 — VB·LTV 를 BFB·VCP 보다 앞으로 옮겼다. 09:00 정각엔 급등
# 목록이 아직 비어 있고 BFB·VCP 첫 매수는 운영 DB `entry_start=09:05` 라 5분
# 여유가 있다 — 그 5분을 VB·LTV(첫 매수 09:00:35~) 에 먼저 쓴다.
_GROUP = {
    "volatility_breakout": 1, "long_tail_volatility": 1,
    "bull_flag_breakout": 2, "vcp_breakout": 2,
    "donchian_swing": 3, "kojiro": 3,
}
_SWING_GROUP = 3  # P1 은 스윙(donchian·kojiro)을 읽지 않는다 — 스윙 폴 훅이 덮는다(Q9)


def _now_kst() -> datetime:
    """테스트 시계 seam."""
    return datetime.now(_KST)


def _monotonic() -> float:
    """P1 벽시계 25초 상한 검증용 seam(`open_price_rest._monotonic` 선례)."""
    return _time_mod.monotonic()


async def _sleep(seconds: float) -> None:
    """`task_loop` 대기 seam. 루프는 이것 또는 `sched._wait_until` 로만 기다린다."""
    await asyncio.sleep(seconds)


@dataclass(frozen=True)
class StatusRead:
    """`classify(output)` 의 결과 — 순수·never-raise (명세 §2)."""

    managed: bool = False
    overheat: bool = False
    halted: bool = False
    flags_missing: bool = False
    price_ok: bool = False
    fetch_fail: bool = False
    iscd_conflict: bool = False
    unknown_values: tuple = ()
    reason: str = ""
    mang: str | None = None
    short_over: str | None = None
    iscd: str | None = None

    @property
    def flagged(self) -> bool:
        return self.managed or self.overheat

    @property
    def dedicated_flagged(self) -> bool:
        """cycle369 — 전용 플래그가 문자 그대로 `"Y"` 인가(폴백 제외).

        cycle203 실측 "51=정상 ETF·스팩·우선주" 때문에 매도는 iscd 폴백만으로
        쏘지 않는다 — 이 값이 False 인 `flagged` 는 `_sell_verdict` 에서
        `fallback_only` 로 갈라진다.
        """
        return self.mang == "Y" or self.short_over == "Y"


_FETCH_FAIL = StatusRead(fetch_fail=True)


def _flag(v, unknown: list) -> str | None:
    """`"Y"`/`"N"` 만 유효. 그 밖은 None + `unknown` 에 원문 append."""
    if v is None:
        return None
    if not isinstance(v, str):
        unknown.append(repr(v))
        return None
    s = v.strip().upper()
    if s in ("Y", "N"):
        return s
    unknown.append(v)
    return None


def classify(output) -> StatusRead:
    """FHKST01010100 응답 → `StatusRead`. 순수·never-raise(명세 §2).

    `iscd`(종목상태코드)는 전용 플래그(`mang_issu_cls_code`/`short_over_yn`)가
    **비어 있을 때만** 폴백으로 쓴다 — 명시 `"N"` 을 iscd 가 뒤집지 못한다
    (K3' — cycle203 실측 「51=정상 ETF/스팩/우선주」).
    """
    try:
        if not isinstance(output, dict) or not output:
            return _FETCH_FAIL
        unknown: list = []
        mang = _flag(output.get("mang_issu_cls_code"), unknown)
        short_over = _flag(output.get("short_over_yn"), unknown)
        temp_stop = _flag(output.get("temp_stop_yn"), [])
        raw_iscd = output.get("iscd_stat_cls_code")
        iscd = raw_iscd.strip() if isinstance(raw_iscd, str) else None
        managed = mang == "Y" or (mang is None and iscd == "51")
        overheat = short_over == "Y" or (short_over is None and iscd == "59")
        halted = iscd == "58" or temp_stop == "Y"
        flags_missing = (mang is None and iscd != "51") or (short_over is None and iscd != "59")
        prpr = output.get("stck_prpr")
        price_ok = isinstance(prpr, str) and prpr.strip().isdigit() and int(prpr.strip()) > 0
        conflict = (mang == "N" and iscd == "51") or (short_over == "N" and iscd == "59")
        reason = "+".join(n for n, on in (("managed", managed), ("overheat", overheat)) if on)
        return StatusRead(
            managed=managed, overheat=overheat, halted=halted, flags_missing=flags_missing,
            price_ok=price_ok, fetch_fail=False, iscd_conflict=conflict,
            unknown_values=tuple(unknown), reason=reason, mang=mang, short_over=short_over, iscd=iscd,
        )
    except Exception:
        return _FETCH_FAIL


def _buy_verdict(r: StatusRead) -> str:
    """매수 차단 해석(명세 §2 표) — `"flagged"`/`"unknown"`/`"clean"`."""
    if r.fetch_fail:
        return "unknown"
    if r.flagged:
        return "flagged"
    if r.flags_missing:
        return "unknown"
    return "clean"


def _sell_verdict(r: StatusRead) -> str:
    """청산 해석(명세 §2 표) — `"fire"`/`"wait_halt"`/`"fallback_only"`/`"unknown"`/`"none"`.

    cycle369 — 발사(`fire`)는 **전용 플래그가 `Y`** 일 때만이다. 종목상태
    (iscd) 폴백만으로 해당인 경우는 `fallback_only` — arm 은 하되 쏘지 않는다
    (cycle203 「51=정상 ETF·스팩·우선주」 실측 — 매도는 틀리면 비싸다).
    """
    if r.fetch_fail:
        return "unknown"
    if r.flagged and r.halted:
        return "wait_halt"
    if r.dedicated_flagged and r.price_ok:
        return "fire"
    if r.flagged and not r.dedicated_flagged:
        return "fallback_only"
    if not r.price_ok or r.flags_missing:
        return "unknown"
    return "none"


@dataclass
class _Block:
    day: date
    phase: str        # "pre" | "in"
    reason: str
    src: str
    at: datetime


# ── 모듈 전역 레지스트리(테스트 간 누수 방지 = tests/conftest.py 중립화 K20) ──
_buy_flags: dict = {}
_skip_counts: dict = {}
_unknown_attempts: dict = {}
_pre_seen: dict = {}
_in_seen: dict = {}
_emitted: set = set()
_fires: dict = {}
_armed: dict = {}
_passes: dict = {}
_modes: dict = {"sell": DEFAULT_MODE, "buy": DEFAULT_MODE}
_last_summary: list = [()]
# cycle369 — 축별 고정(저장 실패 PUT)·세대 번호(in-flight refresh 폐기)
_pinned: dict = {"sell": False, "buy": False}
_generation: dict = {"sell": 0, "buy": 0}
# cycle369 — `[status_block_armed]`/스냅샷의 "지금 이 종목이 누군가의
# 후보인가" 전역 판정용. 가장 최근에 패스를 돈 스케줄러의 registry 를 기억한다
# (패스 밖에서 부르는 관측 훅도 이 값을 쓴다 — read-only, 상태 변경 0).
_last_registry = None
# cycle369 — `_read()` 가 조회하는 동안 그 ticker 를 담는다. 관측 훅이
# 이 집합에 있는 ticker 는 기록을 건너뛴다(패스가 직접 기록한다) — 한 번의
# KIS 조회가 두 번(훅 + 패스) 세지는 것을 막는다.
_pass_fetch_active: set = set()


def reset_state_for_test() -> None:
    """레지스트리·카운터·로그 상한·모드(enforce)를 전부 초기화한다."""
    global _last_registry
    for d in (_buy_flags, _skip_counts, _unknown_attempts, _pre_seen, _in_seen, _fires, _armed, _passes):
        d.clear()
    _emitted.clear()
    _modes.update(sell=DEFAULT_MODE, buy=DEFAULT_MODE)
    _last_summary[0] = ()
    _pinned.update(sell=False, buy=False)
    _generation.update(sell=0, buy=0)
    _last_registry = None
    _pass_fetch_active.clear()


def _remember_registry(sched) -> None:
    """cycle369 — 패스가 시작할 때 registry 를 기억한다(read-only)."""
    global _last_registry
    try:
        _last_registry = sched.registry
    except Exception:
        pass


def _is_global_candidate(ticker: str) -> bool:
    """cycle369 — `ticker` 가 지금 `buy_targets(reg)` 의 멤버인가.

    이전 구현은 전략 후보 구조(`get_scanned_tickers`·`_targets`·`_candidates`·momentum
    급등 목록)를 직접 스캔했는데, 그 구조는 보유·주문중·당일매도 종목도 그대로
    담고 있어 `buy_targets` 가 거르는 배제(`registry.is_ticker_blocked_for_buy`·
    비6자리)를 몰랐다 — 보유 종목이 BFB `_candidates` 에 남아 있으면 청산 패스의
    armed 줄이 `cand=1` 로 뻥튀기됐다. `buy_targets` 자신이 그 후보 구조를 스캔한
    뒤 같은 배제를 적용하므로, 그 결과의 멤버십을 그대로 재사용한다.

    `_last_registry`(가장 최근 패스가 남긴 것)를 읽기만 한다. 레지스트리를
    모르면(테스트가 패스를 한 번도 안 돌렸으면) False — 리터럴 0 보다는
    낫지만 여전히 fail-open(관측만 줄고 차단 판정에는 영향이 없다).
    """
    reg = _last_registry
    if reg is None:
        return False
    try:
        return ticker in buy_targets(reg)
    except Exception:
        return False


def _once(key) -> bool:
    """(마커,키) 1회/일 상한 — `DailyEmitCap` 과 같은 계약을 dict 로 구현."""
    if key in _emitted:
        return False
    _emitted.add(key)
    return True


def _valid_ticker(t) -> bool:
    """진입은 6자리 숫자만(명세 §4.2 · 루트 CLAUDE.md 종목코드 형식 비대칭)."""
    return isinstance(t, str) and len(t) == 6 and t.isdigit()


def record_read(ticker, read: StatusRead, *, now: datetime, src: str) -> None:
    """레지스트리 갱신 규칙 1~4(명세 §4.3). 관측 훅·P0·P1·INC·청산 패스 공용.

    never-raise. 6자리 숫자가 아니면 무시. 모름은 상태를 바꾸지 않고 시도
    횟수만 늘린다. 장 전(now.time() < 09:00) 해당은 `phase="pre"` 로 보수적
    차단하고, 장중 판정은 `phase="in"` 으로 그날 고정한다(K16·K17).
    """
    try:
        if not _valid_ticker(ticker):
            return
        day = now.date()
        if read.unknown_values and _once(("uval", day, ticker)):
            logger.info("[status_exit_unknown_value] ticker=%s values=%s", ticker, list(read.unknown_values)[:3])
        v = _buy_verdict(read)
        if v == "unknown":
            k = (day, ticker)
            n = _unknown_attempts.get(k, 0) + 1
            _unknown_attempts[k] = n
            giveup = int(n >= MAX_UNKNOWN_ATTEMPTS)
            # cycle369 — 첫 회(attempts=1) + 상한 도달(giveup=1) 때 한 번
            # 더. 둘 다 지나면(예: n=2) 조용하다 — 그 시도는 처음도 마지막도
            # 아니라서다.
            emit = (n == 1 and _once(("unk", day, ticker))) or (
                giveup and _once(("unk_giveup", day, ticker))
            )
            if emit:
                logger.info(
                    "[status_block_unknown] ticker=%s attempts=%d reason=%s giveup=%d",
                    ticker, n,
                    "fetch_fail" if read.fetch_fail else "flags_none",
                    giveup,
                )
            return
        if read.iscd_conflict and _once(("conflict", day, ticker)):
            logger.info(
                "[status_exit_iscd_conflict] ticker=%s iscd=%s mang=%s short_over=%s",
                ticker, read.iscd, read.mang, read.short_over,
            )
        flagged = v == "flagged"
        e = _buy_flags.get(ticker)
        if e is not None and e.day != day:
            _buy_flags.pop(ticker, None)
            e = None
        if now.time() < BUY_OPEN_TIME:
            _pre_seen[ticker] = (day, flagged)
            if flagged and e is None:
                _buy_flags[ticker] = _Block(day, "pre", read.reason, src, now)
                _log_armed(ticker, read, "pre", src, day)
            return
        _in_seen[ticker] = day
        if flagged:
            if e is None or e.phase == "pre":
                _buy_flags[ticker] = _Block(day, "in", read.reason, src, now)
                _log_armed(ticker, read, "in", src, day)
            ps = _pre_seen.get(ticker)
            if ps and ps[0] == day and _once(("prechk", day, ticker)):
                logger.info(
                    "[status_block_pre_session_check] ticker=%s pre=%s in=Y",
                    ticker, "Y" if ps[1] else "N",
                )
        else:
            if e is not None and e.phase == "pre":
                _buy_flags.pop(ticker, None)
                logger.info("[status_block_released] ticker=%s reason=pre_session_stale", ticker)
            elif e is not None and e.phase == "in":
                if _once(("flip", day, ticker)):
                    logger.info("[status_block_flip_ignored] ticker=%s", ticker)
    except Exception:
        logger.debug("[status_block_record_failed] ticker=%s", ticker, exc_info=True)


def _log_armed(ticker, read: StatusRead, phase: str, src: str, day: date) -> None:
    if _once(("barmed", day, ticker)):
        logger.warning(
            "[status_block_armed] ticker=%s reason=%s phase=%s src=%s iscd=%s mang=%s "
            "short_over=%s cand=%d",
            ticker, read.reason, phase, src, read.iscd, read.mang, read.short_over,
            int(_is_global_candidate(ticker)),
        )


def observe_fhkst(ticker, output) -> None:
    """관측 훅 진입점 — `condition._notify_status_observer` 가 부른다. never-raise.

    cycle369 — leaf 자신의 패스(`_read`)가 이 조회를 유발한 것이면
    기록을 건너뛴다. 그 패스가 `record_read` 를 패스 이름(src=kind)으로 직접
    부르므로, 여기서도 기록하면 같은 한 번의 KIS 조회가 두 번(src=fetch 와
    src=<kind>) 세진다 — 모름 3회 상한이 실제로는 조회 2번에서 끝난다.
    """
    try:
        if ticker in _pass_fetch_active:
            return
        record_read(ticker, classify(output), now=_now_kst(), src="fetch")
    except Exception:
        logger.debug("[status_observer_failed] ticker=%s", ticker, exc_info=True)


def buy_gate(ticker, strategy_id, *, cand: bool = True) -> bool:
    """매수 차단 hot path 순수 조회(명세 §4.6). await·DB·HTTP 0.

    cycle369 — `cand`(이 전략이 지금 이 종목을 후보로 드는가)는 **기록
    여부만** 가른다. 막는 판정(반환값)은 후보 여부와 무관하게 늘 같다 —
    "후보가 아니라서 안 막는다" 는 절대 아니다(그건 막는 쪽 판단을 후보 목록에
    맡기는 것이라 momentum 처럼 후보 목록이 없는 전략을 못 막는다). 기본값
    `True` 는 `cand` 를 넘기지 않는 bare 호출(테스트 헬퍼 `gate()` 등)이 계속
    세도록 하는 하위호환이다.
    """
    try:
        e = _buy_flags.get(ticker)
        if e is None:
            return False
        day = _now_kst().date()
        if e.day != day:
            return False
        mode = _modes["buy"]
        if mode == MODE_OFF:
            return False
        key = (day, ticker, strategy_id)
        if mode == MODE_OBSERVE:
            if _once(("would",) + key):
                logger.info(
                    "[status_block_buy_would_skip] ticker=%s strategy=%s reason=%s",
                    ticker, strategy_id, e.reason,
                )
            return False
        if cand:
            _skip_counts[key] = _skip_counts.get(key, 0) + 1
            if _once(("skip",) + key):
                logger.info(
                    "[status_block_buy_skip] ticker=%s strategy=%s reason=%s phase=%s",
                    ticker, strategy_id, e.reason, e.phase,
                )
        return True
    except Exception:
        return False


def buy_targets(registry, *, exclude_swing: bool = False) -> list:
    """명세 §4.2 — enabled 전략 후보 ∪ momentum 급등 목록 − 차단 − 비6자리.

    `exclude_swing=True`(cycle369, P1 전용) — 스윙(donchian·kojiro)
    소속 전략을 통째로 건너뛴다. 스윙 매수 폴(09:05~09:30)이 매수 평가
    직전에 같은 조회를 해 관측 훅이 이미 덮으므로, P1 의 25초 예산을 거기
    쓸 이유가 없다. 그 전략의 후보도 `buy_targets(registry)`(기본값)에는
    그대로 남는다 — P0 는 여전히 읽는다.
    """
    group: dict = {}
    mom = False
    for s in registry.enabled():
        sid = s.strategy_id
        if sid == "momentum":
            mom = True
        g = _GROUP.get(sid, _SWING_GROUP)
        tickers: set = set()
        fn = getattr(s, "get_scanned_tickers", None)
        if callable(fn):
            try:
                tickers |= set(fn() or [])
            except Exception:
                pass
        for attr in ("_targets", "_candidates"):
            d = getattr(s, attr, None)
            if isinstance(d, dict):
                tickers |= set(d.keys())
        for t in tickers:
            group[t] = min(group.get(t, 99), g)
    if mom:
        from src.engine import scanner

        for t in list(getattr(scanner, "ticker_prev_close", {}) or {}):
            if t not in group:
                group[t] = 0
    out = []
    for t, g in group.items():
        # 스윙 소속을 여기서 거른다(momentum 급등 목록 채움 **뒤**) — 그래야
        # `ticker_prev_close` 에 우연히 같이 들어 있는 스윙 종목이 "momentum
        # 전용" 으로 재유입되지 않는다.
        if exclude_swing and g == _SWING_GROUP:
            continue
        if not _valid_ticker(t):
            continue
        try:
            if registry.is_ticker_blocked_for_buy(t):
                continue
        except Exception:
            continue
        out.append((g, t))
    return [t for _g, t in sorted(out)]


def _p1_start_time() -> time:
    """cycle369 — P1 개시 = `BUY_OPEN_TIME + condition._PRICE_CACHE_TTL`.

    5초 캐시가 08:59:55~09:00:00 사이 조회를 09:00:00~05 P1 로 되돌려 「장중
    clean」 으로 잘못 봉인하는 것을 막는다(그 캐시가 장 전 값을 들고 있다).
    조회 실패는 캐시 TTL 이 바뀌기 전 값(5.0초)으로 fail-open.
    """
    ttl = 5.0
    try:
        from src.api import condition

        ttl = float(condition._PRICE_CACHE_TTL)
    except Exception:
        pass
    base = datetime.combine(date(2000, 1, 1), BUY_OPEN_TIME) + timedelta(seconds=ttl)
    return base.time()


def _p1_order(targets: list) -> list:
    """cycle369 — P1 전용 정렬: `scanner.ticker_prices` 등락률이 +29%
    에 가까운 순으로 먼저, 값이 없는 나머지는 `buy_targets` 원래 순서(그룹→
    종목코드) 그대로 뒤에 붙인다(안정 정렬 — 원소 재배치는 여기뿐).
    """
    try:
        from src.engine import scanner

        prices = getattr(scanner, "ticker_prices", None) or {}
    except Exception:
        prices = {}

    def _dist(t: str):
        info = prices.get(t)
        if not isinstance(info, dict):
            return None
        # `scanner.ticker_prices` 의 실시간 등락률 키다(`risk.on_tick` 이 채운다) —
        # `stock_master_daily.change_rate`(DB 컬럼, UI 표시 전용, `test_cycle365_change_rate.py`
        # G-365-P4-9 가 매매 코드의 접근을 막는다)와는 무관한 별개 값이라 그 리터럴은
        # 쓰지 않는다.
        rate = info.get("prdy_ctrt")
        if rate is None:
            return None
        try:
            return abs(float(rate) - 29.0)
        except Exception:
            return None

    priced = []
    unpriced = []
    for t in targets:
        d = _dist(t)
        if d is None:
            unpriced.append(t)
        else:
            priced.append((d, t))
    priced.sort(key=lambda x: x[0])
    return [t for _d, t in priced] + unpriced


def pre_pass_time(registry) -> time:
    """P0 시각 — 기본 08:45, enabled 전략에 `pre_nxt` 보드가 있으면 07:59."""
    try:
        for s in registry.enabled():
            boards = (s.config.params or {}).get("tradable_boards")
            if boards is None:
                boards = getattr(s, "DEFAULT_TRADABLE_BOARDS", ())
            if "pre_nxt" in (boards or ()):
                return PRE_PASS_TIME_NXT
    except Exception:
        pass
    return PRE_PASS_TIME


def _resolve_mode(kind: str, raw) -> str:
    if raw is None:
        return DEFAULT_MODE
    v = str(raw).strip().lower()
    if v in VALID_MODES:
        return v
    if _once(("mode_invalid", _now_kst().date(), kind)):
        logger.warning("[status_exit_mode_invalid] kind=%s value=%r -> observe", kind, raw)
    return MODE_OBSERVE


def _emit_mode_pinned(kind: str) -> None:
    """cycle369 — 고정 동안 `[status_exit_mode_pinned]` WARNING 1회/일."""
    if _once(("mode_pinned", _now_kst().date(), kind)):
        logger.warning(
            "[status_exit_mode_pinned] kind=%s mode=%s — DB 저장 실패로 고정된 값을 "
            "refresh 가 덮지 않는다(다음 성공 저장 또는 재시작까지)",
            kind, _modes.get(kind),
        )


async def refresh_modes() -> None:
    """킬스위치 2키를 DB 에서 다시 읽는다. DB 예외는 직전 값을 유지한다(명세 §5).

    cycle369 — 축마다: (a) 고정(`_pinned[kind]`)이면 DB 를 읽지 않고
    고정 경고만 남긴다(끈 시장가 매도가 조용히 되살아나지 않게). (b) 그렇지
    않으면 세대 번호를 먼저 찍고 읽는다 — 읽는 동안(`await`) `apply_mode` 가
    끼어들면(같은 축의 PUT) 세대가 바뀌어, 늦게 돌아온 **옛 값**이 방금 저장한
    값을 덮지 않는다(다른 축의 세대는 무관 — 세대는 축마다 따로다).
    """
    from src.db import system_config

    for kind, getter in (("sell", "get_status_exit_mode_raw"), ("buy", "get_status_buy_block_mode_raw")):
        if _pinned.get(kind):
            _emit_mode_pinned(kind)
            continue
        gen_before = _generation.get(kind, 0)
        try:
            raw = await getattr(system_config, getter)()
        except Exception:
            logger.debug("[status_exit_mode_read_failed] kind=%s", kind, exc_info=True)
            continue
        if _pinned.get(kind) or _generation.get(kind, 0) != gen_before:
            # PUT 이 이 읽기가 걸려 있는 동안 그 축을 바꿨다 — 늦게 돌아온
            # 이 결과는 옛 값이니 버린다(discard, 명세 세대 번호 계약).
            continue
        _modes[kind] = _resolve_mode(kind, raw)


def apply_mode(kind: str, mode: str, *, persisted: bool = True) -> None:
    """라우트가 즉시 반영할 때 쓰는 메모리 setter.

    cycle369 — `persisted=False`(DB 저장 실패)면 그 축을 **고정**한다.
    고정된 축은 그 축의 다음 성공 저장(`persisted=True`) 또는
    `reset_state_for_test()`(재시작과 같은 효과)까지 `refresh_modes` 가
    덮지 않는다. 기본값(`persisted` 미지정)은 저장 성공 취급 = 고정 없음
    (`persisted` 를 넘기지 않는 호출과 하위호환).
    """
    if kind not in _modes or mode not in VALID_MODES:
        raise ValueError(f"bad kind/mode {kind}/{mode}")
    _modes[kind] = mode
    _generation[kind] = _generation.get(kind, 0) + 1
    _pinned[kind] = not persisted


def current_modes() -> dict:
    return dict(_modes)


def snapshot() -> dict:
    """`GET /api/integrations/status-exit` 의 `today` 필드.

    cycle369 — `armed` 은 오늘 것만(다른 날짜 항목은 P0 가 지연 정리해도
    아직 안 지웠을 수 있어 여기서도 한 번 더 날짜로 거른다). Q10 — `cand` 은
    `_is_global_candidate` 실측이다(리터럴 0 금지).
    """
    try:
        today = _now_kst().date()
    except Exception:
        today = None
    blocks = []
    for t, e in _buy_flags.items():
        if e.day != today:
            continue
        skips = {sid: n for (d, tk, sid), n in _skip_counts.items() if d == today and tk == t}
        blocks.append({
            "ticker": t, "reason": e.reason, "phase": e.phase, "src": e.src,
            "at": e.at.isoformat(), "cand": int(_is_global_candidate(t)), "skips": skips,
        })
    armed = [
        dict(v, ticker=k[0], strategy=k[1])
        for k, v in _armed.items() if v.get("day") == today
    ]
    return {"blocks": blocks, "armed": armed, "passes": dict(_passes)}


def _held(registry) -> dict:
    """`registry.all()`(꺼진 전략 포함) 의 `quantity > 0` 포지션."""
    out: dict = {}
    for s in registry.all():
        for t, pos in list(getattr(s.state, "positions", {}).items()):
            if getattr(pos, "quantity", 0) and pos.quantity > 0:
                out.setdefault(t, []).append((s.strategy_id, pos))
    return out


async def _fetch(ticker):
    from src.api.condition import fetch_stock_detail

    return await fetch_stock_detail(ticker)


async def _write(level: str, msg: str) -> None:
    try:
        from src.db.system_logs import write_log

        await write_log(level, msg)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("[status_exit_write_log_failed]", exc_info=True)


_FIRE_TICKER_RE = re.compile(r"ticker=(\S+)")
_FIRE_ATTEMPT_RE = re.compile(r"attempt=(\d+)")


async def _load_fire_counts(day: date) -> dict:
    """cycle369 — 오늘(KST) 영속된 `[status_exit_fire]` 로 종목별 발사
    횟수를 되살린다(읽기 전용). 재시작해도 하루 3회 상한·giveup 이 0 부터
    다시 세지 않게 한다.

    🔁 cycle369 — 발사 기록의 영속은 이제 루트 `_DbLogHandler` 가 logger
    WARNING 줄을 옮겨 적는 **한 줄뿐**이고, 그 줄은 `"[src.engine.status_exit_watch] "`
    접두가 붙는다. 그래서 `startswith` 가 아니라 메시지 **어디든** `[status_exit_fire]`
    가 있는지로 거른다(`[status_exit_fire_error]`·`[status_exit_would_fire]`·
    `[status_exit_giveup]` 는 그 부분 문자열을 포함하지 않으므로 오검출되지 않는다).
    각 줄의 `attempt=` 값 중 **종목별 최댓값**을 취한다(발사 n 번째의 `attempt` 는
    그 시점의 누적 발사 횟수 그 자체라 최댓값 = 실제 발사 횟수이고, 이전 빌드가 남긴
    평문 줄 같은 중복도 같은 값이라 max 로 자연히 걸러진다).
    """
    from src.db import system_logs

    out: dict = {}
    start = f"{day.isoformat()}T00:00:00+09:00"
    end = f"{day.isoformat()}T23:59:59.999999+09:00"
    res = await system_logs.search_logs(
        q="[status_exit_fire]", start=start, end=end, limit=system_logs.SEARCH_MAX_LIMIT,
    )
    for row in res.get("logs", []) or []:
        msg = row.get("message") or ""
        if "[status_exit_fire]" not in msg:
            continue
        tm = _FIRE_TICKER_RE.search(msg)
        am = _FIRE_ATTEMPT_RE.search(msg)
        if not tm or not am:
            continue
        ticker = tm.group(1)
        try:
            attempt = int(am.group(1))
        except ValueError:
            continue
        if attempt > out.get(ticker, 0):
            out[ticker] = attempt
    return out


def _frame_hint(ticker, day) -> None:
    """`H0UNMKO0` 마지막 이벤트를 힌트로만 읽는다(자문 §4(a) · read-only)."""
    try:
        from src.engine import market_operation_monitor

        ev = market_operation_monitor.get_last_event(ticker)
        code = getattr(ev, "iscd_stat_cls_code", None) if ev is not None else None
        if code in ("51", "59") and _once(("frame", day, ticker)):
            logger.info("[status_exit_frame_hint] ticker=%s iscd=%s", ticker, code)
    except Exception:
        pass


async def _read(ticker) -> StatusRead:
    """패스 공용 조회 — `record_read` 는 호출자(패스)가 한다(Q8: 훅 기록 억제)."""
    _pass_fetch_active.add(ticker)
    try:
        return classify(await _fetch(ticker))
    except asyncio.CancelledError:
        raise
    except Exception:
        return _FETCH_FAIL
    finally:
        _pass_fetch_active.discard(ticker)


def _arm(ticker, sid, read: StatusRead, phase: str, day: date) -> None:
    _armed[(ticker, sid)] = {
        "reason": read.reason, "state": phase, "fires": _fires.get((day, ticker), 0), "day": day,
    }
    if _once(("sarmed", day, ticker, read.reason)):
        logger.info(
            "[status_exit_armed] ticker=%s strategy=%s reason=%s iscd=%s mang=%s short_over=%s "
            "src=rest phase=%s",
            ticker, sid, read.reason, read.iscd, read.mang, read.short_over, phase,
        )


async def _summary(mode: str) -> None:
    """`[status_block_summary]` — 차단 집합·skip 카운트가 바뀌었을 때만 write_log.

    cycle369 — `skips=` 필드를 추가한다(전략별 오늘 총 skip 횟수). 이
    요약이 매수 차단의 **유일한 영속 기록**이라 그 안에 실려야 관측된다.
    """
    today = _now_kst().date()
    blocks = tuple(sorted((t, e.reason, e.phase) for t, e in _buy_flags.items() if e.day == today))
    skip_totals: dict = {}
    for (d, _t, sid), n in _skip_counts.items():
        if d == today:
            skip_totals[sid] = skip_totals.get(sid, 0) + n
    skips_sig = tuple(sorted(skip_totals.items()))
    sig = (blocks, skips_sig)
    if sig == _last_summary[0] or (not blocks and not skip_totals):
        _last_summary[0] = sig
        return
    _last_summary[0] = sig
    skips_str = ",".join(f"{sid}:{n}" for sid, n in sorted(skip_totals.items()))
    await _write(
        "WARNING",
        f"[status_block_summary] day={today} blocked={len(blocks)} "
        f"tickers={','.join(f'{t}:{r}' for t, r, _p in blocks)} mode={mode} skips={skips_str}",
    )


def _purge_stale_day(day: date) -> None:
    """cycle369 — P0 메모리 위생. 날짜가 든 **모든** 저장소에서 다른
    날짜 항목을 지운다 — 프로세스 수명 동안 자라지 않게 한다. never-raise.
    """
    try:
        for d in (_unknown_attempts, _fires, _skip_counts):
            for k in [k for k in d if k[0] != day]:
                d.pop(k, None)
        for k in [k for k, e in list(_buy_flags.items()) if e.day != day]:
            _buy_flags.pop(k, None)
        for t in [t for t, v in list(_pre_seen.items()) if v[0] != day]:
            _pre_seen.pop(t, None)
        for t in [t for t, d2 in list(_in_seen.items()) if d2 != day]:
            _in_seen.pop(t, None)
        for k in [k for k, v in list(_armed.items()) if v.get("day") != day]:
            _armed.pop(k, None)
        for k in [k for k, v in list(_passes.items()) if v.get("day") != day]:
            _passes.pop(k, None)
        for k in [k for k in _emitted if len(k) > 1 and isinstance(k[1], date) and k[1] != day]:
            _emitted.discard(k)
    except Exception:
        logger.debug("[status_exit_purge_failed]", exc_info=True)


async def run_pre_pass(sched) -> dict:
    """P0 — 장 전 1회. 보유 ∪ `buy_targets`. 해당이면 phase=pre 차단·arm 만(주문 0)."""
    await refresh_modes()
    _remember_registry(sched)
    now = _now_kst()
    day = now.date()
    _purge_stale_day(day)
    held = _held(sched.registry) if _modes["sell"] != MODE_OFF else {}
    targets = buy_targets(sched.registry) if _modes["buy"] != MODE_OFF else []
    order = list(held) + [t for t in targets if t not in held]
    start = _monotonic()
    read_n = 0
    flagged_n = 0
    fetch_fail_n = 0
    unknown_n = 0
    for t in order:
        r = await _read(t)
        read_n += 1
        v = _buy_verdict(r)
        if v == "flagged":
            flagged_n += 1
        if r.fetch_fail:
            fetch_fail_n += 1
        if v == "unknown":
            unknown_n += 1
        record_read(t, r, now=_now_kst(), src="p0")
        for sid, _pos in held.get(t, ()):
            if _sell_verdict(r) in ("fire", "wait_halt"):
                _arm(t, sid, r, "pre", day)
        await asyncio.sleep(TICKER_SLEEP_S)
    elapsed_ms = int((_monotonic() - start) * 1000)
    _passes["p0"] = {
        "targets": len(order), "read": read_n, "flagged": flagged_n,
        "fetch_fail": fetch_fail_n, "unknown": unknown_n, "truncated": 0,
        "elapsed_ms": elapsed_ms, "at": now.isoformat(), "day": day,
    }
    logger.info(
        "[status_block_pass] kind=p0 targets=%d read=%d truncated=0 mode=%s",
        len(order), read_n, _modes["buy"],
    )
    await _summary(_modes["buy"])
    return {"read": read_n}


async def run_buy_pass(sched, *, kind: str) -> dict:
    """P1(`kind="p1"`)·INC(`kind="inc"`) — `buy_targets` − 오늘 장중 판정 완료.

    cycle369 — P1 은 스윙(donchian·kojiro)을 뺀 `buy_targets` 를 등락률
    +29% 근접 순으로 읽는다(스윙은 09:05~09:30 폴 훅이 이미 덮는다).
    """
    await refresh_modes()
    _remember_registry(sched)
    if _modes["buy"] == MODE_OFF:
        return {"read": 0}
    now = _now_kst()
    day = now.date()
    if kind == "p1":
        targets = _p1_order(buy_targets(sched.registry, exclude_swing=True))
    else:
        targets = buy_targets(sched.registry)
    seen = [t for t in targets if _in_seen.get(t) == day]
    todo = [
        t for t in targets
        if _in_seen.get(t) != day and _unknown_attempts.get((day, t), 0) < MAX_UNKNOWN_ATTEMPTS
    ]
    start = _monotonic()
    truncated = 0
    read_n = 0
    flagged_n = 0
    fetch_fail_n = 0
    unknown_n = 0
    for t in todo:
        if _monotonic() - start > P1_WALL_CLOCK_MAX_S:
            truncated = 1
            break
        r = await _read(t)
        read_n += 1
        v = _buy_verdict(r)
        if v == "flagged":
            flagged_n += 1
        if r.fetch_fail:
            fetch_fail_n += 1
        if v == "unknown":
            unknown_n += 1
        record_read(t, r, now=_now_kst(), src=kind)
        await asyncio.sleep(TICKER_SLEEP_S)
    elapsed_ms = int((_monotonic() - start) * 1000)
    _passes[kind] = {
        "targets": len(targets), "read": read_n, "flagged": flagged_n,
        "fetch_fail": fetch_fail_n, "unknown": unknown_n, "truncated": truncated,
        "elapsed_ms": elapsed_ms, "at": now.isoformat(), "day": day,
    }
    if kind == "p1" or read_n > 0:
        logger.info(
            "[status_block_pass] kind=%s targets=%d read=%d skipped_seen=%d truncated=%d mode=%s",
            kind, len(targets), read_n, len(seen), truncated, _modes["buy"],
        )
    await _summary(_modes["buy"])
    return {"read": read_n, "truncated": truncated}


async def run_sell_pass(sched) -> dict:
    """청산 패스 — 창 안(09:00:30~15:28)에서만 발사(명세 §3)."""
    await refresh_modes()
    _remember_registry(sched)
    mode = _modes["sell"]
    now = _now_kst()
    day = now.date()
    if mode == MODE_OFF:
        return {"fired": 0}
    if not (FIRE_WINDOW_START <= now.time() < FIRE_WINDOW_END):
        return {"fired": 0}
    from src.engine.strategy_base import Signal

    held = _held(sched.registry)
    # cycle369 — 더 이상 보유하지 않는 (종목,전략) 은 armed 에서 뺀다
    # (같은 날 매도 완료 종목이 「매도 대기」로 오판되지 않게).
    held_pairs = {(t, sid) for t, lst in held.items() for sid, _p in lst}
    for k in [k for k in _armed if k not in held_pairs]:
        _armed.pop(k, None)
    oe = sched.order_engine
    fired = 0
    for t in sorted(held):
        r = await _read(t)
        record_read(t, r, now=now, src="sell")
        _frame_hint(t, day)
        v = _sell_verdict(r)
        for sid, pos in held[t]:
            if v == "fire":
                _arm(t, sid, r, "in", day)
                if t in oe._selling:
                    continue
                n = _fires.get((day, t), 0)
                if n >= MAX_FIRES_PER_DAY:
                    if _once(("giveup", day, t)):
                        msg = f"[status_exit_giveup] ticker={t} strategy={sid} fires={n}"
                        logger.critical(msg)
                    continue
                # cycle369 — 발사 직전 창을 다시 본다. 조회가 오래 걸려
                # (시세 풀 지연) 이 시점이 15:28 을 넘겼으면 그 종목은 쏘지
                # 않는다 — 카운터 증가·마커·주문 **전부** 이 재확인 뒤에 온다
                # (재확인을 카운터 증가 뒤에 두면 창 밖 미발사가 하루 3회
                # 상한을 축낸다).
                now_fire = _now_kst()
                if not (FIRE_WINDOW_START <= now_fire.time() < FIRE_WINDOW_END):
                    continue
                # 🔁 cycle369 — 창 재확인 옆에서(`_fires` 증가 **앞**) 킬스위치를
                # 다시 읽는다. 패스는 시작 때 모드를 1회 읽으므로, 앞 종목의 `_read`
                # 나 `execute_sell` 을 기다리는 동안 도착한 `PUT sell_mode=off/observe`
                # 가 이 재확인이 없으면 뒤 종목에 반영되지 않는다.
                mode_now = _modes["sell"]
                if mode_now != MODE_ENFORCE:
                    if mode_now == MODE_OBSERVE:
                        if _once(("would_fire", day, t, sid)):
                            msg = f"[status_exit_would_fire] ticker={t} strategy={sid} reason={r.reason}"
                            logger.warning(msg)
                    continue
                _fires[(day, t)] = n + 1
                bought_today = int(getattr(pos, "buy_date", None) == day)
                msg = (
                    f"[status_exit_fire] ticker={t} strategy={sid} reason={r.reason} iscd={r.iscd} "
                    f"mang={r.mang} short_over={r.short_over} qty={pos.quantity} mode=enforce "
                    f"attempt={n + 1} bought_today={bought_today}"
                )
                # 🔁 cycle369 — 영속은 루트 `_DbLogHandler` 가 이 logger 줄을
                # 큐로 옮겨 적는 한 줄뿐이다(`_spawn_write` 로 한 번 더 쓰면 같은
                # 발사가 system_logs 에 두 줄 — cycle72 G-6 이중 INSERT 금지).
                logger.warning(msg)
                fired += 1
                try:
                    # cycle369 — `stop()` 이 이 패스 task 를 취소해도
                    # 이미 제출 중인 주문은 끝까지 간다(매핑·PENDING 없이
                    # 나가는 반쪽 주문 차단).
                    await asyncio.shield(oe.execute_sell(t, Signal.STATUS_EXIT, sid))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "[status_exit_fire_error] ticker=%s strategy=%s err=%s",
                        t, sid, str(exc)[:150],
                    )
            elif v == "fallback_only":
                # cycle369 — 전용 플래그가 비고 종목상태(iscd) 폴백만
                # 맞았다. arm 은 해 운영자가 보게 하되 쏘지 않는다(cycle203
                # "51=정상 ETF·스팩·우선주" — 매도는 틀리면 비싸다).
                _arm(t, sid, r, "in", day)
                if _once(("fallback", day, t)):
                    logger.warning(
                        "[status_exit_fallback_only] ticker=%s strategy=%s iscd=%s mang=%s "
                        "short_over=%s",
                        t, sid, r.iscd, r.mang, r.short_over,
                    )
            elif v == "wait_halt":
                _arm(t, sid, r, "in", day)
                if _once(("halt", day, t)):
                    logger.info("[status_exit_wait_halt] ticker=%s iscd=%s", t, r.iscd)
            elif v == "unknown":
                if _once(("sunk", day, t)):
                    logger.info("[status_exit_unknown] ticker=%s", t)
            else:
                if _armed.pop((t, sid), None) is not None and _once(("disarm", day, t, sid)):
                    logger.info("[status_exit_disarmed] ticker=%s strategy=%s", t, sid)
    logger.info("[status_exit_summary] held=%d fired=%d mode=%s", len(held), fired, mode)
    return {"fired": fired}


def due_actions(now: datetime, *, pre_time: time, p1_time: time = BUY_OPEN_TIME, pre_done: bool,
                p1_done: bool, last_sell_at: datetime | None, last_inc_at: datetime | None) -> list:
    """순수 planner — `now` 와 하루 상태로 이번 tick 에 돌 패스 목록을 정한다.

    `p1_time`(cycle369, 기본 `BUY_OPEN_TIME` = 하위호환) — P1 이 실제로
    개시되는 시각. `task_loop` 는 `_p1_start_time()`(09:00:05)을 넘긴다.

    🔁 cycle369 — P0 창의 위쪽 끝은 **`p1_time` 이 아니라 `BUY_OPEN_TIME`**
    (09:00:00) 이다. P1 시작을 09:00:05 로 미룰 때 P0 창의 위쪽 끝까지 같은
    `p1_time` 을 썼는데, 그러면 09:00:00~05 에 시작한 루프(in-process 재시작 —
    `/api/trading/restart` 는 condition 5초 캐시를 비우지 않는다)가 P0 를 돌아
    08:59:5x 캐시의 **장 전** clean 값을 `now>=09:00` 으로 「장중 clean」 으로
    봉인한다. P0 창을 09:00:00 에서 끊으면 그 5초 동안은 아무 패스도 안 돌고,
    P1(09:00:05)이 그 종목을 새로 읽어 막는다.
    """
    t = now.time()
    if t >= FIRE_WINDOW_END:
        return ["exit"]
    out = []
    if not pre_done and pre_time <= t < BUY_OPEN_TIME:
        out.append("pre")
    if not p1_done and p1_time <= t < INC_END_TIME:
        out.append("buy_open")
    if FIRE_WINDOW_START <= t < FIRE_WINDOW_END:
        base = now.replace(hour=9, minute=0, second=30, microsecond=0)
        k = int((now - base).total_seconds() // SELL_INTERVAL_S)
        slot = base + timedelta(seconds=SELL_INTERVAL_S * k)
        if last_sell_at is None or last_sell_at < slot:
            out.append("sell")
    if (
        p1_done and t < INC_END_TIME and last_inc_at is not None
        and (now - last_inc_at).total_seconds() >= INC_INTERVAL_S
    ):
        out.append("inc")
    return out


async def task_loop(sched) -> None:
    """08:00~20:00 하루 일정을 돈다. 대기는 `_sleep` 만 쓴다.

    cycle369 — 시작할 때 오늘(KST) 영속 발사 횟수를 1회 읽어 메모리
    카운터와 **max** 로 합친다(재시작해도 하루 3회 상한이 이어진다). 조회
    실패는 fail-open — 메모리 카운터만으로 계속 돈다.
    """
    try:
        await refresh_modes()
    except Exception:
        pass
    today0 = _now_kst().date()
    try:
        seeded = await _load_fire_counts(today0)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("[status_exit_fire_seed_failed]", exc_info=True)
        seeded = None
    if seeded:
        for tkr, n in seeded.items():
            try:
                n = int(n)
            except Exception:
                continue
            k = (today0, tkr)
            if n > _fires.get(k, 0):
                _fires[k] = n
    plan: dict = {"day": None}
    while True:
        if not getattr(sched, "_running", False):
            logger.info("[status_exit_loop_exit] reason=running_false")
            return
        now = _now_kst()
        if plan["day"] != now.date():
            plan = {
                "day": now.date(), "pre_done": False, "p1_done": False,
                "last_sell_at": None, "last_inc_at": None,
            }
        actions = due_actions(
            now, pre_time=pre_pass_time(sched.registry), p1_time=_p1_start_time(),
            pre_done=plan["pre_done"], p1_done=plan["p1_done"],
            last_sell_at=plan["last_sell_at"], last_inc_at=plan["last_inc_at"],
        )
        if "exit" in actions:
            logger.info("[status_exit_loop_exit] reason=after_close")
            return
        # cycle369 — 휴장일(False) 이 확정된 날은 어떤 패스도 돌지
        # 않는다(주말·공휴일 수동 기동이 금요일 값으로 시장가 매도를 내지
        # 않게). 모름(None)·조회 예외는 돈다 — 판정 실패가 청산을 끄면
        # 안 된다.
        try:
            from src.engine import trading_calendar

            open_day = await trading_calendar.is_open_day(now.date())
        except asyncio.CancelledError:
            raise
        except Exception:
            open_day = None
        if open_day is False:
            actions = []
        for a in actions:
            try:
                if a == "pre":
                    plan["pre_done"] = True
                    await run_pre_pass(sched)
                elif a == "buy_open":
                    plan["p1_done"] = True
                    plan["last_inc_at"] = now
                    await run_buy_pass(sched, kind="p1")
                elif a == "sell":
                    plan["last_sell_at"] = now
                    await run_sell_pass(sched)
                elif a == "inc":
                    plan["last_inc_at"] = now
                    await run_buy_pass(sched, kind="inc")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("[status_exit_pass_failed] action=%s", a, exc_info=True)
        await _sleep(LOOP_TICK_S)
