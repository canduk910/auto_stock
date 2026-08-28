# 사이클 229 — Red 실행 결과 (VB·momentum 매수 컷 15:20 + `[단일가매매]` 분류기)

> 작성: tdd-engineer, 2026-08-28
> 명세 정본: `_workspace/red/cycle229_buy_cutoff_spec.md` (W1~W5)
> 자문 정본: `_workspace/domain_consult/cycle229_vb_1530_single_price.md`
> 행위 분해: `_workspace/red/cycle229_behaviors.md`
> **프로덕션 코드 변경 0. 기존 테스트 수정 0.**

---

## 1. 결과 요약

```
23 failed, 27 passed in 0.30s      (총 50)
```

| 파일 | 총 | RED | PASS | 명세 축 |
|---|---|---|---|---|
| `tests/unit/engine/strategies/test_cycle229_vb_buy_cutoff.py` | 13 | 7 | 6 | W1 |
| `tests/unit/engine/strategies/test_cycle229_momentum_buy_cutoff.py` | 13 | 7 | 6 | W2 |
| `tests/unit/api/test_cycle229_single_price_classifier.py` | 12 | 2 | 10 | W3 |
| `tests/unit/engine/test_cycle229_sell_fallback_e2e.py` | 3 | 1 | 2 | W4-5 |
| `tests/unit/ast/test_cycle229_ast_cutoff_guards.py` | 9 | 6 | 3 | W4-8 |

**결정론**: 랜덤 순서 3회 반복 전부 `23 failed / 27 passed` 동일. flaky 0.

**기존 회귀 무영향**:
- `tests/unit/engine/` (신규 3파일 제외) → **3,331 passed** / 1 skipped / 129 xfailed / 4 xpassed
- `tests/unit/engine/strategies/` + `tests/unit/ast/` + `tests/unit/api/` (신규 4파일 제외) → **1,940 passed** / 1 skipped / 50 xfailed / 3 xpassed

---

## 2. RED 23건 — 전량 "기능 부재" 실패

```
W1  vb ::test_b1_2_when_kst_152000_breakout_then_none            # 경계 15:20:00
W1  vb ::test_b1_3_when_kst_152900_breakout_then_none            # 동시호가 한복판
W1  vb ::test_b1_3b_when_kst_153020_breakout_then_none           # 실측 발사 시각(8/27 에코프로)
W1  vb ::test_b1_5_cut_tick_does_not_update_prev_price           # 게이트 위치 뮤테이션 가드
W1  vb ::test_b1_7_cutoff_log_emitted_once_per_day               # [vb_buy_cutoff] cap
W1  vb ::test_b1_8_cutoff_log_resets_on_new_day                  # 날짜 키 자기 리셋
W1  vb ::test_b1_9_module_constant_is_1520                       # BUY_CUTOFF_KST 부재
W2  mo ::test_b2_2 / b2_3 / b2_3b / b2_5 / b2_7 / b2_8 / b2_9    # 위 7건 동형
W3  api::test_b3_1_single_price_msg_is_market_order_disallowed   # 실측 msg1 미분류
W3  api::test_b3_9_new_keyword_is_contiguous_substring           # "단일가매매" 키워드 부재
W4-5 e2e::test_b4_1_single_price_rejection_enters_limit_fallback # 폴백 미진입(현행 3회 재시도)
W4-8 ast::test_g2_module_level_cutoff_constant[vb|momentum]      # 모듈 상수 부재
W4-8 ast::test_g3_gate_precedes_prev_state_reference[vb|momentum]# 게이트 미배선
W4-8 ast::test_g5_gate_statement_uses_tz_aware_now[vb|momentum]  # 게이트 미배선
```

---

## 3. PASS 27건 분류 — **진짜 보존 21 vs 공허 6**

사이클 224 의 **자기 가드 공허성** 교훈(정의상 항상 참이던 가드가 뮤테이션 전후 모두 통과)에
따라 "지금 통과하는 이유" 를 나눈다. 공허 PASS 는 **Green 이후에도 통과하는지가 진짜 검증**이다.

### (a) 진짜 보존 검증 21건 — Green 이 깨면 안 되는 것

