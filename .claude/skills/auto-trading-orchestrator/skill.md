---
name: auto-trading-orchestrator
description: "KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하는 오케스트레이터. 팀장(트레이더)이 리더로서 백엔드(FastAPI), 프론트엔드(React), 테스터를 지휘한다. '자동매매 시스템 구축해줘', '트레이딩 시스템 개발', '매매 시스템 만들어줘' 등 시스템 전체 구축 요청 시 이 스킬을 사용할 것. 개별 모듈만 요청하는 경우에는 해당 개별 스킬을 사용한다."
---

# Auto Trading System Orchestrator

KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하여 완성된 웹 서비스를 산출한다.

## 실행 모드: 에이전트 팀

## 시스템 아키텍처

```
[React.js Frontend] ←REST API→ [FastAPI Backend] ←KIS API→ [한국투자증권]
     (Vercel)                   (AWS EC2)              │
                                    │              [WebSocket 실시간]
                                    ↓
                              [Supabase DB]
                           (PostgreSQL)
                                    ↑
                          [AWS EventBridge + Lambda]
                           (스케줄러: 08:25, 16:10)
```

## 에이전트 구성

| 팀원 | 에이전트 | 역할 | 스킬 | 출력 |
|------|---------|------|------|------|
| team-leader (리더) | team-leader | 매매 규칙 정의, 작업 감독 | — | 매매 규칙 명세 |
| backend-dev | backend-dev | FastAPI + KIS API + 매매 엔진 | kis-api-integration | `src/` |
| frontend-dev | frontend-dev | React.js 대시보드 | trading-dashboard | `frontend/` |
| tester | tester | 통합 테스트, 경계면 검증 | trading-test | 테스트 리포트 |

## 워크플로우

### Phase 1: 준비 — 요구사항 분석

1. 사용자 요청에서 매매 전략, 기능 범위를 파악한다
2. `_workspace/` 디렉토리를 생성한다
3. KIS API 스펙 확인: `docs/kis/README.md` 읽기
4. 팀장(리더)이 매매 규칙 명세를 작성한다:
   - 종목 필터링 조건 (시총 1,000억+, 거래대금 200억+, 최대 40개)
   - 매수 규칙 (시가 대비 +29.5%, 투자대금 25% 비중, 시장가)
   - 당일 손절 (매수가 대비 -7.5%)
   - 익일 청산 (갭상승 +10% 트레일링 스탑 -2% / 그 외 즉시 매도)
   - 스케줄 (08:25 기동 → 08:30~16:00 매매 → 16:10 정산)
   - 부분 체결 처리, Rate Limit 대응

### Phase 2: 팀 구성

1. 팀 생성:
   ```
   TeamCreate(
     team_name: "trading-dev-team",
     members: [
       {
         name: "backend-dev",
         agent_type: "backend-dev",
         model: "opus",
         prompt: "당신은 자동매매시스템의 백엔드 개발자입니다. .claude/agents/backend-dev.md를 읽고 역할을 파악하세요. .claude/skills/kis-api-integration/skill.md를 참조하여 구현하세요. KIS API 스펙은 docs/kis/에 있습니다. 모듈 완성 시 tester에게 SendMessage하고, API 스키마 확정 시 frontend-dev에게 SendMessage하세요."
       },
       {
         name: "frontend-dev",
         agent_type: "frontend-dev",
         model: "opus",
         prompt: "당신은 자동매매시스템의 프론트엔드 개발자입니다. .claude/agents/frontend-dev.md를 읽고 역할을 파악하세요. .claude/skills/trading-dashboard/skill.md를 참조하여 React.js 대시보드를 구현하세요. API 스키마는 backend-dev에게 SendMessage로 확인하세요. 화면 완성 시 tester에게 알려주세요."
       },
       {
         name: "tester",
         agent_type: "tester",
         model: "opus",
         prompt: "당신은 자동매매시스템의 QA 테스터입니다. .claude/agents/tester.md를 읽고 역할을 파악하세요. .claude/skills/trading-test/skill.md를 참조하여 통합 테스트를 수행하세요. 모듈 완성 알림 시 즉시 테스트하세요. 버그는 해당 개발자에게, 매매 안전성 이슈는 team-leader에게 SendMessage하세요."
       }
     ]
   )
   ```

