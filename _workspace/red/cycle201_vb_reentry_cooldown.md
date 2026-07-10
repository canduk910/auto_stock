# 사이클 201 Red — VB 재진입 쿨다운 2영업일 신설

> 작성: 2026-07-10 (tdd-engineer) · 근거: `_workspace/domain_consult/cycle201_vb_weight_derisk.md` §재진단 (정본)
> 성격: **Red 단계** — 실패 테스트만. production 미변경. Green = backend-dev.

## 결함 (근본 원인)

VB(volatility_breakout) 는 **크로스데이 재진입 무방비**. 유일한 재매수 차단 = `is_sold_today`
(당일 재매수만). BFB(3영업일)/VCP(7영업일) 가 사이클 185/191 에서 받은 크로스데이 쿨다운
(`_cooldown_until` + `register_cooldown_after_exit` + `on_position_closed` + `add_business_days`)
이 **VB 미배선** (grep 0건 확정).

재진단 실측 = VB 손실 -57,350 의 45%(-26,000)가 LS ELECTRIC 4일 재진입 (6/19 청산 → 6/23 재매수,
둘 다 장중 손절). 쿨다운 하나만 막았으면 -57,350 → -31,350 (손실 45%↓). 단일 레버 최대 효과.

## Green 계약 (BFB 사이클 191 패턴 100% 미러링, 쿨다운=2영업일)

**대상**: `src/engine/strategies/volatility_breakout.py` (imports 준비 완료 — asyncio ✓ / date,timedelta ✓ /
KST=timezone(+9) ✓ / `add_business_days` from `src.api.condition` **추가 필요** = condition.py:258 존재 확인).

backend-dev 구현 항목 (정확한 위치):

1. **DEFAULT_PARAMS** (L68~85 dict) 에 `"reentry_cooldown_days": 2` 추가. (BFB 3 / VCP 7 과 구분 —
   VB 당일청산 특성상 짧게.)
2. **`__init__`** (L87~108, 마지막 `_scan_stats` 대입 L108 직후) 에 `self._cooldown_until: dict[str, date] = {}` 추가.
3. **import** (L17 `from src.engine.strategy_base ...` 근처) 에 `from src.api.condition import add_business_days` 추가.
4. **`register_cooldown_after_exit(self, ticker)`** 신설 (BFB L966~978 미러):
   ```
   days = self.config.params["reentry_cooldown_days"]
   today = datetime.now(KST).date()
   self._cooldown_until[ticker] = today + timedelta(days=days + 2)   # 즉시 달력일 근사
   ```
   VB 는 `_breakout_first_seen`/`_partial_exit` 없음 → pop 불요 (BFB 의 977 라인 생략).
5. **`async def _refine_cooldown_business_days(self, ticker)`** 신설 (BFB L980~992 미러):
   ```
   days = self.config.params["reentry_cooldown_days"]
   today = datetime.now(KST).date()
   try:
       accurate = await add_business_days(today, days)
       self._cooldown_until[ticker] = accurate
   except Exception:
       logger.warning("[vb] 영업일 정정 실패 (ticker=%s) — 근사값 유지", ticker)
   ```
6. **`on_position_closed(self, ticker)`** 신설 (BFB L998~1006 미러). **VB 에 기존 override 없음 → 신설**:
   ```
   self.register_cooldown_after_exit(ticker)
   coro = self._refine_cooldown_business_days(ticker)
   try:
       asyncio.create_task(coro)
   except RuntimeError:
       coro.close()
   ```
7. **매수 게이트** (`check_buy_signal` L647~) — `is_sold_today` 가드 **L653 직후, L655(`is_max_positions`) 전**에 삽입:
   ```
   today = datetime.now(KST).date()
   cd_until = self._cooldown_until.get(ticker)
   if cd_until and cd_until >= today:
       return Signal.NONE
   ```
   **돌파 절대규칙 판정 前** 위치 (자원 절약 + BFB L811~815 게이트 위치 정합).
8. **recommendation_engine 등록**: ⚠️ **BFB/VCP `reentry_cooldown_days` 는 PARAM_RANGES/INT_PARAMS 미등록**
   (DEFAULT_PARAMS 값만 존재 — 직접 확인). **기존 방식 답습 = VB 도 PARAM_RANGES/INT_PARAMS 미등록**
   (수동값 유지). 스펙 지시서의 "INT_PARAMS 등록"은 BFB/VCP 실태와 불일치 → 미등록이 정합. (등록 시
   자동튜닝 대상이 되나 BFB/VCP 선례 없음 → 범위 밖.)
