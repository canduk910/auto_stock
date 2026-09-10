# cycle273-C 명세 — 고지로 후보 순위 성분 **원설계 복원** + shadow 관측 (D3)

- 작성 2026-09-10 · tdd-engineer(그룹 2) · **읽기 전용 사이클** — `src/**`·`tests/**`·`frontend/**` diff 0
- 사용자 결정(2026-09-10 목 19:5x): **"3. D3 고지로 순위계산을 원래 설계로 복원 — 복원 진행하자."**
  보고서 §9 제안 = 카드 ③ **A(둘 다 복원)** + shadow `[kojiro_band_observe]` **"같이"**
- 정본 = `_workspace/analysis/2026-09-10_cycle273_UC_kojiro_rank.md` ·
  `_workspace/domain_consult/cycle273_kojiro_rank_restore_20260910.md` ·
  원설계 `_workspace/kojiro_ma/kojiro/screener.py:113-120,134-141`
- 기준 트리 = **HEAD `1df6d7d`** (`git show HEAD:` 로만 읽었다 — 워킹트리의 cycle272 작업 무접촉)
- 보류 Red = `…/scratchpad/pending_tests/cycle273c/` (3 파일, DEST 는 각 파일 1행 헤더)

---

## 1. 한 줄 요약

고지로 후보 랭킹의 **성분 ①②만** 원설계 식으로 되돌린다. 자격 게이트·수량·손절·청산·가중치는
**한 글자도 바꾸지 않는다.** 바뀌는 것은 `_scanned_tickers` 의 **순서** 하나뿐이고,
그 순서를 `scheduler._swing_buy_poll_loop` 가 매수 처리 순서로 쓴다.

---

## 2. 무엇이 어긋나 있었나 (실측)

| 성분 | 원설계 (`screener.py`) | 현행 (`kojiro.py:1207-1211`) | 차이의 성질 |
|---|---|---|---|
| ① MACD3 기울기 | `(m3[-1]−m3[-4]) / 3 / close[-1]` | `(m3[li]−m3[pi])` | **`/close` 누락이 실질** — 성분①이 사실상 **주가 순위표**가 됐다(Spearman(성분①, 종가) = **+0.853**, 2026-09-10 후보 17종목). `/3` 은 순위·점수 영향 **정확히 0** |
| ② 띠폭 확장률 | `bw[-1] / mean(bw[-6:-1]) − 1`, 분모 ≤0 → **`0.0`** | `(bw[li]−bw[pi]) / (abs(bw[pi]) + 1e-9)` | 분모가 **단일봉 + 1e-9**. `band_width = |EMA20−EMA40|` 이고 6→1 전환은 그 교차 사건이라 **`bw[pi] ≈ 0` 은 예외가 아니라 상시**다 ⇒ 폭발이 상시 |
| ③ 진입 신선도 | `norm(−fresh_days)` | `norm(within − dist61)` | **어긋남이 아니다** — 양의 아핀 변환이고 min-max 는 아핀 불변 ⇒ 정규화값 동일. **복원 대상 아님** |

**분모 폭발의 규모** (자문 합성 코호트 N=1,031, 게이트 통과 후보만):

| 확장률 | p50 | p90 | p99 | MAX | `>10` 인 후보 |
|---|---|---|---|---|---|
| `exp1`(현행) | +1.37 | +10.33 | +136.8 | **+2,252** | **109 / 1,031 (10.6%)** |
| `exp5`(복원) | +0.86 | +2.04 | +2.95 | +4.53 | **0 / 1,031 (0.0%)** |

> 후보 10개 중 1개가 "확장률 1,000% 이상" 을 받고, 그 한 종목이 min-max 만점을 가져가
> 나머지를 전부 0 근처로 압축한다. **사용자가 벌하려던 "좁은 정배열" 을 현행이 상 주고 있었다.**

---

## 3. 확정 복원식 (자문 §3 그대로)

