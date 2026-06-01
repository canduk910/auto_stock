# 사이클 B-1 — 매도 좀비 폭주 차단 (시장 closed 거부 후 외부 재호출 게이트)

> **작성일**: 2026-06-01
> **작성자**: team-leader
> **사유 분류**: 매매 안전성 결함 (CRITICAL) — 손절/익일청산 가용성 직접 위협
> **연관 사이클**: 사이클 30 (`_completed_orders` race 가드 패턴 — 동형 구조), 사이클 31 R6 (`_risk_silent_skip_logged_today` emit cap 패턴), 사이클 32 (NXT 거래가능 사전 판별), CLAUDE.md "NXT 매도 거부 좀비 차단" 정책 확장
> **출처 카드**: `_workspace/2026-06-01_log_analysis.md` B-1 섹션

---

## 1. 결함 요약 (실측 데이터)

### 증상
- **종목**: 064400 (LG씨엔에스, momentum 전략)
- **시각**: 2026-05-31T23:00:00 ~ 23:09:53 UTC = KST 08:00 ~ 08:09
- **거부 응답**: APBK0918 / KIOK0320 "장운영시간이 아닙니다"
- **빈도**: 10분간 500+ 건 (평균 2건/초)
- **종결**: 23:20 UTC (KST 08:20) 정규시간 진입 후 매도 COMPLETED (+30,100원)

### root cause (확정)
- `src/engine/order_engine.py:519-569` 의 `is_market_closed_rejection(e)` 분기:
  - 함수 *return* + WARNING 1행 + positions/DB/`_selling` 보존 + NXT 시간대면 `stock_master.nxt_tradable=False` 사후 보강.
  - **그러나** 외부에서 같은 ticker 의 `execute_sell` *재호출* 을 막는 *상태* 가 없음.
- `risk.on_tick` (또는 `donchian_swing._swing_rest_poll_loop`) 가 매 tick 마다 보유 종목의 `check_exit_signal` 평가 → STOP_LOSS / TRAILING_STOP / NEXT_DAY_CLEAR 신호 → `order_engine.execute_sell()` 진입 → KIS POST → 거부 → return → 다음 tick 반복.
- 즉 현재 가드는 *호출 내* 재시도만 차단할 뿐, *외부 재진입* 무방비.

### 매매 안전성 영향
1. **자금보전 기능 무력화 위험**: KIS rate limit 위반 시 *유효한* 손절 시도조차 거부될 수 있음. 이번엔 운좋게 손실 없이 체결되었지만 동일 시나리오에서 다음번엔 손절 불가 가능.
2. **system_logs 노이즈**: 다른 결함 (B-2/B-3 등) 가시성 저하.
3. **백엔드 자원 소모**: 매 tick KIS POST → 정상 종목 주문 지연 유발.

---

## 2. 해결 정책 (TTL 채택)

### 채택안: "KST 09:00 단순 만료"
- ticker 별 `_market_closed_blocked: dict[str, datetime]` 에 *다음 KRX 정규시간 시작 시각 (KST 09:00)* 을 expiry 로 등록.
- `execute_sell()` 진입 직후 차단 검사 → expiry 가 미경과면 *조용히 skip* (INFO 1줄 + ticker별 일일 1회 cap).
- `_reset_daily_state()` 호출 시 set clear (사이클 28~30 의 daily reset 패턴 일관).

### 비채택안 (후속 사이클로 보류)
- "정규시간 진입 후 첫 매도 성공 시 해제" — 09:00 직후에도 동일 거부가 이어지는 케이스 발생 시 별도 사이클로 보강.
- "차단 자체를 ticker 가 아닌 전 종목으로" — 다른 종목 영향 차단 + 익일청산 KRX 다운그레이드 정상 경로와 충돌 위험. 채택 안 함.

### 자문 필요 여부
- domain-expert 자문 **호출 안 함**. 본 사이클은 폭주 차단이 단일 책임 — 매매 행위 변경 없음 (positions 보존 동일, 다음 정규시간 재진입 동일).

---

## 3. TDD 사이클 — Red → Green → Verify

### 3-A. Red 발주 (tdd-engineer)

**파일**: `tests/unit/engine/test_b1_market_closed_zombie_block.py`

**필수 시나리오 (6개)**:

