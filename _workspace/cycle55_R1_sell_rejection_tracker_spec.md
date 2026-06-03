# 사이클 55 — R-1 SellRejectionTracker 단일 정책 객체 (HIGH 리팩토링)

> **발주**: team-leader (2026-06-03)
> **카드 원본**: `_workspace/2026-06-01_log_analysis.md` R-1
> **위험 등급**: HIGH (매매 hot path, 4 분류 분기 통합)
> **선례 비교**: 사이클 48 (`stale_tracker.py` 82L), 사이클 51 (`boot_manager.py` 305L) — 둘 다 행위 보존 추출 성공

---

## 1. team-leader 결정사항 (자문 *전* 명확화)

### 1.1 발주 흐름 — **옵션 A 채택**

**선택**: 옵션 A (domain-expert 자문 *먼저* → refactor-expert 설계 → tdd-engineer Red → backend-dev Green → tester 검증)

**사유**:
1. **R-1 의 본질이 매매 행위 명세 영역** — 4 거부 분류의 *현장 의미 차이* 가 핵심. refactor-expert 가 코드 구조부터 잡으면 *행위 통합 가능 여부* 판단이 거꾸로 됨 (코드에 행위를 맞추는 위험).
2. **사이클 52 B-1 시정의 자연 후속** — 사이클 52 는 *진입 차단만* 단일 책임으로 처리 (도메인 자문 미호출). R-1 은 *4 분류 통합* 이라 사이클 52 와 책임 범위가 다르며, 도메인 자문 비용이 정당함.
3. **CLAUDE.md 절대 규칙 다수 보호 영역** — "NXT 매도 좀비 차단" / "시장가 거부 폴백" / "체결통보 race 가드" 3 종이 모두 sell 경로에 얽힘. 도메인 자문이 *어떤 규칙이 통합 가능 / 불가능* 한지 사전 판정 필수.
4. **사이클 49→54 누적 6 사이클** — 리팩토링 카드 효과 누적 측정 필요 시점. 옵션 B (refactor-expert 우선) 는 코드 분석 비용 중복 (이미 분석 메모 R-1 에 충분히 정리됨).
5. **옵션 C (병렬 검토) 배제** — domain-expert 와 refactor-expert 의 의견 충돌 시 합의 비용이 큼. 순차 (도메인 → 리팩토링) 가 효율적.

### 1.2 결정 포인트 1: 통합 범위 — **부분 통합 (행위 보존 우선)**

**1차 판정** (도메인 자문으로 최종 확정):

| 거부 분류 | 진입 차단 게이트 | 폴백 정책 | positions 처리 | 통합 적합성 |
|----------|---------------|----------|--------------|------------|
| `is_market_closed_rejection` | **O** (사이클 52, 다음 KST 09:00 TTL) | 없음 | 보존 | **포함 (이미 구현)** |
| `is_market_order_disallowed` | **검토 필요** (폴백 후 1초 TTL?) | 지정가 5호가 1회 | 보존 | **포함 (다른 TTL 정책)** |
| `is_insufficient_quantity` | 불필요 (positions 자체 제거로 자연 차단) | 없음 | **제거** | **제외 권고** |
| `is_insufficient_cash` | (매도 분기 미해당) | (매수 분기 cooldown) | — | **제외 (sell 비대상)** |

**판정 근거**:
- **`is_insufficient_quantity` 분리** — KIS 가 "수량 없음" 으로 거부 → positions 제거 = 다음 호출에서 `pos = strategy.state.positions.get(ticker)` 가 None → 함수 진입 직후 return. **자연 차단 메커니즘이 이미 존재** → tracker 추가는 중복. 단, 통합 객체에 *기록* 은 가능 (관찰성 가치 — 시간당 거부 카운트, V-1 알람 카드 연계).
- **`is_insufficient_cash` 매도 분기 없음** — 확인 결과 `execute_sell` 에 호출 없음. R-1 카드 원문의 4 분류는 *명세 오류* (매수 가드 포함). **명세 정정**: 통합 범위는 *3 분류* (market_closed / market_order_disallowed / insufficient_quantity 의 *기록* 만).
- **`is_market_order_disallowed` TTL 정책** — 사이클 52 의 단순 09:00 TTL 답습 부적합. 폴백 1회 시도 후 *즉시* 다음 사이클에서 재트리거되어야 함 (청산 의무). **권고: 별도 TTL=0 정책 또는 폴백 *진행 중* 마커 (set 멤버십만)**. → 도메인 자문 핵심 질문.

