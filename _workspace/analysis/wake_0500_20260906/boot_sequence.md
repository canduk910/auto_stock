# 역할 B — 05:00 기동 시 부팅 시퀀스 전수 추적

- 작성: 2026-09-06 (일), 읽기 전용 분석. 코드·DB·설정·git 무수정.
- 대상 커밋: `b985938` (워킹트리 clean)
- 근거: 소스 정독 + 운영 DB `system_logs` SELECT + `docs/HARNESS_CHANGELOG.md` verbatim
- 짝 문서: 역할 A(일봉 스텁봉) = `_workspace/consult/2026-09-06_daily_load_stub_bar.md`

---

## 0. 결론 먼저

**05:00 기동은 현재 코드 그대로는 안전하지 않다. 막는 것은 단 하나 — KIS 가 매일 07:50 에
API 를 재기동하며 모든 기존 접속을 강제로 끊는다는 확정 사실이다.** 지금 우리가 그 사고를
안 겪는 이유는 방어가 작동해서가 아니라 **그 시각에 아직 접속이 없기 때문**이고, 그 "접속이
없음"조차 `TIME_BOOT` 상수가 아니라 **토큰 8개 직렬 재발급이 `_boot` 을 6분 잡아먹는 우연**이
만들고 있다(§3.1). 05:00 로 당기면 메인 1 + 보조 7 = **8개 세션이 전부 07:50 강제 절단선 위에
놓이고**, 그 시각엔 종목 구독이 0건이라 4중 안전망이 **구조적으로 전부 무력**이며(§3.2),
회복 경로(사이클 92 `_trigger_auto_restart`)는 **배포 이후 운영에서 한 번도 발화한 적이 없다**
(30일 로그 0건). 실패 시 증상은 조용하다 — `_send_subscribe` 가 `_ws is None` 이면 **말없이
return** 하므로, 07:59 사전구독도 08:00 매매도 체결통보도 전부 무음 실패한다. 이것이 정확히
2026-06-10 사용자 보고 사고("장 초반 시세 미수신, 수동 재기동만이 유일한 회복 경로")다.

그 하나를 뺀 나머지는 대부분 무해하고, **두 가지는 오히려 개선**이다(§5).

그리고 의뢰서의 잠정 분석은 **맞다**: 시각만 옮기면 일봉 스텁봉 결함은 그대로 재현된다(§4.1).
다만 05:00 기동에는 **의뢰서도 사용자도 말하지 않은 진짜 이득이 하나 있다** — 지금 "오염된
prepare 로 07:59 구독 슬롯을 배분하고 08:00 NXT 프리 매매를 개시"하는 **레이스가 통째로
사라진다**(§4.2). 이건 시각 이동이 아니면 얻을 수 없는 이득이다.

---

## 1. 하루 전체 phase 전이표

### 1.1 `run_daily()` (scheduler.py:1040~1120) — 바깥 루프

| 순서 | 조건/시각 | 무슨 일 | 무엇에 의존 |
|---|---|---|---|
| ① | 루프 진입 | `now = datetime.now()` (naive, 컨테이너 `TZ=Asia/Seoul`) | 컨테이너 TZ |
| ② | `weekday >= 5` | 다음 월요일 `TIME_AUTO_START` 까지 `sleep` → `continue` | 없음 |
| ③ | `now < today_start(=TIME_AUTO_START)` | 그 시각까지 단일 `asyncio.sleep` | — |
| ④ | `now.time() >= TIME_SETTLEMENT` | 내일 `TIME_AUTO_START` 까지 대기 → `continue`. **주의: ③의 sleep 뒤에도 `now` 를 갱신하지 않아 여기서 쓰는 `now` 는 sleep 이전 값**(무해 — ③을 탔다면 `now < 07:45 < 20:10`) | — |
| ⑤ | — | `_is_auto_start_enabled()` — DB `system_config.auto_start` 재확인. false 면 60s sleep 후 `continue` | DB |
| ⑥ | — | `token_manager.get_token()` → `is_market_open(now.date())` (KIS chk-holiday). 휴장이면 `next_trading_day` 까지 대기. **예외는 삼키고 "영업일 가정"으로 진행** | **KIS OAuth + KIS REST** |
| ⑦ | — | `await self.start()` | 이하 §1.2 |
| ⑧ | `start()` 반환 후 | `finally` 에서 배경 task 16종 재-cancel(멱등) → 루프 처음으로 | — |

> ⚠️ ⑦이 예외로 조기 반환하면 루프가 ①로 돌아오는데, `now(=05:0x) > today_start(=05:00)` 이고
> `< 20:10` 이라 **대기 없이 곧바로 ⑤⑥⑦을 재시도**한다. 백오프가 없다. 지금(07:45)도 같은
> 구조지만, 05:00 은 KIS 가용성이 미검증인 시간대(§3.3)라 이 busy-retry 에 걸릴 확률이 더 높다.

### 1.2 `start()` (scheduler.py:556~940) — 하루 본체

`start()` 는 초입에서 `now = datetime.now().time()` 을 읽어 20:10 이후면 거부한다. 그 뒤
**`_boot()` 을 먼저 끝내고**(§2) 배경 task 를 전부 띄운 다음, **line 719 에서 `now` 를 다시 한 번
읽어 스냅샷으로 고정**한다. 이후 모든 `if now < TIME_*` 분기는 **그 고정값**을 본다(중간에
갱신하지 않는다). 05:00 기동이면 `now = 05:0x` 이므로 07:45 기동과 **분기 경로가 완전히 동일**하다.

