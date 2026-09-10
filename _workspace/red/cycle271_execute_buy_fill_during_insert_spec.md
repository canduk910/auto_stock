# cycle271 Red 명세 — 체결통보가 `execute_buy` 의 `insert_trade` await 도중 착지하는 race

- 작성: 2026-09-10, tdd-engineer (Red 단계)
- 범위: `src/engine/order_engine.py` (**8영역**) 최소 변경. 이 문서 작성 시점 `src/` diff **0**.
- 승인 근거: `_workspace/00_URGENT_WORKLIST.md` "🔵 결정 대기" **2번** 원문 (172~175행) —

  > 2. **09:05 `[swing_poll] execute_buy 실패` 오탐 시정** — 사용자가 "고치자" 승인했으나
  >    `src/engine/order_engine.py` 가 8영역이라 **아직 착수 안 함**. 원인 = 체결통보가
  >    `insert_trade` await 도중 착지하는 race(기존 가드는 "검사 전 도달" 만 덮는다). 매수·DB 는
  >    정상(UNIQUE 인덱스가 이미 방어), 실손실은 `cached_buyable_at` 캐시 미무효화 1건뿐 → 위험 LOW.

- 산출 테스트: `tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py`

---

## 1. 결함 재확인 — 코드 줄 번호

모든 줄 번호는 2026-09-10 워킹트리 기준
(`shasum -a 256 src/engine/order_engine.py` =
`36a0af370a966d0c979679d1128bb49c6de7d33ba8d3d403d7953bf43e034377`, 1,550행).

### 1.1 `execute_buy` 시장가 경로

| 줄 | 내용 |
|---|---|
| `order_engine.py:371` | `result = await place_order(**place_kwargs)` |
| `:377~385` | 주문번호 매핑 **동기** 등록 (`_order_qty`/`_order_strategy`/`_order_ticker`/`_pending_buy_orders`) |
| `:388` | `already_completed = result.order_no in self._completed_orders` ← **"검사 전 도달" race 만 덮는다** |
| `:389~392` | 이미 있으면 `discard` + WARNING, PENDING INSERT 생략 |
| `:396~406` | `TradeRecord(status=PENDING)` 구성 |
| `:407` | `await insert_trade(record)` ← **여기서 이벤트 루프에 제어를 넘긴다** |
| `:409~410` | `logger.info("매수 주문 접수: …")` |
| `:412` | `state.cached_buyable_at = 0.0` |
| `:489~492` | `except Exception:` → `pending_buys.discard` + `pending_buy_amounts.pop` + **`raise`** |

### 1.2 지정가 5호가 폴백 경로 (C4)

| 줄 | 내용 |
|---|---|
| `:427` | `try:` (폴백 진입) |
| `:431~438` | 폴백 `place_order` |
| `:442~450` | 매핑 동기 등록 (시장가와 동일 규약) |
| `:452~458` | 선행 race 가드 (`_completed_orders` 검사 + discard) |
| `:461~471` | PENDING `TradeRecord` + `await insert_trade(record)` |
| `:477` | `state.cached_buyable_at = 0.0` · `:478` `return` |
| `:479~487` | `except KisApiError as e2:` — **`UniqueViolationError` 는 여기 안 걸린다** |

⚠️ **폴백 경로의 예외 전파는 시장가 경로와 다르다.** 폴백 INSERT(`:471`)는 바깥
`except KisApiError as e:`(`:414`) **핸들러 본문 안**이므로, 거기서 난 예외는 형제 핸들러인
`except Exception:`(`:489`)이 잡지 못하고 **호출자로 직행**한다. 따라서 폴백 경로에서는
`pending_buys.discard`(`:490`)조차 실행되지 않는다. Green 은 두 경로를 각각 손봐야 한다.

### 1.3 `_handle_buy_fill` 전량 체결 분기

| 줄 | 내용 |
|---|---|
| `:1109` | `async def _handle_buy_fill(...)` |
| `:1216~1219` | `pending_buys.discard` + `pending_buy_amounts.pop` + `_pending_buy_orders.pop` |
| `:1240~1243` | `affected = await update_trade_status(ticker, BUY, COMPLETED, strategy=…, price=…)` |
| `:1249~1250` | `affected == 0` → **`self._completed_orders.add(order_no)`** |
| `:1253~1266` | 보정 `insert_trade(status=COMPLETED)` |
| `:1268~1289` | `except Exception:` → `[buy_fill_correction_unique_violation]` WARNING + `_update_trade_status_by_order_no` 강제 UPDATE |
| `:1313~1316` | 매핑 pop + `_completed_buy_orders.add` |
| `:1318` | `state.cached_buyable_at = 0.0` |
| `:1320~1328` | 부분 체결 분기 — `update_trade_status(PARTIAL)` + `_schedule_cancel` (보정 INSERT **없음**) |

