# cycle276 — AI 매수평가 **주문 발화 시점** 이동 + 전용 테이블 영속화 + 거래기록 UI 팝업 (Red 명세)

- 작업 디렉터리 = `/Users/koscom/Projects/auto_stock_wt276` (브랜치 `cycle276-order-time-llm`, base `34ba9e6`)
- 정본 입력 = 공통 브리프(`scratchpad/cycle276_brief.md`) §3 설계 결정 10개 · 이해 A/B/C 3건 ·
  자문 `_workspace/domain_consult/cycle276_order_time_llm_20260911.md`
- **매매 행위 변경 0.** 주문이 KIS 에 접수된 **뒤**에 평가가 붙는다. 주문을 막지도, 늦추지도, 바꾸지도 않는다.
- 접촉 허용 8영역 = `src/engine/order_engine.py` **단 하나**(사용자 명시 승인). A-ATOMIC 구간 무접촉.
- `enforce` 는 이 사이클에 **구현하지 않는다**. `llm_gate_mode` 는 `off|shadow` 2종 유지.

---

## 0. 이 사이클이 바꾸는 것 / 안 바꾸는 것

| | 대상 | 내용 |
|---|---|---|
| 바꾼다 | `src/engine/order_engine.py` | import 1줄 + 훅 2곳(주 경로·지정가 폴백). 각 훅 = `try` / `observe_order(...)` 1문 / `except Exception` / `logger.debug` |
| 바꾼다 | `src/engine/llm_buy_gate.py` | 진입점 `observe_order` 신설(구 `observe_signal` **삭제**), 래치 키 → 주문번호, `_persist_evaluation` 1곳, 마커 5종 |
| 바꾼다 | `src/engine/llm_features.py` | `_SNAPSHOT_KEYS`/`build_messages` 의 `signal_kst` → `order_kst`, 판단축 문면 "주문 접수 시각" 으로 정직화 |
| 바꾼다 | `src/engine/strategies/{volatility_breakout,long_tail_volatility}.py` | cycle274 훅 **제거**(호출 블록 + `llm_buy_gate` import). `DEFAULT_PARAMS` 4키는 **유지** |
| 신설 | `supabase/migrations/043_llm_buy_evaluations.sql` · `src/db/llm_buy_evaluations.py` · `src/routes/llm_evaluations.py` | |
| 바꾼다 | `src/db/trade_history.py::get_trade_pairs` | `buy_order_nos`/`sell_order_nos`/`pair_key` 3키 **추가**(사영만) |
| 바꾼다 | `src/main.py` | 라우터 import + `include_router` 각 1줄 |
| 신설/바꾼다 | 프론트 | `LlmEvaluationModal.tsx` · `api/llm-evaluations.ts` · `types/trading.ts`·`types/llm-evaluation.ts` · 두 그리드 · MSW · E2E 목 · `e2e/history.spec.ts` |
| **안 바꾼다** | `risk.py`·`session.py`·`scanner.py`·`strategy_registry.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`·`scheduler.py`(3,872L)·`strategy_base.py`·전략 5파일 | **byte 동일** |
| **안 바꾼다** | `src/routes/history.py` | 0줄(§9.4 근거). 문서만 갱신 |

**시각 의미 이동 경고(영속)** — 이 사이클 이후 `[llm_buy_score]` 의 시각·지연·표류 필드는
*신호 시각* 이 아니라 **주문 접수 시각** 기준이다. `slip_bp` 는 부호 의미가 반전되어
**`post_order_drift_bp` 로 개명**한다. **배포 전후 로그를 합산하지 말 것**(cycle228 `would_pass`·
cycle263 `skipped_fresh` 와 같은 계열의 사고).

---

## 1. 계약 (C1..C41)

### 1-A. 행위 0 을 기계로 증명하는 계약 (최우선)

- **C1** — `order_engine.py` 의 훅은 **`ast.Expr` statement** 다. 반환값을 변수에 대입하지 않고
  `await` 하지 않으며 `if`/`return`/`raise` 의 피연산자가 되지 않는다. 훅 statement 는 정확히 **2개**.
- **C2** — 두 훅 각각은 자신의 `try: ... except Exception: logger.debug(..., exc_info=True)` 흡수기
  **안**에 있다. 그 `except` 핸들러 본문에는 `raise`·`return`·상태 변경문이 없다.
- **C3** — 훅이 어떤 예외를 던져도(`observe_order` 를 raise 하도록 monkeypatch)
  `execute_buy` 의 관측 가능한 결과가 **동일**하다: 반환값 `None` · `state.pending_buys` ∋ ticker ·
  `state.pending_buy_amounts[ticker]` 값 동일 · `_order_qty`/`_order_strategy`/`_order_ticker`/
  `_pending_buy_orders` 4매핑 동일 · `insert_trade` 호출 인자 동일 · `state.cached_buyable_at == 0.0`.
  **폴백 경로에서 non-`KisApiError` 를 던져도 같다**(그 훅은 `except KisApiError` 핸들러 안 중첩 try
  안이라 형제 핸들러가 못 잡는다 — 자문 CRITICAL).
- **C4** — `place_order` 호출 인자(`ticker`/`side`/`quantity`/`price`/`exchange`/`order_division`)가
  cycle274 시점과 **동일**하다. 훅은 `place_order` **뒤**에만 존재한다(같은 `try` 안 `place_order`
  이전 라인에 훅 0건).
- **C5** — **A-ATOMIC byte 동일**: `calc_buy_quantity` 호출문(`:313`)부터 `state.pending_buys.add(ticker)`
  (`:354`)까지의 소스 세그먼트 sha256 이 base 와 일치하고, 그 구간 `ast.Await` 0건.
  ⚠️ 브리프 §1·§5 의 좌표 `:272~:314` 는 stale — **현행은 `:313~:354`**(이해 A). 가드는 리터럴이 아니라
  `tests/unit/ast/test_budget_limit_ast.py:63~95` 와 같은 AST 동적 계산을 쓴다.
- **C6** — **매도 경로 훅 0건**: `execute_sell` 본문(`:540~`)·손절 잔여 재주문(`:1576~`)·취소 경로의
  `place_order` 뒤에 `llm_buy_gate.*` 호출 0건. `OrderSide.SELL` 인자를 갖는 `place_order` 호출과
  같은 `try` 블록 안에 훅이 없다.
- **C7** — 훅 자리는 **`_pending_buy_orders[result.order_no] = {...}` 대입문 직후**이고,
  `already_completed`(주 경로) / `result.order_no in self._completed_orders`(폴백) 판정문 **앞**이다.
  AST 로 lineno 순서를 검증한다: `mapping_assign.lineno < hook.lineno < completed_check.lineno`.
  **INSERT 뒤로 옮기면 체결통보 선행 코호트가 통째로 빠진다**(자문 R9, 09-09 034020·09-10 004990 실측).
- **C8** — 훅과 `_insert_pending_buy_or_absorb_race` 사이에 `await` 0건. 훅 statement 자체에 `await` 0건.
  훅 인자식에 `await`·`asyncio.*`·`pg.*`·`httpx`·`fetch` 0건.
- **C9** — 훅은 `pending_buys`·`pending_buy_amounts`·`positions`·`_order_*` 매핑·`_completed_orders`
  중 어느 것도 **변경하지 않는다**(읽기만). AST: 훅 인자식 안에 `ast.Call` 중 `add`/`pop`/`discard`/
  `update`/`clear`/`append` 이름 0건, `ast.Subscript` 의 Store 컨텍스트 0건.
- **C10** — `order_engine.py` 의 **모듈 최상단 `src.*` import 증가분은 정확히 1**
  (`from src.engine import llm_buy_gate`). `observer_trace`·`settings`·`db.llm_buy_evaluations` 는
  order_engine 이 import 하지 않는다(계좌·기록은 leaf 책임).
- **C11** — 전략 2파일의 `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` **6개 메서드
  세그먼트 sha 가 cycle272 값(= `test_cycle274_ast_llm_gate.py::_BASE_METHOD_SHA` 6값)과 전부 일치**한다.
  즉 `("vb","check_buy_signal") = e620ae0d…`, `("ltv","check_buy_signal") = fb1e7460…` **복귀**.
- **C12** — 전략 2파일 어디에도 `llm_buy_gate` 문자열이 없다(import·호출 0건). 반면
  `DEFAULT_PARAMS` 의 4키(`llm_gate_mode`/`llm_gate_min_score`/`llm_gate_daily_call_cap`/
  `llm_gate_timeout_secs`)는 **VB·LTV 두 파일에만, 그대로** 존재한다.
- **C13** — 8영역 나머지 + `scheduler.py` + `strategy_base.py` + 전략 5파일 **byte 동일**
  (`test_cycle274_ast_llm_gate.py::_BASE_SHA` 재활용, `order_engine.py` 항목만 새 값으로 재핀).
  `scheduler.py` 라인 수 **3,872** 불변, cycle257 상한(<3,900) 리터럴과 자동 대조.
- **C14** — 8영역 diff 가드(`test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`)에
  `src/engine/order_engine.py` 의 **내용 sha 1건**을 등록한다(승인 사이클 한시 면제). 헤더에
  "TODO(cycle276 커밋 후): 비운다" 를 남긴다. 다른 8영역 파일은 등록하지 않는다.
- **C15** — 자매 핀 4곳 규약: `test_cycle264_scope_and_pins.py::_STRATEGY_PINS` 6핀을 cycle272 값으로
  **되돌리고**, `test_cycle223_ast_donchian_exit_fix.py::_CYCLE228_STRATEGY_CONTENT_SHA` 의 VB·LTV
  **파일 sha 는 현재값으로 재핀**한다(4키가 남으므로 cycle272 파일 sha 와는 다르다 — 메서드 핀만 복귀).
  `test_g3_9*`("핀은 항상 4곳")가 이 대칭을 강제한다.
- **C16** — 훅이 도는 전략이 `llm_gate_mode` 키를 갖지 않으면(momentum·donchian·BFB·VCP·kojiro)
  `asyncio.create_task` **0건** · DB 기록 **0행** · `[llm_buy_score]`/`[llm_buy_score_failed]`/
  `[llm_eval_persist]` **0행**. (단 `[llm_gate_config] mode=off` 카나리아는 **발화한다** — mode 판정
  앞이 그 카나리아의 자리다. 로그 표면만 5전략만큼 확장되고 행위·비용은 0. §13 기준선 재설정 항목.)

### 1-B. leaf 계약

- **C17** — `observe_order` 는 **동기 · never-raise · 반환 항상 `None`**. 본문 전체가
  `try/except Exception` 으로 감싸이고 except 는 `trace_observer_failure` 후 `return None`.
- **C18** — `observe_order` 안에 `await`/`async for`/`async with` 0건, `pg.`/`httpx`/`requests`/
  `fetch(` 0건. `asyncio.create_task` **정확히 1회**.
- **C19** — 비용 순서(cycle274 §5.2 이식, `test_c5_5` 계열 유지):
  `mode 판정` → `[llm_gate_config]` 카나리아(mode 판정 **앞**) → `order_no` 유효성 → 래치 peek →
  일일 cap peek → **값 복사** → 래치 mark + cap 증가 → `create_task` → `return None`.
  래치 `mark_emitted` 는 `create_task` **앞**이다.
- **C20** — **래치 키 = `str(order_no)`**(구 `(strategy_id, ticker)` 폐기). `KstDailyEmitCap` 이므로
  자정 자기 리셋. 같은 종목을 하루 두 번 사면 주문이 둘이라 **두 번 평가**한다.
- **C21** — `order_no` 가 `""`/`None`/공백이면 **평가하지 않는다**: `create_task` 0건 · DB 0행 ·
  `[llm_eval_persist] result=error reason=empty_order_no` **1행만** 남긴다(자문 R2 — 무음 금지).
- **C22** — leaf 는 8영역 모듈을 import 하지 않는다. `src.engine.session`·`src.engine.risk`·
  `src.engine.order_engine`·`src.engine.strategy_registry`·`src.realtime`·`src.auth`·`src.api.order`
  문자열이 leaf 소스에 **0건**(`test_c17_4` 유지). ⇒ **보드는 `session` 으로 풀지 않는다.**
  `board` 는 leaf 내부 순수 함수 `_board_by_clock(order_kst)` 가 시계만으로 낸다
  (`pre_nxt` [08:00,09:00) · `main` [09:00,15:30) · `post_nxt` [15:30,20:00) · 그 외 `off_hours`).
  `scanner` 는 기존 선례대로 **함수 내 지연 import** 만 허용(read-only).
- **C23** — leaf 는 전략 객체·`_targets`·`config.params` **원본**을 참조하지 않는다. 넘어오는 것은
  값 복사뿐이고, `buy_signals_tail` 은 `dict(d)` 로 다시 복사해 primitive 키만 읽는다.
- **C24** — `_persist_evaluation` 호출 사이트는 **정확히 1곳**이고 `_evaluate` 안에 있다.
  `_evaluate` 는 `_evaluate_core` 의 outcome dict 를 받아 그 1곳에서 upsert 한다.
  성공(9종 실패 사유 아님)·실패(9종 전부) **모두** 1행을 남긴다.
