# cycle349 — VCP 관측 3종 (명세)

사용자 결정 2026-09-24: VCP 는 「A안 유지(G안 파라미터 그대로) + 관측 기록 3개 추가」.
근거 = `_workspace/domain_consult/cycle347_vcp_zero_fills_cause.md` (§결론 · 97행 · 103~130행 선택지 A).
**관측 전용 — 매매 행위 0.** VCP 후보 집합·순서·매수 판정·파라미터·`DEFAULT_PARAMS` 한 글자도 바꾸지 않는다.
8영역·`scheduler.py` 무접촉(② 보류로 `scheduler.py` 를 건드리는 경로가 사라졌다).

## 왜
G안 이후 후보 12~14종목인데 매수 관문 9번(돌파 edge-crossing)을 한 번도 지나지 않았다. 돌파선(`base_high`)이
전일 종가보다 중앙 +9.7% 위였다. 그런데 **오전 후보 목록 자체를 사후에 복원할 수 없었다** — 로그가 후보를
나열하지 않고, 퍼널 스냅샷은 16:20 재준비 숫자로 덮였다. 앞으로 10거래일 동안 「돌파 사건이 있었나」를
판정하려면 세 가지를 남겨야 한다.

---

## ① 오전 후보별 돌파선 거리 — `[vcp_breakout_distance]`

**위치**: `VcpBreakoutStrategy.prepare()` 끝. `self._scanned_tickers = ...`·`self._bought_today.clear()`·
`stats["last_run_at"]`·`VCP 준비 완료` INFO 로그 **뒤**, 새 헬퍼 하나를 **자기 try** 로 부른다.
유니버스 0종목 조기 반환 분기(`if not tickers: ... return`)에서도 같은 헬퍼를 부른다(후보 0 = 요약 `n=0`).

D1. **오전 판정** — 「오늘 매매에 쓰일 수 있는 prepare」 = 실행 시각이 **매수 창 끝 이하**인 prepare.
    시계는 `check_buy_signal` 의 창 게이트와 **같은 식**(`datetime.now().time()` vs
    `_parse_time_hhmm(self.config.params["entry_end"])`)을 쓴다. 이유 = 관측의 「오전」과 게이트의 「창」이
    갈라지면 안 된다. 창 끝을 넘은 prepare(16:20 저녁 재준비, 21:30 이후 재기동 등)는 **줄을 하나도 남기지 않고**
    ③의 관측 대상(watch)도 **건드리지 않는다**.
D2. **후보별 1줄** (WARNING — INFO 는 `system_logs` 2일 보존·리포트 미반영):
    `[vcp_breakout_distance] run=HH:MM:SS ticker=<6자리> base_high=<int> prev_close=<int> dist_pct=<+x.xx|na> box_high_date=<YYYYMMDD|na> box_high_ago=<int|na> base_low=<int> base_len=<int>`
    - `dist_pct = (base_high − prev_close) / prev_close × 100`, 소수 2자리. **분모 = 전일 종가.** `prev_close <= 0` 이면 `na`.
    - `box_high_date` = `_detect_base` 가 쓴 창(`candles[:base_len]`, `candles[0]` = 전일, 최신순) 안에서
      `stck_hgpr == base_high` 인 봉 중 **가장 최근**(인덱스 최소) 봉의 `stck_bsop_date`. `box_high_ago` = 그 인덱스 + 1
      (전일 = 1). 못 찾으면 둘 다 `na`.
    - `base_len` = `_detect_base` 결과의 `length`. `base_low` = 결과의 `low`.
    - 방출 순서 = `_candidates` 삽입 순서.
D3. **run 요약 1줄** (WARNING — 오전 prepare 1회당 1줄. 단 **같은 KST 날짜의 직전 요약과 내용(`n`·`median_pct`·`within5`·`over10`·`tickers`)이 같으면 생략**한다 — team-leader 결정(tester F3): 후보 0 인 날 `_reprepare_breakout_if_empty` 가 5분마다 prepare 를 불러 요약이 62줄이 되던 것을 막는다. 「직전과 같으면」이라 A→B→A 로 바뀌면 세 줄 다 남는다):
    `[vcp_breakout_distance_summary] run=HH:MM:SS n=<후보수> median_pct=<x.xx|na> within5=<int> over10=<int> tickers=<t1,t2,...>`
    - `median_pct` = `dist_pct` 가 수치인 후보들의 중앙값(짝수 개면 두 가운데 평균). 없으면 `na`.
    - `within5` = `dist_pct <= 5.0` 개수, `over10` = `dist_pct > 10.0` 개수.
    - `tickers` = 그 run 의 후보 전체(삽입 순서). **이 줄이 run 별 후보 목록의 정본**이다(아래 D4 cap 으로 후보 줄이 생략돼도 목록은 남는다).
D4. **중복 억제** — 후보 줄은 `KstDailyEmitCap`(`src/engine/daily_emit_cap.py`, 인스턴스는 전략 객체 소유) 키
    `(ticker, base_high, prev_close)` 로 **하루 1회**. 07:55 재준비가 같은 값을 내면 그 줄은 생략되고, 값이 바뀌었거나
    새 종목이면 찍힌다. 요약 줄은 cap 하지 않는다.
D5. **읽기 전용** — `_detect_base`·`_check_*`·`_candidates`(키·값 모두)·`_scanned_tickers`·`_scan_stats`·`_funnel_steps`·
    `_bought_today`·`scanner.ticker_prev_close` 를 **바꾸지 않는다**. 필요한 입력(후보별 `candles`·`base` dict)은 루프 안
    `self._candidates[ticker] = {...}` 대입 **직후** 로컬 dict 에 참조만 모아 둔다(새 계산·새 I/O 0). `_candidates` 엔트리에
    키를 추가하지 않는다(UI `get_targets_status`·다른 소비처로 새어 나간다).
