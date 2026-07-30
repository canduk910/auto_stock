# 사이클 C Red 로그 — VCP/BFB 브레이크이븐 승격 (default-off + live-ATR 래치)

- 작성: tdd-engineer, 2026-07-30
- 명세: `_workspace/red/_behaviors_cycleC_breakeven_20260730.md`
- 자문: `_workspace/domain_consult/cycle_breakeven_promotion_rollout.md`
- 선례: `src/engine/strategies/donchian_swing.py` P1-A (`test_p1a_donchian_layered_exit.py`)

## 산출 파일

- `tests/unit/engine/strategies/test_cycleC_vcp_breakeven.py` (C-V1~C-V5, 13 케이스)
- `tests/unit/engine/strategies/test_cycleC_bfb_breakeven.py` (C-B1~C-B4, 9 케이스)

## RED 실행 결과 (구현 전)

```
python -m pytest test_cycleC_vcp_breakeven.py test_cycleC_bfb_breakeven.py -q
→ 14 failed, 8 passed
```

- **14 failed** = 신규 기능 부재로 인한 정당한 RED (`_breakeven_latched` 필드 AttributeError /
  `breakeven_promote_atr` DEFAULT_PARAMS 부재 / `recompute_high_since_buy` 메서드 부재 /
  래치 승격 무발화).
- **8 passed** = 지금도 성립하고 구현 후에도 유지되어야 하는 불변식 (default-off no-op 회귀 +
  PARAM_RANGES/INT_PARAMS 제외). GREEN 기준선의 일부.

### RED 상세 (14건)

| 케이스 | RED 사유 | GREEN 조건 |
|--------|----------|-----------|
| C-V1 `test_CV1_latch_persists_after_atr_expansion` (HIGH) | `_breakeven_latched` 부재 (AttributeError) | 래치 성립 후 ATR 팽창해도 buy 도달 시 STOP_LOSS |
| C-V1 `test_CV1_no_latch_before_threshold_reached` | 동상 | high<임계면 래치 미형성 |
| C-V2 `test_CV2_promotion_fires_at_buy_price` | `_breakeven_latched.add` AttributeError | 래치+current≤buy → STOP_LOSS |
| C-V2 `test_CV2_promotion_tighten_only_no_fire_above_buy` | 동상 | 래치+current>buy → NONE (tighten-only) |
| C-V3 `test_CV3_default_param_is_off` (HIGH) | DEFAULT_PARAMS 키 부재 (None≠0.0) | `breakeven_promote_atr=0.0` 추가 |
| C-V4 `test_CV4_vcp_has_recompute_high_since_buy` | 메서드 부재 | `recompute_high_since_buy` 이식 |
| C-V4 `test_CV4_recompute_corrects_stale_high_since_buy` | 동상 (AttributeError) | 매수일<bsop<today high max 보정 |
| C-V4 `test_CV4_recompute_does_not_lower_high` | 동상 | 후보≤기존 시 미갱신 (max-only) |
| C-V5 `test_CV5_on_position_closed_discards_latch` | `_breakeven_latched` 부재 | on_position_closed 에서 discard |
| C-B1 `test_CB1_latch_persists_after_atr_expansion` (HIGH) | `_breakeven_latched` 부재 | VCP C-V1 동형 |
| C-B2 `test_CB2_promotion_fires_at_buy_price` | 동상 | 래치+current≤buy → STOP_LOSS |
| C-B2 `test_CB2_promotion_tighten_only_no_fire_above_buy` | 동상 | tighten-only |
| C-B3 `test_CB3_default_param_is_off` (HIGH) | DEFAULT_PARAMS 키 부재 | `breakeven_promote_atr=0.0` 추가 |
| C-B4 `test_CB4_on_position_closed_discards_latch` | `_breakeven_latched` 부재 | discard + 기존 `_partial_exit`/쿨다운 보존 |

### GREEN 유지 (8건, 지금 PASS)

- VCP/BFB `test_CV3_disabled_no_latch_no_promotion` — default-off 시 임계 도달해도 무발화.
- VCP `test_CV3_existing_exit_stack_preserved_when_off` — default-off 하드손절 -7%/base_low 보존.
- BFB `test_CB3_existing_exit_stack_preserved_when_off` — default-off 하드손절 -5%/measured-move 보존.
- VCP/BFB `test_breakeven_key_excluded_from_param_ranges` / `..._int_params`.

## 기준선 (기존 VCP/BFB 스위트 GREEN)

구현 전 기존 스위트 실행:
```
test_vcp_breakout.py, test_vcp_breakout_mcap_pass.py, test_cycle48/49/125_vcp*,
test_bull_flag_breakout*.py, test_cycle50/198/211_bfb*
→ 90 passed, 6 xfailed
```
구현 후 이 90 PASS / 6 XFAIL 이 **불변** 이어야 한다 (default-off byte 동일 = 계약 기준선).

## backend-dev 인계 인터페이스 (확정)

두 전략(`vcp_breakout.py` / `bull_flag_breakout.py`) 공통:

1. **`__init__`**: `self._breakeven_latched: set[str] = set()` 추가.
2. **DEFAULT_PARAMS**: `"breakeven_promote_atr": 0.0` 추가 (default-off).
   - PARAM_RANGES / INT_PARAMS **미편입** (청산 정체성 상수).
3. **`check_exit_signal`** 승격 분기 (하드손절 계열, `breakeven_promote_atr > 0` 일 때만):
   - live atr = `_candidates.get(ticker, {}).get("atr14", 0)`.
   - 래치: `ticker not in _breakeven_latched and atr>0 and high_since_buy >= buy_price + mult*atr`
     → `_breakeven_latched.add(ticker)`.
   - 발화: `ticker in _breakeven_latched and current_price <= buy_price` → `Signal.STOP_LOSS`
     (로그 prefix VCP `[vcp_breakeven_promote]` / BFB `[bfb_breakeven_promote]`).
   - **위치 자유** (전부 STOP_LOSS 계열) — 하드손절/base_low/flag_low 앞뒤 무방. tighten-only:
     current>buy 에서 절대 미발화 (손절선이 buy 위로 넓어지는 케이스 0).
4. **`on_position_closed(ticker)`**: 기존 정리 옆에 `self._breakeven_latched.discard(ticker)` 추가.
   - BFB 는 `_partial_exit.pop` + `register_cooldown_after_exit` 보존 (C-B4 회귀 가드).

VCP 전용 (C-V4):
5. **`recompute_high_since_buy()` + `_apply_high_since_buy_from_candles()` 이식** — donchian
   패턴 100% (매수일 < bsop_date < today 일봉 high max, 기존값 초과 시에만 갱신 + DB UPDATE + 로그).
   - **fetch 소스 계약**: 메서드 내부에서 `from src.api.condition import fetch_daily_candles` import
     (테스트가 `src.api.condition.fetch_daily_candles` 패치). DB 신선도 부담 없이 donchian 동일.
     만약 backend 가 DB 어댑터(`get_recent_daily_normalized`)로 구현하면 테스트 패치 타겟을
     동반 조정 (Red→Green 협상 대상 — tdd-engineer 통보 요망).
   - BFB 는 범위 외 (자문 — 5영업일 한도라 한계효용 낮음, 후순위).

## 매매 안전성 diff 0 의무 (명세 §24)

`src/realtime/` `src/auth/` `src/api/order.py` `src/engine/risk.py` `src/engine/order_engine.py` diff 0.
변경 대상 = 두 전략 파일 + 테스트만. 매수 경로(check_buy_signal/prepare) 무변경.
