# cycle273 U-A — D2(가) C235-V2 + D2(다) 필옵틱스 무행위 3건 코드 확정 (읽기 전용)

**작성 2026-09-10 · 기준 커밋 `a10191b`(HEAD) · 워킹트리 = HEAD 와 동일**
(`git diff --stat HEAD -- src/engine/order_engine.py src/db/trade_history.py` → 0. 이 문서의
**모든 줄 번호는 HEAD 기준**이며, 정본 조사 문서 두 편의 줄 번호는 cycle271(`d4cbb58`) 이전 것이라
**최대 +41행 어긋난다** — 대조 표를 §0-1 에 둔다.)

**이 문서는 코드를 한 글자도 바꾸지 않았다.** 산출은 이 md 하나뿐이다.

---

## 0. 선요약

| 항목 | 결론 |
|---|---|
| (가) C235-V2-a 잔여취소 타이머 미해제 | **확정** — 전량 체결 분기 2곳(`order_engine.py:1262-1360` 매수 / `:1433-1498` 매도)에 `_pending_cancel_tasks` 참조가 **0건**. 타이머는 `_schedule_cancel(:1506)` / `_schedule_cancel_and_reorder(:1528)` 만 만들고 **자기 자신·`_reset_daily_state`(scheduler `:3737-3739`) 만** 지운다 |
| (가) C235-V2-b 1차 `update_trade_status` PARTIAL 미포괄 | **확정** — `trade_history.py:107` 이 status 필터를 `PENDING` **단독 리터럴**로 박는다. `_update_trade_status_by_order_no`(`:212-229`)만 cycle235 N1-b 로 `PENDING∪PARTIAL` 이다 |
| cycle271 `_completed_orders` 누수(F-271-1)와 같은 뿌리인가 | **뿌리는 절반만 같다.** 누수의 **트리거**는 C235-V2-b 가 만드는 가짜 `affected=0` 이 맞다(그 경로가 `:1291`/`:1456` 에서 set 에 넣고 UniqueViolation 분기 `:1309`/`:1474` 는 **discard 하지 않는다**). 그러나 누수의 **메커니즘**(UniqueViolation 분기 미소비 + `reset_daily_state`(`:1565-1577`)가 `_completed_orders` 를 비우지 않음)은 별개이며 C235-V2-b 로 자동으로 닫히지 않는다 — §4 |
| (다) F-3 `[trade_status_multi_update]` | 무행위 **증명 가능**. 다만 **놓을 자리를 바꾸자는 제안**이 있다(order_engine 2곳 → `trade_history.update_trade_status` 1곳) — §5.1, 미승인 사안이라 §9 에 질문으로 남김 |
| (다) F-1/F-2 `order_no` in WHERE | 무행위 **증명 가능**(WHERE 를 **좁히기만** 한다). ⚠️ **단 하나의 실질 위험** = REST `ODNO` 와 체결통보 `fields[2]` 의 **문자열 표기가 다르면** 모든 체결이 보정 경로로 낙하한다 — §6.2 |
| (다) F-7 `_selling` 장기 유지 가시화 | 지점 = `scheduler.py:3572-3601`(HEAD). `scheduler.py` = **3,898L / 상한 <3,900L** ⇒ 여유 **1행**. **leaf 위임 필수** — §7 |
| 🔴 최대 함정 | **`update_trade_status` 의 status 필터를 전역으로 넓히면 무행위가 아니다.** `_cancel_after_wait`(`:1515`)·`_cancel_and_reorder`(`:1541`)의 **CANCELLED** 호출이 함께 넓어져 **PARTIAL 행이 CANCELLED 로 뒤집히고**, 그 행은 정산(`get_today_trades_for_settlement`, COMPLETED∪PARTIAL)에서 **빠지고** sync(`get_today_buy_trades_for_sync`, CANCELLED 제외)에서도 **빠진다** — §3.3 |

---

## 0-1. 줄 번호 대조 (정본 문서 ↔ HEAD)

정본 조사 2편은 cycle271 배포(`d4cbb58`, `order_engine.py` +41행) **이전**에 쓰였다.

| 무엇 | 정본 문서 표기 | **HEAD(`a10191b`)** |
|---|---|---|
| `_handle_buy_fill` 진입 | 1109 / 1150 | **`:1150`** |
| 매수 전량 체결 분기 시작 | 1221 | **`:1262`** (`if total_filled >= ordered_qty:`) |
| 매수 1차 `update_trade_status(COMPLETED)` | 1236-1239 | **`:1277-1280`** |
| `_completed_orders.add` (매수) | — | **`:1291`** |
| `[buy_fill_correction_unique_violation]` | 1274 | **`:1314-1317`** (`except` 는 `:1309`) |
| 매핑 4종 pop (매수) | 1310-1313 | **`:1353-1356`** |
| `_completed_buy_orders.add` | 1316 | **`:1357`** |
| "매수 전량 체결" INFO | 1319 | **`:1360`** |
| 매수 부분 체결 분기 | 1320-1328 | **`:1361-1369`** (`update_trade_status(PARTIAL)` = `:1364-1367`, `_schedule_cancel` = **`:1368`**) |
| `_handle_sell_fill` 진입 | 1370 | **`:1371`** |
| 매도 전량 체결 분기 시작 | — | **`:1433`** |
| 매도 1차 `update_trade_status(COMPLETED)` | 1408-1411 | **`:1449-1452`** |
| `_completed_orders.add` (매도) | — | **`:1456`** |
| `[sell_fill_correction_unique_violation]` | — | **`:1478-1481`** (`except` 는 `:1474`) |
| 매도 부분 체결 분기 | — | **`:1499-1504`** (`_schedule_cancel_and_reorder` = **`:1503`**) |
| `_schedule_cancel` | 1465-1485 | **`:1506-1526`** (`sleep` `:1513` · `cancel_order` `:1514` · `update_trade_status(CANCELLED)` **`:1515`** · `except Exception` **`:1519-1520`** · finally pop `:1521-1524`) |
| `_schedule_cancel_and_reorder` | 1462 | **`:1528-1563`** (`cancel_order` `:1539` · `update_trade_status(CANCELLED)` **`:1541`** · 재주문 `:1545-1552`) |
| `PARTIAL_FILL_WAIT = 30` | 65 | **`:66`** |
| `_pending_cancel_tasks` 선언 | 79 | **`:79`** |
| `reset_daily_state` | — | **`:1565-1577`** |
| `update_trade_status` (db) | 88-123 | **`trade_history.py:88-123`** (동일 — 이 파일은 cycle271 무접촉) |
| `_update_trade_status_by_order_no` | 179 | **`trade_history.py:179-245`** |
| `_selling` 재대조 (scheduler) | 3572-3601 | **`scheduler.py:3572-3601`** (동일) |