| 시각(상수) | phase | 무슨 일 | 의존 |
|---|---|---|---|
| — | `booting` | `_boot()` (§2) | KIS OAuth/REST, DB, dkstock |
| — | — | `register_tick/execution/board_handler` → `kis_ws.connect()` task → `kis_ws_pool.start()` → `sleep(2)` → **`H0STCNI0` 체결통보 구독** → `H0UNMKO0`(005930) 구독 | **KIS WS** |
| — | — | 배경 task 16종 spawn (§4.3 표) | — |
| — | — | **`now = datetime.now().time()` 스냅샷 고정 (line 719)** | — |
| `TIME_PRESUBSCRIBE` 07:59 | `presubscribe_wait` | `_wait_until(07:59)` → 돌파/스윙 유니버스가 비었으면 `prepare()` 재실행 → `_collect_presubscribe_tickers()` → `subscribe_filtered_stocks` | prepare 산출물 |
| `TIME_PRE_NXT_OPEN` 08:00 | `pre_nxt_trading` | `_execute_next_day_clear()` task + `_confirm_breakout_open_prices(board="pre_nxt")` | 시세 |
| `TIME_KRX_OPEN_CONFIRM` 09:00:05 | `main_trading` | `_confirm_breakout_open_prices(board="main")` → `_drain_pending_next_day_clear()` | 시세 |
| `TIME_SCAN_START` 09:30 | `scanning`→`trading` | `scan_stocks()` + `subscribe_filtered_stocks` + `_scan_loop` task(5분) | KIS 조건검색 |
| `TIME_KRX_MAIN_BUY_STOP` 15:20 | `krx_main_stopped` | `_scan_task.cancel()` + `_force_clear_main_only()` | — |
| `TIME_KRX_MAIN_CLOSE` 15:30 | `post_nxt_trading` | `_confirm_breakout_open_prices(board="post_nxt")` + `_scan_loop` 재spawn | — |
| `TIME_NXT_POST_BUY_STOP` 19:50 | `post_nxt_stopped` | 전 전략 `buy_disabled=True` | — |
| `TIME_NXT_POST_CLOSE` 20:00 | `closing` | `_scan_task.cancel()` → `unsubscribe_all()` → `generate_recommendations()` → `auto_apply_recommendations()` | OpenAI |
| `TIME_SETTLEMENT` 20:10 | `settling`→`log_analysis` | 가격필터 요약 → `_settle()` → `generate_daily_log_report()` → `purge_old_logs()` → **`_reset_daily_state()`** → `kis_ws.disconnect()` | DB/OpenAI |
| — | `idle` | `finally`: 배경 task 16종 cancel → `kis_ws.disconnect()` → `kis_ws_pool.stop()` → `_running=False` | — |

### 1.3 `_wait_until` (scheduler.py:3813) 규약

```
target_dt = now.replace(hour/minute/second)          # 호출 시점 1회 확정, 루프 내 재계산 금지
if now >= target_dt:
    if not advance_if_passed: return                 # ← run_daily phase 전환: 즉시 return
    target_dt += 1일                                  # ← task_loop_helper: 내일로 1회만 미룸
while self._running:
    if now >= target_dt: return
    sleep(min(남은 초, 60))
```

- `run_daily`/`start()` 영역은 **전부 기본값(`advance_if_passed=False`)** — 이미 지난 시각이면
  즉시 통과. 그래서 05:00 기동이든 07:45 기동이든 phase 전환 자체는 동일하게 성립한다.
- `task_loop_helper` 만 `advance_if_passed=True` — 05:00 시점에 16:00/16:10/…/20:00:05 는 전부
  **아직 안 지난** 시각이라 +1일 분기를 타지 않는다(07:45 기동과 동일). **05:00 이동으로 저녁
  task 의 당일 정기 발화가 사라지는 일은 없다.**
- `_running=False` 면 발화 없이 return. sleep 상한 60s 라 05:00→16:00 대기 구간에서 각 task 가
  시간당 60회 wake-up 한다(6 task × 11시간 ≈ 3,960회 → 현행 8시간 대비 +37%). 무해.

---

## 2. `_boot()` 전수 — 각 단계가 05:00 에 유효한가

`scheduler._boot()` 은 2줄 wrapper 이고 본체는 `src/engine/boot_manager.py::boot()` 다.
**실행 순서 그대로** 나열한다(순서가 계약이다).

