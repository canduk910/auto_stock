# U-C — D3 고지로 후보 순위 성분 원설계 복원 (조사·명세 초안)

- 작성 2026-09-10 · cycle273 U-C 조사 담당
- 범위 = **읽기 전용**. `src/**`·`tests/**`·`frontend/**` 무변경. 이 문서 + scratchpad 시뮬레이션이 전부다.
- 사용자 결정(2026-09-10 목 19:5x) = **"3. D3 고지로 순위계산을 원래 설계로 복원 — 복원 진행하자."**
  보고서 §9 제안 = 카드 ③ **A(둘 다 복원)** + shadow 관측 `[kojiro_band_observe]` **"같이"**.
- 정본 = `_workspace/domain_consult/kojiro_band_width_floor_filter_20260910.md` §3.3·§4.3·§7 ·
  `_workspace/reports/2026-09-10_thursday_autonomous_work.md` §D3 ·
  `_workspace/kojiro_ma/전략설계서_고지로_대순환_자동매매.md` §9④ ·
  `_workspace/kojiro_ma/kojiro/screener.py`(레퍼런스 구현) ·
  `_workspace/00_leader_trading_rules.md:31` · `src/engine/strategies/CLAUDE.md:79`
- 기준 트리 = **HEAD `a10191b`**. (워킹트리에 cycle272 의 작업이 보여도 이 문서는 `git show HEAD:` 로만 읽었다.)

---

## 0. 한눈에

| # | 항목 | 판정 |
|---|---|---|
| 1 | 원설계 정본 식 | `_workspace/kojiro_ma/kojiro/screener.py:113-120,134-141` 이 **유일한 실행 가능 정본**. 설계서 `:155` 은 한 줄 요약, 루트/전략 CLAUDE.md·leader rules 는 그 요약의 재인용이라 **분모·정규화 분모를 담고 있지 않다** |
| 2 | 어긋남 (가) `macd3_slope` | 원설계 `(m3[-1]-m3[-4]) / 3 / close` ↔ 현행 `(m3[-1]-m3[-4])` — **`/close` 누락이 실질**, `/3` 은 순위·점수 **완전 불변**(증명 §3.1, 실측 최대 점수차 `0.0`) |
| 3 | 어긋남 (나) `band_expansion` | 원설계 `bw[-1]/mean(bw[-6:-1]) - 1`, 분모 `>0` 아니면 **`0.0`** ↔ 현행 `(bw[-1]-bw[-4])/(abs(bw[-4])+1e-9)` — 분모가 **단일봉 + 1e-9** 라 6→1 직후(정의상 `bw≈0`)에 폭발. 실측 격리: 분모 0 이면 `9.0e10` |
| 4 | 성분 ③ 신선도 | **어긋남이 아니다.** 현행 `within − dist61` 은 원설계 `−fresh_days` 의 **양의 아핀 변환**이고 min-max 는 아핀 불변 ⇒ 점수 동일. **복원 대상 아님**(§2.3) |
| 5 | 가중치 0.4/0.3/0.3 | 원설계 `screener.py:37-39` 와 **동일**. 손대지 않는다 |
| 6 | 오늘 후보군 재계산 | **이 세션에서는 불가**(운영 API 접근이 auto-mode classifier 로 차단됨). 로컬 캐시 일봉은 7봉뿐이라 EMA40 산출 불가. §5 에 **그대로 실행 가능한 스크립트**와 판독 규칙을 실었다 |
| 7 | 신규 `DEFAULT_PARAMS` 키 | **0개.** `test_g268_7` 의 `KOJIRO_PARAM_KEYS` 동결 가드가 그대로 초록 |
| 8 | 8영역·`scheduler.py` | **무접촉.** 접촉 파일 = `kojiro.py` + 신규 leaf 1 + 테스트. sha 핀 4곳(8영역)은 **해당 없음**, 단 §7 의 `G-223-12`(전략 파일 diff 0)는 **반드시 걸린다** |

> ⚠️ **이 문서는 결정을 재해석하지 않는다.** 사용자 결정은 "복원 진행 + shadow 같이" 다.
> 결정문에 없는 판단이 필요한 지점(`/3` 포함 여부, 신선도 비복원)은 §9 미해결로 올렸고 여기서 확정하지 않았다.

---

## 1. 원설계 정본 확정

### 1.1 네 문서의 대조

| 정본 후보 | 담고 있는 것 | 분모·정규화 정보 |
|---|---|---|
| `_workspace/kojiro_ma/전략설계서_고지로_대순환_자동매매.md:155` (§9 4단 깔때기 ④) | `0.4×MACD3 기울기 + 0.3×띠 폭 확장률 + 0.3×진입 신선도 (min-max 정규화 가중합)` | **없음** (가중치와 정규화 방식만) |
| `_workspace/kojiro_ma/kojiro/screener.py:113-120` (레퍼런스 구현) | 성분 3종의 **실제 식** | **있음 — 유일** |
| `_workspace/kojiro_ma/kojiro/screener.py:134-141` | min-max `norm()` + 가중합 + 신선도 **부호 반전** | **있음** |
| `_workspace/00_leader_trading_rules.md:31` / `src/engine/strategies/CLAUDE.md:79` | `0.4×MACD3기울기 + 0.3×띠폭확장률 + 0.3×6→1신선도` | 없음 (설계서 요약의 재인용) |
| `src/engine/strategies/kojiro.py:1-20` 상단 docstring | 진입/청산만 기술 | **랭킹 언급 자체가 없다** |
| `docs/HARNESS_CHANGELOG.md` | 2026-07-20 kojiro 랭킹 도입 행이 **표에 남아 있지 않다**(15행 롤링에서 밀려남) | 없음 |

⇒ **정본 = `screener.py`.** 설계서 `:155` 과 프로젝트 문서 3곳은 전부 "0.4/0.3/0.3 + min-max" 만 전달하고
**분모를 전달하지 않는다** — 포팅이 어긋난 지점이 정확히 그 전달되지 않은 부분이다.
(문서가 코드보다 성기다는 사실 자체가 이번 결함의 **발생 경로**이며, §8 에서 문서 동기화를 최소 diff 에 포함한 이유다.)

### 1.2 원설계 정본 원문 (verbatim)

`_workspace/kojiro_ma/kojiro/screener.py:109-120`

```python
            fresh = _days_in_current_stage(df["stage"])
            if fresh <= cfg.stage1_freshness:
                # 점수 요소 (종목 간 비교는 정규화 후)
                macd3_slope = float(df["macd3"].iloc[-1] - df["macd3"].iloc[-4]) / 3
                band_now = df["band_width"].iloc[-1]
                band_prev = df["band_width"].iloc[-6:-1].mean()
                band_expansion = float(band_now / band_prev - 1) if band_prev > 0 else 0.0
                candidates.append({**base,
                                   "fresh_days": fresh,
                                   "macd3_slope_pct": macd3_slope / last["close"],
                                   "band_expansion": band_expansion})
```

`:131-142`

```python
    cand_df = pd.DataFrame(candidates)
    if not cand_df.empty:
        def norm(s: pd.Series) -> pd.Series:
            rng = s.max() - s.min()
            return (s - s.min()) / rng if rng > 0 else pd.Series(0.5, index=s.index)
        cand_df["score"] = (
            cfg.w_macd3_slope * norm(cand_df["macd3_slope_pct"])
            + cfg.w_band_expansion * norm(cand_df["band_expansion"])
            + cfg.w_freshness * norm(-cand_df["fresh_days"].astype(float))
        ).round(4)
        cand_df = cand_df.sort_values("score", ascending=False).reset_index(drop=True)
```

