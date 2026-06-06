# 사이클 65 — 거래대금 동행 필터 도메인 자문 회신

> **작성자**: domain-expert (데이/스윙 트레이더 출신 컨설턴트)
> **작성 시각**: 2026-06-06 (토) KST — KRX/NXT 휴장 (운영 영향 0)
> **수신자**: team-leader
> **자문 의뢰서**: `_workspace/cycle65_trade_amount_filter_domain_consult.md`
> **선행 설계 카드**: `_workspace/cycle65_trade_amount_filter_design_card.md` v1
> **선행 사이클 64 회신**: `_workspace/cycle64_price_filter_scanner_domain_response.md` (Q1~Q6 + Q7-1~Q7-5)
> **위험 등급 종합**: **HIGH** (사이클 64 갭상승 회피 효과 폐기의 *유일 보강 메커니즘* + KIS LMS chain 차단 영속 의무)

---

## 핵심 결론 한 줄

**사용자 사전 결정 5건 전부 트레이더 시각에서 RECOMMEND**. 다만 (1) **Q1 디폴트는 0 유지 + 권장값 1억 (10,0000,0000원) 보수 마커** — 사이클 64 graceful 통과로 5억/10억 즉시 디폴트 시 신규 상장 + 유동성 정상 종목 graceful 통과 폭주 risk. (2) **Q2 옵션 C 통합 폴백 (stock_master 1순위 + ticker_market_info 2순위 + 둘 다 미확보 graceful)** — 사이클 64 `prdy_clpr` 단독과 달리 **scanner 가 5분 주기로 이미 `fetch_stock_detail` 호출 → `ticker_market_info[t]["trade_amount"]` 정확한 *당일 누적* 보유 중**. 신규 상장 + 09:00 직후 race 보호. (3) **Q3 순차 hook + funnel step_no=97 권고** (team-leader 1차 동의). (4) **Q4 헬퍼 100% 재사용 + 60s TTL 캐시는 별도 (사이클 64 와 독립)** — 무효화 시점 다르게 가능 + 단일 책임. (5) **Q5 daily_summary 별도 prefix + Q7-5 효과 측정은 2 주 후 (1 주 short)**. **Q6+ 신규 발의 4건** — Q6-1 (HIGH) 09:00 직후 acml_tr_pbmn=0 race / Q6-2 (MEDIUM) 우선주·ETF 정상 저거래대금 / Q6-3 (LOW) 시간대별 임계 차별 권고 비채택 / Q6-4 (MEDIUM) 사이클 64 답습 *역설* — 가격 필터 통과한 우량주가 거래대금 컷오프 미통과 시 후보 풀 폭축

---

## Q1 — 거래대금 임계 권고 (HIGH)

**답변**: **RECOMMEND 옵션 A (디폴트 0 비활성) + 권장 마커 1억/5억/10억 + UI 슬라이더 범위 0~100억 step 1억**

**근거 (트레이더 시각)**:

### 시장 미시구조 — 한국 시장 거래대금 분포 (실전 운영자 본능)

| 분류 | 일일 거래대금 | 작전주 risk | 비고 |
|---|---|---|---|
| KOSPI 대형주 (시총 10조+) | 1,000~10,000억 | 0 | 삼성전자 5,000~10,000억 |
| KOSPI 중형주 (시총 1~10조) | 200~1,000억 | 매우 낮음 | 정상 매매 영역 |
| KOSDAQ 대형주 (시총 1~5조) | 100~500억 | 낮음 | 셀트리온헬스케어 등 |
| KOSDAQ 중소형주 (시총 1천억~1조) | 50~300억 | 중간 | momentum 주요 영역 |
| **작전주 / 동전주 / 신규 상장 작전** | **< 50억** | **HIGH** | **차단 1순위 영역** |
| 명백 작전 / 시세조작 | < 10억 | 즉시 차단 영역 | 호가 5호가 깊이 0 |

→ **트레이더 본능 컷오프**:
- **1억 미만** = "명백한 동전주 / 시세조작" — 호가 5호가 1만주 미만 가능. 매수 가능하지만 매도 호가 부재로 손절 불가
- **5억 미만** = "의심 영역" — 정상 우량주 영역 거의 없음. momentum +15% 후보 진입 시 작전 의심 1순위
- **10억 미만** = "보수 컷오프" — 일반 트레이더가 *호가창 두께 충분* 으로 안심하는 최소 임계
- **50억 미만** = "단타 트레이더 최소 임계" — 시초 5분 거래대금 5억 + 시간당 10억 누적 패턴

### 디폴트 = 0 (비활성) 권고 — 사이클 64 답습

사이클 64 의 **디폴트 OFF + 권장값 툴팁** 패턴이 *옳음*. 본 사이클도 동일:

1. **운영자 인지 부재 자동 차단 위험** — 디폴트 5억 즉시 활성 시 *익일 _boot 직후* 후보 풀 50% 축소 위험. 운영자가 *왜 매수 신호 없는지* 추적 곤란
2. **사이클 64 graceful 통과 운영 데이터 0** — 사이클 64 신규 위치 운영 데이터 1주 축적 *이후* 사이클 65 임계 미세 조정이 합리적. 현재 시점 (사이클 64 종결 직후 토요일) 운영 데이터 = 0
3. **Q6-1 race (09:00 직후 acml_tr_pbmn=0)** — 디폴트 활성 시 09:00 직후 5분 사이 *전 후보 차단* 위험. graceful 통과 정책 + 운영자 명시 활성화 의무로 risk 분산

### 권장값 마커 (UI 툴팁)

```
권장값 (운영자 본능):
- 1억 = 명백 작전주 차단 (보수적 최소)
- 5억 = 의심 영역 차단 (표준)
- 10억 = 호가 두께 보장 (적극적)

⚠️ 사이클 64 가격 필터 와 동시 활성화 시 후보 풀 50% 이상 축소 가능
   → 운영 1주 후 임계 미세 조정 권고
```

### UI 슬라이더 범위

- 범위: **0 ~ 100억 (10_000_000_000원)**
- step: **1억 (100_000_000원)**
- 디폴트: **0** (비활성)
- 마커: **1억 / 5억 / 10억** 3 단계 (시각 표시)

100억 상한 근거: 100억 이상은 *KOSPI 대형주 절반 차단* + *작전주 차단 효과 마진 효용 체감* — 실전 트레이더가 100억 이상 임계 설정하지 않음. UI 슬라이더 over-engineering 회피.

### KOSPI / KOSDAQ 단일 임계 권고 — 보드별 차별 비채택

- 보드별 차별 = 운영자 인지 부담 2 배 (KOSPI 1억 / KOSDAQ 5억 등)
- KOSDAQ 작전주 risk 가 더 높으나 *시스템 단순화 우선* — 사용자가 보수적 임계 (5억) 설정 시 KOSDAQ 영역 *자연 보강*
- 후속 카드 (사이클 67+) 운영 데이터 회고 후 *진짜 필요 시* 보드별 차별 검토

**트레이드오프**:
- 채택 비용: 디폴트 OFF → 운영자 명시 활성화 의무 (UX 부담 1회)
- 채택 효과: 운영자 인지 + 운영 1주 후 정밀 임계 미세 조정 + Q6-1 race 자연 회피