| # | 단계 | 하는 일 | 05:00 유효성 | 판정 |
|---|---|---|---|---|
| 1 | `_preissue_all_tokens()` | 메인 + 보조 N(운영 7개: main/ISA/RIA/fire/gold/44606571/71513056/1004) 토큰을 **모듈 전역 lock + 60s gap** 으로 직렬 발급 | 토큰 24h·만료 10분 전 갱신. 현행은 전일 07:45 발급분이 07:45 에 만료 임박 → **매일 아침 8개 전량 재발급 ≈ 7~8분**(운영 로그 07:45:01 → prepare 07:51:13 이 이것) | ⚠️ **KIS OAuth 가 05:00 에 응답해야 함**(미검증, §3.3). 응답만 하면 **오히려 유리** — 재발급 8분이 3시간 여유 안으로 들어간다 |
| 2 | `token_manager.get_token()` | 메인 토큰 확인 | 위와 동일 | 위와 동일 |
| 3 | `_load_strategy_config()` | DB `strategy_config` 로드 | 시각 무관 | ✅ |
| 4 | `check_budget_invariant()` | `position_ratio × max_positions ≤ 1.0` 관찰 WARNING | 시각 무관 | ✅ |
| 5 | `get_balance()` | **KIS 잔고 조회** (`inquire-balance`) | 전일 종가 기준 잔고. 05:00 에도 값 자체는 동일 | ⚠️ KIS REST 가용성 의존(§3.3). 실패 시 `KisApiError` → `start()` 가 graceful return → §1.1 busy-retry |
| 6 | `_refresh_market_regime_and_persist()` | dkstock.cloud 매크로 fetch + `market_regime_snapshots` INSERT + ETF 스테이지 계산 | `DKSTOCK_REGIME_ENABLED` 이 `.env` 에 **없음 → `settings` 기본 `False`** → `MarketRegime.empty()`, 외부 호출 0건 | ✅ (현행 비활성) |
| 7 | `_resolve_cash_usage_ratio()` | `auto_regime_adjust` 가 true 면 레짐 `cash_min` 으로 `cash_usage_ratio` **DB 갱신** | 6이 empty → `computed=None` → **수동값 폴백**. 운영 실측 `auto_regime_adjust=false`(2026-08-07 changelog) | ✅ 단 **조건부 위험**: 두 토글을 켜면 05:00 은 미국 정규장 마감(EDT 05:00 / EST 06:00) **직전~직후**라 미확정 매크로로 그날 자금이 정해진다. 지금은 무해하지만 토글 켤 때 반드시 재검토 |
| 8 | `allocate_funds(net_asset × ratio)` | 전략별 예산 배분 | 5·7 산출물에만 의존 | ✅ |
| 9 | stock_master 대기 가드 | `count_active() > 0` 까지 10s 폴링, cap 300s | 전일 20:00:05 적재분이 남아 있어 즉시 통과 | ✅ |
| 10 | **`for s in registry.enabled(): await s.prepare()`** | 7 전략 유니버스/후보 산출 | **§2.1 별도 분석** | ⚠️ 오염되지만 **05:00 이 더 낫다** |
| 11 | DB `positions` 복구 | KIS 잔고에 없는 행은 `delete_position`, 있는 행은 `Position` 복원 | 05:00 KIS 잔고 = 전일 종가 기준 = 정상 | ✅ |
| 12 | KIS 잔고 보완 복구 | DB 없고 KIS 에만 있는 종목을 `get_daily_orders()` 로 매수일 판정(당일 주문 있으면 `today`) | 05:00 엔 당일 주문 0건 → 전부 `yesterday`(=익일청산 대상) 로 판정. **07:45 도 동일** | ✅ |
| 13 | `mark_pending_buys_completed` | PENDING 매수 → COMPLETED | 시각 무관 | ✅ |
| 14 | `get_daily_orders()` + `_sync_orders_to_db` | 당일 체결 동기화 | 05:00 = 0건 (07:45 도 0건) | ✅ |
| 15 | 미체결 매수 복구 + `sold_today` 시드 | `get_today_buys_ticker_strategy()` 로 당일 매수 종목을 `sold_today` 에 시드 | 05:00 = 0건 | ✅ |
| 16 | `_eager_refresh_stock_master_for_held_positions()` | 보유+익일청산 ticker 의 `stock_master` eager 갱신 (KIS CTPF1002R) | KIS REST 의존, graceful | ⚠️ §3.3 |
| 17 | BFB `recompute_high_since_buy()` | 재시작 시 트레일링 기준점 복원 | 일봉 DB 기반, 시각 무관 | ✅ |
| 18 | VI 시드 `inquire_vi_status_today()` | 부팅 시점 VI 활성 종목 REST 시드 | 코드 주석이 이미 "부팅 = 07:50 = 장 시작 전 = VI 활성 거의 없음". **05:00 은 그 전제가 더 강해진다** | ✅ (graceful) |
| 19 | `load_pending_ndc(today)` | `pending_next_day_clear` 에서 **오늘 날짜** 행 복구 | KST 날짜는 05:00 도 07:45 도 같은 D | ✅ |
| 20 | `run_account_risk_watch_once_guarded` + `ensure_watch_loop` | 계좌 리스크 SOFT 게이트 부팅 1회 평가 + 5분 루프 | 05:00 평가값은 전일 종가 기준. 5분마다 갱신되므로 09:00 이전에 30회 넘게 재평가 | ✅ (관측 비용만 +36회/일) |
| 21 | `report_boot_blind_gap` + 60s 하트비트 루프 | 프로세스 부재 blind 계측 | `market_blind_overlap_secs` 는 **09:00~15:30 교집합만** 세므로 05:00 이동에 불변 | ✅ (DB write +165회/일) |

### 2.1 `prepare()` 가 05:00 에 도는 것이 안전한가 — 코드로 확인

**당일 실시간 데이터에 의존하는 prepare 는 없다.** 7 전략 전부 소스가 정적 DB 다.

