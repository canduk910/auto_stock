# cycle363 — 영업일 기준 신선도(①) + 일봉 신선도를 직전 영업일 기준으로(①′) 작업 지시서

> 작성: team-leader, 2026-09-25 (금, 추석 휴장). 사용자 결정 2026-09-25 = D4 카드1 (가) · 카드2 (나) + 추가 선택 「①′ 도 같이」.
> **09-28(월, 연휴 뒤 첫 영업일) 07:45 부팅 전 배포**가 목표다.
> 설계 정본 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.5·§3 표 ①·①′·§5 단계 1·§8(161~165행)·§6.
> 이 문서는 하위 에이전트(tdd-engineer · backend-dev · tester · report-writer) 공용 지시서다.

---

## 0. 한 줄 요약

월요일·연휴 뒤 아침에 **목요일(또는 그 전) KRX 값이 금요일 값을 덮는 것**과 **연휴 뒤 일봉이 전부 KIS 100봉 폴백으로 빠지는 것**을 막는다.
판정 기준을 「몇 시간 지났나」·「달력 며칠 지났나」에서 「**직전 영업일** 정기 실행/봉이 있나」로 바꾼다.

## 1. 경계 (절대 규칙)

- 🔴 **청산 규약 불변.** `check_exit_signal`·손절·트레일링·`_entry_atr` 경로 무접촉. 바뀌는 것은 「부팅 즉시 실행을 할까 말까」와 「prepare 가 DB 봉을 쓸까 KIS 로 갈까」뿐이다.
- 🔴 **+600초 재준비(`evening_funnel_capture` 즉시 1회)는 건드리지 않는다.** 게이트 추가 금지(②③ 는 단계 3, 카드3 결정 뒤). F-10-2 의 evening_funnel·purge 무게이트는 그대로 유지.
- 🔴 **8영역·`scheduler.py` 무접촉.** (`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**` · `src/engine/scheduler.py`). 불가피하면 **멈추고 반환**한다.
- 🔴 **master(16:30) · financial(16:40) 은 현행 시간 게이트 유지**(범위 밖). `IMMEDIATE_FRESH_SKIP_HOURS=20.0` 상수는 master 가 계속 쓴다.
- 다른 에이전트가 `tools/archive/`·`data/`·`.gitignore`·`_workspace/00_URGENT_WORKLIST.md` 를 쓰고 있다 — **건드리지 않는다.** `git add`·`git stash`·`git checkout --`·`git commit`·`git push` 금지(메인 세션 몫).

## 2. 설계

### 2.1 새 leaf — `src/engine/trading_calendar.py`

휴장일 판정 공용 leaf. 8영역 import 0.

- 조회 seam = 모듈 전역 `async def _lookup_open(d: date) -> bool | None` → `src.api.condition.is_trading_day(d)` (기존 3상태 함수 재사용: True=개장 / False=휴장 / None=모름).
  - `boot_manager._previous_trading_day` 는 **재사용하지 않는다** — 그 함수는 조회 실패를 「영업일」로 삼키는 관측용 fail-open 이라 「실패 → 실행」을 표현할 수 없다(`is_market_open` 이 실패 시 True). 그 함수는 **무접촉**.
- 메모: 모듈 전역 `dict[date, bool]` — **True/False 만 캐시**(날짜의 개장 여부는 바뀌지 않는다), None 은 캐시하지 않는다. 40일보다 오래된 키는 삽입 시 정리. KIS 공지 「CTCA0903R 은 가급적 1일 1회」 → 날짜당 프로세스 수명 1회.
- 주말(`weekday() >= 5`)은 **조회 없이** 휴장.
- API (전부 never-raise, 예외 → None):
  - `async def is_open_day(d: date) -> bool | None`
  - `async def previous_trading_day(today: date) -> date | None` — `today` 보다 엄격히 이전의 가장 최근 개장일. 최대 10일 역산. 도중 None 을 만나면 None(모름).
  - `async def latest_passed_trading_slot(now_kst: datetime, slot: time) -> datetime | None` — `now` 이하인 「개장일 D 의 slot 시각」 중 가장 최근(KST aware). `now.time() >= slot` 이면 오늘부터 검사(오늘 개장 여부 조회, None → None), 아니면 `previous_trading_day(today)` 의 slot.
  - `def _reset_cache_for_tests() -> None`
- naive `datetime.now()` 금지(KST 강제).

### 2.2 ① `task_loop_helper.run_periodic_task_loop` — 영업일 슬롯 게이트

