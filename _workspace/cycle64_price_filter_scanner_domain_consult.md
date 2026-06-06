# 사이클 64 가격 필터 위치 변경 + 단순화 — 도메인 전문가 자문 의뢰서

> **작성**: team-leader (2026-06-06 KST)
> **수신**: domain-expert (데이/스윙 트레이더 출신)
> **사이클 컨텍스트**: 사이클 62 가격 필터 (risk.on_tick 매수 진입 전용 3 모드) 운영 후, 사용자가 사이클 64 = **위치 변경 (risk → scanner) + 단순화 (3 모드 폐기)** 를 명시 지시.
> **선행 설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md`
> **선행 자문 (사이클 62)**: `_workspace/cycle62_price_filter_domain_response.md`
> **위험 등급**: MEDIUM (scanner 차단 + 보유/익일청산 절대 보호 의무 + 신규 상장 처리)

---

## 0. 사용자 결정 사항 (자문 *전* 확정 — 재논의 대상 아님)

| 항목 | 사용자 결정 | 자문 대상 여부 |
|---|---|---|
| **위치 변경** | `risk.on_tick` 제거 → scanner 단계 (WS 구독 *전*) | 확정 (자문 대상 아님) |
| **3 모드 제거** | HARD/WARN/OFF 모두 폐기. 단순 임계 필터링만 | 확정 (자문 대상 아님) |
| **비교 가격** | 전일종가 단독 (`stock_master.raw.prdy_clpr` or KIS pre-fetch) | 자문 대상 (graceful 처리 방식만) |
| **로그 prefix** | `[price_filter_scanner_skip]` 신규 + DailyEmitCap 1회/ticker/일 | 확정 |
| **사이클 분할** | 백엔드 + 프론트 단일 사이클 | 확정 |

자문 대상은 **확정 결정의 안전성 검증 + 미확정 영역의 트레이더 시각 권고**.

---

## 1. 자문 의제 (Q1~Q6 + 자유 발의)

### Q1 — 보유/익일청산 절대 보호 안전 가드 (HIGH 영역)

**컨텍스트**:
- scanner 가격 필터가 임계 외 종목을 후보 풀에서 제거할 때, **보유 종목** (`registry.all().positions`) + **익일청산 대기 종목** (`scheduler._pending_next_day_clear`) 은 절대 제외 안 됨
- 사이클 32 R4 `_evaluate_universe_guard` (stale + low_volume → universe 제외) 패턴 답습
- 매도/익일청산/손절/Trailing/15:20 강제청산 영향 0 보장 의무 (사이클 38 명문화)

**자문 질문**:
1. scanner 차단이 매도/익일청산/손절에 미치는 잠재 영향 평가 — 사이클 32 R4 universe guard 패턴 답습이 충분한가?
2. 보유 종목 가격이 임계 외로 변동한 race 시나리오 — 매도 발화 정확성 보장 가능한가? (예: 보유 종목이 작전주 급락으로 5,000원 미만 진입 → scanner 가 unsubscribe 시도 → WS 시세 끊김 → 손절 발화 실패 위험)
3. `_pending_next_day_clear` 종목 절대 보호 의무 — `subscribe_filtered_stocks` 의 `priority_groups` HIGH 분기와 정합성 검증
4. 어떤 추가 안전 가드가 필요한가? (예: 보유 종목은 scanner 필터 *제외 안 됨* + WS 구독 *대상 유지* 이중 가드)

**옵션**:
- **옵션 A** (보수 권장): 사이클 32 R4 패턴 100% 답습 — `protected_tickers = positions ∪ _pending_next_day_clear` 합집합 필터링 우회. 추가 가드 0
- **옵션 B**: 옵션 A + WS 구독 슬롯 영역에서도 HIGH 보장 검증 (이중 안전망)
- **옵션 C**: 옵션 A + 보유 종목 가격 변동 시 알람 (`[price_filter_protected_drift]` WARNING) 추가

---

### Q2 — `prdy_clpr` 미확보 처리 (MEDIUM)

**컨텍스트**:
- scanner = WS 구독 *전* → `current_price` 미확보 (실시간 시세 fallback 불가)
- 사용자 결정: 전일종가 단독
- 1순위: `stock_master.get(ticker).raw.get("prdy_clpr")` (24h TTL 캐시)
- 2순위: KIS `inquire-price` (`FHKST01010100`) 사전 fetch + stock_master upsert
- 두 경로 모두 미확보 시 처리 방침 자문 필요

**자문 질문**:
1. `prdy_clpr` 미확보 (신규 상장 1일차 / KIS API 일시 장애 / stock_master 캐시 miss + 사전 fetch 실패) 시 처리 방침:
   - **옵션 A** (보수적 = 매수 허용): graceful 통과 (필터 skip + 후보 보존) — 사이클 62 Q2 답습
   - **옵션 B** (보수적 = 매수 차단): 후보 풀에서 제외 + `[price_filter_scanner_skip_no_prev_close]` 별도 로그 prefix
   - **옵션 C**: 신규 상장만 옵션 A (graceful 통과), KIS 일시 장애는 옵션 B (차단)
2. KIS `inquire-price` 사전 fetch 의 Rate Limit 영향 평가 (20 req/s 한도) — momentum 30종목 / VB 40종목 / BFB+VCP 40+종목 = 최대 100~150 호출 / 5분 사이클 → 분당 20~30 호출 영향
3. `stock_master.raw.prdy_clpr` 필드 존재 확인 의무 — KIS `CTPF1002R` 응답 스키마 검증 필요 (`docs/kis/` 캐시 또는 KIS MCP 조회)

**권고 영역**:
- 옵션 A 선택 시 → 신규 상장 종목이 작전주 가능성 (저가주) 인지 트레이더 시각 평가
- 옵션 B 선택 시 → 신규 상장 호재 종목 매수 기회 손실 위험

---

### Q3 — 신규 상장 영향 (MEDIUM)

**컨텍스트**:
- 신규 상장 1일차 종목은 `prdy_clpr=0` (전일 거래 없음) — KIS 응답 자체에 NULL 또는 0
- 신규 상장 종목 = 작전주 / IPO 호재 / 동전주 모두 혼재 — 트레이더 시각 판단 필요
- 자동매매 시스템에서 신규 상장 종목의 매매 비중 평가 필요

**자문 질문**:
1. 신규 상장 종목 (`prdy_clpr=0`) 의 일반 자동매매 기대 효과 / 위험:
   - 모멘텀 전략 측면 (상장일 +30% 가능성)
   - VB/LTV 측면 (전일 range 미확보 → K값 계산 불가)
   - BFB/VCP 측면 (베이스 미형성 → 필터 통과 거의 불가)
   - donchian 측면 (60일 EMA 미확보 → prepare() 자체 skip)
2. 시스템 측 명세 (`_workspace/00_leader_trading_rules.md`) 에 신규 상장 처리 규칙 명시 필요 여부
3. 가격 필터의 신규 상장 처리 (Q2) 결정과 시스템 전반 정합성

**옵션**:
- **옵션 A**: 신규 상장 종목 자체를 모든 전략에서 사전 제외 (보수적)
- **옵션 B**: 신규 상장 종목 graceful 통과 + 전략별 자연 필터에 위임 (관용적)
- **옵션 C**: 신규 상장 종목 별도 화이트리스트 (운영자 명시 등록)

---

### Q4 — scanner 진입점 정확성 (전 전략 공통 의무) (HIGH 영역)

**컨텍스트**:
- 사용자 의도: scanner 단계 = WS 구독 *전* = 모든 전략 공통
- 현재 6 전략 진입점:
  - MomentumStrategy: `scan_stocks()` (scanner.py L149)
  - VolatilityBreakout: `prepare()` (volatility_breakout.py L93) → `_collect_breakout_tickers`
  - LongTailVolatility: `prepare()` (long_tail_volatility.py L101)
  - BullFlagBreakout: `prepare()` (bull_flag_breakout.py L136)
  - VCPBreakout: `prepare()` (vcp_breakout.py L152)
  - DonchianSwing: `prepare()` (donchian_swing.py L102) — KOSPI200/KOSDAQ150 고정 유니버스
- **단일 진입점 vs 전 전략 분산 진입** 결정 필요

**자문 질문**:
1. scanner 필터 진입점 후보:
   - **옵션 A** (단일 진입점): `subscribe_filtered_stocks` *전* 단일 hook (scheduler `_scan_loop` 또는 `_collect_*` 직후) — 단일 진실 원천, 코드 변경 최소, 누락 위험 0
   - **옵션 B** (전 전략 분산): 6 전략 각 `prepare()` 끝에서 개별 hook — 전략별 커스터마이징 가능, 단 누락 위험 + 중복 코드
   - **옵션 C**: 옵션 A + 단일 헬퍼 `_apply_price_filter(candidates, *, protected_tickers)` 6 전략 공통 호출
2. donchian_swing 의 KOSPI200/KOSDAQ150 고정 유니버스 (대형주) 에도 가격 필터 적용해야 하는가? — 우량주는 사실상 필터 무영향이지만 일관성 vs 예외 처리
3. 진입점 누락 위험 차단 AST 정적 가드 가능성 — 모든 `subscribe_filtered_stocks` 호출 전 `_apply_price_filter` 호출 검증

**권고 영역**: 옵션 A + C 조합 (단일 진입점 + 헬퍼 함수) — 사이클 38 명문화 답습 (`tradable_boards` 단일 진실 원천 패턴)

---

### Q5 — WS 구독 슬롯 영향 (MEDIUM)

**컨텍스트**:
- MAX 41 슬롯 (KIS 공식 한도)
- 사이클 17~25 우선순위 분리 + 사이클 32 R4 universe guard 로 슬롯 보호 영속 운영
- 가격 필터 scanner 단계 차단 → 후보 풀 축소 → 슬롯 절약 효과
- HIGH (보유/익일청산) 보장 영속 의무

**자문 질문**:
1. 후보 풀 축소가 매매 기회에 미치는 영향 평가 — 운영 통계 (1주 운영 후) 기반 임계값 권고
2. 슬롯 절약 효과의 정량적 기대치 — 예: 디폴트 0/0 비활성 → 운영자 5,000/1,000,000 활성화 시 후보 30~40% 축소 가능?
3. HIGH 종목 우선순위 시스템과의 정합성 — 보유 절대 보호 + LOW 후보 우선순위 영향
4. donchian_swing 보유 종목의 시세 보장 (사이클 12 BREAKOUT_LOW_CAP=25 슬롯 보호) — 가격 필터 활성화 시에도 영속?

**권고 영역**:
- 디폴트 0/0 (비활성) 보존 → 운영자 명시 활성화 후 1주 운영 통계로 임계값 미세 조정

---

### Q6 — 사이클 62 회귀 가드 폐기 범위 (MEDIUM)

**컨텍스트**:
- 사이클 62 회귀 가드 38 케이스 → 사이클 64 위치 변경으로 일부 폐기 / 갱신 / 유지 필요
- 폐기 대상:
  - B 4 (risk.on_tick 영역) → 폐기
  - D 2 (60s 캐시 — risk 영역) → 폐기 (scanner 영역 신규로 대체)
  - E 4 (매도 영향 0) → **영역 변경 후 재검증 (scanner 영역에서도 동일)** + E-4 AST 가드 유지 (영역만 risk → scanner)
  - F 5 (Q2 fallback — current_price fallback) → 폐기 (prdy_clpr 단독 신규)
  - G 2 (WARN 모드) → 폐기 (모드 자체 제거)
  - H 1 (일일 집계) → **폐기 또는 scanner 영역 이전 (자문 결정)**
- 폐기 합계: ~18 케이스 / 갱신 합계: ~8 케이스 / 유지: ~12 케이스

**자문 질문**:
1. 사이클 62 일일 집계 (`[price_filter_daily_summary]` `_settle()` 직전) 의 운영 가치 평가:
   - **옵션 A** (폐기): 단순화 우선 — 디폴트 0/0 비활성이면 집계 무의미
   - **옵션 B** (scanner 영역 이전): 일일 차단 카운트 + reason 분포는 운영 가시화 가치 있음 → `[price_filter_scanner_daily_summary]` 신규 prefix
   - **옵션 C** (옵션 B + funnel snapshot 통합): `strategy_funnel_snapshots` 의 step_no 단계 추가 — 단, 사이클 34/41 funnel 영역과 충돌 위험
2. 사이클 62 E 카테고리 (매도 영향 0) 재검증 의무 — scanner 영역에서도 동일 회귀 가드 4 케이스 신규 작성 필요한가? (옵션 A 답습 권고 vs 옵션 B 영역 변경으로 자연 무영향 처리)
3. AST 정적 가드 (사이클 62 E-4 + 사이클 64 G-1) 통합 가능성

---

### 자유 발의 (트레이더 시각)

**의제**: 본 카드 + 자문 의제 외에 트레이더 시각으로 발의할 안건이 있는가?

**예상 발의**:
- 가격 필터 + 거래대금 동행 필터 (사이클 63 카드 #13) 시너지 / 충돌 평가
- VCP / BFB 매매 기회와 가격 필터 활성화 임계 권고 (사이클 49 VCP 30일 0건 매매 사고 답습)
- KIS 매크로 레짐 (`buy_block_mode`) 과 가격 필터 동시 활성화 시 매수 차단 누적 효과
- 모멘텀 전략의 신규 상장 종목 매매 기회 평가 (Q3 연관)

---

## 2. 자문 응답 형식

응답 파일: `_workspace/cycle64_price_filter_scanner_domain_response.md`

각 Q1~Q6 응답에 다음 형식 의무:

```markdown
### Q1 — 보유/익일청산 절대 보호 안전 가드

