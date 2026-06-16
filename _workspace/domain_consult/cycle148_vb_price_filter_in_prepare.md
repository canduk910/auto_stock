# 사이클 148 도메인 자문 — VB prepare() 가격 max 필터 추가

작성일: 2026-06-16
의제: VB prepare() 영역 가격 max 필터 추가 (5건 의제)
사용자 결정: Q1=B (VB 단독) + Q2=C (PriceFilter 단일 source) + Q3=A (scanner 유지) + Q4=B (MEDIUM)
영속 의무: feedback_no_redundant_phrases.md 준수 (반복 문구 금지)

---

## 의제 1 — VB prepare() 가격 필터 추가 적정성

**자문 결론: 채택 (3 안 중 1순위)**

### 3 안 정렬
- **안 A (채택)**: VB `_scan_universe()` 영역에서 `list_by_filter()` 결과에 Python-side PriceFilter 후처리 추가. scanner `_apply_price_filter`는 이중 안전망으로 유지.
- 안 B: scanner 단계만 유지하고 prepare() 단계는 가격 미적용. funnel snapshot에 차단 종목 노출 결함 영속.
- 안 C: scanner 단계 가격 필터를 prepare() 단계로 이전. 사이클 64 명문화 폐기 위험.

### 채택 사유
- 사이클 64 명문화 = "scanner 단계 매수 진입 *전* 종목 풀 차단" → 매수 진입 전 영역에서 일관 적용 의무.
- prepare()는 매수 진입 전 단계 (시총/거래대금 필터와 동일 영역) → 가격 필터 같은 위치 적용이 자연스러운 정합성.
- 운영 실증 6 종목 (298040/000660/009150/402340/011070/012450) bfdy_clpr > 500,000원 차단 = funnel snapshot에 31 종목 노출 + scanner 25 통과 + UI 6 차단 종목 표시 결함 → prepare 단계 차단 시 처음부터 25 종목만 노출 → 운영자 인지 일치.

### 반례
- KIS volume-rank API 사용 시점이면 `stck_prpr` 직접 사용 가능했으나, 사이클 108 list_by_filter 전환 후 가격 데이터는 `raw.bfdy_clpr` 한정. raw miss 시 graceful 통과 → 운영 안전.
- 가격 max 임계 변경 시 prepare() 1일 1회 갱신 + scanner 60s TTL 캐시 = 운영 PUT 즉시 반영은 scanner 영역만 (당일 prepare는 다음 영업일 반영). 사용자 PUT 직후 적용 의무가 강하지 않다면 수용 가능.

### CLAUDE.md 안전 규칙 정합
- 사이클 38 명문화 영속 — prepare()는 매수 진입 전 영역, 매도/익일청산/15:20 강제청산 hot path 무관.
- 사이클 32 R4 universe guard 답습 — 보유/익일청산 종목 절대 보호 (prepare 영역에서도 동일 패턴).

---

## 의제 2 — PriceFilter 단일 source (system_config price_filter_min / price_filter_max 키)

**자문 결론: 채택**

### 3 안 정렬
- **안 A (채택)**: scanner 영역과 동일 키 (`price_filter_min` / `price_filter_max`) 공유. `get_price_filter()` 헬퍼 재사용.
- 안 B: VB 전용 키 별도 신설 (`vb_price_filter_min` / `vb_price_filter_max`). 운영 복잡도 증가.
- 안 C: VB DEFAULT_PARAMS에 하드코딩. 운영 PUT 불가, 변경 시 코드 배포 필요.

### 채택 사유
- scanner 영역과 prepare 영역이 동일 임계 적용 → 운영자 인지 일치 + 운영 단순화.
- 사이클 65 PriceFilter Pydantic 모델 재사용 + 60s TTL 캐시 호환 (scanner 모듈 전역 캐시 재사용 가능).
- DB 단일 키 → PUT 시 양쪽 영역 동시 갱신 효과 (scanner 캐시 invalidate + prepare 다음 호출 반영).

### 호출 패턴 권고
```
# VB._scan_universe() 영역 종료 직전
from src.db.system_config import get_price_filter
pf = await get_price_filter()
if pf.is_active:
    filtered = await self._apply_price_filter_in_prepare(filtered, pf)
```

`_apply_price_filter_in_prepare(tickers, pf)` 헬퍼 = VB strategy 내부 메서드 또는 scanner 모듈 헬퍼 공유.

### PUT 즉시 반영
- scanner 영역 = 60s TTL 캐시 + PUT 직후 `invalidate_price_filter_cache_scanner()` → 다음 `_scan_loop` 5분 자연 반영.
- prepare 영역 = 매일 07:50 _boot 1회 호출 → PUT 즉시 반영 불가. **익일 반영 영속 명시 의무** (Settings UI 안내 메시지 추가 권고).

---

## 의제 3 — scanner `_apply_price_filter` 유지 (이중 안전망)

**자문 결론: 유지 (사이클 32 R4 universe guard 패턴 답습)**

### 3 안 정렬
- **안 A (채택)**: scanner 영역 유지. prepare 단계 차단 누락 시 scanner 단계가 흡수.
- 안 B: scanner 영역 폐기. prepare 단독 신뢰. 회귀 위험 (prepare 미실행 사이클 = 사이클 106 lifecycle race 영역 영향).
- 안 C: scanner 영역 로그만 축소. 운영자 진단 어려움.

