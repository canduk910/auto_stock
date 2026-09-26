---
name: tdd-cycle
description: "주식 자동매매시스템의 Red→Green→Refactor TDD 사이클을 운영하는 스킬. 명세 → 실패 테스트 작성 → 최소 구현 → 리팩토링 루프를 표준화한다. 'TDD', '테스트 먼저', '테스트 작성', '실패 테스트', 'Red/Green', '회귀 테스트', '커버리지' 등을 언급하면 반드시 이 스킬을 사용할 것. 백엔드(pytest+respx+freezegun)와 프론트엔드(vitest+RTL+MSW)에 모두 적용된다."
---

# TDD Cycle Skill — Red→Green→Refactor 사이클 운영

자동매매시스템처럼 회귀 위험이 큰 시스템에서는 "테스트 먼저"가 안전 장치다. 이 스킬은 명세를 받고 실패 테스트를 만들어 구현을 유도하는 사이클을 표준화한다.

## 사이클의 3단계

### 1. Red — 실패 테스트 작성
- 명세에서 검증 가능한 행위 1개를 추출한다
- 그 행위를 검증하는 테스트를 작성한다 — 구현이 없으므로 반드시 실패해야 한다
- 실행 결과(`pytest -x` 또는 `vitest run`)에서 RED를 눈으로 확인한다
- 테스트가 즉시 통과하면 명세 해석이 잘못됐거나 이미 구현되어 있는 것 — 사이클 중단하고 재검토

### 2. Green — 최소 구현
- 테스트를 통과시키는 가장 작은 코드를 작성한다 (성능/우아함은 나중)
- 다른 테스트가 깨지면 그것도 함께 처리한다
- "이 테스트만 빨리 통과시키자" 모드 — 디자인 욕심 금물

### 3. Refactor — 안전한 정리
- 테스트가 모두 Green인 상태에서 코드 구조만 다듬는다
- 변수/함수 이름, 중복 제거, 의존성 정리
- 리팩토링 도중 RED가 한 번이라도 보이면 즉시 되돌린다

## 한 사이클 = 작은 행위 1개

큰 기능을 통째로 테스트하지 않는다. 큰 기능은 작은 행위로 쪼갠다:

```
나쁜 예: "VolatilityBreakout 전략 전체 동작 검증"
좋은 예:
  - K값이 보드별로 분리 저장된다
  - 보드별 시가가 확정되기 전에는 target_price가 None이다
  - target_price 돌파 시 BUY 신호가 발생한다
  - 손절 -3% 도달 시 SELL 신호가 발생한다
  - 15:20 강제청산 트리거가 발동한다
```

각 행위 1개당 사이클 1회. 5개 행위 = 5번의 Red→Green→Refactor.

## 명세는 어디서 오는가

| 출처 | 어디 |
|------|------|
| 매매 규칙 | `_workspace/00_leader_trading_rules.md` (team-leader 작성) |
| API 인터페이스 | backend-dev ↔ frontend-dev 합의 (SendMessage 로그) |
| KIS API 스펙 | `docs/kis/*.md` |
| 운영 결함의 회귀 | tester가 의뢰한 회귀 테스트 |

명세가 모호하면 테스트 쓰지 말고 **team-leader에게 즉시 확인**.

## Red 케이스 작성 표준

### 백엔드 (pytest)
- 파일 위치: `tests/unit/`, `tests/integration/`, `tests/contract/` 중 적합한 곳
- 명명: `test_<대상>_<조건>_<기대>.py` 또는 `test_<대상>.py` 안에 `test_<조건>_when_<상황>_then_<기대>` 함수
- 외부 의존성: 반드시 conftest.py의 fixture(`mock_kis`, `fake_supabase`, `freeze_time`, `fake_ws`)로 격리
- 실제 외부 네트워크는 루트 `tests/conftest.py` autouse `_block_external_network` 가 막는다 — 루프백이 아닌 DNS·연결이 즉시 `ConnectError` 가 된다(차단 기록 = `blocked_network_attempts` 픽스처, 옵트아웃 마커 `real_network`). 테스트가 부르는 경로가 KIS 로 나가면 결과가 그 시각 서버 속도에 묶인다(2026-09-25 CI 부팅 테스트 60초 초과) — 모킹으로 막지 못한 호출을 옵트아웃으로 살리지 않는다
- 모듈 전역 상태(싱글턴 필드·폴백 dict·메모)를 바꾸는 테스트는 `monkeypatch.setattr` 로 바꿔 테스트 끝에 되돌린다 — 직접 대입은 뒤따르는 테스트의 결과를 수집 순서에 묶는다
- async 코드는 `pytest.mark.asyncio` (asyncio_mode=auto면 생략 가능)