**구현 가이드** (backend-dev + frontend-dev):
1. `system_config.trade_amount_filter_min` 디폴트 **0** 영속 (DB row 미존재 시 = 0 graceful)
2. `TradeAmountFilter.is_active` property: `min_amount > 0` 평가 — 디폴트 0 = `is_active=False` = early return `return candidates`
3. UI `TradeAmountFilterCard`: 슬라이더 0~10_000_000_000 (0~100억) + step=100_000_000 (1억) + 마커 [100_000_000, 500_000_000, 1_000_000_000]
4. 안내 배너: `"거래대금 미만 종목은 WebSocket 구독 자체 차단. 작전주/저유동성 차단 (사이클 64 갭상승 회피 보강). **보유/익일청산 종목은 절대 제외 안 됨**. 운영 1주 데이터 축적 후 임계 미세 조정 권고."`

**위험 평가**: **MEDIUM** (디폴트 0 영속 → 디폴트 운영자 명시 활성화 없이 push 즉시 회귀 0)

---

## Q2 — 데이터 소스 정확성 (HIGH)

**답변**: **RECOMMEND 옵션 C (통합 폴백) — `ticker_market_info[t]["trade_amount"]` 1순위 + `stock_master.raw.acml_tr_pbmn` 2순위 + 둘 다 미확보 graceful 통과**. 사이클 64 답습보다 정확성 *상승* (구조적 데이터 활용)

**근거 (트레이더 시각)**:

### 핵심 발견 — `fetch_stock_detail` 가 *이미* acml_tr_pbmn 보강 중

`src/api/condition.py:477` 확인 결과:

```python
async def fetch_rising_stocks() -> list[dict]:
    ...
    for item in candidates:
        ticker = item.get("stck_shrn_iscd", "")
        try:
            detail = await fetch_stock_detail(ticker)  # 5s TTL 캐시 + 시세 풀 라우팅
            merged = {**item}
            merged["lstn_stcn"] = detail.get("lstn_stcn", "0")
            merged["acml_tr_pbmn"] = detail.get("acml_tr_pbmn", "0")  # ← 이미 fetch
            ...
```

그리고 `src/engine/scanner.py:455`:

```python
ticker_market_info[ticker] = {
    "market_cap": round(market_cap / 1e8),
    "trade_amount": round(trade_amount / 1e8),  # ← *억 단위 round* 로 메모리 저장 (원본 손실)
}
```

→ **scanner 가 이미 momentum scan 마다 `fetch_stock_detail` (= `inquire-price` FHKST01010100) 호출 + `acml_tr_pbmn` 확보**. **단, 억 단위 round 저장 — 임계 1억 미만 판정 시 정밀도 손실** (1억 = 1 → 5천만 = 0 으로 round 위험)

### 옵션 비교 매트릭스

| 옵션 | 1순위 데이터 | 정확성 | KIS Rate Limit | 신규 KIS 호출 | 신규 상장 (acml_tr_pbmn=0) |
|---|---|---|---|---|---|
| **옵션 A (stock_master 단독)** | `stock_master.raw.acml_tr_pbmn` | **불확정** (CTPF1002R 응답 필드 KIS MCP 미검증) | 0 호출 | 0 | graceful 통과 |
| **옵션 B (등락률 순위 단독)** | `fetch_stock_detail` 응답 (`acml_tr_pbmn`) | **확정** (FHKST01010100) | momentum scan 시 30~40 호출 (이미 발생) | 0 추가 (재사용) | acml_tr_pbmn=0 → graceful 통과 |
| **옵션 C 통합 폴백 (RECOMMEND)** | `ticker_market_info[t]["trade_amount"]` (메모리) → fallback `stock_master.raw.acml_tr_pbmn` | **확정** + 폴백 | 0 호출 (메모리 lookup) | 0 | 둘 다 0 → graceful 통과 |

### 옵션 C 채택 근거 — 트레이더 본능

1. **scanner 가 *이미 알고 있는 데이터* 재활용**: momentum scan 마다 fetch 한 acml_tr_pbmn 이 `ticker_market_info` 에 *억 단위 round* 저장됨. 임계 1억/5억/10억 비교에 충분한 정밀도. 추가 KIS 호출 0.
2. **사이클 64 graceful 통과 패턴 답습**: stock_master 단독 옵션 A 도 *미확보 시 graceful 통과* 라 운영 안전. 다만 *언제 사용 가능한가* 가 다름:
   - momentum 후보 (등락률 15%+) → `ticker_market_info` 1순위 자동 hit (방금 fetch)
   - 그 외 후보 (VB/LTV/donchian/BFB/VCP) → `ticker_market_info` miss → `stock_master.raw` 2순위 (24h TTL 캐시 hit 가능)
   - 둘 다 miss → graceful 통과 (사이클 64 패턴)
3. **KIS MCP §8 검증 결과 보강**: CTPF1002R 응답 `acml_tr_pbmn` 필드 미확정. *옵션 A 단독 채택 시 운영 1일차에 사실상 100% graceful 통과 = 필터 무용*. 옵션 C 가 *실효성 확보*
4. **scanner 단계 = WS 구독 *전*** = 실시간 시세 미확보. 옵션 C 의 `ticker_market_info` 는 *지난 scan 시점 (5분 이내) 데이터* 라 *최신성 충분*

### 정밀도 보강 — `ticker_market_info` 단위 변경 권고

현재 `trade_amount: round(trade_amount / 1e8)` → 임계 1억 미만 정밀 판정 위해:

**옵션 C-1 (RECOMMEND)**: `ticker_market_info` 에 raw 원본 `acml_tr_pbmn` 추가 키 신규
```python
ticker_market_info[ticker] = {
    "market_cap": round(market_cap / 1e8),
    "trade_amount": round(trade_amount / 1e8),  # 기존 (UI 표시용)
    "trade_amount_raw": trade_amount,  # 신규 (원 단위, 필터 판정용)
}
```
- 기존 키 보존 (UI 영향 0)
- 신규 키 추가만으로 정밀도 확보
- 옵션 C 의 1순위 데이터 = `ticker_market_info[t].get("trade_amount_raw", 0)`

**옵션 C-2 (대안)**: 기존 `trade_amount` 키 단위 변경 (억 → 원)
- UI 영향 (`/api/trading/status` 응답 변경) → 사이클 65 범위 외
- 비채택

### 09:00 직후 race 처리 (Q6-1 보강)

옵션 C 의 `ticker_market_info` 는 *이전 5 분 sync 결과* 라 09:00 직후도 일부 데이터 보유 가능. 다만 *09:00 ~ 09:30 사이 신규 후보* 는 `ticker_market_info` miss → `stock_master.raw` 2순위 (전일 데이터 가능) → graceful 통과. **09:00 직후 30 분간 사실상 graceful 통과 폭주** 가능성을 Q6-1 에서 별도 처리.

**트레이드오프**:
- 채택 비용: `ticker_market_info` 신규 키 `trade_amount_raw` 1개 추가 (UI 영향 0)
- 채택 효과: KIS 호출 0 + 정확성 옵션 B 동등 + 사이클 64 graceful 통과 패턴 호환

**구현 가이드** (backend-dev):
```python
async def _get_acml_tr_pbmn(ticker: str) -> int:
    """누적 거래대금 조회 — 옵션 C 통합 폴백.

    1순위: ticker_market_info[t]["trade_amount_raw"] (메모리 — momentum scan 직후)
    2순위: stock_master.raw.acml_tr_pbmn (24h TTL 캐시 — fallback)
    둘 다 미확보 시 0 반환 → graceful 통과 (사이클 64 답습)

    KIS 호출 0 — Rate Limit 부담 0.
    """
    # 1순위: scanner 메모리 (momentum scan 시점 보강)
    try:
        from src.engine.scanner import ticker_market_info
        info = ticker_market_info.get(ticker, {})
        raw_amount = info.get("trade_amount_raw", 0)
        if raw_amount > 0:
            return int(raw_amount)
    except Exception:
        pass  # graceful

    # 2순위: stock_master 24h TTL 캐시
    try:
        from src.db.stock_master import get as stock_master_get
        basics = await stock_master_get(ticker)
        if basics and basics.raw:
            try:
                amount = int(basics.raw.get("acml_tr_pbmn", 0))
                if amount > 0:
                    return amount
            except (TypeError, ValueError):
                pass
    except Exception:
        pass  # graceful

    return 0  # 둘 다 miss → graceful 통과
```