신규 키워드 3개 (기존 `immediate_skip_if_fresh_hours` 는 그대로, master·financial 이 계속 사용):

| 인자 | 기본 | 뜻 |
|---|---|---|
| `immediate_skip_if_fresh_since_trading_slot: bool` | False | True 면 슬롯 = **`wait_time`**(= scheduler `TIME_*` 정본, 새 시각 리터럴 금지). 마커 ≥ `latest_passed_trading_slot(now, wait_time)` 이면 immediate skip |
| `immediate_force_run_check: Callable[[], Awaitable[bool]] \| None` | None | True 반환 또는 예외면 무조건 실행(full_universe 행 수 하한) |
| `immediate_skip_if_marker_absent: bool` | False | 마커가 **없을 때**(None) skip 할지. full_universe 부트스트랩 전용(§2.3) |

- `immediate_skip_if_fresh_hours` 와 `immediate_skip_if_fresh_since_trading_slot=True` 동시 지정 = 프로그래밍 오류 → 함수 진입 즉시 `ValueError`.
- 슬롯 모드 판정 순서 (immediate 블록, stagger sleep 뒤 · once 앞):
  1. `immediate_force_run_check` 가 있으면 await → True/예외 → **RUN** `reason=below_floor` / `force_check_error`
  2. 마커 조회(`get_task_last_success(task_label)`) 예외 → **RUN** `reason=marker_error`
  3. 마커 None → `immediate_skip_if_marker_absent` 면 **SKIP** `reason=no_marker`, 아니면 **RUN** `reason=no_marker`
  4. 마커 파싱 실패 → **RUN** `reason=marker_unparseable`
  5. 마커 > now(KST) → **RUN** `reason=future_marker` (시계 이상 방어, 기존 F9 와 같은 정신)
  6. `latest_passed_trading_slot(now, wait_time)` None → **RUN** `reason=calendar_unknown` (🔴 사용자 지시: 휴장일 조회 실패 = 실행 쪽)
  7. 마커 ≥ 슬롯 → **SKIP** `reason=fresh`, 아니면 **RUN** `reason=stale`
- 관측 로그(INFO, 판정마다 1행): `[immediate_gate] task=<label> decision=run|skip reason=<위 어휘> marker=<iso|None> slot=<iso|None>`. SKIP 이면 기존 grep 연속성을 위해 `[<label>] immediate run skip — <reason> last_success=<iso|None>` 1행도 남긴다(`reason=fresh` 일 때 기존 문자열과 동일).
- 마커 기록: 지금은 `immediate_skip_if_fresh_hours is not None` 일 때만 기록한다 → **시간 모드 또는 슬롯 모드**면 기록(immediate 성공 + while 성공 양쪽). 기록 실패 graceful 유지.
- 🔴 정기 while 루프 발화는 게이트와 무관(F-8 불변).

### 2.3 ① `data_load_tasks.py` 배선

| wrapper | 변경 |
|---|---|
| `stock_master_daily_load_task_loop` | `immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS` → `immediate_skip_if_fresh_since_trading_slot=True` (슬롯 = 20:30) |
| `stock_master_basics_refresh_task_loop` | 같음 (슬롯 = 16:10) |
| `full_universe_load_task_loop` | **신규** `immediate_skip_if_fresh_since_trading_slot=True` (슬롯 = 20:00:05) + `immediate_force_run_check=<행 수 하한 판정>` + `immediate_skip_if_marker_absent=True` |
| master · financial | 무변경 (시간 게이트) |
| purge · evening_funnel | 무변경 (게이트 없음 — F-10-2 유지) |

- 행 수 하한: 모듈 상수 `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000`. 판정 = `stock_master.count_active() < 2000` → 실행. `count_active` 는 예외 시 0 을 돌려주므로 DB 장애 = 실행(fail-safe). 근거 한 줄: 운영 3,583행 · 2026-08-08 degrade 사고 60행 — 정상 운영보다 한참 아래, degrade 보다 한참 위.
- **부트스트랩(설계 결정, team-leader)**: full_universe 는 지금까지 마커를 한 번도 남긴 적이 없다(`market_ops` 가 「영구 결측」으로 다룬다). 09-28 이전에 거래일이 없으므로 09-28 07:45 에 마커가 없다. 「마커 없음 = 실행」이면 **09-28 에 09-22 KRX 값 덮어쓰기가 그대로 일어나** 사용자가 카드2 (나)를 고른 이유가 사라진다. 그래서 full_universe 만 「마커 없음 + 행 수 ≥ 하한 → skip」이다. 근거: full_universe 즉시 실행이 실제로 한 일은 월요일 전량 덮어쓰기뿐이었다(10거래일 실측, 평일 `fetched=0`), 자가 치유는 행 수 하한이 맡는다, 신규 상장 유입은 20:00 정기 실행이 계속 맡는다. 09-28 20:00:05 정기 실행이 첫 마커를 남긴다. daily·basics 는 마커 없음 = 실행(현행) 유지.
- 🔴 `once_callable`(= `scanner._full_universe_load_once`) 무접촉 — 게이트는 헬퍼·wrapper 쪽이다.

