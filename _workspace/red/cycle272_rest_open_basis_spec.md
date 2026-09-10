# cycle272 Red 명세 — VB·LTV `main` 목표가 기준가를 KRX REST 로 교체

- 작성 2026-09-10 (목) · tdd-engineer · **Red 단계 = 테스트만. `src/**` 한 글자도 안 고쳤다.**
- 기준 HEAD `1df6d7d` · `wc -l src/engine/scheduler.py` = **3,898**
- 자문 정본 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`
- 근거 입력 = `_workspace/analysis/2026-09-10_cycle272_U1_open_price_path.md` ·
  `..._U2_rest_capacity.md` · `..._U3_guards_and_rollback.md` ·
  `_workspace/analysis/2026-09-10_open_scope_3way_readout.md` ·
  `_workspace/analysis/2026-09-10_cycle265_direction_report.md`
- 사용자 결정 D1 (2026-09-10) = *"체크할 필요가 없이 KRX시가를 쓰는게 원칙 / 기준가를 조회값으로
  교체하고나서, 금요일 실측한 뒤에 구독채널을 분리하자 / 여섯가지 유지 동의"*

> **무접촉 6종 (사용자 D1 §범위)** — 전략 비중 · `position_ratio` · `max_positions` ·
> 랏 캡(K·K_ρ) · `open_entry_hold_secs`(90초) · LTV 청산 규약.
> **이 명세의 어떤 테스트도 그 여섯 값을 바꾸지 않는다.** 90초 보류는 *예산*으로만 쓴다
> (C8 이 "보류가 0 으로 롤백돼도 안전하다" 를 못 박아 의존을 끊는다).

---

## 0. 한 줄

통합 채널 `H0UNCNT0` `fields[7]` 이 실어 오는 어제/프리장 시가로 오늘의 돌파선을 긋는 일을
멈춘다. `board=="main"` 목표가의 기준가는 **KRX REST `stck_oprc`(`J`) 단일 출처**이고,
그 값이 프린트될 때까지 기다렸다가 프린트된 값으로만 선을 긋는다. 못 기다린 종목은 오늘 안 산다.

---

## 1. 구현 계약 (이름 정본) — Green 이 만들어야 하는 것

### 1-a. 신규 leaf `src/engine/open_price_rest.py` — **행위 leaf**

> ⚠️ cycle264 `open_price_observe.py` 는 "행위 변경 0" 이 첫 계약인 **관측 leaf** 였다.
> 이 모듈은 반대다 — **목표가를 실제로 세우는 행위 leaf** 이며 그 사실을 docstring 첫 줄에
> 명시한다. `never-raise` 는 **관측에만** 적용하고, 확보 실패는 침묵하지 않고 계수·기록한다.

```python
MODE_KEY      = "open_price_scope_mode"
MODE_ENFORCE  = "enforce"
MODE_OFF      = "off"
_MAIN_BOARD   = "main"
_TRUSTED_MAIN_SOURCES = ("rest",)          # 채널 분리(P1-7 B) 때 "ws_krx" 가 여기 꽂힌다
_BASIS_STRATEGIES = ("volatility_breakout", "long_tail_volatility")

TIME_MAIN_REST_BASIS_R1        = time(9, 0, 35)
MAIN_REST_BASIS_ROUND_INTERVAL_S = 30.0
MAIN_REST_BASIS_FAST_ROUNDS    = 9
MAIN_REST_BASIS_SLOW_INTERVAL_S = 300.0
TIME_MAIN_REST_BASIS_STOP      = time(15, 20)
TIME_MAIN_REST_BASIS_HANDOFF   = time(9, 5, 0)
_TICKER_SLEEP_S        = 0.05
_ROUND_WALL_CLOCK_MAX_S = 45.0
_READY_POLL_INTERVAL_S = 2.0
_READY_POLL_MAX_S      = 90.0

def resolve_mode(params) -> str
def reject_untrusted_main_basis(params, board, source, *, strategy_id="", ticker="",
                                tick_open=0, dest_logger=None) -> bool
def owns_board(strategy, board, *, now=None) -> bool
def round_schedule() -> list[tuple[int, int, str, time]]   # (round_no, total, kind, KST time)
def select_strategies(registry) -> list[tuple[str, object]]
def reset_main_rest_basis_caps() -> None
def _monotonic() -> float                                   # 벽시계 seam (C17)
async def _fetch_stock_detail(ticker) -> dict               # KIS seam (지연 import)
async def run_main_rest_basis_round(sched, *, round_no, total_rounds, kind) -> dict
async def main_rest_basis_task_loop(sched) -> None
```

`run_main_rest_basis_round` 반환 dict 키 =
`{"total","confirmed","pending","ok","zero","err","calls","elapsed_ms","truncated"}`.

**게이트 본체 — 순서가 계약이다** (C5 가 AST 로 봉인):

```python
def reject_untrusted_main_basis(params, board, source, **obs) -> bool:
    if board != _MAIN_BOARD:                 # ① 순수 비교 — 예외 불가
        return False
    if source in _TRUSTED_MAIN_SOURCES:      # ② REST 경로는 params 를 읽기 **전에** 통과
        return False
    try:
        mode = resolve_mode(params)
    except Exception:
        mode = MODE_ENFORCE                  # 선언된 기본값
    if mode == MODE_OFF:
        return False
    _emit_config_canary(...)                 # never-raise, 별도 try
    return True