가중치 기본값 `:37-39` = `w_macd3_slope 0.4` / `w_band_expansion 0.3` / `w_freshness 0.3`.

**원설계 3성분 (부호·창·정규화 분모 확정)**

| 성분 | 식 | 창 | 정규화 분모 | 부호 |
|---|---|---|---|---|
| ① MACD3 기울기 | `(macd3[-1] − macd3[-4]) / 3 / close[-1]` | **3봉 스팬**(인덱스 −4 → −1) | **봉 수 3** *그리고* **당일 종가** | 클수록 좋다(그대로) |
| ② 띠폭 확장률 | `bw[-1] / mean(bw[-6:-1]) − 1`, 분모 ≤0 이면 `0.0` | 현재봉 1 vs **직전 5봉 평균**(−6..−2) | **직전 5봉 평균 밴드폭** | 클수록 좋다(그대로) |
| ③ 진입 신선도 | `norm(−fresh_days)`, `fresh_days = 현재 스테이지 연속 지속일(당일 포함)` | 현재 스테이지 런 길이 | (없음) | **부호 반전** — 짧을수록 좋다 |

---

## 2. 현행 코드 대조 — 성분별 판정

### 2.1 현행 구현 (HEAD `a10191b`, `src/engine/strategies/kojiro.py:1194-1212`)

```python
    def _rank_candidate_components(self, enriched, stages_series: list, within: int) -> tuple[float, float, float]:
        dist = _stage_transition_distance(stages_series, 6, 1, within)          # :1200
        fresh = float(within - dist) if dist is not None else 0.0               # :1201
        try:
            m3 = enriched["macd3"]                                              # :1203
            bw = enriched["band_width"]                                         # :1204
        except (KeyError, TypeError):
            return (0.0, 0.0, fresh)                                            # :1206
        li = len(m3) - 1                                                        # :1207
        pi = max(0, li - _RANK_LOOKBACK)                                        # :1208   (_RANK_LOOKBACK = 3, :115)
        macd3_slope = float(m3.iloc[li] - m3.iloc[pi])                          # :1209
        prev_bw = float(bw.iloc[pi])                                            # :1210
        band_expansion = (float(bw.iloc[li]) - prev_bw) / (abs(prev_bw) + 1e-9) # :1211
        return (macd3_slope, band_expansion, fresh)                             # :1212
```

배선 = `prepare` 안 3지점 — `rank_raw` 초기화 `:336` · 후보 확정 직후 stash `:448-449` ·
`_score_candidates` → `score` 스탬프 → `ranked_final` `:486-491`.
`self._candidates[t]["score"]` 의 **소비처는 `src/` 전체에서 `kojiro.py:489` 대입 한 곳뿐**이고
(`get_targets_status` 는 `score` 를 내보내지 않는다), 실제 소비는 `_scanned_tickers` **순서**다.
그 순서를 `scheduler._swing_buy_poll_loop` 가 그대로 처리 순서로 쓴다.

### 2.2 어긋남 (가) — `macd3_slope` : `/3` 과 `/close` 두 개가 빠졌다

| | 원설계 | 현행 | 차이의 성질 |
|---|---|---|---|
| 스팬 | `[-4] → [-1]` | `[pi] → [li]`, `pi = li−3` = **동일** | 동일 ✅ |
| 봉 수 나눗셈 | `/ 3` | 없음 | **모든 후보에 같은 양의 상수** ⇒ min-max 뒤 점수 **완전 동일**(§3.1 증명·실측) |
| 가격 정규화 | `/ last["close"]` | 없음 | **종목마다 다른 수** ⇒ 순위가 실제로 바뀐다 |
| 단위 | 무차원(일당 가격비율) | **원(₩)** | 고가주가 구조적으로 큰 값을 갖는다 |

자문 실측(오늘 후보 17종목, `_workspace/domain_consult/kojiro_band_width_floor_filter_20260910.md` §4.3):
**Spearman(macd3_slope, 종가) = +0.853**, 정규화 후 HD현대(255,000원) 1.000 / 유안타증권(4,720원) 0.000.
가중치가 가장 큰 성분(0.4)이 사실상 **주가 순위표**로 동작한다.

격리 실증(§3.2) — 수익률 시퀀스를 완전히 같게 두고 가격 스케일만 4,720 / 47,950 / 255,000 으로 바꾸면
현행 정규화값 `[0.000, 0.173, 1.000]`(= 가격 순서) ↔ 원설계 정규화값 `[0.5, 0.5, 0.5]`(= 전부 동값 → 중립).

### 2.3 어긋남 (나) — `band_expansion` : 분모가 단일봉 + `1e-9`

| | 원설계 | 현행 |
|---|---|---|
| 분자 | `bw[-1] − 분모` (비율 형태 `bw[-1]/분모 − 1` 와 동치) | `bw[li] − bw[pi]` |
| 분모 | `mean(bw[-6:-1])` = **직전 5봉 평균** | `bw[pi]` = **단일봉**(−4) |
| 0 근처 가드 | `band_prev > 0` 아니면 **`0.0` 반환** | `abs(prev_bw) + 1e-9` = **폭발 허용** |
| `_RANK_LOOKBACK` 결합 | 없음(성분 ①과 창이 다르다) | **있다** — `pi` 를 ①과 공유해 `_RANK_LOOKBACK` 을 건드리면 두 성분이 동시에 움직인다 |

- `band_width = |ema_m − ema_l|`(`src/engine/kojiro_indicators.py:99`)이고 6→1 전환은 **EMA20 이 EMA40 을 뚫는 사건**이므로,
  strict entry 를 통과한 후보는 정의상 `bw[pi] ≈ 0` 이다. **폭발은 예외가 아니라 상시**다.
- 격리 실증(§3.3): 분모 `bw[-4] = 0` 이면 현행 값 **9.0e10**. 같은 시리즈에서 원설계 5봉 평균 분모는 `0.875`.
- 방향의 역전 — 현행 `exp1` 은 **분모가 작을수록**(= 밴드가 좁을수록) 큰 값을 준다.
  자문 표(§4.3 나): 롯데지주 `bw 10.4 → 95` 가 확장률 8.15 로 **1위 만점**. 절대 크기로는
  주가의 0.34% · ATR 의 0.10배다. **사용자가 벌하려던 "좁은 정배열"을 현행 랭킹이 상 주고 있다.**

**자문 표에서 파생되는 사실 하나** — §4.3(나) 표 5행에 min-max 를 역산하면 `(min, max) ≈ (−0.238, 8.15)`
에서 5행 전부가 **오차 ≤ 0.025** 로 재현된다(§5.3). 즉 오늘 후보 17종목 중 **밴드가 수축 중인(exp1 < 0)
종목이 최소 1건** 있었고 그 값이 대략 −0.24 다. 자문 §3.3 의 `exp5 < 0` 코호트 논의와 정합한다.

### 2.4 성분 ③ 신선도 — **어긋남이 아니다 (복원 대상 아님)**

- 원설계: `fresh_days = _days_in_current_stage(stage)`(현재 스테이지 연속 지속일, 당일 포함) → `norm(−fresh_days)`.
- 현행: `dist = _stage_transition_distance(stages, 6, 1, within)`(6→1 전환의 마지막 봉 기준 거리) →
  `fresh = within − dist` → `norm(fresh)`.
