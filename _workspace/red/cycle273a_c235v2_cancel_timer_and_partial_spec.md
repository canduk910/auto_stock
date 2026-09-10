# cycle273a Red 명세 — D2(가) C235-V2: 잔여취소 타이머 해제 + `update_trade_status` PARTIAL 포괄

- 작성 2026-09-10 · tdd-engineer · **기준 HEAD `1df6d7d`**(`order_engine.py`·`trade_history.py` 는 `a10191b` 이후 무접촉)
- 사용자 결정 원문(09-10 목 19:5x) = "**2. D2 주문/청산 안전 3건 — 가, 다, 나 순서로 진행하자.**" ⇒ 이 문서가 **(가)**
- 정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` ·
  `_workspace/analysis/2026-09-10_004990_partial_fill_cancel_race.md` ·
  보고서 `_workspace/reports/2026-09-10_thursday_autonomous_work.md` §9 · 워크리스트 1292행(C235-V2)
- **이 문서는 코드를 한 글자도 바꾸지 않았다.** 산출 = 이 md + 보류 Red 4파일(§7)

---

## 0. 한 줄

전량 체결이 **자기 주문의 30초 잔여취소 타이머를 해제**하게 하고(가-a), 전량 체결의
1차 `update_trade_status` 만 **PENDING∪PARTIAL** 을 보게 한다(가-b). 둘 다 **매매 행위
불변**이며, 오늘 KIS 거부(APBK0927)와 3단 DB 보정 우회로 흡수되던 것을 **없앤다**.

| 축 | 오늘 | 이 사이클 뒤 |
|---|---|---|
| 전량 체결 후 30초 | `cancel_order(잔량0)` → KIS APBK0927 거부 → ERROR 3행 | 호출 자체가 없다 |
| PARTIAL 행 위 전량 체결 | 1차 UPDATE `affected=0` → 보정 INSERT → UniqueViolation → 강제 UPDATE | 1차 UPDATE `affected=1` 로 끝 |
| 매도 잔여 재주문(`:1545-1552`) | "KIS 가 거부해 주는 것" 이 유일한 중복매도 방어선 | 우연 의존 소멸 |

---

## 1. 사실관계 (HEAD 실측)

### 1-a. 타이머의 전 생애 — 전량 체결 분기에 참조가 **0건**

`_pending_cancel_tasks` 를 읽거나 쓰는 곳은 소스 전체 **9곳**뿐이다.

| 줄 | 무엇 |
|---|---|
| `order_engine.py:79` | 선언 `dict[str, asyncio.Task]` — **키가 `ticker`**(order_no 아님) |
| `:1508-1509` / `:1526` | `_schedule_cancel` 진입 시 같은 ticker 기존 task `.cancel()` / 등록 |
| `:1523-1524` | `_cancel_after_wait` `finally` — 본인일 때만 pop |
| `:1532-1533` / `:1563` | `_schedule_cancel_and_reorder` 동형 |
| `:1560-1561` | `_cancel_and_reorder` `finally` |
| `scheduler.py:1301` | 상태 조회(읽기 전용) |
| `scheduler.py:3737-3739` | `_reset_daily_state` — 전량 `.cancel()` + `.clear()` (**20:10**) |

⇒ 매수 전량 체결 분기(`:1262-1360`)·매도 전량 체결 분기(`:1433-1498`)에 **한 건도 없다.**
타이머를 멈출 수 있는 것은 (a) 같은 ticker 의 **다음** 부분체결 (b) 자기 만료 (c) 20:10 정산뿐.

### 1-b. 004990(09-10 09:05) 재현 경로

```
09:05:01  3/5 → _handle_buy_fill else 분기(:1361) → update_trade_status(BUY, PARTIAL)
                → _schedule_cancel(...) → _pending_cancel_tasks["004990"] = task
09:05:01  5/5 → if 분기(:1262) → update_trade_status(BUY, COMPLETED)  ← WHERE status='PENDING' → affected=0
                → :1291 _completed_orders.add → :1294 보정 insert_trade → UniqueViolation
                → :1314 [buy_fill_correction_unique_violation] → :1320 강제 UPDATE(자기치유)
                ── _pending_cancel_tasks 무접촉 ──
