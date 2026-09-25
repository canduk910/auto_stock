# cycle364 — A1 `prepare(as_of=)` 저녁 미리보기 · 아침 재준비 ②③④ · 비상 캡처 설계 (domain-expert 자문 + 부수효과 감사, 2026-09-25)

> **입력** — 사용자 결정(2026-09-25): D3 = A1(저녁 캡처는 `prepare(as_of=다음 거래일)`, 오늘 봉 포함) + 비상 캡처(파라미터를 주면 오늘 봉을 버리고 캡처) · D4 카드1 (가)(4a + ①②③ + A1 과 ①′④·비상 캡처 규칙, ①·①′ 는 cycle363 `dce10e0` 로 이미 배포) · 카드3 (나)(donchian 보유 트레일링 = 오늘 ATR, P2 청산 자문으로 따로) · 카드4 (가)(비상 캡처 허용 = 07:58 전 · 08:50~08:59 · 20:00 뒤 · 휴장일).
> **정본** — `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` · `_workspace/red/cycle350_evening_funnel_spec.md` §2 · `_workspace/red/cycle363_business_day_freshness_spec.md`.
> **범위** — 설계·명세만. 코드·설정·DB 쓰기 없음. 「실측」은 이 자문이 직접 돌린 읽기 조회만(부록). 줄 번호는 HEAD `dce10e0` 기준.

---

## 0. 결론 먼저

1. **A1 은 라이브 전략 객체에 그대로 불러도 된다. A2(격리 인스턴스)로 갈 필요는 없다.** 저녁 21:00 에는 시세가 끊겨 있고(20:00 `unsubscribe_all`), 모듈 전역 캐시는 21:30 정산이 비우며, 다음 날 부팅이 모든 준비 상태를 다시 만든다. A2 는 오히려 모듈 전역(`scanner.ticker_prev_close` 등)을 격리하지 못해 불완전하다.
2. 🔴 **크리티컬 가드 1 — 저녁 준비는 보유 종목의 청산 입력을 건드리면 안 된다(PV-1).** 지금 코드에 `as_of` 만 넣으면 kojiro 가 보유 종목에 `_held_stage3 = (오늘 날짜, 내일 판정값)` 을 찍는다(`kojiro.py:461`). 이 플래그는 **오늘 안에 소비된다**(`kojiro.py:1071-1077`, `_judged_on == 오늘` 이면 가격 무관 청산). 20:00 뒤 시세가 구조적으로 막혀 있지 않다 — stale watcher 가 보유 종목을 HIGH 로 다시 구독한다(`scheduler.py:3002-3031`, 시각 게이트 없음) — 그래서 틱 하나면 야간 청산 주문이 나가고, `APBK0918` 거부, NXT TTL, 익일청산 경로로 흘러간다. donchian 은 저녁 준비가 보유 종목 ATR 엔트리를 지워(`donchian_swing.py:327`) 21:30 포트폴리오 리스크 손절선이 매수시점 ATR 로 떨어진다. → **donchian·kojiro 는 미리보기 준비에서 보유 종목을 건너뛰고, 기존 엔트리는 보존한다.**
3. 🔴 **크리티컬 가드 2 — 저녁 캡처 시각은 21:00 이다. 20:30~20:55 는 쓸 수 없다.** 20:45 에 보조 시세 계정 7개의 토큰 강제 재발급이 돈다(`quote_token_refresh.py:168`). 실측으로는 20:45:00 에 시작해 20:51:07 에 끝나고 `window_issues_total=7` 이다. 그 창 [20:35, 20:53] 에 보조 풀 REST 가 들어가면 자연 재발급이 겹쳐 발급 수가 두 배가 된다(cycle296 사고의 재현). 일봉 적재 창 [20:30, 20:40] 도 비어 있어야 한다. A1 의 KIS 폴백(`fetch_daily_candles` → `kis_get_quote`)과 휴장일 조회는 **둘 다 보조 풀**을 탄다.
4. 🔴 **크리티컬 가드 3 — 아침 재준비와 비상 캡처는 창이 끝나기 전에 반드시 끝나야 한다.** 08:59 를 넘겨 준비가 돌면 09:00:05 시가 확정 직후 VB·LTV `_targets`·`_open_confirmed` 가 지워진다. main 목표가는 REST 로만 다시 확정되므로 최대 5분 동안 main 매수가 비고, BFB·donchian·kojiro·VCP 는 매수 창 안에서 `_bought_today` 가 초기화된다. → **전략 단위 마감 검사**(아래 §4.2)가 필요하다. 준비 한 번의 실측 소요는 약 60~75초다.
5. 🟠 **A1 과 같은 배포에 반드시 함께 넣을 것 — 캡처 라벨 가드.** A1 뒤에는 저녁부터 다음 부팅까지 메모리의 funnel 이 「다음 거래일 목록」이다. 지금 수동 캡처(`POST /api/strategy-funnel/snapshot`)는 메모리를 **오늘 날짜의 확정 행**으로 저장한다(`strategy_funnel.py` route :150-155). 밤에 누르면 내일 목록이 오늘 09:35 확정 행을 덮는다. 매매 영향은 없지만 기록이 거짓이 된다. 09:30 자동 캡처도 같은 헬퍼를 쓴다.
6. **②③④·비상 캡처는 cycle360 안대로 간다.** 달라진 점만 적는다. (a) 완료 신호는 `count_all()` 이 아니라 즉시 실행 결과 기록기(`task_loop_helper` 훅)로 받는다. (b) 조용한 창은 **시작 시각이 아니라 예상 종료 시각**으로 판정한다. (c) 오후 재기동의 +600초 재준비는 21:00 저녁 A1 에 넘긴다.
7. **8영역 접촉 0.** `scheduler.py` 는 다섯 자리를 건드리지만 몸통을 새 leaf 로 빼서 **순감 약 35줄**이다(3,812 → 약 3,777, 상한 3,900 미만). D3 승인(`scheduler.py` 포함) 범위에서 재확인이 필요하다.
8. **곁에서 확인한 사실(설계 입력) 둘.** ① 지금 16:20 재준비 목록은 「D-1 봉 + D 16:10 basics 거래대금」의 **혼합물**이다. 09-21~23 분모가 아침과 16:20 사이에 매일 바뀌었다(BFB 600→564, VCP 711→659, kojiro 703→657). 이 목록이 애프터장 도중 LTV 후보를 갈아 끼우고 있었다. A1 이 이것을 없앤다. ② 일봉 적재 대상은 하루 970~1,063 종목이다. 전략 유니버스와의 차집합은 저녁·아침 모두 KIS 폴백으로 읽힌다(§7).

---

## 1. 부수효과 전수 감사

### 1.1 A1 이 도는 시점의 세계 (거래일 D, 코드 기준)

| 시각 | 일어나는 일 | 근거 |
|---|---|---|
| 19:50 | 활성 전략 전부 `state.buy_disabled = True` | `scheduler.py:880-884` |
| 20:00 | `_scan_task.cancel()` · `unsubscribe_all()` · AI 자문 · 자동 적용(파라미터 감액, 메모리+DB) | `scheduler.py:885-935` |
| 20:00:05 | full_universe 정기 실행(평일 `fetched=0`) | `TIME_FULL_UNIVERSE_LOAD` |
| 20:05 | metrics 1차 스냅샷(`vcp_breakout_events`·`portfolio_risk` 포함) | `scheduler.py:937-944` |
| 20:30~20:32 | 일봉 적재(메인 계정), 성공 마커 `task_last_success_stock_master_daily_load` | 실측 09-21 20:32:36 · 09-22 20:32:34 · 09-23 20:32:10 |
| 20:45~20:51 | 보조 7계정 토큰 강제 재발급(직렬화 61초 간격) | 실측 3일 모두 elapsed 367~368s, `window_issues_total=7` |
| **21:00** | **A1 저녁 캡처(제안)** | §2.4 |
| 21:30 | `_settle()` → 일일 로그 분석(`portfolio_risk`·`vcp_breakout_events`·funnel 단계 DB 조회) → 로그 purge → `_reset_daily_state()` | `scheduler.py:940-984` |
| 21:3x | WS disconnect → `finally` 가 적재·캡처 task 전부 cancel | `scheduler.py:1025-1052` |
| 다음 거래일 07:45 | `_boot()`: stock_master 대기 → 헤드 관측 → **활성 전략 prepare** → 포지션 복구 → `recompute_held_atr` → 익일청산 복구 | `boot_manager.py:229-262·478·519` |

- `_reset_daily_state()`(`scheduler.py:3618`)가 비우는 것은 `state.positions` 등 계좌 상태, 주문 추적, `scanner.ticker_prev_close`·`ticker_names`·`ticker_prices`·`ticker_last_tick`, 그리고 `condition` 캐시다(`:3714-3731`). 전략의 `_candidates`·`_targets`·`_funnel_steps`·`_scanned_tickers` 는 **지우지 않는다**. 전략별 훅은 BFB(`_breakout_first_seen`)와 momentum(`_prev_prdy_rate`)만 있다.
- 그래서 A1 이 만든 준비 상태는 **21:30 뒤에도 남아 다음 부팅까지 메모리의 「현재 목록」이 된다**(주말이면 월요일 부팅까지). 대시보드(`registry` 상태 → `get_targets_status`·`get_scan_stats`, `strategy_registry.py:126-132`)가 밤새 다음 거래일 후보를 보여 준다. 이것이 cycle171 이 원했던 「운영자 밤 후보 확인」의 실제 모습이다.

