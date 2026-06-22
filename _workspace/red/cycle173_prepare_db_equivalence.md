# 사이클 173 — 5 전략 prepare 일봉 source KIS→DB 전환 (HIGH, 매수 target 행위 보존)

> 작성: team-leader
> 승인 설계: `/Users/koscom/.claude/plans/funnel-vast-wolf.md` 사이클 173 절
> domain-expert 동등성 자문: `_workspace/domain_consult/cycle173_prepare_db_equivalence.md` (정독 완료)
> 선행: 사이클 172 (`get_recent_daily_normalized` 어댑터 정의 + 220일 backfill + retention 230)
> 분류: **HIGH 카드 — 동등성 게이트가 통과 의무**

---

## 0. 목적 한 줄

5 전략(VB/LTV/donchian/BFB/VCP) `prepare()` 의 일봉 source 를
`fetch_daily_candles(ticker, days=N)` (KIS REST 매일 fetch)
→ `get_recent_daily_normalized(ticker, days=N, min_required=M)` (사이클 172 DB 우선 어댑터)
로 전환한다. **매수 target 행위 보존** (정상 종목 == KIS-source 결과). momentum 제외(실시간).

---

## 1. team-leader 진단 — 운영 DB 실측으로 확정한 게이트 임계 (★ 자문 보정)

자문 §2(수정주가 divergence) 완화책 1 = "`flng_cls_code` 비기본 OR `prtt_rate != 1.0`" 락 게이트.
**team-leader 운영 DB 실측 (Supabase MCP, stock_master_daily ~367,460 row) 으로 임계 정밀 확정:**

### `flng_cls_code` 분포 (락 구분 코드)
| 값 | 건수 | 비율 | 의미 |
|----|------|------|------|
| `"00"` | 365,826 | 99.6% | **기본값(정상)** |
| `"03"` | 1,076 | 0.29% | 락 발생 |
| `"02"` | 463 | 0.13% | 락 발생 |
| `"05"` | 54 | — | 락 발생 |
| `"01"` | 41 | — | 락 발생 |
| (비기본 합계) | 1,634 | 0.44% | **락 표시** |

### `prtt_rate` 분포 (분할 비율)
| 값 | 건수 | 비율 | 의미 |
|----|------|------|------|
| `"0.0000"` | 366,343 | 99.7% | **기본값(분할/병합 없음)** |
| 음수 다수(`-0.2000`/`-0.1000`/`-0.2400` 등) | 잔여 | 0.3% | 락 조정 비율 |

### ★ 결정적 보정 (자문 재도출 아님 — 운영 데이터 기반 임계 확정)

자문은 `prtt_rate != 1.0` 을 락 기준으로 제안했으나 **운영 실측상 기본값은 `1.0` 이 아니라 `0`("0.0000")**.
자문의 `!= 1.0` 을 그대로 쓰면 **거의 전 row 가 락 판정 → 전 종목 KIS 폴백 → DB 전환 효과 0**
(자문 §271 의 "전 종목 폴백" 비정상 시나리오 자체).

**확정 락 판정 규칙 (어댑터 게이트):**
```
락(lock) 발생 = (flng_cls_code 가 "" / "00" 둘 다 아님)
                 OR (prtt_rate 가 기본값 0 아님 = abs(float(prtt_rate or 0)) > 1e-9)
```
- `flng_cls_code` 기본 = `""` 또는 `"00"` (정본 docstring + 운영 실측). 비기본 = 락.
- `prtt_rate` 기본 = `0` / `""` / `None`. 비-0 = 분할/병합/조정 락.
- **KIS 정본 docstring 은 코드 *값 의미*(어떤 코드가 액면분할/배당락/유증락)를 안 줌** (자문 §263 한계 확인).
  → 정밀 분류 대신 **비기본=무조건 락 의심 → KIS 폴백 (보수적)**. silent 결함 방어 우선.
  근거: KIS MCP 정본 `chk_inquire_daily_itemchartprice.py` COLUMN_MAPPING 에
  `flng_cls_code`(락 구분 코드) + `prtt_rate`(분할 비율) 키 존재만 확정.