### 2.4 ①′ `stock_master_daily.get_recent_daily_normalized` — `expected_head`

- 시그니처: `get_recent_daily_normalized(ticker, days, *, min_required=None, expected_head: date | None = None)`.
- 2번 신선도 게이트만 바뀐다:
  - `expected_head is not None` → `latest < expected_head` 이면 KIS 폴백(`reason=stale`, 어휘 유지).
  - `expected_head is None` → 현행 달력 판정(`(today − latest).days > DAILY_STALENESS_DAYS`) **바이트 동일**(하위 호환).
- 락 게이트(1)·min_required 게이트(3)·`_kis_fallback`·`DAILY_STALENESS_DAYS=4` 무변경.
- 알려진 부작용(테스트로 고정): **하루치 결손도 폴백**으로 잡힌다(`latest = expected_head − 1영업일` → 폴백). 전 종목 헤드가 하루 밀린 날(저녁 적재 결손)엔 전 종목 KIS 폴백 — 값은 맞아지지만 prepare 가 느려진다(`[daily_head_stale]` 가 같은 날 알린다).

### 2.5 ①′ 6전략 prepare 배선

- `StrategyBase` 에 `async def _resolve_expected_daily_head(self) -> date | None` — `trading_calendar.previous_trading_day(today_kst())`, never-raise(예외 → None), INFO 1행 `[prepare_expected_head] strategy=<id> expected_head=<YYYY-MM-DD|None>`.
- 6전략 prepare(VB `volatility_breakout.py:290` · LTV `long_tail_volatility.py:328` · donchian `donchian_swing.py:405` · BFB `bull_flag_breakout.py:312` · VCP `vcp_breakout.py:398` · kojiro `kojiro.py:345`)가 **gather 전에 1회** 계산해 `_fetch_one` 안의 `get_recent_daily_normalized(..., expected_head=expected_head)` 로 넘긴다(종목마다 조회 금지 — 메모가 날짜당 1회를 보장하지만 호출도 prepare 당 1회).
- **범위 밖(현행 달력 판정 유지)**: `kojiro.py:768`(`recompute_held_atr` 계열) · `llm_buy_gate.py:1011` · `tools/`. 보고서에 명시.
- momentum 은 일봉 미사용 — 무접촉.

## 3. 테스트 (tdd-engineer Red → backend-dev Green)

### 3.1 시각·휴장일 고정 시나리오 (벽시계 의존 금지 — 시각은 인자/패치로 고정)

2026-09 달력: 09-21(월)~09-23(수) 개장, **09-24(목)·09-25(금) 휴장(추석)**, 09-26(토)·09-27(일) 주말, 09-28(월) 개장. 09-18(금) 개장.