### 채택 사유
- 사이클 106 영역 발견 = `_full_universe_load_task_loop` lifecycle race 결함 → prepare() 영역만 신뢰 시 동일 패턴 결함 시 가격 필터 무력화.
- 이중 안전망 = 사이클 32 R4 (보유 보호) + 사이클 64 (가격 필터) + 사이클 65 (거래대금) 모두 적용된 표준 패턴.
- 운영 로그 노이즈 우려는 사이클 64 영역 `DailyEmitCap` 1회/ticker/일 cap이 이미 흡수.

### 위험 검토
- prepare에서 차단된 종목이 scanner 영역에 도달하지 않음 = scanner `_apply_price_filter` 로그 발화 감소 = 노이즈 자연 감소. 별도 시정 불필요.

---

## 의제 4 — VB prepare() 가격 max 적용 시 사이클 30 005935 매매 안전성 위험 0 확인

**자문 결론: 매매 안전성 영향 0 (직접 검증)**

### 사이클 30 005935 사고 패턴
- 2026-05-21 005935 5/20 매수 → 5/21 strategy_id 매핑 누락 결함 → 핑퐁 INSERT.
- 근본 원인 = `get_today_buy_trades` ticker dedupe를 `_sync_orders_to_db`에 잘못 재사용 → 같은 ticker 다른 order_no 가려짐.
- 매핑 영역 + DB UNIQUE 인덱스 + `_completed_orders` race 가드 3중 시정 영속.

### 사이클 148 영향 평가
- VB prepare() 가격 max 필터는 **신규 매수 진입 *전* 후보 풀 차단 영역만** → 이미 보유 종목 (positions) 영향 0.
- prepare()는 매수 진입 *전* 단계 (사이클 38 명문화 영속) → check_exit_signal / 매도 / 익일청산 / 손절 / Trailing / 15:20 강제청산 hot path 무관.
- 005935 매매 안전성 영역 (매핑/체결통보 race/UNIQUE 인덱스) = 변경 0.

### 가드 의무
- G-148-SAFETY-1: VB prepare() 본체에서 `check_exit_signal` 영역 호출 0건 직접 검증 (사이클 143 G-143-SAFETY-3 답습).
- G-148-SAFETY-2: `risk.on_tick` / `order_engine` import 0건 직접 검증.
- G-148-SAFETY-3: 보유 종목 (positions) 가격 필터 차단 0건 (사이클 32 R4 답습 — 보호 영역).

---

## 의제 5 — VB 단독 우선 + LTV/donchian/BFB/VCP 4 전략 사이클 149+ 인계 (위험 분산)

**자문 결론: 적정 (위험 분산 영속)**

### 3 안 정렬
- **안 A (채택)**: VB 단독 사이클 148 + 4 전략 사이클 149+ 인계. 위험 분산 + 운영 측정 가능.
- 안 B: 5 전략 통합 단일 사이클. 사이클 108 list_by_filter 전환 패턴 답습. 효율적이지만 위험 집중.
- 안 C: VB+LTV 우선 2 전략. 사용자 verbatim VB 영역 한정 정합 vs 효율 균형.

### 채택 사유
- VB는 운영 실증 6 종목 차단 사례 직접 검증 가능 영역 → tester 영역 funnel snapshot 검증 명확.
- VB 사이클 148 완료 후 운영 1일 측정 → LTV/donchian/BFB/VCP 4 전략 동일 패턴 적용 시 회귀 가드 0 보장.
- 사이클 130 권고 카드 #21~#26 패턴 답습 (HIGH 영역은 단독 사이클 우선).

### 사이클 149+ 인계 권고
- LTV: VB 동일 패턴 (5 단계 funnel + 가격 필터 hook). LTV 6 단계 funnel 영역 영속 (사이클 143).
- donchian: 멀티데이 보유 영역 = 가격 필터 적용 시 이미 보유 종목 변경 0 가드 강화 의무.
- BFB / VCP: prepare 단계 일봉 fetch 영역 보호 (KIS Rate Limit 안전 마진).

### 운영 측정 의무
- VB 사이클 148 push 후 1일 영업일 운영 = `[price_filter_scanner_skip]` 빈도 감소 측정 → prepare 단계 흡수 효과 정량화.

---

## 종합 권고

| 의제 | 결정 | 위험 | 진행 |
|------|------|------|------|
| 1. prepare() 가격 필터 추가 | 채택 | MEDIUM | 사이클 148 |
| 2. PriceFilter 단일 source | 채택 | LOW | 사이클 148 |
| 3. scanner 이중 안전망 | 유지 | LOW | 사이클 148 |
| 4. 매매 안전성 영향 0 | 확인 | LOW | 사이클 148 가드 |
| 5. VB 단독 + 4 전략 인계 | 적정 | LOW | 사이클 148+149 |

### 추가 권고
- Settings UI 안내 메시지 = "VB prepare 영역 가격 필터는 익일 반영" 명시 의무 (PUT 즉시 반영은 scanner 영역만).
- 사이클 149+ 인계 시 LTV/donchian/BFB/VCP 동일 패턴 일관 적용.
