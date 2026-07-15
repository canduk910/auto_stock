# 사이클 213 Red — LTV(long_tail_volatility) 재진입 쿨다운 도입

설계 자문 = `_workspace/domain_consult/cycle213_ltv_reentry_cooldown.md` (채택).
**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

## 결함 배경

테스(095610) LTV 이틀 whipsaw -20,000 (7/13 매수→손절 -10,100 / 7/14 재매수→손절 -9,900). 둘 다 **당일 모드 손절** (상한가 미도달). LTV 만 재진입 쿨다운 무방비 — BFB(3)/VCP(7)/VB(2, 사이클 201) 배선됨, LTV 미배선.

LTV 특유 = 두 모드가 한 클래스에 붙어 있다.
- **당일 모드** (`_limit_up_reached` 비멤버) = VB 와 동형 whipsaw. 쿨다운 대상.
- **상한가 모드** (`_limit_up_reached` 멤버) = 밤샘 보유 → 익일 청산 = 정상 재진입 사이클. 쿨다운 면제.

`on_position_closed(ticker)` 훅은 exit_reason 미배선 → 훅 시점 `_limit_up_reached` 멤버십으로 "당일 모드 손절만" 근사.

## Green 계약 (VB 사이클 201 패턴 복사 + 상한가 게이트 한 겹)

`src/engine/strategies/long_tail_volatility.py`:

1. `DEFAULT_PARAMS["reentry_cooldown_days"] = 2` (BFB 3 / VCP 7 / VB 2 와 구분, **PARAM_RANGES 미등록**).
2. `__init__` `self._cooldown_until: dict[str, date] = {}`.
3. `register_cooldown_after_exit(ticker)` = 즉시 근사 `today + timedelta(days=days + 2)` (VB 201 복사).
4. `async def _refine_cooldown_business_days(ticker)` = `add_business_days(today, days)` 정정 graceful (VB 201 복사).
5. **`on_position_closed(ticker)` override 수정 (핵심)**:
   ```python
   def on_position_closed(self, ticker):
       was_limit_up = ticker in self._limit_up_reached   # discard 전 판정 (게이트 핵심)
       self._limit_up_reached.discard(ticker)             # 사이클 185 보존
       if was_limit_up:
           return                                          # 상한가 모드 = 쿨다운 면제
       self.register_cooldown_after_exit(ticker)
       coro = self._refine_cooldown_business_days(ticker)
       try:
           asyncio.create_task(coro)
       except RuntimeError:
           coro.close()
   ```
6. `check_buy_signal` 매수 게이트 = `is_sold_today` 가드 직후:
   ```python
   today = datetime.now(KST).date()
   cd_until = self._cooldown_until.get(ticker)
   if cd_until and cd_until >= today:
       return Signal.NONE
   ```
   (현재 LTV L688-691 `has_position/is_buy_pending/is_sold_today` 가드 직후, `is_max_positions` 전.)

`add_business_days` 는 `from src.api.condition import add_business_days` (VB 201 동일). LTV top-level `import asyncio` (14행) 기존재 = create_task 사용 가능.

## 회귀 가드 (Red — production 미변경 FAIL)

### `tests/unit/engine/strategies/test_cycle213_ltv_reentry_cooldown.py` (G-213-1~5,7)

- **G-213-1** (Red): LTV DEFAULT_PARAMS `reentry_cooldown_days == 2` (키 부재 KeyError).
- **G-213-2** (HIGH Red, whipsaw 차단): 당일 모드 종목(ticker ∉ `_limit_up_reached`) `on_position_closed` → `_cooldown_until` 등록 → 쿨다운 내 `check_buy_signal` NONE. 테스 재현.
- **G-213-3** (HIGH Red, 상한가 면제): 상한가 모드(ticker ∈ `_limit_up_reached`) `on_position_closed` → `_cooldown_until` 미등록 (정상 익일 재진입 보존).
- **G-213-4** (HIGH Red, DISCARD-ORDER 시퀀스): `on_position_closed` 후 `_limit_up_reached` 에서 discard 됨 AND `_cooldown_until` 미등록 (상한가 종목 대상). discard 먼저였다면 was_limit_up=False → 쿨다운 등록 = 면제 붕괴. 행위 검증(mock 상한가 멤버) 은 이 파일, AST 는 별도 파일.
- **G-213-5** (SET-185-PRESERVE): `on_position_closed` 후 `_limit_up_reached` 에서 ticker discard (사이클 185 계약 불변, 양쪽 모드).
- 부가 (VB 201 답습): register 즉시 근사값 + refine 성공/실패 graceful.
- **G-213-7** (SAFETY): risk/order_engine/realtime/auth diff 검증은 메인 세션 git diff 로 (테스트 파일 아님) — 여기선 check_exit_signal 본체 불변 대리 검증 (당일 -3% / 상한가 -5% 분기 보존).

