> 원본: `src/engine/CLAUDE.md` · 이관: 2026-09-17

정본은 [`src/engine/CLAUDE.md`](../../src/engine/CLAUDE.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

절 제목은 **이관 시점의 정본 절 제목**이다. 정본에서 절 이름이 바뀐 곳은 괄호로 새 자리를 적었다.

---

## 접수 후 PENDING 영속화 — 4경로 1코어 + 경계는 호출자 층 (cycle334)

(정본에서 걷어낸 원문 그대로, 편집 금지 — cycle335 가 매수 경계를 세우면서 대체됐다)

> 「선행 체결통보 체크 → skip 로그 → `TradeRecord` 조립 → race 흡수 INSERT」는 **코어 하나**가 한다 — `_persist_pending_after_send(*, trade_type, ticker, order_no, strategy_id, record_price, quantity, path)`. 매수 주·폴백이 **직접**, 매도 두 경로는 **경계 래퍼** `_persist_sell_pending_after_send` 를 거쳐 부른다(코어 호출 = 매수 2 + 래퍼 1 = **정확히 3곳**).
>
> 🔴 **경계(cycle327 ⓑ)는 코어에 없다 — 호출자 층의 책임이다.** 코어는 예외를 **그대로 전파**한다. 매도는 래퍼가 닫고 **매수는 아직 닫지 않는다**. 코어에 `try` 를 들이면 매수 두 경로의 예외 전파가 **조용히 바뀐다**(가드 `test_g328_0d`).
>
> - ⚠️ **매수 축의 접수 후 경계 부재는 결함이다**(별도 승인 사이클). 지금 매수는 접수 후 실패가 `:1512` 의 `pending_buys.discard` + `pending_buy_amounts.pop` 으로 흘러 — 그것은 **발사 실패의 정리**인데 발사 **성공** 뒤에도 실행된다 — `is_ticker_blocked_for_buy=False`(같은 종목 재매수) + `_calc_used_funds` 과소계상(**예산 이중 사용**, 미체결 LIMIT 은 하루 종일 안 채워질 수 있다) + `raise` 가 `risk.on_tick`(try 없음) 관통 + `cached_buyable_at` 미무효화(최대 60초 stale). 폴백은 중첩 `try` 의 핸들러가 `except KisApiError` 하나뿐이라 non-`KisApiError` 가 `execute_buy` 를 관통한다. **그 시정은 호출자 층에 세운다**(코어가 아니라).
> - ⚠️ **의도된 문구 변경 1건** — 매수 폴백 skip WARNING 에 ` (주문번호: %s)` 가 붙는다(정보가 느는 방향). 21:30 `top_patterns` 는 메시지 전문이 키라 **2026-09-21 전후 패턴 문자열을 비교하지 않는다**.

→ CHANGELOG: cycle334 행 · cycle335 행
→ 자문 원문(피해 범위의 전략별 차이 · 돌연변이 5종 실측 · 별건 카드 A~E) =
  `_workspace/domain_consult/cycle335_buy_post_send_boundary.md`

## 모듈 맵

### 2026-09-17 이관 — DB 접근 (Supabase→RDS 이전 M5) 전환 서술

```
> **DB 접근 (Supabase→RDS 이전 M5)**: `scheduler`(auto_start read + trade_history update + strategy select) / `boot_manager`(strategy 조회 + PENDING BUY 일괄 COMPLETED + 오늘 BUY 조회) / `log_analysis_engine`(`_fetch_logs_in_range` pg.fetch 페이징) 이 직접 supabase.table() 호출하던 것을 `src/db/pg.py`(asyncpg) 헬퍼 + `system_config`/`trade_history` 신규 헬퍼로 전환. auto_start = `system_config.get_auto_start`/`set_auto_start`. 상세 `src/db/CLAUDE.md`.
```

→ CHANGELOG: M5

### 2026-09-17 이관 — 모듈 맵 전문 (모듈 한 줄이 그 모듈의 사이클별 변경 로그이던 시절)

정본은 "모듈 — 현재 역할·API·불변식·금기" 한 줄로 다시 썼다. 아래는 그 재작성 직전의 원문 전체다
(사이클 48·51·55·57·60·61·63·66·67·76·78·88·89·102·106·107·116·122·126·127·129·133·134·135·
145·146·149·158·162·167·171·176·182·186·193·196·214·227·228·230·233·234·239·240·241·245·250·
251·252·258·259·263·264·268·269·270·272·273b·273c·273e·273-pre·274·276·278·282·283·285·287·
287b·289·290·292·293·294·295 의 증분 서술이 층층이 쌓여 있다).

````
```
strategy_base / strategy_registry → 추상 + 등록/비중/중복 가드
strategies/{momentum, volatility_breakout, long_tail_volatility, donchian_swing, bull_flag_breakout, vcp_breakout, kojiro}
session.py(MarketBoard, SessionTracker)
risk.py(on_tick) → order_engine.py(체결통보·DB persistence) → scheduler.py(시간 가드·run/settle) ← boot_manager.py(_boot 본체, 사이클 51) / stale_tracker.py(StaleTrackerState, 사이클 48) / **stale_manager.py facade 96L** (re-export only, `__all__` 21 — 사이클 67 분해) ⇄ **4 sub-module (사이클 67 카드 #14 분해)**: stale_diagnostics.py 357L (5 함수 + 4 상수 — 진단·CCNL 캐시·force_retry history prune) / stale_session_recovery.py 438L (3 함수 + 5 상수 SoT + **cycle241** private 2 상수 `_MARKET_WIDE_MIN_ELIGIBLE`/`_MARKET_WIDE_PERSIST_WARN_SECS` + `_MW_EPISODE` 관측 상태 + 헬퍼 6 — silent inactive 감지(**세션 상대 판정** — 판정 가능 세션 전원 동시 침묵 = 시장 침묵 기각)·세션 강제 reconnect·delta unsubscribe) / stale_universe_guard.py 157L (1 함수 + 1 상수 — 보유/익일청산 절대 보호 universe guard) / stale_watcher_core.py 619L (2 함수 + private 헬퍼 `_collect_low_desired` — **K stale watcher 본체 HIGH hot path** `check_and_resubscribe_stale` + `resubscribe_stale_priority` 사이클 66 priority 분리 *후* cap 영속 + **cycle240 LOW desired 교집합**(breakout ∪ momentum, HIGH 구조적 면제)). 사이클 60 Phase 2-A1 + 사이클 61 Phase 2-A2 + **사이클 63 Phase 2-A3 (refactor #2 완료)** + **사이클 67 sub-module 분해 (카드 #14 종결)** / sell_rejection.py(SellRejectionTracker, 사이클 55 R-1 + 사이클 57 V-1 알람)
scanner.py(종목 스캔/구독/STATIC_TICKER_NAMES + 사이클 122 `_stock_master_daily_load_once` + 사이클 126 `_stock_master_basics_refresh_once` + 사이클 129 `_stock_master_master_load_once`)
**metrics_collector.py** (사이클 133 — 공통 헬퍼 `make_metrics_collector(*, prefix, summary_keys, int_keys, str_keys, accumulate_keys, use_last) -> (record_fn, flush_fn, collector_list)` 팩토리. 사이클 76 Q2 빈 윈도우 skip + 사이클 89 누적/단일 행 분기 통합 + 사이클 68 KST `noqa: F401` L-3 영속. 4 facade 위임 영역)
**task_loop_helper.py** (사이클 134 — 공통 헬퍼 `run_periodic_task_loop(*, scheduler, task_label, wait_time, once_callable, record_fn, flush_fn, summary_log_format, summary_keys, immediate_first_run=True, retry_delay_secs=60, initial_delay_secs=0)` 팩토리. 사이클 88 G-REJECT graceful (CancelledError + Exception 분리) + 사이클 106 lifecycle race 차단 (immediate_first_run start 직후 즉시 1회) + 사이클 78 G-AST1 (record + flush 호출 사이트 영속 = 헬퍼 영역 내부) + Protocol `_SchedulerLike` TradingScheduler 호환. 4 task loop facade 위임 영역 — scheduler.py 3,501L → 3,398L -103L. **사이클 158 (2026-06-17) — `initial_delay_secs` 인자 신규** (default 0 = 회귀 보존). EC2 재시작 직후 4 task 동시 발화로 Supabase HTTP/2 ConnectionTerminated 폭주 결함 시정. scheduler 영역 4 task wrapper 별 stagger (full_universe=0 / basics=60 / daily=120 / master=180초). **사이클 193 (2026-07-04) — `immediate_skip_if_fresh_hours: float | None = None` 신선도 게이트 인자 신규** (default None = 기존 행위 완전 동일, 마커 조회/기록/import 0건). 지정 시 immediate 블록(stagger sleep 후, once 전)에서 `system_config.get_task_last_success(task_label)` 마커가 `0 <= elapsed < hours*3600` (미래 마커 음수 방어) 이면 immediate once() skip + `[<label>] immediate run skip — fresh` INFO 1행. once() 성공 직후(immediate + while 양쪽) `set_task_last_success(task_label, now_kst_iso())` 기록 (try/except graceful — 기록 실패 → 다음 부팅 immediate 실행 = 안전 방향). **정기 while 루프 발화는 게이트 무관 무조건 실행** (사이클 188 정기 발화 복원 보존, F-8 HIGH 가드). 모듈 상수 `IMMEDIATE_FRESH_SKIP_HOURS = 20.0` (16:10 저녁 성공 → 익일 07:55 boot ≈ 15.75h → skip / 저녁 장애 시 ≈ 39h → catch-up 실행). **게이트 대상 = basics/master/daily_load 3 task** — basics/master 는 멱등 없이 매 run 전량 재작성(17분/4분 실제 burst), **daily_load 는 사이클 263 (2026-09-06) 편입**(사용자 결정 09-06 카드 ④). **미대상 = full_universe/purge/evening_funnel** (`skipped_ttl`·사이클 192 후 저렴·사용자 결정 범위 외). ⚠️ **사이클 263 이 사이클 193 의 daily_load 제외 결정을 뒤집었다** — 제외 근거였던 "`max_bas_dd` 멱등이 immediate 를 이미 저렴하게 한다" 는 전제가 **실제로는 깨져 있었다**: 아침 immediate(07:56)가 장 전 KIS 로부터 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)을 받아 먼저 써서 `max_bas_dd == today` 를 만들고 그날 16:00 정기 실행을 전 종목 skip 시켰다(09-03 `fetched=0 skipped_fresh=982` · 09-04 `fetched=1 skipped_fresh=1015` 실측). 게이트 투입은 껍데기 생성 주체를 없애 **사이클 193 의 전제를 되살리는 방향**이다. 제외 사유였던 **후장 완결 off-by-one 우려는 사이클 263 의 오늘봉 시각 필터가 폐쇄했다**(자문 §A-1) — 낮 12:0x~15:30 재배포로 마커가 만료돼 immediate 가 다시 떠도 그 실행은 오늘 잠정봉을 기록하지 않으므로 같은 날 16:00 이 정상 fetch 한다. 마커는 `once()` **성공 시에만** 갱신되므로 16:00 실패·프로세스 다운이면 다음 아침 immediate 가 자동 부활한다(사이클 106 안전망 보존). 배경 = 재시작마다 basics 17분 풀런 + master 4분 이중 실행 → 아침 프리마켓 burst = 187 잔존 read 실패 33건/일 공통 뿌리. 회귀 가드 18 (`test_cycle193_immediate_fresh_gate.py` 10 + `test_cycle193_task_marker_helpers.py` 3 + `test_cycle193_ast_fresh_gate.py` 5 = F-10-1 게이트 **3** task + F-10-2 미대상 **3** task 부재) + 사이클 263 `tests/unit/engine/test_cycle263_daily_load_stub_filter.py` A 계열)
**data_load_tasks.py** (refactor-review B1, 2026-08-09 커밋 583c8a4 — scheduler.py 재비대 시정. 8 저녁 데이터적재 task loop 본체 (`scan_pool_eager_refresh_loop` / `full_universe_load_task_loop` / `stock_master_daily_load_task_loop` / `stock_master_basics_refresh_task_loop` / `stock_master_master_load_task_loop` / `stock_master_financial_load_task_loop` / `evening_funnel_capture_task_loop` / `stock_master_daily_purge_task_loop`)를 scheduler.py 에서 위임 (사이클 51/67 boot_manager/stale_manager 패턴). 각 함수 `scheduler` 인자 + `wait_time` kwarg (TIME_* 는 wrapper 가 전달 = 순환 import 회피). 모듈 `logger = logging.getLogger("src.engine.scheduler")` (운영 grep 연속성). scheduler.py 8 wrapper 2줄 위임 (`data_load_tasks.<fn>` 호출). scheduler.py 4,230 → 3,859L. 회귀 가드 `test_refactor_b1_data_load_tasks.py` (순환 import 0 + 8 함수 존재 + wrapper 위임 + <4,000L))
stock_master_metrics.py / stock_master_basics_metrics.py / stock_master_daily_metrics.py / **stock_master_master_metrics.py** (사이클 133 — 4 facade re-export only 패턴, 사이클 67 stale_manager.py 답습. 3 기존 facade 298L → 132L -166L -56% + master 39L 신규 일관성 결함 해소. 사이클 78 G-AST1 영속 — 4 flush 호출 사이트 ≥ 1 의무 scheduler.py 영역)
**stale_diagnostics.py** (사이클 135 — `SUBSCRIBE_GRACE_SECS = 180` 상수 신규 = 3.0 × STALE_FRESHNESS_SECS P95 안전 마진 정합. `stale_manager.__all__` re-export 영속. `STALE_FRESHNESS_SECS = 60` 변경 0 (사이클 17 KIS LMS chain 안전 마진 영속, G-SAFETY-1). 자문 산출물 `_workspace/domain_consult/cycle135_websocket_grace_period.md` 영속)
**stale_watcher_core.py** (사이클 135 — `check_and_resubscribe_stale` 영역 grace 가드 `_is_within_grace(t)` 영역 신규: `if t in ticker_last_tick: return False` (G-GRACE-7 사이클 29 005935 보호 직접 검증) + `ack_at not datetime: return False` (G-GRACE-6 ACK race 보호) + try/except 안전 폴백 (mock 환경 영역 = 사이클 63 Phase 2-A3 mock 회귀 가드 보존). `_ack_map_raw if isinstance(_ack_map_raw, dict) else {}` 안전 가드. 매매 안전성 무영향. **사이클 162 (2026-06-18)** — 동시호가 시간대 stale 회피 hook 신규 = `SessionTracker.is_call_auction_now()` True 시 stale 종목 전체 skip + `[stale_skip_call_auction]` WARNING 1행. 6/17 15:21:48 KST `subscribed=10 fresh=0 stale=10 ratio=0%` 5분 주기 재구독 폭주 결함 차단 — 동시호가 시간대 (08:30~09:00 ∪ 15:20~15:30) 체결 부재 = 정상. KIS LMS chain 위험 감소.) **cycle252 no_feed skip (2026-09-05)** — `check_and_resubscribe_stale` 는 `subscribed` 확보 직후 `no_feed_registry.ensure_fresh(subscribed)`(try/except) 를 부르고, 루프 안 priority 결정 직후·`retry > MAX_STALE_RETRIES` 비교 직전에 `sub_priority=="LOW" ∧ is_no_feed(t)` 면 (**cycle293 이 조건을 3항으로 좁혔다 — 아래 참조**) r 증가·r>5 홀드(`MAX+1`)만 하고 `continue`(SEND 0·스탬프 0·history 0·sleep 0). `record_stale_watcher_check` 에 `no_feed_skipped`, `[stale_watcher_summary]` 끝에 ` no_feed_skipped=%d`(기존 5필드 prefix byte 보존). `high_tickers` 계산은 `if not stale_tickers: return` **앞**으로 이동해 `[no_feed_held] tickers=[…]`(HIGH∩no_feed, WARNING 1회/일, DailyEmitCap peek→로그→mark, **예외 흡수**)를 stale 여부 무관 매 사이클 판정한다. HIGH·정상 LOW·`resubscribe_stale_priority`·`_collect_low_desired` 는 HEAD 대비 `ast.dump` 동일. 차분 기준 sha 핀 = 8b146ff(W5, shallow clone 이면 SKIP). **cycle293(2026-09-14) 갱신 3건** — ① `ensure_fresh` 인자가 `subscribed` 에서 **`subscribed ∪ 보유·익일청산`**(채널 무관 집합)으로 넓어졌다(§6-E 자기 강화 플리커 차단: 집계가 세 채널 합집합이 된 지금도 인자를 그 함수에 다시 묶으면 같은 함정이 부활한다). ② skip 조건이 3항 논리곱 = `LOW ∧ is_no_feed ∧ (킬스위치 off ∨ 실제 구독 채널 ∉ DEDICATED)` — 전용 채널로 옮긴 종목은 프레임이 **실제로 오므로 회복 가치가 생긴다**(skip 을 그대로 두면 그 채널의 진짜 stale 을 영원히 못 고친다). 킬스위치 `off` 는 판정뿐 아니라 **churn 차단까지 복원**한다(`off` 가 "오늘과 동일" 을 뜻해야 하고, 이미 옮겨진 구독은 되돌아가지 않으므로 채널 축을 보면 `off` 로 그날 멈출 수 없다). ③ ACK grace 조회 키가 `(TICK_TR_ID, t)` 고정에서 **채널 무관 역인덱스**(`ack_at_by_ticker`)로 바뀌었다 — 고정이면 전용 채널 종목만 180초 구독 grace 를 영구 miss 해 구독 직후 stale → 즉시 강제 재등록 = cycle252 가 없앤 하루 ≈14,600 SEND 폭주의 조용한 부활. ⚠️ **`no_feed_skipped`·`[stale_force_retry]`·`[no_feed_held]` 는 cycle293 전후 grep 합산 금지**(§9-B 의미 전환 — 전자 둘은 감소가 성공 서명, `[no_feed_held]` 는 S2 뒤 0 이 정상).

**session.py** (사이클 162 (2026-06-18) — `SessionTracker.is_call_auction_now(now=None) -> bool` 신규. KIS MCP 정본 H0UNMKO0 `MKOP_CLS_CODE` = 110 (장전 동시호가 08:30~09:00) / 121 (장후 동시호가 15:20~15:30) 코드 기반 인지 + 시간 기반 폴백. domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`. **사이클 182 (2026-06-28) — 시간창 게이트 (stale-1 HIGH + stale-5 LOW)**: 코드 기반 분기 `if _last_nxt_mkop_code in ("110","121"): return True` 가 시간창 게이트 없이 무조건 True + `_last_nxt_mkop_code` 리셋/전환 처리 0건 → KIS 가 "121" push 후 전환 코드 미발신 시 고착 → 15:30~20:00 NXT 애프터(또는 stuck-110 시 MAIN 09:00~15:20)에 보유 종목 stale 탐지 영구 비활성 = 손절 누락. 시정 = 코드 분기를 `code AND 명목창±5분`(110: 08:25~09:05 / 121: 15:15~15:35)으로 게이트 + `now or datetime.now(_KST)` KST 강제(stale-5). domain-expert + KIS MCP = KIS 가 코드 의미·push 트리거 미문서화 → push 신뢰 불가 → 시간창 게이트(방식 A) robust. `on_h0nxmko0` 무조건 재대입 변경 0. 사이클 162 동시호가 skip 100% 보존(진짜 동시호가창엔 코드+시간폴백 양쪽 True). 보유 stale 탐지 복원 = 매매 안전성 강화. 회귀 가드 `tests/unit/engine/test_cycle182_call_auction_time_gate.py`(23) + `tests/unit/ast/test_cycle182_call_auction_ast_gate.py`(4, 코드분기 `time()` 동반 의무 + naive now 0건) + 의미 전환 3(test_cycle162 E-1/E-2 xfail + E-10 freezegun 15:25).)

**market_operation_monitor.py** (사이클 149 — H0UNMKO0 종목별 VI/거래정지/종목상태 추적. `handler._handle_market_op` 가 `record_market_op_event(MarketOpEvent)` 호출 → `_vi_active_tickers`/`_halt_active_tickers`/`_market_op_last_event` 3 dict 갱신. `is_ticker_stale_excluded(ticker)` = stale_watcher_core 소비(VI/거래정지 종목 stale 회피). `MarketOpEvent`(`src/api/market_operation.py`) = KIS 10컬럼 전수 파싱(trht_yn/tr_susp_reas_cntt/mkop_cls_code/.../exch_cls_code). **사이클 186 (2026-06-29) — 장운영 UI + 서킷브레이커 휴리스틱 (관찰성 전용)**: `get_circuit_breaker_state() -> dict` 신규(suspected = (R)거래정지 사유 `_CB_REASON_KEYWORDS`("서킷"/"매매거래중단"/"circuit") 매칭 OR (W)`halted >= _CB_MIN_HALTED(5) AND halted/observed >= _CB_HALT_RATIO(0.8)` 전 시장 동시 거래정지 / `representative_mkop_cls_code`=005930 계측 / `halt_reasons_sample`) + `get_market_op_state_summary()` 확장(`circuit_breaker`+`iscd_stat_active_count`) + `record_market_op_event` CB 첫 발화 `[market_op_cb_suspected]` INFO DailyEmitCap 1/일(`reset_market_op_state` 동행 reset). 기존 VI·halt 추적·`is_ticker_stale_excluded` 불변. KIS H0UNMKO0 에 CB 전용 필드 부재 → MKOP_CLS_CODE/사유 휴리스틱 + 계측 우선(실CB 관측 시 정식 코드 승격). `GET /api/realtime/market-operation`(routes/realtime.py) → RealtimeHealth 5번째 카드 노출. **매수 가드 미연계(표시만)** — risk.on_tick 변경 0. ⚠️ **cycle292(2026-09-14) — 본체가 이 파일이 아니라 `market_op_subscribe.subscribe_market_operation_tickers` 로 옮겨갔다**(행위 변경 0, `scheduler.py` 에는 5줄 위임 wrapper 만 잔존). 이름 `scheduler._subscribe_market_operation_tickers` 는 그대로 실존하고 호출부(`_scan_loop`)·시그니처·예외 전파도 불변이지만, **아래 07-25·08-07·cycle230 서술의 코드는 전부 그 leaf 안에 있다** — `scheduler.py` 를 grep 하면 wrapper 2줄만 나온다. 인용된 회귀 가드 4파일도 이제 leaf 를 겨눈다(`_BODY_PATH`). **사이클 214 (2026-07-15) — H0UNMKO0 후보 구독 풀 분산**: `scheduler._subscribe_market_operation_tickers` 의 LOW 후보 루프가 `kis_ws.subscribe`(메인 단독) → `kis_ws_pool.subscribe(priority="LOW")`(보조 세션 분산) + cap 20→**60**. 유니버스 확대(203/204/208/211)로 후보 H0UNMKO0 가 메인 41-cap 초과 드롭(119건/일) 시정. cycle 149 "보조 세션 절대 금지"(의제 2)를 3중 정본으로 반증: H0UNMKO0=실시간시세 quote류(체결통보 아님) / `websocket_pool._EXECUTION_NOTICE_TR_IDS`={H0STCNI0/H0STCNI9}만 보조 차단(H0UNMKO0 미포함) / `dispatch_message` 세션무관 전역 콜백(보조가 받아도 monitor 갱신 동일). **HIGH(보유/익일청산) 는 `kis_ws` 메인 직접 + bypass_limit=True 유지**(cycle 32 R4 절대보호). 시세 tick(H0STCNT0)·체결통보(H0STCNI0 메인단일)·사이클 197 41-cap cap 불변. realtime/websocket_pool.py diff 0(기존 분배 재사용). 매매 안전성 8영역 diff 0. **⚠️ 2026-07-25 정정 — cycle214 는 배포 이래 완전 미작동(silent)이었음**: `_subscribe_market_operation_tickers` 함수-로컬 import 가 `from src.realtime.websocket import kis_ws, kis_ws_pool` 였는데 `kis_ws_pool` 은 `websocket_pool` 에만 정의(`websocket` 부재) → 매 호출 ImportError, 함수 첫 줄이라 HIGH/LOW 구독 전량 미실행. 07-15~07-24 매 `_scan_loop`(5분) 117건/일 ERROR(일일 94%). 07-24 로그분석 리뷰에서 발견 → import 2줄 분리 시정(`kis_ws`←websocket, `kis_ws_pool`←websocket_pool). 은닉 원인 = `test_cycle214_h0unmko0_pool.py::_patch_ws` 가 `websocket.kis_ws_pool` 잘못된 네임스페이스에 mock 주입(→ `websocket_pool` 정정, patch 경로 적응 3건). 회귀 가드 = `test_market_op_subscribe_import_regression.py`(런타임 delattr 로 프로덕션 부재 재현) + `test_market_op_subscribe_import_path_guard.py`(AST import 경로). 매매 안전성 = 손절/트레일링은 H0STCNT0/H0STCNI0 의존이라 직접 훼손 아님, VI/거래정지 stale 제외·CB UI 만 blind. **2026-08-07 — 닫힌 소켓 send 레이스 가드**: 진입 가드가 `_ws` 존재만 봤는데(`not getattr(kis_ws, "_ws", None)`) 재연결 레이스로 `_ws` 가 "존재하지만 닫힌"(state != OPEN) 상태이면 통과 → `send()` 에서 `ConnectionClosedError` 가 HIGH 종목마다 ERROR+traceback 폭주(08-07 11:24:57 실측 = 재연결 8초새 2회 튐 순간 HIGH 7종목 버스트, 일회성·다음 사이클 자동 복구). 시정 = 진입 가드에 `getattr(_ws_obj, "state", None) is State.OPEN` 추가(미개방 시 사이클 전체 skip + `[market_op_subscribe_skip]` INFO 1행) + HIGH/LOW 루프 `except ConnectionClosedError: break`(종목별 ERROR 폭주 → WARNING 1행, 재연결 중 예상 상태). 사용자 결정 = **realtime `_send_subscribe`(8영역 hot path, 시세·체결통보 공유) 미접촉** — scheduler 훅이 duck-typing 으로 `_ws.state` 만 읽는다(AST 가드). 회귀 `test_market_op_subscribe_socket_guard.py`(11) + mock 적응 2(cycle214/import_regression 픽스처 `_ws` = `SimpleNamespace(state=State.OPEN)`). scheduler 외 7영역 diff 0. **cycle230 (2026-08-29, cycle221 잔류 채택) — cycle214 의 'HIGH 메인 직접 + bypass_limit=True' 는 폐기**: 08-19 실사고(메인 45/41 KIS **서버** 한도 초과 → OPSP0008 117건 중 시세 7건 = 보유 4종목 ~58분 tick blind)로 `bypass_limit=True` 가 로컬 가드만 우회함이 판명, H0UNMKO0 는 매매 게이트 미연계 관찰 채널이라 tick 규칙(cycle 32 R4)의 오적용이었다. 현행 = VI 는 메인 0건, 보유+익일청산만 보조 세션 **직접**(풀 API 미경유 — tr_key 단일 키 라우팅 오염 방지) 라운드로빈 + `_market_op_subs` 추적 **델타** 해제(슬롯 누수 차단) + 후보 VI 미배치(실질 noop 이던 경로 삭제) + `[market_op_subscribe_summary]` 에 main_tick/main_total/**main_over** 5분 상시 계측(초과 시 WARNING) + 보조 만석 `[market_op_subscribe_no_slot]` WARNING(메인 폴백 금지 = tick > VI 명시적 교환). 회귀 = `test_cycle221_market_op_off_main.py` + `test_cycle221_ast_market_op_no_main.py`(4중 봉인). 잔여 후속 = 메인 헤드룸 관리(LOW tick fallback 상한).)
refresh_progress.py (사이클 127 — 3 작업 universe/basics/daily 진행 state 통합 메모리 dict + threading.Lock + 헬퍼 `start_progress` / `update_progress` / `finish_progress` / `get_progress` / `get_all_progress` / `is_running` / `reset_progress` / `reset_all_progress`. uvicorn 단일 워커 의무 + KST timestamp 영속. **사이클 129 TaskKey 4 확장** `Literal["universe", "basics", "daily", "master"]` + `TASK_KEYS` tuple 2 위치 동행 — AST 영구 가드)
util/tick_size.py(KRX 7구간 호가단위 헬퍼 — `get_tick_size` / `round_to_tick` / `step_down` / `step_up`)
market_regime.py(dkstock.cloud 매크로 → 매수 가드 + cash_usage_ratio)
**quant_score.py** (사이클 C2 — 퀀트 재무필터 순수 함수. `compute_f_score_7(curr, prev) -> int|None`(Piotroski 9지표 中 **7지표** = 현금흐름표 TR 부재로 CFO 2지표 제외, 개별 결측 미가점 / 2기 부족 fail-open None) + `compute_magic_formula(series_by_ticker, mktcap_by_ticker) -> dict`(Greenblatt EY=1/ev_ebitda 폴백 bsop_prti/EV, ROC=bsop_prti/((cras-flow_lblt)+fxas), mf_rank=ey_rank+roc_rank). DB/HTTP/시계 미접촉 순수 함수, 8영역 미접촉)
**kojiro_indicators.py** (2026-07 — 고지로 대순환 순수 지표. `ema`/`atr`(Wilder ewm(1/period))/`stage_of`(6배열+동가 유지)/`enrich`(EMA 5/20/40 + 스테이지 + 대순환 MACD1/2/3 + 밴드폭 + ATR). pandas 사용, `KojiroIndicatorConfig` 주입. quant_score 선례 = DB/HTTP/시계 미접촉 순수 함수, 8영역 미접촉. **ATR = Wilder ewm(1/20)** ≠ donchian `_atr`/`get_atr`(단순평균) — 손절선 정의 단일 진실원, 재사용 금지)

**kojiro_band_observe.py** (cycle273c, 2026-09-10 — 고지로 후보 순위 성분①② 원설계 복원의 shadow 관측 leaf. `observe_band(band_raw, ranked_final, held_only, scores=None)` 이 `[kojiro_band_observe]` 마커로 `ranked_final + held_only` 순서 1행/(ticker,role)/일 방출 — `bar`(D-1 완성봉 날짜)·`exp1`(레거시 단일봉 분모)/`exp5`(복원 직전5봉평균 분모)·`slope_raw`/`slope_pct`·`score` 등 12원소 stash + 파생 3필드(atr_pct/bw_close_pct/bw_atr)를 한 행에 나란히 남겨 복원 전후 대조. never-raise(`_band_observe_row`·`observe_band`·`absorb_band_call_failure` 전부 단일 `try/except Exception`, 실패는 `observer_trace.trace_observer_failure` 흔적) + read-only + cap=`KstDailyEmitCap`(키=(ticker,role)) — `kojiro_gap_observe.py`(cycle268) 자매 leaf, 이름만 band 계열. 소비처 = `KojiroStrategy.prepare()` 점수 확정 직후 1블록, 실패해도 매수 후보 처리(final_prepared/`_scanned_tickers`) 무영향)
recommendation_engine.py(20:00 AI자문) / **backtest_orchestration.py**(refactor-review B3, 2026-08-18 — 백테스트 오케스트레이션 5함수 `_get_backtest_engine`/`_spawn_backtest_poll_task`/`_enqueue_backtest_jobs`/`_backtest_poll_loop`/`_emit_pending_summaries` + `_backtest_poll_loop_running`/`_BACKTEST_POLL_*` 상수를 recommendation_engine 에서 위임 분리. leaf 모듈(core 미호출, 순환 0). recommendation_engine 이 module-level 재export = scheduler.py:3760 `_backtest_poll_loop_running` import·테스트 patch 경로 **동일 객체** 보존. logger 명시 `getLogger("src.engine.recommendation_engine")`. recommendation_engine 1126→657L) / log_analysis_engine.py(21:30 일일 로그 분석 — cycle283 D3, 종전 20:10)
**sector_naming.py** (2026-08-04 — 보유 종목 섹터명 해석 **단일 진실원**. `resolve_sector_name(ticker, *, basics_raw=_UNSET)` + `resolve_sector_names(tickers)`. 우선순위 = basics raw `bstp_kor_isnm`(사람이 읽는 업종 한글명) → `_kojiro_sector_key(master_raw)`(KRX 산업지수 플래그 → 업종코드) → `미분류-{ticker}`(독립 키 fail-open). `basics_raw` 주입 시 `stock_master.get` 재조회 생략(잔고 라우트 중복 fetch 방지). **추출 배경** = 동일 로직이 `routes/portfolio.py` 와 `log_analysis_engine.py` 에 이미 중복돼 있었고 `routes/balance.py` 섹터 컬럼으로 세 번째 복사본이 생길 상황이었다 — 3 소비처 전부 위임(회귀 가드가 중복 재발 차단). 행위는 사이클 H Phase 2a + 사이클 I 후속 계약 그대로 보존)
**portfolio_risk.py** (사이클 H, 2026-08-02 — 포트폴리오 리스크 관찰 순수함수. `extract_hard_stop_pct(params, *, default=-7.0)`(후보 7키 stop_loss_rate/intraday/overnight/main/pre_nxt/turtle_backstop_pct/hard_stop_pct 中 음수만 min, 결측→-7.0 fail-open, 0.0 금지) + `compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of) -> dict`(전 전략 합산 오픈 리스크. 포지션 리스크 프록시=buy_price×qty×|hard_stop%|/100, by_strategy(0포지션 포함)/by_sector(포지션有)/top_sector/open_risk_pct_of_net). **배제 0 — 입력 무변경**. DB/HTTP/시계/registry/kojiro 미접촉(quant_score 선례). 소비=`GET /api/portfolio/risk`(routes/portfolio.py, get_balance+registry+섹터 pull) + 일일리포트 metrics(`portfolio_risk_snapshot` 키). 터틀 서적 대조 감사 갭 2건(포트폴리오 총리스크 상한·전략간 섹터 집중) Phase 1 가시화. **Phase 1 관찰 전용** — 매수 차단·SOFT 상한·entry_atr 정밀화는 2주 관찰 후 Phase 2. 신규 리스크 임계 PARAM_RANGES 미편입. **세 번째 함수 `check_budget_invariant(strategies) -> list[dict]`** — `params.position_ratio × params.max_positions > 1.0 + 1e-9` 위반 목록 반환(결측/0 이하/예외 skip = fail-open). 소비 = `boot_manager` 가 `_load_strategy_config` 직후 호출해 `[budget_invariant_violation]` WARNING. **차단 아닌 관찰** — 운영자 수동 DB apply 사각을 잡는 런타임 가드다. ⚠️ 이 가드는 `position_ratio × max_positions` 축만 본다 — **Σweight ≤ 1.0 축은 보지 않는다**(2026-08-18 비중 단위 오염을 전혀 못 잡았다). Σ 축은 라우트 Σ 가드 + `[weight_config_anomaly]` 담당)
**log_metrics_collector.py** (cycle259, 2026-09-05 — 일일 리포트(21:30 — cycle283 D3, 종전 20:10)의 **수집/집계 계층**. `log_analysis_engine` 에서 byte 동일 이동한 `collect_daily_log_metrics`(반환 dict 키 집합·순서 = OpenAI 프롬프트 = `daily_log_reports.metrics` JSONB = 20:20 루틴 번들 — 고정 입력 sha 3자 일치 실증) + `_fetch_logs_in_range`·`_aggregate_*`·`_build_portfolio_risk_snapshot`·funnel 수집 + 정규식·`DAILY_LOG_FETCH_LIMIT`·`HIGH_SEVERITY_FETCH_CAP`·`KST`. `log_analysis_engine.py`(293L)는 LLM 호출·검증·저장만 남기고 위 심볼을 재export(`__all__`) — `routes/log_reports.py` import 문 무접촉이 계약(L2 텍스트 가드). monkeypatch 는 **collector 경로**로. 이관 2단계(OpenAI 은퇴)는 `log_analysis_engine.py` 삭제 범위 하나. **`account_risk_watcher.get_gate_snapshot()`**(같은 사이클) = `get_gate_state()` 8키 + `eval_timeouts_today` 복사본, 무발화 — 일일 리포트 스냅샷과 `/api/portfolio/risk` 의 **단일 소유자**(두 형상 불일치 해소), `_eval_timeout_count` 는 watcher 내부 전용)

**selling_reconcile.py** (cycle273b-F7, 2026-09-10 — `scheduler._sync_positions_from_balance` 의 stale `_selling` 재대조 블록 위임 leaf. `reconcile_stale_selling(order_engine, holdings, *, min_age_s, now=None)`: 판정 3분기 `held_zero`(보유 0)·`open_order`(KIS 일별 주문에 `sll_buy_dvsn_cd=01 ∧ rmn_qty>0`)·`too_young`(`elapsed_s < min_age_s`=180s) 은 유지 + `[selling_hold] ticker= reason= elapsed_s=` WARNING 1회/(ticker,reason)/일, 그 외 해제(WARNING 문구·`write_log` byte 동일). logger 는 `"src.engine.scheduler"` 고정(사이클 60 I1 — `system_logs` 접두 보존). `get_daily_orders` 예외는 graceful(`_selling` 유지). AST 가드 `test_cycle273b_ast_no_behavior_guards.py`)

**kojiro_gap_observe.py** (cycle268 leaf, 2026-09-09 — `[kojiro_gap_observe]` 판독 마커, cap 1회/(ticker,caller,verdict)/일, never-raise. cycle273-pre(09-10)로 14번째 필드 `ws_collapse=blocked|allowed|-`(WS 시가였다면 붕괴 가드 판정이 어땠을지 — 반사실) 순수 append. ⚠️ **cycle273e(09-11) 이후 — 경로 B(`caller=on_tick`) 행은 더 이상 발생하지 않는다**(아래 `risk.py` 사실 참조). 이 문서 문단은 cycle273e **이전**의 경로 B 행에 대한 서술로 읽는다(과거 로그 판독용, "동어반복" 함정 문구는 09-11 이전 로그에만 적용) — 오염 판정은 항상 경로 A(`_swing_buy_poll_loop`) 행만 유효했다, `ws_open` 부재 시 `-` 가 다수(정상))

**observer_trace.py** (cycle258, 2026-09-05 — 관측기 자기 실패 흔적의 단일 정책 leaf. `trace_observer_failure(marker, key, cap=None, *, now=None, dest_logger=None)` = `logger.debug(exc_info=True)` **항상** + cap 이 있으면 `f"{marker} observer_failed key={key}"` WARNING **1회/(marker, key)/일**(실패 cap 키 `marker|key__observer_failed__` — 정상 키와 비충돌), never-raise(2차 예외 흡수). `src.*` import 는 `daily_emit_cap` 뿐. 근거 = cycle237 C237-L2-1 "debug 단독은 도입 이전 무음과 구별 불가" — 종전 4방언(무음 `pass` 13 · debug 만 2 · donchian debug+WARNING 7 · wrapper pass)을 이것 하나로. `dest_logger` 는 호출자 로거 주입(donchian 의 caplog 스코프 회귀 호환). **`KstDailyEmitCap`**(`daily_emit_cap.py`, 기존 `DailyEmitCap` byte 불변 서브클래스) = KST 날짜 경계 자기 리셋(`should_emit/mark_emitted(key, *, now=None)`) + `emit_once(key, log_fn, msg, *args, now=None)`(peek→로그→mark, log_fn 예외 시 mark 안 함 + trace) — `emit_once` 는 **차기 관측 마커의 표준 진입점**이고 기존 사이트는 인라인 `should_emit/logger/mark_emitted` 구조를 유지한 채 day 필드만 제거했다(G-242-5/9·G-245-5/9 가드 그대로 유효). ⚠️ 정상 관측 서식은 byte 불변이지만 **실패 흔적 서식은 `observer_failed` 토큰으로 전환** — 배포 전후 옛 실패 서식(donchian `note='관측기 내부 예외…'`, stale_watcher_core `[no_feed_held] emit 실패`) grep 합산 금지. 잔존(8영역, 권고만) = `risk.py:244,419`·`scanner.py:388`·`kojiro.py:987`)

**no_feed_registry.py** (cycle252, 2026-09-05 — 무송출 종목 집합 leaf. `ensure_fresh(tickers, *, ttl_secs=600)` 이 `stock_master.get_nxt_tradable_map`(`= ANY($1::text[])` 1회) 로 `nxt_tradable=False` 집합을 적재(ttl 경과·미지 ticker 유입 시 전체 재조회, 예외 시 이전 집합 유지 + `[no_feed_registry_refresh_failed]` 1회/일 + `_loaded_mono` 미갱신 = 다음 호출 재시도, `None`=마스터 부재는 no_feed 아님), `is_no_feed(ticker)`·`snapshot()`·`reset_state_for_test()`. scheduler/scanner/realtime/registry import 0(AST G-252-1). 의미 = "이 종목은 H0UNCNT0 로 프레임이 오지 않는다" 이지 "구독하지 않는다" 가 아니다 — 구독·ACK 는 유지되므로 채널이 열리면 그대로 수신한다. **cycle293(2026-09-14) — 채널 리졸버가 착지해 이 집합이 `scanner.tick_tr_id_for` 의 소스가 됐다**: 소비처가 `stale_watcher_core.check_and_resubscribe_stale` **단일**에서 **둘**(+ `scanner._classify_channel`)로 늘었고, 신규 판정 2개가 붙었다 — `is_provenance_ok(ticker)`(그 행 raw 에 KIS `cptt_trad_tr_psbl_yn` 키가 있는가 = 값의 출처가 권위 있는가. `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 2,674종목에 도장하는 창에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어 09-14 실측 **2,344/3,583(65.4%)** 이 도장 상태였고 그중 **420종목은 실제로 True** 였다 — 그대로 믿으면 진짜 NXT 종목을 NXT 체결을 실을 수 없는 채널로 보낸다) + `is_classified(ticker)`(레지스트리가 **분류한 적 있는가** — `is_no_feed` 의 "모르면 False" 는 **미지**와 **송출 정상**을 같은 값으로 접어 INV-4 "판정 실패 + 보유 = WARNING" 이 구조적으로 성립하지 않게 한다. `is_no_feed` 의 극성은 건드리지 않았다). 출처 조회(`stock_master.get_nxt_provenance_map`)는 `get_nxt_tradable_map` 과 **독립 try** 다 — 한 try 로 묶으면 출처 쿼리가 실패하는 날 cycle252 의 churn 차단까지 함께 죽는다. 🔴 **구독 전에 덥혀야 한다** — `ensure_fresh` 의 호출자가 `stale_watcher_core`(120초, 인자 = `subscribed ∪ 보유`)뿐이면 **아직 구독하지 않은 후보는 원리상 분류될 수 없어** 07:59 사전 구독 코호트 전체가 판정 불가로 빠진다. 그래서 `scanner.subscribe_filtered_stocks` 가 리졸버를 부르기 **전에** 그 사이클 대상 전체로 `ensure_fresh` 를 한 번 더 부른다(AST 가드 A22 가 순서를 잠근다))

**account_risk_guard.py** (cycle233, 2026-08-29 — 계좌 SOFT Σ상한 순수 판정 leaf. `evaluate_soft_gate(open_risk_pct, *, warn_pct, block_pct) -> {level: ok|warn|block, reasons}`. **block_pct None = 다크런치**(어떤 값도 block 불가 — DB `account_risk_block_pct` 한 줄로 활성, 권고 6.0). pct None/음수 → ok fail-open. DB/HTTP/registry/scheduler import 0 — AST G-3 봉인. 임계를 발화시키려 낮추기 금지(자문 cycle232 §2.6 — 관측 경보 4% 의 발화 빈도가 유일한 학습 신호))
**account_risk_watcher.py** (cycle233 — 계좌 Σ오픈리스크 감시자. `run_account_risk_watch_once(scheduler)` = registry.all() + `get_balance()` net + 전략 `get_effective_stop_price` 주입 → `portfolio_risk` 척도 병기 스냅샷 → guard 판정 → **순간 게이트**(양방향) `is_soft_gated()`. 배선 = boot 동기 1회 + `ensure_watch_loop` 스폰 **자기 종료 루프** 5분(`_running` False 시 ≤60s 자연 종료 — **scheduler.py 무접촉**: 라인 상한 가드 <4,000L(실측 3,999)가 piggyback 을 거부해 밖으로 뺐다. cancel 목록/task_attrs 미등록이 설계). **D1 이원화** — 전략별 일일손실 플래그 절대 미접촉(AST G-4 토큰 0 봉인 = risk.py 세팅을 지우는 회귀 구조 차단). fail-open+LOUD(`[account_risk_watch_failed]`, 활성 중 실패는 `released reason=eval_failure` WARNING). 로그 = `[account_risk_gate] transition=entered`(cap 밖)/`reconfirm`(1회/일)/`released` + `[account_risk_watch]` warn/ok(1회/일). 관측 순서 = peek→로그→mark(cycle226 D-3). **cycle239 신선도 계약 (2026-09-02, 활성화 선결)** — `is_soft_gated()` 는 `_gate_active` ∧ 마지막 평가 monotonic 스탬프(`_evaluated_mono`, 성공·실패 공통·`_now_mono` seam) 경과가 `_GATE_STALE_MAX_SECS`(=3×주기 900s, 리터럴 금지 G-239-1) 이하일 때만 True — **초과(stale)·미평가 None·판정 예외 전부 fail-open(False)** 이고 소비자 경로가 관측하면 `[account_risk_gate] released reason=stale` WARNING(cap `gate_stale` 1회/일 — F5 명시 예외: read 경로라 전이 엣지 부재. 기록자 `run_account_risk_watch_once` 는 **원시 `_gate_active`** 만 읽어 이 cap 을 선소비하지 않는다, R1). `get_gate_state()` 는 `stale/age_secs/stale_max_secs/effective_gated` 4키를 더하되 `level` 은 마지막 평가값 보존·무발화(동결 서명 = `level=block ∧ stale ∧ !effective_gated`), 단일 기록자 계약(read 함수 `global` 금지 G-239-4 · `_gate_active` 대입↔스탬프 사이 await 0 G-239-5) + `ensure_watch_loop` done_callback(`[account_risk_watch_loop_died]` WARNING / `_loop_exit] reason=running_false` INFO 매일 1건 = liveness 표본). 운영 복구 = `POST /api/trading/restart`. **cycle250 평가 타임아웃 (2026-09-05, 후속 A 종결)** — 루프·부팅 동기 1회 모두 `run_account_risk_watch_once_guarded`(`asyncio.wait_for`, `_EVAL_TIMEOUT_SECS=300` 리터럴 1곳 · 런타임 부등식 `0<T≤_WATCH_INTERVAL_SECS<_GATE_STALE_MAX_SECS`) 를 호출한다 — hang(KIS 세마포어·asyncpg acquire) 이 300s 를 넘으면 **TimeoutError 만** 포착해 원시 `_gate_active` 를 읽고 `_gate_active=False` + `_evaluated_mono` 스탬프(await 0) + `level=error reasons=[timeout]` + 활성이었으면 `released reason=eval_timeout` WARNING(cap 밖) + `[account_risk_eval_timeout] timeout_secs= count=` WARNING 1회/일(cap 키 `eval_timeout` 독립, 카운터는 cap 무관). `CancelledError` 동반 포착 금지(외부 취소는 그대로 전파, AST) · `run_account_risk_watch_once` 본체 무변경(AST 가 `ast.dump` 동일 검증) · 부팅 hang 은 종전 무한 → ≤300s. `[account_risk_eval_timeout]` 0건이 정상 — 1건이라도 있으면 그 자체가 hang 실측(후속 B 재스폰·E acquire 타임아웃의 근거). **cycle251 관측 노출 (2026-09-05, 후속 F·G 종결)** — `log_analysis_engine._build_portfolio_risk_snapshot` 이 `account_gate`(= `dict(get_gate_state())` + `eval_timeouts_today`) 를 over_cap 과 **독립 try** 로 붙인다(실패 시 키 미부착, `is_soft_gated` 호출 금지 — read 경로가 stale cap 을 선소비하면 안 된다, AST g251_1a). 이 dict 는 `collect_daily_log_metrics` → `metrics.portfolio_risk_snapshot` 으로 OpenAI 프롬프트·JSONB·20:20 루틴 번들에 실린다(리포트 생성 시점 프로세스 값). 프론트 `PortfolioRiskCard` 는 `/api/portfolio/risk` 의 `account_gate` 를 배지로 표시(차단 중/경고/정상 + STALE N분 전 + KST HH:mm) — 장중 `age_secs` 실측의 유일 채널. **cycle259** — 두 소비자 모두 `get_gate_snapshot()`(9키) 하나를 쓴다. 소비처 = `StrategyBase._account_soft_gate_blocked`(7전략 check_buy_signal — **위치 이원화**: 폴/래치형 5전략 첫 문장 / momentum·VB 는 **발사 직전**(최상단이면 block 구간 baseline 동결 → 해제 후 거짓 돌파, 적대 검증 C233-F1) — 청산·손절 경로는 구조적으로 차단 불가능. 드로다운 정지선(−10/−20/−30 일 래칫)은 다음 사이클 — 입출금 보정 선행 필수)
**uptime_monitor.py** (cycle234, 2026-08-29 — 프로세스 가동 하트비트 + 부팅 tick blind 계측, G2 대체 조치 ①. 60s 하트비트(`system_config.set_task_last_success("engine_alive_heartbeat")` — 사이클 193 마커 인프라 재사용, 신규 테이블 0) + 부팅 시 `[tick_blind_boot] downtime_secs=… market_blind_secs=…`(평일 09:00~15:30 겹침 — 공휴일 미고려 근사 = 과대계상 보수 방향. **market>0 = WARNING** = 장중 다운 손절 사각 실측). 배선 = boot_manager 가 갭 보고 1회 + `ensure_heartbeat_loop` idempotent 스폰(자기 종료 루프 — scheduler 무접촉, watcher 선례). 일일 리포트 metrics `tick_blind` 집계(`_aggregate_tick_blind`). **`market_blind_secs` 주간 분포 = cycle232 G2(서버 스탑) 재검토의 정량 분자** — 0 수렴이면 서버 스탑 편익도 0. WS 재연결 blind 는 stale watcher 소관(중복 금지). never-raise 관측 전용)
**ta_indicators.py** (사이클 G, 2026-08-02 — RSI/상대강도 순수함수. `rsi(closes, period=14) -> float|None`(Wilder 평균, all-gains→100/all-losses→0/flat→50, len<period+1→None) + `relative_strength(stock_closes, index_closes, period=20) -> float|None`(종목 N일 수익률 − 지수 N일 수익률 %p, 양수=지수 초과 강세). **시리즈 ASC(과거→최신) 기대** — `get_recent_daily` DESC 는 호출자가 역순 변환. quant_score 선례 = DB/HTTP/시계 미접촉 순수함수, 8영역 미접촉. **⚠️ kojiro_indicators ema/atr 재사용 금지**(ATR 이원화). 소비=VB `_apply_rs_rsi_observe_in_prepare` 진입 품질 관찰(Part B, 배제 0))
**te_metrics.py** (사이클 F, 2026-08-02 — TE/RR 전략 지표 순수함수. `compute_te_rr(pairs, *, now, window_days=90, strategy_id="") -> TeRrMetrics`(19필드). 입력=`get_trade_pairs` 출력(진입가 기준 profit_rate·왕복·미실현분리). 모집단=status=='closed'∧sell_date≥now−window_days(청산일 윈도우, open 제외). **te_pct=profit_rate 단순평균**(compute_metrics 매도가 기준 재사용 금지) / win_rate=W/N(보합 포함 분모) / rr=avg_win/|avg_loss|(전승 or min(W,L)<5 → None) / **required_rr=L/W**(서적 (1−승률)/승률 은 보합=0 특수해) / 동치 TE>0⟺RR>필요RR / 표본 게이트 sample_tier(N<20/20-49/50+) + rr_available(min(W,L)≥5) + verdict(undecided/superior/inferior/flat) + structure_tag(N≥20∧rr_available: 저승률·고RR robust/고승률·저RR fragile/balanced) + single_trade_dominant. quant_score 선례 = DB/HTTP/시계 미접촉 순수함수, 8영역 미접촉. 소비=`GET /api/strategies/te`(routes/strategies.py, 5분 캐시). 관찰 전용)
**turtle_sizing.py** (Phase 2A, 2026-07~08 — 터틀식 유닛 자금관리 **순수 함수**. `compute_unit_qty(budget, atr, risk_pct, fraction=1.0)` = `floor(예산 × risk_pct ÷ ATR)` + `compute_unit_qty_guarded(...)` = 변동성 floor(`atr/price < min_vol_pct` → 0 = `position_ratio` 낙하) + 잔여예산 클램프 + **notional 상한**(`min(qty, int(예산×position_ratio)//price)`). 그 notional 상한이 "**터틀 수량 ≤ 비중 수량**" 을 항등으로 만들어 cycle245 ρ축 캡이 사이즈드 랏에 무접촉인 근거다. DB/HTTP/시계 미접촉, 8영역 미접촉 — 호출은 전략 파일 `calc_buy_quantity` 뿐. **cycle242 `max_lot_units`(K축) 캡 산출도 이 함수를 `fraction=K` 로 재사용한다**(새 수식 금지))
**tick_volume.py** (cycle227, 2026-08-25 — 실측 누적거래량 관측 **leaf**. P0-1 시정 배관: BFB/VCP 매수 최종 관문이 `scanner.ticker_prices[t]["acml_vol"]` 를 읽는데 그 키의 **대입부가 전 소스에 없어** 두 전략이 구조적으로 매수 불가였다. WS payload `[13] ACML_VOL` → `handler._parse_acml_vol` → `on_tick(*, acml_vol=)` → 이 모듈이 기록. cycle228 이 게이트를 실측 + 충족 래치 + 추격 상한으로 전환하며 매수를 열었다. 🔴 **`acml_vol` 은 채널마다 따로 쌓인다 — 채널이 다른 두 값을 비교·합산하지 않는다.** 2026-09-14 라이브 실측: 같은 `000660` 이 `H0STCNT0`(KRX) 16:41 에 **3,773,544**, `H0NXCNT0`(NXT) 19:55 에 **1,981,520** 이었다. `record_acml_vol` 은 last-write-wins 이라 cycle294 의 채널 전환 뒤 첫 프레임이 새 채널의 누적값으로 **덮는다** — 그 자체는 의도한 동작이다(KRX 거래량 게이트는 KRX 누적을 봐야 한다). 전환이 안전한 이유는 전환 창에 프레임이 구조적으로 0 이고(NXT 휴장 + KRX 시가 단일가) 이중 채널 구독을 금지하기 때문이다 — 그 둘 중 하나가 깨지면 last-write-wins 가 두 누적을 번갈아 쓰는 비결정론이 된다)
**backtest_yaml.py** (Phase 2, 2026-05 — 6 전략 → 외부 MCP 백테스트 서버 YAML DSL 변환. 소비 = `backtest_engine.py`(20:00 자문 직후 12 job fire-and-forget) + `routes/backtest.py`. 매매 hot path 무관)
**open_price_observe.py** (cycle264, 2026-09-07 — 시가(`[7] STCK_OPRC`) 스코프 shadow 관측 **leaf, 행위 변경 0**. 09:05:30 에 VB·LTV `main` 보드의 `used_open`(그날 목표가를 만든 값) vs KRX REST `stck_oprc` 를 `[open_source_compare]` 로 나란히 남겨 익일 `stock_master_daily` 까지 **3자 대조**를 가능하게 한다. throttle 5건/초, 1회/(ticker,strategy)/일, read-only(`_targets`/`_open_confirmed` 무변경). `scheduler.py` 라인 상한(<3,900) 때문에 leaf 로 분리했다 — cycle233/234/259 위임 선례. ⚠️ 이 사이클은 **관측만**이고 시정(`[7]` 에 `[24] OPRC_HOUR` 스코프 필터)은 미완 = cycle265)
**kojiro_gap_observe.py** (cycle268, 2026-09-07 — 고지로 갭 판정 오염 shadow 관측 **leaf, 행위 변경 0**. `observe_gap(ticker, verdict, *, arg_open, prev_close, current_price, params, depth=2)` 가 `[kojiro_gap_observe]` 1행에 실제 판정(`arg_open` 경로)과 WS 캐시 반사실(`ws_open` 경로)을 나란히 남긴다 — 경로 A(`_swing_buy_poll_loop`, KIS REST 시가=깨끗)·경로 B(`risk.on_tick`, WS 프리장 시가=오염 가능)가 같은 함수를 같은 인자명(`open_price`)으로 불러 로그만으로는 구별이 안 되던 것을 `caller`(`sys._getframe(depth)`, 미지 호출자는 원문 그대로) 로 식별한다. cap = `KstDailyEmitCap[(ticker, caller, verdict)]`. ⚠️ **경로 B 행의 `ws_*` 필드는 오염 판정에 쓸 수 없다** — `risk.py:495` 가 `check_buy_signal` 호출 전에 인자와 **같은 값**을 캐시에 먼저 쓰므로 `ws_cmp=ws_eq` 가 산술적으로 보장된다(cycle264 `used_src=rest → delta_bp=0` 동형 함정). 오염 판정 = `caller=_swing_buy_poll_loop` 행 + 명세 §5 오프라인 조인만 유효. **cycle273-pre (2026-09-10, 자문 `cycle273_kojiro_gap_gate_20260910.md` §3.4(다)) — `ws_collapse` 필드 추가**(기존 13필드 순서·서식 byte 불변, 순수 꼬리 append — cycle264 `truth_confirmed`/`truth_total` 추가 선례 동형) = `ws_open` 이었으면 붕괴 가드(`kojiro.py:891 current_price<open_price`)에 걸렸을지 반사실(`blocked`/`allowed`/`-`, `ws_open` 부재·0·음수는 `-`) — 기존 `ws_verdict` 는 **갭 게이트만** 재현해 판독에서 실제로 뒤집힌 유일한 관문인 붕괴 가드는 관측 밖이었다. 같은 구조적 이유로 경로 B 행에서는 이 필드도 실제 붕괴 판정과 항상 일치(동어반복))

**quote_token_refresh.py** (cycle269, 2026-09-08 — 보조 시세 계정 접근토큰 **장 마감 후 고정 시각 강제 재발급 leaf**(현재 19:00, cycle270-C). `refresh_quote_tokens_once()` 가 `kis_quote_accounts.list_accounts(active_only=True)` 순회 → 계정별 `TokenManager.revoke()` → `issue()` **순차** 호출(**cycle270, 2026-09-10 정정** — 캐시 hit 면 no-op 인 `get_token()` 도 아니고 `issue()` 단독도 아니다: KIS 는 유효 토큰이 있으면 **같은 토큰·같은 만료를 반환**하므로 폐기가 선행돼야 **만료 앵커가 이동**한다. 09-10 D+2 실측 = cycle269 의 issue 단독 21:30(cycle270-B, 종전 15:45) 강제 발급 14/14 이 장중 자연 발급과 동일 만료 → 효과 0 · 사용자 승인 하 `fire` 1계정 revoke→issue 는 만료 +24h 이동), `task_loop()` 는 `run_periodic_task_loop(immediate_first_run=False)` 위임. 배경 = `_is_valid()` 의 **10분 선제 갱신 마진**이 보조 계정(종일 시세 REST 사용)에서 매일 재발급 시각을 10분씩 앞당기는 **단조 드리프트**(EC2 3일 실측 09-06 15:07 → 09-07 14:58 → 09-08 14:48, 자기 안정화 없음 ⇒ ~5주 뒤 장 시작 전 진입). 시정은 `src/auth/token.py` **무접촉**(AST G-269-6 이 `_is_valid` 소스 sha 핀) — 매일 고정 시각에 `revoke()`→`issue()` 페어를 부르면 그 시각이 새 24h 창의 앵커가 된다(~~`issue()` 단독~~ 은 앵커를 옮기지 못한다 — cycle270 정정). revoke 실패는 WARNING 1행 후 issue 를 계속 시도(무토큰 방치 금지), `failed` 카운터는 issue 실패 전용, `revoke()` 는 전역 issue lock·61s gap 을 소모도 우회도 하지 않는다. **시각 = 19:00 KST**(cycle270-C, 2026-09-10 밤 — 사용자 요구 "20:00 이후" 로 21:30 을 골랐던 cycle270-B 는 스케줄러 루프 생존 창(~20:10) 밖이라 무발화였고 같은 밤 19:00 으로 재이동; 아래는 종전 15:45 를 고른 근거로 기록만 남긴다): 정상 상태의 자연 재발급 문턱은 **T−10분**에 오므로 T 뿐 아니라 T−10분도 KRX 마감(15:30) 뒤여야 요구('장마감 후')가 성립한다 — 15:35 은 문턱이 15:25 = 장중이라 탈락(가드 C9 가 이 불변식을 잠근다). 7계정 × 61s 직렬화 ≈ 15:45~15:52 로 16:00 일봉 적재 전 완료. **대상은 보조 계정뿐** — 주계정(`label=None`, 매매용)은 무접촉(재기동 시각에 묶여 있고 D6 로 이미 장외 한정). **WS 무영향** — WS 는 별도 엔드포인트 `/oauth2/Approval` 의 `approval_key` 로 접속·구독하며(`realtime/websocket.py:213`→`:603`) `issue()` 는 그것을 건드리지 않는다. 계정 단위 예외 흡수(`_preissue_all_tokens` 패턴), `immediate_first_run=False`(부팅 즉시 실행하면 부팅 시각이 앵커가 되어 설계가 무너진다). 마커 `[quote_token_refresh]` 3종 = `scheduled at=`(배선 카나리아) · `label=… issued expired=… revoked=True|False`(계정별 — cycle270 이 ` revoked=` 꼬리 추가, 접두 byte 보존; `revoked=False` = 그 계정은 이번 회차 앵커 미이동) · `accounts=%d issued=%d failed=%d`(회차 요약, **3필드 불변**). **D+1 판독(cycle270)** = 15:45~16:00 `[token] 분당 한도 대기: label=` ≥8건이면 라운드가 16:00 일봉 적재를 침범(`_scan_loop`·16:00 적재가 같은 quote pool·같은 전역 issue lock 을 쓰므로 계정당 ≤61s 무토큰 창에 요청이 떨어지면 `get_token()` herd) · 요약 행 시각 ≤15:52 · 배포 D+2 부터 장중 자연 재발급 0건이 성공 서명. `scheduler.py` 배선은 **2줄**(import + `create_task`) + cancel 목록 3곳 등재 — 라인 상한 <3,900 때문에 본체는 leaf)

**open_price_rest.py** (cycle272, 2026-09-10 — VB·LTV `main` 목표가 기준가를 KRX REST 로 확정하는 **행위 leaf**(cycle264 `open_price_observe.py` 와 반대 — 목표가를 실제로 세운다). 좁은 목 `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")` — `reject_untrusted_main_basis(params, board, source, …)` 가 `board=="main"` ∧ `source ∉ ("rest",)` ∧ `resolve_mode(params)=="enforce"`(전략별 `DEFAULT_PARAMS["open_price_scope_mode"]`, 기본 `enforce`, `"off"` 만 롤백)일 때 조용히 거부한다. `source` 기본값이 불신 `"ws"` 라 WS 3 호출부(스케줄러 1차 폴링·전략 인라인 확정)는 **한 글자도 안 바뀐다**(`check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` byte 동일 = cycle264 `_STRATEGY_PINS` 6개 불변). **09:00:35 R1** → 30초 간격 **fast 19라운드**(마지막 09:09:35, `round_schedule()` 순수 함수 — cycle276 후속 A-2 가 9→19 로 늘렸다: 종전 마지막 fast 09:04:35 와 첫 slow 09:09:35 사이 5분을 메우는 주체가 없었다. `owns_board` 는 09:05:00 에 스케줄러로 이관하지만 스케줄러의 재시도 경로 `_confirm_breakout_open_prices_if_pending` 은 `_scan_loop` 안이고 그 루프는 **09:30**(`TIME_SCAN_START`)에 시작한다. 09-11 실측 노출 0건이었으나 구조적 구멍. 이관 시각 09:05:00 은 불변이고, 그 뒤 leaf·스케줄러가 같은 종목을 중복 조회해도 라운드 대상이 `_pending_main_tickers` 뿐이라 무해하다) → 이후 **300초 간격 slow 라운드** 15:20 까지, `main_rest_basis_task_loop(sched)` 가 일정을 순서대로 대기하며 `run_main_rest_basis_round(sched, round_no=, total_rounds=, kind=)` 호출. 대상 전략 `select_strategies(registry)` = `main ∈ tradable_boards ∧ mode=="enforce"`(`config.enabled` 미고려 — D-9, 09-10 17:07 VB·LTV `enabled=False` 여도 REST 확보·게이트·부하 검증 가능). 종목 간 `sleep(0.05)`, 라운드 벽시계 상한 45초(`truncated=1`). 확정 시 `on_open_price_confirmed(..., source="rest")` **와** `open_price_observe.mark_confirmed_via_rest` 둘 다 호출. `owns_board(strategy, board, *, now=None)` = `board=="main" ∧ mode=="enforce" ∧ now < 09:05:00`(예외 fail-open False) — `scheduler._confirm_breakout_open_prices` 가 이 창 동안 그 전략을 대상에서 빼고(S3), 09:05:00 이후는 스케줄러의 기존 2차 REST 폴백이 `source="rest"` 로 백스톱(S4). 마커 4종(`[main_rest_basis_config/round/confirmed/unresolved]`, `KstDailyEmitCap` + `observer_trace.trace_observer_failure`) — `config`(1회/(전략,모드,emitter)/일, 값-민감) / `round`(전략별, fast 항상·slow는 pending>0 일 때만) / `confirmed`(1회/(전략,종목)/일, `scanner.ticker_prices` REST 조회 **직전** shadow 병기 — `ws_open`/`ws_src`/`delta_bp`/`target_rest`/`target_ws`, cycle264 `[open_source_compare]` 의 산술 항등 붕괴를 대체하는 오염 규모의 새 정본) / `unresolved`(1회/(전략,종목)/일, 마지막 fast 라운드 직후 — 커버리지 손실 정본. ⚠️ cycle276 후속으로 그 발화 시각이 **09:04:35 → 09:09:35** 로 이동했다: 배포 전후의 unresolved 행 수를 같은 코호트로 합산 금지). `scanner.ticker_prices` **읽기 전용**(8영역 무접촉). `scheduler.py` 배선은 순증 **+1행**(import 합류 + task 생성 1줄 + owns_board 조건 인라인 + source="rest" 인라인 + cancel 목록 3곳 등재, 라인 상한 <3,900 때문에 본체는 leaf) — cycle264 `_open_source_compare_task` 생성부를 cycle269 1행 스타일로 접어 예산을 확보했다. 자문 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`)

**llm_buy_gate.py** (cycle274 → **cycle276**, 2026-09-11 — VB·LTV **매수 주문 접수 시점** LLM 평가 **shadow leaf**. 진입점 = `observe_order(*, strategy_id, ticker, order_no, order_kst, order_price_won, ordered_qty, order_division, order_path, exchange, current_price_won, budget_total_won, budget_remaining_after_won, open_positions_n, params_snapshot, buy_signals_tail)` — **키워드 전용·동기·never-raise·`await`/DB/HTTP 0·반환 항상 `None`**. cycle274 의 `observe_signal`(신호 시점)은 **소스에 존재하지 않는다**(이름·시그니처 전부 삭제) — 전략 파일에는 훅이 없다 — 소비처는 **`order_engine.execute_buy` 의 매수 `place_order` 성공 직후 매핑 등록 블록 끝 2곳**(주 경로 · 시장가 거부 지정가 5호가 폴백)이며 `_insert_pending_buy_or_absorb_race` **앞**이다. 비용 순서 = `mode(off|shadow, 그 외 off) → [llm_gate_config] 카나리아(off-return 앞) → off 즉시 return → order_no 유효성(빈 값 = `[llm_eval_persist] reason=empty_order_no` 1행 후 return) → 래치 peek(키 = **주문번호**/일, cycle274 의 (전략,종목) 아님 → 같은 종목을 하루 두 번 사면 두 번 평가) → 일일 cap peek(`[llm_gate_daily_cap]` WARNING 1회/전략/일 + `[llm_eval_persist] reason=cap_exceeded` **주문별 1행**) → 값 복사 payload → 래치 mark + cap 증가 → `asyncio.create_task(_evaluate)` 정확 1회 → None`. `_evaluate` 는 `_evaluate_core` 의 outcome 을 받아 **단 1곳**에서 `_persist_evaluation` 하고(성공·실패 **모두** `llm_buy_evaluations` 1행 — 실패도 `input_payload` 를 담고 `score=NULL`), `_evaluate_core` 는 세마포어 2 안에서 `db.stock_master_daily.get_recent_daily_normalized`(캐시 `(ticker, KST date)` 상한 400, 당일 봉 폐기, 60봉 fetch → 프롬프트에는 30봉) → `llm_features.compute_technicals`/`build_messages` → `AsyncOpenAI.chat.completions.create`(`settings.openai_buy_gate_model`, `response_format=json_object`, `wait_for` 타임아웃) → 출력 검증(클램프 금지, `int(inf)` OverflowError 흡수) → outcome. **`_MAX_COMPLETION_TOKENS=2000`**(cycle276 후속 A-1) — `gpt-5.6-luna` 는 추론 모델이라 추론 토큰이 이 한도를 함께 소비한다. 종전 400 은 실측 여유가 30 토큰뿐이어서 09-11 실전 2건이 `content=""` → `schema_error` 로 전건 실패했다(같은 프롬프트 재현: 250·150 은 `finish_reason="length"`·content 0자, 400 은 stop·270자, 3000 은 stop·218자). 과금은 실제 사용량이라 **비용은 오르지 않는다**. 한도 소진은 `schema_error` 가 아니라 신규 **`reason=truncated`** 로 분류한다(파싱이 실패한 경우에만 재분류 — 완전한 JSON 이면 점수를 살린다). `asyncio.CancelledError` re-raise. 마커 **5종** = `[llm_gate_config]` · `[llm_buy_score]`(`order_no=`·`order_kst=`·`order_price=`·**`post_order_drift_bp=`** — cycle274 `slip_bp` 와 부호 **의미가 반대**(이제 + 는 주문 뒤 상승 = 이득)이라 **배포 전후 로그 합산 금지**) · `[llm_buy_score_failed] reason=` **10종**(+`finish=` = OpenAI `finish_reason` 원문, LLM 호출 전 실패는 `-`) · `[llm_gate_daily_cap]` · **`[llm_eval_persist] order_no= result=ok|error [reason=]`**(DB 무음을 깨는 유일 채널). 보드는 세션 트래커가 아니라 **시계**(`_board_by_clock`, 8영역 무참조), 계좌번호는 leaf 가 `settings` 에서 읽는다(order_engine 은 계좌를 모른다). 회고 층화 2열 = `_prompt_version()`(SYSTEM 프롬프트 + user 프리앰블 + `llm_features._SNAPSHOT_KEYS` 의 sha256 앞 12자) / `_feature_version()`(`compute_technicals` 출력 키 집합) — 계산 실패는 `""` fail-open. 8영역 중 `order_engine.py` 만 접촉(A-ATOMIC 구간 byte 동일)·scheduler 무접촉. 킬스위치 `llm_gate_mode=off`(PUT 즉시). 영속 = `src/db/llm_buy_evaluations.py` + migration 043, 조회 = `src/routes/llm_evaluations.py`. 자문 `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md` + `_workspace/domain_consult/cycle276_order_time_llm_20260911.md`, 명세 `_workspace/red/cycle276_order_time_llm_eval_spec.md`)

**llm_features.py** (cycle274 → cycle276 — 순수 함수 leaf, `src.*` import 0: `ema`(시드=첫 period 단순평균)·`rsi_wilder`(완전 평탄=50)·`macd`·`atr_wilder`·`hv_annualized`(ddof=1×√252×100)·`channel`·`normalize_volume_ratio`·`pct_change`·`sanitize_text`(개행·`|` 제거, 종목명 20자, 주입 방어)·`compute_technicals(bars_desc, *, current_price, today_open_won=0)`·`build_messages(payload, tech, bars30)`(§4 프롬프트 verbatim, 스냅샷은 §3.3 **화이트리스트 `_SNAPSHOT_KEYS`** 로만 조립 — 설정값·datetime 이 모델에 새지 않고, `json.dumps` 는 try 밖 = 조용한 `{}` 폴백 금지 — 실패는 leaf 가 `reason=payload_error` 로 남긴다). **cycle276 스냅샷 스키마 이동** = `signal_kst`→`order_kst` · `price_won`→`order_price_won` · `prev_price_won`/`target_offset_won` **제거**(주문 시점 복원 불가 → 영구 null 이 SYSTEM 프롬프트의 "결측 3개 이상이면 score ≤ 50" 규칙에 걸린다) · 주문 스냅샷 3키(`order_division`/`order_path`/`exchange`) 추가 · `meta.schema_version="cycle276.1"`. `_SNAPSHOT_KEYS` 를 바꾸면 `llm_buy_gate._prompt_version()` 해시도 함께 바뀐다(층화 키 정합 — 가드 `test_c30_2b/2c`). 단가 상수는 `log_analysis_engine.py` 와 이원화(후속 F-274-3))

**market_state.py** (cycle282, 2026-09-12 — 장운영상태 화면의 **단일 정본**. 순수 데이터 leaf(`src.*` import 0 · I/O 0). `MARKET_TABLE` 13행(KRX K1~K7 · NXT N1~N6)이 시각 구간마다 `order_divisions`(그 시장이 받는 호가유형)·`phase`·`effective_from/to` 를 담고, `ORDER_DIVISIONS` 28코드가 코드별 명칭·거래소 지원·`confidence` 를 담는다. **날짜 차원이 내장**돼 있어 2026-09-14 제도 변경이 `effective_from` 으로 자동 전환된다 — 그래서 09-14 이전에 배포해도 그날까지 행위 변화가 0이다(cycle287 이 이 성질에 기댄다). 소비처 = `GET /api/market-state`(`routes/market_state.py`) 화면 + **cycle287 의 시각 라우팅** (`order_engine._route_exchange_by_clock` 가 이 표만 읽는다 — `order_engine.py` 안에 시각 리터럴 0건이 계약이다). ⚠️ **이 파일을 바꾸면 픽스처 동기 사슬이 딸려 온다** — `python tools/test_fixtures/gen_market_state_fixture.py` 를 다시 돌리지 않으면 `test_cycle282_fixture_sync.py::test_i1/i2` 가 붉어진다(설계된 강제다. 픽스처가 라우트를 흉내낸 것이 되지 않도록 생성기가 라우트를 직접 호출한다). **cycle289(2026-09-13)** — NXT GTP `27~29` + KRX 애프터마켓 `41~47` **10개 코드의 개별 명칭 확정**(`confidence` `name_unconfirmed` → `confirmed`). 출처 = KIS 공지 2026-09-09(시행 09-14), `docs/kis/domestic-stock-order.md` 의 `ORD_DVSN` 칸과 같은 값이어야 한다. **cycle287b(2026-09-13)** — `FINDINGS` 의 "현재 전 주문이 SOR 이므로" 가 cycle287 배포로 거짓이 되어 시정 + SOR 폐기 각주 1행 추가(총 3행). 🔴 **`EXCHANGE_ORDER` 에서 SOR 열을 지우지 않는다** — 이 표는 "우리가 어디로 주문하는가" 가 아니라 "KIS 가 그 호가유형을 그 거래소에서 받는가" 의 사실 표다. 열을 지우면 `41~47` 의 SOR 지원이 **확인 필요**라는 사실까지 화면에서 사라져 cycle282 의 "미확인을 미지원으로 접지 않는다" 를 정면으로 깬다(가드 `test_cycle287_sor_retired.py::test_n4`/`test_n4b`). 우리가 안 쓰기로 한 사실은 열 삭제가 아니라 **각주**로 적는다). **cycle285(2026-09-13)** — 같은 화면에 "오늘 야간작업 현황" 섹션이 추가됐다. 신규 로직은 이 leaf 가 아니라 **읽기 전용 신규 라우트** `GET /api/market-ops`(`routes/market_ops.py`)에 있다 — `src/engine/` 에 신규 파일이 생기면 `test_cycle287_ast_scope.py::test_s1b` 가 붉어지고(`src/**/*.py` 트리 파일 수 핀 `_SRC_TREE_FILES` + `_SRC_TREE_DIGEST`), 이 leaf 자체는 sha 로 핀돼 있어 손대지 않았다(읽기만). ⚠️ **신규 파일 차단을 `_PINNED_DIRS`/`test_s1d` 로 인용하지 마라 — 그 가드는 공허하다.** 비교 양변(`found` = 디스크 rglob, `pinned` = `_tree_digest()` 역시 디스크 순회)이 모두 디스크에서 만들어져 **항상 참**이다. cycle292 가 실제로 신규 leaf 를 추가했을 때 `test_s1d` 는 통과했고 `test_s1b`·`test_g290_3`·`test_a8` 셋만 붉어졌다(2026-09-14 실측). 시각은 `scheduler.TIME_*`/`quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` 를 그 라우트가 직접 import 해서 읽는다 — 이 표는 관여하지 않는다. 상세 = `src/routes/CLAUDE.md`

**param_catalog.py** (cycle278, 2026-09-11 — 7 전략 `DEFAULT_PARAMS` 합집합 **101 키의 단일 진실원**(cycle290 이 `order_exchange_clock_mode`·`after_market_exit_division` 2키를 추가해 99→101, `group="time_board"` · `risk="identity"` · `range_src="enum"` · `auto_tunable=False`), 순수 데이터 leaf(`src.*` import 0 · I/O 0 · 모듈 로드 부작용 0). 키마다 `ParamSpec`(label_ko/group/type/min/max/step/unit/editable/risk/auto_tunable/deprecated/deprecated_for/range_src/pattern/choices/applies_to/help/**min_items**/**forbidden_choices**). **범위를 지어내지 않는다** — `range_src` ∈ clamp(읽는 쪽 하드 클램프 6) · param_ranges(`PARAM_RANGES` 원문 복사 23) · sign(부호 규약 6) · structural(자료형·구조 필연) · enum(값 집합) · **none(근거 없음 → min=max=None, 9키)**. ⚠️ 범위를 `PARAM_RANGES` 에서 **파생시키면 즉시 무매매 사고** — `max_scan_stocks` 는 PARAM_RANGES 상한 500 인데 bfb·vcp·kojiro 기본값이 4000 이라 파생하면 아무것도 안 바꾸고 저장만 눌러도 3 전략이 422 다(그래서 이 키만 `range_src="none"`). `auto_tunable` 은 `PARAM_RANGES` 를 **그대로 반영**하고 그 집합을 넓히지 않는다(AI 자동 조정 가능성과 사람의 편집 가능성은 별개). `deprecated`(8, 전부 `editable=False`)는 **숨기지 않고** 회색 배지로 보여 준다 — 값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다. 전략 한정 무효는 전역 플래그가 아니라 `deprecated_for`(유일 사례 `k_value_nxt_pre/_post` → VB. LTV 는 야간 목표가에 **실제로 곱한다**). **`min_items`**(list_str 최소 항목 수 — `tradable_boards`=1 · `exclude_tickers`=0) 와 **`forbidden_choices`**(전략별 금지 선택지 — 유일 사례 VB + `post_nxt`, 루트 `CLAUDE.md` 의 'POST_NXT 추가 금지' 조항을 데이터로 옮긴 것)는 검증과 화면이 같은 근거를 읽게 하려고 카탈로그에 둔다 — 화면에 규칙을 적으면 카탈로그가 둘이 된다. ⚠️ 빈 목록을 **자료형 단위로** 막지 않는 이유 = 빈 목록의 뜻이 키마다 정반대다(`exclude_tickers=[]` 는 '제외 없음' 이라는 정상 기본값))

> **cycle287b (2026-09-13)** — `exchange` 의 `SOR` 선택지를 `Choice(deprecated=True)` 로 표시하고 라벨을 `"SOR (폐기 — 주문에 쓰이지 않음)"` 으로 바꿨다(사용자 결정 2026-09-12 "SOR 내용들 UI에서 일단 걷어내자"). ⚠️ **어휘에서 지우지 않았다** — 당시(2026-09-12) 운영 DB 7 전략이 전부 `SOR` 이었고 그 값의 마이그레이션은 별도 승인 대상이라, 어휘를 먼저 좁히면 그 값을 **명시 저장**하는 경로가 422 가 된다. **2026-09-13 04:3x 사용자 결정 D3 로 7 전략 전부 `SOR`→`NXT` PUT 을 마쳤다**(메모리·DB 양쪽 확인, SOR 잔여 0) — 이제 어휘에서 `SOR` 을 지울 수 있는 상태가 됐으나, 그 제거는 09-14 실측 뒤로 남긴다(가드 `test_cycle287_sor_retired.py::test_n3b` 가 배포 순서 `코드 → D+1 → 카탈로그/프론트 → DB` 를 강제한다). 두 PUT 클라이언트(`Settings.tsx`·`StrategyParamsEditor`)가 **변경분만** 보내므로 지금 실害는 없다. `exchange` 자체는 `editable=True` 로 남는다 — `editable=False` 로 만들면 그 키를 보내는 모든 PUT 이 422 다. `<select>` 의 `<option>` 은 브라우저가 스타일을 제한해 `choice.deprecated` 회색 처리가 닿지 않으므로 **라벨 자체가 유일한 폐기 신호**이고, 프론트 회귀 가드가 그 문자열을 봉인한다.

**param_validation.py** (cycle278 — 파라미터 검증 **순수 함수 leaf**(`param_catalog` 만 import). `validate_params(strategy_id, current_params, incoming) -> ValidationResult(errors, warnings, accepted)`. 판정 순서 = 키 존재 → editable → 자료형 → choices/pattern → **금지 선택지(`forbidden_choice`)** → min/max · **최소 항목 수(`too_few_items`)** → 예산 불변식(병합 결과) → 순서 불변식(경고). **첫 오류에서 멈추지 않는다**(한 저장에 여러 필드를 고치는 화면이라, 멈추면 운영자가 오류를 하나씩 왕복하고 그 왕복마다 all-or-nothing 이 다시 걸린다). 예산 불변식 `position_ratio × max_positions <= 1.0` 은 EPS=1e-9 로 경계 1.0 을 **통과**시키고(7 전략 중 6 전략 기본값이 정확히 1.0), **이미 위반 중인 상태를 악화시키지 않는 편집은 통과 + `budget_invariant_preexisting` 경고**(막으면 그 전략이 영구 편집 불가 = 복구 수단이 DB 직접 UPDATE 뿐). 빈 `tradable_boards` 는 **422** 다 — 효과가 전략마다 정반대라(momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS` 폴백으로 매수 계속, BFB·VCP·kojiro 는 공집합 = 매수 전면 중단) 어느 쪽도 운영자의 의도가 아니고, 매수를 멈추는 정당한 수단은 전략 비활성화다(구 `Settings.tsx::ExchangeBoardRow` 가 화면에서 막던 규칙을 서버로 올렸다). VB + `post_nxt` 도 **422**. ⚠️ `applies_to` 는 PUT 의 관문이 **아니다**(의도된 fail-open) — 미지 키 판정이 `key in current_params` 라 DB 드리프트로 들어온 소관 밖 키는 저장된다. 그 전략이 읽지 않는 키라 매매 영향 0 이고, 조이면 비상 `curl` 롤백 경로가 좁아진다. 소비처 = `routes/strategies.py::update_params`. AI 자문 수동 적용 경로(`routes/recommendations.py`)는 아직 이 함수를 거치지 않는다 — 검증 비대칭이 남아 있고, 순수 함수라 후속 사이클의 연결은 한 줄이다)

**tick_channel_mode.py** (cycle293, 2026-09-14 — 시세 채널 리졸버 **킬스위치 모드 leaf**. `system_config.tick_channel_resolver_mode` 한 키가 정본이고 값은 `off`(전 종목 통합 = 오늘과 동일, 롤백 위치) / `observe`(판정만 로그, **배포 기본값 = 행위 0**) / `enforce_low`(LOW 후보만 전용 채널, HIGH 제외) / `enforce`(전면). API = `current_mode()`(동기, hot path) · `refresh_mode()`(async, **once-latch 금지** — `_load_strategy_config` 의 `_config_loaded` 같은 프로세스당 1회 래치를 두면 킬스위치가 아니다) · `apply_mode(mode)`(라우트용 즉시 메모리 반영) · 테스트 seam 2. 🔴 **장중에 닿아야 한다** — cycle287 은 킬스위치 2개를 `param_catalog` 에 넣지 않아 `PUT /api/strategies/{id}/params` 가 `unknown_key` 422 를 돌려줬고(cycle290 이 그 둘을 등재해 닫았다), D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지) 때문에 "다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다. 즉시 경로 = `PUT /api/realtime/tick-channel-mode {"mode":"off"}`(DB 저장 + **같은 요청에서** 이 모듈의 메모리 값까지 덮는다). 폴링 백업 2곳 = `scanner.subscribe_filtered_stocks`(5분) · `stale_watcher_core.check_and_resubscribe_stale`(120초). 실패 방향 = DB 조회 실패·키 부재·미지 값 전부 **현재 값 유지**(기본값 되돌림 금지 — 운영자가 `off` 로 내려놓은 뒤 조회가 한 번 실패했다고 다시 켜지면 안 된다) + 미지 값은 `[tick_channel_mode_invalid]` WARNING. 시각 리터럴 0건(플리커 백스톱은 시간 창이 아니라 출처 검사 + KST **날짜** 키). ⚠️ **`off` 가 즉시 되돌리지 못하는 것** — §3-C "장중 전환 금지" 때문에 이미 전용 채널에 올라간 종목은 다음 `_boot`/재구독까지 그 채널에 남는다(매수 축 게이트는 그 사실을 읽으므로 계속 닫혀 있다). `system_config` 헬퍼는 `src/db/system_config.py`)

**tick_channel_clock.py** (cycle294, 2026-09-14 — 시세 채널 **시각축 판정 leaf**. 동기·순수·never-raise, `await`/DB/HTTP 0(AST G-294-14). 3단계의 종착지는 통합 채널의 **소멸**이다 — 프리장은 `H0NXCNT0`, 정규장+애프터는 `H0STCNT0`, 전환은 하루 **1회**. 09-14 16:39~16:41 라이브 실측(`000815`·`005385` = `nxt_false` / `000660` = `nxt_true`)에서 셋 다 `H0STCNT0` 로 KRX 애프터마켓 체결을 받았다 = 그 채널은 **종목 속성과 무관하게** 정규장 개장부터 연속 체결 종료까지를 덮는다. API = `_windows(on_date)` → `(krx_regular_open, nxt_pre_end, krx_continuous_end)` · `switch_at(on_date, *, offset_secs)` · `clock_channel(now, *, offset_secs)` → `(tr_id, reason)` · `set_day_revert()`/`day_reverted()`(§5 자동 원복 래치, 벽시계 날짜 경과 시 자기 해제 — **시계를 못 읽는 경로에서도 날짜 키가 비지 않는다**: 비면 리셋 조건이 영원히 거짓이라 영구 좌초다) · `switch_windows()`/`active_switch_window()`(🔴 **cycle295 (2026-09-16) — 전환 허용 창 3개 → 1개**(`pre_to_krx`). cycle294 가 CRITICAL-1 커버리지로 넣었던 `nxt_only_continuous_window(on_date)`·`in_nxt_gap()`·`gap_hold_enabled()` 와 갭 창 2개(`krx_to_nxt_gap`·`nxt_gap_to_krx`)는 **전부 삭제**됐다) · 관측 `emit_clock_config()`/`note_pre_window_frame()`/`emit_pre_window_frame_summary()` · `reset_state_for_test()`. 표 파생값은 **날짜 키로 메모**한다(`risk.on_tick` 이 코호트 종목마다 부르는 경로라 틱마다 `get_market_table` 을 두 번 재구성하던 것을 하루 1회로). 🔴 **시각 리터럴 0건이 계약이다** — 경계 셋이 전부 `market_state.get_market_table(on_date)` **공개 API** 파생이다(`MARKET_TABLE` 직접 순회 금지: `effective_from`/`effective_to` 해석기 `_is_effective` 가 private 이고 빠뜨리면 09-13 이전 날짜에서 20:00 이 나와 거짓이다). `krx_continuous_end` 는 `phase` 가 아니라 **`match_kind == "continuous"`** 로 고른다 — `phase` 면 `REGULAR`(15:20)와 `AFTER_MARKET`(20:00)을 둘 다 열거해야 하고 KRX 가 연속 구간을 또 신설하는 날 그 열거가 조용히 낡는다. 전환 시각 = `clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`(offset 기본 300초). 🔴 **cycle295 갭 홀드 철회** — cycle294 는 NXT 단독 연속 구간(09-15 = 15:40~16:00)에서 HIGH(보유·익일청산)만 NXT 를 따라가게 했다. 그 판단의 **사실 근거는 지금도 참**이다(그 20분 KRX 에 연속 체결이 없다). 뒤집힌 것은 사실이 아니라 **필요**다 — 2026-09-15 사용자 결정 「15:30~16:00 완전 휴식」으로 그 구간엔 주문 자체를 내지 않으므로(아래 `order_engine.py` 절의 컷 게이트) 시세만 NXT 를 따라갈 이유가 사라졌다. 그 20분의 KRX 커버리지 공백은 그 결정이 **수용한 비용**이고, 되살리기 전에 `_workspace/00_URGENT_WORKLIST.md` 의 2026-09-15 결정을 확인하라. `clock_channel` 은 여전히 `priority` 키워드를 받지만 **판정에 쓰지 않는다**(제거하면 `scanner.py` 8영역 연쇄 변경이라 인자만 남겼다). 킬스위치 `tick_channel_gap_hold_enabled` 도 함께 폐기됐다(DB 잔존 행은 남아 있으나 **소비처 0** — 그 키 이름 재사용 금지). 🔴 **통합 채널을 절대 반환하지 않는다** — 판정 실패(L1)의 폴백도 `H0STCNT0` 다(실측 확정 채널 · 구독 수명의 92% 가 KRX 창 · 셋 중 **모의(VTS) 지원은 그것뿐**). "구독을 안 한다" 방향으로는 가지 않는다(P0-1 재현 방향). 통합은 `scanner.tick_tr_id_for` 의 킬스위치 `off` 분기에서만 나온다)

**tick_channel_switch.py** (cycle294, 2026-09-14 — 살아 있는 구독의 **채널 전환 + 자동 원복 leaf**. `run_switch_cycle(scheduler, pool, *, now)` 가 120초 `stale_watcher_core.check_and_resubscribe_stale` 안에서 불린다(**never-raise** — 전환 실패가 4중 안전망의 한 축을 끊으면 안 된다). 🔴 **창 밖 전환 금지** — 전환 창 `[switch_at, krx_regular_open)` 안에서만 옮긴다. 근거 셋이 그 창에서만 동시에 성립한다: ① 그 창에만 프레임이 구조적으로 0(NXT 휴장 + KRX 시가 단일가)이라 이중 채널 창의 `tick_volume` last-write-wins 비결정론이 노출되지 않는다 ② 주문이 0건이다 ③ 못 옮겨도 blind 가 아니다(미전환 잔여는 NXT 에 남고 NXT 는 정규장·애프터에 체결을 싣는다). 트리거가 이 루프 하나뿐인 이유 = `_scan_loop`(300초)은 `TIME_SCAN_START` 에 생성돼 **아침 전환 창에 존재하지 않는다**. HIGH(보유·익일청산) = **make-before-break**(신 채널 SEND → ACK 확인 = `(new, t) ∈ _subscriptions ∧ ∈ _subscriptions_acked` **두 집합** → 구 채널 해제. `_subscriptions` 만 보면 SEND 직후 무응답을 성공으로 읽는다. ACK 실패는 신 채널만 즉시 회수하고 구 채널 유지 + **전환 예산 미소모**), LOW = break-before-make. 🔴 **세션 재추첨 금지** — `websocket_pool.switch_channel_same_session` 은 `_ticker_to_session` 을 **읽기만** 한다(다른 세션에 떨어뜨리면 그 dict 가 덮여 구 세션 튜플이 영구 고아로 41 슬롯을 잠식한다). **자동 원복** = `krx_regular_open + revert_probe_secs`(기본 180 = `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용, 재정의 금지) 시점 판정. 🔴 **착지 직후 적대 검증이 세 구멍을 닫았다** — ① 표본이 「전환 **성공**한 HIGH」에서 **「지금 KRX 전용 채널에 앉은 HIGH」**로(프리 창부터 KRX 였던 `nxt_false` 보유가 영영 표본 밖이었고, `enforce_low`·`nxt_true` 보유 0 인 날엔 트리거 자체가 없었다) ② 교차 확인이 "비교 코호트 전부 침묵 = `market_wide` 로 **결론**" 이던 것을 **비결론**으로 바꾸고 2×probe 뒤 escalation(3단계 정상 상태가 "전 종목 같은 채널" 이라 진짜 고장에서만 발화 못 하는 교차 확인이었다) ③ 판정 **전에** 세우던 `_revert_probe_done` 을 **결론적 판정에만** 세운다(상한 `MAX_REVERT_PROBE_ATTEMPTS=10`). 되돌림은 **make-before-break**(종전 break-before-make + `bypass_limit=False` 를 보유 종목에 라이브 구간에서 걸고 반환값도 안 읽었다 = 좀비 경로) + `tick_channel_clock.set_day_revert()` + `[tick_channel_auto_revert] n= reverted= failed= …` **ERROR** 1행(ERROR 인 이유 = `pattern_by_level` 이 WARNING 이상만 21:30 리포트 `top_patterns` 에 넣는다 — cycle245 `[ratio_cap_config]` 함정). 되돌림은 "전원 NXT" 가 아니라 **프리 창 규칙**이다 — 단순 전원 NXT 면 `nxt_false` 가 새 blind 가 된다. **그날 재시도는 없다**. 전체 침묵(`cross_fresh < 2`)은 채널이 아니라 세션·시장 문제라 기각한다(cycle241 계열). 다이얼 = `tick_channel_switch_enabled`(전환만 끈다) · `tick_channel_switch_offset_secs` · `tick_channel_switch_ack_timeout_secs` · `tick_channel_revert_probe_secs` — **4키**(cycle295 가 `tick_channel_gap_hold_enabled` 를 폐기해 5→4). 전부 `system_config` 축이고 `PUT /api/realtime/tick-channel-mode` 의 선택 필드 `switch_enabled` 로 즉시 끌 수 있다(옛 `gap_hold_enabled` 를 보내면 **422 가 아니라 조용히 무시**된다). 🔴 창 밖 금지는 **창 안에서도 종목마다 재확인**된다(120초 루프가 창 끝 직전에 진입하면 종전 구현은 예산이 찰 때까지 창을 넘겨 계속 옮겼다). 전환 대상에서 cycle253 **진단 프로브 튜플**과 **비-TICK 라우팅**(체결통보 등)을 제외한다 — 없으면 `wanted` 가 항상 전용 TICK 이라 체결통보 구독이 전환 대상이 된다. LOW 전환 실패는 `_ticker_to_session`/`_ticker_to_tr_id` 를 **동행 pop** 해 다음 사이클이 재구독하게 한다(종전에는 세션 튜플 0 + 라우팅 잔존 = 20:00 까지 자가 치유 없는 **구독 좀비**))

**daily_metrics_snapshot.py** (cycle283 D5, 2026-09-11 — 20:05 metrics **1차 스냅샷 leaf**. `run_daily_metrics_snapshot(target_date: date | None = None) -> dict | None` 이 `TIME_METRICS_SNAPSHOT`(20:05) 에 불려 `daily_log_reports` 의 그날 행을 upsert 한다. 목적 = `api_metrics`·`strategy_funnel` 이 **프로세스 메모리 전용**이라 정산이 21:30 으로 밀린 뒤 유실 노출이 10분에서 90분으로 늘어난 것을 5분으로 되돌리는 것. 🔴 **OpenAI 를 부르지 않는다**(비용·지연 0, `model`·토큰 5컬럼 전부 NULL) · 🔴 **`reset_request_metrics()` 를 부르지 않는다**(부르면 21:30 완전판이 저녁 90분치만 보게 된다) · never-raise · 마커 `[daily_metrics_snapshot] target_date= pass=1 saved=1|0 elapsed_ms=` 실행당 1행 — **성공 서명은 「마커 1행」이 아니라 `saved=1` 1행**이다(`saved=0` 은 WARNING = 저장이 조용히 비었다). 21:30 완전판과 같은 행을 쓰므로 `insert_log_report` 는 `ON CONFLICT (target_date) DO UPDATE`(SET 절은 base 9컬럼만 — `ext_*` 6컬럼·`created_at` 무접촉). 스케줄 시각 표는 아래 `TIME_*` 절 참조)

**market_op_subscribe.py** (cycle292, 2026-09-14 — 종목별 H0UNMKO0(VI) 구독 **본체 leaf, 행위 변경 0**. `scheduler._subscribe_market_operation_tickers` 176줄을 그대로 옮겼다(`self.` → `scheduler.` 6곳 + 4칸 dedent 뿐 — 세그먼트 sha 로 라인 단위 동일을 기계 증명). 이유는 `scheduler.py` 라인 상한(cycle257 영구 상한 **<3,900**)에 여유가 3줄뿐이었던 것이고, 3,897 → **3,726L**(여유 174) 이 됐다 — `quote_token_refresh`/`open_price_rest` 위임 선례. 규약·마커·우선순위는 cycle221/230 계약 그대로다(HIGH = 보유+익일청산만 · 메인 0건 · `bypass_limit=False` 명시 · 보조 세션 **직접** 라운드로빈 · 델타 해제 · 소켓 `State.OPEN` 가드 · `ConnectionClosedError` break+WARNING 1행 · `asyncio.sleep(0.05)` Rate Limit · `cap` 은 vestigial). 형제 **`market_operation_monitor.py`** 와 역할이 반대다 — 그쪽은 H0UNMKO0 **수신·상태 추적**, 이쪽은 **송신·구독 배치**. 🔴 **함수-로컬 import 5줄**(`ConnectionClosedError`/`State`/`MARKET_OP_TR_ID`/`MAX_SUBSCRIPTIONS` + `kis_ws`←`websocket` / `kis_ws_pool`←`websocket_pool`)을 **모듈 최상단으로 올리지 않는다** — 기존 회귀 4파일이 *정의 모듈의 속성*(`src.realtime.websocket.*` / `src.realtime.websocket_pool.*`)을 monkeypatch 하고 함수-로컬 import 는 매 호출 재실행되므로 그 patch 가 걸린다. 올리면 이름이 import 시점에 바인딩돼 patch 가 무력화되고 `_ws is None → return 0` 조기 반환이 **부정 단언 6케이스를 조용히 초록**으로 통과시킨다(실측: 승격 뮤테이션에 행위 테스트 22건이 붉어진다). 두 줄 분리도 유지 — 합치면 2026-07-24 의 매 호출 ImportError(cycle214 배포 이래 완전 미작동, 하루 117건) 재발이다. 🔴 **`logger = logging.getLogger("src.engine.scheduler")` 고정** — `__name__` 으로 바꾸지 않는다. 마커 5종(`[market_op_subscribe_skip]`/`[market_op_no_quote_session]`/`[market_op_subscribe]`/`[market_op_subscribe_summary]`/`[market_op_subscribe_no_slot]`)이 전부 기존이라 이름이 갈리면 `_DbLogHandler` 가 적는 `system_logs` 접두가 바뀌어 운영 grep 사슬이 끊긴다(사이클 60 I1 관례). scheduler 에는 **5줄 위임 wrapper** 만 남아 호출부(`_scan_loop`)·시그니처·예외 전파가 불변이다. 가드 = `tests/unit/ast/test_cycle292_ast_market_op_leaf.py`(G-292-1~8, G-292-9 는 별칭 우회 차단이라 아래 cycle221 파일이 집이다) + 재조준된 `test_cycle221_ast_market_op_no_main.py`·`test_cycle214_ast_h0unmko0_pool.py`·`test_market_op_subscribe_import_path_guard.py`·`test_market_op_subscribe_socket_guard.py`(넷 다 부정 단언이라 **양성 대조군**을 함께 심었다 — 본체가 사라져도 초록이 되는 공허 통과 차단). 명세 = `_workspace/red/cycle292_scheduler_market_op_leaf_spec.md`)
```
````

→ CHANGELOG: 각 사이클 행

## 사이클 C1~C3 (2026-07-15) — 퀀트 재무필터 Phase 1 (관찰 전용, 마법공식 + F-Score-7)

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「저녁 데이터 적재」 절의 재무 적재 + `strategies/CLAUDE.md` VB 절)

```

관찰 전용 Phase 1 = 재무 데이터 적재 + 스코어 계산 인프라 + VB funnel 노출까지만. 실배제 게이트는 Phase 2(C4) 조건부. 매매 hot path 무관.

### 16:40 재무 적재 task (`TIME_STOCK_MASTER_FINANCIAL_LOAD = time(16, 40)`)

- `scanner._stock_master_financial_load_once(force=False)` — 주1회 재무 5 TR (`src/api/finance.py`) 적재. 유니버스 = `_is_daily_load_universe` 자격 856종목 (index ∪ 시총 500억 & 거래 20억, 사이클 206 답습). ticker 별 `stock_master_financial.max_stac_yymm` 신선도 skip (당분기 이미 적재 시) → 미신선 시 `fetch_all_financials` → `upsert_financial_batch`. `[stock_master_financial_load_summary] total=.. updated=.. skipped=.. failed=..` emit. graceful (사이클 88).
- `scheduler._stock_master_financial_load_task_loop()` — `run_periodic_task_loop` 답습. `initial_delay_secs=900` (master 16:30 후 stagger) + `immediate_skip_if_fresh_hours=168` (주1회 신선도 게이트, 사이클 193 답습). `task_label="stock_master_financial_load"`. `task_attrs` 4 위치 (start + connect finally + run_daily finally + stop, 사이클 79 G-AST2). `refresh_progress` TaskKey `"financial"` (5키).
- **scan_stocks/매수 경로 diff 0** — 16:40 적재 = 매수 진입 전 데이터 계층 (사이클 38).

### VB 관찰 훅 `_apply_quant_filter_in_prepare` (사이클 C3)

- `volatility_breakout.py` — `_apply_price_filter_in_prepare`(사이클 148) 미러. DEFAULT_PARAMS `quant_filter_enabled=False` / `quant_min_f_score=0` / `quant_max_mf_rank=0` (**PARAM_RANGES 미편입**). `VB_FUNNEL_STAGES` 6→7단계 ("퀀트 재무 게이트(관찰) — F-Score/마법공식 스코어 기록, 배제 0").
- **기본 OFF = 관찰 전용, 배제 0** — 스코어 계산 (`quant_score`) + funnel step 7 기록만. `quant_filter_enabled=True` 여도 아직 실배제 로직 미구현 (Phase 2 C4 인계). 결측·보유 fail-open (사이클 32 R4). momentum 라이브 경로 무변경 (관찰은 오프라인).

### 매매 안전성 무영향

- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py(매수경로) src/engine/strategy_registry.py` = **0** (재무 task = 16:40 매수 진입 전 + quant_score 8영역 미접촉 + VB 관찰 훅 배제 0).
- 백엔드 3,434 PASS/0 fail. 회귀 가드 `tests/unit/api/test_cycleC1_finance_allowlist.py` 외.
- 인계: Phase 1 관찰 데이터 유의성 검정 후 Phase 2(C4) = quant_filter_enabled=True + 실배제 조건부 게이트.
```

→ CHANGELOG: 사이클 C1~C3 행

## 사이클 G (2026-08-02) — VB RR(손익비) 개선 Phase 1 (Part A C2 조기청산 default-off + Part B RS/RSI 관찰)

### 2026-09-17 이관 — 절 전문 (현행 규칙 = `src/engine/strategies/CLAUDE.md` VB 절)

```

사이클 F 실측 = VB 유일 열위(N=65, 승률 35%, RR 1.35 < 필요RR 1.83, TE −0.63%). 구조적 원인 = check_exit_signal 에 익절·트레일링 부재(승자 15:20 캡) + −3% 하드손절 고정 + 진입 품질 필터 전무. Part A(avg_loss↓) + Part B(승률↑ 증거 축적)로 대응. 승인 계획 `~/.claude/plans/luminous-drifting-widget.md`.

### Part A — 실패 돌파 조기청산 (C2, `check_exit_signal`, default-off → 백테스트 게이트)

- `volatility_breakout.py` DEFAULT_PARAMS 3키 (`failed_breakout_exit_enabled=False` / `failed_breakout_buffer_pct=-0.5` / `failed_breakout_confirm_ticks=2`, **PARAM_RANGES 미편입** = 청산 정체성 상수). `check_exit_signal` 손절 분기 *뒤*·익일 안전망 *앞* 신규 분기: 돌파선(`_targets[ticker].boards[board].target_price` 우선, top-level 폴백) 대비 `current_price < target × (1 + buffer/100)` 가 `confirm_ticks` 연속 → `Signal.STOP_LOSS`. 회복(돌파선 위) 시 카운터 리셋. `_failed_breakout_count: dict[str,int]` transient(prepare clear + on_position_closed pop). **`enabled=False`(기본) → 분기 미진입 = byte-identical**(BFB 사이클 C `breakeven_promote_atr=0` 선례).
- 롤아웃 게이트 = default-off 라이브 배포 → 외부 MCP 백테스트 buffer/confirm 스윕 통과 시 운영자 DB `strategy_config.volatility_breakout.params.failed_breakout_exit_enabled=true` 활성 → te_metrics 로 RR/avg_loss 재측정.

### Part B — RS/RSI 진입 품질 관찰 훅 `_apply_rs_rsi_observe_in_prepare` (관찰 전용, 배제 0)

- `_apply_quant_filter_in_prepare`(C3) 미러. DEFAULT_PARAMS 3키 (`rs_filter_enabled=False` / `rsi_filter_enabled=False` / `rsi_extreme_max=85`, **PARAM_RANGES 미편입**). `VB_FUNNEL_STAGES` 7→**9단계** (step 8 RS 관찰 / step 9 RSI 관찰). prepare 말미(quant 훅 뒤) 호출. `ta_indicators.rsi`/`relative_strength` + `stock_master_daily.get_recent_daily`(DESC→ASC 역순) + 지수 KODEX200(069500) 벤치마크. **입력==출력 배제 0** — enabled=True 여도 Phase 1 실배제 미구현. 보유 protected 스킵(사이클 32 R4) + 결측/예외/지수 미수신 fail-open(사이클 88 G-REJECT). RSI 관찰 = 극단(>85)만(단순 >70 과매수 컷 금지 — 강세 돌파는 정상적으로 RSI 高).
- 관찰 게이트 = 2주 후 고RS/저RSI극단 vs 저RS/고RSI 진입의 승률·RR 유의성 검정 → 유의 시 별도 사이클 실배제 활성.

### 매매 안전성 무영향

- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/scheduler.py src/engine/session.py src/engine/strategy_registry.py` = **0** (Part A default-off byte-identical + Part B 관찰 prepare 매수 진입 전, 사이클 38). check_buy/exit 본체 rs/rsi 토큰 인젝션 0(AST 가드).
- 회귀 가드 43 케이스: `test_cycleG_ta_indicators.py`(14, rsi/rs 순수함수 결정적) + `test_cycleG_vb_failed_breakout_exit.py`(13, C2 임계·카운터·byte-identical·승자 미간섭) + `test_cycleG_vb_rs_rsi_observe.py`(16, 배제 0·protected·fail-open·지수 069500·funnel 8/9·SAFETY). 의미 전환 3(cycle157 6→9 + cycleC3 7→9 + cycle148 xfail 영속). 8영역 diff 0.
- 인계: Part B 관찰 유의 시 RS(B2) 실배제 활성 → C1/C3 손절 정교화 → ETF 레짐 E-2 → 최후 A1 느슨한 트레일링(avg_win, fat-tail 절단 위험으로 마지막).
```

→ CHANGELOG: 사이클 G 행

## 사이클 H (2026-08-02) — 포트폴리오 리스크 관찰 훅 Phase 1 (터틀 서적 대조 감사 갭 2건, 관찰 전용)

### 2026-09-17 이관 — 절 전문 (Phase 2a·사이클 I 후속 포함 — 현행 규칙 = 정본 모듈 맵의 `portfolio_risk.py`·`sector_naming.py`·`account_risk_guard/watcher` 항목)

```

「터틀 자금관리」 서적 14p 발췌를 3중 대조(개념·정밀수치·포트폴리오)한 감사에서 도출한 최대 구조적 갭 2건(둘 다 High) 대응: (1) **포트폴리오 단위 총리스크 상한 부재** — `is_daily_loss_exceeded`가 전략별 격리라 7전략×최대5=최대 35 동시보유를 묶는 계좌 통합 정지 게이트 없음. (2) **전략 간 섹터/상관 집중 무통제** — `is_ticker_blocked_for_buy`는 동일 종목코드만 차단, donchian 반도체A+VCP B+kojiro C 동시보유 무차단. **이번 사이클 = Phase 1 관찰 전용**(매수 차단·SOFT 상한은 2주 관찰 후 Phase 2).

### 8영역 회피 설계 (strategy_registry.py 가 8영역이라 registry 미접촉)

- **신규 순수함수 `portfolio_risk.py`**(위 모듈 맵) — registry/kojiro/db/http 미접촉, 호출자 주입(pull). AST 가드 = 8영역 파일에 `portfolio_risk` 참조 0건 + portfolio_risk.py 에 `_kojiro_sector_key`/`trading_scheduler`/registry/db import 0건.
- **`GET /api/portfolio/risk`**(routes/portfolio.py, 8영역 아님) — `trading_scheduler.registry.all()` + `get_balance()` net_asset + 보유 ticker 섹터명 pull → snapshot. **섹터명 소스(사이클 I 후속)** = basics raw `bstp_kor_isnm`(KIS 업종 한글명 "유통"/"금융") 우선 → 부재 시 `_kojiro_sector_key(get_master_raw)`(KRX 플래그→업종코드→미분류) 폴백. `_kojiro_sector_key` 무변경(kojiro 섹터 캡 보존, display 전용). get_balance/stock_master 실패 graceful 200(500 금지).
- **일일리포트 계량화**(log_analysis_engine.py, hot path 아님) — `_build_portfolio_risk_snapshot(now_kst)` async 헬퍼 + metrics `portfolio_risk_snapshot` 키(빌드 실패→None graceful, 리포트 INSERT 보존).

### 매매 안전성 무영향

- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = **0** (신규 순수함수 + 라우트 + 일일 리포트 = 매매 hot path 미접촉, 배제 0).
- 회귀 가드 43(순수함수 25 + 라우트 4 + log_analysis 2 + AST 격리 12) 전량 GREEN. 백엔드 4,033 PASS.
- 인계 Phase 2: (a) ~~SOFT 상한~~ **→ cycle233 완료**(단 registry 가 아니라 `account_risk_guard`/`watcher` + StrategyBase 게이트 — registry 는 8영역이라 원안 폐기. 다크런치, DB `account_risk_block_pct` 활성 대기) (b) ~~섹터 소스 master_raw 승격~~ **→ Phase 2a 완료** (c) ~~turtle entry_atr 정밀 리스크~~ **→ cycle233 척도 병기 완료**(`stop_price_of` 주입 — 프록시 **대체 금지**, 병기가 계약: 실효 척도도 갭 관통 손실은 못 잡는다) (d) 프론트 카드 — 잔여.

### 사이클 H Phase 2a (2026-08-03) — 섹터 소스 승격 (관찰 전용, 8영역 diff 0)

EC2 실측에서 `by_sector`가 보유 7종목 전부 `미분류-{ticker}`로 나온 결함 시정. **근본 원인**: 두 소비 seam(`routes/portfolio.py::_sector_of_graceful` + `log_analysis_engine.py::_build_portfolio_risk_snapshot`)이 섹터 소스로 `stock_master.get(ticker).raw`(basics raw = CTPF1002R merge)를 넘겼으나, `_kojiro_sector_key`가 읽는 KRX 산업지수 플래그 12개(`krx_smcn_yn`·`krx_bio_yn` 등)+업종코드 2개(`bstp_larg/medm_div_code`)는 `stock_master.master_raw` 컬럼(migration 034, `kis_master.py` 파서 적재)에만 존재 → basics raw엔 전무(grep 0) → 항상 미분류 폴백. **시정**: 두 seam 모두 `get(ticker).raw` → `stock_master.get_master_raw(ticker)`(kojiro `_fetch_sector`와 동일 소스). `_kojiro_sector_key` 호출부 byte-identical(`get_master_raw`가 이미 `Optional[dict]` → 기존 `isinstance` 가드 그대로). **fail-open 보존**: `get_master_raw`는 lazy fallback 없음(16:30 배치만) → 미적재 종목 None → `미분류-{ticker}`(kojiro 동일). 매매 안전성 8영역+`portfolio_risk.py` diff 0(관찰 전용, 매수 차단 0). 신규 회귀 1(route `test_route_classifies_real_sector_from_master_raw` = KRX 플래그 dict→"바이오" 분류, 승격 전 RED) + 기존 route 테스트 monkeypatch seam 2줄 조정. 백엔드 4,358 PASS.

**사이클 I 후속 (2026-08-03) — 섹터명 사람이 읽는 명칭 전환**: Phase 2a 배포 후 `by_sector`가 `업종-0016`처럼 업종 대분류 코드로 표기(KRX 12플래그 미해당 종목이 `bstp_larg_div_code` 폴백)돼 판독 불가. 조사 결과 `master_raw`엔 업종 한글명 없으나 **basics raw(`get().raw`)의 `bstp_kor_isnm`("유통"/"금융"/"전기·전자")이 전 종목 채워짐**(CTPF1002R, 신규 호출 0). 두 seam(route+log_analysis)을 **`bstp_kor_isnm` 우선 → 부재 시 `_kojiro_sector_key(get_master_raw)` 폴백**으로 변경. `_kojiro_sector_key` 무변경(kojiro 섹터 캡 그룹핑 보존, display 전용). ⚠️ `idx_bztp_lcls_cd_name`="시가총액규모중"은 섹터 아님(사용 금지). 신규 회귀 2(bstp_kor_isnm 명칭 + 폴백). 8영역 diff 0.
```

→ CHANGELOG: 사이클 H · 사이클 H Phase 2a · 사이클 I 행

## 사이클 188 (2026-07-02) — `_wait_until(advance_if_passed=True)` never-return 회귀 시정

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「`scheduler._wait_until` 계약」 절)

```

사이클 187 실측 검증 중 발견한 사이클 160 회귀(6/17~7/2, 2주). `scheduler.py::_wait_until` 의 advance 모드에 return 경로가 없어 — while 루프가 매 iteration "오늘 target" 재계산 → 도달 순간 `+1일`로 밀며 무한 sleep — production 유일 호출처 `task_loop_helper.py:114`(`run_periodic_task_loop`)가 영원히 대기 → **모든 정기 task(16:00 일봉/16:10 basics/16:15 purge/16:20 저녁 funnel/16:30 master/20:00:05 universe) 정기 시각 발화 0회**. 매일 아침 run_daily 재시작의 `immediate_first_run` 이 D-1 데이터를 채워 silent (부작용 = 무거운 full load 가 프리마켓 07:45~08:13 에 집중).

### `_wait_until` 계약 (사이클 188 이후 정본)

- `target_dt` 는 **호출 시점 1회 확정** (while 루프 진입 전). 루프 내 재계산 금지 — 재-advance 구조적 차단.
- default (`advance_if_passed=False`): target 이미 지남 → 즉시 return (사이클 160 본질, run_daily phase 전환 9곳). 미도달 → 대기 후 도달 시 return.
- advance (`=True`, task_loop_helper 전용): target 이미 지남 → `+= timedelta(days=1)` 1회 확정 (사이클 152 폭주 차단) → **확정 target 도달 시 return (발화)** — 사이클 188 신설 경로.
- `asyncio.sleep(min(잔여초, 60))` + `while self._running` 체크 영속 (stop 시 신속 탈출, 헬퍼의 `if not scheduler._running: break` 가 흡수).
- `break` 사용 금지 (cycle152 AST 가드) / naive `datetime.now()` (컨테이너 TZ=Asia/Seoul) / 시그니처 불변.

### 회귀 가드

`tests/unit/engine/test_cycle188_wait_until_advance_return.py` 7케이스 — 가상 시계 단조 전진 mock(fake sleep 이 가상 시각 전진, freezegun 금지 = 사이클 187 동결 monotonic hang 교훈). G-188-1/2/3(advance 당일·익일 발화 + 재-advance 금지, HIGH) + G-188-4/5(default 보존) + G-188-6(_running=False 계약) + G-188-7(HIGH 통합 — `run_periodic_task_loop` + 실제 `_wait_until` 본체로 정기 발화 end-to-end, cycle134 스위트 미검증 갭 봉합). 기존 cycle160/152/134/158 테스트 수정 0 (전부 PASS 유지 — 고정 clock 방식이라 return 여부 미단언이었음). 매매 안전성 8영역 diff 0.

### 인계

(a) 아침 immediate_first_run 프리마켓 부하 완화 (D+1 실측 후 사용자 결정) (b) `_wait_until`/run_daily naive now → KST 명시 (LOW) (c) D+1 운영 실측 = 16:00 정기 발화 + 16:20 funnel 저녁 `is_provisional` 생성 확인.
```

→ CHANGELOG: 사이클 188 행

## 사이클 172 (2026-06-22) — stock_master_daily 220일 확보 (LOW~MEDIUM, 데이터 plumbing, 사이클 173 선행)

### 2026-09-17 이관 — 절 전문 (사이클 263 오늘봉 필터 · 사이클 273d 보호 종목 포함 포함 — 현행 규칙 = 정본 「저녁 데이터 적재」 절)

```

승인 설계 `/Users/koscom/.claude/plans/funnel-vast-wolf.md` 사이클 172 절 (도입 시점 동기부여 서술 — 아래 사이클 196 정정 참조). 사이클 172 는 VCP universe (KOSPI200∪KOSDAQ150, 348종목) 220일 backfill 을 도입했으나, **⚠️ 사이클 196 정정**: retention 230cal = 154영업일 실측 < 220 → `existing_count` 220 미도달 → 무한 재backfill(churn). VCP prepare 는 실사용 100일뿐(`vcp_breakout.py:162-164`, "220 미사용") → **backfill target 220→120 하향 수렴** (아래 분기 절). **prepare/매수 target 불변** (데이터 적재/조회만).

### `scanner.py::_stock_master_daily_load_once` VCP universe backfill 분기 (사이클 172 도입 220일 → 사이클 196 120일 수렴)

- `vcp_universe_tickers: set[str]` = `list_all` row 의 `is_kospi200 OR is_kosdaq150` (사이클 153 컬럼, `.select("*")` 포함 → 별도 쿼리 0건). 플래그 키 부재 mock/legacy row 는 falsy → 비 VCP 취급 (회귀 0).
- 분기 (**사이클 196 (2026-07-07) — 220→120 수렴**): VCP universe + `existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=120)` → `condition.fetch_daily_candles_backfill(ticker, total_days=120)` (분할 fetch 윈도우 ×2, 마지막 클램프). 그 외 = 현행 (비 VCP `<50` 백필 100일 / `>=50` 증분 7일, 사이클 122 영속). VCP `>=120` → 증분 7일 (재 backfill 금지). **churn 근본 원인**: 사이클 172 target=220 이 retention 230cal(=154영업일 실측) 초과 → `existing_count` 220 미도달 → VCP 348종목 매 load 전량 재backfill (churn 45K행/load + 잉여 KIS 2,088호출/일). VCP prepare 는 100일만 사용 (`vcp_breakout.py:162-164`) → 220 = 순수 낭비. 시정 = target 120 (retained 154 대비 34일 마진) → 즉시 수렴 (backfill 1회 후 incremental) + 윈도우 클램프로 backfill 도달 178cal < retention → churn 0.
- graceful (사이클 88 G-REJECT — backfill 실패 → failed++ + 다음 ticker). **장중 자동 실행 금지** — 20:30 daily task (`TIME_STOCK_MASTER_DAILY_LOAD`, cycle283 D2 — 종전 16:00 → 18:10 → 20:30) + 수동 trigger 만 (task lifecycle 변경 0, 사이클 122).

### 사이클 263 (2026-09-06) — 확정 전 오늘봉 시각 필터 (8영역 승인, 09-06 카드 ④)

`_stock_master_daily_load_once` 는 `fetched += 1` **뒤** · `upsert_batch` **앞**에서
`_drop_today_bars(candles, now_kst=load_now_kst, today=today)` 로 **확정 전 오늘봉**을 폐기한다.
그 자리가 유일하게 안전하다 — 두 fetch 분기(`fetch_daily_candles` / `fetch_daily_candles_backfill`)의
**합류점**이고 `fetched`("KIS 응답을 받았다")·`failed`(KIS 실패 전용) 카운터 의미가 보존된다.

- **판정 기준 = 시각 단독.** `load_now_kst`(= `datetime.now(KST_TZ)`, **함수 진입 시 1회** — `stock_master.list_all` 페이징 *앞*, tz-aware 필수)가 `_DAILY_LOAD_TODAY_BAR_CUTOFF`(= `time(20, 0)`, **cycle283** — 09-14 KRX 애프터마켓(16:00~20:00 실시간 체결) 종료 시각. 종전 `15:40`(마감 동시호가 흡수)은 그 뒤의 모든 적재가 **부분 거래량 봉**을 확정봉으로 받아들이게 했다 = 09-11 사고의 직접 원인) **이전**이면 `bas_dd >= today` 를 폐기하고, 이후면 `bas_dd > today`(시계 왜곡 방어)만 폐기한다. `bas_dd` 파싱 불가/부재는 **보존**.
- **커트오프는 scanner 전용 상수다.** 값이 같아 보여도 scheduler 의 매매/보드 시각 상수를 재사용하지 않는다 — 매수 보드 시각 변경이 적재 규약을 딸려 바꾸는 커플링을 끊는다(`tradable_boards` ↔ 청산 규약 커플링을 끊어 둔 원칙과 같은 이유).
- ⚠️ **데이터 기준(거래량 0 ∧ OHLC 평탄) 금지** — 반증 2건: (a) 장중 재시작이 만드는 **부분봉**은 거래량>0·비평탄이라 데이터 기준을 확정봉인 척 통과한다(껍데기보다 나쁘다: 평탄하지 않아 눈에 안 띈다) (b) 거래정지 종목의 **진짜 평탄 확정봉**(하루 1~8건)을 저녁 적재에서 죽여 그 날짜 행을 영영 못 갖게 한다. 시각 기준은 둘 다 자동 처리하고 진짜 무거래봉을 정의상 100% 보존한다.
- **fail-open** — 판정 예외는 전량 upsert 유지(현행 행위) + `[daily_load_today_filter_skipped]` WARNING **실행당 1행**. fail-closed 는 P0-1(유령 키가 두 전략을 전 기간 체결 0건으로 만든 방향)이라 금지. 판정 실패는 **캔들 단위**이지 종목 단위가 아니다(`isinstance(candle, dict)` 방어 — 이상 원소 1개가 그 종목의 필터 전체를 무력화하면 오늘 껍데기까지 함께 새어 들어간다).
- **`force=True`(수동 `POST /api/stock-master/refresh-daily`)도 필터를 통과한다** — `force` 는 `latest >= today` 멱등 skip **만** 우회한다. 주말·20:00 이후 수동 보정은 오늘 날짜 봉 자체가 없거나 확정봉이라 **무접촉**이고, 장중·시간외 수동 실행(cycle283 이후 20:00 이전 전부)만 잠정봉을 버린다(설계 의도).
- **관측 = `[daily_load_today_bar_filter]` 실행당 1행 INFO** (`mode` / `cutoff` / `now` / `today` / `dropped_rows` / `tickers_affected` / `filter_errors`). 종목당 emit 은 하루 1,000행 폭주다(사이클 237 donchian 청산 로그 폭주 시정의 교훈). `dropped_rows`(행) ≠ `tickers_affected`(종목)이고 `filter_errors>0` 이 fail-open 발생을 뜻한다 — 이게 없으면 `dropped_rows=0` 이 "버릴 봉이 없었다" 와 "필터가 전량 죽었다" 를 구분하지 못한다. **유니버스가 비면(`candidates=0` 조기 return) 이 마커가 0행**이므로, D+1 에 마커가 안 보이면 `[stock_master_daily_load_begin] candidates=` 를 먼저 본다.
- ⚠️ **의미 반전(3세대)** — 이 마커·카운터는 **원본 / cycle263 / cycle283** 세 세대다. cycle263 = 16:00 실행의 `skipped_fresh` 가 ~1,000 → ~0(아침 껍데기가 전 종목을 skip 시켜 왔다). cycle283 = 커트오프 15:40 → 20:00 이라 **15:40~20:00 구간 실행의 `mode` 가 keep → drop 으로 뒤집힌다**(`dropped_rows`·`tickers_affected` 포함). **세대 간 로그 grep 합산 금지.**
- **최종값 보정 담지자 교체** — (가) 신선도 게이트 투입으로 아침 immediate 가 정상일마다 skip 되므로, D 봉의 최종값을 나중에 바로잡는 것은 더 이상 *다음 날 아침 재fetch* 가 아니라 **D+1 정기 실행(cycle283 이후 20:30)의 7일 증분 창**(`fetch_days=7` → `ON CONFLICT DO UPDATE`)이다. 그 창을 1~2일로 줄이면 D 봉이 그날 스냅샷에 영구 고정된다(회귀 가드 = cycle263 G2 수렴 시뮬의 "보정 창 존치" 단언).
- **부작용** — 신규 상장·유니버스 진입 종목의 일봉 backfill 이 아침(07:56)에서 같은 날 20:30 으로 **≈12.5시간 미뤄진다**(그 사이 `get_recent_daily_normalized` 는 `reason="miss"` KIS 폴백 = 데이터는 더 정확하지만 장중 KIS 호출이 는다). 최종 커버리지 손실은 0. UI `last_daily_load_at` 은 낮 동안 어제 날짜로 보인다(의미상 정확).
- 회귀 가드 = `tests/unit/engine/test_cycle263_daily_load_stub_filter.py` (40) + `tests/unit/ast/test_cycle193_ast_fresh_gate.py`(게이트 대상 3 task 로 갱신).

### 사이클 273d (2026-09-10) — 보유/익일청산 종목 유니버스 필터 강제 포함 (D5, 8영역 승인)

`_stock_master_daily_load_once` 의 유니버스 필터 게이트가 `if is_index or is_qualifier:` 였던 것을
`if is_index or is_qualifier or is_protected:` 로 확장했다(순수 OR 추가, 기존 분기 제거 0). 16:15
purge(`_evaluate_universe_guard` 계열)는 보유·익일청산 종목을 이미 절대 보호하는데, 16:00 load 는
자격(시총·거래대금 등) 미달 종목을 그냥 건너뛰어 "지우는 쪽은 보호, 채우는 쪽은 방치"라는 비대칭이
있었다 — 자격 미달일마다 그날 봉을 영구 결손시킨 004690(삼천리) 실사례가 발단.

- `is_protected` = 기존 공통 헬퍼 `_collect_protected_tickers_for_scanner()`(사이클 64 도입, 신규
  아님 — line 55)로 얻은 보유·익일청산 종목 중 **6자리 숫자 ticker 만**(진입 게이트 비대칭 규약과
  동일 — ETF/신주인수권/오염 문자열은 보호 집합에서 제외).
- 헬퍼 예외는 **fail-open** — `protected_tickers = set()` 으로 현행 집합(index/qualifier)만 진행.
- 페이징 루프 종료 뒤 `protected_tickers - set(all_tickers)` 차집합을 `all_tickers` 에 추가
  append 한다(중복 방지 + 페이징 부분 실패·누락 종목 대비 합집합 — 어느 페이지에도 안 실린
  보호 종목까지 커버).
- `vcp_universe_tickers` 에는 넣지 않는다(120일 분할 backfill 은 index 전용, 보호 목적은
  "오늘 봉 결손 방지" 로 국한).
- 관측 `[daily_load_protected_forced] protected=%d forced_in_universe=%d forced_extra=%d tickers=%s`
  — **실행당 1행**(cycle237 donchian 로그 폭주 교훈 재적용, 종목당 emit 금지). 페이징 루프 밖·
  `summary["total"]` 대입 앞에서 무조건 emit 되므로 조기 return 경로에서도 1행이 남는다.
- scanner.py +44L, `scheduler.py` 무접촉(3,898L, <3,900 상한 유지). 회귀 가드 =
  `tests/unit/engine/test_cycle273_daily_load_protected.py` (47) + sha 핀 4곳 갱신.
- 명세 `_workspace/red/cycle273d_daily_load_held_inclusion_spec.md`, 사용자 결정 D3.

### 매매 안전성 무영향 (데이터 plumbing 한정)

- scanner `_stock_master_daily_load_once` = 20:30 daily task (`TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` — **cycle283** 2026-09-11 사용자 결정 D2, 종전 16:00 → 18:10; 09-14 KRX 애프터마켓 종료(20:00) 후라 그날 거래량이 확정된 뒤에 적재한다. 16:1x~16:40 작업보다 뒤라 유니버스 판정이 오늘치 raw. 매수 진입 무관, 사이클 38/122). 어댑터 `get_recent_daily_normalized` (db) = 정의만 (prepare 미연결 → 매수 target 불변, 호출처 0).
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = **0 라인** (직접 검증). 신규 함수 본체 매매 hot path 참조 0.
- production: `src/api/condition.py` (+128L 분할 fetch — `fetch_daily_candles_ranged` + `fetch_daily_candles_backfill`, `src/api/CLAUDE.md` 참조) / `src/db/stock_master_daily.py` (+70L retention 230 + 어댑터, `src/db/CLAUDE.md` 참조) / `src/engine/scanner.py` (+37L VCP 분기). net +219L.
- 회귀 가드 27 케이스 (RANGE 4 + BACKFILL 4 + AST 1 / RET 2 + ADAPT 4 / SCAN 5 + SCAN-3b + SAFETY 1 / SAFETY AST 5) + 의미 전환 1 (cycle150 retention 150→230). 백엔드 3,161 PASS × flakiness 0.
- 사이클 173 인계: 5 전략 prepare `fetch_daily_candles` → `get_recent_daily_normalized(days, min_required)` 전환 (HIGH 동등성 게이트 + domain-expert 자문). **사이클 196 갱신**: VCP prepare 는 100일만 사용 확정 → backfill 220→120 수렴 (churn 시정). VCP EMA 원설계 복원(220일)은 미실현 별도 사이클 — 복원 시 retention(230→~320cal) + backfill target 동반 상향 필요 (220영업일 = ~308cal > 현 retention 230).
```

→ CHANGELOG: 사이클 172 · 사이클 196 · cycle263 · cycle273d · cycle283 행

## 사이클 171 (2026-06-22) — 저녁 16:20 잠정 funnel 캡처 + 수동 trigger 단계별 캡처 (MEDIUM 운영자 가치)

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「funnel 스냅샷 캡처」 절)

```

자문 `_workspace/domain_consult/cycle171_master_funnel_timing_redesign.md` 의제 4 우선순위 2 + 의제 6 (a) 채택. funnel 은 순수 관찰성 + D-1 일봉 기반 → 장중 불변 → 전날 저녁 미리 생성하면 운영자가 밤에 다음 영업일 후보 확인 가능 (현재 09:30 개장 후 캡처는 늦음).

### 공통 헬퍼 `capture_funnel_snapshots(registry, *, is_provisional)` (모듈 함수)

- `_auto_capture_funnel_snapshots` 의 "registry 순회 → 각 strategy `_funnel_steps` 단계별 + step_no=99 insert_snapshot" 로직을 추출. **3 호출처 공유**: (a) 09:30 자동 (`_auto_capture_funnel_snapshots` 위임, is_provisional=False, 행위 보존) + (b) 16:20 저녁 (`_evening_funnel_capture_once`, is_provisional=True) + (c) 수동 trigger (`routes/strategy_funnel.py::trigger_snapshot`, is_provisional=False).
- graceful (사이클 88) — 전략별 예외 격리. 사이클 132 momentum funnel 영구 제외 + 사이클 170 in-place upsert 영속. 관찰성 한정 — check_exit/buy funnel hook 0건 + risk/order_engine/realtime/auth 참조 0 (SAFETY 가드).

### 16:20 저녁 task (`TIME_EVENING_FUNNEL_CAPTURE = time(16, 20)`)

- `_evening_funnel_capture_task_loop` — `run_periodic_task_loop` 답습 (`_stock_master_master_load_task_loop` 패턴 100% + no-op record/flush). `initial_delay_secs=600` (basics 16:10 완료 후 진입, HTTP/2 race 마진).
- `_evening_funnel_capture_once` 본체: (1) 일봉 테이블 비어있지 않음 확인 — `stock_master_daily.count_all() > 0` 5분 cap polling(⚠️ F-D8-a: 그날 적재 완료 대기가 아니다 — cycle283 부터 일봉은 20:30 이라 16:20 캡처는 전일 봉 기준, 전략 절단이 날짜 비교라 결과 동일) (사이클 163 boot prepare 가드 패턴, 빈 funnel 영속 방지) (2) 5 전략 `prepare()` (기존 KIS-fetch 그대로 — 16:20 한가, 속도 무관. HIGH DB일봉 전환은 사이클 173) (3) `capture_funnel_snapshots(registry, is_provisional=True)`.
- `task_attrs` 4 위치 영속 (사이클 79 G-AST2): `self._evening_funnel_capture_task = asyncio.create_task(...)` (start) + cancel 튜플 3 (start finally / run_daily finally / stop). `test_scheduler_stop_zombie_tasks.py::expected_members` 16 → 17종 갱신.

### 매매 안전성 무영향

- 관찰성 한정. scanner/risk.on_tick/order_engine/realtime/auth diff 0. 16:00 일봉 → 16:10 basics → 16:20 funnel → 16:30 마스터 순서 의존성 보장 (count polling 가드).
- migration `040_funnel_provisional.sql` (additive `is_provisional BOOLEAN NOT NULL DEFAULT FALSE`, 운영 DB 적용 완료).
- 회귀 가드: DB 4 (insert_snapshot is_provisional) + 헬퍼/16:20 task 14 (`test_cycle171_evening_funnel.py`) + 수동 trigger 2 (`test_cycle171_snapshot_route_steps.py`) + 프론트 3 (`StrategyFunnel.cycle171.test.tsx`) + 의미 전환 (C-3 contract 단계별 / 159 stagger allowlist / 134 라인 임계 ≤3,990 / zombie expected_members 17종).
- 사이클 174 인계: 아침 08:46 마스터 델타 (잠정 → 확정 전환) + prepare DB일봉 전환 (사이클 173 HIGH 선행).
```

→ CHANGELOG: 사이클 171 행

## 사이클 161 (2026-06-17) — `_handle_buy_fill` 영역 체결단가 정합 시정 (HIGH 매매 안전성 직결)

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「체결단가 정합」 절)

```

사용자 보고 005940 NH투자증권 6/16 BUY trade_history 33,400원 vs HTS 33,350원 (+50원 차이) 시정. 근본 원인 = `_handle_buy_fill` 영역 `update_trade_status(BUY, COMPLETED, strategy=strategy_id)` 호출 시 `price` 인자 누락 → PENDING INSERT 시점 `record_price` (주문가 LIMIT / scanner `current_price` MARKET) 그대로 잔존 → KIS CNTG_UNPR (체결단가) 미반영.

### KIS MCP 정본 검증 (사이클 161)

- 체결통보 (H0STCNI0) 26 컬럼: `CNTG_UNPR` (체결단가, idx 10) = 실제 체결가
- 주문 응답 (TTTC0011U/TTTC0012U): `KRX_FWDG_ORD_ORGNO` + `ODNO` + `ORD_TMD` 3 키 + **체결가 응답 부재**
- `src/realtime/handler.py:166` 영역 = `price = int(fields[10])` = CNTG_UNPR 정합 확인

### 시정 영역 (`_handle_buy_fill` 사이클 147 패턴 100% 답습)

- 전량 체결 분기: `update_trade_status(BUY, COMPLETED, strategy=strategy_id, price=price)` — `price` 인자 명시
- 보정 INSERT UniqueViolation 영역: `try/except Exception` + `_update_trade_status_by_order_no(price=price)` 강제 UPDATE (사이클 147 `_handle_sell_fill` 패턴 답습)
- 부분 체결 분기: `update_trade_status(BUY, PARTIAL, strategy=strategy_id, price=price)` — `price` 인자 명시
- **cycle273a/273b(2026-09-10) 이후** 위 호출부(C1~C6 여섯 곳)는 전부 `order_no=order_no` 를 함께 넘겨 WHERE 를 그 주문 행으로 좁히고, 전량 체결 분기 2곳은 `match_partial=True` 로 PARTIAL 행까지 포괄한다(AST1/AST2 가 강제)

### 영속 의무 매트릭스

- 사이클 30 trade_history 부분 UNIQUE 인덱스 영속
- 사이클 38 명문화 영속
- 사이클 102 G-REJECT-1 callback exception raise 영속
- 사이클 147 `_handle_sell_fill` strategy fallback + UniqueViolation 강제 UPDATE 영속

### 매매 안전성 (변경 0 영역)

- risk.on_tick / realtime / auth 변경 0
- `_handle_sell_fill` 변경 0 (사이클 147 영속 영구 보존)
- 매도/익일청산/15:20 강제청산/손절 hot path 변경 0

### 회귀 가드 7 케이스 (HIGH 4 = 57%)

- `tests/unit/engine/test_cycle161_buy_fill_price_consistency.py`
- G-161-K-1 (HIGH): `_handle_buy_fill` 전량 체결 → `update_trade_status` price 인자
- G-161-K-2 (HIGH): trade_history.price = CNTG_UNPR 영구 정합
- G-161-K-3: 보정 INSERT UniqueViolation → `_update_trade_status_by_order_no` 강제 UPDATE
- G-161-K-4: 부분 체결 BUY price 인자 명시
- G-161-K-5 (HIGH): `_handle_sell_fill` 영역 price 인자 보존 (회귀 0)
- G-161-K-6: AST 정적 가드 = `_handle_buy_fill` 영역 `update_trade_status` 호출 시 `price=` keyword 의무
- G-161-SAFETY-1 (HIGH): risk / realtime / auth 변경 0

### 사이클 162+ 인계 (의제 A)

- 005940 SELL PENDING 잔존 정합 검증 (Supabase MCP 영역 권한 회복 시점)
- `_boot()` 영역 `_recover_pending_trades()` hook 도입 (당일 PENDING/PARTIAL 자동 sync chain)
- domain-expert 자문 필요 영역 (callback exception silent 자동 복구 chain 안전성)
```

→ CHANGELOG: 사이클 161 · cycle273a · cycle273b 행

## 사이클 153 (2026-06-16) — KOSPI200/KOSDAQ150 영역 복원 + stock_master is_kospi200/is_kosdaq150 컬럼 신규

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「저녁 데이터 적재」 절의 마스터 적재 + `src/db/CLAUDE.md` `list_by_filter` 항목)

```

사용자 보고 영역 = donchian step_no=1 "코스피200+코스닥150 합집합" survived 비정상 (실측 KOSPI200 1796 + KOSDAQ150 149 = ~1945 가능 → 영업일 종목 ≤ 5). 근본 원인 = 사이클 121 Plan Phase B silent 결함 (donchian_swing.py::_scan_universe() 영역 변경 시 KOSPI_200_TICKERS + KOSDAQ_150_TICKERS 합집합 → stock_master.list_by_filter(min_market_cap, min_trade_amount) 전환 시점에 KOSPI200/KOSDAQ150 필터 영역 완전 누락 + FUNNEL_STAGES[0] step_name 영속 미동기화). 사이클 122~152 영구 미시정.

### 사용자 결정 영속

- Q1=A KIS 공식 마스터 source (`kospi200_apnt_cls_code != ""` AND `ksq150_nmix_yn == "Y"`)
- Q2=A `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None` 인자 (사이클 108 nxt_tradable 답습)
- Q3=A TDD 정공

### migration 037 영역

- `is_kospi200 BOOLEAN NOT NULL DEFAULT FALSE` 신규 컬럼
- `is_kosdaq150 BOOLEAN NOT NULL DEFAULT FALSE` 신규 컬럼
- 부분 인덱스 2건 (`idx_stock_master_is_kospi200 WHERE is_kospi200=TRUE` / `idx_stock_master_is_kosdaq150 WHERE is_kosdaq150=TRUE`)
- IF NOT EXISTS idempotent + Supabase MCP apply_migration 운영 DB 즉시 적용 영역

### `_stock_master_master_load_once()` 영역 분기 확장

- `tagged_records: list[tuple[str, dict]]` 영역 = (`source`, `record`) 영역 (KOSPI/KOSDAQ 분리)
- KOSPI 분기: `record["kospi200_apnt_cls_code"].strip() != ""` → `is_kospi200=True`
- KOSDAQ 분기: `record["ksq150_nmix_yn"] == "Y"` → `is_kosdaq150=True`
- `upsert_master_raw(ticker, record, is_kospi200=..., is_kosdaq150=...)` 호출

### `upsert_master_raw()` 영역 확장

- 시그너처 신규 인자: `is_kospi200: bool = False`, `is_kosdaq150: bool = False` (사이클 146 nxt_tradable 패턴 답습)
- payload 영역 에 2 컬럼 동시 명시 (ON CONFLICT DO UPDATE 영역 이 명시된 키만 SET 의무)

### `list_by_filter()` 영역 확장 (`src/db/stock_master.py`)

- 신규 인자 `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None`
- 양쪽 True 시 `.or_("is_kospi200.eq.true,is_kosdaq150.eq.true")` OR 합집합 영역 (donchian 의무)
- 한쪽만 명시 시 `.eq()` 영역 (PostgREST 인덱스 활용)
- 양쪽 None 시 무필터 (회귀 보존)
- Python-side mock 환경 영역 폴백

### `donchian_swing.py::_scan_universe()` 영역 시정

- `list_by_filter(..., is_kospi200=True, is_kosdaq150=True,...)` 호출
- FUNNEL_STAGES[0] step_name "코스피200+코스닥150 합집합" 영역 (변경 0)

### 매매 안전성 무영향

- scanner 단계 매수 진입 *전* 영역만 (사이클 38 명문화 영속)
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
- 사이클 32 R4 보유/익일청산 절대 보호 영속 (영향 0)

### 영속 의무 매트릭스

- 사이클 32 R4 보유/익일청산 절대 보호
- 사이클 38 명문화 (scanner 매수 진입 전 한정)
- 사이클 81 G-AST1 raw JSONB 영역 보호 (신규 컬럼 = raw 영역 외부)
- 사이클 108 list_by_filter 패턴 답습 (nxt_tradable 영역 정합)
- 사이클 121 Q2=D 임계 완화 영속 (변경 0)
- 사이클 129 master_raw 영역 영속 (변경 0)
- 사이클 143 FUNNEL_STAGES 영속 (donchian step_name)
- 사이클 146 upsert_master_raw 영역 nxt_tradable 명시 영속 답습

### vcp_breakout 영역 영향 0 (사이클 153 범위 외)

- `vcp_breakout.py:726, 732` 영역 KOSPI_200_TICKERS + KOSDAQ_150_TICKERS hardcoded list 영역 변경 0
- scanner.py hardcoded list (~124 종목 영역) 폐기는 사이클 154+ 인계 (vcp_breakout 영역 영향 평가 후)

### 회귀 가드 16 케이스 (HIGH 8 = 50%)

- `tests/unit/db/test_cycle153_list_by_filter_index_flags.py` 5 케이스 (G-153-FILTER-1~5)
- `tests/unit/engine/test_cycle153_master_load_kospi200_kosdaq150.py` 3 케이스 (G-153-MASTER-1~3)
- `tests/unit/engine/strategies/test_cycle153_donchian_index_filter.py` 5 케이스 (G-153-DONCHIAN-1~3 + G-153-SAFETY-1/3)
```

→ CHANGELOG: 사이클 153 행

## 사이클 129 (2026-06-14) — KIS 공식 일일 마스터 파일 도입 + master_raw 별도 컬럼 + 16:30 KST 자동 task

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「저녁 데이터 적재」 절의 마스터 적재·진입 차단 7건)

```

사용자 verbatim "종목마스터 만들 때 아래 소스코드 참고해줘" + KIS 공식 샘플 코드 제공. 사용자 결정 Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼 + Q12=A × 100 단위 환산 + Q9=B 단계별 분할 진행.

### `scanner.py` 신규 영역 (+289L)

- **사이클 167 폐기 (dead code, callsite 0건)**: `market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions` 3 시총 헬퍼 영구 폐기. 사이클 129 도입 이후 production 호출 0건 (서로만 호출하는 폐쇄 그래프). 실제 시총 필터는 `list_by_filter` / `list_paged_by_filter` 가 직접 수행 (사이클 166 억원 정합 완료). AST 영구 가드 = `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` (3 함수 부재 + 미래 재발 차단). 사이클 103 strategy.py dead code 폐기 패턴 답습.
- `_is_master_blocked_for_entry(ticker)` — **1단계 차단 7건** (master_raw 우선 + raw 폴백 chain): `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기 (KOSDAQ 전용)
- `_stock_master_master_load_once(force=False)` — KIS 공식 파일 다운로드 (`src/api/kis_master.py`) + `master_raw` 배치 upsert + 진행 emit + graceful (사이클 88) + `refresh_progress` integration (사이클 127)

### `scheduler.py` 신규 16:30 KST task (+86L)

- `TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)` — 일봉 task 16:00 / basics task 16:10 직후 안전 마진 + KIS 마스터 갱신 시점
- `_stock_master_master_load_task_loop()` — start() 직후 즉시 1회 + 매일 16:30 KST while 루프 (사이클 106 lifecycle race 차단 답습)
- `task_attrs` 4 위치 영속 (instance + `connect().finally` + `run_daily.finally` + `stop()`) — 사이클 79 G-AST2 영속 / expected_members 14 → 15

### 매매 안전성 무영향

- scanner 단계 매수 진입 *전* 영역만 (사이클 38 명문화 영속)
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
- 1단계 차단 7건 hook = 매수 진입 *전* 차단 (이미 보유 종목 영향 0)

### 영속 의무 매트릭스 (사이클 129 영구 확인 영역)

- 사이클 17 KIS LMS chain (외부 HTTP 1회 + 사이클 122 50ms sleep 답습)
- 사이클 38 명문화
- 사이클 79 G-AST2 task_attrs 4 위치 (`_stock_master_master_load_task`)
- **사이클 81 G-AST1 raw 영역 영구 보호 (master_raw 별도 컬럼 분리 = 절대 보호)**
- 사이클 84 L-2 POST 화이트리스트 (4 라우트 영속)
- 사이클 88 G-REJECT graceful
- 사이클 106 lifecycle race 차단
- **사이클 116 단위 환산 패턴 100% 답습 (× 100)**
- 사이클 122/126 task 패턴 100% 답습
- 사이클 127 fire-and-forget + refresh_progress TaskKey 4 확장
```

→ CHANGELOG: 사이클 129 · 사이클 167 행

## 사이클 127 (2026-06-13) — 3 작업 fire-and-forget + 5초 폴링 진행 가시화

### 2026-09-17 이관 — 절 전문 (사이클 176 raw 머지 포함 — 현행 규칙 = 정본 모듈 맵 `refresh_progress.py` + 「저녁 데이터 적재」 절의 basics 갱신)

```

사이클 126 사용자 보고 — 기본정보 새로고침 13분 39초 후 "KIS API 일시 결함" 토스트. 운영 로그 = 백엔드 정상 완료(updated=2697/2697). 진짜 결함 = **axios 클라이언트 디폴트 timeout silent 결함**. 사용자 결정 Q1=5초 폴링 (경량) + Q2=상단 배너+카운터 + Q3=3 작업 통일.

### `refresh_progress.py` 신규 (3 작업 통합 state)

- 모듈 전역 `_progress: dict[TaskKey, dict]` (universe/basics/daily 3 키) + `threading.Lock` (FastAPI 동시 요청 + BackgroundTasks race 차단)
- 각 state schema (10 키): `status` (idle/running/completed/failed) + `total/processed/updated/skipped/failed` + `started_at/finished_at` (KST `+09:00` ISO) + `elapsed_ms` + `error_message`
- 헬퍼: `start_progress(task_key, total)` / `update_progress(task_key, **kwargs)` / `finish_progress(task_key, status, **kwargs)` / `get_progress(task_key) -> dict` / `get_all_progress() -> dict[TaskKey, dict]` / `is_running(task_key) -> bool` (409 Conflict 판정용) / `reset_progress(task_key)` + `reset_all_progress()` (테스트 전용)
- **uvicorn 단일 워커 필수** (process-local in-memory state). multi-worker 시 state 불일치 silent 결함 발생.

### `scanner.py::_stock_master_basics_refresh_once()` (사이클 126 추가 영역)

- KRX 1차 폴백의 `nxt_tradable=False`/`krx_halted=False`/`admin_item=False` 하드코딩 결함 시정. KIS `inquire_stock_basics()` (CTPF1002R + FHKST01010100 merge, 사이클 107 영속) 매스 호출 → `stock_master.upsert_one()` 갱신
- **사이클 176 (2026-06-25) — 기존 raw 머지 보존 (거래대금 결손 시정)**: `list_all` 로드 시 `existing_raw_by_ticker: dict[str, dict]` 에 기존 row 의 `raw` 보관 → upsert *전* `_new_raw = getattr(basics, "raw", None)` 이 dict 이고 `_prev_raw` 비어있지 않으면 `basics = basics.model_copy(update={"raw": {**_prev_raw, **_new_raw}})` 머지. 근본 = `inquire_stock_basics` 가 `merged_raw = dict(ctpf_output)` 로 raw 신규 빌드 (기존 DB raw 미read) + 개장 전 FHKST `acml_tr_pbmn=0` → cycle 145 `_ZERO_VALUE_SKIP_KEYS` skip → 거래대금 부재 + `upsert_one` raw 통째 교체 → 부팅 전 refresh 가 매일 전 종목 거래대금 삭제 (cycle 145 "기존 raw 보존" 은 read-merge 부재로 no-op, 운영 실측 6/3573 → VB/LTV/donchian/BFB universe 0). 머지가 cycle 145 skip 15키 (거래대금/거래량/per/pbr/외국인/신고가/실적) 를 기존 값에서 보존, 새 키 우선. blast radius 최소 (scanner 한정 + 추가 DB read 0, `upsert_one` 전역 의미변경 회피). bare-object (`model_copy`/`raw` 부재) `getattr` graceful (기존 cycle126 테스트 회귀 0). 매매 안전성 무영향 (매수 진입 전, 사이클 38). 회귀 가드 `tests/unit/engine/test_cycle176_basics_refresh_raw_merge.py` (5)
- 페이징 `stock_master.list_all()` (PAGE_SIZE=1000) + Rate Limit `await asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS=0.05)` (사이클 17 KIS LMS chain 답습)
- graceful: KIS 거부 → `[stock_master_basics_refresh_skip] ticker=X reason=Y` WARNING + `failed++` continue (사이클 88 G-REJECT 답습)
- 500건마다 `[stock_master_basics_refresh]` INFO 진행 emit + 종료 시 `[stock_master_basics_refresh_summary] total=N updated=K skipped=L failed=M elapsed_ms=X` 1행
- 2,697 종목 × ~100ms ≈ 13분 소요

### 라우트 fire-and-forget 전환 (routes/stock_master.py)

- 3 POST 라우트 (`/refresh-universe` + `/basics/refresh` + `/daily/refresh`) 모두 **FastAPI `BackgroundTasks`** 사용. response 전송 *후* schedule (axios timeout 영구 차단)
- `asyncio.Lock` 폐기 → `refresh_progress.is_running()` state 기반 가드 (single source of truth)
- 응답 schema 변경: 동기 summary `{universe, fetched, elapsed_ms,...}` → `{status: "started", task_key}`
- `_run_universe_background` / `_run_basics_background` / `_run_daily_background` 3 wrapper — once 함수 호출 + Exception 시 `finish_progress("failed", error_message=str(exc))` 안전망
- 신규 라우트 `GET /refresh-progress` — 3 작업 통합 응답 (5초 폴링 endpoint)

### `_stock_master_basics_refresh_task_loop()` (스케줄러 신규 task — 사이클 126)

- `TIME_STOCK_MASTER_BASICS_REFRESH = time(16, 10)` (일봉 task 직후 안전 마진)
- start() 직후 즉시 1회 실행 + 매일 16:10 KST 정기 (사이클 106 lifecycle race 차단 답습)
- `task_attrs` 튜플 3곳 (`stop()` + `run_daily.finally` + `connect()` finally) 에 `"_stock_master_basics_refresh_task"` 추가 (사이클 79 G-AST2 영속)

### 영속 의무 매트릭스 (사이클 127 영구 확인 영역)

- 사이클 17 KIS LMS chain (50ms sleep 영속)
- 사이클 38 명문화 (scanner 단계 매수 진입 전용, 매도/익일청산 hot path 무관)
- 사이클 79 G-AST2 task_attrs 3곳 영속 (`_stock_master_basics_refresh_task` 추가)
- 사이클 84 L-2 POST 화이트리스트 (3 라우트 영속)
- 사이클 88 G-REJECT graceful (개별 ticker 실패 → continue)
- 사이클 90 `_refresh_universe_lock` 폐기 → state 기반 가드 의미 전환 (사이클 66 K-2 패턴 답습, xfail 의미 전환 9건)
- 사이클 106 lifecycle race 차단 (start() 즉시 1회 + while 루프 영속)
- 사이클 107 CTPF1002R + FHKST01010100 merge 영속
- 사이클 122 일봉 task 패턴 영속

### 회귀 가드 (사이클 127 격리 33 PASS, flakiness 0)

- engine `test_cycle127_refresh_progress_state.py` (11 케이스 — state 머신 transition + reset + concurrent 호출)
- routes `test_cycle127_progress_routes.py` (14 케이스 — 3 POST 라우트 started/409/BackgroundTasks 등록/응답 즉시 + GET schema + idle 디폴트). **TestClient 의존 폐기 + 라우트 함수 직접 await 호출** (anyio portal event loop hang silent 결함 영구 차단)
- ast `test_cycle127_ast_progress_hooks.py` (8 케이스 — 모듈 영속 + G-AST4 `background_tasks.add_task ≥ 3` + `asyncio.create_task == 0`)

### 운영 효과 (push + EC2 자동 배포 후)

- UI "기본정보 새로고침" 클릭 → 즉시 202 응답 (timeout 0) + 상단 배너 5초 폴링으로 1500/2697 진행률 실시간 가시화
- 동일 패턴 3 작업 통일 (universe + basics + daily)
- 자동 task = 매일 16:00 일봉 + 16:10 basics 정기 발화
```

→ CHANGELOG: 사이클 126 · 사이클 127 · 사이클 176 행

## 사이클 126 (2026-06-13) — 종목마스터 UI/데이터 결함 4건 통합 시정

### 2026-09-17 이관 — 절 전문 (현행 규칙 = 정본 「저녁 데이터 적재」 절 + `src/db/CLAUDE.md`)

```

사용자 보고 4건: (1) 전체현황 1000 cap (2) 목록 데이터 부족 (3) NXT/거래정지/관리종목 입수 누락 (4) 일봉 task 미발화.

### 결함 1 시정 — `stock_master.get_stats()` count="exact" 디코딩

- PostgREST 디폴트 1000행 한도 → `len(rows) ≤ 1000` cap. 시정: count 전용 `.select("ticker", count="exact").limit(0)` + raw 분석 `.range(0, 9999)` 분리. `count_all = 2,697` 정확 반영

### 결함 3 시정 — KIS CTPF1002R 매스 보강 자동 task + 수동 trigger

- 자동 task: `scheduler.TIME_STOCK_MASTER_BASICS_REFRESH=16:10` + `_stock_master_basics_refresh_task_loop()` (start() 즉시 1회 + 매일 16:10 KST)
- 수동 trigger: `POST /api/stock-master/basics/refresh` (사이클 127 fire-and-forget 전환)
- 적재 함수: `scanner._stock_master_basics_refresh_once()` — `inquire_stock_basics()` (사이클 107 merge) + **사이클 176 기존 raw 머지 보존** (`{**기존, **신규}`, 거래대금 결손 시정) + `upsert_one()` + Rate Limit 50ms sleep + graceful
- metrics 모듈: `stock_master_basics_metrics.py` (record/flush 페어링, 사이클 122 답습)
- 운영 실측 (2026-06-13 10:46 KST 시작 → 11:00:22 완료): updated=2697/2697, NXT 가능 400 / 거래정지 60 / 관리종목 57 (이전 0/0/0 영역에서 정상 분포 입수)

### 결함 4 시정 — 일봉 task 진단 강화 + 수동 trigger

- `scanner._stock_master_daily_load_once()` (사이클 122 영속) 영역에 진단 로그 강화 + `db_write_failures` 카운터
- 수동 trigger: `POST /api/stock-master/daily/refresh` (사이클 127 fire-and-forget)

### 매매 안전성 무영향

- scanner 단계 매수 진입 *전* 영역만 변경 (사이클 38 명문화 영속)
- `risk.on_tick` / `order_engine` / `realtime/` / `auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
```

→ CHANGELOG: 사이클 126 행

## 사이클 122 (2026-06-12) — KIS 일봉 도입 + `stock_master_daily` 적재 task (→ 「저녁 데이터 적재」 · 「일봉 적재 본체」)

### 2026-09-17 이관 — 사이클 절 전문(사용자 결정 Q1~Q4 · 도입 당시 시각 16:00 · 영속 의무 · 운영 효과 · 회귀 가드 · 사이클 123+ 인계)

```
## 사이클 122 (2026-06-12) — KIS 일봉 도입 + `stock_master_daily` 적재 task

사용자 결정 Q1=A + Q2=C + Q3=B + Q4=B (team-leader 권고 채택).

### 핵심 사실

- **신규 KIS API 도입 0건** — `fetch_daily_candles` (사이클 14, `src/api/condition.py`) 100% 재사용
- **영속화만 추가** — memcache 5분 TTL → DB 적재로 전환
- DB 적재 단계만 추가, 전략 prepare 영역 전환은 사이클 123+ 별개

### `scanner.py::_stock_master_daily_load_once` (+168L)

- 호출: `_stock_master_daily_load_task_loop` 매일 **20:30** KST(cycle283 D2 — 종전 16:00 → 18:10 → 20:30, 09-14 KRX 애프터마켓 종료 20:00 뒤) 1회
- 분기 로직: `max_bas_dd(ticker)` 사용 — 부재 시 백필 (T-100일), 존재 시 증분 (1일 단위)
- KIS `fetch_daily_candles(ticker, days=N)` 호출 → `upsert_batch(ticker, rows)` 영속화
- graceful (사이클 88 G-REJECT 답습) — KIS 거부/타임아웃 시 ticker skip 후 다음 진행
- emit: `[stock_master_daily_load_summary]` 1행 INFO (tickers_total / inserted / skipped / failed / elapsed_ms)

### `scheduler.py` — 일봉 적재 task lifecycle (아래 시각은 **사이클 122 당시 값** — 현행은 20:30)

- `TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0)` (사이클 122 — KRX 메인 종료 30분 후 안전 마진). **현행 값은 `time(20, 30)`**(cycle283 D2, 위 `:488` 참조) — 아래 16:00 서술은 도입 당시 기록이다
- `_stock_master_daily_load_task_loop`: start() 직후 즉시 1회 + 매일 지정 시각 while 루프 (사이클 106 lifecycle race 패턴 답습)
- stop() task cancel 3곳 추가 (`_stock_master_daily_load_task` — `expected_members` 13종 갱신, 사이클 79 G-AST2 답습)

### 영속 의무

- 사이클 14 `fetch_daily_candles` 재사용 (신규 KIS API 도입 0건)
- 사이클 38 명문화 — scanner 단계 매수 진입 전 한정 (매도/익일청산 hot path 무관)
- 사이클 49 VCP Pullback ATR ZigZag = 캔들 입력만 의존 (행위 영향 0)
- 사이클 79 G-AST2 task cancel 영속
- 사이클 81 G-AST1 raw JSONB 덮어쓰기 금지 답습
- 사이클 106 lifecycle race 차단 패턴 (start() 즉시 1회 + while 루프)

### 운영 효과 (push + EC2 자동 배포 후)

- 16:00 KST start() 직후 1회 백필 — 2,700 종목 × 100ms ≈ 4.5분 소요
- 매일 16:00 KST D-1 영업일 증분 1행 추가
- DB 부담: 270K 행 × 80 bytes ≈ 22MB (Supabase 무료 tier 500MB 의 4.4%)
- donchian/VCP/VB 전략 선시행 데이터 준비 완료 (사이클 123+ 전환)

### 회귀 가드 (사이클 122 격리 34 PASS, flakiness 0)

- `tests/unit/db/test_cycle122_stock_master_daily.py` 15 케이스
- `tests/unit/engine/test_cycle122_daily_load_task.py` 11 케이스
- `tests/unit/ast/test_cycle122_kis_tr_id_persistence.py` 4 케이스 (FHKST03010100 TR_ID 영속)
- `tests/unit/engine/test_scheduler_stop_zombie_tasks.py` expected_members 13종 갱신 (사이클 79 G-AST2 답습)

### 사이클 123+ 인계

- HIGH: donchian/VCP/VB prepare 영역에서 `get_donchian_high` / `get_atr` / `get_recent_daily_with_fallback` 헬퍼 전환
- LOW: 90일 retention cron (사이클 6 답습)
- D+1 운영 실측 (다음 영업일 16:00 KST `[stock_master_daily_load_summary]` emit 확인)

```

→ CHANGELOG: 사이클 122 행 · cycle273f 행 · cycle283 행

## 사이클 106 (2026-06-11) — `_full_universe_load_task_loop` lifecycle race 영구 차단 (start() 직후 즉시 1회 + while 루프) (→ 「정기 task 루프」)

### 2026-09-17 이관 — 사이클 절 전문(사용자 보고 verbatim · 변경 전/후 · 영속 의무 매트릭스 · 운영 효과 191→2,800 ticker)

```
## 사이클 106 (2026-06-11) — `_full_universe_load_task_loop` lifecycle race 영구 차단 (start() 직후 즉시 1회 + while 루프)

사용자 보고 (verbatim): "종목마스터 갱신작업 점검이 금일 내로 완료되어야 할 것 같아. 현재 종목마스터의 상단에 있는 메시지는 이제 무효한거 아닌가? 점검해서 UI에서 지우고 프론트와 백엔드 모두 현행화하길 바래." Phase 1 진단 결정적 발견: stock_master 191 ticker = 사이클 101 `_full_universe_load_task_loop` 어제 (2026-06-10 수) 20:00:05 **미발화** 영역 확정. root cause = start() 직후 → `_wait_until(20:00:05)` 영역 대기 중 → 20:10 _settle → stop() cancel 발화 = **lifecycle race**.

### `_full_universe_load_task_loop` start() 직후 즉시 1회 + while 루프

- **위치**: `src/engine/scheduler.py::_full_universe_load_task_loop` (+21/-14L 순증 +7L)
- **변경 전 (사이클 101)**: while 루프 `_wait_until(20:00:05)` 후 호출 → start() 직후 대기 → lifecycle race 영역
- **변경 후 (사이클 106, 2026-06-11)**:
 1. **start() 직후 즉시 1회 실행 블록** — `_full_universe_load_once()` 호출 + try/except graceful (CancelledError → return / Exception → graceful `logger.exception("[full_universe_load] 초기 실행 실패 graceful")`)
 2. **while 루프 블록** — `_wait_until(20:00:05)` 무한 루프 (CancelledError → break / Exception → graceful `logger.exception("[full_universe_load] while 루프 실패 graceful") + asyncio.sleep(60)`)
- **사유**:
 - 사이클 101 시점 silent 결함 영구 차단 (start() 직후 대기 → 20:10 _settle → stop() cancel = lifecycle race 영구 차단)
 - 사이클 78 G-AST1 + 79 G-AST2 영속 (`_full_universe_load_task` stop 튜플 포함, lifecycle 영역 답습)
 - 사이클 83 `_scan_pool_eager_refresh_task` 영속 답습 (start() 직후 즉시 1회 + while 루프 + asyncio.sleep)
 - is_stale 24h TTL idempotency 영역 활용 = 동일 영업일 2회 실행 시 24h TTL idempotent (`stock_master.is_stale()` 영속)
 - asyncio.sleep(60) = KIS LMS chain 안전 마진 영속 (사이클 17 OPSP0002 backoff 영속 답습)

### 영속 의무 매트릭스 (사이클 106 영구 확인 영역)

- **사이클 32 R4 universe guard 영속** (보유/익일청산 절대 보호)
- **사이클 38 명문화 영속** (영역 3 = scheduler lifecycle 영역, 매수 진입 전 영역 한정 + 매도/손절/익일청산/15:20 강제청산 hot path 무관)
- **사이클 78 G-AST1 + 79 G-AST2 영속** (`_full_universe_load_task` stop 튜플 포함, 영역 3 lifecycle 영역 답습 + `_api_recovered_collector_task` cancel 영구 가드 영속)
- **사이클 88 G-REJECT 영속** (재구독 영역 영구 보존, 영역 3 = lifecycle 영역 차단만, 재구독 영역 변경 0)
- **사이클 101 영속 영구 확인** (`_full_universe_load_once` 함수 영역 변경 0, lifecycle 영역만 시정)
- **사이클 102 G-REJECT 영속** (양 agent 일치, 매수/매도/익일청산 hot path 영역 보존 의무)
- **사이클 49→106 누적 61 사이클 + hotfix 14 영역 영속**

### 운영 효과 (push + EC2 자동 배포 후)

- `[full_universe_load] 초기 실행 완료 total=N kospi=K kosdaq=L` start() 직후 즉시 1회 emit ()
- 매일 20:00:05 while 루프 정기 실행 영역
- stock_master 191 ticker → **~2,800 ticker 정상화 영역 ** (KOSPI ~1,400 + KOSDAQ ~1,400, 사이클 99 60 ticker 영역 회복 + 사이클 100 3 prefix OR)
- 매매 안전성 무영향 (영역 3 = lifecycle race 차단 영역 한정 + 매수/매도/익일청산/15:20 강제청산 hot path 무관)

```

→ CHANGELOG: 사이클 106 행

## 사이클 103 (2026-06-11) — strategy.py dead code 영구 폐기 + momentum.py 손절 로그 임계 동행 emit (→ 「절대 깨지면 안 되는 규칙」)

### 2026-09-17 이관 — 사이클 절 전문(코미코 183300 회고 · 변경 전/후 로그 서식 · 폐기 라인 수 · 영속 의무 매트릭스)

```
## 사이클 103 (2026-06-11) — strategy.py dead code 영구 폐기 + momentum.py 손절 로그 임계 동행 emit

사이클 102.5 회고 결정적 사실: 코미코(183300) 2026-06-11 10:03 매수 138,200원 → 13:21:30 STOP_LOSS 매도 138,200원. 단일 근본 원인 = DB `strategy_config.momentum.params.stop_loss_rate = -2.4%` (2026-06-03 22:11 KST 사용자 수동 apply). 매도 시점 loss_rate = -2.604% ≤ -2.4% 만족 → momentum.py STOP_LOSS 분기 정상 작동. 사용자 의문 = 코드 DEFAULT `-7.5%` 가정 → 운영 영역 `-2.4%` 가시화 부족 → 오인. **결함 영역 = 아님** (코드 정상, 운영 가시화 영역 보강 의무).

### 영역 2 — `momentum.py:127` 손절 로그 임계 동행 emit

- **변경 전**: `logger.info("손절 신호: %s(%s) 매수가(%d) 대비 %.1f%% (현재가: %d)", strategy_name, ticker, buy_price, loss_rate * 100, current_price)`
- **변경 후 (사이클 103, 2026-06-11)**: `logger.info("손절 신호: %s(%s) 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)", strategy_name, ticker, buy_price, loss_rate * 100, stop_loss * 100, current_price)` (+1 인자 `stop_loss` 임계 동행 emit)
- **사유**:
 - 사이클 102.5 회고 결정적 사실 (코미코 사례 운영자 오인 영역 영구 차단)
 - 미래 동일 영역 운영자 오인 영구 차단 (운영자 즉시 임계 확인 가능)
 - 사이클 89 한글 친숙 용어 영속 답습 + 사이클 102 가시화 영역 보강 답습

### 영역 3 — `strategy.py` dead code 영구 폐기 (callsite 0건 확인 후 안전 폐기)

- **폐기 영역 (L85~L207, -119L 순감)**:
 - `check_buy_signal(ticker, current_price, recent_high, params, position_count_today)` — 64L 매수 신호 판단 모듈 함수 (callsite 0건 확인)
 - `check_stop_loss(ticker, current_price, buy_price, params)` — 21L 손절 판단 모듈 함수 (callsite 0건 확인)
 - `check_next_day_clear(ticker, current_price, buy_price, params)` — 34L 익일 청산 판단 모듈 함수 (callsite 0건 확인)
- **보존 영역 ()**:
 - `class Signal` + `class Position` + `class StrategyState` (사용 영역 영속)
 - 7 상수 (`MOMENTUM_RECENT_HIGH_DAYS` 등 사용 영역 영속)
 - `calc_buy_quantity()` (사용 영역 영속)
- **AST 영구 가드 신설**: `tests/unit/ast/test_cycle103_ast_no_dead_strategy_funcs.py` (3 함수 영구 부재 영구 가드 + 미래 재발 영구 차단)
- **사유**:
 - callsite 0건 확인 (전체 production codebase grep + tests/ grep 모두 0건)
 - 사이클 78 G-AST1 + 79 G-AST2 영속 패턴 답습 (dead code 안전 폐기 + AST 영구 가드 신설)
 - 코드 정합성 영속 (사이클 49→103 누적 58 사이클 영속 영역)

### 영속 의무 매트릭스 (사이클 103 영구 확인 영역)

- **사이클 38 명문화 영속** (영역 2 매도 hot path 영역 — momentum.py STOP_LOSS 분기 PRE/MAIN/POST 무관 항상 작동)
- **사이클 78 G-AST1 + 79 G-AST2 영속** (영역 3 dead code 폐기 + AST 영구 가드 영역 답습)
- **사이클 89 한글 친숙 용어 영속** (영역 2 로그 한글 메시지 영속)
- **사이클 102 G-REJECT 영속** (양 agent 일치, 매수/매도/익일청산 hot path 영역 보존 의무)
- **사이클 49→103 누적 58 사이클 + hotfix 14 영역 영속**

### 운영 효과 (push + EC2 자동 배포 후)

- momentum.py 손절 로그 = 임계 동행 emit (운영자 즉시 임계 확인 가능, 코미코 사례 운영자 오인 영구 차단)
- strategy.py = dead code 영구 폐기 (코드 정합성 영속 + 미래 재발 영구 차단 AST 가드)
- 매매 안전성 무영향 (영역 2 = 로그 메시지 1줄 보강 영역 + 영역 3 = dead code 영구 폐기 (callsite 0건 확인) = 매수/매도/익일청산/15:20 강제청산 hot path 무관)

```

→ CHANGELOG: 사이클 103 행

## 사이클 102 (2026-06-11) — force_retry 임계 상향 + flush 호출 사이트 영구 확인 (→ 「scheduler.py」 stale watcher 절)

### 2026-09-17 이관 — 사이클 절 전문(사이클 29 R1 → 102 임계 상향 경위(Q73=B) · 운영 효과 예상 124~141→50~70건/일 · 영속 의무 매트릭스)

```
## 사이클 102 (2026-06-11) — force_retry 임계 상향 + flush 호출 사이트 영구 확인

사용자 신규 요구 "재구독 로직 자체가 실수가 아닌가 싶어. 시세구독 관련 부분을 전면 새로운 시각에서 재검토" + refactor-expert + domain-expert 병렬 자문 일치 (사이클 88 G-REJECT + 임계 상향 영역 안전 마진 2 배 확장). 사용자 결정 Q73=B (5분 → 10분 + 12회 → 6회).

### `stale_diagnostics.py::STALE_FORCE_RETRY_AFTER_SECS` + `STALE_FORCE_RETRY_HOURLY_CAP` 임계 상향

- **위치**: `src/engine/stale_diagnostics.py:29~32`
- **변경 전 (사이클 29 R1, 2026-05-21)**: `STALE_FORCE_RETRY_AFTER_SECS = 300` (5분) + `STALE_FORCE_RETRY_HOURLY_CAP = 12` (시간당 12회)
- **변경 후 (사이클 102, 2026-06-11)**: `STALE_FORCE_RETRY_AFTER_SECS = 600` (10분) + `STALE_FORCE_RETRY_HOURLY_CAP = 6` (시간당 6회)
- **사유**:
 - KIS LMS chain 사고 안전 마진 2 배 확장 (사이클 29 005935 chain 진단 의무 영속)
 - 운영 실측 예상 (124~141건/일 → 50~70건/일 영구 감소)
 - 사이클 29 R1 영속 (임계 상향만, 영역 폐기 0 — 사이클 102 = 사이클 29 R1 임계 상향 영역 답습 + 시간 척도 유지)
- **영속 의무 영역 (변경 0)**: `MAX_STALE_RETRIES = 5` 영속 (사이클 17 보강) + `STALE_FRESHNESS_SECS = 60` 영속 (사이클 61 Phase 2-A2 이전 영역) + `_resubscribe_stale_priority` cap=10 priority 분리 *후* 적용 영속 (사이클 66 K-10) + **`RESUBSCRIBE_THROTTLE_SECS = 3 × STALE_FRESHNESS_SECS = 180`** (cycle216 LOW throttle, **`< 300`(함수 5분 주기) 불변식** — self-block 시 cycle215 split-brain 복구 원복 방지). + **`resubscribe_stale_priority` LOW desired 교집합**(cycle240 — desired_low = `scheduler._collect_breakout_tickers()` ∪ `scanner._last_scan_result`, 활성 게이트 = breakout(scheduler 소유 소스) 비어있지 않음 ∧ HIGH 수집 무예외, momentum 은 게이트 불참, **HIGH 면제·`low_targets` 한정**, 순서 = 분리 → 필터 → cycle216 A/B → cap, 게이트 off 시 현행 byte 동일 fail-open — AST `test_cycle240_ast_desired_filter.py` G-240-1~7 봉인. `kis_ws_pool.get_subscribed_tickers()` 를 desired 로 쓰는 것은 cycle215/217 split-brain 복구 계약 무력화라 **금지**).

### `scheduler.py::_api_recovered_collector_loop` flush 호출 사이트 영구 확인 (영역 1 변경 0)

- **위치**: `src/engine/scheduler.py:2543~L2565` (`_api_recovered_collector_loop`) + `stop()` (L923~L928) lifecycle hook
- **사이클 78 G-AST1 영역 영속 영구 확인 (변경 0)**: `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 5분 주기 호출 영속 + `stop()` lifecycle hook 양쪽 flush 영속.
- **사이클 102 신규 추가 (handler.py flush 영역 chain)**: `flush_silent_drop_count` import (L41) + 5분 주기 호출 (L2567~L2571) try/except graceful (사이클 78 G-AST1 영역 답습 — 동일 collector loop 영역 chain).
- **AST 영구 가드 5 신설**: G-78-VERIFY-1~5 (`[swing_rest_poll_summary]` + `[stale_watcher_summary]` emit 영속 + flush 호출 사이트 3 (collector loop / stop / 5분 주기) 영속 + 사이클 102 신규 flush 영역 chain 영속).

### 영속 의무 매트릭스 (사이클 102 영구 확인 영역)

- **사이클 29 R1 영속**: 임계 상향만, 영역 폐기 0 (시간 척도 + cap 영역 유지)
- **사이클 32 R4 universe guard 영속**: 보유/익일청산 절대 보호
- **사이클 66 cap=10 priority 분리 영속**: HIGH > cap 절대 보장
- **사이클 67 stale_manager 4 sub-module 영속**: stale_diagnostics + stale_session_recovery + stale_universe_guard + stale_watcher_core
- **사이클 78 G-AST1 flush 호출 사이트 영속**: collector loop / stop / 5분 주기 (영역 1 변경 0 영구 확인)
- **사이클 79 G-AST2 task cancel 영속**: `_api_recovered_collector_task` cancel 목록 영속
- **사이클 88 G-REJECT-1/2/3 **: 외부 LLM 단순 graceful 추천 거부 + 재연결 trigger 영역 영구 보존
- **WebSocket 4중 안전망 영속**: F1 + `_scan_loop` + K stale watcher + `_resubscribe_stale_priority`
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**

### 운영 효과 예상 (push + EC2 자동 배포 후)

- `[stale_force_retry]` 124~141건/일 → **50~70건/일 영구 감소** (LMS chain 안전 마진 2 배 확장)
- `[swing_rest_poll_summary]` / `[stale_watcher_summary]` / `[dispatch_drop_summary]` 5분 주기 emit 영속 (사이클 74/78/102 통합 가시화)
- 사이클 88 G-REJECT-1 callback `raise` 영속 = WebSocket 재연결 자연 발화 영역 영구 보존
```

→ CHANGELOG: 사이클 102 행

## strategy_base.py

### 2026-09-17 이관 — 생명주기 훅(사이클 185 클러스터 ①)·트레일링 기준점 복구(H-1) 도입 경위와 인계 목록

```
- **생명주기 훅 (사이클 185 클러스터 ①, 기본 no-op + 서브클래스 override)**: `_reset_daily_state()` — 일일 transient cross-day 상태 정리. `scheduler._reset_daily_state`(21:30 정산 후 — cycle283 D3) registry 순회가 전략별 호출(try/except graceful). override = momentum `_prev_prdy_rate.clear()`(strat-4 익일 첫틱 거짓돌파 차단) + BFB `_breakout_first_seen.clear()`(strat-3, 기존 L978 고아였던 메서드 이제 배선). **보유결합 필드(_limit_up_reached/_partial_exit)는 본 훅 금지** — 익일 보유(LTV 상한가 종목 밤샘) 청산 모드가 깨짐. `on_position_closed(ticker)` — 포지션 전량 청산(매도 체결) 시 per-ticker 보유결합 상태 정리. order_engine 2 site(`_handle_sell_fill` 전량체결 `if pos:` 후 + `execute_sell` insufficient_qty reconciliation, 각 try/except 격리)에서 호출. override = LTV `_limit_up_reached.discard(ticker)`(strat-2 재매수 종목 전일 상한가 모드 누설 차단) + BFB `_partial_exit.pop(ticker, None)`(strat-5 재진입 익절 억제 차단) **+ 사이클 191 — BFB·VCP `register_cooldown_after_exit(ticker)` + `asyncio.create_task(_refine_cooldown_business_days)` 배선**(재진입 쿨다운 최초 실효 — 즉시 달력일 근사(days+2) 후 CTCA0903R `add_business_days` 로 정확 N영업일 정정, VCP 는 191 에서 override 신설. `_cooldown_until` 은 multi-day 상태 — 일일/prepare 리셋 금지 AST G-191-NO-DAILY-RESET). 불변식 = "보유 중 flag 유지, 전량 매도 시 clear" (포지션 제거 site 정확히 2곳 = 누설 구조적 봉쇄, AST G2-STRUCT-INVARIANT 가 3번째 site 누락 영구 차단). 부분 체결은 full-fill 한정이라 잔량 청산모드 자연 보존. domain-expert 조건부 GO `_workspace/domain_consult/cycle185_position_closed_cleanup.md`. 매매 안전성 8영역 diff 0(order_engine 매도 본류 불변). 인계: A-3(BFB/VCP `_prev_price` 동형 cross-day) — A-4(`register_cooldown_after_exit` 고아)는 **사이클 191 종결**
- **트레일링 기준점 복구 단일 진실원 (H-1, 2026-08-06)**: `_apply_high_since_buy_from_candles(pos, candles, today)` — `buy_date < 영업일 < today` 일봉 high max 로 고점 보정(올리기 전용) + `update_high` DB 영속 + `[high_since_buy_recover]`. donchian/VCP 에 로그 접두사만 다른 byte-identical 2벌이던 것을 base 승격(kojiro 가 3번째가 될 참이었음). 보조 파서 `_candle_trade_date`/`_candle_high` 는 KIS 원본 키(`stck_bsop_date`/`stck_hgpr`)와 DB 정규화 컬럼(`bas_dd` date 객체/`high_price`) **양쪽 수용** — `get_recent_daily_normalized` 가 raw 없는 row 를 row 자체로 반환하기 때문. `_candle_high` 는 `except Exception: return 0`(OverflowError 포함 — 봉 하나가 배치 복구를 중단시키면 안 됨). `_HIGH_RECOVER_LABEL` ClassVar 로 전략별 로그 접두사 보존(donchian "도치안 스윙"/VCP "VCP"). ⚠️ `recompute_high_since_buy` 자체는 base 승격 금지(전략별 fetch 소스·일수 상이 — donchian/VCP/BFB 자체 정의, kojiro 는 `recompute_held_atr` 에 내장). 소비자 = `risk.on_tick`(메모리 갱신)→boot 훅(일봉 복구+DB 영속) 분업 — on_tick 에 DB write 금지(회귀 가드)
```

→ CHANGELOG: 사이클 185 행 · 사이클 191 행

### 2026-09-17 이관 — 예산 관문 K축(cycle242)·ρ축(cycle245)의 단계별 확장 경위, 구 결정 ⑦ 폐기(cycle254), 마커 의미 반전 서술

```
- **`_apply_budget_limit(qty, current_price, ticker=None)` — 전략 예산 이중제한 ② 명목 축 (2026-08-03)**. 7 전략 `calc_buy_quantity` 의 **공통 return 관문**. 이중제한 = ① 개수 `max_positions`(`is_max_positions`, check_buy_signal 담당) + ② 명목 `Σ매수금액 ≤ total_investment`. 규약: `qty<=0` → `_fallback_one_share` 위임(**분기 순서가 계약** — `test_strategy_fallback_budget.py` Case D 가 호출 자체 검증) / `qty>0` → `min(qty, 잔여//price)` **부분 매수 허용**(잔여<price → 0). 배경 = 주 분기가 `int(예산×ratio)//price` 를 잔여 검증 없이 반환해 `position_ratio × max_positions > 1.0` 전략이 예산을 초과 매수하던 결함(라이브 kojiro/LTV 각 200%, 계좌 122.5% 초과 청약). **원자성 조건**: `order_engine.execute_buy` 의 `calc_buy_quantity`(:272) ~ `pending_buys.add`(:313) 사이 `await` 0건이라 관문 read 가 pending 등록까지 원자적 → order_engine 미접촉으로 완결. 따라서 이 메서드 안에서 `await`/DB/HTTP **절대 금지**. AST 가드 `tests/unit/ast/test_budget_limit_ast.py` = A-ATOMIC(await 0건, 8영역 미접촉으로 8영역 보호) + A-PURE + A-GATE(7전략 모든 return 이 관문 경유) + C-DEFAULT(`ratio×maxp ≤ 1.0` 기본값 불변식). 관측 로그 `[budget_clamp]` = `_emit_budget_clamp` DailyEmitCap 1회/(ticker,전략)/일, 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존 — 서브클래스 override 가 super() 를 호출하지 않아 누락 위험)
- **cycle242 — 랏당 최대 유닛 상한(`_apply_lot_units_cap`)**. 관문 분기 순서 계약이 확장됐다: `price ≤ 0 → 0` → (`qty ≤ 0` → `_fallback_one_share` / `qty > 0` → 잔여 클램프 + `[budget_clamp]`) → **랏 유닛 캡** → `[oversized_fallback]` 관측 → `return`. 캡은 `sizing_mode == "turtle"` 전략의 **모든 랏**에 `min(final, compute_unit_qty(budget, atr, risk_pct, fraction=K))` 를 적용한다(K = `max_lot_units`, 기본 2.0). 관측 **앞**에 두는 것이 계약 — `[oversized_fallback]` 이 **캡 이후 최종 수량**을 재야 하고, 캡→0 이면 그 관측기는 `final_qty < 1` 로 자연 침묵하므로 차단 사실은 전용 마커가 담당한다.
  - **ATR 소스** `_resolve_sizing_atr(ticker)` — 터틀 분기와 **같은** `_candidates[ticker]` 를 read-only 로 읽고, `_SIZING_ATR_KEYS = ("atr", "atr14")` 중 양수로 파싱되는 값이 **둘 이상 서로 다르면 채택하지 않는다**(`ambiguous_atr`). 관문 시그니처는 무변경 — 명시 kwarg 전달은 후속.
  - **fail-open 경계** — `sizing_mode` 아님 / `ticker is None` = 조용히 통과. `no_candidates`·`no_atr`·`ambiguous_atr`·`no_risk_pct`·`no_budget`·`exception` = **현행 수량 유지 + `[fallback_cap_skipped]` WARNING**. 수량을 0 으로 만드는 fail-closed 구현은 금지(P0-1 유령 키 재현 방향).
  - **마커 5종** — `[fallback_notional_capped]`(INFO, 캡 발동. `path=fallback|sized`·`units_before`·`units_after`·`k`·`atr` 필드) / `[fallback_cap_skipped]`(WARNING, `reason=` 6종 + `atr=`/`units=` 진단 병기 — PR 경로 fail-open 랏의 K 초과가 어떤 마커에도 안 남던 사각을 메운다) / `[fallback_cap_config]`(INFO 카나리아, 1회/전략/일, `cap=on|off`·`k`·`atr_max`) / `[fallback_cap_clamped]`(WARNING, **키가 명시 존재하는데** 범위 밖일 때만 — DB 미설정과 PUT 무효값을 구별) / `[oversized_fallback]`(cycle233 ρ 축, 접두 byte 보존 + 꼬리 ` units=` 확장). 전부 하나의 `DailyEmitCap[str]` 복합 키(`cap|t` / `skip|t|r` / `cfg` / `clamp`) + 날짜 키 자기 리셋 + **peek→로그→mark** 순서(cycle226 D-3 — 같은 파일 `_emit_budget_clamp` 의 mark 선행 위반도 동행 시정). **행위는 cap 밖** — 마커 성패와 무관하게 캡 수량을 반환한다.
  - **두 척도 병존** — `[oversized_fallback]` 의 `cap` 은 ρ 축(`position_ratio × 예산`, ATR 무관 = 갭·거래정지 명목 리스크), `units` 는 K 축(`qty × ATR ÷ (예산 × risk_pct)` = 정상 시장 손절 리스크). **대체재가 아니다.** ⚠️ K>1 이면 캡을 통과한 랏도 ρ 상한을 넘을 수 있어 `[oversized_fallback]` 의 **비제로가 정상**이다(의미 반전 — 배포 전후 grep 합산 금지).
  - **오귀인 주의** — 캡→0 은 `order_engine.execute_buy` 의 `quantity <= 0` 경로로 흘러 `block_low_funds(+900s)` + "매수 수량 0 → 900s cooldown (투자금: …)" WARNING 을 남긴다(8영역이라 무접촉). 같은 시각·같은 ticker 의 `[fallback_notional_capped]` 와 짝지어 읽어야 하며, `_bought_today` 가 종목당 1회/일이라 이 짝은 1:1 로 성립한다. ⚠️ **이 1:1 은 K축 표적(donchian·kojiro) 한정이다** — `_bought_today` 는 `vcp_breakout`·`kojiro`·`donchian_swing`·`bull_flag_breakout` 4파일에만 있고 `momentum`·`volatility_breakout`·`long_tail_volatility` 에는 없다(그 3전략은 900s 만료 또는 `_sync_positions_from_balance` ≈15분의 `clear_low_funds()` 로 같은 종목을 하루 3~4번 재시도 = **1:N**). ρ축(cycle245) 판독에 이 문장을 승계하지 말 것.
  - **K 취급** — `_read_max_lot_units` 가 `[1.0, 20.0]` 로 클램프(비수치·bool·비유한·<MIN → 기본 2.0 / >MAX → 20.0). `_MAX_LOT_UNITS_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 4 터틀 전략 `DEFAULT_PARAMS` 리터럴과 동치여야 한다(AST G-242-6). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(G-242-1). `_MiniStrategy` 류 더블은 DEFAULT_PARAMS 병합을 타지 않으므로 **모듈 상수 기본값이 필수**다.
- **cycle245 — 비터틀 랏 명목 ρ축 상한(`_apply_ratio_notional_cap`)**. 관문 분기 순서 계약이 한 단계 더 확장됐다: `price ≤ 0 → 0` → (`qty ≤ 0` → `_fallback_one_share` / `qty > 0` → 잔여 클램프 + `[budget_clamp]`) → `_apply_lot_units_cap`(K축, cycle242) → `[oversized_fallback]` 관측(cycle233) → **ρ축 캡** → `return`. 관측 **뒤**가 계약 — 앞에 두면 차단된 랏의 ρ 관측이 `final_qty < 1` 로 통째로 사라진다. 산식 = `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // price` · `final = min(final, cap_qty)`(K_ρ = `max_lot_ratio_mult`, 기본 2.5. 경계는 `final × price > cutoff` 일 때만 차단 = 경계 포함).
  - **적용 범위 = 관문을 지나는 모든 랏**(`_lot_units_cap_governs` 는 K축이 이 랏을 실제로 심사했는지만 판정한다). 심사 = `sizing_mode == "turtle"` ∧ `ticker is not None` ∧ `risk_pct > 0` ∧ 예산 > 0 ∧ ATR 해석 성공. 대상 = 비터틀 5전략 전부 + **터틀이지만 ATR 배관이 끊긴 랏**(cycle242 가 fail-open 하던 양축 무방비 구간) + **cycle254 부터 — K축 심사 랏도 포함**. **K축 심사 랏도 ρ축이 `min` 으로 후심사한다(cycle254, 구 결정 ⑦ "상호배타" 폐기)** — 사이즈드 터틀 랏·PR 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(B×ρ)//P)`)이 명목을 이미 `cap` 이하로 묶어 두므로 `cutoff ≥ cap` 인 이상 `final <= cap_qty` 로 항등적으로 통과해 무접촉이고, 실효는 **1주 폴백 랏**(`P > B×ρ`)뿐이다. 판정 실패(`probe_error`)만 fail-open 으로 남는다.
  - **스코프와 항등식은 다른 문장이다 — 뭉치지 마라.** (a) 스코프 = 캡은 1주 폴백 랏뿐 아니라 관문을 지나는 **모든** 랏에 적용된다(`via_fallback`·`final == 1` 로 좁히지 않는다 — 축소 뮤테이션을 F-5b/F-5c 가 봉인). 현행 7 전략 호출부에서는 주 분기가 정의상 ρ상한 이하라 프로덕션 도달이 없고, 이 조항이 지키는 것은 장래 회귀다. (b) 항등식 `notional ≤ K_ρ × int(예산 × position_ratio)` 는 **cycle254 이후 관문을 지나는 모든 랏에 성립한다** — K축이 심사한 터틀 랏은 `compute_unit_qty_guarded` 의 notional 상한이 명목을 이미 그 이하로 묶어 두므로 `final <= cap_qty` 로 항등적으로 만족되고(수량 불변), 실제로 컷오프에 걸리는 것은 1주 폴백 랏뿐이다. cycle254 이전에는 K축이 심사한 터틀 랏이 이 항등식 **밖**이라 잔여 노출이 kojiro **3.86배** · donchian **5.00배**까지 열려 있었으나(구 결정 ⑦ "상호배타"), cycle254 가 그 조기탈출을 판정 실패(`probe_error`) 한 경우로만 좁혀 닫았다.
  - **fail-open 경계** — 키 부재 = **캡 OFF**(cycle242 `_read_max_lot_units` 의 "키 부재도 기본값" 관례와 **반대**: 이 캡은 *매수를 막는* 통제라 fail-closed 는 P0-1 유령 키 재현 경로다) / K축 심사 = 조용히 통과. `no_ratio`·`no_budget`·`no_cap`·`k_axis_probe_error`·`exception` = **현행 수량 유지 + `[ratio_cap_skipped]` WARNING**. 어떤 결측·예외도 수량을 0 으로 만들지 않는다.
  - **마커 4종** — `[ratio_notional_blocked]`(INFO, 차단·축소 행위. `path=fallback|sized`·`price`·`cap`·`cutoff`·`k`·`ratio`·`req_qty`·`capped_qty`·`budget`·`pos_ratio`) / `[ratio_cap_skipped]`(WARNING, `reason` 5종) / `[ratio_cap_config]`(INFO 카나리아 — **`cutoff_price` 필수 필드**, 운영자가 아침에 "오늘 LTV 는 130,100원 넘는 종목을 못 산다"를 한 줄로 읽는 근거) / `[ratio_cap_clamped]`(WARNING). 전부 cycle242 `_lot_cap_logged` 와 **별개 인스턴스**인 `_ratio_cap_logged: DailyEmitCap[str]` 복합 키(`blk|t` / `skip|t|r` / `cfg|cap상태|k|cutoff` / `clamp|raw`) + 날짜 키 자기 리셋 + **peek→로그→mark** + 예외 전부 흡수. **행위는 cap 밖** — 마커 성패와 무관하게 차단은 매 호출 수행. `[ratio_cap_config]`/`[ratio_cap_clamped]` 의 키는 **값-민감**이라 "1회/전략/일"이 아니라 **"1회/(전략, 값 조합)/일"** — 정상 운영은 하루 1행이고 K·예산이 실제로 바뀐 날에만 1행이 더 붙는다(= 공식 롤백 PUT 을 확인하는 유일 채널).
  - **`[oversized_fallback]` 의미 전환** — ρ캡 **앞**에서 발화하므로 "실제로 산 랏" → **"사려 했던 랏"** 이다(로그 서식은 byte 불변, G-245-10). 자기검증 **R7(cycle254 재정의)** = `ratio` 가 **그날 그 전략의 `[ratio_cap_config] k=` 값**(리터럴 2.50 금지 — 롤백하면 20.0 이 된다)을 넘는데 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` 도 `[ratio_cap_skipped]` 도 없고 그 전략이 `cap=on` 이면 **캡 우회 = 결함**. **터틀 행에도 예외가 없다** — cycle254 가 K축이 심사한 랏도 ρ축으로 `min` 후심사하므로, 사이즈드 터틀 랏은 항등식으로 애초에 `ratio ≤ k` 이고(BLOCKED/RSKIP 부재가 정상), 1주 폴백만 `ratio > k` 가 가능한데 그때는 반드시 BLOCKED 나 RSKIP 이 동반돼야 한다(구 결정 ⑦ 시절 터틀 전용 라벨의 예외는 폐기 — 그 라벨 자체도 `cap=on` 으로 통일). ⚠️ 배포 전후 같은 grep 합산 금지.
  - **오귀인 판독은 1:N** — 캡→0 은 `order_engine` 의 `quantity <= 0` 경로로 흘러 "매수 수량 0 → 900s cooldown (투자금: …)" WARNING 을 남긴다(8영역 무접촉). 표적 3전략(momentum·VB·LTV)에는 `_bought_today` 가 **없어** 900s 만료 또는 `_sync_positions_from_balance`(≈15분)의 `clear_low_funds()` 로 같은 종목을 하루 3~4번 재시도한다(실측 LTV 095610 4행·131290 3행). 판독 규칙 = 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` 가 **한 행이라도** 있으면 그날 그 종목의 **모든** 수량-0 WARNING 을 캡 귀속으로 읽는다(캡 마커는 1회/일이라 2행째부터는 단독으로 보인다).
  - **20:10 리포트 미도달** — 4마커는 INFO 2 / WARNING 2 이고 `log_analysis_engine._aggregate_log_patterns` 는 `{WARNING, ERROR, CRITICAL}` 만 패턴 집계하므로 `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 리포트 payload 에 한 글자도 안 들어간다. 반대로 오귀인의 **원인**인 수량-0 WARNING 은 `top_patterns` 에 오른다 ⇒ 리포트만 읽으면 "투자금 부족 급증" 오결론이 나온다. 판독은 `system_logs` 직접 조회가 유일 채널(집계 편입은 후속 F-12).
  - **K_ρ 취급** — `_read_max_lot_ratio_mult` 가 `[1.0, 20.0]` 클램프(비수치·bool·비유한·<MIN → 기본 2.5 / >MAX → 20.0). **하한 1.0 이 "정상 비중 랏 무접촉" 항등식의 수학적 전제**다 — 1.0 미만을 허용하면 주 분기까지 잘려 전면 무매매가 된다. `_MAX_LOT_RATIO_MULT_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 **7 전략 전부**의 `DEFAULT_PARAMS` 리터럴과 동치여야 한다(AST G-245-6, glob 전수). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(G-245-1) + AI 자문 자동 적용 경로 편입 금지. 롤백 = 해당 전략 K=20.0 — ⚠️ **`PUT /api/strategies/{id}/params` 는 즉시 반영, `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만** 반영된다(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회, 07:55 `_boot` 재호출은 no-op). cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 롤백 수단은 PUT 뿐**이다.
```

→ CHANGELOG: cycle233 행 · cycle242 행 · cycle245 행 · cycle254 행

### 2026-09-17 이관 — `_MULTIDAY_STRATEGIES` 정적 선언 전 동적 side-effect 등록 상태 · funnel 캡처 사이클 라벨(39/47/132/143/170)

```
- `Position.is_next_day`: `buy_date < today AND strategy_id not in _MULTIDAY_STRATEGIES`(**리터럴 정본 = `{donchian_swing, vcp_breakout, kojiro}`**). 멀티데이 전략은 항상 False — 확장 시 frozenset 리터럴 멤버만 추가, `Position` 시그니처 변경 금지. 3 전략 모두 `strategy_base.py` 리터럴에 정적 선언(2026-07 — vcp 가 과거 import 시점 동적 side-effect 로 자기를 추가하던 취약 패턴을 리터럴로 통합, import-order 독립 단일 진실원)

- **funnel 단계 캡처** (관찰성 전용 — 메모리 `_funnel_steps` + DB `strategy_funnel_snapshots` + UI): `_record_funnel_step(step_no, step_name, survived, excluded=None, *, step_conditions=None)` + `_record_funnel_pipeline_step(FunnelStage, ...)` 위임 (사이클 47). survived/excluded cap 200/20 자동, survived_count 는 cap *전* 정확 보존. **사이클 170 카드 B — in-place upsert**: 같은 step_no 존재 시 교체 (append-only 누적 차단). `_reset_funnel_steps(stages=None)` — `stages` 전달 시 모든 `FunnelStage` `survived=[]` count=0 0-시드 pre-populate (조기반환/실패 run 도 전 단계 0 일관 → step1=0/step4=7 stale 잔존 영구 차단). `stages=None` = 빈 리스트 (사이클 39 회귀). 5 전략 prepare()+retry 가 각 전략 STAGES 상수 인자 전달 (donchian/BFB/VCP=`FUNNEL_STAGES` / VB=`VB_FUNNEL_STAGES` / LTV=`LTV_FUNNEL_STAGES`). **check_exit_signal/check_buy_signal funnel hook 0건** (매도/매수 hot path 적재 금지, 사이클 143/170 SAFETY). momentum 영구 제외 (사이클 132)
```

→ CHANGELOG: 사이클 47 행 · 사이클 132 행 · 사이클 170 행

## risk.py

### 2026-09-17 이관 — NXT 프리장 청산 평가 보류 게이트 — cycle238 이전 'wall-clock 아님' 계약과 08-31 실측 APBK0918 사고 경위

```
- **NXT 프리장 청산 평가 보류 게이트 (2026-08-06)**: `_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})` 화이트리스트 외 전략은 **`by_active`(`PRE_NXT ∈ session_tracker.active AND MAIN ∉ active`, 매수 PR-F 동일 membership) OR `by_clock`(`session.boards_at(_now_kst().time())` 가 PRE_NXT 단독 — cycle238)** 동안 **청산 평가 + `high_since_buy` 갱신을 보류**한다. 근거 = 프리장 시초가 왜곡(전일 상한가 종목 하한가 형성 등, 사용자 실측)으로 허깨비 손절 발화·트레일링 앵커 오염. **평가 보류이지 주문 보류가 아님** — 주문만 보류하면 허깨비 신호가 09:00 실매도로 전환. 09:00 MAIN 진입 시 자동 재개. **cycle238 (2026-09-02, P1-6)** — `active` 는 `SessionTracker.tick()`(`_session_loop` 30초 주기)이 기록하는 **stale 캐시**라 `boards_at(07:59)`=∅ 스냅샷이 08:00:00~29 살아남아 게이트가 매일 ~30초 fail-open 했다(실측 08:00:00 시장가 매도 실발사 → APBK0918). 시정 = 시각 폴백 `by_clock` 을 **OR** 로 결합(fail-closed 방향, tracker 가 쓰는 같은 `_BOARD_SCHEDULE` 표를 fresh 로 읽음 — 08:00/09:00 리터럴 신설 금지, `_KST` 명시·naive 금지). **09:00 정각**은 stale `active`={PRE} 잔존 ≤30초 동안 OR 라 보류 유지(현행 동일·안전 방향 — clock-primary 는 후속). 두 소스가 갈릴 때만 `[pre_market_exit_gate_divergence] reason=clock_fallback|active_stale_hold` 1회/(전략,사유)/일(날짜 키 자기 리셋 + peek→로그→mark). "wall-clock 아님" 계약은 **폐기** — 결정성은 루트 `tests/conftest.py` autouse `_pin_pre_market_clock`(`risk._now_kst` MAIN 핀, 옵트아웃 마커 `real_pre_market_clock`)이 담보. `tradable_boards` 게이팅 금지(매수 전용 doctrine 커플링 차단, AST 가드) + fail-open 은 **두 소스 모두** 판정 불가일 때만(평가 유지). `[pre_market_exit_deferred]` 1회/전략/일(서식·cap 무변경 — D+1 판독 = 첫 타임스탬프 08:00:0x + 같은 시각 `clock_fallback` 동반). 사이클 38 "청산 항상 평가" 의 **유일한 명시 예외**. 회귀 `test_risk_pre_market_exit_gate.py`(13) + `test_cycle238_pre_market_clock_gate.py`(21)
```

→ CHANGELOG: cycle238 행

### 2026-09-17 이관 — 보드 가드 사이클 38 명문화 표기 · 시장 레짐 매수 가드(4 모드) 제거 경위(사이클 I) + 2026-08-07 자문 계층 정직화 + buffett_ratio F1 버그

```
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)`. **사이클 38 (2026-05-22) 명문화**: `tradable_boards` 는 매수 진입 전용 — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동. `check_exit_signal` 분기는 본 가드 *전* 진입 (`on_tick` line 88-99 영역)
- **~~시장 레짐 매수 가드 (4 모드)~~ — 사이클 I (2026-08-03) 제거**: risk.py on_tick + scheduler swing 폴링의 `get_buy_block_state()` 게이트(HARD skip / WARN 로그 / SOFT soft_multiplier)를 **전면 제거**. 마켓레짐은 더 이상 매수를 차단/축소하지 않는다 (**관찰 전용 전환**). 레짐 대응은 `cash_usage_ratio`(`auto_regime_adjust`)로만. `get_buy_block_state`/`BuyBlockState`/`buy_block_mode` 는 잔존하나 **대시보드·AI자문 payload 표시 전용**(매매 미소비). `execute_buy` 는 soft_multiplier 미전달(order_engine 파라미터는 vestigial). 점검 배경 = `/api/market-regime/current` 이 레거시 `regime.buy_blocked`(모드 무시) 노출해 방어국면=항상 "차단" 오인 → `buy_blocked=False` 정직화. **2026-08-07 — 자문 계층 정직화 완결**: `/current` 는 사이클 I 가 정직화했으나 `to_advisor_dict`(자문 payload) 만 여전히 레거시 `buy_blocked=True` 를 방출 → SYSTEM_PROMPT 의 거짓 등가("buy_blocked=True = 모든 전략 매수 차단 → 매수 튜닝 무용")와 결합해 매일 20:00 자문이 **매수 파라미터 권고를 통째 스킵**했다. 시정 = `to_advisor_dict` buy_blocked→False(`/current` 정합, `block_reason` 은 방어 '권고' 관찰용 유지) + SYSTEM_PROMPT 재작성("레짐은 매매 미개입, 매수 튜닝 유효, block_reason 은 보수적 권고 참고 신호"). 동반 **buffett_ratio 파싱 버그(F1)**: `from_macro_cycle` 이 `params.pbr_max`(PBR 상한, 라이브 0=비활성)를 buffett 로 읽어 /current·자문·스냅샷 전 계층 null → `regime.buffett_ratio`(라이브 1.45) 로 정정. 프론트 `MarketRegimeCard` = `auto_regime_adjust=false` 시 "관찰 전용 — 실제 매매 미반영(cash N% 수동)" 배너 + 경보에 "(권고·관찰)" 표기. 방향 = **A 관찰 전용 확정**(사용자 결정 2026-08-07, 행위 무변경). buy_blocked 프로퍼티/is_buy_allowed/스냅샷 감사 기록은 유지(자문 payload 에서만 False). 회귀 = `test_regime_observation_honesty.py`(10) + 의미 전환 2(payload buy_blocked True→False) + 프론트 2(관찰 배너 ON/OFF). 매매 안전성 8영역 diff 0(market_regime/recommendation_engine 은 8영역 아님).
```

→ CHANGELOG: 사이클 I 행

### 2026-09-17 이관 — 자금 사전 가드 사이클 31 R6/56-D 경위 · 거래대금 필터(사이클 65)·가격 필터(사이클 64) 절 전문(자문 Q1~Q7 채택 · 회귀 가드 분류 · 검증 수치 · 사이클 62 폐기 목록)

```
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. **사이클 31 R6 (2026-05-21) 가시화**: `current_price > total_investment` 분기에 `_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]` (RiskManager 필드, 사이클 56-D 마이그레이션) 기반 1회/페어/일 INFO emit cap — `[risk_silent_skip] ticker=009150 strategy=volatility_breakout reason=price_gt_total_investment price=1186000 total=352217`. 매 틱 폭주 차단. `scheduler._reset_daily_state` → `RiskManager.reset_daily_state()` 위임 (사이클 56-D 캡슐화 — 사이클 52 OrderEngine 패턴 답습) + AttributeError 후방호환 가드. 5/21 09:13 VB 미매수 사고 디버깅 곤란 해소
- **사이클 65 거래대금 동행 필터 (2026-06-06) — scanner 단계 거래대금 임계 차단 (사이클 64 답습 + Q7-5 갭상승 회피 효과 폐기 보강)**: 사용자 의도 = 가격만으론 작전주 차단 불충분 (예: 5,000원 통과 + 거래대금 5천만 = 작전 신호). domain-expert 자문 옵션 A 전부 적용 (Q1~Q5 + Q6-1~Q6-4). **사이클 64 패턴 100% 답습**: `_collect_protected_tickers_for_scanner` 헬퍼 100% 재사용 + 60s TTL 캐시 (`time.monotonic`) + invalidate 즉시 무효화 (**Q7-1 unsubscribe 0 발화 영속**) + DailyEmitCap 1회/ticker/일 + daily_summary + reset_daily 동행 + AST keyword 의무 + 사이클 38 명문화 (매수 진입 전용). **Q1 임계 (HIGH)**: 디폴트 0 (비활성) + UI 0~100억 step 1억 + 권장값 마커 1억/5억/10억 (team-leader 1차 0~5,000억 → 도메인 반박 채택, 100억 이상 비현실). **Q2 데이터 소스 (HIGH 핵심) — 옵션 C 통합 폴백**: (1) `scanner.ticker_market_info["trade_amount_raw"]` (신규 키, 원 단위 정밀값) 1순위 — scanner 가 이미 `fetch_rising_stocks::fetch_stock_detail` 호출 + `acml_tr_pbmn` 보강 중이라 **KIS 호출 0건 추가** (2) `stock_master.raw.acml_tr_pbmn` 2순위 fallback (3) 둘 다 miss = graceful 통과 (Q6-1 09:00 race 영속, 시스템 매매 무용 차단). **신규 키 호환**: `trade_amount_raw` 추가 + 기존 `trade_amount` (억 단위 round) 호환 보존 — UI/API 응답 영속. **Q3 순차 hook**: `_apply_price_filter` (사이클 64) → `_apply_trade_amount_filter` (사이클 65) 순차 호출 — `subscribe_filtered_stocks` 4 호출 (tickers + extra_tickers + breakout/momentum for loop + swing 명시 분리). **Q4 헬퍼 재사용**: `_collect_protected_tickers_for_scanner` 100% 재사용 + 60s TTL **별도 캐시** (단일 책임). **Q5 별도 prefix**: `[trade_amount_filter_scanner_skip] ticker=... acml_tr_pbmn=... reason=below_min min=...` INFO + `[trade_amount_filter_scanner_daily_summary] block_count=N` 1행. **Q6-1 (HIGH) 09:00 race graceful 영속**: `acml_tr_pbmn=0` (양쪽 miss) = graceful 통과 — 09:00 직후 누적 거래대금 0 시 후보 차단 = 시스템 매매 무용 위험 영구 차단. **funnel `step_no=97`** (사이클 64 step_no=98 보다 *전* 단계 표기). **사이클 64 hotfix 패턴 답습 (H-2 NO_TRY)**: `scheduler._settle()` 직전 `await _scanner_mod.emit_trade_amount_filter_scanner_daily_summary()` **try/except 금지** (사이클 64 G-3 답습) + `_reset_daily_state()` 동행 `_scanner_mod.reset_trade_amount_filter_daily_state()` 호출. **신규 5 함수** (scanner.py): `_get_trade_amount_filter_for_scanner` (60s TTL) + `invalidate_trade_amount_filter_cache_scanner` (Q7-1 unsubscribe 0) + `reset_trade_amount_filter_daily_state` + `_get_acml_tr_pbmn` (Q2 옵션 C 3 분기) + `_apply_trade_amount_filter` (Q1 옵션 D 3중 안전망 + Q6-1 graceful + funnel step_no=97) + `emit_trade_amount_filter_scanner_daily_summary`. **모듈 전역 4 필드**: `_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` / `_trade_amount_filter_scanner_skip_count_today: dict[str, int]`. **회귀 가드 31 함수 (28 케이스 / 12 파일 분리, HIGH 3)**: A system_config 3 + B 본체 4 + B-5 옵션 C 3 분기 + **C 보유/익일청산 보호 2 HIGH** + D+E 캐시 + DailyEmitCap 4 + F integration 4 + **G AST keyword + 호출 카운트 2 HIGH** + H daily_summary 1 + H-2 scheduler 통합 + AST 3 + C-Route 3 함수 + **I 신규 (Q6 자문) 2** (I-1 옵션 C 정합성 + I-2 Q6-1 09:00 race) + F-FE 프론트 4. **백엔드 1939 → 1970 PASS** (+31 = 사이클 65 신규 26 + 사이클 64 vacuous PASS 5 진정한 PASS 전환). **사이클 64 vacuous PASS 진정한 PASS 전환 (부가 효과)**: 사이클 65 hook 추가로 사이클 64 G-2 keyword 호출 + H-2 NO_TRY 모두 호출 발생 → 진정한 PASS. **사이클 62 갭상승 회피 효과 폐기 보강 평가** (Q7-5 인계): 작전주 시나리오 80~90% 회복 (신규 상장 작전주 / 기존 갭상승 작전주 차단 + 정상 IPO/우량주 보존). 잔존 10~20% = 시스템 본질 한계 (운영자 화이트리스트 영역). **운영 2주 후 정량 측정 의무**. **신규 카드 #16 (MEDIUM, Q6-4)** 후보 풀 폭축 역설 risk 2주 회고 — 사이클 67+ 발의. UI: `TradeAmountFilterCard.tsx` 167L (사이클 64 PriceFilterCard 답습, 4 testid + 권장값 마커 3 + 안내 배너 Q6-1 명시).
- **사이클 64 가격 필터 (2026-06-06) — scanner 단계 종목 필터 (사이클 62 폐기 + 위치 변경 + 단순화)**: 사용자 의도 재정의 = **WebSocket 구독 *전* 종목 풀 차단** (매매 신호 판단용 X). 사이클 62 `risk.on_tick` 가격 필터 분기 + 3 모드 (HARD/WARN/OFF) + current_price fallback + RiskManager 캐시 4 헬퍼 **전부 폐기** (G3, risk.py -178L). 신규 위치: `src/engine/scanner.py::subscribe_filtered_stocks` 진입점 내부 **단일 hook** (Q4 자문 옵션 A — 호출자 시그너처 변경 0 + 신규 전략 추가 누락 차단). **단순화** (Q4 자문 옵션 A): mode 폐기 (HARD 만 의미 + WARN/OFF 제거 = 단순 임계 필터). DB 키 2 종만 (`price_filter_min` / `price_filter_max`, mode 키 폐기). **Q1 자문 옵션 D 3 중 안전망 (보유/익일청산 절대 보호 HIGH)**: (1) `_collect_protected_tickers_for_scanner()` 공통 헬퍼 (`registry.all().positions` ∪ `_pending_next_day_clear`, 사이클 32 R4 universe guard 답습), (2) `_apply_price_filter` 최상단 early-return (`if ticker in protected_tickers: survived.append(ticker); continue`), (3) AST `protected_tickers=` keyword 의무 가드 (G-2 정적 검증). **Q2 자문 (current_price fallback 폐기)**: `stock_master.raw.prdy_clpr` 단독 (scanner 단계 = WS 구독 *전*, current_price 미확보) + 미확보 graceful 통과 (사이클 32 R4 답습) + KIS `inquire-price` pre-fetch 비채택 (Rate Limit + hot path 부담). **60s TTL 캐시** (`time.monotonic`) + **`invalidate_price_filter_cache_scanner()` 즉시 무효화** + **Q7-1 unsubscribe 발화 0건 HIGH** (다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단 — 사이클 17 OPSP0002 답습). 임계 외 종목 → `[price_filter_scanner_skip] ticker=... prdy_clpr=... reason=below_min/above_max min=... max=...` INFO + `DailyEmitCap[str]` 1회/ticker/일 cap. **Q7-4 funnel `step_no=98` hook**: `strategy_funnel_snapshots` step_no=98 INSERT (graceful). **일일 카운터** `_price_filter_scanner_skip_count: dict[str, int]` (`count`) — `scheduler._settle()` 직전 `[price_filter_scanner_daily_summary] min=... max=... skip_count=N` INFO 1행. **사이클 64 hotfix (H-2 + G-3 영구 가드, tester verify 결함 1건 발견 후)**: `scheduler.py:638-642` 가 사이클 62 폐기 메서드 `_emit_price_filter_daily_summary` 잔존 호출 → AttributeError graceful skip → 운영 가시화 무력화. 2 줄 교체 (`from src.engine import scanner as _scanner_mod; await _scanner_mod.emit_price_filter_scanner_daily_summary()`) + log prefix 갱신 + H-2 (scheduler 통합 가드 AST 정적) + G-3 (src/ 전체 폐기 메서드 호출 0건 AST 정적) 영구 가드 도입. **회귀 가드 28 케이스 (12 파일 분리, HIGH 8 = 29%)**: A system_config 단순화 4 (mode 인자 제거) + B scanner 필터 적용 5 + **C 보유/익일청산 보호 4 HIGH** (옵션 D 3 중 안전망) + D 60s TTL 캐시 2 (Q7-1 unsubscribe 0) + E DailyEmitCap 2 + F integration 4 (F-4 funnel step_no=98) + **G AST 2 HIGH** (G-1 risk.py 17 금지 문자열 0 + G-2 `protected_tickers` keyword 의무) + H daily_summary 1 + **H-2 scheduler 통합 가드 HIGH** + **G-3 폐기 메서드 src/ 전체 0건 AST HIGH** + C-Route 2 + F-FE 4 (mode 토글 폐기, 5 → 4). **백엔드 1944 → 1939 PASS** (사이클 62 폐기 34 케이스 + 사이클 64 신규 28 = 차이 -8, frontend 167 → 166). **사이클 38 명문화 영속**: scanner 단계 = 매수 진입 전용 (매도/익일청산/손절/15:20 강제청산 영향 0). **사이클 62 폐기 9 파일 git rm**: `test_cycle62_price_filter_*.py` (백엔드 33 케이스) + `PriceFilterCard.test.tsx::F-5 mode 토글` (1 케이스). UI: `PriceFilterCard.tsx` -88L (mode select 폐기) + 안내 배너 갱신 ("WebSocket 구독 대상 필터 — 임계 외 종목은 시세 구독 자체 차단. 보유/익일청산 종목은 절대 제외 안 됨").
```

→ CHANGELOG: 사이클 31 행 · 사이클 62 행 · 사이클 64 행 · 사이클 65 행

### 2026-09-17 이관 — `_selling` 가드 사이클 19 라벨과 '6 전략 공통 적용' 표기(현행 7 전략)

```
- **사이클 19 (2026-05-20) `_selling` 가드**: `risk.on_tick` 의 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 검사 — 매도 발사 후 체결통보 도착 전까지 신호 평가 + 로그 폭주 차단. 042700 7초 18+ 행 운영 결함 대응. 6 전략 공통 적용
```

→ CHANGELOG: 사이클 19 행

## market_regime.py

### 2026-09-17 이관 — 사이클 I 전환 표기 · 60s TTL 캐시 효과 수치 · ETF 스테이지 신호(사이클 E-1) 다크런치·E-2 인계·EC2 실측 · 레짐 가드 silent inert(사이클 D) 근본 원인과 인계

```
`dkstock.cloud` 매크로 기반 시장 레짐 + cash_usage_ratio 자동 조정. **사이클 I (2026-08-03) — 매수 가드(get_buy_block_state 게이트) 제거, 레짐 관찰 전용 전환.** `get_buy_block_state`/`buy_blocked` 프로퍼티는 표시·자문 payload 전용으로 잔존(매매 미소비).

- **`get_buy_block_state()` 60s TTL 인스턴스 캐시** — `_buy_block_cache` + `_buy_block_cache_expires_at` 필드(`compare=False, repr=False`). `BUY_BLOCK_CACHE_TTL=60.0`, `time.monotonic()` 비교. DB fetch 폴백 분기는 캐시 미저장. `invalidate_buy_block_cache()` 운영 토글 즉시 반영. 분당 ~1,800 DB 쿼리 → ~10 쿼리 (180배 감소)
- **사이클 E-1 (2026-07-31) — 지수ETF 고지로 스테이지 레짐 신호 (관찰 전용 다크런치)**: `DEFENSIVE_STAGES=frozenset({3,4,5})`(고지로 대순환 하락 사분면) + `is_two_day_defensive(stages)`(최근 2 스테이지 모두 방어집합, None/len<2→False, whipsaw 히스테리시스) + `EtfStageSignal` frozen dataclass + `compute_etf_stage_signal(now=None)` async(KODEX200 069500 + 코스닥150 229200, 일봉 seam=`stock_master_daily.get_recent_daily` DESC→ASC 정렬 후 `kojiro_indicators.ema(5/20/40)`+`stage_of` 순차 → 각 지수 스테이지 + 2일 방어, etf_defensive=신선 지수 OR·양쪽 stale→None) + `_is_daily_row_stale`(달력 `ETF_STALE_MAX_CALENDAR_DAYS=10` never-raise) + `get/set_current_etf_signal` 싱글톤. **dkstock 독립** — boot(`_refresh_market_regime_and_persist` set_current_regime 직후)가 dkstock 성패 무관 계산·`[etf_regime]` 로그(다운 시 fallback = 프래질리티 완화 동기). **E-1 = 관찰만 — `get_buy_block_state`/blocked/reasons/soft_multiplier 무변경(배제 0), 매수 가드 행위 byte 동일**. `etf_regime_enabled=False`(system_config) 다크런치. **FREEZE 무관**: kojiro_indicators 순수함수 재사용, kojiro 전략/파라미터/포지션 무접촉, ETF 전용 5/20/40 파라미터화 금지(정체성 상수). **E-2 인계(2주 관찰 후)**: block_reason etf OR 통합 + SOFT 상한(HARD 승격 금지) + reasons 태깅(dkstock/etf 구분) + cycle D robustness(dkstock empty·etf 신선 → 무력 아님) + 프론트 배너. 실측(EC2) = 양지수 stage4·whipsaw 낮음·dkstock defensive 부합
- **사이클 D (2026-07-31) — 레짐 가드 silent inert 가시화 (관찰성 전용)**: `has_regime_data` property (`regime`/`vix`/`fear_greed_score` 중 1개라도 not None 또는 `bool(raw)` — `empty()` 폴백은 전부 None+raw={} → False, `persist_snapshot` 의 `regime is None` empty 판정과 정합) + `BuyBlockState.data_available: bool=True` 필드 + `get_buy_block_state()` 5개 생성분(OFF/HARD/WARN/SOFT/unknown-fallback) 전부 `data_available=self.has_regime_data` 세팅. **blocked/soft_multiplier/reasons 로직 + 60s TTL 캐시 완전 무변경 = fail-open 보존** (신규 필드는 표시/경보 전용). 근본 = "데이터 있고 임계 미발동"과 "데이터 없음(empty)"이 동일 `blocked=False,reasons=[]` 라 운영자 구분 불가하던 결함 (dkstock 인증서 07-27 만료 → 4일 무력화 무경보). boot 경보 = `_refresh_market_regime_and_persist` 의 `set_current_regime` 직후 `get_buy_block_mode()` graceful → `not has_regime_data and mode != "OFF"` 시 `[regime_guard_inert]` WARNING (boot 1회/일). **인계**: fail-open→fail-safe 전환(dkstock 다운 시 전량 매수 차단 위험) / 수동 방어 오버라이드 / 장중 매크로 재시도(현재 boot 1회만) — 별도 결정
```

→ CHANGELOG: 사이클 D 행 · 사이클 E-1 행 · 사이클 I 행

### 2026-09-17 이관 — `get_buy_block_state` 4 모드 항목과 운영 graceful 항목의 사이클 I 표기

```
- **`get_buy_block_state() -> BuyBlockState` (async)** — 4 모드 분기. `BuyBlockState{mode, blocked, soft_multiplier, reasons}` 반환. DB 조회 실패 시 HARD + 기본 임계 fallback. **사이클 I — 매매 미소비**(대시보드 `/api/integrations/buy-block` 표시만). buy_block_mode 운영 DB=OFF 권장(정직 표시)

- 운영 graceful: `DKSTOCK_REGIME_ENABLED=false` 기본 → 외부 호출 0건, 레짐 관찰 비활성 (매수 가드는 사이클 I 제거)
```

→ CHANGELOG: 사이클 I 행

## order_engine.py

### 2026-09-17 이관 — `is_market_closed_rejection` 절 — cycle286 C4-a 이전 시계 단독 창(`08:00~09:00 ∪ 15:30~20:00`)과 사이클 55 R-1 → 57 V-1 갱신 사슬

```
- **`is_market_closed_rejection(err)`** (장운영시간 외) → 재시도 중단 + `state.positions`·DB 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 체결통보가 오지 않아 stale `_selling` 좀비 = `risk.py` on_tick 손절 마비이므로 반드시 해제. cf. `_sync_positions_from_balance` stale `_selling` 재대조 훅) + 다음 거래 시각 자연 재트리거. **`target_exchange ∈ ("NXT","SOR")` ∧ KST `08:00~08:50`**(NXT 프리마켓 실질 종료, GTP 미체결 일괄취소 = market_state N1.end)이면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강(cycle286 C4-a — 종전 `08:00~09:00 ∪ 15:30~20:00` 시계 단독 판정을 거래소 조건과 좁힌 창으로 교체. 근거 = 09-14 부터 KRX 애프터마켓(16:00~20:00)이 구 `15:30~20:00` 창 안에 통째로 들어와 KRX 로 보낸 애프터 주문의 거부가 그 종목을 NXT 불가로 잘못 낙인찍고, 그 오염이 16:10 CTPF1002R 재적재 창을 지나치면 다음 영업일 프리장까지 ≈24h 존속해 자기 강화 래치가 되기 때문 — 판단 불가는 fail-safe 로 쓰지 않는다. 마커 `[nxt_post_reinforce] ticker= exchange= div= now= wrote=1|0 reason=nxt_pre_window|exchange|window`, `wrote=0` 이 D+1 판독의 분모). **사이클 B-1 (2026-06-01) 진입 차단 이중 안전망** → **사이클 55 R-1 (2026-06-03) 2단계 TTL 로 갱신**: `SellRejectionTracker.register_market_closed(in_krx_main_hours=...)` 위임. KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대 거부 = 다음 KST 09:00 TTL. `execute_sell` 진입 게이트에서 TTL 미경과 시 KIS 호출 없이 skip (INFO `[market_closed_blocked]` 1줄/ticker/일 cap, reason 필드 포함). `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 5 필드 일괄 위임 (사이클 57 V-1: `_alarm_last_emitted` 추가) — `scheduler._reset_daily_state()` 위임 호출 보존. **사이클 57 V-1 (2026-06-04) 폭주 알람**: `_append_history` 단일 진입점에서 10분 윈도우 5건 초과 시 CRITICAL system_logs INSERT + 30분 per-ticker cooldown. 임계 상수: `ALARM_WINDOW_SECONDS=600 / ALARM_THRESHOLD=5 / ALARM_COOLDOWN_SECONDS=1800`. fire-and-forget (`asyncio.create_task`) — 매매 hot path 블로킹 0
```

→ CHANGELOG: 사이클 55 행 · 사이클 57 행 · cycle286 행

### 2026-09-17 이관 — 체결통보 race 가드 — cycle271/273a/273b 라벨과 161580(필옵틱스) 사건 서술

```
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 단일 COMPLETED row 보장 · **cycle273a(C235-V2)** — 부분체결(PARTIAL) 뒤 전량 체결이 오면 1차 UPDATE 가 `match_partial=True`(PENDING∪PARTIAL + KST 당일 하한, **datetime 바인딩**)로 그 행을 COMPLETED 로 덮어 3단 우회(보정 INSERT→UniqueViolation→강제 UPDATE)를 타지 않고, `_pending_cancel_order_no[ticker]==order_no` 일 때만 잔여취소 타이머를 cancel+pop(`[partial_cancel_timer_cleared]`) — CANCELLED 호출은 opt-in 하지 않는다(PARTIAL→CANCELLED 뒤집힘 금지) · **cycle271** — PENDING INSERT 의 `await` 도중 체결통보가 먼저 완주하면 그 PENDING INSERT 가 migration 029 부분 UNIQUE 를 위반한다 → `_insert_pending_buy_or_absorb_race`(시장가·지정가 폴백 두 지점 공용) 가 `order_no in _completed_orders` 일 때만 흡수·discard + `[buy_fill_during_insert] ticker= order_no= strategy= path=market|fallback` INFO 1행, 증거 없는 위반은 전파(`test_cycle271_execute_buy_fill_during_insert.py` 16케이스) · **cycle273b(F-1/F-2/F-3, I3)** — `update_trade_status(*, order_no=None, match_partial=False)` 에 keyword-only `order_no` 신설(미전달=SQL byte 동일, opt-in). `order_engine.py` 의 호출 6곳(C1 매수 COMPLETED·C2 매수 PARTIAL·C3 매도 COMPLETED·C4 매도 PARTIAL·C5 `_cancel_after_wait` 매수 CANCELLED·C6 `_cancel_and_reorder` 매도 CANCELLED) 전부가 지역 변수 `order_no` 를 그대로 전달해 WHERE 를 그 주문 한 건으로 좁힌다 — 09-08 필옵틱스(161580) 사건의 근본 원인(order_no 없는 WHERE 가 같은 (ticker,trade_type,strategy) 의 **다른 주문 행**까지 함께 덮어 한 체결통보가 여러 PENDING 행에 같은 price·profit_loss 를 도배)을 닫는다. `affected>1` 시 `src/db/trade_history.py` 한 곳에서 `[trade_status_multi_update]` WARNING(F-3) — order_no 있는 호출은 부분 UNIQUE 인덱스(migration 029) 때문에 구조적으로 발화 불가능해 과거 측정기가 아니라 WHERE·인덱스 후퇴 회귀 감시자다
```

→ CHANGELOG: cycle271 행 · cycle273a 행 · cycle273b 행

### 2026-09-17 이관 — 거래소 라우팅 cycle287 규칙 1·2 전문 + 「장중 킬스위치 있음(cycle290 이 등재)」 절 + cycle287 적대 검증 시정 목록(CRITICAL 1 · HIGH · MEDIUM)

```
- **NXT 거래가능 사전 차단**: `_probe_nxt_downgrade_base(strategy_id, ticker)`(cycle287 — 종전 `_strategy_exchange_async` 본체, 다운그레이드 판정까지만 담당하도록 분리)가 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 1행. 캐시 miss / 예외 시 전략 기본 exchange (보수적 fallback). 익일 청산 NXT 지정가(`limit_price>0`)는 사전 차단 적용 안 함. **사이클 54 (2026-06-03) — `[nxt_downgrade]` 로그 ticker별 1회/일 cap** (`_nxt_downgrade_logged_today: set[str]`). 다운그레이드 결정(return "KRX") 은 cap 밖 — 100회 호출 모두 정상 KRX 반환. `OrderEngine.reset_daily_state()` 동행 clear. 사이클 52 `_market_closed_blocked_logged_today` 와 동형 이중 안전망
- **cycle287(2026-09-12) — 규칙 1: 시각이 거래소를 정한다.** `_probe_nxt_downgrade_base` 가 정한 다운그레이드 결과(`base`) **뒤**에, `_strategy_exchange_async`(반환 시점 1회) · `_apply_clock`(그 밖 4곳)이 순수 함수 `_route_exchange_by_clock(base, *, side, mode, now)` 로 감싼다. 판정은 `market_state.MARKET_TABLE` 단일 정본만 읽는다(시각 리터럴 order_engine.py 안 0건) — `base ∉ {"NXT","SOR"}`(이미 KRX)→그대로 / `mode=="off"`→그대로 / `mode=="sell_only" ∧ side=="buy"`→그대로 / `session_tracker.active` 가 `PRE_NXT` 단독(PR-F 와 같은 출처, 08:50~09:00 NXT 휴장 구간도 이 판정으로 base 유지)→그대로 / 그 시각 KRX 가 우리 `OrderDivision` 값 집합(`_SENDABLE_DIVISIONS`) 중 하나라도 받으면 `"KRX"` / 아니면 그 시각 NXT 가 받으면 base 유지 / 둘 다 안 받으면 base 유지. 예외는 전부 `probe_error` 로 base 유지(fail-safe — 판정 실패가 주문을 막지 않는다). 적용 지점 5(`_strategy_exchange_async` 반환) + 4(`limit_price>0` 분기·`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`) = `_apply_clock` 단일 seam(mode/dial 조회는 `_clock_params` 공유). 킬스위치 `order_exchange_clock_mode`(기본 `enforce` — cycle287 시점 미등재였고 cycle290 이 등재했다, 아래 참조). 마커 `[order_channel] side= ticker= strategy= base= exchange= reason=`(routed≠base 일 때만, 1회/(ticker,side,reason)/일) + `[order_channel_config] strategy= mode= division=`(카나리아, 1회/(전략,mode,dial)/일).
- **cycle287 — 규칙 2: KRX 애프터마켓(16:00~20:00, 2026-09-14 신설) 청산 호가.** `execute_sell` 이 프리장 사전 변환(위 블록) **뒤** · 재시도 루프 **앞**에서 `order_division==MARKET ∧ target_exchange=="KRX" ∧ settings.is_production ∧ market_state.get_market_state(now,"KRX").phase is AFTER_MARKET` 이면 전략 params `after_market_exit_division`(화이트리스트 `{"44","41"}`, 기본·미지값 폴백 `"44"`)에 따라 `44`(최유리지정가, `ORD_UNPR=0`) 또는 `41`(지정가, `step_down(현재가,5)`, 현재가 미확보 시 변환 취소)로 사전 변환 — VTS 는 41~47 지원 여부가 정본에 없어 무접촉. 재시도 루프의 폴백 게이트가 `order_division==MARKET` 에서 `order_division==primary_div ∧ (is_market_order_disallowed(e) ∨ primary_div≠MARKET)` 로 일반화됐다 — 정규장·프리장은 `primary_div is MARKET` 이라 이 조건이 기존과 논리적으로 항등이고, 애프터는 **분류에 의존하지 않는 구조적 폴백**(msg1 원문이 완전 미지라 키워드에 폴백을 인질로 주지 않는다)이 된다. 폴백은 `fallback_div`(44→41, 41→41)로 1회. **봉인 3종**: ① `register_market_order_disallowed` 는 분류·성패 무관 항상 호출(TTL 30초) ② 종목당 그 저녁 실패(주문 사이클 단위) `_AFTER_EXIT_GIVEUP_THRESHOLD=5` 도달 시 `[after_exit_giveup]` CRITICAL + `register_market_closed(in_krx_main_hours=False)`(다음 09:00 TTL, 30초 TTL 뒤에 등록해 덮어쓴다) + `_pending_next_day_clear` 등록·그날 밤 포기 ③ TTL 축 `_exit_capable_krx_window(now)` — `register_market_closed(in_krx_main_hours=...)` 호출부의 인자 의미를 "그 시각 KRX 가 우리 청산 호가를 받는가"(`_EXIT_CAPABLE_KRX_PHASES = {REGULAR, CLOSE_AUCTION, AFTER_MARKET}`)로 재정의(`sell_rejection.py` 는 diff 0, 09-14 이전은 `is_krx_main_hours` 와 완전히 동치). 손절 잔여 재주문(`_cancel_and_reorder`)도 같은 창에서 시장가(price=0) 대신 창 호가쌍으로 교체(정규장·프리장은 byte 동일). ETP 관측 `[after_etp_exit_observe]`(`stock_master.raw.scty_grp_id_cd ∈ {EF,EN,FE}`, 애프터 1차 거부 **직후에만** — 행복 경로엔 DB 왕복을 얹지 않는다, 행위 분기 없음). 취소 `ORD_DVSN` 은 `"00"` 하드코딩 유지(자문 §4-C1 — 국내주식 스펙에 원주문 호가유형 승계 규약이 없고, 그 창의 취소 실적이 all-time 0건이라 추측 변경이 더 위험). 마커 `[after_exit_division] ticker= div= unpr= cur= exchange= dial=` / `[after_exit_rejected] ticker= div= msg_cd= classified= ttl_registered= msg1=` / `[after_exit_giveup] ticker= fails= next_day_clear=1`(CRITICAL).
- ✅ **장중 킬스위치 있음(cycle290 이 등재, 이력 — cycle287 시점에는 없었다)** — 배포 당시 `order_exchange_clock_mode`/`after_market_exit_division` 은 브리프 제약(전략 7파일 diff 0)으로 `param_catalog`/`DEFAULT_PARAMS` 어디에도 없었다. `PUT /api/strategies/{id}/params` 로 그 키를 보내면 `unknown_key` 422 — 롤백 수단이 **1커밋 revert + 장외 배포**뿐이라 09-14(월) 16:00~20:00 KRX 애프터마켓이 열리기 전에 반드시 닫아야 할 구멍이었다. **cycle290(2026-09-13)이 두 키를 7 전략 전부의 `DEFAULT_PARAMS` + `param_catalog` 에 코드 상수와 같은 값으로 등재해 열었다**(매매 행위는 등재 자체로 변경 0 — `params.get(key, DEFAULT)` 가 항등). `param_validation` 의 미지 키 판정이 `key not in current_params or spec is None` 이라 카탈로그 등재만으로는 부족했고 `DEFAULT_PARAMS` 등재가 함께 필요했다. `order_engine.py` 는 무접촉(cycle287 이 이미 그 키를 읽는 코드를 갖고 있었다). `risk="identity"`(2단계 확인) + `PARAM_RANGES`/`INT_PARAMS` 편입 금지(AI 자문이 청산 수단을 끄는 스위치를 뒤집으면 안 된다). ⚠️ **정정 — `PUT {"exchange":"KRX"}` 는 `off` 보다 부작용이 큰 "우회로"가 아니라 오히려 더 안전한 비상정지다**: `off` 는 라우팅 전체를 죽여 44/41 애프터 청산 변환까지 함께 꺼뜨리고(그 게이트가 "거래소가 KRX 인가"라서), `PUT {"exchange":"KRX"}` 는 `_route_exchange_by_clock` clause 1(`base ∉ {"NXT","SOR"}`→그대로)이 mode 검사보다 **앞**에서 발화해 KRX 로 고정되면서 44/41 전환이 보존된다(부작용은 프리장 주문도 KRX 로 가는 것 하나뿐). 사고 중 조작 순서(거부/미체결/악체결 3분류 + 5단계)는 `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절 참조. `order_engine.py:67-70` 의 이 절 관련 주석은 cycle290 이후 낡았다 — 8영역이라 이 사이클은 주석을 고치지 못했고(diff 0 계약), 다음 승인 사이클의 과제로 남긴다. 같은 이유로 `param_validation.py:3` docstring 의 "99 스펙"도 낡았다(실제 101) — 그 파일도 diff 0 계약 대상이라 함께 다음 승인 사이클 과제. ⚠️ **두 킬스위치는 `exchange ∈ {"NXT","SOR"}` 일 때만 효력이 있다** — `_route_exchange_by_clock` clause 1 이 mode 검사보다 앞서 `base ∉ {"NXT","SOR"}` 이면 그대로 반환하므로, 어떤 전략의 `exchange` 값이 `"KRX"` 로 바뀌는 날 그 전략은 `enforce`/`sell_only`/`off` 세 값이 전부 동일한 무동작이 된다(코드 기본값은 7전략 전부 `"KRX"`, 지금 운영 DB 는 7전략 전부 `"NXT"` 라 현재는 두 스위치가 실제로 작동한다 — 2026-09-13 사용자 결정 D3 로 `SOR`→`NXT` PUT 완료(SOR 잔여 0), 2026-09-15 실측 재확인. `NXT` 도 `_CLOCK_ROUTED_BASES` 안이라 라우팅 판정은 불변이다 — `_workspace/00_URGENT_WORKLIST.md` 운영 설정 실측표). `exchange` 를 KRX 로 마이그레이션하는 사이클은 이 두 키의 help 도 함께 갱신해야 한다. ⚠️ **두 킬스위치는 전략별이다** — 전역 스위치가 없으므로 보유 중인 전략이 여럿이면 사고 중 그 전략 각각에 PUT 해야 한다(자세한 절차는 `00_leader_trading_rules.md`).
- **cycle287 적대 검증 시정(2026-09-12, 커밋 전 반영)** — 4렌즈 적대 검증이 찾은 CRITICAL 1 + HIGH 다수를 같은 사이클에서 닫았다. 정정할 것 = **"봉인① 은 분류·성패 무관 항상 호출"은 Green 시점엔 사실이 아니었다** — `cur_price<=0`(현재가 미확보로 폴백 자체를 못 내는 경로)와 `market_closed` 분류(검사 순서 1번이라 폴백에 아예 도달하지 않는 경로) 둘 다 TTL·포기 래치가 미등록이라, 애프터마켓(16:00~20:00 실시간 연속체결)에서 브레이크 없이 반복 재시도할 수 있었다(CRITICAL C1 — 시정 = `_register_after_exit_disallowed`/`_bump_after_exit_fails_and_maybe_giveup` 공용 헬퍼를 두 경로에도 적용, `ttl_registered=` 필드도 그 등록 성공 여부를 실제로 싣도록 동적화). 그 밖 — **HIGH** 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)가 취소 **시각**에 라우터를 재평가해 `PARTIAL_FILL_WAIT`(30초) 동안 시간 경계를 넘으면 원주문과 다른 거래소로 취소가 나갈 수 있었다 — `place_order` 응답 직후 동기 영역에 `self._order_exchange[order_no] = <그 주문의 실제 거래소>` 를 추가 등록(기존 `_order_qty`/`_order_strategy`/`_order_ticker` 4종 매핑과 동일 자리·동일 정리 주기)하고, 취소 3경로는 그 값을 우선 쓰고 매핑이 없을 때만 라우터로 fail-open 한다. `[after_cancel_result] ticker= order_no= ord_dvsn=00 exchange= result=ok|error err=`(자문 §4-C1 "관측만"의 산출물)도 그 3경로에 실제로 붙었다(`ORD_DVSN="00"` 하드코딩·`cancel_order` 시그니처는 byte 동일 — `src/api/order.py::cancel_order` docstring 이 "관측은 구현돼 있다, 첫 실측은 아직" 으로 갱신됨). **MEDIUM** `[order_channel]` 이 `routed != base` 게이트 때문에 라우팅 자체가 죽은 `probe_error` 도 정상 유지 사유(`pre_nxt_keep` 등)와 똑같이 침묵했다 — `probe_error` 만 게이트 밖에서 남기도록 시정(`test_r8b` 의 "정상 유지 시 침묵" 계약은 무변경). **MEDIUM** ETP 관측(`_observe_after_exit_etp`)이 41 폴백 발사 **앞**에서 `await` 돼 손절 크리티컬 패스에 DB 왕복을 얹고 있었다 — `asyncio.create_task` fire-and-forget 으로 전환(`_log_stale_async` 선례 답습). **MEDIUM** `session_tracker.active` 가 기동 직후(첫 `tick()` 전) 빈 캐시인 채로 08:20~09:00 프리장 창과 겹치면 clause 4 가 실패해 KRX PRE_AUCTION 으로 조용히 새던 경로를, `_route_exchange_by_clock` 안에서 `active` 가 비었을 때만 `session.boards_at(moment.time())` 로 즉석 재계산하는 폴백을 추가해 닫았다(PR-F·프리장 사전 지정가 변환 두 frozen 세그먼트는 byte 동일 — 그 블록들은 여전히 `session_tracker.active` 를 직접 읽는다). 회귀 가드 = `test_r1f`/`test_r1g`(빈 캐시)·`test_r3d`(probe_error 비침묵)·`test_k11d`(경계 교차 일관성)·`test_k11e`/`test_k11f`(`[after_cancel_result]` 성공·실패)·`test_k7`(fire-and-forget 뒤 `asyncio.gather` 로 대기) — 전부 `tests/unit/engine/test_cycle287_exchange_routing.py`/`test_cycle287_krx_after_exit.py` 안. 프로덕션 diff 는 여전히 세 파일(`models/order.py`·`order_engine.py`·`api/order.py`, api/order.py 는 docstring 만)뿐이고 `scheduler.py`(3,897L)·8영역 나머지·전략 7파일·`strategy_base.py`·`market_state.py`·`sell_rejection.py` 는 diff 0 — 세션 트래커 파일 자체(`session.py`)도 무접촉(순수 함수 `boards_at` 을 읽기만 한다).
```

→ CHANGELOG: cycle287 행

### 2026-09-17 이관 — cycle295 규칙 3 전문 — 명세 §9-Q2 현실 관측 fail-open 권고와 착지 직후 철회 경위 포함

```
- 🔴 **cycle295(2026-09-16, 사용자 결정 2026-09-15) — 규칙 3: 15:30~16:00 은 완전 휴식이다.** 접촉 = `order_engine.py` 1파일(8영역, 승인). 라우터(`_route_exchange_by_clock`) **밖**의 순수·never-raise 술어 `_market_rest_now(now) -> (blocked, reason)` 를 **주문 발사점 3곳**(`execute_sell` 의 `target_exchange` 산출 직후·재시도 루프 앞 / `execute_buy` 의 중복매수 가드 직후·`get_buyable` 앞 = A-ATOMIC **밖** / `_cancel_and_reorder` 의 `sleep(30)` 뒤·`cancel_order` 앞)에만 건다. **시각 리터럴 0건** — 경계는 전부 `market_state.get_market_state(now, market=...)` 파생이다.
  - **왜 라우터 밖인가** — `_strategy_exchange_async` 는 `_probe_nxt_downgrade_base` 를 먼저 부르고, 그 함수는 `stock_master.nxt_tradable=False` 종목에 `"KRX"` 를 돌려준다. 그 코호트(마스터 **83.2%**)는 라우터에 `base="KRX"` 로 들어가 clause 1 에서 **즉시 반환**되어 뒤 clause 에 닿지 않는다 — 라우터 안에 컷을 넣으면 컷이 가장 필요한 다수 코호트를 통째로 비껴간다.
  - **판정** = 프리장(`session_tracker.active` 가 `PRE_NXT` 단독, 라우터 clause 4 와 **같은 출처**)→`pre_nxt_keep` / 그 시각 KRX 가 `_SENDABLE_DIVISIONS` 중 하나라도 받으면 →`krx_sendable` / KRX·NXT 둘 다 세션이 없으면 →`no_session`(야간 안전망 보존) / 그 밖 →**`market_rest`(컷)**. 판정 예외는 `probe_error` **fail-open**(컷하지 않는다).
  - **`_cancel_and_reorder` 는 쌍으로 막는다** — 이것만 `cancel_order` → `place_order` 의 atomic replace 다. 절반만 막으면 "호가창에 있던 손절을 우리가 빼고 아무것도 안 넣은" 상태가 된다. 컷이면 **취소도 하지 않고** 작동 중인 주문을 그대로 둔다(16:00 이후 `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임).
  - **컷이 「하지 않는」 것 4** — 거부 등록 안 함(`SellRejectionTracker` 에 걸면 NXT 시간대 TTL = 다음 09:00 이라 그 한 건이 16:00~20:00 KRX 애프터 청산 4시간을 잠근다) · 익일청산 미전환(16:00 에 KRX 애프터가 열리므로 컷은 취소가 아니라 **최대 20분 유예**다) · 포지션 불변 · `_selling` **유지 금지**(유지하면 그것이 곧 stale `_selling` 좀비 = 손절 마비).
  - **마커 2종** — `[market_rest_blocked] side= ticker= strategy= base= reason=`(1회/(ticker,side)/일, **이 사이클이 무엇을 잃는지의 유일한 분모**) + `[market_rest_window] start= end= source=market_table`(1회/일 카나리아, 차단 0건인 날에도. `start`/`end` 는 리터럴이 아니라 표에서 역산). 둘 다 `KstDailyEmitCap` + never-raise이고 **행위는 cap 밖**이다.
  - 🔴 **현실 관측 fail-open 은 착지 직후 적대 검증으로 철회했다.** 명세 §9-Q2 권고는 "컷 창 안에 그 종목 틱이 최근 N초 내 들어오면 fail-open + `[market_rest_reality_mismatch]` CRITICAL" 이었다. 해제 키가 `scanner.ticker_last_tick` 신선도였는데 두 사실이 그것을 무너뜨렸다 — ① `risk.on_tick` 이 **같은 콜스택**에서 그 dict 를 먼저 쓰고(`risk.py:585`) 곧바로 `execute_sell`/`execute_buy` 를 부르므로 게이트가 재는 틱 나이가 **항상 0.0초**다(그 구간의 청산 트리거는 WS 틱 단독 — REST 폴은 15:20 에 끝난다). 즉 컷이 막으려던 유일한 경로가 정확히 컷을 **100% 해제**했다 ② 설령 ①을 고쳐도 KRX **K5**(15:30~16:00 장후 시간외 종가, `fixed_price ('06',)`)가 **같은 채널 `H0STCNT0`** 로 실제 체결 프레임을 보낸다 — "틱이 온다" 와 "우리 호가유형이 접수된다" 는 분리된 사실이라 신선도는 해제 키로 성립하지 않는다. **신선도 기반 해제를 다시 들이지 마라.**
  - ⚠️ **남은 한계(§4-6, 명시)** — `market_state` 표는 날짜 범위만 보는 고정 벽시계라 **특별 개장일(지연 개장, 수능일이 표준 사례)을 모른다**. 그런 날 15:30~16:00 은 실제로 연속체결 중인 정규장인데 컷이 **30분 무음 차단**한다(연 1회 수준). 닫는 방법은 신선도가 아니라 **표에 거래일·특별일 입력을 넣는 것**이다(별건 카드).
  - ⚠️ **면제 경로 = `POST /api/trading/manual-sell`.** 그 라우트는 `place_order` 를 직접 불러 `execute_sell`·`_apply_clock`·`_route_exchange_by_clock` 을 하나도 거치지 않으므로 게이트에 닿는 경로가 **구조적으로 없다**(운영자 수동 조작은 막지 않기로 한 결정). 그 구간엔 응답 message 에 경고가 붙고 접수 로그에 `[market_rest_manual_exempt]` 가 찍힌다 — **D+1 에 그 구간 주문이 1건 나오면 이 라우트를 먼저 본다.**
  - ⚠️ **판독 보조** — 컷 창 판정의 프리장 예외는 `session_tracker.active`(30초 주기 전역 캐시, `now` 와 무관)를 먼저 보고 비었을 때만 `boards_at(now.time())` 로 폴백한다. 라우터 clause 4 와 **같은 출처**를 쓰는 것이 계약이지만, `stop`/`start` 가 보드 경계를 가로질러 캐시가 낡으면 컷이 조용히 풀리거나(캐시 `{PRE_NXT}` × 벽시계 15:45) 08:00~08:19 프리장 주문이 무주문으로 잘릴 수 있다(캐시 `{MAIN}`/`{POST_NXT}` × 벽시계 08:0x). `_session_loop` 이 도는 동안 staleness 는 30초로 묶인다. **`[market_rest_window]` 는 있는데 `[market_rest_blocked]` 가 0 인 날**은 ⓐ 그 구간 손절 신호 자체가 없었는지 ⓑ 세션 캐시가 낡았는지 두 가지를 먼저 본다.
  - ⚠️ **컷에는 장중 다이얼이 없다**(cycle287 의 두 다이얼과는 별개 — 그쪽은 cycle290 이 등재해 장중에 닿는다) — 컷은 `order_exchange_clock_mode` 에 **종속시키지 않았다**(명세 §9-Q1 권고 = 무종속. 없애자고 한 것이 다이얼인데 롤백 다이얼 하나가 방금 없앤 참여를 조용히 되살리면 자기모순이고, 종속시키면 44/41 KRX 애프터 청산 변환도 함께 꺼진다). 롤백 수단은 **1커밋 revert + 장외 배포**뿐이다.
  - ⚠️ **15:20 강제청산과의 경계** — `_force_clear_main_only` 는 진입 시 15:30 가드로 skip 하지만, 15:20 에 시작한 순차 루프가 15:30 을 넘기면 남은 종목은 조용히 컷되어 익일청산 안전망으로 밀린다(종전에는 APBK3013 거부 + CRITICAL 로그였다). 그 경우 `[market_rest_blocked] side=sell` 이 남는다.
```

→ CHANGELOG: cycle295 행

### 2026-09-17 이관 — cycle291 규칙 4 전문 — 접촉 파일 목록 · scheduler 라인 수 · 09-14 GTP 자동취소 실측 필드 전문 · cycle287 테스트 갱신 목록 · sha 핀 18곳

```
- **cycle291(2026-09-13, 사용자 결정 "(나)안") — NXT 프리장 매수를 GTP(27)로 + 취소가 원주문 호가유형을 관측한다.** 접촉 = `models/order.py`(enum `NXT_GTP_LIMIT="27"` 추가) · `order_engine.py`(8영역, 사용자 승인) · `api/order.py`(8영역, 사용자 승인) 세 파일뿐 — `scheduler.py`(3,897L)·8영역 나머지·전략 7파일·`strategy_base.py`·`market_state.py`는 diff 0.
  - **매수만, `27` 만.** 매수 PR-F 사전 지정가 변환 블록(`order_price=step_up(현재가,5)` 확정 **뒤**) 안에 게이트 4중이 붙는다 — `settings.is_production` ∧ `buy_exchange=="NXT"` ∧ `"27" in get_market_state(now, market="NXT").order_divisions`(시행일 2026-09-14·프리마켓 종료 08:50 경계는 `market_state.py` 표에서만 읽는다, 날짜·시각 리터럴 신규 0건) ∧ 이미 참인 프리장 판정. 넷 중 하나라도 실패·예외면 이미 확정된 `00`(LIMIT)이 그대로 나간다(순수 옵셔널 승격, fail-safe). `ORD_UNPR` 은 오늘 `00` 이 보내는 값과 **완전히 같다**(`step_up(현재가,5)`) — 가격 행위 변경은 0, 바뀌는 것은 08:50 이후 미체결의 **수명**뿐이다. 매도(`execute_sell` 프리장 사전 `step_down` 변환)는 **무접촉**(자문 §2 — GTP 매도는 08:50 자동취소가 `_selling` 을 ≈09:45(`_scan_loop` 첫 sync)까지 잠가 손절 재평가를 억제하고, 현행 `00`은 09:00:30 NXT 정규장에서 시세 아래 지정가라 거의 확실히 체결돼 안전망으로 기능한다 — 루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉 판정).
  - **화이트리스트 제거** — `place_kwargs["order_division"]` 게이트가 `== OrderDivision.LIMIT` 열거에서 `!= OrderDivision.MARKET` 로, `record_price` 게이트도 동일하게 일반화됐다(cycle287 `test_s4d` 원칙 승계 — 열거로 남기면 새 호가유형이 조용히 시장가로 떨어지거나 기록 가격이 변환 전 값으로 샌다).
  - **GTP 거부 폴백** — `27` 거부는 `_MARKET_ORDER_DISALLOWED_KEYWORDS`/`_MARKET_CLOSED_KEYWORDS` 어디에도 안 걸려 미분류로 `raise` 되면 `risk.on_tick` 을 죽인다(cycle229 실증). 그래서 폴백 게이트를 키워드가 아니라 "우리가 27을 보냈다"는 사실(`order_division is OrderDivision.NXT_GTP_LIMIT`)에 걸어 같은 가격 `00` 1회로 즉시 재주문한다(`[pre_nxt_gtp_fallback] ticker= reason=rejected msg_cd= msg1=`). 정규장·프리장·애프터의 기존 `is_market_order_disallowed` 폴백 경로는 byte 동일.
  - **마커** `[market_order_preconvert_pre_nxt]` 는 기존 4필드(`ticker/exchange/current_price/converted_to_limit_price`) byte 보존 + 꼬리 append `div= gtp=0|1 reason=ok|vts|exchange|not_effective|probe_error`(09-14 전후 grep 합산 가능). **`[pre_nxt_division_config] division=27 effective= production= exchange_gate=`** 1회/일 카나리아(적대 검증 시정 — 3렌즈 공통 지적) — 프리장 매수가 대부분의 날 0~2건이라 위 마커만으로는 주문 없이 "게이트가 무장됐는가"를 볼 채널이 없었다. **그날 첫 매수 후보가 이 블록에 도달해야만 발화한다** — 후보가 0건인 날은 이 카나리아도 침묵한다(무코드 대안 = `GET /api/market-state?market=NXT` 로 `order_divisions` 에 `27` 존재 여부 사람이 1회 확인).
  - **알려진 비용 — 2026-09-14 실측으로 전제가 뒤집혔다.** 자문 §1-d 와 이 문서의 종전 서술은 "거래소발 08:50 자동취소는 우리에게 어떤 통보도 만들지 않는다" 였으나 **둘 다 틀렸다**. 09-14 실측(073240 금호타이어, MTS 수동 주문 `27` 1주 5,160원, `order_no=0000149100`) — `08:29:34` 주문 접수 통보 + **`08:50:00` 정각에 같은 주문번호로 두 번째 통보**가 도착했고, KIS 주문내역이 그 주문을 `sll_buy_dvsn_cd_name='GTP매수자동취소*'`(`odno=0000149100` · `ord_dvsn_cd=27` · `ord_dvsn_name=GTP지정가` · `excg_id_dvsn_cd=NXT` · `ord_qty=1` · `tot_ccld_qty=0` · `rmn_qty=0`) 로 기록했다. **통보는 온다 — 우리가 `handler.py::_handle_execution` 의 `exec_type != "2"` 분기에서 DEBUG 한 줄만 남기고 버린다**(그 줄이 찍혔다는 것 자체가 프레임이 계좌 필터를 통과해 우리 핸들러까지 왔다는 증거다).
    **증상은 그대로다** — 잔존 상태(`pending_buys`/`pending_buy_amounts`/`_pending_buy_orders`/`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division`/`trade_history` PENDING 행)를 장중에 정리하는 경로가 **없다**. GTP 로 08:50 취소된 종목은 그날 21:30 `reset_daily_state()`(메모리 5종)까지, `trade_history` 행은 **영구**(07-06 101730 실사례) 남고 `is_ticker_blocked_for_buy` 가 그 종목의 그날 재진입을 막고 예산을 점유한다. GTP 는 이 빈도를 **늘린다**(08:50 까지 안 채워진 모든 프리장 매수가 대상. `00` 은 09:00:30 정규장 이월로 그 중 일부가 결국 체결/취소돼 조기 정리된다). 순수 기회비용(자본 위험 아님).
    ⚠️ **시정 경로가 달라졌다** — 종전에 적었던 "08:50 REST 잔량 스윕"(`scheduler.py` 접촉)은 **불필요하다** — 다만 근거는 하나 줄었다: 함께 적었던 "라인 상한 압박" 은 cycle292(2026-09-14, 여유 3 → **174줄**)로 소멸했고 남은 근거는 "체결통보가 이미 온다" 하나다. 이미 구독 중인 체결통보 채널로 취소가 도착하므로, `handler.py` 가 `exec_type=="1"` 프레임에서 취소를 판별해 콜백으로 넘기고 `order_engine` 이 잔존 상태를 정리하면 된다. 접촉 = `src/realtime/handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**) · `scheduler.py` **무접촉**.
    🔴 **선결 = 취소 프레임의 판별 필드 실측.** 09-14 관측은 "프레임이 왔다" 까지만 증명한다 — 현행 DEBUG 줄이 `order_no`·`ticker` 두 필드만 찍으므로 **그 프레임의 `fields[5]`(RCTF_CLS 정정구분)·`fields[12]`(RFUS_YN 거부여부)·`fields[14]`(ACPT_YN 1:주문접수 2:확인 3:취소) 실제 값은 모른다**. 접수(08:29:34)와 취소(08:50:00)를 가르는 필드가 무엇인지 확정하지 않고 분기를 짜면 접수 통보를 취소로 오인해 살아 있는 주문의 상태를 지운다. 관측 방법 = 그 DEBUG 줄에 `fields[:20]` 를 실어 GTP 미체결 1건 관측(`handler.py` 8영역 1줄 변경, 승인 대상).
    **측정** = 프리장 매수 발생일 09:05 `GET /api/trading/status` 의 `orders.pending_buy_tickers` 길이.
  - **취소 축 Stage A** — `_order_exchange`(cycle287)와 완전 대칭인 `OrderEngine._order_division: dict[str, str]`(order_no → 실제 전송한 `ORD_DVSN`, 등록 4곳·pop 2곳·`reset_daily_state()` clear — `scheduler.py` 는 무참조)이 신설됐고, `api/order.py::cancel_order` 에 키워드 전용 opt-in `order_division: str | None = None` 이 생겼다(falsy → `"00"`, 미전달 시 body 10키 byte 동일 — 런타임 캡처로 증명됨). **호출자 3곳(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)은 여전히 전달하지 않는다** — 정본에 취소 시 원주문 호가유형 승계 규약이 없고, 전송을 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `00`→`01`(원주문 시장가)로 바뀐다. `[after_cancel_result]` 가 `orig_dvsn=`(매핑값, 부재 시 `-`)·`dvsn_src=map|absent` 를 얻어 D+1 이후 층화 실측(비-`{00,01}` `orig_dvsn` 행만 `result=error` 면 Stage B 전송 검토 — 매매 행위 변경 = 별도 승인) 근거가 된다.
  - 자문 = `_workspace/domain_consult/cycle291_pre_nxt_gtp_20260913.md`. 회귀 가드 = `tests/unit/engine/test_cycle291_pre_nxt_gtp.py`(52 — 적대 검증 시정 3건: `_cancel_and_reorder`/`cancel_remaining` 의 `[after_cancel_result]` orig_dvsn/dvsn_src 커버리지 + `_handle_sell_fill` pop 이 `_pending_cancel_order_no` 게이트 밖임을 잠그는 행위 테스트) + `tests/unit/ast/test_cycle291_ast_scope.py`(44, 금지 파일 diff 0·`scheduler.py` **3,726L**(cycle292 가 VI 구독 176줄을 leaf 로 뺀 뒤의 값 — 이 서술은 역사가 아니라 *살아 있는 가드가 지금 재는 수*다)·`_SENDABLE_DIVISIONS` 확장 라우팅 무영향 봉인 + 취소 호출 3곳 소스 전수 `order_division` 미전달 봉인 + 매핑 등록이 `place_kwargs` 파생값을 읽는지 구조 확인 포함). cycle287 쪽 갱신 = enum 등식 `{00,01,41,44}`→`{00,01,27,41,44}`(`test_s4`/`test_k1b`, forbidden 집합에 `28`/`29` 추가) · `_FROZEN_SEGMENTS["execute_buy_prf"]` 새 sha(B5 카나리아 배관 포함) · `test_s4c` 반전(구 "opt-in 인자 없음" → 새 "opt-in kwonly + 기본값 None + byte 동일") · `test_s4c2` docstring 정직화(cycle291 이 `cancel_order` 시그니처에 kwonly 를 늘렸다는 사실 — 본문 문장 수 불변은 여전히 참) · 18곳 내용 sha 핀 갱신.
```

→ CHANGELOG: cycle291 행 · cycle292 행

### 2026-09-17 이관 — 프리 시장가 매도 사전 지정가 변환·매도 시장가 폴백·insufficient_quantity·`is_sell_qty_exceeded` 항목의 사이클 라벨(2026-08-06 · 사이클 55 R-1 Q3 · cycle236 N2 · C236-F1)

```
- **NXT 프리 시장가 매도 사전 지정가 변환 (2026-08-06, 매수 PR-F 대칭)**: `execute_sell` 이 프리장 단독(`PRE_NXT ∈ active AND MAIN ∉`) + `target_exchange ∈ (NXT, SOR)` + 시장가일 때 `step_down(현재가, 5)` 지정가로 사전 변환 — 매도는 호가 깊이로 **내려** 체결률 확보. 실효 대상 = LTV 만(risk 게이트가 나머지 전략의 프리장 매도를 원천 차단). 현재가 미수신 시 무변환(임의 가격 지정가가 더 위험 — 시장가 거부 → market_closed 보류가 안전망). INFO `[sell_market_preconvert_pre_nxt]`. ⚠️ 거부 분류 검사 순서 = `is_market_closed_rejection` **먼저**(프리마켓 msg1 이중 매칭 시 보류로 낙하 = 의도된 계약, `src/api/CLAUDE.md` 분류 헬퍼 절) — 순서 반전 금지. 회귀 `test_order_engine_sell_pre_nxt_preconvert.py`(6)

- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`. **사이클 55 R-1 (2026-06-03) 30초 TTL + NXT 익일 전환**: 폴백 결과(성공/실패) 무관 `SellRejectionTracker.register_market_order_disallowed(fallback_succeeded=...)` 위임 → 30초 TTL 등록 (동일 tick 폭주 차단). NXT 시간대 폴백 실패(`is_nxt_session=True, fallback_succeeded=False`) 시 `RejectionResult.next_day_clear_required=True` → `_pending_next_day_clear_provider().add((ticker, strategy_id))` + `[next_day_clear_deferred]` WARNING 1행. 폴백 실패 시 `_selling.discard` + positions 보존. 지정가 매도(`limit_price>0`)는 폴백 안 함. 키워드: `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` (APBK1943 / APBK3013)
- **`is_insufficient_quantity(err)`** (보유 수량 부족) → 재시도 중단 + 메모리/DB positions 정리. **사이클 55 R-1 (2026-06-03) Q3 reconciliation**: `SellRejectionTracker.register_insufficient_quantity` history 적재(차단 X, positions 제거가 자연 차단) + `[positions_reconciliation]` INFO 로그 + `get_balance()` 1회 호출 (실제 잔량 > 0 이면 재등록 권고 로그). 실패 graceful
- **`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조 (cycle236, N2 — 257720 실사고)**: APBK0400 "수량 초과" 는 부분 보유 내재 코드라 insufficient(통째 삭제) **흡수 금지**. `execute_sell` 재시도 루프에서 closed 다음·insufficient 앞에 `get_balance` 재대조 — ① 오염(`held < positions`) = `[sell_qty_reconciled]` WARNING + **held(보유 실체)로 보정**(sellable 아님 — C236-F1: 잠긴 주식도 보유라 손절 감시 수량은 held 가 정합, sellable 부족 재거부는 다음 분기가 흡수) + `save_position` DB 동행 + `continue`(3회 한도 내 자기 치유) ② 부분/전량 잠김(`held ≥ positions ∧ sellable < held`) = `[sell_qty_partial_locked]`/`[sell_qty_locked]` WARNING + 보존 + return — **`_selling` 의도적 유지**(열린 기주문 실재 = 진행 중 표식 참, on_tick 재진입 폭주 차단, stale 은 `[selling_reconcile]` 180s 재대조 소관. market_closed 의 discard 와 다른 이유 = 그쪽엔 열린 주문이 없다) ③ 실보유 0 = 기존 insufficient 경로 재사용 ④ 재대조 실패 = graceful 일반 재시도. ⚠️ sync 는 기보유 종목 수량을 갱신하지 않으므로 DB 보정 실패 시 구값 잔존(다음 보정/청산까지)
```

→ CHANGELOG: 사이클 55 행 · cycle236 행

### 2026-09-17 이관 — 체결 후처리 WS 구독 정리 hook 의 사이클 15-A 라벨

```
- 매도 → DB positions 삭제 + `sold_today` 등록. **사이클 15-A (2026-05-19) WS 구독 정리 hook** — `_unsubscribe_if_no_other_strategy(ticker)` 가 (a) `registry.is_ticker_held_by_any(ticker)=False` + (b) `_pending_next_day_clear` 부재 + (c) 모든 전략 `get_scanned_tickers()` 부재 — 모두 통과 시 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)`. KIS 정상 패턴 "불필요 종목 구독해제" 즉시 적용. `_pending_next_day_clear_provider` 는 scheduler 가 `OrderEngine.__init__` 직후 주입 (lambda)
```

→ CHANGELOG: 사이클 15-A 행

## session.py

### 2026-09-17 이관 — 「2026-09-14(월) 시장 제도 변경이 이 표를 어긋나게 한다」 절 전문 — 09-13 까지 열 + 시정 완료 항목 3·4·5·6

```
`MarketBoard` enum 5종 중 **실제로 쓰는 것은 3종**이다(사이클 26 에 `KRX_OPEN`·`KRX_AFTER` 비활성,
enum 값은 DB 파라미터 호환 때문에 남겼다 — `session.py::MarketBoard` docstring 이 정본).
`_BOARD_SCHEDULE` 실제 구간 = `pre_nxt` **08:00~08:59:59** / `main` **09:00~15:39:59**(15:20~15:30 buy_stop
구간 + 15:30~15:40 갭 마진 포함) / `post_nxt` **15:40~19:59:59**. `krx_open`(08:30~09:00)·`krx_after`(15:30~18:00)
는 **표에 없다**.

### 🔴 2026-09-14(월) 시장 제도 변경이 이 표를 어긋나게 한다

근거 = 한국투자증권 고객 공지(거래시간·가격제한·미체결 규약) + Open API 공지 2026-09-09
(TR·필드 변경분은 `docs/kis/README.md` 「제도 변경 공지 반영」 절이 정본).

| | 09-13 까지 | 09-14 부터 |
|---|---|---|
| KRX 시가 단일가 | 08:30~09:00 | **08:20~09:00** (40분 확대) |
| KRX 정규장 연속매매 | 09:00~15:20 | 유지 |
| KRX 종가 단일가 | 15:20~15:30 | 유지 |
| KRX 장전후 시간외 **종가** | 08:30~08:40 · 15:30~16:00 | **유지** |
| KRX 시간외 **단일가** | 16:00~18:00 (10분 주기 체결) | **폐지** |
| **KRX 애프터마켓** | 없음 | **16:00~20:00 · 실시간 연속체결 신설** |
| NXT 프리마켓 | 08:00~08:50 | 유지 (+ `GTP` 전용호가 신설, 08:50 미체결 일괄취소) |
| NXT 애프터 | 15:40~20:00 | 유지 (15:30~15:40 단일가) |

⚠️ **없어지는 것은 시간외 *단일가* 뿐이고 시간외 *종가* 는 남는다** — 둘을 섞으면 15:30~16:00 판단이 뒤집힌다.

**애프터마켓 상세** — 가격제한 **전일 KRX 정규장 종가 ±30%** · 호가유형은 지정가 계열 **7종만**
(`ORD_DVSN` 41~47, `docs/kis/domestic-stock-order.md`) · **시장가 불가** · **ETP(ETF/ETN) 제외** ·
수수료·세금은 정규장과 동일 · SOR 가능.

**주문 존속 규약이 거래소마다 반대다** — KRX 는 정규장 마감 후 미체결이 **자동 취소**되므로 애프터마켓에서
거래하려면 16:00 이후 **새로 주문**해야 한다. NXT 는 미체결이 애프터까지 **유지**된다. SOR 주문도 주문이
들어간 시장에 따라 자동취소될 수 있다.

**우리 코드가 어긋나는 지점** (시정 사이클은 `_workspace/00_URGENT_WORKLIST.md` 의 보드 재설계 C0~C6)

1. `_BOARD_SCHEDULE` 에 **KRX 애프터마켓(16:00~20:00) 구간이 없다.** `post_nxt` 15:40~20:00 은 NXT 기준이다.
2. 시가 단일가 08:30 을 가정한 곳 — 08:20 으로 40분 앞당겨졌다.
3. ✅ **시정 완료(cycle286 C4-a, C안)** — 종전 `order_engine.py::is_nxt_window` 가 `15:30~20:00`
   시계만으로 `stock_master.nxt_tradable=False` 를 썼던 것을 **거래소(`target_exchange ∈
   {"NXT","SOR"}`) ∧ 좁힌 프리장 창(`08:00~08:50`)** 판정으로 교체했다 — KRX 로 보낸
   애프터 주문의 거부는 이제 그 값을 쓰지 않는다(상세 = 이 파일 §order_engine.py 「NXT
   거래가능 사전 차단」 절, 마커 `[nxt_post_reinforce]`).
4. ✅ **시정 완료(cycle287)** — 애프터 시간대 시장가 주문 거부는 여전히 발생하지만
   (KRX 애프터에 시장가가 없다), 이제 `execute_sell` 이 시장가를 보내기 **전**에
   구간을 판정해 `44`(최유리지정가) 또는 `41`(지정가)로 사전 변환하므로 거부 자체가
   구조적으로 줄어든다. 그래도 `44`/`41` 자체가 거부될 가능성(ETP·가격제한·미지원)은
   `msg1` 원문 실측 전까지 모른다 — **분류에 의존하지 않는 구조적 폴백**(44→41, §S5)
   으로 그 미지를 우회했다(상세 = 이 파일 §order_engine.py 「cycle287」 절).
5. ✅ **시정 완료(cycle287)** — `OrderDivision` 에 `KRX_AFTER_BEST="44"`(1차) ·
   `KRX_AFTER_LIMIT="41"`(폴백) 2종 추가. IOC/FOK(42/43/45/46)·최우선지정가(47)는
   손절 수단으로 부적합해(잔량 자동취소·비크로스) 의도적으로 추가하지 않았다.
6. ETF/ETN 제외는 우리 유니버스가 이미 ETF 를 빼므로 **무영향** — cycle287 은 관측만
   추가했다(`[after_etp_exit_observe]`, `stock_master.raw.scty_grp_id_cd`, 행위 분기 없음).

- `_BOARD_SCHEDULE`: 시각 → 활성 보드 frozenset (H0NXMKO0 미수신 시 fallback)
- `SessionTracker.tick()`: `_session_loop` (scheduler 30s 주기) 에서 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅
```

→ CHANGELOG: cycle286 행 · cycle287 행

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

### 2026-09-17 이관 — `TIME_*` 표의 사이클 라벨·경위 주석 전문 — 사이클 26/51/142/171 · cycle269→270-B→270-C 토큰 재발급 시각 이동 · cycle283 D2~D5 분리 근거

```
| `TIME_AUTO_START` | 07:45 | DB `auto_start` 우선 폴백 자동 시작 |
| `TIME_BOOT` | 07:55 | `_boot()` (사이클 51 분해: 본체 `src/engine/boot_manager.py::boot(scheduler)` 위임 — 2 줄 wrapper. 외부 import 경로 영향 0) — `_preissue_all_tokens()` (사이클 20: 메인+보조 N 매니저 분당 1개 한도 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()` (보유 + 익일청산 후보 ticker 를 stock_master eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → **`portfolio_risk.check_budget_invariant` WARNING**(`position_ratio × max_positions > 1.0` 위반 시 `[budget_invariant_violation]`, 차단 아닌 관찰) → `allocate_funds(net_asset × ratio)` |
| `TIME_PRESUBSCRIBE` | 07:59 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task (`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`). 사이클 26: VB/LTV PRE_NXT 매수 제거됨 — `_confirm_breakout_open_prices(board="pre_nxt")` 대상 없음 (tradable_boards=("main",)) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV가 KRX 09:00 시가로 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산. 모두 이미 확정이면 idempotent skip |
| `TIME_SCAN_START` | 09:30 | 모멘텀 `scan_stocks()` + 통합 구독 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — **사이클 142 결함 #1 시정 **: POST_NXT 활성 여부 무관 `check_force_clear()` 호출 영속. VB(`tradable_boards=("main",)` 사이클 26 영속) = 전량 청산. LTV(`("pre_nxt","main","post_nxt")` 사이클 38 복원 영속) = `check_force_clear()` 본체가 `_limit_up_reached` 상한가 모드 종목 제외 → 일반 종목만 15:20 즉시 청산 + 상한가 모드 종목 NXT 익일 청산 모드 보존. *사이클 142 이전 결함*: `keeps_post_nxt=True` 시 `continue` 분기 → LTV 모든 종목 보류 (사이클 38 명세 위반) |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감. 사이클 26: `_confirm_breakout_open_prices(board="post_nxt")` 제거 (VB/LTV tradable_boards 에 post_nxt 없음). 15:30~15:39:59 = MAIN 유지 (종가 흡수 마진) |
| `TIME_EVENING_FUNNEL_CAPTURE` | 16:20 | **사이클 171** — 저녁 잠정 funnel 캡처 (`_evening_funnel_capture_task_loop`). 16:10 basics → **16:20 funnel** → 16:30 마스터 → (cycle283) 20:30 일봉 순서. 일봉 적재보다 **앞**이라 이 캡처는 여전히 전일 봉 기준 — 전략 `prev_idx` 가 날짜 비교라 결과 동일(행위 불변, 서술만 정정). `count_all` 폴링 대기 + 5 전략 prepare → `capture_funnel_snapshots(is_provisional=True)`. 운영자 전날 밤 후보 확인 (관찰성 전용) |
| `TIME_POST_NXT_OPEN` | 15:40 | **사이클 26 신규**: NXT 애프터 진입 (기존 15:30 → 15:40 으로 변경). 매도만 (VB/LTV tradable_boards=("main",)) |
| `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` | 19:00 | **cycle269 → cycle270** — 보조 시세 계정 접근토큰 강제 재발급 (`quote_token_refresh.task_loop`). 활성 계정 전부 `TokenManager.revoke()`→`issue()` 순차(cycle270 — `issue()` 단독은 KIS 동일 토큰 반환으로 앵커 불이동, 09-10 실측; 61s gap, 7계정 ≈ 7분, 요약 행 ≤19:08 가 정상). 매매 무관(시세 풀 전용) · 주계정 무접촉 · WS `approval_key` 무영향. **cycle270-B → cycle270-C(2026-09-10 밤)** 15:45 → 21:30(사용자 요구 "20:00 이후") 으로 옮겼으나 **21:30 은 `scheduler.start()` 루프 생존 창(~20:10 정산 → finally 가 task 전부 cancel) 밖이라 무발화** → 같은 밤 **19:00** 으로 재이동. 제약 = T·T−10분 장중 밖 + T+8분 < 20:00 REST 집중 창 + **T < TIME_SETTLEMENT(루프 생존)** + scheduler `TIME_*` 전수와 [T−10, T+8] 창 충돌 0(`test_c9`) + 주기 루프 시각 전수 < `TIME_SETTLEMENT` 영속 가드(`test_c10`). ⚠️ **cycle283** 이 `TIME_SETTLEMENT` 을 21:30 으로 옮겨 그 상한이 90분 늘었다 — **상한이 늘어난 것은 정산 시각이 옮겨졌기 때문이지 "루프 밖 시각을 다시 제안해도 된다" 는 뜻이 아니다**(cycle270-B 가 기각당한 값 21:30 이 이제 정산 시각인 것은 아이러니일 뿐, 그때 죽은 이유는 "21:30 이라서" 가 아니라 "정산 뒤라서" 였다) |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 애프터 신규 매수 중단, 변경 금지) |
| `TIME_NXT_POST_CLOSE` / `TIME_RECOMMENDATION` | 20:00 | `unsubscribe_all()` + `generate_recommendations()` — 동기 순차 (자문 ~3분). **cycle283** — 같은 20:00 이 `TIME_SESSION_START_CUTOFF`(기동 거부 경계)이기도 하다 |
| `TIME_SESSION_START_CUTOFF` | 20:00 | **cycle283 D4** — `scheduler.start()` 기동 거부 경계. 종전에는 `TIME_SETTLEMENT` 이 겸했는데 정산이 21:30 으로 밀리면서 분리했다(겸하면 20:00~21:30 재기동이 AI 자문·`auto_apply_recommendations` 를 재실행한다). `run_daily` 의 "이미 장 종료면 내일로" 판정도 **같은 상수**를 쓴다 — 갈리면 그 창에서 60초 주기 헛 재시도 ~90회(KIS 휴장일 API + WARNING 2행/회 → 그날 리포트 `level_counts` 오염). ⚠️ 그 창의 재기동은 **그날 20:30 일봉 적재를 통째로 잃는다**(다음 영업일 07:59 immediate 가 7일 증분으로 보정하지만 07:55 prepare 보다 늦다 — `[daily_head_stale]` 관측이 그것을 알린다) |
| `TIME_METRICS_SNAPSHOT` | 20:05 | **cycle283 D5** — metrics 1차 스냅샷(`daily_metrics_snapshot.run_daily_metrics_snapshot`, leaf). `api_metrics`·`strategy_funnel` 은 프로세스 메모리 전용이라 정산이 21:30 으로 밀리면 유실 노출이 10분 → 90분이 된다. **OpenAI 미호출**(비용·지연 0, `model`·토큰 5컬럼 전부 NULL) · **`reset_request_metrics()` 미호출**(부르면 21:30 완전판이 저녁 90분치만 본다) · never-raise · 마커 `[daily_metrics_snapshot] target_date= pass=1 elapsed_ms=` 실행당 1행 |
| `TIME_STOCK_MASTER_DAILY_LOAD` | 20:30 | **cycle283 D2** — KIS 일봉 적재(`scanner._stock_master_daily_load_once`). 애프터마켓 종료 후, 전량 스윕 ~121초 |
| `TIME_SETTLEMENT` | 21:30 | **cycle283 D3**(종전 20:10 — 일봉 적재 20:30 뒤여야 한다). `_settle()` → `generate_daily_log_report()`(= 완전판이 20:05 1차 행을 upsert 로 덮어쓴다) → **`purge_old_logs()`** (사이클 6 통합, 2026-05-20 — INFO 2일 / WARNING+ 30일 retention 자동 정리, 실패 graceful `[log_retention_skip]` INFO + 다음 사이클 재시도) → `_reset_daily_state()` (퍼널 카운터 초기화는 분석 *후*) |
```

→ CHANGELOG: 사이클 26 행 · 사이클 142 행 · 사이클 171 행 · cycle269 행 · cycle270 행 · cycle283 행 · cycle296 행

### 2026-09-17 이관 — `_scan_loop`·stale watcher·stale_manager 이주 bullet 전문 — 사이클 15-A/17/24/25-B/28/29-R1·R2·R3/60/61/63/66/67/74/78 · cycle215~218 · cycle240 · cycle241 실측과 검증 수치

```
- `_scan_loop()` (5분 주기, 09:30~): VB+LTV+donchian + 모든 전략 보유 합집합 재구독. **사이클 15-A (2026-05-19) KIS 정상 패턴 준수**: 기존 `unsubscribe_all() → subscribe_filtered_stocks()` 전체 재구독 → `_delta_unsubscribe_dropped(new_set)` (빠진 종목만 unsubscribe) + `subscribe_filtered_stocks` (scanner LOW 분기에 `already_in_pool` 가드 추가로 이미 구독 중 종목 SEND skip). KIS 공지 "비정상 케이스 2" (무한 등록/해제) 패턴 차단. HIGH 종목 (positions/next_day_clear) 은 always 호출 — 풀의 `_select_session` promote 보존. 직후 `_reprepare_breakout_if_empty()` (사이클 48, 2026-05-27 — 대상 `volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`. BFB/VCP 는 boot 실패/일시 API 오류 회복 안전망 — 주 메커니즘은 prdy 시간무관 유니버스) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`. **사이클 25-B (2026-05-20) `_resubscribe_stale_priority` 우선순위 분리**: positions/next_day_clear 소속 stale → HIGH+bypass_limit=True (메인 절대 보장, 기존), 그 외 후보 stale → LOW+bypass_limit=False (보조 분산). 2026-05-20 14:58 VB/LTV 후보 8종목 stale→HIGH 메인 승격→메인 과부하→silent inactive 사고 대응. 사이클 24 자동 reconnect 와 이중 안전망. **cycle215~217 (2026-08-13 재구독 안전망 정합화, 실측 손절 사각 시정)**: `resubscribe_stale_priority` 가 subscribe *전* **cycle217 구독상태 가드** — `kis_ws_pool.get_subscribed_tickers()` 스냅샷으로 실제 구독 종목은 `unsubscribe_in_pool`(**cycle215** 도입, K watcher 342 패턴 = split-brain 시 `_ticker_to_session[t]=main` 잔존→풀 dedup 가드가 재SEND 억제→개장러시 매수 보유 종목 온종일 미구독=손절 사각이던 것 복구, 실측 001450/053800 5h+ 미구독), 미구독(split-brain/stale 후보)은 `kis_ws_pool._ticker_to_session.pop` 직접(KIS unsubscribe 미발송 → **OPSP0003 'UNSUBSCRIBE not found' 스팸 회피**, 08-13 766→08-14 0). **cycle216 동시호가 LOW-scoped skip**(`is_call_auction_now` True → `low_targets=[]`, HIGH 유지 = 09:00 갭개장 대비) + **LOW-only throttle**(`RESUBSCRIBE_THROTTLE_SECS=180`=3×STALE_FRESHNESS, `_stale_last_resubscribe_at` gate, **HIGH 면제** = 300s 케이던스 LMS-safe·손절 직결, domain-consult). 부수 효과 = NXT 애프터 K watcher force_retry 4340→411(priority 가 timestamp 로 대체). **cycle240 (2026-09-02, 08-31 포렌식 결함 ⓑ — 5분 우선 재구독 핑퐁 시정)**: `resubscribe_stale_priority` 의 LOW 후보 소스가 `scanner.ticker_last_tick` **전수**(per-ticker pop 0건, 유일 정리 = 20:10 `_reset_daily_state` clear)라 매도·후보 이탈 종목이 20:10 까지 stale 자격을 유지 → 같은 `_scan_loop` 이터레이션 안 ~12초에서 `_delta_unsubscribe_dropped`(빼기) ↔ `_resubscribe_stale_priority`(되살리기) 1:1 무한 페어링(09-02 실측 034020 매도 후 35회 재구독, 일 ~900 종목언급). 시정 = priority 분리 **직후**·cycle216 A/B·cap **앞**에 `low_targets` 만 desired(breakout `_collect_breakout_tickers()` ∪ momentum `scanner._last_scan_result` = `new_set ∪ NDC` 동치)와 교집합. HIGH 는 `low_targets` 에 없어 필터를 지나지 않는다(구조적 면제 + `_high_collect_ok` 이중). 활성 게이트 = breakout 비어있지 않음 ∧ HIGH 수집 무예외 — off 면 현행 byte 동일(fail-open). `get_subscribed_tickers()` 는 desired 부적격(cycle215/217 split-brain 복구 계약 보존 — 미구독 desired LOW 는 여전히 `_ticker_to_session.pop` + 재SEND). 로그 = `[stale_priority_resubscribe] count=… tickers=… desired_low=… filtered_not_desired=… filtered_sample=…`(3필드 확장, `count=` 첫 필드 보존). ⚠️ 의미 반전 — `count` 감소가 정상(09-01 993 언급 → 기대 <50/일), 배포 전후 합산 금지. 잔여 = `ticker_last_tick` 매도 시 pop(8영역, 워크리스트 P1-7 후속 A)
- **사이클 17 (2026-05-19) — 사이클 15-B/C 전체 롤백**: `_near_signal_loop` + `stream_pool_manager` + `near_signal_monitor` + `settings.near_signal_mode` + `_build_priority_groups` 분기 + `_near_signal_task` 멤버 + `GET /api/realtime/stream-status` + 프론트 `StreamStatus` 메뉴 모두 제거. 단순화 원칙(단일 데이터 경로 + 신규 모듈 추가 금지) 위반 + 60s `_near_signal_loop` 와 `_scan_loop`/K stale watcher race → KIS `OPSP0002` 폭주 → tick_coverage 0% 결함(2026-05-19 15:15 사고). `_build_priority_groups` 는 항상 momentum/breakout 정상 list 반환. WS 등록 경로 = `_scan_loop` 5분 delta 단일. OPSP0002 차단은 `_handle_raw` 의 backoff (`_opsp_backoff_until`) 로 단순 흡수
- **사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영**: 1) `_check_and_resubscribe_stale` 의 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(HIGH, bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴). 2) OPSP0002 backoff 60s → 300s 연장 — `_scan_loop` 5분 주기 ≥ backoff 만료 보장. KIS 인용: "기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록 (다수 요청 시 LMS + 앱정보 이용중지)". `MAX_STALE_RETRIES=5` 신규 상수 — 6회 이상 stale skip (영구 stale 의심)
- `_stale_watcher_loop()` (`_check_and_resubscribe_stale`, 120s 주기): `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick` 비교. `STALE_FRESHNESS_SECS=60s` 초과면 stale, 종목별 `_stale_retry_count` 누적. **사이클 17 보강 (2026-05-19) — KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영**: 1~5회 `pool.resend_subscribe_for_ticker` (같은 종목 재SEND) 분기 완전 폐기 → 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건). 6회 이상 (`> MAX_STALE_RETRIES=5`) → 사이클 28 *전*: skip / **사이클 29-R1 (2026-05-21)**: 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS` (사이클 29-R1 300s/5분 → **사이클 102 600s/10분 상향**) 경과 또는 `_stale_last_resubscribe_at` 부재 시 강제 재등록 + `_stale_retry_count[ticker]=0` 리셋 + `_stale_force_retry_history` (60분 슬라이딩 윈도우) 등록. `STALE_FORCE_RETRY_HOURLY_CAP` (사이클 29-R1 12 → **사이클 102 6 상향**) 초과 시 `[stale_force_retry_cap]` WARNING skip. 영구 stale 무한 skip 결함 차단. **사이클 29-R3 (2026-05-21) — K stale watcher 양쪽 분기 우선순위 분리**: `high_tickers` = `registry.all()` positions ∪ `_pending_next_day_clear` 합집합. `ticker in high_tickers` → HIGH+bypass=True (메인 절대 보장), 그 외 → LOW+bypass=False (보조 분산). 사이클 28 실측 main=25/보조 합 9 편중 73% → R3 후 main=2/보조 합 34 편중 5%. F1(재연결 1회) + `_scan_loop`(5분) + K(120s) + `_resubscribe_stale_priority`(5분 우선) 4중 안전망. **사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect**: K stale watcher 가 종목별 재등록 외에 세션 자체 결함도 5분 지속 후 `_force_reconnect_session(label)` 으로 `_ws.close()` 발화 → 재연결 자동 발화. **사이클 29-R2 (2026-05-21) 정의 완화**: `fresh==0` → `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 3중 가드. 시간당 2회 cap (LMS / 앱 정지 위험 차단) 보존. 사이클 28 실측 메인 fresh=2/25=8% 결함 자동 감지. **cycle241 (2026-09-02) — 세션 상대 판정으로 4중 (08-31 포렌식 결함 ⓐ · P1-4)**: 세션별 독립 판정이 시장 전체가 조용한 슬롯(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 · 15:30~15:40 마감 흡수)에서 8세션 동시 침묵을 '8개 동시 고장'으로 오판해 8세션×3슬롯 강제 재연결 = 접속키 하루 16~24 낭비(EC2 30일 522건 중 491건 94.1% 풀 전원 동시, 09:00~15:20 정규장 0건, 재연결 회복 가치 0 — 회복 시각은 항상 15:40 POST_NXT 진입) → `detect_silent_inactive_sessions` 를 2-pass 로 재구성: pass 1 세션별 `(label, subscribed, silent_suspect)` 상태 무변경 계산 → 판정 가능 세션(`subscribed >= 5`) ≥ `_MARKET_WIDE_MIN_ELIGIBLE(=2)` ∧ **전원** suspect 면 **시장 침묵 = 판정 가능 전 라벨 first_seen pop + `[]`**(hold 금지 — 침묵 중 first_seen 이 자라면 재개 순간 지각 세션이 즉발) → pass 2 사이클 24/29-R2 누적 루프 byte 동일. 판정 가능 < 2(VTS 단일 세션·20:00 unsubscribe_all 후) 또는 하나라도 fresh(진짜 단독 결함) 면 현행 byte 동일(fail-open) = **결과 집합 ⊆ 현행**. 시각 게이트(`is_call_auction_now`·`boards_at`·시간창 리터럴)·`session` import 미사용(AST G-241-5 — 운영 8세션에선 세션 비교만이 15:30~15:40 갭까지 닫는다). 관측 `[silent_inactive_market_wide_skip] transition=entered|persisting(≥1800s 지속 WARNING 1800s 마다)|exited(elapsed_secs·cycles)`, 상태 `_MW_EPISODE` 모듈 전역 날짜 키 자기 리셋(StaleTrackerState 7필드 가드·scheduler 3,999L 이라 유일 위치), peek→로그→mark, `write_log` 0. 마커의 `connected=`(`_ws` 객체 보유)·`reconnects=`(핸드셰이크 재시도 인덱스 합 — `force_reconnect_session` 강제 close 미반영)는 소켓 생존 확증이 아니다 → `[ws_heartbeat]` + `persisting` 지속으로 읽는다. ⚠️ 의미 반전 — `[silent_inactive_force_reconnect]` 24/일 → 0~3(전부 16:00+ main 단독 = 후속 domain-consult 축), `entered` 2~3행/일(≈08:51~53·≈15:21~23), `persisting` 0행이 정상, 배포 전후 같은 grep 합산 금지. 2회 cap·`_silent_inactive_recovery_count` 동일성·`force_reconnect_session` diff 0. **사이클 28 (2026-05-21) — 추적 강화**: `_stale_last_resubscribe_at: dict[str, datetime]` 신규 + `[stale_watcher_detail] session=main sub=22/41 fresh=8 stale=14 ratio=0.64 stale=[(009150,r=3,@09:12:45),...]` 신규 prefix (종목 cap 20 + overflow `...+N`). 기존 `[stale_watcher]` / `[stale_priority_resubscribe]` 보존. **cycle218 (2026-08-14) — r 카운터 무한 climb 관찰성 정리**: cooldown-skip 분기(`age_secs < STALE_FORCE_RETRY_AFTER_SECS`)에서 `_stale_retry_count[ticker] = MAX_STALE_RETRIES+1` 홀드. priority_resubscribe(cycle215 실효화)가 `_stale_last_resubscribe_at` 를 5분마다 갱신 → force_retry 600s 게이트 지속 미충족 → r 리셋 없이 무한 climb(실측 051905 **r=131**)하던 오해 숫자 제거. r>5 는 전부 동일 임계 경로(force_retry `>MAX` / universe_guard `<=MAX`(`stale_universe_guard.py:85`) / diagnostics `<2`(`stale_diagnostics.py:243`))라 **행위 불변**(reset-to-0 는 universe guard 가 persistent-stale 종목 미제외로 깨져 캡이 정답). force_retry FIRE(age≥600) r=0 리셋 + 1-5 즉시 재등록 무손상. **cycle240 주석 (2026-09-02)**: 이 120s 경로는 소스가 `get_subscribed_tickers()`(구독 집합 한정)라 5분 우선 경로의 핑퐁 결함(`ticker_last_tick` 전수)이 **없다** — 두 경로의 소스 비대칭이 뿌리였고 cycle240 은 5분 경로(`resubscribe_stale_priority`)만 손댔다. D+1 `[stale_watcher_detail] stale=` 수 감소(유령의 5분 구독 점유 소멸)로 간접 확인.
- **`_refresh_stale_ccnl_cache(stale_tickers, cap=20)` (사이클 37, 2026-05-21)**: stale r≥2 종목 대상 `quotation.inquire_ccnl` 호출 + `_last_ccnl_cache: dict[ticker, dict]` 갱신. TTL 5분 + cap 20 + 종목 간 50ms sleep + 보유 종목 우선 처리 + KIS None/예외 graceful 캐시 미저장. `_scan_loop` (5분 주기) 통합 + `_reset_daily_state` 동행 clear. R4 universe guard 와 race 무해 (TTL 자동 차단). `/api/realtime/subscriptions` 의 `tickers_detail.last_cntg_hour / today_volume` 응답 데이터 소스.
- **`_evaluate_universe_guard(candidate_tickers)` (사이클 32 R4, 2026-05-21)**: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 universe 제외. 사전 가드 (보유/익일청산/이미 제외/stale≤5 → KIS 호출 자체 skip) + `inquire_ccnl` 호출 + `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` + `[universe_excluded] ticker=... reason=stale_6plus_low_volume retries=... last_resub_age=...s last_cntg_hour=... today_volume=...` INFO + system_logs 영구. `_collect_breakout_tickers` 필터링 + `_scan_loop` 5분 주기 통합 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지).
- **사이클 60 Phase 2-A1 (2026-06-04) — `stale_manager.py` 신규 모듈 추출**: 5 함수 (`_build_session_subscription_view` / `_emit_stale_session_detail` / `_refresh_stale_ccnl_cache` / `_evict_expired_ccnl` / `_prune_force_retry_history`, scheduler.py 의 ~275L) + 5 상수 (`MAX_STALE_RETRIES` / `STALE_FORCE_RETRY_AFTER_SECS` / `STALE_FORCE_RETRY_HOURLY_CAP` / `UNIVERSE_LOW_VOLUME_THRESHOLD` / `SILENT_INACTIVE_FRESH_RATIO_THRESHOLD`) 모두 stale_manager.py 로 이전. **사이클 51 boot_manager 패턴 답습** (scheduler 인자 + 2 줄 wrapper 위임). **행위 변경 0** (refactor) + **5 상수 re-export 호환** (`is` 동일성). **logger 명시 binding**: `logging.getLogger("src.engine.scheduler")` — 사이클 28 회귀 가드 (`caplog.set_level(logger="src.engine.scheduler")`) + 운영 logging config 호환 보존 (`__name__` 사용 시 `[stale_watcher_detail]` 운영 로그 누락 위험). property 7 쌍 (`_stale_retry_count` / `_stale_last_resubscribe_at` / `_last_ccnl_cache` 등) layer 보존 — `src/routes/realtime.py:88-91` `getattr` 호환. scheduler.py 3,880 → 3,605L (−275L, −7.1%). K stale watcher 핵심 (`_check_and_resubscribe_stale` 221L + `_resubscribe_stale_priority` 100L) 은 scheduler.py 잔류 (Phase 2-A2 사이클 61 / 2-A3 사이클 62 분리 예정).
- **사이클 61 Phase 2-A2 (2026-06-05) — `stale_manager.py` 4 함수 + 5 상수 추가 이주**: `_detect_silent_inactive_sessions` (62L, 사이클 29-R2 silent inactive 3중 가드 — **cycle241 이 이 함수에만 의도된 행위 변경(세션 상대 판정 4중)을 도입, 나머지 2 함수 diff 0**) + `_force_reconnect_session` (83L, 사이클 24 세션 강제 reconnect, **KIS LMS/앱키 정지 위험 직접 영역**) + `_delta_unsubscribe_dropped` (52L, 사이클 15-A delta 패턴) + `_evaluate_universe_guard` (117L, 사이클 32 R4 보유/익일청산 보호) = **314L**. 추가 5 상수: `STALE_FRESHNESS_SECS=60` (사이클 17) + `SILENT_INACTIVE_MIN_SUBSCRIBED=5` / `SILENT_INACTIVE_PERSIST_SECS=300` / `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR=2` / `SILENT_INACTIVE_RECOVERY_WINDOW_SECS=3600` (사이클 24/29-R2). 누적 9 함수 + 10 상수 (사이클 60 A1 5+5 + 사이클 61 A2 4+5). scheduler.py 3,605 → 3,315L (−290L). stale_manager.py 358 → 731L. **사이클 60 lazy import 빚 청산**: `_build_session_subscription_view` 의 `from src.engine import scheduler as _sched_mod` 1 줄 제거 (`STALE_FRESHNESS_SECS` 이전으로 자연 해소). **`sys.modules.get("src.engine.scheduler")` 패턴**: `detect_silent_inactive_sessions` / `force_reconnect_session` 에서 `kis_ws_pool` / `kis_ws` / `datetime` 접근 시 scheduler 네임스페이스 우선 참조. D-1 AST 가드 통과 (정적 import 0) + 테스트 patch 호환 (`patch("src.engine.scheduler.kis_ws")`) + 운영 환경 동일 객체. **회귀 가드 20 케이스 (12 파일 분리)**: A 위임 4 + B 5 상수 동일성 + **C cap dict `is` 동일성 (HIGH)** + D 의존성 역전 정적 + E reset_daily 동행 + F dataclass 7 필드 누락 가드 (2 케이스) + G silent inactive cap freezegun + H 5분 지속 freezegun + **I universe guard 보유 보호 (HIGH)** + **J universe guard 익일청산 보호 (HIGH)** + K delta unsubscribe race best-effort + L import sanity. **백엔드 1862 → 1882 PASS** (+20, 회귀 0). 누적 scheduler.py 라인 감소: 사이클 51 직전 ~4,185 → 사이클 61 후 3,315 (**−870L, −21%**). **A3 (사이클 63) 잔여 2 함수**: `_check_and_resubscribe_stale` 221L + `_resubscribe_stale_priority` 100L = K stale watcher 핵심 — *주말 push 의무 + 월요일 첫 _boot 1h tester verify*.
- **사이클 66 (2026-06-06) — `_resubscribe_stale_priority` cap=10 결함 시정 (카드 #5 HIGH, 사이클 63 K-2 발견)**: 사이클 63 발견 결함 영속 시정. **결함 (사이클 63 K-2 PASS = 결함 confirm)**: `stale_manager.py:1023-1034` `targets = stale_tickers[:cap]` 가 priority 분리 *전* `[:cap]` 적용 → HIGH 종목 (보유/익일청산) 이 sorted LOW 후보에 밀려 cap 밖 잘림 가능 → 5분 우선 재구독 누락 → KIS LMS chain 사고 위험 (사이클 29 005935 사고 패턴). **시정 (사이클 66 K-2 = 시정 confirm 의미 전환)**: ~22L 교체 — Q1 priority 분리 *먼저* (`high_targets = [t for t in stale_tickers if t in high_tickers]` / `low_targets = [t for t in stale_tickers if t not in high_tickers]`) + Q2 try/except 4중 가드 통일 (본체 `_check_and_resubscribe_stale` 답습 — `for s in registry.all()` outer try + inner positions try + NDC try) + Q3 HIGH > cap 모두 보장 + `logger.warning("[stale_priority_resubscribe_cap_exceeded]...")` (운영 가시화) + 최종 `targets = high_targets + low_targets[:max(0, cap - len(high_targets))]`. **회귀 가드 11 케이스 (단일 파일 `tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`, HIGH 4)**: K-2 시정 confirm (Q6-4 docstring 의미 전환 명시) + K-3 HIGH 12 > cap=10 모두 통과 + K-4 HIGH 5 후반 + LOW 20 정확 분리 + K-5/K-6/K-7 LOW 영속 + **K-8 registry 예외 try/except 4중 (Q2)** + K-9 HIGH 0 + LOW 0 early return + **K-10 WARNING 발화 (Q3)** + **AST 정적 가드** (`stale_tickers[:cap]` 잔존 0건 + `low_targets[:max(...)]` 패턴 1건). **사이클 63 K-2 의미 전환**: `tests/unit/engine/test_cycle63_phase2A3_priority_cap.py::test_K2` 에 `@pytest.mark.xfail(strict=False)` 마킹 — 사이클 63 시점 결함 confirm 영속 보존 (호환), 사이클 66 시정 완료로 자동 XFAIL 전환. **백엔드 1975 → 1984 PASS + 1 XFAIL** (+9 신규 PASS + 1 의미 전환 XFAIL) / 회귀 0 / coverage 80.95% (+0.02%). **사이클 29 005935 사고 패턴 영구 차단** (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + KIS LMS chain 차단). **사이클 38 명문화 영속** (시세 영역 — 매도/익일청산/손절 영향 0). **무변경 영역 (회귀 가드)**: `sys.modules.get` 패턴 (사이클 61 D-1 AST) / `kis_ws_pool.subscribe(priority, bypass_limit)` 인터페이스 / `_stale_last_resubscribe_at` 갱신 / `asyncio.sleep(0.05)` Rate Limit / `[stale_priority_resubscribe]` INFO + `write_log` fire-and-forget / `high_tickers` ↔ `bypass_limit` 매핑 (HIGH=True / LOW=False) / 함수 시그너처. **월요일 (2026-06-09) 09:00~10:00 1h tester verify 시나리오 D 신규** (Q5 자문): HIGH 인위 stale 주입 보유 0 종목 + 신규 측정 지표 3 (HIGH 5분 우선 재구독 보장률 100% / WARNING 발화 빈도 / HIGH 회복 시간 ≤5분) — 시나리오 A/B/C/D 결합 효과 측정. domain-expert 자문 옵션 A 전부 (Q1~Q5 + Q6-1~Q6-6) 7 사이클 연속 패턴 일관 (사이클 55 R-1 / 60 / 62 / 63 / 64 / 65 / 66).
- **사이클 78 (2026-06-08) — 사이클 74 도입 누락 silent 결함 시정 (flush 호출 사이트 0건 + 메모리 leak 영구 차단)**: 사이클 78 C 진단 (Supabase READ-ONLY) 결과 = `[swing_rest_poll_summary]` + `[stale_watcher_summary]` 영구 0건 확정. **근본 원인**: 사이클 74 commit (`0017fe0`) 가 `record_swing_rest_poll` + `flush_swing_rest_poll_collector` + `record_stale_watcher_check` + `flush_stale_watcher_collector` 함수 도입했으나 *5분 주기 호출 사이트 누락* + 사이클 76 commit (`0d633a8`) 가 `_api_recovered_collector_loop` task 도입했으나 *swing/stale flush 도 함께 호출 누락* → collector 무한 누적 (메모리 leak HIGH) + summary 영원히 emit 0건. **시정 (옵션 1 = 사이클 76 task 재사용, +26L)**: `scheduler.py::_api_recovered_collector_loop` (L2469~L2480 영역) 본체에 `flush_stale_watcher_collector` import 추가 + swing/stale flush 4 줄 (try/except 각각) + `if not self._running: break` 를 flush 블록 *이후*로 이동 (sleep 후 무조건 1회 flush 보장, 사이클 42 답습) + `scheduler.py::stop()` lifecycle hook 양쪽 flush try/except (Q5 사이클 74 답습, `unsubscribe_all()` 직전 잔여 카운터 손실 방지). **회귀 가드 6 케이스 (3 파일)**: G-FL1~FL4 flush 호출 사이트 (각 collector ≥1건 + lifecycle hook + 5분 task co-located) + G-ML1 메모리 leak 차단 (5분 윈도우 종료 후 `len == 0`) + **G-AST1 영구 가드** (`record_*` 정의 모듈의 대응 `flush_*` 호출 사이트 ≥1건, 미래 신규 collector 추가 시 flush 호출 누락 영구 차단). 백엔드 2083 → 2089 PASS (+6) + 1 XFAIL + 2 skip / flakiness 0 / 회귀 0. **C 진단 부차 확정**: `[swing_rest_poll]` 개별 마지막 14:09:27 KST (사이클 74 배포 14:13 KST 이전) + `[stale_watcher]` 개별 마지막 14:08:57 KST = 모두 배포 후 emit 0건 = 사이클 74 collector 흡수 정상 작동 확정 = **카드 #19 (realtime_other 16.13x, 사이클 73 인계) 거짓 알람 종결**. **부차 발견 카드 #20 (LOW)**: `stop()` task cancel 목록 (L860~865) 에 `_api_recovered_collector_task` 누락 (좀비 task 위험, 운영 중 `_running=False` → loop 자연 종료로 즉각 위험 낮음, 본 사이클 범위 외). 17 사이클 연속 옵션 A 패턴 영속 (55 R-1 / 60 / 62~69 / 72~78). silent 결함 영구 차단 13 회 누적
- **사이클 74 (2026-06-08) — WebSocket 로그 sampling/aggregation 옵션 E-1/C 도입 (카드 #19 인계, refactor-expert 자문 6 카드 #A/#B 채택)**: 사이클 71/73 운영 실증 dup_factor 잔존 영역 (`[swing_rest_poll]` 5.00x / `[stale_watcher]` 3.00x / WS 구독·ACK·해제 logger.info 빈도) 5분 윈도우 1행 aggregation 흡수. **신규 모듈 헬퍼**: `stale_watcher_core.py` +51L (`record_stale_watcher_check(stats)` + `flush_stale_watcher_collector()` 모듈 전역, `[stale_watcher_summary] checks=N stale_total=M retried=K cap_blocked=L force_retried=J` 1행 emit, **결함 시 (`stale_count > 0`) `[stale_watcher_detail]` individual 영속** + 사이클 66 K-10 `[stale_force_retry_cap]` / `[stale_priority_resubscribe_cap_exceeded]` WARNING individual 영속) + `scheduler.py` +42L (`record_swing_rest_poll(stats)` + `flush_swing_rest_poll_collector()`, `[swing_rest_poll_summary] polls=N candidates_avg=X max=Y total_held=Z elapsed_ms_avg=W` 1행 emit). `_run_swing_rest_poll_once` (L2319) + `check_and_resubscribe_stale` (L237) 직접 `logger.info(...)` 제거 + collector 흡수. **AST 영구 가드 G-7/G-8 신설**: G-7 (`_send_subscribe` 직접 logger.info 0건) + G-8-A (`_run_swing_rest_poll_once` 영역 한정) + G-8-B (`check_and_resubscribe_stale` 영역 한정). **회귀 가드 9 케이스 (engine 영역)**: G-SP1~SP4 swing_rest_poll aggregation freezegun (5분 윈도우 / 통계 정확 / window reset / shutdown flush, Q5 옵션 A) + G-SW1/SW2/SW5 stale_watcher aggregation + G-SW3 `[stale_watcher_detail]` individual 영속 + G-SW4 `[stale_force_retry_cap]` WARNING 영속 (사이클 66 K-10). 운영 효과 예상: `[swing_rest_poll]` ~720/day → 144/day (~80% 감소) + `[stale_watcher]` ~360/day → 144/day. **사이클 17/29 LMS chain 차단 영속** (collector 흡수만, `_opsp_backoff_until` 등록 행위 변경 0) + **사이클 38/55 R-1/66/67 매매 안전성 영역 영향 0** (로깅 영역 시정만, ERROR/WARNING individual 보존 매트릭스 영속). 신규 모듈 헬퍼 = 영역별 격리 (Q3 옵션 A 채택, 사이클 76+ shared 헬퍼 추출 #20 인계). flush 주기 5분 (사이클 42 `HEARTBEAT_METRICS_INTERVAL_SECS=300` 답습, Q4 옵션 A).
- **사이클 67 (2026-06-06) — `stale_manager.py` 1,099L 4 sub-module + facade 96L 분해 (카드 #14 MEDIUM 종결, refactor #2 후속)**: domain-expert 옵션 A 자문 (Q1~Q5 + Q6-1~Q6-3) 전부 적용 (**8 사이클 연속 패턴 영속**) + **Q4 유일 불일치 채택** (옵션 B facade patch 영속, 자문 실측 `patch("src.engine.stale_manager.*")` = 0건 강력 권고). **분해 매트릭스**: `stale_diagnostics.py` 357L (5 함수 + 4 상수 — `build_session_subscription_view` / `emit_stale_session_detail` / `refresh_stale_ccnl_cache` / `evict_expired_ccnl` / `prune_force_retry_history`) + `stale_session_recovery.py` 274L (3 함수 + 5 상수 — `detect_silent_inactive_sessions` / `force_reconnect_session` / `delta_unsubscribe_dropped`) + `stale_universe_guard.py` 157L (1 함수 + 1 상수 — `evaluate_universe_guard`) + `stale_watcher_core.py` 399L (2 함수 — **K stale watcher 본체 HIGH hot path** `check_and_resubscribe_stale` 222L + `resubscribe_stale_priority` 100L). facade `stale_manager.py` 96L (`__all__` 21 항목 re-export only — 11 함수 + 10 상수). `scheduler.py` 11 wrapper L2435~L2501 + 5 상수 re-export L92 **변경 0** (Q5=A `from src.engine import stale_manager` lazy import 영속). **Q1=A facade** (단일 진입점 보존, 사이클 51 boot_manager 답습) / **Q2=P1 모듈-레벨 정적 import** (`stale_watcher_core.py:30-36` `from src.engine.stale_diagnostics import emit_stale_session_detail` 모듈-레벨, 함수-레벨 lazy import 비채택) / **Q3=A 4 sub-module 모두 `logger = logging.getLogger("src.engine.scheduler")` 명시** (사이클 60 I1 영속 — `caplog set_level(logger="src.engine.scheduler")` 호환) / **Q4=B facade patch 영속** (자문 실측 0건 → 갱신 의무 사실상 0, G-16 AST 신설로 silent 결함 영구 차단) / **Q5=A wrapper 변경 0** (`from src.engine import stale_manager; await stale_manager.X(self)` 패턴 영속). **Q6 채택**: Q6-1 (LOW) hot path import 캐시 측정 권고 / Q6-2 (MEDIUM) 사이클 71+ 옵션 B 헬퍼 청사진 (3 헬퍼 ~75L: `_sched_mod_get` / `_collect_high_tickers` / `_write_log_fire_and_forget`) / Q6-3 (MEDIUM) 사이클 68+ 시점 분리 권고 (사이클 67 push → 1 주 운영 → 사이클 68+ #16 후보 풀 폭축 회고 → 1 주 운영 → 사이클 71+ #15 액면분할). **사이클 29 005935 사고 영역 영속**: G-15 WARNING (`[stale_priority_resubscribe_cap_exceeded]` `stale_watcher_core.py:346-357`) + G-17 priority 분리 *후* cap AST. **사이클 66 시정 영속**: G-11 `high_targets`/`low_targets` 변수명 + G-12 try/except 4중. **회귀 가드 17 케이스 (6 파일, HIGH 6 = 35%)**: G-1~G-5 분해 검증 (5 — 4 sub-module 파일 존재 + 11 함수 + 10 상수 export + facade 21 `__all__`) + G-6~G-9 의존성+logger (4 — Q3 4 sub-module 동일 logger AST + Q1 단방향 의존 AST + Q2 모듈-레벨 정적 import AST + Q5 facade lazy import AST) + G-10~G-13 사이클 63+66 영속 (4 — Q4=B 직접 호출 + 사이클 66 변수명 + try/except 4중 + caplog 일관성) + G-14~G-15 사이클 60+64 영속 (2 — 폐기 메서드 0건 + 사이클 29 WARNING) + **G-16 facade patch 안전선 신규** (1 — `tests/unit/engine/` rglob `patch("src.engine.stale_manager.X")` → X facade export 검증) + **G-17 priority 분리 *후* cap 신규** (1 — `resubscribe_stale_priority` AST 정적 가드). **백엔드 1985 → 2002 PASS + 1 XFAIL** (+17 신규) **+ 2 skipped**. `tests/unit/engine/stale_manager/` 27 PASS / `tests/unit/engine/` 1,162 PASS + 1 XFAIL. flakiness 0 (3 회 `stale_manager/` 0.24~0.39s / `engine/` 36.34~36.56s, ±0.5%). 회귀 0 / 매매 안전성 무영향 (행위 보존 + 외부 인터페이스 0 + scheduler.py 변경 0). **누적 scheduler.py 감소** (사이클 51 직전 ~4,185 → 사이클 67 후 3,007 영속): **−1,178L, −28%**. **patch 경로 적응 3 건**: `test_C1` (`test_cycle60_phase2A1_stale_manager.py:227`) `patch.object(stale_manager, "evict_expired_ccnl")` → `patch("src.engine.stale_diagnostics.evict_expired_ccnl")` (본체 동일 모듈 네임스페이스 직접 호출 → facade patch 비효과) + `test_D2` (`test_cycle63_phase2A3_dependency_direction.py:64`) 단일 파일 grep → `stale_watcher_core.py` + `stale_session_recovery.py` 합산 grep (총 6건 ≥ 4 충족) + `test_cycle66_resubscribe_cap_priority_fix.py` 일부 적응. **G-12 라인 cap 마진 (정보, 결함 아님)**: `stale_watcher_core` 실측 399L (권고 ≤380L 대비 5% 초과) — 본체 라인 단위 보존 (행위 보존 의무 우선) + Q1/Q2/Q3 시정 모두 보존 결과. 후속 사이클 71+ Q6-2 헬퍼 분리 시 추가 압축 가능. **무변경 영역**: 함수 본체 라인 단위(**사이클 67 분해 시점 계약 — cycle241 이 `detect_silent_inactive_sessions` 1건을 의도된 행위 변경으로 예외 처리, 기계 가드 없음 실측·산문 재스코프. 2회 cap·`force_reconnect_session`·`delta_unsubscribe_dropped` 는 여전히 무변경**) + 시그너처 (`emit_stale_session_detail(scheduler,...)` Q4=B 답습) + 상수 값 (cap=10 / SILENT_INACTIVE_* / UNIVERSE_*) + `sys.modules.get("src.engine.scheduler")` 패턴 (`stale_watcher_core` 3건 + `stale_session_recovery` 3건 = 6건, 사이클 61 D-1 AST) + try/except 4중 (사이클 66 Q2) + 운영 prefix 전수 (`[stale_watcher_detail]` / `[stale_priority_resubscribe]` / `[stale_priority_resubscribe_cap_exceeded]` / `[stale_force_retry]` / `[silent_inactive_*]` / `[universe_excluded]`) + WebSocket 4중 안전망 호출 시점/횟수 0 + silent inactive 시간당 세션당 2회 cap + universe 가드 보유/익일청산 절대 보호. **월요일 (2026-06-09) 09:00~10:00 1h tester verify 의무** (시나리오 A 자연 monitoring + B 인위 stale 주입 보유 0 + C KIS LMS chain 차단 + D HIGH 인위 stale — 사이클 67 분해 후 운영 hot path 첫 노출 검증).
- **사이클 63 Phase 2-A3 (2026-06-06) — `stale_manager.py` K stale watcher 핵심 2 함수 추가 이주 (HIGH, refactor #2 완료)**: `_check_and_resubscribe_stale` (222L, **K stale watcher 본체** — 사이클 17 보강 1~5회 즉시 강제재등록 + 사이클 29-R1 6회 초과 force_retry 5분 cooldown + 시간당 12회 cap + 사이클 29-R3 HIGH/LOW 우선순위 분리) + `_resubscribe_stale_priority` (100L, 사이클 25-B 5분 우선 재구독 분리). 합 322L. 누적 9 → **11 함수**. 추가 상수 0 (사이클 60+61 누적 10 상수 모두 이전 완료). **K stale watcher = 영구 hot path 360 회/일 + KIS LMS/앱키 정지 chain 직접 영역** — domain-expert §Q7 본질 차이 인지 별도 자문 (옵션 A 전부 적용). **Q4=B 직접 호출** (사이클 60 A1 답습하지 않는 *유일 영역*): `check_and_resubscribe_stale` 본체가 `_emit_stale_session_detail` 호출 시 `self.*` wrapper 우회 → `emit_stale_session_detail(scheduler,...)` 모듈 함수 직접 호출 (1 hop 단축 + 사이클 61 `_refresh_stale_ccnl_cache` → `evict_expired_ccnl` 패턴 일관). **Q2 try/except 4 중 가드 보존** (`getattr` 폴백 silent 실패 위험으로 비채택). **사이클 29 005935 사고 패턴 차단 영속** (T+0 stale → T+18min 8 분 영구 잔류 + KIS LMS chain) — H 4 케이스 freezegun 재현 PASS. scheduler.py 3,315 → 3,007L (−308L). stale_manager.py 731 → 1,076L (+345L). **누적 scheduler.py 감소** (사이클 51 직전 ~4,185L → 사이클 63 후 3,007L): **−1,178L, −28%**. **회귀 가드 29 케이스 (12 파일)**: A 위임 4 (A-1 HIGH = Q4=B 직접 호출 검증) + C property 호환 3 + D AST 의존성 역전 2 + E reset_daily 동행 2 + F dataclass 누락 2 + **G 1~5회 강제재등록 3 HIGH** + **H 6회 초과 force_retry 4 HIGH (freezegun)** + **I 우선순위 분리 3 HIGH** + J history 60분 윈도우 2 (freezegun) + K cap=10 영역 2 + L caplog logger 1 + M import sanity 1. **HIGH 11 (38%) 전수 PASS**. **백엔드 1915 → 1944 PASS** (+29, 회귀 0). 기존 patch 경로 수정 2 파일 (`test_scheduler_stale_force_retry.py` + `test_scan_loop_stale_priority.py` — A3 이주 후 `src.db.system_logs.write_log` 추가 patch). **사이클 64+ 후속 카드 (tester 발견)**: **카드 #5 (HIGH)** Q5-3 cap=10 결함 영속 (K-2 PASS = 결함 confirm — `_resubscribe_stale_priority` L2748 `targets = stale_tickers[:cap]` priority 분리 *전* 적용 → HIGH 종목 cap 밖 잘림 가능) — 시정 안: priority 분리 *후* HIGH 먼저 + LOW 잔여 cap. **카드 #14 (MEDIUM)** Q5-2 stale_manager.py 1,076L sub-module 분해 (3+1 청사진: `stale_diagnostics` ~350L / `stale_session_recovery` ~250L / `stale_universe_guard` ~150L / `stale_watcher_core` ~322L). **월요일 (2026-06-09) 09:00~10:00 1h tester verify 의무** (시나리오 A 자연 monitoring + B 인위 stale 주입 보유 0 종목만 + C KIS LMS chain 차단 monitoring) — 사이클 60 §Q7 영속 의무.
```

→ CHANGELOG: 사이클 15-A 행 · 사이클 17 행 · 사이클 24 행 · 사이클 28 행 · 사이클 29 행 · 사이클 60 행 · 사이클 61 행 · 사이클 63 행 · 사이클 66 행 · 사이클 67 행 · 사이클 74 행 · 사이클 78 행 · cycle215 행 · cycle216 행 · cycle217 행 · cycle218 행 · cycle240 행 · cycle241 행

### 2026-09-17 이관 — `_sync_positions_from_balance` stale `_selling` 재대조 Defect 2 병리 서술 · `_execute_next_day_clear` Tier 1 NXT 프리 지정가 폐지 경위와 사이클 142 결함 #2(093370 사례)

```
- `_sync_positions_from_balance()`: 15분 주기. strategy 매핑은 trade_history 직전 BUY 행에서 상속. 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제. **stale `_selling` 재대조 (2026-07-23, 자문 `nxt_prelimit_stale_selling_orderflow` 공통 방어선 — hot path 밖)**: `_selling` 각 ticker 가 (보유 잔존[balance qty>0] ∧ 열린 매도주문 없음[`get_daily_orders` 의 `sll_buy_dvsn_cd=="01"` ∧ `rmn_qty>0` 부재] ∧ `_selling_since` 경과 ≥ `SELLING_RECONCILE_MIN_AGE_S`=180s) 이면 `_selling.discard` + `_selling_since.pop` → 다음 on_tick 손절 재평가 재개 (`[selling_reconcile]` WARNING). NXT 지정가 미체결 만료·체결통보 WebSocket 유실 등으로 `_selling` 이 영구 잔존해 `risk.py:128` 게이트가 손절/트레일링을 종일 억제(Defect 2)하던 병리의 공통 시정. 3중 가드로 double-sell 방지: 열린주문 존재(`exchange=ALL` 조회 → NXT 연속세션 잔존 주문까지 포착) 시 유지, 미보유 유지, 180s 미만(전파지연 창) 유지
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 시가 수신 후 30s 안정화 → 갭≥임계 트레일링 / **갭<임계는 `_pending_next_day_clear` 보류(reason=`nxt_underthreshold`) → 09:00 KRX 시장가 청산 (Tier 1, 2026-07-23, 자문 `nxt_prelimit_stale_selling_orderflow` — NXT 프리 지정가 조기청산 폐지)**. *폐지 사유*: 얇은 NXT 프리 유동성에서 open−1tick 지정가는 미체결 만료가 잦고, 만료가 어느 `_selling` discard 경로에도 안 걸려 영구 잔존 → Defect 2(손절 마비). 08:00 지정가를 아예 내지 않으니 leak·double-sell 레이스 원천 소멸. 시가 미수신이면 `_pending_next_day_clear` set 보류. `stock_master.nxt_tradable=False` 가 1순위 판별 → 즉시 보류 등록 (NXT 주문 0건). **사이클 142 결함 #2 시정 **: 트레일링 분기 (`gap_rate >= gap_up_threshold`) 진입 시 `strategy_id == "long_tail_volatility"` 가드로 LTV strategy 후성 동기화 = `_limit_up_reached.add(ticker)` (상한가 모드 영역 진입 보장 → `check_exit_signal` 익일 트레일링 분기 정합 발화) + `pos.high_since_buy = today_open` (트레일링 기준점 = 시가). VB 변경 0 (가드 분기 미진입). *사이클 142 이전 결함*: 트레일링 모드 메시지만 emit + LTV 후성 미동기화 → `check_exit_signal` 당일 모드 진입 → `intraday_stop_loss=-3%` 임계만 작동 → 트레일링 silent 미발화 (후성 093370 운영 사례 = 6/12 매수 17,150원 → 6/15 일중 고점 23,700원(15:55) → 마감 22,300원 = -5.91% 트레일링 임계 -1.2% 발화 미시정)
```

→ CHANGELOG: 사이클 142 행 · cycle273b 행

### 2026-09-17 이관 — `_load_strategy_config` 비중 단위 오염 감지 항목의 도입 시점 표기(2026-08-18)

```
- `_load_strategy_config()`: DB `strategy_config` 에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구. **비중 단위 오염 감지 (2026-08-18)** — 적용 루프 직후·`_config_loaded=True` 직전에 `[weight_config_anomaly] sum=%.4f over_one=%s` WARNING(개별 `weight > 1.0` **또는** Σ `> 1.001`). 집계는 **레지스트리 등록 전략 행만**(`registry.get(sid) is not None` — 은퇴 전략 stale row 영구 오탐 차단), `enabled=False` 행은 **포함**(`enabled` 가 weight 에서 파생되므로 배제하면 오염 행이 통째로 탐지 구멍). **자동 클램프·정규화 절대 금지** — 오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다. 블록 전체 try/except **fail-open**. ⚠️ Σ 임계 `1.001` 은 `routes/strategies.py::_WEIGHT_SUM_TOLERANCE`(1e-3)와 **동치이나 리터럴 중복**이다. `weight=None` 은 감지 블록 *이전* 적용 루프의 `cfg["weight"] * 100` 에서 TypeError → 바깥 except → 기본값 폴백 + `_config_loaded=False` 재시도(기존 계약, 완화 금지). 회귀 `tests/unit/engine/test_weight_config_anomaly.py`(7)
```

→ CHANGELOG: 2026-08-18 비중 단위 계약 행

## log_analysis_engine.py — 일일 로그 분석

### 2026-09-17 이관 — Supabase PostgREST `.range()` 시절 데이터 수집 사양(사이클 53 B-2/B-4 · 53.1)과 08-03 표본 절단 사례 시간대 상세

```
21:30 정산 직후(cycle283 D3, 종전 20:10) `generate_daily_log_report(_now_kst=None)` 호출. 호출 *후* run loop가 `_reset_daily_state()` 별도 실행 (퍼널 카운터 보존). `_now_kst` 파라미터는 테스트용 현재 시각 override — None 이면 `datetime.now(KST)` 사용.

- **`_fetch_logs_in_range(start, end, limit=5000)`**: Supabase PostgREST default 1000 페이지 한도 회피를 위해 `.range(offset, offset+999)` 루프. `limit` 은 *총* 한도 (limit=5000 → 최대 5페이지). 빈 페이지 또는 <1000건 페이지 도달 시 종료. `.limit(N)` 단독은 서버가 1000으로 강제 cap 함 — 반드시 `.range()` 루프 사용.
- **사이클 53.1 — 호출 측 limit=30000 명시**: `generate_daily_log_report` 의 `_fetch_logs_in_range` 호출에 `limit=30000` 명시. 운영 부피 18,000건/일 대비 1.6배 마진 확보. 디폴트 5000 으로는 drained(ASC 7,000+번) 누락 결함 차단.
- **`get_trades_in_range`**: start/end ISO 에 `+09:00` KST timezone 명시 (`src/db/trade_history.py`). TZ 없는 문자열은 PostgREST 가 UTC 해석 → KST 00:00~09:00 거래 누락 결함.
- **표본 절단 감지 (2026-08-04)** — `_fetch_logs_in_range` 는 `ORDER BY timestamp ASC` 라 상한 초과 시 **이른 시각부터 채우고 조용히 끊는다**. 08-03 실측 총 97,353건(상한 30,000 의 3.2배) → 리포트가 **07:45~09:47 두 시간**만 보고 "일일 분석"을 산출했고, 그 뒤(11:20 사이클 I 배포 / 20:10 정산 / 21:03 까지)는 전부 시야 밖이었다. **조용함 + 이른 시각 편향** 두 결함이 겹친 것이며, 평시(~18,000건)엔 안 걸리고 **폭주한 날 = 리포트가 가장 필요한 날**에만 발동한다. 시정 3종:
  - **`_count_logs_by_level(start, end)`** — `GROUP BY log_level` 로 **진짜 총계**를 원문 fetch 와 무관하게 산출 → `logs.level_counts_actual`. 실패 graceful(`{}`).
  - **`_fetch_high_severity_logs(start, end, limit=HIGH_SEVERITY_FETCH_CAP)`** — ERROR/CRITICAL 만 별도 쿼리로 **전량 확보**(상한 무관). `_merge_high_severity(logs, high)` 가 `(timestamp, log_level, message)` 중복 제거 + 시간 오름차순 유지로 병합 — 가장 중요한 신호는 절대 잘리지 않는다.
  - **`_aggregate_logs(logs, fetch_limit=...)`** — `truncated` / `covered_from` / `covered_to` / `fetched_logs` / `coverage_note` 추가. ⚠️ 커버 구간과 절단 판정은 **ERROR/CRITICAL 을 제외한 레벨 기준**으로 계산한다 — 전량 병합된 ERROR 시각이 섞이면 "오후까지 다 봤다"는 **역-오인**이 생긴다. 전량이 ERROR 인 날은 전체 기준 폴백. `fetch_limit` 미전달 시 기존 계약 보존(`truncated=False`).
  - 절단 시 `[log_report_truncated]` WARNING 1행 + `SYSTEM_PROMPT` 가 AI 에게 "총계는 `level_counts_actual` 인용, 분석 구간을 summary 에 명시" 를 지시. 상수 `DAILY_LOG_FETCH_LIMIT=30_000` / `HIGH_SEVERITY_FETCH_CAP=5_000`. 회귀 가드 `tests/unit/engine/test_log_report_truncation.py`(13).
```

→ CHANGELOG: 사이클 53 행 · M5 행 · cycle283 행

## recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

### 2026-09-17 이관 — 증액 Σ 검증 도입 배경(2026-08-18) · `PARAM_RANGES` 제외 경위(사이클 208/209/212/223) · `_CONSERVATIVE_KEYS` 빈 frozenset 화(사이클 210)와 사이클 36 hotfix · SYSTEM_PROMPT 2026-08-07 재작성 부작용

```
- `apply_weight=true` 옵션 → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. `allocate_funds()` 즉시 재호출 금지 (다음 _boot 반영). **증액 한정 Σ 사전 검증 (2026-08-18)** — `new > 현재 weight` 일 때만 `타 전략 weight 합 + new > 1.0 + _WEIGHT_SUM_TOLERANCE`(routes/strategies.py 에서 import, 단일 진실원) 를 검사해 위반 시 `[weight_sum_violation]` WARNING + `success=false` **early return**(params/weight/status 어느 것도 저장 안 됨). **감액은 Σ 상태와 무관하게 항상 통과** — 오염 상태에서 감액이 복구 수단이라 여기에 검사를 걸면 복구 경로가 봉쇄된다. float 변환 실패 시 검사 skip(기존 관용 경로 위임). 도입 배경 = Settings 가 Σ>1 이면 저장을 잠그므로 무가드 증액이 **DB 직접 UPDATE 외 복구 불가** 상태를 만들었다. ⚠️ 이 경로는 메모리 `config.weight` 만 갱신하고 `enabled` 는 안 건드린다(메모리 활성 / DB 비활성 split-brain) — `risk.py` 가 `registry.enabled()` 단일 순회라 메모리도 비활성화하면 그 즉시 손절이 멈추므로 **의도적 미시정**, `enabled` 축 후속 사이클 소관
- `PARAM_RANGES` 화이트리스트 (자동 튜닝 대상): `k_value_krx_main`/`k_value_nxt_pre` `(0.5, 2.0)` (VB, LTV) + `stop_loss_main`/`stop_loss_pre_nxt` `(-15.0, 0.0)` + `long_ma_period` `(20, 120)` + `volume_multiplier` `(1.0, 5.0)` + `min_prdy_rate` + **사이클 23**: VCP 4 키 (`base_depth_pct`/`volume_contraction_ratio`/`breakout_volume_mult`/`last_pullback_max`) + P2 1 키 (`breakout_retention_minutes`) — **사이클 208 (2026-07-13): donchian `box_contraction_period`/`max_box_volatility_pct` 제외** (박스 수축 필터 완전 제거) + **사이클 209 (2026-07-14): donchian `max_breakout_extension_pct` 제외** (AI가 3.0→하한 0.5로 과튜닝 → donchian 후보(전일 이미 돌파) 상시 매수 스킵, DB 0.5→4.0 지혈 동반. 진입 임계=전략 정체성 상수 AI 부적합, 사이클 198/208 선례) + **사이클 212 (2026-07-15): `buy_threshold`(momentum, 29% 급등 진입 정의)·`donchian_period`(donchian, 20일 신고가 정의) 제외** (진입 정체성, AI 튜닝 시 전략 변태. C 동반 = VB `position_ratio` 0.5→0.35 DB 지혈, 손실 변동성 축소) + **사이클 223 (2026-08-21): donchian 청산 2 키 `atr_trail_mult`·`breakout_fail_n_days` 제외** (진입이 아닌 **청산 정체성 상수**. 19 왕복 실측 MFE 대비 −12%·RR 0.47 → 트레일링 배수는 재튜닝 대상이지 매일 밤 흔들 값이 아니다. `atr_trail_mult` 는 donchian·BFB·VCP **3 전략 공유**인데 근거 표본은 donchian 뿐 → VCP/BFB 청산 왕복 ≥20 시 재검토. 수동 적용 라우트도 동일 정본 참조로 차단)

- **사이클 23 P3-1+2 `auto_apply_recommendations(target_date)` (신규 함수)**: 20:00 AI 자문 직후 자동 적용. 감액만 + 50% cap. **사이클 210 (2026-07-14) — `_CONSERVATIVE_KEYS` 빈 frozenset 화 (param ratchet 차단)**: 손절/일일한도/비중 7키(stop_loss_rate/position_ratio/daily_loss_limit/intraday_stop_loss/overnight_stop_loss/stop_loss_main/stop_loss_pre_nxt)를 자동적용 대상서 전량 제거 → **auto_apply 는 weight 감액만 잔존**. 사유: `float(v)>current` 게이트가 조이는 방향만 통과 + 완화 경로 부재 = 단조 조임(monotone ratchet) → 전략 교살(donchian daily_loss -6→-0.8 방치가 산물). 진입/청산 임계는 전략 정체성 상수 = 사람이 판단(208/209 선례). `_STOP_LOSS_KEYS` + 게이트 로직은 도달 불가로 잔존(무해). (구 서술: 보수적 파라미터 `_CONSERVATIVE_KEYS` 자동 적용.) `auto_apply_enabled=False` 시 즉시 disabled 반환. `[auto_weight_apply]`/`[auto_params_apply]`/`[auto_apply_skip_increase]`/`[auto_apply_safeguard_skip]` 4종 영구 로그. `status='applied_auto'` (수동 'applied' 와 분리). scheduler `TIME_RECOMMENDATION` 직후 호출. **사이클 36 hotfix (2026-05-21)**: scheduler.py:542 호출부에 `from src.engine.scanner import KST_TZ as _AUTO_APPLY_KST_TZ` import + `datetime.now(_AUTO_APPLY_KST_TZ).date()` 사용 (이전엔 `KST` 미정의 NameError 로 매일 20:00 자동 적용 실패). `backtest_engine.poll() / wait_for_result()` 의 `pending` status 도 `running` 동일 처리 (이전엔 unknown 분기 → ExternalAPIError → `backtest_runs status=failed` 잘못 기록)

- SYSTEM_PROMPT 끝에 매크로 컨텍스트 활용 가이드 — defensive/neutral/aggressive 분기 + **레짐은 매매 미개입(관찰 전용)·`buy_blocked` 는 항상 false 이므로 매수 임계 튜닝은 유효하고 스킵 금지, `block_reason` 은 보수적 권고 참고 신호** (2026-08-07 재작성 — 종전 "buy_blocked=True 면 매수 튜닝 무용" 문구가 매일 20:00 자문에서 매수 파라미터 권고를 통째로 스킵시켰다) + `weight_reasoning`/`code_review_notes` 에 매크로 영향 명시 권장
```

→ CHANGELOG: 사이클 23 행 · 사이클 36 행 · 사이클 208/209/212 행 · 사이클 223 행

## 절대 깨지면 안 되는 규칙

### 2026-09-17 이관 — 사이클 55 R-1 갱신 사슬 표기 · `_confirm_breakout_open_prices` 15:30 `post_nxt` 오기 · buy poll 레짐 게이트 취소선 서술

```
- NXT 프리/애프터 매도 거부 (`is_market_closed_rejection`) 시 `execute_sell` 이 `state.positions`·DB 보존 + `_selling` discard (진입 게이트 `is_blocked()` 위임 — stale `_selling` 좀비 방지) + **`target_exchange ∈ ("NXT","SOR")` ∧ KST 08:00~08:50 일 때만** `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강(cycle286 C4-a — KRX 로 보낸 주문의 거부에는 절대 쓰지 않는다. 09-14 부터 KRX 애프터마켓이 구 `15:30~20:00` 창 안에 들어와 그 창의 거부는 어느 시장 것인지 시계로 가릴 수 없다). **사이클 B-1 진입 차단 → 사이클 55 R-1 2단계 TTL**: `SellRejectionTracker.is_blocked()` 진입 게이트. KRX 메인(09:00~15:30) 거부 = 5분 TTL, NXT 시간대 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` = 30초 TTL, NXT 폴백 실패 = 익일 청산 큐 등록. `_reset_daily_state` 동행 `_sell_rejection.reset_daily()` 위임 필수. 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 유지

- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:30 `post_nxt`. SessionTracker race 차단

- `_swing_rest_poll_loop` / `_swing_buy_poll_loop` 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 보유 손절 평가 보강 + 09:05~09:30 매수 평가. **공유 순차 대상 `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")`** (2026-07 — 순차 처리로 동일 종목 double-buy race 차단, 전용 task 신설 금지). ⚠️ ~~buy poll 은 `execute_buy` 직전 레짐 매수가드(HARD skip / SOFT soft_multiplier) 복제~~ → **사이클 I(2026-08-03)로 레짐 매수 게이트 전면 제거됨 — buy poll 은 레짐 미소비(관찰 전용).** 이 게이트를 복원하지 마라(유령 게이트, 603행 참조). **`_SWING_POLL_STRATEGIES` 는 매수 평가 소스(poll)를 정하고, `risk.py:_TICK_BUY_EVAL_SKIP_STRATEGIES`(cycle273e, 2026-09-11)는 WS 틱(`on_tick`) 경로에서 같은 두 전략의 매수 평가를 skip 시켜 그 소스를 배타적으로 만든다 — 두 상수의 멤버는 항상 같이 움직인다(한쪽에만 전략을 추가하면 그 전략이 틱·폴 이중 평가되거나 아예 평가되지 않는다). skip 은 `check_exit_signal`·보드 가드·중복 가드·자금 가드 **뒤**, `check_buy_signal` **바로 앞**에서만 발생 — 청산·트레일링·익일청산은 on_tick 에서 두 전략 모두 여전히 정상 평가된다. 킬스위치 없음(1행 revert 로만 롤백)**
```

→ CHANGELOG: 사이클 55 행 · 사이클 I 행 · cycle273e 행

### 2026-09-17 cycle298 이관 — `TIME_BOOT` · `TIME_POST_NXT_OPEN` 이 런타임 미사용이라는 실측

팀장이 `grep -rn "TIME_BOOT\|TIME_POST_NXT_OPEN" src/` 로 전수 확인한 결과, 두 상수 모두
**런타임 참조가 0건**이었다. `_boot()` 는 `scheduler.start()` 안에서 즉시 불리고(`scheduler.py:600`),
POST_NXT 전환과 `_confirm_breakout_open_prices(board="post_nxt")` 는 `TIME_KRX_MAIN_CLOSE`(15:30)
대기 직후에 일어난다(`scheduler.py:865-874`). 아래가 그 전까지 정본에 있던 원문이다.

```
| `TIME_BOOT` | 07:55 | `_boot()` — 본체는 `src/engine/boot_manager.py::boot(scheduler)` 위임(2줄 wrapper). `_preissue_all_tokens()`(메인+보조 N 매니저를 분당 1개 한도로 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()`(보유 + 익일청산 후보 ticker 를 `stock_master` eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → **`portfolio_risk.check_budget_invariant`**(`position_ratio × max_positions > 1.0` 위반 시 `[budget_invariant_violation]` WARNING, **차단 아닌 관찰**) → `allocate_funds(net_asset × ratio)` |

| `TIME_POST_NXT_OPEN` | 15:40 | NXT 애프터 진입. `_confirm_breakout_open_prices(board="post_nxt")` |

- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:40 `post_nxt`(`TIME_POST_NXT_OPEN` 뒤). SessionTracker 30초 race 차단
```

상수는 지우지 않았다 — 테스트 6파일이 두 상수를 참조하고, 그중
`tests/unit/engine/scheduler/test_post_nxt_open_time.py::test_time_post_nxt_open_is_15_40` 와
`tests/unit/engine/test_cycle92_time_boot_moved.py` 는 값 자체를 핀한다. 상수 정리는 별도 카드다.

`session._BOARD_SCHEDULE` 의 보드 경계(`main` ~15:39:59 · `post_nxt` 15:40~20:00)는 **별개 축이고
여전히 사실**이라 손대지 않았다. 고친 것은 "스케줄러가 15:40 에 무엇을 한다" 는 서술뿐이다.

→ CHANGELOG: cycle298 행

## VCP universe backfill 분기

### 2026-09-17 cycle299 — target 120 → 220 (200일 EMA 가 요구하는 깊이)

경위는 `src-db-CLAUDE.history.md` 의 같은 날짜 항목이 정본이다(두 상수가 한 사이클에서 함께 움직였다).
여기엔 정본에서 걷어낸 원문만 둔다.

알려진 편차. 달력 환산 `int(n*7/5)+10`(영업일당 1.40 가정)이 실측 1.494 와 벌어져,
`total_days=220` 1회 backfill 의 실제 도달이 약 212 영업일로 target 에 8영업일 모자란다.
영구 churn 이 아니다 — 윈도우가 하루씩 미끄러지며 `existing_count` 가 자라 약 8밤 뒤 수렴한다.
그동안 VCP 유니버스 전량이 3윈도우 backfill 을 돈다. 수식 정정은 이 사이클 밖이다.

원문(`src/engine/CLAUDE.md:155-159`, 2026-09-17 이관):

---

- VCP ∧ `existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=120)` → `condition.fetch_daily_candles_backfill(ticker, total_days=120)`(분할 fetch, 마지막 윈도우 클램프). VCP ∧ `>=120` → 증분 7일(재 backfill 금지). 비 VCP 는 `<50` 백필 100일 / `>=50` 증분 7일.
- 🔴 120 인 이유 = retention `DAILY_RETENTION_DAYS=230`cal ≈ 154영업일 아래의 마진이다. 그보다 크면 `existing_count` 가 영원히 target 에 못 닿아 매 load 전량 재backfill(churn)이 된다. VCP `prepare` 실사용은 100일이다.
- ⚠️ VCP EMA 220일 원설계를 복원하려면 retention(~320cal)과 target 을 함께 올려야 한다.

---

마지막 ⚠️ 는 이번 사이클이 실현했으므로 정본에서 사라졌다. 대신 **아직 남은 cap 두 겹**
(`get_recent_daily` 의 `min(days,100)` · `vcp_breakout.py` 의 `KIS_DAILY_CANDLES_MAX = 100`)을
정본에 새로 적었다 — 데이터 계층만 열렸고 전략은 아직 100일을 넘어 읽지 못한다.

→ CHANGELOG: cycle299 행

### cycle299 (2026-09-18) — 목표를 220 → 225, 보존을 380 → 390 으로 다시 올린 경위

사이클 안에서 값이 한 번 더 움직였다. 앞 항목에 380/220 으로 적힌 서술은 그 시점의 기록이고,
확정값은 **retention 390 달력일 · VCP backfill target 225 영업일** 이다.

- **왜 225 인가** — VCP 추세 필터의 `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)`
  에 운영 DB 값(`ema_short=50` / `ema_mid=150` / `ema_long=200`)을 넣고 보유 영업일을 움직이면,
  보유 220 에서는 실효 장기선이 **195** 에 그치고 **225 에서 정확히 200** 이 된다. 미네르비니 원전의
  200EMA 를 형식이 아니라 값으로 성립시키는 최소 깊이가 225 다. 같은 계산에서 mid↔long 간격도
  220 의 45 에서 225 의 50 으로 벌어진다(보유 100 이면 간격 10 = 사실상 동전던지기였다).
- **왜 retention 도 함께 올렸나** — 가드 `G-299-3c`(`retained_trading(retention) >= target + 30`)
  때문이다. 환산 앵커 230cal ⇄ 154영업일로 `retained(380) = 254` 인데 `225 + 30 = 255` 라 **1 모자라
  FAIL** 한다. 3c 를 만족하는 retention 최소값은 **381** 이고, 여유를 두어 390 을 택했다
  (`retained(390) = 261` → 마진 **36 영업일**, 사이클196 의 34 보다 크다).
- **실측(가드 헬퍼 `_capture_backfill_reach_cal` 로 확인)** — `total_days=225` 의 윈도우는 3개
  (100/100/25), 최고 도달 **325 달력일** < retention 390(여유 65cal). 1회 backfill 실도달은
  `trading_days_in(325) = 217` 영업일이라 target 에 **8 영업일** 모자라고, 이 부족분은 220 일 때와
  같다(둘 다 8). 전이 기간과 비용 추정은 앞 항목과 동일하다.
- **재핀** — `scanner.py` 가 다시 바뀌어 8영역 sha 핀 13곳(`_PIN_GUARD_FILES` 4 + 기준선 9)과
  `test_cycle287::_SRC_TREE_DIGEST` 를 같은 값으로 한 번 더 옮겼다. 단언은 약화되지 않았다.

### cycle299 (2026-09-18, 이어서) — 달력 환산을 고쳐 1회 backfill 이 목표를 넘게 했다

사용자 요청("데이터 지금 바로 채울 수는 없어?")으로, 별건으로 미뤄 두었던 환산식을 이 사이클에서 고쳤다.

- **고친 것** — `fetch_daily_candles_backfill` 의 **깊이**(마지막 윈도우 시작점) 환산에만 휴일 보정을
  비례로 얹었다: `int(n*7/5) + int(n*0.10) + 10`. 상수 3개를 이름으로 뽑고 근거를 주석에 남겼다
  (`_WEEKEND_CAL_PER_TRADING_DAY` / `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO` / `_DAILY_BACKFILL_BASE_MARGIN_CAL`).
- **왜 계수를 통째로 올리지 않았나** — `3/2`(=1.50) 제안은 **stride 까지 함께 키운다**. KIS 가 한 호출에
  100건까지만 주므로 앞 윈도우는 공휴일이 하나도 없는 구간에서 정확히 100영업일 = **140 달력일**까지만
  덮는다. stride 가 140 을 넘는 순간 다음 윈도우의 머리가 그 바닥보다 아래로 내려가 **사이 구간이 통째로
  비고**, 빈 날짜는 어느 윈도우도 다시 집지 않는다(`3/2` 면 stride 150 > 140). 그래서 stride 는 7/5 로
  두고 깊이에만 보정을 얹는 형태를 택했다. 구멍 검사는 공휴일 0 이라는 최악 가정으로 확인했다.
- **실측** — `total_days=225` → 윈도우 3개 `[(0,160), (140,310), (280,347)]`, 최고 도달 **347 달력일**.
  실측 비율(앵커 230cal ⇄ 154영업일 = 1.479)로 **232 영업일**이라 목표 225 를 **7 넘는다**. 공휴일이
  없는 해(1.40)에는 247, 밀집한 해(1.52)에도 228 로 어느 쪽도 목표 위다. 전이 기간이 사라졌다.
- **가드** — `retention 390` 기준 3a(347 < 390, 여유 43) · 3b(347+30 = 377 ≤ 390) · 3c(261 ≥ 255) 전부
  통과라 retention 은 옮기지 않았다. `G-299-9` 는 "부족분 ≤ 10"(음수에서 공허해진다)에서
  **"실도달 ≥ target"** 으로 부등식을 뒤집어 강화했다.
- **`scanner.py` 무접촉** — 변경을 `condition.py` 에 가둬 8영역 sha 핀 13곳을 다시 옮기지 않았다.
  움직인 것은 `test_cycle287::_SRC_TREE_DIGEST` 하나다.
- **호출자** — `fetch_daily_candles_backfill` 의 프로덕션 호출자는 `scanner._stock_master_daily_load_once`
  **하나뿐**임을 `grep` 으로 재확인했다. 별도 함수 `fetch_daily_candles` 는 무접촉이다.

## 분할 backfill 분기 — 대상 확대 (cycle302, 2026-09-18)

정본이 이 사이클 전까지 적던 문장 둘을 덮어썼다.

- 「유니버스 선정」의 `🔴 vcp_universe_tickers 에는 넣지 않는다(분할 backfill 은 index 전용이고
  보호 목적은 "오늘 봉 결손 방지" 로 국한한다)`(cycle273 D5, C1)
- 「VCP universe backfill 분기」 절 머리 두 줄 — `vcp_universe_tickers: set[str]` = `is_kospi200 OR
  is_kosdaq150` 정의와 `VCP ∧ <225 → backfill / 비 VCP 는 <50 백필 100일 / >=50 증분 7일` 분기표

### 왜 뒤집었나 — 2026-09-18 09:37 실측

| 집합 | 종목 | 225행 이상 | 평균 행수 |
|---|---|---|---|
| 지수(KOSPI200 ∪ KOSDAQ150) | 348 | 348 (100%) | 232 |
| 비지수 | 1,526 | **0** | 125 |

cycle299 가 target 을 225 로, cycle300 이 읽기 클램프를 400 으로 열었는데 **대상이 지수뿐**이라
비지수는 한 종목도 깊이를 못 받았다. VCP 는 628 종목을 평가하므로 그중 약 280(45%)이
`effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)` = **74·114·121** 로 잡혀
중기↔장기 간격이 10 안팎이 됐다. 그날 5단계 탈락 사유 로그에 `50EMA / 150EMA / 121EMA` 가
그대로 찍혔다 — 정배열 판정이 동전던지기인 상태가 그 종목들에 남아 있었다.

### 무엇을 바꿨나 — 조건식 한 줄

```
- is_vcp_universe = ticker in vcp_universe_tickers
- use_vcp_backfill = (is_vcp_universe and existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS)
+ use_deep_backfill = existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS
```

`vcp_universe_tickers` 집합(선언·`add`)과 `is_vcp_universe` 지역변수는 이 분기가 **유일 소비처**라
(`grep` 전수) 함께 지웠다. 예외 로그의 `vcp=%s` 필드는 값의 뜻이 바뀌었으므로 `deep=%s` 로 고쳤다
(소비처 0 — 테스트·운영 grep 어디에도 없었다).

### 비용 — 1회성이라는 것이 이 설계의 안전 근거다

| | KIS 호출 | 소요 | 20:30 적재 종료 |
|---|---|---|---|
| 첫 채움(1회) | ≈2,886 | ≈345초 | ≈20:36 |
| 정상 운영(매일) | 962 | ≈120초 | 20:32 |

`existing_count >= 225` 가 되면 증분(7일·1콜)으로 내려오고 retention 390 달력일(≈261 영업일)이
225 아래로 떨어뜨리지 않는다. 그 사실을 `test_g302_3_converged_universe_costs_one_call_per_ticker`
가 봉인한다(전 종목 수렴 → backfill 0건 · `fetch_days` 전량 7).

첫 채움을 20:30 스케줄이 떠안으면 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식
창(20:35~)을 **1분 침범**한다. 그래서 첫 채움은 배포 후 21:35 이후에 수동 trigger
(`POST /api/stock-master/daily/refresh?force=1`)로 한 번만 돌린다 — 코드에 특별 분기를 두지 않았다.

### 판단 2건

1. **`vcp_universe_tickers` 는 지웠다.** 남기면 write-only 집합이 되어 소스가 "지수만 깊이를
   받는다" 는 거짓을 계속 말한다. 프로덕션 파일에서는 오히려 **줄어드는** diff 다.
2. **상수 이름 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 는 유지했다.** 정정하려면 `src/api/condition.py`
   의 호출자 주석이 딸려 움직여 "프로덕션 변경은 `scanner.py` 한 파일" 제약을 깬다. 대신 정의
   자리에 "이 상수는 VCP 전용이 아니다 — 적재 대상 전부의 목표 깊이다" 를 못 박았다.

### 알려진 귀결 둘 (숨기지 않는다)

- `existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD(50) → 100일 단발` 분기는 225 > 50 인 한
  **도달 불가**다. 신규 상장도 첫 밤에 225일 분할 backfill 을 탄다. 그 사실을 계약으로 드러낸
  핀이 `test_g302_8b_deep_target_dominates_incremental_threshold` 다 — 다음 사람이 "100일 분기가
  신규상장을 처리한다" 고 읽고 그 위에 무언가를 얹는 것을 막는다.
- **상장 이력이 225 영업일보다 짧은 종목은 수렴하지 않는다.** 매일 밤 3콜을 쓰고 목표에 못 닿는다
  (최근 상장 코호트 한정, 종목당 하루 2콜 초과분). 자본 위험 0 이고 관측 채널은
  `[stock_master_daily_load_summary] elapsed_ms` 다. 구조적 시정(시도 마커 등)은 하지 않았다.

### 의미 전환한 기존 가드 (값만 덮지 않았다)

- `test_cycle172_vcp_universe_backfill.py` SCAN-3/3b(비지수 → 100일) · SCAN-5(두 종목 모두
  backfill 로 변해 공허해질 뻔한 graceful 시나리오에 수렴 종목을 붙였다)
- `test_cycle196_vcp_backfill_convergence.py` B-5a/B-5b("非VCP 불변")
- `test_cycle206_daily_load_universe.py` UNIVERSE-5("vcp_universe = index 만")
- `test_cycle273_daily_load_protected.py` C1("보호 종목은 backfill 밖") · G-273D-4(소스 봉인) +
  적재 대상 집합을 재는 보조 단언 3건을 **분기 무관 종목 수**(`backfill + fetch`)로 바꿨다
- `test_cycle263_daily_load_stub_filter.py` — 대역 기본 깊이를 수렴 상태로 올리고
  `fetch_daily_candles_backfill` 격리 패치를 심었다. 종전에는 분기가 새면 **실 KIS 로 나가**
  스위트가 157초 걸렸다(네트워크 hang). 이제 단언이 터진다.

## 2026-09-21 (cycle331) — B-2 ERROR 문구 정정

`[buy_fill_fallback_held_conflict]` 의 종전 문구는 `"이미 타 전략 보유 중"` 이었다.
**실측상 거짓이다** — 운영 DB 의 2건(078930 08-26 14:44 · 161890 08-31 08:13)은 둘 다
*타 전략*이 아니라 **자기 전략**(LTV)이었고 *보유*가 아니라 **주문 중**이었다.
`is_ticker_held_by_any` 가 `_strategies.values()` 전수를 보고 `has_position OR
is_buy_pending` 이기 때문이다.

운영자가 그 ERROR 를 읽고 "다른 전략이 들고 있어서 중복을 막았구나" 로 이해하면
정확히 반대다. `"타 전략 보유/주문중"` 으로 고쳤다.

⚠️ 21:30 리포트의 `_normalize_message` 가 메시지 전문을 패턴 키로 쓰므로
**2026-09-21 전후의 `top_patterns` 문자열을 비교하지 않는다**(cycle328 폴백 문구 통일과 같은 주의).

## 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

### 2026-09-25 cycle350 — stagger 값 서술 교체 (cycle159 상향이 반영되지 않았던 서술)

정본 원문. 코드는 cycle159(`3a237fd`)부터 0/240/480/720초였다:

task 별 stagger `initial_delay_secs`(full_universe=0 / basics=60 / daily=120 / master=180 / financial=900초).

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

### 2026-09-25 cycle350 — `TIME_SESSION_START_CUTOFF` 행의 일봉 immediate stagger 서술 교체

정본 원문(행 일부). 일봉 task 의 `initial_delay_secs` 는 240초다:

`start()` 직후 stagger 120초)이 7일 증분으로 보정하지만 `_boot()` 의 prepare 보다 늦다 — `[daily_head_stale]` 관측이 그것을 알린다)

→ CHANGELOG: cycle350 행

## 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

### 2026-09-25 cycle363 — 부팅 즉시 실행 게이트를 두 갈래(시간 / 영업일 슬롯)로 나눴다

정본 원문(시그니처 + 게이트 서술 4줄):

```
run_periodic_task_loop(*, scheduler, task_label, wait_time, once_callable, record_fn, flush_fn,
                       summary_log_format, summary_keys, immediate_first_run=True,
                       retry_delay_secs=60, initial_delay_secs=0,
                       immediate_skip_if_fresh_hours=None)
```

- **신선도 게이트**: `immediate_skip_if_fresh_hours` 를 주면 immediate 블록(stagger sleep 뒤 · once 앞)에서 `system_config.get_task_last_success(task_label)` 마커가 `0 <= elapsed < hours*3600`(미래 마커 음수 방어)일 때 immediate `once()` 를 skip 하고 `[<label>] immediate run skip — fresh` INFO 1행을 남긴다. 마커는 `once()` **성공 직후에만** 기록한다(기록 실패 → 다음 부팅 immediate 실행 = 안전 방향).
- 모듈 상수 `IMMEDIATE_FRESH_SKIP_HOURS = 20.0`(저녁 성공 → 익일 아침 boot 이 그 안, 저녁 장애 시에는 넘어서 catch-up 실행).
- 게이트 대상 = basics / master / daily_load / financial. 🔴 daily_load 를 넣는 이유 = 아침 immediate 가 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)을 먼저 써서 `max_bas_dd == today` 를 만들면 그날 정기 실행이 전 종목을 `skipped_fresh` 로 건너뛴다. 미대상 = full_universe / purge / evening_funnel(full_universe 는 `stock_master.is_stale()` 24h TTL 로 이미 멱등이라 같은 영업일 2회 실행이 무해하다).
- 가드 `test_cycle193_immediate_fresh_gate.py` · `test_cycle193_task_marker_helpers.py` · `test_cycle193_ast_fresh_gate.py` · `test_cycle263_daily_load_stub_filter.py`.

경위 (사용자 결정 2026-09-25 D4 카드1 (가) · 카드2 (나) + 「①′ 도 같이」):

- **20h 시계가 주말·연휴를 「낡았다」로 셌다.** 금요일 저녁 마커 → 월 07:5x 부팅은 20h 를 훌쩍 넘어
  (cycle263 A5 의 합성 = 주말 63.9h) basics·일봉 보충 적재가 월요일마다 돌았다. 영업일 슬롯 게이트는 「마커가 직전 영업일 정기 슬롯 뒤인가」
  로 판정하므로 평상시 월요일·연휴 뒤 아침에는 돌지 않는다. master(16:30)·financial(16:40)은 범위 밖이라
  시간 게이트에 남겼다.
- **`test_cycle193_ast_fresh_gate.py::F-10-2` 개정 — full_universe 가 무게이트 목록을 떠났다.**
  위 원문의 제외 근거 「TTL 멱등이라 즉시 실행이 저렴」은 실측과 달랐다. EC2 파일 로그 10거래일에서
  20:00:0x 정기 full_universe 는 10일 모두 `fetched=0`(TTL skip)이었고, 아침 즉시 실행이 일을 한 날은
  두 월요일(09-14 `fetched=2,674` · 09-21 `fetched=2,670`)뿐이었다. 그 일은 **전량 덮어쓰기**였다.
  평일 아침에는 16:10 basics 가 전 종목 `refreshed_at` 을 매일 갱신해 24h TTL 이 전부 skip 했다.
- **덮어쓴 값은 목요일 KRX 값이었다.** KRX `basDd` 는 `today − 1일` 부터 거꾸로 찾는데, 아침
  07:45~07:53 로그 10일 전부에 `[krx_empty_response] basDd=<직전 영업일>` 이 찍혔다 — 직전 영업일 KRX
  자료는 다음 영업일 07:53 까지 비어 있다. 09-21 07:52:52 `basDd=20260918 빈 응답` → **09-17(목) 자료를
  적재**했다(DB 대조: `raw.TDD_CLSPRC` 가 09-17 종가와 같은 종목 965개, 09-18 종가와 같은 종목 27개).
  09-14 07:45:52 `basDd=20260911 빈 응답` → 09-10(목) 적재. 이 값이 덮은 것은 금요일 16:10 basics 가 쓴
  금요일 KIS 값이다. 정의 차이는 작다(09-23 KIS 16:1x 스냅샷 대 그날 일봉 거래대금 중앙값 비율 0.98,
  10억 경계 뒤집힘 970 중 2) — **문제는 정의가 아니라 날짜였다.**
- 자가 치유(populator)는 행 수 하한 `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS=2000` 으로 보존했다(운영 3,583행 ·
  2026-08-08 degrade 사고 60행). full_universe 는 이 게이트 전에 마커를 남긴 적이 없어(`market_ops` 가
  「영구 결측」으로 다뤘다) 09-28(월, 추석 연휴 뒤 첫 영업일) 07:45 에 마커가 없다. 「마커 없음 = 실행」
  이면 09-28 에 09-22 KRX 값 덮어쓰기가 그대로 일어나 카드2 (나)를 고른 이유가 사라지므로, full_universe
  만 「마커 없음 + 행 수 ≥ 하한 → skip」으로 정했다(team-leader 설계 결정). 첫 마커는 09-28 20:00:05
  정기 실행이 남긴다.
- **`test_cycle263_daily_load_stub_filter.py` A5 를 의도적으로 뒤집었다.**
  `test_A5_marker_63h9_weekend_runs_immediate`(「주말 63.9h → 월요일 실행 = 주 1회 무결성 재fetch」) →
  `test_A5_weekend_friday_marker_skips_monday_immediate`(「금요일 20:30 뒤 마커 → 월요일 SKIP」).
  월요일 재fetch 가 없어져도 월요일 20:30 정기 실행의 7일 증분 창이 같은 구간을 다시 덮는다(G2 의
  「보정 창 존치」 단언이 그 창을 잠근다). 금요일 「마커를 남기고 부분 실패」는 평일과 같은 위험 등급이다
  (cycle360 메모 §7). A1·A3~A8·G2 는 「N시간 전 마커」 합성을 고정 시각(`task_loop_helper._now_kst`) +
  고정 달력(`trading_calendar._lookup_open`) 위의 날짜 마커로 바꿨다.
- 함께 움직인 가드 값 둘 — `test_cycle134_task_loop_helper.py::G-134-F2` 헬퍼 라인 상한 200L → 320L
  (실측 304L, 슬롯 게이트 +100L) · `test_cycle348_kojiro_macd_stage6.py::test_g348_b10` kojiro `prepare`
  의 `await` 수 7 → 8(`_resolve_expected_daily_head` 1건 — 관측 확장이 아니라 별도 승인 사이클의 신규 await).
- 근거 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.1·§1.2·§1.5·§6 · 지시서
  `_workspace/red/cycle363_business_day_freshness_spec.md`.

→ CHANGELOG: cycle363 행

## funnel 스냅샷 캡처

### 2026-09-25 cycle363 — 「재준비 = 월요일 보충 적재를 반영하는 유일한 경로」 서술 정정

정본 원문:

- **저녁 task 는 아침에도 한 번 돈다** — `run_periodic_task_loop` 의 즉시 1회(`immediate_first_run` 기본값, 신선도 게이트 `immediate_skip_if_fresh_hours` 미전달)가 `start()` +600초에 실행된다(07:45 기동이면 ≈07:57). `run_daily` 가 매 거래일 `start()` 를 다시 부르므로 재시작이 없어도 매일 돈다. 그때도 등록 전략 전부의 `prepare()` 를 다시 부르고 오늘 날짜로 잠정(`is_provisional=True`) 행을 쓴다. 이 재준비는 살아 있는 전략 객체의 후보를 교체하므로 그 뒤 매수 평가는 이 결과를 쓴다. 부팅 준비(`_boot()` 안의 전 전략 `prepare()`)는 `start()` 가 적재 태스크(`_full_universe_load_task` +0초 · `_stock_master_daily_load_task` +240초 · `_stock_master_basics_refresh_task` +480초)를 만들기 **전에** 끝난다. 그래서 월요일·연휴 뒤 아침 보충 적재(full_universe TTL 재적재 · 일봉 · basics)가 바꾼 입력을 라이브 후보에 반영하는 경로는 이 재준비 **하나뿐**이다. 🔴 **이 즉시 1회에 신선도 게이트를 걸지 않는다** — 평일 8일은 같은 결과였지만 2026-09-14·09-21(월)에는 그날 실매매 후보를 바꿨다(근거 = `_workspace/red/cycle350_evening_funnel_spec.md` §1). 이 교정은 순서 보장이 아니라 경합에 기댄다 — 재준비는 `count_all() > 0` 만 기다리고 +240초 일봉 보충 적재의 **완료**는 기다리지 않는다.

경위:

- cycle350 명세 §1·§3 은 +600초 재준비를 「월요일 보충 적재를 라이브 후보에 반영하는 유일한 교정 경로
  (게이트 금지 사유)」로 적었다. cycle360 자문 실측상 그 경로가 반영한 것은 **더 오래된(목요일) KRX 값**
  이었다 — 교정이 아니라 교체였다. 09-21 재준비의 변화(VB 81→63, VCP 7/729→5/640)는 「금요일 값 →
  목요일 값」 교체다. 월요일 08:00 basics 가 뒤따라 돌았지만 장전이라 거래대금이 0 이고,
  `_ZERO_VALUE_SKIP_KEYS`(`acml_tr_pbmn` 포함) 때문에 목요일 KRX 거래대금이 월요일 16:10 까지 남았다.
- 금 19:46 재기동 부팅 준비와 월 07:51 부팅 준비는 6전략 유니버스 분모가 모두 같았다(주말 동안
  `stock_master` 불변). 평일 부팅 준비와 +600초 재준비는 8일 중 7일 6전략 숫자까지 같았다(cycle360 §1.3).
- cycle363 의 영업일 슬롯 게이트 뒤로는 평상시 월요일에 보충 적재가 돌지 않아 재준비가 부팅 준비와 같은
  입력을 읽는다. 재준비 자체(+600초 즉시 1회)는 그대로 두고 게이트도 걸지 않는다 — 게이트(4a ②③)는
  donchian 보유 트레일링 ATR 출처를 바꾸므로 카드3 결정 뒤(단계 3)다. 게이트 금지의 근거 문장을 그
  이유로 바꿨다.
- **F-1(미시정, 결정 대기)** — `scanner._scan_pool_eager_refresh_loop`(`scanner.py:2051-2063`)는
  basics 경로(`scanner.py:3475`, cycle176)와 달리 기존 raw 를 머지하지 않고 `upsert_one` 이 raw 를 통째로
  바꾼다. 월요일·연휴 뒤 아침엔 `stock_master` 행이 24h 를 넘겨 이 경로가 풀 종목(추정 120~150)을 장전에
  KIS 로 갱신하고, 장전 0 값 키가 사라져 `acml_tr_pbmn_won` 이 NULL 이 된다. 그러면 그날 16:10 basics 가
  복원할 때까지 그 종목이 `list_by_filter`(거래대금 임계)에서 빠진다. 월요일 아침 KRX 적재·basics 가 행을
  fresh 로 만들던 동안에는 잠들어 있던 경로이고, 슬롯 게이트가 그 두 적재를 월요일 아침에서 걷어 내면서
  드러났다(cycle363 심층 검증). 시정은 `scanner.py`(8영역) = 사용자 승인 대상이다.

→ CHANGELOG: cycle363 행

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

### 2026-09-25 cycle363 — `TIME_SESSION_START_CUTOFF` 행의 보정 경로 서술 교체

정본 원문(행 일부):

⚠️ 그 창의 재기동은 **그날 20:30 일봉 적재를 통째로 잃는다**(다음 영업일 일봉 task 의 immediate 실행(`run_periodic_task_loop` 의 `immediate_first_run`, `start()` 직후 stagger 240초)이 7일 증분으로 보정하지만 `_boot()` 의 prepare 보다 늦다 — `[daily_head_stale]` 관측이 그것을 알린다. 보정된 일봉을 라이브 후보에 반영하는 경로는 +600초 재준비 하나이고, 그 재준비는 적재 완료를 기다리지 않는다 — 「funnel 스냅샷 캡처」 절)

경위: cycle363 ①′ 이후 6전략 prepare 는 헤드가 `expected_head`(직전 영업일)보다 오래된 종목을 KIS 로
폴백해 읽으므로, 저녁 적재가 결손된 다음 날에도 부팅 준비가 보정된 봉을 본다(휴장일 조회가 실패한 날만
하루 밀린 DB 헤드). 「재준비 하나」가 더는 참이 아니라 교체했다.

→ CHANGELOG: cycle363 행

## 일봉 적재 본체

### 2026-09-25 cycle363 — 어댑터 호출부 서술 교체

정본 원문:

- 어댑터 `get_recent_daily_normalized`(`src/db/stock_master_daily.py`)는 `strategy_base` · 전략 6파일 · `llm_buy_gate` 가 쓴다.

`strategy_base` 는 어댑터를 부르지 않는다(docstring 언급뿐). 호출부는 전략 6파일 `prepare()` · kojiro
`recompute_held_atr` · `llm_buy_gate` 이고, cycle363 부터 `prepare()` 만 `expected_head` 를 넘긴다.

→ CHANGELOG: cycle363 행

## 정기 task 루프 / funnel 스냅샷 캡처 / trading_calendar.py

### 2026-09-25 cycle363(배포 전 보강) — 독립 검증 confirmed 반영

경위: cycle363 배포 전 독립 검증(적대적, 26 에이전트 — suite·09-28 시뮬레이션·전략별 영향·
비활성화 심층검증 4렌즈)이 confirmed 8건을 냈다. 그중 4건(F-1·F-3·F-4·F-5, major 3·minor 1)을
같은 배포 전에 시정했다.

- **F-1** — funnel 캡처 절이 「월요일·연휴 뒤 장전 `scanner._scan_pool_eager_refresh_loop` 가
  기존 raw 머지 없이 upsert 해 장전 0값 키를 지운다」를 「미시정(결정 대기)」로 적었던 것을
  「시정(사용자 8영역 승인)」으로 갱신했다. 시정 자체는 `scanner.py` 코드(cycle176 basics 경로와
  같은 `{**기존, **신규}` 머지)이고, 이 문서 갱신은 그 사실을 반영한 것뿐이다. 겹치는 시각(T+600)
  자체는 여전하다 — 바뀐 것은 그 겹침이 더 이상 데이터를 파괴하지 않는다는 것.
- **F-4** — basics 가 full_universe 뒤에도 계속 SKIP 하며 KIS 출처 키 결손을 16:10 까지
  방치하던 것에 강제 재실행 콜백(`immediate_force_run_check`/`immediate_force_run_reason`)을
  신설했다. `task_loop_helper` 의 `run_periodic_task_loop`/`_evaluate_slot_gate` 시그니처에
  키워드 인자가 하나씩 늘었다(기본값이 기존 `"below_floor"` 라 full_universe 회귀 0).
- **F-5** — `_evaluate_slot_gate` 판정 순서 ②(marker_error)가 실제로는 도달 불가라는 사실을
  실측(실 `get_task_last_success` 경로 테스트)으로 확인하고 문서에 명시했다. 코드는 무변경이다.

→ CHANGELOG: cycle363(배포 전 보강) 행

## VI · 장운영 채널 (H0UNMKO0)

### 2026-09-26 cycle368 — `market_operation_monitor.py` 항목의 상태 목록·파싱 서술 교체

정본 원문(행 일부, `src/engine/CLAUDE.md:84`):

- **`market_operation_monitor.py`** — H0UNMKO0 **수신·상태 추적**. `handler._handle_market_op` → `record_market_op_event(MarketOpEvent)` → `_vi_active_tickers`/`_halt_active_tickers`/`_market_op_last_event` 3 dict. `MarketOpEvent`(`src/api/market_operation.py`) = KIS 10컬럼 전수 파싱. `is_ticker_stale_excluded(ticker)` 를 `stale_watcher_core` 가 소비한다(VI·거래정지 종목 stale 회피). … + `get_market_op_state_summary()`(`circuit_breaker` + `iscd_stat_active_count`) + …

경위: 「KIS 10컬럼 전수 파싱」은 라이브 프레임에서 사실이 아니었다(첫 칸이 종목코드라 한 칸씩 밀렸다 —
cycle359 조사). cycle368 이 파서 기준점을 고치고, VI 수명 600초(사용자 결정 「10분 뒤 자동 해제」)와
거래정지 수명 600초(메인 세션 결정, 사용자 승인 범위 안)를 위해 수명 dict 2개를 더해 상태가 5개가 됐다.
`iscd_stat_active_count` 는 표시 집합 {51,52,53,54,58,59} 로 세도록 바뀌었다(55·57·00 제외).

→ CHANGELOG: cycle368 행

## funnel 스냅샷 캡처

### 2026-09-26 cycle364 S1 — 16:20 저녁 재준비 → 21:00 다음 거래일 미리보기(A1), 확정 행 보호(③-b)·라벨 가드·④ 대조 신설

정본 원문(절 본문 전체, 교체 전):

- 공통 헬퍼 `capture_funnel_snapshots(registry, *, is_provisional)` — registry 를 순회하며 전략별 `_funnel_steps` 단계별 + `step_no=99` 를 insert 한다. 전략별 예외 격리(graceful), momentum 은 영구 제외, in-place upsert.
- 호출처 3 = 09:30 자동(`_auto_capture_funnel_snapshots`, `is_provisional=False` — 실행은 `_scan_loop` 첫 패스라 첫 대기 `SCAN_INTERVAL` 뒤 ≈09:35) · 16:20 저녁(`_evening_funnel_capture_once`, `is_provisional=True`) · 수동 trigger(`routes/strategy_funnel.py::trigger_snapshot`, `is_provisional=False`).
- 저녁 task `TIME_EVENING_FUNNEL_CAPTURE = time(16, 20)`, `initial_delay_secs=600`: (1) `stock_master_daily.count_all() > 0` 5분 cap polling — ⚠️ **그날 적재 완료를 기다리는 것이 아니다**(일봉은 20:30 이라 16:20 캡처는 전일 봉 기준이고, 전략 절단이 날짜 비교라 결과가 같다). 빈 테이블만 막는다 (2) 등록 전략 전부(`registry.all()`)의 `prepare()` (3) 캡처.
- **저녁 task 는 아침에도 한 번 돈다** — `run_periodic_task_loop` 의 즉시 1회(`immediate_first_run` 기본값, 게이트 kw 전무)가 `start()` +600초에 실행된다(07:45 기동이면 ≈07:57). `run_daily` 가 매 거래일 `start()` 를 다시 부르므로 재시작이 없어도 매일 돈다. 그때도 등록 전략 전부의 `prepare()` 를 다시 부르고 오늘 날짜로 잠정(`is_provisional=True`) 행을 쓴다. 이 재준비는 살아 있는 전략 객체의 후보를 교체하므로 그 뒤 매수 평가는 이 결과를 쓴다.
  - **입력은 부팅 준비와 같다.** 부팅 준비(`_boot()` 안의 전 전략 `prepare()`)는 `start()` 가 적재 태스크(`_full_universe_load_task` +0초 · `_stock_master_daily_load_task` +240초 · `_stock_master_basics_refresh_task` +480초)를 만들기 **전에** 끝난다. 그 세 적재의 즉시 실행은 영업일 슬롯 게이트를 지나야 돈다(「정기 task 루프」 절). 그래서 평상시 월요일·연휴 뒤 아침에는 보충 적재가 돌지 않고, 재준비는 부팅 준비와 같은 입력을 읽어 같은 목록을 낸다.
  - **보충 적재가 도는 날**(직전 영업일 정기 실행 결손 = `reason=stale` · 휴장일 모름 = `calendar_unknown` · full_universe 행 수 미달 = `below_floor`)에는 그 적재가 바꾼 입력을 라이브 후보에 반영하는 경로가 이 재준비다. 이 반영은 순서 보장이 아니라 경합에 기댄다 — 재준비는 `count_all() > 0` 만 기다리고 +240초 일봉 보충 적재의 **완료**는 기다리지 않는다.
  - 🔴 **이 즉시 1회에 게이트를 걸지 않는다** — 재준비의 `self._candidates = {}` 가 donchian 보유 종목을 후보에서 지워, 그날 트레일링 ATR 이 `_entry_atr`(매수 시점 ATR)로 떨어진다. 재준비를 건너뛰면 그 기준이 부팅 recompute 의 오늘 ATR 로 바뀐다. 청산 규약 변화라 그 결정(cycle360 카드 3)이 게이트보다 먼저다(근거 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.4·§5).
  - ✅ **「같은 입력」을 깨던 예외 경로(F-1) — cycle363 배포 전 보강으로 시정(사용자 승인 8영역).** 월요일·연휴 뒤 장전에는 `scanner._scan_pool_eager_refresh_loop`(5분 주기)가 24h 를 넘긴 풀 종목을 갱신하는데, 그 갱신과 +600초 재준비가 **같은 시각(T+600)에 시작하는 것 자체는 여전하다**(독립 검증 finding #1/#5, 09-28 에 실제로 겹칠 것으로 추정). 바뀐 것은 그 갱신이 더 이상 raw 를 통째로 지우지 않는다는 것이다 — `upsert_one` 전에 basics 경로(cycle176)와 같은 `{**기존 raw, **신규 raw}` 머지를 넣어, 장전 0 값 키(`_ZERO_VALUE_SKIP_KEYS` — `acml_tr_pbmn` 등)가 사라지지 않고 기존 값에서 보존된다. 그래서 재준비가 그 갱신과 겹쳐도 `list_by_filter` 거래대금 임계(`acml_tr_pbmn_won`)가 더 이상 NULL 로 떨어지지 않는다. 판별 마커 = `[scan_pool_eager_refresh] refreshed=N`(N>0 이면 그 사이클이 실제로 돌았다는 뜻, 결함 여부와 무관) + `select count(*) from stock_master where not raw ? 'acml_tr_pbmn'`(머지가 살아 있으면 이 값이 늘지 않아야 한다). 회귀 = `tests/unit/engine/test_cycle363_scan_pool_eager_refresh_raw_merge.py`.
- 🔴 **결함 — 16:20 캡처가 그날 확정 행을 덮는다.** `capture_funnel_snapshots` 는 호출자와 무관하게 `target_date = 오늘(KST)` 를 쓴다. 그래서 하루 세 쓰기가 같은 `(target_date, strategy_id, step_no)` 행에 떨어진다 — ≈07:57 잠정 INSERT → ≈09:35 확정 UPSERT → 16:21 잠정 UPSERT. **그날 매매에 쓴 확정 행은 남지 않고**, 20:05·21:30 리포트의 `strategy_funnel_stages` 도 16:20 숫자를 읽는다. 덮인 행은 `snapshot_at`(마지막 쓰기 시각)이 16:21 을, `is_provisional` 이 `TRUE` 를 가리키므로 행만 보고는 09:35 확정 값이 있었는지 알 수 없다(`snapshot_at` 정의 = `src/db/CLAUDE.md` `strategy_funnel.py` 절). 잠정 쓰기가 확정 행을 못 덮게 하는 보호는 들어가 있지 않다 — 지금 일정(16:20 · 오늘 날짜)에서 단독으로 넣으면 평일 저녁 쓰기가 전부 거부돼 저녁 산출물이 사라지기 때문이다(설계와 근거 = `_workspace/red/cycle350_evening_funnel_spec.md` §2). 실측·근거·결정에 필요한 사실 = `_workspace/red/cycle349_vcp_observe_spec.md` 「② 퍼널 스냅샷 오전/16:20 분리」 절. VCP 의 오전 후보 목록은 이 스냅샷이 아니라 `[vcp_breakout_distance_summary]` 로 복원한다(`strategies/CLAUDE.md` 각주 ⑥).
- 🔴 **저녁 캡처를 20:30 일봉 적재 뒤로 옮기는 것만으로는 다음 거래일 미리보기가 되지 않는다** — funnel 을 내는 6전략(momentum 제외)의 `prepare()` 가 벽시계 오늘(KST) 날짜의 봉을 버려(`prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0`) 20:4x 에 돌려도 D-1 기준이므로, `prepare()` 에 기준일을 넣는 것이 선결이다(근거·선택지 = `_workspace/red/cycle350_evening_funnel_spec.md` §2).
- `task_attrs` 4 위치(start + connect finally + run_daily finally + stop, G-AST2).
- `is_provisional` 컬럼 = migration 040.
- 관찰성 한정 — `check_exit`/`check_buy` funnel hook 0건 + risk/order_engine/realtime/auth 참조 0(SAFETY 가드).

경위: 사용자 결정 D3(2026-09-25 저녁 「D3 카드는 모두 권고대로」 — 설계 `_workspace/domain_consult/cycle364_a1_as_of_design.md` 카드 1~5 (가)).
위 원문의 「🔴 결함 — 16:20 캡처가 그날 확정 행을 덮는다」는 세 가지로 닫혔다 — 저녁 쓰기가 다음 거래일 날짜로 가고,
잠정 쓰기가 확정 행을 못 덮고(③-b), 확정 캡처가 저녁 미리보기 meta 를 거부한다(라벨 가드).
「저녁 캡처를 20:30 일봉 적재 뒤로 옮기는 것만으로는 다음 거래일 미리보기가 되지 않는다」는 `prepare(as_of=)` 로 해결했다.
캡처 시각은 20:30 이 아니라 21:00 이다(20:45 보조 계정 토큰 재발급 체인과 겹치지 않게). 16:20 재준비가 사라지면서
애프터장(16:00~20:00) 도중 LTV 후보가 갈리던 일과 donchian 보유 트레일링 ATR 이 16:20 에 매수 시점 ATR 로 떨어지던 일이 없어졌다.
부팅 +600초 즉시 1회는 S1 임시 「레거시 재준비」로 남았고 대기 신호(`count_all() > 0` 5분 폴링)는 없어졌다.
실측 근거(09-21~23, 16:20 재준비가 분모를 매일 바꿈 — BFB 600→564, VCP 711→659, kojiro 703→657)는 설계 §0-8.

→ CHANGELOG: cycle364 S1 행

## 저녁 데이터 적재 (scanner + data_load_tasks)

### 2026-09-26 cycle364 S1 — 시각 표의 저녁 funnel 행

정본 원문(표 행):

| `TIME_EVENING_FUNNEL_CAPTURE = time(16, 20)` | 16:20 | 저녁 잠정 funnel 캡처 |

경위: 캡처 시각을 21:00 으로 옮기고 행을 시각순(20:30 적재 뒤)으로 옮겼다.

→ CHANGELOG: cycle364 S1 행

## scheduler.py — KRX/NXT 통합 운영 08:00~20:00

### 2026-09-26 cycle364 S1 — `TIME_*` 표의 저녁 funnel 행 · 07:59 사전 구독 행 · 재준비 cap 문장

정본 원문(표 행 2 + 목록 행 1):

| `TIME_EVENING_FUNNEL_CAPTURE` | 16:20 | 저녁 잠정 funnel 캡처(`_evening_funnel_capture_task_loop`) — 상세 = 「funnel 스냅샷 캡처」 절 |
| `TIME_PRESUBSCRIBE` | 07:59 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독 |
- **`_reprepare_breakout_if_empty` WARNING DailyEmitCap**: "스캔 후보 비어있음 — 재 prepare 시도" logger.warning + `write_log` DB INSERT 를 `_reprepare_empty_logged_today: DailyEmitCap[str]` 로 1회/전략/일 cap 한다(후보 0 은 정상 장세일 수 있다). 🔴 **`strategy.prepare()` 재시도 행위는 cap 밖 불변**이다(회복 메커니즘 보존). `getattr` 폴백 = `__new__` 스텁 인스턴스 호환(cap 부재 시 기존 무제한 emit). 회귀 `tests/unit/engine/test_cycle189_reprepare_emit_cap.py`

경위: 저녁 funnel 행을 21:00 으로 옮겼고, 07:59 재준비와 `_reprepare_breakout_if_empty` 의 재준비가 `strategy.prepare()` 직접 호출에서
`funnel_capture.live_prepare_one(…)` 경유로 바뀌었다(라이브 준비 단일 입구 + 잠금 + meta).

→ CHANGELOG: cycle364 S1 행

## 모듈 맵

### 2026-09-26 cycle364 S1 — `trading_calendar.py` 항목(소비처 2곳 → 3곳, API 3개 → 4개)

정본 원문(목록 행 2):

- **`trading_calendar.py`** — 휴장일 판정 공용 leaf(8영역·`scheduler.py`·`boot_manager.py` import 0). 「몇 시간 지났나」·「달력 며칠 지났나」 대신 「직전 영업일이 언제인가」를 묻는 두 곳이 쓴다 — 부팅 즉시 실행 슬롯 게이트(`task_loop_helper._evaluate_slot_gate`)와 6전략 prepare 의 일봉 신선도 기준(`StrategyBase._resolve_expected_daily_head`).
  - API 3개는 전부 **never-raise**(예외 → `None`)다. `is_open_day(d) -> bool | None` · `previous_trading_day(today) -> date | None`(`today` 보다 엄격히 이전의 가장 최근 개장일. 최대 `_PREVIOUS_TRADING_DAY_LOOKBACK_DAYS`=10 달력일을 거슬러 가고, 도중 `None` 을 만나면 추측하지 않고 `None`) · `latest_passed_trading_slot(now_kst, slot) -> datetime | None`(`now` 이하인 「개장일 D 의 `slot` 시각」 중 가장 최근, KST aware. `now.time() >= slot` 이면 오늘부터 본다).

경위: `next_trading_day(d)`(앞으로 최대 14 달력일)가 더해졌고 저녁 미리보기(`funnel_capture`)가 세 번째 소비처가 됐다.

→ CHANGELOG: cycle364 S1 행

## 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

### 2026-09-26 cycle364 S1 — 「미대상」 문장

정본 원문(목록 행):

- 미대상 = purge · evening_funnel(게이트 kw 전무). evening_funnel 의 즉시 1회가 +600초 재준비다 — 게이트를 걸지 않는 이유는 「funnel 스냅샷 캡처」 절.

경위: +600초 즉시 1회는 21:00 전이라 레거시 재준비 분기를 탄다. 그 분기는 미리보기가 아니다.

→ CHANGELOG: cycle364 S1 행

## strategy_base.py

### 2026-09-26 cycle364 S1 — 추상 `prepare` 시그니처 · `_resolve_expected_daily_head` 시그니처

정본 원문(목록 행 2, 둘째 행은 앞부분만):

- `StrategyBase` 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`
- **일봉 신선도 기준 `_resolve_expected_daily_head() -> date | None`** — `trading_calendar.previous_trading_day(today_kst())` 를 지연 import 로 부르고(never-raise, 예외 → `None`) `[prepare_expected_head] strategy=<id…

경위: `prepare(self, *, as_of: date | None = None)` 로 기준일 인자가 생겼고 `_resolve_expected_daily_head(as_of_date=None)` 가
`previous_trading_day(as_of_date 또는 오늘)` 을 쓴다. 헬퍼 3종(`_resolve_prepare_as_of`·`_preview_keep_tickers`·`_preview_skip_tickers`)이 더해졌다.

→ CHANGELOG: cycle364 S1 행

## order_engine.py

### 2026-09-26 묶음 D S1(J-1) — 규칙 3 「`_cancel_and_reorder` 는 쌍으로 막는다」 행의 회수 위임 문장

정본 원문(목록 행 끝 괄호):

  - **`_cancel_and_reorder` 는 쌍으로 막는다** — 이것만 `cancel_order` → `place_order` 의 atomic replace 다. 절반만 막으면 "호가창에 있던 손절을 우리가 빼고 아무것도 안 넣은" 상태가 된다. 컷이면 **취소도 하지 않고** 작동 중인 주문을 그대로 둔다(16:00 이후 `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임).

경위: 괄호 안 위임처 둘 다 걸린 잔량을 거두지 않는다. `cancel_remaining` 은 `src/` 안에 호출자가 없고(정의 1곳뿐), 그 함수가 취소하는 `pos.order_no` 는 포지션을 만든 매수 주문번호다. `risk.on_tick` 재평가는 새 매도를 낼 뿐 취소를 하지 않는다. 운영자가 「16:00 에 알아서 회수된다」고 믿고 걸린 주문을 두게 만드는 문장이라 걷었다.

→ 근거: `_workspace/domain_consult/cycle332_buy_cancel_timer.md` §10 · `_workspace/red/bundle_D_plan.md` S1

### 2026-09-27 cycle374 — 규칙 4 「알려진 비용 — GTP 08:50 자동취소 잔존 상태」 의 DEBUG 서술 · 관측 방법 문장

정본 원문(목록 행 3):

  - **알려진 비용 — GTP 08:50 자동취소 잔존 상태.** 취소 통보는 체결통보 채널로 **온다**(09-14 실측 073240: `08:29:34` 접수 통보 + `08:50:00` 정각에 같은 주문번호로 두 번째 통보, KIS 주문내역은 그 주문을 `GTP매수자동취소*` 로 기록). 그러나 `handler.py::_handle_execution` 의 `exec_type != "2"` 분기가 DEBUG 한 줄만 남기고 버려, 잔존 상태(`pending_buys`/`pending_buy_amounts`/`_pending_buy_orders`/`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division`/`trade_history` PENDING 행)를 **장중에 정리하는 경로가 없다**. 그 종목은 그날 21:30 `reset_daily_state()`(메모리 5종)까지, `trade_history` 행은 **영구**로 남고 `is_ticker_blocked_for_buy` 가 그날 재진입을 막고 예산을 점유한다. GTP 는 이 빈도를 **늘린다**(08:50 까지 안 채워진 모든 프리장 매수가 대상 — `00` 은 09:00:30 정규장 이월로 일부가 결국 체결·취소돼 조기 정리된다). 순수 기회비용이고 자본 위험은 아니다.
    - **시정 경로** = 이미 구독 중인 체결통보 채널로 취소가 도착하므로 `handler.py` 가 `exec_type=="1"` 프레임에서 취소를 판별해 콜백으로 넘기고 `order_engine` 이 잔존 상태를 정리한다. 접촉 = `src/realtime/handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**) · `scheduler.py` **무접촉**.
    - 🔴 **선결 = 취소 프레임의 판별 필드 실측.** 09-14 관측은 "프레임이 왔다" 까지만 증명한다 — 현행 DEBUG 줄이 `order_no`·`ticker` 두 필드만 찍으므로 그 프레임의 `fields[5]`(RCTF_CLS 정정구분)·`fields[12]`(RFUS_YN 거부여부)·`fields[14]`(ACPT_YN 1:주문접수 2:확인 3:취소) 실제 값은 모른다. 접수(08:29:34)와 취소(08:50:00)를 가르는 필드를 확정하지 않고 분기를 짜면 접수 통보를 취소로 오인해 **살아 있는 주문의 상태를 지운다**. 관측 방법 = 그 DEBUG 줄에 `fields[:20]` 을 실어 GTP 미체결 1건 관측(`handler.py` 8영역 1줄 변경, 승인 대상).

경위: cycle374 가 `handler.py::_handle_execution` 에 접수 전문(`CNTG_YN=1`) 기록을 넣었다 — INFO `[order_notice]`(이름 붙은 칸) + 거부면 WARNING `[order_rejected_notice]`. 「DEBUG 한 줄만 남기고 버려」 와 「현행 DEBUG 줄이 `order_no`·`ticker` 두 필드만 찍으므로」 는 사실이 아니게 됐다. 관측 방법 「그 DEBUG 줄에 `fields[:20]` 을 실어」 는 `[0]` HTS ID·`[1]` 계좌번호·`[17]` 계좌명을 로그에 싣는 방법이라 채택하지 않았고, 이름 붙은 칸만 싣는 `[order_notice]` 로 대신했다. 잔존 상태를 장중에 정리하는 경로가 없다는 결론은 그대로다(기록만, 콜백 없음).

→ CHANGELOG: cycle374 행

## 접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2

### 2026-09-27 cycle379 — 「접수된 자금은 묶어 둔다」 행의 유지 비용 문장

정본 원문(목록 행):

- **접수된 자금은 묶어 둔다** — 접수 후 실패에서 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다**. 접수된 매수는 KIS 가 주문가능금액에서 이미 뺀 「묶인 자금」이라 푸는 것은 **우리가 묶인 사실을 잊는 것**이고, 계좌 방어(`get_buyable`)는 통과하므로 **전략 예산 관문만 조용히 무력화**된다. 유지의 비용은 **체결 0건인 주문 한정**으로 그 슬롯·금액이 21:30 `_reset_daily_state` 까지 노는 것뿐이다 — 첫 **부분**체결만 나도 `_handle_buy_fill` 이 해제한다(그 블록은 전량 분기 **앞**이다).

경위: cycle379 가 leaf `src/engine/buying_reconcile.py` 를 넣었다. 15분 잔고 sync 가 그 주문 자신의 KIS 행(`tot_ccld_qty==0 ∧ rmn_qty==0`, 주문 뒤 300초 경과)을 보고 `pending_buys`·`pending_buy_amounts`·`_pending_buy_orders` 를 푼다. 「그 슬롯·금액이 21:30 `_reset_daily_state` 까지 노는 것」 은 20:00 뒤에 끝난 주문에만 맞는 말이 됐다. 접수 후 실패에서 `execute_buy` 가 pending 을 풀지 않는다는 규칙 자체는 그대로다.

→ CHANGELOG: cycle379 행

## order_engine.py

### 2026-09-27 cycle379 — 규칙 4 「알려진 비용 — GTP 08:50 자동취소 잔존 상태」 의 잔존 기간 문장 · 「시정 경로」 머리

정본 원문(목록 행 2):

  - **알려진 비용 — GTP 08:50 자동취소 잔존 상태.** 취소 통보는 체결통보 채널로 **온다**(09-14 실측 073240: `08:29:34` 접수 통보 + `08:50:00` 정각에 같은 주문번호로 두 번째 통보, KIS 주문내역은 그 주문을 `GTP매수자동취소*` 로 기록). 그러나 `handler.py::_handle_execution` 은 `CNTG_YN != "2"` 프레임을 `[order_notice]` 로 **기록만** 하고 콜백으로 넘기지 않는다(`src/realtime/CLAUDE.md` 「접수 전문 기록」). 그래서 잔존 상태(`pending_buys`/`pending_buy_amounts`/`_pending_buy_orders`/`_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division`/`trade_history` PENDING 행)를 **장중에 정리하는 경로가 없다**. 그 종목은 그날 21:30 `reset_daily_state()`(메모리 5종)까지, `trade_history` 행은 **영구**로 남고 `is_ticker_blocked_for_buy` 가 그날 재진입을 막고 예산을 점유한다. GTP 는 이 빈도를 **늘린다**(08:50 까지 안 채워진 모든 프리장 매수가 대상 — `00` 은 09:00:30 정규장 이월로 일부가 결국 체결·취소돼 조기 정리된다). 순수 기회비용이고 자본 위험은 아니다.
    - **시정 경로** = 이미 구독 중인 체결통보 채널로 취소가 도착하므로 `handler.py` 가 `CNTG_YN=="1"` 프레임에서 취소를 판별해 콜백으로 넘기고 `order_engine` 이 잔존 상태를 정리한다. 접촉 = `src/realtime/handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**) · `scheduler.py` **무접촉**.

경위: cycle379 의 `buying_reconcile` 이 그날 첫 잔고 sync(≈09:45)에서 자동취소된 매수의 `pending_buys`·`pending_buy_amounts`·`_pending_buy_orders` 를 풀고 `trade_history` PENDING 행을 CANCELLED 로 적는다. 「장중에 정리하는 경로가 없다」 와 「`trade_history` 행은 영구로 남고」 는 사실이 아니게 됐다. 주문번호 매핑 5종은 늦은 체결통보 안전망이라 일부러 21:30 까지 남긴다. 통보(`CNTG_YN=="1"`)로 정리하는 경로는 여전히 없지만, 그 경로가 줄이는 것은 08:50~≈09:45 의 점유뿐이라 「시정 경로」 가 아니라 「통보로 즉시 정리하는 경로」 로 이름을 바꿨다.

→ CHANGELOG: cycle379 행

## 저녁 데이터 적재 (scanner + data_load_tasks)

### 2026-09-27 cycle380 — 「유니버스 선정」 `is_protected` 의 괄호 설명

정본 원문(목록 행):

- `is_protected` = 공통 헬퍼 `_collect_protected_tickers_for_scanner()` 가 돌려준 보유·익일청산 종목 중 **6자리 숫자 ticker 만**(진입 게이트 비대칭 규약과 동일 — ETF·신주인수권·오염 문자열 제외). 헬퍼 예외는 **fail-open**(`protected_tickers = set()` 로 index/qualifier 만 진행).

경위: cycle380 이 ETF 코드도 6자리 숫자임을 확인했다(`stock_master` 3,583행 전부 6자리 숫자, 2026-09-27 읽기 전용 조회). 6자리 숫자 필터는 ETF 를 빼지 않는다. 필터 동작은 바뀌지 않았고 괄호 설명만 사실에 맞췄다.

→ CHANGELOG: cycle380 행

## 순수 함수 leaf (DB · HTTP · 시계 미접촉, 8영역 미접촉)

### 2026-09-27 cycle384 — `param_validation.py` 항목의 「매수를 멈추는 정당한 수단」

정본 원문(`param_validation.py` 항목 중 한 구절):

어느 쪽도 운영자의 의도가 아니고, 매수를 멈추는 정당한 수단은 전략 비활성화다.

경위: 전략 비활성화는 보유분의 손절·트레일링까지 멈춘다(루트 `CLAUDE.md` 금기 — `risk.on_tick` 이 `registry.enabled()` 만 돈다). cycle384(사용자 결정 2026-09-27 「돈키언 신규매수 중지」)가 신규 매수 신호만 멈추는 `buy_paused` 를 7 전략에 두었으므로 그것을 정당한 수단으로 적었다.

→ CHANGELOG: cycle384 행

## 체결통보 주문수량 — 출처 3단 (cycle329)

### 2026-09-27 cycle385 — 매도 피해 서술 · 「재조회 0」 · 남는 사각

정본 원문(「고치는 것」 문단 중 한 문장):

매도는 `del positions[ticker]` 로 **미체결 잔량이 손절 감시 밖으로 사라지고**(15분 sync 까지 무방비), 매수는 `_completed_buy_orders` 가 무장해 잔여 통보가 `[buy_fill_duplicate_ignored]` 로 **조용히 버려진 채** `_sync_positions_from_balance` 가 `is_ticker_held_by_any → continue` 라 **기보유 수량을 영원히 고치지 않는다**(10주를 갖고 3주로 믿는 상태가 익일 `_boot` 까지 간다).

정본 원문(「재주문 타이머」 항목 중 한 구절):

이 시정으로 매핑 부재 창의 통보가 처음으로 **부분 분기에 도달**하는데 `_cancel_and_reorder` 에는 포지션 재조회가 **한 줄도 없다**(실측).

정본 원문(「남는 사각」 항목):

- ⚠️ **남는 사각** — payload 가 없으면 매핑 부재 창에서 주문수량을 알 길이 없어 결함이 그대로다. 그 빈도는 `increment` 카운터가 센다.

경위: cycle385(사용자 결정 2026-09-26·27 「부분매도해도 잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리할 수 있다는 전제하에 허용」 · 「b7 분할매도 진행」)가 `_handle_sell_fill` 을 주문 축(`total_filled >= ordered_qty`)과 보유 축(`pos.quantity` 차감 → 0 이면 닫기)으로 나눴다. 매도는 매핑 부재 창에서 주문 축이 틀려도 보유 축이 체결량만큼만 빼므로 잔량이 추적에 남는다. 같은 사이클의 J-2 가 `_cancel_and_reorder` 의 `place_order` 직전에 registry 전수 보유 재조회(`_reorder_requery`)를 넣었으므로 「재조회가 한 줄도 없다」 는 사실이 아니게 됐다. 다만 취소는 여전히 조건 없이 나가므로 `qty_src == "map"` 게이트의 이유는 그대로다. 명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md`.

→ CHANGELOG: cycle385 행

## strategy_base.py

### 2026-09-27 cycle385 — `on_position_closed` 호출 site 표현 · 「full-fill 한정」

정본 원문(두 구절):

- `on_position_closed(ticker)` — 포지션 전량 청산(매도 체결) 시 per-ticker 보유결합 상태 정리. 호출 site 는 `order_engine` **정확히 2곳**(`_handle_sell_fill` 전량체결 `if pos:` 후 + `execute_sell` insufficient_qty reconciliation, 각 try/except 격리).
- 부분 체결은 full-fill 한정이라 잔량 청산모드가 자연 보존된다.

경위: cycle385 가 `_handle_sell_fill` 의 닫기 판정을 「주문 전량 체결」 에서 「보유가 0 이 됐나」(`if close_position:`)로 옮겼다. 호출 site 는 여전히 두 곳이고(G2-STRUCT-INVARIANT 그대로), 보유가 남는 매도는 훅을 부르지 않는다 — 뜻은 같고 판정 기준만 정확해졌다.

→ CHANGELOG: cycle385 행

## order_engine.py

### 2026-09-27 cycle385 — 「체결 후처리」 매도 항목

정본 원문(「체결 후처리」 매도 항목 첫 문장):

- 매도 → DB positions 삭제 + `sold_today` 등록.

경위: cycle385 부터 매도 체결은 보유가 0 이 될 때만 DB 삭제·`sold_today`·구독 해제를 한다. 보유가 남으면 차감 수량을 `save_position` 으로 저장한다.

→ CHANGELOG: cycle385 행

### 2026-09-27 cycle385 부록 R — `is_sell_qty_exceeded` #1.5 잔고 재대조 항목

정본 원문(「`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조」 항목):

- **`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조**: APBK0400 "수량 초과" 는 부분 보유 내재 코드라 insufficient(통째 삭제)로 **흡수 금지**다(257720 실사고). `execute_sell` 재시도 루프에서 closed 다음·insufficient 앞에 `get_balance` 재대조 — ① 오염(`held < positions`) = `[sell_qty_reconciled]` WARNING + **held(보유 실체)로 보정**(sellable 아님 — 잠긴 주식도 보유라 손절 감시 수량은 held 가 정합이고, sellable 부족 재거부는 다음 분기가 흡수한다) + `save_position` DB 동행 + `continue`(3회 한도 내 자기 치유) ② 부분/전량 잠김(`held ≥ positions ∧ sellable < held`) = `[sell_qty_partial_locked]`/`[sell_qty_locked]` WARNING + 보존 + return — **`_selling` 의도적 유지**(열린 기주문이 실재하므로 진행 중 표식이 참이고, on_tick 재진입 폭주를 차단한다. stale 은 `[selling_reconcile]` 180s 재대조 소관. market_closed 의 discard 와 다른 이유 = 그쪽엔 열린 주문이 없다) ③ 실보유 0 = 기존 insufficient 경로 재사용 ④ 재대조 실패 = graceful 일반 재시도. ⚠️ sync 는 기보유 종목 수량을 갱신하지 않으므로 DB 보정 실패 시 구값이 다음 보정·청산까지 남는다

경위: cycle385 부록 R(사용자 전제 2026-09-26 「잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리」 · 적대 검토 F-1·F-3)이 두 분기를 바꿨다. ① 오염 보정 전에 TTTC0081R(`get_daily_orders(exchange="ALL", pdno=ticker)`)로 주문별 「스냅샷에 이미 반영된 체결」 크레딧을 적는다. 보정 뒤 늦게 온 체결통보를 보유 축이 한 번 더 빼던 이중 차감의 시정이다(탐침: 추적 10 · MTS 3주 체결 · 통보 지연 → 재발사 `[10, 4]`, 실보유 7). ② 부분 잠김은 `fire = sellable − (held − eff)` 가 1 이상이면 그 수량을 판다(`eff` = 추적 − 아직 안 온 외부 체결 통보, 부록 R2-8). 외부 부분 매도주문이 걸린 동안 안 잠긴 추적 잔여의 손절이 그 주문이 끝날 때까지 멈추던 공백의 시정이다. 주문 조회를 못 믿으면 쏘지 않고 동결한다. 두 분기가 쓰는 주문 조회는 1건이고 2.0초 상한이다(부록 R2-9). 동결 분기는 `_selling_locked_wait` 표식을 단다(「주문 없이 멈춘 동결」 — 부록 R2-5). 부록 R3 가 원장 시작 시각(`_sell_ledger_since`)보다 먼저 접수된 주문을 「아직 안 온 체결 통보」에서 빼고(재시작 뒤 빈 원장 때문에 손절이 그날 멈추던 회귀의 시정), 걸린 매도가 없을 때의 보류를 `[sell_qty_unnoticed_fills]` 로 나눴다. 부록 R4 가 그 보류를 유지하기로 정하고(D1 — 글자대로 풀면 재대조가 운영자 몫을 판다), 주문 조회가 실패한 경우를 `[sell_qty_hold_orders_unavailable]` 로 다시 나눴다(D4 — 조회 `await` 동안 통보가 추적을 줄인 경합에서 「거래소가 확인한 미통보 체결」 문구가 사실이 아니었다, seed 1177).

→ CHANGELOG: cycle385 행

## 저녁 데이터 적재 (scanner + data_load_tasks)

### 2026-09-28 cycle386 — 「확정 전 오늘봉 시각 필터」 D 봉의 최종값 보정 담지자

정본 원문(목록 행):

- **D 봉의 최종값 보정 담지자 = D+1 정기 실행(20:30)의 7일 증분 창**(`fetch_days=7` → `ON CONFLICT DO UPDATE`). 🔴 그 창을 1~2일로 줄이면 D 봉이 그날 스냅샷에 영구 고정된다(가드 = cycle263 G2 의 "보정 창 존치" 단언).

경위: cycle386 실측(2026-09-28, `_workspace/domain_consult/cycle386_daily_close_after_market.md` §0~§4)으로 KIS 일봉(FHKST03010100 `J`)이 D일 20:30 에도 종가를 19:59 애프터마켓 마지막 체결가로, 고저를 애프터마켓 포함 범위로 준다는 것이 드러났다(09-23 봉 모집단 약 60% 종가 불일치). D+1 20:30 7일 창은 다음 날 아침 prepare 보다 늦어, 모든 전략이 하루 동안 가짜 전일 봉을 읽었다. 유니버스에서 빠진 종목의 가짜 봉은 그 창이 다시 덮지 않아 DB 에 남았다. 1차 확정을 다음 거래일 아침 부팅(`daily_bar_finalize`)으로 옮기고, 7일 창은 2차 안전망으로 남겼다.

→ CHANGELOG: cycle386 행

## 2026-10-01 sync-docs 압축 — 정본에서 이관 (앞쪽 절반: 파일 시작 ~ 「매도 체결 — 주문 축과 보유 축」)

> 사용자 요청 「CLAUDE.md 파일들 전반 점검 — 중복·낡은 부분 삭제, 유지할 내용 압축」에 따른 /sync-docs 모드 B 압축.
> 아래는 압축·정정으로 정본에서 바뀌거나 빠진 **원문 줄 그대로**다(정본에 글자 그대로 남지 않은 줄 전부). 정본은 새 값만 남겼다.
> 정정한 사실(원문이 틀렸던 것): 일봉 적재 분기·요약 마커 서식 · 수동 일봉 적재 경로 · `backtest_yaml` 변환 범위 · 자동 원복 「전체 침묵 기각」 · LTV 손절 수치(운영 DB 값) · `DEDICATED` → `DEDICATED_TICK_TR_IDS` · `observer_trace` 미적용 잔존 줄번호 표류.

### 출처 절: 모듈 맵 › 매매 흐름 축

- **`boot_manager.py`** — `_boot` 본체. 토큰 발급(`token_manager.get_token()`) 직후 `daily_bar_finalize.spawn(phase="boot")` 로 전일 잠정 봉 확정 태스크를 **await 없이** 띄운다(함수 안 import). 설정 로드·잔고·레짐과 겹쳐 돌고, prepare 직전(`emit_daily_head_staleness` 앞)에 `daily_bar_finalize.wait_for_boot(…, budget_secs=daily_bar_finalize.BOOT_BUDGET_SECS)` 로 최대 90초 기다린다(하단 「저녁 데이터 적재」 절의 「전일 잠정 봉 확정」). `_load_strategy_config` 직후 `portfolio_risk.check_budget_invariant` 를 불러 `[budget_invariant_violation]` WARNING 을 남긴다. 활성 전략 준비는 `funnel_capture.live_prepare_one(strategy, phase="boot")` 로 부른다(wrapper 가 never-raise 라 호출부에 try 가 없다). 익일청산 복구 직후 `funnel_capture.spawn_funnel_boot_vs_evening(scheduler, phase="boot")` 를 **await 없이** 1회 부른다(④ 대조 — 하단 「funnel 스냅샷 캡처」 절).

### 출처 절: 모듈 맵 › stale 계열 (K stale watcher)

- **`stale_session_recovery.py`** — silent inactive 감지 · 세션 강제 reconnect · delta unsubscribe. **세션 상대 판정** = 판정 가능 세션(`subscribed >= 5`)이 2개 이상이고 그 전부가 `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` 면 세션 고장이 아니라 **시장 침묵**으로 보고 그 사이클을 기각하고 판정 가능 전 라벨의 `first_seen` 을 pop 한다(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다). 다른 세션이 하나라도 fresh 면 현행대로 발화하고, 판정 가능 세션이 2 미만이면 현행 유지(fail-open). 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측한다. 🔴 기각 판정에 시간창 리터럴·`tradable_boards`·`session` import 를 쓰지 않는다 — 세션 간 비교만이 15:30~15:40 갭까지 닫는다(AST G-241-5).
- **`stale_universe_guard.py`** — 보유·익일청산 절대 보호 universe guard.
- **`stale_watcher_core.py`** — 본체 `check_and_resubscribe_stale` + `resubscribe_stale_priority`(LOW desired = breakout ∪ momentum 교집합, HIGH 는 구조적 면제). 순서 = ① grace 가드 `_is_within_grace(t)`(`t in ticker_last_tick` 이면 False · `ack_at` 이 datetime 이 아니면 False · 예외 시 안전 폴백). ACK 조회 키는 **채널 무관 역인덱스** `ack_at_by_ticker` 다 — 채널 고정 키면 전용 채널 종목이 180초 grace 를 영구 miss 해 구독 직후 stale 로 읽히고 강제 재등록이 폭주한다. ② `SessionTracker.is_call_auction_now()` 가 True 면 **LOW-scoped skip**(cycle371 — `resubscribe_stale_priority`(5분 우선)가 이미 갖던 LOW-scoped skip 을 K watcher(120초)에도 미러) — stale ∩ HIGH(보유·익일청산)는 그대로 `unsubscribe_in_pool`→`subscribe(priority="HIGH", bypass_limit=True)` 강제 재등록하고, stale ∩ LOW 만 SEND 0·retry 카운터 무변경으로 건너뛴다. `[stale_skip_call_auction] subscribed= low= high=` WARNING 은 매 사이클 발화(HIGH stale 가 없어 전부 skip 인 사이클도 포함, 사이클 162 원 계약 — 그 경우 누적 retry 카운터 보존 + 조기 반환은 byte 동일). HIGH stale 이 하나도 없을 때만 조기 반환하고, `is_no_feed`(no_feed_held 판정)는 그 반환 **뒤**라 HIGH 없는 동시호가 사이클에서 판정 0회(W9 불변, `test_cycle252_stale_watcher_no_feed.py::test_w9_...`). HIGH 를 skip 하면 그 동시호가 창(아침 08:30~09:00, 110 코드가 있으면 08:25~09:05) 동안 보유 종목 재구독이 멎는 것이 곧 005935 사고 패턴이라 HIGH 는 skip 대상에서 뺐다. ③ no_feed skip: `subscribed` 확보 직후 `no_feed_registry.ensure_fresh(subscribed ∪ 보유·익일청산)` 를 try/except 로 부르고, `LOW ∧ is_no_feed(t) ∧ (킬스위치 off ∨ 실제 구독 채널 ∉ DEDICATED)` 이면(판정 위치 = priority 결정 직후 · `retry > MAX_STALE_RETRIES` 비교 직전) `r` 증가·`r>5` 홀드(`MAX+1`)만 하고 `continue`(SEND 0 · 스탬프 0 · history 0). 🔴 **HIGH 경로는 skip 대상이 아니다** — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지다. `high_tickers` 는 `if not stale_tickers: return` **앞**에서 계산해 `[no_feed_held] tickers=[…]` WARNING 1회/일을 stale 여부와 무관하게 매 사이클 판정한다(예외 흡수). **그 판정은 KRX 연속체결 창(09:00~, `_is_before_krx_continuous_open` — `tick_channel_clock._windows()` 의 `krx_regular_open` 재사용, 시각 리터럴 0건) 이전에는 억제하고 cap 을 소비하지 않는다(cycle357)** — NXT 프리장 동안 `nxt_tradable=False` 종목은 KRX 전용 채널에 있어도 KRX 가 시가 단일가라 어느 채널이든 연속체결 프레임이 정의상 0 이고, 그 정의상 공백을 무송출로 오판하던 08:00 거짓 경보(운영 2026-09-22·23 실측)를 없앤다. 경계 판정 실패는 억제하지 않는 방향(관찰 유지)으로 fail-open. `[stale_watcher_summary]` 끝 필드 ` no_feed_skipped=%d`. 마커 판독 = `no_feed_skipped` 와 `[stale_force_retry]` 는 **감소**가 성공 서명, `[no_feed_held]` 는 **0** 이 정상(09:00 이전 억제는 관측 범위 축소이지 판정 결과 변화가 아니다 — 09:00 이후에도 무송출이면 여전히 뜬다).
  - **해제는 3필드뿐이다** — 마지막 `await` 뒤 동기 헬퍼 `_release_if_unchanged` 가 다시 본다: pending 소유 전략이 여전히 그 하나인가 · 누구도 보유하지 않는가 · 연결 주문 집합이 같은가. 통과하면 같은 자리에서 `pending_buys.discard` · `pending_buy_amounts.pop` · `_pending_buy_orders.pop(o)` 만 한다. `_handle_buy_fill` 첫 체결 경로가 지우는 것과 같은 셋이다. 🔴 `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 **남긴다** — 판단이 틀려 늦은 체결통보가 오면 그 매핑이 올바른 전략·수량(`qty_src=map`)으로 포지션을 세운다. 21:30 reset 이 치운다. `sold_today`·`buy_blocked_until`·`low_funds_tickers`·`_completed_buy_orders` 는 무접촉이다 — **같은 날 재진입을 막지 않는다**(2026-09-27 사용자 결정 「9-a 풀어준 종목 재매수가능」, 기존 가드만 적용).

### 출처 절: 모듈 맵 › 관측·공통 헬퍼

- **`funnel_capture.py`** — 라이브 전략 준비의 **단일 입구** + 저녁 미리보기 본체 leaf. 공개 API = `resolve_as_of(now_kst, mode) -> AsOf | None` · `live_prepare_one(strategy, *, phase) -> bool` · `live_prepare_many(strategies, *, as_of, phase) -> {"prepared", "failed"}` · `capture_skip_reason(strategy, label, today, *, is_provisional) -> str | None` · `evening_capture_once(scheduler) -> dict` · `emit_funnel_boot_vs_evening(scheduler, *, phase="boot")` · `spawn_funnel_boot_vs_evening(scheduler, *, phase="boot") -> asyncio.Task`. 상수 = `EVENING_POLL_SECS = 30` · `EVENING_START_DEADLINE = timedelta(minutes=15)` · `BOOT_VS_EVENING_TIMEOUT_SECS = 10` · `_WS_WAIT_TIMEOUT_SECS = 120.0`. 스폰한 task 는 모듈 전역 `_BG_TASKS` 가 붙든다. 공개 함수는 전부 **never-raise** 다(호출자가 부팅 경로·task loop 라 하나가 죽으면 전체가 죽는다). 🔴 8영역 import 0 · naive 벽시계 0(가드 `tests/unit/ast/test_cycle364_ast_live_prepare_lock.py`) — 보호 종목도 scanner 헬퍼가 아니라 scheduler 가 가진 registry·`_pending_next_day_clear` 에서 모은다. `scheduler`(TIME 상수·`capture_funnel_snapshots`)와 `trading_calendar` 는 함수 안에서 지연 import 한다. 계약 상세 = 하단 「funnel 스냅샷 캡처」 절.
- **`trading_calendar.py`** — 휴장일 판정 공용 leaf(8영역·`scheduler.py`·`boot_manager.py` import 0). 「몇 시간 지났나」·「달력 며칠 지났나」 대신 「직전·다음 영업일이 언제인가」를 묻는 세 곳이 쓴다 — 부팅 즉시 실행 슬롯 게이트(`task_loop_helper._evaluate_slot_gate`) · 6전략 prepare 의 일봉 신선도 기준(`StrategyBase._resolve_expected_daily_head`) · 저녁 미리보기의 기준일(`funnel_capture.resolve_as_of`·`evening_capture_once`).
  - 메모 = 모듈 전역 dict 에 **True/False 만 영구** 담는다(날짜의 개장 여부는 바뀌지 않는다). 주말(`weekday() >= 5`)은 조회 없이 휴장이다. `_MEMO_MAX_AGE_DAYS`(40일)보다 오래된 키는 **삽입되는 날짜 기준**으로 정리한다 — 벽시계 기준이면 회귀 스위트가 달력이 흐르는 것만으로 붉어진다.
  - **cycle363 F-2(독립 검증 반영)** — `None`(모름)은 영구 캐시하지 않지만 `_NEGATIVE_CACHE_TTL_SECS`(90초) 동안 별도 저장소(`_negative_memo`)에 짧게 재사용한다(같은 CTCA0903R 지연을 반복해서 기다리지 않는다). 조회 자체는 `_LOOKUP_TIMEOUT_SECS`(5초)로 감싼다(`asyncio.wait_for`) — 지연이 부팅 prepare 를 분 단위로 늘리는 것을 막는다. 타임아웃도 never-raise 계약 안에서 「모름」으로 흡수하고 「모르면 실행」 방향은 바뀌지 않는다. `_reset_cache_for_tests()` 는 영구 메모·음성 캐시 양쪽을 비운다.
  - 이 메모가 KIS 공지 「CTCA0903R 은 가급적 1일 1회 호출」(`docs/kis/domestic-stock-industry.md` 국내휴장일조회)을 **날짜당 프로세스 수명 1회**로 지킨다.
- **`daily_emit_cap.py`** — `KstDailyEmitCap` = KST 날짜 경계 자기 리셋(`should_emit`/`mark_emitted(key, *, now=None)`) + `emit_once(key, log_fn, msg, *args, now=None)`(peek → 로그 → mark, `log_fn` 이 예외면 mark 하지 않고 trace). **신규 관측 마커의 표준 진입점**이다. `count_matching(predicate, *, now=None)`(cycle348) = 오늘(KST) 기록된 키 중 `predicate(key)` 가 참인 개수를 세는 **읽기 전용** 메서드다 — 상태를 바꾸지 않고, 세기 전에 `should_emit` 과 같은 날짜 자기 동기화를 먼저 태워 날짜가 바뀐 뒤 전날 키를 세지 않는다(never-raise, 실패는 0). 호출부가 새 가변 모듈 전역 없이 일일 카운트를 얻는 수단이다(소비처 = `observe_macd_stage6` 의 일일 상한). `KstDailyEmitCap` 에만 있고 기반 `DailyEmitCap` 에는 없다 — 기반은 cycle258 K-12 byte 불변 계약이다.
- **`observer_trace.py`** — 관측기 자기 실패 흔적의 단일 정책 leaf. `trace_observer_failure(marker, key, cap=None, *, now=None, dest_logger=None)` = `logger.debug(exc_info=True)` **항상** + cap 이 있으면 `f"{marker} observer_failed key={key}"` WARNING **1회/(marker, key)/일**(실패 cap 키 `marker|key__observer_failed__` — 정상 키와 비충돌), never-raise. 근거 = debug 단독은 도입 이전의 무음과 구별되지 않는다. 실패 흔적 서식은 `observer_failed` 토큰 **하나**다. `dest_logger` 는 호출자 로거 주입용. `src.*` import 는 `daily_emit_cap` 뿐. 미적용 잔존(8영역, 권고만) = `risk.py:244,419` · `scanner.py:388` · `kojiro.py:987`.
- **`uptime_monitor.py`** — 프로세스 가동 하트비트 + 부팅 tick blind 계측. 60초 하트비트(`system_config.set_task_last_success("engine_alive_heartbeat")`, 신규 테이블 0) + 부팅 시 `[tick_blind_boot] downtime_secs=… market_blind_secs=… after_market_blind_secs=… pre_market_blind_secs=…`(평일 09:00~15:30 겹침 — 공휴일 미고려 근사 = 과대계상 보수 방향). **`market_blind_secs > 0` 이면 WARNING** = 장중 다운으로 손절 사각이 실제로 있었다는 실측이다(WARNING/INFO 분기는 이 필드만 본다). **cycle366(P6-b)** — `after_market_blind_secs`/`pre_market_blind_secs`(각각 KRX 애프터마켓 16:00~20:00 · NXT 프리마켓 08:00~08:50 겹침, 참고용)를 같은 줄에 더했다. `market_blind_overlap_secs`/`after_market_blind_overlap_secs`/`pre_market_blind_overlap_secs` 3함수가 공용 코어 `_weekday_window_overlap_secs(start, end, window_open, window_close)` 를 창만 바꿔 재사용한다(리팩토링 — 기존 `market_blind_overlap_secs` 반환값 불변). 배선 = `boot_manager` 갭 보고 1회 + `ensure_heartbeat_loop` idempotent 스폰(자기 종료 루프, scheduler 무접촉). 일일 리포트 metrics `tick_blind` 집계(`_aggregate_tick_blind`, 기존 3키 무변경) + `report_accuracy.{after_market,pre_market}_blind_secs_total`(`_aggregate_extended_blind`, 신규·독립). never-raise 관측 전용. 🔴 WS 재연결 blind 는 stale watcher 소관이다 — 여기서 중복 계측하지 않는다.

### 출처 절: 모듈 맵 › 순수 함수 leaf (DB · HTTP · 시계 미접촉, 8영역 미접촉)

- **`position_exit_lines.py`** — 잔고 화면의 **청산선(손절가·목표가) 해석 단일 진실원**. `resolve_exit_lines(strategies, ticker) -> {strategy_id, stop_price, stop_source, target_price, target_source}` + `build_exit_line_map(strategies, tickers)`. **순수·read-only·never-raise·`await`/DB/HTTP 0** — 전부 in-memory registry 조회다. 손절선은 2단 = `get_effective_stop_price`(보유형 4전략, `check_exit_signal` 과 **동일 산식·동일 상태 소스**) → `hard_pct`(`buy_price × (1 + 하드손절%/100)`). 🔴 **`extract_hard_stop_pct` 의 기본값 −7.0 으로 계산한 숫자를 내지 않는다** — sentinel 을 넣어 **키가 실제로 있을 때만** 값을 낸다(없으면 `None`). 없는 값을 그럴듯하게 만들면 운영자가 설정한 적 없는 손절가를 보고 버틴다. 🔴 **목표가는 전략의 read-only 미러 `get_effective_target_price(ticker) -> (target, already_hit)` 에서만 읽는다** — `get_targets_status()` 는 `_candidates` 를 순회하는데 **보유 종목은 후보 자격을 잃는 것이 정상**이라 그 경로로는 목표가가 **간헐적으로 사라진다**(cycle339 초판 결함 — 실측 09-14~09-21: 036800 은 매수 다음 날부터 **5영업일 내내** 후보에서 빠져 빈 칸, 003160 은 계속 남아 값이 났다). ⚠️ 남아 있는 날에도 값은 **live 재검출 구조** 기준이라 엔진 §3(진입 stamp)과 **갈릴 수 있다** — 「어떤 날은 보이고 어떤 날은 다르다」가 결함의 실제 모양이다. 🔴 **목표가는 `bull_flag_breakout` 의 `measured_target` 하나뿐**이고 그것도 **부분 익절 트리거**다 — ⚠️ **VB·LTV 의 `target_price` 를 목표가로 쓰지 않는다**(그것은 **매수 트리거 가격**이라 이미 산 종목의 목표가 칸에 넣으면 완전한 거짓 정보다). 🔴 **가격 무관 청산은 어느 출처에도 안 담긴다**(VB 15:20 일괄매도 · kojiro stage3 · 익일청산) — 프론트 툴팁이 그 사실을 말한다. 🔴 **`_MODE_DEPENDENT_STOP_STRATEGIES`(= LTV)는 `hard_pct` 근사를 내지 않고 `stop_source="mode_dependent"` 로 둔다** — LTV 는 보유 중 모드가 갈려(당일 `intraday_stop_loss` −5 / 상한가 `overnight_stop_loss` −3.5) `extract_hard_stop_pct` 의 음수 min 이 항상 −5 를 내는데 상한가 모드의 실제 임계는 **−3.5(더 조인다)** 라 운영자가 **1.5%p 여유를 더 있다고 오판**한다(메모리에 박제된 함정). 모드는 `_limit_up_reached` 메모리라 leaf 가 밖에서 판정할 수 없다 — 정확히 내려면 그 전략에 미러를 붙여야 하고 그건 `account_risk_watcher` 의 SOFT 게이트 입력을 바꿔 **`domain-consult` 선행**이다(별건). 보유 전략 미상(수동 매매분)은 전 필드 `None`. 🔴 **`engine_running=False` 면 판정 불가를 `stop_source="engine_idle"` 로 구분한다** — 엔진은 21:30 `_reset_daily_state` 가 메모리 포지션을 비우고 07:45 `_boot()` 가 DB 에서 되살리므로 그 사이 ~10시간은 보유가 있어도 청산선을 알 길이 없다. 「손절선이 없다」와 「지금은 모른다」를 같은 `—` 로 접으면 운영자가 아침에 **손절이 안 걸려 있다**로 읽는다(2026-09-21 23:57 배포 직후 보유 9건 전부 `—` 실측). ⚠️ 판정은 **엔진 상태**(`trading_scheduler.is_running`)로 한다 — 「메모리 포지션이 0」으로 추론하면 수동 매수분만 든 정상 상태가 엔진 정지로 잘못 찍힌다. 소비처 = `routes/balance.py`(graceful — registry 조회 실패해도 잔고는 그대로 나가고 전 종목이 `—`). 회귀 = `tests/unit/engine/test_cycle339_position_exit_lines.py`(31 — 🔴 **후보 표면을 읽으면 붉어지는 양성 대조군** 포함. 돌연변이 실측 = 초판 경로로 되돌리면 5 RED).
- **`param_catalog.py`** — 7 전략 `DEFAULT_PARAMS` 합집합 **105 키의 단일 진실원**, 순수 데이터 leaf(`src.*` import 0 · I/O 0 · 모듈 로드 부작용 0). 킬스위치 `order_exchange_clock_mode`·`after_market_exit_division` 도 여기 있다(`group="time_board"` · `risk="identity"` · `range_src="enum"` · `auto_tunable=False`). 시장 유닛 `market_unit_mode` 도 같은 모양이다(`group="sizing_risk"` · `risk="identity"` · `range_src="enum"` · `auto_tunable=False` · `applies_to` = 터틀 4전략, cycle382). 신규 매수 멈춤 `buy_paused` 는 `group="entry"` · `type="bool"` · `risk="identity"` · `range_src="enum"` · `auto_tunable=False` · `applies_to` = 7 전략이다(cycle384). 키마다 `ParamSpec`(`label_ko`/`group`/`type`/`min`/`max`/`step`/`unit`/`editable`/`risk`/`auto_tunable`/`deprecated`/`deprecated_for`/`range_src`/`pattern`/`choices`/`applies_to`/`help`/**`min_items`**/**`forbidden_choices`**). 🔴 **범위를 지어내지 않는다** — `range_src` ∈ `clamp`(읽는 쪽 하드 클램프 6) · `param_ranges`(`PARAM_RANGES` 원문 복사 24) · `sign`(부호 규약 6) · `structural`(자료형·구조 필연) · `enum`(값 집합) · **`none`(근거 없음 → min=max=None, 8키 — 전부 `deprecated=True ∧ editable=False`)**. ⚠️ 범위를 `PARAM_RANGES` 에서 **파생시키면 그 범위가 실제 운영값을 담아야만 안전**하다 — `max_scan_stocks` 는 cycle278~363 에 `PARAM_RANGES` 상한이 500 인데 bfb·vcp·kojiro 기본값이 4000 이라 파생하면 3 전략이 저장 전면 422 였다(그래서 그때는 `range_src="none"`). **cycle365 P5b(2026-09-25, 사용자 승인)가 `PARAM_RANGES["max_scan_stocks"]` 상한을 4000 으로 올려**(AI 자문이 이 상한 때문에 그 3 전략에 매일 500=유니버스 87% 축소를 권고하던 근본 원인 시정) 7 전략 기본값을 전부 담게 됐고, 지금은 `param_ranges` 로 옮겨 다른 키와 같은 갈래를 탄다. `auto_tunable` 은 `PARAM_RANGES` 를 **그대로 반영**하고 그 집합을 넓히지 않는다(AI 자동 조정 가능성과 사람의 편집 가능성은 별개다). `deprecated`(8, 전부 `editable=False`)는 **숨기지 않고** 회색 배지로 보여 준다 — 값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다. 전략 한정 무효는 전역 플래그가 아니라 `deprecated_for` 다(유일 사례 `k_value_nxt_pre`/`_post` → VB. LTV 는 야간 목표가에 **실제로 곱한다**). `min_items`(list_str 최소 항목 수 — `tradable_boards`=1 · `exclude_tickers`=0)와 `forbidden_choices`(전략별 금지 선택지 — 유일 사례 VB + `post_nxt`, 루트 `CLAUDE.md` 의 'POST_NXT 추가 금지' 를 데이터로 옮긴 것)는 검증과 화면이 같은 근거를 읽게 하려고 카탈로그에 둔다. ⚠️ 빈 목록을 **자료형 단위로** 막지 않는 이유 = 빈 목록의 뜻이 키마다 정반대다(`exclude_tickers=[]` 는 '제외 없음' 이라는 정상 기본값이다). `trailing_stop_rate` 도움말은 **적용 범위**를 명시한다(cycle365 P5a) — momentum·LTV 둘 다 **익일 청산 모드**(갭 ≥ `gap_up_threshold` 유지)에서만 쓰이고 당일 손절에는 쓰이지 않는다(LTV 는 추가로 전일 상한가 도달 종목 한정). 두 자문(주간·20:00)이 이 범위를 몰라 반대 방향으로 같은 오독을 한 것이 계기다.
  > `exchange` 의 `SOR` 은 `Choice(deprecated=True)` + 라벨 `"SOR (폐기 — 주문에 쓰이지 않음)"` 로 어휘에 남아 있다(운영 DB 7 전략은 전부 `NXT`, SOR 잔여 0). 어휘에서 지우는 것은 `test_cycle287_sor_retired.py::test_n3b` 가 강제하는 순서(코드 → D+1 → 카탈로그/프론트 → DB)를 따르는 별도 작업이다. 🔴 `exchange` 는 `editable=True` 로 남는다 — `editable=False` 로 만들면 그 키를 보내는 모든 PUT 이 422 다. `<select>` 의 `<option>` 은 브라우저가 스타일을 제한해 `choice.deprecated` 회색 처리가 닿지 않으므로 **라벨 자체가 유일한 폐기 신호**이고 프론트 회귀 가드가 그 문자열을 봉인한다. 두 PUT 클라이언트(`Settings.tsx`·`StrategyParamsEditor`)는 변경분만 보낸다.
- **`param_validation.py`** — 파라미터 검증 순수 함수(`param_catalog` 만 import). `validate_params(strategy_id, current_params, incoming) -> ValidationResult(errors, warnings, accepted)`. 판정 순서 = 키 존재 → `editable` → 자료형 → `choices`/`pattern` → 금지 선택지(`forbidden_choice`) → min/max · 최소 항목 수(`too_few_items`) → 예산 불변식(병합 결과) → 순서 불변식(경고). 🔴 **첫 오류에서 멈추지 않는다** — 한 저장에 여러 필드를 고치는 화면이라, 멈추면 운영자가 오류를 하나씩 왕복하고 그 왕복마다 all-or-nothing 이 다시 걸린다. 예산 불변식 `position_ratio × max_positions <= 1.0` 은 EPS=1e-9 로 경계 1.0 을 **통과**시키고(7 전략 중 6 전략 기본값이 정확히 1.0), **이미 위반 중인 상태를 악화시키지 않는 편집은 통과 + `budget_invariant_preexisting` 경고**다(막으면 그 전략이 영구 편집 불가 = 복구 수단이 DB 직접 UPDATE 뿐이다). 빈 `tradable_boards` 는 **422** 다 — 효과가 전략마다 정반대라(momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS` 폴백으로 매수를 계속하고, BFB·VCP·kojiro 는 공집합 = 매수 전면 중단) 어느 쪽도 운영자의 의도가 아니고, 매수를 멈추는 정당한 수단은 `buy_paused` 다(전략 비활성화는 보유분의 손절까지 멈춘다 — 루트 금기). VB + `post_nxt` 도 **422**. ⚠️ `applies_to` 는 PUT 의 관문이 **아니다**(의도된 fail-open) — 미지 키 판정이 `key in current_params` 라 DB 드리프트로 들어온 소관 밖 키는 저장된다. 그 전략이 읽지 않는 키라 매매 영향이 0 이고, 조이면 비상 `curl` 롤백 경로가 좁아진다. 소비처 = `routes/strategies.py::update_params`. AI 자문 수동 적용 경로(`routes/recommendations.py`)는 아직 이 함수를 거치지 않는다 — 검증 비대칭이 남아 있다.
- **`param_drift.py`** — 운영 DB params ↔ 코드 `DEFAULT_PARAMS` 드리프트 **관측 전용** 순수 함수 leaf(`src.*` import 0 · I/O 0). 왜 있나 — `_load_strategy_config` 가 DB params 를 키별로 덮으므로 한 번 박힌 DB 값이 계속 살고, 코드 기본값만 읽으면 운영값을 오판한다(LTV 상한가 손절을 코드값으로 읽어 반대 방향으로 보고한 사례). `collect_param_drift(strategies) -> list[{strategy_id, key, live, code}]` — 실행 params(`config.params`) 와 `DEFAULT_PARAMS` 를 키별로 비교한다. 수치는 `4` 와 `4.0` 을 같다고 보고(`_same`, 오차 1e-9), bool 은 `is` 로 비교한다. **코드에 없는 키는 차이로 세지 않는다**(운영 전용 키를 세면 매일 경고가 나 배경 소음이 된다). 판정 불가·예외는 조용히 건너뛰고 예외를 올리지 않는다. 소비처 = `boot_manager.boot` 가 `_load_strategy_config` 직후 1회 부른다 — 차이가 있으면 `[param_drift] count=N` WARNING(예시 5건), 없으면 INFO, 호출 실패는 `logger.exception` 후 부팅 계속. 🔴 **값을 바꾸지 않는다** — DB 가 정본이고, 차이 대부분은 운영자가 의도로 넣은 값이라 코드값으로 되돌리는 것이 곧 사고다. 회귀 = `tests/unit/engine/test_cycle326_param_drift_visibility.py`.
- **`backtest_yaml.py`** — 6 전략 → 외부 MCP 백테스트 서버 YAML DSL 변환. 소비 = `backtest_engine.py`(20:00 자문 직후 12 job fire-and-forget) + `routes/backtest.py`. 매매 hot path 무관.

### 출처 절: 모듈 맵 › 시세 채널 (통합 채널 소멸 후)

- **`tick_channel_mode.py`** — 채널 리졸버 **킬스위치 모드 leaf**. `system_config.tick_channel_resolver_mode` 한 키가 정본이고 값은 `off`(전 종목 통합 채널 `H0UNCNT0` — 롤백 위치) / `observe`(판정만 로그, **배포 기본값 = 행위 0**) / `enforce_low`(LOW 후보만 전용 채널, HIGH 제외) / `enforce`(전면). API = `current_mode()`(동기, hot path) · `refresh_mode()`(async) · `apply_mode(mode)`(라우트용 즉시 메모리 반영) · 테스트 seam 2. 🔴 `refresh_mode()` 에 프로세스당 1회 래치를 두지 않는다 — 래치가 있으면 킬스위치가 아니다. 🔴 **장중에 닿아야 한다** — D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지) 때문에 "다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다. 즉시 경로 = `PUT /api/realtime/tick-channel-mode {"mode":"off"}`(DB 저장 + **같은 요청에서** 메모리 값까지 덮는다). 폴링 백업 2곳 = `scanner.subscribe_filtered_stocks`(5분) · `stale_watcher_core.check_and_resubscribe_stale`(120초). 실패 방향 = DB 조회 실패·키 부재·미지 값 전부 **현재 값 유지**(기본값 되돌림 금지 — 운영자가 `off` 로 내려놓은 뒤 조회가 한 번 실패했다고 다시 켜지면 안 된다) + 미지 값은 `[tick_channel_mode_invalid]` WARNING. 시각 리터럴 0건. ⚠️ **`off` 가 즉시 되돌리지 못하는 것** — 장중 전환 금지 규약 때문에 이미 전용 채널에 올라간 종목은 다음 `_boot`/재구독까지 그 채널에 남는다(매수 축 게이트는 그 사실을 읽으므로 계속 닫혀 있다). `system_config` 헬퍼는 `src/db/system_config.py`.
- **`tick_channel_clock.py`** — 채널 **시각축 판정 leaf**. 동기·순수·never-raise, `await`/DB/HTTP 0(AST G-294-14). 프리장은 `H0NXCNT0`, 정규장+애프터는 `H0STCNT0`, 전환은 하루 **1회**. API = `_windows(on_date)` → `(krx_regular_open, nxt_pre_end, krx_continuous_end)` · `switch_at(on_date, *, offset_secs)` · `clock_channel(now, *, offset_secs)` → `(tr_id, reason)` · `set_day_revert()`/`day_reverted()`(자동 원복 래치, 벽시계 날짜 경과 시 자기 해제 — **시계를 못 읽는 경로에서도 날짜 키가 비면 안 된다**: 비면 리셋 조건이 영원히 거짓이라 영구 좌초다) · `switch_windows()`/`active_switch_window()` · 관측 `emit_clock_config()`/`note_pre_window_frame()`/`emit_pre_window_frame_summary()` · `reset_state_for_test()`. 표 파생값은 **날짜 키로 메모**한다(`risk.on_tick` 이 코호트 종목마다 부르는 경로다). 🔴 **시각 리터럴 0건이 계약이다** — 경계 셋이 전부 `market_state.get_market_table(on_date)` **공개 API** 파생이다(`MARKET_TABLE` 직접 순회 금지: `effective_from`/`effective_to` 해석기 `_is_effective` 가 private 이라 빠뜨리면 09-13 이전 날짜에서 20:00 이 나와 거짓이 된다). `krx_continuous_end` 는 `phase` 가 아니라 **`match_kind == "continuous"`** 로 고른다 — `phase` 면 `REGULAR`(15:20)와 `AFTER_MARKET`(20:00)을 둘 다 열거해야 하고 KRX 가 연속 구간을 또 신설하는 날 그 열거가 조용히 낡는다. 전환 시각 = `clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`(offset 기본 300초). 전환 허용 창은 `pre_to_krx` **하나**다 — 15:40~16:00 NXT 단독 연속 구간에서 `nxt_true` 보유의 KRX 채널 커버리지 공백은 2026-09-15 사용자 결정 「15:30~16:00 완전 휴식」(그 구간 주문 0)이 **수용한 비용**이다. 되살리려면 `_workspace/00_URGENT_WORKLIST.md` 의 그 결정을 먼저 뒤집어야 한다. `clock_channel` 은 `priority` 키워드를 받지만 **판정에 쓰지 않는다**(제거하면 `scanner.py` 8영역 연쇄 변경이라 인자만 남겼다). `system_config.tick_channel_gap_hold_enabled` 는 소비처 0 인 폐기 키다(cycle295) — **그 키 이름을 재사용하지 않는다**(DB 잔존 행은 무해). 🔴 **통합 채널을 절대 반환하지 않는다** — 판정 실패(L1)의 폴백도 `H0STCNT0` 다(실측 확정 채널 · 구독 수명의 92% 가 KRX 창 · 셋 중 **모의(VTS) 지원은 그것뿐**). "구독을 안 한다" 방향으로는 가지 않는다. 통합은 `scanner.tick_tr_id_for` 의 킬스위치 `off` 분기에서만 나온다.
- **`tick_channel_switch.py`** — 살아 있는 구독의 **채널 전환 + 자동 원복 leaf**. `run_switch_cycle(scheduler, pool, *, now)` 가 120초 `stale_watcher_core.check_and_resubscribe_stale` 안에서 불린다(**never-raise** — 전환 실패가 4중 안전망의 한 축을 끊으면 안 된다). 🔴 **창 밖 전환 금지** — 전환 창 `[switch_at, krx_regular_open)` 안에서만 옮긴다. 근거 셋이 그 창에서만 동시에 성립한다: ① 그 창에만 프레임이 구조적으로 0(NXT 휴장 + KRX 시가 단일가)이라 이중 채널 창의 `tick_volume` last-write-wins 비결정론이 노출되지 않는다 ② 주문이 0건이다 ③ 못 옮겨도 blind 가 아니다(미전환 잔여는 NXT 에 남고 NXT 는 정규장·애프터에 체결을 싣는다). 트리거가 이 루프 하나뿐인 이유 = `_scan_loop`(300초)은 `TIME_SCAN_START` 에 생성돼 **아침 전환 창에 존재하지 않는다**. HIGH(보유·익일청산) = **make-before-break**(신 채널 SEND → ACK 확인 = `(new, t)` 가 `_subscriptions` **와** `_subscriptions_acked` **두 집합**에 있는가 → 구 채널 해제. `_subscriptions` 만 보면 SEND 직후 무응답을 성공으로 읽는다. ACK 실패는 신 채널만 즉시 회수하고 구 채널을 유지하며 전환 예산을 소모하지 않는다), LOW = break-before-make. 🔴 **세션 재추첨 금지** — `websocket_pool.switch_channel_same_session` 은 `_ticker_to_session` 을 **읽기만** 한다(다른 세션에 떨어뜨리면 그 dict 가 덮여 구 세션 튜플이 영구 고아로 41 슬롯을 잠식한다). **자동 원복** = `krx_regular_open + revert_probe_secs`(기본 180 = `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용, 재정의 금지) 시점 판정이고, 표본은 **지금 KRX 전용 채널에 앉은 HIGH 전부**(`nxt_false` 보유 포함)다. 교차 확인은 비교 코호트가 전부 침묵이면 **비결론**으로 두고 2×probe 뒤 escalation 한다(3단계 정상 상태가 "전 종목 같은 채널" 이라, 전원 침묵을 결론으로 삼으면 진짜 고장에서만 발화하지 못한다). `_revert_probe_done` 은 **결론적 판정에만** 세운다(상한 `MAX_REVERT_PROBE_ATTEMPTS=10`). 되돌림은 **make-before-break** + `tick_channel_clock.set_day_revert()` + `[tick_channel_auto_revert] n= reverted= failed= …` **ERROR** 1행(ERROR 인 이유 = `pattern_by_level` 이 WARNING 이상만 21:30 리포트 `top_patterns` 에 넣는다). 되돌림은 "전원 NXT" 가 아니라 **프리 창 규칙**이다 — 단순 전원 NXT 면 `nxt_false` 가 새 blind 가 된다. **그날 재시도는 없다.** 전체 침묵(`cross_fresh < 2`)은 채널이 아니라 세션·시장 문제라 기각한다. 다이얼 **4키** = `tick_channel_switch_enabled`(전환만 끈다) · `tick_channel_switch_offset_secs` · `tick_channel_switch_ack_timeout_secs` · `tick_channel_revert_probe_secs` — 전부 `system_config` 축이고 `PUT /api/realtime/tick-channel-mode` 의 선택 필드 `switch_enabled` 로 즉시 끌 수 있다(폐기된 `gap_hold_enabled` 필드를 보내면 **422 가 아니라 조용히 무시**된다 — cycle295). 🔴 창 밖 금지는 **창 안에서도 종목마다 재확인**한다(경과는 벽시계가 아니라 `now` + monotonic). 전환 대상에서 진단 프로브 튜플과 비-TICK 라우팅(체결통보 등)을 제외한다 — 없으면 `wanted` 가 항상 전용 TICK 이라 체결통보 구독까지 전환 대상이 된다. LOW 전환 실패는 `_ticker_to_session`/`_ticker_to_tr_id` 를 **동행 pop** 해 다음 사이클이 재구독하게 한다(안 하면 세션 튜플 0 + 라우팅 잔존 = 20:00 까지 자가 치유 없는 구독 좀비다).
- **`no_feed_registry.py`** — `nxt_tradable=False` 종목 집합 leaf. `ensure_fresh(tickers, *, ttl_secs=600)` 이 `stock_master.get_nxt_tradable_map` 1회로 집합을 적재한다(ttl 경과·미지 ticker 유입 시 전체 재조회, 예외 시 이전 집합 유지 + `[no_feed_registry_refresh_failed]` 1회/일 + 다음 호출 재시도, `None` = 마스터 부재는 no_feed 아님). 그 밖에 `is_no_feed(ticker)` · `is_provenance_ok(ticker)`(그 행 raw 에 KIS `cptt_trad_tr_psbl_yn` 키가 있는가 = 값의 출처가 권위 있는가 — `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 도장하는 창에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어, 도장값을 그대로 믿으면 진짜 NXT 종목을 프리장 무체결 채널로 보낸다) · `is_classified(ticker)`(분류한 적 있는가 — `is_no_feed` 의 "모르면 False" 는 **미지**와 **송출 정상**을 같은 값으로 접는다. `is_no_feed` 의 극성은 건드리지 않았다) · `snapshot()` · `reset_state_for_test()`. 🔴 출처 조회 `get_nxt_provenance_map` 은 `get_nxt_tradable_map` 과 **독립 try** 다 — 한 try 로 묶으면 출처 쿼리가 실패하는 날 churn 차단까지 함께 죽는다. 소비처 2 = `stale_watcher_core.check_and_resubscribe_stale` + `scanner._classify_channel`. 🔴 **구독 전에 덥혀야 한다** — `scanner.subscribe_filtered_stocks` 가 리졸버를 부르기 **전에** 그 사이클 대상 전체로 `ensure_fresh` 를 부른다(AST 가드 A22 가 순서를 잠근다). 안 덥히면 아직 구독하지 않은 후보는 원리상 분류될 수 없어 07:59 사전 구독 코호트 전체가 판정 불가로 빠진다. scheduler/scanner/realtime/registry import 0(AST G-252-1).
- **`tick_volume.py`** — 실측 누적거래량 관측 leaf. WS payload `[13] ACML_VOL` → `handler._parse_acml_vol` → `on_tick(*, acml_vol=)` → `record_acml_vol`(last-write-wins) → BFB·VCP 거래량 게이트가 읽는다. 🔴 **`acml_vol` 은 채널마다 따로 쌓인다 — 채널이 다른 두 값을 비교·합산하지 않는다**(2026-09-14 라이브 실측: 같은 `000660` 이 `H0STCNT0` 16:41 에 3,773,544, `H0NXCNT0` 19:55 에 1,981,520). 채널 전환 뒤 첫 프레임이 새 채널 누적으로 덮는 것은 의도한 동작이다(KRX 거래량 게이트는 KRX 누적을 봐야 한다). 전환이 안전한 전제는 전환 창에 프레임이 구조적으로 0 인 것과 이중 채널 구독 금지 둘이다 — 하나라도 깨지면 last-write-wins 가 두 누적을 번갈아 쓰는 비결정론이 된다.

### 출처 절: 모듈 맵 › VI · 장운영 채널 (H0UNMKO0)

- **`market_operation_monitor.py`** — H0UNMKO0 **수신·상태 추적**. `handler._handle_market_op` → `record_market_op_event(MarketOpEvent)`. 파싱과 칸 기준점은 `src/api/market_operation.py` 가 정본이다(`src/api/CLAUDE.md` 해당 절). 상태는 **5개**이고 서로 합치지 않는다 — `_vi_active_tickers`(VI 활성 집합) · `_halt_active_tickers`(거래정지 활성 집합) · `_market_op_last_event`(종목별 마지막 이벤트) · `_vi_last_active_at` · `_halt_last_active_at`(각 수명 전용, ticker → 마지막 활성 시각). 두 수명 dict 는 **서로 독립**이다 — VI 타이머가 만료돼도 거래정지 타이머는 그대로다(「멤버십」과 「마지막 활성 시각」을 한 자료구조에 넣지 않는다). **판정** — VI 활성 = `_is_code_active(vi_cls_code) or _is_code_active(ovtm_vi_cls_code)`. 거래정지 활성 = `trht_yn.upper() == "Y"` **또는** `is_iscd_stat_blocking(iscd_stat_cls_code)`(종목상태 `58` 하나, 2026-09-25 사용자 결정). **수명** — 해제 프레임이 늘 온다는 보장이 없어서 둘 다 수명을 둔다. 마지막 활성 프레임 뒤 `VI_ACTIVE_TTL_SECONDS`(600초, 사용자 결정 「10분 뒤 자동 해제」) · `HALT_ACTIVE_TTL_SECONDS`(600초, 메인 세션 결정 — 사용자 승인 범위 안)가 지나면 해제 프레임 없이도 푼다. 매 활성 프레임이 시각을 갱신하고, 명시 해제 프레임(비활성)은 수명을 기다리지 않고 즉시 푼다. 로그는 `[market_op_vi_release] ticker=…` / `[market_op_halt_release] ticker=…` 이고 수명 해제만 뒤에 `reason=ttl` 이 붙는다. 부팅 REST 시드 `seed_vi_active_from_rest` 도 시드 시각을 마지막 활성으로 찍는다(장중 재기동이면 이미 풀린 종목까지 들어오기 때문). 활성 집합에 있는데 시각이 없는 종목은 **발견 시각**을 찍고 그로부터 600초 뒤 푼다 — 무기한 유지하지 않는다. **만료 sweep 은 지연 평가**다(백그라운드 task 없음). `_expire_stale_vi()`/`_expire_stale_halt()` 를 `record_market_op_event` **첫머리**와 읽기 함수들이 먼저 부른다 — VI 는 `is_ticker_stale_excluded` · `get_market_op_active_tickers` · `get_vi_active_tickers` · `get_market_op_state_summary`, 거래정지는 그 넷에서 `get_vi_active_tickers` 대신 `get_halt_active_tickers` 에 `get_circuit_breaker_state` 를 더한 다섯이다. 🔴 sweep 을 `record_market_op_event` 의 기록 **뒤**로 옮기지 않는다 — 만료된 에피소드 위에 온 해제 프레임이 「프레임 해제」로 잘못 적히고(TTL 해제 로그 누락), 만료 뒤 새 활성 프레임이 「갱신」으로 뭉개져 새 에피소드 로그가 사라진다. `reset_market_op_state()` 가 다섯 상태와 CB 1회/일 cap 을 함께 비운다. 가드 = `test_cycle149_ast_dict_separation.py`(앞 세 dict 분리) + `tests/unit/realtime/test_cycle368_market_op_decisions.py`(수명 V·L·T 묶음, sweep 순서 R 묶음, 판정 S·D 묶음). `is_ticker_stale_excluded(ticker)` 를 `stale_watcher_core` 의 두 경로(`check_and_resubscribe_stale` 120초 · `resubscribe_stale_priority` 5분)가 소비한다(VI·거래정지 종목 stale 회피). `get_circuit_breaker_state()` = **관찰 전용 휴리스틱**(거래정지 사유 `_CB_REASON_KEYWORDS` 매칭 **또는** `halted >= _CB_MIN_HALTED(5) ∧ halted/observed >= _CB_HALT_RATIO(0.8)`, `representative_mkop_cls_code`=005930, `halt_reasons_sample`) + `get_market_op_state_summary()`(`circuit_breaker` + `iscd_stat_active_count` — **표시 집합** `_ISCD_STAT_DISPLAY_CODES = {"51","52","53","54","58","59"}` 멤버십으로 `_market_op_last_event` 를 센다. 55·57·00·빈값은 정상 상태라 세지 않는다) + `[market_op_cb_suspected]` INFO 1회/일(`reset_market_op_state` 동행 reset). KIS H0UNMKO0 에 CB 전용 필드가 없어 휴리스틱 + 계측이 먼저다. 소비 = `GET /api/realtime/market-operation` → RealtimeHealth 카드. 🔴 **매수 가드 미연계(표시 전용)** — `risk.on_tick` 참조 0. 관리종목(51)·단기과열(59) 청산·당일 매수 차단은 이 모듈이 아니라 `status_exit_watch.py` 가 REST 로 판정한다 — 그 leaf 는 `get_last_event(ticker)` 를 **힌트로 읽기만** 한다(51·59 가 이 프레임으로 온 실측이 없다). 송신·구독 배치는 형제 모듈이 맡는다.
- **`market_op_subscribe.py`** — 종목별 H0UNMKO0 구독 **송신·배치 본체**(`subscribe_market_operation_tickers(scheduler)`). `scheduler.py` 에는 5줄 위임 wrapper `_subscribe_market_operation_tickers` 만 있고 호출부는 `_scan_loop` 다(`scheduler.py` 를 grep 하면 wrapper 만 나온다). 규약 = HIGH(보유+익일청산)만 · **메인 세션 0건** · `bypass_limit=False` 명시 · 보조 세션 **직접** 라운드로빈(풀 API 미경유 — tr_key 단일 키 라우팅 오염 방지) · `_market_op_subs` **델타** 해제(슬롯 누수 차단) · 소켓 `State.OPEN` 가드(미개방이면 사이클 skip + `[market_op_subscribe_skip]`) · `ConnectionClosedError` 는 break + WARNING 1행 · `asyncio.sleep(0.05)` Rate Limit · 보조 만석이면 `[market_op_subscribe_no_slot]` WARNING(**메인 폴백 금지** = tick > VI 라는 명시적 교환) · `[market_op_subscribe_summary]` main_tick/main_total/main_over 5분 계측. 🔴 **함수-로컬 import 5줄**(`ConnectionClosedError`/`State`/`MARKET_OP_TR_ID`/`MAX_SUBSCRIPTIONS` + `kis_ws`←`websocket` / `kis_ws_pool`←`websocket_pool`)을 **모듈 최상단으로 올리지 않는다** — 회귀 4파일이 정의 모듈의 속성을 monkeypatch 하는데 함수-로컬 import 는 매 호출 재실행돼 그 patch 가 걸린다. 올리면 이름이 import 시점에 바인딩돼 patch 가 무력화되고 `_ws is None → return 0` 조기 반환이 부정 단언을 조용히 초록으로 만든다. 🔴 **두 줄 분리도 유지한다** — 합치면 매 호출 ImportError 로 구독이 전량 미실행된다(2026-07-24 사고). 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정 — 마커 5종(`[market_op_subscribe_skip]`/`[market_op_no_quote_session]`/`[market_op_subscribe]`/`[market_op_subscribe_summary]`/`[market_op_subscribe_no_slot]`)이 전부 기존이라 이름이 갈리면 `_DbLogHandler` 가 적는 `system_logs` 접두가 바뀌어 운영 grep 사슬이 끊긴다. 본체가 이 leaf 에 있는 이유는 `scheduler.py` 라인 상한(cycle257 영구 상한 **<3,900**)이다. 가드 = `test_cycle292_ast_market_op_leaf.py` + 재조준된 `test_cycle221_ast_market_op_no_main.py`·`test_cycle214_ast_h0unmko0_pool.py`·`test_market_op_subscribe_import_path_guard.py`·`test_market_op_subscribe_socket_guard.py`(넷 다 부정 단언이라 **양성 대조군**을 함께 심었다 — 본체가 사라져도 초록이 되는 공허 통과 차단).

### 출처 절: 모듈 맵 › 계좌 리스크 · 관측기

- **`account_risk_watcher.py`** — 계좌 Σ오픈리스크 감시자(scheduler 무접촉 자기 종료 루프). `run_account_risk_watch_once(scheduler)` = `registry.all()` + `get_balance()` net + 전략 `get_effective_stop_price` 를 `portfolio_risk(stop_price_of=)` 로 주입 → 척도 병기 스냅샷 → guard 판정 → 순간 게이트. 🔴 **프록시 대체 금지, 병기가 계약이다** — 실효 척도도 갭 관통 손실은 못 잡는다. 배선 = boot 동기 1회 + `ensure_watch_loop` 5분(`_running` False 면 ≤60s 종료, done_callback `[account_risk_watch_loop_died]` WARNING / `[account_risk_watch_loop_exit] reason=running_false` INFO = liveness 표본). 호출은 항상 `run_account_risk_watch_once_guarded`(`asyncio.wait_for`, `_EVAL_TIMEOUT_SECS=300`, 런타임 부등식 `0 < T <= _WATCH_INTERVAL_SECS < _GATE_STALE_MAX_SECS`) 를 거친다 — **TimeoutError 만** 포착해 `_gate_active=False` + 스탬프 + `level=error reasons=[timeout]` + `[account_risk_eval_timeout]` WARNING 1회/일(**0건이 정상** — 1건이라도 있으면 그 자체가 hang 실측)이고 `CancelledError` 는 그대로 전파한다. **신선도 계약** = `is_soft_gated()` 는 `_gate_active` 이고 마지막 평가 monotonic 경과가 `_GATE_STALE_MAX_SECS`(= 3 × 주기 = 900s, 리터럴 금지 G-239-1) 이하일 때만 True 이며, 초과(stale)·미평가·판정 예외는 전부 **fail-open(False)** + `[account_risk_gate] released reason=stale` 1회/일이다. `get_gate_state()` 는 `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 4키를 더하되 `level` 은 마지막 평가값을 보존한다(동결 서명 = `level=block ∧ stale ∧ !effective_gated`). fail-open 은 **LOUD** 다 — 평가 실패는 `[account_risk_watch_failed]` WARNING 1회/일이고 활성 중 실패면 `released reason=eval_failure`, 타임아웃이면 `released reason=eval_timeout`(둘 다 cap 밖)이다. 🔴 `gate_stale` cap 키는 `gate_block`/`watch_failed` 와 절대 공유하지 않는다. 🔴 단일 기록자 계약 — read 함수에 `global` 금지(G-239-4), `_gate_active` 대입과 스탬프 사이 `await` 0(G-239-5). 마지막 평가 스탬프는 `_evaluated_mono`(성공·실패 공통, `_now_mono` seam)다. `get_gate_snapshot()`(9키 = `get_gate_state()` 8키 + `eval_timeouts_today`) **하나**를 일일 리포트(`portfolio_risk_snapshot.account_gate`, `over_cap` 과 독립 try, `is_soft_gated` 호출 금지 — read 경로가 stale cap 을 선소비하면 안 된다)와 `/api/portfolio/risk`(프론트 `PortfolioRiskCard` 배지)가 공유한다. 로그 = `[account_risk_gate] transition=entered|reconfirm|released` + `[account_risk_watch]` warn/ok(1회/일), 순서는 peek → 로그 → mark. **D1 이원화** — 전략별 일일손실 플래그는 절대 건드리지 않는다(AST G-4 토큰 0 봉인). 소비처 = `StrategyBase._account_soft_gate_blocked`(폴·래치형 5전략은 `check_buy_signal` 첫 문장 / momentum·VB 는 **발사 직전** — 최상단이면 block 구간에 baseline 이 동결돼 해제 후 거짓 돌파가 난다). 🔴 청산·손절 경로는 구조적으로 차단 불가능하다. 운영 복구 = `POST /api/trading/restart`.
- **`kojiro_band_observe.py` — `observe_macd`(cycle340, 대순환 MACD shadow)** — 원전 `docs/trading_base/이동평균선과MACD.md` §7 의 MACD(상·중·하) 상태를 `[kojiro_macd_observe] ticker= role= stage= gc3= bars_since_gc3= m1..m3= s1..s3= hist3= m{1,2,3}_up= all_macd_up= rule6= rule5= rule4=` 로 남긴다(관측 전용, 행위 0). 행 계약 = 12원소 튜플. 🔴 **WARNING 이다** — INFO 는 21:30 `top_patterns` 에 안 오르고 retention 2일이라 표본이 쌓이기 전에 지워진다. 값은 `_num`(소수 2자리 고정·비수치·NaN·inf 는 `-`)으로 **파싱 계약**을 고정한다(`_fmt` 는 `2.5`/`2.50` 을 섞고 비수치를 흘린다). cap 키는 `(ticker, "macd:"+role)` 로 band 관측과 **슬롯을 다투지 않는다**. **배선은 cycle344** — `kojiro.prepare()` 가 `_macd_observe_row(enriched, stage)` 수집 2곳(보유 stamp 직후 · `rank_raw` 확정 직후) + `observe_band` 다음 emit 1곳으로 부른다(`enriched` 에 재료가 다 있어 **추가 I/O 0**). 🔴 **`gc3` 는 상태가 아니라 교차 사건**(직전 봉 `macd3 ≤ sig3` ∧ 이번 봉 `>`)이다 — 실측이 그렇게 셌고 `rule6/5/4` 가 그 값을 그대로 쓴다. 상태(`m3 > s3`)로 바꾸면 교차 다음 날부터 며칠씩 참이라 규칙 발화가 부풀어 표본이 실측과 갈린다. 🔴 **emit 은 `observe_band` 와 별도 `try` + 전용 흡수기 `absorb_macd_call_failure`** — `absorb_band_call_failure` 재사용은 MACD 고장을 밴드 고장으로 기록하는 오귀인이다(`test_g344_12` 봉인). `_macd_observe_row` 는 `prepare` 의 ticker 루프와 같은 try 스코프라 **never-raise**(컬럼 부재·비수치는 폴백 튜플). 실측 = `_workspace/domain_consult/cycle340_kojiro_macd.md`(962종목 — 선행 중앙값 9영업일, 국면 조건 병용 시 거짓 신호 34%→10%, 다만 **빈도 0.32/일**이라 기존 후보를 밀어낸다). 회귀 = `tests/unit/engine/strategies/test_cycle344_kojiro_macd_wiring.py`(18, 돌연변이 7종 KILL 실측).
  **role 은 3종이다(cycle348)** — `held`(보유 stamp 직후) · `candidate`(strict entry 최종 후보, 위 두 role 은 `_macd_observe_row` 만 호출) · `stage6_gc`(step6 직후 = ATR 밴드 통과 ∧ 스테이지 판별 가능한 **모든** 종목 중 국면6 ∧ 마지막 봉 gc3). `stage6_gc` 는 cycle346 이 발견한 B6 규칙(ATR 밴드 ∧ 국면6 ∧ gc3)의 실매매 유니버스 표본을 얻으려는 것 — strict entry(국면1)를 못 넘는 국면6 종목은 held/candidate 어느 role 로도 안 남기 때문이다. 수집 = `KojiroStrategy._stage6_gc_observe_row(enriched, stage, bar_date, prev_close, atr_val)`(step6 직후·보유 stamp 앞, `stage != 6` 이면 `_macd_observe_row` 를 **부르지 않는다** — 국면6 만 추가 계산). 반환 = `_macd_observe_row` 의 12원소 + `(bar_date, prev_close, atr_val)` = **15원소**, `gc3` 가 아니면(교차가 아니라 상태이거나 국면≠6) `None`. emit = `observe_macd_stage6(macd_s6_raw)` — `observe_macd` 호출 **다음**·`_scanned_tickers` 대입 **앞**에 **별도 try**(흡수기는 같은 `absorb_macd_call_failure`, M8 — `observe_macd` 와 같은 try 에 합치면 한쪽 실패가 다른 쪽 표본까지 삼킨다). 행 서식은 `held`/`candidate` 와 **같은 필드·같은 순서** + 끝에 `bar=<YYYYMMDD> close=<int> atr=<소수2자리>`(`close` 는 `_int_or_dash`, 비수치는 `-`). cap 키 = `(ticker, "macd:stage6_gc")` — 다른 두 role 슬롯과 안 다툰다. **일일 상한 `STAGE6_GC_DAILY_LIMIT`(60)** — 새 가변 모듈 전역을 두지 않고 `_cap.count_matching(...)` 으로 그날 이미 emit 된 `(ticker,"macd:stage6_gc")` 키 수를 세어 판정한다. 초과분은 종목당 기록하지 않고 배치 끝에 요약 1행(`[kojiro_macd_observe] role=stage6_gc cap_reached=1 limit=60 suppressed=N`, 별도 cap 키 `("-","macd:stage6_gc:summary")` 로 하루 1회). 수집 헬퍼·leaf 어느 쪽이 실패해도 held stamp·step7 탈락·후보 등록 등 매매 산출은 **완전 동일**(자기 try 이중 방어). `stage6_gc` 표본을 읽을 때 넷을 안다 — (a) **운영 100봉 창으로 계산한 B6 다** — `prepare` 는 종목당 최근 100봉(`KOJIRO_FETCH_DAYS`)으로 EMA·MACD 를 새로 계산하므로 창 앞머리의 시드 차이로 gc3·국면6 판정이 뒤집힐 수 있고, 전체 이력으로 계산한 cycle346 스크립트와 사건의 약 9% 가 갈린다(합성 가격 경로 실측 — 전체 이력 사건 121 중 11 이 창에서 빠지고 창에만 있는 사건이 12, ATR 밴드는 뒤집히지 않았다). 두 표본을 한 표로 합치지 않는다. (b) **보유 중인 국면6 ∧ gc3 종목은 두 줄에 기록된다** — `role=held` 와 `role=stage6_gc`(cap 슬롯이 달라 서로 막지 않는다). (c) **마커 전체 줄 수·`rule6=1` 합계에 `stage6_gc` 가 섞인다** — `[kojiro_macd_observe]` 를 세거나 `rule6=1` 을 합산할 때는 반드시 `role=` 로 나눠 집계한다(`stage6_gc` 행은 정의상 국면6 ∧ gc3 라 3 MACD 가 모두 우상향이면 곧 `rule6=1` 이다). (d) **예상 기록량 = 하루 0~5줄, 평균 약 0.3줄**(최근 60영업일 운영 일봉 재현, `_workspace/domain_consult/cycle348_stage6_volume_probe.py`) — 상한 60 은 안전 여유이지 예상치가 아니다. 회귀 = `tests/unit/engine/strategies/test_cycle348_kojiro_macd_stage6.py`(54) — 매매 무변경은 차분이 아니라 확장 전 코드(`2087ad3`)로 도출한 **골든**(stats 전체·키 집합·스캔 순서·후보 키·funnel 9단계)과의 완전 일치로 잰다(차분 비교는 수집 `try` 바깥 돌연변이를 양쪽이 공유해 못 잡는다). 돌연변이 15종 KILL 실측.

### 출처 절: 모듈 맵 › 행위 leaf

- **`open_price_rest.py`** — VB·LTV `main` 목표가 기준가를 KRX REST 로 확정한다. 좁은 목 `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")` — `reject_untrusted_main_basis(params, board, source, …)` 가 `board=="main"` ∧ `source ∉ ("rest",)` ∧ `resolve_mode(params)=="enforce"`(전략별 `DEFAULT_PARAMS["open_price_scope_mode"]`, 기본 `enforce`, `"off"` 만 롤백)일 때 조용히 거부한다. 🔴 `source` 기본값이 불신 `"ws"` 라 WS 3 호출부(스케줄러 1차 폴링·전략 인라인 확정)는 한 글자도 바뀌지 않는다(`_STRATEGY_PINS` 6개 불변). 일정(`round_schedule()` 순수 함수) = 09:00:35 R1 → 30초 간격 **fast 19라운드**(마지막 09:09:35) → 300초 간격 slow 라운드 15:20 까지(slow 라운드 대상은 `_pending_main_tickers` 뿐이다). `main_rest_basis_task_loop(sched)` 가 `run_main_rest_basis_round(sched, round_no=, total_rounds=, kind=)` 를 호출한다. 대상 `select_strategies(registry)` = `main ∈ tradable_boards ∧ mode=="enforce"`(`config.enabled` 미고려 — 비활성 전략으로도 REST 확보·게이트·부하를 검증한다). 종목 간 `sleep(0.05)`, 라운드 벽시계 상한 45초(`truncated=1`). 확정 시 `on_open_price_confirmed(..., source="rest")` **와** `open_price_observe.mark_confirmed_via_rest` 를 둘 다 부른다. `owns_board(strategy, board, *, now=None)` = `board=="main" ∧ mode=="enforce" ∧ now < 09:05:00`(예외 fail-open False) — 그 창 동안 `scheduler._confirm_breakout_open_prices` 는 그 전략을 대상에서 빼고, 09:05:00 이후는 스케줄러의 2차 REST 폴백이 `source="rest"` 로 백스톱한다. 마커 4종(`[main_rest_basis_config|round|confirmed|unresolved]`, `KstDailyEmitCap` + `observer_trace`) — `config` 1회/(전략,모드,emitter)/일 · `round` 전략별(fast 항상, slow 는 pending>0 일 때만) · `confirmed` 1회/(전략,종목)/일로 REST 조회 **직전** shadow 병기(`ws_open`/`ws_src`/`delta_bp`/`target_rest`/`target_ws` = 오염 규모의 정본) · `unresolved` 1회/(전략,종목)/일로 마지막 fast 라운드 직후(= 커버리지 손실의 정본). `scanner.ticker_prices` 는 **읽기 전용**(8영역 무접촉). 자문 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.
- **`quote_token_refresh.py`** — 보조 시세 계정 접근토큰을 매일 `TIME_QUOTE_TOKEN_REFRESH`(**20:45 KST**)에 계정별 `TokenManager.revoke()` → `issue()` 순차로 재발급하는 leaf. `refresh_quote_tokens_once()` 가 `kis_quote_accounts.list_accounts(active_only=True)` 를 순회하고, `task_loop()` 는 `run_periodic_task_loop(immediate_first_run=False)` 에 위임한다(부팅 시각이 앵커가 되면 설계가 무너진다). 고치는 것 = `TokenManager._is_valid()` 의 10분 선제 갱신 마진이 종일 REST 를 쓰는 보조 계정의 재발급 시각을 매일 10분씩 앞당기는 **단조 드리프트**다. 🔴 `revoke()` 가 선행해야 한다 — KIS `/oauth2/tokenP` 는 유효 토큰이 살아 있으면 **같은 토큰·같은 만료**를 돌려주므로 폐기 없이는 만료 앵커가 이동하지 않는다. `revoke()` 실패는 WARNING 1행 뒤 `issue()` 를 계속 시도하고(무토큰 방치 금지), `failed` 카운터는 issue 실패 전용이며, `revoke()` 는 전역 issue lock 과 61초 gap 을 소모도 우회도 하지 않는다. **시각 불변식 3** = (a) T 와 T−10분이 모두 KRX 장중(09:00~15:30) 밖 — 필요조건이지 충분조건이 아니다 (b) 7계정 × 61s ≈ 7분의 직렬화 창이 REST 를 많이 쓰는 예정 작업과 겹치지 않을 것 (c) **T 는 스케줄러 task 루프의 생존 창 안**일 것 — `run_daily` 의 `finally` 가 정산(`TIME_SETTLEMENT`) 뒤 백그라운드 task 를 전부 cancel 하므로 그 뒤 시각은 매일 0회 발화한다(로그에는 부팅 시 `scheduled at=` 한 줄만 남아 배선이 살아 있는 것처럼 보인다). 🔴 **진짜 요건은 "장중 밖" 이 아니라 "보조 풀 REST 가 없는 창"** 이다 — T−10분 문턱이 REST 창 한복판이면 자연 재발급이 항상 강제보다 먼저 난다. 20:45 는 20:00 자문·20:00:05 유니버스·20:05 metrics·20:30 일봉(≈20:32 종료)·21:30 정산을 전부 `[T−10, T+8]` 창 밖에 둔다(가드 `test_c9`·`test_c10` 이 전수 스캔으로 잠근다). 대상은 보조 계정뿐이고 주계정(`label=None`)은 무접촉이다. **WS 무영향** — WS 는 별도 엔드포인트 `/oauth2/Approval` 의 `approval_key` 로 접속·구독하며 `issue()` 는 그것을 건드리지 않는다. 마커 `[quote_token_refresh]` 3종 = `scheduled at=`(배선 카나리아) · `label=… issued expired=… revoked=True|False`(계정별, `revoked=False` = 그 계정은 이번 회차에 앵커 미이동) · `accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d`(회차 요약 — `elapsed_s` 는 체인 총 소요 ≈420s = 7계정 × 61s, `window_issues_total` 은 체인 시작 **−15분**부터 종료까지 그 회차 매니저들의 발급 횟수). 성공 서명 = 장중 자연 재발급 0건 · `window_issues_total=7`. `scheduler.py` 배선은 2줄(import + `create_task`) + cancel 목록 3곳이고 본체가 leaf 인 이유는 라인 상한이다.
- **`llm_buy_gate.py`** — **매수 주문 접수 시점** LLM 평가 shadow leaf(매매 행위 변경 0). 진입점 `observe_order(*, strategy_id, ticker, order_no, order_kst, order_price_won, ordered_qty, order_division, order_path, exchange, current_price_won, budget_total_won, budget_remaining_after_won, open_positions_n, params_snapshot, buy_signals_tail)` — **키워드 전용 · 동기 · never-raise · `await`/DB/HTTP 0 · 반환 항상 `None`**. 전략 파일에는 훅이 없다. 소비처는 `order_engine.execute_buy` 의 매수 `place_order` 성공 직후 매핑 등록 블록 끝 **2곳**(주 경로 · 시장가 거부 지정가 5호가 폴백)이며 `_insert_pending_or_absorb_race` **앞**이다. 순서 = `mode(off|shadow, 그 외 off)` → `[llm_gate_config]` 카나리아(off-return 앞) → off 즉시 return → `order_no` 유효성(빈 값이면 `[llm_eval_persist] reason=empty_order_no` 1행 후 return) → 래치 peek(키 = **주문번호**/일 — 같은 종목을 하루 두 번 사면 두 번 평가한다) → 일일 cap peek(`[llm_gate_daily_cap]` WARNING 1회/전략/일 + `[llm_eval_persist] reason=cap_exceeded` 주문별 1행) → 값 복사 payload → 래치 mark + cap 증가 → `asyncio.create_task(_evaluate)` 정확 1회. `_evaluate` 는 `_evaluate_core` 의 outcome 을 받아 **단 1곳**에서 `_persist_evaluation` 한다(성공·실패 **모두** `llm_buy_evaluations` 1행 — 실패도 `input_payload` 를 담고 `score=NULL`). `_evaluate_core` 는 세마포어 2 안에서 `db.stock_master_daily.get_recent_daily_normalized`(캐시 `(ticker, KST date)` 상한 400, 당일 봉 폐기, 60봉 fetch → 프롬프트에는 30봉) → `llm_features.compute_technicals`/`build_messages` → `AsyncOpenAI.chat.completions.create`(`settings.openai_buy_gate_model`, `response_format=json_object`, `asyncio.wait_for`) → 출력 검증(클램프 금지, `int(inf)` OverflowError 흡수) 순으로 돈다. `_MAX_COMPLETION_TOKENS = 2000` — 추론 모델은 추론 토큰이 이 한도를 함께 소비하고 과금은 실사용량이라 **비용은 오르지 않는다**. 한도 소진은 파싱이 실패한 경우에만 `reason=truncated` 로 분류한다(완전한 JSON 이면 점수를 살린다). `asyncio.CancelledError` 는 re-raise. 마커 5종 = `[llm_gate_config]` · `[llm_buy_score]`(`order_no=`·`order_kst=`·`order_price=`·`post_order_drift_bp=` — **+ 는 주문 뒤 상승 = 이득**) · `[llm_buy_score_failed] reason=` 10종(timeout / api_error / parse_error / schema_error / no_bars / no_key / cap_exceeded / disabled_model / payload_error / truncated, `finish=` 는 OpenAI `finish_reason` 원문이고 LLM 호출 전 실패는 `-`) · `[llm_gate_daily_cap]` · `[llm_eval_persist] order_no= result=ok|error [reason=]`(DB 무음을 깨는 유일 채널). 🔴 `empty_order_no` 와 `cap_exceeded` 는 **persist 어휘**이지 평가 실패 어휘가 아니다 — 섞으면 일일 리포트의 실패 분류가 오염된다. 보드는 세션 트래커가 아니라 **시계**(`_board_by_clock`)로 푼다(leaf 는 8영역을 참조하지 않고, 트래커의 활성 보드는 30초 stale 이라 09:00:0x 에 `pre_nxt` 로 굳는다). 계좌번호는 leaf 가 `settings` 에서 읽는다. 회고 층화 2열 = `_prompt_version()`(SYSTEM 프롬프트 + user 프리앰블 + `llm_features` 스냅샷 키의 sha256 앞 12자) / `_feature_version()`(`compute_technicals` 출력 키 집합), 계산 실패는 `""` fail-open. `src.*` import 는 허용 목록(`daily_emit_cap`·`observer_trace`·`llm_features`·`config`·`db.stock_master_daily`)만 **모듈 최상단**에 두고 `scanner`·`tick_volume`·`log_analysis_engine`·`db.llm_buy_evaluations` 는 함수 내 **지연 import** 다(순환 차단). 8영역 중 `order_engine.py` 만 접촉하고 A-ATOMIC 구간은 byte 동일. 킬스위치 `llm_gate_mode=off`(PUT 즉시). 영속 = `src/db/llm_buy_evaluations.py` + migration 043, 조회 = `src/routes/llm_evaluations.py`.
- **`market_unit.py`** — 시장 유닛(단계형) 판정 leaf(cycle382). KODEX 200(`SOURCE_TICKER="069500"`) 일봉 종가로 그 거래일의 장세를 4단계로 나눈다. `MULTIPLIERS` = `up_rising` 1.0 · `up_falling` 0.75 · `down_rising` 0.5 · `down_falling` 0.0. 창 `w` = `bas_dd < as_of_date` 인 행을 오름차순으로 세운 마지막 `MIN_ROWS`(80)개다. `above = w[-1] × 60 > sum(w[20:80])` · `rising = sum(w[20:80]) > sum(w[0:60])`(60일선이 20봉 전 60일선보다 높다). 평균 대신 합으로 비교해 부동소수 동률 흔들림을 없앴고, 동률은 약한 쪽(엄격 부등호)이다. 상수(`MA_WINDOW=60`·`SLOPE_LOOKBACK=20`·배수 4개)는 이 파일 한 곳에만 있고 파라미터로 열지 않는다(AST A02). 공개 함수 = 순수 `classify(closes)` · `normalize_mode(raw)`(부재 = `("off", True)`, 오타·비문자열 = `("off", False)`) + never-raise 로더 `async compute_snapshot(as_of_date, *, preview) -> Snapshot`. 로더는 `stock_master_daily.get_recent_daily("069500", FETCH_ROWS=120)` 와 `trading_calendar.previous_trading_day(as_of_date)` 를 **함수 안 지연 import** 로 부른다(테스트 monkeypatch seam · DB 전용 · KIS 폴백 없음). 판정 순서 = 행 수(`rows_short`) → 신선도(`stale_head` = `head < previous_trading_day(as_of_date)`, 달력을 모르면 `(as_of_date − head).days > STALE_FALLBACK_MAX_CALENDAR_DAYS`(10)) → 종가 품질(`bad_close` = 창 안 결측·비수치·비유한·0 이하) → 그 밖 `exception`. 실패는 전부 `ok=False, state="unavailable", m=1.0` 이다 — 🔴 실패를 m=0(fail-closed)으로 바꾸지 않는다. 최상위 import 는 표준 라이브러리뿐이고 8영역·`scheduler`·`boot_manager`·`market_regime` 을 import 하지 않는다(AST A01). 모든 시장 유닛 마커는 이 모듈의 `logger`(`"src.engine.market_unit"`) 하나로 나가고, 부르는 쪽과 cap 판정은 `StrategyBase` 헬퍼다(하단 `strategy_base.py` 절). ⚠️ `069500` 은 지수 편입이 아니라 시총·거래대금 자격(`scanner._is_daily_load_universe`)으로 일봉 적재 대상에 든다 — 그 자격을 잃으면 매일 `stale_head` 로 m=1 이 된다.

### 출처 절: 모듈 맵 › 자문 · 리포트 · 레짐

  **`"vcp_breakout_events"` 키(cycle349, 관측 전용)** — 10번째 키다(cycle351 이 그 뒤에 `pyramid_shadow` 를 더해 더 이상 마지막이 아니다). 호출 시점에 `trading_scheduler.registry.get("vcp_breakout")` 의 `breakout_event_summary(target_date)` 를 읽는다(메모리 읽기 = 추가 I/O 0). 전략 부재·조회 실패·요약 실패는 그 키만 `None` 이고 나머지 metrics 는 무영향이다(never-raise). 값에는 `final` 이 붙는다 — **1** = 그날 VCP 매수 창(`params["entry_end"]`, 못 읽으면 14:30)이 닫힌 뒤의 값이라 더 바뀌지 않는다(지난 날짜 포함), **0** = 창이 아직 열려 있어 중간값이다. WARNING `[vcp_breakout_events] date= status=ok crossed=<C>/<N> observed= unobserved= run_at= window= partial= crossed_tickers=` 는 `target_date == 오늘(KST)` **이고 창이 닫힌 뒤에만**, 모듈 전역 `KstDailyEmitCap` 로 **하루 1회** 찍는다. 이 함수는 20:05 스냅샷·20:20 번들·21:30 완전판이 모두 부르므로 평소에는 20:05 가 찍는다. 창이 열린 동안의 호출(낮의 번들 GET·`POST /api/log-reports/run`)과 과거 날짜 호출은 키만 채우고 cap 을 소비하지 않는다 — 소비하면 그 중간값이 그날의 결과 줄이 된다. `ok` 가 아니면 `status=` 까지만 찍는다. 수집 실패 흔적은 DEBUG `[vcp_breakout_events_error]` 다(데이터 마커와 접두를 가른다). 🔴 새 키는 항상 **끝에** 더한다 — 키 순서가 OpenAI 프롬프트·JSONB·번들의 계약이다(핀 = `test_cycle249_collect_metrics.py::EXPECTED_METRIC_KEYS` · `test_cycle259_log_metrics_collector.py::test_l3_metric_key_order_is_byte_identical`·`test_l3b_reexported_entrypoint_returns_same_shape`). 값의 의미·한계 = `strategies/CLAUDE.md` 각주 ⑥.
  **`"pyramid_shadow"` 키(cycle351, 관측 전용)** — 11번째 키다(cycle366 이 그 뒤에 `report_accuracy` 를 더해 더 이상 마지막이 아니다). `kojiro`·`donchian_swing` 의 레지스트리 파라미터 사본 + 예산 + 보유 ticker 집합만 읽어(읽기만, 등록·상태 무변경) `src.engine.pyramid_shadow.build_pyramid_shadow` 에 넘긴다. 30초 상한(`_PYRAMID_SHADOW_TIMEOUT_SECS`) + 예외는 이 키만 `None`(never-raise) — 실패·타임아웃은 DEBUG(매 실패) + WARNING `[pyramid_shadow_error]` 1회/일(`_pyramid_shadow_failure_cap`, `observer_trace` 규약)로 남는다. 상세 = `pyramid_shadow.py` 항목.
  **`"report_accuracy"` 키(cycle366, 관측 전용)** — 반환 dict 의 **맨 끝**(12번째) 키다(§5 P6). `{trading_day, market_closed, by_ticker_pnl_total_tickers, by_ticker_pnl_truncated, after_market_blind_secs_total, pre_market_blind_secs_total}`. `trading_day`(`bool | None`)는 `trading_calendar.is_open_day(target_date)` 를 그대로 재사용한다(지연 import, never-raise — 조회 예외는 `None`="모름"으로 흡수). `market_closed = (trading_day is False)` — `None`(모름)은 휴장으로 단정하지 않는다. 20:20 클라우드 루틴·21:30 LLM(`log_analysis_engine.SYSTEM_PROMPT` 에 해석 규칙 명시)이 휴장일의 0건을 결함으로 오독하지 않게 하는 것이 목적이다. `by_ticker_pnl_total_tickers`/`by_ticker_pnl_truncated`(`_by_ticker_pnl_truncation`)는 `trades.by_ticker_pnl` 상위 5개 절단 여부를 별도로 관측한다(그 서브딕트 자체는 cycle351 골든 byte 계약 대상이라 손대지 않는다). 확장 blind 2필드(`_aggregate_extended_blind`)는 `[tick_blind_boot]` 로그의 애프터마켓(16:00~20:00)·NXT 프리마켓(08:00~08:50) 겹침 초를 `tick_blind.market_blind_secs_total`(기존 09:00~15:30 KRX 메인, cycle234, 무변경)과 별도로 합산한다 — 출처는 `uptime_monitor.after_market_blind_overlap_secs`/`pre_market_blind_overlap_secs`(신규 함수, `market_blind_overlap_secs` 와 공용 코어 `_weekday_window_overlap_secs` 공유·기존 함수 값 불변). 매매 행위 0. 회귀 = `tests/unit/engine/test_cycle366_report_accuracy.py`.

### 출처 절: 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

  1. `immediate_force_run_check` 가 True → RUN `<immediate_force_run_reason>`(기본 `below_floor`, cycle363 F-4) / 예외 → RUN `force_check_error`(이 값은 `immediate_force_run_reason` 과 무관하게 항상 고정 — "판정 자체가 실패했다" 는 "판정이 임계를 넘었다" 와 다른 사실이다)
  2. 마커 조회 예외 → RUN `marker_error` — 🔴 **운영에서 도달 불가**(cycle363 F-5, 독립 검증 반영). `system_config.get_task_last_success`(`_get_string_or_none`)가 broad `except Exception: return None` 이라 pg 예외를 삼켜 `None` 을 돌려준다 — 이 분기는 방어적 코드일 뿐 실측 경로가 없다. 실제로는 pg 장애도 다음 ③(마커 없음)으로 떨어진다. **명세 한계** — full_universe(`skip_if_absent=True`)에서는 진짜 pg 장애가 부트스트랩(마커 영구 결측)과 구분되지 않는 SKIP 이 된다(둘 다 `reason=no_marker`). 실측 = `tests/unit/engine/test_cycle363_immediate_slot_gate.py::test_H3b_*`(실 함수 경로)
- **basics 전용 자가 치유 — 강제 재실행(cycle363 F-4, 사용자 승인)** — `stock_master.count_missing_kis_provenance_key()`(`raw` 에 KIS CTPF1002R 키 `cptt_trad_tr_psbl_yn` 이 없는 행 수) `> STOCK_MASTER_BASICS_FORCE_RUN_MISSING_THRESHOLD`(=100, `data_load_tasks.py`)이면 마커가 fresh 여도 실행한다(`immediate_force_run_check=_stock_master_basics_kis_keys_missing_above_threshold`, `immediate_force_run_reason="kis_keys_missing"`). 판정은 full_universe(+0초) **뒤**(basics +480초)라 실제 손상(결측 행 수)을 보고 결정한다 — full_universe 만 RUN 하고 basics 가 SKIP 하는 월요일 아침에, KRX 적재의 하드코딩 False(`nxt_tradable`·`krx_halted`·`admin_item`)와 KIS 출처 키 부재가 16:10 정기 실행까지 방치되던 결함(독립 검증 finding #6) 시정이다. 🔴 `count_missing_kis_provenance_key()` 는 **예외를 삼키지 않는다** — `count_active()` 류의 "실패 시 0" 관례를 반복하면 쿼리 실패가 "결측 0건"(SKIP 방향)으로 읽혀 사용자 결정("쿼리 실패는 RUN 쪽 fail-safe")과 반대로 움직인다. 예외는 그대로 전파해 위 ①의 `force_check_error` 가 흡수한다.
- 🔴 daily_load 가 게이트 대상인 이유 = 아침 immediate 가 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)을 먼저 써서 `max_bas_dd == today` 를 만들면 그날 정기 실행이 전 종목을 `skipped_fresh` 로 건너뛴다. 🔴 full_universe 를 무게이트로 두지 않는 이유 = 아침의 KRX 는 직전 영업일 자료를 아직 내놓지 않아(07:53 까지 빈 응답 실측) 즉시 실행이 **그 전 영업일 값으로 전량을 덮는다** — 월요일이면 목요일 값이 금요일 값을 덮는다(경위 = history). 신규 상장 유입은 20:00:05 정기 실행이 맡는다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 시각과 순서

🔴 **20:30 에 쓴 D 봉의 종가·고가·저가는 확정값이 아니다(잠정 봉).** KIS 일봉(FHKST03010100, 시장 `J`)은 D일 20:00 뒤에도 종가를 19:59 애프터마켓 마지막 체결가로, 고저를 애프터마켓까지 넣은 범위로 준다. 정규장 값(15:30 종가·정규장 고저)으로 바뀌는 것은 D일 23:12 뒤 ~ D+1일 05:28 전이다(cycle386 실측, 09-23 봉 종가 불일치 모집단 약 60%). 시가·거래량·거래대금은 잠정 봉과 확정 봉이 같다 — 거래량·거래대금은 확정 봉도 애프터마켓을 포함한다. 잠정 봉은 다음 거래일 아침 부팅이 prepare 직전에 확정한다(아래 「전일 잠정 봉 확정」 절).

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 분할 backfill 분기 — 대상은 적재 대상 전부

- 분기 조건은 **깊이 하나**다: `existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=225)` → `condition.fetch_daily_candles_backfill(ticker, total_days=225)`(분할 fetch, 마지막 윈도우 클램프) / `>=225` → 증분 7일(재 backfill 금지). 지수 소속·자격·보호 어느 것도 깊이를 가르지 않는다(cycle302).
- 🔴 **`_DAILY_LOAD_VCP_BACKFILL_DAYS` 는 VCP 전용이 아니다.** 이름의 `VCP` 는 이 깊이를 처음 요구한 전략의 흔적이고, 값은 적재 대상(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) 전부의 목표 깊이다. 이름 정정은 `src/api/condition.py` 호출자 주석 동반 이동이라 후속 과제로 둔다.
- 🔴 깊이를 가르면 안 되는 이유 = 보유 행수가 얕은 종목은 `effective_ema_long = min(ema_long, 보유 − 20 − 5)` 가 74~121 로 잡혀 VCP 의 중기↔장기 간격이 10 안팎이 되고 정배열 판정이 동전던지기가 된다. 근거 실측은 [`docs/history/src-engine-CLAUDE.history.md`](../../docs/history/src-engine-CLAUDE.history.md) 「분할 backfill 분기 — 대상 확대」.
- 🔴 **비용은 1회성이다.** 깊이에 닿으면 증분(7일·1콜)으로 내려오고 retention 390cal(≈261 영업일)이 225 아래로 떨어뜨리지 않는다 — 수렴 상태의 매일 밤 호출량은 종목당 1콜 그대로다(가드 `tests/unit/engine/test_cycle302_backfill_scope_expansion.py::test_g302_3_converged_universe_costs_one_call_per_ticker`). 첫 채움만 종목당 3콜(962종목 ≈ 2,886 호출 ≈ 345초)이라 20:30 정기 실행이 아니라 **수동 trigger**(`POST /api/stock-master/daily/refresh?force=1`)로 장 종료 후에 돌린다 — 20:30 에 얹으면 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창(20:35~)을 1분 침범한다.
- ⚠️ `existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD(=50)` → 100일 단발 분기는 **225 > 50 인 한 도달 불가**한 구조적 폴백이다(신규 상장도 첫 밤에 225일을 탄다). 목표 깊이를 50 아래로 되돌리면 되살아난다 — 관계 핀 `test_cycle302...::test_g302_8b_deep_target_dominates_incremental_threshold`.
- ⚠️ **상장 이력이 225 영업일보다 짧은 종목은 수렴하지 않는다** — 매일 밤 3콜을 쓰고 목표에 못 닿는다(최근 상장 코호트 한정, 종목당 하루 2콜 초과분). 자본 위험 0 · 관측 채널 = `[stock_master_daily_load_summary]` 의 `mode=`(수렴하면 `incremental`, 미수렴 종목이 남으면 `mixed`)와 `elapsed_ms`.
- 🔴 225 인 이유 = `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)` 라 보유 **225 영업일에서 실효 장기선이 정확히 200** 이 된다(220 이면 195 에 그친다). retention `DAILY_RETENTION_DAYS=390`cal ≈ 261영업일이 그 아래로 **36 영업일 마진**을 남긴다. 🔴 **target 과 retention 은 함께 움직인다** — target 이 보유 영업일을 넘으면 `existing_count` 가 영원히 target 에 못 닿아 매 load 전량 재backfill(churn)이 된다.
- **1회 backfill 이 target 을 넘는다 — 한 밤에 채운다.** `condition.fetch_daily_candles_backfill` 의 깊이 환산이 `total_days=225` 에서 347 달력일에 닿고, 실측 비율(1.479)로 약 **232 영업일**이다(잉여 7). 전이 기간이 없다. 🔴 그 환산의 **stride 는 7/5 고정**이다 — 키우면 윈도우 사이에 구멍이 생긴다(상세 = `src/api/CLAUDE.md`). 가드 = `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`.
- VCP `prepare` 가 그 깊이를 실제로 읽는 것은 `daily_fetch_depth_mode="full"` 일 때뿐이다(코드 기본값은 `"cap100"` = 100봉이고 **운영 DB 는 `"full"`** — 상세 = `strategies/CLAUDE.md` VCP 절).
- graceful — backfill 실패는 `failed++` 후 다음 ticker.
- 🔴 장중 자동 실행 없음 — 20:30 daily task + 수동 trigger 뿐이다.
- **읽기 두 겹은 cycle300 이 열었다** — `db/stock_master_daily.get_recent_daily` 의 상한은 `_MAX_DAILY_ROWS`(400)이고, VCP 는 전략 파라미터 `daily_fetch_depth_mode` 로 요청 깊이를 정한다(코드 기본값 `"cap100"` = 100봉, `"full"` = `ema_long + base_max_days + 10`). **코드 기본값에서는 행위가 cycle300 이전과 byte 동일**하고, 200일 EMA 를 실제로 쓰려면 `PUT /api/strategies/vcp_breakout/params {"daily_fetch_depth_mode":"full"}` 로 켠다(운영 DB 는 켜져 있다). 상세 = `strategies/CLAUDE.md` VCP 절.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 확정 전 오늘봉 시각 필터 (`_drop_today_bars`)

- ⚠️ **데이터 기준(거래량 0 ∧ OHLC 평탄) 금지** — 반증 2건: (a) 장중 재시작이 만드는 **부분봉**은 거래량>0·비평탄이라 데이터 기준을 확정봉인 척 통과한다(껍데기보다 나쁘다 — 평탄하지 않아 눈에 안 띈다) (b) 거래정지 종목의 **진짜 평탄 확정봉**을 저녁 적재에서 죽여 그 날짜 행을 영영 못 갖게 한다. 시각 기준은 둘 다 자동 처리하고 진짜 무거래봉을 정의상 100% 보존한다.
- **`force=True`(수동 `POST /api/stock-master/refresh-daily`)도 필터를 통과한다** — `force` 는 `latest >= today` 멱등 skip **만** 우회한다. 주말·20:00 이후 수동 보정은 오늘 날짜 봉 자체가 없거나 확정봉이라 무접촉이고, 장중·시간외 수동 실행만 잠정봉을 버린다(설계 의도).

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 일봉 적재 본체

- 분기 = `max_bas_dd(ticker)` — 부재면 백필(T-100일), 존재하면 증분.
- KIS `fetch_daily_candles`(`src/api/condition.py`) **재사용**(신규 KIS API 도입 0) → `stock_master_daily.upsert_batch(ticker, rows)` 영속화.
- graceful — KIS 거부·타임아웃이면 그 ticker 를 skip 하고 다음으로 간다.
- emit `[stock_master_daily_load_summary]` 1행 INFO(`tickers_total` / `inserted` / `skipped` / `failed` / `elapsed_ms`) + `db_write_failures` 카운터.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 전일 잠정 봉 확정 (`daily_bar_finalize.py`, 부팅 prepare 직전)

- 헤드 행 = `updated_at < 오늘 06:00` 이면 잠정.
- 헤드보다 옛 행 = `updated_at < (bas_dd + 1일) 06:00 KST` 이면 잠정.
- 헤드에 더 보수적인 기준을 쓰는 이유 = 주말·연휴 중 쓰기가 확정인지 모른다(KIS 야간 처리가 비영업일에도 도는지 모른다). 헤드는 prepare 가 직접 읽는 행이라 한 번 더 받는 비용이 싸다.
- 같은 날 재기동은 대상이 0 이다. 아침에 덮은 행은 `updated_at` 이 06:00 뒤다.
- 00:00~06:00 에 수동 기동해도 안전하다. 그때 쓴 행은 06:00 전이라 잠정으로 남고 다음 부팅이 다시 받는다(`start()` 는 20:00 이후만 거부한다).
5. 교차검증 — 그 종목의 `newest` 가 헤드일 때만 한다. `prdy` = `output1.stck_prdy_clpr`.
   - `prdy` == 헤드 봉 종가 → `verified`
   - `prdy` == 헤드 앞 봉 종가 → `unrolled`. KIS 요약이 아직 날짜를 넘기지 않은 것이다. 시각 기준으로 받아들여 쓴다
   - 그 밖 → `mismatch` → **그 종목은 쓰지 않는다**
   - 응답에 헤드 봉이 없음 → `missing` → 쓰지 않는다
   - 응답이 비었거나 KIS 예외 → `failed` → 쓰지 않는다
- `wait_for_boot` = `asyncio.wait_for(asyncio.shield(task), timeout=budget_secs)`. 예산을 넘겨도 태스크를 **취소하지 않는다**. 배경 전환 신호만 켜고 돌아오고, 부팅은 prepare 로 간다.
- 전환 뒤 첫 일꾼이 `result=budget_exceeded` WARNING 1행을 남긴다. 그 뒤로 0번 일꾼 하나만 `BG_SLEEP_SECS` 간격으로 나머지를 처리하고, 끝에 `phase=background` 요약 1행을 더 남긴다.
- 확정 시작부터 `HARD_CAP_SECS` 가 지나면 멈추고 `result=hard_cap` 을 남긴다. 판정은 종목 사이에서 한다.
- 태스크 참조는 모듈 전역 `_BG_TASKS` 가 붙든다(`funnel_capture._BG_TASKS` 관례).
- `wait_for_boot` 는 부팅을 멈추지 않는다. 태스크가 없으면 바로 돌아오고, 예산을 넘기면 위처럼 배경으로 돌린 뒤 돌아온다. 태스크의 예외는 WARNING 을 남기고 흡수한다.
- `CancelledError` 는 부팅 자신에게 취소 요청이 걸렸을 때만 전파한다(`asyncio.current_task().cancelling() > 0`). 확정 태스크만 밖에서 취소됐으면 WARNING `wait_for_boot 확정 태스크가 외부에서 취소됐다` 를 남기고 부팅을 계속한다. `shield` 는 부팅이 취소될 때 확정 태스크를 지킬 뿐, 확정 태스크 자신의 취소는 그대로 올려 보내기 때문이다.
**킬스위치 `system_config.daily_bar_finalize_mode`**
- 키 없음 = `enforce` · `observe`(받고 비교만) · `off`(아무것도 안 함) · 행은 있는데 모양이 틀림 = `observe` · 조회 실패 = `enforce`(요약에 `mode=enforce(db_error)`).
- 조회 실패를 `enforce` 로 두는 이유 = 쓰는 값이 KIS 확정값이라 고치는 것 자체가 안전하다.
- 판정은 `system_config._select_value`·`_string_from_raw` 를 재사용한다(cycle369 `status_exit_mode` 와 같은 판정).
- 읽는 때 = `finalize_once` 시작마다. 그래서 바꾼 값은 **다음 부팅부터** 먹는다. 🔴 운영 DB 쓰기라 승인 대상이다.
- `[daily_bar_finalize] phase=boot|background mode= result=ok|noop|budget_exceeded|hard_cap|error [stage=] head= since= targets= fetched= upserted_rows= close_changed= hl_changed= verified= unrolled= mismatch= missing= failed= db_write_failures= span_clipped= pending= elapsed_ms= [sample_failed=<≤5>] [sample_mismatch=<≤5>]` — 실행당 1행. 예산을 넘긴 날은 `budget_exceeded` 1행 + `phase=background` 1행이다.
- `stage=`(`result=error` 일 때만) = `head`(헤드 조회 실패) · `select`(대상 조회 실패) · `processing`(일꾼 단계 예외 — 나머지 일꾼을 멈춘 뒤 찍는다. traceback 을 함께 남긴다) · `unexpected`(그 밖 예외 — 대상 묶기·순서 정하기 등. traceback 을 함께 남긴다). `head`·`select` 는 아무것도 고치지 않은 것이다.
- `mode=off` 가 아닌데 `result=noop head=`(빈 값)이면 테이블에 오늘 앞 봉이 하나도 없는 것이다. 헤드 조회 실패는 `stage=head` 로 따로 찍힌다.
- 요약 마커를 남기지 않는 경로는 취소(`CancelledError`) 하나다.
- 예산을 넘긴 날은 부팅 prepare 가 확정 전 종목을 읽는다. 그날 후보는 +600초 레거시 재준비가 확정된 DB 로 다시 만든다. 배경은 확정 시작 + 600초에 반드시 끝나고, 레거시 재준비 task 는 `_boot()` 뒤에 만들어져 +600초에 시작하므로 항상 그 뒤다. 🔴 S2 가 레거시 분기를 없앨 때 이 역할을 넘겨받아야 한다.
- 전략 객체(`_candidates`·`_held_stage3`·`_entry_atr` …)는 읽지도 쓰지도 않는다 — DB 만 쓴다(cycle364 PV-1 과 교집합 0). 보유 종목의 진입 ATR 스탬프는 그대로다. 부팅 prepare 가 확정 봉으로 트레일링 ATR·kojiro 스테이지를 다시 계산하는 것은 원래 부팅의 일이다. 애프터마켓이 넓힌 고저가 걷혀 ATR 이 조금 줄 수 있다.
- `_drop_today_bars`·cycle363 `expected_head` 는 무변경이다. 헤드 날짜는 그대로이고 값만 바뀐다.
- ④ `[funnel_boot_vs_evening]` 에 주는 영향 = 「funnel 스냅샷 캡처」 절 ④ 항목.
1. 06:00 경계는 표본 두 묶음(05:28 적재 11종목 · 07:56 적재 25종목)으로 정했다. KIS 야간 처리가 부팅보다 늦는 날은 잠정 값을 받아 쓰고, 그 행은 06:00 뒤에 쓴 것이라 확정으로 분류된다. `output1` 이 이미 넘어가 있으면 `mismatch` 로 잡힌다. 둘 다 안 넘어간 날(`unrolled` 대부분)은 못 잡고, D+1 20:30 7일 창이 다시 덮는다.
**롤백** — 즉시(다음 부팅부터) = `daily_bar_finalize_mode = 'off'`(승인 대상). 코드 = 커밋 되돌리기. 이 leaf 가 쓴 데이터는 KIS 확정값이라 되돌릴 필요가 없다.
- `tests/unit/engine/strategies/test_cycle386_prev_close_regression.py` — G8. 394800 가짜 전일종가 5,520 이면 momentum BUY, 확정 5,800 이면 NONE. 393210(momentum NONE) · 441270(LTV `min_prdy_rate` 에 막힘) · 323350(VB `prev_range` 1,660 → 1,050)도 확정 뒤 정규장 기준 판정으로 돌아온다.

### 출처 절: funnel 스냅샷 캡처 › 라이브 준비는 wrapper 한 곳에서, 한 번에 하나

- never-raise — `prepare()` 예외는 wrapper 가 흡수해 `False` 를 돌려주고 `[live_prepare] <sid> phase=<phase> 전략 prepare 실패`(phase=boot) 또는 `… 재 prepare 실패`(그 밖) 를 ERROR + traceback 으로 남긴다. 옛 호출부 문구를 그대로 담는 것은 grep 연속성 때문이다. 그래서 호출부에 try/except 를 두지 않는다. `_reprepare_breakout_if_empty` 는 `False` 를 받으면 `write_log("ERROR", "<sid> 재 prepare 실패")` 한 줄만 더 남긴다. 🔴 그 자리에서 logger ERROR 를 또 찍지 않는다 — 실패 1건이 ERROR 로그 2행이 되어 21:30 `top_patterns` 집계가 배가된다.

### 출처 절: funnel 스냅샷 캡처 › 레거시 분기 — 21:00 전 (S1 임시)

  - ✅ **「같은 입력」을 깨던 예외 경로(F-1) — cycle363 배포 전 보강으로 시정(사용자 승인 8영역).** 월요일·연휴 뒤 장전에는 `scanner._scan_pool_eager_refresh_loop`(5분 주기)가 24h 를 넘긴 풀 종목을 갱신하는데, 그 갱신과 +600초 재준비가 **같은 시각(T+600)에 시작하는 것 자체는 여전하다**(독립 검증 finding #1/#5, 09-28 에 실제로 겹칠 것으로 추정). 바뀐 것은 그 갱신이 더 이상 raw 를 통째로 지우지 않는다는 것이다 — `upsert_one` 전에 basics 경로(cycle176)와 같은 `{**기존 raw, **신규 raw}` 머지를 넣어, 장전 0 값 키(`_ZERO_VALUE_SKIP_KEYS` — `acml_tr_pbmn` 등)가 사라지지 않고 기존 값에서 보존된다. 그래서 재준비가 그 갱신과 겹쳐도 `list_by_filter` 거래대금 임계(`acml_tr_pbmn_won`)가 더 이상 NULL 로 떨어지지 않는다. 판별 마커 = `[scan_pool_eager_refresh] refreshed=N`(N>0 이면 그 사이클이 실제로 돌았다는 뜻, 결함 여부와 무관) + `select count(*) from stock_master where not raw ? 'acml_tr_pbmn'`(머지가 살아 있으면 이 값이 늘지 않아야 한다). 회귀 = `tests/unit/engine/test_cycle363_scan_pool_eager_refresh_raw_merge.py`.

### 출처 절: funnel 스냅샷 캡처 › ④ 저녁 목록 ↔ 부팅 목록 대조 `[funnel_boot_vs_evening]`

- task 참조 = 모듈 전역 `_BG_TASKS` 에 넣고 `add_done_callback(_BG_TASKS.discard)` 로 스스로 빠진다(`llm_buy_gate` 관례). asyncio 는 버린 Task 를 약한 참조로만 쥐기 때문이다.
- 전체 상한 = `BOOT_VS_EVENING_TIMEOUT_SECS`(10초, `asyncio.wait_for`). S1 의 `phase` 는 `boot` 뿐이다.
- 부팅 목록 = 활성 전략의 `get_scanned_tickers()`. `get_scanned_tickers` 가 호출할 수 없는 전략(momentum)은 저녁 행이 있어도 행을 내지 않고 건너뛴다 — 비교할 부팅 목록이 없어서다. 실패가 아니므로 `error=strategy_failed` 에 세지 않는다(저녁 캡처는 momentum 에도 `step_no=99` 행을 쓴다 · 회귀 `test_cycle364_funnel_boot_vs_evening.py::test_boot4_23_when_strategy_has_no_scanned_list_then_skipped_without_failure`). 비교 전에 양쪽에서 보호 종목(전 전략 보유 ∪ `_pending_next_day_clear`)을 뺀다 — 저녁엔 보호 종목이 마스터 차단·가격 필터를 통과하고, 부팅엔 포지션 복구 전이라 보유가 0 이다. 그 차이는 설명된 차이다.
- ⚠️ **전일 잠정 봉 확정이 켜진 날은 `bars_changed_after` 가 평일마다 수백 이상이다** — `daily_bar_finalize` 가 부팅 prepare 앞에서 헤드 봉 약 970행을 다시 쓰기 때문이다(「저녁 데이터 적재」 절). 틀린 값이 아니라 아침에 입력이 실제로 바뀐 것이다. 그래서 「세 힌트 전부 0 인데 목록이 다르다」 WARNING 은 평일에 거의 나지 않는다. 🔴 S2 착수 근거로 모으는 평시 `same=1` 표본은 이 leaf 배포 전후를 합산하지 않는다. S2 가 쓸 입력 변화 신호는 `updated_at` 이 아니라 `[daily_bar_finalize]` 의 `close_changed`·`hl_changed` 다.

### 출처 절: 접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2

- 🔴 **래퍼의 `except Exception` 을 좁히지 않는다 — 구조 가드가 유일한 방어다.** 두 축에서 실측으로 확인했다: 매도는 좁히면 기존 회귀 13건이 **전부 초록**인 채로 접수 성공 주문을 「거부」로 적고 익일청산 큐에 넣고(cycle328), 매수는 회귀 14건 중 **`UniqueViolationError` 케이스가 통과**한다(cycle335 — 좁히기가 「가장 많이 테스트된 타입」을 그대로 잡는다). 타입 표본을 늘려도 같은 종류의 누락에 노출되므로 행위 테스트로는 못 막는다. 가드 = `test_g328_3`/`test_g328_3b`(두 축 parametrize).
- **접수된 자금은 묶어 둔다** — 접수 후 실패에서 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다**. 접수된 매수는 KIS 가 주문가능금액에서 이미 뺀 「묶인 자금」이라 푸는 것은 **우리가 묶인 사실을 잊는 것**이고, 계좌 방어(`get_buyable`)는 통과하므로 **전략 예산 관문만 조용히 무력화**된다. 유지의 비용은 **체결 0건으로 끝난 주문 한정**으로 그 슬롯·금액이 노는 것뿐이다. 그 주문의 KIS 행이 끝남(`tot_ccld_qty==0 ∧ rmn_qty==0`)을 보이면 다음 잔고 sync 에서 `buying_reconcile`(모듈 맵)이 푼다. 20:00 뒤에 끝난 주문은 21:30 `_reset_daily_state` 까지 남는다. 첫 **부분**체결만 나도 `_handle_buy_fill` 이 해제한다(그 블록은 전량 분기 **앞**이다).
- 자문 = `_workspace/domain_consult/cycle335_buy_post_send_boundary.md` · 설계 카드 = `_workspace/refactor/2026-09-21_step2_card.md` · 가드 = `tests/unit/ast/test_cycle328_sell_pending_helper.py`(11케이스) · 회귀 = `tests/unit/engine/test_cycle335_buy_post_send_boundary.py`(14케이스) · `test_cycle327_sell_fill_during_insert.py`(6) · `test_cycle271_execute_buy_fill_during_insert.py`(17)

### 출처 절: 취소 타이머 키 — `(ticker, 축)` (cycle332)

`_pending_cancel_tasks` / `_pending_cancel_order_no` 의 키는 **`(ticker, side)`** 다(`side ∈ {"buy","sell"}`, 리터럴은 모듈 상수 `CANCEL_AXIS_BUY`/`CANCEL_AXIS_SELL` 한 곳에만 둔다). 매수 잔량 취소(`_schedule_cancel`)와 매도 손절 잔여 재주문(`_schedule_cancel_and_reorder`)이 **각자 자기 축만** 교체하므로 두 타이머가 공존한다.
🔴 **ticker 단독 키에서는 나중에 걸린 쪽이 앞선 쪽을 `order_no` 검사 없이 죽였다.** 해제는 cycle273a 가 `order_no` 게이트로 좁혀 두었는데 **등록만 안 좁혀져 있던** 것이고, 이 키가 그 미완성 규약을 완성한다.
- **S1(매수 타이머가 손절 타이머를 죽인다)이 심각하다** — `_cancel_and_reorder` 는 취소 3경로 중 **유일한 `cancel_order → place_order` atomic replace** 다. 그게 죽으면 원 매도 주문이 호가에 남고 시장가가 아니면(프리장 `step_down` 변환·KRX 애프터 `41` 지정가·NXT 잔존) **안 팔린다**. 게다가 매도 **부분**체결 분기는 `_selling` 을 discard 하지 않으므로 `risk.on_tick` 의 `_selling` 가드가 `check_exit_signal` 을 건너뛰고, `selling_reconcile`(180초)도 원 주문이 **열린 채**라 `open_order` = **유지** 분기다. 즉 **급락장에서 손절 잔여가 체결도·재주문도·재평가도 못 받은 채 21:30 까지 간다**.
- 🔴 **해제의 `order_no` 일치 게이트는 그대로다**(cycle273a 계약) — 이 사이클이 좁힌 것은 **등록 축**뿐이다. 같은 축 재스케줄은 여전히 교체한다(부분체결 연속은 정상이고, 안 그러면 타이머가 쌓인다).
- **UI 계약 보존** — `GET /api/trading/status` 의 `pending_cancels` 는 여전히 **ticker 배열**이다(`frontend/src/types/trading.ts` · `OrderMonitor.tsx`). `order_engine.pending_cancel_tickers(engine)` 한 줄 파생이 담당하고, 한 종목에 두 축 타이머가 걸려 있어도 **한 번만** 나온다. 🔴 `order_no` 단독 키를 쓰지 않는 이유가 이것이다(그쪽이 더 정확하지만 UI 의미가 바뀌고 cycle273a·cycle291 가드 다수가 재작성 대상이 된다).
- 자문 = `_workspace/domain_consult/cycle332_buy_cancel_timer.md` · 회귀 = `tests/unit/engine/test_cycle332_cancel_timer_key.py`(5케이스)

### 출처 절: 발사 창 귀속 — `pending_buys` 단 (cycle331)

`await place_order` 가 걸려 있는 동안 주문번호 매핑 5종이 **전부 비어 있고** `pending_buys` 는 **이미 차 있다**(`execute_buy` 가 `place_order` **앞**에서 넣는다). 그 창에 착지한 **우리 자신의** 매수 체결통보는 `_order_strategy` miss → `trade_history` miss(PENDING INSERT 도 `place_order` 뒤라 그 `order_no` 행이 원리상 없다) → `is_ticker_held_by_any` **참** 으로 흘러 P1-B(B-2) 조기 return 에 걸렸다. `is_ticker_held_by_any` 는 `_strategies.values()` **전수**를 보고 `has_position OR is_buy_pending` 이므로(`strategy_registry.py`) **매수 당사자 자신이 그 조건을 세운다** — 확률이 아니라 창에 들어오면 예외 없이 걸린다.
🔴 **그러면 Position 이 아예 등록되지 않아 그날 하루 손절·트레일링·15:20 일괄청산이 성립하지 않는다**(`risk.on_tick` 은 `state.positions` 를 본다). 익일청산만 다음 날 `_boot` 의 KIS 잔고 복구가 되살린다. `trade_history` 는 `mark_pending_buys_completed` 가 장부만 뒤늦게 맞추므로 **대시보드·DB 어느 쪽을 봐도 정상으로 보인다** — 이것이 이 결함이 조용한 이유다.
- **시정** = 폴백 체인에 `_resolve_pending_buy_owner(ticker)` 단을 `trade_history` **뒤**, B-2 가드 **앞**에 끼운다. 채택은 `ticker in state.pending_buys` 인 전략이 **정확히 1개**이고 그 전략이 **미보유**일 때만. 0개·2개 이상·판정 예외는 `None` 으로 물러선다(fail-open, **결과 집합 ⊆ 현행**). 전부 in-memory, `await` 0, never-raise — 체결통보 콜백의 예외는 `realtime/handler.py` 규약상 **WS 재연결**을 부른다.
- 🔴 **B-2 가드를 없애지 않는다** — 그것이 막는 것은 **출처를 모르는 매수가 `momentum` 을 우겨 남의 포지션을 덮는 것**(377450 사고)이고 수동 매매·외부 주문에서 여전히 유효하다. 좁히는 것이지 없애는 것이 아니다. **수동/외부 매수는 우리 `pending_buys` 에 없으므로 한 글자도 바뀌지 않는다.**
- 🔴 **잔량 취소 타이머는 `qty_src == "map"` ∧ 귀속이 `pending` 단이 **아닐** 때만 건다** — 이 시정이 창의 통보를 **처음으로** 부분 체결 분기에 도달시키는데, 귀속이 틀린 랏에서 `_cancel_after_wait` 가 30초 뒤 **사람이 낸 주문의 잔량을 취소**한다(cycle327·cycle329 와 같은 계열). 잃는 것은 없다 — 우리 주문이면 매핑이 곧 서고 잔여 통보가 `src=map` 으로 와서 정상적으로 건다. 보류는 `[buy_partial_no_cancel_timer]` WARNING.
- **관측** = `[buy_fill_strategy_from_pending] order_no= ticker= strategy= qty_src= incr= filled_total= ordered=` **무cap WARNING** = 시정의 성공 서명. cap 을 `(ticker,strategy)` 로 묶으면 같은 날 두 번째 사건이 사라지는데, 실측 빈도가 **BUY COMPLETED 96건 중 2건(2.1%)** 이라 **한 건 한 건이 조사 단위**다. 형제 마커 `[buy_fill_fallback_held_conflict]` 도 무cap ERROR 이고, 시정 뒤에는 **진짜 미지 출처만 남아 0 에 수렴**이 정상이다.
- **별건 권고(이번 사이클 밖)** = `scheduler._sync_positions_from_balance` 의 `is_ticker_held_by_any` 를 **보유 축만** 보는 헬퍼로 바꾸면 블라인드 창이 17~24시간 → ≤15분이 된다. 다만 그 함수 소비처가 5곳이라 광역 회귀이고, 이 시정이 들어가면 실익이 급감한다.
- 자문 = `_workspace/domain_consult/cycle331_buy_fill_dropped.md` · 회귀 = `tests/unit/engine/test_cycle331_buy_fill_from_pending.py`(6케이스)

### 출처 절: 체결통보 주문수량 — 출처 3단 (cycle329)

| `increment` | 이번 통보의 증분 체결량 | 둘 다 없을 때의 **현행 폴백 그대로** |
🔴 **고치는 것** — `order_no` 는 KIS 응답이 와야 알 수 있어 `await place_order` 가 걸린 동안 매핑 5종이 **전부 비어 있다**. 그 창에 착지한 통보는 `ordered_qty` 가 증분 체결량으로 폴백돼 `total_filled >= ordered_qty` 가 **항상 참**이 되고 **부분 체결이 전량으로 읽힌다**. 매수는 `_completed_buy_orders` 가 무장해 잔여 통보가 `[buy_fill_duplicate_ignored]` 로 **조용히 버려진 채** `_sync_positions_from_balance` 가 `is_ticker_held_by_any → continue` 라 **기보유 수량을 영원히 고치지 않는다**(10주를 갖고 3주로 믿는 상태가 익일 `_boot` 까지 간다). 매도는 **주문 축만** 틀린다 — 매핑·타이머·`_selling` 이 일찍 정리되지만, 보유 축이 체결량만큼만 빼므로 잔량은 손절 감시 안에 남는다(「매도 체결 — 주문 축과 보유 축」 절).
- 🔴 **전량 판정에 출처 게이트를 걸지 않는다** — `qty_src != "increment"` 조건을 붙이면 payload 가 없는 퇴화 상황에서 **수동 전량 매도가 유보**되어 포지션 유령 잔존 + `_selling` 좀비(= 손절 마비)가 된다(`selling_reconcile` 의 `held_zero` 는 해제가 아니라 **유지** 분기다). 자문이 B′안을 배제한 이유다. payload 가 있으면 수동 주문도 정확해지므로 게이트 자체가 불필요하다.
- 🔴 **재주문 타이머는 `qty_src == "map"` 일 때만 건다** — 이 시정으로 매핑 부재 창의 통보가 처음으로 **부분 분기에 도달**한다. `_cancel_and_reorder` 는 취소를 **조건 없이** 내고, 발사 직전 보유 재조회(J-2, 「매도 체결 — 주문 축과 보유 축」 절)는 **재발사 수량**만 보유에 맞춘다. `payload` 에는 수동 매매 주문도 포함되므로 게이트가 없으면 **사람이 낸 주문을 우리가 30초 뒤 취소하고 다시 낸다** — cycle327 이 봉한 「주문이 나간 뒤의 재발사」와 같은 계열이다. 우리 주문의 잔여는 ms 뒤 다음 통보가 `src=map` 으로 와서 정상적으로 건다(잃는 것 0). 보류는 `[fill_partial_no_reorder]` WARNING 이 남긴다.
- **overrun 클램프 게이트가 `known_ordered` → `qty_src != "increment"` 로 넓어졌다** — payload 는 KIS 가 준 주문수량이라 매핑과 같은 신뢰도이고, 배제하면 이번에 고치는 그 창에서 클램프만 꺼진다.
- 🔴 **`fields[16]` 은 cycle235 가 오독해 사고(257720)를 낸 자리다** — 체결수량 소스 `fields[9]` 는 무접촉이고 `test_cycle235_ast_execution_qty.py` 가 그대로 봉인한다. 그리고 매핑이 선 **정상 통보마다** `[ordered_qty_mismatch]` 로 payload 를 대조한다(불일치해도 판정은 `map` 값을 쓴다) — 그 사고는 부분/분할 체결에서만 드러나 오래 잠복했는데, 이 대조는 창을 기다리지 않는다.
- **관측** = `[fill_qty_src] order_no= ticker= side= src= ordered= filled_total= incr=` — `src=map` 은 **DEBUG**(정상·대량), 나머지 둘은 **WARNING**(`KstDailyEmitCap[(src,ticker,side)]` 1회/일). WARNING 이상만 21:30 `top_patterns` 에 오르므로 **비정상만 리포트에 뜬다**(ρ축 마커가 INFO 라 리포트에 한 글자도 안 들어가 오귀인을 낳은 선례의 반대). `_settle()` 직전 `[fill_qty_src_summary] window=day map= payload= increment=` 1행 — 🔴 **호출부를 try/except 로 감싸지 않는다**(scanner 일일 summary 2종과 같은 이유). **판독** = `payload > 0` 이면 그 창이 실제로 열렸고 **우리가 막았다**(성공 서명) / `increment > 0` 인데 그날 수동 매매를 한 적이 없으면 **조사 신호**(payload 가 안 실려 온다 = 그 창의 결함이 아직 남는 경로).
- 자문 = `_workspace/domain_consult/cycle329_mapping_absent_full_fill.md` · 회귀 = `tests/unit/engine/test_cycle329_mapping_absent_full_fill.py`(5케이스)

### 출처 절: 매도 체결 — 주문 축과 보유 축 (cycle385)

  - 🔴 **원장 시작 전에 접수된 주문은 `pending` 에서 뺀다(원장 시작 전 주문).** `_sell_ledger_since` 의 뜻 = 「`_sell_notice_seen` 은 이 시각 **뒤**에 처리한 매도 통보를 빠짐없이 담는다」. `__init__`(프로세스 시작)과 `reset_daily_state()` 가 `datetime.now(_KST_TZ)` 로 적는다. 재시작하면 원장이 빈다. 빼지 않으면 그날 재시작 전 체결이 전부 `pending` 으로 잡혀 `eff` 가 작아지고, 손절이 매 틱 발사 없이 보류된다(탐침 — 추적 5 · 계좌 4 · 재시작 전 MTS 6주 체결 → 발사 `[5, 5, 5, 5]`, 판 수량 0). 빼면 분기가 「보유 대 추적」 비교로 돌아가 재대조가 고친다(같은 탐침 → 발사 `[5, 4]`).
  - 🔴 **아직 안 온 외부 체결 통보를 먼저 뺀다.** `_sell_pending_dec(fills, pre)`(동기 · `await` 0) = 원장 시작 뒤 주문마다 `max(0, 누적 체결 − _sell_notice_seen − _sell_reflected_credit)` 의 합이다(`pre` 에 든 주문은 세지 않는다). 거래소는 체결했지만 추적에서 아직 안 빠진 수량이다. 빼지 않으면 surplus 를 작게 봐서 운영자 몫을 판다(탐침 — 추적 10 · 계좌 15 · MTS 3주 체결 통보 전 · MTS 4주 걸림 → 전략 몫은 3 인데 6 을 냈다). 🔴 `max(0, …)` 는 **주문마다** 건다 — 합한 뒤 한 번 거르면, 주문 목록이 통보보다 늦은 주문의 음수가 다른 주문의 대기분을 지워 운영자 몫을 판다(AST AR3-3).
    - 🔴 **걸린 매도가 없어도 보류한다**(명세 부록 R4 D1). 「걸린 것이 없으면 동결하지 않는다」를 글자대로 따르면 그 순간 재대조로 가서 계좌에 남은 운영자 몫을 판다. 탐침 — 추적 5 · 계좌 4 · 원장 시작 뒤 접수된 MTS 주문 5주 체결, 통보 대기. 글자대로면 재대조가 추적을 4 로 맞춰 다시 쏘고 운영자 4주가 팔린다. 지금은 첫 발사 `[5]` 뒤 보류하고, 통보가 오면 닫혀 계좌 4 가 남는다. 무작위 탐침에서도 글자대로 하면 운영자 몫 매도가 늘어 수용 기준을 못 맞춘다.
    - 왜 나머지는 「안 걸렸다」의 증거가 아닌가 — `src/api/base.py::_request` 는 주문 POST 도 전송 오류(`httpx.RequestError` — 타임아웃 포함)와 5xx 에서 다시 보낸다. KIS 거부(`rt_cd≠0`)는 다시 보내지 않는다. 그래서 거부 앞에는 전송 실패 시도만 있고, 그 시도가 응답만 잃고 접수됐을 수 있다. 풀면 다음 틱 손절이 걸린 재주문 위에 또 나간다(탐침 — 계좌 20 · 운영자 10 · 재주문 첫 전송 접수 + 재전송 EGW00201 → 운영자 6주 매도).
    - 종목 크레딧(주문 조회 실패)이 유실 통보분이나 진짜 유령분까지 들고 있다가 뒤 통보를 흡수한 몫. 우리 매도 체결도 흡수 대상이라 우리 매도가 다 끝나도 추적이 남는다(탐침 — 추적 12 · 계좌 10 · 조회 실패 → 우리 10주 체결 뒤 추적 2 · 계좌 0). 그 뒤 운영자가 같은 종목을 사면 남은 추적만큼 손절이 판다. strict xfail `tests/unit/engine/test_cycle385r3_round3.py` TK13 이 적어 둔다.
    - ① 앞 전송 접수(응답 유실) + 재전송 APBK0400 인데, 숨은 재주문의 부분 체결 통보가 다음 틱 **전**에 착지하면 추적이 재주문 수량 아래로 내려가 APBK0400 보장이 풀린다. 운영자 초과분이 있으면 그 몫이 팔린다(명세 R4-4 R4-1 — 탐침 발사 `[10, 6, 6, 3]` · 계좌 13 → 0 · 운영자 3주 매도. 통보가 다음 틱 뒤에 오면 계좌 3 이 남는다).
  - **교체된 재주문 타이머가 손님 수동 매도 옆에서 `_selling` 을 푼다**(명세 R4-4 R4-7). 손님 수동 매도(`_added` 거짓)가 걸린 동안, 자동 매도 원주문을 취소한 재주문 태스크가 CANCELLED 장부 `await` 창(ms)에서 다음 부분 체결 통보에 교체 취소되면, `finally` 가 `place=none` 으로 표식을 푼다. 다음 손절이 걸린 수동 매도 위에 쌓인다(탐침 — 발사 `[10, 4, 3, 6]` · 계좌 20 → 7). 운영자 초과분이 쌓인 몫보다 작으면 운영자 몫이 팔린다. 첫 항목과 같은 계열이다.


## 2026-10-01 sync-docs 압축 — 정본에서 이관 (뒤쪽 절반: 「체결단가 정합」 ~ 파일 끝)

> 사용자 요청 「CLAUDE.md 파일들 전반 점검 — 중복·낡은 부분 삭제, 유지할 내용 압축」에 따른 /sync-docs 모드 B 압축.
> 아래는 압축·정정·중복 제거로 정본에서 바뀌거나 빠진 **원문 줄 그대로**다(정본에 글자 그대로 남지 않은 줄 전부). 정본은 새 값만 남겼다.
> 정정한 사실(원문이 틀렸던 것): ρ축 fail-open 경계의 「K축 심사 = 조용히 통과」(cycle254 뒤로는 K축이 심사한 랏도 `min` 후심사) · `INT_PARAMS` 목록(`breakout_fail_n_days` 는 없고 `k_period`·`max_scan_stocks`·`exclude_consecutive_limit` 가 있다)과 `PARAM_RANGES` 부분 목록 · stale facade 상수 개수(10→11)·`stale_diagnostics` 상수(4→5)·scheduler re-export 상수(5→10) · 매도 시장가 폴백 실패의 「cooldown 등록 안 함」(실제는 결과 무관 30초 TTL 등록) · 시장가 거부 키워드 3종 부분 목록(정본 = `src/api/CLAUDE.md`) · 폐기 식별자 `_SELL_PENDING_SKIP_PATH_LABEL`(현행 `_PENDING_SKIP_PREFIX`) · `param_validation.py` docstring 「실제 101」 · scheduler 줄번호(`scheduler.py:600`·`:846`·`:849-851`·`:852`·`:863-876`·`:875`·`:876`) 표류 · 루트에 없는 「무송출」 절 링크 · GTP 취소 프레임 판별 필드 「표본 없음」(워크리스트 ⑨B 에 09-28 실측이 있다).

### 출처 절: 체결단가 정합 (`_handle_buy_fill` / `_handle_sell_fill`)

- **PARTIAL·CANCELLED `affected==0` 관측 (cycle358 카드 D)** — COMPLETED 는 `affected==0` 시 보정 INSERT/강제 UPDATE 로 스스로 흡수하지만, PARTIAL·CANCELLED 4 호출부(매수 PARTIAL·매도 PARTIAL·매수 CANCELLED·매도 CANCELLED)는 그런 흡수 경로가 없어 장부 행이 없으면 부분체결·취소가 한 글자도 안 남았다. 관측 전용 — 매매·상태전이 로직 무변경. `affected==0` 이면 `_emit_trade_status_update_miss`(`_trade_status_update_miss_logged: KstDailyEmitCap` 1회/(order_no, status)/일)가 `[trade_status_update_miss] status=PARTIAL|CANCELLED order_no= ticker= side=` WARNING 1줄을 낸다. never-raise — 로그 실패는 `observer_trace.trace_observer_failure` 로 흡수하고 주문 흐름을 끊지 않는다(관측 emit 은 예외 흡수, 행위는 cap 밖 — 기존 관측 마커와 같은 규약).

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369)

관리종목·단기과열로 지정된 종목은 보유 중이면 시장가로 판다. 그리고 그날은 어느 전략도 그 종목을 새로 사지 않는다. 사용자 결정(2026-09-25·26)이다. 설계 정본 = `_workspace/domain_consult/cycle369_status_51_59_exit.md` · 명세 = `_workspace/red/cycle369_status_exit_spec.md`.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 보유 청산

- 🔴 **창은 발사 직전에 `_now_kst()` 로 한 번 더 본다.** 조회가 늦어 그 시점이 15:28 을 넘겼으면 그 종목은 쏘지 않는다. 재확인은 카운터 증가·마커·주문보다 **앞**이다 — 뒤에 두면 창 밖 미발사가 하루 3회 상한을 축낸다.
- 🔴 **킬스위치도 발사 직전에 다시 읽는다** — 창 재확인 바로 뒤, 카운터 증가 앞에서 `_modes["sell"]` 을 본다. 앞 종목의 조회나 `execute_sell` 을 기다리는 동안 `PUT sell_mode=off` 가 오면 그 뒤 종목부터 쏘지 않는다. `observe` 가 오면 `[status_exit_would_fire]` 로 돌린다. 메모리 읽기 한 번이라 `await` 가 없다.
- 발사 순서 = 창 재확인 → 모드 재확인 → 발사 횟수 증가 → `[status_exit_fire]` logger WARNING(동기) → `execute_sell`. 횟수 증가는 `execute_sell` await **전**이라, 매 패스 예외가 나도 3회 상한과 giveup 이 살아 있다. 발사 예외는 흡수해 `[status_exit_fire_error]` 를 남긴다(`CancelledError` 는 전파).
- 🔴 **청산 패스는 `system_logs` 를 직접 쓰지 않는다** — `await` 도 fire-and-forget 도 없다(AST F8b). 느린 RDS 가 뒤 종목의 시장가 매도 시각을 15:28 밖으로 밀면 안 되기 때문이다. `[status_exit_fire]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 의 영속은 루트 `_DbLogHandler`(`src/main.py`)가 한다. 그 핸들러는 `src.*` 로거의 INFO 이상을 큐에 넣고(`put_nowait` — 동기·non-blocking) 별도 task 가 `[src.engine.status_exit_watch] <메시지>` 한 줄로 적는다. 🔴 같은 메시지를 `write_log` 로 또 쓰지 않는다 — 사건당 두 줄이 된다(cycle72 G-6 · leaf 판 AST F3b). leaf 는 태스크·타이머를 하나도 만들지 않는다(AST F8).
- **재시작해도 하루 3회 상한이 이어진다.** `task_loop` 가 시작할 때 오늘(KST) `[status_exit_fire]` 행을 `system_logs.search_logs` 로 읽어(읽기 전용) 종목별 발사 횟수를 되살리고, 메모리 카운터와 `max` 로 합친다. 행은 메시지 **어디든** `[status_exit_fire]` 가 들어 있는지로 고른다 — 핸들러 줄은 앞에 `[src.engine.status_exit_watch] ` 가 붙어 `startswith` 로는 못 찾는다. 횟수는 행 수가 아니라 각 행 `attempt=` 의 **종목별 최댓값**이다 — n 번째 발사의 `attempt` 가 곧 그때까지의 누적 횟수다. `[status_exit_fire_error]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 은 그 부분 문자열을 담지 않는다. 조회 실패는 DEBUG `[status_exit_fire_seed_failed]` 뒤 메모리 카운터만으로 돈다(fail-open).
- **재시작 뒤 걸려 있는 59 청산 주문** — 프로세스를 다시 켜면 `_selling` 이 비고, 부팅은 거래소에 걸려 있는 매도 주문으로 그것을 되살리지 않는다. 그래서 이전 청산 주문이 아직 걸려 있으면(단기과열 30분 단일가) 재시작 뒤 첫 청산 패스가 한 번 더 쏜다. 그 주문은 `APBK0400`(요청 수량 > 매도가능수량, `docs/kis/error-codes.md`)으로 거부된다. `execute_sell` #1.5 재대조가 `sellable == 0 ∧ held > 0` 을 보고 `[sell_qty_locked]` 로 끝낸다 — **포지션은 보존**되고 `_selling` 은 **유지**된다(아래 「order_engine.py」 절). 그래서 그 종목은 이후 패스에서 더 쏘지 않는다(`t in _selling` → 건너뜀). 걸린 주문이 체결되면 체결통보가, 만료되면 `selling_reconcile`(180초 age gate · 열린 주문 검사)이 수습한다. 두 번 팔리지 않는다. 거부된 그 발사도 하루 3회에 센다.
- ⚠️ **특별 개장일(지연 개장 — 수능일이 표준 사례)** — 발사 창은 고정 시계(`FIRE_WINDOW_START`~`FIRE_WINDOW_END`)라 그날 장 시간을 모른다. 09:00:30 이 아직 정규장 전이면, 그 시각 주문이 거부될 때 하루 3회가 개장 전에 소진돼 `[status_exit_giveup]` CRITICAL 이 날 수 있다(발사 횟수는 주문 결과와 무관하게 오른다). 15:28 뒤로 늦게 닫히는 장도 보지 않는다. **운영자 조치** = 그날 개장 전에 `PUT /api/integrations/status-exit {"sell_mode":"off"}`(또는 `observe`)로 내리고, 정규장이 열린 뒤 `enforce` 로 되돌린다. 같은 한계가 `_market_rest_now` 에도 있다(아래 「order_engine.py」 규칙 3).

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 당일 매수 차단 (지정 첫날 포함)

- 🔴 **막는 순간 그 전략의 그 종목 edge 기준가를 비운다**(`StrategyBase._clear_edge_baseline_on_block`, 순수 메모리 · `await` 0 · never-raise). 첫 문장 게이트인 LTV 는 차단 동안 `_prev_price` 갱신이 멈춰, 비우지 않으면 해제 뒤 첫 틱이 옛 기준가 대비 거짓 돌파가 된다. 비운 뒤 첫 틱은 기록만 하고 돌파로 읽지 않는다. 비우는 대상은 **모양으로** 고른다(전략 이름 하드코딩 없음) — 중첩 `_prev_price[t]`(VB·LTV `{board: price}`)와 momentum `_prev_prdy_rate[t]` 만 비운다. 🔴 평평한 `_prev_price`(BFB·VCP `{ticker: price}`)는 건드리지 않는다 — 비우면 없는 값이 `0` 으로 읽혀 `0 < level <= current` 가 새 거짓 돌파가 된다. `observe`·`off` 에서는 게이트가 `False` 라 비우지 않는다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 언제 읽나 — `task_loop(sched)` + 관측 훅

- 🔴 **P0 창의 끝은 P1 시작(09:00:05)이 아니라 `BUY_OPEN_TIME`(09:00:00)이다** — `due_actions` 의 `pre_time <= t < BUY_OPEN_TIME`. 09:00:00~05 에 시작한 루프가 P0 를 돌면 같은 봉인이 생긴다. `/api/trading/restart` 는 condition 5초 캐시를 비우지 않아서, P0 가 08:59:5x 캐시의 장 전 clean 값을 `now ≥ 09:00` 으로 기록해 「장중 clean」 이 되고, P1 은 그 종목을 건너뛴다. 그래서 그 5초 동안은 어떤 패스도 돌지 않고, P1 이 그 종목을 새로 읽는다. 보유 종목은 09:00:30 청산 패스가 읽으므로 잃는 것이 없다.
- **조회 한 번은 한 번만 기록한다.** leaf 자신의 패스가 조회하는 동안 그 종목은 `_pass_fetch_active` 에 있고, 훅은 그 종목을 건너뛴다 — 패스가 `src=p0|p1|inc|sell` 로 직접 기록한다. 둘 다 기록하면 모름 3회 상한이 조회 2번에서 끝난다. 🔴 훅은 **이중 try**(condition 쪽 + leaf 쪽)가 계약이다 — 예외가 새면 모든 FHKST 소비자가 깨져 VB·LTV 목표가가 서지 않는다(AST J16).
- 루프는 순수 planner `due_actions(now, …)` 로 할 일을 고르고 `_sleep(LOOP_TICK_S)`(1초)로만 기다린다. `FIRE_WINDOW_END`(15:28)가 지나면 `[status_exit_loop_exit] reason=after_close` 로 끝나고, `_running` 이 거짓이면 `reason=running_false` 로 끝난다. 재시작하면 그 시각에 맞는 패스부터 즉시 돈다(시작 때 오늘 발사 횟수를 되살린다 — 위 「보유 청산」). 루프가 끝난 뒤에도 그날 차단 항목과 관측 훅 기록은 살아 있다 — 게이트는 그날 계속 막는다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 킬스위치 — `system_config` 2키

- 🔴 **「키 없음」은 행 자체가 없을 때뿐이다.** 행은 있는데 모양이 틀리면(값 없는 dict · `{"value": null}` · JSONB null · 숫자 · 목록) 「알 수 없는 값」 이라 `observe` 다. getter 가 어휘 밖 마커 `__cycle369_malformed__` 를 돌려줘 그렇게 떨어진다(`src/db/CLAUDE.md`). 깨진 행을 `enforce` 로 읽으면 끄려던 시장가 매도가 켜진다.
- 🔴 **청산 패스는 발사 직전마다 메모리 모드를 다시 읽는다**(위 「보유 청산」). 그래서 패스 도중 PUT 한 `off` 는 그 패스의 뒤 종목부터 적용된다. 매수 게이트 `buy_gate` 도 호출마다 메모리 모드를 읽는다. 매수 패스(P0·P1·INC)의 조회 대상만 패스 시작 때 읽은 모드로 정해진다 — 조회만 하고 주문하지 않는다.
- 🔴 **즉시 반영 = `PUT /api/integrations/status-exit` — 메모리가 DB 쓰기보다 먼저다.** 라우트는 보낸 축을 먼저 `apply_mode(kind, mode, persisted=False)` 로 **고정 반영**한 뒤 DB 에 쓰고, 저장이 성공한 축만 `apply_mode(kind, mode, persisted=True)` 로 고정을 푼다. 이유 = `pg.execute` 는 커넥션 획득에 상한이 없어, RDS 가 멈추면 운영자의 `off` 가 30초 넘게 메모리에 닿지 못했다. 두 축을 함께 보내면 두 축 모두 메모리 반영을 끝낸 뒤 첫 DB 쓰기를 시작한다(`src/routes/CLAUDE.md`).
- 🔴 **저장에 실패한 축은 고정된 채 남는다.** 고정된 축은 그 축의 다음 성공 저장(`persisted=True`)이나 재시작까지 `refresh_modes()` 가 DB 값으로 덮지 않는다. 고정 동안은 `[status_exit_mode_pinned] kind= mode=` WARNING 을 1회/(날짜, 축) 남긴다. 이유 = 저장 못 한 `off` 를 다음 refresh(매수 60초 · 청산 300초 안)가 `enforce` 로 조용히 되살리면 안 된다. `apply_mode` 의 기본값(`persisted` 생략)은 저장 성공 취급이다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 관측 마커

- `cand=`(`[status_block_armed]`·스냅샷 `blocks[].cand`) = `_is_global_candidate(t)` = `t in buy_targets(registry)`. 즉 enabled 전략 후보 ∪ momentum 급등 목록에서 `registry.is_ticker_blocked_for_buy`(보유·주문중·당일매도)와 6자리 숫자가 아닌 것을 뺀 집합의 멤버일 때 1 이다(스윙 후보 포함). 그래서 보유 종목은 BFB `_candidates` 나 `ticker_prev_close` 에 남아 있어도 `cand=0` 이다 — 청산 패스의 armed 줄이 이 값을 부풀리지 않는다. 가장 최근 패스가 남긴 registry(`_last_registry`)를 읽기만 하고, 패스가 한 번도 안 돌았으면 0 이다. 이 값이 1 인 차단이 「진입 필터가 놓친 첫날」 빈도다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 테스트 격리와 가드

- 레지스트리가 모듈 전역이라 루트 `tests/conftest.py` autouse `_neutralize_status_watch` 가 매 테스트 전후 `reset_state_for_test()` 를 부른다. 마커 `real_status_watch` 가 없으면 `observe_fhkst` → no-op · `buy_gate` → `False` · `task_loop` → 즉시 반환으로 바꾼다. leaf·배선을 직접 검증하는 테스트만 마커로 옵트아웃한다. 🔴 이 중립화는 메타 가드 Y14 가 벽시계와 무관하게 봉인한다. 실 `task_loop` 는 15:28 뒤 곧바로 끝나서, 행위 테스트는 장중에 돈 실행에서만 중립화 제거를 잡기 때문이다(`test_6` 은 시계를 평일 10:00 KST 로 고정한다).

### 출처 절: strategy_base.py

- **트레일링 기준점 복구 단일 진실원**: `_apply_high_since_buy_from_candles(pos, candles, today)` — `buy_date < 영업일 < today` 일봉 high max 로 고점 보정(**올리기 전용**) + `update_high` DB 영속 + `[high_since_buy_recover]`. base 에 하나만 둔다 — **전략별 복제 금지**(`_HIGH_RECOVER_LABEL` ClassVar 로 로그 접두사만 다르게: donchian "도치안 스윙" / VCP "VCP"). 보조 파서 `_candle_trade_date`/`_candle_high` 는 KIS 원본 키(`stck_bsop_date`/`stck_hgpr`)와 DB 정규화 컬럼(`bas_dd` date 객체/`high_price`) **양쪽을 수용**한다 — `get_recent_daily_normalized` 가 raw 없는 row 를 row 자체로 반환하기 때문이다. `_candle_high` 는 `except Exception: return 0`(OverflowError 포함 — 봉 하나가 배치 복구를 중단시키면 안 된다). ⚠️ `recompute_high_since_buy` 자체는 base 승격 금지(전략별 fetch 소스·일수가 다르다 — donchian/VCP/BFB 자체 정의, kojiro 는 `recompute_held_atr` 에 내장). 소비자 분업 = `risk.on_tick`(메모리 갱신) → boot 훅(일봉 복구 + DB 영속)이고 **on_tick 에 DB write 금지**(회귀 가드).
  - 두 캡의 **자리**가 계약인 이유 = K축은 관측 **앞**(관측이 캡 이후 최종 수량을 재야 하고, 캡→0 이면 그 관측기는 `final_qty < 1` 로 자연 침묵하므로 차단 사실은 전용 마커가 담당한다) · ρ축은 관측 **뒤**(앞에 두면 차단된 랏의 ρ 관측이 통째로 사라진다).
  - **마커 5종** — `[fallback_notional_capped]`(INFO, 캡 발동. `path=fallback|sized`·`units_before`·`units_after`·`k`·`atr`) / `[fallback_cap_skipped]`(WARNING, `reason=` 6종 + `atr=`/`units=` 진단 병기 — PR 경로 fail-open 랏의 K 초과가 어떤 마커에도 안 남던 사각을 메운다) / `[fallback_cap_config]`(INFO 카나리아, 1회/전략/일, `cap=on|off`·`k`·`atr_max`) / `[fallback_cap_clamped]`(WARNING, **키가 명시 존재하는데** 범위 밖일 때만 — DB 미설정과 PUT 무효값을 구별한다) / `[oversized_fallback]`(ρ축 서식 + 꼬리 ` units=`). 전부 하나의 `DailyEmitCap[str]` 복합 키(`cap|t` / `skip|t|r` / `cfg` / `clamp`) + 날짜 키 자기 리셋 + **peek→로그→mark** 순서. **행위는 cap 밖** — 마커 성패와 무관하게 캡 수량을 반환한다.
  - **스코프와 항등식은 다른 문장이다 — 뭉치지 마라.** (a) 스코프 = `via_fallback`·`final == 1` 로 좁히지 않는다(축소 뮤테이션을 F-5b/F-5c 가 봉인). 현행 7 전략 호출부에서는 주 분기가 정의상 ρ상한 이하라 프로덕션 도달이 없고, 이 조항이 지키는 것은 **장래 회귀**다. (b) 항등식 `notional ≤ K_ρ × int(예산 × position_ratio)` 는 관문을 지나는 모든 랏에 성립한다 — 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산 × position_ratio)//price)`)이 명목을 이미 컷오프 이하로 묶어 두므로 `final <= cap_qty` 로 항등적으로 무접촉이고, **실효는 1주 폴백 랏(`price > 예산 × position_ratio`)뿐**이다.
  - **fail-open 경계** — 키 부재 = **캡 OFF**(K축 `_read_max_lot_units` 의 "키 부재도 기본값" 관례와 **반대**다: 이 캡은 *매수를 막는* 통제라 fail-closed 는 유령 키 재현 경로다) / K축 심사 = 조용히 통과. `no_ratio`·`no_budget`·`no_cap`·`k_axis_probe_error`·`exception` = **현행 수량 유지 + `[ratio_cap_skipped]` WARNING**. 어떤 결측·예외도 수량을 0 으로 만들지 않는다.
  - **마커 4종** — `[ratio_notional_blocked]`(INFO, 차단·축소 행위. `path=fallback|sized`·`price`·`cap`·`cutoff`·`k`·`ratio`·`req_qty`·`capped_qty`·`budget`·`pos_ratio`) / `[ratio_cap_skipped]`(WARNING, `reason` 5종) / `[ratio_cap_config]`(INFO 카나리아 — **`cutoff_price` 필수 필드**, 운영자가 아침에 "오늘 LTV 는 130,100원 넘는 종목을 못 산다" 를 한 줄로 읽는 근거) / `[ratio_cap_clamped]`(WARNING). 전부 K축 `_lot_cap_logged` 와 **별개 인스턴스**인 `_ratio_cap_logged: DailyEmitCap[str]` 복합 키(`blk|t` / `skip|t|r` / `cfg|cap상태|k|cutoff` / `clamp|raw`) + 날짜 키 자기 리셋 + peek→로그→mark + 예외 전부 흡수. **행위는 cap 밖** — 마커 성패와 무관하게 차단은 매 호출 수행한다. `[ratio_cap_config]`/`[ratio_cap_clamped]` 의 키는 **값-민감**이라 "1회/전략/일" 이 아니라 **"1회/(전략, 값 조합)/일"** 이다 — 정상 운영은 하루 1행이고 K·예산이 실제로 바뀐 날에만 1행이 더 붙는다(= 공식 롤백 PUT 을 확인하는 유일 채널). 라벨은 `off|on` 2종이다.
  - **오귀인 판독** — 캡→0 은 `order_engine.execute_buy` 의 `quantity <= 0` 경로로 흘러 `block_low_funds(+900s)` + "매수 수량 0 → 900s cooldown (투자금: …)" WARNING 을 남긴다(8영역이라 무접촉). `_bought_today` 가 있는 4전략(`donchian_swing`·`kojiro`·`vcp_breakout`·`bull_flag_breakout`)은 종목당 1회/일이라 캡 마커와 **1:1**, 없는 3전략(`momentum`·`volatility_breakout`·`long_tail_volatility`)은 900s 만료 또는 `_sync_positions_from_balance`(≈15분)의 `clear_low_funds()` 로 같은 종목을 하루 3~4번 재시도해 **1:N** 이다(실측 LTV 095610 4행·131290 3행). 판독 규칙 = 같은 (전략, ticker, 일자)에 `[fallback_notional_capped]` 나 `[ratio_notional_blocked]` 가 **한 행이라도** 있으면 그날 그 종목의 **모든** 수량-0 WARNING 을 캡 귀속으로 읽는다(캡 마커는 1회/일이라 2행째부터는 단독으로 보인다).
  - **21:30 일일 리포트 미도달** — 4마커는 INFO 2 / WARNING 2 이고 `log_analysis_engine._aggregate_log_patterns` 는 `{WARNING, ERROR, CRITICAL}` 만 패턴 집계하므로 `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 리포트 payload 에 한 글자도 안 들어간다. 반대로 오귀인의 **원인**인 수량-0 WARNING 은 `top_patterns` 에 오른다 ⇒ 리포트만 읽으면 "투자금 부족 급증" 오결론이 나온다. 판독은 `system_logs` 직접 조회가 유일 채널이다(집계 편입은 후속 F-12).
  - **K_ρ 취급** — `_read_max_lot_ratio_mult` 가 `[1.0, 20.0]` 로 클램프한다(비수치·bool·비유한·<MIN → 기본 2.5 / >MAX → 20.0). **하한 1.0 이 "정상 비중 랏 무접촉" 항등식의 수학적 전제**다 — 1.0 미만을 허용하면 주 분기까지 잘려 전면 무매매가 된다. `_MAX_LOT_RATIO_MULT_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 **7 전략 전부**의 `DEFAULT_PARAMS` 리터럴과 동치여야 한다(`G-245-6`, glob 전수). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(`G-245-1`) + AI 자문 자동 적용 경로 편입 금지. 롤백 = 해당 전략 K_ρ=20.0 — ⚠️ `PUT /api/strategies/{id}/params` 는 **즉시**, `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만** 반영된다(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 `_boot` 재호출은 no-op). 보유 중 장중 재시작이 금지(D6)이므로 **장중 실효 롤백 수단은 PUT 뿐**이다.
- **시장 유닛 헬퍼 (cycle382 — 터틀 4전략 `kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout` 한정)** — 규칙 요약 = 루트 [`CLAUDE.md`](../../CLAUDE.md) 「자금 관리」 절 · 판정 = 모듈 맵 `market_unit.py`. 관문 `_apply_budget_limit` 본문은 이 헬퍼들과 무관하다(소스 세그먼트 sha 불변, AST A12). 나머지 3전략은 속성만 물려받고 부르지 않는다(AST A04).
  - **계산 자리 = 4전략 `prepare()`** — `_resolve_prepare_as_of(as_of)` 바로 다음 줄에서 `await self._refresh_market_unit(as_of_date=, preview=)` 를 정확히 1회 부른다. 어떤 조기 `return` 보다 앞이다(AST A08). 결과는 전략 객체의 `_market_unit_snaps: dict[date, Snapshot]` 에 **거래일별로** 담고, 오늘(KST)보다 과거 키는 지운다(「오늘 · 다음 거래일」 두 칸). 저녁 미리보기(`as_of` = 다음 거래일)는 다음 거래일 칸만 쓴다. 이 헬퍼는 `_candidates`·`positions`·`_entry_atr`·`_position_setup`·`_position_atr`·`_breakout_high` 를 읽지도 쓰지도 않는다(PV-1 과 교집합 0, AST A07). **보존 규칙** = 같은 날짜에 `ok=True` 스냅샷이 있으면 새 실패가 덮지 않는다(`kept=1`) — 21:00 미리보기의 좋은 값을 다음 날 부팅의 일시 DB 실패가 지우지 않게 한다. 새 스냅샷이 `ok=True` 면 항상 덮는다. 모드가 `off` 여도 계산한다 — 그래야 `enforce` PUT 이 재시작 없이 먹는다. never-raise.
  - **`calc_buy_quantity` 첫머리**(4전략 같은 모양, 기존 본문은 그 아래 그대로) — `_market_unit_sizing(price, ticker)` 는 `enforce` ∧ m<1 일 때만 값을 돌려준다. `shadow` ∧ m<1 은 `[market_unit] where=calc` 한 줄과 일일 집계만 남기고 `None`(수량 불변). m=1 인 날은 calc 줄이 없다. 값이 오면 `lot_after <= 0` → `return 0`(폴백·낙하 없음), 아니면 `_apply_budget_limit(lots.design_after, …)` 다. 터틀 경로의 donchian·BFB·VCP 는 `_entry_atr[ticker] = lots.atr` 를 찍는다(= 사이징 ATR, m 과 무관 — 손절선이 m=1 랏과 같다). kojiro 는 이 줄이 없다 — `_position_atr` 을 신호 시점에 찍는다.
  - **마커 2종**(로거 `src.engine.strategy_base` · cap = 인스턴스 `_buy_paused_logged: KstDailyEmitCap[str]` · peek→로그→mark · 실패 = `trace_observer_failure` · **행위는 cap 밖** · `write_log` 병행 0, AST A13). `[buy_paused_config] strategy= paused= valid= raw= note=` = 설정 카나리아, 1회/(전략, 값)/일(키 `cfg|{paused}|{valid}`). `paused=1` 과 `valid=0` 은 **WARNING**, `paused=0 valid=1` 은 INFO 다. WARNING 인 이유 = 21:30 일일 분석 상위 WARNING 에 매일 올라, 멈춘 전략의 무매매가 결함으로 오진되지 않게 한다. `[buy_paused_skip] strategy= ticker= cand=1 dropped= note=` = INFO, 1회/(종목, 전략)/일(키 `skip|{ticker}`). 후보 판정 `_is_status_gate_candidate` 가 참인 종목만 남기고, 후보가 아니면 mark 하지 않는다(장중에 뒤늦게 후보가 된 종목도 기록되게). `dropped` = 실제로 지운 래치 이름(`breakout_first_seen,vol_latch` 또는 `-`). INFO 인 이유 = 운영자가 정한 상태의 결과라, WARNING 이면 진짜 경고를 밀어낸다(AST A15). ⚠️ 두 줄 모두 그날 게이트가 한 번은 닿아야 찍힌다 — momentum·VB 는 돌파가, donchian·kojiro 는 09:05 뒤 스윙 폴 후보가 있어야 한다. 멈춤 여부의 정본은 로그가 아니라 `GET /api/strategies` 와 DB `strategy_config.params` 다.
  - 🔴 **운영 함정 둘** — (a) 서버 기동 때 설정 로드(`main.py` → `_load_strategy_config`)가 실패한 채로 PUT 하면, 메모리의 코드 기본값 전체가 `save_params` 로 DB 에 써진다. PUT 전에 GET 의 운영값(`sizing_mode`·`max_positions`·`stop_loss_rate`)이 DB 와 같은지 본다(실패 흔적 = 「전략 설정 초기 로드 실패」 WARNING). (b) 멈춰 둔 동안 키를 지운 코드를 배포하면, `_load_strategy_config` 의 `if key in strategy.config.params` 가 DB 의 `true` 를 버려 조용히 풀린다.

### 출처 절: risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호.
- **손절 로그는 임계를 함께 찍는다** — momentum `check_exit_signal` 의 손절 INFO 는 `stop_loss` 임계를 인자로 싣는다. 운영 DB `strategy_config.momentum.params.stop_loss_rate` 가 코드 기본값과 다를 때 운영자가 로그 한 줄로 실제 임계를 확인하는 유일한 장치라 **임계 인자를 빼지 않는다**.
- **레짐은 매수를 차단하지 않는다(관찰 전용)** — `risk.on_tick`·swing 폴에 레짐 게이트가 없다. `get_buy_block_state`/`BuyBlockState`/`buy_block_mode` 는 대시보드·AI자문 payload **표시 전용**이고 `to_advisor_dict()`·`GET /api/market-regime/current` 는 `buy_blocked=False` 를 낸다(`block_reason` 은 방어 '권고' 관찰용으로 유지). `execute_buy` 의 `soft_multiplier` 파라미터는 vestigial 이다. 레짐 대응은 `cash_usage_ratio`(`auto_regime_adjust`)뿐이다. 🔴 이 게이트를 복원하지 마라. 회귀 `test_regime_observation_honesty.py`. 시장 유닛(cycle382)은 레짐 게이트가 아니다 — `risk.on_tick`·swing 폴에는 게이트가 없고, 터틀 4전략의 `check_buy_signal`·`calc_buy_quantity` **안**에서 전략 사이징으로 작동한다(`strategy_base.py` 절)
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. 후자는 `[risk_silent_skip] ticker=009150 strategy=volatility_breakout reason=price_gt_total_investment price=1186000 total=352217` INFO 를 1회/(ticker,전략)/일 남긴다(`_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]` — 매 틱 폭주 차단). `scheduler._reset_daily_state` → `RiskManager.reset_daily_state()` 위임 + AttributeError 후방호환 가드.
- **가격 필터(scanner 단계, 매수 진입 전용)**: `scanner.subscribe_filtered_stocks` 안의 단일 hook `_apply_price_filter` — 임계는 `system_config` 의 `price_filter_min`/`price_filter_max`(기본 비활성), 기준가는 `stock_master.raw.prdy_clpr` 단독이고 미확보는 graceful 통과다(scanner 단계는 WS 구독 *전*이라 `current_price` 가 없고, KIS `inquire-price` pre-fetch 는 Rate Limit·hot path 부담으로 비채택). 🔴 **보유·익일청산 3중 보호** = 공통 헬퍼 `_collect_protected_tickers_for_scanner()`(`registry.all().positions` ∪ `_pending_next_day_clear`) + `_apply_price_filter` 최상단 early-return(`if ticker in protected_tickers: survived.append(ticker); continue`) + AST `protected_tickers=` keyword 의무 가드. 60s TTL 캐시(`time.monotonic`) + `invalidate_price_filter_cache_scanner()` 즉시 무효화, **unsubscribe 발화 0건**(다음 `_scan_loop` 5분 자연 delta — KIS LMS chain 차단). 임계 외 종목은 `[price_filter_scanner_skip] ticker=… prdy_clpr=… reason=below_min|above_max min=… max=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_price_filter_scanner_daily_summary()` 가 `[price_filter_scanner_daily_summary] min=… max=… skip_count=N` 1행(일일 카운터 `_price_filter_scanner_skip_count: dict[str, int]`)을 남긴다 — 🔴 그 호출은 **try/except 로 감싸지 않는다**(감싸면 폐기 메서드 잔존 호출 같은 결함이 AttributeError graceful skip 으로 조용히 먹히고 운영 가시화가 무력화된다) + `_reset_daily_state()` 동행 리셋. funnel `step_no=98`. 🔴 `risk.on_tick` 에 가격 필터를 두지 않는다(AST G-1 — 필터는 구독 대상 결정이고 매매 신호 판단이 아니다). UI `PriceFilterCard.tsx`.
- **거래대금 필터(scanner 단계, 매수 진입 전용)**: `_apply_trade_amount_filter` — 임계 `system_config.trade_amount_filter_min`(기본 0 = 비활성, UI 0~100억 step 1억 + 권장값 마커 1억/5억/10억). 가격만으로는 작전주를 못 가른다는 판단의 동행 필터다(5,000원 통과 + 거래대금 5천만 = 작전 신호). 임계 조회 = `_get_trade_amount_filter_for_scanner`(60s TTL). 소스 3분기(`_get_acml_tr_pbmn`) = `scanner.ticker_market_info["trade_amount_raw"]`(원 단위 정밀값, scanner 가 이미 `fetch_rising_stocks` → `fetch_stock_detail` 로 `acml_tr_pbmn` 을 보강하므로 **KIS 호출 추가 0건**) → `stock_master.raw.acml_tr_pbmn` 폴백 → 🔴 **둘 다 miss 이거나 0 이면 graceful 통과**(09:00 직후 누적 거래대금 0 으로 후보를 차단하면 시스템 매매가 통째로 무용해진다). 기존 `trade_amount`(억 단위 round) 키는 UI·API 호환으로 보존한다. 순서 = `_apply_price_filter` → `_apply_trade_amount_filter` 순차 hook, `subscribe_filtered_stocks` 4 호출 경로(tickers + extra_tickers + breakout/momentum for loop + swing) 전부 경유. 보호 종목은 `_collect_protected_tickers_for_scanner()` 재사용 + **별도** 60s TTL 캐시 + `invalidate_trade_amount_filter_cache_scanner()`. 로그 `[trade_amount_filter_scanner_skip] ticker=… acml_tr_pbmn=… reason=below_min min=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_trade_amount_filter_scanner_daily_summary()` 가 `[trade_amount_filter_scanner_daily_summary] block_count=N` 1행(**try/except 로 감싸지 않는다**) + `_reset_daily_state()` 동행 `_scanner_mod.reset_trade_amount_filter_daily_state()`. funnel `step_no=97`(가격 필터 98 보다 *전* 단계 표기). 모듈 전역 4 필드 = `_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` / `_trade_amount_filter_scanner_skip_count_today: dict[str, int]`. UI `TradeAmountFilterCard.tsx`.

### 출처 절: market_regime.py

- `MarketRegime.from_macro_cycle(macro)` — `/api/macro/macro-cycle` 응답 파싱(우리 macro 컨테이너. 외부 dkstock 과 **같은 코드(macro_lite)** 라 shape 가 같아 전환 시 파서 무변경이었다). 🔴 `buffett_ratio` 는 `regime.buffett_ratio` 에서 읽는다(`params.pbr_max` 아님 — 그쪽은 PBR 상한이라 전 계층 null 을 만든다).
- **지수ETF 고지로 스테이지 레짐 신호 (관찰 전용)**: `DEFENSIVE_STAGES=frozenset({3,4,5})`(고지로 대순환 하락 사분면) + `is_two_day_defensive(stages)`(최근 2 스테이지 모두 방어집합, None/len<2→False = whipsaw 히스테리시스) + `EtfStageSignal` frozen dataclass + `compute_etf_stage_signal(now=None)` async(KODEX200 069500 + 코스닥150 229200, 일봉 seam=`stock_master_daily.get_recent_daily` DESC→ASC 정렬 후 `kojiro_indicators.ema(5/20/40)`+`stage_of` 순차 → 각 지수 스테이지 + 2일 방어, `etf_defensive` = 신선 지수 OR·양쪽 stale→None) + `_is_daily_row_stale`(달력 `ETF_STALE_MAX_CALENDAR_DAYS=10`, never-raise) + `get/set_current_etf_signal` 싱글톤. **레짐 독립** — boot(`_refresh_market_regime_and_persist` 의 `set_current_regime` 직후)가 macro fetch 성패와 무관하게 계산하고 `[etf_regime]` 을 남긴다. 🔴 **관찰만** — `get_buy_block_state`/blocked/reasons/soft_multiplier 무변경(배제 0). `etf_regime_enabled=False`(`system_config`) 다크런치. ETF 전용 5/20/40 파라미터화 금지(정체성 상수), kojiro 전략·파라미터·포지션 무접촉. ETF 스테이지를 매수 가드(`block_reason`·SOFT 상한·reasons)로 통합하지 않는다(E-2 계획 폐기 — 사용자 결정 2026-09-27, cycle382). 장세에 따른 신규 진입 축소는 `market_unit.py` 가 전략 사이징에서 맡는다.
- **레짐 가드 silent inert 가시화 (관찰성 전용)**: `has_regime_data` property(`regime`/`vix`/`fear_greed_score` 중 하나라도 not None 또는 `bool(raw)` — `empty()` 폴백은 전부 None+raw={} 라 False 이고 `persist_snapshot` 의 `regime is None` empty 판정과 정합) + `BuyBlockState.data_available: bool=True` 필드 + `get_buy_block_state()` 5개 생성분(OFF/HARD/WARN/SOFT/unknown-fallback) 전부 `data_available=self.has_regime_data`. 🔴 blocked/soft_multiplier/reasons 로직과 60s TTL 캐시는 **완전 무변경 = fail-open 보존**(신규 필드는 표시·경보 전용). 고치는 것 = "데이터 있고 임계 미발동" 과 "데이터 없음(empty)" 이 같은 `blocked=False, reasons=[]` 라 운영자가 구분할 수 없던 결함이다(외부 서버 인증서 만료가 4일 동안 무경보로 레짐을 무력화한 사례). boot 경보 = `get_buy_block_mode()` graceful 조회 후 `not has_regime_data and mode != "OFF"` 면 `[regime_guard_inert]` WARNING 1회/일.
- `refresh_from_dkstock(timeout=None)` — `macro_client` → MarketRegime. 모든 예외 흡수 → empty. 실패 사유는 `reason=disabled|timeout|fetch_failed|exception` 으로 구분해 WARNING 1행. 🔴 **`.env` 단독 veto 를 두지 않는다** — client 보다 앞에 두면 DB 우선 판정이 영구 도달 불가가 되어 운영 토글이 죽은 스위치가 된다(cycle315 가 그 결함을 걷어냈다). 🔴 **함수명은 계약이다** — `scheduler.py`(승인 대상)가 이 이름으로 부르므로 개명하면 무관한 승인 절차가 딸려 온다. `timeout` 은 부팅 경로가 더 짧게(`macro_api_boot_timeout_secs`=25s) 넘긴다 — 그 자리는 `boot_manager` 인라인 await 이고 바로 다음 줄이 자금 배분이라, 차가운 macro 가 재시작 직후 tick blind 창을 늘린다.

### 출처 절: order_engine.py

- 락/cooldown 은 다음 잔고 sync (15분) 에서 `unblock_buy()` + `clear_low_funds()` 일괄 해제
  - **NXT 불가 사후 보강**은 `target_exchange ∈ ("NXT","SOR")` ∧ KST **08:00~08:50**(NXT 프리마켓 실질 종료 = GTP 미체결 일괄취소 = `market_state` N1.end)일 때만 `stock_master.upsert_one(ticker, nxt_tradable=False)` 를 쓴다. 🔴 KRX 로 보낸 주문의 거부에는 **절대 쓰지 않는다** — KRX 애프터마켓(16:00~20:00)이 구 `15:30~20:00` 창 안에 통째로 들어와 있어 시계 단독으로는 어느 시장의 거부인지 가릴 수 없고, 잘못된 낙인은 16:10 CTPF1002R 재적재 창을 지나치면 다음 영업일 프리장까지 ≈24h 존속하는 자기 강화 래치가 된다. 판단 불가를 fail-safe 로 쓰지 않는다. 마커 `[nxt_post_reinforce] ticker= exchange= div= now= wrote=1|0 reason=nxt_pre_window|exchange|window` — `wrote=0` 이 D+1 판독의 분모다.
  - **진입 게이트 2단계 TTL**: KRX 메인(09:00~15:30) 거부 = **5분 TTL**(일시 장애 가정) / NXT 시간대 거부 = **다음 KST 09:00 TTL**. TTL 미경과면 KIS 호출 없이 skip 하고 INFO `[market_closed_blocked]` 를 1줄/ticker/일 남긴다(`reason` 필드 포함). `SellRejectionTracker.register_market_closed(in_krx_main_hours=...)` 위임이고, `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 가 5 필드(`_alarm_last_emitted` 포함)를 일괄 위임한다 — `scheduler._reset_daily_state()` 의 위임 호출을 보존한다.
- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`. 폴백 결과(성공/실패) 무관 `SellRejectionTracker.register_market_order_disallowed(fallback_succeeded=...)` 위임 → **30초 TTL** 등록(동일 tick 폭주 차단). NXT 시간대 폴백 실패(`is_nxt_session=True, fallback_succeeded=False`)면 `RejectionResult.next_day_clear_required=True` → `_pending_next_day_clear_provider().add((ticker, strategy_id))` + `[next_day_clear_deferred]` WARNING 1행. 폴백 실패 시 `_selling.discard` + positions 보존. 지정가 매도(`limit_price>0`)는 폴백하지 않는다. 키워드 = `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리`(APBK1943 / APBK3013)
- **`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조**: APBK0400 "수량 초과" 는 부분 보유 내재 코드라 insufficient(통째 삭제)로 **흡수 금지**다(257720 실사고). `execute_sell` 재시도 루프에서 closed 다음·insufficient 앞에 `get_balance` 재대조. `0 < sellable < positions` 이면 먼저 `_sell_orders_snapshot`(TTTC0081R `get_daily_orders(exchange="ALL", pdno=ticker)` 1건, 2.0초 상한)을 읽고 포지션 객체 동일성을 다시 본 뒤 `eff = positions − 아직 안 온 체결 통보`(`_sell_pending_dec` — 원장 시작 전 접수 주문은 세지 않는다, 조회 실패면 `eff = positions`)로 가른다 — ① 오염(`held < eff`) = **held(보유 실체)로 보정**(sellable 아님 — 잠긴 주식도 보유라 손절 감시 수량은 held 가 정합이고, sellable 부족 재거부는 다음 분기가 흡수한다) + `save_position` DB 동행 + `continue`(3회 한도 내 자기 치유). 보정 전에 주문별 「스냅샷에 이미 반영된 체결」 크레딧을 적는다(조회 실패면 종목 크레딧에 더한다) — 늦은 체결통보가 같은 체결을 두 번 빼지 않게 하는 장치다(「매도 체결 — 주문 축과 보유 축」 절) ② 부분 잠김(`held ≥ eff`) = `fire = sellable − (held − eff)` 이 1 이상이면 그 수량만 판다(`[sell_qty_partial_sellable]`, `pos.quantity` 무변경). 0 이하이거나 조회를 못 믿으면, 전량 잠김(`sellable == 0 ∧ held > 0`)과 같이 `[sell_qty_partial_locked]`(걸린 매도 있음)/`[sell_qty_unnoticed_fills]`(걸린 매도 없음 · 주문 조회 성공)/`[sell_qty_hold_orders_unavailable]`(걸린 매도 없음 · 주문 조회 실패)/`[sell_qty_locked]` WARNING + 보존 + `_selling_locked_wait` 표식 + return — **`_selling` 의도적 유지**(열린 기주문이 실재하거나, 걸린 것이 없으면 운영자 몫을 팔지 않으려고 미통보 체결을 기다리는 보류이고(명세 부록 R4 D1), on_tick 재진입 폭주를 차단한다. 어느 주문이든 종료 통보가 오거나 지키던 보유가 닫히면 푼다. stale 은 `[selling_reconcile]` 180s 재대조 소관. market_closed 의 discard 와 다른 이유 = 그쪽엔 열린 주문이 없다) ③ 실보유 0 = 기존 insufficient 경로 재사용 ④ 재대조 실패 = graceful 일반 재시도. ⚠️ sync 는 기보유 종목 수량을 갱신하지 않으므로 DB 보정 실패 시 구값이 다음 보정·청산까지 남는다
체결통보 race 가드:
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 단일 COMPLETED row 를 보장한다. 규칙 3개:
  - ② PENDING INSERT 의 `await` 도중 체결통보가 먼저 완주해 migration 029 부분 UNIQUE 를 위반하면, `_insert_pending_or_absorb_race(side="buy"|"sell")`(**매수·매도 4 지점 공용** — 각 축의 시장가·폴백)가 **`order_no in _completed_orders` 일 때만** 흡수·discard 하고 `[buy_fill_during_insert]`/`[sell_fill_during_insert] ticker= order_no= strategy= path=market|fallback` INFO 1행을 남긴다. 🔴 증거 없는 위반은 그대로 전파한다(다른 원인 은폐 금지). 회귀 `test_cycle271_execute_buy_fill_during_insert.py` · `test_cycle327_sell_fill_during_insert.py`
  - ④ 🔴 **`place_order` 가 성공한 뒤의 실패는 「발사 실패」가 아니다** — 매핑 등록 이후 구간(선행 체크·PENDING INSERT)은 자체 `try/except Exception` 으로 닫히고 `[sell_post_send_error] ticker= order_no= strategy= path=` 를 남긴 뒤 **재시도 루프로 돌아가지 않는다**. 매도 재시도 루프는 발사 직전 `strategy.state.positions.get(ticker)` 를 **재조회**해 포지션이 사라졌으면 `[sell_position_gone]` 1행 후 중단한다(루프 밖 지역 참조 `pos` 는 체결 뒤에도 옛 수량을 들고 있다 — 피라미딩에서는 그 재조회가 수량의 유일한 진실원이 된다). 이것이 없으면 DB 타임아웃·페일오버 한 번이 **이미 판 것을 다시 판다**(cycle327 **돌연변이 재현** 3회 발사 — 운영 로그의 사고 기록이 아니다. 매도 부분체결 실적은 5개월간 0건이고, 부분체결은 유동성이 얇아지는 순간에 몰린다). 회귀 `test_cycle327_sell_fill_during_insert.py::test_sell_does_not_refire_on_generic_insert_error`
  - ⑤ 🔴 **그 경계는 매도 두 경로가 공유한다 (cycle328)** — `_persist_sell_pending_after_send(*, ticker, order_no, strategy_id, record_price, quantity, path)` 가 선행 체크·PENDING INSERT·경계를 한 곳에 담고 주 경로(`path="market"`)·폴백(`path="fallback"`)이 같은 함수를 부른다. **경계는 호출부 문맥이 아니라 헬퍼 자신의 `except Exception` 에 있다** — 호출부가 어디에 있든 "이 문장은 예외를 던지지 않는다" 가 유지되게 하려는 것이고, 두 호출부의 피해 모양이 다르기 때문이다(주 경로가 새면 재시도 루프 → **그 종목 중복 매도**, 폴백은 `except KisApiError` **안**이라 형제 핸들러가 non-`KisApiError` 를 못 받아 `execute_sell` 을 관통 → **`risk.on_tick` 사망 = 그 틱의 전 보유 종목 손절 평가 소멸**). 🔴 **그 `except` 를 좁히지 않는다** — 격리 스냅샷 실측(관문 리뷰 2026-09-20): `except (UniqueViolationError, TimeoutError, OSError)` 로 좁히면 기존 행위 회귀 13건이 **전부 초록**인 채로, 폴백+`KisApiError` 에서 **접수 성공한 주문을 장부에 「폴백 모두 거부」로 적고 `_selling` 을 풀고 `_pending_next_day_clear` 에 넣어 익일 09:00 에 다시 판다**(`positions` 는 안 변해 화면·DB 로는 정상으로 보인다). 주 경로+`KisApiError` 는 발사 **3회**. 행위 테스트로는 못 막는다(그 열거가 같은 누락에 노출된다) — 구조 가드 `tests/unit/ast/test_cycle328_sell_pending_helper.py::test_g328_3b`(최상위 `try` 1개 · 핸들러 1개 · 타입 `Exception`)가 유일한 방어다. 헬퍼 **앞부분에 `await` 를 넣지 않는다**(최초 양보점이 `await insert_trade` 라는 사실이 「매핑은 동기 영역」 금기의 전제 — `test_g328_2`). 경로 수식어 `_SELL_PENDING_SKIP_PATH_LABEL` 은 `.get(path, "")` 총함수다(`[path]` 면 **정상 경로인 체결통보 선행**이 에러 마커를 뱉어 그 창의 유일한 관측 채널을 오염시키고, `discard` 가 로거보다 **앞**이라 운영자의 수동 복구가 중복 행을 만든다 — `test_g328_4`). 값 4개(`record_price`/`quantity`/`path`/`order_no`)는 `test_order_engine_sell_fallback.py` 시나리오 J 3건이 봉인한다(그 전에는 맞바꿈·뭉갬이 광역 스위트를 **전부 초록으로 통과**했다). ⚠️ 폴백 `[sell_post_send_error]` 의 **꼬리 문구가 2026-09-20 에 주 경로와 통일**됐다 — 21:30 리포트 `top_patterns` 는 `_normalize_message` 가 메시지 전문을 패턴 키로 쓰므로 **그 날짜 전후의 패턴 문자열을 비교하지 않는다**(마커 + 4필드는 byte 동일)
  - ③ `update_trade_status(*, order_no=None, match_partial=False)` 의 `order_no` 는 keyword-only opt-in 이고 미전달 시 SQL 이 byte 동일하다. `order_engine.py` 의 호출 6곳(C1 매수 COMPLETED · C2 매수 PARTIAL · C3 매도 COMPLETED · C4 매도 PARTIAL · C5 `_cancel_after_wait` 매수 CANCELLED · C6 `_cancel_and_reorder` 매도 CANCELLED)이 전부 지역 변수 `order_no` 를 그대로 전달해 WHERE 를 **그 주문 한 건**으로 좁힌다 — 근거 = order_no 없는 WHERE 가 같은 `(ticker, trade_type, strategy)` 의 **다른 주문 행**까지 함께 덮어 한 체결통보가 여러 PENDING 행에 같은 price·profit_loss 를 도배한 사고(161580). `affected>1` 이면 `src/db/trade_history.py` 한 곳에서 `[trade_status_multi_update]` WARNING — order_no 있는 호출은 부분 UNIQUE 인덱스(migration 029) 때문에 구조적으로 발화 불가라 **과거 측정기가 아니라 WHERE·인덱스 후퇴 회귀 감시자**다.
- **규칙 1 — 시각이 거래소를 정한다(cycle287).** `_probe_nxt_downgrade_base` 가 정한 다운그레이드 결과(`base`) **뒤**에, `_strategy_exchange_async`(반환 시점 1회) · `_apply_clock`(그 밖 4곳)이 순수 함수 `_route_exchange_by_clock(base, *, side, mode, now)` 로 감싼다. 판정은 `market_state.MARKET_TABLE` 단일 정본만 읽는다(`order_engine.py` 안 시각 리터럴 0건) — `base ∉ {"NXT","SOR"}`(이미 KRX)→그대로 / `mode=="off"`→그대로 / `mode=="sell_only" ∧ side=="buy"`→그대로 / `session_tracker.active` 가 `PRE_NXT` 단독(PR-F 와 같은 출처, 08:50~09:00 NXT 휴장 구간도 이 판정으로 base 유지)→그대로 / 그 시각 KRX 가 우리 `OrderDivision` 값 집합(`_SENDABLE_DIVISIONS`) 중 하나라도 받으면 `"KRX"` / 아니면 그 시각 NXT 가 받으면 base 유지 / 둘 다 안 받으면 base 유지. 예외는 전부 `probe_error` 로 base 유지(fail-safe — 판정 실패가 주문을 막지 않는다). `active` 가 비었을 때만(기동 직후 첫 `tick()` 전) `session.boards_at(moment.time())` 로 즉석 재계산하는 폴백이 clause 4 를 지킨다 — 없으면 08:20~09:00 프리장 창이 KRX PRE_AUCTION 으로 조용히 샌다. 적용 지점 = `_strategy_exchange_async` 반환 1 + `_apply_clock` 4(`limit_price>0` 분기·`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`)이고 mode/dial 조회는 `_clock_params` 공유다. 마커 `[order_channel] side= ticker= strategy= base= exchange= reason=`(`routed≠base` 일 때만. 단 `probe_error` 는 게이트 밖에서 항상 남긴다 — 라우팅이 죽은 것과 정상 유지(`pre_nxt_keep` 등)가 똑같이 침묵하면 안 된다) + `[order_channel_config] strategy= mode= division=`(카나리아, 1회/(전략,mode,dial)/일).
  - ⚠️ **두 키는 `exchange ∈ {"NXT","SOR"}` 일 때만 효력이 있다** — `_route_exchange_by_clock` clause 1(`base ∉ {"NXT","SOR"}`→그대로)이 mode 검사보다 **앞**서므로, 어떤 전략의 `exchange` 가 `"KRX"` 이면 그 전략은 `enforce`/`sell_only`/`off` 세 값이 전부 동일한 무동작이다. 코드 기본값은 7전략 전부 `"KRX"` 이고 운영 DB 는 7전략 전부 `"NXT"`(2026-09-13 사용자 결정 D3 로 `SOR`→`NXT` PUT 완료, SOR 잔여 0)라 현재는 두 스위치가 실제로 작동한다 — `NXT` 도 `_CLOCK_ROUTED_BASES` 안이라 라우팅 판정은 불변이다. `exchange` 를 KRX 로 마이그레이션하는 사이클은 이 두 키의 help 도 함께 갱신한다.
  - ⚠️ `order_engine.py:67-70` 의 이 절 관련 주석과 `param_validation.py:3` docstring 의 "99 스펙"(실제 101)은 낡았다 — 두 파일 모두 무접촉 계약 대상이라 다음 8영역 승인 사이클의 과제다.
  - **왜 라우터 밖인가** — `_strategy_exchange_async` 는 `_probe_nxt_downgrade_base` 를 먼저 부르고, 그 함수는 `stock_master.nxt_tradable=False` 종목에 `"KRX"` 를 돌려준다. 그 코호트(마스터 **83.2%**)는 라우터에 `base="KRX"` 로 들어가 clause 1 에서 **즉시 반환**되어 뒤 clause 에 닿지 않는다 — 라우터 안에 컷을 넣으면 컷이 가장 필요한 다수 코호트를 통째로 비껴간다.
    - 🔴 **그 잔량을 우리가 거두는 경로는 없다.** `cancel_remaining` 은 `src/` 안에 호출자가 0 이다. 배선해도 해결되지 않는다 — 그 함수는 `pos.order_no`(포지션을 만든 **매수** 주문번호)를 취소한다. `risk.on_tick` 재평가도 새 매도를 낼 수는 있어도 걸린 주문을 취소하지 않는다.
    - 잔량이 어떻게 되는지는 거래소가 정한다(아래 session.py 절 「주문 존속 규약이 거래소마다 반대다」). KRX 잔량은 정규장 마감 후 거래소가 자동 취소한다. NXT 잔량은 애프터마켓이 끝나는 20:00 까지 남는다.
    - `execute_sell` 의 매도가 KRX 가 아닌 곳(base `NXT`/`SOR`)으로 나가는 것은 규칙 1 이 base 를 유지할 때뿐이다 — 프리장 `pre_nxt_keep` · `order_exchange_clock_mode="off"` · `probe_error`. KRX 가 우리 호가를 받는 시각(09:00~15:30 · 16:00~20:00)에는 clause 5 가 KRX 로 보낸다.
  - 🔴 **신선도 기반 해제를 들이지 마라** — `scanner.ticker_last_tick` 신선도로 컷을 풀면 안 된다. ① `risk.on_tick` 이 **같은 콜스택**에서 그 dict 를 먼저 쓰고(`risk.py`) 곧바로 `execute_sell`/`execute_buy` 를 부르므로 게이트가 재는 틱 나이가 **항상 0.0초**다(그 구간의 청산 트리거는 WS 틱 단독 — REST 폴은 15:20 에 끝난다). 즉 컷이 막으려던 유일한 경로가 정확히 컷을 100% 해제한다. ② 설령 ①을 고쳐도 KRX **K5**(15:30~16:00 장후 시간외 종가, `fixed_price ('06',)`)가 **같은 채널 `H0STCNT0`** 로 실제 체결 프레임을 보낸다 — "틱이 온다" 와 "우리 호가유형이 접수된다" 는 분리된 사실이다.
  - ⚠️ **컷에는 장중 다이얼이 없다** — 위 킬스위치 2키와 별개이고 `order_exchange_clock_mode` 에 **종속시키지 않았다**(없애려는 것이 다이얼인데 롤백 다이얼 하나가 방금 없앤 참여를 조용히 되살리면 자기모순이고, 종속시키면 44/41 KRX 애프터 청산 변환도 함께 꺼진다). 롤백 수단은 **1커밋 revert + 장외 배포**뿐이다.
  - **알려진 비용 — GTP 08:50 자동취소 잔존 상태.** 취소 통보는 체결통보 채널로 **온다**(09-14 실측 073240: `08:29:34` 접수 통보 + `08:50:00` 정각에 같은 주문번호로 두 번째 통보, KIS 주문내역은 그 주문을 `GTP매수자동취소*` 로 기록). 그러나 `handler.py::_handle_execution` 은 `CNTG_YN != "2"` 프레임을 `[order_notice]` 로 **기록만** 하고 콜백으로 넘기지 않는다(`src/realtime/CLAUDE.md` 「접수 전문 기록」). 그래서 자동취소된 주문의 `pending_buys`/`pending_buy_amounts`/`_pending_buy_orders` 와 `trade_history` PENDING 행은 **그날 첫 잔고 sync(≈09:45)까지** 남는다. 그때 `buying_reconcile`(모듈 맵)이 그 주문 자신의 KIS 행(`tot_ccld_qty==0 ∧ rmn_qty==0`)을 보고 세 필드를 풀고 행을 CANCELLED 로 적는다. 그 전까지는 `is_ticker_blocked_for_buy` 가 그 종목 재진입을 막고 예산·슬롯을 점유한다. `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 일부러 21:30 `reset_daily_state()` 까지 남긴다(늦은 체결통보 안전망). GTP 는 이 빈도를 **늘린다**(08:50 까지 안 채워진 모든 프리장 매수가 대상 — `00` 은 09:00:30 정규장 이월로 일부가 결국 체결·취소돼 조기 정리된다). 순수 기회비용이고 자본 위험은 아니다.
    - **통보로 즉시 정리하는 경로** = 이미 구독 중인 체결통보 채널로 취소가 도착하므로 `handler.py` 가 `CNTG_YN=="1"` 프레임에서 취소를 판별해 콜백으로 넘기고 `order_engine` 이 잔존 상태를 정리한다. 이 경로가 줄이는 것은 08:50~≈09:45 의 점유다. 접촉 = `src/realtime/handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**) · `scheduler.py` **무접촉**.
    - 🔴 **선결 = 취소 프레임의 판별 필드 실측.** 09-14 관측은 "프레임이 왔다" 까지만 증명한다 — 그 프레임의 `fields[5]`(RCTF_CLS 정정구분)·`fields[12]`(RFUS_YN 거부여부)·`fields[14]`(ACPT_YN 1:주문접수 2:확인 3:취소) 실제 값은 표본이 없다. 접수(08:29:34)와 취소(08:50:00)를 가르는 필드를 확정하지 않고 분기를 짜면 접수 통보를 취소로 오인해 **살아 있는 주문의 상태를 지운다**. 관측 채널 = `[order_notice]`(세 칸을 `rctf=`·`rfus=`·`acpt=` 로 싣는다) — GTP 미체결 1건의 접수(08:29대)·취소(08:50) 행을 대조해 판별 필드를 정한다. ⚠️ `CNTG_YN` 이 `"1"`·`"2"` 둘 다 아닌 프레임은 이 채널에 남지 않는다(KIS 명세상 값은 둘뿐이다) — 08:50 행이 없으면 먼저 이 가능성을 본다. 🔴 관측을 위해 `fields[:N]` 원문을 로그에 싣지 않는다 — `[0]` HTS ID·`[1]` 계좌번호·`[17]` 계좌명이 섞인다.
    - **측정** = 프리장 매수 발생일 09:05 `GET /api/trading/status` 의 `orders.pending_buy_tickers` 길이.

### 출처 절: session.py › 시장 시간표 — 정본은 `market_state.MARKET_TABLE`

⚠️ KRX **시간외 단일가**(구 16:00~18:00, K7)는 폐지됐고 **시간외 종가**(K5)는 남는다 — 둘을 섞으면 15:30~16:00 판단이 뒤집힌다.

### 출처 절: scheduler.py — KRX/NXT 통합 운영 08:00~20:00

| `TIME_BOOT` | 07:55 | **런타임 미사용 상수** — `_boot()` 는 이 시각을 기다리지 않고 `scheduler.start()` 안에서 **즉시** 실행된다(`scheduler.py:600`). 07:45 자동 기동이면 그 직후, 수동 재기동이면 그 시각이다. `src/` 안 참조는 정의 1줄과 `realtime/websocket.py:46` 주석뿐이고, 값 07:55 는 테스트 핀(`tests/unit/engine/test_cycle92_time_boot_moved.py`)이 남아 있어 지우지 않는다. `_boot()` 본체는 `src/engine/boot_manager.py::boot(scheduler)` 위임(2줄 wrapper). `_preissue_all_tokens()`(메인+보조 N 매니저를 분당 1개 한도로 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()`(보유 + 익일청산 후보 ticker 를 `stock_master` eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → **`portfolio_risk.check_budget_invariant`**(`position_ratio × max_positions > 1.0` 위반 시 `[budget_invariant_violation]` WARNING, **차단 아닌 관찰**) → `allocate_funds(net_asset × ratio)` |
| `TIME_POST_NXT_OPEN` | 15:40 | **런타임 미사용 상수** — 스케줄러의 POST_NXT 전환(`_phase = "post_nxt_trading"`)과 `_confirm_breakout_open_prices(board="post_nxt")` 는 `TIME_KRX_MAIN_CLOSE`(15:30) 대기 직후에 일어난다(`scheduler.py:863-876`). 값 15:40 은 `session._BOARD_SCHEDULE` 의 `post_nxt` 보드 시작과 같지만 **보드 경계의 정본은 `_BOARD_SCHEDULE` 이지 이 상수가 아니다**. 테스트 핀(`tests/unit/engine/scheduler/test_post_nxt_open_time.py`)이 값을 잡고 있어 지우지 않는다 |
| `TIME_SESSION_START_CUTOFF` | 20:00 | `scheduler.start()` 기동 거부 경계이자 `run_daily` 의 "이미 장 종료면 내일로" 판정 — **같은 상수**를 쓴다(갈리면 그 창에서 60초 주기 헛 재시도 ~90회 + KIS 휴장일 API + WARNING 2행/회 → 그날 리포트 `level_counts` 오염). `TIME_SETTLEMENT` 과 분리한 이유 = 겸하면 20:00~21:30 재기동이 AI 자문·`auto_apply_recommendations` 를 재실행한다. ⚠️ 그 창의 재기동은 **그날 20:30 일봉 적재를 통째로 잃는다**. 다음 영업일 일봉 task 의 immediate 실행(`start()` 직후 stagger 240초 — 마커가 직전 영업일 20:30 슬롯보다 이르므로 영업일 슬롯 게이트가 `reason=stale` 로 실행한다)이 7일 증분으로 보정하지만 `_boot()` 의 prepare 보다 늦다. 그 사이 6전략 prepare 는 헤드가 `expected_head`(직전 영업일)보다 오래된 종목을 KIS 로 폴백해 읽는다 — 전 종목 폴백이라 prepare 가 느려지고, 휴장일 조회가 실패한 날(`expected_head=None`)은 하루 밀린 DB 헤드를 그대로 읽는다. `[daily_head_stale]` 관측이 결손을 알린다. +600초 재준비는 적재 완료를 기다리지 않는다(「funnel 스냅샷 캡처」 절) |
- **`_scan_loop(*, first_delay: float | None = None)`(5분 주기, 09:30~)**: VB+LTV+donchian + 모든 전략 보유 합집합 재구독. 🔴 **첫 회차 진입 지연은 호출부가 정한다(cycle298)** — 루프가 `while` 진입 직후 `sleep` 을 먼저 하기 때문에, 선행 구독이 없는 경로에서 그 `sleep` 이 그대로 시세 공백이 된다. 그래서 **호출부 2곳의 배정이 계약이다**: 09:30 진입(`scheduler.py:846`)은 **인자 없음**(바로 앞에서 `scan_stocks()` + `subscribe_filtered_stocks()` 를 이미 동기로 했으므로 0 을 주면 같은 조건검색·구독을 수초 안에 두 번 한다), 15:30 POST_NXT 전환(`:876`)은 **`first_delay=0`**(이 경로엔 선행 구독이 하나도 없어 15:30~19:50 기동이 약 5분 blind 였다). 🔴 **`:876` 은 재기동 전용 경로가 아니라 매일 타는 경로다** — 평시에도 `:849-851` 의 15:20 `cancel()` 이 `done()=True` 를 만들어 `:875` 의 `if self._scan_task is None or self._scan_task.done():` 가 **매일 성립**한다. 즉 `first_delay=0` 은 매일 15:30 에 발효해 그날 첫 POST_NXT 재구독을 15:35 → **15:30** 으로 당긴다. `None`(기본값) = `SCAN_INTERVAL`(300초)이라 **인자를 안 주는 호출은 현행과 동일**하고, 숫자는 **`min(float(SCAN_INTERVAL), max(0.0, float(x)))`** 로 `[0, SCAN_INTERVAL]` 에 가두고, 비수치는 `SCAN_INTERVAL` 폴백이다(예외로 루프를 죽이지 않는다). 🔴 **상한이 계약이다** — 없으면 `first_delay=float("inf")`·`1e9` 가 그대로 `asyncio.sleep()` 에 들어가 **예외도 로그도 없이 그 루프를 영구 blind** 로 만든다. `_scan_loop` 이 유일한 WS 재구독 경로라 그 무음 실패가 곧 손절·트레일링 전면 정지다. 상한은 정상값을 깎지 않는다(`first_delay=SCAN_INTERVAL` → 300 그대로). **2회차부터는 언제나 `SCAN_INTERVAL`** — 주기가 아니라 위상만 당긴다(`sync_counter % 3` 의 `_sync_positions_from_balance` 도 회차 기준이라 주기 불변). 첫 성공 회차의 구독 직후 `[scan_loop_first_subscribe] first_delay= elapsed_s= n=` INFO 1행(never-raise). 남은 공백 = `15:20 ≤ T < 15:30` 기동의 **최대 10분**(`:852` else 가 `_scan_task=None` 으로 두고 15:30 까지 기다린다).
  - **매매 행위 영향은 구간마다 다르다 — "행위 변화 없음" 은 15:30~16:00 에만 참이다.** 주문 발화점은 다섯뿐이고(`risk.on_tick` 2곳 · `_drain_pending_next_day_clear` · `_force_clear_main_only` · `_swing_buy_poll_loop`) `_scan_loop` 본문은 그 어디에도 닿지 않는다. 다만 **구독이 당겨지면 틱이 당겨지고 틱은 `on_tick` 의 입구**이므로 이렇게 갈린다: ① **15:30~16:00 = 변화 0** — 그 창의 주문은 `order_engine._market_rest_now` 가 전량 컷한다(`(True, "market_rest")`). ② **16:00~19:50 재기동 = 손절·트레일링 매도와 LTV `post_nxt` 매수가 최대 5분 앞당겨진다** — 결함이 아니라 이 변경이 되찾으려는 **손절 커버리지 그 자체**다. ③ **평시 무재기동 = 보유 종목 틱 커버리지 불변** — 15:20 `cancel()` 은 구독을 해제하지 않는다(해제는 20:00 `unsubscribe_all()` 뿐). 바뀌는 것은 delta 갱신·universe guard 시각이 5분 당겨지는 것뿐이다(funnel 캡처는 일일 1회 가드 `_auto_funnel_snapshot_done_today` 가 이미 그날 첫 회차에서 닫아 무관하다). 🔴 **전체 재구독 금지** — `_delta_unsubscribe_dropped(new_set)`(빠진 종목만 unsubscribe) + `subscribe_filtered_stocks`(LOW 분기의 `already_in_pool` 가드로 이미 구독 중 종목은 SEND skip)로만 갱신한다. KIS 공지 "비정상 케이스 2"(무한 등록/해제) 패턴 차단이다. HIGH 종목(positions/next_day_clear)은 **항상** 호출한다 — 풀의 `_select_session` promote 를 보존한다. 우선순위 그룹은 `_build_priority_groups(momentum_tickers=...)` 가 만들고 **항상 momentum/breakout 정상 list 를 반환한다**(모드 분기 신설 금지). 직후 `_reprepare_breakout_if_empty()`(대상 `volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`. BFB/VCP 는 boot 실패·일시 API 오류 회복 안전망이고 주 메커니즘은 prdy 시간무관 유니버스) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`.
  - LOW 는 **desired 교집합**만 남긴다 — `desired_low` = `scheduler._collect_breakout_tickers()` ∪ `scanner._last_scan_result`. 순서 = priority 분리 **직후** → desired 필터 → 동시호가 A/B → cap **앞**. HIGH 는 `low_targets` 에 없어 구조적으로 면제된다(+ `_high_collect_ok` 이중). 활성 게이트 = breakout(scheduler 소유 소스) 비어있지 않음 ∧ HIGH 수집 무예외이고, off 면 현행 byte 동일 **fail-open** 이다. 근거 = LOW 후보 소스가 `scanner.ticker_last_tick` **전수**(per-ticker pop 0건, 유일 정리 = 정산의 `_reset_daily_state` clear)라 매도·후보 이탈 종목이 정산까지 stale 자격을 유지해, 같은 `_scan_loop` 이터레이션 안 ~12초에서 `_delta_unsubscribe_dropped`(빼기) ↔ `_resubscribe_stale_priority`(되살리기)가 1:1 무한 페어링을 만들었다(실측 034020 매도 후 35회 재구독). 🔴 `kis_ws_pool.get_subscribed_tickers()` 를 desired 로 쓰는 것은 split-brain 복구 계약 무력화라 **금지**(미구독 desired LOW 는 여전히 `_ticker_to_session.pop` + 재SEND 대상이다). AST `test_cycle240_ast_desired_filter.py` G-240-1~7 봉인.
- **`_stale_watcher_loop()`(120s 주기, 본체 `stale_watcher_core.check_and_resubscribe_stale`)**: `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick` 비교, `STALE_FRESHNESS_SECS=60` 초과면 stale, 종목별 `_stale_retry_count` 누적.
  - **시장 침묵 기각(세션 상대 판정)** — `detect_silent_inactive_sessions` 는 2-pass 다: pass 1 이 세션별 `(label, subscribed, silent_suspect)` 를 상태 무변경으로 계산하고, 판정 가능 세션(`subscribed >= 5`)이 `_MARKET_WIDE_MIN_ELIGIBLE(=2)` 이상이며 **전원** suspect 면 **시장 침묵**으로 보아 판정 가능 전 라벨의 `first_seen` 을 **pop 하고 `[]` 를 반환**한다(🔴 hold 금지 — 침묵 중 `first_seen` 이 자라면 시장 재개 순간 지각 세션이 즉발한다). 판정 가능 < 2(VTS 단일 세션·20:00 `unsubscribe_all` 후) 또는 하나라도 fresh(진짜 단독 결함)면 현행 byte 동일 fail-open 이라 **결과 집합 ⊆ 현행**이다. 근거 = 시장 전체가 조용한 슬롯(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 · 15:30~15:40 마감 흡수)에서 8세션 동시 침묵을 '8개 동시 고장' 으로 오판해 접속키를 하루 16~24 낭비했고 재연결의 회복 가치는 0 이었다(회복 시각은 항상 15:40 POST_NXT 진입). 🔴 **시각 게이트 금지** — `is_call_auction_now`·`boards_at`·시간창 리터럴·`session` import 를 쓰지 않는다(AST G-241-5. 운영 8세션에서는 세션 간 비교만이 15:30~15:40 갭까지 닫는다).
  - 무송출(no_feed) 종목 skip 규칙 = 루트 `CLAUDE.md` 「무송출」 절.
- **stale 관리 모듈 구조**: facade `stale_manager.py`(`__all__` re-export only — 11 함수 + 10 상수. 프로덕션은 본체 모듈을 patch 한다) + `stale_diagnostics.py`(`build_session_subscription_view`/`emit_stale_session_detail`/`refresh_stale_ccnl_cache`/`evict_expired_ccnl`/`prune_force_retry_history` + 상수 4) · `stale_session_recovery.py`(`detect_silent_inactive_sessions`/`force_reconnect_session`/`delta_unsubscribe_dropped` + 상수 5) · `stale_universe_guard.py`(`evaluate_universe_guard` + 상수 1) · `stale_watcher_core.py`(`check_and_resubscribe_stale`·`resubscribe_stale_priority` = **K stale watcher HIGH hot path**). `scheduler.py` 는 `from src.engine import stale_manager` lazy import 2줄 wrapper **11개**로 위임하고 상수 5개를 re-export 한다(`is` 동일). wrapper 이름은 `_` 접두를 유지한다 — `_check_and_resubscribe_stale` · `_resubscribe_stale_priority` · `_detect_silent_inactive_sessions` · `_force_reconnect_session` · `_delta_unsubscribe_dropped` · `_evaluate_universe_guard` · `_build_session_subscription_view` · `_emit_stale_session_detail` · `_refresh_stale_ccnl_cache` · `_evict_expired_ccnl` · `_prune_force_retry_history`. 계약:
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`) → trade_history 동기화. **호출부는 `boot_manager.py` 유일**(부팅 시점 1회 — 장중 주기 호출 없음). MTS/HTS 수동 매매분 반영. 중복 판정 키 `(ticker, order_no)` 페어. **전략 귀속 출처 순서(cycle354)** = DB(당일 같은 티커 매수 기록, `db_strategy_map`) → `order_engine._order_strategy`(order_no → strategy_id, `place_order` 응답 직후 동기 등록·전량체결 시 pop, 루트 CLAUDE.md 「주문번호 매핑」 규약 — 읽기 전용, 8영역 무접촉) → 하드코딩 `"momentum"`(최종 폴백). 당일 첫 매수(가장 흔한 sync 경로)는 `db_strategy_map` 에 그 ticker 가 아직 없어 order_no 매핑이 주 출처가 된다 — 재시작 전 체결통보(WS)가 유실돼 `_order_strategy` 엔트리가 아직 pop 되지 않은 주문이 전형적 표적이다. 매도는 registry 라이브 포지션 조회(정확한 buy_price 의 유일한 출처)가 최종 권위로 남아 order_no 매핑을 덮어쓴다. 셋 다 미확보 시에만 `[sync_strategy_unknown] ticker= order_no=` WARNING(성과 귀인 오염 가능성 가시화) — 빈 문자열 등 오염된 매핑 값은 `or None` 정규화로 "값 있음"으로 오판하지 않는다. 구형 테스트 더블(`order_engine` 속성 부재) 은 `getattr` 이중 폴백으로 fail-open. **포지션 복구 시 전략 귀속은 이 함수와 별개 경로다** — `boot_manager.boot()` 의 KIS 잔고 보완 복구(DB `positions` 에 없는 KIS 보유 종목)는 `get_recent_buy_strategy(ticker)`(`trade_history` 최근 매수 행)로 전략을 상속하고 실패 시 자체 `"momentum"` 폴백을 쓰며, 미체결 매수 주문 복구는 `db_positions`→`get_today_buys_ticker_strategy()`→`"momentum"` 3단 폴백을 쓴다 — **둘 다 이 사이클이 손대지 않은 별도의 momentum 폴백**이고(cycle354 범위 = `_sync_orders_to_db` 단독), 청산 규칙이 전략별이라 그 폴백이 틀리면 복구된 포지션이 엉뚱한 전략의 손절·트레일링 규약을 탄다 — 후속 검토 대상
- `_sync_positions_from_balance()`: 15분 주기. strategy 매핑은 trade_history 직전 BUY 행에서 상속. 종료 시 `unblock_buy()` + `clear_low_funds()` 일괄 해제. **stale `_selling` 재대조**(본체 = leaf `selling_reconcile.py`, hot path 밖): `_selling` 각 ticker 가 (보유 잔존[balance qty>0] ∧ 열린 매도주문 없음[`get_daily_orders` 의 `sll_buy_dvsn_cd=="01"` ∧ `rmn_qty>0` 부재] ∧ `_selling_since` 경과 ≥ `SELLING_RECONCILE_MIN_AGE_S=180s`) 이면 `_selling.discard` + `_selling_since.pop` → 다음 on_tick 손절 재평가 재개(`[selling_reconcile]` WARNING). 고치는 것 = NXT 지정가 미체결 만료·체결통보 유실로 `_selling` 이 영구 잔존해 손절·트레일링이 종일 억제되던 병리다. double-sell 방지 3중 가드 = 열린주문 존재(`exchange=ALL` 조회로 NXT 연속세션 잔존 주문까지 포착) 시 유지 / 미보유 유지 / 180s 미만(전파지연 창) 유지. 유지 사유는 `[selling_hold] ticker= reason=held_zero|open_order|too_young elapsed_s=` WARNING 1회/(ticker,reason)/일로 남는다. **체결 0 매수 pending 회수**(본체 = leaf `buying_reconcile.py`, 판정·마커는 모듈 맵): selling 재대조 **뒤**에서, 어느 전략이든 `pending_buys` 가 있을 때만 `reconcile_stale_buying(self.registry, self.order_engine, holdings)` 를 부른다. `holdings` 는 같은 함수 첫머리 `get_balance()` 결과를 그대로 쓴다(추가 잔고 조회 0). sync 는 `_scan_loop` 3회차마다(≈15분) 돌고 `_scan_loop` 은 09:30~15:20 · 15:30~20:00 에 산다. 그래서 해제 시점은 ≈09:45~15:15 · ≈15:40~19:55 이고, 20:00 뒤에 남은 pending 은 21:30 `_reset_daily_state` 가 치운다

### 출처 절: scanner.py

 - **2-pass**: 1차 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing 잔여 슬롯 add → 2차 `MAX - len(_subscriptions) > 0` 면 breakout overflow 흡수 add. 최종 drop = `max(0, len(overflow) - absorbed_overflow)`. drop>0 시 `[priority_drop]` INFO + WARNING `system_logs`. 중복은 HIGH 1회만, HIGH 단독 41 초과 시 ERROR. **로그 필드** = `breakout/momentum/swing/total_subscribed/max/high_count/low_remaining/pool_sessions/pool_slots` + **cc68119(2026-08-13) `pool_subscribed`(현 풀 실제 구독량 `len(kis_ws_pool._subscriptions)`) + `pool_remaining`(잔여 = `max(0, pool_slots − pool_subscribed)`)** 병기 — 포화가 41-cap(메인)인지 풀 전체(`pool_slots=41×세션수`)인지 진단

### 출처 절: log_analysis_engine.py — 일일 로그 분석

- **표본 절단 감지** — `_fetch_logs_in_range` 는 `ORDER BY timestamp ASC` 라 상한 초과 시 **이른 시각부터 채우고 조용히 끊는다**. 평시(~18,000건)엔 안 걸리고 **폭주한 날 = 리포트가 가장 필요한 날**에만 발동한다(08-03 실측 97,353건 = 상한의 3.2배). **조용함 + 이른 시각 편향** 두 결함이 겹친 것이라 시정도 3종이다:

### 출처 절: recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

- `apply_weight=true` 옵션 → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. 🔴 `allocate_funds()` 즉시 재호출 금지(다음 `_boot` 반영). **증액 한정 Σ 사전 검증** — `new > 현재 weight` 일 때만 `타 전략 weight 합 + new > 1.0 + _WEIGHT_SUM_TOLERANCE`(`routes/strategies.py` 에서 import = 단일 진실원)를 검사해 위반 시 `[weight_sum_violation]` WARNING + `success=false` **early return**(params/weight/status 어느 것도 저장 안 됨). 🔴 **감액은 Σ 상태와 무관하게 항상 통과한다** — 오염 상태에서 감액이 복구 수단이라 여기에 검사를 걸면 복구 경로가 봉쇄된다(Settings 는 Σ>1 이면 저장을 잠그므로 무가드 증액은 DB 직접 UPDATE 외 복구 불가 상태를 만든다). float 변환 실패 시 검사 skip(기존 관용 경로 위임). ⚠️ 이 경로는 메모리 `config.weight` 만 갱신하고 `enabled` 는 건드리지 않는다(메모리 활성 / DB 비활성 split-brain) — `risk.py` 가 `registry.enabled()` 단일 순회라 메모리도 비활성화하면 그 즉시 손절이 멈추므로 **의도적 미시정**이고 `enabled` 축은 후속 사이클 소관이다
- **`PARAM_RANGES` 화이트리스트(자동 튜닝 대상)** = `k_value_krx_main`/`k_value_nxt_pre` `(0.5, 2.0)`(VB, LTV) · `stop_loss_main`/`stop_loss_pre_nxt` `(-15.0, 0.0)` · `long_ma_period` `(20, 120)` · `volume_multiplier` `(1.0, 5.0)` · `min_prdy_rate` · VCP 4키(`base_depth_pct`/`volume_contraction_ratio`/`breakout_volume_mult`/`last_pullback_max`) · `breakout_retention_minutes`.
  - 🔴 **편입 금지(정체성 상수)** = 진입 축 `buy_threshold`(momentum 급등 진입 정의)·`donchian_period`(20일 신고가 정의)·`max_breakout_extension_pct`·`box_contraction_period`·`max_box_volatility_pct` / 청산 축 `atr_trail_mult`·`breakout_fail_n_days`(donchian·BFB·VCP **3 전략 공유**인데 근거 표본은 donchian 뿐 → VCP/BFB 청산 왕복 ≥20 시 재검토) / 리스크 축 `max_positions`·`max_lot_units`·`max_lot_ratio_mult`·킬스위치 2키. 근거 = 진입·청산 임계는 전략 정체성이라 AI 가 매일 밤 흔들면 전략이 변태한다. **수동 적용 라우트도 같은 정본을 참조한다.**
- `INT_PARAMS` = `long_ma_period` · `breakout_retention_minutes` · `breakout_fail_n_days`

### 출처 절: 절대 깨지면 안 되는 규칙

- 체결통보(H0STCNI0/9) 구독 제거 금지 — 미구독 시 포지션 등록 불가 → 손절 불가
- uvicorn 단일 워커 필수 (`--workers` 금지)
- 익일 청산은 scheduler에서 시가 수신 후 30s 안정화 (`_next_day_clear_pending` 전략 가드 + `_pending_next_day_clear` scheduler 보류 set) — on_tick 즉시 청산 금지
- 익일 청산 갭률은 반드시 `ticker_prices[ticker]["open_price"]` (WebSocket 시가) — `high_since_buy` 폴백 금지. 시가 미수신이면 `_pending_next_day_clear` 보류 후 09:00 KRX 시장가
- NXT 프리/애프터 매도 거부 (`is_market_closed_rejection`) 시 `execute_sell` 이 `state.positions`·DB 보존 + `_selling` discard (진입 게이트 `is_blocked()` 위임 — stale `_selling` 좀비 방지) + **`target_exchange ∈ ("NXT","SOR")` ∧ KST 08:00~08:50 일 때만** `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강(KRX 로 보낸 주문의 거부에는 절대 쓰지 않는다 — KRX 애프터마켓이 구 `15:30~20:00` 창 안에 들어와 그 창의 거부는 어느 시장 것인지 시계로 가릴 수 없다). 진입 게이트 `SellRejectionTracker.is_blocked()` 2단계 TTL: KRX 메인(09:00~15:30) 거부 = 5분 TTL, NXT 시간대 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` = 30초 TTL, NXT 폴백 실패 = 익일 청산 큐 등록. `_reset_daily_state` 동행 `_sell_rejection.reset_daily()` 위임 필수. 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 유지
- 매수 시장가 거부 (`is_market_order_disallowed`) → `step_up(current_price, 5)` 지정가 1회 폴백
- 매도 시장가 거부 (`is_market_order_disallowed`) + `order_division==MARKET` → `step_down(current_price, 5)` 지정가 1회 폴백. 폴백 실패 시 cooldown 등록 안 함 + positions 보존 (청산 의무, 다음 사이클 재트리거). 지정가 매도는 폴백 안 함
- 주문번호 매핑 등록은 **`place_order` 응답 직후 동기 영역**, `await insert_trade` 진입 *전*
- 체결통보 선행 race 가드 (`_completed_orders` + UPDATE 0건 보정 INSERT) 매수·매도 양쪽 필수
- `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` ↔ sync 주기(15분) 정합성 — 변경 시 sync 종료 시 일괄 해제 동작 보존
- `position_ratio`는 **전략 할당 자금 기준** — 정확히는 `순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio`. `allocate_funds` 가 **Σ 로 정규화**하므로 Σ≠1 이어도 자산 전액이 배분된다(Σ<1 부분 저장이 허용되므로 특히 유의)
- TR_ID 는 `settings.get_tr_id()` 사용
- VB `DEFAULT_TRADABLE_BOARDS` 에 POST_NXT 추가 금지 — 당일 15:20 일괄매도 정책 위반 + OVERNIGHT 자연 보유 결함


## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관 (앞쪽 절반: 파일 시작 ~ 「매도 체결 — 주문 축과 보유 축」)

> 사용자 요청 「유지해야할 내용도 전반적으로 압축하자」에 따른 /sync-docs 2차 압축(압축만 — 정정 없음).
> 아래는 2차 압축으로 정본에서 바뀌거나 빠진 **원문 줄 그대로**다(1차 반영본 기준, 정본에 글자 그대로 남지 않은 줄 전부).
> 정본은 같은 규칙·조건·식별자를 짧게 다시 적었다. 사고 사례(004690 · 2026-07-24 import 사고 · cycle328/335 좁히기 회귀 등)·실측 수치(3,583행 · 74~121 · 09-23 봉 비율 등)·근거 설명은 여기에만 남는다.

### 출처 절: 머리말(첫 「##」 앞)

다중 전략 아키텍처. `StrategyBase` 추상 클래스 기반 플러그인 구조. **지금 동작하는 규칙만** 적는다.
> **DB 접근**: 엔진 모듈은 전부 `src/db/pg.py`(asyncpg) 헬퍼를 경유한다 — `scheduler`(auto_start·trade_history·strategy) / `boot_manager`(strategy 조회 + PENDING BUY 일괄 COMPLETED + 오늘 BUY 조회) / `log_metrics_collector`(`_fetch_logs_in_range` 페이징). auto_start 는 `system_config.get_auto_start`/`set_auto_start`. 상세 = [`src/db/CLAUDE.md`](../db/CLAUDE.md).

### 출처 절: 모듈 맵

한 줄 = 그 모듈의 **현재 역할 · 공개 API · 불변식 · 금기**다. 사이클 번호는 값의 출처 표기로만 쓴다.

### 출처 절: 모듈 맵 › 매매 흐름 축

- **`strategy_base.py` / `strategy_registry.py`** — 전략 추상 + 등록·비중 배분·중복 매수 가드. 매수 수량 공통 관문 `_apply_budget_limit` 의 계약은 루트 [`CLAUDE.md`](../../CLAUDE.md) 「핵심 안전 규칙」 절이 정본. 하단 전용 절 참조.
- **`session.py`** — `MarketBoard` · `SessionTracker`. `is_call_auction_now(now=None) -> bool` = H0UNMKO0 `MKOP_CLS_CODE`(110 장전 / 121 장후) **AND** 명목창 ±5분(110: 08:25~09:05 / 121: 15:15~15:35) 게이트 + 시간 기반 폴백, `now or datetime.now(_KST)` KST 강제. 🔴 코드 단독으로 판정하지 않는다 — KIS 가 코드 의미·push 트리거를 문서화하지 않아 전환 코드가 안 오면 `_last_nxt_mkop_code` 가 고착하고, 고착하면 보유 종목 stale 탐지가 꺼져 손절이 누락된다. 가드 `test_cycle182_call_auction_time_gate.py` · `test_cycle182_call_auction_ast_gate.py`. 시간표는 하단 `session.py` 절.
- **`risk.py`** → **`order_engine.py`** → **`scheduler.py`** — 틱 판정 → 체결통보·DB 영속화 → 시간 가드·run/settle. 각 전용 절은 하단.
- **`boot_manager.py`** — `_boot` 본체. 백그라운드 태스크 둘을 **await 없이** 띄운다. ① 토큰 발급(`token_manager.get_token()`) 직후 `daily_bar_finalize.spawn(phase="boot")`(함수 안 import) — 설정 로드·잔고·레짐과 겹쳐 돌고, prepare 직전(`emit_daily_head_staleness` 앞)에 `daily_bar_finalize.wait_for_boot(…, budget_secs=daily_bar_finalize.BOOT_BUDGET_SECS)` 로 최대 90초 기다린다(「저녁 데이터 적재」 절의 「전일 잠정 봉 확정」). ② 익일청산 복구 직후 `funnel_capture.spawn_funnel_boot_vs_evening(scheduler, phase="boot")` 1회(「funnel 스냅샷 캡처」 절 ④). `_load_strategy_config` 직후 `portfolio_risk.check_budget_invariant` 로 `[budget_invariant_violation]` WARNING 을 남긴다. 활성 전략 준비는 `funnel_capture.live_prepare_one(strategy, phase="boot")` 다(wrapper 가 never-raise 라 호출부에 try 가 없다).
- **`scanner.py`** — 종목 스캔·구독·`STATIC_TICKER_NAMES` + 적재 함수 4종(`_stock_master_daily_load_once` · `_stock_master_basics_refresh_once` · `_stock_master_master_load_once` · `_stock_master_financial_load_once`) + 매수 진입 차단 `_is_master_blocked_for_entry` + 시세 채널 리졸버 `tick_tr_id_for`. 적재 규약은 하단 「저녁 데이터 적재」 절, 구독 규약은 하단 `scanner.py` 절.

### 출처 절: 모듈 맵 › stale 계열 (K stale watcher)

- **`stale_diagnostics.py`** — 진단 · CCNL 캐시 · force_retry history prune. `STALE_FRESHNESS_SECS = 60`(KIS LMS chain 안전 마진, G-SAFETY-1) · `SUBSCRIBE_GRACE_SECS = 180`(= 3 × freshness, 구독 직후 ACK grace). 🔴 `tick_channel_switch` 의 원복 probe 가 이 상수를 **재사용**한다 — 그쪽에서 재정의하지 않는다.
- **`stale_session_recovery.py`** — silent inactive 감지 · 세션 강제 reconnect · delta unsubscribe(임계·cap 은 `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」). **세션 상대 판정** = 판정 가능 세션(`subscribed >= 5`)이 2개 이상이고 그 전부가 `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD` 면 세션 고장이 아니라 **시장 침묵**으로 보고 그 사이클을 기각하고 판정 가능 전 라벨의 `first_seen` 을 pop 한다(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다). 다른 세션이 하나라도 fresh 면 현행대로 발화하고, 판정 가능 세션이 2 미만이면 현행 유지(fail-open). 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측한다. 🔴 기각 판정에 시간창 리터럴·`tradable_boards`·`session` import 를 쓰지 않는다 — 세션 간 비교만이 15:30~15:40 갭까지 닫는다(AST G-241-5).
- **`stale_universe_guard.py`** — 보유·익일청산 절대 보호 universe guard. 본체 `evaluate_universe_guard` + scheduler wrapper `_evaluate_universe_guard`(규약 = 하단 `scheduler.py` 절).
- **`stale_watcher_core.py`** — 본체 `check_and_resubscribe_stale`(120초) + `resubscribe_stale_priority`(5분, LOW desired = breakout ∪ momentum 교집합, HIGH 는 구조적 면제). `check_and_resubscribe_stale` 의 판정 순서:
  - ① grace 가드 `_is_within_grace(t)` — `t in ticker_last_tick` 이면 False · `ack_at` 이 datetime 이 아니면 False · 예외 시 안전 폴백. ACK 조회 키는 **채널 무관 역인덱스** `ack_at_by_ticker` 다 — 채널 고정 키면 전용 채널 종목이 180초 grace 를 영구 miss 해 구독 직후 stale 로 읽히고 강제 재등록이 폭주한다.
  - ② `SessionTracker.is_call_auction_now()` 가 True 면 **LOW-scoped skip**(cycle371) — stale ∩ HIGH(보유·익일청산)는 그대로 `unsubscribe_in_pool`→`subscribe(priority="HIGH", bypass_limit=True)` 강제 재등록하고, stale ∩ LOW 만 SEND 0·retry 카운터 무변경으로 건너뛴다. 🔴 HIGH 는 skip 하지 않는다 — 동시호가 창(아침 08:30~09:00, 110 코드가 있으면 08:25~09:05) 동안 보유 종목 재구독이 멎는 것이 005935 사고 패턴이다. `[stale_skip_call_auction] subscribed= low= high=` WARNING 은 매 사이클 남는다(HIGH stale 이 없어 전부 skip 인 사이클도 — 그때 누적 retry 카운터를 보존하고 조기 반환한다). `is_no_feed`(no_feed_held 판정)는 그 반환 **뒤**라 HIGH 없는 동시호가 사이클에서 판정 0회다(W9, `test_cycle252_stale_watcher_no_feed.py::test_w9_...`).
  - ③ no_feed skip — `subscribed` 확보 직후 `no_feed_registry.ensure_fresh(subscribed ∪ 보유·익일청산)` 를 try/except 로 부른다. `LOW ∧ is_no_feed(t) ∧ (킬스위치 off ∨ 실제 구독 채널 ∉ DEDICATED_TICK_TR_IDS)` 이면(판정 위치 = priority 결정 직후 · `retry > MAX_STALE_RETRIES` 비교 직전) `r` 증가·`r>5` 홀드(`MAX+1`)만 하고 `continue`(SEND 0 · 스탬프 0 · history 0). `r` 을 계속 올리는 이유 = `stale_universe_guard` 의 저유동 축출 경로를 보존한다. 🔴 **HIGH 경로는 skip 대상이 아니다** — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지다.
  - `[no_feed_held] tickers=[…]` WARNING 1회/일 — `high_tickers` 를 `if not stale_tickers: return` **앞**에서 계산해 stale 여부와 무관하게 매 사이클 판정한다(예외 흡수 — 관측 헬퍼가 예외를 올려 HIGH 재등록 사이클을 끊으면 안 된다). KRX 연속체결 창(09:00~, `_is_before_krx_continuous_open` — `tick_channel_clock._windows()` 의 `krx_regular_open` 재사용, 시각 리터럴 0건) 이전에는 판정을 억제하고 cap 을 소비하지 않는다(cycle357) — NXT 프리장의 `nxt_tradable=False` 종목은 KRX 가 시가 단일가라 어느 채널이든 연속체결 프레임이 정의상 0 이어서 무송출로 오판한다. 경계 판정 실패는 억제하지 않는 방향(fail-open)이다.
  - `[stale_watcher_summary]` 끝 필드 ` no_feed_skipped=%d`. 판독 = `no_feed_skipped` 와 `[stale_force_retry]` 는 **감소**가 성공 서명, `[no_feed_held]` 는 **0** 이 정상이다(09:00 이후에도 무송출이면 여전히 뜬다). 🔴 이 마커들과 `[tick_coverage] stale` 의 의미는 2026-09-14 채널 분리 배포로 뒤집혔다 — 그 전후 로그를 합산하지 않는다.
  - 🔴 금기 = no_feed 종목을 stale 집계에서 **빼서** 숫자를 좋게 만드는 것. `resubscribe_stale_priority`(5분)는 no_feed 처리와 무관하다 — 후보 소스 `ticker_last_tick` 에 no_feed 종목은 프레임 0 이라 애초에 없다.
- **`sell_rejection.py`** — `SellRejectionTracker`. 2단계 TTL 진입 게이트 계약은 루트 `CLAUDE.md` 「핵심 안전 규칙」 절이 정본.
- **`selling_reconcile.py`** — `scheduler._sync_positions_from_balance` 의 stale `_selling` 재대조 위임 leaf. `reconcile_stale_selling(order_engine, holdings, *, min_age_s, now=None)` 판정 3분기 `held_zero`(보유 0) · `open_order`(KIS 일별 주문에 `sll_buy_dvsn_cd=01 ∧ rmn_qty>0`) · `too_young`(`elapsed_s < min_age_s`=180s) 은 유지 + `[selling_hold] ticker= reason= elapsed_s=` WARNING 1회/(ticker,reason)/일, 그 외는 해제. `get_daily_orders` 예외는 graceful(`_selling` 유지). 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정 — `system_logs` 접두가 갈리면 운영 grep 사슬이 끊긴다.
- **`buying_reconcile.py`** — `scheduler._sync_positions_from_balance` 의 매수 pending 회수 위임 leaf(`selling_reconcile.py` 대칭, 8영역·`scheduler` import 0, cycle379). 거래소가 접수 뒤 끝낸 매수 주문(거부·취소·GTP 08:50 자동취소·KRX 15:30 정규장 미체결 자동취소)이 붙잡고 있던 **슬롯·예산·그 종목 진입권**을 되찾는다. `reconcile_stale_buying(registry, order_engine, holdings, *, min_age_s=BUYING_RECONCILE_MIN_AGE_S, now=None, max_lookups=MAX_ORDER_LOOKUPS_PER_PASS)`. 상수 = `BUYING_RECONCILE_MIN_AGE_S = 300` · `MAX_ORDER_LOOKUPS_PER_PASS = 10` · `ORD_TMD_FUTURE_TOLERANCE_S = 60`.
  - 🔴 **양성 증거로만 푼다. 없다는 것은 해제 근거가 아니다** — 잘못 풀면 살아 있는 주문을 잊는다(전략 예산 이중 사용 + 같은 종목 2랏 + `max_positions` 초과). 해제 조건은 넷이다. ① 그 종목에 연결된 **모든** 주문(`order_engine._pending_buy_orders` 중 `ticker` 일치)의 자기 행을 `get_daily_orders(target_date=오늘, odno=o)` 로 찾는다(`odno`·`pdno` 는 `strip()` 비교, `sll_buy_dvsn_cd=="02"`). ② Σ`tot_ccld_qty`==0 ③ Σ`rmn_qty`==0 — 두 칸 모두 명시값이어야 한다(빈 값·비수치는 0 으로 읽지 않고 `bad_row`). ④ `now − max(ord_tmd)` ≥ `min_age_s`(경계 포함, `ord_tmd` 는 오늘 날짜와 합친 KST). 행이 여럿(SOR 분할)이면 수량은 합, `ord_tmd` 는 가장 늦은 값이다.
  - **유지 사유** — 메모리 단계(KIS 호출 0): `ambiguous_owner`(두 전략 이상이 pending) · `held`(어느 전략이든 `has_position`, KIS 잔고 수량>0, 잔고 파싱 실패) · `no_order_no`(연결 주문 0 = `await place_order` 창 또는 매핑 유실). 여기서 후보가 다 빠지면 KIS 를 부르지 않는다. KIS 단계: `lookup_error` · `open_order`(자기 행 `rmn_qty>0`, 또는 오늘 전체 목록에 같은 종목 매수 `rmn_qty>0` — 수동 MTS 주문 포함) · `deferred`(패스당 조회 상한 초과) · `not_found` · `bad_row` · `fill_seen`(Σ`tot_ccld_qty`>0) · `age_unknown`(`ord_tmd` 부재·형식 오류·`now` + 60초보다 미래) · `too_young` · `raced`.
  - **해제는 3필드뿐이다** — 마지막 `await` 뒤 동기 헬퍼 `_release_if_unchanged` 가 다시 본다: pending 소유 전략이 여전히 그 하나인가 · 누구도 보유하지 않는가 · 연결 주문 집합이 같은가. 통과하면 같은 자리에서 `pending_buys.discard` · `pending_buy_amounts.pop` · `_pending_buy_orders.pop(o)` 만 한다. `_handle_buy_fill` 첫 체결 경로가 지우는 것과 같은 셋이다. 🔴 `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 **남긴다** — 판단이 틀려 늦은 체결통보가 오면 그 매핑이 올바른 전략·수량(`qty_src=map`)으로 포지션을 세운다. 21:30 reset 이 치운다. `sold_today`·`buy_blocked_until`·`low_funds_tickers`·`_completed_buy_orders` 는 무접촉이다 — **같은 날 재진입을 막지 않는다**(사용자 결정 2026-09-27, 기존 가드만 적용).
  - **장부** — 해제 뒤 연결 주문마다 `update_trade_status(t, BUY, CANCELLED, strategy=, order_no=o)` 를 부른다. `match_partial` 을 넘기지 않으므로 PENDING 행만 바뀌고 PARTIAL·COMPLETED 는 안 뒤집힌다. 🔴 CANCELLED 가 필수인 이유 = 재진입으로 보유가 생기면 다음 sync 첫머리 `mark_pending_buys_completed(t)` 가 남은 PENDING BUY 행을 COMPLETED 로 뒤집어 죽은 주문이 유령 체결이 된다. DB 예외는 마커에 `db=error` 로 싣고 메모리 해제는 되돌리지 않는다.
  - **마커** — `[buying_reconcile] ticker= strategy= odno= kind=rejected|cancelled|auto_cancel|zero ord= rjct= cncl= age_s= amount= db= release_n=` WARNING 무cap(해제 1건 = 1줄, `kind`·`release_n` 은 관측 전용) · `[buying_hold] ticker= strategy= reason= odno= age_s=` 1회/(ticker, reason)/일(`KstDailyEmitCap`) — WARNING = `held`·`fill_seen`·`not_found`·`bad_row`·`ambiguous_owner`·`age_unknown`, INFO = 그 밖 · `[buying_reconcile_error]` ERROR(본체 예외 흡수, `CancelledError` 는 전파). logger = `src.engine.buying_reconcile` 이고 `write_log` 호출은 0 이다(영속은 루트 `_DbLogHandler`).
  - ⚠️ **판독** — `held`·`fill_seen` 은 pending 이 남은 채 실제로는 체결됐을 수 있다는 뜻이다. 체결통보가 유실됐다면 sync 입양도 `is_ticker_held_by_any` 가 pending 을 보고 건너뛰어 손절 사각이 된다. 이 leaf 는 유지만 하고 입양 경로는 바꾸지 않는다(「발사 창 귀속」 절의 별건 권고 소관). 같은 종목 `release_n>=2` 는 거부 루프다(행위 제한은 없다). `kind=rejected` 행 앞에는 같은 주문번호의 `[order_rejected_notice]` 가 있는 것이 정상이다(없으면 조사).
  - 🔴 **잘못 풀 수 있는 유일한 경로** = KIS 가 살아 있는 주문을 `min_age_s` 넘게 `ccld=0 ∧ rmn=0` 으로 보고하는 경우다(알려진 메커니즘 없음). 그 사이 같은 종목을 재진입했다면 늦은 체결의 `_handle_buy_fill` 이 `pending_buys` 를 **종목 키로** 지워 새 주문의 pending 까지 지운다. `pending_buy_amounts` 키를 `(ticker, order_no)` 로 바꾸는 카드 E 가 이것을 닫고, 그때 이 leaf 의 pop 자리도 같이 바꾼다.

### 출처 절: 모듈 맵 › 관측·공통 헬퍼

- **`metrics_collector.py`** — `make_metrics_collector(*, prefix, summary_keys, int_keys, str_keys, accumulate_keys, use_last) -> (record_fn, flush_fn, collector_list)` 팩토리. 빈 윈도우는 flush skip, 누적/단일 행은 `use_last` 로 분기. metrics facade 4종이 여기 위임한다.
- **`stock_master_metrics.py` / `stock_master_basics_metrics.py` / `stock_master_daily_metrics.py` / `stock_master_master_metrics.py`** — 위 팩토리 위 re-export facade. 각 flush 는 `scheduler.py` 영역에서 **1회 이상** 호출돼야 한다(G-AST1).
- **`task_loop_helper.py`** — `run_periodic_task_loop(...)`. 계약은 하단 「정기 task 루프」 절.
- **`data_load_tasks.py`** — 저녁 데이터 적재 task loop 본체 8종(`scan_pool_eager_refresh_loop` / `full_universe_load_task_loop` / `stock_master_daily_load_task_loop` / `stock_master_basics_refresh_task_loop` / `stock_master_master_load_task_loop` / `stock_master_financial_load_task_loop` / `evening_funnel_capture_task_loop` / `stock_master_daily_purge_task_loop`). 각 함수는 `scheduler` 인자 + `wait_time` kwarg 를 받고(TIME_* 는 wrapper 가 넘긴다 = 순환 import 회피), `scheduler.py` 쪽은 2줄 위임 wrapper 다. 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정(`system_logs` 접두 연속성). full_universe 부팅 즉시 실행의 행 수 하한 `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000` 과 그 판정 콜백 `_full_universe_below_immediate_floor` 도 여기 있다(하단 「정기 task 루프」 절). 가드 `test_refactor_b1_data_load_tasks.py`.
- **`funnel_capture.py`** — 라이브 전략 준비의 **단일 입구** + 저녁 미리보기 본체 leaf. 공개 API = `resolve_as_of(now_kst, mode) -> AsOf | None` · `live_prepare_one(strategy, *, phase) -> bool` · `live_prepare_many(strategies, *, as_of, phase) -> {"prepared", "failed"}` · `capture_skip_reason(strategy, label, today, *, is_provisional) -> str | None` · `evening_capture_once(scheduler) -> dict` · `emit_funnel_boot_vs_evening(scheduler, *, phase="boot")` · `spawn_funnel_boot_vs_evening(scheduler, *, phase="boot") -> asyncio.Task`. 공개 함수는 전부 **never-raise** 다(호출자가 부팅 경로·task loop 라 하나가 죽으면 전체가 죽는다). 🔴 8영역 import 0 · naive 벽시계 0(가드 `tests/unit/ast/test_cycle364_ast_live_prepare_lock.py`) — 보호 종목도 scanner 헬퍼가 아니라 scheduler 가 가진 registry·`_pending_next_day_clear` 에서 모은다. `scheduler`(TIME 상수·`capture_funnel_snapshots`)와 `trading_calendar` 는 함수 안에서 지연 import 한다. 상수·계약 = 하단 「funnel 스냅샷 캡처」 절.
- **`trading_calendar.py`** — 휴장일 판정 공용 leaf(8영역·`scheduler.py`·`boot_manager.py` import 0). 「직전·다음 영업일이 언제인가」를 묻는 세 곳이 쓴다 — 부팅 즉시 실행 슬롯 게이트(`task_loop_helper._evaluate_slot_gate`) · 6전략 prepare 의 일봉 신선도 기준(`StrategyBase._resolve_expected_daily_head`) · 저녁 미리보기의 기준일(`funnel_capture.resolve_as_of`·`evening_capture_once`).
  - API 4개는 전부 **never-raise**(예외 → `None`)다. `is_open_day(d) -> bool | None` · `previous_trading_day(today) -> date | None`(`today` 보다 엄격히 이전의 가장 최근 개장일. 최대 `_PREVIOUS_TRADING_DAY_LOOKBACK_DAYS`=10 달력일을 거슬러 가고, 도중 `None` 을 만나면 추측하지 않고 `None`) · `next_trading_day(d) -> date | None`(`d` 보다 엄격히 뒤의 가장 가까운 개장일. 최대 `_NEXT_TRADING_DAY_LOOKAHEAD_DAYS`=14 달력일을 앞으로 가고, 도중 `None` 이면 `None` — 추석 5일 연휴도 한 번에 넘는다) · `latest_passed_trading_slot(now_kst, slot) -> datetime | None`(`now` 이하인 「개장일 D 의 `slot` 시각」 중 가장 최근, KST aware. `now.time() >= slot` 이면 오늘부터 본다).
  - 조회 seam 은 모듈 전역 `_lookup_open(d)` 하나다. 호출 시점에 `src.api.condition.is_trading_day`(KIS CTCA0903R, 3상태 True=개장 / False=휴장 / None=모름)를 지연 import 로 부른다.
  - 메모 = 모듈 전역 dict 에 **True/False 만 영구** 담는다(날짜의 개장 여부는 바뀌지 않는다). 주말(`weekday() >= 5`)은 조회 없이 휴장이다. `_MEMO_MAX_AGE_DAYS`(40일)보다 오래된 키는 **삽입되는 날짜 기준**으로 정리한다 — 벽시계 기준이면 회귀 스위트가 달력이 흐르는 것만으로 붉어진다. 이 메모가 KIS 공지 「CTCA0903R 은 가급적 1일 1회 호출」(`docs/kis/domestic-stock-industry.md` 국내휴장일조회)을 **날짜당 프로세스 수명 1회**로 지킨다.
  - `None`(모름)은 영구 캐시하지 않고 `_NEGATIVE_CACHE_TTL_SECS`(90초) 동안 별도 저장소 `_negative_memo` 에서 재사용한다(같은 CTCA0903R 지연을 반복해 기다리지 않는다). 조회는 `_LOOKUP_TIMEOUT_SECS`(5초) `asyncio.wait_for` 로 감싼다 — 지연이 부팅 prepare 를 분 단위로 늘리지 않게 한다. 타임아웃도 「모름」으로 흡수하고 「모르면 실행」 방향은 그대로다. `_reset_cache_for_tests()` 는 두 저장소를 비운다.
  - 🔴 `boot_manager._previous_trading_day` 를 재사용하지 않는다 — 그 함수는 조회 실패를 「영업일」로 삼키는 관측용 fail-open 이라(`is_market_open` 이 실패 시 True) 「모르면 실행한다」를 표현할 수 없다. 🔴 naive 벽시계 호출(`datetime.now()`·인자 없는 today 계열) 금지.
  - 테스트는 루트 `tests/conftest.py` autouse `_neutralize_trading_calendar` 가 seam 을 `None`(모름)으로 바꾸고 메모를 비운다(옵트아웃 마커 `real_trading_calendar`). 그래서 기존 테스트는 슬롯 게이트에서 `calendar_unknown → RUN`, prepare 에서 `expected_head=None` 을 본다. 가드 `test_cycle363_trading_calendar.py` · `test_cycle363_ast_business_day_gate.py`.
- **`daily_emit_cap.py`** — `KstDailyEmitCap` = KST 날짜 경계 자기 리셋(`should_emit`/`mark_emitted(key, *, now=None)`) + `emit_once(key, log_fn, msg, *args, now=None)`(peek → 로그 → mark, `log_fn` 이 예외면 mark 하지 않고 trace). **신규 관측 마커의 표준 진입점**이다. `count_matching(predicate, *, now=None)` = 오늘(KST) 기록된 키 중 `predicate(key)` 가 참인 개수를 세는 **읽기 전용** 메서드다(cycle348) — 상태를 바꾸지 않고, 세기 전에 `should_emit` 과 같은 날짜 자기 동기화를 먼저 태워 날짜가 바뀐 뒤 전날 키를 세지 않는다(never-raise, 실패는 0). 호출부가 새 가변 모듈 전역 없이 일일 카운트를 얻는 수단이다(소비처 = `observe_macd_stage6` 의 일일 상한). `KstDailyEmitCap` 에만 있고 기반 `DailyEmitCap` 에는 없다 — 기반은 cycle258 K-12 byte 불변 계약이다.
- **`observer_trace.py`** — 관측기 자기 실패 흔적의 단일 정책 leaf. `trace_observer_failure(marker, key, cap=None, *, now=None, dest_logger=None)` = `logger.debug(exc_info=True)` **항상** + cap 이 있으면 `f"{marker} observer_failed key={key}"` WARNING **1회/(marker, key)/일**(실패 cap 키 `marker|key__observer_failed__` — 정상 키와 비충돌), never-raise. 근거 = debug 단독은 도입 이전의 무음과 구별되지 않는다. 실패 흔적 서식은 `observer_failed` 토큰 **하나**다. `dest_logger` 는 호출자 로거 주입용. `src.*` import 는 `daily_emit_cap` 뿐. 관측 배관(`observer_trace`·`KstDailyEmitCap`) 미적용 잔존(권고만 — `risk.py`·`scanner.py` 는 8영역이라 승인 대상) = `risk.py` `_maybe_emit_pre_market_gate_divergence`(`_pre_market_divergence_day` 자기 리셋 + `except Exception: pass`) · `risk.py` `_maybe_emit_day_high_adopted` · `scanner.py` `_apply_trade_amount_filter` 의 `[trade_amount_filter_scanner_skip]` · `kojiro.py` `_is_open_risk_capped`(뒤 셋은 `mark_emitted` 가 로그보다 먼저다).
- **`uptime_monitor.py`** — 프로세스 가동 하트비트 + 부팅 tick blind 계측(never-raise 관측 전용). 60초 하트비트 = `system_config.set_task_last_success("engine_alive_heartbeat")`(신규 테이블 0). 부팅 시 `[tick_blind_boot] downtime_secs=… market_blind_secs=… after_market_blind_secs=… pre_market_blind_secs=…` — `market_blind_secs` 는 평일 09:00~15:30 겹침(공휴일 미고려 근사 = 과대계상 보수 방향)이고 **`> 0` 이면 WARNING** = 장중 다운으로 손절 사각이 실제로 있었다는 실측이다(WARNING/INFO 분기는 이 필드만 본다). 뒤 두 필드는 KRX 애프터마켓 16:00~20:00 · NXT 프리마켓 08:00~08:50 겹침(참고용, cycle366). 겹침 3함수 `market_blind_overlap_secs`/`after_market_blind_overlap_secs`/`pre_market_blind_overlap_secs` 가 공용 코어 `_weekday_window_overlap_secs(start, end, window_open, window_close)` 를 창만 바꿔 쓴다. 배선 = `boot_manager` 갭 보고 1회 + `ensure_heartbeat_loop` idempotent 스폰(자기 종료 루프, scheduler 무접촉). 일일 리포트 = `tick_blind`(`_aggregate_tick_blind`) + `report_accuracy.{after_market,pre_market}_blind_secs_total`(`_aggregate_extended_blind`). 🔴 WS 재연결 blind 는 stale watcher 소관이다 — 여기서 중복 계측하지 않는다.
- **`refresh_progress.py`** — universe / basics / daily / master / financial **5 작업**의 진행 state(모듈 전역 dict + `threading.Lock`). 헬퍼 `start_progress` / `update_progress` / `finish_progress` / `get_progress` / `get_all_progress` / `is_running`(409 판정용) / `reset_progress` / `reset_all_progress`. state schema **10키** = `status`(idle/running/completed/failed) · `total`/`processed`/`updated`/`skipped`/`failed` · `started_at`/`finished_at`(KST `+09:00` ISO) · `elapsed_ms` · `error_message`. 🔴 `TaskKey` Literal 과 `TASK_KEYS` tuple **2 위치 동행**이 AST 영구 가드다. 🔴 uvicorn 단일 워커 필수 — process-local state 라 multi-worker 면 조용히 어긋난다.

### 출처 절: 모듈 맵 › 순수 함수 leaf (DB · HTTP · 시계 미접촉, 8영역 미접촉)

- **`quant_score.py`** — `compute_f_score_7(curr, prev) -> int|None`(Piotroski 9지표 중 **7지표** — 현금흐름표 TR 부재로 CFO 2지표 제외, 개별 결측은 미가점, 2기 부족은 fail-open `None`) + `compute_magic_formula(series_by_ticker, mktcap_by_ticker) -> dict`(EY = 1/`ev_ebitda`, 폴백 `bsop_prti`/EV · ROC = `bsop_prti`/((`cras`−`flow_lblt`)+`fxas`) · `mf_rank` = `ey_rank`+`roc_rank`).
- **`kojiro_indicators.py`** — 고지로 대순환 지표 `ema` / `atr`(Wilder `ewm(1/period)`) / `stage_of`(6배열 + 동가 유지) / `enrich`(EMA 5·20·40 + 스테이지 + 대순환 MACD1/2/3 + 밴드폭 + ATR). pandas 사용, `KojiroIndicatorConfig` 주입. 🔴 **ATR = Wilder `ewm(1/20)` 로 donchian 의 `_atr`/`get_atr`(단순평균)과 다르다** — 손절선 정의의 단일 진실원이라 서로 재사용 금지.
- **`ta_indicators.py`** — `rsi(closes, period=14) -> float|None`(Wilder 평균, all-gains→100 / all-losses→0 / flat→50 / `len < period+1`→None) + `relative_strength(stock_closes, index_closes, period=20) -> float|None`(종목 N일 수익률 − 지수 N일 수익률 %p, 양수 = 지수 초과 강세). 🔴 **시리즈는 ASC(과거→최신) 기대** — `get_recent_daily` 는 DESC 라 호출자가 역순으로 바꿔 넣는다. 🔴 `kojiro_indicators` 의 `ema`/`atr` 재사용 금지(ATR 이원화).
- **`te_metrics.py`** — `compute_te_rr(pairs, *, now, window_days=90, strategy_id="") -> TeRrMetrics`(19필드). 입력 = `get_trade_pairs` 출력(진입가 기준 `profit_rate`). 모집단 = `status=='closed' ∧ sell_date ≥ now − window_days`(청산일 윈도우, open 제외). `te_pct` = `profit_rate` 단순평균(`compute_metrics` 의 매도가 기준 재사용 금지) · `win_rate` = W/N(보합 포함 분모) · `rr` = `avg_win`/|`avg_loss`|(전승이거나 `min(W,L) < 5` → None) · `required_rr` = L/W(서적의 (1−승률)/승률 은 보합=0 특수해) · 표본 게이트 `sample_tier`(N<20 / 20-49 / 50+) + `rr_available` + `verdict` + `structure_tag` + `single_trade_dominant`. 소비 = `GET /api/strategies/te`(5분 캐시). 관찰 전용.
- **`turtle_sizing.py`** — `compute_unit_qty(budget, atr, risk_pct, fraction=1.0)` = `floor(예산 × risk_pct ÷ ATR)` + `compute_unit_qty_guarded(...)` = 변동성 floor(`atr/price < min_vol_pct` → 0 = `position_ratio` 낙하) + 잔여예산 클램프 + **notional 상한** `min(qty, int(예산×position_ratio)//price)`. 그 notional 상한이 "**터틀 수량 ≤ 비중 수량**" 을 항등으로 만든다. 호출은 전략 `calc_buy_quantity` 뿐. 🔴 `max_lot_units`(K) 캡 산출도 이 함수를 `fraction=K` 로 **재사용**한다 — 새 수식을 쓰지 않는다.
- **`portfolio_risk.py`** — `extract_hard_stop_pct(params, *, default=-7.0)`(후보 7키 `stop_loss_rate` / intraday / overnight / main / pre_nxt / `turtle_backstop_pct` / `hard_stop_pct` 중 **음수만** min, 결측 → −7.0 fail-open, 0.0 금지) + `compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of) -> dict`(포지션 리스크 프록시 = `buy_price × qty × |hard_stop%| / 100`, `by_strategy`(0 포지션 포함) / `by_sector`(포지션 있는 것만) / `top_sector` / `open_risk_pct_of_net`) + `check_budget_invariant(strategies) -> list[dict]`(`params.position_ratio × params.max_positions > 1.0 + 1e-9` 위반 목록, 결측·0 이하·예외는 skip = fail-open). **배제 0 — 입력 무변경.** 소비 = `GET /api/portfolio/risk` · 일일 리포트 `portfolio_risk_snapshot` · `boot_manager`. 🔴 8영역 파일에서 `portfolio_risk` 참조 0건 + 이 파일에서 `_kojiro_sector_key`/`trading_scheduler`/registry/db import 0건이 AST 가드다. ⚠️ `check_budget_invariant` 는 `position_ratio × max_positions` 축만 본다 — **Σweight ≤ 1.0 축은 보지 않는다**(라우트 Σ 가드 + `[weight_config_anomaly]` 담당).
- **`position_exit_lines.py`** — 잔고 화면의 **청산선(손절가·목표가) 해석 단일 진실원**. `resolve_exit_lines(strategies, ticker) -> {strategy_id, stop_price, stop_source, target_price, target_source}` + `build_exit_line_map(strategies, tickers)`. **순수·read-only·never-raise·`await`/DB/HTTP 0** — 전부 in-memory registry 조회다. 소비처 = `routes/balance.py`(graceful — registry 조회가 실패해도 잔고는 그대로 나가고 전 종목이 `—`). 보유 전략 미상(수동 매매분)은 전 필드 `None`.
  - 손절선 2단 = `get_effective_stop_price`(보유형 4전략, `check_exit_signal` 과 **동일 산식·동일 상태 소스**) → `hard_pct`(`buy_price × (1 + 하드손절%/100)`). 🔴 **`extract_hard_stop_pct` 의 기본값 −7.0 으로 계산한 숫자를 내지 않는다** — sentinel 을 넣어 **키가 실제로 있을 때만** 값을 낸다(없으면 `None`). 없는 값을 그럴듯하게 만들면 운영자가 설정한 적 없는 손절가를 보고 버틴다.
  - 🔴 **`_MODE_DEPENDENT_STOP_STRATEGIES`(= LTV)는 `hard_pct` 근사를 내지 않고 `stop_source="mode_dependent"` 로 둔다** — LTV 는 보유 중 모드가 갈려(당일 `intraday_stop_loss` / 상한가 `overnight_stop_loss`) `extract_hard_stop_pct` 의 음수 min 이 두 모드 중 느슨한 쪽을 낸다. 그러면 더 조인 모드에서 운영자가 여유를 더 있다고 오판한다. 모드는 `_limit_up_reached` 메모리라 leaf 가 밖에서 판정할 수 없다. 정확히 내려면 그 전략에 미러를 붙여야 하고, 그것은 `account_risk_watcher` 의 SOFT 게이트 입력을 바꾸므로 **`domain-consult` 선행**이다(별건).
  - 🔴 **목표가는 전략의 read-only 미러 `get_effective_target_price(ticker) -> (target, already_hit)` 에서만 읽는다** — `get_targets_status()` 는 `_candidates` 를 순회하는데 **보유 종목은 후보 자격을 잃는 것이 정상**이라 그 경로로는 목표가가 **간헐적으로 사라진다**. 남아 있는 날에도 값은 live 재검출 구조 기준이라 엔진 §3(진입 stamp)과 갈릴 수 있다. 🔴 **목표가는 `bull_flag_breakout` 의 `measured_target` 하나뿐**이고 그것도 **부분 익절 트리거**다. ⚠️ **VB·LTV 의 `target_price` 를 목표가로 쓰지 않는다** — 그것은 **매수 트리거 가격**이라 이미 산 종목의 목표가 칸에 넣으면 거짓 정보다. 🔴 **가격 무관 청산은 어느 출처에도 안 담긴다**(VB 15:20 일괄매도 · kojiro stage3 · 익일청산) — 프론트 툴팁이 그 사실을 말한다.
  - 🔴 **`engine_running=False` 면 판정 불가를 `stop_source="engine_idle"` 로 구분한다** — 21:30 `_reset_daily_state` 가 메모리 포지션을 비우고 07:45 `_boot()` 가 DB 에서 되살리므로, 그 사이 약 10시간은 보유가 있어도 청산선을 알 길이 없다. 「손절선이 없다」와 「지금은 모른다」를 같은 `—` 로 접으면 운영자가 아침에 **손절이 안 걸려 있다**로 읽는다. ⚠️ 판정은 **엔진 상태**(`trading_scheduler.is_running`)로 한다 — 「메모리 포지션이 0」으로 추론하면 수동 매수분만 든 정상 상태가 엔진 정지로 잘못 찍힌다.
  - 회귀 = `tests/unit/engine/test_cycle339_position_exit_lines.py` — 🔴 **후보 표면을 읽으면 붉어지는 양성 대조군**을 포함한다.
- **`sector_naming.py`** — 보유 종목 섹터명 해석 **단일 진실원**. `resolve_sector_name(ticker, *, basics_raw=_UNSET)` + `resolve_sector_names(tickers)`. 우선순위 = basics raw `bstp_kor_isnm`(사람이 읽는 업종 한글명) → `_kojiro_sector_key(master_raw)`(KRX 산업지수 플래그 → 업종코드) → `미분류-{ticker}`(독립 키 fail-open). `basics_raw` 주입 시 `stock_master.get` 재조회를 생략한다. 🔴 소비처 3곳(`routes/portfolio.py` · `log_analysis_engine.py` · `routes/balance.py`)이 전부 이 함수에 위임한다 — 섹터명 로직을 다른 곳에 복제하지 않는다(회귀 가드가 중복 재발을 막는다). ⚠️ `idx_bztp_lcls_cd_name`("시가총액규모중")은 섹터가 아니다 — 사용 금지.
- **`account_risk_guard.py`** — 계좌 SOFT Σ상한 순수 판정. `evaluate_soft_gate(open_risk_pct, *, warn_pct, block_pct) -> {level: ok|warn|block, reasons}`. **`block_pct=None` 은 다크런치**라 어떤 값도 block 되지 않는다(DB `account_risk_block_pct` 한 줄로 활성, 권고 6.0). pct 가 None 이거나 음수면 ok fail-open. DB/HTTP/registry/scheduler import 0(AST G-3). 🔴 임계를 발화시키려고 낮추지 않는다 — 관측 경보 4% 의 발화 빈도가 유일한 학습 신호다.
- **`llm_features.py`** — LLM 매수평가 입력 조립 순수 함수(`src.*` import 0): `ema`(시드 = 첫 period 단순평균) · `rsi_wilder`(완전 평탄 = 50) · `macd` · `atr_wilder` · `hv_annualized`(ddof=1 × √252 × 100) · `channel` · `normalize_volume_ratio` · `pct_change` · `sanitize_text`(개행·`|` 제거, 종목명 20자, 주입 방어) · `compute_technicals(bars_desc, *, current_price, today_open_won=0)` · `build_messages(payload, tech, bars30)` · `snapshot_keys_for(sid)`(전략별 NA 키 제거, `_SNAPSHOT_KEYS` 순서 유지). 전략 컨텍스트 `_STRATEGY_META` 는 **7 전략**을 담는다(`name`/`entry_rule`/`matters`). 스냅샷은 화이트리스트 `_SNAPSHOT_KEYS` 로만 조립한다 — 설정값·datetime 이 모델로 새지 않는다. 🔴 `json.dumps` 는 try **밖**이다(조용한 `{}` 폴백 금지 — 실패는 `reason=payload_error` 로 남는다). `meta.schema_version="cycle276.1"`. ⚠️ `_SNAPSHOT_KEYS` 를 바꾸면 `llm_buy_gate._prompt_version()` 해시도 바뀐다(가드 `test_c30_2b/2c`). 단가 상수는 `log_analysis_engine.py` 와 이원화돼 있다(후속 F-274-3).
- **`llm_retrospective.py`** — 주간 회고 조인·집계 순수 함수(`src.*` import 0 · I/O 0 · `await` 0). `join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date)` + `aggregate(rows, *, cost_pct)`. 🔴 매칭 축은 **`(order_no, trade_date)`** 다 — KIS `ODNO` 는 하루 단위로만 유일해서 주문번호 단독 매칭은 같은 번호의 다른 날짜 평가를 붙인다. `primary` = 첫 매수 주문(`buy_order_nos[0]`)의 평가(한 페어에 매수 2건 이상이 실측되고, 사이클을 연 판단은 첫 매수다). 🔴 평가 없는 페어를 버리지 않는다 — 버리면 분모가 사라져 커버리지를 못 잰다. 손실 정의는 `profit_rate <= cost_pct`(기본 0.25, 경계 포함). 소비 = `GET /api/llm-evaluations/retrospective`.
- **`market_state.py`** — 장운영상태의 **단일 정본**, 순수 데이터 leaf(`src.*` import 0 · I/O 0). `MARKET_TABLE` 13행(KRX K1~K7 · NXT N1~N6)이 시각 구간마다 `order_divisions`·`phase`·`match_kind`·`effective_from/to` 를 담는다 — **날짜 차원이 내장**돼 있어 제도 변경이 `effective_from` 으로 자동 전환된다. `ORDER_DIVISIONS` 28코드(명칭·거래소 지원·`confidence` ∈ `confirmed`/`name_unconfirmed`; 27~29 NXT GTP 와 41~47 KRX 애프터마켓은 KIS 공지 2026-09-09 원문으로 `confirmed` 이고 `docs/kis/domestic-stock-order.md` 의 `ORD_DVSN` 칸과 같은 값이어야 한다) + `FINDINGS` 3행(SOR 폐기 각주 포함). 소비처 = `GET /api/market-state` · `order_engine._route_exchange_by_clock`(이 표만 읽는다 — `order_engine.py` 안 시각 리터럴 0건이 계약) · `tick_channel_clock`. ⚠️ 이 파일을 바꾸면 `python tools/test_fixtures/gen_market_state_fixture.py` 재생성이 딸려 온다(`test_cycle282_fixture_sync.py::test_i1/i2`). 🔴 **`EXCHANGE_ORDER` 의 SOR 열을 지우지 않는다** — 그 표는 "우리가 어디로 주문하는가" 가 아니라 "KIS 가 그 호가유형을 그 거래소에서 받는가" 의 사실 표라, 열을 지우면 41~47 의 SOR 지원이 **확인 필요**라는 사실까지 사라진다(가드 `test_cycle287_sor_retired.py::test_n4`/`test_n4b`). 안 쓰기로 한 사실은 열 삭제가 아니라 **각주**로 적는다. 야간작업 현황은 별도 라우트 `GET /api/market-ops`(`routes/market_ops.py`)가 `scheduler.TIME_*`/`quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` 를 직접 읽는다 — 이 표는 관여하지 않는다. ⚠️ 신규 `src/**/*.py` 파일은 `test_cycle287_ast_scope.py::test_s1b`(`_SRC_TREE_FILES` + `_SRC_TREE_DIGEST`)가 잡는다. **`_PINNED_DIRS`/`test_s1d` 를 신규 파일 차단 근거로 인용하지 마라 — 비교 양변이 모두 디스크에서 만들어져 공허하다.** 상세 = `src/routes/CLAUDE.md`.
- **`param_catalog.py`** — 7 전략 `DEFAULT_PARAMS` 합집합 **105 키의 단일 진실원**, 순수 데이터 leaf(`src.*` import 0 · I/O 0 · 모듈 로드 부작용 0). 키마다 `ParamSpec`(`label_ko`/`group`/`type`/`min`/`max`/`step`/`unit`/`editable`/`risk`/`auto_tunable`/`deprecated`/`deprecated_for`/`range_src`/`pattern`/`choices`/`applies_to`/`help`/**`min_items`**/**`forbidden_choices`**).
  - 🔴 **범위를 지어내지 않는다** — `range_src` ∈ `clamp`(읽는 쪽 하드 클램프 6) · `param_ranges`(`PARAM_RANGES` 원문 복사 24) · `sign`(부호 규약 6) · `structural`(자료형·구조 필연) · `enum`(값 집합) · **`none`(근거 없음 → min=max=None, 8키 — 전부 `deprecated=True ∧ editable=False`)**. ⚠️ 범위를 `PARAM_RANGES` 에서 **파생시키는 것은 그 범위가 실제 운영값을 담을 때만 안전**하다 — 못 담으면 그 키를 보내는 저장이 전면 422 가 된다. `auto_tunable` 은 `PARAM_RANGES` 를 **그대로 반영**하고 그 집합을 넓히지 않는다(AI 자동 조정 가능성과 사람의 편집 가능성은 별개다).
  - `deprecated`(8, 전부 `editable=False`)는 **숨기지 않고** 회색 배지로 보여 준다 — 값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다. 전략 한정 무효는 전역 플래그가 아니라 `deprecated_for` 다(유일 사례 `k_value_nxt_pre`/`_post` → VB. LTV 는 야간 목표가에 **실제로 곱한다**).
  - `min_items`(list_str 최소 항목 수 — `tradable_boards`=1 · `exclude_tickers`=0)와 `forbidden_choices`(전략별 금지 선택지 — 유일 사례 VB + `post_nxt`, 루트 `CLAUDE.md` 의 'POST_NXT 추가 금지' 를 데이터로 옮긴 것)는 검증과 화면이 같은 근거를 읽게 하려고 카탈로그에 둔다. ⚠️ 빈 목록을 **자료형 단위로** 막지 않는 이유 = 빈 목록의 뜻이 키마다 정반대다(`exclude_tickers=[]` 는 '제외 없음' 이라는 정상 기본값이다).
  - `trailing_stop_rate` 도움말은 **적용 범위**를 명시한다(cycle365) — momentum·LTV 둘 다 **익일 청산 모드**(갭 ≥ `gap_up_threshold` 유지)에서만 쓰이고 당일 손절에는 쓰이지 않는다(LTV 는 추가로 전일 상한가 도달 종목 한정).
  - `exchange` 의 `SOR` 은 `Choice(deprecated=True)` + 라벨 `"SOR (폐기 — 주문에 쓰이지 않음)"` 로 어휘에 남아 있다. 어휘에서 지우는 것은 `test_cycle287_sor_retired.py::test_n3b` 가 강제하는 순서(코드 → D+1 → 카탈로그/프론트 → DB)를 따르는 별도 작업이다. 🔴 `exchange` 는 `editable=True` 로 남는다 — `editable=False` 로 만들면 그 키를 보내는 모든 PUT 이 422 다. `<select>` 의 `<option>` 은 브라우저가 스타일을 제한해 `choice.deprecated` 회색 처리가 닿지 않으므로 **라벨 자체가 유일한 폐기 신호**이고 프론트 회귀 가드가 그 문자열을 봉인한다. 두 PUT 클라이언트(`Settings.tsx`·`StrategyParamsEditor`)는 변경분만 보낸다.
- **`param_validation.py`** — 파라미터 검증 순수 함수(`param_catalog` 만 import). `validate_params(strategy_id, current_params, incoming) -> ValidationResult(errors, warnings, accepted)`. 판정 순서 = 키 존재 → `editable` → 자료형 → `choices`/`pattern` → 금지 선택지(`forbidden_choice`) → min/max · 최소 항목 수(`too_few_items`) → 예산 불변식(병합 결과) → 순서 불변식(경고). 🔴 **첫 오류에서 멈추지 않는다** — 한 저장에 여러 필드를 고치는 화면이라, 멈추면 운영자가 오류를 하나씩 왕복하고 그 왕복마다 all-or-nothing 이 다시 걸린다. 예산 불변식 `position_ratio × max_positions <= 1.0` 은 EPS=1e-9 로 경계 1.0 을 **통과**시키고(7 전략 중 6 전략 기본값이 정확히 1.0), **이미 위반 중인 상태를 악화시키지 않는 편집은 통과 + `budget_invariant_preexisting` 경고**다(막으면 그 전략이 영구 편집 불가 = 복구 수단이 DB 직접 UPDATE 뿐이다). 빈 `tradable_boards` 는 **422** 다 — 효과가 전략마다 정반대라(momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS` 폴백으로 매수를 계속하고, BFB·VCP·kojiro 는 공집합 = 매수 전면 중단) 어느 쪽도 운영자의 의도가 아니고, 매수를 멈추는 정당한 수단은 `buy_paused` 다(전략 비활성화는 보유분의 손절까지 멈춘다 — 루트 금기). VB + `post_nxt` 도 **422**. ⚠️ `applies_to` 는 PUT 의 관문이 **아니다**(의도된 fail-open) — 미지 키 판정이 `key in current_params` 라 DB 드리프트로 들어온 소관 밖 키는 저장된다. 그 전략이 읽지 않는 키라 매매 영향이 0 이고, 조이면 비상 `curl` 롤백 경로가 좁아진다. 소비처 = `routes/strategies.py::update_params`. AI 자문 수동 적용 경로(`routes/recommendations.py`)는 이 함수를 거치지 않는다 — 검증 비대칭이 남아 있다.
- **`param_drift.py`** — 운영 DB params ↔ 코드 `DEFAULT_PARAMS` 드리프트 **관측 전용** 순수 함수 leaf(`src.*` import 0 · I/O 0). `_load_strategy_config` 가 DB params 를 키별로 덮으므로 한 번 박힌 DB 값이 계속 살고, 코드 기본값만 읽으면 운영값을 오판한다. `collect_param_drift(strategies) -> list[{strategy_id, key, live, code}]` — 실행 params(`config.params`) 와 `DEFAULT_PARAMS` 를 키별로 비교한다. 수치는 `4` 와 `4.0` 을 같다고 보고(`_same`, 오차 1e-9), bool 은 `is` 로 비교한다. **코드에 없는 키는 차이로 세지 않는다**(운영 전용 키를 세면 매일 경고가 나 배경 소음이 된다). 판정 불가·예외는 조용히 건너뛰고 예외를 올리지 않는다. 소비처 = `boot_manager.boot` 가 `_load_strategy_config` 직후 1회 부른다 — 차이가 있으면 `[param_drift] count=N` WARNING(예시 5건), 없으면 INFO, 호출 실패는 `logger.exception` 후 부팅 계속. 🔴 **값을 바꾸지 않는다** — DB 가 정본이고, 차이 대부분은 운영자가 의도로 넣은 값이라 코드값으로 되돌리는 것이 곧 사고다. 회귀 = `tests/unit/engine/test_cycle326_param_drift_visibility.py`.
- **`etf_like.py`** — ETF/ETN(류) 판정 **단일 진실원**. 표준 라이브러리만 import 한다 — `db/stock_master.py` SQL 빌더가 같은 상수를 읽어야 하는데, `scanner.py` 에 두면 8영역의 무거운 import 가 SQL 빌더까지 끌려온다.
  - 판정 = `raw` 가 Mapping 이고 `scty_grp_id_cd` 가 strip 후 비어 있지 않으면 **코드만** 본다(strip+upper 가 `ETF_GROUP_CODES` 에 드는가). 이름은 보지 않는다. 코드가 없으면(`raw` 가 None·Mapping 아님·키 없음·None·빈 값·공백) 이름 키워드 부분일치(대소문자 구분)로 떨어진다. `raw` 를 바꾸지 않는다.
  - 소비처 셋 = `stock_master.list_by_filter(exclude_etf_like=True)` 의 SQL 판정(상수를 여기서 가져간다) · 6 전략 `_scan_universe` 루프(SQL 뒤 방어 겹) · `scanner.scan_stocks`(momentum).
  - 🔴 **momentum 은 이름 폴백만 탄다** — 원천인 KIS 등락률 순위(`FHPST01700000`) 행에 `scty_grp_id_cd` 가 없다. 이름이 키워드에 걸리지 않는 ETF(KIWOOM·TIME·1Q 등)는 이 경로에서 막히지 않는다.
  - RT·FS·DR·IF·MF 는 ETF 로 보지 않는다 — 시총·거래대금 컷을 넘으면 유니버스에 든다.
  - 🔴 판정을 다른 자리에 다시 쓰지 않는다. `ETF_KEYWORDS` 순회는 이 파일과 `stock_master.py` SQL 빌더 두 곳뿐이다(G1). 전략 파일은 `ETF_KEYWORDS` 를 참조하지 않는다(G2). `stock_master.py` 는 코드·키워드 문자열을 다시 적지 않는다(G6). `order_engine._observe_after_exit_etp` 의 코드 집합과 같아야 한다(G7 — 표류 감시). 가드 = `tests/unit/ast/test_cycle380_ast_etf_like.py`.
- **`backtest_yaml.py`** — 전략 → 외부 MCP 백테스트 서버 YAML DSL 변환. `build_yaml(strategy_id, params)` 가 변환하는 것은 `momentum` · `volatility_breakout` · `donchian_swing` 셋뿐이고, LTV·BFB·VCP 와 그 밖 id(kojiro 포함)는 `BacktestNotSupportedError` 다. 유일한 import 처 = `backtest_engine.py`(20:00 자문 INSERT 직후 자문 행마다 `current`·`recommended` 2 job fire-and-forget — 변환 못 하는 전략은 `skipped`). 매매 hot path 무관.

### 출처 절: 모듈 맵 › 시세 채널 (통합 채널 소멸 후)

채널 규칙(구간표 · 층별 폴백 · 전환 창 · 자동 원복 · 운영 다이얼 4키 · 폐기 키 재사용 금지 · `off` 가 되돌리지 못하는 것)의 정본 = `src/realtime/CLAUDE.md` 「시세 채널」 절. 여기에는 엔진 모듈의 계약만 적는다.
- **리졸버 `scanner._resolve_channel`** — 공개 입구는 `scanner.tick_tr_id_for(ticker, *, priority, now)` 이고, 판정은 시각축(`tick_channel_clock.clock_channel`) × 속성축(`scanner._classify_channel`) 합성이다. 시각축이 `H0STCNT0` 을 주면 속성축을 **호출하지 않는다**. 그래서 전환 시각 뒤 KRX 연속체결 창(정규장+애프터)에서는 `nxt_tradable` 과 무관하게 전 종목이 `H0STCNT0` 이고, `nxt_tradable` 이 채널을 가르는 것은 시각축이 `H0NXCNT0` 을 주는 프리 창(그리고 자동 원복 래치가 선 날)뿐이다. 속성축의 통합 반환은 여기서 NXT 로 흡수된다. 프리 창에서 `nxt_false` 를 KRX 채널에 두는 근거는 커버리지가 아니라 **전환 횟수**다 — 걷으면 프리 창 KRX 프레임(K2 08:30~08:40 장전 시간외 종가 — 전일 종가 고정)과 전환 폭 감소분을 잃을 뿐, 정규장 시세·매수 평가에는 닿지 않는다.
- **`tick_channel_mode.py`** — 채널 리졸버 **킬스위치 모드 leaf**(`system_config.tick_channel_resolver_mode`). API = `current_mode()`(동기, hot path) · `refresh_mode()`(async) · `apply_mode(mode)`(라우트용 즉시 메모리 반영) · 테스트 seam 2. 🔴 `refresh_mode()` 에 프로세스당 1회 래치를 두지 않는다 — 래치가 있으면 킬스위치가 아니다. 🔴 **장중에 닿아야 한다** — D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지) 때문에 "다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다. 즉시 경로 = `PUT /api/realtime/tick-channel-mode`(DB 저장 + **같은 요청에서** 메모리 값까지 덮는다). 폴링 백업 2곳 = `scanner.subscribe_filtered_stocks`(5분) · `stale_watcher_core.check_and_resubscribe_stale`(120초). 실패 방향 = DB 조회 실패·키 부재·미지 값 전부 **현재 값 유지**(기본값 되돌림 금지 — 운영자가 `off` 로 내려놓은 뒤 조회가 한 번 실패했다고 다시 켜지면 안 된다) + 미지 값은 `[tick_channel_mode_invalid]` WARNING. 시각 리터럴 0건. `system_config` 헬퍼는 `src/db/system_config.py`.
- **`tick_channel_clock.py`** — 채널 **시각축 판정 leaf**. 동기·순수·never-raise, `await`/DB/HTTP 0(AST G-294-14). API = `_windows(on_date)` → `(krx_regular_open, nxt_pre_end, krx_continuous_end)` · `switch_at(on_date, *, offset_secs)` · `clock_channel(now, *, offset_secs)` → `(tr_id, reason)` · `set_day_revert()`/`day_reverted()`(자동 원복 래치, 벽시계 날짜 경과 시 자기 해제 — **시계를 못 읽는 경로에서도 날짜 키가 비면 안 된다**: 비면 리셋 조건이 영원히 거짓이라 영구 좌초다) · `switch_windows()`/`active_switch_window()` · 관측 `emit_clock_config()`/`note_pre_window_frame()`/`emit_pre_window_frame_summary()` · `reset_state_for_test()`. 표 파생값은 **날짜 키로 메모**한다(`risk.on_tick` 이 코호트 종목마다 부르는 경로다). `clock_channel` 은 `priority` 키워드를 받지만 **판정에 쓰지 않는다**(제거하면 `scanner.py` 8영역 연쇄 변경이라 인자만 남겼다). 🔴 **통합 채널을 절대 반환하지 않는다** — 판정 실패의 폴백도 `H0STCNT0` 이고 "구독을 안 한다" 방향으로는 가지 않는다. 시각 리터럴 0건·`match_kind` 선택·전환 시각 clamp 식·전환 창 `pre_to_krx` 하나 = realtime 「시세 채널」 절.
- **`tick_channel_switch.py`** — 살아 있는 구독의 **채널 전환 + 자동 원복 leaf**. `run_switch_cycle(scheduler, pool, *, now)` 가 120초 `stale_watcher_core.check_and_resubscribe_stale` 안에서 불린다(**never-raise** — 전환 실패가 4중 안전망의 한 축을 끊으면 안 된다). 창 밖 전환 금지와 그 근거 = realtime 「시세 채널」 절 + 아래 `tick_volume.py`. 🔴 **세션 재추첨 금지** — `websocket_pool.switch_channel_same_session` 은 `_ticker_to_session` 을 **읽기만** 한다(다른 세션에 떨어뜨리면 그 dict 가 덮여 구 세션 튜플이 영구 고아로 41 슬롯을 잠식한다). 자동 원복은 비교 코호트가 전부 침묵이면 그 사이클을 `reason=market_wide` **비결론**으로 두고 2×probe 뒤 escalation 한다. `_revert_probe_done` 은 결론적 판정에만 세운다(상한 `MAX_REVERT_PROBE_ATTEMPTS=10`). 되돌림은 make-before-break + `tick_channel_clock.set_day_revert()` + `[tick_channel_auto_revert] n= reverted= failed= …` **ERROR** 1행이다(ERROR 인 이유 = `pattern_by_level` 이 WARNING 이상만 21:30 리포트 `top_patterns` 에 넣는다). 전환 대상에서 진단 프로브 튜플과 비-TICK 라우팅(체결통보 등)을 뺀다 — 없으면 `wanted` 가 항상 전용 TICK 이라 체결통보 구독까지 전환 대상이 된다. LOW 전환 실패는 `_ticker_to_session`/`_ticker_to_tr_id` 를 **동행 pop** 해 다음 사이클이 재구독하게 한다(안 하면 세션 튜플 0 + 라우팅 잔존 = 20:00 까지 자가 치유 없는 구독 좀비다).
- **`no_feed_registry.py`** — `nxt_tradable=False` 종목 집합 leaf. `ensure_fresh(tickers, *, ttl_secs=600)` 이 `stock_master.get_nxt_tradable_map` 1회로 집합을 적재한다(ttl 경과·미지 ticker 유입 시 전체 재조회, 예외 시 이전 집합 유지 + `[no_feed_registry_refresh_failed]` 1회/일 + 다음 호출 재시도, `None` = 마스터 부재는 no_feed 아님).
  - 그 밖 API = `is_no_feed(ticker)` · `is_provenance_ok(ticker)`(그 행 raw 에 KIS `cptt_trad_tr_psbl_yn` 키가 있는가 = 값의 출처가 권위 있는가 — `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 도장하는 창에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어, 도장값을 그대로 믿으면 진짜 NXT 종목을 프리장 무체결 채널로 보낸다) · `is_classified(ticker)`(분류한 적 있는가 — `is_no_feed` 의 "모르면 False" 는 **미지**와 **송출 정상**을 같은 값으로 접는다. `is_no_feed` 의 극성은 그대로다) · `snapshot()` · `reset_state_for_test()`.
  - 🔴 출처 조회 `get_nxt_provenance_map` 은 `get_nxt_tradable_map` 과 **독립 try** 다 — 한 try 로 묶으면 출처 쿼리가 실패하는 날 churn 차단까지 함께 죽는다. 소비처 2 = `stale_watcher_core.check_and_resubscribe_stale` + `scanner._classify_channel`.
  - 🔴 **구독 전에 덥혀야 한다** — `scanner.subscribe_filtered_stocks` 가 리졸버를 부르기 **전에** 그 사이클 대상 전체로 `ensure_fresh` 를 부른다(AST 가드 A22 가 순서를 잠근다). 안 덥히면 아직 구독하지 않은 후보는 분류될 수 없어 07:59 사전 구독 코호트 전체가 판정 불가로 빠진다. scheduler/scanner/realtime/registry import 0(AST G-252-1).
- **`tick_volume.py`** — 실측 누적거래량 관측 leaf. WS payload `[13] ACML_VOL` → `handler._parse_acml_vol` → `on_tick(*, acml_vol=)` → `record_acml_vol`(last-write-wins) → BFB·VCP 거래량 게이트가 읽는다. 🔴 **`acml_vol` 은 채널마다 따로 쌓인다 — 채널이 다른 두 값을 비교·합산하지 않는다**. 채널 전환 뒤 첫 프레임이 새 채널 누적으로 덮는 것은 의도한 동작이다(KRX 거래량 게이트는 KRX 누적을 봐야 한다). 전환이 안전한 전제는 전환 창에 프레임이 구조적으로 0 인 것과 이중 채널 구독 금지 둘이다 — 하나라도 깨지면 last-write-wins 가 두 누적을 번갈아 쓰는 비결정론이 된다.

### 출처 절: 모듈 맵 › VI · 장운영 채널 (H0UNMKO0)

- **`market_operation_monitor.py`** — H0UNMKO0 **수신·상태 추적**. `handler._handle_market_op` → `record_market_op_event(MarketOpEvent)`. 파싱과 칸 기준점은 `src/api/market_operation.py` 가 정본이다(`src/api/CLAUDE.md` 해당 절). 송신·구독 배치는 형제 모듈 `market_op_subscribe.py` 다.
  - 상태는 **5개**이고 서로 합치지 않는다 — `_vi_active_tickers`(VI 활성 집합) · `_halt_active_tickers`(거래정지 활성 집합) · `_market_op_last_event`(종목별 마지막 이벤트) · `_vi_last_active_at` · `_halt_last_active_at`(각 수명 전용, ticker → 마지막 활성 시각). 두 수명 dict 는 **서로 독립**이다 — VI 타이머가 만료돼도 거래정지 타이머는 그대로다(「멤버십」과 「마지막 활성 시각」을 한 자료구조에 넣지 않는다).
  - **수명** — 해제 프레임이 늘 온다는 보장이 없어서 둘 다 수명을 둔다. 마지막 활성 프레임 뒤 `VI_ACTIVE_TTL_SECONDS`(600초) · `HALT_ACTIVE_TTL_SECONDS`(600초)가 지나면 해제 프레임 없이도 푼다. 매 활성 프레임이 시각을 갱신하고, 명시 해제 프레임(비활성)은 수명을 기다리지 않고 즉시 푼다. 로그는 `[market_op_vi_release] ticker=…` / `[market_op_halt_release] ticker=…` 이고 수명 해제만 뒤에 `reason=ttl` 이 붙는다. 부팅 REST 시드 `seed_vi_active_from_rest` 도 시드 시각을 마지막 활성으로 찍는다(장중 재기동이면 이미 풀린 종목까지 들어온다). 활성 집합에 있는데 시각이 없는 종목은 **발견 시각**을 찍고 그로부터 600초 뒤 푼다 — 무기한 유지하지 않는다.
  - **만료 sweep 은 지연 평가**다(백그라운드 task 없음). `_expire_stale_vi()`/`_expire_stale_halt()` 를 `record_market_op_event` **첫머리**와 읽기 함수들이 먼저 부른다 — VI 는 `is_ticker_stale_excluded` · `get_market_op_active_tickers` · `get_vi_active_tickers` · `get_market_op_state_summary`, 거래정지는 그 넷에서 `get_vi_active_tickers` 대신 `get_halt_active_tickers` 에 `get_circuit_breaker_state` 를 더한 다섯이다. 🔴 sweep 을 `record_market_op_event` 의 기록 **뒤**로 옮기지 않는다 — 만료된 에피소드 위에 온 해제 프레임이 「프레임 해제」로 잘못 적히고(TTL 해제 로그 누락), 만료 뒤 새 활성 프레임이 「갱신」으로 뭉개져 새 에피소드 로그가 사라진다. `reset_market_op_state()` 가 다섯 상태와 CB 1회/일 cap 을 함께 비운다.
  - **소비** — `is_ticker_stale_excluded(ticker)` 를 `stale_watcher_core` 의 두 경로(`check_and_resubscribe_stale` 120초 · `resubscribe_stale_priority` 5분)가 쓴다(VI·거래정지 종목 stale 회피). `get_circuit_breaker_state()` = **관찰 전용 휴리스틱**(거래정지 사유 `_CB_REASON_KEYWORDS` 매칭 **또는** `halted >= _CB_MIN_HALTED(5) ∧ halted/observed >= _CB_HALT_RATIO(0.8)`, `representative_mkop_cls_code`=005930, `halt_reasons_sample`) — KIS H0UNMKO0 에 CB 전용 필드가 없어 휴리스틱 + 계측이 먼저다. `get_market_op_state_summary()` = `circuit_breaker` + `iscd_stat_active_count`(**표시 집합** `_ISCD_STAT_DISPLAY_CODES = {"51","52","53","54","58","59"}` 멤버십으로 `_market_op_last_event` 를 센다. 55·57·00·빈값은 정상 상태라 세지 않는다). `[market_op_cb_suspected]` INFO 1회/일(`reset_market_op_state` 동행 reset). 화면 = `GET /api/realtime/market-operation` → RealtimeHealth 카드.
  - 🔴 **매수 가드 미연계(표시 전용)** — `risk.on_tick` 참조 0. 관리종목(51)·단기과열(59) 청산·당일 매수 차단은 이 모듈이 아니라 `status_exit_watch.py` 가 REST 로 판정한다 — 그 leaf 는 `get_last_event(ticker)` 를 **힌트로 읽기만** 한다(51·59 가 이 프레임으로 온 실측이 없다).
  - 가드 = `test_cycle149_ast_dict_separation.py`(앞 세 dict 분리) + `tests/unit/realtime/test_cycle368_market_op_decisions.py`(수명 V·L·T 묶음, sweep 순서 R 묶음, 판정 S·D 묶음).
- **`market_op_subscribe.py`** — 종목별 H0UNMKO0 구독 **송신·배치 본체**(`subscribe_market_operation_tickers(scheduler)`). `scheduler.py` 에는 5줄 위임 wrapper `_subscribe_market_operation_tickers` 만 있고 호출부는 `_scan_loop` 다. 본체가 leaf 에 있는 이유는 `scheduler.py` 라인 상한(cycle257 영구 상한 **<3,900**)이다.
  - 규약 = HIGH(보유+익일청산)만 · **메인 세션 0건** · `bypass_limit=False` 명시 · 보조 세션 **직접** 라운드로빈(풀 API 미경유 — tr_key 단일 키 라우팅 오염 방지) · `_market_op_subs` **델타** 해제(슬롯 누수 차단) · 소켓 `State.OPEN` 가드(미개방이면 사이클 skip + `[market_op_subscribe_skip]`) · `ConnectionClosedError` 는 break + WARNING 1행 · `asyncio.sleep(0.05)` Rate Limit · 보조 만석이면 `[market_op_subscribe_no_slot]` WARNING(**메인 폴백 금지** = tick > VI 라는 명시적 교환) · `[market_op_subscribe_summary]` main_tick/main_total/main_over 5분 계측.
  - 🔴 **함수-로컬 import 5줄**(`ConnectionClosedError`/`State`/`MARKET_OP_TR_ID`/`MAX_SUBSCRIPTIONS` + `kis_ws`←`websocket` / `kis_ws_pool`←`websocket_pool`)을 **모듈 최상단으로 올리지 않는다** — 회귀 4파일이 정의 모듈의 속성을 monkeypatch 하는데 함수-로컬 import 는 매 호출 재실행돼 그 patch 가 걸린다. 올리면 이름이 import 시점에 바인딩돼 patch 가 무력화되고 `_ws is None → return 0` 조기 반환이 부정 단언을 조용히 초록으로 만든다. 🔴 **두 줄 분리도 유지한다** — 합치면 매 호출 ImportError 로 구독이 전량 미실행된다(2026-07-24 사고).
  - 🔴 `logger = logging.getLogger("src.engine.scheduler")` 고정 — 마커 5종(`[market_op_subscribe_skip]`/`[market_op_no_quote_session]`/`[market_op_subscribe]`/`[market_op_subscribe_summary]`/`[market_op_subscribe_no_slot]`)의 `system_logs` 접두가 바뀌면 운영 grep 사슬이 끊긴다.
  - 가드 = `test_cycle292_ast_market_op_leaf.py` + `test_cycle221_ast_market_op_no_main.py`·`test_cycle214_ast_h0unmko0_pool.py`·`test_market_op_subscribe_import_path_guard.py`·`test_market_op_subscribe_socket_guard.py`(넷 다 부정 단언이라 **양성 대조군**을 함께 심었다 — 본체가 사라져도 초록이 되는 공허 통과 차단).

### 출처 절: 모듈 맵 › 계좌 리스크 · 관측기

- **`account_risk_watcher.py`** — 계좌 Σ오픈리스크 감시자(scheduler 무접촉 자기 종료 루프). `run_account_risk_watch_once(scheduler)` = `registry.all()` + `get_balance()` net + 전략 `get_effective_stop_price` 를 `portfolio_risk(stop_price_of=)` 로 주입 → 척도 병기 스냅샷 → guard 판정 → 순간 게이트. 🔴 **프록시 대체 금지, 병기가 계약이다** — 실효 척도도 갭 관통 손실은 못 잡는다.
  - 배선 = boot 동기 1회 + `ensure_watch_loop` 5분(`_running` False 면 ≤60s 종료, done_callback `[account_risk_watch_loop_died]` WARNING / `[account_risk_watch_loop_exit] reason=running_false` INFO = liveness 표본). 호출은 항상 `run_account_risk_watch_once_guarded`(`asyncio.wait_for`, `_EVAL_TIMEOUT_SECS=300`, 런타임 부등식 `0 < T <= _WATCH_INTERVAL_SECS < _GATE_STALE_MAX_SECS`)를 거친다 — **TimeoutError 만** 포착해 `_gate_active=False` + 스탬프 + `level=error reasons=[timeout]` + `[account_risk_eval_timeout]` WARNING 1회/일(**0건이 정상** — 1건이라도 있으면 그 자체가 hang 실측)이고 `CancelledError` 는 그대로 전파한다.
  - **신선도 계약** = `is_soft_gated()` 는 `_gate_active` 이고 마지막 평가 monotonic 경과가 `_GATE_STALE_MAX_SECS`(= 3 × 주기 = 900s, 리터럴 금지 G-239-1) 이하일 때만 True 다. 초과(stale)·미평가·판정 예외는 전부 **fail-open(False)** + `[account_risk_gate] released reason=stale` 1회/일이다. `get_gate_state()` 는 `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 4키를 더하되 `level` 은 마지막 평가값을 보존한다(동결 서명 = `level=block ∧ stale ∧ !effective_gated`). fail-open 은 **LOUD** 다 — 평가 실패는 `[account_risk_watch_failed]` WARNING 1회/일이고 활성 중 실패면 `released reason=eval_failure`, 타임아웃이면 `released reason=eval_timeout`(둘 다 cap 밖)이다. 🔴 `gate_stale` cap 키는 `gate_block`/`watch_failed` 와 절대 공유하지 않는다.
  - 🔴 단일 기록자 계약 — read 함수에 `global` 금지(G-239-4), `_gate_active` 대입과 스탬프 사이 `await` 0(G-239-5). 마지막 평가 스탬프는 `_evaluated_mono`(성공·실패 공통, `_now_mono` seam)다. `get_gate_snapshot()`(9키 = `get_gate_state()` 8키 + `eval_timeouts_today`) **하나**를 일일 리포트(`portfolio_risk_snapshot.account_gate`, `over_cap` 과 독립 try, `is_soft_gated` 호출 금지 — read 경로가 stale cap 을 선소비하면 안 된다)와 `/api/portfolio/risk`(프론트 `PortfolioRiskCard` 배지)가 공유한다. 로그 = `[account_risk_gate] transition=entered|reconfirm|released` + `[account_risk_watch]` warn/ok(1회/일), 순서는 peek → 로그 → mark.
  - **D1 이원화** — 전략별 일일손실 플래그는 절대 건드리지 않는다(AST G-4 토큰 0 봉인). 소비처 = `StrategyBase._account_soft_gate_blocked`(폴·래치형 5전략은 `check_buy_signal` 첫 문장 / momentum·VB 는 **발사 직전** — 최상단이면 block 구간에 baseline 이 동결돼 해제 후 거짓 돌파가 난다). 🔴 청산·손절 경로는 구조적으로 차단 불가능하다. 운영 복구 = `POST /api/trading/restart`.
- **`kojiro_gap_observe.py`** — 고지로 갭 판정 shadow 관측 leaf(행위 변경 0). `observe_gap(ticker, verdict, *, arg_open, prev_close, current_price, params, depth=2)` 가 `[kojiro_gap_observe]` 1행(14필드, 마지막 `ws_collapse=blocked|allowed|-` = WS 시가였다면 붕괴 가드에 걸렸을지 반사실)에 실제 판정(`arg_open`)과 WS 캐시 반사실(`ws_open`)을 나란히 남긴다. 호출자는 `_swing_buy_poll_loop`(KIS REST `stck_oprc`) **뿐**이다 — kojiro 는 `risk.on_tick` 에서 매수 평가를 하지 않는다(`risk._TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})`). `caller` 는 `sys._getframe(depth)` 로 식별하고(미지 호출자는 원문 그대로), cap = `KstDailyEmitCap[(ticker, caller, verdict)]`, never-raise. `ws_open` 부재 시 `-` 가 정상이다.
- **`kojiro_band_observe.py` — `observe_macd`(cycle340, 대순환 MACD shadow)** — 원전 `docs/trading_base/이동평균선과MACD.md` §7 의 MACD(상·중·하) 상태를 `[kojiro_macd_observe] ticker= role= stage= gc3= bars_since_gc3= m1..m3= s1..s3= hist3= m{1,2,3}_up= all_macd_up= rule6= rule5= rule4=` 로 남긴다(관측 전용, 행위 0). 행 계약 = 12원소 튜플. 근거 실측 = `_workspace/domain_consult/cycle340_kojiro_macd.md`.
  - 🔴 **WARNING 이다** — INFO 는 21:30 `top_patterns` 에 안 오르고 retention 2일이라 표본이 쌓이기 전에 지워진다. 값은 `_num`(소수 2자리 고정·비수치·NaN·inf 는 `-`)으로 **파싱 계약**을 고정한다(`_fmt` 는 `2.5`/`2.50` 을 섞고 비수치를 흘린다). cap 키는 `(ticker, "macd:"+role)` 로 band 관측과 **슬롯을 다투지 않는다**.
  - 배선(cycle344) — `kojiro.prepare()` 가 `_macd_observe_row(enriched, stage)` 수집 2곳(보유 stamp 직후 · `rank_raw` 확정 직후) + `observe_band` 다음 emit 1곳으로 부른다(`enriched` 에 재료가 다 있어 **추가 I/O 0**). 🔴 **`gc3` 는 상태가 아니라 교차 사건**(직전 봉 `macd3 ≤ sig3` ∧ 이번 봉 `>`)이다 — 상태(`m3 > s3`)로 바꾸면 교차 다음 날부터 며칠씩 참이라 규칙 발화가 부풀어 표본이 실측과 갈린다. 🔴 **emit 은 `observe_band` 와 별도 `try` + 전용 흡수기 `absorb_macd_call_failure`** — `absorb_band_call_failure` 재사용은 MACD 고장을 밴드 고장으로 기록하는 오귀인이다(`test_g344_12` 봉인). `_macd_observe_row` 는 `prepare` 의 ticker 루프와 같은 try 스코프라 **never-raise**(컬럼 부재·비수치는 폴백 튜플). 회귀 = `tests/unit/engine/strategies/test_cycle344_kojiro_macd_wiring.py`.
  - **role 3종(cycle348)** — `held`(보유 stamp 직후) · `candidate`(strict entry 최종 후보, 두 role 은 `_macd_observe_row` 만 호출) · `stage6_gc`(step6 직후 = ATR 밴드 통과 ∧ 스테이지 판별 가능한 **모든** 종목 중 국면6 ∧ 마지막 봉 gc3 — B6 규칙의 실매매 유니버스 표본. strict entry(국면1)를 못 넘는 국면6 종목은 다른 role 로 안 남는다).
  - `stage6_gc` 수집 = `KojiroStrategy._stage6_gc_observe_row(enriched, stage, bar_date, prev_close, atr_val)`(step6 직후·보유 stamp 앞, `stage != 6` 이면 `_macd_observe_row` 를 **부르지 않는다**). 반환 = 12원소 + `(bar_date, prev_close, atr_val)` = **15원소**, gc3 교차가 아니면 `None`. emit = `observe_macd_stage6(macd_s6_raw)` — `observe_macd` 호출 **다음**·`_scanned_tickers` 대입 **앞**에 **별도 try**(흡수기는 같은 `absorb_macd_call_failure`, M8 — 한 try 에 합치면 한쪽 실패가 다른 쪽 표본까지 삼킨다). 행 서식은 `held`/`candidate` 와 같은 필드·순서 + 끝에 `bar=<YYYYMMDD> close=<int> atr=<소수2자리>`(`close` 는 `_int_or_dash`). cap 키 = `(ticker, "macd:stage6_gc")`.
  - **일일 상한 `STAGE6_GC_DAILY_LIMIT`(60)** — 새 가변 모듈 전역 없이 `_cap.count_matching(...)` 으로 그날 이미 emit 된 `(ticker,"macd:stage6_gc")` 키 수를 세어 판정한다. 초과분은 배치 끝 요약 1행(`[kojiro_macd_observe] role=stage6_gc cap_reached=1 limit=60 suppressed=N`, 별도 cap 키 `("-","macd:stage6_gc:summary")` 로 하루 1회). 수집 헬퍼·leaf 어느 쪽이 실패해도 held stamp·step7 탈락·후보 등록 등 매매 산출은 **완전 동일**(자기 try 이중 방어).
  - `stage6_gc` 표본 판독 넷 — (a) **운영 100봉 창(`KOJIRO_FETCH_DAYS`)으로 계산한 B6** 라 창 앞머리 시드 차이로 전체 이력 계산(cycle346 스크립트)과 사건 일부가 갈린다 — 두 표본을 한 표로 합치지 않는다 (b) 보유 중인 국면6 ∧ gc3 종목은 `role=held` 와 `role=stage6_gc` 두 줄에 기록된다 (c) `[kojiro_macd_observe]` 줄 수·`rule6=1` 합계는 반드시 `role=` 로 나눠 집계한다(`stage6_gc` 행은 3 MACD 가 모두 우상향이면 곧 `rule6=1` 이다) (d) 상한 60 은 안전 여유이지 예상치가 아니다(예상 = `_workspace/domain_consult/cycle348_stage6_volume_probe.py`).
  - 회귀 = `tests/unit/engine/strategies/test_cycle348_kojiro_macd_stage6.py` — 매매 무변경은 차분이 아니라 확장 전 코드(`2087ad3`)로 도출한 **골든**(stats 전체·키 집합·스캔 순서·후보 키·funnel 9단계)과의 완전 일치로 잰다(차분 비교는 수집 `try` 바깥 돌연변이를 양쪽이 공유해 못 잡는다).
- **`kojiro_band_observe.py`** — 고지로 후보 순위 성분①② shadow 관측 leaf. `observe_band(band_raw, ranked_final, held_only, scores=None)` 이 `[kojiro_band_observe]` 1행/(ticker,role)/일로 `bar`(D-1 완성봉 날짜)·`exp1`(단일봉 분모)/`exp5`(직전 5봉 평균 분모)·`slope_raw`/`slope_pct`·`score` 등 12원소 + 파생 3필드(`atr_pct`/`bw_close_pct`/`bw_atr`)를 나란히 남긴다. never-raise(`_band_observe_row`·`observe_band`·`absorb_band_call_failure` 전부 단일 `try/except Exception`, 실패는 `observer_trace.trace_observer_failure` 흔적) + read-only + cap = `KstDailyEmitCap[(ticker, role)]`. 소비처 = `KojiroStrategy.prepare()` 점수 확정 직후 1블록이고, 실패해도 매수 후보 처리(`final_prepared`/`_scanned_tickers`)에 영향이 없다.
- **`open_price_observe.py`** — 시가(`[7] STCK_OPRC`) 스코프 shadow 관측 leaf(행위 변경 0). 09:05:30 에 VB·LTV `main` 보드의 `used_open`(그날 목표가를 만든 값)과 KRX REST `stck_oprc` 를 `[open_source_compare]` 로 나란히 남겨 익일 `stock_master_daily` 까지 3자 대조를 가능하게 한다. throttle 5건/초, 1회/(ticker,strategy)/일, read-only(`_targets`/`_open_confirmed` 무변경). 기준가를 실제로 세우는 본체는 `open_price_rest.py` 다.

### 출처 절: 모듈 맵 › 행위 leaf

- **`status_exit_watch.py`** — 관리종목(51)·단기과열(59) **보유 청산 + 당일 매수 차단** leaf(cycle369). 보유 종목을 REST `FHKST01010100` 으로 읽고, KRX 정규장 창 **09:00:30~15:28** 안에서 전용 플래그가 `Y` 면 `order_engine.execute_sell(t, Signal.STATUS_EXIT, sid)` 를 시장가로 낸다. 같은 조회 결과로 그날 그 종목의 신규 매수 신호를 공통 게이트 `StrategyBase._account_soft_gate_blocked` 첫 문장에서 막는다. 모듈 최상위 import 는 표준 라이브러리뿐이다(`condition`·`strategy_base` 가 이 모듈을 지연 import 하므로 최상위에서 `src.*` 를 끌어오면 순환이다). 8영역 파일은 고치지 않는다. 8영역 객체에서 부르거나 읽는 것 = `order_engine.execute_sell`(호출) · `order_engine._selling`(읽기) · `registry.all()`·`registry.enabled()`·`registry.is_ticker_blocked_for_buy`(호출) · `scanner.ticker_prev_close`·`scanner.ticker_prices`(읽기). 계약 상세 = 하단 「종목상태 청산·당일 매수 차단」 절.
- **`open_price_rest.py`** — VB·LTV `main` 목표가 기준가를 KRX REST 로 확정한다. 좁은 목 `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")` — `reject_untrusted_main_basis(params, board, source, …)` 가 `board=="main"` ∧ `source ∉ ("rest",)` ∧ `resolve_mode(params)=="enforce"`(전략별 `DEFAULT_PARAMS["open_price_scope_mode"]`, 기본 `enforce`, `"off"` 만 롤백)일 때 조용히 거부한다. 🔴 `source` 기본값이 불신 `"ws"` 라 WS 3 호출부(스케줄러 1차 폴링·전략 인라인 확정)는 한 글자도 바뀌지 않는다(`_STRATEGY_PINS` 6개 불변).
  - 일정(`round_schedule()` 순수 함수) = 09:00:35 R1 → 30초 간격 **fast 19라운드**(마지막 09:09:35) → 300초 간격 slow 라운드 15:20 까지(slow 라운드 대상은 `_pending_main_tickers` 뿐이다). `main_rest_basis_task_loop(sched)` 가 `run_main_rest_basis_round(sched, round_no=, total_rounds=, kind=)` 를 호출한다. 대상 `select_strategies(registry)` = `main ∈ tradable_boards ∧ mode=="enforce"`(`config.enabled` 미고려 — 비활성 전략으로도 REST 확보·게이트·부하를 검증한다). 종목 간 `sleep(0.05)`, 라운드 벽시계 상한 45초(`truncated=1`). 확정 시 `on_open_price_confirmed(..., source="rest")` **와** `open_price_observe.mark_confirmed_via_rest` 를 둘 다 부른다.
  - `owns_board(strategy, board, *, now=None)` = `board=="main" ∧ mode=="enforce" ∧ now < 09:05:00`(예외 fail-open False) — 그 창 동안 `scheduler._confirm_breakout_open_prices` 는 그 전략을 대상에서 빼고, 09:05:00 이후는 스케줄러의 2차 REST 폴백이 `source="rest"` 로 백스톱한다.
  - 마커 4종(`[main_rest_basis_config|round|confirmed|unresolved]`, `KstDailyEmitCap` + `observer_trace`) — `config` 1회/(전략,모드,emitter)/일 · `round` 전략별(fast 항상, slow 는 pending>0 일 때만) · `confirmed` 1회/(전략,종목)/일로 REST 조회 **직전** shadow 병기(`ws_open`/`ws_src`/`delta_bp`/`target_rest`/`target_ws` = 오염 규모의 정본) · `unresolved` 1회/(전략,종목)/일로 마지막 fast 라운드 직후(= 커버리지 손실의 정본). `scanner.ticker_prices` 는 **읽기 전용**(8영역 무접촉). 자문 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.
- **`quote_token_refresh.py`** — 보조 시세 계정 접근토큰을 매일 `TIME_QUOTE_TOKEN_REFRESH`(**20:45 KST**)에 계정별 `TokenManager.revoke()` → `issue()` 순차로 재발급하는 leaf. `refresh_quote_tokens_once()` 가 `kis_quote_accounts.list_accounts(active_only=True)` 를 순회하고, `task_loop()` 는 `run_periodic_task_loop(immediate_first_run=False)` 에 위임한다(부팅 시각이 앵커가 되면 설계가 무너진다). 고치는 것 = `TokenManager._is_valid()` 의 10분 선제 갱신 마진이 종일 REST 를 쓰는 보조 계정의 재발급 시각을 매일 10분씩 앞당기는 **단조 드리프트**다. 대상은 보조 계정뿐이고 주계정(`label=None`)은 무접촉이다.
  - 🔴 `revoke()` 가 선행해야 한다 — KIS `/oauth2/tokenP` 는 유효 토큰이 살아 있으면 **같은 토큰·같은 만료**를 돌려주므로 폐기 없이는 만료 앵커가 이동하지 않는다. `revoke()` 실패는 WARNING 1행 뒤 `issue()` 를 계속 시도하고(무토큰 방치 금지), `failed` 카운터는 issue 실패 전용이며, `revoke()` 는 전역 issue lock 과 61초 gap 을 소모도 우회도 하지 않는다. **WS 무영향** — WS 는 별도 엔드포인트 `/oauth2/Approval` 의 `approval_key` 로 접속·구독하며 `issue()` 는 그것을 건드리지 않는다.
  - **시각 불변식 3** = (a) T 와 T−10분이 모두 KRX 장중(09:00~15:30) 밖 — 필요조건이지 충분조건이 아니다 (b) 7계정 × 61s ≈ 7분의 직렬화 창이 REST 를 많이 쓰는 예정 작업과 겹치지 않을 것 (c) **T 는 스케줄러 task 루프의 생존 창 안**일 것 — `run_daily` 의 `finally` 가 정산(`TIME_SETTLEMENT`) 뒤 백그라운드 task 를 전부 cancel 하므로 그 뒤 시각은 매일 0회 발화한다(로그에는 부팅 시 `scheduled at=` 한 줄만 남아 배선이 살아 있는 것처럼 보인다). 🔴 **진짜 요건은 "장중 밖" 이 아니라 "보조 풀 REST 가 없는 창"** 이다 — T−10분 문턱이 REST 창 한복판이면 자연 재발급이 항상 강제보다 먼저 난다. 20:45 는 20:00 자문·20:00:05 유니버스·20:05 metrics·20:30 일봉(≈20:32 종료)·21:30 정산을 전부 `[T−10, T+8]` 창 밖에 둔다(가드 `test_c9`·`test_c10` 이 전수 스캔으로 잠근다).
  - 마커 `[quote_token_refresh]` 3종 = `scheduled at=`(배선 카나리아) · `label=… issued expired=… revoked=True|False`(계정별, `revoked=False` = 그 계정은 이번 회차에 앵커 미이동) · `accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d`(회차 요약 — `elapsed_s` 는 체인 총 소요 ≈420s = 7계정 × 61s, `window_issues_total` 은 체인 시작 **−15분**부터 종료까지 그 회차 매니저들의 발급 횟수). 성공 서명 = 장중 자연 재발급 0건 · `window_issues_total=7`. `scheduler.py` 배선은 2줄(import + `create_task`) + cancel 목록 3곳이고 본체가 leaf 인 이유는 라인 상한이다.
- **`daily_bar_finalize.py`** — 부팅 prepare 직전에 전일 「잠정 봉」을 KIS 정규장 확정값으로 덮는 leaf(cycle386). 잠정 봉 = 20:30 적재가 쓴, 종가·고저에 애프터마켓 값이 섞인 봉이다. 공개 API = `spawn(*, phase) -> asyncio.Task` · `wait_for_boot(task, *, budget_secs)` · `finalize_once(*, now_kst=None, phase)` + 상수 8개. 최상위 import 는 `src.db.{positions,stock_master_daily,system_config}` · `src.db._kst` 뿐이고, `src.api.condition` 은 함수 안에서 지연 import 한다. 🔴 8영역·`scheduler`·`scanner`·`boot_manager`·strategies import 0(AST G5 b). 계약 상세 = 하단 「저녁 데이터 적재」 절의 「전일 잠정 봉 확정」.
- **`llm_buy_gate.py`** — **매수 주문 접수 시점** LLM 평가 shadow leaf(매매 행위 변경 0). 진입점 `observe_order(*, strategy_id, ticker, order_no, order_kst, order_price_won, ordered_qty, order_division, order_path, exchange, current_price_won, budget_total_won, budget_remaining_after_won, open_positions_n, params_snapshot, buy_signals_tail)` — **키워드 전용 · 동기 · never-raise · `await`/DB/HTTP 0 · 반환 항상 `None`**. 전략 파일에는 훅이 없다. 소비처는 `order_engine.execute_buy` 의 매수 `place_order` 성공 직후 매핑 등록 블록 끝 **2곳**(주 경로 · 시장가 거부 지정가 5호가 폴백)이며 `_insert_pending_or_absorb_race` **앞**이다. 8영역 중 `order_engine.py` 만 접촉하고 A-ATOMIC 구간은 byte 동일. 킬스위치 `llm_gate_mode=off`(PUT 즉시). 영속 = `src/db/llm_buy_evaluations.py` + migration 043, 조회 = `src/routes/llm_evaluations.py`.
  - **순서** = `mode(off|shadow, 그 외 off)` → `[llm_gate_config]` 카나리아(off-return 앞) → off 즉시 return → `order_no` 유효성(빈 값이면 `[llm_eval_persist] reason=empty_order_no` 1행 후 return) → 래치 peek(키 = **주문번호**/일 — 같은 종목을 하루 두 번 사면 두 번 평가한다) → 일일 cap peek(`[llm_gate_daily_cap]` WARNING 1회/전략/일 + `[llm_eval_persist] reason=cap_exceeded` 주문별 1행) → 값 복사 payload → 래치 mark + cap 증가 → `asyncio.create_task(_evaluate)` 정확 1회.
  - `_evaluate` 는 `_evaluate_core` 의 outcome 을 받아 **단 1곳**에서 `_persist_evaluation` 한다(성공·실패 **모두** `llm_buy_evaluations` 1행 — 실패도 `input_payload` 를 담고 `score=NULL`). `_evaluate_core` 는 세마포어 2 안에서 `db.stock_master_daily.get_recent_daily_normalized`(캐시 `(ticker, KST date)` 상한 400, 당일 봉 폐기, 60봉 fetch → 프롬프트에는 30봉) → `llm_features.compute_technicals`/`build_messages` → `AsyncOpenAI.chat.completions.create`(`settings.openai_buy_gate_model`, `response_format=json_object`, `asyncio.wait_for`) → 출력 검증(클램프 금지, `int(inf)` OverflowError 흡수) 순으로 돈다. `_MAX_COMPLETION_TOKENS = 2000` — 추론 모델은 추론 토큰이 이 한도를 함께 소비하고 과금은 실사용량이라 **비용은 오르지 않는다**. 한도 소진은 파싱이 실패한 경우에만 `reason=truncated` 로 분류한다(완전한 JSON 이면 점수를 살린다). `asyncio.CancelledError` 는 re-raise.
  - 마커 5종 = `[llm_gate_config]` · `[llm_buy_score]`(`order_no=`·`order_kst=`·`order_price=`·`post_order_drift_bp=` — **+ 는 주문 뒤 상승 = 이득**) · `[llm_buy_score_failed] reason=` 10종(timeout / api_error / parse_error / schema_error / no_bars / no_key / cap_exceeded / disabled_model / payload_error / truncated, `finish=` 는 OpenAI `finish_reason` 원문이고 LLM 호출 전 실패는 `-`) · `[llm_gate_daily_cap]` · `[llm_eval_persist] order_no= result=ok|error [reason=]`(DB 무음을 깨는 유일 채널). 🔴 `empty_order_no` 와 `cap_exceeded` 는 **persist 어휘**이지 평가 실패 어휘가 아니다 — 섞으면 일일 리포트의 실패 분류가 오염된다.
  - 보드는 세션 트래커가 아니라 **시계**(`_board_by_clock`)로 푼다(leaf 는 8영역을 참조하지 않고, 트래커의 활성 보드는 30초 stale 이라 09:00:0x 에 `pre_nxt` 로 굳는다). 계좌번호는 leaf 가 `settings` 에서 읽는다. 회고 층화 2열 = `_prompt_version()`(SYSTEM 프롬프트 + user 프리앰블 + `llm_features` 스냅샷 키의 sha256 앞 12자) / `_feature_version()`(`compute_technicals` 출력 키 집합), 계산 실패는 `""` fail-open. `src.*` import 는 허용 목록(`daily_emit_cap`·`observer_trace`·`llm_features`·`config`·`db.stock_master_daily`)만 **모듈 최상단**에 두고 `scanner`·`tick_volume`·`log_analysis_engine`·`db.llm_buy_evaluations` 는 함수 내 **지연 import** 다(순환 차단).
- **`market_unit.py`** — 시장 유닛(단계형) 판정 leaf(cycle382). KODEX 200(`SOURCE_TICKER="069500"`) 일봉 종가로 그 거래일의 장세를 4단계로 나눈다. `MULTIPLIERS` = `up_rising` 1.0 · `up_falling` 0.75 · `down_rising` 0.5 · `down_falling` 0.0.
  - 창 `w` = `bas_dd < as_of_date` 인 행을 오름차순으로 세운 마지막 `MIN_ROWS`(80)개다. `above = w[-1] × 60 > sum(w[20:80])` · `rising = sum(w[20:80]) > sum(w[0:60])`(60일선이 20봉 전 60일선보다 높다). 평균 대신 합으로 비교해 부동소수 동률 흔들림을 없앴고, 동률은 약한 쪽(엄격 부등호)이다. 상수(`MA_WINDOW=60`·`SLOPE_LOOKBACK=20`·배수 4개)는 이 파일 한 곳에만 있고 파라미터로 열지 않는다(AST A02).
  - 공개 함수 = 순수 `classify(closes)` · `normalize_mode(raw)`(부재 = `("off", True)`, 오타·비문자열 = `("off", False)`) + never-raise 로더 `async compute_snapshot(as_of_date, *, preview) -> Snapshot`. 로더는 `stock_master_daily.get_recent_daily("069500", FETCH_ROWS=120)` 와 `trading_calendar.previous_trading_day(as_of_date)` 를 **함수 안 지연 import** 로 부른다(테스트 monkeypatch seam · DB 전용 · KIS 폴백 없음).
  - 판정 순서 = 행 수(`rows_short`) → 신선도(`stale_head` = `head < previous_trading_day(as_of_date)`, 달력을 모르면 `(as_of_date − head).days > STALE_FALLBACK_MAX_CALENDAR_DAYS`(10)) → 종가 품질(`bad_close` = 창 안 결측·비수치·비유한·0 이하) → 그 밖 `exception`. 실패는 전부 `ok=False, state="unavailable", m=1.0` 이다 — 🔴 실패를 m=0(fail-closed)으로 바꾸지 않는다.
  - 최상위 import 는 표준 라이브러리뿐이고 8영역·`scheduler`·`boot_manager`·`market_regime` 을 import 하지 않는다(AST A01). 모든 시장 유닛 마커는 이 모듈의 `logger`(`"src.engine.market_unit"`) 하나로 나가고, 부르는 쪽과 cap 판정은 `StrategyBase` 헬퍼다(하단 `strategy_base.py` 절). ⚠️ `069500` 은 지수 편입이 아니라 시총·거래대금 자격(`scanner._is_daily_load_universe`)으로 일봉 적재 대상에 든다 — 그 자격을 잃으면 매일 `stale_head` 로 m=1 이 된다.

### 출처 절: 모듈 맵 › 자문 · 리포트 · 레짐

- **`recommendation_engine.py`** — 20:00 AI 자문. `auto_apply` 는 살아 있는 전략 객체를 직접 변이하는 **파라미터 즉시 반영의 유일한 경로**다. 상세 = 하단 전용 절.
- **`recommendation_metrics.py`** — `trade_history` + `daily_performance` 를 받아 LLM 프롬프트용 **결정적 통계 dict** 를 만드는 순수 계산 모듈.
- **`backtest_orchestration.py`** — 백테스트 오케스트레이션 5함수(`_get_backtest_engine`/`_spawn_backtest_poll_task`/`_enqueue_backtest_jobs`/`_backtest_poll_loop`/`_emit_pending_summaries`) + `_backtest_poll_loop_running`/`_BACKTEST_POLL_*`. leaf(core 미호출, 순환 0)이고 `recommendation_engine` 이 module-level 로 재export 하므로 scheduler import 경로와 테스트 patch 경로가 **동일 객체**다. 🔴 `logger = logging.getLogger("src.engine.recommendation_engine")` 명시.
- **`log_metrics_collector.py`** — 일일 리포트(21:30)의 **수집·집계 계층**. `collect_daily_log_metrics`(반환 dict 의 키 집합·순서 = OpenAI 프롬프트 = `daily_log_reports.metrics` JSONB = 20:20 루틴 번들) + `_fetch_logs_in_range` · `_aggregate_*` · `_build_portfolio_risk_snapshot` · funnel 수집 + 정규식 · `DAILY_LOG_FETCH_LIMIT` · `HIGH_SEVERITY_FETCH_CAP` · `KST`. `log_analysis_engine.py` 는 LLM 호출·검증·저장만 갖고 위 심볼을 `__all__` 로 재export 한다 — 🔴 `routes/log_reports.py` 의 import 문 무접촉이 계약이다(L2 텍스트 가드). monkeypatch 는 **collector 경로**로 한다.
  - 🔴 **새 키는 항상 끝에 더한다** — 키 순서가 OpenAI 프롬프트·JSONB·번들의 계약이다(핀 = `test_cycle249_collect_metrics.py::EXPECTED_METRIC_KEYS` · `test_cycle259_log_metrics_collector.py::test_l3_metric_key_order_is_byte_identical`·`test_l3b_reexported_entrypoint_returns_same_shape`). 관측 전용 끝 세 키 = 10번째 `vcp_breakout_events` · 11번째 `pyramid_shadow` · 12번째(맨 끝) `report_accuracy`.
  - **`"vcp_breakout_events"`(cycle349)** — 호출 시점에 `trading_scheduler.registry.get("vcp_breakout")` 의 `breakout_event_summary(target_date)` 를 읽는다(메모리 읽기 = 추가 I/O 0). 전략 부재·조회 실패·요약 실패는 그 키만 `None` 이고 나머지 metrics 는 무영향이다(never-raise). 값의 `final` — **1** = 그날 VCP 매수 창(`params["entry_end"]`, 못 읽으면 14:30)이 닫힌 뒤의 값이라 더 바뀌지 않는다(지난 날짜 포함), **0** = 창이 열려 있는 중간값. WARNING `[vcp_breakout_events] date= status=ok crossed=<C>/<N> observed= unobserved= run_at= window= partial= crossed_tickers=` 는 `target_date == 오늘(KST)` **이고 창이 닫힌 뒤에만**, 모듈 전역 `KstDailyEmitCap` 로 **하루 1회** 찍는다(20:05 스냅샷·20:20 번들·21:30 완전판이 모두 부르므로 평소에는 20:05 가 찍는다). 창이 열린 동안의 호출(낮의 번들 GET·`POST /api/log-reports/run`)과 과거 날짜 호출은 키만 채우고 cap 을 소비하지 않는다 — 소비하면 그 중간값이 그날의 결과 줄이 된다. `ok` 가 아니면 `status=` 까지만 찍는다. 수집 실패 흔적은 DEBUG `[vcp_breakout_events_error]` 다(데이터 마커와 접두를 가른다). 값의 의미·한계 = `strategies/CLAUDE.md` 각주 ⑥.
  - **`"pyramid_shadow"`(cycle351)** — `kojiro`·`donchian_swing` 의 레지스트리 파라미터 사본 + 예산 + 보유 ticker 집합만 읽어(읽기만, 등록·상태 무변경) `src.engine.pyramid_shadow.build_pyramid_shadow` 에 넘긴다. 30초 상한(`_PYRAMID_SHADOW_TIMEOUT_SECS`) + 예외는 이 키만 `None`(never-raise) — 실패·타임아웃은 DEBUG(매 실패) + WARNING `[pyramid_shadow_error]` 1회/일(`_pyramid_shadow_failure_cap`, `observer_trace` 규약)로 남는다. 상세 = `pyramid_shadow.py` 항목.
  - **`"report_accuracy"`(cycle366)** — `{trading_day, market_closed, by_ticker_pnl_total_tickers, by_ticker_pnl_truncated, after_market_blind_secs_total, pre_market_blind_secs_total}`. `trading_day`(`bool | None`)는 `trading_calendar.is_open_day(target_date)` 를 그대로 재사용한다(지연 import, never-raise — 조회 예외는 `None`="모름"). `market_closed = (trading_day is False)` — `None`(모름)은 휴장으로 단정하지 않는다. 20:20 클라우드 루틴·21:30 LLM(`log_analysis_engine.SYSTEM_PROMPT` 에 해석 규칙 명시)이 휴장일의 0건을 결함으로 오독하지 않게 하는 것이 목적이다. `by_ticker_pnl_total_tickers`/`by_ticker_pnl_truncated`(`_by_ticker_pnl_truncation`)는 `trades.by_ticker_pnl` 상위 5개 절단 여부를 별도로 관측한다(그 서브딕트 자체는 cycle351 골든 byte 계약 대상이라 손대지 않는다). 확장 blind 2필드(`_aggregate_extended_blind`)는 `[tick_blind_boot]` 로그의 애프터마켓·NXT 프리마켓 겹침 초를 `tick_blind.market_blind_secs_total`(09:00~15:30 KRX 메인, cycle234)과 별도로 합산한다(출처 = `uptime_monitor` 항목). 매매 행위 0. 회귀 = `tests/unit/engine/test_cycle366_report_accuracy.py`.
- **`pyramid_shadow.py`** — 피라미딩(사다리 증량) 가상 기록(셰도) leaf. **매매 행위 0 · 읽기 전용**(DB SELECT 만, KIS 호출 0). 순수 코어 `overlay_ladder`(+ `no_add_flags` · `LadderConfig` · `LADDER_C`)가 "실제 청산(앵커) 위에 사다리만 덧씌우는" 모형을 계산하고, async 어댑터 `build_pyramid_shadow`가 `kojiro`·`donchian_swing` 의 그날 대상 포지션(보유 + 최근 7 달력일 안의 미확정 청산 재확인 포함, §2-1 확장)에 그 모형을 적용해 `metrics["pyramid_shadow"]` 를 만든다. 손절선은 `_stop_floor` 래칫(조이기만 함, 세트선·평단 backstop·평단 본전 승격 + kojiro 는 live ATR 「가중평단 − stop_atr×ATR」항)으로 계산한다. 청산 확정(`final=1`, 오늘) 시 `[pyramid_shadow_close]` WARNING 1회/포지션/일(`system_logs` 30일 보존 — 21:30 `top_patterns` 에는 오르지 않는다, 로그 읽기가 이 마커보다 먼저다). 이 모듈을 import 하는 프로덕션 모듈은 `log_metrics_collector.py` 하나뿐이다(AST 가드). 회귀 = `tests/unit/engine/test_cycle351_pyramid_shadow_{core,collect}.py` + `tests/unit/ast/test_cycle351_pyramid_shadow_scope.py`.
- **`log_analysis_engine.py`** — 21:30 일일 로그 분석(LLM 호출·검증·저장). 상세 = 하단 전용 절.
- **`daily_metrics_snapshot.py`** — 20:05 metrics **1차 스냅샷 leaf**. `run_daily_metrics_snapshot(target_date: date | None = None) -> dict | None` 이 `TIME_METRICS_SNAPSHOT` 에 불려 `daily_log_reports` 의 그날 행을 upsert 한다. 목적 = 프로세스 메모리 전용인 `api_metrics`·`strategy_funnel` 의 유실 노출을 21:30 정산까지 기다리지 않고 **5분**(20:00 매매 종료 → 20:05)으로 줄이는 것. 🔴 **OpenAI 를 부르지 않는다**(비용·지연 0, `model`·토큰 5컬럼 전부 NULL). 🔴 **`reset_request_metrics()` 를 부르지 않는다** — 부르면 21:30 완전판이 저녁 90분치만 보게 된다. never-raise. 마커 `[daily_metrics_snapshot] target_date= pass=1 saved=1|0 elapsed_ms=` 실행당 1행 — **성공 서명은 「마커 1행」이 아니라 `saved=1`** 이다(`saved=0` 은 WARNING = 저장이 조용히 비었다). 21:30 완전판과 같은 행을 쓰므로 `insert_log_report` 는 `ON CONFLICT (target_date) DO UPDATE` 이고 SET 절은 base 9컬럼만 건드린다(`ext_*` 6컬럼·`created_at` 무접촉).
- **`market_regime.py`** — 매크로 레짐 **관찰** + `cash_usage_ratio` 자동 조정. 출처는 우리 `macro` 컨테이너다(cycle315). 🔴 매수 가드는 없다 — `get_buy_block_state` 는 대시보드·자문 payload 표시 전용이다. 상세 = 하단 전용 절.

### 출처 절: `scheduler._wait_until` 계약

- `target_dt` 는 **호출 시점 1회 확정**한다(while 루프 진입 전). 루프 안에서 재계산하지 않는다 — 재-advance 를 구조적으로 막는다.
- default(`advance_if_passed=False`): target 이 이미 지났으면 즉시 return, 아니면 도달 시 return(`run_daily` phase 전환 9곳).
- advance(`=True`, `task_loop_helper` 전용): target 이 이미 지났으면 `+= timedelta(days=1)` 를 **1회** 확정한 뒤 그 target 도달 시 return(발화).
- `asyncio.sleep(min(잔여초, 60))` + `while self._running` 체크(stop 시 신속 탈출, 헬퍼의 `if not scheduler._running: break` 가 흡수).
- 가드 `tests/unit/engine/test_cycle188_wait_until_advance_return.py` — 가상 시계 단조 전진 mock(fake sleep 이 가상 시각을 전진시킨다). 🔴 **freezegun 금지** — 동결된 monotonic 이 hang 을 만든다.

### 출처 절: 정기 task 루프 (`task_loop_helper.run_periodic_task_loop`)

- graceful(`CancelledError` 와 `Exception` 분리) · `start()` 직후 즉시 1회(`immediate_first_run`) · task 별 stagger `initial_delay_secs`(full_universe=0 / daily=240 / basics=480 / evening_funnel=600 / master=720 / financial=900초, purge 는 기본값 0 — 값의 정본 = `data_load_tasks.py`). 🔴 대기만 하다 `stop()` 에 잘리는 lifecycle race 를 막는 표준 패턴이라 **신규 일일 task 도 이 헬퍼를 경유한다**(직접 while 루프 신설 금지).
- **부팅 즉시 실행 게이트는 두 갈래다.** 둘 다 immediate 블록(stagger sleep 뒤 · once 앞)에서만 판정하고 `system_config.get_task_last_success(task_label)` 마커를 읽는다. 두 kw 를 함께 주면 함수 진입 즉시 `ValueError` 다(프로그래밍 오류).
  - **시간 게이트** `immediate_skip_if_fresh_hours` — 마커가 `0 <= elapsed < hours*3600`(미래 마커 음수 방어)이면 immediate `once()` 를 skip 하고 `[<label>] immediate run skip — fresh last_success=<iso>` INFO 1행을 남긴다. 대상 = master(모듈 상수 `IMMEDIATE_FRESH_SKIP_HOURS = 20.0` — 저녁 성공 → 익일 아침 boot 이 그 안) · financial(`168` = 주1회). 이 게이트는 주말·연휴를 낡음으로 세므로 master 는 월요일·연휴 뒤 아침에 실행된다.
  - **영업일 슬롯 게이트** `immediate_skip_if_fresh_since_trading_slot=True` — 슬롯 = 그 task 의 `wait_time`(= `scheduler.TIME_*` 정본, 새 시각 리터럴 없음)이다. 마커가 「가장 최근에 지나간 영업일 슬롯」(`trading_calendar.latest_passed_trading_slot(now, wait_time)`) 이후면 skip 한다. 대상 = basics(16:10) · daily_load(20:30) · full_universe(20:00:05). 주말·연휴를 낡음으로 세지 않으므로 평상시 월요일·연휴 뒤 아침에는 셋 다 돌지 않는다.
- **슬롯 판정 순서**(`_evaluate_slot_gate`, never-raise — 각 단계의 예외는 「실행」 쪽이다):
  1. `immediate_force_run_check` 가 True → RUN `<immediate_force_run_reason>`(기본 `below_floor`) / 예외 → RUN `force_check_error`(이 값은 `immediate_force_run_reason` 과 무관하게 항상 고정 — "판정 자체가 실패했다" 는 "판정이 임계를 넘었다" 와 다른 사실이다)
  2. 마커 조회 예외 → RUN `marker_error` — 🔴 **운영에서 도달 불가**한 방어 분기다. `system_config.get_task_last_success`(`_get_string_or_none`)가 broad `except Exception: return None` 이라 pg 예외를 삼켜 `None` 을 돌려주므로 pg 장애도 ③(마커 없음)으로 떨어진다. 그래서 full_universe(`skip_if_absent=True`)에서는 진짜 pg 장애가 부트스트랩(마커 영구 결측)과 구분되지 않는 SKIP 이 된다(둘 다 `reason=no_marker`, 실 함수 경로 = `tests/unit/engine/test_cycle363_immediate_slot_gate.py::test_H3b_*`)
  4. 마커 파싱 실패 → RUN `marker_unparseable`. **naive 마커(`utcoffset() is None`)도 여기다** — KST 로 가정하지 않는다(aware 시각과 비교하면 TypeError 가 task 루프를 죽인다)
  6. 슬롯이 `None`(휴장일 모름)이거나 leaf 가 tz-aware datetime 이 아닌 값을 돌려줌 → RUN `calendar_unknown`. 🔴 휴장일 조회 실패는 실행 쪽이다(사용자 지시)
- **관측** = 판정마다 `[immediate_gate] task=<label> decision=run|skip reason=<위 어휘> marker=<iso|None> slot=<iso|None>` INFO 1행. SKIP 이면 grep 연속성을 위해 `[<label>] immediate run skip — <reason> last_success=<iso|None>` 1행을 더 남긴다(`reason=fresh` 면 시간 게이트의 문자열과 같다). 슬롯 모드의 시각 seam 은 `task_loop_helper._now_kst()` 하나다(테스트가 이 이름을 패치한다).
- 마커는 두 게이트 모두 `once()` **성공 직후에만** 기록한다(immediate · while 양쪽). 기록 실패는 graceful 이고, 다음 부팅 immediate 실행 = 안전 방향이다.
- 🔴 **정기 while 루프 발화는 게이트와 무관하게 무조건 실행한다**(F-8 HIGH 가드).
- **full_universe 전용 장치 둘** — 🔴 `once_callable`(= `scanner._full_universe_load_once`)은 무접촉이고 게이트는 헬퍼·wrapper 쪽에 있다.
  - **행 수 하한** `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000`(`data_load_tasks.py`) — `stock_master.count_active() < 2000` 이면 마커가 fresh 여도 실행한다(`immediate_force_run_check`). `count_active` 는 예외 시 0 을 돌려주므로 DB 장애 = 실행(fail-safe)이다. 2000 = 운영 3,583행보다 한참 아래, 2026-08-08 degrade 사고 60행보다 한참 위. 유니버스 자가 치유를 이 하한이 맡는다.
  - **마커 없음 = SKIP**(`immediate_skip_if_marker_absent=True`, 부트스트랩) — 마커 없는 부팅을 실행으로 두면 그 부팅이 직전 영업일보다 오래된 KRX 값으로 전량을 덮는다. 행 수가 하한 이상이면 건너뛰고, 첫 마커는 20:00:05 정기 실행이 남긴다. daily·basics 는 마커 없음 = 실행이다.
- **basics 전용 강제 재실행(cycle363, 사용자 승인)** — `stock_master.count_missing_kis_provenance_key()`(`raw` 에 KIS CTPF1002R 키 `cptt_trad_tr_psbl_yn` 이 없는 행 수) `> STOCK_MASTER_BASICS_FORCE_RUN_MISSING_THRESHOLD`(=100, `data_load_tasks.py`)이면 마커가 fresh 여도 실행한다(`immediate_force_run_check=_stock_master_basics_kis_keys_missing_above_threshold`, `immediate_force_run_reason="kis_keys_missing"`). 판정이 full_universe(+0초) **뒤**(basics +480초)라 실제 손상(결측 행 수)을 보고 정한다 — full_universe 만 RUN 하는 월요일 아침에 KRX 적재의 하드코딩 False(`nxt_tradable`·`krx_halted`·`admin_item`)와 KIS 출처 키 부재가 16:10 정기 실행까지 남지 않게 한다. 🔴 `count_missing_kis_provenance_key()` 는 **예외를 삼키지 않는다** — `count_active()` 류의 "실패 시 0" 관례를 따르면 쿼리 실패가 "결측 0건"(SKIP 방향)으로 읽혀 사용자 결정("쿼리 실패는 RUN 쪽 fail-safe")과 반대로 움직인다. 예외는 그대로 전파해 위 ①의 `force_check_error` 가 흡수한다.
- 🔴 daily_load 가 게이트 대상인 이유 = 아침 immediate 가 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)을 먼저 써서 `max_bas_dd == today` 를 만들면 그날 정기 실행이 전 종목을 `skipped_fresh` 로 건너뛴다. 🔴 full_universe 를 무게이트로 두지 않는 이유 = 아침의 KRX 는 직전 영업일 자료를 아직 내놓지 않아 즉시 실행이 **그 전 영업일 값으로 전량을 덮는다** — 월요일이면 목요일 값이 금요일 값을 덮는다(경위 = history). 신규 상장 유입은 20:00:05 정기 실행이 맡는다.
- 미대상 = purge · evening_funnel(게이트 kw 전무). evening_funnel 의 즉시 1회(+600초)는 21:00 전에 돌아 레거시 재준비 분기를 탄다 — 그 분기와 게이트를 걸지 않는 이유는 「funnel 스냅샷 캡처」 절.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 시각과 순서

데이터 적재 5종만 여기 적는다 — 매매·세션 시각을 포함한 전체 일과표는 하단 `scheduler.py` 절의 `TIME_*` 표가 정본이다.
`TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` 인 이유 = KRX 애프터마켓 종료(20:00) 뒤라야 그날 거래량이 확정된 값이고, 16:1x~16:40 마스터 작업보다 뒤라야 유니버스 판정이 오늘치 raw 를 본다. 매수 진입과 무관한 데이터 계층이다.
🔴 **20:30 에 쓴 D 봉의 종가·고가·저가는 확정값이 아니다(잠정 봉).** KIS 일봉(FHKST03010100, 시장 `J`)은 D일 20:00 뒤에도 종가를 19:59 애프터마켓 마지막 체결가로, 고저를 애프터마켓까지 넣은 범위로 준다. 정규장 값(15:30 종가·정규장 고저)으로 바뀌는 것은 D일 23:12 뒤 ~ D+1일 05:28 전이다(cycle386 실측). 시가·거래량·거래대금은 잠정 봉과 확정 봉이 같다 — 거래량·거래대금은 확정 봉도 애프터마켓을 포함한다. 잠정 봉은 다음 거래일 아침 부팅이 prepare 직전에 확정한다(아래 「전일 잠정 봉 확정」 절).
- 🔴 **적재 시각을 뒤로 미는 것으로는 못 고친다** — KIS 확정은 23:12 뒤인데 스케줄러 task 는 21:30 정산 뒤 `run_daily` 의 `finally` 에서 전부 cancel 된다. `scanner.py` 의 `_DAILY_LOAD_TODAY_BAR_CUTOFF` 주석에 있는 두 문장 「일봉 OHLC 는 15:30 에 확정되지만」 · 「어긋나면 이 상수와 scheduler 의 일봉 적재 시각을 함께 뒤로 민다」는 사실이 아니다. `scanner.py` 가 8영역이라 이 문서가 정본이다.
- 21:00 저녁 미리보기는 이 잠정 D 봉을 읽는다(다른 길이 없다 — 확정은 23:12 뒤이고 루프는 21:30 에 끝난다). 그래서 미리보기 목록은 **잠정 종가 기준**이고 다음 날 부팅 목록이 정본이다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 유니버스 선정

- `is_protected` = 공통 헬퍼 `_collect_protected_tickers_for_scanner()` 가 돌려준 보유·익일청산 종목 중 **6자리 숫자 ticker 만**(진입 게이트 비대칭 규약과 동일 — 영숫자 코드·오염 문자열 제외. ETF 코드는 6자리 숫자라 여기서 빠지지 않는다). 헬퍼 예외는 **fail-open**(`protected_tickers = set()` 로 index/qualifier 만 진행).
- 🔴 근거 = purge(`_evaluate_universe_guard` 계열)는 보유·익일청산 종목을 절대 보호하는데 load 가 자격 미달 종목을 건너뛰면 "지우는 쪽은 보호, 채우는 쪽은 방치" 가 되어 그날 봉이 영구 결손된다(004690 삼천리 실사례).
- 페이징 루프가 끝난 뒤 `protected_tickers - set(all_tickers)` 차집합을 `all_tickers` 에 append 한다(어느 페이지에도 안 실린 보호 종목까지 커버).
- 보호 종목도 분할 backfill 대상이다 — 깊이 축은 이 게이트를 통과한 **적재 대상 전부**에 똑같이 적용된다(아래 절).
- 관측 `[daily_load_protected_forced] protected=%d forced_in_universe=%d forced_extra=%d tickers=%s` — **실행당 1행**(종목당 emit 금지). 페이징 루프 밖 · `summary["total"]` 대입 앞에서 무조건 emit 하므로 조기 return 경로에서도 1행이 남는다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 분할 backfill 분기 — 대상은 적재 대상 전부

- 분기 조건은 **깊이 하나**다: `existing_count`(= `stock_master_daily.count_by_ticker`) `< _DAILY_LOAD_VCP_BACKFILL_DAYS(=225)` → `condition.fetch_daily_candles_backfill(ticker, total_days=225)`(분할 fetch, 마지막 윈도우 클램프) / `>=225` → 증분 7일(재 backfill 금지). 지수 소속·자격·보호 어느 것도 깊이를 가르지 않는다(cycle302).
- 🔴 **`_DAILY_LOAD_VCP_BACKFILL_DAYS` 는 VCP 전용이 아니다.** 이름의 `VCP` 는 이 깊이를 처음 요구한 전략의 흔적이고, 값은 적재 대상(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) 전부의 목표 깊이다. 이름 정정은 `src/api/condition.py` 호출자 주석을 함께 옮겨야 해서 후속 과제다.
- 🔴 **225 인 이유** = `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)` 라 보유 **225 영업일에서 실효 장기선이 정확히 200** 이 된다(220 이면 195 에 그친다). 깊이를 가르면 안 되는 이유도 같다 — 보유 행수가 얕은 종목은 실효 장기선이 74~121 로 잡혀 VCP 의 중기↔장기 간격이 10 안팎이 되고 정배열 판정이 동전던지기가 된다(근거 실측 = history).
- 🔴 **target 과 retention 은 함께 움직인다** — retention `DAILY_RETENTION_DAYS=390`cal ≈ 261영업일이 225 위로 **36 영업일 마진**을 남긴다. target 이 보유 영업일을 넘으면 `existing_count` 가 영원히 target 에 못 닿아 매 load 전량 재backfill(churn)이 된다.
- 🔴 **비용은 1회성이다.** 깊이에 닿으면 증분(7일·1콜)으로 내려오고 retention 이 225 아래로 떨어뜨리지 않는다 — 수렴 상태의 매일 밤 호출량은 종목당 1콜이다(가드 `tests/unit/engine/test_cycle302_backfill_scope_expansion.py::test_g302_3_converged_universe_costs_one_call_per_ticker`). 첫 채움만 종목당 3콜이라 20:30 정기 실행이 아니라 **수동 trigger**(`POST /api/stock-master/daily/refresh`, 기본 `force=true`)로 장 종료 후에 돌린다 — 20:30 에 얹으면 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창(20:35~)을 침범한다.
- **1회 backfill 이 target 을 넘는다 — 한 밤에 채운다.** `condition.fetch_daily_candles_backfill` 의 깊이 환산이 `total_days=225` 에서 347 달력일에 닿아 약 **232 영업일**이다. 🔴 그 환산의 **stride 는 7/5 고정**이다 — 키우면 윈도우 사이에 구멍이 생긴다(상세 = `src/api/CLAUDE.md`). 가드 = `tests/unit/engine/test_cycle299_backfill_target_expansion.py::test_g299_9_one_pass_reaches_target`.
- ⚠️ `existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD(=50)` → 100일 단발 분기(`_DAILY_LOAD_FETCH_DAYS`)는 **225 > 50 인 한 도달 불가**한 구조적 폴백이다(신규 상장도 첫 밤에 225일을 탄다). 목표 깊이를 50 아래로 되돌리면 되살아난다 — 관계 핀 `test_cycle302...::test_g302_8b_deep_target_dominates_incremental_threshold`.
- ⚠️ **상장 이력이 225 영업일보다 짧은 종목은 수렴하지 않는다** — 매일 밤 3콜을 쓰고 목표에 못 닿는다(최근 상장 코호트 한정). 자본 위험 0 · 관측 채널 = `[stock_master_daily_load_summary]` 의 `mode=`(전 종목 backfill 이면 `full`, 수렴하면 `incremental`, 섞이면 `mixed`)와 `elapsed_ms`.
- 읽기 쪽 — `db/stock_master_daily.get_recent_daily` 의 상한은 `_MAX_DAILY_ROWS`(400)이고, VCP 는 전략 파라미터 `daily_fetch_depth_mode` 로 요청 깊이를 정한다(코드 기본값 `"cap100"` = 100봉, `"full"` = `ema_long + base_max_days + 10`). 200일 EMA 를 실제로 쓰려면 `"full"` 이어야 한다(상세 = `strategies/CLAUDE.md` VCP 절).
- graceful — backfill 실패는 `failed++` 후 다음 ticker. 🔴 장중 자동 실행 없음 — 20:30 daily task + 수동 trigger 뿐이다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 확정 전 오늘봉 시각 필터 (`_drop_today_bars`)

`_stock_master_daily_load_once` 는 `fetched += 1` **뒤** · `upsert_batch` **앞**에서 `_drop_today_bars(candles, now_kst=load_now_kst, today=today)` 로 확정 전 오늘봉을 폐기한다. 그 자리가 유일하게 안전하다 — 두 fetch 분기(`fetch_daily_candles` / `fetch_daily_candles_backfill`)의 **합류점**이고 `fetched`("KIS 응답을 받았다")·`failed`(KIS 실패 전용) 카운터의 의미가 보존된다.
- **판정 기준 = 시각 단독.** `load_now_kst`(= `datetime.now(KST_TZ)`, **함수 진입 시 1회** — `stock_master.list_all` 페이징 *앞*, tz-aware 필수)가 `_DAILY_LOAD_TODAY_BAR_CUTOFF`(= `time(20, 0)` — KRX 애프터마켓 종료 시각. 그 전에는 당일 거래량이 부분값이다) **이전**이면 `bas_dd >= today` 를 폐기하고, 이후면 `bas_dd > today`(시계 왜곡 방어)만 폐기한다. `bas_dd` 파싱 불가·부재는 **보존**한다. 20:00 뒤에 남긴 오늘(D) 봉은 거래량은 확정이지만 종가·고저는 잠정 봉이다(위 「시각과 순서」).
- 🔴 **커트오프는 scanner 전용 상수다.** 값이 같아 보여도 scheduler 의 매매·보드 시각 상수를 재사용하지 않는다 — 매수 보드 시각 변경이 적재 규약을 딸려 바꾸는 커플링을 끊는다(`tradable_boards` ↔ 청산 규약 커플링을 끊어 둔 원칙과 같은 이유). `scanner` 가 `scheduler` 를 import 하면 값의 일치가 **우연**이 아니라 **커플링**이 된다.
- ⚠️ **데이터 기준(거래량 0 ∧ OHLC 평탄) 금지** — 반증 2건: (a) 장중 재시작이 만드는 **부분봉**은 거래량>0·비평탄이라 데이터 기준을 확정봉인 척 통과한다(평탄하지 않아 눈에 안 띄어 껍데기보다 나쁘다) (b) 거래정지 종목의 **진짜 평탄 확정봉**을 저녁 적재에서 죽여 그 날짜 행을 영영 못 갖게 한다. 시각 기준은 둘 다 자동 처리하고 진짜 무거래봉을 정의상 100% 보존한다.
- **fail-open** — 판정 예외는 전량 upsert 유지(현행 행위) + `[daily_load_today_filter_skipped]` WARNING **실행당 1행**. fail-closed 는 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이라 금지. 판정 실패는 **캔들 단위**이지 종목 단위가 아니다(`isinstance(candle, dict)` 방어 — 이상 원소 하나가 그 종목의 필터 전체를 무력화하면 오늘 껍데기까지 함께 샌다).
- **수동 실행(`POST /api/stock-master/daily/refresh`, 기본 `force=true`)도 필터를 통과한다** — `force` 는 `latest >= today` 멱등 skip **만** 우회한다. 주말·20:00 이후 수동 보정은 오늘 날짜 봉 자체가 없거나 확정봉이라 무접촉이고, 장중·시간외 수동 실행만 잠정봉을 버린다(설계 의도).
- **관측 = `[daily_load_today_bar_filter]` 실행당 1행 INFO**(`mode` / `cutoff` / `now` / `today` / `dropped_rows` / `tickers_affected` / `filter_errors`). 종목당 emit 은 하루 1,000행 폭주다. `dropped_rows`(행) ≠ `tickers_affected`(종목)이고, `filter_errors > 0` 이 fail-open 발생을 뜻한다 — 이게 없으면 `dropped_rows=0` 이 "버릴 봉이 없었다" 와 "필터가 전량 죽었다" 를 구분하지 못한다. 유니버스가 비면(`candidates=0` 조기 return) 이 마커가 0행이므로, 안 보이면 `[stock_master_daily_load_begin] candidates=` 를 먼저 본다. `mode=` 는 20:00 을 경계로 keep/drop 이 갈린다.
- **D 봉을 최종값으로 바꾸는 곳은 둘이다.** 1차 = 다음 거래일 아침 부팅의 `daily_bar_finalize`(prepare 직전, 아래 「전일 잠정 봉 확정」 절). 2차 = D+1 정기 실행(20:30)의 7일 증분 창(`fetch_days=7` → `ON CONFLICT DO UPDATE`). 2차는 그날 유니버스 안 종목만 덮고, 1차는 유니버스가 아니라 DB 행을 보고 고른다 — 유니버스에서 빠진 종목의 잠정 봉도 1차가 고친다. 🔴 7일 창을 1~2일로 줄이지 않는다 — 1차가 꺼졌거나(`daily_bar_finalize_mode=off`) 그 종목에서 실패한 날의 안전망이다(가드 = cycle263 G2 의 "보정 창 존치" 단언).
- **부작용** — 신규 상장·유니버스 진입 종목의 backfill 은 같은 날 20:30 에 이뤄진다(그 사이 `get_recent_daily_normalized` 는 `reason="miss"` KIS 폴백 = 데이터는 더 정확하지만 장중 KIS 호출이 는다). 최종 커버리지 손실은 0. UI `last_daily_load_at` 은 낮 동안 어제 날짜로 보인다(의미상 정확).

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 일봉 적재 본체

- 호출 = `_stock_master_daily_load_task_loop` 가 매일 20:30 KST 1회.
- lifecycle = `run_periodic_task_loop` 위임(`start()` 직후 즉시 1회 — 영업일 슬롯 게이트가 판정 — + 매일 20:30 while 루프). `stop` 계열 3곳이 `_stock_master_daily_load_task` 를 cancel 한다(`tests/unit/engine/test_scheduler_stop_zombie_tasks.py` 의 `expected_members` 가 목록을 잠근다).
- 종목마다 `max_bas_dd(ticker) == 오늘` 이면 skip 한다(멱등 — `force` 가 우회). 그 밖은 위 「분할 backfill 분기」 의 깊이 분기다.
- KIS `fetch_daily_candles` / `fetch_daily_candles_backfill`(`src/api/condition.py`) **재사용**(신규 KIS API 도입 0) → `stock_master_daily.upsert_batch(ticker, rows)` 영속화.
- graceful — KIS 거부·타임아웃이면 그 ticker 를 skip 하고 다음으로 간다. upsert 실패는 `[stock_master_daily_load_skip] ticker= reason=upsert_batch_failed` WARNING + `db_write_failures` 카운터(KIS 실패 `failed` 와 분리).
- 요약 = `[stock_master_daily_load_summary] total= fetched= upserted_rows= skipped_fresh= failed= elapsed_ms= mode=` 1행 INFO(`data_load_tasks.py` 서식). `failed` 는 KIS 실패만 센다 — `db_write_failures` 는 반환 dict 와 진행 state(`refresh_progress` 의 `failed` = 둘의 합)에만 있다. 500건마다 진행 emit.
- 어댑터 `get_recent_daily_normalized`(`src/db/stock_master_daily.py`)는 전략 6파일의 `prepare()`(`expected_head` 전달) · kojiro `recompute_held_atr` · `llm_buy_gate`(뒤의 둘은 인자 없이 달력 판정)가 쓴다. 신선도 판정 계약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 전일 잠정 봉 확정 (`daily_bar_finalize.py`, 부팅 prepare 직전)

20:30 적재가 쓴 D 봉은 종가·고저가 잠정이다(위 「시각과 순서」). 그래서 다음 거래일 아침 부팅이 prepare 직전에 잠정 봉만 골라 KIS 에서 다시 받아 덮는다. 20:30 적재는 그대로다. 새 컬럼도 새 KIS API 도 없다 — 받는 TR 은 적재와 같은 FHKST03010100 시장 `J` 다. 명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8.
**배선** — `boot_manager.boot()` 안 두 자리다. `scheduler.py`·`scanner.py` 는 이 기능에 0줄이다.
- 토큰 발급 직후 = `daily_bar_finalize.spawn(phase="boot")`. 태스크를 띄우기만 한다. 설정 로드·잔고·레짐(최대 25초)·자금 배분·`count_active` 대기와 겹쳐 돈다.
- `emit_daily_head_staleness()` 바로 앞 = `wait_for_boot(task, budget_secs=BOOT_BUDGET_SECS)`. 그 뒤 prepare 루프가 확정된 봉을 읽는다.
- 순서 `get_token` < `spawn` < `wait_for_boot` < `emit_daily_head_staleness` < prepare 는 AST G5(a) 가 잠근다.
- 배경 일꾼 수는 상수가 없다. 전환 뒤 `_run_workers` 가 0번 일꾼 하나만 남긴다.
**잠정 판정 — `updated_at` 하나로 한다.** `stock_master_daily.list_provisional_rows(*, since, head, today_boundary)` 가 SQL 로 고른다. `updated_at` 규약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.
- 헤드 `head` = `stock_master_daily.max_bas_dd_before(오늘)` = `max(bas_dd) WHERE bas_dd < 오늘`(오늘 = KST 날짜). 오늘·미래 날짜 봉은 조건에서 빠진다(오늘 껍데기 봉 방어). 휴장일 달력은 쓰지 않는다.
- 헤드 조회는 예외를 삼키지 않는다. 실패하면 `result=error stage=head` 로 끝난다. 결과가 `None`(오늘 앞 봉이 하나도 없음)이면 `result=noop` 이고 `head=` 는 빈 값이다.
- 헤드 행 = `updated_at < 오늘 06:00` 이면 잠정. 헤드보다 옛 행 = `updated_at < (bas_dd + 1일) 06:00 KST` 이면 잠정. 헤드에 더 보수적인 기준을 쓰는 이유 = 주말·연휴 중 쓰기가 확정인지 모르고(KIS 야간 처리가 비영업일에도 도는지 모른다), 헤드는 prepare 가 직접 읽는 행이라 한 번 더 받는 비용이 싸다.
- 같은 날 재기동은 대상이 0 이다(아침에 덮은 행은 `updated_at` 이 06:00 뒤다). 00:00~06:00 에 수동 기동해도 안전하다 — 그때 쓴 행은 06:00 전이라 잠정으로 남고 다음 부팅이 다시 받는다(`start()` 는 20:00 이후만 거부한다).
1. 모드를 읽는다(아래 킬스위치). `off` 면 `result=noop` 1행을 남기고 끝난다.
2. 대상을 조회해 종목별로 `oldest`·`newest` 로 묶는다. 헤드보다 뒤 행은 버린다.
3. 순서 = ① `069500`·`229200`(시장 유닛·ETF 레짐 입력) ② DB `positions` 보유 종목(청산 입력 ATR·스테이지) ③ 나머지를 `newest` 내림차순 → 종목코드순. 예산을 넘겨도 prepare 가 가장 많이 읽는 헤드가 먼저 확정된다. 보유 조회가 실패하면 ② 없이 진행한다.
4. 받기 = `condition.fetch_daily_chart_ranged_with_summary(ticker, start, end)`. `start = oldest − 10일`, `end = newest` 다. `end` 는 항상 헤드 이하라 **오늘 봉을 받지 않는다**(AST G5 d). 구간이 130일을 넘으면 `start` 를 `newest − 130일` 로 자르고 `span_clipped` 로 센다. 응답에서 `[start, newest]` 밖 봉은 버린다.
5. 교차검증 — 그 종목의 `newest` 가 헤드일 때만 한다. `prdy` = `output1.stck_prdy_clpr`. `prdy` == 헤드 봉 종가 → `verified` · `prdy` == 헤드 앞 봉 종가 → `unrolled`(KIS 요약이 아직 날짜를 넘기지 않았다 — 시각 기준으로 받아들여 쓴다) · 그 밖 → `mismatch` · 응답에 헤드 봉이 없음 → `missing` · 응답이 비었거나 KIS 예외 → `failed`. **`mismatch`·`missing`·`failed` 종목은 쓰지 않는다.**
6. 쓰기(`enforce`) = 기존 `stock_master_daily.upsert_batch(ticker, 받은 봉 전부)`. 새 쓰기 SQL 은 없다. 쓰기 전 DB 값과 비교해, 잠정이던 행 중 값이 바뀐 행을 `close_changed`·`hl_changed` 로 센다. upsert 가 예외이거나 돌려준 수가 보낸 수보다 적으면 `db_write_failures` 다. `observe` 는 받고 비교만 하고 쓰지 않는다.
- `wait_for_boot` = `asyncio.wait_for(asyncio.shield(task), timeout=budget_secs)`. 부팅을 멈추지 않는다 — 태스크가 없으면 바로 돌아오고, 예산을 넘겨도 태스크를 **취소하지 않고** 배경 전환 신호만 켠 뒤 돌아온다(부팅은 prepare 로 간다). 태스크의 예외는 WARNING 을 남기고 흡수한다.
- 전환 뒤 첫 일꾼이 `result=budget_exceeded` WARNING 1행을 남긴다. 그 뒤로 0번 일꾼 하나만 `BG_SLEEP_SECS` 간격으로 나머지를 처리하고, 끝에 `phase=background` 요약 1행을 더 남긴다. 확정 시작부터 `HARD_CAP_SECS` 가 지나면 멈추고 `result=hard_cap` 을 남긴다(판정은 종목 사이). 태스크 참조는 모듈 전역 `_BG_TASKS` 가 붙든다(`funnel_capture._BG_TASKS` 관례).
- `CancelledError` 는 부팅 자신에게 취소 요청이 걸렸을 때만 전파한다(`asyncio.current_task().cancelling() > 0`). 확정 태스크만 밖에서 취소됐으면 WARNING `wait_for_boot 확정 태스크가 외부에서 취소됐다` 를 남기고 부팅을 계속한다 — `shield` 는 부팅이 취소될 때 확정 태스크를 지킬 뿐, 확정 태스크 자신의 취소는 그대로 올려 보낸다.
- 호출은 `kis_get_quote`(시세 풀)로 나가 전역 한도 20건/초(`src/api/base.py` `_rate_limit`)를 주문과 함께 쓴다. 부팅 대기 중(주문 없음)은 3 일꾼으로 한도까지 쓰고, 배경은 1 일꾼 + 0.05초로 약 7건/초만 쓴다(20:30 적재와 같은 보폭).
**실패 방향 — 매수를 막지 않는다(fail-open). 잠정 값을 조용히 쓰지도 않는다(개수 + 표본을 마커에).**
- 🔴 종목 단위로 매수 후보에서 빼지 않는다. 유령 키가 두 전략을 전 기간 체결 0건으로 만든 fail-closed 방향이다.
- `finalize_once` 는 `CancelledError` 말고는 예외를 밖으로 내지 않는다. 단계별 `try` 밖 예외는 바깥 `try` 가 받는다(`stage=unexpected`).
- 일꾼 하나가 못 잡은 예외로 죽으면 `_run_workers` 가 나머지 일꾼을 취소하고, 멈출 때까지 기다린 뒤 다시 던진다. 그래서 `stage=processing` 요약이 찍힌 뒤에는 어떤 일꾼도 쓰지 않는다.
- 실패한 종목은 잠정 상태로 남는다. 다음 부팅(창 21일)과 D+1 20:30 7일 창이 다시 받는다.
**킬스위치 `system_config.daily_bar_finalize_mode`** — 키 없음 = `enforce` · `observe`(받고 비교만) · `off`(아무것도 안 함) · 행은 있는데 모양이 틀림 = `observe` · 조회 실패 = `enforce`(요약에 `mode=enforce(db_error)`). 조회 실패를 `enforce` 로 두는 이유 = 쓰는 값이 KIS 확정값이라 고치는 것 자체가 안전하다. 판정은 `system_config._select_value`·`_string_from_raw` 를 재사용한다(cycle369 `status_exit_mode` 와 같은 판정). `finalize_once` 시작마다 읽으므로 바꾼 값은 **다음 부팅부터** 먹는다. 🔴 운영 DB 쓰기라 승인 대상이다. 롤백 = `daily_bar_finalize_mode = 'off'`(승인 대상) 또는 커밋 되돌리기 — 이 leaf 가 쓴 데이터는 KIS 확정값이라 되돌릴 필요가 없다.
- `[daily_bar_finalize] phase=boot|background mode= result=ok|noop|budget_exceeded|hard_cap|error [stage=] head= since= targets= fetched= upserted_rows= close_changed= hl_changed= verified= unrolled= mismatch= missing= failed= db_write_failures= span_clipped= pending= elapsed_ms= [sample_failed=<≤5>] [sample_mismatch=<≤5>]` — 실행당 1행. 예산을 넘긴 날은 `budget_exceeded` 1행 + `phase=background` 1행이다. 요약 마커를 남기지 않는 경로는 취소(`CancelledError`) 하나다.
- **INFO 는 `result` 가 `ok`·`noop` 이고 `failed`·`missing`·`mismatch`·`db_write_failures` 가 전부 0 일 때뿐이다.** 나머지는 WARNING 이다. `noop`(대상 0)도 1행을 남긴다 — 「안 돌았다」와 「고칠 것이 없었다」를 가른다.
- `stage=`(`result=error` 일 때만) = `head`(헤드 조회 실패) · `select`(대상 조회 실패) · `processing`(일꾼 단계 예외 — 나머지 일꾼을 멈춘 뒤 찍는다. traceback 동반) · `unexpected`(그 밖 예외 — 대상 묶기·순서 정하기 등. traceback 동반). `head`·`select` 는 아무것도 고치지 않은 것이다. `mode=off` 가 아닌데 `result=noop head=`(빈 값)이면 테이블에 오늘 앞 봉이 하나도 없는 것이다.
- `unrolled` 는 실패가 아니다. 그 개수는 「`stck_prdy_clpr` 가 D 로 넘어가는 시각」을 운영 중에 모으는 표본이다.
- 두 번째 눈 = `[prev_close_overwrite]`(`src/api/CLAUDE.md` `condition.py` 절). 09:30 급등 스캔이 `ticker_prev_close` 를 기준가로 덮을 때 값이 달랐던 종목을 남긴다.
- 성공 서명 = 07:45 기동이면 07:46~07:47 에 `phase=boot result=ok` 1행 · `close_changed` 가 `targets` 의 약 40~60%(예상 — 09-23 봉 실측 비율. `targets` 는 종목 수, `close_changed` 는 행 수라 세는 단위가 다르다. 평시엔 종목당 잠정 행이 1개라 견줄 수 있다) · `[prev_close_overwrite]` 는 권리락·배당락 종목 말고 0.
- 판독 = `unrolled` 가 대부분인데 `close_changed` 가 거의 0 이면, 그날 부팅 시각까지 KIS 가 아직 정규장 값으로 바꾸지 않은 것이다(아래 한계 1).
**시각 불변식(AST G7)** — `TIME_SESSION_START_CUTOFF`(20:00) + `HARD_CAP_SECS` ≤ `TIME_STOCK_MASTER_DAILY_LOAD`(20:30) < `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` − 10분. 가장 늦은 부팅(19:59)도 20:10 전에 끝나 20:30 적재와 20:35~ 보조 토큰 창에 겹칠 수 없다.
**부팅 시간** — 늘어나는 시간 = 확정 소요 − 겹친 시간(설정·잔고·레짐). 평시 약 +20~45초(예상), 최악은 예산만큼 +90초다. 그만큼 +600초 레거시 재준비(「funnel 스냅샷 캡처」 절)의 시작도 밀린다. 07:45 기동의 최악이면 레거시 재준비가 ≈07:59:45 에 끝나 08:00 NXT 프리장까지 여유가 얇다. 요약의 `elapsed_ms` 로 본다.
- 예산을 넘긴 날은 부팅 prepare 가 확정 전 종목을 읽는다. 그날 후보는 +600초 레거시 재준비가 확정된 DB 로 다시 만든다(배경은 확정 시작 + 600초에 반드시 끝나고, 레거시 재준비 task 는 `_boot()` 뒤에 만들어져 +600초에 시작하므로 항상 그 뒤다). 🔴 S2 가 레거시 분기를 없앨 때 이 역할을 넘겨받아야 한다.
- 전략 객체(`_candidates`·`_held_stage3`·`_entry_atr` …)는 읽지도 쓰지도 않는다 — DB 만 쓴다(cycle364 PV-1 과 교집합 0). 보유 종목의 진입 ATR 스탬프는 그대로다. 부팅 prepare 가 확정 봉으로 트레일링 ATR·kojiro 스테이지를 다시 계산하는 것은 원래 부팅의 일이다(애프터마켓이 넓힌 고저가 걷혀 ATR 이 조금 줄 수 있다).
- 시장 유닛은 4전략 prepare 안에서 계산하므로 확정값을 읽는다(`069500` 이 순서 ①). ETF 레짐(관찰 전용)은 prepare **앞**(`_refresh_market_regime_and_persist`)에서 계산돼 확정 전 잠정 종가를 읽을 수 있다.
- 부팅 즉시 일봉 적재(`start()` + 240초, 전날 20:30 결손 날만)와 배경이 겹쳐도 결과는 같다. 둘 다 같은 아침의 KIS 값을 같은 upsert 로 쓴다.
- `_drop_today_bars`·cycle363 `expected_head` 는 무변경이다. 헤드 날짜는 그대로이고 값만 바뀐다. ④ `[funnel_boot_vs_evening]` 에 주는 영향 = 「funnel 스냅샷 캡처」 절 ④ 항목.
1. 06:00 경계는 표본 두 묶음으로 정했다. KIS 야간 처리가 부팅보다 늦는 날은 잠정 값을 받아 쓰고, 그 행은 06:00 뒤에 쓴 것이라 확정으로 분류된다. `output1` 이 이미 넘어가 있으면 `mismatch` 로 잡힌다. 둘 다 안 넘어간 날(`unrolled` 대부분)은 못 잡고, D+1 20:30 7일 창이 다시 덮는다.
2. 권리락·배당락일은 전일종가와 기준가가 달라 `mismatch` 가 날 수 있다. 그 종목은 락 게이트(`_row_has_lock`)가 prepare 에서 KIS 로 폴백시키고, D+1 20:30 7일 창이 덮는다.
3. 수정주가(`FID_ORG_ADJ_PRC="0"`) 값으로 구간을 덮는다. 그 사이 액면분할 등이 있었으면 덮은 구간과 그 앞 DB 봉의 기준이 다를 수 있다. 창을 21일로 묶은 이유다.
**테스트 격리** — 루트 `tests/conftest.py` autouse `_neutralize_daily_bar_finalize` 가 `finalize_once` 를 즉시 끝나는 빈 코루틴으로 바꾼다. `spawn`·`wait_for_boot` 는 실물이라 배선은 그대로 돈다.
- 🔴 그래서 `spawn` 은 `finalize_once` 를 **모듈 전역 이름으로** 불러야 한다. 이름을 미리 묶으면 중립화가 새어 테스트가 실제 DB·KIS 에 닿는다(G9-5).
- leaf 를 직접 검증하는 테스트만 마커 `real_daily_bar_finalize` 로 옵트아웃한다. 마커 사용처는 허용 목록으로 묶는다(G9-6).
- `tests/unit/engine/strategies/test_cycle386_prev_close_regression.py` — G8(잠정 전일종가와 확정 전일종가에서 momentum·LTV·VB 판정이 갈리는 실사례가 확정 뒤 정규장 기준 판정으로 돌아온다).
- 실 Postgres `tests/integration/test_cycle386_provisional_predicate_pg.py` — G1 경계 · 세션 시간대 무관 · `updated_at` 을 다시 쓰는 트리거 없음 · 왕복 뒤 같은 날 재기동 noop · 오늘·미래 행이 있어도 헤드는 오늘 앞 최신 봉(`max_bas_dd_before` 실 SQL — 단위 하네스는 그 SQL 을 가짜로 둔다).

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › basics 갱신 (`_stock_master_basics_refresh_once`)

- `stock_master.list_all()` 페이징(PAGE_SIZE=1000) → 종목별 `inquire_stock_basics()`(CTPF1002R + FHKST01010100 merge) → `stock_master.upsert_one()`.
- 🔴 **기존 raw 머지 보존** — `list_all` 로드 시 `existing_raw_by_ticker` 에 기존 row 의 `raw` 를 보관하고, upsert **전** 에 새 raw 가 dict 이고 기존이 비어 있지 않으면 `{**기존, **신규}` 로 머지한다. 안 하면 개장 전 FHKST `acml_tr_pbmn=0` 이 `_ZERO_VALUE_SKIP_KEYS` 로 빠지고 `upsert_one` 이 raw 를 통째로 교체해 **거래대금 15키가 매일 지워진다**(그러면 VB·LTV·donchian·BFB 의 universe 가 0이 된다). bare object(`model_copy`/`raw` 부재)는 `getattr` graceful.
- graceful — KIS 거부는 `[stock_master_basics_refresh_skip] ticker=X reason=Y` WARNING + `failed++` 후 continue.
- 500건마다 `[stock_master_basics_refresh]` INFO 진행 emit + 종료 시 `[stock_master_basics_refresh_summary] total= updated= skipped= failed= elapsed_ms=` 1행. 전량 스윕 약 13분.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 마스터 적재 (`_stock_master_master_load_once`)

- KIS 공식 마스터 파일(`src/api/kis_master.py`) 다운로드 → `master_raw` 배치 upsert → `refresh_progress` 갱신 → graceful.
- 지수 편입 판정 = `kospi200_apnt_cls_code != ""` → `is_kospi200=True` / `ksq150_nmix_yn == "Y"` → `is_kosdaq150=True` → `upsert_master_raw(ticker, record, is_kospi200=, is_kosdaq150=)`.
- 소비 = `stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True)`(양쪽 True 면 OR 합집합, 한쪽만이면 단독 필터, 둘 다 None 이면 무필터) → donchian `_scan_universe` 의 `FUNNEL_STAGES[0]` "코스피200+코스닥150 합집합". 컬럼 정의는 `src/db/CLAUDE.md`.
- 🔴 시총 헬퍼 3종(`market_cap_master_to_millions` / `validate_market_cap_consistency` / `get_market_cap_millions`)은 **존재하지 않는다** — AST 가드 `tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py` 가 재도입을 막는다. 시총 필터는 `list_by_filter`/`list_paged_by_filter` 가 직접 한다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 재무 적재 (`_stock_master_financial_load_once`)

- 주1회 재무 5 TR(`src/api/finance.py`) 적재. 유니버스 = `_is_daily_load_universe` 자격 종목. ticker 별 `stock_master_financial.max_stac_yymm` 신선도 skip → 미신선이면 `fetch_all_financials` → `upsert_financial_batch`.
- loop = `run_periodic_task_loop` 위임, `initial_delay_secs=900` + `immediate_skip_if_fresh_hours=168`(주1회 신선도 게이트), `task_label="stock_master_financial_load"`, `task_attrs` 4 위치, `refresh_progress` TaskKey `"financial"`.
- 매수 경로 무접촉 — 매수 진입 **전** 데이터 계층이다.

### 출처 절: 저녁 데이터 적재 (scanner + data_load_tasks) › 매수 진입 차단 (`_is_master_blocked_for_entry`)

`master_raw` 우선 · `raw` 폴백으로 **7건**을 본다: `trht_yn` 거래정지 / `mang_issu_yn` 관리종목 / `ssts_hot_yn` 공매도과열 / `stange_runup_yn` 이상급등 / `sltr_yn` 정리매매 / `mrkt_alrm_cls_code` 시장경고 / `invt_alrm_yn` 투자주의환기(KOSDAQ 전용). 🔴 **매수 진입 전 차단이다 — 이미 보유한 종목에는 영향이 없다.**

### 출처 절: funnel 스냅샷 캡처

캡처는 **라이브 전략 객체의 메모리**(`_funnel_steps`·`get_scanned_tickers()`)를 DB `strategy_funnel_snapshots` 에 옮긴다. 매매 행위와 무관한 관찰 경로지만, 같은 전략 객체를 준비(`prepare`)가 다시 채우므로 **준비·캡처 순서와 라벨**이 계약이다.

### 출처 절: funnel 스냅샷 캡처 › 공통 헬퍼와 호출처

- `capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None, skipped_out=None) -> int` — 라벨 `label = target_date or 오늘(KST)`. 전략마다 먼저 `funnel_capture.capture_skip_reason(strategy, label, today, is_provisional=...)` 를 묻고, 통과한 전략만 `_funnel_steps` 단계별 + `step_no=99` 를 `target_date=label` 로 insert 한다. 전략별 예외 격리(graceful), momentum 영구 제외, in-place upsert. 완료 로그 = `[funnel_snapshot] 캡처 완료 — target_date= saved= provisional= skipped=<sid:사유,…>`. `skipped_out` 에 dict 를 주면 건너뛴 전략마다 `{sid: 사유}` 를 채운다(사유 문자열은 완료 로그와 같다). 반환값은 이 인자와 무관하다 — 수동 trigger 만 이 인자를 넘긴다.
  - 09:30 자동 — `_auto_capture_funnel_snapshots`, `is_provisional=False`, `target_date=today_kst()`. 실행은 `_scan_loop` 첫 패스라 첫 대기 `SCAN_INTERVAL` 뒤 ≈09:35.
  - 저녁 — `_evening_funnel_capture_once` → `funnel_capture.evening_capture_once(self)`(한 줄 위임), `is_provisional=True`. 21:00 정기 실행은 `target_date=다음 거래일`, 레거시 분기는 오늘(아래).
  - 수동 trigger — `routes/strategy_funnel.py::trigger_snapshot`, `is_provisional=False`, `target_date` 없음 = 오늘.

### 출처 절: funnel 스냅샷 캡처 › 라이브 준비는 wrapper 한 곳에서, 한 번에 하나

- 라이브 전략의 `prepare()` 는 `funnel_capture.live_prepare_one(strategy, *, phase)` · `live_prepare_many(strategies, *, as_of, phase)` 로만 부른다. `phase` = `boot`(`boot_manager`) · `presubscribe`(07:59 사전 구독 직전, 후보가 빈 VB/LTV·스윙 재준비) · `intraday_empty`(`_reprepare_breakout_if_empty`) · `evening`(21:00) · `reprepare_legacy`(레거시 분기). 가드 = `test_cycle364_ast_live_prepare_lock.py` — `src/engine` 에서 `strategies/**`·`funnel_capture.py` 를 뺀 곳의 `.prepare(` 직접 호출과 `getattr(X, "prepare")` 가 0 이다.
- 잠금 = 이벤트 루프별 `asyncio.Lock` 하나(`_lock()`). 두 준비가 같은 객체의 `_funnel_steps`/`_candidates` 를 섞지 않게 한다. `live_prepare_many` 는 전략마다 잡고 푼다.
- never-raise — `prepare()` 예외는 wrapper 가 흡수해 `False` 를 돌려주고 `[live_prepare] <sid> phase=<phase> 전략 prepare 실패`(phase=boot) 또는 `… 재 prepare 실패`(그 밖) 를 ERROR + traceback 으로 남긴다(옛 호출부 문구 그대로 = grep 연속성). 그래서 호출부에 try/except 를 두지 않는다. `_reprepare_breakout_if_empty` 는 `False` 를 받으면 `write_log("ERROR", "<sid> 재 prepare 실패")` 한 줄만 더 남긴다. 🔴 그 자리에서 logger ERROR 를 또 찍지 않는다 — 실패 1건이 ERROR 로그 2행이 되어 21:30 `top_patterns` 집계가 배가된다.
- meta = 전략 객체의 `_live_prepare_meta = {as_of, phase, started_at, finished_at, ok}`. **시작 시점에 `ok=None` 으로 먼저 찍고**, 끝나면 `ok`(bool)·`finished_at` 을 채운다. `as_of` 인자가 없으면 시작 시각의 KST 날짜가 들어간다. 전략 코드는 이 필드를 읽지도 쓰지도 않는다.

### 출처 절: funnel 스냅샷 캡처 › 캡처 라벨 가드 — `capture_skip_reason`

판정은 위에서부터 첫 해당에서 멈춘다. `None` 이면 캡처한다.
5 가 필요한 이유 = 자정이 지나면 저녁 meta 의 `as_of` 가 새 오늘과 같아져 4 를 통과한다. 그대로 두면 00:xx 수동 캡처가 저녁 미리보기를 **확정** 행으로 저장한다. 수동 캡처는 건너뛴 전략과 그 사유를 응답 `message` 에 적는다(응답 키 불변 — `src/routes/CLAUDE.md`).

### 출처 절: funnel 스냅샷 캡처 › 저녁 미리보기 — 21:00 정기 실행

- 🔴 **21:00 인 이유와 금기** — 20:30 일봉 적재 뒤라야 오늘(D) 봉을 「전일」로 읽는다. 20:45 보조 7계정 토큰 강제 재발급 체인(`quote_token_refresh`) 뒤라야 한다 — 그 직렬화 창 [20:35, 20:53] 에 보조 풀 REST(일봉 KIS 폴백·휴장일 조회)가 들어가면 자연 재발급이 겹쳐 발급 수가 두 배가 된다. 21:30 정산 전에 끝나야 한다. **20:30~20:55 로 당기지 않는다.** 가드 = `test_cycle364_time_invariants.py`(적재 < 캡처 · `TIME_QUOTE_TOKEN_REFRESH + 15분 ≤ 캡처` · 캡처 + `EVENING_START_DEADLINE` + 준비 예산 3분 ≤ `TIME_SETTLEMENT`) + 기존 충돌 스캔 `test_cycle273…::test_g273f_2` · `test_cycle269…::test_c9`.
  1. 30초(`EVENING_POLL_SECS`) 간격 폴링. 시작 마감 = 캡처 시각 + `EVENING_START_DEADLINE`(15분) = **21:15**.
  2. 회차마다 달력을 다시 푼다. `is_open_day(오늘)` 이 `False` 면 즉시 `decision=skip reason=today_closed`(INFO). `True` 면 `resolve_as_of(now, "evening")` 이 `as_of = next_trading_day(오늘)` · `expected_head = 오늘` 을 준다(`mode="evening"` 만 지원, 모르면 `None`).
  3. 적재 완료 신호 = `system_config.get_task_last_success("stock_master_daily_load")` 가 **오늘 `TIME_STOCK_MASTER_DAILY_LOAD`(20:30) KST 이상**일 때만이다(`_marker_done`). 날짜만 같은 마커(부팅 보충 적재가 07:5x 에 쓴 것)와 naive 마커는 완료가 아니다 — 받아들이면 20:30 적재가 실패한 날 D-1 헤드로 미리보기가 돈다.
  4. 21:15 까지 준비가 안 되면 건너뛴다 — 달력을 끝내 모르면 `reason=calendar_unknown`, 마커가 없으면 `reason=daily_load_not_done`, 둘 다 **WARNING**. 준비는 부르지 않는다. 🔴 추측한 날짜로 라벨을 붙이지 않는다(다음 부팅이 정본 목록을 만든다). 🔴 대기 신호를 `count_all() > 0` 으로 되돌리지 않는다 — 빈 테이블만 막을 뿐 그날 적재를 기다리지 않는다.
  5. `live_prepare_many(…, as_of=as_of, phase="evening")` — 대상은 `registry.all()`(비활성 포함). 순서 = 활성 먼저, 그 안에서 VB → LTV → BFB → VCP → donchian → kojiro → momentum → 그 밖.
- 요약 1행 = `[evening_funnel_capture] decision=run|skip|legacy_reprepare reason= as_of= expected_head= load_marker= daily_head= prepared= saved= skipped=<sid:prepare_failed,…>`. `daily_head` = `stock_master_daily.max_bas_dd()`(인덱스 컬럼) 1회, 폴링 루프 밖에서 구한다. 조회 실패는 `None`(모름)이다.
- 🔴 **PV-1 이 전제다** — 21:00 에 옮기는 것만으로는 안전하지 않다. 미리보기 준비가 보유 종목의 청산 입력(kojiro `_held_stage3`, 네 전략의 `_candidates` 보유 엔트리)을 바꾸면 야간 틱 하나로 청산이 나갈 수 있다. 20:00 뒤에도 stale watcher 가 보유를 HIGH 로 다시 구독하므로 틱 부재는 보장이 아니다. 계약 = `strategies/CLAUDE.md` 「prepare 공통」 절.
- 미리보기가 만든 준비 상태는 21:30 정산 뒤에도 메모리에 남는다(`_reset_daily_state` 는 전략의 후보·`_funnel_steps`·`_scanned_tickers` 를 지우지 않는다). 그래서 다음 부팅까지 대시보드가 다음 세션 후보를 보여 준다. 활성 전략은 다음 부팅이 다시 준비한다.

### 출처 절: funnel 스냅샷 캡처 › 레거시 분기 — 21:00 전 (S1 임시)

- `evening_capture_once` 는 `now.time() < TIME_EVENING_FUNNEL_CAPTURE` 이면 이 분기를 탄다. 실제로 타는 것은 `start()` +600초 즉시 1회다(`immediate_first_run` 기본값, 게이트 kw 전무 — 07:45 기동이면 ≈07:57). `run_daily` 가 매 거래일 `start()` 를 다시 부르므로 재시작이 없어도 매일 돈다. 오후 재기동(16:00~20:00)의 +600초도 이 분기다.
- 동작은 미리보기가 아니다 — `registry.all()` 전부를 `as_of=None`(오늘)로 다시 준비하고(`phase="reprepare_legacy"`) 오늘 라벨 잠정(`is_provisional=True`) 행을 쓴다. 로그 = `[evening_funnel_capture] decision=legacy_reprepare reason=boot_immediate_run …`. 이 재준비는 살아 있는 전략 객체의 후보를 교체하므로 그 뒤 매수 평가는 이 결과를 쓴다.
  - **입력은 부팅 준비와 같다.** 부팅 준비(`_boot()` 안의 전 전략 `prepare()`)는 `start()` 가 적재 태스크(`_full_universe_load_task` +0초 · `_stock_master_daily_load_task` +240초 · `_stock_master_basics_refresh_task` +480초)를 만들기 **전에** 끝난다. 그 세 적재의 즉시 실행은 영업일 슬롯 게이트를 지나야 돈다(「정기 task 루프」 절). 그래서 평상시 월요일·연휴 뒤 아침에는 보충 적재가 돌지 않고, 재준비는 부팅 준비와 같은 입력을 읽어 같은 목록을 낸다.
  - **보충 적재가 도는 날**(직전 영업일 정기 실행 결손 = `reason=stale` · 휴장일 모름 = `calendar_unknown` · full_universe 행 수 미달 = `below_floor`)에는 그 적재가 바꾼 입력을 라이브 후보에 반영하는 경로가 이 재준비다. 이 반영은 순서 보장이 아니라 경합에 기댄다 — 레거시 재준비는 아무것도 기다리지 않아 +240초 일봉 보충 적재의 **완료**를 기다리지 않는다.
  - 🔴 **이 즉시 1회에 게이트를 걸지 않는다** — 재준비의 `self._candidates = {}` 가 donchian 보유 종목을 후보에서 지워, 그날 트레일링 ATR 이 `_entry_atr`(매수 시점 ATR)로 떨어진다. 재준비를 건너뛰면 그 기준이 부팅 recompute 의 오늘 ATR 로 바뀐다. 청산 규약 변화라 그 결정(cycle360 카드 3)이 게이트보다 먼저다(근거 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.4·§5).
  - **장전 풀 갱신과 겹쳐도 입력이 깨지지 않는다** — 월요일·연휴 뒤 장전에는 `scanner._scan_pool_eager_refresh_loop`(5분 주기)가 24h 를 넘긴 풀 종목을 갱신하고, 그 갱신과 +600초 재준비가 같은 시각(T+600)에 시작할 수 있다. 그 갱신은 `upsert_one` 전에 basics 경로와 같은 `{**기존 raw, **신규 raw}` 머지를 해 장전 0 값 키(`_ZERO_VALUE_SKIP_KEYS` — `acml_tr_pbmn` 등)를 기존 값으로 보존한다 — 그래서 `list_by_filter` 거래대금 임계(`acml_tr_pbmn_won`)가 NULL 로 떨어지지 않는다(cycle363, 사용자 승인 8영역). 판별 = `[scan_pool_eager_refresh] refreshed=N`(N>0 이면 그 사이클이 실제로 돌았다는 뜻, 결함 여부와 무관) + `select count(*) from stock_master where not raw ? 'acml_tr_pbmn'`(머지가 살아 있으면 이 값이 늘지 않는다). 회귀 = `tests/unit/engine/test_cycle363_scan_pool_eager_refresh_raw_merge.py`.
  - ⚠️ **07:59 사전 구독 재준비가 이 분기 뒤에서 기다릴 수 있다.** 두 준비는 같은 잠금을 쓰고, 07:45 기동이면 레거시(≈07:57 시작, 60~75초)가 `TIME_PRESUBSCRIBE`(07:59)에 걸친다. 부팅이 전일 잠정 봉 확정 대기로 길어진 날은 레거시 시작도 그만큼 늦다(평시 +20~45초, 최악 +90초 — 「저녁 데이터 적재」 절). 사전 구독 재준비는 부팅 뒤 VB/LTV 후보나 스윙 후보가 빈 날에만 돈다(부팅 준비 실패 회복). `asyncio.Lock` 은 들어온 순서대로 넘기므로 기다림은 호출 하나당 전략 하나의 준비(VCP 약 35초)까지다. 그 사이 뒤에 이어지는 사전 구독(보유 포함)과 08:00 프리장 진입이 그만큼 밀린다.
- 🔴 **S2 가 이 분기를 없앤다** — 아침 재준비를 「입력이 실제로 바뀐 날만」으로 바꾸는 판정(②)·완료 대기와 조용한 창(③)·비상 캡처는 **아직 코드가 없다**(설계 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §4·§5). S2 착수 근거는 아래 ④ 의 평시 `same=1` 실측이다.

### 출처 절: funnel 스냅샷 캡처 › 하루 쓰기 순서와 확정 행 보호

- 거래일 D 의 쓰기 = ≈07:57 레거시 → `(D, 잠정)` · ≈09:35 자동 → `(D, 확정)`(잠정을 덮는다) · 21:00 → `(다음 거래일, 잠정)`. 저녁 쓰기는 다른 날짜 키로 가므로 **그날 매매에 쓴 확정 행이 남는다**. 20:05·21:30 리포트의 `strategy_funnel_stages`(D) 는 09:35 확정본을 읽는다.
- 같은 키에서 **잠정 쓰기는 확정 행을 못 덮는다**(③-b — `insert_snapshot` 이 `None` 을 돌려준다, 계약 = `src/db/CLAUDE.md` `strategy_funnel.py` 절). 거래일 20:00 뒤 오늘 라벨 잠정 쓰기(장중·저녁 재기동의 레거시 분기)가 그 경우다.
- 다음 거래일 09:30 확정 캡처가 저녁 잠정 행을 덮는다. 저녁 목록의 영구 기록은 ④ 로그뿐이다. VCP 의 오전 prepare 별 후보 목록은 스냅샷이 아니라 `[vcp_breakout_distance_summary]` 로 복원한다(`strategies/CLAUDE.md` 각주 ⑥).

### 출처 절: funnel 스냅샷 캡처 › ④ 저녁 목록 ↔ 부팅 목록 대조 `[funnel_boot_vs_evening]`

- 배선 = `boot_manager` 가 익일청산 복구 직후 `spawn_funnel_boot_vs_evening(scheduler, phase="boot")` 를 **await 없이** 부른다. task 는 `scheduler._ws_task` 가 생길 때까지 0.2초 간격으로 기다린 뒤(그동안 DB 무접촉) `emit_funnel_boot_vs_evening` 을 돈다. 🔴 `_boot()` 는 WebSocket 연결 **전**에 await 되므로, 동기로 두면 보유 중 재기동의 틱 공백이 그만큼 늘어난다.
- 대기의 끝 — 기다리는 동안 `scheduler._running` 이 거짓이 되면 DB 를 건드리지 않고 조용히 끝난다(정지·기동 실패 뒤 다음 기동과 겹쳐 ④ 가 두 번 찍히지 않게). 속성이 없으면 참으로 본다. 누적 대기가 `_WS_WAIT_TIMEOUT_SECS`(120초)를 넘으면 `[funnel_boot_vs_evening] phase=boot error=ws_not_started strategies=<활성 전부>` WARNING 1행을 남기고 끝난다.
- task 참조 = 모듈 전역 `_BG_TASKS` 에 넣고 `add_done_callback(_BG_TASKS.discard)` 로 스스로 빠진다(`llm_buy_gate` 관례 — asyncio 는 버린 Task 를 약한 참조로만 쥔다). 전체 상한 = `BOOT_VS_EVENING_TIMEOUT_SECS`(10초, `asyncio.wait_for`). S1 의 `phase` 는 `boot` 뿐이다.
- 저녁 목록 = `list_snapshots(target_date=오늘, raise_on_error=True)` 의 `step_no=99 ∧ is_provisional=True` 행 `survived_tickers`(보통 전날 21:0x 미리보기가 쓴 것). 없으면 `[funnel_boot_vs_evening] phase=boot as_of= evening=absent` INFO 1행. `raise_on_error=True` 인 이유 = 기본값은 DB 예외를 삼키고 `[]` 를 돌려주므로 DB 장애가 「저녁 캡처 없음」으로 읽힌다.
- 부팅 목록 = 활성 전략의 `get_scanned_tickers()`. 그것을 부를 수 없는 전략(momentum)은 저녁 행이 있어도 행을 내지 않고 건너뛴다 — 비교할 부팅 목록이 없어서다. 실패가 아니므로 `error=strategy_failed` 에 세지 않는다(회귀 `test_cycle364_funnel_boot_vs_evening.py::test_boot4_23_when_strategy_has_no_scanned_list_then_skipped_without_failure`). 비교 전에 양쪽에서 보호 종목(전 전략 보유 ∪ `_pending_next_day_clear`)을 뺀다 — 저녁엔 보호 종목이 마스터 차단·가격 필터를 통과하고, 부팅엔 포지션 복구 전이라 보유가 0 이다. 그 차이는 설명된 차이다.
- 원인 힌트 = **부팅당 1회**, DB 3쿼리, 창 `[evening_at, until)`. `evening_at` = 저녁 행 `snapshot_at` 최솟값, `until` = 가장 이른 `phase=boot` meta 의 `started_at`(없으면 지금). 상한을 두는 이유 = 부팅 자신의 보유 종목 eager refresh 는 준비 **뒤**에 돈다. 상한이 없으면 그것이 `sm_refreshed_after` 로 새어 월요일·연휴 뒤마다 WARNING 이 억제된다.
  - `bars_changed_after`·`head_now` = `stock_master_daily` 를 `bas_dd >= evening_at::date − 2일`(인덱스 컬럼)로 먼저 묶고, `updated_at` 이 창 안인 행 수와 `max(bas_dd)` — 무인덱스 `updated_at` 전 행 스캔을 피한다
  - 못 구한 축은 `None`(모름)이다. 한 호출 안에서 첫 쿼리 실패가 나면 `[funnel_boot_vs_evening] phase=boot hint_error=<축>` WARNING 1행을 남긴다(세 쿼리가 다 실패해도 1행). 힌트가 `None` 이면 아래 WARNING 판정이 서지 않으므로, 이 행이 「꺼진 판정」과 「깨끗한 결과」를 가른다. 이 행은 ④ 실패(`error=`)가 아니다.
  - PG 왕복 = `tests/integration/test_cycle364_boot_vs_evening_hints_pg.py` — 창 안·밖 행을 심고 세 개수가 정확한 정수인지, `head_now` 가 `max(bas_dd)` 인지 본다.
- 행 = 전략마다 `[funnel_boot_vs_evening] phase=boot strategy= as_of= evening_at= evening_n= boot_n= same= added= removed= sample_added=<≤5> sample_removed=<≤5> held_excluded= params_changed= bars_changed_after= sm_refreshed_after= head_now=`. 기본은 INFO 다. `same=0` 이면서 세 힌트가 **전부 0** 일 때만 WARNING(설명 안 되는 차이)이다 — 힌트가 `None` 이면 WARNING 이 아니다.
- ⚠️ **전일 잠정 봉 확정이 켜진 날은 `bars_changed_after` 가 평일마다 수백 이상이다** — `daily_bar_finalize` 가 부팅 prepare 앞에서 헤드 봉을 다시 쓰기 때문이다(「저녁 데이터 적재」 절). 틀린 값이 아니라 아침에 입력이 실제로 바뀐 것이다. 그래서 「세 힌트 전부 0 인데 목록이 다르다」 WARNING 은 평일에 거의 나지 않는다. 🔴 S2 착수 근거로 모으는 평시 `same=1` 표본은 이 leaf 배포 전후를 합산하지 않는다. S2 가 쓸 입력 변화 신호는 `updated_at` 이 아니라 `[daily_bar_finalize]` 의 `close_changed`·`hl_changed` 다.
- 🔴 **실패는 조용히 사라지지 않는다** — 이 대조가 S2 착수의 판정 근거라서다. 전략 한 줄의 예외는 그 전략만 격리하고 끝에 `[funnel_boot_vs_evening] phase=boot error=strategy_failed strategies=<…>` WARNING 1행. `list_snapshots` 실패는 `error=list_snapshots_failed strategies=<활성 전부>` WARNING 1행이다(`evening=absent` 로 보고하지 않는다). 타임아웃과 그 밖 예외는 `error=timeout_or_exception strategies=<아직 못 낸 전략>` WARNING 1행. WebSocket 단계가 120초 안에 안 생기면 `error=ws_not_started`(위).

### 출처 절: funnel 스냅샷 캡처 › 기타

- `task_attrs` 4 위치(start + connect finally + run_daily finally + stop, G-AST2).
- `is_provisional` 컬럼 = migration 040.

### 출처 절: 접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2

「선행 체결통보 체크 → skip 로그 → `TradeRecord` 조립 → race 흡수 INSERT」는 **코어 하나**가 한다 — `_persist_pending_after_send(*, trade_type, ticker, order_no, strategy_id, record_price, quantity, path)`. 4 경로(매수 주·폴백 · 매도 주·폴백)는 전부 **축별 경계 래퍼**를 거친다 — `_persist_buy_pending_after_send` · `_persist_sell_pending_after_send`. 코어 직접 호출은 **그 두 래퍼뿐**이고 `execute_buy`/`execute_sell` 안에는 **0건**이다(가드 `test_g328_0c`).
🔴 **경계(cycle327 ⓑ)는 코어에 없다 — 호출자 층의 책임이다.** 코어는 예외를 **그대로 전파**하고, 축별 래퍼가 자기 `except Exception` 으로 받는다. 코어에 `try` 를 들이면 두 래퍼의 `except` 가 **영영 도달 불가**가 되어 좁히기·지우기 회귀가 무증상이 된다(가드 `test_g328_0d`).
- 🔴 **래퍼의 `except Exception` 을 좁히지 않는다 — 구조 가드가 유일한 방어다.** 좁히면 행위 회귀가 초록인 채로 샌다 — 매도는 기존 회귀가 **전부 초록**인 채로 접수 성공 주문을 「거부」로 적고 익일청산 큐에 넣었고(cycle328), 매수는 **`UniqueViolationError` 케이스가 통과**했다(cycle335 — 좁히기가 「가장 많이 테스트된 타입」을 그대로 잡는다). 타입 표본을 늘려도 같은 종류의 누락에 노출되므로 행위 테스트로는 못 막는다. 가드 = `test_g328_3`/`test_g328_3b`(두 축 parametrize).
- **접수된 자금은 묶어 둔다** — 접수 후 실패에서 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다**. 접수된 매수는 KIS 가 주문가능금액에서 이미 뺀 「묶인 자금」이라 푸는 것은 **우리가 묶인 사실을 잊는 것**이다. 풀면 같은 종목 재매수 + 전략 예산 이중 사용 + 그 틱 청산 평가 소멸 + 900초 매수 락이 함께 열린다. 계좌 방어(`get_buyable`)는 전략 예산보다 훨씬 커서 통과하므로 **전략 예산 관문만 조용히 무력화**된다. 유지의 비용은 **체결 0건으로 끝난 주문 한정**으로 그 슬롯·금액이 노는 것뿐이다. 그 주문의 KIS 행이 끝남(`tot_ccld_qty==0 ∧ rmn_qty==0`)을 보이면 다음 잔고 sync 에서 `buying_reconcile`(모듈 맵)이 푼다. 20:00 뒤에 끝난 주문은 21:30 `_reset_daily_state` 까지 남는다. 첫 **부분**체결만 나도 `_handle_buy_fill` 이 해제한다(그 블록은 전량 분기 **앞**이다).
- **마커 2종** — `[buy_post_send_error] ticker= order_no= strategy= path= qty= price=` · `[sell_post_send_error] ticker= order_no= strategy= path=`. 둘 다 **ERROR · 무cap**(21:30 `top_patterns` 편입). 🔴 매수만 `qty=`·`price=` 를 싣는 이유 = 매도는 포지션이 남아 사후에 규모를 알 수 있지만 **매수는 포지션도 장부도 없어** 그 줄이 규모를 아는 유일한 채널이다. 🔴 cap 을 걸지 않는 이유 = 이 마커가 **「예산을 점유한 채 장부가 없는 주문」의 유일한 목록**이라 건별로 KIS 주문내역과 대조해야 한다. **판독** = 하루 5건 이상이면 이 시정의 결함이 아니라 **RDS 가 아픈 것**이다(revert 는 경계를 없애 로그만 지운다).
- 🔴 **축 파생 방향이 계약이다** — `_PENDING_SIDE_BY_TRADE_TYPE` 가 **행위값(`trade_type`)에서 관측값(`side`)을 파생**시킨다. 반대로 하면 `side` 오타 하나가 `trade_history` 의 매수/매도를 뒤집는다.
- **수식어 표** `_PENDING_SKIP_PREFIX[(side, path)]` 는 `.get(key, "")` **총함수**다(관측이 행위를 바꾸면 안 된다). ⚠️ `("buy","fallback")` 만 `"매수 폴백 "` 이 아닌 것은 **현행 문구 보존**이다.
- ⚠️ **21:30 `top_patterns` 는 메시지 전문이 키다** — 매수 폴백 skip WARNING 에 ` (주문번호: %s)` 가 붙었으므로 **2026-09-21 전후 패턴 문자열을 비교하지 않는다**. `[sell_post_send_error]` 폴백 꼬리 문구도 2026-09-20 에 주 경로와 통일됐다 — **그 날짜 전후도 비교하지 않는다**(마커 + 4필드는 byte 동일).
- 자문 = `_workspace/domain_consult/cycle335_buy_post_send_boundary.md` · 설계 카드 = `_workspace/refactor/2026-09-21_step2_card.md` · 가드 = `tests/unit/ast/test_cycle328_sell_pending_helper.py` · 회귀 = `tests/unit/engine/test_cycle335_buy_post_send_boundary.py` · `test_cycle327_sell_fill_during_insert.py` · `test_cycle271_execute_buy_fill_during_insert.py`

### 출처 절: 취소 타이머 키 — `(ticker, 축)` (cycle332)

`_pending_cancel_tasks` / `_pending_cancel_order_no` 의 키는 **`(ticker, side)`** 다(`side ∈ {"buy","sell"}`, 리터럴은 모듈 상수 `CANCEL_AXIS_BUY`/`CANCEL_AXIS_SELL` 한 곳에만 둔다). 매수 잔량 취소(`_schedule_cancel`)와 매도 손절 잔여 재주문(`_schedule_cancel_and_reorder`)이 **각자 자기 축만** 교체하므로 두 타이머가 공존한다. ticker 단독 키면 나중에 걸린 쪽이 앞선 쪽을 `order_no` 검사 없이 죽인다.
- **S1(매수 타이머가 손절 타이머를 죽인다)이 심각하다** — `_cancel_and_reorder` 는 취소 3경로 중 **유일한 `cancel_order → place_order` atomic replace** 다. 그게 죽으면 원 매도 주문이 호가에 남고 시장가가 아니면(프리장 `step_down` 변환·KRX 애프터 `41` 지정가·NXT 잔존) **안 팔린다**. 매도 **부분**체결 분기는 `_selling` 을 discard 하지 않으므로 `risk.on_tick` 의 `_selling` 가드가 `check_exit_signal` 을 건너뛰고, `selling_reconcile`(180초)도 원 주문이 **열린 채**라 `open_order` = **유지** 분기다. 즉 **급락장에서 손절 잔여가 체결도·재주문도·재평가도 못 받은 채 21:30 까지 간다**.
- **S2(매도 타이머가 매수 타이머를 죽인다)** — 미취소 매수 잔여가 남아 (a) 손절 중인 종목을 계속 사들이고 (b) `pending_buys`/`pending_buy_amounts` 는 첫 부분체결에서 이미 풀리므로 그 잔여가 나중에 체결되면 **설계 랏을 넘는다**. K축·ρ축 캡은 **진입 시점 통제**라 못 막는다.
- 🔴 **해제의 `order_no` 일치 게이트는 그대로다**(cycle273a 계약) — 축으로 나눈 것은 **등록**뿐이다. 같은 축 재스케줄은 교체한다(부분체결 연속은 정상이고, 안 그러면 타이머가 쌓인다).
- **UI 계약 보존** — `GET /api/trading/status` 의 `pending_cancels` 는 **ticker 배열**이다(`frontend/src/types/trading.ts` · `OrderMonitor.tsx`). `order_engine.pending_cancel_tickers(engine)` 한 줄 파생이 담당하고, 한 종목에 두 축 타이머가 걸려 있어도 **한 번만** 나온다. 🔴 `order_no` 단독 키를 쓰지 않는 이유가 이것이다(그쪽이 더 정확하지만 UI 의미가 바뀌고 cycle273a·cycle291 가드 다수가 재작성 대상이 된다).
- `scheduler._reset_daily_state` 의 일괄 clear 는 `.values()`/`.clear()` 라 **키 모양과 무관 = 무접촉**.

### 출처 절: 발사 창 귀속 — `pending_buys` 단 (cycle331)

`await place_order` 가 걸려 있는 동안 주문번호 매핑 5종이 **전부 비어 있고** `pending_buys` 는 **이미 차 있다**(`execute_buy` 가 `place_order` **앞**에서 넣는다). 그 창에 착지한 **우리 자신의** 매수 체결통보는 `_order_strategy` miss → `trade_history` miss(PENDING INSERT 도 `place_order` 뒤라 그 `order_no` 행이 원리상 없다) → `is_ticker_held_by_any` **참** 으로 흘러 P1-B(B-2) 조기 return 에 걸린다. `is_ticker_held_by_any` 는 `_strategies.values()` **전수**를 보고 `has_position OR is_buy_pending` 이므로(`strategy_registry.py`) **매수 당사자 자신이 그 조건을 세운다** — 창에 들어오면 예외 없이 걸린다.
🔴 **그러면 Position 이 아예 등록되지 않아 그날 하루 손절·트레일링·15:20 일괄청산이 성립하지 않는다**(`risk.on_tick` 은 `state.positions` 를 본다). 익일청산만 다음 날 `_boot` 의 KIS 잔고 복구가 되살린다. `trade_history` 는 `mark_pending_buys_completed` 가 장부만 뒤늦게 맞추므로 **대시보드·DB 어느 쪽을 봐도 정상으로 보인다**.
- **귀속 단** = 폴백 체인에 `_resolve_pending_buy_owner(ticker)` 단을 `trade_history` **뒤**, B-2 가드 **앞**에 둔다. 채택은 `ticker in state.pending_buys` 인 전략이 **정확히 1개**이고 그 전략이 **미보유**일 때만. 0개·2개 이상·판정 예외는 `None` 으로 물러선다(fail-open, **결과 집합 ⊆ 현행**). 전부 in-memory, `await` 0, never-raise — 체결통보 콜백의 예외는 `realtime/handler.py` 규약상 **WS 재연결**을 부른다.
- 🔴 **B-2 가드를 없애지 않는다** — 그것이 막는 것은 **출처를 모르는 매수가 `momentum` 을 우겨 남의 포지션을 덮는 것**(377450 사고)이고 수동 매매·외부 주문에서 여전히 유효하다. **수동/외부 매수는 우리 `pending_buys` 에 없으므로 이 단을 타지 않는다.**
- 🔴 **잔량 취소 타이머는 `qty_src == "map"` ∧ 귀속이 `pending` 단이 **아닐** 때만 건다** — 이 단이 창의 통보를 부분 체결 분기에 도달시키는데, 귀속이 틀린 랏에서 `_cancel_after_wait` 가 30초 뒤 **사람이 낸 주문의 잔량을 취소**한다(cycle327·cycle329 와 같은 계열). 잃는 것은 없다 — 우리 주문이면 매핑이 곧 서고 잔여 통보가 `src=map` 으로 와서 정상적으로 건다. 보류는 `[buy_partial_no_cancel_timer]` WARNING.
- **관측** = `[buy_fill_strategy_from_pending] order_no= ticker= strategy= qty_src= incr= filled_total= ordered=` **무cap WARNING** = 귀속 단의 성공 서명. cap 을 `(ticker,strategy)` 로 묶으면 같은 날 두 번째 사건이 사라지는데, 실측 빈도가 낮아 **한 건 한 건이 조사 단위**다. 형제 마커 `[buy_fill_fallback_held_conflict]` 도 무cap ERROR 이고, **진짜 미지 출처만 남아 0 에 수렴**이 정상이다.
- ⚠️ **1주 랏에 집중된다** — 단일 통보로 전량 체결되면 **두 번째 통보가 없어 자기 치유 경로가 구조적으로 없다**. 다주 랏은 잔여 통보가 `src=map` 으로 와서 포지션을 만들어 준다. 우리 매수의 상당수가 1주라 노출이 크다.
- ⚠️ B-2 ERROR 문구는 `"타 전략 보유/주문중"` 이다 — 그 판정이 `has_position OR is_buy_pending` 이라 **보유가 아니라 주문 중**일 수 있다. 21:30 리포트 `top_patterns` 는 메시지 전문을 키로 쓰므로 **2026-09-21 전후 패턴 문자열을 비교하지 않는다**(경위 = history).
- **별건 권고** = `scheduler._sync_positions_from_balance` 의 `is_ticker_held_by_any` 를 **보유 축만** 보는 헬퍼로 바꾸면 블라인드 창이 17~24시간 → ≤15분이 된다. 다만 그 함수 소비처가 5곳이라 광역 회귀이고, 귀속 단이 들어간 뒤로는 실익이 작다.

### 출처 절: 체결통보 주문수량 — 출처 3단 (cycle329)

`handle_execution_notice` 는 「이 주문의 **주문수량**이 몇 주인가」를 세 출처에서 이 순서로 얻는다.
| `map` | `_order_qty[order_no]` | 우리 주문이고 매핑이 이미 섰다(정상, 하루 수천 건) |
| `payload` | 체결통보 `fields[16] ODER_QTY` | **매핑 부재 창**에서 주문수량을 아는 유일한 경로 |
| `increment` | 이번 통보의 증분 체결량 | 둘 다 없을 때의 폴백 |
🔴 **막는 결함** — `order_no` 는 KIS 응답이 와야 알 수 있어 `await place_order` 가 걸린 동안 매핑 5종이 **전부 비어 있다**. 그 창에 착지한 통보는 `ordered_qty` 가 증분 체결량으로 폴백돼 `total_filled >= ordered_qty` 가 **항상 참**이 되고 **부분 체결이 전량으로 읽힌다**. 매수는 `_completed_buy_orders` 가 무장해 잔여 통보가 `[buy_fill_duplicate_ignored]` 로 **조용히 버려진 채** `_sync_positions_from_balance` 가 `is_ticker_held_by_any → continue` 라 **기보유 수량을 영원히 고치지 않는다**(10주를 갖고 3주로 믿는 상태가 익일 `_boot` 까지 간다). 매도는 **주문 축만** 틀린다 — 매핑·타이머·`_selling` 이 일찍 정리되지만, 보유 축이 체결량만큼만 빼므로 잔량은 손절 감시 안에 남는다(「매도 체결 — 주문 축과 보유 축」 절).
- 🔴 **전량 판정에 출처 게이트를 걸지 않는다** — `qty_src != "increment"` 조건을 붙이면 payload 가 없는 퇴화 상황에서 **수동 전량 매도가 유보**되어 포지션 유령 잔존 + `_selling` 좀비(= 손절 마비)가 된다(`selling_reconcile` 의 `held_zero` 는 해제가 아니라 **유지** 분기다). payload 가 있으면 수동 주문도 정확해지므로 게이트 자체가 불필요하다.
- 🔴 **재주문 타이머는 `qty_src == "map"` 일 때만 건다** — 매핑 부재 창의 통보도 **부분 분기에 도달**한다. `_cancel_and_reorder` 는 취소를 **조건 없이** 내고, 발사 직전 보유 재조회(J-2, 「매도 체결 — 주문 축과 보유 축」 절)는 **재발사 수량**만 보유에 맞춘다. `payload` 에는 수동 매매 주문도 포함되므로 게이트가 없으면 **사람이 낸 주문을 우리가 30초 뒤 취소하고 다시 낸다** — cycle327 이 봉한 「주문이 나간 뒤의 재발사」와 같은 계열이다. 우리 주문의 잔여는 ms 뒤 다음 통보가 `src=map` 으로 와서 정상적으로 건다(잃는 것 0). 보류는 `[fill_partial_no_reorder]` WARNING 이 남긴다.
- **overrun 클램프 게이트 = `qty_src != "increment"`** — payload 는 KIS 가 준 주문수량이라 매핑과 같은 신뢰도이고, 배제하면 이 창에서 클램프만 꺼진다.
- 🔴 **`fields[16]` 은 cycle235 가 오독해 사고(257720)를 낸 자리다** — 체결수량 소스 `fields[9]` 는 무접촉이고 `test_cycle235_ast_execution_qty.py` 가 그대로 봉인한다. 매핑이 선 **정상 통보마다** `[ordered_qty_mismatch]` 로 payload 를 대조한다(불일치해도 판정은 `map` 값을 쓴다) — 그 사고는 부분/분할 체결에서만 드러나 오래 잠복했는데, 이 대조는 창을 기다리지 않는다.
- **관측** = `[fill_qty_src] order_no= ticker= side= src= ordered= filled_total= incr=` — `src=map` 은 **DEBUG**(정상·대량), 나머지 둘은 **WARNING**(`KstDailyEmitCap[(src,ticker,side)]` 1회/일). WARNING 이상만 21:30 `top_patterns` 에 오르므로 **비정상만 리포트에 뜬다**. `_settle()` 직전 `[fill_qty_src_summary] window=day map= payload= increment=` 1행 — 🔴 **호출부를 try/except 로 감싸지 않는다**(scanner 일일 summary 2종과 같은 이유). **판독** = `payload > 0` 이면 그 창이 실제로 열렸고 **우리가 막았다**(성공 서명) / `increment > 0` 인데 그날 수동 매매를 한 적이 없으면 **조사 신호**(payload 가 안 실려 온다 = 그 창의 결함이 아직 남는 경로).
- ⚠️ **남는 사각** — payload 가 없으면 매핑 부재 창에서 주문수량을 알 길이 없다. 매수는 결함이 그대로다. 매도는 주문 축만 틀리고 보유 축은 출처와 무관하게 정확하다. 그 빈도는 `increment` 카운터가 센다.

### 출처 절: 매도 체결 — 주문 축과 보유 축 (cycle385)

사람은 보유의 일부만 팔 수 있다 — `POST /api/trading/manual-sell` 의 `quantity` < 보유, MTS/HTS 매도, 손절 잔여 재주문이 그렇다. 전략 매도는 언제나 보유 전량을 내므로 「주문이 끝났다」와 「보유가 0 이 됐다」가 같은 말이지만, 일부만 팔면 둘이 갈라진다. 그래서 `_handle_sell_fill` 은 두 판정을 나눈다. 근거 = 사용자 결정(2026-09-26·27) 「부분매도해도 잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리할 수 있다는 전제하에 허용」.
이 절의 규칙은 세 불변식을 지키려고 있다(명세 부록 R).
- **추적 밖 실보유 0** — 추적 수량이 실보유보다 **작아지는** 쪽(과소 추적)은 만들지 않는다. 과대 추적은 허용한다. 다음 매도의 APBK0400 → #1.5 재대조가 회수한다.
- **우리 주문 합 ≤ 추적 수량** — 걸린 우리 매도와 새 우리 매도를 합쳐도 추적을 넘지 않는다. 계좌에 운영자가 따로 산 몫이 있어도 우리 주문은 그 몫을 팔지 않는다.
- **잔여는 팔 수 있어야 한다** — 다른 주문이 일부를 잠가도 안 잠긴 추적 잔여는 손절이 판다. 동결은 팔 수 있는 추적 잔여가 0 일 때만이다.
⚠️ 세 불변식이 깨지는 경로가 아직 남아 있다 — 이 절 끝 「알려진 한계」.
`hold_dec` = 이번 체결량에서 재대조 크레딧이 흡수한 몫을 뺀 수량이다(아래 「#1.5 재대조와 늦은 통보」). 크레딧이 없으면 체결량 그대로다.
- **보유가 남으면** 차감 수량을 `save_position` 으로 upsert 한다. 인자 8개를 전부 넘긴다(한 필드라도 빠지면 다른 값이 덮인다). 종목명은 `scanner.ticker_names` 캐시에서 넘기고, 캐시가 비면 빈 이름이 간다 — `save_position` 은 빈 이름으로 저장된 이름을 덮지 않는다(`src/db/CLAUDE.md`). 삭제·훅·`sold_today`·구독 해제는 하지 않는다. 저장 실패는 `[sell_fill_db_error] step=save_position` ERROR 로 남기고 전파하지 않는다 — 체결통보 콜백의 예외는 `handler.py` 규약상 WS 재연결을 부른다. 메모리는 이미 차감됐고, DB 의 옛 수량은 재시작 뒤 매도 시점 #1.5 재대조가 고친다. 재시작 전에 접수된 주문의 체결은 `pending` 에 세지 않으므로 그날 재시작 전 매도가 있어도 고친다(아래 「원장 시작 전 주문」). `delete_position` 은 감싸지 않는다.
- 🔴 **보유 축에도 출처 게이트를 걸지 않는다**(「체결통보 주문수량」 절 금기와 같다). `map`/`payload`/`increment` 어느 출처든 체결량만큼 빼고 0 에서만 닫는다(AST A10).
- 🔴 **주문이 끝나면 `_selling` 을 푼다 — 어느 주문의 종료든, 보유가 남아도 푼다.** `risk.on_tick` 은 `_selling` 에 든 종목의 `check_exit_signal` 을 건너뛴다. 그래서 남기면 잔여 보유의 손절이 멈춘다. 주문 축 If 본문의 첫 두 문장이 `self._selling.discard(ticker)` · `self._selling_locked_wait.discard(ticker)` 이고, 그 If 의 첫 `await` 앞이다.
  - 🔴 해제에 조건을 달지 않는다. `qty_src` · 보유자 · `pos` 는 통보 앞쪽 `await`(`_lookup_strategy_from_trade_history` · `delete_position` · `save_position`) 전에 잡은 값이다. 그 값으로 가르면, 우리 통보가 REST 응답보다 먼저 와서 DB 조회 중일 때 응답이 착지한 경우 주문이 끝나도 표식이 남는다(AST AR2-1 — 해제를 감싸는 If 가 없고, `qty_src` 가 해제를 가르지 않는다).
  - 🔴 「표식을 세운 주문의 종료로만 푼다」로 좁히지 않는다 — 원주문 취소를 이미 낸 재주문 태스크가 다음 부분 체결 통보에 교체 취소되면 재주문이 나갔는지 알 길이 없어, 그 표식은 풀 주체 없이 `selling_reconcile` 까지 좀비로 남는다(명세 부록 R2-1). 대가는 이 절 끝 「알려진 한계」 첫 항목이다.
  - `_selling_locked_wait` = 「지금 `_selling` 은 우리 `execute_sell` 이 **주문 없이** 멈춰 세워 둔 것이다」. 부분 잠김 판매의 보류(`fire ≤ 0` · 주문 조회 실패 — `[sell_qty_partial_locked]` · `[sell_qty_hold_orders_unavailable]` · `[sell_qty_unnoticed_fills]`)와 `[sell_qty_locked]` 가 return 직전에 넣는다. `execute_sell` 진입과 수동 매도 라우트의 `_selling` 세움(새 주인이 섰다) · 주문 축 종료 · J-2 `gone` · 재주문 미접수 해제 · 닫기 묶음 해제 · `reset_daily_state()` 가 뺀다.
  - **동결이 지키던 보유가 닫히면 동결을 푼다.** 닫기 묶음(`if close_position:`)에서 `ticker in _selling_locked_wait` 이면 `_selling` · `_selling_since` · 표식을 비운다(`[selling_freeze_released]`). 동결이 기다리던 외부 주문이 부분 체결로 추적을 0 으로 만들고 「종료」가 끝내 오지 않으면(운영자가 나머지를 취소 등), 이것이 없을 때 `_selling` 이 하루 끝까지 남는다 — `selling_reconcile` 은 보유 0 인 종목의 표식을 유지한다(`held_zero`). 조건이 표식이라, 우리 주문이 걸린 채 외부 체결이 추적을 0 으로 만든 경우는 유지한다(AST AR2-7).
  - 주문이 부분이면 `_selling` 은 그대로다(주문이 아직 열려 있다).
  - `POST /api/trading/manual-sell` 이 `_selling` 을 발사 **앞**에서 세우는 것도 잔여 보유의 손절을 지키기 위해서다(`src/routes/CLAUDE.md`).
  - `_handle_sell_fill` 의 「매도 체결: 전략 찾을 수 없음」 오류 경로도 `_selling` 을 푼다(운영에서 momentum 은 항상 등록돼 있어 도달하지 않는다).
- 🔴 **`if total_filled >= ordered_qty:` 는 함수 본문 최상위에 글자 그대로 1개다**(AST A1). `test_cycle273a_ast_partial_optin_and_timer.py` g273_ast3/ast4 가 그 If 안에서 타이머 해제와 `order_no` 게이트를 찾는다. `del positions[...]` 는 `_handle_sell_fill` 안에 남는다(G2-STRUCT-INVARIANT 의 site 집합).
- **소유 전략** — 장부 전략 `sid` = `_order_strategy` → `_lookup_strategy_from_trade_history` → **registry 전수 보유자가 정확히 1개**면 그 전략(`[sell_fill_owner_from_holding] from=none`) → `"momentum"` 순이다. 보유 축 전략 = `sid` 가 그 종목을 들고 있으면 그것, 아니면 보유자가 정확히 1개일 때 그것이다(`[sell_fill_owner_from_holding] from=<sid>`). `sid` 가 들고 있지 않은데 보유자가 2개 이상이거나 판정 예외면 **보유 축은 어느 수량도 바꾸지 않는다**(`[sell_fill_owner_ambiguous]` ERROR). 보유자가 0 이면 주문이 끝날 때 닫기 묶음(`on_position_closed`·`sold_today`·`delete_position`)을 돈다(추적 보유가 없는 전략의 멱등 정리).
  - 🔴 `_ticker_holders(ticker)` 는 `registry.all()`(꺼진 전략 포함)을 본다. `enabled()` 로 좁히면 꺼진 전략의 실보유를 놓친다. `registry.get(strategy_id)` 로 좁히면 그것이 곧 `"momentum"` 기본값 함정이다. 동기 · `await` 0 · never-raise(예외 = `None`)(AST A5).
  - 소유 해석 뒤 보유 차감까지 `await` 가 없다(AST A9). 그래서 `execute_sell` 루프 상단 재조회·J-2 재조회와 원자적으로 맞물린다.
- **손익** = 이번 체결분만 `(체결가 − 매수가) × 체결량` 이고 보유 축 전략의 `daily_realized_pnl` 에 더한다. 크레딧이 흡수한 몫도 실제로 판 주식이라 손익은 체결량 전체로 잡는다(AST AR3). `trade_history` SELL 행 수량은 그 주문의 수량(= 판 수량)이다. 분할 매도의 매수↔매도 짝짓기는 `get_trade_pairs` 의 누적 보유 모델이 맡는다.
- **보유보다 큰 체결** — 추적이 이미 실보유보다 작았다는 뜻이다(수동 추가매수 등). 보유를 0 으로 닫고(음수 금지) `[sell_fill_exceeds_holding]` WARNING 을 남긴다. 남은 실보유는 15분 sync 가 「미보유」로 보고 다시 채택한다. 주문 축 overrun 클램프(누적 > 주문수량)와는 다른 축이다.
- 🔴 **`execute_sell` 은 발사 수량을 `send_qty` 로 고정한다.** 재시도 루프 상단 재조회 직후 `send_qty = pos.quantity` 를 잡고, `sell_cap` 이 있으면 `min(send_qty, sell_cap)` 으로 줄인다(줄이기만 한다 — 아래 부분 잠김). 발사·`_order_qty`·`_persist_sell_pending_after_send(quantity=)`·로그에 그 값만 쓴다(주 경로·폴백 둘 다). 루프 안 `send_qty` 대입은 정확히 2개다(AST A3 · AR5). `await place_order` 중 착지한 통보가 `pos.quantity` 를 먼저 깎으면, 발사 뒤 다시 읽은 값이 매핑에 적힌다. 그러면 잔여 통보가 overrun 클램프에 잘리고 유령 보유가 남는다.
- 🔴 **#1.5 재대조와 늦은 통보는 같은 체결을 두 번 빼지 않는다.** 재대조(`[sell_qty_reconciled]`)는 `pos.quantity` 를 잔고 스냅샷의 `held` 로 덮는다. 그 스냅샷에 이미 반영된 체결의 통보가 뒤에 오면 보유 축이 같은 체결을 또 뺀다. 그러면 추적이 실보유보다 작아진다. 그래서 재대조가 주문별로 「스냅샷에 이미 반영된 체결」을 크레딧으로 적고, 통보는 크레딧을 먼저 쓴다. 순서가 계약이다.
  | 1 | `get_balance()` — 시각 t1, `held`·`sellable`. `0 < sellable < 추적` 이면 아래로 간다 |
  | 2 | `_sell_orders_snapshot(ticker)` — `get_daily_orders(exchange="ALL", pdno=ticker)`(TTTC0081R) 1건. 반드시 1 **뒤**다. t2 ≥ t1 이어야 크레딧이 모자라지 않는다. 돌려주는 값 = `(fills, reason, pre)`. `reason` 은 `ok`·`error`·`timeout`·`bad_row`·`page_full` 이다. `pre` 는 원장 시작 전에 접수된 주문번호 집합이고, 실패 넷에서는 빈 집합이다(AST AR2-5 · AR2-6 · AR3-2) |
  | 3 | `strategy.state.positions.get(ticker) is pos` — 아니면 `[sell_qty_reconcile_skipped] reason=position_replaced` 후 `continue`. 닫힌 포지션을 `save_position` 으로 되살리지 않는다 |
  | 4 | `pending = _sell_pending_dec(fills, pre)` · `eff = pos.quantity − pending`(조회 실패면 `eff = pos.quantity`). `held ≥ eff` 면 아래 「부분 잠김 판매」로 가고, `held < eff` 면 5 로 간다 |
  | 5 | 크레딧 기록 — 조회가 되면 원장 시작 뒤 주문 `o` 마다 `c = 누적 체결 − _sell_notice_seen[o]`. `c > 0` 이면 `_sell_reflected_credit[o] = c`, 아니면 pop. 원장 시작 전 주문은 같은 `c` 를 상한 `_pre_cap` 까지만 적는다(아래 「원장 시작 전 주문」). 종목 크레딧은 지운다. 조회가 안 되면 종목 크레딧에 `max(0, pos.quantity − target_qty)` 를 **더한다** |
  - 3 부터 대입(6 의 `pos.quantity` 또는 부분 잠김의 `sell_cap`)까지 `await` 가 없다. 2 의 await 뒤에 수량 술어를 다시 보지 않는 이유 — 6 의 대입은 「t1 의 계좌 보유 = `held`, 반영됐지만 미처리인 통보 = 크레딧」이라는 절대 진술이라, await 동안 어떤 통보가 처리됐든 성립한다(명세 R-1-6). 그래서 재검증은 객체 동일성만 본다. `eff` 는 await 뒤 상태로 계산한다. t1 뒤 체결은 `pending` 에만 들어가 덜 쏘는 쪽으로만 작용한다(명세 R2-8).
  - `held < eff` 는 「원장 시작 뒤 주문으로 설명되지 않는 차이」(유령 보유 · 유실 통보 · 재시작 전 체결)다. 원장 시작 뒤 주문으로 설명되는 차이는 재대조하지 않는다 — 통보가 곧 뺄 몫을 `held` 로 덮으면 운영자 초과분까지 추적에 들어온다.
  - 🔴 주문 조회는 `asyncio.wait_for(…, timeout=SELL_ORDERS_QUERY_TIMEOUT)` 로 묶는다. `SELL_ORDERS_QUERY_TIMEOUT = 2.0`(초)은 모듈 상수다 — `DEFAULT_PARAMS`·`system_config` 키가 아니다. 손절 경로가 APBK0400 뒤 잔고 1건을 이미 기다린 상태라 더 기다리지 않는다. 넘으면 `reason=timeout` 으로 조회 실패와 같게 간다. `wait_for` 가 취소하는 것은 읽기 조회뿐이다.
  - 🔴 `exchange="ALL"`·`pdno=ticker` 는 키워드로 고정한다 — KRX 만 보면 NXT/SOR 체결을 놓쳐 크레딧이 모자란다(AST AR2-6).
  - 파서 `_sell_fills_by_order(rows, ticker, page_size)`(모듈 함수 · 순수 · never-raise) — 그 종목(`pdno`) 매도(`sll_buy_dvsn_cd == "01"`) 행만 본다. 같은 `odno` 의 여러 행(SOR)은 `tot_ccld_qty` 를 합한다. 통과한 행 하나라도 `odno` 가 비었거나 수량이 정수가 아니면 **전체 `None`** 이다. 행 수가 `page_size` 이상이어도(한 쪽이 가득 — 잘렸을 수 있다) `None` 이다. 부분 신뢰를 하지 않는 이유 — 한 주문이 빠지면 그 주문의 늦은 통보가 이중 차감된다.
  - 🔴 `page_size` 는 환경별이다 — `settings.is_production` 이면 `_DAILY_ORDERS_PAGE_REAL`(100), 아니면 `_DAILY_ORDERS_PAGE_VTS`(15)다(정본 `docs/kis/domestic-stock-order.md` — 실전 1회 100건 · 모의 15건). 인자에 기본값을 두지 않는다 — 기본값 하나가 곧 한쪽 환경의 잘림 오판이다.
  - 🔴 **종목 크레딧은 더한다(덮어쓰지 않는다).** 두 번째 재대조가 세는 몫은 첫 재대조 이후 새로 반영된 체결뿐이다. 덮어쓰면 첫 몫의 통보가 다시 빠져 과소 추적이 된다(AST AR2-4). 조회가 되는 재대조는 종목 크레딧을 버린다 — 주문별 크레딧이 그 몫을 대신한다.
  - 조회를 못 믿어도 재대조는 한다(`[sell_qty_reconcile_orders_unavailable]`). 재대조를 건너뛰면 오염된 포지션의 손절이 그 사이 멈춘다. 크레딧 없이 재대조하면 과소 추적이 된다.
  - `_handle_sell_fill` 은 통보마다 `_sell_notice_seen[주문]` 에 체결량을 더한다. 그리고 자기 주문 크레딧 → 종목 크레딧 순으로 흡수하고, 남은 `hold_dec` 만 보유에서 뺀다(`[sell_fill_credit_absorbed]`). 주문 크레딧은 자기 주문의 통보만 쓴다 — 우리 재발사 체결이 MTS 주문의 크레딧을 먹으면 유령 보유가 남는다. 원장과 흡수는 출처 · `pos` 유무 · 모호 여부와 무관하게 돈다. 소유 해석 뒤 첫 `await` 보다 앞이다(AST AR2).
  - 주문번호는 `_odno_key(s)`(앞 0 제거)로 맞춘다 — REST `ODNO` · 체결통보 · TTTC0081R `odno` 의 0-패딩 차이를 흡수한다. 포지션이 닫힐 때 그 종목 크레딧을 지운다. 다섯 구조(`_sell_notice_seen` · `_sell_reflected_credit` · `_sell_blind_credit` · `_manual_sell_orders` · `_selling_locked_wait`)는 `reset_daily_state()` 가 비우고, 같은 자리에서 원장 시작 시각을 그 순간으로 옮긴다(AST AR11 · AR3-1). 주문번호는 하루 단위로만 유일하다. 원장은 메모리에만 있어 재시작하면 빈다 — 그래서 아래 원장 시작 시각을 둔다.
  - 🔴 **원장 시작 전에 접수된 주문은 `pending` 에서 뺀다(원장 시작 전 주문).** `_sell_ledger_since` 의 뜻 = 「`_sell_notice_seen` 은 이 시각 **뒤**에 처리한 매도 통보를 빠짐없이 담는다」. `__init__`(프로세스 시작)과 `reset_daily_state()` 가 `datetime.now(_KST_TZ)` 로 적는다. 재시작하면 원장이 빈다. 빼지 않으면 그날 재시작 전 체결이 전부 `pending` 으로 잡혀 `eff` 가 작아지고, 손절이 매 틱 발사 없이 보류된다. 빼면 분기가 「보유 대 추적」 비교로 돌아가 재대조가 고친다.
    - 분류 = `_sell_orders_placed_before(rows, ticker, since)`(모듈 함수 · 동기 · never-raise, 예외 = 빈 집합). 그 종목 매도 행의 `ord_dt`(8자리) + `ord_tmd`(6자리)를 `_ord_datetime` 이 KST 시각으로 읽는다. 한 주문의 여러 행(SOR)은 가장 늦은 시각을 쓴다. 그 시각이 `since` 보다 **앞**(`<`)일 때만 넣는다. 🔴 한 행이라도 못 읽으면 그 주문은 「뒤」다 — `pending` 에 세어 덜 쏘는 쪽이다.
    - 🔴 **벽시계 게이트가 아니다.** 기록된 두 시각(원장 시작 · 그 주문의 접수 시각)을 비교할 뿐이고, 지금 몇 시인지는 판정에 쓰지 않는다. 테스트는 `_sell_ledger_since` 를 상수로 대입한다.
    - 원장을 「재시작 전 주문의 체결 = 다 봤다」로 채우지 않는다. 부팅은 복원 수량을 KIS 수량에 맞추지 않기 때문이다 — `boot_manager.py` 는 DB 행 수량을 그대로 쓰고, KIS 에 없는 종목의 행만 지운다. 그래서 복원 수량은 `save_position` 실패나 다운타임 체결만큼 KIS 와 다를 수 있다.
    - 🔴 **원장 시작 전 주문도 크레딧은 적되 상한을 둔다.** 크레딧에서까지 빼면, 재시작 뒤 체결돼 잔고에서는 빠졌는데 통보가 아직인 몫이 두 번 빠진다(과소 추적). 상한이 없으면 원장이 모르는 재시작 전 체결까지 크레딧이 되어, 그 주문이 계속 체결될 때 새 통보를 삼킨다(과대 추적). 상한 = `_pre_cap = max(0, pos.quantity − target_qty − 뒤 주문 크레딧 + _old_credit)` — 이번 재대조가 내리는 폭에 남은 크레딧을 더한 값이다. `_old_credit`(그 주문들의 기존 주문 크레딧 + 종목 크레딧)은 첫 덮어쓰기 **앞**에서 센다. 순서 = 뒤 주문 루프 → `_pre_cap` → 앞 주문 루프(`min(누적 체결 − _sell_notice_seen, _pre_cap)`)이다(AST AR3-5).
- 🔴 **외부 매도가 일부를 잠가도 안 잠긴 추적 잔여는 판다(부분 잠김 판매).** 4 에서 `held ≥ eff` 면 `surplus = held − eff` · `fire = sellable − surplus` 다. `held − sellable` 은 이 종목에 걸린 매도 전부다(우리 주문 · 수동 매도 · MTS, 매핑 여부 무관). 그래서 새 주문 + 걸린 주문 ≤ 추적이 되고, 우리가 이미 잠근 주식을 두 번 팔지 않는다. 주문 조회는 재대조와 **같은 1건**을 쓴다.
  - 🔴 **아직 안 온 외부 체결 통보를 먼저 뺀다.** `_sell_pending_dec(fills, pre)`(동기 · `await` 0) = 원장 시작 뒤 주문마다 `max(0, 누적 체결 − _sell_notice_seen − _sell_reflected_credit)` 의 합이다(`pre` 에 든 주문은 세지 않는다). 거래소는 체결했지만 추적에서 아직 안 빠진 수량이다. 빼지 않으면 surplus 를 작게 봐서 운영자 몫을 판다. 🔴 `max(0, …)` 는 **주문마다** 건다 — 합한 뒤 한 번 거르면, 주문 목록이 통보보다 늦은 주문의 음수가 다른 주문의 대기분을 지워 운영자 몫을 판다(AST AR3-3).
  - 🔴 종목 크레딧(`_sell_blind_credit`)은 `pending` 에서 빼지 않는다 — 유실 통보가 섞일 수 있어, 빼면 `eff` 가 커져 운영자 몫을 판다. 빼지 않으면 덜 쏜다(AST AR2-8).
  - 🔴 **주문 조회를 못 믿으면 쏘지 않는다**(`fire = 0` → 동결). 걸린 체결 통보와 운영자 초과분을 가를 수 없기 때문이다.
  - `fire ≥ 1` → `sell_cap = fire` 를 두고 재시도한다(`[sell_qty_partial_sellable]`). `pos.quantity` 는 바꾸지 않는다(C236-F1 — 잠긴 주식도 추적 보유다. 걸린 주문이 취소되면 다시 손절 대상이다).
  - `fire ≤ 0`(운영자 초과분이 걸린 주문을 덮는다 · 조회 실패) → 보존 · `_selling` 유지 · `_selling_locked_wait` 에 넣고 return 한다. 걸린 주문을 「운영자가 전략 몫부터 판다」로 읽는 보수 해석이다. 운영자 몫을 우리가 파는 쪽보다 낫다. 로그는 걸린 매도가 있는지와 주문 조회 성공 여부로 가른다(AST AR3-6 · AR4-2).
    - `held > sellable`(무엇이 걸려 있다) → `[sell_qty_partial_locked]`.
    - `held == sellable` ∧ 주문 조회 실패(`fills is None`) → `[sell_qty_hold_orders_unavailable]`. 진입 때는 `0 < sellable < 추적` 이었는데, 조회 `await` 동안 매도 통보가 추적을 보유 이하로 줄인 경우다. 조회를 못 믿으니 미통보 체결이 있는지 모른다. 그래서 「거래소가 확인한 미통보 체결」 문구를 쓰지 않는다.
    - `held == sellable` ∧ 주문 조회 성공 → `[sell_qty_unnoticed_fills]`. 원장 시작 뒤 주문의 미통보 체결이 추적 전부를 덮을 때다 — 거래소 기록으로는 전략 몫이 이미 다 팔렸고, 계좌에 남은 것은 운영자 몫이다.
    - 🔴 **걸린 매도가 없어도 보류한다**(명세 부록 R4 D1). 「걸린 것이 없으면 동결하지 않는다」를 글자대로 따르면 그 순간 재대조로 가서 계좌에 남은 운영자 몫을 판다.
    - 걸린 것 없는 보류를 푸는 주체는 셋이다 — 그 주문의 종료 통보 · 보유 닫힘(닫기 묶음의 동결 해제) · 통보가 유실되면 `selling_reconcile`. 이 보류는 늘 `held == sellable > 0` 이라 `selling_reconcile` 이 풀 수 있다. 「잠김」 문구는 이 두 경우에 뜨지 않는다.
- **J-2 — 손절 잔여 재주문 직전 보유 재조회.** `_cancel_and_reorder` 는 30초 전 스냅샷 `remaining` 을 그대로 쏘지 않는다. 마지막 `await`(CANCELLED 장부) 뒤, `place_order` 앞에서 `_reorder_requery(ticker, order_no, remaining)`(동기 · never-raise)가 registry 전수 보유를 다시 본다(AST A4).
  - 🔴 **보유에 맞추는 것은 상한이지 증액이 아니다**(`min(remaining, 보유)`). 보유로 올리면 운영자가 남기려던 수량까지 판다.
  - 🔴 **의심스러우면 쏜다** — 손절 잔여를 버리는 쪽이 더 비싸다. 과대 요청은 KIS 가 APBK0400 으로 막고 #1.5 가 흡수한다.
  - 🔴 **수동 매도 라우트 주문은 운영자 의도를 따른다.** 운영자가 누른 수량의 대상은 추적 밖 주식일 수 있어 `shrunk`·`gone` 을 적용하지 않는다. 표식은 라우트가 매핑과 같은 동기 구간에서 `_manual_sell_orders[order_no] = _added` 로 단다. 🔴 `strategy_id`·`_order_strategy` 로 추론하지 않는다 — 라우트는 보유 전략이 있으면 그 전략 id 를 적는다(AST AR9). 재주문 번호는 표식을 물려받는다(`_cancel_and_reorder` 결과 블록). 그래서 재주문이 또 부분 체결되면 다음 J-2 도 같은 규칙을 탄다. 과대 요청은 KIS 가 APBK0400 으로 막고 `_cancel_and_reorder` 의 `except` 가 흡수한다.
  - 취소(`cancel_order`)는 이 재조회와 무관하게 나간다. 그래서 재주문 타이머의 `qty_src == "map"` 게이트는 계속 필요하다(「체결통보 주문수량」 절).
- 🔴 **원주문을 취소했는데 우리 재주문이 확정적으로 안 걸렸으면 `_selling` 을 푼다.** 우리 것이 하나도 안 걸렸는데 표식이 남으면 잔여 보유의 손절이 `selling_reconcile` 까지 멈춘다. `_cancel_and_reorder` 는 태스크 자신이 한 일 두 가지를 `try` 앞에서 초기화한다 — `_cancel_ok`(원주문 취소 성공) · `_place_state`(`none` · `sending` · `accepted` · `rejected`). `finally` 가 한 번 판정한다(`await` 0, AST AR2-3).
  | 쌍 게이트 컷 · 원주문 취소 실패 · 취소 전 교체 취소 | 거짓 | `none` | 유지 — 원주문이 아직 걸려 있거나 이미 끝났다(끝났으면 그 통보가 푼다) |
  | 취소 성공 → 재주문 그 밖의 `KisApiError`(EGW00201 · APBK0918 보유 부족 문구 · 코드만 APBK0400 인 다른 문구 · 모르는 코드) | 참 | `sending` | 🔴 유지 — 앞 전송이 접수됐을 수 있다(아래) |
  | 취소 성공 → 재주문 전송 중 다른 예외(타임아웃 등) · 전송 중 교체 취소 | 참 | `sending` | 🔴 유지 — 거래소에 나갔을 수 있다. 풀면 다음 틱이 한 번 더 낸다. `selling_reconcile` 이 푼다 |
  - 🔴 **「안 걸렸다」는 `_sell_not_placed_reason(exc)` 한 곳이 가른다**(명세 부록 R4 D2). 모듈 함수 · 동기 · never-raise(예외 = `None`)다. 재주문과 수동 매도 라우트(`src/routes/CLAUDE.md` `manual-sell` 행)가 같은 함수를 쓴다. 분류는 `src.api.balance` 의 기존 판정 함수만 부르고 키워드를 다시 맞추지 않는다(AST AR4-1).
    | 2 | `is_market_closed_rejection` — 장운영시간 외 문구(프리마켓 문구는 두 분류기에 다 걸리고 여기서 끝난다 — `execute_sell` 과 같은 우선순위) | `market_closed` |
    | — | 그 밖 — `KisApiError` 가 아닌 예외(전송 오류 · HTTP 5xx · `RuntimeError`) · EGW00201 · APBK0918 보유 부족 문구 · 코드만 APBK0400 인 다른 문구 · 모르는 코드 | `None` = 「전송 중」 |
    - 왜 나머지는 「안 걸렸다」의 증거가 아닌가 — `src/api/base.py::_request` 는 주문 POST 도 전송 오류(`httpx.RequestError` — 타임아웃 포함)와 5xx 에서 다시 보낸다. KIS 거부(`rt_cd≠0`)는 다시 보내지 않는다. 그래서 거부 앞에는 전송 실패 시도만 있고, 그 시도가 응답만 잃고 접수됐을 수 있다. 풀면 다음 틱 손절이 걸린 재주문 위에 또 나간다.
    - APBK0400 이 안전한 이유 — J-2 `same`·`shrunk` 면 재주문 수량 R ≤ 추적 T 라, 숨은 재주문 옆에서 APBK0400 이 났다면 다음 틱의 첫 발사 T 도 APBK0400 을 받는다(명세 R3-2-3). 그 뒤 부분 잠김 판매가 걸린 재주문을 빼고 계산한다.
    - 장운영시간 외 · 시장가 불가가 안전한 이유 — 주문 자체의 결정적 거부다. 시각 · 호가유형 · 종목으로 정해지므로 같은 본문의 앞 시도도 똑같이 거부됐다. 남기면 걸린 주문 없는 `_selling` 좀비가 된다(루트 `CLAUDE.md` 「NXT 매도 거부 좀비 차단」 과 같은 원리). 앞 시도와 뒤 시도 사이에 장 경계가 끼면 성립하지 않는다(「알려진 한계」).
    - 🔴 분류는 msg1 문구 기반이다. 코드가 같아도 문구가 키워드에 없으면 `None` 이다 — 덜 푸는 쪽이다.
  - `except KisApiError` 본문은 `_sell_not_placed_reason` 판정 1회와 맨 끝 bare `raise` 뿐이다. `_cancel_and_reorder` 안에서 분류기 셋을 직접 부르지 않는다(AST AR2-3). 이 판정은 「무엇이 안 걸렸나」만 정한다. 「누구의 표식을 푸나」는 `finally` 의 해제 조건(아래)이 정한다.
  - 유지한 표식은 걸린 재주문의 종료나 `selling_reconcile`(열린 매도 0 · 180초)이 푼다.
  - 해제 조건의 마지막 항 = `ticker in self._selling_locked_wait or self._manual_sell_orders.get(order_no, True)`. 해제 시점에 읽는다. 자동 주문(표식 없음)과 표식이 참인 manual 은 참이다. **손님 manual**(`_added` 거짓 — 자동 매도가 `_selling` 주인)은 동결 표식이 서 있을 때만 참이다. 동결 표식이 서 있으면 `_selling` 은 우리 `execute_sell` 이 주문 없이 멈춰 세운 것이다. 원주문은 방금 취소됐고 재주문은 안 걸린 것이 확정된 거부로 끝났으니 우리 것이 아무것도 안 걸려 있다. 동결 표식이 없으면 자동 매도의 주문이 걸려 있어 풀지 않는다. 재주문 번호가 표식을 물려받으므로 그 재주문의 재주문도 같다.
  - 해제는 `_selling` · `_selling_since` · `_selling_locked_wait` 를 함께 비우고 `[reorder_selling_released]` 를 남긴다.
- **마커** — 전부 `logger.*` 만 쓰고 cap 이 없다(행위 밖).
  - `[sell_fill_holding_remains] order_no= ticker= owner= sold= held_after= ordered= src=` WARNING — 분할 매도의 성공 서명. `src=increment` 와 짝이면 주문 종료가 거짓일 수 있으니 `[fill_qty_src]` 와 대조한다.
  - `[sell_fill_exceeds_holding] order_no= ticker= owner= held_before= fill= src=` WARNING — `fill=` 은 `hold_dec` 다. 0 이 정상.
  - `[sell_fill_owner_from_holding] order_no= ticker= from=<sid|none> to=<sid> src=` WARNING — `from=none` = MTS·발사 창, `from=<sid>` = 장부 전략이 그 종목을 안 들고 있었다(이상).
  - `[sell_fill_owner_ambiguous] order_no= ticker= sid= holders=<csv|error> src=` ERROR — 0 이 정상, 1건이면 조사.
  - `[sell_fill_db_error] step=save_position ticker= order_no= owner= held_after= err=` ERROR — 하루 여러 건이면 RDS 를 본다.
  - `[sell_fill_credit_absorbed] order_no= ticker= fill= absorbed_order= absorbed_blind= hold_dec= src=` WARNING — 늦은 통보를 이중 차감하지 않은 건수.
  - `[sell_qty_reconciled]` WARNING — 문구 끝에 `credit_src=orders|blind credit_orders= credit_qty= pre_orders= pre_cap=` 가 붙는다. `credit_qty>0` 이면 재대조 순간 통보가 오는 중이었다. `pre_orders>0` 이면 원장 시작 전 접수 주문이 재대조에 섞여 크레딧 상한 `pre_cap` 을 적용했다.
  - `[sell_qty_reconcile_orders_unavailable] ticker= reason=error|timeout|bad_row|page_full blind_credit=` WARNING — 주문 목록을 못 믿어 종목 크레딧으로 갔다. `blind_credit=` 은 이번 재대조가 더한 몫이다. 0 이 정상.
  - `[sell_qty_reconcile_skipped] ticker= reason=position_replaced` INFO — 재대조 조회 중 포지션이 닫혔다.
  - `[sell_qty_partial_sellable] ticker= strategy= held= sellable= positions= surplus= fire= pending=` WARNING — 걸린 외부 주문 옆에서 잔여를 팔았다. `pending>0` 이면 아직 안 온 외부 체결 통보를 빼고 쐈다.
  - `[sell_qty_partial_locked]` WARNING — 걸린 매도가 있을 때(`held > sellable`)만 뜬다. 문구 끝에 `surplus= fire= pending=<n|?> orders=ok|error|timeout|bad_row|page_full` 가 붙는다. `orders` 가 `ok` 가 아니면 주문 조회를 못 믿어 동결했다.
  - `[sell_qty_unnoticed_fills] ticker= strategy= held= sellable= positions= pending= eff=` WARNING — 걸린 매도 없이 보류했다(주문 조회는 성공). 드물다. 같은 종목에서 `selling_reconcile` 해제 뒤마다 되풀이되면 통보 유실을 의심한다(계좌에 남은 것은 운영자 몫이라 팔지 않는다).
  - `[sell_qty_hold_orders_unavailable] ticker= strategy= held= sellable= positions= orders=error|timeout|bad_row|page_full` WARNING — 걸린 매도 없이 보류했는데 주문 조회를 못 믿었다. 드물다. `orders=` 는 조회 실패 이유다.
  - `[reorder_selling_released] ticker= order_no= place=none|rejected reject=qty_exceeded|market_closed|market_order_disallowed|-` WARNING — 원주문 취소 뒤 우리 재주문이 안 걸려 `_selling` 을 풀었다. `reject=` 는 `_sell_not_placed_reason` 의 이유다. `place=none` 이면 `-` 다. 드물다.
  - `[selling_freeze_released] ticker= order_no= reason=position_closed` INFO — 동결이 지키던 보유가 닫혀 동결을 풀었다.
  - `[reorder_requery] verdict= ticker= order_no= remaining= held= fire_qty=` — `same` 은 INFO, `manual` 은 위 표, 그 밖은 WARNING.
  - 「매도 부분 체결」 INFO 끝의 `held_after=` — 부분 체결마다 남은 보유.
  - **무관한 주문의 종료가 `_selling` 을 푼다.** 우리 손절 주문이 걸려 있는 동안 MTS 주문이나 손님 수동 매도가 끝나면 표식이 풀리고, 다음 틱 손절이 추적 잔여를 또 낸다. 계좌에 운영자 초과분 ≥ 추적 잔여이면 그 발사가 통과해 운영자 몫을 판다. 초과분이 없으면 KIS 가 APBK0400 으로 막는다. 막는 수단은 「걸린 우리 매도 등록부」(후속 F-385-5)다. strict xfail 테스트가 이 성질을 적어 둔다 — `tests/unit/engine/test_cycle385r2_round2.py` TQ22 · `tests/unit/engine/test_cycle385r_partial_locked_sell.py` TR18 · `tests/unit/routes/test_cycle385_manual_sell_selling.py` TR20 · TR20b. TR18·TR20 은 마커가 아니라 행위를 단언하므로, 이 한계가 고쳐지면 XPASS 로 붉어진다. `increment` 퇴화(`fields[16]` 없음)에서 우리 주문의 발사 창 첫 통보가 거짓 「종료」를 만들 때도 결과가 같다.
  - **과대 추적은 운영자 초과분이 있으면 운영자 몫 매도로 번진다.** 과대 추적은 보통 다음 매도의 APBK0400 → #1.5 가 회수한다. 그 사이 계좌에 운영자 몫이 있으면 APBK0400 이 나지 않고 그 몫이 팔린다. 과대 추적이 생기는 곳은 넷이다.
    - 재대조의 두 조회 사이(수백 ms)에 난 체결.
    - 종목 크레딧(주문 조회 실패)이 유실 통보분이나 진짜 유령분까지 들고 있다가 뒤 통보를 흡수한 몫. 우리 매도 체결도 흡수 대상이라 우리 매도가 다 끝나도 추적이 남는다. 그 뒤 운영자가 같은 종목을 사면 남은 추적만큼 손절이 판다. strict xfail `tests/unit/engine/test_cycle385r3_round3.py` TK13 이 적어 둔다.
    - 원장 시작 전 접수 주문의 재대조 크레딧. 상한 `_pre_cap` 은 주문마다 걸려 합은 참값을 넘을 수 있다(명세 R3-13-4).
  - 부분 잠김 판매의 `eff` 도 위 첫째·둘째와 같은 폭만큼 참값보다 클 수 있다. 그만큼 surplus 를 작게 봐서, 운영자 초과분이 있으면 운영자 몫을 판다.
  - **원장 시작 전 접수 주문이 재시작 뒤에도 체결 중이고 통보가 늦으면** 그 체결이 `pending` 에서 빠진 만큼 `eff` 가 크다. 운영자 초과분이 있으면 부분 잠김 판매가 그만큼 더 쏜다(명세 R3-13-2).
  - **접수 시각을 못 읽는 행은 「뒤」다.** 그 주문이 재시작 전 것이면 재시작 뒤 손절이 `[sell_qty_unnoticed_fills]` 로 보류된다(돈은 안전한 쪽이다). KIS 가 필수 필드 `ord_dt`·`ord_tmd` 를 비울 때만 생긴다. 운영 TTTC0081R 캡처에서 두 필드가 8·6자리 숫자인 것은 매수 행으로만 확인했다 — 매도 행과 SOR 부모·자식 행의 `ord_tmd` 는 재지 않았다(명세 R3-12 F-R3-1).
  - **다운타임 체결**(프로세스가 죽은 동안의 체결 — 통보 없음)은 복원 수량에 없다. 운영자 초과분이 그 양 이상이면 재시작 뒤 첫 발사가 통과해 운영자 몫을 판다.
  - **재시작으로 잃은 통보**(전송 중 · 다운타임)는 원장도 크레딧도 모른다. 유령 보유(과대 추적)가 남을 수 있고, 그 보유가 `held_zero` 면 `selling_reconcile` 이 `_selling` 을 풀지 못한다. 과소 추적은 만들지 않는다(명세 R3-1-7 완전 재시작 모의).
  - **통보 유실 유령** — 원장 시작 뒤 주문의 체결 통보를 잃고 운영자 초과분이 있으면, `[sell_qty_unnoticed_fills]` 보류가 `selling_reconcile` 해제 뒤마다 되풀이된다(APBK0400 1회 + 조회 2회). 계좌에 남은 것은 운영자 몫이라 돈 손실은 없다.
  - **재주문 해제의 남는 틈** — 셋 다 첫 항목(우리 주문이 `_selling` 없이 걸림) 모양이다.
    - ① 앞 전송 접수(응답 유실) + 재전송 APBK0400 인데, 숨은 재주문의 부분 체결 통보가 다음 틱 **전**에 착지하면 추적이 재주문 수량 아래로 내려가 APBK0400 보장이 풀린다. 운영자 초과분이 있으면 그 몫이 팔린다(명세 R4-4 R4-1).
    - ② J-2 `manual`·`ambiguous`·`error` 재주문은 수량이 추적을 넘을 수 있어 같은 보장이 없다(명세 R3-2-3).
    - ③ **장 경계를 가로지른 재시도** — 앞 시도가 경계 앞에서 접수되고 응답만 잃은 뒤, 재시도가 경계 뒤에서 장운영시간 외·시장가 불가로 거부되면 걸린 주문 옆에서 `_selling` 이 풀린다(명세 R4-1). 닿는 경계는 NXT 15:20 하나다. NXT 로 라우팅된 수동 매도와 NXT 원주문의 재주문만 해당하고, NXT 잔량은 20:00 까지 남는다. 다음 KRX 손절은 운영자 초과분이 걸린 수량 이상일 때만 통과한다. 검토가 본 다른 경계(15:30 KRX · 20:00 · NXT 프리장)는 해당하지 않는다 — 15:30~16:00 은 `_market_rest_gate` 가 자동 매도를 막고 그 사이 걸린 주문이 종가 체결되거나 자동 취소된다.
  - **교체된 재주문 타이머가 손님 수동 매도 옆에서 `_selling` 을 푼다**(명세 R4-4 R4-7). 손님 수동 매도(`_added` 거짓)가 걸린 동안, 자동 매도 원주문을 취소한 재주문 태스크가 CANCELLED 장부 `await` 창(ms)에서 다음 부분 체결 통보에 교체 취소되면, `finally` 가 `place=none` 으로 표식을 푼다. 다음 손절이 걸린 수동 매도 위에 쌓인다. 운영자 초과분이 쌓인 몫보다 작으면 운영자 몫이 팔린다. 첫 항목과 같은 계열이다.
  - **수동 매도가 발사 여부를 모르는 이유로 실패하면 `_selling` 이 남는다.** EGW00201 · 전송 예외 · 모르는 코드 · 보유 부족 문구는 앞 전송이 접수됐을 수 있어 풀지 않는다(`[manual_sell_selling_kept]`). 그동안 그 종목 자동 손절이 그 주문의 종료 통보나 `selling_reconcile`(15분 sync + 180초, 09:30 전에는 sync 가 돌지 않는다)까지 멈춘다(`src/routes/CLAUDE.md` `manual-sell` 행).
  - 주문 조회 실패 중 운영자 초과분이 있으면 재대조가 초과분을 추적에 받아들일 수 있다(명세 R-13-8).
  - 혼합 보유(전략 추적분 + 추적 밖 수동 매수분)의 수동 부분 매도는 전략 보유에서 빠진다 — 주식은 구별되지 않는다. 추적분이 닫힌 뒤 sync 가 나머지를 다시 채택한다.
  - 우리 주문이 통보 없이 사라지면(MTS 로 우리 주문 취소 · 거래소 자동취소 · 접수 뒤 거부) `_selling` 은 `selling_reconcile` 이 풀 때까지 남는다. 09:30 전에는 sync 가 돌지 않는다. 동결이 기다리던 외부 주문이 통보 없이 사라져도(운영자가 앱에서 취소) 같다.
  - `_selling` 에 주인 식별자가 없다. 해제하는 순간의 표식이 다른 코루틴이 새로 세운 것일 수 있다(첫 항목 경로로 한 번 풀린 뒤에만). 재주문 해제와 수동 매도 라우트의 되돌림도 표식의 주인을 보지 않는다. 결과는 첫 항목과 같다.
  - 주문번호 형식(0-패딩)과 SOR 주문의 TTTC0081R 행 모양은 운영에서 재지 않았다(명세 R-14 F-R1·F-R3). SOR 행에 부모·자식 합계 행이 섞이면 파서의 합산이 이중 계산이 된다.
  - `trade_history.profit_loss` 는 여러 통보로 끝나는 주문에서 마지막 증분으로 덮인다(`update_trade_status` 가 SET 한다). `daily_realized_pnl`(메모리)은 증분 합이라 정확하다.
- 명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md`(부록 R · R2 · R3 · R4 포함) · 회귀 = `tests/unit/engine/test_cycle385_b7_partial_sell.py` · `tests/unit/engine/test_cycle385_reorder_requery.py` · `tests/unit/engine/test_cycle385r_recount_credit.py` · `tests/unit/engine/test_cycle385r_partial_locked_sell.py` · `tests/unit/engine/test_cycle385r2_round2.py` · `tests/unit/engine/test_cycle385r3_round3.py` · `tests/unit/engine/test_cycle385r4_round4.py` · `tests/unit/routes/test_cycle385_manual_sell_selling.py` · AST = `tests/unit/ast/test_cycle385_ast_b7.py`


## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관 (뒤쪽 절반: 「체결단가 정합」 ~ 파일 끝)

> 사용자 요청 「유지해야할 내용도 전반적으로 압축하자」에 따른 /sync-docs 2차 압축(압축만 — 정정 없음).
> 아래는 2차 압축으로 정본에서 바뀌거나 빠진 **원문 줄 그대로**다(1차 반영본 기준, 정본에 글자 그대로 남지 않은 줄 전부).
> 정본은 같은 규칙·조건·식별자를 짧게 다시 적었다. 근거 서사(042700 · 161580 · 257720 · 4일 무경보 등)·대안 비교·판독 보조 설명·같은 파일 안 반복 설명·회귀 테스트 파일 전체 목록은 여기에만 남는다.

### 출처 절: 체결단가 정합 (`_handle_buy_fill` / `_handle_sell_fill`)

- `update_trade_status` 호출은 항상 **`price=`** 를 넘긴다 — 체결단가는 체결통보 `CNTG_UNPR`(`handler.py` 의 `fields[10]`)이고, 주문 응답(TTTC0011U/TTTC0012U)에는 `KRX_FWDG_ORD_ORGNO`·`ODNO`·`ORD_TMD` 3키뿐 **체결가가 없다**. 안 넘기면 PENDING INSERT 시점의 `record_price`(LIMIT 주문가 / MARKET 은 scanner `current_price`)가 그대로 남는다.
- 호출부 6곳(C1~C6)은 전부 **`order_no=order_no`** 를 함께 넘겨 WHERE 를 그 주문 행으로 좁히고, 전량 체결 분기 2곳은 **`match_partial=True`** 로 PARTIAL 행까지 포괄한다.
- 가드 = AST G-161-K-6(`_handle_buy_fill` 영역의 `update_trade_status` 호출에 `price=` 키워드 의무) + `test_cycle273b_ast_no_behavior_guards.py` AST1/AST2.
- **PARTIAL·CANCELLED `affected==0` 관측 (cycle358)** — COMPLETED 는 `affected==0` 이면 보정 INSERT/강제 UPDATE 로 스스로 흡수한다. PARTIAL·CANCELLED 4 호출부(매수·매도 × PARTIAL·CANCELLED)는 흡수 경로가 없으므로, `affected==0` 이면 `_emit_trade_status_update_miss`(`_trade_status_update_miss_logged: KstDailyEmitCap` 1회/(order_no, status)/일)가 `[trade_status_update_miss] status=PARTIAL|CANCELLED order_no= ticker= side=` WARNING 1줄을 낸다. 관측 전용이고 never-raise 다 — 로그 실패는 `observer_trace.trace_observer_failure` 로 흡수하고 주문 흐름을 끊지 않는다(행위는 cap 밖).

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369)

관리종목·단기과열로 지정된 종목은 보유 중이면 시장가로 판다. 그날은 어느 전략도 그 종목을 새로 사지 않는다(사용자 결정 2026-09-25·26). 설계 정본 = `_workspace/domain_consult/cycle369_status_51_59_exit.md` · 명세 = `_workspace/red/cycle369_status_exit_spec.md`.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 판정 — `classify(output) -> StatusRead` (순수 · never-raise)

- 소스는 REST `FHKST01010100` 응답 하나다. 조회는 `condition.fetch_stock_detail` 만 쓴다(시세 풀 · 5초 캐시 · 단일 비행). leaf 는 `kis_*` 를 직접 부르지 않는다(AST F6).
- 전용 플래그 = `mang_issu_cls_code`(관리) · `short_over_yn`(단기과열 **지정·연장** — 예고는 `N`). 값은 `.strip().upper()` 뒤 `"Y"`/`"N"` 만 유효하다. 그 밖의 문자열은 `None` 으로 보고 `[status_exit_unknown_value]` 를 남긴다.
- 🔴 **종목상태(`iscd_stat_cls_code`) 51·59 는 전용 플래그가 비었을 때만 쓴다** — 명시 `"N"` 을 iscd 가 뒤집지 못한다. 둘이 어긋나면 플래그를 따르고 `[status_exit_iscd_conflict]` 를 남긴다. 종목상태 칸은 값을 하나만 담아서 51 만 보면 관리종목 약 절반을 놓친다(58·00·59 로 가려진다).
- 🔴 **매도는 전용 플래그가 `"Y"` 일 때만 쏜다(`dedicated_flagged`).** 종목상태 폴백만으로 해당이면 `fallback_only` 다 — arm 하고 `[status_exit_fallback_only]` 를 남기되 주문은 내지 않는다. 이유 = cycle203 실측 「51 = 정상 ETF·스팩·우선주」(`scanner.py` 의 사이클 203 주석). 잘못 판 매도는 되돌릴 수 없다. **매수 차단은 폴백도 쓴다** — 막는 쪽이 안전한 방향이다.
- 🔴 **판정에 쓰지 않는 것** — `ssts_hot_yn`(공매도과열이지 단기과열이 아니다) · master `short_over_cls_code`(`1` 은 예고다) · `stock_master.raw`/`master_raw` DB 값(하루 늦어 해제된 종목을 판다) · `H0UNMKO0` 프레임 단독. 프레임은 `market_operation_monitor.get_last_event` 를 **읽기만** 해서 `[status_exit_frame_hint]` 로 남긴다.
- 「모름」은 「해당 없음」이 아니다. 응답 실패·빈 output(`fetch_fail`) · `stck_prpr` 이 양의 정수가 아님 · 전용 플래그가 비고 iscd 폴백도 안 걸림(`flags_missing`)은 판정하지 않는다.
| 매수 차단 | 해당(폴백 포함 · 정지·가격 무관 — 막는 쪽이라 보수적) | `fetch_fail` · (`flags_missing` ∧ ¬해당) |
`_sell_verdict` 의 판정 순서가 계약이다 — `fetch_fail` → 해당 ∧ `halted` → 전용 `Y` ∧ 가격 유효 → 폴백만 해당 → 가격 무효·`flags_missing` → 해당 없음(`none`).

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 보유 청산

- 대상 = `registry.all()`(**꺼진 전략 포함**)의 `quantity > 0` 포지션이다. `risk.on_tick` 은 켜진 전략만 돌아서 꺼진 전략의 보유는 아무도 안 보기 때문이다. 종목당 조회는 1회, 판정은 (전략, 종목)마다 한다.
- 🔴 **발사 창 = `FIRE_WINDOW_START`(09:00:30) ≤ now < `FIRE_WINDOW_END`(15:28:00) KST** 이고, 창 안에서 **그 패스가 읽은 값**으로만 발사한다. 창 밖은 주문을 내지 않는다. 프리장은 `execute_sell` 이 NXT 지정가로 바꿔 미체결 `_selling` 이 남을 수 있다. **16:00~20:00 KRX 애프터마켓은 단기과열종목을 거래 대상에서 뺀다**(KRX 규정 — 관리종목 제외는 보도 수준). 거기서 내면 44/41 연속 거부 → 포기 래치 + CRITICAL 이다.
- 발사 = `await asyncio.shield(order_engine.execute_sell(t, Signal.STATUS_EXIT, sid))`. `limit_price` 인자가 없으니 시장가다. 거래소는 `execute_sell` 이 정한다(09:00~20:00 `krx_by_clock` → KRX). 거부 처리(APBK1943 지정가 5호가 폴백 · APBK0918 포지션 보존)는 `execute_sell` 의 기존 규약을 그대로 탄다.
- 🔴 **`execute_sell` 은 `asyncio.shield` 안에서만 부른다**(AST F8c). `stop()` 이 패스 task 를 취소해도 이미 제출 중인 주문은 끝까지 간다 — 매핑·PENDING 없이 나가는 반쪽 주문을 막는다. 패스 쪽에는 `CancelledError` 가 그대로 전파된다.
- 발사 조건 = 모드 `enforce` ∧ 판정 `fire` ∧ `t not in order_engine._selling`(읽기만) ∧ 그날 그 종목 발사 횟수 < `MAX_FIRES_PER_DAY`(3) ∧ **발사 직전에 다시 본 창 안** ∧ **발사 직전에 다시 읽은 모드가 `enforce`**. 횟수가 차면 `[status_exit_giveup]` CRITICAL 1회/일. 카운터 키가 `(날짜, 종목)` 이라 `_reset_daily_state` 는 무접촉이다.
- 🔴 **발사 순서가 계약이다** = 창 재확인(`_now_kst()`) → 모드 재확인(`_modes["sell"]`, 메모리 읽기 한 번 · `await` 0) → 발사 횟수 증가 → `[status_exit_fire]` logger WARNING(동기) → `execute_sell`.
  - 창 재확인이 카운터·마커·주문보다 **앞**인 이유 = 조회가 늦어 15:28 을 넘긴 종목은 쏘지 않는데, 뒤에 두면 그 미발사가 하루 3회 상한을 축낸다.
  - 모드 재확인 덕에 앞 종목의 조회나 `execute_sell` 을 기다리는 동안 온 `PUT sell_mode=off` 는 그 뒤 종목부터 먹는다. `observe` 가 오면 `[status_exit_would_fire]` 로 돌린다.
  - 횟수 증가가 `execute_sell` await **전**이라 매 패스 예외가 나도 3회 상한과 giveup 이 살아 있다. 발사 예외는 흡수해 `[status_exit_fire_error]` 를 남긴다(`CancelledError` 는 전파).
- 🔴 **청산 패스는 `system_logs` 를 직접 쓰지 않는다** — `await` 도 fire-and-forget 도 없다(AST F8b). 느린 RDS 가 뒤 종목의 시장가 매도 시각을 15:28 밖으로 밀면 안 되기 때문이다. `[status_exit_fire]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 의 영속은 루트 `_DbLogHandler`(`src/main.py`)가 한다 — `src.*` 로거의 INFO 이상을 큐에 넣고(`put_nowait` — 동기·non-blocking) 별도 task 가 `[src.engine.status_exit_watch] <메시지>` 한 줄로 적는다. 🔴 같은 메시지를 `write_log` 로 또 쓰지 않는다 — 사건당 두 줄이 된다(cycle72 G-6 · leaf 판 AST F3b). leaf 는 태스크·타이머를 하나도 만들지 않는다(AST F8).
- **재시작해도 하루 3회 상한이 이어진다** — `task_loop` 가 시작할 때 오늘(KST) `[status_exit_fire]` 행을 `system_logs.search_logs` 로 읽어(읽기 전용) 종목별 발사 횟수를 되살리고 메모리 카운터와 `max` 로 합친다. 행은 메시지 **어디든** `[status_exit_fire]` 를 담는지로 고른다(핸들러 줄은 접두가 붙어 `startswith` 로는 못 찾는다). 횟수는 행 수가 아니라 행 `attempt=` 의 **종목별 최댓값**이다(n 번째 발사의 `attempt` = 그때까지의 누적). `[status_exit_fire_error]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 은 그 부분 문자열을 담지 않는다. 조회 실패 = DEBUG `[status_exit_fire_seed_failed]` 뒤 메모리 카운터만으로 돈다(fail-open).
- ⚠️ 발사 기록의 영속 경로는 핸들러 한 줄뿐이다. 핸들러 큐(`maxsize=10_000`)가 가득 차 그 줄을 버리면 흔적 없이 사라지고(never-raise), 그 발사는 재시작 시드에 잡히지 않는다.
- **재시작 뒤 걸려 있는 59 청산 주문** — 재시작하면 `_selling` 이 비고, 부팅은 거래소에 걸린 매도 주문으로 그것을 되살리지 않는다. 그래서 이전 청산 주문이 아직 걸려 있으면(단기과열 30분 단일가) 첫 청산 패스가 한 번 더 쏜다. 그 주문은 `APBK0400`(요청 수량 > 매도가능수량, `docs/kis/error-codes.md`)으로 거부되고, `execute_sell` #1.5 재대조가 `sellable == 0 ∧ held > 0` 을 보고 `[sell_qty_locked]` 로 끝낸다 — **포지션은 보존**, `_selling` 은 **유지**(아래 「order_engine.py」 절)라 이후 패스는 그 종목을 건너뛴다(`t in _selling`). 걸린 주문은 체결되면 체결통보가, 만료되면 `selling_reconcile`(180초 age gate · 열린 주문 검사)이 수습한다 — 두 번 팔리지 않는다. 거부된 그 발사도 하루 3회에 센다.
- ⚠️ **특별 개장일(지연 개장 — 수능일이 표준 사례)** — 발사 창은 고정 시계(`FIRE_WINDOW_START`~`FIRE_WINDOW_END`)라 그날 장 시간을 모른다. 09:00:30 이 아직 정규장 전이면 거부된 발사가 하루 3회를 개장 전에 소진해 `[status_exit_giveup]` CRITICAL 이 날 수 있다(발사 횟수는 주문 결과와 무관하게 오른다). 15:28 뒤로 늦게 닫히는 장도 보지 않는다. **운영자 조치** = 그날 개장 전에 `PUT /api/integrations/status-exit {"sell_mode":"off"}`(또는 `observe`)로 내리고, 정규장이 열린 뒤 `enforce` 로 되돌린다. 같은 한계가 `_market_rest_now` 에도 있다(아래 「order_engine.py」 규칙 3).
- 정지(58·임시정지)가 겹치면 기다린다(`[status_exit_wait_halt]` 1회/일). 풀리는 다음 패스에서 판다 — 주문을 반복해 넣지 않는다. 폴백만 해당인 종목이 정지 중이어도 `wait_halt` 다(판정 순서상 정지가 먼저다).
- 청산 패스는 지금 보유하지 않는 `(종목, 전략)` 을 `_armed` 에서 뺀다 — 같은 날 판 종목이 「매도 대기」로 보이지 않게 한다.
- 🔴 **새 취소·재주문 타이머를 만들지 않는다**(AST F8 — 태스크·타이머 0). 단기과열은 30분 단일가라 시장가도 다음 :00/:30 까지 기다린다. 그 대기는 `selling_reconcile` 이 열린 매도 주문을 보존(`open_order` 유지)하는 것으로 이미 견딘다.
- 🔴 **익일청산 큐 `_pending_next_day_clear` 를 재사용하지 않는다**(AST F9). 그 경로는 한 번 쏘면 결과와 무관하게 항목을 지워 정지 대기·재시도 규칙과 맞지 않는다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 당일 매수 차단 (지정 첫날 포함)

- 규칙 = 그날(KST) **장중** 라이브 조회에서 해당이면, 그날 그 종목의 신규 매수 신호를 **7전략 전부**에서 막는다. 매일 새로 읽으므로 지정 첫날(T+1)부터 막힌다 — 진입 필터 `_is_master_blocked_for_entry` 는 T일 16:10 갱신값이라 첫날을 못 본다.
- 막는 자리 = `StrategyBase._account_soft_gate_blocked` 의 **첫 문장** `if self._status_buy_blocked(ticker): return True`(AST J25). 7전략 `check_buy_signal` 이 이미 이 공통 게이트를 거치므로 새 전략도 자동으로 따라온다. 게이트 위치(폴·래치형 5전략 첫 문장 / momentum·VB 발사 직전)도 그대로 물려받는다.
- `_status_buy_blocked` → `status_exit_watch.buy_gate(ticker, strategy_id, *, cand)` 는 **순수 메모리 조회**다(`await`·DB·HTTP·`write_log` 0 — AST J23). 판정 예외는 `False`(fail-open) + DEBUG `[status_block_gate_failed]`.
- 🔴 **막는 순간 그 전략의 그 종목 edge 기준가를 비운다**(`StrategyBase._clear_edge_baseline_on_block`, 순수 메모리 · `await` 0 · never-raise). 첫 문장 게이트인 LTV 는 차단 동안 `_prev_price` 갱신이 멈춰, 안 비우면 해제 뒤 첫 틱이 옛 기준가 대비 거짓 돌파가 된다. 비운 뒤 첫 틱은 기록만 하고 돌파로 읽지 않는다. 대상은 **모양으로** 고른다(전략 이름 하드코딩 없음) — 중첩 `_prev_price[t]`(VB·LTV `{board: price}`)와 momentum `_prev_prdy_rate[t]` 만 비운다. 🔴 평평한 `_prev_price`(BFB·VCP `{ticker: price}`)는 건드리지 않는다 — 비우면 없는 값이 `0` 으로 읽혀 `0 < level <= current` 가 새 거짓 돌파가 된다. `observe`·`off` 에서는 게이트가 `False` 라 비우지 않는다.
- `cand`(이 전략이 지금 이 종목을 후보로 드는가)는 **집계만** 가른다 — 막는 판정은 `cand` 와 무관하게 같다. `cand` 가 참일 때만 `_skip_counts` 를 올리고 `[status_block_buy_skip]` 을 남긴다. 판정 = `StrategyBase._is_status_gate_candidate` — momentum·VB(`_ALWAYS_STATUS_GATE_CANDIDATE_SIDS`)는 게이트가 발사 직전이라 항상 참이고, 나머지는 `get_scanned_tickers()`·`_targets`·`_candidates` 멤버십이다.
- 🔴 **수량 0 반환으로 막지 않는다** — 신호 단계에서 끝나야 `calc_buy_quantity`·`_apply_budget_limit` 이 불리지 않고 「매수 수량 0 → 900s cooldown(투자금 부족)」 오귀인도 생기지 않는다. 🔴 `registry.is_ticker_blocked_for_buy`(8영역)에도 넣지 않는다 — `risk.on_tick` 에서 `check_buy_signal` **앞** `continue` 라 기준가가 얼고, 스윙 폴 조회가 빠져 관측 훅도 못 탄다.
- 판정은 청산과 달리 **종목상태 폴백도 쓴다**(`flagged`) — 매수를 막는 것은 안전한 방향이다.
- 🔴 **못 읽은 종목은 막지 않는다(fail-open)** — 시세 풀 장애 하나로 7전략 매수가 조용히 멈추면 안 된다. 새는 경우는 청산 패스가 다음 칸(≤300초)에 팔고 `[status_exit_fire] bought_today=1` 로 드러난다.
- 판정 완료는 **장중(≥09:00:00) 조회만** 인정한다 — 장 전 값은 전날 것일 수 있다. 장 전 해당은 `phase=pre` 차단을 걸고(보수적), 장중 clean 이면 푼다(`[status_block_released] reason=pre_session_stale`). 장중 해당(`phase=in`)은 그날 풀리지 않는다(`[status_block_flip_ignored]`).
- 수명 = 항목에 담긴 KST 날짜. 날짜가 다르면 게이트가 무시한다(지연 만료). `_reset_daily_state` 는 무접촉이다.
- **하루 상태는 전부 날짜를 담는다** — `_buy_flags`·`_pre_seen`·`_in_seen`·`_armed`·`_passes` 는 값에, `_unknown_attempts`·`_fires`·`_skip_counts`·`_emitted` 는 키에. 읽는 쪽이 날짜로 거르고, P0 가 시작할 때 `_purge_stale_day(오늘)` 로 다른 날 항목을 전부 지운다(프로세스 수명 동안 자라지 않게).
- 막지 않는 것 = 청산·손절·트레일링·익일청산·15:20 강제청산(게이트가 `check_buy_signal` 안에만 있다) · 구독.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 언제 읽나 — `task_loop(sched)` + 관측 훅

| P0 | `PRE_PASS_TIME` 08:45. enabled 전략의 `tradable_boards` 에 `pre_nxt` 가 있으면 `PRE_PASS_TIME_NXT` 07:59(`pre_pass_time(registry)`). `BUY_OPEN_TIME`(09:00:00) 전까지 | 보유(청산 `off` 면 빼고) ∪ `buy_targets`(매수 차단 `off` 면 빼고). 장 전 기록·arm 만 한다(주문 0) |
| P1 | `_p1_start_time()` = `BUY_OPEN_TIME` + `condition._PRICE_CACHE_TTL` = **09:00:05**, 날마다 1회 | `buy_targets(registry, exclude_swing=True)` − 오늘 장중 판정 완료 − 모름 `MAX_UNKNOWN_ATTEMPTS`(3회) 소진 종목, `_p1_order` 순서. 벽시계 상한 `P1_WALL_CLOCK_MAX_S`(25초) — 넘으면 `truncated=1` 로 나머지를 INC 에 넘긴다 |
| INC | P1 뒤 `INC_INTERVAL_S`(60초)마다, `< INC_END_TIME`(15:20) | `buy_targets(registry)`(스윙 포함) − 오늘 장중 판정 완료 − 모름 3회 소진 종목 |
| 청산 | 창 안 첫 반복에서 즉시 + 격자 `09:00:30 + k·SELL_INTERVAL_S`(300초) | 보유 |
- `buy_targets(registry)` = enabled 전략의 `get_scanned_tickers()` ∪ `_targets` 키 ∪ `_candidates` 키 ∪ (momentum 이 enabled 면) `scanner.ticker_prev_close` 키 − `registry.is_ticker_blocked_for_buy` − 6자리 숫자가 아닌 것. 순서(`_GROUP`) = momentum 급등 목록 → VB·LTV → BFB·VCP → donchian·kojiro, 같은 순위는 종목코드 순. VB·LTV 가 BFB·VCP 보다 앞인 이유 = BFB·VCP 첫 매수는 운영 DB `entry_start` 09:05 라 여유가 있고, VB·LTV 는 09:00:35 부터 산다.
- 🔴 **P1 은 09:00:05 에 시작한다** — `condition` 의 5초 캐시가 08:59:55~09:00:00 조회를 돌려주면 장 전 값이 「장중 clean」 으로 봉인된다. 캐시 TTL 을 바꾸면 P1 시각도 따라 바뀐다(TTL 조회 실패는 5.0초로 계산).
- 🔴 **P0 창의 끝은 P1 시작(09:00:05)이 아니라 `BUY_OPEN_TIME`(09:00:00)이다** — `due_actions` 의 `pre_time <= t < BUY_OPEN_TIME`. 09:00:00~05 에 시작한 루프가 P0 를 돌면 같은 봉인이 생긴다 — `/api/trading/restart` 는 condition 5초 캐시를 비우지 않아, P0 가 08:59:5x 캐시의 장 전 clean 값을 `now ≥ 09:00` 으로 기록하면 「장중 clean」 이 되고 P1 은 그 종목을 건너뛴다. 그래서 그 5초 동안은 어떤 패스도 돌지 않고, P1 이 그 종목을 새로 읽는다. 보유 종목은 09:00:30 청산 패스가 읽으므로 잃는 것이 없다.
- **P1 은 스윙(donchian·kojiro)을 읽지 않는다**(`exclude_swing=True`). 스윙 매수 폴(09:05~09:30)이 매수 평가 직전에 같은 조회를 하고 관측 훅이 그것을 기록하므로, P1 의 25초 예산을 거기 쓸 이유가 없다. 스윙 후보는 P0·INC·관측 훅이 계속 읽는다. 걸러내는 자리는 momentum 급등 목록을 채운 **뒤**다 — 앞에서 거르면 `ticker_prev_close` 에 같이 든 스윙 종목이 momentum 몫으로 다시 들어온다.
- **P1 순서 `_p1_order`** — `scanner.ticker_prices[t]["prdy_ctrt"]`(읽기만)가 +29% 에 가까운 종목부터 읽고, 값이 없는 종목은 `buy_targets` 순서 그대로 뒤에 붙인다. `change_rate` 키는 읽지 않는다 — `test_cycle365_change_rate.py` G-365-P4-9 가 `src/engine/` 전체에서 그 리터럴을 막는다.
- 관측 훅이 스윙 매수 폴·VB/LTV 기준가 REST·momentum 급등 스캔의 **기존 조회를 추가 호출 0 으로** 기록한다(`src=fetch`). 그 세 경로는 매수 평가 전에 같은 조회를 반드시 지나므로 판정이 결정적이다. 캐시 적중 경로는 훅을 부르지 않는다(첫 조회가 이미 기록했다).
- **조회 한 번은 한 번만 기록한다** — leaf 자신의 패스가 조회하는 동안 그 종목은 `_pass_fetch_active` 에 있어 훅이 건너뛰고, 패스가 `src=p0|p1|inc|sell` 로 직접 기록한다. 둘 다 기록하면 모름 3회 상한이 조회 2번에서 끝난다. 🔴 훅은 **이중 try**(condition 쪽 + leaf 쪽)가 계약이다 — 예외가 새면 모든 FHKST 소비자가 깨져 VB·LTV 목표가가 서지 않는다(AST J16).
- 루프는 순수 planner `due_actions(now, …)` 로 할 일을 고르고 `_sleep(LOOP_TICK_S)`(1초)로만 기다린다. `FIRE_WINDOW_END`(15:28)가 지나면 `[status_exit_loop_exit] reason=after_close`, `_running` 이 거짓이면 `reason=running_false` 로 끝난다. 재시작하면 그 시각에 맞는 패스부터 즉시 돈다(시작 때 오늘 발사 횟수를 되살린다 — 위 「보유 청산」). 루프가 끝난 뒤에도 그날 차단 항목과 관측 훅 기록은 살아 있다 — 게이트는 그날 계속 막는다.
- 🔴 **휴장일로 확정된 날은 어떤 패스도 돌지 않는다.** 매 반복 `trading_calendar.is_open_day(오늘)` 을 보고 `False` 면 할 일을 비운다 — 주말·공휴일 수동 기동이 금요일 값으로 시장가 매도를 내지 않게 한다. `None`(모름)·예외는 돈다 — 판정 실패가 청산을 끄면 안 된다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 킬스위치 — `system_config` 2키

- 🔴 **「키 없음」은 행 자체가 없을 때뿐이다.** 모양이 틀린 행은 getter 가 어휘 밖 마커 `__cycle369_malformed__` 를 돌려줘 「알 수 없는 값」 = `observe` 로 떨어진다(행 모양 목록 = `src/db/CLAUDE.md` `system_config.py` 절). 깨진 행을 `enforce` 로 읽으면 끄려던 시장가 매도가 켜진다.
- 값 = `enforce` · `observe`(판정만 — 청산은 `[status_exit_would_fire]`, 매수는 게이트 `False` + `[status_block_buy_would_skip]`) · `off`(그 축의 조회 패스를 돌지 않고 게이트는 `False`). 관측 훅 기록은 `off` 에서도 계속된다.
- 두 키로 나눈 이유 = 롤백 상황이 다르다. 잘못 팔면 청산만 끄고, 과잉 차단이면 차단만 끈다.
- 「키 없음 = enforce」 는 ρ축의 「키 부재 = OFF」 와 반대다. 이 차단은 라이브 조회가 양성인 종목에만 걸리고 결측은 fail-open 이라 전체 정지 경로가 없다. 그리고 사용자가 명시로 켜기로 결정했다.
- 새로 읽는 시점 = task 시작 직후 + **모든 패스 시작**(`refresh_modes()`). SQL UPDATE 는 다음 패스에 반영된다.
- 🔴 **청산 패스는 발사 직전마다 메모리 모드를 다시 읽는다**(위 「보유 청산」 발사 순서) — 패스 도중 PUT 한 `off` 는 그 패스의 뒤 종목부터 적용된다. 매수 게이트 `buy_gate` 도 호출마다 메모리 모드를 읽는다. 매수 패스(P0·P1·INC)의 **조회 대상**만 패스 시작 때 읽은 모드로 정해진다 — 조회만 하고 주문하지 않는다.
- 🔴 **즉시 반영 = `PUT /api/integrations/status-exit` — 메모리가 DB 쓰기보다 먼저다**(라우트 순서 = `src/routes/CLAUDE.md` 그 행). leaf 계약 = `apply_mode(kind, mode, persisted=False)` 는 **고정 반영**, `persisted=True` 는 저장 성공 뒤 고정 해제다. 이유 = `pg.execute` 는 커넥션 획득에 상한이 없어, RDS 가 멈추면 운영자의 `off` 가 30초 넘게 메모리에 닿지 못했다.
- 🔴 **저장에 실패한 축은 고정된 채 남는다** — 그 축의 다음 성공 저장(`persisted=True`)이나 재시작까지 `refresh_modes()` 가 DB 값으로 덮지 않고, 고정 동안 `[status_exit_mode_pinned] kind= mode=` WARNING 을 1회/(날짜, 축) 남긴다. 이유 = 저장 못 한 `off` 를 다음 refresh(매수 60초 · 청산 300초 안)가 `enforce` 로 조용히 되살리면 안 된다. `apply_mode` 의 기본값(`persisted` 생략)은 저장 성공 취급이다.
- ⚠️ 저장이 성공하는 PUT 도 DB 쓰기가 끝나기 전까지는 그 축이 고정 상태다. 그 사이 패스가 `refresh_modes()` 를 부르면 `[status_exit_mode_pinned]` 가 찍히고 그날의 1회 몫을 쓴다. 저장 성공 여부는 PUT 응답의 `persisted` 로 본다.
- **축마다 세대 번호**(`_generation`)를 둔다. `refresh_modes()` 는 DB 를 읽기 전에 세대를 기억하고, 기다리는 동안 PUT 이 그 축을 바꿨으면 늦게 온 옛 값을 버린다. 다른 축의 PUT 은 이 판정에 영향이 없다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 구독은 건드리지 않는다

🔴 사용자 원문 「재구독 중지」 는 글자 그대로 구현하지 않는다(사용자 동의 2026-09-26). 보유 종목 구독을 끊으면 청산 주문이 거부됐을 때 손절이 눈을 감는다. leaf 에는 `src.realtime` import 0 · `unsubscribe` 토큰 0 이다(AST F1). 체결 뒤 구독 해제는 기존 `_unsubscribe_if_no_other_strategy` 가 한다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 관측 마커

- 영속은 두 길이다. (1) leaf 가 `write_log` 로 직접 쓰는 줄은 `[status_block_summary]` 하나다 — 매수 패스 끝에서 `await` 한다(발사 경로가 아니다). (2) 나머지 INFO 이상 줄은 루트 `_DbLogHandler` 가 `[src.engine.status_exit_watch] ` 접두를 붙여 옮겨 적는다(사건당 한 줄). 그래서 `system_logs` 에서 찾을 때는 `[status_exit_fire]` 같은 마커를 부분 문자열로 찾는다.
- WARNING = `[status_exit_fire] ticker= strategy= reason=managed|overheat|managed+overheat iscd= mang= short_over= qty= mode=enforce attempt= bought_today=0|1` · `[status_exit_would_fire] ticker= strategy= reason=`(1회/(날짜, 종목, 전략)). CRITICAL = `[status_exit_giveup] ticker= strategy= fires=`. WARNING + `write_log`(접두 없음) = `[status_block_summary] day= blocked= tickers= mode= skips=<전략:횟수,…>`(차단 집합이나 skip 횟수가 바뀐 패스 끝에만 — 매수 차단의 유일한 영속 기록이라 skip 합계를 싣는다).
- INFO = `[status_exit_armed]` · `[status_exit_disarmed]` · `[status_exit_wait_halt]` · `[status_exit_unknown]` · `[status_exit_unknown_value]` · `[status_exit_iscd_conflict]` · `[status_exit_frame_hint]` · `[status_exit_summary] held= fired= mode=` · `[status_block_released]` · `[status_block_flip_ignored]` · `[status_block_pre_session_check] pre=Y|N in=Y` · `[status_block_buy_skip]` · `[status_block_buy_would_skip]` · `[status_block_unknown] ticker= attempts= reason=fetch_fail|flags_none giveup=0|1` · `[status_block_pass] kind=p0|p1|inc` · `[status_exit_loop_exit]`.
- 로그 상한은 모듈 전역 `_emitted` 집합이다(키에 날짜가 들어가 1회/일).
- `cand=`(`[status_block_armed]`·스냅샷 `blocks[].cand`) = `_is_global_candidate(t)` = `t in buy_targets(registry)` — enabled 전략 후보 ∪ momentum 급등 목록(스윙 후보 포함)에서 보유·주문중·당일매도(`registry.is_ticker_blocked_for_buy`)와 6자리 숫자가 아닌 것을 뺀 집합이다. 그래서 보유 종목은 BFB `_candidates` 나 `ticker_prev_close` 에 남아 있어도 `cand=0` 이라, 청산 패스의 armed 줄이 이 값을 부풀리지 않는다. 가장 최근 패스가 남긴 registry(`_last_registry`)를 읽기만 하고, 패스가 한 번도 안 돌았으면 0 이다. 이 값이 1 인 차단이 「진입 필터가 놓친 첫날」 빈도다.
- `[status_block_unknown]` 은 모름 첫 회와 상한 도달(`attempts=3 giveup=1`) 때 한 번씩 나온다. 그 사이 시도는 조용하다.
- 패스 기록 `_passes[kind]`(kind = `p0`·`p1`·`inc`, 패스 끝에 기록) = `targets · read · flagged · fetch_fail · unknown · truncated · elapsed_ms · at · day`. 청산 패스는 여기 없다. 로그 `[status_block_pass]`·`[status_exit_summary]` 에는 `unknown`·`fetch_fail` 칸이 없다 — 로그로 셀 때는 `[status_block_unknown]`·`[status_exit_unknown]` 줄 수를 쓴다.

### 출처 절: 종목상태 청산·당일 매수 차단 (`status_exit_watch.py`, cycle369) › 테스트 격리와 가드

- 레지스트리가 모듈 전역이라 루트 `tests/conftest.py` autouse `_neutralize_status_watch` 가 매 테스트 전후 `reset_state_for_test()` 를 부르고, 마커 `real_status_watch` 가 없으면 `observe_fhkst` → no-op · `buy_gate` → `False` · `task_loop` → 즉시 반환으로 바꾼다. leaf·배선을 직접 검증하는 테스트만 마커로 옵트아웃한다. 🔴 이 중립화는 메타 가드 Y14 가 벽시계와 무관하게 봉인한다 — 실 `task_loop` 는 15:28 뒤 곧바로 끝나서 행위 테스트는 장중에 돈 실행에서만 중립화 제거를 잡는다(`test_6` 은 시계를 평일 10:00 KST 로 고정한다).
- 가드 = `tests/unit/ast/test_cycle369_ast_status_exit.py`(F1~F4 · F4b · F3b · F6~F9 · F8b · F8c · J16 · J23 · J25 · S1·S1b · R7 · Y14). F4 는 `src.db.system_logs`·`src.db.system_config` **모듈 핸들**로 닿는 속성(호출·참조·`getattr`)까지 허용 목록(`write_log`·`safe_write_log`·`search_logs`·`SEARCH_MAX_LIMIT`·getter 2종)으로 묶고, F4b 가 심은 파괴적 호출로 그 가드가 공허하지 않음을 확인한다. 회귀 = `tests/unit/engine/test_cycle369_status_{classify,sell_pass,buy_block,buy_wiring,isolation,exit_integration}.py` · `tests/unit/engine/test_cycle369_r2_{kill_switch,sell_safety,edge_baseline,buy_observability}.py` · `tests/unit/db/test_cycle369_status_mode_config.py` · `tests/unit/routes/test_cycle369_status_exit_route.py` · `tests/unit/routes/test_cycle369_r2_status_exit_route.py` · 실 Postgres `tests/integration/test_cycle369_status_mode_roundtrip_pg.py` · `tests/integration/test_cycle369_r2_fire_seed_pg.py`.

### 출처 절: strategy_base.py

사이징 규칙(삼중 한도·K축·ρ축·시장 유닛의 의미·롤백 수단·반영 시점)의 정본 = `strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절. 이 절에는 헬퍼·마커·순수성 계약만 적는다.
  - `_resolve_prepare_as_of(as_of) -> (as_of_date, preview)` — `None` = (오늘, False) · 오늘 = (오늘, False) · 미래 = (as_of, True) · 과거 = `ValueError`(DB 가 as_of 뒤의 봉을 돌려주므로 과거 재현은 성립하지 않는다).
  - `_preview_keep_tickers() -> set[str]` — 자기 보유 ∪ **자기** 익일청산대기(`trading_scheduler._pending_next_day_clear` 의 `(ticker, 자기 strategy_id)`). 미리보기 와이프 뒤에도 같은 객체로 남기는 집합이다. 🔴 다른 전략의 보호 종목을 넣지 않는다 — 넣으면 그 전략의 후보 목록·`_scanned_tickers`·kojiro `held_only`·donchian `get_targets_status` 가 남의 보유로 오염된다.
  - `_preview_skip_tickers() -> set[str]` — 자기 보유 ∪ `scanner._collect_protected_tickers_for_scanner()`(전 전략 보유 ∪ 익일청산). 종목 루프가 건너뛰는 집합이다. 🔴 **합집합**인 이유 = 헬퍼는 조회 실패를 조용히 ∅ 로 삼키는데, 그때도 자기 보유는 지켜야 한다. 헬퍼 예외는 흡수한다.
- **생명주기 훅** (기본 no-op + 서브클래스 override):
  - `_reset_daily_state()` — 일일 transient cross-day 상태 정리. `scheduler._reset_daily_state`(21:30 정산 후) registry 순회가 전략별로 호출한다(try/except graceful). override = momentum `_prev_prdy_rate.clear()`(익일 첫틱 거짓돌파 차단) + BFB `_breakout_first_seen.clear()`. 🔴 **보유결합 필드(`_limit_up_reached`/`_partial_exit`)는 이 훅에서 지우지 않는다** — 익일 보유(LTV 상한가 종목 밤샘) 청산 모드가 깨진다.
  - `on_position_closed(ticker)` — 매도 체결로 보유 축이 닫힐 때 per-ticker 보유결합 상태 정리. 호출 site 는 `order_engine` **정확히 2곳**(`_handle_sell_fill` 의 닫기 묶음 `if close_position:` + `execute_sell` insufficient_qty reconciliation, 각 try/except 격리). override = LTV `_limit_up_reached.discard(ticker)`(재매수 종목의 전일 상한가 모드 누설 차단) + BFB `_partial_exit.pop(ticker, None)`(재진입 익절 억제 차단) + BFB·VCP `register_cooldown_after_exit(ticker)` + `asyncio.create_task(_refine_cooldown_business_days)`(즉시 달력일 근사 `days+2` → CTCA0903R `add_business_days` 로 정확 N영업일 정정).
  - 불변식 = **"보유 중 flag 유지, 전량 매도 시 clear"**. 포지션 제거 site 가 2곳뿐이라는 것이 누설의 구조적 봉쇄이고 AST `G2-STRUCT-INVARIANT` 가 3번째 site 누락을 막는다. 보유가 남는 매도(부분 체결 · 보유보다 적은 주문)는 훅을 부르지 않으므로 잔여 보유의 청산모드가 보존된다(「매도 체결 — 주문 축과 보유 축」 절).
  - 🔴 `_cooldown_until` 은 multi-day 상태다 — 일일·prepare 리셋 금지(AST `G-191-NO-DAILY-RESET`).
- **트레일링 기준점 복구 단일 진실원 `_apply_high_since_buy_from_candles(pos, candles, today)`** — `buy_date < 영업일 < today` 일봉 high max 로 고점을 **올리기만** 하고 `update_high` 로 DB 에 남긴다(`[high_since_buy_recover]`). base 에 하나만 둔다 — **전략별 복제 금지**(`_HIGH_RECOVER_LABEL` ClassVar 로 로그 접두사만 다르게: donchian "도치안 스윙" / VCP "VCP"). 보조 파서 `_candle_trade_date`/`_candle_high` 는 KIS 원본 키(`stck_bsop_date`/`stck_hgpr`)와 DB 정규화 컬럼(`bas_dd` date 객체/`high_price`) **양쪽을 받는다** — `get_recent_daily_normalized` 가 raw 없는 row 를 row 자체로 돌려주기 때문이다. `_candle_high` 는 `except Exception: return 0`(OverflowError 포함 — 봉 하나가 배치 복구를 멈추면 안 된다). ⚠️ `recompute_high_since_buy` 자체는 base 승격 금지(전략별 fetch 소스·일수가 다르다 — donchian/VCP/BFB 자체 정의, kojiro 는 `recompute_held_atr` 에 내장). 분업 = `risk.on_tick`(메모리 갱신) → boot 훅(일봉 복구 + DB 영속)이고 **on_tick 에 DB write 금지**(회귀 가드).
- **일봉 신선도 기준 `_resolve_expected_daily_head(as_of_date=None) -> date | None`** — `trading_calendar.previous_trading_day(as_of_date 또는 today_kst())` 를 지연 import 로 부르고(never-raise, 예외 → `None`) `[prepare_expected_head] strategy=<id> expected_head=<YYYY-MM-DD|None>` INFO 1행을 남긴다. 6전략(VB·LTV·donchian·BFB·VCP·kojiro) `prepare()` 가 받은 `as_of` 를 그대로 넘겨(미리보기면 `previous_trading_day(as_of)` — 저녁 미리보기에선 오늘) gather **전에 1회** 불러 `_fetch_one` 안의 `get_recent_daily_normalized(..., expected_head=expected_head)` 로 넘긴다(종목마다 부르지 않는다). 휴장일을 모르면 `None` 을 명시해 넘겨 어댑터의 달력 판정으로 떨어뜨린다. 판정 계약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절. momentum 은 일봉을 쓰지 않아 무관하다.
- **`_apply_budget_limit(qty, current_price, ticker=None)` — 7 전략 `calc_buy_quantity` 의 공통 return 관문**(전략 예산 이중제한의 ② 명목 축 `Σ매수금액 ≤ total_investment`. ① 개수 축 `max_positions` 는 `is_max_positions` 가 `check_buy_signal` 에서 담당).
  - **분기 순서가 계약이다** — `price ≤ 0 → 0` → (`qty ≤ 0` → `_fallback_one_share` 위임 / `qty > 0` → 잔여 클램프 `min(qty, 잔여//price)` + `[budget_clamp]`) → `_apply_lot_units_cap`(K축) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축) → `return`. 잔여 < price 면 0 이고 그 밖은 **부분 매수 허용**이다. `qty<=0` 분기가 폴백을 호출한다는 사실 자체를 `test_strategy_fallback_budget.py` Case D 가 검증한다.
  - 두 캡의 **자리**가 계약인 이유 = K축은 관측 **앞**(관측이 캡 이후 최종 수량을 재야 하고, 캡→0 이면 그 관측기는 `final_qty < 1` 로 자연 침묵하므로 차단 사실은 전용 마커가 담당한다) · ρ축은 관측 **뒤**(앞에 두면 차단된 랏의 ρ 관측이 통째로 사라진다)이자 K축 **뒤**(앞에 두면 조기탈출로 K축 마커 3종(cycle242)이 사라진다).
  - 🔴 **관문 안에서 `await`/DB/HTTP 절대 금지.** `order_engine.execute_buy` 의 `calc_buy_quantity` ~ `pending_buys.add` 사이 `await` 0건이라 관문 read 가 pending 등록까지 원자적이다 — 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다. 같은 제약이 신규 헬퍼 전부에 확장 적용된다(A-PURE · `G-242-2` · `G-242-10` · `G-245-2`). 관문 반환 타입은 **`int`** 여야 한다 — float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다(`G-245` 회귀).
  - 가드 `tests/unit/ast/test_budget_limit_ast.py` = A-ATOMIC(await 0건) + A-PURE + A-GATE(7전략 모든 return 이 관문 경유) + C-DEFAULT(`position_ratio × max_positions ≤ 1.0` 기본값 불변식). 관측 `[budget_clamp]` = `_emit_budget_clamp` DailyEmitCap 1회/(ticker,전략)/일, 날짜 키 **자기 리셋**(`_reset_daily_state` 훅에 의존하지 않는다 — 서브클래스 override 가 `super()` 를 부르지 않을 수 있다).
- **K축 — 랏당 최대 유닛 상한 `_apply_lot_units_cap`**: `sizing_mode == "turtle"` 전략의 **모든 랏**에 `min(final, compute_unit_qty(budget, atr, risk_pct, fraction=K))` 를 적용한다(K = `max_lot_units`, 기본 2.0).
  - **ATR 소스** `_resolve_sizing_atr(ticker)` — 터틀 분기와 **같은** `_candidates[ticker]` 를 read-only 로 읽고, `_SIZING_ATR_KEYS = ("atr", "atr14")` 중 양수로 파싱되는 값이 **둘 이상 서로 다르면 채택하지 않는다**(`ambiguous_atr`). `_candidates` 를 생성·변경하지 않는다(`G-242-8`).
  - **fail-open 경계** — `sizing_mode` 아님 / `ticker is None` = 조용히 통과. `no_candidates`·`no_atr`·`ambiguous_atr`·`no_risk_pct`·`no_budget`·`exception` = **현행 수량 유지 + `[fallback_cap_skipped]` WARNING**. 🔴 수량을 0 으로 만드는 fail-closed 구현 금지 — 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이다.
  - **마커 5종** — `[fallback_notional_capped]`(INFO, 캡 발동 — `path=fallback|sized`·`units_before`·`units_after`·`k`·`atr`) / `[fallback_cap_skipped]`(WARNING, `reason=` 6종 + `atr=`/`units=` 진단 병기 — PR 경로 fail-open 랏의 K 초과를 남기는 유일한 채널) / `[fallback_cap_config]`(INFO 카나리아, 1회/전략/일, `cap=on|off`·`k`·`atr_max`) / `[fallback_cap_clamped]`(WARNING, **키가 명시 존재하는데** 범위 밖일 때만 — DB 미설정과 PUT 무효값을 구별한다) / `[oversized_fallback]`(ρ축 서식 + 꼬리 ` units=`). 전부 `_lot_cap_logged: DailyEmitCap[str]` 하나의 복합 키(`cap|t` / `skip|t|r` / `cfg` / `clamp`) + 날짜 키 자기 리셋 + **peek→로그→mark** 순서. **행위는 cap 밖** — 마커 성패와 무관하게 캡 수량을 반환한다.
  - **두 척도 병존** — `[oversized_fallback]` 의 `cap` 은 ρ축(`position_ratio × 예산`, ATR 무관 = 갭·거래정지 명목 리스크), `units` 는 K축(`qty × ATR ÷ (예산 × risk_pct)` = 정상 시장 손절 리스크). **대체재가 아니다.**
  - **K 취급** — `_read_max_lot_units` 가 `[1.0, 20.0]` 로 클램프한다(비수치·bool·비유한·<MIN → 기본 2.0 / >MAX → 20.0). `_MAX_LOT_UNITS_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 4 터틀 전략 `DEFAULT_PARAMS` 리터럴과 동치여야 한다(`G-242-6`). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(`G-242-1`). `_MiniStrategy` 류 더블은 `DEFAULT_PARAMS` 병합을 타지 않으므로 **모듈 상수 기본값이 필수**다.
- **ρ축 — 랏 명목 상한 `_apply_ratio_notional_cap`**: `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // price` · `final = min(final, cap_qty)`(K_ρ = `max_lot_ratio_mult`, 기본 2.5). 경계는 `final × price > cutoff` 일 때만 차단 = 경계 포함이다.
  - **적용 범위 = 관문을 지나는 모든 랏**이다. `_lot_units_cap_governs`(= `sizing_mode == "turtle"` ∧ `ticker is not None` ∧ `risk_pct > 0` ∧ 예산 > 0 ∧ ATR 해석 성공)는 K축이 이 랏을 실제로 심사했는지만 판정하고, 조기탈출은 **그 판정 자체가 실패한 경우(`probe_error`)뿐**이다 — K축 심사 여부와 무관하게 컷오프를 적용한다(cycle254).
  - **스코프와 항등식은 다른 문장이다 — 뭉치지 마라.** (a) 스코프 = `via_fallback`·`final == 1` 로 좁히지 않는다(축소 뮤테이션을 F-5b/F-5c 가 봉인 — 현행 호출부에서는 주 분기가 정의상 ρ상한 이하라 지키는 것은 **장래 회귀**다). (b) 항등식 `notional ≤ K_ρ × int(예산 × position_ratio)` 는 관문을 지나는 모든 랏에 성립한다 — 사이즈드 터틀 랏·낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산 × position_ratio)//price)`)이 이미 묶어 `final <= cap_qty` 로 무접촉이고, **실효는 1주 폴백 랏(`price > 예산 × position_ratio`)뿐**이다.
  - **fail-open 경계** — 키 부재 = **캡 OFF**(조용히 — K축 `_read_max_lot_units` 의 "키 부재도 기본값" 관례와 **반대**다: 이 캡은 *매수를 막는* 통제라 fail-closed 는 유령 키 재현 경로다). K축이 심사한 랏도 `min` 으로 후심사한다. `k_axis_probe_error`(판정 자체 실패)·`no_ratio`·`no_budget`·`no_cap`·`exception` = **현행 수량 유지 + `[ratio_cap_skipped]` WARNING**. 어떤 결측·예외도 수량을 0 으로 만들지 않는다.
  - **마커 4종** — `[ratio_notional_blocked]`(INFO, 차단·축소 행위. `path=fallback|sized`·`price`·`cap`·`cutoff`·`k`·`ratio`·`req_qty`·`capped_qty`·`budget`·`pos_ratio`) / `[ratio_cap_skipped]`(WARNING, `reason` 5종) / `[ratio_cap_config]`(INFO 카나리아 — **`cutoff_price` 필수 필드**, 운영자가 아침에 "오늘 이 전략은 몇 원 넘는 종목을 못 산다" 를 한 줄로 읽는 근거) / `[ratio_cap_clamped]`(WARNING). 전부 K축 `_lot_cap_logged` 와 **별개 인스턴스**인 `_ratio_cap_logged: DailyEmitCap[str]` 복합 키(`blk|t` / `skip|t|r` / `cfg|cap상태|k|cutoff` / `clamp|raw`) + 날짜 키 자기 리셋 + peek→로그→mark + 예외 전부 흡수. **행위는 cap 밖** — 마커 성패와 무관하게 차단은 매 호출 수행한다. `[ratio_cap_config]`/`[ratio_cap_clamped]` 의 키는 **값-민감**이라 **"1회/(전략, 값 조합)/일"** 이다 — 정상 운영은 하루 1행이고 K·예산이 실제로 바뀐 날에만 1행이 더 붙는다(= 공식 롤백 PUT 을 확인하는 유일 채널). 라벨은 `off|on` 2종이다.
  - **`[oversized_fallback]` 은 "사려 했던 랏" 을 잰다** — ρ캡 **앞**에서 발화한다(로그 서식 byte 불변, `G-245-10`). K>1 이면 K축을 통과한 랏도 ρ 상한을 넘을 수 있어 **비제로가 정상**이다. 자기검증 **R7** = `ratio` 가 그날 그 전략의 `[ratio_cap_config] k=` 값(리터럴 2.50 금지 — 롤백하면 20.0 이 된다)을 넘는데 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]` 도 `[ratio_cap_skipped]` 도 없고 그 전략이 `cap=on` 이면 **캡 우회 = 결함**이다. 터틀 행에도 예외가 없다 — 사이즈드 터틀 랏은 항등식으로 애초에 `ratio ≤ k` 라 두 마커 부재가 정상이고, 1주 폴백만 `ratio > k` 가 가능한데 그때는 반드시 한쪽이 동반돼야 한다.
  - **오귀인 판독** — 캡→0 은 `order_engine.execute_buy` 의 `quantity <= 0` 경로로 흘러 `block_low_funds(+900s)` + "매수 수량 0 → 900s cooldown (투자금: …)" WARNING 을 남긴다(8영역이라 무접촉). `_bought_today` 가 있는 4전략(`donchian_swing`·`kojiro`·`vcp_breakout`·`bull_flag_breakout`)은 종목당 1회/일이라 캡 마커와 **1:1**, 없는 3전략(`momentum`·`volatility_breakout`·`long_tail_volatility`)은 900s 만료 또는 `_sync_positions_from_balance`(≈15분)의 `clear_low_funds()` 로 같은 종목을 하루 여러 번 재시도해 **1:N** 이다. 판독 규칙 = 같은 (전략, ticker, 일자)에 `[fallback_notional_capped]` 나 `[ratio_notional_blocked]` 가 **한 행이라도** 있으면 그날 그 종목의 **모든** 수량-0 WARNING 을 캡 귀속으로 읽는다(캡 마커는 1회/일이라 2행째부터는 단독으로 보인다).
  - **21:30 일일 리포트 미도달** — `log_analysis_engine._aggregate_log_patterns` 는 `{WARNING, ERROR, CRITICAL}` 만 패턴 집계하므로 INFO 인 `[ratio_notional_blocked]`·`[ratio_cap_config]` 는 리포트 payload 에 안 들어간다. 반대로 오귀인의 **원인**인 수량-0 WARNING 은 `top_patterns` 에 오른다 ⇒ 리포트만 읽으면 "투자금 부족 급증" 오결론이 나온다. 판독은 `system_logs` 직접 조회가 유일 채널이다(집계 편입은 후속 F-12).
  - **K_ρ 취급** — `_read_max_lot_ratio_mult` 가 `[1.0, 20.0]` 로 클램프한다(비수치·bool·비유한·<MIN → 기본 2.5 / >MAX → 20.0). **하한 1.0 이 "정상 비중 랏 무접촉" 항등식의 수학적 전제**다. `_MAX_LOT_RATIO_MULT_DEFAULT/MIN/MAX` 모듈 상수가 정본이고 **7 전략 전부**의 `DEFAULT_PARAMS` 리터럴과 동치여야 한다(`G-245-6`, glob 전수). `PARAM_RANGES`/`INT_PARAMS` 편입 금지(`G-245-1`) + AI 자문 자동 적용 경로 편입 금지.
- **시장 유닛 헬퍼 (cycle382 — 터틀 4전략 `kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout` 한정)** — 규칙 = `strategies/CLAUDE.md` 「시장 유닛 — 터틀 4전략 (cycle382)」 절 · 판정 = 모듈 맵 `market_unit.py`. 관문 `_apply_budget_limit` 본문은 이 헬퍼들과 무관하다(소스 세그먼트 sha 불변, AST A12). 나머지 3전략은 속성만 물려받고 부르지 않는다(AST A04).
  - **계산 자리 = 4전략 `prepare()`** — `_resolve_prepare_as_of(as_of)` 바로 다음 줄에서 `await self._refresh_market_unit(as_of_date=, preview=)` 를 정확히 1회, 어떤 조기 `return` 보다 앞에서 부른다(AST A08). 결과는 `_market_unit_snaps: dict[date, Snapshot]` 에 **거래일별로** 담고, 오늘(KST)보다 과거 키는 지운다(「오늘 · 다음 거래일」 두 칸 — 저녁 미리보기는 다음 거래일 칸만 쓴다). 이 헬퍼는 `_candidates`·`positions`·`_entry_atr`·`_position_setup`·`_position_atr`·`_breakout_high` 를 읽지도 쓰지도 않는다(PV-1 과 교집합 0, AST A07). **보존 규칙** = 같은 날짜에 `ok=True` 스냅샷이 있으면 새 실패가 덮지 않는다(`kept=1` — 21:00 미리보기의 좋은 값을 다음 날 부팅의 일시 DB 실패가 지우지 않게). 새 스냅샷이 `ok=True` 면 항상 덮는다. 모드가 `off` 여도 계산한다 — 그래야 `enforce` PUT 이 재시작 없이 먹는다. never-raise.
  - **읽는 쪽은 순수다**(`await`·DB·HTTP 0 — A-PURE·A-ATOMIC 그대로, AST A05). `_market_unit_view()` 가 매 호출 모드와 **오늘 날짜 칸**을 다시 읽는다(캐시 없음 = PUT 즉시 반영). 모드 오타 = `off` + `[market_unit_config]`. 오늘 칸이 없으면 m=1 + `[market_unit_unavailable] where=view reason=not_computed`.
  - **`calc_buy_quantity` 첫머리**(4전략 같은 모양, 기존 본문은 그 아래 그대로) — `_market_unit_sizing(price, ticker)` 는 `enforce` ∧ m<1 일 때만 값을 돌려준다. `shadow` ∧ m<1 은 `[market_unit] where=calc` 한 줄과 일일 집계만 남기고 `None`(수량 불변). m=1 인 날은 calc 줄이 없다. 값이 오면 `lot_after <= 0` → `return 0`(폴백·낙하 없음), 아니면 `_apply_budget_limit(lots.design_after, …)` 다 — 그래서 축소일에는 관문의 폴백 분기에 닿지 않는다. 터틀 경로의 donchian·BFB·VCP 는 `_entry_atr[ticker] = lots.atr` 를 찍는다(= 사이징 ATR, m 과 무관 — 손절선이 m=1 랏과 같다). kojiro 는 이 줄이 없다 — `_position_atr` 을 신호 시점에 찍는다.
  - **설계 랏 `_market_unit_lots(price, ticker, m)`** — `budget = int(total_investment)` 와 잔여 `budget − _calc_used_funds()` 는 **줄이지 않는다**(줄이면 재현하지 않은 예산 경로가 된다). 터틀 = `compute_unit_qty_guarded(int(budget × m), atr, price, risk_pct, remaining_budget=잔여, min_vol_pct=, position_ratio=)` — 명목 상한도 `int(budget × m) × position_ratio` 로 함께 준다. 🔴 `fraction=m` 으로 쓰지 않는다(명목 상한이 안 줄어 저ATR 종목 랏이 그대로 남는다 — G-242-7). 비중 = `int(int(budget × m) × position_ratio) // price`. ATR 키 = 전략 ClassVar `_MARKET_UNIT_ATR_KEY`(kojiro·donchian `"atr"` · BFB·VCP `"atr14"`) — 그 전략 터틀 블록이 읽는 키와 같아야 한다(AST A09). 경로는 매 호출 `sizing_mode == "turtle" and ticker is not None` 로 정한다(BFB 전환 PUT 을 따라간다). `lot_before`/`lot_after` = `min(설계 랏(1.0 | m), 잔여 // price)` 이고, `lot_after` 는 `enforce` 때 실제 주문 수량과 같다(축소 랏은 K축·ρ축 캡 아래라 두 캡이 무접촉이다).
  - **스킵 사유 `_market_unit_skip_reason`** = `zero_state`(m ≤ 0) → 살 수 있으면 `None` → `funds`(잔여 < 1주) → `rounds_to_zero`(설계 랏이 줄어서 0) → `no_fallback`(m=1 이었으면 1주 폴백·비중 낙하로 샀을 종목).
  - **신호 필터 `_market_unit_blocks_entry(ticker, price)`** — `enforce` ∧ m<1 ∧ 사유 ∉ {`None`, `funds`} 일 때만 `True` 이고 호출부가 `Signal.NONE` 을 낸다. **부작용 0** — `_bought_today`·`buy_signals`·래치·스탬프 무엇도 바꾸지 않아 PUT `off` 가 다음 평가부터 먹는다. 자리 = 각 전략의 매수 확정 블록 바로 앞, 다른 매수 게이트 전부 뒤다(`_account_soft_gate_blocked` 는 그대로 첫 문장). 자리 표 = `strategies/CLAUDE.md` 「시장 유닛」 절.
  - **fail-open** — calc·signal 헬퍼 예외는 `[market_unit_error] where=calc|signal` WARNING 을 남기고 m=1 경로로 간다.
  - **마커 6종**(로거 `src.engine.market_unit`) — INFO = `[market_unit]`(`where=calc|signal`, 1회/(ticker, where)/일) · `[market_unit_state]`(refresh 성공, (as_of, preview, state, m) 조합당 1회) · `[market_unit_daily]`(거래일마다 전략당 1줄 — 보통 그날 21:00 미리보기의 refresh 가 낸다). WARNING = `[market_unit_unavailable]` · `[market_unit_config]` · `[market_unit_error]`. cap = 전략 인스턴스별 `KstDailyEmitCap` 3개(state·attempt·warn). `write_log` 는 따로 부르지 않는다 — `_DbLogHandler` 가 INFO 이상을 `system_logs` 로 나른다. ⚠️ INFO 3종은 21:30 `top_patterns` 에 오르지 않고 INFO retention 이 2일이다 — 섀도 판독은 이틀 안에 `system_logs` 를 직접 조회한다. 일일 집계 `_market_unit_tally` 는 **더 뒤 날짜**가 올 때만 닫는다(`_market_unit_tally_roll` 의 `tally["date"] < day` — refresh·calc·signal 공통). 닫을 때 그 날짜의 `[market_unit_daily]` 를 내고 새 날짜로 연다. 같은 날짜·앞 날짜는 no-op 이다 — 미리보기가 연 다음 거래일 집계를 되돌리거나 한 날짜를 두 번 내지 않게 한다. 집계는 메모리라 재시작하면 그날 앞부분이 빠진다 — 정본은 `[market_unit]` 개별 줄이다.
- **공통 매수 게이트 `_account_soft_gate_blocked(ticker)` — 순서 = 종목상태 차단 → `buy_paused` → 계좌 SOFT.** 7전략 `check_buy_signal` 이 전부 이 게이트를 지난다(자리 = 폴·래치형 5전략 첫 문장 / momentum·VB 발사 직전 — `strategies/CLAUDE.md` 「안전 규칙」).
  - **첫 문장 = `if self._status_buy_blocked(ticker): return True`** (AST J25). `_status_buy_blocked` 는 `status_exit_watch.buy_gate` 를 함수 안에서 지연 import 해 부르는 순수 메모리 조회이고, 판정 예외는 `False`(fail-open)다. 부르기 전에 `_is_status_gate_candidate(ticker)` 로 `cand` 를 계산해 넘기고(집계 전용), 막히면 `_clear_edge_baseline_on_block(ticker)` 로 edge 기준가를 비운다. 셋 다 `await` 0 · never-raise 다. 계약 = 위 「종목상태 청산·당일 매수 차단」 절
  - **둘째 문장 = `if self._buy_paused_blocked(ticker): return True`** (cycle384, AST `test_cycle384_ast_buy_paused.py` A02). 셋째가 기존 계좌 SOFT `try` 다. 멈춤이 계좌 SOFT 보다 먼저인 이유 = 멈춘 전략에서 `[account_gate_skip]` 이 찍히면 원인이 「계좌 오픈리스크」로 잘못 읽힌다. 종목상태 차단과 멈춤이 둘 다 걸리면 `[status_block_buy_skip]` 만 남는다.
  - 행위·값 규칙(신호 단계에서만 막는다 · `is True` 만 멈춘다 · 멈춰 둔 동안 키 삭제 금지) = `strategies/CLAUDE.md` 각주 ⑨. 여기에는 게이트 구현만 적는다.
  - **`_buy_paused_blocked(ticker)`** — 동기 · 순수 메모리 · never-raise(`await`·DB·HTTP·`write_log` 0 — A-PURE·A-ATOMIC 그대로, AST A03). **매 호출** `self.config.params.get(BUY_PAUSED_KEY, _BUY_PAUSED_ABSENT)` 를 읽고 인스턴스에 캐시하지 않는다(A07). PUT 라우트가 같은 dict 를 `update` 하므로 다음 틱·다음 1분 폴부터 먹는다. **`raw is True` 일 때만 멈춘다** — 부재·`False`·그 밖의 모양은 멈추지 않는다. 읽기 예외 = `False`(fail-open) + DEBUG `[buy_paused_gate_failed]`. `ticker` 가 비어도 멈춘다(전략 단위).
  - **막을 때 지우는 것** — ① `_clear_edge_baseline_on_block(ticker)`(종목상태 차단과 같은 헬퍼, 본문 무변경) ② `_clear_entry_latches_on_pause(ticker)` — `_PAUSE_ENTRY_LATCH_ATTRS = ("_breakout_first_seen", "_vol_latch")` 중 dict 인 속성에서 그 종목만 `pop` 한다(BFB 돌파 유지 대기 · BFB/VCP 거래량 대기 래치). 순서는 ①→②다(A10). 첫 문장 게이트 전략은 멈춘 동안 신호 본문이 통째로 안 돌아 기준가·래치가 언다. 지우지 않으면 해제 첫 틱이 거짓 돌파가 되거나, 멈춘 사이 무너진 셋업을 낡은 래치로 산다. 실패 = DEBUG `[buy_paused_latch_clear_failed]`.
  - **안 지우는 것** — `_bought_today` · `_position_setup` · `_entry_atr` · `_cooldown_until` · `_breakeven_latched` · VCP `_breakout_watch` · 평평한 `_prev_price`(BFB·VCP — 비우면 0 이 새 거짓 교차가 된다) · 시장 유닛 스냅샷. donchian·kojiro 는 기준가가 없고 `_bought_today` 도 그대로라, 매수 창(09:05~09:30) 중간 해제는 창 중간 재기동과 같다. ⚠️ BFB·VCP 는 멈추기 전 기준가가 돌파선 아래이고 멈춘 사이 가격이 돌파선을 넘었으면, 해제 첫 틱이 그 교차를 **늦게** 본다. 가짜 교차가 아니라 WS 공백·밤사이 갭과 같은 기존 의미론이다.
  - **함께 멈추는 것(게이트 뒤라서)** — `[market_unit] where=signal|calc` · LLM 매수평가 행(`llm_buy_evaluations`) · kojiro 갭 관측 · VCP 돌파 관측 틱 · VB `[open_entry_hold_blocked]` · LTV `[open_entry_hold_*]` 둘 다. **계속 도는 것** — `prepare()` · 퍼널 기록 · 구독 · `[market_unit_state]`·`[market_unit_daily]` · 스윙 폴 조회. 멈춘 donchian 후보는 `_bought_today` 에 들어가지 않아 09:05~09:30 매 분 REST 조회가 계속된다.
  - **마커 2종**(로거 `src.engine.strategy_base` · cap = 인스턴스 `_buy_paused_logged: KstDailyEmitCap[str]` · peek→로그→mark · 실패 = `trace_observer_failure` · **행위는 cap 밖** · `write_log` 병행 0, AST A13).
    - `[buy_paused_config] strategy= paused= valid= raw= note=` = 설정 카나리아, 1회/(전략, 값)/일(키 `cfg|{paused}|{valid}`). `paused=1` 과 `valid=0` 은 **WARNING**, `paused=0 valid=1` 은 INFO 다. WARNING 인 이유 = 21:30 일일 분석 상위 WARNING 에 매일 올라, 멈춘 전략의 무매매가 결함으로 오진되지 않게 한다.
    - `[buy_paused_skip] strategy= ticker= cand=1 dropped= note=` = INFO, 1회/(종목, 전략)/일(키 `skip|{ticker}`). 후보 판정 `_is_status_gate_candidate` 가 참인 종목만 남기고, 후보가 아니면 mark 하지 않는다(장중에 뒤늦게 후보가 된 종목도 기록되게). `dropped` = 실제로 지운 래치 이름(`breakout_first_seen,vol_latch` 또는 `-`). INFO 인 이유 = 운영자가 정한 상태의 결과라, WARNING 이면 진짜 경고를 밀어낸다(AST A15).
    - ⚠️ 두 줄 모두 그날 게이트가 한 번은 닿아야 찍힌다 — momentum·VB 는 돌파가, donchian·kojiro 는 09:05 뒤 스윙 폴 후보가 있어야 한다. 멈춤 여부의 정본은 로그가 아니라 `GET /api/strategies` 와 DB `strategy_config.params` 다.
  - 🔴 **운영 함정** — 서버 기동 때 설정 로드(`main.py` → `_load_strategy_config`)가 실패한 채로 PUT 하면, 메모리의 코드 기본값 전체가 `save_params` 로 DB 에 써진다. PUT 전에 GET 의 운영값(`sizing_mode`·`max_positions`·`stop_loss_rate`)이 DB 와 같은지 본다(실패 흔적 = 「전략 설정 초기 로드 실패」 WARNING). 키 삭제 함정(각주 ⑨)의 원인 = `_load_strategy_config` 의 `if key in strategy.config.params` 가 코드에 없는 키의 DB 값을 버린다.
- `Position.is_next_day`: `buy_date < today AND strategy_id not in _MULTIDAY_STRATEGIES`(**리터럴 정본 = `{donchian_swing, vcp_breakout, kojiro}`**, `strategy_base.py` 의 frozenset 리터럴이 유일 진실원). 멀티데이 전략은 항상 False — 확장 시 frozenset 리터럴 멤버만 추가하고 `Position` 시그니처는 바꾸지 않는다. 🔴 전략 모듈이 import 시점에 자기를 추가하는 방식 금지(import 순서 의존).
- `pending_buy_amounts` 는 OrderEngine `execute_buy` 시장가/지정가 폴백에서 `pending_buys.add(ticker)` 옆 동기 등록. `pending_buys.discard` 옆에서 동시 정리
- **funnel 단계 캡처** (관찰성 전용 — 메모리 `_funnel_steps` + DB `strategy_funnel_snapshots` + UI): `_record_funnel_step(step_no, step_name, survived, excluded=None, *, step_conditions=None)` + `_record_funnel_pipeline_step(FunnelStage, ...)` 위임. survived/excluded cap 200/20 자동, `survived_count` 는 cap *전* 정확 보존. 같은 `step_no` 는 **교체**한다(in-place upsert — append-only 누적 차단). `_reset_funnel_steps(stages)` 는 모든 `FunnelStage` 를 `survived=[]` count=0 으로 pre-populate 해 조기반환·실패 run 도 전 단계 0 으로 일관되게 만들고(단계별 stale 잔존 차단), `stages=None` 은 빈 리스트다. 5 전략 prepare()+retry 가 각 전략 STAGES 상수를 인자로 넘긴다(donchian/BFB/VCP=`FUNNEL_STAGES` / VB=`VB_FUNNEL_STAGES` / LTV=`LTV_FUNNEL_STAGES`). 🔴 **`check_exit_signal`/`check_buy_signal` funnel hook 0건**(매도·매수 hot path 적재 금지, SAFETY 가드). momentum 은 영구 제외.

### 출처 절: strategy_registry.py

- `allocate_funds(total_asset)` 비중 기반 분배 / `update_weights(weights)` — **단위는 비율 `0.0~1.0`**(`get_strategies_status` 의 `weight` 도 동일 → GET↔PUT 왕복 항등). `allocate_funds` 는 `enabled()` 전략만 모아 `weight / Σweight` **상대 정규화** 후 `int()` 절삭이라 **Σ≠1 이어도 자산 전액이 배분된다** — 단위 오염이 조용히 흡수되므로 탐지는 라우트 Σ 가드와 부팅 `[weight_config_anomaly]` 가 담당한다. `update_weights` 는 값을 그대로 대입하고 `config.enabled = weight > 0` 을 **자동 토글**한다(비중 0 = 비활성화 → `registry.enabled()` 이탈)

### 출처 절: risk.py

`on_tick()`: ticker_prices 갱신 1회 → `registry.enabled()` 순회 → 전략별 exit/buy 신호. 꺼진 전략의 보유는 이 순회에 없다(금기 = 루트 `CLAUDE.md` 「핵심 안전 규칙」 보유 전략 끄기 금지).
- **`_selling` 가드**: `risk.on_tick` 의 보유 분기에서 `check_exit_signal` 호출 *전* `order_engine._selling` 을 검사한다 — 매도 발사 후 체결통보 도착 전까지 신호 평가와 로그 폭주를 차단한다(근거 = 042700 7초 18+ 행 운영 결함). 7 전략 공통.
- **NXT 프리장 청산 평가 보류 게이트**: `_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})` 화이트리스트 **밖**의 전략은 프리장 단독 구간에 **청산 평가 + `high_since_buy` 갱신을 보류**한다. 근거 = 프리장 시초가 왜곡(전일 상한가 종목이 하한가를 형성하는 등)으로 허깨비 손절이 발화하고 트레일링 앵커가 오염된다.
  - **판정 = `by_active` OR `by_clock`** — `by_active`(`PRE_NXT ∈ session_tracker.active AND MAIN ∉ active`, 매수 PR-F 와 같은 membership) 또는 `by_clock`(`session.boards_at(_now_kst().time())` 가 PRE_NXT 단독). OR 인 이유 = `active` 는 `SessionTracker.tick()`(`_session_loop` 30초 주기)이 기록하는 **stale 캐시**라 `boards_at(07:59)`=∅ 스냅샷이 08:00:00~29 를 살아남아 단독으로는 매일 ~30초 fail-open 한다. 폴백은 tracker 가 쓰는 **같은 `_BOARD_SCHEDULE` 표**를 fresh 로 읽는다 — 08:00/09:00 리터럴 신설 금지, `_KST` 명시(naive 금지).
  - **09:00 정각**은 stale `active`={PRE} 가 남는 ≤30초 동안 OR 때문에 보류를 유지한다(안전 방향).
  - 🔴 **평가 보류이지 주문 보류가 아니다** — 주문만 보류하면 허깨비 신호가 09:00 실매도로 전환된다. 09:00 MAIN 진입 시 자동 재개.
  - 두 소스가 갈릴 때만 `[pre_market_exit_gate_divergence] reason=clock_fallback|active_stale_hold` 1회/(전략,사유)/일(날짜 키 자기 리셋 + peek→로그→mark). `[pre_market_exit_deferred]` 는 1회/전략/일이고 D+1 판독 = 첫 타임스탬프 08:00:0x + 같은 시각 `clock_fallback` 동반.
  - 결정성은 루트 `tests/conftest.py` autouse `_pin_pre_market_clock`(`risk._now_kst` MAIN 핀, 옵트아웃 마커 `real_pre_market_clock`)이 담보한다.
  - 🔴 `tradable_boards` 로 게이팅 금지(매수 전용 doctrine 커플링 차단, AST 가드) + fail-open 은 **두 소스 모두** 판정 불가일 때만(평가 유지). 이 게이트가 "청산은 항상 평가" 의 **유일한 명시 예외**다. 회귀 `test_risk_pre_market_exit_gate.py` + `test_cycle238_pre_market_clock_gate.py`
- **보드 가드**: `session_tracker.is_tradable(strategy_id, params)`. 🔴 `tradable_boards` 는 **매수 진입 전용**이다 — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동하고, `check_exit_signal` 분기는 본 가드 *전* 진입한다.
- **레짐은 매수를 차단하지 않는다(관찰 전용)** — `risk.on_tick`·swing 폴에 레짐 게이트가 없다. `get_buy_block_state`/`BuyBlockState`/`buy_block_mode` 는 대시보드·AI자문 payload **표시 전용**이고 `to_advisor_dict()`·`GET /api/market-regime/current` 는 `buy_blocked=False` 를 낸다(`block_reason` 은 방어 '권고' 관찰용). `execute_buy` 의 `soft_multiplier` 파라미터는 vestigial 이다. 레짐 대응은 `cash_usage_ratio`(`auto_regime_adjust`)뿐이다. 🔴 이 게이트를 복원하지 마라. 회귀 `test_regime_observation_honesty.py`. 시장 유닛(cycle382)은 레짐 게이트가 아니다 — 터틀 4전략의 `check_buy_signal`·`calc_buy_quantity` **안**에서 전략 사이징으로 작동한다(`strategy_base.py` 절)
- **자금 사전 가드**: `state.is_low_funds_blocked(ticker)` 또는 `current_price > state.total_investment` skip. 후자는 `[risk_silent_skip] ticker= strategy= reason=price_gt_total_investment price= total=` INFO 를 1회/(ticker,전략)/일 남긴다(`_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]` — 매 틱 폭주 차단). `scheduler._reset_daily_state` → `RiskManager.reset_daily_state()` 위임 + AttributeError 후방호환 가드.
- **가격 필터(scanner 단계, 매수 진입 전용)** `_apply_price_filter` — `scanner.subscribe_filtered_stocks` 안의 단일 hook. 임계 = `system_config` 의 `price_filter_min`/`price_filter_max`(기본 비활성), 기준가 = `stock_master.raw.prdy_clpr` 단독, 미확보는 graceful 통과다(scanner 단계는 WS 구독 *전*이라 `current_price` 가 없고, KIS `inquire-price` pre-fetch 는 Rate Limit·hot path 부담으로 쓰지 않는다).
  - 60s TTL 캐시(`time.monotonic`) + `invalidate_price_filter_cache_scanner()` 즉시 무효화. **unsubscribe 발화 0건** — 다음 `_scan_loop` 5분 자연 delta 에 맡긴다(KIS LMS chain 차단).
  - 관측 = `[price_filter_scanner_skip] ticker=… prdy_clpr=… reason=below_min|above_max min=… max=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_price_filter_scanner_daily_summary()` 가 `[price_filter_scanner_daily_summary] min=… max=… skip_count=N` 1행(일일 카운터 `_price_filter_scanner_skip_count: dict[str, int]`, `_reset_daily_state()` 동행 리셋). 🔴 그 호출은 **try/except 로 감싸지 않는다** — 감싸면 폐기 메서드 잔존 호출 같은 결함이 AttributeError graceful skip 으로 조용히 먹혀 운영 가시화가 무력화된다. funnel `step_no=98`. UI `PriceFilterCard.tsx`.
  - 🔴 `risk.on_tick` 에 가격 필터를 두지 않는다(AST G-1 — 필터는 구독 대상 결정이고 매매 신호 판단이 아니다).
- **거래대금 필터(scanner 단계, 매수 진입 전용)** `_apply_trade_amount_filter` — 가격만으로는 작전주를 못 가른다는 판단의 동행 필터다(5,000원 통과 + 거래대금 5천만 = 작전 신호). 임계 `system_config.trade_amount_filter_min`(기본 0 = 비활성, UI 0~100억 step 1억 + 권장값 마커 1억/5억/10억), 조회 = `_get_trade_amount_filter_for_scanner`(60s TTL).
  - 소스 3분기(`_get_acml_tr_pbmn`) = `scanner.ticker_market_info["trade_amount_raw"]`(원 단위 정밀값 — scanner 가 `fetch_rising_stocks` → `fetch_stock_detail` 로 `acml_tr_pbmn` 을 이미 보강하므로 **KIS 호출 추가 0건**) → `stock_master.raw.acml_tr_pbmn` 폴백 → 🔴 **둘 다 miss 이거나 0 이면 graceful 통과**(09:00 직후 누적 거래대금 0 으로 후보를 막으면 시스템 매매가 통째로 무용해진다). 기존 `trade_amount`(억 단위 round) 키는 UI·API 호환으로 보존한다.
  - 순서 = `_apply_price_filter` → `_apply_trade_amount_filter` 순차 hook 이고, `subscribe_filtered_stocks` 4 호출 경로(tickers + extra_tickers + breakout/momentum for loop + swing)가 전부 지난다. 보호 종목은 `_collect_protected_tickers_for_scanner()` 재사용 + **별도** 60s TTL 캐시 + `invalidate_trade_amount_filter_cache_scanner()`.
  - 관측 = `[trade_amount_filter_scanner_skip] ticker=… acml_tr_pbmn=… reason=below_min min=…` INFO 1회/ticker/일 + `_settle()` 직전 `await _scanner_mod.emit_trade_amount_filter_scanner_daily_summary()` 가 `[trade_amount_filter_scanner_daily_summary] block_count=N` 1행(**try/except 로 감싸지 않는다**) + `_reset_daily_state()` 동행 `_scanner_mod.reset_trade_amount_filter_daily_state()`. funnel `step_no=97`(가격 필터 98 보다 *전* 단계 표기). 모듈 전역 4 필드 = `_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` / `_trade_amount_filter_scanner_skip_count_today: dict[str, int]`. UI `TradeAmountFilterCard.tsx`.

### 출처 절: market_regime.py

우리 `macro` 컨테이너(`GET /api/macro/macro-cycle`) 기반 시장 레짐 + cash_usage_ratio 자동 조정. **관찰 전용 — 매수를 차단하지 않는다.** `get_buy_block_state`/`buy_blocked` 프로퍼티는 표시·자문 payload 전용이다(매매 미소비).
- `MarketRegime.from_macro_cycle(macro)` — `/api/macro/macro-cycle` 응답 파싱(우리 macro 컨테이너 — `macro_lite` 코드라 응답 shape 가 고정이다). 🔴 `buffett_ratio` 는 `regime.buffett_ratio` 에서 읽는다(`params.pbr_max` 아님 — 그쪽은 PBR 상한이라 전 계층 null 을 만든다).
- `is_buy_allowed(strategy_id) -> bool` — 동기 회귀 가드 API (표시/자문 전용, 매매 미소비)
- **`get_buy_block_state() -> BuyBlockState` (async)** — 4 모드 분기. `BuyBlockState{mode, blocked, soft_multiplier, reasons, data_available}` 반환. DB 조회 실패 시 HARD + 기본 임계 fallback. 소비처는 대시보드 `/api/integrations/buy-block` 표시뿐이다. `buy_block_mode` 운영 DB 는 OFF 권장(정직 표시)
- **`get_buy_block_state()` 60s TTL 인스턴스 캐시** — `_buy_block_cache` + `_buy_block_cache_expires_at` 필드(`compare=False, repr=False`). `BUY_BLOCK_CACHE_TTL=60.0`, `time.monotonic()` 비교. DB fetch 폴백 분기는 캐시에 저장하지 않는다. `invalidate_buy_block_cache()` 로 운영 토글 즉시 반영
  - `DEFENSIVE_STAGES=frozenset({3,4,5})`(고지로 대순환 하락 사분면) + `is_two_day_defensive(stages)`(최근 2 스테이지 모두 방어집합, None/len<2→False = whipsaw 히스테리시스) + `EtfStageSignal` frozen dataclass + `get/set_current_etf_signal` 싱글톤.
  - `compute_etf_stage_signal(now=None)` async — KODEX200 069500 + 코스닥150 229200, 일봉 seam=`stock_master_daily.get_recent_daily` DESC→ASC 정렬 후 `kojiro_indicators.ema(5/20/40)`+`stage_of` 순차 → 각 지수 스테이지 + 2일 방어. `etf_defensive` = 신선 지수 OR, 양쪽 stale → None. 신선도 = `_is_daily_row_stale`(달력 `ETF_STALE_MAX_CALENDAR_DAYS=10`, never-raise).
  - **레짐 독립** — boot(`_refresh_market_regime_and_persist` 의 `set_current_regime` 직후)가 macro fetch 성패와 무관하게 계산하고 `[etf_regime]` 을 남긴다.
  - 🔴 **관찰만** — `get_buy_block_state`/blocked/reasons/soft_multiplier 무변경(배제 0). ETF 전용 5/20/40 파라미터화 금지(정체성 상수), kojiro 전략·파라미터·포지션 무접촉. ETF 스테이지를 매수 가드(`block_reason`·SOFT 상한·reasons)로 통합하지 않는다(사용자 결정 2026-09-27) — 장세에 따른 신규 진입 축소는 `market_unit.py` 가 전략 사이징에서 맡는다.
- **레짐 가드 silent inert 가시화 (관찰성 전용)** — `has_regime_data` property(`regime`/`vix`/`fear_greed_score` 중 하나라도 not None 또는 `bool(raw)`. `empty()` 폴백은 전부 None+raw={} 라 False 이고 `persist_snapshot` 의 `regime is None` empty 판정과 정합) + `BuyBlockState.data_available: bool=True` 필드 + `get_buy_block_state()` 5개 생성분(OFF/HARD/WARN/SOFT/unknown-fallback) 전부 `data_available=self.has_regime_data`. 🔴 blocked/soft_multiplier/reasons 로직과 60s TTL 캐시는 **무변경 = fail-open 보존**(신규 필드는 표시·경보 전용). 이유 = "데이터 있고 임계 미발동" 과 "데이터 없음(empty)" 이 같은 `blocked=False, reasons=[]` 라 운영자가 구분할 수 없다(외부 서버 인증서 만료가 4일 동안 무경보로 레짐을 무력화한 사례). boot 경보 = `get_buy_block_mode()` graceful 조회 후 `not has_regime_data and mode != "OFF"` 면 `[regime_guard_inert]` WARNING 1회/일.
- `to_advisor_dict()` 12 키 dict 반환 — AI 자문 user_payload 통합
- `refresh_from_dkstock(timeout=None)` — `macro_client` → MarketRegime. 모든 예외 흡수 → empty. 실패 사유는 `reason=disabled|timeout|fetch_failed|exception` 으로 구분해 WARNING 1행. 🔴 **`.env` 단독 veto 를 두지 않는다** — client 보다 앞에 두면 DB 우선 판정이 영구 도달 불가가 되어 운영 토글이 죽은 스위치가 된다. 🔴 **함수명은 계약이다** — `scheduler.py`(승인 대상)가 이 이름으로 부르므로 개명하면 무관한 승인 절차가 딸려 온다. `timeout` 은 부팅 경로가 더 짧게(`macro_api_boot_timeout_secs`=25s) 넘긴다 — 그 자리는 `boot_manager` 인라인 await 이고 바로 다음 줄이 자금 배분이라, 차가운 macro 가 재시작 직후 tick blind 창을 늘린다.
- **DB 우선 토글**: `macro_client._check_enabled_async` + `mcp_client._check_enabled_async` + `backtest_engine.is_enabled_async()` 가 `system_config.get_*` 먼저 → DB True/False 채택, None / 예외 시 `settings.*` (.env) fallback. 매 호출마다 DB 조회 — Settings UI 토글 즉시 반영

### 출처 절: order_engine.py

- **NXT 프리 시장가 매도 사전 지정가 변환**(매수 PR-F 대칭): `execute_sell` 이 프리장 단독(`PRE_NXT ∈ active AND MAIN ∉`) + `target_exchange ∈ (NXT, SOR)` + 시장가일 때 `step_down(현재가, 5)` 지정가로 사전 변환한다 — 매도는 호가 깊이로 **내려** 체결률을 확보한다. 실효 대상은 LTV 뿐이다(risk 게이트가 나머지 전략의 프리장 매도를 원천 차단). 현재가 미수신 시 무변환(임의 가격 지정가가 더 위험하다 — 시장가 거부 → market_closed 보류가 안전망이다). INFO `[sell_market_preconvert_pre_nxt]`. ⚠️ 거부 분류 검사 순서 = `is_market_closed_rejection` **먼저**(프리마켓 msg1 이중 매칭 시 보류로 낙하 = 의도된 계약, `src/api/CLAUDE.md` 분류 헬퍼 절) — 순서 반전 금지. 회귀 `test_order_engine_sell_pre_nxt_preconvert.py`
거부 분류 헬퍼(`is_market_closed_rejection` · `is_market_order_disallowed` · `is_insufficient_*` · `is_sell_qty_exceeded`)의 msg_cd·msg1 키워드 목록 정본 = `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절. 여기에는 분류 결과로 엔진이 하는 일만 적는다.
- **NXT 프리마켓 시장가 사전 차단 (preconvert)**: `place_order` 호출 *직전*, `MarketBoard.PRE_NXT in session_tracker.active` AND `MAIN not in active` AND `buy_exchange in ("NXT", "SOR")` 면 사전에 `step_up(current_price, 5)` 지정가로 변환. 변환 시 `state.pending_buy_amounts[ticker] = order_price × quantity` 동기 갱신, `record_price = order_price` 로 PENDING. INFO `[market_order_preconvert_pre_nxt]` 1행
- 매수가능 캐시 `BUYABLE_CACHE_TTL=60s` — KIS 호출 매 틱 → 분당 1회
- **`is_market_order_disallowed` 거부 → 지정가 5호가 폴백 1회** — `step_up(current_price, 5)` + `LIMIT`. 매핑 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, fallback_price)` 동기. 폴백 거부 시 cooldown
- 락/cooldown 은 다음 잔고 sync (15분) 에서 `unblock_buy()` + `clear_low_funds()` 일괄 해제. 🔴 `BUYABLE_CACHE_TTL=60s` / `BUY_BLOCK_DURATION=900s` / `LOW_FUNDS_COOLDOWN=900s` 를 바꿀 때도 sync(15분) 종료 시 일괄 해제 동작을 보존한다
- `limit_price > 0` 이면 `LIMIT` + `exchange="NXT"` 강제. 0 이면 시장가 + 전략 `_strategy_exchange()` 라우팅. 호가단위 정렬은 호출자가 `util.tick_size.step_down` 책임
- `KisApiError(insufficient_quantity)` 시 3회 재시도 생략 + 즉시 break + 메모리/DB positions 정리
- **`is_market_closed_rejection(err)`**(장운영시간 외) → 재시도 중단 + `state.positions`·DB 보존 + `_selling` **discard** + 다음 거래 시각 자연 재트리거. 🔴 `_selling` 을 보존하면 체결통보가 오지 않아 그것이 곧 stale `_selling` 좀비 = `risk.py` on_tick 손절 마비이므로 **반드시 해제**한다(이후 차단은 진입 게이트 `SellRejectionTracker.is_blocked()` 가 담당한다. cf. `_sync_positions_from_balance` 의 stale `_selling` 재대조 훅).
  - **NXT 불가 사후 보강**은 `target_exchange ∈ ("NXT","SOR")` ∧ KST **08:00~08:50**(NXT 프리마켓 실질 종료 = GTP 미체결 일괄취소 = `market_state` N1.end)일 때만 `stock_master.upsert_one(ticker, nxt_tradable=False)` 를 쓴다. 🔴 KRX 로 보낸 주문의 거부에는 **절대 쓰지 않는다** — KRX 애프터마켓(16:00~20:00)이 15:30~20:00 창 안에 통째로 들어 있어 시계 단독으로는 어느 시장의 거부인지 가릴 수 없고, 잘못된 낙인은 16:10 CTPF1002R 재적재 창을 지나치면 다음 영업일 프리장까지 ≈24h 존속하는 자기 강화 래치가 된다. 판단 불가를 fail-safe 로 쓰지 않는다. 마커 `[nxt_post_reinforce] ticker= exchange= div= now= wrote=1|0 reason=nxt_pre_window|exchange|window` — `wrote=0` 이 D+1 판독의 분모다.
  - **진입 게이트 2단계 TTL**: KRX 메인(09:00~15:30) 거부 = **5분 TTL**(일시 장애 가정) / NXT 시간대 거부 = **다음 KST 09:00 TTL**. TTL 미경과면 KIS 호출 없이 skip 하고 INFO `[market_closed_blocked]` 를 1줄/ticker/일 남긴다(`reason` 필드 포함). `SellRejectionTracker.register_market_closed(in_krx_main_hours=...)` 위임이고, `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 가 5 필드(`_alarm_last_emitted` 포함)를 일괄 위임한다 — `scheduler._reset_daily_state()` 의 위임 호출을 보존한다(`OrderEngine.reset_daily_state()` 캡슐화). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 을 직접 노출한다(`is` 동일성 보장 — 유지).
  - **폭주 알람**: `_append_history` 단일 진입점에서 10분 윈도우 5건 초과 시 CRITICAL `system_logs` INSERT + 30분 per-ticker cooldown. 임계 상수 `ALARM_WINDOW_SECONDS=600` / `ALARM_THRESHOLD=5` / `ALARM_COOLDOWN_SECONDS=1800`. fire-and-forget(`asyncio.create_task`) — 매매 hot path 블로킹 0.
- **`is_market_order_disallowed(err)` + `order_division==MARKET`** → 지정가 5호가 폴백 1회. `step_down(scanner.ticker_prices[ticker]["current_price"], 5)` + `LIMIT`. 폴백 결과(성공/실패) 무관 `SellRejectionTracker.register_market_order_disallowed(fallback_succeeded=...)` 위임 → **30초 TTL** 등록(동일 tick 폭주 차단). NXT 시간대 폴백 실패(`is_nxt_session=True, fallback_succeeded=False`)면 `RejectionResult.next_day_clear_required=True` → `_pending_next_day_clear_provider().add((ticker, strategy_id))` + `[next_day_clear_deferred]` WARNING 1행. 폴백 실패 시 `_selling.discard` + positions 보존(청산 의무 — 다음 사이클 재트리거). 🔴 매수(`block_low_funds` 900초)와 달리 매도는 cooldown 을 걸지 않는다 — 막는 것은 30초 TTL 뿐이다(청산 의무). 지정가 매도(`limit_price>0`)는 폴백하지 않는다.
- **`is_insufficient_quantity(err)`**(보유 수량 부족) → 재시도 중단 + 메모리/DB positions 정리. `SellRejectionTracker.register_insufficient_quantity` 는 history 만 적재하고 **차단하지 않는다**(positions 제거가 자연 차단이다) + `[positions_reconciliation]` INFO + `get_balance()` 1회 호출(실제 잔량 > 0 이면 재등록 권고 로그). 실패 graceful
- **`is_sell_qty_exceeded(err)` → #1.5 잔고 재대조** — APBK0400 "수량 초과" 는 부분 보유 내재 코드라 insufficient(통째 삭제)로 **흡수 금지**다(257720 실사고). `execute_sell` 재시도 루프에서 closed 다음·insufficient 앞에 `get_balance` 로 재대조한다. 분기:
  - ① 오염(`held < eff`) = **held(보유 실체)로 보정**(sellable 아님 — 잠긴 주식도 보유라 손절 감시 수량은 held 가 정합이고, sellable 부족 재거부는 다음 분기가 흡수한다) + `save_position` DB 동행 + `continue`(3회 한도 내 자기 치유).
  - ② 부분 잠김(`held ≥ eff`) = `fire = sellable − (held − eff)` 이 1 이상이면 그 수량만 판다(`[sell_qty_partial_sellable]`, `pos.quantity` 무변경). 0 이하이거나 주문 조회를 못 믿으면 보류한다.
  - ③ 전량 잠김(`sellable == 0 ∧ held > 0`) = 보류(`[sell_qty_locked]`).
  - ④ 실보유 0 = 기존 insufficient 경로 재사용 ⑤ 재대조 실패 = graceful 일반 재시도.
  - **보류** = 포지션 보존 + `_selling_locked_wait` 표식 + return(마커 `[sell_qty_partial_locked]`·`[sell_qty_unnoticed_fills]`·`[sell_qty_hold_orders_unavailable]`·`[sell_qty_locked]`). **`_selling` 은 의도적으로 유지**한다 — 열린 기주문이 실재하거나, 걸린 것이 없으면 운영자 몫을 팔지 않으려고 미통보 체결을 기다리는 보류이고(명세 부록 R4 D1), on_tick 재진입 폭주를 막는다. 어느 주문이든 종료 통보가 오거나 지키던 보유가 닫히면 푼다. stale 은 `[selling_reconcile]` 180s 재대조 소관이다. market_closed 의 discard 와 다른 이유 = 그쪽엔 열린 주문이 없다.
  - `eff`(= positions − 아직 안 온 체결 통보, `_sell_pending_dec`) · 주문 목록 조회(`_sell_orders_snapshot` — TTTC0081R `get_daily_orders(exchange="ALL", pdno=ticker)` 1건, 2.0초 상한) · 재대조 크레딧 · 보류 마커 판독의 정본 = 「매도 체결 — 주문 축과 보유 축」 절.
  - ⚠️ sync 는 기보유 종목 수량을 갱신하지 않으므로 DB 보정 실패 시 구값이 다음 보정·청산까지 남는다
- `_completed_orders` set + `update_trade_status` 영향 row 0건 보정 INSERT — 체결통보가 REST 응답보다 먼저 도착해도 단일 COMPLETED row 를 보장한다(매수·매도 양쪽 필수). 규칙 4개:
  - ① **부분체결(PARTIAL) 뒤 전량 체결**이 오면 1차 UPDATE 가 `match_partial=True`(PENDING∪PARTIAL + KST 당일 하한, **datetime 바인딩**)로 그 행을 COMPLETED 로 덮어 3단 우회(보정 INSERT → UniqueViolation → 강제 UPDATE)를 타지 않는다. 잔여취소 타이머는 `_pending_cancel_order_no[ticker] == order_no` 일 때만 cancel+pop 한다(`[partial_cancel_timer_cleared]`). 🔴 CANCELLED 호출은 `match_partial` 을 opt-in 하지 않는다(PARTIAL→CANCELLED 뒤집힘 금지).
  - ② PENDING INSERT 의 `await` 도중 체결통보가 먼저 완주해 migration 029 부분 UNIQUE 를 위반하면, `_insert_pending_or_absorb_race(side="buy"|"sell")`(**매수·매도 4 지점 공용** — 각 축의 시장가·폴백)가 **`order_no in _completed_orders` 일 때만** 흡수·discard 하고 `[buy_fill_during_insert]`/`[sell_fill_during_insert] ticker= order_no= strategy= path=market|fallback` INFO 1행을 남긴다. 🔴 증거 없는 위반은 그대로 전파한다(다른 원인 은폐 금지) — 무조건 삼키기·재시도 INSERT 로 바꾸지 않는다. 회귀 `test_cycle271_execute_buy_fill_during_insert.py` · `test_cycle327_sell_fill_during_insert.py`
  - ③ `update_trade_status(*, order_no=None, match_partial=False)` 의 `order_no` 는 keyword-only opt-in 이고 미전달 시 SQL 이 byte 동일하다. `order_engine.py` 의 호출 6곳(C1 매수 COMPLETED · C2 매수 PARTIAL · C3 매도 COMPLETED · C4 매도 PARTIAL · C5 `_cancel_after_wait` 매수 CANCELLED · C6 `_cancel_and_reorder` 매도 CANCELLED)이 전부 지역 변수 `order_no` 를 그대로 전달해 WHERE 를 **그 주문 한 건**으로 좁힌다 — 근거 = order_no 없는 WHERE 가 같은 `(ticker, trade_type, strategy)` 의 **다른 주문 행**까지 덮어 한 체결통보가 여러 PENDING 행에 같은 price·profit_loss 를 도배한 사고(161580). `affected>1` 이면 `src/db/trade_history.py` 한 곳에서 `[trade_status_multi_update]` WARNING — order_no 있는 호출은 부분 UNIQUE 인덱스(migration 029) 때문에 구조적으로 발화 불가라 **과거 측정기가 아니라 WHERE·인덱스 후퇴 회귀 감시자**다.
  - ④ 🔴 **`place_order` 가 성공한 뒤의 실패는 「발사 실패」가 아니다** — 매핑 등록 이후 구간(선행 체크·PENDING INSERT)은 축별 경계 래퍼(`_persist_buy_pending_after_send`·`_persist_sell_pending_after_send`)가 자기 `except Exception` 으로 닫고 **재시도 루프로 돌아가지 않는다**(코어·래퍼 구조 · 마커 2종 · `except` 좁히기 금지 · 묶인 자금 = 위 「접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2」 절). 래퍼가 막는 피해는 매도 두 호출부에서 모양이 다르다 — 주 경로에서 새면 재시도 루프 → **그 종목 중복 매도**, 폴백은 `except KisApiError` **안**이라 형제 핸들러가 non-`KisApiError` 를 못 받아 `execute_sell` 을 관통 → **`risk.on_tick` 사망 = 그 틱의 전 보유 종목 손절 평가 소멸**.
    - 매도 재시도 루프는 발사 직전 `strategy.state.positions.get(ticker)` 를 **재조회**해 포지션이 사라졌으면 `[sell_position_gone]` 1행 후 중단한다(루프 밖 지역 참조 `pos` 는 체결 뒤에도 옛 수량을 들고 있다 — 피라미딩에서는 그 재조회가 수량의 유일한 진실원이 된다). 회귀 `test_cycle327_sell_fill_during_insert.py::test_sell_does_not_refire_on_generic_insert_error`
    - 래퍼 **앞부분에 `await` 를 넣지 않는다** — 최초 양보점이 `await insert_trade` 라는 사실이 「매핑은 동기 영역」 금기의 전제다(`test_g328_2`). 매도 래퍼 값 4개(`record_price`/`quantity`/`path`/`order_no`)는 `test_order_engine_sell_fallback.py` 시나리오 J 3건이 봉인한다(맞바꿈·뭉갬이 광역 스위트를 전부 초록으로 통과하던 자리다).
- **NXT 거래가능 사전 차단**: `_probe_nxt_downgrade_base(strategy_id, ticker)` 가 `stock_master.get(ticker).nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 1행. 캐시 miss·예외 시 전략 기본 exchange(보수적 fallback). 익일 청산 NXT 지정가(`limit_price>0`)는 사전 차단을 적용하지 않는다. 로그는 ticker 별 **1회/일 cap**(`_nxt_downgrade_logged_today: set[str]`, `OrderEngine.reset_daily_state()` 동행 clear)이고 **다운그레이드 결정(`return "KRX"`)은 cap 밖**이다 — 100회 호출 모두 정상 KRX 를 반환한다.
- **규칙 1 — 시각이 거래소를 정한다(cycle287).** `_probe_nxt_downgrade_base` 가 정한 다운그레이드 결과(`base`) **뒤**에, `_strategy_exchange_async`(반환 시점 1회) · `_apply_clock`(그 밖 4곳)이 순수 함수 `_route_exchange_by_clock(base, *, side, mode, now)` 로 감싼다. 판정은 `market_state.MARKET_TABLE` 단일 정본만 읽는다(`order_engine.py` 안 시각 리터럴 0건).
  - clause 순서 = `base ∉ {"NXT","SOR"}`(이미 KRX)→그대로 / `mode=="off"`→그대로 / `mode=="sell_only" ∧ side=="buy"`→그대로 / `session_tracker.active` 가 `PRE_NXT` 단독(PR-F 와 같은 출처, 08:50~09:00 NXT 휴장 구간도 이 판정으로 base 유지)→그대로 / 그 시각 KRX 가 우리 `OrderDivision` 값 집합(`_SENDABLE_DIVISIONS`) 중 하나라도 받으면 `"KRX"` / 아니면 그 시각 NXT 가 받으면 base 유지 / 둘 다 안 받으면 base 유지.
  - 예외는 전부 `probe_error` 로 base 유지(fail-safe — 판정 실패가 주문을 막지 않는다). `active` 가 비었을 때만(기동 직후 첫 `tick()` 전) `session.boards_at(moment.time())` 로 즉석 재계산하는 폴백이 clause 4 를 지킨다 — 없으면 08:20~09:00 프리장 창이 KRX PRE_AUCTION 으로 조용히 샌다.
  - 적용 지점 = `_strategy_exchange_async` 반환 1 + `_apply_clock` 4(`limit_price>0` 분기·`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`)이고 mode/dial 조회는 `_clock_params` 공유다. 마커 `[order_channel] side= ticker= strategy= base= exchange= reason=`(`routed≠base` 일 때만. 단 `probe_error` 는 게이트 밖에서 항상 남긴다 — 라우팅이 죽은 것과 정상 유지(`pre_nxt_keep` 등)가 똑같이 침묵하면 안 된다) + `[order_channel_config] strategy= mode= division=`(카나리아, 1회/(전략,mode,dial)/일).
- **규칙 2 — KRX 애프터마켓(16:00~20:00) 청산 호가(cycle287).** `execute_sell` 이 프리장 사전 변환 **뒤** · 재시도 루프 **앞**에서 `order_division==MARKET ∧ target_exchange=="KRX" ∧ settings.is_production ∧ market_state.get_market_state(now,"KRX").phase is AFTER_MARKET` 이면 전략 params `after_market_exit_division`(화이트리스트 `{"44","41"}`, 기본·미지값 폴백 `"44"`)에 따라 `44`(최유리지정가, `ORD_UNPR=0`) 또는 `41`(지정가, `step_down(현재가,5)`, 현재가 미확보 시 변환 취소)로 사전 변환한다 — VTS 는 41~47 지원 여부가 정본에 없어 무접촉이다. 재시도 루프의 폴백 게이트는 `order_division==primary_div ∧ (is_market_order_disallowed(e) ∨ primary_div≠MARKET)` 다 — 정규장·프리장은 `primary_div is MARKET` 이라 분류 기반이고, 애프터는 **분류에 의존하지 않는 구조적 폴백**(msg1 원문이 미지라 키워드에 폴백을 인질로 주지 않는다)이다. 폴백은 `fallback_div`(44→41, 41→41)로 1회. `src/models/order.py::OrderDivision` 에 `KRX_AFTER_BEST="44"`(1차) · `KRX_AFTER_LIMIT="41"`(폴백) 2종이 있고, 🔴 **IOC/FOK(42/43/45/46)·최우선지정가(47)는 추가하지 않는다** — 잔량 자동취소·비크로스라 손절 수단으로 부적합하다.
  - 🔴 **44 는 시장가가 아니다** — 반대편 최우선호가 지정가라 실질 최악이 1틱이다. `ORD_UNPR=0` 의 근거는 비대칭이다: 0 이 틀리면 즉시 거부가 알려 주고 41 폴백이 받지만, 가격이 틀리면 미체결 잔존 = 손절 **무음** 실패다.
  - **봉인 3종**: ① `register_market_order_disallowed` 는 분류·성패 무관 **항상** 호출한다(TTL 30초). `cur_price<=0`(폴백 자체를 못 내는 경로)과 `market_closed` 분류(검사 순서 1번이라 폴백에 도달하지 않는 경로)에도 공용 헬퍼 `_register_after_exit_disallowed`/`_bump_after_exit_fails_and_maybe_giveup` 로 걸린다 — 빠지면 애프터마켓의 실시간 연속체결에서 브레이크 없이 반복 재시도한다. `ttl_registered=` 는 그 등록 성공 여부를 실제로 싣는다. ② 종목당 그 저녁 실패(주문 사이클 단위)가 `_AFTER_EXIT_GIVEUP_THRESHOLD=5` 에 도달하면 `[after_exit_giveup]` CRITICAL + `register_market_closed(in_krx_main_hours=False)`(다음 09:00 TTL, 30초 TTL 뒤에 등록해 덮어쓴다) + `_pending_next_day_clear` 등록으로 그날 밤을 포기한다. ③ TTL 축 `_exit_capable_krx_window(now)` — `register_market_closed(in_krx_main_hours=...)` 인자의 의미를 "그 시각 KRX 가 우리 청산 호가를 받는가"(`_EXIT_CAPABLE_KRX_PHASES = {REGULAR, CLOSE_AUCTION, AFTER_MARKET}`)로 정의한다(`sell_rejection.py` 자체는 무접촉이다).
  - 손절 잔여 재주문(`_cancel_and_reorder`)도 같은 창에서 시장가(price=0) 대신 창 호가쌍으로 교체한다(정규장·프리장은 byte 동일). ETP 관측 `_observe_after_exit_etp` → `[after_etp_exit_observe]`(`stock_master.raw.scty_grp_id_cd ∈ {EF,EN,FE}`)는 애프터 1차 거부 **직후에만** 발화하고 `asyncio.create_task` fire-and-forget 이다 — 행복 경로와 손절 크리티컬 패스에 DB 왕복을 얹지 않는다(행위 분기 없음).
  - 취소 `ORD_DVSN` 은 `"00"` 하드코딩 유지 — 국내주식 스펙에 원주문 호가유형 승계 규약이 없고 그 창의 취소 실적이 all-time 0건이라 추측 변경이 더 위험하다.
  - 🔴 **취소는 원주문의 거래소로 나간다** — `place_order` 응답 직후 동기 영역에서 `self._order_exchange[order_no] = <그 주문의 실제 거래소>` 를 등록하고(기존 `_order_qty`/`_order_strategy`/`_order_ticker` 와 같은 자리·같은 정리 주기), 취소 3경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)는 그 값을 우선 쓰고 매핑이 없을 때만 라우터로 fail-open 한다. 없으면 `PARTIAL_FILL_WAIT`(30초) 동안 시간 경계를 넘긴 취소가 원주문과 다른 거래소로 나간다. 관측 `[after_cancel_result] ticker= order_no= ord_dvsn=00 exchange= result=ok|error err=`(`ORD_DVSN="00"` 하드코딩·`cancel_order` 시그니처 byte 동일).
- **장중 킬스위치 2키** `order_exchange_clock_mode`(기본 `enforce`) · `after_market_exit_division`(기본 `"44"`) — 7 전략 전부의 `DEFAULT_PARAMS` + `param_catalog`(`risk="identity"` 2단계 확인)에 코드 상수와 같은 값으로 등재돼 있어 `PUT /api/strategies/{id}/params` 가 즉시 통한다. `param_validation` 의 미지 키 판정이 `key not in current_params or spec is None` 이라 카탈로그 등재만으로는 부족하고 `DEFAULT_PARAMS` 등재가 함께 필요하다. `PARAM_RANGES`/`INT_PARAMS` 편입 금지 — AI 자문이 청산 수단을 끄는 스위치를 뒤집으면 안 된다.
  - ⚠️ **두 키는 전략별이다**(전역 스위치 없음) — 사고 중에 보유 전략이 여럿이면 그 전략 각각에 PUT 한다. 사고 중 조작 순서(거부/미체결/악체결 3분류 + 5단계)는 `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절이 정본이다.
  - ⚠️ **두 키는 `exchange ∈ {"NXT","SOR"}` 일 때만 효력이 있다** — `_route_exchange_by_clock` clause 1(`base ∉ {"NXT","SOR"}`→그대로)이 mode 검사보다 **앞**서므로, `exchange` 가 `"KRX"` 인 전략은 `enforce`/`sell_only`/`off` 세 값이 전부 동일한 무동작이다. 코드 기본값은 7전략 전부 `"KRX"` 라, 두 스위치는 운영 DB `exchange` 가 `NXT`/`SOR`(`_CLOCK_ROUTED_BASES`)인 전략에서만 작동한다. `exchange` 를 KRX 로 마이그레이션하는 사이클은 이 두 키의 help 도 함께 갱신한다.
  - ⚠️ **비상정지는 `off` 보다 `PUT {"exchange":"KRX"}` 가 안전하다** — `off` 는 라우팅 전체를 죽여 44/41 애프터 청산 변환까지 함께 꺼뜨리지만(그 게이트가 "거래소가 KRX 인가" 이므로), `PUT {"exchange":"KRX"}` 는 clause 1 이 mode 검사보다 앞에서 발화해 KRX 로 고정되면서 44/41 전환을 보존한다(부작용은 프리장 주문도 KRX 로 가는 것 하나뿐).
  - ⚠️ `order_engine.py` 의 `_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT` 위 주석(「두 신규 파라미터는 어느 전략 `DEFAULT_PARAMS` 에도 없다」)과 `param_validation.py` 모듈 docstring 의 「99 스펙」(실제 개수 = `len(param_catalog.SPEC_BY_KEY)`)은 낡았다 — 두 파일 모두 무접촉 계약 대상이라 다음 8영역 승인 사이클의 과제다.
- 🔴 **규칙 3 — 15:30~16:00 은 완전 휴식이다(cycle295).** 라우터(`_route_exchange_by_clock`) **밖**의 순수·never-raise 술어 `_market_rest_now(now) -> (blocked, reason)` 를 **주문 발사점 3곳**(`execute_sell` 의 `target_exchange` 산출 직후·재시도 루프 앞 / `execute_buy` 의 중복매수 가드 직후·`get_buyable` 앞 = A-ATOMIC **밖** / `_cancel_and_reorder` 의 `sleep(30)` 뒤·`cancel_order` 앞)에만 건다. **시각 리터럴 0건** — 경계는 전부 `market_state.get_market_state(now, market=...)` 파생이다.
  - **왜 라우터 밖인가** — `_strategy_exchange_async` 는 `_probe_nxt_downgrade_base` 를 먼저 부르고, 그 함수는 `stock_master.nxt_tradable=False` 종목에 `"KRX"` 를 돌려준다. 그 코호트(마스터의 다수)는 라우터에 `base="KRX"` 로 들어가 clause 1 에서 **즉시 반환**되어 뒤 clause 에 닿지 않는다 — 라우터 안에 컷을 넣으면 컷이 가장 필요한 다수 코호트를 통째로 비껴간다.
  - **판정** = 프리장(`session_tracker.active` 가 `PRE_NXT` 단독, 라우터 clause 4 와 **같은 출처**)→`pre_nxt_keep` / 그 시각 KRX 가 `_SENDABLE_DIVISIONS` 중 하나라도 받으면 →`krx_sendable` / KRX·NXT 둘 다 세션이 없으면 →`no_session`(야간 안전망 보존) / 그 밖 →**`market_rest`(컷)**. 판정 예외는 `probe_error` **fail-open**(컷하지 않는다).
  - **`_cancel_and_reorder` 는 쌍으로 막는다** — 이것만 `cancel_order` → `place_order` 의 atomic replace 다. 절반만 막으면 "호가창에 있던 손절을 우리가 빼고 아무것도 안 넣은" 상태가 된다. 컷이면 **취소도 하지 않고** 작동 중인 주문을 그대로 둔다.
    - 🔴 **그 잔량을 우리가 거두는 경로는 없다.** `cancel_remaining` 은 `src/` 안에 호출자가 0 이고, 배선해도 해결되지 않는다 — 그 함수는 `pos.order_no`(포지션을 만든 **매수** 주문번호)를 취소한다. `risk.on_tick` 재평가도 새 매도를 낼 수는 있어도 걸린 주문을 취소하지 않는다.
    - 잔량의 운명은 거래소가 정한다(아래 session.py 절 「주문 존속 규약이 거래소마다 반대다」) — KRX 잔량은 정규장 마감 후 거래소가 자동 취소하고, NXT 잔량은 애프터마켓이 끝나는 20:00 까지 남는다. `execute_sell` 의 매도가 KRX 가 아닌 곳(base `NXT`/`SOR`)으로 나가는 것은 규칙 1 이 base 를 유지할 때뿐이다(프리장 `pre_nxt_keep` · `order_exchange_clock_mode="off"` · `probe_error`). KRX 가 우리 호가를 받는 시각(09:00~15:30 · 16:00~20:00)에는 clause 5 가 KRX 로 보낸다.
  - **컷이 「하지 않는」 것 4** — 거부 등록 안 함(`SellRejectionTracker` 에 걸면 NXT 시간대 TTL = 다음 09:00 이라 그 한 건이 16:00~20:00 KRX 애프터 청산 4시간을 잠근다) · 익일청산 미전환(16:00 에 KRX 애프터가 열리므로 컷은 취소가 아니라 **최대 20분 유예**다) · 포지션 불변 · `_selling` **유지 금지**(유지하면 그것이 곧 stale `_selling` 좀비 = 손절 마비).
  - **마커 2종** — `[market_rest_blocked] side= ticker= strategy= base= reason=`(1회/(ticker,side)/일, **이 규칙이 무엇을 잃는지의 유일한 분모**) + `[market_rest_window] start= end= source=market_table`(1회/일 카나리아, 차단 0건인 날에도. `start`/`end` 는 리터럴이 아니라 표에서 역산). 둘 다 `KstDailyEmitCap` + never-raise 이고 **행위는 cap 밖**이다.
  - 🔴 **신선도 기반 해제를 들이지 마라** — `scanner.ticker_last_tick` 신선도로 컷을 풀면 안 된다. ① `risk.on_tick` 이 **같은 콜스택**에서 그 dict 를 먼저 쓰고 곧바로 `execute_sell`/`execute_buy` 를 부르므로 게이트가 재는 틱 나이가 **항상 0.0초**다(그 구간의 청산 트리거는 WS 틱 단독 — REST 폴은 15:20 에 끝난다). 즉 컷이 막으려던 유일한 경로가 정확히 컷을 100% 해제한다. ② KRX **K5**(15:30~16:00 장후 시간외 종가, `fixed_price ('06',)`)가 **같은 채널 `H0STCNT0`** 로 실제 체결 프레임을 보낸다 — "틱이 온다" 와 "우리 호가유형이 접수된다" 는 분리된 사실이다.
  - ⚠️ **남은 한계** — `market_state` 표는 날짜 범위만 보는 고정 벽시계라 **특별 개장일(지연 개장, 수능일이 표준 사례)을 모른다**. 그런 날 15:30~16:00 은 실제로 연속체결 중인 정규장인데 컷이 **30분 무음 차단**한다(연 1회 수준). 닫는 방법은 신선도가 아니라 **표에 거래일·특별일 입력을 넣는 것**이다(별건 카드).
  - ⚠️ **면제 경로 = `POST /api/trading/manual-sell`.** 그 라우트는 `place_order` 를 직접 불러 `execute_sell`·`_apply_clock`·`_route_exchange_by_clock` 을 하나도 거치지 않으므로 게이트에 닿는 경로가 **구조적으로 없다**(운영자 수동 조작은 막지 않기로 한 결정). 그 구간엔 응답 message 에 경고가 붙고 접수 로그에 `[market_rest_manual_exempt]` 가 찍힌다 — **D+1 에 그 구간 주문이 1건 나오면 이 라우트를 먼저 본다.**
  - ⚠️ **판독 보조** — 컷 창 판정의 프리장 예외는 `session_tracker.active`(30초 주기 전역 캐시, `now` 와 무관)를 먼저 보고 비었을 때만 `boards_at(now.time())` 로 폴백한다. `stop`/`start` 가 보드 경계를 가로질러 캐시가 낡으면 컷이 조용히 풀리거나(캐시 `{PRE_NXT}` × 벽시계 15:45) 08:00~08:19 프리장 주문이 무주문으로 잘릴 수 있다(캐시 `{MAIN}`/`{POST_NXT}` × 벽시계 08:0x). `_session_loop` 이 도는 동안 staleness 는 30초로 묶인다. **`[market_rest_window]` 는 있는데 `[market_rest_blocked]` 가 0 인 날**은 ⓐ 그 구간 손절 신호 자체가 없었는지 ⓑ 세션 캐시가 낡았는지 두 가지를 먼저 본다.
  - ⚠️ **컷에는 장중 다이얼이 없다** — 위 킬스위치 2키와 별개이고 `order_exchange_clock_mode` 에 **종속시키지 않는다**(롤백 다이얼 하나가 방금 없앤 참여를 조용히 되살리면 자기모순이고, 종속시키면 44/41 KRX 애프터 청산 변환도 함께 꺼진다). 롤백 수단은 **1커밋 revert + 장외 배포**뿐이다.
  - ⚠️ **15:20 강제청산과의 경계** — `_force_clear_main_only` 는 진입 시 15:30 가드로 skip 하지만, 15:20 에 시작한 순차 루프가 15:30 을 넘기면 남은 종목은 조용히 컷되어 익일청산 안전망으로 밀린다. 그 경우 `[market_rest_blocked] side=sell` 이 남는다.
  - **매수만, `27` 만.** 매수 PR-F 사전 지정가 변환 블록(`order_price=step_up(현재가,5)` 확정 **뒤**) 안에 게이트 4중이 붙는다 — `settings.is_production` ∧ `buy_exchange=="NXT"` ∧ `"27" in get_market_state(now, market="NXT").order_divisions` ∧ 이미 참인 프리장 판정. 시행일·프리마켓 종료 08:50 경계는 `market_state.py` 표에서만 읽는다(날짜·시각 리터럴 신규 0건). 넷 중 하나라도 실패·예외면 이미 확정된 `00`(LIMIT)이 그대로 나간다(순수 옵셔널 승격, fail-safe). `ORD_UNPR` 은 `00` 이 보내는 값과 **완전히 같다**(`step_up(현재가,5)`) — 가격 행위 변경은 0 이고 바뀌는 것은 08:50 이후 미체결의 **수명**뿐이다.
  - 🔴 **매도는 무접촉이다**(`execute_sell` 프리장 사전 `step_down` 변환 그대로) — GTP 매도는 08:50 자동취소가 `_selling` 을 ≈09:45(`_scan_loop` 첫 sync)까지 잠가 손절 재평가를 억제하고, 현행 `00` 은 09:00:30 NXT 정규장에서 시세 아래 지정가라 거의 확실히 체결돼 안전망으로 기능한다(루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉 판정).
  - **화이트리스트 제거** — `place_kwargs["order_division"]` 게이트가 `!= OrderDivision.MARKET` 이고 `record_price` 게이트도 같다. 🔴 열거(`== OrderDivision.LIMIT`)로 되돌리면 새 호가유형이 조용히 시장가로 떨어지거나 기록 가격이 변환 전 값으로 샌다.
  - **GTP 거부 폴백** — `27` 거부는 `_MARKET_ORDER_DISALLOWED_KEYWORDS`/`_MARKET_CLOSED_KEYWORDS` 어디에도 안 걸려 미분류로 `raise` 되면 `risk.on_tick` 을 죽인다. 그래서 폴백 게이트를 키워드가 아니라 **"우리가 27을 보냈다"는 사실**(`order_division is OrderDivision.NXT_GTP_LIMIT` — `src/models/order.py` 의 `NXT_GTP_LIMIT="27"`)에 걸어 같은 가격 `00` 1회로 즉시 재주문한다(`[pre_nxt_gtp_fallback] ticker= reason=rejected msg_cd= msg1=`). 정규장·프리장·애프터의 기존 `is_market_order_disallowed` 폴백 경로는 byte 동일하다.
  - **마커** `[market_order_preconvert_pre_nxt]` 는 기존 4필드(`ticker/exchange/current_price/converted_to_limit_price`) byte 보존 + 꼬리 append `div= gtp=0|1 reason=ok|vts|exchange|not_effective|probe_error`. **`[pre_nxt_division_config] division=27 effective= production= exchange_gate=`** 는 1회/일 카나리아다(프리장 매수가 대부분의 날 0~2건이라 위 마커만으로는 "게이트가 무장됐는가" 를 볼 채널이 없다). ⚠️ **그날 첫 매수 후보가 이 블록에 도달해야만 발화한다** — 후보가 0건인 날은 이 카나리아도 침묵한다(무코드 대안 = `GET /api/market-state?market=NXT` 로 `order_divisions` 에 `27` 존재 여부를 사람이 1회 확인).
  - **알려진 비용 — GTP 08:50 자동취소 잔존 상태.** 취소 통보(같은 주문번호의 두 번째 접수 전문 — KIS 주문내역 기록은 `GTP매수자동취소*`)는 체결통보 채널로 **오지만**, `handler.py::_handle_execution` 은 `CNTG_YN != "2"` 프레임을 `[order_notice]` 로 **기록만** 하고 콜백으로 넘기지 않는다(`src/realtime/CLAUDE.md` 「접수 전문 기록」). 그래서 자동취소된 주문의 `pending_buys`/`pending_buy_amounts`/`_pending_buy_orders` 와 `trade_history` PENDING 행은 **그날 첫 잔고 sync(≈09:45)까지** 남아, 그동안 `is_ticker_blocked_for_buy` 가 그 종목 재진입을 막고 예산·슬롯을 점유한다. sync 때 `buying_reconcile`(모듈 맵)이 그 주문의 KIS 행(`tot_ccld_qty==0 ∧ rmn_qty==0`)을 보고 세 필드를 풀고 행을 CANCELLED 로 적는다. `_order_qty`/`_order_strategy`/`_order_ticker`/`_order_exchange`/`_order_division` 은 늦은 체결통보 안전망이라 21:30 `reset_daily_state()` 까지 일부러 남긴다. GTP 는 이 빈도를 **늘린다**(08:50 까지 안 채워진 모든 프리장 매수가 대상 — `00` 은 09:00:30 정규장 이월로 일부가 조기 정리된다). 순수 기회비용이고 자본 위험은 아니다.
    - 통보로 즉시 정리하는 경로는 없다. 만들려면 `handler.py` + `order_engine.py`(**둘 다 8영역, 승인 필요**, `scheduler.py` 무접촉)를 바꿔야 하고, 접수 전문과 취소 전문을 가르는 판별 필드를 확정하지 않고 분기를 짜면 접수 통보를 취소로 오인해 **살아 있는 주문의 상태를 지운다**. 판별 필드 실측과 진행 상태 = `_workspace/00_URGENT_WORKLIST.md` ⑨B. 원문 payload·개인정보 칸 로깅 금지 = `src/realtime/CLAUDE.md` 「접수 전문 기록」.
  - **취소 축 Stage A** — `_order_exchange` 와 완전 대칭인 `OrderEngine._order_division: dict[str, str]`(order_no → 실제 전송한 `ORD_DVSN`, 등록 4곳·pop 2곳·`reset_daily_state()` clear — `scheduler.py` 는 무참조)이 있고, `api/order.py::cancel_order` 에 키워드 전용 opt-in `order_division: str | None = None` 이 있다(falsy → `"00"`, 미전달 시 body 10키 byte 동일). 🔴 **호출자 3곳(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)은 전달하지 않는다** — 정본에 취소 시 원주문 호가유형 승계 규약이 없고, 전송을 켜면 실적 있는 정규장 부분체결 취소의 `ORD_DVSN` 이 `00`→`01`(원주문 시장가)로 바뀐다. `[after_cancel_result]` 가 `orig_dvsn=`(매핑값, 부재 시 `-`)·`dvsn_src=map|absent` 를 실어 층화 실측(비-`{00,01}` `orig_dvsn` 행만 `result=error` 면 Stage B 전송 검토 = 매매 행위 변경이라 별도 승인)의 근거가 된다.
  - 회귀 가드 = `tests/unit/engine/test_cycle291_pre_nxt_gtp.py` · `tests/unit/ast/test_cycle291_ast_scope.py`(금지 파일 무접촉 · `scheduler.py` 라인 상한 · `_SENDABLE_DIVISIONS` 확장 라우팅 무영향 봉인 + 취소 호출 3곳 소스 전수 `order_division` 미전달 봉인 + 매핑 등록이 `place_kwargs` 파생값을 읽는지 구조 확인).
- 매수 → DB `positions` 저장 + `cached_buyable_at=0` (가용액 캐시 무효화)
- 매도 → 보유가 남으면 차감 수량을 DB `positions` 에 저장하고 끝난다(「매도 체결 — 주문 축과 보유 축」 절). 보유가 0 이 되면 DB positions 삭제 + `sold_today` 등록 + (주문 종료 분기에서) **WS 구독 정리 hook** — `_unsubscribe_if_no_other_strategy(ticker)` 가 (a) `registry.is_ticker_held_by_any(ticker)=False` + (b) `_pending_next_day_clear` 부재 + (c) 모든 전략 `get_scanned_tickers()` 부재 — 모두 통과 시 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)`(KIS 정상 패턴 "불필요 종목 구독해제"). `_pending_next_day_clear_provider` 는 scheduler 가 `OrderEngine.__init__` 직후 주입한다(lambda)

### 출처 절: session.py

`MarketBoard` enum 5종 중 **실제로 쓰는 것은 3종**이다(`KRX_OPEN`·`KRX_AFTER` 는 비활성이고 enum 값만 DB 파라미터 호환 때문에 남겼다 — `session.py::MarketBoard` docstring 이 정본).
`_BOARD_SCHEDULE` 실제 구간 = `pre_nxt` **08:00~08:59:59** / `main` **09:00~15:39:59**(15:20~15:30 buy_stop
구간 + 15:30~15:40 갭 마진 포함) / `post_nxt` **15:40~19:59:59**. `krx_open`(08:30~09:00)·`krx_after`(15:30~18:00)
는 **표에 없다**.
- `on_h0nxmko0(...)`: NXT 장운영정보 수신 (KIS 명세 미확정 → 코드 기록만)

### 출처 절: session.py › 시장 시간표 — 정본은 `market_state.MARKET_TABLE`

`_BOARD_SCHEDULE` 은 우리 **보드** 구간이고, 실제 거래소 세션·호가유형은 `market_state.MARKET_TABLE` 이 정본이다. 근거 = 한국투자증권 고객 공지(거래시간·가격제한·미체결 규약) + Open API 공지 2026-09-09(TR·필드 변경분은 `docs/kis/README.md` 「제도 변경 공지 반영」 절이 정본).
**애프터마켓(K6) 상세** — 가격제한 **전일 KRX 정규장 종가 ±30%** · 호가유형은 지정가 계열 **7종만**
(`ORD_DVSN` 41~47, `docs/kis/domestic-stock-order.md`) · **시장가 불가** · **ETP(ETF/ETN) 제외** ·
수수료·세금은 정규장과 동일 · SOR 가능.
🔴 **주문 존속 규약이 거래소마다 반대다** — KRX 는 정규장 마감 후 미체결이 **자동 취소**되므로 애프터마켓에서
거래하려면 16:00 이후 **새로 주문**해야 한다. NXT 는 미체결이 애프터까지 **유지**된다. SOR 주문도 주문이
들어간 시장에 따라 자동취소될 수 있다. NXT 프리마켓은 `GTP` 전용호가(`27`)가 있고 08:50 에 미체결을 일괄취소한다.
**`_BOARD_SCHEDULE` 과의 남은 어긋남 2건**(시정 사이클은 `_workspace/00_URGENT_WORKLIST.md` 의 보드 재설계 C0~C6)

### 출처 절: scheduler.py — KRX/NXT 통합 운영 08:00~20:00

| `TIME_BOOT` | 07:55 | **런타임 미사용 상수** — `_boot()` 는 이 시각을 기다리지 않고 `scheduler.start()` 안에서 **즉시** 실행된다(07:45 자동 기동이면 그 직후, 수동 재기동이면 그 시각). `src/` 안 참조는 정의 1줄과 `realtime/websocket.py` 주석뿐이고, 테스트 핀(`tests/unit/engine/test_cycle92_time_boot_moved.py`)이 값 07:55 를 잡고 있어 지우지 않는다. `_boot()` 본체는 `src/engine/boot_manager.py::boot(scheduler)` 위임(2줄 wrapper). `_preissue_all_tokens()`(메인+보조 N 매니저를 분당 1개 한도로 직렬화 사전 발급) → DB positions 복구 → KIS 잔고 교차 검증 → 미체결 복구 → `_eager_refresh_stock_master_for_held_positions()`(보유 + 익일청산 후보 ticker 를 `stock_master` eager 갱신) → 매크로 fetch + `market_regime_snapshots` INSERT → `cash_usage_ratio` 자동 조정 → **`portfolio_risk.check_budget_invariant`**(`position_ratio × max_positions > 1.0` 위반 시 `[budget_invariant_violation]` WARNING, **차단 아닌 관찰**) → `allocate_funds(net_asset × ratio)` |
| `TIME_PRESUBSCRIBE` | 07:59 | `_collect_presubscribe_tickers()` — VB/LTV/donchian + 모든 전략 보유 합집합 사전 구독. 그 직전에 돌파 후보가 비었으면 VB/LTV 를, 후보가 빈 스윙 전략을 `funnel_capture.live_prepare_one(…, phase="presubscribe")` 로 다시 준비한다(부팅 준비 실패 회복용) |
| `TIME_PRE_NXT_OPEN` | 08:00 | 익일 청산 task (`_execute_next_day_clear`, `NEXT_DAY_STABILIZE_SECS=30s`) + `_confirm_breakout_open_prices(board="pre_nxt")`(LTV `pre_nxt` 보드 시가 확정. VB 는 `tradable_boards=("main",)` 라 대상 없음) |
| `status_exit_watch` 패스 (scheduler 상수 아님) | 08:45 · 09:00:05 · 09:00:30~15:28 | 종목상태(관리·단기과열) 조회 — P0 장 전 기록(08:45, `pre_nxt` 전략이 있으면 07:59) · P1 매수 후보 전수(09:00:05, 스윙 제외) · 보유 청산 패스(09:00:30 부터 5분 격자, 15:28 미만). 휴장일로 확정된 날은 돌지 않는다. 상세 = 위 「종목상태 청산·당일 매수 차단」 절 |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | `_confirm_breakout_open_prices(board="main")` — VB/LTV 가 KRX 09:00 시가로 target_price 계산. 직후 `_drain_pending_next_day_clear()` — 08:00 보류 종목 KRX 시장가 일괄 청산. 모두 이미 확정이면 idempotent skip |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | `_force_clear_main_only` — POST_NXT 활성 여부와 무관하게 모든 전략에 `check_force_clear()` 를 호출한다. VB(`("main",)`) = 전량 청산. LTV(`("pre_nxt","main","post_nxt")`) = 본체가 `_limit_up_reached` 상한가 모드 종목 중 15:20 가격이 `limit_up_threshold` 이상을 유지하는 종목만 제외한다(`limit_up_close_hold_mode`, cycle352 — 상세 = `src/engine/strategies/CLAUDE.md` LTV 절); 미달 종목은 그 15:20 청산에 함께 포함되고, 유지분만 익일 청산 모드로 보존된다 |
| `TIME_POST_NXT_OPEN` | 15:40 | **런타임 미사용 상수** — 스케줄러의 POST_NXT 전환(`_phase = "post_nxt_trading"`)과 `_confirm_breakout_open_prices(board="post_nxt")` 는 `run_daily` 가 `TIME_KRX_MAIN_CLOSE`(15:30)를 기다린 직후에 일어난다. 값 15:40 은 `session._BOARD_SCHEDULE` 의 `post_nxt` 보드 시작과 같지만 **보드 경계의 정본은 `_BOARD_SCHEDULE` 이지 이 상수가 아니다**. 테스트 핀(`tests/unit/engine/scheduler/test_post_nxt_open_time.py`)이 값을 잡고 있어 지우지 않는다 |
| `TIME_SESSION_START_CUTOFF` | 20:00 | `scheduler.start()` 기동 거부 경계이자 `run_daily` 의 "이미 장 종료면 내일로" 판정 — **같은 상수**를 쓴다(갈리면 그 창에서 60초 주기 헛 재시도 ~90회 + KIS 휴장일 API + WARNING 2행/회로 그날 리포트 `level_counts` 가 오염된다). `TIME_SETTLEMENT` 과 나눈 이유 = 겸하면 20:00~21:30 재기동이 AI 자문·`auto_apply_recommendations` 를 다시 돌린다. ⚠️ 그 창의 재기동은 **그날 20:30 일봉 적재를 통째로 잃는다** — 다음 영업일 일봉 task 의 immediate 실행(`start()` 직후 stagger 240초, 마커가 직전 영업일 20:30 슬롯보다 일러 영업일 슬롯 게이트가 `reason=stale` 로 실행)이 7일 증분으로 보정하지만 `_boot()` 의 prepare 보다 늦다. 그 사이 6전략 prepare 는 헤드가 `expected_head`(직전 영업일)보다 오래된 종목을 KIS 로 폴백해 읽어 느려지고, 휴장일 조회가 실패한 날(`expected_head=None`)은 하루 밀린 DB 헤드를 그대로 읽는다. `[daily_head_stale]` 관측이 결손을 알린다. +600초 재준비는 적재 완료를 기다리지 않는다(「funnel 스냅샷 캡처」 절) |
| `TIME_FULL_UNIVERSE_LOAD` | 20:00:05 | 전체 유니버스 일괄 적재(`_full_universe_load_task_loop` → `scanner._full_universe_load_once`, 자문 직후 5초 마진). `[full_universe_load_summary] total= kospi= kosdaq= fetched= skipped_ttl= failed= elapsed_ms=` 1행 |
| `TIME_METRICS_SNAPSHOT` | 20:05 | metrics 1차 스냅샷(`daily_metrics_snapshot.run_daily_metrics_snapshot`, leaf). `api_metrics`·`strategy_funnel` 이 프로세스 메모리 전용이라 21:30 정산까지의 유실 노출을 5분으로 묶는다. 🔴 **OpenAI 미호출**(비용·지연 0, `model`·토큰 5컬럼 전부 NULL) · 🔴 **`reset_request_metrics()` 미호출**(부르면 21:30 완전판이 저녁 90분치만 본다) · never-raise · 마커 `[daily_metrics_snapshot] target_date= pass=1 elapsed_ms=` 실행당 1행 |
| `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` | 20:45 | 보조 시세 계정 접근토큰 강제 재발급 — 상세·시각 불변식 3은 모듈 맵의 `quote_token_refresh.py` 항목이 정본이다 |
| `TIME_EVENING_FUNNEL_CAPTURE` | 21:00 | 저녁 미리보기 funnel 캡처(`_evening_funnel_capture_task_loop` → `funnel_capture.evening_capture_once`) — 다음 거래일 기준 `prepare(as_of=)` + 잠정 캡처. 20:30 적재 성공 마커를 30초 간격으로 21:15 까지 기다린다. 상세 = 「funnel 스냅샷 캡처」 절 |
| `TIME_SETTLEMENT` | 21:30 | `_settle()` → `generate_daily_log_report()`(완전판이 20:05 1차 행을 upsert 로 덮어쓴다) → **`purge_old_logs()`**(INFO 2일 / WARNING+ 30일 retention 자동 정리, 실패 graceful `[log_retention_skip]` INFO + 다음 사이클 재시도) → `_reset_daily_state()`(퍼널 카운터 초기화는 분석 *후*) |
- `_load_strategy_config()`: DB `strategy_config` 에서 비중/`tradable_boards`/`exchange`/`k_value_*` 복구. **비중 단위 오염 감지** — 적용 루프 직후·`_config_loaded=True` 직전에 `[weight_config_anomaly] sum=%.4f over_one=%s` WARNING(개별 `weight > 1.0` **또는** Σ `> 1.001`). 집계는 **레지스트리 등록 전략 행만**(`registry.get(sid) is not None` — 은퇴 전략 stale row 영구 오탐 차단), `enabled=False` 행은 **포함**(`enabled` 가 weight 에서 파생되므로 배제하면 오염 행이 통째로 탐지 구멍). 🔴 **자동 클램프·정규화 절대 금지** — 오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다. 블록 전체 try/except **fail-open**. ⚠️ Σ 임계 `1.001` 은 `routes/strategies.py::_WEIGHT_SUM_TOLERANCE`(1e-3)와 동치이나 리터럴 중복이다. `weight=None` 은 감지 블록 *이전* 적용 루프의 `cfg["weight"] * 100` 에서 TypeError → 바깥 except → 기본값 폴백 + `_config_loaded=False` 재시도(기존 계약, 완화 금지). 회귀 `tests/unit/engine/test_weight_config_anomaly.py`
  - 🔴 **첫 회차 진입 지연은 호출부가 정한다(cycle298)** — 루프가 `while` 진입 직후 `sleep` 을 먼저 하므로, 선행 구독이 없는 경로에서는 그 `sleep` 이 그대로 시세 공백이 된다. **호출부 2곳의 배정이 계약이다**: 09:30 진입은 **인자 없음**(바로 앞에서 `scan_stocks()` + `subscribe_filtered_stocks()` 를 이미 동기로 했으므로 0 을 주면 같은 조건검색·구독을 수초 안에 두 번 한다), 15:30 POST_NXT 전환은 **`first_delay=0`**(이 경로엔 선행 구독이 없다).
  - 🔴 **15:30 경로는 재기동 전용이 아니라 매일 탄다** — 평시에도 15:20 의 `self._scan_task.cancel()` 이 `done()=True` 를 만들어 15:30 의 `if self._scan_task is None or self._scan_task.done():` 가 **매일 성립**한다. 그래서 그날 첫 POST_NXT 재구독이 15:35 → **15:30** 으로 당겨진다.
  - 값 처리 — `None`(기본값) = `SCAN_INTERVAL`(300초)이라 **인자를 안 주는 호출은 현행과 동일**하다. 숫자는 **`min(float(SCAN_INTERVAL), max(0.0, float(x)))`** 로 `[0, SCAN_INTERVAL]` 에 가두고, 비수치는 `SCAN_INTERVAL` 폴백이다(예외로 루프를 죽이지 않는다). 🔴 **상한이 계약이다** — 없으면 `first_delay=float("inf")`·`1e9` 가 그대로 `asyncio.sleep()` 에 들어가 **예외도 로그도 없이 그 루프를 영구 blind** 로 만든다. `_scan_loop` 이 유일한 WS 재구독 경로라 그 무음 실패가 곧 손절·트레일링 전면 정지다. **2회차부터는 언제나 `SCAN_INTERVAL`** — 주기가 아니라 위상만 당긴다(`sync_counter % 3` 의 `_sync_positions_from_balance` 도 회차 기준이라 주기 불변).
  - 첫 성공 회차의 구독 직후 `[scan_loop_first_subscribe] first_delay= elapsed_s= n=` INFO 1행(never-raise). 남은 공백 = `15:20 ≤ T < 15:30` 기동의 **최대 10분**(15:20 이후 시작이면 `_scan_task=None` 으로 두고 15:30 까지 기다린다).
  - **매매 행위 영향은 구간마다 다르다** — `_scan_loop` 본문은 주문 발화점 다섯(`risk.on_tick` 2곳 · `_drain_pending_next_day_clear` · `_force_clear_main_only` · `_swing_buy_poll_loop`) 어디에도 닿지 않지만, 구독이 당겨지면 `on_tick` 입구인 틱도 당겨진다. ① **15:30~16:00 = 변화 0**(그 창의 주문은 `order_engine._market_rest_now` 가 전량 컷한다) ② **16:00~19:50 재기동 = 손절·트레일링 매도와 LTV `post_nxt` 매수가 최대 5분 앞당겨진다**(되찾으려는 손절 커버리지 그 자체다) ③ **평시 무재기동 = 보유 종목 틱 커버리지 불변** — 15:20 `cancel()` 은 구독을 해제하지 않는다(해제는 20:00 `unsubscribe_all()` 뿐). delta 갱신·universe guard 시각만 5분 당겨진다(funnel 캡처는 일일 1회 가드 `_auto_funnel_snapshot_done_today` 가 이미 닫는다).
  - 🔴 **전체 재구독 금지** — `_delta_unsubscribe_dropped(new_set)`(빠진 종목만 unsubscribe) + `subscribe_filtered_stocks`(LOW 분기의 `already_in_pool` 가드로 이미 구독 중 종목은 SEND skip)로만 갱신한다. KIS 공지 "비정상 케이스 2"(무한 등록/해제) 패턴 차단이다. HIGH 종목(positions/next_day_clear)은 **항상** 호출한다 — 풀의 `_select_session` promote 를 보존한다. 우선순위 그룹은 `_build_priority_groups(momentum_tickers=...)` 가 만들고 **항상 momentum/breakout 정상 list 를 반환한다**(모드 분기 신설 금지). 직후 `_reprepare_breakout_if_empty()`(대상 `volatility_breakout`/`long_tail_volatility`/`bull_flag_breakout`/`vcp_breakout`. BFB/VCP 는 boot 실패·일시 API 오류 회복 안전망이고 주 메커니즘은 prdy 시간무관 유니버스) + `_resubscribe_stale_priority(cap=10)` + `_report_tick_coverage()`.
- **`_resubscribe_stale_priority`(5분 우선 재구독)** 규칙:
  - 우선순위 분리 = positions/`_pending_next_day_clear` 소속 stale → **HIGH + `bypass_limit=True`**(메인 절대 보장) / 그 외 후보 stale → **LOW + `bypass_limit=False`**(보조 분산). 근거 = 후보 stale 을 HIGH 로 승격시켜 메인을 과부하로 만들고 silent inactive 를 유발한 사고.
  - subscribe **전** 구독상태 가드 — `kis_ws_pool.get_subscribed_tickers()` 스냅샷으로 **실제 구독 종목은 `unsubscribe_in_pool`**, **미구독(split-brain·stale 후보)은 `kis_ws_pool._ticker_to_session.pop` 직접**(KIS unsubscribe 미발송 → OPSP0003 'UNSUBSCRIBE not found' 스팸 회피). 앞쪽이 없으면 `_ticker_to_session[t]=main` 잔존 → 풀 dedup 가드가 재SEND 를 억제 → 개장 러시에 매수한 보유 종목이 온종일 미구독 = 손절 사각이 된다(실측 001450/053800 5h+).
  - 동시호가면 **LOW-scoped skip**(`is_call_auction_now` True → `low_targets=[]`, HIGH 는 유지 = 09:00 갭개장 대비) + **LOW-only throttle** `RESUBSCRIBE_THROTTLE_SECS = 3 × STALE_FRESHNESS_SECS = 180`(`_stale_last_resubscribe_at` gate). 🔴 **HIGH 면제**(300s 케이던스가 LMS-safe 이고 손절 직결) · 🔴 `< 300`(함수 5분 주기) **불변식** — self-block 이 split-brain 복구 원복을 막는다.
  - LOW 는 **desired 교집합**만 남긴다 — `desired_low` = `scheduler._collect_breakout_tickers()` ∪ `scanner._last_scan_result`. 순서 = priority 분리 **직후** → desired 필터 → 동시호가 A/B → cap **앞**. HIGH 는 `low_targets` 에 없어 구조적으로 면제된다(+ `_high_collect_ok` 이중). 활성 게이트 = breakout(scheduler 소유 소스) 비어있지 않음 ∧ HIGH 수집 무예외이고, off 면 현행 byte 동일 **fail-open** 이다. 근거 = LOW 후보 소스가 `scanner.ticker_last_tick` **전수**(per-ticker pop 0건, 유일 정리 = 정산의 `_reset_daily_state` clear)라 매도·후보 이탈 종목이 정산까지 stale 자격을 유지해, 같은 `_scan_loop` 이터레이션 안에서 `_delta_unsubscribe_dropped`(빼기) ↔ `_resubscribe_stale_priority`(되살리기)가 1:1 무한 페어링을 만들었다. 🔴 `kis_ws_pool.get_subscribed_tickers()` 를 desired 로 쓰는 것은 split-brain 복구 계약 무력화라 **금지**(미구독 desired LOW 는 여전히 `_ticker_to_session.pop` + 재SEND 대상이다). AST `test_cycle240_ast_desired_filter.py` G-240-1~7 봉인.
  - cap 은 priority 분리 **후** 적용한다 — `targets = high_targets + low_targets[:max(0, cap - len(high_targets))]` 로 **HIGH > cap 이면 전부 보장**하고 `[stale_priority_resubscribe_cap_exceeded]` WARNING 을 남긴다(AST G-17). 분리 **전** `stale_tickers[:cap]` 은 HIGH 가 sorted LOW 에 밀려 잘리는 결함이라 재도입 금지.
  - 로그 `[stale_priority_resubscribe] count= tickers= desired_low= filtered_not_desired= filtered_sample=`(`count=` 첫 필드 보존).
  - 잔여 = `ticker_last_tick` 을 매도 시 pop 하는 것(8영역, 워크리스트 P1-7 후속 A).
- 🔴 **WS 등록 경로는 `_scan_loop` 5분 delta 단일이다** — 별도 near-signal 류 60초 주기 루프·스트림 풀 모듈을 신설하지 않는다(단일 데이터 경로 + 신규 모듈 추가 금지). 근거 = 그 루프가 `_scan_loop`/K stale watcher 와 race 를 일으켜 KIS `OPSP0002` 폭주 → tick_coverage 0% 사고를 냈다. OPSP0002 는 `_handle_raw` 의 backoff(`_opsp_backoff_until`, **300s ≥ `_scan_loop` 5분 주기**)로 단순 흡수한다.
- **`_stale_watcher_loop()`(120s 주기, 본체 `stale_watcher_core.check_and_resubscribe_stale` — 판정 순서·no_feed skip 은 모듈 맵 `stale_watcher_core.py` 항목)**: `kis_ws_pool.get_subscribed_tickers()` 합집합 vs `scanner.ticker_last_tick` 비교, `STALE_FRESHNESS_SECS=60` 초과면 stale, 종목별 `_stale_retry_count` 누적.
  - **1~5회** = 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority, bypass_limit)` 강제 재등록. 🔴 같은 종목 재SEND(`pool.resend_subscribe_for_ticker`) 분기는 폐기됐고 재도입 금지다 — KIS 인용 "기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록(다수 요청 시 LMS + 앱정보 이용중지)".
  - **`> MAX_STALE_RETRIES=5`** = 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS=600` 경과 또는 `_stale_last_resubscribe_at` 부재면 강제 재등록 + `_stale_retry_count[ticker]=0` 리셋 + `_stale_force_retry_history`(60분 슬라이딩 윈도우) 등록. 시간당 `STALE_FORCE_RETRY_HOURLY_CAP=6` 초과면 `[stale_force_retry_cap]` WARNING skip. cooldown-skip 분기는 `_stale_retry_count[ticker] = MAX_STALE_RETRIES+1` 로 **홀드**한다(무한 climb 방지). r>5 는 force_retry(`>MAX`)·universe_guard(`<=MAX`)·diagnostics(`<2`)가 전부 같은 임계 경로라 **행위 불변**이고, r 을 0 으로 되돌리면 universe guard 가 persistent-stale 종목을 제외하지 못하므로 **캡이 정답**이다.
  - 우선순위 = `high_tickers` = `registry.all()` positions ∪ `_pending_next_day_clear` → HIGH+bypass=True / 그 외 → LOW+bypass=False(메인 편중 차단).
  - **세션 단위 silent inactive** = `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)` ∧ `subscribed_count >= SILENT_INACTIVE_MIN_SUBSCRIBED(=5)` ∧ `SILENT_INACTIVE_PERSIST_SECS(=300)` 지속 → `_force_reconnect_session(label)` 이 `_ws.close()` 를 불러 재연결을 발화시키고 `[silent_inactive_force_reconnect]` 를 남긴다. **시간당 세션당 `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR=2` cap**(`_silent_inactive_recovery_count`)(LMS·앱키 정지 위험 차단, 윈도우 `SILENT_INACTIVE_RECOVERY_WINDOW_SECS=3600`).
  - **시장 침묵 기각(세션 상대 판정)** — 규칙·금기(시간창 리터럴·`tradable_boards`·`session` import 금지, AST G-241-5)는 모듈 맵 `stale_session_recovery.py` 항목. 구현은 2-pass 다 — pass 1 이 세션별 `(label, subscribed, silent_suspect)` 를 상태 무변경으로 계산하고, 판정 가능 세션(`subscribed >= 5`)이 `_MARKET_WIDE_MIN_ELIGIBLE(=2)` 이상이며 **전원** suspect 면 판정 가능 전 라벨의 `first_seen` 을 **pop 하고 `[]` 를 반환**한다(🔴 hold 금지 — 침묵 중 `first_seen` 이 자라면 시장 재개 순간 지각 세션이 즉발한다). 판정 가능 < 2(VTS 단일 세션·20:00 `unsubscribe_all` 후) 또는 하나라도 fresh 면 현행 byte 동일 fail-open 이라 **결과 집합 ⊆ 현행**이다. 대상 슬롯 = 시장 전체가 조용한 NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 · 15:30~15:40 마감 흡수(그 슬롯의 동시 침묵을 세션 고장으로 오판하면 접속키만 낭비하고 회복 가치는 0 이다).
  - 관측 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited`(1800초 이상 지속 시 `persisting` WARNING 을 1800초마다, `exited` 는 `elapsed_secs`·`cycles`), peek→로그→mark, `write_log` 0. 상태 `_MW_EPISODE` 는 **모듈 전역 날짜 키 자기 리셋**이다(`StaleTrackerState` 7필드 가드 때문에 그 자리가 유일하다).
  - ⚠️ 마커의 `connected=`(`_ws` 객체 보유)·`reconnects=`(핸드셰이크 재시도 인덱스 합 — `force_reconnect_session` 강제 close 미반영)는 **소켓 생존 확증이 아니다** → `[ws_heartbeat]` + `persisting` 지속으로 읽는다.
  - 로그 `[stale_watcher_detail] session=main sub=22/41 fresh=8 stale=14 ratio=0.64 stale=[(009150,r=3,@09:12:45),...]`(종목 cap 20 + overflow `...+N`). `[stale_watcher]`/`[stale_priority_resubscribe]` 도 보존한다.
  - 안전망 4중 = F1(재연결 1회) + `_scan_loop`(5분) + K stale watcher(120s) + `_resubscribe_stale_priority`(5분 우선).
  - 이 120s 경로는 소스가 **구독 집합**(`get_subscribed_tickers()`)이라 5분 경로의 핑퐁 결함(`ticker_last_tick` 전수)이 **없다** — 두 경로의 소스 비대칭이 그 결함의 뿌리였다.
- **`_refresh_stale_ccnl_cache(stale_tickers, cap=20)`**: stale r≥2 종목 대상 `quotation.inquire_ccnl` 호출 + `_last_ccnl_cache: dict[ticker, dict]` 갱신. TTL 5분 + cap 20 + 종목 간 50ms sleep + 보유 종목 우선 처리 + KIS None/예외 graceful 캐시 미저장. `_scan_loop`(5분 주기) 통합 + `_reset_daily_state` 동행 clear. universe guard 와 race 무해(TTL 자동 차단). `/api/realtime/subscriptions` 의 `tickers_detail.last_cntg_hour / today_volume` 응답 데이터 소스.
- **`_evaluate_universe_guard(candidate_tickers)`**: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 universe 제외. 사전 가드(보유/익일청산/이미 제외/stale≤5 → KIS 호출 자체 skip) + `inquire_ccnl` 호출 + `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` + `[universe_excluded] ticker=... reason=stale_6plus_low_volume retries=... last_resub_age=...s last_cntg_hour=... today_volume=...` INFO + system_logs 영구. `_collect_breakout_tickers` 필터링 + `_scan_loop` 5분 주기 통합 + `_reset_daily_state` 동행 clear(🔴 영구 블랙리스트 금지).
- **stale 관리 모듈 구조**: facade `stale_manager.py`(`__all__` re-export only — 11 함수 + 11 상수. 프로덕션은 본체 모듈을 patch 한다) + `stale_diagnostics.py`(`build_session_subscription_view`/`emit_stale_session_detail`/`refresh_stale_ccnl_cache`/`evict_expired_ccnl`/`prune_force_retry_history` + 상수 5) · `stale_session_recovery.py`(`detect_silent_inactive_sessions`/`force_reconnect_session`/`delta_unsubscribe_dropped` + 상수 5) · `stale_universe_guard.py`(`evaluate_universe_guard` + 상수 1) · `stale_watcher_core.py`(`check_and_resubscribe_stale`·`resubscribe_stale_priority` = **K stale watcher HIGH hot path**). `scheduler.py` 는 `from src.engine import stale_manager` lazy import 2줄 wrapper **11개**로 위임하고 상수 10개를 re-export 한다(`is` 동일). wrapper 이름은 `_` 접두를 유지한다 — `_check_and_resubscribe_stale` · `_resubscribe_stale_priority` · `_detect_silent_inactive_sessions` · `_force_reconnect_session` · `_delta_unsubscribe_dropped` · `_evaluate_universe_guard` · `_build_session_subscription_view` · `_emit_stale_session_detail` · `_refresh_stale_ccnl_cache` · `_evict_expired_ccnl` · `_prune_force_retry_history`. 계약:
  - ① 4 모듈 logger 는 `logging.getLogger("src.engine.scheduler")` **고정**이다 — `__name__` 을 쓰면 `system_logs` 접두가 갈려 판독 사슬이 깨지고 `caplog.set_level(logger="src.engine.scheduler")` 회귀도 무력화된다(AST Q3).
  - ② `kis_ws_pool`/`kis_ws`/`datetime` 은 `sys.modules.get("src.engine.scheduler")` 네임스페이스 **우선** 참조다(정적 import 금지 AST D-1) — 테스트 patch 호환이면서 운영 환경에서 동일 객체다.
  - ③ 의존 방향은 단방향이고 `stale_watcher_core` → `stale_diagnostics` 는 **모듈-레벨 정적 import** 다(함수-레벨 lazy import 비채택).
  - ④ registry 순회 try/except **4중**(outer + positions + NDC) — `getattr` 폴백은 silent 실패 위험으로 비채택.
  - ⑤ 5분 aggregation 은 `record_*`/`flush_*` **쌍**이다(`record_swing_rest_poll(stats)`/`flush_swing_rest_poll_collector()` · `record_stale_watcher_check(stats)`/`flush_stale_watcher_collector()`) — `[swing_rest_poll_summary] polls= candidates_avg= max= total_held= elapsed_ms_avg=` · `[stale_watcher_summary] checks= stale_total= retried= cap_blocked= force_retried=` · `[dispatch_drop_summary]` 각 1행이고, 결함 시(`stale_count > 0`) `[stale_watcher_detail]` individual 과 `[stale_force_retry_cap]`·`[stale_priority_resubscribe_cap_exceeded]` WARNING individual 은 **영속**한다. 🔴 `record_*` 를 정의한 모듈에는 대응 `flush_*` 호출 사이트가 **≥1** 있어야 한다(AST G-AST1 — 없으면 collector 가 무한 누적하는 메모리 leak + summary 가 영원히 0건이다). 직접 `logger.info` 금지 가드(G-7/G-8-A/G-8-B)와 **개별 ERROR 로 남기는 7 prefix** 목록은 `src/realtime/CLAUDE.md` 「WS action 집계」 절이 정본이다.
  - ⑥ `_api_recovered_collector_loop`(5분 주기)가 `flush_swing_rest_poll_collector`·`flush_stale_watcher_collector`·`flush_silent_drop_count` 를 각각 try/except 로 호출하고 `stop()` lifecycle hook 도 양쪽을 flush 한다(`unsubscribe_all()` 직전 잔여 카운터 손실 방지). `_api_recovered_collector_task` 는 `stop()` cancel 목록에 포함된다(좀비 task 차단). `if not self._running: break` 는 flush 블록 **이후**여야 한다(sleep 후 무조건 1회 flush 보장). AST G-78 / G-78-VERIFY-1~5.
  - ⑦ scheduler 의 `_stale_retry_count`·`_stale_last_resubscribe_at`·`_last_ccnl_cache` 등 **property layer 7쌍을 보존한다** — `src/routes/realtime.py` 가 `getattr` 로 읽는다.
  - ⑧ facade patch 안전선 = `tests/unit/engine/` 의 `patch("src.engine.stale_manager.X")` 는 X 가 facade export 여야 한다(AST G-16). 단 본체가 같은 모듈 네임스페이스에서 직접 호출하는 대상은 facade patch 가 안 먹으므로 본체 모듈 경로로 patch 한다.
- `_sync_orders_to_db(orders)`: KIS 주문체결내역(`get_daily_orders`) → trade_history 동기화. **호출부는 `boot_manager.py` 유일**(부팅 시점 1회 — 장중 주기 호출 없음). MTS/HTS 수동 매매분 반영. 중복 판정 키 `(ticker, order_no)` 페어 — 소스는 dedupe 없는 `get_today_*_trades_for_sync()`(`src/db/CLAUDE.md` `trade_history.py` 절).
  - **전략 귀속 출처 순서(cycle354)** = DB(당일 같은 티커 매수 기록, `db_strategy_map`) → `order_engine._order_strategy`(order_no → strategy_id, 읽기 전용 · 8영역 무접촉, 루트 CLAUDE.md 「주문번호 매핑」 규약) → 하드코딩 `"momentum"`(최종 폴백). 당일 첫 매수(가장 흔한 sync 경로)는 `db_strategy_map` 에 그 ticker 가 아직 없어 order_no 매핑이 주 출처가 된다 — 재시작 전 체결통보(WS)가 유실돼 `_order_strategy` 엔트리가 아직 pop 되지 않은 주문이 전형적 표적이다. 매도는 registry 라이브 포지션 조회(정확한 buy_price 의 유일한 출처)가 최종 권위로 남아 order_no 매핑을 덮어쓴다.
  - 셋 다 미확보 시에만 `[sync_strategy_unknown] ticker= order_no=` WARNING(성과 귀인 오염 가능성 가시화) — 빈 문자열 등 오염된 매핑 값은 `or None` 정규화로 "값 있음"으로 오판하지 않는다. 구형 테스트 더블(`order_engine` 속성 부재)은 `getattr` 이중 폴백으로 fail-open.
  - ⚠️ **포지션 복구의 전략 귀속은 이 함수와 별개 경로다** — `boot_manager.boot()` 의 KIS 잔고 보완 복구(DB `positions` 에 없는 KIS 보유 종목)는 `get_recent_buy_strategy(ticker)`(`trade_history` 최근 매수 행)로 전략을 상속하고 실패 시 자체 `"momentum"` 폴백을 쓴다. 미체결 매수 주문 복구는 `db_positions`→`get_today_buys_ticker_strategy()`→`"momentum"` 3단 폴백이다. 둘 다 별도의 momentum 폴백이고, 청산 규칙이 전략별이라 그 폴백이 틀리면 복구된 포지션이 엉뚱한 전략의 손절·트레일링 규약을 탄다 — 후속 검토 대상
  - **stale `_selling` 재대조** — 본체 = leaf `selling_reconcile.py`(hot path 밖, 판정 3분기·`[selling_hold]` 마커 = 모듈 맵). `_selling` 각 ticker 가 보유 잔존 ∧ 열린 매도주문 없음 ∧ `_selling_since` 경과 ≥ `SELLING_RECONCILE_MIN_AGE_S=180s` 이면 `_selling.discard` + `_selling_since.pop` → 다음 on_tick 손절 재평가 재개(`[selling_reconcile]` WARNING). 고치는 것 = NXT 지정가 미체결 만료·체결통보 유실로 `_selling` 이 영구 잔존해 손절·트레일링이 종일 억제되던 병리다. double-sell 방지 3중 가드 = 열린주문 존재(`exchange=ALL` 조회로 NXT 연속세션 잔존 주문까지 포착) 시 유지 / 미보유 유지 / 180s 미만(전파지연 창) 유지.
  - **체결 0 매수 pending 회수** — 본체 = leaf `buying_reconcile.py`(판정·마커 = 모듈 맵). selling 재대조 **뒤**에서, 어느 전략이든 `pending_buys` 가 있을 때만 `reconcile_stale_buying(self.registry, self.order_engine, holdings)` 를 부른다. `holdings` 는 같은 함수 첫머리 `get_balance()` 결과를 그대로 쓴다(추가 잔고 조회 0).
  - sync 는 `_scan_loop` 3회차마다(≈15분) 돌고 `_scan_loop` 은 09:30~15:20 · 15:30~20:00 에 산다. 그래서 해제 시점은 ≈09:45~15:15 · ≈15:40~19:55 이고, 20:00 뒤에 남은 pending 은 21:30 `_reset_daily_state` 가 치운다
- `_execute_next_day_clear()`: 다음 영업일 NXT 프리 시가 수신 후 30s 안정화 → **갭 ≥ 임계**(`gap_rate >= gap_up_threshold`) = 트레일링 모드(`strategy_id == "long_tail_volatility"` 가드로 LTV 만 후성 동기화 = `_limit_up_reached.add(ticker)` + `pos.high_since_buy = today_open`. 이 동기화가 없으면 `check_exit_signal` 이 당일 모드로 진입해 `intraday_stop_loss` 임계만 작동하고 트레일링이 silent 미발화한다. VB 는 가드 분기 미진입) / **갭 < 임계**·시가 미수신·`nxt_tradable=False`(1순위 판별) = `_pending_next_day_clear` 보류(reason=`nxt_underthreshold` 등) → 09:00 KRX 시장가 청산. 🔴 **08:00 NXT 프리 지정가는 내지 않는다** — 얇은 프리 유동성에서 open−1tick 지정가는 미체결 만료가 잦고 그 만료가 어느 `_selling` discard 경로에도 안 걸려 손절 마비를 만든다. 지정가를 아예 안 내므로 leak·double-sell 레이스가 원천 소멸한다
- `_drain_pending_next_day_clear()`: `_confirm_breakout_open_prices(board="main")` 직후 호출. `_pending_next_day_clear` 종목 KRX 시장가 일괄 청산
- 구조화 로그: `[next_day_clear_deferred] ticker={t} strategy={s} reason={nxt_not_tradable|nxt_open_missing|nxt_underthreshold}` / `[next_day_clear_drained] ticker={t} strategy={s} result={success|fail} elapsed_ms={ms}` / `[selling_reconcile] stale _selling 해제: {t}`(재대조 discard)
- **`_reprepare_breakout_if_empty` WARNING DailyEmitCap**: "스캔 후보 비어있음 — 재 prepare 시도" logger.warning + `write_log` DB INSERT 를 `_reprepare_empty_logged_today: DailyEmitCap[str]` 로 1회/전략/일 cap 한다(후보 0 은 정상 장세일 수 있다). 🔴 **재준비(`funnel_capture.live_prepare_one(strategy, phase="intraday_empty")`) 행위는 cap 밖 불변**이다(회복 메커니즘 보존). `getattr` 폴백 = `__new__` 스텁 인스턴스 호환(cap 부재 시 기존 무제한 emit). 회귀 `tests/unit/engine/test_cycle189_reprepare_emit_cap.py`

### 출처 절: scanner.py

 - `priority_groups` 분기: `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=...)` 위임. `positions`/`next_day_clear` → HIGH + `bypass_limit=True` (메인 절대 보장), `breakout`/`momentum`/`swing` → LOW + `bypass_limit=False` (보조 라운드로빈 우선, 보조 가득 시 메인 fallback)
 - **2-pass**: 1차 `breakout[:BREAKOUT_LOW_CAP=25]` + momentum + swing 잔여 슬롯 add → 2차 `MAX - len(_subscriptions) > 0` 면 breakout overflow 흡수 add. 최종 drop = `max(0, len(overflow) - absorbed_overflow)`. drop>0 시 `[priority_drop]` INFO + WARNING `system_logs`. 중복은 HIGH 1회만, HIGH 단독 41 초과 시 ERROR. **로그 필드** = `breakout/momentum/swing/total_subscribed/max/high_count/low_remaining/pool_sessions/pool_slots/pool_subscribed/pool_remaining` — `pool_subscribed`(현 풀 실제 구독량 `len(kis_ws_pool._subscriptions)`)·`pool_remaining`(잔여 = `max(0, pool_slots − pool_subscribed)`)이 포화가 41-cap(메인)인지 풀 전체(`pool_slots=41×세션수`)인지 가른다
 - `source_counts` dict 전달 시 `[scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)` 노출 (영문 라벨 — Grafana/Loki 안정성)
 - 평탄 처리 분기 (`priority_groups=None`)는 기존 `kis_ws.subscribe` 직접 호출 보존
- `STATIC_TICKER_NAMES` / `_parse_static_ticker_names()`: 모듈 import 시 자기 파일을 정규식으로 파싱 → 종목명 dict. KIS `inquire-price` 빈 응답 대비 보강
- **`get_scan_status()` 풀 전체 카운트**: `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합 위임. `tick_coverage_total/acked/fresh/stale` 4 키 + 기존 `subscribed_count` 보존. `/api/trading/status` `scan` 필드 동봉 → ScanMonitor stale 색상 배지 + 진행바

### 출처 절: log_analysis_engine.py — 일일 로그 분석

21:30 정산 직후 `generate_daily_log_report(_now_kst=None)` 호출. 호출 *후* run loop 가 `_reset_daily_state()` 를 별도 실행한다(퍼널 카운터 보존). `_now_kst` 파라미터는 테스트 주입용이다.
당일 KST 00:00~now `system_logs` + `trade_history` → OpenAI → `daily_log_reports` INSERT.
데이터 수집 구현 사양:
- **`log_metrics_collector._fetch_logs_in_range(start, end, limit=5000)`**: RDS `pg.fetch` 의 `LIMIT/OFFSET` 1,000행(`PAGE_SIZE`) 페이지 루프. `limit` 은 *총* 한도이고(호출부는 `DAILY_LOG_FETCH_LIMIT=30_000` 명시), 빈 페이지 또는 <1,000건 페이지에 닿으면 종료한다. `timestamp` 는 `+09:00` KST str 캐스트(소비처 str 계약 보존).
- **`get_trades_in_range`**: start/end ISO 에 `+09:00` KST timezone 명시 (`src/db/trade_history.py`). TZ 없는 문자열은 KST 00:00~09:00 거래를 누락시킨다.
- **표본 절단 감지** — `_fetch_logs_in_range` 는 `ORDER BY timestamp ASC` 라 상한 초과 시 **이른 시각부터 채우고 조용히 끊는다**. 평시엔 안 걸리고 **폭주한 날 = 리포트가 가장 필요한 날**에만 발동한다. **조용함 + 이른 시각 편향** 두 결함이 겹친 것이라 시정도 3종이다:
  - **`_count_logs_by_level(start, end)`** — `GROUP BY log_level` 로 **진짜 총계**를 원문 fetch 와 무관하게 산출 → `logs.level_counts_actual`. 실패 graceful(`{}`).
  - **`_fetch_high_severity_logs(start, end, limit=HIGH_SEVERITY_FETCH_CAP)`** — ERROR/CRITICAL 만 별도 쿼리로 **전량 확보**(상한 무관). `_merge_high_severity(logs, high)` 가 `(timestamp, log_level, message)` 중복 제거 + 시간 오름차순 유지로 병합한다 — 가장 중요한 신호는 절대 잘리지 않는다.
  - **`_aggregate_logs(logs, fetch_limit=...)`** — `truncated` / `covered_from` / `covered_to` / `fetched_logs` / `coverage_note` 추가. ⚠️ 커버 구간과 절단 판정은 **ERROR/CRITICAL 을 제외한 레벨 기준**으로 계산한다 — 전량 병합된 ERROR 시각이 섞이면 "오후까지 다 봤다" 는 **역-오인**이 생긴다. 전량이 ERROR 인 날은 전체 기준 폴백. `fetch_limit` 미전달 시 기존 계약 보존(`truncated=False`).
  - 절단 시 `[log_report_truncated]` WARNING 1행 + `SYSTEM_PROMPT` 가 AI 에게 "총계는 `level_counts_actual` 인용, 분석 구간을 summary 에 명시" 를 지시한다. 상수 `DAILY_LOG_FETCH_LIMIT=30_000` / `HIGH_SEVERITY_FETCH_CAP=5_000`. 회귀 가드 `tests/unit/engine/test_log_report_truncation.py`

### 출처 절: recommendation_engine.py / recommendation_metrics.py — 20:00 AI자문

- 전략별 metrics(승률/평균손익/손절률/누적수익률) → OpenAI → `parameter_recommendations` INSERT (status: pending)
- `(target_date, strategy_id)` UNIQUE
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`
- user_payload 에 `current_weight` + `peer_weights` + `peer_metrics` + `market_regime` 12 키 추가
- `apply_weight=true` 옵션 → `save_weights({sid: w})` + `strategy.config.weight` 메모리 반영 + `applied_weight` 트래킹. 🔴 `allocate_funds()` 즉시 재호출 금지(다음 `_boot` 반영).
  - **증액 한정 Σ 사전 검증** — `new > 현재 weight` 일 때만 `타 전략 weight 합 + new > 1.0 + _WEIGHT_SUM_TOLERANCE`(`routes/strategies.py` 에서 import = 단일 진실원)를 검사해 위반 시 `[weight_sum_violation]` WARNING + `success=false` **early return**(params/weight/status 어느 것도 저장 안 됨). float 변환 실패 시 검사 skip(기존 관용 경로 위임).
  - 🔴 **감액은 Σ 상태와 무관하게 항상 통과한다** — 오염 상태에서 감액이 복구 수단이라 여기에 검사를 걸면 복구 경로가 봉쇄된다(Settings 는 Σ>1 이면 저장을 잠그므로 무가드 증액은 DB 직접 UPDATE 외 복구 불가 상태를 만든다).
  - ⚠️ 이 경로는 메모리 `config.weight` 만 갱신하고 `enabled` 는 건드리지 않는다(메모리 활성 / DB 비활성 split-brain) — `risk.py` 가 `registry.enabled()` 단일 순회라 메모리도 비활성화하면 그 즉시 손절이 멈추므로 **의도적 미시정**이고 `enabled` 축은 후속 사이클 소관이다. 보유 매수금액 하한선 검증은 이 경로에도 있다(루트 `CLAUDE.md` 「핵심 안전 규칙」 보유 전략 끄기 금지 항목)
- **`PARAM_RANGES`(자동 튜닝 대상 화이트리스트)·`INT_PARAMS`(정수 캐스트)** — 정본은 `recommendation_engine.py` 의 두 상수이고 키 목록은 여기 다시 적지 않는다. 불변식 **`INT_PARAMS` ⊆ `PARAM_RANGES`**. 진입 품질 키(VCP·BFB) = `strategies/CLAUDE.md` 「PARAM_RANGES 편입 목록」 절.
  - 🔴 **편입 금지(정체성 상수)** = 진입 축 `buy_threshold`(momentum 급등 진입 정의)·`donchian_period`(20일 신고가 정의)·`max_breakout_extension_pct`·`box_contraction_period`·`max_box_volatility_pct` / 청산 축 `atr_trail_mult`·`breakout_fail_n_days`(donchian·BFB·VCP **3 전략 공유**인데 근거 표본은 donchian 뿐 → VCP/BFB 청산 왕복 ≥20 시 재검토) / 리스크 축 `max_positions`·`max_lot_units`·`max_lot_ratio_mult`·킬스위치 2키. 근거 = 진입·청산 임계는 전략 정체성이라 AI 가 매일 밤 흔들면 전략이 변태한다. **수동 적용 라우트도 같은 정본을 참조한다.** 나머지 편입 금지 키 = `strategies/CLAUDE.md` 같은 절.
- **`auto_apply_recommendations(target_date)`**: 20:00 AI 자문 직후 자동 적용 — **weight 감액만**(감액 + 50% cap). 🔴 `_CONSERVATIVE_KEYS` 는 **빈 frozenset** 이다 — 손절/일일한도/비중 7키(`stop_loss_rate`·`position_ratio`·`daily_loss_limit`·`intraday_stop_loss`·`overnight_stop_loss`·`stop_loss_main`·`stop_loss_pre_nxt`)를 자동 적용하지 않는다. 근거 = `float(v) > current` 게이트가 조이는 방향만 통과시키고 완화 경로가 없어 단조 ratchet 이 되고, 그것이 전략을 교살한다(`_STOP_LOSS_KEYS` 와 게이트 로직은 도달 불가로 잔존, 무해). `auto_apply_enabled=False` 면 즉시 disabled 반환. 로그 4종 `[auto_weight_apply]`/`[auto_params_apply]`/`[auto_apply_skip_increase]`/`[auto_apply_safeguard_skip]`, `status='applied_auto'`(수동 `'applied'` 와 분리). scheduler `TIME_RECOMMENDATION` 직후 호출이고 호출부는 `from src.engine.scanner import KST_TZ as _AUTO_APPLY_KST_TZ` 후 `datetime.now(_AUTO_APPLY_KST_TZ).date()` 를 쓴다. `backtest_engine.poll()`/`wait_for_result()` 는 `pending` 을 `running` 과 동일 처리한다(unknown 분기로 흘리면 `backtest_runs status=failed` 로 잘못 기록된다)
- `recommendation_metrics._normalize_stop_loss_rate(params)`: 5 키 후보(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`) → 음수만 → `min(candidates)` 반환 (가장 보수적)
- SYSTEM_PROMPT 끝에 매크로 컨텍스트 활용 가이드 — defensive/neutral/aggressive 분기 + **레짐은 매매 미개입(관찰 전용)·`buy_blocked` 는 항상 false 이므로 매수 임계 튜닝은 유효하고 스킵 금지, `block_reason` 은 보수적 권고 참고 신호** + `weight_reasoning`/`code_review_notes` 에 매크로 영향 명시 권장
- VIX 분류 `_classify_vix()` 임계 15/25/35 (low/normal/elevated/high). Fear & Greed 분류 `_classify_fear_greed()` 임계 15/35/65/85
- `weight_reasoning` (≤1000자, 한국어, 통합 `reasoning` 과 별개). `weight=None` 이면 자동 정리, `weight` 있는데 사유 누락 → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING

### 출처 절: 절대 깨지면 안 되는 규칙

시스템 전역 금기의 정본은 루트 `CLAUDE.md` 다 — 「핵심 안전 규칙 (절대 깨지 말 것)」(체결통보 구독 · uvicorn 단일 워커 · 주문번호 매핑 · race 가드 · NXT 매도 거부 좀비 · 시장가 거부 폴백 · VB 15:20 일괄매도) · 「자금 관리」(`position_ratio` 식) · 「코딩 컨벤션」(TR_ID). 엔진 쪽 구현 상세는 위 「order_engine.py」 절이고, 여기에는 엔진 고유 규칙만 둔다.
- `_confirm_breakout_open_prices` 보드 경계 정각 호출은 `board=...` 명시 의무 — 08:00 `pre_nxt` / 09:00:05 `main` / 15:30 `post_nxt`(`TIME_KRX_MAIN_CLOSE` 대기 직후. `post_nxt` 보드 자체는 15:40 부터라 **보드 전환보다 10분 앞서 확정**한다). SessionTracker 30초 race 차단
- `src/engine/strategies/momentum.py` 의 손절 로그는 임계(`stop_loss`)를 함께 찍는다 — 운영 DB `strategy_config.momentum.params.stop_loss_rate` 가 코드 기본값과 다를 때 운영자가 로그 한 줄로 실제 임계를 확인하는 유일한 장치다(임계 인자 제거 금지)
- `src/engine/strategy.py` 의 모듈 함수 `check_buy_signal` / `check_stop_loss` / `check_next_day_clear` 는 삭제됐다 — **재도입 금지**(AST `tests/unit/ast/test_cycle103_ast_no_dead_strategy_funcs.py`). 그 파일에 남은 것은 `Signal` · `Position` · `StrategyState` · `calc_buy_quantity` + 모듈 상수 7종(`BUY_THRESHOLD`·`STOP_LOSS_RATE`·`GAP_UP_THRESHOLD`·`TRAILING_STOP_RATE`·`POSITION_RATIO`·`MAX_POSITIONS`·`DAILY_LOSS_LIMIT`)이다
- `_swing_rest_poll_loop` / `_swing_buy_poll_loop` 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 보유 손절 평가 보강 + 09:05~09:30 매수 평가. **공유 순차 대상 `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")`**(순차 처리로 동일 종목 double-buy race 차단, 전용 task 신설 금지). 🔴 buy poll 은 레짐을 읽지 않는다 — 레짐 매수 게이트를 복원하지 마라(관찰 전용, `risk.py` 절 참조). **`_SWING_POLL_STRATEGIES` 는 매수 평가 소스(poll)를 정하고, `risk.py::_TICK_BUY_EVAL_SKIP_STRATEGIES` 는 WS 틱(`on_tick`) 경로에서 같은 두 전략의 매수 평가를 skip 시켜 그 소스를 배타적으로 만든다 — 두 상수의 멤버는 항상 같이 움직인다**(한쪽에만 전략을 추가하면 그 전략이 틱·폴 이중 평가되거나 아예 평가되지 않는다). skip 은 `check_exit_signal`·보드 가드·중복 가드·자금 가드 **뒤**, `check_buy_signal` **바로 앞**에서만 발생하므로 청산·트레일링·익일청산은 on_tick 에서 두 전략 모두 여전히 정상 평가된다. 킬스위치 없음(1행 revert 로만 롤백)
