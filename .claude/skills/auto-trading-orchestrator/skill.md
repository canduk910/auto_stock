---
name: auto-trading-orchestrator
description: "KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하는 오케스트레이터. 팀장(트레이더)이 리더로서 TDD 엔지니어, 백엔드(FastAPI), 프론트엔드(React), 테스터를 지휘한다. **TDD(Red→Green→Refactor) 사이클을 기본 워크플로우로 강제**하며, tdd-engineer가 Red 테스트를 먼저 작성한 뒤 개발자가 Green 구현을 한다. '자동매매 시스템 구축해줘', '트레이딩 시스템 개발', '매매 시스템 만들어줘', '전략 추가해줘', '기능 추가/수정' 등 시스템 전체 구축/확장 요청 시 이 스킬을 사용할 것. 개별 모듈만 요청하는 경우에는 해당 개별 스킬을 사용한다."
---

# Auto Trading System Orchestrator (TDD-First)

KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하여 완성된 웹 서비스를 산출한다. **모든 코드 변경은 Red→Green→Refactor 사이클을 거친다.**

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
├── LongTailVolatilityStrategy
└── DonchianSwingStrategy

StrategyRegistry ← 전략 등록/비중/중복 방지
RiskManager ← on_tick에서 registry 순회, 전략별 신호 체크
OrderEngine ← strategy_id 태깅, 전략별 포지션 관리
TradingScheduler ← registry 기반 boot/run/settle
```

매매 전략의 구체적 규칙은 `_workspace/00_leader_trading_rules.md`에 정의한다.

## 에이전트 구성 (TDD 통합 후)

| 팀원 | 에이전트 | 역할 | 스킬 | 출력 |
|------|---------|------|------|------|
| team-leader (리더) | team-leader | 매매 규칙 정의, 작업 감독 | — | 매매 규칙 명세 |
| **tdd-engineer** | tdd-engineer | **Red 테스트 선작성 + Green 검증 + 영향 인덱스 갱신** | **tdd-cycle, test-impact-index** | `tests/`, `frontend/**/__tests__/`, `e2e/`, `_workspace/red/` |
| backend-dev | backend-dev | FastAPI + KIS API + 매매 엔진 | kis-api-integration | `src/` |
| frontend-dev | frontend-dev | React.js 대시보드 | trading-dashboard | `frontend/` |
| tester | tester | 사후 통합/경계면/안전성 검증 | trading-test | 테스트 리포트 |

## 워크플로우

### Phase 0: 컨텍스트 확인 — 초기/후속/부분 재실행 판별

1. `_workspace/` 존재 여부 확인
2. `_workspace/test_index.yaml` 존재 시 마지막 사이클 결과 로드
3. 사용자 요청 유형 판별:
   - **초기 실행**: `_workspace/` 미존재 → Phase 1부터 전체 진행
   - **부분 재실행**: 기존 산출물 + 사용자가 특정 부분 수정 요청 → 해당 행위만 새 사이클로
   - **새 실행**: 기존 `_workspace/`를 `_workspace_prev/`로 이동 후 Phase 1부터

### Phase 1: 준비 — 요구사항 분석

1. 사용자 요청에서 기능 범위 파악
2. `_workspace/` 디렉토리 생성 (필요 시 `_workspace/red/`도)
3. 매매 전략 명세 확인: `_workspace/00_leader_trading_rules.md`
4. KIS API 스펙 확인: `docs/kis/README.md`

### Phase 2: 팀 구성

```
TeamCreate(
  team_name: "trading-tdd-team",
  members: [
    {
      name: "tdd-engineer",
      agent_type: "tdd-engineer",
      model: "opus",
      prompt: "TDD 엔지니어. .claude/agents/tdd-engineer.md 역할, .claude/skills/tdd-cycle/skill.md + .claude/skills/test-impact-index/skill.md 참조. 명세 수신 시 Red 테스트 선작성 → backend-dev/frontend-dev에 SendMessage. Green 검증 후 영향 인덱스 갱신."
    },
    {
      name: "backend-dev",
      agent_type: "backend-dev",
      model: "sonnet",
      prompt: "백엔드 개발자. .claude/agents/backend-dev.md, .claude/skills/kis-api-integration/skill.md 참조. **Red 테스트 수신 후에만** 최소 구현 작성. tdd-engineer에 Green 알림. 모듈 완성 시 tester에 통합 검증 의뢰."
    },
    {
      name: "frontend-dev",
      agent_type: "frontend-dev",
      model: "sonnet",
      prompt: "프론트엔드 개발자. .claude/agents/frontend-dev.md, .claude/skills/trading-dashboard/skill.md 참조. **Red 테스트 수신 후** Green 구현. tdd-engineer에 Green 알림. 화면 완성 시 tester에 알림."
    },
    {
      name: "tester",
      agent_type: "tester",
      model: "opus",
      prompt: "QA 테스터. .claude/agents/tester.md, .claude/skills/trading-test/skill.md 참조. Red/Green 사이클은 tdd-engineer 담당. tester는 모듈 결합 후 통합/경계면/E2E 검증. 결함은 tdd-engineer에 회귀 테스트 의뢰."
    }
  ]
)
```

### Phase 2.5: 명세 → 행위 분해 (TDD 사이클의 입력)

이 단계가 TDD를 강제하는 핵심이다. **개발자에게 작업을 분배하기 전에** team-leader와 tdd-engineer가 함께 명세를 검증 가능한 행위 단위로 분해한다.

1. team-leader가 매매 규칙/기능 명세를 `_workspace/00_leader_trading_rules.md`에 작성
2. tdd-engineer가 명세를 읽고 검증 가능한 행위 목록을 `_workspace/red/_behaviors.md`에 작성
3. 모호한 항목은 team-leader에 SendMessage로 즉시 확인
4. team-leader 승인 후 Phase 3 사이클 시작

행위 분해 예시 (전략 추가 요청):
```
명세: "VolatilityBreakout 전략에 보드별 K값 분리 추가"
→ 행위:
  1. K값이 3개 보드(KRX_MAIN, NXT_PRE, NXT_POST)별로 저장된다
  2. 보드 시가 미확정 시 해당 보드 target_price는 None이다
  3. 보드 시가 확정 시 target_price = open + K * prev_range로 계산된다
  4. 보드별 target 돌파 시 BUY 신호가 해당 보드에서 발생한다
  5. PRE_NXT 보드 매수 후 KRX_MAIN으로 보드 전환 시 포지션 유지된다
