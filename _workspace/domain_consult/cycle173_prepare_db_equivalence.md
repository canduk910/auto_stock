# 사이클 173 자문 — 5 전략 prepare() 일봉 source DB 우선 전환의 매수 target 동등성 (행위 보존)

> 작성: domain-expert (데이/스윙 트레이더 출신 컨설턴트)
> 요청자: team-leader
> 산출 분류: HIGH 카드 (매수 target 직접 경로) — 자문 + 동등성 게이트 설계 (코드 변경 0)
> 선행: 사이클 171 (저녁 funnel) / 사이클 172 (220일 backfill + `get_recent_daily_normalized` 어댑터 정의)

---

## 질문 요약

각 전략 `prepare()` 의 일봉 source 를 `fetch_daily_candles(ticker, days)` (KIS REST 실시간) → `get_recent_daily_normalized(ticker, days, *, min_required)` (사이클 172 DB 우선 어댑터, DB 부족 시 KIS 폴백) 로 전환할 때:

> **"DB-source 일봉으로 계산한 매수 target 이 KIS-source 일봉으로 계산한 매수 target 과 동일한가? 동일하지 않다면 어디서·왜·얼마나 어긋나고, 무엇을 게이트로 막을 것인가?"**

핵심 트레이더 판정 4 쟁점: (1) 당일 부분봉 prev_idx 정규화, (2) **수정주가 조정 시점 divergence (silent 매수 target 결함 최대 위험)**, (3) VCP 220일 → effective_ema_long 의도적 행위 변화, (4) DB miss → KIS 폴백 경계의 min_required 적정성.

---

## 결론 한 줄 요약 (team-leader 채택 판단용)

> **쟁점 1 = 실효 동등 (boot 07:55 경로 한정 — 장중 reprepare 는 비동등이나 *DB 가 더 정확*). 쟁점 2 = 비동등 위험 실재 (수정주가 divergence), 단 빈도 낮고 완화 가능 — `flng_cls_code` + `prtt_rate` 기반 "최근 N일 내 락 발생 종목" 강제 KIS 폴백 게이트가 silent 결함의 유일한 확실한 방어. 쟁점 3 = VCP 는 (가) 현행 100일 실효 유지 권고 (행위 보존 사이클 = 173, 220 혜택은 backtest 동반 별도 사이클). 쟁점 4 = min_required 를 "전략별 필수 lookback +2~3 안전 마진" 으로 상향 권고 (현재 §3 값 일부 과소).**

가장 중요한 권고: **수정주가 divergence 는 동등성 회귀 테스트로 "잡히지 않는" 종류의 결함**이다 (정상 종목 fixture 로는 100% 통과하나 운영에서 액면분할 종목만 silent 하게 어긋남). 따라서 동등성 게이트는 *테스트*가 아니라 *런타임 폴백 규칙*으로 박아야 한다.

---

## 사전 확인한 코드/정본 사실 (자문 근거)

| 항목 | 확인 결과 | 출처 |
|------|----------|------|
| 어댑터 `get_recent_daily_normalized` | DB 충분 시 row 의 `raw` JSONB (KIS 원본 키 보존) 그대로 반환 → `c.get("stck_clpr")` 무변경. raw 부재 row 는 row 자체 (graceful). DB 부족 시 `fetch_daily_candles` 폴백 | `src/db/stock_master_daily.py:452-501` |
| `min_required` 기본 | `None → max(days // 2, 10)` | 동 L470-471 |
| DB 적재 수정주가 기준 | `fetch_daily_candles_ranged` / `_backfill` 모두 `FID_ORG_ADJ_PRC="0"` (수정주가) | `src/api/condition.py:499, 616` |
| KIS fetch 수정주가 기준 | `_fetch_daily_candles_and_cache` 도 `FID_ORG_ADJ_PRC="0"` | `src/api/condition.py:499` |
| **KIS 정본 FID_ORG_ADJ_PRC 의미** | **"수정주가 원주가 가격 여부 (0:수정주가 1:원주가)"** — 필수 파라미터 | KIS MCP 정본 `inquire_daily_itemchartprice.py` docstring |
| **KIS 정본 응답 락 관련 키** | output2 에 `flng_cls_code`(락 구분 코드) + `prtt_rate`(분할 비율) + `revl_issu_reas`(재평가사유코드) 포함 | KIS MCP 정본 `chk_inquire_daily_itemchartprice.py` COLUMN_MAPPING |
| 5 전략 prev_idx 분기 | 전 전략 `prev_idx = 1 if candles[0].stck_bsop_date == today_str else 0` 동일 | VB:214 / LTV:225 / donchian:264 / BFB:248 / VCP:267 |
| **donchian 이미 DB 우선** | `get_donchian_high(ticker, days)` DB 헬퍼 우선 + KIS fallback (사이클 123). 단 **EMA·거래대금은 여전히 KIS candles 의존** | `donchian_swing.py:286-335` |
| 전략별 fetch_days (= days 전달값) | VB/LTV `k_period+2`(~22) / donchian `max(long_ma+5, donchian+5)+1`(~66) / BFB `pole_max+flag_max+atr+10`(~44) / VCP `min(ema_long+base_max+10, 100)`(100) | 각 전략 prepare 본문 |
| VCP effective_ema_long | `min(ema_long(120), available_len - uptrend(20) - 5)`. KIS 100일 → ~75. DB 220일 → 120 (원설계) | `vcp_breakout.py:270` |

---

