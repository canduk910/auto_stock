# 사이클 65 거래대금 동행 필터 — 도메인 전문가 자문 의뢰서 (sketch)

> **작성**: team-leader (2026-06-06 KST)
> **수신**: domain-expert (데이/스윙 트레이더 출신)
> **사이클 컨텍스트**: 사이클 64 가격 필터 위치 변경 (risk → scanner) + 단순화 (3 모드 폐기) 직후, 자문 응답 §Q7-5 (HIGH) 발의로 **즉시 발주 확정**. 사이클 64 가격 필터의 *갭상승 회피 효과 영구 폐기* 위험 (전일종가 단독 → 신규 상장 동전주 graceful 통과) 을 *결을 다른 차원에서 보강* 의무.
> **사이클 64 인계**: 갭상승 회피 = *작전주/동전주* 차단 *유일 메커니즘 폐기* → 거래대금 필터 (1억/5억/10억 임계) 가 *유일 차단 메커니즘* 으로 격상
> **선행 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` v2 §15
> **선행 자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md` §Q7-5
> **위험 등급**: **HIGH** (작전주 차단 *유일 메커니즘* + 사이클 64 위치 변경 직후 즉시 보강 의무)

---

## 0. 사용자 사전 결정 (자문 *전* 확정)

| 항목 | 사용자 결정 | 자문 대상 여부 |
|---|---|---|
| **사이클 65 즉시 발주** | 사이클 64 종료 직후 (1주 운영 데이터 대기 미수행) | 확정 |
| **위치** | 사이클 64 가격 필터와 동일 = scanner 단계 = `subscribe_filtered_stocks` 진입 직후 단일 hook | 확정 |
| **보유/익일청산 절대 보호** | 사이클 64 옵션 D 3 중 안전망 답습 (`_collect_protected_tickers_for_scanner` 재사용) | 확정 |
| **데이터 소스** | `stock_master.raw.acml_tr_pbmn` 또는 등락률 순위 API 응답 `acml_tr_pbmn` | 자문 대상 (Q2) |
| **DB 키** | `trade_amount_filter_min` 단일 (max 없음 — 거래대금 미만 차단만) | 확정 (단순화 의도) |

자문 대상은 **임계값 권고 + 데이터 소스 정확성 + 사이클 64 시너지 검증**.

---

## 1. 자문 의제 (Q1~Q5 + 자유 발의)

### Q1 — 거래대금 임계 권고 (HIGH)

**컨텍스트**:
- 사이클 64 가격 필터 위치 변경 후 *갭상승 회피 효과 영구 폐기* → 거래대금 필터 = 작전주 차단 *유일 메커니즘*
- 통상 작전주 식별 임계 (트레이더 본능):
  - 거래대금 1억 미만 = 명백한 동전주/작전주 (사이클 64 graceful 통과 위험 1순위)
  - 거래대금 5억 미만 = 의심 영역 (정상 우량주는 보통 50억+)
  - 거래대금 10억 미만 = 보수 컷오프 (호가창 5호가 깊이 부족)
- 현재 momentum 전략 `MIN_TRADE_AMOUNT = 20_000_000_000` (200억) = scan_stocks 단독 임계, *전 전략 공통* 미적용

**자문 질문**:
1. system_config `trade_amount_filter_min` 디폴트 권고:
   - **옵션 A**: 0 (비활성, 운영자 명시 활성화 의무) — 사이클 64 디폴트 답습
   - **옵션 B**: 100_000_000 (1억) — 작전주 차단 최소 임계
   - **옵션 C**: 500_000_000 (5억) — 의심 영역 차단
   - **옵션 D**: 1_000_000_000 (10억) — 보수 차단
2. UI 슬라이더 권장값 + 범위:
   - 권장값: 1억 / 5억 / 10억 (3 단계 마커)
   - 범위: 0 ~ 100억 (단위 1억)