```

②가 ③(try/`params` 접근)보다 **앞**이라는 것이 안전 계약이다 — 게이트가 무슨 이유로
터지든 REST 경로는 구조적으로 면역이고, "게이트 고장 = 종일 목표가 0" 이라는 P0-1 계열
사고가 성립하지 않는다.

**모드 해석** = `str(params.get(MODE_KEY, MODE_ENFORCE) or MODE_ENFORCE).strip().lower()`
가 정확히 `"off"` 일 때만 `off`. 그 외(부재·`None`·`""`·공백·오타·타입 이상·예외) 전부
`enforce`. 카나리아가 **원문 값을 병기**한다(`mode=enforce raw="of"`).

**`owns_board(strategy, board, *, now=None)`** =
`board=="main" ∧ resolve_mode(strategy.config.params)=="enforce" ∧ now_kst.time() < 09:05:00`.
**예외는 False(fail-open = 스케줄러가 계속 담당)**.

**라운드 일정** (`round_schedule()`, 순수 함수 — 벽시계 무의존):

| kind | round_no/total | 시각 |
|---|---|---|
| fast | 1/9 … 9/9 | 09:00:35 · 09:01:05 · … · 09:04:35 (30초 간격) |
| slow | 1/75 … 75/75 | 09:09:35 · 09:14:35 · … · 15:19:35 (300초 간격, ≤ 15:20) |

> ⚠️ **명세가 더 정밀해진 지점(자문 §6 C11 의 해석)** — 자문은 `round=%d/%d` 의 분모를
> 정하지 않았고 §5-d 는 `round=1/9 kind=fast` 만 예시했다. 이 명세는 **round_no·total 을
> kind 별로 매긴다**(fast 1..9/9, slow 1..75/75). 그래야 §5-d 판독 예시가 문자 그대로
> 성립하고 D+1 판독의 "R2~R9 pending 단조 감소" 를 분모 혼동 없이 읽는다.

**한 라운드의 처리 순서 (계약)**

1. 대상 전략 = `_BASIS_STRATEGIES` 중 (i) `main ∈ get_tradable_boards(sid, params)`
   (ii) `resolve_mode(params) == "enforce"` 인 것. **`config.enabled` 는 보지 않는다**(D-9).
2. 각 전략 `_targets` 스냅샷에서 `_open_confirmed[t].get("main") is not True` 인 종목을 모으고
   **전략 합집합의 distinct ticker** 로 접는다(5초 캐시에 기대지 않는다 — 스윕이 15~28초라 TTL 밖).
3. 조회 **직전**에 `scanner.ticker_prices.get(t, {}).get("open_price", 0)` 를 읽어 둔다
   (= 옛 코드가 그 순간 썼을 값 = **shadow**). **읽기만 한다.**
4. `_fetch_stock_detail(t)` → `stck_oprc` 파싱.
   - `>0` → 그 종목을 필요로 하는 **모든** 대상 전략에 대해
     `strategy.on_open_price_confirmed(t, v, board="main", source="rest")`
     **와** `open_price_observe.mark_confirmed_via_rest(sid, t, "main")` 를 **둘 다** 호출
     + `[main_rest_basis_confirmed]` 1행(shadow 병기).
   - `0`/빈/비숫자 → 확정 없음, `reason=rest_zero` 계수.
   - 예외 → 확정 없음, `reason=rest_error` 계수. **둘을 분리한다**(O-1 이 하루 만에 갈린다).
5. 종목 간 `await asyncio.sleep(_TICKER_SLEEP_S)`.
6. 라운드 종료 시 **전략별** `[main_rest_basis_round]` 1행(fast 는 항상, slow 는 `pending>0` 일 때만).
7. **빠른 창 마지막 라운드(09:04:35, `kind=="fast" ∧ round_no==total_rounds`) 직후**,
   남은 미확정 종목마다 `[main_rest_basis_unresolved]` 1행(1회/(전략,종목)/일).

**never-raise / lifecycle** — 라운드 본체는 통째로 `try/except Exception`, `CancelledError`
는 re-raise. task 속성명은 **`_main_rest_basis_task`**(`_*_task_handle` 은 cycle79 수집기에
안 잡힌다), `start()`·`run_daily()`·`stop()` **세 취소 목록 전부**에 등재.

### 1-b. 전략 2파일 (VB·LTV 동형, 상호 import 금지)

```python
DEFAULT_PARAMS = {..., "open_price_scope_mode": "enforce", ...}