추가 변경 (`scanner.scan_stocks` line 455 직전):
```python
ticker_market_info[ticker] = {
    "market_cap": round(market_cap / 1e8),
    "trade_amount": round(trade_amount / 1e8),
    "trade_amount_raw": trade_amount,  # 사이클 65 신규 (원 단위, 필터 판정)
}
```

**위험 평가**: **MEDIUM** (graceful 통과 폭주 가능성 — Q6-1 + Q1 디폴트 0 영속으로 보강)

---

## Q3 — 사이클 64 시너지 (순차 hook + funnel step_no=97)

**답변**: **RECOMMEND 옵션 B (순차 hook) + funnel step_no=97**. team-leader 1차 권고 100% 동의

**근거 (트레이더 시각)**:

### 순차 hook 채택 근거

- **책임 분리**: `_apply_price_filter` (가격 1차원) ↔ `_apply_trade_amount_filter` (거래대금 1차원). 각 hook 의 회귀 가드 + invalidate + log prefix 가 *독립*. 사이클 67+ 신규 필터 추가 시 동일 패턴 답습 가능
- **사이클 64 회귀 가드 영향 0**: 통합 hook 채택 시 사이클 64 의 30 케이스 회귀 가드를 *함께 수정* 의무. 순차 hook 채택 시 사이클 64 회귀 가드는 *불변* — 안전성 우선
- **funnel step 분리 가능**: 통합 hook 채택 시 funnel step_no 도 통합 (예: step_no=97 통합) — 차단 *원인* (가격 vs 거래대금) 분리 불가. 순차 hook 채택 시 step_no=97 (거래대금) / step_no=98 (가격) 분리 → 운영자 차단 *원인* 분석 가능
- **AND vs OR 결합 자연 통일**: 순차 hook = AND 자연 (1차 통과 + 2차 통과 = 최종 통과). 가격 차단 또는 거래대금 차단 모두 *후보 풀에서 제외* — 트레이더 본능 "두 조건 모두 만족" 일치

### funnel step_no 권고 — 97 (사이클 64 = 98)

| step_no | 용도 | 사이클 |
|---|---|---|
| 97 | 거래대금 필터 (사이클 65 신규) | 65 |
| 98 | 가격 필터 (사이클 64) | 64 |
| 99 | 최종 (전략별 매수 신호 진입) | 41+ |

→ 순차 hook 호출 순서 = 가격 *먼저* → 거래대금 *나중* 이라 *상위 step_no* (98) 가 *먼저 실행*, *하위 step_no* (97) 가 *나중 실행*. funnel snapshot 시각 = *실행 시각순* 이라 운영자가 *step_no 역순* 으로 분석 → 99 → 97 → 98 → 96... 형태 . 사이클 41 funnel 명세 자연 호환.

또는 *실행 순서대로 step_no 부여* 옵션 (96=가격, 97=거래대금, 99=최종) 도 가능하나 *기존 사이클 64 step_no=98 변경* 의무 → 비채택. **사이클 64 step_no=98 보존 + 신규 사이클 65 step_no=97 부여** 가 변경 최소화.

### 호출 순서 — 가격 먼저 → 거래대금 나중 권고

```python
# scanner.subscribe_filtered_stocks 진입 직후 (사이클 64 답습)
protected = _collect_protected_tickers_for_scanner()

# 1차 — 가격 필터 (사이클 64)
tickers = await _apply_price_filter(tickers, protected_tickers=protected)
# 2차 — 거래대금 필터 (사이클 65)
tickers = await _apply_trade_amount_filter(tickers, protected_tickers=protected)
```

근거:
1. **가격 필터 = 단순 비교** (`min <= prdy_clpr <= max`). 거래대금 조회 비용 0
2. **거래대금 필터 = 메모리 + DB lookup** (옵션 C). 가격 필터 통과 후보만 거래대금 조회 → 호출 횟수 감소
3. **가격 필터 차단이 거래대금 필터 차단보다 *결정적*** (가격 = 가격대 자체 불일치 vs 거래대금 = 유동성). 가격 차단 후보는 거래대금 평가 *불필요*

**트레이드오프**:
- 채택 비용: 사이클 64 hook 1개 + 사이클 65 hook 1개 = 2 hook (통합 1 hook 대비 +1)
- 채택 효과: 책임 분리 + funnel step 분리 + 사이클 64 회귀 가드 불변 + 사이클 67+ 동일 패턴 답습

**구현 가이드** (backend-dev): 설계 카드 v1 §3.1 옵션 A (순차 hook) 코드 그대로 채택. funnel step_no=97 명시.

**위험 평가**: **LOW** (사이클 64 답습 + 변경 최소화)

---

## Q4 — 헬퍼 재사용 + 60s TTL 캐시 (별도)

**답변**: **RECOMMEND `_collect_protected_tickers_for_scanner` 100% 재사용 + 60s TTL 캐시는 별도 (사이클 64 와 독립)**

**근거 (트레이더 시각)**:

### `_collect_protected_tickers_for_scanner` 100% 재사용 — 의무