빈도 정합: 비기본 row 0.44% → 윈도우 내 락 종목만 폴백 → 일 평균 소수 종목 (자문 정량 판정 일치, KIS LMS chain 안전).

---

## 2. 사전 확정 코드 사실 (진단 완료 — 구현 입력)

| 항목 | 사실 | 출처 |
|------|------|------|
| 어댑터 존재 | `get_recent_daily_normalized(ticker, days, *, min_required=None)` 정의됨 (DB raw JSONB 반환 + KIS 폴백) | `stock_master_daily.py:452-501` (사이클 172) |
| **어댑터에 락/신선도 게이트 부재** | 172 어댑터는 `len >= min_required` 만 검사. **flng_cls_code/prtt_rate 락 검사 + max_bas_dd 신선도 검사 미구현** → 173 보강 핵심 | 동 |
| `get_recent_daily` 반환 | DB row 그대로 — top-level `flng_cls_code` / `prtt_rate` 컬럼 **존재** (raw JSONB 와 별개 정규화 컬럼) | `stock_master_daily.py:216-247` + migration 033 |
| `get_recent_daily` days clamp | `max(1, min(days, 100))` → **VCP days=100 전달 시 자동 100 반환** = (가) 행위 보존 자연 충족 | 동 L229 |
| `max_bas_dd(ticker)` 존재 | 최신 bas_dd 반환 (없으면 None) — 신선도 가드 입력 | `stock_master_daily.py:360` |
| 5 전략 fetch 패턴 | 각 `_fetch_one(ticker)` 내부 `await fetch_daily_candles(ticker, days=N)` 동일 구조 | VB:186 / LTV:195 / donchian:210 / BFB:213 / VCP:228 |
| 전 전략 prev_idx | `prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0` 동일 | VB:214 / LTV:225 / donchian:264 / BFB:248 / VCP:267 |
| donchian 이미 DB 신고가 | `get_donchian_high` DB 우선 (사이클 123). EMA/거래대금은 KIS candles 의존 → 173 에서 DB 통일 | donchian:285-295 |
| KIS flng_cls_code 값 의미 | 정본 docstring 미제공 (키 존재만) → 보수적 비기본 폴백 채택 | KIS MCP `chk_inquire_daily_itemchartprice.py` |

---

## 3. 구현 명세

### 3-1. 어댑터 `get_recent_daily_normalized` 보강 (HIGH 핵심)

`src/db/stock_master_daily.py::get_recent_daily_normalized` 에 **2 게이트 추가** (락 → KIS 폴백 + 신선도 → KIS 폴백).
**raw JSONB 반환 영속** (정상 종목은 172 동작 그대로).

폴백 우선순위 (DB 사용 전 검사 순서):
1. **락 게이트 (G-EQ-3, 최우선 HIGH)**: `get_recent_daily(ticker, days)` 윈도우 내 **1 row 라도 락 발생** (§1 규칙) → DB 버리고 `fetch_daily_candles(ticker, days)` 폴백.
   - 검사 대상 = DB row 의 top-level `flng_cls_code` / `prtt_rate` 컬럼 (추가 KIS 호출 0건).
2. **신선도 게이트 (G-EQ-4)**: `max_bas_dd(ticker)` 가 **직전 영업일 미만** (D-1 미적재) → KIS 폴백.
   - 직전 영업일 판정 = 단순 캘린더 D-1 이 아니라, **DB 최신봉이 "충분히 최신"인지** 검사.
     보수적 구현 = `max_bas_dd < (today_kst - N일)` 형태 임계. 정확 영업일 계산은 KIS chk-holiday 의존 회피 →
     **team-leader 결정: `staleness_days` 임계 = 4일** (주말 2 + 공휴일 마진 1 + 1). DB 최신봉이 today-4 보다 오래되면 폴백.
     (D-1 정확 비교는 휴장일/연휴 race 로 거짓 폴백 다발 → 4일 마진이 보수적 안전.)