- 관계: 6→1 전환 후 스테이지가 계속 1이면 `fresh_days = dist + 1` 이므로
  `fresh = within − dist = (within − 1) + (−fresh_days)` — **기울기 +1 의 아핀 변환**이다.
  min-max 정규화는 양의 아핀 변환에 불변이므로 **정규화값·점수·순위 전부 동일**하다.
- 게다가 현행 정의는 이 전략의 **진입 게이트와 같은 사건**(`_stage_recently(6,1,within=stage1_freshness)`, `:426`)을
  재사용한다 — `rank_raw` 에 들어온 후보는 전원 그 게이트를 통과했으므로 `dist ∈ [0, within−1]` 이 보장된다.
- **유일한 발산 경로**: 창 안에서 `6→1→2→1` 처럼 스테이지가 되돌아온 경우.
  원설계는 마지막 1-런만 세어 `fresh_days=1`(가장 신선), 현행은 6→1 전환까지 거슬러 `dist=2`(덜 신선).
  이 코호트는 "정배열이 한 번 무너졌다 돌아온" 종목이고, **현행 쪽이 덜 후하게 주는** 방향이다.
- ⇒ 복원 이득 0, 회귀 위험만 있다. **비복원 권고.** (결정문에 없는 판단이므로 §9-③ 미해결로 올린다.)

---

## 3. 수학적 성질 — 무엇이 순위를 바꾸고 무엇이 안 바꾸는가

`_score_candidates`(`kojiro.py:1214-1242`)의 `_mm` 은 성분별 min-max 다:
`norm(v) = (v − lo) / (hi − lo)` (단, `hi − lo < 1e-12` → 전부 `0.5`).

### 3.1 `/3` 은 순위·점수 **완전 불변** (증명 + 실측)

성분 벡터 `v` 를 양의 상수 `c` 로 나누면 `lo' = lo/c`, `hi' = hi/c` 이므로
`(v/c − lo/c) / (hi/c − lo/c) = (v − lo)/(hi − lo)` — **정규화값이 문자 그대로 같다.**
`/3` 은 모든 후보에 같은 상수이므로 이 조건을 만족한다.

실측(scratchpad `uc/sim.py`, 8종목 합성 풀): `/3` 적용 전후 **최대 점수차 `0.0`**, 순위 리스트 동일(`True`).

> ⇒ **`/3` 을 넣어도 오늘 매수 순위는 한 칸도 안 바뀐다.** 넣는 이유는 오직 (a) 원설계 문언 일치 (b) 성분 ①이
> "하루당 가격비율" 이라는 **읽을 수 있는 단위**를 갖게 되어 §6 shadow 로그가 임계 논의에 쓸 수 있는 수가 된다는 것이다.
> 반대로 **순위 변화를 `/3` 탓으로 귀인하는 판독은 전부 오독**이다 — 판독 규칙에 못 박아야 한다.

⚠️ 단, `pi = max(0, li − _RANK_LOOKBACK)` 가 **클램프될 때**(`len(m3) < 4`) 실제 스팬은 3이 아니다.
프로덕션은 `KOJIRO_MIN_REQUIRED = 80` 이라 도달 불가지만, 테스트 스텁(len 3~5)에서는 도달한다.
그 경우 `/3` 은 종목마다 다른 스팬을 같은 3으로 나누므로 **불변성이 깨진다**(후보 간 워밍업 봉 수가 다를 때).
→ 구현 시 `/ _RANK_LOOKBACK`(상수)로 쓰고, 클램프 상황은 §8 의 fail-safe 로 흡수한다.

### 3.2 `/close` 는 순위를 **실제로** 바꾼다 (격리 실증)

scratchpad `uc/sim2.py` — 동일 수익률 시퀀스(하락 60봉 → 상승 60봉), 가격 스케일만 다름:

| ticker | 마지막 종가 | 현행 `macd3_slope`(원) | 원설계 `macd3_slope_pct` |
|---|---|---|---|
| 저가주 | 5,631 | 17.26 | 1.021879e-03 |
| 중가주 | 57,206 | 175.37 | 1.021879e-03 |
| 고가주 | 304,224 | 932.64 | 1.021879e-03 |

- 현행 min-max: `[0.000, 0.173, 1.000]` — **가격 순서 그대로**
- 원설계 min-max: `[0.5, 0.5, 0.5]` — 전부 동값 → 중립

이것이 자문의 `ρ = +0.853` 이 만들어지는 기전이며, `§7.2` 가 요구한 "고가주/저가주 쌍" Red 의 형태다.

### 3.3 `exp1` → `exp5` 는 순위를 **뒤집는다** (격리 실증)

`bw` 시리즈를 직접 주입(마지막 6봉만 의미 있음):

| 케이스 | `bw` 시리즈 | `bw_now` | `bw[-4]`(현행 분모) | **exp1** | `mean(bw[-6:-1])` | **exp5** |
|---|---|---|---|---|---|---|
| 얇은분모_잡음 | `200,190,180,10,150,160,95` | 95 | **10.0** | **8.500** | 138.0 | **−0.312** |
| 굵직한_확장 | `200,300,400,500,600,700,1400` | 1,400 | 500.0 | 1.800 | 500.0 | 1.800 |

- 현행 순위: `얇은분모_잡음` > `굵직한_확장`
- 원설계 순위: `굵직한_확장` > `얇은분모_잡음` ← **역전**

경계값:

| 입력 | 현행 `exp1` | 원설계 `exp5` |
|---|---|---|
| `bw[-4] = 0`, `bw` = `100,80,60,0,40,60,90` | **9.0e10** | `0.8750` (분모 48.0) |
| `bw` 전부 0 | `0.000e+00`(0/1e-9) | **`0.0`**(가드 발동) |

`iloc[-6:-1]` 의 짧은 시리즈 거동(원설계 표현을 그대로 써도 안전한 근거):

| `len(bw)` | `iloc[-6:-1]` 인덱스 | `mean()` |
|---|---|---|
| 1 | `[]` | `nan` → `nan > 0` 은 **False** → `0.0` 반환 ✅ |
| 2 | `[0]` | 1.0 |
| 3 | `[0,1]` | 1.5 |
| 5 | `[0,1,2,3]` | 2.5 |

⇒ **원설계 표현 `bw.iloc[-6:-1].mean()` 을 그대로 옮겨도 `IndexError`·`ZeroDivisionError` 가 없다.**
`nan` 이 `> 0` 비교에서 False 로 떨어지는 것이 그 안전성의 근거다(명시적 `math.isnan` 불필요, 다만 §8 에 주석으로 남긴다).

### 3.4 min-max 엡실론 `1e-12` 여유 — 스케일 축소의 유일한 부작용

`/close /3` 는 성분 ①의 스케일을 대략 `1e5~1e6` 배 줄인다. `_mm` 의 `hi − lo < 1e-12` 중립 분기가
잘못 발동할 위험이 이론상 새로 생긴다.

| 단위 | 실측 스팬 예시(합성 8종목) | `1e-12` 대비 여유 |
|---|---|---|
| 원(현행) | `1191.83 − (−11.84) = 1203.67` | 1.2e15 배 |
| 비율(복원) | `1.032e-3 − (−5.113e-4) = 1.543e-03` | **1.5e9 배** |

⇒ 여유 9자릿수. 실무상 위험 없음. 단 **"모든 후보가 0.5 중립이 되는 날"** 은 결함 서명이므로
§6 shadow 가 `slope_pct` 원값을 남겨 사후 판별 가능하게 한다. (`_mm` 자체는 손대지 않는다.)

