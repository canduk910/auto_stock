# VB(volatility_breakout) · LTV(long_tail_volatility) 사실지

- 작성: 2026-09-06 (KST 08:1x), 조사자 = 코드·이력 조사 에이전트 (읽기 전용 — 리포 무수정, 운영 DB SELECT 만)
- 정본 우선순위: **운영 DB 실측 > 코드(HEAD 9f09977, 09-06 실측) > 문서**. 세 소스가 다를 때는 그 사실 자체를 적었다.
- 출처 표기 = `파일:행`. DB 수치는 `[DB 09-06]` 표기. 모든 손익은 `trade_history.profit_loss` gross(수수료·세금 미반영).

---

## 0. 브리프와 다른 것 — 먼저 읽을 것

| 항목 | 브리프(09-06 실측이라 적힘) | 이번 실측 / 코드 | 출처 |
|---|---|---|---|
| VB `k_period` | (언급 없음, 코드 기본 20) | **15** (DB) — `days = k_period+2 = 17 < min_required=22` 라 **일봉 어댑터가 매번 KIS 폴백** (§2.3) | `[DB 09-06] strategy_config` · `volatility_breakout.py:236-239` · `stock_master_daily.py:690-695` |
| LTV `tradable_boards` | 3보드 | **`["main","pre_nxt"]` 2보드** (post_nxt 없음). 코드 기본값만 3보드 | `[DB 09-06]` · `long_tail_volatility.py:71` |
| LTV 손절 | 당일 −3% / 상한가 모드 −5% | **당일 −5% (`intraday_stop_loss`) / 상한가 모드 −2% (`overnight_stop_loss`)**, `gap_up_threshold` **7**(기본 10), `trailing_stop_rate` **−1.2**(기본 −2) | `[DB 09-06]` · `long_tail_volatility.py:90-95` |
| VB 손절 | −5% | −5% 맞음 (`stop_loss_main=-5` 우선, `stop_loss_rate=-5` 폴백) | `[DB 09-06]` · `volatility_breakout.py:918-956` |
| VB/LTV `exchange` | (언급 없음) | 둘 다 **`SOR`** (DB). `nxt_tradable=False` 종목은 주문 시 KRX 다운그레이드 (루트 CLAUDE.md 규약) | `[DB 09-06]` |
| 퀀트/RS/RSI 플래그 | 전부 False | DB `params` 에 키 자체가 **없음** → `DEFAULT_PARAMS` False 적용 = 결과 동일 | `[DB 09-06]` · `volatility_breakout.py:105-119` |
| 관찰 스냅샷 시각 | 잠정 16:20→익일 / 확정 09:30→당일 | **VB·LTV 행은 전부 `is_provisional=true`(366/320행, 40일)** 이고 `snapshot_at` 은 항상 **08:02 KST**(그날 첫 INSERT), 내용은 **그날 마지막 캡처**(보통 16:20) 로 덮인다 — §3.3 | `[DB 09-06]` · `strategy_funnel.py:114-120` |
| 실현손익 | VB 64매도 −83,540 / LTV 37매도 −39,025 | 동일 재현 (07-01~09-04 마지막 체결) | `[DB 09-06]` |

---

## 1. 라이브 설정 (strategy_config, `[DB 09-06]`) vs 코드 기본값

### 1.1 volatility_breakout — `enabled=true`, `weight=0.15`, `updated_at=2026-08-18 08:10:53Z(17:10 KST)`

| 키 | DB(라이브) | 코드 DEFAULT (`volatility_breakout.py:84-121`) | 비고 |
|---|---|---|---|
| `tradable_boards` | `["main"]` | `("main",)` :82 | 사이클 26 KRX ONLY |
| `k_period` | **15** | 20 | 노이즈 평균 창 + 일봉 fetch 일수(`k_period+2`) |
| `k_value_krx_main` | **1.3** | 1.0 | 07-10 자문 시점에도 1.3 (`cycle201_vb_weight_derisk.md:11,37`) |
| `k_value_nxt_pre/post` | 1 / 1 | 1.0 | 미사용 보드 |
| `position_ratio` | **0.35** | 0.10 | 07-15 사이클 212 에서 0.5→0.35 (커밋 4327a16) |
| `max_positions` | **2** | 10 | |
| `stop_loss_rate` / `stop_loss_main` / `stop_loss_pre_nxt` | −5 / −5 / −5 | −3.0 / (없음) / (없음) | 실효 −5% |
| `daily_loss_limit` | **−7** | −5.0 | `is_daily_loss_exceeded` 기준 |
| `min_market_cap` | **500억** | 1,000억 | `list_by_filter` DB-side |
| `min_trade_amount` | **500억** | 200억 | 07-10 자문 시점에도 50B (`cycle201:139`) |
| `max_scan_stocks` | 100 | 100 | `list_by_filter(limit=100)` |
| `exchange` | `SOR` | `KRX` | |
| `reentry_cooldown_days` | (키 없음→2) | 2 | 사이클 201 |
| `quant_filter_enabled`/`rs_filter_enabled`/`rsi_filter_enabled` | (키 없음→False) | False | 관찰 전용, 배제 0 |
| `failed_breakout_exit_enabled` | (키 없음→False) | False | 사이클 G Part A default-off |
| `max_lot_ratio_mult` | (키 없음→2.5) | 2.5 | cycle245 ρ축 캡 |

### 1.2 long_tail_volatility — `enabled=true`, `weight=0.10`, `updated_at=2026-08-18 08:10:53Z`

