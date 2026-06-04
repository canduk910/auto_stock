# 사이클 57 발주서 — V-1 매도 거부 폭주 실시간 알람

> **발주**: team-leader (2026-06-04)
> **카드 원본**: `_workspace/2026-06-01_log_analysis.md` V-1 (P1)
> **위험 등급**: LOW (관찰성/가시화만 추가, 매매 hot path 분기 변경 0)
> **선례 비교**:
> - 사이클 31 R6 `_risk_silent_skip_logged_today` 1회/페어/일 INFO emit cap
> - 사이클 52 `_market_closed_blocked_logged_today` 1회/ticker/일
> - 사이클 54 `_nxt_downgrade_logged_today` 1회/ticker/일
> - 사이클 55 R-1 `SellRejectionTracker._history` deque maxlen=20 (V-1 인프라 사전 도입)
> - 사이클 56 `DailyEmitCap[K]` 제네릭 (cap 패턴 표준화 완료)

---

## 0. 배경 — V-1 카드 본질

**문제**: 사이클 52 B-1 의 10분 500건 매도 거부 폭주가 *실시간 운영자 알람 없이* 다음 날 20:10 자동 리포트에서야 발견됨. 사이클 55 R-1 2단계 TTL + 30초 TTL 도입으로 *폭주 자체* 는 차단되지만, "왜 폭주가 발생했는지" 의 즉시 가시성은 여전히 없음. 사이클 56 의 cap 패턴은 *로그 발화 폭주 차단* 이지 *사고 발생 즉시 운영자 통보* 가 아님.

**해결 본질**: SellRejectionTracker 가 `record_rejection` 시점에 (a) 단일 ticker 의 최근 10분 거부 카운트 누적 + (b) 임계 초과 시 단일 CRITICAL system_logs INSERT + (c) cooldown 으로 같은 ticker 알람 폭주 방지.

**범위 제약**:
- 외부 채널 (Slack/email/SMS) 통합 = **본 사이클 제외**. 추후 사이클 (system_config.notification_webhook_url 신설 시점) 별도.
- 매매 hot path 분기 변경 0 — register_market_closed / register_market_order_disallowed / register_insufficient_quantity 의 *기존 동작* 절대 보존. 알람 hook 만 추가.
- KIS API 추가 호출 0 — registry/positions 의존 안 함 (D-4 결정 참조).

---

## 1. team-leader 결정사항 (D-1 ~ D-7)

### D-1 임계 / 시간 윈도우 — **D-1-b 채택**: 10분당 5건 초과

**판정**:

| 옵션 | 임계 | 채택 |
|------|------|------|
| D-1-a | 시간당 5건 초과 (분석 메모) | ✗ — 1시간 후 발화는 사고 *진행 중* 대응 불가 |
| D-1-b | **10분당 5건 초과** (사이클 52 폭주 실측 기반) | **✓ 채택** |
| D-1-c | 10분당 10건 초과 | ✗ — 일시 KIS 거부 5~10건 누락 위험 |
| D-1-d | 다중 임계 (WARN + CRITICAL) | ✗ — 본 사이클 *최소 본질* 위반, 사이클 58+ 별도 검토 |

**사유**:
1. **사이클 52 B-1 실측 (2026-06-01 13:35~13:45)** — 10분 500건 폭주가 약 1분에 50건 수준으로 시작. 10분 5건 임계는 사고 *발생 60~90초* 후 발화 보장.
2. **R-1 `_history` deque maxlen=20** — 최근 20건만 보존. 시간당 윈도우 (60분) 면 폭주 시 deque overflow 로 임계 판정 부정확. 10분 윈도우는 deque 20건 안에서 안전.
3. **단일 임계** — 다중 임계 (D-1-d) 는 *cooldown 정책 복잡도* (WARN 발화 후 CRITICAL 발화 허용 여부 등) 증가. 본 사이클 = 단일 임계 + 단일 알람 레벨 (CRITICAL).