```
vb ::test_b1_1_when_kst_151959_breakout_then_buy        # 정상 매수창 잠식 금지 (대조군)
vb ::test_b1_6_exit_signal_still_fires_at_kst_1525      # 청산 무간섭
vb ::test_b1_12_tradable_boards_unchanged               # 보드 축 무접촉
mo ::test_b2_1_when_kst_151959_breakout_then_buy
mo ::test_b2_6_exit_signal_still_fires_at_kst_1525
api::test_b3_2_single_price_msg_is_not_market_closed    # 순서 계약 무교차
api::test_b3_3_..._not_insufficient_cash                # 자금 락 오분류 차단
api::test_b3_4_..._not_insufficient_quantity            # positions 삭제 오분류 차단
api::test_b3_5_aftermarket_variant_still_matches        # Phase H1 회귀
api::test_b3_6_apbk1943_variant_still_matches           # 계양전기 회귀
api::test_b3_7_pre_market_double_match_preserved        # 2026-08-06 이중 매칭 계약
api::test_b3_8_existing_keywords_structurally_cannot_match  # B3-1 우회 차단 (아래 §3-c)
api::test_b3_10_benign_messages_not_classified[×3]      # 신규 키워드 오탐 차단
e2e::test_b4_2_no_exception_propagates_to_caller        # G-REJECT-1 전파 설계 불변
e2e::test_b4_4_pre_market_rejection_still_defers        # 순서 계약 e2e
ast::test_g4_no_cross_strategy_import[vb|momentum]      # 상수 공유 금지
```

### (b) ⚠️ 공허 PASS 6건 — 기능이 **아직 없어서** 통과 중

```
vb ::test_b1_4_when_utc_wallclock_1520_but_kst_0020_then_buy    # 게이트가 없으니 컷도 없다
mo ::test_b2_4_when_utc_wallclock_1520_but_kst_0020_then_buy
vb ::test_b1_10 / b1_11  (DEFAULT_PARAMS · PARAM_RANGES 미편입)  # 상수 자체가 없다
mo ::test_b2_10 / b2_11
ast::test_g1_no_naive_now_time_in_check_buy_signal[vb|momentum]  # `.time()` 호출이 0건
```

`b1_4`/`b2_4`(TZ 역방향)와 `g1`(naive 금지)은 **Green 이후에 비로소 의미가 생긴다** —
§4 뮤테이션 검증에서 이 6건이 실제로 무는지 확인했다.

### (c) B3-8 의 역할 — B3-1 의 우회 차단

`test_b3_8` 은 PASS 이지만 공허하지 않다. 실측 msg1 이 기존 키워드 2종
(`"지정가 및 최유리"` / `"최유리/최우선지정가 주문만"`)으로 **구조적으로 매칭 불가**함을 고정해,
B3-1 을 "기존 키워드 느슨화" 로 통과시키는 경로를 막는다. B3-1 이 통과했다면 그것은 반드시
신규 키워드의 공로다.

---

## 4. 뮤테이션 검증 — 가드가 실제로 무는지 실증

Red 를 넘기기 전에 **후보 Green 구현을 임시로 적용해 3가지를 확인**했다(적용 후 백업에서
byte 단위 복원, `md5` + `git diff` 로 diff 0 확인 완료).

### 뮤테이션 0 — 정상 Green (Green 도달 가능성)

VB/momentum 에 `BUY_CUTOFF_KST = time(15, 20)` + `check_buy_signal` 최상단
`_now_kst = datetime.now(KST)` 게이트 + 날짜 키 자기 리셋 cap, `balance.py` 에 `"단일가매매"` 1줄.

```
50 passed in 0.29s      ← RED 23건 전량 해소, 보존 27건 무손상
```

**중요**: 이 테스트 묶음은 backend-dev 가 도달 불가능한 요구를 담고 있지 않다.

### 뮤테이션 1 — 게이트를 naive 로 (`datetime.now().time()`)

```
16 failed
  ├ ast::test_g1[vb|momentum]                       # naive 직접 검출
  ├ vb::test_b1_4 / mo::test_b2_4                   # TZ 역방향 — "엉뚱한 때 컷한다"
  └ vb::b1_2·b1_3·b1_3b·b1_5·b1_7·b1_8 + mo 동형    # 경계 — "컷을 놓친다"
```

양방향 TZ 가드가 둘 다 발화했다. **한쪽만 있었으면 naive 구현이 절반의 케이스를 통과**한다.
(G-5 는 이 뮤테이션에서 통과한다 — 음성 판정은 G-1 담당, G-5 는 "시각을 아예 안 읽는" 구현을
잡는 양성 짝이다. 둘의 조합이 커버리지를 만든다.)

### 뮤테이션 2 — 게이트를 `_prev_price` 갱신 **뒤**로 이동

```
2 failed
  ├ ast::test_g3_gate_precedes_prev_state_reference[vb]   # 856 < 852 실패로 정확히 지목
  └ vb ::test_b1_5_cut_tick_does_not_update_prev_price
```