| 키 | DB(라이브) | 코드 DEFAULT (`long_tail_volatility.py:73-101`) |
|---|---|---|
| `tradable_boards` | **`["main","pre_nxt"]`** | `("pre_nxt","main","post_nxt")` :71 |
| `k_period` | 20 | 20 |
| `k_value_krx_main` / `nxt_pre` / `nxt_post` | 1 / 1 / 1 | 1.0 |
| `min_prdy_rate` | 5 | 5.0 |
| `position_ratio` | **0.2** | 0.15 |
| `max_positions` | **4** | 6 |
| `intraday_stop_loss` | **−5** | −3.0 |
| `limit_up_threshold` | 29 | 29.0 |
| `overnight_stop_loss` | **−2** | −5.0 |
| `gap_up_threshold` | **7** | 10.0 |
| `trailing_stop_rate` | **−1.2** | −2.0 |
| `daily_loss_limit` | **−7** | −5.0 |
| `min_market_cap` / `min_trade_amount` | **500억** / 200억 | 1,000억 / 200억 |
| `exclude_consecutive_limit` | 2 | 2 |
| `reentry_cooldown_days` | 2 | 2 (사이클 213) |
| `exchange` | `SOR` | `KRX` |

### 1.3 공통 시스템 설정 (`[DB 09-06] system_config`)
- `price_filter_min=3,000` / `price_filter_max=500,000` / `price_filter_mode=HARD` — prepare 가격 필터 소스 (`strategy_base.py:1536-1538`)
- `cash_usage_ratio=1.0`
- `account_risk_block_pct` 키 **없음** → 계좌 SOFT 게이트는 다크런치 상태(항상 False, `strategy_base.py:1245-1248`)
- 예산 역산: cycle245 로그의 ρ컷오프 VB 341,515 / LTV 130,100 (`_workspace/00_URGENT_WORKLIST.md:78`) → `int(예산×0.35)=136,606` → VB 예산 ≈ 390,300 → 순자산 ≈ **2.60M원**(09-04). 1포지션 명목 = VB 136,606원(순자산 5.25%, 최대 2개 = 10.5%) / LTV 52,040원(2.0%, 최대 4개 = 8%)

---

## 2. 진입~청산 end-to-end (코드 사실)

### 2.1 prepare 가 언제 도는가
| 시각(KST) | 경로 | 출처 |
|---|---|---|
| 07:55 부팅(`TIME_BOOT`) → `_boot()` 내 prepare | `scheduler.py:56, 2013` |
| 07:59 사전구독 전 유니버스 비면 VB/LTV 재prepare | `scheduler.py:721-736` |
| 09:00:05 이후 `_scan_loop` 5분 주기: `_scanned_tickers` 비면 재prepare (VB/LTV/BFB/VCP) | `scheduler.py:2490-2529` |
| 16:20 저녁 캡처(`TIME_EVENING_FUNNEL_CAPTURE`)가 **7전략 전부 prepare() 재호출** 후 잠정 스냅샷 | `scheduler.py:69, 2988-3050` · `data_load_tasks.py:208-237` |
| 재시작 직후: 저녁 캡처 루프가 `immediate_first_run=True` + `initial_delay_secs=600` 이라 **부팅 10분 뒤 한 번 더 prepare+캡처** | `task_loop_helper.py:54-57,102-107` · `data_load_tasks.py:236` |

prepare 시작 시 `_targets/_open_confirmed/_prev_price(/_failed_breakout_count)` clear (`volatility_breakout.py:175-178`, `long_tail_volatility.py:172-174`). `_cooldown_until` 은 유지(G-VB-NO-DAILY-RESET).

### 2.2 유니버스 필터 (순서대로)
1. `stock_master.list_by_filter(min_market_cap, min_trade_amount, limit=max_scan_stocks)` — DB 생성컬럼 `hts_avls_eok ≥ ceil(min_market_cap/1e8)` ∧ `acml_tr_pbmn_won ≥ min_trade_amount`, KIS 호출 0 (`volatility_breakout.py:400-404`, `long_tail_volatility.py:427-431`, `src/db/stock_master.py:512-552`). 시총·거래대금 원천 = 20:00/07:48 KRX 전체 적재(`scanner.py:1627+`, 전일 확정치).
2. 6자리 숫자 ticker 만 + `ETF_KEYWORDS` 이름 제외 (`vb:413-416`, `ltv:440-443`).
3. 가격 필터 `_apply_price_filter_in_prepare` — `stock_master.raw.bfdy_clpr` 기준 3,000~500,000, 결측은 통과, 보유 종목 보호 (`strategy_base.py:1520-1580`). VB 는 `_scan_universe` 안(`vb:423`), LTV 도 안(`ltv:471`) → **funnel step1 "원천 후보" 는 이미 가격 필터 뒤 값**.
4. 진입 차단 플래그 `_apply_master_block_filter_in_prepare` → `scanner._is_master_blocked_for_entry` (`strategy_base.py:1493-1518`, `scanner.py:2652-2712`). **현행 실효 11건** = master_raw 7(거래정지 `trht_yn`·정리매매 `sltr_yn`·관리 `mang_issu_yn`·공매도과열 `ssts_hot_yn`·이상급등 `stange_runup_yn`·시장경고 `mrkt_alrm_cls_code ≥ "02"`·KOSDAQ 투자주의환기 `invt_alrm_yn`) + FHKST raw 4(`mrkt_warn_cls_code ≥ "02"`·단기과열 `short_over_yn`·정리매매·임시정지 `temp_stop_yn`). funnel 라벨의 "13건" 은 사이클 157 당시 값(사이클 203 종목상태코드 차단 제거 + 204 투자주의(01) 해제로 11건, `scanner.py:2655,2667-2677`).
5. (LTV 만) 연속 상한가 필터: `prev` 부터 `exclude_consecutive_limit`(2)일 연속 `(종가−시가)/시가 ≥ +25%` 면 제외 (`ltv:302-315, 389-408`). 기준이 전일대비가 아니라 **시가대비**임.

