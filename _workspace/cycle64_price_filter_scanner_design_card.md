# 사이클 64 가격 필터 위치 변경 + 단순화 — 설계 카드 (v2 — 자문 옵션 A 전부 적용 확정)

> **작성**: team-leader (2026-06-06 KST 초안 v1 → **2026-06-06 자문 결과 옵션 A 전부 적용 v2**)
> **사용자 결정**: **옵션 A 채택** — 자문 응답 (`_workspace/cycle64_price_filter_scanner_domain_response.md`) Q1~Q6 + Q7-1~Q7-5 전부 적용. 사이클 55 R-1 / 60 / 62 / 63 의 4 사이클 연속 옵션 A 패턴 일관.
> **선행 자문**: `_workspace/cycle64_price_filter_scanner_domain_consult.md` (Q1~Q6 + 자유 발의)
> **자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md` — **Q1 옵션 D 신규 발의 채택** + **Q4 옵션 A 단일 hook 채택** + **Q7-1~Q7-5 5건 신규 발의 채택**
> **CLAUDE.md 절대 규칙 충돌**: 없음 (사이클 32 R4 universe guard + 사이클 38 명문화 답습)
> **회귀 가드 합계**: v1 20 → **v2 24 케이스** (도메인 +4: C-4 옵션 D + G-2 AST + H scanner 이전 + F-4 funnel step_no=98)
> **사이클 65 인계**: Q7-5 거래대금 동행 필터 즉시 발주 확정 (본 카드 §15 + 별도 sketch `_workspace/cycle65_trade_amount_filter_domain_consult.md`)

---

## 0. 자문 결과 확정 사항 (Q1~Q6 + Q7-1~Q7-5)

| 의제 | 사용자 결정 | 비고 |
|---|---|---|
| **Q1** 보유/익일청산 보호 (HIGH) | **옵션 A + 옵션 D 3 중 안전망** (자문 신규 발의) | hot path 호출 빈도 사이클 32 R4 100배 → 시세 끊김 결함 차단 필수 |
| **Q2** prdy_clpr 미확보 | **옵션 A graceful 통과 + KIS pre-fetch 비채택** | Rate Limit + hot path 부담 회피, 2순위 KIS `inquire-price` 폐기 |
| **Q3** 신규 상장 | **옵션 B graceful + 자연 필터** | IPO 흥행 매수 기회 보존, 작전주는 Q7-5 위임 |
| **Q4** scanner 진입점 (HIGH) | **옵션 A `subscribe_filtered_stocks` 직전 단일 hook** | 6 전략 분산 (옵션 B) 절대 금지 |
| **Q5** WS 슬롯 | 디폴트 0/0 영속 | 운영자 명시 활성화 후 1주 통계로 임계 미세 조정 |
| **Q6** H 카테고리 (일일 집계) | **옵션 B scanner 영역 이전** + funnel hook (Q7-4) | 사이클 41 funnel 진단 패턴 답습 |
| **Q7-1** 자동 unsubscribe 차단 (HIGH) | **AVOID 자동 unsubscribe** — invalidate_cache 가 unsubscribe 발화 안 함 | 사이클 17 OPSP0002 KIS LMS chain 차단 |
| **Q7-2** 액면분할 invalidate | **본 사이클 범위 밖, 후속 카드 #15 발의** | 희소 사건 |
| **Q7-3** 사이클 62 데이터 손실 | 사이클 64 HARNESS_CHANGELOG 행에 영구 기록 | 디폴트 OFF 영속 → 데이터 손실 0 |
| **Q7-4** funnel step_no=98 분리 | **F-4 신규 회귀 가드 1 케이스** | 사이클 41 funnel 명세 답습 |
| **Q7-5** 거래대금 동행 필터 격상 (HIGH) | **사이클 65 즉시 발주 확정** | 갭상승 회피 효과 폐기 위험 즉시 시정 |

---

## 1. DB 스키마 변경 (단순화)

### 1.1 `system_config` 키 변경 (1 종 폐기)

| 키 | 사이클 62 | 사이클 64 | 변경 |
|---|---|---|---|
| `price_filter_min` | int (default 0) | **유지** | - |
| `price_filter_max` | int (default 0) | **유지** | - |
| `price_filter_mode` | str (default `OFF`) | **폐기** | DB row 잔존 허용 (코드 미참조), 후속 정리 사이클 cleanup |

### 1.2 `PriceFilter` Pydantic 모델 단순화

```python
# src/db/system_config.py (수정 — mode 필드 제거)

class PriceFilter(BaseModel):
    """가격 필터 설정 (사이클 64 단순화, 2026-06-06).

    매수 후보 풀 필터 — scanner 단계에서 WS 구독 *전* 적용.
    보유/익일청산 종목은 절대 제외 안 됨 (사이클 32 R4 universe guard + 사이클 64 Q1 옵션 D 답습).
    """
    min_price: int = 0   # 0 = 비활성
    max_price: int = 0   # 0 = 비활성 (무한대 의미)
    # mode 필드 제거 (사이클 64)

    @property
    def is_active(self) -> bool:
        """min 또는 max 가 > 0 이면 활성."""
        return self.min_price > 0 or self.max_price > 0
