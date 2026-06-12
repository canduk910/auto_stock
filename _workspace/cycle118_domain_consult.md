# 사이클 118 domain-expert 자문 메모 — Plan Phase B (donchian/VCP)

## 자문 요청 컨텍스트

team-leader 가 Plan Phase B (donchian/VCP stock_master 베이스 전환) 발주 후 Phase 1 진단 결과 **결정적 운영 영역 발견**: `acml_tr_pbmn_present 77/2,697 = 2.85%` — 사이클 107 raw 보강이 운영 stock_master 영역에 거의 미적용. 사이클 108 답습 (거래대금 필터 적용) 시 신호 빈도 -90~95% 폭축 위험.

## 도메인 자문 필수 영역

### A1: 멀티데이 보유 영역 영구 영속이 위험 평가

**현황**:
- donchian/VCP = `Position._MULTIDAY_STRATEGIES` 영구 영속 = `is_next_day=False` 영구 영속
- `_check_force_clear()` = `return []` (15:20 강제 청산 없음 영구 영속)
- 사이클 49 VCP Pullback 시정 영속 = 4중 청산 (손절 -7% / 베이스 하단 / ATR 트레일링 / 50일 EMA)
- 도치안 `_swing_rest_poll_loop` 60s 영역 영구 영속 (사이클 49 영속)

**자문 의제**:
1. **A1-1**: stock_master TTL skip (24h) + KRX 1차 가용 영역 영구 영속이 = 멀티데이 보유 종목이 `_scan_universe()` 영역에서 사라지는 영역 영구 영속이 위험. 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호) 영역과 어떻게 통합 보장?
2. **A1-2**: 사이클 49 영속이 `_scan_universe()` 시정만으로 영향 받지 않는가? (`prepare()` candle fetch 영역 + `recompute_held_atr()` 영역은 무변경)
3. **A1-3**: `_swing_rest_poll_loop` 영역 영구 영속이 60s REST 폴링이 stock_master 영역 의존성 0 영구 영속 확인 의무.

### A2: 신호 빈도 -90~95% 감소 영향 평가

**현황** (운영 실측 영구 영속):
- donchian DEFAULT (시총 3,000억 + 거래대금 50억) = **28 종목** (vs 현재 ~150 종목 영구 영속이 예상)
- VCP DEFAULT (시총 1,000억 + 거래대금 30억) = **35 종목** (vs 현재 ~250 종목 영구 영속이 예상)

**자문 의제**:
1. **A2-1**: 도치안 추세추종 스윙 영역 영구 영속이 = 후보 28 종목 영역 영구 영속이 매매 빈도 + 분산도 충분한가? (사이클 49 이전 영역 = ~150 종목)
2. **A2-2**: VCP 미네르비니식 베이스 검출 영역 영구 영속이 = 후보 35 종목 영역 영구 영속이 베이스 검출 비율 + 매매 빈도 충분한가? (사이클 49 이전 영역 = ~250 종목)
3. **A2-3**: 임시 완화 (거래대금 50억 → 10억 / 30억 → 5억) 시 운영 영구 영속이 안전한가? (`acml_tr_pbmn_present 2.85%` 영역 영구 영속이 점진 증가 대기)

### A3: nxt_tradable 영역 영구 영속이 결정

**자문 의제**:
1. **A3-1**: donchian/VCP MAIN 단독 영역 영구 영속이 = NXT 의존성 0 → `nxt_tradable=None` (전체) 영역이 정합 영역 영구 영속이 확인.
2. **A3-2**: 사이클 108 VB/LTV/BFB 답습 시 `nxt_tradable=True` 영역 영구 영속이 = 65/2697 폭축 영역 영구 영속이 위험. 도치안/VCP 는 `nxt_tradable=None` 가 안전.

### A4: 시정 영역 통합 vs 분리

**자문 의제**:
1. **A4-1**: 통합 단일 사이클 (donchian + VCP 동시) vs 분리 사이클 (사이클 118 donchian / 119 VCP) — 회귀 위험 vs 검증 효율성 trade-off.
2. **A4-2**: 사이클 108 답습 패턴 (통합) = HIGH 위험 영역 영구 영속이 시정 빈도 단축. 사이클 118 = MEDIUM 위험 (신호 빈도 영향).

### A5: 사이클 38 명문화 영속 확인 의무

- scanner 단계 = 매수 진입 전 후보 풀 영역 한정 영구 영속 확인.
- 매도/익일청산 hot path 무관 영구 영속 확인 (도치안/VCP 멀티데이 영역 + 사이클 49 4중 청산).
- 사이클 32 R4 universe guard 영속이 보유/익일청산 절대 보호 영역 영구 영속이.

### A6: 사이클 108 패턴 답습 영구 영속

- `list_by_filter()` 영역 영구 영속이 활용 (사이클 108 신규 메서드)
- 4 필터 (`min_market_cap` + `min_trade_amount` + `exclude_tickers` + `nxt_tradable`)
- ETF 키워드 제외 영역 영구 영속 (사이클 89 답습)
- 6자리 ticker 영속 (사이클 89 답습)
- funnel 카운터 영속 (`universe_candidates` + `universe_filtered` + `last_run_at`)
- graceful 영역 (`list_by_filter()` raise 시 빈 list 반환)

## team-leader 권장 영역 (자문 의무 검토)

- **Q1=A** (통합 단일 사이클, 사이클 108 답습 패턴)
- **Q2=D** (임시 완화 50억 → 10억 / 30억 → 5억) — `acml_tr_pbmn_present 2.85%` 영역 영구 영속이 점진 증가 대기 + 신호 빈도 보존
- **Q3=B** (별개 사이클, 사이클 119+) — ETF 키워드 제외 영역 영구 영속이 이미 영속
- **Q4=C** (Q2=D 결합) — 점진 증가 대기 + 1주 운영 측정 의무
- **Q5=A** (`nxt_tradable=None` 전체) — donchian/VCP MAIN 단독 영역 영구 영속이
- **Q6=B** (domain-expert 자문 의무) — 멀티데이 보유 영역 + 사이클 49 영속 영향 평가

## 자문 결과 영구 영속 영역 (사용자 결정 후 갱신 의무)

[자문 완료 후 갱신]

## 영속 의무 매트릭스 영구 영속

전수 영속 — 사이클 17/29/32/38/49/65/78/79/81/88/89/94/100/107/108/110/112/115/116/117 + CLAUDE.md "절대 깨지 말 것" 8 영역.