### 1.2 전략별 감사표 — prepare 가 라이브 상태에 쓰는 것

「저녁 영향」은 21:00, `as_of = 다음 거래일`, PV-1 적용 **전**을 기준으로 적었다. 「덮나」는 다음 부팅 준비가 다시 만드는지를 뜻한다.

| 전략 | 쓰는 것 (파일:줄) | 저녁 실행 영향 | 덮나 | 판정 |
|---|---|---|---|---|
| **VB** | `_scan_stats`(:224,246) · `_funnel_steps`(reset·record) · `_targets.clear()`(:228) · `_open_confirmed.clear()`(:229) · `_prev_price.clear()`(:230) · `_failed_breakout_count.clear()`(:231) · `_targets[t]`(:372) · `_open_confirmed[t]`(:384) · `scanner.ticker_prev_close[t]`(:390) · `_scanned_tickers`(:398) · `_universe_candidate_tickers`(:482) · `scanner.ticker_names[t]`(:475) · 퀀트·RS/RSI 관찰(funnel 7~9단계) | 매수는 19:50 에 닫혔다. VB 보유는 15:20 에 비는 것이 정상이다. 드물게 밤을 넘기는 VB 보유는 조기청산 입력(`_targets`, `check_exit_signal`)을 잃는다. 틱이 없으니 발화하지 않고, 부팅도 똑같이 지운다(현행 동일) | 예 | 무해. 조치 없음 |
| **LTV** | VB 와 같은 구조(:262·266-268·427·438·444·452·543·571) · 연속 상한가 필터는 D 봉 포함 | 상한가 모드로 밤을 넘기는 보유는 `ticker_prev_close`(청산 판정에서 읽음)만 관련된다. 그 종목이 내일 후보로 다시 뽑힐 때만 D 종가로 바뀌고, 21:30 에 비워진다 | 예 | 무해. 조치 없음 |
| **donchian** | `_candidates = {}`(:327) · `_scan_stats` · `_funnel_steps` · `_scan_stage_counts`(:705) · `ticker_names`(:731) · `_update_trading_days(candles)`(:444) · `ticker_prev_close`(:589) · `_candidates[t]`(:591) · `_scanned_tickers`(:636) · `_bought_today.clear()`(:637) | 🔴 **보유 종목 ATR 엔트리가 지워진다**(아침 `recompute_held_atr` 가 넣은 「오늘 ATR」). 트레일링과 손절선 미러가 `_entry_atr`(매수시점)로 떨어진다(`:1789`, `get_effective_stop_price` `:1836-1837`). 틱이 없어 청산은 없다. 다만 21:30 `portfolio_risk` 는 이 값을 읽는다(`log_metrics_collector.py:449-462`). 그 결과 20:05 스냅샷(오늘 ATR)과 21:30 완전판(매수 ATR)이 갈린다. 보유 종목이 내일 후보로 다시 뽑히면 D 종가 ATR 로 덮인다. 거래일 캐시는 D 를 더하는데, D 는 실제 거래일이라 무해하다 | 예(부팅 준비 → 복구 → recompute) | **PV-1 적용** |
| **BFB** | `_check_extension_cap_invariant()`(:234, 로그만) · `_candidates = {}`(:242) · `ticker_names`(:749) · `_scan_stage_counts`(:735) · `ticker_prev_close`(:445) · `_candidates[t]`(:447) · `_scanned_tickers`(:502) · `_bought_today.clear()`(:503) | 청산은 `_candidates` 를 읽지 않는다(`_entry_atr`·`_position_setup` 스탬프). 고점 보정(`_apply_high_since_buy_from_candles`)은 prepare 가 아니라 `recompute_high_since_buy`(`boot_manager.py:495-499`)에서 돈다. cycle350 §2 가 걱정한 경로는 prepare 에 없다 | 예 | 무해 |
| **VCP** | `_check_extension_cap_invariant()`(:299) · `_candidates = {}`(:323) · `ticker_prev_close`(:580) · `_candidates[t]`(:582) · `_scanned_tickers`(:654) · `_bought_today.clear()`(:655) · `_observe_breakout_distance`(:384·664) → `_breakout_watch` · `_breakout_summary_last` · `_breakout_distance_cap` · DB `get_atr`(최신 14행, 벽시계 무관) | 🟠 `_breakout_watch` 를 교체하면 그날 돌파 관측(20:05·21:30 `vcp_breakout_events`)이 지워진다. 다만 cycle349 D1 가드 `now > entry_end → return`(:1146-1148)이 거래일 저녁을 이미 막는다. **휴장일 낮의 비상 캡처는 막지 못한다**(watch 가 휴장일 날짜로 교체되고, 다음 부팅이 다시 교체하므로 무해). `get_atr` 는 D 봉을 포함해 as_of 와 정합한다 | 예 | 거래일 저녁 무해. P3(미리보기 관측 생략) 권고 |
| **kojiro** | `_candidates = {}`(:290) · `_scan_stage_counts`(:629) · 보유 `_candidates[t]`(:455) · 🔴 **`_held_stage3[t] = (datetime.now(KST).date(), stage == 3)`(:461)** · 후보 `_candidates[t]`(:497, `_fetch_sector` DB 읽기) · `ticker_prev_close`(:495) · 점수(:550) · `observe_band`(:556) · `observe_macd`(:562) · `observe_macd_stage6`(:569) · `_scanned_tickers = ranked_final + held_only`(:572) · `_bought_today.clear()`(:573) | 🔴 보유 종목의 stage3 플래그가 **(D, D 종가 판정)** 으로 찍힌다. `check_exit_signal` §3(:1068-1079)은 `_judged_on == 오늘` 이면 `TRAILING_STOP` 을 돌려준다. **21:00~21:30 에 틱 하나면 가격 무관 청산이 야간에 발사된다.** 보유 ATR 은 D 종가 ATR 로 바뀐다(`_effective_atr` :1119 는 `_candidates` 가 우선). 관측 행은 `bar`(D-1 완성봉 날짜 계약)에 D 가 찍히고, `KstDailyEmitCap` 하루 cap 을 소비해 D 표본을 오염시킨다 | 예(부팅 준비에서는 보유가 복구 전이라 보유 표시 0, 복구 후 `recompute_held_atr` 가 `(D+1, …)` 로 다시 찍음 — `kojiro.py:758-861`) | **PV-1 + P3 적용** |
| **momentum** | `prepare` = `pass`(`momentum.py:100-117`) | 없음 | — | as_of 인자만 받는다 |
| **공용** (`strategy_base`) | `_reset_funnel_steps`·`_record_funnel_pipeline_step`(:280-395, 인스턴스 `_funnel_steps` 만) · `_apply_master_block_filter_in_prepare`(:1517, 보호 종목 = 보유 ∪ 익일청산 → **저녁엔 보유가 통과, 부팅엔 보유 0**) · `_apply_price_filter_in_prepare`(:1544, `raw.bfdy_clpr` = D 16:10 basics 의 **D-1 종가**) · `_resolve_expected_daily_head`(:1606 → `trading_calendar` 메모) | 보호 종목 차이는 저녁 목록과 부팅 목록이 **보유 종목에서만** 갈리는 원인이다. 그래서 ④ 는 보유를 뺀다. 가격 필터가 D-1 종가를 쓰는 것은 저녁과 부팅이 같다(§7) | — | ④ 에서 보유 제외 |

### 1.3 모듈 전역·공용 캐시

| 대상 | 쓰는 곳 | 저녁 21:00~21:30 소비처 | 21:30 | 판정 |
|---|---|---|---|---|
| `scanner.ticker_prev_close` | 6전략 후보 등록 | `risk.on_tick` 의 `prdy_ctrt`(틱 없음) · `llm_buy_gate`(매수 없음) · LTV `check_exit_signal`(보유가 후보로 다시 뽑힐 때만) | clear(`scheduler.py:3721`) | 무해. D 종가는 D+1 기준으로는 오히려 맞다 |
| `scanner.ticker_names` | `_scan_universe` | 이름 표시 | clear + 정적 시드 | 무해 |
| `condition._candle_cache`(5분 TTL) | KIS 폴백 | 21:30 `pyramid_shadow` 등. 같은 키면 D 봉을 포함한 같은 응답이다 | `clear_caches()` | 무해 |
| `trading_calendar` 메모 | as_of·expected_head 해석 | — | 유지(날짜별 개장 여부는 불변) | 무해 |
| `kojiro_band_observe._cap` | kojiro 관측 3종 | D 표본 | KST 날짜 자기 리셋 | P3 로 소비 차단 |
| `stock_master_daily._RAW_MISSING_LOGGED` | 어댑터 | 로그 cap | 날짜 자기 리셋 | 무해 |

