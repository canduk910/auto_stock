# 사이클 142 — VB/LTV funnel hook 11단계 + LTV 결함 #1+#2 통합 시정

- **사용자 결정**: 옵션 A 단일 통합 TDD (사이클 142)
- **인계 영역**: 사이클 140 funnel 자문 + 사이클 141 LTV 재설계 자문 (refactor + domain 병렬)
- **위험 등급**: MEDIUM (scheduler.py + LTV strategy 상태 동기화 + funnel hook)

## 통합 영역

### 1. VB 5단계 funnel hook (사이클 140 자문)

VB `_scan_universe` + `prepare()` for loop 영역에 `_record_funnel_pipeline_step()` 호출:
1. 유니버스 후보 (universe_candidates)
2. 시총 + 거래대금 통과 (universe_filtered)
3. 가격 정합성 통과 (price_filtered)
4. 일봉 fetch 통과 (candle_fetch_ok)
5. K값 계산 통과 (final_prepared)

### 2. LTV 6단계 funnel hook (사이클 140 자문)

LTV `_scan_universe` + `prepare()` for loop 영역:
1. 유니버스 후보
2. 시총 + 거래대금 + 전일대비 통과 (min_prdy_rate 5% 이상)
3. 가격 정합성 통과
4. 일봉 fetch 통과
5. 연속 상한가 필터 통과 (consecutive_limit_pass)
6. K값 계산 통과

### 3. LTV 결함 #1 시정 (사이클 141 자문)

**현행 (`scheduler.py:1786~1807`)**:
```python
if keeps_post_nxt:
    logger.info("%s POST_NXT 활성 — 15:20 강제 청산 보류, ...", ...)
    continue  # ← LTV.check_force_clear() 호출 자체 안 함
```

**시정**:
```python
clear_tickers = strategy.check_force_clear()
if not clear_tickers:
    continue

allowed = get_tradable_boards(sid, strategy.config.params)
keeps_post_nxt = MarketBoard.POST_NXT in allowed
if keeps_post_nxt:
    logger.info(
        "%s POST_NXT 활성 — 15:20 강제 청산: %d 종목 (상한가 모드 제외)",
        strategy.config.name, len(clear_tickers),
    )
# 청산 진행
```

### 4. LTV 결함 #2 시정 (사이클 141 자문)

**현행 (`scheduler.py:1210~1215`)**:
```python
if gap_rate >= gap_up_threshold:
    logger.info("트레일링 스탑 모드: %s 갭률 %.1f%%", t(ticker), gap_rate)
    # ← LTV strategy 후성 미동기화
```

**시정**:
```python
if gap_rate >= gap_up_threshold:
    if strategy_id == "long_tail_volatility":
        strategy = self.registry.get(strategy_id)
        if strategy and hasattr(strategy, "_limit_up_reached"):
            strategy._limit_up_reached.add(ticker)
        pos.high_since_buy = today_open  # 트레일링 기준점 = 시가
    logger.info(
        "트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s, 기준가: %d)",
        t(ticker), gap_rate, strategy_id, today_open,
    )
```

### 5. 사이클 132 UI 안내 메시지 제거 (선택)

`frontend/src/pages/StrategyFunnel.tsx` — VB/LTV "단계별 funnel 후속 사이클 영역 (사이클 133 인계)" 안내 제거.

## Red 회귀 가드 (G-142 시리즈)

### G-142-FUNNEL — VB/LTV funnel hook 영역
- G-142-FUNNEL-1: VB `prepare()` `_record_funnel_pipeline_step` 호출 ≥ 5건
- G-142-FUNNEL-2: LTV `prepare()` `_record_funnel_pipeline_step` 호출 ≥ 6건
- G-142-FUNNEL-3: VB `_funnel_steps` 8개 키 (step_no=1~5 + name + survived + excluded)
- G-142-FUNNEL-4: LTV `_funnel_steps` 9개 키

### G-142-DEFECT1 — 결함 #1 시정 가드
- G-142-DEFECT1-1: `_force_clear_main_only` LTV `check_force_clear()` 호출 영구 보장 (`keeps_post_nxt=True` 케이스)
- G-142-DEFECT1-2: VB는 변경 0 (POST_NXT 미포함 케이스 정상 작동)
- G-142-DEFECT1-3: LTV `check_force_clear()` 본체 변경 0 (상한가 모드 제외 로직)
- G-142-DEFECT1-4: AST 가드 — `continue` 분기 `check_force_clear()` 호출 *전* 차단 0건

### G-142-DEFECT2 — 결함 #2 시정 가드
- G-142-DEFECT2-1: `_execute_next_day_clear` 트레일링 분기 LTV `_limit_up_reached.add` 호출 보장
- G-142-DEFECT2-2: 트레일링 분기 `pos.high_since_buy = today_open` 설정 보장
- G-142-DEFECT2-3: VB 변경 0 (`strategy_id != "long_tail_volatility"`)
- G-142-DEFECT2-4: 후성 093370 운영 사례 재현 (freezegun)
- G-142-DEFECT2-5: AST 가드 — 트레일링 분기 `_limit_up_reached.add` 호출 검증

### G-142-SAFETY — 매매 안전성 직접 검증
- G-142-SAFETY-1: 사이클 38 명세 정합 (상한가 모드 종목 15:20 보존)
- G-142-SAFETY-2: VB 변경 0 (사용자 verbatim "VB는 잘 동작" 보존)
- G-142-SAFETY-3: CLAUDE.md "절대 깨지 말 것" 8 영역 영속
- G-142-SAFETY-4: risk/order_engine/realtime/auth import 0건

## 행위 보존 가정

- 사이클 38 명문화 영속
- 사이클 39+41 funnel hook 패턴 답습
- 사이클 67 facade 답습
- 사이클 79 G-AST2 영속
- VB `DEFAULT_TRADABLE_BOARDS=("main",)` 영속
- LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")` 영속
- `_pending_next_day_clear` + 30s 안정화 영역 보존