- **C25** — `_persist_evaluation` 은 never-raise 이며 결과를 `[llm_eval_persist] order_no=… result=ok|error`
  **1행**으로 남긴다(`result=error` 면 `reason=` 에 예외 종류를 짧게). 이 마커가 DB 무음을 깨는 유일한 채널.
- **C26** — 마커 5종(`[llm_buy_score]`·`[llm_buy_score_failed]`·`[llm_gate_config]`·
  `[llm_gate_daily_cap]`·`[llm_eval_persist]`)은 **leaf 안에서만** 로깅된다
  (`test_g1_4_markers_live_only_in_the_leaf` 를 5종으로 확장).
- **C27** — `[llm_buy_score]`/`[llm_buy_score_failed]` 에 **`order_no=` 필드 추가**.
  `[llm_buy_score]` 의 `slip_bp=` → **`post_order_drift_bp=`** 로 개명하고 `signal_kst=` → `order_kst=`,
  `signal_price=` → `order_price=` 로 정직화한다. `slip_bp` 문자열은 소스 전체에서 **0건**.
- **C28** — 실패 9종 어휘(`timeout`/`api_error`/`parse_error`/`schema_error`/`no_bars`/`no_key`/
  `cap_exceeded`/`disabled_model`/`payload_error`) 불변 + `empty_order_no` 는 **평가 어휘가 아니라
  persist 어휘**로 분리(§C21). `_FAILURE_REASONS` 튜플은 9종 그대로.
- **C29** — `_parse_score_response` 가 돌려준 `key_risks`/`invalidations` 를 **버리지 않는다**
  (cycle274 는 `_risks, _invalids` 로 버렸다). outcome 에 실어 DB 에 저장한다. **로그 서식은 불변**
  (20:10 파서 기준선 보호 — DB 에만 싣는다).
- **C30** — `prompt_version` = `sha256(SYSTEM_PROMPT + user 템플릿 문자열)[:12]`,
  `feature_version` = `sha256("|".join(sorted(compute_technicals 출력 키)))[:12]`. 둘 다 leaf 가
  **모듈 로드 시 1회** 계산해 캐시하고, 계산 실패는 `""`(fail-open, 평가는 계속).

### 1-C. DB·라우트 계약

- **C31** — 마이그레이션 043 은 **가산형**: `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
  4개 + `COMMENT ON` 만. 기존 테이블·컬럼·인덱스를 건드리는 문장 0건(`ALTER`/`DROP`/`UPDATE`/`DELETE` 0건).
  **deploy.yml 이 매 push 마다 전 마이그레이션을 재적용하고 오류를 삼키므로 idempotent 가 아니면
  운영에 테이블이 없는 채로 조용히 실패한다**(042:5-6 명문).
- **C32** — PK = `(trade_date, account_no, ticker, order_no)`. `order_no` 는 `TEXT NOT NULL DEFAULT ''`
  (enforce 차단 평가 전방 호환). 4열 모두 NOT NULL.
- **C33** — `eval_kind TEXT NOT NULL DEFAULT 'order'` (`'order'|'blocked'`) — 운영 DB 에 이미 존재하는
  `order_no=''` 체결 행과 미래의 "차단된 평가" 가 같은 PK 공간을 쓰는 충돌을 **지금** 분리한다(자문 R2).
  이번 사이클은 `'order'` 만 쓴다.
- **C34** — asyncpg 바인딩 규약(`src/db/CLAUDE.md:18~24`, 신규 CRUD 의무):
  **DATE** 은 `_kst.to_date(...)` · **TIMESTAMPTZ** 는 `datetime.fromisoformat(now_kst_iso())`(aware
  datetime) · **JSONB** 는 raw dict/list 를 그대로 바인딩(호출부 `json.dumps` 금지) ·
  `.in_` 은 `= ANY($1::text[])` · NUMERIC 은 `Decimal` 반환.
  ⚠️ `now_kst_iso()`(str)를 TIMESTAMPTZ 에 넘기면 mock 은 전건 초록인데 실 PG 에서만 `DataError`
  (cycle273a HIGH#1 재현 경로).
- **C35** — `input_payload` 는 **JSON 직렬화 안전한 사영**이다. leaf 의 payload dict 는
  `now_kst`(datetime)를 담고 있으므로 `_json_safe()` 로 datetime→`isoformat()`, `Decimal`→`float`,
  `set`→`list` 변환한 뒤 저장한다. 실패 기록 경로에서도 같은 사영을 쓴다(**관측이 관측을 막지 않게**).
- **C36** — `input_payload` 는 `build_messages` 에 실제로 들어간 **세 인자 그대로**:
  `{"payload": <사영된 payload>, "tech": <tech dict>, "bars30": <bars[:30]>}`. **요약·절단 금지.**
  프롬프트가 아직 조립되지 못한 실패(`no_bars`/`payload_error` 등)는 확보된 만큼만 담고
  `"tech": {}`/`"bars30": []` 로 남긴다.
- **C37** — 신규 라우트는 인증 코드를 **한 줄도 쓰지 않는다**. `ApiAuthMiddleware` 가 최외곽에서
  `/health` 를 뺀 전 경로를 지킨다. `EXEMPT_PATHS` 를 **늘리지 않는다**. 테스트는
  `tests/conftest.py::_neutralize_api_auth` seam 하나만 쓴다.
- **C38** — 오류 분리(cycle266 정본): DB 예외 → `logger.exception("[llm_eval_route_error] …")` +
  **HTTP 500**. 결과 없음 → **HTTP 404**(단건) / **200 + 빈 맵**(배치). `except Exception: rows=[]`
  형태의 fail-silent **금지**.
- **C39** — 계좌번호는 **저장은 원문, 응답은 마스킹**. 마스킹은 **라우트 응답 조립 시점**에 걸고
  db 모듈은 원문을 반환한다. 신규 헬퍼 `mask_account_no(s)` — **앞 4자리 + `****`**
  (브리프 §3.6). 빈 값·8자 미만은 전체 `****`(길이 누출 방지). 기존 `mask_secret`(뒤 4자리)을
  **재사용하지 않는다**(두 관례를 섞지 않기 위해 이름·모듈 분리).
- **C40** — `input_payload` 에 계좌번호를 **넣지 않는다**(PK 열로 충분). 리포터 키가 GET/HEAD 를
  경로 무관 통과시키므로(cycle249) 응답 표면에 원문이 실릴 경로를 원천 차단한다.
- **C41** — `get_trade_pairs` 의 **기존 15키 이름·타입·값 불변**, 페어링 알고리즘(그룹 키·시간
  오름차순·누적 0 emit·가중평균·open 1행·정렬) **한 글자도** 바꾸지 않는다.
  추가는 `buy_order_nos`/`sell_order_nos`/`pair_key` 3키뿐이고, 버퍼 튜플 **arity 를 늘리지 않는다**
  (병행 리스트로 구현 — 4-튜플 전환은 언패킹 5곳 이상 동시 수정이라 한 곳만 놓쳐도 매매손익 뷰가 500).

---

## 2. 마이그레이션 `supabase/migrations/043_llm_buy_evaluations.sql` (전문)

```sql
-- cycle276 (2026-09-11) — AI 매수평가(LLM shadow) 주문 시점 기록 전용 테이블.
--
-- 배경: cycle274 는 `check_buy_signal` 의 `return Signal.BUY` 직전(= 신호 시점)에서
-- 평가를 던졌다. 신호 10건 중 실제 주문은 5건(50%)이라 점수 절반이 실현손익에 붙지
-- 않았고, 래치가 (전략, 종목)/일 이라 12:06 첫 신호의 점수가 15:13 주문에 붙는 사례
-- (09-10 000990)까지 생겼다. cycle276 은 훅을 `order_engine.execute_buy` 의
-- `place_order` 성공 직후로 옮겨 **주문 1건 = 평가 1행**을 만든다.
--
-- PK (trade_date, account_no, ticker, order_no) — KIS ODNO 는 **하루 단위로만** 유일하다
-- (`order_engine.reset_daily_state` docstring). 그래서 날짜가 PK 선두에 있어야 하고,
-- trade_history 조인도 (trade_date, ticker, order_no) 3축이어야 안전하다.
-- order_no 는 TEXT NOT NULL DEFAULT '' — 향후 enforce 로 "차단되어 주문이 없는 평가"를
-- 같은 PK 로 수용하기 위한 전방 호환이며, 그 경우를 지금 있는 order_no='' 수기 체결 행과
-- 구분하려고 eval_kind('order'|'blocked') 열을 처음부터 둔다.
--
-- 회고분석 전제(사후 복원 불가라 지금 넣는다):
--   prompt_version/feature_version  — 프롬프트·지표가 바뀐 전후 행을 섞어 회귀하면 안 된다
--   budget_remaining_after_won/open_positions_n — 차단의 반사실은 "손익이 사라진다"가
--     아니라 "다른 종목 매수로 대체된다" 일 수 있다. 그 구분에 필요하다
--   raw_response — 파싱 실패 재분류 + 다른 파서로 재판독
--   input_payload — build_messages 세 인자 그대로. 훗날 다른 모델로 오프라인 재채점
--   order_kst/evaluated_at/eval_to_order_lag_ms — enforce(선평가)로 가면 "얼마나 묵은
--     점수로 샀는지" 를 재야 한다
--
-- 매매 안전성: 이 테이블은 주문이 KIS 에 접수된 **뒤** 기록되는 관측 계층이다.
-- 쓰기는 전부 `asyncio.create_task` 안 never-raise 경로이고 매매 hot path 무관.
--
-- IF NOT EXISTS 는 deploy.yml 이 매 push 마다 전 마이그레이션을 재적용하고
-- ON_ERROR_STOP=0 + `|| true` 로 오류를 삼키기 때문에 **필수**다(031·042 선례).
--
-- ⚠️ 번호 재배정: cycle275(입출금 T+2) 명세도 043 을 예약했었다 — cycle276 이 043,
--    cycle275 는 044 로 재배정한다.

CREATE TABLE IF NOT EXISTS llm_buy_evaluations (
    -- ---- PK 4열 -------------------------------------------------------
    trade_date              DATE        NOT NULL,
    account_no              TEXT        NOT NULL,
    ticker                  TEXT        NOT NULL,
    order_no                TEXT        NOT NULL DEFAULT '',

    -- ---- 분류 ---------------------------------------------------------
    eval_kind               TEXT        NOT NULL DEFAULT 'order',
    account_product         TEXT,
    strategy_id             TEXT        NOT NULL,
    mode                    TEXT        NOT NULL,
    result                  TEXT        NOT NULL,
    reason                  TEXT,

    -- ---- 평가 결과 -----------------------------------------------------
    score                   INTEGER,
    min_score               INTEGER     NOT NULL,
    would_block             BOOLEAN,
    rationale               TEXT,
    key_risks               JSONB,
    invalidations           JSONB,

    -- ---- 모델/비용/지연 -------------------------------------------------
    model                   TEXT,
    tokens_in               INTEGER,
    tokens_out              INTEGER,
    cost_usd                NUMERIC(12, 6),
    latency_ms              INTEGER,
    verdict_lag_ms          INTEGER,
    eval_to_order_lag_ms    INTEGER,
    order_kst               TIMESTAMPTZ NOT NULL,
    evaluated_at            TIMESTAMPTZ,

    -- ---- 주문 스냅샷 ----------------------------------------------------
    order_price_won         BIGINT      NOT NULL,
    ordered_qty             INTEGER     NOT NULL,
    order_notional_won      BIGINT      NOT NULL,
    order_division          TEXT        NOT NULL,
    order_path              TEXT        NOT NULL,
    exchange                TEXT,
    board                   TEXT        NOT NULL,
    current_price_won       BIGINT,

    -- ---- 신호 역참조(있을 때만) -------------------------------------------
    signal_matched          BOOLEAN     NOT NULL DEFAULT FALSE,
    signal_price_won        BIGINT,
    signal_time_kst         TEXT,
    strategy_board          TEXT,
    target_won              BIGINT,
    k                       NUMERIC(10, 4),
    breakout_excess_bp      NUMERIC(12, 4),

    -- ---- 판정 시점 표류 --------------------------------------------------
    post_order_drift_bp     NUMERIC(12, 4),
    drift_price_won         BIGINT,
    tick_age_s              NUMERIC(10, 2),

    -- ---- 주문 시점 제약(반사실 분석용) -------------------------------------
    budget_total_won        BIGINT,
    budget_remaining_after_won BIGINT,
    open_positions_n        INTEGER,

    -- ---- 버전 고정 + 원문 -------------------------------------------------
    prompt_version          TEXT,
    feature_version         TEXT,
    bars_count              INTEGER,
    input_payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    raw_response            JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (trade_date, account_no, ticker, order_no)
);

COMMENT ON TABLE llm_buy_evaluations IS
    'cycle276 — AI 매수평가(LLM shadow) 주문 시점 기록. 주문 1건 = 1행(성공·실패 모두).
     PK (trade_date, account_no, ticker, order_no) — KIS ODNO 는 하루 단위로만 유일.
     trade_history 조인은 (trade_date, ticker, order_no) 3축. 체결 결과(체결가·수량·손익)는
     이 테이블에 절대 쓰지 않는다 — 결과는 언제나 조인으로 얻는다(자문 R1).';