### 1.4 결함이 성립하는 전제 3가지 (전부 코드로 확인)

1. `src/db/trade_history.py:65~85` `insert_trade` 는 `pg.execute` 를 **감싸지 않는다** →
   `UniqueViolationError` 가 그대로 전파된다.
2. migration 029 부분 UNIQUE 인덱스 `uq_trade_history_ticker_order_no_type ON (ticker,
   order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''` 가 두 번째 INSERT 를 거부한다.
3. `await insert_trade` 는 asyncio 단일 루프에서 **제어를 넘긴다** → WS 체결통보 task 가 그 사이 완주할 수 있다.

### 1.5 발현 시퀀스

```
execute_buy                                   _handle_buy_fill (WS task)
──────────────────────────────────────────────────────────────────────────
:371 place_order 응답
:377~385 매핑 동기 등록
:388 _completed_orders 검사 → False
:407 await insert_trade(PENDING) ──── yield ──▶ :1216 pending 정리
                                               :1240 update_trade_status(COMPLETED) → affected=0
                                                     (PENDING 행이 아직 없다)
                                               :1250 _completed_orders.add(order_no)
                                               :1253 insert_trade(COMPLETED) → 성공 (첫 행)
                                               :1318 cached_buyable_at = 0.0
        ◀──────────────────────────────────── 완주
:407 INSERT 도달 → UniqueViolationError
:489 except Exception → discard/pop → raise
                                               ▲ 호출자가 "실패"로 기록
```

---

## 2. 실손실 재평가 — 워크리스트 서술과 다른 점 2가지

워크리스트 2번은 "실손실은 `cached_buyable_at` 캐시 미무효화 1건뿐 → 위험 LOW" 라고 적었다.
코드를 읽은 결과 **둘 다 정정이 필요하다**. (아래는 코드 판독 결론이며 운영 실측이 아니다.)

### 2.1 `cached_buyable_at` 는 이미 무효화된다 — 실손실이 아니다

`_handle_buy_fill` 전량 분기 `:1318` 이 같은 `state` 객체에 `cached_buyable_at = 0.0` 을
이미 수행한다. `execute_buy:412` 를 못 타도 결과는 같다. 테스트 `test_c2_2` 가 이를 실증한다
(GREEN). → **워크리스트가 지목한 실손실은 실재하지 않는다.**

### 2.2 대신 더 무거운 손실 2가지가 있다

**(가) 매수 직후 HIGH WS 구독 누락 — 손절 사각 (`scheduler.py:2688~2709`)**

```python
buy_succeeded = False
try:
    await self.order_engine.execute_buy(t, current_price, strategy)
    buy_succeeded = (t in strategy.state.pending_buys
                     or t in strategy.state.positions)
    if buy_succeeded:
        total_bought += 1
except Exception:
    logger.exception("[swing_poll] execute_buy 실패: %s", t)
if buy_succeeded:
    await _kis_ws.subscribe(_TICK_TR_ID, t, bypass_limit=True)   # ← 실행되지 않는다
```

예외가 나면 `buy_succeeded` 대입 자체가 일어나지 않아 `False` 로 남는다. 포지션은 이미
등록됐는데 **"안전 불변식: 보유 종목 손절/트레일링 평가 필수 → 매수 직후 HIGH 구독"** 이
통째로 건너뛰어진다. 회복은 `_scan_loop`(5분) 또는 K stale watcher(120초 주기)에 의존 —
즉 **방금 산 포지션이 최대 5분간 WS blind** 다. `total_bought` 카운터도 어긋난다.

**(나) `risk.on_tick` 경로에서는 WebSocket 재연결까지 간다 (`risk.py:651`)**

`risk.on_tick` 은 `execute_buy` 를 try 없이 호출한다(`risk.py:651~653`). 예외는
`handler.py:629~639` 로 올라가고 거기서

