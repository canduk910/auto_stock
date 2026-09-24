# cycle351 — 피라미딩 단계 1(S0 과거 재현) + 단계 2(S1 야간 가상 기록) 명세 (team-leader, 2026-09-25)

사용자 결정(2026-09-24): 설계안 D-1~D-5 **권고대로** — D-1 첫 트랜치 2/3u · D-2 K=2.0 유지 + 「1주 폴백 랏에는
사다리 금지」 · D-3 kojiro 실매매 대상 + donchian 가상 기록만 · **D-4 = 단계 1 + 단계 2** · D-5 배관은 단계 2 문턱 뒤.

- 설계안 = `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md` (§3 사다리 · §4 손절선 · §8 단계 · §10 귀인)
- 자문 = `_workspace/domain_consult/cycle345_three_stage_pyramiding.md` (Q6 shadow · 후속 검증 권고)
- 🔴 **매매 행위 무변경.** 8영역 · `scheduler.py` · 전략 7파일(`kojiro.py`·`donchian_swing.py` 포함) · `strategy_base.py` **무접촉**.
  마이그레이션 없음(JSONB). KIS 호출 0. DB 는 **SELECT 만**.
- 바뀌는 프로덕션 파일 = **딱 둘** — 신규 leaf `src/engine/pyramid_shadow.py` · `src/engine/log_metrics_collector.py`(끝 키 1개).
  둘 다 `src/` 라 배포 모드는 **full**(backend 재시작). 커밋·push 는 이 사이클 밖(메인 세션 몫).

---

## 0. 구성 한눈에

```
[20:05 스냅샷 / 20:20 번들 / 21:30 완전판]  ← 셋 다 collect_daily_log_metrics 를 부른다(기존)
        │
        ▼
log_metrics_collector.collect_daily_log_metrics(target_date)
   … 기존 10키 무변경 …
   "pyramid_shadow": await wait_for(_collect_pyramid_shadow(target_date), 30s)   ← 신규 11번째(맨 끝) 키
        │   (registry 메모리에서 kojiro·donchian params 사본 + 예산만 읽어 넘긴다)
        ▼
pyramid_shadow.build_pyramid_shadow(target_date, params_by_sid=, budget_by_sid=)   ← 신규 leaf (async 어댑터)
   ├─ get_trade_pairs(strategy=sid)  → open 페어 + 그날 청산된 페어       (SELECT)
   ├─ get_recent_daily(ticker, 400)  → 일봉 (bas_dd ≤ target_date)        (SELECT)
   ├─ 진입 N 재계산 (매수일 **이전** 봉만)
   └─ overlay_ladder(...)  ← 순수 코어. S0 스크립트도 이 함수를 import 해 같은 모형을 쓴다
        → records + summary  → metrics["pyramid_shadow"]
        → 청산 확정 레코드마다 [pyramid_shadow_close] WARNING (하루 1회/포지션)
```

---

## 1. 가상 사다리 모형 (순수 코어 `overlay_ladder`) — 「앵커 위 덧씌우기」

**핵심 결정 — 사다리는 실제 청산(앵커)보다 늦게 나가지 않는다.** 실제 포지션의 청산(날짜·가격·시각)을
앵커로 두고, 그 위에 **사다리만의 추가 매수와 사다리만의 더 조인 손절선**만 모형화한다. 이렇게 하면
`virtual_R − actual_R` 이 모형 오차(일봉으로 샹들리에·스테이지3·시간청산을 흉내 낸 오차)가 아니라
**사다리 효과만** 잰다. 설계 §4-1 에서 1랏과 **공유**되는 선(샹들리에·스테이지3·시간청산·채널)은
앵커가 이미 담고 있다. 대가 = 「사다리가 1랏보다 오래 버티는 경우」(평단 기준 본전 승격이 늦게 켜짐)는
S1 이 못 본다 — 그것은 S0 의 「자유 모드」가 잰다(§3).

### 1-1. 입력

