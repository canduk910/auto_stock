# cycle238 — donchian 프리장 청산 보류 게이트 08:00 정각 ~30초 구멍 시정 (P1-6, 시정안 A)

작성: team-leader, 2026-09-02. 사용자 결정 "P1-6 은 A 로 진행". **8영역 `src/engine/risk.py` 수정 승인**
— 범위는 `_defers_pre_market_exit` 와 그 판정에 필요한 최소 헬퍼로 한정. 다른 8영역 파일 무접촉.

## 1. 확증된 원인 (Phase 1 — 코드 실측)

| 사실 | 근거 |
|---|---|
| `_defers_pre_market_exit` 는 `session_tracker.active` 만 읽는다 | `src/engine/risk.py:156~174` |
| `active` 의 유일한 기록자는 `SessionTracker.tick()` = `boards_at(datetime.now().time())` | `src/engine/session.py:163~170` (`_active` 대입은 이 한 곳) |
| `tick()` 은 `_session_loop` 가 **30초 주기**로만 호출 | `scheduler.py:1218~1225`, `SESSION_TICK_INTERVAL = 30` (`:79`) |
| H0UNMKO0 는 `_last_nxt_mkop_code` 에만 기록, `active` 미관여 | `session.py:244` |
| 08:00:00 틱은 07:55 사전 구독(H0NXCNT0)으로 즉시 유입 | `scheduler.py:724~757` |
| `boards_at(07:59:xx)` = ∅ ⇒ 08:00:00~08:00:29 동안 `active`=∅ ⇒ 게이트 fail-open | `session.py:63` 스케줄 표 + 실측 로그(08:00:00 청산 → 08:00:29 deferred) |

같은 30초 race 를 2026-05-15 "결함 A" 가 매수측(`_confirm_breakout_open_prices(board=...)`)에서 이미
인지하고 board 명시로 우회했다(`scheduler.py:768~770`). 청산측 게이트는 그 우회를 받지 못했다.

## 2. 시정 설계 (A — 시각 폴백, fail-closed)

### 2.1 판정식

```
whitelist(LTV)                     → False (불변)
by_active = PRE_NXT ∈ active ∧ MAIN ∉ active          # 기존 소스, 판정 불가 시 None
by_clock  = boards_at(_now_kst().time()) 가 PRE_NXT 단독  # 신규 소스, 판정 불가 시 None
defer     = bool(by_active) or bool(by_clock)           # OR — 둘 다 None 이면 False(fail-open 유지)
```

- **스케줄 표 단일 소스**: 시각 폴백은 `08:00`/`09:00` 리터럴을 새로 쓰지 않고 `session.boards_at`
  (tracker 가 쓰는 바로 그 표)을 **fresh 로** 읽는다. `active` 는 이 표의 30초 stale 캐시일 뿐이다.
- **KST 명시**: `_now_kst()` = `datetime.now(_KST)` (`_KST = timezone(timedelta(hours=9))`, `session.py:25`
  관례). naive `datetime.now()` 금지(P2-6 부류). 모듈 함수로 두어 테스트 주입 seam 으로 쓴다.
- **09:00 정각 반대 방향 판단 (team-leader 결정)**: 08:59:59 보류 → 09:00:00 시각은 MAIN 인데 stale
  `active` 가 PRE 를 아직 들고 있는 ≤30초는 **OR 판정이라 보류가 유지**된다 = 현행 라이브 행위와 동일.
  이유 = (a) 이 방향은 안전 방향(평가 지연 ≤30초, 사고 증거 0) (b) 한 사이클에 한 엣지만 바꿔야 D+1
  귀인이 된다 (c) 개장 직후 30초는 스프레드가 가장 넓어 평가 지연이 불리하다고 단정할 수 없다.
  대신 이 구간을 `reason=active_stale_hold` 관측으로 **계량**해 후속 판단 근거를 남긴다.
  clock-primary(09:00:00 정확 해제)는 후속 후보로 워크리스트 등재.
- **fail-open 계약 보존**: 두 소스 모두 판정 불가(예외)일 때만 False. 한쪽만 살아 있으면 그쪽으로.
- **적용 범위 명시(적대 검증 관측)**: `by_active` 가 False 인 **모든** 경우(∅뿐 아니라 stale MAIN/POST 포함)에 시각이 PRE 면 보류. 정상 운영에선 tracker 가 1시간 이상 죽어야 도달하며 방향은 안전(PRE 만 보류, MAIN 은 시각이 평가 재개).
- **불변 계약**: 화이트리스트 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 불변 · 평가 보류이지 주문 보류 아님
  (on_tick 분기 구조 무접촉 — `defer_exit` 소비부 byte 불변) · `tradable_boards` 미독(기존 가드 유지).

### 2.2 관측 — `[pre_market_exit_gate_divergence]`

