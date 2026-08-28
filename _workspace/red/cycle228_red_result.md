# 사이클 228 — Red 실행 결과 (228-A 게이트 전환+래치 / 228-B setup 리졸버)

> 작성: tdd-engineer, 2026-08-27
> 명세 정본: `_workspace/red/cycle228_gate_latch_spec.md`
> 자문 정본: `_workspace/domain_consult/cycle228_vol_gate_latch.md`
> 프로덕션 코드 변경 **0**. 기존 테스트 수정 **0**.

---

## 1. 결과 요약

```
78 failed, 19 passed in 0.81s      (총 97)
```

| 파일 | 총 | RED | PASS | 성격 |
|---|---|---|---|---|
| `tests/unit/engine/strategies/test_cycle228_bfb_gate_transition.py` | 24 | 23 | 1 | A1·A2·A4 |
| `tests/unit/engine/strategies/test_cycle228_vcp_gate_transition.py` | 22 | 19 | 3 | A1·A3·A4 |
| `tests/unit/engine/strategies/test_cycle228_log_cap_counters.py` | 17 | 15 | 2 | A5·A6 |
| `tests/unit/ast/test_cycle228_ast_gate_guards.py` | 18 | 11 | 7 | A8 |
| `tests/unit/engine/strategies/test_cycle228b_setup_resolver.py` | 16 | 10 | 6 | B1·B2·B3 |

파일 분리 = 명세의 **커밋 순서 구속**(Red A+B 동시 → Green A → A 커밋 → Green B) 이행.
`test_cycle228b_*` 10건은 A 구현으로 만족될 수 없다(§4.3 근거).

기존 회귀 무영향 확인:
`tests/unit/engine/strategies/` + `tests/unit/ast/`(신규 5파일 제외) → **1,611 passed / 2 skipped / 50 xfailed / 3 xpassed**.

---

## 2. PASS 19건 분류 — **진짜 보존 10 vs 공허 9**

사이클 224 의 **자기 가드 공허성** 교훈(정의상 항상 참이던 가드가 뮤테이션 전후 모두 통과)에 따라
"지금 통과하는 이유"를 나눠 적는다. **공허 PASS 는 Green 이후에도 통과하는지가 진짜 검증**이다.

### (a) 진짜 보존 검증 10건 — 이번 변경이 깨면 안 되는 것

```
vcp ::test_gate_mirror_when_threshold_is_zero_then_pass            # 거울 정합 의미론
vcp ::test_gate_mirror_zero_threshold_passes_even_without_observation
logs::test_a5_korean_literals_are_byte_preserved                   # 한글 grep 이력
ast ::test_g8_korean_transition_literals_preserved[seen|retreat]
ast ::test_g4_extension_cap_not_ai_tunable                         # PARAM_RANGES 영구 배제
b   ::test_b2_bfb_indicator_atr_still_comes_from_live              # 지표 live 우선 유지
b   ::test_b2_vcp_indicator_ema50_still_comes_from_live
b   ::test_b2_bfb_unstamped_position_still_uses_live_fallback
b   ::test_b2_bfb_no_position_setup_and_no_live_is_still_empty_dict
```

### (b) ⚠️ 공허 PASS 9건 — 기능이 **아예 없어서** 통과 중

```
bfb ::test_latch_requires_candidate_membership          # 래치가 없어 후보 소멸이 곧 NONE
vcp ::test_latch_requires_candidate_membership
logs::test_a5_cap_key_separates_transition_kinds        # cap 자체가 없어 1행씩 나옴
ast ::test_g2_gate_reads_tick_volume[bfb|vcp]           # 현재는 관측 훅이 그 심볼을 참조
ast ::test_g5_extension_check_has_no_daily_high_tokens[bfb|vcp]   # 판정식 자체가 부재
b   ::test_b2_no_conflict_log_when_live_matches_stamp   # conflict 로그가 부재
b   ::test_b2_no_conflict_log_when_unstamped
```

특히 `test_g2` 는 **Green 후에야 의미가 생긴다** — 지금 통과하는 이유는
`_observe_vol_gate`(A6 에서 은퇴 대상)가 `get_observed_acml_vol` 을 참조하기 때문이고,
훅이 사라진 뒤에도 통과해야 비로소 "게이트가 그 소스를 읽는다"의 증거가 된다.

---

## 3. cycle227 의미 전환·은퇴 대상 전수 (Green 에서 처리)

cycle227 총 103건 중 **41건이 영향**을 받는다.

### 3.1 전량 은퇴 — 36건 (관측 훅 은퇴에 종속)

`tests/unit/engine/strategies/test_cycle227_bfb_vol_gate_observe.py` (18)
`tests/unit/engine/strategies/test_cycle227_vcp_vol_gate_observe.py` (18)

