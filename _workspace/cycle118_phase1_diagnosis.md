# 사이클 118 Phase 1 진단 — Plan Phase B (donchian/VCP stock_master 베이스 전환)

## 발주 컨텍스트

- 사이클 117 (2026-06-12 16:14 KST) hotfix 영구 성공 → stock_master 60 → **1,008 ticker** 정상화 영구 확정.
- 사이클 108 (Plan Phase A) VB/LTV/BFB 전환 완료 영구 영속.
- 사이클 100 인계 영역 영구 영속 + Plan Phase B 신규 발주 사이클 = 본 사이클 118.

## 결정적 발견 (운영 실측 Supabase MCP READ-ONLY)

### stock_master 운영 실측 (사이클 117 hotfix 후 영구 영속)

| 영역 | 값 | 비율 |
|------|-----|------|
| total | 2,697 | 100% |
| `hts_avls_present` (시총 키 영역) | 2,693 | **99.85%** |
| `acml_tr_pbmn_present` (거래대금 키 영역) | **77** | **2.85%** |
| KOSPI | 922 | 34.2% |
| KOSDAQ | 1,775 | 65.8% |
| `nxt_tradable=true` | **65** | **2.4%** |

### 결정적 운영 영향 분석

#### 1. 거래대금 키 부재 영역 영구 영속 (HIGH 위험)

`acml_tr_pbmn_present 77/2697 = 2.85%` — 사이클 107 raw 보강 (`inquire_stock_basics` CTPF1002R + FHKST01010100 merge) 이 운영 stock_master 영역에 거의 미적용됨. `acml_tr_pbmn` 부재 종목은 `int(raw.get("acml_tr_pbmn") or 0) = 0` → 거래대금 필터 통과 못함.

**영향 매트릭스** (DEFAULT_PARAMS 값 기준):

| 시정 시나리오 | donchian 통과 | VCP 통과 |
|--------------|--------------|----------|
| 시총만 (거래대금 0) | 661 종목 | 1,331 종목 |
| **시총 + 거래대금 (사이클 108 DEFAULT)** | **28 종목** | **35 종목** |
| 시총 + 거래대금 + nxt_tradable=true | 28 종목 | 34 종목 |

**현재 코드 (사이클 49 이전 영구 영속)** = `KOSPI_200_TICKERS ∪ KOSDAQ_150_TICKERS` 고정 350 종목 영역에서 시총 컷 → 일봉 fetch → 통과.

**사이클 108 패턴 답습 시 (거래대금 필터 적용)** → 28 / 35 종목으로 **drastic 폭축** → 멀티데이 신호 빈도 -90~95% 감소 가능성. HIGH 위험.

#### 2. nxt_tradable=true 영역 영구 영속 (보수적 KRX fallback)

`nxt_tradable=true 65 종목 / 2,697 = 2.4%` — 사이클 94 (`nxt_tradable` default False, 보수적 KRX fallback) 영역 영구 영속이.

도치안/VCP 는 **DEFAULT_TRADABLE_BOARDS = ("main",)** 영역 영구 영속 = MAIN 단독 (KRX). NXT 거래성 의존성 0. **`nxt_tradable=None`** 전체 영역 영속이 적합.

## 현재 코드 영역 분석

### `src/engine/strategies/donchian_swing.py:405~454` `_scan_universe()` 영역 영구 영속

**현재 (사이클 49 이전 영역)** — KIS API 호출 영역:
- `from src.engine.scanner import KOSDAQ_150_TICKERS, KOSPI_200_TICKERS` 고정 350 종목 영역
- `from src.api.condition import fetch_stock_detail` 호출 영역 = **350 × KIS REST 호출** (Rate Limit 50ms sleep)
- `price * listed = mcap` 영역 = 시총 직접 계산
- 거래대금 필터 0 (`prepare()` 의 `volume_multiplier 1.5×` 영역에서 일원화)

### `src/engine/strategies/vcp_breakout.py:694~728` `_scan_universe()` 영역 영구 영속

**현재 (사이클 49 이전 영역)** — KIS API 호출 영역:
- donchian 컨벤션 재사용 (`KOSPI_200_TICKERS ∪ KOSDAQ_150_TICKERS` 고정 350 종목)
- `fetch_stock_detail()` 350 × KIS REST 호출
- 시총만 필터 (`mcap >= min_mcap`)

### KIS API 호출 영역 영구 영속

donchian + VCP `_scan_universe()` = **2 × 350 = 700 KIS REST 호출/일** (사이클 17 OPSP0002 backoff + KIS LMS chain 안전 영역 영구 영속).

## 사이클 108 답습 패턴 영구 영속 분석

### 동일 패턴 영역