### 1.4 저녁부터 다음 부팅 사이에 이 상태를 읽는 것

- **청산**: `risk.on_tick` 하나다(REST 폴 `SWING_REST_POLL` 창은 09:00:30~15:20, `scheduler.py:138-140`). 20:00 에 구독을 해제하지만 stale watcher 가 보유를 다시 구독할 수 있다. 틱 프레임은 실측상 0 이지만 **구조적으로 0 은 아니다**. → PV-1 이 막는다.
- **21:30 로그 분석**: DB funnel 단계는 `target_date = D`(A1 은 D+1 에 쓴다). `vcp_breakout_events` 는 D1 가드가 지킨다. `portfolio_risk` 손절선 → PV-1. 거친 funnel 카운터(`state.signal_count_today` 등)는 prepare 가 **건드리지 않는다**. cycle350 §2 의 「21:30 거친 지표가 D+1 상태를 읽게 된다」는 우려는 코드로 **반증**했다(`log_metrics_collector.py:570-619` 는 `state` 카운터만 읽는다).
- **잔고 화면 손절선**(`position_exit_lines` → `get_effective_stop_price`, 엔진 동작 중) → PV-1.
- **대시보드 후보·funnel 통계**: 다음 거래일 미리보기로 바뀐다(의도). KojiroMonitor 문구 「16:20 스캔」은 거짓이 된다 → 문구 수정 대상.
- **매도 뒤 구독 정리**(`order_engine.py:2440-2480`): 매도가 없으니 해당 없다.

### 1.5 16:20 재준비를 없애면 바뀌는 것 (애프터장 16:00~20:00)

- **LTV post_nxt 후보가 장중에 바뀌지 않는다.** 지금은 16:20 에 `_targets`·`_open_confirmed`·`_prev_price` 가 지워지고, 16:10 basics 거래대금으로 유니버스가 다시 뽑힌다. 실측 09-21~23 에 매일 분모가 바뀌었다. cycle350 실측으로 08-01 이후 16:20~20:00 매수는 0건이라 체결 영향은 0 이다.
- **donchian 보유 트레일링 ATR 이 애프터장에서도 「오늘 ATR」로 유지된다.** 지금은 16:20 에 매수시점 ATR 로 떨어진다. 카드3 (나)와 같은 방향이다.
- **16:20 잠정 행의 소비처**: market_ops 저녁 행(§2.6 재작성) · funnel 화면 「잠정」 배지(이제 미래 날짜 행에만 붙는다) · 21:30 `_collect_strategy_funnel_stages(D)`(이제 09:35 확정본을 읽는다 — 혼합물이 아니라 실제 매매 목록이라 개선) · 20:20 클라우드 루틴(같은 행을 읽는다면 같은 개선). 루트 CLAUDE.md 「기능·설정 비활성화 심층 검증 의무」에 해당하는 **경로 변경**이다. 배포 뒤 실측 항목은 §6.4 에 있다.

---

## 2. A1 설계

### 2.1 인자 규약

- 7전략 `async def prepare(self, *, as_of: date | None = None) -> None`, 추상 선언(`strategy_base.py` `prepare` abstract)도 같다.
- `as_of is None` → **현행 바이트 동일**. 내부 기준일 = `today_kst()`, `today_str` 와 `expected_head` 는 지금과 같다. `[prepare_expected_head]` 로그 형식도 불변.
- `as_of == 오늘` → `None` 과 같은 계산(비상 캡처의 거래일 오전). 미리보기가 아니다.
- `as_of > 오늘` → **미리보기**다. 오늘 봉을 자르지 않는다(`today_str = as_of.strftime(...)` 라 `prev_idx` 는 항상 0), `expected_head = previous_trading_day(as_of)`, PV-1·P3 를 적용한다.
- `as_of < 오늘` → `ValueError`(프로그래밍 오류). DB 가 as_of 뒤의 봉을 돌려주므로 과거 기준일 재현은 성립하지 않는다.
- 공용 헬퍼(`strategy_base`): `_resolve_prepare_as_of(as_of) -> (as_of_date, preview: bool)` 와 `_resolve_expected_daily_head(as_of_date: date | None = None)`. 인자가 없으면 `today_kst()` 라 cycle363 호출부·테스트가 그대로 돈다.
- **호출 형태 보존**: 부팅·장중 경로는 계속 `strategy.prepare()`(인자 없음)로 부른다. `as_of` 는 저녁·비상 경로만 넘긴다. 부팅 경로 테스트의 가짜 전략(`async def prepare(self)`)이 깨지지 않는다.

**PV-1 (🔴 필수) — 미리보기 준비는 보유 종목의 청산 입력을 바꾸지 않는다** (donchian·kojiro)
- 시작부의 `self._candidates = {}` 를 미리보기에서는 `{t: v for t, v in self._candidates.items() if t ∈ 보유 ∪ 익일청산대기}` 로 바꾼다. 아침 recompute 엔트리가 보존된다.
- 종목 루프에서 `preview and t ∈ 보유 ∪ 익일청산대기` 이면 fetch 결과를 버리고 `continue` 한다. `_candidates`·`_held_stage3`·`ticker_prev_close`·관측 행·거래일 캐시 모두 쓰지 않는다.
- donchian 미리보기 `_scanned_tickers` 는 이번 실행이 만든 후보만 담는다(보존한 보유 엔트리 제외 — 평시에도 보유는 `_scanned_tickers` 밖이다. prepare 가 recompute 전에 확정하기 때문).
- kojiro 미리보기 `held_only` 에는 보존 엔트리가 그대로 들어간다(현행 step 99 계약 유지). ④ 는 보유를 뺀다.
- 🔴 **금기**: 미리보기에서 `_held_stage3` 를 `as_of` 날짜로 찍는 절충도 쓰지 않는다. 스테이지3은 「가격을 보지 않는 유일한 청산」(`kojiro.py:1063-1067`)이라, 장외 계산이 청산 트리거를 만들 여지를 아예 두지 않는다. 다음 날 판정은 부팅 recompute(`kojiro.py:758-861`)가 정본이다.

**P3 (권고) — 미리보기에서는 관측 전용 부수 로그를 생략한다**
- kojiro `observe_band`·`observe_macd`·`observe_macd_stage6`(`bar` 필드는 「D-1 완성봉」 계약이다), VCP `_observe_breakout_distance`(휴장일 낮 비상 캡처 대비). 거래일 저녁 VCP 는 D1 가드가 이미 막는다.
- funnel 단계 기록(`_record_funnel_pipeline_step`)과 VB 퀀트·RS/RSI(funnel 7~9단계)는 **생략하지 않는다**. 이것들이 미리보기의 산출물이다.

### 2.2 기준일 해석 — `resolve_as_of(now_kst, mode)` 하나

새 leaf `src/engine/funnel_capture.py` 에 둔다(8영역 import 0, never-raise).

```
@dataclass(frozen=True)
class AsOf:
    as_of: date          # 이 목록을 쓸 세션(거래일)
    expected_head: date  # = previous_trading_day(as_of) — 입력 봉의 기대 헤드
    mode: str            # "evening" | "emergency"
    preview: bool        # as_of > today

async def resolve_as_of(now_kst: datetime, mode: str) -> AsOf | None
```

| mode | 오늘 개장 판정 | as_of | expected_head | None(건너뜀·거부) |
|---|---|---|---|---|
| `evening` | True 필수 | `next_trading_day(오늘)` | 오늘 | 오늘 휴장·모름, 또는 다음 거래일 모름 |
| `emergency` | True | 오늘(오늘 봉을 버림 = 부팅과 같은 해석) | `previous_trading_day(오늘)` | 휴장일 조회 모름 |
| `emergency` | False(휴장일) | `next_trading_day(오늘)`(버릴 오늘 봉이 없다 → 다음 세션 목록) | `previous_trading_day(as_of)` | 다음 거래일 모름 |

- `trading_calendar` 에 `next_trading_day(d) -> date | None` 을 더한다. 앞으로 최대 14일 순회, 도중 None 이면 None, 주말은 조회하지 않음, 메모 재사용. 추석 5일 연휴(09-24~09-28) 형태도 한 번에 넘는다.
- 🔴 **모르면 라벨을 붙이지 않는다.** 저녁 모드가 None 이면 캡처를 건너뛰고 `[evening_funnel_capture] decision=skip reason=calendar_unknown` 을 남긴다. 추측한 날짜로 저장하지 않는다. 다음 부팅이 정본 목록을 만든다.
- 휴장일 조회(CTCA0903R)는 **보조 풀 경로**다(`base.py:80` 화이트리스트, `condition.py:282`). 저녁 모드는 21:00 에 부르므로 토큰 창과 겹치지 않는다(§2.4).

### 2.3 `expected_head`(①′)와의 관계

