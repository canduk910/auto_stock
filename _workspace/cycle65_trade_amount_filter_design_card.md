# 사이클 65 거래대금 동행 필터 — 설계 카드 **v2** (자문 옵션 A 전부 적용 확정)

> **작성**: team-leader (2026-06-06 KST 초안 v1 → **2026-06-06 자문 결과 옵션 A 전부 적용 v2**)
> **사용자 결정**: **옵션 A 채택** — 자문 응답 (`_workspace/cycle65_trade_amount_filter_domain_response.md`) Q1~Q5 + Q6-1~Q6-4 전부 적용. 사이클 55 R-1 / 60 / 62 / 63 / 64 / 65 의 **6 사이클 연속** 옵션 A 패턴 일관.
> **선행 자문**: `_workspace/cycle65_trade_amount_filter_domain_consult.md` (Q1~Q5 + 자유 발의)
> **자문 응답**: `_workspace/cycle65_trade_amount_filter_domain_response.md` — **Q2 옵션 C 통합 폴백 채택** + **Q6-1~Q6-4 4건 신규 발의 채택**
> **CLAUDE.md 절대 규칙 충돌**: 없음 (사이클 32 R4 universe guard + 사이클 38 명문화 + 사이클 64 답습)
> **회귀 가드 합계**: v1 23 → **v2 28 케이스** (자문 +5: B-5 옵션 C 통합 폴백 + F-4 사이클 64+65 순차 hook E2E + F-FE-4 안내 배너 + I-1 옵션 C 정합성 + I-2 Q6-1 09:00 race)
> **위험 등급**: **HIGH** (작전주 차단 유일 메커니즘 + 사이클 64 위치 변경 직후 즉시 보강)
> **사이클 66+ 인계**: Q6-4 후보 풀 폭축 역설 risk → 카드 #16 (사이클 67+) 2주 회고 의무

---

## 0. 자문 결과 확정 사항 (Q1~Q5 + Q6-1~Q6-4)

| 의제 | 채택 | 비고 |
|---|---|---|
| **Q1 임계 (HIGH)** | **디폴트 0 (비활성)** + UI **0~100억 step 1억** + 권장값 마커 **1억 / 5억 / 10억** | team-leader 1차 권고 0~5,000억 → 도메인 반박 채택, 100억 이상 비현실 |
| **Q2 데이터 소스 (HIGH, 핵심)** | **옵션 C 통합 폴백** — `ticker_market_info["trade_amount_raw"]` (신규 키) 1순위 + `stock_master.raw.acml_tr_pbmn` 2순위 + 둘 다 miss graceful 통과 | scanner 가 이미 `fetch_rising_stocks::fetch_stock_detail` 호출 + acml_tr_pbmn 보강 중 → **KIS 호출 0건 추가** |
| **Q3 시너지 (MEDIUM)** | **순차 hook** (`_apply_price_filter` → `_apply_trade_amount_filter`) + funnel `step_no=97` | 사이클 64 패턴 답습, 신규 필터 hook 별 책임 분리 명확 |
| **Q4 헬퍼 재사용 (MEDIUM)** | `_collect_protected_tickers_for_scanner` **100% 재사용** + 60s TTL 캐시 **별도** | 사이클 64 와 무효화 시점 다름 + 단일 책임 |
| **Q5 운영 모니터링 (LOW)** | 별도 prefix `[trade_amount_filter_scanner_daily_summary]` + **2주 후 효과 측정** | team-leader 1차 1~2일 → 2주 통계 유의성 |
| **Q6-1 (HIGH 신규)** | **09:00 직후 `acml_tr_pbmn=0` race graceful 통과 영속** | 잘못 처리 시 09:00~09:30 후보 차단 = 시스템 매매 무용 |
| Q6-2 (MEDIUM) | 우선주/ETF/ETN/신주인수권 영향 0 (기존 가드 영속) | 기존 ETF_KEYWORDS + `ticker.isdigit()` 가드 |
| Q6-3 (LOW) | 시간대별 임계 차별 비채택 (NXT = 매수 회피 시간대) | 사이클 38 LTV `tradable_boards` 우선 |
| **Q6-4 (MEDIUM)** | **사이클 67+ 후속 카드 #16** 발의 (2주 회고 + 임계 미세 조정) | 후보 풀 폭축 역설 risk |

---

## 1. DB 스키마 변경 (단순화 — 단일 키)

### 1.1 `system_config` 신규 키 1 종

| 키 | 타입 | 디폴트 | 비고 |
|---|---|---|---|
| `trade_amount_filter_min` | int (원 단위) | **0** = 비활성 | Q1 디폴트 0 확정 |