09:05:32  만료 → cancel_order(0000305100, 0, cancel_all=True) → KIS APBK0927(rt_cd=7)
                → :1519-1520 logger.exception("부분 체결 잔여 취소 실패: ...")
```

`system_logs` 기준 1회 발화 = **ERROR 3행**. 발화 하한 2회(08-28 `257720` · 09-10 `004990`).

### 1-c. 오늘 매매를 망치지 않은 이유 — 그리고 매도 쪽의 이빨

`cancel_order(order_no, 0, cancel_all=True)` 는 그 주문 한 건만 대상으로 하고 잔량이
물리적으로 0 이라 KIS 가 거부한다. **그러나 `_schedule_cancel_and_reorder` 는 취소 성공 뒤
`remaining` 주를 재주문한다**(`:1545-1552`). `remaining` 은 부분체결 시점에 고정된 상수라
그 뒤 전량 체결되면 낡은 값이다. 지금은 `cancel_order` 가 던져 그 줄에 닿지 못할 뿐 —
**"KIS 가 거부해 주는 것" 이 유일한 중복매도 방어선**이다. (가) 는 이 우연 의존을 없앤다.

### 1-d. 🔴 `pop(ticker)` 단독으로 고치면 안 되는 이유

키가 **ticker** 이고 매수·매도가 **같은 dict** 를 공유한다. ticker 만 보고 지우면:

```
T 매수 부분체결 → _pending_cancel_tasks["T"] = 매수취소타이머
잠시 뒤 T 매도 전량체결 → (잘못된 수정이) 그 타이머를 지움
⇒ 매수 잔량 취소가 영구 실종 — 미체결 잔량이 장 마감까지 남고 예수금·pending 회계가 어긋난다
```

⇒ **해제는 "그 타이머가 이 order_no 의 것일 때만".**

### 1-e. `update_trade_status` 호출자 전수 (6곳)

| # | 위치 | status | PARTIAL 행을 만나면 | 이번 처리 |
|---|---|---|---|---|
| C1 | `:1277-1280` | **COMPLETED**(BUY) | affected=0 → 3단 우회 | ✅ `match_partial=True` |
| C2 | `:1364-1367` | PARTIAL(BUY) | affected=0(무해) | ❌ 유지 |
| C3 | `:1449-1452` | **COMPLETED**(SELL) | C1 동일 | ✅ `match_partial=True` |
| C4 | `:1501` | PARTIAL(SELL) | C2 동일 | ❌ 유지 |
| C5 | `:1515` `_cancel_after_wait` | **CANCELLED**(BUY) | affected=0 | 🔴 **절대 금지** |
| C6 | `:1541` `_cancel_and_reorder` | **CANCELLED**(SELL) | affected=0 | 🔴 **절대 금지** |

---

## 2. 🔴 무행위 경계 — 전역 확대는 무행위가 아니다

`match_partial` 를 기본 True 로 하거나 SQL 리터럴을 통째로 넓히면 C5/C6 이 함께 넓어진다.

```
부분체결(3/5) → 행 = PARTIAL(quantity=5, price=체결가)
30초 뒤 잔여취소 성공 → C5 가 그 행을 CANCELLED 로 뒤집는다
```

| 영향 | 근거 |
|---|---|
| **정산에서 사라진다** | `get_today_trades_for_settlement`(`trade_history.py:330-348`)는 `COMPLETED∪PARTIAL` |
| **sync 판정에서 사라진다** | `get_today_buy_trades_for_sync`(`:456-481`)/`..._sell_...`(`:484-501`)는 CANCELLED 제외 ⇒ `_sync_orders_to_db` 가 "DB 에 없는 주문" 으로 보고 재-INSERT → migration 029 부분 UNIQUE 위반(042700 핑퐁 계열) |
| **부분 체결 사실 소실** | 3주를 실제로 샀는데 기록은 "취소" |

⇒ **C235-V2-b 는 반드시 call-site opt-in.** 이 문장이 이 명세에서 가장 중요한 한 줄이다.

---

## 3. 계약 (Red)

### A축 — 타이머 해제

| # | 계약 | HEAD |
|---|---|---|
| A1 | 3/5 부분체결 → **같은 order_no** 5/5 전량체결 → `_pending_cancel_tasks` 비어 있고 `cancel_order` 호출 0 | RED |
| A1b | 매도 축 동일 + `place_order`(잔여 재주문) 호출 0 | RED |
| A2 | 주문 A 부분체결 → **다른** 주문 B 전량체결 → A 타이머 **생존** | GREEN(계약) |
| A3 | 매수 타이머 존재 상태에서 같은 ticker **매도** 전량체결 → 매수 타이머 **생존** | GREEN(계약) |
| A4 | 해제된 task 가 **즉시 종료**되고 `CancelledError` 를 밖으로 흘리지 않는다 | RED |

A4 가 A1 과 별개인 이유 — `_pending_cancel_tasks` 를 비우기만 하고 `task.cancel()` 을 빼면
A1 은 초록인데 30초 뒤 `cancel_order` 가 그대로 나간다. A4 는 `PARTIAL_FILL_WAIT` 를 **줄이지
않고**(기본 30초) task 의 종료 자체를 잰다.

### B축 — PARTIAL 포괄

| # | 계약 | HEAD |
|---|---|---|
| B1 | 행이 PARTIAL 인 상태의 매수 전량체결 → 보정 INSERT 0회 · 강제 UPDATE 0회 · `[buy_fill_correction_unique_violation]` 미발화 · `_completed_orders` 비어 있음 · 행은 COMPLETED(체결단가) | RED |
| B1b | 매도 축 동일 | RED |
| B1c | 행 자체가 없는 **진짜** 선행 race 는 보정 INSERT 경로 **보존** + `_completed_orders` 에 등록 | GREEN(회귀) |
| B2 | `match_partial` 미전달 시 SQL 이 **byte 동일**(단일 `status = $n`) | GREEN(계약) |
| B2b | `match_partial=True` 시 `status = ANY($n::text[])` + `['PENDING','PARTIAL']`, COMPLETED/CANCELLED 불포함 | RED |
| B2c | `match_partial` 은 **keyword-only**, 기본 False | RED |

### AST축

| # | 계약 | HEAD |
|---|---|---|
| AST1 | `match_partial=True` 리터럴이 소스 전체에 **정확히 2회**, 둘 다 `TradeStatus.COMPLETED` 호출, 둘 다 `order_engine.py` | RED |
| AST2 | 🔴 `TradeStatus.CANCELLED` 호출에 `match_partial` 키워드 **0건**(기준선 = CANCELLED 호출 ≥2곳) | GREEN(영구) |
| AST3 | `_handle_buy_fill`·`_handle_sell_fill` 의 `if total_filled >= ordered_qty:` 안에 `_pending_cancel_tasks` 참조 **존재**(되살림 차단) | RED |
| AST4 | 그 분기 안에 `order_no` 비교가 **함께** 있다(§1-d) | RED |

---

## 4. 최소 diff 계획

### 4.1 `src/db/trade_history.py` (8영역 **아님**)

| # | 위치 | 변경 |
|---|---|---|
| T1 | `:88-95` 시그니처 | `*, match_partial: bool = False` 추가 (cycle273b 의 `order_no` 와 **같은 커밋**이면 함께) |
| T2 | `:96` docstring | "최신 PENDING" → 실제 SQL 서술로 정정("최신" 은 SQL 에 없다) + 근거 주석 |
| T3 | `:107-117` | `match_partial` → `status = ANY($n::text[])`, 기본은 **현행 문자열 그대로** |

### 4.2 `src/engine/order_engine.py` (🔴 **8영역 — D2 승인됨**)

| # | 위치 | 변경 |
|---|---|---|
| O1 | `:79` 근처 | `self._pending_cancel_order_no: dict[str, str] = {}`  # ticker → 그 타이머가 지키는 order_no |
| O2 | `:1526` 직전 / `:1563` 직전 | 등록 시 동반 기록 |
| O3 | `:1521-1524` / `:1558-1561` `finally` | 본인 pop 시 동반 pop |
| O4 | `:1277-1280`(C1) / `:1449-1452`(C3) | `match_partial=True` |
| O5 | `:1360` 뒤(매수) / `:1495` 뒤(매도) | order_no 일치 게이트 뒤 타이머 해제 (아래) |

```python
if self._pending_cancel_order_no.get(ticker) == order_no:
    task = self._pending_cancel_tasks.pop(ticker, None)
    self._pending_cancel_order_no.pop(ticker, None)
    if task is not None and not task.done():
        task.cancel()   # → _cancel_after_wait 의 except asyncio.CancelledError: pass (:1517-1518)
