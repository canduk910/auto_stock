# cycle414 전략별 진행상황 화면 — 패널 명세 (domain-expert)

- 작성: 2026-10-09 (domain-expert) · 기준 = 브랜치 `feat/strategy-monitors`(main `1b3c95a1`)
- 사용자 요청(10-09): 「대시보드에 전략의 진행상황을 확인할 수 있게 다양한 내용들을 조회해줘. 가능하면 시각정보를 포함해서.」 → 선택 「각 전략별 내용을 각 전략의 대시보드에서 자세히. 고지로를 참고해서 보강」 + 「대시보드 요약 + 전략 화면 상세」
- 해석: **요약** = 대시보드 「전체」 탭의 전략 요약표 · **상세** = 대시보드의 각 전략 탭 패널(KojiroMonitor 와 같은 틀)
- 이 문서는 명세만 담는다. 코드 변경 0. 매매 행위 변경 0(읽기 전용 화면 + 읽기 전용 라우트 1개).

---

## 0. 한 줄 요약

트레이더가 장중에 묻는 질문은 넷이다 — **① 지금 이 전략이 살 수 있는 상태인가 ② 오늘 후보가 몇이고 어디서 걸러졌나 ③ 후보가 매수선까지 얼마 남았나, 왜 안 샀나 ④ 들고 있는 것은 어디서 잘리나**. 모든 전략 패널을 이 네 질문 순서의 같은 틀(7칸)로 그리고, 화면의 문턱 숫자는 전부 `params`(운영 DB 값)와 엔진이 남긴 단계 이름에서 읽는다. 엔진 메모리에만 있는 값(ETF 깔때기 중간 수·보유 방어선 구성·래치·오늘 거르기 사유·준비 기준일)은 **새 읽기 전용 라우트 `GET /api/strategies/monitor` 한 개**로 연다(`src/routes/strategies.py`, 새 `.py` 파일 0, 전략 파일 0줄).

---

## 1. 트레이더 시각

### 1.1 시장 가설이 아니라 「운영 가설」

이 화면은 매매 규칙을 바꾸지 않는다. 대신 「전략이 규칙대로 돌고 있다」는 가설을 장중에 눈으로 검증하게 한다. 지난 두 달의 사고 대부분이 **「왜 안 사지?」를 결함으로 오진**하거나(BFB `entry_end` 09:04, 돈키언 `buy_paused`), **반대로 결함을 「시장이 안 줬다」로 넘긴** 경우였다(VCP 체결 0 = 돌파 기준선 결함). 화면이 둘을 가르려면 다음이 보여야 한다.

| 질문 | 트레이더 말 | 화면이 답하는 값 |
|---|---|---|
| ① 살 수 있나 | 「오늘 이 전략 총 쏠 수 있어?」 | 상태 배지(실매매·멈춤·섀도·꺼짐) · 진입창 열림 · 시장 유닛 · 예산 · 보유 한도 |
| ② 어디서 걸렸나 | 「후보가 왜 0이야?」 | 깔때기 — **처음 0 이 되는 단계 = 병목** + 14일 추이 |
| ③ 얼마 남았나 · 왜 안 샀나 | 「돌파선까지 몇 %? 거래량은?」 | 후보표의 거리 막대 · 거래량 게이지 · 종목별 상태(엔진 거름 순서 그대로) · 오늘 거르기 사유 분포 |
| ④ 어디서 잘리나 | 「손절까지 여유 몇 %? 언제 시간청산?」 | 보유 사다리(손절선—매수가—현재가—고점) · 실효 손절선까지 거리 · 시간·15:20 판정 카운트다운 |

### 1.2 화면이 지켜야 할 원칙 다섯

1. **틀린 숫자는 빈 칸보다 나쁘다**(`position_exit_lines.py` 머리말 원칙을 그대로 따른다). 엔진이 실제로 쓰는 선을 모르면 `—` 로 둔다. 화면이 엔진 산식을 흉내 내서 손절선을 계산하지 않는다 — 손절선은 엔진 값(`get_effective_stop_price` → `/api/balance/exit-lines` `stop_price`)이 정본이고, 구성 선은 라우트가 엔진 함수로 계산한 값만 쓴다.
2. **문턱 숫자는 `params` 에서 읽는다.** 운영 DB 와 코드 기본값이 39키 넘게 다르다(메모리 실측표). 화면 문자열에 `3%`·`4.5%`·`−7%` 같은 숫자를 박지 않는다. 깔때기 단계 이름은 엔진의 `step_name`·`step_conditions` 를 쓴다.
3. **엔진의 거름 순서를 그대로 비춘다.** 후보 한 종목의 상태 배지는 「엔진이 그 종목을 거르는 첫 관문」이다(전략별 순서 = §4). 순서를 바꾸면 「멈춤인데 갭 스킵으로 보임」 같은 오귀인이 생긴다.
4. **「0건」과 「모름」을 가른다.** 엔진이 사유를 남기지 않는 전략·시간(멈춤 중, 재시작 직후, 사유 기록이 없는 전략)은 「기록 없음」으로 쓰고 0 으로 쓰지 않는다.
5. **기준일을 밝힌다.** 21:00 저녁 미리보기 뒤의 후보는 「다음 거래일 잠정 후보」다(20:30 일봉은 잠정 — 다음 날 아침 부팅이 확정한다). 후보 목록 머리에 기준일·준비 단계·완료 시각을 붙인다.

### 1.3 위험 시나리오 (화면이 사람을 속이는 경우)

| 상황 | 화면이 보여 줄 수 있는 거짓 | 막는 방법 |
|---|---|---|
| 신규 매수 멈춤(`buy_paused`) 중 | 엔진은 멈춤 관문에서 바로 돌아가 갭·붕괴·묶음 사유를 남기지 않는다 → 「거르기 사유 0건」이 「후보가 다 좋다」로 읽힌다 | 주 배지 「멈춤」 + 회색 보조 「풀리면: ○○」(화면 추정임을 밝힘) · 사유 분포 칸은 「멈춤 중 — 엔진 기록 없음」 |
| 멈춤 + 섀도 동시 | 섀도 기록(`[shadow_buy]`)도 멈춤 관문 **뒤**라 안 남는다 | 같은 문구. 섀도 기록 0 을 「섀도가 고장」으로 보이지 않게 |
| 전략 꺼짐(`enabled=false`) + 보유 남음 | 끈 전략의 보유분은 손절·트레일링·15:20 청산이 **전부 멈춘다**(루트 CLAUDE.md 금기) | 빨강 경고 칩 「꺼짐 + 보유 n — 손절 정지」 |
| 비중 0 + 켜짐 + 섀도 아님 | 매수 신호가 900초 「투자금 부족」으로 오귀인된다(CLAUDE.md shadow 절) | 보조 칩 「예산 0」 |
| 백엔드 재시작 직후 | 오늘 사유·래치·섀도 기록이 메모리에서 지워져 0 으로 보인다 | 준비 시각(`prepare.started_at`)을 머리에 표시, 사유 칸에 「hh:mm 재준비 이후」 |
| 후보가 시세 미구독 | 평가 자체가 없는데 「대기」로 보인다 | 상태 배지 최우선 「시세 없음」(구독 목록·마지막 틱 나이) |
| 보유 종목이 후보에서 빠짐 | 후보표 ATR 로 방어선을 계산하면 `-` 로 비거나 틀린다(KojiroMonitor 326-327 현행 결함) | 보유 방어선은 exit-lines `entry_atr`·`stop_price` 와 라우트 holdings 만 쓴다 |

---

## 2. 공통 규약 (모든 전략 패널)

### 2.1 패널 틀 — 7칸, KojiroMonitor 순서를 일반화

| 칸 | 이름(화면 제목) | 내용 | KojiroMonitor 대응 |
|---|---|---|---|
| ① | 상태 | 상태 배지 + 보조 칩 + 비중·예산 + 시장 유닛 + 기준일 | 1. 상태 배너 |
| ② | 오늘의 시간표 | 07:00~21:30 가로 띠 위에 준비·진입창·15:20 판정·저녁 미리보기, 「지금」 세로선 | (새로 둠) |
| ③ | 후보 깔때기 | 단계별 생존 수 막대 + 병목 표시 + 14일 최종 후보 작은 선 그래프 | 3. 유니버스 깔때기 |
| ④ | 후보 종목 | 후보표(상태·현재가·매수선·거리 막대·전략 고유 칸) | 4. 후보 종목 그리드 |
| ⑤ | 오늘 거르기 사유 | 사유별 종목 수 가로 막대(엔진 기록 기준) | (새로 둠) |
| ⑥ | 진입 기록 | 오늘 매수 신호 + 섀도 기록 | 5. 진입 이벤트 |
| ⑦ | 보유 방어선 | 보유 종목별 사다리 막대 + 실효 손절선 거리 + 시간·15:20 카운트다운 | 6. 보유 종목 방어선 |

전략 고유 칸(kojiro 「대순환 스테이지」 등)은 ③ 앞에 둔다. 가벼운 패널(VB·momentum·LTV)은 ①②③⑥만 둔다(§4.6~4.8).

**배치 권고**: 전략 탭을 고르면 상세 패널을 `Dashboard.tsx` 의 `ScanMonitor`/`OrderMonitor` 2열 그리드 **위에 전폭**으로 그린다(후보표가 10칸 안팎이라 반폭이면 가로 스크롤만 생긴다). `ScanMonitor` 는 활성 보드·구독 요약·모멘텀 목록·VB/LTV 보드별 목표가표 같은 공용 칸만 남긴다. 「전체」 탭은 같은 자리에 요약표(§5)를 그린다. — 배치는 팀장 판단으로 바꿀 수 있다. 바꾸면 `ScanMonitor.kojiro.test.tsx` 등 기존 테스트의 렌더 위치 단언을 함께 고친다.

