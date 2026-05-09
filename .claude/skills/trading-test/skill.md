---
name: trading-test
description: "주식 자동매매시스템의 사후 통합 테스트를 수행하는 스킬. 모듈 결합 후 KIS API 연동 검증, FastAPI↔React 경계면 교차 검증, Supabase 스키마 정합성, 주문 흐름 E2E, 매매 안전성 시나리오, Playwright E2E를 포함한다. 단위 단계 Red/Green 사이클은 tdd-cycle 스킬이 담당하며, 이 스킬은 tdd-engineer 사이클 종료 후 통합/안전성 책임. 테스트, 검증, QA, 버그, 정합성 확인, 통합 검증, E2E 등을 언급하면 이 스킬을 사용할 것."
---

# Trading System Integration Test Skill

자동매매시스템의 모듈 간 연결 정합성과 매매 흐름 안전성을 검증한다. **단위 행위 검증(Red→Green)은 tdd-cycle 스킬이 담당**하며, 이 스킬은 사이클 산출물이 결합되었을 때의 통합·경계면·운영 시나리오를 책임진다.

## 책임 경계

| 단계 | 담당 스킬 | 산출물 |
|------|----------|--------|
| 단위 행위 (함수/메서드/컴포넌트) | tdd-cycle | `tests/unit/`, `frontend/**/__tests__/` |
| 통합 (모듈 결합, 경계면, DB↔코드) | **trading-test (이 스킬)** | `tests/integration/`, `tests/contract/` |
| E2E (브라우저, 사용자 흐름) | **trading-test (이 스킬)** | `e2e/*.spec.ts` |
| 매매 안전성 시나리오 | **trading-test (이 스킬)** | `_workspace/test_report.md` |

## 검증 영역

### 1. KIS API 연동 정합성

KIS API 스펙(`docs/kis/*.md`)과 구현 코드를 교차 비교한다.

```
검증 단계:
1. docs/kis/README.md에서 프로젝트 사용 API 목록 확인
2. src/api/*.py에서 TR_ID 사용처를 Grep으로 검색
3. 각 TR_ID의 스펙(URL, Method, Request, Response)과 코드 비교
4. Response Example의 필드명과 코드의 파싱 키 정확히 일치하는지
5. 모의투자/실전 환경별 도메인 전환이 올바른지
```

### 2. FastAPI ↔ React 경계면 검증

| 검증 대상 | FastAPI 측 | React 측 |
|----------|-----------|----------|
| 엔드포인트 URL | `src/routes/*.py` @router 데코레이터 | `frontend/src/api/*.ts` fetch URL |
| 응답 필드명 | `src/models/response.py` pydantic 모델 | `frontend/src/types/*.ts` 타입 정의 |
| 페이징 파라미터 | `page`, `size` Query 파라미터 | TanStack Table 페이징 요청 |
| 에러 응답 형식 | HTTPException detail 구조 | 프론트 에러 핸들링 |

### 3. Supabase 스키마 ↔ 코드 정합성

```
1. DB 스키마 정의(마이그레이션 SQL)에서 테이블/컬럼 추출
2. src/models/*.py pydantic 모델의 필드와 대조
3. src/db/*.py CRUD 코드의 컬럼명과 스키마 대조
4. trade_history.status ENUM('PENDING','COMPLETED','PARTIAL','CANCELLED')과
   코드의 모든 상태 전이 일치 확인
```

### 4. 매매 로직 검증 (통합 단계)

각 전략의 매수/청산 조건이 `_workspace/00_leader_trading_rules.md` 명세와 일치하는지 통합 환경에서 재검증.

| 검증 항목 | 검증 방법 |
|----------|----------|
| 전략별 매수 조건 | `tests/integration/test_buy_flow.py`로 시뮬레이션 가격 → 매수 발생 검증 |
| 전략별 청산 조건 | `tests/integration/test_sell_flow.py` |
| 전략별 비중 계산 | `tests/integration/test_fund_allocation.py` |
| 전략 간 중복 차단 | `tests/integration/test_multi_strategy_block.py` |
| 보드 전환 시 포지션 유지 | `tests/integration/test_board_transition.py` |