```python
    def _rank_candidate_components(self, enriched, stages_series: list, within: int) -> tuple[float, float, float]:
        """후보 랭킹 raw 3성분 (원설계 §9④): (macd3 기울기%, 띠폭 확장률, 신선도).

        원설계 정본 = `_workspace/kojiro_ma/kojiro/screener.py:113-120`.
        ① macd3_slope_pct = (macd3[-1]-macd3[-4]) / 3 / 종가 — **원(₩) 단위 금지.**
           `/종가` 누락이 이 성분을 주가 순위표로 만들었다(2026-09-10 실측 ρ=+0.853).
           `/3` 은 후보 공통 상수라 min-max 뒤 점수 불변이지만 원설계 단위를 지킨다.
        ② band_expansion 분모 = 직전 5봉 **평균**(`bw[-6:-1]`), `>0` 아니면 `0.0`.
           단일봉 분모 + `1e-9` 는 6→1 직후(정의상 bw≈0)에 폭발해 **좁은 밴드를 보상**했다.
           5봉 평균 자체가 하한 기구다 — 별도 엡실론·ATR·중앙값 하한을 두지 않는다.
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
        # ② 짧은 시리즈는 pandas 가 알아서 자른다(len 1 → 빈 슬라이스 → mean()=nan,
        #    `nan > 0` 이 False 라 0.0). ZeroDivisionError·IndexError 불가.
        band_prev = float(bw.iloc[-6:-1].mean())
        band_expansion = (float(bw.iloc[li]) / band_prev - 1.0) if band_prev > 0 else 0.0
        # ① 종가 정규화. close<=0/비수치는 성분①만 0.0 (밴드·신선도는 살린다).
        try:
            close = float(close_s.iloc[li])
        except (TypeError, ValueError):
            close = 0.0
        macd3_slope = (
            (float(m3.iloc[li] - m3.iloc[pi]) / _RANK_LOOKBACK) / close if close > 0 else 0.0
        )
        return (macd3_slope, band_expansion, fresh)
```

**손대지 않는 것** — 가중치 `0.4 / 0.3 / 0.3`(원설계와 이미 동일) · `_score_candidates`(min-max·`1e-12`
중립 임계 포함) · `check_buy_signal` / `calc_buy_quantity` / `check_exit_signal` · `DEFAULT_PARAMS`(신규 키 **0개**).

**`/3` 을 넣는 이유** (자문 §3.1 (나)) — 순위·점수 영향이 증명된 **0**이다. 원설계 문언에 있고,
사용자 지시가 "원래 설계로 복원" 이므로 **영향 0 인 항을 빼는 쪽이 재해석**이다. 실익은
shadow 로그의 `slope_pct` 가 "하루당 주가의 몇 %" 라는 **읽을 수 있는 단위**를 갖는 것
(실측 분포 p01 +4.55e-4 · p50 +2.30e-3 · p99 +4.70e-3 = 하루 0.05%~0.47%).
⚠️ **판독 규칙** — 배포 후 순위 변화를 `/3` 탓으로 귀인하면 **전부 오독**이다.

---

## 4. shadow 관측 `[kojiro_band_observe]`

### 4.1 leaf 계약 — `src/engine/kojiro_band_observe.py` (신규)

`src/engine/kojiro_gap_observe.py`(cycle268) **구조 그대로**, 이름만 band 계열:

- never-raise(본체 전체 단일 `try/except Exception`) · 반환 **`None` 고정** · read-only
- 실패는 `observer_trace.trace_observer_failure(MARKER, key, _cap)` — 무흔적 `pass` 금지(cycle258)
- cap = `KstDailyEmitCap`(자기 날짜 리셋 — `_reset_daily_state` override 신설 금지), 키 **`(ticker, role)`**
- `await` / DB / HTTP **0건**, 어떤 공유 dict 도 생성·변경하지 않는다(cycle242 G-242-8 동형)
- **임계 판정·차단 플래그를 넣지 않는다**(cycle228 `would_pass` 의미 반전 선례)
- **현행 식 반사실 순위(`rank_if_cur`)를 넣지 않는다** — leaf 가 `_score_candidates` 를 복제해야 하고,
  본체가 바뀌는 날 복제본이 조용히 어긋나 판독이 거짓말을 한다. `exp1`·`slope_raw` 원자료를 남기므로
  **오프라인 재계산으로 같은 정보를 얻는다**

**⚠️ 이름 충돌 (실측 — 반드시 지킬 것)**