| 전략 | prepare 데이터 소스 | 시각 의존 |
|---|---|---|
| momentum | **없음** (`pass` — 실시간 돌파 전용) | 없음 |
| volatility_breakout | `_scan_universe()` = `stock_master.list_by_filter` → `get_recent_daily_normalized` | ⚠️ 아래 (a) |
| long_tail_volatility | 동일 | 없음 |
| donchian_swing | 동일 | 없음 |
| bull_flag_breakout | 동일 | 없음 |
| vcp_breakout | 동일 + `stock_master_daily.get_atr()` | 없음 |
| kojiro | 동일 | 없음 |

- 시총·거래대금 컷은 `stock_master`(전일 20:00:05/16:10/16:30 적재분)에서 읽는다. **당일 누적
  거래량(`acml_vol`)에 기대던 옛 BFB 방식은 사이클 48 에 폐기**됐다(`strategies/CLAUDE.md` 명시).
  즉 **05:00 산출물과 07:51 산출물의 입력은 같은 DB 스냅샷**이다.
- 6 전략이 공통으로 갖는 오늘봉 가드 `prev_idx = 1 if candles[0]["stck_bsop_date"] == today_str else 0`
  는 **날짜 비교**라 05:00 이든 07:51 이든 결과가 같다.
- **(a) VB 만 예외**: DB `strategy_config` 의 `k_period=15` 때문에 `days = 17 < min_required = 22`
  가 되어 **매 prepare 마다 종목당 KIS 일봉을 직접 호출**한다(역할 A 자문 §8 D-4 실측). 05:00
  기동이면 이 KIS 호출 55~65건이 2시간 45분 앞당겨진다 — KIS 가용성 의존이 하나 더 늘어난다.

**결론:** prepare 자체는 05:00 에 도는 것이 안전하다. **다만 그 산출물이 오염돼 있다는 사실은
시각과 무관하며(역할 A), 05:00 이동은 오염을 없애지는 못하고 오염 노출 창을 줄인다**(§4.2).

---

## 3. 05:00 기동이 깨뜨리는 시간 가정 — 전수 조사

`src/engine/*.py`, `src/realtime/*.py`, `src/api/*.py` 의 `time(h, m)` 리터럴을 전수 조사했다.
**05:00~07:45 구간에 걸리는 리터럴은 하나도 없다.** 전부 08:00 이후를 가리킨다.

| 위치 | 리터럴 | 05:00 에서의 판정 |
|---|---|---|
| `session.py:63-67` `_BOARD_SCHEDULE` | 08:00/09:00/15:40/20:00 | `boards_at(05:00) = frozenset()` → **모든 전략 `is_tradable=False`**. 05:00~08:00 매매 0건 보장 ✅ |
| `session.py:221-228` 동시호가 | 08:25~09:05 / 15:15~15:35 | 05:00 은 False ✅ |
| `sell_rejection.py:344-368` | 09:00 / 15:30 / 08:00~09:00 / 15:30~20:00 | `is_krx_main_hours=False`, `is_nxt_hours=False` → 05:00 거부는 **KRX 5분 TTL 도 NXT 익일 TTL 도 아닌 경로**. 다만 05:00 엔 주문 자체가 없다 ✅ |
| `order_engine.py:668-669` | 08:00~09:00 / 15:30~20:00 (프리장 지정가 변환) | 05:00 은 False. 주문 없음 ✅ |
| `scheduler.py:1592` `_confirm_breakout_open_prices` 폴백 | `now < 09:00 → "pre_nxt"` | 05:00 에는 호출 자체가 없다(08:00 이후 진입) ✅ |
| `scheduler.py:2554-2555` `_swing_buy_poll_loop` | 09:05~09:30 | 05:00 → `now_t < 09:05` 분기 → **60s cap chunked sleep 대기**. 발화 0 ✅ (비용은 §4.3) |
| `scheduler.py:134-136` `_swing_rest_poll_loop` | 09:00:30~15:20 | 05:00 → 윈도우 밖 → 60s sleep 반복. 발화 0 ✅ |
| `uptime_monitor.py:39-40` | 09:00/15:30 | blind 계측 분모라 05:00 이동에 **불변** ✅ |
| `task_loop_helper.py:29` `IMMEDIATE_FRESH_SKIP_HOURS=20.0` | — | §3.4 |
| `scheduler.py:64~74` 저녁 task 시각 | 16:00~20:10 | §3.4 |

### 3.1 ★ 결정적 — `TIME_BOOT` 은 죽은 상수다

```
$ grep -rn "TIME_BOOT" src/ tests/
src/engine/scheduler.py:56  TIME_BOOT = time(7, 55)   # 정의
src/engine/CLAUDE.md:713                              # 문서
tests/unit/engine/test_cycle92_time_boot_moved.py     # 값만 검증하는 가드
```

**`start()` 도 `run_daily()` 도 `TIME_BOOT` 을 읽지 않는다.** 실제 부팅 시각은
`TIME_AUTO_START(07:45) + _boot 소요시간`이고, `_boot` 소요시간은 **`_preissue_all_tokens` 의
토큰 8개 × 60s gap ≈ 7분**이 지배한다(운영 로그: 07:45:01 start → 07:51:13 prepare 시작 →
07:51:54 `WebSocket 연결 성공`).

즉 **"07:50 이후에 접속한다"는 사이클 92 의 안전 마진은 상수가 아니라 토큰 재발급 지연이라는
부수효과가 지키고 있다.** 토큰 캐시가 살아 있는 날(장중 재시작 등)에는 `_boot` 이 1분 안에
끝나 07:46 에 접속하고, 그러면 지금도 07:50 절단선에 걸린다. **이 잠복 노출은 05:00 제안과
무관하게 이미 존재한다.**

