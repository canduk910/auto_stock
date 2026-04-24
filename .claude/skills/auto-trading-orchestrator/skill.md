---
name: auto-trading-orchestrator
description: "KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하는 오케스트레이터. 팀장(트레이더)이 리더로서 백엔드(FastAPI), 프론트엔드(React), 테스터를 지휘한다. '자동매매 시스템 구축해줘', '트레이딩 시스템 개발', '매매 시스템 만들어줘', '전략 추가해줘' 등 시스템 전체 구축/확장 요청 시 이 스킬을 사용할 것. 개별 모듈만 요청하는 경우에는 해당 개별 스킬을 사용한다."
---

# Auto Trading System Orchestrator

KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하여 완성된 웹 서비스를 산출한다.

## 실행 모드: 에이전트 팀

## 시스템 아키텍처

```
[React.js Frontend] ←REST API→ [FastAPI Backend] ←KIS API→ [한국투자증권]
   (Vite)                       (Uvicorn)               │
                                    │              [WebSocket 실시간]
                                    ↓
                              [Supabase DB]
                            (PostgreSQL)
```

## 다중 전략 아키텍처

```
StrategyBase (추상 베이스)
├── MomentumStrategy
├── VolatilityBreakoutStrategy
└── (향후 추가 전략)

StrategyRegistry ← 전략 등록/비중/중복 방지
RiskManager ← on_tick에서 registry 순회, 전략별 신호 체크
OrderEngine ← strategy_id 태깅, 전략별 포지션 관리
TradingScheduler ← registry 기반 boot/run/settle
```

매매 전략의 구체적 규칙은 `_workspace/00_leader_trading_rules.md`에 정의한다.

## 에이전트 구성

| 팀원 | 에이전트 | 역할 | 스킬 | 출력 |
|------|---------|------|------|------|
| team-leader (리더) | team-leader | 매매 규칙 정의, 작업 감독 | — | 매매 규칙 명세 |
| backend-dev | backend-dev | FastAPI + KIS API + 매매 엔진 | kis-api-integration | `src/` |
| frontend-dev | frontend-dev | React.js 대시보드 | trading-dashboard | `frontend/` |
| tester | tester | 통합 테스트, 경계면 검증 | trading-test | 테스트 리포트 |

## 워크플로우

### Phase 1: 준비 — 요구사항 분석

1. 사용자 요청에서 기능 범위를 파악한다
2. `_workspace/` 디렉토리를 생성한다
3. 매매 전략 명세 확인: `_workspace/00_leader_trading_rules.md`
4. KIS API 스펙 확인: `docs/kis/README.md`

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
         prompt: "백엔드 개발자. .claude/agents/backend-dev.md 역할 정의, .claude/skills/kis-api-integration/skill.md 참조. KIS API 스펙은 docs/kis/. 모듈 완성 시 tester에게 SendMessage, API 스키마 확정 시 frontend-dev에게 SendMessage."
       },
       {
         name: "frontend-dev",
         agent_type: "frontend-dev",
         model: "opus",
         prompt: "프론트엔드 개발자. .claude/agents/frontend-dev.md 역할 정의, .claude/skills/trading-dashboard/skill.md 참조. API 스키마는 backend-dev에게 확인. 화면 완성 시 tester에게 알림."
       },
       {
         name: "tester",
         agent_type: "tester",
         model: "opus",
         prompt: "QA 테스터. .claude/agents/tester.md 역할 정의, .claude/skills/trading-test/skill.md 참조. 모듈 완성 알림 시 즉시 테스트. 버그는 해당 개발자에게, 매매 안전성 이슈는 team-leader에게 SendMessage."
       }
     ]
   )
   ```

2. 작업 등록 — 팀장(리더)이 매매 규칙 명세를 작성한 후 TaskCreate로 등록.
   작업 내용은 요구사항에 따라 동적으로 결정한다.
   팀원당 4~6개 작업이 적정. 의존성이 있는 작업은 `depends_on`으로 명시.

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
4. 팀장이 최종 검수 — 매매 규칙 명세(`_workspace/00_leader_trading_rules.md`)와 구현의 일치 확인

### Phase 5: 정리

1. 팀원들에게 종료 요청 (SendMessage)
2. 팀 정리 (TeamDelete)
3. `_workspace/` 보존 (감사 추적)
4. 사용자에게 결과 요약 보고:
   - 구현 완료 모듈 목록
   - 테스트 결과 요약 (통과/실패/미검증)
   - 알려진 제한사항
   - 실행 방법 안내

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
1. 사용자가 기능 요청
2. Phase 1: 요구사항 분석, 매매 규칙 명세 확인/작성
3. Phase 2: 팀 구성 + 작업 등록
4. Phase 3: 팀장 매매 규칙 전달 → 백엔드 → 프론트 → 점진적 테스트
5. Phase 4: 최종 통합 테스트 통과
6. Phase 5: 팀 정리 + 결과 보고

### 에러 흐름
1. Phase 3에서 tester가 경계면 불일치 발견
2. tester → 해당 개발자: 버그 리포트 (파일:라인 + 수정 제안)
3. 개발자 수정 → tester 재검증
4. tester가 매매 안전성 이슈 발견 → team-leader 보고
5. team-leader → 개발자: 수정 지시 (현업 관점 명확화)
6. 수정 → 재검증 → 통과