## 쟁점 1 — 당일 부분봉 (prev_idx) 정규화 동등성

### 트레이더 시각

5 전략의 prev_idx 분기의 본질은 한 줄이다: **"오늘 봉은 아직 안 끝났으니(부분봉) 쓰지 말고, 직전 확정봉(D-1)을 '전일'로 삼아라."** 트레이더가 장중에 차트 볼 때 "오늘 봉은 미완성이라 어제 종가/고저로 신호 판단한다"는 본능 그대로다.

핵심은 **두 source 가 동일한 D-1 확정봉을 '전일'로 쓰게 되느냐**이고, 답은 시나리오에 따라 갈린다.

| 시나리오 | KIS fetch (현행) | DB (사이클 173) | 실효 전일 봉 |
|----------|-----------------|----------------|-------------|
| **boot 07:55 (장 시작 전)** | candles[0] = D-1 (오늘 봉 아직 없음) → prev_idx=0 | DB candles[0] = D-1 (16:00 적재) → prev_idx=0 | **양쪽 D-1 동일** ✅ |
| **장중 reprepare 09:30+ (`_reprepare_breakout_if_empty`)** | candles[0] = 오늘 부분봉 → prev_idx=1 → 전일=D-1 | DB candles[0] = D-1 (당일 미적재) → prev_idx=0 → 전일=D-1 | **양쪽 실효 D-1 동일** ✅ (경로는 다르나 결과 같음) |

**핵심 통찰**: prev_idx 정규화는 정확히 "당일 부분봉을 버리고 D-1 을 쓰는" 장치다. DB 는 16:00 적재라 애초에 당일 봉이 없으므로 *정규화 자체가 불필요*하지만 (prev_idx=0), 결과적으로 "전일 = D-1" 이라는 **동일한 실효 데이터**에 수렴한다. KIS fetch 가 장중에 candles[0]=오늘부분봉을 받아 prev_idx=1 로 한 칸 밀어도, 그 한 칸 민 결과가 곧 D-1 이다. 두 경로는 같은 봉을 가리킨다.

### 위험 시나리오 (동등성 깨지는 경우)

1. **장중 16:00 적재 *이후* reprepare (이론적, 현실 희박)**: 만약 어떤 경로가 16:00 daily task 완료 *후* 같은 날 장중에 reprepare 한다면, DB candles[0] = "오늘(=방금 적재된 당일 종가)" 이 되어 `stck_bsop_date == today_str` → prev_idx=1 → 전일=D-1. 이때는 KIS(장 마감 후이므로 당일 확정봉) 와도 동일. **무해**. 단 운영상 16:00 이후 장중 reprepare 는 발생 안 함 (장 마감).
2. **DB 적재 지연 race (16:00 task 가 아직 D-1 을 안 넣은 boot 직후)**: 사이클 163 `count_active` 가드 + 사이클 158 재시도 hook 으로 1차 방어되나, DB 가 D-2 까지만 있고 D-1 미적재 상태에서 prepare 가 돌면 **DB 의 "전일" = D-2 ≠ KIS 의 "전일" = D-1**. → **비동등 (이건 진짜 위험)**. min_required 가 이걸 못 잡는다 (개수는 충분하나 *최신성*이 어긋남). → 쟁점 4 + 게이트에서 별도 방어 필요 (아래 "max_bas_dd 최신성 가드" 권고).

### 정량 판정

- **boot 07:55 경로 (= 운영의 정상 경로, 95%+)**: **완전 동등**. 게이트 PASS.
- **장중 reprepare 경로**: **실효 동등 (DB 가 오히려 더 정확** — KIS 는 부분봉 노이즈 한 칸을 받았다 버리는 반면 DB 는 애초에 깨끗한 D-1). 게이트 PASS.
- **DB 최신성 미달 (D-1 누락) 경로**: **비동등** — 단 이건 부분봉 문제가 아니라 *적재 신선도* 문제. 게이트에서 `max_bas_dd(ticker) >= 직전영업일` 검사로 별도 차단 권고.

**옵션 정렬**:
- (A) prev_idx 분기 유지 + DB 신선도 가드 추가 (권고) — 코드 변경 최소, 양 경로 모두 안전.
- (B) DB 전환 시 prev_idx 분기 제거 (DB 는 당일 봉 없으니 불필요) — **비채택**. 폴백 시 KIS candles 는 여전히 당일 부분봉 포함 → 분기 제거하면 폴백 경로에서 부분봉 오염. 분기는 폴백 안전망으로 반드시 유지.
- (C) 어댑터가 당일 봉을 강제 제거해서 반환 — **비채택**. 어댑터 책임 비대화 + 폴백 KIS 경로 일관성 깨짐.

---

## 쟁점 2 — 수정주가 조정 시점 divergence (★ 최대 위험, silent 매수 target 결함)

### 트레이더 시각 (이게 왜 무서운가)

이건 동등성 자문에서 **유일하게 "테스트로는 절대 못 잡는" 종류의 결함**이다. 트레이더 본능으로 풀면:

> "DB에 쌓아둔 과거 봉은 *그때 그 시점의 수정주가 기준*으로 박제돼 있다. 그런데 어제 액면분할 5:1 이 떴으면, KIS 는 오늘 조회하는 순간 *과거 전체를 5분의 1로 재조정*해서 내려준다. DB의 박제된 과거 봉(분할 전 큰 숫자)과 KIS의 오늘 재조정 과거 봉(분할 후 작은 숫자)이 5배 어긋난다. 신고가·EMA·base·pole 다 틀어진다."

