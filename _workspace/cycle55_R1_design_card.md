# 사이클 55 R-1 — SellRejectionTracker 설계 카드

> **작성**: refactor-expert (2026-06-03)
> **승인 대기**: team-leader → tdd-engineer Red 발주
> **선행 자문**: domain-expert (Q1~Q5 5 RECOMMEND 채택)
> **사용자 확정**: 자문 전부 적용 (Q1 2단계 TTL / Q2 30초+NXT 익일 전환 / Q3 reconciliation / Q4 부분 캡슐화 / Q5 history)
> **선례 답습**: 사이클 48 `src/engine/stale_tracker.py::StaleTrackerState` (82L)
> **위험 등급**: HIGH (매매 hot path, 4 분류 분기 통합, CLAUDE.md 절대 규칙 다수 보호 영역)

---

## 1. SellRejectionTracker 인터페이스 명세

### 1.1 모듈 위치 & 라인 예상
- **경로**: `src/engine/sell_rejection.py` (신규)
- **예상 라인**: 130~170L (선례 stale_tracker 82L + RejectionResult/EventRecord/dual-TTL 분기 추가분)

### 1.2 데이터클래스 구조

```python
"""Sell 거부 4 분류 통합 정책 객체 (사이클 55 R-1, 2026-06-03).

사이클 52 (B-1) 단일 책임 진입 차단 → 사이클 55 (R-1) 4 분류 통합:
- is_market_closed_rejection (KRX 메인 5분 TTL / NXT 시간대 다음 09:00 TTL)
- is_market_order_disallowed (30초 TTL + NXT 폴백 실패 시 익일 청산 전환)
- is_insufficient_quantity (기록만 + reconciliation 트리거, 차단 X)
- (정상/기타 거부 — tracker 통과)

호환 layer:
- OrderEngine 의 3 property (_market_closed_blocked / _market_closed_blocked_logged_today
  / _nxt_downgrade_logged_today*) 가 본 데이터클래스 필드 직접 노출.
  *사이클 54 _nxt_downgrade_logged_today 는 R-1 범위 밖 — 사이클 56 emit cap 통합에서 흡수.
- 사이클 52 회귀 가드 8 시나리오 호환 보장.

안전 가드:
- reset_daily() 가 _blocked_until / _blocked_reason / _logged_today / _history 일괄 clear.
- record_rejection() 은 항상 history 적재 (V-1 사이클 56+ 알람 hook 사전 준비).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Literal

_KST_TZ = timezone(timedelta(hours=9))

RejectionReason = Literal[
    "market_closed",
    "market_order_disallowed",
    "insufficient_quantity",
]

@dataclass(frozen=True)
class RejectionEvent:
    """거부 이벤트 1건 (V-1 알람 hook 사전 준비, 사이클 56+)."""
    reason: RejectionReason
    msg_cd: str
    msg1: str
    occurred_at: datetime

@dataclass(frozen=True)
class RejectionResult:
    """register_market_order_disallowed() 응답.

    Attributes:
        next_day_clear_required: NXT 폴백 실패 → 익일 청산 전환 의무.
            execute_sell 호출자가 _pending_next_day_clear 에 등록.
        block_ttl_expires_at: 30 초 TTL 만료 시각 (재시도 진입 게이트).
    """
    next_day_clear_required: bool
    block_ttl_expires_at: datetime

@dataclass
class SellRejectionTracker:
    # 통합 차단 게이트 (Q1+Q2 — 2단계 TTL + 30초 TTL 공용 저장)
    _blocked_until: dict[str, datetime] = field(default_factory=dict)
    _blocked_reason: dict[str, RejectionReason] = field(default_factory=dict)
    # emit cap (사이클 52 호환 — 사이클 56 통합 후보)
    _logged_today: set[str] = field(default_factory=set)
    # V-1 알람 hook 사전 준비 (Q5, 사이클 56+)
    _history: dict[str, deque[RejectionEvent]] = field(default_factory=dict)

    # ──────────────────────────── public 게이트
    def is_blocked(self, ticker: str, now_kst: datetime) -> bool:
        """진입 차단 게이트. TTL 자연 만료면 lazy clear 후 False.
        execute_sell 진입 직후 (selling.add 다음) 호출 — 사이클 52 순서 보존."""
        expiry = self._blocked_until.get(ticker)
        if expiry is None:
            return False
        if now_kst >= expiry:
            self._blocked_until.pop(ticker, None)
            self._blocked_reason.pop(ticker, None)
            return False
        return True

    def should_emit_block_log(self, ticker: str) -> bool:
        """차단 게이트 발화 시 1회/ticker/일 emit cap 판단.
        return True 시 호출자가 즉시 mark_block_logged(ticker)."""
        return ticker not in self._logged_today

    def mark_block_logged(self, ticker: str) -> None:
        self._logged_today.add(ticker)

    # ──────────────────────────── public 등록 (분류별)
    def register_market_closed(
        self,
        ticker: str,
        now_kst: datetime,
        *,
        in_krx_main_hours: bool,
    ) -> datetime:
        """Q1 — KRX 메인 5분 TTL / 그 외(NXT 시간대) 다음 KST 09:00.

        Args:
            in_krx_main_hours: True 면 09:00~15:30 KRX 메인 거부 (일시 장애 가정,
                과보수 차단). False 면 NXT 시간대 거부 (자연 만료 명확).
        """
        if in_krx_main_hours:
            expiry = now_kst + timedelta(minutes=5)
        else:
            expiry = _compute_next_market_open_kst(now_kst)
        self._blocked_until[ticker] = expiry
        self._blocked_reason[ticker] = "market_closed"
        self._logged_today.discard(ticker)  # 만료 후 재폭주 시 INFO 1줄 emit
        self._append_history(
            ticker,
            RejectionEvent("market_closed", "", "", now_kst),
        )
        return expiry

    def register_market_order_disallowed(
        self,
        ticker: str,
        now_kst: datetime,
        *,
        is_nxt_session: bool,
        fallback_succeeded: bool,
    ) -> RejectionResult:
        """Q2 — 30초 TTL (동일 tick 폭주 차단) + NXT 폴백 실패 시 익일 청산 전환.

        Args:
            is_nxt_session: 현재 NXT 시간대 (08:00~09:00 / 15:30~20:00).
            fallback_succeeded: step_down 5호가 LIMIT 폴백이 성공했는지.
                False 이고 is_nxt_session=True → next_day_clear_required=True
                (Q2 핵심 — NXT 야간 폴백 실패 시 익일 KRX 시장가로 전환).
        """
        expiry = now_kst + timedelta(seconds=30)
        self._blocked_until[ticker] = expiry
        self._blocked_reason[ticker] = "market_order_disallowed"
        self._append_history(
            ticker,
            RejectionEvent("market_order_disallowed", "", "", now_kst),
        )
        next_day_required = (is_nxt_session and not fallback_succeeded)
        return RejectionResult(
            next_day_clear_required=next_day_required,
            block_ttl_expires_at=expiry,
        )

    def register_insufficient_quantity(
        self,
        ticker: str,
        now_kst: datetime,
    ) -> None:
        """Q3 — 차단 X (positions 제거가 자연 차단). history 만 적재.

        호출자(execute_sell)가 별도로:
          1) state.positions / DB positions 제거 (현행 보존)
          2) inquire_balance() 1회 호출 + [positions_reconciliation] 로그
        """
        self._append_history(
            ticker,
            RejectionEvent("insufficient_quantity", "", "", now_kst),
        )

    def record_rejection(
        self,
        ticker: str,
        reason: RejectionReason,
        msg_cd: str,
        msg1: str,
        now_kst: datetime,
    ) -> None:
        """V-1 알람 hook 사전 준비 — 분류별 register_* 외 raw history 채널."""
        self._append_history(
            ticker,
            RejectionEvent(reason, msg_cd, msg1, now_kst),
        )

    def get_recent_rejections(self, ticker: str) -> list[RejectionEvent]:
        """V-1 알람 / 진단 readonly 조회. maxlen=20."""
        dq = self._history.get(ticker)
        return list(dq) if dq else []

    # ──────────────────────────── 일일 reset
    def reset_daily(self) -> None:
        """_reset_daily_state 동행. 4 필드 일괄 clear."""
        self._blocked_until.clear()
        self._blocked_reason.clear()
        self._logged_today.clear()
        self._history.clear()

    # ──────────────────────────── internal
    def _append_history(self, ticker: str, event: RejectionEvent) -> None:
        dq = self._history.get(ticker)
        if dq is None:
            dq = deque(maxlen=20)
            self._history[ticker] = dq
        dq.append(event)


def _compute_next_market_open_kst(now: datetime) -> datetime:
    """다음 KST 09:00 만료 (사이클 52 헬퍼 재이주)."""
    next_day = now.date() if now.time() < dtime(9, 0) else now.date() + timedelta(days=1)
    return datetime.combine(next_day, dtime(9, 0), tzinfo=_KST_TZ)


def is_krx_main_hours(now_kst: datetime) -> bool:
    """KRX 메인 시간 (09:00~15:30) 판정 (Q1 분기 helper)."""
    t = now_kst.time()
    return dtime(9, 0) <= t < dtime(15, 30)


def is_nxt_session_hours(now_kst: datetime) -> bool:
    """NXT 시간대 (08:00~09:00 / 15:30~20:00) 판정 (Q2 분기 helper)."""
    t = now_kst.time()
    return (dtime(8, 0) <= t < dtime(9, 0)) or (dtime(15, 30) <= t < dtime(20, 0))
```