COMMENT ON COLUMN llm_buy_evaluations.eval_kind IS
    '''order'' = 실제 주문에 붙은 평가 / ''blocked'' = (미래 enforce) 차단되어 주문이 없는 평가.
     운영 DB 에 이미 존재하는 order_no='''' 수기 체결 행과 충돌하지 않게 처음부터 분리한다.';
COMMENT ON COLUMN llm_buy_evaluations.board IS
    '주문 접수 KST 시각만으로 파생한 보드(pre_nxt/main/post_nxt/off_hours).
     session_tracker.active 가 아니다 — 그 값은 30초 stale 이라 09:00:0x 에 pre_nxt 로 굳는다(cycle264).';
COMMENT ON COLUMN llm_buy_evaluations.order_path IS
    '''market'' = 주 경로(시장가 또는 프리장 사전변환 지정가) / ''fallback'' = 시장가 거부 후
     지정가 5호가 폴백. 둘 다 LIMIT 일 수 있어 order_division 만으로는 분리되지 않는다(자문 R3).';
COMMENT ON COLUMN llm_buy_evaluations.ordered_qty IS
    '주문 수량이며 체결 수량이 아니다. 실현손익 분석은 trade_history.quantity 를 쓴다(자문 R8).';
COMMENT ON COLUMN llm_buy_evaluations.budget_remaining_after_won IS
    '이 주문의 pending_buy_amounts 가 이미 등록된 **뒤**의 전략 잔여 예산
     (= total_investment - _calc_used_funds()). "이 주문을 안 냈다면 남았을 예산" 은
     이 값 + order_notional_won 이다(자문 MEDIUM).';
COMMENT ON COLUMN llm_buy_evaluations.post_order_drift_bp IS
    '판정 도착 순간 scanner 현재가 대비 주문가 이동폭(bp). + = 주문 뒤 올랐다(이득).
     cycle274 의 slip_bp 와 **부호 의미가 반대**다 — 두 이름의 값을 절대 합산하지 말 것.';
COMMENT ON COLUMN llm_buy_evaluations.tick_age_s IS
    '드리프트 기준 틱의 나이(초). 무송출 종목(nxt_tradable=false, cycle252)은 고정값이 실려
     "표류 0" 으로 오독되므로, 판독 시 stale 행을 분포에서 제외하는 근거로 쓴다.';
COMMENT ON COLUMN llm_buy_evaluations.input_payload IS
    'build_messages 의 세 인자 그대로 {payload, tech, bars30}. 요약·절단 금지 —
     훗날 다른 모델·다른 프롬프트로 같은 거래를 오프라인 재채점하는 유일한 다리다.';

CREATE INDEX IF NOT EXISTS idx_llm_eval_trade_date
    ON llm_buy_evaluations (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_strategy_date
    ON llm_buy_evaluations (strategy_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_ticker_date
    ON llm_buy_evaluations (ticker, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_order_no
    ON llm_buy_evaluations (order_no)
    WHERE order_no <> '';

COMMENT ON INDEX idx_llm_eval_order_no IS
    'cycle276 — UI 버튼이 order_no 단독(또는 CSV 배치)으로 조회한다. PK 선두가 trade_date 라
     PK 인덱스로는 그 조회가 커버되지 않는다. order_no='''' 행은 조회 대상이 아니라 부분 인덱스.';
```

---

## 3. 테이블 열 정의 표

| # | 열 | 타입 | NULL | 의미 / 출처 |
|---|---|---|---|---|
| 1 | `trade_date` | DATE | NOT NULL (PK) | 주문 KST 영업일. `to_date(order_kst.date())` |
| 2 | `account_no` | TEXT | NOT NULL (PK) | `settings.kis_account_no`(CANO) **원문 저장** |
| 3 | `ticker` | TEXT | NOT NULL (PK) | 6자리 종목코드 |
| 4 | `order_no` | TEXT | NOT NULL, `''` (PK) | KIS ODNO. 빈 값이면 애초에 행을 만들지 않는다(C21) |
| 5 | `eval_kind` | TEXT | NOT NULL, `'order'` | `order`\|`blocked`. 이번 사이클은 `order` 만 |
| 6 | `account_product` | TEXT | NULL | `settings.kis_account_product`(기본 `"01"`) |
| 7 | `strategy_id` | TEXT | NOT NULL | `volatility_breakout`\|`long_tail_volatility`(현재) |
| 8 | `mode` | TEXT | NOT NULL | `shadow`(현재 유일) |
| 9 | `result` | TEXT | NOT NULL | `ok`\|`failed` |
| 10 | `reason` | TEXT | NULL | 실패 9종 어휘 중 하나. `result=ok` 면 NULL |
| 11 | `score` | INTEGER | NULL | 1~100. 실패면 NULL(**0 위장 금지**) |
| 12 | `min_score` | INTEGER | NOT NULL | 판정 시점 임계(기본 70) |
| 13 | `would_block` | BOOLEAN | NULL | `score < min_score`. 실패면 NULL |
| 14 | `rationale` | TEXT | NULL | 모델 사유 **원문**(로그의 60자 절단과 무관) |
| 15 | `key_risks` | JSONB | NULL | 모델 응답 `key_risks`(cycle274 가 버리던 값) |
| 16 | `invalidations` | JSONB | NULL | 모델 응답 `invalidations` |
| 17 | `model` | TEXT | NULL | `settings.openai_buy_gate_model` |
| 18 | `tokens_in` / 19 `tokens_out` | INTEGER | NULL | usage |
| 20 | `cost_usd` | NUMERIC(12,6) | NULL | `_cost_usd`. 미등록 모델은 **-1.0**(모른다를 정직하게) |
| 21 | `latency_ms` | INTEGER | NULL | LLM 호출 구간만 |
| 22 | `verdict_lag_ms` | INTEGER | NULL | 접수→판정 전체(세마포어·DB fetch 포함) |
| 23 | `eval_to_order_lag_ms` | INTEGER | NULL | `evaluated_at - order_kst`(ms). 지금은 ≈ verdict_lag |
| 24 | `order_kst` | TIMESTAMPTZ | NOT NULL | 주문 접수 시각(훅 시점 `datetime.now(_KST_TZ)`) |
| 25 | `evaluated_at` | TIMESTAMPTZ | NULL | 점수 산출 완료 시각 |
| 26 | `order_price_won` | BIGINT | NOT NULL | 주 경로 `record_price` / 폴백 `fallback_price` |
| 27 | `ordered_qty` | INTEGER | NOT NULL | `quantity`(주문 수량, 체결 아님) |
| 28 | `order_notional_won` | BIGINT | NOT NULL | `order_price_won × ordered_qty` |
| 29 | `order_division` | TEXT | NOT NULL | `MARKET`\|`LIMIT` |
| 30 | `order_path` | TEXT | NOT NULL | `market`\|`fallback`(cycle271 라벨과 동일 어휘) |
| 31 | `exchange` | TEXT | NULL | `KRX`\|`NXT`\|`SOR`(`buy_exchange`) |
| 32 | `board` | TEXT | NOT NULL | `_board_by_clock(order_kst)` — 시계 파생 |
| 33 | `current_price_won` | BIGINT | NULL | 훅 시점 `current_price`(scanner 틱가) |
| 34 | `signal_matched` | BOOLEAN | NOT NULL, false | `buy_signals` 꼬리에서 같은 ticker 를 찾았는가 |
| 35 | `signal_price_won` | BIGINT | NULL | 매칭된 신호의 `price` |
| 36 | `signal_time_kst` | TEXT | NULL | 매칭된 신호의 `time`(HH:MM:SS) |
| 37 | `strategy_board` | TEXT | NULL | 매칭된 신호의 `board`(전략이 본 보드) |
| 38 | `target_won` | BIGINT | NULL | 매칭된 신호의 `target_price` |
| 39 | `k` | NUMERIC(10,4) | NULL | 매칭된 신호의 `k` |
| 40 | `breakout_excess_bp` | NUMERIC(12,4) | NULL | `(order_price/target − 1)×10000`, 매칭 시만 |
| 41 | `post_order_drift_bp` | NUMERIC(12,4) | NULL | 판정 시점 표류(부호 의미 = 자문 ③) |
| 42 | `drift_price_won` | BIGINT | NULL | 표류 계산에 쓴 현재가 |
| 43 | `tick_age_s` | NUMERIC(10,2) | NULL | 그 현재가 틱의 나이(초). 미상은 NULL |
| 44 | `budget_total_won` | BIGINT | NULL | `state.total_investment` |
| 45 | `budget_remaining_after_won` | BIGINT | NULL | `total_investment − _calc_used_funds()` (이 주문 **포함 후**) |
| 46 | `open_positions_n` | INTEGER | NULL | `len(state.positions)` |
| 47 | `prompt_version` | TEXT | NULL | 프롬프트 sha256 앞 12자 |
| 48 | `feature_version` | TEXT | NULL | `compute_technicals` 키 집합 sha256 앞 12자 |
| 49 | `bars_count` | INTEGER | NULL | 프롬프트에 실린 일봉 수 |
| 50 | `input_payload` | JSONB | NOT NULL, `{}` | `{payload, tech, bars30}` 사영 전체 |
| 51 | `raw_response` | JSONB | NULL | `{"content": <파싱 전 원문>}` |
| 52 | `created_at` / 53 `updated_at` | TIMESTAMPTZ | NOT NULL | KST aware datetime 바인딩 |

**계좌번호는 `input_payload` 에 넣지 않는다**(C40).

---

## 4. `src/db/llm_buy_evaluations.py` — 시그니처와 바인딩 규약

```python
async def upsert_evaluation(
    *,
    trade_date,                 # date | datetime | str  → to_date() 강제
    account_no: str,
    ticker: str,
    order_no: str,
    eval_kind: str = "order",
    account_product: str | None = None,
    strategy_id: str,
    mode: str,
    result: str,                # "ok" | "failed"
    reason: str | None = None,
    score: int | None = None,
    min_score: int,
    would_block: bool | None = None,
    rationale: str | None = None,
    key_risks=None,             # list|dict|None  → raw 바인딩($N::jsonb)
    invalidations=None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd=None,              # float|Decimal|None
    latency_ms: int | None = None,
    verdict_lag_ms: int | None = None,
    eval_to_order_lag_ms: int | None = None,
    order_kst,                  # datetime (aware) — str 금지
    evaluated_at=None,          # datetime (aware) | None
    order_price_won: int,
    ordered_qty: int,
    order_notional_won: int,
    order_division: str,
    order_path: str,
    exchange: str | None = None,
    board: str,
    current_price_won: int | None = None,
    signal_matched: bool = False,
    signal_price_won: int | None = None,
    signal_time_kst: str | None = None,
    strategy_board: str | None = None,
    target_won: int | None = None,
    k=None,
    breakout_excess_bp=None,
    post_order_drift_bp=None,
    drift_price_won: int | None = None,
    tick_age_s=None,
    budget_total_won: int | None = None,
    budget_remaining_after_won: int | None = None,
    open_positions_n: int | None = None,
    prompt_version: str | None = None,
    feature_version: str | None = None,
    bars_count: int | None = None,
    input_payload: dict | None = None,   # raw dict → $N::jsonb
    raw_response: dict | None = None,
) -> dict | None: ...