### 3.2 ★ 최대 위험 — KIS 07:50 API 재기동 강제 절단

`docs/HARNESS_CHANGELOG.md` 사이클 92(2026-06-10) verbatim:

> 사용자 보고 chain = 우리 매일 기동 07:45 vs **KIS API 재기동 07:50 (모든 기존 접속 강제 중단)**
> 정확히 동일 시점 충돌. 결함 chain 확정: `MAX_RECONNECT=5 + BACKOFF_BASE=1.0` = 1+2+4+8+16=31초
> 누적 → "최대 재연결 횟수 초과, 종료" → **WS 영구 종료** → 4중 안전망(F1 / `_scan_loop` /
> K stale watcher / `_resubscribe_stale_priority`) 모두 무력(전제 `self._ws is not None` 불충족)
> → **사용자 수동 재기동만 유일한 회복 경로**

05:00 기동이면 `_boot` 종료 ≈ 05:08 에 **메인 1 + 보조 7 = 8 세션**이 접속하고, 그 상태로
2시간 42분 뒤 07:50 절단선을 정면으로 맞는다. 그 시점의 방어를 코드대로 따라가면:

1. `_receive_loop` → `ConnectionClosed` → return. 안정 접속(>5s)이었으므로 `_reconnect_count=0`
   리셋 → **백오프 없이 즉시 재접속 시도**. KIS 가 이미 살아 있으면 여기서 회복(최선 시나리오).
2. KIS 가 아직 재기동 중이면 `OSError` → 1→2→4→8→16s = **31초** 후 `_trigger_auto_restart()`.
3. `_trigger_auto_restart` → `stop()` → `start()` → 새 `connect()` task(카운터 0). 다시 31초 소진.
4. 두 번째 도달 시각 t+62s → **cooldown 60s 검사에서 `62-31=31s < 60` 이라 False 반환**.
   그런데 호출부는 **반환값과 무관하게 `break`** 한다 →
   ```python
   if self._reconnect_count > MAX_RECONNECT:
       logger.error("최대 재연결 횟수 초과, 종료")
       await self._trigger_auto_restart()   # False 여도
       break                                 # 무조건 종료
   ```
   → **KIS 무응답이 약 62초를 넘으면 그 세션은 그날 영구 사망.**
5. 그 시각 종목 구독은 **0건**(사전구독은 07:59)이므로:
   - `_detect_silent_inactive_sessions` 는 `subscribed >= 5` 전제 → **발화 불가**
   - `check_and_resubscribe_stale` 은 구독 ticker 순회 → **대상 0건**
   - `_resubscribe_stale_priority` 도 동일
   → **4중 안전망이 전부 구조적으로 무력**(사이클 92 가 기록한 그 상태).
6. 07:59 사전구독은 `_send_subscribe` 에서 `if not self._ws: return` — **말없이 통과**.
   체결통보 `H0STCNI0` 도 이미 사라진 상태 → **포지션 등록·손절 불가**.

**운영 증거로 본 위험도**
- 30일 WARNING+ 로그에 **`[ws_auto_restart*]` 0건** — 회복 경로는 **배포 후 한 번도 발화한 적이
  없다**(미검증 코드).
- 반면 매 영업일 **08:57~09:00 에 `WebSocket 연결 닫힘` WARNING 이 1~2회** 찍히고 정상 회복한다
  (08-06~09-04 전 영업일). 이건 안정 접속 후 절단 → 즉시 재접속 경로가 **실제로 작동한다**는
  증거다. 07:50 도 KIS 가 곧바로 다시 받아주면 같은 경로로 살 수 있다.
- 즉 **05:00 의 생사는 "KIS 07:50 재기동 무응답 구간이 62초보다 짧은가"** 하나에 걸린다.
  그 값을 우리는 **모른다**(사이클 92 사고 당시 로그는 30일 retention 밖).

### 3.3 KIS 05:00 가용성 — 미검증 공백

운영 DB `system_logs` 의 WARNING+ 시간대 분포:

```
시각 00 → 2건   |  07 → 28   |  08 → 535  |  09 → 398  | … | 16 → 3,537 | … | 20 → 535
시각 01~06 → 0건 (전무)
```

**21:00~06:59 로그가 통째로 0건** = 그 시간대에 이 시스템이 KIS 를 호출한 적이 한 번도 없다.
따라서 다음은 **전부 미검증 가정**이다:

- `/oauth2/tokenP` 가 05:00 에 토큰을 발급하는가 (실패 시 §1.1 busy-retry 로 직행)
- `chk-holiday` / `inquire-balance` / `inquire-daily-ccld` 가 05:00 에 응답하는가
- KIS WS 접속을 05:00 에 받아주는가
- KRX OPEN API(`openapi.krx.co.kr`) 가 05:00 에 응답하는가 — 단 `base_date = today_kst() - 1일`
  이라 **요청 날짜는 07:45 과 동일**하므로 응답 내용은 바뀌지 않는다

### 3.4 신선도 게이트 20h 창 — 결론적으로 무변화 (문서만 낡는다)

`immediate_skip_if_fresh_hours` 는 **immediate 실행에만** 걸리고 정기 while 발화에는 무관하다.

