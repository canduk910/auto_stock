# 포렌식 — 장중 후보 35~38종목 stale 고정 (09-04 리포트 HIGH 1건)

- 작성: 2026-09-05 (읽기 전용 포렌식, 3 렌즈 logs-db / code-path / symbols 종합 + EC2 직접 재확인)
- 대상 기간: 2026-09-01 ~ 09-04 (대조 08-06 ~ 08-31, error.log 07-24 ~)
- 원천: EC2 host 로그 `~/auto_stock/logs/auto_stock.log.YYYY-MM-DD`(DEBUG, websockets 프레임 포함) · `system_logs`(INFO 2일 / WARNING+ 30일 retention) · `stock_master` · `stock_master_daily` · `positions` · `trade_history`
- 운영 변경 명령 0 (SELECT · grep · 로컬 코드 대조만)

---

## ① 결론 (한 문단)

stale 로 고정된 후보 35~38종목은 **세션·전략·유동성과 무관하게 `stock_master.nxt_tradable=False`(KIS `cptt_trad_tr_psbl_yn='N'` = NXT 거래대상 아님, KRX 단독) 종목과 1:1 로 일치한다** — 09-01~09-04 나흘 동안 ACK 받은 184~209 구독 종목이 `nxt_true ↔ H0UNCNT0 프레임 > 0` / `nxt_false ↔ 프레임 = 0` 으로 **예외 0건 완전 분할**되고(유일한 예외 09-01 064550 은 그날까지 NXT 편입 종목이었고 09-02 편출과 동시에 프레임이 0 이 됐다 — 자연 실험), 삼성전자우(거래대금 3,538억)·카카오(1,426억)·GS건설·한화솔루션·대우건설 같은 유동주가 포함되므로 침묵이 아니라 **채널 결함**이다. 모든 시세 구독이 통합 채널 `H0UNCNT0` 단일(`scanner.TICK_TR_ID`)이고 사이클 26 이 설계한 시간대별 `H0STCNT0` 전환(`get_active_tick_tr_ids`·`_board_transition_loop`)은 정의만 있고 호출자 0 인 죽은 코드라, **KIS 통합 채널이 NXT 거래대상 종목만 송출한다는 가설(확신도 ≈90%)** 아래 KRX 단독 종목은 SUBSCRIBE → `SUBSCRIBE SUCCESS` ACK 까지 정상이지만 체결 프레임이 하루 1건도 오지 않으며, K stale watcher 가 그 종목들을 종목당 하루 ~134회 7개 보조 세션으로 옮겨가며 unsub/sub(하루 SEND ≈14,600, `[ws_ack_orphan]` 7,120)하는 회복 가치 0 의 churn 이 관측된 것이다. 현상은 09-01 에 시작된 것이 아니라 **최소 07-24 부터 매일 31~44% 로 만성**이고, "09-01 이후" 인상은 `purge_old_logs()` 의 **INFO 2일 retention** 이 만든 관측창 착시다(09-02 20:10 이전 INFO 행이 삭제돼 있음). **손절 사각**: 보유 000815·003490(kojiro, 둘 다 nxt_false)은 WS 로는 **매일 종일 blind**(프레임 0)이고 손절 평가는 `_swing_rest_poll_loop` 60s REST 폴(09:05~15:20)만이 대신한다 — 구조적 공백 = **09:00:00~≈09:05:30(시가 포함)** + **15:20~15:30** + 폴 해상도 60~120s. 정규장 대부분은 60s 로 커버돼 리포트의 "간헐 stale" 표현은 부정확하지만 "사각 없음" 도 아니다. 더 큰 잠재 위험은 REST 폴이 없는 tick 전략(VB/LTV/BFB/VCP/momentum)이 보유 중 NXT 편출(064550 형 사건)을 맞으면 **손절 평가 0** 이 되는 경로다.

---

## ② 실측 표

### ②-1 날짜별 stale 고정 집합 × `nxt_tradable` × 프레임 (EC2 host 로그 직접 재파싱, 09:05~15:20)

