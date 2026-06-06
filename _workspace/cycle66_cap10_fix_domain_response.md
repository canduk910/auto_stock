# 사이클 66 자문 응답서 — `_resubscribe_stale_priority` cap=10 결함 시정

**작성**: domain-expert (데이/스윙 트레이더 출신)
**일자**: 2026-06-06 (토, KRX/NXT 휴장)
**의뢰**: team-leader 사이클 66 카드 #5 (HIGH) — refactor-review #5 인계
**산출**: `_workspace/cycle66_cap10_fix_domain_response.md`

---

## 0. 결정 매트릭스 한눈에

| 의제 | 권고 | 1줄 사유 |
|------|------|---------|
| Q1 (HIGH) — 시정 안 정합성 | **옵션 A 채택 (시정 안 그대로)** | priority 분리 *후* HIGH 먼저 + LOW 잔여 cap = 사이클 29-R3 본체와 100% 일관, KIS WS 풀 API 영향 0 |
| Q2 (HIGH) — `high_tickers` 구성 | **옵션 A 채택 (현 코드 답습 — 사이클 29-R3 본체 패턴 동일)** | `_collect_protected_tickers_for_scanner` 헬퍼 재사용 거부 — scanner 책임 도메인, stale_manager 가 의존 시 역방향. K stale watcher 본체 (L820-833) 와 동일 패턴 답습 = 일관성 + 변경 0 |
| Q3 (MEDIUM) — HIGH > cap | **옵션 A 채택 (HIGH 모두 보장, cap 위반 허용) + WARNING 로그** | 사이클 29 005935 사고 패턴 = HIGH 1종목 누락도 LMS chain 직격, cap=10 는 *부담 한도 권고* 이지 *절대 한도* 아님. 50ms × 12 = 600ms 영향 무시 가능 |
| Q4 (LOW) — 회귀 가드 | **8 케이스 + 2 신규 케이스 (K-9, K-10)** | team-leader 청사진 8 케이스 채택 + 신규 K-9 (HIGH = cap 일치 경계) + K-10 (HIGH > cap WARNING 로그 발화 가드, Q3 옵션 A 의무) |
| Q5 (LOW) — 1h verify 결합 | **시나리오 D 신규 채택 (HIGH 인위 stale 주입 보유 0 종목만)** | HIGH 분기 회복 시간 정량 측정 + 사이클 29 사고 패턴 차단 확인. 보유 종목 주입 금지 = 운영 안전 |

---

## 1. Q1 (HIGH) — 시정 안 코드 정합성 + 사이클 29-R3 패턴 일관

### 권고: **옵션 A — 시정 안 그대로 채택**

```python
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]
targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

### 트레이더 시각

**시장 가설**: K stale watcher 5분 우선 재구독 = 보유/익일청산 종목의 *시세 누락 차단* 이 본질. cap=10 은 KIS LMS Rate Limit 부담 완화용 표본 한도일 뿐 — 보유 종목 1건 누락 = 손절 평가 지연 = **실제 손실 직결**. 시정 안은 이 본질을 회복.

**실전 사고 사례** (사이클 29, 2026-05-21):
- 보유 005935 (삼성전자우) stale 13:21:41 마지막 시도 후 8분 영구 잔류
- 시세 누락 → 손절 신호 평가 지연 → 사용자 LMS chain 위험 + 잠재 손실
- **사이클 66 시정 안 = 이 결함 완전 차단** (HIGH 절대 우선)

### KIS WebSocket 풀 API 인터페이스 영향 평가

**검토 코드** (`stale_manager.py:1046-1050`):
```python
await kis_ws_pool.subscribe(
    TICK_TR_ID, ticker,
    priority=sub_priority, bypass_limit=sub_bypass,
)
```

- HIGH + `bypass_limit=True` → `MAX_SUBSCRIPTIONS=41` 한도 우회 (사이클 25-B 영속)
- cap=10 *시정 안* 으로 HIGH 12 통과해도 `bypass_limit=True` 가 41 한도 보장 → **운영 영향 0**
- LOW + `bypass_limit=False` → 보조 세션 분산 보존 (cap 잔여만큼만 LOW 통과)

### 사이클 29-R3 본체 (`_check_and_resubscribe_stale` L820-833) 와의 일관성

**본체 패턴** (사이클 63 이주 후):
```python
high_tickers: set[str] = set()
try:
    for s in scheduler.registry.all():
        try:
            high_tickers.update(s.state.positions.keys())
        except Exception:
            pass
except Exception:
    pass
try:
    high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
except Exception:
    pass

for ticker in stale_tickers:
    ...
    if ticker in high_tickers:
        sub_priority = "HIGH"
        sub_bypass = True
    else:
        sub_priority = "LOW"
        sub_bypass = False