| 심볼 | gap leaf | **band leaf** | 근거 |
|---|---|---|---|
| 관측 함수 | `observe_gap` | **`observe_band`** | `test_g268_3b`·`test_g268_4` 가 `observe_gap` Call 을 `kojiro.py` 전체에서 세어 **6** 을 강제 |
| 흡수기 | `absorb_call_failure` | **`absorb_band_call_failure`** | `test_g268_15b` 가 같은 이름의 Call 을 세어 **6** 을 강제 |
| 리셋 훅 | `reset_kojiro_gap_observe_cap` | **`reset_kojiro_band_observe_cap`** | `test_g268_16` |
| 마커/토큰 | `[kojiro_gap_observe]` | `[kojiro_band_observe]` | `test_g268_9` 는 **부분문자열** 검색 — `band` 는 `gap` 을 포함하지 않아 무충돌 |

### 4.2 발화 지점 = `prepare` 의 **점수 확정 뒤 1곳**

```
:336        band_raw: dict[str, tuple] = {}                       ← 지역 dict 선언
:404-411    held 스탬프 직후 ………………………… band_raw[ticker] = (...)   role=held 원자료
:448-449    rank_raw[ticker] = self._rank_candidate_components(...)
            └ 직후 ……………………………………… band_raw[ticker] = (...)   role=candidate 원자료
:486        scores = self._score_candidates(rank_raw, params)
:490        ranked_final = sorted(...)
:491        held_only = [...]
   ────────  ← 여기서 emit 1블록  try: observe_band(...) except Exception: absorb_band_call_failure("prepare")
:492        self._scanned_tickers = ranked_final + held_only
```

- `rank`·`score` 를 한 행에 담으려면 **구조적으로 이 자리뿐**이다(점수는 풀 전체가 모여야 계산된다).
  K1 §7.1 문언("후보 확정 루프 옆")은 이 구조 앞에서 성립하지 않는다 — **자문 미해결 ③, 이 명세가 채택**.
- 원자료는 **지역 `band_raw`** 에 담는다. `_candidates` 는 대시보드(`get_targets_status`)·
  `_apply_lot_units_cap`·`_effective_atr` 이 읽는 **공유 상태**라 관측을 위해 넓히지 않는다(자문 미해결 ④ 채택).
- emit 순서 = `ranked_final + held_only` ⇒ **로그 행 순서 = 그날 매수 처리 순서**.
- **`role=held` 행의 결측은 정보다** — held 스탬프는 ATR 밴드·스테이지 판별을 통과한 뒤에 찍히므로,
  밴드 밖으로 나간 보유 종목은 행이 없다. **결측을 0 으로 읽지 말 것.**

### 4.3 한 행 (필드 순서 = 파싱 계약)

```
[kojiro_band_observe] ticker= name= role= rank= bar= close= atr= atr_pct=
                      bw= bw_close_pct= bw_atr= bw_prev1= bw_prev5=
                      exp1= exp5= slope_raw= slope_pct= dist61= score=
```

stash 튜플(12원소, 순서 고정) =
`(name, bar, close, atr, bw, bw_prev1, bw_prev5, exp1, exp5, slope_raw, slope_pct, dist61)`.
파생 3필드(`atr_pct` = atr/close, `bw_close_pct` = bw/close×100, `bw_atr` = bw/atr)는 **leaf 가 계산**하고
분모 0 이면 `-`. `rank` 는 `ranked_final` 0-base(held 는 `-`), `score` 미상은 `-`(0.0 위장 금지).

| 필드 | 왜 필요한가 |
|---|---|
| `bar` | **F-3 stale 일봉을 사후 판별하는 유일한 근거.** `004690`(삼천리, **보유**)이 4거래일 stale 이고 그 ATR 이 2ATR 손절선의 입력이다 — `role=held` 행이 손절 입력의 신선도를 매일 잰다 |
| `exp1` **와** `exp5` | 둘 다 한 행에 있어야 시정의 전후 대조가 성립한다 |
| `slope_raw` **와** `slope_pct` | (가) 시정의 전후 대조 + "전 후보 성분① 0.5 중립" 결함 서명 감지 |
| `bw_close_pct`, `bw_atr` | 밴드폭 관문(카드 ①/②) 논의의 척도 후보를 **동시에** 적립 — 하나만 쌓으면 나중에 척도를 못 바꾼다 |