```

### 1.3 `set_price_filter` 시그니처 단순화

```python
async def set_price_filter(
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    # mode 인자 제거 (사이클 64)
) -> None:
    """부분 갱신 — None 인 키는 보존.

    - min_price 음수 → ValueError
    - max_price 음수 → ValueError
    - min/max 둘 다 > 0 + max < min → ValueError
    """
    ...
```

### 1.4 호환 layer 제거 대상

- `PriceFilterMode` Literal 제거
- `_PRICE_FILTER_MODE_KEY` / `_PRICE_FILTER_MODE_DEFAULT` / `_PRICE_FILTER_VALID_MODES` / `_PRICE_FILTER_MODE_UNSET` 모두 제거
- `_get_str_or_default` / `_set_str` 헬퍼는 다른 곳 미사용 확인 후 제거 (사이클 65 거래대금 필터에서 미사용 확인 필요)

### 1.5 마이그레이션

**불필요** — `price_filter_mode` DB row 는 그대로 두되 코드에서 미참조. 후속 정리 사이클에서 cleanup 권고 (선택).

---

## 2. 적용 위치 (scanner 단계 — 단일 진실 원천 + 옵션 D 3 중 안전망)

### 2.1 사이클 62 코드 완전 제거 (risk.py)

| 영역 | 제거 대상 | 라인 (현재) |
|---|---|---|
| import | `from src.db.system_config import PriceFilter, get_price_filter` | risk.py L19 |
| 필드 | `_price_filter_skip_logged_today` / `_price_filter_warn_logged_today` / `_price_filter_cache` / `_price_filter_cache_expires_at` / `_price_filter_skip_count_today` / `_price_filter_warn_count_today` / `_price_filter_skip_reasons_today` | risk.py L54-62 (7 필드) |
| reset_daily | 7 필드 reset 로직 | risk.py L73-78 |
| on_tick 분기 | 사이클 62 가격 필터 가드 + HARD/WARN 분기 | risk.py L213-246 |
| 헬퍼 메서드 | `_get_price_filter_cached` / `invalidate_price_filter_cache` / `_emit_price_filter_skip` / `_emit_price_filter_warn` | risk.py L266+ (4 메서드) |
| 상수 | `PRICE_FILTER_CACHE_TTL` | risk.py 모듈 상수 |

### 2.2 scanner.py 신규 진입점 (Q4 옵션 A — 단일 hook 확정)

#### 2.2.1 진입점 위치 — `subscribe_filtered_stocks` 진입 직후 단일 hook

```python
# src/engine/scanner.py — subscribe_filtered_stocks 진입 직후 (자문 §Q4 옵션 A)

async def subscribe_filtered_stocks(
    tickers: list[str],
    extra_tickers: list[str] | None = None,
    source_counts: dict[str, int] | None = None,
    *,
    priority_groups: dict[str, list[str]] | None = None,
) -> None:
    """필터링된 종목들에 대해 WebSocket 실시간 시세 구독을 등록한다.

    사이클 64 (2026-06-06) — 진입 직후 가격 필터 단일 hook 적용 의무.
    Q1 옵션 D 답습: `_apply_price_filter` 는 `protected_tickers` keyword 의무.
    """
    # 사이클 64 — 가격 필터 단일 hook (Q4 옵션 A 답습)
    protected = _collect_protected_tickers_for_scanner()
    tickers = await _apply_price_filter(tickers, protected_tickers=protected)
    if extra_tickers:
        extra_tickers = await _apply_price_filter(extra_tickers, protected_tickers=protected)
    if priority_groups:
        for key in ("breakout", "momentum", "swing"):
            # HIGH 키 (positions / next_day_clear) 는 protected 가 자동 보호 — 필터 적용해도 무영향
            if priority_groups.get(key):
                priority_groups[key] = await _apply_price_filter(
                    priority_groups[key], protected_tickers=protected,
                )

    # 기존 흐름 (사이클 17 우선순위 분리 보존) — 변경 0
    extra = extra_tickers or []
    all_tickers = list(dict.fromkeys(tickers + extra))
    ...
```

**핵심 원칙**:
- **`subscribe_filtered_stocks` 외부 호출자 시그니처 변경 0** — 호출자(scheduler 4 호출부) 영향 0
- **신규 전략 추가 시 자동 적용** — 6 전략 분산 (옵션 B) 누락 위험 차단
- **HIGH 키 (`positions` / `next_day_clear`) 는 protected 자동 보호** — 필터 적용해도 무영향

#### 2.2.2 옵션 D 3 중 안전망 (Q1 자문 신규 발의 채택)

**(1) `_collect_protected_tickers_for_scanner()` 공통 헬퍼**

```python
# src/engine/scanner.py (신규 모듈 공개 함수)