---

## 1. (가) C235-V2-a — 전량 체결이 잔여취소 타이머를 해제하지 않는다

### 1.1 타이머의 전 생애 (전수)

`_pending_cancel_tasks` 를 읽거나 쓰는 곳은 **소스 전체에 12곳**뿐이다
(`grep -rn --include='*.py' "_pending_cancel_tasks" src/`):

| 줄 | 무엇 |
|---|---|
| `order_engine.py:79` | 선언 `dict[str, asyncio.Task]` — **키가 `ticker`** (order_no 아님) |
| `:1508-1509` | `_schedule_cancel` 진입 — 같은 **ticker** 의 기존 task 무조건 `.cancel()` |
| `:1523-1524` | `_cancel_after_wait` 의 `finally` — 자기 자신일 때만 pop |
| `:1526` | 등록 |
| `:1532-1533` | `_schedule_cancel_and_reorder` 진입 — 같은 ticker 기존 task `.cancel()` |
| `:1560-1561` | `_cancel_and_reorder` 의 `finally` — 자기 자신일 때만 pop |
| `:1563` | 등록 |
| `scheduler.py:1301` | 상태 조회(읽기 전용, `"pending_cancels"`) |
| `scheduler.py:3737-3739` | `_reset_daily_state` — 전량 `.cancel()` + `.clear()` (**20:10 정산 시각**) |

⇒ **전량 체결 분기 안(매수 `:1262-1360`, 매도 `:1433-1498`)에는 단 한 건도 없다.**
30초 타이머를 멈출 수 있는 것은 (a) 같은 ticker 의 **다음** 부분체결, (b) 자기 만료,
(c) **20:10 정산** 셋뿐이다.

### 1.2 004990(09-10 09:05) 재현 경로

```
09:05:01  체결통보 3/5  → _handle_buy_fill → else 분기(:1361)
                         → update_trade_status(BUY, PARTIAL)  (:1364)   ← 행이 PARTIAL 이 된다
                         → _schedule_cancel(004990, 0000305100, 5, kojiro)  (:1368)
                            └ _pending_cancel_tasks["004990"] = task  (:1526)
09:05:01  체결통보 5/5  → _handle_buy_fill → if 분기(:1262)
                         → update_trade_status(BUY, COMPLETED)  (:1277)  ← WHERE status='PENDING' → affected=0
                         → :1291 _completed_orders.add("0000305100")
                         → :1294 보정 insert_trade(COMPLETED) → UniqueViolation
                         → :1314 [buy_fill_correction_unique_violation] WARNING
                         → :1320 _update_trade_status_by_order_no(...) → affected=1  (자기치유)
                         ── _pending_cancel_tasks 는 손대지 않는다 ──
09:05:32  타이머 만료   → :1513 sleep(30) 종료 → :1514 cancel_order(0000305100, 0, cancel_all=True)
                         → KIS APBK0927 "정정취소 가능수량이 없습니다" (rt_cd=7)
                         → :1519-1520 except Exception → logger.exception("부분 체결 잔여 취소 실패: ...")
```

`system_logs` 기준 **1회 발화 = ERROR 3행**(`[kis_rejection]` DB 전용 + `src.api.base` + `src.engine.order_engine`).
발화 하한 2회(08-28 `257720`, 09-10 `004990`) — 정본 §정정 V-2 / V-6.

### 1.3 오늘 이 코드가 **매매를 망치지 않은** 유일한 이유

`cancel_order(order_no, 0, cancel_all=True)` 는 **그 order_no 한 건**을 대상으로 하고 그 주문의
잔량이 물리적으로 0 이므로 KIS 가 거부한다. 다른 주문을 건드릴 경로가 없다.

⚠️ **그러나 매도 쪽에는 잠재적 이빨이 있다.** `_schedule_cancel_and_reorder` 는 취소 성공 뒤
`remaining` **주를 재주문**한다(`:1545-1552`). `remaining` 은 **부분체결 시점에 계산된 상수**
(`:1502 remaining = ordered_qty - total_filled`)라 그 뒤 전량 체결되면 **낡은 값**이다. 지금은
`cancel_order` 가 APBK0927 로 **던져서** `:1545` 에 도달하지 못할 뿐이다 —
즉 **"KIS 가 거부해 주는 것"이 유일한 중복매도 방어선**이다. (가) 는 이 우연 의존을 없앤다.

### 1.4 🔴 (가) 를 그냥 `self._pending_cancel_tasks.pop(ticker).cancel()` 로 쓰면 안 되는 이유

`_pending_cancel_tasks` 의 **키가 order_no 가 아니라 ticker** 다(`:79`). 그리고 매수·매도가
**같은 dict 를 공유**한다(`_schedule_cancel` `:1526` 과 `_schedule_cancel_and_reorder` `:1563`).
따라서 ticker 만 보고 지우면 다음이 깨진다:

- 종목 T 의 **매수** 부분체결 → `_pending_cancel_tasks["T"] = 매수취소타이머`
- 잠시 뒤 T 의 **매도**가 전량 체결 → (가) 가 `_pending_cancel_tasks["T"]` 를 지움
- ⇒ **매수 잔량 취소가 영구 실종** — 미체결 잔량이 장 마감까지 남아 예수금·`pending` 회계가 어긋난다.

⇒ **(가) 는 반드시 "그 타이머가 이 order_no 의 것일 때만" 취소해야 한다.** 구체안은 §3.1.

---

## 2. (가) C235-V2-b — 1차 `update_trade_status` 의 status 필터

### 2.1 코드 (HEAD, `src/db/trade_history.py:88-123`)

```python
 88 async def update_trade_status(
 89     ticker: str,
 90     trade_type: TradeType,
 91     status: TradeStatus,
 92     strategy: str = "momentum",
 93     price: int | None = None,
 94     profit_loss: float | None = None,
 95 ) -> int:
 96     """최신 PENDING 거래 기록의 상태를 업데이트하고 영향받은 행 수를 반환한다."""
...
107     args.extend([ticker, trade_type.value, TradeStatus.PENDING.value, strategy])
108     ticker_idx = len(args) - 3
109     type_idx = len(args) - 2
110     pending_idx = len(args) - 1
111     strategy_idx = len(args)
112
113     sql = (
114         f"UPDATE trade_history SET {', '.join(set_clauses)} "
115         f"WHERE ticker = ${ticker_idx} AND trade_type = ${type_idx} "
116         f"AND status = ${pending_idx} AND strategy = ${strategy_idx}"
117     )
```