- 전략 안에서는 `expected_head = previous_trading_day(as_of_date)` 하나로 통일한다. 저녁 = D, 부팅(D+1) = D. **저녁 미리보기와 다음 날 부팅이 같은 기대 헤드를 쓴다.** 이것이 「금요일 저녁 목록 = 월요일 부팅 목록」의 코드상 근거다.
- 헤드가 D 에 못 미친 종목(적재 대상 밖, 정지, 적재 실패)은 ①′ 가 KIS 폴백으로 읽는다(21:00 에는 완성된 D 봉을 준다).
- 남는 벽시계 한 곳: 어댑터의 F-3 깊은 읽기 예외 `_legacy_calendar_fresh`(`stock_master_daily.py:684-693`)는 `today` 를 벽시계로 본다. 이 예외는 요청이 100봉을 넘고(VCP `full`) 헤드가 2영업일 이상 밀린 종목에만 해당한다. 계산해 보면 저녁(D)과 부팅(D+1) 모두 「4달력일 이내 → DB」로 같은 쪽으로 떨어진다. 그래서 ④ `same=1` 은 유지되지만 **둘 다 밀린 헤드**로 계산된다. A1 이 새로 만든 문제가 아니라 cycle363 F-3 에서 이어받은 한계다(§7). 어댑터에 as_of 를 넘기는 것은 이 설계 범위 밖이다.

### 2.4 저녁 캡처 시각과 적재 완료 신호

**시각 = `TIME_EVENING_FUNNEL_CAPTURE = time(21, 0)`** (`scheduler.py:71`, 값과 주석 교체).

| 후보 | 결과 |
|---|---|
| 20:30 + 마커 대기 | ✗ 적재 창 가드 `test_cycle273…::test_g273f_2`([20:30, 20:40] 안 `TIME_*` 0건)와 토큰 창 가드 `test_cycle269…::test_c9 (vi)`([20:35, 20:53]) 둘 다 위반. 실제 위험은 보조 풀 REST 로 인한 자연 재발급이다 |
| 20:45 | ✗ 토큰 강제 재발급 T 와 같은 시각. 직렬화 창 한가운데다 |
| **21:00** | ✓ `T + 15분`(cycle269 (iv) 가 정산 전 종료를 보장하는 체인 상한). 실측 체인은 20:51:07 에 끝난다. 적재 마커(20:32)보다 28분 뒤, 정산(21:30)까지 30분 여유가 있고, 준비 실측은 60~75초다 |

**적재 완료 신호** — `system_config` 마커 `task_last_success_stock_master_daily_load` ≥ `오늘 TIME_STOCK_MASTER_DAILY_LOAD`(KST aware) 이다. 이 마커는 `once()` 가 예외 없이 끝났을 때만 기록된다(`task_loop_helper.py` while 블록). 실측값 `2026-09-23T20:32:10.634156+09:00`.
- 21:00 에 이미 참이면 곧바로 진행한다(평시).
- 거짓이면 30초 간격으로 다시 보되, **시작 마감 21:15** 를 넘기면 건너뛴다. `[evening_funnel_capture] decision=skip reason=daily_load_not_done` WARNING. 적재 없이 돌리면 ①′ 폴백이 수천 건 KIS 호출(보조 풀)이 되고, KIS 장애일이면 값도 비어 **내일 라벨을 붙인 부실 목록**이 남는다. 다음 부팅이 정본을 만드니 건너뛰는 편이 싸다.
- `count_all() > 0`(현행 `scheduler.py:3140-3160`)은 **쓰지 않는다**. 빈 테이블만 막을 뿐 그날 적재를 기다리지 않는다(cycle273 F-D8-a 가 스스로 적은 사실).
- 행 수 비율 같은 보조 충분성 검사는 **넣지 않는다**. 실측상 날짜별 행 수가 대상 크기(970~1,063)를 따라 매일 달라 임계가 성립하지 않는다(부록 SQL-1: 09-21 1,170 · 09-22 1,106 · 09-23 970).
- 요약 로그 1행: `[evening_funnel_capture] decision=run|skip reason= as_of= expected_head= load_marker= daily_head= prepared= saved= skipped=<sid:사유,…>`. 기존 `[evening_funnel_capture_summary] prepared=%d saved=%d` 형식은 grep 연속성을 위해 그대로 둔다.
- 대상 전략은 **`registry.all()` 유지**(현행과 같음. 비활성 전략의 funnel 도 계속 채운다). 순서는 VB → LTV → BFB → VCP → donchian → kojiro → momentum → 비활성 순. 마감 검사(§4.2) 때 중요한 것부터 끝낸다.
- 준비 뒤에는 `capture_funnel_snapshots(registry, is_provisional=True, target_date=as_of)` 를 부른다.

### 2.5 스냅샷 날짜와 라벨 가드

- **스냅샷 날짜 = `as_of`(다음 거래일), `is_provisional=True`.** 다음 날 09:30 확정 캡처가 이 행을 덮는다. 저녁 목록의 영구 기록은 ④ 로그뿐이다(cycle360 이 수용한 한계).
- **라이브 준비 기록**: 모든 라이브 준비는 새 wrapper `funnel_capture.live_prepare(...)`(§4.4)를 거친다. 이 wrapper 가 전략 객체에 `_live_prepare_meta = {as_of, phase, started_at, finished_at, ok}` 를 남긴다. 전략 코드는 이 필드를 쓰지 않는다.
- **`capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None)`**(`scheduler.py:188`) — `label = target_date or 오늘`. 전략마다 `funnel_capture.capture_skip_reason(strategy, label, today)` 로 판정한다.
  - meta 가 있고 `ok=False` → `prepare_failed` 건너뜀
  - meta 가 있고 `as_of ≠ label` → `as_of_mismatch` 건너뜀
  - meta 가 없으면 → `label == 오늘` 일 때만 캡처(레거시·테스트 가짜 호환), 아니면 `no_meta`
  - 건너뛴 목록은 캡처 완료 로그에 `skipped=` 로 남긴다.
- 호출자별 라벨: 09:30 자동 = `target_date=오늘`(`scheduler.py:3357`, 1줄) · 저녁 A1 = `as_of` · 비상 = `as_of` · 아침 캡처만 = 오늘 · **수동(파라미터 없음) = 오늘**(카드 3 (가) — 밤에 누르면 메모리 목록 기준일이 달라 저장 0건이 되고, 응답 메시지가 「메모리 목록은 <as_of> 기준이라 오늘 날짜로 저장하지 않았다」고 알린다. 응답 키는 불변).
- 알려진 잔여: 재기동 직후 첫 저녁 A1 전까지 비활성 전략은 meta 가 없다. 그 사이 09:30 캡처는 빈 99단계 행을 남긴다(현행도 비슷하다 — 지금은 +600초 재준비가 채운다).

### 2.6 확정 행 보호(③-b)와 market_ops, 테스트 영향

- **③-b** (`src/db/strategy_funnel.py:108-121`): `ON CONFLICT … DO UPDATE SET … WHERE NOT (strategy_funnel_snapshots.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)`. 거부되면 `RETURNING` 이 비어 `insert_snapshot` 이 None 을 준다. 마이그레이션은 없다. 효과: 20:00 뒤 거래일 비상 캡처(as_of=오늘)와 장중 재기동의 캡처만 경로가 오늘 09:35 확정 행을 덮지 못한다. A1 은 미래 날짜라 충돌하지 않는다. **A1 이 들어오면 평일 저녁 쓰기가 오늘 키를 치지 않으므로, cycle350 이 ③-b 단독 배포를 막았던 이유(「평일 저녁 쓰기 전부 거부」)가 사라진다.**
- **market_ops 저녁 행**(`routes/market_ops.py:168-169·531-543`): `funnel_rows` 조건을 `target_date = $1` → **`target_date > $1`** 로 바꾼다(`AND is_provisional = TRUE AND snapshot_at >= $2` 는 유지). 저녁 증거 = 「오늘 저녁에 쓴 다음 세션 행」이다. 오늘 날짜 잠정 행(아침 캡처만·비상)은 자연히 빠진다. 하한은 `_funnel_evidence_floor(today)` 공식 그대로(21:00 − 2시간 = 19:00). `funnel_last_at` 불변. evidence 키 `snapshot_rows_today` 는 이름이 조금 어긋나지만 계약이라 유지하고 docstring 으로 뜻을 적는다. 행 순서(시각순 14행)에서 저녁 funnel 행을 「일봉 적재(20:30)」와 「정산(21:30)」 사이로 옮긴다.
- **다시 짜야 하는 기존 테스트**(의미 전환, 이유는 테스트 주석과 history)
  - `tests/integration/test_cycle285_market_ops_pg_roundtrip.py::pg_1` — 「확정 행을 잠정 쓰기가 덮으면 저녁 증거로 센다」 → 「잠정은 확정을 못 덮는다(행·`snapshot_at` 불변) + 오늘 날짜 잠정 행은 저녁 증거가 아니다」. `pg_2`·`pg_4` 는 저녁 행을 `target_date=다음 날`로 바꾼다.
  - `tests/integration/test_cycle350_funnel_snapshot_at_pg.py` B2 계열 — 저녁 행 `target_date` 를 다음 날로. B1(잠정→잠정 덮어쓸 때 `snapshot_at` 갱신)은 유지. 새로 「확정→잠정 거부」와 「확정→확정 덮기 허용」을 둔다.
  - `tests/unit/routes/test_cycle350_market_ops_funnel_floor.py` — SQL 문구 단언을 `target_date > $1` 로. 16:20 기준 하한 기대값(14:20)은 19:00 으로.
  - `tests/unit/engine/test_cycle171_evening_funnel.py`(EVE-1 `time(16,20)` · EVE-3 `count_all` 폴링) · `tests/unit/engine/test_cycle273_daily_load_1810.py::test_g273f_2b`(16:20 핀) · `test_g273f_4`(본체에 `count_all` 존재·`max_bas_dd` 부재 단언 — 본체가 leaf 로 가고 마커 대기로 바뀐다) → 의도적 개정.
  - 프론트 `StrategyFunnel.cycle171.test.tsx`(배지 문구) · `KojiroMonitor.test.tsx`·`ScanMonitor.kojiro.test.tsx`(「16:20」 문구) · `frontend/src/test/handlers.ts:578-580`(market-ops `scheduled_at: "16:20"`).

