# 회귀 테스트 디렉토리

운영 중 발견된 결함이나 통합/E2E 단계에서 노출된 버그를 단위 테스트로 영구화한다.

## 컨벤션

1. **이슈 식별자**: 매 회귀 테스트는 짧은 슬러그로 시작한다 (예: `chegyeol-race`, `15-20-clear-keep-post-nxt`).
2. **사이클 로그**: `_workspace/red/<slug>.md`에 다음을 기록한다:
   - **명세 출처**: 결함이 발견된 시점 / 트레이스 / 운영 로그 / Phase 리포트
   - **재현 조건**: 어떤 입력/시나리오에서 깨졌는지
   - **테스트 파일 경로**: 회귀 테스트가 어디로 영구화됐는지 (예: `tests/integration/test_chegyeol_race.py::test_buy_chegyeol_race_when_ws_first_then_completed_direct_insert`)
   - **수정 커밋**: 어떤 PR/커밋이 fix했는지
3. **테스트 위치**: 가장 좁은 범위로 영구화한다.
   - 함수 단위 행위면 → `tests/unit/...`
   - 모듈 결합이면 → `tests/integration/...`
   - 라우트 계약이면 → `tests/contract/...`
   - 사용자 흐름이면 → `e2e/...`

## 신규 회귀 등록 절차 (tdd-engineer 가 수행)

```
1. tester 또는 사용자로부터 결함 보고 수신
2. _workspace/red/<slug>.md 작성 (명세/재현/실패 출력)
3. 가장 좁은 레이어에서 실패 테스트 작성 (Red 확인)
4. 개발자 fix 도착 → 테스트 통과 (Green)
5. _workspace/red/<slug>.md 에 fix 커밋 SHA 기록
6. tools/test_impact/build_index.py 재실행 → 인덱스 갱신
7. 회귀가 영구화됐음을 사용자에게 통보
```

## 인덱스 자동 재생성

영향 인덱스(`_workspace/test_index.yaml`)는 다음 시점에 갱신한다:

- **TDD 사이클 종료 시**: `python tools/test_impact/build_index.py && node tools/test_impact/build_index_frontend.mjs`
- **PR 생성 시**: `.github/workflows/test-impact.yml` 이 affected 테스트만 실행 (인덱스 자체 갱신은 사이클 종료 시점 책임)
- **`manual_overrides.yaml` 수정 시**: 즉시 재생성

## 회귀 테스트 권장 명명 규칙

```python
def test_<상황>_when_<입력>_then_<기대>():
    ...

# 예시
def test_chegyeol_race_when_ws_first_then_completed_direct_insert():
def test_force_clear_when_post_nxt_active_then_keeps_position():
def test_buy_when_kis_returns_insufficient_cash_then_block_buy_lock():
```

이름이 명세를 그대로 표현하면 실패 출력만 봐도 무엇이 깨졌는지 알 수 있다.