---

## 2. 행위 보존 매트릭스 (현행 → 신 위임 1:1)

| # | 분류 / 위치 | 현행 동작 (line) | 신 tracker 책임 | 변경 사항 (행위 변경 ★) |
|---|----------|----------------|----------------|----------------------|
| 1 | **진입 게이트** (482~499) | 단일 TTL 다음 09:00. INFO 1회/ticker/일 emit cap. 만료 lazy clear. | `is_blocked(ticker, now)` + `should_emit_block_log/mark_block_logged` | **무변경** (분류 무관 게이트 통합 — TTL 정책은 register 시점에 결정됨) |
| 2 | `is_market_closed_rejection` (577~629) | 거부 → WARNING + `_market_closed_blocked[ticker]=다음 09:00` + `discard` cap + NXT 시간대면 `stock_master.upsert(nxt_tradable=False)` 사후 보강 + `return` | `register_market_closed(ticker, now, in_krx_main_hours=...)` → expiry 반환 | **★ Q1 2단계 TTL** — KRX 메인(09:00~15:30) 거부 시 expiry = now+5분. 그 외(NXT 시간대) 다음 09:00 보존. `stock_master` 사후 보강은 `execute_sell` 잔존 (별 책임). |
| 3 | `is_insufficient_quantity` (631~637, 729~743) | `insufficient_qty=True` + break → 루프 외 `positions.pop` + `delete_position` + WARNING | `register_insufficient_quantity(ticker, now)` (history 만) + 기존 break + 기존 positions 정리 + **신규** `[positions_reconciliation]` INFO + `inquire_balance()` 1회 (잔고 회복 시 재등록 hook — execute_sell 잔존) | **★ Q3 추가** — `inquire_balance()` 호출 + `[positions_reconciliation]` 로그 1줄. 실패 graceful. positions 제거 자체는 현행 보존. |
| 4 | `is_market_order_disallowed` + MARKET (643~713) | 현재가 조회 → `step_down(cur, 5)` LIMIT 폴백 1회 → 성공 시 mapping 등록 + race 가드 + insert_trade(PENDING) + return. 폴백 거부 시 `_selling.discard` + WARNING + return (positions 보존, 다음 사이클 재트리거). | `register_market_order_disallowed(ticker, now, is_nxt_session=..., fallback_succeeded=...)` → `RejectionResult`. | **★ Q2 30초 TTL** — 폴백 결과 무관 30초 차단 (동일 tick 폭주 차단). **★ NXT 폴백 실패 → 익일 청산 전환** — `RejectionResult.next_day_clear_required=True` 시 `execute_sell` 호출자가 `_pending_next_day_clear.add(ticker)` (scheduler 09:00 KRX 시장가 자연 청산). 폴백 흐름 자체(mapping/race 가드/insert_trade)는 `execute_sell` 잔존. |
| 5 | (정상/기타 거부) | `_selling.discard` + 일반 재시도 | tracker 통과 (`is_blocked=False`) | **무변경** |