3. 사이클 64 가격 필터 임계 (5,000원 / 1,000,000원) 와 동시 활성화 시 후보 풀 축소 효과 정량 평가
4. 사이클 64 의 momentum 단독 `MIN_TRADE_AMOUNT = 20_000_000_000` (200억) 과 본 사이클 65 시스템 전역 임계 의 *역할 분리* 권고

**옵션**:
- **옵션 A (보수 권장)**: 디폴트 0 비활성 + 권장값 5억 툴팁 (사이클 64 답습)
- **옵션 B**: 디폴트 1억 (최소 작전주 차단)
- **옵션 C**: 디폴트 5억 + 활성화 (사이클 64 갭상승 폐기 위험 즉시 시정)

---

### Q2 — 데이터 소스 정확성 (MEDIUM)

**컨텍스트**:
- 사이클 64 답습: `stock_master.raw.prdy_clpr` (24h TTL 캐시) 단독 + 미확보 graceful 통과
- 거래대금 데이터:
  - **1순위 후보**: `stock_master.raw.acml_tr_pbmn` (CTPF1002R 응답 필드 — 미확인 시 KIS MCP 검증 의무)
  - **2순위 후보**: 등락률 순위 API 응답 `acml_tr_pbmn` (실시간 거래대금, scanner 진입 *전* fetch 결과)
  - **3순위 후보**: KIS `inquire-price` (`FHKST01010100`) — 사이클 64 Q2 와 동일 Rate Limit 부담

**자문 질문**:
1. 거래대금 데이터 정확성 평가:
   - **1순위 (stock_master.raw.acml_tr_pbmn)**: 24h TTL → 전일 거래대금 = 작전주 차단에 *충분* vs *부적합* (운영자 시각)
   - **2순위 (등락률 순위 API)**: 실시간 거래대금 = 정확성 1위지만 *momentum 전략 scan_stocks 의존* (다른 전략은 미사용)
   - **3순위 (KIS inquire-price)**: 사이클 64 Q2 답습 폐기 (Rate Limit)
2. *전일 거래대금* vs *실시간 거래대금* 의 작전주 차단 효과 차이:
   - 전일 거래대금: 작전 전일 5억 미만 → 당일 10억 폭발 = 차단 (의도 부합)
   - 실시간 거래대금: 당일 09:30 시점 1억 미만 = 차단 (즉시 반응)
3. KIS MCP 검증 의무 — `stock_master.raw.acml_tr_pbmn` 필드 존재 확인 + `acml_tr_pbmn` 단위 (원 vs 백만원 vs 억) 확정

**옵션**:
- **옵션 A**: stock_master 단독 (사이클 64 답습) — graceful 통과 미확보 시
- **옵션 B**: 등락률 순위 API 응답 우선 + stock_master fallback
- **옵션 C**: 둘 다 활용 (실시간 1순위 + stock_master 2순위 + 둘 다 미확보 graceful 통과)

---

### Q3 — 사이클 64 가격 필터와의 시너지 / 충돌 (MEDIUM)

**컨텍스트**:
- 사이클 64 가격 필터 = 가격 1차원 차단
- 사이클 65 거래대금 필터 = 가격 X 거래량 = 2차원 차단
- 두 필터 모두 활성화 시 후보 풀 과도 축소 위험

**자문 질문**:
1. 동시 활성화 시 후보 풀 축소 정량 평가 — 운영 데이터 1주 후 임계 미세 조정 권고
2. AND vs OR 결합:
   - **AND**: 가격 통과 + 거래대금 통과 → 후보 보존 (보수)
   - **OR**: 가격 차단 또는 거래대금 차단 → 후보 차단 (관용)
3. 사이클 64 의 `[price_filter_scanner_skip]` 와 사이클 65 의 `[trade_amount_filter_scanner_skip]` 로그 prefix 분리 (의무)
4. funnel step_no 분리:
   - 사이클 64 step_no=98 = 가격 필터
   - **사이클 65 step_no=97 = 거래대금 필터** (권고)