두 소스가 **갈릴 때만** 1행:
```
[pre_market_exit_gate_divergence] strategy=%s reason=%s active=%s clock_kst=%s
  reason=clock_fallback     : by_clock=True,  by_active=False  ← 08:00 정각 구멍을 시각이 닫음 (D+1 판독 채널)
  reason=active_stale_hold  : by_active=True, by_clock=False   ← 09:00 정각 stale 보류 (계량용)
```
- cap = 1회/(strategy, reason)/일. **날짜 키 자기 리셋**(cycle237 `_emit_breakeven_promote` 패턴:
  `today_key` 비교 → `reset_daily()`) + `reset_daily_state()` 동행 clear.
  **날짜 키 소스 = `_now_kst().date().isoformat()`** (Red 확정 — cycle237 원본은 `datetime.now(KST)` 직독이지만
  cycle238 은 seam 이 있고 T-8 naive-now 가드와 정합해야 한다). 로그 레벨 = **INFO** (T-9c 가 계약으로 봉인).
- ⚠️ 판독 한계: on_tick 이 `pos is not None and ...` 단락 평가라 divergence 는 **보유 포지션 틱에서만** 계량된다.
  `reason=clock_fallback` 부재는 "구멍 없음" 과 "그 창에 보유 종목 틱 없음" 을 구분하지 못한다.
- **peek → 로그 → mark** (mark-before-log 금지). 예외 전부 흡수 — 관측 실패가 판정을 바꾸지 않는다.
- hot path — `logger` 만. `write_log`/DB/`await` 금지(A-1 관례).
- 기존 `[pre_market_exit_deferred]`(1회/전략/일)는 **서식·cap 무변경**. D+1 판독 = 이 마커의 첫
  타임스탬프가 08:00:0x 로 당겨지고, 같은 시각에 `reason=clock_fallback` 이 동반되면 구멍이 닫힌 것.
  `도치안 시간 기반 청산` 첫 발화가 09:00 이전이면 여전히 결함.

### 2.3 테스트 결정성 seam (tests/conftest.py)

시각 폴백은 벽시계 의존을 **불가피하게** 도입한다(08:00:00 라이브와 단위 테스트 기본 상태가 둘 다
`active`=∅ 라 `active` 만으로는 구분 불가). 기존 on_tick 테스트 11+ 파일이 08:00~09:00 KST 실행 시
흔들리지 않도록:
- 루트 `tests/conftest.py` 에 autouse 픽스처 `_pin_pre_market_clock` — `risk._now_kst` 를
  `2026-01-05 10:30:00+09:00`(MAIN, 프리장 밖)로 핀. 사이클 202 `_neutralize_call_auction_gate` 동형.
- 옵트아웃 마커 `@pytest.mark.real_pre_market_clock` (pyproject `markers` 등록 필수 —
  `filterwarnings = error` 라 미등록 마커는 곧 실패).
- 게이트를 직접 검증하는 테스트는 `monkeypatch.setattr(risk, "_now_kst", lambda: <KST datetime>)` 로
  시각을 명시한다(픽스처보다 뒤에 적용되므로 이긴다).

## 3. Red 테스트 목록 — `tests/unit/engine/test_cycle238_pre_market_clock_gate.py`

리그는 `test_risk_pre_market_exit_gate.py` 의 `_SpyStrategy`/`_rig` 를 import 해 재사용(중복 금지).
`(현행 FAIL)` 표시가 없는 항목은 회귀 가드 — 현행에서도 통과해야 하며 그 사실을 Red 보고에 명시.