| # | 시나리오 | 기대 |
|---|---|---|
| (1) | 월 09-21 07:45 · basics 마커 금 09-18 16:24 · daily 마커 금 09-18 20:32 · full_universe 마커 금 09-18 20:00:40 | 셋 다 SKIP `reason=fresh` |
| (2) | 화 09-22 07:45 · 마커 월 09-21 (16:24/20:32/20:00:40) | 셋 다 SKIP |
| (3) | **09-28 07:45** · 마커 09-23 (16:24/20:32) · full_universe 마커 없음 · 행 수 3,583 | 셋 다 SKIP (full_universe = `reason=no_marker`) |
| (4) | 월 09-21 07:45 · daily 마커 목 09-17 20:32 (금 적재 실패) | daily RUN `reason=stale` |
| (5) | 휴장일 조회 None · 조회 예외 (각각) | RUN `reason=calendar_unknown` |
| (6) | full_universe · 행 수 1,999 (마커 fresh 여도) · `count_active` 예외(0) | RUN `reason=below_floor` |
| (7) | full_universe · 마커 없음 · 행 수 < 하한 | RUN |
| (8) | 같은 날 재기동: 화 17:00 · basics 마커 화 16:24 → SKIP / 마커 월 16:24 → RUN | |
| (9) | 미래 마커 | RUN `reason=future_marker` |
| (10) | 시간+슬롯 동시 지정 | `ValueError` |
| (11) | 슬롯 모드 성공 시 마커 기록(immediate·while 양쪽), 기록 실패 graceful | |
| (12) | 슬롯 모드에서도 while 정기 발화는 무조건 | F-8 동형 |
| (13) | leaf: 주말은 조회 0회 · 같은 날짜 두 번째 조회는 seam 호출 0회 · None 은 캐시 안 함 · 09-28 기준 `previous_trading_day` = 09-23 · 조회 예외 → None | |
| (14) | ①′: 09-28, `latest=09-23`, `expected_head=09-23` → **DB 경로(폴백 0)** · `days=250` 요청이 DB 250행 그대로 반환(VCP full 보존) | |
| (15) | ①′: `latest=09-22`, `expected_head=09-23` → `reason=stale` 폴백 (하루치 결손도 폴백 — 부작용 고정) | |
| (16) | ①′: `expected_head=None`, 09-28, `latest=09-23` → 현행 달력 판정 = 폴백 (하위 호환 고정) | |
| (17) | ①′: 락 게이트가 여전히 신선도보다 먼저 | |
| (18) | 6전략 prepare 가 `expected_head=<previous_trading_day>` 를 어댑터에 넘긴다 · 휴장일 모름이면 `None` 을 넘긴다 · prepare 당 leaf 호출 1회 | |

### 3.2 테스트 인프라

- 🔴 **leaf 조회 seam 전역 중립화**(cycle295·317 교훈 — 게이트 넣는 사이클이 같이 만든다): `tests/conftest.py` autouse 픽스처가 `src.engine.trading_calendar._lookup_open` 을 **None(모름)** 으로 바꾸고 메모를 비운다. 옵트아웃 마커 `real_trading_calendar`(`pyproject.toml` markers 에 **같은 커밋**으로 등재 — `filterwarnings=error` 라 미등록 마커는 스위트 실패). 기존 테스트는 이 중립화 아래에서 ①′ 는 현행 달력 판정(`expected_head=None`), 슬롯 게이트는 `calendar_unknown → RUN` 을 본다.
- 벽시계 의존 금지: `now` 는 `task_loop_helper` 안에서 `datetime.now(KST)` 로 읽으므로 테스트는 그 모듈의 `datetime` 을 패치하거나(freezegun 은 asyncio 결합 hang 교훈 — 기존 cycle193 테스트 방식 참고) leaf 쪽에 `now` 를 주입해 고정한다. 로컬 23:5x / CI 00:0x 모두 같은 결과여야 한다.
- AST 가드 신규(파일 `tests/unit/ast/test_cycle363_ast_business_day_gate.py` 권장):
  - daily·basics·full_universe wrapper = 슬롯 kw True, 시간 kw **없음** / master·financial = 시간 kw / purge·evening_funnel = 게이트 kw 전무.
  - full_universe = `immediate_force_run_check` + `immediate_skip_if_marker_absent=True`.
  - 6전략 prepare 의 `get_recent_daily_normalized` 호출에 `expected_head` kw.
  - leaf naive `now()` 0 · 8영역 import 0.
- 기존 가드 개정(**값·목록만, 사유는 테스트 주석 + history**):
  - `tests/unit/ast/test_cycle193_ast_fresh_gate.py` F-10-1/F-10-2 — full_universe 가 무게이트 목록을 떠난다. 개정 사유 = 「TTL 멱등이라 즉시 실행이 저렴」이 실측과 다르다(10거래일 중 월요일 2회 전량 덮어쓰기, 09-21 은 목요일 KRX 값) · 자가 치유는 행 수 하한으로 보존 · 근거 = cycle360 메모 §1.1·§1.2·§6.
  - `tests/unit/engine/test_cycle263_daily_load_stub_filter.py` A1·A3~A6 — daily 게이트가 시간→슬롯. A5(「주말 63.9h → 월요일 실행 = 주 1회 무결성 재fetch」)는 **의도적으로 뒤집힌다**: 월요일 재fetch 가 없어져도 월요일 20:30 정기 실행의 7일 증분이 같은 창을 다시 덮는다. 금요일 「마커 남기고 부분 실패」는 평일과 같은 위험 등급(cycle360 §7).
  - `test_refactor_b1_data_load_tasks.py` 등 wrapper kw 를 보는 테스트.