3. **min_required 게이트 (G-EQ-5, 기존 172 + §4 임계 상향)**: `len(db_rows) < min_required` → KIS 폴백.
4. 위 3 게이트 모두 통과 → DB raw JSONB 반환 (172 동작).

graceful: KIS 폴백 실패 시 사이클 88 — DB raw 추출 결과 반환 (호출자 보호). `max_bas_dd`/락 검사 예외 시 보수적으로 **KIS 폴백 시도** (안전 우선) 후 실패 시 DB.

운영 가시화 (자문 완화책 3): 폴백 사유 분류 카운터 — `[prepare_db_fallback] reason={lock|stale|insufficient|miss}` 형태.
**team-leader 결정: 사이클 144 graceful_failed 가시화 패턴 답습 — 모듈 전역 카운터 + 일일 summary emit (선택 구현, LOW). 173 필수 = 락/신선도/min_required 게이트 자체. 가시화는 동반 권고이나 게이트가 우선.**

### 3-2. 5 전략 prepare() 일봉 source 전환

각 전략 `_fetch_one(ticker)` 내부:
```
# 변경 전
await fetch_daily_candles(ticker, days=N)
# 변경 후
from src.db.stock_master_daily import get_recent_daily_normalized
await get_recent_daily_normalized(ticker, days=N, min_required=M)
```

**전략별 days / min_required (자문 §4 채택 — None 의존 금지, 명시 의무):**

| 전략 | days (= 현 fetch_days) | min_required | 근거 |
|------|----------------------|--------------|------|
| VB | `k_period + 2` (~22) | **22** | k_period(~20) + prev_idx + 마진 |
| LTV | `k_period + 2` (~22) | **22** | VB 동일 |
| donchian | `max(long_ma+5, donchian+5)+1` (~66) | **63** | long_ma(60)+1 컷 + prev_idx + 마진 (60 과소 = silent 왜곡 차단) |
| BFB | `pole_max+flag_max+atr+10` (~44) | **35** | pole_max+flag_max+2(~33) + 마진 |
| VCP | `min(ema_long+base_max+10, 100)` = **100 cap 유지** | **100** | (가) 행위 보존 — 220 미사용, effective_ema_long 식 변경 0 |

> 자문 §4 권고값(VB/LTV 24, BFB 37)에서 team-leader 가 plan 본문 §3 값(VB/LTV 22, BFB 35)을 **채택**.
> 사유: plan 승인 설계가 정본이며, 22/35 도 prev_idx 마진 포함 충분 (VB k_period 실측 ~20 + prev_idx 1 + 1 = 22 빠듯하나 미달 시 KIS 폴백으로 안전). donchian 63 / VCP 100 은 자문·plan 일치.
> **단, donchian min_required=63 은 절대 하향 금지** (필수 lookback 61 미달 시 EMA silent 왜곡 — 자문 최강 권고).

**VCP days=100 cap 절대 유지 (G-VCP-1~3):**
- `fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX=100)` 라인 변경 0.
- `get_recent_daily_normalized(ticker, days=fetch_days=100, min_required=100)` → 어댑터 `get_recent_daily` 가 `min(100,100)=100` 만 반환.
  DB 에 220 있어도 최신 100 DESC 만 → `effective_ema_long = min(120, 100-20-5) ≈ 75` 불변 = 현행 KIS 100일과 동일 후보.
- **220 혜택(EMA 원설계 복원)은 별도 backtest 사이클 인계 — 173 에서 VCP 행위 변경 절대 금지.**

