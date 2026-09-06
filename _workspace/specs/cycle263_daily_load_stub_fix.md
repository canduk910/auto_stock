# cycle263 명세 — 일봉 적재 껍데기 봉 결함 시정 (라) = (가) + (다)

> 승인 = 2026-09-06 사용자 결정 카드 ④ "승인"(`scanner.py` 8영역 접촉 포함).
> 자문 정본 = `_workspace/consult/2026-09-06_daily_load_stub_bar.md` (본문 + 부록 A).
> 선행 실행 = 09-06 15:16 금요일 일봉 보정 완료(963종목·6,916행, 스텁 1,015→120).

---

## 1. 결함 (실측 확증)

`_stock_master_daily_load_once` 의 멱등 규칙은 `latest >= today` 면 skip 이다
(`scanner.py:2184`). 그런데 이 task 의 **기동 직후 1회 실행**(`immediate_first_run=True`,
`initial_delay_secs=240`, `data_load_tasks.py:96-111`)이 매일 아침 07:56 에 장 시작 전
KIS 로부터 **오늘 날짜 껍데기 봉**(O=H=L=C=전일종가, 거래량 0)을 받아 먼저 쓴다.
⇒ `max_bas_dd == today` ⇒ **그날 16:00 실행이 전 종목 skip.**

```
09-03 07:57  fetched=982  skipped_fresh=0      09-03 16:00  fetched=0  skipped_fresh=982
09-04 07:57  fetched=1015 skipped_fresh=0      09-04 16:04  fetched=1  skipped_fresh=1015
```

### 오염 경로 — "오늘 스텁" 이 아니라 "어제 스텁"이다 (자문의 정정)

전략 7종은 `prev_idx` 가드로 **오늘 봉을 이미 잘라낸다.** 진짜 손상은 `_boot` 의
`prepare()` 가 daily load 보다 **4분 먼저** 돌기 때문이다(07:51 vs 07:56,
`scheduler.py:555~680` — `await self._boot()` 뒤에야 `create_task`). 그 시점 테이블
헤드는 **어제 날짜 껍데기**이고 `bas_dd ≠ today` 라 가드를 그대로 통과해 "전일봉" 으로
소비된다.

그리고 이 손상을 매일 지워온 것은 설계가 아니라 **우연**이다 —
`evening_funnel_capture` 의 immediate run(boot+600s)이 08:02 에 전 전략을 다시
prepare 한다. daily load 가 360초를 넘기면 그 우연이 깨진다.

### 크기 (같은 아침 두 prepare 의 로그 실측)

| 전략 | 오염 상태 | 보정 후 |
|---|---|---|
| LTV (09-03) | 10/90 | 90/90 |
| LTV (09-04) | 5/32 | 32/32 |
| donchian | 1/111 | 4/111 |
| BFB | 42/595 | 25/596 |
| kojiro | 32/662 | 14/663 |

BFB·kojiro 는 오염 쪽이 **더 많다** = 거짓 후보. donchian 은 오염 상태에서 신고가·거래대금
게이트가 **수학적으로 통과 불가**다(P0-1 계열 구조적 차단).

### 상시 손상 (2차 prepare 로도 안 지워짐)

`stock_master_daily.get_atr()` 에는 오늘봉 가드가 **없다** ⇒ VCP ATR 평균 **6.3% 과소**
(중앙값 6.3%, 최악 29.3%, 1,805종목 중 272종목이 10%+). VCP 의 ±10% 교차검증 문턱
**아래**라 `[vcp_atr_mismatch]` 가 3개월간 한 번도 울리지 않았다.
⇒ **VCP/BFB 터틀 sizing 전환을 켜면 전 유닛이 6.7% 과대**가 된다(D-8 — 이 시정 D+1 이후로).

---

## 2. 시정 = (라) = (가) + (다)

### (가) 신선도 게이트 — `data_load_tasks.py`, **8영역 밖**

`stock_master_daily_load_task_loop` 의 `run_periodic_task_loop` 호출에
`immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS`(20.0) 를 추가하고
`:110` 의 "미적용" 주석을 정정한다.

