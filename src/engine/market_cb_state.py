"""서킷브레이커·사이드카 인지 leaf (cycle465 — 사용자 결정 2026-10-16 「인지 + R3 C」).

메인 세션이 시장 대표 종목의 장운영정보(KRX `H0STMKO0` · 통합 `H0UNMKO0`)를 구독하고,
그 프레임의 장운영 구분 코드(MKOP_CLS_CODE)로 시장(코스피·코스닥)별 상태를 둔다.
자문 = `_workspace/domain_consult/2026-10-16_market_cb_sidecar_detect.md`.

- 서킷브레이커(CB)·시장임시정지(164) 중에는 09:00~15:30 안에서 후보(LOW) 종목 재구독을
  멈춘다(`is_low_resub_suppressed`). 보유(HIGH)는 호출부가 건드리지 않는다.
- 사이드카는 기록·표시만 한다 — 프로그램매매만 5분 멈추고 일반 체결은 계속된다.
- 대표 종목의 VI·거래정지·종목상태는 판정에 쓰지 않는다(시장 코드 집합만 본다).
- 매매 신호·주문·청산 무접촉. 표준 라이브러리만 최상위 import(8영역·scheduler import 0).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

MARKETS = ("KOSPI", "KOSDAQ")

#: 시장 대표 종목 — 시장 코드는 종목과 무관하게 같으므로 시장당 1종목이면 된다.
#: 코스닥 대표 = 196170(알테오젠). 이전상장·장기 정지 공시가 나면 이 줄을 바꾼다.
REP_MARKET: dict[str, str] = {"005930": "KOSPI", "196170": "KOSDAQ"}

#: 부팅 때 메인 세션에 거는 대표 구독. 기존 `H0UNMKO0/005930`(보드 기록용, scheduler)은
#: 그대로 두고 그 밖 3건만 여기서 건다. 🔴 늘리지 않는다(메인 VI 0건 규약 cycle221 의
#: 명시적 예외 — 시장 코드 대표 구독. AST 가 원소 수 ≤ 3 을 잠근다).
MARKET_STATUS_REPS: tuple[tuple[str, str], ...] = (
    ("H0STMKO0", "005930"),
    ("H0STMKO0", "196170"),
    ("H0UNMKO0", "196170"),
)

#: KRX 채널 숫자 코드(`docs/kis/domestic-stock-realtime.md` H0STMKO0 표) + 통합 채널
#: 알파벳 코드(10-15 실측 — AF8 정지 → AF1 단일가 → BF9 재개, V0: 그날 말고는 미출현).
_CB_ENTER_ST = frozenset({"174", "182", "184"})
_CB_ENTER_UN = frozenset({"AF8", "AF1"})
_CB_RELEASE_ST = frozenset({"175", "185"})
_CB_RELEASE_UN = frozenset({"BF9"})
#: 알파벳 계열이 상태를 바꾸는가 — 정상일에도 나오는 것이 확인되면 False(기록만)로 내린다.
_UN_CODES_DRIVE_STATE = True
_HALT_CODE = "164"
_HALT_RELEASE = frozenset({"112"})
_SIDECAR_ON = {"387": "sell", "397": "buy"}
_SIDECAR_OFF = {"388": "sell", "398": "buy"}
_KNOWN_NORMAL = frozenset({
    "110", "112", "121", "129", "130", "139", "140", "146", "149", "150", "156", "159",
    "AB1",  # 통합 채널 VI 단계 코드(cycle359 §3.1) — 종목 사건이라 시장 상태와 무관
})

#: 마지막 활성 프레임 뒤 해제 코드가 없으면 풀리는 시간(20분 정지 + 10분 단일가 + 여유).
CB_TTL_SECS = 2400
HALT_TTL_SECS = 2400
SIDECAR_TTL_SECS = 360
#: 해제 뒤 유예 — 재개 첫 체결이 기존 구독으로 들어올 시간.
#: = `stale_watcher_core.RESUBSCRIBE_THROTTLE_SECS`(테스트가 같은 값을 확인한다).
RELEASE_GRACE_SECS = 180
#: 해제 뒤 이 안에 다시 오는 발동 코드는 같은 단계로 본다(오차 프레임).
REENTRY_SAME_STAGE_SECS = 300
#: 1·2단계는 14:50 이후 발동되지 않는다.
_LATE_CB_CUTOFF = time(14, 50)
LOW_SKIP_START = time(9, 0)
LOW_SKIP_END = time(15, 30)
_EVENTS_MAX = 10
#: 코드 변화 관측 기록(cycle468)의 (시장, 출처)당 하루 상한.
TRACE_DAILY_MAX = 200

_CB = "CB_ACTIVE"
_HALT = "HALT_164"
_RELEASED = "RELEASED"
_NORMAL = "NORMAL"
_SUPPRESSING = frozenset({_CB, _HALT, _RELEASED})


def _fresh_market() -> dict:
    return {
        "state": _NORMAL, "stage": 0, "since": None, "last_active_at": None,
        "last_code": "", "source": "", "released_at": None,
    }


_day: date | None = None
_markets: dict[str, dict] = {m: _fresh_market() for m in MARKETS}
_sidecar: dict[str, dict | None] = {m: None for m in MARKETS}
_events: list[dict] = []
_unknown_logged: set[str] = set()
_trace_prev: dict[tuple[str, str], str] = {}
_trace_count: dict[tuple[str, str], int] = {}


def reset_market_cb_state() -> None:
    """21:30 `_reset_daily_state` 동행(`market_operation_monitor.reset_market_op_state` 경유)."""
    global _day
    _day = None
    for m in MARKETS:
        _markets[m] = _fresh_market()
        _sidecar[m] = None
    _events.clear()
    _unknown_logged.clear()
    _trace_prev.clear()
    _trace_count.clear()


def _now() -> datetime:
    return datetime.now(_KST)


def _roll_day(now: datetime) -> None:
    global _day
    d = now.date()
    if _day != d:
        reset_market_cb_state()
        _day = d


def _source(code: str) -> str:
    return "UN" if code[:1].isalpha() else "ST"


def _is_quiet_code(code: str) -> bool:
    return code in _KNOWN_NORMAL or code[:1] in ("F", "P")


def _trace_code(market: str, code: str, now: datetime) -> None:
    """대표 종목 코드가 바뀔 때마다 한 줄(cycle468 — 판정 로직 무관, 관측 전용).

    182·175·185 의 실제 뜻과 도착 순서를 다음 CB·임시정지 때 확정하려고 남긴다.
    정상 코드끼리의 변화 = INFO, 한쪽이라도 정상 밖 코드 = WARNING(30일 보관).
    """
    key = (market, _source(code))
    prev = _trace_prev.get(key)
    if prev == code:
        return
    _trace_prev[key] = code
    n = _trace_count.get(key, 0)
    if n > TRACE_DAILY_MAX:
        return
    _trace_count[key] = n + 1
    if n == TRACE_DAILY_MAX:
        logger.warning(
            "[market_status_code_trace] market=%s source=%s cap_reached=1 limit=%d",
            market, key[1], TRACE_DAILY_MAX,
        )
        return
    quiet = _is_quiet_code(code) and (prev is None or _is_quiet_code(prev))
    (logger.info if quiet else logger.warning)(
        "[market_status_code_trace] market=%s source=%s code=%s prev=%s ts=%s state=%s",
        market, key[1], code, prev or "-", now.strftime("%H:%M:%S"), _markets[market]["state"],
    )


def _record(kind: str, market: str, now: datetime, **extra) -> None:
    _events.append({"kind": kind, "market": market, "at": now.isoformat(), **extra})
    del _events[:-_EVENTS_MAX]


def _expire(now: datetime) -> None:
    for m in MARKETS:
        st = _markets[m]
        last = st["last_active_at"]
        if st["state"] == _CB and st["stage"] < 3 and last and (now - last).total_seconds() > CB_TTL_SECS:
            _release(m, now, code="", reason="ttl")
        elif st["state"] == _HALT and last and (now - last).total_seconds() > HALT_TTL_SECS:
            logger.warning("[market_halt_164] market=%s transition=ttl", m)
            _release(m, now, code="", reason="ttl", log=False)
        if st["state"] == _RELEASED and st["released_at"] and (
            (now - st["released_at"]).total_seconds() > RELEASE_GRACE_SECS
        ):
            st["state"] = _NORMAL
        sc = _sidecar[m]
        if sc and (now - sc["last_at"]).total_seconds() > SIDECAR_TTL_SECS:
            logger.warning("[market_sidecar] market=%s side=%s transition=ttl", m, sc["side"])
            _record("sidecar_off", m, now, side=sc["side"], reason="ttl")
            _sidecar[m] = None


def _release(market: str, now: datetime, *, code: str, reason: str, log: bool = True) -> None:
    st = _markets[market]
    if log:
        elapsed = int((now - st["since"]).total_seconds()) if st["since"] else -1
        logger.warning(
            "[market_cb_release] market=%s stage=%d code=%s elapsed_secs=%d reason=%s",
            market, st["stage"], code or "-", elapsed, reason,
        )
    _record("release", market, now, code=code, reason=reason, stage=st["stage"])
    st["state"] = _RELEASED
    st["released_at"] = now


def _enter_cb(market: str, code: str, now: datetime) -> None:
    st = _markets[market]
    st["last_active_at"] = now
    st["last_code"] = code
    st["source"] = _source(code)
    if st["state"] == _CB:
        return
    rel = st["released_at"]
    same_event = rel is not None and (now - rel).total_seconds() <= REENTRY_SAME_STAGE_SECS
    if not same_event or st["stage"] == 0:
        st["stage"] += 1
    st["state"] = _CB
    st["since"] = now
    st["released_at"] = None
    logger.warning(
        "[market_cb_active] market=%s stage=%d code=%s source=%s ts=%s",
        market, st["stage"], code, st["source"], now.isoformat(),
    )
    _record("cb_active", market, now, code=code, stage=st["stage"])
    t = now.time()
    if not (LOW_SKIP_START <= t < LOW_SKIP_END) or (t >= _LATE_CB_CUTOFF and st["stage"] < 3):
        logger.warning(
            "[market_cb_unexpected] market=%s stage=%d code=%s time=%s",
            market, st["stage"], code, t.strftime("%H:%M:%S"),
        )


def on_event(event) -> None:
    """`market_operation_monitor.record_market_op_event` 끝에서 부른다(호출부 try 흡수)."""
    market = REP_MARKET.get(getattr(event, "ticker", "") or "")
    if market is None:
        return
    code = (getattr(event, "mkop_cls_code", "") or "").strip()
    if not code or code == "(null)":
        return
    now = getattr(event, "received_at", None)
    if not isinstance(now, datetime):
        now = _now()
    _roll_day(now)
    _expire(now)
    st = _markets[market]

    if code in _CB_ENTER_ST or (_UN_CODES_DRIVE_STATE and code in _CB_ENTER_UN):
        _enter_cb(market, code, now)
    elif code in _CB_RELEASE_ST or (_UN_CODES_DRIVE_STATE and code in _CB_RELEASE_UN):
        st["last_code"] = code
        if st["state"] in (_CB, _HALT) and not (st["state"] == _CB and st["stage"] >= 3):
            if st["state"] == _HALT:
                logger.warning("[market_halt_164] market=%s transition=off code=%s", market, code)
            _release(market, now, code=code, reason="code")
    elif code == _HALT_CODE:
        st["last_active_at"] = now
        st["last_code"] = code
        if st["state"] not in (_CB, _HALT):
            st["state"] = _HALT
            st["since"] = now
            st["released_at"] = None
            logger.warning("[market_halt_164] market=%s transition=on", market)
            _record("halt_164", market, now, code=code)
    elif code in _HALT_RELEASE and st["state"] == _HALT:
        st["last_code"] = code
        logger.warning("[market_halt_164] market=%s transition=off code=%s", market, code)
        _release(market, now, code=code, reason="code", log=False)
    elif code in _SIDECAR_ON:
        side = _SIDECAR_ON[code]
        prev = _sidecar[market]
        _sidecar[market] = {"side": side, "since": prev["since"] if prev else now, "last_at": now}
        if prev is None:
            logger.warning("[market_sidecar] market=%s side=%s transition=on", market, side)
            _record("sidecar_on", market, now, side=side)
    elif code in _SIDECAR_OFF:
        prev = _sidecar[market]
        if prev is not None:
            logger.warning("[market_sidecar] market=%s side=%s transition=off", market, prev["side"])
            _record("sidecar_off", market, now, side=prev["side"], reason="code")
            _sidecar[market] = None
    elif code in _KNOWN_NORMAL or code[:1] in ("F", "P") or code in _CB_ENTER_UN or code in _CB_RELEASE_UN:
        pass
    elif code not in _unknown_logged:
        _unknown_logged.add(code)
        logger.info("[market_status_unknown_code] market=%s code=%s", market, code)

    try:
        _trace_code(market, code, now)
    except Exception:
        logger.debug("[market_status_code_trace] 기록 실패", exc_info=True)


def suppressing_markets(now: datetime | None = None) -> list[str]:
    """LOW 재구독을 멈추게 하는 시장 목록(시간창 무관)."""
    now = now or _now()
    _roll_day(now)
    _expire(now)
    return [m for m in MARKETS if _markets[m]["state"] in _SUPPRESSING]


def is_low_resub_suppressed(now: datetime | None = None) -> bool:
    """어느 시장이든 CB·시장임시정지(해제 유예 포함) ∧ 09:00~15:30 이면 True. never-raise."""
    try:
        now = now or _now()
        if now.tzinfo is not None:
            now = now.astimezone(_KST)
        if not (LOW_SKIP_START <= now.time() < LOW_SKIP_END):
            return False
        return bool(suppressing_markets(now))
    except Exception:
        logger.debug("[market_cb_state] 판정 실패 — False", exc_info=True)
        return False


def get_market_cb_summary(now: datetime | None = None) -> dict:
    """대시보드용 확인 축 — `get_market_op_state_summary()["circuit_breaker"]` 에 합친다."""
    now = now or _now()
    _roll_day(now)
    _expire(now)

    def _iso(v):
        return v.isoformat() if isinstance(v, datetime) else None

    markets = {}
    for m in MARKETS:
        st = _markets[m]
        ttl = None
        if st["state"] == _CB and st["stage"] < 3 and st["last_active_at"]:
            ttl = st["last_active_at"] + timedelta(seconds=CB_TTL_SECS)
        elif st["state"] == _HALT and st["last_active_at"]:
            ttl = st["last_active_at"] + timedelta(seconds=HALT_TTL_SECS)
        markets[m] = {
            "state": st["state"], "stage": st["stage"], "since": _iso(st["since"]),
            "last_code": st["last_code"], "source": st["source"], "ttl_expires_at": _iso(ttl),
        }
    sidecar = {
        m: ({"side": sc["side"], "since": _iso(sc["since"])} if (sc := _sidecar[m]) else None)
        for m in MARKETS
    }
    return {
        "markets": markets,
        "sidecar": sidecar,
        "low_skip_active": is_low_resub_suppressed(now),
        "events_today": list(_events),
    }


async def subscribe_market_status_reps(ws) -> int:
    """메인 세션에 대표 구독 3건(`bypass_limit=False` — tick 슬롯을 밀어내지 않는다).

    재연결 때는 `KisWebSocket._restore_subscriptions_after_reconnect` 가 `_subscriptions`
    전체를 다시 보내므로 따로 할 일이 없다. 각 건 독립 try — 실패는 WARNING 후 다음 건.
    """
    ok = 0
    for tr_id, tr_key in MARKET_STATUS_REPS:
        try:
            await ws.subscribe(tr_id, tr_key, bypass_limit=False)
            ok += 1
            logger.info("[market_status_rep_subscribed] tr_id=%s tr_key=%s", tr_id, tr_key)
        except Exception as exc:
            logger.warning(
                "[market_status_rep_subscribed] 실패 tr_id=%s tr_key=%s err=%s", tr_id, tr_key, exc,
            )
    return ok