> **단위 확정**: **원 (₩)** — `src/engine/scanner.py:414` `MIN_TRADE_AMOUNT = 20_000_000_000` (200억) 패턴 답습. 등락률 순위 API 응답 `acml_tr_pbmn` 도 원 단위.

### 1.2 `TradeAmountFilter` Pydantic 모델 (신규)

```python
# src/db/system_config.py — 신규 모델 + getter/setter (사이클 64 패턴 답습)

class TradeAmountFilter(BaseModel):
    """거래대금 필터 설정 (사이클 65, 2026-06-06).

    매수 후보 풀 필터 — scanner 단계에서 WS 구독 *전* 적용.
    보유/익일청산 종목은 절대 제외 안 됨 (사이클 64 Q1 옵션 D 3 중 안전망 답습).
    작전주/저유동성 차단 = 사이클 64 갭상승 회피 효과 영구 폐기의 *유일 보강 메커니즘*.
    """
    min_amount: int = 0  # 원 단위, 0 = 비활성

    @property
    def is_active(self) -> bool:
        return self.min_amount > 0
```

### 1.3 시그니처

```python
_TRADE_AMOUNT_FILTER_MIN_KEY = "trade_amount_filter_min"
_TRADE_AMOUNT_FILTER_MIN_DEFAULT = 0

async def get_trade_amount_filter() -> TradeAmountFilter:
    """system_config 에서 거래대금 필터 조회. 미설정 시 default 반환."""
    ...

async def set_trade_amount_filter(*, min_amount: int | None = None) -> None:
    """부분 갱신 — None 인 키는 보존.

    - min_amount 음수 → ValueError
    """
    ...
```

### 1.4 마이그레이션

- **불필요** — `system_config` 는 `(key, value)` row 추가만으로 처리
- 디폴트 = 0 = 비활성 → DB row 미존재 시에도 graceful

---

## 2. scanner.py 신규 영역 — Q2 옵션 C 통합 폴백 (핵심 변경)

### 2.1 `ticker_market_info` 키 확장 — **신규 `trade_amount_raw` 키 추가**

**현재 (사이클 21):**

```python
# src/engine/scanner.py:453
ticker_market_info[ticker] = {
    "market_cap": round(market_cap / 1e8),    # 억 단위 반올림
    "trade_amount": round(trade_amount / 1e8),  # 억 단위 반올림 — 정확도 손실!
}
```

**사이클 65 변경:**

```python
# src/engine/scanner.py:453 — 사이클 65 trade_amount_raw 신규 키 추가
ticker_market_info[ticker] = {
    "market_cap": round(market_cap / 1e8),         # 억 단위 반올림 (기존 호환)
    "trade_amount": round(trade_amount / 1e8),     # 억 단위 반올림 (기존 호환)
    "trade_amount_raw": trade_amount,              # 사이클 65 신규 — 원 단위 정밀값 (Q2 옵션 C 1순위)
}
```

> **핵심 원칙**:
> - **기존 키 (`market_cap` / `trade_amount`) 변경 0** — UI/API 응답 호환 영속
> - **신규 키 `trade_amount_raw`** 만 추가 — `_apply_trade_amount_filter` 가 원 단위 정밀 평가
> - **KIS 호출 0건 추가** — scanner 가 이미 `fetch_rising_stocks` 호출 + acml_tr_pbmn 보강 중 (자문 §Q2 핵심 발견)

### 2.2 진입점 (Q3 순차 hook 확정)

```python
# src/engine/scanner.py — subscribe_filtered_stocks 진입 직후 (사이클 64 + 65 순차 hook)

async def subscribe_filtered_stocks(...):
    """필터링된 종목들에 대해 WebSocket 실시간 시세 구독을 등록한다.

    사이클 64 (2026-06-06) — 가격 필터 단일 hook
    사이클 65 (2026-06-06) — 거래대금 필터 순차 hook (Q3 옵션 A 확정)
    Q1 옵션 D 답습: `_apply_price_filter` / `_apply_trade_amount_filter` 둘 다 `protected_tickers=` keyword 의무.
    """
    protected = _collect_protected_tickers_for_scanner()

    # 사이클 64 — 가격 필터 (1차)
    tickers = await _apply_price_filter(tickers, protected_tickers=protected)
    # 사이클 65 — 거래대금 필터 (2차, AND 결합)
    tickers = await _apply_trade_amount_filter(tickers, protected_tickers=protected)

    if extra_tickers:
        extra_tickers = await _apply_price_filter(extra_tickers, protected_tickers=protected)
        extra_tickers = await _apply_trade_amount_filter(extra_tickers, protected_tickers=protected)
    if priority_groups:
        for key in ("breakout", "momentum", "swing"):
            if priority_groups.get(key):
                priority_groups[key] = await _apply_price_filter(
                    priority_groups[key], protected_tickers=protected,
                )
                priority_groups[key] = await _apply_trade_amount_filter(
                    priority_groups[key], protected_tickers=protected,
                )
    # 기존 흐름 변경 0
    ...
```