2. 작업 등록:
   ```
   TaskCreate(tasks: [
     // 백엔드 — 인프라
     { title: "환경 설정 및 프로젝트 초기화", description: "FastAPI 프로젝트 구조, .env, config.py, Supabase 테이블 생성", assignee: "backend-dev" },
     { title: "인증 모듈", description: "OAuth 토큰 발급/갱신, Hashkey, 접속키 발급", assignee: "backend-dev" },
     { title: "REST API 공통 래퍼", description: "헤더 구성, Rate Limit(Semaphore), 에러 처리, 재시도", assignee: "backend-dev", depends_on: ["인증 모듈"] },
     
     // 백엔드 — 매매 핵심
     { title: "종목 필터링 모듈", description: "조건검색 API 연동, 시총/거래대금 필터, 최대 40개 제한", assignee: "backend-dev", depends_on: ["REST API 공통 래퍼"] },
     { title: "WebSocket 실시간 모듈", description: "시세 구독, 체결통보(H0STCNI0) 수신/복호화, Heartbeat, 재연결", assignee: "backend-dev", depends_on: ["인증 모듈"] },
     { title: "주문 모듈", description: "현금 매수/매도(TTTC0011U/0012U), 정정취소, 잔고/매수가능 조회", assignee: "backend-dev", depends_on: ["REST API 공통 래퍼"] },
     { title: "매매 엔진", description: "시가+29.5% 매수, -7.5% 손절, 익일 청산(갭상승/트레일링스탑), 중복매수 차단, 부분체결 관리", assignee: "backend-dev", depends_on: ["주문 모듈", "WebSocket 실시간 모듈", "종목 필터링 모듈"] },
     { title: "스케줄러", description: "08:25 기동, 08:30~16:00 매매, 16:10 정산, DB 동기화", assignee: "backend-dev", depends_on: ["매매 엔진"] },
     
     // 백엔드 — 프론트 연동 API
     { title: "FastAPI 라우트", description: "/api/trading/*, /api/balance, /api/history, /api/performance 엔드포인트", assignee: "backend-dev", depends_on: ["주문 모듈"] },
     
     // 프론트엔드
     { title: "프론트 프로젝트 초기화", description: "React + TypeScript + TanStack Query + Tailwind 설정", assignee: "frontend-dev" },
     { title: "구동 관리 화면", description: "시작/정지 버튼 + 이중확인 모달 + 상태 인디케이터", assignee: "frontend-dev", depends_on: ["FastAPI 라우트"] },
     { title: "매매 실적 화면", description: "요약 카드 + 일별/월별 차트", assignee: "frontend-dev", depends_on: ["FastAPI 라우트"] },
     { title: "거래 내역 화면", description: "TanStack Table + 서버사이드 페이징 + 필터", assignee: "frontend-dev", depends_on: ["FastAPI 라우트"] },
     { title: "잔고 조회 화면", description: "예수금 + 보유종목 테이블 + 자동 갱신", assignee: "frontend-dev", depends_on: ["FastAPI 라우트"] },
     
     // 테스트
     { title: "인증/API 래퍼 테스트", description: "토큰 관리, Rate Limit, KIS 스펙 교차 검증", assignee: "tester", depends_on: ["인증 모듈", "REST API 공통 래퍼"] },
     { title: "주문 흐름 E2E 테스트", description: "매수→체결→잔고→손절/청산 전체 흐름 + 부분 체결", assignee: "tester", depends_on: ["매매 엔진"] },
     { title: "FastAPI↔React 경계면 검증", description: "엔드포인트 URL, 응답 스키마, 타입 교차 비교", assignee: "tester", depends_on: ["구동 관리 화면", "매매 실적 화면", "거래 내역 화면", "잔고 조회 화면"] },
     { title: "매매 안전성 테스트", description: "중복 매수 차단, 손절 트리거, 트레일링 스탑, Rate Limit, 스케줄러", assignee: "tester", depends_on: ["매매 엔진", "스케줄러"] }
   ])
   ```

### Phase 3: 개발 — 팀 자체 조율

**실행 방식:** 감독자 패턴 — 팀장(리더)이 감독, 팀원 자체 조율

1. 팀장(리더)이 매매 규칙 명세를 `_workspace/00_leader_trading_rules.md`에 작성
2. 팀장 → backend-dev: 매매 규칙 + 기술 요구사항 SendMessage
3. 팀장 → frontend-dev: 화면 요구사항 SendMessage
4. 팀장 → tester: 테스트 시나리오 + 엣지 케이스 SendMessage