```

### Phase 3: TDD 사이클 — Red → Green → Refactor

**한 행위 = 한 사이클**. 위에서 분해한 행위 N개에 대해 N번 반복한다.

```
[행위 i 시작]
   │
   ├─ ① tdd-engineer: Red 작성
   │     ├─ tests/ 또는 frontend/**/__tests__/ 에 실패 테스트 작성
   │     ├─ pytest -x / vitest run 으로 RED 확인
   │     └─ _workspace/red/<feature-i>.md 에 의도+결과 기록
   │
   ├─ ② tdd-engineer → backend-dev/frontend-dev: SendMessage("Red 준비됨, 행위 i")
   │
   ├─ ③ 개발자: 최소 구현 (Green)
   │     └─ SendMessage to tdd-engineer: "구현 완료"
   │
   ├─ ④ tdd-engineer: 테스트 재실행
   │     ├─ Green 확인 → ⑤
   │     └─ Red 유지 → 원인 진단 → 테스트 결함 vs 구현 결함 결정 → 해당 측에 회신
   │
   ├─ ⑤ Refactor (선택)
   │     ├─ 개발자가 코드 정리 → tdd-engineer가 Green 유지 모니터링
   │     └─ Refactor 중 RED 발생 시 즉시 되돌림
   │
   └─ ⑥ 인덱스 갱신
         ├─ tdd-engineer: build_index.py + build_index_frontend.mjs 실행
         └─ _workspace/test_index.yaml 커밋