def on_open_price_confirmed(
    self, ticker: str, open_price: int, board: str = "main", *, source: str = "ws",
) -> None:
    if open_price_rest.reject_untrusted_main_basis(
        self.config.params, board, source,
        strategy_id=self.config.strategy_id, ticker=ticker,
        tick_open=open_price, dest_logger=logger,
    ):
        return
    ...  # 이하 현행 본문 **byte 동일**
```

`check_buy_signal` · `check_exit_signal` · `calc_buy_quantity` 는 **한 글자도 안 바꾼다**
(`source` 기본값 `"ws"` = 불신이므로 인라인 호출부 `volatility_breakout.py:901` /
`long_tail_volatility.py:707` 은 손댈 필요가 없다).

### 1-c. `scheduler.py` — 5곳, 순증 **+1행** (3,898 → 3,899 < 3,900)

| # | 위치 | 변경 | 라인 |
|---|---|---|---|
| S1 | `:42` | 기존 `from src.engine import open_price_observe` 행에 `open_price_rest` 합류 | **+0** |
| S2 | `:723-726` 옆 | `self._main_rest_basis_task = asyncio.create_task(open_price_rest.main_rest_basis_task_loop(self))` (cycle269 1행 스타일) | **+1** |
| S3 | `:1622` | `if MarketBoard(board) not in allowed or open_price_rest.owns_board(strategy, board):` | +0 |
| S4 | `:1679` | `strategy.on_open_price_confirmed(ticker, open_price, board=board, source="rest")` | +0 |
| S5 | `:1013 / :1140 / :1176` | 취소 목록 3행에 `"_main_rest_basis_task",` 추가(같은 행 안) | +0 |

> **권고(선택, 필수 계약 아님)** — `:723-725` 3행을 cycle269 처럼 1행으로 접으면 −2행
> (3,897L)이라 여유 2행이 생긴다. **필수 계약은 `≤ 3,899`**.

---

## 2. 계약 C1~C28 ↔ 테스트 매핑

> 배치 원칙 = **정적 술어는 AST 파일, 상태·비동기 행위는 행위 파일.**
> 자문 §6 은 C23~C28 을 한 파일로 묶었으나, C23·C25 는 `owns_board` 가 만든 **비동기 행위**라
> leaf 행위 파일에 둔다(계약 자체는 한 글자도 안 바꿨다 — §7 이견 ①).

| C | 내용 | 파일 | 테스트 |
|---|---|---|---|
| C1 | enforce·main·source 미지정 → `boards["main"]` 미생성 ∧ `_open_confirmed[t]["main"] is not True` (VB·LTV 각각) | 게이트 | `test_c1_*` |
| C2 | 같은 호출에 `source="rest"` → `boards["main"]` 3키가 현행과 값 동일(`k_value_krx_main` 격자 포함) | 게이트 | `test_c2_*` |
| C3 | `mode="off"` 면 source 미지정도 현행대로 확정 · **두 전략 독립** | 게이트 | `test_c3_*` |
| C4 | `board ∈ {pre_nxt, post_nxt}` 는 mode×source **4조합 전부** byte 동일 | 게이트 | `test_c4_*` |
| C5 | (AST) 두 조기반환이 **모든 `Try`·`params` 접근보다 앞** | AST | `test_g272_5*` |
| C6 | 모드 해석 격자 12종 — `off` 는 대소문자·공백 무시 `off` 뿐, 나머지 전부 enforce, 예외도 enforce | 게이트 | `test_c6_*` |
| C7 | (sha) cycle264 `_STRATEGY_PINS` **6개 전부 불변** — **갱신 금지가 계약** | AST | `test_g272_7*` |
| C8 | enforce+main 목표가 부재 동안 `check_buy_signal` → `Signal.NONE` ∧ `_prev_price[t]["main"]` **미기록** | 게이트 | `test_c8_*` |
| C9 | 게이트 관측이 폭발해도 반환값·상태 변화 동일 | 게이트 | `test_c9_*` |
| C10 | 시그니처 `(self, ticker, open_price, board="main", *, source="ws")`, `source` 키워드 전용, 신뢰 목록 `("rest",)` | 게이트+AST | `test_c10_*` · `test_g272_10*` |
| C11 | 라운드 시각 09:00:35·…·09:04:35(9) → 300초 간격 15:20 까지 | leaf | `test_c11_*` |
| C12 | 대상 = main∈boards ∧ enforce ∧ 미확정 · **`config.enabled` 미사용** | leaf | `test_c12_*` |
| C13 | 공통 종목 한 라운드 fetch **정확히 1회** ∧ 두 전략 모두 확정 | leaf | `test_c13_*` |
| C14 | 확정 시 setter(`source="rest"`) **와** `mark_confirmed_via_rest` 둘 다 | leaf | `test_c14_*` |
| C15 | `"0"`/`""`/`"abc"` → `rest_zero`, 예외 → `rest_error` **분리 계수**, 둘 다 미확정 | leaf | `test_c15_*` |
| C16 | 종목 간 `sleep(0.05)` 실삽입 ∧ 어떤 1초 반열린 구간에서도 REST ≤ 20건 | leaf | `test_c16_*` |
| C17 | 벽시계 45초 초과 시 라운드 절단 + `truncated=1`, 다음 라운드는 정상 발화 | leaf | `test_c17_*` |
| C18 | 라운드 본체 예외에도 task 생존 · `CancelledError` re-raise | leaf | `test_c18_*` |
| C19 | `_targets` 비면 REST 0콜 · 준비 폴링 90초 초과 시 `skipped reason=no_target` 1행 | leaf | `test_c19_*` |
| C20 | `scanner.ticker_prices` **읽기 전용** — 전후 스냅샷 동일 | leaf | `test_c20_*` |
| C21 | 마지막 fast 라운드 직후 미확정마다 `[main_rest_basis_unresolved]` 1회/(전략,종목)/일 | leaf | `test_c21_*` |
| C22 | task 속성 `_main_rest_basis_task` ∧ 세 취소 목록 전부 등재 | leaf | `test_c22_*` |
| C23 | `owns_board` True 동안 confirm 은 그 전략을 빼고, 둘 다 빠지면 WS 폴링 0초·REST 0콜 즉시 반환 | leaf | `test_c23_*` |
| C24 | (AST) `start()` 에서 `_drain_pending_next_day_clear` 가 confirm(board="main") **직후** | AST | `test_g272_24*` |
| C25 | 09:05:00 이후 `owns_board` False → 2차 REST 폴백이 백스톱 확정(1차 WS 는 게이트가 전부 거부) · 예외는 False | leaf | `test_c25_*` |
| C26 | (AST) `scheduler.py` REST 폴백 호출만 `source="rest"` 명시, 나머지 3곳은 미명시 | AST | `test_g272_26*` |
| C27 | `scheduler.py ≤ 3,899` ∧ cycle257 리터럴 대조 가드 통과 | AST | `test_g272_27*` |
| C28 | 키 ∉ `PARAM_RANGES`/`INT_PARAMS`(런타임+소스 리터럴) · glob 전수 {VB,LTV} 정확히 · 값 `"enforce"` · 8영역 diff 0 · 타 전략 5파일 diff 0 · 문서 2곳 기재 | AST | `test_g272_28*` |

---

## 3. 경계 조건 (전부 테스트로 고정)

| 축 | 입력 | 기대 |
|---|---|---|
| REST 값 | `stck_oprc="0"` · `""` · `"abc"` · 키 부재 · `None` | 확정 없음, `reason=rest_zero`, 계수만 |
| REST 실패 | `asyncio.TimeoutError` · `KisApiError` · 임의 `Exception` | 확정 없음, `reason=rest_error` |
| REST 실패 | `asyncio.CancelledError` | **흡수 금지** — 상위로 전파(task 취소가 라운드에 갇히면 안 된다) |
| 재시도 상한 | fast 9라운드(09:04:35)까지 · 이후 slow 는 15:20 까지 **포기하지 않는다** | 09:04:35 직후 `unresolved` 계수, slow 는 계속 시도 |
| 재시도 하한 | 라운드 간격 30초 ≥ `fetch_stock_detail` 캐시 TTL 5초 | 같은 캐시값 재독 방지 |
| 킬스위치 | `"off"`/`"OFF"`/`" off "`/`"Off"` | off (대소문자·공백 무시) |
| 킬스위치 | 부재 · `None` · `""` · `"  "` · `"ENFORCE"` · `"true"` · `0` · `[]` · `{"a":1}` · `.get` 예외 | **enforce** |
| 보드 | `pre_nxt` / `post_nxt` | mode×source 4조합 전부 현행 byte 동일 (LTV 08:00 프리장 확정·목표가·`_BOARD_K_KEY` 포함) |
| 90초 보류 | `open_entry_hold_secs = 0` (롤백된 상태) | C8 이 "목표가 없으면 `Signal.NONE`" 을 독립으로 보장 — **보류에 의존하지 않는다** |
| `owns_board` | 09:04:59.999 / 09:05:00.000 | True / False (경계 배타) |
| `owns_board` | `strategy.config.params` 접근이 예외 | **False (fail-open)** |
| 관측 | 4마커 emit 각각이 예외 | 확정 결과·라운드 진행·틱 처리 **동일** |
| 부하 | 140종목 스윕 | 어떤 1초 반열린 구간도 REST ≤ 20건 ∧ 연속 호출 최소 간격 ≥ 50ms |

> ⚠️ **부하 단언은 ms 격자로 잰다.** 설계가 정확히 20건/초에 닿아 있어서(0.05s × 20 = 1s)
> 가짜 시계 누산의 부동소수 드리프트만으로 21 이 나온다(실측: `0.05` 를 20번 더하면
> `1.0000000000000002`). `round(s*1000)` 격자 + 반열린 1,000ms 창으로 재고, **연속 호출
> 최소 간격 ≥ 50ms** 를 함께 단언해 조건부 sleep(버스트)까지 막는다.

---

## 4. 관측 마커 서식 (4종 전부 신규 — cycle264 이름 재사용 금지)

```
[main_rest_basis_config]     emitter=leaf|gate strategy=%s mode=enforce|off raw=%s
                             source=default|override
                             # 1회/(전략,모드,emitter)/일 — **값-민감 cap** `key=f"cfg|{mode}"`
                             # (장중 PUT 롤백 확인 채널 — 단일 키면 그날 첫 행이 cap 을
                             #  소진해 바뀐 값을 볼 마커가 0행이 된다, cycle245 R1 사각)