- 매칭 키 = `(ticker, trade_type, status='PENDING', strategy)` — **주문 단위가 아니다**(F-1 대상).
- `status` 는 **`PENDING` 리터럴 고정** — 인자로 넘어온 `status` 는 **SET 절에만** 쓰인다(C235-V2-b 대상).
- `ORDER BY`·`LIMIT` 없음 ⇒ 조건 만족 행 **전부** 갱신(F-3 대상).
- docstring `:96` "최신 PENDING" 은 SQL 과 어긋난다("최신" 이 없다).

대조군 — `_update_trade_status_by_order_no`(`:179-245`)는 cycle235 N1-b 로 이미 넓다:

```python
216     args.extend([
217         order_no, trade_type.value,
218         [TradeStatus.PENDING.value, TradeStatus.PARTIAL.value],
219     ])
...
224     f"WHERE order_no = ${order_no_idx} AND trade_type = ${type_idx} "
225     f"AND status = ANY(${status_idx}::text[])"
```

### 2.2 호출자 전수 (`grep -rn --include='*.py' "update_trade_status" src/`)

| # | 위치 | 인자 | 오늘 PARTIAL 행을 만나면 | C235-V2-b 대상? |
|---|---|---|---|---|
| C1 | `order_engine.py:1277-1280` | BUY, **COMPLETED**, price | `affected=0` → 보정 INSERT → UniqueViolation → 강제 UPDATE | **✅ 넓힌다** |
| C2 | `order_engine.py:1364-1367` | BUY, PARTIAL, price | `affected=0`(2차 부분체결 시 price 미갱신) | ❌ 유지(무해·범위 밖) |
| C3 | `order_engine.py:1449-1452` | SELL, **COMPLETED**, price, pnl | C1 과 동일 | **✅ 넓힌다** |
| C4 | `order_engine.py:1501` | SELL, PARTIAL, price, pnl | C2 와 동일 | ❌ 유지 |
| C5 | `order_engine.py:1515` (`_cancel_after_wait`) | BUY, **CANCELLED** | `affected=0` → 행이 PARTIAL 로 남는다 | 🔴 **절대 넓히지 않는다** |
| C6 | `order_engine.py:1541` (`_cancel_and_reorder`) | SELL, **CANCELLED** | 동일 | 🔴 **절대 넓히지 않는다** |
| — | `scheduler.py:3517` | **import 만, 호출 0건**(`_sync_positions_from_balance` 본문에 `update_trade_status(` 없음 = 죽은 import) | — | — |

---

## 3. 🔴 무행위 경계 — 전역 확대가 왜 무행위가 아닌가

### 3.1 (가)-a 최소 설계 (타이머 해제)

**필요한 것은 dict 하나 + 4줄이다.**

```
order_engine.py:79 근처   self._pending_cancel_order_no: dict[str, str] = {}   # ticker -> 그 타이머가 지키는 order_no
:1526 직전               self._pending_cancel_order_no[ticker] = order_no
:1563 직전               self._pending_cancel_order_no[ticker] = order_no
:1521-1524 finally       (본인 pop 시) self._pending_cancel_order_no.pop(ticker, None)
:1558-1561 finally       동일
```

전량 체결 분기 2곳(`:1262` 블록 끝 · `:1433` 블록 끝)에서:

```
if self._pending_cancel_order_no.get(ticker) == order_no:
    task = self._pending_cancel_tasks.pop(ticker, None)
    self._pending_cancel_order_no.pop(ticker, None)
    if task is not None and not task.done():
        task.cancel()          # → _cancel_after_wait 의 except asyncio.CancelledError: pass (:1517-1518)
```

- `task.cancel()` 은 `_cancel_after_wait` 의 `sleep`(`:1513`)에서 `CancelledError` 를 일으키고
  그것은 이미 `:1517-1518 except asyncio.CancelledError: pass` 로 **삼켜지도록 설계돼 있다**.
  `finally`(`:1521-1524`)의 pop 은 `self._pending_cancel_tasks.get(ticker) is current_task` 를
  보므로 우리가 **먼저 pop 해 두면** 조용히 지나간다(이중 pop 없음).
- `scheduler._reset_daily_state`(`:3737-3739`)는 `.values()` 순회 후 `.clear()` 라 새 dict 도
  같이 비워야 한다(그 파일은 **8영역 밖이지만 라인 상한 대상** — §7).

**무행위 증명**
1. 취소되는 대상은 "이미 100% 체결된 order_no 에 대한 `cancel_order`" 뿐이다. 그 호출은 오늘
   **항상 APBK0927 로 실패**한다(08-28·09-10 실측 2/2). 성공 사례 0건 ⇒ 주문 상태 변화 0.
2. 그 뒤에 오는 `update_trade_status(CANCELLED)`(C5/C6)는 **오늘도 실행되지 않는다**
   (`cancel_order` 가 던져 같은 `try` 안에서 건너뛴다) ⇒ DB 변화 0.
3. 매도 재주문(`:1545-1552`)도 같은 이유로 오늘 실행되지 않는다 ⇒ 주문 변화 0.
   (오히려 §1.3 의 우연 의존이 사라진다 = **위험 감소 방향**.)
4. `order_no` 일치 게이트가 §1.4 의 교차 취소를 구조적으로 막는다 ⇒ 기존 정상 타이머 무영향.
5. 관측: `[partial_cancel_timer_cleared] ticker=… order_no=…` INFO 1행(선택). 발화해도 매매 경로 밖.

### 3.2 (가)-b 최소 설계 (PARTIAL 포괄)

```python
# trade_history.py:88 시그니처에 keyword-only 추가 (기본값이 현행 SQL 을 byte 동일 보존)
async def update_trade_status(
    ticker, trade_type, status, strategy="momentum", price=None, profit_loss=None,
    *, match_partial: bool = False, order_no: str | None = None,   # ← F-1 도 여기
) -> int:
```

- `match_partial=False` (기본) → `AND status = $n` (**현행 SQL 문자열 그대로**)
- `match_partial=True` → `AND status = ANY($n::text[])` with `['PENDING','PARTIAL']`
  (= `_update_trade_status_by_order_no` 와 같은 형태 = cycle235 N1-b 답습)