```

**행위 간 병렬화:** 의존성 없는 행위는 tdd-engineer가 동시에 여러 개의 Red를 띄워두고 개발자들이 병렬로 Green을 만들 수 있다. team-leader가 의존 그래프를 결정.

**모듈 완성 트리거:** 한 모듈에 속한 모든 행위가 Green이 되면 tdd-engineer가 tester에 SendMessage로 통합 검증 의뢰.

### Phase 4: 통합 및 안전성 검증

1. tester가 모듈 완성 알림을 받으면 즉시 시작
2. 양쪽 동시 읽기로 경계면 검증 (KIS 스펙↔구현, FastAPI↔React, DB↔모델)
3. 매매 안전성 시나리오 실행 (중복 매수, 부분 체결, 체결통보 race, 강제청산, Rate Limit)
4. Playwright E2E 4개 시나리오 실행
5. 결함 발견 시 → tdd-engineer에 회귀 테스트 의뢰 → Phase 3 사이클로 복귀
6. 최종 통합 리포트: `_workspace/test_report.md`

### Phase 5: 정리

1. 팀원 종료 요청 (SendMessage)
2. 팀 정리 (TeamDelete)
3. `_workspace/` 보존 (감사 추적)
4. 사용자 보고:
   - 추가/수정된 행위 N개 → 모두 Green
   - 사이클 산출물: 테스트 코드, 구현 코드, 인덱스 갱신
   - 테스트 통계: 단위/통합/계약/E2E 통과 수
   - 알려진 제한사항
   - 실행 방법

## 데이터 흐름 (TDD 통합 후)

```
[team-leader/리더]
    │ 매매 규칙
    ▼
[tdd-engineer] ←──── 명세 검증/행위 분해 ────→ [team-leader]
    │ Red 준비
    ▼
[backend-dev / frontend-dev]
    │ Green 구현
    ▼
[tdd-engineer] ── 인덱스 갱신 ──→ _workspace/test_index.yaml
    │ 모듈 완성 알림
    ▼
[tester]
    │ 통합/경계면/E2E
    ├── 결함 발견 시 ──→ [tdd-engineer] (회귀 테스트로)
    └── 안전성 이슈 ──→ [team-leader] (작업 중단 판단)
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 개발자가 Red 없이 구현 시도 | tdd-engineer가 거부 → team-leader가 명세 분해 재시작 |
| Red가 즉시 통과 (false-red) | 명세 해석 오류 또는 이미 구현됨 — tdd-engineer가 사이클 중단 후 team-leader 확인 |
| Green 후 다른 테스트 깨짐 | 회귀 발생 — 원인 모듈 식별 후 같은 사이클에서 함께 Green 만들기 |
| 인덱스 정확도 의심 | manual_overrides.yaml 보강 + main 브랜치 풀 실행으로 안전망 |
| 매매 안전성 이슈 | tester → team-leader 즉시 → 작업 중단 판단 |
| 팀원 1명 실패 | 리더가 SendMessage 상태 확인 → 재시작 또는 작업 재할당 |
| 타임아웃 | 산출물 보존, 미완료 항목 목록화 |

## 테스트 시나리오

### 정상 흐름
1. 사용자가 "VB 전략에 보드별 K값 분리 추가" 요청
2. Phase 1: `_workspace/00_leader_trading_rules.md` 읽기
3. Phase 2: 4명 팀 구성
4. Phase 2.5: team-leader가 명세 작성, tdd-engineer가 5개 행위로 분해 → 승인
5. Phase 3: 5번의 Red→Green→Refactor 사이클 (병렬 가능 항목은 동시 진행)
6. 매 사이클 종료 시 인덱스 갱신
7. Phase 4: tester가 보드 전환 통합 + Playwright E2E 검증
8. Phase 5: 팀 정리 + 결과 보고

### 에러 흐름
1. Phase 3 사이클 ②에서 backend-dev가 Red 없이 구현 푸시 시도
2. tdd-engineer가 거부 + team-leader에 보고
3. team-leader가 행위 분해 누락분 추가
4. Red 준비 후 정상 사이클 진입
5. Phase 4에서 tester가 보드 전환 시 포지션 누락 결함 발견
6. → tdd-engineer에 회귀 테스트 의뢰 → Phase 3 추가 사이클로 fix
7. tester 재검증 통과 후 Phase 5

## 후속 작업 키워드 (재실행/부분 수정)

이 스킬은 다음 표현에서도 트리거된다:
- "다시 실행", "재실행", "업데이트"
- "{전략명}만 다시 테스트 작성"
- "이전 결과 기반으로 ~ 보강"
- "~ 회귀 테스트 추가"
- "~ 영향 인덱스 갱신"