| 날짜 | K 체크 수 | stale 1회 이상 | **고정(≥80% 체크)** | 고정의 nxt 분포 | ACK 종목 | 프레임>0 (nxt) | 프레임=0 (nxt) | 분할 예외 |
|---|---|---|---|---|---|---|---|---|
| 09-01 | 181 | 87 | **47** | F47 / T0 | 209 | 138 (T137 + **F1**) | 71 (F71 / T0) | 064550 — 32,806 프레임(12:08~19:59, NXT 애프터 포함) |
| 09-02 | 136 | 53 | **27** | F27 / T0 | 205 | 128 (T128) | 77 (F77 / T0) | 0 |
| 09-03 | 146 | 76 | **49** | F49 / T0 | 205 | 127 (T127) | 78 (F78 / T0) | 0 |
| 09-04 | 181 | 54 | **35** | F35 / T0 | 184 | 113 (T113) | 71 (F71 / T0) | 0 |

- 프레임 = `grep -o '|H0UNCNT0|[0-9]*|XXXXXX^'` (websockets DEBUG 수신 프레임, 09-04 총 1,250,374 건 / tr_id 분포 `0|H0UNCNT0|` 1,250,374 · `0|H0UNMKO0|` 4 · **H0STCNT0 0**)
- ACK 종목 = `[ws_action_summary] tr_id=H0UNCNT0 … ACK=[...]` 합집합. 09-04 세션별 SUBSCRIBE/ACK: main 626/437, 1004 956/836, 44606571 957/790, 71513056 957/790, ISA 963/776, RIA 961/773, fire 957/787, gold 957/789 — SEND 는 나가고 ACK 도 온다
- 고정 종목 nxt_true 는 **나흘 합계 0**. nxt_true 종목의 산발 stale 은 저유동주뿐: 09-04 3종목(004690 삼천리 8회 — 09-04 거래량 9,261주 / 114810 2 / 014620 2), 09-01 20종목(445680 12회 최대)

### ②-2 집합 교집합 (유니버스가 매일 바뀌므로 종목이 아니라 **속성**이 고정)

| 쌍 | 교집합 |
|---|---|
| 09-01∩09-02 | 19 |
| 09-01∩09-03 | 31 |
| 09-01∩09-04 | 17 |
| 09-02∩09-03 | 15 |
| 09-02∩09-04 | 17 |
| 09-03∩09-04 | 17 |
| **4일 공통** | **9** = 002990 금호건설 · 005935 삼성전자우 · 006360 GS건설 · 009830 한화솔루션 · 010170 대한광통신 · 047040 대우건설 · 079650 서산 · 353200 대덕전자 · 403870 HPSP |

유동성(09-03 `stock_master_daily` 거래대금, symbols/logs-db 렌즈): 고정 38종목 중앙값 **513억**, 최소 17억(032580), 상위 005935 3,538억 · 067290 2,593억 · 079650 1,681억 · 035720 1,426억 · 032940 1,267억. KOSPI200 편입 8종목 포함. 49/49 volume>0.

### ②-3 세션 분포 — 몰림 없음, 종목이 세션을 순환

| 항목 | 값 |
|---|---|
| 고정 종목 1개가 하루에 거치는 보조 세션 수 (min/med/max) | 09-01 7/7/7 · 09-02 7/7/7 · 09-03 7/7/7 · 09-04 7/7/7 (7개 전부) |
| 한 세션 최대 점유 비중 중앙값 | 0.18 ~ 0.24 (균등 = `_select_session` 라운드로빈 + `unsubscribe_in_pool` 이 `_ticker_to_session` pop) |
| `[tick_coverage_session]` 09-04 10~15h 평균 stale | main **0.0** · 71513056 5.4 · ISA 5.2 · fire 5.2 · 1004 5.1 · gold 5.2 · 44606571 5.4 · RIA 5.3 |
| 동시 2세션(split-brain) / 무세션(orphan) | `[stale_watcher_detail]` 하루 출현 n=183 = 세션당 detail 행수와 일치 → 매 사이클 정확히 1세션. `[tick_coverage] subscribed` vs Σ세션 차이 ±1~2 순간값뿐 |
| 세션 건강 | 09-04 `[ws_heartbeat]` 8세션 heartbeat_timeout=0, `[dispatch_drop_summary]` 전 기간 0행 |

main 이 0 인 이유는 WS 가 아니라 REST 폴(④·⑤ 참조).

### ②-4 시계열 대조군 — 09-01 에 바뀐 것 없음

`[tick_coverage]`(write_log 직접 기록, WARNING 으로 영속) 09:05~15:20 평균: 