부피 ≈ **13 + 6 ≈ 19행/일** (cap 1행/(ticker,role)/일).

### 4.4 시그니처 (U-C §8.2(c) 3인자 스케치의 기계적 보정)

```python
def observe_band(
    band_raw: dict[str, tuple],
    ranked_final: list[str],
    held_only: list[str],
    scores: dict[str, float] | None = None,
) -> None
```
`score` 는 stash 시점에 존재하지 않으므로 4번째 인자로 받는다. **결정 변경이 아니라 배치의 귀결**이다.

---

## 5. Red 계약 ↔ 테스트 매핑

보류 파일(3):

| # | 보류 파일 | DEST |
|---|---|---|
| 1 | `pending_tests/cycle273c/test_cycle273_kojiro_rank_restore.py` | `tests/unit/engine/strategies/test_cycle273_kojiro_rank_restore.py` |
| 2 | `pending_tests/cycle273c/test_cycle273_kojiro_band_observe.py` | `tests/unit/engine/test_cycle273_kojiro_band_observe.py` |
| 3 | `pending_tests/cycle273c/test_cycle273_ast_kojiro_rank.py` | `tests/unit/ast/test_cycle273_ast_kojiro_rank.py` |

| 계약 | 테스트 | 현재 |
|---|---|---|
| C1 (G-273-1) 가격 스케일 불변 + **현행 반증 동시 고정** | `test_c1_g273_1_price_scale_invariance_with_legacy_counterexample` | **RED** |
| C2 (G-273-8) `/3` 무해성 | `test_c2_g273_8_rank_lookback_division_is_order_preserving` | PASS(현행에서도 성립 — 복원 뒤 유지 계약) |
| C3 (G-273-2) 분모 폭발 대조(쌍) | `test_c3_g273_2_denominator_explosion_pair` | **RED** |
| C4 (G-273-3) `band_prev` 정확히 0 → `0.0` | `test_c4_g273_3_band_prev_exactly_zero_returns_zero` | PASS(현행 우연 일치 — M4/M5 뮤테이션이 잡는다) |
| C5 (G-273-4) 짧은 시리즈 `{1,2,3,5,6}` | `test_c5_g273_4_short_series_no_exception[…]` (5) | PASS |
| C6 (G-273-5) close 가드 | `test_c6_…[3]` · `test_c6b_…` · `test_c6c_…` | **RED**(c6c 는 PASS) |
| C6-OQ5 비유한 성분 중립화 | `test_c6d_oq5_nonfinite_components_are_neutralized` | **RED — 승인 대기(§7 OQ-5)** |
| C7 기존 함수 갱신값 | `test_c7_rank_components_from_enriched_restored_values` | **RED** |
| C8 통합 순위 불변 | `test_c8_ranked_desc_components_still_monotone` | **RED** |
| C9 (G-273-6) **후보 집합 불변** | `test_c9_g273_6_candidate_set_independent_of_rank_components` | PASS(최상위 안전 계약 — 복원 뒤에도 PASS 여야 한다) |
| C10 (G-273-7) 진입/수량/청산 sha 핀 | `test_c10_g273_7_entry_exit_methods_pinned[3]` | PASS |
| C11 (G-273-9) 관측 차분 | `test_c11_…` · `test_c11b_prepare_emits_the_marker` | **수집 에러(모듈 미존재)** |
| C12 leaf 순수성 AST | `test_c12_…` 4건 | **RED** |
| C13 마커·토큰 격리 | `test_c13_g273_12_cap_key_is_ticker_and_role` · `test_g273_16b_…` | RED / PASS |
| 복원식 봉인 | `test_g273_18_…` · `test_g273_18b_…` · `test_g273_18c_…` | **RED**(18c PASS) |
| 이름 충돌 0 | `test_g273_17_gap_leaf_call_counts_unchanged`(6/6) · `test_g273_17b_…` | PASS / **RED** |
| 신규 키 0 · 가중치 무접촉 | `test_g273_19_…` · `test_g273_19b_…` | PASS |
| 8영역·scheduler 무접촉 | `test_g273_20_…` · `test_g273_20b_…`(<3,900L) | PASS |