### 2.2 상태 배지 — 판정표

입력 = `/api/trading/status` 의 `strategies.<id>` (`enabled`·`weight`·`params.buy_paused`·`params.shadow_mode`·`buy_disabled`·`positions`·`total_investment`). 엔진과 같게 **`=== true` 일 때만** 켜짐으로 본다(`strategy_base.py` `_buy_paused_blocked`·`shadow_mode_on` 의 `is True`).

**주 배지(하나만)** — 위에서 처음 맞는 것:

| 순 | 조건 | 배지 문구 | 색 |
|---|---|---|---|
| 1 | `enabled === false` | 꺼짐 | 회색 |
| 2 | `params.buy_paused === true` | 신규 매수 멈춤 · 청산은 작동 | 주황 |
| 3 | `params.shadow_mode === true` | 섀도 · 주문 없이 기록만 | 보라 |
| 4 | 그 밖 | 실매매 | 초록 |

**보조 칩(여러 개 가능)**:

| 조건 | 칩 문구 | 색 | 근거 |
|---|---|---|---|
| `enabled === false` ∧ `positions > 0` | 꺼짐 + 보유 n — 손절 정지 | 빨강(굵게) | 루트 CLAUDE.md 「보유 포지션이 있는 전략을 끄지 않는다」 |
| `buy_paused === true` ∧ `shadow_mode === true` | 섀도 기록도 멈춤 | 회색 | 멈춤 관문(`_account_soft_gate_blocked` 둘째 문장)이 섀도 관문(`return Signal.BUY` 바로 앞)보다 먼저 돈다 |
| `buy_paused` 가 있는데 불리언이 아님(`"true"`·`1` 등) | 멈춤 설정 모양 오류 — 엔진은 「멈추지 않음」으로 읽음 | 빨강 | `_emit_buy_paused_config` WARNING 과 같은 판정 |
| `shadow_mode` 가 불리언이 아님 | 섀도 설정 모양 오류 — 엔진은 「실매매」로 읽음 | 빨강 | `_emit_shadow_mode_config` |
| `enabled` ∧ `weight === 0` ∧ 섀도 아님 | 예산 0 — 신호가 「투자금 부족」으로 기록됨 | 주황 | CLAUDE.md shadow_mode 절 「끌 때는 비중을 먼저」 |
| `buy_disabled === true` | 매수 중단(일일 손실 한도 또는 19:50 이후) | 주황 | `risk.py:646-648` · `scheduler.py:860-861` |
| `positions >= params.max_positions` | 보유 한도 n/n | 회색 | `is_max_positions()` |
| 시장 유닛(§2.4) | 시장 유닛 m=0.75 (관찰만) / 랏 ×0.75 / 신규 0배 | 보라 | §2.4 |

비중 표기 = `Math.round(weight*100)`% · 예산 = `total_investment`(원, 만 원 단위) · 사용률 = `invested_amount / total_investment`.

### 2.3 진입창·시간표 (② 칸)

시간은 전부 `src/utils/kst.ts` 의 `kstMinutesOfDay(now)` 로 판정한다(`now` 주입 seam — 테스트 시각 고정).

| 전략 | 준비 | 진입창 | 장중 청산 판정 | 15:20 | 저녁 |
|---|---|---|---|---|---|
| etf_trend | 07:45 부팅 | **09:05~09:30**(코드 상수 `_ENTRY_WINDOW_START/END`, `params` 아님) | 손절·트레일·채널(틱) | 돌파 실패 판정(보유 `breakout_fail_min_bars` 봉 이후) | 21:00 다음 거래일 미리보기 |
| donchian_swing | 07:45 | **09:05~09:30**(코드 상수, `check_buy_signal` 안 `time(9,5)`·`time(9,30)`) | 손절·채널(틱) + 09:30~15:20 REST 폴 | 시간청산 판정(`kk_time_exit_bars`·`kk_max_hold_bars`) | 21:00 |
| vcp_breakout | 07:45 | `params.entry_start`~`params.entry_end` | 손절·트레일 | — | 21:00 |
| bull_flag_breakout | 07:45 | `params.entry_start`~`params.entry_end` | 손절·트레일·측정목표 부분 익절 | — | 21:00 |
| kojiro | 07:45 | **09:05~09:30**(코드 상수) | 4선 + 스테이지3 | — | 21:00 |
| volatility_breakout | 07:45 | 09:00:05~15:20(메인 보드, `[vb_buy_cutoff]`) | 손절 | 15:20 일괄청산 | — |
| momentum | 09:30 스캔 | 09:00~15:20(`BUY_CUTOFF_KST`) | 손절·트레일 | — | — |

- 「지금」 세로선과 진입창 색 띠로 「진입창 열림 / 닫힘 · 다음 열림 09:05」를 한눈에 보인다. 기존 `EntryWindowBadge`(VCP·BFB)는 이 띠 위에 문구로 남긴다.
- 진입창 배지 문구는 `params` 값을 쓰고, 코드 상수 전략(etf·donchian·kojiro)은 「09:05~09:30(코드 고정)」으로 밝힌다.

### 2.4 시장 유닛 표시 — 전략마다 뜻이 다르다

라우트 `market_unit` = 엔진 스냅샷 `_market_unit_snaps[오늘]` 직접 읽기(§3). 모드 = `params.market_unit_mode`.

| 전략 | `off` | `shadow` | `enforce` |
|---|---|---|---|
| 터틀 4전략(kojiro·donchian·VCP·BFB) | 표시 안 함 | 「시장 유닛 m=0.75 (관찰만 · 랏 그대로)」 | m<1 「랏 ×m 적용」 · m=0 「신규 진입 0배 — 사지 않음」 |
| **etf_trend** | 표시 안 함 | 🔴 **m≤0 이거나 스냅샷 결손이면 shadow 에서도 사지 않는다**(`etf_trend.py:184-190`, 설계 L4). m>0 이면 「관찰만」 | m≤0·결손 = 차단 · m<1 = 「랏 ×m」 |

스냅샷이 없거나 `ok=false` → 「시장 유닛 미계산」(etf 는 빨강 — 그날 신규 매수 0). 대시보드의 `/api/market-regime-label` `market_unit` 은 운영 DB 로 다시 계산한 근사값이라 이 칩에 쓰지 않는다(쓰면 엔진과 어긋날 수 있다). 장세 카드에서만 쓴다.

### 2.5 깔때기 (③ 칸)

- **단계 출처** = 라우트 `funnel[]`(엔진 `_funnel_steps` = `step_no`·`step_name`·`step_conditions`·`survived_count`·`excluded_count`). 라벨은 `step_name`, 둘째 줄 회색 작은 글씨 = `step_conditions`(엔진이 런타임 `params` 로 만든 문자열). 화면 상수 라벨(`ScanMonitor` `VB_STAGES`·`VCP_STAGES`·`KOJIRO_STAGES` 등)은 **라우트가 없을 때의 폴백**으로만 남긴다.
- 막대 폭 = `survived_count / max(1단계 survived_count, 1)`. 0 단계 = 장미색 막대 + 숫자 빨강. **병목 = 위에서 처음 0 이 되는 단계** — 그 행 오른쪽에 「← 여기서 0」. 최종 0 이면 아래 한 줄: 「최종 후보 0 — ○단계(이름)에서 전부 걸렸습니다」.
- `excluded_count > 0` 인 단계는 행에 마우스를 올리면 엔진이 남긴 탈락 표본(최대 20) 대신 개수만 보인다(표본 목록은 기존 `/strategy-funnel` 화면 링크 — 무거운 목록을 5초 폴링에 싣지 않는다).
- **14일 추이** = `/api/strategy-funnel/recent?strategy_id=<id>&days=14` 의 `step_no=99`(최종) `survived_count` 를 recharts 작은 선 그래프(높이 32px, 축 없음, 0 인 날 빨간 점). 옆에 「0 연속 n일」(`StrategyFunnel.tsx` `extractDailyFinalCounts`·`computeZeroStreak` 재사용). DB 스냅샷이라 탭을 열 때 1회 + 10분 캐시.
- 기준일 머리말 = 라우트 `prepare`: 「기준일 10-12(월) · 아침 준비 07:46 완료」 / 「기준일 10-13(화) · **저녁 미리보기(잠정)** 21:02 완료」 / 「준비 중…」(`ok=null`) / 「준비 실패 hh:mm」(`ok=false`, 빨강).

### 2.6 후보표 (④ 칸) 공통 칸과 계산식

| 칸 | 식 / 출처 | 표기 |
|---|---|---|
| 종목 | `targets[t].name` → 없으면 `scan.ticker_names[t]` → 없으면 코드 | 이름(코드) |
| 상태 | 전략별 거름 순서(§4) 첫 관문 | 배지 1개 + 멈춤 중이면 회색 「풀리면: ○○」 |
| 현재가 | `scan.ticker_prices[t].current_price` | 없으면 `—` |
| 매수선 | 전략별: etf `line` · donchian `donchian_high` · VCP `base_high` · BFB `flag_high` · kojiro(없음 — 스테이지) | 원 |
| 매수선 대비 % | `(현재가 − 매수선) / 매수선 × 100` | 음수 = 아직 아래(파랑), 양수 = 위(빨강) |
| 거리 막대 | 가로 막대, 0% 위치에 매수선 눈금. 구간 색: 매수선 아래 = 회색, `0 ~ 추격 상한` = 연초록(살 수 있는 구간), 상한 초과 = 주황(추격 금지). 현재가 표식. 범위 = −10% ~ (상한 + 3%p), 밖이면 끝에 고정 + 화살표 | SVG |
| 시세 | 라우트 `ticks[t].last_tick_at` 나이(초) · `scan.subscribed_tickers` 포함 여부 | 「미구독」 빨강 · 60초 넘으면 「n분 전」 주황 |

