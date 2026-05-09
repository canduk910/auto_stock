---
name: test-impact-index
description: "코드 변경 시 영향받는 테스트만 실행할 수 있도록 source↔test 의존성 인덱스를 생성·관리하는 스킬. 백엔드는 Python AST로 import 그래프를 분석하고, 프론트엔드는 TS/TSX import를 분석한다. 정적 분석으로 잡히지 않는 동적 의존성은 manual_overrides.yaml로 보강한다. '영향 테스트', '테스트 인덱스', '변경 영향 분석', 'affected tests', '인덱스 재생성', 'test-impact' 언급 시 반드시 이 스킬을 사용한다."
---

# Test Impact Index — 변경 → 영향 테스트 매핑

소스 한 줄 바뀌었을 때 어떤 테스트가 깨질 수 있는지 즉시 알아내기 위한 인덱스. PR CI에서 부분 실행으로 피드백 속도를 끌어올리고, 로컬 개발 중에도 해당 테스트만 빠르게 돌릴 수 있게 한다.

## 인덱스 생성 도구

### 백엔드 — `tools/test_impact/build_index.py`
- 입력: `src/**/*.py`, `tests/**/test_*.py`
- 동작:
  1. 모든 `src/**/*.py`의 `import` 문을 AST로 파싱
  2. 모든 테스트 파일의 import도 파싱
  3. 모듈 → 직접 테스트 매핑 + 모듈 의존성 그래프로 transitive 계산
- 출력: `_workspace/test_index.yaml` 의 `backend:` 섹션

### 프론트엔드 — `tools/test_impact/build_index_frontend.mjs`
- 입력: `frontend/src/**/*.{ts,tsx}`, `frontend/src/**/__tests__/**/*.{test,spec}.{ts,tsx}`
- 동작: 정규식 기반 `import ... from "..."` 분석 (단순/충분)
- 출력: `_workspace/test_index.yaml` 의 `frontend:` 섹션

### 영향 분석 — `tools/test_impact/affected.py`
- 입력: `git diff --name-only <ref>` 결과
- 동작:
  1. 변경된 파일 목록 수집
  2. 인덱스에서 각 파일의 `direct_tests` + `transitive_tests` 합집합
  3. `manual_overrides.yaml` 항목 병합
- 출력: 공백 구분 테스트 경로 (pytest/vitest에 그대로 전달)

```bash
pytest $(python tools/test_impact/affected.py HEAD~1 --target=backend)
```

## 인덱스 스키마 (`_workspace/test_index.yaml`)

```yaml
version: 1
generated_at: 2026-05-08T12:00:00+09:00
backend:
  src/api/base.py:
    direct_tests:
      - tests/unit/api/test_base.py
    transitive_tests:
      - tests/unit/api/test_order.py
      - tests/contract/test_routes_trading.py
    domain_tags: [external-io]
  src/engine/scheduler.py:
    direct_tests:
      - tests/unit/engine/test_scheduler.py
    transitive_tests:
      - tests/integration/test_force_clear_1520.py
      - tests/integration/test_next_day_clear.py
    domain_tags: [time-sensitive, single-worker]
frontend:
  frontend/src/hooks/useTradingStatus.ts:
    direct_tests:
      - frontend/src/hooks/__tests__/useTradingStatus.test.ts
    transitive_tests:
      - frontend/src/components/__tests__/ControlPanel.test.tsx
      - frontend/src/components/__tests__/PerformanceCard.test.tsx
overrides_applied:
  - "_workspace/00_leader_trading_rules.md"
  - "src/config.py"
```

## 수동 보강 (`tools/test_impact/manual_overrides.yaml`)

정적 분석이 못 잡는 의존성을 추가한다. 각 항목에는 **이유 코멘트** 필수.

```yaml
# 매매 규칙 텍스트가 바뀌면 모든 전략 단위 테스트와 통합 테스트를 다시 돌린다
"_workspace/00_leader_trading_rules.md":
  - "tests/unit/engine/strategies/**"
  - "tests/integration/**"

# session.py의 시각 상수는 import만으로 의존성이 안 잡힘
"src/engine/session.py":
  - "tests/integration/test_force_clear_1520.py"
  - "tests/integration/test_next_day_clear.py"
  - "tests/integration/test_board_transition.py"

# config.py의 TR_ID 매핑은 모든 KIS 호출에 영향
"src/config.py":
  - "tests/unit/api/**"
  - "tests/contract/**"

# 프론트엔드 axios 베이스 변경은 모든 API + E2E에 영향
"frontend/src/api/client.ts":
  - "frontend/src/**/__tests__/**"
  - "e2e/**"

# DB 마이그레이션 스키마 변경은 db/routes 전체에 영향
"src/db/migrations/**":
  - "tests/unit/db/**"
  - "tests/contract/**"
```

## 운영 시점

| 시점 | 트리거 |
|------|--------|
| TDD 사이클 종료 시 | tdd-engineer가 `build_index.py` 실행 후 `test_index.yaml` 커밋 |
| PR 생성 시 | `.github/workflows/test-impact.yml`이 affected만 실행 |
| main push 시 | 일반 CI가 전체 테스트 실행 (안전망) |
| `manual_overrides.yaml` 수정 시 | 즉시 인덱스 재생성 + 커밋 |

## 정확도 원칙

정적 분석은 100%를 보장하지 않는다. 감수해야 할 한계:

- 동적 import (`importlib.import_module(name)`) — 잡히지 않음 → manual_overrides
- 시간 의존성, 전역 dict — 잡히지 않음 → manual_overrides + tag 기반 보강
- 문자열 기반 라우팅 (FastAPI 경로) — 잡히지 않음 → contract 테스트는 항상 manual_overrides에 포함

**안전망:** main 브랜치는 항상 전체 실행. PR은 부분 실행 + 머지 전 main에서 풀 실행으로 더블체크.

## CLI 사용 예

```bash
# 인덱스 생성
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs

# 변경 영향 테스트 출력 (백엔드)
python tools/test_impact/affected.py HEAD --target=backend
# > tests/unit/api/test_base.py tests/contract/test_routes_trading.py

# 변경 영향 테스트 출력 (프론트엔드)
python tools/test_impact/affected.py HEAD --target=frontend
# > frontend/src/components/__tests__/ControlPanel.test.tsx ...

# 부분 실행
pytest $(python tools/test_impact/affected.py HEAD --target=backend)
cd frontend && npx vitest run $(python ../tools/test_impact/affected.py HEAD --target=frontend)
```

## 트리거 키워드

이 스킬을 트리거해야 하는 상황:
- "영향 테스트", "affected tests"
- "테스트 인덱스 재생성", "build test index"
- "변경 영향 분석"
- "이 변경이 어떤 테스트를 깨뜨리나"
- "manual_overrides 추가/수정"
- TDD 사이클 종료 시 자동 (tdd-cycle 스킬과 결합)

> 인덱스 스키마 상세는 `references/index-schema.md` 참조.