**구체 명세**:
- 윈도우: `now_kst - timedelta(minutes=10)` 이후 발생한 RejectionEvent 카운트
- 임계: `count > 5` (5건은 미발화, 6건째에서 발화)
- 카운트 기준: `_history[ticker]` 의 `occurred_at >= window_start` 필터 + len. msg_cd / reason 무관 (모든 sell 거부 합산).
- **근거 보강**: `SellRejectionTracker.register_*` 3 메서드 + `record_rejection` 4 채널 모두 `_append_history` 경유 → 카운팅 통일.

### D-2 알람 cooldown — **D-2-c 채택**: 30분 cooldown (per-ticker)

**판정**:

| 옵션 | cooldown | 채택 |
|------|----------|------|
| D-2-a | 10분 (domain-expert 권고) | ✗ — 10분 윈도우와 동일 → 만료 즉시 카운터 임계 재돌입 시 폭주 알람 |
| D-2-b | 일일 1회 (DailyEmitCap 직접 활용) | ✗ — 사고가 1시간 후 재발할 때 운영자 인지 불가 |
| D-2-c | **30분** | **✓ 채택** |

**사유**:
1. **10분 윈도우 + 10분 cooldown 충돌** — D-2-a 채택 시 cooldown 만료 시점에 윈도우 안 카운트가 여전히 6+ 면 즉시 재발화 → 30분당 3회 알람 가능. 30분 cooldown 은 윈도우 (10분) 의 3배 → 카운트 자연 감쇠 보장.
2. **사고 *진행* 추적 가능** — KIS 좀비 사고가 30분 이상 지속될 경우 30분 간격 알람으로 운영자가 *진행 중* 인지 *재발* 인지 구분 가능.
3. **DailyEmitCap 부적합** — daily reset 만 지원. cooldown 은 *시간 기반* 으로 다른 자료구조 필요 (D-5 구현 결정 참조).
4. **운영 부담** — 5 ticker 동시 사고 시 30분당 최대 5건 알람. system_logs CRITICAL 5건/30분은 무시 가능 수준.

**구체 명세**:
- `_alarm_cooldown_until: dict[str, datetime]` 신규 필드 (SellRejectionTracker 내부)
- 발화 직후 `_alarm_cooldown_until[ticker] = now_kst + timedelta(minutes=30)`
- cooldown 진입 시 `now_kst < _alarm_cooldown_until[ticker]` → 알람 skip (카운트 누적은 계속)
- cooldown 만료 시 lazy clear (`is_blocked` 패턴 답습)
- `reset_daily()` 가 `_alarm_cooldown_until.clear()` 동행

### D-3 외부 채널 통합 범위 — **D-3-a 채택**: system_logs CRITICAL INSERT 만

**판정**:

| 옵션 | 범위 | 채택 |
|------|------|------|
| D-3-a | **system_logs CRITICAL 만** | **✓ 채택** |
| D-3-b | system_logs + Slack webhook 인터페이스 hook | ✗ — *미사용 인터페이스* 도입 비용 |
| D-3-c | Slack webhook 까지 통합 (notification_webhook_url 신설) | ✗ — system_config 신규 키 + webhook HTTP 의존 + 보안 검토 → 별도 사이클 |

**사유**:
1. **V-1 본질 = 실시간 감지** — system_logs 는 `/api/system-logs` 프론트 폴링 (5초 주기) 으로 *실시간* 가시성 충족. 프론트 헤더 알림 배지 (LEVEL=CRITICAL 카운트) 가 운영자 즉시 인지 보장.
2. **외부 채널 의존성 회피** — Slack webhook = HTTP 외부 의존 + URL 토큰 관리 + retry 정책 신설 필요. system_logs 는 graceful fire-and-forget 기존 패턴 답습.
3. **본 사이클 LOW 위험 보존** — 외부 채널 추가는 신규 모듈 + 신규 system_config 키 → MEDIUM+ 위험. 본 사이클은 *관찰성 가시화* 만 LOW.
4. **후속 사이클 분리** — V-1 검증 완료 후 (사이클 58+) `notification_webhook_url` + Slack 통합 별도 카드. 본 사이클이 채널 인터페이스를 *미리 정의* 하면 사용처 0 인 사장 코드.

### D-4 알람 메시지 정보 범위 — **D-4-b 채택**: tracker 독립 최소 메시지

**판정**:

| 옵션 | 메시지 범위 | 채택 |
|------|-----------|------|
| D-4-a | 전체 (현재 보유 / positions 상태 / 권장 행동) — tracker 에 registry 주입 | ✗ — tracker 의존성 폭증, 단위 테스트 복잡도 ↑ |
| D-4-b | **최소** (KST + ticker + 윈도우 횟수 + 거부 코드 분포 + 마지막 메시지) | **✓ 채택** |
| D-4-c | 분리 (tracker 최소 + OrderEngine 보유/권장 행동 추가) | ✗ — 발화 위치 분기 복잡 |

**사유**:
1. **tracker 독립성 보존** — `SellRejectionTracker` 의 현재 의존성 = `DailyEmitCap` + `RejectionEvent` 만. registry/positions 주입 시 사이클 55 의 *4 분류 통합 단일 정책 객체* 책임 위반.
2. **운영자 추가 조사 가능** — system_logs CRITICAL 발화 시점에 ticker 가 있으면 운영자가 `/api/realtime/positions` + `/api/trades?ticker=...` 즉시 조회 가능. 메시지에 보유/권장 행동 포함은 *알람 메시지* 가 아닌 *진단 메시지* 책임 영역.
3. **D-4-c 분리 복잡도** — OrderEngine 이 알람 발화 위치 (D-5) 가 아니라 단순 record 호출자. 분리 시 OrderEngine 에 알람 hook 추가 → tracker 의 단일 책임 깨짐.
4. **메시지 포맷 명세** (3.2 절 참조):
   ```
   [매도거부폭주] ticker={ticker} window=10min count={count} threshold=5
     reasons={reason_dist}
     last_msg_cd={last.msg_cd} last_msg1={last.msg1}
     occurred_at_kst={now_kst.isoformat()}
   ```

### D-5 알람 발화 위치 — **D-5-a 채택**: `_append_history` 내부 자동 발화

**판정**:

| 옵션 | 위치 | 채택 |
|------|------|------|
| D-5-a | **`_append_history` 내부 자동 발화** | **✓ 채택** |
| D-5-b | 별도 `_check_alarm_threshold` 메서드 + execute_sell 명시 호출 | ✗ — execute_sell 14곳 hook 추가 + 사후 누락 위험 |
| D-5-c | scheduler 주기 task (1분 마다 전 ticker) | ✗ — *즉시성* 손실 (최대 60초 지연) + 신규 task |

**사유**:
1. **즉시성** — `register_*` 3 메서드 + `record_rejection` 모두 `_append_history` 경유 → 단일 진입점으로 *모든 거부 즉시* 임계 체크.
2. **사이클 55 R-1 인프라 활용** — `_history` deque 적재 직후가 자연스러운 임계 평가 위치. 외부 호출자 (OrderEngine) 코드 변경 0.
3. **단위 테스트 격리** — tracker 단독 인스턴스로 알람 발화 시나리오 8~12 케이스 검증 가능.
4. **D-5-c 부적합** — 사이클 17 의 `_near_signal_loop` 폐기 교훈 (신규 주기 task = race 위험). 본 알람은 *이벤트 기반* 이 적합.

**구현 시그너처**:
```python
def _append_history(self, ticker: str, event: RejectionEvent) -> None:
    """history deque 적재 + V-1 알람 임계 체크 (사이클 57)."""
    dq = self._history.get(ticker)
    if dq is None:
        dq = deque(maxlen=20)
        self._history[ticker] = dq
    dq.append(event)
    # V-1 (사이클 57) — 10분 5건 초과 시 CRITICAL system_logs 발화
    self._maybe_emit_burst_alarm(ticker, event.occurred_at)
```

### D-6 회귀 가드 매트릭스 — 12 케이스

**파일**: `tests/unit/engine/test_v1_rejection_alarm.py` (신규)