### 2.3 `_apply_trade_amount_filter` 본체 (옵션 C 통합 폴백)

```python
async def _apply_trade_amount_filter(
    candidates: list[str],
    *,
    protected_tickers: set[str],  # keyword-only 강제 (옵션 D 답습)
) -> list[str]:
    """거래대금 필터 적용 — 후보 풀에서 임계 미만 종목 제거.

    사이클 65 (2026-06-06) — 작전주 차단 유일 메커니즘 (사이클 64 갭상승 폐기 보강).
    Q1 옵션 D 답습: protected_tickers 는 최상단 early-return — 거래대금 평가 *전* 단독 분기.
    Q2 옵션 C 확정: ticker_market_info["trade_amount_raw"] (1순위) + stock_master.raw.acml_tr_pbmn (2순위) + 둘 다 miss graceful 통과.
    Q6-1 답습: 09:00 직후 acml_tr_pbmn=0 race graceful 통과 영속 — 시스템 매매 무용 위험 차단.
    Q7-1 답습: invalidate_cache 가 unsubscribe 발화 안 함 (5분 자연 delta).
    """
    taf = await _get_trade_amount_filter_for_scanner()
    if not taf.is_active:
        return candidates  # 비활성 → 통과

    survivors: list[str] = []
    excluded: list[tuple[str, int]] = []
    for ticker in candidates:
        # (1) 옵션 D early-return — 보유/익일청산 절대 보호
        if ticker in protected_tickers:
            survivors.append(ticker)
            continue

        # (2) 거래대금 조회 — Q2 옵션 C 통합 폴백
        trade_amount = await _get_acml_tr_pbmn(ticker)
        if trade_amount <= 0:
            # 미확보 graceful 통과 (Q2 옵션 C + Q6-1 09:00 race 영속)
            survivors.append(ticker)
            continue

        # (3) 임계 평가
        if trade_amount < taf.min_amount:
            excluded.append((ticker, trade_amount))
            if ticker not in _trade_amount_filter_scanner_skip_logged_today:
                _trade_amount_filter_scanner_skip_logged_today.add(ticker)
                logger.info(
                    "[trade_amount_filter_scanner_skip] ticker=%s acml_tr_pbmn=%d "
                    "reason=below_min min=%d",
                    ticker, trade_amount, taf.min_amount,
                )
                try:
                    from src.db.system_logs import write_log
                    await write_log(
                        "INFO",
                        f"[trade_amount_filter_scanner_skip] ticker={ticker} "
                        f"acml_tr_pbmn={trade_amount} reason=below_min "
                        f"min={taf.min_amount}",
                    )
                except Exception:
                    logger.debug("[trade_amount_filter_scanner_skip] write_log 실패", exc_info=True)
            _trade_amount_filter_scanner_skip_count_today["total"] += 1
            continue

        survivors.append(ticker)

    # funnel hook (step_no=97 — Q3 확정)
    try:
        from src.db.strategy_funnel import insert_snapshot
        from datetime import datetime, timezone, timedelta
        today_kst = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        await insert_snapshot(
            target_date=today_kst,
            strategy_id="ALL",
            step_no=97,
            step_name="trade_amount_filter_scanner",
            survived_count=len(survivors),
            survived_tickers=[{"ticker": t} for t in survivors[:200]],
            excluded_count=len(excluded),
            excluded_sample=[
                {"ticker": t, "acml_tr_pbmn": a, "reason": "below_min"}
                for (t, a) in excluded[:20]
            ],
        )
    except Exception:
        logger.debug("[trade_amount_filter_scanner_funnel] hook 실패 graceful", exc_info=True)

    return survivors
```

### 2.4 데이터 소스 — **Q2 옵션 C 통합 폴백 (핵심)**

