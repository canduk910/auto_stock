# 롯데지주(004990) 부분체결 잔여취소 ERROR 성격 확정 (2026-09-10)

**결론(선요약)**: 실손실·포지션·DB 손상 **없음**. `[buy_fill_correction_unique_violation]` 은
~~기존에 설계·문서화된 "체결통보 선행 race" 가~~ **[정정 V-1]** **1차 `update_trade_status` 의
status 필터가 `PENDING` 단독**이라 이미 `PARTIAL` 이 된 행을 못 잡아 생긴 것이고(§1-B),
그 뒤 **cycle235 N1-b 의 강제 UPDATE(WHERE `PENDING∪PARTIAL`)** 가 정상적으로 자기 치유했다. `부분 체결 잔여 취소 실패`
ERROR ×2 는 **워크리스트 N1(cycle235) 후속 후보 C235-V2 "전량 체결 분기의 잔여취소 타이머 해제"
미구현**이 오늘 실측으로 재현된 것이다 — **같은 결함**이다. 로그 소음이며 8영역 코드 수정은
이 문서 범위 밖(읽기 전용 지시).

## 0. 실측 로그 원문 (EC2, `docker compose -f docker-compose.prod.yml logs backend --since 2026-09-10T00:00:00`)

```
09:05:01 [INFO ] src.engine.strategies.kojiro — 고지로 매수 신호: 004990 현재가(24800) — 스테이지1(6→1) + EMA정배열 + ATR(856.8)
09:05:01 [INFO ] src.api.order — BUY 주문 완료: 004990 5주 @ 0 (주문번호: 0000305100)
09:05:01 [INFO ] src.engine.order_engine — 매수 체결 → 포지션 등록: 롯데지주(004990) 3주 @ 24800 (전략: kojiro)
09:05:01 [INFO ] src.engine.order_engine — 매수 주문 접수: 롯데지주(004990) 5주 @ 24800 (주문번호: 0000305100, 전략: kojiro)
09:05:01 [INFO ] src.engine.order_engine — 매수 부분 체결: 롯데지주(004990) 3/5주 @ 24800 (전략: kojiro)
09:05:01 [WARNING] src.engine.order_engine — [buy_fill_correction_unique_violation] ticker=004990 order_no=0000305100
    strategy_attempted=kojiro err=UniqueViolationError('duplicate key value violates unique constraint
    "uq_trade_history_ticker_order_no_type"') → strategy 무관 강제 COMPLETED UPDATE
09:05:01 [INFO ] src.db.trade_history — [trade_status_update_by_order_no] order_no=0000305100 trade_type=BUY status=COMPLETED affected=1
09:05:01 [INFO ] src.engine.order_engine — 매수 전량 체결: 롯데지주(004990) 5주 @ 24800 (전략: kojiro)
...
09:05:32 [ERROR] src.api.base — KIS API 에러: rt_cd=7, msg_cd=APBK0927, msg1=정정취소 가능수량이 없습니다.
09:05:32 [ERROR] src.engine.order_engine — 부분 체결 잔여 취소 실패: 004990
Traceback (most recent call last):
  File "/app/src/engine/order_engine.py", line 1473, in _cancel_after_wait
    await cancel_order(order_no, 0, cancel_all=True, exchange=self._strategy_exchange(strategy_id))
  File "/app/src/api/order.py", line 121, in cancel_order
    data = await kis_post(ORDER_RVSECNCL_URL, tr_id, body, hashkey=hashkey)
  File "/app/src/api/base.py", line 473, in kis_post
    return await _request("POST", path, tr_id, body=body, hashkey=hashkey)
  File "/app/src/api/base.py", line 647, in _request
    raise KisApiError(rt_cd, msg_cd, msg1)
src.api.base.KisApiError: KIS API Error [APBK0927]: 정정취소 가능수량이 없습니다.
```