### 1.3 결정 포인트 2: emit cap 통합 헬퍼 — **분리 (사이클 56 후속)**

**1차 판정**: 사이클 55 = SellRejectionTracker **단일**. emit cap 통합은 사이클 56 별도 카드.

**사유**:
- 사이클 31 (`_risk_silent_skip_logged_today` set[tuple]) / 사이클 52 (`_market_closed_blocked_logged_today` set[str]) / 사이클 54 (`_nxt_downgrade_logged_today` set[str]) — 키 형식 다름 (tuple vs str), reset 위치 다름 (RiskManager vs OrderEngine).
- 동시 통합 시 사이클 55 가 **2 개 추상화** (SellRejectionTracker + DailyEmitCap) 를 한 번에 도입 → 회귀 위험 + 리뷰 비용 ↑.
- **단계 분리**: 사이클 55 = SellRejectionTracker (sell 경로 내부 emit cap 은 *직접 포함* — 차단 게이트 발화 시 1회/일 INFO 등록 + reset 동행). 사이클 56 = 3 set 전체 통합 (`DailyEmitCap[K]` 제네릭, RiskManager + OrderEngine + 잠재 추가).

### 1.4 결정 포인트 3: 모듈 위치 — **별도 모듈 `src/engine/sell_rejection.py`**

**1차 판정**: `src/engine/sell_rejection.py` 신규 모듈 (선례: 사이클 48 `stale_tracker.py` 82L).

**사유**:
- `OrderEngine` 내부 inner class → 단일 책임 위반 (OrderEngine 은 주문 실행, tracker 는 차단 정책).
- 별도 모듈 = (a) 단위 테스트 격리 용이 (b) 사이클 51 boot_manager 추출 패턴 일관 (c) 사이클 56 emit cap 통합 시 `SellRejectionTracker` 가 `DailyEmitCap` 을 멤버로 흡수하기 쉬움.
- 예상 라인: 80~120L (선례 `stale_tracker.py` 82L 유사).

### 1.5 결정 포인트 4: TTL 정책 — **분류별 차별화**

**1차 판정**:

| 분류 | TTL 정책 | 사유 |
|------|---------|------|
| `is_market_closed_rejection` | 다음 KST 09:00 (사이클 52 보존) | 장운영시간 외 = 자연 만료 시점 명확 |
| `is_market_order_disallowed` | **TTL=0 (폴백 즉시 재시도 허용)** | 청산 의무, 폴백 1회 실패 시 다음 *사이클* (5분) 자연 재트리거 필요 |
| `is_insufficient_quantity` | TTL=0 (기록만, 차단 없음) | positions 제거가 자연 차단 |

**대안 (도메인 자문 의제)**: `is_market_order_disallowed` 도 짧은 TTL (10~30초) 부여하여 동일 tick 폭주 차단 — 폴백 후 즉시 재호출되는 시나리오 방어 필요 여부.

---

## 2. domain-expert 자문 발주 (선행)

### 2.1 자문 제목
**[사이클 55 R-1 선행] SellRejectionTracker 4 거부 분류 통합 — 매매 행위 영향 평가**

### 2.2 자문 질문 (5 항목)

#### Q1 — `is_market_closed_rejection` 진입 차단 TTL 정책 (사이클 52) 의 *유지 / 강화 / 완화* 권고
- 현행: 거부 시 ticker → 다음 KST 09:00 만료 게이트. TTL 미경과 시 KIS 호출 없이 skip.
- 사이클 52 운영 검증 (2026-06-02~03): 결함 미관측 (B-1 폭주 시나리오 재현 0건).
- **질문**: TTL=다음 09:00 이 *과도하게 보수적* 일 가능성 (장 중 KIS 시스템 일시 장애로 동일 거부 발생 시 정상 시장 시간에도 차단)? 예: KRX 메인 시간 (09:00~15:30) 중 발생한 거부도 다음 09:00 까지 차단되는 게 맞나?

#### Q2 — `is_market_order_disallowed` (시장가 거부 → 지정가 폴백) 에 진입 차단 게이트 적용 시 *원하지 않는 행위* 발생 가능성
- 현행: 거부 시 `step_down(current_price, 5)` LIMIT 폴백 1회. 폴백 실패 시 positions 보존, 다음 사이클 자연 재트리거.
- 가설: 폴백 성공해도 *체결까지 시간 lag* 발생 → 그 사이 다른 신호 (다른 전략의 청산) 가 같은 ticker `execute_sell` 호출하면 *중복 매도 시도* 위험.
- 현행 방어: `self._selling` set (매도 진행 중 중복 차단). 폴백 성공 → `return` (selling 보존 — 체결통보에서 해제).
- **질문**: `is_market_order_disallowed` 거부 후 짧은 TTL (예: 10초) 진입 차단을 *추가* 도입 시 (a) 폴백 후 정상 체결 흐름 영향 (b) 다른 전략 청산 의무 위반 가능성?

