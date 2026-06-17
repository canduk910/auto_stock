# 사이클 162 domain-expert 자문 산출물

발주: team-leader (사용자 결정 = 사이클 162 D + E 통합)
대상: 의제 D (익일청산큐 DB 영속화) + 의제 E (동시호가 시간대 stale 회피)
회신 형식: 의제별 권고 + 채택안 + 회귀 가드 항목

---

## 의제 D — 익일청산큐 DB 영속화

### 사고 사례

알테오젠 (196170, VB) + 알지노믹스 (476830, LTV) 6/17 15:20 강제청산 누락. 근본 원인 후보:
1. `_pending_next_day_clear: set[tuple[ticker, strategy_id]]` 메모리 휘발 (EC2 재기동 시)
2. 15:21:48 KST stale_watcher = subscribed=10 fresh=0 stale=10 ratio=0% → 동시호가 시간대 stale 오판 (의제 E)

### Phase 1 진단 (현재 chain)

`_pending_next_day_clear` 영역 = scheduler 메모리 단독:
- 등록 사이트 4건 (scheduler `_execute_next_day_clear` 1193/1223 + order_engine 매도 거부 NXT 폴백 + sell_rejection NXT 익일 전환)
- 사용 사이트 11건 (drain 1296, scanner protected, stale_watcher_core HIGH, universe_guard, recovery, scheduler R4 영역)
- clear 사이트 1건 (`_reset_daily_state` 3554)
- EC2 재기동 = 메모리 휘발 = drain 시 0건 = 강제청산 영구 누락

### 권고 — 옵션 A (DB 테이블 신규)

신규 테이블 `pending_next_day_clear`:
```sql
CREATE TABLE IF NOT EXISTS pending_next_day_clear (
    target_date DATE NOT NULL,
    ticker      VARCHAR(10) NOT NULL,
    strategy_id VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason      VARCHAR(50) NOT NULL DEFAULT 'unknown',
    PRIMARY KEY (target_date, ticker, strategy_id)
);
CREATE INDEX IF NOT EXISTS idx_pending_ndc_target_date
    ON pending_next_day_clear (target_date);
```

채택 사유:
- DB = 단일 진실 원천 (uvicorn 단일 워커 + EC2 재기동 무관)
- target_date PK = 다음 영업일 drain 후 즉시 DELETE 가능
- ticker + strategy_id 복합 PK = 동일 종목 여러 전략 보유 시 보존

### 동기화 chain

- 등록 (4 사이트): `_pending_next_day_clear.add((ticker, sid))` 직후 `await save_pending_ndc(target_date, ticker, sid, reason)` 동기 호출. 실패 graceful (사이클 88 G-REJECT 답습) + WARNING.
- drain 완료 (`_drain_pending_next_day_clear` finally 영역): `await delete_pending_ndc(target_date, ticker, sid)`.
- `_reset_daily_state` 동행: DB 작업 0건 (다음 영업일 _boot 영역 새 target_date 로드 = 자연 정리).
- `_boot()` 영역 신규 hook: `restored = await load_pending_ndc(today)` → `self._pending_next_day_clear.update(restored)`. boot_manager 마지막 단계 (사이클 149 VI seed 답습 위치). 실패 graceful + WARNING.

### 동시성 / race

- uvicorn 단일 워커 + Supabase async = race 무. `asyncio.Lock` 불필요.
- 등록/삭제 모두 DB UPSERT/DELETE idempotent = 중복 호출 안전.

### 매매 안전성

- 익일청산 의무 영구 보존 (EC2 재기동 무관)
- risk/order_engine/realtime/auth 변경 0
- 사이클 32 R4 보유/익일청산 절대 보호 영속 (DB load 후 메모리 set 동일)

---

## 의제 E — 동시호가 시간대 stale 회피

### 사고 사례

6/17 15:21:48 KST stale_watcher = subscribed=10 fresh=0 stale=10 ratio=0% → 5분 주기 재구독 시도 반복 = KIS LMS chain 위험. 정상 동시호가 시간대 영역 잘못된 처리.

### KIS MCP 정본 (H0UNMKO0 응답 10 컬럼)

`market_status_total` 정본:
- TRHT_YN, TR_SUSP_REAS_CNTT
- **MKOP_CLS_CODE** (장운영 구분 코드) — 핵심
- ANTC_MKOP_CLS_CODE (예상 장운영 구분 코드)
- MRKT_TRTM_CLS_CODE (임의연장구분코드)
- DIVI_APP_CLS_CODE (동시호가배분처리구분코드)
- ISCD_STAT_CLS_CODE (종목상태구분코드)
- VI_CLS_CODE, OVTM_VI_CLS_CODE
- EXCH_CLS_CODE