정렬 = 상태 우선순위 → 매수선 대비 % 내림차순(가장 가까운·이미 넘은 종목이 위). 현재가 없는 종목은 맨 아래.

### 2.7 오늘 거르기 사유 (⑤ 칸)

- 출처 = 라우트 `skips`(엔진 하루 1회 기록 캡의 오늘 키). `known=false` 인 전략은 「이 전략은 종목별 거르기 사유를 기록하지 않습니다」.
- 그림 = 사유별 **종목 수** 가로 막대(사건 수가 아니다 — VCP/BFB `scan_stats.vol_gate_no_data` 는 틱마다 늘어나는 사건 수라 쓰지 않는다. 사건 수는 툴팁으로만).
- 사유 색 묶음: 가격·갭(주황) · 구조·묶음(회색) · 자금·수량(장미) · 운영 멈춤(진한 주황) · 시장 유닛(보라) · 데이터 결손(빨강).
- 멈춤 중이면 막대 대신 「멈춤 중 — 엔진은 멈춤 관문에서 돌아가 다른 사유를 남기지 않습니다. 오늘 멈춤으로 건너뛴 종목 n」(`paused_skips` 수).

### 2.8 진입 기록 (⑥ 칸)

- 실매수 신호 = `strategies.<id>.buy_signals`(최근 10). **기준선 칸 정규화** — 전략마다 키가 다르다: etf `line` · donchian `donchian_high` · VCP `base_high` · BFB `flag_high`(+ `target_price` = 측정목표) · VB/LTV `target_price` · kojiro `stage`. 화면은 「매수가 / 기준선 / 기준선 대비 %」로 맞춘다. `change_rate` 가 0 으로 들어오는 전략(etf·donchian·VCP·BFB·kojiro)은 전일 대비 칸을 `—` 로 둔다(현행 `ScanMonitor` 1195-1199 의 「+0%」 거짓 표기 시정).
- 시각 = `time`(엔진이 `HH:MM:SS` 문자열로 준다 — 변환 없이 그대로).
- 섀도 기록 = 라우트 `shadow_buys`(오늘 `[shadow_buy]` 남긴 종목 목록). 가격·기준선이 필요하면 「자세히」 버튼을 눌렀을 때만 `/api/logs/search?q=[shadow_buy] strategy=<id>&start=<오늘>` 1회 조회(ILIKE DB 조회라 폴링 금지 · INFO 로그 보존 2일).

### 2.9 보유 방어선 (⑦ 칸)

- 행 = `positions_detail` ∪ exit-lines `items`(strategy_id 일치). 값 출처:
  - **실효 손절선** = exit-lines `stop_price`(`stop_source=effective` 일 때만 「엔진」 표기, `hard_pct` 면 「근사」, null 이면 `—`).
  - 진입 ATR = exit-lines `entry_atr`(kojiro 는 `_position_atr` 대체가 이미 들어 있다).
  - 구성 선·카운트다운 = 라우트 `holdings`(전략별 §4).
- **사다리 막대**(행마다 가로 SVG): 왼쪽 끝 = 실효 손절선, 눈금 = 매수가, 오른쪽 = 매수 뒤 고점(`high_since_buy`), 현재가 표식. 구성 선(하드·본전·트레일·채널·돌파선)은 작은 눈금. **엔진 실효선과 같은 값(±1원)인 구성 선만** 「작동 중」 굵게 표시 — 같은 값이 없으면 아무것도 강조하지 않는다(화면이 고른 선을 엔진 선처럼 보이지 않게).
- 손절까지 거리 = `(현재가 − 실효 손절선) / 현재가 × 100`(KojiroMonitor 와 같은 분모). 3% 미만 주황, 1% 미만 빨강.
- 가격과 무관한 청산(시간청산·15:20 돌파 실패·kojiro 스테이지3·VB 15:20)은 사다리에 그리지 않고 **카운트다운 칩**으로 따로 둔다(exit-lines 머리말 「가격 무관 청산은 어느 출처에도 안 담긴다」).

### 2.10 프론트 규약

- 시각 = `src/utils/kst.ts` 만(`formatKstHHMM`·`formatKstDateTime`·`kstTodayISO`·`kstMinutesOfDay`). 이번 사이클에 아래 다섯 곳을 바꾼다:
  - `KojiroMonitor.tsx:36-46` 자체 `formatKst` → `formatKstDateTime`(`KojiroMonitor.test.tsx:51` 의 `/07-17|21:00/` 는 그대로 맞는다)
  - `ScanMonitor.tsx:233-242` `formatRunAt`(toLocaleString) → `formatKstDateTime`, `ScanMonitor.formatRunAt.test.ts` 함께
  - `ScanMonitor.tsx:340-358` 활성 보드 자체 Intl → `kstMinutesOfDay`
  - `BreakoutCandidateMonitor.tsx:22-24` `kstTodayStr` → `kstTodayISO`
  - `BreakoutCandidateMonitor.tsx:73-77` `kstNowHhmm` → `formatKstHHMM(new Date(now).toISOString())` 또는 `kstMinutesOfDay` 비교(테스트 seam 유지)
- 타입 = `src/types/` 에 둔다: `StrategyMonitorResponse`·전략별 candidate/holding 타입 · `PositionDetail.buy_date?: string` 추가(백엔드는 이미 보냄, `strategy_registry.py:115`) · `ScanStats` 에 VCP/BFB 관문 카운터 키 옵셔널 추가.
- 차트 = recharts(이미 씀) + SVG 직접. chart.js 는 쓰지 않는다. 새 의존성 0.
- 색 = 이익 빨강 / 손실 파랑(`BreakoutCandidateMonitor.signColor` 관례).
- 폴링 = `/trading/status` 5초(기존) · `/strategies/monitor` 10초(탭이 보일 때만) · `/balance/exit-lines` 10초(서버 5초 캐시) · `/strategy-funnel/recent` 탭 열 때 1회(10분 캐시) · `/logs/search` 버튼 눌렀을 때만.
- 테스트 id 는 `<sid>-monitor-*` 꼴로 짓고, 기존 `kojiro-*` id 는 그대로 둔다(`KojiroMonitor.test.tsx` 보존).

---

## 3. 새 읽기 전용 라우트 — `GET /api/strategies/monitor`

### 3.1 자리와 경계

- 자리 = `src/routes/strategies.py`(이미 `main.py:355` 에 등록된 라우터). 이 파일은 어떤 sha 핀에도 없다.
- 🔴 새 `.py` 파일 금지 — `tests/unit/ast/test_cycle412_scope_guard.py` S3(`src/**/*.py` 182개 고정)가 깨진다.
- 🔴 전략 파일·`strategy_base.py`·`routes/trading.py`·8영역·`scheduler.py` 0줄 — 같은 파일 S1·S2 가 sha 로 막는다. 라우트는 `getattr` 로 엔진 객체를 읽기만 한다(`balance.py:314-388` exit-lines 와 같은 방식).
- `async def` · `await` 0 · DB 0 · KIS 0 · 응답은 한 번에 조립. 실패는 HTTP 200 + `success=false`(exit-lines 와 같은 이유 — 화면 폴링이 500 을 로그에 쌓지 않게). 서버 캐시 2초(exit-lines `_exit_lines_cache` 꼴).
- `trading_scheduler`·`scanner`·`tick_volume`·`etf_trend_core` 는 **함수 안에서** import(G1 A7 관례).

### 3.2 응답 모양

```jsonc
{
  "success": true,
  "data": {
    "as_of": "2026-10-12T09:12:03+09:00",
    "running": true,
    "strategies": {
      "<sid>": {
        "prepare": { "as_of": "2026-10-12", "phase": "boot", "started_at": "…+09:00", "finished_at": "…+09:00", "ok": true },  // _live_prepare_meta, 없으면 null
        "funnel": [ { "step_no": 1, "step_name": "…", "step_conditions": "…" , "survived_count": 412, "excluded_count": 0 } ],  // _funnel_steps, survived/excluded 목록은 싣지 않는다
        "market_unit": { "mode": "shadow", "ok": true, "m": 0.75, "state": "up_falling", "bar_date": "2026-10-08" },        // 터틀 4전략·etf 만, 오늘 스냅샷 없으면 {"mode": …, "ok": false, "reason": "not_computed"}
        "skips": { "known": true, "day": "2026-10-12", "counts": { "gap_up": 2 }, "by_ticker": { "069500": ["gap_up"] } },  // 기록 캡이 없는 전략은 {"known": false}
        "paused_skips": ["…"],     // _buy_paused_logged 의 "skip|<ticker>" 키(오늘)
        "shadow_buys": ["…"],      // _shadow_logged 의 "buy|<ticker>" 키(오늘)
        "ticks": { "<ticker>": { "last_tick_at": "…+09:00", "acml_vol": 1234567 } },   // 후보 ∪ 보유
        "candidates": { "<ticker>": { /* 전략 고유 — §4 */ } },
        "holdings":   { "<ticker>": { /* 전략 고유 — §4 */ } },
        "extra": { /* 전략 고유 — 예: donchian daily_entries */ }
      }
    }
  },
  "message": ""
}
```

### 3.3 읽어도 되는 것 / 부르면 안 되는 것

**읽기(속성)**: `config.params`·`config.enabled` · `state.positions`·`state.pending_buys`·`state.sold_today`·`state.total_investment` · `_funnel_steps` · `_live_prepare_meta` · `_market_unit_snaps` · `_candidates` · `_cluster_pairs` · `_bought_today` · `_breakout_line`·`_entry_atr`·`_hsb_closed`·`_channel_low`·`_bars_since_buy`(etf) · `_breakout_high`·`_channel_low`(donchian) · `_vol_latch`·`_cooldown_until`·`_breakout_first_seen`·`_gate_emit_capped`·`_gate_emit_day`(VCP·BFB) · 캡 객체의 `_day`·`_emitted`(`_skip_logged`·`_buy_paused_logged`·`_shadow_logged`·`_kk_lot_zero_logged`·`_kk_entry_cap_logged`) · `scanner.ticker_last_tick`.