```python
async def _get_acml_tr_pbmn(ticker: str) -> int:
    """누적 거래대금 조회 — Q2 옵션 C 통합 폴백 (사이클 65, 2026-06-06).

    1순위: ticker_market_info["trade_amount_raw"] (scanner 가 이미 fetch_rising_stocks 호출 + acml_tr_pbmn 보강)
    2순위: stock_master.raw.acml_tr_pbmn (24h TTL 캐시 — CTPF1002R 응답)
    둘 다 miss: 0 반환 → `_apply_trade_amount_filter` 가 graceful 통과 처리

    단위: 원 (₩) — KIS MCP 검증 완료 (자문 의뢰서 §8 + scanner.py:414)

    Q6-1 09:00 race 영속: scanner 1순위가 0 (장 시작 직후 누적 미반영) + stock_master 2순위가 전일 데이터 → graceful 통과 보장.
    """
    # 1순위 — scanner ticker_market_info (원 단위 정밀값)
    try:
        from src.engine.scanner import ticker_market_info
        info = ticker_market_info.get(ticker)
        if info:
            raw = info.get("trade_amount_raw", 0)
            try:
                raw_int = int(raw)
                if raw_int > 0:
                    return raw_int
            except (TypeError, ValueError):
                pass
    except Exception:
        logger.debug("[trade_amount_filter] scanner ticker_market_info 조회 실패 graceful: %s", ticker, exc_info=True)

    # 2순위 — stock_master.raw.acml_tr_pbmn (CTPF1002R 응답, 24h TTL)
    try:
        from src.db.stock_master import get as stock_master_get
        basics = await stock_master_get(ticker)
        if basics and basics.raw:
            try:
                raw_int = int(basics.raw.get("acml_tr_pbmn", 0))
                if raw_int > 0:
                    return raw_int
            except (TypeError, ValueError):
                pass
    except Exception:
        logger.debug("[trade_amount_filter] stock_master 조회 실패 graceful: %s", ticker, exc_info=True)

    return 0  # 둘 다 miss → graceful 통과
```

### 2.5 60s TTL 캐시 + invalidate (Q4 별도 + Q7-1 답습)

```python
# src/engine/scanner.py — 모듈 전역 (사이클 64 패턴 답습, Q4 별도 캐시 확정)

_trade_amount_filter_cache: TradeAmountFilter | None = None
_trade_amount_filter_cache_expires_at: float = 0.0
TRADE_AMOUNT_FILTER_CACHE_TTL = 60.0

# 일일 emit cap (사이클 64 패턴 답습)
_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str] = DailyEmitCap[str]()
# 일일 집계 카운터 (사이클 64 H 카테고리 답습)
_trade_amount_filter_scanner_skip_count_today: dict[str, int] = {"total": 0}


async def _get_trade_amount_filter_for_scanner() -> 'TradeAmountFilter':
    """60s TTL 캐시. invalidate 토글 시 즉시 무효화 (Q7-1: unsubscribe 미발화).

    Q4 별도 캐시: 사이클 64 와 무효화 시점 다름 + 단일 책임 분리.
    """
    global _trade_amount_filter_cache, _trade_amount_filter_cache_expires_at
    import time as _t
    now = _t.monotonic()
    if _trade_amount_filter_cache is not None and now < _trade_amount_filter_cache_expires_at:
        return _trade_amount_filter_cache
    taf = await get_trade_amount_filter()
    _trade_amount_filter_cache = taf
    _trade_amount_filter_cache_expires_at = now + TRADE_AMOUNT_FILTER_CACHE_TTL
    return taf


def invalidate_trade_amount_filter_cache_scanner() -> None:
    """Settings PUT 직후 즉시 반영 — 캐시만 무효화, unsubscribe 발화 0 (Q7-1).

    다음 `_scan_loop` 5분 사이클에서 자연 delta 처리.
    KIS LMS chain 차단 (사이클 17 OPSP0002 답습).
    """
    global _trade_amount_filter_cache, _trade_amount_filter_cache_expires_at
    _trade_amount_filter_cache = None
    _trade_amount_filter_cache_expires_at = 0.0
```

### 2.6 일일 집계 emit (Q5 별도 prefix 확정)

```python
async def emit_trade_amount_filter_scanner_daily_summary() -> None:
    """일일 집계 emit — scheduler._settle() 진입 직전 호출.

    사이클 65 (2026-06-06) — 사이클 64 H 카테고리 답습.
    Q5 별도 prefix 확정: `[trade_amount_filter_scanner_daily_summary]`
    """
    total = _trade_amount_filter_scanner_skip_count_today.get("total", 0)
    msg = f"[trade_amount_filter_scanner_daily_summary] block_count={total}"
    logger.info(msg)
    try:
        from src.db.system_logs import write_log
        await write_log("INFO", msg)
    except Exception:
        logger.debug("[trade_amount_filter_scanner_daily_summary] write_log 실패", exc_info=True)
```

### 2.7 reset_daily 동행 clear

```python
def reset_trade_amount_filter_daily_state() -> None:
    """매일 자정 reset — scheduler._reset_daily_state 가 호출 의무."""
    _trade_amount_filter_scanner_skip_logged_today.clear()
    for k in _trade_amount_filter_scanner_skip_count_today:
        _trade_amount_filter_scanner_skip_count_today[k] = 0
```