- 호출부 변경은 **C1·C3 두 곳에 `match_partial=True` 한 인자**뿐. C2/C4/C5/C6·scheduler 는 무접촉.

**무행위 증명**
- `affected` 는 매매 결정에 쓰이지 않는다. 유일한 소비처는 `if affected == 0:`(`:1288`, `:1453`)
  = **DB 보정 체인의 진입 여부**뿐이다. 포지션 등록(`:1229-1257`)·`pending_buys` 정리(`:1257-1260`)·
  매도 포지션 삭제(`:1435-1448`)는 전부 이 호출 **앞**에서 끝난다.
- 최종 DB 상태는 동일하다: 오늘은 `PARTIAL --(강제 UPDATE)--> COMPLETED(price)`,
  바뀐 뒤는 `PARTIAL --(1차 UPDATE)--> COMPLETED(price)`. 같은 행, 같은 값.
- 사라지는 것: WARNING `[buy_fill_correction_unique_violation]` 1행 + INFO
  `[trade_status_update_by_order_no]` 1행 + `_completed_orders.add` 1건(§4).
- 진짜 "체결통보 선행 race"(행 자체가 없음)는 여전히 `affected=0` ⇒ 보정 INSERT 경로 **보존**.

### 3.3 🔴 넓히면 안 되는 곳 — C5/C6 (CANCELLED)

`match_partial` 를 **전역 기본값 True** 로 하거나 SQL 리터럴을 통째로 넓히면 C5/C6 이 함께 넓어진다.
그 순간:

```
부분체결(3/5) → 행 = PARTIAL(quantity=5, price=체결가)
30초 뒤 잔여취소 성공 → C5 가 그 행을 CANCELLED 로 뒤집는다
```

결과(전부 실측 코드 근거):

| 영향 | 근거 |
|---|---|
| **정산에서 사라진다** | `get_today_trades_for_settlement`(`trade_history.py:330-348`)는 `status = ANY(['COMPLETED','PARTIAL'])` — CANCELLED 제외. `buy_total`/`sell_total`/`daily_realized_pnl`(`scheduler.py:3626-3639`)이 바뀌고 `daily_performance` 수치가 달라진다 |
| **sync 판정에서 사라진다** | `get_today_buy_trades_for_sync`(`:456-481`) / `..._sell_...`(`:484-501`) 둘 다 `['PENDING','COMPLETED','PARTIAL']` — CANCELLED 제외. `_sync_orders_to_db` 가 "DB 에 없는 주문"으로 보고 재-INSERT 를 시도한다 ⇒ migration 029 부분 UNIQUE(`(ticker, order_no, trade_type)`, status 무관)에 걸려 UniqueViolation = 042700 핑퐁 사고 계열의 문 앞까지 간다 |
| **부분 체결 사실 자체가 소실** | 3주를 실제로 샀는데 기록은 "취소" |

⇒ **C235-V2-b 는 반드시 call-site opt-in 이어야 한다.** 이 문장이 이 문서에서 가장 중요한 한 줄이다.
AST 가드로 "`match_partial=True` 는 소스 전체에 정확히 2회, 그 둘은 `TradeStatus.COMPLETED` 호출"
을 못박기를 권한다.

---

## 4. cycle271 `_completed_orders` 누수(F-271-1)와의 관계

### 4.1 누수 경로 (HEAD 코드)

```
:1288  if affected == 0:
:1291      self._completed_orders.add(order_no)          ← 넣는다
:1293      try: await insert_trade(COMPLETED)            ← 성공하면 execute_buy(:423-425) 가 소비
:1309      except Exception:                             ← UniqueViolation
:1314          logger.warning("[buy_fill_correction_unique_violation] ...")
:1320          _update_trade_status_by_order_no(...)     ← 자기치유
           ── discard 없음 ──                            ← 🔴 누수
```

매도도 동일(`:1456` add / `:1474` except / **discard 없음**).
그리고 `reset_daily_state`(`:1565-1577`)는 `_sell_rejection`·`_nxt_downgrade_logged_today`·
**`_completed_buy_orders`(`:1577`)** 만 비우고 **`_completed_orders`(`:89`)는 비우지 않는다.**

004990 시퀀스에서는 `execute_buy` 가 **이미 반환한 뒤**(`"매수 주문 접수"` INFO `:447-448` 이
`insert_trade` 반환 후에만 찍히고, EC2 원문에서 그 행이 부분체결보다 **앞**) 이 add 가 일어나므로
**소비자가 영원히 오지 않는다**.

### 4.2 "같은 뿌리인가" 에 대한 정확한 답

| 축 | 답 |
|---|---|
| **트리거** | **같다.** 오늘 관측된 누수의 유일한 입구는 "`affected=0` 인데 행은 존재" = C235-V2-b 가 만드는 가짜 0 이다. C235-V2-b 를 고치면 **이 입구가 닫힌다** |
| **메커니즘** | **다르다.** 누수 자체는 `except` 분기의 미소비 + 일일 리셋 부재다. C235-V2-b 로도 남는 입구가 있다 — **strategy 불일치**로 1차 UPDATE 가 0을 내는 경우(`:1277` 의 `strategy=strategy_id` 필터). 그 경로는 사이클 147/161 이 **설계로 인정한** 경로라 계속 살아 있고, 그때도 UniqueViolation → discard 없음 |
| **잔존 위험** | KIS `order_no` 는 **하루 단위 유일성**뿐이다. 며칠 쌓인 스테일 `order_no` 가 새 주문번호와 충돌하면 `execute_buy:423` 이 `already_completed=True` 로 오판해 **PENDING INSERT 를 통째로 건너뛴다**(이후 체결통보가 보정 INSERT 로 복구하긴 한다). 확률은 낮으나 0 이 아니다 |
| **이번에 손대도 되나** | ⚠️ 워크리스트 200행이 **"cycle271 에서 `.clear()` 추가 금지 — 사이클 30 가드의 세션 경계 의미 변경 = 별도 승인·명세"** 라고 못박고, 동시에 **"명세 F-3 을 F-1/C235-V2 와 묶어 판단"** 하라고 적었다. 즉 **판단은 이번 사이클, 실행은 별도 승인**이 문면이다 ⇒ §9 질문 |
| **`except` 안 discard 는 권하지 않는다** | 그 분기에서 discard 하면, 진짜 race + 다른 이유의 UniqueViolation(예: 같은 키 CANCELLED 잔존)이 겹칠 때 `execute_buy` 가 `already_completed=False` 로 보고 PENDING INSERT 를 시도 → cycle271 `_insert_pending_buy_or_absorb_race`(`:233-243`)가 **증거 없음으로 raise** → `execute_buy` 밖으로 전파. **현행(discard 안 함)이 더 안전하다.** 누수는 **일일 clear** 로 닫는 것이 맞다 |