| 날짜 | n | subscribed | stale | stale% |
|---|---|---|---|---|
| 08-24 | 8 | 162 | 53.8 | 33.1 |
| 08-25 | 4 | 160 | 49.5 | 30.9 |
| 08-26 | 108 | 122 | 38.8 | 31.9 |
| 08-27 | 130 | 154 | 53.5 | 34.8 |
| 08-28 | 134 | 118 | 38.8 | 32.8 |
| 08-31 | 124 | 146 | 46.7 | 32.1 |
| **09-01** | 108 | 163 | 51.9 | **31.8** |
| 09-02 | 40 | 115 | 35.9 | 31.2 |
| 09-03 | 132 | 146 | 50.7 | 34.7 |
| 09-04 | 132 | 108 | 36.4 | 33.6 |

logs-db 렌즈 추가: 08-06 36.4 / 08-07 35.2 / 08-10 44.3 / 08-11 39.6 / 08-14 41.8 / 08-18 39.1 … ; host error.log 07-24 32.1% / 07-28 43.9% / 07-30 30.6%. 절대 개수 감소(08-27 51~58 → 09-04 35~38)는 subscribed 154→108 축소 탓이지 회복이 아니다.

### ②-5 churn 정량 (09-04)

| 지표 | 값 | 비고 |
|---|---|---|
| `[stale_force_retry]` | 877건 / 115종목(전일) — **09:05~15:20 한정 399건 / 40종목 = 100% nxt_false** | 전일 115종목 중 nxt_true 45 는 전부 15:30 이후 NXT 애프터(자연 침묵) |
| 고정 종목당 SUBSCRIBE 이벤트/일 | median 134 (min 78 / max 135) | 120s 체크 × r=1..5 즉시 재등록 5회 + 600s cooldown 후 force_retry 1회 = 20분 주기 6회 ≈ 135 ✓ |
| 하루 SEND | SUBSCRIBE 7,492 + UNSUBSCRIBE 7,118 ≈ **14,600** | 보조 세션당 ≈957 SUBSCRIBE |
| `[ws_ack_orphan]` | **7,120** (host DEBUG) | `websocket.py:732` 가 msg1 substring `"SUBSCRIBE SUCCESS"` 로 `"UNSUBSCRIBE SUCCESS"` 도 매칭 → 이미 discard 된 키 = orphan. system_logs 에는 0행(DEBUG 미영속) |
| 슬롯 점유 | nxt_false 71~78 종목 = 풀 용량 328(41×8)의 ≈22~24% | 4일간 회복 가치 0 |

---

## ③ 코드 경로와 서명 대조 (시나리오별)

| # | 시나리오 | 판정 | 근거 |
|---|---|---|---|
| S1 | KIS 거부 / 슬롯 한도 (OPSP0008·MAX SUBSCRIBE) | **반증** | 09-04 `[ws_subscribe_reject]` 1건(18:39 003550, 애프터), OPSP0008 0, SUBSCRIBE≈ACK 세션별 일치 |
| S2 | 세션 죽음 / heartbeat / 재연결 폭풍 | **반증** | 8세션 heartbeat_timeout=0, `[silent_inactive_force_reconnect]` 09-04 1건(17:30 장후). 종목은 7세션 전부에서 동일하게 0 프레임 |
| S3 | `_ticker_to_session` 라우팅 오염으로 틱 폐기 | **반증** | 틱 핸들러는 `scheduler.py:586 register_tick_handler(risk.on_tick)` 단일 전역 — 어느 세션이 받아도 `ticker_last_tick` 갱신. `[dispatch_drop_summary]` 0. 프레임은 transport(websockets DEBUG) 단계에서 이미 0 = 도착 자체가 없음 |
| S4 | 파서 드롭 / 필드 수 미달 | **반증** | `handler.py:262` 가 H0STCNT0/H0UNCNT0/H0NXCNT0 동일 파서. silent drop 카운터 0 |
| S5 | 유동성 침묵 | **반증** | ②-2 거래대금. 같은 세션·같은 tr_id 로 nxt_true 종목은 100% 수신 |
| S6 | cycle240/241 부작용 | **반증** | 배포 09-02 23:03 / 09-03 06:15 전후 stale% 31.2 → 34.7 → 33.6 (범위 내). cycle240 은 5분 우선 재구독 경로만 필터(`[stale_priority_resubscribe] count=0 … filtered_not_desired=7`), 120s K watcher 는 `get_subscribed_tickers()` 전수라 무관 |
| S7 | **통합 채널 H0UNCNT0 이 NXT 거래대상 종목만 송출** | **확인(가설, ≈90%)** | (a) 나흘 × ~200종목 완전 분할 예외 0 (b) 064550 자연 실험 — `stock_master upsert: 064550 (nxt_tradable=True)` 08-27·08-28·08-31·09-01 16:15 → 09-01 32,806 프레임(16~19h NXT 애프터 포함) → **09-02 16:06 `nxt_tradable=False`** 로 반전 → 09-02 SEND 219건에도 프레임 0, 09-03·09-04 0 (c) NXT 는 한도 관리로 거래대상을 2026-02-12 650종목 → 7월 정기변경 610종목으로 축소했고 **카카오·대한전선·한국전력·현대건설 등이 편출**됐다(웹 확인, 하단 출처) — `stock_master` 의 'Y' 602 ≈ 610 이므로 `cptt_trad_tr_psbl_yn` 은 실제 NXT 거래대상 여부가 맞다(symbols 렌즈의 의미 의문 해소) |