#### Q3 — `is_insufficient_quantity` 분리 권고 (positions 자체 제거로 자연 차단) 의 *맹점*
- 현행: 거부 시 `insufficient_qty = True` → 3회 재시도 skip → 메모리/DB positions 제거.
- 가설: positions 제거 직후 *체결통보 지연 도착* 시 → KIS 잔고에는 수량 있는데 메모리는 0 → 다음 청산 신호 못 발사 → 좀비 보유.
- **질문**: 이 경로의 안전 마진 (예: `_sync_positions_from_balance()` 15분 주기 보강) 이 충분한가? SellRejectionTracker 가 *기록* 만 (차단 X) 해도 V-1 알람 카드와 연계해 시간당 N건 거부 즉시 검출 가치가 있는가?

#### Q4 — 4 분류 통합 객체가 *각 분류별 다른 행위* 를 캡슐화하면 코드 가독성 ↓ 위험
- 현행: 분류별 분기가 `execute_sell` 내부에 명시적 if/elif (사이클 52 게이트 + market_closed 사후 처리 + market_order_disallowed 폴백 + insufficient_quantity break).
- 통합 후 가설: `tracker.gate(ticker)` → bool 만 반환, 분류별 다른 후속 액션은 여전히 `execute_sell` 내부에 남음. **부분 캡슐화** → 책임 분리 효과 제한적일 수 있음.
- **질문**: (a) tracker 가 *게이트 검사* 만 위임받고 (b) 거부 응답 후 등록 + 분류별 TTL 정책은 tracker 가 처리 — 이런 *제한된 위임* 설계가 매매 안전성 측면에서 (회귀 위험 / 행위 변경 영역) 적절한가? 아니면 *통합하지 말고* 사이클 56 emit cap 통합만 진행이 낫다?

#### Q5 — V-1 알람 카드 (per-ticker 시간당 5건 초과 CRITICAL) 와 R-1 의 *연계 시점*
- V-1 은 별도 사이클 후속 (분석 메모 우선순위 2위).
- R-1 의 tracker 가 *거부 발생 시각 history* 를 보유하면 V-1 발화 hook 으로 자연 흡수 가능.
- **질문**: R-1 사이클 55 에서 *알람 발화는 미구현* 하되 *history 자료구조* 는 미리 도입할 가치 (사이클 56 V-1 시 자료구조 변경 없이 hook 만 추가)?

### 2.3 자문 응답 활용 계획
- Q1~Q3 응답 → 결정 포인트 1.2 (통합 범위) 와 1.5 (TTL 정책) 확정
- Q4 응답 → SellRejectionTracker 위임 범위 확정 (게이트만 vs 게이트+후속 액션)
- Q5 응답 → history 자료구조 사전 도입 여부

---

## 3. refactor-expert 설계 발주 (도메인 자문 *후*)

### 3.1 설계 발주 제목
**[사이클 55 R-1 후속] SellRejectionTracker 행위 보존 설계 카드 (domain-expert 응답 반영)**

### 3.2 설계 산출물 요구

1. **`SellRejectionTracker` 인터페이스 명세** (도메인 자문 Q4 결과 반영)
   ```python
   # 예시 인터페이스 (도메인 자문 Q4 응답에 따라 확정)
   @dataclass
   class SellRejectionTracker:
       market_closed_blocked: dict[str, datetime]  # 사이클 52 보존
       market_closed_logged_today: set[str]        # 사이클 52 emit cap 보존
       market_order_disallowed_recent: dict[str, datetime]  # NEW (Q2 따라)
       insufficient_qty_history: dict[str, list[datetime]]  # NEW (Q5 따라, 미발화 hook)

       def should_block_sell(self, ticker: str, now: datetime) -> tuple[bool, str | None]: ...
       def register_market_closed(self, ticker: str, now: datetime) -> None: ...
       def register_market_order_disallowed(self, ticker: str, now: datetime) -> None: ...
       def register_insufficient_quantity(self, ticker: str, now: datetime) -> None: ...
       def reset_daily(self) -> None: ...
   ```