### 2.1 사이클 52 진입 게이트 순서 보존
- `selling.add(ticker)` (line 477) → `now_kst = datetime.now(_KST_TZ)` (481) → **`tracker.is_blocked(ticker, now_kst)` 위임** → True 시 `_selling.discard(ticker)` + return.
- 사이클 52 순서 (selling.add → 게이트 → discard) 절대 보존. selling.add *전* 게이트 검사 금지 (race 차단).

### 2.2 미해당 분류 (R-1 비대상)
- `is_insufficient_cash` — `execute_sell` 호출 없음 (매수 분기 전용). R-1 범위 외.
- `_nxt_downgrade_logged_today` (사이클 54) — emit cap 통합 사이클 56 후속.

---

## 3. 회귀 가드 매트릭스

### 3.1 사이클 52 기존 8 시나리오 영향 평가
`tests/unit/engine/test_b1_market_closed_zombie_block.py`:

| 시나리오 | 현행 검증 | R-1 후 영향 | 조치 |
|---------|---------|-----------|------|
| S1 APBK0918 100회 → place_order 1회 | 단일 09:00 TTL | **★ 갱신** — 거부 시각이 NXT 시간대(15:30~20:00 가정)면 동일. KRX 메인 가정이면 5분 TTL 로 변경 → 시각 명시 (`freezegun`) | 시각 명시 + 동작 동일 |
| S2 KIOK0320 100회 | 동상 | **★ 갱신** (동일) | 시각 명시 |
| S3a insufficient_quantity → 블록 set 미등록 | `_market_closed_blocked` 무영향 | **무변경** (tracker `_blocked_until` 도 미영향) | 무변경 |
| S3b market_order_disallowed 폴백 → 블록 set 클린 | `_market_closed_blocked` 무영향 (별 set) | **★ 갱신** — 사이클 55 Q2 후 폴백 성공해도 `_blocked_until` 에 30초 등록. *의미가 바뀜*. → S3b 는 "market_closed 블록 set 클린" 으로 좁히고 **신규 S3c** (market_order_disallowed → 30초 TTL 등록) 추가 | S3b 좁히기 + S3c 신규 |
| S4 TTL 만료 후 재진입 | 만료 다음 09:00 | **★ 갱신** — 5분 / 30초 / 다음 09:00 3 분류 | 분기별 3 케이스로 확장 |
| S5 ticker 격리 | 무영향 | **무변경** | 무변경 |
| S6 reset_daily_state → 블록 set clear | `_market_closed_blocked` clear | **무변경** (tracker.reset_daily 위임 호출 동일 효과) | 무변경 (호환 layer property 동작 확인) |
| S7 100회 차단 → INFO 1회 emit | emit cap 동작 | **무변경** (should_emit_block_log/mark_block_logged 위임) | 무변경 |

