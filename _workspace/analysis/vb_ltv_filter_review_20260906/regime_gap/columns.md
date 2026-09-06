# 컬럼 사전 — 정보 확정 시각 명시

정보 확정 시각(when) 코드

| 코드 | 뜻 | 특징량 사용 |
|---|---|---|
| `KEY` | 키·라벨 | — |
| `META` | 표본 구성 라벨(빌드 산물) | 층화에만 |
| `D-1` | **D-1 종가(15:30 KST)까지의 정보** | ✅ |
| `D0900` | **D 09:00 시가로 확정** | ✅ |
| `DCLS` | D 고저·종가·거래대금 | ❌ **성과 전용** |
| `D+1` | D+1 시가 | ❌ **성과 전용(오버나잇)** |
| `FILL` | 실체결(trade_history) 사실 | ❌ |

## `obs_regime_gap.csv` — 107 컬럼 / 25361 행

| 컬럼 | 확정 시각 | 설명 |
|---|---|---|
| `strategy` | `KEY` | volatility_breakout \| long_tail_volatility |
| `target_date` | `KEY` | 거래일 D (KST) |
| `ticker` | `KEY` | 종목코드 6자리 |
| `name` | `KEY` | 종목명 (stock_master 현재 스냅샷) |
| `in_funnel_window` | `KEY` | 1 = 그 전략의 저장 funnel 행이 존재하는 날 (VB/LTV 07-13~09-03) |
| `prev_date` | `KEY` | 특징량 기준일 = 그 종목의 D 직전 실봉 날짜 |
| `prev_trading_day` | `KEY` | 시장 기준 D-1 거래일 |
| `prev_gap_flag` | `KEY` | 1 = prev_date != prev_trading_day (거래정지 등으로 D-1 봉 결측) |
| `next_date` | `KEY` | D+1 거래일 (오버나잇 청산 기준일) |
| `idx_k200_ticker` | `KEY` | KOSPI200(069500) 프록시 ETF 티커 |
| `idx_kq150_ticker` | `KEY` | KOSDAQ150(229200) 프록시 ETF 티커 |
| `in_stored_pool` | `META` | 1 = 저장 funnel 최종 후보(VB step6 / LTV step7)에 있음. 저장 내용은 16:20 저녁 캡처 = D 당일 거래대금으로 걸러진 풀(룩어헤드 원천) |
| `sample_stored_eligible` | `META` | **표본 (i) 적격 부분집합** = in_stored_pool ∧ prev_tv_eligible |
| `sample_stored_contaminated` | `META` | 저장 풀이지만 D-1 거래대금 미달 = 룩어헤드 오염. **대조 전용** |
| `sample_recon_d1` | `META` | **표본 (ii) D-1 재구성 풀** = D-1 거래대금 임계 ∧ D-1 종가 3,000~500,000 ∧ 6자리 숫자 ∧ ETF 키워드 제외 |
| `sample_recon_d1_top100` | `META` | recon_rank_prev_tv <= max_scan_stocks(100) — 라이브 limit 근사 |
| `prev_tv_won` | `D-1` | D-1 거래대금(원). stock_master_daily.trade_value 우선, 결측 시 close×volume |
| `prev_tv_source` | `D-1` | trade_value \| close_x_volume |
| `prev_tv_eligible` | `D-1` | 1 = prev_tv_won >= 전략 min_trade_amount (VB 500억 / LTV 200억) |
| `recon_rank_prev_tv` | `D-1` | 그날 재구성 풀 안에서 D-1 거래대금 내림차순 순위 |
| `ltv_consec_limitup_excl` | `D-1` | 1 = prev 부터 2일 연속 (종가-시가)/시가 >= +25% (LTV 연속상한가 배제 재현) |
| `prev_open` | `D-1` | 직전 실봉 시가 |
| `prev_high` | `D-1` | 직전 실봉 고가 |
| `prev_low` | `D-1` | 직전 실봉 저가 |
| `prev_close` | `D-1` | 직전 실봉 종가 (갭·목표가·LTV 게이트의 분모) |
| `prev_range` | `D-1` | prev_high - prev_low |
| `prev_range_pct` | `D-1` | prev_range / prev_close × 100 |
| `prev_ret_bp` | `D-1` | (c) D-1 종가 수익률 = prev_close / prev_prev_close - 1 (bp) |
| `prev_ret5_bp` | `D-1` | (c) 5일 수익률 = prev_close / (5봉 전 종가) - 1 (bp) |
| `k_noise` | `D-1` | prev 이전 k_period 일 평균 noise = mean(1 - \|c-o\|/(h-l)). VB k_period=15 / LTV=20 |
| `k_noise_n` | `D-1` | noise 평균에 쓰인 봉 수 |
| `k_noise_full` | `D-1` | 1 = k_noise_n >= k_period (창이 온전) |
| `idx_k200_prev_ret_bp` | `D-1` | (a) KOSPI200(069500) 전일 수익률 (bp) |
| `idx_k200_ma5_pos_pct` | `D-1` | KOSPI200(069500) — (b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝 |
| `idx_k200_ma20_pos_pct` | `D-1` | KOSPI200(069500) — (b) MA20 대비 위치 % |
| `idx_k200_ma60_pos_pct` | `D-1` | KOSPI200(069500) — (b) MA60 대비 위치 % |
| `idx_k200_vol20_ann_pct` | `D-1` | KOSPI200(069500) — (c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %) |
| `idx_k200_ret5_bp` | `D-1` | KOSPI200(069500) — (d) 5일 누적 수익률 (bp) |
| `idx_k200_ma5_gt_ma20` | `D-1` | KOSPI200(069500) — (e) 1 = MA5 > MA20 |
| `idx_k200_updays20_ratio` | `D-1` | KOSPI200(069500) — (f) 최근 20일 중 상승일 비율 |
| `idx_kq150_prev_ret_bp` | `D-1` | (a) KOSDAQ150(229200) 전일 수익률 (bp) |
| `idx_kq150_ma5_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝 |
| `idx_kq150_ma20_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) MA20 대비 위치 % |
| `idx_kq150_ma60_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) MA60 대비 위치 % |
| `idx_kq150_vol20_ann_pct` | `D-1` | KOSDAQ150(229200) — (c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %) |
| `idx_kq150_ret5_bp` | `D-1` | KOSDAQ150(229200) — (d) 5일 누적 수익률 (bp) |
| `idx_kq150_ma5_gt_ma20` | `D-1` | KOSDAQ150(229200) — (e) 1 = MA5 > MA20 |
| `idx_kq150_updays20_ratio` | `D-1` | KOSDAQ150(229200) — (f) 최근 20일 중 상승일 비율 |
| `mac_snapshot_date` | `D-1` | D-1 이하의 마지막 매크로 스냅샷 날짜 (없으면 공란) |
| `mac_stale_days` | `D-1` | prev_trading_day - mac_snapshot_date (일). 0 = 당일치 |
| `mac_regime` | `D-1` | dkstock regime 라벨 (표본 전 구간 defensive) |
| `mac_vix` | `D-1` | VIX |
| `mac_fear_greed` | `D-1` | Fear & Greed 점수 |
| `mac_cash_min` | `D-1` | raw_response.regime.params.cash_min |
| `mac_cash_usage_ratio` | `D-1` | computed_cash_usage_ratio |
| `eff_k_mult` | `D0900` | 실효 배수 = int(int(prev_range×k_noise)×k_value) / prev_range (VB k_value=1.3 → 실측 ≈0.73) |
| `open_D` | `D0900` | D 시가 |
| `gap_pct` | `D0900` | **갭** = (D 시가 - prev_close) / prev_close × 100 |
| `gap_bp` | `D0900` | gap_pct × 100 (bp) |
| `gap_over_prev_range` | `D0900` | (a) D 시가의 prev_close 대비 위치를 전일 range 로 나눈 배수 |
| `target_live` | `D0900` | 라이브 목표가 = open + int(int(prev_range × k_noise) × k_value) |
| `target_simple` | `D0900` | 단순 목표가 = open + k_value × prev_range (참고) |
| `ltv_prdy_gate_at_open` | `D0900` | LTV: 1 = 시가가 이미 prev_close×1.05 이상 |
| `idx_k200_gap_bp_D0900` | `D0900` | KOSPI200(069500) — 지수 갭 = D 시가 / D-1 종가 - 1 (bp) |
| `idx_kq150_gap_bp_D0900` | `D0900` | KOSDAQ150(229200) — 지수 갭 = D 시가 / D-1 종가 - 1 (bp) |
| `ltv_gate_px` | `D0900` | LTV 전일대비 +5% 게이트 가격 = prev_close × 1.05 |
| `high_D` | `DCLS` | D 고가 — 돌파 판정 |
| `low_D` | `DCLS` | D 저가 — 손절 판정 |
| `close_D` | `DCLS` | D 종가 — 15:20 청산 근사 |
| `volume_D` | `DCLS` | D 거래량 |
| `tv_won_D` | `DCLS` | D 거래대금(원) — 저장 풀 룩어헤드의 원인 축 |
| `idx_k200_oc_bp_Dclose` | `DCLS` | KOSPI200(069500) — 지수 D 시가→종가 (bp) — 문맥 전용 |
| `idx_k200_cc_bp_Dclose` | `DCLS` | KOSPI200(069500) — 지수 D-1 종가→D 종가 (bp) — 문맥 전용 |
| `ret_oc_bp` | `DCLS` | (a) 무조건 시가→종가 (bp, gross) |
| `ret_oc_net_bp` | `DCLS` | (a) net = gross - 28bp |
| `ret_oc_won_on_140k` | `DCLS` | (a) gross 를 명목 140,547원에 적용한 원 환산 |
| `breakout_live` | `DCLS` | 1 = high_D >= target_live (그리고 target_live > open_D). None = k_noise 결측 또는 목표가가 시가 이하(갭 관통) |
| `entry_px_live` | `DCLS` | 돌파 시 가정 진입가 = target_live |
| `low_to_entry_bp` | `DCLS` | (low_D/entry - 1) bp — 임의 손절 임계 재적용용 |
| `high_to_entry_bp` | `DCLS` | (high_D/entry - 1) bp |
| `ret_bo_live_bp` | `DCLS` | (b) 라이브 목표가 돌파 조건부 진입→종가 (bp, gross) |
| `ret_bo_live_net_bp` | `DCLS` | (b) net |
| `stopped_live_ub` | `DCLS` | 상한 손절 정의: low_D <= entry×(1-5%) (진입 전 터치 포함 = 손절 과다계상) |
| `stopped_live_lb` | `DCLS` | 하한 손절 정의: close_D <= entry×(1-5%) (확실한 손절만) |
| `ret_bo_live_stopub_bp` | `DCLS` | (b+stop 상한) 손절 시 -500bp 확정 |
| `ret_bo_live_stoplb_bp` | `DCLS` | (b+stop 하한) 손절 시 -500bp 확정 — **주 성과 지표** |
| `ret_bo_live_stopub_net_bp` | `DCLS` | 위의 net |
| `ret_bo_live_stoplb_net_bp` | `DCLS` | 위의 net — **주 성과 지표(net)** |
| `ret_bo_live_stoplb_won_on_140k` | `DCLS` | 주 성과 net 의 원 환산 (명목 140,547원) |
| `ltv_gate_pass_D` | `DCLS` | 1 = high_D >= prev_close×1.05 (전일대비 +5% 게이트가 D 중 성립) |
| `ltv_entry_px` | `DCLS` | LTV 가정 진입가 = max(target_live, gate_px), high_D 가 그 값에 도달할 때만 |
| `ltv_entry_binding` | `DCLS` | gate \| target — 진입가를 결정한 쪽 |
| `ltv_low_to_entry_bp` | `DCLS` | (low_D/ltv_entry - 1) bp |
| `ltv_stopped_ub` | `DCLS` | LTV 상한 손절 정의 |
| `ltv_stopped_lb` | `DCLS` | LTV 하한 손절 정의 |
| `ret_ltv_close_bp` | `DCLS` | LTV 진입→D 종가 (bp, gross) = 15:20 강제청산 근사 |
| `ret_ltv_close_net_bp` | `DCLS` | 위의 net |
| `ret_ltv_close_stoplb_bp` | `DCLS` | LTV 종가청산 + 하한 손절(-5%) — **LTV 주 성과 지표** |
| `ret_ltv_close_stopub_bp` | `DCLS` | LTV 종가청산 + 상한 손절 |
| `ret_ltv_close_stoplb_net_bp` | `DCLS` | 위의 net |
| `ltv_limit_up_D` | `DCLS` | 1 = high_D >= prev_close×1.29 (라이브 상한가 모드 전환 = 익일 청산) |
| `next_open` | `D+1` | D+1 시가 — 오버나잇 청산가 |
| `ret_ltv_overnight_bp` | `D+1` | LTV 진입→D+1 시가 (bp, gross) — 오버나잇 근사(전 진입 대상) |
| `ret_ltv_overnight_net_bp` | `D+1` | 위의 net |
| `ret_ltv_overnight_stopub_bp` | `D+1` | D 중 손절선 터치면 -500bp, 아니면 D+1 시가 청산 |
| `ret_ltv_livemode_bp` | `D+1` | 라이브 근사: ltv_limit_up_D=1 이면 D+1 시가, 아니면 D 종가 |
| `ret_ltv_livemode_net_bp` | `D+1` | 위의 net |

## `trades_features.csv` — 87 컬럼 / 185 행

| 컬럼 | 확정 시각 | 설명 |
|---|---|---|
| `strategy` | `KEY` | volatility_breakout \| long_tail_volatility |
| `ticker` | `KEY` | 종목코드 6자리 |
| `name` | `KEY` | 종목명 (stock_master 현재 스냅샷) |
| `in_funnel_window` | `KEY` | 1 = 그 전략의 저장 funnel 행이 존재하는 날 (VB/LTV 07-13~09-03) |
| `prev_date` | `KEY` | 특징량 기준일 = 그 종목의 D 직전 실봉 날짜 |
| `prev_gap_flag` | `KEY` | 1 = prev_date != prev_trading_day (거래정지 등으로 D-1 봉 결측) |
| `in_obs` | `META` | 1 = obs_regime_gap.csv 에 같은 (strategy, buy_date, ticker) 행이 있어 특징량이 붙음 |
| `in_stored_pool` | `META` | 1 = 저장 funnel 최종 후보(VB step6 / LTV step7)에 있음. 저장 내용은 16:20 저녁 캡처 = D 당일 거래대금으로 걸러진 풀(룩어헤드 원천) |
| `sample_stored_eligible` | `META` | **표본 (i) 적격 부분집합** = in_stored_pool ∧ prev_tv_eligible |
| `sample_stored_contaminated` | `META` | 저장 풀이지만 D-1 거래대금 미달 = 룩어헤드 오염. **대조 전용** |
| `sample_recon_d1` | `META` | **표본 (ii) D-1 재구성 풀** = D-1 거래대금 임계 ∧ D-1 종가 3,000~500,000 ∧ 6자리 숫자 ∧ ETF 키워드 제외 |
| `prev_close` | `D-1` | 직전 실봉 종가 (갭·목표가·LTV 게이트의 분모) |
| `prev_range` | `D-1` | prev_high - prev_low |
| `prev_range_pct` | `D-1` | prev_range / prev_close × 100 |
| `prev_ret_bp` | `D-1` | (c) D-1 종가 수익률 = prev_close / prev_prev_close - 1 (bp) |
| `prev_ret5_bp` | `D-1` | (c) 5일 수익률 = prev_close / (5봉 전 종가) - 1 (bp) |
| `k_noise` | `D-1` | prev 이전 k_period 일 평균 noise = mean(1 - \|c-o\|/(h-l)). VB k_period=15 / LTV=20 |
| `k_noise_full` | `D-1` | 1 = k_noise_n >= k_period (창이 온전) |
| `prev_tv_won` | `D-1` | D-1 거래대금(원). stock_master_daily.trade_value 우선, 결측 시 close×volume |
| `prev_tv_eligible` | `D-1` | 1 = prev_tv_won >= 전략 min_trade_amount (VB 500억 / LTV 200억) |
| `recon_rank_prev_tv` | `D-1` | 그날 재구성 풀 안에서 D-1 거래대금 내림차순 순위 |
| `ltv_consec_limitup_excl` | `D-1` | 1 = prev 부터 2일 연속 (종가-시가)/시가 >= +25% (LTV 연속상한가 배제 재현) |
| `idx_k200_prev_ret_bp` | `D-1` | (a) KOSPI200(069500) 전일 수익률 (bp) |
| `idx_k200_ma5_pos_pct` | `D-1` | KOSPI200(069500) — (b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝 |
| `idx_k200_ma20_pos_pct` | `D-1` | KOSPI200(069500) — (b) MA20 대비 위치 % |
| `idx_k200_ma60_pos_pct` | `D-1` | KOSPI200(069500) — (b) MA60 대비 위치 % |
| `idx_k200_vol20_ann_pct` | `D-1` | KOSPI200(069500) — (c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %) |
| `idx_k200_ret5_bp` | `D-1` | KOSPI200(069500) — (d) 5일 누적 수익률 (bp) |
| `idx_k200_ma5_gt_ma20` | `D-1` | KOSPI200(069500) — (e) 1 = MA5 > MA20 |
| `idx_k200_updays20_ratio` | `D-1` | KOSPI200(069500) — (f) 최근 20일 중 상승일 비율 |
| `idx_kq150_prev_ret_bp` | `D-1` | (a) KOSDAQ150(229200) 전일 수익률 (bp) |
| `idx_kq150_ma5_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝 |
| `idx_kq150_ma20_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) MA20 대비 위치 % |
| `idx_kq150_ma60_pos_pct` | `D-1` | KOSDAQ150(229200) — (b) MA60 대비 위치 % |
| `idx_kq150_vol20_ann_pct` | `D-1` | KOSDAQ150(229200) — (c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %) |
| `idx_kq150_ret5_bp` | `D-1` | KOSDAQ150(229200) — (d) 5일 누적 수익률 (bp) |
| `idx_kq150_ma5_gt_ma20` | `D-1` | KOSDAQ150(229200) — (e) 1 = MA5 > MA20 |
| `idx_kq150_updays20_ratio` | `D-1` | KOSDAQ150(229200) — (f) 최근 20일 중 상승일 비율 |
| `mac_snapshot_date` | `D-1` | D-1 이하의 마지막 매크로 스냅샷 날짜 (없으면 공란) |
| `mac_stale_days` | `D-1` | prev_trading_day - mac_snapshot_date (일). 0 = 당일치 |
| `mac_regime` | `D-1` | dkstock regime 라벨 (표본 전 구간 defensive) |
| `mac_vix` | `D-1` | VIX |
| `mac_fear_greed` | `D-1` | Fear & Greed 점수 |
| `mac_cash_min` | `D-1` | raw_response.regime.params.cash_min |
| `eff_k_mult` | `D0900` | 실효 배수 = int(int(prev_range×k_noise)×k_value) / prev_range (VB k_value=1.3 → 실측 ≈0.73) |
| `open_D` | `D0900` | D 시가 |
| `gap_pct` | `D0900` | **갭** = (D 시가 - prev_close) / prev_close × 100 |
| `gap_bp` | `D0900` | gap_pct × 100 (bp) |
| `gap_over_prev_range` | `D0900` | (a) D 시가의 prev_close 대비 위치를 전일 range 로 나눈 배수 |
| `target_live` | `D0900` | 라이브 목표가 = open + int(int(prev_range × k_noise) × k_value) |
| `idx_k200_gap_bp_D0900` | `D0900` | KOSPI200(069500) — 지수 갭 = D 시가 / D-1 종가 - 1 (bp) |
| `idx_kq150_gap_bp_D0900` | `D0900` | KOSDAQ150(229200) — 지수 갭 = D 시가 / D-1 종가 - 1 (bp) |
| `high_D` | `DCLS` | D 고가 — 돌파 판정 |
| `low_D` | `DCLS` | D 저가 — 손절 판정 |
| `close_D` | `DCLS` | D 종가 — 15:20 청산 근사 |
| `breakout_live` | `DCLS` | 1 = high_D >= target_live (그리고 target_live > open_D). None = k_noise 결측 또는 목표가가 시가 이하(갭 관통) |
| `entry_px_live` | `DCLS` | 돌파 시 가정 진입가 = target_live |
| `ret_bo_live_bp` | `DCLS` | (b) 라이브 목표가 돌파 조건부 진입→종가 (bp, gross) |
| `ret_bo_live_stoplb_bp` | `DCLS` | (b+stop 하한) 손절 시 -500bp 확정 — **주 성과 지표** |
| `ret_bo_live_stopub_bp` | `DCLS` | (b+stop 상한) 손절 시 -500bp 확정 |
| `ret_bo_live_stoplb_net_bp` | `DCLS` | 위의 net — **주 성과 지표(net)** |
| `ltv_gate_pass_D` | `DCLS` | 1 = high_D >= prev_close×1.05 (전일대비 +5% 게이트가 D 중 성립) |
| `ltv_entry_px` | `DCLS` | LTV 가정 진입가 = max(target_live, gate_px), high_D 가 그 값에 도달할 때만 |
| `ret_ltv_close_bp` | `DCLS` | LTV 진입→D 종가 (bp, gross) = 15:20 강제청산 근사 |
| `ltv_limit_up_D` | `DCLS` | 1 = high_D >= prev_close×1.29 (라이브 상한가 모드 전환 = 익일 청산) |
| `ret_ltv_overnight_bp` | `D+1` | LTV 진입→D+1 시가 (bp, gross) — 오버나잇 근사(전 진입 대상) |
| `ret_ltv_livemode_bp` | `D+1` | 라이브 근사: ltv_limit_up_D=1 이면 D+1 시가, 아니면 D 종가 |
| `buy_date` | `FILL` | 매수 체결일 D (KST) |
| `buy_time_kst` | `FILL` | 매수 체결 시각 HH:MM:SS (KST) |
| `sell_ts_kst` | `FILL` | 매도 체결 시각 (KST) |
| `buy_px` | `FILL` | 매수 체결가 |
| `sell_px` | `FILL` | 매도 체결가 |
| `qty` | `FILL` | FIFO 짝지은 수량 |
| `notional_won` | `FILL` | buy_px × qty |
| `ret_gross_bp` | `FILL` | (sell_px/buy_px - 1) bp |
| `ret_net_bp` | `FILL` | gross - (수수료 0.015%×2 + 세금 0.15%). 슬리피지는 체결가에 내재 |
| `pnl_gross_won` | `FILL` | (sell_px - buy_px) × qty |
| `pnl_net_on_140k_won` | `FILL` | ret_net_bp 를 명목 140,547원에 적용 |
| `sell_pl_db` | `FILL` | trade_history.profit_loss (매도행, gross) |
| `entry_0900_0901_30` | `FILL` | 1 = 09:00:00~09:01:30 진입 (VB 09:00 직후 진입 가설 플래그) |
| `entry_before_0900` | `FILL` | 1 = 09:00 이전 진입 (LTV PRE_NXT 보드) |
| `entry_hour` | `FILL` | 매수 시각의 시(hour) |
| `buy_trade_id` | `FILL` | trade_history.id (매수) |
| `sell_trade_id` | `FILL` | trade_history.id (매도) |
| `entry_vs_target_live_bp` | `FILL` | 실체결 매수가 vs 돌파 가정 진입가 (bp) |
| `entry_vs_target_any_bp` | `FILL` | 실체결 매수가 vs target_live (돌파 여부 무관, bp) |
| `entry_vs_open_bp` | `FILL` | 실체결 매수가 vs D 시가 (bp) |

## `index_features.csv` — 16 컬럼 / 166 행

| 컬럼 | 확정 시각 | 설명 |
|---|---|---|
| `trade_date` | `KEY` | 거래일 D |
| `index_label` | `KEY` | kospi200 \| kosdaq150 |
| `index_ticker` | `KEY` | 지수 프록시 ETF 티커 (069500 / 229200) |
| `prev_date` | `KEY` | 특징량 기준일 = 그 종목의 D 직전 실봉 날짜 |
| `prev_close` | `D-1` | 직전 실봉 종가 (갭·목표가·LTV 게이트의 분모) |
| `prev_ret_bp` | `D-1` | (c) D-1 종가 수익률 = prev_close / prev_prev_close - 1 (bp) |
| `ma5_pos_pct` | `D-1` | (b) 종가의 MA5 대비 위치 % — 창은 D-1 에서 끝 |
| `ma20_pos_pct` | `D-1` | (b) MA20 대비 위치 % |
| `ma60_pos_pct` | `D-1` | (b) MA60 대비 위치 % |
| `vol20_ann_pct` | `D-1` | (c) 20일 일간수익률 표준편차 × sqrt(252) × 100 (연율 %) |
| `ret5_bp` | `D-1` | (d) 5일 누적 수익률 (bp) |
| `ma5_gt_ma20` | `D-1` | (e) 1 = MA5 > MA20 |
| `updays20_ratio` | `D-1` | (f) 최근 20일 중 상승일 비율 |
| `gap_bp_D0900` | `D0900` | 지수 갭 = D 시가 / D-1 종가 - 1 (bp) |
| `oc_bp_Dclose` | `DCLS` | 지수 D 시가→종가 (bp) — 문맥 전용 |
| `cc_bp_Dclose` | `DCLS` | 지수 D-1 종가→D 종가 (bp) — 문맥 전용 |