기존 `session.py:188` docstring 매핑 (사이클 16 기록):
- 110: 장전 동시호가 개시
- 112: 장개시 (09:00)
- **121: 장후 동시호가 개시**
- 129: 장마감 (15:30)
- 130-139: 장개시전시간외 (08:00-09:00)
- 140-149: 시간외 종가 매매 (15:30-16:00)
- 150-159: 시간외 단일가 (16:00-18:00)

**동시호가 코드값 = `{110, 121}` (정규장 진입 *전*/장 종료 *후* 호가만 접수 + 체결 부재)**

추가 확정:
- 보수적 채택 = MKOP_CLS_CODE 미수신 시 **시간 기반 폴백** = KRX 동시호가 시간대 `08:30~09:00` ∪ `15:20~15:30`
- 시간 기반 폴백이 정본 = H0UNMKO0 미수신 환경 (모의 VTS) 보호 + 사이클 28 fallback 패턴 답습

### 권고 — 옵션 B (시간 기반 + 코드 기반 OR 통합)

`session.py::SessionTracker` 영역 신규 메서드:
```python
def is_call_auction_now(self, now: datetime | None = None) -> bool:
    """동시호가 시간대 판정 (시간 + 코드 OR).

    코드 기반 (H0UNMKO0 정본): MKOP_CLS_CODE in {"110", "121"}
    시간 기반 (폴백): 08:30~09:00 ∪ 15:20~15:30
    """
```

`stale_watcher_core.py::check_and_resubscribe_stale` 영역 hook 추가:
- `_is_within_grace` + `_market_op_skip` 패턴 답습 = `_call_auction_skip` 신규 가드
- True 시 = stale 종목 *전체* skip + WARNING 1행 `[stale_skip_call_auction]`
- 시간 기반 폴백 = sessiontracker import 시점에 1회 호출 (성능 무영향)

### 동시호가 코드값 매트릭스

| MKOP_CLS_CODE | 의미 | 체결 가능 | stale 회피 |
|---------------|------|-----------|------------|
| 110 | 장전 동시호가 (08:30~09:00) | ❌ | ✅ |
| 112 | 장개시 (09:00~) | ✅ | ❌ |
| 121 | 장후 동시호가 (15:20~15:30) | ❌ | ✅ |
| 129 | 장마감 (15:30) | ❌ | (시간외 분기) |
| 130~139 | 장개시전시간외 | ⚠️ | ❌ |
| 140~149 | 시간외 종가 매매 | ⚠️ | ❌ |
| 150~159 | 시간외 단일가 | ⚠️ | ❌ |

채택 = `{110, 121}` 단독 + 시간 기반 폴백.

### 매매 안전성

- stale 판정 *지연*만 = 사이클 38 명문화 영속
- risk/order_engine 변경 0
- 사이클 29 005935 보호 영속 = 첫 시세 입수 *후* 영역 = `_is_within_grace` 패턴 답습 (회복 케이스 보장)
- 사이클 135 grace + 사이클 149 VI 영역 영속

### 적용 효과

- 6/17 15:21:48 사고 영역 = stale 종목 *전체* skip = KIS LMS chain 위험 차단
- 6/18 08:30~09:00 동시호가 시간대 = stale skip = 09:00 장 개시 후 자연 회복

---

## 회귀 가드 매트릭스 (≥10 케이스 의무)

| ID | 영역 | 위험 |
|----|------|------|
| G-162-D-1 | migration 038 pending_next_day_clear DDL | HIGH |
| G-162-D-2 | `src/db/pending_next_day_clear.py` CRUD 4 함수 | HIGH |
| G-162-D-3 | `_execute_next_day_clear` 등록 → DB save 동기 | HIGH |
| G-162-D-4 | `_drain_pending_next_day_clear` finally → DB delete | HIGH |
| G-162-D-5 | `boot()` 영역 DB load → 메모리 set restore | HIGH |
| G-162-D-6 | graceful = DB 실패 시 메모리 set 보존 (no-op) | MEDIUM |
| G-162-E-1 | `SessionTracker.is_call_auction_now` 시간 + 코드 OR | HIGH |
| G-162-E-2 | MKOP_CLS_CODE in {110, 121} 채택 | HIGH |
| G-162-E-3 | `check_and_resubscribe_stale` `_call_auction_skip` hook | HIGH |
| G-162-E-4 | 동시호가 시간대 전체 skip + WARNING 1행 | MEDIUM |
| G-162-E-5 | 09:00 / 15:30 경계 정확 (8:59:59 / 15:30:00 분기) | MEDIUM |
| G-162-SAFETY-1 | risk/order_engine/realtime/auth 변경 0 | HIGH |
| G-162-SAFETY-2 | 사이클 29 005935 보호 영속 (첫 시세 후 회복) | HIGH |

---

## 결론

옵션 A (의제 D DB 테이블 신규) + 옵션 B (의제 E 시간 + 코드 OR 통합) 채택.
TDD Red → Green → tester verify chain 진행.