[main_rest_basis_round]      round=%d/%d kind=fast|slow mode=%s strategy=%s board=main
                             total=%d confirmed=%d pending=%d ok=%d zero=%d err=%d
                             calls=%d elapsed_ms=%d truncated=0|1
                             # fast 는 항상, slow 는 pending>0 일 때만.
                             # `[breakout_open_confirm] truth_*` 의 **대체 커버리지 채널**

[main_rest_basis_confirmed]  strategy=%s ticker=%s board=main round=%d rest_open=%d
                             ws_open=%d ws_src=cache|absent delta_bp=%+.1f
                             target_rest=%d target_ws=%d
                             # 1회/(전략,종목)/일 — **오염 규모의 새 정본(shadow)**.
                             # REST 조회 **직전** `ticker_prices` 를 읽어 '옛 코드가 그 순간
                             # 썼을 값' 을 병기 ⇒ `delta_bp=0` 산술 항등 문제를 우회한다

[main_rest_basis_unresolved] strategy=%s ticker=%s board=main
                             reason=rest_zero|rest_error|no_tick rounds=%d
                             # 1회/(전략,종목)/일 — **커버리지 손실 정본**.
                             # 0 이 아니면 '고치려다 매수를 잃고 있다' 는 뜻이다
```

**공통 계약** — 모든 emit 은 `try/except` + `observer_trace.trace_observer_failure`
(never-raise), cap 은 **마커마다 별개 `KstDailyEmitCap` 인스턴스**(`now=` 키워드 전용),
`logger` 만 사용(`write_log`/DB/`await` 금지), **행위는 관측 밖**.

### 4-a. 기존 마커의 의미 반전 (판독문에 반드시 남길 것)

| 마커 | 시정 후 의미 |
|---|---|
| `[open_source_compare] used_src` | **전부 `rest` 여야 정상.** `ws` 행이 한 줄이라도 있으면 게이트를 뚫었다는 **결함 서명**(영구 회귀 탐지기로 승격) |
| `[open_source_compare] delta_bp` | 전부 0 — **산술 항등이므로 오염 지표로 읽지 마라.** ⚠️ **배포 전후 grep 합산 금지** |
| `[breakout_open_confirm] board=main` | `owns_board` 로 대상이 비어 **09:00:1x 에 사라진다(의도된 침묵)**. 09:35 이후 pending 이 있을 때만 재등장. **배포 전후 행 수 합산 금지.** 대체 채널 = `[main_rest_basis_round]` 의 `confirmed/total` |
| `[open_entry_hold_blocked]`(cycle262) | 감소는 cycle272 의 **부수 효과**(목표가가 없으면 발사점까지 못 간다) — "보류가 더 세졌다" 로 읽지 말 것 |

---

## 5. 의도적으로 깨질 기존 테스트 — 처리 방침

> **원칙 — 삭제하지 않는다.** `off` 경로는 살아 있는 롤백 경로이므로 그 계약을 검증하는
> 테스트도 살아 있어야 한다. 기존 테스트는 **"레거시(off) 경로 회귀 가드" 로 재분류**하고,
> enforce 판은 cycle272 신규 파일에 추가한다.

| # | 파일 / 테스트 | 왜 깨지나 | 처리 |
|---|---|---|---|
| 1 | `tests/integration/test_confirm_open_prices.py` — `..._when_open_price_in_cache_then_target_set` · `..._falls_back_to_kis_api_when_open_price_missing` · `..._is_idempotent_when_all_already_confirmed` · `..._proceeds_when_partially_confirmed` | WS 캐시가 `main` 기준가를 만든다는 계약 | 픽스처에 `open_price_scope_mode="off"` 명시 → **현행 계약 그대로 유지** |
| 2 | `tests/unit/engine/strategies/test_volatility_breakout.py` — `test_on_open_when_main_board_then_target_uses_krx_main_k` · `test_buy_first_tick_per_board_records_only` · `test_buy_when_breakout_moment_then_buy` · `test_buy_when_above_target_but_no_breakout_moment_then_none` · `test_buy_signal_per_board_is_independent` | 인라인 자동확정(`check_buy_signal` 안 setter 호출) 의존 | `vb` 픽스처(또는 각 테스트)에 `"off"` 명시. **행위를 검증하는 테스트는 off 로** |
| 3 | 같은 파일 `test_on_open_records_top_level_compat_for_first_confirmed_board` | setter 직접 호출로 상태만 세팅 | 호출에 **`source="rest"`** 추가 |
| 4 | `tests/unit/engine/strategies/test_long_tail_volatility.py` — `test_buy_when_prdy_rate_below_min_then_none` · `test_buy_when_breakout_and_prdy_rate_above_min_then_buy` | 인라인 자동확정 의존 | `"off"` 픽스처 |
| 5 | `test_cycle262_open_entry_hold.py::_armed` · `test_cycle201_vb_reentry_cooldown.py` · `test_cycle213_ltv_reentry_cooldown.py` · `test_cycle229_vb_buy_cutoff.py` · `test_cycleG_vb_failed_breakout_exit.py` | setter 직접 호출로 상태만 세팅 | 셋업 호출에 **`source="rest"` 한 인자 추가**. 의미상으로도 정직하다("이 테스트는 REST 로 확정된 기준가를 심는다") |
| 6 | `tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py` | `owns_board` 때문에 09:00~09:05 구간 main 대상이 0 | freezegun **09:35 고정** 또는 `"off"` 픽스처로 재조정 (두 테스트는 `pre_nxt`/`post_nxt` 스코프라 실제로는 무영향일 가능성이 높다 — 실행해 확인) |
| 7 | `tests/unit/ast/test_cycle264_scope_and_pins.py::test_c7_no_killswitch_param_introduced` | 금지 목록에 `open_price_scope_mode` 가 있다 | 금지 목록에서 **그 이름 하나만 제거**. `open_scope_observe_enabled`·`open_source_compare_enabled` 금지는 **유지**. 테스트 자체는 삭제 금지 |
| 8 | 같은 파일 `_STRATEGY_PINS` 6개 + docstring 예고 문장 | docstring 이 "cycle265 가 이 핀을 갱신한다" 고 예고 | **핀은 갱신하지 않는다.** 6/6 불변이 곧 "여섯 가지 무접촉" 의 기계적 증거다. **docstring 의 예고 문장만 정정** |
| 9 | `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::test_g223_12`(`_CYCLE228_STRATEGY_CONTENT_SHA`, 현재 빈 dict) | VB·LTV 를 실제로 바꾼다 | **커밋 직전 한시 등록 → 커밋 직후 삭제.** 8영역 무접촉이므로 자매 가드 4곳은 손대지 않는다 |
| 10 | `tests/integration/test_post_nxt_open_price_confirm.py` · `test_cycle164_open_confirm_retry_chain.py` · `test_cycle264_open_source_compare.py` | 생존 예상 | **실행해 확인만** |

**xfail 은 쓰지 않는다** — 깨지는 테스트는 전부 "계약이 바뀐 곳"이 아니라 "픽스처가
새 기본값을 명시해야 하는 곳"이다. xfail 로 덮으면 롤백 경로(off)의 회귀 가드가 사라진다.

---

## 6. 8영역 접촉 · 핀 절차

**이 사이클의 8영역 접촉 = 0.**
`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` ·
`src/realtime/**` · `src/auth/**` **전부 diff 0**. leaf 는 `scanner.ticker_prices` 를 **읽기만** 한다.

⇒ **자매 sha 핀 4곳은 손대지 않는다**:
`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` ·
`test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA` ·
`test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA` ·
`tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA`.

**전략 파일 한시 핀 절차 (커밋 직전 · 위 표 #9)**
1. `git status` 재확인 — 다른 에이전트가 같은 창에 전략/8영역을 건드렸으면 핀이 뒤엉킨다.
2. `test_cycle223_ast_donchian_exit_fix.py::_CYCLE228_STRATEGY_CONTENT_SHA` 에
   `volatility_breakout.py` · `long_tail_volatility.py` 2항목을 **파일 내용 sha256** 으로 등록.
3. 커밋.
4. **즉시 삭제**(빈 dict 복원) + 후속 커밋. 남겨 두면 다음 사이클이 스테일 핀에 걸린다.

---

## 7. 명세 이견 — **고치지 않고 기록만 한다**

1. **테스트 파일 이름** — 지시문 항목 2 는 `tests/unit/engine/test_cycle272_rest_open_basis.py`
   + `tests/unit/ast/test_cycle272_ast_guards.py` **2파일**을 지정했고, 같은 지시문의
   「파일 대상」 목록과 자문 §6 은 `tests/unit/engine/strategies/test_cycle272_main_rest_basis.py`
   + `tests/unit/engine/test_cycle272_open_price_rest_leaf.py` +
   `tests/unit/ast/test_cycle272_ast_main_rest_basis.py` **3파일**을 지정한다.
   **더 구체적이고 자문 §6 정본과 일치하는 3파일 안을 채택**했다. 이름을 되돌리려면
   `git mv` 3회로 끝난다(내용 무변경).
2. **C23·C25 배치** — 자문 §6 은 C23~C28 을 AST 파일로 묶었으나 C23·C25 는 비동기 행위
   테스트라 leaf 행위 파일에 뒀다. 계약 문언은 한 글자도 안 바꿨다.
3. **`round=%d/%d` 분모** — 자문이 정하지 않은 축. kind 별 분모(fast 9 / slow 75)로 확정했다(§1-a).
4. **O-A (자문 §9)** — VB·LTV 가 09-10 17:07 부로 `enabled=False weight=0` 이다.
   D-9(비활성 전략도 스윕) 덕분에 REST 확보·오염 shadow·게이트·부하는 금요일에 검증되지만
   **진입 건수 영향은 검증되지 않는다.** 비중은 무접촉 6종이자 사용자 결정 항목이므로
   이 명세는 제안하지 않는다 — "금요일 실측" 이 무엇을 가리키는지 확정이 필요하다.
5. **O-I (자문 §9)** — cycle264 docstring·U3 §0-C 는 "cycle265/272 가 `check_buy_signal`
   sha 핀 2개를 갱신한다" 고 예고했다. 이 설계는 핀 6개를 **전부 불변**으로 남긴다 —
   예고 문장 쪽을 정정해야 한다(§5 표 #8).
6. **F-3 / F-3b (자문 §9 O-G)** — momentum·LTV 익일 갭률과 kojiro 갭 가드는 여전히 오염된
   `[7]` 을 쓴다. **이번 범위 밖이며 열린 채로 남는다.**
7. **롤백 비대칭** — `open_entry_hold_secs` 는 매 틱 params 를 다시 읽어 PUT 이 즉시 먹혔지만
   목표가 기준가는 `_targets[t]["boards"]["main"]` 에 **한 번 박히는 값**이라
   **이미 확정된 그날 목표가는 되돌아오지 않는다**(그 값이 올바른 KRX 시가이므로 문제는 아니다).
   롤백은 미확정 잔여분·다음 라운드에만 전진 방향으로 듣고, **완전 복원 단위는 다음 영업일**이다.
   롤백 확인 채널 = `[main_rest_basis_config]` 값-민감 cap(슬로우 라운드 5분 주기 ⇒ PUT 후
   5분 안에 `mode=off` 행).
8. **DB 선반영 금지** — 배포 **전** `PUT /api/strategies/{id}/params` 는 미지 키를 조용히 버리고
   `params` JSONB 를 통째로 덮어 먼저 넣은 SQL 값까지 지운다(cycle245 실측).

---

## 8. 회귀 게이트 (Green 후 tester 가 돌릴 목록)

```bash
# 신규 3파일
python -m pytest -q tests/unit/engine/strategies/test_cycle272_main_rest_basis.py \
                    tests/unit/engine/test_cycle272_open_price_rest_leaf.py \
                    tests/unit/ast/test_cycle272_ast_main_rest_basis.py

# 직접 영향 (§5 표)
python -m pytest -q tests/integration/test_confirm_open_prices.py \
                    tests/integration/test_post_nxt_open_price_confirm.py \
                    tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py \
                    tests/unit/engine/test_cycle164_open_confirm_retry_chain.py \
                    tests/unit/engine/test_cycle264_open_source_compare.py \
                    tests/unit/engine/strategies/ \
                    tests/unit/ast/

# 전체
python -m pytest -q                      # 기준 7,548 PASS (cycle270 시점)
python tools/test_impact/build_index.py  # 인덱스 재생성
```

**뮤테이션 (전부 KILL 되어야 한다)** — 신뢰 목록 `("rest",)` → `("rest","ws")` ·
게이트 조기반환 순서 뒤집기 · `owns_board` 시각 경계(09:04:59.9 / 09:05:00.0) ·
`mode == MODE_OFF` → `!=` · 종목 간 `sleep` 삭제 · `mark_confirmed_via_rest` 호출 삭제 ·
`rest_zero`/`rest_error` 합치기 · `config.enabled` 대상 판정 편입 · `truncated` 항상 0.

**caplog 단언 규약** — 이 사이클의 모든 로그 단언은 **로거명 + `levelno >= INFO` +
마커 prefix 3중 한정**이다(CI 루트 로거 DEBUG 차이 — `feedback_caplog_debug_level`).

**코드 핀 규약** — `ast.dump` sha 금지(3.12 CI ↔ 3.13 로컬 출력 상이).
`ast.get_source_segment(src, fn)` 의 sha256 만 쓴다.

---

*Red 작성 시점 `src/**` 변경 0 · 커밋 0 · 운영 접근 없음.*

---

## 9. Red 실행 수치 (2026-09-10, HEAD `1df6d7d`, `src/**` 변경 0)

```
tests/unit/engine/strategies/test_cycle272_main_rest_basis.py   78 failed, 20 passed
tests/unit/engine/test_cycle272_open_price_rest_leaf.py         50 failed,  0 passed
tests/unit/ast/test_cycle272_ast_main_rest_basis.py             14 failed, 18 passed
────────────────────────────────────────────────────────────────────────────────
합계                                                           142 failed, 38 passed
```

**RED 142 ↔ 계약 28항 대응** — C1·C2·C4(rest 조합)·C5·C6·C7c·C8(2/3)·C9·C10(2/3)·
C11~C23·C25·C26a·C28(c/c2/f/h/i) 이 붉다. `src/engine/open_price_rest.py` 부재가
직접 원인인 것이 대부분이고, 나머지는 `source` 키워드 미존재(TypeError) ·
`DEFAULT_PARAMS` 키 부재 · 문서 미기재 · cycle264 금지 목록/예고 문장이다.

**이미 GREEN 인 38 개는 "지금도 참이어야 하고 Green 이후에도 참이어야 하는" 계약**이다:

| 성격 | 테스트 | 지금 초록인 이유 |
|---|---|---|
| 롤백 경로(off) 회귀 가드 | `test_c3_1_mode_off_allows_ws_source` | `off` 는 정의상 현행 행위 |
| 비-main 무접촉 | `test_c4_1_*[*-None-*]` (12) · `test_c4_2_*` | 게이트가 `main` 스코프 |
| 조용한 return | `test_c1_3_*` | 현행 setter 도 `None` 반환 |
| 키워드 전용 | `test_c10_1_*` | 현행 시그니처가 3인자라 4번째 위치 인자는 `TypeError` |
| 무접촉 6종 sha 핀 | `test_g272_7a_*` (6) · `test_g272_7b_*` | **끝까지 초록이어야 한다**(갱신 금지) |
| 라인 예산 | `test_g272_27a/27b` | 3,898 ≤ 3,899 (Green 후 3,899 여야 한다) |
| 호출 순서 | `test_g272_24a_*` | 순서는 안 바꾼다 |
| 인라인 무접촉 | `test_g272_26b_*` (2) | 인라인은 `source` 미명시가 계약 |
| 상호 import 금지 | `test_g272_10c_*` | 현행도 서로 import 안 한다 |
| 자동 튜닝 차단 | `test_g272_28a/28b` | 키가 아직 없다(Green 후에도 없어야 한다) |
| 마커 누수 | `test_g272_28g_*` | 아직 마커가 없다(Green 후 3파일 안에만) |
| 접촉 범위(**사이클 한정**) | `test_g272_28d/28e` | 워킹트리 clean — **커밋 직후 삭제** |

### 9-a. 이번 변경으로 깨져야 하는 기존 테스트 — **현재 전부 GREEN 임을 확인했다**

```
tests/integration/test_confirm_open_prices.py
tests/integration/test_post_nxt_open_price_confirm.py
tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py
tests/unit/engine/test_cycle164_open_confirm_retry_chain.py
tests/unit/engine/test_cycle264_open_source_compare.py
tests/unit/engine/strategies/test_volatility_breakout.py
tests/unit/engine/strategies/test_long_tail_volatility.py
tests/unit/engine/strategies/test_cycle262_open_entry_hold.py
tests/unit/engine/strategies/test_cycle201_vb_reentry_cooldown.py
tests/unit/engine/strategies/test_cycle213_ltv_reentry_cooldown.py
tests/unit/engine/strategies/test_cycle229_vb_buy_cutoff.py
tests/unit/engine/strategies/test_cycleG_vb_failed_breakout_exit.py
tests/unit/ast/test_cycle264_scope_and_pins.py
tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py
                                              → 270 passed (2026-09-10)
```

Green 단계에서 §5 표대로 **픽스처만** 고친다(계약은 그대로). 이 270 중 몇 개가 붉어지는지는
Green 이 실제로 배선한 뒤에만 정확히 말할 수 있다 — §5 는 **예상 목록**이지 확정 목록이 아니다.

### 9-b. 전체 스위트 기준선

```
python -m pytest -q  (cycle272 신규 3파일 제외)
  → 7,564 passed, 11 skipped, 328 xfailed, 13 xpassed  (254s)
```

Green 후 기대치 = **7,564 + 180(신규) = 7,744 PASS**(§5 픽스처 수정으로 기존 개수는 불변).