async def get_by_order(order_no: str, *, trade_date=None) -> dict | None: ...
async def list_by_order_nos(order_nos: list[str], *, trade_date=None) -> list[dict]: ...
```

바인딩 규약(전부 C34):
- `trade_date` → `to_date(trade_date)`. **str 바인딩 금지**(M6 사고).
- `order_kst`/`evaluated_at`/`created_at`/`updated_at` → **aware `datetime`**.
  `created_at`/`updated_at` 은 `datetime.fromisoformat(now_kst_iso())`.
- `key_risks`/`invalidations`/`input_payload`/`raw_response` → **raw** dict/list 를 그대로 넘기고
  SQL 쪽에서 `$N::jsonb` 캐스트. `json.dumps` 사전 적용 **금지**.
- `order_no` 는 `str(order_no or "")` 정규화 후 바인딩(NULL 로 PK 가 통째로 사라지는 사고 차단).
- `list_by_order_nos` 는 `WHERE order_no = ANY($1::text[])`. 입력이 빈 리스트면 **쿼리 없이 `[]`**.
- SQL 은 `INSERT … ON CONFLICT (trade_date, account_no, ticker, order_no) DO UPDATE SET <전 열 열거,
  단 created_at 제외> RETURNING *`. `updated_at = EXCLUDED.updated_at`.
- 읽기 함수는 `to_char(order_kst,'YYYY-MM-DD"T"HH24:MI:SS.US+09:00') AS order_kst_iso` 등
  **ISO 문자열 별칭 3개**(`order_kst_iso`/`evaluated_at_iso`/`created_at_iso`)를 함께 사영한다
  (프론트가 `Intl.DateTimeFormat(timeZone:'Asia/Seoul')` 로 그리는 계약).
- `NUMERIC` 은 `Decimal` 로 돌아온다 — **라우트가 float 로 사영**한다(cycle266 흰 화면 재현 금지).

---

## 5. 라우트 계약 — `src/routes/llm_evaluations.py`

```python
router = APIRouter(prefix="/api/llm-evaluations", tags=["llm-evaluations"])
```
`src/main.py` 에 import 1줄 + `app.include_router(llm_evaluations.router)` 1줄.

### 5.1 `GET /api/llm-evaluations` (배치 요약)

- 쿼리: `order_nos: str`(CSV, **필수**), `trade_date: str | None`(`YYYY-MM-DD`)
- 검증: 공백 제거 후 빈 항목 제거 → 개수 **1~200**. 0개 또는 >200 → **422**
  (손익 그리드 최대 페이지 200 `history.py:45` 와 정렬).
- 응답 `data` = `{ "<order_no>": { … 요약 … } }` — 기록이 없는 주문번호는 **키 자체가 없다**.
- 같은 `order_no` 가 여러 날짜에 있으면 `trade_date` 가 주어졌으면 그 날짜, 아니면 **가장 최근** 1건.

```json
{
  "success": true,
  "message": "",
  "data": {
    "0000123456": {
      "order_no": "0000123456",
      "trade_date": "2026-09-11",
      "ticker": "005930",
      "strategy_id": "volatility_breakout",
      "result": "ok",
      "reason": null,
      "score": 62,
      "min_score": 70,
      "would_block": true,
      "evaluated_at": "2026-09-11T09:01:34.512000+09:00"
    }
  }
}
```

### 5.2 `GET /api/llm-evaluations/{order_no}` (단건 상세)

- 경로: `order_no`(빈 문자열 불가 — FastAPI 가 라우트 미매치로 처리)
- 쿼리: `trade_date: str | None`
- 없으면 **404** `detail="order_no=… 평가 기록 없음 (trade_date=…)"`
- DB 예외는 **500** + `logger.exception("[llm_eval_route_error] order_no=%s", order_no)`
- 응답 `data` 전문(계좌 마스킹 적용, `NUMERIC` → float 사영):

```json
{
  "success": true,
  "message": "",
  "data": {
    "trade_date": "2026-09-11",
    "account_no_masked": "1234****",
    "ticker": "005930",
    "ticker_name": null,
    "order_no": "0000123456",
    "eval_kind": "order",
    "strategy_id": "volatility_breakout",
    "mode": "shadow",
    "result": "ok",
    "reason": null,
    "score": 62,
    "min_score": 70,
    "would_block": true,
    "rationale": "…",
    "key_risks": ["…"],
    "invalidations": ["…"],
    "model": "gpt-5.6-luna",
    "tokens_in": 3120,
    "tokens_out": 210,
    "cost_usd": 0.004380,
    "latency_ms": 3120,
    "verdict_lag_ms": 3480,
    "eval_to_order_lag_ms": 3480,
    "order_kst": "2026-09-11T09:01:31.032000+09:00",
    "evaluated_at": "2026-09-11T09:01:34.512000+09:00",
    "order_price_won": 71800,
    "ordered_qty": 3,
    "order_notional_won": 215400,
    "order_division": "MARKET",
    "order_path": "market",
    "exchange": "KRX",
    "board": "main",
    "current_price_won": 71800,
    "signal_matched": true,
    "signal_price_won": 71800,
    "signal_time_kst": "09:01:31",
    "strategy_board": "main",
    "target_won": 71650,
    "k": 0.5,
    "breakout_excess_bp": 20.9,
    "post_order_drift_bp": -13.9,
    "drift_price_won": 71700,
    "tick_age_s": 1.2,
    "budget_total_won": 247949,
    "budget_remaining_after_won": 32549,
    "open_positions_n": 1,
    "prompt_version": "a1b2c3d4e5f6",
    "feature_version": "0f1e2d3c4b5a",
    "bars_count": 59,
    "input_payload": { "payload": {}, "tech": {}, "bars30": [] },
    "raw_response": { "content": "{\"score\":62,…}" }
  }
}
```

- **`account_no` 원문 키는 응답에 존재하지 않는다** — `account_no_masked` 하나뿐(C39/C40).
- 마스킹: `mask_account_no("12345678") == "1234****"`, `mask_account_no("") == "****"`,
  `mask_account_no("123") == "****"`.
- 리포터 키(GET/HEAD 경로 무관 통과, cycle249)로도 읽히는 표면이다 — 그래서 계좌 원문이
  db→라우트 사영에서 **반드시** 떨어져야 한다. `REPORTER_READ_METHODS` 는 손대지 않는다(인증 계약 변경).

---

## 6. leaf 변경 — `src/engine/llm_buy_gate.py`

### 6.1 진입점 `observe_order` (구 `observe_signal` 삭제)

```python
def observe_order(
    *,
    strategy_id, ticker, order_no, order_kst,
    order_price_won, ordered_qty, order_division, order_path, exchange,
    current_price_won,
    budget_total_won, budget_remaining_after_won, open_positions_n,
    params_snapshot, buy_signals_tail,
) -> None:
```

동기 본문 순서(C19):
1. `params = params_snapshot if isinstance(params_snapshot, dict) else {}`
2. `mode/min_score/daily_cap/timeout_s/model` 읽기 → `_emit_config_canary(...)`
3. `if mode != "shadow": return None`
4. `ono = str(order_no or "").strip()` — 빈 값이면 `[llm_eval_persist] order_no=- result=error
   reason=empty_order_no` 1행 후 `return None`(C21)
5. `if not _latch.should_emit(ono, now=order_kst): return None`
6. `if _peek_call_count(strategy_id, order_kst) >= daily_cap:` → `[llm_gate_daily_cap]` 1회/전략/일 후 return
7. **값 복사** — scanner 지연 import 로 `ticker_names`/`ticker_prev_close`/`ticker_market_info`
   read-only 조회(O(1) dict get), `buy_signals_tail` 꼬리에서 같은 ticker 최신 1건 매칭,
   `_board_by_clock(order_kst)`, `account_no`/`account_product` 는 `settings` 에서 읽는다
   (**order_engine 은 계좌를 모른다** — import 순증 0)
8. `_latch.mark_emitted(ono, now=order_kst)` → `_increment_call_count(strategy_id)`
9. `coro = _evaluate(payload)` → `asyncio.create_task` (실패 시 `coro.close()`) → `_tasks` 강참조
10. `return None`

전체가 `try/except Exception` 안이며 except 는 `trace_observer_failure("[llm_buy_gate]", ticker, None,
now=order_kst)` 후 `return None`.

`payload` 는 cycle274 키를 계승하되 다음이 바뀐다:
- `signal_kst` → **`order_kst`**(문자열 `HH:MM:SS`) + 별도 `order_kst_dt`(datetime, DB용)
- `price_won` → **`order_price_won`**(주문가). `current_price_won` 별도 키로 병행
- 신설: `order_no`·`ordered_qty`·`order_division`·`order_path`·`exchange`·`board`·
  `signal_matched`·`signal_price_won`·`signal_time_kst`·`strategy_board`·
  `budget_total_won`·`budget_remaining_after_won`·`open_positions_n`·`account_no`·`account_product`
- `target_won`/`k`/`breakout_excess_bp` 는 **`signal_matched=True` 일 때만** 값이 있고 아니면 `None`
- `prev_price_won` **삭제**(주문 시점에 복구 불가 — 전략이 판정 직후 `current_price` 로 덮는다. 자문 R7)
- `target_offset_won` **삭제**(`buy_signals` 에 없다)

### 6.2 `_evaluate` / `_evaluate_core` / `_persist_evaluation`

```python
async def _evaluate(payload: dict) -> None:
    t_start = _monotonic()
    outcome = await _evaluate_core(payload, t_start)   # CancelledError 만 전파
    if outcome is not None:
        await _persist_evaluation(payload, outcome)    # ← 유일한 persist 사이트(C24)
```

- `_evaluate_core` 는 cycle274 `_evaluate` 본문을 그대로 옮긴 것이며, 각 `return None` 자리에서
  **outcome dict 를 반환**한다. `_emit_failed`/`_emit_score` 호출 위치·서식은 그대로 두되
  `order_no=` 필드가 추가되고 `slip_bp` → `post_order_drift_bp`, `signal_kst` → `order_kst`,
  `signal_price` → `order_price` 로 개명한다(C27).
- outcome 키 = `result`·`reason`·`score`·`rationale`·`key_risks`·`invalidations`·`tokens_in`·
  `tokens_out`·`cost_usd`·`latency_ms`·`verdict_lag_ms`·`evaluated_at`·`bars_count`·`tech`·
  `bars30`·`raw_content`·`post_order_drift_bp`·`drift_price_won`·`tick_age_s`.
- `_parse_score_response` 의 3·4번째 반환값을 **버리지 않는다**(C29).
- `_persist_evaluation(payload, outcome)`:
  - `from src.db.llm_buy_evaluations import upsert_evaluation`(**함수 내 지연 import** — leaf
    최상단 허용 목록은 `db.stock_master_daily` 하나였고 그 목록을 새 모듈 하나로만 넓힌다.
    지연 import 로 두면 §10 허용 목록 자체를 건드리지 않는다)
  - `input_payload = {"payload": _json_safe(payload), "tech": outcome["tech"] or {},
    "bars30": outcome["bars30"] or []}` (C35/C36)
  - `raw_response = {"content": outcome["raw_content"]}` (없으면 `None`)
  - `await upsert_evaluation(...)` 를 `try/except Exception` 으로 감싸고
    `[llm_eval_persist] order_no=… result=ok|error [reason=…]` **1행**(C25)
  - 어떤 경우에도 raise 하지 않는다(never-raise).

### 6.3 신규 순수 헬퍼(전부 leaf 안, never-raise)

| 헬퍼 | 계약 |
|---|---|
| `_board_by_clock(order_kst)` | `pre_nxt`/`main`/`post_nxt`/`off_hours`. **`session` import 금지**(C22) |
| `_match_signal(buy_signals_tail, ticker)` | 꼬리부터 스캔, 같은 ticker 최신 1건 `dict(d)` 복사 반환. 없으면 `None` |
| `_json_safe(obj)` | datetime→isoformat · Decimal→float · set→list · 그 외 미지 타입→`str(obj)`. 재귀 깊이 상한 6 |
| `_prompt_version()` / `_feature_version()` | 모듈 로드 1회 캐시, 실패 시 `""` (C30) |
| `_read_drift(ticker, order_price_won)` | 구 `_read_slip_bp`. 반환 `(drift_price, drift_bp, tick_age_s)`. `scanner` 지연 import read-only |

### 6.4 삭제·개명 목록

- `observe_signal` **삭제**(이름이 남아 있으면 전략 원복이 미완이라는 뜻)
- `_read_slip_bp` → `_read_drift`, `slip_bp` 문자열 소스 전체 **0건**
- `_latch` 타입 주석 `KstDailyEmitCap[tuple[str,str]]` → `KstDailyEmitCap[str]`
- `llm_features._SNAPSHOT_KEYS` 의 `"signal_kst"` → `"order_kst"`, `"price_won"` → `"order_price_won"`,
  `"prev_price_won"` 제거, `"order_division"`·`"order_path"`·`"exchange"` 추가
- `llm_features` user 템플릿 문면: "신호 시각" → "**주문 접수 시각**", 판단축 5번의 설명을
  "돌파 후 주문이 접수된 시각" 으로 정직화

---

## 7. `src/engine/order_engine.py` 훅 (정확한 자리와 형태)

### 7.1 주 경로 — `_pending_buy_orders[...] = {...}` 대입 직후(현행 `:425` 닫는 `}` 다음 줄, `:428` 판정 앞)

```python
            # cycle276 — AI 매수평가(shadow) 주문 시점 훅. 주문은 이미 KIS 에 접수됐고
            # 이 호출은 기록만 한다. 동기·never-raise·반환 미사용(Expr statement).
            # 자리 = 매핑 등록 **뒤** · `already_completed` 판정과 PENDING INSERT **앞**.
            # INSERT 뒤로 옮기면 체결통보 선행 코호트(가장 빨리 체결되는 진입)가
            # 기록에서 통째로 빠진다(cycle276 C7, 09-09 034020·09-10 004990 실측).
            try:
                llm_buy_gate.observe_order(
                    strategy_id=strategy.strategy_id,
                    ticker=ticker,
                    order_no=result.order_no,
                    order_kst=datetime.now(_KST_TZ),
                    order_price_won=record_price,
                    ordered_qty=quantity,
                    order_division=getattr(order_division, "value", order_division),
                    order_path="market",
                    exchange=buy_exchange,
                    current_price_won=current_price,
                    budget_total_won=state.total_investment,
                    budget_remaining_after_won=(
                        state.total_investment - strategy._calc_used_funds()
                    ),
                    open_positions_n=len(state.positions),
                    params_snapshot=dict(strategy.config.params),
                    buy_signals_tail=list(state.buy_signals[-3:]),
                )
            except Exception:
                logger.debug("[llm_buy_gate_call] 주문 시점 관측 호출 실패", exc_info=True)