**ERROR "2건"의 정체**: 서로 다른 두 로거가 **같은 한 번의 `cancel_order()` 실패**를 각자 기록한
것이다 — `src.api.base`(base.py:622, "KIS API 에러: …") 1건 + `src.engine.order_engine`
(order_engine.py:1479, "부분 체결 잔여 취소 실패: 004990" + traceback) 1건. `cancel_order` 호출은
09:05:32 에 **단 1회**만 발생했다(~~09:05:01 + `PARTIAL_FILL_WAIT=30`초~~ →
**30초 타이머 + KIS 왕복 지연**, order_engine.py:65).

> **[정정 V-2] 영속 `system_logs` 에서는 3행이다(도커 stdout 2행 ≠ DB 3행).**
> `src/api/base.py:643` 이 `[kis_rejection] path=/uapi/domestic-stock/v1/trading/order-rvsecncl
> tr_id=TTTC0013U msg_cd=APBK0927 …` 를 **`write_log("ERROR", …)` 로 DB 에만** 기록하고 stdout
> 에는 찍지 않는다(당일 stdout `grep -c kis_rejection` = 0). 이 차이는 §3 위험 논거와 **직결**된다 —
> 20:10 일일 리포트(`log_metrics_collector`)는 `SELECT … FROM system_logs`
> (`log_metrics_collector.py:78/105/134`)로 집계하므로 **운영자·AI 자문이 실제로 보는 수는 3**이다.
> **실측** `GET /api/logs?level=ERROR&from_date=2026-09-10&to_date=2026-09-10` → **total=3**
> (09:05:32.279444 `[kis_rejection]` · 09:05:32.353127 `src.api.base` · 09:05:32.368820
> `src.engine.order_engine`), CRITICAL=0, **3행 모두 이 한 건**이다.
> ⇒ 소음 논거는 **약화가 아니라 강화**된다(발화당 3행).

> **[정정 V-3] 30초 산술이 1초 어긋난다.** 09:05:01 + 30초 = **09:05:31** 이고 관측 발화는
> 09:05:32(`system_logs` 밀리초 09:05:32.279444)다. 실제 델타는 **31초**이며,
> 매수 시각의 소수부(`trade_history` 09:05:01.958)와 `cancel_order` KIS 왕복 지연으로 설명된다.
> **30초 타이머라는 인과는 유효**하되 `= 09:05:01 + 30초` 라는 **등식 표기는 부정확**하다.

> **[정정 V-4] §0 머리말의 재현 명령이 창을 오도한다.** EC2 호스트 TZ 는 **UTC** 이고
> (`date` → `UTC`, `/etc/timezone` → `Etc/UTC`) `docker logs --since` 는 호스트 로컬시로
> 해석되므로 `--since 2026-09-10T00:00:00` 은 **KST 09:00:00** 이다 —
> **00:00~09:00 KST(NXT 프리장 08:00~09:00 포함)가 통째로 빠진다.**
> 정정된 재현 명령 = `--since 2026-09-09T15:00:00`(= 09-10 00:00 KST). 그 창으로 다시 세도
> `[ERROR` = 2 · `[CRITICAL` = 0 으로 **결론은 유지**된다(첫 행 07:44:59 KST, 컨테이너 기동
> 09-09 23:45:11 KST). 더 안전한 정본은 `system_logs` KST 필터
> (`/api/logs?from_date=2026-09-10&to_date=2026-09-10`) — docker 로그 보존과 무관하다.

## 1. 왜 오늘 시퀀스가 ERROR 를 만들었는가 (줄 번호 근거)

### 1-A. 부분체결 잔여취소 타이머 — 아무도 해제하지 않았다

- 3/5 부분체결 통보 → `_handle_buy_fill` 의 "부분 체결" 분기(order_engine.py:1320-1328)가
  `update_trade_status(...PARTIAL...)` 뒤 **`_schedule_cancel(ticker, order_no, ordered_qty=5,
  strategy_id)`**(1327행)를 호출한다. `_schedule_cancel`(1465-1485행)은 `asyncio.sleep(PARTIAL_FILL_WAIT)`
  (1472행, `PARTIAL_FILL_WAIT=30`, 65행) 뒤 `cancel_order(order_no, 0, cancel_all=True, …)`(1473행)를
  실행하는 백그라운드 task 를 `self._pending_cancel_tasks[ticker]` 에 등록한다.
