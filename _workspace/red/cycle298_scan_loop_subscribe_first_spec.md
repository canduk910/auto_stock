# cycle298 — `_scan_loop` 구독-먼저 전환 + 정본 문서 시각 상수 오류 시정

사용자 승인 2026-09-17 17:1x KST. 배경 정본 = `_workspace/00_URGENT_WORKLIST.md` 「재기동 시 시세 구독 공백」.

---

## §1 문제 (실측)

2026-09-17 16:11 배포에서 프로세스 부재는 56초인데 **시세 구독 공백은 5분 16초**였다
(16:11:55 부팅 완료 → 16:17:12 148종목 ACK). 보유 11종목의 손절·트레일링 평가가 그동안 0회.

원인 = 15:20 이후 기동 경로에 사전 구독 호출이 없고, 유일한 구독 경로 `_scan_loop` 이
`while` 진입 직후 `await asyncio.sleep(SCAN_INTERVAL)`(300초)을 **먼저** 한다
(`src/engine/scheduler.py:2362-2363`, 구독은 `:2382`).

## §2 채택 설계 — 첫 회차 지연을 호출부가 정한다

```python
async def _scan_loop(self, *, first_delay: float | None = None) -> None:
    sync_counter = 0
    delay = SCAN_INTERVAL if first_delay is None else max(0.0, float(first_delay))
    while self._running:
        await asyncio.sleep(delay)
        delay = SCAN_INTERVAL
        ...  # 이하 현행 byte 동일
```

호출부 2곳의 배정이 **계약**이다:

| 생성 지점 | 인자 | 이유 |
|---|---|---|
| `scheduler.py:846` (09:30~15:20 진입) | **인자 없음**(=300초) | 바로 앞 `:837-843` 에서 `scan_stocks()` + `subscribe_filtered_stocks()` 를 **이미 동기적으로** 했다. 0 을 주면 같은 조건검색·구독을 수초 안에 두 번 한다 |
| `scheduler.py:876` (15:30 POST_NXT 전환) | **`first_delay=0`** | 이 경로에는 선행 구독이 **하나도 없다**. 15:30~19:50 기동의 약 5분 공백이 여기서 생긴다 |

⚠️ **`:876` 은 재기동 전용 경로가 아니다 — 매일 탄다.** `:849-851` 의 15:20 `cancel()` 이 `done()=True` 를 만들어 `:875` 조건이 평시에도 매일 성립한다. 즉 `first_delay=0` 은 매일 15:30 에 발효하며, 그날의 첫 POST_NXT 재구독을 15:35 에서 15:30 으로 당긴다.

기본값이 `None`(=현행 300초)이라 **인자를 안 주는 모든 호출은 byte 동일**이다.

## §3 검증 가능한 행위 (Red 대상)

- **B1** `_scan_loop()` 를 인자 없이 만들면 첫 구독 전에 `SCAN_INTERVAL` 을 잔다 (현행 보존).
- **B2** `_scan_loop(first_delay=0)` 은 **첫 sleep 없이** 즉시 `scan_stocks`+`subscribe_filtered_stocks` 를 부른다.
- **B3** 첫 회차 뒤 주기는 항상 `SCAN_INTERVAL` 로 복귀한다(2회차 sleep 인자 == 300).
- **B4** `first_delay` 음수·비수치는 0 으로 클램프하거나 그대로 `max(0.0, ...)` — 절대 예외로 루프를 죽이지 않는다.
- **B4b** `first_delay` 는 **상한도 걸린다** — `float("inf")`·`1e9` 같은 거대값이 와도 첫 지연이 `SCAN_INTERVAL` 을 넘지 않는다. 상한이 없으면 `asyncio.sleep(inf)` 이 **예외도 로그도 없이 그 루프를 영구 blind** 로 만든다(무음 실패). 계약 = `delay = min(float(SCAN_INTERVAL), max(0.0, float(first_delay)))`.
- **B5** 기동 시각별 첫 구독 시점 봉인(freezegun, 창 안·밖 두 시각):
  - `15:30 ≤ T < 19:50` → 생성 즉시 구독 (공백 ≈ 0)
  - `15:20 ≤ T < 15:30` → 15:30 에 구독 (공백 = 15:30 − T, **최대 10분**. 완전히 닫히지 않는다 = §5 권고 카드)
  - `09:30 < T < 15:20` → 현행과 동일(선행 인라인 구독 + 루프 첫 회차는 300초 뒤)
- **B6** `sync_counter % 3` 의 `_sync_positions_from_balance` 는 **회차 기준**이라 위상만 5분 당겨진다 — 주기(3회차)는 불변.
- **B7** `19:50` cancel / `20:00` `unsubscribe_all()` / `TIME_SESSION_START_CUTOFF` 기동 거부 경로 **무접촉**.

## §4 위험 판정 (팀장 사전 검토)