**불러도 되는 것(순수 확인됨)**:

| 호출 | 근거 |
|---|---|
| `get_effective_stop_price(t)` | 계약상 read-only(`strategy_base.py` docstring · exit-lines 가 이미 쓴다) |
| etf `_cluster_blocked(t)` · `_pure_turtle_qty(price, info)` · `_sizing_mode_ok()` | 상태·로그 무변경(`etf_trend.py` `_pure_turtle_qty` docstring 「스탬프 없음·관문 미경유」) |
| `etf_trend_core.hard_stop`·`stop_line`·`gap_skip_reason` | 순수 함수 |
| donchian `_business_days_held(buy_date, today)` · `_kk_exit_lines(t, pos)` · `_kk_r(price, atr)` · `_kk_design_lot(price, t, 1.0)` · `_kk(key)` | 순수. 단 `_kk` 는 **파라미터가 잘못됐을 때만** WARNING 1회/키/일 + 캡 기록 — exit-lines G1 이 이미 받아들인 부작용(`_kk("kk_breakeven_r")`). 키는 리터럴 집합 `{"kk_breakeven_r","kk_time_exit_bars","kk_time_exit_min_r","kk_max_hold_bars","max_daily_entries"}` 로만 |
| VCP `breakout_event_summary(today)` | docstring 「순수 읽기, never-raise」 |
| `tick_volume.get_observed_acml_vol(t)` | 「읽기 전용 — 날짜 불일치여도 clear 하지 않는다」 |

**금지**: `_market_unit_view()`(미계산이면 로그·캡 기록) · `_latch_entry()`(지난 래치를 pop) · 캡의 `should_emit`·`mark_emitted`·`count_matching`(`_sync_day` 가 날짜를 바꾸며 캡을 비운다) · `get_targets_status()`(이미 `/status` 에 있음 — 이중 계산 불필요) · `check_*`·`on_*`·`calc_*`·`prepare`·`_apply_budget_limit`·`_market_unit_*`·`_record_*`·`_emit_*`·`_roll_gate_day_if_needed` · `setattr`·변이 메서드(`pop`·`add`·`clear`·`update`…).

**캡 날짜 처리**: 캡의 `_day` 가 오늘(KST)이 아니면 「오늘 기록 없음」(`counts={}`, `day=<캡 날짜>`)으로 내고, 캡을 고치지 않는다. VCP/BFB `_gate_emit_capped` 는 `_gate_emit_day == 오늘` 일 때만 쓴다. `_vol_latch` 는 `armed_date == 오늘` 인 항목만 싣고 지우지 않는다.

---

## 4. 전략별 명세

각 전략 = (a) 깔때기 (b) 후보표 칸 + 상태 순서 (c) 시각 요소 (d) 배지 (e) 데이터 출처 (f) 요약 한 줄.

### 4.1 etf_trend — ETF 추세 (운영 활성, 현재 멈춤) — 가장 비어 있는 패널

트레이더 메모: ETF 20일 신고가 돌파는 **드물다**. 이 패널의 주 용도는 「오늘 후보가 왜 0 인가」(깔때기)와 「들고 있는 ETF 가 15:20 에 잘리나」(돌파선)다. 사용자 결정 10-09 = 설정은 지금 그대로 — 화면은 값을 보여 주기만 한다.

**(a) 깔때기 7행** — 라우트 `funnel`(엔진 `FUNNEL_STAGES`, `etf_trend.py:44-52`). `scan_stats` 에는 universe·candidates·clusters 셋뿐이라 라우트가 없으면 1행·최종만 그린다.

| step_no | 화면 라벨(짧게) | 조건 줄 = 엔진 `step_conditions`, 숫자는 `params` |
|---|---|---|
| 1 | 국내주식형 1배 ETF · 투자유의 제외 · 시총 기준 | `min_market_cap` |
| 2 | 일봉 품질 | `min_bars`봉 이상 · 최신봉 = KODEX200 최신봉 · 최근 `quality_window`봉 결손 0 |
| 3 | 유동성·변동성 밴드 | 20일 평균 거래대금 ≥ `min_trade_amount_20d` · 가격 `min_price`~`max_price` · ATR20/종가 `atr_ratio_min`~`atr_ratio_max` |
| 4 | 20일 신고가 돌파 | 종가 > 직전 20봉 고가(=돌파선) |
| 5 | EMA60 우상향 | EMA60 상승 + 종가 > EMA60 |
| 6 | 거래대금 확대 | 거래대금 ≥ 직전 20봉 평균 × `volume_multiplier` |
| 99 | 최종 후보 | + 「묶음(상관 > `cluster_corr_threshold`) 쌍 n」 보조 표기 = `scan_stats.clusters` |

**(b) 후보표 칸**

| 칸 | 값 |
|---|---|
| 상태 | 아래 순서 |
| 현재가 · 시가 | `ticker_prices` |
| 돌파선 | `candidates[t].line` |
| 돌파선 대비 % + 거리 막대 | §2.6. ETF 는 「추격 상한」 대신 **시가 기준** 두 문턱을 막대 위에 표시: 전일종가 +`gap_skip_threshold`% 선, 돌파선 +`gap_over_line_pct`% 선 |
| 시가 갭 % | `(시가 − 전일종가)/전일종가×100`, `≥ gap_skip_threshold` 면 주황 |
| 시가−돌파선 % | `(시가 − line)/line×100`, `> gap_over_line_pct` 면 주황(엔진은 `>` — 같은 값은 통과) |
| N · 변동성 | `n`(TR14 단순평균, 사이징 기준) · `atr20/prev_close`% 를 밴드 게이지(`atr_ratio_min`~`max`, kojiro ATR 밴드 막대 재사용) |
| 20일 거래대금 | `tv20`(억 원) |
| 예상 수량 | `design_qty` = 라우트가 `_pure_turtle_qty(prev_close, info)` 로 계산(전일 종가 기준 · 상한·시장유닛 enforce 적용 전). **0 이면 빨강 「1주도 안 됨 — 사지 않음」**(엔진 `rounds_to_zero`). 양수는 「최대 n주」 |
| 묶음 | `cluster_partners`(상관 쌍 상대 종목) · `cluster_blocked=true` 면 「묶음 보유로 차단(상대: ○○)」 |
| 시세 | §2.6 |

**상태 순서(엔진 `check_buy_signal` 순서 그대로, `etf_trend.py:143-215`)** — 처음 맞는 것:
1. 시세 없음(미구독 또는 60초 넘게 틱 없음) — 화면 판단(엔진 평가 자체가 없음)
2. 보유 중 / 주문 중(`pending_buy_tickers`) / 오늘 매도함
3. 오늘 시도함(`bought_today`) — 갭 스킵도 여기 들어간다(엔진이 갭 사유 때 `_bought_today` 에 넣는다). `skips.by_ticker` 에 `gap_up`·`gap_over_line` 이 있으면 「오늘 갭 스킵」으로 구체화
4. **신규 매수 멈춤** — 주 배지. 회색 「풀리면: (5~14 중 첫 관문)」
5. 매수 중단(`buy_disabled`) · 보유 한도 · 일일 손실 한도
6. 진입창 전(「09:05 부터」) / 진입창 지남(「다음 거래일」)
7. 시가 미확정(`open_price ≤ 0`)
8. 갭 초과 — `gap_skip_reason(open, prev_close, line, …)` 결과 `gap_up` / `gap_over_line`(화면도 같은 식, 라우트가 값 제공)
9. 장중 붕괴(현재가 < 시가)
10. 묶음 보유로 차단
11. 시장 유닛 미계산 / 0배(§2.4 — shadow 에서도 차단)
12. 예산 0(섀도 아님) / 1주도 안 됨
13. 진입 가능

**(c) 시각 요소**: ② 시간표(15:20 돌파 실패 판정 눈금 포함) · ③ 7단 깔때기 + 14일 선 · ④ 거리 막대(시가 두 문턱) + ATR 밴드 게이지 · ⑤ 사유 분포(아래 표) · ⑦ 사다리.

⑤ 사유(엔진 `[etf_trend_skip] reason=`, `_skip_logged` 키 `ticker|reason`):

| reason | 화면 문구 | 색 묶음 |
|---|---|---|
| `open_unknown` | 시가 미확정 | 데이터 결손 |
| `gap_up` | 전일 대비 갭 과다 | 가격·갭 |
| `gap_over_line` | 돌파선 위로 너무 떠서 시작 | 가격·갭 |
| `collapse` | 시가 아래로 밀림 | 가격·갭 |
| `cluster_held` | 같은 묶음 ETF 보유 중 | 구조·묶음 |
| `market_unit_unavailable` | 시장 유닛 미계산 | 시장 유닛 |
| `zero_state` | 시장 유닛 0배 | 시장 유닛 |
| `no_budget` | 예산 0 | 자금·수량 |
| `rounds_to_zero` | 1주도 안 됨 | 자금·수량 |
| `sizing_mode_invalid` | 사이징 설정 오류(터틀 아님) | 데이터 결손(빨강) |

⑦ **보유 방어선** — 라우트 `holdings[t]`:

| 키 | 값 | 화면 |
|---|---|---|
| `entry_n` | `_entry_atr[t]` | 진입 N |
| `hsb_closed` | `_hsb_closed[t]` | 「매수 뒤 확정 고점(어제까지 봉) — 장중 고점은 다음 날 반영」 |
| `bars_since_buy` | `_bars_since_buy[t]` | 보유 n봉 |
| `lines.hard` | `core.hard_stop(E, N, backstop_pct=turtle_backstop_pct, stop_atr=stop_atr)` | 하드 손절 |
| `lines.breakeven` | `hsb_closed ≥ E + breakeven_promote_atr×N` 이면 E, 아니면 null | 본전 승격 |
| `lines.trail` | `hsb_closed − atr_trail_mult×N`(hsb·N 있을 때) | 트레일 |
| `lines.channel` | `bars ≥ 1` 이면 `_channel_low[t]`, 아니면 null | 10일 채널(현재가가 이 **아래**로 가면 청산) |
| `breakout_fail` | `{ "line": _breakout_line[t], "active": bars ≥ breakout_fail_min_bars }` | 15:20 판정선 |
| `effective_stop` | `get_effective_stop_price(t)` | 실효 손절선(엔진) |

- 15:20 카운트다운 칩: `active=false` → 「15:20 돌파선 판정은 보유 n봉째부터」 · `active=true` ∧ 현재가 < 돌파선 → 빨강 「지금 가격이면 15:20 정리(돌파 실패)」 · 이상이면 「15:20 판정 대상 · 돌파선까지 +x%」 · 보유 ETF 마지막 틱이 `breakout_fail_price_max_age_secs`(180초)보다 낡으면 회색 「시세 낡음 — 15:20 판정 건너뜀 위험」(엔진 `[etf_trend_1520_stale]`).
- ⚠️ `breakeven_promote_atr=0` 이면 엔진은 「끔」이 아니라 「다음 날 손절선 본전」으로 동작한다(워크리스트 10-06 별건 결함, 도움말과 불일치). 화면은 엔진이 하는 대로(본전 선 활성) 보여 주고 고치지 않는다.

**(d) 배지**: §2.2 + §2.4(etf 행).
**(e) 출처**: `/status`(params·positions·targets 2키·scan_stats·buy_signals) + `/strategies/monitor`(funnel·candidates·holdings·skips·market_unit·prepare·ticks) + `/balance/exit-lines`(stop_price) + `/strategy-funnel/recent`.
**(f) 요약 한 줄 예**: 「ETF 추세 · 멈춤 · 후보 2 (병목 없음) · 진입창 닫힘 · 신호 0 · 보유 1/4 · 예산 31% · 손절까지 −4.2% · 15:20 판정 1」.

`utils/strategyInfo.ts` 에 etf_trend 항목을 더한다(탭 설명). 숫자 문턱은 쓰지 않는다(「숫자는 패널 상단의 현재 설정을 보세요」) — 정적 문장이 운영 값과 어긋나는 것을 막는다.

### 4.2 donchian_swing — 돈키언 (깡토식 청산 cycle405, 현재 멈춤)

트레이더 메모: 진입은 그대로(20일 신고가 + EMA60 + 거래대금 1.5배, 다음 날 09:05~09:30, 갭·추격 상한), 청산이 바뀌었다 — **손절 = 매수가 − 1R, 고점이 +3R 닿으면 「무장」(손절선 본전 + 10일 채널 감시), 20봉째 15:20 에 +1R 못 넘었으면 정리, 최대 250봉**. 화면 도움말(`ScanMonitor.tsx:598, 664-691` 「ATR×2 트레일링, −7% 손절, 시간 청산 없음」)은 **틀린 설명**이라 이번에 교체한다.

**(a) 깔때기 9행** — 라우트 `funnel`(엔진 `FUNNEL_STAGES`, `donchian_swing.py:39-53`). 3단계 「진입 차단 13건 통과」가 `scan_stats` 에 없어 지금 화면에서 빠져 있다 — 라우트로 채운다. 막대 기준 = 1단계(합집합)(현행 `universeMax` 가 union 을 빼는 결함 시정, `ScanMonitor.tsx:546-550`).

**(b) 후보표 칸**: 상태 · 현재가 · 시가 · 20일 신고가(`donchian_high`) · 돌파선 대비 % + 거리 막대(구간 상한 = `max_breakout_extension_pct`) · 시가 갭 %(`≥ gap_skip_threshold` 주황) · 당일 확장 % = `(max(현재가, 시가) − donchian_high)/donchian_high×100`(엔진도 `ticker_prices` 에 고가 키가 없어 같은 값을 본다, `> max_breakout_extension_pct` 주황) · EMA60 · N(ATR14) · **1R** = 라우트 `r_won`(`_kk_r(prev_close, atr)`) 과 `r_pct = r_won/prev_close×100` · **설계 랏** = 라우트 `design_lot`(`_kk_design_lot(prev_close, t, 1.0)`, 0 이면 빨강 「1R 이 너무 크거나 예산 부족 — 사지 않음」) · 시세.

**상태 순서(`donchian_swing.py:1572-1668`)**: 시세 없음 → 보유/주문/매도함 → 오늘 시도함(`_bought_today` — 갭 스킵 포함, 엔진은 갭 스킵 사유를 캡으로 남기지 않으므로 화면이 시가 갭으로 「갭 스킵(추정)」 구체화) → **멈춤** → 매수 중단·보유 한도·일일 손실 → 진입창 전/지남 → 갭 초과 → 추격 상한 초과 → 시장 유닛(enforce 차단) → 설계 랏 0(`[donchian_kk_lot_zero]`) → 하루 신규 상한 도달(`[donchian_daily_entry_cap]`) → 진입 가능.

**(c) 시각**:
- ⑤ 사유 = `skips.known=true` 이지만 **엔진이 캡으로 남기는 사유는 둘뿐**이다 — `_kk_lot_zero_logged`(키 = 종목 → 「설계 랏 0」) · `_kk_entry_cap_logged`(키 = 종목 → 「하루 신규 상한」). 갭 스킵·추격 상한은 캡이 없어(자유 문장 로그) 라우트가 못 센다 → 사유 칸 아래 회색 「갭·추격 상한은 후보표 상태(화면 추정)로 확인」.
- 상단 게이지 「오늘 신규 진입 n / `max_daily_entries`」 — 라우트 `extra.daily_entries = {count, cap}`(count = 오늘 매수일 보유 + 주문 중, 엔진 `_kk_daily_cap_blocks` 와 같은 식 — `_kk_daily_cap_blocks` 자체는 로그를 남기므로 부르지 않고 같은 합을 라우트가 센다).
- ⑦ **보유 사다리(깡토식)** — 라우트 `holdings[t]`:

| 키 | 값 |
|---|---|
| `r_won` | `_kk_r(E, _entry_atr.get(t, 0))` |
| `stop` · `armed` · `channel` | `_kk_exit_lines(t, pos)` 반환 그대로 |
| `arm_price` | 미무장일 때 `ceil(E + kk_breakeven_r × (E − stop))`(exit-lines `kk_arm_price` 와 같은 식) |
| `target_1r` | `E + kk_time_exit_min_r × r_won` |
| `reached_1r` | `high_since_buy ≥ target_1r` |
| `days_held` · `days_fallback` | `_business_days_held(buy_date, 오늘)` |
| `time_exit_bars` · `max_hold_bars` | `_kk("kk_time_exit_bars")`·`_kk("kk_max_hold_bars")` |

  사다리: 손절선(E−R) — 매수가 — 무장가(E+3R) 눈금 — 고점 — 현재가. 무장 뒤에는 「무장 ✓ 손절선 본전 · 10일 채널 n원 감시」.
- **시간청산 카운트다운 칩**: 「보유 (days_held+1)봉째」. `due = time_exit_bars − 1 − days_held`. `reached_1r=false` 이면 `due > 0` → 「n영업일 뒤 15:20 시간청산 판정 — +1R(target_1r원) 못 넘으면 정리」, `due ≤ 0` → 빨강 「오늘 15:20 시간청산 대상(+1R 미도달)」. `reached_1r=true` 면 「+1R 넘음 — 시간청산 면제(최대 max_hold_bars봉)」. `days_fallback=true` 면 회색 「보유일 근사(거래일 캐시 부족)」.
- 도움말 교체 문안(요지만, 숫자는 `params` 로): 「손절 = 매수가 − 1R(1R = max(매수가×`kk_r_floor_pct`%, `kk_r_atr_mult`×진입 ATR)) · 고점이 매수가+`kk_breakeven_r`R 에 닿으면 무장: 손절선이 본전으로 올라가고 `channel_exit_period`일 저가 채널 이탈도 청산 · 매수 뒤 `kk_time_exit_bars`봉째 15:20 에 +`kk_time_exit_min_r`R 를 못 넘었으면 정리 · 최대 `kk_max_hold_bars`봉 · 하루 신규 진입 최대 `max_daily_entries`종목」.

**(d)(e)(f)**: 배지 §2.2·§2.4 · 출처 `/status` + 라우트 + exit-lines(`kk_armed`·`kk_arm_price`·`stop_price` — 라우트와 같은 값이어야 한다, §8 R4) · 요약 예 「돈키언 · 멈춤 · 후보 4 · 진입창 닫힘 · 오늘 진입 0/3 · 보유 2/6 · 손절까지 −6.1% · 시간청산 D-3 1종목」.

### 4.3 vcp_breakout — VCP (운영 활성, 현재 멈춤)

트레이더 메모: VCP 는 **돌파선(베이스 고점)을 아래에서 위로 넘는 순간** 평가하고, 그 순간 거래량이 컷에 못 미치면 「래치」를 걸어 **같은 날** 거래량이 차기를 기다린다. 체결 0 의 1순위 원인은 「돌파는 했는데 거래량이 안 찼다」와 「추격 상한을 넘었다」다 — 이 둘이 보여야 한다. 지금 화면(`BreakoutCandidateMonitor`)은 거래량 **컷**만 있고 **현재 거래량**이 없다.

**(a) 깔때기 9행** — 라우트 `funnel`(엔진 `vcp_breakout.py:78-91`). 화면 상수 `VCP_STAGES` 의 「50/150/200 EMA 정렬」은 낡은 라벨(엔진 = 단기/중기/장기, 실효 길이는 `step_conditions`) — 엔진 이름으로 바꾼다.