**현재 RED 수** = 17 failed / 19 passed **+ leaf 파일 1 수집 에러(테스트 11함수·14항목 전부 차단)**.

### 5.1 갱신되는 기존 테스트 — **1개 함수**

`tests/unit/engine/strategies/test_kojiro_candidate_rank.py::test_rank_components_from_enriched`
입력 df 에 `close=10000` 열 추가 → `m3s == 1.3333333333333333e-4` · `be == 0.30434782608695654` · `fr == 4.0`
(= `4/3/10000`, `15/11.5−1` where `mean(10,10,12,14)=11.5`. **이 명세가 독립 재계산으로 확인**).

그대로 초록인 것(계산·실행으로 확인): `test_score_*` 5건 · `test_stage_transition_distance` ·
`test_rank_components_failsafe_missing_columns` · `test_get_scanned_tickers_ranked_desc`(T1>T2>T3 유지 —
복원값 slope_pct `2e-4`/`1e-4`/`0`, exp5 `0.391304`/`0.209302`/`0.0`) · `test_single_candidate_preserves_set_and_scores` ·
`test_rank_weights_*` 2건 · `test_check_exit_has_no_rank_logic` · `test_g268_7` · `test_g268_9` · `test_g268_11/11b` ·
`test_cycle264_scope_and_pins::test_c4_*`(kojiro 미포함).

### 5.2 반드시 걸리는 절차 가드

`tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::test_g223_12_other_strategy_files_diff_zero` —
`kojiro.py` 가 워킹트리에서 바뀌면 `_CYCLE228_STRATEGY_CONTENT_SHA`(현재 **빈 dict**)에 등재되지 않는 한 RED.
**절차** = 소스 확정 → `git diff HEAD -- src/engine/strategies/kojiro.py` 를 **눈으로 읽고** →
마지막에 `shasum -a 256` 산출 → 등재 → 커밋 → **즉시 후속 커밋으로 비운다**(자기소멸 관례).
8영역 sha 핀 **자매 4곳**은 이 사이클 **해당 없음**(8영역 diff 0) — cycle271 `4d88aa6` 이 비운 상태 유지.

### 5.3 뮤테이션 (최소 7종)

| # | 뮤테이션 | KILL 하는 테스트 |
|---|---|---|
| M1 | `/ close` 삭제 | C1 · `test_g273_18b` |
| M2 | `/ _RANK_LOOKBACK` → `/1` 등 | C7 · `test_g273_18` |
| M3 | `bw.iloc[-6:-1]` → `[-5:-1]` / `[-6:]` | C7(정확값 + 명시 반증 2줄) |
| M4 | `band_prev > 0` → `>= 0` | C4 · `test_g273_18`(GtE 금지) |
| M5 | 가드 반환 `0.0` → `1.0` | C4 |
| M6 | `close > 0` 가드 삭제 | C6 |
| M7 | `bw.iloc[-1]` → `bw.iloc[li]` | **등가 뮤테이션 — KILL 되지 않는 것이 정상.** 같은 DataFrame 유래라 항상 동일. 문서화로 처리 |

---

## 6. 배포·검증 게이트

| 항목 | 기준 |
|---|---|
| 접촉 파일 | `src/engine/strategies/kojiro.py`(≈ +25/−4) · `src/engine/kojiro_band_observe.py`(신규 ≈130L) · 테스트 3 |
| 8영역·`scheduler.py` | `git diff HEAD --stat` **0건** |
| 신규 `DEFAULT_PARAMS` 키 | **0개** (`test_g268_7` 초록) |
| `PARAM_RANGES`/`INT_PARAMS` | 편입 0 |
| 회귀 | `tests/unit/engine/strategies` + `tests/unit/ast` 전량 → 백엔드 전체 |
| 뮤테이션 | M1~M6 KILLED, M7 등가 문서화 |
| 문서 동기화(Phase 4.8, 커밋 전 필수) | `_workspace/00_leader_trading_rules.md:31` · `src/engine/strategies/CLAUDE.md:79` 의 랭킹 한 줄에 **분모 명시** (`0.4×(MACD3 3봉기울기/3/종가) + 0.3×(띠폭/직전5봉평균 − 1) + 0.3×6→1신선도`) + 루트 CLAUDE.md 표 1행 + `docs/HARNESS_CHANGELOG.md` append. **§2 가 보여준 대로 문서가 분모를 안 적어서 포팅이 어긋났다 — 이 갱신은 장식이 아니라 재발 방지다** |
| 배포 모드 | **full**(`src/**`). 장외 창 **15:30~19:55 / 20:20~익일 07:45**, **20:00~20:15 금지** |