### 2.8 scheduler 통합 (사이클 64 hotfix H-2 영구 가드 답습)

```python
# src/engine/scheduler.py — _settle 진입 직전 (사이클 64 H-2 패턴 답습)

async def _settle(self) -> None:
    from src.engine.scanner import (
        emit_price_filter_scanner_daily_summary,
        emit_trade_amount_filter_scanner_daily_summary,  # 사이클 65 신규
    )
    await emit_price_filter_scanner_daily_summary()
    await emit_trade_amount_filter_scanner_daily_summary()  # 사이클 65 신규
    ...

async def _reset_daily_state(self) -> None:
    ...
    from src.engine.scanner import (
        reset_price_filter_daily_state,
        reset_trade_amount_filter_daily_state,  # 사이클 65 신규
    )
    reset_price_filter_daily_state()
    reset_trade_amount_filter_daily_state()
```

> **H-2 영구 가드**: 사이클 64 hotfix 답습 — AttributeError 가드 제거. 직접 호출 + AST 가드 H 케이스 동행.

---

## 3. API 라우트 변경

### 3.1 `src/routes/system.py` 신규 엔드포인트

```python
from pydantic import ConfigDict

class TradeAmountFilterUpdateRequest(BaseModel):
    min_amount: int | None = None
    model_config = ConfigDict(extra="forbid")  # 422 검증

@router.get("/trade-amount-filter", response_model=ApiResponse)
async def get_trade_amount_filter_endpoint():
    taf = await get_trade_amount_filter()
    return ApiResponse(success=True, data=taf, message="거래대금 필터 조회 성공")

@router.put("/trade-amount-filter", response_model=ApiResponse)
async def set_trade_amount_filter_endpoint(req: TradeAmountFilterUpdateRequest):
    try:
        kwargs = {}
        if req.min_amount is not None:
            kwargs["min_amount"] = req.min_amount
        await set_trade_amount_filter(**kwargs)
        # 사이클 65 — scanner 영역 invalidate (Q7-1: unsubscribe 미발화)
        try:
            from src.engine.scanner import invalidate_trade_amount_filter_cache_scanner
            invalidate_trade_amount_filter_cache_scanner()
        except Exception:
            logger.debug("[trade_amount_filter] scanner invalidate 실패 — 60s 후 자동 만료", exc_info=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    taf = await get_trade_amount_filter()
    return ApiResponse(success=True, data=taf, message="거래대금 필터가 즉시 반영되었습니다.")
```

---

## 4. UI 변경 — Q1 확정 (디폴트 0 + UI 0~100억 step 1억 + 마커 1억/5억/10억)

### 4.1 `frontend/src/types/trade-amount-filter.ts` (신규)

```typescript
export interface TradeAmountFilter {
  min_amount: number  // 원 단위
}

export interface TradeAmountFilterUpdate {
  min_amount?: number
}
```

### 4.2 `TradeAmountFilterCard.tsx` (신규)

| 항목 | 내용 |
|---|---|
| 단일 슬라이더 `trade-amount-filter-min-slider` | **범위 0 ~ 100억 step 1억** (Q1 확정) |
| 권장값 마커 (3 단계) | **1억 / 5억 / 10억** (Q1 도메인 권고) — 슬라이더 옆 빠른 선택 버튼 |
| 저장 버튼 | PUT `/api/system/trade-amount-filter` |
| 안내 배너 (Q6-1 + Q6-4 명시) | "거래대금 미만 종목은 WebSocket 구독 자체 차단. 작전주/저유동성 차단 (사이클 64 갭상승 회피 보강). **보유/익일청산 종목은 절대 제외 안 됨. 09:00 직후 거래대금 미반영 종목은 graceful 통과 (Q6-1).**" |
| 저장 토스트 | "거래대금 필터가 즉시 반영되었습니다" |

### 4.3 사이클 64 `PriceFilterCard` 와의 관계

- **별도 카드 배치** — Settings 페이지에 `PriceFilterCard` 옆 나란히 배치
- Q3 순차 hook 확정 → UI 도 분리 카드 (단일 책임)

---

## 5. 회귀 가드 28 케이스 (v1 23 → v2 +5 자문)

### 5.1 카테고리 분포