**(b) 후보표 칸**(기존 `BreakoutCandidateMonitor` 칸에 더함): 상태 · 현재가 · 돌파선(`base_high`) · 돌파선 대비 % + 거리 막대(구간 상한 = `max_breakout_extension_pct`, 엔진은 `>` 초과만 거부) · **거래량 게이지** = `ticks[t].acml_vol / volume_threshold`(0~150% 막대, 100% 선 표시. `acml_vol=null` 이면 회색 「거래량 미관측 — 엔진은 사지 않음(fail-closed)」) · 손절선(`base_low`)과 손절폭 % = `(base_high − base_low)/base_high` · **래치** = 라우트 `candidates[t].latch_armed_at`(오늘 무장 시각, hh:mm) · **오늘 첫 돌파** = 라우트 `candidates[t].first_cross_at`·`max`(`breakout_event_summary(오늘).per_ticker`) · 쿨다운 D-n · 시세.

**상태 순서(`vcp_breakout.py:1397-1475`)**: 시세 없음 → 보유/주문/매도함/오늘 매수 → **멈춤** → 매수 중단·보유 한도·일일 손실 → 진입창 밖(`entry_start`~`entry_end`) → 쿨다운 D-n → (래치 무장 중) 「래치: 돌파선 위 거래량 대기 n%」/「래치: 돌파선 아래로 밀림(유지)」 → 돌파선 아래(거리 −x%) → 거래량 미관측 → 거래량 부족 n% → 추격 상한 초과 → 시장 유닛 차단 → 진입 가능(다음 교차·거래량 충족 시).
- ⑤ 사유 = 라우트 `skips` 를 `_gate_emit_capped`(오늘)의 `(ticker, kind)` 로 만든다: `no_data`(거래량 미관측) · `reject_ext`(추격 상한) · `latch_armed`(래치 무장) · `setup_conflict`. 종목 수 기준.
- 🔴 멈춤 중에는 엔진이 `_observe_breakout_tick` 도 건너뛴다(계좌 게이트 뒤라서) → `first_cross_at` 이 비는 것이 정상. 「멈춤 중 — 돌파 관측 없음」.

**(c) 시각**: 행마다 **구조 막대** — 손절선(`base_low`) ─ 돌파선(`base_high`) ─ 추격 상한(`base_high×(1+cap)`) 구간을 한 줄에, 현재가 표식(VCP/BFB 공통 컴포넌트). 거래량 게이지. 래치는 시간표 띠 위 점(무장 시각).

**(d)(e)(f)**: 배지 §2.2·§2.4 · 출처 `/status` targets(이미 있음) + 라우트(latch·first_cross·acml_vol·skips·funnel) · 요약 예 「VCP · 멈춤 · 후보 8 · 진입창 09:05~14:30 닫힘 · 돌파 0 · 래치 0 · 보유 1/5」.

### 4.4 bull_flag_breakout — BFB (운영 활성, 현재 멈춤)

VCP 와 같은 틀. 차이만 적는다.
- (a) 깔때기 9행 = 엔진 `bull_flag_breakout.py:42-53`.
- (b) 매수선 = `flag_high` · 손절선 = `flag_low` · **측정목표** = `measured_target`(부분 익절 트리거 — 전량 익절 아님, exit-lines 머리말) · 거래량 컷 = `volume_threshold`(`flag_avg_volume × breakout_volume_mult`). **유지 대기(retention)** 칸은 `params.breakout_retention_minutes > 0` 일 때만 보인다(운영 DB 실측 0 — 0 이면 칸 자체를 숨긴다). `breakout_seen_at` 이 있으면 「⏱ m:ss 대기」(기존 `computeStatus` 재사용).
- 상태 순서(`bull_flag_breakout.py:960-1060`): VCP 와 같고, 래치 앞에 「유지 대기 m:ss」(retention>0 일 때), 래치 뒤 「후퇴(돌파선 아래로 복귀)」(`retreat`).
- (c) 구조 막대 = 손절선(`flag_low`) ─ 돌파선(`flag_high`) ─ 추격 상한 ─ 측정목표. 깃대 길이(`pole_high − pole_start`)를 막대 옆 작은 숫자로.
- ⑤ 사유 kind = `no_data`·`reject_ext`·`latch_armed`·`seen`·`retreat`·`setup_conflict`.
- BFB 에는 `breakout_event_summary` 가 없다 — 「오늘 첫 돌파」 칸은 `breakout_seen_at`(retention 대기 중일 때만)으로 대신하고, 없으면 칸을 숨긴다(지어내지 않는다).
- ⑦ 보유: exit-lines `target_price`(`target_source`) 를 측정목표로, `target_hit` 이면 「부분 익절 끝」.

### 4.5 kojiro — 고지로 대순환 (기준 패널, 정정 목록)

틀은 유지하고 **틀린 상수만 고친다**. 테스트 id 보존.

| 위치 | 지금 | 고칠 것 |
|---|---|---|
| `KojiroMonitor.tsx:1-3` 머리 주석 | 「enabled=False 다크런치 · 21:00 스캔 기준」 | 운영 활성. 준비 시각은 `prepare` 머리말로 |
| 36-46 `formatKst` | 자체 Intl | `formatKstDateTime` |
| 24 깔때기 라벨 「(1.0~4.5%)」 · 83 `bandMax` 기본 0.045 | 엔진 0.06(`kojiro.py:159`) | 라벨은 라우트 `funnel` 의 엔진 이름+조건, 밴드 게이지는 `params.atr_ratio_min/max`(기본값 폴백은 `—`) |
| 111-132 배너 | 활성/관찰 둘뿐 | §2.2 배지(멈춤·섀도·꺼짐+보유) + §2.4 시장 유닛 + 기준일 |
| 162-166 「최근 3영업일 6→1 전환」 | 엔진 `stage1_freshness` 5 | `params.stage1_freshness` |
| 279 「갭업 ≥5% / 갭다운 ≤-4%」 | 리터럴 | `params.gap_up_skip_pct`·`gap_down_skip_pct` |
| 302-364 방어선 | 후보 ATR 로 화면 계산 · 보유가 후보 밖이면 `-` · 본전 승격선 없음 · 머리글 숫자 리터럴 | **실효 손절선 = exit-lines `stop_price`**(엔진 `_position_stop_price` = max(고정% · ATR 하드(+`_stop_floor`) · 샹들리에 · 본전)). 구성 선은 exit-lines `entry_atr` 로 그리되 §2.9 규칙(엔진 값과 같은 선만 강조). 머리글은 `params.stop_atr`·`trail_atr`·`hard_stop_pct`·`breakeven_promote_atr`. 스테이지3 = 카운트다운 칩 「스테이지3 — 다음 평가 때 청산」 |
| `utils/strategyInfo.ts:66-77` | 「3영업일 · 4.5% · 관찰 모드로 출시」 | 숫자 제거(§4.1 끝 문장과 같은 원칙), 「관찰 모드」 문구 제거 |

추가: ② 시간표 · ③ 14일 선 · ⑤ 사유는 `known=false`(kojiro 캡 사유 `[kojiro_sector_cap]`·`[kojiro_open_risk_cap]` 의 화면화는 이번 범위 밖 — 「기록 없음」).

### 4.6 volatility_breakout — VB (섀도, 가벼운 패널)

- ① 주 배지 「섀도 · 주문 없이 기록만」 + 비중 0 정상 표기(「섀도 전략은 비중 0 + 켜짐이 정상」). VB 는 멈춤 목록에 없어 섀도 기록이 **실제로 쌓인다**.
- ③ 깔때기 = 기존 `VB_STAGES`(라우트 있으면 엔진 9단계, 7~9 는 관찰 전용 표기).
- 기존 보드별 목표가표(`ScanMonitor.tsx:892-1130`) 그대로.
- ⑥ **오늘 섀도 매수 기록** = 라우트 `shadow_buys`(종목) — 「실전이었으면 샀을 종목 n」. 「자세히」 = logs search 1회(가격·기준선·m). 🔴 섀도 BUY 는 `buy_signals` 에 없다(`strategy_base.py` `_shadow_buy_intercepted` docstring) — 「매수 신호 0」을 「섀도가 안 돈다」로 읽지 않게 ⑥ 머리말에 밝힌다.
- 15:20 일괄청산 칩(보유 있을 때만).
- 요약 예 「변동성 돌파 · 섀도 · 후보 31 · 섀도 기록 2 · 보유 0」.

### 4.7 momentum — 모멘텀 (가벼운 패널)

- 🔴 **운영 상태를 단정하지 않는다.** 조사 결과는 「꺼짐」이라 했지만 워크리스트 10-06 기록은 비중 0.03(켜짐)이고 10-08 멈춤 목록(kojiro·donchian·VCP·BFB·etf)에 momentum 이 **없다**. 즉 계좌 전환 기간에도 momentum 은 살 수 있는 상태일 수 있다. 화면은 §2.2 판정으로만 그린다 — 하드코딩 금지. tester 가 실측(§8 T1).
- 기존 깔때기(`MOMENTUM_STAGES`, scanner `scan_filter_stats`)와 종목 목록 유지. `_funnel_steps` 없음(준비 단계 없음) → 라우트 `funnel=[]`, 화면은 기존 키로.
- ② 시간표 09:00~15:20(매수 컷). ⑤ `known=false`.
- 요약 예 「모멘텀 · 실매매(또는 꺼짐) · 순위 후보 n · 신호 n · 보유 n/4」.

### 4.8 long_tail_volatility — LTV (꺼짐, 가벼운 패널)