```python
except Exception:
    logger.exception("[callback_exception] handler=_on_tick ticker=%s", ticker)
    raise  # 재연결 trigger 영속 (사이클 88 G-REJECT-1 영속)
```

→ **WS 재연결 trigger**. 시장가 즉시체결이 흔한 momentum/VB/LTV 가 이 경로를 탄다.
구조적으로 도달 가능하다는 것이 코드 사실이며, 운영 로그로 실제 발생을 확인하지는 못했다(§5.2).

> **결론**: 위험 등급을 LOW 로 유지할 근거가 약하다. 등급 재판정은 team-leader 몫으로 남긴다.

---

## 3. 시정 계약 C1~C7 (Red 가 잠근 것)

| ID | 계약 | 잠근 테스트 | 현재 |
|---|---|---|---|
| C1 | 체결통보가 `insert_trade` await 도중 착지해도 `execute_buy` 는 예외를 내지 않는다 | `test_c1_1` (시장가) | **RED** |
| C1 | 〃 지정가 폴백 경로 | `test_c1_2` | **RED** |
| C2 | `trade_history` 그 주문 정확히 1행 COMPLETED | `test_c2_1` | GREEN (UNIQUE 인덱스가 방어) |
| C2 | 포지션 수량 정확 + pending 정리 + `cached_buyable_at == 0.0` | `test_c2_2` | GREEN (§2.1) |
| C2 | `_completed_orders` 에 order_no 잔류 없음 | `test_c2_3` | **RED** |
| C3 | 기존 "체결통보 선행" race(사이클 30) 보존 — 시장가 | `test_c3_1` | GREEN |
| C3 | 〃 폴백 | `test_c3_2` | GREEN |
| C4 | 두 경로 동일 계약 | C1-2 · C3-2 · C5-2 | — |
| C5 | `[buy_fill_during_insert]` INFO 1행 (ticker·order_no 포함) | `test_c5_1` / `test_c5_2` | **RED** |
| C5 | 평시 매수에는 안 찍힌다 | `test_c5_3` | GREEN |
| C6 | A-ATOMIC 등 기존 AST 가드 보존 | `test_c6_1` | GREEN |
| C7 | 다른 원인의 UniqueViolation 은 삼키지 않는다 | `test_c7_1` | GREEN (시정 후에도 유지) |
| B | 부분 체결만 착지한 경우는 예외가 나지 않는다 (계약 경계) | `test_b_1` | GREEN |

### C2-3 상세 — `_completed_orders` 누수

`_handle_buy_fill:1250` 이 `add` 하지만 `execute_buy:388` 검사는 이미 지나갔으므로
`:390` 의 `discard` 가 실행되지 않아 set 에 영구 잔류한다. 같은 order_no 가 재활용되면
다음 주문의 PENDING INSERT 가 조용히 생략된다. Green 은 복구 시 이 order_no 를 **소비**해야 한다.

### C5 상세 — 마커 규약

- **접두 토큰 `[buy_fill_during_insert]` 는 이 명세가 고정한다.** 뒤따르는 key=value 서식은 Green 이 정한다.
- 레벨 INFO, 최소 `ticker=` 와 `order_no=` 를 포함한다.
- **관측이 행위를 바꾸면 안 된다** — 마커 emit 은 예외를 흡수하되, 흡수해도 마커는 남긴다.
- **`write_log` 직접 호출 금지** (`_DbLogHandler` 위임 관례, cycle72 G-6). `logger.info` 만.
- 캡은 두지 않는다(이 경로는 본래 희소하다). 운영에서 폭주가 관측되면 `KstDailyEmitCap` 도입은 후속.

### C6 상세 — 8영역 순수성

A-ATOMIC 가드(`tests/unit/ast/test_budget_limit_ast.py::test_execute_buy_sizing_to_pending_is_await_free`)는
`calc_buy_quantity`(`:272`) ~ `pending_buys.add`(`:314`) 구간의 `await` 0건을 강제한다.
**시정 지점(`:407` / `:471` 전후)은 그 구간 밖**이므로 계약이 유지된다.
`test_c6_1` 이 그 가드를 직접 호출해 이 파일 단독 실행으로도 깨짐을 감지한다.

---

## 4. Green 후보 2안과 각각의 위험

### (a) `insert_trade` 를 `try/except UniqueViolationError` 로 감싸고 성공 경로로 합류