### 6.1 D+1 서명 (배포 다음 영업일 07:5x~09:10)

| # | 서명 | 어긋나면 |
|---|---|---|
| S1 | `[kojiro_band_observe]` **10~25행** | 0행 = 미배선/흡수 → `observer_failed` WARNING 확인 |
| S2 | `role=candidate` 행 수 **==** "고지로 대순환 준비 완료" 의 `strict entry` 수 | 불일치 = 후보 집합 변경 = **계약 위반, 즉시 원복** |
| S3 | 전 행 `bar` == 직전 영업일 | 불일치 종목 = F-3 stale 일봉. `role=held` 면 2ATR 손절 입력 오염 |
| S4 | `exp5` 최댓값 **< 10** | ≥10 = 5봉 평균 하한 미작동 → `bw_prev5` 확인 |
| S5 | `exp1` ≥ 10 인 행 **존재**(합성 10.6%) | `exp1` 폭발 ∧ `exp5` 유한 **쌍**이 시정의 직접 증거 |
| S6 | `slope_pct` 대략 `1e-4`~`1e-2`, 전 후보 동일값 아님 | 전 후보 0.5 중립 = `_mm` 축퇴 = 결함 서명(여유 실측 1e9배라 정상은 불가) |
| S7 | `score` 가 `rank` 를 따라 비증가 | emit 순서와 정렬 기준 불일치 |
| S8 | `rank` 순서 == 09:05 `[swing_poll]` 처리 순서 | `_scanned_tickers` 와 로그가 다른 것을 본다 |
| S9 | `observer_failed` WARNING **0건** | ≥1 = 관측기 자기 실패(행위는 안전, 판독 결측) |

### 6.2 판독 규칙 (⚠️ 의미 전환)

1. **`[kojiro_band_observe]` 는 배포 이후에만 존재하고, 그 시점부터 랭킹 입력이 `exp5`·`slope_pct` 다.
   배포 전후 순위를 합산 판독하면 안 된다**(cycle228 `would_pass` · cycle263 `skipped_fresh` 선례).
2. 순위 변화를 **`/3` 탓으로 읽지 않는다**(점수차 0 증명).
3. **`bar` 열을 먼저 본다.** 다르면 그 종목의 변화는 복원이 아니라 stale 일봉의 결과다.
4. kojiro **만석이면** 이 표는 "지금의 매수 변화"가 아니라 "슬롯이 비는 첫날의 처리 순서" 다.

---

## 7. 롤백 — 코드 롤백 **단독**. 킬스위치 키는 만들지 않는다

`git revert <sha>` + full 배포. 근거 4 = ① 폭발 반경이 순서 하나(후보 집합 불변 = C9) ② kojiro 6/6 만석이라
즉시 위험 0 ③ 장중 긴급 되돌림 불필요(최악이 순서 오차 1건) ④ 1커밋 원복 = 사전 승인 범위 (c) 충족.
원복 완료 서명 = 다음 07:5x 에 마커가 **사라지는 것**.

**신규 params 킬스위치 금지** — (a) 신규 `DEFAULT_PARAMS` 키는 승인 + `domain-consult` 대상이고
`test_g268_7` 동결을 깬다 (b) **"on 위치가 알려진 결함" 인 다이얼**을 만드는 셈이다 (c) 두 식을 계속 유지해야 한다.