D6. **never-raise** — 헬퍼 본체 전체 try. 한 종목 계산 실패 = 그 종목 줄만 생략. 헬퍼가 어떤 예외를 던져도 `prepare()` 는
    확장 전과 같은 상태로 정상 종료한다.

## ② 퍼널 스냅샷 오전/16:20 분리 — 🔴 보류 (사용자 결정 대기, 코드 변경 0)

메인 세션 지시(2026-09-24): ② 는 이 사이클에서 **고치지 않는다.** 이 사이클은 ①③ 만 착지한다.

### 보류 사유
16:20 캡처는 일봉 적재(20:30)보다 앞이라 **전일 봉(D-1) 기준**이다(`vcp_breakout.py` 의 오늘 봉 절단 = 날짜 비교, `scheduler.py:71` 주석
「여전히 전일 봉 기준」). 즉 16:20 목록은 **그날 아침 후보와 같은 입력을 저녁 유니버스(16:10 basics)로 다시 고른 것**이지 다음 거래일
미리보기가 아니다(실측 차이도 시총·거래대금 단계에 몰렸다: 09-22 667→708, 09-23 711→659). 이것을 다음 거래일 날짜로 저장하면
**D-1 기반 목록에 D+1 라벨을 붙이는 거짓 정보**가 된다. 저녁 캡처의 시각·방식(20:30 적재 뒤로 옮길지, 라이브 전략 `prepare()` 를
부르지 않는 격리 계산으로 바꿀지)은 사용자 결정이다.

### 원인 (tester 확정 — 코드·운영 DB·EC2 로그, 가설 H1~H5 전부 참. 조사 = 읽기 전용, SELECT 만)
하루 세 번 같은 `(target_date=오늘, strategy_id, step_no)` 행에 쓴다.

| 시각 | 누가 | 쓰기 |
|---|---|---|
| 07:57 (부팅 +600초) | 저녁 캡처 태스크의 **즉시 1회** — `data_load_tasks.py:233-248`(`initial_delay_secs=600`, `immediate_skip_if_fresh_hours` 미전달) → `task_loop_helper.run_periodic_task_loop` 즉시 블록. 태스크는 `start()` 안 `scheduler.py:733` 에서 생성되고 `run_daily` 가 매일 `start()` 를 다시 부르므로 **재시작이 없어도 매일** 돈다. 전 전략 `prepare()` 재실행 후 | 잠정(TRUE) INSERT → `snapshot_at` 이 여기서 고정 |
| 09:35 | `_scan_loop` 첫 패스 `_auto_capture_funnel_snapshots`(`scheduler.py:2512`) | 확정(FALSE) UPSERT — **그날 매매에 쓴 목록** |
| 16:21 | 16:20 저녁 캡처(`_evening_funnel_capture_once`) — 전 전략 재준비 후 `capture_funnel_snapshots` 가 호출자와 무관하게 `today_kst` 사용 | 잠정(TRUE) UPSERT → **확정 행을 저녁 숫자로 덮는다** |

- H1: `src/db/strategy_funnel.py:114-120` `DO UPDATE SET` 에 `snapshot_at` 없음(운영 DB 트리거 0, 기본값 `now()`) → 최초 INSERT 시각 고정.
  `src/db/CLAUDE.md:182` 와 그 파일 docstring 의 「UPSERT 시 자동 갱신」은 **거짓**이다(문서 정정은 ② 착수 때 함께).
- H5: 의도(migration `040_funnel_provisional.sql:4-5` 「다음 영업일 후보」 + `StrategyFunnel.tsx:436` 배지 「익일 아침 …」)와 코드(오늘 날짜)가 다르다.

운영 DB 실측(VCP, 날짜마다 10행 전부 `is_provisional=TRUE`, `snapshot_at` 하나):

| target_date | snapshot_at (KST) | step3 | step5 | step7 | step8/9/99 |
|---|---|---|---|---|---|
| 09-21 | 08:03:53 | 652 | 70 | 17 | 8 |
| 09-22 | 07:57:16 | 708 | 92 | 18 | 13 |
| 09-23 | 07:57:18 | 659 | 73 | 20 | 14 |

- 09-10~09-23 전 거래일 같은 모양: TRUE 59행/7전략, FALSE 는 `strategy_id='ALL'` 스캐너 훅(step 97/98) 2행뿐 = **09:35 확정 캡처는 한 행도 살아남지 않았다.** 미래 날짜 행 0.
- `daily_log_reports.metrics.strategy_funnel_stages.vcp_breakout`(20:05 저장): 09-22 step3 708·step9 13 / 09-23 659·14 = **20:05·21:30 리포트도 16:20 숫자를 읽는다.**

EC2 파일 로그 시각표(`VCP 준비 완료` · `[funnel_snapshot] 캡처 완료`):

| 날짜 | 부팅 prepare | +600초 즉시 실행(TRUE) | 09:35 확정(FALSE) | 16:20 재준비 → 16:21(TRUE) |
|---|---|---|---|---|
| 09-21 | 07:52:26 `7/729` | 08:03:38 `5/640` → 08:03:53 | 09:35:07 | 16:20:55 `8/652` → 16:21:13 |
| 09-22 | 07:45:55 `12/667` | 07:57:01 `12/667` → 07:57:16 | 09:35:06 | 16:20:57 `13/708` → 16:21:15 |
| 09-23 | 07:45:51 `14/711` | 07:57:02 `14/711` → 07:57:18 | 09:35:05 | 16:20:55 `14/659` → 16:21:12 |

### 결정에 필요한 사실 (착수 시 재사용)
- 소비처: `routes/market_ops.py::_COMBINED_SQL` 의 `funnel_rows`(`target_date=$1 AND is_provisional`)는 지금도 07:57~09:35 에 「완료」로 오판하고,
  `funnel_last_at` 은 07:57 즉시 실행을 「저녁 캡처 마지막 성공」으로 보인다. `log_metrics_collector._collect_strategy_funnel_stages` 는 오늘 행(= 16:20 숫자)을 읽는다.
  프론트 funnel 화면은 `snapshot_at` 을 표시하지 않고 날짜 입력에 `max` 제한이 없다.