두 파일 전체가 `_observe_vol_gate` / `[*_vol_gate_observe]` 마커 / `vol_gate_observe_*`
카운터 위에 서 있다. A6 이 셋을 모두 은퇴시키므로 파일 단위 은퇴가 정직하다.
**cycle228 신규 3파일이 그 커버리지를 승계한다:**

| cycle227 (은퇴) | cycle228 승계처 |
|---|---|
| `test_observe_when_observed_ge_threshold_then_would_pass_true` | `test_gate_when_tick_volume_sufficient_then_buy` |
| `test_observe_when_no_observation_then_distinct_reason` | `test_gate_when_no_observation_then_fail_closed_with_warning` |
| `test_observe_when_threshold_is_zero_then_would_pass_true`(VCP) | `test_gate_mirror_when_threshold_is_zero_then_pass` |
| `test_scan_stats_exposes_three_observe_counters_...` | `test_a6_new_counters_present_from_fresh_instance` |
| cap 4종 | `test_a6_*_marker_capped_and_counted` + `test_a5_*` |
| `test_log_body_does_not_contain_other_markers` | `test_a6_markers_do_not_mention_other_markers` |
| `test_observer_failure_when_lookup_raises_...` | **승계처 없음** — 아래 §5 미결 2 |

⚠️ **의미 반전 명시 대상 2건**:
`test_gate_still_returns_none_regardless_of_observation[exact]`·`[far_above]` 는
"관측이 충분해도 NONE" 을 Stage 0 봉인으로 단언했다. 이번 사이클이 그 봉인을 **푸는 것**이므로
`xfail` 이 아니라 **삭제 + 반대 계약 신설**(`test_gate_when_tick_volume_sufficient_then_buy`)이 정답이다.

### 3.2 의미 전환 — 2건

```
tests/unit/ast/test_cycle227_ast_acml_vol_guards.py
  ::test_AST2_existing_volume_gate_block_is_byte_identical[bfb]
  ::test_AST2_existing_volume_gate_block_is_byte_identical[vcp]
```

게이트 블록 소스 pin. cycle227 작성 당시 주석에 *"게이트 전환 사이클에서 이 가드를
의미 전환하는 것이 정상 경로"* 라고 예고해 두었고, 그 사이클이 지금이다.
대체 가드 = cycle228 `test_g1_no_ticker_prices_reference` + `test_g9_legacy_gate_expression_removed`.

### 3.3 무변경 유지 — 3건 (명세 A8 명시)

```
::test_AST1_no_acml_vol_assignment_into_ticker_prices   # 유령 키 재발 영구 차단
::test_AST3_handle_tick_field_guard_stays_at_ten
::test_AST4_tick_volume_is_leaf_module
```

### 3.4 무영향 — 62건

`test_cycle227_handler_acml_vol.py`(22) · `test_cycle227_tick_volume.py`(14) ·
`test_cycle227_risk_on_tick_acml.py`(9) · `test_cycle227_universe_guard_acml.py`(14) ·
`test_cycle227_e2e_acml_vol_pipeline.py`(3). 228 은 8영역·`tick_volume.py` 무접촉이다.

### 3.5 은폐 3파일 (A7) — BUY 기대 5건이 FAIL 예정

`ticker_prices["acml_vol"]` 손주입 **11곳** → `tick_volume.record_acml_vol` 로 교체.
게이트 소스가 바뀌므로 **BUY 를 기대하는 5건만** 실제로 깨진다:

```
test_bull_flag_breakout.py:133  test_buy_when_breakout_with_volume_then_buy
test_bull_flag_breakout.py:217  test_buy_when_cooldown_expired_then_buy
test_bull_flag_breakout_retention.py:97  test_buy_signal_after_retention_period
test_vcp_breakout.py:153        test_buy_when_breakout_with_volume_then_buy
test_vcp_breakout.py:236        test_buy_when_cooldown_expired_then_buy
```

⚠️ 나머지 6곳(`NONE` 기대)은 전환 없이도 **계속 통과한다 — 이유가 바뀐 채로**
(거래량 미달 → 미관측 fail-closed). **공허 PASS 로 남는다.** 주입을 함께 옮기지 않으면
"시정이 검증되지 않는다"는 worklist 의무가 정확히 이 6곳에서 깨진다.

✅ **추격 상한은 이 5건을 추가로 깨뜨리지 않는다** — 실측 확인:
BFB `flag_high=12,300 / 현재 12,350` = +0.41%, retention `12,000 / 12,100` = +0.83%,
VCP `12,000 / 12,100` = +0.83%. 모두 캡(5.0 / 7.5) 안쪽이다.

### 3.6 8영역·전략 파일 sha 핀