코드 사실(로컬 대조):
- `src/engine/scanner.py:502` `TICK_TR_ID = "H0UNCNT0"  # (deprecated: 사이클 26 이후 get_active_tick_tr_ids() 사용)` — 그러나 `get_active_tick_tr_ids()`(`:518`) 호출자 **0**(테스트 제외), `scheduler._board_transition_loop`(`:1975`) `create_task` **0**. `git log -S` 결과 f7f0766(2026-05-20) 단 1건 = 정의만 추가되고 배선된 적 없음. `src/realtime/CLAUDE.md:95~120` 의 "시간대별 전환" 서술은 코드와 불일치
- `TICK_TR_ID` 직접 사용처 = scanner 1064/1072/1130/1160/1197/1234 · websocket 503/513/565/588 · websocket_pool 494/505/542/545 · stale_watcher_core(재등록) · stale_universe_guard:161 · stale_session_recovery:427 · order_engine:1104 · scheduler:1347
- K watcher 루프(`stale_watcher_core.py:270~365`): r=1..5 `unsubscribe_in_pool` + `subscribe(LOW)`(라운드로빈 → 세션 이동), r>5 600s cooldown 후 `[stale_force_retry]`(r=0 리셋) — stale 이 **구조적**이면 20분 주기 6회 무한 반복. `_stale_last_resubscribe_at` 갱신은 `subscribe` 성공 여부와 무관(cycle240 후속 H 미해결)
- `[stale_watcher_detail]` 의 `@HH:MM:SS` 는 `_stale_last_resubscribe_at`(`stale_diagnostics.py:131~136`)이지 마지막 tick 이 아니다 → tick 공백 측정에 쓸 수 없음
- `nxt_tradable` 파생 = `cptt_trad_tr_psbl_yn=='Y' and nxt_tr_stop_yn=='N'`(`src/api/condition.py:419`, `src/models/stock.py:6`), 24h TTL, 16:15 일괄 갱신 + 07:5x 보유·후보 eager 갱신. 08-31 07:52 064550 False → 08:05 True 플리커 1건 관측(원인 미확인 — 채널 자동 전환 설계 시 debounce 필요)

렌즈 간 모순 정리(EC2 재확인 결과):
- code-path "ws_ack_orphan 0" ↔ logs-db "7,120": **logs-db 가 맞다**. 마커가 `logger.debug` 라 system_logs 에 없고 host DEBUG 로그에만 있다(`grep -c ws_ack_orphan auto_stock.log.2026-09-04` = 7,120)
- code-path "115/119 종목이 회전, 고정 40 아님": **전일 합산의 착시**. 09:05~15:20 창의 force_retry 는 40종목·100% nxt_false, nxt_true 45종목은 전부 15:30 이후
- code-path "003490 retry 카운터 리셋 = 체결 정상 수신 방증": **오류**. 003490 프레임은 08-21·08-24·08-28·09-01~09-04 전부 0. 리셋은 REST 폴이 `risk.on_tick`(`risk.py:504` `ticker_last_tick[ticker] = now`)을 호출하기 때문
- code-path "000815 는 진짜 얇은 종목 자연 침묵": 000815 도 nxt_false — 거래량과 무관하게 같은 구조적 0
- logs-db/symbols "09-03 로그 40배 증가 원인 미확인": **retention 산물**. `purge_old_logs()`(`src/db/system_logs.py`, `src/db/CLAUDE.md:66`)가 20:10 마다 INFO `< now-2d` 삭제 → system_logs INFO 행: 09-01 0 · 09-02 33(전부 20:10:25 이후) · 09-03 7,781 · 09-04 8,084. WARNING+ 는 30일 보존이라 `[tick_coverage]`(WARNING)만 남아 있었다