---

## 4. 자문 수치의 재현 절차 (어느 덤프/어느 조회였나)

### 4.1 원천

자문 문서 머리말: *"실측 원천 = 운영 EC2 읽기 전용 API(`/api/strategies`, `/api/history`,
`/api/stock-master/{t}/daily`, `/api/balance`) 2026-09-10 조회분"*.

이 세션 scratchpad 에 **자문이 실제로 돌린 스크립트가 그대로 남아 있다**:

| 파일 | 역할 | 산출 |
|---|---|---|
| `…/scratchpad/q.sh` | EC2(3.38.228.74) ssh → 컨테이너 밖 `curl -H 'X-API-Key: …' http://127.0.0.1:8000<path>` 읽기 전용 래퍼 | 임의 GET |
| `…/scratchpad/rank.py` | **§4.3 (가)(나) 수치의 정본 스크립트** — `/api/strategies` 의 kojiro `targets` 전 종목에 `/api/stock-master/{t}/daily?days=100` 을 걸어 EMA20/40·Wilder ATR(20)·`macd3`·`bw` 를 직접 재계산하고, 현행 `macd3_slope`·`exp1` 과 Spearman 3종·min-max 정규화표를 출력 | `Spearman(macd3_slope, close)=+0.853` · `Spearman(macd3_slope, band_expan)=−0.069` · §4.3(나) 표 |
| `…/scratchpad/bw.py` | §2.2 진입 23건 밴드폭 복원 표(`/api/history` BUY 전량 × 매수일 직전 완성봉) | 밴드/ATR 분포 |
| `…/scratchpad/chop.py`·`sens.py` | §3.3 `exp5` 소급·컷 스윕·부호변경 탐지기 | §5 차단율표 |
| `…/scratchpad/hist_kojiro*.json`, `…/tickers.txt` | `/api/history?strategy=kojiro` 캐시, WS 유니버스 티커 목록 | |

**`rank.py` 의 재계산 규약**(그대로 옮겨 적는다 — 이것이 "어느 봉을 기준으로 쟀나"의 답이다):

1. `bars = sorted(daily, key=bas_dd)` 후 **최신 봉(오늘 부분봉)을 드롭** → `prepare` 의 `prev_idx` 규약과 정합.
2. `ema(span)` 은 `adjust=False` 재귀식, `watr` 는 Wilder `alpha=1/20` — `src/engine/kojiro_indicators.py` 와 동일 정의.
3. `len(closes) < 45` 인 종목은 스킵(워밍업 부족).
4. `li = len-1`, `pi = max(0, li-3)`, `slope = m3[li]-m3[pi]`, `expan = (bw[li]-bw[pi])/(abs(bw[pi])+1e-9)`
   — **HEAD 코드와 문자 그대로 같은 식**이다(그래서 §4.3 수치는 라이브 랭킹의 재현이다).

### 4.2 이 세션의 재현 가능성 — **불가**

- `q.sh`(ssh) 호출이 auto-mode classifier 에 의해 **차단**됐다(`Blocked by classifier`). 우회 시도 안 함.
- 로컬 캐시 `…/scratchpad/verify_daily.jsonl` 은 157종목 × **7봉**뿐(`days=7`) — EMA40 산출 불가.
  `…/scratchpad/readout/daily.json` 도 동일하게 짧다.
- 오늘 후보 17종목의 **완전한 목록조차 문서에 남아 있지 않다**(gap readout `:214` 가 앞 6개
  `267250, 041510, 004990, 034020, 443060, 005490, …` 만 인용).
  `041510`(에스엠)·`003470`(유안타)은 로컬 캐시 티커 목록에도 없다.

⇒ **재계산에는 운영 API 1회 read-only 왕복이 반드시 필요하다.** §5 에 그대로 쓸 수 있는 형태로 실었다.

---

## 5. 오늘(다음) 후보군으로 복원 전후 순위를 재계산하는 절차

### 5.1 실행 (읽기 전용, GET 만 — POST/PUT 0건)

EC2 에서 아래를 **한 번** 돌린다(`rank.py` 의 확장판이다 — 현행/복원 두 벌을 같은 입력으로 계산한다).

```python
# rerank.py — 읽기 전용. GET /api/strategies, GET /api/stock-master/{t}/daily?days=100 만 호출.
import json, urllib.request, os
KEY = next(l.split("=",1)[1].strip() for l in open(os.path.expanduser("~/auto_stock/.env"))
           if l.startswith("API_AUTH_KEY="))
def api(p):
    return json.load(urllib.request.urlopen(
        urllib.request.Request("http://127.0.0.1:8000"+p, headers={"X-API-Key": KEY}), timeout=30))

K = api("/api/strategies")["data"]["kojiro"]
T, P = K["targets"], K.get("params", {})
W = (float(P.get("rank_w_macd3", .4)), float(P.get("rank_w_band", .3)), float(P.get("rank_w_fresh", .3)))
WITHIN = int(P.get("stage1_freshness", 5)); LB = 3

def ema(v, s):
    a = 2.0/(s+1); o=[]; p=None
    for x in v: p = x if p is None else a*x+(1-a)*p; o.append(p)
    return o
def watr(h, l, c, per=20):
    a = 1.0/per; o=[]; p=None
    for i in range(len(c)):
        tr = (h[i]-l[i]) if i == 0 else max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        p = tr if p is None else a*tr+(1-a)*p; o.append(p)
    return o
STAGE = {("s","m","l"):1,("m","s","l"):2,("m","l","s"):3,("l","m","s"):4,("l","s","m"):5,("s","l","m"):6}
def stages_of(es, em, el):
    out=[]; prev=None
    for s,m,l in zip(es,em,el):
        if s==m or m==l or s==l: out.append(prev); continue
        k=tuple(n for n,_ in sorted([("s",s),("m",m),("l",l)], key=lambda x:-x[1]))
        prev=STAGE.get(k,prev); out.append(prev)
    return out
def dist61(st, within):
    w = st[-(within+1):]; last=len(w)-1; best=None
    for j in range(len(w)-1):
        if w[j]==6 and w[j+1]==1: best = last-(j+1)
    return best

rows={}
for t in T:
    d = api("/api/stock-master/%s/daily?days=100" % t)["data"] or []
    bars = sorted(d, key=lambda x: x["bas_dd"])
    today = max(x["bas_dd"] for x in bars)
    bars = [x for x in bars if x["bas_dd"] < today] if len(bars) > 1 else bars   # 오늘 부분봉 드롭
    if len(bars) < 45: continue
    c=[x["close_price"] for x in bars]; h=[x["high_price"] for x in bars]; lo=[x["low_price"] for x in bars]
    e5, e20, e40 = ema(c,5), ema(c,20), ema(c,40); at = watr(h,lo,c,20)
    m3=[a-b for a,b in zip(e20,e40)]; bw=[abs(x) for x in m3]
    li=len(c)-1; pi=max(0,li-LB)
    dd = dist61(stages_of(e5,e20,e40), WITHIN)
    fresh = float(WITHIN-dd) if dd is not None else 0.0
    cur_slope = m3[li]-m3[pi]
    cur_exp   = (bw[li]-bw[pi])/(abs(bw[pi])+1e-9)
    new_slope = (cur_slope/LB)/c[li]
    bp = sum(bw[-6:-1])/len(bw[-6:-1]) if len(bw)>=2 else 0.0     # 원설계 iloc[-6:-1]
    new_exp = (bw[li]/bp - 1.0) if bp > 0 else 0.0
    rows[t] = dict(name=(T[t].get("name") or "")[:12], bar=bars[-1]["bas_dd"], close=c[li], atr=at[li],
                   bw=bw[li], bw_prev1=bw[pi], bw_prev5=bp, fresh=fresh,
                   cur_slope=cur_slope, cur_exp=cur_exp, new_slope=new_slope, new_exp=new_exp)

def mm(v):
    lo_, hi = min(v), max(v)
    return [0.5]*len(v) if hi-lo_ < 1e-12 else [(x-lo_)/(hi-lo_) for x in v]
ts = list(rows)
def score(sk, ek):
    a, b = mm([rows[t][sk] for t in ts]), mm([rows[t][ek] for t in ts]); f = mm([rows[t]["fresh"] for t in ts])
    s = sum(W) or 1.0; w = [x/s for x in W]
    return {t: w[0]*a[i] + w[1]*b[i] + w[2]*f[i] for i, t in enumerate(ts)}
cur, new = score("cur_slope","cur_exp"), score("new_slope","new_exp")
oc = sorted(ts, key=lambda t: -cur[t]); on = sorted(ts, key=lambda t: -new[t])
print("N=%d  bar=%s" % (len(ts), sorted({rows[t]["bar"] for t in ts})))
print("%-4s%-8s%-12s%9s%9s%9s%9s%8s%8s%8s%8s%6s" % ("#","ticker","name","close","bw","bw(-3)","bw5mean",
                                                     "curScr","newScr","curExp","newExp","Δ순위"))
for i, t in enumerate(oc):
    r = rows[t]
    print("%-4d%-8s%-12s%9.0f%9.1f%9.1f%9.1f%8.3f%8.3f%8.2f%8.2f%6+d"
          % (i+1, t, r["name"], r["close"], r["bw"], r["bw_prev1"], r["bw_prev5"],
             cur[t], new[t], r["cur_exp"], r["new_exp"], i - on.index(t)))
print("현행 상위5:", oc[:5]); print("복원 상위5:", on[:5])
```