---

## 3. 라이브 객체를 부를지 격리할지 — 판정

| 기준 | 라이브(A1) + PV-1 | 격리(A2) |
|---|---|---|
| 청산 입력 오염 | PV-1 로 0(donchian·kojiro 보유 엔트리 보존, stage3 미스탬프) | 0 |
| 모듈 전역 오염 | 21:00~21:30 에 `ticker_prev_close`·이름·캐시. 소비처는 틱·매수뿐이라 무해, 21:30 에 비워짐 | **격리 안 됨** — 별도 인스턴스도 같은 `scanner` 전역에 쓴다 |
| 다음 날 누수 | 부팅이 활성 전략 전부를 다시 준비한다. 비활성 전략은 미리보기 상태가 다음 날의 정답(as_of = 그날)이라 오히려 개선된다 | 없음 |
| 밤 후보 화면 | 대시보드가 밤새 다음 세션 후보를 보여 준다(의도) | 별도 경로가 필요하다 |
| 규모 | 전략 6곳 몇 줄 + leaf | 인스턴스 복제·레지스트리 우회·가격 캐시 격리까지 대공사 |

**판정: A1 라이브 호출로 간다. A2 전환은 필요 없다.** 단 PV-1 이 빠지면 A1 은 **안전하지 않다**(🔴 크리티컬 가드 1). PV-1 은 A1 과 떼어 배포하지 않는다. 돌연변이 M1(§6.2)이 이를 강제한다.

---

## 4. ②③④ 설계

### 4.1 ② 재준비 조건 — 입력이 실제로 바뀐 날만

아침 +600초 자리(현행 `evening_funnel_capture` 즉시 1회)의 판정 순서는 이렇다. 순수 함수 `decide_morning_reprepare(catchup, boot_meta, today_rows) -> Decision` 로 둔다.

1. **(i) 보충 적재가 입력을 채웠나** — 이번 기동의 즉시 실행 결과(§4.2 기록기)를 본다. full_universe `fetched > 0` · 일봉 `upserted_rows > 0` · basics `updated > 0` 중 하나라도 참이고 그 실행이 **성공**이면 `run` (reason=`catchup_filled:<task,…>`). 대상은 **활성+비활성 전부**다(입력이 모두에게 바뀌었으므로).
2. 보충 적재가 **실행됐지만 예외로 끝났으면** `skip` + WARNING `reason=catchup_failed:<task>`. 반쯤 쓰인 입력으로 다시 고르지 않는다. 부팅 목록(①′ 로 헤드 결손은 이미 KIS 로 바로잡혔다)을 유지한다.
3. **(ii) 부팅 준비 실패** — 활성 전략 중 부팅 meta 가 `ok=False` 이거나 funnel 1단계 `survived_count == 0`(stock_master 경합으로 유니버스 0)이면 `run`. 대상은 **실패한 전략만**이다(다른 전략의 부팅 상태, 특히 donchian 보유 ATR 을 건드리지 않는다).
4. 셋 다 아니면 `skip reason=inputs_current`. 이것이 평상시다. 오늘 날짜 funnel 행이 **하나도 없을 때만**(잠정·확정 불문, 저녁 A1 이 실패한 다음 날이나 배포 첫날) 부팅 목록을 **캡처만** 한다(`target_date=오늘`, 잠정, 준비 없음).
5. 기록기에 아직 결정이 안 들어온 작업이 있으면 pending 으로 보고 §4.2 로 넘긴다(+600초 시점이면 basics 는 +480초에 이미 결정했다).

- master(16:30, 시간 게이트)는 cycle360 ② 와 같이 **판정에 넣지 않는다**. 월요일 master 반영은 지금도 0 이다(§7).
- 로그: `[morning_reprepare] decision=skip|capture_only|run|defer|abandon reason=… window=W1|W2|- est_s= waited_s=`.

### 4.2 ③ 완료 대기와 조용한 창

**완료 신호 — `task_loop_helper` 즉시 실행 결과 훅**
- `run_periodic_task_loop(..., on_immediate_result: Callable[[str, str, dict | None], None] | None = None)`. 기본 None 이라 기존 호출부는 diff 0 이다. 사건 = `skip` · `run_start` · `run_ok`(요약 dict 동반) · `run_error`. 콜백 예외는 흡수한다.
- data_load_tasks 의 full_universe·일봉·basics wrapper 만 기록기 `funnel_capture.record_catchup` 을 넘긴다. 기록은 `(task_label → 사건, 요약, 시각)` 이다. 아침 판정은 **자기 task 시작 시각 이후의 기록만** 본다(프로세스가 여러 날 살아도 전날 기록을 읽지 않는다).
- 🔴 `count_all() > 0` 으로 되돌리지 않는다(돌연변이 M8).

**조용한 창** — 상수에서 계산하고 리터럴을 두지 않는다.
- W1 = [부팅 준비 완료, `TIME_PRESUBSCRIBE`(07:59) − 60초) = ~07:58. 07:59 사전 구독이 `get_scanned_tickers()` 를 읽기 전에 끝나야 한다.
- W2 = `market_state.MARKET_TABLE` 의 NXT `N2` 행 [08:50, 09:00) − 끝 60초 = 08:50~08:59. NXT 휴장·KRX 시가 단일가 구간이다. 08:59:10 H0STCNT0 사전 구독(`session.py:59`) 전에 끝난다. 특수 개장일(수능 등)은 그 표가 날짜별 행을 가지면 자동으로 따라간다.
- **예상 종료로 판정한다**: `now + est < 창 끝` 일 때만 시작한다. `est` = 이번 기동 부팅 준비의 전략별 실측 소요 × 1.5(대상 전략 합). 모르면 180초. 실측 기준값은 준비 한 번 60~75초(09-21 07:51:38→07:52:42, 09-22 07:45:11→07:46:10, 09-23 07:45:06→07:46:07)다. VB·LTV 1~2초, VCP 약 35초, kojiro 약 16초.
- **전략 단위 마감 검사**(🔴 크리티컬 가드 3): 각 전략 시작 전 `now + 그 전략 직전 소요 × 1.5 < 창 끝` 이 아니면 그 전략부터 멈춘다. 끝난 전략은 새 목록, 나머지는 부팅 목록을 유지한다. `[live_prepare_deadline] phase= stopped_before=<sid> window_end= est_s=` WARNING. 순서는 §2.4 와 같다(VB·LTV 먼저 — 09:00 시가 확정의 직접 소비자).
- 창 배정: 지금 W1 안이고 예상 종료가 W1 안이면 즉시 → 아니면 W2 까지 잠든다 → W2 도 불가하면(09:00 뒤 기동 등) `abandon` + WARNING. 창 밖 교정의 정본은 `daily/refresh` + 재기동이다(cycle360). **오후 재기동**(16:00~20:00)이면 다음 창이 저녁이므로 `skip reason=next_window_is_evening` — 21:00 A1 이 대신한다.
- (ii) 실패 재시도에 대한 알려진 한계: 09:00 뒤 재기동에서 donchian·kojiro 부팅 준비가 실패하면 그날 재시도가 없다. VB·LTV·BFB·VCP 는 5분 `_reprepare_breakout_if_empty`(`scheduler.py:2628`)가 계속 잡는다. cycle360 §3 ③ 이 이미 수용한 한계다. 보유 청산은 준비가 아니라 recompute 가 맡으므로 청산 영향은 없다.

### 4.3 ④ 저녁↔부팅 대조 마커 `[funnel_boot_vs_evening]`