- 사이클 64 옵션 D 3 중 안전망의 *단일 진실 원천*. 사이클 65 가 *별도 헬퍼* 신규 시 사이클 64 와 *분기 누락* 위험 — 한 곳 수정에 다른 곳 누락 결함 (사이클 49 VCP Pullback 30 일 0 건 매매 결함 답습 회피)
- AST 가드 (G-1) 도 사이클 64 와 동일 패턴 답습 — `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 의무
- import 패턴: `from src.engine.scanner import _collect_protected_tickers_for_scanner` (사이클 64 가 이미 공개 함수로 노출)

### 60s TTL 캐시 — 별도 (사이클 64 와 독립) 권고

| 옵션 | 캐시 구조 | invalidate 시점 | 비고 |
|---|---|---|---|
| **옵션 A (별도, RECOMMEND)** | `_trade_amount_filter_cache` 신규 + `_trade_amount_filter_cache_expires_at` 신규 | `invalidate_trade_amount_filter_cache_scanner()` 호출 시 (`PUT /api/system/trade-amount-filter`) | 독립 — Settings UI 가격 필터 변경 ≠ 거래대금 필터 변경 |
| 옵션 B (통합) | `_scanner_filter_cache` 통합 dict | 양쪽 동시 무효화 | UI 1 필터만 변경해도 양쪽 캐시 무효화 → 불필요 DB 조회 |

→ **옵션 A (별도)** 채택 근거:
1. **무효화 시점 다름**: 운영자가 가격 필터만 변경하거나 거래대금 필터만 변경 가능. 옵션 B 통합 시 *한 쪽 변경* 에 *양쪽 캐시 무효화* → 다음 `_scan_loop` 진입 시 *불필요 DB 조회 1회 추가* (`get_price_filter` + `get_trade_amount_filter` 분리 호출)
2. **단일 책임**: 사이클 64 의 `_get_price_filter_for_scanner()` 와 `_apply_price_filter()` 는 *가격 필터* 단일 책임. 사이클 65 의 `_get_trade_amount_filter_for_scanner()` 와 `_apply_trade_amount_filter()` 도 *거래대금 필터* 단일 책임. 통합 시 *복수 책임* 결함
3. **사이클 67+ 신규 필터 추가 시 동일 패턴 답습** (시총 필터, ATR 필터 등) — 모든 필터가 *별도 캐시* 패턴 통일

### AST 가드 (G-1) — 사이클 64 G-2 답습

```python
# tests/unit/engine/test_cycle65_trade_amount_filter_protected_invariant.py
def test_apply_trade_amount_filter_calls_must_pass_protected_tickers_kwarg():
    """`_apply_trade_amount_filter` 호출은 `protected_tickers=` keyword-only 인자 필수.

    AST 정적 가드 — 호출자 누락 시 CI 실패. 사이클 64 G-2 답습."""
    import ast
    from pathlib import Path
    src = Path("src/engine/scanner.py").read_text()
    src += "\n" + Path("src/engine/scheduler.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "_apply_trade_amount_filter":
                kw_keys = {kw.arg for kw in node.keywords}
                assert "protected_tickers" in kw_keys, \
                    f"_apply_trade_amount_filter 호출 누락: line {node.lineno}"
            elif isinstance(fn, ast.Name) and fn.id == "_apply_trade_amount_filter":
                kw_keys = {kw.arg for kw in node.keywords}
                assert "protected_tickers" in kw_keys
```

**트레이드오프**:
- 채택 비용: 캐시 변수 2개 (`_trade_amount_filter_cache` + `_trade_amount_filter_cache_expires_at`) + invalidate 함수 1개 — 사이클 64 패턴 그대로 답습
- 채택 효과: 단일 책임 + 무효화 독립 + 후속 사이클 패턴 통일

**구현 가이드** (backend-dev): 설계 카드 v1 §3.4 코드 그대로 채택. import 패턴은 `from src.engine.scanner import _collect_protected_tickers_for_scanner` (사이클 64 공개 함수 재사용).

**위험 평가**: **LOW** (사이클 64 답습)

---

## Q5 — 운영 모니터링

**답변**: **RECOMMEND daily_summary 별도 prefix (`[trade_amount_filter_scanner_daily_summary]`) + 효과 측정 2 주 후 (1 주 short)**

**근거 (트레이더 시각)**:

### daily_summary 별도 prefix 권고 — 통합 비채택

| 옵션 | log prefix | 운영자 가시화 |
|---|---|---|
| **옵션 A (별도, RECOMMEND)** | `[trade_amount_filter_scanner_daily_summary]` | 가격 필터 (`[price_filter_scanner_daily_summary]`) 와 독립 — 차단 *원인* 즉시 분리 |
| 옵션 B (통합) | `[scanner_filter_daily_summary]` 통합 | 차단 원인 분리 불가 → 운영자 분석 시 grep 분기 필요 |

→ **옵션 A** 채택 근거:
1. **로그 grep 분리** — 운영자가 *어떤 필터가 더 많이 차단했는가* 즉시 분석. `grep "[price_filter_scanner_daily_summary]" system_logs` vs `grep "[trade_amount_filter_scanner_daily_summary]" system_logs`
2. **사이클 67+ 신규 필터 추가 시 동일 패턴 답습** — 각 필터별 별도 prefix 통일
3. **daily_log_reports.metrics 통합 영역은 별도** — `log_analysis_engine` 가 양쪽 prefix 통합 집계 가능 (사이클 67+ 후속)

### 효과 측정 시점 — 2 주 후 (1 주 short)

team-leader 의뢰서 §5: "운영 1~2 영업일 후 가시화" — 이는 **너무 짧음**. 트레이더 본능:

1. **사이클 64 신규 위치 운영 데이터 1 주 축적 *전*** 사이클 65 임계 미세 조정 불가
2. **사이클 65 운영 첫 주 = 디폴트 0 (비활성) → 차단 0**. 운영자 명시 활성화 후에 실측 시작
3. **효과 측정 = (a) 사이클 64 갭상승 회피 효과 폐기 보강 (Q7-5) — 신규 상장 작전주 차단 빈도 + (b) Q6-4 후보 풀 폭축 risk** — 양쪽 모두 *2 주 운영* 필요

| 측정 시점 | 데이터 | 의사 결정 |
|---|---|---|
| 1 주차 (사이클 65 push + 운영자 활성화 직후) | 차단 빈도 raw 데이터 | 임계 미세 조정 *불가* (데이터 부족) |
| 2 주차 | 차단 빈도 + 매매 실적 + 후보 풀 축소 비율 | 임계 미세 조정 *가능* (5억 → 3억 등) |
| 4 주차 (월 단위) | 매매 실적 회귀 + 사이클 62 갭상승 회피 효과 회복 검증 | Q7-5 정량 확인 + 후속 카드 발주 |

### 효과 측정 영구 기록 — HARNESS_CHANGELOG.md

사이클 64 + 65 통합 운영 데이터 회고는 *별도 사이클 67+* 분리. 사이클 65 발주 직후 HARNESS_CHANGELOG.md 에 *2 주 후 효과 측정 의무* 명시:

```
| 2026-06-06 | 사이클 65 — 거래대금 동행 필터 ... | scanner.py / system_config / TradeAmountFilterCard | ... 운영 효과 측정 시점: 2026-06-20 (2 주 후) — (a) Q7-5 갭상승 회피 회복 (b) Q6-4 후보 풀 폭축 검증 |
```

**트레이드오프**:
- 채택 비용: 2 주 대기 — 사이클 67+ 임계 미세 조정 발주 지연
- 채택 효과: 통계적 유의성 확보 + 잘못된 임계 결정 회피

**구현 가이드** (backend-dev + team-leader):
1. `emit_trade_amount_filter_scanner_daily_summary()` 함수: `[trade_amount_filter_scanner_daily_summary] block_count=N min=... ratio=...` 1행 INFO + `system_logs` INSERT
2. HARNESS_CHANGELOG.md 사이클 65 행에 "**2 주 후 (2026-06-20) 효과 측정 의무**" 명시

**위험 평가**: **LOW** (운영자 가시화 효과 우세)

---

## Q6+ 신규 발의 (트레이더 시각 추가 위험)

### Q6-1 (HIGH) — 09:00 직후 acml_tr_pbmn=0 race

**의제**: KRX 시초 09:00 직후 5~30분 사이 `acml_tr_pbmn` = 0 race. 디폴트 활성 시 *전 후보 차단* 위험

**답변**: **RECOMMEND graceful 통과 영속 (acml_tr_pbmn=0 → 통과)** — 디폴트 0 (비활성) 영속 + 운영자 활성화 후에도 *0 통과* 정책 영속

**근거 (트레이더 시각)**:

1. **09:00 직후 = 시장 정보 비대칭 영역** — 매도 호가 두께 부재 / 시초 변동성 50%+ / 운영자가 *시장 진입* 보다 *관망* 권고 시간대. 디폴트 활성 시 *합리적 차단* 처럼 보이나 *전 후보 차단* = *시스템 매매 무용*
2. **acml_tr_pbmn = 0 의 3 가지 origin**:
   - 신규 상장 1일차 (전일 거래 0)
   - KIS 응답 race (09:00 직후 5분 사이 acml_tr_pbmn 갱신 지연)
   - 종목 거래정지 (단, `stock_master.krx_halted=True` 가 별도 가드 — Q6-1 직접 영향 0)
3. **트레이더 본능**: "거래대금 0 = 알 수 없음" 이라 *통과* 가 보수적. *차단* 은 *알 수 없는데 위험하다* 가정 — 잘못된 가정 (KIS race 가능성)
4. **사이클 64 `prdy_clpr=0` graceful 통과 답습** — 결을 동일하게 유지

### Q6-1 보강 권고 — 09:00~09:30 강화 가드 비채택

대안: 09:00~09:30 사이 *임시 graceful 통과* (활성화 무관) — 트레이더 본능 *과도한 안전 가드* 로 비채택. 디폴트 0 + 운영자 활성화 후 graceful 통과 영속 = 충분.

**구현 가이드** (backend-dev): `_get_acml_tr_pbmn` 함수의 `return 0` graceful 통과 분기를 *시간대 무관* 동일 처리. *09:00 직후 30분 추가 분기* 신규 코드 0.

**위험 평가**: **HIGH** (잘못 처리 시 09:00~09:30 사이 *전 후보 차단* → 시스템 매매 무용)

---

### Q6-2 (MEDIUM) — 우선주 / ETF / ETN / 신주인수권 정상 저거래대금

**의제**: 우선주 (예: 005935 삼성전자우) / 일부 ETF / ETN / 신주인수권 = *정상 종목이지만 거래대금 임계 미만* (예: 5억 임계 활성 시 삼성전자우 거래대금 3억 → 차단). 운영자 의도 위반

**답변**: **CONSIDER 대부분 OK + 신주인수권 별도 처리 권고**

**근거 (트레이더 시각)**:

| 종목 분류 | 거래대금 범위 | 임계 5억 차단 risk |
|---|---|---|
| 우선주 (삼성전자우 등) | 100~500억 | 0 (정상 통과) |
| 인기 ETF (KODEX 200 등) | 1,000억+ | 0 |
| 소형 ETF (Index 추종) | 1~10억 | **차단 가능** — 거래대금 적은 ETF 정상 가능 |
| ETN (희소) | 0.1~5억 | **차단 가능** |
| 신주인수권 | 0.01~1억 | **거의 100% 차단** |

→ 우선주는 거래대금 정상 (100억+) — risk 0. ETF/ETN/신주인수권은 거래대금 적을 수 있으나 *시스템에 이미 가드 존재*:

```python
# scanner.scan_stocks (line 416-418, 사이클 21 가드)
if not (len(ticker) == 6 and ticker.isdigit()):
    continue  # ETF/ETN/신주인수권 알파벳 포함 코드 차단 (사전)
```

```python
# scanner.scan_stocks (line 427-428)
if any(kw in name for kw in ETF_KEYWORDS):
    continue  # ETF/ETN 키워드 차단
```

→ momentum scan 단계에서 *이미 ETF/ETN/신주인수권 차단*. 사이클 65 거래대금 필터 영향 = *우량주 (6자리 숫자)* 한정 → Q6-2 risk 매우 낮음.

다만 *donchian_swing 고정 유니버스 (KOSPI 200 / KOSDAQ 150)* + *VB/LTV/BFB/VCP 보유 유니버스* 도 사이클 65 필터 적용 — 보유 우선 보호 (`protected_tickers` 옵션 D) 로 *기존 보유 종목* risk 0. *신규 진입* 만 영향 → 거래대금 5억 미만 *우량주 종목* 사실상 없음 (KOSPI 200 / KOSDAQ 150 = 시총 상위 → 거래대금도 상위).

### 신주인수권 별도 처리 — 비채택

신주인수권 = 6자리 숫자 (예: 0070P3) 가능 — `isdigit()` 통과 가능. 그러나:
- KIS 등락률 순위 API 응답 자체에서 신주인수권 빈도 극히 낮음
- 사이클 65 필터 = *보호 가드* 라 신주인수권 차단 = *부수 효과* 로 trader 본능 *오히려 OK*
- 별도 가드 신규 = over-engineering

**트레이드오프**: 영향 거의 0. 별도 처리 신규 없음.

**위험 평가**: **LOW** (기존 가드로 영향 차단됨)

---

### Q6-3 (LOW) — 시간대별 임계 차별 권고 비채택

**의제**: KRX 메인 (09:00~15:30) vs NXT 애프터 (15:40~) 거래대금 차별. NXT 애프터 = 거래대금 1/10 ~ 1/50 수준 — 동일 임계 적용 시 NXT 애프터 매매 거의 차단

**답변**: **AVOID 시간대별 차별** — 단일 임계 영속 + NXT 애프터 차단 *의도된 결과* 로 해석

**근거 (트레이더 시각)**:

1. **NXT 애프터 = 정보 비대칭 영역** (사이클 26~57 누적 명문화) — 매도 거부 빈번 + 호가 두께 약함 + KIS LMS chain risk. 트레이더 본능 *신규 매수 진입 회피* — 시간대 임계 차별로 *낮은 임계 적용* 시 *오히려 NXT 매수 진입 권장* 형태로 안전 규칙 위반
2. **사이클 38 명문화 — tradable_boards 매수 진입 전용**: VB/LTV `tradable_boards=("main",)` 이므로 NXT 애프터 *신규 매수* 거의 0. 사이클 65 시간대 차별 = *불필요 over-engineering*
3. **시스템 단순화 영속** — 사이클 64 + 65 모두 *단일 임계* 패턴 답습. 운영자 인지 부담 최소화
4. **NXT 애프터 매수 가능 전략 (LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")`)**:
   - LTV 가 NXT 야간 매수 활성화 시에도 임계 5억/10억 적용 = *대부분 차단* — 트레이더 본능 *적절* (NXT 야간 = 보수적 매매 의도). 운영자가 NXT 야간 매수 활성화 시 *명시적 임계 0 (비활성)* 선택 가능