---

### Q4 — 진입점 + 헬퍼 재사용 (MEDIUM)

**컨텍스트**:
- 사이클 64 옵션 A: `subscribe_filtered_stocks` 진입 직후 단일 hook
- 사이클 64 옵션 D: `_collect_protected_tickers_for_scanner()` 공통 헬퍼

**자문 질문**:
1. 사이클 65 진입점 — 사이클 64 답습 의무:
   - 사이클 64 의 `_apply_price_filter` 호출 *직후* `_apply_trade_amount_filter` 호출 (분리된 두 hook)
   - 또는 통합 hook `_apply_scanner_filters(candidates, *, protected_tickers, filters=[...])` (확장성)
2. `_collect_protected_tickers_for_scanner()` 헬퍼 100% 재사용 — 새 헬퍼 추가 0
3. AST 가드 답습 (G-2 패턴) — `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 의무

---

### Q5 — 60s TTL 캐시 + invalidate 답습 (LOW)

**컨텍스트**:
- 사이클 64 의 60s TTL 캐시 + `invalidate_price_filter_cache_scanner()` 패턴 답습
- 본 사이클 65 도 동일 패턴 의무

**자문 질문**:
1. 사이클 64 캐시 구조 100% 답습 — 별도 변형 미권고 확인
2. Q7-1 (자동 unsubscribe 차단) 답습 의무 — `invalidate_trade_amount_filter_cache_scanner()` 도 unsubscribe 발화 0

---

### 자유 발의 (트레이더 시각)

**의제**: 본 카드 + 자문 의제 외에 트레이더 시각으로 발의할 안건이 있는가?

**예상 발의**:
- 거래대금 변동성 (당일 09:30 1억 → 11:00 50억 폭발) 처리
- 우선주 / ETF / ETN 의 거래대금 패턴 (정상이지만 작전주 임계 미만)
- 코스닥 vs 코스피 거래대금 차이 — 보드별 임계 분리 권고
- 사이클 64 + 65 연속 운영 후 *후보 풀 0건* 위험 (디폴트 0/0 + 디폴트 0 답습으로 회피)

---

## 2. 자문 응답 형식

응답 파일: `_workspace/cycle65_trade_amount_filter_domain_response.md`

각 Q1~Q5 응답에 다음 형식 의무 (사이클 64 답습):

```markdown
### Q1 — 거래대금 임계 권고

**옵션 채택**: A / B / C / D (또는 신규 옵션 E 발의)

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
| Q1 (거래대금 임계 권고) | **HIGH** | 작전주 차단 *유일 메커니즘* 정량 결정 |
| Q2 (데이터 소스 정확성) | **HIGH** | KIS 응답 필드 존재 + 단위 확인 의무 (KIS MCP 검증) |
| Q3 (사이클 64 시너지) | MEDIUM | 후보 풀 축소 정량 평가 |
| Q4 (진입점 + 헬퍼 재사용) | MEDIUM | 사이클 64 답습 의무 확정 |
| Q5 (60s TTL 캐시) | LOW | 사이클 64 답습 |

---

## 4. 사이클 64 vs 65 비교

