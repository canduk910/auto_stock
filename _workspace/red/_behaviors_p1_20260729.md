# P1 결함 2건 — 행위 분해 (team-leader, 2026-07-29)

자문: `_workspace/domain_consult/cycle_weekly_review_20260729.md`

## 사이클 A — donchian 청산 상태 견고성 + 레이어드 청산 (`src/engine/strategies/donchian_swing.py`)

### 근본 원인 (team-leader 코드 진단 확정)
- `check_exit_signal` L995-1006: 트레일링 ATR = `self._candidates.get(ticker)["atr"]`. `_candidates` 는 매일 prepare 가 새 20일 신고가 후보로 재구성 → 보유 종목이 후보 이탈하면 `info=None` → `atr=0` → 트레일링 분기 영구 침묵. 하드손절만 `_entry_atr` 폴백 보유(L961-973) → 관측된 "백스톱만 발화"와 정확히 일치 (096770/017670 실증).
- 시간 기반 청산(L984)의 `_breakout_high` 도 인메모리 매수시점 등록 — 재시작/후보 이탈 후 소실 가능성 조사 필요 (011200 은 발화했으므로 재도출 경로 존재 여부 확인 후 갭만 보강).

### 행위
- **A-1 (버그픽스, HIGH)**: 보유 종목 트레일링 ATR 은 `_candidates` miss 시 `_entry_atr[ticker]` (recompute_held_atr 재도출 포함) 폴백으로 평가된다. `_candidates`/`_entry_atr` 모두 miss 면 기존과 동일 skip (fail-open 금지 아님 — 트레일링은 이익보호라 skip 허용, 백스톱이 최후 방어).
- **A-2 (버그픽스)**: `_breakout_high` 가 재시작 후 보유 종목에 대해 재도출된다 (매수일 이전 20일 신고가; 기존 recompute 훅(boot recompute_held_atr / recompute_high_since_buy 경로) 동승). 이미 커버라면 회귀 가드만 추가.
- **A-3 (신규, 자문 채택)**: 브레이크이븐 승격 — `high_since_buy ≥ buy_price + 1.5×entry_atr` 도달 시 하드손절선이 `max(기존 손절선, buy_price)` 로 승격 (tighten-only, entry_atr 존재 시에만). DEFAULT_PARAMS `breakeven_promote_atr=1.5` (PARAM_RANGES 미편입 — 전략 정체성 상수).
- **A-4 (신규, 자문 채택)**: 10일 저가 채널 청산 — 현재가 < 최근 10영업일 최저가(당일 제외, 보유 중에만) → TRAILING_STOP. DEFAULT_PARAMS `channel_exit_period=10` (0=비활성, 기본 10, PARAM_RANGES 미편입). 데이터 소스는 prepare/recompute 시점 일봉 (stock_master_daily 어댑터) — on_tick 시점 KIS 호출 금지 (hot path).
- **A-5 (회귀 0)**: 기존 발화 케이스 보존 — 백스톱(-9%)·터틀 2ATR 하드손절·시간 기반 청산(011200 시나리오)·position_ratio 매수(-7% byte 동일) 전부 무변경.
- **A-6 (자문 검증 시리즈)**: 096770 실데이터 근사 시나리오(매수 117,300 → 고점 135,800 → 하락)에서 트레일링/채널 청산이 백스톱 이전에 발화 = 승자 전환. 017670 시나리오 손익분기 이상.

### 우선순위 명세 (발화 순서)
하드손절(2ATR/승격 후 브레이크이븐) → 백스톱(-9%) → 시간 기반 청산 → 10일 채널 청산 → ATR 트레일링. STOP_LOSS 계열이 TRAILING 계열보다 선행 (기존 순서 보존, 신규 분기는 기존 분기 뒤 삽입).

## 사이클 B — 체결통보 중복 수신 race (`src/engine/order_engine.py`)

### 근본 원인 (07-27 377450 실사고)
- `_handle_buy_fill` 전량 체결 완료 시 `_order_strategy.pop(order_no)` (L1101). 동일 order_no 2차 체결통보 도착 → 매핑 miss → `_lookup_strategy_from_trade_history` 는 PENDING row 탐색인데 이미 COMPLETED → miss → `"momentum"` 하드코딩 폴백(L974) → `registry.get("momentum")` (비활성이어도 등록돼 있음) → `state.positions[ticker]` 신규 등록 + DB positions PK(ticker) 덮어쓰기 → 원래 kojiro 포지션이 비활성 momentum 명의로 실명 → 손절/익일청산 완전 사각.

### 행위
- **B-1 (멱등 가드, HIGH)**: 전량 체결 처리 완료된 order_no 의 후속 체결통보는 무시된다 — positions/trade_history/pending 매핑 무변경 + `[buy_fill_duplicate_ignored]` INFO 1행. 멱등 상태는 전량 체결 완료 시점에 동기 등록 (`_reset_daily_state` 동행 clear, 무한 성장 금지).
- **B-2 (폴백 안전, HIGH)**: 매핑 miss 폴백 경로에서 ticker 가 이미 어느 전략 포지션(registry 전체)에 존재하면 신규 등록/덮어쓰기 대신 `[buy_fill_fallback_held_conflict]` ERROR 1행 + skip (기존 포지션 보존).
- **B-3 (가시화)**: 그럼에도 momentum 폴백으로 신규 포지션이 등록되는 경우(B-1/B-2 미해당 진짜 고아 체결) `system_logs` CRITICAL 1행 — 운영자 즉시 인지 (fire-and-forget, hot path 블로킹 0).
- **B-4 (회귀 0)**: 부분 체결 → 잔여 체결 정상 흐름(같은 order_no 복수 통보가 합법인 경우: total_filled < ordered_qty 동안) 무변경. 멱등 가드는 "전량 체결 완료 후" 통보에만 적용.
- **B-5 (회귀 0)**: `_completed_orders` 보정 INSERT race 가드(사이클 30)·사이클 147 lookup 폴백·사이클 161 price 정합·매도 `_handle_sell_fill` 전부 무변경.

## 매매 안전성 diff 0 의무 영역
`src/realtime/` `src/auth/` `src/api/order.py` `src/engine/risk.py` — diff 0. order_engine 은 `_handle_buy_fill` 영역 한정 (매도 본류 무변경). donchian 은 `check_exit_signal`/prepare-recompute 영역 한정 (매수 경로 무변경).