**구현 가이드**: 별도 코드 0. 단일 임계 영속.

**위험 평가**: **LOW** (단순화 우선)

---

### Q6-4 (MEDIUM) — 후보 풀 폭축 역설 risk

**의제**: 사이클 64 가격 필터 (5,000원~1,000,000원) + 사이클 65 거래대금 필터 (5억+) 동시 활성 시 *우량주 (KOSPI 200) 80% 통과 + momentum 후보 50% 차단* 형태 — *원래 활성화 의도와 다른 결과* (작전주 차단 *부수 효과* 가 *우량주 통과* 보다 *후보 풀 자체 축소* 가 더 두드러짐)

**답변**: **CONSIDER** — 사이클 64 권고와 동일하게 **운영 2 주 후 데이터 회고** + 운영자 임계 미세 조정 의무

**근거 (트레이더 시각)**:

### 사이클 64 + 65 동시 활성 시 후보 풀 추정

기존 (사이클 64 + 65 비활성):
- momentum scan (15%+ 등락률 + 시총 1,000억 + 거래대금 200억) → 약 30~40 종목/일
- BFB/VCP 베이스 영역 → 약 50~100 종목/일

사이클 64 단독 (5,000 / 1,000,000 활성):
- 5,000원 미만 차단 = 약 15% 감소 → 25~34 종목/일 (momentum)
- 1,000,000원 초과 차단 = 약 2~3% 감소 → 추가 1 종목 감소

사이클 65 단독 (5억 활성):
- momentum 은 `MIN_TRADE_AMOUNT=200억` 이미 적용 → 사이클 65 5억 임계 = *0 추가 차단* (이미 통과)
- BFB/VCP 베이스 영역 = 거래대금 5억 미만 = *작전주 / 동전주* = 약 20~30% 감소 → 35~80 종목/일