- **위치**: `boot_manager.py` 익일청산 복구(`:519-528`) 바로 뒤. 보유 ∪ 익일청산이 확정된 시점이다. never-raise, 전체 10초 상한.
- **저녁 목록**: `list_snapshots(target_date=오늘)` 에서 `step_no=99 ∧ is_provisional` 행의 `survived_tickers`. 보통 전날 21:0x A1 이 쓴 것이다. 부팅 때 **모듈 메모리에 캐시**한다. 아침 재준비·비상 캡처가 이 행을 덮어도 대조 기준이 남는다.
- **부팅 목록**: 활성 전략 `get_scanned_tickers()`. 비교 집합 = 양쪽에서 **보유 ∪ 익일청산 제외**(저녁엔 보호 종목이라 마스터 차단·가격 필터를 통과하고, 부팅엔 복구 전이라 보유 0 이다 — §1.2 공용 행).
- **원인 힌트**(DB 3쿼리, 종목 단위 조회 금지): `params_changed` = `strategy_config.updated_at > evening_at`(20:00 자동 적용은 21:00 전이라 평시 0) · `bars_changed_after` = `stock_master_daily.updated_at > evening_at` 행 수 · `sm_refreshed_after` = `stock_master.refreshed_at > evening_at` 행 수 · `head_now` = `max(bas_dd)`.
- **형식**: `[funnel_boot_vs_evening] phase=boot|reprepare|emergency strategy= as_of= evening_at= evening_n= boot_n= same= added= removed= sample_added=<≤5> sample_removed=<≤5> held_excluded= params_changed= bars_changed_after= sm_refreshed_after= head_now=`. **INFO** 가 기본이다. `same=0 ∧ 힌트 전부 0`(설명 안 되는 차이)일 때만 **WARNING** 이다. 저녁 행이 없으면 `evening=absent` 1행.
- 기대값: 평시 6전략 `same=1`(§1.3 실측 — 금 19:46 과 월 07:51 부팅 준비는 분모가 같았다).

### 4.4 잠금 — 라이브 준비는 한 번에 하나

- `funnel_capture.LIVE_PREPARE_LOCK`(이벤트 루프별로 늦게 생성). wrapper 는 `live_prepare_one(strategy, *, phase)` 와 `live_prepare_many(strategies, *, as_of, phase, deadline)` 둘이다. 잠금·meta 기록·소요 측정·예외 격리를 한 곳에서 한다.
- **호출부 전수(현재 5곳)** → 전부 wrapper 경유: `boot_manager.py:261`(부팅) · `scheduler.py:758·767`(07:59 사전 구독 직전 VB/LTV·donchian 재준비) · `scheduler.py:2665`(`_reprepare_breakout_if_empty`) · `scheduler.py:3176`(저녁 → leaf 로 이동). AST 가드: `src/engine`(strategies 제외)에서 `.prepare(` 직접 호출 0.
- 비상 캡처는 잠금이 잡혀 있으면 기다리지 않고 409 를 준다. 아침 재준비는 기다린다(상한 = 창 끝).

### 4.5 카드3 (나) 관련 기록 — donchian 보유 트레일링 ATR 출처

- ② 이후 평시(재준비 0회)에는 **종일 「오늘 ATR」**(부팅 recompute)이다. 지금은 07:56 재준비 뒤 매수시점 ATR 이다. 16:20 재준비 제거로 애프터장도 오늘 ATR 이다.
- 🟠 **여전히 매수시점 ATR 로 떨어지는 경로 두 개**(이 설계가 새로 만든 것은 아니다. 현행 재준비와 같은 부수효과다): ② 가 `run` 이 된 날의 아침 재준비(donchian 이 대상일 때) · 거래일 오전 비상 캡처(as_of=오늘, 비미리보기라 PV-1 이 아니다). 21:00 A1 은 PV-1 로 안 떨어진다.
- P2 로 넘길 최소 수정 후보 한 줄: 「보유가 있는 상태의 비미리보기 준비 뒤 `_eager_refresh_stock_master_for_held_positions()` 의 recompute 루프(`scheduler.py:2281-2288`)를 한 번 더 부른다」. recompute 는 멱등이다(stage3 같은 날 재판정, `_stop_floor` tighten-only, 고점은 올리기만). 이 명세에서는 **구현하지 않는다**.

### 4.6 `scheduler.py` 접촉 범위와 라인

| 자리 | 변경 | 줄 증감 |
|---|---|---|
| `:71` `TIME_EVENING_FUNNEL_CAPTURE` | `time(16,20)` → `time(21,0)` + 주석(근거 = 적재 뒤·토큰 체인 뒤·정산 전) | 0 |
| `:188-293` `capture_funnel_snapshots` | `target_date` 키워드 + 전략별 `capture_skip_reason` 위임 + 완료 로그 `skipped=` | +8 |
| `:758` · `:767` | `strategy.prepare()` → `live_prepare_one(..., phase="presubscribe")` | 0 |
| `:2665` | → `live_prepare_one(..., phase="intraday_empty")` | 0 |
| `:3126-3188` `_evening_funnel_capture_once` | 본체를 leaf `funnel_capture.evening_capture_once(self)` 로 옮기고 3줄 위임만 남김 | 약 −45 |
| `:3357` `_auto_capture_funnel_snapshots` | `target_date=오늘` | +1 |

순감 약 35줄 → **약 3,777줄**(상한 `<3,900`, `test_cycle257…::test_line_count_below_3900` 외 자매 가드 6곳). `boot_manager.py` +10 내외, `data_load_tasks.py` +15 내외(저녁 task = 아침 판정 인라인 호출 후 `run_periodic_task_loop(immediate_first_run=False, wait_time=21:00)`, 새 task 속성 없음 → cycle79 G-AST2 4자리 무변경), `task_loop_helper.py` +15, `strategy_base.py` +30, 전략 6파일 +3~12, 새 leaf `funnel_capture.py` 약 350줄, `trading_calendar.py` +25.

---

## 5. 비상 캡처

- **경로**: `POST /api/strategy-funnel/snapshot?mode=emergency`. 파라미터가 없으면 §2.5 수동 캡처(오늘 라벨 + 가드)다. 리포터 키는 이 경로를 못 부른다(미들웨어 리포터 스코프 = GET + log-reports 한 경로).
- **판정 순서**(하나라도 걸리면 409 + `message` 에 사유와 다음 창)
  1. 휴장일 조회 모름 → `calendar_unknown`
  2. 시간창(카드4 (가)): 거래일이면 금지 = [07:58, 08:50) ∪ [08:59, 20:00). 휴장일은 종일 허용.
  3. 카드4 안의 구현 세목(카드 4 권고): ⓐ [`TIME_QUOTE_TOKEN_REFRESH` − 10분, + 15분) = [20:35, 21:00) 금지(`token_window`) ⓑ `_phase ∈ {settling, log_analysis}` 금지(`settling`) ⓒ 거래일 부팅 완료 전(오늘 날짜 `phase=boot` meta 없음) 금지(`pre_boot` — 부팅이 곧 다시 준비해 결과가 덮이고 DB 행만 남아 어긋난다)
  4. 예상 종료가 창 끝을 넘음 → `window` (창 끝 = 07:58 · 08:59 · 거래일 저녁은 다음 날 07:58, 휴장일은 없음)
  5. 잠금이 잡혀 있음 → `lock_busy`
- **실행**: 백그라운드 task(`daily/refresh` 와 같은 fire-and-forget + 200 `{status:"started", mode, as_of, expected_head, window_end}`). 본체 `funnel_capture.emergency_capture(scheduler, as_of)`:
  1. 대조 기준 확보: as_of == 오늘이면 부팅 때 캐시한 저녁 목록, 미래면 DB 의 as_of 잠정 행을 **덮기 전에** 읽는다
  2. `live_prepare_many(활성 우선순 → 비활성, as_of=as_of, phase="emergency", deadline=창 끝)` — as_of 가 미래면 미리보기 규칙(PV-1·P3)이 그대로 적용된다
  3. `capture_funnel_snapshots(is_provisional=True, target_date=as_of)` — ③-b 가 확정 행을 지킨다(20:00 뒤 거래일 비상은 사실상 0건 저장이 정상이다. 로그 `protected=`)
  4. `[funnel_boot_vs_evening] phase=emergency`
  5. `[funnel_emergency] decision=done as_of= prepared= saved= stopped_before=`
- **아침 재준비와의 중복**: 비상 캡처가 W2 전에 끝났고 그 뒤 보충 적재 완료가 없으면, 아침 재준비는 `skip reason=emergency_done`. 반대(재준비 뒤 비상)는 사람의 명시 요청이라 허용하고 로그에 `prior_phase=` 를 남긴다.
- **cycle360 §4 말미와 다른 점**: 「헤드가 뒤처지면 일봉부터 채운다(⑥)」는 **넣지 않는다**. ①′ 가 헤드 결손 종목을 KIS 폴백으로 이미 바로잡는다. 창(08:50~08:59)에 일봉 전량 적재(약 130~157초, 백필이면 더 길다)를 끼우면 마감을 못 지킨다. 필요하면 운영자가 `daily/refresh` 를 먼저 누른다(카드 4 ③).
- **화면 버튼은 두지 않는다**(카드 4 ④). API 파라미터만 둔다. 버튼을 둔다면 「값이 찍히는지까지 실측」 의무가 붙는 새 화면이다.