- sha 핀: 바뀐 파일의 핀은 **값만** 재핀.

## 4. 돌연변이 (tester, KILL 실측 — 각각 붉어지는 테스트 이름 기록)

- M1 daily·basics 를 시간 게이트(`immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS`)로 되돌림
- M2 full_universe 행 수 하한 제거(force_run_check 미전달)
- M3 휴장일 조회 실패(`calendar_unknown`)를 SKIP 으로 바꿈
- M4 ①′ 달력 판정 복귀(`expected_head` 인자를 받아도 무시)
- M5 6전략이 `expected_head` 를 넘기지 않음(또는 None 고정)
- M6 full_universe 부트스트랩 제거(마커 없음 → RUN)
- M7 leaf 가 주말을 개장으로 취급 / None 을 캐시

## 5. 심층 검증 (tester — 루트 CLAUDE.md 「기능 비활성화」 의무)

월요일 보충 적재(KRX full_universe · basics 08:00 · 일봉)가 꺼지는 「경로 변경」이다. 확인할 소비처:

1. KRX 전용 raw 키(`ACC_TRDVAL`·`MKTCAP`·`TDD_CLSPRC`·`LIST_DD` 등) 적재기 밖 소비처 grep 전수 (메모 실측 0건 재확인).
2. `stock_master.refreshed_at` / `is_stale()` 소비처 전수와 월요일 영향 — 알려진 것: `scanner._scan_pool_eager_refresh_loop`(월요일 첫 패스에 풀 종목 KIS 갱신이 실제로 돈다) · `order_engine` `[stock_master_miss] reason=stale` 관측 로그(월요일 주문마다 INFO) · `scheduler` 부팅 보유 eager 갱신. **읽기만**(8영역 무접촉).
3. 🔴 `stock_master.list_by_filter` 기본 정렬이 `refreshed_at DESC LIMIT`(`stock_master.py:636`) — 6전략 각각 `sort_by`/`limit` 과 실제 후보 수를 대조해 **LIMIT 절단이 일어나는 전략이 있는지**. 있으면 월요일 풀 eager 갱신이 `refreshed_at` 순서를 바꿔 부팅 준비와 +600초 재준비의 유니버스가 달라질 수 있다 — 결론만 보고.
4. `market_ops` 9행(full_universe)이 새 마커를 읽지 않음(`marker_iso=None`) 확인 — 화면 행위 불변, 문서의 「영구 결측 4작업」 서술만 낡는다.
5. ①′ 소비처: 6전략 prepare 외 호출부(`kojiro.py:768` · `llm_buy_gate.py:1011`)는 인자 없이 현행 유지.
6. 청산 경로 무접촉(diff 에 `check_exit_signal`·risk·order 경로 0).

## 6. 문서 (report-writer, 덧칠 금지·정본은 현재형)

- `src/engine/CLAUDE.md` — 정기 task 루프 절(슬롯 게이트·대상 목록·부트스트랩·하한) · funnel 스냅샷 캡처 절의 「월요일 보충 적재를 라이브 후보에 반영하는 경로는 재준비 하나뿐 / 게이트 금지」 서술을 cycle360 §1.2·§6 결론대로 정정(재준비가 반영하던 것은 **더 오래된 KRX 값 = 교체**였고, ① 이후 월요일 재준비는 같은 입력을 읽는다. 재준비 자체는 불변·게이트 없음) · `trading_calendar.py` leaf.
- `src/db/CLAUDE.md` — `get_recent_daily_normalized(..., expected_head=)` · 신선도 게이트 2갈래 · task 마커가 슬롯 게이트에도 쓰임.
- `src/engine/strategies/CLAUDE.md` — 어댑터 호출 계약에 `expected_head`(한 줄, 상세는 db 문서 링크).
- `src/routes/CLAUDE.md` + `src/routes/market_ops.py` docstring — 「마커 영구 결측 4작업」 서술 갱신(full_universe 는 cycle363 부터 마커를 남기지만 이 화면 9행은 진행률만 읽는다).
- `src/engine/boot_manager.py` `emit_daily_head_staleness` docstring 의 「마커 20h 초과로 실행」 문구.
- `docs/HARNESS_CHANGELOG.md` cycle363 행 · `docs/history/src-engine-CLAUDE.history.md`(F-10-2 개정 사유·A5 반전 사유) · 필요 시 `src-db-CLAUDE.history.md`.
- `/sync-docs` 덧칠 패턴 검사 0.