### 2.3 일봉 소스
- `get_recent_daily_normalized(ticker, days=k_period+2, min_required=22)` (`vb:237-239`, `ltv:234-236`). 어댑터: DB `stock_master_daily` `LIMIT days` 조회 → 락/신선도 게이트 → `len(db_rows) ≥ min_required` 아니면 KIS `fetch_daily_candles(days)` 폴백 (`stock_master_daily.py:258-286, 636-695`).
- **VB 라이브 `k_period=15` → days=17 → DB 행 ≤17 < 22 → 항상 `_kis_fallback(reason="insufficient")`**. 결과 데이터는 KIS 일봉이라 K 계산 자체는 정상이지만, "사이클 173 DB 우선 전환"은 VB 에서 사실상 무효이고 매 prepare(하루 3~5회) 마다 후보 수(≈60) 만큼 KIS 일봉 호출이 나간다. 로그는 debug(`[prepare_db_fallback]`) 라 DB `system_logs` 에 안 남는다.
- LTV(k_period 20) → days=22, min_required 22 → DB 에 22행 있으면 DB 경로.

### 2.4 noise / K / 목표가
- `prev_idx = 1 if candles[0].date == 오늘 else 0` (부분봉 가드, `vb:267`, `ltv:266`). 16:20 저녁 prepare 는 당일 봉이 이미 적재(16:00)돼 `prev = 전일(D-1)` 이 된다 — 즉 저녁 재계산도 **D 의 목표가**를 다시 만들 뿐 D+1 목표가가 아니다.
- 일별 `noise = 1 − |close−open| / (high−low)` (range>0 인 날만), `k = mean(noise)` over `candles[prev_idx+1:]` (= prev 이전 `k_period`일) (`vb:271-287`).
- `prev_range = high_prev − low_prev`, `target_offset_base = int(prev_range × k)`; `prev_range ≤ 0` 또는 `target_offset ≤ 0` 이면 제외 (`vb:289-313`).
- 보드 시가 확정 시 `target = open + max(int(base × k_value_<board>), 0)` (`vb:798-820`). VB 라이브 = `open + int(int(range×noise)×1.3)`.
- 시가 소스: 09:00:05 `_confirm_breakout_open_prices(board="main")` 가 WS `ticker_prices[ticker]["open_price"]` 폴링 → 미확정은 KIS `fetch_stock_detail.stck_oprc` 폴백 (`scheduler.py:1596-1674`); 그 전에 틱이 오면 `check_buy_signal` 이 `open_price>0` 으로 즉시 확정 (`vb:866-869`).
- `ticker_prev_close[ticker]` = prev 종가를 prepare 가 등록 (`vb:331-334`) → LTV `min_prdy_rate` 판정 분모.

### 2.5 보드·시간창
- 보드 정의: PRE_NXT 08:00~08:59:59 / MAIN 09:00~15:39:59 / POST_NXT 15:40~19:59:59 (`session.py:62-67`). `is_tradable` = `params.tradable_boards ∩ active` (`session.py:112-121,150-155`).
- `risk.on_tick` 순서: 보유면 청산 평가(보드 무관, `risk.py:589-598`) → `is_tradable` 보드 가드(`:603`) → `registry.is_ticker_blocked_for_buy`(`:617`) → 자금 부족 사전 가드 `current_price > total_investment`(`:625`) → `check_buy_signal`(`:648`) → `execute_buy`(`:651`).
- **VB 매수 컷 15:20** `BUY_CUTOFF_KST` 모듈 상수, `check_buy_signal` 최상단·상태 무갱신 (`vb:22-30, 830-841`). 09-03·09-04 `[vb_buy_cutoff]` 발화 실측 (`[DB 09-06] system_logs`).
- **LTV 는 매수 컷이 없다** — `long_tail_volatility.py` 에 `BUY_CUTOFF` 부재, MAIN 보드가 15:39:59 까지라 15:20~15:30 장후 동시호가(시장가 접수됨, cycle229 자문 §2-1)에 신호가 나면 매수되고, 15:20 `_force_clear_main_only` 는 이미 지나가 **익일 `_execute_next_day_clear` 까지 오버나잇**. 실측 LTV 15시대 매수 1건(07-01~, `[DB 09-06]`). 19:50 에 전 전략 `buy_disabled=True` (`scheduler.py:853-856`).
- LTV PRE_NXT(08:00~09:00) 매수 허용 — 실측 08시대 매수 8건/37 (`[DB 09-06]`). 프리장 청산 평가 보류 게이트의 유일 예외 = LTV (`risk.py:79, 214-215`).