| ID | 시나리오 | 기대 |
|---|---|---|
| T-1 **(현행 FAIL — 핵심)** | clock 08:00:00 KST, `active`=∅(07:59 stale), donchian 보유, 급락 틱 | `exit_calls == []`, `execute_sell` 미호출, `high_since_buy` 불변 |
| T-2 (현행 FAIL) | T-1 조건 5틱 | `[pre_market_exit_deferred]` 정확 1회 **+** `[pre_market_exit_gate_divergence] ... reason=clock_fallback` 정확 1회, 메시지에 `active=` `clock_kst=` 포함 |
| T-3 (현행 부분 FAIL) | clock 08:59:59 + active=∅ → 보류 / clock 09:00:00 + active={MAIN} → 평가 | 경계는 `boards_at` 표 그대로 (08:59:59 case 가 현행 FAIL) |
| T-4 (현행 부분 FAIL) | clock 09:00:00 + active={PRE_NXT}(stale) | **보류 유지**(OR) + `reason=active_stale_hold` 1회 (마커가 현행 FAIL) |
| T-5 | clock 08:30 + active=∅, LTV | 평가 1회 + 매도 1회 (화이트리스트 불변) |
| T-6 (현행 FAIL) `@real_pre_market_clock` (T-7·T-8 도 동일 마커 — autouse 픽스처가 `raising=False` 로 seam 을 생성하므로 존재/소스 검사는 옵트아웃 필수) | `risk._now_kst()` 실함수 | tz-aware, `utcoffset() == 9h` |
| T-7 (현행 FAIL) | `_now_kst` 가 raise + active=∅ → False / raise + active={PRE} → True / `session_tracker.active` 도 raise(property monkeypatch) → False | fail-open 계약 + 한쪽 생존 시 그쪽 |
| T-8 (현행 FAIL) 소스 가드 | `_defers_pre_market_exit` 와 신규 헬퍼 소스 | `tradable_boards` 0건(기존) · `boards_at` 사용 · `time(8`/`"08:00"`/`"09:00"` 리터럴 0건 · AST: `now` 호출에 인자 0개인 곳 0건(naive 금지) · `await`/`write_log` 0건 |
| T-9 (현행 FAIL) cap | (a) 날짜 키가 바뀌면 divergence 재발화 (b) `reset_daily_state()` 후 재발화 (c) `logger.info` 가 raise 하면 cap 미소비(다음 틱에 다시 시도) **이고** 그 틱의 게이트 판정은 여전히 True | peek→로그→mark, 관측 실패 ≠ 행위 변화 |
| T-10 | 픽스처 계약 | 기본 상태 `boards_at(risk._now_kst().time()) == {MAIN}` (기존 테스트 무영향의 근거) |
| T-11 (현행 FAIL) `@real_pre_market_clock` | freezegun `freeze_time("2026-09-02 08:00:00+09:00")` + active=∅ + donchian | 보류 — 실 seam 이 frozen 벽시계에서 동작 |
| T-12 | 기존 `test_risk_pre_market_exit_gate.py` 13건 | 전부 그대로 PASS (OR 판정이라 `active`=PRE 케이스 의미 보존). 모듈 docstring 의 "wall-clock 아님" 문구만 새 계약으로 정정 |

## 4. Green 범위

- `src/engine/risk.py`: 상단 import `MarketBoard, boards_at` 추가 · `_KST`/`_now_kst()`/
  `_pre_market_only_by_clock()` 모듈 헬퍼 · `_defers_pre_market_exit` 재구성(§2.1) ·
  `_maybe_emit_pre_market_gate_divergence` 메서드 + `__init__` 상태(`DailyEmitCap[tuple[str,str]]`
  + `_..._day: str`) + `reset_daily_state()` 동행 clear. on_tick 본문·`_maybe_emit_pre_market_defer` 무접촉.
- `tests/conftest.py` autouse 픽스처 + `pyproject.toml` 마커.
- 8영역 sha 핀: `shasum -a 256 src/engine/risk.py` 를 `test_cycle223_ast_donchian_exit_fix.py`
  (`_PREEXISTING_CONTENT_SHA`) · `test_cycle223f_ast_manual_apply_safeguard.py` (동일) ·
  `test_cycle226_zero_breakout_defense.py` (`_ALLOWED_CONTENT_SHA`) 에 cycle238 주석과 함께 등록.
  `test_cycle222a3_ast_followup_fixes.py` 는 `_ALLOWED` 파일명에 risk.py 가 영구 포함이라 핀 불필요.
  세 dict 의 cycle235 항목(handler/order_engine/realtime CLAUDE.md)은 커밋 f2b831f 로 자기소멸한
  죽은 값 — TODO 대로 삭제(청소, 행위 무관). 등록 후 뮤테이션(risk.py 1 byte 변조 → 3 가드 FAIL → 원복)
  실증을 보고에 남긴다.

## 5. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| m1 | `by_clock` 항 제거(현행 환원) | T-1/T-2/T-3/T-11 FAIL |
| m2 | OR → AND | T-1 FAIL |
| m3 | clock-primary(`active` 무시) | T-4 FAIL |
| m4 | mark-before-log | T-9(c) FAIL |
| m5 | `boards_at` 대신 `time(8,0)<=t<time(9,0)` 리터럴 | T-8 FAIL |
| m6 | `_datetime.now()` naive | T-6/T-8 FAIL |
| m7 | 화이트리스트 검사 뒤로 이동/제거 | T-5 FAIL |
| m8 | divergence 판정에 예외 흡수 제거 | T-9(c) FAIL |

추가 렌즈: hot path 비용(`_now_kst` 호출 ≤ 수 µs, 보유 전략 수만큼) · 3,000틱 차분으로 `active`
정상 갱신 상태(PRE 창 안팎)에서 판정 결과가 현행과 **동일**함 실증(행위 변경은 두 소스가 갈리는
08:00:00~29 / 09:00:00~29 창에서만) · autouse 픽스처가 게이트 직접 검증 파일에서 monkeypatch 로
정상 override 되는지.
