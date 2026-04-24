---
name: trading-test
description: "주식 자동매매시스템의 통합 테스트를 수행하는 스킬. KIS API 연동 검증, FastAPI↔React 경계면 교차 검증, Supabase 스키마 정합성, 주문 흐름 E2E, 매매 안전성 테스트를 포함한다. 테스트, 검증, QA, 버그, 정합성 확인 등을 언급하면 이 스킬을 사용할 것."
---

# 트레이딩 시스템 통합 테스트 스킬

자동매매시스템의 모듈 간 연결 정합성과 매매 흐름 안전성을 검증한다.

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

```
검증 단계:
1. FastAPI route에서 모든 엔드포인트와 응답 모델 추출
2. React api/ 디렉토리에서 모든 fetch URL과 기대 타입 추출
3. URL 경로, HTTP 메서드, 응답 필드명을 1:1 대조
4. 특히: 페이징 응답({ items: [], total, page })과 프론트 기대 구조 비교
```

### 3. Supabase 스키마 ↔ 코드 정합성

```
검증 단계:
1. DB 스키마 정의(마이그레이션 SQL)에서 테이블/컬럼 추출
2. src/models/*.py pydantic 모델의 필드와 대조
3. src/db/*.py CRUD 코드의 컬럼명과 스키마 대조
4. 특히: trade_history.status ENUM 값('PENDING','COMPLETED','PARTIAL')이
   코드의 모든 상태 전이와 일치하는지
```

### 4. 매매 로직 검증

각 전략의 매수/청산 조건이 `_workspace/00_leader_trading_rules.md` 명세와 일치하는지 검증한다.

| 검증 항목 | 검증 방법 |
|----------|----------|
| 전략별 매수 조건 | `src/engine/strategies/*.py`의 check_buy_signal()과 명세 대조 |
| 전략별 청산 조건 | check_exit_signal()과 명세 대조 |
| 전략별 비중 계산 | calc_buy_quantity()의 position_ratio와 명세 대조 |
| 중복 매수 차단 | registry.is_ticker_held_by_any() 동작 확인 |
| 전략별 자금 분배 | allocate_funds()에서 weight 기반 분배 정확성 |

### 5. 주문 안전성 시나리오

```markdown
## 정상 흐름
1. 종목 스캔 → 필터 통과 → WS 구독 → 전략별 매수 조건 감지
2. 매수가능금액 확인 → 전략 비중 계산 → 시장가 매수
3. 체결통보 수신 → 올바른 전략에 포지션 등록 → trade_history(strategy 포함) INSERT
4. 잔고 반영 → 프론트 갱신

## 부분 체결
1. 매수 주문 → 일부만 체결
2. trade_history INSERT(PARTIAL) → 잔여 물량 추적
3. 일정 시간 후 잔여 취소 → 상태 업데이트

## 청산 트리거
1. 전략별 청산 조건 도달 (손절/익절/강제청산)
2. 시장가 매도 → 체결 → 전략 state에서 포지션 제거
3. 매도 실패 시 → 재시도(최대 3회) → 실패 시 system_logs 기록 + team-leader 알림

## Rate Limit 초과 시나리오
1. 여러 종목 동시 손절 발생 → 일괄 매도 주문
2. Semaphore로 초당 20건 제한 → 큐잉
3. 지연된 주문도 순차 실행 확인
```

## 테스트 리포트 형식

```markdown
## 테스트 리포트 — {날짜}

### 요약
- 전체: {N}건 | 통과: {N}건 | 실패: {N}건 | 미검증: {N}건

### 실패 항목
#### [{번호}] {테스트명}
- **파일**: {경로}:{라인}
- **현상**: {무엇이 잘못됐는지}
- **기대**: {올바른 동작}
- **수정 제안**: {구체적 방향}
- **심각도**: 높음/중간/낮음
- **담당**: backend-dev / frontend-dev
```

## 점진적 테스트 원칙

각 모듈 완성 직후 즉시 테스트한다:
1. 인증/API 래퍼 완성 → KIS 스펙 교차 검증
2. 주문 모듈 완성 → 주문 흐름 + 안전 장치 검증
3. 매매 엔진 완성 → 전략 규칙 정확성 검증
4. FastAPI 라우트 완성 → 엔드포인트 스키마 검증
5. React 화면 완성 → FastAPI ↔ React 경계면 검증
6. 전체 통합 → E2E 시나리오 테스트