- 장점: 최소 변경.
- **위험: 다른 원인의 UniqueViolation 을 삼킨다.** 예를 들어 같은 `(ticker, order_no, BUY)` 의
  CANCELLED 행이 이미 있는 경우(수동 정정 후 재주문 등)를 "체결통보가 먼저 넣었다"로 오독하고
  **주문이 기록되지 않은 채 성공으로 보고**한다. `test_c7_1` 이 이 형태를 거부한다.
- 채택하려면 **반드시 order_no 로 한정**해야 한다 — 즉 (b)와 사실상 같아진다.

### (b) INSERT 실패 후 `_completed_orders` 재검사 ← **권장**

```
except UniqueViolationError:
    if result.order_no in self._completed_orders:
        self._completed_orders.discard(result.order_no)   # C2-3 누수 해소
        logger.info("[buy_fill_during_insert] ticker=%s order_no=%s ...", ...)
        # 성공 경로로 합류 (아래 logger.info / cached_buyable_at = 0.0)
    else:
        raise
```

- `_completed_orders` 에 그 order_no 가 있다는 것이 "체결통보가 먼저 INSERT 했다"는 **유일한 증거**다.
- `discard` 가 C2-3(누수)까지 동시에 해결하고, `:389~392` 의 기존 소비 규약과 대칭이 된다.
- **두 경로 모두에 필요하다** — 시장가(`:407`)와 폴백(`:471`). §1.2 때문에 폴백은 별도로 감싸야 한다.
- 예외 타입은 `asyncpg.exceptions.UniqueViolationError`. `order_engine.py` 가 asyncpg 를 직접
  import 하는 것이 부담이면 `src/db/trade_history.py` 에 좁은 헬퍼를 두는 편이 낫다 —
  다만 **그 파일은 8영역이 아니므로 sha 핀 대상이 아니다**(핀은 `order_engine.py` 만).

> Green 은 위 형태를 강제받지 않는다. C1~C7 을 모두 만족하는 다른 형태여도 된다.

---

## 5. 증거의 한계 — 반드시 읽을 것

### 5.1 인용된 004990 로그는 이 결함의 사례가 **아니다**

의뢰문이 첨부한 09-10 09:05:01 004990 사례를 원문(`_workspace/analysis/2026-09-10_004990_partial_fill_cancel_race.md` §0)으로
대조한 결과, 그 로그에는 **`매수 주문 접수`(`order_engine.py:409`)가 정상 기록**돼 있다.
`:409` 는 `await insert_trade`(`:407`) **뒤**에 있으므로 그 INSERT 는 성공했고,
`execute_buy` 는 예외를 내지 않았다. `[swing_poll] execute_buy 실패` 도 없다.
→ **004990 은 cycle271 표적 결함의 인스턴스가 아니다.** 같은 race 창을 공유하지만
승자가 반대인, 이미 자기치유되는 반대 방향 사례다.

### 5.2 표적 결함의 운영 실측 로그는 확보하지 못했다

이 Red 는 (i) 워크리스트 2번의 사용자 승인 기록과 (ii) 위 §1.4 세 전제의 코드 사실에 근거한다.
`[swing_poll] execute_buy 실패` 실제 발생 로그는 이번 작업에서 확인하지 못했다.
**Green 착수 전 EC2 로그로 1건이라도 확증하는 것을 권장**한다:

```bash
docker compose -f docker-compose.prod.yml logs backend --since 2026-09-01T00:00:00 \
  | grep -A5 "\[swing_poll\] execute_buy 실패"
```

`UniqueViolationError` 가 traceback 에 보이면 표적 결함 확증, 다른 예외면 귀인이 달라진다.

### 5.3 004990 의 `affected=0` 원인에 대한 교차 확인 (별건, 참고)

기존 분석 문서 §1-B 는 `affected=0` 을 "PENDING INSERT 가 아직 커밋되지 않아서"로 설명한다.
그런데 같은 로그의 순서(`매수 체결 → 포지션 등록 3주` → `매수 주문 접수` → `매수 부분 체결 3/5`)와
`update_trade_status` 의 WHERE 절(`src/db/trade_history.py:107~117`, **`status = 'PENDING'` 단독**)을
함께 보면 다른 해석이 가능하다:

1. 부분 체결이 `update_trade_status(…, PARTIAL, …)` 로 행을 **PARTIAL 로 바꾸는 데 성공**했고
2. 뒤이은 전량 체결의 `update_trade_status(…, COMPLETED, …)` 는 `WHERE status = 'PENDING'` 이라
   **PARTIAL 행을 못 찾아** `affected=0` 이 됐다