cycle227 이 **커밋됐다**(`a7245af`) — risk/handler/BFB/VCP 4항목 핀은 이미 **자기소멸**했고
(워킹트리 clean) 현재 4개 가드 모두 통과 중이다. A8 의 "잔존 핀 삭제(TODO 이행)" 는
죽은 값 청소이며, Green A 가 BFB/VCP 를 수정하는 순간
`test_g223_12_other_strategy_files_diff_zero` 가 **스테일 sha 로 FAIL** 한다 → 재핀 필요.

```
test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA        → 2항목 삭제
test_cycle223_ast_donchian_exit_fix.py::_CYCLE227_STRATEGY_CONTENT_SHA  → BFB/VCP 재핀 (A 커밋 전 1회, B Green 후 1회)
test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA  → 2항목 삭제
test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA            → 2항목 삭제 (BFB/VCP 는 이 가드의 8영역 목록 밖이라 신규 핀 불요)
```

---

## 4. 착수 전 검증 결과

### 4.1 B1 결함 주장 — **양 축 모두 코드로 확인됨 (반증 아님, 진행)**

| 축 | 확인 방법 | 결과 |
|---|---|---|
| `_effective_setup` 이 live 를 **통째로** 우선 | 소스 직독 | `if live: return live` — 키별 병합 **없음** (BFB `:965-968` / VCP `:1076-1079`) |
| `prepare()` 가 보유 종목 **미제외** | `prepare` 본체 AST unparse 토큰 집계 | `has_position`·`is_ticker_held_by_any`·`positions`·`_position_setup` 전부 **0회** (BFB·VCP 양쪽) |

부수 확증: `_refresh_position_setup_from_candles` docstring 이
*"구조 레벨 … 이미 있으면 건드리지 않는다"* 라고 적어 두었다 — 그 함수는 `_position_setup` 을
지키지만 `_effective_setup` 의 live-우선이 **그 보호를 우회**한다. 보호받는 값이 읽히지 않는다.

### 4.2 라이브 파라미터 가정 금지 (자문 실측 정정 1)

테스트는 **코드 기본값**만 쓴다 — BFB `breakout_volume_mult=2.0`·`retention=3`,
VCP `mult=1.5`. 라이브(1.0 / 1 / 1.2)는 어디에도 박지 않았다.
실측 시나리오(280360·001450)는 **임계를 직접 주입**해 재현하므로 mult 변화에 면역이다.

### 4.3 A 구현이 B 를 우연히 만족시키지 않는다

`test_cycle228b_*` 는 전부 `check_exit_signal` 경로이고, A 의 변경면은
`check_buy_signal` + `_scan_stats` + cap 헬퍼다. 접점 0.
`_candidates` / `_position_setup` 을 테스트가 **직접 주입**하므로,
설령 Green 이 "`prepare()` 에서 보유 종목 제외" 로 우회 시정하더라도 B 테스트는 여전히 RED 다
(리졸버 자체를 고쳐야만 통과한다 — 명세 B2 의 의도).

### 4.4 freezegun 함정 — 이번엔 해당 없음

cycle227 에서 universe 가드가 `await asyncio.sleep(0.05)` 때문에 freeze 아래 행(hang)했다.
이번 5파일은 **asyncio 미포함**(전부 동기 `check_buy_signal`/`check_exit_signal`)이라 안전하다.
전체 실행 0.81초로 확인.

---

## 5. ⚠️ 명세 미명시 5건 — team-leader 판정 요청

Red 가 **자문에서 도출해 계약으로 고정**했으나 명세 본문에 없는 항목이다.
반대 판정이면 해당 테스트를 삭제/수정한다.

| # | 항목 | 근거 | 고정한 테스트 |
|---|---|---|---|
| **1** | **래치 레벨 박제** — 무장 후 live `flag_high`/`base_high` 가 이동하면 래치 해제 | 자문 Q1 "구현 시 못박을 것 2" + tdd 권고 6. `prepare()` 는 후보가 빌 때 장중 재실행되어(`scheduler.py:2662`) 골대가 래치 아래에서 움직일 수 있다 | `test_latch_released_when_live_levels_move_under_it` (BFB·VCP) |
| **2** | **미관측(`no_data`)도 래치를 무장한다** | 자문의 래치 정의 = *"오늘 retention 을 이미 통과했다"* 만 기억(거래량 판정 결과가 아님). 무장 안 하면 edge-crossing 소진 후 관측이 도착해도 재평가 기회가 없어 역선택이 미관측 경로로 부활 | `test_a6_no_data_also_arms_latch` |
| **3** | **`no_data` 마커 레벨 = WARNING** | 자문 Q7 표에 WARNING 명시(명세 A1 은 "마커" 로만 표기). `_DbLogHandler` INFO 컷을 넘겨야 `system_logs` 도달 | `test_gate_when_no_observation_then_fail_closed_with_warning` (BFB·VCP) |
| **4** | **`latch_age_sec` 위치 = `[*_vol_gate_pass]` 로그 본문, 미래치 시 `0`** | 명세는 "매수 로그/신호에" 로 열어 두었다. tester 가 로그에서 분포를 수집하므로 로그 본문으로 고정하고, 조건부 누락은 파서를 이중화하므로 항상 0 을 넣는다 | `test_latch_records_latch_age_sec_on_fire`, `test_latch_age_sec_is_zero_when_never_latched` |
| **5** | **`_check_extension_cap_invariant` = 이름 있는 헬퍼** | `prepare()` 본체는 DB/KIS + 0건 시 `asyncio.sleep(30)` 재시도라 단위 테스트로 못 돈다. cycle224 의 "행위는 헬퍼 직접 검증 + 배선은 AST 가드" 조합 답습 | `test_extension_cap_invariant_helper_exists` + `test_g7_prepare_calls_extension_cap_invariant` |

