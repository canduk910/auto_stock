# cycle379 명세 — ⑨A `buying_reconcile` (체결 0으로 끝난 매수의 pending 회수)

작성 2026-09-27 · domain-expert · 사용자 결정 2026-09-27 「9-a 풀어준 종목 재매수가능」(⑨A 카드 승인 포함) · `scheduler.py` 위임 줄 접촉 승인(상한 <3,900)
근거 = `_workspace/red/bundle_D_plan.md` ④ · `_workspace/domain_consult/cycle373_bundleD_S2_measurements.md` §2 · `cycle335_buy_post_send_boundary.md` Q1(b)·카드 A · `src/engine/CLAUDE.md` 규칙 4 「알려진 비용」

---

## 0. 한 줄

15분 잔고 sync 끝에서, `pending_buys` 에 걸린 종목의 **자기 주문번호 행**이 KIS 일별주문체결(TTTC0081R)에서 `tot_ccld_qty==0 ∧ rmn_qty==0` 이고 주문 뒤 5분이 지났으면 그 pending 을 풀고 장부 행을 CANCELLED 로 적는다. 증거가 하나라도 모자라면 푼다가 아니라 **유지**한다.

## 1. 트레이더 시각

- **무엇을 되찾나** — 거래소가 접수 뒤 죽인 매수 주문(거부 · GTP 08:50 자동취소 · KRX 15:30 정규장 미체결 자동취소)이 21:30 까지 붙잡고 있던 **전략 슬롯 1개 + 그 금액 + 그 종목 진입권**. 순수 기회비용이다.
- **실측 코호트**(cycle373) — 우리 주문 기준으로 8거래일 1건(437730 09-15 momentum, `ord1·ccld0·rmn0·rjct1`)이고 **접수 뒤 거부**다. GTP 자동취소는 우리 주문에서 0건이다. KRX 15:30 자동취소(09-14 신설)는 표본이 없다. 가치는 작고, 그래서 **잘못 푸는 비용이 이 작업의 전부**다.
- **잘못 풀면** — 살아 있는 주문을 잊는다 = 전략 예산 이중 사용 + 같은 종목 2랏(momentum·VB·LTV 는 래치가 없다) + `max_positions` 초과. cycle335 가 pending 을 붙잡기로 한 이유 그대로다. 따라서 **부재가 아니라 양성 증거로만** 푼다(카드 원문 「미체결 목록에 없으면 해제」를 버린다 — 부재는 첫 쪽 잘림·조회 지연·주문번호 형식 차이를 전부 「끝났다」로 읽는다).

## 2. 확정 설계

### 2.1 파일

| 파일 | 변경 |
|---|---|
| **신규** `src/engine/buying_reconcile.py` | leaf 본체(≈180줄). `selling_reconcile.py` 대칭 |
| `src/engine/scheduler.py` | `_sync_positions_from_balance` 끝, `reconcile_stale_selling` 위임 **뒤**에 4줄(3,781→3,785) |
| `src/api/balance.py` | `get_daily_orders(target_date="", exchange="ALL", *, odno: str = "")` — keyword-only, `"ODNO": odno`. 기본값이면 params **byte 동일** |
| 8영역 | **무접촉**. `order_engine` 은 인자로 받은 객체의 속성만 만진다(selling_reconcile 의 `_selling` 선례와 같은 패턴). 🔴 리뷰가 order_engine 메서드로 옮기자고 하면 **멈추고 보고**한다(그 순간 8영역 승인 사안) |

scheduler 4줄(정확히 이것):

```python
        # cycle379 ⑨A — 체결 0 으로 끝난 매수의 pending 회수(자기 주문 행의 양성 증거로만). leaf 위임.
        if any(s.state.pending_buys for s in self.registry.all()):
            from src.engine.buying_reconcile import reconcile_stale_buying
            await reconcile_stale_buying(self.registry, self.order_engine, holdings)
```

`holdings` 는 같은 함수 첫 줄 `get_balance()` 값을 재사용한다(추가 잔고 조회 0).

### 2.2 공개 API

