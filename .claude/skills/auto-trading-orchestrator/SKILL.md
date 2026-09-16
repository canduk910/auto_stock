---
name: auto-trading-orchestrator
description: "KIS OpenAPI 기반 주식 자동매매시스템 개발 팀을 조율하는 오케스트레이터. 팀장(트레이더)이 리더로서 도메인 전문가(데이/스윙 트레이더), TDD 엔지니어, 백엔드(FastAPI), 프론트엔드(React), 테스터, 리팩토링 전문가를 지휘한다. **TDD(Red→Green→Refactor) 사이클을 기본 워크플로우로 강제**하며, tdd-engineer가 Red 테스트를 먼저 작성한 뒤 개발자가 Green 구현을 한다. 매매 의사결정·파라미터·시장 행태 자문은 domain-expert 가 *깊이있는 권고* 를 제공하고, 사이클 5회 누적 또는 명시 요청 시 refactor-expert 가 *행위 보존 리팩토링* 을 검토한다. '자동매매 시스템 구축해줘', '트레이딩 시스템 개발', '매매 시스템 만들어줘', '전략 추가해줘', '기능 추가/수정', '리팩토링', '코드 정리', '도메인 자문' 등 시스템 전체 구축/확장/유지보수 요청 시 이 스킬을 사용할 것. 개별 모듈만 요청하는 경우에는 해당 개별 스킬을 사용한다."
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

## 에이전트 구성 (TDD + 도메인 자문 + 리팩토링 통합 후)

| 팀원 | 에이전트 | 역할 | 스킬 | 출력 |
|------|---------|------|------|------|
| team-leader (리더) | team-leader | 매매 규칙 *정의 + 감독*, 작업 분배, 산출물 검수 | — | 매매 규칙 명세 |
| **domain-expert** | domain-expert | 데이/스윙 트레이더 출신 *깊이있는 자문* — 신규 전략, 파라미터 결정, 시장 미시구조, 보드 행태, 시장 레짐 | **domain-consult** | `_workspace/domain_consult/` |
| **tdd-engineer** | tdd-engineer | **Red 테스트 선작성 + Green 검증 + 영향 인덱스 갱신** | **tdd-cycle, test-impact-index, kis-mcp-query** | `tests/`, `frontend/**/__tests__/`, `e2e/`, `_workspace/red/` |
| backend-dev | backend-dev | FastAPI + KIS API + 매매 엔진 | kis-api-integration, **kis-mcp-query** | `src/` |
| frontend-dev | frontend-dev | React.js 대시보드 | trading-dashboard | `frontend/` |
| tester | tester | 사후 통합/경계면/안전성 검증 | trading-test, **kis-mcp-query** | 테스트 리포트 |
| **refactor-expert** | refactor-expert | *주기적* 코드 품질 검토 — 중복/명명/모듈 비대화/아키텍처 드리프트 | **refactor-review, kis-mcp-query** | `_workspace/refactor/` |
| **report-writer** | report-writer | 긴 작업 주기 끝의 쉬운 말 보고서(HTML 아티팩트) + 원문 md | **cycle-report** | `_workspace/reports/` |

### 호출 시점

- **team-leader**: 모든 요청의 1차 진입
- **domain-expert**: Phase 2.5 명세 분해 *직전* (선택적, 매매 의사결정 자문이 필요할 때) + 사이클 중 *행위 영향 평가* 가 필요할 때
- **tdd-engineer / backend-dev / frontend-dev / tester**: Phase 3~4 표준 TDD 사이클
- **refactor-expert**: Phase 4.5 — 사이클 5회 누적 또는 사용자 명시 요청 시
- **report-writer**: Phase 5 — 사이클 3회 이상 연속 · 자율 진행 구간 종료 · 사용자 "리포트" 요청 시 (`cycle-report` 스킬)

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

기본 팀 = 5 명 (team-leader 는 오케스트레이터 자신). domain-expert / refactor-expert 는 *필요 시 합류* (Phase 2.5 / Phase 4.5).