---

## 6. 단계 · 테스트 · 돌연변이 · 롤백 · 8영역 · 결정 카드

### 6.1 단계 (권고 = 카드 5 (가))

| 단계 | 내용 | 매매 규약 변화 | 배포 |
|---|---|---|---|
| **S1 — A1 본체** | `prepare(as_of)` 7전략 + PV-1·P3 · `trading_calendar.next_trading_day` · leaf(`resolve_as_of`·`evening_capture_once`·`live_prepare*`·잠금·meta·`capture_skip_reason`) · 21:00 상수 · 라벨 가드(09:30·수동) · ③-b · market_ops `target_date > $1` · ④(`phase=boot`) · 프론트 문구 | 애프터장 16:20 재준비 소멸(LTV 후보 갈아끼우기·donchian ATR 전환 소멸). 청산 규약 무변경(PV-1) | full, 장외 창(주말 가능) |
| S1 실측 | 첫 거래일 21:0x · 다음 날 07:4x (§6.4) | — | — |
| **S2 — 아침 ②③ + 비상** | 기록기 훅 · `decide_morning_reprepare` · 창·예상 종료·전략 단위 마감 · 오후 재기동 인계 · 비상 캡처 경로 · ④ `phase=reprepare|emergency` | 평시 아침 재준비 0회 → donchian 보유 트레일링 종일 오늘 ATR(카드3 (나) 방향) | full, 장외 창 |

S1 을 먼저 두는 이유: ④ 가 S2 의 판정 근거(평시 `same=1`)를 먼저 실측으로 확인해 준다. S2 는 「매일 돌던 것을 끈다」는 기능 비활성화급 변경이라 그 근거가 선행돼야 한다.

### 6.2 테스트 (tdd-engineer Red) · 돌연변이 (tester KILL 실측)

**단위·통합 시나리오** (시각·휴장일은 인자/패치로 고정 — 벽시계 금지, `trading_calendar._lookup_open` 전역 중립화 픽스처 재사용)

- A1-1 6전략 × {`prepare()`, `prepare(as_of=오늘)`} → `_funnel_steps`·`_candidates`/`_targets`·`_scanned_tickers` 동일(바이트 동일 계약).
- A1-2 6전략 `prepare(as_of=D+1)`, DB 헤드 D → D 봉이 「전일」(`prev_idx=0`), `expected_head=D` 가 어댑터로 간다.
- A1-3 벽시계 D 21:00 · `as_of=None` → D 봉 절단(현행). A1-2 와 짝을 이룬다.
- A1-4 `as_of < 오늘` → ValueError.
- PV-1a kojiro 미리보기 + 보유(D 종가 stage3) → `_held_stage3` 불변 · `_candidates[보유]` 가 원래 객체 그대로 · 보유 관측 행 0 · **곧이어 `check_exit_signal(보유, 가격)` = NONE**. 비미리보기 대조군(as_of=오늘) = 현행 재표시.
- PV-1b donchian 미리보기 + 보유가 내일 후보 자격 충족 → `_candidates[보유]` 불변 · `ticker_prev_close[보유]` 불변 · `_scanned_tickers` 에 보유 없음 · `get_effective_stop_price` 가 준비 전후 같음.
- P3 미리보기에서 kojiro 관측 3종 호출 0 · VCP `_breakout_watch` 동일성 유지(휴장일 낮 비상 포함).
- CAL `next_trading_day`: 09-23 → 09-28(추석) · 금 → 월 · 주말 조회 0 · None 전파 · 메모.
- RES `resolve_as_of` 표 5행(거래일 저녁·거래일 비상·휴장일 비상·모름 2종).
- EVE 저녁 once: 마커 ≥ 20:30 → 진행 · 마커 없음 → 30초 폴링 → 21:15 에 skip WARNING · 잠금 획득 · 준비 실패 전략은 캡처 건너뜀 · `target_date=as_of`·잠정.
- CAP 라벨 가드 4갈래(meta 불일치·실패·부재+오늘·부재+미래) · 09:30 이 `target_date=오늘`을 넘김 · 수동 캡처 밤(메모리 D+1) → 저장 0 + 메시지.
- ③-b (PG 왕복): 잠정→확정 거부(행·`snapshot_at` 불변, 반환 None) · 확정→잠정 덮기 · 잠정→잠정 덮기(`snapshot_at` 갱신) · 확정→확정 덮기.
- OPS market_ops: 미래 날짜 잠정 행(19:00 뒤) → done · 오늘 날짜 잠정 행 → 증거 아님 · 하한 = 21:00 − 2h · 행 순서.
- TIME 불변식: `TIME_STOCK_MASTER_DAILY_LOAD < TIME_EVENING_FUNNEL_CAPTURE` · `TIME_QUOTE_TOKEN_REFRESH + 15분 ≤ TIME_EVENING_FUNNEL_CAPTURE` · `TIME_EVENING_FUNNEL_CAPTURE + 20분 ≤ TIME_SETTLEMENT` · 기존 충돌 스캔 2종 초록.
- LOCK AST: `src/engine`(strategies 제외) 직접 `.prepare(` 0 · 5곳 wrapper 경유.
- ②(S2) 결정표 8행: 적재 없음 → skip · 일봉 `upserted_rows>0` → run(전체) · 일봉 실행 0행 → skip · basics `updated>0` → run · 적재 예외 → skip+WARNING · 부팅 예외 → run(그 전략만) · 유니버스 0 → run(그 전략만) · 오늘 행 전무 → 캡처만.
- ③(S2) 창: 07:50(W1 안) · 07:57 + est 90초(→W2) · 08:50 · 08:58 + est 90초(→abandon) · 16:30 재기동(→저녁 인계) · 전략 단위 마감(VB·LTV 뒤 VCP 에서 멈춤) · 완료 대기가 기록기를 본다.
- ④ 필드 · 보유 제외 · WARNING 조건 · 예외가 부팅을 끊지 않음.
- EMG(S2) 판정 순서 5단 · 토큰 창 · 정산 중 · 부팅 전 · 휴장일 as_of=다음 거래일 · 백그라운드 200 · ③-b 보호 로그.

**돌연변이** (각각 붉어지는 테스트 이름을 기록)

| # | 돌연변이 | 잡아야 할 것 |
|---|---|---|
| M1 | kojiro PV-1 제거(미리보기에도 보유 재표시) | PV-1a — **야간 `TRAILING_STOP`** |
| M2 | donchian 미리보기 `_candidates = {}` 복귀 | PV-1b 손절선 변화 |
| M3 | `today_str` 를 벽시계로 복귀(as_of 무시) | A1-2 |
| M4 | `expected_head` 를 벽시계 기준으로 | A1-2 · RES |
| M5 | 저녁 once 가 마커 대신 `count_all()` | EVE |
| M6 | 라벨 가드 제거(항상 `target_date` 로 저장) | CAP |
| M7 | ③-b `WHERE` 제거 | ③-b PG |
| M8 | 아침 완료 대기를 `count_all()` 로 | ③ |
| M9 | 창 판정을 시작 시각 기준으로(예상 종료 무시) | ③ 07:57·08:58 |
| M10 | 전략 단위 마감 제거 | ③ 마감 |
| M11 | ④ 보유 제외 제거 | ④(kojiro 가 늘 `same=0`) |
| M12 | market_ops `target_date > $1` → `= $1` | OPS |
| M13 | `TIME_EVENING_FUNNEL_CAPTURE = time(20,45)` | TIME + `test_c9` |
| M14 | 비상 토큰 창 검사 제거 | EMG |

### 6.3 롤백

- S1·S2 각각 `git revert` 한 커밋 + full 배포(backend 재시작). 창 = 21:35~07:45 · 15:30~16:00 · 주말. 🔴 20:00~21:35 push 금지(cycle283 D8). 🔴 보유 중 KRX 장중 push 금지(D6).
- 킬스위치는 두지 않는다. A1 은 21:00 에만 돌아 장중 매매에 닿지 않는다. S2 는 되돌리면 현행 +600초 무조건 재준비로 돌아간다. 둘 다 배포 한 번으로 원복된다.
- DB: ③-b 는 SQL 문 한 줄이라 마이그레이션이 없다. 미래 날짜 잠정 행은 되돌린 뒤에도 무해하다(다음 날 09:30 이 덮는다).

### 6.4 배포 뒤 실측 (tester, 기능 경로 변경 심층 검증 의무)

- S1 첫 거래일: 21:00~21:02 `[evening_funnel_capture] decision=run as_of=<다음 거래일> expected_head=<오늘>` · DB `target_date=다음 거래일 ∧ is_provisional` 약 59행 · market_ops 저녁 행 done · `[quote_token_refresh] window_issues_total=7` 불변 · 20:05/21:30 `[vcp_breakout_events] run_at` 이 오전 시각 · 21:30 `portfolio_risk` donchian 손절선 = 20:05 값.
- 다음 날 07:4x: `[funnel_boot_vs_evening] phase=boot` 6전략 `same=1` · 16:20 에 준비 로그 0줄.
- S2 첫 월요일: `[morning_reprepare] decision=skip reason=inputs_current` · 07:5x 준비 로그 0줄 · donchian 보유 트레일링 로그의 ATR = recompute 값.