### `tests/unit/ast/test_cycle213_ltv_cooldown_ast.py` (G-213-4 AST, G-213-6 AST)

- **G-213-4-AST** (HIGH): `on_position_closed` 본문에서 `was_limit_up`(멤버십 Compare/Name 대입)이 `_limit_up_reached.discard` Call *전* 라인. 시퀀스 정적 가드.
- **G-213-6** (HIGH, NO-DAILY-RESET): LTV `_reset_daily_state`/`prepare` 에 `_cooldown_until` mutation 0건 (multi-day 방어, 사이클 191 G-191-NO-DAILY-RESET 답습). 현행 미접촉 PASS (미래 재발 차단).
- 부가: LTV `on_position_closed` 내 `register_cooldown_after_exit` Call ≥ 1 + `_limit_up_reached.discard` Call ≥ 1 + DEFAULT_PARAMS `reentry_cooldown_days: 2` 리터럴 + 다른 전략(BFB=3/VCP=7/VB=2) 값 불변.

## 의미 전환

사이클 185 LTV `on_position_closed` 테스트(`test_cycle185_cluster1_reset.py::TestMechanism2OnPositionClosed`)는 `_limit_up_reached.add(...)` 후 매도 → discard 만 단언. **상한가 멤버 종목**이라 사이클 213 게이트에서 was_limit_up=True → 쿨다운 미등록 → discard 만 수행 = 사이클 185 단언 전부 보존 (충돌 0, 의미 전환 불요 예상). Green 후 실행으로 확인.

## Red 결과 (production 미변경)

`pytest test_cycle213_ltv_reentry_cooldown.py test_cycle213_ltv_cooldown_ast.py` = **8 FAIL / 10 PASS**.

### FAIL (8 = Red 유효성 — Green 이 없애야 할 결함)
- `test_g213_1_default_params_reentry_cooldown_is_2` — 키 부재 (KeyError).
- `test_g213_2_today_mode_close_registers_cooldown_blocks_rebuy` (HIGH) — `_cooldown_until` AttributeError (등록 부재 → whipsaw 무방비).
- `test_register_cooldown_after_exit_approx` — 메서드 부재.
- `test_refine_success_replaces_with_business_day` — 메서드 부재.
- `test_refine_failure_keeps_approx_graceful` — 메서드 부재.
- `test_g213_4_ast_membership_read_before_discard` (HIGH) — `_limit_up_reached` 멤버십 판정 라인 부재 (게이트 미신설).
- `test_ltv_on_position_closed_calls_register_and_discard` — register Call 0건.
- `test_ltv_default_params_cooldown_days_is_2_ast` — 키 부재.

### PASS (10 = 불변식 / SAFETY / 미래 회귀 가드)
- `test_g213_3_limit_up_mode_close_exempts_cooldown` — 상한가 면제 불변식 (현행 register 부재라 자연 PASS, Green 후 over-register 차단 가드).
- `test_g213_4_discard_order_limit_up_discarded_and_not_registered` (HIGH) — 순서 역전 시 즉시 FAIL 되는 행위 가드 (현행 discard-only PASS).
- `test_g213_5_set_185_discard_preserved[limit_up/today_mode]` — 사이클 185 discard 계약 불변.
- `test_register`/`refine` 무관 `test_normal_breakout_allows_buy` — 게이트 over-block 0 (현행 게이트 부재 BUY, Green 후에도 쿨다운 없는 종목 BUY 유지).
- `test_g213_7_check_exit_signal_body_unchanged` — 당일 -3% / 상한가 -5% 청산 분기 불변 (SAFETY 대리).
- `test_g213_6_no_cooldown_reset_in_ltv_daily_or_prepare` (HIGH) — `_reset_daily_state`/`prepare` 에 `_cooldown_until` mutation 0건 (현행 미접촉 PASS, 사이클 191 답습).
- `test_other_strategy_cooldown_days_unchanged[bfb=3/vcp=7/vb=2]` — 다른 3전략 값 불변.

### 의미 전환 — 없음
사이클 185 LTV `on_position_closed` 테스트(`test_cycle185_cluster1_reset.py`) **14 PASS 전량 유지** (production 미변경 확인). 사이클 185 discard 테스트는 `_limit_up_reached.add(...)` 상한가 멤버 종목 대상 → Green 후 게이트에서 was_limit_up=True → 쿨다운 미등록 + discard 만 수행 = 사이클 185 단언 전부 보존. 충돌 0.

**Green 후 예상**: 8 FAIL → PASS (register/refine/게이트/DEFAULT_PARAMS/멤버십 순서 신설). 10 PASS 유지. 사이클 185 14 PASS 유지.