| 항목 | 사이클 64 (가격 필터) | 사이클 65 (거래대금 필터) |
|---|---|---|
| 차원 | 1차원 (가격) | 2차원 (가격 X 거래량) |
| DB 키 | `price_filter_min` / `price_filter_max` (2 종) | `trade_amount_filter_min` (1 종, 단순화) |
| 위치 | scanner `subscribe_filtered_stocks` 진입 직후 | 사이클 64 hook *직후* (또는 통합 hook) |
| 헬퍼 | `_apply_price_filter` + `_collect_protected_tickers_for_scanner` | `_apply_trade_amount_filter` (헬퍼 재사용) |
| 데이터 소스 | `stock_master.raw.prdy_clpr` (단독) | `stock_master.raw.acml_tr_pbmn` (단독 or 등락률 순위 응답 — 자문 결정) |
| 미확보 처리 | graceful 통과 | graceful 통과 (사이클 64 답습) |
| 로그 prefix | `[price_filter_scanner_skip]` | `[trade_amount_filter_scanner_skip]` |
| funnel step_no | 98 | **97** (권고) |
| 60s TTL 캐시 | ✅ | ✅ (답습) |
| Q7-1 unsubscribe 미발화 | ✅ | ✅ (답습) |
| AST 가드 | G-1 risk.py 잔존 0 + G-2 keyword 의무 | G-2 답습 (`_apply_trade_amount_filter` keyword 의무) |
| UI 카드 | `PriceFilterCard` | `TradeAmountFilterCard` (신규) |
| 위험 등급 | MEDIUM (HIGH 0 잔존) | **HIGH** (작전주 차단 유일 메커니즘) |
| 회귀 가드 추정 | 30 케이스 | **~20 케이스** (mode 없음 + max 없음 단순화) |

---

## 5. 회귀 가드 추정 (사이클 64 답습 — ~20 케이스)

| 카테고리 | 사이클 65 케이스 | 비고 |
|---|---|---|
| A `system_config` (`trade_amount_filter_min` 1 키) | 3 | get/set/범위 검증 |
| B scanner `_apply_trade_amount_filter` | 4 | 비활성 / 미만 차단 / 미확보 graceful / 임계 통과 |
| C 보유/익일청산 절대 보호 (HIGH) | 2 | 헬퍼 재사용 — `_collect_protected_tickers_for_scanner` 답습 |
| D 60s TTL 캐시 + Q7-1 답습 | 2 | invalidate + unsubscribe 미발화 |
| E DailyEmitCap | 2 | 1회/ticker/일 + reset |
| F integration (E2E) | 3 | scan → 필터 → subscribe + 보유 보호 검증 + funnel hook |
| G AST 가드 (HIGH) | 1 | `_apply_trade_amount_filter` keyword 의무 |
| H scanner daily_summary | 1 | 일일 집계 |
| C-Route API | 1 | PUT 검증 |
| F-FE 프론트 | 3 | TradeAmountFilterCard 초기/슬라이더/저장 |
| **합계** | **~22** | HIGH 3 / MEDIUM 5 / LOW 14 |

---

## 6. 자문 후 단계

1. domain-expert 응답 수신 → `_workspace/cycle65_trade_amount_filter_domain_response.md`
2. team-leader 채택 + 설계 카드 v2 작성 (`_workspace/cycle65_trade_amount_filter_design_card.md`)
3. 사용자 결정 (옵션 A 자문 결과 전부 적용 권장 — 사이클 60~64 패턴 답습)
4. tdd-engineer Red 발주
5. backend-dev + frontend-dev 동시 Green 발주
6. tester Verify
7. sync-docs
8. 사용자 명시 commit + push

---

## 7. 안전 가드

- 본 sketch 작성은 운영 영향 0 (문서 산출물만)
- 사이클 65 실제 발주는 **사이클 64 완료 직후 + 사용자 명시 지시 후** 진행
- HIGH 등급 (작전주 차단 유일 메커니즘) → tester verify 의무 강화
- 사이클 64 답습 패턴 최대 재사용 → 신규 코드 최소화 + 회귀 가드 비용 축소
- KIS MCP 검증 의무 (Q2) — `stock_master.raw.acml_tr_pbmn` 필드 존재 + 단위 확인 *전* Green 발주 금지

---

## 8. KIS MCP 검증 의무 (Q2 사전 작업) — **team-leader 사전 수행 결과 (2026-06-06)**