정확히 2건만 실패 = 가드가 **정밀**하다(노이즈 없음). G-3 의 기준선(`_prev_price` 첫 참조
라인)이 게이트 위치와 독립이라 사이클 224 식 공허화가 발생하지 않음을 실증했다.

---

## 5. Green 담당자(backend-dev) 인계 사항

### 수정 허용 파일 (명세 §제약)

`volatility_breakout.py` / `momentum.py` / `balance.py` — **이 3개뿐**.
8영역 · `scheduler.py` · `session.py` · `order_engine.py` **diff 0**.

### 계약 요약

1. **상수** — 각 전략 파일에 **모듈 레벨** `BUY_CUTOFF_KST = time(15, 20)`.
   서로 import 금지(G-4). `DEFAULT_PARAMS`/`PARAM_RANGES`/`INT_PARAMS` 미편입.
2. **게이트** — `check_buy_signal` 최상단, prev 상태(`_prev_price` / `_prev_prdy_rate`)
   read/write **이전**. `datetime.now(KST).time() >= BUY_CUTOFF_KST` → `Signal.NONE`.
   momentum 에는 `KST` 상수 자체가 없으니 함께 들여와야 한다.
3. **관측** — `[vb_buy_cutoff]` / `[momentum_buy_cutoff]` INFO, 하루 1행,
   **날짜 키 자기 리셋**(`_reset_daily_state` 훅 의존 금지 — momentum 은 그 훅을 override
   하고 있어 거기 얹으면 호출 누락 한 번에 관측이 영구 침묵한다).
4. **분류기** — `_MARKET_ORDER_DISALLOWED_KEYWORDS` 에 `"단일가매매"` 추가. **그것만**.
   기존 키워드를 넓히면 B3-8/B3-10 이 깨진다.
5. `execute_sell` 은 **손대지 않는다** — 기존 폴백 분기가 자동으로 열린다(e2e 로 실증).

### Green 이후 확인 명령

```bash
python -m pytest -q tests/unit/engine/strategies/test_cycle229_vb_buy_cutoff.py \
  tests/unit/engine/strategies/test_cycle229_momentum_buy_cutoff.py \
  tests/unit/api/test_cycle229_single_price_classifier.py \
  tests/unit/engine/test_cycle229_sell_fallback_e2e.py \
  tests/unit/ast/test_cycle229_ast_cutoff_guards.py
# 기대: 50 passed
```

---

## 6. 기존 테스트 의미 전환 — **0건**

이번 Red 는 기존 테스트를 하나도 수정하지 않았고, Green 단계에서도 의미 전환이 필요한
기존 케이스를 발견하지 못했다. 근거:

- VB/momentum `check_buy_signal` 을 부르는 기존 테스트는 **freezegun 미사용이거나 장중 시각**
  이라 게이트에 걸리지 않는다(전 엔진 스위트 3,331 PASS 로 확인 — Green 뮤테이션 0 적용
  상태에서도 회귀 0이었다).
- `balance.py` 키워드 추가는 기존 매칭 집합을 넓히기만 하고 좁히지 않는다
  (`test_insufficient_classification.py` · `test_rejection_classifier_pre_market_priority.py` ·
  `test_order_engine_sell_fallback.py` 전부 무영향 확인).

⚠️ 단, **Green 커밋 시점에 전 스위트를 다시 돌릴 것** — 위 확인은 후보 구현 기준이다.

---

## 7. tester 인계 — D+1(2026-08-31 월) 실측 체크리스트

cycle228 지표와 **같은 표에 섞지 말 것**(시각축·전략축이 다르다).

1. `[callback_exception]` **15:30 대 0건** — 주 판정.
2. `[vb_buy_cutoff]` / `[momentum_buy_cutoff]` 발화 여부 — **미발화도 정상**(그날 15:2x 이후
   돌파가 없었을 뿐). 며칠 이어지면 게이트가 도달 가능한지 자체를 의심할 것.
3. VB 15:20 이후 `buy_signals` 0건.
4. `[kis_rejection]` 중 `APBK3013` — 15:30 대 소멸 확인.
5. `[selling_reconcile]` 빈도 — 지정가 매도 미체결 잔존 부작용 감시(자문 §5-2 잔여 위험 1).

**⚠️ 관측 은퇴 주의**: 이번 사이클로 15:30 대 `[callback_exception]` 의 **의미가 반전**된다
(있음 → 없음이 정상). 2026-08-28 이전/이후 로그를 같은 grep 으로 합산하지 말 것.
