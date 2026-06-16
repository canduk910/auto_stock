# 사이클 151 — 4 전략 (LTV/donchian/BFB/VCP) prepare() 가격 필터 확대 (MEDIUM)

## 사용자 verbatim (2026-06-16 16:54 KST)

> "아까 변동성돌파에만 적용했던 작업 나머지 전략에도 확대하자."

## 사이클 148 영역 영속

사이클 148 = VB `prepare()` `_apply_price_filter_in_prepare()` 신규 (+66L net). 운영 실증 영구 영속:
- 11:11:27~33 KST 12 종목 (6 ticker × 2 호출) 차단 정합
- VB 영역 31 → 25 종목 영구 영속
- 매매 안전성 무영향 (보유 종목 절대 보호 + bfdy_clpr miss graceful)

## Phase 1 진단 — 4 전략 prepare() 영역 영구 영속 확인 완료

### 매트릭스

| 전략 | `_scan_universe()` | `_apply_price_filter_in_prepare()` | 확대 의무 |
|------|-------------------|-------------------------------------|----------|
| LTV (long_tail_volatility) | L335 (`return filtered` L395) | **부재** | YES |
| donchian_swing | L427 (`return filtered` L508) | **부재** | YES |
| bull_flag_breakout | L574 (`return filtered` L632) | **부재** | YES |
| vcp_breakout | L722 (`return filtered` L756) | **부재** | YES |
| ~~VB~~ | 사이클 148 영구 영속 (변경 0) | L353~411 영구 영속 | 완료 |

### 사이클 148 패턴 영속 (4 전략 답습 의무)

영역 A — 각 `_scan_universe()` `return filtered` 직전 1줄:
```python
filtered = await self._apply_price_filter_in_prepare(filtered)
```

영역 B — 각 전략 `_apply_price_filter_in_prepare()` 신규 메서드 (사이클 148 VB 답습, ~60L × 4 = ~240L 추정).

### 영속 의무 (4 전략 동일)

- PriceFilter 단일 source (`system_config.get_price_filter`)
- 보유 종목 절대 보호 (사이클 32 R4 + 사이클 30 005935)
- `raw.bfdy_clpr` miss → graceful 통과 (사이클 64 답습)
- PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존)
- scanner `_apply_price_filter` 영속 (이중 안전망)
- 매수 진입 *전* 영역 한정 (사이클 38 명문화 영속)
- 사이클 143 (LTV) / 사이클 39+41 (BFB/VCP/donchian) FUNNEL_STAGES 영속
- `_collect_protected_tickers_for_scanner` 헬퍼 재사용 (사이클 64 영속)

## TDD Red → Green → Verify

### 1. tdd-engineer Red (회귀 가드)

4 전략 각 영역 12 케이스 × 4 = 48 케이스:
- G-151-{LTV|DC|BFB|VCP}-PRICE-1 (HIGH): 가격 max 차단 (운영 실증 답습)
- G-151-*-PRICE-2: 가격 min 동행
- G-151-*-PRICE-3: PriceFilter 비활성 회귀 보존
- G-151-*-PRICE-4: protected_tickers keyword 영속
- G-151-*-PRICE-5: list_by_filter 시그너처 변경 0
- G-151-*-FUNNEL-1: FUNNEL_STAGES 영속 (LTV 6단계 / BFB+VCP+donchian 8단계)
- G-151-AST-1: 4 전략 `get_price_filter` import 영속
- G-151-AST-2: DEFAULT_PARAMS 별도 가격 키 금지
- **G-151-*-SAFETY-1 (HIGH)**: check_exit_signal 호출 0건
- **G-151-*-SAFETY-2 (HIGH)**: risk/order_engine import 0
- **G-151-*-SAFETY-3 (HIGH)**: 보유 종목 차단 0건
- G-151-INT-1: scanner `_apply_price_filter` 변경 0

### 2. backend-dev Green

4 전략 각 영역 (LTV/donchian/BFB/VCP):
- `_scan_universe()` `return filtered` 직전 1줄 추가
- `_apply_price_filter_in_prepare()` 신규 메서드 (사이클 148 VB 영역 100% 답습)

production +240~280L 추정.

### 3. tester verify

- 풀 회귀 3회 flakiness 0 (2,848 → ~2,896)
- 사이클 151 격리 PASS
- Supabase MCP READ-ONLY = 4 전략 차단 정합 검증
- 매매 안전성 8영역 + 사이클 30/32 R4/38/64/65/143/148 변경 0

## 영속 의무

- CLAUDE.md "절대 깨지 말 것" 8 영역 영속
- 사이클 30 005935 매매 안전성 영속
- 사이클 32 R4 universe guard (보유/익일청산 절대 보호)
- 사이클 38 명문화 (scanner 매수 진입 전 영역 한정)
- 사이클 39+41 BFB/VCP/donchian FUNNEL_STAGES 영속
- 사이클 64 PriceFilter 영역 영속
- 사이클 65 거래대금 동행 영속
- 사이클 143 LTV FUNNEL_STAGES 영속
- 사이클 148 VB 영역 영구 영속 (변경 0)
- commit/push 사용자 명시 승인 전 절대 금지

## Green 결과

### Red 테스트 (tdd-engineer)
- 파일: `tests/unit/engine/strategies/test_cycle151_4_strategies_price_filter.py`
- 32 케이스 (4 전략 × 6 + 공통 AST 5 + 공통 SAFETY AST 3)
- Red 확인: `AttributeError: 'LongTailVolatilityStrategy' object has no attribute '_apply_price_filter_in_prepare'`

### Green 구현 (backend-dev)
- `src/engine/strategies/long_tail_volatility.py` +63L
- `src/engine/strategies/donchian_swing.py` +63L
- `src/engine/strategies/bull_flag_breakout.py` +63L
- `src/engine/strategies/vcp_breakout.py` +64L
- production +253L 합계 (사이클 148 VB 영역 답습 100%)

### tester verify
- 사이클 151 격리: **32/32 PASS** (0.24s)
- 백엔드 풀 회귀 3회 모두 **2,880 PASS / 2 skipped / 157 xfailed / 2 xpassed** (사이클 150 시점 2,848 + 신규 32 = 정확)
- flakiness 0 (84.71s / 85.03s / 85.57s, ±0.5%)
- 사이클 150 인계 결함 0건 (Supabase 영역 영속)

### 매매 안전성 영역 영속 검증
- check_exit_signal 호출 0건 영속 (4 전략 _apply_price_filter_in_prepare 본체 AST 가드)
- risk.on_tick / order_engine import 0건 영속 (4 전략 소스 AST 가드)
- 보유 종목 절대 보호 영속 (사이클 32 R4 답습 — `_collect_protected_tickers_for_scanner` 헬퍼 재사용)
- raw.bfdy_clpr miss graceful 통과 영속 (사이클 64 답습)
- stock_master.get() 예외 graceful 통과 영속 (사이클 88 G-REJECT 답습)
- PriceFilter 비활성 시 전수 통과 영속 (회귀 보존)
- scanner `_apply_price_filter` 변경 0 (이중 안전망 영속)
- 사이클 143 LTV FUNNEL_STAGES 변경 0 (사이클 39+41 BFB/VCP/donchian FUNNEL_STAGES 변경 0)
- DEFAULT_PARAMS 별도 가격 키 (min_price/max_price) 추가 0건 (단일 source = system_config 영속)
- 사이클 148 VB 영역 변경 0 (volatility_breakout.py 변경 0건)

### commit/push 사용자 명시 승인 대기