1. **DEFAULT_PARAMS 영역 4 필터 추가**: `min_market_cap` + `min_trade_amount` + `exclude_tickers` + `nxt_tradable` — donchian/VCP 이미 일부 키 존재 (`min_market_cap` + `min_trade_amount`).
2. **`_scan_universe()` 영역 = `stock_master.list_by_filter()` 호출 영구 영속**.
3. **ETF 키워드 제외 영역 + 6자리 ticker 필터링 영속**.
4. **funnel 카운터 영속** (`universe_candidates` + `universe_filtered` + `last_run_at`).
5. **graceful 영역** (raise 시 빈 list 반환).

### 차이점 영역 (멀티데이 보유 영역 영구 영속 위험)

1. **`Position._MULTIDAY_STRATEGIES = frozenset({donchian_swing, vcp_breakout})`** 영구 영속 — `is_next_day` 항상 False.
2. **`_check_force_clear()` 영역 = `return []`** (15:20 강제 청산 없음 영구 영속).
3. **사이클 49 VCP Pullback 시정 영속** (멀티데이 보유 영역 + 4중 청산: 손절/베이스 하단/ATR 트레일링/50일 EMA).
4. **donchian `_swing_rest_poll_loop`** 60s 영역 영구 영속 (사이클 49 영속).
5. **멀티데이 보유 종목 영역 영구 영속이** = stock_master에서 사라지는 영역 영구 영속이 위험 (TTL skip + KRX 1차 가용 영역).

### `prepare()` 영역 영구 영속

도치안 + VCP `prepare()` = `_scan_universe()` 호출 → `fetch_daily_candles()` (60일/220일) → `_check_trend_filter` / `_check_pullback_sequence` / `_check_volume_contraction` 영역 영구 영속. **`_scan_universe()` 만 시정 영역** (사이클 108 동일).

### 보유 종목 영역 영구 영속이 (`recompute_held_atr()` + `recompute_high_since_buy()`)

- 도치안: `recompute_held_atr()` (사이클 E3) — 보유 종목 ATR + `high_since_buy` 폴백 보정 영역. `fetch_daily_candles()` 직접 호출. `_scan_universe()` 와 별개.
- **이 영역은 시정 무관 영구 영속** (사이클 49 영속 + 보유 종목 핫 패스 영구 영속).

## 영속 의무 매트릭스 (사이클 118 전수 영속)

- 사이클 17 KIS LMS chain backoff
- 사이클 29 005935 LMS chain 진단 의무
- 사이클 32 R4 universe guard (보유/익일청산 절대 보호)
- 사이클 38 명문화 (scanner 단계 매수 진입 전 후보 풀 영역 한정)
- 사이클 49 VCP Pullback 시정 영속 (멀티데이 보유 영역 + 4중 청산)
- 사이클 65 거래대금 필터 (`_apply_trade_amount_filter` 영역 영구 영속, scanner 단계 hook)
- 사이클 78 G-AST1 + 79 G-AST2 영속
- 사이클 81 G-AST1 (KIS `bfdy_clpr` / `hts_avls` 덮어쓰기 금지)
- 사이클 88 G-REJECT (graceful)
- 사이클 89 ETF 키워드 제외 + 6자리 ticker 영속
- 사이클 94 nxt_tradable default False (보수적 KRX fallback)
- 사이클 100 인계 (Plan Phase B donchian/VCP 영역)
- 사이클 107 raw 보강 (CTPF1002R + FHKST01010100 merge)
- 사이클 108 Plan Phase A (VB/LTV/BFB 전환 영구 영속, `list_by_filter()` 신규 메서드 영구 영속)
- 사이클 110 silent 결함 시정
- 사이클 112 KRX 인프라
- 사이클 115 Q3=C 폴백
- 사이클 116 MKTCAP 환산
- 사이클 117 basDd 재시도 + source 키
- CLAUDE.md "절대 깨지 말 것" 8 영역

## 매매 안전성 평가

**핵심 위험 영역** (MEDIUM):
1. **신호 빈도 감소** (donchian -90~95% / VCP -90~95% 가능성) — `acml_tr_pbmn_present 2.85%` 영역 영구 영속이 결정적 원인.
2. **멀티데이 보유 종목 영역 영구 영속이** — stock_master TTL skip + KRX 1차 가용 영역 영구 영속에 직접 의존.
3. **사이클 49 VCP Pullback 시정 영속** — `_scan_universe()` 시정만으론 영향 없으나, `prepare()` candle fetch 영역과 통합 검증 의무.

**안전 영역**:
- scanner 단계 매수 진입 전 후보 풀 영역 한정 영구 영속 + 매도/익일청산 hot path 무관 영구 영속.
- 사이클 38 명문화 영속 + 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호).