---

## ④ 09-01 변경점과의 인과

- **배포 이력**: 08-29 19:01 a14bc98(cycle236) → **09-01 배포 0건** → 09-02 11:57 ad86768(cycle237) · 17:54 4cbea99(238) · 21:19 756be67(239) · 23:03 140a79a(240) → 09-03 06:15 6ac2bc2(241) · 13:25 c350129(242) · 21:12 233b663(243) → 09-04 18:22~ cycle246~249. 어느 것도 stale% 를 바꾸지 않았다(②-4)
- **stale 고정 시작 시각**: 특정할 수 없다 — 최소 07-24(error.log) 부터 매일 같은 형상. 09-04 하루 안에서는 07:59 부팅 구독 직후 첫 K 체크(08:01:56, stale 44 — 프리장엔 KRX 단독 종목이 체결 자체가 없다)부터 종일
- **"09-01 이후 만성" 의 정체**: 리포터가 읽는 system_logs 에 `[stale_watcher_detail]`·`[stale_force_retry]`·`[ws_action_summary]`(전부 INFO)가 **09-02 20:10 이후 분만 존재**(INFO 2일 retention). 즉 발병 시점이 아니라 관측창 하한이다. 08-2x 데이터는 host `logs/` 에만 있다
- **cycle240/241 과의 관계**: 둘 다 현상 이후 배포이며 원인도 치유도 아니다. cycle241 은 별개 문제(silent_inactive 재연결 폭풍 24~27건/일 → 1건)를 정상 해소했다. cycle240 이 닫은 5분 핑퐁은 phantom(매도 후 잔존) 종목용이었고, 이번 churn 은 120s K watcher 경로다(cycle240 자체가 이 경로를 범위 밖으로 명시)

---

## ⑤ 권고 조치

우선순위 순. 각 항목에 파일·계약·8영역 여부·검증법.

### A. 즉시 — 구조적 무송출 종목의 재등록 churn 중단 (비8영역, 1사이클)
- **파일**: `src/engine/stale_watcher_core.py`(K watcher 후보 산출 + `resubscribe_stale_priority`), `src/engine/stale_diagnostics.py`(`[stale_watcher_detail]`/`[tick_coverage_session]` 분류 라벨), `src/engine/scheduler.py` `_report_tick_coverage`(`[tick_coverage]` 에 `no_feed=N` 병기 — 3,999L 라인 상한 주의, 가능하면 leaf 로)
- **내용**: `stock_master.nxt_tradable=False` 종목은 stale 판정 대상에서 `no_feed` 로 분리 — 재등록(SEND)·force_retry·priority 재구독 **제외**, 카운트는 별도 필드로 유지(은폐 금지). HIGH(보유)도 재등록 효과가 0 이므로 제외하되 `[no_feed_held]` WARNING 1회/일 로 보유 종목이 WS blind 임을 매일 남긴다
- **계약 확인(비활성화 심층 검증 의무)**: 소비처 = `_evaluate_universe_guard`(stale>5 ∧ 거래량<1만 → 축출: 유동 nxt_false 는 `inquire_ccnl` 거래량이 커서 축출되지 않으므로 무영향, 저유동 nxt_false 는 기존대로 축출됨), `refresh_stale_ccnl_cache`, `[stale_watcher_detail]`, cycle215~218 split-brain 복구 경로(TICK 집합 정합성은 그대로), cycle241 시장 침묵 판정(`fresh_ratio` 분모에 no_feed 를 넣을지 결정 — 넣으면 nxt_false 편중 세션이 상시 suspect 가 되므로 **제외 권고**)
- **검증**: D+1 host 로그 `[stale_force_retry]` 09:05~15:20 399 → ≈0, `[ws_action_summary]` 보조 세션 SUBSCRIBE ≈957 → <100, `grep -c ws_ack_orphan` 7,120 → ≈0, `[tick_coverage] stale` ≈ 0~5(저유동 nxt_true 잔여) + `no_feed≈35~78`. ⚠️ 의미 반전 — 배포 전후 `stale=` 합산 금지