```

- `finally`(`:1521-1524`)는 `self._pending_cancel_tasks.get(ticker) is current_task` 를 보므로
  **먼저 pop 해 두면** 조용히 지나간다(이중 pop 없음).
- 관측은 **선택** — 넣는다면 `[partial_cancel_timer_cleared] ticker=… order_no=…` INFO 1행.

### 4.3 `src/engine/scheduler.py` (라인 상한 대상)

| # | 위치 | 변경 | 라인 |
|---|---|---|---|
| S1 | `:3737-3739` | `_pending_cancel_order_no.clear()` 동반 | **+1 → 3,899L** |
| S2 | `:3516-3520` | 죽은 import `update_trade_status`(호출 0건) 제거 | −1 |

⚠️ **S1 단독이면 상한(<3,900)에 딱 붙는다.** S2 를 함께 하거나, **cycle273b 의 F-7 leaf 위임
(−27행 내외)을 먼저 넣는다.** 순서 권고 = **F-7 → (가)**. (배포 묶음은 §8 open question.)

---

## 5. 영향받는 기존 테스트

`update_trade_status` 참조 = **117 hit / 19 파일**. 기존 단언은 전부 `c.args[0..2]` 와
`kwargs["price"]`/`kwargs.get("strategy")` 만 읽어 **keyword-only 인자 추가에 무영향**이다.

### 반드시 고쳐야 하는 것 (2곳 + 1 거울)

| 파일·줄 | 왜 | 무엇 |
|---|---|---|
| `tests/integration/conftest.py:159` | `fake_update_trade_status(...)` 가 **명시 시그니처** → `match_partial=`/`order_no=` 전달 시 `TypeError` | `*, order_no=None, match_partial=False` 추가 + `calls` 에 기록 |
| `tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py:251` | 동일 | 동일 |
| 같은 파일 `:102-119` `FakeDb.update_status` | docstring 이 "실 WHERE 의 거울" 이라고 선언한다 — "PENDING 단독" 을 두면 **초록인 채로 낡은 계약을 검증** | `match_partial`(+`order_no`) 분기를 거울에 반영. `:640-643` docstring 의 "PENDING 단독 필터 때문" 문구도 정정 |

### 확인만 하면 되는 것

`tests/unit/db/test_cycleM2a_trade_history_pg.py:110-113` 은 `"PENDING" in sql or "PENDING" in str(args)`
라 리스트가 와도 통과한다. 다만 `:89` 주석 "4-eq 필터 보존" 이 낡으므로 **주석 갱신**.
`test_cycle163_ast_persistence.py:68` 은 `"step=update_trade_status"` 문자열 존속을 요구 ⇒
`order_engine.py:1283` 로그 문구 **보존 의무**.

---

## 6. 검증 게이트 · 뮤테이션 · D+1

### 게이트
1. 보류 Red 17건 전부 GREEN 전환 (§7 표)
2. `pytest tests/unit/db tests/unit/engine tests/unit/ast` 회귀 0
3. `pytest tests/integration/test_buy_flow.py test_sell_flow.py test_chegyeol_race.py test_reset_daily_state.py test_cycleM2a_hotpath_roundtrip.py`
4. 백엔드 전체 PASS (직전 기준선 **7,548**)
5. `python -m pytest ... --log-level=DEBUG` 재실행(CI 루트 로거 DEBUG 차이 선제 확인)

### 뮤테이션 — 전부 KILLED 여야 한다
| # | 뮤테이션 | 잡는 가드 |
|---|---|---|
| M1 | `match_partial` 기본값 `True` | AST1 + B2 |
| M2 | C5/C6 에 `match_partial=True` 추가 | AST2 |
| M3 | 타이머 해제에서 `order_no` 비교 삭제(`pop(ticker)` 단독) | A2 · A3 · AST4 |
| M4 | `_pending_cancel_tasks.pop` 만 하고 `task.cancel()` 삭제 | **A4** |
| M5 | 타이머 해제를 매수 분기에만 넣고 매도 누락 | A1b · AST3[_handle_sell_fill] |
| M6 | `match_partial=True` 를 C2/C4(PARTIAL)에도 붙임 | AST1(정확히 2회) |

### D+1 실측 서명 (배포 다음 영업일) — ⚠️ **의미 반전 없음, 배포 전후 grep 합산 가능**
| 서명 | 기대 |
|---|---|
| `부분 체결 잔여 취소 실패` / APBK0927 | **0건**(부분체결이 있었던 날 한정 — 없으면 무증거) |
| `[buy_fill_correction_unique_violation]` / `[sell_fill_correction_unique_violation]` | 0건 |
| `체결통보 선행 race — COMPLETED 직접 INSERT` | **기준선 대비 증가 0** (cycle273b F-1 을 같은 커밋에 실으면 이 서명이 order_no 표기 불일치의 조기경보다) |
| `[trade_status_update_by_order_no]` | 감소(자기치유 호출이 준다) |
| `[buy_fill_correction_forced_update_zero]` | 0건 |
| 매수 체결 건수 · `trade_history` 행 수 | **불변**(행위 불변의 증거) |

---

## 7. 보류 Red 파일 (이관 대상)

| 보류 경로 | → 최종 목적지 | RED/GREEN(HEAD) |
|---|---|---|
| `…/pending_tests/cycle273a/test_cycle273a_cancel_timer_on_full_fill.py` | `tests/unit/engine/test_cycle273a_cancel_timer_on_full_fill.py` | 3 RED / 2 GREEN |
| `…/pending_tests/cycle273a/test_cycle273a_partial_row_full_fill_no_correction.py` | `tests/unit/engine/test_cycle273a_partial_row_full_fill_no_correction.py` | 2 RED / 1 GREEN |
| `…/pending_tests/cycle273a/test_cycle273a_update_trade_status_match_partial.py` | `tests/unit/db/test_cycle273a_update_trade_status_match_partial.py` | 2 RED / 1 GREEN |
| `…/pending_tests/cycle273a/test_cycle273a_ast_partial_optin_and_timer.py` | `tests/unit/ast/test_cycle273a_ast_partial_optin_and_timer.py` | 5 RED / 1 GREEN |
| **합계** | | **12 RED / 5 GREEN** |

(보류 루트 = `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/823ca95c-aa00-4436-b4f5-5eac77e3c1db/scratchpad/pending_tests/`)

실행:
```bash
python -m pytest <보류경로> -q -p no:cacheprovider -c /Users/koscom/Projects/auto_stock/pyproject.toml
```
⚠️ `-c` 로 리포 `pyproject.toml` 을 명시해야 `asyncio_mode=auto`·마커 등록이 적용된다
(보류 위치는 `testpaths` 밖이라 설정 자동 탐색이 안 된다). 이관 후에는 불필요.

이관 시 삭제할 것 = 각 파일의 리포 밖 전용 보조(있는 경우). AST 파일은 `import src` 로 루트를
유도하므로 `tests/unit/ast/` 에서도 그대로 동작한다(`parents[N]` 하드코딩 아님).

---

## 8. 8영역 절차 · 배포

### 8.1 sha 핀 (커밋 시)
`src/engine/order_engine.py` = 8영역. **작업 커밋 전** `_content_sha` 를 **4곳 전부**에 같은 값으로 등록:

| # | 파일 | 변수 |
|---|---|---|
| 1 | `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` | `_APPROVED_CONTENT_SHA` |
| 2 | `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` | `_PREEXISTING_CONTENT_SHA` |
| 3 | `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` | `_PREEXISTING_CONTENT_SHA` |
| 4 | `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` | `_ALLOWED_CONTENT_SHA` |

값이 갈리거나 한 곳만 등록되면 그 자체가 결함(`test_g3_9a/9b` "핀은 항상 4곳").
커밋 직후 **후속 커밋으로 네 dict 를 비운다** — cycle271 의 `d4cbb58` → `4d88aa6` 절차 그대로.

### 8.2 배포
- 모드 = **full**(`src/**` 변경). 창 = 15:30~19:55 / 20:20~익일 07:45 / 주말·공휴일.
  **20:00~20:15 금지.** 보유 중 KRX 메인(09:00~15:30) push 금지(D6).
- ⚠️ **cycle272 와 동시 작업 중이다.** 병합 전 `git diff` 로 `order_engine.py`·`trade_history.py`
  가 그쪽 diff 에 없는지 확인한다(조사 시점 기준 무접촉).

---

## 9. 범위 밖 (열어 둔 채로 남는 것)

| # | 항목 | 왜 이번이 아닌가 |
|---|---|---|
| X1 | `_completed_orders` 누수(F-271-1) 자체 | 워크리스트 200행이 "cycle271 에서 `.clear()` 추가 금지 — 사이클 30 가드의 세션 경계 의미 변경 = **별도 승인·명세**" 라고 못박았다. (가)-b 는 그 누수의 **트리거**(가짜 `affected=0`)를 닫지만 메커니즘(except 분기 미소비 + 일일 clear 부재)은 남는다. ⚠️ `except` 안 `discard` 는 **권하지 않는다** — 진짜 race + 다른 이유의 UniqueViolation 이 겹치면 cycle271 `_insert_pending_buy_or_absorb_race` 가 증거 없음으로 raise 한다. 누수는 **일일 clear** 로 닫는 것이 맞다 |
| X2 | strategy 불일치로 인한 `affected=0` | 사이클 147/161 이 **설계로 인정한** 경로. 계속 살아 있다 |
| X3 | REST `ODNO` ↔ 체결통보 `fields[2]` 표기 정규화 | cycle273b §최대 위험 참조. 이번엔 **관측·서명**으로만 방어 |
| X4 | 부분체결↔전량체결 30초 내 페어의 실제 빈도 | 09-10 `매수 부분 체결` 1건이 유일 표본(정본 §정정 V-8) |

---

## 10. Open questions (team-leader/사용자 결정 — 재해석 금지)

| # | 질문 | tdd-engineer 권고 |
|---|---|---|
| **O-A1** | (가)-b 와 cycle273b 의 F-1 은 **같은 함수**(`update_trade_status`)를 건드린다. 한 커밋인가, (가)/(다) 두 커밋인가? | **한 커밋** 권고(diff·리뷰·핀 절차 비용 최소). 단 사용자 지시 순서는 "가 → 다" 이므로 **명세는 분리**해 둔다 |
| **O-A2** | `[partial_cancel_timer_cleared]` INFO 를 넣을 것인가? | **넣는다**(1행, 매매 경로 밖). D+1 에 "해제가 실제로 일어났다" 는 양성 대조가 된다 — APBK0927 0건은 "부분체결이 없었다" 와 구별되지 않는다 |
| **O-A3** | `scheduler.py` S2(죽은 import 제거) 를 이번에 하는가? | **한다**(−1행, S1 의 +1행 상쇄). 단 scheduler 변경은 승인 대상이므로 명시 확인 |
| **O-A4** | (가) 와 (다)의 **배포 묶음** | 같은 날 배포 권고(둘 다 행위 불변). cycle272(VB/LTV 진입 −27.6% 추정)와는 **날짜 분리**(귀인 오염) |
