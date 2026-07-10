# 사이클 200 (D-1) — VCP funnel step1/2 기록 정합 (관찰성 race, 매매 무관)

출처: `_workspace/ai_advisory_review/2026-07-09_3day_consolidation.md` §6-3 D-1.

## 근본 원인 (진단 완료)

`src/engine/scheduler.py::capture_funnel_snapshots` **L216**:

```python
funnel_steps = getattr(strategy, "_funnel_steps", []) or []   # ← 라이브 리스트 참조
for step in funnel_steps:
    row = await insert_snapshot(...)   # ← step 마다 await (yield)
```

이 루프가 라이브 `_funnel_steps` 리스트를 참조하며 step 마다 `await`(yield) 로
iterate 한다. 동시에 concurrent `prepare()` (09:30 auto capture vs boot re-prepare /
`_scan_loop` 5분 re-prepare / `_reprepare_breakout_if_empty`) 가 `_record_funnel_step`
(`src/engine/strategy_base.py` L280-284, `self._funnel_steps[idx] = entry` in-place
요소 replace) 로 같은 리스트를 변형하면, capture 의 await 사이에 인터리빙 발생 →
나중 step 이 먼저 기록되어 **논리 불가 단조성** (step3 survived > step1/2 survived) 이
DB 에 기록된다.

**운영 실측** (Supabase, 7/9 VCP is_provisional): step1=0, step2=0, step3=67, step4=67,
step5=3 (step3≤step2≤step1 위반). 다른 날(7/7/8/10)은 정상(step1=328~330) = **간헐 race**.

## 확정 수정 (backend-dev Green)

`capture_funnel_snapshots` **L216** 을 원자적 shallow copy 로:

```python
funnel_steps = list(getattr(strategy, "_funnel_steps", []) or [])
```

`_record_funnel_step` 이 리스트 요소를 **replace** (`[idx]=entry`, 기존 dict 변형 아님)
하므로 `list(...)` shallow copy 로 capture 시작 시점 요소 참조가 고정된다 → 이후
concurrent prepare 가 원본 리스트를 변형해도 copy 는 불변 → 단조 일관성 보장.
prepare / hot path 무변경.

## 회귀 가드 (신규 `tests/unit/engine/test_cycle200_funnel_capture_atomic.py`)

| 케이스 | 등급 | 현재 코드 | 수정 후 |
|--------|------|-----------|---------|
| G-200-1 `test_g_200_1_atomic_capture_under_concurrent_mutation` (핵심 race — 운영 실측 330/330/67 재현, insert_snapshot mock 이 첫 호출 중 step1/2 를 count=0 으로 in-place replace) | HIGH | **FAIL** (step2=0 유입, 단조 위반) | PASS |
| G-200-1b `test_g_200_1b_mutation_after_first_step_does_not_leak` (변형이 뒷 step 을 999 로 오염) | HIGH | **FAIL** (step2/3=999 유입) | PASS |
| G-200-2 `test_g_200_2_normal_capture_matches_original` (무변형 캡처 = 원본 정확 일치 + step99 + is_provisional=True) | — | PASS | PASS |
| G-200-2b `test_g_200_2b_provisional_false_propagated` (is_provisional=False 전파) | — | PASS | PASS |
| G-200-3 `test_g_200_3_empty_funnel_steps_final_row_only` (빈 리스트 → step99 만, momentum 패턴) | — | PASS | PASS |
| G-200-3b `test_g_200_3b_registry_exception_graceful` (registry.all() 예외 → 0) | — | PASS | PASS |
| G-200-3c `test_g_200_3c_per_strategy_exception_isolated` (한 전략 예외 → 다른 전략 계속) | — | PASS | PASS |

step_no=99 최종 row 는 파이프라인 단조성 판정에서 제외 (`_pipeline_counts` 헬퍼).

## Red 유효성 검증

- 현재 코드 (라이브 참조): `2 failed (G-200-1, G-200-1b), 5 passed` ✅
- L216 → `list(...)` copy 1줄 flip 후: `7 passed` ✅ → 즉시 revert 완료.
- 기존 `test_cycle171_evening_funnel.py` 14 PASS (**의미 전환 없음** — capture 헬퍼
  계약 단언은 존재/step99/is_provisional 전파만 검사, 리스트 참조 방식 미단언).

## 매매 안전성

`capture_funnel_snapshots` = 관찰성 (사이클 171 SAFETY = check_exit/buy funnel hook 0 +
risk/order_engine/realtime/auth 참조 0). risk/order_engine/realtime/scanner 무관 —
8영역 밖. shallow copy 1줄은 prepare/hot path 무변경.

## backend-dev 구현 지시

`src/engine/scheduler.py` **L216** (`capture_funnel_snapshots` 내부, `for strategy in
strategies:` 루프 안 try 블록):

```python
# 변경 전
            funnel_steps = getattr(strategy, "_funnel_steps", []) or []
# 변경 후
            funnel_steps = list(getattr(strategy, "_funnel_steps", []) or [])
```

이 1줄 외 변경 없음. prepare / `_record_funnel_step` / step99 최종 row / graceful 로직
전부 불변.