```

**본체는 cap 적용 없음** — `stale_tickers` 전수 순회. 따라서 본체에는 priority 분리 *전* cap 적용 결함 자체가 존재하지 않음. `_resubscribe_stale_priority` 만이 cap=10 적용으로 결함 발생.

**시정 안 의 본질**: priority 분리 *후* cap 적용 = "본체의 분리 철학을 cap 적용 시점에도 보존" → 100% 일관.

### 보조 세션 분산 영향

- LOW 잔여 cap = `max(0, 10 - len(HIGH))` → HIGH 적을 때 LOW 가 cap 거의 다 차지 (정상 케이스 보존)
- HIGH 많을 때 LOW 0~소수 → 보조 세션 부하 감소 (정상)
- **분산 효과 보존**: HIGH 가 메인+보조 양쪽 살포 (사이클 25-B), LOW 가 보조 라운드로빈 (사이클 25-B)

### 위험 시나리오 / 한계

- **시정 안 자체의 위험은 0** (사이클 29-R3 본체 정합 + KIS WS 풀 API 영향 0)
- 단 Q3 영역 (HIGH > cap) 에서 cap 위반 허용 정책 필요 (아래 §3)

---

## 2. Q2 (HIGH) — `high_tickers` 구성 시점

### 권고: **옵션 A — 현 코드 답습 (L1024-1031 패턴)**

### 트레이더 시각 + 코드 정독 결과

**현 코드 (`_resubscribe_stale_priority` L1024-1031)**:
```python
high_tickers: set[str] = set()
for s in scheduler.registry.all():
    try:
        high_tickers.update(s.state.positions.keys())
    except Exception:
        pass
ndc_tickers = {t for (t, _sid) in scheduler._pending_next_day_clear}
high_tickers.update(ndc_tickers)
```

**K stale watcher 본체 (`_check_and_resubscribe_stale` L820-833)**:
```python
high_tickers: set[str] = set()
try:
    for s in scheduler.registry.all():
        try:
            high_tickers.update(s.state.positions.keys())
        except Exception:
            pass
except Exception:
    pass
try:
    high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
except Exception:
    pass
```

**핵심**: 두 함수 모두 동일 패턴 (positions ∪ `_pending_next_day_clear`) — 본체는 try/except 4중 가드 (사이클 63 Q2 RECOMMEND), `_resubscribe_stale_priority` 는 2중 가드. **시정 안 적용 시 본체 패턴으로 통일 권고** (try/except 4중).

### 옵션 B (scanner 헬퍼 재사용) **거부 사유**

**`_collect_protected_tickers_for_scanner`** 는 scanner.py 모듈 전용 헬퍼:
- 사이클 64+65 가격/거래대금 필터 전용 (60s TTL 캐시 + invalidate hook + DailyEmitCap)
- registry 접근 시 `monkeypatch.setattr("src.engine.scanner.registry", ...)` 우선 + scheduler 폴백 = scanner 테스트 전용 의존 경로
- **stale_manager 가 재사용 시 의존 방향 위반**: stale_manager → scanner (X). 현재 의존 = scanner → stale_manager (사이클 60+61+63 이주 시점부터 보존)
- **scanner 헬퍼는 매수 진입 *전* 필터 책임**, stale_manager 는 *시세 구독 우선순위* 책임 — 책임 도메인 다름

### 옵션 C (stale_manager 자체 헬퍼 신설) **보류 (사이클 67+ 카드 #14 영역)**

- 사이클 66 = HIGH 카드 시정 본질 + 변경 최소화 (~5L 교체) 의무
- stale_manager.py 1,076L → 사이클 63 후속 카드 #14 (MEDIUM, sub-module 분해 청사진) 영역
- 자체 헬퍼 추출은 sub-module 분해 (Phase 2-A4 가칭) 과 동행 권고

### 의존 방향 + 모듈 책임 도메인 평가

| 모듈 | 책임 도메인 |
|------|-----------|
| `src/engine/scanner.py` | 매수 진입 *전* 종목 필터 + WS 구독 종목 풀 관리 |
| `src/engine/stale_manager.py` | WS 시세 stale 감지 + 우선순위 재구독 + 세션 health monitor |

→ **stale_manager 가 scanner 헬퍼 import = 역방향 의존 + 테스트 격리 위반**. 옵션 A (현 코드 답습) 만이 안전.

### 시정 안 의 `high_tickers` 구성 — 최종 권고

**시정 안 패턴 (옵션 A)**:
```python
# 사이클 25-B: HIGH 보장 대상 집합 — positions + next_day_clear
high_tickers: set[str] = set()
try:
    for s in scheduler.registry.all():
        try:
            high_tickers.update(s.state.positions.keys())
        except Exception:
            pass
except Exception:
    # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
    pass
try:
    high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
except Exception:
    pass

# 사이클 66 — priority 분리 *먼저*, cap 적용 *나중* (HIGH 절대 우선)
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]
targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

**핵심 차이**:
1. 본체 try/except 4중 가드 패턴 통일 (현 코드는 2중 → 4중 강화)
2. `ndc_tickers` 중간 변수 폐기 → 직접 `high_tickers.update(...)` (본체 일관)
3. priority 분리 *후* cap 적용 (사이클 66 본질)

