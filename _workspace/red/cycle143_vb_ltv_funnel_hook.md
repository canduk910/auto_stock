# 사이클 143 — VB 5단계 + LTV 6단계 funnel hook (사이클 140 자문 영속)

- **사용자 결정**: Q1=A 사이클 142 commit `5d69467` push + CI success 5분 43초 + EC2 Deploy success 19초 영속 + Q2 사이클 143 = funnel hook 즉시 발주
- **인계**: 사이클 140 자문 (`_workspace/domain_consult/cycle140_vb_ltv_funnel_step_definition.md`)
- **위험 등급**: LOW (scanner 매수 진입 *전* 영역 한정, 사이클 38 명문화 영속)

## VB 5단계 funnel hook

| step_no | step_name | survived 조건 |
|---------|-----------|--------------|
| 1 | "거래량순위 + stock_master 기반 후보" | stock_master `list_by_filter` 응답 영역 |
| 2 | "시총 + 거래대금 필터 통과" | universe_filtered (시총 1,000억+ / 거래대금 200억+) |
| 3 | "일봉 fetch 통과" | candle_fetch_ok (KIS fetch_daily_candles 정상) |
| 4 | "전일 Range > 0 + noise 계산 통과" | prev_range + noise_list 존재 영역 |
| 5 | "K값 계산 + target_offset > 0" | k_value_computed = final_prepared |

## LTV 6단계 funnel hook

| step_no | step_name | survived 조건 |
|---------|-----------|--------------|
| 1 | "거래량순위 + stock_master 기반 후보" | stock_master 응답 영역 |
| 2 | "시총 + 거래대금 필터 통과" | universe_filtered |
| 3 | "일봉 fetch 통과" | candle_fetch_ok |
| 4 | "전일 Range + noise 통과" | prev_range + noise_list 존재 |
| 5 | "연속 상한가 필터 통과" | consecutive_limit_pass (직전 N영업일 상한가 미만) |
| 6 | "K값 계산 + target_offset > 0" | k_value_computed = final_prepared |

## 구현 영역

### VB / LTV 공통 (donchian 답습)

1. 모듈 상단 `VB_FUNNEL_STAGES: tuple[FunnelStage, ...] = (FunnelStage(1, "..."), ...)` / `LTV_FUNNEL_STAGES`
2. `prepare()` `self._reset_funnel_steps()` 호출 (사이클 39 영속)
3. `_scan_universe()` 직후 step 1 / step 2 hook (donchian L136~145 답습)
4. `prepare()` for loop 단계 hook (step 3~5 / step 3~6)
5. `survived: list[str]` 영역 = donchian `_resolve_ticker_name` 자동 dict 변환 영역 (사이클 41 영속)
6. `excluded: list[dict]` 영역 = 수치 포함 사유 (사이클 41 답습)

### `_record_funnel_pipeline_step(stage, *, survived, step_conditions, excluded=None)` 시그너처

```python
self._record_funnel_pipeline_step(
    VB_FUNNEL_STAGES[2],  # step 3 일봉 fetch
    survived=candle_fetch_ok_tickers,
    step_conditions="KIS fetch_daily_candles 정상 응답",
    excluded=candle_fetch_excluded,
)
```

## 사이클 132 UI 안내 메시지 제거

`frontend/src/pages/StrategyFunnel.tsx` — VB/LTV "단계별 funnel 후속 사이클 영역 (사이클 133 인계)" 메시지 영역 영구 영속 제거 + 정상 funnel 표시 활성화.

## Red 회귀 가드 (G-143 시리즈)

### G-143-VB — VB 5단계 hook
- G-143-VB-1: `VB_FUNNEL_STAGES` 모듈 상수 (5 stages) 영속
- G-143-VB-2: `prepare()` `_record_funnel_pipeline_step` 호출 ≥ 5건 영속
- G-143-VB-3: `_reset_funnel_steps()` 호출 영속 (사이클 39 답습)
- G-143-VB-4: AST 가드 — VB `prepare()` 영역 `_record_funnel_pipeline_step` 호출 위치

### G-143-LTV — LTV 6단계 hook
- G-143-LTV-1: `LTV_FUNNEL_STAGES` 모듈 상수 (6 stages) 영속
- G-143-LTV-2: `prepare()` `_record_funnel_pipeline_step` 호출 ≥ 6건 영속
- G-143-LTV-3: `_reset_funnel_steps()` 호출 영속
- G-143-LTV-4: AST 가드 — LTV `prepare()` 영역

### G-143-INTEGRATION
- G-143-INT-1: VB `prepare()` 호출 후 `_funnel_steps` 메모리 적재 영역 5건 영속
- G-143-INT-2: LTV `prepare()` 호출 후 `_funnel_steps` 메모리 적재 영역 6건 영속

### G-143-SAFETY
- G-143-SAFETY-1: VB `_scan_universe` + `prepare()` 본체 동작 영역 변경 0 (signal 결과 동일)
- G-143-SAFETY-2: LTV 동일
- G-143-SAFETY-3: risk/order_engine/realtime/auth 변경 0

## 영속 의무 매트릭스

- 사이클 21 `_scan_stats` 9/10 키 (변경 0, 추가 hook만)
- 사이클 38 명문화 (scanner 매수 진입 *전* 영역 한정)
- 사이클 39+41 funnel hook 패턴 100% 답습
- 사이클 47 FUNNEL_STAGES 위임 패턴 답습
- 사이클 79 G-AST2 (영향 0)
- 사이클 81 G-AST1 (영향 0)
- 사이클 108 stock_master 베이스 (영향 0)
- 사이클 122/126/127/128/129/131/132/133/134/135/136/137/138/139/140/142 영속 (영향 0)