## 사용자 결정 의제 (Q1~Q6)

### Q1: 시정 영역 (시정 시점 분리 vs 통합)

- **A**: 통합 단일 사이클 (사이클 118 = donchian + VCP 동시 전환) — 사이클 108 답습 패턴
- **B**: 분리 사이클 (사이클 118 donchian / 사이클 119 VCP) — 멀티데이 보유 영역 영구 영속 위험 완화

### Q2: 필터 임계 (`min_market_cap` / `min_trade_amount`)

**A**: DEFAULT_PARAMS 값 유지 (donchian 3,000억/50억 + VCP 1,000억/30억) — 운영 신호 28/35 종목 폭축 영역 영구 영속이 허용

**B**: 거래대금 필터 0 (시총만 적용) — donchian 661/VCP 1,331 종목 영역 영구 영속이 = 사이클 49 이전 영역과 유사 신호 수준

**C**: 거래대금 graceful 통과 (`acml_tr_pbmn=0` 시 통과) — `list_by_filter()` 영역 영구 영속이 현재 `< min_trade_amount` 시 skip 영구 영속이 결함

**D**: 임시 완화 (거래대금 임계 50억 → 10억 / 30억 → 5억) — 사이클 117 후 stock_master 운영 영역에서 `acml_tr_pbmn` 적재 영역 영구 영속이 점진 증가 대기

### Q3: SECUGRP_NM ETF 분류 통합 영역

- **A**: Plan Phase B에 포함 (사이클 118) — 종합 시정 영역
- **B**: 별개 사이클 (사이클 119+) — 사이클 108 답습 패턴 영구 영속 (ETF 키워드 제외 영역 영구 영속이 이미 사이클 89 영속)

### Q4: 신호 -90~95% 감소 허용도 + 영향 모니터링

- **A**: 허용 + 운영 1주 모니터링 (D+1 운영 측정 의무) — 사이클 108 패턴
- **B**: 비허용 + Q2=B (시총만 적용) 으로 신호 빈도 보존 — 사이클 49 이전 영역 유사
- **C**: 비허용 + Q2=C/D (graceful 통과 또는 임시 완화) — 점진 증가 대기

### Q5: nxt_tradable 영역 영구 영속이

- **A**: `nxt_tradable=None` (전체) — donchian/VCP MAIN 단독 + 65/2697 영구 영속이 NXT 의존성 0
- **B**: `nxt_tradable=True` (사이클 108 VB/LTV/BFB 답습) — 65 종목으로 폭축 영구 영속이

### Q6: 매매 안전성 우선 영역 (사이클 49 VCP Pullback 시정 영속 영구 보장)

- **A**: 멀티데이 보유 종목 영역 영구 영속이 절대 보호 + `_scan_universe()` 시정만 (`prepare()` 영역 무변경) — 사이클 49 영속 100% 보장
- **B**: domain-expert 자문 의무 — 멀티데이 보유 영역 + 사이클 49 영속 영향 평가 의무

## 권장 사항 (team-leader 의견)

- **Q1=A** (통합 단일 사이클, 사이클 108 답습 패턴)
- **Q2=D** (임시 완화 50억→10억 / 30억→5억) — `acml_tr_pbmn_present 2.85%` 영역 영구 영속이 점진 증가 대기 + 신호 빈도 보존 (donchian ~80 / VCP ~150 종목 예상)
- **Q3=B** (별개 사이클, 사이클 119+) — ETF 키워드 제외 영역 영구 영속이 이미 영속
- **Q4=C** (Q2=D 결합) — 점진 증가 대기 + 1주 운영 측정 의무
- **Q5=A** (`nxt_tradable=None` 전체) — donchian/VCP MAIN 단독 영역 영구 영속이
- **Q6=B** (domain-expert 자문 의무) — 멀티데이 보유 영역 + 사이클 49 영속 영향 평가

## D+1 운영 측정 의무 (사이클 119+ 인계)

- 2026-06-13 (금) 09:30~ donchian/VCP `prepare()` 정상 작동 영구 영속 확인.
- KIS API 호출 영역 변화 = 700 → 0 호출/일 영구 영속 (도치안 + VCP 통합).
- 신호 빈도 측정 (사이클 49 이전 baseline 대비 ±X%).
- 멀티데이 보유 종목 영역 영구 영속이 안전 (사이클 49 VCP 4중 청산 정상 작동).

## 영속 의무 매트릭스 영구 영속 (전수 영속)

전수 영속 — 사이클 17/29/32/38/49/65/78/79/81/88/89/94/100/107/108/110/112/115/116/117 + CLAUDE.md "절대 깨지 말 것" 8 영역.
