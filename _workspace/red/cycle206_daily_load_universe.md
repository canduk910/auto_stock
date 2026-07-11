# 사이클 206 Red — `_stock_master_daily_load_once` 유니버스 한정 적재

**작성**: tdd-engineer / **날짜**: 2026-07-11 / **위험**: Supabase 용량 (매매 무관)

## 배경 / 확정 진단

심층점검 결과 `stock_master_daily` 가 3576종목 **전부** 일봉 적재하나, 전략은
856종목(index ∪ mcap/trade 자격)만 사용 → 2720종목(74%) = 317K행 = ~195MB 낭비.
즉시 raw SQL 퍼지 완료 (261MB → 54MB), 이제 **재적재 방지** 코드 시정.

**결함 위치**: `src/engine/scanner.py::_stock_master_daily_load_once` ticker 수집 루프
(L2156–2163). `list_all` 페이징 루프가 **모든 6자리 ticker 를 `all_tickers` 에 append**
(VCP universe=index 만 별도 `vcp_universe_tickers` 수집). 이후 all_tickers 전부에
일봉 적재 → 비유니버스 2720종목 낭비.

```python
# 현재 (전량 append)
for row in rows:
    ticker = row.get("ticker", "")
    if ticker and len(ticker) == 6 and ticker.isdigit():
        all_tickers.append(ticker)                         # ← 무조건 전량
        if row.get("is_kospi200") or row.get("is_kosdaq150"):
            vcp_universe_tickers.add(ticker)
```

## 구현 명세 (backend-dev Green)

수집 루프를 **유니버스(index ∪ mcap500억&trade20억 자격)만 append** 로 게이트:

```python
for row in rows:
    ticker = row.get("ticker", "")
    if not (ticker and len(ticker) == 6 and ticker.isdigit()):
        continue
    is_index = bool(row.get("is_kospi200") or row.get("is_kosdaq150"))
    is_qualifier = _is_daily_load_universe(row)   # 신규 헬퍼
    if is_index or is_qualifier:
        all_tickers.append(ticker)
        if is_index:
            vcp_universe_tickers.add(ticker)
```

### 신규 모듈 상수 (scanner.py, `_DAILY_LOAD_VCP_BACKFILL_DAYS` 인근)

- `_DAILY_LOAD_MIN_MCAP_EOK = 500` (억원, BFB `min_market_cap` 500억 정합)
- `_DAILY_LOAD_MIN_TRADE_WON = 2_000_000_000` (20억, BFB `min_trade_amount` 정합 —
  5전략 中 non-index 최저 필터)

### 신규 헬퍼 `_is_daily_load_universe(row) -> bool`

```python
def _is_daily_load_universe(row: dict) -> bool:
    """유니버스(자격) 판정 — mcap 500억(억원 단위) & trade 20억(원). 비숫자 → False."""
    raw = row.get("raw") or {}
    try:
        mcap_ok = int(raw.get("hts_avls") or 0) >= _DAILY_LOAD_MIN_MCAP_EOK
        trade_ok = int(raw.get("acml_tr_pbmn") or 0) >= _DAILY_LOAD_MIN_TRADE_WON
    except (ValueError, TypeError):
        return False
    return mcap_ok and trade_ok
```

- `raw.hts_avls` 는 **억원 단위** (사이클 166/108, `list_by_filter` 답습) → 상수 500 과
  직접 비교. `raw.acml_tr_pbmn` 는 **원 단위** → 상수 20억 직접 비교.
- 비숫자/부재 → `int("N/A")` ValueError → except → False (list_by_filter graceful 답습).

### 주석 명시

유니버스 = index(donchian/VCP) ∪ mcap500억&trade20억(VB/LTV/BFB 자격, BFB 최저).
비유니버스 종목 = 전략 스캔 0 → 일봉 캐시 불요. 재진입 시 다음 load 가
backfill(existing_count 분기). **VCP backfill 분기(120일)는 index 기반 불변**
(`vcp_universe_tickers` 세팅 유지).

## 회귀 가드 (`tests/unit/engine/test_cycle206_daily_load_universe.py`, 8 케이스)

| ID | 등급 | 검증 | 현재 코드 |
|----|------|------|-----------|
| UNIVERSE-1 | HIGH | index 2 + 자격 2 + 비유니버스 3 → total=4 (KIS 호출 4) | **RED** (total=7 / 호출 7) |
| UNIVERSE-2 | — | index 는 시총/거래대금 무관 항상 포함 | PASS (불변식) |
| UNIVERSE-3a | — | 자격 경계 (mcap=500억&trade=20억) 포함 (>= 비교) | PASS (불변식) |
| UNIVERSE-3b | — | 자격 하회 (mcap=499억 or trade=19.9억) 제외 | **RED** (total=2 vs 0) |
| UNIVERSE-4 | — | 헬퍼 graceful (raw 부재/비숫자 → False, but index 포함) | **RED** (total=4 vs 1) |
| UNIVERSE-5 | HIGH | VCP backfill 불변 (vcp_universe = index 종목만) | PASS (불변식) |
| UNIVERSE-6 | AST | 수집 루프 `is_index or is_qualifier` 게이트 + 헬퍼/상수 정의 | **RED** (헬퍼 부재) |
| SAFETY-1 | HIGH | 매매 hot path 참조 0 (risk/order_engine/execute_*) | PASS (불변식) |