**donchian 일봉 source 통일:**
- 신고가 = `get_donchian_high` DB (사이클 123 영속) + EMA/거래대금 = `get_recent_daily_normalized` DB 전환.
- **락 종목은 둘 다 KIS 폴백 의무** (신고가만 DB / EMA만 KIS 혼재 금지 — 자문 §249).
  → donchian `_fetch_one` 이 `get_recent_daily_normalized` 폴백 시, 그 candles 로 신고가도 계산 (혼재 차단).
  현 코드는 `db_high = get_donchian_high(...)` 우선 + `kis_high = max(highs[...])` fallback 구조.
  **173: candles 가 KIS 폴백된 경우(락) 에도 db_high 가 DB 라면 혼재** → tdd-engineer 가 G-EQ 게이트로 일관성 검증.
  team-leader 결정: donchian 은 `get_recent_daily_normalized` 가 폴백 판단(락/신선도) 후 candles 반환 →
  그 candles 의 신고가(`max(highs[1:donchian+1])`)를 신뢰. `get_donchian_high` 별도 DB 호출은 **유지하되**,
  candles 가 락 폴백된 경우 db_high 도 무시하고 kis_high 사용하도록 **일관성 가드** 추가 (G-EQ 검증).
  *구현 단순화 옵션*: donchian 도 candles 단일 source 로 신고가 계산 (db_high 분기 제거)이 일관성 보장 최선 —
  단 사이클 123 회귀 위험. **tdd-engineer 가 Red 에서 "락 시 신고가+EMA 동일 source" 게이트로 강제** 후 backend-dev 가 최소 구현.

### 3-3. 보존 의무 (절대 변경 0)

- 사이클 158 VB prepare 0건 자동 재시도 hook (cap 3 + sleep 30s) — VB/BFB/VCP 영속.
- 사이클 163 `count_active` 가드 (boot prepare) 영속.
- 사이클 32 R4 보유/익일청산 절대 보호 — DB 부족/락 무관 보유 종목 prepare 영향 0.
- prev_idx 분기 5 전략 유지 (폴백 KIS candles 당일 부분봉 방어 — 자문 §73 옵션 B 비채택).
- 사이클 170 funnel 단계 캡처 + `_reset_funnel_steps` 영속.
- 사이클 143/157 FUNNEL_STAGES + master_block hook 영속.

---

## 4. 회귀 가드 (자문 G-EQ / G-SAFETY / G-VCP — tdd-engineer Red 설계)

### 공통 게이트 (VB / LTV / donchian / BFB)

| 게이트 | 검증 | 등급 |
|--------|------|------|
| **G-EQ-3 (락 폴백, 최우선 HIGH)** | 락 fixture(`prtt_rate=-0.2` 또는 `flng_cls_code="02"` 1 row 윈도우 삽입) → **DB 사용 금지 + KIS 폴백 발생** 명시 검증. 정상 fixture 로는 silent 결함 안 잡힘 — 락 fixture 필수 | HIGH |
| **G-EQ-1 (HIGH)** | 정상 종목(락 없음) DB-source prepare `_targets`/`_candidates` == KIS-source 동일 buy target (VB noise/K · donchian 신고가/EMA/ATR · BFB pole/flag — respx KIS vs DB mock, 가격 int `==` / EMA 부동소수 `abs < 1.0`) | HIGH |
| **G-EQ-2 (HIGH)** | prev_idx 경계 — DB(당일 미적재 prev_idx=0) ↔ KIS(당일 부분봉 prev_idx=1) 동일 D-1 전일 → 같은 target. boot + 장중 2 fixture | HIGH |
| **G-EQ-4 (신선도 가드)** | `max_bas_dd` 가 staleness 임계(today-4) 초과 → KIS 폴백 발생 | MEDIUM |
| **G-EQ-5 (min_required, HIGH)** | DB len < 전략별 min_required → KIS 폴백. len == min_required-1 경계 fixture. donchian 62(=63-1) 폴백 / 63 통과 | HIGH |
| **G-EQ-6 (폴백 동등)** | DB 완전 miss → KIS 폴백 → 현행 KIS-only prepare 와 동일 (회귀 보존) | MEDIUM |

### VCP 전용 (G-VCP-1~3, 행위 보존 (가))

