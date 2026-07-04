# 사이클 191 Red 작업 지시서 — BFB/VCP 재진입 쿨다운 고아 배선 (영업일 2단계 등록)

출처: 사이클 185 인계 A-4 (MEDIUM 매매 행위). 자문 `_workspace/domain_consult/cycle191_reentry_cooldown_wiring.md` + 사용자 결정 2건.

## 결함
`register_cooldown_after_exit` (BFB `bull_flag_breakout.py:965` days=3 / VCP `vcp_breakout.py:1070` days=7) **production 호출처 0건 (고아)** — 매수 게이트(`check_buy_signal` 의 `if cd_until and cd_until >= today: return NONE`, BFB L812/VCP L963)는 살아있으나 등록이 없어 도입 이래 재진입 쿨다운 무력. 청산 종목 당일/익일 재돌파 시 즉시 재매수 (whipsaw 무방비).

## 사용자 결정 + 자문 채택
- **청산 유형 무구분 일괄** (손절/익절/강제청산/수동 HTS 매도 전부) — 훅 시그니처 불변
- **영업일 2단계 등록**: 즉시 달력일 근사(days+2) → chk-holiday(CTCA0903R, 기존 통합 TR — `condition.py` `is_market_open`/`next_trading_day` 재사용 계열) 1회로 정확한 N영업일 정정. **BFB 3/VCP 7 값 불변** (의미 = 영업일 확정, docstring "3영업일" 원문 정합 — DEFAULT_PARAMS 변경 0 = 00_leader_rules 동기화 불요)
- 배선 = 사이클 185 `on_position_closed` 훅 (order_engine 2 site 계약 불변)
- 재시작 휘발 허용(영속화 별건 인계) / `_cooldown_until` 일일·prepare 리셋 절대 금지 / 부분익절 잔량 보유 중 미발화 = registry 차단과 정합

## Green 계약

### 1. `src/api/condition.py` — `add_business_days(base_date, n) -> date` 신규
- `next_trading_day` 패턴 답습: `kis_get_quote(HOLIDAY_URL, "CTCA0903R", {"BASS_DT": base+1일, ...})` 1회 → 응답 output(~30일치)에서 `opnd_yn=="Y"` row 를 순서대로 세어 **n번째 개장일 date 반환** (n≤7 이면 30일 응답으로 충분)
- 실패/부족 시 fallback = `base_date + timedelta(days=n + 2)` (주말 마진 근사) + `logger.exception` graceful — `next_trading_day` 실패 처리 답습

### 2. BFB/VCP — 2단계 등록
- `register_cooldown_after_exit(ticker)` 수정: 즉시 근사 `_cooldown_until[ticker] = today + timedelta(days=days + 2)` (재매수 공백 0 보장). docstring = "영업일 의도 + 2단계 정정" 명시
- 신규 `async def _refine_cooldown_business_days(self, ticker)`: `add_business_days(today, days)` 호출 → 성공 시 `_cooldown_until[ticker]` 정확값으로 교체 (ticker 가 dict 에 없으면 no-op) + 예외 전체 graceful (근사값 유지)
- `on_position_closed(ticker)` 배선:
  - BFB: 기존 override(`_partial_exit.pop` — **보존 의무**)에 `self.register_cooldown_after_exit(ticker)` + `asyncio.create_task(self._refine_cooldown_business_days(ticker))` 추가. create_task 는 try/except RuntimeError (이벤트 루프 없는 테스트/스텁 환경 graceful — 근사값 유지)
  - VCP: override **신설** (register + create_task 만)
- 게이트 코드(check_buy_signal 비교) **불변** / `_handle_sell_fill`·`execute_sell` 등 order_engine **변경 0**

## Red 테스트

### `tests/unit/api/test_cycle191_add_business_days.py` (~4)
- B-1: 30일 mock 응답(주말+공휴일 포함)에서 n=3 → 정확한 3번째 개장일 (주말 스킵 검증)
- B-2: n=7 (VCP) 정확성
- B-3: KIS 실패 → fallback `base + n + 2` 달력일
- B-4: 응답에 개장일 부족(<n) → fallback

### `tests/unit/engine/strategies/test_cycle191_cooldown_wiring.py` (~8)
- C-1 (HIGH): BFB `on_position_closed` → `_cooldown_until[ticker]` 즉시 세팅 (today + days+2)
- C-2 (HIGH): VCP 동일 (override 신설 확인)
- C-3 (HIGH): BFB 기존 `_partial_exit.pop` **보존** (사이클 185 계약)
- C-4: refine 성공 → dict 가 정확 영업일 date 로 교체
- C-5: refine 실패(KIS 예외) → 근사값 유지 graceful
- C-6 (HIGH): 등록 후 `check_buy_signal` = NONE (게이트 최초 실효 end-to-end — 돌파 조건 충족 합성 틱에서도 쿨다운이 차단)
- C-7: 쿨다운 만료(cd_until < today) 후 매수 신호 정상 (freezegun 또는 date 주입)
- C-8: 이벤트 루프 없는 환경에서 on_position_closed graceful (근사값은 세팅됨)

### `tests/unit/ast/test_cycle191_cooldown_ast.py` (~3)
- A-1 (HIGH, G-191-NO-DAILY-RESET): BFB/VCP `_reset_daily_state`·`prepare` 본체에 `_cooldown_until` clear/재대입 0건 (multi-day 상태 영구 보호)
- A-2: `on_position_closed` 내 `register_cooldown_after_exit` 호출 존재 (BFB+VCP, 고아 재발 영구 차단)
- A-3: order_engine `on_position_closed` 호출 site 정확히 2곳 불변 (사이클 185 G2 답습 — 기존 가드 중복이면 참조만)

## Red 유효성
현재 코드: C-1/2/3(pop 은 PASS 가능하니 register 부분으로 FAIL 유도)/4/6 + A-2 + B-* (함수 부재 ImportError) FAIL, A-1/C-7 등 불변식 PASS 허용.

## 주의
- freezegun 사용 시 asyncio.sleep/모듈 경계 주의 (사이클 187 교훈 — KIS mock 은 respx 또는 kis_get_quote patch, DB 미접촉)
- 기존 BFB/VCP 테스트(strategies 434) 회귀 금지 — on_position_closed 기존 케이스가 create_task 로 RuntimeWarning 나면 loop 처리 확인
- 매매 안전성 8영역 diff 0 의무 (변경 = condition.py + strategies 2 + 테스트만, order_engine 절대 불변)