| task | 게이트 | 저녁 성공 | 07:52 기동 경과 | **05:08 기동 경과** | 판정 변화 |
|---|---|---|---|---|---|
| `full_universe_load` | 없음(24h TTL 내장) | 20:00:05 | 11.9h | 9.1h | 없음(둘 다 TTL skip) |
| `stock_master_daily_load` | **없음**(`max_bas_dd` 멱등) | 16:00 | — | — | **없음 → §4.1 결함 그대로** |
| `stock_master_basics_refresh` | 20h | 16:10 | 15.7h → skip | **13.1h → skip** | 없음 |
| `evening_funnel_capture` | 없음 | 16:20 | 매일 실행 | 매일 실행 | 없음 |
| `stock_master_master_load` | 20h | 16:30 | 15.4h → skip | **12.8h → skip** | 없음 |
| `stock_master_financial_load` | 168h(주1회) | 16:40 | 주 단위 | 주 단위 | 없음(경계 2.7h 이동) |
| `stock_master_daily_purge` | 없음 | 16:15 | 매일 | 매일 | 없음(cutoff = KST 날짜) |

- 월요일(주말 후) 은 basics/master 경과가 61h 이므로 **양쪽 다 immediate 실행** — 변화 없음.
- ⚠️ **문서 드리프트**: `task_loop_helper.py:29` 주석 "16:10 저녁 basics 성공 → 익일 07:50 boot
  = ~15.7h < 20h" 이 사실과 어긋나게 된다. 상수를 바꿀 필요는 없다(여유가 오히려 커진다).

### 3.5 그 밖에 확인한 것들 (전부 무해)

- `_reset_daily_state()` — 20:10 정산 뒤 1회. 05:00 기동은 같은 영업일 안에서 끝나므로
  reset 시점·대상 불변. `_bought_today`/`sold_today`/`_universe_excluded_today` 모두 그대로.
- `AUTO_START` — `.env` `true` + DB `system_config.auto_start` 우선. 시각 무관.
- 주말/공휴일 — `run_daily` ②(`weekday>=5`)와 ⑥(`is_market_open`)이 `TIME_AUTO_START` 를
  그대로 쓴다. 상수만 바꾸면 자동으로 따라온다.
- KST 강제 — 프로세스 TZ 가 `Asia/Seoul` 이고 날짜 경계(자정)를 건드리지 않으므로 naive
  `datetime.now()` 사용처들도 05:00 에서 안전하다.
- `_execute_next_day_clear` / `_drain_pending_next_day_clear` — 08:00 / 09:00:05 분기 안에서만
  생성·호출. 05:00 에는 접근 자체가 없다.

---

## 4. 05:00~08:00 3시간 동안 시스템은 무엇을 하는가

### 4.1 일봉 결함은 그대로 재현된다 — 의뢰서 잠정 분석 확인

`_stock_master_daily_load_once` 의 멱등 조건은 **날짜 비교**다:

```python
latest = await stock_master_daily.max_bas_dd(ticker)
if not force and latest is not None and latest >= today:
    summary["skipped_fresh"] += 1;  continue
```

