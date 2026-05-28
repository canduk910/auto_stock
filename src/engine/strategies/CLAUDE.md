# CLAUDE.md — src/engine/strategies/

`StrategyBase` 서브클래스 6개. 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`.

## 전략 카탈로그

| ID | 핵심 동작 | 손절·청산 | tradable_boards / exchange |
|----|----------|----------|---------------------------|
| `momentum` | 전일종가 +29% 돌파 (상한가 30% 제외, 돌파 순간만) | -7.5% / 익일 청산: 갭+10%↑ → 트레일링 -2% / 그 외 즉시 매도 | KRX_OPEN+MAIN / KRX·NXT·SOR (실전 SOR 권장, 모의는 KRX 강제) |
| `volatility_breakout` | 보드별 시가 + (전일Range × 보드별 K) 돌파. `_targets[ticker].boards[board]` 보드 분리 저장. `_open_confirmed[ticker]` / `_prev_price[ticker]` 도 `{board: ...}` dict | **보드별 손절**: `stop_loss_main` 우선 → 부재 시 `stop_loss_rate` top-level fallback. (`stop_loss_pre_nxt` 키는 DB 호환 보존, PRE_NXT 제거로 적용 안 됨). `_get_stop_loss_for_board(params, board)` 헬퍼 + `_resolve_active_board()` 활성 보드 조회. **15:20 KRX 메인 일괄 청산** (OVERNIGHT 거부) | **MAIN 단독** (사이클 26: PRE_NXT + POST_NXT 제거, KRX ONLY) / `k_value_krx_main` / `k_value_nxt_pre` (`k_value_nxt_post` 키 호환 보존만) |
| `long_tail_volatility` | VB 방식 + 전일대비 `min_prdy_rate%`↑. `_limit_up_reached` set으로 모드 관리 | 당일 모드 -3% / 상한가 모드 -5% + 익일 갭/트레일링. **15:20 상한가 미도달 일괄 청산** / 상한가 모드는 익일 NXT 프리 청산 + POST_NXT 손절 모니터링. `_next_day_clear_pending` 가드 | **PRE_NXT + MAIN + POST_NXT 3보드** (사이클 38, 2026-05-22 사용자 의도 복원 — 연속 상한가 익일 청산 + 야간 매수. 사이클 26 KRX ONLY 정책 폐기). 매수 진입 전용 — 보유 손절/Trailing/익일청산은 보드 가드 무관 항상 작동 |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스 → 시총 컷 → 60일 일봉 → 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5×. `prepare` 부분봉 가드(`candles[0]==오늘`이면 [1] 부터). 09:05~09:30 매수, 갭 +3%↑ 스킵, 1회만 | ATR(14)×2 Chandelier 트레일링 + -7% 하드. **시간·15:20 청산 없음** — 멀티데이 보유 (DB positions 영속화) | MAIN |
| `bull_flag_breakout` | KRX 등락률 순위 → 시총 ≥ 500억 + 거래대금 ≥ 20억 컷 → 30일 일봉 → **폴 자동 검출**(3~10영업일 누적 +20%↑, 음봉 ≤ 30%) + **플래그 자동 검출**(3~10영업일, 조정 폭 ≤ 폴 폭의 38.2%, 거래량 < 폴 평균 × 60%). 09:05~13:00 **`flag_high` 돌파 순간** + 당일 거래량 ≥ `flag_avg_volume × 2`. `_bought_today` 1회 가드 + `_cooldown_until[ticker]=date` 3영업일 쿨다운 | -5% 손절 / **`flag_low` 이탈 → STOP_LOSS** / **측정된 이동 도달 → TRAILING_STOP**(타겟가 `flag_high + (pole_high - pole_start)`, 1차 구현 전량 청산) / 잔여 `high_since_buy - ATR×2` 트레일링 / 5영업일 시간 청산 (캘린더일 +2 보정) | MAIN / KRX |
| `vcp_breakout` | **미네르비니식 VCP**. 코스피200+코스닥150 → 시총 ≥ 1,000억 → 220일 일봉 → **추세 필터**(50/150/200 EMA 정렬 + 200EMA 1개월 우상향) → **베이스 자동 검출**(25~75영업일, 깊이 ≤ 25%) → **pullback 점진 수축**(swing high→low→high, 2~4회, 직전 대비 폭 감소, 마지막 ≤ 8%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%). 09:05~14:30 **`base_high` 돌파 순간** + 당일 거래량 ≥ 20일 평균 × 1.5. `_bought_today` + `_cooldown_until` 7영업일. **`Position._MULTIDAY_STRATEGIES` 멤버** → `is_next_day` 항상 False | -7% 손절 / **`base_low` 이탈 → STOP_LOSS** / `high_since_buy - ATR×2` 트레일링 / **50일 EMA 이탈 → TRAILING_STOP**. **시간·15:20 청산 없음** — donchian 컨벤션, 멀티데이 보유 | MAIN / KRX |

## 공통 패턴

- `prepare()` 단계별 통과 카운트는 `_scan_stats` 누적 → `get_scan_stats()` → `strategies.<id>.scan_stats` 로 프론트 ScanMonitor 깔때기
- **사이클 21 (2026-05-20) — VB/LTV/momentum 도 깔때기 노출**:
  - VB: `_empty_scan_stats()` 9 키 (`universe_candidates / universe_filtered / price_filtered / mcap_pass / trade_amount_pass / candle_fetch_ok / k_value_computed / final_prepared / last_run_at`)
  - LTV: VB 9 키 + `consecutive_limit_pass` (10 키 — 연속상한가 N일 제외 통과)
  - momentum: prepare 없음 → `scanner.scan_filter_stats` 모듈 전역 dict 7 키 (`universe_candidates / rate_pass / mcap_pass / trade_amount_pass / limit_up_excluded / final_prepared / last_run_at`). `MomentumStrategy.get_scan_stats()` 는 모듈 dict 사본 반환
  - scan_stocks() 가 등락률 30%+ (상한가) 도 명시 분기 — `limit_up_excluded` 카운트 + 구독 후보 풀에서 제거 (`check_buy_signal` 의 30% 가드와 이중 안전망)
- VB/LTV `_scan_universe`: 거래량순위 API(`FHPST01710000`) 응답 1건으로 후보 + 시총·전일거래대금 산출(`prdy_vol × (stck_prpr - prdy_vrss)`로 시간 의존 제거)
- **BFB `_scan_universe` 시간무관화** (사이클 48, 2026-05-27 — 0건 매매 결함 전면 시정): 사이클 33 의 `acml_vol`(당일 누적) 방식은 BFB `prepare()` 가 07:50 장 전 boot 에서만 호출 → `acml_vol=0` → **매일 "유니버스 0종목"** (운영 DB 확정). VB/LTV 와 동일하게 `volume-rank`(FHPST01710000, blng 0/1/3 합집합)로 소스 교체 — 응답 1건에 `prdy_vol`/`stck_prpr`/`prdy_vrss`/`lstn_stcn` 포함 → 개별 `fetch_stock_detail` 호출 없이 `trade_amt = prdy_vol × (stck_prpr - prdy_vrss)` 산출 + 시간 의존 제거. 전일 확정치 필수 (당일 acml 금지 — 오후 편중 왜곡). `min_trade_amount_failed` scan_stats 유지
- **BFB Pole 임계 완화** (사이클 48): `pole_min_return` 20.0→15.0 / `pole_max_red_ratio` 0.30→0.45. 한국 ±30% 환경에서 +20% + 음봉 30% 교집합 0 차단. flag_retracement 0.382 / 거래량 2배 컷 유지
- **VCP 추세필터 EMA 하향** (사이클 48): KIS 100일 한도로 `effective_ema_long` 이 200EMA 를 ~75 로 축소 + `ema_mid(150)>75` 재축소 → 50/65/75 정배열 항상 0 (추세필터 0건 결함). `ema_long` 200→**120** / `ema_mid` 150→**60** → 100일 내 50/60/120 안정 계산. `last_pullback_max` 0.08→**0.12** 완화. `effective_ema_long = min(ema_long, available_len - uptrend_days - 5)` 자동 축소 가드 + `_check_trend_filter(candles, effective_ema_long=)` 시그니처는 안전망으로 유지. 분할 fetch 인프라는 운영 1주 후 별도 검토
- **BFB/VCP 장중 재prepare 안전망** (사이클 48): `scheduler._reprepare_breakout_if_empty` 대상에 `bull_flag_breakout`/`vcp_breakout` 추가 (기존 VB/LTV 에 더해). boot 실패/일시 API 오류 회복용 — 주 메커니즘은 prdy 시간무관 유니버스. 후보 비었을 때만 호출 (전략당 5분 1회, rate limit 부담 미미)
- VB/LTV/donchian/bull_flag/vcp 모두 `prev_idx` 분기 동일: `candles[0].stck_bsop_date == 오늘`이면 candles[1] 을 전일로 사용
- 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- 1주 폴백 (모든 전략): `StrategyBase._fallback_one_share(current_price)` 잔여 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`
- **사이클 39+41 (2026-05-22) — funnel 단계별 자동 hook**: BFB/VCP/donchian `prepare()` 가 `StrategyBase._record_funnel_step(step_no, step_name, survived, excluded=None, *, step_conditions=None)` 호출로 8단계 통과/탈락 종목 캡처. **사이클 41**: `survived: list[str \| dict]` (자동 dict 변환 — `_resolve_ticker_name` 종목명 lookup) + `excluded: list[{ticker, name, reason}]` (수치 포함 사유 — "음봉 비율 35% > 30%" / "마지막 폭 12% > 8%" / "신고가 미달 52000 < 55000" 등) + `step_conditions` (UI 단계 조건 툴팁용). cap 200/20 자동 적용. 9:30 `_scan_loop` 첫 진입 시 `scheduler._auto_capture_funnel_snapshots` 자동 발화 → DB `strategy_funnel_snapshots` 단계별 INSERT. `_reset_daily_state` 동행 reset