### 2.6 신호 판정 (VB `vb:822-916`, LTV `ltv:630-711`)
edge-crossing: `prev_tick < target ≤ current` 순간 1회. 보드별 첫 틱은 baseline 만 기록. 통과해야 하는 게이트(순서):
1. (VB) 15:20 컷 → 2. `state.buy_disabled` → 3. 보유/주문중/당일매도 → 4. `_cooldown_until ≥ today`(2영업일) → 5. `is_max_positions`(보유+pending ≥ max) → 6. `is_daily_loss_exceeded`(실현손익/예산 ≤ daily_loss_limit) → 7. `_targets` 등재 → 8. 활성 보드 ∈ tradable → 9. 보드 목표가 확정 → 10. (LTV) `prdy_rate = (current−prev_close)/prev_close ≥ min_prdy_rate 5%` (`ltv:675-681`) → 11. 돌파 순간 → 12. (VB 는 여기서, LTV 는 최상단에서) 계좌 SOFT 게이트(다크런치=항상 통과).

### 2.7 수량·주문
- `calc_buy_quantity = _apply_budget_limit(int(total_investment × position_ratio) // price, ...)` (`vb:1049-1060`, `ltv:785-794`). 관문: 잔여(`total_investment − 보유원금 − pending`) 클램프, 0주면 `_fallback_one_share`(잔여 ≥ 현재가면 1주), 그 뒤 ρ축 캡 `명목 ≤ 2.5 × position_ratio × 예산`, 1주도 초과면 0주 (`strategy_base.py:463-500`). 
- 주문 = `order_engine.execute_buy` 시장가(SOR → 비NXT 종목은 KRX). VB 1주 폴백 비율 91%(90일, 워크리스트 `:46`).

### 2.8 청산
**VB** (`vb:958-1047`): ① 손절 `loss_rate ≤ stop_loss_<board>`(−5%) ② `failed_breakout_exit`(OFF) ③ 익일 안전망 `NEXT_DAY_CLEAR` ④ **15:20 `_force_clear_main_only`** → `check_force_clear()` = 전 보유 (`vb:1045-1047`, `scheduler.py:1913-1976`; 15:30 이후 호출은 skip → 익일 안전망). 익절·트레일링 분기 **없음**(사이클 G 배경 그대로).
**LTV** (`ltv:713-783`): 당일 모드 = `loss_rate ≤ intraday_stop_loss`(−5%) 손절 + `prdy_rate ≥ 29%` 면 `_limit_up_reached` 등록(상한가 모드 전환) + 15:20 강제청산(상한가 모드 제외, `ltv:778-783`). 상한가 모드 = 당일 `overnight_stop_loss`(−2%) 만 / 익일: 시가 갭 `< gap_up_threshold(7%)` → 즉시 `NEXT_DAY_CLEAR`(NXT 프리 시가 30s 안정화 후), `≥ 7%` → `high_since_buy` 트레일링 −1.2%. `_limit_up_reached` 는 메모리 set(영속 없음, 워크리스트 F-5 "15:20 청산 누수").
**공통** 재진입 쿨다운 2영업일 — VB 전 청산, LTV 는 당일 모드 청산만(상한가 모드 면제) (`vb:1062-1081`, `ltv:124-150`).

---

## 3. 관찰 훅의 정확한 정의

### 3.1 사이클 C3 — 퀀트 재무 게이트 (`vb:455-557`, step 7, 배제 0)
- 대상 = step 6 통과 종목(보유 종목은 스킵). 재무 = `stock_master_financial.get_financial_series(ticker, div_cls="0"(연간), limit=2)` → `curr, prev`; 2기 미만이면 `f_score=None`.
- **F-Score-7** (`quant_score.py:32-108`, Piotroski 9 중 현금흐름 2지표 제외): ① ROA(`cptl_ntin_rate`)>0 ② ΔROA>0 ③ 부채비율(`lblt_rate`) 감소 ④ 유동비율(`crnt_rate`) 증가 ⑤ 매출총이익률(`sale_totl_rate`) 증가 ⑥ 총자산회전율(`sale_account/total_aset`) 증가 ⑦ 자본금(`cpfn`) 불변/감소. 결측 지표는 0점, prev 7필드 전부 결측이면 None.
- **마법공식** (`quant_score.py:111-195`): `EY = 1/ev_ebitda`(>0) 아니면 `bsop_prti / (시총 + total_lblt)`; `ROC = bsop_prti / ((cras − flow_lblt) + fxas)`; 각각 내림차순 랭크(None 최하위, ticker 순 tie-break), `mf_rank = ey_rank + roc_rank`(낮을수록 우량). 랭킹 모집단 = **그날 VB 후보 중 재무 2기 보유 종목**(유니버스 상대순위). 시총 = `stock_master.raw.hts_avls_eok|hts_avls`.
- 데이터 갱신: 16:40 `stock_master_financial_load` 태스크, 주1회 신선도 게이트 168h + ticker 별 `max_stac_yymm` 당분기 적재 시 skip (`scheduler.py:67`, `data_load_tasks.py:175-203`, `src/engine/CLAUDE.md:53-56`).
- `[DB 09-06]` 실측: `stock_master_financial` 6,791행 / **347 종목**, 최초 적재 07-15(291종목), **마지막 갱신 2026-08-12**(11행/1종목). 08-18 이후 VB step7 후보 171종목 중 연간 재무 보유 **111(65%)**; step7 엔트리 860 중 `f_score=None` **200(23%)**.