- `src/api/condition.py::next_trading_day` 는 실패(예외·Y 행 없음)를 「다음 달력일」 반환으로 삼켜 **호출자가 구분할 수 없다**. 본문은
  `test_cycle282_ast_purity.py` H5 sha 핀(「한 글자도 안 바뀐다」)이라 쓰려면 3상태 새 헬퍼가 필요하다. KIS 문서는 CTCA0903R 를 「가급적 1일 1회」로 요청한다.
- 착수하면 붉어질 것: `scheduler.py` 전체 sha 핀 10파일 + 정확 줄 수 핀 11곳, `test_cycle285_market_ops_pg_roundtrip.py::test_c285_pg_1/pg_4`,
  벽시계 의존 `test_cycle171_evening_funnel::test_g_171_eve_2b`(시계 미고정이라 16:20~24:00 에만 붉어진다), cycle145 docstring 문구 가드.

### 곁가지 (고치지 않음 — 사용자 결정 대기)
부팅 +600초 즉시 실행이 **매 거래일 07:56~08:03 에 7전략 전부를 재준비**한다. 09-22·23 은 결과가 부팅 때와 같았지만 09-21 은
07:53 `full_universe_load` 즉시 실행·07:59 일봉 적재 즉시 실행이 끼어 후보가 바뀌었다(VB 81→63 · donchian 3→1 · BFB 33→32 · VCP 7→5 · kojiro 8→7) —
**그날 실매매 후보는 08:03 결과**였고, 그 재준비는 NXT 프리장(08:00~) 중에 살아 있는 전략 상태를 교체했다. 16:20 재준비도 애프터마켓(16:00~20:00)
중 살아 있는 전략의 `prepare()` 를 다시 부른다. 이 사이클은 두 동작 모두 **무접촉**이다(`scheduler.py`·`data_load_tasks.py`·`task_loop_helper.py` 무변경).
①③ 은 이 재준비와 공존한다 — 07:57 재준비는 청산선이 아니라 매수 후보를 바꾸므로 ①이 그 run 의 요약 줄을 남기고 ③의 watch 를 그 목록으로 교체한다.

## ③ 하루 돌파 사건 수 — `[vcp_breakout_events]` + `daily_log_reports.metrics["vcp_breakout_events"]`

E1. **관측 대상(watch)** — ①의 오전 prepare 가 끝날 때(조기 반환 포함) 새 인스턴스 속성(예: `self._breakout_watch`)을
    **통째로 교체**한다: `{date: KST 날짜, run_at: "HH:MM:SS", tickers: {ticker: {base_high, max: 0, ticks: 0, first_cross_at: None}}}`.
    tickers 는 그 시점 `_candidates` 와 같은 집합·같은 `base_high`. 저녁 prepare 는 watch 를 건드리지 않는다(D1).
    `prepare` 가 도중 예외로 빠지면 watch 는 직전 값을 유지한다(알려진 한계 — 문서에 적는다).
E2. **틱 관측 훅** — `check_buy_signal` 의 **첫 문장(계좌 SOFT 게이트 `if`) 바로 다음**에 새 헬퍼 한 줄
    (예: `self._observe_breakout_tick(ticker, current_price)`). 첫 문장 자리는 cycle233 AST 가드가 계좌 게이트로 고정한다.
    헬퍼 계약:
    - 먼저 `watch` 가 없거나 `ticker` 가 watch 에 없으면 즉시 반환(비후보 틱 비용 = dict 조회 1회).
    - watch `date` ≠ 오늘(KST) 이면 반환. `current_price <= 0` 이면 반환.
    - 창 판정은 게이트와 **같은 식**을 매번 params 에서 읽어 쓴다: `now_t < entry_start or now_t > entry_end` 면 반환.
    - 창 안이면 `ticks += 1`, `max = max(max, current_price)`, `first_cross_at` 이 None 이고 `current_price >= base_high`
      면 `first_cross_at = now_t.strftime("%H:%M:%S")`.
    - **이 헬퍼가 읽고 쓰는 것은 watch 뿐**이다. `_prev_price`·`_vol_latch`·`_bought_today`·`_scan_stats`·`_gate_emit_capped`·
      `_candidates`·`state` 무접촉. 반환값 없음 — `check_buy_signal` 의 흐름·반환값에 관여하지 않는다.
    - never-raise(본체 전체 try — 예외가 on_tick 으로 새면 틱마다 WS 재연결이 된다).
E3. **하루 요약** — 전략에 순수 읽기 메서드(예: `breakout_event_summary(target_date) -> dict`):
    - watch 없음·watch `date` ≠ `target_date` → `{"status": "no_watch", "date": iso}`
    - 그 외 `{"status": "ok", "date", "run_at", "window": "HH:MM-HH:MM"(params), "partial": run_at > entry_start,
      "candidates": N, "observed": ticks>0 인 수, "crossed": 관측 종목 중 max >= base_high 인 수,
      "crossed_tickers": [...], "unobserved_tickers": [...],
      "per_ticker": {t: {"base_high", "max", "gap_pct": (max−base_high)/base_high×100 소수2자리 | None(미관측), "ticks", "first_cross_at"}}}`
    - never-raise(실패 시 `{"status": "error", "date": iso}`).