**수렴 추적** — D0 아침 immediate 가 마지막 껍데기를 쓴다 → D1 아침은 마커 15.9h 로
skip(껍데기 생성 주체 소멸) → D1 16:00 은 `latest=D0 < D1` 이라 fetch 하는데 **16:00 의
KIS 오늘봉은 껍데기가 아니라 확정 실봉**이다 → D2 아침 prepare 부터 헤드가 실봉.

**메커니즘은 이미 프로덕션 검증됨** — `system_config` 실측으로 basics/master/financial
3 task 의 `task_last_success_*` 마커가 D-1 16:2x~16:4x 로 살아 있고 익일 07:55
(15.5h < 20h)에 실제로 skip 중이다. `task_last_success_stock_master_daily_load` 만 부재
(게이트 미적용이라 쓴 적이 없다).

사이클193 이 daily_load 만 게이트를 뺀 이유가 주석대로 "`max_bas_dd` 멱등을 믿어서" 인데
**지금 깨진 것이 정확히 그 멱등**이다 ⇒ 게이트 투입은 사이클193 의 전제를 되살리는 방향.

### (다) 오늘봉 시각 필터 — `scanner.py:2236~2240`, **8영역(승인 완료)**

`fetched += 1` **뒤**, `upsert_batch` **앞**. 그 자리가 유일하게 안전하다 —
두 fetch 분기(`fetch_daily_candles` / `fetch_daily_candles_backfill`)의 합류점이고
`failed`/`fetched` 카운터 의미가 보존된다.

**규칙** = 함수 진입 시각이 **15:40 KST 이전**이면 `bas_dd == today` 인 캔들을 폐기한다.
예외는 **fail-open**(전량 upsert 유지 — fail-closed 는 P0-1 방향).

### 왜 데이터 기준(거래량 0 ∧ OHLC 평탄)이면 안 되는가 — 반증 2건

1. **장중 재시작이 만드는 부분봉은 거래량 > 0 · 비평탄**이라 데이터 기준이 확정봉인 척
   통과시킨다. 껍데기보다 **나쁘다** — 평탄하지 않아 눈에 안 띈다.
2. 거래정지 종목의 **진짜 평탄 확정봉**을 16:00 에 죽여 그 날짜 행을 영영 못 갖게 한다.

시각 기준은 둘 다 자동 처리한다. 그리고 진짜 무거래봉(하루 1~8건)을 **정의상 100% 보존**한다.

### (가) 단독이 아닌 이유 = 낮 재배포 구멍

마커 D-1 16:0x + 20h = D 12:0x 만료 ⇒ 12:0x~15:30 재시작이면 immediate 가 다시 떠서
부분봉을 확정봉처럼 박고 그날 16:00 이 skip 된다. 빈도 실측 = git main full 모드 커밋 중
12:00~15:30 이 **최근 30일 5건**(13:25·13:45·13:49·14:01·14:30) = 주 1회 이상.
(다)가 이걸 닫는다(13:04 < 15:40 → 오늘봉 폐기 → 16:00 정상 fetch).

### 자기 치유 (실패 모드 8케이스)

마커는 **성공 시에만** 갱신되므로 16:00 이 실패하면 다음 아침 immediate 가 자동 부활한다
⇒ 사이클106 lifecycle race 안전망이 그대로 보존된다. 16:00 raise / 프로세스 다운 /
하루 종일 다운 / 주말 / 공휴일 / 12~15:30 재배포 / 마커 조회 실패 전부 자기 치유.

---

## 3. 부작용 — 실측 확인 완료

| 소비처 | 영향 |
|---|---|
| `count_by_ticker` 임계(백필 50 / VCP 120) | **0** — 껍데기는 추가 행이 아니라 같은 날짜 행의 값이 틀린 것이라 날짜 집합이 동일 |
| `purge_old_rows` · `count_all()` | **0** |
| `get_recent_daily_normalized` 신선도 게이트(`DAILY_STALENESS_DAYS=4`) | **유일한 실질 위험.** 2026-02 이후 144회 거래일 전이 중 간격 ≥5 는 1회(02-19 설, 간격 6). 다음은 추석. 발화 시 1,000종목 250~300초 지연이나 폴백 데이터가 더 정확하다 ⇒ **이번 사이클 무변경**(D-4) |
| UI `last_daily_load_at` | 낮 동안 어제 날짜로 보인다 — **수용**(의미상 정확, D-7) |
| `market_regime` · VB RS/RSI 훅 | 증상 소멸(개선). 가드 자체는 별건(D-6) |