| # | 케이스 | 검증 |
|---|--------|------|
| 1 | 임계 미만 (5건) → 알람 없음 | system_logs CRITICAL INSERT 0건 |
| 2 | 임계 도달 (6건째) → 알람 1회 발화 | CRITICAL INSERT 1건, 메시지 포맷 정확성 |
| 3 | cooldown 중 (10분당 7~50건) → 알람 skip | CRITICAL INSERT 누적 1건 보존 |
| 4 | cooldown 만료 (30분 후) + 임계 재도달 → 재발화 | CRITICAL INSERT 2건 |
| 5 | 10분 윈도우 밖 이벤트는 카운트 제외 | 11분 전 5건 + 현재 5건 = 5건 (미발화) |
| 6 | 다른 ticker 영향 없음 (격리) | ticker A 6건 발화, ticker B 5건 미발화 |
| 7 | `_history` deque maxlen=20 보존 | 30건 발생해도 deque 길이 20, 알람 동작 정상 |
| 8 | 메시지 포맷 — reason 분포 정확성 | market_closed 4 + market_order_disallowed 2 = "market_closed:4, market_order_disallowed:2" |
| 9 | 메시지 포맷 — last_msg_cd / last_msg1 정확성 | 마지막 RejectionEvent 의 msg_cd/msg1 노출 |
| 10 | `reset_daily()` 동행 — cooldown 초기화 | cooldown 진입 → reset_daily → 즉시 재발화 가능 |
| 11 | safe_write_log 실패 graceful | system_logs 예외 raise 시 tracker 정상 동작 (예외 swallow) |
| 12 | 사이클 52/54/55/56 회귀 무영향 | 기존 회귀 테스트 PASS (register_market_closed TTL / register_market_order_disallowed NXT 전환 / DailyEmitCap 동작) |

**기존 회귀 가드 영향 없음 보장**:
- `tests/unit/engine/test_sell_rejection.py` (사이클 55)
- `tests/unit/engine/test_b1_market_closed_zombie_block.py` (사이클 52)
- `tests/unit/engine/test_daily_emit_cap.py` (사이클 56)
- `tests/unit/engine/test_cycle54_nxt_downgrade_emit_cap.py` (사이클 54)

### D-7 domain-expert 자문 사전 의뢰 — **생략**

**판정**: 본 사이클 = domain-consult 호출 안 함.

**사유**:
1. **사이클 55 Q5 자문에서 메시지 형태 권고 이미 받음** — domain-expert 가 "최근 10분 거부 횟수 / 거부 코드 분포 / 마지막 거부 메시지" 핵심 정보 명시. 본 사이클은 *임계 수치* (10분 5건) 만 team-leader 단독 결정.
2. **사이클 52 B-1 실측 데이터** — 10분 500건 폭주 시 1분당 50건 수준. 임계 5건은 사고 *60~90초 후* 발화 보장 → 운영자 인지 시간 충분. 추가 자문 비용 정당화 어려움.
3. **위험 등급 LOW** — 매매 hot path 분기 변경 0. domain-expert 자문은 *매매 행위 영향 평가* 가 본질이라, 관찰성/가시화 카드에는 부적합.
4. **후속 사이클 가능성** — 실제 운영에서 임계 5건이 *과민* (정상 거부 시 알람 폭주) 또는 *둔감* (사고 늦은 감지) 으로 판명되면 사이클 58+ 에서 domain-expert 자문 + 임계 조정. 본 사이클 데이터 수집 후 결정.

---

## 2. tdd-engineer Red 단계 발주

### 2.1 신규 파일 `tests/unit/engine/test_v1_rejection_alarm.py`

**선례 답습**:
- `tests/unit/engine/test_sell_rejection.py` (사이클 55 R-1, ~20 케이스)
- `tests/unit/engine/test_daily_emit_cap.py` (사이클 56-A, ~15 케이스)

**프레임워크**:
- pytest + freezegun (시간 윈도우 / cooldown 검증)
- `unittest.mock.patch` (`src.db.system_logs.safe_write_log` 호출 횟수 + 인자 검증)

**케이스 구성 (D-6 12 케이스 매트릭스)**:

```python
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.sell_rejection import SellRejectionTracker, RejectionEvent

_KST = timezone(timedelta(hours=9))


class TestV1RejectionAlarm:
    """사이클 57 V-1 — 매도 거부 폭주 실시간 알람.

    임계: 10분 윈도우 5건 초과 (6건째 발화).
    Cooldown: 30분 per-ticker (윈도우의 3배).
    레벨: CRITICAL system_logs INSERT.
    """

    def _make_event(self, reason="market_closed", msg_cd="APBK0918",
                    msg1="장운영시간외", at=None):
        return RejectionEvent(reason, msg_cd, msg1, at or datetime.now(_KST))

    @pytest.mark.asyncio
    async def test_below_threshold_no_alarm(self):
        """1) 5건 (임계 정확히 일치) → 알람 없음."""
        tracker = SellRejectionTracker()
        now = datetime(2026, 6, 4, 13, 0, 0, tzinfo=_KST)
        with patch("src.engine.sell_rejection.safe_write_log",
                   new_callable=AsyncMock) as mock_log:
            for i in range(5):
                tracker.record_rejection(
                    "005930", "market_closed", "APBK0918", "장운영시간외",
                    now + timedelta(seconds=i),
                )
            await asyncio.sleep(0)  # fire-and-forget task drain
            mock_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_threshold_exceeded_alarm_emitted(self):
        """2) 6건째 → CRITICAL 알람 1회 발화."""
        tracker = SellRejectionTracker()
        now = datetime(2026, 6, 4, 13, 0, 0, tzinfo=_KST)
        with patch("src.engine.sell_rejection.safe_write_log",
                   new_callable=AsyncMock) as mock_log:
            for i in range(6):
                tracker.record_rejection(
                    "005930", "market_closed", "APBK0918", "장운영시간외",
                    now + timedelta(seconds=i),
                )
            await asyncio.sleep(0)
            assert mock_log.await_count == 1
            level, msg = mock_log.await_args.args
            assert level == "CRITICAL"
            assert "[매도거부폭주]" in msg
            assert "ticker=005930" in msg
            assert "count=6" in msg
            assert "threshold=5" in msg

    # ... 3) ~ 12) 케이스 동일 패턴
```

### 2.2 신규 인터페이스 (tdd-engineer Red 작성)

**파일**: `src/engine/sell_rejection.py` (사이클 55 R-1 확장)

```python
# 신규 import
from src.db.system_logs import safe_write_log  # 사이클 56-E

# SellRejectionTracker 필드 추가
@dataclass
class SellRejectionTracker:
    # ... 기존 필드 보존 ...
    # 사이클 57 V-1 — 알람 cooldown (per-ticker, 30분)
    _alarm_cooldown_until: dict[str, datetime] = field(default_factory=dict)

    # 사이클 57 V-1 신규 상수 (class-level constant)
    _ALARM_WINDOW_MINUTES: ClassVar[int] = 10
    _ALARM_THRESHOLD: ClassVar[int] = 5  # 초과 (> 5 = 6 건째 발화)
    _ALARM_COOLDOWN_MINUTES: ClassVar[int] = 30

    # 신규 private 메서드
    def _maybe_emit_burst_alarm(self, ticker: str, now_kst: datetime) -> None:
        """10분 윈도우 5건 초과 시 CRITICAL system_logs 발화.

        사이클 57 V-1 — `_append_history` 내부 자동 호출.
        cooldown 진입 시 skip (카운트 누적은 계속).
        """
        # cooldown 체크 (lazy clear)
        cooldown_expiry = self._alarm_cooldown_until.get(ticker)
        if cooldown_expiry is not None:
            if now_kst < cooldown_expiry:
                return  # cooldown 중 — skip
            self._alarm_cooldown_until.pop(ticker, None)

        # 10분 윈도우 카운트
        window_start = now_kst - timedelta(minutes=self._ALARM_WINDOW_MINUTES)
        dq = self._history.get(ticker)
        if dq is None:
            return
        recent = [e for e in dq if e.occurred_at >= window_start]
        if len(recent) <= self._ALARM_THRESHOLD:
            return

        # 알람 발화
        reason_counts: dict[str, int] = {}
        for ev in recent:
            reason_counts[ev.reason] = reason_counts.get(ev.reason, 0) + 1
        reason_dist = ", ".join(
            f"{r}:{c}" for r, c in sorted(reason_counts.items())
        )
        last = recent[-1]
        msg = (
            f"[매도거부폭주] ticker={ticker} window=10min "
            f"count={len(recent)} threshold={self._ALARM_THRESHOLD} "
            f"reasons={reason_dist} "
            f"last_msg_cd={last.msg_cd} last_msg1={last.msg1} "
            f"occurred_at_kst={now_kst.isoformat()}"
        )
        # fire-and-forget (safe_write_log 가 graceful 보장)
        asyncio.create_task(safe_write_log("CRITICAL", msg))
        # cooldown 등록
        self._alarm_cooldown_until[ticker] = (
            now_kst + timedelta(minutes=self._ALARM_COOLDOWN_MINUTES)
        )

    # _append_history 수정
    def _append_history(self, ticker: str, event: RejectionEvent) -> None:
        """history deque 적재 + V-1 알람 임계 체크 (사이클 57)."""
        dq = self._history.get(ticker)
        if dq is None:
            dq = deque(maxlen=20)
            self._history[ticker] = dq
        dq.append(event)
        # 사이클 57 V-1 — 10분 5건 초과 시 CRITICAL system_logs
        self._maybe_emit_burst_alarm(ticker, event.occurred_at)

    # reset_daily 확장
    def reset_daily(self) -> None:
        """일일 정산 — 5 필드 일괄 clear (사이클 57 _alarm_cooldown_until 추가)."""
        self._blocked_until.clear()
        self._blocked_reason.clear()
        self._logged_today.clear()
        self._history.clear()
        self._alarm_cooldown_until.clear()  # 사이클 57 V-1
```