### 3.2 사이클 G Part B — RS / RSI (`vb:559-658`, step 8/9, 배제 0)
- 일봉 = `stock_master_daily.get_recent_daily(ticker, days=30)` DESC → ASC 종가. 지수 = **KODEX200(069500)** 일봉 30일.
- **RS** = `((S_t/S_{t−20}) − 1 − ((I_t/I_{t−20}) − 1)) × 100` %p, `period=20`, 길이 < 21 이면 None (`ta_indicators.py:55-81`). 랭킹/분위 없음, 원값 기록.
- **RSI** = Wilder 14: 첫 평균은 처음 14개 델타 단순평균, 이후 `(prev×13 + cur)/14` 평활; 전 구간 상승 100 / 하락 0 / 평탄 50 (`ta_indicators.py:19-52`). 관찰 임계 `rsi_extreme_max=85`(초과만 "극단" 라벨; 실배제 미구현).
- `[DB 09-06]` 실측(08-18~09-04, 14일): step 8/9 각 860 엔트리, null 31; RS 중앙값 **+8.1 %p**(−59.1 ~ +738.7), RSI 중앙값 **53.7**(24.8 ~ 90.3), **RSI>85 = 2건**.

### 3.3 스냅샷이 실제로 저장되는 방식 (분석 정렬에 직결)
- 저장 = `insert_snapshot` **UPSERT ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE** — `survived_tickers/counts/is_provisional` 은 덮고 **`snapshot_at` 은 안 덮는다**(DB DEFAULT now() = 그날 첫 INSERT 시각) (`src/db/strategy_funnel.py:82-87, 114-120`).
- 캡처 호출처 3곳(`scheduler.py:184-191`): (a) 09:30 `_scan_loop` 첫 진입 `is_provisional=False` (b) 16:20 저녁 루프 `True` — **7전략 prepare 재호출 뒤** 캡처 (c) 수동 트리거 `False`. 저녁 루프는 `immediate_first_run` 이라 **부팅 10분 뒤에도 한 번 돈다**(`task_loop_helper.py:63,102-107`, `data_load_tasks.py:236`).
- 그래서 하루 행 하나의 의미 = `snapshot_at` **≈ 08:02 KST**(07:52 부팅+600s 즉시 실행의 INSERT), **내용 = 그날 마지막 캡처**. 09-04 `system_logs` 실측: 캡처 09:35(F) → 16:05(F) → 16:11(T) → 16:20(T) → 18:46(F) → 18:51(T) → 19:26(F) → 19:31(T) KST(저녁 재배포 재시작들), DB 최종 행 = `snapshot_at 08:02`·`is_provisional=t`·LTV step7 **99**(16:20 prepare 로그는 64/64, 19:31 은 99/99 → 저녁 basics/마스터 갱신 뒤 유니버스가 달라진 값이 남았다).
- 함의: (i) 정상일(재시작 없음)의 최종 내용은 16:20 캡처 = **D 종가로 계산한 RS/RSI + D 저녁 기준 유니버스**이므로 "잠정→익일(D+1) 정렬"은 look-ahead 없이 맞고, `is_provisional=false` 행이 VB·LTV 에 **한 건도 없는 것**(`ALL` 전략만 39행)도 이 덮어쓰기 때문이다. (ii) 그러나 재시작이 있던 날은 마지막 캡처 시각이 제각각이고 `snapshot_at` 으로는 식별 불가. (iii) step 6(K 통과 후보) 의 저녁 값은 D 목표가 기준(§2.4) 재계산이라 "D+1 후보"가 아니다. 08-18 선행 분석의 정렬 규칙은 (i) 에 한해 타당.
- 후보 규모(`[DB 09-06]`, 08-18~09-04 최종 행): VB step6 51~79/일(중앙 ≈61), LTV step7 38~99/일.

---

## 4. 관련 이력