2. **행위 보존 매트릭스** (각 분류별 *현행 행위 → 통합 후 행위* 1:1 매핑)
   - 현행 `execute_sell` line 482-499 (게이트) → tracker.should_block_sell()
   - 현행 line 577-629 (market_closed 사후 처리) → tracker.register_market_closed() + 기존 stock_master 보강 분기 보존
   - 현행 line 631-637 (insufficient_quantity) → tracker.register_insufficient_quantity() (기록만) + 기존 break 보존
   - 현행 line 643-713 (market_order_disallowed 폴백) → tracker.register_market_order_disallowed() (TTL 정책 Q2 따라) + 기존 폴백 흐름 보존

3. **회귀 가드 매트릭스** (어떤 기존 테스트가 영향받는지)
   - `tests/unit/engine/test_b1_market_closed_zombie_block.py` (사이클 52, 8 시나리오) — 행위 동일성 검증
   - `tests/unit/engine/test_b3_nxt_downgrade_log_cap.py` (사이클 54, 4 시나리오) — 별 영역, 무영향 확인
   - 신규 회귀 가드 케이스 카운트 추정 (10~15 케이스 예상)

4. **호환 layer 설계** (사이클 48 `stale_tracker.py` 패턴)
   - `OrderEngine._market_closed_blocked` property → `self._sell_rejection.market_closed_blocked` 위임
   - `OrderEngine._market_closed_blocked_logged_today` property → `self._sell_rejection.market_closed_logged_today` 위임
   - 외부 코드 (테스트 등) 의 `order_engine._market_closed_*` 직접 접근 호환 보장

5. **CLAUDE.md 절대 규칙 충돌 사전 점검** (각 규칙별 영향 평가)
   - "NXT 매도 좀비 차단" — 통합 후에도 보존 (게이트 위치 동일)
   - "시장가 거부 폴백" — 통합 후에도 보존 (폴백 흐름 미변경)
   - "체결통보 race 가드" — 통합 무영향 (별 영역)
   - "_reset_daily_state" — `order_engine.reset_daily_state()` 가 `self._sell_rejection.reset_daily()` 위임 호출 (선례: 사이클 48)

### 3.3 설계 카드 산출 경로
`_workspace/cycle55_R1_design_card.md` (refactor-expert 작성, team-leader 승인 후 tdd-engineer Red 발주)

---

## 4. TDD 사이클 진입 시 분배 명세 (자문 + 설계 *후*)

### 4.1 tdd-engineer (Red 단계)
- 회귀 가드 작성: `tests/unit/engine/test_cycle55_sell_rejection_tracker.py`
- 설계 카드의 *행위 보존 매트릭스* 1:1 검증 케이스 (10~15)
- 신규 영역 케이스:
  - market_order_disallowed TTL 정책 (Q2 결과 반영)
  - insufficient_quantity history 기록 검증 (Q5 결과 반영, 발화 없음 확인)
  - reset_daily 호출 후 4 필드 일괄 clear 검증
- 호환 layer 검증: `order_engine._market_closed_blocked` 직접 접근이 tracker 와 동일 dict 참조 (`is` 동일성, 사이클 48 stale_tracker 패턴)

### 4.2 backend-dev (Green 단계)
- 신규 모듈 `src/engine/sell_rejection.py` 작성 (80~120L 예상)
- `OrderEngine.__init__` 에 `self._sell_rejection = SellRejectionTracker()` 추가
- 4 dict/set 필드를 tracker 로 이동 + property 호환 layer 추가
- `execute_sell` 의 게이트 / 사후 처리 / 폴백 분기를 tracker 메서드 위임으로 치환 (행위 변경 0)
- `OrderEngine.reset_daily_state()` 에 `self._sell_rejection.reset_daily()` 위임 호출 (1줄 추가)
- CLAUDE.md `src/engine/CLAUDE.md` 의 "order_engine.py" 섹션 동기화

### 4.3 tester (검증 단계)
- 백엔드 전체 회귀 (1776 → 1786~1791 예상)
- 사이클 52/54 회귀 가드 (`test_b1_*`, `test_b3_*`) 영향 0 확인
- 매매 hot path 통합 시나리오:
  - market_closed 폭주 시나리오 (사이클 52 재현) — 차단 정상
  - market_order_disallowed 폴백 시나리오 — 폴백 흐름 보존
  - insufficient_quantity → positions 제거 시나리오 — 자연 차단 보존