immediate run 은 `initial_delay_secs=240` 이므로 **`_boot` 종료 + 4분**에 뜬다 — 절대 시각이
아니라 **부팅 상대 오프셋**이다. 그래서 05:00 기동이면 05:12 쯤 돌고, 그 시각 `max_bas_dd = D-1
< D` 이므로 **fetch → KIS 가 주는 오늘(D) 껍데기 봉을 그대로 upsert → 그날 16:00 정기 실행이
`latest >= today` 로 전 종목 skip`**. **시각 이동은 이 결함에 아무 영향이 없다.**

**"하루 한 번"을 만드는 것은 기동 시각이 아니라 (가) 적재 시각 게이트 또는 (다) 오늘봉 필터다**
— 역할 A 자문의 결론(`적재 시각 < 15:40 KST` 판정)과 일치한다.

### 4.2 ★ 그럼에도 05:00 에는 진짜 이득이 하나 있다 — 오염 노출 창 소멸

역할 A 자문이 확정한 아침 인과 사슬(09-04 로그 실측)은 **전부 부팅 상대 오프셋**이다:

| 오프셋 | 이벤트 | 현행(07:45 기동) | **05:00 기동 시** |
|---|---|---|---|
| `_boot` 내부 | 1차 prepare — **오염** | 07:51:13~07:51:52 | 05:06 |
| `_boot`+240s | daily load immediate — 실봉+스텁 동시 기록 | 07:55:56~07:57:55 | 05:11~05:13 |
| `_boot`+600s | `evening_funnel_capture` immediate 가 prepare **재실행 = 우연한 복구** | 08:01:57~08:02:34 | 05:17 |
| **절대 시각** | **07:59 사전구독** — 구독 슬롯 배분 | **오염된 후보로 배분** | **정상 후보로 배분** |
| **절대 시각** | **08:00 NXT 프리 개장** (LTV `tradable_boards` = pre_nxt 포함) | **오염 상태로 매매 개시**(복구는 08:02) | **정상 상태로 개시** |

현행 구조에서 복구(08:02)는 **사전구독(07:59)과 프리장 개장(08:00)보다 늦다.** 그리고 07:59 에
배분된 구독 슬롯은 08:02 복구가 다시 만들어 주지 않는다 — 다음 재구독은 09:30 `scan_stocks`
이후다. 즉 **07:59~09:30 동안 오염된 후보 집합으로 시세 슬롯을 쥐고 있다.**

05:00 기동이면 복구(05:17)가 사전구독보다 **2시간 42분 앞선다.** 360초 여유에 기댄 우연이
2시간 42분 여유로 바뀐다. **이건 시각 이동이 아니면 얻을 수 없는 이득이고, 사용자가
직관적으로 옳았던 부분이다** — 다만 그 이유는 "하루 한 번이라서"가 아니라 **"복구가 매매보다
확실히 앞서서"** 다.

⚠️ 단 이건 **결함을 고치는 게 아니라 창을 넓히는 것**이다. 스텁봉 자체는 남고, VCP `get_atr()`
의 상시 6.3% 과소(역할 A §1.2)는 05:00 으로도 **전혀 줄지 않는다**. 근본 시정(가/다)은 별개로
반드시 해야 한다.

### 4.3 05:00~08:00 자원 소비 실측 근거

| 루프/task | 주기 | 05:00~08:00 에 하는 일 | KIS | DB | 비고 |
|---|---|---|---|---|---|
| `kis_ws.connect` ×1 + pool ×7 | 상시 | **접속 유지**, 구독 = `H0STCNI0` + `H0UNMKO0`(005930) 뿐. 시세 프레임 0 | WS 8세션 | — | **§3.2 위험의 본체** |
| `_receive_loop` | recv | `HEARTBEAT_TIMEOUT=30s` 내 프레임 없으면 재접속. 3시간 무-tick 구간을 PINGPONG 만으로 버텨야 함 | — | — | 30일 로그상 07~09시 `Heartbeat 타임아웃` **0건**(다만 현행 노출은 07:52~08:00 ≈ 7분뿐이라 3시간 근거로는 부족). 타임아웃 발생 시각 분포는 10·11·12·15·16시 총 44건 = 발생해도 자가회복 |
| `_session_loop` | 30s | `session_tracker.tick()` → `boards_at(05:xx)=∅` → 콜백 0 | 0 | 0 | 360회 |
| `_stale_watcher_loop` | 120s | 구독 ticker 0건 → 순회 대상 없음. silent-inactive 는 `subscribed>=5` 미달로 발화 불가 | 0 | 0 | 90회 |
| `_session_health_loop` | 300s | 8세션 heartbeat 지표 emit | 0 | 로그 | 36회 × 8행 |
| `_swing_buy_poll_loop` | 2s chunk(60s cap) | 09:05 대기 — 발화 0 | 0 | 0 | **wake-up ≈ 5,400회 추가**(현행 대비 +3.3배). 코드 주석이 이미 "매초 wake-up 4,400회+" 를 결함으로 지목한 그 지점 |
| `_swing_rest_poll_loop` | 2s chunk(60s cap) | 윈도우 밖 — 발화 0 | 0 | 0 | 위와 동일 규모 |
| `_5xx_dedupe_summary_loop` | 60s | 만료 카운터 flush | 0 | 로그 | 180회 |
| `_api_recovered_collector_loop` | 300s | flush | 0 | 로그 | 36회 |
| `_scan_pool_eager_refresh_loop` | 300s | 후보 풀 0건(사전구독 전) → no-op | 0 | 0 | 36회 |
| `account_risk_watcher.watch_loop` | 300s | **KIS 잔고 평가** (300s 타임아웃) | **+36회** | 쓰기 | 하루 147→183회 |
| `uptime_monitor` 하트비트 | 60s | `system_config` UPSERT | 0 | **+165 write** | 하루 745→910 |
| 저녁 task 6종 `_wait_until` | 60s cap | 16:00~20:00 대기 | 0 | 0 | +약 1,000 wake-up |
| `full_universe_load` immediate | boot+0s | KRX 4호출(`basDd = today-1`, 05:00/07:45 동일) + 24h TTL skip | KRX 4 | 읽기 | 시각 이동 무영향 |
| `daily_purge` immediate | boot+0s | `today_kst()-230일` 컷 삭제 | 0 | 삭제 | 동일 |
| `daily_load` immediate | boot+240s | **~1,015 ticker 일봉 fetch(약 2분)** | **~1,015회** | upsert | 07:56→**05:12** 이동. 07:50 절단선과 09:00 개장에서 **멀어지는** 방향 |
| `basics`/`master`/`financial` immediate | +480/+720/+900s | 신선도 게이트로 skip | 0 | 마커 조회 | 변화 없음 |
| `evening_funnel_capture` immediate | boot+600s | **7 전략 prepare 재실행**(§4.2) + funnel 스냅샷 | VB 만 종목당 1회(§2.1 a) | 쓰기 | 08:02→**05:17** |

**요약**: 유휴 3시간의 실제 비용은 (1) WS 8세션 상시 접속, (2) 계좌 감시 KIS 호출 +36회,
(3) 하트비트 DB write +165회, (4) 빈 sleep wake-up 약 +1만회다. **t4g.small 기준 자원 문제는
아니다.** 유일하게 무거운 것은 (1) 이고, 그건 자원이 아니라 **§3.2 안전 문제**다.

---

## 5. 05:00 이동의 순이익/순손실 정리

**이득 (2)**
1. **§4.2 — 오염된 prepare 로 구독 슬롯을 배분하고 프리장을 여는 레이스가 사라진다.** 복구 여유
   360초 → 2시간 42분. 현행 아키텍처에서 가장 취약한 우연 하나가 제거된다.
2. **§2 #1 — 토큰 8개 직렬 재발급(≈8분)과 `_boot` 전체가 3시간 여유 안으로 들어간다.** 지금은
   07:45 시작이 07:59 사전구독까지 14분밖에 없어서, KIS 지연·재시도가 겹치면 사전구독을
   놓친다(사이클 158/163 이 이미 겪은 종류의 사고). 05:00 은 그 여유를 12배로 늘린다.

**손실 (1, 그러나 치명적)**
1. **§3.2 — WS 8세션이 KIS 07:50 강제 절단선 위에 놓인다.** 회복 경로는 62초 한계 + 배포 후
   미발화 + 그 시각 4중 안전망 전부 구조적 무력. 실패하면 **그날 종일 무음 blind**(시세 0,
   체결통보 0, 손절 0) — 2026-06-10 사고의 완전 재현.

**중립 (전부 확인 완료)**
- 일봉 스텁봉 결함 자체는 불변(§4.1) · 신선도 게이트 판정 불변(§3.4) · 보드/매매 게이트는
  05:00 을 비거래로 판정(§3) · `_reset_daily_state`·주말·공휴일·KST 처리 불변 · 자원 증가는
  무시 가능(§4.3).

**미검증 공백 (선결)**
- KIS OAuth/REST/WS 및 KRX OPEN API 의 **05:00 가용성**(§3.3) — 운영 로그에 21~07시 근거가 0건.
- KIS **07:50 재기동 무응답 구간의 길이** — 62초보다 짧은지 아무도 모른다.

---

## verdict

**05:00 기동은 지금 코드 그대로는 안전하지 않다.** 깨지는 것은 단 하나지만 그 하나가 치명적이다
— KIS 가 매일 07:50 에 API 를 재기동하며 모든 접속을 강제로 끊는데(사이클 92, 사용자 보고
확정), 05:00 기동은 메인 1 + 보조 7 세션을 그 절단선 위에 2시간 42분 동안 세워 둔다. 그 시각엔
종목 구독이 0건이라 4중 안전망(F1 / `_scan_loop` / K stale watcher / `_resubscribe_stale_priority`)
이 전부 전제 미충족으로 무력이고, 유일한 회복 코드인 `_trigger_auto_restart` 는 60s cooldown +
호출부의 무조건 `break` 때문에 **KIS 무응답이 62초를 넘으면 세션을 그날 영구 사망시키며, 배포
이후 운영에서 한 번도 발화한 적이 없다**(30일 로그 0건). 실패는 조용하다 — `_send_subscribe` 가
`_ws is None` 이면 말없이 return 하므로 07:59 사전구독·체결통보·손절이 전부 무음으로 사라진다.
지금 이 사고가 안 나는 이유는 방어가 아니라 **토큰 8개 직렬 재발급이 `_boot` 을 6분 잡아먹어
07:52 에야 접속하는 우연**이며(`TIME_BOOT` 07:55 는 어디서도 읽히지 않는 죽은 상수다), 그래서
같은 위험은 05:00 제안과 무관하게 **토큰 캐시가 살아 있는 날에 이미 잠복해 있다**. 그 하나를
빼면 나머지는 무해하다 — 보드 스케줄은 05:00 을 비거래로 판정해 매매를 0으로 막고, 신선도
게이트·`_wait_until` 판정·`_reset_daily_state`·주말/공휴일 처리는 전부 불변이며, 7 전략
`prepare()` 는 당일 실시간 데이터에 의존하지 않아(사이클 48 이 `acml_vol` 방식을 폐기했다)
05:00 산출물과 07:51 산출물의 입력이 같은 DB 스냅샷이고, 자원 증가(KIS +36회·DB +165 write·
빈 wake-up 1만회)는 무시할 수준이다. **그리고 의뢰서의 잠정 분석은 맞다** — 시각만 옮기면
`max_bas_dd < today` 판정이 05:12 에 그대로 성립해 스텁봉이 다시 쓰이고 16:00 이 다시 skip 되며,
VCP `get_atr()` 의 상시 6.3% 과소는 조금도 줄지 않는다. 다만 사용자 직관에는 의뢰서가 짚지
못한 진짜 이득이 하나 있다 — 아침 파이프라인의 세 이벤트(오염 prepare / 일봉 적재 / 우연한
복구 prepare)가 전부 **부팅 상대 오프셋**(+0 / +240s / +600s)이라 통째로 앞당겨지는 반면
사전구독(07:59)과 프리장 개장(08:00)은 절대 시각이므로, **현재 360초 여유에 기대어 매매보다
겨우 2분 늦게 끝나던 복구가 2시간 42분 앞서게 되어 "오염된 후보로 구독 슬롯을 배분하고
프리장을 여는" 레이스가 통째로 사라진다**. 요컨대 05:00 이동은 일봉 결함의 해법이 아니라
**노출 창 축소책**이고, 그 이득을 얻으려면 먼저 (1) KIS 의 05:00 가용성(OAuth/REST/WS/KRX)을
실측하고 (2) 07:50 절단 생존 대책 — 07:45 직전 계획적 disconnect 후 07:55 재접속, 또는
`_trigger_auto_restart` 의 cooldown/`break` 규약 시정 — 을 `src/realtime/**`·`scheduler.py`
(8영역) 승인과 함께 선행해야 한다. **그 둘 없이 상수만 05:00 으로 바꾸는 변경은 반대한다.**