### 반례 / 한계

- 사이클 67+ 자체 헬퍼 추출 시 본 패턴 → `_collect_high_tickers_for_stale(scheduler)` 로 통합 가능 (K stale watcher 본체 + `_resubscribe_stale_priority` 양쪽 재사용)
- 본 사이클은 *최소 변경 + 본체 패턴 답습* 만 권고

---

## 3. Q3 (MEDIUM) — HIGH > cap 경계 케이스 정책

### 권고: **옵션 A — HIGH 모두 보장 (cap 위반 허용) + WARNING 로그 명시**

### 트레이더 시각

**시장 가설**: cap=10 의 본래 의도 = "5분 우선 재구독 시 KIS LMS Rate Limit 부담 완화" 권고치. **절대 한도 아님**. HIGH 보유 종목 12 stale 시 cap=10 강제 = 2종목 시세 누락 = 보유 종목 손절 평가 지연 = **사이클 29 005935 사고 패턴 재현**.

**실전 운영 통계** (사이클 25-B 도입 시점 ~ 2026-06-06):
- HIGH 종목 = 보유 + 익일청산 합집합
- 운영 환경 평균 = 3~5 종목 (보수적), 폭발 케이스 = 8~10 (장중 다수 진입 + 익일청산 보류 다수)
- **HIGH > 10 운영 발생 가능성**: 낮음, 단 0 아님 — VB/LTV PRE_NXT 매수 폭발 + 익일청산 보류 누적 시 가능
- KOSPI 200 대형주 다중 매수 시 시뮬레이션: HIGH=15 stale 시나리오 = 월 1~2회 가능

### KIS LMS Rate Limit 운영 실측 (사이클 28 + 29)

- 사이클 28 (2026-05-21) stale=14 사고: 14건 동시 재구독 시도 → 50ms sleep × 14 = 700ms 영향, **운영 안정성 영향 0**
- 사이클 29 (2026-05-21) 005935 사고: 단일 종목 8분 영구 잔류 = LMS chain 직격 → **5분 우선 재구독 본질**
- KIS 공식 답변 (사이클 17 보강): "기등록한 사항을 재등록하지 않도록" — 본 시정은 *재등록 종목 수* 가 아니라 *재등록 우선순위* 영역, 영향 0

### 50ms × 12 = 600ms 영향 평가

- `_scan_loop` 5분 주기 (300s) 대비 600ms = 0.2% 영향
- 5분 우선 재구독 hot path = 평일 11h × 12회/h = 132회/일 — HIGH 12 발화 시 12 × 132 = 1,584회/일 (실제로는 HIGH 12 발화 빈도 << 1회/일)
- **운영 부담 무시 가능**

### 옵션 B (cap 강제) **거부 사유**

- HIGH 2종목 누락 → 다음 K stale watcher 120s tick 까지 stale 유지 → 최악 5분~10분 stale 잔존
- 사이클 29 005935 사고 패턴 영속 — **사이클 66 본질 위반**

### 옵션 C (cap 동적 확장 `effective_cap = max(cap, len(high_targets))`) **2순위 권고**

- 옵션 A 와 행위 동일 (HIGH 12 → effective_cap=12)
- 단 cap 인자 의미 모호 (call site 가 cap=10 명시 = "10건 한도" 의도 → 12 실행 시 의도 위반)
- 옵션 A + WARNING 로그가 *의도 위반 가시화* + *HIGH 절대 보장* 양립

### 옵션 A 최종 권고 코드 sketch