- **같은 초 안에** 5/5 전량체결 통보가 도착해 `_handle_buy_fill` 의 "전량 체결" 분기(1221-1319행)로
  들어간다. 이 분기는 `update_trade_status`→positions 저장→`_filled_qty`/`_order_qty`/`_order_strategy`/
  `_order_ticker` pop(~~1313-1316행~~ → **`:1310-1313`**)→`_completed_buy_orders.add`
  (**`:1316`**, 1314-1315 는 주석) **[정정 V-5]** 까지 정리하지만, **`self._pending_cancel_tasks`
  에는 한 글자도 손대지 않는다**(1221~1319행 전 구간에 `_pending_cancel_tasks` 참조 0건, 직접 확인).
- 결과: 30초 뒤(09:05:32) 이미 100% 체결된 주문의 취소 타이머가 그대로 발화 → KIS 가 "정정취소
  가능수량이 없습니다"(APBK0927)로 정당하게 거부 → `_cancel_after_wait` 의 `except Exception:`
  (1478-1479행)이 걸려 ERROR 로그 + traceback을 남긴다.

### 1-B. `[buy_fill_correction_unique_violation]` — ~~별개의, 이미 설계된 race 의 정상 자기치유~~ **[정정 V-1] 1차 `update_trade_status` 의 `PENDING` 단독 필터가 만든 것**

> **[정정 V-1] `affected=0` 의 귀인이 틀렸다.** 실측 로그 순서와 코드가 "선행 race(PENDING 미커밋)"
> 를 **배제**한다:
> ① `매수 주문 접수` 로그는 `order_engine.py:409-410` 으로 `await insert_trade(record)`(407)가
> **반환된 뒤**에만 찍히고, EC2 원문에서 그 행(09:05:01)이 `매수 부분 체결`(1328) 과
> `[buy_fill_correction_unique_violation]`(1274) **보다 앞**에 있다.
> ② 체결통보는 `websocket.py:782` `await self._on_message` → `handler.py:397-403`
> `await _handle_execution` 로 **순차** 처리되므로, 전량체결 분기의 UPDATE(1236-1239)는 부분체결
> 핸들러 종료 **이후** = **PENDING 행이 이미 커밋된 뒤**에 실행됐다.
> ③ 보정 INSERT 가 `UniqueViolation` 을 맞은 것 자체가 **그 순간 행이 존재했음**을 증명한다.
> ④ 그런데도 `affected=0` 이 나온 이유는 `update_trade_status` 의 WHERE 가
> **`status = 'PENDING' AND strategy = $`**(`trade_history.py:107`, `113-117`)로 **PENDING 만**
> 매치하기 때문이며, 그 행은 직전 부분체결 분기(1323-1326)가 이미 **`PARTIAL`** 로 바꿔 둔
> 상태였다고 보는 것이 유일하게 정합적이다(strategy 불일치 대안은 양쪽 다 kojiro 라 배제).
> ⑤ 결정적으로 `_update_trade_status_by_order_no` 의 **cycle235 주석**(`trade_history.py:212-216`)이
> "부분 체결로 이미 PARTIAL 이 된 row 를 전량 체결 보정이 COMPLETED 로 올리지 못해 affected=0"
> 이라는 **바로 이 시나리오**를 기술하고 그 실측 사례로 **`257720`** 을 든다.
> ⇒ **오늘 자기치유를 성립시킨 주체는 사이클 30/161 의 선행 race 폴백이 아니라
> cycle235 N1-b(강제 UPDATE 의 WHERE `PENDING∪PARTIAL` 포괄, `trade_history.py:212-229`)** 다 —
> cycle235 **이전이었다면** `[buy_fill_correction_forced_update_zero]`(1283-1287)로 PARTIAL 이
> **영구 잔존**했을 시퀀스다.