### 2.3 회귀 가드 추가 검증

**기존 테스트 PASS 보장**:
- `tests/unit/engine/test_sell_rejection.py` 전체 (사이클 55)
- `tests/unit/engine/test_b1_market_closed_zombie_block.py` (사이클 52)
- `tests/unit/engine/test_cycle54_nxt_downgrade_emit_cap.py` (사이클 54)
- `tests/unit/engine/test_daily_emit_cap.py` (사이클 56-A)

**`reset_daily()` 호환성**:
- 기존 4 필드 clear 보존 + 신규 `_alarm_cooldown_until` clear 추가
- `OrderEngine.reset_daily_state()` 위임 호출 영향 없음 (5 필드 일괄 → 4 필드 → 5 필드 확장만)

---

## 3. backend-dev Green 단계 발주

### 3.1 구현 범위

**대상 파일**: `src/engine/sell_rejection.py` 1개만.

**변경 라인 예상**: +60L (필드 1 + 상수 3 + private 메서드 1 + `_append_history` 1줄 + `reset_daily` 1줄)

### 3.2 구현 순서

1. **상수 + 필드 추가** (사이클 55 R-1 패턴 답습)
2. **`_maybe_emit_burst_alarm` 메서드 신설** (D-5-a 자동 발화)
3. **`_append_history` 수정** (1줄 hook)
4. **`reset_daily` 확장** (1줄 clear 추가)
5. **import 추가**: `asyncio`, `from typing import ClassVar`, `from src.db.system_logs import safe_write_log`

### 3.3 절대 금지 사항

- **`register_market_closed` / `register_market_order_disallowed` / `register_insufficient_quantity` 본문 변경 금지** — 기존 행위 100% 보존. 알람은 *공통 진입점* (`_append_history`) 에서만 발화.
- **외부 호출자 (OrderEngine) 변경 금지** — V-1 본질은 *tracker 내부 hook* 만. execute_sell / execute_buy 분기 변경 0.
- **TTL / 차단 정책 변경 금지** — 사이클 55 R-1 의 `_blocked_until` / `_blocked_reason` / `_logged_today` 동작 100% 보존.
- **registry / positions 의존성 추가 금지** — D-4-b 결정에 따라 tracker 독립성 보존.
- **asyncio.create_task 예외 swallow** — `safe_write_log` 가 내부 graceful 보장 + 본 hook 은 fire-and-forget. await 금지 (`_append_history` 동기 메서드).

### 3.4 commit 명세