- 주 배지 「꺼짐」. 보유 > 0 이면 §2.2 빨강 칩(손절 정지).
- 깔때기·보드별 목표가표는 기존 그대로(접힘 기본).
- ⑦ 보유 손절선은 exit-lines 가 `mode_dependent`(—)로 준다 — 「상한가 모드에 따라 −5%/−3.5% — 화면이 하나로 고르지 않음」 문구(`position_exit_lines.py` `_MODE_DEPENDENT_STOP_STRATEGIES` 원칙).

---

## 5. 대시보드 요약 — 「전체」 탭 전략 요약표

### 5.1 표 칸

행 = 전략 하나. 순서 = 주 배지(실매매 → 멈춤 → 섀도 → 꺼짐) → 비중 내림차순. 행을 누르면 그 전략 탭으로 간다.

| 칸 | 값 | 시각 |
|---|---|---|
| 전략 | `strategyLabel(id)` + 색 점(`getStrategyColor`) | |
| 상태 | §2.2 주 배지 + 빨강 보조 칩만(손절 정지·설정 오류) | 배지 |
| 왜 안 사나(한 줄) | §5.2 규칙 | 문구 |
| 후보 | 최종 후보 수 · 병목 단계 이름(최종 0 일 때) | 작은 숫자 + 「병목: ○○」 |
| 14일 | 최종 후보 선 그래프(높이 20px) | recharts, 탭 열 때 1회 |
| 진입창 | 열림/닫힘 · 다음 열림 시각 | 점 + 시각 |
| 오늘 신호 | `buy_signals` 중 오늘 수 · 섀도면 `shadow_buys` 수(「섀도 n」) | 숫자 |
| 보유 | `positions / params.max_positions` | 작은 칸 막대(n칸 중 채움) |
| 예산 | `invested_amount / total_investment` | 가로 막대 0~100% |
| 손절 여유 | 보유 종목 중 가장 가까운 실효 손절선까지 % | 3% 미만 주황 · 1% 미만 빨강 |
| 청산 예정 | 오늘 15:20 판정 대상 수(etf 돌파 실패 위험 · donchian 시간청산 · VB 일괄) | 칩 |
| 오늘 실현손익 | `daily_realized_pnl` | 빨강/파랑 |

성과 지표(3개월 거래 수·승률·세후 합계 = `/api/strategies/te`)는 요약표 오른쪽 끝에 접힘 칸으로만 둔다 — 「진행상황」 요청의 중심이 아니고, 표본이 작은 전략에서 승률이 과신을 부른다(kojiro 「대시보드 성과는 합성값 — 비중 근거 금지」 메모와 같은 이유).

### 5.2 「왜 안 사나」 한 줄 — 우선순위

처음 맞는 것 하나:
1. 꺼짐 → 「꺼짐」(보유 있으면 「꺼짐 — 보유 n 손절 정지!」)
2. 멈춤 → 「신규 매수 멈춤(운영자 설정)」
3. 준비 실패·준비 중 → 「후보 준비 실패 hh:mm」 / 「준비 중」
4. 최종 후보 0 → 「후보 0 — 병목: ○○」
5. 매수 중단(`buy_disabled`) → 「매수 중단(일일 손실 한도 또는 19:50 이후)」
6. 보유 한도 → 「보유 한도 n/n」
7. 진입창 밖 → 「진입창 밖 — 다음 hh:mm」
8. 시장 유닛 차단(etf m≤0 · enforce m=0) → 「시장 유닛 0배」
9. 예산 0(섀도 아님) → 「예산 0」
10. 오늘 거르기 사유가 있으면 가장 많은 사유 → 「오늘 주 사유: 거래량 부족(3종목)」
11. 섀도 → 「섀도 기록 n」
12. 그 밖 → 「대기 중 — 후보 n, 가장 가까운 ○○ 돌파선까지 −x%」

---

## 6. 현 코드와의 정합성 — 충돌·불일치

| # | 항목 | 지금 | 이 명세 | 선택지 |
|---|---|---|---|---|
| C1 | **KojiroMonitor 상수**(밴드 4.5%·freshness 3·갭 리터럴·방어선 머리글·본전선 누락·후보 ATR 로 방어선 계산) | 엔진 값과 다름 | §4.5 대로 `params`·exit-lines 로 | 고침(권고) / 유지 시 화면이 운영과 다른 문턱을 계속 보인다 |
| C2 | **donchian 도움말**(ATR×2 트레일·−7%·시간청산 없음) | cycle405 이전 설명 | §4.2 문안으로 교체 | 고침(권고) — 운영자가 틀린 청산 규칙을 믿는다 |
| C3 | 화면 깔때기 상수 라벨(`VCP_STAGES` 「50/150/200」 등) | 낡음 | 엔진 `step_name`·`step_conditions` 우선, 상수는 폴백 | 고침(권고) |
| C4 | **momentum 운영 상태** | 조사 = 꺼짐 / 워크리스트 10-06 = 비중 0.03 · 10-08 멈춤 목록에 없음 | 화면은 데이터로만 판정 | tester 실측(§8 T1) — 켜져 있고 멈춤이 아니면 **계좌 전환(10-13) 전 신규 매수 가능 상태**라 팀장에게 알린다(이 명세는 설정을 바꾸지 않는다) |
| C5 | `test_cycle412_scope_guard.py` S1~S4 | 「cycle412 병합 후 삭제」인데 남아 있음 | 라우트는 `strategies.py` 안 · 새 파일 0 · 전략 파일 0줄이라 안 깨진다 | 전략 파일에 getter 가 필요해지면 S2 sha 재조정 또는 가드 삭제를 팀장이 정한다(이 명세는 필요 없게 설계) |
| C6 | `Strategies.tsx:401-409` 배지 「활성/비활성」뿐 | 멈춤·섀도 전략도 「활성」 | 같은 배지 컴포넌트 재사용 가능 | **범위 판단은 팀장**(설정 화면이라 요청 범위 밖일 수 있음). 하면 한 줄 교체 |
| C7 | etf `breakeven_promote_atr=0` 도움말 불일치 | 별건 결함 | 화면은 엔진 동작대로 | 이번에 고치지 않는다 |
| C8 | `PositionDetail` 타입 `buy_date` 누락 | 백엔드는 보냄 | 타입에 추가 | 고침 |
| C9 | MSW `/trading/status` = `strategies: {}` | 실제 키 fixture 없음 | §9 fixture 신설 | 고침 |

`DEFAULT_PARAMS`·`tradable_boards`·안전 규칙과 충돌하는 권고는 없다(읽기 전용).

---

## 7. 반례 / 한계

- **「풀리면: ○○」 은 화면 추정이다.** 멈춤 중 엔진은 다음 관문을 계산하지 않는다. 화면은 같은 순서·같은 식으로 흉내 내지만 시가·현재가가 바뀌면 답도 바뀐다. 회색·「추정」 표기를 빼지 않는다.
- **예상 수량은 최대치다.** etf `design_qty`·donchian `design_lot` 은 전일 종가 기준 설계 랏(K축·ρ축·시장 유닛 enforce·잔여 클램프 전)이라 실제 주문 수량이 더 작을 수 있다. 다만 **0 은 믿어도 된다**(엔진도 0 이면 신호 단계에서 거른다).
- **거래량 게이지는 우리가 받은 체결 누적이다.** WS 수신이 빠지면 실제 거래소 누적보다 작게 보이고, 엔진도 같은 값으로 판정한다(fail-closed). 화면과 엔진은 일치하지만 HTS 거래량과는 다를 수 있다 — 툴팁에 밝힌다.
- **장중 고가는 모른다.** donchian 확장 판정은 엔진도 `max(현재가, 시가)` 를 본다(`ticker_prices` 에 고가 키가 없다). 장중에 더 높았다가 내려온 경우 화면·엔진 모두 확장을 작게 본다 — 일치하므로 그대로 둔다.
- **etf 트레일은 어제까지의 봉 고점 기준이다**(`_hsb_closed`). 오늘 장중 고점이 높아도 트레일 선은 내일 올라간다 — 사다리 툴팁에 밝힌다.
- **21:00 뒤 후보는 잠정이다.** 20:30 일봉 종가가 아침 확정에서 바뀔 수 있다(cycle386). 기준일 머리말이 막는다.
- **재시작 뒤 사유·래치·섀도 기록은 0 부터 다시 쌓인다.** 「hh:mm 재준비 이후」 표기.
- **시장 유닛 칩은 엔진 스냅샷이 있을 때만 정확하다.** 없으면 「미계산」 — 다른 출처로 메우지 않는다.
- **가격 무관 청산**(시간청산·15:20 돌파 실패·스테이지3·VB 15:20)은 사다리에 없다. 카운트다운 칩을 놓치면 「손절선까지 여유 있음」을 「안 팔린다」로 오독한다.
- 이 화면은 **설정을 바꾸는 버튼을 두지 않는다**(멈춤 해제·섀도 끄기 등). 바꾸는 길은 기존 설정 화면·PUT 그대로.

---

## 8. 후속 검증 권고

### 8.1 tdd-engineer (Red)

백엔드(pytest, freezegun, 합성 전략 객체):