KIS `FID_ORG_ADJ_PRC="0"` 의 의미를 정본에서 재확인했다: **"0:수정주가"** — 즉 KIS 는 조회 *호출 시점* 의 수정 계수로 과거 전체를 소급 재계산해서 준다. 이게 수정주가의 본질이다. "수정주가"는 *영구 불변값이 아니라 조회 시점 의존값*이다.

- **DB**: 일봉을 *적재 당일의 수정 계수*로 누적 보관. 액면분할 이전에 적재한 봉은 분할 전 큰 숫자로 남아있음. 16:00 daily task 는 증분(D-1 1건)만 추가하므로 *과거 봉을 재조정하지 않는다*.
- **KIS fetch**: 매 호출이 *그 순간*의 수정 계수로 220일/100일 전체를 재조정.

→ **최근 락 이벤트(액면분할/병합/유상증자 신주락/대규모 배당락)가 발생한 종목**에서, DB 의 과거 봉(락 전 계수)과 KIS 의 과거 봉(락 후 계수)이 어긋난다.

### 임팩트 — 전략별로 얼마나 치명적인가

| 전략 | 매수 target | divergence 임팩트 | 심각도 |
|------|------------|-------------------|--------|
| **donchian** | 직전 20일 신고가 돌파 | `get_donchian_high` 는 이미 DB (사이클 123) → **현행에서도 같은 위험 이미 존재**. 단 EMA(60일)·거래대금은 KIS candles 의존 → 173 전환 시 EMA 도 DB 화 → 분할 종목은 EMA 계산이 락 전후 봉 혼재로 왜곡 | **HIGH** (신고가는 절대수준 직접 비교) |
| **VB / LTV** | 전일 Range × K (노이즈 비율) | K(노이즈)는 *비율*이라 분할에 robust (high-low가 같이 스케일). 단 prev_range(절대값)·prev_close 등록값이 락 전 봉이면 target_offset 절대값 왜곡 + scanner `ticker_prev_close` 오염 | **MEDIUM** (비율 robust, 절대값만 위험) |
| **BFB** | flag_high 돌파 + pole +20% | pole 상승률은 비율(robust)이나, flag_high(절대값) 등록 + pole_start~pole_high 측정이 락 봉 혼재 시 왜곡 | **MEDIUM~HIGH** |
| **VCP** | base_high 돌파 + EMA 정렬 + base 깊이 | EMA 정렬(상대)·base 깊이(비율)는 일부 robust 하나, 220일 long lookback 이라 *락 봉이 윈도우에 포함될 확률 가장 높음* + base_high(절대값) | **HIGH** (가장 긴 lookback) |

비율 기반 신호(K, pole%, base depth%)는 락에 어느 정도 robust 하지만, **절대값 비교 신호(신고가, flag_high, base_high)는 직격탄**. 그리고 5 전략 모두 절대값 비교를 핵심에 두므로 전 전략 위험.

### 빈도 — 실전 감각

한국 시장에서 액면분할/병합/유증 신주락은 *개별 종목 기준 연 0~2회*, *전체 유니버스(KOSPI200∪KOSDAQ150 348종목 + VB/LTV/BFB ~2,800 후보) 기준 일 평균 수 종목*. 즉:
- 임의의 한 종목이 "오늘 락 영향권(최근 220일 내 락 발생)"일 확률은 낮다 (수 %).
- 그러나 *매일 전체 후보를 스캔*하므로 **매일 몇 종목은 반드시 락 영향권에 있다**. 후보 풀이 클수록(VCP 348, VB 2,800) 절대 건수 증가.
- 배당락은 더 빈번(분기/연 배당락)하나 조정폭이 작아(보통 1~3%) 임팩트는 작다. 단 고배당주 연말 배당락은 5%+ 도 있어 무시 못 함.

→ **"드물지만 매일 존재하고, 발생하면 매수 target 이 silent 하게 틀어지는"** 전형적 long-tail silent 결함. 빈도가 낮아 회귀 테스트 fixture 에 안 잡히고, 임팩트가 커서 한 번 터지면 잘못된 가격에 매수/미매수.

### 완화책 (★ 자문의 핵심 — 우선순위순)

**완화책 1 (필수 권고) — 락 이벤트 종목 강제 KIS 폴백 게이트**

어댑터 또는 prepare 단에서, DB candles 의 `flng_cls_code`(락 구분 코드) 또는 `prtt_rate`(분할 비율) 가 **최근 N일(= 해당 전략 lookback) 윈도우 내에 락 발생을 표시**하면, *그 종목만* DB 를 버리고 KIS fetch 로 강제 폴백한다. KIS 는 호출 시점 재조정이라 락 전후 일관성 보장.

- `flng_cls_code` 비-기본값(락 있음) 또는 `prtt_rate != 1.0`(분할/병합) 행이 윈도우에 1개라도 있으면 → KIS 폴백.
- 근거: KIS 정본 응답에 `flng_cls_code` + `prtt_rate` 가 *이미 포함*되고 DB `stock_master_daily` 가 이를 컬럼으로 보관(`flng_cls_code` / `prtt_rate`, 사이클 122 스키마 확인). 데이터가 이미 손 안에 있다 — 추가 KIS 호출 0건으로 탐지 가능.
- 비용: 락 영향권 종목만 KIS 폴백 → 일 평균 수 종목 → KIS 부하 무시 가능 (사이클 17 LMS chain 안전).
- **이것이 silent 결함의 유일한 확실한 런타임 방어**. 테스트가 아니라 규칙으로 박는다.