---

## 5. (다) F-3 — `[trade_status_multi_update]`

### 5.1 어디에 놓을 것인가

정본 §6 표는 **`order_engine.py` 2지점**(C1·C3)을 적었다. 코드를 보고 나면 **`trade_history.update_trade_status`
안(`:119` 부근, `affected` 가 계산되는 바로 그 자리)** 이 더 낫다는 근거가 셋이다:

1. **범위** — C1·C3 만이 아니라 C2·C4·**C5·C6**(CANCELLED)까지 덮는다. §3.3 이 보였듯 CANCELLED
   축의 오매칭이야말로 데이터가 **소실**되는 쪽이다.
2. **8영역 diff 축소** — `order_engine.py`(8영역) 대신 `trade_history.py`(db, 8영역 아님) 한 파일.
   (가)·F-1/F-2 로 이미 `order_engine.py` 를 열지만, 관측 코드를 8영역 밖에 두는 것은 cycle258
   `observer_trace` 계열의 관례와도 맞는다.
3. **단일 진실원** — F-1 과 같은 함수라 diff 가 한 덩어리로 읽힌다.

⚠️ 다만 이것은 **정본 표의 문면을 바꾸는 제안**이다. 사용자 결정 원문은 "F-3 `[trade_status_multi_update]`
관측" 이라 **지점을 지정하지 않았다** — 그래도 재해석 금지 원칙에 따라 §9 에 질문으로 남긴다.

### 5.2 형태 (권고안)

```python
    affected = _parse_affected(result)
    if affected > 1:
        logger.warning(
            "[trade_status_multi_update] ticker=%s trade_type=%s status=%s strategy=%s "
            "order_no=%s affected=%d — 한 주문의 체결이 다중 행을 덮었다",
            ticker, trade_type.value, status.value, strategy, order_no or "-", affected,
        )
```

- **WARNING 이상** — `_DbLogHandler` 가 INFO 컷이라 DEBUG/INFO 는 `system_logs` 에 안 남는다
  (교훈 메모 `feedback_caplog_debug_level`). WARNING 은 30일 보존(`system_logs.py:32-33`).
- **cap 불필요** — 발화가 곧 결함이고, 정상 운영에서는 0 이어야 한다. (폭주가 걱정되면
  `KstDailyEmitCap` 1회/(ticker,trade_type)/일; 그러나 억제는 재발 계수를 잃는다.)
- **never-raise** — `logger.warning` 자체가 예외를 던지지 않지만, 형식 인자에 `%r` 을 쓰지 않아
  추가 방어가 필요 없다. 굳이 넣는다면 `observer_trace.trace_observer_failure` 를 쓴다.

### 5.3 무행위 증명
반환값·SQL·인자 전부 불변, 로그 1행 추가뿐. `logger` 는 이미 모듈 상단에 있다.

### 5.4 ⚠️ F-3 의 진단력에 대한 정직한 한계

**F-1 과 같은 커밋에 들어가면 F-3 는 과거를 재지 못한다.** F-1 이 `order_no` 를 WHERE 에 넣는 순간
migration 029 부분 UNIQUE `(ticker, order_no, trade_type)` 때문에 `affected > 1` 은 **비어 있지 않은
order_no 에 대해 구조적으로 불가능**해진다. 즉 F-3 는 D-3("과거 재발 여부를 셀 수 없다")을
**닫지 못하고**, 대신 **영구 회귀 감시자**(인덱스나 WHERE 가 후퇴하면 붉어진다 / `order_no=''` 인
수기 행에는 여전히 유효)가 된다. 순서를 "F-3 먼저 관측 배포 → 며칠 뒤 F-1" 로 나누면 과거 대신
**미래 며칠치**를 셀 수 있지만, 그동안 161580 오염이 계속 일어난다. **권고 = 같은 커밋, 대신 §6.3
의 `affected == 0` 진단을 함께 넣어 F-1 의 부작용을 즉시 보이게 한다.**

---

## 6. (다) F-1/F-2 — WHERE 에 `order_no` 추가

### 6.1 최소 설계

```python
# trade_history.py — §3.2 의 시그니처에 이미 포함된 order_no 를 사용
if order_no is not None:
    args.append(order_no)
    where += f" AND order_no = ${len(args)}"
```

호출부(`order_engine.py`)는 각 지점에 `order_no=order_no` 한 인자.
`order_no=None` (기본) 이면 SQL 은 **현행과 byte 동일** ⇒ scheduler 의 죽은 import·기존 테스트 무영향.

**어느 호출부에 넣을 것인가** — 정본 F-2 는 C1·C3 만 적었다. 코드 근거로는 **6곳 전부**가 맞다:

| # | 넣어야 하는 이유 |
|---|---|
| C1·C3 | 161580 본 사건(같은 ticker·strategy 의 **다른 주문** PENDING 행을 덮었다) |
| C2·C4 | 같은 오염이 PARTIAL 축에서 일어난다 — 좁히기만 하므로 무해 |
| **C5·C6** | 🔴 **가장 위험한 축.** 부분체결한 주문 A 의 30초 타이머가 만료될 때 같은 ticker·strategy 의 **다른 주문 B 의 PENDING 행**을 `CANCELLED` 로 뒤집을 수 있다. 그러면 B 의 체결통보가 와도 1차 UPDATE 는 0(B 는 CANCELLED), 보정 INSERT 는 UniqueViolation, **강제 UPDATE 는 `PENDING∪PARTIAL` 만 보므로 CANCELLED 인 B 를 못 집는다** ⇒ `[buy_fill_correction_forced_update_zero]` ERROR + **B 행이 영구 CANCELLED** = 정산·sync 양쪽에서 소실 |

⇒ 6곳 전부 권고. 다만 정본 F-2 문면(2곳)과 다르므로 §9 질문.

### 6.2 🔴 이 사이클 최대 위험 — `order_no` 문자열 표기 불일치

- 체결통보 쪽: `src/realtime/handler.py:682` `order_no = fields[2]` — **정규화 0**.
- REST 쪽: `src/api/order.py:75` `order_no=output["ODNO"]` — **정규화 0**.
- 09-10 004990 로그에서는 둘 다 `0000305100` 으로 **일치**했다(1건 실측).