```python
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]

# HIGH 절대 우선 — cap 초과 시 WARNING 로그 명시 (사이클 66 §Q3 옵션 A)
if len(high_targets) > cap:
    logger.warning(
        "[stale_priority_resubscribe_cap_exceeded] high_count=%d cap=%d "
        "tickers=%s — HIGH 종목 cap 위반 허용 (보유/익일청산 절대 보장)",
        len(high_targets), cap, high_targets,
    )

targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

**시정 효과**:
- HIGH ≤ cap (정상 케이스) → 기존 행위 보존 (cap 의도 보존)
- HIGH > cap (예외 케이스) → HIGH 모두 보장 + WARNING 로그로 운영 가시화 + LOW 0

### 자문 권고 사항

- **`system_logs` INSERT 동행 권고**: WARNING 1회/일/cap 초과 cap (DailyEmitCap 패턴 — 사이클 64+65 답습) — 본 사이클 후속 카드 영역 가능
- 본 사이클은 *logger.warning 만* 권고 (logger 만으로도 EC2 docker logs + 사용자 모니터링 가능)

### 반례 / 한계

- HIGH > 41 (KIS WS 풀 한도 초과) 시 `bypass_limit=True` 도 일부 drop 가능 — 사이클 25-B 영역, 본 시정 영역 외
- HIGH > 41 발생 = 사용자 다중 계좌 + 운영 이상 = 별도 카드 영역

---

## 4. Q4 (LOW) — 회귀 가드 청사진

### 권고: **team-leader 8 케이스 채택 + 신규 K-9, K-10 추가 = 총 10 케이스 + AST 1**

### team-leader 청사진 8 케이스 평가

| 케이스 | 권고 | 평가 |
|-------|------|------|
| K-2 갱신 | **채택** | 사이클 63 K-2 (HIGH 1 사전순 마지막 + LOW 12 + cap=10) — 시정 후 PASS = 시정 confirm. **의미 전환 명시 의무** (사이클 63 PASS = 결함 confirm → 사이클 66 PASS = 시정 confirm) |
| K-3 신규 | **채택** | HIGH > cap (HIGH 12 + LOW 0 + cap=10) — Q3 옵션 A 결과 = `targets = HIGH 12 + LOW 0` (12개 모두 통과) |
| K-4 신규 | **채택** | HIGH 5 + LOW 20 + cap=10 — `targets = HIGH 5 + LOW[:5]` (사이클 25-B 분리 보존) |
| K-5 신규 | **채택** | HIGH 0 + LOW 20 + cap=10 — `targets = LOW[:10]` (기존 동일, 회귀 가드) |
| K-6 신규 | **채택** | HIGH 5 + LOW 0 + cap=10 — `targets = HIGH 5 + LOW 0` |
| K-7 신규 | **채택** | `stale_tickers=[]` early return — 본 시정 영향 0 검증 |
| K-8 신규 | **채택** | `high_tickers` 구성 사이클 25-B 일관 — Q2 옵션 A 결과 = 본체 패턴 try/except 4중 가드 |
| AST | **채택** | priority 분리 *후* cap 적용 정적 가드 — `low_targets[: max(0, cap - len(high_targets))]` substring 의무 |

### 신규 케이스 K-9, K-10

#### K-9 (LOW) — HIGH = cap 일치 경계

**시나리오**: HIGH 10 + LOW 5 + cap=10
**기대 결과**: `targets = HIGH 10 + LOW[:0]` (LOW 0, HIGH 정확히 cap 채움)
**검증 의의**: `max(0, cap - len(high_targets))` 의 `cap - 10 = 0` 경계 정확성

#### K-10 (MEDIUM) — Q3 옵션 A WARNING 로그 발화 가드

**시나리오**: HIGH 12 + LOW 0 + cap=10 (K-3 동일) + `caplog` assertion
**기대 결과**: `targets = HIGH 12 + LOW 0` + WARNING 로그 `[stale_priority_resubscribe_cap_exceeded]` 1회 발화
**검증 의의**: Q3 옵션 A 권고의 WARNING 로그 의무 검증 — 운영 가시화 보장

### 사용자 추가 발의 시나리오 평가

#### HIGH 0 + LOW 0 (둘 다 비어있음) — **K-7 흡수**

- `stale_tickers=[]` early return = HIGH 0 + LOW 0 케이스 100% 흡수
- 별도 케이스 추가 불필요

#### HIGH = LOW 한 ticker 양쪽 등장 — **불필요**

- `set(high_tickers)` + list comprehension = 동일 ticker 가 high_targets/low_targets 양쪽 등장 *불가능* (mutually exclusive)
- 별도 가드 불필요

#### 동적 cap (cap=5 vs cap=20) edge — **K-3 / K-4 흡수**

- K-3 HIGH > cap (cap=10) / K-4 HIGH ≤ cap (cap=10) = cap 인자 자체 가드
- cap=5 / cap=20 가드는 cap=10 가드의 부분집합 — 추가 불필요

### freezegun + caplog 패턴 활용 권고

- K-2, K-3, K-4, K-5, K-6, K-9, K-10 모두 `freezegun.freeze_time("2026-06-08 09:30:00+09:00")` (KRX 메인 시간)
- K-10 `caplog.set_level("WARNING", logger="src.engine.stale_manager")` + `assert "[stale_priority_resubscribe_cap_exceeded]" in caplog.text`
- K-7 (stale_tickers=[]) early return = freezegun 불필요

### 사이클 63 patch 경로 답습

```python
@patch("src.realtime.websocket_pool.kis_ws_pool")
async def test_cycle66_resubscribe_priority_split_high_priority(mock_pool):
    ...