E4. **방출 위치** — `scheduler.py` 무접촉 경로: `src/engine/log_metrics_collector.py::collect_daily_log_metrics` 가
    `metrics["vcp_breakout_events"]` 키 **하나**를 추가한다(레지스트리에서 `vcp_breakout` 을 찾아 E3 호출. 전략 부재 = `None`).
    이 함수는 20:05 1차 스냅샷·20:20 번들·21:30 완전판이 모두 부르므로 **WARNING 줄은 KST 하루 1회**
    (`KstDailyEmitCap`, 첫 호출 = 20:05)이고 `target_date == 오늘(KST)` 일 때만 찍는다. 과거 날짜 호출은 키만 채운다(no_watch).
    `[vcp_breakout_events] date=<iso> status=<ok|no_watch|error> crossed=<C>/<N> observed=<K> unobserved=<U> run_at=<HH:MM:SS> window=<HH:MM-HH:MM> partial=<0|1> crossed_tickers=<t,..|->`
    (no_watch 면 `status=no_watch` 까지만 — 「0」과 「모른다」를 가른다.)
    수집 실패는 그 키만 `None`, 나머지 metrics·리포트는 무영향(never-raise).
E5. **알려진 한계(문서에 적는다)** — **14:30 이후 재기동**(15:30~16:00 배포 창 포함)이면 부팅 prepare 가 D1 에 걸려 watch 가 안 생기고 그날 ③ 은 `status=no_watch` 다(① 줄은 아침에 이미 남아 있다). 창 안 재기동이면 부팅 prepare 와 600초 뒤 재준비가 watch 를 교체해 그 전 관측이 버려진다(`partial=1`, `run_at` = 마지막 교체 시각). 틱은 `risk.on_tick` 이 VCP `check_buy_signal` 을 부를 때만 보인다. 다른 전략이 보유·주문중·
    당일매도(L3)거나 자금 사전 가드(L4)에 걸린 종목은 그동안 틱이 기록되지 않는다 — 창 시작부터 막히면 `unobserved_tickers` 에
    남지만(09-23 대한항공 사례), 장중에 막히기 시작하면 `observed`(= 창 안 틱 최소 1개)로 세고 그 뒤 고가가 `max` 에 없다
    (거짓 음성 가능 — 끊긴 지점은 watch 엔트리 `last_tick_at`, 아래 「커밋 전 독립 검증 보강」). 창 안 재기동이면 `partial=1`.
E6. **추가 I/O 0** — KIS 호출·DB 쓰기·`await` 추가 없음(요약 수집도 메모리 읽기).

---

## 골든 (확장 전 HEAD 코드로 먼저 뜬다 — 차분 비교 금지)

cycle348 에서 차분 비교(「훅 있음 vs 훅 raise 스텁」)만으로는 두 쪽을 같이 바꾸는 돌연변이가 살아남았다.
그래서 **src 를 한 줄도 고치기 전에** HEAD 코드로 아래 결과를 뽑아 **리터럴(또는 커밋되는 fixture 파일)** 로 박는다.
확장 후 테스트는 그 리터럴과 비교한다.

- **G1 prepare** — 합성 유니버스(최소 5종목: 통과 2~3, 추세·베이스·pullback·거래량 수축 탈락 각 1, 박스 최고가 동률 1)를
  monkeypatch(`_scan_universe`·`get_recent_daily_normalized`·`get_atr`·master block·종목명)로 고정. 오전 시각(07:45)·저녁 시각(16:25)
  두 번 실행 → `_candidates` 전체 · `_scanned_tickers` · `_scan_stats`(`last_run_at` 제외) · `_funnel_steps`(단계명·생존·탈락·조건 문자열) ·
  `scanner.ticker_prev_close` 해당 키 · `_bought_today` 가 골든과 동일.
- **G2 check_buy_signal** — 후보 3종목 + 비후보 1종목, 시각 09:04:59 / 09:05:00 / 돌파 / 거래량 미달(래치) / 충족 / 추격 상한 초과 /
  14:30:00 / 14:30:01 을 섞은 스크립트 틱 시퀀스(freezegun + `tick_volume` 고정). 매 틱 반환 신호 목록 + 끝 상태
  (`_prev_price` · `_vol_latch`(armed_at 은 고정 시각) · `_bought_today` · `_scan_stats` · `_gate_emit_capped` · `state.buy_signals` ·
  `_position_setup`) 이 골든과 동일.
- (G3 — ② 보류로 폐기. `scheduler.py` 무접촉이라 캡처 경로 골든이 필요 없다.)

## 행위 테스트 (Red)

①: 거리 값 정확성(분모·부호·반올림) · `na` 분기 · 박스 최고가 날짜(동률이면 최신) · 오전 run 만 방출 · 저녁 run 방출 0 ·
요약 줄 형식·중앙값(홀·짝) · cap(같은 값 재준비 = 후보 줄 생략·요약 줄은 찍힘(→ D3 개정으로 폐기: 내용이 같으면 요약도 생략 — 끝의 「F3 인터페이스」), 값이 바뀌면 찍힘, KST 날짜 넘어가면 다시 찍힘) ·
헬퍼 raise 스텁에서 G1 동일 · 조기 반환 분기 `n=0`.
③: 창 경계(09:04:59 미관측·09:05:00 관측·14:30:00 관측·14:30:01 미관측) · 비후보 틱 무시 · 저녁 prepare 가 watch 보존 ·
오전 재준비가 watch 교체 · `first_cross_at` 최초 1회 · 날짜 넘어가면 no_watch · 요약 dict 구조 · 수집기 키 추가 ·
WARNING 1회/일(두 번 호출해도 1줄) · 과거 날짜 호출 = 줄 0 · 헬퍼 raise 스텁에서 G2 동일 · 전략 부재 = `None`.

## 가드·핀
- `vcp_breakout.py`·`log_metrics_collector.py` 를 sha/세그먼트로 핀하는 AST 가드는
  **값만** 재핀한다. 가드 논리 무접촉. 구조 가드가 붉어지면 느슨하게 하지 말고 의도를 확인해 team-leader 에 보고.
- `metrics` 키 집합을 핀하는 테스트가 있으면 새 키를 **기대 목록에 추가**한다(삭제·완화 금지).
- 8영역·`scheduler.py`·`data_load_tasks.py`·`task_loop_helper.py` 무접촉. `DEFAULT_PARAMS` 신규 키 0. `PARAM_RANGES`/`INT_PARAMS` 무접촉.