### 명세 ↔ 자문 충돌 2건 — **명세를 따랐다**

1. **`_prev_price` 일일 clear** — 자문 Q2 "만료의 실제 경계" 가 `_reset_daily_state` 에서
   래치와 **함께** clear 하라고 요구한다(일 경계를 넘으면 다음 날 첫 틱이 어제 종가와 비교돼
   허위 edge-crossing). 그러나 명세 A2 는 **"edge-crossing 등 기존 진입 로직 무변경"** 이고
   `_vol_latch` 만 날짜 키 자기 리셋으로 못박았다. ⇒ **명세 채택**, `_prev_price` 무변경.
   부작용을 `test_latch_is_daily_scoped_by_date_key_self_reset` docstring 에 남겼다 —
   그 테스트가 통과하는 이유의 일부가 `_prev_price` 잔존이므로, 후속 사이클이 clear 를
   도입하면 이 케이스를 함께 다시 봐야 한다.
2. **카운터 이름** — 자문 Q5 는 `breakout_detect`/`latch_released`/`latch_fired` 를 제안했으나
   명세 A5/A6 이 `breakeout_seen_count`/`breakout_retreat_count`/`latch_armed_count` 로 확정했다.
   ⇒ **명세 채택**(6키: `vol_gate_pass`·`vol_gate_reject_ext`·`vol_gate_no_data`·
   `latch_armed_count`·`breakout_seen_count`·`breakout_retreat_count`).
   `latch_released`/`latch_fired` 카운터는 신설하지 않았다.

### 미결 2 — 승계처 없는 커버리지 1건

cycle227 의 `test_observer_failure_when_lookup_raises_then_warning_and_evaluation_survives`
(관측기 자기실패 흡수)는 **승계처가 없다**. 관측 훅과 달리 **게이트 본체는 실패를 흡수하면
안 되기 때문**이다 — 거래량을 못 읽었는데 매수를 계속하면 fail-open 이 되어 이 사이클의
fail-closed 계약과 정면 충돌한다. 다만 `tick_volume.get_observed_acml_vol` 이 예외를 던질 때
`check_buy_signal` 전체가 죽어 **그 종목의 청산 평가까지 멈추는지** 는 확인되지 않은 축이다.
Green 단계에서 backend-dev 가 판단하거나, 별도 사이클로 올릴 것을 권고한다.

---

## 6. 실행 명령

```bash
python -m pytest -q \
  tests/unit/engine/strategies/test_cycle228_bfb_gate_transition.py \
  tests/unit/engine/strategies/test_cycle228_vcp_gate_transition.py \
  tests/unit/engine/strategies/test_cycle228_log_cap_counters.py \
  tests/unit/ast/test_cycle228_ast_gate_guards.py \
  tests/unit/engine/strategies/test_cycle228b_setup_resolver.py
# → 78 failed, 19 passed
```

### 대표 RED 메시지

```
E  AssertionError: tick_volume 관측치가 임계를 넘었는데 매수하지 않았다
   — 게이트가 아직 유령 키(ticker_prices)를 읽고 있다
E  AttributeError: 'BullFlagBreakoutStrategy' object has no attribute '_vol_latch'
E  AssertionError: 래치 재평가 경로가 없다 — 깨끗한 돌파(뚫고 안 돌아본 종목)가
   재심사를 못 받아 영구 탈락하는 역선택이 그대로 남는다
E  KeyError: 'max_breakout_extension_pct'
E  AssertionError: 감지 로그 cap 미작동            # 100회 왕복 → 100행
E  AssertionError: 매수가 대비 +2% 인 포지션이 Signal.STOP_LOSS 로 청산됐다
   — §2 손절선이 익일 재검출된 새 flag_low(10,500)로 갈아탔다
```
