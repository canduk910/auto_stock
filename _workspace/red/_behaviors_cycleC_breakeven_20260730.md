# 사이클 C — VCP/BFB 브레이크이븐 승격 (default-off) 행위 분해 (team-leader, 2026-07-30)

자문: `_workspace/domain_consult/cycle_breakeven_promotion_rollout.md` (채택: VCP 1.5N + BFB 1.5N default-off + 래치 필수 + kojiro 보류(A) + 2단계 ratchet 기각)
사용자 결정: kojiro=A 보류 / VCP·BFB 지금 착수 + **default-off 배포** (donchian D+1 실측 게이트 통과 후 DB 토글 활성)

## 공통 설계 (donchian P1-A 와의 차이)
- donchian 은 entry_atr *스냅샷* + 단조증가 high_since_buy 라 조건이 자연 래치. **VCP/BFB 는 live ATR 사용 → ATR 팽창 시 un-latch 병리 → boolean 래치 필수**: `_breakeven_latched: set[str]` — `high_since_buy >= buy_price + N×ATR` 최초 관측 시 add, 이후 ATR 변동 무관 유지.
- DEFAULT_PARAMS `breakeven_promote_atr = 0.0` (**0 = 비활성이 기본** — 사용자 결정 default-off). 활성값 1.5 는 게이트 후 strategy_config DB 로 주입. PARAM_RANGES/INT_PARAMS 편입 금지 (청산 정체성 상수).
- 승격 효과: 래치된 ticker 는 % 하드손절 임계가 `max(기존 손절선, buy_price)` 로 승격 (tighten-only) — 현재가 ≤ buy_price 도달 시 STOP_LOSS. 손절선을 넓히는 방향 절대 금지.
- `on_position_closed(ticker)` 에서 래치 정리 (재진입 stale 차단). 멀티데이 상태 — 일일 리셋 금지.

## 행위 — VCP (`src/engine/strategies/vcp_breakout.py`)
- **C-V1 (래치)**: `breakeven_promote_atr>0` + 보유 중 `high_since_buy >= buy + N×ATR` 관측 → `_breakeven_latched.add(ticker)`. 이후 ATR 이 팽창해 조건이 거짓이 돼도 래치 유지.
- **C-V2 (승격 발화)**: 래치된 ticker 현재가 ≤ buy_price → STOP_LOSS (기존 -7% 손절·base_low 이탈보다 먼저 평가돼도 무방 — 전부 STOP_LOSS 계열, 로그 prefix `[vcp_breakeven_promote]`).
- **C-V3 (default-off 회귀 0)**: `breakeven_promote_atr=0.0`(기본) 이면 래치/승격 분기 완전 무발화 — 기존 청산 스택(−7%/base_low/2ATR 샹들리에/50일 EMA) byte 동일.
- **C-V4 (recompute_high_since_buy 이식)**: donchian `recompute_high_since_buy` 패턴(매수일~전영업일 일봉 high max 보정, 초과 시에만 갱신 + DB UPDATE + 로그)을 VCP 에 이식 — 재시작 시 high_since_buy 동결로 래치 미형성되는 결함 예방. 기존 fetch 하는 candles 재사용, on_tick KIS 호출 금지.
- **C-V5 (정리)**: on_position_closed 래치 discard.

## 행위 — BFB (`src/engine/strategies/bull_flag_breakout.py`)
- **C-B1~C-B3**: C-V1~C-V3 동형 (N=1.5 동일, 로그 prefix `[bfb_breakeven_promote]`). 측정된 이동 타겟/flag_low/5영업일 시간청산 기존 스택 byte 동일 보존.
- **C-B4 (정리)**: on_position_closed 래치 discard (기존 `_partial_exit`/cooldown 정리 옆 동행).
- recompute_high_since_buy 이식은 **범위 외** (자문 — 5영업일 한도라 한계효용 낮음, 후순위).

## 매매 안전성 diff 0 의무
`src/realtime/` `src/auth/` `src/api/order.py` `src/engine/risk.py` `src/engine/order_engine.py` — diff 0. 두 전략 파일 + 테스트만. 매수 경로(check_buy_signal/prepare 필터) 무변경.

## 게이트 (배포 후 활성화 조건 — 운영 절차)
donchian 실측에서: `[donchian_breakeven_promote]` 발화 + whipsaw(본전 스탑아웃 후 재상승 반복) 부재 + high_since_buy 보정 온전 → strategy_config.vcp_breakout.params.breakeven_promote_atr=1.5 DB 주입 (BFB 는 그 후 재평가). NO-GO 신호 시 1.5→2.0 상향 후 재평가.