| 게이트 | 검증 | 등급 |
|--------|------|------|
| **G-VCP-1 (HIGH, 행위 보존)** | DB 220일 적재 상태에서도 VCP days=100 cap 유지 → effective_ema_long ≈75 불변 → 후보 == 현행 KIS 100일. "DB 220 있으나 100만 사용" 직접 검증 | HIGH |
| **G-VCP-2 (HIGH)** | 어댑터 `get_recent_daily(ticker, days=100)` 가 DB 220 중 최신 100 DESC 만 반환 → EMA 입력 동일 | HIGH |
| **G-VCP-3** | VCP `effective_ema_long` 계산식 변경 0 (사이클 33/48 영속) + `fetch_days` 100 cap 라인 변경 0 (AST) | LOW |

### 안전성 (G-SAFETY-1/2, HIGH)

| 게이트 | 검증 | 등급 |
|--------|------|------|
| **G-SAFETY-1 (HIGH)** | `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = 0 라인 + check_exit_signal/check_buy_signal 일봉 source 무관 (호출 0건) | HIGH |
| **G-SAFETY-2 (HIGH)** | 보유/`_pending_next_day_clear` 절대 보호 — DB 부족/락/신선도 무관 보유 종목 prepare 영향 0 (사이클 32 R4) | HIGH |

### 락 fixture 구성 (tdd-engineer 설계 입력)
- 정상 fixture: 락 없는 합성 일봉 (단조 + 노이즈). DB row(top-level flng_cls_code="00" / prtt_rate="0.0000" + raw JSONB KIS 키) ↔ KIS fetch 동일 시리즈 → bit-동일 target.
- **락 fixture**: 윈도우 중간 1 row 에 `flng_cls_code="02"` OR `prtt_rate="-0.2000"` → DB(락 전 값) vs KIS(락 후 값) 의도적 불일치 → 게이트가 "DB 안 쓰고 KIS 폴백" 검증 (target 동등이 아니라 폴백 발생).
- prev_idx 경계: ① DB candles[0].bas_dd=D-1 (prev_idx=0) ② KIS candles[0].bas_dd=today (prev_idx=1) → 둘 다 "전일=D-1 봉".
- AST: 5 전략 prepare 에 `min_required=` keyword 명시 (None 의존 0건) + `get_recent_daily_normalized` 호출 ≥ 1 + `fetch_daily_candles` 직접 호출 0 (전략 prepare 영역, _fetch_one 한정).
- 사이클 81 G-AST1 영역 확인: `stock_master_daily.raw` 재적재(완화책 2)는 173 미구현 → AST 충돌 0. 어댑터는 raw 읽기만 (변경 0).

---

## 5. 매매 안전성 (HIGH — 매수 target 경로)

- **동등성 게이트가 통과 의무.** risk.on_tick / order_engine / realtime / auth / api/order.py diff **0**.
- prepare = 매수 진입 *전* 한정 (사이클 38 명문화). check_exit/buy 일봉 source 무관.
- 사이클 158 재시도 hook / 163 count_active / 32 R4 / 170 funnel 영속.

---

## 6. 검증

- `python -m pytest -q` 전체 PASS (현 3,161 기준) flakiness 0.
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = **0**.
- **동등성 가드 전 전략 PASS** (G-EQ-3 락 폴백 포함).
- VCP days=100 행위 보존 확인 (G-VCP-1).
- 락 폴백 KIS 추가 호출 0건 확인 (검사는 DB top-level 컬럼).

---

## 7. 문서 동기화

- `src/engine/strategies/CLAUDE.md` (5 전략 prepare DB일봉 전환 + min_required 명시 + VCP 100 cap)
- `src/db/CLAUDE.md` (어댑터 락/신선도 게이트 보강)
- `docs/HARNESS_CHANGELOG.md` + 루트 `CLAUDE.md`
- 자문 산출물 경로 인용: `_workspace/domain_consult/cycle173_prepare_db_equivalence.md`

---

## 8. ★ 커밋/푸시 금지 (장중 + HIGH)

구현·검증·문서까지만. `git commit` / `git push` **절대 금지**. 변경은 작업 트리에 둔 채 보고만.
(push 는 장 마감 후 메인 세션이 라이브 검증 동반 처리.)