**완화책 2 (보강) — 락 발생 시 재적재 (16:00 daily task)**

16:00 daily task 가 증분 적재 시, 해당 종목의 *오늘 봉* `flng_cls_code`/`prtt_rate` 가 락을 표시하면 → 그 종목은 증분이 아니라 *전체 윈도우(220일) 재backfill*. KIS 재조정값으로 과거 봉 덮어쓰기. 이러면 다음날 boot 부터 DB 가 자동 정합. (단 사이클 81 G-AST1 = `raw` 덮어쓰기 금지 영속과 충돌 검토 필요 — `stock_master_daily.raw` 는 별개 테이블이라 G-AST1(stock_master.raw) 영역 아님. 확인 권고.)

- 완화책 1(런타임 폴백)이 즉시 방어, 완화책 2(재적재)가 다음날 근본 정합. **둘 다 권고 (1 우선, 2 후속)**.

**완화책 3 (대안, 비권고)** — DB 전체를 매일 재backfill. **비채택**. 220일 × 348종목 × 3윈도우 = KIS 호출 폭증, 사이클 172 가 증분 설계한 의도 정면 위배.

### 현 코드와의 충돌

- **사이클 81 G-AST1 (raw JSONB 덮어쓰기 금지)** 과 완화책 2 의 잠재 충돌 — 단 G-AST1 은 `stock_master.raw` 영역이고 `stock_master_daily.raw` 는 별개. 완화책 2 는 `stock_master_daily` 재적재이므로 영역 외일 가능성 높으나, **tdd-engineer 가 AST 가드 영역 확인 의무**.

### 정량 판정

> **수정주가 divergence = 비동등 위험 실재. 빈도 낮으나(일 수 종목) 임팩트 크고(매수 target 직격) 테스트로 안 잡힘. → 완화책 1(flng_cls_code/prtt_rate 기반 강제 KIS 폴백 게이트) 필수 + 완화책 2(락 종목 재적재) 후속.** 이 게이트 없이 173 을 그냥 전환하면 silent 매수 target 결함을 운영에 심는다.

---

## 쟁점 3 — VCP 220일 → effective_ema_long 행위 변화

### 트레이더 시각

이건 쟁점 1~2 와 성격이 다르다. 1~2 는 "같아야 하는데 어긋나는" 동등성 문제고, 3 은 **"의도적으로 달라지는(개선)" 행위 변화**다.

현재 VCP 는 KIS 100일 한도 때문에 `effective_ema_long = min(120, 100 - 20 - 5) ≈ 75` 로 *축소된 EMA* 를 쓴다 (사이클 33/48 한도 우회). 이건 미네르비니 원설계(120 EMA = 약 6개월 추세)를 **75일(약 3.5개월)로 강제 단축한 타협값**이다. DB 220일 확보 시 `available_len=220 → effective_ema_long = min(120, 220-25) = 120` → **원설계 복원**.

즉 VCP 만은 데이터가 늘어나서 *추세 필터가 더 길어지고 더 엄격해진다*. 트레이더 관점에서 120 EMA 정렬 + 1개월 우상향은 75 EMA 보다 *더 강한 추세*를 요구 → **후보가 줄고(더 깐깐), 잡힌 후보의 질은 올라간다**. 이건 좋은 변화지만 **매수 target(어떤 종목이 base_high 돌파 후보가 되는가)이 바뀐다** = 행위 변화.

### 위험 시나리오

- 173 에서 동등성 게이트를 "DB-source == KIS-source" 로 걸면, **VCP 는 이 게이트를 의도적으로 통과 못 한다** (75 EMA vs 120 EMA → 다른 후보). 게이트가 거짓 빨강(false red)을 낸다.
- 반대로 220 을 그냥 수용하면, *검증 없이 매수 후보 풀이 바뀐다* — backtest 없이 라이브 행위 변경은 위험(사이클 다수 "행위 보존" 원칙 위배).

### 옵션 정렬

- **(가) 173 에서 VCP 는 현행 100일 실효 유지 (행위 보존)** — VCP 만 `days=100` (또는 `min(fetch_days, 100)`) 캡 유지 + effective_ema_long ≈75 보존. DB 220 backfill 은 사이클 172 에서 이미 적재됐으되 *173 은 안 쓴다*. 220 혜택(원설계 EMA 복원)은 **별도 튜닝 사이클**에서 backtest 동반 적용. → **권고**.
  - 동등성 게이트: VB/LTV/donchian/BFB 와 동일 "DB==KIS" 게이트 적용 가능 (days 동일하면 동일 결과).
  - 장점: 173 = 순수 행위 보존 (source 만 DB 화, 결과 불변) → 회귀 위험 최소 + 게이트 단순.
- **(나) 173 에서 220 수용 (VCP 행위 의도 변화)** — effective_ema_long=120 원설계 복원. 동등성 게이트에서 VCP 예외 처리 + EMA 길이 변화 명시 + **backtest 필수**.
  - 단점: 173 이 "데이터 plumbing 행위 보존" + "VCP 전략 개선" 두 가지를 섞음 → 회귀 분석 복잡 + 라이브 행위 변경 검증 부담. team-leader 의 "행위 보존 사이클" 원칙과 충돌.

### 정량 판정