### B. 근본 — 종목 속성 기반 시세 채널 선택 (8영역 승인 필요)
- **가설 검증 프로브 먼저(다크런치)**: env `KRX_ONLY_CHANNEL_PROBE_TICKERS`(기본 빈 값) 에 005935·035720 을 넣으면 `_scan_loop` 이후 보조 세션 1개에서 `H0STCNT0` 로만 구독 + `[krx_channel_probe] ticker= frames=` 5분 계측. 핸들러는 이미 H0STCNT0 를 동일 처리(`handler.py:262`)하므로 성공 시 `[tick_coverage]` 에서 그 종목이 fresh 로 돌아서는 것이 바로 판정이다. 장중 1시간이면 충분. 주의 = 풀의 `_ticker_to_session`·`get_subscribed_tickers()` 는 `TICK_TR_ID` 만 세므로 프로브 2종목은 슬롯 회계 밖(문서화). 수동 스크립트로 기존 계좌 approval_key 를 재사용해 별도 접속하는 방식은 라이브 세션 충돌 위험이 있어 **비권고**
- **본 시정(프로브 성공 시)**: 채널 리졸버 1개(`tick_tr_id_for(ticker) -> "H0STCNT0" | "H0UNCNT0"`, 소스 = `stock_master.nxt_tradable` 메모리 캐시) 를 두고 위 `TICK_TR_ID` 직접 사용처 전부를 경유시킨다. 풀/세션의 TICK 필터(`websocket.py:503/513/565`, `websocket_pool.py:494/505/542/545`)는 `{H0UNCNT0, H0STCNT0}` 집합으로. `_ticker_to_session` 은 tr_key 단일 키라 동일 종목 이중 채널 금지 불변식 필요. **접촉 파일 = 8영역 `scanner.py`·`websocket.py`·`websocket_pool.py`(cycle221 가드 기준) + `order_engine.py:1104`(매도 후 unsubscribe) + 비8영역 stale_watcher_core·stale_universe_guard·stale_session_recovery·scheduler:1347** → 사용자 승인 + sha 핀 재핀 + 뮤테이션 실증 대상
- **플리커/편출 대응**: NXT 편출(064550 형)은 분기 정기변경 + 수시 시장조치로 발생 — 보유 종목이 편출되면 다음 16:15 갱신 또는 부팅 시 채널을 재결정해 재구독(scan_loop 델타가 `(tr_id, ticker)` 쌍으로 desired 를 비교). 07:5x 보유 eager 갱신에서 관측된 False 플리커(08-31 064550)는 debounce(16:15 값 우선)
- **시간대별 전환(사이클 26 설계) 처분**: 시간 기반 전환만으로도 09:00~15:30 은 H0STCNT0 로 고쳐지지만 하루 2회 전 종목 대량 재구독 churn 이 생기고 nxt_true 종목의 NXT 체결을 잃는다 → **속성 기반이 우월**. `get_active_tick_tr_ids`/`_board_transition_loop` 는 refactor-review 로 삭제 또는 재목적화, `src/realtime/CLAUDE.md` 의 전환 서술 정정
- **검증**: ②-1 과 동일한 분할 검사를 D+1 에 반복 — ACK 종목 100% 프레임>0 이면 종결. 부하 확인: nxt_false 71~78 종목이 실제 틱을 내기 시작하면 프레임/일 1.25M → +30~40% 예상, `dispatch_drop_summary`·이벤트루프 지연 관측

### C. 보유 사각 축소 (B 착지 전 임시, scheduler 상수 — 라인 상한 주의)
- `SWING_REST_POLL_EARLY_START` 09:05 → 09:00:30(held_only) 로 시가 직후 5분 공백 축소, 15:20~15:30 은 동시호가라 REST 현재가가 정적이어서 실익 낮음. B 가 붙으면 불필요
- kojiro/donchian 외 tick 전략이 nxt_false 를 보유하게 되는 경로(편출 사건)는 A 의 `[no_feed_held]` WARNING 이 매일 잡는다 — 발화 시 수동 판단