### 4.1 사이클 요약 (출처)
| 사이클/날짜 | 내용 | 출처 |
|---|---|---|
| 108 (06-11) | VB/LTV/BFB 유니버스 = `stock_master.list_by_filter` (volume-rank API 폐기) | `strategies/CLAUDE.md:94` |
| 140 (06-15) | VB 5 / LTV 6 funnel 단계 정의 자문 | `_workspace/domain_consult/cycle140_vb_ltv_funnel_step_definition.md` |
| 143 (06-16) | funnel hook 활성화 (커밋 ed8298b) | `docs/HARNESS_CHANGELOG.md:118` |
| 148 (06-16) | VB prepare 가격 필터 후처리(PriceFilter 단일 source, 커밋 8bba0d8) — 6종목 `bfdy_clpr>500,000` 미구독 사고 | `strategies/CLAUDE.md:110` · `_workspace/domain_consult/cycle148_vb_price_filter_in_prepare.md` |
| 156 Q0 (06-17) | `nxt_tradable=True` 강제 필터 제거(후보 풀 5.2배 확장, 커밋 69ac7e9) | `strategies/CLAUDE.md:107` |
| 157 (06-17) | 진입 차단 플래그 hook + funnel +1단계 | `strategies/CLAUDE.md:108` |
| 173 (06-22) | prepare 일봉 KIS→DB 어댑터(min_required 22 명시) | `strategies/CLAUDE.md:114` |
| 180 (06-27) | prepare 3-dict 리셋(전일 stale 타겟 매수 차단) | `docs/HARNESS_CHANGELOG.md:101` |
| 201 (07-10) | VB 재진입 쿨다운 2영업일 + **weight 0.36→0.28 DB 지혈** (커밋 3d4196a) | 커밋 본문 · `_workspace/domain_consult/cycle201_vb_weight_derisk.md` |
| 212 (07-15) | VB `position_ratio` 0.5→0.35 (DB) (커밋 4327a16) | 커밋 본문 |
| 213 (07-15) | LTV 재진입 쿨다운 | `_workspace/domain_consult/cycle213_ltv_reentry_cooldown.md` |
| C1~C3 (07-15) | 재무 5TR 적재 + F-Score-7/마법공식 + VB 관찰 훅 | `docs/HARNESS_CHANGELOG.md:82` · `src/engine/CLAUDE.md:49-66` |
| F (08-02) | TE/RR 대시보드. EC2 실측: **VB N=65 TE −0.63%, 승률 35%, RR 1.35 < 필요RR 1.83 = 정상표본 중 유일 열위** / LTV N42 +1.05% 우위 / momentum N36 +0.82% | `docs/HARNESS_CHANGELOG.md:68` · `_workspace/red/_behaviors_cycleF_te_rr_20260802.md:4` |
| G (08-02/03) | Part A 실패돌파 조기청산 default-off + Part B RS/RSI 관찰(커밋 0bf51fd). 구조 원인 진술: 익절·트레일링 부재(avg_win 캡) + 하드손절 고정 + 진입 확인이 가격 돌파 하나 | `docs/HARNESS_CHANGELOG.md:67` · `_workspace/red/_behaviors_cycleG_vb_rr_20260802.md` |
| 08-04 | kojiro 0.30→0.60 집중, **VB 0.03→0.01 / LTV 0.03→0.01**(손절 평가 유지용 극소값) | `docs/HARNESS_CHANGELOG.md:58` |
| 08-18 | 비중 단위 결함(1%→1.0 저장, Σ 2.97~2.98) 시정(커밋 dc057b6) + 17:10 KST 재설정 → VB 0.15 / LTV 0.10 | `docs/HARNESS_CHANGELOG.md:46` · `[DB] strategy_config.updated_at` · `[DB] system_logs [weight_config_anomaly] 08-18 07:26Z sum=2.9700` |
| 229 (08-28) | VB·momentum 매수 컷 15:20 (8/20~27 15:30 종가 틱 매수 9건 → APBK3013) | `_workspace/domain_consult/cycle229_vb_1530_single_price.md` |
| 233 (08-29) | 계좌 SOFT 게이트 배선(다크런치) | `strategies/CLAUDE.md:123` |
| 245 (09-04) | ρ축 명목 상한 K_ρ=2.5(LTV 000500 4.23배 랏 −11,000 발단) | 루트 CLAUDE.md 표 |
| 워크리스트 후속 | F-2 VB `position_ratio` 0.35 재검토 · F-4 LTV `pre_nxt` 제거(사용자 결정) · F-5 LTV 15:20 청산 누수 · G-9B4 VB 조기청산 백테스트 스윕 대기 · G-9B5 RS/RSI 유의성 검정 대기 | `_workspace/00_URGENT_WORKLIST.md:103-105, 280-286` |

### 4.2 VB weight 변천 (확인된 것만)
| 시점 | 값 | 근거 |
|---|---|---|
| 2026-05-15 | AI 자문 apply `applied_weight=0.48` | `[DB] parameter_recommendations` |
| 2026-07-10 이전 | 0.36 (최대 비중) | `cycle201_vb_weight_derisk.md:11` |
| 2026-07-10 | 0.36 → **0.28** ("지혈", +1개월 후 원복 재검토 조건) | 커밋 3d4196a 본문 |
| 07-10 ~ 08-04 사이 | 0.28 → 0.03 (**시점·문서 미확인** — 07-24 kojiro 0.35 확정 재분배 추정, 미검증) | `docs/HARNESS_CHANGELOG.md:58` 의 "VB 0.03→0.01" 만 확인 |
| 2026-08-04 | 0.03 → **0.01** (enabled 유지 목적 극소값) | `docs/HARNESS_CHANGELOG.md:58` |
| 08-04 ~ 08-18 | DB 에 **1.0** 으로 저장됨(단위 결함) → 엔진 배분 오염 | `docs/HARNESS_CHANGELOG.md:46` |
| 2026-08-18 17:10 KST | **0.15** (현행) | `[DB] strategy_config.updated_at` · `00_leader_trading_rules.md:39` |
| 브리프의 "0.01 → 0.15" | = 08-04 값 → 08-18 재설정. AI 자문 최근 권고 weight 0.08~0.10(08-31~09-04) 은 미적용(`applied_weight` NULL) | `[DB] parameter_recommendations` |

### 4.3 cycle201 자문 요지 (정본 = 재진단 절, `cycle201_vb_weight_derisk.md:147-264`)
- 1차 가설 "15:20 청산이 수익 절단 진범"은 트레이드 레벨 실측으로 **반증**: 15:20 청산 12건 −12,150 거의 본전(최대 승 +12,000 포함), **손실 79% 가 장중 손절**, 그중 LS ELECTRIC 4일 재진입 −26,000 = 45%.
- 근본 = 재진입 무방비 × position 0.5. 권고: 재진입 쿨다운(근본, 사이클 201 구현) / `position_ratio` 0.5→0.4 / `k_value` 1.3→1.45 는 EV 베팅이라 1주 관찰 후 / **`stop_loss` 타이트화(−5→−4) 거부(whipsaw)** / weight 0.28 은 "조건부 대증요법".
- 실제 적용: 쿨다운(코드) · weight 0.28(DB) · position 0.35(07-15) — **k 1.45 는 미적용(현행 1.3)**.

### 4.4 08-18 RS/RSI/퀀트 검정
- 브리프 요약대로(표본 1,498 관측/195종목, RS 역방향 Q1 +91.1bp > Q4 +34.7bp t=−1.73 p≈0.08, RSI>85 0건, F-Score/MF 무신호, 돌파 조건부 −41.9bp). 리포 안에 산출물 파일 **없음**(`1,498`·`Q1 약세`·`가설 반대` grep 0건; 메모리 `project_vb_observation_hooks_verdict.md` 만 존재).

