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
#: `[no_feed_provenance_unavailable]` 1회/일 cap (출처 조회 실패 전용).
_last_provenance_error_day = None
#: cycle293 §6-C — `nxt_tradable` 값의 출처가 권위 있는 ticker 집합
#: (그 행 raw 에 KIS `cptt_trad_tr_psbl_yn` 키가 있다).
_provenance_ok: set[str] = set()


def _now_mono() -> float:
    """`time.monotonic` seam — 테스트가 결정론적으로 고정하는 유일한 지점."""
    return time.monotonic()


def reset_state_for_test() -> None:
    """모듈 전역 상태 전부 초기화 (테스트 격리 seam).

    cycle293 — 이 레지스트리는 채널 리졸버의 **유일한 소스**이고 리졸버의 적용
    범위는 `tick_channel_mode` 가 정한다. 그 모드가 테스트 사이에 살아남으면
    다른 사이클의 stale watcher 테스트가 전용 채널 tr_id 를 보게 되므로, 이
    seam 이 모드까지 함께 초기화한다(모드 leaf 는 stdlib 만 보는 가벼운 모듈이라
    의존 방향 제약 G-252-1 에 걸리지 않는다).
    """
    global _no_feed, _known, _loaded_mono, _last_error_day, _provenance_ok
    global _last_provenance_error_day
    _no_feed = set()
    _known = set()
    _loaded_mono = None
    _last_error_day = None
    _last_provenance_error_day = None
    _provenance_ok = set()
    try:
        from src.engine import tick_channel_mode

        tick_channel_mode.reset_state_for_test()
    except Exception:  # pragma: no cover — never-raise
        pass


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
    global _no_feed, _known, _loaded_mono, _last_error_day, _provenance_ok

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

    # cycle293 §6-C — 출처(provenance) 조회는 **독립 실패**한다. no_feed 분류는
    # cycle252 의 churn 차단(회복 가치 0 인 재등록 SEND 억제)을 담당하고, 출처는
    # 채널 리졸버가 그 값을 믿어도 되는지만 정한다. 둘을 한 try 로 묶으면 출처
    # 쿼리 하나가 실패하는 날 churn 차단까지 함께 죽는다 — 더 중요한 기능이
    # 덜 중요한 기능의 실패에 인질이 되면 안 된다.
    #
    # 실패 시 **이전 집합을 유지**한다(cycle252 refresh 실패 관례 승계). 빈 집합은
    # "아무것도 옮기지 않는다" = 오늘과 동일이고, 유지는 "이미 내린 판정을 흔들지
    # 않는다" 다 — 둘 다 안전 방향이지만 유지가 채널 왕복을 만들지 않는다.
    # 함수가 아예 없는 환경(구 DB 모듈·테스트 스텁)도 같은 경로로 흡수되므로
    # `_provenance_ok` 가 빈 채 남아 리졸버는 현행 유지로 fail-open 한다.
    try:
        provenance = await stock_master.get_nxt_provenance_map(requested)
    except Exception:
        logger.debug(
            "%s 출처(provenance) 조회 실패 — 이전 집합 유지(채널 이동 보류)", _MARKER,
            exc_info=True,
        )
        # 🔴 cycle294 적대 검증 F-1(매수축 HIGH) 시정 — 이 실패는 **상관된 실패**다.
        # `_provenance_ok` 가 비면 `scanner._stamp_cohort` 가 무송출 코호트 **전체**
        # 를 미스탬프로 남기고, 미스탬프는 fail-open(매수 허용)이라 5전략의 틱 매수가
        # 그 코호트에 통째로 열린다(§6-D 가 "열림 오류는 종목별로 독립" 이라고 본
        # 전제가 이 경로에서만 깨진다). 그런데 종전에는 `logger.debug` 뿐이라 21:30
        # 리포트(`pattern_by_level` 이 WARNING 이상만 집계)에 한 글자도 안 떴다 —
        # 되돌릴 수 없는 방향의 사고가 **무음**이었다. 행위는 그대로 두고(조회
        # 실패로 매수를 막으면 P0-1 재현 방향) 소리만 키운다.
        _emit_provenance_failed_once_per_day()
    else:
        _provenance_ok = {t for t, ok in provenance.items() if ok}


def _emit_provenance_failed_once_per_day() -> None:
    """`[no_feed_provenance_unavailable]` — 1회/일 WARNING (리포트 진입)."""
    global _last_provenance_error_day
    try:
        from datetime import datetime as _dt

        from src.db._kst import KST

        today = _dt.now(KST).date()
    except Exception:  # pragma: no cover — never-raise
        today = None
    if today is not None and today == _last_provenance_error_day:
        return
    _last_provenance_error_day = today
    logger.warning(
        "[no_feed_provenance_unavailable] 출처 조회 실패 — 무송출 코호트 스탬프 보류. "
        "매수 축 게이트가 그 코호트에 열린 채로 남는다(fail-open). 이전 집합 유지."
    )


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


def is_classified(ticker: str) -> bool:
    """cycle293 — 이 종목이 **분류된 적이 있는가**(레지스트리 적재 여부).

    `is_no_feed()` 는 "모르면 False" 라 **미지**와 **송출 정상**을 같은 값으로
    접는다. 채널 리졸버는 그 둘을 구별해야 한다 — 미지는 판정 불가(INV-4: 보유
    종목이면 WARNING 으로 사람에게 올린다)이고, 송출 정상은 판정 성공(현행 유지)
    이다. cycle252 의 churn 차단은 그 구별이 필요 없었으므로 이 함수는 리졸버
    전용이고 `is_no_feed` 의 극성은 **건드리지 않는다**.
    """
    return ticker in _known


def is_provenance_ok(ticker: str) -> bool:
    """cycle293 §6-C — 이 종목의 `nxt_tradable` 값이 **권위 있는 출처**에서 왔는가.

    False = "모른다"(조회 전·DB 미존재·KRX 도장 상태) ⇒ 채널 리졸버는 그 종목을
    옮기지 않는다. 모르면 움직이지 않는다 — `is_no_feed` 의 "모르면 막지 않는다"
    와 같은 방향의 fail-open 이다.
    """
    return ticker in _provenance_ok


def provenance_snapshot() -> frozenset[str]:
    """출처 확인 집합 (호출자가 내부 집합을 변조 못 하도록 frozenset)."""
    return frozenset(_provenance_ok)


def snapshot() -> frozenset[str]:
    """현재 no_feed 집합 (호출자가 내부 집합을 변조 못 하도록 frozenset)."""
    return frozenset(_no_feed)