### D. 관측 정정 (비8영역)
- `[tick_coverage]` fresh 는 WS 건강도가 아니다(REST touch 포함, main 0% 의 정체). `[stale_watcher_detail] @ts` 는 마지막 재등록 시각 — 필드명 `resub@` 로 정직화하거나 `last_tick@` 병기
- 일일 루틴 리포터: system_logs INFO 는 48시간만 남으므로 "N일 전부터" 류 주장은 host `logs/auto_stock.log.*`(07-24~) 로 확인해야 한다. 이번 HIGH 판정의 "09-01 이후 만성"·"stale_force_retry 877건" 은 정확했지만 발병 시점과 원인 귀속이 틀렸다
- 리포터 판독 가이드: A 배포 전까지 `stale 35~38` 은 **예상값**이며 임계 재조정·세션 재시작·수동 재구독(`POST /api/realtime/resubscribe`)은 효과 0 이므로 금지

---

## ⑥ 열린 질문

1. **H0STCNT0 가 KRX 단독 종목을 실제 송출하는가** — 기대는 예(NXT 이전 채널)이지만 05-08 b77a764 전환 이전 로그가 남아 있지 않다. B 프로브가 유일한 답. KIS 공식 문서(`ccnl_total.py` 샘플, `docs/kis/domestic-stock-realtime.md:725`)에는 통합 채널의 대상 종목 제한이 명시돼 있지 않다 — KIS 문의 가치 있음("NXT 비대상 종목 SUBSCRIBE 가 SUCCESS ACK 를 주면서 데이터는 없다")
2. nxt_true 종목을 H0STCNT0 로 구독하면 NXT 체결이 빠지는가(→ 이중 채널 회피 위해 nxt_true 는 H0UNCNT0 유지). 같은 종목 두 채널 동시 구독이 KIS 슬롯 2개를 소비하는지
3. `stock_master` 플리커(08-31 07:52 064550 False → 08:05 True) 의 원인 — 응답 결측 시 기본 False 인지. 채널 자동 전환의 debounce 규칙을 이 답에 맞춘다
4. 09-04 tick 후보 164종목 중 nxt_false 54(33%) — B 이후 tick 전략 유니버스가 1/3 커지는 효과의 체결률·슬롯 예산 재산정(메인 41 헤드룸 후속과 연동)
5. `[tick_coverage]` 08-03 "98% fresh" 이상치(logs-db) — `get_subscribed_tickers()` vs 세션 뷰 소스 차이로 추정, 미확인
6. K watcher 가 `subscribe` 성공 전 `_stale_last_resubscribe_at` 을 스탬프하는 순서(cycle240 후속 H) — A 와 같은 파일이므로 동행 시정 후보

---

### 부록 — 검증 명령 (읽기 전용)
```bash
# 프레임 유무 (host, KST)
ssh auto-stock 'grep -c "|005935^" ~/auto_stock/logs/auto_stock.log.2026-09-04'   # 0
ssh auto-stock 'grep -c "|005930^" ~/auto_stock/logs/auto_stock.log.2026-09-04'   # 20781
# 064550 자연 실험
ssh auto-stock 'grep -h "stock_master upsert: 064550" ~/auto_stock/logs/auto_stock.log.2026-09-0[1-3]'
# 정규장 force_retry 의 nxt 분포 (DB) — 40종목 / F40 / T0
select ticker from system_logs … where message like '%[stale_force_retry]%' and time between 09:05 and 15:20  ⨝ stock_master.nxt_tradable
# INFO retention 확인
select date, log_level, count(*) from system_logs where message like '[src.%' group by 1,2   -- 09-01 INFO 0 / 09-02 33(≥20:10) / 09-03 7,781
```

웹 출처(NXT 거래대상 축소·편출): [넥스트레이드 거래대상종목(646→610)](https://nextrade.co.kr/menu/marketData/menuList.do) · [KB증권 — 대체거래소(NXT) 거래 가능 종목 축소 안내(2026-02-10)](https://www.kbsec.com/go.able?linkcd=s060901010000&seq=10009476&idt=20260210) · [한국경제 — 카카오·한전·에코프로 등 20개 종목 넥스트레이드서 거래중단](https://www.hankyung.com/article/202511031063i) · [삼성증권 — NXT 거래정지 종목 안내(6/15~)](https://www.samsungpop.com/ux/kor/customer/notice/notice/noticeViewContent.do?MenuSeqNo=24040)