사이클 64 + 65 동시 (5,000 / 1,000,000 / 5억):
- momentum: 25 종목/일 (사이클 64 영향만 — 사이클 65 추가 영향 0)
- BFB/VCP: 30~60 종목/일 (사이클 65 영향 + 사이클 64 영향)

→ **후보 풀 50% 폭축 위험 < 실제 30% 축소**. 다만 *2 주 운영 데이터* 후 실측 의무.

### 운영자 임계 미세 조정 가이드

운영자가 후보 풀 *과도 축소* 인지 시:
1. **사이클 64 임계 우선 완화** — 5,000원 → 3,000원 / 1,000,000원 → 1,500,000원
2. **사이클 65 임계 우선 완화** — 5억 → 3억 → 1억
3. **둘 다 비활성 (디폴트 0/0/0)** → 사이클 64 갭상승 회피 효과 폐기 risk 재발

### 후속 카드 인계 — 사이클 67+

**카드 #X (MEDIUM)**: 사이클 67+ = **사이클 64 + 65 통합 운영 데이터 2 주 회고 + 임계 미세 조정**:
- (a) Q7-5 갭상승 회피 회복 검증 (신규 상장 작전주 차단 빈도)
- (b) Q6-4 후보 풀 폭축 risk 정량 측정
- (c) 임계 미세 조정 권고 — 운영자 의사 결정 지원 (트레이더 도메인 자문 동행)

**구현 가이드** (team-leader): 본 사이클 변경 0. HARNESS_CHANGELOG.md 사이클 65 행에 "**Q6-4 후속 카드 #X (사이클 67+) — 통합 운영 데이터 2 주 회고 + 임계 미세 조정**" 명시.

**위험 평가**: **MEDIUM** (디폴트 0 영속 → 즉시 회귀 0. 활성화 후 2 주 회고 의무)

---

## team-leader 1차 권고와의 차이점 매트릭스

| 의제 | team-leader 1차 권고 | domain-expert 회신 | 차이 이유 |
|---|---|---|---|
| Q1 임계 디폴트 | A/B/C/D 결정 | **옵션 A (0 비활성) + 권장값 1억/5억/10억 마커** | 사이클 64 답습 + Q6-1 09:00 race 회피 + 운영자 인지 부담 최소화 |
| Q1 UI 슬라이더 범위 | 0~5000억 step 10억/50억 후보 | **0~100억 step 1억** | 100억 이상 임계 = 실전 비현실. step 1억 = 임계 1억/5억/10억 정밀 조정 가능 |
| Q2 데이터 소스 | A 단독 권고 / B / C 옵션 | **옵션 C 통합 폴백 + `ticker_market_info` 신규 키 `trade_amount_raw`** | scanner 가 *이미* fetch 한 `acml_tr_pbmn` 재활용 — KIS 호출 0 + 정확성 *확정 데이터* |
| Q3 hook 통합 vs 순차 | 순차 hook 권고 | **순차 hook 동의** + funnel step_no=97 동의 | 책임 분리 + 사이클 64 회귀 가드 불변 |
| Q4 헬퍼 + 60s TTL 캐시 | 동의 추정 | **`_collect_protected_tickers_for_scanner` 100% 재사용 + 60s TTL 별도 (사이클 64 와 독립)** | 무효화 시점 다름 + 단일 책임 + 사이클 67+ 동일 패턴 답습 |
| Q5 효과 측정 시점 | 운영 1~2 영업일 | **2 주 후 (1 주 short)** | 사이클 64 운영 데이터 0 + 통계적 유의성 |
| Q6+ 신규 발의 | (없음) | **Q6-1 (HIGH) 09:00 race + Q6-2 (MEDIUM) 우선주/ETF + Q6-3 (LOW) 시간대별 차별 비채택 + Q6-4 (MEDIUM) 후보 풀 폭축** | 트레이더 시각 추가 risk |

---

## 우선순위 결정 매트릭스 (사용자 확정 의무 영역)

| 의제 | 위험 등급 | 사용자 확정 우선순위 | 사유 |
|---|---|---|---|
| **Q2 옵션 C 통합 폴백 + `ticker_market_info` 신규 키** | **HIGH** | **1순위** | KIS MCP §8 결과 — `stock_master.raw.acml_tr_pbmn` 미확정 → 옵션 A 단독 채택 시 사실상 100% graceful 통과 = 필터 무용. 옵션 C 가 *실효성 확보* 필수 |
| **Q1 디폴트 0 + 권장값 1억/5억/10억 마커** | **HIGH** | **2순위** | 디폴트 5억 즉시 활성 시 09:00 race + 후보 풀 폭축 risk |
| **Q6-1 09:00 race graceful 통과 영속** | **HIGH** | **3순위** | 09:00~09:30 *전 후보 차단* 위험 차단 |
| Q3 순차 hook + funnel step_no=97 | LOW | **4순위** | team-leader 권고 동의 |
| Q4 헬퍼 100% 재사용 + 60s TTL 별도 | LOW | **5순위** | 사이클 64 답습 |
| Q5 daily_summary 별도 prefix + 2 주 후 효과 측정 | LOW | **6순위** | 운영자 가시화 |
| Q6-4 후속 카드 (사이클 67+) | MEDIUM | **7순위** | 2 주 운영 후 회고 |
| Q6-2 우선주/ETF | LOW | **8순위** | 기존 가드로 영향 차단됨 |
| Q6-3 시간대별 차별 비채택 | LOW | **9순위** | 단순화 우선 |

---

## 회귀 가드 영향 매트릭스 (도메인 권고 후)

| 카테고리 | team-leader 1차 | 도메인 권고 후 | 변경 |
|---|---|---|---|
| A `system_config` (`trade_amount_filter_min` 1 키) | 3 | 3 | 변경 0 |
| B scanner `_apply_trade_amount_filter` | 4 | **5** | B-5 신규 (옵션 C 통합 폴백: `ticker_market_info` 1순위 → `stock_master` 2순위 → graceful) |
| **C 보유/익일청산 절대 보호 (HIGH)** | 2 | 2 | 변경 0 (사이클 64 답습) |
| D 60s TTL 캐시 + Q7-1 답습 (별도) | 2 | 2 | 변경 0 (별도 캐시 채택 — 사이클 64 와 독립) |
| E DailyEmitCap | 2 | 2 | 변경 0 |
| F integration (E2E) | 3 | **4** | F-4 신규 (사이클 64 + 65 순차 hook E2E — 가격 차단 + 거래대금 차단 양쪽 적용 후 funnel step_no 97 + 98 분리 INSERT 확인) |
| **G AST 가드 (HIGH)** | 1 | 1 | 변경 0 (G-1 사이클 64 G-2 답습) |
| H scanner daily_summary | 1 | 1 | 변경 0 |
| H-2 scheduler 통합 가드 (사이클 64 hotfix 답습) | 1 | 1 | 변경 0 |
| C-Route API | 1 | 1 | 변경 0 |
| F-FE 프론트 | 3 | **4** | F-FE-4 신규 (안내 배너 "운영 1 주 후 임계 미세 조정 권고" 텍스트 검증) |
| **신규 추가 (Q2 + Q6-1)** | 0 | **2** | I-1 신규 (Q2 `_get_acml_tr_pbmn` 옵션 C 통합 폴백 단위 테스트 — `ticker_market_info` hit / miss + stock_master fallback hit / miss + 둘 다 miss graceful 0) + I-2 신규 (Q6-1 09:00 race 시뮬레이션 — `acml_tr_pbmn=0` 종목 통과 + 디폴트 0 시 전 후보 통과) |
| **합계** | **23** | **28** | +5 (B-5 +1, F-4 +1, F-FE-4 +1, I-1 +1, I-2 +1) |

