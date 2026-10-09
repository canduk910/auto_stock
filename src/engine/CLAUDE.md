# CLAUDE.md — src/engine/ (매매 엔진)

다중 전략 아키텍처(`StrategyBase` 추상 클래스 플러그인). **지금 동작하는 규칙만** 적는다.

> 이력: [`docs/history/src-engine-CLAUDE.history.md`](../../docs/history/src-engine-CLAUDE.history.md)
> 전략 7개 상세: [`src/engine/strategies/CLAUDE.md`](strategies/CLAUDE.md)
> 사이클별 변경 이력: [`docs/HARNESS_CHANGELOG.md`](../../docs/HARNESS_CHANGELOG.md)

> **DB 접근** = 전 엔진 모듈이 `src/db/pg.py`(asyncpg) 헬퍼 경유 — `scheduler`(auto_start·trade_history·strategy) · `boot_manager`(strategy 조회 · PENDING BUY 일괄 COMPLETED · 오늘 BUY 조회) · `log_metrics_collector`(`_fetch_logs_in_range` 페이징). auto_start = `system_config.get_auto_start`/`set_auto_start`. 상세 = [`src/db/CLAUDE.md`](../db/CLAUDE.md).

## 모듈 맵

한 줄 = 모듈의 **현재 역할 · 공개 API · 불변식 · 금기**. 사이클 번호는 값의 출처 표기로만 쓴다.

### 매매 흐름 축

- **`strategy_manifest.py`**(cycle398 카드 #2·#3) — 전략 등록 7행(클래스·id·이름·초기 켜짐·비중 + 원형 칸 `eval_driver`·`breakout_rank`·`open_price_target`·`close_at_1520`·`market_unit_policy`)의 **유일한 정본**. 전부 필수 칸(기본값 없음) — 하나라도 빠뜨리면 import 시 `TypeError` 또는 `_validate_manifest()` 의 `ValueError`(조용한 무매매 대신 기동 실패). `scheduler.__init__` 는 `STRATEGY_MANIFEST` 를 순회해 등록할 뿐이고(for 문 7줄), 새 전략 추가·등록 순서 변경은 이 모듈에 행을 더하는 것이다. 등록 순서 = `risk.on_tick` 평가 순서 = 같은 틱 매수 우선순위(golden = `tests/unit/engine/test_cycle398_strategy_wiring_golden.py`). 파생 집합 여섯(`SWING_POLL_IDS`·`BREAKOUT_IDS`·`BREAKOUT_SUBSCRIBE_ORDER`·`OPEN_PRICE_TARGET_IDS`·`CLOSE_AT_1520_IDS`·`MARKET_UNIT_SCALE_IDS`)이 `scheduler.py` 의 옛 리터럴 7자리를 대신한다 — 값·순서는 그대로다. `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 는 **리터럴로 유지**하고(사용자 결정 B, risk 가 명부를 import 하지 않게) `SWING_POLL_IDS` 와 교차 검사만 한다(`tests/unit/engine/test_cycle398_strategy_manifest.py`). `open_price_target`(시가 목표가)과 `close_at_1520`(15:20 강제청산)은 지금 값이 둘 다 VB·LTV 로 같지만 **독립된 칸**이다 — 합치지 않는다(ETF 가 `close_at_1520` 만 켜고 `scheduler.py` 를 다시 열지 않을 수 있게). `market_unit_policy` 는 지금 선언 + 교차 검사일 뿐 행위가 없다(시장 유닛 적용은 각 전략 `calc_buy_quantity`/`check_buy_signal` 안 명시 호출이 정본). 표준 라이브러리 + 전략 7파일 + `strategy_base` 만 import(src import 순환 0 — 이 모듈을 import 하는 곳은 `scheduler.py` 하나뿐이다).
- **`strategy_base.py` / `strategy_registry.py`** — 전략 추상 + 등록·비중 배분·중복 매수 가드. 매수 수량 관문 `_apply_budget_limit` 계약 정본 = 루트 [`CLAUDE.md`](../../CLAUDE.md) 「핵심 안전 규칙」. 하단 전용 절.
- **`strategies/`** — 7 전략(`momentum` · `volatility_breakout` · `long_tail_volatility` · `donchian_swing` · `bull_flag_breakout` · `vcp_breakout` · `kojiro`). 매수·청산·보드 명세 = `strategies/CLAUDE.md`.
- **`session.py`** — `MarketBoard` · `SessionTracker`. `is_call_auction_now(now=None) -> bool` = H0UNMKO0 `MKOP_CLS_CODE`(110 장전 / 121 장후) **AND** 명목창 ±5분(110: 08:25~09:05 / 121: 15:15~15:35) + 시간 기반 폴백, `now or datetime.now(_KST)`. 🔴 코드 단독 판정 금지 — 전환 코드가 안 오면 `_last_nxt_mkop_code` 가 고착해 보유 종목 stale 탐지(손절)가 꺼진다. 가드 `test_cycle182_call_auction_time_gate.py` · `test_cycle182_call_auction_ast_gate.py`. 시간표 = 하단 `session.py` 절.
- **`risk.py`** → **`order_engine.py`** → **`scheduler.py`** — 틱 판정 → 체결통보·DB 영속화 → 시간 가드·run/settle. 하단 전용 절.
- **`boot_manager.py`** — `_boot` 본체. **await 없이** 띄우는 백그라운드 태스크 셋 = ① 토큰 발급(`token_manager.get_token()`) 직후 `daily_bar_finalize.spawn(phase="boot")` → prepare 직전 `wait_for_boot`(「전일 잠정 봉 확정」 배선) ② 익일청산 복구 직후 `funnel_capture.spawn_funnel_boot_vs_evening(scheduler, phase="boot")`(「funnel 스냅샷 캡처」 ④) ③ 그 바로 뒤 `account_cluster.spawn_boot_assign(scheduler, summary.net_asset)`(cycle404 「계좌 묶음 배정 기록」, `try/except Exception` 으로 감싼다 — 실패해도 부팅을 막지 않는다). `_load_strategy_config` 직후 `portfolio_risk.check_budget_invariant` → `[budget_invariant_violation]` WARNING. 활성 전략 준비 = `funnel_capture.live_prepare_one(strategy, phase="boot")`(never-raise, 호출부 try 없음).
- **`scanner.py`** — 스캔·구독·`STATIC_TICKER_NAMES` · 적재 4종(`_stock_master_daily_load_once` · `_stock_master_basics_refresh_once` · `_stock_master_master_load_once` · `_stock_master_financial_load_once`) · 매수 진입 차단 `_is_master_blocked_for_entry` · 채널 리졸버 `tick_tr_id_for`. 적재 = 하단 「저녁 데이터 적재」, 구독 = 하단 `scanner.py` 절.

### stale 계열 (K stale watcher)

- **`stale_tracker.py`** — `StaleTrackerState`.
- **`stale_manager.py`** — facade, re-export only(`__all__`).
- **`stale_diagnostics.py`** — 진단 · CCNL 캐시 · force_retry history prune. `STALE_FRESHNESS_SECS = 60`(KIS LMS chain 안전 마진, G-SAFETY-1) · `SUBSCRIBE_GRACE_SECS = 180`(= 3 × freshness, 구독 직후 ACK grace). 🔴 `tick_channel_switch` 원복 probe 가 **재사용**(재정의 금지).
- **`stale_session_recovery.py`** — silent inactive 감지 · 세션 강제 reconnect · delta unsubscribe(임계·cap = `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」). **세션 상대 판정** — 판정 가능 세션(`subscribed >= 5`) ≥ 2 이고 전부 `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` = **시장 침묵** → 그 사이클 기각 + 판정 가능 전 라벨 `first_seen` pop(누적 후 필터 금지 — 재개 순간 지각 세션 즉발). 하나라도 fresh = 발화, 판정 가능 < 2 = 현행(fail-open). 관측 = `[silent_inactive_market_wide_skip] transition=entered|persisting|exited`. 🔴 기각 판정에 시간창 리터럴·`tradable_boards`·`session` import 금지 — 세션 간 비교만이 15:30~15:40 갭까지 닫는다(AST G-241-5).
- **`stale_universe_guard.py`** — 보유·익일청산 절대 보호 universe guard. `evaluate_universe_guard` + wrapper `_evaluate_universe_guard`(하단 `scheduler.py` 절).
- **`stale_watcher_core.py`** — `check_and_resubscribe_stale`(120초) + `resubscribe_stale_priority`(5분, LOW desired = breakout ∪ momentum 교집합, HIGH 구조적 면제). `check_and_resubscribe_stale` 판정 순서:
  - ① grace `_is_within_grace(t)` — `t in ticker_last_tick` = False · `ack_at` 비 datetime = False · 예외 = 안전 폴백. ACK 키 = **채널 무관 역인덱스** `ack_at_by_ticker`(채널 고정 키면 전용 채널 종목이 grace 를 영구 miss → 재등록 폭주).
  - ② `SessionTracker.is_call_auction_now()` 참 → **LOW-scoped skip**(cycle371): stale ∩ HIGH(보유·익일청산)는 `unsubscribe_in_pool`→`subscribe(priority="HIGH", bypass_limit=True)` 강제 재등록, stale ∩ LOW 만 SEND 0·retry 무변경. 🔴 HIGH skip 금지 — 동시호가 창(08:30~09:00, 110 코드면 08:25~09:05) 보유 재구독 정지 = 005935 사고 패턴. `[stale_skip_call_auction] subscribed= low= high=` WARNING 매 사이클(HIGH stale 없으면 retry 보존 + 조기 반환 → `is_no_feed` 판정 0회, W9 `test_cycle252_stale_watcher_no_feed.py::test_w9_...`).
  - ③ no_feed skip — `subscribed` 확보 직후 `no_feed_registry.ensure_fresh(subscribed ∪ 보유·익일청산)`(try/except). `LOW ∧ is_no_feed(t) ∧ (킬스위치 off ∨ 실제 구독 채널 ∉ DEDICATED_TICK_TR_IDS)`(priority 결정 직후 · `retry > MAX_STALE_RETRIES` 비교 직전) → `r` 증가·`r>5` 홀드(`MAX+1`)만 하고 `continue`(SEND·스탬프·history 0). `r` 증가 = `stale_universe_guard` 저유동 축출 경로 보존. 🔴 **HIGH 는 skip 대상 아님**(틀리면 손절 커버리지를 잃는다).
  - `[no_feed_held] tickers=[…] evidence=[…]` WARNING 1회/일(cycle393 — 사용자 결정 7) — **두 증거 다리가 모두 측정됐을 때만** 말한다. cohort(`high_tickers ∩ is_no_feed(t)`) 계산은 동시호가 LOW-scoped 조기 반환 **뒤**(`high_tickers` 자체는 재등록 우선순위·동시호가 HIGH 판정에도 쓰여 그 분기보다 먼저 계산된다)이고, `subscribed` 와 함께 실제 측정·emit 은 `_observe_no_feed_held(cohort, subscribed, now)` 가 한다.
    - **W** — `tick_volume.get_observed_acml_vol(t) is None`(오늘 KST WS 체결 기록 부재). `ticker_last_tick` 은 쓰지 않는다 — 멀티데이 REST 폴(`_run_swing_rest_poll_once`→`on_tick`)이 그 값을 찍어 donchian·kojiro 보유는 거짓 음성, 거래 없는 저유동 보유는 거짓 양성이 된다(기각 대안, AST A1 이 폐포 안 참조 0 을 잠근다).
    - **R** — `src.api.quotation.inquire_acml_vol(t, market="J")` 를 seam `_probe_krx_acml_vol`(모듈 전역, `real_no_feed_probe` 마커 없는 테스트는 conftest 가 None 스텁으로 중립화)로 `NO_FEED_PROBE_INTERVAL_SECS`(600초) 간격 두 번 읽어 늘었는가. 한 번만 읽으면 재기동·장전 누적을 "체결"로 오판한다. 상태 기계(종목별, 모듈 전역, KST 날짜 자기 리셋) = 기준 없음→읽어 기준 저장 / 간격 전→대기 / 간격 경과→증가면 증분 저장, **동일 또는 감소면 기준은 그대로 두고 시각만 이동**(F1 — 일중 누적거래량 감소는 이상값이라 기준을 내리면 다음 정상 읽기가 "증가"로 오판된다) / 증분 확인 뒤 `NO_FEED_CONFIRM_SECS`(=`STALE_FRESHNESS_SECS`=60초) 더 지나고 W 가 여전히 참이면 **확정**. W 가 거짓(기록 생김)이거나 cohort·구독 이탈이면 그 종목 상태를 **지운다**(구독 공백이 끼면 "구독 중 체결" 증명이 깨진다).
    - **창** = KRX 정규장 K3 `[개장+NO_FEED_OPEN_GRACE_SECS(180초), 종료)` — `market_state.get_market_table` 의 KRX·REGULAR 행에서만 얻는다(시각 리터럴 신설 0). **표 조회 실패는 창 안으로 본다**(cycle357 "시각 게이트 실패는 억제하지 않는다" 승계) — 반대로 **REST 실패·타임아웃·예외는 말하지 않는다**(상태 무변경, 다음 사이클 재시도, cap 미소비). 두 실패 방향이 다른 이유 = 시각 게이트는 호출 수를 줄이는 장치일 뿐이고 증거 다리는 메시지의 진실성 그 자체이기 때문이다. 확인 대기는 창을 벗어나도(예: 15:20 직후) 같은 KST 날짜면 진행한다(REST 재조회 없음).
    - **배치** — `_observe_no_feed_held` 는 **두 출구**에서 `await` 한다: ①「모두 fresh」 조기 반환 분기(`return` 직전, cycle252 T1 의도 보존) ②`emit_stale_session_detail(...)` 호출 **뒤**(HIGH 재등록 루프가 끝난 다음) — REST 대기가 그 사이클의 HIGH 재등록(손절 시세 복구)을 늦추지 않는다. 사이클당 REST 읽기 ≤ `NO_FEED_PROBES_PER_CYCLE`(=4, 정렬 순, 남은 종목은 다음 사이클). 관측기 예외는 전부 흡수(`[no_feed_held_observe_failed]` debug 흔적, `CancelledError` 는 안 막음).
    - `[no_feed_held_probe] ticker= phase=baseline|traded|flat|decreased|failed vol= prev_vol=` INFO — REST 읽을 때마다 1행(확정 전 단계가 조용히 도는 것을 D+1 에 관측하는 용도, 2일 보관). `decreased` = 누적거래량이 직전 기준보다 낮게 읽힌 이상값(F1) — 기준은 유지, 시각만 이동. 🔴 판정에 `ticker_last_tick` 금지 — REST 폴이 찍는다(위 W 참조).
  - `[stale_watcher_summary]` 끝 필드 ` no_feed_skipped=%d`. 판독 = `no_feed_skipped`·`[stale_force_retry]` **감소** = 성공, `[no_feed_held]` **0** = 정상(증거 두 다리가 선 KRX 전용 보유가 없으면 0행이 정상이다). 🔴 이 마커들과 `[tick_coverage] stale` 은 2026-09-14 채널 분리 배포 전후, **그리고 `[no_feed_held]` 는 cycle393 배포 전후** 로그를 합산하지 않는다 — 판정 기준 자체가 다르다(경위 = 이력).
  - 🔴 금기 = no_feed 종목을 stale 집계에서 **빼서** 숫자를 좋게 만들기. `resubscribe_stale_priority`(5분)는 no_feed 무관(후보 소스 `ticker_last_tick` 에 프레임 0 종목은 없다).
  - **두 재등록 경로는 종목 단위 진행 표식으로 서로 배제한다(cycle408)** — 120초 경로와 5분 경로는 다른 task 라 잠금이 없다. 한쪽이 종목을 해제하고 `subscribe` 를 기다리는 사이 다른 쪽이 같은 종목을 해제하면 풀 매핑이 비어 `unsubscribe_in_pool` 이 메인 세션으로 폴백하고, 메인이 들고 있지 않은 종목에 UNSUBSCRIBE 를 보내 KIS `OPSP0003 not found` 가 난다. 모듈 전역 `_RESUB_INFLIGHT` 를 해제 지점 3곳(force_retry · 1~5회 · 우선 재구독 블록) 바로 앞에서 `_claim_resub` 로 세우고, 이미 서 있으면 그 종목은 이번 회차를 건너뛴다(`[stale_resub_inflight]` DEBUG 만, 우선 재구독은 결과·`_stale_last_resubscribe_at` 에 넣지 않는다). 해제는 `finally` 의 `_release_resub` 한 곳이다. 🔴 `finally` 를 지우지 않는다 — 표식이 남으면 그 종목 재등록이 영구히 멈춘다(보유 종목이면 손절 시세 복구가 멈춘다). 🔴 claim 과 첫 `await`(해제 또는 구독) 사이에 `await` 를 두지 않는다 — 원자성의 근거다. 🔴 대기(`asyncio.Lock`)로 바꾸지 않는다 — 두 주기 경로가 서로를 기다리게 된다. HIGH 인자(`priority="HIGH", bypass_limit=True`)는 그대로이고, 건너뛰는 때는 다른 경로가 같은 종목을 같은 HIGH 인자로 재등록 중일 때뿐이다. 가드 = `tests/unit/engine/stale_manager/test_cycle408_resub_inflight.py`.
- **`sell_rejection.py`** — `SellRejectionTracker`. 2단계 TTL 진입 게이트 계약 정본 = 루트 `CLAUDE.md` 「핵심 안전 규칙」.
- **`selling_reconcile.py`** — `scheduler._sync_positions_from_balance` 의 stale `_selling` 재대조 leaf. `reconcile_stale_selling(order_engine, holdings, *, min_age_s, now=None)` — 유지 3분기 `held_zero`(보유 0) · `open_order`(일별 주문 `sll_buy_dvsn_cd=01 ∧ rmn_qty>0` — `get_daily_orders()` 기본 `exchange="ALL"` 이 NXT 잔존 매도까지 잡는다. 🔴 좁히지 않는다 — NXT 주문이 걸린 채 `_selling` 이 풀려 같은 종목을 두 번 판다) · `too_young`(`elapsed_s < min_age_s`=180s) + `[selling_hold] ticker= reason= elapsed_s=` WARNING 1회/(ticker,reason)/일, 그 외 해제. `get_daily_orders` 예외 = 유지. 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정(`system_logs` grep 사슬).
- **`buying_reconcile.py`** — 같은 sync 의 매수 pending 회수 leaf(`selling_reconcile.py` 대칭, 8영역·`scheduler` import 0, cycle379). 거래소가 접수 뒤 끝낸 매수(거부·취소·GTP 08:50 자동취소·KRX 15:30 정규장 미체결 자동취소)가 잡은 **슬롯·예산·진입권** 회수. `reconcile_stale_buying(registry, order_engine, holdings, *, min_age_s=BUYING_RECONCILE_MIN_AGE_S, now=None, max_lookups=MAX_ORDER_LOOKUPS_PER_PASS)`. 상수 `BUYING_RECONCILE_MIN_AGE_S = 300` · `MAX_ORDER_LOOKUPS_PER_PASS = 10` · `ORD_TMD_FUTURE_TOLERANCE_S = 60`.
  - 🔴 **양성 증거로만 푼다**(오해제 = 예산 이중 사용 · 같은 종목 2랏 · `max_positions` 초과). 해제 조건 넷 — ① 그 종목 **모든** 연결 주문(`order_engine._pending_buy_orders` 중 `ticker` 일치)의 자기 행을 `get_daily_orders(target_date=오늘, odno=o)` 로 찾음(`odno`·`pdno` `strip()` 비교, `sll_buy_dvsn_cd=="02"`) ② Σ`tot_ccld_qty`==0 ③ Σ`rmn_qty`==0(둘 다 명시값 — 빈 값·비수치 = `bad_row`) ④ `now − max(ord_tmd)` ≥ `min_age_s`(경계 포함, `ord_tmd` = 오늘 날짜 + KST). 여러 행(SOR) = 수량 합 · `ord_tmd` 최댓값.
  - **유지 사유** — 메모리 단계(KIS 0): `ambiguous_owner`(2전략 이상 pending) · `held`(어느 전략이든 `has_position` · KIS 잔고 >0 · 잔고 파싱 실패) · `no_order_no`(연결 주문 0 = `await place_order` 창·매핑 유실). 후보가 다 빠지면 KIS 미호출. KIS 단계: `lookup_error` · `open_order`(자기 행 `rmn_qty>0`, 또는 오늘 목록에 같은 종목 매수 `rmn_qty>0` — 수동 MTS 포함) · `deferred`(패스당 조회 상한 초과) · `not_found` · `bad_row` · `fill_seen`(Σ`tot_ccld_qty`>0) · `age_unknown`(`ord_tmd` 부재·형식 오류·`now`+60초 초과 미래) · `too_young` · `raced`.
  - **해제 = 3필드뿐** — 마지막 `await` 뒤 동기 `_release_if_unchanged` 재확인(pending 소유 전략 그대로 하나 · 누구도 미보유 · 연결 주문 집합 동일) 통과 시 `pending_buys.discard` · `pending_buy_amounts.pop` · `_pending_buy_orders.pop(o)`(`_handle_buy_fill` 첫 체결 경로와 같은 셋). 🔴 `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 **남긴다**(늦은 체결통보가 올바른 전략·수량 `qty_src=map` 으로 포지션을 세운다, 21:30 reset 이 치움). `sold_today`·`buy_blocked_until`·`low_funds_tickers`·`_completed_buy_orders` 무접촉 — **같은 날 재진입 허용**(사용자 결정 2026-09-27, 기존 가드만 적용).
  - **장부** — 해제 뒤 연결 주문마다 `update_trade_status(t, BUY, CANCELLED, strategy=, order_no=o)`(`match_partial` 미전달 → PENDING 행만). 🔴 CANCELLED 필수 — 재진입 보유가 생기면 다음 sync `mark_pending_buys_completed(t)` 가 남은 PENDING BUY 를 COMPLETED 로 뒤집어 유령 체결이 된다. DB 예외 = 마커 `db=error`, 메모리 해제는 되돌리지 않는다.
  - **마커** — `[buying_reconcile] ticker= strategy= odno= kind=rejected|cancelled|auto_cancel|zero ord= rjct= cncl= age_s= amount= db= release_n=` WARNING 무cap(해제 1건 1줄, `kind`·`release_n` 관측 전용) · `[buying_hold] ticker= strategy= reason= odno= age_s=` 1회/(ticker, reason)/일(`KstDailyEmitCap`; WARNING = `held`·`fill_seen`·`not_found`·`bad_row`·`ambiguous_owner`·`age_unknown`, 그 밖 INFO) · `[buying_reconcile_error]` ERROR(예외 흡수, `CancelledError` 전파). logger = `src.engine.buying_reconcile`, `write_log` 0(영속 = 루트 `_DbLogHandler`).
  - ⚠️ **판독** — `held`·`fill_seen` = pending 이 남은 채 실은 체결됐을 수 있다(통보 유실이면 sync 입양도 `is_ticker_held_by_any` 로 건너뛰어 손절 사각 — 입양 경로는 「발사 창 귀속」 별건 권고 소관). 같은 종목 `release_n>=2` = 거부 루프. `kind=rejected` 앞에 같은 주문번호 `[order_rejected_notice]` 가 없으면 조사.
  - 🔴 **오해제 유일 경로** = KIS 가 살아 있는 주문을 `min_age_s` 넘게 `ccld=0 ∧ rmn=0` 으로 보고(알려진 메커니즘 없음) + 그 사이 재진입 → 늦은 체결의 `_handle_buy_fill` 이 `pending_buys` 를 종목 키로 지워 새 주문 pending 까지 지운다. 닫는 것 = `pending_buy_amounts` 키를 `(ticker, order_no)` 로 바꾸는 카드 E(이 leaf 의 pop 자리도 함께).
  - 명세 = `_workspace/red/cycle379_buying_reconcile_spec.md` · 회귀 = `tests/unit/engine/test_cycle379_{buying_reconcile,sync_wiring}.py` · `tests/unit/api/test_cycle379_daily_orders_odno.py` · `tests/integration/test_cycle379_buying_reconcile_pg.py` · 가드 = `tests/unit/ast/test_cycle379_ast_buying_reconcile.py`.

### 관측·공통 헬퍼

- **`metrics_collector.py`** — `make_metrics_collector(*, prefix, summary_keys, int_keys, str_keys, accumulate_keys, use_last) -> (record_fn, flush_fn, collector_list)`. 빈 윈도우 flush skip, 누적/단일 행 = `use_last`. facade 4종이 위임.
- **`stock_master_metrics.py` / `stock_master_basics_metrics.py` / `stock_master_daily_metrics.py` / `stock_master_master_metrics.py`** — 위 팩토리 re-export facade. flush 는 `scheduler.py` 에서 **1회 이상** 호출(G-AST1).
- **`task_loop_helper.py`** — `run_periodic_task_loop(...)`. 계약 = 하단 「정기 task 루프」.
- **`data_load_tasks.py`** — 저녁 적재 task loop 본체 8종(`scan_pool_eager_refresh_loop` / `full_universe_load_task_loop` / `stock_master_daily_load_task_loop` / `stock_master_basics_refresh_task_loop` / `stock_master_master_load_task_loop` / `stock_master_financial_load_task_loop` / `evening_funnel_capture_task_loop` / `stock_master_daily_purge_task_loop`). 인자 = `scheduler` + `wait_time` kwarg(TIME_* 는 wrapper 가 넘긴다 — 순환 import 회피), `scheduler.py` 는 2줄 위임 wrapper. 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정. `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000` · `_full_universe_below_immediate_floor` 도 여기(「정기 task 루프」). 가드 `test_refactor_b1_data_load_tasks.py`.
- **`funnel_capture.py`** — 라이브 전략 준비의 **단일 입구** + 저녁 미리보기 본체. 공개 API(전부 **never-raise**) = `resolve_as_of(now_kst, mode) -> AsOf | None` · `live_prepare_one(strategy, *, phase) -> bool` · `live_prepare_many(strategies, *, as_of, phase) -> {"prepared", "failed"}` · `capture_skip_reason(strategy, label, today, *, is_provisional) -> str | None` · `evening_capture_once(scheduler) -> dict` · `emit_funnel_boot_vs_evening(scheduler, *, phase="boot")` · `spawn_funnel_boot_vs_evening(scheduler, *, phase="boot") -> asyncio.Task`. 🔴 8영역 import 0 · naive 벽시계 0(가드 `tests/unit/ast/test_cycle364_ast_live_prepare_lock.py`) — 보호 종목은 scheduler 의 registry·`_pending_next_day_clear` 에서. `scheduler`(TIME 상수·`capture_funnel_snapshots`)·`trading_calendar` = 함수 안 지연 import. 계약 = 하단 「funnel 스냅샷 캡처」.
- **`trading_calendar.py`** — 휴장일 판정 공용 leaf(8영역·`scheduler.py`·`boot_manager.py` import 0). 소비 = 슬롯 게이트(`task_loop_helper._evaluate_slot_gate`) · 6전략 prepare 일봉 신선도(`StrategyBase._resolve_expected_daily_head`) · 저녁 미리보기 기준일(`funnel_capture.resolve_as_of`·`evening_capture_once`).
  - API 4개(**never-raise**, 예외 → `None`): `is_open_day(d) -> bool | None` · `previous_trading_day(today) -> date | None`(엄격히 이전 최근 개장일, 최대 `_PREVIOUS_TRADING_DAY_LOOKBACK_DAYS`=10 달력일, 도중 `None` = `None`) · `next_trading_day(d) -> date | None`(엄격히 뒤 최근 개장일, 최대 `_NEXT_TRADING_DAY_LOOKAHEAD_DAYS`=14 달력일, 도중 `None` = `None`) · `latest_passed_trading_slot(now_kst, slot) -> datetime | None`(`now` 이하 「개장일 D 의 `slot` 시각」 중 최근, KST aware, `now.time() >= slot` 이면 오늘부터).
  - seam = 모듈 전역 `_lookup_open(d)` — 호출 시 `src.api.condition.is_trading_day`(KIS CTCA0903R, True 개장 / False 휴장 / None 모름) 지연 import.
  - 메모 = 모듈 전역 dict 에 **True/False 만 영구**(주말 `weekday() >= 5` = 조회 없이 휴장). `_MEMO_MAX_AGE_DAYS`(40일) 초과 키는 **삽입 날짜 기준** 정리(벽시계 기준 금지). KIS 「CTCA0903R 가급적 1일 1회」(`docs/kis/domestic-stock-industry.md` 국내휴장일조회) = **날짜당 프로세스 수명 1회**로 준수.
  - `None`(모름)은 `_NEGATIVE_CACHE_TTL_SECS`(90초) 동안만 `_negative_memo` 재사용. 조회 = `_LOOKUP_TIMEOUT_SECS`(5초) `asyncio.wait_for`, 타임아웃 = 모름(모르면 실행). `_reset_cache_for_tests()` 가 두 저장소를 비운다.
  - 🔴 `boot_manager._previous_trading_day` 재사용 금지 — 조회 실패를 「영업일」로 삼키는 관측용 fail-open(`is_market_open` 실패 = True)이라 「모르면 실행」을 표현 못 한다. 🔴 naive 벽시계(`datetime.now()`·인자 없는 today 계열) 금지.
  - 테스트 = autouse `tests/conftest.py::_neutralize_trading_calendar`(seam → `None` + 메모 비움, 옵트아웃 마커 `real_trading_calendar`) — 기존 테스트는 슬롯 게이트 `calendar_unknown → RUN`, prepare `expected_head=None`. 가드 `test_cycle363_trading_calendar.py` · `test_cycle363_ast_business_day_gate.py`.
- **`daily_emit_cap.py`** — `KstDailyEmitCap` = KST 날짜 경계 자기 리셋(`should_emit`/`mark_emitted(key, *, now=None)`) + `emit_once(key, log_fn, msg, *args, now=None)`(peek → 로그 → mark, `log_fn` 예외면 mark 없이 trace). **신규 관측 마커의 표준 진입점**. `count_matching(predicate, *, now=None)`(cycle348) = 오늘 키 중 `predicate` 참 개수 — **읽기 전용**(날짜 자기 동기화 선행, never-raise, 실패 0), 새 가변 전역 없이 일일 카운트(소비 `observe_macd_stage6`). `KstDailyEmitCap` 전용 — 기반 `DailyEmitCap` 은 cycle258 K-12 byte 불변.
- **`observer_trace.py`** — 관측기 자기 실패 흔적 정책 leaf. `trace_observer_failure(marker, key, cap=None, *, now=None, dest_logger=None)` = `logger.debug(exc_info=True)` **항상** + cap 이 있으면 `f"{marker} observer_failed key={key}"` WARNING **1회/(marker, key)/일**(cap 키 `marker|key__observer_failed__`), never-raise. 흔적 토큰 = `observer_failed` **하나**. `src.*` import 는 `daily_emit_cap` 뿐. 미적용 잔존(권고만, `risk.py`·`scanner.py` 는 8영역 승인 대상) = `risk.py` `_maybe_emit_pre_market_gate_divergence`(`_pre_market_divergence_day` 자기 리셋 + `except Exception: pass`) · `risk.py` `_maybe_emit_day_high_adopted` · `scanner.py` `_apply_trade_amount_filter` 의 `[trade_amount_filter_scanner_skip]` · `kojiro.py` `_is_open_risk_capped`(뒤 셋은 `mark_emitted` 가 로그보다 먼저).
- **`uptime_monitor.py`** — 가동 하트비트 + 부팅 tick blind 계측(never-raise 관측). 60초 하트비트 = `system_config.set_task_last_success("engine_alive_heartbeat")`. 부팅 시 `[tick_blind_boot] downtime_secs=… market_blind_secs=… after_market_blind_secs=… pre_market_blind_secs=…` — `market_blind_secs` = 평일 09:00~15:30 겹침(공휴일 미고려 = 과대계상), **`> 0` = WARNING**(장중 다운 = 손절 사각 실측, 분기는 이 필드만). 뒤 두 필드 = KRX 애프터 16:00~20:00 · NXT 프리 08:00~08:50 겹침(참고, cycle366). 겹침 3함수 `market_blind_overlap_secs`/`after_market_blind_overlap_secs`/`pre_market_blind_overlap_secs` → 공용 `_weekday_window_overlap_secs(start, end, window_open, window_close)`. 배선 = `boot_manager` 갭 보고 1회 + `ensure_heartbeat_loop` idempotent(scheduler 무접촉). 리포트 = `tick_blind`(`_aggregate_tick_blind`) + `report_accuracy.{after_market,pre_market}_blind_secs_total`(`_aggregate_extended_blind`). 🔴 WS 재연결 blind 는 stale watcher 소관(중복 계측 금지).
- **`refresh_progress.py`** — universe / basics / daily / master / financial **5 작업** 진행 state(모듈 전역 dict + `threading.Lock`). `start_progress` / `update_progress` / `finish_progress` / `get_progress` / `get_all_progress` / `is_running`(409 판정) / `reset_progress` / `reset_all_progress`. **10키** = `status`(idle/running/completed/failed) · `total`/`processed`/`updated`/`skipped`/`failed` · `started_at`/`finished_at`(KST `+09:00` ISO) · `elapsed_ms` · `error_message`. 🔴 `TaskKey` Literal ↔ `TASK_KEYS` tuple **2 위치 동행**(AST 가드). 🔴 process-local 이라 uvicorn 단일 워커 필수.

### 순수 함수 leaf (DB · HTTP · 시계 미접촉, 8영역 미접촉)

- **`util/tick_size.py`** — KRX 7구간 호가단위 헬퍼 `get_tick_size` / `round_to_tick` / `step_down` / `step_up`.
- **`quant_score.py`** — `compute_f_score_7(curr, prev) -> int|None`(Piotroski 9지표 중 **7** — CFO 2지표 제외, 개별 결측 미가점, 2기 부족 `None`) + `compute_magic_formula(series_by_ticker, mktcap_by_ticker) -> dict`(EY = 1/`ev_ebitda`, 폴백 `bsop_prti`/EV · ROC = `bsop_prti`/((`cras`−`flow_lblt`)+`fxas`) · `mf_rank` = `ey_rank`+`roc_rank`).
- **`kojiro_indicators.py`** — `ema` / `atr`(Wilder `ewm(1/period)`) / `stage_of`(6배열 + 동가 유지) / `enrich`(EMA 5·20·40 + 스테이지 + 대순환 MACD1/2/3 + 밴드폭 + ATR). pandas, `KojiroIndicatorConfig` 주입. 🔴 **ATR = Wilder `ewm(1/20)` ≠ donchian `_atr`/`get_atr`(단순평균)** — 손절선 정의라 상호 재사용 금지.
- **`etf_trend_core.py`** — ETF 추세 전략(`etf_trend`, cycle403) 순수 leaf. 표준 라이브러리(`math`·`typing`)만 import 한다(`src.*` import 0 · I/O 0 · `await` 0 · 로깅 0). 지표 `ema`·`true_ranges`·`atr_wilder`·`n14`·`breakout_line`·`tv20`·`tv_prev20` · 진입 판정 `entry_signal`(→ `EntrySignal`)·`gap_skip_reason` · 청산선 `hard_stop`·`stop_line`·`channel_low`·`breakout_failed` · `simulate_exit` · 묶음 상관 `return_correlation`. 식의 정본 = 재현 스크립트 `_workspace/domain_consult/cycle391_etf_s0_remeasure.py` — 기간 기본값(20·14·10)은 재현 측정값이라 바꾸면 측정 밖이다. 소비 = `strategies/etf_trend.py`(전략 규칙 = `src/engine/strategies/CLAUDE.md`).
- **`ta_indicators.py`** — `rsi(closes, period=14) -> float|None`(Wilder, all-gains 100 / all-losses 0 / flat 50 / `len < period+1` None) + `relative_strength(stock_closes, index_closes, period=20) -> float|None`(종목 − 지수 N일 수익률 %p). 🔴 **시리즈 ASC 기대**(`get_recent_daily` 는 DESC — 호출자가 뒤집는다). 🔴 `kojiro_indicators` 의 `ema`/`atr` 재사용 금지.
- **`te_metrics.py`** — `compute_te_rr(pairs, *, now, window_days=90, strategy_id="", costs_available=True) -> TeRrMetrics`(29필드 = 기본 19 + 실비용 10). 입력 = `get_trade_pairs`(진입가 기준 `profit_rate`). 모집단 = `status=='closed' ∧ sell_date ≥ now − window_days`. `te_pct` = `profit_rate` 단순평균(`compute_metrics` 매도가 기준 재사용 금지) · `win_rate` = W/N(보합 포함) · `rr` = `avg_win`/|`avg_loss`|(전승 또는 `min(W,L) < 5` → None) · `required_rr` = L/W · `sample_tier`(N<20 / 20-49 / 50+) + `rr_available` + `verdict` + `structure_tag` + `single_trade_dominant`. 소비 = `GET /api/strategies/te`(5분 캐시). 관찰 전용.
  - **판정 = 순손익 기준(cycle411, 사용자 결정 10-08 Q2)** — 판정(win/loss·`te_pct`·`te_krw_avg`·`rr`·`verdict`, 위 필드들)은 페어의 `net_profit_rate`/`net_profit_loss`(순손익)가 있으면 그 값을 쓰고, 없는 페어는 그 페어만 세전 값으로 폴백한다(`_core(population, rate_fn, pl_fn)` 를 net/gross 두 번 돌린다). 페어에 net 칸을 얹는 쪽은 `cost_overlay.overlay_pairs` 다(`/api/strategies/te` 가 `compute_te_rr` 호출 전에 부른다).
  - **실비용 10필드** — 세전 판정 `te_pct_gross`·`te_krw_avg_gross`·`win_rate_gross`·`rr_gross`·`verdict_gross` + 세전 승/패 수 `win_gross`·`loss_gross`(= `gross_core["win"/"loss"]`, 빈 모집단 0) + `realized_net_sum_krw`·`fee_sum`·`tax_sum`. `realized_sum_krw` 는 세전 합 그대로다(의미 불변).
  - **세후 합계 3칸이 `None` 인 경우 둘** — 「모름」 을 0 이나 세전 값으로 채우지 않는다. ① `costs_available=False`(호출부의 비용 조회가 실패·예외) ② 모집단 안에 net 칸이 있는 페어와 없는 페어가 섞였을 때(`mixed_net_state` — `costs_available` 과 무관). 판정 자체는 두 경우 모두 페어 값 그대로 계산한다. 빈 모집단은 `_empty_metrics`(세 칸 0.0).
- **`turtle_sizing.py`** — `compute_unit_qty(budget, atr, risk_pct, fraction=1.0)` = `floor(예산 × risk_pct ÷ ATR)` + `compute_unit_qty_guarded(...)` = 변동성 floor(`atr/price < min_vol_pct` → 0 = `position_ratio` 낙하) + 잔여예산 클램프 + **notional 상한** `min(qty, int(예산×position_ratio)//price)`(= 「**터틀 수량 ≤ 비중 수량**」 항등). 호출 = 전략 `calc_buy_quantity` 뿐. 🔴 `max_lot_units`(K) 캡도 `fraction=K` 로 **재사용**(새 수식 금지).
- **`portfolio_risk.py`** — `extract_hard_stop_pct(params, *, default=-7.0)`(후보 7키 `stop_loss_rate` / intraday / overnight / main / pre_nxt / `turtle_backstop_pct` / `hard_stop_pct` 중 **음수만** min, 결측 −7.0 fail-open, 0.0 금지) + `compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of) -> dict`(프록시 = `buy_price × qty × |hard_stop%| / 100`, `by_strategy`(0 포지션 포함) / `by_sector`(보유분만) / `top_sector` / `open_risk_pct_of_net`) + `check_budget_invariant(strategies) -> list[dict]`(`params.position_ratio × params.max_positions > 1.0 + 1e-9` 위반, 결측·0 이하·예외 skip). **입력 무변경.** 소비 = `GET /api/portfolio/risk` · 리포트 `portfolio_risk_snapshot` · `boot_manager`. 🔴 AST 가드 = 8영역의 `portfolio_risk` 참조 0 + 이 파일의 `_kojiro_sector_key`/`trading_scheduler`/registry/db import 0. ⚠️ **Σweight ≤ 1.0 축은 안 본다**(라우트 Σ 가드 + `[weight_config_anomaly]`).
- **`position_exit_lines.py`** — 잔고 화면 **청산선(손절가·목표가) 단일 진실원**. `resolve_exit_lines(strategies, ticker) -> {strategy_id, stop_price, stop_source, target_price, target_source}` + `build_exit_line_map(strategies, tickers)`. **순수·read-only·never-raise·`await`/DB/HTTP 0**. 소비 = `routes/balance.py`(실패해도 잔고는 나가고 전 종목 `—`). 보유 전략 미상(수동 매매분) = 전 필드 `None`.
  - 손절선 2단 = `get_effective_stop_price`(보유형 4전략, `check_exit_signal` 과 **동일 산식·상태 소스**) → `hard_pct`(`buy_price × (1 + 하드손절%/100)`). 🔴 `extract_hard_stop_pct` 기본값 −7.0 으로 만든 숫자 금지 — sentinel 로 **키가 실제로 있을 때만**(설정한 적 없는 손절가를 운영자가 믿는다).
  - 🔴 **`_MODE_DEPENDENT_STOP_STRATEGIES`(= LTV) = `hard_pct` 근사 없이 `stop_source="mode_dependent"`** — 보유 중 모드(당일 `intraday_stop_loss` / 상한가 `overnight_stop_loss`)가 갈려 음수 min 이 느슨한 쪽을 내고, 모드(`_limit_up_reached` 메모리)는 leaf 가 모른다. 미러를 붙이면 `account_risk_watcher` SOFT 게이트 입력이 바뀌므로 **`domain-consult` 선행**(별건).
  - 🔴 **목표가 = read-only 미러 `get_effective_target_price(ticker) -> (target, already_hit)` 에서만** — `get_targets_status()` 는 `_candidates` 순회라 보유 종목(후보 자격 상실이 정상)의 목표가가 간헐적으로 사라진다. 🔴 목표가는 `bull_flag_breakout` `measured_target` 하나(**부분 익절 트리거**). ⚠️ VB·LTV `target_price` = **매수 트리거 가격** — 목표가로 쓰지 않는다. 🔴 가격 무관 청산(VB 15:20 일괄매도 · kojiro stage3 · 익일청산)은 어느 출처에도 없다(프론트 툴팁 안내).
  - 🔴 **`engine_running=False` → `stop_source="engine_idle"`** — 21:30 `_reset_daily_state` ~ 07:45 `_boot()` 약 10시간은 보유가 있어도 청산선을 모른다(「없음」과 「모름」을 같은 `—` 로 접지 않는다). ⚠️ 판정 = **엔진 상태**(`trading_scheduler.is_running`), 「메모리 포지션 0」 추론 금지(수동 매수분만 든 정상 상태가 정지로 찍힌다).
  - 회귀 = `tests/unit/engine/test_cycle339_position_exit_lines.py`(🔴 후보 표면을 읽으면 붉어지는 **양성 대조군** 포함).
- **`position_buy_date.py`** — 잔고 화면 **매입일(최초 매입일) 단일 진실원**(cycle397, 사용자 요청 2026-10-02). `resolve_engine_buy_dates(strategies) -> {ticker: ISO}`(**순수·read-only·never-raise·`await`/DB/HTTP 0**) + `merge_buy_date(engine_iso, db_value) -> ISO|None`(두 출처 중 **더 이른 날짜**). 소비 = `routes/balance.py` — 1순위 엔진 포지션 `Position.buy_date`, 2순위 DB `positions.buy_date`(`db/positions.get_buy_dates`, 엔진 정지·수동 보유의 폴백). 🔴 불확실하면 `None`(오늘 날짜로 채우지 않는다). 🔴 **같은 전략의 동일 종목 추가 매수(피라미딩)는 `is_ticker_blocked_for_buy` 가 막고 있어 `Position.buy_date` 자체가 이미 최초 매입일이다** — 그 제약이 풀리면 이 모듈의 "최초" 규약을 `trade_history` 기반으로 재검토해야 한다. 회귀 = `tests/unit/engine/test_cycle397_position_buy_date.py` + `tests/contract/test_cycle397_balance_buy_date.py`(보유 11종목 칸이 비지 않는지 직접 확인).
- **`sector_naming.py`** — 보유 종목 섹터명 **단일 진실원**. `resolve_sector_name(ticker, *, basics_raw=_UNSET)` + `resolve_sector_names(tickers)`. 우선순위 = basics raw `bstp_kor_isnm` → `_kojiro_sector_key(master_raw)`(KRX 산업지수 플래그 → 업종코드) → `미분류-{ticker}`(fail-open). `basics_raw` 주입 = `stock_master.get` 생략. 🔴 소비 3곳(`routes/portfolio.py` · `log_analysis_engine.py` · `routes/balance.py`) 전부 위임, 복제 금지(회귀 가드). ⚠️ `idx_bztp_lcls_cd_name`("시가총액규모중")은 섹터가 아니다 — 사용 금지.
- **`account_risk_guard.py`** — 계좌 SOFT Σ상한 순수 판정. `evaluate_soft_gate(open_risk_pct, *, warn_pct, block_pct) -> {level: ok|warn|block, reasons}`. **`block_pct=None` = 다크런치**(block 없음, DB `account_risk_block_pct` 한 줄로 활성, 권고 6.0). pct None·음수 = ok fail-open. DB/HTTP/registry/scheduler import 0(AST G-3). 🔴 임계를 발화시키려고 낮추지 않는다(관측 경보 4% 발화 빈도가 유일한 학습 신호).
- **`llm_features.py`** — LLM 매수평가 입력 조립 순수 함수(`src.*` import 0): `ema`(시드 = 첫 period 단순평균) · `rsi_wilder`(완전 평탄 50) · `macd` · `atr_wilder` · `hv_annualized`(ddof=1 × √252 × 100) · `channel` · `normalize_volume_ratio` · `pct_change` · `sanitize_text`(개행·`|` 제거, 종목명 20자, 주입 방어) · `compute_technicals(bars_desc, *, current_price, today_open_won=0)` · `build_messages(payload, tech, bars30)` · `snapshot_keys_for(sid)`(전략별 NA 키 제거, `_SNAPSHOT_KEYS` 순서). `_STRATEGY_META` = **7 전략**(`name`/`entry_rule`/`matters`). 스냅샷 = 화이트리스트 `_SNAPSHOT_KEYS` 만(설정값·datetime 유출 차단). 🔴 `json.dumps` 는 try **밖**(조용한 `{}` 폴백 금지 → `reason=payload_error`). `meta.schema_version="cycle276.1"`. ⚠️ `_SNAPSHOT_KEYS` 변경 = `llm_buy_gate._prompt_version()` 해시 변경(가드 `test_c30_2b/2c`). 단가 상수는 `log_analysis_engine.py` 와 이원화(후속 F-274-3).
- **`llm_retrospective.py`** — 주간 회고 조인·집계 순수 함수(`src.*` import 0 · I/O 0 · `await` 0). `join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date)` + `aggregate(rows, *, cost_pct)`. 🔴 매칭 축 = **`(order_no, trade_date)`**(KIS `ODNO` 는 하루 단위 유일). `primary` = 첫 매수 주문(`buy_order_nos[0]`) 평가. 🔴 평가 없는 페어를 버리지 않는다(분모 = 커버리지). 손실 = `profit_rate <= cost_pct`(기본 0.25, 경계 포함). 소비 = `GET /api/llm-evaluations/retrospective`.
- **`market_state.py`** — 장운영상태 **단일 정본**, 순수 데이터 leaf(`src.*` import 0 · I/O 0). `MARKET_TABLE` 13행(KRX K1~K7 · NXT N1~N6) = 시각 구간별 `order_divisions`·`phase`·`match_kind`·`effective_from/to`(날짜 차원 내장 — 제도 변경이 `effective_from` 으로 자동 전환). `ORDER_DIVISIONS` 28코드(명칭·거래소 지원·`confidence` ∈ `confirmed`/`name_unconfirmed`; 27~29 NXT GTP · 41~47 KRX 애프터마켓 = KIS 공지 2026-09-09 원문 `confirmed`, `docs/kis/domestic-stock-order.md` `ORD_DVSN` 칸과 일치 필수) + `FINDINGS` 3행(SOR 폐기 각주 포함). 소비 = `GET /api/market-state` · `order_engine._route_exchange_by_clock`(이 표만 읽는다 — `order_engine.py` 시각 리터럴 0) · `tick_channel_clock`. ⚠️ 변경 시 `python tools/test_fixtures/gen_market_state_fixture.py` 재생성(`test_cycle282_fixture_sync.py::test_i1/i2`). 🔴 **`EXCHANGE_ORDER` 의 SOR 열 삭제 금지** — 「KIS 가 그 호가유형을 그 거래소에서 받는가」 사실 표라 지우면 41~47 SOR 지원 **확인 필요** 사실까지 사라진다(가드 `test_cycle287_sor_retired.py::test_n4`/`test_n4b`); 안 쓰는 것은 **각주**로. `GET /api/market-ops`(`routes/market_ops.py`)는 `scheduler.TIME_*`/`quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` 직접 판독(이 표 무관). ⚠️ 신규 `src/**/*.py` = `test_cycle287_ast_scope.py::test_s1b`(`_SRC_TREE_FILES` + `_SRC_TREE_DIGEST`)가 잡는다 — `_PINNED_DIRS`/`test_s1d` 를 근거로 인용하지 않는다(양변이 디스크 산출이라 공허). 상세 = `src/routes/CLAUDE.md`.
- **`param_catalog.py`** — 7 전략 `DEFAULT_PARAMS` 합집합 **105 키 단일 진실원**, 순수 데이터 leaf(`src.*` import 0 · I/O 0 · 로드 부작용 0). 키마다 `ParamSpec`(`label_ko`/`group`/`type`/`min`/`max`/`step`/`unit`/`editable`/`risk`/`auto_tunable`/`deprecated`/`deprecated_for`/`range_src`/`pattern`/`choices`/`applies_to`/`help`/**`min_items`**/**`forbidden_choices`**).
  - 리스크 정체성 키(`risk="identity"` · `range_src="enum"` · `auto_tunable=False`) — 킬스위치 `order_exchange_clock_mode`·`after_market_exit_division`(`group="time_board"`) · 시장 유닛 `market_unit_mode`(`group="sizing_risk"`, `applies_to` = 터틀 4전략, cycle382) · 신규 매수 멈춤 `buy_paused`(`group="entry"` · `type="bool"`, `applies_to` = 7 전략, cycle384) · 섀도 모드 `shadow_mode`(같은 모양, cycle399).
  - 🔴 **범위를 지어내지 않는다** — `range_src` ∈ `clamp`(읽는 쪽 하드 클램프 6) · `param_ranges`(`PARAM_RANGES` 원문 복사 24) · `sign`(부호 규약 6) · `structural`(자료형·구조 필연) · `enum`(값 집합) · **`none`(근거 없음 → min=max=None, 8키 — 전부 `deprecated=True ∧ editable=False`)**. ⚠️ `PARAM_RANGES` 파생은 그 범위가 실제 운영값을 담을 때만(아니면 그 키 저장 전면 422). `auto_tunable` = `PARAM_RANGES` 그대로, 넓히지 않는다(AI 자동 조정 ≠ 사람 편집).
  - `deprecated`(8, 전부 `editable=False`) = 숨기지 않고 회색 배지. 전략 한정 무효 = `deprecated_for`(유일 사례 `k_value_nxt_pre`/`_post` → VB; LTV 는 야간 목표가에 **실제로 곱한다**).
  - `min_items`(list_str 최소 항목 — `tradable_boards`=1 · `exclude_tickers`=0)·`forbidden_choices`(전략별 금지 선택지 — 유일 사례 VB + `post_nxt` = 루트 `CLAUDE.md` 'POST_NXT 추가 금지')는 검증·화면 공통 근거라 카탈로그에 둔다. ⚠️ 빈 목록을 자료형 단위로 막지 않는다(`exclude_tickers=[]` = 정상 기본값 '제외 없음').
  - `trailing_stop_rate` 도움말 = 적용 범위 명시(cycle365) — momentum·LTV 둘 다 **익일 청산 모드**(갭 ≥ `gap_up_threshold` 유지)에서만, 당일 손절엔 미사용(LTV 는 전일 상한가 도달 종목 한정).
  - `exchange` `SOR` = `Choice(deprecated=True)` + 라벨 `"SOR (폐기 — 주문에 쓰이지 않음)"`. 어휘 삭제는 `test_cycle287_sor_retired.py::test_n3b` 순서(코드 → D+1 → 카탈로그/프론트 → DB)의 별도 작업. 🔴 `exchange` 는 `editable=True` 유지(`False` 면 그 키를 보내는 모든 PUT 422). `<select>` `<option>` 엔 `choice.deprecated` 회색이 안 닿아 **라벨이 유일한 폐기 신호**(프론트 회귀 가드가 봉인). 두 PUT 클라이언트(`Settings.tsx`·`StrategyParamsEditor`)는 변경분만 보낸다.
- **`param_validation.py`** — 파라미터 검증 순수 함수(`param_catalog` 만 import). `validate_params(strategy_id, current_params, incoming) -> ValidationResult(errors, warnings, accepted)`. 순서 = 키 존재 → `editable` → 자료형 → `choices`/`pattern` → 금지 선택지(`forbidden_choice`) → min/max · 최소 항목 수(`too_few_items`) → 예산 불변식(병합 결과) → 순서 불변식(경고). 🔴 **첫 오류에서 멈추지 않는다**. 예산 불변식 `position_ratio × max_positions <= 1.0` = EPS=1e-9 로 경계 1.0 **통과**, **이미 위반 중인 상태를 악화시키지 않는 편집 = 통과 + `budget_invariant_preexisting` 경고**(막으면 복구가 DB 직접 UPDATE 뿐). 빈 `tradable_boards` = **422**(효과가 정반대 — momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS` 폴백 매수, BFB·VCP·kojiro 는 매수 전면 중단; 매수 멈춤 수단 = `buy_paused`, 비활성화는 손절까지 멈춘다 — 루트 금기). VB + `post_nxt` = **422**. ⚠️ `applies_to` 는 PUT 관문 **아님**(의도된 fail-open — 미지 키 판정 = `key in current_params` 라 DB 드리프트 키는 저장, 매매 영향 0, 조이면 비상 `curl` 롤백 경로가 좁아진다). 소비 = `routes/strategies.py::update_params`. AI 자문 수동 적용(`routes/recommendations.py`)은 미경유(검증 비대칭).
- **`param_drift.py`** — 운영 DB params ↔ 코드 `DEFAULT_PARAMS` 드리프트 **관측 전용** 순수 leaf(`src.*` import 0 · I/O 0). `collect_param_drift(strategies) -> list[{strategy_id, key, live, code}]` — `config.params` vs `DEFAULT_PARAMS` 키별(수치 `4`=`4.0`(`_same`, 오차 1e-9), bool `is`). **코드에 없는 키는 안 센다**(운영 전용 키 = 배경 소음). 판정 불가·예외 skip. 소비 = `boot_manager.boot` 가 `_load_strategy_config` 직후 1회 → 차이 `[param_drift] count=N` WARNING(예시 5건) / 없음 INFO / 실패 `logger.exception` 후 부팅 계속. 🔴 **값을 바꾸지 않는다**(DB 가 정본, 차이 대부분은 운영자 의도). 회귀 = `tests/unit/engine/test_cycle326_param_drift_visibility.py`.
- **`etf_like.py`** — ETF/ETN(류) 판정 **단일 진실원**. 표준 라이브러리만 import(`db/stock_master.py` SQL 빌더가 같은 상수를 읽는다 — `scanner.py` 에 두면 8영역 import 가 끌려온다).
  - 공개 = `ETF_GROUP_CODES = frozenset({"EF", "EN", "FE"})`(KIS CTPF1002R #7 `scty_grp_id_cd` — ETF·ETN·해외ETF) · `ETF_KEYWORDS`(이름 키워드 25개, **폴백 전용**) · `is_etf_like(raw, name) -> bool`.
  - 판정 = `raw` Mapping ∧ `scty_grp_id_cd` strip 후 비지 않음 → **코드만**(strip+upper ∈ `ETF_GROUP_CODES`, 이름 무시). 코드 없음(`raw` None·비 Mapping·키 없음·None·빈 값·공백) → 이름 키워드 부분일치(대소문자 구분). `raw` 무변경.
  - 소비 셋 = `stock_master.list_by_filter(exclude_etf_like=True)` SQL 판정(상수 공유) · 6 전략 `_scan_universe` 루프(SQL 뒤 방어 겹) · `scanner.scan_stocks`(momentum).
  - 🔴 **momentum 은 이름 폴백만** — 원천 KIS 등락률 순위(`FHPST01700000`) 행에 `scty_grp_id_cd` 가 없다. 키워드에 안 걸리는 ETF(KIWOOM·TIME·1Q 등)는 이 경로에서 안 막힌다.
  - RT·FS·DR·IF·MF 는 ETF 아님(시총·거래대금 컷을 넘으면 유니버스 편입).
  - 🔴 판정 재구현 금지 — `ETF_KEYWORDS` 순회는 이 파일·`stock_master.py` SQL 빌더 두 곳뿐(G1) · 전략 파일 `ETF_KEYWORDS` 비참조(G2) · `stock_master.py` 코드·키워드 문자열 재기재 금지(G6) · `order_engine._observe_after_exit_etp` 코드 집합과 동일(G7 표류 감시). 가드 = `tests/unit/ast/test_cycle380_ast_etf_like.py`.
- **`market_breadth.py`** — 시장 등락 통계 판정·집계 leaf(cycle416 — 사용자 요청 10-07·10-09). **관찰 전용 — 매매 경로가 읽지 않는다**(소비 = `routes/market_breadth.py` 하나, AST G-416-5). 표준 라이브러리만 import · `await`·`async def` 0 · 벽시계(`now`·`today`·`utcnow`·`monotonic`) 호출 0 — 오늘·지금은 호출자가 인자로 넘긴다(G-416-1). 그래서 호가단위 표 `KRX_TICK_TABLE_20230125` 는 `util/tick_size.py::_TICK_BANDS` 와 값이 같은 별도 사본이다.
  - 행 판정 `classify_row(row) -> RowClass` — 입력은 KRX 일별 매매정보 한 줄이고 숫자는 쉼표 섞인 문자열이다(`parse_krx_int` — `None`·`""`·`"-"`·소수·읽기 실패 → `None`). 순서 = 종가·대비·거래량 중 하나를 못 읽거나 종가 ≤ 0·거래량 < 0 → `unparsed`(어느 칸에도 세지 않는다) → 거래량 0 → `no_trade` → `CMPPREVDD_PRC` 부호로 `up`/`down`/`flat`. 🔴 상승·하락은 `FLUC_RT` 가 아니라 **대비 부호**로 가른다 — 둘의 부호가 어긋나면 `sign_mismatch` 로만 세고(응답에 싣지 않는다) 라우트가 `[market_breadth_sign_mismatch]` WARNING 을 남긴다.
  - 상한가·하한가 = 종가가 기준가 `base = 종가 − 대비` 의 가격제한폭 값(`price_limits(base)`, ±`PRICE_LIMIT_PCT`=30)에 닫힌 종목. 제한폭 `w` = 기준가 30% 를 기준가 호가단위로 절사 · 상한가 = `base + w` 를 **그 가격대 호가단위로 한 번 더 절사** · 하한가 = `base − w`(추가 절사 없음). 그날 저가·고가가 그 밴드를 벗어나면 `out_of_band` 로 세고 상·하한가로 세지 않는다. `base ≤ 0` 이거나 고가·저가를 못 읽으면 상·하한가 판정만 건너뛴다.
  - 집계 `aggregate_rows(rows) -> DayStats` · 두 시장 합계 `merge_stats(a, b)`(정수는 더하고 `up_ratio` 는 합계 숫자로 다시 계산 — 평균이 아니다) · 여러 날 요약 `summarize(days) -> SummaryStats`(`adr = round(Σup ÷ Σdown × 100, 1)`, Σdown 0 → `None`) · 직렬화 `stats_to_dict`(날 11키 · 요약 9키, `sign_mismatch` 제외). `rows = traded + no_trade`(`unparsed` 제외) · `up_ratio = round(up ÷ traded, 4)`(traded 0 → `None`).
  - 날짜 창 — `candidate_weekdays(today, days)` = 오늘을 뺀 평일을 최신부터 `lookback_calendar_days(days) = max(MIN_LOOKBACK_CALENDAR_DAYS(=40), 2 × days)` 달력일까지 · `is_publish_pending(d, d1, now)` = 가장 최근 평일 `d1` 이고 지금이 그 다음 평일 `PUBLISH_PENDING_CUTOFF`(10:00 KST) 전 · `classify_day(kospi, kosdaq) -> DayStatus` = 한쪽이라도 `None`(호출 실패) → `MISSING` · 둘 다 행 > 0 → `TRADING` · 둘 다 0 → `EMPTY`(휴장) · 한쪽만 0 → `MISSING`. 상수 `DEFAULT_DAYS`=20 · `MIN_DAYS`=1 · `MAX_DAYS`=60 · `ADR_REFERENCE`=`{oversold: 75, overheated: 120}`(업계 통상 기준선 — 판정 문구로 쓰지 않는다).
  - 정의 정본 = `_workspace/red/cycle416/breadth_spec.md` §2~§5 · 회귀 = `tests/unit/engine/test_cycle416_market_breadth_leaf.py` · 구조 가드 = `tests/unit/ast/test_cycle416_ast_market_breadth.py`.
- **`backtest_yaml.py`** — 전략 → 외부 MCP 백테스트 YAML DSL. `build_yaml(strategy_id, params)` 변환 = `momentum` · `volatility_breakout` · `donchian_swing` 셋, 그 밖(LTV·BFB·VCP·kojiro 등) = `BacktestNotSupportedError`. 유일 import 처 = `backtest_engine.py`(20:00 자문 INSERT 직후 자문 행마다 `current`·`recommended` 2 job fire-and-forget, 미지원 = `skipped`). hot path 무관.

### 시세 채널 (통합 채널 소멸 후)

채널 규칙(구간표 · 층별 폴백 · 전환 창 · 자동 원복 · 운영 다이얼 4키 · 폐기 키 재사용 금지 · `off` 가 되돌리지 못하는 것) 정본 = `src/realtime/CLAUDE.md` 「시세 채널」. 여기는 엔진 모듈 계약만.

- **리졸버 `scanner._resolve_channel`** — 입구 `scanner.tick_tr_id_for(ticker, *, priority, now)`. 판정 = 시각축(`tick_channel_clock.clock_channel`) × 속성축(`scanner._classify_channel`). 시각축이 `H0STCNT0` 이면 속성축 **미호출** → KRX 연속체결 창(정규장+애프터)은 `nxt_tradable` 무관 전 종목 `H0STCNT0`; `nxt_tradable` 이 채널을 가르는 것은 시각축 `H0NXCNT0` 프리 창(+ 자동 원복 래치일)뿐. 속성축 통합 반환 = NXT 로 흡수. 프리 창 `nxt_false` 를 KRX 채널에 두는 근거 = **전환 횟수**(걷으면 프리 창 KRX 프레임(K2 08:30~08:40 장전 시간외 종가 — 전일 종가 고정)과 전환 감소분만 잃는다).
- **`tick_channel_mode.py`** — 리졸버 **킬스위치 모드 leaf**(`system_config.tick_channel_resolver_mode`). `current_mode()`(동기, hot path) · `refresh_mode()`(async) · `apply_mode(mode)`(라우트 즉시 메모리 반영) · 테스트 seam 2. 🔴 `refresh_mode()` 에 프로세스당 1회 래치 금지(래치면 킬스위치가 아니다). 🔴 **장중에 닿아야 한다**(D6 보유 중 장중 재시작 금지 · D8 20:00~21:35 금지 → 「다음 재시작 반영」 = 「못 끔」) — 즉시 경로 `PUT /api/realtime/tick-channel-mode`(DB 저장 + 같은 요청에서 메모리 덮기), 폴링 백업 `scanner.subscribe_filtered_stocks`(5분) · `stale_watcher_core.check_and_resubscribe_stale`(120초). DB 조회 실패·키 부재·미지 값 = **현재 값 유지**(기본값 되돌림 금지) + 미지 값 `[tick_channel_mode_invalid]` WARNING. 시각 리터럴 0. 헬퍼 = `src/db/system_config.py`.
- **`tick_channel_clock.py`** — **시각축 판정 leaf**(동기·순수·never-raise, `await`/DB/HTTP 0, AST G-294-14). `_windows(on_date)` → `(krx_regular_open, nxt_pre_end, krx_continuous_end)` · `switch_at(on_date, *, offset_secs)` · `clock_channel(now, *, offset_secs)` → `(tr_id, reason)` · `set_day_revert()`/`day_reverted()`(자동 원복 래치, 날짜 경과 자기 해제 — 🔴 시계를 못 읽어도 날짜 키가 비면 안 된다: 리셋 조건이 영원히 거짓 = 영구 좌초) · `switch_windows()`/`active_switch_window()` · 관측 `emit_clock_config()`/`note_pre_window_frame()`/`emit_pre_window_frame_summary()` · `reset_state_for_test()`. 표 파생값 = **날짜 키 메모**(`risk.on_tick` 이 코호트 종목마다 호출). `clock_channel` 의 `priority` kw 는 판정 미사용(제거 = `scanner.py` 8영역 연쇄 변경). 🔴 **통합 채널 반환 금지** — 판정 실패 폴백도 `H0STCNT0`(「구독 안 함」 방향 금지). 시각 리터럴 0 · `match_kind` 선택 · 전환 시각 clamp 식 · 전환 창 `pre_to_krx` 하나 = realtime 「시세 채널」.
- **`tick_channel_switch.py`** — 살아 있는 구독의 **채널 전환 + 자동 원복 leaf**. `run_switch_cycle(scheduler, pool, *, now)` = 120초 `stale_watcher_core.check_and_resubscribe_stale` 안에서 호출(**never-raise** — 4중 안전망의 한 축). 창 밖 전환 금지와 근거 = realtime 「시세 채널」 + 아래 `tick_volume.py`. 🔴 **세션 재추첨 금지** — `websocket_pool.switch_channel_same_session` 은 `_ticker_to_session` **읽기만**(다른 세션에 떨어지면 구 세션 튜플이 영구 고아로 41 슬롯 잠식). 자동 원복 = 비교 코호트 전부 침묵이면 그 사이클 `reason=market_wide` **비결론**, 2×probe 뒤 escalation. `_revert_probe_done` = 결론적 판정에만(상한 `MAX_REVERT_PROBE_ATTEMPTS=10`). 되돌림 = make-before-break + `tick_channel_clock.set_day_revert()` + `[tick_channel_auto_revert] n= reverted= failed= …` **ERROR** 1행(`pattern_by_level` 은 WARNING 이상만 21:30 `top_patterns` 편입). 전환 대상에서 진단 프로브 튜플·비-TICK 라우팅(체결통보 등) 제외. LOW 전환 실패 = `_ticker_to_session`/`_ticker_to_tr_id` **동행 pop**(안 하면 20:00 까지 자가 치유 없는 구독 좀비).
- **`no_feed_registry.py`** — `nxt_tradable=False` 종목 집합 leaf. `ensure_fresh(tickers, *, ttl_secs=600)` = `stock_master.get_nxt_tradable_map` 1회 적재(ttl 경과·미지 ticker 유입 = 전체 재조회, 예외 = 이전 집합 유지 + `[no_feed_registry_refresh_failed]` 1회/일 + 다음 호출 재시도, `None`(마스터 부재) = no_feed 아님).
  - 그 밖 API = `is_no_feed(ticker)` · `is_provenance_ok(ticker)`(그 행 raw 에 KIS `cptt_trad_tr_psbl_yn` 키가 있는가 — `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 도장하는 창에 `TIME_PRESUBSCRIBE`(07:59)가 있어, 도장값을 믿으면 진짜 NXT 종목을 프리장 무체결 채널로 보낸다) · `is_classified(ticker)`(분류한 적 있는가 — `is_no_feed` 의 「모르면 False」는 미지·송출 정상을 접는다, 극성 불변) · `snapshot()` · `reset_state_for_test()`.
  - 🔴 출처 조회 `get_nxt_provenance_map` 은 `get_nxt_tradable_map` 과 **독립 try**(묶으면 출처 쿼리 실패일에 churn 차단까지 죽는다). 소비 2 = `stale_watcher_core.check_and_resubscribe_stale` + `scanner._classify_channel`.
  - 🔴 **구독 전에 덥힌다** — `scanner.subscribe_filtered_stocks` 가 리졸버 호출 **전** 그 사이클 대상 전체로 `ensure_fresh`(AST A22 가 순서 잠금 — 안 덥히면 07:59 사전 구독 코호트 전체 판정 불가). scheduler/scanner/realtime/registry import 0(AST G-252-1).
- **`tick_volume.py`** — 실측 누적거래량 leaf. WS `[13] ACML_VOL` → `handler._parse_acml_vol` → `on_tick(*, acml_vol=)` → `record_acml_vol`(last-write-wins) → BFB·VCP 거래량 게이트. 🔴 **`acml_vol` 은 채널별 누적 — 채널이 다른 두 값을 비교·합산하지 않는다**(전환 뒤 첫 프레임이 새 채널 누적으로 덮는 것은 의도). 전환 안전 전제 = 전환 창 프레임 구조적 0 + 이중 채널 구독 금지(하나라도 깨지면 두 누적을 번갈아 쓰는 비결정론). 소비처 추가(cycle393) = `stale_watcher_core` `[no_feed_held]` 의 WS 증거 다리(`get_observed_acml_vol`, 읽기만).

### VI · 장운영 채널 (H0UNMKO0)

- **`market_operation_monitor.py`** — H0UNMKO0 **수신·상태 추적**. `handler._handle_market_op` → `record_market_op_event(MarketOpEvent)`. 파싱·칸 기준점 정본 = `src/api/market_operation.py`(`src/api/CLAUDE.md`). 송신·구독 = 형제 `market_op_subscribe.py`.
  - 상태 **5개**, 합치지 않는다 — `_vi_active_tickers` · `_halt_active_tickers` · `_market_op_last_event` · `_vi_last_active_at` · `_halt_last_active_at`(ticker → 마지막 활성 시각). 두 수명 dict 는 **독립**(「멤버십」과 「마지막 활성 시각」을 한 구조에 넣지 않는다).
  - **판정** — VI 활성 = `_is_code_active(vi_cls_code) or _is_code_active(ovtm_vi_cls_code)`. 거래정지 활성 = `trht_yn.upper() == "Y"` **또는** `is_iscd_stat_blocking(iscd_stat_cls_code)`(종목상태 `58` 하나).
  - **수명** — 마지막 활성 프레임 뒤 `VI_ACTIVE_TTL_SECONDS`(600초) · `HALT_ACTIVE_TTL_SECONDS`(600초) 경과 = 해제(해제 프레임 보장 없음). 활성 프레임마다 시각 갱신, 명시 해제 프레임 = 즉시. 로그 `[market_op_vi_release] ticker=…` / `[market_op_halt_release] ticker=…`(수명 해제만 `reason=ttl`). 부팅 REST 시드 `seed_vi_active_from_rest` 도 시드 시각을 마지막 활성으로(장중 재기동이면 이미 풀린 종목도 들어온다). 시각 없는 활성 종목 = **발견 시각**부터 600초(무기한 유지 금지).
  - **만료 sweep = 지연 평가**(백그라운드 task 없음) — `_expire_stale_vi()`/`_expire_stale_halt()` 를 `record_market_op_event` **첫머리**와 읽기 함수가 먼저 호출(VI = `is_ticker_stale_excluded` · `get_market_op_active_tickers` · `get_vi_active_tickers` · `get_market_op_state_summary`; 거래정지 = 그 넷에서 `get_vi_active_tickers` 대신 `get_halt_active_tickers` + `get_circuit_breaker_state`). 🔴 sweep 을 기록 **뒤**로 옮기지 않는다(만료 에피소드 위 해제 프레임이 「프레임 해제」로, 새 활성 프레임이 「갱신」으로 뭉개진다). `reset_market_op_state()` = 다섯 상태 + CB 1회/일 cap 초기화.
  - **소비** — `is_ticker_stale_excluded(ticker)` = `stale_watcher_core` 두 경로(120초 · 5분)의 VI·거래정지 stale 회피. `get_circuit_breaker_state()` = **관찰 전용 휴리스틱**(사유 `_CB_REASON_KEYWORDS` **또는** `halted >= _CB_MIN_HALTED(5) ∧ halted/observed >= _CB_HALT_RATIO(0.8)`, `representative_mkop_cls_code`=005930, `halt_reasons_sample`; H0UNMKO0 에 CB 필드 없음). `get_market_op_state_summary()` = `circuit_breaker` + `iscd_stat_active_count`(**표시 집합** `_ISCD_STAT_DISPLAY_CODES = {"51","52","53","54","58","59"}` 멤버십, 55·57·00·빈값 제외). `[market_op_cb_suspected]` INFO 1회/일. 화면 = `GET /api/realtime/market-operation` → RealtimeHealth 카드.
  - 🔴 **매수 가드 미연계(표시 전용)** — `risk.on_tick` 참조 0. 관리종목(51)·단기과열(59) 청산·매수 차단 = `status_exit_watch.py` REST 판정(이 모듈 `get_last_event(ticker)` 는 **힌트 읽기만**).
  - 가드 = `test_cycle149_ast_dict_separation.py`(앞 세 dict 분리) + `tests/unit/realtime/test_cycle368_market_op_decisions.py`(수명 V·L·T, sweep 순서 R, 판정 S·D).
- **`market_op_subscribe.py`** — 종목별 H0UNMKO0 구독 **송신·배치 본체**(`subscribe_market_operation_tickers(scheduler)`). `scheduler.py` 는 5줄 wrapper `_subscribe_market_operation_tickers`, 호출부 `_scan_loop`(본체가 leaf 인 이유 = `scheduler.py` 라인 상한 **<3,900**, cycle257).
  - 규약 = HIGH(보유+익일청산)만 · **메인 세션 0건** · `bypass_limit=False` 명시 · 보조 세션 **직접** 라운드로빈(풀 API 미경유 — tr_key 단일 키 라우팅 오염 방지) · `_market_op_subs` **델타** 해제 · 소켓 `State.OPEN` 가드(미개방 = 사이클 skip + `[market_op_subscribe_skip]`) · `ConnectionClosedError` = break + WARNING 1행 · `asyncio.sleep(0.05)` · 보조 만석 = `[market_op_subscribe_no_slot]` WARNING(**메인 폴백 금지** = tick > VI) · `[market_op_subscribe_summary]` main_tick/main_total/main_over 5분 계측.
  - 🔴 **함수-로컬 import 5줄**(`ConnectionClosedError`/`State`/`MARKET_OP_TR_ID`/`MAX_SUBSCRIPTIONS` + `kis_ws`←`websocket` / `kis_ws_pool`←`websocket_pool`) **최상단 이동 금지** — 회귀 4파일의 monkeypatch 가 무력화되고 `_ws is None → return 0` 조기 반환이 부정 단언을 공허하게 초록으로 만든다. 🔴 **두 줄 분리 유지**(합치면 매 호출 ImportError = 구독 전량 미실행).
  - 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정 — 마커 5종(`[market_op_subscribe_skip]`/`[market_op_no_quote_session]`/`[market_op_subscribe]`/`[market_op_subscribe_summary]`/`[market_op_subscribe_no_slot]`) `system_logs` 접두 유지.
  - 가드 = `test_cycle292_ast_market_op_leaf.py` + `test_cycle221_ast_market_op_no_main.py`·`test_cycle214_ast_h0unmko0_pool.py`·`test_market_op_subscribe_import_path_guard.py`·`test_market_op_subscribe_socket_guard.py`(부정 단언 넷 — **양성 대조군** 동반).

### 계좌 리스크 · 관측기

- **`account_risk_watcher.py`** — 계좌 Σ오픈리스크 감시자(scheduler 무접촉 자기 종료 루프). `run_account_risk_watch_once(scheduler)` = `registry.all()` + `get_balance()` net + 전략 `get_effective_stop_price` 를 `portfolio_risk(stop_price_of=)` 로 주입 → 척도 병기 스냅샷 → guard 판정 → 순간 게이트. 🔴 **프록시 대체 금지, 병기가 계약**(실효 척도도 갭 관통 손실은 못 잡는다).
  - 배선 = boot 동기 1회 + `ensure_watch_loop` 5분(`_running` False 면 ≤60s 종료, done_callback `[account_risk_watch_loop_died]` WARNING / `[account_risk_watch_loop_exit] reason=running_false` INFO). 호출 = 항상 `run_account_risk_watch_once_guarded`(`asyncio.wait_for`, `_EVAL_TIMEOUT_SECS=300`, 런타임 부등식 `0 < T <= _WATCH_INTERVAL_SECS < _GATE_STALE_MAX_SECS`) — **TimeoutError 만** 포착 → `_gate_active=False` + 스탬프 + `level=error reasons=[timeout]` + `[account_risk_eval_timeout]` WARNING 1회/일(**0건 정상**, 1건 = hang 실측), `CancelledError` 전파.
  - **신선도 계약** — `is_soft_gated()` = `_gate_active` ∧ 마지막 평가 monotonic 경과 ≤ `_GATE_STALE_MAX_SECS`(= 3 × 주기 = 900s, 리터럴 금지 G-239-1). stale·미평가·판정 예외 = **fail-open(False)** + `[account_risk_gate] released reason=stale` 1회/일. `get_gate_state()` = `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 추가, `level` 은 마지막 평가값 보존(동결 서명 = `level=block ∧ stale ∧ !effective_gated`). fail-open 은 **LOUD** — `[account_risk_watch_failed]` WARNING 1회/일, 활성 중 실패 `released reason=eval_failure`, 타임아웃 `released reason=eval_timeout`(둘 다 cap 밖). 🔴 `gate_stale` cap 키를 `gate_block`/`watch_failed` 와 공유 금지.
  - 🔴 단일 기록자 — read 함수 `global` 금지(G-239-4), `_gate_active` 대입~스탬프 사이 `await` 0(G-239-5). 스탬프 = `_evaluated_mono`(성공·실패 공통, `_now_mono` seam). `get_gate_snapshot()`(9키 = `get_gate_state()` 8키 + `eval_timeouts_today`) **하나**를 일일 리포트(`portfolio_risk_snapshot.account_gate`, `over_cap` 과 독립 try, `is_soft_gated` 호출 금지 — read 경로가 stale cap 을 선소비하면 안 된다)와 `/api/portfolio/risk`(프론트 `PortfolioRiskCard`)가 공유. 로그 = `[account_risk_gate] transition=entered|reconfirm|released` + `[account_risk_watch]` warn/ok(1회/일), peek → 로그 → mark.
  - **D1 이원화** — 전략별 일일손실 플래그 무접촉(AST G-4 토큰 0). 소비 = `StrategyBase._account_soft_gate_blocked`(폴·래치형 5전략 = `check_buy_signal` 첫 문장 / momentum·VB = **발사 직전** — 최상단이면 block 구간 baseline 동결 → 해제 후 거짓 돌파). 🔴 청산·손절 경로는 구조적으로 차단 불가. 복구 = `POST /api/trading/restart`.
- **`kojiro_gap_observe.py`** — 고지로 갭 판정 shadow 관측(행위 0). `observe_gap(ticker, verdict, *, arg_open, prev_close, current_price, params, depth=2)` → `[kojiro_gap_observe]` 1행(14필드, 끝 `ws_collapse=blocked|allowed|-` = WS 시가였다면의 붕괴 가드 반사실): 실제 판정(`arg_open`) vs WS 캐시(`ws_open`). 호출자 = `_swing_buy_poll_loop`(KIS REST `stck_oprc`) **뿐**(`risk._TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})`). `caller` = `sys._getframe(depth)`(미지 = 원문), cap = `KstDailyEmitCap[(ticker, caller, verdict)]`, never-raise. `ws_open` 부재 `-` 정상.
- **`kojiro_band_observe.py` — `observe_macd`(cycle340, 대순환 MACD shadow)** — 원전 `docs/trading_base/이동평균선과MACD.md` §7 MACD(상·중·하) 상태 → `[kojiro_macd_observe] ticker= role= stage= gc3= bars_since_gc3= m1..m3= s1..s3= hist3= m{1,2,3}_up= all_macd_up= rule6= rule5= rule4=`(관측 전용). 행 계약 = 12원소 튜플. 근거 = `_workspace/domain_consult/cycle340_kojiro_macd.md`.
  - 🔴 **WARNING**(INFO 는 `top_patterns` 미편입·retention 2일). 값 = `_num`(소수 2자리 고정, 비수치·NaN·inf `-`) 파싱 계약(`_fmt` 금지). cap 키 `(ticker, "macd:"+role)`(band 와 슬롯 분리).
  - 배선(cycle344) = `kojiro.prepare()` 의 `_macd_observe_row(enriched, stage)` 수집 2곳(보유 stamp 직후 · `rank_raw` 확정 직후) + `observe_band` 다음 emit 1곳(추가 I/O 0). 🔴 **`gc3` = 교차 사건**(직전 봉 `macd3 ≤ sig3` ∧ 이번 봉 `>`, 상태 `m3 > s3` 로 바꾸면 발화 부풀림). 🔴 emit = `observe_band` 와 **별도 `try`** + 전용 흡수기 `absorb_macd_call_failure`(`absorb_band_call_failure` 재사용 = 오귀인, `test_g344_12`). `_macd_observe_row` = **never-raise**(폴백 튜플). 회귀 `tests/unit/engine/strategies/test_cycle344_kojiro_macd_wiring.py`.
  - **role 3종(cycle348)** = `held`(보유 stamp 직후) · `candidate`(strict entry 최종 후보) · `stage6_gc`(step6 직후, ATR 밴드 통과 ∧ 스테이지 판별 가능 **모든** 종목 중 국면6 ∧ 마지막 봉 gc3 = B6 실매매 유니버스 표본).
  - `stage6_gc` = `KojiroStrategy._stage6_gc_observe_row(enriched, stage, bar_date, prev_close, atr_val)`(step6 직후·보유 stamp 앞, `stage != 6` 이면 `_macd_observe_row` **미호출**) → **15원소**(12 + `(bar_date, prev_close, atr_val)`), gc3 교차 아니면 `None`. emit = `observe_macd_stage6(macd_s6_raw)` — `observe_macd` **다음**·`_scanned_tickers` 대입 **앞** **별도 try**(흡수기 `absorb_macd_call_failure`, M8). 행 = 같은 필드·순서 + 끝 `bar=<YYYYMMDD> close=<int> atr=<소수2자리>`(`close` = `_int_or_dash`), cap 키 `(ticker, "macd:stage6_gc")`.
  - **일일 상한 `STAGE6_GC_DAILY_LIMIT`(60)** = `_cap.count_matching(...)` 으로 그날 `(ticker,"macd:stage6_gc")` 키 수 판정(새 가변 전역 없음). 초과 = 배치 끝 `[kojiro_macd_observe] role=stage6_gc cap_reached=1 limit=60 suppressed=N` 1행(cap 키 `("-","macd:stage6_gc:summary")` 하루 1회). 수집·leaf 실패와 무관하게 매매 산출(held stamp·step7 탈락·후보 등록) **완전 동일**.
  - 판독 — 운영 100봉 창(`KOJIRO_FETCH_DAYS`) 기준이라 전체 이력 계산(cycle346 스크립트)과 섞지 않는다 · 보유 국면6 ∧ gc3 = `role=held`·`role=stage6_gc` 두 줄 · 줄 수·`rule6=1` 합계는 반드시 `role=` 로 나눈다 · 상한 60 = 안전 여유(예상 = `_workspace/domain_consult/cycle348_stage6_volume_probe.py`).
  - 회귀 `tests/unit/engine/strategies/test_cycle348_kojiro_macd_stage6.py` = 확장 전 코드(`2087ad3`) **골든**(stats·키 집합·스캔 순서·후보 키·funnel 9단계) 완전 일치.
- **`kojiro_band_observe.py`** — 고지로 후보 순위 성분①② shadow 관측. `observe_band(band_raw, ranked_final, held_only, scores=None)` → `[kojiro_band_observe]` 1행/(ticker,role)/일: `bar`(D-1 완성봉)·`exp1`(단일봉 분모)/`exp5`(직전 5봉 평균 분모)·`slope_raw`/`slope_pct`·`score` 등 12원소 + 파생 `atr_pct`/`bw_close_pct`/`bw_atr`. never-raise(`_band_observe_row`·`observe_band`·`absorb_band_call_failure` 단일 `try/except Exception`, 흔적 = `observer_trace.trace_observer_failure`) + read-only + cap `KstDailyEmitCap[(ticker, role)]`. 소비 = `KojiroStrategy.prepare()` 점수 확정 직후(실패해도 `final_prepared`/`_scanned_tickers` 무영향).
- **`open_price_observe.py`** — 시가(`[7] STCK_OPRC`) shadow 관측(행위 0). 09:05:30 VB·LTV `main` 의 `used_open`(그날 목표가 기준) vs KRX REST `stck_oprc` → `[open_source_compare]`(익일 `stock_master_daily` 와 3자 대조). throttle 5건/초, 1회/(ticker,strategy)/일, read-only(`_targets`/`_open_confirmed` 무변경). 기준가 본체 = `open_price_rest.py`.

### 행위 leaf

- **`status_exit_watch.py`** — 관리종목(51)·단기과열(59) **보유 청산 + 당일 매수 차단** leaf(cycle369). 보유 종목 REST `FHKST01010100` → KRX 정규장 창 **09:00:30~15:28** 안 전용 플래그 `Y` = `order_engine.execute_sell(t, Signal.STATUS_EXIT, sid)` 시장가 + 그날 신규 매수 = `StrategyBase._account_soft_gate_blocked` 첫 문장 차단. 최상위 import = 표준 라이브러리뿐(`condition`·`strategy_base` 가 이 모듈을 지연 import — 순환). 8영역 무수정; 접촉 = `order_engine.execute_sell`(호출) · `order_engine._selling`(읽기) · `registry.all()`·`registry.enabled()`·`registry.is_ticker_blocked_for_buy`(호출) · `scanner.ticker_prev_close`·`scanner.ticker_prices`(읽기). 계약 = 하단 「종목상태 청산·당일 매수 차단」.
- **`open_price_rest.py`** — VB·LTV `main` 목표가 기준가 = KRX REST 확정. 좁은 목 `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")` — `reject_untrusted_main_basis(params, board, source, …)` 가 `board=="main"` ∧ `source ∉ ("rest",)` ∧ `resolve_mode(params)=="enforce"`(전략별 `DEFAULT_PARAMS["open_price_scope_mode"]`, 기본 `enforce`, `"off"` 만 롤백)면 조용히 거부. 🔴 `source` 기본값 = 불신 `"ws"`(WS 3 호출부 — 스케줄러 1차 폴링·전략 인라인 확정 — 무변경, `_STRATEGY_PINS` 6개 불변).
  - 일정(`round_schedule()` 순수) = 09:00:35 R1 → 30초 간격 **fast 19라운드**(마지막 09:09:35) → 300초 slow 라운드 15:20 까지(대상 `_pending_main_tickers` 뿐). `main_rest_basis_task_loop(sched)` → `run_main_rest_basis_round(sched, round_no=, total_rounds=, kind=)`. 대상 `select_strategies(registry)` = `main ∈ tradable_boards ∧ mode=="enforce"`(`config.enabled` 미고려). 종목 간 `sleep(0.05)`, 라운드 상한 45초(`truncated=1`). 확정 = `on_open_price_confirmed(..., source="rest")` **+** `open_price_observe.mark_confirmed_via_rest`.
  - `owns_board(strategy, board, *, now=None)` = `board=="main" ∧ mode=="enforce" ∧ now < 09:05:00`(예외 = False) — 그 창 동안 `scheduler._confirm_breakout_open_prices` 가 그 전략 제외, 09:05:00 이후 = 스케줄러 2차 REST 폴백이 `source="rest"` 로 백스톱.
  - 마커 4종(`[main_rest_basis_config|round|confirmed|unresolved]`, `KstDailyEmitCap` + `observer_trace`) — `config` 1회/(전략,모드,emitter)/일 · `round` 전략별(fast 항상, slow 는 pending>0) · `confirmed` 1회/(전략,종목)/일, REST 조회 **직전** shadow 병기(`ws_open`/`ws_src`/`delta_bp`/`target_rest`/`target_ws` = 오염 규모 정본) · `unresolved` 1회/(전략,종목)/일, 마지막 fast 라운드 직후(= 커버리지 손실 정본). `scanner.ticker_prices` **읽기 전용**. 자문 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.
- **`quote_token_refresh.py`** — 보조 시세 계정 토큰을 매일 `TIME_QUOTE_TOKEN_REFRESH`(**20:45 KST**)에 계정별 `TokenManager.revoke()` → `issue()` 순차 재발급. `refresh_quote_tokens_once()` = `kis_quote_accounts.list_accounts(active_only=True)` 순회, `task_loop()` = `run_periodic_task_loop(immediate_first_run=False)`(부팅 시각 앵커 금지). 목적 = `TokenManager._is_valid()` 10분 선제 갱신이 보조 계정 재발급 시각을 매일 10분씩 당기는 **단조 드리프트** 차단. 주계정(`label=None`) 무접촉.
  - 🔴 `revoke()` 선행(KIS `/oauth2/tokenP` 는 유효 토큰이 있으면 **같은 토큰·같은 만료** 반환). `revoke()` 실패 = WARNING 1행 뒤 `issue()` 계속(무토큰 방치 금지), `failed` = issue 실패 전용, `revoke()` 는 전역 issue lock·61초 gap 소모·우회 없음. **WS 무영향**(WS 는 `/oauth2/Approval` `approval_key`).
  - **시각 불변식 3** = (a) T 와 T−10분 모두 KRX 장중(09:00~15:30) 밖(필요조건) (b) 7계정 × 61s ≈ 7분 직렬화 창이 REST 다량 사용 작업과 비겹침 (c) **T 는 task 루프 생존 창 안** — `run_daily` 의 `finally` 가 정산(`TIME_SETTLEMENT`) 뒤 백그라운드 task 를 전부 cancel(그 뒤 시각은 0회 발화인데 `scheduled at=` 만 남는다). 🔴 진짜 요건 = 「보조 풀 REST 가 없는 창」. 20:45 = 20:00 자문·20:00:05 유니버스·20:05 metrics·20:30 일봉(≈20:32 종료)·21:30 정산이 전부 `[T−10, T+8]` 밖(가드 `test_c9`·`test_c10` 전수 스캔).
  - 마커 `[quote_token_refresh]` 3종 = `scheduled at=`(배선 카나리아) · `label=… issued expired=… revoked=True|False`(`revoked=False` = 앵커 미이동) · `accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d`(`elapsed_s` ≈420s = 7 × 61s, `window_issues_total` = 체인 시작 **−15분**~종료 발급 수). 성공 서명 = 장중 자연 재발급 0 · `window_issues_total=7`. `scheduler.py` 배선 = 2줄(import + `create_task`) + cancel 목록 3곳.
- **`daily_bar_finalize.py`** — 부팅 prepare 직전 전일 「잠정 봉」(20:30 적재분, 종가·고저에 애프터마켓 값 혼입)을 KIS 정규장 확정값으로 덮는 leaf(cycle386). 공개 = `spawn(*, phase) -> asyncio.Task` · `wait_for_boot(task, *, budget_secs)` · `finalize_once(*, now_kst=None, phase)` + 상수 8개. 최상위 import = `src.db.{positions,stock_master_daily,system_config}` · `src.db._kst` 뿐, `src.api.condition` = 함수 안 지연. 🔴 8영역·`scheduler`·`scanner`·`boot_manager`·strategies import 0(AST G5 b). 계약 = 하단 「전일 잠정 봉 확정」.
- **`account_cluster.py`** — 계좌 묶음 배정 **기록**(단계 0, cycle404, 자문 cycle400 R1~R5). **행위 변경 0** — 매수 차단·수량 변경·신호 변경 없음, 읽기(DB SELECT)와 `system_logs` 기록만. 매일 부팅에서 포지션 복구 뒤 1회, 보유 전부(꺼진 전략 포함) ∪ 켜진 전략 후보(`_candidates`)를 업종 ETF 요인 10개(`FACTORS`, `091160` 반도체 등) 또는 KODEX200(`069500`)·`independent`·`missing` 으로 배정(120일 수익률 피어슨 상관, `CORR_MIN=0.60`·`MARKET_MARGIN=0.03`)하고, 묶음별 유닛(`CLUSTER_CAP_U=4`)·명목(`CLUSTER_CAP_PCT=20.0%`)·계좌 유닛(`ACCOUNT_CAP_U=18`)을 `[account_cluster_assign]` WARNING(「기록 전용」)으로 남긴다. 공개 = 순수 `assign_one`/`assign_all`/`summarize` + I/O `run_boot_assign(registry, net_asset)`/`spawn_boot_assign(scheduler_or_registry, net_asset)`(`INITIAL_DELAY_SECS=30` 뒤 실행, await 없음)/`get_assignment_map()`. import = 표준 라이브러리 + `src.db.stock_master_daily.get_recent_daily`(KIS 폴백 없는 DB 전용)·`src.db.system_config` 뿐 — `src.api.*`·8영역·`scheduler`·`strategy_registry` 전부 금지. 킬스위치 `system_config.account_cluster_mode`(`off`/`record`, 부재=`record`, `shadow`/`enforce`=미구현이라 `record`+WARNING — **전략 `params` 가 아니라 계좌 키**, `PARAM_RANGES`/`INT_PARAMS`/AI 자문 편입 금지). 🔴 **소비처 0** — `tests/unit/ast/test_cycle404_ast_account_cluster.py` G2 가 전략·`risk`·`order_engine`·`scheduler`·`strategy_registry` 무접촉을 봉인한다(단계 1 섀도 게이트 착수 시 `strategy_base.py` 가 이 모듈을 부르게 되며 그 사이클이 G2 를 의도적으로 고친다). never-raise — 종목 하나 읽기 실패는 그 종목만 `missing`, 시장(069500) 결손·타임아웃(`RUN_TIMEOUT_SECS=120`)·레지스트리 예외는 `[account_cluster_unavailable]` + 배정표 비움(이전 값 잔존 금지). 배선 = `boot_manager.py` `spawn_funnel_boot_vs_evening` 바로 뒤 `try/except Exception`.
- **`llm_buy_gate.py`** — **매수 주문 접수 시점** LLM 평가 shadow leaf(행위 0). `observe_order(*, strategy_id, ticker, order_no, order_kst, order_price_won, ordered_qty, order_division, order_path, exchange, current_price_won, budget_total_won, budget_remaining_after_won, open_positions_n, params_snapshot, buy_signals_tail)` — **키워드 전용 · 동기 · never-raise · `await`/DB/HTTP 0 · 반환 `None`**. 호출 = `order_engine.execute_buy` 매수 `place_order` 성공 직후 매핑 등록 블록 끝 **2곳**(주 경로 · 시장가 거부 지정가 5호가 폴백), `_insert_pending_or_absorb_race` **앞**(전략 파일 훅 없음, 8영역 중 `order_engine.py` 만 접촉, A-ATOMIC 구간 byte 동일). 킬스위치 `llm_gate_mode=off`(PUT 즉시). 영속 = `src/db/llm_buy_evaluations.py` + migration 043, 조회 = `src/routes/llm_evaluations.py`.
  - **순서** = `mode(off|shadow, 그 외 off)` → `[llm_gate_config]` 카나리아(off-return 앞) → off return → `order_no` 유효성(빈 값 = `[llm_eval_persist] reason=empty_order_no` 후 return) → 래치 peek(키 = **주문번호**/일 — 같은 종목 하루 두 번 = 두 번 평가) → 일일 cap peek(`[llm_gate_daily_cap]` WARNING 1회/전략/일 + `[llm_eval_persist] reason=cap_exceeded` 주문별) → 값 복사 payload → 래치 mark + cap 증가 → `asyncio.create_task(_evaluate)` 정확 1회.
  - `_evaluate` = `_evaluate_core` outcome 을 **단 1곳** `_persist_evaluation`(성공·실패 **모두** `llm_buy_evaluations` 1행, 실패 = `input_payload` + `score=NULL`). `_evaluate_core`(세마포어 2) = `db.stock_master_daily.get_recent_daily_normalized`(캐시 `(ticker, KST date)` 상한 400, 당일 봉 폐기, 60봉 → 프롬프트 30봉) → `llm_features.compute_technicals`/`build_messages` → `AsyncOpenAI.chat.completions.create`(`settings.openai_buy_gate_model`, `response_format=json_object`, `asyncio.wait_for`) → 출력 검증(클램프 금지, `int(inf)` OverflowError 흡수). `_MAX_COMPLETION_TOKENS = 2000`. 출력 한도 소진(`finish_reason=="length"`) ∧ 파싱 실패일 때만 `reason=truncated`(완전한 JSON 이면 점수 유지). `asyncio.CancelledError` re-raise.
  - 마커 5종 = `[llm_gate_config]` · `[llm_buy_score]`(`order_no=`·`order_kst=`·`order_price=`·`post_order_drift_bp=` — **+ = 주문 뒤 상승 = 이득**) · `[llm_buy_score_failed] reason=` 10종(timeout / api_error / parse_error / schema_error / no_bars / no_key / cap_exceeded / disabled_model / payload_error / truncated; `finish=` = OpenAI `finish_reason` 원문, 호출 전 실패 `-`) · `[llm_gate_daily_cap]` · `[llm_eval_persist] order_no= result=ok|error [reason=]`(DB 무음을 깨는 유일 채널). 🔴 `empty_order_no`·`cap_exceeded` = **persist 어휘**(평가 실패 어휘와 섞으면 리포트 실패 분류 오염).
  - 보드 = **시계**(`_board_by_clock` — 트래커 활성 보드는 30초 stale 이라 09:00:0x 에 `pre_nxt` 로 굳는다). 계좌번호 = `settings`. 회고 층화 = `_prompt_version()`(SYSTEM 프롬프트 + user 프리앰블 + `llm_features` 스냅샷 키 sha256 앞 12자) / `_feature_version()`(`compute_technicals` 출력 키 집합), 실패 `""`. 최상단 `src.*` import 허용 = `daily_emit_cap`·`observer_trace`·`llm_features`·`config`·`db.stock_master_daily`; `scanner`·`tick_volume`·`log_analysis_engine`·`db.llm_buy_evaluations` = 함수 내 **지연 import**(순환 차단).
- **`market_unit.py`** — 시장 유닛(단계형) 판정 leaf(cycle382). KODEX 200(`SOURCE_TICKER="069500"`) 일봉 종가 → 거래일 장세 4단계. `MULTIPLIERS` = `up_rising` 1.0 · `up_falling` 0.75 · `down_rising` 0.5 · `down_falling` 0.0.
  - 창 `w` = `bas_dd < as_of_date` 행 오름차순 마지막 `MIN_ROWS`(80)개. `above = w[-1] × 60 > sum(w[20:80])` · `rising = sum(w[20:80]) > sum(w[0:60])`(60일선 > 20봉 전 60일선). 합 비교(부동소수 동률 흔들림 제거), 동률 = 약한 쪽(엄격 부등호). 상수(`MA_WINDOW=60`·`SLOPE_LOOKBACK=20`·배수 4개)는 이 파일에만, 파라미터로 열지 않는다(AST A02).
  - 공개 = 순수 `classify(closes)` · `normalize_mode(raw)`(부재 = `("off", True)`, 오타·비문자열 = `("off", False)`) + never-raise 로더 `async compute_snapshot(as_of_date, *, preview) -> Snapshot` — `stock_master_daily.get_recent_daily("069500", FETCH_ROWS=120)`·`trading_calendar.previous_trading_day(as_of_date)` 를 **함수 안 지연 import**(monkeypatch seam · DB 전용 · KIS 폴백 없음).
  - 판정 순서 = 행 수(`rows_short`) → 신선도(`stale_head` = `head < previous_trading_day(as_of_date)`, 달력 모름 = `(as_of_date − head).days > STALE_FALLBACK_MAX_CALENDAR_DAYS`(10)) → 종가 품질(`bad_close` = 창 안 결측·비수치·비유한·0 이하) → 그 밖 `exception`. 실패 = 전부 `ok=False, state="unavailable", m=1.0`. 🔴 m=0(fail-closed)으로 바꾸지 않는다.
  - 화면 소비 = `routes/market_regime_label.py` 가 `classify` 를 그대로 불러 오늘·최근 60일 배수를 보인다(읽기 전용).
  - 최상위 import = 표준 라이브러리뿐, 8영역·`scheduler`·`boot_manager`·`market_regime` import 0(AST A01). 마커는 전부 이 모듈 `logger`(`"src.engine.market_unit"`), 호출·cap 판정은 `StrategyBase` 헬퍼(하단 `strategy_base.py` 절). ⚠️ `069500` 은 시총·거래대금 자격(`scanner._is_daily_load_universe`)으로 일봉 적재 대상 — 자격 상실 시 매일 `stale_head` → m=1.

- **`market_regime_label.py`** — 6장세 라벨 leaf(cycle410 — 사용자 결정 10-05). **관찰 전용 — 매매 경로가 읽지 않는다**(소비 = `routes/market_regime_label.py` 하나). `069500` 종가 → {`stable`,`volatile`} × {`up`,`flat`,`down`}. 방향 = `SMA60(t)/SMA60(t−20) − 1` 히스테리시스(횡보에서 > +3% 상승 · < −3% 하락 · 상승은 < +1%, 하락은 > −1% 에서 횡보로 풀린다) · 변동 = 20일 로그수익률 표본표준편차 × √252 히스테리시스(> 20% 변동 · < 16% 안정 · 사이는 직전 유지). 상태는 첫 특징(80번째 종가)에서 (`flat`, `stable`)로 시작해 이력을 걸어 이어 간다(시작점이 다르면 첫 구간이 달라질 수 있다). `label_after_closes(closes)` = 종가 시점별 상태 · `session_labels(dates, closes)` = D 일 라벨 = D-1 종가까지. 상수는 이 파일에만, 파라미터로 열지 않는다. 표준 라이브러리만 · I/O 0. 정의 정본 = `_workspace/domain_consult/2026-10-05_six_regime_strategy_map.md` §1.4 (골든 재현 = `tests/unit/engine/test_cycle410_market_regime_label.py::test_g1`, ETF 보관소 없으면 skip — 보관소 종가 기준이라 운영 DB 종가로 매기는 화면 값과 다를 수 있다). 🔴 시장 유닛(`market_unit.py`)과 재료만 같고 다른 장치다 — 이 라벨로 랏·전략을 바꾸지 않는다.

### 자문 · 리포트 · 레짐

- **`recommendation_engine.py`** — 20:00 AI 자문. `auto_apply` = 살아 있는 전략 객체 직접 변이 = **파라미터 즉시 반영의 유일 경로**. 하단 전용 절.
- **`recommendation_metrics.py`** — `trade_history` + `daily_performance` → LLM 프롬프트용 **결정적 통계 dict** 순수 계산.
- **`backtest_orchestration.py`** — 백테스트 오케스트레이션 5함수(`_get_backtest_engine`/`_spawn_backtest_poll_task`/`_enqueue_backtest_jobs`/`_backtest_poll_loop`/`_emit_pending_summaries`) + `_backtest_poll_loop_running`/`_BACKTEST_POLL_*`. leaf(core 미호출, 순환 0), `recommendation_engine` 이 module-level 재export(scheduler import 경로 = 테스트 patch 경로 = **동일 객체**). 🔴 `logger = logging.getLogger("src.engine.recommendation_engine")` 명시.
- **`log_metrics_collector.py`** — 일일 리포트(21:30) **수집·집계 계층**. `collect_daily_log_metrics`(반환 키 집합·순서 = OpenAI 프롬프트 = `daily_log_reports.metrics` JSONB = 20:20 루틴 번들) + `_fetch_logs_in_range` · `_aggregate_*` · `_build_portfolio_risk_snapshot` · funnel 수집 + 정규식 · `DAILY_LOG_FETCH_LIMIT` · `HIGH_SEVERITY_FETCH_CAP` · `KST`. `log_analysis_engine.py` = LLM 호출·검증·저장 + 위 심볼 `__all__` 재export — 🔴 `routes/log_reports.py` import 문 무접촉(L2 텍스트 가드). monkeypatch = **collector 경로**.
  - 🔴 **새 키는 끝에만 추가**(핀 = `test_cycle249_collect_metrics.py::EXPECTED_METRIC_KEYS` · `test_cycle259_log_metrics_collector.py::test_l3_metric_key_order_is_byte_identical`·`test_l3b_reexported_entrypoint_returns_same_shape`). 관측 전용 끝 세 키 = 10번째 `vcp_breakout_events` · 11번째 `pyramid_shadow` · 12번째(맨 끝) `report_accuracy`.
  - **`"vcp_breakout_events"`(cycle349)** = `trading_scheduler.registry.get("vcp_breakout")` 의 `breakout_event_summary(target_date)`(메모리, 실패 = 이 키만 `None`). `final` **1** = VCP 매수 창(`params["entry_end"]`, 못 읽으면 14:30) 종료 후 값(지난 날짜 포함) / **0** = 중간값. WARNING `[vcp_breakout_events] date= status=ok crossed=<C>/<N> observed= unobserved= run_at= window= partial= crossed_tickers=` = `target_date == 오늘(KST)` **∧ 창 종료 후만**, 모듈 전역 `KstDailyEmitCap` **하루 1회**(평소 20:05). 창 열린 동안(낮 번들 GET·`POST /api/log-reports/run`)·과거 날짜 = 키만 채우고 cap 미소비. `ok` 아니면 `status=` 까지. 실패 흔적 = DEBUG `[vcp_breakout_events_error]`. 의미 = `strategies/CLAUDE.md` 각주 ⑥.
  - **`"pyramid_shadow"`(cycle351)** — `kojiro`·`donchian_swing` 레지스트리 파라미터 사본 + 예산 + 보유 ticker 집합(읽기만) → `src.engine.pyramid_shadow.build_pyramid_shadow`. 30초 상한(`_PYRAMID_SHADOW_TIMEOUT_SECS`), 실패 = 이 키만 `None` + DEBUG(매번) + WARNING `[pyramid_shadow_error]` 1회/일(`_pyramid_shadow_failure_cap`, `observer_trace` 규약).
  - **`"report_accuracy"`(cycle366)** = `{trading_day, market_closed, by_ticker_pnl_total_tickers, by_ticker_pnl_truncated, after_market_blind_secs_total, pre_market_blind_secs_total}`. `trading_day`(`bool | None`) = `trading_calendar.is_open_day(target_date)`(지연 import, 예외 `None`), `market_closed = (trading_day is False)`(모름 ≠ 휴장) — 20:20 루틴·21:30 LLM(`log_analysis_engine.SYSTEM_PROMPT`)의 휴장일 0건 오독 방지. `by_ticker_pnl_total_tickers`/`by_ticker_pnl_truncated`(`_by_ticker_pnl_truncation`) = `trades.by_ticker_pnl` 상위 5 절단 관측(서브딕트는 cycle351 골든 byte 계약 — 무접촉). 확장 blind 2필드(`_aggregate_extended_blind`) = `[tick_blind_boot]` 애프터·프리 겹침 초(`tick_blind.market_blind_secs_total`(09:00~15:30, cycle234)과 별도). 회귀 `tests/unit/engine/test_cycle366_report_accuracy.py`.
- **`pyramid_shadow.py`** — 피라미딩(사다리 증량) 가상 기록 leaf. **행위 0 · 읽기 전용**(DB SELECT 만, KIS 0). 순수 코어 `overlay_ladder`(+ `no_add_flags` · `LadderConfig` · `LADDER_C`) = 「실제 청산(앵커) 위 사다리만 덧씌우는」 모형, async 어댑터 `build_pyramid_shadow` = `kojiro`·`donchian_swing` 그날 대상 포지션(보유 + 최근 7 달력일 미확정 청산 재확인, §2-1 확장)에 적용 → `metrics["pyramid_shadow"]`. 손절선 = `_stop_floor` 래칫(조이기만 — 세트선·평단 backstop·평단 본전 승격 + kojiro live ATR 「가중평단 − stop_atr×ATR」항). 청산 확정(`final=1`, 오늘) = `[pyramid_shadow_close]` WARNING 1회/포지션/일(`system_logs` 30일, `top_patterns` 미편입). import 하는 프로덕션 모듈 = `log_metrics_collector.py` 하나(AST 가드). 회귀 = `tests/unit/engine/test_cycle351_pyramid_shadow_{core,collect}.py` + `tests/unit/ast/test_cycle351_pyramid_shadow_scope.py`.
- **`log_analysis_engine.py`** — 21:30 일일 로그 분석(LLM 호출·검증·저장). 하단 전용 절.
- **`daily_metrics_snapshot.py`** — 20:05 metrics **1차 스냅샷 leaf**. `run_daily_metrics_snapshot(target_date: date | None = None) -> dict | None` 이 `TIME_METRICS_SNAPSHOT` 에 `daily_log_reports` 그날 행 upsert(메모리 전용 `api_metrics`·`strategy_funnel` 유실 노출을 **5분**으로). 🔴 **OpenAI 미호출**(`model`·토큰 5컬럼 NULL). 🔴 **`reset_request_metrics()` 미호출**(부르면 21:30 완전판이 저녁 90분치만 본다). never-raise. 마커 `[daily_metrics_snapshot] target_date= pass=1 saved=1|0 elapsed_ms=` 실행당 1행 — 성공 서명 = `saved=1`(`saved=0` = WARNING). 같은 행이라 `insert_log_report` = `ON CONFLICT (target_date) DO UPDATE`, SET = base 9컬럼만(`ext_*` 6컬럼·`created_at` 무접촉).
- **`trade_cost.py`** — 실비용 사후 대사·요약(트랙 C). **행위 0** — 매매 경로(`order_engine.py` 손익 계산)를 건드리지 않고 KIS `TTTC8715R` 정산값을 사후에 가져온다. `reconcile(start, end)` = 조회(`api/trade_profit.py`) → `aggregate_kis_rows`(`(trad_dt, pdno 뒤 6자리)` 로 접기) → `db/trade_cost.upsert_daily`·`upsert_period_total` → 행 합계 ↔ KIS output2 합계 대조(`totals_match`, 0.5원 이내) → 경보. `build_summary(start, end, strategy)` = DB 읽기 → `summarize`. 소비 = `/api/costs/*`(수동 실행) · 매일 자동 대사 = `trade_cost_reconcile_task.py`
  - **전략 귀속** `attribute(cost_rows, trades)` = `allocate_rows(cost_rows, trades, key="strategy")` 와 동일(cycle411 — 일반화는 `allocate_rows` 가 맡고 이 함수는 기존 호출부를 위해 남는다, 행위 보존). 같은 KST 날짜·종목의 `trade_history` COMPLETED 체결금액(price × quantity) 비율로 `key` 값(전략 또는 `id`)별 1행씩 나눈다. 수수료 = 매수+매도 체결금액 비율 · 세금·실현손익 = 매도 체결금액 비율(매도가 없으면 전체 비율) · 매수/매도금액 = 같은 쪽 비율. 두 group(전략/체결 행) 이상이 나눠 가지면 `estimated=True`(「배분 추정」) · 짝 없는 KIS 행 = `unattributed`(key="strategy") 또는 `None`(그 외). `key="id"`(cost_overlay 전용)는 체결 행 단위 — `estimated=True` 가 cost_overlay 의 `allocated` 플래그다. ⚠️ BUY 행 가격은 다건 체결통보면 마지막 체결가라 매수 쪽 비율에 그 오차가 든다
  - **요약** = 전략별 `gross_pnl`(`trade_history` SELL `profit_loss` 합 — 세전·비용 전, 의미 무변경) · `fee` · `tax` · `net_pnl` = gross − fee − tax · `cost_bp` = (fee+tax) ÷ ((buy_amt+sell_amt)/2) × 10⁴(분모 0 = `None`) · `kis_rlzt_pfls`(KIS 실현손익 귀속분, 참고값)
  - **슬리피지** = `trade_history.order_price`(주문가) 대비 체결가(`price`), + 가 비용 — 매수 (체결가 − 주문가) × 수량 · 매도 (주문가 − 체결가) × 수량. `order_price` NULL 행은 빠지고 덮인 건수 `slippage_n` 을 함께 낸다(cycle409 — 사용자 결정 10-04 Q4). ⚠️ 한계 — 시장가 주문의 주문가 = 주문 순간 현재가(호가가 아니다)라 스프레드 절반이 빠지고, 매도 시장가에 현재가 캐시가 없으면 NULL. 체결통보 선행 보정·동기화 INSERT 행도 NULL. `slippage_bp` 는 덮인 주문금액 기준이라 `cost_bp` 와 합치지 않는다
  - **경보** `[trade_cost_high]` WARNING(+`system_logs`) = 전략별 `end` 포함 30 달력일 `cost_bp` > `system_config.trade_cost_alert_bp`. 🔴 **기준값을 코드에 두지 않는다**(사용자 결정 Q3 — 키 없음 = 경보 끔) · `unattributed` 제외 · 경보 판정 실패는 삼키고 대사 결과는 돌려준다. 가드 = `tests/unit/engine/test_trackc_trade_cost_calc.py` · `test_trackc_reconcile.py`
- **`cost_overlay.py`** — 실적 화면에 실비용(수수료·세금)을 합치는 leaf(cycle411, 사용자 결정 10-08). 순수 함수(`estimate_rates`·`trade_costs`·`net_twr`·`day_cost_status`) + DB 를 읽는 async 어댑터(`today_window_rates`·`stock_master_etf_flags`·`overlay_pairs` — KST 오늘 기준)로 나뉜다. **8영역·`scheduler.py` 무접촉**(import 0 — `test_cycle411_cost_overlay.py::test_e1` · 8영역 sha 불변 = `test_cycle411_ast_scope.py`). DB 저장값을 바꾸지 않고 읽을 때 합친다. `trade_history.profit_loss` 의 의미(세전)는 그대로다.
  - **요율** — `estimate_rates(cost_rows)` = 정산 행 Σfee÷Σ(buy_amt+sll_amt) · Σtl_tax÷Σsll_amt → `{fee_rate, tax_rate, source: "measured"|"default"}`. 표본이 없으면 `DEFAULT_FEE_RATE`(0.00142) · `DEFAULT_TAX_RATE`(0.00199). `today_window_rates(window_days=RATE_WINDOW_DAYS)`(async, 30) 는 **서버 오늘(KST) 기준 `[today−30, today]`** 정산 행으로만 요율을 낸다. 화면 날짜 범위가 아니라 전 라우트 공통 출처다 — 화면 범위의 정산 행은 **배분에만** 쓴다.
  - **요율 캐시** — `today_window_rates` 결과를 KST 날짜 단위로 메모리에 둔다(키 `(today, window_days)`). 같은 날 두 번째 호출은 DB 를 읽지 않고, 날짜가 바뀌면 다시 읽는다. 조회 예외는 캐시하지 않는다(다음 호출이 다시 시도한다).
  - **ETF 판정** — `stock_master_etf_flags(trades) -> dict[ticker, bool]`(async). 고유 종목을 `src.db.stock_master.get_etf_group_codes` 로 **한 번에** 읽는다(모듈 속성 경유, `stock_master.get` 호출 0). 코드가 있는 종목만 `is_etf_like({"scty_grp_id_cd": code}, name)` 로 판정하고, 코드가 없는 종목은 결과에서 뺀다(이름 폴백이 받는다). 조회 예외 = `{}` + DEBUG(전부 이름 폴백).
  - **체결 행 단위 비용** — `trade_costs(cost_rows, trades, rates, etf_tickers=frozenset(), etf_flags=None) -> {id: {fee, tax, cost_status, allocated}}`. 정산 행이 있으면 `trade_cost.allocate_rows(key="id")` 로 쪼개 `cost_status="settled"` 이고, 정산 1행을 2개 이상 체결 행이 나눠 받았으면 `allocated=True`. 정산 행이 없으면 추정 요율 × 체결금액 → `cost_status="estimated"`·`allocated=False`. 세금은 매도 행만이고 ETF/ETN 매도는 0 이다(판정 순서 `etf_flags[ticker]` → `etf_tickers` → `etf_like.is_etf_like` 이름 폴백). **정산값이 있으면 ETF 라도 그 값이 정본**이다(KIS 가 낸 세금을 0 으로 덮지 않는다).
  - 🔴 **「매도 없음」 은 체결 집합으로 판정한다** — 그 `(trad_dt, pdno)` 의 체결 행 중 금액 > 0 인 SELL 이 없는데 정산 `tl_tax > 0` 이면, 정산 행 `sll_amt` 와 무관하게 세금을 매수 행에 몰지 않는다(체결 행 `tax` = 0, 미배분) + `[cost_overlay_tax_unallocated] ` WARNING. 짝 체결이 **하나도 없는** 정산 행은 `[cost_overlay_unmatched_cost] trad_dt=… pdno=…` WARNING 만 남기고 반환 dict 에 아무것도 더하지 않는다(귀속할 체결 id 가 없다). 짝이 아예 없는 키는 미배분 대상에서 먼저 빠지므로 경고는 한 줄이다. 두 경고는 `(kind, trad_dt, pdno)` 당 **프로세스 수명 1회**다(`_warn_once` — 날짜를 키에 넣지 않는다). 전략 귀속 `trade_cost.attribute`/`allocate_rows(key="strategy")` 는 이 미배분 규칙을 쓰지 않는다(트랙 C 요약 행위 보존).
  - **일별** — `net_twr(records, costs_by_date)` = `daily_performance` 행에 일별 비용을 얹어 net TWR 재누적(분모 = 가장 가까운 이전 0 아닌 `total_asset`, `recompute_daily_performance` 와 같은 식 — 비용 0 인 날은 gross 값을 그대로 써 부동소수 오차가 없다). `day_cost_status(statuses)` = settled/estimated/mixed.
  - **페어 어댑터** `overlay_pairs(pairs) -> dict[id, trade] | None`(async) — `get_trade_pairs` 출력(`buy_trade_ids`/`sell_trade_ids`/`partial_sell_trade_ids`)에 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`·`allocated` 를 채운다. 거래 단위 귀속이다 — 수수료 = 매수+매도 전부, 세금 = 매도 행만. 조회 범위는 페어들의 `buy_date`/`sell_date` 에 **오늘(KST)을 더해** 넓힌다(분할 매도는 날짜를 모른다). 반환 맵 `trades_by_id` 는 `slippage_n` 집계용이고, 각 행에 체결 행 단위 `fee`·`tax`·`cost_status`·`allocated` 도 실린다(cycle413) — `/api/history/journal` 이 비용 원천을 두 번 읽지 않으려고 쓴다. `/api/history/pnl` 은 그중 `order_price`·`id` 만 읽는다.
    - 🔴 **체결 id 의 타입을 맞춰 넘긴다** — 비용 맵과 `trades_by_id` 의 키는 `get_trades_by_status` 가 돌려준 `uuid.UUID` 다. 페어의 `*_trade_ids` 를 문자열로 바꿔 넘기면 키가 하나도 맞지 않는다. 그러면 오류·경고 없이 페어 비용이 0 으로 계산된다 — closed 는 `fee`·`tax` = 0·세후 = 세전·`cost_status="estimated"`, open 은 낸 매수 수수료와 `partial_fee`·`partial_tax` 가 0. 문자열이 필요한 호출부는 이 함수를 부른 **뒤에** 바꾼다(`/api/history/journal`).
    - closed 페어 — 체결 행 비용 합, `cost_status` = `day_cost_status`. `allocated` 는 그 페어 체결 행(`buy_trade_ids`+`sell_trade_ids`+`partial_sell_trade_ids`)이 받은 정산 행 중 **하나라도 페어 밖 체결 행에도 나뉘었을 때만** True 다(`_settlement_id_groups`·`_pair_allocated_outside`). 같은 날 사고 판 단일 페어는 False — 체결 행 단위 `trade_costs(...)[id]["allocated"]` 와 뜻이 다르다.
    - open 페어 — `cost_status="estimated"`·`allocated=False`. `fee` = 낸 매수 수수료(정산/추정) × **남은 수량 비율**(`buy_qty` ÷ `buy_trade_ids` 매수 수량 합) + 예상 매도 수수료, `tax` = 예상 매도세. 현재가는 `(buy_price × 남은 수량 + profit_loss) ÷ 남은 수량` 으로 페어 안에서만 역산한다(scanner 캐시 무의존). 분할 매도 뒤 판 몫은 `partial_fee`(매수 수수료 × 판 비율 + `partial_sell_trade_ids` 매도 수수료)·`partial_tax`(그 매도세)로 따로 낸다 — 총합 보존(보유 몫 + 판 몫 = 정산 합).
    - 🔴 **현재가를 모르면 비용도 모른다** — open 페어의 `profit_loss is None`(21:30 이후·재기동 직후·휴장일 종일)이면 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp` = `None` 이다(0 으로 치지 않는다). 이미 낸 `partial_fee`·`partial_tax` 는 숫자 그대로 둔다.
    - `net_profit_loss` = `profit_loss − fee − tax` · `net_profit_rate` = ÷ 매수금액 × 100(소수 넷째 자리) · `cost_bp` = (fee+tax) ÷ ((매수금액+매도금액)/2) × 10⁴(매도가 없으면 분모 = 매수금액, 소수 넷째 자리). `slippage_won` 은 그 페어 체결 행 중 `order_price` 가 하나도 없으면 `None`(있으면 덮인 행만 합산 — 0 과 구분).
    - 실패 처리 — 정산·체결·요율 **조회** 예외는(ETF 판정 조회 예외는 `stock_master_etf_flags` 가 `{}` 로 삼킨다) `[cost_overlay_unavailable]` WARNING + `None`(호출부가 기존 응답을 유지). 그 뒤 순수 계산의 예외는 이 함수 밖으로 나가므로 라우트가 한 번 더 감싼다(`src/routes/CLAUDE.md` `/api/history/pnl`·`/api/strategies/te` 행).
  - **메모리 초기화** — `_reset_cache_for_tests()` 가 요율 캐시와 경고 dedupe 를 비운다. `tests/conftest.py::_reset_cost_overlay_memo`(autouse)가 매 테스트 전·후에 부른다.
  - 소비 = `overlay_pairs` → `/api/history/pnl`·`/api/history/journal`·`/api/strategies/te` · 나머지 함수 직접 호출 → `/api/performance/{daily,summary}`·`/api/history`·`/api/costs/{today,daily}`·`/api/balance`(잔고는 매수 수수료만 쓰므로 `etf_flags` 를 넘기지 않는다). 가드 = `tests/unit/engine/test_cycle411_cost_overlay.py` · `test_cycle411b_cost_overlay_engine_fixes.py` · `test_cycle411c_cost_overlay_engine_fixes2.py` · `test_cycle411d_cost_overlay_warn_fixes.py` · `test_cycle411_te_net.py` · `test_cycle411d_te_net_mixed_guard.py` · `tests/unit/ast/test_cycle411_ast_scope.py`.
- **`journal_view.py`** — 거래일지 화면(1b) 카드 조립 순수 leaf(cycle413). 공개 함수는 `build_card(pair, *, fills, orders, stops, note, closes, business_days, llm_evals, costs, record_start, now) -> dict`(`JournalCard`) 하나다. `async def`·`await` 0 · `src.db`/`src.api`/`src.realtime`/`src.auth`/`scheduler`/8영역/`asyncpg`/`httpx` import 0(AST `test_cycle413_scope_guard.py` S4). 응답 모양·이유 문장 규칙의 정본 = `_workspace/red/cycle413/journal_view_spec.md` + 키 목록 `tests/fixtures/cycle413_journal_shape.json`(백엔드·프론트 테스트가 같은 파일로 키 집합을 비교한다). 소비 = `src/routes/history.py` `GET /api/history/journal` 하나.
  - **입력** — DB 함수가 돌려주는 모양 그대로 받는다(시각 = KST ISO 문자열, 날짜 = `date`). `fills`·`orders`·`stops`·`closes`·`business_days`·`costs` 가 `None` 이면 「조회 실패」 로 읽는다(빈 목록과 다르다). `pair` 의 `*_trade_ids` · `fills` 의 `id` · `costs` 키는 같은 타입이어야 한다(라우트는 셋 다 문자열로 맞춘다).
  - **체결 행 조회 실패(`fills=None`)** — `opened_at`·`closed_at` 은 페어의 `buy_date`+`buy_time`·`sell_date`+`sell_time`(`+09:00`)으로 채우고 `held_days` 도 그 값으로 센다(응답 타입의 non-null 유지). 주문 줄·청산 줄은 비고, MFE/MAE 는 종가가 있어도 `lookup_failed` 다(보유 수량을 모른다). 비용 합계 `paid_total` 은 `None`, 보유 중이면 `expected_exit` 도 `None`(`expected_exit_na="lookup_failed"`)이다. 진입 이유는 AI 매수평가로 복원하지 못하면 `lookup_failed` 다(주문번호를 몰라 일지 행을 찾지 못했다 — `unknown` 이 아니다).
  - **「모름 ≠ 0」** — 값이 `None` 이면 짝 `*_na` 가 반드시 있다. `*_na` = `unknown`·`before_record`·`not_applicable`·`pending`·`lookup_failed` 5종. 숫자 칸에 0 을 채워 「모름」을 숨기지 않는다. 비용 맵(`costs`)에 없는 체결 id 가 하나라도 있으면 그 몫(`entry_fee`, 그 청산 줄의 `fee`·`tax`)은 `None` 이고 `paid_total` 도 `None` 이다(부분합을 합계처럼 내지 않는다 · `costs.na` 는 그대로 `null` — 비용 블록 전체 실패가 아니다).
  - **기록 전 판정** — `record_start` 4종(`orders_restored`·`orders_live`·`stops`·`order_price`)과 체결 날짜를 비교해 `before_record` 와 `unknown` 을 가른다. 접수 구분(`order_division`)은 `_DIVISION_RECORD_START`(2026-09-28) 전이면 `before_record` 다. 판단가가 없는 매수 줄은 AI 매수평가(`signal_price_won`)로 복원한다(`judge.src="restored_ai"`). 대상 = `_AI_BREAKOUT_NAME` 6전략(VB·LTV·donchian·BFB·VCP·`etf_trend`)이고, `_AI_CUTOFF`(2026-09-17) 전 거래는 VB·LTV 만이다.
  - **이유 문장** — VB·LTV 진입 문장은 돌파선 이름 앞에 보드를 붙인다(`_BOARD_LABEL` = `main` 본장 · `pre_nxt` NXT 프리 · `post_nxt` NXT 애프터, 출처 = 일지 `signal.board` · AI 매수평가 `strategy_board`). 보드를 모르면 붙이지 않는다. TRAILING_STOP 청산에서 `fired_line` 이 없고 스냅샷 `signal.stop_kind` 가 `hard_pct`(고정% 근사)면 숫자 없이 「트레일선 이탈」 이다 — 근사값을 발동선처럼 보이지 않는다(momentum·`etf_trend` 는 워커 문법에 트레일 패턴이 없어 `fired_line` 이 늘 없다). TAKE_PROFIT 청산의 `fired_line` 이 없으면 `signal.target` 으로 세우고 `fired_src` = `restored`(`log_restore` 행)·`live` 다.
  - **청산 줄 역할 `line_role`** — `STOP_LOSS`·`TRAILING_STOP` = `fired` · `TAKE_PROFIT` = `target` · 그 밖 사유 = `reference`(가격과 무관한 청산 — 화면이 「손절 미발동」). 사유 코드가 `None`(기록 전 청산·`external`·`unmatched`·일지 조회 실패)이면 `None` 이다 — 엔진이 판 것인지 모르므로 손절 발동 여부를 단정하지 않는다.
  - **체결오차** — 불리한 쪽이 + 다(매수 = 체결가 − 기준가, 매도 = 기준가 − 체결가). `slip_order` 의 기준가 = `trade_history.order_price`, 없으면 `trade_journal_orders.order_price`. `slip_judge` 의 기준가 = 판단가(`judge_price`, 없으면 상한 `judge_upper`)이고 주문가와 같으면 내지 않는다.
  - **손절선 변화 표** — 행은 (전략, 종목) · `observed_at ∈ [진입 − 60초, 청산 + 120초(보유 중이면 now)]` 인 것만 쓰고, `pos_order_no` 가 있는데 그 페어 매수 주문번호가 아니면 뺀다(없는 행은 남긴다). `first`·`boot`·`paused`·`exit` 사건은 항상 보이고, 나머지는 `stop_price`·`stop_kind`·`target_price`·`target_hit`·`arm_price` 다섯 칸이 직전에 보인 행과 같으면 숨긴다. 방향(`direction`·`delta_won`)은 직전에 보인 행 중 `stop_price` 가 **있는** 행과 비교한다(값 없는 행을 건너뛴다 — 없으면 방향 `None`). `hidden_eod` 는 숨긴 행 중 `eod` 만 센다. 원인 문구는 13가지를 우선순위 순으로 최대 2개 붙인다.
  - **MFE/MAE** — 기준가 = 페어 `buy_price`. 그날 15:30 에 1주 이상 들고 있던 영업일(`business_days`)의 종가만 쓴다. 그런 날이 0 이면 `not_applicable`, 있는데 종가 행이 0 이면 `unknown`. 종가 행의 `updated_at` 이 다음 날 06:00 KST 전이면 잠정(`provisional_dates`), `flng_cls_code` 가 `00`·빈 값이 아니거나 `prtt_rate ≠ 0` 이면 락(`lock_dates`)으로 표시한다.
- **`trade_cost_reconcile_task.py`** — 매일 자동 대사 훅(cycle409 — 사용자 결정 10-04 Q1). `scheduler.start()` 가 `_trade_cost_reconcile_task` 로 띄우고 21:30 정산 뒤 cancel 목록 3곳이 끈다. 60초마다 `system_config.trade_cost_reconcile_time` 을 다시 읽어 **키 없음 = 실행 안 함**(코드에 시각이 없다 — 사용자가 `PUT /api/costs/schedule` 로 켠다). 오늘 아직 안 돌았고 `at ≤ now < at+60분` 이면 직전 영업일(`trading_calendar.previous_trading_day`)까지 `days` 달력일을 `trade_cost.reconcile` 한다(하루 1회, 늦은 기동은 그날 건너뜀). 시각은 루프 수명 `[07:45, 21:30)` 안만 유효. 휴장일 = 건너뜀 · 직전 영업일 모름·실패·600초 초과 = `[trade_cost_reconcile_failed]` WARNING 1행(같은 날 재시도 없음) · 성공 = `[trade_cost_reconcile_done]` INFO. 8영역·scheduler import 0(AST `test_cycle409_ast_reconcile_hook.py`)
- **`market_regime.py`** — 매크로 레짐 **관찰** + `cash_usage_ratio` 자동 조정(출처 = 우리 `macro` 컨테이너, cycle315). 🔴 매수 가드 없음(`get_buy_block_state` = 대시보드·자문 payload 표시 전용). 하단 전용 절.

## `scheduler._wait_until` 계약

- `target_dt` = **호출 시점 1회 확정**(while 진입 전, 루프 안 재계산 금지 — 재-advance 차단).
- default(`advance_if_passed=False`): 지났으면 즉시 return, 아니면 도달 시 return(`run_daily` phase 전환 9곳).
- advance(`=True`, `task_loop_helper` 전용): 지났으면 `+= timedelta(days=1)` **1회** 확정 후 도달 시 return(발화).
- `asyncio.sleep(min(잔여초, 60))` + `while self._running`(stop 시 탈출 — 헬퍼 `if not scheduler._running: break` 가 흡수).
- 🔴 `break` 사용 금지(AST 가드) · naive `datetime.now()` 유지(컨테이너 `TZ=Asia/Seoul`) · 시그니처 불변(mock 6+ 파일 호환).
- 가드 `tests/unit/engine/test_cycle188_wait_until_advance_return.py`(fake sleep 이 가상 시각을 단조 전진). 🔴 **freezegun 금지**(동결 monotonic = hang).

## 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

```
run_periodic_task_loop(*, scheduler, task_label, wait_time, once_callable, record_fn, flush_fn,
                       summary_log_format, summary_keys, immediate_first_run=True,
                       retry_delay_secs=60, initial_delay_secs=0,
                       immediate_skip_if_fresh_hours=None,
                       immediate_skip_if_fresh_since_trading_slot=False,
                       immediate_force_run_check=None,
                       immediate_skip_if_marker_absent=False,
                       immediate_force_run_reason="below_floor")
```

- graceful(`CancelledError`·`Exception` 분리) · `start()` 직후 즉시 1회(`immediate_first_run`) · stagger `initial_delay_secs`(full_universe=0 / daily=240 / basics=480 / evening_funnel=600 / master=720 / financial=900초, purge 0 — 정본 `data_load_tasks.py`). 🔴 **신규 일일 task 도 이 헬퍼 경유**(직접 while 루프 금지 — 대기 중 `stop()` 에 잘리는 lifecycle race 표준 차단).
- **부팅 즉시 실행 게이트 두 갈래** — immediate 블록(stagger sleep 뒤 · once 앞)에서 `system_config.get_task_last_success(task_label)` 마커로 판정. 두 kw 동시 지정 = 진입 즉시 `ValueError`.
  - **시간 게이트** `immediate_skip_if_fresh_hours` — 마커 `0 <= elapsed < hours*3600`(미래 마커 음수 방어) → immediate `once()` skip + `[<label>] immediate run skip — fresh last_success=<iso>` INFO. 대상 = master(`IMMEDIATE_FRESH_SKIP_HOURS = 20.0`) · financial(`168` = 주1회). 주말·연휴도 낡음으로 센다(master 는 월요일·연휴 뒤 아침에 돈다).
  - **영업일 슬롯 게이트** `immediate_skip_if_fresh_since_trading_slot=True` — 슬롯 = 그 task `wait_time`(= `scheduler.TIME_*`, 새 시각 리터럴 금지). 마커 ≥ 「최근 지나간 영업일 슬롯」(`trading_calendar.latest_passed_trading_slot(now, wait_time)`) → skip. 대상 = basics(16:10) · daily_load(20:30) · full_universe(20:00:05) — 평상시 월요일·연휴 뒤 아침엔 셋 다 안 돈다.
- **슬롯 판정 순서**(`_evaluate_slot_gate`, never-raise — 단계 예외 = 실행):
  1. `immediate_force_run_check` True → RUN `<immediate_force_run_reason>`(기본 `below_floor`) / 예외 → RUN `force_check_error`(항상 고정 — 판정 실패 ≠ 임계 초과)
  2. 마커 조회 예외 → RUN `marker_error` — 🔴 **운영에서 도달 불가**(`system_config.get_task_last_success`(`_get_string_or_none`)의 broad `except Exception: return None` 이 pg 예외를 삼켜 ③으로). full_universe(`skip_if_absent=True`)에서 pg 장애 = 부트스트랩과 구분 불가 SKIP(둘 다 `reason=no_marker`, `tests/unit/engine/test_cycle363_immediate_slot_gate.py::test_H3b_*`)
  3. 마커 없음 → `immediate_skip_if_marker_absent` 면 SKIP, 아니면 RUN(둘 다 `reason=no_marker`)
  4. 마커 파싱 실패 → RUN `marker_unparseable`. **naive 마커(`utcoffset() is None`)도 여기**(KST 가정 금지 — aware 비교 TypeError 가 루프를 죽인다)
  5. 마커 > now(KST) → RUN `future_marker`(시계 이상 방어)
  6. 슬롯 `None`(휴장일 모름)·tz-aware datetime 아님 → RUN `calendar_unknown`. 🔴 휴장일 조회 실패 = 실행 쪽(사용자 지시)
  7. 마커 ≥ 슬롯 → SKIP `fresh`, 아니면 RUN `stale`
- **관측** = 판정마다 `[immediate_gate] task=<label> decision=run|skip reason=<위 어휘> marker=<iso|None> slot=<iso|None>` INFO. SKIP 이면 `[<label>] immediate run skip — <reason> last_success=<iso|None>` 추가(grep 연속성, `reason=fresh` 면 시간 게이트 문자열과 같다). 슬롯 모드 시각 seam = `task_loop_helper._now_kst()` 하나.
- 마커 = `once()` **성공 직후에만** 기록(immediate · while 양쪽). 기록 실패 graceful(다음 부팅 실행 = 안전 방향).
- 🔴 **정기 while 루프 발화는 게이트 무관 무조건 실행**(F-8 HIGH 가드).
- **full_universe 전용 장치 둘**(🔴 `once_callable` = `scanner._full_universe_load_once` 무접촉, 게이트는 헬퍼·wrapper 쪽):
  - **행 수 하한** `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000`(`data_load_tasks.py`) — `stock_master.count_active() < 2000` → 마커가 fresh 여도 실행(`immediate_force_run_check`, 유니버스 자가 치유). `count_active` 예외 = 0 = 실행.
  - **마커 없음 = SKIP**(`immediate_skip_if_marker_absent=True`, 부트스트랩 — 실행하면 직전 영업일보다 오래된 KRX 값으로 전량을 덮는다). 행 수가 하한 이상일 때 건너뛰고(미달이면 ① 이 실행), 첫 마커는 20:00:05 정기 실행이 남긴다. daily·basics 는 마커 없음 = 실행.
- **basics 강제 재실행(cycle363, 사용자 승인)** — `stock_master.count_missing_kis_provenance_key()`(`raw` 에 KIS CTPF1002R 키 `cptt_trad_tr_psbl_yn` 없는 행 수) `> STOCK_MASTER_BASICS_FORCE_RUN_MISSING_THRESHOLD`(=100, `data_load_tasks.py`) → fresh 여도 실행(`immediate_force_run_check=_stock_master_basics_kis_keys_missing_above_threshold`, `immediate_force_run_reason="kis_keys_missing"`). full_universe(+0초) **뒤**(+480초) 판정 — KRX 적재의 하드코딩 False(`nxt_tradable`·`krx_halted`·`admin_item`)·KIS 출처 키 부재가 16:10 까지 남지 않게. 🔴 `count_missing_kis_provenance_key()` 는 **예외를 삼키지 않는다**(「실패 시 0」이면 쿼리 실패 = SKIP, 사용자 결정 「쿼리 실패 = RUN」 위반) — ①의 `force_check_error` 가 흡수.
- 🔴 daily_load 게이트 이유 = 아침 immediate 가 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)으로 `max_bas_dd == today` 를 만들면 그날 정기 실행이 전 종목 `skipped_fresh`. 🔴 full_universe 무게이트 금지 = 아침 KRX 는 직전 영업일 자료가 없어 **그 전 영업일 값으로 전량을 덮는다**. 신규 상장 유입 = 20:00:05 정기 실행.
- 미대상 = purge · evening_funnel(게이트 kw 전무). evening_funnel 즉시 1회(+600초) = 21:00 전 레거시 재준비 분기(「funnel 스냅샷 캡처」).
- 가드 `test_cycle193_immediate_fresh_gate.py` · `test_cycle193_task_marker_helpers.py` · `test_cycle193_ast_fresh_gate.py`(F-10-1 시간/슬롯 두 갈래 · F-10-2 무게이트 = purge·evening_funnel) · `test_cycle263_daily_load_stub_filter.py` · `test_cycle363_immediate_slot_gate.py` · `test_cycle363_ast_business_day_gate.py`.

## 저녁 데이터 적재 (scanner + data_load_tasks)

### 시각과 순서

데이터 적재 5종만 — 전체 일과표 정본 = 하단 `scheduler.py` 절 `TIME_*` 표.

| 상수 | 값 | 작업 |
|---|---|---|
| `TIME_STOCK_MASTER_BASICS_REFRESH = time(16, 10)` | 16:10 | KIS CTPF1002R 매스 보강 |
| `TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)` | 16:30 | KIS 공식 마스터 파일(`kospi_code.mst`/`kosdaq_code.mst`) |
| `TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)` | 16:40 | 재무 5 TR 주1회 |
| `TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` | 20:30 | 일봉 적재 |
| `TIME_EVENING_FUNNEL_CAPTURE = time(21, 0)` | 21:00 | 저녁 미리보기 funnel 캡처(다음 거래일 기준, 일봉 적재 성공 마커를 기다린다) |

`TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` 인 이유 = KRX 애프터마켓 종료(20:00) 뒤라야 그날 거래량 확정, 16:1x~16:40 마스터 작업 뒤라야 유니버스 판정이 오늘치 raw 를 본다(매수 진입 무관 데이터 계층).

🔴 **20:30 에 쓴 D 봉의 종가·고가·저가 = 잠정 봉** — KIS 일봉(FHKST03010100, 시장 `J`)은 D일 20:00 뒤에도 종가 = 19:59 애프터마켓 마지막 체결가, 고저 = 애프터 포함 범위이고, D일 23:12 뒤 ~ D+1일 05:28 전에 정규장 값으로 바뀐다(cycle386 실측). 시가·거래량·거래대금은 같다(거래량·거래대금은 확정도 애프터 포함). 확정 = 다음 거래일 아침 부팅 prepare 직전(아래 「전일 잠정 봉 확정」).

- 🔴 **적재 시각을 미는 것으로는 못 고친다**(KIS 확정 23:12 뒤 vs task 는 21:30 정산 뒤 `run_daily` `finally` 에서 전부 cancel). `scanner.py` `_DAILY_LOAD_TODAY_BAR_CUTOFF` 주석 두 문장(「일봉 OHLC 는 15:30 에 확정되지만」 · 「어긋나면 이 상수와 scheduler 의 일봉 적재 시각을 함께 뒤로 민다」)은 사실이 아니다(`scanner.py` 8영역 — 이 문서가 정본).
- 21:00 저녁 미리보기 = 잠정 D 봉 기준(확정은 23:12 뒤, 루프는 21:30 종료) — 다음 날 부팅 목록이 정본.

### 유니버스 선정

- 게이트 = `if is_index or is_qualifier or is_protected:`.
- `is_protected` = `_collect_protected_tickers_for_scanner()` 의 보유·익일청산 중 **6자리 숫자 ticker 만**(진입 게이트 비대칭 규약 — 영숫자·오염 문자열 제외, ETF 코드는 남는다). 헬퍼 예외 = **fail-open**(`protected_tickers = set()`).
- 🔴 근거 = purge(`_evaluate_universe_guard` 계열)는 보유·익일청산을 절대 보호 — load 가 자격 미달로 건너뛰면 그날 봉이 영구 결손된다.
- 페이징 루프 뒤 `protected_tickers - set(all_tickers)` 를 `all_tickers` 에 append(어느 페이지에도 없는 보호 종목까지). 보호 종목도 분할 backfill 대상(깊이 축 = **적재 대상 전부**).
- 관측 `[daily_load_protected_forced] protected=%d forced_in_universe=%d forced_extra=%d tickers=%s` **실행당 1행**(종목당 금지) — 페이징 루프 밖 · `summary["total"]` 대입 앞 무조건 emit(조기 return 에도 1행).
- 가드 `tests/unit/engine/test_cycle273_daily_load_protected.py`.

### 분할 backfill 분기 — 대상은 적재 대상 전부

- 분기 = **깊이 하나**: `existing_count`(= `stock_master_daily.count_by_ticker`) `< _DAILY_LOAD_VCP_BACKFILL_DAYS(=225)` → `condition.fetch_daily_candles_backfill(ticker, total_days=225)`(분할 fetch, 마지막 윈도우 클램프) / `>=225` → 증분 `fetch_daily_candles(ticker, days=fetch_days)` 1콜(재 backfill 금지, 창 = 아래 「증분 창 — 빈 날 메우기」). 지수 소속·자격·보호는 깊이 무관(cycle302).
- 🔴 **`_DAILY_LOAD_VCP_BACKFILL_DAYS` 는 VCP 전용이 아니다** — 적재 대상(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) 전부의 목표 깊이(개명 = `src/api/condition.py` 호출자 주석과 함께 옮길 후속 과제).
- 🔴 **225 인 이유** = `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)` → 보유 **225 영업일에서 실효 장기선 정확히 200**. 깊이를 가르면 얕은 종목의 VCP 정배열 판정이 흔들린다.
- 🔴 **target·retention 동행** — `DAILY_RETENTION_DAYS=390`cal ≈ 261영업일 = 225 위 **36 영업일 마진**. target 이 보유 영업일을 넘으면 매 load 전량 재backfill(churn).
- 🔴 **비용 1회성** — 깊이 도달 뒤 증분(종목당 1콜), retention 이 225 아래로 안 떨어뜨린다(수렴 = 종목당 1콜, 가드 `tests/unit/engine/test_cycle302_backfill_scope_expansion.py::test_g302_3_converged_universe_costs_one_call_per_ticker`). 첫 채움(종목당 3콜) = **수동 trigger**(`POST /api/stock-master/daily/refresh`, 기본 `force=true`) 장 종료 후 — 20:30 에 얹으면 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창(20:35~) 침범.
- **1회 backfill > target** — `condition.fetch_daily_candles_backfill` 환산 `total_days=225` = 347 달력일 ≈ **232 영업일**(한 밤에 채운다). 🔴 환산 **stride 7/5 고정**(키우면 윈도우 사이 구멍 — `src/api/CLAUDE.md`). 가드 `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`.
- ⚠️ `existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD(=50)` → 100일 단발(`_DAILY_LOAD_FETCH_DAYS`) = **225 > 50 인 한 도달 불가**한 구조적 폴백(목표 깊이 < 50 이면 부활 — 관계 핀 `test_cycle302...::test_g302_8b_deep_target_dominates_incremental_threshold`).
- ⚠️ **상장 이력 < 225 영업일 종목은 수렴 안 함**(매일 밤 3콜, 자본 위험 0). 관측 = `[stock_master_daily_load_summary]` `mode=`(전량 backfill `full` · 수렴 `incremental` · 혼합 `mixed`)·`elapsed_ms`.
- 읽기 = `db/stock_master_daily.get_recent_daily` 상한 `_MAX_DAILY_ROWS`(400). VCP 깊이 = `daily_fetch_depth_mode`(기본 `"cap100"` = 100봉, `"full"` = `ema_long + base_max_days + 10` — 200일 EMA 실사용은 `"full"`, `strategies/CLAUDE.md` VCP 절).
- backfill 실패 = `failed++` 후 다음 ticker. 🔴 장중 자동 실행 없음(20:30 task + 수동 trigger 뿐).

### 증분 창 — 빈 날 메우기 (cycle417)

적재 대상은 밤마다 바뀐다. 깊이 분기는 행 수만 보므로, 7영업일 넘게 대상 밖에 있다 돌아온 종목은 7봉 창으로 그 사이를 채우지 못한다. 빈 날이 있으면 20일 고가·ATR·EMA 가 그날을 건너뛰고 계산된다. 신선도 게이트(`DAILY_STALENESS_DAYS`)는 마지막 날짜만 봐서 이 구멍을 못 잡는다. 그래서 증분 분기가 빈 날을 보고 창을 넓힌다.

- **판정 = 실행당 1회, 종목 루프 밖** — `today = today_kst()` 뒤 `stock_master_daily.earliest_missing_bas_dd(all_tickers, before=today)`(보호 종목 포함 적재 대상 전부, 쿼리 1회, 종목당 조회 0). 반환 = 빈 날이 있는 종목의 가장 이른 빈 날. 달력·빈 날의 정의 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.
- **창 = 증분 분기(`existing_count >= 225`)에서만 정한다.**
  - 빈 날 없음 → `_DAILY_LOAD_INCREMENTAL_DAYS`(=7).
  - 빈 날 있음 → `min(max(_gap_fill_need_days(빈 날, today), 7), _DAILY_LOAD_FETCH_DAYS(=100))`.
  - `_gap_fill_need_days(earliest_missing, today)` = 빈 날부터 오늘까지 **평일 수(양 끝 포함, 휴일 미차감)** + `_DAILY_LOAD_GAP_MARGIN_DAYS`(=2). 순수 함수(KIS·DB 0).
  - 휴일을 빼지 않는 이유 = `fetch_daily_candles` 는 최근 N봉(`output[:N]`)만 준다. N 이 크면 빈 날을 반드시 덮고, 작으면 놓친다. 남는 봉은 upsert 멱등이 흡수한다.
- 🔴 **KIS 호출 수는 그대로 종목당 1콜이다** — 창만 넓힌다(수렴 가드 G-302-3 그대로). 🔴 이 경로(적재 함수·`_gap_fill_need_days`)에서 휴장 조회(`trading_calendar`·`is_trading_day`)와 `kis_get` 을 부르지 않는다(AST 가드 A3).
- **그대로인 것** — 깊은 backfill 분기(< 225, 빈 날과 무관) · `skipped_fresh`(오늘 봉이 있으면 빈 날이 있어도 skip, 다음 밤에 메운다) · `force`(skip 만 우회) · 보호 종목 규약과 `[daily_load_protected_forced]` · `_drop_today_bars` · upsert `ON CONFLICT DO UPDATE`.
- **100 영업일보다 오래된 빈 날** = 100봉만 받아 최근 쪽만 채운다(`beyond_horizon` 으로 센다).
- **KIS 가 봉을 주지 않는 날(거래정지 등)** = 빈 날이 남아 밤마다 넓은 창을 다시 요청한다. 호출은 1콜 그대로이고 창은 100 에서 멈춘다. 그날이 달력(최근 `GAP_HORIZON`=100개) 밖으로 밀리면 판정에서 빠진다.
- **fail-open** — 판정 예외 = 전 종목 7 + `[daily_load_gap_fill_skipped] reason=gap_scan_error` WARNING **실행당 1행** + `errors=1`. 값이 날짜가 아니면 그 종목만 7 + `errors` 증가(같은 WARNING, 실행당 1행). 적재 대상 밖 키는 버린다. 판정 실패는 `failed`(KIS 실패 전용)에 세지 않는다.
- **관측** = `[daily_load_gap_fill] tickers=%d widened=%d max_fetch_days=%d beyond_horizon=%d errors=%d` **실행당 1행** INFO(종목당 금지) + `summary["gap_fill"]`(같은 5칸, int).
  - 빈 날이 0 이어도 1행 남긴다 — 「판정이 돌았고 0」 과 「판정이 안 돌았다」 를 가른다. 종목 루프 뒤에 남기므로 `candidates=0` 조기 return 이면 0행이다.
  - `tickers` = 빈 날을 보고받은 적재 대상 종목 수. `widened` = 7 보다 큰 창을 요청한 종목 수. 둘은 다를 수 있다(fresh skip·깊은 backfill 종목, 필요 창 ≤ 7 인 종목은 넓히지 않는다).
  - `max_fetch_days` = 넓힌 창의 최댓값(`widened=0` 이면 0). `beyond_horizon` = 필요 창 > 100 이라 100 으로 자른 종목 수(정확히 100 은 아니다). `errors` = fail-open 수.
  - ⚠️ `beyond_horizon` 은 평일 과대 계산이라 실제로는 100봉 안에 드는 빈 날도 셀 수 있다.
- **알려진 한계** — 그날 전체 행 수가 `GAP_CALENDAR_MIN_ROWS`(300) 미만인 날(대규모 적재 실패일)은 달력에 없어 그날의 빈 날을 못 잡는다(7영업일 안이면 다음 밤 7봉 창이 덮는다). 첫 행보다 오래된 이력 부족(신규 상장·retention)은 깊은 backfill 의 몫이다.
- 가드 `tests/unit/engine/test_cycle417_daily_gap_fill.py` · `tests/unit/db/test_cycle417_gap_scan_contract.py` · `tests/integration/test_cycle417_daily_gap_scan_pg.py`.

### 확정 전 오늘봉 시각 필터 (`_drop_today_bars`)

`_stock_master_daily_load_once` 는 `fetched += 1` **뒤** · `upsert_batch` **앞**에서 `_drop_today_bars(candles, now_kst=load_now_kst, today=today)` 로 확정 전 오늘봉 폐기 — 두 fetch 분기(`fetch_daily_candles` / `fetch_daily_candles_backfill`) **합류점**이고 `fetched`(KIS 응답)·`failed`(KIS 실패 전용) 의미가 보존되는 유일한 자리.

- **판정 = 시각 단독.** `load_now_kst`(= `datetime.now(KST_TZ)`, **함수 진입 1회** — `stock_master.list_all` 페이징 *앞*, tz-aware 필수)가 `_DAILY_LOAD_TODAY_BAR_CUTOFF`(= `time(20, 0)` — KRX 애프터마켓 종료, 그 전 당일 거래량은 부분값) **이전** = `bas_dd >= today` 폐기, 이후 = `bas_dd > today`(시계 왜곡 방어)만 폐기. `bas_dd` 파싱 불가·부재 = **보존**. 20:00 뒤 D 봉 = 거래량 확정, 종가·고저 잠정.
- 🔴 **커트오프 = scanner 전용 상수**(값이 같아도 scheduler 매매·보드 시각 상수 재사용 금지 — 보드 시각 변경이 적재 규약을 딸려 바꾸는 커플링 차단, `tradable_boards` ↔ 청산 규약 분리와 같은 원칙). `scanner` 가 `scheduler` 를 import 하면 값의 일치가 우연이 아니라 커플링이 된다.
- ⚠️ **데이터 기준(거래량 0 ∧ OHLC 평탄) 금지** — 장중 재시작 **부분봉**(거래량>0·비평탄)은 통과시키고 거래정지 종목의 **진짜 평탄 확정봉**은 죽인다. 시각 기준은 둘 다 처리.
- **fail-open** — 판정 예외 = 전량 upsert + `[daily_load_today_filter_skipped]` WARNING **실행당 1행**(fail-closed 금지 — 유령 키가 두 전략을 전 기간 체결 0건으로 만든 방향). 실패 단위 = **캔들**(`isinstance(candle, dict)` 방어 — 이상 원소 하나가 종목 필터 전체를 무력화하지 않게).
- **수동 실행(`POST /api/stock-master/daily/refresh`, 기본 `force=true`)도 필터 통과** — `force` 는 `latest >= today` 멱등 skip **만** 우회(장중·시간외 수동 실행만 잠정봉을 버린다).
- **관측** = `[daily_load_today_bar_filter]` 실행당 1행 INFO(`mode` / `cutoff` / `now` / `today` / `dropped_rows` / `tickers_affected` / `filter_errors`, 종목당 금지). `dropped_rows`(행) ≠ `tickers_affected`(종목). `filter_errors > 0` = fail-open 발생(없으면 `dropped_rows=0` 이 「버릴 봉 없음」·「필터 전멸」을 못 가른다). `candidates=0` 조기 return 이면 0행 — `[stock_master_daily_load_begin] candidates=` 를 먼저 본다. `mode=` = 20:00 경계 keep/drop.
- **D 봉 확정 경로 둘** — 1차 = 다음 거래일 아침 부팅 `daily_bar_finalize`(DB 행 기준 — 유니버스 밖 종목도). 2차 = D+1 20:30 정기 실행 증분 창(하한 `_DAILY_LOAD_INCREMENTAL_DAYS`=7 → `ON CONFLICT DO UPDATE`, 유니버스 안만). 🔴 7일 하한을 1~2일로 줄이지 않는다 — 1차가 꺼졌거나(`daily_bar_finalize_mode=off`) 실패한 날의 안전망(가드 cycle263 G2 「보정 창 존치」).
- **부작용** — 신규 상장·유니버스 진입 종목 backfill = 같은 날 20:30(그 사이 `get_recent_daily_normalized` = `reason="miss"` KIS 폴백, 장중 KIS 호출 증가). UI `last_daily_load_at` 은 낮 동안 어제 날짜.
- 가드 `tests/unit/engine/test_cycle263_daily_load_stub_filter.py` + `tests/unit/ast/test_cycle193_ast_fresh_gate.py`.

### 일봉 적재 본체

- 호출 = `_stock_master_daily_load_task_loop`, 매일 20:30 KST 1회.
- lifecycle = `run_periodic_task_loop`(`start()` 직후 즉시 1회 — 영업일 슬롯 게이트 — + 매일 20:30). `stop` 계열 3곳이 `_stock_master_daily_load_task` cancel(`tests/unit/engine/test_scheduler_stop_zombie_tasks.py` `expected_members` 가 잠금).
- 종목별 `max_bas_dd(ticker) == 오늘` = skip(멱등, `force` 우회), 그 밖 = 위 깊이 분기.
- KIS `fetch_daily_candles` / `fetch_daily_candles_backfill`(`src/api/condition.py`) **재사용** → `stock_master_daily.upsert_batch(ticker, rows)`.
- KIS 거부·타임아웃 = 그 ticker skip. upsert 실패 = `[stock_master_daily_load_skip] ticker= reason=upsert_batch_failed` WARNING + `db_write_failures`(KIS `failed` 와 분리).
- 요약 = `[stock_master_daily_load_summary] total= fetched= upserted_rows= skipped_fresh= failed= elapsed_ms= mode=` 1행 INFO(`data_load_tasks.py` 서식). `failed` = KIS 실패만, `db_write_failures` = 반환 dict·진행 state 에만(`refresh_progress` `failed` = 둘의 합). 500건마다 진행 emit.
- 어댑터 `get_recent_daily_normalized`(`src/db/stock_master_daily.py`) 소비 = 전략 6파일 `prepare()`(`expected_head` 전달) · kojiro `recompute_held_atr` · `llm_buy_gate`(뒤 둘은 인자 없이 달력 판정). 신선도 계약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.

### 전일 잠정 봉 확정 (`daily_bar_finalize.py`, 부팅 prepare 직전)

다음 거래일 아침 부팅이 prepare 직전에 잠정 봉(위 「시각과 순서」)만 골라 KIS(적재와 같은 FHKST03010100 시장 `J`)에서 다시 받아 덮는다. 20:30 적재 무변경, 새 컬럼·새 KIS API 없음. 명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8.

**배선** — `boot_manager.boot()` 안 두 자리(`scheduler.py`·`scanner.py` 0줄):
- 토큰 발급 직후 `daily_bar_finalize.spawn(phase="boot")` — 띄우기만, 설정 로드·잔고·레짐(최대 25초)·자금 배분·`count_active` 대기와 겹쳐 돈다.
- `emit_daily_head_staleness()` 바로 앞 `wait_for_boot(task, budget_secs=BOOT_BUDGET_SECS)` → prepare 가 확정 봉을 읽는다.
- 순서 `get_token` < `spawn` < `wait_for_boot` < `emit_daily_head_staleness` < prepare = AST G5(a).

**상수**

| 상수 | 값 | 뜻 |
|---|---|---|
| `FINAL_BOUNDARY_TIME` | `time(6, 0)` | 확정 경계 = 봉 다음 날 06:00 KST. 관측된 가장 늦은 「아직 바뀌는 중」(05:28)에 32분 여유 |
| `WINDOW_CAL_DAYS` | 21 | 대상 조회 창 — `since = 오늘 − 21일` |
| `MAX_SPAN_CAL_DAYS` | 130 | 종목당 1회 호출 구간 상한(KIS 100봉 한도 안) |
| `RANGE_PAD_CAL_DAYS` | 10 | 받는 구간 앞 여유 — 교차검증에 헤드 앞 봉이 필요하다 |
| `BOOT_WORKERS` | 3 | 부팅 대기 중 동시 일꾼 수 |
| `BOOT_BUDGET_SECS` | 90 | 부팅이 기다리는 상한 |
| `BG_SLEEP_SECS` | 0.05 | 예산을 넘긴 뒤 배경 일꾼이 종목 사이에 쉬는 시간(약 7건/초) |
| `HARD_CAP_SECS` | 600 | 확정 시작부터 이 시간이 지나면 멈춘다 |

- 관계(AST G6) = `WINDOW_CAL_DAYS + RANGE_PAD_CAL_DAYS ≤ MAX_SPAN_CAL_DAYS ≤ 140` · `1 ≤ BOOT_WORKERS ≤ 20` · `0 < BOOT_BUDGET_SECS < HARD_CAP_SECS`.
- 배경 일꾼 수 상수 없음(전환 뒤 `_run_workers` 가 0번 일꾼만 남긴다).

**잠정 판정 = `updated_at` 하나** — `stock_master_daily.list_provisional_rows(*, since, head, today_boundary)` SQL(`updated_at` 규약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절).
- 헤드 `head` = `stock_master_daily.max_bas_dd_before(오늘)` = `max(bas_dd) WHERE bas_dd < 오늘`(KST; 오늘·미래 봉 제외 = 껍데기 봉 방어, 휴장일 달력 미사용).
- 헤드 조회 예외 미흡수(`result=error stage=head`). `None`(오늘 앞 봉 0) = `result=noop`, `head=` 빈 값.
- 헤드 행 = `updated_at < 오늘 06:00` 이면 잠정, 헤드보다 옛 행 = `updated_at < (bas_dd + 1일) 06:00 KST` 이면 잠정(헤드가 더 보수적 — 주말·연휴 쓰기의 확정 여부를 모르고, prepare 직독 행이라 재수신이 싸다).
- 같은 날 재기동 = 대상 0(아침에 덮은 행은 `updated_at` 06:00 뒤). 00:00~06:00 수동 기동도 안전(그때 쓴 행은 잠정으로 남아 다음 부팅이 재수신 — `start()` 는 20:00 이후만 거부).

**흐름 — `finalize_once(*, now_kst=None, phase)`**
1. 모드(아래 킬스위치) — `off` = `result=noop` 1행 후 끝.
2. 대상 조회 → 종목별 `oldest`·`newest`(헤드보다 뒤 행 버림).
3. 순서 = ① `069500`·`229200`(시장 유닛·ETF 레짐 입력) ② DB `positions` 보유 종목(청산 입력 ATR·스테이지) ③ 나머지 `newest` 내림차순 → 종목코드순(예산 초과여도 헤드 먼저). 보유 조회 실패 = ② 생략.
4. 받기 = `condition.fetch_daily_chart_ranged_with_summary(ticker, start, end)`, `start = oldest − 10일` · `end = newest`(항상 헤드 이하 = **오늘 봉 미수신**, AST G5 d). 130일 초과 = `start = newest − 130일` + `span_clipped`. `[start, newest]` 밖 봉 버림.
5. 교차검증(`newest` = 헤드일 때만) — `prdy` = `output1.stck_prdy_clpr`. `prdy` == 헤드 봉 종가 → `verified` · == 헤드 앞 봉 종가 → `unrolled`(KIS 요약 날짜 미전환 — 시각 기준으로 받아 쓴다) · 그 밖 → `mismatch` · 헤드 봉 없음 → `missing` · 빈 응답·KIS 예외 → `failed`. **`mismatch`·`missing`·`failed` 종목은 쓰지 않는다.**
6. 쓰기(`enforce`) = 기존 `stock_master_daily.upsert_batch(ticker, 받은 봉 전부)`(새 쓰기 SQL 없음). 쓰기 전 DB 와 비교해 잠정 행 중 바뀐 행 = `close_changed`·`hl_changed`. upsert 예외·반환 수 < 보낸 수 = `db_write_failures`. `observe` = 받고 비교만.

**예산과 배경**
- `wait_for_boot` = `asyncio.wait_for(asyncio.shield(task), timeout=budget_secs)` — 부팅을 멈추지 않는다(태스크 없음 = 즉시 반환, 예산 초과 = 태스크를 **취소하지 않고** 배경 전환 신호만 켜고 반환). 태스크 예외 = WARNING 후 흡수.
- 전환 뒤 첫 일꾼 `result=budget_exceeded` WARNING 1행 → 0번 일꾼 하나가 `BG_SLEEP_SECS` 간격으로 나머지 → 끝에 `phase=background` 요약 1행. 확정 시작 + `HARD_CAP_SECS` = 멈춤 + `result=hard_cap`(판정은 종목 사이). 태스크 참조 = 모듈 전역 `_BG_TASKS`(`funnel_capture._BG_TASKS` 관례).
- `CancelledError` = 부팅 자신의 취소 요청(`asyncio.current_task().cancelling() > 0`)일 때만 전파. 확정 태스크만 외부 취소 = WARNING `wait_for_boot 확정 태스크가 외부에서 취소됐다` 후 부팅 계속(`shield` 는 확정 태스크 자신의 취소를 올려 보낸다).
- 호출 = `kis_get_quote`(시세 풀), 전역 20건/초(`src/api/base.py` `_rate_limit`)를 주문과 공유. 부팅 대기 = 3 일꾼, 배경 = 1 일꾼 + 0.05초(약 7건/초, 20:30 적재 보폭).

**실패 방향 — 매수를 막지 않고(fail-open), 잠정 값을 조용히 쓰지도 않는다(개수 + 표본을 마커에).**
- 🔴 종목 단위 매수 후보 제외 금지(유령 키가 두 전략을 전 기간 체결 0건으로 만든 fail-closed 방향).
- `finalize_once` 는 `CancelledError` 외 예외를 내지 않는다(단계별 `try` 밖 = 바깥 `try`, `stage=unexpected`).
- 일꾼 하나가 미포착 예외로 죽으면 `_run_workers` 가 나머지를 취소·대기 후 재발생(`stage=processing` 요약 뒤엔 어떤 일꾼도 쓰지 않는다).
- 실패 종목 = 잠정 유지 → 다음 부팅(창 21일)·D+1 20:30 7일 창이 재수신.

**킬스위치 `system_config.daily_bar_finalize_mode`** — 키 없음 = `enforce` · `observe`(받고 비교만) · `off` · 모양 틀린 행 = `observe` · 조회 실패 = `enforce`(요약 `mode=enforce(db_error)` — KIS 확정값이라 고치는 쪽이 안전). 판정 = `system_config._select_value`·`_string_from_raw` 재사용(cycle369 `status_exit_mode` 와 동일). `finalize_once` 시작마다 읽음 = **다음 부팅부터** 반영. 🔴 운영 DB 쓰기 = 승인 대상. 롤백 = `daily_bar_finalize_mode = 'off'`(승인 대상) 또는 커밋 되돌리기(쓴 값은 KIS 확정값이라 데이터 원복 불필요).

**마커**
- `[daily_bar_finalize] phase=boot|background mode= result=ok|noop|budget_exceeded|hard_cap|error [stage=] head= since= targets= fetched= upserted_rows= close_changed= hl_changed= verified= unrolled= mismatch= missing= failed= db_write_failures= span_clipped= pending= elapsed_ms= [sample_failed=<≤5>] [sample_mismatch=<≤5>]` — 실행당 1행(예산 초과일 = `budget_exceeded` + `phase=background` 2행). 요약 없는 경로 = 취소(`CancelledError`) 하나.
- **INFO = `result` ∈ {`ok`, `noop`} ∧ `failed`·`missing`·`mismatch`·`db_write_failures` 전부 0**, 그 밖 WARNING. `noop`(대상 0)도 1행(「안 돌았다」 ≠ 「고칠 것 없음」).
- `stage=`(`result=error` 때만) = `head`(헤드 조회 실패) · `select`(대상 조회 실패) · `processing`(일꾼 예외 — 나머지 정지 후, traceback) · `unexpected`(그 밖 — 대상 묶기·순서 등, traceback). `head`·`select` = 아무것도 안 고침. `mode=off` 아닌데 `result=noop head=`(빈 값) = 테이블에 오늘 앞 봉 없음.
- `unrolled` ≠ 실패(「`stck_prdy_clpr` 가 D 로 넘어가는 시각」 표본).
- 두 번째 눈 = `[prev_close_overwrite]`(`src/api/CLAUDE.md` `condition.py` 절) — 09:30 급등 스캔이 `ticker_prev_close` 를 덮을 때 값이 다른 종목.
- 성공 서명 = 07:45 기동 → 07:46~07:47 `phase=boot result=ok` 1행 · `close_changed` ≈ `targets` 의 40~60%(예상, 단위 다름 — `targets` 종목 · `close_changed` 행) · `[prev_close_overwrite]` = 권리락·배당락 외 0.
- 판독 = `unrolled` 대부분 ∧ `close_changed` ≈ 0 → 부팅 시각까지 KIS 미전환(아래 한계 1).

**시각 불변식(AST G7)** — `TIME_SESSION_START_CUTOFF`(20:00) + `HARD_CAP_SECS` ≤ `TIME_STOCK_MASTER_DAILY_LOAD`(20:30) < `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` − 10분(가장 늦은 부팅 19:59 도 20:10 전에 끝나 20:30 적재·20:35~ 보조 토큰 창과 안 겹친다).

**부팅 시간** — 최대 `BOOT_BUDGET_SECS`(90초) 늘고(평시 약 +20~45초 예상) +600초 레거시 재준비(「funnel 스냅샷 캡처」)도 그만큼 밀린다 — 07:45 기동 최악 ≈07:59:45 종료(08:00 NXT 프리장 여유 얇음, `elapsed_ms` 로 확인).

**다른 장치와의 관계**
- 예산 초과일 = 부팅 prepare 가 확정 전 종목을 읽고, +600초 레거시 재준비가 확정 DB 로 후보를 다시 만든다(배경은 확정 시작 + 600초에 반드시 끝나고 레거시는 그 뒤). 🔴 S2 가 레거시 분기를 없앨 때 이 역할을 넘겨받아야 한다.
- 전략 객체(`_candidates`·`_held_stage3`·`_entry_atr` …) 무접촉 — DB 만(cycle364 PV-1 과 교집합 0, 진입 ATR 스탬프 불변). 확정 봉 기반 트레일링 ATR·kojiro 스테이지 재계산 = 원래 부팅 prepare 몫.
- 시장 유닛 = 4전략 prepare 안이라 확정값(`069500` = 순서 ①). ETF 레짐(관찰 전용)은 prepare **앞**(`_refresh_market_regime_and_persist`)이라 잠정 종가를 읽을 수 있다.
- 부팅 즉시 일봉 적재(`start()` + 240초, 전날 20:30 결손일만)와 겹쳐도 결과 동일(같은 아침 KIS 값·같은 upsert).
- `_drop_today_bars`·cycle363 `expected_head` 무변경(헤드 날짜 그대로, 값만 바뀐다). ④ `[funnel_boot_vs_evening]` 영향 = 「funnel 스냅샷 캡처」 ④.

**알려진 한계**
1. 06:00 경계 = 표본 두 묶음 기준. KIS 야간 처리가 부팅보다 늦는 날은 잠정 값을 받아 쓰고 그 행이 확정으로 분류된다 — `output1` 이 넘어가 있으면 `mismatch`, 둘 다 미전환(`unrolled` 대부분)이면 D+1 20:30 7일 창이 덮는다.
2. 권리락·배당락일 = 전일종가 ≠ 기준가라 `mismatch` 가능 — 그 종목의 직전 잠정 봉은 쓰지 않고 남는다(`daily_bar_finalize.py` mismatch 분기). 락 표시는 락일 봉에만 붙고 그 봉은 그날 20:30 에야 DB 에 들어오므로, **락일 당일 아침에는** 락 게이트 `_row_has_lock` 의 prepare KIS 폴백이 걸리지 않는다. 잠정 봉은 D+1 7일 창이 덮는다.
3. 수정주가(`FID_ORG_ADJ_PRC="0"`)로 덮어 그 사이 액면분할 등이 있으면 덮은 구간과 앞 DB 봉의 기준이 다를 수 있다(창 21일 제한 이유).
4. 21일보다 옛 잠정 봉은 대상이 아니다.

**테스트 격리** — autouse `tests/conftest.py::_neutralize_daily_bar_finalize` 가 `finalize_once` 를 빈 코루틴으로 교체(`spawn`·`wait_for_boot` 실물 — 배선은 돈다).
- 🔴 `spawn` 은 `finalize_once` 를 **모듈 전역 이름으로** 호출(미리 묶으면 중립화가 새어 실제 DB·KIS 접촉, G9-5).
- leaf 직접 검증만 마커 `real_daily_bar_finalize` 옵트아웃(허용 목록 G9-6).

**가드·회귀**
- `tests/unit/ast/test_cycle386_ast_finalize.py` — G5(부팅 순서 · import 제약 · `stock_master_daily` 쓰기는 `_UPSERT_DAILY_SQL` 하나 · naive 벽시계 0) · G6(상수) · G7(시각).
- `tests/unit/engine/test_cycle386_daily_bar_finalize.py` — G2(쓰기·비교·교차검증·모드) · G3(실패 경로) · G4(예산·배경·하드캡).
- `tests/unit/engine/strategies/test_cycle386_prev_close_regression.py` — G8(잠정·확정 전일종가로 momentum·LTV·VB 판정이 갈리는 실사례가 확정 뒤 정규장 기준으로 복귀).
- `tests/unit/engine/test_cycle386_finalize_neutralization.py`(G9) · `tests/unit/db/test_cycle386_list_provisional_rows.py` · `tests/unit/api/test_cycle386_daily_chart_summary.py`.
- 실 Postgres `tests/integration/test_cycle386_provisional_predicate_pg.py` — G1 경계 · 세션 시간대 무관 · `updated_at` 재기록 트리거 없음 · 같은 날 재기동 noop · 오늘·미래 행이 있어도 헤드 = 오늘 앞 최신 봉(`max_bas_dd_before` 실 SQL).

### basics 갱신 (`_stock_master_basics_refresh_once`)

- `stock_master.list_all()` 페이징(PAGE_SIZE=1000) → `inquire_stock_basics()`(CTPF1002R + FHKST01010100 merge) → `stock_master.upsert_one()`.
- 🔴 **기존 raw 머지 보존** — `list_all` 로드 때 `existing_raw_by_ticker` 에 기존 `raw` 보관, upsert **전** 새 raw 가 dict ∧ 기존 비지 않음 → `{**기존, **신규}`. 안 하면 개장 전 FHKST `acml_tr_pbmn=0` 이 `_ZERO_VALUE_SKIP_KEYS` 로 빠지고 `upsert_one` 이 raw 를 통째로 교체 → **거래대금 15키 매일 소실**(VB·LTV·donchian·BFB universe 0). bare object(`model_copy`/`raw` 부재) = `getattr` graceful.
- Rate Limit `await asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS = 0.05)`.
- KIS 거부 = `[stock_master_basics_refresh_skip] ticker=X reason=Y` WARNING + `failed++` 후 continue.
- 500건마다 `[stock_master_basics_refresh]` INFO + 종료 `[stock_master_basics_refresh_summary] total= updated= skipped= failed= elapsed_ms=` 1행. 전량 약 13분.

### 마스터 적재 (`_stock_master_master_load_once`)

- KIS 공식 마스터 파일(`src/api/kis_master.py`) 다운로드 → `master_raw` 배치 upsert → `refresh_progress` 갱신, graceful.
- 지수 편입 = `kospi200_apnt_cls_code != ""` → `is_kospi200=True` / `ksq150_nmix_yn == "Y"` → `is_kosdaq150=True` → `upsert_master_raw(ticker, record, is_kospi200=, is_kosdaq150=)`.
- 🔴 `master_raw` 는 `raw` 와 **별도 컬럼**이다(raw 영역 절대 보호, G-AST1).
- 소비 = `stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True)`(둘 다 True = OR, 한쪽 = 단독, 둘 다 None = 무필터) → donchian `_scan_universe` `FUNNEL_STAGES[0]` "코스피200+코스닥150 합집합". 컬럼 = `src/db/CLAUDE.md`.
- 🔴 시총 헬퍼 3종(`market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions`) **부재**(재도입 차단 AST `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py`). 시총 필터 = `list_by_filter`/`list_paged_by_filter` 직접.

### 재무 적재 (`_stock_master_financial_load_once`)

- 주1회 재무 5 TR(`src/api/finance.py`). 유니버스 = `_is_daily_load_universe` 자격 종목. `stock_master_financial.max_stac_yymm` 신선도 skip → `fetch_all_financials` → `upsert_financial_batch`.
- `[stock_master_financial_load_summary] total= updated= skipped= failed=` emit. graceful.
- loop = `run_periodic_task_loop`(`initial_delay_secs=900` + `immediate_skip_if_fresh_hours=168`), `task_label="stock_master_financial_load"`, `task_attrs` 4 위치, `refresh_progress` TaskKey `"financial"`.
- 매수 경로 무접촉(진입 **전** 데이터 계층).

### 매수 진입 차단 (`_is_master_blocked_for_entry`)

`master_raw` 우선 · `raw` 폴백 **7건**: `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기(KOSDAQ 전용). 🔴 **매수 진입 전 차단 — 기보유 종목 무영향.**

## funnel 스냅샷 캡처

캡처 = **라이브 전략 객체 메모리**(`_funnel_steps`·`get_scanned_tickers()`) → DB `strategy_funnel_snapshots`. 매매 무관 관찰 경로지만 같은 객체를 준비(`prepare`)가 다시 채우므로 **준비·캡처 순서와 라벨**이 계약.

### 공통 헬퍼와 호출처

- `capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None, skipped_out=None, protect_confirmed=False) -> int` — `label = target_date or 오늘(KST)`. 전략마다 `funnel_capture.capture_skip_reason(strategy, label, today, is_provisional=...)` 통과분만 `_funnel_steps` 단계별 + `step_no=99` 를 `target_date=label` insert(전략별 예외 격리, momentum 영구 제외, in-place upsert). 완료 로그 `[funnel_snapshot] 캡처 완료 — target_date= saved= provisional= skipped=<sid:사유,…>`. `skipped_out` dict = `{sid: 사유}` 채움(반환값 무관, 수동 trigger 전용). `protect_confirmed` = 두 insert 에 그대로 전달(cycle408-L1, 아래 09:30 자동만 `True`).
- 호출처 3:
  - 09:30 자동 `_auto_capture_funnel_snapshots`, `is_provisional=False`, `target_date=today_kst()`, `protect_confirmed=True`(`_scan_loop` 첫 패스 = 첫 `SCAN_INTERVAL` 뒤 ≈09:35).
  - 저녁 `_evening_funnel_capture_once` → `funnel_capture.evening_capture_once(self)`, `is_provisional=True`(21:00 정기 = `target_date=다음 거래일`, 레거시 분기 = 오늘).
  - 수동 trigger `routes/strategy_funnel.py::trigger_snapshot`, `is_provisional=False`, `target_date` 없음 = 오늘.

### 라이브 준비는 wrapper 한 곳에서, 한 번에 하나

- 라이브 `prepare()` = `funnel_capture.live_prepare_one(strategy, *, phase)` · `live_prepare_many(strategies, *, as_of, phase)` 로만. `phase` = `boot`(`boot_manager`) · `presubscribe`(07:59 사전 구독 직전, 후보가 빈 VB/LTV·스윙) · `intraday_empty`(`_reprepare_breakout_if_empty`) · `evening`(21:00) · `reprepare_legacy`(레거시 분기). 가드 `test_cycle364_ast_live_prepare_lock.py`(`src/engine` 중 `strategies/**`·`funnel_capture.py` 밖 `.prepare(` 직접 호출·`getattr(X, "prepare")` = 0).
- 잠금 = 이벤트 루프별 `asyncio.Lock` 하나(`_lock()`, 같은 객체 `_funnel_steps`/`_candidates` 혼선 차단). `live_prepare_many` = 전략마다 잡고 푼다.
- never-raise — `prepare()` 예외 = wrapper 흡수 → `False` + `[live_prepare] <sid> phase=<phase> 전략 prepare 실패`(phase=boot) / `… 재 prepare 실패`(그 밖) ERROR + traceback(옛 문구 = grep 연속성). 호출부 try/except 없음. `_reprepare_breakout_if_empty` 는 `False` 면 `write_log("ERROR", "<sid> 재 prepare 실패")` 한 줄만 추가. 🔴 거기서 logger ERROR 재기록 금지(ERROR 2행 → `top_patterns` 배가).
- meta = `_live_prepare_meta = {as_of, phase, started_at, finished_at, ok}` — **시작 시 `ok=None`**, 종료 시 `ok`(bool)·`finished_at`. `as_of` 미지정 = 시작 KST 날짜. 전략 코드는 읽지도 쓰지도 않는다.

### 캡처 라벨 가드 — `capture_skip_reason`

위에서부터 첫 해당에서 멈춘다. `None` = 캡처.

1. meta 가 dict 가 아님 → `label == 오늘` 이면 `None`, 아니면 `no_meta`
2. `ok is False` → `prepare_failed`
3. `ok is not True`(시작만 찍혔다) → `in_progress` — 반쯤 만든 목록을 저장하지 않는다
4. `meta["as_of"] != label` → `as_of_mismatch`
5. 확정 캡처(`is_provisional=False`)인데 `meta["phase"] == "evening"` → `evening_preview_reject`

5 의 이유 = 자정 뒤 저녁 meta `as_of` 가 새 오늘과 같아져 4 를 통과 → 00:xx 수동 캡처가 저녁 미리보기를 **확정** 행으로 저장. 수동 캡처는 건너뛴 전략·사유를 응답 `message` 에(응답 키 불변 — `src/routes/CLAUDE.md`).

### 저녁 미리보기 — 21:00 정기 실행

- task = `_evening_funnel_capture_task_loop` → `data_load_tasks.evening_funnel_capture_task_loop` → `run_periodic_task_loop(wait_time=TIME_EVENING_FUNNEL_CAPTURE, initial_delay_secs=600)`.
- 🔴 **21:00 인 이유와 금기** — 20:30 일봉 적재 뒤(D 봉을 「전일」로) · 20:45 보조 7계정 토큰 강제 재발급(`quote_token_refresh`) 직렬화 창 [20:35, 20:53] 밖(보조 풀 REST 가 겹치면 발급 수 2배) · 21:30 정산 전. **20:30~20:55 로 당기지 않는다.** 가드 = `test_cycle364_time_invariants.py`(적재 < 캡처 · `TIME_QUOTE_TOKEN_REFRESH + 15분 ≤ 캡처` · 캡처 + `EVENING_START_DEADLINE` + 준비 예산 3분 ≤ `TIME_SETTLEMENT`) + `test_cycle273…::test_g273f_2` · `test_cycle269…::test_c9`.
- 흐름(`evening_capture_once`, 시각 ≥ 21:00):
  1. 30초(`EVENING_POLL_SECS`) 폴링, 시작 마감 = 캡처 시각 + `EVENING_START_DEADLINE`(15분) = **21:15**.
  2. 회차마다 달력 재판정 — `is_open_day(오늘)` `False` = 즉시 `decision=skip reason=today_closed`(INFO). `True` = `resolve_as_of(now, "evening")` → `as_of = next_trading_day(오늘)` · `expected_head = 오늘`(`mode="evening"` 만, 모르면 `None`).
  3. 적재 완료 = `system_config.get_task_last_success("stock_master_daily_load")` ≥ **오늘 `TIME_STOCK_MASTER_DAILY_LOAD`(20:30) KST**(`_marker_done`). 날짜만 같은 마커(부팅 보충 적재 07:5x)·naive 마커 ≠ 완료(받으면 적재 실패일에 D-1 헤드로 돈다).
  4. 21:15 까지 미준비 = 건너뜀(준비 미호출) — 달력 모름 `reason=calendar_unknown` / 마커 없음 `reason=daily_load_not_done`, 둘 다 **WARNING**. 🔴 추측 날짜로 라벨 금지(다음 부팅이 정본 목록). 🔴 대기 신호를 `count_all() > 0` 으로 되돌리지 않는다(그날 적재를 기다리지 않는다).
  5. `live_prepare_many(…, as_of=as_of, phase="evening")` — 대상 `registry.all()`(비활성 포함), 순서 = 활성 먼저, 그 안에서 VB → LTV → BFB → VCP → donchian → kojiro → momentum → 그 밖.
  6. `capture_funnel_snapshots(registry, is_provisional=True, target_date=as_of)`.
- 요약 1행 `[evening_funnel_capture] decision=run|skip|legacy_reprepare reason= as_of= expected_head= load_marker= daily_head= prepared= saved= skipped=<sid:prepare_failed,…>`. `daily_head` = `stock_master_daily.max_bas_dd()`(인덱스 컬럼) 1회, 폴링 루프 밖, 실패 `None`.
- 🔴 **PV-1 전제** — 미리보기 준비가 보유 종목 청산 입력(kojiro `_held_stage3`, 네 전략 `_candidates` 보유 엔트리)을 바꾸면 야간 틱 하나로 청산이 나갈 수 있다(20:00 뒤에도 stale watcher 가 보유를 HIGH 재구독). 계약 = `strategies/CLAUDE.md` 「prepare 공통」.
- 미리보기 준비 상태는 21:30 정산 뒤에도 메모리 잔류(`_reset_daily_state` 는 후보·`_funnel_steps`·`_scanned_tickers` 미삭제) → 다음 부팅까지 대시보드가 다음 세션 후보를 보인다(활성 전략은 다음 부팅이 재준비).

### 레거시 분기 — 21:00 전 (S1 임시)

- `now.time() < TIME_EVENING_FUNNEL_CAPTURE` 이면 이 분기 — 실제로는 `start()` +600초 즉시 1회(`immediate_first_run` 기본, 게이트 kw 전무, 07:45 기동 ≈07:57). `run_daily` 가 거래일마다 `start()` 를 다시 불러 매일 돈다. 오후 재기동(16:00~20:00) +600초도 이 분기.
- 동작 = 미리보기 아님: `registry.all()` 전부 `as_of=None`(오늘) 재준비(`phase="reprepare_legacy"`) + 오늘 라벨 잠정(`is_provisional=True`) 행. 로그 `[evening_funnel_capture] decision=legacy_reprepare reason=boot_immediate_run …`. 살아 있는 후보를 교체하므로 이후 매수 평가가 이 결과를 쓴다.
  - **입력 = 부팅 준비와 같다** — 부팅 준비(`_boot()` 의 전 전략 `prepare()`)는 `start()` 가 적재 태스크(`_full_universe_load_task` +0초 · `_stock_master_daily_load_task` +240초 · `_stock_master_basics_refresh_task` +480초)를 만들기 **전에** 끝나고, 그 즉시 실행은 영업일 슬롯 게이트 통과 시만(평상시 월요일·연휴 뒤 아침 = 미실행 = 같은 목록).
  - **보충 적재일**(`reason=stale` 정기 결손 · `calendar_unknown` · full_universe `below_floor`) = 이 재준비가 바뀐 입력을 라이브 후보에 반영 — 순서 보장 아닌 경합(+240초 일봉 보충 적재 **완료**를 기다리지 않는다).
  - 🔴 **이 즉시 1회에 게이트 금지** — 재준비의 `self._candidates = {}` 가 donchian 보유 종목을 후보에서 지워 그날 트레일링 ATR 이 `_entry_atr` 로 떨어지는데, 건너뛰면 부팅 recompute 의 오늘 ATR 로 바뀐다(청산 규약 변화 — cycle360 카드 3 결정 선행, 근거 `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.4·§5).
  - **장전 풀 갱신과 겹쳐도 안전** — 월요일·연휴 뒤 장전 `scanner._scan_pool_eager_refresh_loop`(5분)의 24h 초과 풀 종목 갱신이 +600초 재준비와 동시 시작 가능. 그 갱신은 `upsert_one` 전 basics 와 같은 `{**기존 raw, **신규 raw}` 머지로 장전 0 값 키(`_ZERO_VALUE_SKIP_KEYS` — `acml_tr_pbmn` 등)를 보존(`list_by_filter` 거래대금 임계 `acml_tr_pbmn_won` NULL 방지, cycle363, 사용자 승인 8영역). 판별 = `[scan_pool_eager_refresh] refreshed=N` + `select count(*) from stock_master where not raw ? 'acml_tr_pbmn'`(머지 정상이면 불변). 회귀 = `tests/unit/engine/test_cycle363_scan_pool_eager_refresh_raw_merge.py`.
  - ⚠️ **07:59 사전 구독 재준비가 이 분기 뒤에서 대기 가능** — 같은 잠금, 07:45 기동이면 레거시(≈07:57 시작, 60~75초)가 `TIME_PRESUBSCRIBE`(07:59)에 걸친다(전일 잠정 봉 확정 대기일은 평시 +20~45초·최악 +90초 더). 사전 구독 재준비 = 부팅 뒤 VB/LTV·스윙 후보가 빈 날만. `asyncio.Lock` FIFO → 대기 ≤ 호출당 전략 하나 준비(VCP 약 35초), 그만큼 뒤 사전 구독(보유 포함)·08:00 프리장 진입 지연.
- 🔴 **S2 가 이 분기를 없앤다** — 「입력이 실제로 바뀐 날만」 재준비 판정(②)·완료 대기와 조용한 창(③)·비상 캡처는 **코드 없음**(설계 `_workspace/domain_consult/cycle364_a1_as_of_design.md` §4·§5). 착수 근거 = ④ 평시 `same=1` 실측.

### 하루 쓰기 순서와 확정 행 보호

- 거래일 D 쓰기 = ≈07:57 레거시 `(D, 잠정)` · ≈09:35 자동 `(D, 확정)`(잠정 덮음) · 21:00 `(다음 거래일, 잠정)` — 저녁은 다른 키라 **그날 확정 행 보존**(20:05·21:30 리포트 `strategy_funnel_stages`(D) = 09:35 확정본). 그날 첫 캡처 뒤 재기동하면 하루 1회 게이트(`_auto_funnel_snapshot_done_today`)가 프로세스 메모리라 다시 열려 자동 캡처가 한 번 더 돈다(09:30~15:20 재기동은 부팅 +5분 뒤, 15:20~20:00 재기동은 즉시) — 자동 캡처는 `protect_confirmed=True` 라 **이미 확정된 행은 덮지 않고**(`None`, saved 에 안 셈) 오전에 확정되지 못한 전략의 행만 채운다(cycle408-L1). 수동 trigger 는 확정 행을 덮는다.
- 같은 키 **잠정 쓰기는 확정 행을 못 덮는다**(③-b — `insert_snapshot` `None`, 계약 = `src/db/CLAUDE.md` `strategy_funnel.py` 절; 거래일 20:00 뒤 오늘 라벨 잠정 쓰기 = 장중·저녁 재기동 레거시 분기).
- 다음 거래일 09:30 확정이 저녁 잠정 행을 덮는다(저녁 목록 영구 기록 = ④ 로그뿐). VCP 오전 prepare 별 후보 = `[vcp_breakout_distance_summary]` 로 복원(`strategies/CLAUDE.md` 각주 ⑥).

### ④ 저녁 목록 ↔ 부팅 목록 대조 `[funnel_boot_vs_evening]`

- 배선 = `boot_manager` 익일청산 복구 직후 `spawn_funnel_boot_vs_evening(scheduler, phase="boot")` **await 없이** → `scheduler._ws_task` 생성까지 0.2초 간격 대기(DB 무접촉) → `emit_funnel_boot_vs_evening`. 🔴 동기화 금지(`_boot()` 는 WS 연결 **전** — 보유 중 재기동 틱 공백 증가).
- 대기 중 `scheduler._running` 거짓 = DB 무접촉 조용히 종료(정지·기동 실패 후 ④ 이중 기록 방지, 속성 부재 = 참). 누적 대기 > `_WS_WAIT_TIMEOUT_SECS`(120초) = `[funnel_boot_vs_evening] phase=boot error=ws_not_started strategies=<활성 전부>` WARNING 1행 후 종료.
- task 참조 = 모듈 전역 `_BG_TASKS` + `add_done_callback(_BG_TASKS.discard)`(`llm_buy_gate` 관례 — asyncio 는 버린 Task 를 약한 참조로만). 전체 상한 = `BOOT_VS_EVENING_TIMEOUT_SECS`(10초, `asyncio.wait_for`). S1 `phase` = `boot` 뿐.
- 저녁 목록 = `list_snapshots(target_date=오늘, raise_on_error=True)` 의 `step_no=99 ∧ is_provisional=True` 행 `survived_tickers`. 없음 = `[funnel_boot_vs_evening] phase=boot as_of= evening=absent` INFO. `raise_on_error=True` = 기본값은 DB 예외를 `[]` 로 삼켜 장애가 「캡처 없음」으로 읽히기 때문.
- 부팅 목록 = 활성 전략 `get_scanned_tickers()`(없는 전략 momentum = 건너뜀, 실패 아님 — `error=strategy_failed` 미산입, 회귀 `test_cycle364_funnel_boot_vs_evening.py::test_boot4_23_when_strategy_has_no_scanned_list_then_skipped_without_failure`). 비교 전 양쪽에서 보호 종목(전 전략 보유 ∪ `_pending_next_day_clear`) 제외(저녁엔 필터 통과, 부팅엔 포지션 복구 전 보유 0 — 설명된 차이).
- 원인 힌트 = **부팅당 1회**, DB 3쿼리, 창 `[evening_at, until)` — `evening_at` = 저녁 행 `snapshot_at` 최솟값, `until` = 가장 이른 `phase=boot` meta `started_at`(없으면 지금). 상한 이유 = 준비 **뒤** 도는 부팅 자신의 보유 eager refresh 가 `sm_refreshed_after` 로 새면 월요일·연휴 뒤마다 WARNING 이 억제된다.
  - `params_changed` = `strategy_config.updated_at` 이 창 안인 행 수
  - `bars_changed_after`·`head_now` = `stock_master_daily` 를 `bas_dd >= evening_at::date − 2일`(인덱스 컬럼)로 먼저 묶고 `updated_at` 창 안 행 수 · `max(bas_dd)`(무인덱스 `updated_at` 전 행 스캔 회피)
  - `sm_refreshed_after` = `stock_master.refreshed_at` 이 창 안인 행 수
  - 못 구한 축 = `None`(모름). 첫 쿼리 실패 시 `[funnel_boot_vs_evening] phase=boot hint_error=<축>` WARNING 1행(셋 다 실패해도 1행) — 「꺼진 판정」과 「깨끗한 결과」 구분(④ 실패 `error=` 아님).
  - PG 왕복 = `tests/integration/test_cycle364_boot_vs_evening_hints_pg.py`(창 안·밖 행 → 세 개수 정확 · `head_now` = `max(bas_dd)`).
- 행 = 전략마다 `[funnel_boot_vs_evening] phase=boot strategy= as_of= evening_at= evening_n= boot_n= same= added= removed= sample_added=<≤5> sample_removed=<≤5> held_excluded= params_changed= bars_changed_after= sm_refreshed_after= head_now=`. 기본 INFO, `same=0` ∧ 세 힌트 **전부 0** 일 때만 WARNING(힌트 `None` = WARNING 아님).
- ⚠️ **전일 잠정 봉 확정이 켜진 날 `bars_changed_after` = 평일마다 수백 이상**(`daily_bar_finalize` 가 prepare 앞에서 헤드 봉을 다시 쓴다 = 실제 입력 변화) → 「힌트 전부 0 인데 목록이 다르다」 WARNING 은 평일 거의 없음. 🔴 S2 근거 표본(평시 `same=1`)은 이 leaf 배포 전후를 합산하지 않는다. S2 입력 변화 신호 = `updated_at` 이 아니라 `[daily_bar_finalize]` `close_changed`·`hl_changed`.
- 🔴 **실패는 조용히 사라지지 않는다**(S2 착수 판정 근거) — 전략 한 줄 예외 = 그 전략만 격리 + 끝에 `[funnel_boot_vs_evening] phase=boot error=strategy_failed strategies=<…>` WARNING 1행. `list_snapshots` 실패 = `error=list_snapshots_failed strategies=<활성 전부>`(`evening=absent` 로 보고 금지). 타임아웃·그 밖 = `error=timeout_or_exception strategies=<아직 못 낸 전략>`. WS 단계 120초 초과 = `error=ws_not_started`(위).

### 기타

- `task_attrs` 4 위치(start + connect finally + run_daily finally + stop, G-AST2). `is_provisional` 컬럼 = migration 040.
- 관찰성 한정 — `check_exit`/`check_buy` funnel hook 0건 + risk/order_engine/realtime/auth 참조 0(SAFETY 가드).
- 테스트 = `tests/unit/engine/test_cycle364_{evening_capture,capture_label_guard,funnel_boot_vs_evening,time_invariants,trading_calendar_next}.py` · `tests/unit/engine/strategies/test_cycle364_{prepare_as_of,preview_held_guard,preview_keep_own_skip_all}.py` · `tests/unit/db/test_cycle364_funnel_protect_confirmed.py` · `tests/integration/test_cycle364_{funnel_protect_confirmed,boot_vs_evening_hints}_pg.py` · `tests/unit/routes/test_cycle364_market_ops_evening_preview.py`.

## 접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2

「선행 체결통보 체크 → skip 로그 → `TradeRecord` 조립 → race 흡수 INSERT」 = **코어 하나** `_persist_pending_after_send(*, trade_type, ticker, order_no, strategy_id, record_price, quantity, path, order_price=None)`. 매도 래퍼는 `order_unpr`(주 경로 = 지정가 `order_unpr` · 폴백 = `fallback_price`)를 받아 `_sell_order_price(ticker, order_unpr)`(지정가 = 그 값 · 시장가 = 주문 순간 `scanner.ticker_prices` 현재가 · 없으면 None, never-raise, await 0)로 `order_price` 를 만든다 — `record_price`(매도 = 매수가 장부)와 별개 칸(cycle409 — 사용자 결정 10-04 Q4 8영역 승인). 4 경로(매수 주·폴백 · 매도 주·폴백)는 전부 **축별 경계 래퍼** `_persist_buy_pending_after_send` · `_persist_sell_pending_after_send` 경유 — 코어 직접 호출은 **두 래퍼뿐**, `execute_buy`/`execute_sell` 안 **0건**(가드 `test_g328_0c`).

🔴 **경계(cycle327 ⓑ)는 코어에 없다 — 호출자 층 책임.** 코어는 예외를 **그대로 전파**, 래퍼가 자기 `except Exception` 으로 받는다(코어에 `try` 를 들이면 래퍼 `except` 가 도달 불가 → 좁히기·지우기 회귀 무증상, 가드 `test_g328_0d`).

- 🔴 **래퍼의 `except Exception` 을 좁히지 않는다 — 구조 가드가 유일한 방어**(좁히면 행위 회귀가 초록인 채 새고, 타입 표본을 늘려도 같은 누락에 노출된다). 가드 = `test_g328_3`/`test_g328_3b`(두 축 parametrize).
- **접수된 자금은 묶어 둔다** — 접수 후 실패에서 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다**(KIS 가 주문가능금액에서 이미 뺀 「묶인 자금」). 풀면 같은 종목 재매수 + 전략 예산 이중 사용 + 그 틱 청산 평가 소멸 + 900초 매수 락이 열린다(계좌 방어 `get_buyable` 은 전략 예산보다 커서 못 막는다). 유지 비용 = **체결 0건 종료 주문 한정** 슬롯·금액 유휴 — KIS 행이 끝남(`tot_ccld_qty==0 ∧ rmn_qty==0`)을 보이면 다음 잔고 sync 의 `buying_reconcile` 이 푼다(20:00 뒤 종료분은 21:30 `_reset_daily_state` 까지). 첫 **부분**체결이면 `_handle_buy_fill` 이 해제(그 블록은 전량 분기 **앞**).
- **마커 2종** — `[buy_post_send_error] ticker= order_no= strategy= path= qty= price=` · `[sell_post_send_error] ticker= order_no= strategy= path=` — **ERROR · 무cap**(21:30 `top_patterns` 편입). 🔴 매수만 `qty=`·`price=`(포지션도 장부도 없어 규모를 아는 유일 채널). 🔴 cap 금지(**「예산을 점유한 채 장부가 없는 주문」의 유일한 목록** — 건별 KIS 주문내역 대조). **판독** = 하루 5건 이상이면 시정 결함이 아니라 **RDS 장애**(revert 는 로그만 지운다).
- 🔴 **축 파생 방향 = 계약** — `_PENDING_SIDE_BY_TRADE_TYPE` 가 **행위값 `trade_type` → 관측값 `side`** 를 파생(반대면 `side` 오타 하나가 매수/매도를 뒤집는다).
- **수식어 표** `_PENDING_SKIP_PREFIX[(side, path)]` = `.get(key, "")` **총함수**(관측이 행위를 바꾸지 않게). ⚠️ `("buy","fallback")` 만 `"매수 폴백 "` 이 아닌 것 = 현행 문구 보존.
- ⚠️ **`top_patterns` 키 = 메시지 전문** — 매수 폴백 skip WARNING(` (주문번호: %s)` 추가)은 **2026-09-21**, `[sell_post_send_error]` 폴백 꼬리 문구는 **2026-09-20** 전후 패턴 문자열을 비교하지 않는다(마커 + 4필드는 byte 동일).
- 자문 = `_workspace/domain_consult/cycle335_buy_post_send_boundary.md` · 설계 = `_workspace/refactor/2026-09-21_step2_card.md` · 가드 = `tests/unit/ast/test_cycle328_sell_pending_helper.py` · 회귀 = `tests/unit/engine/test_cycle335_buy_post_send_boundary.py` · `test_cycle327_sell_fill_during_insert.py` · `test_cycle271_execute_buy_fill_during_insert.py`

## 취소 타이머 키 — `(ticker, 축)` (cycle332)

`_pending_cancel_tasks` / `_pending_cancel_order_no` 키 = **`(ticker, side)`**(`side ∈ {"buy","sell"}`, 리터럴은 모듈 상수 `CANCEL_AXIS_BUY`/`CANCEL_AXIS_SELL` 한 곳). 매수 잔량 취소(`_schedule_cancel`)·매도 손절 잔여 재주문(`_schedule_cancel_and_reorder`)이 **자기 축만** 교체 → 두 타이머 공존(ticker 단독 키면 나중 것이 앞선 것을 `order_no` 검사 없이 죽인다).

- **S1(매수 타이머가 손절 타이머를 죽임)이 심각** — `_cancel_and_reorder` = 취소 3경로 중 **유일한 `cancel_order → place_order` atomic replace**. 죽으면 원 매도가 호가에 남고 비시장가(프리장 `step_down` 변환·KRX 애프터 `41` 지정가·NXT 잔존)면 안 팔리며, 매도 **부분**체결 분기는 `_selling` 을 유지해 `risk.on_tick` 이 `check_exit_signal` 을 건너뛰고, `selling_reconcile`(180초)도 원 주문이 열려 `open_order` 유지 → **급락장에 손절 잔여가 21:30 까지 방치**.
- **S2(매도 타이머가 매수 타이머를 죽임)** — 미취소 매수 잔여가 (a) 손절 중 종목을 계속 사들이고 (b) `pending_buys`/`pending_buy_amounts` 는 첫 부분체결에 이미 풀려 그 잔여 체결이 **설계 랏 초과**(K축·ρ축 캡은 진입 시점 통제라 못 막는다).
- 🔴 **해제의 `order_no` 일치 게이트 불변**(cycle273a) — 축 분리는 **등록**뿐. 같은 축 재스케줄 = 교체(부분체결 연속은 정상, 안 그러면 타이머 누적).
- **UI 계약** — `GET /api/trading/status` `pending_cancels` = **ticker 배열**(`frontend/src/types/trading.ts` · `OrderMonitor.tsx`), `order_engine.pending_cancel_tickers(engine)` 파생(두 축이어도 **한 번만**). 🔴 `order_no` 단독 키 금지(UI 의미 변경 + cycle273a·cycle291 가드 다수 재작성).
- `scheduler._reset_daily_state` 일괄 clear = `.values()`/`.clear()` 라 키 모양 무관.
- 자문 = `_workspace/domain_consult/cycle332_buy_cancel_timer.md` · 회귀 = `tests/unit/engine/test_cycle332_cancel_timer_key.py`

## 발사 창 귀속 — `pending_buys` 단 (cycle331)

`await place_order` 동안 주문번호 매핑 5종은 **비어 있고** `pending_buys` 는 **이미 차 있다**(`execute_buy` 가 `place_order` **앞**에서 넣는다). 그 창에 착지한 **우리** 매수 체결통보 = `_order_strategy` miss → `trade_history` miss(PENDING INSERT 도 `place_order` 뒤) → `is_ticker_held_by_any` **참**(`_strategies.values()` 전수 `has_position OR is_buy_pending` — 매수 당사자 자신이 조건을 세운다) → P1-B(B-2) 조기 return.

🔴 **그러면 Position 미등록 → 그날 손절·트레일링·15:20 일괄청산 불성립**(`risk.on_tick` 은 `state.positions` 를 본다). 익일청산만 다음 날 `_boot` 잔고 복구가 되살리고, `trade_history` 는 `mark_pending_buys_completed` 가 뒤늦게 맞춰 **대시보드·DB 는 정상으로 보인다**.

- **귀속 단** = 폴백 체인의 `trade_history` **뒤**·B-2 가드 **앞**에 `_resolve_pending_buy_owner(ticker)`. 채택 = `ticker in state.pending_buys` 전략이 **정확히 1개** ∧ 그 전략 **미보유**. 0개·2개 이상·예외 = `None`(fail-open, **결과 집합 ⊆ 현행**). in-memory, `await` 0, never-raise(체결통보 콜백 예외 = `realtime/handler.py` 규약상 **WS 재연결**).
- 🔴 **B-2 가드 제거 금지** — **출처 모를 매수가 `momentum` 을 우겨 남의 포지션을 덮는 것**(377450 사고)을 막고 수동 매매·외부 주문에 여전히 유효. 수동/외부 매수는 `pending_buys` 에 없어 이 단을 타지 않는다.
- 🔴 **잔량 취소 타이머 = `qty_src == "map"` ∧ 귀속이 `pending` 단이 **아닐** 때만** — 귀속이 틀린 랏이면 `_cancel_after_wait` 가 30초 뒤 **사람이 낸 주문의 잔량을 취소**(cycle327·cycle329 계열). 우리 주문이면 곧 매핑이 서고 잔여 통보가 `src=map` 으로 와서 건다(손실 0). 보류 = `[buy_partial_no_cancel_timer]` WARNING.
- **관측** = `[buy_fill_strategy_from_pending] order_no= ticker= strategy= qty_src= incr= filled_total= ordered=` **무cap WARNING** = 귀속 단 성공 서명(건별 조사 단위). 형제 `[buy_fill_fallback_held_conflict]` = 무cap ERROR, 진짜 미지 출처만 남아 **0 수렴**이 정상.
- ⚠️ **1주 랏에 집중** — 단일 통보 전량 체결이면 두 번째 통보가 없어 자기 치유 경로가 없다(다주 랏은 잔여 통보 `src=map` 이 포지션을 만든다).
- ⚠️ B-2 ERROR 문구 `"타 전략 보유/주문중"` = 판정이 `has_position OR is_buy_pending` 이라 **주문 중**일 수 있다. `top_patterns` 키 = 메시지 전문 → **2026-09-21 전후 패턴 문자열 비교 금지**.
- **별건 권고** = `scheduler._sync_positions_from_balance` 의 `is_ticker_held_by_any` 를 **보유 축만** 보는 헬퍼로 → 블라인드 창 17~24시간 → ≤15분(소비처 5곳 광역 회귀, 귀속 단 이후 실익 작음).
- 자문 = `_workspace/domain_consult/cycle331_buy_fill_dropped.md` · 회귀 = `tests/unit/engine/test_cycle331_buy_fill_from_pending.py`

## 체결통보 주문수량 — 출처 3단 (cycle329)

`handle_execution_notice` 의 **주문수량** 출처(이 순서):

| `qty_src` | 출처 | 뜻 |
|---|---|---|
| `map` | `_order_qty[order_no]` | 우리 주문, 매핑 섰음(정상, 하루 수천 건) |
| `payload` | 체결통보 `fields[16] ODER_QTY` | **매핑 부재 창**의 유일한 주문수량 경로 |
| `increment` | 이번 통보 증분 체결량 | 둘 다 없을 때 폴백 |

🔴 **막는 결함** — `order_no` 는 KIS 응답 뒤라 `await place_order` 동안 매핑 5종이 비어 있다. 그 창 통보는 `ordered_qty` 가 증분으로 폴백 → `total_filled >= ordered_qty` **항상 참** = **부분 체결이 전량으로 읽힌다**. 매수 = `_completed_buy_orders` 무장으로 잔여 통보가 `[buy_fill_duplicate_ignored]` 로 버려지고 `_sync_positions_from_balance` 는 `is_ticker_held_by_any → continue` 라 기보유 수량을 고치지 않는다(익일 `_boot` 까지). 매도 = **주문 축만** 틀리고 보유 축이 잔량을 손절 감시 안에 남긴다(「매도 체결 — 주문 축과 보유 축」).

- 🔴 **전량 판정에 출처 게이트 금지** — `qty_src != "increment"` 를 붙이면 payload 부재 퇴화에서 **수동 전량 매도가 유보** → 유령 포지션 + `_selling` 좀비(= 손절 마비)(`selling_reconcile` `held_zero` = **유지** 분기). payload 가 있으면 수동 주문도 정확하다.
- 🔴 **재주문 타이머 = `qty_src == "map"` 일 때만** — 매핑 부재 창 통보도 부분 분기에 닿고 `_cancel_and_reorder` 는 취소를 **조건 없이** 낸다(J-2 재조회는 재발사 수량만 조정). `payload` 엔 수동 주문도 있어 게이트가 없으면 **사람이 낸 주문을 30초 뒤 취소·재발사**(cycle327 「주문이 나간 뒤의 재발사」 계열). 우리 잔여는 다음 통보 `src=map` 이 건다(손실 0). 보류 = `[fill_partial_no_reorder]` WARNING.
- **overrun 클램프 게이트 = `qty_src != "increment"`**(payload = KIS 주문수량 = 매핑과 동급, 배제하면 이 창에서 클램프만 꺼진다).
- 🔴 **`fields[16]` = cycle235 오독(257720 사고) 자리** — 체결수량 소스 `fields[9]` 무접촉(`test_cycle235_ast_execution_qty.py` 봉인). 매핑이 선 **정상 통보마다** `[ordered_qty_mismatch]` 로 payload 교차검증(불일치여도 판정은 `map` 값).
- **관측** = `[fill_qty_src] order_no= ticker= side= src= ordered= filled_total= incr=` — `src=map` **DEBUG**, 나머지 **WARNING**(`KstDailyEmitCap[(src,ticker,side)]` 1회/일 — 비정상만 리포트). `_settle()` 직전 `[fill_qty_src_summary] window=day map= payload= increment=` 1행(🔴 호출부 try/except 금지 — scanner 일일 summary 2종과 동일). **판독** = `payload > 0` = 창이 열렸고 막았다(성공 서명) / 수동 매매 없는 날 `increment > 0` = **조사 신호**.
- ⚠️ **남는 사각** — payload 부재면 매핑 부재 창 주문수량을 모른다(매수 결함 잔존, 매도는 주문 축만 틀리고 보유 축 정확). 빈도 = `increment` 카운터.
- 자문 = `_workspace/domain_consult/cycle329_mapping_absent_full_fill.md` · 회귀 = `tests/unit/engine/test_cycle329_mapping_absent_full_fill.py`

## 매도 체결 — 주문 축과 보유 축 (cycle385)

사람은 보유 일부만 팔 수 있다(`POST /api/trading/manual-sell` `quantity` < 보유 · MTS/HTS · 손절 잔여 재주문). 전략 매도는 항상 전량이라 「주문 종료」 = 「보유 0」 이지만 일부 매도에서 갈라지므로 `_handle_sell_fill` 은 두 판정을 나눈다(사용자 결정 2026-09-26·27 — 잔여 보유 추가 매도를 추적한다는 전제로 분할 매도 허용).

세 불변식(명세 부록 R):

- **추적 밖 실보유 0** — 과소 추적(추적 < 실보유) 금지. 과대 추적은 허용(다음 매도의 APBK0400 → #1.5 재대조가 회수).
- **우리 주문 합 ≤ 추적 수량** — 운영자가 따로 산 몫은 우리 주문이 팔지 않는다.
- **잔여는 팔 수 있어야 한다** — 다른 주문이 일부를 잠가도 안 잠긴 추적 잔여는 손절이 판다(동결은 팔 수 있는 추적 잔여 0 일 때만).

⚠️ 깨지는 경로 잔존 — 이 절 끝 「알려진 한계」.

| 축 | 판정 | 정하는 것 |
|---|---|---|
| **주문 축** | `total_filled >= ordered_qty` (그 주문이 끝났나) | 장부(`update_trade_status` COMPLETED/PARTIAL · 보정 INSERT) · 매핑 pop · 취소 타이머 해제·등록 · `_selling`·`_selling_locked_wait` 해제(조건 없음) |
| **보유 축** | `pos.quantity = max(0, 보유 − hold_dec)` 뒤 `pos.quantity == 0` | `del positions` · `delete_position` · `on_position_closed` · `sold_today.add` · 종목 크레딧 삭제 · 동결 해제(동결 중일 때) · 구독 해제(`_unsubscribe_if_no_other_strategy` — 주문 종료 분기 안에서만) |

`hold_dec` = 이번 체결량 − 재대조 크레딧 흡수분(아래 #1.5, 크레딧 없으면 체결량).

- **보유가 남으면** 차감 수량 `save_position` upsert — 인자 8개 전부(빠지면 다른 값이 덮인다). 종목명 = `scanner.ticker_names` 캐시(비면 빈 이름 — `save_position` 은 빈 이름으로 기존 이름을 덮지 않는다, `src/db/CLAUDE.md`). 삭제·훅·`sold_today`·구독 해제 없음. 저장 실패 = `[sell_fill_db_error] step=save_position` ERROR 만, 전파 금지(콜백 예외 = WS 재연결) — 메모리는 이미 차감, DB 옛 수량은 재시작 뒤 매도 시점 #1.5 재대조가 고친다(재시작 전 접수 주문 체결은 `pending` 미산입 — 아래 「원장 시작 전 주문」). `delete_position` 은 감싸지 않는다.
- 🔴 **보유 축에도 출처 게이트 금지**(「체결통보 주문수량」 금기와 같다) — `map`/`payload`/`increment` 무관 체결량만큼 빼고 0 에서만 닫는다(AST A10).
- 🔴 **주문이 끝나면 `_selling` 을 푼다 — 어느 주문의 종료든, 보유가 남아도.** `risk.on_tick` 은 `_selling` 종목의 `check_exit_signal` 을 건너뛰므로 남기면 잔여 손절이 멈춘다. 주문 축 If 본문 첫 두 문장 = `self._selling.discard(ticker)` · `self._selling_locked_wait.discard(ticker)`(그 If 의 첫 `await` 앞).
  - 🔴 해제에 조건 금지 — `qty_src` · 보유자 · `pos` 는 통보 앞쪽 `await`(`_lookup_strategy_from_trade_history` · `delete_position` · `save_position`) 전 값이라, 그걸로 가르면 REST 응답이 통보 도중 착지할 때 표식이 남는다(AST AR2-1 — 해제를 감싸는 If 없음, `qty_src` 미분기).
  - 🔴 「표식을 세운 주문의 종료로만 해제」로 좁히지 않는다 — 원주문 취소를 낸 재주문 태스크가 다음 부분 체결에 교체 취소되면 재주문 발사 여부를 몰라 표식이 `selling_reconcile` 까지 좀비(명세 부록 R2-1). 대가 = 「알려진 한계」 첫 항목.
  - `_selling_locked_wait` = 「`_selling` 은 우리 `execute_sell` 이 **주문 없이** 멈춰 세운 것」. 넣는 곳 = 부분 잠김 판매 보류(`fire ≤ 0` · 주문 조회 실패 — `[sell_qty_partial_locked]` · `[sell_qty_hold_orders_unavailable]` · `[sell_qty_unnoticed_fills]`)·`[sell_qty_locked]` 의 return 직전. 빼는 곳 = `execute_sell` 진입 · 수동 매도 라우트 `_selling` 세움 · 주문 축 종료 · J-2 `gone` · 재주문 미접수 해제 · 닫기 묶음 해제 · `reset_daily_state()`.
  - **동결이 지키던 보유가 닫히면 동결 해제** — 닫기 묶음(`if close_position:`)에서 `ticker in _selling_locked_wait` 이면 `_selling` · `_selling_since` · 표식 비움(`[selling_freeze_released]`)(외부 주문이 추적을 0 으로 만들고 「종료」가 끝내 안 오면 `_selling` 이 하루 내내 남는다 — `selling_reconcile` 은 `held_zero` 유지). 조건이 표식이라, 우리 주문이 걸린 채 외부 체결이 추적을 0 으로 만든 경우는 유지(AST AR2-7).
  - 주문 부분 체결 = `_selling` 유지(주문이 열려 있다).
  - `POST /api/trading/manual-sell` 이 `_selling` 을 발사 **앞**에서 세움 = 잔여 손절 보호(`src/routes/CLAUDE.md`).
  - `_handle_sell_fill` 「매도 체결: 전략 찾을 수 없음」 오류 경로도 `_selling` 해제(운영에선 momentum 상시 등록이라 미도달).
- 🔴 **`if total_filled >= ordered_qty:` = 함수 본문 최상위 글자 그대로 1개**(AST A1 — `test_cycle273a_ast_partial_optin_and_timer.py` g273_ast3/ast4 가 그 If 안에서 타이머 해제·`order_no` 게이트를 찾는다). `del positions[...]` 는 `_handle_sell_fill` 안(G2-STRUCT-INVARIANT site 집합).
- **소유 전략** — 장부 전략 `sid` = `_order_strategy` → `_lookup_strategy_from_trade_history` → **registry 전수 보유자 정확히 1개**(`[sell_fill_owner_from_holding] from=none`) → `"momentum"`. 보유 축 전략 = `sid` 가 보유하면 `sid`, 아니면 보유자 정확히 1개(`[sell_fill_owner_from_holding] from=<sid>`). `sid` 미보유 ∧ 보유자 2개 이상·판정 예외 = **보유 축 수량 무변경**(`[sell_fill_owner_ambiguous]` ERROR). 보유자 0 = 주문 종료 시 닫기 묶음(`on_position_closed`·`sold_today`·`delete_position`) 멱등 정리.
  - 🔴 `_ticker_holders(ticker)` = `registry.all()`(꺼진 전략 포함 — `enabled()` 로 좁히면 꺼진 전략 실보유를 놓친다, `registry.get(strategy_id)` 로 좁히면 `"momentum"` 기본값 함정). 동기 · `await` 0 · never-raise(예외 = `None`)(AST A5).
  - 소유 해석 ~ 보유 차감 `await` 0(AST A9) — `execute_sell` 루프 상단·J-2 재조회와 원자적으로 맞물린다.
- **손익** = 이번 체결분 `(체결가 − 매수가) × 체결량` → 보유 축 전략 `daily_realized_pnl`(크레딧 흡수분도 판 주식이라 체결량 전체, AST AR3). `trade_history` SELL 행 수량 = 그 주문 수량. 분할 매도 짝짓기 = `get_trade_pairs` 누적 보유 모델.
- **보유보다 큰 체결**(= 추적이 이미 과소 — 수동 추가매수 등) → 0 으로 닫고(음수 금지) `[sell_fill_exceeds_holding]` WARNING, 남은 실보유는 15분 sync 가 「미보유」로 재채택. 주문 축 overrun 클램프(누적 > 주문수량)와 다른 축.
- 🔴 **`execute_sell` 발사 수량 = `send_qty` 고정** — 루프 상단 재조회 직후 `send_qty = pos.quantity`, `sell_cap` 이 있으면 `min(send_qty, sell_cap)`(줄이기만). 발사·`_order_qty`·`_persist_sell_pending_after_send(quantity=)`·로그에 그 값만(주 경로·폴백). 루프 안 `send_qty` 대입 정확히 2개(AST A3 · AR5). 발사 뒤 재독하면 `await place_order` 중 통보가 깎은 값이 매핑에 적혀 잔여가 overrun 클램프에 잘리고 유령 보유가 남는다.
- 🔴 **#1.5 재대조와 늦은 통보는 같은 체결을 두 번 빼지 않는다** — 재대조(`[sell_qty_reconciled]`)는 `pos.quantity` 를 잔고 스냅샷 `held` 로 덮으므로, 스냅샷에 반영된 체결의 통보가 뒤에 오면 이중 차감(과소 추적). 그래서 재대조가 주문별 「이미 반영된 체결」을 크레딧으로 적고 통보는 크레딧을 먼저 쓴다(순서 = 계약).

  | # | 단계 |
  |---|---|
  | 1 | `get_balance()` — 시각 t1, `held`·`sellable`. `0 < sellable < 추적` 이면 계속 |
  | 2 | `_sell_orders_snapshot(ticker)` — `get_daily_orders(exchange="ALL", pdno=ticker)`(TTTC0081R) 1건, 반드시 1 **뒤**(t2 ≥ t1 이어야 크레딧 부족 없음). 반환 `(fills, reason, pre)` — `reason` ∈ `ok`·`error`·`timeout`·`bad_row`·`page_full`, `pre` = 원장 시작 전 접수 주문번호 집합(실패 넷 = 빈 집합)(AST AR2-5 · AR2-6 · AR3-2) |
  | 3 | `strategy.state.positions.get(ticker) is pos` 아니면 `[sell_qty_reconcile_skipped] reason=position_replaced` 후 `continue`(닫힌 포지션을 `save_position` 으로 되살리지 않는다) |
  | 4 | `pending = _sell_pending_dec(fills, pre)` · `eff = pos.quantity − pending`(조회 실패 = `eff = pos.quantity`). `held ≥ eff` → 아래 「부분 잠김 판매」, `held < eff` → 5 |
  | 5 | 크레딧 — 조회 성공: 원장 시작 뒤 주문 `o` 마다 `c = 누적 체결 − _sell_notice_seen[o]`, `c > 0` = `_sell_reflected_credit[o] = c`, 아니면 pop. 원장 시작 전 주문은 같은 `c` 를 상한 `_pre_cap` 까지(아래). 종목 크레딧 삭제. 조회 실패: 종목 크레딧에 `max(0, pos.quantity − target_qty)` **가산** |
  | 6 | `pos.quantity = target_qty` · `sell_cap = None` → `save_position` → `continue` |

  - 3 ~ 대입(6 의 `pos.quantity` 또는 부분 잠김 `sell_cap`) `await` 0. 2 의 await 뒤 수량 술어를 다시 안 보는 이유 = 6 은 「t1 계좌 보유 = `held`, 반영·미처리 통보 = 크레딧」 절대 진술(명세 R-1-6) — 재검증은 객체 동일성만. `eff` = await 뒤 상태, t1 뒤 체결은 `pending` 에만(덜 쏘는 쪽, 명세 R2-8).
  - `held < eff` = 원장 시작 뒤 주문으로 설명 안 되는 차이(유령 보유 · 유실 통보 · 재시작 전 체결). 설명되는 차이는 재대조하지 않는다(곧 뺄 몫을 `held` 로 덮으면 운영자 초과분까지 추적에 들어온다).
  - 🔴 주문 조회 = `asyncio.wait_for(…, timeout=SELL_ORDERS_QUERY_TIMEOUT)`, `SELL_ORDERS_QUERY_TIMEOUT = 2.0`(초) 모듈 상수(`DEFAULT_PARAMS`·`system_config` 키 아님 — 손절 경로가 APBK0400 뒤 잔고 1건을 이미 기다렸다). 초과 = `reason=timeout`(조회 실패와 동일, 취소되는 것은 읽기 조회뿐).
  - 🔴 `exchange="ALL"`·`pdno=ticker` 키워드 고정(KRX 만 보면 NXT/SOR 체결 누락 → 크레딧 부족, AST AR2-6).
  - 파서 `_sell_fills_by_order(rows, ticker, page_size)`(모듈 함수 · 순수 · never-raise) — 그 종목(`pdno`) 매도(`sll_buy_dvsn_cd == "01"`) 행만, 같은 `odno`(SOR) = `tot_ccld_qty` 합. 통과 행 하나라도 `odno` 빈 값·수량 비정수, 또는 행 수 ≥ `page_size`(잘림 가능) = **전체 `None`**(한 주문 누락 = 그 늦은 통보 이중 차감).
  - 🔴 `page_size` = 환경별 — `settings.is_production` 이면 `_DAILY_ORDERS_PAGE_REAL`(100), 아니면 `_DAILY_ORDERS_PAGE_VTS`(15)(정본 `docs/kis/domestic-stock-order.md`). 인자 기본값 금지(한쪽 환경 잘림 오판).
  - 🔴 **종목 크레딧 = 가산(덮어쓰기 금지)** — 두 번째 재대조는 첫 재대조 이후 새 반영분만 센다(덮으면 첫 몫 통보가 다시 빠져 과소 추적, AST AR2-4). 조회 성공 재대조는 종목 크레딧을 버린다(주문별 크레딧이 대신).
  - 조회를 못 믿어도 재대조는 한다(`[sell_qty_reconcile_orders_unavailable]`) — 건너뛰면 오염 포지션 손절이 멈추고, 크레딧 없이 하면 과소 추적.
  - `_handle_sell_fill` = 통보마다 `_sell_notice_seen[주문]` += 체결량 → 자기 주문 크레딧 → 종목 크레딧 순 흡수 → 남은 `hold_dec` 만 차감(`[sell_fill_credit_absorbed]`). 주문 크레딧은 자기 주문 통보만(우리 재발사 체결이 MTS 주문 크레딧을 먹으면 유령 보유). 원장·흡수 = 출처·`pos` 유무·모호 여부 무관, 소유 해석 뒤 첫 `await` 앞(AST AR2).
  - 주문번호 = `_odno_key(s)`(앞 0 제거 — REST `ODNO`·체결통보·TTTC0081R `odno` 패딩 흡수). 포지션 닫힘 = 그 종목 크레딧 삭제. 다섯 구조(`_sell_notice_seen` · `_sell_reflected_credit` · `_sell_blind_credit` · `_manual_sell_orders` · `_selling_locked_wait`)는 `reset_daily_state()` 가 비우고 같은 자리에서 원장 시작 시각을 그 순간으로(AST AR11 · AR3-1). 주문번호는 하루 단위 유일, 원장은 메모리라 재시작 = 빈다(아래).
  - 🔴 **원장 시작 전 접수 주문은 `pending` 에서 뺀다(원장 시작 전 주문).** `_sell_ledger_since` = 「`_sell_notice_seen` 은 이 시각 **뒤** 처리한 매도 통보를 빠짐없이 담는다」 — `__init__`·`reset_daily_state()` 가 `datetime.now(_KST_TZ)` 기록. 빼지 않으면 재시작 전 체결이 전부 `pending` → 손절이 매 틱 보류. 빼면 「보유 대 추적」 비교 → 재대조가 고친다.
    - 분류 = `_sell_orders_placed_before(rows, ticker, since)`(모듈 함수 · 동기 · never-raise, 예외 = 빈 집합) — 그 종목 매도 행 `ord_dt`(8자리) + `ord_tmd`(6자리)를 `_ord_datetime` 이 KST 로, 여러 행(SOR) = 가장 늦은 시각, `since` 보다 **앞**(`<`)만 포함. 🔴 한 행이라도 못 읽으면 「뒤」(`pending` 산입 = 덜 쏜다).
    - 🔴 **벽시계 게이트 아님** — 기록된 두 시각(원장 시작 · 접수 시각) 비교뿐(테스트는 `_sell_ledger_since` 를 상수 대입).
    - 원장을 「재시작 전 체결 = 다 봤다」로 채우지 않는다 — 부팅은 복원 수량을 KIS 에 안 맞춘다(`boot_manager.py` = DB 행 수량 사용, KIS 에 없는 종목 행만 삭제 → `save_position` 실패·다운타임 체결만큼 KIS 와 다를 수 있다).
    - 🔴 **원장 시작 전 주문도 크레딧은 적되 상한** — 크레딧에서까지 빼면 재시작 뒤 체결된 미통보 몫 이중 차감(과소), 상한이 없으면 원장이 모르는 재시작 전 체결까지 크레딧이 되어 새 통보를 삼킨다(과대). `_pre_cap = max(0, pos.quantity − target_qty − 뒤 주문 크레딧 + _old_credit)`(이번 재대조 하강폭 + 남은 크레딧). `_old_credit`(그 주문들의 기존 주문 크레딧 + 종목 크레딧) = 첫 덮어쓰기 **앞**에서 계산. 순서 = 뒤 주문 루프 → `_pre_cap` → 앞 주문 루프(`min(누적 체결 − _sell_notice_seen, _pre_cap)`)(AST AR3-5).
- 🔴 **외부 매도가 일부를 잠가도 안 잠긴 추적 잔여는 판다(부분 잠김 판매).** 4 에서 `held ≥ eff` → `surplus = held − eff` · `fire = sellable − surplus`. `held − sellable` = 이 종목에 걸린 매도 전부(우리·수동·MTS, 매핑 무관) → 새 주문 + 걸린 주문 ≤ 추적, 이미 잠근 주식을 두 번 팔지 않는다. 주문 조회 = 재대조와 **같은 1건**.
  - 🔴 **아직 안 온 외부 체결 통보를 먼저 뺀다** — `_sell_pending_dec(fills, pre)`(동기 · `await` 0) = 원장 시작 뒤 주문마다 `max(0, 누적 체결 − _sell_notice_seen − _sell_reflected_credit)` 합(`pre` 제외). 안 빼면 surplus 과소 → 운영자 몫 매도. 🔴 `max(0, …)` = **주문마다**(합 뒤 한 번이면 목록이 통보보다 늦은 주문의 음수가 다른 주문 대기분을 지운다, AST AR3-3).
  - 🔴 종목 크레딧(`_sell_blind_credit`)은 `pending` 미차감(유실 통보가 섞일 수 있어 빼면 `eff` 과대 → 운영자 몫 매도, AST AR2-8).
  - 🔴 **주문 조회를 못 믿으면 쏘지 않는다**(`fire = 0` → 동결 — 걸린 체결 통보와 운영자 초과분을 못 가른다).
  - `fire ≥ 1` → `sell_cap = fire` 재시도(`[sell_qty_partial_sellable]`), `pos.quantity` 불변(C236-F1 — 잠긴 주식도 추적 보유, 취소되면 다시 손절 대상).
  - `fire ≤ 0`(운영자 초과분이 걸린 주문을 덮음 · 조회 실패) → 보존 · `_selling` 유지 · `_selling_locked_wait` 추가 후 return(걸린 주문 = 「운영자가 전략 몫부터 판다」 보수 해석). 로그 = 걸린 매도 유무 × 조회 성공 여부(AST AR3-6 · AR4-2):
    - `held > sellable`(걸린 것 있음) → `[sell_qty_partial_locked]`.
    - `held == sellable` ∧ 조회 실패(`fills is None`) → `[sell_qty_hold_orders_unavailable]`(진입 땐 `0 < sellable < 추적` 이었는데 조회 `await` 중 통보가 추적을 보유 이하로 줄인 경우 — 미통보 체결 유무를 몰라 「거래소가 확인한 미통보 체결」 문구 미사용).
    - `held == sellable` ∧ 조회 성공 → `[sell_qty_unnoticed_fills]`(원장 시작 뒤 주문의 미통보 체결이 추적 전부를 덮음 — 전략 몫은 이미 팔렸고 계좌 잔량 = 운영자 몫).
    - 🔴 **걸린 매도가 없어도 보류**(명세 부록 R4 D1 — 「걸린 것 없으면 동결 안 함」을 글자대로 따르면 재대조로 가서 운영자 몫을 판다).
    - 걸린 것 없는 보류를 푸는 주체 셋 = 그 주문의 종료 통보 · 보유 닫힘(닫기 묶음 동결 해제) · 통보 유실 시 `selling_reconcile`(이 보류는 늘 `held == sellable > 0`). 「잠김」 문구는 이 두 경우에 뜨지 않는다.
  - `sellable == 0 ∧ held > 0` → `[sell_qty_locked]` 동결(보존 · `_selling` 유지 · `_selling_locked_wait`).
- **J-2 — 손절 잔여 재주문 직전 보유 재조회.** `_cancel_and_reorder` 는 30초 전 `remaining` 을 그대로 쏘지 않는다 — 마지막 `await`(CANCELLED 장부) 뒤·`place_order` 앞 `_reorder_requery(ticker, order_no, remaining)`(동기 · never-raise)가 registry 전수 보유 재조회(AST A4).

  | 주문 · 보유자 | `verdict` | 발사 수량 |
  |---|---|---|
  | 수동 매도 라우트 주문(`order_no in _manual_sell_orders`) | `manual` (보유자 1 ∧ 보유 ≥ `remaining` 이면 INFO, 그 밖 WARNING) | `remaining` — 보유와 무관 |
  | 1, 보유 ≥ `remaining` | `same` (INFO) | `remaining` |
  | 1, 0 < 보유 < `remaining` | `shrunk` | 보유 |
  | 0 (또는 보유 ≤ 0) | `gone` | 발사하지 않는다 + `_selling`·`_selling_since`·`_selling_locked_wait` 해제 |
  | 2 이상 | `ambiguous` | `remaining` |
  | 판정 예외(바깥 `except` 포함) | `error` | `remaining` |

  - 🔴 **보유 맞춤 = 상한, 증액 아님**(`min(remaining, 보유)` — 올리면 운영자가 남기려던 수량까지 판다).
  - 🔴 **의심스러우면 쏜다**(손절 잔여 포기가 더 비싸다 — 과대 요청은 KIS APBK0400 → #1.5 흡수).
  - 🔴 **수동 매도 라우트 주문 = 운영자 의도 우선** — 대상이 추적 밖 주식일 수 있어 `shrunk`·`gone` 미적용. 표식 = 라우트가 매핑과 같은 동기 구간에서 `_manual_sell_orders[order_no] = _added`. 🔴 `strategy_id`·`_order_strategy` 로 추론 금지(라우트는 보유 전략 id 를 적는다, AST AR9). 재주문 번호가 표식 승계(`_cancel_and_reorder` 결과 블록) → 재주문의 J-2 도 같은 규칙. 과대 요청 = APBK0400 → `_cancel_and_reorder` `except` 흡수.
  - 취소(`cancel_order`)는 재조회 무관하게 나간다 → 재주문 타이머 `qty_src == "map"` 게이트 계속 필요(「체결통보 주문수량」).
- 🔴 **원주문을 취소했는데 우리 재주문이 확정적으로 안 걸렸으면 `_selling` 을 푼다**(남기면 잔여 손절이 `selling_reconcile` 까지 멈춘다). `_cancel_and_reorder` 가 `try` 앞에서 `_cancel_ok`(원주문 취소 성공) · `_place_state`(`none` · `sending` · `accepted` · `rejected`) 초기화, `finally` 1회 판정(`await` 0, AST AR2-3).

  | 출구 | `_cancel_ok` | `_place_state` | `_selling` |
  |---|---|---|---|
  | 쌍 게이트 컷 · 원주문 취소 실패 · 취소 전 교체 취소 | 거짓 | `none` | 유지 — 원주문이 아직 걸렸거나 이미 끝났다(끝났으면 그 통보가 푼다) |
  | 취소 성공 → CANCELLED 장부·재조회 중 예외 · 태스크 교체 취소 | 참 | `none` | 해제 |
  | 취소 성공 → J-2 `gone` | 참 | `none` | 해제(J-2 표의 해제가 먼저 돈다) |
  | 취소 성공 → 재주문 거부, `_sell_not_placed_reason` 이 이유를 준다(APBK0400 수량 초과 · 장운영시간 외 · 시장가 불가 — 아래) | 참 | `rejected` | 해제(아래 주인·동결 조건) |
  | 취소 성공 → 재주문 그 밖의 `KisApiError`(EGW00201 · APBK0918 보유 부족 문구 · 코드만 APBK0400 인 다른 문구 · 모르는 코드) | 참 | `sending` | 🔴 유지 — 앞 전송이 접수됐을 수 있다 |
  | 취소 성공 → 재주문 전송 중 다른 예외(타임아웃 등) · 전송 중 교체 취소 | 참 | `sending` | 🔴 유지 — 나갔을 수 있다(풀면 다음 틱이 또 낸다). `selling_reconcile` 이 푼다 |
  | 취소 성공 → 재주문 접수 | 참 | `accepted` | 유지 — 새 주문의 종료가 푼다 |

  - 🔴 **「안 걸렸다」 = `_sell_not_placed_reason(exc)` 한 곳**(명세 부록 R4 D2) — 모듈 함수 · 동기 · never-raise(예외 = `None`). 재주문·수동 매도 라우트(`src/routes/CLAUDE.md` `manual-sell` 행) 공용. 분류는 `src.api.balance` 기존 판정 함수만(키워드 재정의 금지, AST AR4-1).

    | 순서 | 예외 | 반환 |
    |---|---|---|
    | 1 | `is_sell_qty_exceeded` — APBK0400 ∧ msg1 「수량」·「초과」 | `qty_exceeded` |
    | 2 | `is_market_closed_rejection` — 장운영시간 외 문구(프리마켓 문구는 두 분류기 모두 걸리고 여기서 끝 — `execute_sell` 과 같은 우선순위) | `market_closed` |
    | 3 | `is_market_order_disallowed` — 시장가 불가 문구(APBK1943 · APBK3013 계열) | `market_order_disallowed` |
    | — | 그 밖 — 비 `KisApiError` 예외(전송 오류 · HTTP 5xx · `RuntimeError`) · EGW00201 · APBK0918 보유 부족 문구 · 코드만 APBK0400 인 다른 문구 · 모르는 코드 | `None` = 「전송 중」 |

    - 🔴 표 밖은 「안 걸렸다」의 증거가 아니다 — `src/api/base.py::_request` 가 주문 POST 도 전송 오류(`httpx.RequestError`, 타임아웃 포함)·5xx 에 재전송해(KIS 거부 `rt_cd≠0` 은 재전송 안 함) 앞 전송이 접수됐을 수 있다(풀면 다음 틱 손절이 걸린 재주문 위에 또 나간다). 표 안 셋 = APBK0400 보장(명세 R3-2-3) 또는 결정적 거부(루트 `CLAUDE.md` 「NXT 매도 거부 좀비 차단」 과 같은 원리)라 안전, 장 경계 예외 = 「알려진 한계」 ③.
    - 🔴 분류 = msg1 문구 기반 — 코드가 같아도 문구가 키워드에 없으면 `None`(덜 푸는 쪽).
  - `except KisApiError` 본문 = `_sell_not_placed_reason` 판정 1회 + 끝 bare `raise` 뿐(`_cancel_and_reorder` 안 분류기 셋 직접 호출 금지, AST AR2-3). 이 판정 = 「무엇이 안 걸렸나」, 「누구의 표식을 푸나」 = `finally` 해제 조건.
  - 유지한 표식 = 걸린 재주문 종료 또는 `selling_reconcile`(열린 매도 0 · 180초)이 푼다.
  - 해제 조건 마지막 항 = `ticker in self._selling_locked_wait or self._manual_sell_orders.get(order_no, True)`(해제 시점 판독) — 자동 주문(표식 없음)·표식 참 manual = 참, **손님 manual**(`_added` 거짓 — 자동 매도가 `_selling` 주인) = 동결 표식이 있을 때만 참(없으면 자동 매도 주문이 걸려 있다). 재주문 번호 표식 승계 → 재주문의 재주문도 같다.
  - 해제 = `_selling` · `_selling_since` · `_selling_locked_wait` 동시 비움 + `[reorder_selling_released]`.
- **마커**(전부 `logger.*`, cap 없음 — 행위 밖):
  - `[sell_fill_holding_remains] order_no= ticker= owner= sold= held_after= ordered= src=` WARNING = 분할 매도 성공 서명(`src=increment` 짝이면 주문 종료가 거짓일 수 있다 — `[fill_qty_src]` 대조).
  - `[sell_fill_exceeds_holding] order_no= ticker= owner= held_before= fill= src=` WARNING(`fill=` = `hold_dec`, 0 정상).
  - `[sell_fill_owner_from_holding] order_no= ticker= from=<sid|none> to=<sid> src=` WARNING — `from=none` = MTS·발사 창, `from=<sid>` = 장부 전략 미보유(이상).
  - `[sell_fill_owner_ambiguous] order_no= ticker= sid= holders=<csv|error> src=` ERROR — 0 정상, 1건 = 조사.
  - `[sell_fill_db_error] step=save_position ticker= order_no= owner= held_after= err=` ERROR — 하루 여러 건 = RDS.
  - `[sell_fill_credit_absorbed] order_no= ticker= fill= absorbed_order= absorbed_blind= hold_dec= src=` WARNING = 늦은 통보 이중 차감 회피 건수.
  - `[sell_qty_reconciled]` WARNING 끝 `credit_src=orders|blind credit_orders= credit_qty= pre_orders= pre_cap=` — `credit_qty>0` = 재대조 순간 통보 진행 중, `pre_orders>0` = 원장 시작 전 주문 섞임(`pre_cap` 적용).
  - `[sell_qty_reconcile_orders_unavailable] ticker= reason=error|timeout|bad_row|page_full blind_credit=` WARNING = 종목 크레딧 경로(`blind_credit=` = 이번 가산분, 0 정상).
  - `[sell_qty_reconcile_skipped] ticker= reason=position_replaced` INFO = 조회 중 포지션 닫힘.
  - `[sell_qty_partial_sellable] ticker= strategy= held= sellable= positions= surplus= fire= pending=` WARNING = 걸린 외부 주문 옆 잔여 매도(`pending>0` = 미도착 외부 체결 차감).
  - `[sell_qty_partial_locked]` WARNING(`held > sellable` 일 때만) 끝 `surplus= fire= pending=<n|?> orders=ok|error|timeout|bad_row|page_full`(`orders` ≠ `ok` = 조회 불신 동결).
  - `[sell_qty_unnoticed_fills] ticker= strategy= held= sellable= positions= pending= eff=` WARNING = 걸린 매도 없는 보류(조회 성공). 드묾 — `selling_reconcile` 해제 뒤마다 반복되면 통보 유실 의심(계좌 잔량 = 운영자 몫).
  - `[sell_qty_hold_orders_unavailable] ticker= strategy= held= sellable= positions= orders=error|timeout|bad_row|page_full` WARNING = 걸린 매도 없는 보류 + 조회 불신(`orders=` = 실패 이유). 드묾.
  - `[reorder_selling_released] ticker= order_no= place=none|rejected reject=qty_exceeded|market_closed|market_order_disallowed|-` WARNING = 재주문 미걸림 해제(`reject=` = `_sell_not_placed_reason` 이유, `place=none` 이면 `-`). 드묾.
  - `[selling_freeze_released] ticker= order_no= reason=position_closed` INFO = 동결이 지키던 보유가 닫힘.
  - `[reorder_requery] verdict= ticker= order_no= remaining= held= fire_qty=` — `same` INFO, `manual` = J-2 표, 그 밖 WARNING.
  - 「매도 부분 체결」 INFO 끝 `held_after=` = 부분 체결마다 남은 보유.
- ⚠️ **알려진 한계**
  - **무관한 주문의 종료가 `_selling` 을 푼다** — 우리 손절 주문이 걸린 동안 MTS·손님 수동 매도가 끝나면 다음 틱이 추적 잔여를 또 낸다. 운영자 초과분 ≥ 추적 잔여면 통과해 운영자 몫을 판다(초과분이 없으면 APBK0400). 해결 = 「걸린 우리 매도 등록부」(후속 F-385-5). strict xfail = `tests/unit/engine/test_cycle385r2_round2.py` TQ22 · `tests/unit/engine/test_cycle385r_partial_locked_sell.py` TR18 · `tests/unit/routes/test_cycle385_manual_sell_selling.py` TR20 · TR20b(TR18·TR20 은 행위 단언 — 고쳐지면 XPASS 로 붉어진다). `increment` 퇴화(`fields[16]` 없음)의 발사 창 첫 통보 거짓 「종료」도 같다.
  - **과대 추적**(보통 다음 매도 APBK0400 → #1.5 가 회수, 운영자 몫이 있으면 APBK0400 없이 팔린다) 발생처 넷:
    - 재대조 두 조회 사이(수백 ms) 체결.
    - 종목 크레딧(조회 실패)이 유실 통보·유령분까지 들고 뒤 통보(우리 매도 체결 포함)를 흡수한 몫 — 우리 매도가 다 끝나도 추적이 남아, 운영자가 그 종목을 사면 그만큼 손절이 판다(strict xfail `tests/unit/engine/test_cycle385r3_round3.py` TK13).
    - 원장 시작 전 접수 주문의 재대조 크레딧(상한 `_pre_cap` 은 주문마다라 합이 참값을 넘을 수 있다, 명세 R3-13-4).
    - 재대조 `held` 가 t1 전 운영자 수동 매수분을 포함할 때.
  - 부분 잠김 판매의 `eff` 도 위 첫째·둘째 폭만큼 과대 → surplus 과소(운영자 초과분이 있으면 운영자 몫 매도).
  - **원장 시작 전 접수 주문이 재시작 뒤에도 체결 중 + 통보 지연** → 그 체결이 `pending` 에서 빠진 만큼 `eff` 과대 → 운영자 초과분이 있으면 부분 잠김 판매가 그만큼 더 쏜다(명세 R3-13-2).
  - **접수 시각을 못 읽는 행 = 「뒤」** — 재시작 전 주문이면 재시작 뒤 손절이 `[sell_qty_unnoticed_fills]` 로 보류(돈은 안전). KIS 가 `ord_dt`·`ord_tmd` 를 비울 때만. 8·6자리 숫자 확인은 매수 행 캡처뿐(매도·SOR 부모·자식 행 `ord_tmd` 미측정, 명세 R3-12 F-R3-1).
  - **다운타임 체결**(통보 없음)은 복원 수량에 없다 → 운영자 초과분 ≥ 그 양이면 재시작 뒤 첫 발사가 통과해 운영자 몫을 판다.
  - **재시작으로 잃은 통보**(전송 중 · 다운타임) = 원장·크레딧 모름 → 유령 보유(과대) 가능, 그 보유가 `held_zero` 면 `selling_reconcile` 이 `_selling` 을 못 푼다. 과소 추적은 안 만든다(명세 R3-1-7).
  - **통보 유실 유령** — 원장 시작 뒤 주문의 체결 통보 유실 + 운영자 초과분 → `[sell_qty_unnoticed_fills]` 보류가 `selling_reconcile` 해제 뒤마다 반복(APBK0400 1회 + 조회 2회, 돈 손실 없음).
  - **재주문 해제의 남는 틈**(전부 첫 항목 모양 — 우리 주문이 `_selling` 없이 걸림):
    - ① 앞 전송 접수(응답 유실) + 재전송 APBK0400 인데 숨은 재주문의 부분 체결 통보가 다음 틱 **전** 착지 → 추적이 재주문 수량 아래로 내려가 APBK0400 보장 해제 — 운영자 초과분이 있으면 그 몫이 팔린다(명세 R4-4 R4-1).
    - ② J-2 `manual`·`ambiguous`·`error` 재주문은 수량이 추적을 넘을 수 있어 같은 보장 없음(명세 R3-2-3).
    - ③ **장 경계를 가로지른 재시도** — 앞 시도가 경계 앞 접수(응답 유실), 재시도가 경계 뒤 장운영시간 외·시장가 불가 거부 → 걸린 주문 옆 `_selling` 해제(명세 R4-1). 닿는 경계 = NXT 15:20 하나(NXT 라우팅 수동 매도·NXT 원주문의 재주문만, NXT 잔량은 20:00 까지). 다음 KRX 손절은 운영자 초과분 ≥ 걸린 수량일 때만 통과. 15:30 KRX · 20:00 · NXT 프리장 = 해당 없음(15:30~16:00 은 `_market_rest_gate` 가 자동 매도를 막고 걸린 주문은 종가 체결·자동 취소).
  - **교체된 재주문 타이머가 손님 수동 매도 옆에서 `_selling` 해제**(명세 R4-4 R4-7) — 손님 수동 매도(`_added` 거짓)가 걸린 동안 자동 매도 원주문을 취소한 재주문 태스크가 CANCELLED 장부 `await` 창(ms)에서 교체 취소되면 `finally` 가 `place=none` 으로 푼다 → 다음 손절이 수동 매도 위에 쌓이고, 운영자 초과분 < 쌓인 몫이면 운영자 몫이 팔린다(첫 항목 계열).
  - **수동 매도가 발사 여부 불명으로 실패하면 `_selling` 잔류** — EGW00201 · 전송 예외 · 모르는 코드 · 보유 부족 문구 = 앞 전송 접수 가능이라 유지(`[manual_sell_selling_kept]`). 그동안 그 종목 자동 손절이 그 주문 종료 통보 또는 `selling_reconcile`(15분 sync + 180초, 09:30 전 sync 없음)까지 정지(`src/routes/CLAUDE.md` `manual-sell` 행).
  - 조회 실패 중 운영자 초과분이 있으면 재대조가 그 초과분을 추적에 받아들일 수 있다(명세 R-13-8).
  - 혼합 보유(전략 추적분 + 추적 밖 수동 매수분)의 수동 부분 매도는 전략 보유에서 빠진다(주식 구별 불가 — 추적분이 닫힌 뒤 sync 가 나머지를 재채택).
  - 우리 주문이 통보 없이 사라지면(MTS 취소 · 거래소 자동취소 · 접수 뒤 거부) `_selling` 은 `selling_reconcile` 까지 잔류(09:30 전 sync 없음). 동결이 기다리던 외부 주문이 통보 없이 사라져도(앱 취소) 같다.
  - `_selling` 에 주인 식별자 없음 — 해제 순간의 표식이 다른 코루틴의 새 표식일 수 있다(첫 항목 경로로 한 번 풀린 뒤에만). 재주문 해제·수동 매도 라우트 되돌림도 주인을 안 본다(결과 = 첫 항목).
  - 주문번호 형식(0-패딩)·SOR 주문의 TTTC0081R 행 모양 = 운영 미측정(명세 R-14 F-R1·F-R3) — SOR 부모·자식 합계 행이 섞이면 파서 합산이 이중 계산.
- 명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md`(부록 R · R2 · R3 · R4) · 회귀 = `tests/unit/engine/test_cycle385_b7_partial_sell.py` · `tests/unit/engine/test_cycle385_reorder_requery.py` · `tests/unit/engine/test_cycle385r_recount_credit.py` · `tests/unit/engine/test_cycle385r_partial_locked_sell.py` · `tests/unit/engine/test_cycle385r2_round2.py` · `tests/unit/engine/test_cycle385r3_round3.py` · `tests/unit/engine/test_cycle385r4_round4.py` · `tests/unit/routes/test_cycle385_manual_sell_selling.py` · AST = `tests/unit/ast/test_cycle385_ast_b7.py`

## 체결단가 정합 (`_handle_buy_fill` / `_handle_sell_fill`)

- `update_trade_status` 는 항상 **`price=`** 를 넘긴다 — 체결단가는 체결통보 `CNTG_UNPR`(`handler.py` `fields[10]`)이고 주문 응답(TTTC0011U/TTTC0012U)에는 체결가가 없다. 안 넘기면 PENDING 의 `record_price`(LIMIT 주문가 / MARKET 은 scanner `current_price`)가 남는다.
- 보정 INSERT 가 `UniqueViolation` 이면 `try/except Exception` + 강제 UPDATE 한다 — 매수 `_update_trade_status_by_order_no(price=price)` · 매도 `_update_trade_status_by_order_no(price=book_price)`(cycle392, 아래 「SELL 장부는 주문 단위 누적이다」 절).
- 호출부 6곳(C1~C6)은 전부 **`order_no=order_no`** 로 WHERE 를 그 주문 행으로 좁히고, 전량 체결 분기 2곳은 **`match_partial=True`** 로 PARTIAL 행까지 덮는다.
- 가드 = AST G-161-K-6(`_handle_buy_fill` 영역 `update_trade_status` 의 `price=` 의무) + `test_cycle273b_ast_no_behavior_guards.py` AST1/AST2.
- **PARTIAL·CANCELLED `affected==0` 관측 (cycle358)** — 흡수 경로가 없는 PARTIAL·CANCELLED 4 호출부(매수·매도 × 2)는 `affected==0` 이면 `_emit_trade_status_update_miss`(`_trade_status_update_miss_logged: KstDailyEmitCap`, 1회/(order_no, status)/일)가 `[trade_status_update_miss] status=PARTIAL|CANCELLED order_no= ticker= side=` WARNING 을 낸다. COMPLETED 는 보정 INSERT/강제 UPDATE 가 흡수한다. 관측 전용 · never-raise(`observer_trace.trace_observer_failure`, 행위는 cap 밖).
- **SELL 장부는 주문 단위 누적이다(cycle392)** — 한 매도 주문이 체결통보 여러 건으로 끝나도, 장부(네 쓰기 곳 COMPLETED UPDATE · PARTIAL UPDATE · 보정 INSERT · 강제 UPDATE 전부) `profit_loss` = 그 주문의 손익 **증분 합**(= 메모리 `daily_realized_pnl` 에 그 주문이 더한 합과 같은 값), `price` = 그 주문의 **체결 가중평균**(Σ가격×수량 ÷ Σ수량)을 **원 단위 절사**한 `int`(`_vwap_floor` — 반올림·올림 없이 내림, cycle396 사용자 요청). 누적기 `OrderEngine._sell_fill_book: dict[order_no, (체결수량 합, 체결금액 합, 손익 증분 합)]` — 키는 raw `order_no`(`_filled_qty` 와 같은 체계), 수명도 `_filled_qty` 와 같다(주문 종료 분기에서 같이 pop, `reset_daily_state()` 에서 같이 clear). 누적·장부 로컬 확정은 `daily_realized_pnl +=` 과 그 뒤 첫 `await` 사이 동기 영역에서 끝내고(I4), 네 쓰기 곳은 그 뒤 재계산 없이 그 로컬 값만 쓴다(I5) — 같은 주문의 다음 통보가 끼어들어도 앞 통보의 쓰기가 뒤 값을 섞지 않는다. 통보 1건 주문은 결과 불변(가격·손익 그대로). 전량 체결 INFO 끝에 `avg=` 가중평균(정수)이 붙는다. 남는 한계 — **주문 도중 재시작**은 재시작으로 `_order_qty`·`_filled_qty`(그리고 `_sell_fill_book`)가 비므로 두 갈래다: 매핑 있는 출처(`map`/`payload`)는 재시작 전 첫 PARTIAL 값이 장부에 PARTIAL 로 남고 재시작 뒤 통보는 한 건도 기록되지 않는다(종료 분기 조건 `total_filled >= ordered_qty` 에 재시작 뒤 통보 혼자서는 못 닿는다) · 주문수량을 모르는 `qty_src="increment"`(매핑·payload 둘 다 없는 외부 주문)만 재시작 뒤 첫 통보 한 건이 장부에 남는다(D6 로 드묾) · 부분 체결 뒤 잔량이 취소로 끝난 행은 첫 PARTIAL 쓰기 값 그대로(실측 0건). **매수 쪽(`_handle_buy_fill`)은 그대로다** — 장부 BUY `price`·메모리 `pos.buy_price` 모두 마지막 통보가(손절 기준가라 매매 행위 변경 = domain-consult + 사용자 승인 대상, 실측 20일 0건). 가드 = `tests/unit/engine/test_cycle392_sell_book_cumulative.py` · `tests/unit/ast/test_cycle392_ast_sell_book.py` · 절사 = `tests/unit/engine/test_cycle396_vwap_floor.py` · `tests/unit/ast/test_cycle396_ast_vwap_floor.py`.

## 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369)

보유 중인 관리종목·단기과열 지정 종목은 시장가로 판다. 그날은 어느 전략도 그 종목을 새로 사지 않는다(사용자 결정 2026-09-25·26). 설계 = `_workspace/domain_consult/cycle369_status_51_59_exit.md` · 명세 = `_workspace/red/cycle369_status_exit_spec.md`.

### 판정 — `classify(output) -> StatusRead` (순수 · never-raise)

- 소스 = REST `FHKST01010100` 응답 하나. 조회는 `condition.fetch_stock_detail` 만 쓴다(시세 풀 · 5초 캐시 · 단일 비행). leaf 는 `kis_*` 를 직접 부르지 않는다(AST F6).
- 전용 플래그 = `mang_issu_cls_code`(관리) · `short_over_yn`(단기과열 **지정·연장** — 예고는 `N`). `.strip().upper()` 뒤 `"Y"`/`"N"` 만 유효하고 그 밖은 `None` + `[status_exit_unknown_value]`.
- 식 = `managed = mang == "Y" or (mang is None and iscd == "51")` · `overheat = short_over == "Y" or (short_over is None and iscd == "59")` · `halted = iscd == "58" or temp_stop_yn == "Y"`. `flagged = managed or overheat` · `dedicated_flagged = mang == "Y" or short_over == "Y"`(폴백 제외).
- 🔴 **종목상태(`iscd_stat_cls_code`) 51·59 는 전용 플래그가 비었을 때만 쓴다** — 명시 `"N"` 을 iscd 가 뒤집지 못한다. 어긋나면 플래그를 따르고 `[status_exit_iscd_conflict]`.
- 🔴 **매도는 전용 플래그 `"Y"` 일 때만 쏜다(`dedicated_flagged`)** — 51 은 정상 ETF·스팩·우선주에도 붙는다(cycle203 실측). 폴백만 해당이면 `fallback_only`(arm + `[status_exit_fallback_only]`, 주문 없음). **매수 차단은 폴백도 쓴다**(막는 쪽이 안전).
- 🔴 **판정에 쓰지 않는 것** — `ssts_hot_yn`(공매도과열) · master `short_over_cls_code`(`1` = 예고) · `stock_master.raw`/`master_raw`(하루 늦다) · `H0UNMKO0` 프레임 단독. 프레임은 `market_operation_monitor.get_last_event` 를 **읽기만** 해 `[status_exit_frame_hint]` 로 남긴다.
- 「모름」(판정 안 함) = `fetch_fail`(응답 실패·빈 output) · `stck_prpr` 이 양의 정수 아님 · `flags_missing`(전용 플래그가 비고 iscd 폴백도 안 걸림).

| 용도 | 해당 | 모름 |
|---|---|---|
| 청산 | 해당 ∧ `halted` → 대기(`wait_halt`) · 전용 플래그 `Y` ∧ 가격 유효 → 발사(`fire`) · 폴백만 해당 → `fallback_only`(arm·경고, 발사 없음) | `fetch_fail` · 가격 무효 · `flags_missing` |
| 매수 차단 | 해당(폴백 포함 · 정지·가격 무관) | `fetch_fail` · (`flags_missing` ∧ ¬해당) |

`_sell_verdict` 판정 순서가 계약이다 — `fetch_fail` → 해당 ∧ `halted` → 전용 `Y` ∧ 가격 유효 → 폴백만 해당 → 가격 무효·`flags_missing` → 해당 없음(`none`).

### 보유 청산

- 대상 = `registry.all()`(**꺼진 전략 포함** — `risk.on_tick` 은 켜진 전략만 돈다)의 `quantity > 0` 포지션. 조회는 종목당 1회, 판정은 (전략, 종목)마다.
- 🔴 **발사 창 = `FIRE_WINDOW_START`(09:00:30) ≤ now < `FIRE_WINDOW_END`(15:28:00) KST**, 그 패스가 읽은 값으로만 쏜다. 창 밖 발사 금지 — 프리장은 NXT 지정가 변환으로 미체결 `_selling` 이 남고, **16:00~20:00 KRX 애프터마켓은 단기과열종목을 거래 대상에서 뺀다**(44/41 연속 거부 → 포기 래치 + CRITICAL).
- 발사 = `await asyncio.shield(order_engine.execute_sell(t, Signal.STATUS_EXIT, sid))`(`limit_price` 없음 = 시장가). 거래소(09:00~20:00 `krx_by_clock` → KRX)와 거부 처리(APBK1943 지정가 5호가 폴백 · APBK0918 포지션 보존)는 `execute_sell` 규약 그대로다.
- 🔴 **`execute_sell` 은 `asyncio.shield` 안에서만 부른다**(AST F8c) — `stop()` 이 패스를 취소해도 제출 중 주문이 끝까지 가서 매핑·PENDING 없는 반쪽 주문이 안 생긴다. 패스에는 `CancelledError` 가 전파된다.
- 발사 조건 = 모드 `enforce` ∧ 판정 `fire` ∧ `t not in order_engine._selling`(읽기만) ∧ 그날 그 종목 발사 < `MAX_FIRES_PER_DAY`(3) ∧ **발사 직전 다시 본 창 안** ∧ **발사 직전 다시 읽은 모드 `enforce`**. 횟수가 차면 `[status_exit_giveup]` CRITICAL 1회/일. 카운터 키 `(날짜, 종목)` — `_reset_daily_state` 무접촉.
- 🔴 **발사 순서가 계약이다** = 창 재확인(`_now_kst()`) → 모드 재확인(`_modes["sell"]`, 메모리 · `await` 0) → 발사 횟수 증가 → `[status_exit_fire]` logger WARNING(동기) → `execute_sell`. 창이 맨 앞이라 15:28 을 넘긴 미발사가 3회를 축내지 않는다. 모드 재확인으로 패스 도중 `PUT sell_mode=off` 가 뒤 종목부터 먹는다(`observe` 면 `[status_exit_would_fire]`). 횟수 증가가 await **전**이라 예외가 나도 상한·giveup 이 산다. 발사 예외는 흡수해 `[status_exit_fire_error]`(`CancelledError` 는 전파).
- 🔴 **청산 패스는 `system_logs` 를 직접 쓰지 않는다**(`await`·fire-and-forget 0, AST F8b) — 느린 RDS 가 뒤 종목 매도를 15:28 밖으로 밀면 안 된다. 영속은 루트 `_DbLogHandler`(`src/main.py`)가 `src.*` 로거 INFO 이상을 `put_nowait` 로 받아 `[src.engine.status_exit_watch] <메시지>` 한 줄로 적는다. 🔴 같은 메시지를 `write_log` 로 또 쓰지 않는다 — 사건당 두 줄(cycle72 G-6 · AST F3b). leaf 는 태스크·타이머 0(AST F8).
- **재시작해도 하루 3회 상한이 이어진다** — `task_loop` 시작 때 오늘(KST) `system_logs.search_logs` 에서 메시지 **어디든** `[status_exit_fire]` 를 담은 행(핸들러 접두 때문에 `startswith` 불가)의 종목별 `attempt=` **최댓값**을 메모리 카운터와 `max` 로 합친다. `[status_exit_fire_error]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 은 그 부분 문자열을 담지 않는다. 조회 실패 = DEBUG `[status_exit_fire_seed_failed]` + 메모리 카운터만(fail-open).
- ⚠️ 핸들러 큐(`maxsize=10_000`)가 차서 줄을 버리면 그 발사는 흔적 없이 사라지고 재시작 시드에도 안 잡힌다.
- **재시작 뒤 걸려 있는 59 청산 주문** — `_selling` 이 비어 첫 패스가 한 번 더 쏘지만 `APBK0400` 거부 → #1.5 재대조 `sellable == 0 ∧ held > 0` → `[sell_qty_locked]`(포지션 보존 · `_selling` 유지)로 끝나 이후 패스는 건너뛴다. 걸린 주문은 체결통보나 `selling_reconcile`(180초 age gate · 열린 주문 검사)이 수습한다 — 두 번 팔리지 않는다. 거부된 발사도 3회에 센다.
- ⚠️ **특별 개장일(지연 개장 — 수능일이 표준 사례)** — 발사 창이 고정 시계라 개장 전 09:00:30 발사가 거부되며 3회를 소진해 `[status_exit_giveup]` 이 날 수 있고, 15:28 뒤 늦게 닫히는 장도 못 본다. **운영자 조치** = 그날 개장 전 `PUT /api/integrations/status-exit {"sell_mode":"off"}`(또는 `observe`) → 정규장 개장 뒤 `enforce`. 같은 한계 = `_market_rest_now`(「order_engine.py」 규칙 3).
- 정지(58·임시정지)가 겹치면 기다린다(`[status_exit_wait_halt]` 1회/일) — 풀린 다음 패스에서 팔고 주문을 반복해 넣지 않는다. 폴백만 해당이어도 정지 중이면 `wait_halt`(정지 판정이 먼저).
- 청산 패스는 지금 보유하지 않는 `(종목, 전략)` 을 `_armed` 에서 뺀다.
- 🔴 **새 취소·재주문 타이머를 만들지 않는다**(AST F8) — 단기과열 30분 단일가 대기는 `selling_reconcile` 의 열린 매도 주문 보존(`open_order` 유지)이 견딘다.
- 🔴 **익일청산 큐 `_pending_next_day_clear` 를 재사용하지 않는다**(AST F9) — 한 번 쏘면 결과와 무관하게 항목을 지운다.

### 당일 매수 차단 (지정 첫날 포함)

- 규칙 = 그날(KST) **장중** 라이브 조회가 해당이면 그날 그 종목의 신규 매수 신호를 **7전략 전부**에서 막는다. 매일 새로 읽어 지정 첫날(T+1)부터 막힌다(진입 필터 `_is_master_blocked_for_entry` 는 T일 16:10 값이라 첫날을 못 본다).
- 막는 자리 = `StrategyBase._account_soft_gate_blocked` **첫 문장** `if self._status_buy_blocked(ticker): return True`(AST J25) — 공통 게이트라 새 전략도 자동으로 따르고 게이트 위치(폴·래치형 5전략 첫 문장 / momentum·VB 발사 직전)도 같다.
- `_status_buy_blocked` → `status_exit_watch.buy_gate(ticker, strategy_id, *, cand)` = **순수 메모리 조회**(`await`·DB·HTTP·`write_log` 0 — AST J23). 예외 = `False`(fail-open) + DEBUG `[status_block_gate_failed]`.
- 🔴 **막는 순간 그 전략의 그 종목 edge 기준가를 비운다**(`StrategyBase._clear_edge_baseline_on_block`, 순수 메모리 · never-raise) — 안 비우면 해제 뒤 첫 틱이 옛 기준가 대비 거짓 돌파다. 비운 뒤 첫 틱은 기록만 한다. 대상은 **모양으로** 고른다 — 중첩 `_prev_price[t]`(VB·LTV `{board: price}`)와 momentum `_prev_prdy_rate[t]` 만. 🔴 평평한 `_prev_price`(BFB·VCP `{ticker: price}`)는 건드리지 않는다 — 없는 값이 `0` 으로 읽혀 `0 < level <= current` 거짓 돌파가 된다. `observe`·`off` 에서는 비우지 않는다.
- `cand`(이 전략이 지금 이 종목을 후보로 드는가)는 **집계만** 가른다 — 참일 때만 `_skip_counts` 증가 + `[status_block_buy_skip]`. 판정 = `StrategyBase._is_status_gate_candidate`(momentum·VB `_ALWAYS_STATUS_GATE_CANDIDATE_SIDS` 는 항상 참, 나머지는 `get_scanned_tickers()`·`_targets`·`_candidates` 멤버십).
- 🔴 **수량 0 반환으로 막지 않는다** — 「매수 수량 0 → 900s cooldown(투자금 부족)」 오귀인이 된다. 🔴 `registry.is_ticker_blocked_for_buy`(8영역)에도 넣지 않는다 — `check_buy_signal` **앞** `continue` 라 기준가가 얼고 스윙 폴 조회·관측 훅이 빠진다.
- 🔴 **못 읽은 종목은 막지 않는다(fail-open)** — 시세 풀 장애 하나로 7전략 매수가 멈추면 안 된다. 새는 경우는 청산 패스가 다음 칸(≤300초)에 팔고 `[status_exit_fire] bought_today=1` 로 드러난다.
- 판정 완료는 **장중(≥09:00:00) 조회만** 인정한다. 장 전 해당 = `phase=pre` 차단, 장중 clean 이면 해제(`[status_block_released] reason=pre_session_stale`). 장중 해당(`phase=in`)은 그날 풀리지 않는다(`[status_block_flip_ignored]`).
- 수명 = 항목의 KST 날짜(다르면 게이트가 무시). `_reset_daily_state` 무접촉. 하루 상태는 전부 날짜를 담는다 — `_buy_flags`·`_pre_seen`·`_in_seen`·`_armed`·`_passes` 는 값에, `_unknown_attempts`·`_fires`·`_skip_counts`·`_emitted` 는 키에. P0 시작 때 `_purge_stale_day(오늘)` 이 다른 날 항목을 지운다.
- 막지 않는 것 = 청산·손절·트레일링·익일청산·15:20 강제청산 · 구독.

### 언제 읽나 — `task_loop(sched)` + 관측 훅

| 패스 | 시각 | 대상 · 규칙 |
|---|---|---|
| P0 | `PRE_PASS_TIME` 08:45. enabled 전략 `tradable_boards` 에 `pre_nxt` 가 있으면 `PRE_PASS_TIME_NXT` 07:59(`pre_pass_time(registry)`). `BUY_OPEN_TIME`(09:00:00) 전까지 | 보유(청산 `off` 면 제외) ∪ `buy_targets`(매수 차단 `off` 면 제외). 기록·arm 만(주문 0) |
| P1 | `_p1_start_time()` = `BUY_OPEN_TIME` + `condition._PRICE_CACHE_TTL` = **09:00:05**, 1회/일 | `buy_targets(registry, exclude_swing=True)` − 오늘 장중 판정 완료 − 모름 `MAX_UNKNOWN_ATTEMPTS`(3회) 소진, `_p1_order` 순. 상한 `P1_WALL_CLOCK_MAX_S`(25초) — 넘으면 `truncated=1`, 나머지는 INC |
| INC | P1 뒤 `INC_INTERVAL_S`(60초)마다, `< INC_END_TIME`(15:20) | `buy_targets(registry)`(스윙 포함) − 오늘 장중 판정 완료 − 모름 3회 소진 |
| 청산 | 창 안 첫 반복 즉시 + 격자 `09:00:30 + k·SELL_INTERVAL_S`(300초) | 보유 |
| 관측 훅 | 항상 | `condition._fetch_stock_detail_and_cache` 가 **새로 조회할 때마다** |

- `buy_targets(registry)` = enabled 전략의 `get_scanned_tickers()` ∪ `_targets` 키 ∪ `_candidates` 키 ∪ (momentum enabled 면) `scanner.ticker_prev_close` 키 − `registry.is_ticker_blocked_for_buy` − 6자리 숫자 아닌 것. 순서(`_GROUP`) = momentum 급등 목록 → VB·LTV(09:00:35 매수) → BFB·VCP(운영 DB `entry_start` 09:05) → donchian·kojiro, 동순위는 종목코드 순.
- 🔴 **P1 은 09:00:05 에 시작한다** — `condition` 5초 캐시가 08:59:55~09:00:00 조회를 돌려주면 장 전 값이 「장중 clean」 으로 봉인된다. 캐시 TTL 이 바뀌면 P1 시각도 바뀐다(TTL 조회 실패 = 5.0초).
- 🔴 **P0 창의 끝은 `BUY_OPEN_TIME`(09:00:00)이다**(`due_actions` 의 `pre_time <= t < BUY_OPEN_TIME`) — 09:00:00~05 에는 어떤 패스도 돌지 않는다. `/api/trading/restart` 가 condition 캐시를 안 비워, 그 5초의 P0 가 08:59:5x 캐시를 「장중 clean」 으로 기록하면 P1 이 그 종목을 건너뛰기 때문이다.
- **P1 은 스윙(donchian·kojiro)을 읽지 않는다**(`exclude_swing=True`) — 스윙 매수 폴(09:05~09:30)의 조회를 관측 훅이 기록한다. 거르는 자리는 momentum 급등 목록을 채운 **뒤**다(앞이면 `ticker_prev_close` 의 스윙 종목이 momentum 몫으로 다시 들어온다).
- **P1 순서 `_p1_order`** — `scanner.ticker_prices[t]["prdy_ctrt"]`(읽기만)가 +29% 에 가까운 순, 값이 없으면 `buy_targets` 순으로 뒤에. `change_rate` 키는 읽지 않는다(`test_cycle365_change_rate.py` G-365-P4-9 가 `src/engine/` 전체에서 그 리터럴을 막는다).
- 관측 훅은 스윙 매수 폴·VB/LTV 기준가 REST·momentum 급등 스캔의 **기존 조회를 추가 호출 0 으로** 기록한다(`src=fetch`). 캐시 적중 경로는 훅을 부르지 않는다.
- **조회 한 번은 한 번만 기록한다** — 자기 패스가 조회 중인 종목은 `_pass_fetch_active` 에 있어 훅이 건너뛰고 패스가 `src=p0|p1|inc|sell` 로 기록한다. 🔴 훅은 **이중 try**(condition 쪽 + leaf 쪽)가 계약이다 — 예외가 새면 모든 FHKST 소비자가 깨져 VB·LTV 목표가가 서지 않는다(AST J16).
- 루프 = 순수 planner `due_actions(now, …)` + `_sleep(LOOP_TICK_S)`(1초). `FIRE_WINDOW_END`(15:28) 뒤 `[status_exit_loop_exit] reason=after_close`, `_running` 거짓이면 `reason=running_false`. 재시작하면 그 시각의 패스부터 즉시 돈다. 루프가 끝나도 그날 차단 항목·훅 기록은 살아 게이트는 계속 막는다.
- 🔴 **휴장일로 확정된 날은 어떤 패스도 돌지 않는다** — 매 반복 `trading_calendar.is_open_day(오늘)` 이 `False` 면 할 일을 비운다(주말·공휴일 수동 기동이 금요일 값으로 팔지 않게). `None`(모름)·예외는 돈다.
- 배선 = `scheduler.start()` 의 `self._status_exit_task = asyncio.create_task(status_exit_watch.task_loop(self))` 1줄 + task_attrs 세 튜플(AST S1·S1b). leaf 가 `sched` 에서 읽는 것 = `registry` · `order_engine` · `_running`.

### 킬스위치 — `system_config` 2키

| 키 | 대상 | 키 없음 | 알 수 없는 값 | DB 조회 실패 |
|---|---|---|---|---|
| `status_exit_mode` | 보유 청산 | `enforce` | `observe` + `[status_exit_mode_invalid]` 1회/일 | 직전 값 유지 |
| `status_buy_block_mode` | 당일 매수 차단 | `enforce` | 〃 | 〃 |

- 🔴 **「키 없음」은 행 자체가 없을 때뿐이다** — 모양이 틀린 행은 getter 가 어휘 밖 마커 `__cycle369_malformed__` 를 돌려줘 `observe` 가 된다(행 모양 = `src/db/CLAUDE.md` `system_config.py` 절). 깨진 행을 `enforce` 로 읽으면 끄려던 매도가 켜진다.
- 값 = `enforce` · `observe`(판정만 — 청산 `[status_exit_would_fire]`, 매수 게이트 `False` + `[status_block_buy_would_skip]`) · `off`(그 축 조회 패스 생략 · 게이트 `False`). 관측 훅 기록은 `off` 에서도 계속된다.
- 두 키 = 롤백 상황이 다르다(잘못 팔면 청산만, 과잉 차단이면 차단만 끈다). 「키 없음 = enforce」(ρ축 「키 부재 = OFF」 와 반대)는 사용자 결정이다 — 양성 종목에만 걸리고 결측은 fail-open 이라 전체 정지 경로가 없다.
- 새로 읽는 시점 = task 시작 직후 + **모든 패스 시작**(`refresh_modes()`) — SQL UPDATE 는 다음 패스에 반영된다. 청산 패스는 **발사 직전마다**, `buy_gate` 는 호출마다 메모리 모드를 다시 읽는다. 매수 패스(P0·P1·INC)의 **조회 대상**만 패스 시작 때 모드로 정한다.
- 🔴 **즉시 반영 = `PUT /api/integrations/status-exit` — 메모리가 DB 쓰기보다 먼저다**(라우트 순서 = `src/routes/CLAUDE.md` 그 행) — `pg.execute` 는 커넥션 획득 상한이 없어 RDS 가 멈추면 `off` 가 메모리에 닿지 못한다. leaf 계약 = `apply_mode(kind, mode, persisted=False)` 는 **고정 반영**, `persisted=True` 는 저장 성공 뒤 고정 해제, 생략 = 저장 성공 취급.
- 🔴 **저장에 실패한 축은 고정된 채 남는다** — 그 축의 다음 성공 저장이나 재시작까지 `refresh_modes()` 가 DB 값으로 덮지 않고 `[status_exit_mode_pinned] kind= mode=` WARNING 1회/(날짜, 축). 저장 못 한 `off` 를 다음 refresh(매수 60초 · 청산 300초 안)가 `enforce` 로 되살리면 안 된다. ⚠️ 성공하는 PUT 도 DB 쓰기 전엔 고정이라 그 사이 refresh 가 그날 1회 몫을 쓸 수 있다 — 저장 성공은 PUT 응답 `persisted` 로 본다.
- **축마다 세대 번호**(`_generation`) — `refresh_modes()` 는 읽기 전 세대를 기억해, 기다리는 동안 PUT 이 그 축을 바꿨으면 늦게 온 옛 값을 버린다.

### 구독은 건드리지 않는다

🔴 사용자 원문 「재구독 중지」 는 글자 그대로 구현하지 않는다(사용자 동의 2026-09-26) — 보유 종목 구독을 끊으면 청산 주문이 거부됐을 때 손절이 눈을 감는다. leaf 에는 `src.realtime` import 0 · `unsubscribe` 토큰 0(AST F1). 체결 뒤 구독 해제는 기존 `_unsubscribe_if_no_other_strategy` 가 한다.

### 관측 마커

- 영속 = (1) leaf 가 `write_log` 로 직접 쓰는 줄은 `[status_block_summary]` 하나(매수 패스 끝 `await` — 발사 경로 아님) (2) 나머지 INFO 이상은 루트 `_DbLogHandler` 가 `[src.engine.status_exit_watch] ` 접두로 옮긴다. `system_logs` 에서는 마커를 부분 문자열로 찾는다.
- WARNING = `[status_exit_fire] ticker= strategy= reason=managed|overheat|managed+overheat iscd= mang= short_over= qty= mode=enforce attempt= bought_today=0|1` · `[status_exit_would_fire] ticker= strategy= reason=`(1회/(날짜, 종목, 전략)). CRITICAL = `[status_exit_giveup] ticker= strategy= fires=`. WARNING + `write_log`(접두 없음) = `[status_block_summary] day= blocked= tickers= mode= skips=<전략:횟수,…>`(차단 집합·skip 횟수가 바뀐 패스 끝에만 — 매수 차단의 유일한 영속 기록).
- WARNING(logger) = `[status_block_armed] ticker= reason= phase=pre|in src=fetch|p0|p1|inc|sell iscd= mang= short_over= cand=` 1회/(날짜, 종목) · `[status_exit_fallback_only] ticker= strategy= iscd= mang= short_over=` 1회/(날짜, 종목) · `[status_exit_mode_pinned] kind= mode=` 1회/(날짜, 축) · `[status_exit_fire_error]` · `[status_exit_mode_invalid]` · `[status_exit_pass_failed] action=` · 라우트의 `[status_exit_mode]`.
- INFO = `[status_exit_armed]` · `[status_exit_disarmed]` · `[status_exit_wait_halt]` · `[status_exit_unknown]` · `[status_exit_unknown_value]` · `[status_exit_iscd_conflict]` · `[status_exit_frame_hint]` · `[status_exit_summary] held= fired= mode=` · `[status_block_released]` · `[status_block_flip_ignored]` · `[status_block_pre_session_check] pre=Y|N in=Y` · `[status_block_buy_skip]` · `[status_block_buy_would_skip]` · `[status_block_unknown] ticker= attempts= reason=fetch_fail|flags_none giveup=0|1`(첫 회·상한 도달 때만) · `[status_block_pass] kind=p0|p1|inc` · `[status_exit_loop_exit]`.
- DEBUG(fail-open 흔적) = `[status_block_gate_failed]` · `[status_block_baseline_clear_failed]` · `[status_observer_failed]` · `[status_block_record_failed]` · `[status_exit_mode_read_failed]` · `[status_exit_fire_seed_failed]` · `[status_exit_write_log_failed]` · `[status_exit_purge_failed]`.
- 로그 상한 = 모듈 전역 `_emitted` 집합(키에 날짜 — 1회/일).
- `cand=`(`[status_block_armed]`·스냅샷 `blocks[].cand`) = `_is_global_candidate(t)` = `t in buy_targets(registry)`(최근 패스의 `_last_registry`, 패스 전이면 0 · 보유 종목은 0). 1 인 차단 = 「진입 필터가 놓친 첫날」.
- 패스 기록 `_passes[kind]`(`p0`·`p1`·`inc`) = `targets · read · flagged · fetch_fail · unknown · truncated · elapsed_ms · at · day`. 로그에는 `unknown`·`fetch_fail` 칸이 없어 `[status_block_unknown]`·`[status_exit_unknown]` 줄 수로 센다.

### 테스트 격리와 가드

- 루트 `tests/conftest.py` autouse `_neutralize_status_watch` 가 매 테스트 전후 `reset_state_for_test()` 를 부르고, 마커 `real_status_watch` 가 없으면 `observe_fhkst` → no-op · `buy_gate` → `False` · `task_loop` → 즉시 반환. leaf·배선을 직접 검증하는 테스트만 `real_status_watch` 로 옵트아웃한다. 🔴 이 중립화는 메타 가드 Y14 가 벽시계와 무관하게 봉인한다(`test_6` 은 평일 10:00 KST 고정).
- 가드 = `tests/unit/ast/test_cycle369_ast_status_exit.py`(F1~F4 · F4b · F3b · F6~F9 · F8b · F8c · J16 · J23 · J25 · S1·S1b · R7 · Y14). F4 는 `src.db.system_logs`·`src.db.system_config` **모듈 핸들**로 닿는 속성을 허용 목록(`write_log`·`safe_write_log`·`search_logs`·`SEARCH_MAX_LIMIT`·getter 2종)으로 묶고 F4b 가 공허하지 않음을 확인한다. 회귀 = `tests/unit/{engine,db,routes}/test_cycle369_*.py` · 실 Postgres `tests/integration/test_cycle369_*_pg.py`.

## strategy_base.py

사이징 규칙(삼중 한도·K축·ρ축·시장 유닛의 의미·롤백 수단·반영 시점)의 정본 = `strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절. 여기에는 헬퍼·마커·순수성 계약만 적는다.

- `StrategyBase` 추상 메서드: `prepare(self, *, as_of: date | None = None)` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`
- **준비 기준일 헬퍼 3종**(`as_of` 계약·PV-1 = `strategies/CLAUDE.md` 「prepare 공통」 절)
  - `_resolve_prepare_as_of(as_of) -> (as_of_date, preview)` — `None`·오늘 = (오늘, False) · 미래 = (as_of, True) · 과거 = `ValueError`(DB 가 as_of 뒤 봉을 돌려줘 과거 재현이 성립하지 않는다).
  - `_preview_keep_tickers() -> set[str]` — 자기 보유 ∪ **자기** 익일청산대기(`trading_scheduler._pending_next_day_clear` 의 `(ticker, 자기 strategy_id)`). 미리보기 와이프 뒤에도 같은 객체로 남긴다. 🔴 다른 전략의 보호 종목을 넣지 않는다 — 그 전략의 후보 목록·`_scanned_tickers`·kojiro `held_only`·donchian `get_targets_status` 가 오염된다.
  - `_preview_skip_tickers() -> set[str]` — 자기 보유 ∪ `scanner._collect_protected_tickers_for_scanner()`(전 전략 보유 ∪ 익일청산). 종목 루프가 건너뛰는 집합. 🔴 **합집합** — 헬퍼가 조회 실패를 ∅ 로 삼켜도 자기 보유는 지킨다. 헬퍼 예외는 흡수한다.
- **생명주기 훅** (기본 no-op + override):
  - `_reset_daily_state()` — 일일 transient 상태 정리. `scheduler._reset_daily_state`(21:30 정산 후)가 전략별로 호출(try/except). override = momentum `_prev_prdy_rate.clear()`(익일 첫틱 거짓돌파 차단) + BFB `_breakout_first_seen.clear()`. 🔴 **보유결합 필드(`_limit_up_reached`/`_partial_exit`)는 지우지 않는다** — 익일 보유(LTV 상한가 밤샘) 청산 모드가 깨진다.
  - `on_position_closed(ticker)` — 보유 축이 닫힐 때 per-ticker 보유결합 상태 정리. 호출 site 는 `order_engine` **정확히 2곳**(`_handle_sell_fill` 의 `if close_position:` 닫기 묶음 + `execute_sell` insufficient_qty reconciliation, 각 try/except). override = LTV `_limit_up_reached.discard(ticker)` + BFB `_partial_exit.pop(ticker, None)` + BFB·VCP `register_cooldown_after_exit(ticker)` + `asyncio.create_task(_refine_cooldown_business_days)`(달력일 근사 `days+2` → CTCA0903R `add_business_days` 로 N영업일 정정).
  - 불변식 = **"보유 중 flag 유지, 전량 매도 시 clear"** — AST `G2-STRUCT-INVARIANT` 가 3번째 제거 site 를 막는다. 보유가 남는 매도는 훅을 부르지 않는다(「매도 체결 — 주문 축과 보유 축」 절).
  - 🔴 `_cooldown_until` 은 multi-day 상태 — 일일·prepare 리셋 금지(AST `G-191-NO-DAILY-RESET`).
- **트레일링 기준점 복구 단일 진실원 `_apply_high_since_buy_from_candles(pos, candles, today)`** — `buy_date < 영업일 < today` 일봉 high max 로 고점을 **올리기만** 하고 `update_high` 로 DB 에 남긴다(`[high_since_buy_recover]`). **전략별 복제 금지**(로그 접두만 `_HIGH_RECOVER_LABEL` ClassVar). 보조 파서 `_candle_trade_date`/`_candle_high` 는 KIS 원본 키(`stck_bsop_date`/`stck_hgpr`)와 DB 컬럼(`bas_dd`/`high_price`)을 **둘 다 받고**, `_candle_high` 는 `except Exception: return 0`. ⚠️ `recompute_high_since_buy` 는 base 승격 금지(전략별 fetch 소스·일수가 다르다, kojiro 는 `recompute_held_atr` 내장). 🔴 **on_tick 에 DB write 금지** — `risk.on_tick` 은 메모리만, 영속은 boot 훅(회귀 가드).
- **일봉 신선도 기준 `_resolve_expected_daily_head(as_of_date=None) -> date | None`** — `trading_calendar.previous_trading_day(as_of_date 또는 today_kst())`(지연 import · never-raise, 예외 → `None`) + `[prepare_expected_head] strategy=<id> expected_head=<YYYY-MM-DD|None>` INFO. 6전략(VB·LTV·donchian·BFB·VCP·kojiro) `prepare()` 가 gather **전에 1회** 불러 `get_recent_daily_normalized(..., expected_head=expected_head)` 로 넘긴다(휴장일을 모르면 `None` 을 명시해 넘긴다). 판정 계약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.
- 공통 헬퍼: `_calc_used_funds()` / `_fallback_one_share(current_price)` — 잔여 자금 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`
- **`_apply_budget_limit(qty, current_price, ticker=None)` — 7 전략 `calc_buy_quantity` 의 공통 return 관문**(② 명목 축 `Σ매수금액 ≤ total_investment`. ① 개수 축 `max_positions` 는 `is_max_positions` 가 `check_buy_signal` 에서).
  - **분기 순서가 계약이다** — `price ≤ 0 → 0` → (`qty ≤ 0` → `_fallback_one_share` 위임 / `qty > 0` → 잔여 클램프 `min(qty, 잔여//price)` + `[budget_clamp]`) → `_apply_lot_units_cap`(K축) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축) → `return`. 잔여 < price 면 0, 그 밖은 **부분 매수 허용**(Case D = `test_strategy_fallback_budget.py`). ρ축을 관측 앞에 두면 차단 랏의 ρ 관측이, K축 앞에 두면 K축 마커 3종(cycle242)이 사라진다.
  - 🔴 **관문 안에서 `await`/DB/HTTP 절대 금지** — `order_engine.execute_buy` 의 `calc_buy_quantity` ~ `pending_buys.add` 사이 `await` 0건이 원자성의 전제다(깨지면 두 코루틴이 같은 잔여로 각자 매수한다). 신규 헬퍼 전부에 적용(A-PURE · `G-242-2` · `G-242-10` · `G-245-2`). 반환 타입은 **`int`** — float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 보낸다(`G-245` 회귀).
  - 가드 `tests/unit/ast/test_budget_limit_ast.py` = A-ATOMIC + A-PURE + A-GATE(7전략 모든 return 이 관문 경유) + C-DEFAULT(`position_ratio × max_positions ≤ 1.0`). `[budget_clamp]` = `_emit_budget_clamp` DailyEmitCap 1회/(ticker,전략)/일, 날짜 키 **자기 리셋**(override 가 `super()` 를 안 부를 수 있다).
- **K축 — 랏당 최대 유닛 상한 `_apply_lot_units_cap`**: `sizing_mode == "turtle"` 전략의 **모든 랏**에 `min(final, compute_unit_qty(budget, atr, risk_pct, fraction=K))`(K = `max_lot_units`, 기본 2.0).
  - **ATR 소스** `_resolve_sizing_atr(ticker)` — 터틀 분기와 **같은** `_candidates[ticker]` 를 read-only 로. `_SIZING_ATR_KEYS = ("atr", "atr14")` 중 양수 값이 **둘 이상 서로 다르면 불채택**(`ambiguous_atr`). `_candidates` 를 생성·변경하지 않는다(`G-242-8`).
  - **fail-open** — `sizing_mode` 아님 / `ticker is None` = 조용히 통과. `no_candidates`·`no_atr`·`ambiguous_atr`·`no_risk_pct`·`no_budget`·`exception` = **현행 수량 유지 + `[fallback_cap_skipped]` WARNING**. 🔴 수량을 0 으로 만드는 fail-closed 금지 — 유령 키가 두 전략을 전 기간 체결 0건으로 만든 방향이다.
  - **마커 5종** — `[fallback_notional_capped]`(INFO, `path=fallback|sized`·`units_before`·`units_after`·`k`·`atr`) / `[fallback_cap_skipped]`(WARNING, `reason=` 6종 + `atr=`/`units=`) / `[fallback_cap_config]`(INFO 카나리아 1회/전략/일, `cap=on|off`·`k`·`atr_max`) / `[fallback_cap_clamped]`(WARNING, **키가 명시 존재**하는데 범위 밖일 때만) / `[oversized_fallback]`(ρ축 서식 + 꼬리 ` units=`). 전부 `_lot_cap_logged: DailyEmitCap[str]` 복합 키(`cap|t` / `skip|t|r` / `cfg` / `clamp`) + 날짜 키 자기 리셋 + **peek→로그→mark**. **행위는 cap 밖**.
  - **K 취급** — `_read_max_lot_units` 가 `[1.0, 20.0]` 클램프(비수치·bool·비유한·<MIN → 2.0 / >MAX → 20.0). `_MAX_LOT_UNITS_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 4 터틀 전략 `DEFAULT_PARAMS` 리터럴과 동치(`G-242-6`). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(`G-242-1`). `_MiniStrategy` 류 더블 때문에 **모듈 상수 기본값이 필수**다.
- **ρ축 — 랏 명목 상한 `_apply_ratio_notional_cap`**: `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // price` · `final = min(final, cap_qty)`(K_ρ = `max_lot_ratio_mult`, 기본 2.5). `final × price > cutoff` 일 때만 차단(경계 포함 통과).
  - **적용 범위 = 관문을 지나는 모든 랏**(cycle254). `_lot_units_cap_governs`(= `sizing_mode == "turtle"` ∧ `ticker is not None` ∧ `risk_pct > 0` ∧ 예산 > 0 ∧ ATR 해석 성공)는 K축 심사 여부만 판정하고, 조기탈출은 **그 판정 자체의 실패(`probe_error`)뿐**이다. 스코프를 `via_fallback`·`final == 1` 로 좁히지 않는다(F-5b/F-5c). 항등식 `notional ≤ K_ρ × int(예산 × position_ratio)` 때문에 사이즈드·낙하 랏은 무접촉이고(`compute_unit_qty_guarded` notional 상한), 실효는 **1주 폴백 랏(`price > 예산 × position_ratio`)뿐**이다.
  - **fail-open** — 키 부재 = **캡 OFF**(K축과 **반대** — 매수를 막는 통제라 fail-closed 는 유령 키 재현 경로다). `k_axis_probe_error`·`no_ratio`·`no_budget`·`no_cap`·`exception` = **현행 수량 유지 + `[ratio_cap_skipped]` WARNING**. 어떤 결측·예외도 수량을 0 으로 만들지 않는다.
  - **마커 4종** — `[ratio_notional_blocked]`(INFO, `path=fallback|sized`·`price`·`cap`·`cutoff`·`k`·`ratio`·`req_qty`·`capped_qty`·`budget`·`pos_ratio`) / `[ratio_cap_skipped]`(WARNING, `reason` 5종) / `[ratio_cap_config]`(INFO 카나리아, **`cutoff_price` 필수**) / `[ratio_cap_clamped]`(WARNING). K축과 **별개 인스턴스** `_ratio_cap_logged: DailyEmitCap[str]`(`blk|t` / `skip|t|r` / `cfg|cap상태|k|cutoff` / `clamp|raw`) + 자기 리셋 + peek→로그→mark + 예외 흡수, **행위는 cap 밖**. `[ratio_cap_config]`/`[ratio_cap_clamped]` 는 **값-민감 키**라 **"1회/(전략, 값 조합)/일"**(롤백 PUT 확인 채널). 라벨 `off|on`.
  - **`[oversized_fallback]` 은 "사려 했던 랏" 을 잰다**(ρ캡 **앞** 발화, 서식 byte 불변 `G-245-10` — K>1 이면 비제로가 정상). 자기검증 **R7** = `ratio` > 그날 `[ratio_cap_config] k=`(리터럴 2.50 금지) 인데 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]`·`[ratio_cap_skipped]` 가 없고 `cap=on` 이면 **캡 우회 = 결함**. 터틀 행도 예외 없음(사이즈드 랏은 항등식으로 `ratio ≤ k`, 1주 폴백만 `ratio > k` — 그때 두 마커 중 하나가 반드시 동반).
  - **원인 판독** — 캡→0 은 `execute_buy` 의 `quantity <= 0` 경로에서 `block_low_funds(+900s)` + 「매수 수량 0 → 900s cooldown … `원인: cap`」 WARNING 이 되고, 잔여 자금이 현재가 미만이면 `원인: funds` 다(cycle408-L3, `order_engine.py` 절). 꼬리는 `_normalize_message` 뒤에도 남아 21:30 `top_patterns` 에서 두 원인이 다른 패턴으로 갈린다. `cap` 안의 세부(K축·ρ축)는 같은 (전략, ticker, 일자)의 `[fallback_notional_capped]`·`[ratio_notional_blocked]` INFO(2일 보관)로 가른다. ⚠️ 2026-10-04 배포 전 로그의 수량-0 WARNING 에는 꼬리가 없다 — 그 구간은 같은 날 같은 종목의 INFO 마커 유무로만 가른다.
  - **K_ρ 취급** — `_read_max_lot_ratio_mult` 가 `[1.0, 20.0]` 클램프(비수치·bool·비유한·<MIN → 2.5 / >MAX → 20.0). **하한 1.0 = 정상 비중 랏 무접촉의 수학적 전제**. `_MAX_LOT_RATIO_MULT_DEFAULT/MIN/MAX` 가 정본이고 **7 전략 전부** `DEFAULT_PARAMS` 와 동치(`G-245-6`, glob 전수). `PARAM_RANGES`/`INT_PARAMS`(`G-245-1`)·AI 자문 자동 적용 경로 편입 금지.
- **시장 유닛 헬퍼 (cycle382 — 터틀 4전략 `kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout` 한정)** — 규칙·전략별 ATR 키·필터 자리·스탬프 = `strategies/CLAUDE.md` 「시장 유닛 — 터틀 4전략 (cycle382)」 절 · 판정 = 모듈 맵 `market_unit.py`. 관문 `_apply_budget_limit` 본문은 무관(소스 세그먼트 sha 불변, AST A12). 나머지 3전략은 부르지 않는다(AST A04).
  - **계산 = 4전략 `prepare()`** — `_resolve_prepare_as_of(as_of)` 바로 다음 줄, 어떤 조기 `return` 보다 앞에서 `await self._refresh_market_unit(as_of_date=, preview=)` 정확히 1회(AST A08). 결과는 `_market_unit_snaps: dict[date, Snapshot]` 에 **거래일별로**(오늘 · 다음 거래일, 과거 키 삭제 — 저녁 미리보기는 다음 거래일 칸만 쓴다). PV-1 상태(`_candidates`·`positions`·`_entry_atr`·`_position_setup`·`_position_atr`·`_breakout_high`)는 읽지도 쓰지도 않는다(AST A07). 같은 날짜의 `ok=True` 를 새 실패가 덮지 않는다(`kept=1`). 새 `ok=True` 는 항상 덮는다. 모드가 `off` 여도 계산한다. never-raise.
  - **읽는 쪽은 순수다**(`await`·DB·HTTP 0, AST A05). `_market_unit_view()` 가 매 호출 모드와 **오늘 칸**을 다시 읽는다(PUT 즉시 반영). 모드 오타 = `off` + `[market_unit_config]`. 오늘 칸이 없으면 m=1 + `[market_unit_unavailable] where=view reason=not_computed`.
  - **`calc_buy_quantity` 첫머리** — `_market_unit_sizing(price, ticker)` 는 `enforce` ∧ m<1 일 때만 값을 준다(`shadow` ∧ m<1 = `[market_unit] where=calc` + 집계만, `None` · m=1 날은 calc 줄 없음). 값이 오면 `lot_after <= 0` → `return 0`, 아니면 `_apply_budget_limit(lots.design_after, …)` — 축소일에는 관문 폴백 분기에 닿지 않는다.
  - **설계 랏 `_market_unit_lots(price, ticker, m)`** — `budget = int(total_investment)` 와 잔여(`budget − _calc_used_funds()`)는 **줄이지 않는다**. 터틀 = `compute_unit_qty_guarded(int(budget × m), atr, price, risk_pct, remaining_budget=잔여, min_vol_pct=, position_ratio=)`. 명목 상한도 `int(budget × m) × position_ratio`. 🔴 `fraction=m` 으로 쓰지 않는다 — 명목 상한이 안 줄어 저ATR 종목 랏이 남는다(G-242-7). 비중 = `int(int(budget × m) × position_ratio) // price`. ATR 키 = ClassVar `_MARKET_UNIT_ATR_KEY`(그 전략 터틀 블록과 같은 키, AST A09). 경로는 매 호출 `sizing_mode == "turtle" and ticker is not None`. `lot_before`/`lot_after` = `min(설계 랏(1.0 | m), 잔여 // price)`, `lot_after` = `enforce` 때 실제 주문 수량(K축·ρ축 캡 무접촉).
  - **스킵 사유 `_market_unit_skip_reason`** = `zero_state`(m ≤ 0) → 살 수 있으면 `None` → `funds`(잔여 < 1주) → `rounds_to_zero` → `no_fallback`(m=1 이었으면 폴백·낙하로 샀을 종목). **신호 필터 `_market_unit_blocks_entry(ticker, price)`** = `enforce` ∧ m<1 ∧ 사유 ∉ {`None`, `funds`} 일 때만 `True`(호출부가 `Signal.NONE`, 부작용 0). 헬퍼 예외 = `[market_unit_error] where=calc|signal` WARNING + m=1.
  - **마커 6종**(로거 `src.engine.market_unit`) — INFO = `[market_unit]`(`where=calc|signal`, 1회/(ticker, where)/일) · `[market_unit_state]`((as_of, preview, state, m) 조합당 1회) · `[market_unit_daily]`(거래일마다 전략당 1줄). WARNING = `[market_unit_unavailable]` · `[market_unit_config]` · `[market_unit_error]`. cap = 인스턴스별 `KstDailyEmitCap` 3개(state·attempt·warn), `write_log` 별도 호출 없음. ⚠️ INFO 3종은 21:30 `top_patterns` 에 없고 INFO retention 2일 — 섀도 판독은 이틀 안에 `system_logs` 직접 조회. 일일 집계 `_market_unit_tally` 는 **더 뒤 날짜**가 올 때만 닫으며 `[market_unit_daily]` 를 낸다(`_market_unit_tally_roll` 의 `tally["date"] < day`). 메모리라 재시작하면 앞부분이 빠진다 — 정본은 `[market_unit]` 개별 줄.
- `Signal`: NONE / BUY / STOP_LOSS / NEXT_DAY_CLEAR / TRAILING_STOP / FORCE_CLEAR / STATUS_EXIT(관리종목·단기과열 보유 청산 — `status_exit_watch` 만 쓴다) / TIME_EXIT / TAKE_PROFIT / TREND_EXIT(cycle402 — 보유 기간 초과·목표가 익절·추세 종료. 어느 전략 분기가 어느 이름을 쓰는지 = `strategies/CLAUDE.md` 「청산 사유 이름」). 가산형 — 기존 값은 바꾸지 않는다. `signal.value` 는 로그(「`<신호> 매도 주문 접수`」·최종 실패 메시지)에만 쓰이고 `trade_history` 에는 사유 칸이 없다
- **`force_clear_signal(ticker)` + `resolve_force_clear_signal(strategy, ticker)` (cycle402)** — 15:20 `_force_clear_main_only` 매도 사유. 훅 기본 = `FORCE_CLEAR`, 15:20 에 조건부 조기 청산을 하는 전략만 덮어쓴다(VB·LTV 는 덮어쓰지 않는다). 해석기는 never-raise — `NONE`·`BUY`·`Signal` 아닌 값·예외 = `FORCE_CLEAR` + `[force_clear_signal_invalid]` WARNING. 사유 판정 실패가 15:20 청산을 막거나 뒤 전략 루프를 끊지 않는다
- **공통 매수 게이트 `_account_soft_gate_blocked(ticker)` — 순서 = 종목상태 차단 → `buy_paused` → 계좌 SOFT.** 7전략 `check_buy_signal` 이 전부 지난다(자리 = 폴·래치형 5전략 첫 문장 / momentum·VB 발사 직전 — `strategies/CLAUDE.md` 「안전 규칙」).
  - **첫 문장 = `if self._status_buy_blocked(ticker): return True`** (AST J25) — `status_exit_watch.buy_gate` 지연 import 순수 메모리 조회. `cand`(`_is_status_gate_candidate`)·막힐 때 `_clear_edge_baseline_on_block` 의 계약 = 위 「종목상태 청산·당일 매수 차단」 절
  - **둘째 문장 = `if self._buy_paused_blocked(ticker): return True`** (cycle384, AST `test_cycle384_ast_buy_paused.py` A02). 셋째가 계좌 SOFT `try` — 멈춘 전략의 `[account_gate_skip]` 이 「계좌 오픈리스크」로 오독되지 않게 멈춤이 먼저다. 둘 다 걸리면 `[status_block_buy_skip]` 만 남는다. 행위·값 규칙(신호 단계에서만 막는다 · `is True` 만 멈춘다 · 멈춰 둔 동안 키 삭제 금지) = `strategies/CLAUDE.md` 각주 ⑨.
  - **`_buy_paused_blocked(ticker)`** — 동기 · 순수 메모리 · never-raise(AST A03). **매 호출** `self.config.params.get(BUY_PAUSED_KEY, _BUY_PAUSED_ABSENT)` 를 읽고 캐시하지 않는다(A07 — PUT 이 같은 dict 를 `update` 한다). **`raw is True` 일 때만 멈춘다**. 읽기 예외 = `False` + DEBUG `[buy_paused_gate_failed]`. `ticker` 가 비어도 멈춘다(전략 단위).
  - **막을 때 지우는 것** — ① `_clear_edge_baseline_on_block(ticker)` ② `_clear_entry_latches_on_pause(ticker)`(`_PAUSE_ENTRY_LATCH_ATTRS = ("_breakout_first_seen", "_vol_latch")` 중 dict 속성에서 그 종목만 `pop`), 순서 ①→②(A10). 안 지우면 해제 첫 틱이 거짓 돌파거나 낡은 래치로 산다. 실패 = DEBUG `[buy_paused_latch_clear_failed]`.
  - **안 지우는 것** — `_bought_today` · `_position_setup` · `_entry_atr` · `_cooldown_until` · `_breakeven_latched` · VCP `_breakout_watch` · 평평한 `_prev_price`(BFB·VCP) · 시장 유닛 스냅샷. ⚠️ 해제 첫 틱 — donchian·kojiro 의 매수 창(09:05~09:30) 중간 해제 = 창 중간 재기동. BFB·VCP 는 멈추기 전 기준가가 돌파선 아래이고 멈춘 사이 돌파선을 넘었으면 그 교차를 해제 첫 틱이 **늦게** 본다(가짜 교차 아님 — WS 공백·밤사이 갭과 같은 기존 의미론).
  - **함께 멈추는 것(게이트 뒤)** — `[market_unit] where=signal|calc` · LLM 매수평가 행(`llm_buy_evaluations`) · kojiro 갭 관측 · VCP 돌파 관측 틱 · VB `[open_entry_hold_blocked]` · LTV `[open_entry_hold_*]`. **계속 도는 것** — `prepare()` · 퍼널 기록 · 구독 · `[market_unit_state]`·`[market_unit_daily]` · 스윙 폴 조회. 멈춘 donchian 후보는 `_bought_today` 에 안 들어가 09:05~09:30 매 분 REST 조회가 계속된다.
  - **마커 2종**(로거 `src.engine.strategy_base` · `_buy_paused_logged: KstDailyEmitCap[str]` · peek→로그→mark · 실패 = `trace_observer_failure` · **행위는 cap 밖** · `write_log` 병행 0, AST A13) — `[buy_paused_config] strategy= paused= valid= raw= note=`(1회/(전략, 값)/일, 키 `cfg|{paused}|{valid}`. `paused=1`·`valid=0` 은 **WARNING** — 무매매가 결함으로 오진되지 않게 21:30 상위 WARNING 에 올린다, `paused=0 valid=1` 은 INFO) · `[buy_paused_skip] strategy= ticker= cand=1 dropped= note=`(INFO, 1회/(종목, 전략)/일, 키 `skip|{ticker}`. 후보인 종목만 기록·mark. `dropped` = 지운 래치 또는 `-`. AST A15). ⚠️ 두 줄은 게이트가 그날 한 번은 닿아야 찍힌다 — 멈춤 여부의 정본은 `GET /api/strategies`·DB `strategy_config.params`.
  - 🔴 **운영 함정** — 기동 때 `_load_strategy_config` 가 실패한 채로 PUT 하면 메모리의 코드 기본값 전체가 `save_params` 로 DB 에 써진다. PUT 전에 GET 운영값(`sizing_mode`·`max_positions`·`stop_loss_rate`)이 DB 와 같은지 본다(실패 흔적 = 「전략 설정 초기 로드 실패」 WARNING). 키 삭제 함정(각주 ⑨) 원인 = `if key in strategy.config.params` 가 코드에 없는 키의 DB 값을 버린다.
  - 가드·회귀 = `tests/unit/ast/test_cycle384_ast_buy_paused.py`(A01~A15 · R06 · F01) · `tests/unit/engine/test_cycle384_buy_paused_gate.py` · `tests/unit/engine/strategies/test_cycle384_buy_paused_unpause.py` · `tests/contract/test_cycle384_buy_paused_params_route.py`(R01~R05) · 실 Postgres `tests/integration/test_cycle384_buy_paused_pg.py`(P01).
- **섀도 관문 `_shadow_buy_intercepted(ticker, current_price, open_price=None, *, level=None, board=None)` (cycle399)** — 7전략 각자의 `return Signal.BUY` 바로 앞 블록에 `if self._shadow_buy_intercepted(...): return Signal.NONE` 한 문장. 공통 게이트(`_account_soft_gate_blocked`)가 아니다 — 폴·래치형 5전략은 그 게이트가 첫 문장이라 신호 계산 전에 끝나 기록이 남지 않는다. 자리 = **마지막 거름 뒤 · 상태 변경 앞**(momentum 계좌 SOFT 뒤 · VB 09:00 진입 보류 뒤 · LTV 15:20 main 컷 뒤 · donchian·kojiro·BFB·VCP 시장 유닛 거름 뒤). BFB·VCP 는 BUY 가 `_evaluate_vol_gate` 안에서 나므로 관문도 거기 있고 시가를 받지 않는다(`open=-`). 행위 규칙 = `strategies/CLAUDE.md` 각주 ⑩.
  - 동기 · 순수 메모리 · never-raise. **매 호출** `self.config.params.get(SHADOW_MODE_KEY, _SHADOW_MODE_ABSENT)` — `raw is True` 일 때만 True(섀도). 읽기 예외 = False + DEBUG `[shadow_mode_gate_failed]`. 켜지면 몇 번 닿아도 True 를 돌려준다(그날 같은 종목 재평가도 NONE).
  - **바꾸지 않는 것** — 주문 · 예산 · `pending_buys` · `buy_signals` · `_bought_today` · 진입 스탬프(`_breakout_high`·`_position_setup`·`_position_atr`·`_position_sectors`) · 래치(`_vol_latch` 소비 포함) · `_scan_stats["vol_gate_pass"]` · `signal_count_today` · 수량 계산. 가상 수량은 계산하지 않는다(예산 0 + 사이징 마커 오귀인).
  - **`StrategyBase.shadow_mode_on(strategy)`**(정적) — 같은 키를 `is True` 로만 읽는 판정. `strategy_registry.update_weights` 가 쓴다(아래 절). 판정 실패 = False.
  - **마커 2종**(로거 `src.engine.strategy_base` · `_shadow_logged: KstDailyEmitCap[str]` · peek→로그→mark · 실패 = `trace_observer_failure` · 행위는 cap 밖 · `write_log` 0) — `[shadow_mode_config] strategy= shadow= valid= raw= note=`(**WARNING** 만 — 섀도 켜짐 또는 모양 오류, 1회/(전략, 값)/일, 키 `cfg|{shadow}|{valid}`. 꺼짐은 남기지 않는다. 그날 BUY 가 관문에 닿아야 찍힌다 — 섀도 여부의 정본은 `GET /api/strategies`·DB `strategy_config.params`) · `[shadow_buy] strategy= ticker= price= open= level= board= atr= m= mu_state= note=`(INFO, 1회/(종목, 전략)/일, 키 `buy|{ticker}`. `level` = 돌파선/목표가, `atr` = `_candidates[t]` 의 `_MARKET_UNIT_ATR_KEY`·`atr`·`atr14` 첫 값, `m`·`mu_state` = `_market_unit_view()`).
  - 가드·회귀 = `tests/unit/ast/test_cycle399_ast_shadow_mode.py`(S01~S13 — S01 「모든 `return Signal.BUY` 앞 같은 블록에 섀도 관문, 사이에 return/raise 0」 전략 명부 전수) · `tests/unit/engine/test_cycle399_shadow_mode_gate.py` · `tests/unit/engine/test_cycle399_shadow_weights.py` · `tests/contract/test_cycle399_shadow_mode_route.py`.
- `Position`: ticker, buy_price, quantity, order_no, strategy_id, buy_date, is_next_day(프로퍼티)
- `Position.is_next_day`: `buy_date < today AND strategy_id not in _MULTIDAY_STRATEGIES`(**리터럴 정본 = `{donchian_swing, vcp_breakout, kojiro}`**, `strategy_base.py` frozenset 리터럴이 유일 진실원). 확장은 frozenset 멤버만 추가하고 `Position` 시그니처는 바꾸지 않는다. 🔴 전략 모듈이 import 시점에 자기를 추가하는 방식 금지(import 순서 의존).
- `StrategyState`: positions, pending_buys, **pending_buy_amounts**(ticker→가격×수량, 1주 폴백 잔여 자금 계산), total_investment, daily_realized_pnl, cached_buyable_qty/at, buy_blocked_until, low_funds_tickers, **signal_count_today / order_attempt_today / fill_count_today** + 헬퍼 (`is_buy_blocked / block_buy / unblock_buy / is_buyable_cache_fresh / is_low_funds_blocked / block_low_funds / clear_low_funds`)
- 일일 퍼널 카운터는 `_reset_daily_state()` 0 초기화 → `metrics.strategy_funnel` 노출
- `pending_buy_amounts` 는 OrderEngine `execute_buy` 시장가/지정가 폴백에서 `pending_buys.add(ticker)` 옆 동기 등록, `pending_buys.discard` 옆에서 정리
- **funnel 단계 캡처**(관찰성 전용 — 메모리 `_funnel_steps` + DB `strategy_funnel_snapshots` + UI): `_record_funnel_step(step_no, step_name, survived, excluded=None, *, step_conditions=None)` + `_record_funnel_pipeline_step(FunnelStage, ...)`. survived/excluded cap 200/20(`survived_count` 는 cap *전* 값), 같은 `step_no` 는 **교체**. `_reset_funnel_steps(stages)` 는 모든 `FunnelStage` 를 count=0 으로 pre-populate 한다(`stages=None` = 빈 리스트). 5 전략 prepare()+retry 가 STAGES 상수를 넘긴다(donchian/BFB/VCP=`FUNNEL_STAGES` / VB=`VB_FUNNEL_STAGES` / LTV=`LTV_FUNNEL_STAGES`). 🔴 **`check_exit_signal`/`check_buy_signal` funnel hook 0건**(SAFETY 가드). momentum 은 영구 제외.

## strategy_registry.py

- `allocate_funds(total_asset)` / `update_weights(weights)` — **단위는 비율 `0.0~1.0`**(`get_strategies_status` 의 `weight` 도 같다). `allocate_funds` 는 `enabled()` 전략만 `weight / Σweight` **상대 정규화** 후 `int()` 절삭(Σ≠1 이어도 전액 배분 — 오염 탐지는 라우트 Σ 가드와 부팅 `[weight_config_anomaly]`). `update_weights` 는 값을 그대로 대입하고 `config.enabled = weight > 0 or (was_enabled and StrategyBase.shadow_mode_on(s))` 로 정한다 — 비중 0 = 비활성화, **단 섀도 전략(`shadow_mode is True`)은 켜져 있으면 켜짐을 유지한다**(cycle399, 8영역 한 줄 · AST S09). 꺼져 있던 섀도 전략을 켜지는 않는다. `allocate_funds` 에서 비중 0 섀도 전략의 예산은 0 이고 다른 전략 예산은 그대로다
- `is_ticker_held_by_any` / `is_ticker_sold_today_by_any`
- **`is_ticker_blocked_for_buy(ticker)`** — 보유 OR 주문중 OR 당일매도 통합 가드. RiskManager·OrderEngine 매수 입구
- `get_strategies_status()` — 프론트 노출

## risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호. 꺼진 전략의 보유는 이 순회에 없다(금기 = 루트 `CLAUDE.md` 「핵심 안전 규칙」).

- **`_selling` 가드**: 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 을 검사한다 — 매도 발사 후 체결통보 전까지 평가·로그 폭주를 막는다. 7 전략 공통.
- **NXT 프리장 청산 평가 보류 게이트**: `_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})` **밖**의 전략은 프리장 단독 구간에 **청산 평가 + `high_since_buy` 갱신을 보류**한다(프리장 시초가 왜곡의 허깨비 손절·앵커 오염 차단).
  - **판정 = `by_active` OR `by_clock`** — `by_active`(`PRE_NXT ∈ session_tracker.active AND MAIN ∉ active`, 매수 PR-F 와 같은 membership) 또는 `by_clock`(`session.boards_at(_now_kst().time())` 가 PRE_NXT 단독). `active` 는 30초 주기 stale 캐시라 단독이면 08:00:00~29 가 fail-open 이다. 폴백은 같은 `_BOARD_SCHEDULE` 를 fresh 로 읽는다 — 08:00/09:00 리터럴 신설 금지, `_KST` 명시. 09:00 정각은 stale `active`={PRE} 동안(≤30초) 보류를 유지한다.
  - 🔴 **평가 보류이지 주문 보류가 아니다** — 주문만 보류하면 허깨비 신호가 09:00 실매도가 된다. 09:00 MAIN 진입 시 자동 재개.
  - 두 소스가 갈리면 `[pre_market_exit_gate_divergence] reason=clock_fallback|active_stale_hold` 1회/(전략,사유)/일. `[pre_market_exit_deferred]` 는 1회/전략/일(D+1 판독 = 첫 타임스탬프 08:00:0x + 같은 시각 `clock_fallback`). 결정성 = 루트 `tests/conftest.py` autouse `_pin_pre_market_clock`(옵트아웃 `real_pre_market_clock`).
  - 🔴 `tradable_boards` 로 게이팅 금지(AST 가드). fail-open 은 **두 소스 모두** 판정 불가일 때만. 이 게이트가 "청산은 항상 평가" 의 **유일한 명시 예외**다. 회귀 `test_risk_pre_market_exit_gate.py` + `test_cycle238_pre_market_clock_gate.py`

매수 신호 평가 *전* 가드 (순서):
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)`. 🔴 `tradable_boards` 는 **매수 진입 전용** — 청산류는 보드 가드 없이 항상 작동하고 `check_exit_signal` 분기는 이 가드 *전* 진입한다.
- **레짐은 매수를 차단하지 않는다(관찰 전용)** — `risk.on_tick`·swing 폴에 레짐 게이트가 없다(`execute_buy` 의 `soft_multiplier` 는 vestigial). 🔴 복원하지 마라(회귀 `test_regime_observation_honesty.py`). 표시 전용 API = 「market_regime.py」 절. 시장 유닛(cycle382)은 레짐 게이트가 아니라 전략 사이징이다.
- **중복 가드**: `registry.is_ticker_blocked_for_buy()`
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. 후자는 `[risk_silent_skip] ticker= strategy= reason=price_gt_total_investment price= total=` INFO 1회/(ticker,전략)/일(`_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]`). `scheduler._reset_daily_state` → `RiskManager.reset_daily_state()` 위임 + AttributeError 후방호환 가드.
- **가격 필터(scanner 단계, 매수 진입 전용)** `_apply_price_filter` — `scanner.subscribe_filtered_stocks` 안의 단일 hook. 임계 = `system_config` `price_filter_min`/`price_filter_max`(기본 비활성), 기준가 = `stock_master.raw.prdy_clpr` 단독, 미확보는 graceful 통과(구독 *전*이라 `current_price` 가 없다). KIS `inquire-price` pre-fetch 는 쓰지 않는다 — Rate Limit·hot path 부담.
  - 🔴 **보유·익일청산 3중 보호** = 공통 헬퍼 `_collect_protected_tickers_for_scanner()`(`registry.all().positions` ∪ `_pending_next_day_clear`) + `_apply_price_filter` 최상단 early-return(`if ticker in protected_tickers: survived.append(ticker); continue`) + AST `protected_tickers=` keyword 의무 가드.
  - 60s TTL 캐시(`time.monotonic`) + `invalidate_price_filter_cache_scanner()`. **unsubscribe 발화 0건** — 다음 `_scan_loop` 5분 delta 에 맡긴다(KIS LMS chain 차단).
  - 관측 = `[price_filter_scanner_skip] ticker=… prdy_clpr=… reason=below_min|above_max min=… max=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_price_filter_scanner_daily_summary()` → `[price_filter_scanner_daily_summary] min=… max=… skip_count=N`(카운터 `_price_filter_scanner_skip_count: dict[str, int]`, `_reset_daily_state()` 동행 리셋). 🔴 그 호출은 **try/except 로 감싸지 않는다**(결함이 조용히 먹힌다). funnel `step_no=98`. UI `PriceFilterCard.tsx`.
  - 🔴 `risk.on_tick` 에 가격 필터를 두지 않는다(AST G-1 — 구독 대상 결정이지 매매 신호 판단이 아니다).
- **거래대금 필터(scanner 단계, 매수 진입 전용)** `_apply_trade_amount_filter` — 임계 `system_config.trade_amount_filter_min`(기본 0 = 비활성, UI 0~100억 step 1억 + 권장 마커 1억/5억/10억), 조회 = `_get_trade_amount_filter_for_scanner`(60s TTL).
  - 소스(`_get_acml_tr_pbmn`) = `scanner.ticker_market_info["trade_amount_raw"]`(원 단위, **KIS 호출 추가 0건**) → `stock_master.raw.acml_tr_pbmn` → 🔴 **둘 다 miss 이거나 0 이면 graceful 통과**(09:00 직후 누적 0 으로 후보를 막으면 매매가 멈춘다). `trade_amount`(억 단위 round) 키는 UI·API 호환으로 보존.
  - 순서 = `_apply_price_filter` → `_apply_trade_amount_filter`, `subscribe_filtered_stocks` 4 호출 경로(tickers + extra_tickers + breakout/momentum for loop + swing) 전부. 보호 종목 = `_collect_protected_tickers_for_scanner()` 재사용 + **별도** 60s TTL 캐시 + `invalidate_trade_amount_filter_cache_scanner()`.
  - 관측 = `[trade_amount_filter_scanner_skip] ticker=… acml_tr_pbmn=… reason=below_min min=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_trade_amount_filter_scanner_daily_summary()` → `[trade_amount_filter_scanner_daily_summary] block_count=N`(**try/except 로 감싸지 않는다**) + `_reset_daily_state()` 동행 `_scanner_mod.reset_trade_amount_filter_daily_state()`. funnel `step_no=97`. 모듈 전역 = `_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` / `_trade_amount_filter_scanner_skip_count_today: dict[str, int]`. UI `TradeAmountFilterCard.tsx`.
- BUY 신호 발생 시 `state.signal_count_today += 1`

## market_regime.py

우리 `macro` 컨테이너(`GET /api/macro/macro-cycle`) 기반 시장 레짐 + cash_usage_ratio 자동 조정. **관찰 전용 — 매수를 차단하지 않는다.** `get_buy_block_state`/`buy_blocked` 는 대시보드·AI자문 payload **표시 전용**이고 `to_advisor_dict()`·`GET /api/market-regime/current` 는 `buy_blocked=False` 를 낸다(`block_reason` 은 관찰용). 레짐 대응은 `cash_usage_ratio`(`auto_regime_adjust`)뿐이다.

- `MarketRegime` dataclass: regime / regime_desc / cycle_phase / vix / fear_greed_score / buffett_ratio / cash_min / raw
- `MarketRegime.empty()` — 외부 fetch 실패 graceful (`is_buy_allowed=True`)
- `MarketRegime.from_macro_cycle(macro)` — `/api/macro/macro-cycle` 응답 파싱. 🔴 `buffett_ratio` 는 `regime.buffett_ratio` 에서 읽는다(`params.pbr_max` 는 PBR 상한이라 전 계층 null 이 된다).
- `is_buy_allowed(strategy_id) -> bool` — 동기 회귀 가드 API (표시/자문 전용)
- **`get_buy_block_state() -> BuyBlockState` (async)** — 4 모드 분기, `BuyBlockState{mode, blocked, soft_multiplier, reasons, data_available}`. DB 조회 실패 시 HARD + 기본 임계 fallback. 소비처 = 대시보드 `/api/integrations/buy-block` 뿐. `buy_block_mode` 운영 DB 는 OFF 권장. 60s TTL 인스턴스 캐시(`_buy_block_cache` + `_buy_block_cache_expires_at`, `compare=False, repr=False`, `BUY_BLOCK_CACHE_TTL=60.0`, `time.monotonic()`) — DB fetch 폴백 분기는 캐시하지 않고, `invalidate_buy_block_cache()` 로 즉시 반영
- **지수ETF 고지로 스테이지 레짐 신호 (관찰 전용, `etf_regime_enabled=False` 다크런치)**:
  - `DEFENSIVE_STAGES=frozenset({3,4,5})` + `is_two_day_defensive(stages)`(최근 2 스테이지 모두 방어, None/len<2→False) + `EtfStageSignal` frozen dataclass + `get/set_current_etf_signal` 싱글톤.
  - `compute_etf_stage_signal(now=None)` async — KODEX200 069500 + 코스닥150 229200, `stock_master_daily.get_recent_daily` DESC→ASC 후 `kojiro_indicators.ema(5/20/40)`+`stage_of`. `etf_defensive` = 신선 지수 OR, 양쪽 stale → None. 신선도 = `_is_daily_row_stale`(`ETF_STALE_MAX_CALENDAR_DAYS=10`, never-raise). boot(`_refresh_market_regime_and_persist` 의 `set_current_regime` 직후)가 macro 성패와 무관하게 계산해 `[etf_regime]` 을 남긴다.
  - 🔴 **관찰만** — `get_buy_block_state`/blocked/reasons/soft_multiplier 무변경. ETF 전용 5/20/40 파라미터화 금지(정체성 상수), kojiro 무접촉. ETF 스테이지를 매수 가드로 통합하지 않는다(사용자 결정 2026-09-27) — 장세별 진입 축소는 `market_unit.py` 의 몫이다.
- **레짐 가드 silent inert 가시화 (관찰성 전용)** — `has_regime_data` property(`regime`/`vix`/`fear_greed_score` 중 하나라도 not None 또는 `bool(raw)` — `empty()` 는 False) + `BuyBlockState.data_available: bool=True` + `get_buy_block_state()` 5개 생성분(OFF/HARD/WARN/SOFT/unknown-fallback) 전부 `data_available=self.has_regime_data`. 🔴 blocked/soft_multiplier/reasons 로직·캐시는 **무변경 = fail-open 보존**("데이터 없음" 과 "임계 미발동" 을 구분하는 표시 전용 필드다). boot 경보 = `get_buy_block_mode()` 조회 후 `not has_regime_data and mode != "OFF"` 면 `[regime_guard_inert]` WARNING 1회/일.
- `to_advisor_dict()` 12 키 dict — AI 자문 user_payload
- `cash_usage_ratio_from_regime(cash_min)` — `clamp((100 - cash_min)/100, 0.0, 1.0)`
- `refresh_from_dkstock(timeout=None)` — `macro_client` → MarketRegime. 모든 예외 흡수 → empty + `reason=disabled|timeout|fetch_failed|exception` WARNING. 🔴 **`.env` 단독 veto 를 두지 않는다** — client 앞에 두면 DB 우선 판정이 도달 불가가 된다. 🔴 **함수명은 계약이다**(`scheduler.py`(승인 대상)가 이 이름으로 부른다). 부팅 경로는 `timeout` 을 `macro_api_boot_timeout_secs`(25s)로 줄여 넘긴다(바로 다음이 자금 배분).
- `persist_snapshot(regime, target_date)` — `market_regime_snapshots` 1행 INSERT
- `get_current_regime()` / `set_current_regime()` — 모듈 싱글톤
- 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 외부 호출 0건, 레짐 관찰 비활성
- **DB 우선 토글**: `macro_client._check_enabled_async` + `mcp_client._check_enabled_async` + `backtest_engine.is_enabled_async()` 가 `system_config.get_*` 먼저(DB True/False 채택, None / 예외 시 `settings.*` fallback). 매 호출 DB 조회 — Settings UI 토글 즉시 반영

`scheduler._boot()` 이 매크로 fetch + snapshot INSERT + `cash_usage_ratio` 자동 조정 통합.

## order_engine.py

매수/매도 실행 + 체결통보 처리 + DB positions 영속화.

- **NXT 프리 시장가 매도 사전 지정가 변환**(매수 PR-F 대칭): `execute_sell` 이 프리장 단독(`PRE_NXT ∈ active AND MAIN ∉`) ∧ `target_exchange ∈ (NXT, SOR)` ∧ 시장가면 `step_down(현재가, 5)` 지정가로 바꾼다(실효 대상 LTV, 현재가 미수신 = 무변환). INFO `[sell_market_preconvert_pre_nxt]`. ⚠️ 거부 분류는 `is_market_closed_rejection` **먼저**(프리마켓 msg1 이중 매칭 = 보류 낙하가 의도된 계약) — 반전 금지. 회귀 `test_order_engine_sell_pre_nxt_preconvert.py`

거부 분류 헬퍼(`is_market_closed_rejection` · `is_market_order_disallowed` · `is_insufficient_*` · `is_sell_qty_exceeded`)의 msg_cd·msg1 키워드 정본 = `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절. 여기에는 엔진이 하는 일만 적는다.

매수 (`execute_buy`):
- **NXT 프리마켓 시장가 사전 차단 (preconvert)**: `place_order` *직전*, `MarketBoard.PRE_NXT in session_tracker.active` AND `MAIN not in active` AND `buy_exchange in ("NXT", "SOR")` 면 `step_up(current_price, 5)` 지정가로 바꾼다. 변환 시 `state.pending_buy_amounts[ticker] = order_price × quantity` 동기 갱신, `record_price = order_price` 로 PENDING. INFO `[market_order_preconvert_pre_nxt]`
- 진입 시 `is_buy_blocked()` + `is_low_funds_blocked(ticker)` 차단
- 매수가능 캐시 `BUYABLE_CACHE_TTL=60s`
- `max_buy_quantity<=0` 또는 `KisApiError(insufficient_cash)` → `block_buy(now+BUY_BLOCK_DURATION=900s)`
- `calc_buy_quantity()<=0` → `block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN=900s)` + WARNING 「매수 수량 0 → 900s cooldown: … (투자금·현재가·전략, `원인: funds|cap|unknown`, `잔여: N`)」(cycle408-L3). 잔여 = `total_investment - _calc_used_funds()` 를 같은 분기에서 동기로 읽어 `잔여 < 현재가` 면 `funds`, 아니면 `cap`(K축·ρ축·오픈리스크 등 사이징 상한), 판정 예외면 `unknown`(잔여 -1). 쿨다운은 원인과 무관하게 같다 — 원인별 차등은 매수 행위 변경이라 사용자 결정 대상이다. 🔴 이 분기에 `await` 를 넣지 않는다(A-ATOMIC 구간 안)
- **`is_market_order_disallowed` 거부 → 지정가 5호가 폴백 1회** — `step_up(current_price, 5)` + `LIMIT`. 매핑 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, fallback_price)`. 폴백 거부 시 cooldown
- 락/cooldown 은 다음 잔고 sync(15분)에서 `unblock_buy()` + `clear_low_funds()` 로 일괄 해제한다. 🔴 세 상수를 바꿀 때도 이 일괄 해제를 보존한다

매도 (`execute_sell(..., limit_price=0)`):
- `_selling` set 중복 매도 차단
- `limit_price > 0` 이면 `LIMIT` + `exchange="NXT"` 강제, 0 이면 시장가 + `_strategy_exchange()` 라우팅. 호가단위 정렬은 호출자(`util.tick_size.step_down`) 책임
- `KisApiError(insufficient_quantity)` = 재시도 생략 + 즉시 break + 메모리/DB positions 정리
- **`is_market_closed_rejection(err)`**(장운영시간 외) → 재시도 중단 + `state.positions`·DB 보존 + `_selling` **discard** + 다음 거래 시각 자연 재트리거. 🔴 `_selling` 을 남기면 stale `_selling` 좀비 = `risk.py` on_tick 손절 마비이므로 **반드시 해제**한다(이후 차단은 진입 게이트 `SellRejectionTracker.is_blocked()` 담당).
  - **NXT 불가 사후 보강** `stock_master.upsert_one(ticker, nxt_tradable=False)` 은 `target_exchange ∈ ("NXT","SOR")` ∧ KST **08:00~08:50**(`market_state` N1.end)일 때만. 🔴 KRX 로 보낸 주문의 거부에는 **절대 쓰지 않는다** — 시계로는 어느 시장의 거부인지 못 가르고, 잘못된 낙인은 ≈24h 자기 강화 래치가 된다. 판단 불가를 fail-safe 로 쓰지 않는다. 마커 `[nxt_post_reinforce] ticker= exchange= div= now= wrote=1|0 reason=nxt_pre_window|exchange|window` — `wrote=0` 이 D+1 판독의 분모.
  - **진입 게이트 2단계 TTL**: KRX 메인(09:00~15:30) 거부 = **5분 TTL** / NXT 시간대 거부 = **다음 KST 09:00 TTL**(`SellRejectionTracker.register_market_closed(in_krx_main_hours=...)`). TTL 안이면 KIS 호출 없이 skip + INFO `[market_closed_blocked]` 1줄/ticker/일. `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 가 5 필드(`_alarm_last_emitted` 포함)를 비운다(`scheduler._reset_daily_state()` 의 위임 호출 보존). 호환 property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 을 그대로 노출한다(`is` 동일성).
  - **폭주 알람**: `_append_history` 단일 진입점에서 10분 윈도우 5건 초과 시 CRITICAL `system_logs` INSERT + 30분 per-ticker cooldown(`ALARM_WINDOW_SECONDS=600` / `ALARM_THRESHOLD=5` / `ALARM_COOLDOWN_SECONDS=1800`). fire-and-forget(`asyncio.create_task`).
- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회(`step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`) + 결과 무관 `SellRejectionTracker.register_market_order_disallowed(fallback_succeeded=...)` **30초 TTL**. NXT 시간대 폴백 실패(`is_nxt_session=True, fallback_succeeded=False`) = `RejectionResult.next_day_clear_required=True` → `_pending_next_day_clear_provider().add((ticker, strategy_id))` + `[next_day_clear_deferred]` WARNING. 폴백 실패 = `_selling.discard` + positions 보존. 🔴 매도는 cooldown 을 걸지 않는다(청산 의무). 지정가 매도(`limit_price>0`)는 폴백하지 않는다.
- **`is_insufficient_quantity(err)`**(보유 수량 부족) → 재시도 중단 + 메모리/DB positions 정리. `SellRejectionTracker.register_insufficient_quantity` 는 history 만 적재하고 **차단하지 않는다** + `[positions_reconciliation]` INFO + `get_balance()` 1회(실제 잔량 > 0 이면 재등록 권고 로그). 실패 graceful
- **`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조** — APBK0400 "수량 초과" 를 insufficient(통째 삭제)로 **흡수 금지**(부분 보유 내재 코드 — 257720 실사고). 재시도 루프에서 closed 다음·insufficient 앞에 `get_balance` 로 재대조한다: ① 오염(`held < eff`) = **held 로 보정**(잠긴 주식도 보유) + `save_position` + `continue`(3회 한도 안) ② 부분 잠김(`held ≥ eff`) = `fire = sellable − (held − eff)` ≥ 1 이면 그 수량만(`[sell_qty_partial_sellable]`, `pos.quantity` 무변경), 아니면 보류 ③ 전량 잠김(`sellable == 0 ∧ held > 0`) = 보류(`[sell_qty_locked]`) ④ 실보유 0 = insufficient 경로 ⑤ 재대조 실패 = 일반 재시도.
  - **보류** = 포지션 보존 + `_selling_locked_wait` 표식 + return. **`_selling` 은 의도적으로 유지**한다(열린 기주문 또는 미통보 체결 대기 — 명세 부록 R4 D1. market_closed 의 discard 와 다른 이유 = 그쪽엔 열린 주문이 없다). stale 은 `[selling_reconcile]` 180s 소관. `eff`·주문 목록(`_sell_orders_snapshot`)·크레딧·보류 마커 4종의 정본 = 「매도 체결 — 주문 축과 보유 축」 절.
  - ⚠️ sync 는 기보유 수량을 갱신하지 않아 DB 보정 실패 시 구값이 다음 보정·청산까지 남는다

체결통보 race 가드 (금기 = 루트 `CLAUDE.md` 「핵심 안전 규칙」):
- 주문번호 매핑(`_order_qty / _order_strategy / _order_ticker / _pending_buy_orders`)은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 와도 단일 COMPLETED row(매수·매도 양쪽 필수). 규칙 4개:
  - ① **PARTIAL 뒤 전량 체결** = 1차 UPDATE `match_partial=True`(PENDING∪PARTIAL + KST 당일 하한, **datetime 바인딩**)로 COMPLETED. 잔여취소 타이머는 `_pending_cancel_order_no[ticker] == order_no` 일 때만 cancel+pop(`[partial_cancel_timer_cleared]`). 🔴 CANCELLED 호출은 `match_partial` 을 opt-in 하지 않는다(PARTIAL→CANCELLED 뒤집힘 금지).
  - ② PENDING INSERT `await` 도중 체결통보가 먼저 완주해 migration 029 부분 UNIQUE 위반 → `_insert_pending_or_absorb_race(side="buy"|"sell")`(매수·매도 4 지점 공용)가 **`order_no in _completed_orders` 일 때만** 흡수·discard + `[buy_fill_during_insert]`/`[sell_fill_during_insert] ticker= order_no= strategy= path=market|fallback` INFO. 🔴 증거 없는 위반은 전파한다(무조건 삼키기·재시도 INSERT 금지). 회귀 `test_cycle271_execute_buy_fill_during_insert.py` · `test_cycle327_sell_fill_during_insert.py`
  - ③ `update_trade_status(*, order_no=None, match_partial=False)` — `order_no` 는 keyword-only opt-in(미전달 시 SQL byte 동일). 호출 6곳(C1 매수 COMPLETED · C2 매수 PARTIAL · C3 매도 COMPLETED · C4 매도 PARTIAL · C5 `_cancel_after_wait` 매수 CANCELLED · C6 `_cancel_and_reorder` 매도 CANCELLED)이 전부 `order_no` 를 넘긴다 — 없으면 같은 `(ticker, trade_type, strategy)` 의 다른 주문 행까지 덮는다(161580). `affected>1` = `src/db/trade_history.py` `[trade_status_multi_update]` WARNING(WHERE·인덱스 후퇴 회귀 감시자).
  - ④ 🔴 **`place_order` 가 성공한 뒤의 실패는 「발사 실패」가 아니다** — 매핑 등록 이후 구간은 축별 경계 래퍼(`_persist_buy_pending_after_send`·`_persist_sell_pending_after_send`)가 `except Exception` 으로 닫고 **재시도 루프로 돌아가지 않는다**(정본 = 「접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2」 절). 새면 주 경로는 **중복 매도**, 폴백은 **`risk.on_tick` 사망 = 그 틱 손절 평가 소멸**이다.
    - 매도 재시도 루프는 발사 직전 `strategy.state.positions.get(ticker)` 를 **재조회**해 포지션이 사라졌으면 `[sell_position_gone]` 후 중단한다(루프 밖 `pos` 는 옛 수량이다). 회귀 `test_cycle327_sell_fill_during_insert.py::test_sell_does_not_refire_on_generic_insert_error`
    - 래퍼 **앞부분에 `await` 를 넣지 않는다** — 최초 양보점 = `await insert_trade` 가 「매핑은 동기 영역」 금기의 전제다(`test_g328_2`). 매도 래퍼 값 4개(`record_price`/`quantity`/`path`/`order_no`) = `test_order_engine_sell_fallback.py` 시나리오 J 3건.

거래소 라우팅 (`exchange`):
- 모든 `place_order` / `cancel_order` 에 `_strategy_exchange(strategy_id)` 전달
- **NXT 거래가능 사전 차단**: `_probe_nxt_downgrade_base(strategy_id, ticker)` 가 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 + `[nxt_downgrade]`(캐시 miss·예외 = 전략 기본 exchange, 익일 청산 NXT 지정가 `limit_price>0` 은 제외). 로그는 ticker 별 **1회/일 cap**(`_nxt_downgrade_logged_today: set[str]`, `OrderEngine.reset_daily_state()` 동행 clear), **결정(`return "KRX"`)은 cap 밖**.
- **규칙 1 — 시각이 거래소를 정한다(cycle287).** `_probe_nxt_downgrade_base` 결과(`base`) **뒤**에 `_strategy_exchange_async`(반환 시점 1회) · `_apply_clock`(그 밖 4곳)이 순수 함수 `_route_exchange_by_clock(base, *, side, mode, now)` 로 감싼다. 판정은 `market_state.MARKET_TABLE` 만 읽는다(`order_engine.py` 안 시각 리터럴 0건).
  - clause 순서 = `base ∉ {"NXT","SOR"}` → 그대로 / `mode=="off"` → 그대로 / `mode=="sell_only" ∧ side=="buy"` → 그대로 / `session_tracker.active` 가 `PRE_NXT` 단독(PR-F 와 같은 출처, 08:50~09:00 NXT 휴장도 여기서 base 유지) → 그대로 / 그 시각 KRX 가 `_SENDABLE_DIVISIONS` 중 하나라도 받으면 `"KRX"` / 아니면 NXT 가 받으면 base 유지 / 둘 다 아니면 base 유지.
  - 예외는 전부 `probe_error` 로 base 유지(fail-safe). `active` 가 비었을 때만(첫 `tick()` 전) `session.boards_at(moment.time())` 로 재계산하는 폴백이 clause 4 를 지킨다 — 없으면 08:20~09:00 프리장 창이 KRX PRE_AUCTION 으로 샌다.
  - 적용 지점 = `_strategy_exchange_async` 반환 1 + `_apply_clock` 4(`limit_price>0` 분기·`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`), mode/dial 조회는 `_clock_params` 공유. 마커 `[order_channel] side= ticker= strategy= base= exchange= reason=`(`routed≠base` 일 때만, 단 `probe_error` 는 항상) + `[order_channel_config] strategy= mode= division=`(카나리아, 1회/(전략,mode,dial)/일).
- **규칙 2 — KRX 애프터마켓(16:00~20:00) 청산 호가(cycle287).** `execute_sell` 이 프리장 사전 변환 **뒤** · 재시도 루프 **앞**에서 `order_division==MARKET ∧ target_exchange=="KRX" ∧ settings.is_production ∧ market_state.get_market_state(now,"KRX").phase is AFTER_MARKET` 이면 params `after_market_exit_division`(화이트리스트 `{"44","41"}`, 기본·미지값 `"44"`)에 따라 `44`(최유리지정가, `ORD_UNPR=0`) 또는 `41`(지정가 `step_down(현재가,5)`, 현재가 미확보 시 변환 취소)로 바꾼다(VTS 무접촉). 재시도 폴백 게이트 = `order_division==primary_div ∧ (is_market_order_disallowed(e) ∨ primary_div≠MARKET)` — 애프터는 **분류에 의존하지 않는 구조적 폴백**(msg1 원문 미지), `fallback_div`(44→41, 41→41) 1회. `src/models/order.py::OrderDivision` = `KRX_AFTER_BEST="44"` · `KRX_AFTER_LIMIT="41"`. 🔴 **IOC/FOK(42/43/45/46)·최우선지정가(47)는 추가하지 않는다** — 잔량 자동취소·비크로스라 손절 수단으로 부적합하다.
  - 🔴 **44 는 시장가가 아니다**(반대편 최우선호가 지정가 — 실질 최악 1틱). `ORD_UNPR=0` 인 이유 = 0 이 틀리면 즉시 거부되고 41 폴백이 받지만, 가격이 틀리면 미체결 잔존 = 손절 **무음** 실패다.
  - **봉인 3종**: ① `register_market_order_disallowed` 는 분류·성패 무관 **항상**(TTL 30초) — `cur_price<=0`·`market_closed` 분류 경로도 공용 헬퍼 `_register_after_exit_disallowed`/`_bump_after_exit_fails_and_maybe_giveup` 로(빠지면 무제동 재시도), `ttl_registered=` 는 등록 성공 여부. ② 종목당 그 저녁 실패(주문 사이클 단위)가 `_AFTER_EXIT_GIVEUP_THRESHOLD=5` 면 `[after_exit_giveup]` CRITICAL + `register_market_closed(in_krx_main_hours=False)`(다음 09:00 TTL, 30초 TTL 뒤에 덮는다) + `_pending_next_day_clear`. ③ `_exit_capable_krx_window(now)` — `in_krx_main_hours` 의 뜻 = "그 시각 KRX 가 우리 청산 호가를 받는가"(`_EXIT_CAPABLE_KRX_PHASES = {REGULAR, CLOSE_AUCTION, AFTER_MARKET}`, `sell_rejection.py` 무접촉).
  - 손절 잔여 재주문(`_cancel_and_reorder`)도 같은 창에서 시장가(price=0) 대신 창 호가쌍을 쓴다(정규장·프리장 byte 동일). ETP 관측 `_observe_after_exit_etp` → `[after_etp_exit_observe]`(`stock_master.raw.scty_grp_id_cd ∈ {EF,EN,FE}`)는 애프터 1차 거부 **직후에만** fire-and-forget 이다(행위 분기 없음).
  - 취소 `ORD_DVSN` 은 `"00"` 하드코딩 유지(국내주식 스펙에 원주문 호가유형 승계 규약이 없다).
  - 🔴 **취소는 원주문의 거래소로 나간다** — `place_order` 응답 직후 동기 영역에서 `self._order_exchange[order_no]` 를 등록하고(`_order_qty` 와 같은 자리·정리 주기), 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 그 값을 우선, 없을 때만 라우터로 fail-open 한다(`PARTIAL_FILL_WAIT`(30초) 동안 경계를 넘긴 취소가 다른 거래소로 가지 않게). 관측 `[after_cancel_result] ticker= order_no= ord_dvsn=00 exchange= result=ok|error err=`.
  - 마커 `[after_exit_division] ticker= div= unpr= cur= exchange= dial=` / `[after_exit_rejected] ticker= div= msg_cd= classified= ttl_registered= msg1=` / `[after_exit_giveup] ticker= fails= next_day_clear=1`(CRITICAL). 회귀 `test_cycle287_exchange_routing.py` · `test_cycle287_krx_after_exit.py`
- **장중 킬스위치 2키** `order_exchange_clock_mode`(기본 `enforce`) · `after_market_exit_division`(기본 `"44"`) — 7 전략 전부 `DEFAULT_PARAMS` + `param_catalog`(`risk="identity"` 2단계 확인)에 있어 `PUT /api/strategies/{id}/params` 가 즉시 통한다(미지 키 판정 `key not in current_params or spec is None` 이라 둘 다 필요). `PARAM_RANGES`/`INT_PARAMS` 편입 금지 — AI 자문이 청산 수단 스위치를 뒤집으면 안 된다.
  - ⚠️ **두 키는 전략별이다**(전역 스위치 없음) — 사고 중 보유 전략이 여럿이면 각각 PUT 한다. 사고 중 조작 순서(거부/미체결/악체결 3분류 + 5단계) = `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절.
  - ⚠️ **두 키는 `exchange ∈ {"NXT","SOR"}` 일 때만 효력이 있다** — clause 1 이 mode 검사보다 **앞**이라 `"KRX"` 면 무동작이다(코드 기본값은 7전략 전부 `"KRX"`, 운영 DB `exchange` 가 `_CLOCK_ROUTED_BASES` 인 전략에서만 작동). `exchange` 를 KRX 로 옮기는 사이클은 두 키의 help 도 갱신한다.
  - ⚠️ **비상정지는 `off` 보다 `PUT {"exchange":"KRX"}` 가 안전하다** — `off` 는 라우팅 전체와 44/41 애프터 청산 변환까지 끄지만, `exchange=KRX` 는 clause 1 로 KRX 고정되면서 44/41 을 보존한다(부작용 = 프리장 주문도 KRX).
  - ⚠️ `_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT` 위 주석과 `param_validation.py` docstring 의 「99 스펙」(실제 = `len(param_catalog.SPEC_BY_KEY)`)은 낡았다 — 다음 8영역 승인 사이클 과제.

- 🔴 **규칙 3 — 15:30~16:00 은 완전 휴식이다(cycle295).** 라우터 **밖**의 순수·never-raise 술어 `_market_rest_now(now) -> (blocked, reason)` 를 **주문 발사점 3곳**(`execute_sell` 의 `target_exchange` 산출 직후·재시도 루프 앞 / `execute_buy` 의 중복매수 가드 직후·`get_buyable` 앞 = A-ATOMIC **밖** / `_cancel_and_reorder` 의 `sleep(30)` 뒤·`cancel_order` 앞)에만 건다. **시각 리터럴 0건**(`market_state.get_market_state(now, market=...)` 파생). 라우터 밖인 이유 = `nxt_tradable=False` 코호트는 `base="KRX"` 로 clause 1 에서 즉시 반환된다.
  - **판정** = 프리장(`session_tracker.active` 가 `PRE_NXT` 단독, clause 4 와 같은 출처) → `pre_nxt_keep` / KRX 가 `_SENDABLE_DIVISIONS` 중 하나라도 받으면 → `krx_sendable` / KRX·NXT 둘 다 세션 없음 → `no_session` / 그 밖 → **`market_rest`(컷)**. 판정 예외 = `probe_error` **fail-open**.
  - **`_cancel_and_reorder` 는 쌍으로 막는다** — 이것만 `cancel_order` → `place_order` 의 atomic replace 라, 절반만 막으면 걸린 손절을 빼고 아무것도 안 넣은 상태가 된다. 컷이면 **취소도 하지 않는다**.
    - 🔴 **그 잔량을 우리가 거두는 경로는 없다** — `cancel_remaining` 은 `src/` 안 호출자 0 이고 `pos.order_no`(**매수** 주문번호)를 취소한다. `risk.on_tick` 재평가도 걸린 주문을 취소하지 않는다.
    - 잔량의 운명은 거래소가 정한다(「session.py」 절) — KRX 잔량은 정규장 마감 후 자동 취소, NXT 잔량은 20:00 까지. 매도가 NXT/SOR 로 나가는 것은 규칙 1 이 base 를 유지할 때뿐이다(`pre_nxt_keep` · `order_exchange_clock_mode="off"` · `probe_error`).
  - **컷이 「하지 않는」 것 4** — 거부 등록 안 함(`SellRejectionTracker` 의 NXT 시간대 TTL = 다음 09:00 이 16:00~20:00 KRX 애프터 청산을 잠근다) · 익일청산 미전환(컷은 **최대 20분 유예**다) · 포지션 불변 · `_selling` **유지 금지**(stale `_selling` 좀비 = 손절 마비).
  - **마커 2종** — `[market_rest_blocked] side= ticker= strategy= base= reason=`(1회/(ticker,side)/일, **이 규칙이 잃는 것의 유일한 분모**) + `[market_rest_window] start= end= source=market_table`(1회/일 카나리아, 차단 0건인 날에도, `start`/`end` 는 표에서 역산). `KstDailyEmitCap` + never-raise, **행위는 cap 밖**.
  - 🔴 **신선도 기반 해제를 들이지 마라** — `risk.on_tick` 이 같은 콜스택에서 `scanner.ticker_last_tick` 을 쓰고 주문을 불러 틱 나이는 **항상 0.0초**다(컷이 100% 풀린다). KRX **K5**(15:30~16:00, `fixed_price ('06',)`)도 `H0STCNT0` 로 프레임을 보낸다 — 틱 도착 ≠ 우리 호가 접수.
  - ⚠️ **남은 한계** — `market_state` 표는 날짜 범위만 보는 고정 벽시계라 **특별 개장일(지연 개장, 수능일이 표준 사례)**에는 실제 정규장인 15:30~16:00 을 **30분 무음 차단**한다. 닫는 길은 신선도가 아니라 표에 특별일 입력을 넣는 것이다(별건 카드).
  - ⚠️ **면제 경로 = `POST /api/trading/manual-sell`** — `place_order` 를 직접 불러 게이트에 닿지 않는다(운영자 수동 조작은 막지 않는다). 그 구간엔 응답 message 경고 + 접수 로그 `[market_rest_manual_exempt]` — **D+1 에 그 구간 주문이 나오면 이 라우트를 먼저 본다.**
  - ⚠️ **판독 보조** — 프리장 예외는 `session_tracker.active`(30초 캐시) 우선, 비었을 때만 `boards_at(now.time())`. 재기동이 보드 경계를 넘어 캐시가 낡으면(`_session_loop` 이 도는 동안 staleness ≤30초) 컷이 풀리거나 08:00~08:19 프리장 주문이 잘릴 수 있다 — `[market_rest_window]` 만 있고 `[market_rest_blocked]` 0 인 날은 손절 신호 부재와 캐시 노후를 먼저 본다.
  - ⚠️ **컷에는 장중 다이얼이 없다** — `order_exchange_clock_mode` 에 **종속시키지 않는다**(종속시키면 44/41 애프터 청산 변환도 같이 꺼진다). 롤백은 **1커밋 revert + 장외 배포**뿐이다.
  - ⚠️ **15:20 강제청산과의 경계** — 15:20 에 시작한 `_force_clear_main_only` 순차 루프가 15:30 을 넘기면 남은 종목은 컷되어 익일청산으로 밀린다(`[market_rest_blocked] side=sell` 이 남는다).

- **규칙 4 — NXT 프리장 매수는 GTP(`27`)로 낸다(cycle291).**
  - **매수만, `27` 만.** 매수 PR-F 변환 블록(`order_price=step_up(현재가,5)` 확정 **뒤**) 안 게이트 4중 = `settings.is_production` ∧ `buy_exchange=="NXT"` ∧ `"27" in get_market_state(now, market="NXT").order_divisions` ∧ 프리장 판정. 시행일·08:50 경계는 `market_state.py` 표에서만 읽는다(리터럴 신규 0건). 하나라도 실패·예외면 `00`(LIMIT)이 나간다(fail-safe). `ORD_UNPR` 은 `00` 과 같다 — 바뀌는 것은 08:50 이후 미체결의 **수명**뿐이다.
  - 🔴 **매도는 무접촉이다**(`execute_sell` 프리장 `step_down` 변환 그대로) — GTP 매도는 08:50 자동취소가 `_selling` 을 ≈09:45 까지 잠가 손절 재평가를 막는다(루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉).
  - **화이트리스트 제거** — `place_kwargs["order_division"]` 게이트와 `record_price` 게이트가 `!= OrderDivision.MARKET` 이다. 🔴 열거(`== OrderDivision.LIMIT`)로 되돌리면 새 호가유형이 조용히 시장가로 떨어지거나 기록 가격이 샌다.
  - **GTP 거부 폴백** — `27` 거부는 `_MARKET_ORDER_DISALLOWED_KEYWORDS`/`_MARKET_CLOSED_KEYWORDS` 에 안 걸려 미분류 `raise` 면 `risk.on_tick` 이 죽는다. 그래서 게이트를 **"우리가 27을 보냈다"**(`order_division is OrderDivision.NXT_GTP_LIMIT`, `NXT_GTP_LIMIT="27"`)에 걸어 같은 가격 `00` 1회로 재주문한다(`[pre_nxt_gtp_fallback] ticker= reason=rejected msg_cd= msg1=`).
  - **마커** `[market_order_preconvert_pre_nxt]` = 기존 4필드(`ticker/exchange/current_price/converted_to_limit_price`) byte 보존 + 꼬리 `div= gtp=0|1 reason=ok|vts|exchange|not_effective|probe_error`. **`[pre_nxt_division_config] division=27 effective= production= exchange_gate=`** = 1회/일 카나리아(그날 첫 매수 후보가 이 블록에 닿아야 발화 — 무코드 대안 = `GET /api/market-state?market=NXT`).
  - **알려진 비용 — GTP 08:50 자동취소 잔존 상태.** 취소 통보(KIS 기록 `GTP매수자동취소*`)는 오지만 `handler.py::_handle_execution` 은 `CNTG_YN != "2"` 프레임을 `[order_notice]` 로 **기록만** 한다(`src/realtime/CLAUDE.md` 「접수 전문 기록」). 그래서 `pending_buys`/`pending_buy_amounts`/`_pending_buy_orders` 와 `trade_history` PENDING 행이 **그날 첫 잔고 sync(≈09:45)까지** 남아 재진입·예산·슬롯을 막고, sync 의 `buying_reconcile`(모듈 맵)이 KIS 행(`tot_ccld_qty==0 ∧ rmn_qty==0`)으로 풀고 CANCELLED 로 적는다. `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 21:30 `reset_daily_state()` 까지 남긴다(늦은 체결통보 안전망). 기회비용이고 자본 위험은 아니다.
    - 통보로 즉시 정리하려면 `handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**)를 바꿔야 한다. 🔴 접수·취소 전문 판별 필드를 확정하지 않고 분기하지 않는다 — **살아 있는 주문의 상태를 지운다**. 진행 = `_workspace/00_URGENT_WORKLIST.md` ⑨B. 원문 payload·개인정보 칸 로깅 금지 = `src/realtime/CLAUDE.md` 「접수 전문 기록」.
  - **취소 축 Stage A** — `OrderEngine._order_division: dict[str, str]`(order_no → 실제 `ORD_DVSN`, `_order_exchange` 와 대칭: 등록 4곳·pop 2곳·`reset_daily_state()` clear) + `api/order.py::cancel_order(..., order_division: str | None = None)`(falsy → `"00"`). 🔴 **호출자 3곳(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)은 전달하지 않는다** — 켜면 정규장 부분체결 취소가 `00`→`01` 이 된다. `[after_cancel_result]` 의 `orig_dvsn=`(부재 시 `-`)·`dvsn_src=map|absent` 가 층화 실측 근거다. Stage B 검토 조건 = 비-`{00,01}` `orig_dvsn` 행만 `result=error` 일 때(매매 행위 변경 — 별도 승인).
  - 회귀 가드 = `tests/unit/engine/test_cycle291_pre_nxt_gtp.py` · `tests/unit/ast/test_cycle291_ast_scope.py`(금지 파일 무접촉 · `scheduler.py` 라인 상한 · `_SENDABLE_DIVISIONS` 확장 무영향 · 취소 호출 3곳 `order_division` 미전달 · 매핑이 `place_kwargs` 파생값을 읽는지).

체결 후처리:
- 매수 → DB `positions` 저장 + `cached_buyable_at=0`
- 매도 → 보유가 남으면 차감 수량만 `positions` 에 저장(「매도 체결 — 주문 축과 보유 축」 절). 보유 0 이면 positions 삭제 + `sold_today` + (주문 종료 분기에서) **WS 구독 정리 hook** `_unsubscribe_if_no_other_strategy(ticker)` — (a) `registry.is_ticker_held_by_any(ticker)=False` (b) `_pending_next_day_clear` 부재 (c) 모든 전략 `get_scanned_tickers()` 부재면 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)`. `_pending_next_day_clear_provider` 는 scheduler 가 `OrderEngine.__init__` 직후 주입(lambda)
- 체결통보 처리 실패 안전장치: ticker 매핑 실패 → `pending_buys` 제거, strategy 미발견 → `_selling` 해제

퍼널 카운터: `place_order` 직전 `order_attempt_today += 1`, `_handle_buy_fill` 첫 체결 시 `fill_count_today += 1`

## session.py

`MarketBoard` enum 5종 중 **실제로 쓰는 것은 3종**이다(`KRX_OPEN`·`KRX_AFTER` 는 비활성, enum 값은 DB 파라미터 호환으로 남김 — `session.py::MarketBoard` docstring 이 정본). `_BOARD_SCHEDULE` 실제 구간 = `pre_nxt` **08:00~08:59:59** / `main` **09:00~15:39:59**(15:20~15:30 buy_stop + 15:30~15:40 갭 마진 포함) / `post_nxt` **15:40~19:59:59**. `krx_open`(08:30~09:00)·`krx_after`(15:30~18:00)는 **표에 없다**.

- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset (H0NXMKO0 미수신 시 fallback)
- `SessionTracker.tick()`: `_session_loop` (scheduler 30s 주기) 에서 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅
- `on_h0nxmko0(...)`: NXT 장운영정보 수신 (KIS 명세 미확정 → 기록만)

### 시장 시간표 — 정본은 `market_state.MARKET_TABLE`

`_BOARD_SCHEDULE` 은 우리 **보드** 구간이고, 거래소 세션·호가유형의 정본은 `market_state.MARKET_TABLE` 이다. 근거 = 한국투자증권 고객 공지(거래시간·가격제한·미체결 규약) + Open API 공지 2026-09-09(TR·필드 변경분 정본 = `docs/kis/README.md` 「제도 변경 공지 반영」 절).

| 시장 | 구간 | 시각 |
|---|---|---|
| KRX | 시가 단일가(K1) | 08:20~09:00 |
| KRX | 장전 시간외 종가(K2, K1 안의 의도된 중첩) | 08:30~08:40 |
| KRX | 정규장 연속매매(K3) | 09:00~15:20 |
| KRX | 종가 단일가(K4) | 15:20~15:30 |
| KRX | 장후 시간외 종가(K5) | 15:30~16:00 |
| KRX | **애프터마켓(K6)** | 16:00~20:00 |
| NXT | 프리마켓(N1) | 08:00~08:50 |
| NXT | 휴장(N2) | 08:50~09:00 |
| NXT | 정규장(N3) | 09:00:30~15:20 |
| NXT | 휴장(N4) | 15:20~15:30 |
| NXT | 애프터 단일가(N5) | 15:30~15:40 |
| NXT | 애프터마켓(N6) | 15:40~20:00 |

⚠️ KRX **시간외 단일가**(16:00~18:00, K7)는 폐지됐고 **시간외 종가**(K5)는 남는다 — 둘을 섞으면 15:30~16:00 판단이 뒤집힌다.

**애프터마켓(K6)** — 가격제한 **전일 KRX 정규장 종가 ±30%** · 호가유형은 지정가 계열 **7종만**(`ORD_DVSN` 41~47, `docs/kis/domestic-stock-order.md`) · **시장가 불가** · **ETP(ETF/ETN) 제외** · 수수료·세금 정규장 동일 · SOR 가능.

🔴 **주문 존속 규약이 거래소마다 반대다** — KRX 는 정규장 마감 후 미체결이 **자동 취소**되어 애프터마켓은 16:00 이후 **새로 주문**해야 한다. NXT 는 미체결이 애프터까지 **유지**된다. SOR 주문도 들어간 시장에 따라 자동취소될 수 있다. NXT 프리마켓은 `GTP` 전용호가(`27`)가 있고 08:50 에 미체결을 일괄취소한다.

**`_BOARD_SCHEDULE` 과의 남은 어긋남 2건**(시정 = `_workspace/00_URGENT_WORKLIST.md` 보드 재설계 C0~C6)

1. `_BOARD_SCHEDULE` 에 **KRX 애프터마켓(16:00~20:00) 구간이 없다** — `post_nxt` 15:40~20:00 은 NXT 기준이다.
2. 시가 단일가를 08:30 으로 가정한 곳 — 08:20 으로 40분 앞당겨졌다.

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

시간 상수 (`scheduler.TIME_*`):

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_AUTO_START` | 07:45 | DB `auto_start` 우선 폴백 자동 시작 |
| `TIME_BOOT` | 07:55 | **런타임 미사용 상수**(테스트 핀 `tests/unit/engine/test_cycle92_time_boot_moved.py` 가 값을 잡는다 — 지우지 않는다) — `_boot()` 는 `scheduler.start()` 안에서 **즉시** 실행된다. 본체 = `src/engine/boot_manager.py::boot(scheduler)`: `_preissue_all_tokens()` → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()` → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → **`portfolio_risk.check_budget_invariant`**(`position_ratio × max_positions > 1.0` 이면 `[budget_invariant_violation]` WARNING, **관찰만**) → `allocate_funds(net_asset × ratio)` |
| `TIME_PRESUBSCRIBE` | 07:59 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독. 직전에 돌파 후보가 비었으면 VB/LTV 를, 후보가 빈 스윙 전략을 `funnel_capture.live_prepare_one(…, phase="presubscribe")` 로 다시 준비한다 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task (`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`) + `_confirm_breakout_open_prices(board="pre_nxt")`(LTV `pre_nxt` 보드 시가 확정) |
| `status_exit_watch` 패스 (scheduler 상수 아님) | 08:45 · 09:00:05 · 09:00:30~15:28 | 종목상태 조회 — P0(08:45, `pre_nxt` 전략이 있으면 07:59) · P1(09:00:05, 스윙 제외) · 보유 청산(09:00:30 부터 5분 격자, 15:28 미만). 휴장일 확정일은 돌지 않는다. 상세 = 「종목상태 청산·당일 매수 차단」 절 |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV 가 KRX 09:00 시가로 target_price 계산. 직후 `_drain_pending_next_day_clear()`(08:00 보류 종목 KRX 시장가 일괄 청산). 이미 확정이면 idempotent skip |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — POST_NXT 활성과 무관하게 모든 전략에 `check_force_clear()`. 매도 사유 = 전략의 `force_clear_signal`(기본 `FORCE_CLEAR`, cycle402). VB(`("main",)`) = 전량 청산. LTV(`("pre_nxt","main","post_nxt")`) = `_limit_up_reached` 종목 중 15:20 가격이 `limit_up_threshold` 이상인 것만 제외하고(`limit_up_close_hold_mode`, cycle352 — `src/engine/strategies/CLAUDE.md` LTV 절) 나머지는 함께 청산, 유지분만 익일 청산 모드로 보존 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감. 15:30~15:39:59 = MAIN 유지 (종가 흡수 마진) |
| `TIME_POST_NXT_OPEN` | 15:40 | **런타임 미사용 상수**(테스트 핀 `tests/unit/engine/scheduler/test_post_nxt_open_time.py` 가 값을 잡는다 — 지우지 않는다) — POST_NXT 전환(`_phase = "post_nxt_trading"`)과 `_confirm_breakout_open_prices(board="post_nxt")` 는 `run_daily` 가 `TIME_KRX_MAIN_CLOSE`(15:30) 대기 직후에 한다. **보드 경계의 정본은 `_BOARD_SCHEDULE`** 이다 |
| `TIME_STOCK_MASTER_BASICS_REFRESH` | 16:10 | basics 갱신 (상세 = 「저녁 데이터 적재」 절) |
| `TIME_STOCK_MASTER_MASTER_LOAD` | 16:30 | 마스터 파일 적재 |
| `TIME_STOCK_MASTER_FINANCIAL_LOAD` | 16:40 | 재무 5 TR 주1회 적재 |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 애프터 신규 매수 중단, 변경 금지) |
| `TIME_NXT_POST_CLOSE` / `TIME_RECOMMENDATION` | 20:00 | `unsubscribe_all()` + `generate_recommendations()` — 동기 순차 (자문 ~3분). 같은 20:00 이 `TIME_SESSION_START_CUTOFF` 이기도 하다 |
| `TIME_SESSION_START_CUTOFF` | 20:00 | `scheduler.start()` 기동 거부 경계이자 `run_daily` 의 "이미 장 종료면 내일로" 판정 — **같은 상수**다(갈리면 헛 재시도가 그날 `level_counts` 를 오염시킨다). `TIME_SETTLEMENT` 와 나눈 이유 = 겸하면 20:00~21:30 재기동이 AI 자문·`auto_apply_recommendations` 를 다시 돌린다. ⚠️ 그 창의 재기동은 **그날 20:30 일봉 적재를 잃는다** — 다음 영업일 일봉 task 의 immediate 실행(stagger 240초, 슬롯 게이트 `reason=stale`)이 7일 증분으로 보정하지만 `_boot()` prepare 보다 늦고, `[daily_head_stale]` 가 결손을 알린다. 그 사이 prepare 는 헤드가 `expected_head`(직전 영업일)보다 오래된 종목을 KIS 로 폴백해 읽어 느려지고, `expected_head=None`(휴장일 조회 실패)이면 하루 밀린 DB 헤드를 그대로 읽는다. +600초 재준비는 적재 완료를 기다리지 않는다 |
| `TIME_FULL_UNIVERSE_LOAD` | 20:00:05 | 전체 유니버스 일괄 적재(`_full_universe_load_task_loop` → `scanner._full_universe_load_once`). `[full_universe_load_summary] total= kospi= kosdaq= fetched= skipped_ttl= failed= elapsed_ms=` 1행 |
| `TIME_METRICS_SNAPSHOT` | 20:05 | metrics 1차 스냅샷(`daily_metrics_snapshot.run_daily_metrics_snapshot`, leaf) — 메모리 전용 `api_metrics`·`strategy_funnel` 의 유실 노출을 5분으로 묶는다. 🔴 **OpenAI 미호출**(`model`·토큰 5컬럼 NULL) · 🔴 **`reset_request_metrics()` 미호출**(부르면 21:30 완전판이 90분치만 본다) · never-raise · `[daily_metrics_snapshot] target_date= pass=1 elapsed_ms=` |
| `TIME_STOCK_MASTER_DAILY_LOAD` | 20:30 | KIS 일봉 적재(`scanner._stock_master_daily_load_once`) — 상세 = 「저녁 데이터 적재」 절 |
| `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` | 20:45 | 보조 시세 계정 접근토큰 강제 재발급 — 정본 = 모듈 맵 `quote_token_refresh.py` |
| `TIME_EVENING_FUNNEL_CAPTURE` | 21:00 | 저녁 미리보기 funnel 캡처(`_evening_funnel_capture_task_loop` → `funnel_capture.evening_capture_once`) — 다음 거래일 `prepare(as_of=)` + 잠정 캡처, 20:30 적재 성공 마커를 30초 간격으로 21:15 까지 기다린다. 상세 = 「funnel 스냅샷 캡처」 절 |
| `TIME_SETTLEMENT` | 21:30 | `_settle()` → `generate_daily_log_report()`(20:05 1차 행을 upsert 로 덮는다) → **`purge_old_logs()`**(INFO 2일 / WARNING+ 30일, 실패 graceful `[log_retention_skip]` INFO) → `_reset_daily_state()`(퍼널 카운터 초기화는 분석 *후*) |

기타:
- WebSocket 연결 직후 **체결통보 자동 구독** (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호) + 통합 장운영정보 `H0UNMKO0`/`005930` (실전 한정)
- `_load_strategy_config()`: DB `strategy_config` 에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구. **비중 단위 오염 감지** — 적용 루프 직후·`_config_loaded=True` 직전 `[weight_config_anomaly] sum=%.4f over_one=%s` WARNING(개별 `weight > 1.0` **또는** Σ `> 1.001` — `routes/strategies.py::_WEIGHT_SUM_TOLERANCE`(1e-3)와 리터럴 중복). 집계 = **레지스트리 등록 전략 행만**(`registry.get(sid) is not None`), `enabled=False` 행 **포함**. 🔴 **자동 클램프·정규화 절대 금지** — 오염을 그럴듯하게 만들면 실측 근거가 사라진다. try/except **fail-open**. `weight=None` 은 감지 *이전* `cfg["weight"] * 100` TypeError → 기본값 폴백 + `_config_loaded=False` 재시도(완화 금지). 회귀 `tests/unit/engine/test_weight_config_anomaly.py`
- `run_daily()`: 주말+공휴일 건너뜀 (KIS `chk-holiday`), 매일 시작 전 DB auto_start 재확인
- **`_scan_loop(*, first_delay: float | None = None)`(5분 주기, 09:30~)**: VB+LTV+donchian + 모든 전략 보유 합집합 재구독.
  - 🔴 **첫 회차 지연은 호출부가 정한다(cycle298)** — 루프가 진입 직후 `sleep` 을 먼저 하므로 선행 구독이 없는 경로는 그만큼 시세 공백이다. 09:30 진입 = **인자 없음**(바로 앞에서 `scan_stocks()` + `subscribe_filtered_stocks()` 를 했다), 15:30 POST_NXT 전환 = **`first_delay=0`**(선행 구독 없음). 15:30 경로는 15:20 `self._scan_task.cancel()` 때문에 **매일** 탄다(`if self._scan_task is None or self._scan_task.done():`).
  - 값 처리 — `None` = `SCAN_INTERVAL`(300초). 숫자는 **`min(float(SCAN_INTERVAL), max(0.0, float(x)))`**, 비수치는 `SCAN_INTERVAL`. 🔴 **상한이 계약이다** — `float("inf")`·`1e9` 가 `asyncio.sleep()` 에 들어가면 유일한 WS 재구독 경로가 무음으로 영구 정지한다(= 손절·트레일링 정지). **2회차부터는 언제나 `SCAN_INTERVAL`**(위상만 당긴다 — `sync_counter % 3` 주기 불변).
  - 첫 성공 회차 구독 직후 `[scan_loop_first_subscribe] first_delay= elapsed_s= n=` INFO(never-raise). 남은 공백 = `15:20 ≤ T < 15:30` 기동의 **최대 10분**(`_scan_task=None` 으로 15:30 까지 기다린다). 15:20 `cancel()` 은 구독을 해제하지 않는다(해제는 20:00 `unsubscribe_all()` 뿐).
  - 🔴 **전체 재구독 금지** — `_delta_unsubscribe_dropped(new_set)`(빠진 종목만) + `subscribe_filtered_stocks`(LOW `already_in_pool` 가드로 SEND skip)로만 갱신한다(KIS "비정상 케이스 2" 무한 등록/해제 차단). HIGH(positions/next_day_clear)는 **항상** 호출(`_select_session` promote 보존). `_build_priority_groups(momentum_tickers=...)` 는 **항상 momentum/breakout 정상 list**(모드 분기 신설 금지). 직후 `_reprepare_breakout_if_empty()`(`volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`.
- **`_resubscribe_stale_priority`(5분 우선 재구독)**:
  - 우선순위 = positions/`_pending_next_day_clear` stale → **HIGH + `bypass_limit=True`** / 그 외 후보 stale → **LOW + `bypass_limit=False`** — 후보를 HIGH 로 올리면 메인 과부하·silent inactive 를 부른다.
  - subscribe **전** 구독상태 가드 — `kis_ws_pool.get_subscribed_tickers()` 스냅샷으로 **실제 구독 종목은 `unsubscribe_in_pool`**, **미구독(split-brain·stale 후보)은 `kis_ws_pool._ticker_to_session.pop` 직접**(KIS unsubscribe 미발송 — OPSP0003 스팸 회피). 앞쪽이 없으면 `_ticker_to_session[t]=main` 잔존 → 풀 dedup 이 재SEND 를 막아 보유 종목이 온종일 미구독(손절 사각)이 된다.
  - 동시호가면 **LOW-scoped skip**(`is_call_auction_now` True → `low_targets=[]`, HIGH 유지) + **LOW-only throttle** `RESUBSCRIBE_THROTTLE_SECS = 3 × STALE_FRESHNESS_SECS = 180`(`_stale_last_resubscribe_at`). 🔴 **HIGH 면제** · 🔴 `< 300`(함수 5분 주기) **불변식** — self-block 이 split-brain 복구를 막는다.
  - LOW 는 **desired 교집합**만 — `desired_low` = `scheduler._collect_breakout_tickers()` ∪ `scanner._last_scan_result`. 순서 = priority 분리 **직후** → desired 필터 → 동시호가 → cap **앞**. 활성 게이트 = breakout 비어있지 않음 ∧ HIGH 수집 무예외(`_high_collect_ok`), off = 현행 byte 동일 **fail-open**. 없으면 정산까지 안 지워지는 `ticker_last_tick` 때문에 `_delta_unsubscribe_dropped` 와 무한 페어링이 된다. 🔴 `kis_ws_pool.get_subscribed_tickers()` 를 desired 로 쓰지 않는다(split-brain 복구 무력화). AST `test_cycle240_ast_desired_filter.py` G-240-1~7.
  - cap 은 priority 분리 **후** — `targets = high_targets + low_targets[:max(0, cap - len(high_targets))]`(**HIGH > cap 이면 전부 보장** + `[stale_priority_resubscribe_cap_exceeded]` WARNING, AST G-17). 분리 **전** `stale_tickers[:cap]` 재도입 금지(HIGH 가 잘린다).
  - 로그 `[stale_priority_resubscribe] count= tickers= desired_low= filtered_not_desired= filtered_sample=`(`count=` 첫 필드 보존). 잔여 = `ticker_last_tick` 매도 시 pop(8영역, 워크리스트 P1-7 후속 A).
- 🔴 **WS 등록 경로는 `_scan_loop` 5분 delta 단일이다** — near-signal 류 60초 루프·스트림 풀 모듈을 신설하지 않는다(그 루프가 `_scan_loop`/K stale watcher 와 race 해 `OPSP0002` 폭주 → tick_coverage 0% 를 냈다). OPSP0002 는 `_handle_raw` backoff(`_opsp_backoff_until`, **300s ≥ `_scan_loop` 5분 주기**)로 흡수한다.
- **`_stale_watcher_loop()`(120s 주기, 본체 `stale_watcher_core.check_and_resubscribe_stale` — 판정 순서·no_feed skip = 모듈 맵 `stale_watcher_core.py`)**: `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick`, `STALE_FRESHNESS_SECS=60` 초과면 stale, 종목별 `_stale_retry_count` 누적. 소스가 **구독 집합**이라 5분 경로의 핑퐁 결함이 없다.
  - **1~5회** = 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority, bypass_limit)`. 🔴 같은 종목 재SEND(`pool.resend_subscribe_for_ticker`) 재도입 금지 — KIS "기등록한 사항을 재등록하지 않도록(LMS + 앱정보 이용중지)".
  - **`> MAX_STALE_RETRIES=5`** = 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS=600` 경과 또는 `_stale_last_resubscribe_at` 부재면 강제 재등록 + `_stale_retry_count[ticker]=0` + `_stale_force_retry_history`(60분 슬라이딩). 시간당 `STALE_FORCE_RETRY_HOURLY_CAP=6` 초과면 `[stale_force_retry_cap]` WARNING skip. cooldown-skip 은 `_stale_retry_count[ticker] = MAX_STALE_RETRIES+1` 로 **홀드**한다 — 0 으로 되돌리면 universe guard 가 persistent-stale 종목을 못 뺀다.
  - 우선순위 = `high_tickers` = `registry.all()` positions ∪ `_pending_next_day_clear` → HIGH+bypass=True / 그 외 → LOW+bypass=False.
  - **세션 단위 silent inactive** = `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)` ∧ `subscribed_count >= SILENT_INACTIVE_MIN_SUBSCRIBED(=5)` ∧ `SILENT_INACTIVE_PERSIST_SECS(=300)` 지속 → `_force_reconnect_session(label)` 이 `_ws.close()` + `[silent_inactive_force_reconnect]`. **시간당 세션당 `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR=2` cap**(`_silent_inactive_recovery_count`, 윈도우 `SILENT_INACTIVE_RECOVERY_WINDOW_SECS=3600`).
  - **시장 침묵 기각(세션 상대 판정)** — 규칙·금기 = 모듈 맵 `stale_session_recovery.py`. 구현 2-pass — pass 1 이 세션별 `(label, subscribed, silent_suspect)` 를 상태 무변경으로 계산하고, 판정 가능 세션이 `_MARKET_WIDE_MIN_ELIGIBLE(=2)` 이상이며 전원 suspect 면 `first_seen` 을 pop 하고 `[]` 를 반환한다(🔴 hold 금지).
  - 관측 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited`(1800초 이상이면 `persisting` WARNING 1800초마다), `write_log` 0. 상태 `_MW_EPISODE` = **모듈 전역 날짜 키 자기 리셋**(`StaleTrackerState` 7필드 가드 때문). ⚠️ `connected=`·`reconnects=` 는 소켓 생존 확증이 아니다 → `[ws_heartbeat]` 로 읽는다.
  - 로그 `[stale_watcher_detail] session= sub=n/41 fresh= stale= ratio= stale=[(ticker,r=,@시각),...]`(종목 cap 20 + `...+N`). `[stale_watcher]`/`[stale_priority_resubscribe]` 보존. 안전망 4중 = F1(재연결 1회) + `_scan_loop`(5분) + K stale watcher(120s) + `_resubscribe_stale_priority`(5분 우선).
- **`_refresh_stale_ccnl_cache(stale_tickers, cap=20)`**: stale r≥2 종목 `quotation.inquire_ccnl` → `_last_ccnl_cache: dict[ticker, dict]`. TTL 5분 + cap 20 + 종목 간 50ms + 보유 우선 + None/예외 미저장. `_scan_loop` 통합 + `_reset_daily_state` 동행 clear. `/api/realtime/subscriptions` 의 `tickers_detail.last_cntg_hour / today_volume` 소스.
- **`_evaluate_universe_guard(candidate_tickers)`**: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 제외. 사전 가드(보유/익일청산/이미 제외/stale≤5 → KIS 호출 skip) + `inquire_ccnl` + `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` + `[universe_excluded] ticker=... reason=stale_6plus_low_volume retries=... last_resub_age=...s last_cntg_hour=... today_volume=...` INFO. `_collect_breakout_tickers` 필터링 + `_scan_loop` 통합 + `_reset_daily_state` 동행 clear(🔴 영구 블랙리스트 금지).
- **stale 관리 모듈 구조**: facade `stale_manager.py`(`__all__` re-export only — 11 함수 + 11 상수, 프로덕션은 본체 모듈을 patch) + `stale_diagnostics.py`(`build_session_subscription_view`/`emit_stale_session_detail`/`refresh_stale_ccnl_cache`/`evict_expired_ccnl`/`prune_force_retry_history` + 상수 5) · `stale_session_recovery.py`(`detect_silent_inactive_sessions`/`force_reconnect_session`/`delta_unsubscribe_dropped` + 상수 5) · `stale_universe_guard.py`(`evaluate_universe_guard` + 상수 1) · `stale_watcher_core.py`(`check_and_resubscribe_stale`·`resubscribe_stale_priority` = **K stale watcher HIGH hot path**). `scheduler.py` 는 `from src.engine import stale_manager` lazy import 2줄 wrapper **11개**(위 11 함수 이름 + `_` 접두, 예 `_check_and_resubscribe_stale`)로 위임하고 상수 10개를 re-export 한다(`is` 동일). 계약:
  - ① 4 모듈 logger 는 `logging.getLogger("src.engine.scheduler")` **고정**(`__name__` 이면 `system_logs` 접두와 `caplog.set_level(logger="src.engine.scheduler")` 회귀가 깨진다, AST Q3).
  - ② `kis_ws_pool`/`kis_ws`/`datetime` 은 `sys.modules.get("src.engine.scheduler")` 네임스페이스 **우선** 참조(정적 import 금지 AST D-1).
  - ③ 의존은 단방향, `stale_watcher_core` → `stale_diagnostics` 는 **모듈-레벨 정적 import**.
  - ④ registry 순회 try/except **4중**(outer + positions + NDC) — `getattr` 폴백 비채택.
  - ⑤ 5분 aggregation 은 `record_*`/`flush_*` **쌍**(`record_swing_rest_poll(stats)`/`flush_swing_rest_poll_collector()` · `record_stale_watcher_check(stats)`/`flush_stale_watcher_collector()`) → `[swing_rest_poll_summary] polls= candidates_avg= max= total_held= elapsed_ms_avg=` · `[stale_watcher_summary] checks= stale_total= retried= cap_blocked= force_retried=` · `[dispatch_drop_summary]`. 결함 시(`stale_count > 0`) `[stale_watcher_detail]`·`[stale_force_retry_cap]`·`[stale_priority_resubscribe_cap_exceeded]` 는 개별 영속. 🔴 `record_*` 정의 모듈에는 `flush_*` 호출 사이트 **≥1**(AST G-AST1 — 없으면 무한 누적). `logger.info` 금지 가드(G-7/G-8-A/G-8-B)·**개별 ERROR 7 prefix** = `src/realtime/CLAUDE.md` 「WS action 집계」 절.
  - ⑥ `_api_recovered_collector_loop`(5분)가 `flush_swing_rest_poll_collector`·`flush_stale_watcher_collector`·`flush_silent_drop_count` 를 각각 try/except 로 부르고 `stop()` hook 도 flush 한다(`unsubscribe_all()` 직전). `_api_recovered_collector_task` 는 `stop()` cancel 목록에 있다. `if not self._running: break` 는 flush 블록 **이후**. AST G-78 / G-78-VERIFY-1~5.
  - ⑦ scheduler 의 `_stale_retry_count`·`_stale_last_resubscribe_at`·`_last_ccnl_cache` 등 **property layer 7쌍을 보존한다**(`src/routes/realtime.py` 가 `getattr` 로 읽는다).
  - ⑧ `tests/unit/engine/` 의 `patch("src.engine.stale_manager.X")` 는 X 가 facade export 여야 한다(AST G-16). 본체가 같은 모듈에서 직접 부르는 대상은 본체 모듈 경로로 patch 한다.
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`) → trade_history 동기화. **호출부는 `boot_manager.py` 유일**(부팅 1회). MTS/HTS 수동 매매분 반영. 중복 판정 키 `(ticker, order_no)` — 소스는 dedupe 없는 `get_today_*_trades_for_sync()`(`src/db/CLAUDE.md` `trade_history.py` 절).
  - **전략 귀속 출처 순서(cycle354)** = DB(`db_strategy_map`) → `order_engine._order_strategy`(읽기 전용) → `"momentum"`. 매도는 registry 라이브 포지션(정확한 buy_price 의 유일한 출처)이 최종 권위다. 셋 다 미확보 = `[sync_strategy_unknown] ticker= order_no=` WARNING(빈 문자열 매핑은 `or None` 정규화, 속성 부재 더블은 `getattr` 폴백).
  - ⚠️ **포지션 복구의 전략 귀속은 별개 경로다** — `boot_manager.boot()` 의 KIS 잔고 보완 복구 = `get_recent_buy_strategy(ticker)` → `"momentum"`, 미체결 매수 복구 = `db_positions`→`get_today_buys_ticker_strategy()`→`"momentum"`. 폴백이 틀리면 엉뚱한 전략의 손절 규약을 탄다 — 후속 검토 대상
- `_sync_positions_from_balance()`: 15분 주기. strategy 매핑은 trade_history 직전 BUY 행에서 상속. 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제.
  - **stale `_selling` 재대조** — 본체 = leaf `selling_reconcile.py`(3분기·`[selling_hold]` = 모듈 맵). 보유 잔존 ∧ 열린 매도주문 없음 ∧ 경과 ≥ `SELLING_RECONCILE_MIN_AGE_S=180s` 이면 `_selling.discard` + `_selling_since.pop`(`[selling_reconcile]` WARNING).
  - **체결 0 매수 pending 회수** — 본체 = leaf `buying_reconcile.py`(모듈 맵). selling 재대조 **뒤**, 어느 전략이든 `pending_buys` 가 있을 때만 `reconcile_stale_buying(self.registry, self.order_engine, holdings)`(같은 함수 첫머리 `get_balance()` 결과 재사용).
  - sync 는 `_scan_loop` 3회차마다(≈15분), `_scan_loop` 은 09:30~15:20 · 15:30~20:00 에 산다(해제 시점 ≈09:45~15:15 · ≈15:40~19:55). 20:00 뒤 남은 pending 은 21:30 `_reset_daily_state` 가 치운다
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 시가 수신 후 30s 안정화 → **갭 ≥ 임계**(`gap_rate >= gap_up_threshold`) = 트레일링 모드(`strategy_id == "long_tail_volatility"` 가드로 LTV 만 `_limit_up_reached.add(ticker)` + `pos.high_since_buy = today_open` — 없으면 트레일링이 silent 미발화) / **갭 < 임계**·시가 미수신·`nxt_tradable=False` = `_pending_next_day_clear` 보류(reason=`nxt_underthreshold` 등) → 09:00 KRX 시장가. 🔴 **08:00 NXT 프리 지정가는 내지 않는다** — 미체결 만료가 어느 `_selling` discard 경로에도 안 걸려 손절 마비가 된다
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후. `_pending_next_day_clear` 종목 KRX 시장가 일괄 청산
- 구조화 로그: `[next_day_clear_deferred] ticker={t} strategy={s} reason={nxt_not_tradable|nxt_open_missing|nxt_underthreshold}` / `[next_day_clear_drained] ticker={t} strategy={s} result={success|fail} elapsed_ms={ms}` / `[selling_reconcile] stale _selling 해제: {t}`
- `_reset_daily_state()`: 전략별 positions/pending_buys/sold_today + OrderEngine 추적 상태 + scanner 글로벌 dict (`ticker_last_tick.clear()` 포함) + `_pending_next_day_clear.clear()` + `_stale_retry_count.clear()` + `_reprepare_empty_logged_today.reset_daily()` 전체 초기화
- **`_reprepare_breakout_if_empty` WARNING DailyEmitCap**: "스캔 후보 비어있음 — 재 prepare 시도" WARNING + `write_log` 를 `_reprepare_empty_logged_today: DailyEmitCap[str]` 로 1회/전략/일 cap. 🔴 **재준비(`funnel_capture.live_prepare_one(strategy, phase="intraday_empty")`) 행위는 cap 밖**. `getattr` 폴백 = `__new__` 스텁 호환. 회귀 `tests/unit/engine/test_cycle189_reprepare_emit_cap.py`

## scanner.py

- `scan_stocks()`: 모멘텀 등락률 순위. ETF/ETN 제외 = `is_etf_like(item, name)` — 원천 행에 코드가 없어 이름 폴백만 탄다(모듈 맵 `etf_like.py`)
- `subscribe_filtered_stocks(tickers, extra_tickers, source_counts=None, *, priority_groups=None)`: 합집합 구독
 - `priority_groups` 분기: `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=...)`. `positions`/`next_day_clear` → HIGH + `bypass_limit=True`, `breakout`/`momentum`/`swing` → LOW + `bypass_limit=False`(보조 우선, 가득 시 메인 fallback)
 - **2-pass**: 1차 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing → 2차 `MAX - len(_subscriptions) > 0` 면 breakout overflow 흡수. drop = `max(0, len(overflow) - absorbed_overflow)`, drop>0 시 `[priority_drop]` INFO + WARNING `system_logs`. 중복은 HIGH 1회만, HIGH 단독 41 초과 시 ERROR. **로그 필드** = `breakout/momentum/swing/total_subscribed/max/high_count/low_remaining/pool_sessions/pool_slots/pool_subscribed/pool_remaining` — `pool_subscribed`(`len(kis_ws_pool._subscriptions)`)·`pool_remaining`(`max(0, pool_slots − pool_subscribed)`)이 포화가 메인 41-cap 인지 풀 전체(`pool_slots=41×세션수`)인지 가른다
 - `source_counts` 전달 시 `[scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)` (영문 라벨)
 - 평탄 처리 분기 (`priority_groups=None`)는 `kis_ws.subscribe` 직접 호출 보존
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS`: donchian_swing 고정 유니버스
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: import 시 자기 파일을 정규식으로 파싱 → 종목명 dict(KIS `inquire-price` 빈 응답 대비)
- 공용 데이터: ticker_names, ticker_prices, ticker_prev_close, ticker_market_info, **ticker_last_tick** (`risk.on_tick` 호출 시 KST `datetime` 갱신)
- **`get_scan_status()` 풀 전체 카운트**: `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합. `tick_coverage_total/acked/fresh/stale` 4 키 + `subscribed_count` 보존. `/api/trading/status` `scan` 필드 → ScanMonitor stale 배지 + 진행바

## log_analysis_engine.py — 일일 로그 분석

21:30 정산 직후 `generate_daily_log_report(_now_kst=None)` 호출(`_now_kst` = 테스트 주입). 호출 *후* run loop 가 `_reset_daily_state()` 를 따로 실행한다(퍼널 카운터 보존). 당일 KST 00:00~now `system_logs` + `trade_history` → OpenAI → `daily_log_reports` INSERT.

데이터 수집:
- **`log_metrics_collector._fetch_logs_in_range(start, end, limit=5000)`**: `pg.fetch` `LIMIT/OFFSET` 1,000행(`PAGE_SIZE`) 페이지 루프, `limit` = *총* 한도(호출부 `DAILY_LOG_FETCH_LIMIT=30_000`), `timestamp` = `+09:00` KST str. **`get_trades_in_range`** 는 start/end 에 `+09:00` 명시(없으면 KST 00:00~09:00 거래가 빠진다).
- **표본 절단 감지** — `ORDER BY timestamp ASC` 라 상한을 넘으면 이른 시각부터 채우고 조용히 끊는다. 시정 3종:
  - **`_count_logs_by_level(start, end)`** — `GROUP BY log_level` 진짜 총계 → `logs.level_counts_actual`(실패 `{}`).
  - **`_fetch_high_severity_logs(start, end, limit=HIGH_SEVERITY_FETCH_CAP)`** — ERROR/CRITICAL 전량. `_merge_high_severity(logs, high)` = `(timestamp, log_level, message)` 중복 제거 + 시간순 병합.
  - **`_aggregate_logs(logs, fetch_limit=...)`** — `truncated` / `covered_from` / `covered_to` / `fetched_logs` / `coverage_note`. ⚠️ 커버 구간·절단 판정은 **ERROR/CRITICAL 제외 레벨 기준**(전량이 ERROR 인 날은 전체 기준). `fetch_limit` 미전달 = `truncated=False`.
  - 절단 시 `[log_report_truncated]` WARNING + `SYSTEM_PROMPT` 가 "총계는 `level_counts_actual` 인용, 분석 구간 명시" 를 지시한다. 상수 `DAILY_LOG_FETCH_LIMIT=30_000` / `HIGH_SEVERITY_FETCH_CAP=5_000`. 회귀 `tests/unit/engine/test_log_report_truncation.py`

확장 메트릭:
- `api_metrics`: `api/base.py::get_request_metrics()` (5xx/4xx/network/retries + path별 5xx top 5). INSERT 후 `reset_request_metrics()`
- `strategy_funnel`: 전략별 `{signals, orders, fills}` (registry 순회)
- `trades.by_ticker_pnl` (SELL PnL 절대값 top 5) / `trades.by_hour_pnl` (KST hour별)
- `next_day_clear`: `{deferred, drained_success, drained_fail}` (구조화 로그 prefix 정규식)

출력 스키마: `{summary, findings: [{category, severity, title, detail, suggestion}]}`. `(target_date)` UNIQUE. OpenAI 타임아웃 60s, 실패 시 메트릭만 보존 INSERT.

## recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending), `(target_date, strategy_id)` UNIQUE
- `/api/recommendations/{id}/apply`: 사용자 키 선택 적용 → `strategy_config.params` 갱신 + status applied/partial
- `expire_pending_before(target_date)`: 이전 영업일 pending 자동 만료
- `_validate_recommendations()` 5-tuple `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 에 `current_weight` + `peer_weights` + `peer_metrics` + `market_regime` 12 키
- `apply_weight=true` → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. 🔴 `allocate_funds()` 즉시 재호출 금지(다음 `_boot` 반영).
  - **증액 한정 Σ 사전 검증** — `new > 현재 weight` 일 때만 `타 전략 weight 합 + new > 1.0 + _WEIGHT_SUM_TOLERANCE`(`routes/strategies.py` import = 단일 진실원) 위반 시 `[weight_sum_violation]` WARNING + `success=false` **early return**(아무것도 저장 안 됨). float 변환 실패 = 검사 skip.
  - 🔴 **감액은 Σ 상태와 무관하게 항상 통과한다** — 오염 상태에서 감액이 복구 수단이다.
  - ⚠️ 이 경로는 메모리 `config.weight` 만 바꾸고 `enabled` 는 안 건드린다(메모리 활성 / DB 비활성 split-brain) — 메모리도 끄면 즉시 손절이 멈추므로 **의도적 미시정**이고 `enabled` 축은 후속 소관이다. 보유 매수금액 하한선 검증은 이 경로에도 있다(루트 `CLAUDE.md` 「핵심 안전 규칙」)
- **`PARAM_RANGES`(자동 튜닝 화이트리스트)·`INT_PARAMS`(정수 캐스트)** — 정본은 `recommendation_engine.py` 의 두 상수(키 목록은 여기 적지 않는다). 불변식 **`INT_PARAMS` ⊆ `PARAM_RANGES`**. 진입 품질 키(VCP·BFB) = `strategies/CLAUDE.md` 「PARAM_RANGES 편입 목록」 절.
  - 🔴 **편입 금지(정체성 상수)** = 진입 축 `buy_threshold`·`donchian_period`·`max_breakout_extension_pct`·`box_contraction_period`·`max_box_volatility_pct` / 청산 축 `atr_trail_mult`·`breakout_fail_n_days`(donchian·BFB·VCP **3 전략 공유**, 근거 표본은 donchian 뿐 → VCP/BFB 청산 왕복 ≥20 시 재검토) / 리스크 축 `max_positions`·`max_lot_units`·`max_lot_ratio_mult`·킬스위치 2키. AI 가 매일 밤 흔들면 전략이 변태한다. **수동 적용 라우트도 같은 정본을 참조한다.** 나머지 = `strategies/CLAUDE.md` 같은 절.
- **`auto_apply_recommendations(target_date)`**: 20:00 AI 자문 직후 자동 적용 — **weight 감액만**(감액 + 50% cap). 🔴 `_CONSERVATIVE_KEYS` 는 **빈 frozenset** — 손절/일일한도/비중 7키(`stop_loss_rate`·`position_ratio`·`daily_loss_limit`·`intraday_stop_loss`·`overnight_stop_loss`·`stop_loss_main`·`stop_loss_pre_nxt`)를 자동 적용하지 않는다(조이기만 하는 `float(v) > current` 게이트는 단조 ratchet 이라 전략을 교살한다). `auto_apply_enabled=False` = 즉시 disabled. 로그 `[auto_weight_apply]`/`[auto_params_apply]`/`[auto_apply_skip_increase]`/`[auto_apply_safeguard_skip]`, `status='applied_auto'`(수동 `'applied'` 와 분리). 호출 = `TIME_RECOMMENDATION` 직후, 날짜는 `datetime.now(_AUTO_APPLY_KST_TZ).date()`(`scanner.KST_TZ`). `backtest_engine.poll()`/`wait_for_result()` 는 `pending` 을 `running` 과 같게 처리한다(unknown 이면 `status=failed` 오기록)
- `recommendation_metrics._normalize_stop_loss_rate(params)`: 5 키(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`) 중 음수만 → `min(candidates)`(가장 보수적)
- SYSTEM_PROMPT 끝 매크로 가이드 — defensive/neutral/aggressive 분기 + **레짐은 매매 미개입·`buy_blocked` 는 항상 false 이므로 매수 임계 튜닝은 유효하고 스킵 금지, `block_reason` 은 참고 신호** + `weight_reasoning`/`code_review_notes` 에 매크로 영향 명시 권장
- VIX 분류 `_classify_vix()` 임계 15/25/35 (low/normal/elevated/high). Fear & Greed `_classify_fear_greed()` 임계 15/35/65/85
- `weight_reasoning` (≤1000자, 한국어, `reasoning` 과 별개). `weight=None` 이면 자동 정리, 사유 누락 → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING

## 절대 깨지면 안 되는 규칙

전역 금기의 정본은 루트 `CLAUDE.md` — 「핵심 안전 규칙 (절대 깨지 말 것)」(체결통보 구독 · uvicorn 단일 워커 · 주문번호 매핑 · race 가드 · NXT 매도 거부 좀비 · 시장가 거부 폴백 · VB 15:20 일괄매도) · 「자금 관리」(`position_ratio` 식) · 「코딩 컨벤션」(TR_ID). 엔진 구현 상세 = 위 「order_engine.py」 절. 여기에는 엔진 고유 규칙만 둔다.

- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)
- 익일 청산은 scheduler 에서 시가 수신 후 30s 안정화 (`_next_day_clear_pending` 전략 가드 + `_pending_next_day_clear` scheduler 보류 set) — on_tick 즉시 청산 금지. 갭률은 반드시 `ticker_prices[ticker]["open_price"]`(WebSocket 시가) — `high_since_buy` 폴백 금지. 시가 미수신이면 `_pending_next_day_clear` 보류 후 09:00 KRX 시장가
- `Position` 에 `strategy_id` 필수 (체결통보 → 올바른 전략 라우팅)
- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:30 `post_nxt`(`TIME_KRX_MAIN_CLOSE` 대기 직후 — 보드 전환(15:40)보다 10분 앞서 확정). SessionTracker 30초 race 차단
- `src/engine/strategies/momentum.py` 의 손절 로그는 임계(`stop_loss`)를 함께 찍는다 — 운영 DB `stop_loss_rate` 가 코드 기본값과 다를 때 실제 임계를 확인하는 유일한 장치다(임계 인자 제거 금지)
- `src/engine/strategy.py` 의 모듈 함수 `check_buy_signal` / `check_stop_loss` / `check_next_day_clear` 는 **재도입 금지**(AST `tests/unit/ast/test_cycle103_ast_no_dead_strategy_funcs.py`). 남은 것 = `Signal` · `Position` · `StrategyState` · `calc_buy_quantity` + 모듈 상수 7종(`BUY_THRESHOLD`·`STOP_LOSS_RATE`·`GAP_UP_THRESHOLD`·`TRAILING_STOP_RATE`·`POSITION_RATIO`·`MAX_POSITIONS`·`DAILY_LOSS_LIMIT`)
- `_swing_rest_poll_loop` / `_swing_buy_poll_loop` 제거 금지 — 09:30~15:20 60s REST 폴링(멀티데이 보유 손절 평가 보강) + 09:05~09:30 매수 평가. **공유 순차 대상 `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")`**(순차라 double-buy race 차단, 전용 task 신설 금지) — cycle398 카드 #3 부터 `strategy_manifest.SWING_POLL_IDS`(명부 `eval_driver=="swing_poll"` 파생) 를 그대로 가져온 이름이고, 값·순서는 그대로다. 🔴 buy poll 은 레짐을 읽지 않는다. **`_SWING_POLL_STRATEGIES` 와 `risk.py::_TICK_BUY_EVAL_SKIP_STRATEGIES` 의 멤버는 항상 같이 움직인다**(후자가 WS 틱 경로의 매수 평가를 skip 해 poll 을 배타 소스로 만든다 — 한쪽만 바꾸면 이중 평가 또는 무평가). `risk.py:88` 은 **리터럴로 유지**(사용자 결정 B)하고 명부 파생과 교차 검사만 건다(`test_cycle398_strategy_manifest.py`). skip 자리 = `check_exit_signal`·보드·중복·자금 가드 **뒤**, `check_buy_signal` **바로 앞**(청산류는 정상 평가). 킬스위치 없음(1행 revert 로만 롤백)
