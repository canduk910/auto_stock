# Red 명세 — 사이클 119 donchian_swing stock_master 전환

## 사용자 결정 영구 영속
- Q1=B donchian 단독
- Q2=D 임시 완화 (500억 / 10억)
- Q5=A nxt_tradable=None
- Q6=B domain-expert 자문 필수 (team-leader 직접 자문 완료)

## 사이클 108 답습 패턴 영구 영속

VB/LTV/BFB 사이클 108 시정 패턴 100% 답습:
1. DEFAULT_PARAMS 영역 4 필터 추가
2. `_scan_universe()` 영역 = `stock_master.list_by_filter()` 전환
3. ticker 6자리 + ETF 키워드 제외 + ticker_names 보강 영속
4. funnel 카운터 영속 (`universe_candidates` + `universe_filtered` + `last_run_at`)
5. graceful 영역 (raise 시 빈 list + scan_stats 0)
6. KIS API 직접 호출 0 (350 호출/일 → 0 호출/일)

## 회귀 가드 매트릭스 (사이클 108 답습)

### HIGH (4)

**H-1**: DEFAULT_PARAMS 4 필터 신규 키 영구 영속
- `min_market_cap == 50_000_000_000` (500억, Q2=D 임시 완화)
- `min_trade_amount == 1_000_000_000` (10억, Q2=D 임시 완화)
- `exclude_tickers == []` (빈 list 디폴트)
- `nxt_tradable is None` (Q5=A donchian MAIN 단독)

**H-2**: `_scan_universe()` = `stock_master.list_by_filter()` 호출 영속
- `list_by_filter(min_market_cap=, min_trade_amount=, exclude_tickers=, nxt_tradable=, limit=)` 시그너처 호출
- 인자 정합 (params 영역 추출)
- ticker 6자리 + ETF 키워드 제외 (사이클 89 답습 + ETF_KEYWORDS 영속)

**H-3**: funnel 카운터 영속 (사이클 21 답습)
- `_scan_stats["universe_candidates"] == len(rows)` 영속
- `_scan_stats["universe_filtered"] == len(filtered)` 영속
- `_scan_stats["last_run_at"]` ISO 8601 KST 영속

**H-4**: graceful 영역 (raise 시 빈 list)
- `list_by_filter()` Exception raise → 빈 list `[]` 반환
- `_scan_stats["universe_candidates"] = 0` 동행
- `_scan_stats["universe_filtered"] = 0` 동행
- WARNING 로그 emit (사이클 89 답습)

### MEDIUM (2)

**M-1**: 멀티데이 보유 영역 보호 영속 (사이클 32 R4)
- 보유 종목 (`Position._MULTIDAY_STRATEGIES` 영속) = scanner 영역 무관
- 매도/익일청산 hot path = scanner 영역 무관 (사이클 38 명문화)
- `_scan_universe()` 시정 영역 한정 = 매매 안전성 영역 무영향

**M-2**: KIS API 호출 직접 사용 0건 영구 영속 (운영 효과)
- `fetch_stock_detail` 호출 0건 (사이클 108 답습)
- `kis_get_quote` / `kis_post_quote` 직접 호출 0건
- KIS LMS chain 안전 영역 영구 영속 (사이클 17 OPSP0002 영속)

### LOW (AST, 1)

**G-AST1**: `_scan_universe()` 본체 영역 정적 검증
- `fetch_stock_detail` import 영역 0건
- `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS` import 영역 0건 (xfail 의미 전환)
- `list_by_filter` import 영역 1건+
- 사이클 108 답습 패턴 영구 영속

## xfail 의미 전환 (사이클 66 K-2 패턴 답습)

기존 KOSPI200+KOSDAQ150 고정 유니버스 영역 테스트는 사이클 119 시정 영역 폐기 계약으로 의미 전환. `@pytest.mark.xfail(strict=False, reason="cycle 119: KOSPI200+KOSDAQ150 고정 유니버스 폐기, stock_master DB 베이스 전환")` 마킹으로 영구 보존 (호환).

## 운영 효과 예상 (push + EC2 자동 배포 후)

- KIS API 호출 100% 절감 (350 호출/일 → 0 호출/일)
- stock_master ~2,800 종목 영역 활용 (사이클 108 답습)
- 신호 빈도 ±10% 이내 (domain-expert 자문 A3)
- donchian 멀티데이 보유 영역 영구 영속 보호 (사이클 32 R4 + 익일 청산 안전망)
- 사이클 121+ DEFAULT 임계 점진 복원 권고 (D+3 / D+7 / D+14)

## 매매 안전성 무영향 확정

scanner 단계 매수 진입 전 후보 풀 구성 영역 한정 (사이클 38 명문화 영속) + 매도/익일청산/15:20 강제청산/손절 hot path 영역 영구 영속 무관 + 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호).