```python
BUYING_RECONCILE_MIN_AGE_S = 300          # leaf 소유(신규 leaf 라 scheduler 로 올릴 이유 없음)
MAX_ORDER_LOOKUPS_PER_PASS = 10           # 패스당 주문번호 조회 상한
ORD_TMD_FUTURE_TOLERANCE_S = 60           # ord_tmd 가 now 보다 이만큼 넘게 미래면 age_unknown

async def reconcile_stale_buying(registry, order_engine, holdings, *,
                                 min_age_s: float = BUYING_RECONCILE_MIN_AGE_S,
                                 now: datetime | None = None,
                                 max_lookups: int = MAX_ORDER_LOOKUPS_PER_PASS) -> None
def reset_buying_reconcile_state() -> None   # hold cap · release_n 초기화(테스트 훅)
```

- 시계 = `now` 주입, 없으면 `datetime.now(_KST)`. `_KST = timezone(timedelta(hours=9))` 를 leaf 안에서 만든다(scanner 등 8영역 import 0).
- logger = `logging.getLogger(__name__)`(신규 leaf 라 옛 접두 연속성이 없다). 영속은 루트 `_DbLogHandler`(src.* INFO 이상). 🔴 `write_log` import·호출 0.
- **never-raise** — 본체 전체 `try/except Exception` → `logger.exception("[buying_reconcile_error] …")`. `CancelledError` 는 전파(BaseException).

### 2.3 판정 순서 (종목 = 후보 1개)

후보 = `registry.all()` 의 각 전략 `s`, `s.state.pending_buys` 의 각 `t`. 연결 주문 = `order_engine._pending_buy_orders` 중 `info["ticker"]==t` 인 **모든** `odno`(전략 무관).

**A. 메모리 단계 — `await` 0, KIS 호출 0**

| # | 조건 | 결과 |
|---|---|---|
| A1 | `t` 가 2개 이상 전략의 `pending_buys` 에 있다 | 유지 `ambiguous_owner` |
| A2 | 어느 전략이든 `has_position(t)` **또는** KIS `holdings` 에 `t` 수량>0 | 유지 `held` |
| A3 | 연결 주문 0개(`execute_buy` 의 `await place_order` 창, 또는 매핑 유실) | 유지 `no_order_no` |

A 를 통과한 후보가 없으면 **KIS 호출 없이 반환**한다 — 기존 sync 테스트의 `get_daily_orders` 호출 수가 바뀌지 않는 근거다.

**B. KIS 단계**

| # | 조건 | 결과 |
|---|---|---|
| B1 | 오늘 전체 목록 `get_daily_orders(target_date=오늘)` 1회 — 예외 | 생존 후보 전부 유지 `lookup_error`, 반환 |
| B2 | 그 목록에 `sll_buy_dvsn_cd=="02" ∧ pdno==t ∧ rmn_qty>0` 행이 있다(수동 MTS 주문 포함, 거래소 ALL) | 유지 `open_order` |
| B3 | 연결 주문마다 `get_daily_orders(target_date=오늘, odno=o)` — 패스 누적 `max_lookups` 초과분 | 유지 `deferred` |
| B4 | 그 조회 예외 | 유지 `lookup_error` |
| B5 | 일치 행 = `odno.strip()==o.strip() ∧ sll_buy_dvsn_cd=="02" ∧ pdno.strip()==t` 이 0행 | 유지 `not_found` |
| B6 | 일치 행의 `tot_ccld_qty`·`rmn_qty` 중 하나라도 부재·빈 문자열·비숫자 | 유지 `bad_row` (🔴 빈 값을 0 으로 읽지 않는다 — 양성 증거는 명시값이어야 한다) |
| B7 | Σ`rmn_qty` > 0 | 유지 `open_order` |
| B8 | Σ`tot_ccld_qty` > 0 | 유지 `fill_seen` |
| B9 | 나이 = `now − max(ord_tmd)`. `ord_tmd` 부재·6자리 아님·파싱 실패·`now + 60s` 보다 미래 | 유지 `age_unknown` |
| B10 | 나이 < `min_age_s` | 유지 `too_young` |