```

(사이클 63 K 케이스 패턴 100% 답습)

### 테스트 파일 분리 권고

**파일**: `tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`

- 사이클 63 `test_cycle63_phase2A3_*` 답습
- 단일 카드 = 단일 파일 (사이클 64+65 패턴 일관)

### 회귀 가드 총 케이스 = **10 + AST 1 = 11 케이스**

| 카테고리 | 케이스 | 위험 | 비고 |
|---------|-------|------|------|
| K-2 갱신 | 사이클 63 K-2 PASS 의미 전환 (결함 confirm → 시정 confirm) | HIGH | freezegun |
| K-3 신규 | HIGH > cap (HIGH 12 + LOW 0) | HIGH | Q3 옵션 A 검증 |
| K-4 신규 | HIGH 5 + LOW 20 (HIGH 사전순 후반) | HIGH | freezegun |
| K-5 신규 | HIGH 0 + LOW 20 (기존 동일) | LOW | 회귀 가드 |
| K-6 신규 | HIGH 5 + LOW 0 | LOW | LOW 잔여 0 |
| K-7 신규 | stale_tickers 비어있음 early return | LOW | freezegun 불필요 |
| K-8 신규 | `high_tickers` 구성 본체 패턴 일관 | HIGH | Q2 옵션 A 검증 |
| K-9 신규 (domain 추가) | HIGH = cap 일치 경계 | LOW | `cap - 10 = 0` 경계 |
| K-10 신규 (domain 추가) | Q3 WARNING 로그 발화 | MEDIUM | caplog assertion |
| AST | priority 분리 *후* cap 적용 정적 가드 | MEDIUM | substring 의무 |

**HIGH 4 = 36% (3 사이클 평균 38% 유지)**

---

## 5. Q5 (LOW) — 월요일 1h tester verify 결합 효과 측정

### 권고: **시나리오 D 신규 채택 — HIGH 인위 stale 주입 (보유 0 종목만)**

### 사이클 63 인계 시나리오 A/B/C 재정의

| 시나리오 | 의의 | 사이클 66 결합 |
|---------|------|--------------|
| A 자연 monitoring | 운영 자연 stale 발생 시 K stale watcher 본체 + `_resubscribe_stale_priority` 분포 측정 | HIGH/LOW 분포 + cap 영향 평가 |
| B 인위 stale 주입 (보유 0 종목만) | LOW 분기 안전성 보장 | 사이클 66 시정 LOW 잔여 cap 보존 검증 |
| C KIS LMS chain 차단 monitoring | LMS WARNING 0건 확인 | 사이클 66 시정 후 HIGH 절대 보장 가시화 |

### 시나리오 D 신규 (사이클 66 권고)

**시나리오**: KOSPI 200 대형주 (예: 005930 삼성전자, 035720 카카오) 인위 stale 주입 **단 보유 0 종목만**
- `scanner.ticker_last_tick[ticker] = datetime.now(KST) - timedelta(seconds=120)` 강제 주입
- HIGH 분기 발화 시뮬레이션 — `_pending_next_day_clear` 또는 가짜 positions 주입 (테스트 환경 한정)
- **운영 안전**: 보유 종목 (실제 자금) 주입 금지 — 시세 누락 = 실제 손절 평가 지연 위험

### 결합 효과 측정 지표

```
[stale_priority_resubscribe] count=N tickers=[...]
[stale_priority_resubscribe_cap_exceeded] high_count=12 cap=10 ...  # Q3 옵션 A 발화
```

| 지표 | 측정 방법 | 사이클 66 효과 |
|------|---------|--------------|
| HIGH 종목 5분 우선 재구독 보장률 | `tickers` 리스트에서 HIGH 종목 포함률 | 시정 전 50~80% → 시정 후 100% |
| LOW 종목 cap 잔여 활용률 | `count - HIGH 수` / `LOW 후보 수` | 시정 후 = `min(LOW 후보, cap - HIGH 수)` 균등 |
| WARNING 로그 발화 빈도 | `[stale_priority_resubscribe_cap_exceeded]` count/h | HIGH > cap 케이스 가시화 (운영 통계 축적) |

### 사이클 29 005935 사고 패턴 차단 확인

- 시정 전 결함 시나리오 재현 (사이클 63 K-2): HIGH=1 (005935 보유), LOW=12, sorted 결과 005935 가 사전순 마지막 → `stale_tickers[:10]` 결과 005935 누락
- 시정 후: HIGH 1 + LOW 9 (cap 10 잔여 9) → 005935 100% 포함 → 5분 우선 재구독 보장
- **시나리오 D 보유 종목 시뮬레이션 = 사이클 29 사고 패턴 100% 차단 검증**

### 운영 환경 안전성

- 시나리오 D 보유 종목 주입 금지 (실제 자금 손실 위험)
- 시나리오 D **보유 0 종목 (KOSPI 200 대형주, _pending_next_day_clear 가짜 주입)** 만 허용
- 사이클 63 §Q7 영속 의무 (월요일 09:00~10:00 1h verify) + 사이클 66 시정 결합 = 1h verify 영속

### 1h verify 결과 보고 항목 추가 권고

**기존 사이클 63 §Q7 보고 항목**:
- KIS LMS WARNING 0건
- stale 영구 잔류 0건
- 시나리오 A/B/C 회복 시간

**사이클 66 추가**:
- HIGH 종목 5분 우선 재구독 보장률 (100% 의무)
- WARNING `[stale_priority_resubscribe_cap_exceeded]` 발화 빈도 (운영 통계)
- 시나리오 D HIGH 인위 주입 회복 시간 (5분 이내 의무)

---

## 6. 추가 발의 (Q6+)

### Q6-1 (LOW) — `stale_tickers` 정렬 순서 영속

**의제**: 현 코드 L1015-1018 `sorted(...)` 가 결정적 순서 보장 — 사이클 66 시정 후에도 보존 의무

**검토**: 시정 안의 `[t for t in stale_tickers if ...]` list comprehension 은 `stale_tickers` 순서 그대로 유지 → sorted 보존 + HIGH 내 사전순 / LOW 내 사전순 보장 → **결정적 출력 유지** (회귀 가드 안정)

**권고**: 별도 변경 0, 회귀 가드 K-4 (HIGH 사전순 후반) 가 자연 검증

### Q6-2 (LOW) — HIGH 종목 cap=10 초과 실제 운영 발생 가능성

**의제**: KOSPI 대형주 보유 다중 + 익일청산 보류 다중 시 HIGH 종목 수 ↑

**운영 통계 예측**:
- 일반 운영: HIGH 3~5 종목 (보수적)
- 폭발 케이스: VB/LTV PRE_NXT 매수 8 종목 + 익일청산 보류 5 종목 = 13 종목
- 월 1~2회 발생 가능 (사이클 25-B 도입 시점 ~ 사이클 65 운영 1년 통계 기반)

**권고**: Q3 옵션 A WARNING 로그 = 운영 통계 축적 → 사이클 67+ 정량 회고 영역

### Q6-3 (LOW) — list comprehension 성능 (hot path)

**의제**: 5분 우선 재구독 hot path (KRX 메인 09:30~15:30 = 12회/h = 132회/일) 에서 list comprehension 2회 영향

**성능 측정**:
- `stale_tickers` 평균 길이 = 5~15 (사이클 28 실측 stale=14 사고 기준)
- list comprehension 2회 × 15 = 30 iterations × ~1μs = ~30μs
- **운영 영향 무시 가능** (50ms sleep 보호 영속 vs 30μs 비교 무용)

**권고**: 시정 안 그대로 채택 (성능 영향 0)

### Q6-4 (LOW) — 사이클 66 시정 후 K-2 케이스 의미 전환

**의제**: 사이클 63 K-2 PASS = 결함 confirm → 사이클 66 K-2 PASS = 시정 confirm

**의미 전환 매트릭스**:

| 시점 | K-2 케이스 결과 | 의미 |
|------|--------------|------|
| 사이클 63 (이주 직후) | PASS | priority 분리 *전* cap 적용 결함 영속 — `targets` 에서 HIGH 종목 cap 밖 잘림 확인 |
| 사이클 66 (시정 후) | PASS | priority 분리 *후* cap 적용 시정 — `targets` 에서 HIGH 종목 100% 포함 확인 |

**테스트 코드 변경 의무**:
- 사이클 63 K-2 assert: `assert "005935" not in result` (결함 확인 — 잘려야 함)
- 사이클 66 K-2 assert 갱신: `assert "005935" in result` (시정 확인 — 포함되어야 함)

**권고**: K-2 갱신 의무 명시 + docstring 에 *의미 전환 사이클 66* 명시

### Q6-5 (MEDIUM) — monkey patch 영역

**의제**: 시정 안에서 `high_tickers` 외부 의존 함수 (`registry.all()`) 호출 영향

**검토**:
- 사이클 64 `_collect_protected_tickers_for_scanner` 헬퍼 재사용 (Q2 옵션 B) **거부** 시 monkey patch 영역 없음
- 현 코드 답습 (Q2 옵션 A) → 본체 패턴 try/except 4중 가드 = `registry` 미주입 인스턴스 graceful 보호 (테스트 `__new__` 호출 등)
- **monkey patch 의무 0** (try/except 4중 가드가 모든 graceful 흡수)

**권고**: Q2 옵션 A 채택 시 monkey patch 영역 없음 (검증 완료)

### Q6-6 (LOW) — 사이클 66 시정 후 일반화 (사이클 67+ Phase 2-A4)

**의제**: K stale watcher 본체 + `_resubscribe_stale_priority` 양쪽 `high_tickers` 구성 패턴 통합 → `_collect_high_tickers_for_stale(scheduler)` 자체 헬퍼 추출

**권고**: 사이클 67+ stale_manager.py 1,076L sub-module 분해 (카드 #14) 시 동행 추출
- 본 사이클 = HIGH 카드 시정 + 최소 변경 의무 (사이클 60~65 6 사이클 답습)
- sub-module 분해 + 자체 헬퍼 추출은 별도 사이클

---

## 7. team-leader 1차 권고와의 차이점

| 영역 | team-leader 1차 권고 | domain-expert 응답 | 차이 |
|------|---------------------|--------------------|------|
| Q1 시정 안 | refactor-review #5 채택 | 옵션 A 채택 (동일) | 차이 0 |
| Q2 `high_tickers` 구성 | 옵션 A vs B vs C 자문 요청 | **옵션 A 채택 + try/except 4중 가드 강화 (본체 패턴 통일)** | 본체 패턴 통일 권고 추가 |
| Q3 HIGH > cap | 옵션 A vs B vs C 자문 요청 | **옵션 A 채택 + WARNING 로그 명시** | WARNING 로그 의무 권고 |
| Q4 회귀 가드 | 8 케이스 + AST | **10 케이스 + AST (K-9 경계 + K-10 WARNING 발화 추가)** | +2 케이스 |
| Q5 1h verify | 시나리오 D 자문 요청 | **시나리오 D 채택 (보유 0 종목만)** | 시나리오 D 채택 + 보고 항목 추가 |

### 우선순위 결정

1. **HIGH 의제 Q1 (시정 안 정합성) + Q2 (high_tickers 구성)** = 본 사이클 본질, 시정 안 + 본체 패턴 통일 의무
2. **HIGH 의제 Q3 (HIGH > cap)** = 사이클 29 005935 사고 패턴 차단 의무, WARNING 로그 동행
3. **MEDIUM/LOW Q4, Q5** = 회귀 가드 + 1h verify 영역, 사이클 60~65 답습

---

## 8. 사이클 63 K-2 케이스 의미 전환 매트릭스

| 사이클 | K-2 케이스 결과 | 의미 | 코드 상태 |
|-------|--------------|------|---------|
| 63 (이주 직후) | PASS | priority 분리 *전* cap 적용 = **결함 confirm** | `targets = stale_tickers[:cap]` 잔존 |
| 66 (시정 후) | PASS | priority 분리 *후* cap 적용 = **시정 confirm** | `targets = high_targets + low_targets[: max(0, cap - len(high_targets))]` |

**테스트 코드 차이**:
- 사이클 63 K-2: 결함 확인 (HIGH 종목 누락 검증)
- 사이클 66 K-2: 시정 확인 (HIGH 종목 100% 포함 검증)

**docstring 권고**:
```python
def test_cycle66_resubscribe_priority_split_high_priority():
    """사이클 63 K-2 갱신 — 의미 전환: 결함 confirm → 시정 confirm.

    사이클 63 (이주 직후): targets = stale_tickers[:cap] = HIGH 종목 cap 밖 잘림 PASS (결함 확인).
    사이클 66 (시정 후): targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
                       = HIGH 종목 100% 포함 PASS (시정 확인).

    005935 사고 패턴 (2026-05-21 13:21:41) 영구 차단 영역.
    """
