"""사이클 149 (2026-06-16) — 종목별 장운영정보 (H0UNMKO0) state monitor.

VI 활성 / 거래정지 / 종목상태 이상 ticker 영역 추적 + stale 회피 hook 제공.

domain-expert 자문 산출물:
    `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`

핵심 책임 (의제 5 자문 채택):
1. `_vi_active_tickers` — VI 활성 ticker set (정적/동적/시간외 통합)
2. `_halt_active_tickers` — 거래정지 + 종목상태 이상 ticker set
3. `_market_op_last_event` — ticker → 마지막 MarketOpEvent dict (진단 + UI 응답용)

사이클 88 G-REJECT-3 영구 영속 답습:
- 4 dict (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`)
- 사이클 135 `_subscribed_at` 추가 → 5 dict
- **사이클 149 추가 3 dict → 8 dict 분리 영속** (`_vi_active_tickers` + `_halt_active_tickers` + `_market_op_last_event`)
- **cycle368 추가 2 dict → 10 dict 분리 영속** (`_vi_last_active_at` — VI TTL 수명 전용 ·
  `_halt_last_active_at` — 거래정지 TTL 수명 전용. 둘은 서로 **완전 독립**이라 VI 타이머가
  만료돼도 거래정지 타이머는 그대로다. "멤버십" 과 "마지막 활성 시각" 을 한 자료구조에
  합치지 않는다)
- 통합 단일 dict 영구 차단 (책임 분리 + AST 영구 가드)

매매 안전성 무영향 (사이클 38 명문화 영속):
- stale 회피 = stale 판정 *지연*만 (`check_and_resubscribe_stale` 의 `_is_within_grace` 패턴 답습)
- `risk.on_tick` / `order_engine` / `auth` 변경 0
- 메인 WebSocket 단일 (보조 세션 변경 0)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from src.api.market_operation import MarketOpEvent
from src.engine.daily_emit_cap import DailyEmitCap

logger = logging.getLogger(__name__)


# 사이클 149 신규 3 dict (사이클 88 G-REJECT-3 영속 답습 = 통합 단일 dict 영구 차단)
_vi_active_tickers: set[str] = set()
_halt_active_tickers: set[str] = set()
_market_op_last_event: dict[str, MarketOpEvent] = {}

# cycle368 — VI 수명(TTL) 신규 dict. `_vi_active_tickers` 와 분리 보관한다(같은 dict 에
# 합치면 「멤버십」과 「마지막 활성 시각」이 한 자료구조에 뒤섞여 사이클 149 의 분리
# 영속 원칙을 어긴다). ticker → 마지막 활성(Y) 프레임(또는 REST 시드) 시각.
_vi_last_active_at: dict[str, datetime] = {}

#: VI 활성 수명 — 마지막 활성 프레임 뒤 이 초가 지나면 해제 프레임 없이도 자동 해제한다
#: (2026-09-25 사용자 결정, cycle368). 해제 프레임이 항상 온다는 보장이 없어(cycle359
#: 메모 §3.1 — 3일 실측 17건 중 `Y` 는 1건뿐이고 그 뒤 `N` 이 왔지만, 「항상 온다」는
#: 증명되지 않았다) 그 결함(가짜 VI 가 하루 종일 안 풀림)과 같은 모양의 잔여 위험을 없앤다.
VI_ACTIVE_TTL_SECONDS: float = 600.0

# cycle368 F2(적대적 검토 뒤 메인 세션 결정, 사용자 승인 범위 안) — 거래정지도 VI 와 같은
# 수명 원칙을 받는다. `_vi_last_active_at` 와 **별개 dict** 로 둔다(VI 타이머와 거래정지
# 타이머는 독립이다 — L5a/L5b). ticker → 마지막 활성(trht_yn=="Y" 또는 종목상태 58) 프레임 시각.
_halt_last_active_at: dict[str, datetime] = {}

#: 거래정지 활성 수명 — VI 와 동일 상수값(600초). 근거 = 600초 뒤의 행위가 cycle368 이전과
#: 같다(라이브 프레임으로 정지가 실제 발화한 적이 없었다) — 그래서 더 안전한 방향으로만
#: 움직이고, 진짜 정지 종목은 상한 걸린 stale 재구독 SEND 를 다시 받을 뿐이다.
HALT_ACTIVE_TTL_SECONDS: float = 600.0

# 사이클 186 — 서킷브레이커 휴리스틱 상수 + 1회/일 cap
_CB_REASON_KEYWORDS = ("서킷", "매매거래중단", "circuit")
_CB_HALT_RATIO: float = 0.8
_CB_MIN_HALTED: int = 5
_cb_suspected_logged_today: DailyEmitCap = DailyEmitCap()


def _now() -> datetime:
    """VI TTL 판정용 시계 — UTC aware(freezegun 이 전역 `datetime` 을 얼려 테스트를 얼린다).

    `MarketOpEvent.received_at` 은 KST 로 스탬프되지만 aware datetime 뺄셈은 tzinfo 와
    무관하게 절대 경과를 정확히 계산하므로 굳이 KST_TZ 를 이 leaf 로 끌어올 필요가 없다.
    """
    return datetime.now(timezone.utc)


def _expire_stale_vi() -> None:
    """VI TTL 지연 평가(cycle368) — `record_market_op_event` 첫머리 + 읽기 함수 4곳(아래)
    진입 시 먼저 부른다.

    마지막 활성(Y) 프레임 뒤 `VI_ACTIVE_TTL_SECONDS` 가 지난 ticker 를 해제 프레임 없이도
    풀어 준다. 백그라운드 task 를 두지 않고 매 읽기 호출이 스스로 sweep 한다 — 여러 읽기
    함수가 연달아 불려도 최초 1 회만 로그가 남는다(만료 시 즉시 discard).
    """
    if not _vi_active_tickers:
        return
    now = _now()
    expired: list[str] = []
    for ticker in list(_vi_active_tickers):
        last_active = _vi_last_active_at.get(ticker)
        if last_active is None:
            # 방어적 분기 — 활성 집합에 있는데 시각이 없는 종목은 지금(발견 시각)을
            # 마지막 활성으로 찍고 그로부터 TTL 뒤 해제한다. 시각 없음을 영구 활성으로
            # 두면 그 종목이 21:30 정산까지 재구독 안전망 밖에 남는다 — cycle368 이
            # 없애려는 결함과 같은 모양이라 무기한 유지 방향은 쓰지 않는다.
            _vi_last_active_at[ticker] = now
            continue
        if (now - last_active).total_seconds() >= VI_ACTIVE_TTL_SECONDS:
            expired.append(ticker)
    for ticker in expired:
        _vi_active_tickers.discard(ticker)
        _vi_last_active_at.pop(ticker, None)
        logger.info("[market_op_vi_release] ticker=%s reason=ttl", ticker)


def _expire_stale_halt() -> None:
    """거래정지 TTL 지연 평가(cycle368 F2) — `_expire_stale_vi()` 와 대칭이고
    `record_market_op_event` 첫머리 + 읽기 함수 5곳(아래)에서 부른다.

    마지막 활성(정지) 프레임 뒤 `HALT_ACTIVE_TTL_SECONDS` 가 지난 ticker 를 해제 프레임 없이도
    풀어 준다. VI 와 **완전히 독립**된 dict/집합을 본다 — 한쪽 sweep 이 다른 쪽을 지우지 않는다.
    """
    if not _halt_active_tickers:
        return
    now = _now()
    expired: list[str] = []
    for ticker in list(_halt_active_tickers):
        last_active = _halt_last_active_at.get(ticker)
        if last_active is None:
            # 방어적 분기 — VI 와 같은 규칙: 시각 없이 활성 집합에 있는 종목은 지금
            # (발견 시각)을 마지막 활성으로 찍고 그로부터 TTL 뒤 해제한다(무기한 유지 금지).
            _halt_last_active_at[ticker] = now
            continue
        if (now - last_active).total_seconds() >= HALT_ACTIVE_TTL_SECONDS:
            expired.append(ticker)
    for ticker in expired:
        _halt_active_tickers.discard(ticker)
        _halt_last_active_at.pop(ticker, None)
        logger.info("[market_op_halt_release] ticker=%s reason=ttl", ticker)


def record_market_op_event(event: MarketOpEvent) -> None:
    """H0UNMKO0 단일 이벤트 수신 시 state 갱신.

    의제 1 (자문 채택) — truthy 매핑:
    - VI/거래정지/종목상태 활성 → 해당 set add
    - 비활성 ("0"/""/None) → 해당 set discard
    VI/거래정지 판정은 `_is_code_active`/`is_iscd_stat_blocking` 인라인으로 처리
    (is_event_blocking 미사용).

    cycle368 F3 — 이 함수 첫머리에서 VI·거래정지 TTL 만료를 먼저 sweep 한다. 순서가
    계약이다: sweep 이 기록 **뒤**에 있으면 만료된 에피소드 위에 도착한 해제 프레임이
    "프레임 해제"로 잘못 적히고(TTL 해제 로그 누락), 새 활성 프레임은 "갱신"으로 뭉개져
    새 에피소드 로그가 사라진다(R1~R3).
    """
    ticker = event.ticker
    if not ticker:
        return

    _expire_stale_vi()
    _expire_stale_halt()

    # 마지막 이벤트 보존 (UI 진단 + 디버깅용)
    _market_op_last_event[ticker] = event

    # VI 활성/해제 (정적 + 동적 + 시간외 통합)
    from src.api.market_operation import _is_code_active, is_iscd_stat_blocking

    vi_active = _is_code_active(event.vi_cls_code) or _is_code_active(event.ovtm_vi_cls_code)
    if vi_active:
        # cycle368 — 매 활성 프레임이 수명을 갱신한다(마지막 Y 기준 600초).
        _vi_last_active_at[ticker] = _now()
        if ticker not in _vi_active_tickers:
            _vi_active_tickers.add(ticker)
            logger.info(
                "[market_op_vi_active] ticker=%s vi_code=%s ovtm_vi_code=%s",
                ticker, event.vi_cls_code, event.ovtm_vi_cls_code,
            )
    else:
        # 명시 해제(N) 프레임 — TTL 을 기다리지 않고 즉시 해제한다(reason 없음 = 정상
        # 프레임 해제, TTL 해제와 로그 문구로 구분된다).
        _vi_last_active_at.pop(ticker, None)
        if ticker in _vi_active_tickers:
            _vi_active_tickers.discard(ticker)
            logger.info("[market_op_vi_release] ticker=%s", ticker)

    # 거래정지 — cycle368 사용자 결정: 종목상태(ISCD_STAT_CLS_CODE) 58 하나만 정지로 본다
    # (51/55/57/59/00 은 정지 아님). TRHT_YN=="Y" 는 종목상태와 무관하게 정지.
    halt_active = (
        (event.trht_yn and event.trht_yn.upper() == "Y")
        or is_iscd_stat_blocking(event.iscd_stat_cls_code)
    )
    if halt_active:
        # cycle368 F2 — 매 활성 프레임이 수명을 갱신한다(마지막 정지 프레임 기준 600초).
        _halt_last_active_at[ticker] = _now()
        if ticker not in _halt_active_tickers:
            _halt_active_tickers.add(ticker)
            logger.info(
                "[market_op_halt_active] ticker=%s trht_yn=%s iscd_stat=%s reason=%s",
                ticker, event.trht_yn, event.iscd_stat_cls_code,
                event.tr_susp_reas_cntt[:50],
            )
    else:
        # 명시 해제 프레임 — TTL 을 기다리지 않고 즉시 해제한다(reason 없음 = 정상 프레임
        # 해제, TTL 해제와 로그 문구로 구분된다).
        _halt_last_active_at.pop(ticker, None)
        if ticker in _halt_active_tickers:
            _halt_active_tickers.discard(ticker)
            logger.info("[market_op_halt_release] ticker=%s", ticker)

    # 사이클 186 — 서킷브레이커 휴리스틱 체크 + 1회/일 cap 로그
    cb_state = get_circuit_breaker_state()
    if cb_state["suspected"] and _cb_suspected_logged_today.should_emit("cb"):
        _cb_suspected_logged_today.mark_emitted("cb")
        logger.info(
            "[market_op_cb_suspected] mkop_code=%s halted=%d/%d reason=%s",
            cb_state["representative_mkop_cls_code"],
            cb_state["halted"],
            cb_state["observed"],
            cb_state["reasons"],
        )


def is_ticker_stale_excluded(ticker: str) -> bool:
    """stale 판정 회피 hook (`check_and_resubscribe_stale` 영역).

    VI 활성 ∪ 거래정지 활성 ticker = stale 판정 *지연* 의무.
    True 반환 시 stale 종목 set 에서 제외 → 강제 재구독 발화 차단.

    cycle368 — 먼저 `_expire_stale_vi()`/`_expire_stale_halt()` 로 VI·거래정지 TTL 만료를
    sweep 한다(해제 프레임이 오지 않아도 마지막 활성 뒤 600초가 지나면 이 판정에서 빠진다).
    """
    _expire_stale_vi()
    _expire_stale_halt()
    return ticker in _vi_active_tickers or ticker in _halt_active_tickers


def get_market_op_active_tickers() -> set[str]:
    """VI ∪ 거래정지 합집합 (외부 호출자용 read-only view).

    ⚠️ **현재 프로덕션 소비처 0건**(2026-09-14 전수 확인 — 호출은 단위 테스트뿐).
    종전 docstring 이 적었던 "`_subscribe_market_operation_tickers` 영역 delta 계산 +
    UI 진단 응답" 은 두 절 다 사실이 아니다: 그 훅의 델타는 이 함수가 아니라
    `scheduler._market_op_subs` 로 재고(`market_op_subscribe.py` 본문
    `set(scheduler._market_op_subs) - target_set`), 후보 VI 배치 자체가 cycle221 F2 로
    삭제됐다. UI 는 `get_market_op_state_summary()` 를 쓴다.
    read-only view 라 무해해서 남긴다 — 지우는 것은 "비활성화 시 심층 검증 의무"
    대상이라 별건이다.

    cycle368 — 반환 전 `_expire_stale_vi()`/`_expire_stale_halt()` 로 만료된 VI·거래정지를
    sweep 한다.
    """
    _expire_stale_vi()
    _expire_stale_halt()
    return _vi_active_tickers | _halt_active_tickers


def get_vi_active_tickers() -> set[str]:
    """VI 활성 ticker set 복사본 (read-only view). cycle368 — 반환 전 TTL sweep."""
    _expire_stale_vi()
    return set(_vi_active_tickers)


def get_halt_active_tickers() -> set[str]:
    """거래정지 활성 ticker set 복사본 (read-only view). cycle368 F2 — 반환 전 TTL sweep."""
    _expire_stale_halt()
    return set(_halt_active_tickers)


def get_last_event(ticker: str) -> Optional[MarketOpEvent]:
    """ticker 마지막 이벤트 (UI 진단 + 디버깅용)."""
    return _market_op_last_event.get(ticker)


def seed_vi_active_from_rest(tickers: Iterable[str]) -> None:
    """의제 4 (자문 채택) — 부팅 시점 REST 폴백 시드.

    `inquire_vi_status_today()` 반환 set 으로 `_vi_active_tickers` 사전 등록.
    WebSocket 구독 시점 *이전* VI 활성 종목 stale 회피 보장.

    cycle368 — 시드도 수명을 받는다(시드 시각 = 마지막 활성 시각). 시드는 "오늘 VI 가
    있었던" 종목 목록이라 장중 재기동이면 이미 풀린 종목까지 들어올 수 있고, 수명이
    없으면 그 보유 종목이 21:30 정산까지 재구독 안전망 밖에 남는다(이번 결함과 같은
    모양).
    """
    now = _now()
    for ticker in tickers:
        if ticker:
            _vi_active_tickers.add(ticker)
            _vi_last_active_at[ticker] = now
    if tickers:
        logger.info(
            "[market_op_vi_seed] count=%d sample=%s",
            len(_vi_active_tickers),
            sorted(_vi_active_tickers)[:5],
        )


def reset_market_op_state() -> None:
    """일일 상태 초기화 (`_reset_daily_state` 동행 clear).

    사이클 88 G-REJECT 영속 답습 = 모든 dict 일일 0 초기화 의무.
    """
    _vi_active_tickers.clear()
    _halt_active_tickers.clear()
    _market_op_last_event.clear()
    _vi_last_active_at.clear()  # cycle368
    _halt_last_active_at.clear()  # cycle368 F2
    _cb_suspected_logged_today.reset_daily()  # 사이클 186


def get_circuit_breaker_state() -> dict:
    """서킷브레이커 휴리스틱 state snapshot (사이클 186).

    (R) 거래정지 종목의 tr_susp_reas_cntt 에 키워드 포함 OR
    (W) 거래정지 비율 ≥ _CB_HALT_RATIO + 절대 수 ≥ _CB_MIN_HALTED.

    cycle368 F2 — 계산 전 `_expire_stale_halt()` 로 만료된 거래정지를 sweep 한다. 해제
    프레임이 안 온 정지가 CB 의심을 하루 종일 유지하면 안 된다(L7).
    """
    _expire_stale_halt()
    halted = len(_halt_active_tickers)
    observed = len(_market_op_last_event)
    halt_ratio = halted / max(1, observed)

    # (R) keyword path
    keyword_match = False
    for ticker in _halt_active_tickers:
        event = _market_op_last_event.get(ticker)
        if event and event.tr_susp_reas_cntt:
            for kw in _CB_REASON_KEYWORDS:
                if kw in event.tr_susp_reas_cntt:
                    keyword_match = True
                    break
        if keyword_match:
            break

    # (W) ratio path
    ratio_triggered = halted >= _CB_MIN_HALTED and halt_ratio >= _CB_HALT_RATIO

    suspected = keyword_match or ratio_triggered

    reasons: list[str] = []
    if keyword_match:
        reasons.append("거래정지 사유 키워드 포함 (서킷/매매거래중단)")
    if ratio_triggered:
        reasons.append(
            f"전 시장 거래정지 {halted}/{observed} ({int(halt_ratio * 100)}%)"
        )

    # representative: 005930 last event
    rep_event = _market_op_last_event.get("005930")
    representative_mkop_cls_code = rep_event.mkop_cls_code if rep_event else ""

    # halt_reasons_sample: distinct non-empty tr_susp_reas_cntt (최대 5)
    seen: set[str] = set()
    sample: list[str] = []
    for ticker in _halt_active_tickers:
        event = _market_op_last_event.get(ticker)
        if event and event.tr_susp_reas_cntt:
            reason = event.tr_susp_reas_cntt
            if reason not in seen:
                seen.add(reason)
                sample.append(reason)
                if len(sample) >= 5:
                    break

    return {
        "suspected": suspected,
        "reasons": reasons,
        "halt_ratio": halt_ratio,
        "halted": halted,
        "observed": observed,
        "representative_mkop_cls_code": representative_mkop_cls_code,
        "halt_reasons_sample": sample,
    }


#: 요약 `iscd_stat_active_count` 표시 집합(cycle368 — cycle359 조사 메모 §6 권고를 메인 세션이 채택) —
#: 시장경고/관리/정지/단기과열 51~54·58·59. 55(신용가능)·57(증거금100%)·00(그 외)·
#: 빈값은 정상 상태라 세지 않는다(구 `_is_code_active` 는 이 값들까지 「이상」으로 셌다).
_ISCD_STAT_DISPLAY_CODES: frozenset[str] = frozenset({"51", "52", "53", "54", "58", "59"})


def get_market_op_state_summary() -> dict:
    """진단/UI 응답용 state snapshot (사이클 186 확장 = circuit_breaker + iscd_stat_active_count).

    cycle368 — `_expire_stale_vi()`/`_expire_stale_halt()`(F2) 로 만료 VI·거래정지를 먼저
    sweep 하고, `iscd_stat_active_count` 는 표시 집합(`_ISCD_STAT_DISPLAY_CODES`) 멤버십으로
    센다(55/57/00 제외).
    """
    _expire_stale_vi()
    _expire_stale_halt()

    iscd_stat_active_count = sum(
        1 for event in _market_op_last_event.values()
        if event.iscd_stat_cls_code in _ISCD_STAT_DISPLAY_CODES
    )
    return {
        "vi_active_count": len(_vi_active_tickers),
        "halt_active_count": len(_halt_active_tickers),
        "last_event_count": len(_market_op_last_event),
        "vi_active_sample": sorted(_vi_active_tickers)[:10],
        "halt_active_sample": sorted(_halt_active_tickers)[:10],
        "circuit_breaker": get_circuit_breaker_state(),
        "iscd_stat_active_count": iscd_stat_active_count,
    }