### 5.2 판독 규칙 (이 표를 볼 때 지켜야 하는 것)

1. **`Δ순위` 를 `/3` 탓으로 읽지 않는다** — `/3` 은 점수차 0 이 증명돼 있다(§3.1). 순위 변화는 전부 `/close` 와 `exp5` 몫이다.
2. **`bar` 열이 전 종목 동일한 직전 영업일인지 먼저 본다.** 자문 §7.3 F-3 가 `004690`(삼천리) 4거래일 stale ·
   `003470`(유안타) 1일 stale 을 잡았다. stale 종목의 순위 변화는 **결함의 결과이지 복원의 결과가 아니다.**
3. **kojiro 가 만석(6/6)이면 이 표는 "지금 당장의 매수 변화"가 아니다.** 자문 §4.2 — `is_max_positions()`
   (`kojiro.py:809`)가 앞에 있어 신규 매수가 이미 전면 차단이다. 표의 의미는 **슬롯이 비는 첫날**의 처리 순서다.
4. 복원 전후로 **후보 집합(rank_raw 의 키)** 은 절대 바뀌면 안 된다 — 바뀌었으면 자격 게이트를 건드린 것이다(계약 위반).

### 5.3 이 세션에서 확인한 것 (재현 없이 문서 산술만)

자문 §4.3(나) 표 5행에 min-max 를 역산하면 `(min, max) ≈ (−0.238, 8.15)` 에서 5행 전부가 오차 ≤ 0.025 로 재현된다:

| 종목 | exp1 | 표의 정규화 | 역산 예측 | 차 |
|---|---|---|---|---|
| 롯데지주 | 8.15 | 1.000 | 1.000 | +0.000 |
| 에스엠 | 6.75 | 0.846 | 0.833 | −0.013 |
| HD현대 | 5.52 | 0.711 | 0.686 | −0.025 |
| SK케미칼 | 0.06 | 0.011 | 0.036 | +0.025 |
| 삼천리 | 0.30 | 0.084 | 0.064 | −0.020 |

잔차는 표의 `bw`(정수)·`exp1`(2자리) 반올림으로 설명되는 크기다.
**파생 사실** = 오늘 후보 풀의 `exp1` 최솟값이 ≈ **−0.24** (밴드 수축 중인 후보가 최소 1건 존재).
`bw` 값들도 자체 정합한다 — 예: 롯데지주 `(95−10.4)/10.4 = 8.13`(표 8.15), HD현대 `(3150−483)/483 = 5.52` ✅.

---

## 6. shadow 관측 `[kojiro_band_observe]` 설계

자문 §7.1 을 정본으로 하되, **rank_score 를 한 행에 담으려면 발화 지점이 후보 확정 루프가 아니라 그 뒤여야 한다**는
구조적 사실 하나를 반영한다(점수는 후보 풀 전체가 모여야 계산된다 — `kojiro.py:486`).

### 6.1 leaf 계약 (`src/engine/kojiro_band_observe.py`)

`src/engine/kojiro_gap_observe.py`(cycle268) **구조 그대로**:

- never-raise(본체 전체 `try/except Exception`) · 반환 `None` · read-only · `await`/DB/HTTP **0건**
- 실패는 `src/engine/observer_trace.trace_observer_failure(MARKER, key, _cap)` (무흔적 `pass` 금지, cycle258)
- cap = `KstDailyEmitCap`(자기 날짜 리셋, `_reset_daily_state` override 신설 금지)
- 어떤 dict 도 생성·변경하지 않는다(cycle242 G-242-8 동형)
- **임계 판정·차단 플래그를 넣지 않는다**(cycle228 `would_pass` 의미 반전 선례)

**⚠️ 이름 충돌 (실측 확인, 반드시 지킬 것)**

| 심볼 | gap leaf | band leaf | 이유 |
|---|---|---|---|
| 관측 함수 | `observe_gap` | **`observe_band`** | `test_g268_3b`·`test_g268_4` 가 `_call_name == "observe_gap"` 인 Call 을 **kojiro.py 전체**에서 세어 6개를 강제한다 |
| 흡수기 | `absorb_call_failure` | **`absorb_band_call_failure`** | `test_g268_15b` 가 `absorb_call_failure` 라는 이름의 Call 을 **kojiro.py 전체**에서 세어 `== 6` 을 강제한다. 같은 이름을 쓰면 즉시 RED(그리고 import 이름 충돌) |
| 리셋 훅 | `reset_kojiro_gap_observe_cap` | **`reset_kojiro_band_observe_cap`** | `test_g268_16` 이 gap 쪽 이름만 본다 |
| 마커 / 모듈 토큰 | `[kojiro_gap_observe]` / `kojiro_gap_observe` | `[kojiro_band_observe]` / `kojiro_band_observe` | `test_g268_9` 는 **부분문자열** 검색이라 `kojiro_band_observe` 는 `kojiro_gap_observe` 를 포함하지 않아 무충돌 ✅ |

### 6.2 발화 지점 = `prepare` 의 점수 확정 **뒤** 1곳

```
:448-449  rank_raw[ticker] = self._rank_candidate_components(...)     ← ① 여기서 원자료를 stash
:486      scores = self._score_candidates(rank_raw, params)
:487-489  self._candidates[_t]["score"] = _sc
:490      ranked_final = sorted(...)
          ─────────────────────────────────────────────────────────── ← ② 여기서 1회 emit 루프
:491      held_only = [...]
```