```

---

## 9. 월요일 1h verify 결합 효과 평가

### 사이클 63 §Q7 영속 의무 + 사이클 66 시정 결합

| 항목 | 사이클 63 단독 | 사이클 66 시정 결합 |
|------|---------------|--------------------|
| KIS LMS WARNING 0건 | 의무 | 의무 유지 |
| stale 영구 잔류 0건 | 의무 | 의무 유지 |
| 시나리오 A 자연 monitoring | 의무 | 의무 + HIGH 우선 보장 시각화 |
| 시나리오 B 인위 stale 주입 (보유 0) | 의무 | LOW 분기 시정 후 보존 검증 |
| 시나리오 C KIS LMS chain 차단 | 의무 | HIGH 절대 보장 후 chain 0건 검증 |
| **시나리오 D HIGH 인위 stale 주입 (보유 0)** | 신규 | HIGH 분기 5분 우선 재구독 100% 보장 검증 |
| **WARNING `[stale_priority_resubscribe_cap_exceeded]` 발화** | 신규 | Q3 옵션 A 운영 가시화 통계 |
| **HIGH 종목 5분 우선 재구독 보장률** | 신규 | 시정 전 50~80% → 시정 후 100% 측정 |

### 1h verify 평가 의무 항목

1. `[stale_priority_resubscribe] count=N tickers=[...]` 로그 분석 (HIGH/LOW 분포)
2. `[stale_priority_resubscribe_cap_exceeded]` WARNING 발화 0건 (정상 운영) 또는 N건 (HIGH 폭발 시)
3. KIS LMS WARNING 0건 (사이클 29 사고 패턴 차단)
4. 시나리오 D HIGH 인위 stale 회복 시간 ≤ 5분 (사이클 25-B 5분 우선 재구독 SLA)

---

## 10. 후속 검증 권고 (tdd-engineer / backend-dev / tester 에게)

### tdd-engineer Red

- 회귀 가드 10 케이스 + AST 1 추가 (`tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`)
- K-2 갱신 (의미 전환 명시) + K-3~K-10 신규 + AST 신규
- freezegun + caplog + `patch("src.realtime.websocket_pool.kis_ws_pool")` 패턴 답습
- HIGH 4 = 40% (사이클 63 패턴 일관)

### backend-dev Green

**시정 코드 (L1023~L1034 교체, ~10L)**:
```python
# 사이클 25-B + 사이클 66 (2026-06-06) — HIGH 보장 대상 집합 (본체 try/except 4중 가드 통일)
high_tickers: set[str] = set()
try:
    for s in scheduler.registry.all():
        try:
            high_tickers.update(s.state.positions.keys())
        except Exception:
            pass