> **(가) 권고 — VCP 도 173 에서는 100일 실효 유지(행위 보존). 220 혜택은 사이클 174+ 별도 튜닝 사이클에서 backtest(외부 MCP 12 job) + domain 재자문 후 적용.** 이유: (1) 173 의 목적은 "source 전환 행위 보존" 이지 "VCP 개선"이 아니다 — 한 사이클에 두 의도 금지. (2) EMA 길이 변경은 매수 후보 풀을 바꾸는 진짜 파라미터 변경 → 자동 적용 화이트리스트(`PARAM_RANGES`)에도 없는 구조 변경 → backtest 없이 라이브 금지. (3) VCP 만 예외 두면 게이트 설계가 복잡해지고 회귀 분석이 흐려진다.

**현 코드와의 충돌**: VCP prepare 의 `fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX=100)` 라인 — 어댑터 전환 시 이 cap 을 유지하면 (가). cap 을 풀면 (나). **(가) 채택 시 `days=fetch_days`(=100 cap) 그대로 어댑터에 전달 + min_required 도 100 기준** → DB 220 있어도 어댑터가 days=100 슬라이스만 반환하도록 (어댑터 `get_recent_daily(ticker, days)` 가 days 만큼만 반환하는지 확인 의무 — DESC 최신 100 → effective_ema_long 동일 ≈75).

---

## 쟁점 4 — DB miss → KIS 폴백 경계 (min_required 적정성)

### 트레이더 시각

신규상장·적재 누락·거래정지 후 재개 종목은 DB 일봉이 부족하다. 이때 어댑터가 KIS 폴백한다 — 이건 안전망으로 맞다. 문제는 **"몇 개 미만이면 폴백할지(min_required)"의 임계**다. 너무 낮으면 *부족한 DB 로 잘못된 target 계산* (예: 60일 EMA 인데 DB 35개만 있어도 폴백 안 하고 35개로 EMA 계산 → 왜곡), 너무 높으면 *불필요한 KIS 폴백 남발* (LMS chain 부담).

요청 §3 의 전략별 min_required 제안값을 전략 필수 lookback 과 대조:

| 전략 | 필수 lookback (코드 실측) | §3 제안 min_required | 적정성 판정 |
|------|--------------------------|---------------------|------------|
| **VB** | prev_idx + k_period + 1 (~22, k_period 기본 약 20) | 22 | **경계선** — 노이즈 평균에 k_period 봉 전부 필요. 22 면 prev_idx=1 시 정확히 빠듯. **+2 마진 → 24 권고** |
| **LTV** | VB 동일 + consecutive_limit(2) 검사 (~22) | 22 | **경계선** — VB 동일. **24 권고** |
| **donchian** | `long_ma_period + 1` = 61 (EMA 60 + 신고가 20) | 60 | **과소** — 코드가 `len < long_ma_period+1=61` 컷. 60 이면 폴백 안 했는데 61 미달 → 그 다음 컷에서 탈락(매수 기회 손실)하거나 EMA 부정확. **63 권고 (61 + prev_idx + 마진)** |
| **BFB** | prev_idx + pole_max + flag_max + 2 (~33, 본문 명세 30~35) | 35 | **적정** — 단 fetch_days=44 라 DB 44 권고도 가능. 35 유지 가능하나 **37 권고 (마진)** |
| **VCP** | (가) 채택 시 effective_ema_long+uptrend+5 ≈ 100 / available_len ≥ 100 필요 | 120 | **(가) 채택 시 과대** — 100일 실효면 min_required=100 이 맞음. 120 이면 DB 220 중 120 미만일 때 불필요 폴백. **(가) 채택 시 100, (나) 채택 시 145(120+20+5) 권고** |

### 위험 시나리오

- **min_required 과소 → 부족 DB 로 계산**: 가장 위험. 어댑터가 "충분하다" 판단(`len >= min_required`)했으나 실제 전략 필수치 미달 → 폴백 안 하고 부족한 봉으로 EMA/신고가 계산 → **silent 왜곡**. donchian 60 vs 필수 61 이 정확히 이 함정.
- **min_required 과대 → 폴백 남발**: DB 가 충분한데도 임계 못 넘어 KIS 호출 → LMS chain 부담. 단 충분한 종목은 어차피 임계 넘으므로 실제로는 신규/누락 종목만 폴백 → 부담 작음. 과대가 과소보다 **훨씬 안전** (보수적).

### 폴백 시 결과 동등성

- 폴백 발생 = DB 부족 = *그 종목은 처음부터 KIS 로 계산*. 동등성 비교 대상이 아니다 (KIS == KIS). 단 폴백 KIS candles 는 당일 부분봉 포함 가능 → prev_idx 분기 유지 필수 (쟁점 1 옵션 A 와 정합).
- **수정주가**: 폴백 시 KIS 호출은 조회 시점 재조정값 → 락 일관성 자동 보장 (쟁점 2 의 완화책 1 과 같은 효과). 즉 *폴백된 종목은 수정주가 divergence 위험도 없다*. 신규상장 종목은 락 이력도 짧아 이중 안전.

### 정량 판정 + 권고 min_required

> **min_required 를 "전략 필수 lookback + 2~3 안전 마진" 으로 상향. 과소(특히 donchian 60→63)는 silent 왜곡 직결이라 반드시 시정. 과대는 보수적이라 안전.** 권고값:

| 전략 | 권고 min_required | 근거 |
|------|------------------|------|
| VB | **24** | k_period(~20) + prev_idx(1) + 마진(3) |
| LTV | **24** | VB 동일 |
| donchian | **63** | long_ma(60) + 1 컷 + prev_idx + 마진 (60 은 과소, 필수 61 미달 silent 왜곡) |
| BFB | **37** | pole_max+flag_max+2(~33) + 마진 |
| VCP (가) | **100** | effective lookback = 100일 실효 (220 미사용) |

`min_required = None` 의 기본 `max(days//2, 10)` 은 **전 전략 부적합** (donchian days=66 → 기본 33 → 필수 61 미달인데 폴백 안 함 = silent 왜곡). **각 전략 prepare 가 명시적으로 min_required 전달 의무** (None 의존 금지).

---

## 전략별 동등성 게이트 설계 (tdd-engineer 입력)

게이트의 목적: **"DB-source 일봉으로 계산한 매수 target == KIS-source 일봉으로 계산한 매수 target"** 을 회귀 테스트로 고정 (정상 종목 한정). + 락/신선도/폴백 경계의 *행위 규칙*을 별도 가드.

### 공통 게이트 (VB / LTV / donchian / BFB)

| 게이트 | 검증 내용 | 등급 |
|--------|----------|------|
| **G-EQ-1 (HIGH)** | 동일 fixture (정상 종목, 락 없음) 에 대해 DB-source prepare 결과 `_targets`/`_candidates`/`_scanned_tickers` 가 KIS-source 와 **원소·값 동일** (신고가/target_offset/flag_high/base_high 등 매수 target 키 bit-동일) | HIGH |
| **G-EQ-2 (HIGH)** | prev_idx 경계 — DB(당일 미적재, prev_idx=0) 와 KIS(당일 부분봉, prev_idx=1) 가 **동일 D-1 을 전일로** 사용 → 같은 target. boot 경로 + 장중 경로 2 fixture | HIGH |
| **G-EQ-3 (HIGH, 락 게이트)** | 락 fixture (`flng_cls_code` 비기본 OR `prtt_rate != 1.0` 가 윈도우 내 존재) → **그 종목은 KIS 폴백 강제** (DB 사용 안 함). 폴백 호출 발생 검증 + 폴백 결과 사용 검증 | HIGH |
| **G-EQ-4 (신선도 가드)** | DB 최신 봉(`max_bas_dd`)이 직전 영업일 미만 → 해당 종목 KIS 폴백 (D-1 누락 silent 차단, 쟁점 1 위험3) | MEDIUM |
| **G-EQ-5 (min_required)** | DB len < 전략별 권고 min_required → KIS 폴백 발생. len == min_required-1 (경계) fixture | HIGH |
| **G-EQ-6 (폴백 동등)** | DB 완전 miss → KIS 폴백 → 결과가 현행 KIS-only prepare 와 동일 (회귀 보존) | MEDIUM |
| **G-SAFETY-1 (HIGH)** | risk.on_tick / order_engine / realtime / auth diff 0 + check_exit_signal 호출 0건 (prepare = 매수 진입 전 한정, 사이클 38) | HIGH |
| **G-SAFETY-2 (HIGH)** | 보유 종목 / `_pending_next_day_clear` 절대 보호 — DB 부족이든 락이든 보유 종목 prepare 영향 0 (사이클 32 R4) | HIGH |

### VCP 전용 게이트 (쟁점 3 = (가) 행위 보존 채택 시)

| 게이트 | 검증 내용 | 등급 |
|--------|----------|------|
| **G-VCP-1 (HIGH, 행위 보존)** | DB 220일 적재 상태에서도 VCP 가 **days=100 cap 유지** → `effective_ema_long ≈ 75` 불변 → 매수 후보가 현행(KIS 100일)과 **동일**. "DB 220 있으나 100 만 사용" 직접 검증 | HIGH |
| **G-VCP-2** | 어댑터 `get_recent_daily(ticker, days=100)` 가 DB 220 중 **최신 100 (DESC)** 만 반환 → effective_ema_long 계산 입력 동일 | HIGH |
| **G-VCP-3 (가드)** | VCP effective_ema_long 계산식 변경 0 (사이클 33/48 영속) — 220 혜택은 별도 사이클 명시 주석 | LOW |

> (나) 채택 시: G-VCP-1 은 "220 → effective_ema_long=120 원설계 복원 + KIS-source 와 *의도적 비동등*" 으로 의미 전환 + backtest 결과 첨부 필수. **하지만 권고는 (가)**.

### fixture / 경계 / 허용오차 (tdd-engineer 설계 입력)

