# 사이클 148 Red — VB prepare() 가격 max 필터 추가

작성일: 2026-06-16
의제 #1 단독. 사용자 결정: Q1=B (VB 단독) + Q2=C (PriceFilter 단일 source) + Q3=A (scanner 유지) + Q4=B (MEDIUM).

## 운영 실증 (Phase 1 진단)

- 6/16 11:11:27~30 KST: 6 종목 (298040 / 000660 / 009150 / 402340 / 011070 / 012450) bfdy_clpr > max=500,000원 → scanner `_apply_price_filter` 차단.
- VB prepare() 영역 31 종목 통과 → scanner 영역 25 종목 통과 → UI funnel snapshot에 차단 종목 6개 노출 결함.
- 근본 원인: VB `_scan_universe()` = `list_by_filter(min_market_cap, min_trade_amount)` 만 호출, 가격 필터 부재.

## 행위 분해

### 행위 1: VB prepare()가 PriceFilter 활성 시 가격 max 초과 종목을 차단한다
- 입력: stock_master에 6 종목 + bfdy_clpr (450,000 / 600,000 / 700,000 등) + PriceFilter(min=0, max=500_000)
- 기대: `_scan_universe()` 결과에서 600,000 / 700,000 종목 차단, 450,000 종목 통과.

### 행위 2: VB prepare()가 PriceFilter 활성 시 가격 min 미달 종목을 차단한다
- 입력: bfdy_clpr (3,000 / 4,000 / 6,000) + PriceFilter(min=5_000, max=0)
- 기대: 3,000 / 4,000 차단, 6,000 통과.

### 행위 3: VB prepare()가 PriceFilter 비활성 시 모든 종목을 통과시킨다 (회귀 보존)
- 입력: PriceFilter(min=0, max=0)
- 기대: list_by_filter 결과 전수 통과 (가격 필터 미적용).

### 행위 4: VB prepare()가 system_config PriceFilter 단일 source 키를 조회한다
- 입력: `get_price_filter()` mock 호출
- 기대: `src.db.system_config.get_price_filter` 호출 ≥1 검증.

### 행위 5: VB prepare()가 raw.bfdy_clpr miss 종목을 graceful 통과시킨다
- 입력: stock_master raw에 bfdy_clpr 키 부재 + PriceFilter(min=10_000, max=500_000)
- 기대: 해당 종목 통과 (사이클 64 graceful 영속).

### 행위 6: scanner `_apply_price_filter` 영역 변경 0 (G-148-PRICE-4)
- AST 가드: `src/engine/scanner.py::_apply_price_filter` 함수 시그너처 + 본체 변경 0.

### 행위 7: list_by_filter() 시그너처 변경 0 (G-148-PRICE-5)
- AST 가드: `src/db/stock_master.py::list_by_filter` 시그너처 (`min_market_cap`, `min_trade_amount`, `exclude_tickers`, `nxt_tradable`, `market`, `limit`) 변경 0.

### 행위 8: VB FUNNEL_STAGES 영역 영속 (G-148-FUNNEL-1)
- VB_FUNNEL_STAGES 5 단계 (사이클 143) 변경 0. 가격 필터 차단은 step 2 (시총+거래대금) 다음 신규 단계 또는 기존 step 2 흡수 — 선택 = step 2 흡수 (가격 필터는 prepare() universe 영역 후처리).

### 행위 9: VB prepare() 본체 check_exit_signal 호출 0건 (G-148-SAFETY-1)
- AST 가드: VB prepare 본체에 `check_exit_signal` import / call 0건. 사이클 30 005935 영역 매매 안전성 무영향.

### 행위 10: VB prepare()가 보유 종목 가격 필터 차단 0건 (G-148-SAFETY-3)
- 입력: positions에 1 종목 + 해당 ticker bfdy_clpr > max
- 기대: 통과 (사이클 32 R4 답습 — 보유 절대 보호).

## Green 명세

### VB `_scan_universe()` 영역 확장

```python
# src/engine/strategies/volatility_breakout.py::_scan_universe() 종료 직전
from src.db.system_config import get_price_filter
pf = await get_price_filter()
if pf.is_active:
    # 사이클 148 — prepare 영역 가격 필터 후처리 (사이클 64 scanner 정합 + PriceFilter 단일 source)
    filtered = await self._apply_price_filter_in_prepare(filtered, pf)
```

### VB 신규 메서드 `_apply_price_filter_in_prepare(tickers, pf)`

```python
async def _apply_price_filter_in_prepare(
    self,
    tickers: list[str],
    pf: "PriceFilter",
) -> list[str]:
    """VB prepare 영역 가격 필터 후처리 (사이클 148).

    사이클 64 scanner `_apply_price_filter` 패턴 답습 + PriceFilter 단일 source.
    보유/익일청산 절대 보호 (사이클 32 R4) + raw.bfdy_clpr miss graceful 통과.
    """
    from src.db import stock_master as _sm_mod

    # 보유 종목 절대 보호 (사이클 32 R4 답습)
    protected = set()
    try:
        for s in self._registry.all() if hasattr(self, "_registry") else []:
            protected.update(s.state.positions.keys())
    except Exception:
        pass

    survivors: list[str] = []
    for ticker in tickers:
        if ticker in protected:
            survivors.append(ticker)
            continue
        prdy_clpr = 0
        try:
            basics = await _sm_mod.get(ticker)
            if basics and basics.raw:
                raw_val = basics.raw.get("bfdy_clpr", 0)
                if raw_val:
                    prdy_clpr = int(raw_val)
        except Exception:
            pass
        if prdy_clpr <= 0:
            survivors.append(ticker)
            continue
        below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
        above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
        if not (below_min or above_max):
            survivors.append(ticker)
    return survivors
```

### 영속 의무

- VB DEFAULT_PARAMS 변경 0 (PriceFilter 단일 source).
- `list_by_filter()` 시그너처 변경 0.
- scanner `_apply_price_filter` 변경 0 (이중 안전망).
- VB_FUNNEL_STAGES 5 단계 변경 0 (step 2 = 시총 + 거래대금 + 가격 흡수).
- 사이클 30 005935 / 사이클 32 R4 / 사이클 38 명문화 / 사이클 64 / 사이클 65 / 사이클 143 모두 영속.

## 회귀 가드 케이스 (10개)

| ID | 행위 | 위험 |
|----|------|------|
| G-148-PRICE-1 | VB prepare 가격 max 차단 (6 종목 운영 실증) | HIGH |
| G-148-PRICE-2 | VB prepare 가격 min 동행 | MEDIUM |
| G-148-PRICE-3 | PriceFilter 비활성 시 전수 통과 (회귀) | MEDIUM |
| G-148-PRICE-4 | scanner `_apply_price_filter` 변경 0 (AST) | LOW |
| G-148-PRICE-5 | list_by_filter 시그너처 변경 0 (AST) | LOW |
| G-148-FUNNEL-1 | VB_FUNNEL_STAGES 5 단계 변경 0 | LOW |
| G-AST-148 | VB prepare PriceFilter 단일 source AST | LOW |
| G-148-SAFETY-1 | VB prepare check_exit_signal 호출 0건 | HIGH |
| G-148-SAFETY-2 | risk.on_tick / order_engine import 0 | HIGH |
| G-148-SAFETY-3 | 보유 종목 가격 필터 차단 0건 | HIGH |