### Red 유효성 (현재 코드 = 전량 append)

```
4 failed, 4 passed in 0.23s
FAILED UNIVERSE-1 (핵심 결함 재현 — total 7 vs 4)
FAILED UNIVERSE-3b (자격 하회 제외 — total 2 vs 0)
FAILED UNIVERSE-4 (헬퍼 graceful — total 4 vs 1)
FAILED UNIVERSE-6 (AST 게이트 — 헬퍼 부재)
PASSED UNIVERSE-2 / 3a / 5 / SAFETY-1 (불변식 — 전량 append 하에서도 참)
```

관찰 observable = `summary["total"]` (= `len(all_tickers)`) + KIS 호출 카운트
(`fetch_daily_candles_backfill.await_count + fetch_daily_candles.await_count`).

## ★ 의미 전환 (backend-dev Green 필수 — 사이클 66 K-2)

Green 의 유니버스 필터가 **기존 테스트의 mock row 를 제외** → 브레이크.
backend-dev 는 아래 테스트의 **비-index mock row 에 자격 `raw` 를 주입** 하여
원 의도(100일/증분 분기)를 보존해야 한다 (index 종목은 raw 무관 통과 → 무영향).

### `test_cycle122_daily_load_task.py` (5 SCAN 케이스 전부)

모든 mock row 가 **bare `{"ticker": "005930"}`** (플래그·raw 부재) →
Green 필터 하에서 `is_index=False, is_qualifier=False` → **제외 → `all_tickers=[]` →
`summary["total"]=0` → fetch/iterate 단언 전부 실패**.

- `test_g_scan1_load_once_iterates_stock_master` (3 ticker)
- `test_g_scan2_skip_when_already_loaded_today`
- `test_g_scan3_backfill_when_count_below_threshold`
- `test_g_scan3_incremental_when_count_above_threshold`
- `test_g_scan4_rate_limit_50ms_per_ticker` (2 ticker)
- `test_g_scan5_graceful_on_kis_failure` (2 ticker)

**시정**: 각 bare row 에 `"raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}`
(자격 통과 = 1000억 & 50억) 추가. iterate/backfill/incremental/rate-limit/graceful
분기 의도 전부 보존 (append 되어야 fetch 발생).

### `test_cycle172_vcp_universe_backfill.py` (비-index 케이스)

- `test_scan3_non_vcp_keeps_100day` — `{"ticker": "999999", is_kospi200/kosdaq150=False}`
  (raw 부재) → 제외 → `100 in captured_days` 실패.
- `test_scan3b_missing_flag_keys_treated_non_vcp` — bare `{"ticker": "005930"}` → 제외.
- `test_scan5_backfill_failure_graceful` — 2번째 row `{"ticker": "000660", is_*=False}`
  (raw 부재, 비VCP 정상 진행 검증) → 제외 → `fetched >= 1` 실패 가능.
- (index 케이스 SCAN-1/2/4 = `is_kospi200/kosdaq150=True` → raw 무관 통과 → **무영향**)

**시정**: 위 비-index row 에 자격 `raw` 주입 (동일 패턴).

### `test_cycle196_vcp_backfill_convergence.py` (비-index 케이스)

- `test_b5a_non_vcp_154_incremental_unchanged` — `{"ticker": "999999", is_*=False}` (raw 부재)
  → 제외 → 증분(days=7) 단언 실패.
- `test_b5b_non_vcp_30_hundred_day_unchanged` — 동일 → 100일 단언 실패.
- (index 케이스 b2/b3/b4 = `is_kospi200=True` → 무영향)

**시정**: 위 비-index row 에 자격 `raw` 주입.

> 위 의미 전환은 **테스트 mock 데이터 갱신** (원 의도 보존 = 사이클 66 K-2 패턴).
> xfail 마킹이 아니라 mock 정합 갱신 — 필터 도입 후에도 "비-index 자격 종목은
> 현행 100일/증분 분기 유지" 라는 원 의도가 그대로 검증됨.

## 매매 안전성

- scanner 16:00 daily task = 매수 진입 **전** (사이클 38). `git diff -- src/engine/risk.py
  src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = 0 예상.
- **보유 종목 절대 보호 (사이클 32 R4)**: held 종목이 비유니버스면 일봉 미적재이나,
  exit(손절/트레일링/익일청산)은 **실시간 tick** 사용 → daily 무관. prepare 는
  candidate 스캔 전용 (보유 종목 exit 평가에 daily 일봉 불필요). → 무영향.
  **단 인계로 명시** (아래).

## 인계

- (a) D+1 운영 실측 = 16:00 daily task 발화 후 `stock_master_daily` 적재 종목 수 ≈ 856
  (index ∪ 자격) 확인 + Supabase 용량 재증가 0 확인.
- (b) **보유 종목 비유니버스 시 일봉 캐시 미적재** — exit 은 실시간 tick 이라 무영향이나,
  향후 보유 종목을 유니버스에 합집합 편입할지 여부는 별도 판단(현 무영향이라 미편입).
- (c) 자격 임계 (mcap 500억 / trade 20억) = BFB 최저 정합 — 전략 필터 임계 변경 시 동기화 의무.