## 돌연변이 (최소 5종, 전부 KILL — 검증은 tester)
M1 훅이 `_prev_price` 를 쓰거나 조기 `return Signal.NONE` (매매 경로 오염) · M2 훅/①헬퍼의 자기 try 제거(예외 전파) ·
M3 거리 분모를 `base_high` 로 / 부호 반대 · M4 저녁 prepare 가 watch 교체 또는 후보 줄 방출(오전/저녁 혼동) ·
M5 cap 제거(재준비 중복 줄 · 요약 WARNING 2회) · M6 창 경계 `>` ↔ `>=` · M7 `_candidates` 엔트리에 키 추가 ·
M8 요약 WARNING 이 과거 날짜 호출에서 찍힘/cap 소비 · M9 `crossed` 판정 `>=`→`>` · M10 수집기 예외가 metrics 전체를 깨뜨림(never-raise 제거).

## 운영 영향 추정
하루 WARNING(tester 코드 기준 재추정) = 평상시 후보 줄 N(12~14) + 요약 1(07:57 재준비가 같으면 생략) + 하루 요약 1 ≈ **14~16줄** · 07:45~07:57 사이 일봉이 바뀌는 날 최대 ≈ 2N+3 · 후보 0 인 날 2줄 · 장중 재기동이면 후보 줄 N 재방출. KIS 호출 0 · DB 쓰기 0(기존 system_logs 경로).

## 문서
`src/engine/strategies/CLAUDE.md` VCP 절 · `src/engine/CLAUDE.md`(log_metrics_collector 서술이 있으면) ·
`docs/HARNESS_CHANGELOG.md` 상단 cycle349 · ② 보류와 원인은 `_workspace/00_URGENT_WORKLIST.md` 결정 대기 항목(메인 세션 몫). 스키마 무변경이라 DB 문서·루트 DB 표 무접촉.

---

## Red 확정 인터페이스 (tdd-engineer, 2026-09-24 — ①③ 만. ② 는 보류 — 이 절은 ② 를 다루지 않는다)

테스트 파일: `tests/unit/engine/strategies/test_cycle349_vcp_breakout_observe.py`(①③ 전략 · 골든 G1·G2) ·
`tests/unit/engine/test_cycle349_vcp_breakout_events_metrics.py`(③ 수집기).
골든 = `tests/unit/engine/strategies/fixtures/cycle349_golden.json`(`_meta` · `g1_morning` · `g1_evening` · `g2` — HEAD `2ef289b` 산출, 생성기는 리포 밖).
①③ 경로는 `scheduler.py` 를 건드리지 않는다(수집기는 `trading_scheduler` 를 **읽기만** 한다).

### 시계 규약 (freezegun 은 naive `now()` 와 `now(KST)` 를 9시간 어긋나게 준다)
- VCP 전략 안 **시각 판정**(D1 오전 판정·E2 창)과 **시각 문자열**(`run=` · watch `run_at` · `first_cross_at`) = naive
  `datetime.now()`(게이트 `check_buy_signal` 과 같은 시계). **날짜**(watch `date`·E2 날짜 비교) = `datetime.now(KST).date()`.
- ③ 수집기의 「오늘」 = `datetime.now(KST)`(aware).

### ① `VcpBreakoutStrategy` (`src/engine/strategies/vcp_breakout.py`)
- `__init__`: `self._breakout_distance_cap: KstDailyEmitCap`(전략 인스턴스 소유) · `self._breakout_watch: dict | None = None`.
- `_observe_breakout_distance(self, refs: dict[str, dict]) -> None`
  - `refs[ticker] = {"candles": <prev_idx 슬라이스 뒤 candles(= _detect_base 입력)>, "base": <_detect_base 결과 dict>}` —
    `self._candidates[ticker] = {...}` **직후** 참조만 담는다. `_candidates` 엔트리 키 추가 금지.
  - 호출 2곳, 둘 다 `try: … except Exception:` 자기 try: ① prepare 정상 끝(`VCP 준비 완료` INFO **뒤**) ② `if not tickers:` 조기 반환
    분기(`return` 앞, `refs={}`).
  - D1: `datetime.now().time() > _parse_time_hhmm(params["entry_end"])` 면 즉시 반환(줄 0 · watch 무접촉 · cap 무접촉).
  - 순서 = `_candidates` 삽입 순서. `base_high`/`prev_close` = `_candidates[t]`(= refs 와 동치), `base_low`/`base_len` = `base["low"]`/`base["length"]`,
    박스 = `candles[:base_len]` 안 `int(stck_hgpr) == base_high` 인 **최소 인덱스**.
  - 후보 줄(WARNING, cap 키 `(ticker, base_high, prev_close)` 하루 1회):
    `[vcp_breakout_distance] run=HH:MM:SS ticker=… base_high=%d prev_close=%d dist_pct=<%+.2f|na> box_high_date=<YYYYMMDD|na> box_high_ago=<int|na> base_low=%d base_len=%d`
  - 요약 줄(WARNING, cap 없음): `[vcp_breakout_distance_summary] run=HH:MM:SS n=<len(_candidates)> median_pct=<%.2f|na> within5=%d over10=%d tickers=<t1,t2,…|->`
    — **후보 0 이면 `tickers=-`**(③ `crossed_tickers=-` 와 같은 관례. 명세에 없던 결정).
  - 종목 단위 계산 실패(refs 엔트리 조회가 터짐 등) = 그 줄만 생략, 요약은 남는다.
  - 오전이면 끝에 watch 를 통째로 교체(E1).