| 카테고리 | v1 | v2 | 추가 | HIGH | MEDIUM | LOW |
|---|---|---|---|---|---|---|
| A `system_config` (`trade_amount_filter_min` 1 키) | 3 | 3 | - | - | - | 3 |
| B scanner `_apply_trade_amount_filter` 본체 | 4 | **5** | +1 (B-5 옵션 C 통합 폴백) | - | 1 | 4 |
| C 보유/익일청산 절대 보호 (HIGH) | 2 | 2 | - | **2** | - | - |
| D 60s TTL 캐시 + Q7-1 답습 | 2 | 2 | - | - | 1 | 1 |
| E DailyEmitCap | 2 | 2 | - | - | - | 2 |
| F integration (E2E) | 3 | **4** | +1 (F-4 사이클 64+65 순차 hook E2E) | - | 2 | 2 |
| G AST 가드 (HIGH) | 1 | 1 | - | **1** | - | - |
| H scanner daily_summary | 1 | 1 | - | - | - | 1 |
| H-2 scheduler 통합 가드 (사이클 64 hotfix 답습) | 1 | 1 | - | - | 1 | - |
| C-Route API | 1 | 1 | - | - | 1 | - |
| F-FE 프론트 | 3 | **4** | +1 (F-FE-4 안내 배너) | - | 1 | 3 |
| **I integration 추가 (Q6 자문 신규)** | - | **2** | +2 (I-1 옵션 C 정합성 + I-2 Q6-1 09:00 race) | - | 1 | 1 |
| **합계** | **23** | **28** | **+5** | **3** | **8** | **17** |

### 5.2 케이스 상세 (28)

#### A. `system_config` (3 케이스, LOW)
- **A-1** `get_trade_amount_filter` 디폴트 (미설정 → `min_amount=0` + `is_active=False`)
- **A-2** `set_trade_amount_filter(min_amount=100_000_000)` 갱신 + 재조회 일치
- **A-3** `set_trade_amount_filter(min_amount=-1)` → ValueError

#### B. scanner `_apply_trade_amount_filter` 본체 (5 케이스)
- **B-1** [LOW] 비활성 (`min_amount=0`) → 모든 후보 통과 (Q6-1 09:00 race 영속 — 비활성이라 통과)
- **B-2** [LOW] 임계 미만 차단 (`min_amount=1억`, 후보 `trade_amount_raw=5천만` → 차단)
- **B-3** [LOW] 미확보 (양쪽 miss → `_get_acml_tr_pbmn=0`) graceful 통과 (Q6-1 영속)
- **B-4** [LOW] 임계 이상 통과 (`min_amount=1억`, 후보 `trade_amount_raw=50억` → 통과)
- **B-5** [MEDIUM 자문 신규] **Q2 옵션 C 통합 폴백 검증** — scanner 1순위 hit / scanner miss 후 stock_master 2순위 hit / 양쪽 miss graceful 3 경로 분기

#### C. 보유/익일청산 절대 보호 (HIGH 2 케이스)
- **C-1** [HIGH] 보유 종목 (positions, `_collect_protected_tickers_for_scanner` 반환) → 거래대금 50만이어도 통과 (3 중 안전망)
- **C-2** [HIGH] 익일청산 (`_pending_next_day_clear`) → 거래대금 100만이어도 통과

#### D. 60s TTL 캐시 + Q7-1 (2 케이스)
- **D-1** [MEDIUM] 60s 내 재호출 시 DB 미조회 (캐시 hit)
- **D-2** [LOW] `invalidate_trade_amount_filter_cache_scanner()` 호출 후 **unsubscribe 발화 0** (Q7-1, mock 으로 ws.unsubscribe 호출 카운트 검증)

#### E. DailyEmitCap (2 케이스, LOW)
- **E-1** 동일 ticker 차단 2회 → `write_log` 1회만 호출
- **E-2** `reset_trade_amount_filter_daily_state()` 후 동일 ticker 차단 → `write_log` 재호출

#### F. integration E2E (4 케이스)
- **F-1** [MEDIUM] scan → `_apply_price_filter` → `_apply_trade_amount_filter` → subscribe (사이클 64 + 65 연속 호출 정합성)
- **F-2** [MEDIUM] 보유 종목 보호 E2E (가격 차단 + 거래대금 차단 양쪽 통과)
- **F-3** [LOW] funnel hook `step_no=97` INSERT 확인
- **F-4** [LOW 자문 신규] **사이클 64+65 순차 hook E2E** — 가격 필터 차단 종목은 거래대금 필터에 도달 안 함 (호출 카운트 검증)