### 3.2 신규 회귀 가드 (16 케이스 예상)

**`tests/unit/engine/test_cycle55_sell_rejection_tracker.py`** (tracker 단위):
1. `is_blocked` False (등록 없음)
2. `is_blocked` True (TTL 미경과)
3. `is_blocked` False + lazy clear (TTL 경과)
4. `register_market_closed(in_krx_main_hours=True)` → expiry = now+5분
5. `register_market_closed(in_krx_main_hours=False)` → expiry = 다음 09:00
6. `register_market_closed` → `_logged_today.discard` (만료 후 재폭주 시 emit 보장)
7. `register_market_order_disallowed(is_nxt_session=False, fallback_succeeded=True)` → next_day=False, 30s
8. `register_market_order_disallowed(is_nxt_session=True, fallback_succeeded=False)` → **next_day=True** (Q2 핵심)
9. `register_market_order_disallowed(is_nxt_session=False, fallback_succeeded=False)` → next_day=False (KRX 메인은 다음 사이클 자연 재트리거)
10. `register_insufficient_quantity` → `_blocked_until` 무영향, history 적재
11. `record_rejection` → history maxlen=20 cap (21번째 등록 시 1번째 evict)
12. `get_recent_rejections` 응답 list 사본 (호출자 mutate 차단)
13. `reset_daily` → 4 필드 일괄 clear
14. `is_krx_main_hours` / `is_nxt_session_hours` 경계 시각 (08:59:59 / 09:00:00 / 15:29:59 / 15:30:00)
15. property 호환 — `order_engine._market_closed_blocked is tracker._blocked_until` (동일성)
16. property 호환 — `order_engine._market_closed_blocked_logged_today is tracker._logged_today`

