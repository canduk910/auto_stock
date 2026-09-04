"""cycle252 — 무송출(no_feed) 종목 레지스트리.

`stock_master.nxt_tradable=False`(KRX 단독, NXT 거래대상 아님) 종목은 통합 채널
`H0UNCNT0` 로 SUBSCRIBE → `SUBSCRIBE SUCCESS` ACK 까지 정상이지만 체결 프레임이
하루 1건도 오지 않는다(포렌식 `_workspace/forensics/stale_candidates_0904.md`
①·②-5·③(S7) — 09-01~09-04 나흘 × ~200종목, 예외 0. 유동주 포함 = 침묵이 아니라
채널 결함, 확신도 ≈90%). K stale watcher(`stale_watcher_core.py`)가 그 종목들을
회복 가치 0 인 채로 하루 ~134회 재등록하는 churn 을 이 레지스트리가 "그 종목이
어느 것인가"를 답해 끊는다(§2 §3 정본 = `spec_cycle252_no_feed_churn.md`).

설계 뼈대 = fail-open — 집합이 비면(부팅 직후 미적재 / DB 실패) 호출자는 현행
byte 동일로 돌아간다(§1 D3). `None`(마스터 부재)도 no_feed 가 **아니다** — 모르면
막지 않는다.

의존 방향 (AST G-252-1 봉인): stdlib · `src.db.stock_master`(lazy, 함수 안) ·
logging 만. scheduler/scanner/realtime/registry/stale_* import 금지 —
`stale_watcher_core` 가 이 모듈을 모듈-레벨 정적 import 하므로 역방향 순환을
막아야 한다.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Iterable

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 — caplog 호환

_MARKER = "[no_feed_registry_refresh_failed]"

_DEFAULT_TTL_SECS = 600.0

# ── 모듈 전역 상태 ──────────────────────────────────────────────────────────
_no_feed: set[str] = set()
_known: set[str] = set()
_loaded_mono: float | None = None
_last_error_day: date | None = None


def _now_mono() -> float:
    """`time.monotonic` seam — 테스트가 결정론적으로 고정하는 유일한 지점."""
    return time.monotonic()


def reset_state_for_test() -> None:
    """모듈 전역 상태 전부 초기화 (테스트 격리 seam)."""
    global _no_feed, _known, _loaded_mono, _last_error_day
    _no_feed = set()
    _known = set()
    _loaded_mono = None
    _last_error_day = None


async def ensure_fresh(tickers: Iterable[str], *, ttl_secs: float = _DEFAULT_TTL_SECS) -> None:
    """`tickers` 가 신선하게 분류돼 있는지 보장한다 — 필요 시 DB 1회 조회.

    재조회 트리거(OR):
      - 첫 호출(`_loaded_mono is None`)
      - TTL 경과(`>=`, 경계 포함 — R4b)
      - 미지 ticker 유입(`tickers - _known`)

    재조회는 항상 **`sorted(tickers)` 전체**로 수행한다(부분 조회는 `_known` 을
    쪼개 다음 사이클을 또 미지로 만든다 — R3).

    조회 실패는 이전 집합을 유지하고 `_loaded_mono` 를 갱신하지 않는다(다음
    호출에서 즉시 재시도) + WARNING 1회/일(날짜 키 자기 리셋).
    """
    global _no_feed, _known, _loaded_mono, _last_error_day

    ticker_set = set(tickers)
    if not ticker_set:
        return

    now = _now_mono()
    stale = _loaded_mono is None or (now - _loaded_mono) >= ttl_secs
    unknown = bool(ticker_set - _known)

    if not stale and not unknown:
        return

    try:
        import src.db.stock_master as stock_master  # lazy — hot path import 비용 + patch seam

        requested = sorted(ticker_set)
        result = await stock_master.get_nxt_tradable_map(requested)
    except Exception:
        _emit_refresh_failed_once_per_day()
        return

    _no_feed = {t for t, v in result.items() if v is False}
    _known = set(result)
    _loaded_mono = now


def _emit_refresh_failed_once_per_day() -> None:
    global _last_error_day
    try:
        from src.db._kst import KST
        from datetime import datetime as _dt

        today = _dt.now(KST).date()
    except Exception:
        today = None

    if today is not None and today == _last_error_day:
        return
    _last_error_day = today
    logger.warning(
        "%s no_feed 종목 분류 조회 실패 — 이전 집합 유지, 다음 사이클 재시도",
        _MARKER,
    )


def is_no_feed(ticker: str) -> bool:
    """무송출(no_feed) 종목인지 판정. 모르면(마스터 부재) False — 모르면 막지 않는다."""
    return ticker in _no_feed


def snapshot() -> frozenset[str]:
    """현재 no_feed 집합 (호출자가 내부 집합을 변조 못 하도록 frozenset)."""
    return frozenset(_no_feed)
