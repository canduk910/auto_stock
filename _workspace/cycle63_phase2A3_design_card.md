# 사이클 63 Phase 2-A3 설계 카드 v2 — K stale watcher 핵심 추출 (HIGH)

> **작성**: 2026-06-05 (Fri) 16:30 KST · team-leader
> **v2 갱신**: 2026-06-05 (Fri) 17:25 KST — domain-expert 자문 결과 Q1~Q4 + Q5-1~Q5-3 전부 채택 반영
> **사이클**: 63 — refactor #2 카드 #2 마지막 단계
> **위험 등급**: **HIGH** (K stale watcher *핵심* 자체, KIS LMS/앱키 정지 chain 직접 영역, 영구 hot path 360 회/일)
> **답습 기반**: 사이클 51 (boot_manager) → 사이클 60 A1 (stale_manager 5+5) → 사이클 61 A2 (stale_manager 4+5) → **사이클 63 A3 (stale_manager 2+0)**
> **사이클 62 (가격 필터)** 무관 별도 트랙 — Q5-1 자문 확인 (호출 그래프 분리, 공유 자원 0)

---

## v2 갱신 요지 (domain-expert 자문 채택 결과)

| Q | 답변 채택 | 영향 |
|---|----------|------|
| **Q1** 8 단계 호출 순서 | **RECOMMEND** 전부 채택 | §4.1 추가 — 5 단계 `high_tickers` for-loop *전* 단일 구성 의무 강조 |
| **Q2** 우선순위 분리 보존 | **RECOMMEND** 전부 채택 | §4.2 추가 — `try/except` 4 중 가드 *그대로* 보존 (`getattr` 폴백 silent 실패 비채택) |
| **Q3** 005935 사고 시뮬 | **RECOMMEND** 전부 채택 + **1h verify 시나리오 A/B/C 도입 의무** | §5.1 보강 — 사고 재현 사전 시나리오 3 종 명세 (자연 monitoring / 인위 stale 주입 / KIS LMS chain 차단) |
| **Q4** wrapper vs 직접 호출 | **CONSIDER B 채택 — 직접 호출 (1 hop 단축)** | §2.1 갱신 — 사이클 60 A1 답습하지 *않는* 유일 영역. `from src.engine import stale_manager; stale_manager.emit_stale_session_detail(scheduler, ...)` 직접 호출. HARNESS_CHANGELOG 에 *답습하지 않음* 명시 의무 |
| **Q5-1** 사이클 62 영향 | **무관 확정** | 영향 0 |
| **Q5-2** stale_manager 비대화 | **카드 #14 사이클 64+ 발의 의무** | §10 추가 — `_workspace/refactor/2026-06-04_review.md` 카드 #14 본 사이클 종료 후 발의 |
| **Q5-3** cap=10 결함 가능성 | **backend-dev Green 확인 의무** | §10 추가 — `_resubscribe_stale_priority` L2748 `stale_tickers[:cap]` priority 분리 *전* 적용 = HIGH 보장 결함 가능성. 결함 확인 시 카드 #5 발의 |

---

## 1. 범위 확정 (코드 정독 후 검증)

### 1.1 추출 대상 2 함수 (= **322L**)

| 함수 | 위치 (scheduler.py) | 라인 수 | 역할 | 위험 |
|------|---------------------|---------|------|------|
| `_check_and_resubscribe_stale` | L2442~L2663 | **222L** | **K stale watcher 본체** (120s 주기). subscribed vs `scanner.ticker_last_tick` 비교 → 1~5회 즉시 강제 재등록 / 6회 초과 시 시간 기반 force_retry (5분 cooldown + 시간당 12회 cap) | **HIGH** — KIS LMS/앱키 정지 chain 직접, 사이클 29 005935 사고 영역 |
| `_resubscribe_stale_priority` | L2690~L2789 | **100L** | `_scan_loop` 5분 통합 구독 직후 stale 종목 우선순위 분리 재구독 (cap=10) | MEDIUM-HIGH — `_scan_loop` 호출 의존 |

**합계 322L** (사이클 60 A1 ~275L + 사이클 61 A2 ~314L 누적 ~589L → A3 **322L 추가** → 누적 **~911L 추출**).