- `execute_buy` 는 `place_order` 응답 직후 매핑을 동기 등록(377-379행)하고, `_completed_orders`
  에 이 order_no 가 이미 있는지 확인(388행) 후 없으면 `insert_trade(PENDING)`(407행)을 **await** 한다.
- 전량체결 통보의 `_handle_buy_fill`(~~1235행~~ → **`:1236-1239`**, **[정정 V-5]** — 1235 는 `try:`)
  `affected = await update_trade_status(...COMPLETED...)` 이 `affected=0` 을 받으면
  ~~(문서화된 "체결통보 선행 race", 1120-1121·1135-1136행 docstring)~~
  (**오늘 사례에서는 위 [정정 V-1] 의 `PENDING` 단독 필터 때문**), 보정 경로로 낙하해
  `insert_trade(status=COMPLETED)`(1252-1263행)를 시도한다. 그런데 그 사이 `execute_buy` 의 `insert_trade(PENDING)`(407행)가 먼저
  커밋되어 있으면 이 보정 INSERT 가 `uq_trade_history_ticker_order_no_type` 유니크 인덱스에 걸려
  `UniqueViolationError` 를 낸다 — 1268행 `except Exception` 이 이를 잡아 WARNING 을 남기고
  `_update_trade_status_by_order_no(order_no, BUY, COMPLETED, price=price)`(1279행, 구현은
  `src/db/trade_history.py:179`)로 **강제 UPDATE** 한다. 로그의 `affected=1` 이 이 강제 UPDATE 성공을
  증명한다(`trade_history.py:235`).