- **정상 종목 fixture**: 락 없는 220일 합성 일봉 (단조 + 노이즈). DB row(raw JSONB = KIS 키) ↔ KIS fetch 응답을 *동일 시리즈*로 구성 → bit-동일 target 기대. **허용오차 0 (정수 가격 비교)** — 가격은 int, EMA 는 동일 입력 → 동일 부동소수 → `==` 또는 1원 이내. EMA 부동소수 재현성 우려 시 `abs(ema_db - ema_kis) < 1.0` (1원).
- **락 fixture**: 윈도우 중간에 `prtt_rate=5.0`(5:1 분할) 또는 `flng_cls_code` 비기본 1행 삽입 → DB(분할 전 큰 값) vs KIS(분할 후 작은 값) 의도적 불일치 구성 → **게이트는 "DB 안 쓰고 KIS 폴백" 을 검증** (target 동등이 아니라 폴백 발생 검증).
- **prev_idx 경계 fixture**: ① DB candles[0].stck_bsop_date = D-1 (prev_idx=0) ② KIS candles[0].stck_bsop_date = today (부분봉, prev_idx=1) → 둘 다 "전일 = D-1 봉" 가리킴 검증.
- **min_required 경계**: len = 권고값, 권고값-1 두 fixture → -1 에서 폴백 발생.
- **신선도 경계**: `max_bas_dd` = D-2 (D-1 누락) fixture → 폴백 발생.
- **donchian 특이 주의**: `get_donchian_high` 는 이미 DB (사이클 123). 173 에서 EMA/거래대금도 DB 화 → **신고가(이미 DB) ↔ EMA(신규 DB) source 일관성** 게이트 필요. 현행은 신고가 DB + EMA KIS 혼재 → 173 후 둘 다 DB. 락 종목은 *둘 다* KIS 폴백해야 일관 (신고가만 DB, EMA만 KIS 폴백 = 혼재 금지).

---

## 수정주가 divergence 완화책 권고 (★ 재강조 — 가장 중요)

silent 매수 target 결함 방어의 **최종 정렬** (team-leader 채택 우선순위순):

1. **[필수, 런타임] flng_cls_code/prtt_rate 기반 강제 KIS 폴백 게이트** — 어댑터 또는 prepare 가 DB candles 윈도우 내 락 표시(`flng_cls_code` 비기본 OR `prtt_rate != 1.0`) 발견 시 그 종목만 KIS 폴백. 추가 KIS 호출 0건으로 탐지(데이터 이미 보유). **이것이 없으면 173 전환 = silent 결함 심기.** G-EQ-3 게이트로 고정.
2. **[후속, 적재] 락 발생 종목 16:00 재backfill** — 증분 적재 중 오늘 봉이 락 표시 → 그 종목 220일 전체 재backfill (KIS 재조정값 덮어쓰기). 다음날 boot 부터 DB 자동 정합. 사이클 173 또는 174 인계 가능 (1 이 즉시 방어하므로 2 는 후속 허용).
3. **[운영 모니터링] 폴백 빈도 emit** — `[prepare_db_fallback] strategy=X reason={lock|stale|insufficient|miss} count=N` 일일 summary → 운영자가 락 폴백 빈도 추적 (사이클 144 graceful_failed 가시화 패턴 답습). 락 폴백이 비정상 급증하면 적재 결함 신호.

**반례 / 한계**:
- 완화책 1 은 *DB 가 락 행을 정확히 보관*해야 작동. 만약 16:00 적재 시점에 KIS 가 `flng_cls_code`/`prtt_rate` 를 안 채워 보내면(과거 데이터 누락) 탐지 실패 → silent. → 적재 시 이 두 키 보존 검증 필요 (사이클 122 스키마는 컬럼 있음, *값 채워짐* 확인 의무).
- 배당락 중 `flng_cls_code` 가 일반 배당락을 표시 안 하는 경우(KIS 코드 체계 확인 필요) → 소액 배당락은 임팩트 작아 허용 가능하나, 고배당 연말 배당락은 KIS MCP 로 `flng_cls_code` 값 체계 재확인 권고 (어떤 코드가 액면분할/배당락/유증락인지).
- 완화책 1 의 윈도우 = 전략 lookback. VCP 220일(또는 (가) 채택 시 100일) 이 가장 길어 락 포함 확률 최대 → VCP 가 폴백 가장 빈번할 것. 정상.

---

## push 타이밍 · 라이브 검증 권고

- **push 타이밍**: HIGH 카드(매수 target 직접 경로)이므로 **NXT 애프터(15:30~) 또는 익일 07:50 _boot 전** push 의무 (CLAUDE.md 운영 가이드 영속). KRX 메인(09:00~15:30) push 절대 금지 — `_scan_loop` 5분 race + prepare 재호출 시 매수 후보 변동.
- **220 backfill 선행 의무**: 사이클 172 push 후 16:00 daily task 가 *최소 1회* 발화해서 VCP universe 220일이 DB 에 실제 적재된 것을 **운영 DB 실측(Supabase MCP)으로 확인한 후** 173 push. 미적재 상태에서 173 push 하면 VCP 전 종목 KIS 폴백(행위 무변경이라 안전하나 DB 전환 효과 0 = 무의미 push). → **D+1 운영 검증: 172 push → 익일 16:00 task → `count_by_ticker` 220 실측 → 173 push.**
- **라이브 동등성 검증 (173 push 후 D+1)**:
  - boot 07:55 `[prepare_db_fallback]` summary 에서 fallback count 확인 — 정상이면 락/신규 종목만 폴백(소수). 전 종목 폴백이면 DB 미적재 또는 min_required 과대 → 즉시 진단.
  - 09:30 funnel snapshot(사이클 171 저녁 잠정 + 09:30 확정)에서 173 전후 *후보 종목 집합 동일* 확인 — VCP (가) 채택 시 VCP 도 동일해야 함. donchian/VB/LTV/BFB 도 동일. 다르면 동등성 깨짐 → 락 종목 확인.
  - **A/B 그림자 검증 권고**: 173 push 전 1 영업일, prepare 를 DB-source 와 KIS-source *양쪽으로 계산해 로그만 비교*(매매는 KIS-source 로)하는 그림자 모드를 한 사이클 끼워 실측 divergence 0(정상 종목) + 락 종목만 차이를 운영 데이터로 확정 후 173 전환. (선택 — team-leader 판단. 안전 최우선 시 권고.)