```

### 7.2 지정가 폴백 경로 — 폴백 매핑 등록 직후(현행 `:493` 다음 줄, `:496` 판정 앞)

동일 형태. 차이는 `order_price_won=fallback_price` · `order_division="LIMIT"` · `order_path="fallback"`.

### 7.3 호출부 계약

- `logger.debug(..., exc_info=True)` 는 order_engine 자신의 흡수기 관례
  (`[market_order_preconvert_pre_nxt]`·`[stock_master_miss]`)와 같은 형태이며, cycle274 전략 호출부의
  `trace_observer_failure(cap=None)` 과 **동작이 동등**(둘 다 debug 스택 단독)하다.
  이 선택으로 order_engine 의 `src.*` import 증가분이 **1줄**로 유지된다(C10).
- `strategy._calc_used_funds()` 는 `StrategyBase` 의 순수 계산(보유 원금 + pending 합, O(n≤20))이며
  **상태를 바꾸지 않는다**. `strategy_base.py` 는 **읽기만** 하고 byte 동일(C13).
- `state.buy_signals[-3:]` 는 얕은 복사 3건 이하이며 leaf 가 `dict(d)` 로 다시 복사한다(C23).

---

## 8. 전략 2파일 원상 복구

- VB `volatility_breakout.py` — `:1027~:1060` 의 훅 블록 전체를 삭제하고 `return Signal.BUY` 를
  cycle272 형태로 되돌린다. `:18` 의 `from src.engine import llm_buy_gate, open_price_rest` →
  `from src.engine import open_price_rest`.
- LTV `long_tail_volatility.py` — `:830~:864` 동일. `:17` import 동일.
- `trace_observer_failure` import 는 **유지**(cycle262 `open_entry_hold` 가 쓴다).
- `DEFAULT_PARAMS` 4키 블록(주석 포함)은 **한 글자도 건드리지 않는다** — 설정 표면이자 킬스위치이고,
  order_engine 이 `strategy.config.params` 로 읽는다.
- 결과: `check_buy_signal` 세그먼트 sha 가 `_BASE_METHOD_SHA` 값으로 **정확히 복귀**(C11).
  파일 sha 는 4키 때문에 cycle272 와 다르므로 자매 핀은 **현재값으로 재핀**(C15).

---

## 9. `get_trade_pairs` 확장 (사영만)

### 9.1 추가 키 3종

| 키 | 타입 | 규칙 |
|---|---|---|
| `buy_order_nos` | `list[str]` | 그 사이클의 매수 체결 행 `order_no` **시간 오름차순**, 빈 값 제외, 중복 제거(순서 보존) |
| `sell_order_nos` | `list[str]` | 동일(매도). open 페어는 `[]` |
| `pair_key` | `str \| None` | `f"{strategy}:{ticker}:{buy_order_nos[0]}"`. `buy_order_nos` 가 비면 `None` |

### 9.2 구현 규약(C41)

- `buy_buf`/`sell_buf` 의 **arity 를 늘리지 않는다**. 병행 리스트 `buy_ono_buf`/`sell_ono_buf` 를 두고
  `emit_closed()` 와 open 분기에서 함께 리셋한다.
- `emit_closed` 는 클로저이므로 `nonlocal` 또는 리스트 in-place 초기화로 리셋 대칭을 지킨다.
- SQL 은 **변경 0** — `SELECT t.*` 가 이미 `order_no` 를 포함한다.
- 기존 15키의 이름·타입·값·정렬 불변.

### 9.3 분석 규약(문서화, 코드는 다음 사이클)

- 페어 손익을 주문 단위로 배분할 때는 **매수 금액(수량 × 매수가) 가중**으로 나눈다.
- **평가↔손익 분석의 정본은 페어가 아니라 체결 행 단위**다(자문 R10). 페어는 UI 버튼용.
- 조인은 `(trade_date, ticker, order_no)` 3축 + `trade_history.status` 를 함께 읽어 **5분류**:
  `COMPLETED` / `PARTIAL` / `CANCELLED` / `PENDING(미체결 추정)` / `PENDING(체결 의심 — 교차확인 필요)`.
  마지막 분류는 체결통보 유실 케이스이며 **손익 0 으로 섞지 않고 unknown 버킷**에 둔다(자문 R4).

### 9.4 `src/routes/history.py` 는 **0줄 변경**

`:54`·`:70` 이 `pairs` 를 그대로 통과시키므로 새 키는 자동으로 응답에 실린다. **키를 명시 열거하는
사영을 새로 넣지 않는다** — 그러면 미래에 키가 늘 때 조용히 떨어지는 필터가 생긴다.
문서(`src/routes/CLAUDE.md` 의 `/api/history/pnl` 행)만 갱신한다.

---

## 10. 프론트 계약

### 10.1 타입

`frontend/src/types/trading.ts` — `TradePair` 에 추가(**index signature 가 없으므로 명시 선언 필수**):
```ts
  buy_order_nos: string[]
  sell_order_nos: string[]
  pair_key: string | null