- ①에서 **`_candidates` 를 넓히지 않고** 지역 dict `band_raw: dict[str, tuple]` 에 담는다
  (`rank_raw` 와 완전 대칭). `_candidates` 스탬프는 자문이 허용한 대안이지만, 그 dict 는
  대시보드(`get_targets_status`)·`_apply_lot_units_cap`·`_effective_atr` 이 읽는 공유 상태라 **넓히지 않는 쪽이 안전**하다.
- 보유 전용 종목도 한 행을 남기려면 **held 스탬프 지점(`:404-411`)에서도 같은 stash** 를 한다.
  (그 지점은 ATR 밴드·스테이지 판별을 통과한 뒤라, 밴드 밖 보유 종목은 행이 없다 — 그 결측 자체가 정보다.)
- ②의 emit 루프는 `for t in ranked_final + held_only` 순서로 돌아 **로그 행 순서 = 그날 매수 처리 순서**가 되게 한다.
- emit 루프 전체를 `try/except Exception: absorb_band_call_failure(...)` 로 감싼다(호출 지점 흡수기).

### 6.3 한 행의 필드 (전부 D-1 완성봉 기준)

```
[kojiro_band_observe] ticker= name= role= rank= bar= close= atr= atr_pct=
                      bw= bw_close_pct= bw_atr= bw_prev1= bw_prev5=
                      exp1= exp5= slope_raw= slope_pct= dist61= score=
```

| 필드 | 정의 | 왜 필요한가 |
|---|---|---|
| `role` | `candidate`(rank_raw 멤버) / `held`(보유 전용) | 자문 §7.1 이 기대한 13+4 행 구성을 사후 분리 |
| `rank` | `ranked_final` 내 0-base 순위 (held 는 `-`) | 순위 변화 추적의 정본 |
| `bar` | 기준봉 `stck_bsop_date`(= `asc[-1]`) | **F-3 stale 일봉을 사후 판별하는 유일한 근거**(자문 §7.1 명시) |
| `atr`, `atr_pct` | Wilder ewm(1/20) ATR, `atr/close` | 밴드/ATR 의 분모 · 밴드 게이트와 같은 단위 |
| `bw`, `bw_close_pct`, `bw_atr` | `|ema_m−ema_l|`, `bw/close×100`, `bw/atr` | 자문 카드 ②의 세 척도 후보를 **동시에** 쌓는다(하나만 쌓으면 나중에 척도를 못 바꾼다) |
| `bw_prev1`, `bw_prev5` | 현행 분모(−4봉) / 원설계 분모(−6..−2 평균) | 분모 폭발의 직접 증거 |
| **`exp1`**, **`exp5`** | 현행 식 값 / 원설계 식 값 | **둘 다 남겨야 §4.3(나) 시정의 전후 대조가 성립한다**(자문 §7.1 명시) |
| `slope_raw`, `slope_pct` | 현행 원(₩) 값 / 복원 무차원 값 | (가) 시정의 전후 대조 + §3.4 의 "전부 0.5 중립" 결함 서명 감지 |
| `dist61` | 6→1 전환 거리(봉) | 신선도 원자료(정규화 전) |
| `score` | 그날 실제 채택된 최종 점수 | 순위와 성분의 연결 |

- cap 키 = `(ticker, role)`, **1행/(ticker,role)/일**. 예상 부피 = 오늘 기준 13 + 4 ≈ **17행/일**.
- 후보별 **성과는 이 leaf 가 남기지 않는다** — `trade_history` × `stock_master_daily` 오프라인 조인(leaf 순수 유지).
- **판독 시 주의(의미 전환)** — 이 마커는 cycle273 배포 **이후**에만 존재하고, 그 시점부터 `exp5` 가 랭킹의 실제 입력이다.
  배포 전 기간의 `exp1` 기반 순위와 **합산 판독 금지**(cycle228·cycle263 선례).

---

## 7. 관련 기존 테스트·AST 가드 (전수)

### 7.1 반드시 갱신되는 것 — **1개 함수**

| 파일 | 함수 | 현행 단언 | 복원 후 값(실측 계산) |
|---|---|---|---|
| `tests/unit/engine/strategies/test_kojiro_candidate_rank.py` | `test_rank_components_from_enriched` | `m3s == 4.0`, `be == 0.5` | 입력 df 에 `close` 열이 없으면 fail-safe `(0.0, 0.0, fresh)` 로 떨어진다. `close=10000` 열을 추가하면 `m3s = 1.3333e-4`(= `4/3/10000`), `be = 0.30434783`(= `15/11.5 − 1`, `mean(10,10,12,14)=11.5`) |

### 7.2 그대로 초록인 것 (계산으로 확인)

| 파일·함수 | 확인 근거 |
|---|---|
| `test_kojiro_candidate_rank.py::test_stage_transition_distance` | 헬퍼 무변경 |
| `…::test_score_candidates_minmax_weighted` / `test_score_single_and_equal_neutral` / `test_score_weights_normalized_when_sum_ne_one` / `test_score_empty` | `_score_candidates` 무변경 |
| `…::test_rank_components_failsafe_missing_columns` | 입력 df 는 `close` 만 있고 `macd3` 없음 → 동일 fail-safe 경로 |
| `…::test_get_scanned_tickers_ranked_desc` | `_full_enriched` 가 `close=10000` **공통** → `/close /3` 는 공통 상수. 밴드는 T1 `exp5=0.3913` > T2 `0.2093` > T3 `0.0` → 순서 `T1>T2>T3` 유지 ✅ |
| `…::test_single_candidate_preserves_set_and_scores` | 단일 후보 → 성분 무관 `0.5` |
| `…::test_rank_weights_default_params` / `test_rank_weights_excluded_from_param_ranges` | 가중치·`PARAM_RANGES` 무변경 |
| `…::test_check_exit_has_no_rank_logic` | `check_exit_signal` 무접촉 |
| `tests/unit/ast/test_cycle268_ast_gap_observe.py::test_g268_7_default_params_key_set_unchanged` | **신규 키 0개** — `KOJIRO_PARAM_KEYS` 동결 그대로 |
| `…::test_g268_9_marker_and_module_confined` | `MODULE_TOKEN="kojiro_gap_observe"` 부분문자열 검색 — `kojiro_band_observe` 는 미포함 |
| `…::test_g268_11/11b` (scheduler 라인 상한) | scheduler 무접촉 |
| `tests/unit/ast/test_cycle264_scope_and_pins.py::test_c4_strategy_entry_methods_pinned` | 핀 대상은 VB/LTV 6메서드뿐 — **kojiro 미포함** |
| `tests/unit/ast/test_cycle180_prepare_reset_ast.py` | 대상 = VB/LTV 2파일 — kojiro 미포함 |
| `tests/unit/ast/test_budget_limit_ast.py` · `test_cycle242…` · `test_cycle245…` | 대상 = `calc_buy_quantity`/`_apply_budget_limit` — 무접촉 |
| `tests/unit/ast/test_cycle233_ast_account_risk.py` | 대상 = `check_buy_signal` 게이트 위치 — 무접촉 |

### 7.3 반드시 걸리는 것 — 절차 가드