| # | 시나리오 | 검증 포인트 |
|---|---------|------------|
| S1 | 100회 연속 호출 시 KIS API 1회만 | mock `place_order` 가 첫 호출에서 `KisApiError(msg_cd="APBK0918", msg1="장운영시간이 아닙니다")` raise. `execute_sell(ticker="064400", strategy_id="momentum", signal=Signal.STOP_LOSS)` 를 100회 연속 호출. `place_order.call_count == 1`. `_market_closed_blocked["064400"]` 존재 + expiry == 다음 KST 09:00. positions 메모리 보존. |
| S2 | KIOK0320 도 동일 차단 | `KisApiError(msg_cd="KIOK0320", msg1="장운영시간이 아닙니다")`. 100회 호출 → place_order 1회. 주의: 분류는 `src/api/balance.py::is_market_closed_rejection` 의 `_MARKET_CLOSED_KEYWORDS` 키워드 기반. |
| S3a | `is_insufficient_quantity` 는 차단 *안 함* (회귀 가드) | 기존 break 분기 보존. `_market_closed_blocked` 에 미등록. |
| S3b | `is_market_order_disallowed` (APBK1943) 는 차단 *안 함* (회귀 가드) | 기존 `step_down + LIMIT` 지정가 5호가 폴백 호출 검증. `_market_closed_blocked` 미등록. |
| S3c | `is_insufficient_cash` 는 차단 *안 함* (회귀 가드) | 기존 분기 보존. 미등록. |
| S4 | TTL 만료 후 재진입 가능 | freezegun: 08:30 KST 거부 1회 등록. 09:01 KST 로 진행. 같은 ticker `execute_sell` → place_order 진입 (mock 성공 응답). `place_order.call_count == 2` (1회 거부 + 1회 성공). TTL 만료 시점에 `_market_closed_blocked` 에서 ticker 제거. |
| S5 | 차단은 ticker 별 (다른 종목 영향 없음) | 064400 거부 등록 후 005930 매도 호출 → 정상 진입. 005930 place_order 호출됨. 064400 여전히 차단 상태. |
| S6 | `_reset_daily_state()` 후 set clear | 064400 등록 상태에서 reset 호출. `_market_closed_blocked` 가 빈 dict. |

**추가 회귀 가드 (S7, 선택)**:
- 100회 진입 차단 시 INFO 로그 `[market_closed_blocked]` prefix 카운트 == **1** (ticker별 일일 1회 emit cap).
- 패턴: 사이클 31 R6 의 `_risk_silent_skip_logged_today: set[(ticker, strategy_id)]` 동형 → 본 사이클은 `_market_closed_blocked_logged_today: set[str]` (ticker only).

**테스트 명세 제약**:
- `pytest-asyncio` + `freezegun` 사용.
- mock 은 `unittest.mock.AsyncMock` 으로 `src.engine.order_engine.place_order` 패치 (KisApiError 직접 raise).
- KST 시각은 `from src.engine.scanner import KST_TZ` 또는 명시적 `timezone(timedelta(hours=9))`. `datetime.now()` 단독 금지 (사이클 36 NameError 선례).
- 기존 1748 PASS 무회귀 — `python -m pytest tests/unit/engine/ -q` 동시 확인.

**Red 상태 산출물**:
1. 위 6 (또는 7) 시나리오 실패 테스트 파일.
2. 실패 메시지 요약 — S1/S2/S4 는 무한 루프 또는 100회 place_order 호출로 FAIL 예상. S3 는 차단 set 자체가 없어 attribute 오류 또는 PASS — 후자라면 검증 방식 보강 (예: `_market_closed_blocked` 속성이 등록되어 있고 비어 있음을 검증).

---

### 3-B. Green 발주 (backend-dev)

**대상 파일**: `src/engine/order_engine.py`

**변경 명세**:

1. **`OrderEngine.__init__` 에 신규 필드 추가**:
   ```
   self._market_closed_blocked: dict[str, datetime] = {}
   self._market_closed_blocked_logged_today: set[str] = set()
   ```

2. **`execute_sell()` 진입 직후 (`self._selling` 가드 *전* 또는 *직후*) 차단 검사 추가**:
   - `now_kst = datetime.now(KST_TZ)` (KST 강제)
   - `expiry = self._market_closed_blocked.get(ticker)`
   - `if expiry and now_kst < expiry`: INFO 1줄 (ticker별 일일 1회 cap) + `return`.
   - `if expiry and now_kst >= expiry`: `del self._market_closed_blocked[ticker]` (자연 만료).
   - INFO 형식: `[market_closed_blocked] ticker=064400 strategy=momentum expiry=2026-06-01T09:00:00+09:00`

3. **`is_market_closed_rejection(e)` 검출 분기 내 (line 523~569 구간)** 에 다음 추가:
   ```
   next_open = _compute_next_market_open_kst(now_kst)
   self._market_closed_blocked[ticker] = next_open
   ```
   - `_compute_next_market_open_kst(now)`: now < 09:00 KST 이면 오늘 09:00, now >= 09:00 KST 이면 다음 영업일 09:00 (주말 스킵 — 평일 단순 +1일 OK, KIS 휴장 처리는 후속 사이클로 보류 — `_pending_next_day_clear` 가 어차피 휴장일 처리하므로 본 가드는 보수적이어도 안전).
   - 기존 `state.positions`/`DB`/`_selling` 보존 + NXT 사후 보강 + WARNING + `return` 동작은 **그대로 보존**.

4. **`_reset_daily_state()` 동행 clear**:
   - `scheduler.py::_reset_daily_state()` 가 `order_engine._market_closed_blocked.clear()` + `_market_closed_blocked_logged_today.clear()` 호출.
   - 또는 OrderEngine 측에 `reset_daily_state()` 헬퍼를 만들어 scheduler 가 호출. 후자 권장 (캡슐화).