| 인자 | 뜻 |
|---|---|
| `bars` | `(date, open, high, low, close)` 오름차순 시퀀스. `entry_idx` 부터 사용 |
| `entry_idx` | 첫 매수일 봉 인덱스 (D0) |
| `entry_price` `E` | 실제 첫 페어 매수 평단 (1트랜치 체결가로 간주) |
| `n_entry` `N` | 진입 N — **고정**. 추가 눈금·세트선·본전 승격 임계에 쓴다 |
| `cfg: LadderConfig` | `step_n`(추가 간격 N 배수) · `sizes`(트랜치 크기, 유닛 u 배수, 길이 = 최대 트랜치 수) · `gap_skip_mult`(1.05) |
| `stop_atr` | 2.0 — 세트선 배수이자 **R 단위**(`r_unit = stop_atr × N`, 1u 랏 1주당) |
| `hard_stop_pct` | 평단 기준 backstop % (kojiro −8.0 · donchian `turtle_backstop_pct` −9.0) |
| `be_mult` | 평단 본전 승격 배수 (1.5, 0 = 끔) |
| `be_atr` | 본전 승격 임계용 ATR 시퀀스(`bars` 와 같은 길이, `be_atr[d-1]` 을 읽는다) 또는 `None`(= `N` 사용). kojiro = live Wilder ATR 시퀀스, donchian = `None` |
| `no_add` | `bars` 와 같은 길이의 bool — 그날 추가 금지(§1-3 ③). 호출자가 `no_add_flags(dates)` 로 만든다 |
| `anchor_idx` / `anchor_price` | 실제 청산 봉 인덱스와 가격. 보유 중이면 둘 다 `None` |
| `anchor_add_allowed` | 앵커 날 추가 허용 여부. S1 = 실제 매도 시각 ≥ 09:30 KST · S0 = 1랏 청산이 장중(스테이지3·시가 갭 청산이면 False) |

### 1-2. 하루 처리 순서 (`d = entry_idx+1 …`, 보수 순서 = 사다리에 불리하게)

상태: `fills=[(entry_idx, E, sizes[0])]`, `last=E`, `k=1`(트랜치 수), `hsb=high[entry_idx]`(전일까지의 고점), `avg` = `Σsize×price ÷ Σsize`.

**사다리 전용 선** (`k ≥ 2` 일 때만 켠다 — `k == 1` 이면 사다리 = 1랏 × 2/3 이라 앵커와 똑같이 나간다):
```
line = max( last − stop_atr × N                               # 세트선 (마지막 체결가, N 고정)
            avg  × (1 + hard_stop_pct/100)                    # 평단 backstop
            avg  if be_mult>0 and hsb ≥ avg + be_mult × A     # 평단 본전 승격, A = be_atr[d-1] 또는 N
          )
```
(`avg − stop_atr × N` 은 `last ≥ avg` 라 세트선에 항상 덮여 생략한다.)

1. **손절 먼저** — `k ≥ 2` 이고 `open ≤ line` → 시가 청산(`kind="gap"`). 아니고 `low ≤ line` → `line` 에 청산
   (`kind` = line 을 만든 항: `"set_line"` · `"avg_backstop"` · `"avg_breakeven"`).
   앵커 날이면 청산가 = `max(이 청산가, anchor_price)`, 앵커가 더 높으면 `kind="anchor"`.
2. **추가** (청산되지 않았고 `k < len(sizes)` 이고 아래 게이트 전부 통과할 때만, 같은 날 여러 번 가능 = while):
   - ① `d > entry_idx` (D0 금지) ② `not no_add[d]` ③ 앵커 날이면 `anchor_add_allowed`
   - `level = last + step_n × N`
   - ④ `open ≥ level × gap_skip_mult` → **그날 추가 전부 없음**(루프 탈출)
   - ⑤ `high ≥ level` 이면 체결가 `px = max(level, open)` → `fills += (d, px, sizes[k])`, `last = px`, `k += 1`, `avg` 갱신
   - ⑥ 추가 직후 새 `line` 으로 `low ≤ line` 이면 그 `line` 에 청산(`kind="stop_after_add"`, 앵커 날이면 `max(·, anchor_price)`)
3. **앵커 날** 인데 아직 안 나갔으면 `anchor_price` 에 청산(`kind="anchor"`).
4. 날 끝에 `hsb = max(hsb, high[d])` (본전 승격은 **다음 날부터** 켜진다).
5. `bars` 가 끝날 때까지 안 나갔고 앵커도 없으면 **보유 중** — 마지막 종가로 평가(`kind="open"`).