| # | 위험 | 판정 |
|---|---|---|
| 1 | 이미 즉시 구독하던 경로의 이중 스캔 | **회피됨** — `:846` 은 인자를 안 준다. 기본값이 현행값이다 |
| 2 | 매매 행위 변화 | **구간을 나눠 읽는다.** `_scan_loop` 본문에는 주문 발화점이 없다(주문은 `risk.on_tick` · `_drain_pending_next_day_clear` · `_force_clear_main_only` · `_swing_buy_poll_loop` 넷뿐). 바뀌는 것은 **구독 시각**이고 구독은 `on_tick` 의 입구다. ⓐ **15:30~16:00 = 변화 0** — 그 창의 주문은 `order_engine._market_rest_now` 가 전량 컷한다(실측 15:31·15:45·15:59 → `market_rest`). ⓑ **16:00~19:50 재기동 = 손절·트레일링 매도와 LTV `post_nxt` 매수가 최대 5분 앞당겨진다** — 결함이 아니라 이 사이클이 되찾으려는 **손절 커버리지 그 자체**다(16:11 배포에서 보유 11종목이 5분 16초 동안 평가 0회였다). ⓒ **평시 무재기동 = 보유 종목 틱 커버리지 불변**(15:20 cancel 은 구독을 해제하지 않는다 — 해제는 20:00 `unsubscribe_all` 뿐). 트레일링 앵커 오염도 없다: 새로 덮이는 15:30~16:00 은 KRX K5(장후 시간외 **종가**)라 체결가가 종가 상수여서 `high_since_buy` 가 정규장 고가 위로 올라갈 수 없다 |
| 3 | `sync_counter % 3` | 위상만 5분 당겨짐(15:40 vs 15:45). 주기 불변 |
| 4 | 19:50 cancel · 20:00 `unsubscribe_all` · 20:00 기동 거부 | 무접촉 (`first_delay` 는 루프 진입 지연만 바꾼다) |
| 5 | cycle295 15:30~16:00 완전 휴식 | 충돌 없음 — 구독은 되고 주문은 0. `[market_rest_window]` 1회/일 카나리아도 불변 |
| 6 | `MAX_SUBSCRIPTIONS`(41) · HIGH bypass | 무접촉 — 구독 호출의 인자 구성이 그대로다 |

## §5 남는 공백 (권고 카드 — 이번 사이클 범위 밖)

`15:20 ≤ T < 15:30` 기동은 **최대 10분** 공백이 남는다(`:852` else 가 `_scan_task=None` 으로 두고
15:30 까지 기다린다). 닫으려면 그 else 분기에 보유 ∪ `_pending_next_day_clear` **HIGH 구독 1회**를
넣어야 한다 = 범위 확장이므로 사용자 확인 대상.

🔴 **그 대역은 무해하지 않다** — `_market_rest_now(15:22)` = `(False, "krx_sendable")` 다(KRX K4 종가
단일가가 `("00","01")` 을 받는다). **손절 주문은 접수되는데 평가할 틱이 없는 구간**이라, 15:30~16:00
컷 구간과 성격이 다르다.

또한 `07:45 ≤ T < 07:59` 기동의 최대 14분은 이번 설계의 대상이 아니다(08:00 NXT 프리 개장 전이라
그 구간에는 애초에 틱이 없다).

## §6 관측

첫 회차 구독 직후 1행: `[scan_loop_first_subscribe] first_delay=<초> elapsed_s=<루프 생성 후 경과> n=<구독 시도 종목수>`
(INFO, never-raise, 첫 회차에만). 관측 실패가 루프를 끊지 않는다.

## §7 제약

- `scheduler.py` 라인 상한 **< 3,900**(현재 3,726). 변경 후 라인 수를 보고에 적는다.
- 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` ·
  `src/realtime/**` · `src/auth/**`) **무접촉**. 필요하면 멈추고 팀장에게 보고.
- `git commit` / `push` 금지.

---

## §8 별건 — 정본 문서 오류 2건

| 상수 | 문서 서술 | 코드 사실(2026-09-17 grep 전수) |
|---|---|---|
| `TIME_BOOT = time(7,55)` (`scheduler.py:58`) | "07:55 `_boot()` 실행" | **런타임 참조 0건.** `_boot()` 는 `start()` 안에서 즉시 불린다(`scheduler.py:600`) = 07:45 자동 기동 직후. src 참조는 정의 1줄 + `websocket.py:46` 주석뿐 |
| `TIME_POST_NXT_OPEN = time(15,40)` (`scheduler.py:62`) | "15:40 NXT 애프터 진입 + `_confirm_breakout_open_prices(board='post_nxt')`" | **런타임 참조 0건.** 실제 전환·확정은 `TIME_KRX_MAIN_CLOSE`(15:30) 직후(`scheduler.py:865-874`) |

⚠️ **혼동 금지** — `session._BOARD_SCHEDULE` 의 보드 경계 `post_nxt` **15:40~20:00 은 사실이다**(별개 축).
고칠 것은 "**스케줄러가 15:40 에 무엇을 한다**"는 서술뿐이다.

상수 삭제는 **하지 않는다** — 테스트 6파일이 두 상수를 참조하며, 그중
`tests/unit/engine/scheduler/test_post_nxt_open_time.py::test_time_post_nxt_open_is_15_40` 와
`tests/unit/engine/test_cycle92_time_boot_moved.py` 는 값 자체를 핀한다. 문서에 "런타임 미사용"을
현재형으로 적고, 상수 정리는 별도 카드로 권고한다.
