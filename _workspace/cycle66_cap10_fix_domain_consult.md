# 사이클 66 자문 의뢰서 — `_resubscribe_stale_priority` cap=10 결함 시정

## 의뢰 배경

**카드**: refactor-review #5 (HIGH) — 사이클 63 §Q5-3 인계
**위험 등급**: HIGH (K stale watcher 영역 = KIS LMS/앱키 정지 chain 직접 영역, 005935 사고 패턴)

**결함**: `src/engine/stale_manager.py::resubscribe_stale_priority` L1033~L1034 가 `targets = stale_tickers[:cap]` 으로 **priority 분리 *전* cap 적용**. HIGH 종목 (보유/익일청산) 이 사전순으로 LOW 후보 뒤에 위치할 경우 cap 밖 잘림 → 5분 우선 재구독 누락 → KIS LMS chain 위험.

**시정 안 (refactor-review 메모 인용)**:
```python
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]
targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

---

## Q1 (HIGH) — 시정 안 코드 정합성 + 사이클 29-R3 패턴 일관 검증

**의제**: 시정 안의 priority 분리 *후* HIGH 먼저 + LOW 잔여 cap 패턴이:
1. **KIS WebSocket 풀 API 인터페이스 영향 평가**: `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority='HIGH'|'LOW', bypass_limit=True|False)` 호출 시 HIGH 가 cap=10 초과해도 모두 통과 보장되는가? (`bypass_limit=True` 가 41 한도 우회)
2. **사이클 29-R3 패턴 일관**: K stale watcher 본체 (`check_and_resubscribe_stale`) 의 HIGH/LOW 분리 (L839~L845) 와 동일 철학인가?
3. **보조 세션 분산 영향**: LOW (보조 세션) 가 잔여 cap 만 받을 때 분산 효과 보존되는가?

**자문 요청 사항**:
- 옵션 A (시정 안 채택) / B (다른 안 제시) / C (현 결함 영속 + 다른 안전망)
- 코드 sketch 또는 의사코드
- K stale watcher 본체와의 일관성 검증

---

## Q2 (HIGH) — `high_tickers` 구성 시점

**현재 코드 (L1024~L1031)**:
```python
high_tickers: set[str] = set()
for s in scheduler.registry.all():
    try:
        high_tickers.update(s.state.positions.keys())
    except Exception:
        pass