### 1-3. 물타기 금지 (셰도에서는 구조로 성립 — 테스트로 고정)

- 추가 눈금은 `last + step_n × N` 뿐이고 `last` 는 체결 때마다 오르기만 한다 → 가격이 내려간 자리에서 사는 경로가 없다.
- D0 금지 · 추가 금지일 · 갭 스킵 · 손절 먼저 네 게이트는 각각 돌연변이로 붉어져야 한다(§5).

`no_add_flags(dates)` (순수 헬퍼): `flag[i] = (dates[i+1] − dates[i]).days ≥ 3`(다음 거래일까지 2일 이상 빈다 =
금요일·연휴 전날). **마지막 봉**은 다음 거래일을 모르므로 `dates[-1].weekday() == 4`(금) 이면 True, 아니면 False
(평일 휴장 전날은 셰도에서 판정 불가 — KIS `chk-holiday` 호출 금지. 실매매 단계는 설계 §3-3 대로 `next_trading_day`).

### 1-4. 출력 (dict)

| 키 | 뜻 |
|---|---|
| `tranches` | 도달 트랜치 수 `k` |
| `fills` | `[(idx, price, size), …]` |
| `avg` | 최종 가상 평단 |
| `exit_idx` · `exit_price` · `exit_kind` | 가상 청산 (`"open"` 이면 `exit_idx` = 마지막 봉, 가격 = 마지막 종가) |
| `virtual_R` | `Σ size × (exit_price − price) ÷ r_unit` |
| `base_R` | 1랏: `(앵커가 또는 마지막 종가 − E) ÷ r_unit` — S1 에서는 곧 `actual_R` |
| `set_stop` | `k ≥ 2` 면 `last − stop_atr × N`, 아니면 `None` |
| `fixed_stop` | `E − stop_atr × N` (1랏 고정 2N 선 — 비교용) |
| `killed` | `k ≥ 2` ∧ 사다리 전용 선으로 나감(`kind ∈ {gap, set_line, avg_backstop, avg_breakeven, stop_after_add}`) ∧ (`anchor_idx is None` 또는 `exit_idx < anchor_idx`) → 1, 아니면 0. 「1랏이면 살았을 것을 사다리 선이 털었다」 |
| `peak_risk_R` | 트랜치가 늘 때마다 잰 `Σ size × (price − 그 시점 세트선) ÷ r_unit` 의 최댓값(`k=1` 이면 세트선 대신 `fixed_stop`). 설계 §4-3 의 「손절 기준 위험」 이라 backstop·본전 승격 항은 넣지 않는다. C*(1N·2/3×3)면 **1.0** |

모든 값은 유한수 — 비유한(NaN/inf) 입력(예: `N ≤ 0`)은 `ValueError` 로 거부하고 어댑터가 그 레코드를 `error` 로 남긴다.

### 1-5. 셰도가 쓰는 사다리 = C* 하나 (상수, DB 키 아님)

```python
LADDER_C = LadderConfig(step_n=1.0, sizes=(2/3, 2/3, 2/3), gap_skip_mult=1.05)   # 설계 §3-3 · D-1
```
롤백 다이얼(`pyramid_*` 키, 설계 §9)은 단계 4 의 것이다 — **이 사이클은 새 파라미터 키를 만들지 않는다**
(`DEFAULT_PARAMS` 신규 키 = 매매 행위 결정 대상).

---

## 2. S1 야간 가상 기록 — 어댑터 `build_pyramid_shadow`

### 2-1. 대상

- 전략 = `("kojiro", "donchian_swing")` (D-3).
- `src.db.trade_history.get_trade_pairs(strategy=sid)` 의 페어 중
  - `status == "open"` ∧ `buy_date ≤ target_date` (보유 중)
  - `status == "closed"` ∧ `sell_date == target_date` (그날 청산)
- 그 밖(다른 날 청산, 다른 전략)은 넣지 않는다.

### 2-2. 입력 재료 (전부 읽기 전용)