- `_observe_breakout_tick(self, ticker: str, current_price: int) -> None` — `check_buy_signal` 본문 **두 번째 문장**(첫 문장 = 계좌 SOFT
  게이트 if)으로 `self._observe_breakout_tick(ticker, current_price)` 한 줄, 본문 1회. 본체 전체 try. watch 만 읽고 쓴다.
  watch 모양: `{"date": date, "run_at": "HH:MM:SS", "tickers": {t: {"base_high": int, "max": 0, "ticks": 0, "first_cross_at": None}}}`.
- `breakout_event_summary(self, target_date: date) -> dict` — 순수 읽기, never-raise.
  - `{"status": "no_watch", "date": iso}` / `{"status": "error", "date": iso}` / ok 11키
    `status·date·run_at·window("HH:MM-HH:MM", params 원문)·partial(run_at > entry_start)·candidates·observed·crossed·crossed_tickers·unobserved_tickers·per_ticker`.
  - `crossed_tickers`·`unobserved_tickers` 순서 = watch 삽입 순서. `per_ticker[t]` = `base_high·max·gap_pct(round(…,2) | None 미관측)·ticks·first_cross_at`.

### ③ 수집기 (`src/engine/log_metrics_collector.py`)
- `collect_daily_log_metrics` 반환 dict 끝(기존 9키 **뒤**)에 `"vcp_breakout_events"` 1키.
- 전략 조회 = 호출 시점 `from src.engine.scheduler import trading_scheduler` → `trading_scheduler.registry.get("vcp_breakout")`
  (테스트 대역은 `get`·`all` 둘 다 제공). 부재 = `None`. 조회·요약 예외 = 그 키만 `None`.
- WARNING 줄은 `target_date == datetime.now(KST).date()` 일 때만, 모듈 전역 `KstDailyEmitCap` 로 **KST 하루 1회**(이름 제안
  `_vcp_breakout_events_cap` — 테스트는 이름에 의존하지 않고 날짜를 달리해 격리한다). 과거 날짜 호출은 cap 을 소비하지 않는다.
  - ok: `[vcp_breakout_events] date=<iso> status=ok crossed=<C>/<N> observed=<K> unobserved=<U> run_at=<HH:MM:SS> window=<HH:MM-HH:MM> partial=<0|1> crossed_tickers=<t,…|->`
  - no_watch / error: `[vcp_breakout_events] date=<iso> status=<no_watch|error>` (거기서 끝).

### Red 판정 근거 (HEAD `2ef289b`, 2026-09-24 실측)
- 새 파일 2개 = 54건: **골든 4 초록**(G1 07:45 · G1 16:25 · G2 · fixture 출처), **Red 50**(38 + 12) — 사유는 전부 속성 부재
  (`_breakout_watch`·`_observe_breakout_distance`·`breakout_event_summary`·`_breakout_distance_cap`) · 줄 부재 · AST 호출 부재 · metrics 키 부재.
- **충족 가능성 검증**: 리포 밖 복사본에 `vcp_breakout.py`·`log_metrics_collector.py` 만 바꾼 참고 구현을 넣어 54/54 초록, ①③ 돌연변이 17종
  (M1~M7 + 추가 3) 전부 KILL. 리포 `src/` 무접촉.

## 영향 가드 목록 (①③ 만 — 고치지 않았다. Green/tester 가 값만 재핀. 근거 = ①③ 전용 참고 구현 복사본 실측 18건)

### A. `vcp_breakout.py` byte·sha 핀 — 값만 재핀 (10)
`test_cycle223_ast_donchian_exit_fix.py::test_g223_12_other_strategy_files_diff_zero` · `test_cycle274_ast_llm_gate.py::test_c15_1[vcp]` ·
`test_cycle276_ast_order_hook.py::test_c5_1[vcp]` · `test_cycle278_ast_catalog_guards.py::test_eight_areas_and_scheduler_and_strategy_base_untouched[vcp]` ·
`test_cycle282_ast_purity.py::test_h3_eight_areas_untouched[vcp]` · `test_cycle286_ast_scope.py::test_g1[vcp]` · `test_cycle287_ast_scope.py::test_s1[vcp]` ·
`test_cycle291_ast_scope.py::test_a1[vcp]` · `test_cycle293_ast_channel_resolver.py::test_a1[vcp]` · `test_cycle294_ast_stage3.py::test_a1[vcp]`

### B. `vcp_breakout.py` 매매 메서드 세그먼트 핀 — 값만 재핀 (4)
`test_cycle290_ast_scope.py::test_g290_2[check_buy_signal-vcp…]`·`[prepare-vcp…]` · `test_cycle297_ast_scope.py::test_g2_3b[check_buy_signal-vcp]`·`[prepare-vcp]`
— 「매매 메서드 byte 불변」 의미의 핀이다. 이 사이클은 의도적으로 두 메서드에 관측 훅을 넣으므로 재핀 근거 = 골든 G1·G2 초록 + 돌연변이 KILL.
가드 논리 무접촉.

### C. src 트리 digest (1)
`test_cycle287_ast_scope.py::test_s1b_whole_src_tree_is_byte_identical_except_the_three`(`_SRC_TREE_DIGEST`; 새 src 파일 0 이면 `_SRC_TREE_FILES` 그대로)

### D. metrics 키 순서 핀 — 기대 목록 **끝에** `"vcp_breakout_events"` 추가 (3)
`tests/unit/engine/test_cycle249_collect_metrics.py::test_collect_when_called_then_metric_keys_identical`(`EXPECTED_METRIC_KEYS`) ·
`tests/unit/engine/test_cycle259_log_metrics_collector.py::test_l3_metric_key_order_is_byte_identical` · `::test_l3b_reexported_entrypoint_returns_same_shape`

### E. 영향 인덱스 (1 — 새 테스트 파일 미등록, build_index 보류 지시)
`tests/unit/deploy/test_cycle318_impact_index_freshness.py::test_backend_index_is_fresh` — 지금 실제 리포에서 붉은 기존 테스트는 이것 하나다.