만약 어떤 경로(정정취소 응답, 폴백 주문, 특정 거래소 코드)에서 zero-padding 이 다르면
`AND order_no = $n` 이 **항상 0건**이 되어 **모든 체결이 보정 INSERT 경로로 낙하**한다.
그 결과는 (행이 다른 order_no 로 존재하므로) UniqueViolation 이 **아니라** — 새 order_no 로
**중복 행이 조용히 INSERT 된다** ⇒ 정산 이중계상. 이것이 이 사이클에서 유일하게
"조용히 나빠질 수 있는" 경로다.

**방어 3종(권고)**
1. **D+1 서명** — 배포 다음 영업일 `system_logs` 에서
   `"체결통보 선행 race — COMPLETED 직접 INSERT"`(WARNING, `:1303-1306` / `:1468-1471`) 발화가
   **배포 전 기준선 대비 증가 0** 임을 확인. 늘었다면 즉시 롤백. (새 코드 0줄 — 기존 WARNING 재활용)
2. **§6.3 진단** — `affected == 0` 일 때만 도는 1회 SELECT.
3. 계약 테스트 — 같은 KIS 응답 픽스처로 REST `ODNO` 와 WS `fields[2]` 가 동일 문자열임을 고정.

### 6.3 `[trade_status_order_no_miss]` (권고, 미승인)

`if affected == 0:` 분기(`:1288`/`:1453`)는 **이미 DB 왕복 1회(보정 INSERT)를 하는 희소 경로**다.
그 앞에 진단 SELECT 하나를 더해도 hot path 비용이 사실상 0 이다.

```
SELECT order_no, status FROM trade_history
WHERE ticker=$1 AND trade_type=$2 AND strategy=$3 AND status = ANY(['PENDING','PARTIAL'])
LIMIT 3
```
→ 결과가 있으면 `[trade_status_order_no_miss] notice_order_no=… rows=…` WARNING.
- 결과 없음 = 진짜 선행 race(정상).
- 결과 있음 = **F-1 이 실제로 가로챈 오염 1건**(161580 계열) **또는 표기 불일치**.
  둘의 구별은 `notice_order_no` 와 `rows` 의 order_no 를 눈으로 비교하면 즉시 된다.

⇒ D-3(과거를 못 센다)의 **미래분 대체 측정기**이자 §6.2 의 조기경보. 미승인 사안이므로 §9.

---

## 7. (다) F-7 — `_selling` 장기 유지 가시화 (지점 확정만)

- 지점 = **`scheduler.py:3572-3601`**(HEAD, 정본과 동일). 유지 사유 3분기 =
  `:3586-3587` `held=0` · `:3588-3589` `open_order` · `:3590-3592` `too_young`
  (`SELLING_RECONCILE_MIN_AGE_S=180`, `scheduler.py:80`). 해제는 `:3593-3599` 에서만 WARNING 을 낸다
  ⇒ **유지 중인 6h45m 은 통째로 무음**.
- 🔴 **라인 예산** — `scheduler.py` = **3,898L**, 영구 상한 **<3,900L**
  (`tests/unit/ast/test_cycle257_ast_dead_code_removed.py::TestA4SchedulerLineCount::test_line_count_below_3900`,
  cycle264 가 자매 가드로 이중화). **여유 1행.** ⇒ 3분기 안에 로그를 인라인으로 넣는 것은 불가능하다.
- **권고 = 블록 통째 leaf 위임.** `:3572-3601`(30행)을 신규 leaf
  `src/engine/selling_reconcile.py` 로 옮기고 scheduler 는 호출 1~3행만 남긴다
  (cycle233 `account_risk_watcher` · cycle259 `log_metrics_collector` · cycle264
  `open_price_observe` 의 확립된 패턴). 순증 대신 **약 −27행** ⇒ 상한 여유가 생긴다.
- 관측 형태 = `[selling_hold] ticker=… reason=held_zero|open_order|too_young elapsed_s=…`,
  **WARNING**(INFO 는 `system_logs` 미적재), `KstDailyEmitCap` **1회/(ticker,reason)/일**
  (reason 을 키에 넣지 않으면 사유 전이가 첫 사유에 먹힌다), 실패는 `observer_trace.trace_observer_failure`.
- **무행위 증명** — `continue` 3개·`discard` 순서·`write_log` 문자열을 그대로 옮기면 판정은 불변이다.
  leaf 이관은 byte 동일 이동으로 하고, 관측 호출은 각 `continue` **직전**에 추가한다(판정 뒤·행동 앞).
  ⚠️ 이 항목은 `scheduler.py` 변경이라 **U-A 파일 범위 밖**이다. 여기서는 지점·예산·패턴만 확정한다.

---

## 8. 영향받는 기존 테스트 (전수 조사)

`update_trade_status` 참조 = **117 hit / 19 파일**(정본 보고서의 "109곳/18파일" 은 cycle271 테스트
추가 전 값).

### 8.1 인자 추가만으로는 **깨지지 않는** 것들 (다행)

기존 단언은 전부 `c.args[0..2]`(ticker/trade_type/status) 와 `c.kwargs["price"]` /
`kwargs.get("strategy")` 만 읽는다 — **keyword-only 인자를 뒤에 더해도 무영향**.