| 재료 | 출처 |
|---|---|
| 일봉 | `src.db.stock_master_daily.get_recent_daily(ticker, 400)` → `bas_dd ≤ target_date` → 오름차순. 가격 컬럼 `open_price/high_price/low_price/close_price` |
| 진입 N (kojiro) | 매수일 **이전** 봉 최대 100개(= `KOJIRO_FETCH_DAYS`) → `kojiro_indicators.atr(df, params["atr_period"]).iloc[-1]` (Wilder) |
| 진입 N (donchian) | 매수일 **이전** 봉 → `StrategyBase._atr(highs, lows, closes, params["atr_period"])`(최신순, SMA) → `float(int(·))` (`_rederive_entry_atr` 와 같은 절삭) |
| `be_atr` (kojiro) | 전 봉 Wilder ATR 시퀀스(`kojiro_indicators.atr`) — `be_atr[d-1]` 을 쓴다 / donchian = `None` |
| 규칙 파라미터 | 콜렉터가 넘긴 `params_by_sid[sid]`(레지스트리 메모리 사본). kojiro = `stop_atr`·`hard_stop_pct`·`breakeven_promote_atr`·`atr_period`·`risk_pct` / donchian = `stop_atr`·`turtle_backstop_pct`·`breakeven_promote_atr`·`atr_period`·`risk_pct`. 없거나 읽기 실패면 폴백 상수(아래) + `params_source="fallback"` |
| 예산 | 콜렉터가 넘긴 `budget_by_sid[sid]`(= `strat.state.total_investment`, 0 이하면 `None`) |

폴백 상수(2026-09-25 운영 DB 조회값과 같다): kojiro `stop_atr 2.0 · hard −8.0 · be 1.5 · atr_period 20 · risk_pct 0.005` /
donchian `stop_atr 2.0 · backstop −9.0 · be 1.5 · atr_period 14 · risk_pct 0.01`.

- 🔴 **진입 N 은 매수일 봉을 넣지 않는다**(돌파 당일 변동이 N 을 부풀려 세트선·눈금이 넓어진다 = `_rederive_entry_atr` 계약과 같다).
- 매수일 봉이 없으면 `error="no_entry_bar"`, N 이 0 이하·비유한이면 `error="no_atr"` 로 그 레코드만 남기고 계속한다.
- 앵커(청산 페어): `anchor_idx` = `sell_date` 봉 인덱스, `anchor_price` = 페어 `sell_price`,
  `anchor_add_allowed = sell_time ≥ "09:30:00"`. `sell_date` 봉이 아직 없으면(20:30 적재 전) **앵커 없이** 마지막 봉까지
  돌리고 `final=0`.

### 2-3. 레코드 (`records` 의 원소, 키 순서 고정)

`strategy, ticker, buy_date, entry_price, n_entry, r_unit, status("open"|"closed"), exit_date, exit_price, exit_time,
bars_through, final(0|1), actual_R, virtual_R, delta_R, tranches, add_dates, add_prices, set_stop, fixed_stop,
v_exit_date, v_exit_kind, killed(0|1), tranche_shares, eligible(0|1|None), add_stage, add_macd, params_source, error`

- `actual_R` = 청산이면 `(sell_price − E) ÷ r_unit`, 보유 중이면 `(마지막 종가 − E) ÷ r_unit`. `delta_R = virtual_R − actual_R`.
- `final` = 청산 ∧ `bars_through ≥ sell_date`. 보유 중은 항상 0.
- `tranche_shares` = `floor(sizes[0] × 예산 × risk_pct ÷ N)`, `eligible = 1 if tranche_shares ≥ 2 else 0`, 예산 모르면 둘 다 `None`
  (설계 §3-3 「첫 트랜치 2주 미만이면 사다리 없이 오늘처럼」·D-2 「1주 폴백 랏 사다리 금지」의 판정 재료. **`virtual_R` 은 적격과
  무관하게 계산**한다 — S0 의 Δ 가 적격과 무관한 모양 비교라 부호 비교가 성립하려면 같아야 한다).