### F. 참고
- `log_metrics_collector.py` 를 sha 로 핀하는 가드는 참고 구현에서 붉어지지 않았다. `daily_emit_cap.py` 는 무변경(기존 `KstDailyEmitCap` 사용).
- 지금 초록이지만 밟기 쉬운 것: `test_cycle233_ast_account_risk.py`(`GATE_FIRST_FILES` — VCP `check_buy_signal` 첫 문장 = 계좌 게이트, 훅은 두 번째) ·
  `test_cycle287_ast_scope.py::test_s1b` 의 `_SRC_TREE_FILES`(새 `src/**/*.py` 파일을 만들면 갱신 대상 — 이 설계는 새 파일 0).


## 검증 후 보강 (team-leader, tester 사후 검증 반영)
- tester 결과 = 전체 11,243 통과·실패 0 · DEBUG 10,874 통과·실패 0 · 골든 독립 재생성 바이트 동일 · 돌연변이 29종 중 행위 KILL 24 · 동치 2 · 공백 2(M9a·Y4) · 순서 의존 1(M8b).
- **F1(M9a)** 요약 `crossed` 동률 경계 — `max == base_high` 인 틱 하나만 → `crossed=1`·`crossed_tickers=[t]`·`gap_pct=0.0` 회귀 추가(게이트가 `prev < base_high <= current` 라 동률도 돌파다).
- **Y4** `partial` 경계 — `run_at == entry_start`(정확히 09:05:00) 이면 `partial=False` 회귀 추가.
- **F2(M8b)** 수집기 테스트 격리 — E 파일 fixture 가 `log_metrics_collector` 모듈 전역의 `KstDailyEmitCap` 인스턴스를 **타입으로** 찾아 테스트마다 새 인스턴스로 교체(이름 비의존). 그 뒤 M8b(과거 날짜 호출이 `mark_emitted` 선소비)가 파일 통째 실행에서도 죽어야 한다.
- **F3** D3 개정(위) — 요약 줄 「직전과 같으면 생략」. 회귀: ① 같은 목록 재준비 2회 → 요약 1줄 ② 후보 0 재준비 60회 → 요약 1줄 ③ A→B→A → 3줄 ④ KST 날짜가 바뀌면 같은 내용도 다시 찍힌다 ⑤ 생략돼도 watch 는 매번 교체된다(③ run_at = 마지막 오전 prepare).

## F3 인터페이스 (tdd-engineer, 2026-09-24 — D3 개정 구현 계약)

- **새 속성** — `__init__` 에서 `self._breakout_watch` 바로 다음 줄에 `self._breakout_summary_last: tuple | None = None`.
  값 = `(kst_date, content_key)`.
  - `kst_date` = `datetime.now(KST).date()` — watch `date` 와 같은 시계(「시계 규약」).
  - `content_key` = `(n, median_str, within5, over10, tickers_str)` — **줄에 찍히는 값 그대로**다. `median_str` 은 `"%.2f"` 문자열 또는 `"na"`,
    `tickers_str` 은 `"t1,t2,…"` 또는 `"-"`. float 원값이 아니라 포맷된 문자열로 비교해 「줄이 같으면 생략」과 정확히 맞춘다. `run=` 은 키에 넣지 않는다.
- **자리** — `_observe_breakout_distance` 안, D1 조기 반환 **뒤**, 요약 줄을 찍던 기존 `try/except Exception` 블록 안. 저녁 prepare 는 비교도 갱신도 하지 않는다.
- **동작** — `(kst_date, content_key) == self._breakout_summary_last` 면 요약 WARNING **만** 생략한다. 다르면 찍고, **찍은 뒤에**
  `self._breakout_summary_last = (kst_date, content_key)` (peek→로그→mark, cycle226 D-3 — 로그 호출이 터지면 기록하지 않아 다음 run 이 다시 찍는다).
- **생략해도 그대로인 것** — 후보 줄(D4 `_breakout_distance_cap`, 별개) · 끝의 watch 통째 교체(E1 — 생략 분기에서 `return` 금지) ·
  조기 반환 분기(`refs={}`)도 같은 규칙(후보 0 재준비 60회 = 요약 1줄, watch `run_at` = 마지막 호출).
- **「직전」 1개와만 비교** — 집합·하루 전체 dedupe 금지(A→B→A = 3줄). 그래서 `KstDailyEmitCap` 을 쓰지 않는다(그건 하루 집합이다).
  D4 의 「요약 줄은 cap 하지 않는다」 = `KstDailyEmitCap` 을 쓰지 않는다는 뜻이고 이 내용 비교와 충돌하지 않는다.
- **리셋 배선 없음** — 날짜가 키에 들어 있어 `_reset_daily_state` 연결이 필요 없다. 날짜가 바뀌면 같은 내용도 그날 첫 줄로 찍힌다.
- **영향 가드** — `vcp_breakout.py` 가 다시 바뀌므로 「영향 가드 목록」 A(10)·C(1) 값 재핀이 한 번 더 필요하다. 바뀌는 곳은 `__init__` 한 줄과
  `_observe_breakout_distance` 본체뿐이라 B(`prepare`·`check_buy_signal` 세그먼트)는 그대로다(참고 구현 기준).

### 회귀 ↔ 요구 (`test_cycle349_vcp_breakout_observe.py`)
| 요구 | 테스트 | 현 구현(F3 전) |
|---|---|---|
| ① 같은 목록 오전 재준비 2회 → 요약 1줄 | `test_f3_same_content_morning_reprepare_emits_summary_once` | 붉음 |
| ② 후보 0 오전 재준비 60회 → 요약 1줄 (조기 반환 · 전원 탈락 두 길) | `test_f3_zero_candidates_reprepare_60_times_emits_summary_once[early_return / all_excluded]` | 붉음 |
| ③ A→B→A → 3줄 | `test_f3_a_b_a_emits_three_summaries` | 초록(과잉 생략 방어) |
| ④ 다음 KST 날짜 같은 내용 → 다시 찍힘 | `test_f3_next_kst_day_same_content_emits_again` | 초록(날짜 없는 키 방어) |
| ⑤ 생략돼도 watch 교체 | `test_f3_suppressed_summary_still_replaces_watch` (+ ② 의 watch 단언) | 붉음(전제 = 요약 생략) |
| ⑥ 저녁 prepare 0줄·watch 무접촉(목록이 바뀌어도) | `test_f3_evening_prepare_changed_content_emits_nothing_and_keeps_watch` | 초록 |
| 키 필드별(median·within5·over10·tickers 중 하나만 달라도 찍힘) | `test_f3_content_key_covers_each_field[4]` | 초록(좁은 키 방어) |