---

## 현 코드와의 정합성 — 충돌 / 변경 vs 유지

| 항목 | 충돌 여부 | 권고 |
|------|----------|------|
| 사이클 38 명문화 (scanner 매수 진입 전 한정) | 충돌 없음 | prepare = 매수 진입 전 → 영속. G-SAFETY-1 |
| 사이클 32 R4 (보유/익일청산 절대 보호) | 충돌 없음 | DB 부족/락 무관 보유 종목 prepare 영향 0. G-SAFETY-2 |
| 사이클 123 (donchian get_donchian_high DB 우선) | **부분 정합** | 173 이 EMA/거래대금도 DB 화 → 신고가/EMA source 일관. 락 종목 *둘 다* 폴백 의무 (혼재 금지) |
| **사이클 81 G-AST1 (raw JSONB 덮어쓰기 금지)** | **잠재 충돌 (완화책 2)** | `stock_master_daily.raw` 재적재가 G-AST1(stock_master.raw) 영역인지 tdd-engineer 확인. 별개 테이블이면 무충돌 |
| 사이클 33/48 (VCP effective_ema_long 100일 한도) | **(가) 채택 시 유지** | days=100 cap 유지 → effective_ema_long 식 변경 0. (나) 채택 시 충돌(복원) |
| 사이클 172 DAILY_RETENTION_DAYS=230 | 정합 | VCP (가) 채택해도 retention 230 무해 (DB 충분, 100 만 사용) |
| min_required=None 기본 `max(days//2,10)` | **충돌 (silent 왜곡)** | 전 전략 명시 전달 의무, None 의존 금지 (donchian 33 < 필수 61) |

---

## 후속 검증 권고 (tdd-engineer / tester)

**tdd-engineer**:
1. 공통 게이트 G-EQ-1~6 + G-SAFETY-1/2 + VCP G-VCP-1~3 — 위 fixture 설계 입력대로 Red 작성.
2. **G-EQ-3 (락 폴백) 이 최우선 HIGH** — 정상 fixture 만으로는 silent 결함이 안 잡히므로, 락 fixture(`prtt_rate=5.0` 삽입)로 *DB 사용 금지 + KIS 폴백 발생*을 명시 검증.
3. min_required 전 전략 명시 전달 + None 의존 0건 AST 가드.
4. 사이클 81 G-AST1 영역이 `stock_master_daily.raw` 재적재(완화책 2)와 충돌하는지 정적 확인.

**tester**:
1. 172 push 후 D+1 16:00 task → VCP universe 220일 DB 실측(`count_by_ticker`) → 173 push 게이트.
2. 173 push 후 D+1 boot `[prepare_db_fallback]` summary fallback count 비정상(전 종목 폴백) 모니터링.
3. 09:30 funnel snapshot 173 전후 후보 집합 동일 검증 (VCP 포함 5 전략) — 다르면 락/신선도 진단.
4. **시장 행태 vs 코드 결함 1차 판단**: 173 후 특정 종목 매수 target 이 틀어졌다는 운영 보고 시 → 그 종목 최근 220일 락 이력(액면분할/유증) 먼저 확인. 락 있으면 완화책 1 게이트 누락/미작동, 락 없으면 코드 결함.

**kis-mcp-query 추가 확인 권고** (tdd-engineer/tester):
- `flng_cls_code`(락 구분 코드) **값 체계** — 어떤 코드가 액면분할 / 배당락 / 유증 신주락 / 무상증자락인지. 완화책 1 의 "락 판정" 정밀도 직결. (본 자문은 정본에서 키 *존재* + `prtt_rate` 분할비율은 확인했으나 `flng_cls_code` 코드 *값 매핑*은 미확인 — 게이트 구현 전 필수 확인.)

---

## 부록 — 동등성 매트릭스 (한눈 요약)

| 쟁점 | 경로/조건 | 동등성 | 방어 |
|------|----------|--------|------|
| 1 부분봉 | boot 07:55 | 완전 동등 ✅ | 게이트 PASS |
| 1 부분봉 | 장중 reprepare | 실효 동등 (DB 더 정확) ✅ | prev_idx 유지(폴백용) |
| 1 부분봉 | DB D-1 미적재 race | **비동등** ❌ | 신선도 가드 G-EQ-4 (KIS 폴백) |
| 2 수정주가 | 정상 종목 | 동등 ✅ | G-EQ-1 |
| 2 수정주가 | **최근 락 종목** | **비동등** ❌❌ | **완화책 1 강제 KIS 폴백 (필수)** G-EQ-3 |
| 3 VCP EMA | (가) 100 cap 유지 | 동등 (행위 보존) ✅ | G-VCP-1 |
| 3 VCP EMA | (나) 220 수용 | **의도적 비동등** (개선) | backtest 필수 (비권고) |
| 4 폴백 | DB miss/부족 | KIS==KIS (비교 대상 외) | min_required 상향 G-EQ-5 |
| 4 폴백 | min_required 과소 | **silent 왜곡** ❌ | 전략별 필수+마진 명시 |

---

*본 자문은 권고이며 최종 채택 여부는 team-leader 가 결정한다. 가장 중요한 단일 권고: **수정주가 divergence 는 테스트가 아니라 런타임 폴백 규칙(완화책 1)으로 막아야 하며, 이 게이트 없는 173 전환은 silent 매수 target 결함을 운영에 심는다.***