**팀원 간 통신 규칙:**
- backend-dev → frontend-dev: API 스키마 확정 시 즉시 공유
- backend-dev → tester: 모듈 완성 시 인터페이스 정보와 함께 알림
- frontend-dev → tester: 화면 완성 시 알림
- tester → backend-dev/frontend-dev: 버그 리포트 (파일:라인 + 수정 제안)
- tester → team-leader: 매매 안전성 이슈 즉시 보고

**산출물 저장:**

| 팀원 | 출력 경로 |
|------|----------|
| team-leader | `_workspace/00_leader_trading_rules.md` |
| backend-dev | `src/` 하위 모듈 |
| frontend-dev | `frontend/` 하위 |
| tester | `_workspace/test_report.md` |

**리더 모니터링:**
- TaskGet으로 전체 진행률 확인
- 팀원 유휴 알림 수신 시 다음 작업 안내
- backend-dev ↔ frontend-dev 스키마 불일치 시 중재
- tester의 매매 안전성 이슈 보고 시 작업 중단 여부 판단

### Phase 4: 통합 및 검증

1. 모든 팀원 작업 완료 대기 (TaskGet)
2. tester의 최종 통합 테스트 리포트 확인
3. 미해결 이슈가 있으면 해당 팀원에게 수정 지시
4. 팀장이 최종 검수:
   - 매수 조건(+29.5%)이 정확히 구현되었는가?
   - 손절(-7.5%)이 즉시 트리거되는가?
   - 익일 청산 로직(갭상승 분기 + 트레일링 스탑)이 올바른가?
   - 부분 체결 상태 관리가 되는가?
   - 스케줄러가 정시에 동작하는가?

### Phase 5: 정리

1. 팀원들에게 종료 요청 (SendMessage)
2. 팀 정리 (TeamDelete)
3. `_workspace/` 보존 (감사 추적)
4. 사용자에게 결과 요약 보고:
   - 구현 완료 모듈 목록
   - 테스트 결과 요약 (통과/실패/미검증)
   - 모의투자 테스트 가이드
   - 알려진 제한사항
   - 실전 전환 시 변경 사항 (.env의 KIS_ENV=real)

## 데이터 흐름

```
[team-leader/리더]
    │
    ├─ 매매 규칙 ──→ [backend-dev]
    │                    │
    │                    ├─ API 스키마 ──→ [frontend-dev]
    │                    │                      │
    │                    ├─ 모듈 완성 ──→ [tester] ←─ 화면 완성 ┘
    │                    │                   │
    │                    ←─ 버그 리포트 ─────┘
    │
    ←─ 매매 안전성 이슈 ────────────────────┘
    ←─ 테스트 리포트 ───────────────────────┘
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 팀원 1명 실패 | 리더가 SendMessage로 상태 확인 → 재시작 또는 작업 재할당 |
| KIS API 스펙 불명확 | backend-dev → team-leader 확인 → 리더가 현업 지식으로 해석 |
| 프론트-백엔드 스키마 불일치 | tester가 양쪽에 알림 → 리더가 중재 |
| 매매 안전성 이슈 | tester → team-leader 즉시 → 리더가 작업 중단 여부 판단 |
| 타임아웃 | 현재까지 산출물 보존, 미완료 항목 목록화 |

## 테스트 시나리오

### 정상 흐름
1. 사용자가 "자동매매 시스템 만들어줘" 요청
2. Phase 1: 매매 전략 분석 (시가+29.5% 매수, 손절, 익일 청산)
3. Phase 2: 팀 구성 (4명) + 작업 등록 (18개)
4. Phase 3: 팀장 매매 규칙 전달 → 백엔드(FastAPI+KIS) → 프론트(React) → 점진적 테스트
5. Phase 4: 최종 통합 테스트 통과
6. Phase 5: 모의투자 테스트 가이드와 함께 결과 보고
7. 예상 결과: `src/`(백엔드) + `frontend/`(프론트) + Supabase 스키마 완성

### 에러 흐름
1. Phase 3에서 tester가 손절 트리거 오류 발견 (-7.5% 조건이 매수가가 아닌 시가 기준으로 구현)
2. tester → team-leader: 매매 안전성 이슈 보고
3. team-leader → backend-dev: "손절 기준은 매수 체결가 대비여야 함" 명확화
4. backend-dev 수정 → tester 재검증 → 통과