## 멀티데이 보유 전략

`Position._MULTIDAY_STRATEGIES = frozenset({donchian_swing, vcp_breakout})` — `is_next_day` 항상 False, OrderMonitor "청산" 배지 미표시. 추가 시 frozenset 멤버만, `Position` 시그니처 변경 금지.

## 안전 규칙

- **VB/LTV/BFB/VCP 후보 WebSocket 구독 우선순위** — `subscribe_filtered_stocks(priority_groups=...)` 의 `breakout` 그룹: LOW+bypass_limit=False (보조 세션 분산). **사이클 48 (2026-05-27)**: `scheduler._collect_breakout_tickers()` 가 4 돌파 전략(VB/LTV + bull_flag_breakout/vcp_breakout)을 순회 → BFB/VCP 후보도 동일 `breakout` LOW 그룹으로 편입. BFB/VCP 는 폴링 루프 없이 `risk.on_tick` 으로만 매수 평가하므로 이 구독 없이는 0건 지속(PR #15 P1). `_resubscribe_stale_priority` 의 stale 재구독도 positions/next_day_clear 소속이 아닌 후보는 LOW (사이클 25-B, 2026-05-20). 후보 HIGH 메인 집중 → 메인 과부하 → silent inactive 방지
- **VB `DEFAULT_TRADABLE_BOARDS` = ("main",) 유지 (사이클 26)** — KRX ONLY 정책. PRE_NXT 복구 금지 (NXT 갭상승 위험 + SK하이닉스 시가 결함). POST_NXT 추가 금지 (VB OVERNIGHT 보유 결함). DB `strategy_config.params.tradable_boards` 도 함께 갱신
- **LTV `DEFAULT_TRADABLE_BOARDS` = ("pre_nxt", "main", "post_nxt") 복원 (사이클 38, 2026-05-22)** — 사용자 운영 의도 복원. 연속 상한가 종목 익일 청산 모드 + 야간 매수. 사이클 26 KRX ONLY 정책 폐기. DB `strategy_config` 는 운영 중 보존된 3 보드 유지
- **`tradable_boards` 는 매수 진입 전용 (사이클 38 명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동. `risk.on_tick` 의 `check_exit_signal` 분기가 `session_tracker.is_tradable` 검사 *전* 진입 보장. 6 전략 공통 적용
- **VB 익일 청산 안전망** — `_execute_next_day_clear` 대상 포함. 비상 상황(시세 미수신, 시장가 거부, 재시작 race) 회복용
- **donchian_swing 일중 시세 REST 폴링 (`_swing_rest_poll_loop`) 제거 금지** — 09:30~15:20 KRX 메인 시간대 60s 주기로 보유+스캔 합집합 폴링 → ticker_prices 갱신 + 보유 손절 평가 재사용. WebSocket stale 보강
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)

## 사이클 23 파라미터 확장 (2026-05-20)

### BFB `breakout_retention_minutes` (P2-1)
- 기본 3분. 첫 돌파 감지 → `_breakout_first_seen[ticker]=now` 등록 + NONE. 경과 후 BUY 발사.
- 가격 후퇴 시 dict pop. `_reset_daily_state()` 에서 clear.
- `DEFAULT_PARAMS["breakout_retention_minutes"]=3`. `PARAM_RANGES["breakout_retention_minutes"]=(1,30)`. `INT_PARAMS` 등록.
- 기존 동작 회귀: `retention_minutes=0` 이면 즉시 BUY (기존 테스트 픽스처 활용).

### BFB `min_trade_amount_failed` scan_stats (P1-2)
- `_empty_scan_stats()` 키 추가. `_scan_universe`에서 시총 통과 + 거래대금 미달 시 증가.

### VCP `mcap_pass` scan_stats (P1-3)
- `_empty_scan_stats()` 키 추가. `_scan_universe`에서 시총 통과 시 증가.

### donchian `breakout_fail_n_days` (P2-2)
- 기본 5일. `check_exit_signal` 에서 보유 N일 + 현재가 < `_breakout_high[ticker]` → STOP_LOSS.
- `_breakout_high`: 매수 신호 발사 시 donchian_high 등록. graceful skip (0이면 분기 진입 안 함).
- 기존 ATR 트레일링/하드 손절 보존, 추가 분기만.

### donchian `max_breakout_extension_pct` (P2-3)
- 기본 3.0%. `check_buy_signal` 갭 스킵 *후*, BUY 확정 *전* 삽입.
- `daily_high = max(stck_hgpr, high_price, current_price, open_price)`. 초과 시 NONE.
- 기존 `gap_skip_threshold` 와 별개 (시가 갭 vs 당일 고가 추격).

### donchian `box_contraction_period` + `max_box_volatility_pct` (P2-4)
- 기본 10일, 5.0%. `prepare()` ATR 통과 후 박스 수축 필터.
- 직전 N일 (high.max - low.min) / close.mean × 100 > max_box_volatility_pct → skip.
- `_scan_stats["box_contraction_pass"]` 키 추가.

### VCP PARAM_RANGES 화이트리스트 (P1-1)
- `base_depth_pct(0.10,0.50)` / `volume_contraction_ratio(0.30,1.00)` / `breakout_volume_mult(1.0,5.0)` / `last_pullback_max(0.03,0.15)` 추가.
- P2 신규 5 키도 PARAM_RANGES/INT_PARAMS 동시 등록.

## 새 전략 추가
1. 본 디렉토리에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `scheduler.py` `__init__` 에 `registry.register()` 추가
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. 본 표 + `_workspace/00_leader_trading_rules.md` 에 명세 추가