| # | 단언 |
|---|---|
| R1 | 응답 모양 — 등록 전략 전부에 §3.2 키. 전략이 하나도 없거나 스케줄러 미기동이면 `success=true, strategies={}` · 예외는 HTTP 200 `success=false` |
| R2 | **순수성 AST**(`test_cycle412_g1_purity.py` 본뜸): 핸들러 `async`·`await` 0 · 허용 호출 목록(§3.3)만 · 금지 호출 0 · 대입 대상은 이름만 · `del`·`setattr`·`__dict__` 0 · `_kk` 는 리터럴 5키 집합만 · 8영역 모듈 최상단 import 0 |
| R3 | **무변경 행위 시험**: 라우트 호출 전후 전략 객체의 관련 속성(`_vol_latch`·`_breakout_first_seen`·`_gate_emit_capped`·`_gate_emit_day`·캡의 `_day`·`_emitted`·`_market_unit_snaps`·`_candidates`·positions) 깊은 복사 비교가 같다. **날짜 경계**: 캡 `_day`=어제·`_vol_latch` armed_date=어제로 두고 호출 → 응답은 「오늘 기록 없음」·래치 제외, 객체는 그대로(어제 항목이 지워지지 않는다) |
| R4 | **엔진 값과 일치**: etf 합성 보유(bars 0·1·2, hsb None, N None, `breakeven_promote_atr` 0·1.5) → `max(활성 구성 선) == get_effective_stop_price` · donchian `stop`·`armed`·`arm_price` == exit-lines `kk_*` · `due ≤ 0 ∧ ¬reached_1r` 인 날 `check_force_clear()` 가 그 종목을 포함(같은 freezegun 날짜, 공휴일 낀 주 포함) |
| R5 | 사유 사상: etf `_skip_logged._emitted={"069500|gap_up","069500|collapse","229200|cluster_held"}` → `counts={gap_up:1,collapse:1,cluster_held:1}` · `by_ticker` · VCP `_gate_emit_capped={("A","no_data"),("A","latch_armed")}` → 종목 수 기준 |
| R6 | etf `design_qty` == `_pure_turtle_qty(prev_close, info)` · 예산 0 이면 0 · `sizing_mode` 오조작이면 0 |
| R7 | 범위 가드 그대로 초록: cycle412 S1~S4(새 `.py` 0 · 핀 파일 sha 무변경) |
| R8 | 성능: 7전략 × 후보 50 × 보유 6 합성에서 1회 조립 < 50ms(I/O 0 증명 겸) |

프론트(vitest + RTL + MSW, 시각 고정):

| # | 단언 |
|---|---|
| F1 | 배지 행렬: `enabled`(t/f) × `buy_paused`(true/false/`"true"`/없음) × `shadow_mode`(true/false/`1`) × `weight`(0/0.2) × `positions`(0/2) → §2.2 표 그대로. `"true"` 문자열은 「멈춤」이 **아니라** 「설정 모양 오류」 |
| F2 | 꺼짐+보유 → 빨강 「손절 정지」 칩, 요약표 한 줄에도 같은 경고 |
| F3 | etf 상태 경계값: 시가 = 전일종가×1.03 → 갭 초과(`≥`) · ×1.0299 → 통과 / 시가 = line×1.04 → 통과(`>`) · ×1.0401 → 돌파선 위 과다 / 현재가 = 시가−1 → 붕괴 / 멈춤 켜짐 → 주 배지 멈춤 + 「풀리면: 갭 초과」 / 시장 유닛 shadow·m=0 → 차단(etf 만) — 같은 입력의 donchian 은 차단 아님 |
| F4 | donchian: `days_held=18, bars=20, reached_1r=false` → 「1영업일 뒤 15:20 판정」 · `19` → 「오늘 15:20 대상」 · `reached_1r=true` → 면제 문구 · 무장 사다리 |
| F5 | VCP 거래량 게이지(`acml_vol=null` → 미관측 문구) · 추격 상한 정확히 7.5% → 허용, 7.51% → 주황 · 래치 무장 시각 표시 · BFB `breakout_retention_minutes=0` 이면 유지 대기 칸 없음 |
| F6 | 깔때기 병목 = 처음 0 단계 · 라벨은 라우트 `step_name`(화면 리터럴 「4.5%」·「50/150/200」 이 렌더에 **없음**) · 라우트 실패 시 폴백 상수 라벨 |
| F7 | 시간 게이트 테스트는 창 안·밖 두 시각으로(09:04/09:05/09:30/09:31, `kstMinutesOfDay(now)` 주입) — 로컬·CI 시각에 따라 붉어지지 않게(메모리 「벽시계 게이트」) |
| F8 | kst.ts 규약 — 수정한 5개 파일에 `new Intl.DateTimeFormat`·`toLocaleString`·`getHours()` 0 |
| F9 | ⑥ 진입 기록 기준선 정규화: donchian `donchian_high`·VCP `base_high`·etf `line` 이 「기준선」 칸에, `change_rate=0` 전략은 「+0%」 대신 `—` |

### 8.2 tester (통합·실측, 운영 접속은 메인 세션이)

- **T1** 배포 뒤 첫 장 전(또는 지금 읽기 전용 GET): `/api/strategies` 로 8전략 `enabled`·`weight`·`buy_paused`·`shadow_mode` 를 읽어 화면 배지와 대조. 특히 **momentum**(C4).
- **T2** 10-12(월) 09:05~09:30: etf·donchian 패널이 「멈춤 + 풀리면: ○○」 을 보이는지, `paused_skips` 수가 `[buy_paused_skip]` 로그 종목 수와 같은지.
- **T3** VB 섀도: `shadow_buys` 종목 = 그날 `[shadow_buy] strategy=volatility_breakout` 로그 종목.
- **T4** 보유 종목 실효 손절선: 패널 값 = 잔고 화면 손절가 칸 = exit-lines `stop_price`(세 곳 같은 값).
- **T5** 21:00 뒤 기준일 머리말이 다음 거래일·「저녁 미리보기(잠정)」으로 바뀌는지, 다음 날 07:46 에 「아침 준비」로 돌아오는지.
- **T6** 새 화면 칸은 값이 실제로 찍히는지까지(메모리 「검사 초록 + 배포 성공인데 빈 칸」 사고) — 보유 종목의 사다리·카운트다운이 **보유 전부**에서 비지 않는지.

---

## 9. MSW 고정 데이터 — 실제 키 목록

`frontend/src/test/handlers.ts` 의 `/trading/status` 에 아래 키를 가진 전략 fixture 를 더한다(값은 합성, **키 이름은 백엔드 그대로**).

| 전략 | `targets[t]` 키 | `scan_stats` 키 | `buy_signals[i]` 키 |
|---|---|---|---|
| etf_trend | `prev_close`·`target_price` | `universe`·`candidates`·`clusters`·`last_run_at` | `ticker`·`name`·`price`·`open_price`·`line`·`atr`·`change_rate`·`time` |
| donchian_swing | `prev_close`·`atr`·`ema60`·`donchian_high`·`k`·`target_price`·`open_price`·`target_offset`·`open_confirmed` | `universe_union`·`universe_candidates`·`universe_filtered`·`candle_fetch_ok`·`donchian_pass`·`ema_uptrend_pass`·`volume_pass`·`atr_pass`·`final_prepared`·`last_run_at` | `ticker`·`name`·`price`·`donchian_high`·`atr`·`change_rate`·`time` |
| vcp_breakout | `base_high`·`base_low`·`atr14`·`ema50`·`name`·`prev_close`·`stop_line`·`volume_threshold`·`bought_today`·`in_cooldown`·`cooldown_until` + VB 호환 5키 | 위 공통 + `mcap_pass`·`trend_filter_pass`·`base_pass`·`pullback_pass`·`volume_contraction_pass`·`vol_gate_pass`·`vol_gate_reject_ext`·`vol_gate_no_data`·`latch_armed_count` | `ticker`·`name`·`price`·`base_high`·`atr`·`change_rate`·`time` |
| bull_flag_breakout | `pole_start`·`pole_high`·`flag_high`·`flag_low`·`atr14`·`name`·`prev_close`·`stop_line`·`measured_target`·`volume_threshold`·`bought_today`·`in_cooldown`·`cooldown_until`·`breakout_seen_at`·`retention_minutes` + VB 호환 5키 | 공통 + `pole_pass`·`flag_pass`·`volume_contraction_pass`·`atr_pass`·`breakout_seen_count`·`breakout_retreat_count` + 관문 카운터 | `ticker`·`name`·`price`·`flag_high`·`target_price`·`atr`·`change_rate`·`time` |
| kojiro | `name`·`prev_close`·`atr`·`stage`·`ema_s`·`ema_m`·`ema_l`·`atr_ratio`·`sector` + VB 호환 | `universe_union`…`band_pass`·`stage_valid_pass`·`stage1_uptrend_pass`·`strict_entry_pass`·`final_prepared` | `ticker`·`name`·`price`·`stage`·`atr`·`change_rate`·`time` |
| volatility_breakout | 보드별 `{k, target_price, open_price, target_offset, boards{}, open_confirmed}` | `universe_candidates`·`universe_filtered`·`candle_fetch_ok`·`k_value_computed`·`final_prepared` 외 | `ticker`·`name`·`price`·`target_price`·`k`·`board`·`change_rate`·`time` |

공통 전략 키 = `name`·`enabled`·`weight`·`params`(`buy_paused`·`shadow_mode`·`max_positions`·`market_unit_mode`·`entry_start`/`entry_end`(VCP·BFB)·전략 문턱 키)·`tradable_boards`·`positions`·`pending_buys`·`position_tickers`·`total_investment`·`daily_realized_pnl`·`buy_disabled`·`buy_signals`·`positions_detail{name,buy_price,quantity,high_since_buy,buy_date,is_next_day}`·`pending_buy_tickers`·`scanned_tickers`·`scanned_count`·`targets`·`scan_stats`·`invested_amount`·`min_weight`.
`/strategies/monitor` fixture 는 §3.2 모양 그대로, `/balance/exit-lines` 는 `{running, as_of, items:[{strategy_id,ticker,stop_price,stop_source,target_price,target_source,buy_price,quantity,high_since_buy,buy_date,order_no,entry_atr,kk_armed,kk_arm_price}]}`.

---

## 10. 결정이 필요한 것

사용자 결정 필요 = **없음**(읽기 전용 화면, 매매 행위 무변경).
팀장 판단 2건: (1) 상세 패널 배치(§2.1 권고 = 전폭) (2) `Strategies.tsx` 배지 교체 포함 여부(C6). 그리고 C4(momentum 이 켜져 있고 멈춤이 아니면) 실측 결과를 팀장에게 바로 알린다.