**`tests/unit/engine/test_cycle55_execute_sell_integration.py`** (위임 통합, 8 케이스):
17. market_closed (KRX 메인) → 5분 TTL 등록 + S1 동형 (4분 후 차단 / 6분 후 진입)
18. market_closed (NXT) → 다음 09:00 TTL (사이클 52 동형)
19. market_order_disallowed 폴백 성공 (KRX 메인) → 30초 TTL + 폴백 흐름 보존
20. market_order_disallowed 폴백 실패 (NXT) → **`_pending_next_day_clear.add(ticker)` 호출** (Q2)
21. market_order_disallowed 폴백 실패 (KRX 메인) → next_day 등록 안 함
22. insufficient_quantity → `[positions_reconciliation]` 로그 + `inquire_balance` 1회 호출
23. insufficient_quantity → positions 제거 (현행 보존)
24. 정상 매도 → tracker 통과 + place_order 호출 (회귀 안전)

### 3.3 무영향 확인 (지속 PASS 의무)
- `tests/unit/engine/test_b3_nxt_downgrade_log_cap.py` (사이클 54, 4 시나리오) — `_nxt_downgrade_logged_today` R-1 범위 밖 (사이클 56 통합 예정), 무영향.
- 사이클 32 `[nxt_downgrade]` 회귀 가드 — `_strategy_exchange_async` 영역, 무영향.
- 사이클 30 `_completed_orders` race 가드 — 체결통보 영역, 무영향.

### 3.4 회귀 가드 부재 영역 (선행 의뢰 대상)
- `inquire_balance()` 호출 자체 회귀 — 신규 (Q3). tdd-engineer 가 `respx` mock 으로 호출 횟수 검증 가드 작성.
- `_pending_next_day_clear.add` (Q2) — `OrderEngine` 가 scheduler set 에 접근하는 경로 없음 → `execute_sell` 시그니처에 `pending_next_day_clear: set[str] | None = None` 주입 또는 `provider` callable 패턴 (사이클 15-A `_pending_next_day_clear_provider` 답습). tdd-engineer 가 주입 케이스 검증.

---

## 4. 호환 layer 설계 (사이클 48 stale_tracker 패턴 답습)

### 4.1 `OrderEngine.__init__` 변경

```python
# 기존 (사이클 52)
self._market_closed_blocked: dict[str, datetime] = {}
self._market_closed_blocked_logged_today: set[str] = set()
self._nxt_downgrade_logged_today: set[str] = set()  # 사이클 54 (R-1 범위 밖)

# 신규 (사이클 55)
from src.engine.sell_rejection import SellRejectionTracker
self._sell_rejection = SellRejectionTracker()
self._nxt_downgrade_logged_today: set[str] = set()  # 사이클 54 유지 (사이클 56 통합 예정)
```