### 4.5 cycle229 자문 요지 (`cycle229_vb_1530_single_price.md`)
15:20~15:30 은 연속매매가 아니라 KRX 장후 동시호가(틱 희박) → 15:30 랜덤엔드 확정 종가 1틱이 허위 edge-crossing(8/27 에코프로 92,000 ≥ 목표 90,050 = +2.17%) → 컷 15:20 권고, momentum 도 동일. LTV 는 대상 밖.

---

## 5. 백테스트 — 인용 가능한 근거가 사실상 없다
- 엔진은 외부 MCP 에 `yaml_content/symbols/start_date/end_date/initial_capital(10,000,000)` 만 보낸다. **`commission_rate/tax_rate/slippage` 는 docstring 에만 있고 인자로 전달하지 않는다**(서버 기본값, 값 불명) (`backtest_engine.py:23-28, 155-164`).
- 기본 유니버스 = 코스피 대표 5종목(005930/000660/035420/005380/051910) (`backtest_engine.py:51-57`).
- VB YAML 근사 = `close cross_above maximum(high, period=1)`(전일 고가 상향 돌파) + ATR(k_period) 지표 첨부 + `stop_loss.percent`; K×Range·보드·15:20 청산은 표현 불가 (`backtest_yaml.py:204-260`). **LTV 는 `BacktestNotSupportedError`**(`backtest_yaml.py:110-113`).
- `[DB 09-06] backtest_runs`: VB `completed` **108건 전부 `total_trades=0`**(05-18~08-14, metrics 전부 0.0) / `failed` 35건(08-14 이후 `MCP 서버에 연결할 수 없습니다`, 09-02~04 포함) / LTV **146건 전부 `skipped`("YAML DSL 미지원")**. 즉 VB·LTV 백테스트 수치는 존재하지 않는다.
- AI 자문 최근 VB 권고(09-04): weight 0.10, `k_period 20, position_ratio 0.25, stop −4.0, daily_loss −5.0, k 1.5` — 미적용.

---

## 6. "단순 K 돌파 의존" 우려 대비 — 현재 코드가 거는 것 / 안 거는 것

| 구분 | 거는 것 (라이브 실효) | 출처 |
|---|---|---|
| 유니버스 | 시총 ≥500억 · 거래대금(전일) ≥500억(VB)/200억(LTV) · 상위 100종목 cap · 6자리 숫자 · ETF 명 제외 · 가격 3,000~500,000 · 진입 차단 플래그 11건(거래정지/정리매매/관리/공매도과열/이상급등/시장경고 02↑/투자주의환기/단기과열/임시정지) · (LTV) 2일 연속 +25% 시가대비 제외 | §2.2 |
| 변동성 정의 | 15일(VB)/20일(LTV) 노이즈 평균 × 전일 Range × 보드 K(1.3/1.0) | §2.4 |
| 신호 형식 | 시가 확정 후 edge-crossing 1회(추격 매수 아님, 이미 목표가 위에서 시작한 종목은 첫 틱 baseline 이 target 이상이면 영영 미발화) | `vb:879-886` |
| (LTV) 모멘텀 조건 | 전일 종가 대비 +5% 이상일 때만 | `ltv:675-681` |
| 시간창 | VB 09:00~15:20(컷) · LTV 08:00~15:39:59 | §2.5 |
| 포지션/자금 | max_positions 2/4 · position_ratio 0.35/0.2 · 예산 잔여 클램프 · ρ캡 2.5× · daily_loss_limit −7% · 재진입 쿨다운 2영업일 · 전략 간 동일 종목 차단(`is_ticker_blocked_for_buy`) | §2.6-2.7 |
| 청산 | VB −5% 하드손절 + 15:20 전량 · LTV −5% / 상한가 모드 −2%·갭 7%·트레일링 −1.2% | §2.8 |

| 구분 | 안 거는 것 (코드에 없거나 OFF) | 출처 |
|---|---|---|
| 거래량 확인 | 돌파 시점 체결량/거래대금 게이트 없음(BFB/VCP 의 `tick_volume` 게이트는 VB/LTV 미배선) | `vb:822-916` 에 acml_vol 참조 0 |
| 추세/상대강도 | RS·RSI·F-Score·마법공식 전부 **관찰만**(플래그 False, True 여도 실배제 미구현) | `vb:455-658` |
| 추격 상한 | 돌파 후 현재가가 목표가를 얼마나 넘었든 상한 없음(BFB 5%/VCP 7.5% 같은 `max_breakout_extension_pct` 없음) | `strategies/CLAUDE.md:19-21` 대비 |
| 갭 필터 | 시가 갭업/갭다운 스킵 없음(donchian/kojiro 는 있음) | `strategies/CLAUDE.md:36,39` 대비 |
| 익절·트레일링 (VB) | 없음 — 승자는 15:20 까지 방치, 실패 돌파 조기청산은 default-off | `vb:958-1043` |
| 시장 레짐 | 매수 차단 없음(사이클 I 이후 관찰 전용) | `risk.py:611-614` |
| 15:20 컷 (LTV) | 없음 — 장후 동시호가 매수 → 오버나잇 경로 열림 | §2.5 |
| 백테스트 검증 | VB total_trades 0 / LTV 미지원 | §5 |

---

## 7. 실측 손익 (`[DB 09-06] trade_history`, SELL·COMPLETED/PARTIAL, gross)