ndc_tickers = {t for (t, _sid) in scheduler._pending_next_day_clear}
high_tickers.update(ndc_tickers)
```

**대안 — 사이클 64+65 헬퍼 재사용**:
```python
from src.engine.scanner import _collect_protected_tickers_for_scanner
high_tickers = _collect_protected_tickers_for_scanner(scheduler)
```

**자문 의제**:
1. **헬퍼 재사용 위험**: `_collect_protected_tickers_for_scanner` 는 사이클 64 가격 필터용 헬퍼 — stale_manager 와 책임 도메인 다름. 재사용 시 의존 방향 위반 가능성?
2. **현 코드 답습**: 사이클 25-B (2026-05-20) 도입 패턴 답습 시 변경 0 + 일관 유지
3. **자체 헬퍼 추출**: `stale_manager.py` 모듈 내 `_collect_high_tickers_for_stale(scheduler)` 자체 헬퍼 신설 (3중 답습 = stale_manager 자체 캡슐화)

**자문 요청 사항**:
- 옵션 A (현 코드 답습) / B (scanner 헬퍼 재사용) / C (stale_manager 자체 헬퍼 신설)
- 의존 방향 + 모듈 책임 도메인 평가
- 사이클 64+65 답습 일관성 vs stale_manager 캡슐화 trade-off

---

## Q3 (MEDIUM) — HIGH > cap 경계 케이스 정책

**시나리오**: HIGH 보유 12종목 stale + LOW 0 + `cap=10`

**옵션 A (시정 안 그대로)**: `targets = HIGH 12개 + LOW 0` = 12개 모두 재구독
- 장점: HIGH 보유 종목 100% 보장 (사이클 25-B 영구 정책)
- 위험: cap=10 의도 위반 + KIS LMS Rate Limit 부담 (50ms sleep 보호 영속)

**옵션 B (cap 강제)**: `targets = (HIGH + LOW)[:cap]`
- 장점: cap=10 의도 보존
- 위험: HIGH 2종목 누락 → 다음 K stale watcher 120s 까지 stale 유지

**옵션 C (cap 동적 확장)**: `effective_cap = max(cap, len(high_targets))`
- 장점: HIGH 모두 보장 + cap 의도 약간 유지
- 위험: cap 의도가 안전 한도라면 위반

**자문 의제**:
1. KIS LMS Rate Limit 운영 실측 (사이클 28 stale=14 사고 + 사이클 29 005935 사고 시 동시 재구독 부담)
2. HIGH 12개 동시 재구독 시 50ms × 12 = 600ms 영향 평가
3. cap=10 의 본래 의도 = 부담 한도 vs 표본 한도 (HIGH 절대 우선 vs cap 강제)

**자문 요청 사항**:
- 옵션 A/B/C 중 권고
- HIGH > cap 시 INFO/WARNING 로그 명시 권고

---

## Q4 (LOW) — 회귀 가드 청사진

**기준 케이스 8건 (사이클 63 K-2 갱신 + 신규 K-3~K-8)**:

| 케이스 | 시나리오 | 위험 등급 | 결함 검증 |
|-------|---------|----------|----------|
| K-2 갱신 | 사이클 63 K-2 (HIGH 1 사전순 마지막 + LOW 12 + cap=10) | HIGH | 시정 후 HIGH 포함 targets 검증 |
| K-3 | HIGH > cap 경계 (HIGH 12 + LOW 0 + cap=10) | HIGH | Q3 자문 결과 의존 |
| K-4 | HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) | HIGH | targets = HIGH 5 + LOW[:5] |
| K-5 | HIGH 0 + LOW 20 + cap=10 | LOW | targets = LOW[:10] (기존 동일) |
| K-6 | HIGH 5 + LOW 0 + cap=10 | LOW | targets = HIGH 5개만 (LOW 0) |
| K-7 | stale_tickers 비어있음 | LOW | early return |
| K-8 | `high_tickers` 구성 사이클 25-B HIGH/LOW 분리 일관 (positions ∪ next_day_clear) | HIGH | Q2 자문 결과 의존 |
| AST | priority 분리 *후* cap 적용 keyword 정적 가드 | MEDIUM | substring 의무 검증 |

**자문 의제**:
1. 누락된 경계 케이스 추가 권고 (HIGH=cap 일치, LOW=0+HIGH=cap, 등)
2. freezegun + caplog 패턴 활용 권고
3. 사이클 63 patch 경로 (`src.realtime.websocket_pool.kis_ws_pool`) 답습 의무

**자문 요청 사항**:
- 케이스 추가/제거 권고
- 테스트 파일 분리 (`tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`)

---

## Q5 (LOW) — 월요일 1h tester verify 결합 효과 측정

**배경**: 사이클 63 인계 = 월요일 (2026-06-08, **오타 수정 — 사실은 2026-06-09 월요일**) 09:00~10:00 1h tester verify 의무
- 시나리오 A: 자연 monitoring
- 시나리오 B: 인위 stale 주입 (보유 0 종목만 = LOW 케이스로 안전성 보장)
- 시나리오 C: KIS LMS chain 차단 monitoring

**자문 의제**:
1. **시나리오 D 신규 권고 가능성**: HIGH 종목 인위 stale 주입 시나리오 (보유 종목 시뮬레이션) — 사이클 66 시정 효과 실측
2. **결합 효과 측정 지표**: `[stale_priority_resubscribe] count=N tickers=[...]` 로그 분석 → HIGH/LOW 분포 + cap 영향 평가
3. **사이클 29 005935 사고 패턴 차단 확인**: HIGH 종목 5분 우선 재구독 누락 0건 검증

**자문 요청 사항**:
- 시나리오 D 신규 (HIGH 인위 stale 주입) 채택 여부
- 운영 환경 안전성 (HIGH 주입 = 보유 종목 시세 누락 위험)
- 결합 효과 정량 측정 지표 (sub_priority 분포, cap 도달 비율)

---

## 산출물 요청 형식

domain-expert 응답 시:
1. Q1~Q5 옵션 A/B/C 명시
2. 코드 sketch 또는 의사코드
3. 회귀 가드 케이스 추가/제거 권고
4. 운영 위험 등급 재평가 (HIGH 유지 / MEDIUM 강등)
5. 사이클 60~65 답습 패턴 일관성 평가