### 4.2 property 위임 (3 호환 layer)

```python
@property
def _market_closed_blocked(self) -> dict[str, datetime]:
    """사이클 52 호환 — tracker._blocked_until 직접 노출 (is 동일성)."""
    return self._sell_rejection._blocked_until

@property
def _market_closed_blocked_logged_today(self) -> set[str]:
    """사이클 52 emit cap 호환."""
    return self._sell_rejection._logged_today
```

- 사이클 48 `stale_tracker` 답습: dict/set 직접 노출 → `is` 동일성 보장. 기존 테스트 `_market_closed_blocked[ticker]` 직접 add/clear 가능.
- `_nxt_downgrade_logged_today` 는 *property 위임 안 함* (R-1 범위 밖 — 사이클 56 통합 시 함께 위임 신규 추가).

### 4.3 `execute_sell` 진입 게이트 (line 482~499 치환)

```python
# 기존 (사이클 52, 18 lines)
now_kst = datetime.now(_KST_TZ)
_expiry = self._market_closed_blocked.get(ticker)
if _expiry is not None:
    if now_kst < _expiry:
        if ticker not in self._market_closed_blocked_logged_today:
            self._market_closed_blocked_logged_today.add(ticker)
            try:
                await write_log(...)
            except Exception:
                logger.debug(...)
        self._selling.discard(ticker)
        return
    else:
        del self._market_closed_blocked[ticker]

# 신규 (사이클 55, 11 lines)
now_kst = datetime.now(_KST_TZ)
if self._sell_rejection.is_blocked(ticker, now_kst):
    if self._sell_rejection.should_emit_block_log(ticker):
        self._sell_rejection.mark_block_logged(ticker)
        try:
            await write_log(
                "INFO",
                f"[sell_rejection_blocked] ticker={ticker} strategy={strategy_id} "
                f"reason={self._sell_rejection._blocked_reason.get(ticker, '')} "
                f"expiry={self._sell_rejection._blocked_until[ticker].isoformat()}",
            )
        except Exception:
            logger.debug("[sell_rejection_blocked] write_log 실패", exc_info=True)
    self._selling.discard(ticker)
    return
```

> **로그 prefix 변경 검토 결정**: `[market_closed_blocked]` → `[sell_rejection_blocked]` 로 변경 (분류 통합 의미 반영). reason 필드로 분류 노출. **운영 모니터링 grep 패턴 변경 — `docs/HARNESS_CHANGELOG.md` 사이클 55 행에 명시 + Grafana/Loki 대시보드 grep 패턴 갱신 별도 cron 의뢰.** *대안*: `[market_closed_blocked]` 유지 (운영 grep 무영향) — **추천: 유지** (사이클 52 grep 호환 + reason 필드는 메시지 본문 추가).

### 4.4 `_reset_daily_state` (1054 인근)

```python
# 기존
self._market_closed_blocked.clear()
self._market_closed_blocked_logged_today.clear()
self._nxt_downgrade_logged_today.clear()

# 신규
self._sell_rejection.reset_daily()  # 4 필드 일괄 위임 clear
self._nxt_downgrade_logged_today.clear()  # 사이클 54 유지
```

- 호출 측(scheduler `_reset_daily_state` → `OrderEngine.reset_daily_state`) 무변경 — 사이클 48 stale_tracker 답습 패턴.

### 4.5 분류별 등록 위임 (577~713 치환 요약)