### 6.5 8영역·승인

- **8영역 접촉 0** (`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`api/order`·`realtime/**`·`auth/**`). 8영역 sha 핀 절차 불필요.
- `scheduler.py` 접촉 6자리(§4.6) → **D3 승인 범위 재확인**. 파일 sha·세그먼트 핀(scheduler·전략 7파일·boot_manager·`_SRC_TREE_DIGEST`)은 값만 재핀한다. 대조는 cycle350 §8.4 방식(참조 Green 복사본에서 전수)으로 한다.
- 매매 행위 변경(애프터장 16:20 재준비 소멸 · 평시 아침 재준비 소멸 · 비상 경로 신설)은 D3·D4·카드4 결정으로 승인됐다. 이 문서가 선행 domain-consult 다.
- 안전 규칙 저촉 없음: 체결통보 · 15:20 일괄청산 · NXT 좀비 차단 · `tradable_boards` · `_reset_daily_state` 무접촉. 전략 끄기·`weight=0` 없음.

### 6.6 결정 카드

**카드 1 🔴 — 저녁 미리보기 준비에서 보유 종목 처리** (크리티컬 분기)
- (가) **PV-1: donchian·kojiro 는 보유 ∪ 익일청산 종목 엔트리를 보존하고 루프에서 건너뛴다. stage3 스탬프·재표시·관측 행 없음** ← 권고
- (나) as_of 만 주입(현행 코드 유지) — kojiro stage3 가 (오늘, 내일 판정)으로 찍혀 21:00~21:30 틱 하나로 야간 가격 무관 청산이 발사된다. donchian 21:30 리스크 손절선이 매수 ATR 로 바뀐다. **비권고**
- (다) A2 격리 인스턴스 — 모듈 전역이 격리되지 않아 불완전하고 규모가 가장 크다

**카드 2 — 저녁 캡처 시각**
- (가) **21:00** — 적재(20:32) 뒤, 토큰 체인(20:45~20:51) 뒤, 정산까지 30분 ← 권고
- (나) 20:45 — 토큰 강제 재발급과 같은 시각. `test_c9` 붉음 + 발급 중복 위험
- (다) 20:30 + 마커 대기 — 적재 창·토큰 창 가드 둘 다 위반

**카드 3 — 수동 캡처(파라미터 없음)의 라벨**
- (가) **오늘 라벨 + 기준일이 다른 전략은 건너뛰고 응답 메시지로 알린다** ← 권고
- (나) 메모리 목록의 기준일로 라벨(미래면 잠정) — 버튼 하나가 날짜를 스스로 고르게 되어 결과를 예측하기 어렵다
- (다) 현행 유지 — 밤에 누르면 내일 목록이 오늘 확정 행을 「확정」으로 덮는다. 비권고

**카드 4 — 비상 캡처 세부 (카드4 (가) 안의 구현 세목)**
- ① 20:00 뒤 창에서 토큰 재발급 [20:35, 21:00)과 정산 실행 중 제외 ② 거래일 부팅 완료 전 거부 ③ cycle360 §4 말미 「헤드가 뒤처지면 일봉부터 채움」 제외(①′ 가 대신함) ④ 화면 버튼 없이 API 파라미터만
- (가) **넷 다 채택** ← 권고 / (나) 항목별로 거절(거절한 항목은 명세에서 뺀다)

**카드 5 — 순서**
- (가) **S1(A1 본체 + 라벨 가드 + ③-b + market_ops + ④ 부팅) → 첫 거래일 실측 → S2(②③ + 비상)** ← 권고
- (나) S1+S2 한 번에 — 기능 비활성화급 변경(S2)이 근거 실측(④) 없이 들어간다
- (다) S2 먼저 — 저녁 목록이 없어 ④ 가 대조할 기준이 없다

---

## 7. 반례·한계

- **틱 부재는 가정이다.** 20:00 뒤 시세 프레임이 오지 않는 것은 실측이지 보장이 아니다(stale watcher 재구독에 시각 게이트가 없다). PV-1 은 이 가정이 깨져도 청산 입력이 바뀌지 않게 하는 장치다. VB·LTV 의 밤샘 보유 `_targets`/`ticker_prev_close` 는 가드 밖이지만 21:30 정리·부팅 재준비가 덮고, 발화 경로가 틱뿐이다.
- **적재 대상 ≠ 전략 유니버스.** 일봉 적재 대상은 하루 970~1,063 종목(실측 09-21~23)이다. 대상 밖 유니버스 종목은 저녁·아침 모두 ①′ KIS 폴백으로 읽힌다. VCP `full` 깊은 읽기는 F-3 예외 때문에 DB 의 밀린 헤드로 계산될 수 있다. 저녁과 부팅이 같은 쪽으로 틀려 ④ `same=1` 이 「둘 다 맞다」를 뜻하지는 않는다. 차집합 크기는 미측정이다(별건).
- **가격 필터 `bfdy_clpr` 는 D-1 종가다.** 16:10 basics 가 쓴 「전일 종가」라 D+1 미리보기에서도 부팅에서도 하루 밀린 값이다. 저녁과 부팅은 같다. 기존 한계다.
- **다음 세션부터 유효한 지정**(투자경고·거래정지·NXT 대상 변경)은 저녁도 부팅도 못 본다(cycle360 §7 그대로). 월요일 master 적재는 ② 판정에 없다.
- **액면분할·권리락 종목**(`lock` → KIS 폴백)은 저녁과 아침의 KIS 수정주가 응답이 다를 수 있다. ④ 가 잡는다.
- **저녁 목록의 영구 기록은 ④ 로그뿐이다.** 다음 날 09:30 확정 캡처가 잠정 행을 덮는다. 7일 추이(`list_recent_by_strategy`, `target_date ≤ 오늘`)에는 미래 날짜 행이 나오지 않는다.
- **토큰 체인이 15분 넘게 밀리면**(실측 최악 14분 40초) 21:00 A1 의 보조 풀 호출이 마지막 계정의 자연 재발급을 부를 수 있다. 완료 신호를 두지 않은 대신 받아들이는 잔여 위험이다.
- **09:00 뒤 재기동의 donchian·kojiro 준비 실패**는 그날 재시도가 없다(§4.2).
- funnel 화면 기본 날짜는 오늘 그대로다. 미리보기는 날짜를 골라서 본다. 바로가기는 이 명세 밖이다.

---

## 부록 — 실측 명령 (전부 읽기 전용, 2026-09-25 15:1x KST)

```bash
# 준비 소요·16:20 재준비 분모 변화 (09-21~23)
ssh ubuntu@3.38.228.74 'cd ~/auto_stock/logs; for f in auto_stock.log.2026-09-2[123]; do echo "=== $f"; LC_ALL=C grep -a -F -e "준비 완료" -e "[evening_funnel_capture_summary]" -e "기동 완료" "$f"; done'
# → 부팅 준비 64s/59s/61s · 재준비 59~62s · 16:20 VCP 711→659 · kojiro 703→657 · BFB 600→564 (09-23)

# 토큰 강제 재발급 체인
ssh ubuntu@3.38.228.74 'cd ~/auto_stock/logs; LC_ALL=C grep -a -F "[quote_token_refresh]" auto_stock.log.2026-09-23 | tail -4'
# → 20:51:07 accounts=7 issued=7 failed=0 elapsed_s=367 window_issues_total=7 (09-21·22 동일)

# 일봉 적재 요약
ssh ubuntu@3.38.228.74 'cd ~/auto_stock/logs; LC_ALL=C grep -a -F "[stock_master_daily_load_summary]" auto_stock.log.2026-09-2[123]'
# → 20:32:36 total=1012 · 20:32:34 total=1063 · 20:32:10 total=970 (failed=0)
```

```sql
-- (EC2 psql, DATABASE_URL)
-- SQL-1 날짜별 일봉 행 수
select bas_dd, count(*) from stock_master_daily where bas_dd >= date '2026-09-08' group by 1 order by 1;
-- → … 09-18 1273 · 09-21 1170 · 09-22 1106 · 09-23 970
-- SQL-2 작업 마커
select key, value from system_config where key ilike 'task_last_success_%';
-- → stock_master_daily_load 2026-09-23T20:32:10+09:00 · basics 16:24:42 · master 16:30:14 (full_universe 마커 없음 — cycle363 부트스트랩)
-- SQL-3 funnel 행 (target_date · 잠정 · 건수 · snapshot_at 범위)
select target_date, is_provisional, count(*), min(snapshot_at), max(snapshot_at)
  from strategy_funnel_snapshots where target_date >= date '2026-09-17' group by 1,2 order by 1,2;
-- → 매일 잠정 59행(snapshot_at 07:5x — B1 배포 전이라 덮어쓰기 시각 미갱신) + 확정 2행(97/98 훅)
```
