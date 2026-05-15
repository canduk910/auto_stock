# Phase 0 — TIME_RECOMMENDATION 19:50 → 20:00 이동

## Context

- Plan: `/Users/koscom/.claude/plans/backtest-integration-mcp.md` Phase 0
- 목적: 매일 20:00 OpenAI 자문 + (Phase 3 에서 추가될) 백테스트 검증을 위한 시점 정합성 사전 확보
- 자문 시점만 변경. **`TIME_NXT_POST_BUY_STOP=19:50` 는 그대로 유지** (NXT 애프터 매수 중단 안전 마감 시점)
- 20:00 동시 발화: TIME_RECOMMENDATION + TIME_NXT_POST_CLOSE — 두 task 모두 `asyncio.create_task` 백그라운드 비동기로 race 없음

## 변경 대상 코드 핵심

`src/engine/scheduler.py`:

- L59 상수 변경: `TIME_RECOMMENDATION = time(19, 50)` → `time(20, 0)`
- L415-434 분기 분리:
  - 19:50 (`TIME_NXT_POST_BUY_STOP`) 분기에서 `generate_recommendations()` 호출 + INFO 로그 제거
  - 19:50 분기는 `buy_disabled=True` + NXT 애프터 매수 중단 로그만 남김
  - 20:00 분기 (`TIME_NXT_POST_CLOSE`) 도달 직후 `generate_recommendations()` 호출 + `unsubscribe_all()` 둘 다 백그라운드 task 로 발화

## 검증 가능한 행위 (N=6)

| # | 행위 | 검증 방식 |
|---|------|----------|
| 1 | `TIME_RECOMMENDATION` 상수 값이 `time(20, 0)` 이다 | `scheduler.TIME_RECOMMENDATION == datetime.time(20, 0)` |
| 2 | `TIME_NXT_POST_BUY_STOP` 상수 값이 `time(19, 50)` 그대로다 (NXT 매수 중단 안전 규칙 보존) | `scheduler.TIME_NXT_POST_BUY_STOP == datetime.time(19, 50)` |
| 3 | `TIME_RECOMMENDATION < TIME_SETTLEMENT` (20:00 < 20:10) 순서 보장 | 직접 비교 |
| 4 | 20:00 시점에 `generate_recommendations()` 가 호출된다 | scheduler 분기 호출 단위 검증 (mock 호출 카운트=1) |
| 5 | 19:50 시점에는 `generate_recommendations()` 가 호출되지 *않는다* (`buy_disabled=True` 만 발화) | 19:50 분기 진입 시점 mock 호출 카운트=0 |
| 6 | 자문 실패 except 핸들러는 20:00 분기로 함께 이동했고 traceback 포함 ERROR 로그를 그대로 보존한다 | 기존 `test_scheduler_recommendation_failure.py` 갱신 (19:50 → 20:00 컨텍스트로) |

## 영향 받는 기존 테스트 (Red 갱신 필요)

- `tests/integration/test_scheduler_recommendation_failure.py` — "19:50 AI자문 / 20:10 일일 로그 분석 예외 핸들러" docstring/주석을 "20:00 AI자문" 으로 갱신. 시각만 변경이라 동작 자체는 동일.
- `tests/integration/test_post_nxt_open_price_confirm.py` — L116 주석 "19:50 NXT 애프터 매수 중단 대기" 문구 보존 (NXT 매수 중단은 19:50 그대로).
- `tests/unit/engine/test_vb_force_clear_at_15_20.py` — L6~7 docstring "19:50 시점에는 매수 중단 + AI자문" 표현 갱신: "19:50 NXT 매수 중단 / 20:00 AI자문" 으로 분리.

## 영향 받는 문서

- `src/engine/CLAUDE.md` L14, L124, L167 — TIME_RECOMMENDATION 19:50 → 20:00
- `_workspace/00_leader_trading_rules.md` L625, L663, L678 — 자문 시점 갱신
- `frontend/` 19:50 문구는 NXT 애프터 마감 시각(19:50) 으로 그대로 — 자문 시각 별도 표기 없음 (재확인 후 결정)
- `docs/HARNESS_CHANGELOG.md` 1행 추가

## 안전 규칙

- **19:50 NXT 애프터 매수 중단 절대 제거 금지** — 자문 시각만 분리. `TIME_NXT_POST_BUY_STOP=time(19,50)` 보존
- 20:00 두 분기 동시 발화이지만 `unsubscribe_all()` 은 동기 await, `generate_recommendations()` 는 백그라운드 task 로 발화 → race 회피
- 자문 실패해도 20:00 NXT 종료 / 20:10 정산은 정상 진행 (현재 except 블록 보존)
- 커밋 보류: 사용자 게이트 통과 후 Phase 1 진입

## 의존성 / 병렬 가능 여부

- 행위 1, 2, 3: 독립 (병렬 가능)
- 행위 4, 5: scheduler 분기 이동에 의존 (행위 1 Green 후 검증)
- 행위 6: 기존 테스트 갱신, 행위 4/5 와 동일 사이클

→ tdd-engineer 는 6개 행위를 한 파일 `tests/integration/test_recommendation_time_change.py` (행위 1~5) + 기존 `test_scheduler_recommendation_failure.py` (행위 6 갱신) 로 묶어 Red 발화. backend-dev 는 scheduler.py 단일 파일에서 Green.