| 기간 | 전략 | N | 승/패/보합 | 승률 | 평균수익 | 평균손실 | RR(₩) | 최대승/최대패 | 합계 |
|---|---|---|---|---|---|---|---|---|---|
| 07-01~ | VB | 64 | 28/35/1 | 43.8% | +2,438 | −4,337 | 0.56 | +9,400 / −16,000 | **−83,540** |
| 07-01~ | LTV | 37 | 15/22/0 | 40.5% | +3,180 | −3,942 | 0.81 | +29,100 / −11,200 | **−39,025** |
| 08-18~ | VB | 36 | 17/18/1 | 47.2% | +2,679 | −4,722 | 0.57 | | −39,450 |
| 08-18~ | LTV | 17 | 5/12/0 | 29.4% | +1,720 | −3,402 | 0.51 | | −32,225 |

- 매도 시각(07-01~): VB **15시대 48/64**(−37,400) · 09시대 10(−25,400) · 10시대 1(−16,000). LTV 15시대 24/37(−2,650) · 09시대 8(−3,225) · 08시대 1(−11,200).
- 매수 시각: VB 09시대 44/63(70%) · 10시대 11 · 15시대 6. LTV 08시대 8 · 09시대 15 · 10시대 4 · 13시대 4 · 14시대 3 · 15시대 1.
- 08-18 이후 매수 빈도: VB 36건/14영업일/22종목, LTV 17건/11일/15종목.
- 사이클 F(08-02) 대비: 승률 35%→43.8%(누적), RR 1.35(% 기준·페어링)와 위 0.56(₩ 기준·단순) 은 정의가 달라 직접 비교 불가.

---

## 8. 주의·불일치 목록 (보고서가 그대로 쓰면 틀리는 것)
1. LTV 손절 "−3%/−5%" 는 코드 기본값·문서 값이고 라이브는 **−5%/−2%** (§0).
2. LTV "3보드" 는 코드 기본값, 라이브 **2보드(main, pre_nxt)**. 워크리스트 F-4 는 `pre_nxt` 추가 제거를 사용자 결정으로 남겨둠.
3. VB `k_period=15` 가 어댑터 `min_required=22` 와 어긋나 **VB 일봉은 항상 KIS 폴백** (§2.3) — 행위 결함은 아니나 "DB 일봉 전환" 서술은 VB 에 해당하지 않는다.
4. `strategy_funnel_snapshots` 의 `snapshot_at`(08:02) 은 캡처 시각이 아니다(§3.3). VB·LTV 에 `is_provisional=false` 행은 0건.
5. 진입 차단 "13건" 라벨 ≠ 실효 11건 (§2.2).
6. `stock_master_financial` 은 08-12 이후 갱신 0, 347종목 — 퀀트 스코어 결측 23%.
7. 백테스트 수치 인용 불가 (§5). 비용 인자(수수료·세금·슬리피지)는 시스템이 전달하지 않는다.
8. VB weight 0.28→0.03 구간의 결정 문서는 이번 검색(changelog·worklist·reports·ai_advisory_review·memory) 에서 찾지 못했다.
9. 08-18 RS/RSI 검정 산출물 파일은 리포에 없다(메모리 기록만).

---

## 9. 읽은 출처
- 코드: `src/engine/strategies/volatility_breakout.py`(1,081L 전체) · `long_tail_volatility.py`(794L 전체) · `src/engine/strategy_base.py:338-500, 1237-1268, 1493-1580` · `src/engine/quant_score.py`, `ta_indicators.py`(전체) · `src/engine/scanner.py:136-205, 321-421, 2652-2716` · `src/engine/risk.py:79, 205-229, 442-653` · `src/engine/scheduler.py:56-69, 184-288, 718-750, 822-860, 1596-1674, 1913-1976, 2489-2532, 2988-3050, 3373-3390` · `src/engine/session.py:32-83, 95-187` · `src/engine/data_load_tasks.py:175-237` · `src/engine/task_loop_helper.py:44-128` · `src/db/stock_master.py:512-552` · `src/db/stock_master_daily.py:258-286, 609-695` · `src/db/strategy_funnel.py:42-140` · `src/engine/backtest_engine.py:1-80, 145-170` · `src/engine/backtest_yaml.py:32-115, 204-260`
- 문서: `src/engine/strategies/CLAUDE.md`(VB/LTV 행·34-35·48-49·93-131) · `src/engine/CLAUDE.md:31-70` · `src/db/CLAUDE.md:175-185` · `docs/HARNESS_CHANGELOG.md:46,58,67,68,82,101,118` · `_workspace/red/_behaviors_cycleF_te_rr_20260802.md`, `_behaviors_cycleG_vb_rr_20260802.md` · `_workspace/domain_consult/cycle140_*`, `cycle148_*`, `cycle201_vb_weight_derisk.md`, `cycle213_*`, `cycle229_vb_1530_single_price.md` · `_workspace/00_URGENT_WORKLIST.md` · `_workspace/00_leader_trading_rules.md:39,57-63` · git log/커밋 본문 dc057b6·4327a16·3d4196a·6e73958
- DB(SELECT 만, 2026-09-06 08:1x KST): `strategy_config` · `system_config` · `strategy_funnel_snapshots` · `stock_master_financial` · `backtest_runs` · `trade_history` · `parameter_recommendations` · `system_logs` · `information_schema.columns`
- 스크래치: `scratchpad/vbreview/q2.sql`, `q3.sql`(실행한 SELECT 원문), `changelog_rows_F_G_C3_0818.txt`