**안전성 분포 (도메인 권고 후)**:
- **HIGH 3** (C-1, C-2, G-1) — 보유/익일청산 절대 보호 + AST 가드
- **MEDIUM 8** (B-1~B-5, D-1, D-2, F-1~F-4, H-2, C-Route, I-1, I-2)
- **LOW 17** — DB + API 라우트 + Settings 카드 + emit cap 등

---

## 안전 규칙 위반 가능성 (최종 점검)

| CLAUDE.md 절대 규칙 | 본 사이클 영향 | 검증 |
|---|---|---|
| 체결통보 구독 (H0STCNI0/9) | 영향 0 | scanner 단계 신규 |
| uvicorn 단일 워커 | 영향 0 | — |
| WebSocket 4 중 안전망 (F1+scan_loop+K stale watcher+resubscribe_stale) | 영향 0 | scanner 차단 종목 = 구독 자체 없음 → stale 진입 안 함 |
| **`tradable_boards` 매수 진입 전용 (사이클 38)** | **본 카드 핵심 영역 직접** | scanner 차단 = 매수 진입 게이트만. 매도/익일청산/손절/15:20 강제청산/상한가 손절 모니터링 영향 0 |
| `_reset_daily_state` 동행 reset | 의무 | emit cap + count + 옵션 C 의 `_trade_amount_filter_cache` 무효화 모두 reset |
| KST 강제 | 영향 0 | — |
| 매수 시장가 거부 5호가 폴백 | 영향 0 | scanner 단계 = order_engine 영역 무관 |
| NXT 좀비 차단 (사이클 52~57) | 영향 0 | 매도 영역 |
| 15:20 강제청산 (VB) | 영향 0 | 매도 영역 |
| 상한가 손절 모니터링 (5 전략) | 영향 0 | 매도 영역 |
| **WebSocket 시세 보유·익일청산 우선 보장 (MAX 41)** | **본 카드 핵심 영역 직접** | C-1, C-2 회귀 가드 + G-1 AST 가드 + 옵션 D 3 중 안전망 (사이클 64 헬퍼 100% 재사용) |
| **Q7-1 자동 unsubscribe 0 발화 (KIS LMS chain)** | **본 카드 핵심 영역 직접** | `invalidate_trade_amount_filter_cache_scanner()` 가 unsubscribe 발화 0 (다음 `_scan_loop` 5분 자연 delta) — 사이클 17 OPSP0002 답습 |
| K stale watcher 우선순위 분리 (사이클 29-R3) | 영향 0 | scanner 차단 종목 = 구독 안 됨 → stale 진입 안 함 |

→ **CLAUDE.md 절대 규칙 위반 0**. Q1 옵션 A 디폴트 0 + Q6-1 graceful 영속 + Q7-1 KIS LMS 차단 영속 의무.

---

## 사이클 62 갭상승 회피 효과 폐기 보강 효과 평가 (Q7-5 사이클 64 인계 의무)

### 사이클 62 갭상승 회피 효과 폐기 시나리오 재확인

사이클 64 회신 §Q7-5:
> 신규 상장 1일차 작전주 Y: `prdy_clpr=0`. 시초가 1,000원 (IPO 흥행 실패) → +25% 등락률 1,250원 도달 → momentum 후보 진입 → **graceful 통과 (사이클 64) → 매수 발화** → 트레이더 본능 *위반* (전일종가 없는데 1,250원 = 명백히 동전주)

### 사이클 65 의 보강 효과 — 정량 평가

| 시나리오 | 사이클 64 단독 | 사이클 64 + 65 통합 (5억 임계) | 보강 효과 |
|---|---|---|---|
| 신규 상장 작전주 Y (prdy_clpr=0, 시초 1,000원, +25%, 거래대금 5천만원) | **graceful 통과 → 매수 발화** | 사이클 64 graceful 통과 → **사이클 65 차단 (거래대금 5천만 < 5억)** | ✅ **차단 성공** |
| 신규 상장 정상 IPO Z (prdy_clpr=0, 시초 50,000원, +30%, 거래대금 200억) | graceful 통과 → 매수 발화 | 사이클 64 graceful 통과 → 사이클 65 통과 (200억 > 5억) → 매수 발화 | ✅ IPO 흥행 보존 |
| 기존 상장 작전주 W (prdy_clpr=300원, 시초 400원 갭상승 +33%, 거래대금 1억) | **300원 < 5,000원 → 사이클 64 차단** | 사이클 64 차단 → 사이클 65 평가 불필요 | ✅ 사이클 64 단독 차단 (사이클 65 부가 보강 0) |
| 기존 상장 작전주 V (prdy_clpr=6,000원, 시초 6,500원, +8%, 거래대금 3억) | 사이클 64 통과 (6,000원 > 5,000원) → 매수 발화 가능 | 사이클 64 통과 → **사이클 65 차단 (3억 < 5억)** | ✅ **차단 성공** |
| 정상 우량주 U (prdy_clpr=50,000원, 시초 55,000원, +10%, 거래대금 500억) | 사이클 64 통과 → 매수 발화 | 사이클 64 통과 → 사이클 65 통과 → 매수 발화 | ✅ 정상 매수 보존 |

### 보강 효과 정량 평가 (운영 2 주 후 측정 의무)

- **신규 상장 작전주 차단 (Y)**: 사이클 65 5억 임계 시 *100% 차단* 가능
- **기존 상장 갭상승 작전주 차단 (V)**: 사이클 65 5억 임계 시 *고이격 작전주 차단* — 사이클 64 단독으로 차단 못한 영역 보강
- **정상 IPO 보존 (Z)**: 거래대금 200억 → 사이클 65 통과. *IPO 흥행 매수 기회 보존*
- **정상 우량주 보존 (U)**: 거래대금 500억 → 사이클 65 통과. *정상 매매 영역 영향 0*

→ **사이클 65 = 사이클 64 갭상승 회피 효과 폐기의 *유효 보강 메커니즘***. 다만:
- **Q1 디폴트 0 영속** → 운영자 명시 활성화 후에야 효과 시작 (자동 활성화 위험 회피)
- **운영 2 주 후 실측 의무** → 사이클 67+ 통합 회고로 정량 측정

### 잔존 risk — 사이클 65 도 차단 못하는 시나리오

| 시나리오 | 사이클 64 + 65 통합 | 잔존 risk |
|---|---|---|
| 신규 상장 흥행 작전주 (prdy_clpr=0, 시초 5,000원, +25%, 거래대금 100억) | **양쪽 모두 통과 → 매수 발화** | 흥행 IPO 와 작전 IPO 구분 불가 — *시스템 본질 한계*. 운영자 화이트리스트 (Q3 사이클 64 옵션 C) 만이 차단 가능 |
| 우량주 작전 (시총 1조 + prdy_clpr 50,000원 + 거래대금 600억 + 시세조작) | 양쪽 모두 통과 → 매수 발화 | 거래대금 충분한 시세조작 — 본 시스템 차단 영역 외 (감시 시스템 필요) |

→ **사이클 65 = 갭상승 회피 효과 폐기 보강 *80~90%***. 잔존 10~20% 는 *시스템 본질 한계* (운영자 화이트리스트 + 감시).

---

## 후속 카드 인계 (사이클 66+)