```
feat(sell_rejection): V-1 매도 거부 폭주 실시간 알람 (사이클 57)

10분 윈도우 5건 초과 시 CRITICAL system_logs 발화 + 30분 per-ticker cooldown.
사이클 52 B-1 폭주 10분 500건 실측 기반 임계 결정.
사이클 55 R-1 `_history` deque + 사이클 56-E `safe_write_log` 위에 hook 추가.
register_* 3 메서드 본문 변경 0 — `_append_history` 단일 진입점에서만 발화.
회귀 가드 12 케이스 (tests/unit/engine/test_v1_rejection_alarm.py) PASS.
```

---

## 4. tester 검증 발주

### 4.1 회귀 PASS 검증

```bash
# 1. 신규 테스트 (12 케이스)
python -m pytest tests/unit/engine/test_v1_rejection_alarm.py -v

# 2. 사이클 52/54/55/56 회귀 가드
python -m pytest tests/unit/engine/test_sell_rejection.py \
                 tests/unit/engine/test_b1_market_closed_zombie_block.py \
                 tests/unit/engine/test_cycle54_nxt_downgrade_emit_cap.py \
                 tests/unit/engine/test_daily_emit_cap.py -v

# 3. 백엔드 전체 회귀 (베이스라인 1748 PASS)
python -m pytest -q
```

**합격 기준**:
- 신규 12 케이스 PASS
- 기존 4 파일 회귀 PASS
- 백엔드 전체 PASS 카운트 = 1748 + 12 = 1760 (또는 사이클 56 PASS 카운트 + 12)

### 4.2 매매 안전성 검증

- **사이클 55 R-1 시나리오 재현**: `register_market_closed` 호출 1회 → `is_blocked` True (TTL 보존). 알람 발화 안 됨 (1회 < 5).
- **사이클 52 B-1 시나리오 재현**: `register_market_closed` 호출 6회 (10분 내) → 6회째 알람 발화. positions 보존 + TTL 미경과 보존 (기존 동작 100% 보존).
- **사이클 54 NXT downgrade**: 영향 없음 (별 모듈).
- **사이클 56 DailyEmitCap**: `_logged_today` 동작 영향 없음 (`_append_history` 는 cap 무관).

### 4.3 운영 시나리오 검증 (운영 데이터 기반, 사이클 57 적용 후 1~2 영업일)

| 시나리오 | 기대 동작 | 검증 SQL |
|---------|----------|---------|
| 정상 매매 (당일 거부 0~3건) | 알람 0건 | `SELECT COUNT(*) FROM system_logs WHERE level='CRITICAL' AND message LIKE '[매도거부폭주]%'` |
| 일시 KIS 장애 (10분 내 6건) | 알람 1건 | `SELECT * FROM system_logs WHERE message LIKE '[매도거부폭주]%ticker={t}%'` |
| 좀비 사고 (30분 지속) | 알람 2건 (0분 + 30분) | 같은 ticker 알람 2건 (cooldown 정확성) |

---

## 5. team-leader 종료 검수

### 5.1 종료 조건

- [ ] tdd-engineer Red 단계 — 12 케이스 작성 + 실패 확인
- [ ] backend-dev Green 단계 — `_maybe_emit_burst_alarm` 구현 + 12 케이스 PASS
- [ ] tester 회귀 검증 — 사이클 52/54/55/56 + 전체 백엔드 PASS
- [ ] CLAUDE.md 갱신 — `src/engine/CLAUDE.md` 의 `sell_rejection.py` 행에 사이클 57 V-1 표기
- [ ] `_workspace/00_leader_trading_rules.md` 갱신 — 매도 거부 알람 정책 명세
- [ ] `docs/HARNESS_CHANGELOG.md` 갱신 — 사이클 57 행 추가

### 5.2 후속 사이클 후보

- **사이클 58+**: 운영 1주 데이터 수집 후 임계 5건이 과민/둔감 여부 판정. 필요 시 domain-expert 자문 + 임계 조정.
- **사이클 59+**: 외부 채널 통합 (Slack webhook + `system_config.notification_webhook_url` 신설). D-3-a 의 후속 카드.
- **사이클 60+**: 다중 임계 (D-1-d 옵션) — WARNING 5건 + CRITICAL 50건 분리 검토.

---

## 6. 다음 액션 — **자동 진행 (사용자 확인 불필요)**