| 가드 | 무엇을 하는가 | 이번 사이클 처리 |
|---|---|---|
| `test_cycle223_ast_donchian_exit_fix.py::test_g223_12_other_strategy_files_diff_zero` | `kojiro.py` 를 포함한 전략 6파일이 워킹트리에서 변경되면, `_CYCLE228_STRATEGY_CONTENT_SHA`(현재 **빈 dict**)에 등재되지 않은 한 **RED** | `kojiro.py` 를 sha 와 함께 등재(“면제 스냅샷”). ⚠️ 가드 메시지의 절차대로 **핀을 먼저 재산출하지 말고** `git diff HEAD -- src/engine/strategies/kojiro.py` 를 눈으로 읽은 뒤 마지막 단계에 `shasum -a 256` 로 산출. 커밋 직후 **다시 비운다**(자기소멸 관례 — 남기면 다음 사이클이 "cycle273 면제" 문구를 받는다) |
| 8영역 sha 핀 **자매 4곳** — `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` · `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA` · `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA` · `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA`(⚠️ ast 디렉터리가 아니다) | 네 dict 모두 **`_EIGHT_AREAS` 만** 본다(전략 파일은 스코프 밖) | **해당 없음** — 이 사이클은 8영역 diff 0. 네 dict 는 **비운 채로 둔다**(cycle271 `4d88aa6` 이 비워 둔 상태 유지) |

### 7.4 신설 권고 가드 (Red 설계 — tdd-engineer 인계)

| ID | 내용 | 자문 근거 |
|---|---|---|
| G-273-1 | **고가주/저가주 쌍** — 종가 4,720 vs 255,000, `%`-동학 동일 → 복원 성분 ①이 **동값**(정규화 0.5/0.5). 현행 식으로는 0.0/1.0 이 되는 것을 반증 케이스로 함께 고정 | §7.2 |
| G-273-2 | **`bw[pi] ≈ 0` 시리즈** — 현행 `exp1` 이 `1e3` 이상으로 튀는 것을 **현행 계약으로 고정**하는 회귀 + 복원 `exp5` 가 유한한 것을 확인하는 테스트를 **쌍으로** | §7.2 |
| G-273-3 | **`band_prev == 0` 정확히 0** → 복원은 `0.0` 반환(가드 발동), 현행은 `bw[li]/1e-9` | §7.2 |
| G-273-4 | **짧은 시리즈** `len(bw) ∈ {1,2,3,5}` → `IndexError`/`ZeroDivisionError` 0건, `len==1` 은 `nan` 분모 → `0.0` | §3.3 표 |
| G-273-5 | **`close ≤ 0` / `close` 열 부재** → 예외 전파 0, 성분 ① `0.0` fail-safe. (**`ZeroDivisionError` 는 현행 `except (KeyError, TypeError)` 에 안 걸린다** — 걸리면 `prepare` 의 바깥 `except` 로 올라가 그 종목이 후보에서 **통째로 사라진다** = 자격 변경) | §8 F-1 |
| G-273-6 | **후보 집합 불변** — 같은 입력에서 복원 전후 `set(rank_raw)`·`set(_candidates)` 가 동일(순서만 다르다) | tester F-1 |
| G-273-7 | `check_buy_signal`·`calc_buy_quantity`·`check_exit_signal` **소스 세그먼트 sha 불변**(cycle264 `_STRATEGY_PINS` 패턴) | tester F-1 |
| G-273-8 | **`/3` 무해성 회귀** — 임의 후보 풀에서 `/3` 유무가 `_score_candidates` 산출을 **비트 단위로** 바꾸지 않는다 | §3.1 |
| G-273-9 | leaf 가 raise 해도 `prepare` 의 후보·순위가 그대로(관측 예외 흡수) + `observe_band`/`absorb_band_call_failure` **이름 충돌 0**(`observe_gap` 6·`absorb_call_failure` 6 카운트 불변) | §6.1 |

---

## 8. 최소 diff 계획

### 8.1 접촉 파일 (5)

| # | 파일 | 성격 | 규모(예상) |
|---|---|---|---|
| 1 | `src/engine/strategies/kojiro.py` | 성분 2건 복원 + stash 2줄 + emit 루프 1블록 | 본문 **≈ +25 / −4** |
| 2 | `src/engine/kojiro_band_observe.py` | **신규 leaf** | 신규 ≈ 130L |
| 3 | `tests/unit/engine/strategies/test_kojiro_candidate_rank.py` | 1개 함수 갱신 + G-273-1~3,5,6,8 추가 | |
| 4 | `tests/unit/engine/test_cycle273_kojiro_band_observe.py` | **신규** leaf 행위 테스트 (G-273-4,9) | |
| 5 | `tests/unit/ast/test_cycle273_ast_kojiro_rank.py` | **신규** AST 가드 (G-273-7, 신규 키 0, 8영역·scheduler 무접촉, leaf 계약) | |

문서 동기화(Phase 4.8 `/sync-docs`, 커밋 전 필수):
`_workspace/00_leader_trading_rules.md:31` · `src/engine/strategies/CLAUDE.md:79` 의 랭킹 한 줄에
**분모를 명시**(`0.4×(MACD3 3봉기울기/3/종가) + 0.3×(띠폭/직전5봉평균 − 1) + 0.3×6→1신선도`) +
루트 `CLAUDE.md` 하네스 표 1행 + `docs/HARNESS_CHANGELOG.md` append.
§1.1 이 보여준 대로 **문서가 분모를 안 적어서 포팅이 어긋난 것**이므로, 이 갱신은 장식이 아니라 재발 방지다.

### 8.2 `kojiro.py` 본문 (제안)

**(a) 성분 복원 — `_rank_candidate_components` (`:1194-1212`)**

```python
    def _rank_candidate_components(self, enriched, stages_series: list, within: int) -> tuple[float, float, float]:
        """후보 랭킹 raw 3성분 (원설계 §9④): (macd3 기울기%, 띠폭 확장률, 신선도).

        원설계 정본 = `_workspace/kojiro_ma/kojiro/screener.py:113-120`.
        ① `macd3_slope_pct` = (macd3[-1]-macd3[-4]) / 3 / 종가 — **원(₩) 단위 금지**
           (`/종가` 누락이 이 성분을 주가 순위표로 만들었다: 2026-09-10 실측 ρ=+0.853).
           `/3` 은 후보 공통 상수라 min-max 뒤 점수 불변이지만 원설계 단위를 지킨다.
        ② `band_expansion` 분모 = **직전 5봉 평균**(`bw[-6:-1]`), `>0` 아니면 **0.0**.
           단일봉 분모 + `1e-9` 는 6→1 직후(정의상 bw≈0)에 폭발해 **좁은 밴드를 보상**했다.
        ③ 신선도는 현행 유지 — `within − dist61` 은 원설계 `−fresh_days` 의 양의 아핀
           변환이고 min-max 는 아핀 불변이므로 정규화값이 동일하다(복원 대상 아님).

        컬럼 부재(테스트 스텁) → 신선도만 산출 + macd3/band=0 (fail-safe, no crash).
        """
        dist = _stage_transition_distance(stages_series, 6, 1, within)
        fresh = float(within - dist) if dist is not None else 0.0
        try:
            m3 = enriched["macd3"]
            bw = enriched["band_width"]
            close_s = enriched["close"]
        except (KeyError, TypeError):
            return (0.0, 0.0, fresh)
        li = len(m3) - 1
        pi = max(0, li - _RANK_LOOKBACK)
        # ② 원설계 5봉 평균 분모. 짧은 시리즈는 pandas 가 알아서 자르고(len 1 → 빈 슬라이스
        #    → mean()=nan), `nan > 0` 이 False 라 0.0 으로 떨어진다(ZeroDivision 불가).
        band_prev = float(bw.iloc[-6:-1].mean())
        band_expansion = (float(bw.iloc[li]) / band_prev - 1.0) if band_prev > 0 else 0.0
        # ① 종가 정규화. close<=0/비수치는 성분 ①만 0.0 (밴드·신선도는 살린다).
        try:
            close = float(close_s.iloc[li])
        except (TypeError, ValueError):
            close = 0.0
        if close > 0:
            macd3_slope = (float(m3.iloc[li] - m3.iloc[pi]) / _RANK_LOOKBACK) / close
        else:
            macd3_slope = 0.0
        return (macd3_slope, band_expansion, fresh)
```