#### G. AST 가드 (HIGH 1 케이스)
- **G-1** [HIGH] `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 의무 (G-2 패턴 답습) — AST walk 로 `subscribe_filtered_stocks` 내부 호출 4 회 (tickers / extra / 3 priority key) 모두 keyword 인자 검증

#### H. scanner daily_summary + H-2 scheduler 통합 (2 케이스)
- **H-1** [LOW] `emit_trade_amount_filter_scanner_daily_summary` 호출 시 `system_logs` INSERT (prefix `[trade_amount_filter_scanner_daily_summary]`)
- **H-2** [MEDIUM] scheduler `_settle()` 가 `emit_trade_amount_filter_scanner_daily_summary` **직접 호출** (AttributeError 가드 X) — 사이클 64 hotfix 패턴 답습 + AST 가드 (try/except 감싸지 않음 검증)

#### C-Route API (1 케이스)
- **C-R-1** [MEDIUM] PUT `/api/system/trade-amount-filter` body 검증 — extra 키 → 422 / `min_amount=-1` → 400 / 정상 → `invalidate_trade_amount_filter_cache_scanner` 호출 확인 (mock)

#### F-FE 프론트 (4 케이스)
- **F-FE-1** [LOW] 초기 fetch + 슬라이더 렌더 (디폴트 0)
- **F-FE-2** [LOW] 슬라이더 조작 + 저장 버튼 → PUT body 검증
- **F-FE-3** [LOW] 권장값 마커 (1억/5억/10억) 빠른 선택 버튼 → 슬라이더 값 갱신
- **F-FE-4** [MEDIUM 자문 신규] 안내 배너 "보유/익일청산 종목은 절대 제외 안 됨. 09:00 직후 거래대금 미반영 종목은 graceful 통과 (Q6-1)" 텍스트 검증

#### I. integration 추가 (Q6 자문 신규, 2 케이스)
- **I-1** [MEDIUM 자문 신규] **옵션 C 통합 폴백 정합성** — `ticker_market_info` 에 `trade_amount_raw` 키 존재 확인 + scanner 가 `fetch_rising_stocks` 호출 후 보강 확인 (scanner.py:453 변경 검증)
- **I-2** [LOW 자문 신규] **Q6-1 09:00 race 영속 검증** — `trade_amount_raw=0` (scanner 09:00 직후 누적 미반영) + `stock_master.raw.acml_tr_pbmn=0` (장중 reset 가정) → `_apply_trade_amount_filter` graceful 통과 + `[trade_amount_filter_scanner_skip]` emit 0 확인

---

## 6. 위험 매트릭스

| 항목 | 등급 | 시정 |
|---|---|---|
| **보유/익일청산 보호** | **HIGH** | 옵션 D 3 중 안전망 (사이클 64 답습) + G-1 AST 가드 + C-1/C-2 회귀 가드 |
| **KIS LMS chain 차단 (Q7-1)** | **HIGH** | `invalidate_trade_amount_filter_cache_scanner` 가 unsubscribe 발화 0 + D-2 회귀 가드 |
| **09:00 race graceful (Q6-1)** | **HIGH** | B-3 + I-2 회귀 가드 + scanner 1순위 + stock_master 2순위 둘 다 0 → 통과 명시 |
| **데이터 소스 정확성** | MEDIUM | Q2 옵션 C 통합 폴백 + B-5 회귀 가드 + KIS 호출 0건 추가 |
| **scanner 진입점 통합** | MEDIUM | Q3 순차 hook 확정 + F-4 회귀 가드 |
| **funnel step_no 충돌** | LOW | step_no=97 (사이클 64 = 98 분리) |
| **코드 복잡도** | LOW | 사이클 64 패턴 100% 답습 |
| **매도 영향** | **0** | 사이클 38 명문화 답습 — scanner = 매수 진입 전용 |
| **후보 풀 폭축 역설 (Q6-4)** | MEDIUM | 카드 #16 (사이클 67+) 2주 회고 + 임계 미세 조정 인계 |

---

## 7. 사이클 64 답습 매트릭스 (확정)

| 항목 | 사이클 64 | 사이클 65 |
|---|---|---|
| 단일 hook (subscribe_filtered_stocks 진입 직후) | Q4 옵션 A | **순차 hook** (Q3 확정) |
| 3 중 안전망 (보유/익일청산 보호) | Q1 옵션 D | ✅ `_collect_protected_tickers_for_scanner` 헬퍼 100% 재사용 |
| KIS LMS chain 차단 (Q7-1) | invalidate 가 unsubscribe 발화 0 | ✅ 답습 (D-2 회귀 가드) |
| 60s TTL 캐시 | 사이클 56-E | ✅ 답습 (Q4 별도 캐시) |
| graceful 통과 (미확보) | Q2 옵션 A | ✅ 답습 (Q6-1 영속) |
| AST keyword 의무 가드 | G-2 | ✅ 답습 (G-1) |
| H-2 scheduler 통합 가드 (AttributeError 가드 0) | hotfix 영구 | ✅ 답습 |
| G-3 폐기 메서드 0건 | hotfix 영구 | **N/A (사이클 65 신규 — 폐기 영역 없음)** |
| 매도 영향 0 (사이클 38 명문화) | 영속 | ✅ 답습 |
| funnel hook step_no 분리 | 98 | **97** (Q3 확정) |
| 일일 집계 emit (`_settle` 직전) | H 카테고리 (scanner 영역) | ✅ 답습 (Q5 별도 prefix) |
| reset_daily 동행 clear | ✅ | ✅ 답습 |
| API 라우트 (PUT 즉시 invalidate) | ✅ | ✅ 답습 (extra=forbid 422) |
| UI 카드 (Settings 페이지) | PriceFilterCard | TradeAmountFilterCard (신규, **별도 카드 확정**) |
| **신규 — Q2 옵션 C 통합 폴백** | N/A | ✅ ticker_market_info `trade_amount_raw` 신규 키 + B-5 검증 |
| **신규 — Q6-1 09:00 race 영속** | N/A | ✅ B-3 + I-2 회귀 가드 |

---

## 8. 발주 순서

| 단계 | 담당 | 산출물 | 상태 |
|---|---|---|---|
| 1. 설계 카드 v1 (자문 발주 전 초안) | team-leader | `cycle65_trade_amount_filter_design_card.md` v1 | ✅ 완료 |
| 2. domain-expert 자문 발주 | team-leader → domain-expert | `cycle65_trade_amount_filter_domain_response.md` | ✅ 완료 |
| 3. **설계 카드 v2** (자문 옵션 A 전부 반영) | team-leader | 본 카드 v2 | ✅ 완료 |
| 4. **Red 명세** 작성 | team-leader | `_workspace/red/cycle65_trade_amount_filter.md` | ✅ 완료 (별도 파일) |
| 5. tdd-engineer Red | tdd-engineer | 28 케이스 실패 테스트 | 대기 |
| 6. backend-dev + frontend-dev 병렬 Green | backend-dev / frontend-dev | 구현 + Red 통과 | 대기 |
| 7. tester Verify | tester | V1~V13 + V-Scanner + V-AST + 사이클 64 hotfix H-2/G-3 영속 + 사이클 65 신규 V-TradeAmount (09:00 race) | 대기 |
| 8. sync-docs | team-leader → sync-docs | CLAUDE.md / HARNESS_CHANGELOG / src/engine/CLAUDE.md / src/db/CLAUDE.md / frontend/CLAUDE.md / refactor-review 카드 #16 (Q6-4 2주 회고) | 대기 |
| 9. 사용자 명시 commit + push | 사용자 | 일요일 (2026-06-07) 또는 월요일 _boot 전 | 대기 |

---

## 9. 안전 가드

- **현재 = 2026-06-06 (토) → 2026-06-07 (일) = KRX/NXT 휴장**. Red/Green/Verify/sync-docs 모두 운영 영향 0.
- production 변경 영역 = scanner.py 신규 영역 (사이클 64 답습 + `ticker_market_info["trade_amount_raw"]` 키 추가) + `system_config` 단일 키 + 라우트 + scheduler hookup + UI 신규 카드
- **보유/익일청산 절대 보호 = HIGH (사이클 32 R4 + 사이클 64 Q1 옵션 D 답습)** — 헬퍼 재사용 의무
- **09:00 race graceful = HIGH (Q6-1)** — 시스템 매매 무용 위험 차단
- **KIS LMS chain 차단 (Q7-1)** — invalidate unsubscribe 발화 0 영속
- **디폴트 0 (비활성) 영속** → 운영자 명시 활성화 없이 push 즉시 회귀 0
- **KIS 호출 0건 추가** (Q2 옵션 C 통합 폴백 핵심) — scanner 가 이미 `fetch_rising_stocks::fetch_stock_detail` 호출 + acml_tr_pbmn 보강 중
- **사이클 64 hotfix 영속**: H-2 (scheduler 직접 호출) / G-3 (폐기 메서드 0) 영속 보존

---

## 10. 후속 사이클

- **사이클 66+ = 카드 #5 (HIGH)** cap=10 결함 시정 (사이클 63 발견)
- **사이클 67+ = 카드 #14 (MEDIUM)** stale_manager.py 1,076L sub-module 분해 (3+1 청사진)
- **사이클 67+ = 카드 #16 (MEDIUM)** **Q6-4 후보 풀 폭축 역설 risk 2주 회고** (본 사이클 종료 후 발의 의무)
- **사이클 68+ = 카드 #15 (LOW)** Q7-2 액면분할 prdy_clpr invalidate
- **사이클 69+ = 카드 #11 / #12** 보드 전환 mutex / 14 모듈 logger