def _collect_protected_tickers_for_scanner() -> set[str]:
    """보유 + 익일청산 합집합 — scanner 가격 필터 절대 보호 대상.

    사이클 32 R4 universe guard 답습 + 사이클 64 Q1 옵션 D 신규.
    scheduler lazy import + getattr graceful (단위 테스트 + 부팅 race 안전).
    """
    protected: set[str] = set()
    # 보유 종목 (전 전략 합집합)
    try:
        from src.engine.strategy_registry import registry
        for s in registry.all():
            protected |= set(s.state.positions.keys())
    except Exception:
        logger.debug("[protected_tickers] registry 조회 실패 graceful", exc_info=True)
    # 익일청산 종목
    try:
        from src.engine import scheduler as _sched
        ts = getattr(_sched, "trading_scheduler", None)
        if ts is not None:
            pending = getattr(ts, "_pending_next_day_clear", None)
            if pending:
                # _pending_next_day_clear 는 set[(ticker, exchange)] 또는 set[ticker]
                for item in pending:
                    if isinstance(item, tuple) and item:
                        protected.add(item[0])
                    elif isinstance(item, str):
                        protected.add(item)
    except Exception:
        logger.debug("[protected_tickers] scheduler 조회 실패 graceful", exc_info=True)
    return protected
```

**(2) `_apply_price_filter` 최상단 early-return**

```python
async def _apply_price_filter(
    candidates: list[str],
    *,
    protected_tickers: set[str],  # keyword-only 강제 (옵션 D)
) -> list[str]:
    """가격 필터 적용 — 후보 풀에서 임계 외 종목 제거.

    Q1 옵션 D: protected_tickers 는 최상단 early-return — 가격 평가 *전* 단독 분기.
    Q2 옵션 A: prdy_clpr 미확보 시 graceful 통과 (KIS pre-fetch 미수행).
    Q7-1 답습: invalidate_cache 가 unsubscribe 발화 안 함 (5분 자연 delta).
    """
    pf = await _get_price_filter_for_scanner()
    if not pf.is_active:
        return candidates  # 비활성 → 통과

    survivors: list[str] = []
    excluded: list[tuple[str, int, str]] = []  # (ticker, prdy_clpr, reason)
    for ticker in candidates:
        # (1) 옵션 D early-return — 보유/익일청산 절대 보호
        if ticker in protected_tickers:
            survivors.append(ticker)
            continue

        # (2) prdy_clpr 조회 — stock_master.raw.prdy_clpr 단독 (Q2 옵션 A)
        prdy_clpr = await _get_prdy_clpr(ticker)
        if prdy_clpr <= 0:
            # 미확보 graceful 통과 (Q2 + Q3 옵션 A/B)
            survivors.append(ticker)
            continue

        # (3) 임계 평가
        below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
        above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
        if below_min or above_max:
            reason = "below_min" if below_min else "above_max"
            excluded.append((ticker, prdy_clpr, reason))
            # DailyEmitCap 1회/ticker/일 emit
            if ticker not in _price_filter_scanner_skip_logged_today:
                _price_filter_scanner_skip_logged_today.add(ticker)
                logger.info(
                    "[price_filter_scanner_skip] ticker=%s prdy_clpr=%d "
                    "reason=%s min=%d max=%d",
                    ticker, prdy_clpr, reason, pf.min_price, pf.max_price,
                )
                try:
                    from src.db.system_logs import write_log
                    await write_log(
                        "INFO",
                        f"[price_filter_scanner_skip] ticker={ticker} "
                        f"prdy_clpr={prdy_clpr} reason={reason} "
                        f"min={pf.min_price} max={pf.max_price}",
                    )
                except Exception:
                    logger.debug("[price_filter_scanner_skip] write_log 실패", exc_info=True)
            # 일일 집계 카운터
            _price_filter_scanner_skip_count_today["total"] += 1
            _price_filter_scanner_skip_count_today[reason] += 1
            continue

        survivors.append(ticker)

    # Q7-4 funnel hook (step_no=98) — graceful
    try:
        from src.db.strategy_funnel import insert_snapshot
        from datetime import datetime, timezone, timedelta
        today_kst = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        await insert_snapshot(
            target_date=today_kst,
            strategy_id="ALL",  # 단일 hook 이라 strategy 분리 불가
            step_no=98,
            step_name="price_filter_scanner",
            survived_count=len(survivors),
            survived_tickers=[{"ticker": t} for t in survivors[:200]],
            excluded_count=len(excluded),
            excluded_sample=[
                {"ticker": t, "prdy_clpr": p, "reason": r}
                for (t, p, r) in excluded[:20]
            ],
        )
    except Exception:
        logger.debug("[price_filter_scanner_funnel] hook 실패 graceful", exc_info=True)

    return survivors