행이 여럿이면(SOR 분할 대비) 수량은 **합**, `ord_tmd` 는 **가장 늦은 값**(가장 젊은 나이)으로 본다. 한 종목의 연결 주문이 여럿이면 **전부**가 B 를 통과해야 푼다.

**C. 재검증 → 해제 — 둘 사이 `await` 0**

마지막 `await` 뒤에 다시 본다: ① `t ∈ s.state.pending_buys` ② `t` 를 pending 으로 든 전략이 여전히 `{s}` 하나 ③ 연결 주문 집합이 평가한 집합과 같다 ④ 어느 전략도 `has_position(t)` 아님. 하나라도 어긋나면 유지 `raced`(변이 0).

통과하면 같은 동기 블록에서:

- `s.state.pending_buys.discard(t)`
- `amount = s.state.pending_buy_amounts.pop(t, None)`
- 연결 주문 전부 `order_engine._pending_buy_orders.pop(o, None)`

= `order_engine._handle_buy_fill` 첫 체결 경로가 지우는 것과 **같은 세 가지**. 🔴 `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 **남긴다** — 우리 판단이 틀려 늦은 체결통보가 오면 그 매핑이 올바른 전략·주문수량(`qty_src=map`)으로 포지션을 세우는 안전망이고, cycle354 sync 귀속도 `_order_strategy` 를 읽는다. 21:30 reset 이 치운다. 🔴 `sold_today`·`buy_blocked_until`·`low_funds_tickers`·`_completed_buy_orders` 무접촉.

**D. 장부 — 해제 뒤 `await`**

연결 주문마다 `update_trade_status(t, TradeType.BUY, TradeStatus.CANCELLED, strategy=info["strategy_id"], order_no=o)` — `match_partial` **미전달**(PENDING 만 잡는다 → PARTIAL·COMPLETED 는 절대 안 뒤집는다). `affected` 를 마커에 싣는다. 예외는 `db=error` 로 싣고 메모리 해제는 되돌리지 않는다(되돌리면 다시 21:30 까지 묶는 것뿐이고 KIS 사실은 이미 확정이다).

왜 CANCELLED 가 필수인가 — 재진입을 허용하면 그 종목을 다시 사 보유가 생기고, 다음 sync 첫머리의 `mark_pending_buys_completed(t)` 가 날짜·주문번호 무관으로 **모든** PENDING BUY 행을 COMPLETED 로 뒤집는다 → 죽은 주문이 유령 체결이 되어 정산 `buy_total` 이 부풀고 성과 귀인이 틀어진다(cycle373 의 101730 07-06 행이 그 직전까지 갔다).

### 2.4 결정 사항

| 결정 | 값 | 근거 |
|---|---|---|
| **최소 경과** | **300초** | 거부·자동취소는 접수 후 수 초 안에 KIS 행에 반영된다. 잘못 풀 때의 비용(2랏)이 selling 의 잘못 풀 때 비용(평가 재개, 열린 주문 가드가 받침)보다 커서 180초보다 보수적으로 잡는다. sync 가 15분 간격이라 이 값이 묶는 경우는 「sync 직전 5분 안에 낸 주문」뿐이고 그 대가는 다음 sync(15분) 지연 하나다 |
| **경과의 출처** | **그 주문 자신의 KIS 행 `ord_tmd`**(오늘 날짜와 합쳐 KST) | 막으려는 위험이 「주문 직후의 전파 지연」이라 주문 시각을 직접 재는 것이 맞다. leaf 가 처음 본 시각(first-seen)은 매 해제를 15~30분 늦추고 안전은 더하지 않는다. `order_engine` 엔 주문 시각이 없고 넣으려면 8영역이다 |
| **재진입** | **허용**(사용자 결정). 새 래치·`sold_today` 추가 없음. 기존 규칙(보유·주문중·당일매도 가드, 4전략 `_bought_today`)은 그대로 | — |
| **거부 반복 루프** | 행위 제한 없음. 마커 `release_n=`(그날 그 종목 해제 횟수)로만 드러낸다 | 캡을 두면 그것이 곧 「추가 당일 차단」이라 사용자 결정과 충돌한다. 8거래일 1건 빈도에서 루프는 최악 15분 간격 재주문·재거부이고 돈이 들지 않는다. 판독 규칙 §3 |
| **CANCELLED 표기** | 한다(주문번호 한정, PENDING 만) | §2.3 D |
| **킬스위치** | 넣지 않는다 | 해제는 KIS 양성 증거에만 걸리고 최악(늦은 체결)도 매핑 안전망이 받는다. 롤백 = revert + 장외 배포(§6). 넣으면 getter·키·문서가 딸려 오는 범위 확대다 |

### 2.5 적용 시간대 (스코핑 정정)

sync 는 `_scan_loop` 의 3회차마다 돈다. `_scan_loop` 은 09:30~15:20 **과** 15:30~20:00(cycle298 `first_delay=0` 재생성) 두 번 산다 → 해제 시점은 **≈09:45~15:15 · ≈15:40~19:55**. 스코핑 메모의 「09:45~15:15 뿐」은 틀렸다.

| 코호트 | 풀리는 시각 |
|---|---|
| 장중 거부(437730 형) | 거부 뒤 다음 sync(최대 15분 + 최소 경과) |
| NXT GTP 08:50 자동취소 | ≈09:45 첫 sync |
| KRX 15:30 정규장 미체결 자동취소 | ≈15:40 (행 모양 표본 없음 — kind 는 `cancelled` 또는 `zero` 로 찍힐 것) |
| NXT 애프터 잔존·20:00 이후 | 대상 아님(21:30 reset) |

## 3. 마커

| 마커 | 레벨 | 형식 | cap |
|---|---|---|---|
| `[buying_reconcile]` | WARNING | `ticker= strategy= odno=<o[,o]> kind=rejected\|cancelled\|auto_cancel\|zero ord= rjct= cncl= age_s= amount=<int\|-> db=<affected\|error>[,…] release_n=` | 없음(해제 1건 = 1줄) |
| `[buying_hold]` | 사유별 | `ticker= strategy= reason= odno=<o[,o]\|-> age_s=<int\|->` | `KstDailyEmitCap` 1회/(ticker, reason)/일(사유를 키에서 빼면 사유 전이가 먹힌다 — cycle258 #4) |
| `[buying_reconcile_error]` | ERROR(`logger.exception`) | 본체 예외 | 없음 |

- `kind` = `rjct>0`→rejected · `cncl_cfrm_qty>0`→cancelled · `sll_buy_dvsn_cd_name` 에 「자동취소」→auto_cancel · 그 밖→zero. **관측 전용**(판정에 안 쓴다).
- `[buying_hold]` 레벨 — **WARNING**(조사 신호) = `held` · `fill_seen` · `not_found` · `bad_row` · `ambiguous_owner` · `age_unknown`. **INFO**(정상 상태) = `open_order` · `too_young` · `no_order_no` · `lookup_error` · `deferred` · `raced`. 쉬고 있는 지정가 매수(`open_order`)가 매일 WARNING 을 내면 21:30 `top_patterns` 가 오염된다.
- 🔴 `held`·`fill_seen` 은 「pending 이 남은 채 실제로는 체결됐다」 = **체결통보 유실로 포지션이 등록되지 않았을 수 있다**(그 경우 sync 입양도 `is_ticker_held_by_any` 가 pending 을 보고 건너뛴다 = 손절 사각). 이 사이클은 **유지만** 하고 입양 경로는 안 바꾼다(cycle331 별건 권고 소관). 메시지에 그 뜻을 적는다.
- cap 실패는 `observer_trace.trace_observer_failure`.

**D+1 판독**

1. `[buying_reconcile]` 1줄마다 KIS 행이 있어야 한다. `kind=rejected` 는 cycle374 이후 같은 `order_no` 의 `[order_rejected_notice]` 가 앞선다 — 없으면 조사.
2. `[buying_hold] reason=held|fill_seen` = 즉시 그 종목 잔고·포지션 대조(위 손절 사각).
3. `not_found` 가 반복되면 주문번호 형식 불일치 의심(그 경우 기능이 죽을 뿐 위험은 없다).
4. 같은 종목 `release_n>=2` = 거부 루프. 원인(VI·단일가·거래정지류)을 보고 캡 필요 여부를 사용자 결정으로 올린다.

## 4. 테스트 목록 (≥15)

신규 `tests/unit/engine/test_cycle379_buying_reconcile.py`(freezegun 대신 `now` 주입 · caplog 는 `set_level(logging.INFO, logger="src.engine.buying_reconcile")` + 접두 필터 · `get_daily_orders`·`update_trade_status` 는 모듈 경로 patch · 파일 autouse 로 `reset_buying_reconcile_state()`)

| # | 시나리오 | 기대 |
|---|---|---|
| T1 | **거부 행**: 437730 형(`ord1 ccld0 rmn0 cncl0 rjct1 ord_tmd=094829`), now 10:00 | 해제: pending·amount·`_pending_buy_orders[o]` 제거, `_order_qty/_strategy/_ticker/_exchange/_division` **보존**, `update_trade_status(..., CANCELLED, strategy=, order_no=o)` 1회·`match_partial` 미전달, `[buying_reconcile] kind=rejected release_n=1` WARNING |
| T2 | **GTP 자동취소 행**: 073240 형(`GTP매수자동취소*`, 전 칸 0, `ord_tmd=082934`), now 09:45 | 해제, `kind=auto_cancel` |
| T3 | 취소확인 행(`cncl_cfrm_qty=ord`) | 해제, `kind=cancelled` |
| T4 | **부분체결 뒤 취소**: 행 `ccld1 rmn0 cncl1`, holdings 에 t 1주 | 유지 `held`, 변이 0, 주문번호 조회 0회 |
| T5 | 같은 행인데 holdings 비어 있음(잔고 지연) | 유지 `fill_seen` WARNING, 변이 0 |
| T6 | **열린 주문**: 자기 행 `rmn1` / (b) 자기 행은 0 인데 전체 목록에 같은 종목 다른 주문 `rmn>0` | 둘 다 유지 `open_order` INFO |
| T7 | **보유 종목**: 자기 행 전 칸 0 + holdings qty>0 | 유지 `held`, `get_daily_orders` 호출 0(유일 후보일 때) |
| T8 | **행 없음**: 조회 결과 `[]` / 같은 odno 인데 `sll=01` / 다른 pdno | 셋 다 유지 `not_found`, 변이 0 |
| T9 | **매핑 없음**: pending 에만 있고 `_pending_buy_orders` 에 t 없음 | 유지 `no_order_no`, KIS 호출 0 |
| T10 | 나이 경계: ord 09:55:01 / now 10:00:00(299초) → 유지 `too_young`; 정확히 300초 → 해제 | 경계 포함(`>=`) |
| T11 | `ord_tmd` 가 `""` / `"9A0000"` / now+120초 | 유지 `age_unknown` |
| T12 | **await 경합 A**: 주문번호 조회 mock 의 side_effect 가 그 사이 체결을 흉내(pending discard + 포지션 등록) | 유지 `raced`, `update_trade_status` 0회 |
| T13 | **await 경합 B**: 조회 중 같은 종목 두 번째 odno 가 `_pending_buy_orders` 에 생김 | 유지 `raced`, 변이 0 |
| T14 | **재진입 허용**: T1 해제 직후 `registry.is_ticker_blocked_for_buy(t) is False`, `sold_today`·`buy_blocked_until`·`low_funds_tickers` 불변, `is_max_positions` 슬롯 1 회복, `_calc_used_funds` 가 amount 만큼 감소 | — |
| T15 | **never-raise**: (a) 전체 목록 예외 → 전원 `lookup_error` (b) 주문번호 조회 예외 → 그 후보만 `lookup_error` (c) `update_trade_status` 예외 → 메모리 해제 유지 + `db=error` (d) `registry.all()` 예외 (e) holdings 원소에 속성 없음 (f) 수량 칸 `""`·`"abc"` → `bad_row` | 전부 예외 미전파 |
| T16 | 한 종목 주문 2개: 하나 종결·하나 `rmn>0` → 유지 / 둘 다 종결 → 둘 다 pop + CANCELLED 2회 + 마커 1줄 `odno=a,b` | — |
| T17 | `ambiguous_owner`: t 가 두 전략 pending 에 | 유지, KIS 호출 0 |
| T18 | hold cap: 같은 (t, too_young) 두 번 → 1줄 / 사유 전이 (too_young→open_order) → 2줄 / 다음 날 `now` → 다시 1줄 | — |
| T19 | 후보 0(모든 pending 비어 있음 또는 A 에서 전부 탈락) | `get_daily_orders` 호출 0 |
| T20 | 조회 상한: 연결 주문 12개 → 주문번호 조회 10회, 나머지 `deferred` | — |
| T21 | 해제 3회차 같은 종목(동일 날) | `release_n=3`, 행위 제한 없음 |
| T22 | SOR 2행(같은 odno): 수량 합·`ord_tmd` 최대로 판정 | 하나라도 `rmn>0` 면 유지 |

배선·API·구조:

- `tests/unit/engine/test_cycle379_sync_wiring.py` — W1 pending 있을 때만 leaf 호출(없으면 미호출) · W2 `holdings` 가 같은 `get_balance()` 결과 객체 · W3 selling 위임 **뒤** 순서.
- `tests/unit/api/test_cycle379_daily_orders_odno.py` — 기본 호출 params 15키 byte 동일(`ODNO==""`) · `odno="0000454500"` 가 `ODNO` 로만 간다.
- `tests/unit/ast/test_cycle379_ast_buying_reconcile.py` — G1 leaf import 에 `src.realtime`·`src.api.order`·`src.engine.{order_engine,risk,strategy_registry,session,scanner}` 0 · G2 `write_log`·`create_task`·`execute_buy|execute_sell|place_order|cancel_order` 토큰 0 · G3 변이는 `pending_buys.discard` · `pending_buy_amounts.pop` · `_pending_buy_orders.pop` 셋뿐, `_order_qty|_order_strategy|_order_ticker|_order_exchange|_order_division|sold_today|buy_blocked_until|low_funds_tickers|_completed_buy_orders` 참조 0 · G4 `update_trade_status` 호출에 `order_no=` 있고 `match_partial` 없음 · G5 재검증과 변이 사이 `await` 0(C 블록) · G6 scheduler 호출이 `reconcile_stale_selling` 뒤 · `scheduler.py` < 3,900.
- 이름 축 등록 — `test_cycle290_ast_scope.py::_ENGINE_PY_FILES` 에 leaf 추가 · `test_cycle287_ast_scope.py::_SRC_TREE_FILES`(159→160)·`_SRC_TREE_DIGEST` · `balance.py` sha(cycle287 핀) · `scheduler.py` 전체 sha 핀(≈20파일) — **값만** 재핀 + 사유 주석.

## 5. 돌연변이 목록 (≥12, 각 KILL 테스트)

| M | 돌연변이 | 잡는 테스트 |
|---|---|---|
| M1 | 행 없음을 해제로(부재 기반) | T8 |
| M2 | A2 `held` 삭제 | T4 · T7 |
| M3 | B8 `fill_seen` 삭제 | T5 |
| M4 | B7 자기 행 `rmn>0` 검사 삭제 | T6a |
| M5 | B2 종목 전체 열린 주문 검사 삭제 | T6b |
| M6 | `<` → `<=`(경계) 또는 B10 삭제 | T10 |
| M7 | 나이 출처를 `ord_tmd` 대신 0/now 로 | T10 · T11 |
| M8 | C 재검증 삭제 | T12 · T13 |
| M9 | 해제 때 `_order_strategy`·`_order_qty` 도 pop | T1 · G3 |
| M10 | CANCELLED 호출에 `match_partial=True` | T1 · G4 |
| M11 | `order_no=` 인자 삭제 | T1 · G4 |
| M12 | `pending_buy_amounts.pop` 삭제 | T1 · T14 |
| M13 | 연결 주문 첫 번째만 pop | T16 |
| M14 | 빈 문자열을 0 으로 읽기(`int(x or 0)`) | T15f |
| M15 | hold cap 키에서 reason 제거 | T18 |
| M16 | 본체 try/except 제거 | T15 |
| M17 | 해제 때 `sold_today.add(t)`(재진입 차단) | T14 · G3 |
| M18 | 행 매칭에서 `sll_buy_dvsn_cd`·`pdno` 필터 제거 | T8 |
| M19 | 조회 상한 제거 | T20 |
| M20 | scheduler 호출을 selling 위임 앞으로 | W3 · G6 |

## 6. 롤백

- **1커밋 revert**(leaf · scheduler 4줄 · `balance.py` kw · 테스트 · 재핀) → **full 배포**(`src/` 변경 = backend 재시작)를 장외 창에만: 15:30~16:00 · 21:35~익일 07:45 · 주말. 20:00~21:35 금지, 보유 중 09:00~15:30 금지(D6).
- 되돌릴 데이터 없음 — CANCELLED 로 적힌 행은 KIS 사실(체결 0·잔량 0)과 일치하므로 그대로 둔다. 마이그레이션 0.
- 장중 킬스위치는 없다(§2.4). 판단이 틀린 해제가 의심되면 그날은 D+1 판독 규칙으로 기록하고 장외에 revert 한다.

## 7. 반례 · 한계

- **잘못 풀 수 있는 유일한 경로** = KIS 가 살아 있는 주문을 5분 넘게 `rmn=0 ∧ ccld=0` 으로 보고하는 경우. 알려진 메커니즘이 없다. 그래도 벌어지면 매핑을 남겨 두었으므로 늦은 체결은 올바른 전략·수량으로 포지션이 선다. 남는 위험 = 그 사이 같은 종목을 재진입했다면 늦은 체결의 `_handle_buy_fill` 이 `pending_buys` 를 **종목 키로** 지워 새 주문의 pending 까지 지운다(카드 E `(ticker, order_no)` 키 전환이 닫는다 — E 착지 시 이 leaf 의 pop 자리도 함께 바꾼다).
- **이전 날짜의 좌초 PENDING 행**(전 기간 12행 중 437730 을 뺀 11행, 04-22~07-06)은 이 leaf 가 안 건드린다(메모리 pending 이 없는 행이다) — 재매수 시 `mark_pending_buys_completed` 가 여전히 유령 COMPLETED 로 뒤집을 수 있다(기존 결함, 범위 밖).
- 사용자가 MTS 로 같은 종목을 보유하고 있으면 `held` 로 그날 계속 유지된다(보수 방향, 21:30 reset).
- KRX 15:30 자동취소 행의 실제 모양은 표본이 없다 — 양성 증거 규칙(두 칸이 명시 0)만 맞으면 kind 와 무관하게 풀린다.
- 코호트가 드물다(8거래일 1건). 첫 실측 해제가 몇 주 뒤일 수 있다 — 무발화를 결함으로 읽지 않는다.

## 8. 후속 (tdd-engineer / tester)

1. Red 는 T1·T8·T4·T12 를 먼저 — 「양성 증거 · 부재 비해제 · 보유 유지 · 경합」 네 축이 이 설계의 전부다.
2. PG 통합 1건 권고: 실 Postgres 에 PENDING·PARTIAL·COMPLETED 행을 같은 종목으로 심고 CANCELLED 호출이 **PENDING 한 행만** 바꾸는지.
3. 배포는 묶음 D 계획대로 09-28 실측 뒤 장외 창(가장 빠르면 09-28 21:35). 문서 = `src/engine/CLAUDE.md` 모듈 맵(selling_reconcile 옆) · 규칙 4 「알려진 비용」 · `_sync_positions_from_balance` 줄 · `_workspace/00_leader_trading_rules.md`(예산·슬롯 회수 = 매매 행위 변경) · 워크리스트 · changelog.