| 카드 # | 위험 | 의제 | 사유 |
|---|---|---|---|
| #X (MEDIUM) | **사이클 67+ 사이클 64 + 65 통합 운영 데이터 2 주 회고 + 임계 미세 조정** (Q6-4) | 통합 회고 + Q7-5 효과 정량 측정 + 임계 미세 조정 권고 | **2 주 운영 (2026-06-20) 후 의무** |
| #Y (LOW) | 액면분할 invalidate (사이클 64 인계 Q7-2) | KIS 공시 API + 24h 미만 TTL 분할 종목 자동 갱신 | 희소 사건 |
| #Z (LOW) | universe guard funnel step 분리 (사이클 64 인계 Q7-4) | step_no=96 universe guard | 사이클 41 funnel 명세 정합 |
| #5 (HIGH, 사이클 63 인계) | `_resubscribe_stale_priority` cap=10 priority 분리 결함 | priority 분리 *후* HIGH 먼저 + LOW 잔여 cap | 사이클 64+65 영향 0 (별도 영역) |
| #14 (MEDIUM, 사이클 63 인계) | `stale_manager.py` 1,076L sub-module 분해 | 3+1 청사진 | 사이클 64+65 영향 0 |

---

## 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer Red 명세 추가 케이스 (team-leader 23 → 28)

| # | 카테고리 | 케이스 | 근거 |
|---|---|---|---|
| +1 | B (MEDIUM) | B-5: `_get_acml_tr_pbmn` 옵션 C 통합 폴백 — `ticker_market_info["trade_amount_raw"]` 1순위 hit (memory 5억) → 통과. miss + `stock_master.raw.acml_tr_pbmn` 2순위 hit (3억) → 차단. 둘 다 miss → 0 graceful 통과 | Q2 |
| +2 | F (MEDIUM) | F-4: 사이클 64 + 65 순차 hook E2E — 가격 차단 + 거래대금 차단 양쪽 적용 후 funnel step_no 97 + 98 분리 INSERT 확인 | Q3 |
| +3 | F-FE (LOW) | F-FE-4: 안내 배너 "운영 1 주 후 임계 미세 조정 권고" 텍스트 검증 | Q5 |
| +4 | I (MEDIUM) | I-1: Q2 `_get_acml_tr_pbmn` 옵션 C 통합 폴백 — `ticker_market_info` 신규 키 `trade_amount_raw` 1순위 + stock_master 2순위 + 둘 다 miss graceful 정합성 | Q2 |
| +5 | I (HIGH) | I-2: Q6-1 09:00 race 시뮬레이션 — `acml_tr_pbmn=0` 종목 graceful 통과 + 디폴트 0 시 전 후보 통과 (사이클 64 답습) | Q6-1 |

### tester Verify 추가 시나리오

1. **Q2 옵션 C 통합 폴백 정합성**: scanner momentum scan 직후 `ticker_market_info[t]["trade_amount_raw"]` 갱신 확인 + 다음 `_scan_loop` 진입 시 `_apply_trade_amount_filter` 가 메모리 lookup hit 검증
2. **Q6-1 09:00 race 보호**: 09:00~09:30 사이 `acml_tr_pbmn=0` 종목 디폴트 0 시 *전 후보 통과* + 활성화 시 *graceful 통과* 양쪽 확인
3. **Q7-5 시뮬레이션 — 신규 상장 작전주 차단**: 합성 가격 시리즈 (prdy_clpr=0, 시초 1,000원, +25%, 거래대금 5천만) → 사이클 64 graceful 통과 + 사이클 65 차단 검증
4. **Q7-5 시뮬레이션 — 정상 IPO 보존**: 합성 가격 시리즈 (prdy_clpr=0, 시초 50,000원, +30%, 거래대금 200억) → 양쪽 모두 통과 검증
5. **Q3 순차 hook 호출 순서**: scanner.subscribe_filtered_stocks 진입 시 `_apply_price_filter` *먼저* → `_apply_trade_amount_filter` *나중* 호출 순서 검증
6. **Q4 60s TTL 별도 캐시 독립**: `invalidate_price_filter_cache_scanner` 호출 시 `_trade_amount_filter_cache` 영향 0 검증
7. **Q1 + Q6-1 디폴트 0 영속 검증**: 새 DB row 미존재 시 `get_trade_amount_filter()` → `min_amount=0` + `is_active=False` 반환 → `_apply_trade_amount_filter` early return `return candidates`
8. **flakiness 3 회 반복**: HIGH 3 케이스 (C-1, C-2, G-1) freezegun 3 회 반복 안정성

---

## 핵심 결론 재확인

1. **사용자 사전 결정 5건 전부 트레이더 시각 RECOMMEND** (즉시 발주 + scanner 단일 hook + 보유 절대 보호 헬퍼 재사용 + DB 단일 키 + 디폴트 0)
2. **Q1 옵션 A (디폴트 0 비활성) + 권장값 1억/5억/10억 마커 + UI 슬라이더 0~100억 step 1억**
3. **Q2 옵션 C 통합 폴백 — `ticker_market_info["trade_amount_raw"]` 1순위 + `stock_master.raw.acml_tr_pbmn` 2순위 + 둘 다 miss graceful** — scanner 가 *이미 fetch 한 데이터 재활용* + 정확성 *확정 데이터*
4. **Q3 순차 hook + funnel step_no=97** (team-leader 동의)
5. **Q4 헬퍼 100% 재사용 + 60s TTL 별도** (사이클 64 와 독립)
6. **Q5 daily_summary 별도 prefix + 2 주 후 효과 측정** (1 주 short)
7. **Q6+ 신규 발의 4건**: **Q6-1 (HIGH) 09:00 race graceful 통과 영속** + Q6-2 (MEDIUM) 우선주/ETF 영향 0 + Q6-3 (LOW) 시간대별 차별 비채택 + **Q6-4 (MEDIUM) 후보 풀 폭축 — 후속 카드 #X 인계**
8. **회귀 가드 합계** — team-leader 1차 23 → **28** (HIGH 3 변경 0, MEDIUM +5, LOW 변경 0)
9. **CLAUDE.md 절대 규칙 위반 0** — Q1 디폴트 0 + Q6-1 graceful + Q7-1 KIS LMS 차단 영속 의무
10. **사이클 62 갭상승 회피 효과 폐기 보강 효과 = 80~90%** — 잔존 10~20% = 시스템 본질 한계 (운영자 화이트리스트 + 감시)

본 회신은 권고이며, team-leader 가 채택 결정 후 사용자 확정 의무.

---

## 산출물 경로

- 본 응답서: `/Users/koscom/Projects/auto_stock/_workspace/cycle65_trade_amount_filter_domain_response.md`
- 자문 의뢰서: `/Users/koscom/Projects/auto_stock/_workspace/cycle65_trade_amount_filter_domain_consult.md` (수신)
- 설계 카드 v1: `/Users/koscom/Projects/auto_stock/_workspace/cycle65_trade_amount_filter_design_card.md` (참조)
- 사이클 64 회신: `/Users/koscom/Projects/auto_stock/_workspace/cycle64_price_filter_scanner_domain_response.md` (선행 참조)
- 핵심 데이터 발견 영역: `/Users/koscom/Projects/auto_stock/src/api/condition.py:477` (`fetch_rising_stocks` 의 `acml_tr_pbmn` 보강) + `/Users/koscom/Projects/auto_stock/src/engine/scanner.py:455` (`ticker_market_info` 저장 — `trade_amount_raw` 신규 키 추가 권고)