```
TeamCreate(
  team_name: "trading-tdd-team",
  members: [
    {
      name: "tdd-engineer",
      agent_type: "tdd-engineer",
      model: "opus",
      prompt: "TDD 엔지니어. .claude/agents/tdd-engineer.md 역할, .claude/skills/tdd-cycle/skill.md + .claude/skills/test-impact-index/skill.md + .claude/skills/kis-mcp-query/skill.md 참조. 명세 수신 시 Red 테스트 선작성 → backend-dev/frontend-dev에 SendMessage. KIS 응답 합성 시 KIS MCP 인용. Green 검증 후 영향 인덱스 갱신."
    },
    {
      name: "backend-dev",
      agent_type: "backend-dev",
      model: "sonnet",
      prompt: "백엔드 개발자. .claude/agents/backend-dev.md, .claude/skills/kis-api-integration/skill.md + .claude/skills/kis-mcp-query/skill.md 참조. **Red 테스트 수신 후에만** 최소 구현 작성. KIS 신규/응답 의문 시 KIS MCP 로 정본 확인. tdd-engineer에 Green 알림. 모듈 완성 시 tester에 통합 검증 의뢰."
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
      prompt: "QA 테스터. .claude/agents/tester.md, .claude/skills/trading-test/skill.md + .claude/skills/kis-mcp-query/skill.md 참조. Red/Green 사이클은 tdd-engineer 담당. tester는 모듈 결합 후 통합/경계면/E2E 검증. KIS 경계면은 MCP 응답을 정본으로 양쪽 동시 읽기. 결함은 tdd-engineer에 회귀 테스트 의뢰."
    }
  ]
)
```

**선택적 합류 — Phase 2.5 (도메인 자문 필요 시)**

```
Agent(
  subagent_type: "domain-expert",
  model: "opus",
  prompt: "도메인 전문가 (데이/스윙 트레이더). .claude/agents/domain-expert.md + .claude/skills/domain-consult/skill.md 참조. 자문 요청 1 건 처리 후 `_workspace/domain_consult/{topic}.md` 산출. 권고는 *3 안 정렬* + *반례 동반* + *CLAUDE.md 안전 규칙 우선*."
)
```

자문이 짧으면 Agent 직접 호출, 사이클 전반에 걸쳐 자주 요청되면 팀에 정식 합류 (`TeamDelete` 후 `TeamCreate` 로 재구성).

**선택적 합류 — Phase 4.5 (주기적 리팩토링 검토)**

```
Agent(
  subagent_type: "refactor-expert",
  model: "opus",
  prompt: "리팩토링 전문가. .claude/agents/refactor-expert.md + .claude/skills/refactor-review/skill.md + .claude/skills/kis-mcp-query/skill.md 참조. 검토 범위 = {team-leader 가 지정 또는 사이클 N 회 누적 범위}. 산출물 `_workspace/refactor/{YYYY-MM-DD}_review.md`. 카드 단위 분할 + 위험 등급 + 회귀 가드 명시. HIGH 카드는 domain-expert 행위 영향 평가 의뢰."
)
```

### Phase 2.5: 명세 → 행위 분해 (TDD 사이클의 입력)

이 단계가 TDD를 강제하는 핵심이다. **개발자에게 작업을 분배하기 전에** team-leader와 tdd-engineer가 함께 명세를 검증 가능한 행위 단위로 분해한다. *매매 의사결정의 깊이* 가 필요한 명세는 domain-expert 자문을 선행한다.

1. team-leader 가 사용자 요청 분석
2. **(선택) domain-expert 자문 — `domain-consult` 스킬** — 다음 중 하나라도 해당하면 명세 작성 *전* 에 자문 의뢰:
   - 신규 전략 발의 또는 기존 전략의 *행위 변경*
   - 파라미터 (K값/돌파 임계/익절/트레일링/position_ratio/cash_usage_ratio 등) 변경
   - 보드 가드 (tradable_boards) 변경
   - 시장 레짐 임계 조정 또는 매수 가드 모드 변경
   - KIS 거부 코드 / 호가 두께 / 슬리피지 등 *시장 미시구조* 가 결정에 개입
   - 운영 결함이 *시장 행태 vs 코드 결함* 판단을 요구
3. team-leader 가 자문 메모 (`_workspace/domain_consult/{topic}.md`) 를 참조하여 매매 규칙/기능 명세를 `_workspace/00_leader_trading_rules.md` 에 확정
4. tdd-engineer 가 명세를 읽고 검증 가능한 행위 목록을 `_workspace/red/_behaviors.md` 에 작성
5. 모호한 항목은 team-leader / domain-expert 에 SendMessage 로 즉시 확인
6. team-leader 승인 후 Phase 3 사이클 시작

**도메인 자문 결과 채택 흐름**: 자문은 *권고* 다. team-leader 가 채택/보류/폐기 결정. 채택 시 매매 규칙 명세에 자문 메모 경로 + 채택 항목 명시.

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