### 프론트엔드 (vitest + RTL)
- 파일 위치: 컴포넌트 옆 `__tests__/` 디렉토리에 코로케이션
- 명명: `<Component>.test.tsx` 또는 `<hook>.test.ts`
- 외부 API: MSW 핸들러로 격리 (`src/test/handlers.ts`에 추가)
- 사용자 관점: `screen.getByRole`, `userEvent.click` 등 — implementation detail 노출 금지

> 상세 패턴은 `references/backend.md` / `references/frontend.md` 참조.

## 사이클 산출물

각 사이클마다 `_workspace/red/<feature-slug>.md` 파일에 다음을 기록한다:

```markdown
# <Feature Slug>

**명세 출처**: <_workspace/00_leader_trading_rules.md L<n> 또는 메시지 ID>
**행위**: <한 줄로 검증 대상 행위>

## Red
- 테스트 파일: `tests/unit/engine/strategies/test_volatility_breakout.py::test_target_price_unset_before_open`
- 실행 결과:
  ```
  pytest -x tests/unit/.../test_target_price_unset_before_open
  > FAILED ... AssertionError: target_price was None expected ...
  ```

## Green
- 구현 파일: `src/engine/strategies/volatility_breakout.py:142-160`
- 변경 요지: 보드별 _open_confirmed dict로 분리
- 실행 결과: PASSED

## Refactor
- 변경: 보드별 dict 접근 헬퍼 추출 (`_get_board_target`)
- 영향 인덱스 재생성: ✅
```

## 영향 인덱스 갱신 (사이클 종료 시)

```bash
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
```

생성된 `_workspace/test_index.yaml`을 커밋한다. 동적 의존성(시간/전역 dict/DB 스키마)은 `tools/test_impact/manual_overrides.yaml`에 1줄 코멘트와 함께 보강.

## 안티 패턴 (절대 금지)

| 안티 패턴 | 왜 안 되나 |
|----------|-----------|
| 구현 먼저 작성 후 테스트 추가 | 테스트가 구현을 따라가면 디자인 검증 효과가 사라진다 — 특히 매매 시스템에서는 race·시간·격리가 미흡한 코드를 테스트가 그대로 화석화한다 |
| 테스트 통과만 목표로 한 가짜 단언 (`assert True`, `assert hasattr`) | 회귀 위험에 무력 |
| 실제 KIS/Supabase에 닿는 단위 테스트 | 비결정성·요금·rate limit·CI 불안정의 원흉 |
| 시간 의존 테스트에서 `sleep` 사용 | 느리고 불안정. `freeze_time` + 분 단위 step으로 |
| `pytest.mark.skip`을 무기한 방치 | skip은 부채. 1주 안에 해결하거나 삭제 |
| 테스트끼리 상태 공유 | fixture 정리 누락 — 결정성 파괴 |

## 팀 워크플로우 (오케스트레이터 Phase 3 사이클)

```
[team-leader 명세 작성] → _workspace/00_leader_trading_rules.md
        │
        ▼
[tdd-engineer Red]
  ├─ 행위 1개 추출 → 실패 테스트 작성 → Red 확인
  └─ SendMessage to backend-dev/frontend-dev: "Red 준비됨"
        │
        ▼
[backend-dev/frontend-dev Green]
  ├─ 최소 구현 작성
  └─ SendMessage to tdd-engineer: "구현 완료"
        │
        ▼
[tdd-engineer Green 확인]
  ├─ 테스트 통과 확인 → Refactor 제안 → 다음 행위로
  └─ Red 유지 시: 원인 진단 (테스트 vs 구현)
        │
        ▼
[모듈 완성 시 tester 통합 검증]
  ├─ 경계면/안전성/E2E
  └─ 통합에서 발견된 결함 → tdd-engineer에 회귀 테스트 의뢰
```

## 트리거 키워드

이 스킬을 트리거해야 하는 상황:
- "TDD로 ~ 추가해줘"
- "테스트 먼저 작성"
- "실패 테스트", "Red 케이스"
- "회귀 테스트로 만들어줘"
- "커버리지 보강"
- "리팩토링 안전하게 하고 싶어"
- 매매 규칙·전략·주문 흐름 변경 요청 (자동으로 사이클 시작)

트리거하면 안 되는 상황:
- 이미 작성된 테스트의 단순 실행 (그냥 pytest/vitest 실행)
- 일회성 디버그 스크립트 작성
- 운영 로그 분석