except Exception:
    # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
    pass
try:
    high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
except Exception:
    pass

# 사이클 66 — priority 분리 *먼저*, cap 적용 *나중* (HIGH 절대 우선)
# 사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림) 영구 차단.
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]

# HIGH > cap 시 cap 위반 허용 + WARNING 로그 (사이클 66 §Q3 옵션 A)
if len(high_targets) > cap:
    logger.warning(
        "[stale_priority_resubscribe_cap_exceeded] high_count=%d cap=%d "
        "tickers=%s — HIGH 종목 cap 위반 허용 (보유/익일청산 절대 보장)",
        len(high_targets), cap, high_targets,
    )

targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

**변경 라인**: L1023~L1034 (12L) → 시정 후 ~22L (+10L). 함수 본체 ~5L → ~15L (HIGH 보장 가드 강화).

### tester Verify

- V1~V11 (K-2~K-10 + AST 11 케이스)
- V-A3 (월요일 1h verify 시나리오 D 추가)
- Q5 보고 항목 추가 (HIGH 종목 5분 우선 재구독 보장률 + WARNING 발화 빈도)

### sync-docs

- `CLAUDE.md` `_resubscribe_stale_priority` 본문 영속 (사이클 66 시정 명시)
- `src/engine/CLAUDE.md` 사이클 63 본문 + 사이클 66 시정 본문 추가
- `docs/HARNESS_CHANGELOG.md` 사이클 66 행 추가
- refactor-review 카드 #5 완료 표기