> **프론트 전용 사이클 주의 (cycle256 교훈, 2026-09-05)**: vitest·`tsc -b`·build 만으로는 부족하다. 백엔드 pytest 안에 프론트 파일을 읽는 가드가 있다(`grep -rl 'frontend/' tests/unit` — 예: cycle251 의 `AccountGate` 8키·KST 텍스트 가드). 프론트만 바꾼 사이클도 그 목록을 반드시 실행한다. 타입 관문은 `npx tsc -b`(루트 tsconfig 가 솔루션 형식이라 `--noEmit` 은 0파일 검사).


1. tester가 모듈 완성 알림을 받으면 즉시 시작
2. 양쪽 동시 읽기로 경계면 검증 (KIS 스펙 + **KIS MCP** ↔ 구현, FastAPI↔React, DB↔모델)
3. 매매 안전성 시나리오 실행 (중복 매수, 부분 체결, 체결통보 race, 강제청산, Rate Limit, 보드 가드, NXT 좀비 차단)
4. Playwright E2E 4개 시나리오 실행
5. 결함 발견 시:
   - *시장 행태* 의심 → domain-expert 1 차 자문 → 코드 결함이면 tdd-engineer 에 회귀 테스트 의뢰
   - *코드 결함* 확정 → tdd-engineer 에 회귀 테스트 의뢰 → Phase 3 사이클로 복귀
6. 최종 통합 리포트: `_workspace/test_report.md`

### Phase 4.5: 주기적 리팩토링 검토 (선택적)

**트리거** (다음 중 하나라도 해당):
- 사이클 5 회 누적 (오케스트레이터가 `_workspace/red/` 파일 수로 자동 감지)
- 사용자가 "리팩토링", "코드 정리", "중복 제거", "구조 개선" 키워드 요청
- tdd-engineer 가 *드리프트 신호* 보고 (같은 패턴 3 곳 이상 등장)
- 단일 파일 > 800 라인 또는 단일 함수 > 80 라인 발견

**흐름**:
1. team-leader 가 검토 범위 확정 (디렉토리 / 사이클 번호 / 모듈)
2. refactor-expert 합류 (`Agent(subagent_type: "refactor-expert", model: "opus")`)
3. refactor-expert 가 `refactor-review` 스킬 흐름 따라 검토:
   - 코드 정독 + grep 통계 + 모듈 라인 수 분석
   - KIS API 영역이면 KIS MCP 로 정본 재확인
   - 카드 후보 식별 + 위험 등급 (LOW/MEDIUM/HIGH) 분류
   - HIGH 카드 → domain-expert 행위 영향 평가 의뢰 (`domain-consult` 스킬)
   - 회귀 가드 부재 영역 → tdd-engineer 회귀 테스트 선행 의뢰
4. 리뷰 메모 `_workspace/refactor/{YYYY-MM-DD}_review.md` 산출
5. team-leader 가 카드별 채택 / 보류 / 폐기 결정
6. 채택 카드는 Phase 3 사이클로 흡수 (Red→Green→tester 통합 검증)

**Phase 4.5 는 Phase 4 완료 후 또는 별도 세션으로 실행** — 운영 시간 (KRX 메인 09:00~15:30) 중 push 자제 권고 (CLAUDE.md 운영 가이드).

### Phase 4.8: 문서 동기화 (`/sync-docs`) — **필수**

코드가 바뀐 사이클은 커밋 **전에** `/sync-docs` 를 돈다. 워크플로 안에서 처리하더라도
그 명령의 §2 매핑 표와 **대상 문서 정본 목록**을 근거로 삼는다(그게 누락 방지의 유일한 체크리스트다).

- 최소 의무 = ① 변경된 코드 위치 → 매핑 표로 갱신 후보 문서 확정 ② **모듈 누락 자가 점검**
  (디렉터리 정본이 그 디렉터리의 새 모듈을 담고 있는가 — 기계적 grep) ③ `docs/HARNESS_CHANGELOG.md`
  상단에 1행 verbatim — **이력의 유일한 정본**이고 정본 문서에는 이력 표를 만들지 않는다. 그 사이클이
  정본의 규칙을 바꿨으면 정본은 새 값으로 **덮어쓰고** 바뀐 경위만 `docs/history/<정본 이름>.history.md`
  에 append ④ 열린 과제는 `_workspace/00_URGENT_WORKLIST.md` ⑤ **덧칠 패턴 검사**(`/sync-docs` 의
  `DOC_OVERPAINT`)가 0 또는 직전 커밋 대비 감소
- **전용 `CLAUDE.md` 가 없는 디렉터리**(`src/services/` · `src/middleware/` · `tools/` · `e2e/`)를
  건드렸으면 상위 문서를 본다 — 이 넷이 누락이 반복되는 지점이다.