### 5. 주문 안전성 시나리오 (통합 + E2E)

| 시나리오 | 위치 |
|---------|------|
| 정상 매수→체결→포지션 등록 | `tests/integration/test_buy_flow.py` |
| 부분 체결 PARTIAL → 30초 잔여 취소 | `tests/integration/test_partial_fill.py` |
| 체결통보 선행 race 가드 | `tests/integration/test_chegyeol_race.py` |
| 익일 청산 NXT 프리 안정화 30초 | `tests/integration/test_next_day_clear.py` |
| 15:20 강제청산 (KRX_MAIN만) | `tests/integration/test_force_clear_1520.py` |
| Rate Limit 초당 20건 큐잉 | `tests/integration/test_rate_limit.py` |
| 잔고부족 매수 락 (900초) | `tests/integration/test_buy_block_low_funds.py` |

### 6. Playwright E2E (Phase F)

| 시나리오 | 파일 |
|---------|------|
| 시작→감시→정지 + 이중확인 | `e2e/trading-flow.spec.ts` |
| 비중 변경 + 이중확인 모달 | `e2e/settings.spec.ts` |
| 거래 내역 페이징/필터/탭 전환 | `e2e/history.spec.ts` |
| AI 자문 적용/거절 흐름 | `e2e/recommendations.spec.ts` |

## 결함 발견 시 처리 — 회귀 테스트 영구화

통합/E2E에서 결함을 발견하면 **반드시 tdd-engineer에 회귀 테스트 의뢰**한다. 단순 핫픽스로 끝내지 않는다.

```
발견 → 임시 재현 코드 작성 → tdd-engineer에 SendMessage:
  "결함 X 재현 케이스 첨부. tests/unit/.../ 또는 tests/integration/.../ 에
   회귀 테스트로 추가 부탁. 명세 출처: <파일:라인>."
→ tdd-engineer Red 사이클 진행 → 개발자 Green
→ tester 재검증
```

## 테스트 리포트 형식

```markdown
## 테스트 리포트 — {날짜}

### 단위/통합/E2E 통계
- 단위(tdd-cycle): 통과 N / 실패 N
- 통합: 통과 N / 실패 N
- 계약: 통과 N / 실패 N
- E2E: 통과 N / 실패 N

### 실패 항목
#### [{번호}] {테스트명}
- **레이어**: 단위 / 통합 / 계약 / E2E
- **파일**: {경로}:{라인}
- **현상**: {무엇이 잘못됐는지}
- **기대**: {올바른 동작}
- **수정 제안**: {구체적 방향}
- **심각도**: 높음/중간/낮음
- **회귀 테스트 의뢰**: tdd-engineer에 ✅/❌
- **담당**: backend-dev / frontend-dev
```

## TDD 페어링 프로토콜

- tdd-engineer로부터 모듈 완성 알림(`SendMessage`)을 받으면 즉시 통합 검증 시작
- 통합 결함을 단위 테스트로 환원할 수 있으면 tdd-engineer에 의뢰 (회귀 영구화)
- E2E 단계에서 시간 의존 결함은 단위로 환원하기 어려움 — E2E에 유지하되 명확한 시나리오로 기록
- tester가 단위 영역 침범 X — 그 영역은 tdd-cycle이 책임

## 점진적 테스트 원칙 (모듈 완성 직후)

1. 인증/API 래퍼 → KIS 스펙 교차 검증 + 통합 호출 검증
2. 주문 모듈 → 매수/매도/체결 흐름 + 안전 장치 통합
3. 매매 엔진 → 전략 규칙 통합 + 보드 전환
4. FastAPI 라우트 → 19개 엔드포인트 계약
5. React 화면 → 경계면 + 컴포넌트 결합 + Playwright E2E
6. 전체 통합 → 매매 안전성 시나리오 일괄