- **577~629 (market_closed)**: `self._market_closed_blocked[ticker] = _compute_next_market_open_kst(_now_kst)` + `self._market_closed_blocked_logged_today.discard(ticker)` 2 줄을 `self._sell_rejection.register_market_closed(ticker, _now_kst, in_krx_main_hours=is_krx_main_hours(_now_kst))` 1 줄로 치환. `stock_master.upsert(nxt_tradable=False)` 사후 보강은 `execute_sell` 잔존 (별 책임).
- **631~637 (insufficient_quantity)**: `is_insufficient_quantity(e)` 분기 진입 직후 `self._sell_rejection.register_insufficient_quantity(ticker, _now_kst)` 1 줄 추가. break 보존. *루프 외* 729~743 의 positions 정리 직후 `inquire_balance()` 호출 + `[positions_reconciliation]` 로그 추가 (Q3).
- **643~713 (market_order_disallowed)**: 폴백 시도 후 (성공/실패 결정 직후) `result = self._sell_rejection.register_market_order_disallowed(ticker, _now_kst, is_nxt_session=is_nxt_session_hours(_now_kst), fallback_succeeded=<bool>)` 호출. `result.next_day_clear_required=True` 시 `self._pending_next_day_clear_provider().add(ticker)` (사이클 15-A `_pending_next_day_clear_provider` lambda 답습 — `_unsubscribe_if_no_other_strategy` 패턴 동형).

---

## 5. CLAUDE.md 동기화 영역

### 5.1 루트 `CLAUDE.md` — 핵심 안전 규칙 "NXT 매도 거부 좀비 차단"
- **수정 전 (사이클 52)**: "`_market_closed_blocked` ticker별 TTL 게이트 (다음 KST 09:00 만료)"
- **수정 후 (사이클 55)**: "`SellRejectionTracker.is_blocked()` 진입 차단 게이트 — **2단계 TTL**: KRX 메인 시간(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 위임)."

### 5.2 `src/engine/CLAUDE.md` — `order_engine.py` 매도 분기 갱신
- `is_market_closed_rejection` 항목 갱신 (2단계 TTL)
- `is_market_order_disallowed` 항목 갱신 (30초 TTL + NXT 익일 전환)
- `is_insufficient_quantity` 항목 추가 (reconciliation 로그 + inquire_balance)
- 모듈 맵에 `sell_rejection.py(SellRejectionTracker, 사이클 55)` 추가 (stale_tracker / boot_manager 형제 모듈)

### 5.3 `_workspace/00_leader_trading_rules.md` — 매매 명세
- "NXT 매도 거부 처리" 절 갱신 (사이클 55 행 추가, 2단계 TTL + NXT 익일 전환 + reconciliation)

### 5.4 사이클 55 종료 검수 (team-leader)
- `docs/HARNESS_CHANGELOG.md` 사이클 55 행 추가 (행위 보존 + Q1/Q2/Q3 행위 변경 명시)
- `_workspace/2026-06-01_log_analysis.md` R-1 종결 표시

---

## 6. 결정 1 — emit cap 인터페이스 옵션 (사이클 56 대비)

**refactor-expert 권고**: **옵션 A** (R-1 = `set[str]` 직접 사용)

**사유**:
1. **사이클 56 변경 부담 동등 (Wrapper 교체)** — 옵션 B (`_should_emit/_mark_emitted` 추상) 도입 시 사이클 55 회귀 가드 16 케이스가 추상 인터페이스를 검증 → 사이클 56 에서 구현체 교체 시 그 추상 검증이 *의미 잃음*. 결국 사이클 56 에서 재작성 필요.
2. **YAGNI** — CLAUDE.md "3 회 반복 = 추상화 후보" 원칙. 사이클 56 에서 사이클 31/52/54 3 set 통합 시점에 `DailyEmitCap[K]` 제네릭 추상이 *그제야* 자연 발생. R-1 에서 사전 추상은 미래 가정.
3. **호환 layer 영향 최소화** — 옵션 A 는 `_logged_today: set[str]` 직접 노출 → 사이클 52 `_market_closed_blocked_logged_today` property 위임이 1 줄. 옵션 B 는 wrapper 객체 노출 → 사이클 52 회귀 가드의 `.add()/.discard()` 직접 호출이 깨짐 → 호환 layer 복잡도 ↑.
4. **사이클 48 stale_tracker 패턴 답습** — `universe_excluded_today: set[str] = field(default_factory=set)` 직접 노출 패턴 동형. 신규 패턴 도입 금지 원칙.
5. **사이클 56 마이그레이션 계획**: `_logged_today: set[str]` → `_emit_cap: DailyEmitCap[str]` 필드 교체 + `should_emit_block_log/mark_block_logged` 메서드 내부만 변경. R-1 회귀 가드 16 케이스는 메서드 시그니처 보존으로 무회귀. property `_market_closed_blocked_logged_today` 호환 layer 도 `_emit_cap._internal_set` 식 view 노출 가능.