**옵션 채택**: A / B / C (또는 신규 옵션 D 발의)

**근거** (트레이더 시각):
- ...

**행위 영향 평가**:
- 매매 안전성: ...
- 매수 기회: ...
- 운영자 UX: ...

**추가 권고**:
- ...
```

---

## 3. 자문 우선순위

| 의제 | 우선순위 | 사유 |
|---|---|---|
| Q1 (보유/익일청산 절대 보호) | **HIGH** | 매매 안전성 직접 영역 |
| Q4 (scanner 진입점 정확성) | **HIGH** | 누락 위험 + 전 전략 공통 의무 |
| Q2 (prdy_clpr 미확보 처리) | MEDIUM | graceful vs 보수적 trade-off |
| Q3 (신규 상장 영향) | MEDIUM | 시스템 명세 정합성 |
| Q5 (WS 구독 슬롯 영향) | MEDIUM | 슬롯 절약 효과 기대치 |
| Q6 (사이클 62 회귀 가드 폐기 범위) | MEDIUM | 회귀 위험 관리 |

---

## 4. 자문 후 단계

1. domain-expert 응답 수신 → `_workspace/cycle64_price_filter_scanner_domain_response.md`
2. team-leader 채택 + 설계 카드 v2 갱신 (`_workspace/cycle64_price_filter_scanner_design_card.md`)
3. 사용자 결정 (옵션 A 자문 결과 전부 적용 권장 — 사이클 60~63 패턴 답습)
4. tdd-engineer Red 발주

---

## 5. 안전 가드

- 본 자문 의뢰서 작성은 운영 영향 0 (문서 산출물만)
- 자문 응답은 사용자 결정 사항 (위치 변경 + 모드 제거) 을 *재논의하지 않음* — 그 결정의 안전성 검증 + 미확정 영역 권고만
- HIGH 영역 (Q1 / Q4) 은 옵션 채택 외 추가 위험 평가 의무