자문 발주 *직전* KIS MCP 호출 결과:
- ✅ `mcp__kis-code-assistant__search_domestic_stock_api(query="주식기본조회")` — `search_stock_info` (CTPF1002R) 단건 검색 결과 확인
- ✅ `mcp__kis-code-assistant__read_source_code` — `search_stock_info.py` 소스 검증:
  - CTPF1002R 의 응답 `output` 은 **dict (single-item)** — 종목 메타 필드 위주
  - **시세 필드 (`acml_tr_pbmn` / `prdy_clpr` 등) 의 출력 여부 코드만으로는 확정 불가**
  - 본문 명세에 응답 필드 명세 부재 (`stocks_info` 파이썬 정제코드 별도 참조 권고만)
- ✅ 로컬 검증:
  - `docs/kis/domestic-stock-industry.md` 의 `acml_tr_pbmn` 예시 50건 → **숫자 단위 = 원 (₩)** 확정 (예: 130953 = 약 13만원이 아니라 시계열 미세 값 — KIS 등락률 순위 응답과 단위 동일성 검증 필요)
  - `src/engine/scanner.py:414` (`MIN_TRADE_AMOUNT = 20_000_000_000`) = 등락률 순위 응답 `acml_tr_pbmn` 200억 컷오프 → **단위 = 원 (₩) 확정**
  - `src/engine/strategies/donchian_swing.py:410` 주석: "`acml_tr_pbmn`(당일 누적 거래대금)이 장 시작 전 0이라" → **장중 누적값 = 원 단위 확정**
- ⚠️ **CTPF1002R 응답의 `acml_tr_pbmn` 필드 존재 확정 불가** — `inquire_price` (FHKST01010100) 또는 등락률 순위 API 응답에서만 검증됨
  - **자문 Q2 의 데이터 소스 결정 = HIGH 의제 격상 의무**
  - graceful 통과 (미확보 시) 가 운영 안전 보장 → 임계 미설정 시 사이클 65 = no-op 보장

### 검증 결과 자문 인계 사항

| 항목 | 발견 | 자문 인계 |
|---|---|---|
| CTPF1002R `acml_tr_pbmn` | 코드만으로는 미확정 | Q2 옵션 A 채택 시 graceful 통과 운영 안전 + 임계 미설정 시 no-op 확정 |
| 등락률 순위 API `acml_tr_pbmn` | **원 (₩) 단위 확정** | Q2 옵션 B 채택 시 momentum scan_stocks 응답 캐시 도입 필요 (별도 모듈 신규) |
| `inquire_price` FHKST01010100 | 단건 조회 — Rate Limit 부담 | Q2 옵션 C 비채택 (사이클 64 Q2 답습 — Rate Limit 회피) |
| 사이클 64 `prdy_clpr` | 동일 의문 — graceful 통과로 운영 안전 처리 | 사이클 64 답습 = 운영 안전 보장 검증됨 |

---

## 9. 사이클 65 발주 시점 결정 의무

| 옵션 | 시점 | 사유 |
|---|---|---|
| **옵션 A (권장)** | 사이클 64 종료 직후 즉시 | 갭상승 회피 효과 폐기 즉시 시정 (자문 §Q7-5 권고) |
| 옵션 B | 사이클 64 운영 1주 후 | 운영 데이터 축적 후 임계 미세 조정 (자문 §Q5 권고) |
| 옵션 C | 사이클 67+ | 사이클 64 의 후속 카드 #13 시점 (refactor-review 카드 인계) |

→ **사용자 결정 = 옵션 A** (사이클 65 즉시 발주 확정)

---

## 10. 후속 사이클 (사이클 65 이후)

- 사이클 66+ = stale_manager.py 1,076L sub-module 분해 (refactor-review 카드 #14)
- 사이클 67+ = 사이클 62 + 64 + 65 통합 운영 데이터 회고 + 임계 미세 조정
- 사이클 68+ = Q7-2 (액면분할 invalidate, 카드 #15)