**최종**: 옵션 A 채택. 사이클 56 에서 옵션 B 자연 진화.

---

## 7. 막힘 보고 / 결정 위임 (team-leader 확인 요청)

### 7.1 결정 위임 D-1 — 로그 prefix 변경 여부
- 4.3 절 검토 결정: `[market_closed_blocked]` 유지 추천 (운영 grep 호환).
- *대안*: `[sell_rejection_blocked] reason=...` 통합 (의미 명확).
- **위임**: team-leader 가 운영 Grafana/Loki 영향 평가 후 결정. 추천 = 유지.

### 7.2 결정 위임 D-2 — `_pending_next_day_clear` 주입 방식 (Q2)
- *옵션 P-1*: `_pending_next_day_clear_provider: Callable[[], set[str]]` lambda 주입 (사이클 15-A `_unsubscribe_if_no_other_strategy` 답습 — 일관성 ↑).
- *옵션 P-2*: `OrderEngine.execute_sell` 시그니처에 `pending_next_day_clear: set[str] | None = None` 파라미터 추가 (호출자 책임 명시 — 명시성 ↑).
- **추천**: P-1 (선례 답습, scheduler `OrderEngine.__init__` 직후 1회 주입).
- **위임**: tdd-engineer Red 작성 시 P-1 가정. team-leader 가 P-2 선호 시 사전 통보 요청.

### 7.3 결정 위임 D-3 — `inquire_balance()` 호출 위치 (Q3)
- *옵션 B-1*: `execute_sell` 내부 (현행 line 729~743 positions 정리 직후 호출).
- *옵션 B-2*: `tracker.register_insufficient_quantity` 내부 (캡슐화 ↑).
- **추천**: B-1 (KIS REST 호출은 `OrderEngine` 책임 — `SellRejectionTracker` 는 정책 객체로 외부 I/O 격리. 사이클 48 stale_tracker 도 KIS 호출 안 함 — scheduler 가 `quotation.inquire_ccnl` 호출).
- **위임**: B-1 가정. team-leader 미동의 시 사전 통보.

---

## 8. 종합 요약 (tdd-engineer 발주용)

- **신규 모듈**: `src/engine/sell_rejection.py` (130~170L)
- **OrderEngine 변경**: 3 dict/set 필드 → tracker 위임 + 2 property (사이클 54 nxt_downgrade 는 R-1 범위 밖) + 진입 게이트 11 lines + 분류별 등록 위임 3 곳 + `inquire_balance` 1 호출 (Q3) + `_pending_next_day_clear` provider 주입 1 호출 (Q2).
- **회귀 가드 신규**: 16 케이스 단위 + 8 케이스 통합 (총 24 신규).
- **사이클 52 가드 갱신**: 8 케이스 중 S1/S2/S3b/S4 → 4 케이스 갱신 + S3c 신규 추가 (총 5 케이스 영향).
- **CLAUDE.md 동기화**: 4 파일 (루트 / src/engine / 00_leader_trading_rules / HARNESS_CHANGELOG).
- **위험 등급**: HIGH (매매 hot path 4 분류 통합). 호환 layer + 행위 보존 매트릭스 1:1 + 도메인 자문 5 RECOMMEND 반영으로 회귀 위험 격리.
- **CLAUDE.md 절대 규칙 위반**: 0건 (보존 항목 7종 모두 확인 — 7장 결정 위임 3건만 team-leader 최종 확인 요청).
