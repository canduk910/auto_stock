"""세션 침묵 판정 섀도 관측 leaf (cycle470 — 사용자 지시 2026-10-16 「분석약점 찾아보자」).

`stale_session_recovery.detect_silent_inactive_sessions` 의 두 약점을 **행위 변경 없이** 잰다.
근거 = `_workspace/analysis/2026-10-15_silent_skip_1240.md` §3(4) 표 A·B.

- **B — REST 스탬프 섞임**: 판정이 읽는 `scanner.ticker_last_tick` 은 WS 프레임과 REST 폴(스윙
  조회)이 함께 찍는다. 그래서 WS 가 죽어도 REST 로 읽히는 종목이 많은 세션은 신선해 보인다.
  WS 체결 프레임만 센 신선도(`tick_volume.get_last_ws_frame_at`)로 같은 판정을 한 번 더 해
  결과가 갈리는 순간을 남긴다 → `[silent_inactive_ws_shadow]`.
- **A — 시장 침묵의 반증**: 「판정 가능 세션 전부 침묵」 이면 시장 침묵으로 보고 재연결을 기각한다.
  같은 계정·서버 장애로 시세만 한꺼번에 끊긴 경우도 똑같이 기각된다. 기각이 이어지는 동안
  대표 종목 KRX 누적거래량을 REST 로 읽어 **연속으로 늘어나면**(= 시장은 거래 중) 반증 1줄을
  남긴다 → `[silent_inactive_market_wide_counter_evidence]`.

관측 전용 — 반환값 없음, 판정·cap·first_seen 무접촉, never-raise. REST 조회는 기각 에피소드
안에서만, `PROBE_INTERVAL_SECS` 간격, 동시에 하나.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Iterable

from src.engine.daily_emit_cap import KstDailyEmitCap

logger = logging.getLogger("src.engine.scheduler")  # 판정 모듈과 같은 접두(system_logs grep 사슬)

#: 반증용 대표 종목(코스피 삼성전자, KRX `J`).
REP_TICKER = "005930"
#: 기각 에피소드 안 REST 조회 최소 간격.
PROBE_INTERVAL_SECS = 110.0
#: 연속 증가가 이만큼 이어지면 반증으로 본다(15:30 종가 한 번 튀는 것을 거르려고 2).
COUNTER_MIN_RISES = 2

_cap: KstDailyEmitCap[str] = KstDailyEmitCap()
#: asyncio 는 Task 를 약한 참조로만 든다 — 끝날 때까지 여기서 붙든다(funnel_capture 등과 같은 규약).
_BG_TASKS: set = set()
_probe: dict[str, Any] = {"since": None, "reads": [], "inflight": False, "last_at": None, "warned": False}


def reset_for_test() -> None:
    global _cap
    _cap = KstDailyEmitCap()
    _probe.update(since=None, reads=[], inflight=False, last_at=None, warned=False)


# ── B ────────────────────────────────────────────────────────────────────────
def ws_fresh_count(tickers: Iterable[str], now: datetime, threshold: timedelta) -> int:
    from src.engine import tick_volume
    n = 0
    for t in tickers:
        at = tick_volume.get_last_ws_frame_at(t)
        if at is not None and (now - at) <= threshold:
            n += 1
    return n


def observe_ws_shadow(
    now: datetime,
    rows: list[tuple[str, int, int, int, bool]],
    *,
    market_wide_now: bool,
    ratio_threshold: float,
    min_subscribed: int,
    min_eligible: int,
) -> None:
    """rows = (label, subscribed, fresh_all, fresh_ws, suspect_now). 갈리는 것만 남긴다. never-raise."""
    try:
        eligible = [r for r in rows if r[1] >= min_subscribed]
        suspect_ws = {
            r[0]: (r[1] >= min_subscribed and (r[3] / r[1] if r[1] else 0.0) < ratio_threshold)
            for r in rows
        }
        for label, sub, fresh_all, fresh_ws, suspect_now in rows:
            if suspect_ws[label] == suspect_now:
                continue
            key = f"s|{label}|{int(suspect_now)}{int(suspect_ws[label])}"
            if _cap.should_emit(key, now=now):
                logger.warning(
                    "[silent_inactive_ws_shadow] session=%s sub=%d fresh_all=%d fresh_ws=%d "
                    "suspect_now=%d suspect_ws=%d market_wide_now=%d",
                    label, sub, fresh_all, fresh_ws, int(suspect_now), int(suspect_ws[label]),
                    int(market_wide_now),
                )
                _cap.mark_emitted(key, now=now)
        mw_ws = len(eligible) >= min_eligible and all(suspect_ws[r[0]] for r in eligible)
        if mw_ws != market_wide_now:
            key = f"m|{int(market_wide_now)}{int(mw_ws)}"
            if _cap.should_emit(key, now=now):
                logger.warning(
                    "[silent_inactive_ws_shadow] scope=market_wide market_wide_now=%d market_wide_ws=%d "
                    "eligible=%d sessions=%s",
                    int(market_wide_now), int(mw_ws), len(eligible),
                    ",".join(f"{r[0]}:{r[2]}/{r[3]}/{r[1]}" for r in rows),
                )
                _cap.mark_emitted(key, now=now)
    except Exception:
        logger.debug("[silent_inactive_ws_shadow] 관측 실패", exc_info=True)


# ── A ────────────────────────────────────────────────────────────────────────
async def _probe_acml_vol(ticker: str) -> int | None:
    """seam — 테스트는 conftest 가 None 으로 중립화한다."""
    from src.api.quotation import inquire_acml_vol
    return await inquire_acml_vol(ticker, market="J")


def note_market_wide(now: datetime, episode_since: datetime | None) -> None:
    """기각 사이클마다 부른다. 간격이 되면 REST 1회를 띄운다(await 없음). never-raise."""
    try:
        if _probe["since"] != episode_since:
            _probe.update(since=episode_since, reads=[], inflight=False, last_at=None, warned=False)
        if _probe["inflight"] or _probe["warned"]:
            return
        last = _probe["last_at"]
        if last is not None and (now - last).total_seconds() < PROBE_INTERVAL_SECS:
            return
        loop = asyncio.get_running_loop()
        _probe.update(inflight=True, last_at=now)
        task = loop.create_task(_run_probe(now, episode_since))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except Exception:
        _probe["inflight"] = False
        logger.debug("[silent_inactive_market_wide_counter_evidence] 조회 예약 실패", exc_info=True)


def note_market_wide_closed() -> None:
    _probe.update(since=None, reads=[], inflight=False, last_at=None, warned=False)


async def _run_probe(now: datetime, episode_since: datetime | None) -> None:
    try:
        vol = await asyncio.wait_for(_probe_acml_vol(REP_TICKER), timeout=5.0)
    except asyncio.CancelledError:
        raise
    except Exception:
        vol = None
    try:
        if _probe["since"] != episode_since:   # 그 사이 에피소드가 끝났다
            return
        if not isinstance(vol, int) or isinstance(vol, bool):
            return
        reads = _probe["reads"]
        reads.append((now, vol))
        del reads[:-(COUNTER_MIN_RISES + 1)]
        rising = len(reads) == COUNTER_MIN_RISES + 1 and all(
            reads[i + 1][1] > reads[i][1] for i in range(COUNTER_MIN_RISES)
        )
        if rising and not _probe["warned"]:
            logger.warning(
                "[silent_inactive_market_wide_counter_evidence] ticker=%s vols=%s at=%s since=%s "
                "— 전 세션 침묵으로 기각 중인데 REST 누적거래량이 늘고 있다(시세만 끊겼을 가능성)",
                REP_TICKER, ",".join(str(v) for _, v in reads),
                ",".join(t.strftime("%H:%M:%S") for t, _ in reads),
                episode_since.strftime("%H:%M:%S") if episode_since else "-",
            )
            _probe["warned"] = True
    except Exception:
        logger.debug("[silent_inactive_market_wide_counter_evidence] 판정 실패", exc_info=True)
    finally:
        if _probe["since"] == episode_since:
            _probe["inflight"] = False