| 파일 | hit | 성격 |
|---|---|---|
| `tests/unit/engine/test_cycle161_buy_fill_price_consistency.py` | 29 | `await_args_list` 에서 `args[2]==COMPLETED` 필터 후 `kwargs["price"]`(`:154-162`, `:294-301`, `:339`) — 안전. `:272-274` 에서 `_schedule_cancel` 을 monkeypatch 로 무력화하므로 (가) 변경과도 무충돌 |
| `tests/unit/engine/test_cycle147_sell_fill_strategy_fallback.py` | 17 | `kwargs`/`args[3]` 로 strategy 확인(`:170-175`, `:227-231`, …) — 안전 |
| `tests/unit/engine/test_cycle163_buy_fill_db_error_isolation.py` | 15 | 예외 격리(`AsyncMock(side_effect=...)`) — 안전. ⚠️ AST 자매 `tests/unit/ast/test_cycle163_ast_persistence.py:68` 이 `"step=update_trade_status"` 문자열 존속을 요구 ⇒ `:1283` 로그 문구 **보존 의무** |
| `tests/unit/engine/test_cycle185_cluster1_reset.py` | 11 | `AsyncMock` fixture — 안전 |
| `tests/unit/db/test_cycleM2a_trade_history_pg.py` | 6 | `:110-113` 이 `"PENDING" in sql or "PENDING" in str(args)` — 리스트 `['PENDING','PARTIAL']` 도 `str()` 에 `PENDING` 을 포함하므로 **여전히 통과**. 다만 `:89` 주석 "4-eq 필터 보존" 이 낡는다 ⇒ 주석 갱신 권고 |
| `tests/unit/engine/test_order_engine_unsubscribe_on_sell.py` · `test_cycle236_sell_qty_exceeded.py` · `test_cycle235_fill_qty_overrun.py` · `test_p1b_buy_fill_duplicate_race.py` | 5/2/1/1 | 전부 `AsyncMock(return_value=1)` — 안전 (`test_p1b:212` 는 `_schedule_cancel` 자체를 no-op 으로 패치) |
| `tests/integration/test_cycleM2a_hotpath_roundtrip.py:193-212` | 3 | **실 PG 왕복.** `order_no` 미전달 → 기본 None → 현행 SQL ⇒ 그대로 통과 |
| `tests/unit/db/test_cycle235_forced_update_partial.py` | 2 | `_update_trade_status_by_order_no` 전용 — 무접촉 |
| `tests/unit/db/test_cycleM2a_safety_diff0.py` | 1 | 8영역 git-status 가드는 **`@pytest.mark.skip` 은퇴됨**(`:60`) ⇒ 영향 없음 |

### 8.2 **반드시 고쳐야** 하는 것 (2곳 + 1)

| 파일·줄 | 왜 깨지나 | 해야 할 일 |
|---|---|---|
| `tests/integration/conftest.py:159` | `async def fake_update_trade_status(ticker, trade_type, status, strategy=None, price=None, profit_loss=None)` — 명시 시그니처. 프로덕션이 `order_no=`/`match_partial=` 을 넘기면 **TypeError** | 시그니처에 `*, order_no=None, match_partial=False` 추가 + `calls` 딕트에 기록(그래야 F-1/F-2 를 통합 레벨에서 검증할 수 있다) |
| `tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py:251` | 같은 이유(명시 시그니처) | 동일 |
| `tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py:102-119` `FakeDb.update_status` | 실 WHERE 의 **거울**이라고 docstring(`:103-107`)이 선언한다 — "PENDING 단독" 을 그대로 두면 **초록인 채로 낡은 계약을 검증**하게 된다 | `order_no` 매칭 + `match_partial` 분기를 거울에 반영. `:640-643` 의 docstring("⚠️ 다만 그 행은 PENDING 으로 남는다")은 **부분체결 race 케이스**라 C235-V2-b 이후에도 유효(그 행은 아직 INSERT 전) — 다만 사유 문장에 "PENDING 단독 필터 때문" 이 섞여 있으면 정정 |

### 8.3 (가) 로 새로 필요한 Red 테스트

**현재 `_pending_cancel_tasks` 를 전량 체결과 엮어 보는 테스트는 0건이다**(전수 grep: 상태 초기화
fixture 6곳 + `test_reset_daily_state.py:105-121` 의 정산 스윕 + cycle271 의 정리 루프 `:296-298` 뿐).
즉 (가) 는 순수 추가이며 회귀 표면이 매우 얇다.

필요 Red:
- `G-273-A1` 부분체결 → 같은 order_no 전량체결 → `_pending_cancel_tasks` 가 **비어 있다** + `cancel_order` **호출 0**
- `G-273-A2` 부분체결(주문 A) → **다른 order_no** 전량체결(주문 B, 같은 ticker) → A 타이머 **생존**(§1.4 회귀 가드)
- `G-273-A3` 매수 타이머 존재 상태에서 **매도** 전량체결 → 매수 타이머 생존(같은 dict 공유 가드)
- `G-273-A4` 취소된 task 가 `CancelledError` 를 밖으로 흘리지 않는다(`:1517-1518` 계약)
- `G-273-B1` 행이 PARTIAL 인 상태의 전량체결 → `affected=1`, **보정 INSERT 0회**,
  `[buy_fill_correction_unique_violation]` **미발화**, `_completed_orders` **비어 있음**
- `G-273-B2` 🔴 `match_partial` 미전달(C5/C6) → SQL 이 `status = $n` (단일) 임을 확인 = §3.3 봉인
- `G-273-C1` `affected>1` → `[trade_status_multi_update]` WARNING (caplog WARNING+prefix)
- `G-273-D1` `order_no` 전달 시 SQL 에 `AND order_no = $` 포함 / 미전달 시 **문자열 byte 동일**
- `G-273-D2` 161580 재현: 같은 ticker·strategy 의 PENDING 2행(다른 order_no) → 한쪽 체결 →
  **그 한 행만** COMPLETED (실 PG 왕복 = `tests/integration/` 권장)
- AST `G-273-AST1` `match_partial=True` 리터럴이 소스 전체에 **정확히 2회**, 둘 다 `COMPLETED` 호출 안
- AST `G-273-AST2` 전량 체결 분기 2곳에 `_pending_cancel_tasks` 참조가 **존재**(가드의 역방향 — 되살림 차단)

---

## 9. 최소 diff 계획 (파일·함수·줄)

> 순서는 사용자 결정 (가) → (다) 이지만, **(가)-b 와 (다)-F-1 이 같은 함수**(`update_trade_status`)를
> 건드리므로 **한 커밋**으로 묶는 것이 diff·리뷰 비용 모두 작다. (나) F-3 kojiro 는 별건(자문 선행).

### 9.1 `src/db/trade_history.py` (8영역 **아님**)

| # | 위치 | 변경 | 성격 |
|---|---|---|---|
| T1 | `:88-95` 시그니처 | `*, order_no: str \| None = None, match_partial: bool = False` 추가 | 기본값이 현행 보존 |
| T2 | `:96` docstring | "최신 PENDING" → 실제 SQL 서술로 정정 + cycle273 근거 주석 | 문서 |
| T3 | `:107-117` | `match_partial` → `status = ANY($n::text[])`, `order_no` → `AND order_no = $n` | 조건부, 기본은 byte 동일 |
| T4 | `:119` 뒤 | `if affected > 1:` → `[trade_status_multi_update]` WARNING (F-3) | 관측 |

**+약 18행. 8영역 diff 0.**