```

**(3) AST 정적 가드 (G-2) — `protected_tickers` keyword-only 의무**

```python
# tests/unit/engine/test_cycle64_price_filter_ast_guards.py (G 카테고리)

import ast

def test_apply_price_filter_calls_must_pass_protected_tickers_kwarg():
    """`_apply_price_filter` 호출은 `protected_tickers=` keyword-only 인자 필수.

    Q1 옵션 D 답습 — 누락 시 보유 종목 가격 필터 차단 위험 (HIGH).
    """
    src = open("src/engine/scanner.py", encoding="utf-8").read()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name == "_apply_price_filter":
                kw_keys = {kw.arg for kw in node.keywords if kw.arg}
                if "protected_tickers" not in kw_keys:
                    violations.append(node.lineno)
    assert not violations, (
        f"_apply_price_filter 호출에 protected_tickers= keyword 누락 "
        f"(lines={violations}) — Q1 옵션 D 위반"
    )
```

### 2.3 비교 가격 데이터 소스 (Q2 옵션 A 확정)

| 우선순위 | 데이터 소스 | 미확보 시 |
|---|---|---|
| **1순위 (유일)** | `stock_master.get(ticker).raw.get("prdy_clpr")` (24h TTL 캐시) | graceful 통과 (Q2 + Q3) |
| ~~2순위~~ | ~~KIS `inquire-price` (`FHKST01010100`) 사전 fetch~~ | **자문 §Q2 비채택** — Rate Limit + hot path 부담 |

```python
async def _get_prdy_clpr(ticker: str) -> int:
    """전일종가 조회 — stock_master 단독 (Q2 옵션 A).

    미확보 시 0 반환 → `_apply_price_filter` 가 graceful 통과 처리.
    """
    try:
        from src.db.stock_master import get as stock_master_get
        basics = await stock_master_get(ticker)
        if basics and basics.raw:
            try:
                return int(basics.raw.get("prdy_clpr", 0))
            except (TypeError, ValueError):
                return 0
    except Exception:
        logger.debug("[price_filter] stock_master 조회 실패 graceful: %s", ticker, exc_info=True)
    return 0
```

### 2.4 60s TTL 캐시 + invalidate (Q7-1 답습 — unsubscribe 미발화)

```python
# src/engine/scanner.py — 모듈 전역

_price_filter_cache: PriceFilter | None = None
_price_filter_cache_expires_at: float = 0.0
PRICE_FILTER_CACHE_TTL = 60.0

# 일일 emit cap (Q3 + Q6 답습)
_price_filter_scanner_skip_logged_today: DailyEmitCap[str] = DailyEmitCap[str]()
# 일일 집계 카운터 (Q6 옵션 B answer)
_price_filter_scanner_skip_count_today: dict[str, int] = {
    "total": 0, "below_min": 0, "above_max": 0,
}


async def _get_price_filter_for_scanner() -> 'PriceFilter':
    """60s TTL 캐시. invalidate 토글 시 즉시 무효화 (Q7-1: unsubscribe 미발화)."""
    global _price_filter_cache, _price_filter_cache_expires_at
    import time as _t
    now = _t.monotonic()
    if _price_filter_cache is not None and now < _price_filter_cache_expires_at:
        return _price_filter_cache
    pf = await get_price_filter()
    _price_filter_cache = pf
    _price_filter_cache_expires_at = now + PRICE_FILTER_CACHE_TTL
    return pf


def invalidate_price_filter_cache_scanner() -> None:
    """Settings PUT 직후 즉시 반영 — 캐시만 무효화, unsubscribe 발화 0 (Q7-1).

    다음 `_scan_loop` 5분 사이클에서 자연 delta 처리.
    KIS LMS chain 차단 (사이클 17 OPSP0002 답습).
    """
    global _price_filter_cache, _price_filter_cache_expires_at
    _price_filter_cache = None
    _price_filter_cache_expires_at = 0.0
```

### 2.5 일일 집계 emit (Q6 옵션 B — scanner 영역 이전)

```python
async def emit_price_filter_scanner_daily_summary() -> None:
    """일일 집계 emit — scheduler._settle() 진입 직전 호출.

    사이클 62 H 카테고리 (risk 영역) 폐기 → scanner 영역 이전 (Q6 옵션 B).
    """
    total = _price_filter_scanner_skip_count_today.get("total", 0)
    below = _price_filter_scanner_skip_count_today.get("below_min", 0)
    above = _price_filter_scanner_skip_count_today.get("above_max", 0)
    msg = (
        f"[price_filter_scanner_daily_summary] block_count={total} "
        f"reasons={{below_min: {below}, above_max: {above}}}"
    )
    logger.info(msg)
    try:
        from src.db.system_logs import write_log
        await write_log("INFO", msg)
    except Exception:
        logger.debug("[price_filter_scanner_daily_summary] write_log 실패", exc_info=True)