- `add_stage` / `add_macd` = 추가 체결일 `d` 마다 **d−1 완성봉**의 kojiro 스테이지(int) · `"gc"`(그 봉에서 macd3 가 시그널을 상향 교차) /
  `"up"`(macd3 > sig) / `"dn"`. `kojiro_indicators.enrich` 를 그 종목 전 봉에 한 번 돌려 얻는다(두 전략 공통, 실패 시 `None`).
  **기록만** 한다(설계 §3-3 「MACD 는 트리거에 쓰지 않는다」).
- 부동소수는 4자리 반올림. 🔴 **`json.dumps(result, allow_nan=False)` 가 항상 성공해야 한다** — `daily_log_reports.metrics` 는
  JSONB 라 NaN 하나가 21:30 리포트 INSERT 전체를 깨뜨린다. 비유한은 `None`.
- 레코드 상한 50개(넘으면 앞 50개 + `summary.truncated=1`).

### 2-4. 반환 (`metrics["pyramid_shadow"]`)

```json
{"version": 1,
 "target_date": "YYYY-MM-DD",
 "ladder": {"step_n": 1.0, "sizes": [0.6667, 0.6667, 0.6667], "gap_skip_mult": 1.05},
 "summary": {"open_n":, "closed_n":, "closed_final_n":, "killed_n":, "eligible_n":,
             "delta_R_mean_closed_final": (없으면 null), "extra_notional_won":, "gap_stress_won":,
             "errors_n":, "truncated": 0|1},
 "records": [...]}
```
- `extra_notional_won` = 보유 중 ∧ `tranche_shares` 아는 레코드의 **2트랜치 이후 가상 추가분 명목** Σ(`tranche_shares × 추가 체결가`).
  (설계 §5 「예산 선점」의 재료. 「다음 날 신규 진입을 굶긴 횟수」(`budget_starved`) 자체는 **이 사이클 보류** — §6)
- `gap_stress_won` = 보유 중 가상 사다리 명목(`tranche_shares × 트랜치 수 × 마지막 종가`) Σ × 10% (설계 §4-3 「표시만」).

### 2-5. 마커 — `[pyramid_shadow_close]` WARNING

- 조건: 레코드가 `status="closed"` ∧ `final=1` ∧ `target_date == 오늘(KST)`. 과거 날짜 호출(수동 재실행)은 **찍지 않는다**.
- 모듈 전역 `KstDailyEmitCap` 키 = `f"{strategy}:{ticker}:{buy_date}"` — 20:05·20:20·21:30 세 호출 중 **처음 확정된 한 번만**.
  (실무상 매일 21:30 — 그날 봉은 20:30 에 적재된다.)
- 형식(한 줄):
  `[pyramid_shadow_close] strategy= ticker= buy_date= exit_date= v_exit_kind= actual_R= virtual_R= delta_R= tranches= add_dates= set_stop= fixed_stop= killed= tranche_shares= eligible= add_stage= add_macd=`