행이 존재했다는 것은 보정 INSERT 가 UNIQUE 에 걸린 사실로 증명되고, 그 행의 상태가 PENDING 이
아니었다는 것은 COMPLETED UPDATE 가 0건이었다는 사실로 증명된다 → 그 행은 PARTIAL 이었다.
이 해석이 맞다면 004990 의 원인은 워크리스트 N1 후속 후보 **C235-V2 의 "1차 `update_trade_status`
의 PARTIAL 포괄"** 이며, 기존 분석이 "이론상 관여 가능하나 실제 피해 없음"으로 낮춘 항목이 곧
그 사례의 직접 원인이 된다. **이 사이클 범위 밖**이며 team-leader 판단 사항으로 넘긴다.
(cycle271 테스트는 이 축을 건드리지 않는다 — `test_b_1` 이 경계만 문서화한다.)

---

## 6. 열린 후속 (이번 범위 밖 — 등재만)

- **F-1** 부분 체결만 insert 도중 착지하면 예외는 없지만 그 행이 **PENDING 으로 남는다**
  (`_handle_buy_fill:1323` 의 `update_trade_status(PARTIAL)` 이 affected=0 을 확인하지 않는다).
  `test_b_1` 이 "행 1개" 까지만 잠갔다. = C235-V2 와 같은 축.
- **F-2** C235-V2 "전량 체결 분기의 잔여취소 타이머 해제" — 004990 ERROR 2건의 실제 원인.
  기존 분석 문서가 정본.
- **F-3** `_completed_orders` 일일 리셋(C235-R3) 확인 — C2-3 누수와 인접하나 별건.

---

## 7. 8영역 sha 핀 절차 (Green·커밋 담당이 그대로 따를 것)

`src/engine/order_engine.py` 는 8영역이다. **자매 가드 4곳**은 2026-09-10 현재 **전부 비어 있다**(확인 완료):

| 파일 | 심볼 | 현재 |
|---|---|---|
| `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` | `_APPROVED_CONTENT_SHA` (`:449`) | 빈 dict |
| `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` | `_PREEXISTING_CONTENT_SHA` (`:437`) | 빈 dict |
| `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` | `_PREEXISTING_CONTENT_SHA` (`:338`) | 빈 dict |
| `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` | `_ALLOWED_CONTENT_SHA` (`:1140`) | 빈 dict |

절차:

1. `order_engine.py` 를 **최종 확정한 뒤**(더 이상 1 byte 도 안 고치는 단계에서) 산출:
   ```bash
   shasum -a 256 src/engine/order_engine.py
   ```
2. 위 4곳에 **동시에·같은 값**으로 등록. 키는 `"src/engine/order_engine.py"`,
   주석 한 줄: `# cycle271 승인 항목 — 커밋 후 비울 것`.
3. **1 byte 라도 더 고치면 4핀 전부 무효** → 1번부터 재산출.
4. 커밋 직후 **별도 커밋**으로 4곳을 다시 비운다 (선례 `29b67ff` · `0c878ec`).
   재발 방지 가드 `tests/unit/ast/test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a/9b`
   가 "핀은 항상 4곳" 을 강제하므로 한 곳만 등록하거나 값이 갈리면 그 자체가 실패한다.
5. **사이클 한정 가드를 만들지 않는다** — bare `git diff HEAD` 가드는 커밋 후 공허 통과한다
   (cycle240 A11b · cycle252 G-252-5b). 영구 가드만 둔다.

참고: 워킹트리에는 병행 사이클(cycle270 토큰)의 미커밋 테스트가 있다.
`src/` diff 는 0 이므로 8영역 가드는 현재 아무것도 감지하지 않는다.

---

## 8. 배포·롤백

- **배포 모드**: `src/**` 변경이므로 `tools/deploy/compose_up_changed.sh` 판정 **full**(백엔드 재생성).
- **창**: 보유 포지션이 있으면 **KRX 메인 09:00~15:30 push 금지**(cycle232 D6).
  15:30~19:55 · 20:20~익일 07:45 · 주말. **20:00~20:15 금지**(자문·정산).