- 삭제 4줄 = 기존 `:1209-1211` 3줄 + `prev_bw` 1줄. 나머지는 추가.
- **`enriched["close"]` 는 프로덕션에서 항상 존재**한다(`_build_ohlc_df`, `:505-517` 가 `close` 열을 만들고
  `enrich` 는 `df.copy()` 로 시작한다 — `kojiro_indicators.py:74`).
- ⚠️ **F-1**: `close` 를 같은 `try` 에 넣으면 `close` 없는 스텁이 성분 ②까지 0 으로 떨어진다.
  현행 fail-safe 계약(`(0,0,fresh)`)과 동일하므로 의도적이며, `test_rank_components_failsafe_missing_columns` 가 그대로 이를 고정한다.

**(b) shadow stash 2곳**

- `:336` 옆에 `band_raw: dict[str, tuple] = {}` 1줄
- held 스탬프(`:404-411`) 직후 1줄 + 후보 확정(`:448-449`) 직후 1줄 —
  `band_raw[ticker] = (bar, prev_close, atr_val, float(bw.iloc[-1]), band_prev1, band_prev5, exp1, exp5, slope_raw, slope_pct, dist)`
  (필요한 값은 이미 그 스코프에 있거나 `enriched` 에서 1회 읽으면 된다. **`_candidates` 는 넓히지 않는다.**)

**(c) emit 1블록** — `:490` `ranked_final` 산출 뒤, `:491` `held_only` 산출 뒤 지점에서

```python
        try:
            observe_band(band_raw, ranked_final, held_only)
        except Exception:
            absorb_band_call_failure("prepare")
```

### 8.3 배포·검증 게이트

| 항목 | 기준 |
|---|---|
| 8영역·`scheduler.py` | `git diff HEAD --stat` 에 0건 |
| 신규 `DEFAULT_PARAMS` 키 | 0개(`test_g268_7` 초록) |
| `PARAM_RANGES` / `INT_PARAMS` | 편입 0(가중치는 이미 제외 상태 유지) |
| 회귀 | `tests/unit/engine/strategies` + `tests/unit/ast` 전량 → 백엔드 전체 |
| 뮤테이션 | `/close` 제거 · `_RANK_LOOKBACK` → 다른 상수 · `-6:-1` → `-5:-1`/`-6:` · `band_prev > 0` → `>=` · `0.0` → `1.0` 최소 5종 KILLED |
| 배포 모드 | `src/**` 변경 = **full**(backend 재시작). 장외 창(15:30~19:55 / 20:20~익일 07:45) 안에서만 push. **20:00~20:15 금지** |
| D+1 서명 | 07:5x `[kojiro_band_observe]` **10~25행** · 전 행 `bar` = 직전 영업일 · `exp1`/`exp5` 부호 불일치 건수 · `rank` 순서가 09:05 폴 순서(`_swing_buy_poll_loop`)와 일치 |

---

## 9. 위험 · 미해결 (결정 필요)

1. **F-1 (구조) — `_score_candidates` 의 `1e-12` 중립 임계는 손대지 않는다.** 성분 ①의 스케일이 ~1e6 배 줄지만
   여유가 9자릿수다(§3.4). 다만 "모든 후보 0.5" 가 관측되면 그것은 결함 서명이다 — `slope_pct` 원값을 shadow 가 남긴다.
2. **F-2 (조사, 자문 §7.3 F-3 인계) — `004690`(삼천리) 일봉 헤드 4거래일 stale.** 복원 전후 순위 비교에
   **오염된 입력이 섞인다.** cycle263 이후의 잔여 결손인지 확인이 선행되면 §5 표의 신뢰도가 올라간다.
   삼천리는 **보유 종목**이고 그 ATR 이 2ATR 손절선의 입력이다.
3. **③ `/3` 을 포함하는가.** 사용자 결정문·보고서 카드 ③ A 는 `/close` 와 5봉 분모만 명시하고 `/3` 은 적지 않았다.
   원설계 `screener.py:113` 에는 있고, **순위·점수에 영향이 0** 임이 증명됐다(§3.1).
   → 권고 = **포함**(원설계 문언 일치 + shadow 로그 단위 확보). **결정 필요 — 여기서 확정하지 않았다.**
4. **④ 성분 ③(신선도)을 원설계 `_days_in_current_stage` 로 바꾸는가.** 지금은 아핀 동치라 점수 동일이고,
   유일한 차이는 `6→1→2→1` 코호트뿐이다(§2.4). → 권고 = **비복원**(현행 유지). **결정 필요.**
5. **⑤ 밴드폭 최저 관문은 이번 범위 밖이다.** 자문 §3.1 이 비권고했고 사용자 제안도 "shadow 같이" 였다.
   이번 사이클에 `band_*_min` 류 키를 만들면 `test_g268_7` 이 즉시 RED 가 되고, 그것이 올바른 동작이다.
6. **⑥ 표본·귀인 한계.** 오늘 `kojiro` 는 **6/6 만석**(자문 §4.2)이라 복원의 즉시 효과는 0 이고,
   실효는 슬롯이 비는 첫날부터다. 종결 표본 N=17 로는 "복원이 수익을 개선한다"를 **주장할 수 없다** —
   이 사이클의 근거는 손익이 아니라 **"원설계와 다르게 계산되고 있다"는 사실 하나**다.
7. **⑦ 재현 미완.** §5 스크립트를 아직 **한 번도 돌리지 못했다**(§4.2). 배포 전에 1회 돌려
   "복원 전후 순위 표"를 확보하는 것이 사용자 보고의 약속(보고서 `:525` — "배포 전후 순위 변화를 실측 표로 비교")이다.
8. **⑧ 의미 전환 경고.** `[kojiro_band_observe]` 는 배포 이후에만 존재하고, 그 시점부터 랭킹 입력이 `exp5` 다.
   배포 전후 로그를 **합산 판독하면 안 된다**(cycle228 `would_pass` · cycle263 `skipped_fresh` 선례).

---

## 부록 A — 이 조사에서 실행한 결정적 시뮬레이션

| 스크립트 | 확인한 것 |
|---|---|
| `…/scratchpad/uc/sim.py` | 8종목 합성 풀에서 현행/`/3`/(가)만/(가)+(나) 4가지 순위 산출 → **`/3` 점수차 0.0** |
| `…/scratchpad/uc/sim2.py` | (가) 가격 스케일 격리(`[0,0.173,1]` vs `[0.5,0.5,0.5]`) · (나) 분모 격리(순위 역전) · 경계(`bw[-4]=0` → `9.0e10`) · `iloc[-6:-1]` 짧은 시리즈 거동 |
| `…/scratchpad/uc/sim3.py` | 기존 테스트 3개의 복원 후 정확한 기대값(`1.3333e-4`, `0.30434783`, T1>T2>T3 유지) + `1e-12` 여유 1.5e9 배 |

(세 스크립트는 `src/engine/kojiro_indicators.enrich` 를 그대로 import 해 돌렸다 — 별도 구현 재작성 없음.)