- 이 경로는 **사이클 161/163 이 명시적으로 설계·테스트한 폴백**이다(주석 1135-1136행: "UniqueViolation
  (사이클 161 hotfix): 보정 INSERT 영역 try/except + 강제 UPDATE"). DB 최종 상태는 정확히
  `status=COMPLETED, price=24800`(원래 `insert_trade(PENDING)` 이 저장한 quantity=5 그대로) — 이중
  카운팅·유실 없음.

## 2. C235-V2 와 동일 결함인가 — **예, 동일하다**

`_workspace/00_URGENT_WORKLIST.md` "N1 — cycle235" 절(1220-1227행)의 후속 후보:

> "**후속 후보(행위 결정 사안)** = 전량 체결 분기의 잔여취소 타이머 해제 + 1차
> update_trade_status 의 PARTIAL 포괄(C235-V2) · `_completed_orders` 일일 리셋 확인(C235-R3)."

오늘 재현된 근본 원인(1-A)이 정확히 "전량 체결 분기의 잔여취소 타이머 해제" 미구현이다.
~~cycle235(2026-08-29) 시점에 **이미 식별**돼 있었고 우선순위상 시정되지 않은 채 방치된 결함이
오늘(2026-09-10) kojiro 004990 주문에서 최초로(적어도 이번에 처음 관측된 사례로) 실제 발화한 것이다.~~

> **[정정 V-6] 오늘이 최초가 아니다 — 최소 2번째 관측 발화다.** 영속 `system_logs` 에 **선행 발화**가
> 남아 있다: **2026-08-28 09:16:22 KST, ticker `257720`**(워크리스트 N1/N2 절의 그 종목).
> `부분 체결 잔여 취소 실패: 257720`(09:16:22.055478) + `[kis_rejection] … order-rvsecncl …
> APBK0927`(09:16:21.963337) 로 **메시지·거부코드·경로·body 가 09-10 004990 건과 전부 동일**하다.
> ⇒ 발화일은 cycle235(08-29)의 **하루 전**이며, C235-V2 후속 후보 기재는
> "**방치 뒤 오늘 최초 발화**" 가 아니라 "**실제 발화 직후 기재된 항목**" 이다.
> 재현: `GET /api/logs/search?q=APBK0927&limit=50` → **total=4**(08-28 2행 + 09-10 2행) ·
> `q=잔여 취소 실패` → **total=2**(08-28 `257720` / 09-10 `004990`).
> ⚠️ 08-28 이 **진짜 최초**인지는 `system_logs` 의 보존/커버리지를 확인하지 않아 미확정 —
> 확정된 것은 "09-10 이 최초가 아니다"(반증)이고 **총 발화 하한은 2** 다.

`_completed_orders` 일일 리셋(C235-R3)은 이번 사고와 무관 — 이번 관측 대상이 아니다.

~~"1차 update_trade_status 의 PARTIAL 포괄"(부분체결 분기가 `affected==0` 을 확인하지 않는 문제,
1323-1326행)도 이론상 같은 시퀀스에 관여할 수 있으나, 오늘 사례는 결국 DB 가 올바른 COMPLETED
상태로 자기치유됐으므로 그 갭이 실제 피해를 만들지 않았다.~~

> **[정정 V-7] "1차 `update_trade_status` 의 PARTIAL 포괄" 은 이론이 아니라 오늘 실제로 발화한
> 트리거다.** 워크리스트 1224행이 cycle235 시정 ③ 을 이미 "강제 UPDATE WHERE PENDING+PARTIAL
> 포괄(N1-b)" 로 명시하므로, 1226-1227 의 남은 후속 "**1차** `update_trade_status` 의 PARTIAL 포괄"
> 은 강제(2차) UPDATE 가 아니라 **`trade_history.update_trade_status`(88-123행)의 status 필터에
> PARTIAL 을 넣는 것**을 뜻한다 — '부분체결 분기의 `affected` 미확인' 은 그 문장의 지시 대상이 아니다.
> 그리고 [정정 V-1] 이 보인 대로 **그 갭이 오늘 `affected=0` → 보정 INSERT → UniqueViolation →
> 강제 UPDATE 체인을 실제로 촉발했다.**
> ⇒ **C235-V2 는 두 항목이 각각 오늘 사건의 (a) 근본원인(잔여취소 타이머 미해제)과
> (b) 실제 발화한 트리거(1차 `update_trade_status` 의 PARTIAL 미포괄)로 둘 다 실측 재현됐다.**
> '이론상 관여 가능' 이 아니라 '**오늘 관측됨**' 으로 격상해야 한다.

## 3. 실손실/위험 평가

**오늘 사례 — 관측상 무해, 로그 소음**:
- 포지션: 5주 정확 (사용자 확인 사항, 매매 로그와도 정합 — "매수 전량 체결: 5주").
- trade_history: 강제 UPDATE(`affected=1`)로 `status=COMPLETED, price=24800` 정합. 이중 INSERT/중복
  체결 기록 없음(부분 UNIQUE 인덱스가 실제로 막았다 — 설계대로 동작).
- 취소 API 호출(`cancel_order(order_no, 0, cancel_all=True, …)`)이 이미 전량 체결된 주문을 대상으로
  했으나 KIS 가 "취소 가능 수량 없음"으로 정상 거부했을 뿐 — 실주문에 어떤 영향도 주지 않았다
  (취소할 잔량이 물리적으로 0이므로 다른 주문을 잘못 건드릴 경로 자체가 없다).
- 결과: **재무적 손실 0, 포지션 오류 0** — ERROR 2건은 순수 로그 표면 현상.

**재발 시 위험 시나리오**:
1. **알림 피로/신호 대 잡음 저하 (구조적 반복)** — ~~`PARTIAL_FILL_WAIT=30초` 이내에 부분→전량이
   이어지는 체결은 유동성 높은 종목에서 드물지 않다~~(7개 전략 전부가 이 공용 경로,
   `_schedule_cancel`/`_handle_buy_fill` 를 공유). 고쳐지지 않는 한 **이런 패턴이 나올 때마다 매번**
   ERROR ~~2행~~ **3행**(**[정정 V-2]**, `system_logs` 기준)이 남는다.

   > **[정정 V-8] "드물지 않다" 는 근거 없는 빈도 주장이다.** 실측 base rate 는 오히려 **희소**를
   > 시사한다 — 2026-09-10 하루 `매수 부분 체결` **1건**(매도 부분체결 0건), APBK0927 발화는
   > 08-28·09-10 **2주간 2회**. **"고쳐지지 않는 한 발화할 때마다 ERROR 3행" 이라는 결론은 유효**하되
   > 빈도 전제는 삭제해야 한다. 정확한 빈도 측정에는 과거 로그의 `매수 부분 체결` ↔ `매수 전량 체결`
   > **동일 `order_no` 30초 내 페어 집계**가 필요하다. `log_analysis_engine` 의 20:10 일일 리포트가 WARNING/ERROR/CRITICAL 을
   `top_patterns` 로 집계하므로(`src/engine/log_metrics_collector.py`), 이 벤치나인 ERROR 가 반복
   누적되면 운영자·AI 자문이 진짜 이상 신호를 이 소음 속에서 놓칠 위험이 커진다(cycle237 이 donchian
   청산 로그 폭주를 캡한 것과 같은 계열의 문제 — 아직 이 경로는 캡이 없다).
2. **관측 공백 상태에서의 오판 위험(낮은 확률)** — 이번 사례처럼 강제 UPDATE 로 자기치유되는 것은
   `_handle_buy_fill` 의 UniqueViolation 폴백이 있기 때문이다. 만약 향후 리팩토링으로 그 폴백이
   약화되거나(`_update_trade_status_by_order_no` 실패 시 `[buy_fill_correction_forced_update_zero]`
   ERROR, 1283-1287행), PENDING 행이 아예 존재하지 않는 특이 케이스가 겹치면 trade_history 가
   COMPLETED 로 정합되지 못한 채 남을 수 있다 — 오늘 사례는 이 실패 분기까지는 가지 않았지만, 같은
   race 가 반복되는 한 이 실패 분기에 도달할 확률은 0이 아니다.

## 4. 결론

- ERROR 2건("부분 체결 잔여 취소 실패: 004990")과 WARNING 1건(`buy_fill_correction_unique_violation`)
  모두 **금전적/포지션 피해 없음** — 전자는 미해제 타이머의 무해한 뒷북 취소 시도, 후자는 이미
  설계된 race 폴백의 정상 동작.
- 근본 원인은 **cycle235 시점에 이미 식별된 C235-V2 후속 후보와 동일 결함**이며, 오늘 실측으로
  재현이 확인됐다. 시정(전량 체결 분기에서 `_pending_cancel_tasks[ticker]` 취소)은 `order_engine.py`
  가 8영역이라 **승인 대상**이며, 본 작업 범위(읽기 전용)를 벗어난다.

---
*출처: EC2 `docker compose -f docker-compose.prod.yml logs backend --since 2026-09-10T00:00:00`(2026-09-10
조회) / `src/engine/order_engine.py`(라인 번호는 로컬 리포 `main` 브랜치, 이 세션 조회 시점 기준) /
`src/api/base.py` / `src/api/order.py` / `src/db/trade_history.py` / `_workspace/00_URGENT_WORKLIST.md`
"N1 — cycle235" 절.*

---

## 검증 반영 (2026-09-10, 적대 검증 2렌즈 — 재산출 · 코드 대조)

> 원문은 지우지 않고 ~~취소선~~ + 정정값 + 근거로 남겼다.
> **핵심 결론은 그대로다** — 실손실 0 · 포지션 5주 정확 · 근본 원인 = C235-V2 미구현.
> 다만 **두 가지가 실질적으로 바뀌었다** — (가) 자기치유의 **주체**가 사이클 161 선행 race 폴백이
> 아니라 **cycle235 N1-b** 였다(V-1) (나) 오늘이 **최초 발화가 아니다**(V-6, 08-28 `257720` 선행).

| # | 위치 | 원문 | 정정 | 근거 (재현) |
|---|---|---|---|---|
| **V-1** | 선요약 · §1-B | `[buy_fill_correction_unique_violation]` = "**체결통보 선행 race**(PENDING 미커밋)" 의 정상 자기치유 | **`affected=0` 은 1차 `update_trade_status` 의 status 필터가 `PENDING` 단독**(`trade_history.py:107`, `113-117`)이라 **이미 `PARTIAL` 이 된 행**을 못 잡은 결과다. 선행 race 는 **배제**된다 — `매수 주문 접수` 로그(`order_engine.py:409-410`)가 `insert_trade`(407) **반환 뒤**에만 찍히고 EC2 원문에서 그 행이 부분체결·UniqueViolation 보다 **앞**에 있으며, 체결통보는 `websocket.py:782` → `handler.py:403` 로 **순차** 처리된다. **자기치유 주체 = cycle235 N1-b**(`trade_history.py:212-229`) | `trade_history.py:212-216` cycle235 주석이 **바로 이 시나리오**를 기술하고 실측 사례로 **`257720`** 을 든다. cycle235 이전이었다면 `[buy_fill_correction_forced_update_zero]`(1283-1287)로 PARTIAL 영구 잔존 |
| **V-2** | §0 · §3-1 | 1회 실패가 남기는 ERROR = **2행** | **stdout 2행 / `system_logs` 3행.** `src/api/base.py:643` 이 `[kis_rejection] …` 을 `write_log("ERROR", …)` 로 **DB 에만** 기록한다(당일 stdout `grep -c kis_rejection` = 0). 20:10 리포트는 `system_logs` 를 집계하므로(`log_metrics_collector.py:78/105/134`) **운영자가 보는 수는 3**이다 ⇒ 소음 논거 **강화** | `GET /api/logs?level=ERROR&from_date=2026-09-10&to_date=2026-09-10` → **total=3**, CRITICAL=0, 3행 모두 이 한 건 |
| **V-3** | §0 | "09:05:32 = 09:05:01 + `PARTIAL_FILL_WAIT=30`초" | 09:05:01 + 30초 = **09:05:31**. 실제 델타는 **31초** — 매수 시각 소수부(`trade_history` 09:05:01.958) + KIS 왕복 지연. **30초 타이머 인과는 유효**, 등식 표기만 부정확 | `system_logs` 밀리초 09:05:32.279444 |
| **V-4** | §0 머리말 · 바닥글 | 재현 명령 `--since 2026-09-10T00:00:00` = "09-10 하루치" | EC2 호스트 TZ 가 **UTC** 라 그 값은 **KST 09:00:00** 이다 — **00:00~09:00 KST(NXT 프리장 포함)가 통째로 빠진다.** 정정 = `--since 2026-09-09T15:00:00`. 그 창으로 다시 세도 `[ERROR`=2·`[CRITICAL`=0 으로 **결론 유지**. 더 안전한 정본은 `system_logs` KST 필터 | `date` → `Thu Sep 10 … UTC 2026`, `/etc/timezone` → `Etc/UTC` |
| **V-5** | §1-A · §1-B | pop 4행 = `1313-1316` · `affected = await update_trade_status(...)` = `1235행` | pop **`:1310-1313`** · `_completed_buy_orders.add` **`:1316`**(1314-1315 는 주석) · UPDATE 대입문 **`:1236-1239`**(1235 는 `try:`). **결론 무영향, 서식 오차** | `sed -n '1230,1245p'`·`'1305,1330p' src/engine/order_engine.py` |
| **V-6** | §2 | "오늘 kojiro 004990 주문에서 **최초로** 실제 발화" | **최소 2번째다.** 선행 = **2026-08-28 09:16:22 KST, ticker `257720`** — 메시지·거부코드·경로·body 동일. ⇒ 발화일은 cycle235(08-29)의 **하루 전**이고, C235-V2 기재는 "방치 뒤 오늘 최초 발화" 가 아니라 **"실제 발화 직후 기재된 항목"** 이다 | `q=APBK0927` → total=**4**(08-28 2 + 09-10 2) · `q=잔여 취소 실패` → total=**2**. ⚠️ 08-28 이 진짜 최초인지는 보존 커버리지 미확인 — **총 발화 하한 2** |
| **V-7** | §2 | "1차 `update_trade_status` 의 PARTIAL 포괄" 은 "**이론상** 관여 가능하나 피해 없음" | **오늘 실제로 발화한 트리거다**(V-1). 워크리스트 1224행이 cycle235 시정 ③ 을 이미 "강제 UPDATE WHERE PENDING+PARTIAL(N1-b)" 로 명시하므로 1226-1227 의 남은 후속은 **`trade_history.update_trade_status`(88-123행)의 status 필터**를 뜻한다 — '부분체결 분기의 affected 미확인' 은 그 문장의 지시 대상이 아니다. ⇒ **C235-V2 두 항목 모두 오늘 실측 재현**(a=근본원인, b=발화 트리거) | 워크리스트 §"N1 — cycle235" 1220-1227행 |
| **V-8** | §3-1 | "30초 이내 부분→전량 체결은 유동성 높은 종목에서 **드물지 않다**" | **근거 없는 빈도 주장이며 실측은 희소를 시사한다** — 09-10 하루 `매수 부분 체결` **1건**(매도 0건), APBK0927 발화 **2주간 2회**. "발화할 때마다 ERROR 3행" 결론은 유효, **빈도 전제는 삭제** | 정확한 측정에는 `매수 부분 체결` ↔ `매수 전량 체결` 동일 `order_no` 30초 내 페어 집계 필요 |

### 지적을 받아들이지 않은 것

**없다.** 8건 전부 로그 재조회·코드 대조로 확인해 반영했다.

### 이 절이 닫지 못한 것 (원문 유지)

- **DB 최종 상태를 직접 읽지 않았다.** 강제 UPDATE `affected=1` 과 메모리 포지션 5주는 확인했으나
  `trade_history` 해당 행 자체(`quantity` 가 원래 PENDING INSERT 의 5 그대로인지, `price` 가
  24,800 인지)는 **SELECT 하지 않았다**.
- **부분체결 분기(1323-1326)의 `update_trade_status(...PARTIAL...)` 가 실제로 `affected=1` 을 냈는지**
  — 그 함수의 결과 로그는 `trade_history.py:121-122` `logger.debug` 라 콘솔·`_DbLogHandler`(INFO)
  어디에도 남지 않는다. **V-1 은 배제 추론**(UniqueViolation 발생 + `affected=0` + 순차 처리 로그
  순서)이며 행 상태 이력을 직접 읽어 확증한 것이 아니다(`trade_history` 는 이력 테이블이 아님).
- **08-28 `257720` 건이 동일한 "부분체결 → 같은 초 전량체결" 시퀀스였는지** — 그날의
  `매수 부분 체결`/`매수 전량 체결` 원문은 docker 로그 보존 밖이라 재구성하지 않았다.
  동일한 것은 **거부코드·경로·에러 메시지·호출 지점(`_cancel_after_wait`)** 까지다.
- **증권사 실잔고 5주** — 확인한 것은 `trade_history` 1행 `quantity=5`(`GET /api/history`)와
  로그 `매수 전량 체결 … 5주`(1319행, 인자는 `total_filled`)까지다. KIS 실잔고 조회는 외부 API
  호출을 유발해 수행하지 않았다(읽기 전용 규약). **'실손실 0' 도 이 렌즈에서는 판정 불가.**
- **§3-2 의 `[buy_fill_correction_forced_update_zero]` 도달 확률** — 그 마커의 과거 발화 이력을
  `system_logs` 에서 조회하지 않았다(반사실 시나리오라 코드 대조로도 검증 불가).