- ⚠️ `src/**` 는 확장자 무관 **이미지 입력**이라 `src/*/CLAUDE.md` 수정만으로도 배포가 full 이 된다.
  보유 중 장중이면 커밋만 하고 푸시는 장 종료 후로 미룬다(cycle232 D6).

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
5. **마무리 보고 (2026-09-05)**: 사이클 3회 이상 연속 · 자율 진행 구간 종료 · 사용자 요청이면 `cycle-report` 스킬로 `report-writer` 를 호출해 쉬운 말 아티팩트 보고서 + 원문 md + 결정 카드를 만든다. 사이클 1~2회는 위 4의 터미널 보고로 충분하다(결정 항목 3개 이상이면 보고서).

## 데이터 흐름 (TDD + 도메인 자문 + 리팩토링 통합 후)

```
[사용자 요청]
    │
    ▼
[team-leader/리더]
    │ (1) 매매 의사결정 자문 필요 시 ──→ [domain-expert] ──→ _workspace/domain_consult/
    │                                              │
    │←─────────────────── 자문 메모 한 줄 요약 ─────┘
    │
    │ (2) 매매 규칙 명세 (자문 채택 항목 반영)
    ▼
[tdd-engineer] ←──── 명세 검증/행위 분해 ────→ [team-leader]
    │ (필요 시 KIS MCP 응답 합성)
    │ Red 준비
    ▼
[backend-dev / frontend-dev]
    │ (backend-dev 는 KIS MCP 로 정본 재확인)
    │ Green 구현
    ▼
[tdd-engineer] ── 인덱스 갱신 ──→ _workspace/test_index.yaml
    │ 모듈 완성 알림
    ▼
[tester]
    │ KIS MCP 인용 양쪽 동시 읽기 + 통합/경계면/E2E
    ├── 결함 발견 (시장 행태 의심) ──→ [domain-expert] 1차 자문
    ├── 결함 발견 (코드 결함 확정) ──→ [tdd-engineer] (회귀 테스트로)
    └── 안전성 이슈 ──→ [team-leader] (작업 중단 판단)
    │
    │ 사이클 5회 누적 또는 명시 요청 시
    ▼
[refactor-expert] (Phase 4.5)
    │ 리뷰 메모 → _workspace/refactor/
    │ HIGH 카드 ──→ [domain-expert] 행위 영향 평가
    │ 회귀 가드 부재 ──→ [tdd-engineer] 선행 의뢰
    │
    └── 채택 카드 ──→ Phase 3 사이클 (Red→Green→tester 회귀 0)
```

[report-writer] (Phase 5)
    └── 쉬운 말 아티팩트 + `_workspace/reports/` 원문 + 결정 카드 ──→ 사용자

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 개발자가 Red 없이 구현 시도 | tdd-engineer가 거부 → team-leader가 명세 분해 재시작 |
| Red가 즉시 통과 (false-red) | 명세 해석 오류 또는 이미 구현됨 — tdd-engineer가 사이클 중단 후 team-leader 확인 |
| Green 후 다른 테스트 깨짐 | 회귀 발생 — 원인 모듈 식별 후 같은 사이클에서 함께 Green 만들기 |
| 인덱스 정확도 의심 | manual_overrides.yaml 보강 + main 브랜치 풀 실행으로 안전망 |
| 매매 안전성 이슈 | tester → team-leader 즉시 → 작업 중단 판단 |
| 매매 의사결정 모호 | team-leader → domain-expert 자문 (`domain-consult` 스킬) → 3 안 정렬 후 결정 |
| KIS 응답 의문 | backend-dev / tdd-engineer / tester 가 KIS MCP 정본 확인 (`kis-mcp-query` 스킬) |
| 시장 행태 vs 코드 결함 판단 모호 | tester → domain-expert 1차 자문 → 결과에 따라 코드 수정 또는 시장 행태 수용 |
| 리팩토링 카드의 행위 영향 불확실 | refactor-expert → domain-expert 행위 영향 평가 의뢰 → 평가 후 카드 채택/폐기 |
| 회귀 가드 부재 영역 리팩토링 요청 | refactor-expert 가 카드 발의 보류 + tdd-engineer 회귀 테스트 선행 의뢰 |
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
- "다시 실행", "재실행", "업데이트", "수정", "보완"
- "{전략명}만 다시 테스트 작성"
- "이전 결과 기반으로 ~ 보강"
- "~ 회귀 테스트 추가"
- "~ 영향 인덱스 갱신"
- "리팩토링", "코드 정리", "중복 제거", "구조 개선", "모듈 분해"
- "도메인 자문", "트레이더 시각", "파라미터 근거", "시장 미시구조"
- "KIS 응답 재확인", "TR_ID 확인", "KIS 스펙 정본"