5. **CLAUDE.md 핵심 안전규칙 항목 갱신** (Green 단계에서 함께):
   - 루트 `CLAUDE.md` 의 "**NXT 매도 거부 좀비 차단**" 항목에 "*진입 차단* 까지 보장 (`_market_closed_blocked` ticker별 TTL=다음 KST 09:00, `_reset_daily_state` 동행 clear)" 추가.
   - `src/engine/CLAUDE.md` 의 "**`is_market_closed_rejection(err)`**" 항목과 "절대 깨지면 안 되는 규칙" 항목에도 동일 동기화.

6. **영향 인덱스 갱신**: `python tools/test_impact/build_index.py`.

**Green 산출물**:
1. 위 코드 변경 + 신규 회귀 가드 PASS + 기존 1748 PASS 무회귀.
2. CLAUDE.md 3개 파일 동기화 diff.
3. 영향 인덱스 재생성 결과 (변경 파일 → affected tests 카운트).

---

### 3-C. Verify 발주 (tester)

**검증 시나리오**:

1. **신규 회귀 가드 6 (또는 7) 케이스 PASS**.
2. **기존 1748 PASS 무회귀** — 전체 backend pytest 수행 결과.
3. **매매 안전성 E2E**:
   - 익일청산 정상 경로 — `_execute_next_day_clear` → 시가 수신 → 30s 안정화 → NXT 지정가 매도 (정상 응답) → 차단 set 미등록 확인.
   - 손절 정상 경로 — STOP_LOSS 신호 → `execute_sell` → 정상 응답 → 차단 set 미등록 확인.
   - 둘 다 무영향이어야 함.
4. **KIS 거부 폭주 재현 (mock)**:
   - 100회 STOP_LOSS 호출 → KIS API 1회만 호출.
   - 정규시간 진입 후 동일 ticker STOP_LOSS → 정상 매도 성공.
5. **트레이더 관점 검수** (team-leader 가 결과 받아 수행):
   - 차단 INFO 1줄 형식이 운영 로그에서 식별 가능한지.
   - NXT 시간대 거부 → `stock_master.nxt_tradable=False` 사후 보강 + 차단 set 등록이 *둘 다* 발생하는지 (이중 안전망).
   - `_reset_daily_state` 후 다음날 정상 매매 가능 (차단 누락 없음).

**Verify 산출물**:
1. 전체 테스트 결과 (PASS/FAIL 카운트).
2. 매매 안전성 E2E 시나리오 결과.
3. team-leader 에게 검수 요청 메시지.

---

## 4. 사이클 종료 시 체크리스트

- [ ] `CLAUDE.md` (루트) "NXT 매도 거부 좀비 차단" 항목 *진입 차단까지 보장* 명문화
- [ ] `src/engine/CLAUDE.md` "`is_market_closed_rejection(err)`" 항목 동기화
- [ ] `src/engine/CLAUDE.md` "절대 깨지면 안 되는 규칙" 항목 동기화
- [ ] `docs/HARNESS_CHANGELOG.md` 신규 사이클 행 추가 (날짜 2026-06-01, 카드 출처 `_workspace/2026-06-01_log_analysis.md`, 백엔드 PASS 카운트 갱신)
- [ ] `_workspace/2026-06-01_log_analysis.md` B-1 섹션에 "**사이클 N 종결 (2026-06-01)**" 표시 + 잔여 카드 (B-2~V-4) 보존
- [ ] 영향 인덱스 재생성 (`tools/test_impact/build_index.py`)
- [ ] 커밋/푸시는 **사용자 명시 지시 시에만** (메모리 정책)

---

## 5. 제약 / 비범위

### 제약
- 기존 가드 분기 (`is_insufficient_quantity` / `is_insufficient_cash` / `is_market_order_disallowed` 폴백) 동작 **완전 보존**.
- NXT 시간대 `stock_master.upsert_one(nxt_tradable=False)` 사후 보강 동작 **완전 보존**.
- 매매 hot path 라 risk: HIGH — 그러나 차단 분기는 진입 게이트만 추가하므로 회귀 위험은 낮음 (포지션/주문 흐름 무변경).

### 비범위 (후속 사이클)
- B-2: `next_day_clear_drained` 로그 발화 누락 진단 (별도 사이클).
- B-3: NXT 다운그레이드 폭주 (`stock_master.nxt_tradable=False` 사후 보강 누락) — 본 사이클 B-1 의 차단 set 이 *간접적으로* 폭주 노이즈는 줄이지만 root cause (eager 갱신 누락) 는 별도 사이클.
- B-4: 자동 리포트 trade_metrics KST 경계 결함 (별도 사이클).
- R-1: `SellRejectionTracker` 단일 정책 객체로 분류 통합 (refactor, 사이클 누적 후).
- V-1: 매도 거부 폭주 실시간 알람 (CRITICAL 레벨 system_logs INSERT — 본 사이클 B-1 시정 후 *추가* 가시화).