```

신규 `frontend/src/types/llm-evaluation.ts`:
```ts
export interface LlmEvaluationSummary {
  order_no: string
  trade_date: string
  ticker: string
  strategy_id: string
  result: 'ok' | 'failed'
  reason: string | null
  score: number | null
  min_score: number
  would_block: boolean | null
  evaluated_at: string | null
}
export interface LlmEvaluation extends LlmEvaluationSummary {
  account_no_masked: string          // ⚠️ 원문 계좌번호 필드는 만들지 않는다
  eval_kind: string
  mode: string
  rationale: string | null
  key_risks: unknown
  invalidations: unknown
  model: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  latency_ms: number | null
  verdict_lag_ms: number | null
  eval_to_order_lag_ms: number | null
  order_kst: string
  order_price_won: number
  ordered_qty: number
  order_notional_won: number
  order_division: string
  order_path: string
  exchange: string | null
  board: string
  current_price_won: number | null
  signal_matched: boolean
  signal_price_won: number | null
  signal_time_kst: string | null
  strategy_board: string | null
  target_won: number | null
  k: number | null
  breakout_excess_bp: number | null
  post_order_drift_bp: number | null
  drift_price_won: number | null
  tick_age_s: number | null
  budget_total_won: number | null
  budget_remaining_after_won: number | null
  open_positions_n: number | null
  prompt_version: string | null
  feature_version: string | null
  bars_count: number | null
  input_payload: unknown
  raw_response: unknown
}
export type LlmEvaluationSummaryMap = Record<string, LlmEvaluationSummary>
```

### 10.2 API 클라이언트 `frontend/src/api/llm-evaluations.ts`

```ts
export const getLlmEvaluationSummaries = async (
  orderNos: string[], tradeDate?: string,
): Promise<LlmEvaluationSummaryMap> => {
  if (orderNos.length === 0) return {}
  const { data } = await apiClient.get<ApiResponse<LlmEvaluationSummaryMap>>(
    '/llm-evaluations', { params: { order_nos: orderNos.join(','), trade_date: tradeDate } })
  return data.data ?? {}
}
export const getLlmEvaluation = async (
  orderNo: string, tradeDate?: string,
): Promise<LlmEvaluation> => {
  const { data } = await apiClient.get<ApiResponse<LlmEvaluation>>(
    `/llm-evaluations/${orderNo}`, { params: { trade_date: tradeDate } })
  return data.data
}
```
- api 계층에 `try/catch` 없음(axios 오류를 React Query 로 흘린다 — 리포 관례).
- `apiClient` 단일 인스턴스, 인터셉터 추가 금지.

### 10.3 두 그리드

공통:
- 모듈 레벨 `const columns` → **`makeColumns(onOpen, summaries)` 팩토리** + 컴포넌트 안 `useMemo`.
  `colSpan={cols.length}` 참조도 함께 옮긴다.
- `TradeHistoryGrid.tsx` 의 상태 배지 맵 리터럴 형태(`PENDING: { label: …, cls: '…' }` /
  `PARTIAL: {…}`)는 **정규식 가드가 읽으므로 형태 보존**(`badgeContrast.cycle261.test.tsx`).
- 요약 조회 `useQuery` 는 `retry: 1` 명시. 두 그리드 + 모달을
  `_ast_useQuery_retry_required.test.ts::TARGET_FILES` 에 등재하고, 그 파일의 **기존 useQuery 에도
  `retry: 1` 을 명시**한다(가드가 파일 단위이므로 — 프론트 전용 동작 변화, 리포 관례 방향).
- 새 색 hex 리터럴 **0건**(`designSystem.v2.test.ts` (c) 가 `src/**` 를 fs 전수 스캔).
  `accentColor:` 사이트 **정확히 5** 유지(새 게이지에 `accentColor` 금지).
- 새 배지 색은 별칭표(green→sky, amber/yellow→beige, purple/violet/indigo→navy, pink/orange→brown,
  emerald→blue, cyan→sky, slate→gray) 대조 + 배경 sRGB 거리 ≥ 25 자가 검산.

`TradeHistoryGrid` — 신규 열 "AI 자문"(맨 끝):
- 키 = 행의 `order_no`, 날짜 = `timestamp` 를 KST 로 사영한 `YYYY-MM-DD`
- **BUY 행만** 활성 대상. SELL 행은 **비활성 버튼을 렌더**(열 폭 유지) + `title="매수 주문만 평가 대상"`
- 활성 조건 = `trade_type === 'BUY' && order_no && summaries[order_no]`
- 비활성 조건 = 위 실패 시. `title="평가 기록 없음"`, 회색
- `data-testid="llm-eval-btn-{order_no}"`(order_no 가 빈 값이면 `llm-eval-btn-none-{rowIndex}`)
- 배치 조회는 **페이지당 1회**: `useQuery(['llmEvalSummaries','history',page, orderNos.join(',')], …)`
  — 행마다 개별 조회 금지(페이지당 20~30 요청 방지)

`TradePnLGrid` — 신규 열 "AI 자문"(맨 끝):
- 키 = `buy_order_nos`(배열). 배치 조회는 페이지의 모든 `buy_order_nos` 를 flat 하게 모아 1회
- 활성 조건 = `buy_order_nos.some(no => summaries[no])`
- 비활성 = `buy_order_nos.length === 0`(수기 매매 등) 또는 전부 기록 없음
- `data-testid="llm-eval-btn-pair-{pair_key}"`(`pair_key` 가 null 이면 `llm-eval-btn-pair-none-{rowIndex}`)
- 버튼 라벨 옆에 `buy_order_nos.length > 1` 이면 `(n)` 배지

### 10.4 모달 `frontend/src/components/LlmEvaluationModal.tsx`

- props: `{ orderNos: string[]; tradeDate?: string; onClose: () => void }`
- 마운트 = 페이지/그리드 레벨 조건부 렌더(`{sel && <LlmEvaluationModal … />}`) — `StockMaster.tsx:1501` 관례
- **소유 위치 = 각 그리드**(탭 전환 시 그리드가 언마운트되며 모달 상태가 자연 정리된다)
- 구조 = `StockMaster.tsx::DetailModal` 답습:
  오버레이 `fixed inset-0 z-50 flex items-center justify-center bg-black/40` + `onClick={onClose}`,
  패널 `bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col`
  + `onClick={e => e.stopPropagation()}`
- **접근성**: `role="dialog"` + `aria-modal="true"` + `aria-labelledby` + ESC 닫기
  (`InfoTooltip.tsx:17~31` 의 `useEffect` 관용구 그대로) + × 버튼 `aria-label="닫기"` + 닫을 때
  트리거 버튼으로 포커스 복귀. **리포 최초 사례**이며 의도된 상향이다(포커스 트랩은 범위 밖).
- `orderNos.length > 1` 이면 상단 탭 `data-testid="llm-eval-order-tab-{order_no}"` +
  문면 "이 손익 행은 매수 주문 n건이 뭉쳐 있습니다 — **첫 매수 주문 기준**으로 정렬했습니다"(자문 R10)
- 본문 `useQuery(['llmEvaluation', activeOrderNo, tradeDate], … , { retry: 1, enabled: !!activeOrderNo })`
- 렌더 분기(cycle266 계약): `axios.isAxiosError(e) && e.response?.status === 404`
  → 회색 안내 `data-testid="llm-eval-notice"` "평가 기록 없음", 그 외(500·네트워크)
  → 빨강 오류 `data-testid="llm-eval-error"`
- `result === 'failed'` 면 **실패 사유를 크게** `data-testid="llm-eval-failed"`
- 섹션(testid):
  `llm-eval-score`(점수/임계/would_block) · `llm-eval-rationale` · `llm-eval-risks` ·
  `llm-eval-invalidations` · `llm-eval-features`(지표 요약) · `llm-eval-order`(주문 스냅샷:
  주문가·수량·주문구분·경로·거래소·보드·목표가·breakout_excess_bp) · `llm-eval-meta`(모델/토큰/
  비용/지연/버전) · `llm-eval-payload-toggle` / `llm-eval-payload-content`(원문 payload 접기,
  `<pre className="whitespace-pre-wrap text-xs …">{JSON.stringify(v, null, 2)}</pre>`,
  `dangerouslySetInnerHTML` 금지) · `llm-eval-raw-toggle` / `llm-eval-raw-content`
- 신규 프론트 의존성 **0**(마크다운 렌더러·UI 킷 금지)
- 모든 시각은 `Intl.DateTimeFormat(timeZone:'Asia/Seoul')`. `new Date(iso).getHours()` 금지
- 숫자는 방어 변환(`toSafeNumber` 계열) — `NUMERIC` → 문자열로 오는 경로가 다시 생기면
  `toFixed` 가 터진다(cycle266 흰 화면)

### 10.5 testid 목록(정본)

```
llm-eval-btn-{order_no}            체결 그리드 버튼
llm-eval-btn-none-{rowIndex}       체결 그리드 비활성(빈 order_no·SELL)
llm-eval-btn-pair-{pair_key}       손익 그리드 버튼
llm-eval-btn-pair-none-{rowIndex}  손익 그리드 비활성
llm-eval-modal                     모달 루트
llm-eval-order-tab-{order_no}      다중 주문 탭
llm-eval-score / -rationale / -risks / -invalidations / -features / -order / -meta
llm-eval-payload-toggle / -payload-content
llm-eval-raw-toggle / -raw-content
llm-eval-failed / -notice / -error
```

### 10.6 목(mock) 갱신 위치

- `frontend/src/test/handlers.ts`
  - **정직화**: `${base}/history` 기본 핸들러가 `items` 를 돌려준다 — 실제 응답·프론트 타입은
    `trades` + `total_pages` 다. `{trades:[makeTrade()], page:1, size:20, total:1, total_pages:1}`
    로 고친다. **고치지 않으면 새 "AI 자문" 열 테스트가 빈 표를 보고 통과한다**(cycle266 §C-3 재현).
  - `${base}/history/pnl` 응답 pairs 예시에 `buy_order_nos`/`sell_order_nos`/`pair_key` 를 넣는다.
  - 신규 `${base}/llm-evaluations`(배치) + `${base}/llm-evaluations/:orderNo`(단건). MSW 는 배열
    **first-match** 이므로 **구체 경로를 먼저**, 와일드카드/배치를 뒤에 둔다.
  - 파일 헤더의 "19개 엔드포인트" 문구를 실제 수로 갱신(현재도 사실과 다르다).
- `e2e/fixtures/api-mocks.ts`
  - history 블록(`:163~:192`) **직후**에 등록. Playwright 는 **LIFO** 이므로
    `**/api/llm-evaluations*`(배치 fallback) 를 **먼저**, `**/api/llm-evaluations/*`(단건) 를 **나중**에.
  - `MockOptions` 에 `llmEvaluations?: Record<string, AnyJson>` 추가.
  - `**/api/history*` 목의 `trades` 항목에 `order_no` 가 실리도록 픽스처 정직화.
- `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` — **G-AST10** 그룹 신설
  (G-AST9 템플릿: ① `api/llm-evaluations.ts` 가 그 리터럴을 아직 호출하는지 방어 단언
  ② `isRouteRegistered(source, '/api/llm-evaluations')`).

---

## 11. Red 목록

### 11.1 백엔드 (92건)

#### `tests/unit/ast/test_cycle276_ast_order_hook.py` (26)
| # | 케이스 | 검증 |
|---|---|---|
| B1 | `test_c1_1_hook_appears_exactly_twice` | `order_engine.py` AST 에 `llm_buy_gate.observe_order` 호출 정확히 2 |
| B2 | `test_c1_2_hook_is_bare_expression` | 두 호출 모두 `ast.Expr` 의 직접 자식, 대입·비교·인자 아님 |
| B3 | `test_c1_3_hook_uses_keyword_args_only` | `Call.args == []` |
| B4 | `test_c1_4_no_await_on_hook` | 훅 statement 및 인자식에 `ast.Await` 0 |
| B5 | `test_c1_5_hook_is_inside_execute_buy` | 두 훅 모두 `execute_buy` FunctionDef 범위 안 |
| B6 | `test_c1_6_hook_follows_pending_buy_orders_assign` | lineno: 매핑 대입 < 훅 |
| B7 | `test_c1_7_hook_precedes_completed_orders_check` | lineno: 훅 < `_completed_orders` 판정 |
| B8 | `test_c1_8_hook_precedes_insert_helper` | lineno: 훅 < `_insert_pending_buy_or_absorb_race` |
| B9 | `test_c1_9_no_await_between_hook_and_insert` | 두 lineno 사이 `ast.Await` 0 |
| B10 | `test_c1_10_each_hook_wrapped_in_try_except_exception` | 각 훅의 조상 `ast.Try` 의 handler 가 `Exception` 이고 body 에 `raise`/`return` 0 |
| B11 | `test_c1_11_absorber_body_has_no_state_mutation` | except 본문에 `discard`/`pop`/`add`/`clear` 0 |
| B12 | `test_c1_12_hook_args_have_no_store_context` | 인자식에 Store 컨텍스트 `Subscript`/`Name` 0 |
| B13 | `test_c1_13_hook_args_have_no_mutating_calls` | 인자식 Call 이름에 `add/pop/discard/update/clear/append` 0 |
| B14 | `test_c1_14_hook_args_have_no_db_or_http` | `pg.`/`httpx`/`requests`/`insert_trade`/`write_log` 0 |
| B15 | `test_c2_1_sell_paths_have_no_hook` | `execute_sell` FunctionDef + `OrderSide.SELL` 인자 `place_order` 와 같은 try 안에 훅 0 |
| B16 | `test_c2_2_hook_count_in_whole_file_is_two` | 파일 전체 문자열 `observe_order` 등장 = 2 (import 제외) |
| B17 | `test_c3_1_atomic_segment_sha_unchanged` | `calc_buy_quantity` 호출문~`pending_buys.add` 세그먼트 sha == base |
| B18 | `test_c3_2_atomic_segment_has_no_await` | 그 구간 `ast.Await` 0 (AST 동적 경계, 라인 리터럴 금지) |
| B19 | `test_c4_1_place_order_kwargs_unchanged` | 두 매수 `place_order` 호출의 키워드 이름 집합 == base |
| B20 | `test_c4_2_order_engine_src_imports_delta_is_one` | 모듈 최상단 `src.*` import 이름 집합 == base ∪ `{src.engine.llm_buy_gate}` |
| B21 | `test_c5_1_untouchable_files_byte_identical` | `_BASE_SHA` 재활용(order_engine 만 새 값) |
| B22 | `test_c5_2_scheduler_line_count_is_3872` | + cycle257 상한 리터럴 자동 대조 |
| B23 | `test_c6_1_strategy_methods_return_to_cycle272_sha` | 6핀 전부 `_BASE_METHOD_SHA` 와 일치 |
| B24 | `test_c6_2_strategies_have_no_llm_buy_gate_reference` | VB·LTV 소스에 `llm_buy_gate` 0건 |
| B25 | `test_c6_3_default_params_four_keys_survive_in_vb_and_ltv_only` | 4키가 두 파일에만, `PARAM_RANGES`/`INT_PARAMS` 미편입(런타임 dict + 소스 리터럴 이중) |
| B26 | `test_c6_4_sibling_pins_are_consistent` | cycle264 6핀 = cycle272 값 · cycle223 파일 sha = 현재값 · cycle222a3 `_APPROVED_CONTENT_SHA` 에 order_engine 1건 |

#### `tests/unit/engine/test_cycle276_observe_order.py` (18)
| # | 케이스 | 검증 |
|---|---|---|
| B27 | `test_observe_order_is_sync_and_returns_none` | `inspect.iscoroutinefunction` False, 반환 None |
| B28 | `test_observe_order_never_raises_on_garbage_input` | 전 인자 `None`/이상 타입에도 예외 0 |
| B29 | `test_mode_off_creates_no_task` | 4키 없는 params → `create_task` 0, DB 0, 마커 `[llm_buy_score*]` 0 |
| B30 | `test_mode_off_still_emits_config_canary` | `[llm_gate_config] mode=off` 1행(C16) |
| B31 | `test_five_other_strategies_do_nothing` | momentum·donchian·BFB·VCP·kojiro `DEFAULT_PARAMS` 로 호출 → task 0·기록 0 |
| B32 | `test_empty_order_no_records_persist_error_only` | `order_no=""` → task 0, `[llm_eval_persist] result=error reason=empty_order_no` 1행 (C21) |
| B33 | `test_latch_key_is_order_no_same_order_twice` | 같은 order_no 2회 → task 1 |
| B34 | `test_latch_allows_two_orders_same_ticker_same_day` | 같은 ticker 다른 order_no 2회 → task 2 (cycle274 와 반대) |
| B35 | `test_daily_cap_peek_blocks_and_warns_once` | cap 도달 → task 0 + `[llm_gate_daily_cap]` 1회/전략/일 |
| B36 | `test_cap_key_absent_means_zero_calls` | `llm_gate_daily_call_cap` 키 부재 → task 0 |
| B37 | `test_latch_mark_precedes_create_task` | monkeypatch 로 순서 관측 |
| B38 | `test_board_by_clock_windows` | 07:59→off_hours / 08:00→pre_nxt / 08:59:59→pre_nxt / 09:00→main / 15:29:59→main / 15:30→post_nxt / 19:59:59→post_nxt / 20:00→off_hours (freeze_time) |
| B39 | `test_board_never_uses_session_tracker` | leaf 소스에 `session` 문자열 0(C22) |
| B40 | `test_signal_match_picks_newest_same_ticker` | tail 3건 중 같은 ticker 최신 1건, 다른 ticker 만 있으면 `signal_matched=False` |
| B41 | `test_signal_match_copies_not_references` | 원본 dict 를 변조해도 payload 불변 |
| B42 | `test_payload_has_no_prev_price_and_no_signal_kst` | 두 키 부재(자문 R7) |
| B43 | `test_payload_carries_order_snapshot` | order_no·ordered_qty·order_division·order_path·exchange·board·order_price_won 전부 |
| B44 | `test_account_read_from_settings_not_from_caller` | `observe_order` 시그니처에 계좌 인자 없음 + settings 값이 payload 에 실림 |

#### `tests/unit/engine/test_cycle276_persist_and_markers.py` (16)
| # | 케이스 | 검증 |
|---|---|---|
| B45 | `test_persist_called_exactly_once_on_success` | fake client 정상 응답 → upsert 1회, `result="ok"` |
| B46..B53 | `test_persist_called_on_failure[<reason>]` (8종) | `timeout`/`api_error`/`parse_error`/`schema_error`/`no_bars`/`no_key`/`disabled_model`/`payload_error` 각각 upsert 1회 + `result="failed"` + 그 `reason` + **`input_payload` 비어 있지 않음**(브리프 §3.4) |
| B54 | `test_persist_site_count_is_one` | AST: `_persist_evaluation` 호출 1곳, `_evaluate` 안 |
| B55 | `test_persist_never_raises_when_db_fails` | upsert 가 raise → `_evaluate` 정상 종료 + `[llm_eval_persist] result=error` 1행 |
| B56 | `test_key_risks_and_invalidations_are_persisted` | 모델 응답의 두 필드가 DB 인자에 실린다(C29) |
| B57 | `test_log_format_unchanged_for_risks` | `[llm_buy_score]` 행에 risks/invalidations 필드가 **추가되지 않았다**(20:10 파서 기준선) |
| B58 | `test_score_marker_has_order_no_and_renamed_fields` | `order_no=` 존재 · `slip_bp=` 부재 · `post_order_drift_bp=` 존재 · `order_kst=` 존재 |
| B59 | `test_failed_marker_has_order_no` | `[llm_buy_score_failed] … order_no=` |
| B60 | `test_markers_live_only_in_the_leaf` | 5종 마커 문자열이 leaf 밖 `src/**` 에 0건 |
| B61 | `test_input_payload_is_json_serializable` | `json.dumps(input_payload)` 성공(datetime·Decimal 포함 케이스) |
| B62 | `test_input_payload_is_the_three_build_messages_args` | `{payload, tech, bars30}` 키 정확히 3, `bars30` 길이 ≤ 30, 절단·요약 없음 |
| B63 | `test_prompt_and_feature_version_are_12_hex` | 두 값 길이 12, `[0-9a-f]` |
| B64 | `test_version_computation_failure_is_fail_open` | 계산 실패 monkeypatch → `""` 이고 평가는 계속 |

#### `tests/unit/db/test_cycle276_migration_043.py` (9)
| # | 케이스 | 검증 |
|---|---|---|
| B65 | `test_file_exists_and_is_043` | 파일명·번호, 그리고 **044 가 아직 없거나 cycle275 용**임을 확인 |
| B66 | `test_create_table_if_not_exists` | 정규화 SQL 에 `create table if not exists llm_buy_evaluations` |
| B67 | `test_primary_key_columns` | `primary key (trade_date, account_no, ticker, order_no)` |
| B68 | `test_all_53_columns_present` | 열 이름 전수 |
| B69 | `test_order_no_not_null_default_empty` | `order_no text not null default ''` |
| B70 | `test_four_indexes_if_not_exists` | 4개 인덱스 이름 + `if not exists` |
| B71 | `test_order_no_index_is_partial` | `where order_no <> ''` |
| B72 | `test_no_destructive_statements` | `alter`/`drop`/`update`/`delete`/`truncate` 0건(C31) |
| B73 | `test_pg_harness_docstrings_mention_043` | `pg_harness.py` 문면 3곳 갱신(로직은 glob 이라 변경 0) |

#### `tests/unit/db/test_cycle276_llm_buy_evaluations.py` (10)
| # | 케이스 | 검증 |
|---|---|---|
| B74 | `test_upsert_binds_date_via_to_date` | str `"2026-09-11"` 입력 → `date` 객체 바인딩 |
| B75 | `test_upsert_binds_timestamptz_as_datetime` | `order_kst`/`created_at`/`updated_at` 인자 타입이 `datetime` (str 이면 FAIL) |
| B76 | `test_upsert_binds_jsonb_as_raw_dict` | `input_payload` 인자가 `dict`(문자열 아님) |
| B77 | `test_upsert_normalizes_none_order_no_to_empty` | `order_no=None` → `""` |
| B78 | `test_upsert_sql_on_conflict_targets_pk` | `ON CONFLICT (trade_date, account_no, ticker, order_no)` |
| B79 | `test_upsert_do_update_excludes_created_at` | SET 절에 `created_at` 없음 |
| B80 | `test_get_by_order_returns_latest_when_no_date` | 두 날짜 행 → 최신 1건 |
| B81 | `test_get_by_order_with_trade_date_narrows` | 지정 날짜 1건 |
| B82 | `test_list_by_order_nos_uses_any_text_array` | SQL `= ANY($1::text[])` |
| B83 | `test_list_by_order_nos_empty_input_skips_query` | 빈 리스트 → `pg.fetch` 호출 0 |

#### `tests/unit/db/test_cycle276_trade_pairs_order_nos.py` (8)
| # | 케이스 | 검증 |
|---|---|---|
| B84 | `test_existing_15_keys_unchanged` | 키 이름·타입·값이 base 와 동일 |
| B85 | `test_buy_order_nos_time_ascending` | 분할 매수 2건 → 시간 오름차순 2개 |
| B86 | `test_empty_order_no_excluded_but_row_kept` | `order_no=''` 체결 포함 페어 → 목록에서 제외, **행은 그대로** |
| B87 | `test_pair_key_is_strategy_ticker_first_buy` | 형식 정확 |
| B88 | `test_pair_key_none_when_no_order_no` | 전부 빈 값 → `None` |
| B89 | `test_open_pair_sell_order_nos_is_empty_list` | `[]`(None 아님) |
| B90 | `test_multiple_cycles_do_not_leak_order_nos` | 같은 (ticker,strategy) 3사이클 → 각 페어가 자기 주문만 |
| B91 | `test_buffer_arity_unchanged` | AST: `buy_buf`/`sell_buf` 튜플 요소 3 유지(C41) |

#### `tests/unit/routes/test_cycle276_llm_evaluations_route.py` (13)
| # | 케이스 | 검증 |
|---|---|---|
| B92 | `test_single_returns_200_with_masked_account` | `account_no_masked == "1234****"` |
| B93 | `test_single_response_has_no_raw_account_key` | `"account_no" not in data`(C40) |
| B94 | `test_single_404_when_missing` | 404 + detail 에 order_no |
| B95 | `test_single_500_on_db_exception` | `get_by_order` raise → 500 + `[llm_eval_route_error]` 로그 |
| B96 | `test_single_does_not_swallow_into_404` | DB 예외가 404 로 위장되지 않는다(cycle266) |
| B97 | `test_batch_returns_map_keyed_by_order_no` | 있는 것만 키 존재 |
| B98 | `test_batch_missing_keys_absent_not_null` | 없는 주문번호는 키 자체가 없다 |
| B99 | `test_batch_422_on_zero_order_nos` | `order_nos=""` → 422 |
| B100 | `test_batch_422_on_over_200` | 201개 → 422 |
| B101 | `test_batch_trims_and_dedupes` | 공백·중복 정규화 |
| B102 | `test_numeric_decimal_projected_to_float` | `cost_usd`·`k`·`post_order_drift_bp` 가 JSON 에서 number |
| B103 | `test_route_has_no_auth_code_and_no_exempt_change` | 라우트 소스에 `X-API-Key`/`EXEMPT_PATHS` 0건 |
| B104 | `test_router_registered_in_main` | `main.py` import + `include_router` 각 1 |

#### `tests/integration/test_cycle276_llm_eval_roundtrip.py` (실 PG, 8)
| # | 케이스 | 검증 |
|---|---|---|
| B105 | `test_migration_043_applies_and_is_idempotent` | 043 을 **두 번** 실행해도 오류 0(CI 가 같은 DB 에 반복 적용) |
| B106 | `test_upsert_roundtrip_jsonb_dict_in_dict_out` | `input_payload` dict → dict 복원(codec 실증) |
| B107 | `test_upsert_roundtrip_date_column` | `trade_date` DATE 왕복 |
| B108 | `test_upsert_roundtrip_timestamptz_kst` | `order_kst` 가 `+09:00` ISO 로 렌더 |
| B109 | `test_upsert_rejects_str_timestamp_binding` | str 을 넘기면 `DataError`(cycle273a 재현 방지 — 우리 코드가 str 을 넘기지 않음을 증명) |
| B110 | `test_upsert_conflict_updates_not_duplicates` | 같은 PK 2회 → 1행, 값 갱신 |
| B111 | `test_join_with_trade_history_three_axes` | `(trade_date, ticker, order_no)` 조인 성공 + status 5분류 라벨링 |
| B112 | `test_numeric_returns_decimal` | `cost_usd` 가 `Decimal` |

`clean_llm_buy_evaluations` 픽스처를 `pg_harness.py` 에 `clean_<table>` 관례대로 추가.

#### fake client 규약(공통)
- **OpenAI 실호출 금지.** `llm_buy_gate._get_client` 를 monkeypatch 해 `chat.completions.create` 가
  미리 준 응답/예외를 돌려주는 fake 를 주입한다. `usage.prompt_tokens`/`completion_tokens` 를 갖는다.
- 시간은 `freeze_time` 으로 고정하고 `_monotonic` **이름만** monkeypatch 한다(전역
  `time.monotonic` 패치 금지 — cycle274 파인딩 #4).
- `caplog` 개수 단언은 `r.levelno >= WARNING ∧ msg.startswith("[marker] ")` 로 한정(CI 루트 로거 DEBUG).

### 11.2 프론트 (31건)

#### `frontend/src/components/__tests__/LlmEvaluationModal.test.tsx` (12)
| # | 케이스 | 검증 |
|---|---|---|
| F1 | `renders score, min_score and would_block` | `llm-eval-score` 문면 |
| F2 | `renders rationale, risks, invalidations` | 3 섹션 |
| F3 | `renders order snapshot fields` | 주문가·수량·구분·경로·보드·목표가 |
| F4 | `renders meta with model tokens cost latency versions` | |
| F5 | `payload toggle hides content by default and reveals on click` | |
| F6 | `raw response toggle works` | |
| F7 | `failed record shows reason prominently` | `llm-eval-failed` |
| F8 | `404 renders grey notice not red error` | cycle266 분기 |
| F9 | `500 renders red error` | |
| F10 | `ESC closes the modal` | `keydown` Escape |
| F11 | `overlay click closes, panel click does not` | |
| F12 | `multiple order numbers render tabs and the first-buy notice` | `llm-eval-order-tab-*` + 문면 |

#### `frontend/src/components/__tests__/TradeHistoryGrid.test.tsx` (+6)
| # | 케이스 | 검증 |
|---|---|---|
| F13 | `renders AI 자문 column header` | |
| F14 | `BUY row with evaluation shows enabled button` | |
| F15 | `BUY row without evaluation shows disabled button with 평가 기록 없음` | |
| F16 | `SELL row shows disabled button with 매수 주문만 평가 대상` | |
| F17 | `batch summary query fires once per page` | MSW 요청 카운트 == 1 |
| F18 | `clicking the button opens the modal with that order_no` | |

#### `frontend/src/components/__tests__/TradePnLGrid.test.tsx` (+6)
| # | 케이스 | 검증 |
|---|---|---|
| F19 | `renders AI 자문 column and uses buy_order_nos` | |
| F20 | `pair with empty buy_order_nos is disabled` | |
| F21 | `pair with 2 buy orders shows (2) badge` | |
| F22 | `batch query flattens all buy_order_nos of the page into one request` | |
| F23 | `existing 13 columns and pnl-summary testids unchanged` | 회귀 |
| F24 | `open pair row keeps bg-emerald-50/40` | 회귀 |

#### 가드·목 (4)
| # | 파일 / 케이스 | 검증 |
|---|---|---|
| F25 | `_ast_api_mocks_coverage.test.ts` G-AST10 | `api/llm-evaluations.ts` 가 리터럴을 호출 + `isRouteRegistered('/api/llm-evaluations')` |
| F26 | `_ast_useQuery_retry_required.test.ts` | `TARGET_FILES` 에 `LlmEvaluationModal.tsx`·`TradeHistoryGrid.tsx`·`TradePnLGrid.tsx` 등재 + 각 `retry:` 명시 |
| F27 | `designSystem.v2.test.ts` (회귀) | 신규 파일 포함 구 hex 4종 0건 · `accentColor` 사이트 정확히 5 |
| F28 | `handlers.honesty.cycle276.test.ts`(신규) | MSW `/api/history` 기본 응답이 `trades`+`total_pages` 키를 갖는다(= `items` 부정직 재발 차단) |

#### `e2e/history.spec.ts` (신규, G-E2E-10) (3)
| # | 케이스 | 검증 |
|---|---|---|
| F29 | `체결 탭에서 AI 자문 버튼을 눌러 모달을 연다` | `installApiMocks` → `/history` → 버튼 클릭 → `llm-eval-modal` `toBeVisible({timeout:20000})` → 점수 문면 → `not.toContainText("NaN")` |
| F30 | `매매손익 탭에서 다중 주문 페어의 탭이 보인다` | LIFO 오버라이드로 `buy_order_nos` 2건 주입 |
| F31 | `평가 기록 없는 행의 버튼은 비활성이다` | `toBeDisabled()` |

모든 `.toBeVisible()` 에 **명시 timeout**(`test_e2e_spec_timeout_required.py`).

---

## 12. 뮤테이션 후보 (25종 — 전부 KILL 되어야 한다. M21~M25 = 검증 라운드 3 추가)

| # | 뮤테이션 | 죽이는 케이스 |
|---|---|---|
| M1 | 훅 2곳 중 **폴백 경로 훅 삭제** | B1, B16 |
| M2 | 훅을 `_insert_pending_buy_or_absorb_race` **뒤로 이동** | B8, B9 (자문 R9 필수 KILL) |
| M3 | 훅을 `already_completed` 판정 **뒤로 이동** | B7 |
| M4 | 훅 호출부 `try/except` 제거 | B10, C3 행위 동등 테스트 |
| M5 | 폴백 훅의 `except Exception` → `except KisApiError` | B10 + non-KisApiError 주입 시 pending 좀비 |
| M6 | 훅에 `await` 추가(`await llm_buy_gate...`) | B4, B9 |
| M7 | 래치 키를 `(strategy_id, ticker)` 로 되돌리기 | B34 |
| M8 | `order_no` 빈 값에도 평가 진행 | B32 |
| M9 | `_persist_evaluation` 을 성공 경로에서만 호출 | B46~B53 |
| M10 | 실패 기록에서 `input_payload` 를 `{}` 로 비우기 | B46~B53 (payload 비어 있지 않음 단언) |
| M11 | PK 에서 `trade_date` 제거 | B67, B110 |
| M12 | `order_no` 를 `NULL` 허용으로 완화 | B69, B77 |
| M13 | `CREATE TABLE`/`CREATE INDEX` 의 `IF NOT EXISTS` 제거 | B66, B70, B105 |
| M14 | 라우트 응답에서 마스킹 제거(원문 `account_no` 노출) | B92, B93 |
| M15 | 라우트 DB 예외를 `except Exception: return None` 으로 삼켜 404 | B95, B96 |
| M16 | `key_risks`/`invalidations` 를 다시 `_` 로 버리기 | B56 |
| M17 | `post_order_drift_bp` 를 `slip_bp` 로 되돌리기 | B58 |
| M18 | `get_trade_pairs` 버퍼를 4-튜플로 바꾸기 | B91 + 기존 페어 회귀 |
| M19 | 프론트 배치 조회를 행별 개별 조회로 | F17, F22 |
| M20 | MSW `/api/history` 를 다시 `items` 로 | F28 |
| M21 | `_to_dt` 의 `isinstance(value, str)` 분기를 `return value` 로 | `test_d2a` · `test_i14`(검증 라운드 3 #1) |
| M22 | `_to_dt` 의 `raise TypeError` 를 `return value` 로 | `test_d2b` · `test_i15` |
| M23 | `_prompt_version` 해시 blob 에서 `_SNAPSHOT_KEYS` 제거 | `test_c30_2b`(검증 라운드 3 #4) |
| M24 | `schema_version` 리터럴을 `cycle274.1` 로 되돌리기 | `test_c30_2c` |
| M25 | cap 초과 분기의 `_emit_persist(..., "cap_exceeded")` 삭제 | `test_c19_4b`(검증 라운드 3 #3) |

### 12.1 뮤테이션 실행 규약 (검증 라운드 3 #5 — 실측으로 확인된 함정)

코드 **재배치형** 뮤테이션(바이트 수 불변)을 넣고 1초 안에 원복하면 `.pyc` 헤더의 `(source mtime, size)`
가 원본과 일치해 **stale bytecode 가 그대로 재사용된다**. 실측 — 원복 뒤 캐시된
`src/engine/__pycache__/order_engine.cpython-313.pyc` 를 디스어셈블하니 첫 `observe_order` 가 459행(= 훅을
INSERT 뒤로 옮긴 mutant)인데 소스는 434행이었고, `pytest tests/unit` 이
`test_c3_5_hook_fires_before_pending_insert` 를 **결정적으로** 붉혀 없는 코드 결함처럼 보였다.
그대로 믿으면 없는 결함을 보고하거나(false KILL) 있는 구멍을 놓친다(false ESCAPE).

```bash
# 뮤테이션 주입/원복 전후에 항상
find . -name __pycache__ -type d -prune -exec rm -rf {} +
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q <대상>
```

원복 뒤에는 `cmp <원본 사본> <대상 파일>` 로 byte 동일까지 확인한다(sha 핀만 보면 재배치형은 구별되지만
캐시 오염은 드러나지 않는다).

---

## 13. 관측 · 롤백 · D+1 서명

### 13.1 마커 5종

| 마커 | 레벨 | 빈도 | 의미 |
|---|---|---|---|
| `[llm_gate_config]` | INFO | 1회/(전략, mode, min_score)/일 | 적용값 카나리아. **5전략에서 `mode=off` 로 추가 발화**(C16) |
| `[llm_gate_daily_cap]` | WARNING | 1회/전략/일 | 일일 cap 도달 |
| `[llm_buy_score]` | INFO | 주문당 1 | `order_no=` 추가 · `post_order_drift_bp=` 개명 · `order_kst=`/`order_price=` 정직화 |
| `[llm_buy_score_failed]` | INFO | 주문당 1 | `order_no=` 추가 |
| `[llm_eval_persist]` | INFO | 주문당 1 (+ 빈 order_no·cap 초과 시 1) | `order_no= result=ok\|error [reason=]` — DB 무음을 깨는 유일 채널. `reason=empty_order_no`(C21) / `reason=cap_exceeded`(검증 라운드 3 #3)는 평가를 시작하지 않은 주문이라 **DB 행 0** 이고, 그 둘이 없으면 "cap 때문에 평가 안 함" 과 "게이트가 off" 를 주문 단위로 구별할 수 없다 |

### 13.2 롤백 (코드 재배포 불필요)

1. **전략별 즉시 롤백** = `PUT /api/strategies/{volatility_breakout|long_tail_volatility}/params
   {"llm_gate_mode":"off"}` — 라우트가 in-memory `config.params` 를 덮으므로 **즉시** 반영.
   `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**(cycle232 D6 → 장중 실효 수단은 PUT).
   확인 = 다음 매수 주문에서 `[llm_gate_config] mode=off` 1행 + `[llm_buy_score]` 0행.
2. **전면 중단** = `settings.openai_buy_gate_model` 을 빈 값으로 → `reason=disabled_model` 로
   전건 실패 기록(행위 0, 비용 0). 또는 `openai_api_key` 미설정 → `reason=no_key`.
3. **DB 기록만 중단** — 별도 스위치를 두지 않는다(스위치를 늘리면 "설정이 없으면 관측이 사라지는"
   P0-1 계열 경로가 하나 더 생긴다). 기록 실패는 `[llm_eval_persist] result=error` 로 시끄럽게 남는다.
4. **마이그레이션 롤백 없음** — 가산형이라 되돌릴 것이 없다(테이블을 지우지 않는다).

### 13.3 D+1 서명 (배포 다음 영업일 확인 목록)

1. `[llm_gate_config]` — VB·LTV 각 **1행** `mode=shadow`(+ 다른 5전략에서 `mode=off` 행이 보일 수 있다.
   이것이 정상이다). VB·LTV 행이 없으면 **두 전략이 `enabled=false` 로 되돌아간 것**(cycle274 Q1).
2. `[llm_buy_score]` 행 수 == 그날 VB·LTV **매수 주문 수**(cycle274 의 "신호 수" 가 아니다).
   `order_no=` 가 전 행에 실려 있고 `trade_history` 의 그날 BUY `order_no` 집합과 **일치**.
3. `[llm_eval_persist] result=ok` 행 수 == `[llm_buy_score]` + `[llm_buy_score_failed]` 행 수.
   `result=error` 가 1건이라도 있으면 즉시 원인 확인(테이블 미적용·바인딩 오류 후보).
4. `SELECT count(*) FROM llm_buy_evaluations WHERE trade_date = <D>` == 위 3번의 `result=ok` 수.
5. `SELECT count(*) FROM llm_buy_evaluations e JOIN trade_history t
   ON t.ticker=e.ticker AND t.order_no=e.order_no AND t.trade_type='BUY'` — **조인 성공률 100%**
   (cycle274 의 50% → 100% 가 이 사이클의 1차 목표).
6. `slip_bp` 문자열이 그날 로그에 **0건**(개명 완료 서명).
7. UI — `/history` 체결 탭에서 그날 BUY 행의 "AI 자문" 버튼이 **활성**이고 모달이 점수를 보여준다.
   매매손익 탭 open 페어에서도 동일.
8. 비용 — `[llm_buy_score]` 의 `cost_usd` 합계가 하루 **$0.05 미만**(주문 ≈3건/일 기준).
   `cost_usd=-1.000000` 이 보이면 모델이 `log_analysis_engine._OPENAI_PRICING` 에 미등록.
9. `[llm_gate_daily_cap]` **0행**(cap 20 vs 실측 주문 ≈3 = 6배 여유).
10. `execute_buy` 실패 로그(`매수 주문 잔고부족`·`지정가 폴백도 거부` 등) 건수가 **배포 전과 같다**
    — 훅이 매매 경로에 영향을 주지 않았다는 실측 서명.

### 13.4 기준선 재설정 고지(보고서에 반드시 싣는다)

- `[llm_gate_config]` 행 수 기준선이 2 → 최대 7 로 늘어난다(5전략 `mode=off`).
- `[llm_buy_score]` 의 모집단이 **신호 → 주문**으로 바뀌어 행 수가 약 절반이 된다.
- `slip_bp`(구) 와 `post_order_drift_bp`(신)는 **부호 의미가 반대**다 — 합산 금지.
- `signal_kst`/`signal_price` 필드는 사라졌다. `order_kst`/`order_price` 로 대체.

### 13.5 판정 기간 (자문 §2.6 검정력 — 결정 카드에 그대로 싣는다)

주문 ≈ 3.0/영업일, sd(profit_rate) ≈ 2.7%p.

| 구간 | 왕복 수 | 구간당 | TE SE | 검출 가능 |
|---|---|---|---|---|
| 2주 | 30 | 10 | ±0.85%p | **2%p 차이도 1.7σ = 임계 검증 불가** |
| 6주 | 90 | 30 | ±0.49%p | 2%p 이상만 2.9σ, 1%p 는 1.4σ(p≈0.15) |
| 12~16주 | 180~240 | 60~80 | ±0.35%p | 1%p 급 |

프로토콜 = **S1 2주**(배관·비용·`verdict_lag` p50/p95·`post_order_drift` 분포·점수 분포·
**주문 모집단 커버리지** — 여기서 기각 가능) → **S2 +4주**(방향: Spearman 단조성 + 2%p 급 분리) →
**S3 +6주**(전략별 임계 확정). **2주 실측으로 임계 70 을 결정하지 않는다.**

---

## 14. 이 명세가 브리프·이해와 다르게 잡은 것 (근거 포함)

1. **A-ATOMIC 좌표 정정** — 브리프 `:272~:314` → 실제 `:313~:354`. 대상은 동일하고 좌표만 정정.
   가드는 라인 리터럴이 아니라 AST 동적 경계로 잰다.
2. **`slip_bp` → `post_order_drift_bp` 개명** — 브리프 §3.9 는 `order_no=` 추가만 말했으나
   자문 조건 ③(부호 의미 반전 합산 사고 방지)을 수용해 확장했다.
3. **`board` 는 `session_tracker` 가 아니라 시계 파생** — leaf 의 8영역 import 금지(C22, `test_c17_4`
   가 문자열 검사라 지연 import 도 불가)와 cycle264 의 30초 stale 실증 둘 다를 만족하는 유일한 해.
4. **`prev_price_won`·`target_offset_won` 삭제, `target_won`/`k` 는 `buy_signals` 역참조 시에만** —
   주문 시점에 복구 불가하거나(`prev_price`) 존재하지 않는(`target_offset`) 값을 그럴듯하게 남기지 않는다.
   `signal_matched` 로 있음/없음을 정직하게 표시한다.
5. **`buy_order_no`(단수) → `buy_order_nos`/`sell_order_nos`/`pair_key`** — 브리프 §8 이 이미 정정한
   내용을 그대로 따랐다(운영 DB 실측 9건이 매수 2주문 페어).
6. **`src/routes/history.py` 는 0줄** — 브리프 §4 수정 목록에 있으나 코드를 건드릴 이유가 없다.
7. **`account_no` = CANO 만 PK, `account_product` 는 별도 비-PK 열** — PK 를 단순하게 유지하면서
   상품코드도 잃지 않는다.
8. **마스킹 방향은 브리프대로 앞 4자리** — 리포 기존 두 헬퍼(뒤 4자리)와 반대이므로 **재사용하지 않고
   별도 헬퍼 `mask_account_no`** 를 만든다(두 관례가 섞이지 않게).
9. **order_engine 흡수기는 `logger.debug(exc_info=True)`** — cycle274 전략 호출부의
   `trace_observer_failure(cap=None)` 과 동작이 동등하면서 import 증가분을 1줄로 묶는다.
10. **`eval_kind` 열을 지금 넣는다** — 브리프 §3.5 의 enforce 전방 호환과 운영 DB 의 `order_no=''`
    수기 체결 행이 미래에 같은 PK 공간에서 충돌하는 것을 선제 분리(자문 R2).

---

## 15. 후속 (cycle276 검증 라운드 2 이후, 2026-09-11)

### 15.1 이번에 시정한 것

| # | 무엇 | 어디 |
|---|---|---|
| A-1 | LLM 평가 전건 실패 — 추론 토큰이 출력 한도를 먹는다. `_MAX_COMPLETION_TOKENS` 400 → **2000** + 신규 실패 사유 **`truncated`**(+ 마커 `finish=`) | `src/engine/llm_buy_gate.py` |
| A-2 | 시가 기준가 확보 5분 공백. `MAIN_REST_BASIS_FAST_ROUNDS` 9 → **19**(09:00:35~09:09:35 연속) | `src/engine/open_price_rest.py` |
| B-1 | `buy_signals_tail=list(state.buy_signals[-3:])` → **전량 전달**(전략이 이미 20건 cap) | `src/engine/order_engine.py` 2곳 |
| B-2 | 배치 요약과 상세의 날짜 축 비대칭. 배치가 `(trade_date, order_no)` 쌍 전부를 돌려주고 응답 키가 `"<날짜>\|<주문번호>"` 복합 키 | `src/db/llm_buy_evaluations.py` · `src/routes/llm_evaluations.py` · 두 그리드 |
| B-3 | `trade_date` 파싱 실패가 200 + 최신 1행 → **422** | `src/routes/llm_evaluations.py` |
| B-4 | `signal_time_kst` → **`signal_time_local`**(tz-naive 로컬 시각, KST 보장 없음) | migration 043 · db · 라우트 · leaf · 프론트 |
| B-5 | 자매 핀 dict 의 "(비어 있음 …)" 주석이 사실과 달랐다 | `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` |

### 15.2 고치지 않고 남기는 것 (판단 기록)

1. **`encodeURIComponent` 부재** (`api/llm-evaluations.ts` 의 `/${orderNo}` 보간) — KIS ODNO 는 숫자열이고
   값의 원천이 우리 DB·KIS 응답뿐이어서 경로 구분자가 섞일 경로가 없다. 지금 넣으면 방어가 아니라
   "언젠가 문자열이 올 수 있다" 는 잘못된 신호를 남긴다. 외부 입력이 이 경로에 닿는 날 함께 넣는다.
2. **`TradePnLGrid` 멀티데이 탭 안내 문구** — 멀티데이 피라미딩 페어의 둘째 매수(다른 날 주문)는 이 행에서
   열 수 없고 현재 title 이 "다른 날짜의 평가 기록" 이라고만 말한다. 어느 주문이 몇 건 빠졌는지까지
   쓰려면 페어 단위로 날짜별 요약을 다시 조회해야 해서 배치 1요청 규약과 상충한다. 실측 사례가
   9건/614행(1.5%)이라 문구 정교화의 값이 비용보다 작다.
3. **`cap_exceeded` 어휘의 DB 무행** — `[llm_eval_persist] result=error reason=cap_exceeded` 는 주문마다
   1행을 로그에 남기지만 DB 행은 없다(평가를 시작하지 않았으므로 담을 outcome 이 없다). 로그와 DB 의
   주문 집합이 달라지는 유일한 지점이다. cap 20 vs 실측 주문 ≈3/일이라 도달이 0 이므로 그대로 둔다 —
   enforce 로 가거나 cap 도달이 실제로 관측되면 `result='skipped'` 행으로 분리한다.
4. **`prompt_version` 해시 범위** — SYSTEM 프롬프트 + user 프리앰블 + `_SNAPSHOT_KEYS` 만 넣고 user
   템플릿 **본문**은 넣지 않는다. 본문만 바뀌고 해시가 같으면 층화가 두 프롬프트를 섞는다. 지금은
   본문이 프리앰블과 같은 함수에 있어 함께 바뀌므로 실효 위험이 낮고, 해시 범위를 넓히면 과거 행의
   버전 값이 전부 무효가 되어 회귀 비교선이 끊긴다. 프롬프트를 본격적으로 A/B 할 때 재설계한다.