```

### 2.6 reset_daily 동행 clear

```python
def reset_price_filter_daily_state() -> None:
    """매일 자정 reset — scheduler._reset_daily_state 가 호출 의무.

    사이클 32 universe guard 패턴 답습.
    """
    _price_filter_scanner_skip_logged_today.clear()
    for k in _price_filter_scanner_skip_count_today:
        _price_filter_scanner_skip_count_today[k] = 0
```

**호출 위치**:
- `scheduler._reset_daily_state()` 끝부분에 `scanner.reset_price_filter_daily_state()` 호출 추가
- `scheduler._settle()` 진입 *직전* (reset 전) 에 `scanner.emit_price_filter_scanner_daily_summary()` 호출 — 집계가 reset 보다 먼저

---

## 3. API 라우트 변경 (단순화)

### 3.1 `src/routes/system.py` 갱신

```python
class PriceFilterUpdateRequest(BaseModel):
    min_price: int | None = None
    max_price: int | None = None
    # mode 필드 제거 (사이클 64)

@router.put("/price-filter", response_model=ApiResponse)
async def set_price_filter_endpoint(req: PriceFilterUpdateRequest):
    try:
        kwargs = {}
        if req.min_price is not None:
            kwargs["min_price"] = req.min_price
        if req.max_price is not None:
            kwargs["max_price"] = req.max_price
        await set_price_filter(**kwargs)
        # 사이클 64 — scanner 영역 invalidate (Q7-1: unsubscribe 미발화)
        try:
            from src.engine.scanner import invalidate_price_filter_cache_scanner
            invalidate_price_filter_cache_scanner()
        except Exception:
            logger.debug("[price_filter] scanner invalidate 실패 — 60s 후 자동 만료", exc_info=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pf = await get_price_filter()
    return ApiResponse(success=True, data=pf, message="가격 필터가 즉시 반영되었습니다.")
```

### 3.2 422 검증 (PriceFilterUpdateRequest)

- `mode` 키 전달 시 Pydantic 자동 무시 (`extra="ignore"` 디폴트) — 또는 명시 `extra="forbid"` 로 422 반환 (Red 케이스 C-Route-2)

---

## 4. UI 변경 (단순화)

### 4.1 `frontend/src/types/price-filter.ts` 갱신

```typescript
// PriceFilterMode 제거 (사이클 64)

export interface PriceFilter {
  min_price: number
  max_price: number
  // mode 필드 제거
}

export interface PriceFilterUpdate {
  min_price?: number
  max_price?: number
  // mode 필드 제거
}
```

### 4.2 `PriceFilterCard.tsx` 단순화

| 항목 | 변경 | 비고 |
|---|---|---|
| mode select (`price-filter-mode-select` testid) | **제거** | F-FE-5 회귀 가드 폐기 |
| 슬라이더 2 (min / max) | 유지 | 권장값 툴팁 보존 |
| 안내 배너 | **갱신** | "매수 진입 전용" → "**WebSocket 구독 대상 필터 — 임계 외 종목은 시세 구독 자체 차단. 보유/익일청산 종목은 절대 제외 안 됨**" |
| 저장 토스트 | 유지 | "가격 필터가 즉시 반영되었습니다" |

### 4.3 회귀 가드 4 케이스 (F-FE-5 폐기)

| 케이스 | 변경 |
|---|---|
| F-FE-1 초기 fetch + 렌더 | 갱신 (mode select 검증 제거) |
| F-FE-2 슬라이더 조작 | 유지 |
| F-FE-3 저장 버튼 → PUT | 갱신 (PUT body 에 mode 제거 + 안내 배너 텍스트 검증) |
| F-FE-4 범위 외 입력 | 유지 |
| ~~F-FE-5 mode 토글~~ | **폐기** |

---

## 5. 회귀 가드 24 케이스 (v1 20 → v2 +4 자문)

### 5.1 카테고리 분포

| 카테고리 | v1 | v2 | 추가 |
|---|---|---|---|
| A `system_config` 단순화 | 4 | 4 | - |
| B scanner `_apply_price_filter` | 5 | 5 | - |
| **C 보유/익일청산 절대 보호 (HIGH)** | 3 | **4** | **+1 C-4 옵션 D 헬퍼 단독 (Q1)** |
| D 60s TTL 캐시 + invalidate (+ Q7-1) | 2 | 2 | - |
| E DailyEmitCap | 2 | 2 | - |
| F integration (E2E) | 3 | **4** | **+1 F-4 funnel step_no=98 hook (Q7-4)** |
| **G AST 정적 가드 (HIGH)** | 1 | **2** | **+1 G-2 protected_tickers keyword 의무 (Q1 옵션 D)** |
| **H scanner daily_summary (신규)** | 0 | **1** | **+1 H scanner 이전 (Q6 옵션 B)** |
| **합계 내부** | **20** | **24** | **+4** |
| C-Route API (외부 — 라우트) | 3 | 2 | mode 필드 제거 |
| F-FE 프론트 (외부 — UI) | 5 | 4 | mode 토글 케이스 폐기 |
| **합계 전체** | 28 | **30** | (24 + 2 + 4) |

### 5.2 분리 파일 청사진 (11 파일 — tdd-engineer 작업)

| # | 파일 | 카테고리 | 케이스 |
|---|---|---|---|
| 1 | `tests/unit/db/test_cycle64_price_filter_simplified_config.py` | A | 4 |
| 2 | `tests/unit/engine/test_cycle64_price_filter_scanner_apply.py` | B | 5 |
| 3 | `tests/unit/engine/test_cycle64_price_filter_scanner_protected.py` | C (HIGH) | 4 |
| 4 | `tests/unit/engine/test_cycle64_price_filter_scanner_cache.py` | D + Q7-1 | 2 |
| 5 | `tests/unit/engine/test_cycle64_price_filter_scanner_emit_cap.py` | E | 2 |
| 6 | `tests/integration/test_cycle64_price_filter_scanner_e2e.py` | F (F-1~F-3) | 3 |
| 7 | `tests/integration/test_cycle64_price_filter_scanner_funnel.py` | F-4 (Q7-4) | 1 |
| 8 | `tests/unit/engine/test_cycle64_price_filter_ast_guards.py` | G (HIGH) | 2 |
| 9 | `tests/unit/engine/test_cycle64_price_filter_scanner_daily_summary.py` | H | 1 |
| 10 | `tests/contract/test_cycle64_routes_price_filter_simplified.py` | C-Route | 2 |
| 11 | `frontend/src/components/__tests__/PriceFilterCard.test.tsx` (갱신) | F-FE | 4 |
| **합계 신규** | | | **30 (백엔드 26 + 프론트 4)** |

> 별도: 사이클 62 폐기 18 케이스 정리는 tdd-engineer Red 단계에서 파일별 폐기/갱신 의무 표기 (Red 명세 §5 참조).

### 5.3 안전성 분포

- **HIGH 6** — C 4 (보유/익일청산 절대 보호) + G 2 (AST 가드 + protected_tickers keyword 의무)
- **MEDIUM 6** — scanner 진입점 정확성 / 60s 캐시 race / Settings PUT 즉시 반영 / WS 구독 슬롯 영향 / 사이클 62 코드 완전 제거 / Q7-1 unsubscribe 미발화
- **LOW 18** — DB 단순화 / API 라우트 / Settings 카드 / emit cap / funnel hook / daily_summary / F-FE

---

## 6. 사이클 62 폐기/갱신 매트릭스 (영향 평가)

| 파일 | 사이클 64 액션 |
|---|---|
| `tests/unit/db/test_cycle62_price_filter_system_config.py` (A 5) | **갱신** — mode 인자 폐기, 3 케이스 갱신 (sets-only signature), 2 케이스 유지 (min/max 범위 검증) |
| `tests/unit/engine/test_cycle62_price_filter_risk_on_tick.py` (B 4) | **전체 폐기** — risk.on_tick 영역 자체 제거 |
| `tests/unit/engine/test_cycle62_price_filter_emit_cap.py` (C 2) | **전체 폐기** — scanner 영역 신규 E-1/E-2 로 대체 |
| `tests/unit/engine/test_cycle62_price_filter_cache.py` (D 2) | **전체 폐기** — scanner 영역 신규 D-1/D-2 로 대체 |
| `tests/unit/engine/test_cycle62_price_filter_sell_unaffected.py` (E 3+1) | **갱신** — risk → scanner 영역 답습 / E-4 AST 가드 영역만 이전 (`order_engine` 폴백 시 `_apply_price_filter` 호출 0건) |
| `tests/unit/engine/test_cycle62_price_filter_q2_fallback.py` (F 5) | **전체 폐기** — current_price fallback 자체 폐기, prdy_clpr 단독 신규 B 카테고리에서 검증 |
| `tests/unit/engine/test_cycle62_price_filter_warn_mode.py` (G 2) | **전체 폐기** — WARN 모드 자체 제거 |
| `tests/unit/engine/test_cycle62_price_filter_daily_summary.py` (H 1) | **폐기** — scanner 영역 신규 H 1 케이스로 대체 (`[price_filter_scanner_daily_summary]` 신규 prefix) |
| `tests/integration/test_cycle62_price_filter_integration.py` (I 5) | **전체 폐기** — F E2E 4 케이스로 대체 |
| `tests/contract/test_cycle62_routes_price_filter.py` (C-Route 3) | **갱신** — mode 필드 제거 (C-Route 2 케이스로 축소) |
| `frontend/src/components/__tests__/PriceFilterCard.test.tsx` (F-FE 5) | **갱신** — F-FE-5 mode 토글 폐기, F-FE-1/3 갱신 (4 케이스) |

**폐기 합계**: ~18 케이스
**갱신 합계**: ~10 케이스
**신규 합계**: 30 (본 사이클 v2 §5.2 11 파일)

---

## 7. 위험 평가 매트릭스 v2

| 영역 | 위험 | 완화 |
|---|---|---|
| **scanner 차단으로 매수 기회 손실** | MEDIUM | 디폴트 0/0 비활성 보존. 운영자 명시 활성화 의무 |
| **보유 종목 매도 영향** (HIGH 영역) | LOW | **C 4 케이스 + G-2 AST 가드 + 옵션 D 3 중 안전망** |
| **scanner 진입점 누락** (특정 전략) | LOW | **Q4 옵션 A 단일 hook** — 신규 전략 추가 시 자동 적용 |
| **prdy_clpr 미확보 처리** | LOW | **Q2 옵션 A graceful 통과** — B-4 케이스 검증 |
| **60s TTL 캐시 race** | LOW | D 카테고리 2 케이스 |
| **사이클 62 코드 완전 제거** | LOW | **G-1 AST 가드** (risk.py 가격 필터 참조 0건) |
| **Q7-1 자동 unsubscribe 위험** (HIGH 잔존) | LOW | invalidate_cache_scanner() unsubscribe 발화 0 (D 카테고리 검증) |
| **WS 구독 슬롯 영향** | LOW (긍정 효과) | F E2E 검증 |
| **Q7-5 갭상승 회피 폐기 위험** (HIGH 잔존) | **MEDIUM** | **사이클 65 거래대금 동행 필터 즉시 발주 의무** (본 카드 §15) |
| **API 라우트 / Settings UI** | LOW | C-Route + F-FE 카테고리 |

→ **HIGH 0 (잔존)** / **MEDIUM 2** (매수 기회 손실 + Q7-5 갭상승 폐기 위험) / **LOW 18**. 자금 손실 위험 0.

---

## 8. 사이클 분할

- **단일 사이클** (백엔드 + 프론트 동시) — 사이클 62 패턴 답습
- 예상 소요: tdd-engineer Red (2h) + backend-dev Green (2.5h) + frontend-dev Green (1h) + tester Verify (1.5h) + sync-docs (0.5h) = **~7.5h**

---

## 9. push 시점

- **즉시 push 가능** — 디폴트 0/0 비활성 보존 → 운영 영향 0
- 토요일 (2026-06-06) = KRX/NXT 휴장 → push 시점 유연
- tester verify 완료 후 사용자 명시 commit 지시 대기

---

## 10. 절대 깨지면 안 되는 것 (체크리스트 v2)

CLAUDE.md 절대 규칙 + 사이클 32 R4 universe guard + 사이클 38 명문화 + 자문 옵션 D 답습:

- [x] 체결통보 구독 영역 무관
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 영향 0
- [x] **보유/익일청산 절대 보호** (사이클 32 R4 + 옵션 D 3 중 안전망) — C 4 케이스 + G-2 AST 가드
- [x] **`tradable_boards` 매수 진입 전용** (사이클 38) — scanner 필터 매수 후보 전용, 매도/손절/Trailing/익일청산/15:20 강제청산 모두 필터 미적용
- [x] **시장가 거부 5호가 폴백 시 필터 재평가 금지** — `order_engine.py` 시장가 폴백 시 `_apply_price_filter` 호출 0건 (사이클 62 E-4 AST 가드 영역 이전)
- [x] `_reset_daily_state` 동행 reset — scanner emit cap + daily_summary counters clear 의무
- [x] `_settle()` 진입 직전 daily_summary emit (reset 보다 먼저)
- [x] KST 강제
- [x] logger 명시 binding — `logging.getLogger("src.engine.scanner")`
- [x] 사이클 31 매수 가드 4 모드와 충돌 없음 — 영역 완전 분리
- [x] **graceful 통과 영속** — prdy_clpr 미확보 종목 매수 차단 금지 (Q2 옵션 A)
- [x] **사이클 62 코드 완전 제거** — risk.py 에 price_filter 참조 0건 (G-1 AST 가드)
- [x] **`_apply_price_filter` 호출 시 protected_tickers keyword 의무** — 누락 시 빌드 실패 (G-2 AST 가드)
- [x] **Q7-1 자동 unsubscribe 미발화** — invalidate_cache_scanner() 가 unsubscribe 발화 0, 5분 자연 delta 위임 (사이클 17 OPSP0002 답습)
- [x] **Q7-4 funnel step_no=98 hook graceful** — funnel insert 실패 시 매수 후보 평가 무영향
- [x] **Q7-5 갭상승 회피 효과 폐기 인지** — 사이클 65 거래대금 동행 필터 즉시 발주 의무

---

## 11. 발주 순서 (사이클 60~63 패턴 답습)

1. ✅ **team-leader (현재 작업)** — 본 설계 카드 v2 갱신 + Red 명세 (`_workspace/red/cycle64_price_filter_scanner.md`) + 사이클 65 sketch (`_workspace/cycle65_trade_amount_filter_domain_consult.md`) 3 산출물
2. **tdd-engineer Red 발주 (다음 단계)** — Red 명세 기반 30 케이스 본체 작성 + 사이클 62 폐기 18 케이스 정리 (or 폐기 의무 표기)
3. **backend-dev + frontend-dev 동시 Green 발주**
4. **tester Verify** — V1~V13 + HIGH 6 우선 + flakiness 3 회 반복 + AST 가드 + WS 슬롯 영향
5. **sync-docs** — CLAUDE.md / HARNESS_CHANGELOG / src/engine/CLAUDE.md / src/db/CLAUDE.md / frontend/CLAUDE.md / refactor-review 메모 카드 #15 (Q7-2 액면분할 invalidate) + 사이클 64 회고
6. **사용자 명시 commit + push 지시 대기** — 디폴트 0/0 영속 → 즉시 push 안전
7. **사이클 65 즉시 발주** — Q7-5 거래대금 동행 필터 (`_workspace/cycle65_trade_amount_filter_domain_consult.md` 기반)

---

## 12. 사이클 60~63 답습 패턴 매트릭스

| 항목 | 사이클 60~63 | 사이클 64 v2 |
|---|---|---|
| logger 명시 binding | ✅ `getLogger("src.engine.scheduler")` | `getLogger("src.engine.scanner")` 동일 패턴 |
| 카테고리 분리 측정 (tester) | ✅ 4~11 카테고리 + flakiness 3회 | 11 파일 분리 + flakiness 3회 (동일 답습) |
| HIGH 케이스 우선 검증 | ✅ HIGH 영역 우선 | **HIGH 6** (C 4 + G 2) 우선 |
| `_reset_daily_state` 동행 | ✅ 사이클 32 universe guard | scanner emit cap + daily_summary counters 동행 |
| AST 정적 가드 | ✅ 사이클 60 Q3-G6 / 사이클 61 D-1 / 사이클 63 D-2 | **G 카테고리 2 케이스** (G-1 risk.py 잔존 0 + G-2 protected_tickers keyword 의무) |
| 부분 UNIQUE 인덱스 (사이클 30) | 해당 없음 | 해당 없음 |
| 옵션 D 신규 발의 (자문) | 사이클 62 자문 Q3 폴백 가드 | **Q1 옵션 D 3 중 안전망 채택** |

---

## 13. 다음 단계 즉시 작업

| # | 단계 | 에이전트 / 도구 | 산출물 |
|---|---|---|---|
| ✅ 1 | team-leader v2 + Red 명세 + 사이클 65 sketch | team-leader | 본 카드 v2 / `_workspace/red/cycle64_price_filter_scanner.md` / `_workspace/cycle65_trade_amount_filter_domain_consult.md` |
| 2 | tdd-engineer Red | Task (tdd-engineer) | 30 케이스 본체 + 사이클 62 폐기 정리 |
| 3 | backend-dev Green | Task (backend-dev) | `system_config.py` 단순화 + `scanner.py` 신규 + `risk.py` 제거 + `routes/system.py` 갱신 + scheduler 동행 |
| 4 | frontend-dev Green | Task (frontend-dev) | `types/price-filter.ts` + `PriceFilterCard.tsx` 단순화 |
| 5 | tester Verify | Task (tester) | HIGH 6 우선 + flakiness 3회 + AST 가드 |
| 6 | sync-docs | Task (skill `sync-docs`) | CLAUDE.md + HARNESS_CHANGELOG + 카드 #15 |
| 7 | commit + push | 사용자 명시 + git | 디폴트 0/0 보존 → 즉시 push 안전 |
| 8 | **사이클 65 즉시 발주** | team-leader → domain-expert | Q7-5 거래대금 동행 필터 |

---

## 14. 안전 가드

- 본 v2 작성은 운영 영향 0 (문서 산출물만)
- 사이클 64 실제 발주는 사용자 명시 지시 후 별도 진행
- HIGH 6 등급이므로 옵션 D 3 중 안전망 + tester verify 우선 의무
- Q7-5 갭상승 회피 효과 폐기는 사이클 65 거래대금 필터로 즉시 보강 의무

---

## 15. 후속 카드 (사이클 64 이후)

| # | 카드 | 등급 | 시점 |
|---|---|---|---|
| **사이클 65** | **거래대금 동행 필터 (Q7-5 인계 — HIGH)** | **HIGH** | **본 사이클 종료 직후 즉시 발주** — sketch `_workspace/cycle65_trade_amount_filter_domain_consult.md` |
| 카드 #15 | 액면분할/정정공시 stock_master invalidate (Q7-2) | LOW | 후속 사이클 (희소 사건) |
| 사이클 66+ | stale_manager.py 1,076L sub-module 분해 (refactor-review 카드 #14) | MEDIUM | 사이클 64~65 종료 후 |
| 사이클 67+ | 사이클 62 운영 데이터 손실 인계 회고 (Q7-3) | LOW | HARNESS_CHANGELOG 기록 시 흡수 |