---

## 4. 관측

- **의미 반전** — `skipped_fresh` 가 16:00 에서 ~1,000 → ~0 이 된다.
  **배포 전후 grep 합산 금지.**
- 신규 마커 `[daily_load_today_bar_filter]` — **실행당 1행** INFO(종목당 로그 금지).
- **D+1 핵심 성공 서명** = 07:51 과 08:02 **두 prepare 카운트가 수렴**(특히 LTV 가
  07:51 에 이미 N/N).
- ⚠️ 자문 본문 §6-5 의 `[prepare_db_fallback] reason=stale` 은 `logger.debug` 라
  `system_logs`(INFO+)에 **애초에 안 들어간다** — 체크리스트에서 컨테이너 로그 기준으로
  바꾸거나 뺀다(자문 원안 정정 2).

---

## 5. 배포와 되돌리기

- 일요일 장외 배포 가능(주말은 스케줄러가 월 07:45 까지 대기, D6 무관). 모드 **full**.
- 효과 절반은 **월 16:00** 부터, 아침 prepare 정상화는 **화 07:51** 부터.
- 롤백 = 다음 커밋으로 원복 + 재시작(즉시 반영).

---

## 6. 검증 (자문 §A-6)

1. 16:00 성공 시 `set_task_last_success("stock_master_daily_load", ...)` 가 실제로 쓰이고,
   `once()` 가 raise 하면 **안 쓰이는지**(안전망 부활 조건).
2. 마커 경계 3건 — 15.9h → skip / 39.9h(16:00 실패 다음날) → 실행 / 63.9h(주말) → 실행.
3. 마커 조회 예외 → immediate 실행(fail-open) + (다)가 오늘봉을 버려 무해.
4. **부분봉 시나리오** — `now=13:04` immediate + KIS 가 거래량>0 비평탄 오늘봉 반환
   → DB 미기록, 같은 날 16:00 이 `latest=D-1` 을 보고 fetch (구멍 폐쇄 회귀 가드).
5. **수렴 3일 시뮬** — D0 껍데기 → D1 전환 → D2 정상 (freezegun, 07:56/16:00 × 3일).

---

## 7. 이 사이클에서 하지 않는 것 (별건)

| # | 항목 |
|---|---|
| D-5 | VB `k_period=15` vs 하드코딩 `min_required=22` ⇒ **VB 는 DB 일봉을 한 번도 쓴 적이 없다**(매 prepare 종목당 KIS 1회). 고치면 VB 가 처음 DB 경로에 들어오므로 별도 검증 필요 |
| D-6 | `market_regime` · VB RS/RSI 훅의 오늘봉 가드 부재 |
| D-9 | `TIME_STOCK_MASTER_DAILY_LOAD` 16:00 → **18:10**(시간외 단일가 마감 후). 사용자의 "밤에 한 번" 취지에 가장 근접. 이 시정 D+1 확인 후 |
| D-11 | 23:00/05:00 이동은 **구조적 불가** — task loop 이 `while scheduler._running` 인데 `scheduler.py:1035` 가 20:10 정산 직후 `_running=False`. 하려면 task 를 uvicorn lifespan 으로 빼는 재설계 선행 |
| D-12 | 락 게이트를 안 타는 `get_recent_daily` 직접 호출 3곳(`get_atr`·`market_regime`·VB RS/RSI) |
| — | **액면분할 미조정 26,844행** — KIS 는 소급 재조정하지만(210980 실증: 4,445×(1−0.3196)=3,024≈3,054) T-7 창이 회수 못 해 락 종목 271개 중 **242종목 26,844행**이 미조정. 실제 방어는 prepare 시점 락 게이트라 적재 빈도와 독립 ⇒ 아침 실행 폐지와 무관 |
