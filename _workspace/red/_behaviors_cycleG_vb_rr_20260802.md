# 사이클 G Phase 1 — VB RR 개선 (C2 실패돌파 조기청산 + RS/RSI 관찰)

계획: `~/.claude/plans/luminous-drifting-widget.md` (승인됨)
배경: 사이클 F 실측 VB N65 승률 35% RR 1.35 < 필요1.83 열위. RR=avg_win/|avg_loss|.
사용자 결정: C2(손절) + 진입관찰 병행 / 진입=관찰-배제0, 청산=default-off+백테스트.

## 매매 안전성 (전체)
Part A(C2) = `failed_breakout_exit_enabled=False` default 로 활성 전까지 byte-identical(BFB 사이클 C 선례). Part B = prepare 관찰 배제 0(사이클 38). `git diff risk.py order_engine.py src/realtime/ src/auth/ src/api/order.py scheduler(hot path)` = 0. 데이트레이드 정체성(tradable_boards=("main",)·15:20·POST_NXT 금지) 무변경. 신규 파라미터 PARAM_RANGES 미편입.

---

## Part A — C2 실패 돌파 조기청산 (청산, avg_loss↓)

앵커: `volatility_breakout.py` check_exit_signal(880-932, 손절 분기 896-911 *뒤*·익일안전망 923-930 *앞*) / `_targets[ticker]["boards"][board]["target_price"]`(on_open_price_confirmed 755-759) + top-level `_targets[ticker]["target_price"]`(762-766 폴백) / `_resolve_active_board()`(활성보드) / DEFAULT_PARAMS(71-95).

- **G-A1 (파라미터)**: DEFAULT_PARAMS 신규 3키 — `failed_breakout_exit_enabled: bool = False`(default-off) + `failed_breakout_buffer_pct: float = -0.5`(재이탈 임계 = target × (1+buffer/100), 예 −0.5% 아래) + `failed_breakout_confirm_ticks: int = 2`(연속 확인). **PARAM_RANGES/INT_PARAMS 미편입**(진입/청산 정체성 상수).
- **G-A2 (상태)**: `__init__` 에 `self._failed_breakout_count: dict[str, int] = {}`. `prepare()` transient clear 지점(vb.py:144-146, _targets/_open_confirmed 옆) + `on_position_closed`(979-986) 에서 정리.
- **G-A3 (조기청산 분기)**: check_exit_signal 손절 분기 *뒤*: `enabled` and (활성보드 or top-level) `target_price > 0` 획득 → `if current_price < target_price × (1 + buffer/100)`: 카운터++, `>= confirm_ticks` 면 `[vb_failed_breakout_exit]` INFO + `Signal.STOP_LOSS`; 아니면(재이탈 미달·회복) 카운터 0 리셋. `enabled=False`(기본)면 분기 미진입.
- **G-A4 (default-off byte-identical, HIGH)**: enabled=False → 분기 완전 미진입, 기존 손절/익일안전망 byte 동일. 기존 VB check_exit 테스트 무변경.
- **G-A5 (승자 미간섭, HIGH)**: 현재가가 target_price 위 유지(승자) → 카운터 0, 조기청산 무발화. 재이탈만 트리거.
- **G-A6 (경계)**: confirm_ticks−1 회 재이탈 후 회복 → 미발화(카운터 리셋). confirm_ticks 연속 재이탈 → 발화. buffer 정확 적용.
- **재사용**: target_price(기존), Signal.STOP_LOSS(enum), risk.on_tick→execute_sell(risk.py:130-133). 데이트레이드 15:20 캡 무관(손절 조기화일 뿐).

---

## Part B — RS/RSI 관찰-배제0 배선 (진입, 승률↑)

앵커: prepare 말미(vb.py:338, `_apply_quant_filter_in_prepare` 옆) / quant 훅(502-604, 배제0 패턴 템플릿) / VB_FUNNEL_STAGES(30-38, 7→9 확장) / `stock_master_daily.get_recent_daily(days≤100)` / `quant_score._rank_descending`(141).

- **G-B1 (RSI 순수함수)**: 신규 모듈 `src/engine/ta_indicators.py` `rsi(closes: list[float]|Series, period=14) -> float|None`(Wilder 평균, 데이터 부족 None). **kojiro_indicators atr/ema 재사용 금지**(ATR 이원화·kojiro 정체성). 결정적 시리즈 검증(상승 연속→RSI 高, 하락→低).
- **G-B2 (RS 순수함수)**: `ta_indicators.relative_strength(stock_closes, index_closes, period=20) -> float|None` — 종목 N일 수익률 − 지수 N일 수익률(또는 비율). 유니버스 횡단 랭킹은 `_rank_descending` 재사용(호출자에서).
- **G-B3 (파라미터)**: DEFAULT_PARAMS `rs_filter_enabled=False`/`rsi_filter_enabled=False` + 임계(`rsi_extreme_max=85` 등, RSI 는 극단>85+다이버전스만 관찰 — 단순>70 컷 금지). **PARAM_RANGES 미편입**.
- **G-B4 (관찰 훅)**: `_apply_rs_rsi_observe_in_prepare(tickers)` 신규(quant 훅 미러) — prepare 말미 호출. 각 후보 일봉(get_recent_daily) + 지수(KODEX200 069500) 일봉으로 rsi/rs 계산 → `_record_funnel_pipeline_step`(VB_FUNNEL_STAGES step 8/9 신규, "상대강도 RS 관찰"·"RSI 관찰") 스코어 detail 기록 → **`return list(tickers)` 배제 0**.
- **G-B5 (배제 0, HIGH)**: 입력 tickers == 출력(관찰만, 배제 0). 보유 protected 스킵(사이클 32 R4) + 결측/예외 fail-open(사이클 88 G-REJECT).
- **G-B6 (지수 일봉)**: KODEX200 069500 일봉 1회 조회(RS 벤치마크). 미수신 graceful(RS None, 관찰만 skip).
- **B3 재무(작업 없음)**: `_apply_quant_filter_in_prepare` 가 이미 관찰 중 — 무변경 확인만.

---

## 검증 게이트 (배포 후, 코드 밖)
- Part A: default-off 배포 → 외부 MCP 백테스트(`kis_mcp_enabled`) buffer/confirm 스윕 → 활성 결정 → te_metrics RR/avg_loss 재측정.
- Part B: 2주 관찰 → RS/RSI 스코어별 승률·RR 유의성 → 실배제 활성(별도 사이클).
- 추적: `GET /api/strategies/te?months=3` VB verdict/rr/required_rr/win_rate. 목표 RR>필요RR(superior 전환).

## 회귀 가드
Part A: `test_cycleG_vb_failed_breakout_exit.py` — default-off byte동일 / 재이탈 confirm_ticks 발화 / 승자 미간섭 / buffer·confirm 경계 / 카운터 리셋. Part B: `test_cycleG_ta_indicators.py`(rsi/rs 결정적) + `test_cycleG_vb_rs_rsi_observe.py`(배제0·funnel 기록·protected·fail-open). 안전: 8영역 diff 0 + 기존 VB check_exit/prepare 스위트 무회귀.