scheduler.py 라인 변화 (refactor #2 전체 추이):
- 사이클 51 직전: ~4,185L
- 사이클 51 후: ~3,880L (−305L, boot_manager.py 305L 추출)
- 사이클 60 A1 후: ~3,605L (−275L)
- 사이클 61 A2 후: 3,320L (−290L)
- **사이클 63 A3 후 예상: ~3,005L (−315L)** — refactor #2 카드 #2 **완료**
- 최종 누적 감소: **~1,180L (~28%)**

### 1.2 추가 상수 — **0개** (예외!)

사이클 60 A1 + 사이클 61 A2 누적으로 stale 영역 10 상수 모두 이미 이전 완료:

| 상수 | 값 | 이전 사이클 | A3 사용처 |
|------|-----|-------------|-----------|
| `MAX_STALE_RETRIES` | 5 | 사이클 60 A1 | L2543 (retry > MAX_STALE_RETRIES 분기) |
| `STALE_FORCE_RETRY_AFTER_SECS` | 300 | 사이클 60 A1 | L2553 (age 비교) |
| `STALE_FORCE_RETRY_HOURLY_CAP` | 12 | 사이클 60 A1 | L2570 (시간당 cap) |
| `STALE_FRESHNESS_SECS` | 60 | 사이클 61 A2 | L2489, L2726 (stale 판정 threshold) |

→ **A3 추가 상수 0** = 사이클 60 5 + 사이클 61 5 = **10 상수 동일 유지**. 회귀 가드 카테고리 B (상수 동일성) 는 기존 10개 그대로 (추가 케이스 없음).

### 1.3 내부 호출 그래프 (행위 보존 영역)

`_check_and_resubscribe_stale` 내부 호출:
- `kis_ws_pool.get_subscribed_tickers()` (L2484) — 풀 모듈 외부 API, 변경 없음
- `kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` (L2593, L2631) — 풀 직접 호출
- `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority=..., bypass_limit=...)` (L2595, L2633) — 풀 직접 호출
- `write_log(...)` (L2579, L2614, L2652) — DB INSERT fire-and-forget
- `self.registry.all()` (L2518) → `s.state.positions.keys()` (L2520) — HIGH 종목 수집
- `self._pending_next_day_clear` (L2527) — 익일청산 set, HIGH 종목 합집합
- `self._stale_retry_count` (L2532, L2533, L2498, L2601) — getter/setter property
- `self._stale_last_resubscribe_at` (L2501, L2549, L2604, L2640) — getter/setter property
- `self._stale_force_retry_history` (L2564, L2565) — getter/setter property
- `self._emit_stale_session_detail(stale_tickers, now)` (L2662) — **이미 사이클 60 A1 에서 추출됨 → wrapper 위임 호출 보존**

`_resubscribe_stale_priority` 내부 호출:
- `scanner.ticker_last_tick` (L2731) — 글로벌 dict, 변경 없음
- `kis_ws_pool.subscribe(...)` (L2761) — 풀 직접 호출
- `self.registry.all()` (L2740) → `s.state.positions.keys()` (L2742)
- `self._pending_next_day_clear` (L2745)
- `self._stale_last_resubscribe_at` (L2768, L2769)
- `write_log(...)` (L2780)

---

## 2. 위임 패턴 (사이클 60 A1 + 사이클 61 A2 답습)

### 2.1 scheduler.py wrapper (2~3 줄)

```python
async def _check_and_resubscribe_stale(self) -> None:
    """K stale watcher 본체 — 사이클 63 Phase 2-A3 stale_manager 위임."""
    from src.engine import stale_manager
    await stale_manager.check_and_resubscribe_stale(self)

async def _resubscribe_stale_priority(self, cap: int = 10) -> list[str]:
    """`_scan_loop` 5분 stale 우선순위 재구독 — 사이클 63 Phase 2-A3 stale_manager 위임."""
    from src.engine import stale_manager
    return await stale_manager.resubscribe_stale_priority(self, cap=cap)
```

### 2.2 stale_manager.py 신규 2 함수 (단순 이주, 행위 변경 0)

- `async def check_and_resubscribe_stale(scheduler: Any) -> None`
- `async def resubscribe_stale_priority(scheduler: Any, cap: int = 10) -> list[str]`

**핵심 패턴 (사이클 61 답습)**:
1. **logger 명시 binding**: `logging.getLogger("src.engine.scheduler")` — `[stale_watcher]` / `[stale_watcher_detail]` / `[stale_force_retry]` / `[stale_force_retry_cap]` / `[stale_priority_resubscribe]` 5 prefix 운영 logging config 호환 + caplog 회귀 가드 호환
2. **`sys.modules.get("src.engine.scheduler")` 패턴** (사이클 61 도입): `kis_ws_pool` / `datetime.now()` / `scanner` 접근 시 scheduler 네임스페이스 우선 참조 → D-1 AST 가드 + 테스트 patch 호환 + 운영 환경 동일 객체
3. **사이클 60 `_emit_stale_session_detail` 호출 = Q4 CONSIDER B 채택 (직접 호출)** — *사이클 60 A1 답습하지 않는 유일 영역*:
   - `_check_and_resubscribe_stale` 마지막 L2662 `self._emit_stale_session_detail(stale_tickers, now)` 호출을 A3 이주 후 → `stale_manager.emit_stale_session_detail(scheduler, stale_tickers, now)` **직접 호출** (1 hop 단축)
   - 사이클 60 A1 wrapper 분리 의도와 약간 상충하나, **stale_manager 내부 일관성 + 사이클 61 `sys.modules.get()` 패턴 시너지** 우선
   - **HARNESS_CHANGELOG.md 사이클 63 행에 *답습하지 않음* 명시 의무** (Q4 채택 근거 동봉)
   - scheduler.py L2678 `_emit_stale_session_detail` wrapper 자체는 **삭제하지 않음** (외부 호출자 호환 보존)
4. **AttributeError 후방호환 가드 보존**: `hasattr(scheduler, "_stale_last_resubscribe_at")` / `hasattr(scheduler, "_stale_force_retry_history")` — 테스트 `__new__` 호출 패턴 호환
5. **Q2 RECOMMEND**: `try/except` 4 중 가드 (L2517~L2529 `registry.all()` / `s.state.positions.keys()` / `_pending_next_day_clear`) **그대로 보존**. `getattr(scheduler, "registry", None)` 폴백 도입 금지 — silent 실패 위험 (테스트 `__new__` 인스턴스 → silent None → HIGH 종목 빈 집합 → 모든 stale 종목 LOW 처리 = 보유 종목 메인 보장 깨짐)

### 2.3 logger 명시 binding 회귀 가드 (사이클 60 I1 영구)

stale_manager.py 상단 (사이클 60+61 동일):

```python
import logging
logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 — caplog 호환 + 운영 logging config 호환
```

**금기**: `logger = logging.getLogger(__name__)` 사용 시 `[stale_watcher]` / `[stale_watcher_detail]` 운영 로그가 `src.engine.stale_manager` 채널로 분리 → 운영 logging config 누락 위험 + 사이클 28 회귀 가드 `caplog.set_level(logger="src.engine.scheduler")` 실패.

---

## 3. 회귀 가드 케이스 청사진 (HIGH 비중 ↑, **25 케이스 / 14 파일** 목표)

사이클 60 A1 = 17 케이스, 사이클 61 A2 = 20 케이스. A3 = K stale watcher 핵심 + HIGH 비중 ↑ → **25 케이스** (추정 18~25 중 상한).

### 3.1 카테고리별 분류

| 카테고리 | 케이스 수 | HIGH 비중 | 설명 |
|----------|-----------|-----------|------|
| **A. 위임 wrapper 검증** | 4 | 1 | scheduler wrapper → stale_manager 호출 정합성 (2 함수 × 2 분기) |
| **B. 상수 re-export 동일성** | 0 | 0 | A3 추가 상수 0 — 기존 10 상수 유지 (사이클 60+61 케이스 보존) |
| **C. property `is` 동일성** | 3 | 2 | `_stale_retry_count` / `_stale_last_resubscribe_at` / `_stale_force_retry_history` 3 dict 외부 `getattr` (`src/routes/realtime.py:88-91`) 동일성 보장 |
| **D. AST 정적 의존성 역전 가드** | 2 | 1 | stale_manager.py 가 `from src.engine.scheduler import ...` 정적 import 0 (D-1: `import scheduler as _sched_mod` 직접 import 금지, `sys.modules.get()` 패턴만 허용) |
| **E. `_reset_daily_state` 동행 reset (Q2 RECOMMEND 영속)** | 2 | 1 | 사이클 60 G-1 + 사이클 61 E-1 답습 — `_stale_retry_count` / `_stale_last_resubscribe_at` / `_stale_force_retry_history` 3 dict 모두 reset_daily 호출 후 비어있음 |
| **F. dataclass 7 필드 누락 가드 (사이클 48)** | 2 | 1 | A3 가 `_stale_state` 추가 필드 reset 의무 시 사이클 48 dataclass 자동 가드 (현재 추가 0 → 케이스 보존만) |
| **G. 1~5회 즉시 강제 재등록 (KIS 정상 패턴)** | 3 | **3** | first stale → `unsubscribe_in_pool` + `subscribe(HIGH/LOW, bypass=...)` (사이클 17 KIS 공식 답변 반영), retry 1~5회 모두 동일 분기 + retry==5 마지막 분기 |
| **H. 6회 초과 시간 기반 force_retry (사이클 29-R1)** | 4 | **4** | (a) `_stale_last_resubscribe_at` 부재 시 즉시 1회 발화 / (b) age >= 300s 시 발화 + 카운터 리셋 (0) / (c) age < 300s 시 skip / (d) 시간당 12회 cap 초과 시 `[stale_force_retry_cap]` WARNING |
| **I. 우선순위 분리 HIGH+bypass=True / LOW+bypass=False (사이클 29-R3)** | 3 | **3** | positions 소속 → HIGH+bypass / next_day_clear 소속 → HIGH+bypass / 그 외 후보 → LOW+bypass=False |
| **J. force_retry history 60분 슬라이딩 윈도우** | 2 | 1 | history append 후 60분 경과 시 evict / cap 12 비교 정확성 |
| **K. `_scan_loop` 5분 stale priority resubscribe cap=10** | 2 | 1 | stale 30개 중 cap=10 만 재구독 + 결정적 sorted 순서 보장 |
| **L. caplog logger 명시 binding (사이클 60 I1 영속)** | 1 | 1 | `caplog.set_level(logger="src.engine.scheduler")` 로 `[stale_watcher]` / `[stale_priority_resubscribe]` 로그 캡처 호환 |
| **M. import sanity** | 1 | 0 | `from src.engine import stale_manager as sm; assert callable(sm.check_and_resubscribe_stale) and asyncio.iscoroutinefunction(sm.check_and_resubscribe_stale)` |
| **합계** | **25** | **18** | **HIGH 비중 72%** — A3 가 *K stale watcher 핵심* 본체이므로 HIGH 비중 사이클 61 (20%) 대비 ↑↑↑ |

### 3.2 HIGH 케이스 18 건 우선 작성 의무

- 사이클 60 A1 = 17 케이스 중 HIGH 2 (12%)
- 사이클 61 A2 = 20 케이스 중 HIGH 4 (20%)
- **사이클 63 A3 = 25 케이스 중 HIGH 18 (72%)** — *전 케이스 HIGH 가능성* 인지

HIGH 케이스는 tdd-engineer Red 단계에서 **전수 먼저 작성** 의무 (사이클 60/61 답습).

### 3.3 freezegun 의무 카테고리

- **H** (6회 초과 force_retry, age 비교 + 시간당 cap 60분 윈도우): freezegun **필수**
- **J** (history 60분 슬라이딩 evict): freezegun **필수**
- 나머지: 시계 비의존 또는 fixed datetime 사용 가능

### 3.4 flakiness 3 회 반복 의무 (tester 단계)

사이클 58 V-2 / 사이클 60 / 사이클 61 답습 — tester 단계에서 25 케이스 전수 3 회 반복 실행 (`pytest -x --count=3` 또는 `pytest-repeat`) → flake 0건 확인 필수.

---

## 4. 사이클 60 / 61 답습 패턴 매트릭스

| 항목 | 사이클 60 A1 | 사이클 61 A2 | **사이클 63 A3** | 비고 |
|------|--------------|--------------|------------------|------|
| 추출 함수 수 | 5 | 4 | **2** | A3 = 핵심 2 함수만 (마지막 단계) |
| 추출 라인 수 | ~275L | ~290L | **~315L** | A3 가 가장 큼 (`_check_and_resubscribe_stale` 222L 단일 함수) |
| 추가 상수 수 | 5 | 5 | **0** | A3 = 누적 10 상수 모두 이전 완료, 추가 0 |
| 회귀 가드 케이스 | 17 | 20 | **25** | HIGH 비중 12% → 20% → **72%** |
| 분리 파일 수 | 13 | 12 | **14** | A3 새 테스트 파일 1 + 기존 9 파일 영향 4~6 |
| logger binding | `getLogger("src.engine.scheduler")` | 동일 | **동일** | 사이클 60 I1 영구 가드 |
| `sys.modules.get(...)` | N/A | 도입 (silent inactive + force reconnect 한정) | **2 함수 전체 적용** | A3 = K stale watcher 핵심, scheduler 네임스페이스 의존 더 큼 |
| `_reset_daily_state` 동행 | G-1 | E-1 | **(승계)** | A3 추가 dict 필드 0 → 케이스 보존만 |
| dataclass 필드 누락 가드 | F (2) | F (2) | **F (2)** | A3 추가 필드 0 → 케이스 보존만 |
| domain-expert 사전 자문 | Phase 2-A 통합 | Phase 2-A2 별도 자문 | **Phase 2-A3 별도 자문 의무** | Q7 본질 차이 인지 영속 — 의뢰서 동봉 |
| push 시점 | 사이클 60 A1 = LOW, 평일 가능 | 사이클 61 A2 = MEDIUM, 사이클 60 패턴 답습 | **사이클 63 A3 = HIGH, 주말 push 의무** | 영구 hot path 360 회/일 + 금요일 NXT 애프터 금지 |
| 1h tester verify | 자율 | 자율 | **월요일 09:00 첫 _boot 후 1h 운영 환경 직접 검증 의무** | A3 = HIGH, 사이클 29 005935 사고 chain 직접 영역 |
| flakiness 3 회 | 의무 | 의무 | **의무** | tester 단계 25 케이스 전수 |
| 사이클 38 명문화 영속 | N/A | N/A | **무관** | A3 분기 진입 위치 = 시세 영역 (매도/익일청산 영역 아님) |

---

## 5. 위험 매트릭스 (HIGH 비중 명시)

| 위험 항목 | 등급 | 시정 안 됨 시 결과 | 시정 보장 메커니즘 |
|-----------|------|-------------------|---------------------|
| **K stale watcher 영구 정지** | **CRITICAL** | 시세 stale → 손절·트레일링 평가 지연 → 사이클 29 005935 13:21:41 stale 8 분 영구 잔류 = 손실 확정 | A wrapper 4 케이스 + I priority 분리 3 케이스 + H force_retry 4 케이스 = 11 케이스로 본체 검증 |
| **KIS LMS / 앱키 정지 chain** | **CRITICAL** | 강제 재등록 폭주 시 KIS 측 차단 → 모든 시세 끊김 → 매수/매도 전면 정지 | H (d) 시간당 12회 cap WARNING + J history 60분 evict 정확성 검증 |
| **우선순위 분리 깨짐 (메인 편중 회귀)** | **HIGH** | positions/익일청산 → HIGH+bypass 보장 실패 시 보유 종목 stale → 손절 평가 지연 | I 3 케이스 (positions / next_day_clear / 그 외 후보) 전수 검증 |
| **`_scan_loop` 5분 stale priority resubscribe 미발화** | **HIGH** | 사이클 25-B silent inactive 사고 (2026-05-20 14:58 메인 fresh=0 stale=11) 재발 | K 2 케이스 (cap=10 + sorted 결정성) + A wrapper |
| **테스트 patch 호환 깨짐 (운영 환경 무영향)** | MEDIUM | 기존 9 테스트 파일 (`test_stale_watcher_*.py` 등) 의 patch 경로 깨짐 → 회귀 가드 신뢰성 손상 | C property 3 케이스 + D-1 AST 가드 + `sys.modules.get()` 패턴 |
| **logger 명시 binding 누락** | MEDIUM | `[stale_watcher]` / `[stale_priority_resubscribe]` 운영 로그 누락 → 운영자 진단 불가 | L caplog 1 케이스 (사이클 60 I1 영속) |
| **`_emit_stale_session_detail` wrapper hop 손상** | LOW | 1 hop 단축 vs 사이클 60 보존 — domain-expert 자문 채택 결정 | A wrapper 4 케이스 + domain-expert RECOMMEND 결정 |

### 5.1 운영 환경 1h verify 의무 시나리오 — Q3 RECOMMEND 채택 (3 종 도입)

domain-expert Q3 자문 결과 **사고 재현 사전 시나리오 3 종 도입 의무**. 월요일 (2026-06-09) 09:00~10:00 운영 환경 1h 동안 tester 가 직접 모니터링.

#### 시나리오 A — 자연 monitoring (기본, 의무)

- **09:00 KRX 첫 _boot 직후**: `[stale_watcher] subscribed=N stale=0` 정상 로그 확인 (첫 사이클은 stale 0 기대)
- **09:30 _scan_loop 첫 발화 후**: `[stale_priority_resubscribe] count=0 tickers=[]` 또는 `count=N tickers=[...]` 정상 로그 확인
- **10:00 K stale watcher 5 사이클 후 (120s × 5 = 10분)**: stale 발생 시 `[stale_watcher_detail] session=main sub=A/41 fresh=B stale=C ratio=...` 정상 로그 확인
- **보유 종목 stale 발생 시**: HIGH+bypass=True 로 메인 재등록 확인 + `[stale_watcher]` 카운트 정합성
- **stale 6회 초과 발생 시**: `[stale_force_retry] ticker=... retries=6 last_resub_age=...s — 강제 재시도 + 카운터 리셋` 정상 로그 + `_stale_retry_count[ticker]` 0 리셋 확인

#### 시나리오 B — 인위 stale 주입 (선택, 사고 재현 사전 검증)

운영 환경 risk 없이 stale 분기 실주행 검증을 위한 인위 stale 주입 (1회만 / 검증 후 즉시 회복 확인):

1. **사전 준비**: tester 가 prod EC2 SSH 진입 + `psql` 또는 `python -m src.cli.debug_stale_inject` (별도 CLI 도구 사이클 64+ 발의 가능, 본 사이클은 코드 변경 없음 — Read-only `python` REPL 진입)
2. **주입 방법** (Python REPL):
   ```python
   from src.engine.scanner import ticker_last_tick
   from datetime import datetime, timedelta
   from src.engine.scheduler import _KST_TZ
   # 의도적 stale 1 종목 (NXT 주말 휴장 후 잔존 추정, 보유 0 종목만 선택)
   test_ticker = "ACTIVE_NON_HELD_TICKER"  # tester 가 09:30 시점 보유 0 확인 후 결정
   ticker_last_tick[test_ticker] = datetime.now(_KST_TZ) - timedelta(seconds=120)
   ```
3. **검증 항목** (다음 K stale watcher 사이클, ~120s 대기):
   - `[stale_watcher] subscribed=N stale=1 force_reregistered=1 skipped=0` 로그
   - 종목이 보유 0 → LOW+bypass=False 분기 정상 진입 (`[stale_watcher_detail]` 세션 분포에서 보조 세션 신규 등록 확인)
   - `_stale_last_resubscribe_at[test_ticker]` set 확인
4. **회복 확인**: ~10초 내 정상 시세 수신 시작 → `ticker_last_tick[test_ticker]` 갱신 확인

**금기**: 보유 종목 (positions) 에 인위 stale 주입 절대 금지 — 손절 평가 영향 위험.

#### 시나리오 C — KIS LMS chain 차단 monitoring (의무)

사이클 29 005935 사고 재현 패턴 (T+0~T+18min) 의 핵심 안전망 (시간당 12회 cap WARNING) 동작 검증:

1. **모니터링 대상**: 1h verify 기간 동안 `[stale_force_retry_cap]` WARNING 발생 여부
2. **정상 케이스** (예상): WARNING 0건 — 1h 내 동일 종목 12회 초과 force_retry 발생할 가능성 매우 낮음 (자연 발생 빈도 < 시간당 1회 추정)
3. **이상 케이스** (즉시 작업 중단 트리거):
   - WARNING 발생 시 즉시 사용자 보고 → 다음 작업 (사이클 64+) 진입 차단
   - 동일 종목 1h 내 ≥3회 force_retry 발생 시 (cap 도달 전이라도) WARNING 보고
4. **시스템 안정성 확인**: 1h 종료 직후 `[ws_heartbeat]` 5분 통계 + `[tick_coverage_session]` 정상 작동 확인 → KIS LMS / 앱키 정지 발생 0 확인

→ 1h 운영 환경 verify 결과 (시나리오 A/B/C 전수) 는 별도 사이클 또는 운영 점검 작업으로 인계.

---

## 6. push 시점 의무 (Q5 영속)

| 시각 | 동작 | 비고 |
|------|------|------|
| 2026-06-05 (Fri) 16:30 KST | team-leader 단계 완료 (현재) | — |
| 2026-06-05 (Fri) 16:30~17:00 | domain-expert 추가 자문 의뢰 | 사용자 명시 후 발주 |
| 2026-06-05 (Fri) 17:00~ | tdd-engineer Red → backend-dev Green → tester Verify → sync-docs | 운영 영향 0 (테스트 + 문서) |
| **2026-06-05 (Fri) 18:00+** | **NXT 애프터 push 금지** | A1/A2 와 본질 다름 (영구 hot path 360 회/일 K stale watcher) |
| **2026-06-06 (Sat) 또는 2026-06-07 (Sun)** | **주말 push 의무** | KRX/NXT 모두 휴장 → 운영 영향 0, 별도 브랜치 `cycle63/phase2A3/stale-watcher-core` 권장 |
| 2026-06-09 (Mon) 07:50 | EC2 첫 _boot | 자동 배포 (GitHub Actions) |
| **2026-06-09 (Mon) 09:00~10:00** | **tester 1h 운영 환경 직접 verify 의무** | 5.1 시나리오 전수 |

---

## 7. 산출물 발주 순서

1. **(현재 완료)** team-leader — A3 2 함수 + 라인 수 확정 + 설계 카드 작성
2. **(다음)** domain-expert 추가 자문 — `_workspace/cycle63_phase2A3_domain_consult.md` (사용자 명시 후 발주)
3. 사용자 결정 (자문 결과 RECOMMEND/CONSIDER/AVOID 분류 채택)
4. tdd-engineer Red 발주 — 25 케이스 (HIGH 18 우선 작성)
5. backend-dev Green 발주 — wrapper 위임 2 줄 × 2 함수 + stale_manager.py 본체 322L 이주
6. tester Verify 발주 — 4 카테고리 분리 측정 + flakiness 3 회 + HIGH 케이스 전수 우선
7. sync-docs — `src/engine/CLAUDE.md` + `src/engine/stale_manager.py` 헤더 + `docs/HARNESS_CHANGELOG.md` (사이클 63 행 추가)
8. **사용자 명시 commit + 주말 push 지시 대기**
9. **월요일 (2026-06-09) 09:00~10:00 tester 1h 운영 환경 verify** (별도 사이클 또는 운영 점검)

---

## 8. 절대 깨지면 안 되는 6 규칙 (CLAUDE.md, A3 직접 영향)

1. **WebSocket 4 중 안전망**: F1 (재연결 1회) + `_scan_loop` (5분) + **K stale watcher (120s)** + `_resubscribe_stale_priority` (5분 우선) — A3 가 *K stale watcher* + *5분 우선* 자체. 본체 행위 보존 절대.
2. **K stale watcher 우선순위 분리** (사이클 29-R3): `high_tickers = positions ∪ _pending_next_day_clear` → HIGH+bypass=True / 그 외 → LOW+bypass=False. I 3 케이스 전수 검증.
3. **stale watcher force_retry** (사이클 29-R1): 1~5회 즉시 강제 재등록 + 6회 초과 시 5분 cooldown 기반 force_retry + 시간당 12회 cap. G + H 7 케이스 전수 검증.
4. **silent inactive 시간당 세션당 2회 cap** (사이클 29-R2): A2 이주 완료, **A3 영향 0** — 회귀 가드 보존만.
5. **stale universe 가드** (사이클 32): A2 이주 완료, **A3 영향 0** — 회귀 가드 보존만.
6. **`_reset_daily_state` 동행 reset** (사이클 60 G-1 + 사이클 61 E-1): A3 추가 dict 필드 0 → E 2 케이스 보존만 (회귀 가드).

---

## 9. 사이클 60/61 답습 hotfix 패턴 (선제 가드)

사이클 60 hotfix (cycle60-1) = logger 명시 binding 누락 → caplog 회귀 가드 실패 → 즉시 시정.
사이클 61 hotfix (cycle61-1) = `sys.modules.get(...)` 패턴 누락 → silent inactive 테스트 patch 실패 → 즉시 시정.

**사이클 63 hotfix 사전 차단 의무**:
1. logger binding `getLogger("src.engine.scheduler")` 코드 작성 시 즉시 확인
2. `sys.modules.get("src.engine.scheduler")` 패턴 2 함수 전체 적용 즉시 확인 (`kis_ws_pool` / `datetime.now()` / `scanner` 접근 시점)
3. 기존 9 테스트 파일 (`test_stale_watcher_*.py` 등) patch 경로 깨짐 사전 grep — Green 단계 직후 `pytest tests/unit/engine/test_stale_watcher*.py tests/integration/test_stale_watcher*.py -x` 1회 실행 의무

---

## 10. 산출물 파일 + Q5-2 / Q5-3 후속 카드 인계

### 10.1 본 사이클 산출물

- 본 설계 카드 v2: `_workspace/cycle63_phase2A3_design_card.md` (현재 파일)
- domain-expert 의뢰서: `_workspace/cycle63_phase2A3_domain_consult.md` (완료)
- domain-expert 응답: `_workspace/cycle63_phase2A3_domain_response.md` (완료, 채택)
- **Red 명세**: `_workspace/red/cycle63_phase2A3_stale_watcher_core.md` (v2 갱신 직후 작성)
- tdd-engineer Red 산출: `tests/unit/engine/test_cycle63_phase2A3_stale_watcher_core.py` (25 케이스, HIGH 18 우선)
- backend-dev Green 산출: `src/engine/stale_manager.py` (+ 322L, 11 함수 누적) + `src/engine/scheduler.py` (-315L net, wrapper 2 함수 × 2 줄)
- tester Verify 산출: 백엔드 PASS 카운트 갱신 (현재 1882 → 1907 PASS 목표) + 4 카테고리 분리 측정 + flakiness 3 회 PASS + V12 (백엔드 only) + V13 매도 영향 0 (stale watcher = 시세 영역, 매도 영역 무관)
- sync-docs 산출:
  - `src/engine/CLAUDE.md` 사이클 63 행 + 모듈 맵 (9→11 함수)
  - `src/engine/stale_manager.py` 헤더 (사이클 63 행)
  - 루트 `CLAUDE.md` 사이클 63 행
  - `docs/HARNESS_CHANGELOG.md` (Q4=B 직접 호출 = *사이클 60 답습하지 않음* 명시 의무)
  - `_workspace/refactor/2026-06-04_review.md` 카드 #2 A3 완료 표시

### 10.2 Q5-2 카드 #14 인계 (사이클 64+ 발의 의무)

**의제**: stale_manager.py 비대화 (사이클 63 A3 후 731L → ~1,053L) — sub-module 분해 청사진:

| sub-module | 함수 (예시) | 추정 라인 |
|------------|-------------|-----------|
| `stale_diagnostics.py` | `build_session_subscription_view` / `emit_stale_session_detail` / `refresh_stale_ccnl_cache` / `evict_expired_ccnl` / `prune_force_retry_history` | ~350L |
| `stale_session_recovery.py` | `detect_silent_inactive_sessions` / `force_reconnect_session` | ~250L |
| `stale_universe_guard.py` | `delta_unsubscribe_dropped` / `evaluate_universe_guard` | ~150L |
| `stale_watcher_core.py` | **`check_and_resubscribe_stale`** / **`resubscribe_stale_priority`** | ~322L |

**인계**: 본 사이클 종료 후 sync-docs 단계에서 `_workspace/refactor/2026-06-04_review.md` 에 **카드 #14 (Q5-2)** 신규 발의 — 사이클 64+ refactor-expert 검토 대상 등록. HIGH 비중 (사이클 60 답습 = 비대화 회피) 으로 분류.

### 10.3 Q5-3 cap=10 결함 가능성 인계 (backend-dev Green 확인 의무)

**의심**: `_resubscribe_stale_priority` L2748:

```python
targets = stale_tickers[:cap]  # cap=10 적용
```

→ `stale_tickers` 가 `sorted()` 결과 (결정성 보장) 인데, **priority 분리 (HIGH/LOW) 적용 *전*** 에 cap=10 잘림. stale 30 종목 중 sorted 결과 알파벳 순 상위 10건이 모두 LOW (그 외 후보) 라면 → 보유 종목 (HIGH) 이 cap 밖으로 밀려 재구독 미발화 결함 가능성.

**backend-dev Green 단계 의무**:
1. L2745 (이주 후 동일 위치) 코드 정독 + 결함 재현 시뮬 (보유 005935 + LTV 후보 30 종목 모두 stale + sorted "0..." 우선 LTV 후보 → 005935 cap 밖)
2. **결함 확인 시**: 사이클 64+ 카드 #5 별도 발의 (`_workspace/refactor/2026-06-04_review.md`) — *HIGH 종목 cap 적용 전 우선 보장 시정*
3. **결함 부재 시**: tester verify 보고서에 sorted 순서 cap=10 정상 작동 확인 명시 + 카드 발의 skip

**시정 안 (참고, 사이클 64+ 카드 #5 채택 시)**:
```python
# 변경 전 (사이클 25-B)
targets = stale_tickers[:cap]

# 변경 후 (제안)
high_stale = [t for t in stale_tickers if t in high_tickers]
low_stale = [t for t in stale_tickers if t not in high_tickers]
targets = high_stale + low_stale[:max(0, cap - len(high_stale))]
# HIGH 우선 보장 + 잔여 cap 만 LOW 적용
```

### 10.4 사이클 분할 결정

- **사이클 63 단일** = A3 2 함수 추출 (~322L) + Q4 = B 직접 호출 패턴
- **Q5-2 sub-module 분해** = 사이클 64+ 카드 #14 별도 발의 (본 사이클 범위 밖)
- **Q5-3 cap=10 결함 시정** = backend-dev Green 결함 확인 시 사이클 64+ 카드 #5 별도 발의 (조건부)

### 10.5 별도 브랜치 권장

`cycle63/phase2A3/stale-watcher-core` (사이클 60 응답서 §Q5 권고 영속 — HIGH 위험도 영역의 별도 브랜치 격리)

---

> **다음 단계**: Red 명세 (`_workspace/red/cycle63_phase2A3_stale_watcher_core.md`) 작성 → 사용자 보고 → tdd-engineer Red 발주.