- CLAUDE.md 안전 규칙 영향 0 확인 (14 종 절대 규칙 grep + 동작 검증)

### 4.4 산출 경로
- `docs/HARNESS_CHANGELOG.md` 사이클 55 행 추가 (team-leader 직접 작성)
- `_workspace/00_leader_trading_rules.md` 영향 없음 (매매 파라미터 무변경 — 인프라 리팩토링)

---

## 5. 발주 순서 (확정)

| 단계 | 담당 | 산출물 | 예상 소요 |
|------|------|--------|----------|
| 1 | team-leader | 본 발주서 (`cycle55_R1_sell_rejection_tracker_spec.md`) | 즉시 (완료) |
| 2 | **domain-expert** | Q1~Q5 응답 (자문 메모, 매매 행위 영향 평가) | 1 cycle |
| 3 | **refactor-expert** | 설계 카드 (`cycle55_R1_design_card.md`, 행위 보존 매트릭스 + 호환 layer) | 1 cycle |
| 4 | team-leader | 설계 카드 승인 + tdd-engineer 발주 메모 | 즉시 |
| 5 | tdd-engineer | Red 회귀 가드 (`test_cycle55_sell_rejection_tracker.py`) | 1 cycle |
| 6 | backend-dev | Green 구현 (`sell_rejection.py` + `order_engine.py` 위임 치환) | 1 cycle |
| 7 | tester | 전체 회귀 + 통합 시나리오 검증 | 1 cycle |
| 8 | team-leader | CLAUDE.md 동기화 + HARNESS_CHANGELOG 사이클 55 행 추가 | 즉시 |

**총 6 cycle 예상** (사이클 52 종결 4 cycle 대비 +50%, HIGH 리팩토링 + 도메인 자문 +설계 카드 동반 정합)

---

## 6. 회귀 위험 사전 격리

### 6.1 절대 보존 항목 (CLAUDE.md 절대 규칙)
- ✅ 체결통보 구독 (H0STCNI0/H0STCNI9) — 통합 무관
- ✅ 주문번호 매핑 동기 영역 — `execute_sell` 내부 보존 (line 541-543)
- ✅ 체결통보 선행 race 가드 (`_completed_orders`) — 통합 무관
- ✅ `_reset_daily_state` 동행 clear — tracker.reset_daily() 위임으로 보존
- ✅ NXT 매도 거부 좀비 차단 (사이클 52 진입 차단) — tracker.should_block_sell() 로 이관
- ✅ 매도 시장가 거부 폴백 1회 — tracker 위임 후에도 폴백 흐름 보존
- ✅ stock_master 사후 보강 (NXT 시간대) — `execute_sell` 내부 보존 (분리 영역)

### 6.2 R-1 사이클 55 비대상 항목 (사이클 56 후속)
- ❌ 3 set emit cap 통합 (`DailyEmitCap` 헬퍼) — 사이클 56 별도 카드
- ❌ V-1 알람 발화 (per-ticker 시간당 5건 초과 CRITICAL) — 후속 사이클, 단 *history 자료구조* 사전 도입 여부 Q5 자문
- ❌ 매수 분기 통합 (`is_insufficient_cash` block_buy 패턴) — 책임 범위 외

### 6.3 회귀 위험 핫 스팟
- ⚠️ `OrderEngine._market_closed_blocked` 직접 접근하는 외부 코드 — 호환 layer (property) 필수
- ⚠️ 사이클 52 회귀 가드 8 시나리오 — 통합 후 동일 PASS 의무
- ⚠️ `execute_sell` 의 line 478-499 (현 게이트) → tracker.should_block_sell() 위임 시 *순서 보존* (`_selling.add` 직후 게이트 검사)

---

## 7. team-leader 최종 메모

R-1 은 **HIGH 리팩토링 + 매매 hot path** 라 *도메인 자문 → 설계 카드 → TDD* 순차 진행이 정합. 사이클 52 단순 진입 차단 (도메인 자문 미호출) 과 달리 4 분류 통합은 *행위 분리 유지 vs 통합* 판단이 도메인 영역.

**다음 액션**: domain-expert 에게 본 발주서 Q1~Q5 자문 요청. 응답 수신 후 refactor-expert 에 설계 카드 발주.

**비상 시 fallback**: domain-expert 응답이 *통합 부적합* 으로 결론 시 → R-1 폐기 + 사이클 56 emit cap 통합만 단독 진행 (사이클 31/52/54 3 set 동형 패턴 정리, LOW 위험).