F3 때문에 고친 기존 테스트 2개: `test_d4_reprepare_same_values_suppresses_candidate_lines`(요약 2줄 단언 삭제 → 후보 줄만 잰다, 요약은 F3 몫) ·
`test_d1_window_boundary_prepare`(두 번째 prepare 를 후보 하나 뺀 목록으로 — 같은 목록이면 F3 생략이 경계 판정과 섞인다).

### 충족 가능성·돌연변이 (리포 밖 복사본 실측, 리포 `src/` 무접촉)
- 위 계약 그대로의 참고 구현 → 두 파일 68/68 초록.
- F3 돌연변이 5종 전부 KILL: 하루 전체 set dedupe(③) · 키에 날짜 없음(④) · 키 = tickers 만(키 3케이스) · 생략 시 watch 교체 전 `return`(①②⑤ + `test_e1_*`·`test_d4_*`) · D1 제거(⑥ + 기존 저녁 2건).

## 커밋 전 독립 검증 보강 (tdd-engineer, 2026-09-24 — 적대 리뷰 + 반박 2표에서 확정된 지적)

1. **[major] 골든 범위** — `run_g1`/`run_g2` 가 새 인스턴스에서만 돌아, ① 헬퍼가 `prepare` 가 비우지 않는 교차일 상태
   (`_cooldown_until`·`_position_setup`·`_prev_price`·`_vol_latch`)를 덮어쓰거나 틱 훅이 `_candidates` 를 오염시켜도 초록이었다.
   → `seed_cross_day_state` 가 prepare 전에 채운다: 쿨다운 후보 `T_K`(900013, T_A 와 같은 일봉 — 골든 전용 유니버스에만 추가, 기존
   세 후보의 경로를 지키려면 후보가 하나 더 필요했다) `_cooldown_until` D+3 · 비후보 보유 `T_HELD`(900020) `_position_setup` +
   `state.positions` · 후보 T_B `_prev_price` 20,800(돌파선 20,754 위) · 비후보 T_D 전일 무장 `_vol_latch`. G2 틱 2개 추가 —
   09:19 T_B 20,760(전날 가격도 위라 edge 아님) · 09:40 T_K 10,320(쿨다운). G1 스냅샷에 4필드, G2 끝 상태에 `cooldown_until`·
   `candidates`. 골든은 HEAD `2ef289b` 의 `git archive` 트리에서 다시 떴다(`_meta.revision=2`, 생성기 리포 밖 `gen_c349_golden_v2.py`).
   적용 범위(지나지 않는 게이트 = 예산·래치 해제·보유/주문중/당일매도·`buy_disabled`·최대 보유·일일 손실)는 테스트 파일 머리말.
2. **observed 의미** — 틱 1개만 받아도 observed 다. watch 엔트리·요약 `per_ticker` 에 `first_tick_at`/`last_tick_at`(게이트와 같은
   naive 시계). E5 서술 정정(위).
3. **일일 WARNING cap 시각** — 수집기가 시각 조건 없이 첫 호출에서 cap 을 소비해 낮의 번들 GET·`POST /api/log-reports/run` 이
   그날 결과 줄을 중간값으로 만들 수 있었다. → WARNING·cap 소비는 `target_date == 오늘` ∧ VCP 매수 창(`params["entry_end"]`,
   실패 시 14:30)이 **닫힌 뒤**(`now > entry_end`)에만. 키 값에 `final`(1 = 창 닫힌 뒤·지난 날짜, 0 = 중간값).
4. **과거 날짜** — watch 날짜와 다른 지난 `target_date` 는 `status=not_retained`(이 프로세스는 그날 관측 여부를 모른다 — 그날
   `daily_log_reports.metrics` 가 정본). `no_watch` 는 오늘(또는 그 뒤) 날짜에만.
5. 문서·nit — D6 의 「헬퍼 본체 전체 try」는 실제 구조와 다르다: 틱 훅·요약은 본체 전체 try, ① 헬퍼는 종목 단위·요약 줄 try +
   호출부 2곳의 자기 try(각주 ⑥ 정정). 수집 실패 DEBUG 접두 `[vcp_breakout_events_error]`. `box_high_ago` 1부터(전일 = 1) ↔
   cycle347 `high_age` 0부터. 후보 0 인 날의 `partial=1` 은 재준비 흔적. `snapshot_at` 사실은 `src/db/CLAUDE.md` 한 곳 +
   `src/db/strategy_funnel.py` docstring 정정.

돌연변이(리포 밖 복사본, 두 파일 77건 기준) 17종 전부 KILL — MA(훅 → `_candidates` 키) · MB(헬퍼 → `_cooldown_until` clear, G2
09:40 T_K NONE→BUY) · MC(`_position_setup` clear) · MI(`_prev_price`+`_vol_latch` clear, G2 09:19 T_B NONE→BUY) · MI-a/MI-b(각각 단독) ·
M7 · `last_tick_at` 첫 틱만 · `first_tick_at` 덮어쓰기 · 창 게이트 제거 · 경계 `>=` · 리터럴 14:30 · 창 전 cap 소비 · `final` 상수 1 ·
`not_retained` 제거 · `<`→`<=` · 실패 흔적이 데이터 마커 재사용.