**장중 다이얼은 이미 있다** — `PUT /api/strategies/kojiro/params {"rank_w_macd3":0, "rank_w_band":0, "rank_w_fresh":1}`
(랭킹이 신선도 단독으로 **중립 축소**). `PUT` 은 **즉시** 반영, `strategy_config` SQL UPDATE 는 **다음 재시작에서만**
(보유 중 장중 재시작은 cycle232 D6 금지 ⇒ 장중 실효 수단은 PUT 뿐). 라우트는 **부분 병합**이라
가중치 3개만 보내도 다른 키를 지우지 않는다(자문 §6.2 라우트 본문 검증).

---

## 8. 미해결 (결정 필요) — 재해석하지 않고 올린다

| # | 항목 | 이 명세의 권고 |
|---|---|---|
| **OQ-1** | 자문 C2 원문의 "**비트 단위**(`==`)" 는 **실측 반증**됐다 — 무작위 500 풀에서 `_score_candidates` 값 **681개**가 비트 단위로 달랐다(최대 절대차 **2.220446049250313e-16** = 1 ULP, **순위가 달라진 풀 0/500**). 부동소수에서 `mm(v/c) == mm(v)` 는 수학적 항등이나 IEEE-754 항등이 아니다 | 계약을 **"고정 풀 `==` + 무작위 스윕 1 ULP 상한 + 순위 완전 동일"** 로 정정. 테스트는 그렇게 써 두었다 |
| **OQ-2** | C6 문언 정정 — "종목이 후보에서 사라지지 않는다" 는 **prepare 경로에서는 현재 도달 불가**하다. `prev_close = int(last["close"]); if prev_close <= 0: continue`(`kojiro.py:365-366`)가 이미 선행 차단한다 | 그래도 가드는 **넣는다**(공개 메서드 직접 호출 + 그 선행 게이트가 바뀌는 날의 무증상 삭제 차단). 계약 문언만 "단위 계약" 으로 정정 |
| **OQ-3** | **길이 0 시리즈**(`macd3` 열은 있고 행 0)는 `m3.iloc[-1]` 이 `IndexError`. 현행도 동일하며 회귀가 아니고, `KOJIRO_MIN_REQUIRED=80` 이라 도달 불가 | **범위 밖**으로 기록만 하고 테스트로 강제하지 않는다(원설계에 없는 방어 발명 금지) |
| **OQ-4** | `math.isfinite` 출력 가드(자문 미해결 ⑤) — 원설계에 **없는 추가 방어** | **넣기 권고.** `nan` 하나가 `_score_candidates` 의 min/max 를 오염시켜 **전 후보 점수를 nan** 으로 만든다. 미승인이면 `test_c6d_oq5_…` 를 **삭제**하고 이 결정을 여기 남긴다(남기면 영구 RED) |
| **OQ-5** | 배포 전 U-C §5.1 `rerank.py` 1회 실행(실제 후보군 복원 전후 순위 표) | **보고서 `:525` 가 사용자에게 한 약속.** 이 워크플로는 읽기 전용이라 실행하지 못했다 — 메인 세션이 배포 전 1회 |
| **OQ-6** | F-3 `004690` 4거래일 stale 을 선행 조사로 묶는가 | **D5(cycle273-D)가 이미 그 시정이다.** 순위 표를 읽을 때 `bar` 확인이 선행 |
| **OQ-7** | 사이클 번호 `cycle273` 확정(U-A/U-B 와 공유 여부) | 메인 세션 결정 — 파일명·마커 주석이 전부 그 번호를 쓴다 |

**범위 밖 (이번 사이클 아님)** — 밴드폭 최저 **관문**(카드 ①/②). `band_*_min` 류 키를 만들면
`test_g268_7` 이 즉시 RED 가 되며 **그것이 올바른 동작**이다. 성분②↔③ 상쇄(가중치)도 사용자 결정 항목.

---

## 9. 한계 (주장하지 않는 것)

- **"복원이 더 번다" 를 이 사이클은 주장하지 않는다.** 종결 표본 N=17, 검정력 없음.
  근거는 손익이 아니라 **"원설계와 다르게 계산되고 있다" 는 사실 하나**다.
- kojiro **6/6 만석**이라 즉시 효과는 0이고, 실효는 슬롯이 비는 첫날부터다.
- 합성 코호트는 `enrich` 는 진짜지만 가격 시계열이 GBM 합성이다 — 갭·상하한가·거래정지가 없다.