**판단 근거**:
1. **D-1 ~ D-7 모두 team-leader 단독 결정 완료** — 사용자 확인 의뢰 항목 0.
2. **위험 등급 LOW** — 매매 hot path 분기 변경 0, registry/positions 의존성 추가 0, 외부 채널 통합 0.
3. **사이클 55 R-1 / 56 인프라 위에 hook 추가** — *행위 보존* 확실.
4. **사용자 메시지 명시**: "발주서 작성을 부탁드립니다" + "결정 포인트 정리 부탁드립니다" — 발주서 + 결정 작성 완료가 사용자 요구의 종료점. 자동 TDD 사이클 진입은 사용자 후속 명시 시 시작.

**진행 절차**:
1. 본 발주서 산출 완료 (현재)
2. 사용자 검토 + "사이클 57 TDD 진입" 명시 시 → `tdd-cycle` 스킬 호출 → tdd-engineer Red 단계 발주
3. Red 단계 완료 → backend-dev Green → tester 검증 → team-leader 종료 검수
4. 사용자 commit 명시 시 → 사이클 57 단일 commit (위 3.4 메시지)

---

## 부록 A — domain-expert Q5(c) 권고 메시지 포맷 vs 본 사이클 채택

| 항목 | domain-expert 권고 | 본 사이클 채택 | 사유 |
|------|------------------|---------------|------|
| KST timestamp | ✓ | ✓ | 보존 |
| ticker | ✓ | ✓ | 보존 |
| 최근 N분 거부 횟수 | ✓ (10분 N건) | ✓ (10분, count=N) | 보존 + 임계 명시 (threshold=5) |
| 거부 코드 분포 | ✓ (APBK0918 (38) / APBK1943 (9)) | ✓ (reasons=market_closed:4, market_order_disallowed:2) | **변경**: msg_cd 대신 reason 분포 (RejectionEvent.reason 필드 활용, msg_cd 다양성 흡수) |
| 마지막 거부 메시지 | ✓ | ✓ (last_msg_cd + last_msg1) | 보존 + 분리 (cd/msg1 따로) |
| 현재 보유 (수량/평단/손익) | ✓ | **✗ 제외** | D-4-b: tracker 독립성 보존, registry 의존 회피. 운영자가 추가 조사 |
| positions 상태 (TTL 정보) | ✓ | **✗ 제외** | D-4-b 동일 |
| 권장 행동 (MTS 수동 매도 검토) | ✓ | **✗ 제외** | D-4-b: 알람은 *통보* 책임, *행동 권고* 는 운영 매뉴얼 (docs/) 책임 |

**변경 사유 보강**:
- domain-expert 권고는 *완성된 알람 메시지 이상형* — 실제 구현은 tracker 책임 범위 / 의존성 제약 / 본 사이클 LOW 위험 보존 우선.
- "현재 보유 / 권장 행동" 정보는 운영자가 system_logs CRITICAL 발화 *수신 직후* 프론트 `/positions` + `/trade-history` 조회로 추가 수집 가능. 알람 메시지에 포함은 *정보 중복* + *tracker 책임 외*.

---

## 부록 B — 사이클 분류 (행위 보존 / 가시화 / 행위 변경)

| 사이클 | 분류 | 의미 |
|--------|------|------|
| 49 | 행위 변경 | VCP Pullback 매수 진입 임계 시정 |
| 51 | 행위 보존 (리팩토링) | `_boot` boot_manager 추출 |
| 52 | 행위 변경 (안전 게이트) | B-1 진입 차단 도입 |
| 53 | 가시화 | 로그 데이터 수집 정확성 |
| 54 | 가시화 (로그 cap) | NXT downgrade emit cap |
| 55 | 행위 보존 (리팩토링) | R-1 SellRejectionTracker 통합 |
| 56-A~D | 행위 보존 (리팩토링) | DailyEmitCap 제네릭 통합 |
| 56-E | 행위 보존 (리팩토링) | safe_write_log 헬퍼 |
| **57** | **가시화 (알람)** | **V-1 매도 거부 폭주 실시간 알람** |

**본 사이클 = 가시화 (관찰성/실시간 알람)** — 매매 hot path 분기 변경 0.