### 9.2 `src/engine/order_engine.py` (🔴 **8영역 — 승인됨(D2)**)

| # | 위치 | 변경 |
|---|---|---|
| O1 | `:79` 근처 | `self._pending_cancel_order_no: dict[str, str] = {}` |
| O2 | `:1526` 직전 / `:1563` 직전 | 위 dict 에 `ticker → order_no` 기록 |
| O3 | `:1521-1524` / `:1558-1561` `finally` | 본인 pop 시 새 dict 도 pop |
| O4 | `:1277-1280` (C1) | `order_no=order_no, match_partial=True` |
| O5 | `:1449-1452` (C3) | `order_no=order_no, match_partial=True` |
| O6 | `:1364-1367` (C2) / `:1501` (C4) | `order_no=order_no` **만** (match_partial 금지) |
| O7 | `:1515` (C5) / `:1541` (C6) | `order_no=order_no` **만** (🔴 match_partial 절대 금지 — §3.3) |
| O8 | `:1360` 뒤(매수 전량) / `:1495` 뒤(매도 전량) | §3.1 의 order_no-일치 타이머 해제 5행 |

**+약 22행.** `execute_buy`/`execute_sell`/`handle_execution_notice`/`risk` 경로 무접촉.
`_apply_budget_limit` 계열(A-PURE/A-ATOMIC) 무관.

### 9.3 `src/engine/scheduler.py` (라인 상한 대상 — 별도 판단)

| # | 위치 | 변경 |
|---|---|---|
| S1 | `:3737-3739` | `_pending_cancel_order_no.clear()` 동반 (1행) → **3,899L**, 상한 여유 0 |
| S2 | `:3516-3520` | 죽은 import `update_trade_status` 제거 (−1행) → S1 상쇄 가능 |
| S3 | F-7 | `:3572-3601` 을 leaf 로 위임(−27행 내외) |

⚠️ S1 단독이면 상한에 **딱 붙는다**(3,899/3,900). S2 를 함께 하거나 S3 를 같은 사이클에 하는 것을 권한다.

### 9.4 커밋·핀 절차 (8영역)

1. **작업 시작 전** `_content_sha("src/engine/order_engine.py")` 를 **4곳 전부**에 등록:
   - `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`
   - `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA`
   - `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA`
   - `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA`
   (`test_g3_9a/9b` = "핀은 항상 4곳". 선례 = `4d88aa6`)
2. 커밋 뒤 **네 dict 를 다시 비우는 후속 커밋** — cycle271 이 `d4cbb58` → `4d88aa6` 로 한 그대로.
3. 배포 모드 = **full**(`src/**` 변경). 창 = 15:30~19:55 / 20:20~익일 07:45 / 주말·공휴일.
   **20:00~20:15 금지.** 보유 중 장중 push 금지(D6).

### 9.5 검증 게이트

- 신규 Red 10건 + AST 2건 GREEN
- `pytest tests/unit/db tests/unit/engine tests/unit/ast` 회귀 0
- `pytest tests/integration/test_buy_flow.py test_sell_flow.py test_chegyeol_race.py test_reset_daily_state.py test_cycleM2a_hotpath_roundtrip.py`
- 백엔드 전체 PASS (직전 기준선 7,548)
- 뮤테이션: `match_partial` 기본값 True 로 뒤집기 · `order_no` 조건 삭제 · `affected > 1` → `>= 1` ·
  타이머 해제의 order_no 비교 삭제 — 전부 KILLED 여야 한다

### 9.6 D+1 실측 서명 (배포 다음 영업일)

| 서명 | 기대 |
|---|---|
| `부분 체결 잔여 취소 실패` / APBK0927 | **0건** (부분체결이 있었던 날 한정 — 없으면 무증거) |
| `[buy_fill_correction_unique_violation]` / `[sell_fill_...]` | 0건 |
| `체결통보 선행 race — COMPLETED 직접 INSERT` | **기준선 대비 증가 0** ← §6.2 표기 불일치 조기경보 |
| `[trade_status_multi_update]` | 0건 |
| `[trade_status_update_by_order_no]` | 감소(자기치유 호출이 줄어든다) |
| `[buy_fill_correction_forced_update_zero]` | 0건 |
| ⚠️ 의미 반전 없음 | 기존 마커의 뜻이 바뀌지 않는다 — **배포 전후 grep 합산 가능** |

---

## 10. 이 문서가 닫지 못한 것

1. **REST `ODNO` ↔ 체결통보 `fields[2]` 표기 동일성** — 실측 1건(004990 `0000305100`)뿐이다.
   과거 `system_logs` 에서 `주문번호:` 와 체결통보 order_no 를 교차 대조하면 표본을 늘릴 수 있으나
   이 작업(읽기 전용·DB 무접촉)에서는 하지 않았다. §6.2 가 이 미지에 대한 방어다.
2. **`_completed_orders` 실제 잔존 크기** — 프로세스 in-memory 라 로그로 못 잰다. `scheduler.py:1301`
   이 노출하는 것은 `_pending_cancel_tasks` 뿐이고 `_completed_orders` 는 어떤 라우트에도 없다.
3. **부분체결↔전량체결 30초 내 페어의 실제 빈도** — 정본 §정정 V-8 이 남긴 숙제 그대로.
   09-10 하루 `매수 부분 체결` 1건이 유일한 표본이다.
4. **F-7 leaf 위임의 정확한 행 수** — `scheduler.py` 를 실제로 편집하지 않았으므로 −27행은 추정이다.
5. **C5/C6 오매칭이 과거에 실제로 일어났는지** — `update_trade_status` 의 `affected` 가
   `logger.debug`(`:121-122`)라 `system_logs` 에 흔적이 0 이다(D-3). F-3 는 §5.4 대로 미래분만 센다.

---

*근거: HEAD `a10191b` 의 `src/engine/order_engine.py`(1,591L) · `src/db/trade_history.py`(718L) ·
`src/engine/scheduler.py`(3,898L) · `src/realtime/handler.py` · `src/api/order.py` ·
`supabase/migrations/029_*.sql` · `tests/**` 전수 grep · 정본 조사
`_workspace/analysis/2026-09-10_{004990_partial_fill_cancel_race,161580_root_cause}.md` ·
보고서 `_workspace/reports/2026-09-10_thursday_autonomous_work.md` §D2 ·
워크리스트 `_workspace/00_URGENT_WORKLIST.md`(200행 F-271-1, 1292행 C235-V2) · 커밋 `d4cbb58`/`4d88aa6`.*