9. **`_workspace/00_leader_trading_rules.md`** 전략 B(변동성 돌파) 섹션에 "재진입 쿨다운 2영업일" 명세 추가
   (전략 E(BFB) L550 "3영업일" 명세 형식 답습).

## 회귀 가드 & Red/Green

**신규 파일 2개** (참조 = `tests/unit/engine/strategies/test_cycle191_cooldown_wiring.py` + `tests/unit/ast/test_cycle191_cooldown_ast.py`):

| # | 테스트 | 파일 | 현행 | Green 후 |
|---|--------|------|------|---------|
| (1) | 쿨다운 활성 → 매수 차단 (HIGH) | strategies | **FAIL** (게이트 부재 → BUY) | PASS |
| (2) | 정상 돌파 → BUY (over-block 0, 불변식) | strategies | PASS | PASS |
| (3) | register 즉시 근사 (today+2+2=4) | strategies | **FAIL** (메서드 부재) | PASS |
| (4a) | refine 성공 → 정확 영업일 교체 | strategies | **FAIL** (메서드 부재) | PASS |
| (4b) | refine 예외 → 근사값 graceful | strategies | **FAIL** (메서드 부재) | PASS |
| (5) | on_position_closed → 쿨다운 등록 (HIGH) | strategies | **FAIL** (override 부재) | PASS |
| (5b) | LS ELECTRIC end-to-end 재진입 차단 (HIGH) | strategies | **FAIL** (미등록 → BUY) | PASS |
| (8) | DEFAULT_PARAMS == 2 | strategies | **FAIL** (키 부재) | PASS |
| (6) | G-VB-NO-DAILY-RESET (HIGH, 불변식) | ast | PASS (메서드/attr 부재 미접촉) | PASS |
| (7a) | BFB=3/VCP=7 값 불변 (SAFETY, 불변식) | ast | PASS ×2 | PASS |
| (7b) | AST on_position_closed → register Call ≥ 1 | ast | **FAIL** (override 부재) | PASS |
| (7c) | AST DEFAULT_PARAMS 리터럴 == 2 | ast | **FAIL** (키 부재) | PASS |

**Red 유효성 실측 (×2 결정론적)**: `9 failed / 4 passed`.
- FAIL 9 = (1)(3)(4a)(4b)(5)(5b)(8) + AST (7b)(7c).
- PASS 4 = (2) 불변식 + (6) NO-DAILY-RESET + (7a) BFB/VCP 불변 ×2 (parametrize).
- test_1 FAIL 사유 검증 = `Signal.BUY == Signal.NONE` (게이트 부재로 BUY 발화 — AttributeError 아님, 올바른 Red).
  test_1 은 `_cooldown_until` 방어적 주입(`if not hasattr`) — 현행(무시)=BUY→Red / Green(소비)=NONE→PASS.
- test_2 = `_cooldown_until` 직접 시드 회피(Green 산물) → "쿨다운 없는 정상 종목 미차단" 불변식으로 작성
  (게이트 over-block 회귀 영구 차단).

## 규약 / 안전성

- freezegun `@freeze_time("2026-07-10 10:00:00")` = today 고정 (쿨다운 날짜 비교 결정성). BFB 191 답습.
- `add_business_days` = AsyncMock (KIS 호출 회피, (4a)(4b)).
- 돌파 픽스처 = 기존 `test_volatility_breakout.py` 패턴 답습 (base 500 / open 80000 / target 80500,
  tick1=80200 기록 → tick2=80500 돌파). `session_tracker._active` frozenset({MAIN}) 강제.
- **매매 안전성**: strategies/ = 8영역 밖. order_engine `on_position_closed` 호출 site 불변
  (사이클 185 배선 재사용, VB override 만 활성화 = 메인 검증에서 order_engine diff 0 확인).
  risk/realtime/auth 무관. `check_exit_signal`/15:20 청산/돌파규칙/DEFAULT_TRADABLE_BOARDS(=main) 불변.

## 의미 전환

**없음.** 기존 테스트 수정 0. VB `_cooldown_until` 은 신규 필드라 기존 단언 충돌 부재.
인접 `test_volatility_breakout.py` 20 PASS 회귀 0 확인.
