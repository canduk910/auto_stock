# 사이클 218 Red — K stale watcher `_stale_retry_count` 무한 climb 관찰성 정리

- **파일**: `tests/unit/engine/stale_manager/test_cycle218_retry_counter_cap.py` (6 케이스)
- **대상 함수**: `src/engine/stale_watcher_core.py::check_and_resubscribe_stale` (120s K watcher)
- **인계**: backend-dev (구현), 본 문서 = Red 명세 + 정확 위치

## 실측 배경 (2026-08-13 EC2, 051905)
force_retry skip 분기에서 보유 종목 `_stale_retry_count` 가 r=131 까지 무한 climb.
근본 원인: cycle215 로 실효화된 `resubscribe_stale_priority`(5분) 가
`_stale_last_resubscribe_at[ticker]` 를 갱신 → K watcher force_retry 의 600s 게이트
(`stale_watcher_core.py:282` `age_secs < STALE_FORCE_RETRY_AFTER_SECS`) 가 계속 미충족
→ **skip(무SEND) + r 리셋 안 됨**(리셋은 force_retry FIRE 시점 line 323 에만) → r 무한 누적.
**실제 재SEND 는 감소(4340→411), r 은 표시용 오해 숫자.**

## 시정 (backend-dev 구현 — 정확 위치)
`src/engine/stale_watcher_core.py` line 282-285 skip 분기, `continue` **앞**에 1줄:
```python
                if age_secs < STALE_FORCE_RETRY_AFTER_SECS:
                    # cooldown 미경과 — 기존 skip 동작 보존 (LMS 위험 차단, 카운터는 누적)
                    scheduler._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1   # ← 신규 1줄
                    skipped_giveup += 1
                    continue
```
= r 을 6 으로 홀드(무한 climb 차단). `MAX_STALE_RETRIES` 는 파일 상단에서 이미 import 됨.

## 행위 불변 근거 (소비자 전수 — 전부 임계 비교, 6이든 131이든 동일)
- K watcher `retry > MAX_STALE_RETRIES` — `stale_watcher_core.py:272` (6>5 동일)
- universe_guard `retries <= MAX_STALE_RETRIES → continue` — `stale_universe_guard.py:85` (6>5 → target 동일)
- diagnostics CCNL eligible `r < 2 → continue` — `stale_diagnostics.py:243` (6>=2 동일)
- 표시만 값 변경: `stale_diagnostics.py:129` `[stale_watcher_detail]` + `routes/realtime.py:88` UI

## 제약
- 8영역 무접촉 (stale_watcher_core.py 는 realtime/ 아님). 4중 안전망 AST(G-REJECT-1) 무충돌.
- freezegun 고정 base + `asyncio.sleep` patch (cycle63 force_retry 패턴). 동결 hang 무관
  (`check_and_resubscribe_stale` 는 wait 루프 부재 = 단조전진 불요).

## Red 결과 (현재 코드, revert 후 재확인)
`1 failed, 5 passed`

| 케이스 | 등급 | Red 상태 | 검증 |
|--------|------|----------|------|
| G218-1 skip 분기 캡 | HIGH | **FAIL(핵심)** | 5 사이클 r 관측 = 현재 `[7,8,9,10,11]` climb vs 기대 `[6,6,6,6,6]`. skip=무SEND(subscribe/unsub await 0) |
| G218-2 FIRE 리셋 보존 | HIGH | PASS(불변) | age>=600 FIRE → r=0 리셋(line 323) + subscribe 1회 + history 1건 |
| G218-3 universe_guard 임계 | HIGH | PASS(불변) | r=6→target / r=5(경계)·r=0→미target (reset-to-0 대비 명시) |
| G218-4 force_retry 경로 결정 | MEDIUM | PASS(불변) | r=6(retry=7) → force_retry 진입(history append), 1-5 falling 아님 |
| G218-5 1-5 즉시 재등록 | MEDIUM | PASS(불변) | r=2→retry=3 unsub+sub 1회, 카운터 누적(3), history 미접촉 |
| G218-6 sibling 격리 | MEDIUM | PASS(불변) | `resubscribe_stale_priority` 는 `_stale_retry_count` 무접촉 |

## Green 시뮬 검증 (임시 fix apply → 확인 → revert 완료)
- 캡 1줄 적용 시: `test_cycle218` **6 passed**.
- 회귀 0: cycle215/216/217 + cycle63 force_retry/history = `24 passed, 1 xfailed`(cycle102 boundary xfail = 기존).
- `src/engine/stale_watcher_core.py` 는 revert 완료 (`git diff` 무변경) — 구현은 backend-dev.