- **롤백**: 코드 변경이므로 되돌리기는 revert 커밋 1개. 설정 다이얼 없음.
  시정은 예외 경로에만 닿으므로 정상 매수 흐름은 byte 동일이어야 한다 —
  Green 은 `test_c5_3`(평시 마커 0행) 과 기존 `test_order_engine_buy.py` 로 이를 실증한다.
- **의미 전환 없음**: `[buy_fill_during_insert]` 는 신규 마커라 과거 로그와 합산 문제가 없다.
  기존 `[buy_fill_correction_unique_violation]` 의 의미는 바뀌지 않는다.

---

## 9. 실행 결과 (2026-09-10)

### 9.1 신규 테스트 — RED 5 / GREEN 8

```
$ python -m pytest tests/unit/engine/test_cycle271_execute_buy_fill_during_insert.py -q
5 failed, 8 passed in 0.24s

FAILED ...::test_c1_1_market_path_when_full_fill_lands_during_insert_then_no_exception
FAILED ...::test_c1_2_fallback_path_when_full_fill_lands_during_insert_then_no_exception
FAILED ...::test_c2_3_when_full_fill_during_insert_then_completed_orders_is_not_leaked
FAILED ...::test_c5_1_when_full_fill_during_insert_then_marker_emitted_once
FAILED ...::test_c5_2_fallback_when_full_fill_during_insert_then_marker_emitted_once
```

C1-1 · C1-2 의 실패 원인이 정확히 표적 결함임을 확인:

```
E  asyncpg.exceptions.UniqueViolationError: duplicate key value violates
   unique constraint "uq_trade_history_ticker_order_no_type"
```

### 9.2 기존 회귀 — 65 PASS, 무수정

Green 이후에도 **한 줄도 고치지 않고** GREEN 이어야 하는 정본 목록:

```
$ python -m pytest \
    tests/integration/test_chegyeol_race.py \
    tests/unit/engine/test_p1b_buy_fill_duplicate_race.py \
    tests/unit/engine/test_order_engine_sell_fallback.py \
    tests/unit/engine/test_order_engine_buy.py \
    tests/unit/ast/test_budget_limit_ast.py \
    tests/unit/engine/test_cycle161_buy_fill_price_consistency.py \
    tests/unit/engine/test_cycle163_buy_fill_db_error_isolation.py \
    tests/unit/engine/test_cycle235_fill_qty_overrun.py -q
65 passed in 3.27s
```

| 파일 | 지키는 계약 |
|---|---|
| `tests/integration/test_chegyeol_race.py` | 사이클 30 "체결통보 선행" race 정본 (C3) |
| `tests/unit/engine/test_p1b_buy_fill_duplicate_race.py` | P1-B `_completed_buy_orders` 멱등 가드 |
| `tests/unit/engine/test_order_engine_buy.py` | 평시 매수 흐름 byte 동일 |
| `tests/unit/engine/test_order_engine_sell_fallback.py` | 지정가 폴백 규약 |
| `tests/unit/ast/test_budget_limit_ast.py` | A-ATOMIC / A-PURE / A-GATE (C6) |
| `tests/unit/engine/test_cycle161_buy_fill_price_consistency.py` | 체결가 정합(`price=price` 명시 의무) |
| `tests/unit/engine/test_cycle163_buy_fill_db_error_isolation.py` | DB 3영역 try/except 격리 |
| `tests/unit/engine/test_cycle235_fill_qty_overrun.py` | overrun 클램프 |

사이클 30 race 회귀 정본 = `tests/integration/test_chegyeol_race.py`
(`test_buy_chegyeol_race_when_ws_first_then_completed_direct_insert` ·
`test_buy_pending_insert_skipped_when_order_no_in_completed_orders`).
Green 이후에도 **무수정 GREEN** 이어야 한다.

### 9.3 광역 회귀

```
$ python -m pytest tests/unit/engine tests/unit/ast -q
13 failed, 5161 passed, 4 skipped, 155 xfailed, 4 xpassed in 61.39s
```

13 실패 = cycle271 신규 RED **5건** + 병행 cycle270(보조 토큰) Red **8건**
(`test_cycle270_quote_token_revoke_then_issue.py` 6 · `test_cycle269_..._wiring.py::test_g269_4` ·
`test_cycle270_ast_revoke_then_issue.py::test_g270_1`). 후자는 다른 에이전트의 미커밋 Red 이며
이 사이클과 무관하다. `git diff --stat -- src/` = **빈 출력**(src 무변경)으로 확인.