## 7. 배포

`src/` 코드 변경 → **full 모드**(backend 재시작). 09-25(금)~09-27(일) 휴장·주말 = 종일 장외 창. 09-28 07:45 전. 커밋·push 는 메인 세션.

## 8. 배포 전 보강 (독립 검증 반영, 2026-09-25)

배포 전 적대적 독립 검증(4렌즈·26 에이전트)이 confirmed 8건(major 4·minor 4)을 냈다. 사용자
결정(2026-09-25)에 따라 다음을 같은 배포에 포함한다.

- **F-1(8영역 승인)** — `scanner._scan_pool_eager_refresh_loop` 의 `upsert_one` 앞에 cycle176
  basics 경로와 같은 `{**기존 raw, **신규 raw}` 머지를 넣는다. 풀 eager refresh(5분 주기)와
  +600초 재준비가 09-28 아침 같은 시각(T+600)에 겹칠 것으로 추정됐고, 머지 없이 돌면 장전
  0값 키(`acml_tr_pbmn` 등)가 지워져 라이브 후보가 거래대금 임계에서 빠진다. 매수·청산·구독
  로직 무변경 — 8영역 sha 핀 절차(값만 재핀 + 주석에 사유)를 따른다.
- **①′ F-3** — `get_recent_daily_normalized` 에서 `days > 100`(KIS 1회 호출 상한) 이면
  ① 현행 달력 판정(4일 이내)으로 신선하거나 ② 헤드가 `expected_head` 보다 **정확히 1영업일**
  늦으면 KIS 폴백하지 않고 DB 를 쓴다(VCP full 모드 200 EMA 가 100봉 폴백으로 75 EMA 로 깎이던
  결함 — 평상시 요일에도 발생). 사용자 결정 「깊은 읽기는 DB 유지」 = 깊은 읽기의 평일 행위는
  현행과 같다(메인 세션 보강: 처음 구현은 ②만이라 평일 2영업일 결손 64종목이 여전히 100봉으로
  깎였다 → ①을 더함, 테스트 F3g·F3h). 둘 다 아니거나 `days≤100` 요청은 폴백한다.
- **F-4(승인 범위 안)** — `stock_master.count_missing_kis_provenance_key()` 신규 + basics
  wrapper 에 `immediate_force_run_check`/`immediate_force_run_reason="kis_keys_missing"`
  배선. full_universe 만 RUN 하고 basics 는 계속 SKIP 하는 월요일에 KIS 출처 키 결손이 16:10
  까지 방치되던 결함 시정. `task_loop_helper` 에 `force_run_reason`/`immediate_force_run_reason`
  키워드 인자 신설(기본값 `"below_floor"` = 기존 full_universe 회귀 0).
- **F-5(명세 정정, 코드 무변경)** — `system_config.get_task_last_success` 가 pg 예외를
  삼켜 `None` 을 주므로 `_evaluate_slot_gate` 의 `reason=marker_error` 분기는 운영에서
  도달 불가다. 실 함수 경로 테스트 1건으로 실증했고, full_universe 의 `no_marker` SKIP 이
  부트스트랩과 pg 장애를 구분 못 하는 것을 명세 한계로 남긴다.
- **F-2 안정화(승인 범위 안)** — `trading_calendar.is_open_day` 조회에 `asyncio.wait_for`
  (5초) + `None`(모름) 음성 캐시(90초, True/False 영구 메모와 별도 저장소) 추가. never-raise·
  「모르면 실행」 방향은 불변.
- **미채택** — `이 지시서에서 다루지 않은 finding`(휴장일 조회 성공 가정에 대한 지적 등)은
  독립 검증에서 refuted 로 판정됐다(§8 부록·독립 검증 로그 참조).

검증: 관련 테스트 배치(cycle363 전체 + cycle134/163/176/83/193/263 + `tests/unit/db/`·
`tests/unit/ast/` 전체) 415 passed 0 failed. 돌연변이 KILL 5종(F-1 머지 제거·F-3 조건 제거/경계
완화·F-4 배선 제거·F-2 `wait_for`/음성 캐시 제거) 전부 확인. 전체 백엔드 스위트
`python -m pytest -q -p no:cacheprovider` **11,828 passed · 0 failed · 12 skipped ·
342 xfailed · 12 xpassed**(sha 재핀 + `python tools/test_impact/build_index.py` 반영 후).