- WARNING 인 이유(정정, 독립 검증 지적 #23) — 애초에 INFO 든 WARNING 이든 이 마커는 21:30
  `top_patterns` 에 오르지 않는다(그 패스가 로그를 읽는 시점은 이 마커가 나가기 **전**이라
  구조적으로 도달 불가). WARNING 의 실효는 **`system_logs` 30일 보존**(INFO 는 2일)뿐이다 —
  청산 표본이 20건(§8 문턱)까지 쌓이는 데 2일 보존은 부족하고 30일은 충분하다. 표본의 정본은
  어차피 `daily_log_reports.metrics.pyramid_shadow.records`(영구 JSONB)다.
- 실패 흔적은 DEBUG `[pyramid_shadow_error]` (데이터 마커와 접두를 가른다 — cycle349 선례).

### 2-6. 콜렉터 배선 (`log_metrics_collector.py`)

- `_collect_pyramid_shadow(target_date)`: lazy import `trading_scheduler`, 두 전략의 `dict(strat.config.params)` 사본과
  `int(strat.state.total_investment)` 를 모아(실패·부재 = `None`) leaf 에 넘긴다. **읽기만** — 레지스트리·전략 상태 무변경.
- `collect_daily_log_metrics` 끝에 `"pyramid_shadow"` 키 **1개를 맨 끝(11번째)** 에 추가. 기존 10키의 값·순서 **byte 동일**.
- `asyncio.wait_for(…, timeout=30.0)` + `except Exception` → 그 키만 `None`(never-raise, 나머지 metrics 무영향).
  30초 상한 = 21:30 파이프라인(LLM 호출·INSERT)을 셰도가 붙잡지 못하게.
- `log_analysis_engine.py` · `daily_metrics_snapshot.py` · `routes/log_reports.py` **무접촉**(콜렉터를 통해 자동으로 실린다).

---

## 3. S0 과거 재현 — 스크립트(프로덕션 코드 아님, domain-expert 담당)

leaf 가 Green 이 된 **뒤** 착수한다(같은 코어를 import 해야 S0 Δ 와 S1 Δ 의 정의가 같다).

- 파일: `_workspace/domain_consult/cycle351_pyramid_s0_replay.py` · 결과 `_workspace/domain_consult/cycle351_pyramid_s0_replay.md`
- 실행: EC2 backend 컨테이너(`/app`) 안. 🔴 운영 이미지에는 새 leaf 가 없다 → `src/engine/pyramid_shadow.py` 를 컨테이너 `/tmp` 로
  복사해 그 파일에서 `overlay_ladder`·`no_add_flags`·`LadderConfig` 를 import 한다. 실행 뒤 원격 임시 파일 삭제.
- DB 는 SELECT 만. **20:00~21:35 KST 금지**. 실행 전 `free -m` 확인, 일봉은 100종목 청크로(cycle346 방식).
- 표본 A(문턱 판정용) = kojiro 진입 **대리 조건**(cycle345 `ladder.py` 와 같은 정의 — 바꾸면 이유를 적는다).
  1랏 기준선 = kojiro 청산 규약 일봉 재현(cycle346 `simulate` 방식: hard −8% · 2ATR tighten-only floor(D-1 ATR) · 본전 승격 1.5 ·
  스테이지3 다음 날 시가 · 2.5ATR 샹들리에 · 최대 60봉).
  - **앵커 모드** = 1랏 기준선 청산을 앵커로 leaf `overlay_ladder` 를 돌린다 → **S1 과 같은 정의의 Δ**(S1 문턱의 비교 대상)
  - **자유 모드** = 스크립트 자체의 전체 모의(평단 기준 kojiro 규약 + 세트선, 설계 §4-1 그대로) → 설계에 충실한 Δ
- 격자(설계 §8): 간격 {½N, 1N} × 트랜치 {2, 3} × 비율 {균등, 체감 4:2:1} × 첫 트랜치 {1/3, 2/3, 1} — 두 모드 모두.
- 지표: n · 평균 R · 중앙 · 승률 · P(≤−1R) · 하위 5% 평균 · 최대손실 · 평균 트랜치 · 2·3번째 도달률 · 위험 최고치 배수 ·
  **Δ평균R(짝) 95% 구간 — iid 부트스트랩과 진입일 클러스터 부트스트랩 둘 다** · 1랏 이익→손실 전환율 · `killed` 비율 ·
  왕복 비용 0.25% 차감 Δ · 위험 정규화 Δ.
- 표본 B(참고) = kojiro·donchian **실체결 페어 전부**에 S1 과 똑같이(실제 청산 앵커) 소급 적용 — 「S1 을 과거에 켰다면」.
  문턱의 「S1 청산 ≥ 20건」은 **앞으로 쌓이는 표본**이라 B 로 대신하지 않는다(참고로만 표시).
- 연속성: cycle345 `ladder.py`(원본, 세션 스크래치패드)를 **무수정**으로 오늘 데이터에 다시 돌려 855건 · +0.047 과 대조.
- 독립 검산: 앵커 모드 C* 를 스크립트 안에서 **따로 구현**해 leaf 결과와 레코드 단위로 일치율을 보고한다.
- 문턱 판정표(설계 §8 단계 2→3): S0 표본 ≥ 1,500 · C* Δ 하한 > 0(클러스터 기준) · S0 `killed` 비율(→ S1 상한 = 그 2배).

---

## 4. 테스트 명세 (tdd-engineer — Red 먼저)

파일(제안): `tests/unit/engine/test_cycle351_pyramid_shadow_core.py` · `tests/unit/engine/test_cycle351_pyramid_shadow_collect.py` ·
`tests/unit/ast/test_cycle351_pyramid_shadow_scope.py` · 골든 `tests/fixtures/cycle351/collector_golden_head.json`.

### 4-1. 골든 (확장 **전** 코드로 도출 — Green 착수 전에 만든다)

- 기존 `isolated` 픽스처 수준의 결정적 입력으로 **HEAD(`0a7752a`)** `collect_daily_log_metrics` 를 돌려 기존 10키를 JSON 으로 저장.
- Green 뒤: 같은 입력의 결과에서 `pyramid_shadow` 를 뺀 10키가 골든과 **완전히 같다** + 키 순서 = 기존 10키 + `"pyramid_shadow"`.
- 골든 생성 스크립트 경로와 base sha 를 테스트 docstring 에 적는다.

### 4-2. 코어 (합성 봉, `E=10000 · N=500 · stop_atr=2 · hard=−8 · be=1.5 · C*`)

| # | 시나리오 | 기대 |
|---|---|---|
| C1 | D1 고가 10,500 · D2 고가 11,000 · D3 고가 11,500 · 앵커 D5 | 3트랜치(10000/10500/11000), 4번째 없음, `set_stop=10000`, `avg=10500`, `virtual_R` 손계산과 일치 |
| C2 | D1 10,500 추가 → D2 저가 9,400 (앵커 D6) | D2 에 `set_line` 9,500 청산, `killed=1`, `fixed_stop=9000` |
| C3 | 9,500 까지 하락 후 10,250 회복 | 추가 0 (물타기 경로 부재) |
| C4 | D0 고가 ≥ 10,500 | D0 추가 0 |
| C5 | 추가 조건 충족일이 `no_add=True` | 그날 추가 0, 다음 조건 충족일에 추가 |
| C6 | 시가 ≥ 10,500×1.05 | 그날 추가 0 / 시가 10,600(<1.05배) 이면 10,600 체결 |
| C7 | 앵커 날: 사다리 선 적중가 > 앵커가 → 사다리 선 청산 / 반대면 `kind="anchor"` · `anchor_add_allowed=False` 면 앵커 날 추가 0 |
| C8 | 2트랜치 후 `hsb ≥ avg+1.5N` 다음 날 저가 ≤ avg | `avg_breakeven` 청산, 승격은 **다음 날부터**(같은 날 고가로 켜지지 않음) |
| C9 | 고ATR(N=600, 6%) 2트랜치 | `avg_backstop` 이 세트선보다 높아 그 선에서 청산 |
| C10 | `be_atr` 를 크게 바꿔도 | 추가 눈금·세트선 **불변**(N 고정) — 본전 승격 임계만 바뀐다 |
| C11 | C* 3트랜치 | `peak_risk_R == 1.0`(±1e-9), 1트랜치만이면 `0.6667` |
| C12 | 앵커 없음 | 마지막 종가 평가, `exit_kind="open"`, `killed=0` (사다리 선 적중 시 `killed=1`) |
| C13 | 추가 직후 같은 봉 저가 ≤ 새 선 | `stop_after_add` |
| C14 | `no_add_flags` | 금→월 True, 월→화 False, 수(목 휴장)→금 False(1일 공백), 마지막 봉 금요일 True / 목요일 False |

### 4-3. 어댑터·콜렉터

| # | 시나리오 | 기대 |
|---|---|---|
| A1 | kojiro 진입 N | 매수일 이전 ≤100봉 Wilder — 매수일 봉을 넣은 값과 **다르다**(돌연변이 탐지) |
| A2 | donchian 진입 N | SMA14 `float(int(·))` |
| A3 | 범위 | open 페어 + `sell_date == target_date` 청산만, 다른 날 청산·다른 전략 제외 |
| A4 | `final` | `sell_date` 봉 있으면 1(앵커 적용), 없으면 0(앵커 없이) |
| A5 | 마커 | `final=1` ∧ 오늘 → WARNING 1회, 같은 날 두 번째 호출 0회, 과거 날짜 0회, `final=0` 0회 |
| A6 | never-raise | `get_trade_pairs` 예외 → 그 키 `None`, 나머지 10키 무영향 · 한 종목 일봉 예외 → 그 레코드만 `error` |
| A7 | JSON | 퇴화 봉(ATR 0·가격 0)을 섞어도 `json.dumps(allow_nan=False)` 통과 |
| A8 | 적격 | `tranche_shares = floor(2/3 × 예산 × risk_pct ÷ N)`, ≥2 → 1, 예산 `None` → `None` |
| A9 | 파라미터 | 레지스트리 값 우선, 부재 → 폴백 + `params_source="fallback"` |
| A10 | 시간 상한 | leaf 가 30초 넘게 걸리면 그 키 `None`(테스트는 상한을 monkeypatch 로 줄여 빠르게) |
| A11 | 키 순서 | 11키, `pyramid_shadow` 맨 끝 — `EXPECTED_METRIC_KEYS` 3곳(`test_cycle249_collect_metrics.py` · `test_cycle259_log_metrics_collector.py` · `test_cycle349_vcp_breakout_events_metrics.py` 에 있으면) 갱신 |
| A12 | 레지스트리 무변경 | 호출 전후 `config.params` · `state` 동일(사본만 넘긴다) |

### 4-4. 범위 가드 (AST)

- `pyramid_shadow` 를 import 하는 프로덕션 모듈 = `log_metrics_collector.py` **하나뿐**.
- leaf 는 `order_engine` · `risk` · `scheduler` · `strategy_registry` · `session` · `scanner` · `src.api.order` · `src.api.base` ·
  `src.realtime` · `src.auth` 를 import 하지 않는다. `pg.execute` · `INSERT/UPDATE/DELETE` 문자열 0.
- leaf 모듈 최상단 import 는 **표준 라이브러리 + `src.engine.daily_emit_cap`** 까지(S0 스크립트가 컨테이너 `/tmp` 사본을 import
  할 수 있어야 한다). pandas·DB·`kojiro_indicators`·`strategy_base` 는 함수 안 지연 import.
- 기존 sha/digest 핀(`test_cycle287_ast_scope.py` 의 `_SRC_TREE_DIGEST`·파일 수 `src/engine` 77→78 등)은 **이 사이클이 정당하게 움직이는
  두 파일** 때문에 갱신한다 — 갱신 사유 주석은 기존 관례(직전 값 기록)를 따른다. 8영역·`scheduler.py`·전략 파일 핀은 **움직이면 안 된다**.

---

## 5. 돌연변이 (tester, ≥ 6 — 각각 붉어져야 한다)

M1 추가 부등호 `high ≥ level` → `>` 또는 기준을 `last` 대신 `avg` · M2 D0 가드 삭제 · M3 `no_add` 무시 · M4 갭 스킵 삭제 ·
M5 세트선 기준을 `last` 대신 `E`(첫 진입가) · M6 세트선·눈금에 `be_atr`(live) 사용 · M7 손절 먼저 ↔ 추가 먼저 순서 교환 ·
M8 앵커 날 `max` → `min` · M9 마커 `final` 게이트 삭제 또는 cap 삭제 · M10 진입 N 에 매수일 봉 포함 · M11 청산 페어 날짜 필터 삭제 ·
M12 비유한 정리 삭제(NaN 누출).

---

## 6. 이 사이클 밖 (보류 — 사유)

| 항목 | 사유 |
|---|---|
| `budget_starved`(추가가 다음 날 신규 진입을 굶긴 횟수) | 그날 후보·슬롯·예산 경합 재현이 필요 = 셰도 한 층 더. `extra_notional_won` 로 재료만 남긴다 |
| 화면(프론트) 표시 | 요청 범위 밖. JSONB 와 WARNING 으로만 본다 |
| S0 주 1회 자동 실행 | 루틴(schedule) 생성 = 외부 설정 변경이라 승인 대상. 스크립트는 재실행 가능하게만 |
| donchian 대리 진입 S0 | donchian 은 셰도 전용(D-3). 실체결 소급(표본 B)으로 대신한다 |
| 단계 3 배관(P-1·P-1b·카드 E·카드 C·영속화) | D-5 — 단계 2 문턱 뒤 |