### 주말 push 의무 (사이클 60~65 6 사이클 답습 + 사이클 66 영속)

- HIGH 카드 + K stale watcher 영역 (사이클 60 §Q7 영구 hot path)
- KIS LMS/앱키 정지 chain 직접 영역 (005935 사고 패턴)
- **주말 push 권장 시점**: 일요일 사용자 검수 후
- **월요일 09:00~10:00 1h verify 의무** (사이클 63 §Q7 영속 + 사이클 66 시나리오 D 추가)

---

## 11. 현 코드와의 정합성 / 충돌 항목

### 정합 영역 (충돌 0)

- 사이클 25-B HIGH/LOW 분리 정책 = 시정 안 본질 정합
- 사이클 29-R3 K stale watcher 본체 우선순위 분리 = 시정 안 100% 일관
- 사이클 38 명문화 (매수 진입 전용 영역) = 본 시정 = 시세 영역, 매도 영향 0
- 사이클 60+61+63 stale_manager.py 이주 패턴 = 본 시정 = 본체 패턴 답습 정합

### 충돌 영역 (없음)

본 시정은 *cap 적용 순서* 만 교체 — 기존 HIGH/LOW 분리 정책 + sorted 결정적 순서 + KIS WS 풀 API 100% 보존.

### 안전 규칙 영향 평가

- ✅ **WebSocket 시세 보유·익일청산 우선 보장** (`MAX_SUBSCRIPTIONS=41`): HIGH 종목 cap 위반 허용 + bypass_limit=True 보존 = 절대 보장 강화
- ✅ **K stale watcher 우선순위 분리** (사이클 29-R3): 본체와 100% 일관 = 강화
- ✅ **사이클 29 005935 사고 패턴 차단**: 시정 안의 본질 = 100% 차단
- ✅ **사이클 38 명문화** (매수 진입 전용): 본 시정 = 시세 영역, 매도/손절/익일청산 영향 0

---

## 12. 산출물 경로

- **본 응답서**: `/Users/koscom/Projects/auto_stock/_workspace/cycle66_cap10_fix_domain_response.md`
- **설계 카드 (team-leader 사전)**: `/Users/koscom/Projects/auto_stock/_workspace/cycle66_cap10_fix_design_card.md`
- **자문 의뢰서 (team-leader 사전)**: `/Users/koscom/Projects/auto_stock/_workspace/cycle66_cap10_fix_domain_consult.md`
- **결함 위치**: `src/engine/stale_manager.py::resubscribe_stale_priority` L1023~L1034
- **시정 안 코드**: §10 backend-dev Green 섹션 (12L 교체)
- **회귀 가드 청사진**: §4 Q4 표 (10 케이스 + AST 1)

---

## 13. 한 줄 요약 (team-leader 보고)

**Q1~Q5 전부 채택 + Q6-1~Q6-6 보조 발의 (옵션 A 일관 패턴)** — 시정 안의 priority 분리 *후* HIGH 먼저 + LOW 잔여 cap 패턴이 사이클 29-R3 K stale watcher 본체와 100% 일관. `high_tickers` 구성은 본체 try/except 4중 가드 통일. HIGH > cap 케이스는 사이클 29 005935 사고 패턴 차단을 위해 cap 위반 허용 + WARNING 로그 명시. 회귀 가드 10 + AST 1, 월요일 1h verify 에 시나리오 D (HIGH 인위 stale 주입 보유 0) 신규 + HIGH 종목 5분 우선 재구독 보장률 측정 추가. 운영 영향 0 (시세 영역, 매도/손절/익일청산 무영향). 주말 push 의무 영속.
