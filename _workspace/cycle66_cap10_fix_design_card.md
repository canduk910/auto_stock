# 사이클 66 설계 카드 — `_resubscribe_stale_priority` cap=10 결함 시정

## 메타

| 항목 | 값 |
|------|------|
| 사이클 | 66 |
| 시작일 | 2026-06-06 (토) |
| 카드 | refactor-review #5 (HIGH) — 사이클 63 §Q5-3 인계 |
| 영역 | `src/engine/stale_manager.py::resubscribe_stale_priority` |
| 위험 등급 | HIGH (KIS LMS chain 직접 영역 + 005935 사고 패턴 잔존 영역) |
| 변경 범위 | 단일 함수 본체 (~5 줄) |
| DB 변경 | 0 |
| 매도/손절/익일청산 영향 | 0 (사이클 38 명문화: 매수 진입 전용 정책 적용 영역 외 — 본 시정은 시세 구독 우선순위 영역, 매도 경로 무관) |

## 결함 정확 위치

**파일**: `src/engine/stale_manager.py`
**함수**: `resubscribe_stale_priority(scheduler, cap=10)`
**라인**: L970~L1076 (전체 함수)
**결함 코드 라인**: **L1033~L1034**

```python
# L1033~L1034 (사이클 63 이주 시 결함 인지하면서도 영속, 별도 카드 #5 발의)
# Q5-3 결함 영속 — priority 분리 *전* cap 적용 (사이클 64+ 카드 #5 별도 발의)
targets = stale_tickers[:cap]
```

## 결함 시나리오 (사이클 63 K-2 케이스 PASS = confirm)

### 시나리오 A — HIGH 종목 cap 밖 잘림 (운영 사고 직결)

**전제 조건**:
- `ticker_last_tick` 에 stale 종목 13개 (모두 stale 임계 60s 초과)
- 정렬 결과 (사전순): `["000020", "000040", "000060", ..., "000200", "005935"]`
- `high_tickers` = `{"005935"}` (보유 1종목 = 마지막 정렬 위치)
- `cap=10`

**현 코드 결과**:
- `stale_tickers[:10]` = `["000020", "000040", ..., "000200"]` (LOW 10건만)
- `005935` (HIGH 보유) 누락 → 5분 우선 재구독 안 됨
- **다음 K stale watcher 120s tick 까지 stale 유지 → 최악의 경우 5분~10분 stale 잔존**
- 시나리오 사이클 29 005935 사고 패턴 반복 위험

### 시나리오 B — HIGH 종목 다수 + LOW 후보 다수 (현실적 운영)

**전제 조건**:
- stale 종목 25개 = HIGH 5 + LOW 20
- 정렬 결과 HIGH 가 사전순 후반에 분포 (예: `005380`, `005490`, `005930`, `005935`, `068270`)
- `cap=10`

**현 코드 결과**:
- `stale_tickers[:10]` 에 HIGH 0~2개 포함 (LOW 가 사전순 우선)
- HIGH 3~5개 누락 → 보유 종목 5분 우선 재구독 누락

## 시정 안 (refactor-review 메모 #5 인용 + 사이클 29-R3 패턴 일관)

```python
# 사이클 66 — priority 분리 *먼저*, cap 적용 *나중* (HIGH 절대 우선)
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]
# HIGH 먼저 보장 + LOW 잔여 cap (HIGH 가 cap 초과 시 모두 통과 — Q3 자문 영역)
targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

**시정 효과**:
- HIGH 절대 우선: 보유/익일청산 종목은 cap 밖 잘림 0건
- LOW 잔여 cap: HIGH 가 cap 미만일 때만 LOW 가 채워짐 (정상 케이스)
- 사이클 29-R3 패턴 일관: K stale watcher 본체와 동일 HIGH/LOW 분리 철학

## 자문 의제 (domain-expert 발주 5건)

1. **Q1 (HIGH)** — 시정 안 코드 정합성 + 사이클 29-R3 패턴 일관 검증
2. **Q2 (HIGH)** — `high_tickers` 구성 시점: 현 코드 L1024~L1031 답습 (`registry.positions ∪ _pending_next_day_clear`) vs `_collect_protected_tickers_for_scanner` 헬퍼 재사용 (사이클 64+65 답습)
3. **Q3 (MEDIUM)** — HIGH > cap (예: HIGH 12 + LOW 0) 경계 케이스 정책: HIGH 모두 보장 vs cap 강제 (LOW 0이라 무해 보이지만 KIS LMS 부담 평가)
4. **Q4 (LOW)** — 회귀 가드 청사진: 사이클 63 K-2 갱신 + 신규 K-3 (HIGH > cap) + K-4 (HIGH 사전순 후반 case A 재현)
5. **Q5 (LOW)** — 월요일 (2026-06-08) 09:00~10:00 1h tester verify (사이클 63 인계) 와 사이클 66 시정 결합 효과 측정 시나리오

## 회귀 가드 청사진 (사이클 63 답습)

| 카테고리 | 케이스 | 위험 | 비고 |
|---------|-------|------|------|
| K-2 갱신 | 사이클 63 K-2 (결함 confirm PASS) → 시정 confirm PASS 의미 전환 | HIGH | 동일 시나리오 재현하여 시정 후 HIGH 종목 targets 포함 검증 |
| K-3 신규 | HIGH > cap 경계 (HIGH 12 + LOW 0 + cap=10) | HIGH | HIGH 모두 통과 (Q3 자문 결과 의존) |
| K-4 신규 | 시나리오 A 재현 (HIGH 1 사전순 마지막 + LOW 12) | HIGH | targets = [HIGH] + LOW[:9] |
| K-5 신규 | HIGH 0 + LOW 20 + cap=10 | LOW | targets = LOW[:10] (기존 동일) |
| K-6 신규 | HIGH 5 + LOW 0 + cap=10 | LOW | targets = HIGH 5개만 (LOW 0) |
| K-7 신규 | stale_tickers 비어있음 | LOW | early return |
| K-8 신규 | `high_tickers` 구성 사이클 25-B HIGH/LOW 분리 일관 (positions ∪ next_day_clear) | HIGH | Q2 자문 결과 의존 |
| AST | priority 분리 *후* cap 적용 keyword 정적 가드 (`low_targets[: max(0, cap - len(high_targets))]` substring 의무) | MEDIUM | G AST 가드 답습 |

**예상 회귀 가드 총 8~10 케이스** (HIGH 4 = 40%+)

## 다음 단계

1. **(현재)** team-leader 설계 카드 + 자문 의뢰서 산출 완료
2. **domain-expert 자문 발주** (사용자 명시 지시 후) — Q1~Q5 응답
3. **사용자 결정** (옵션 A 전부 적용 권장, 사이클 60~65 6 사이클 연속 패턴)
4. **tdd-engineer Red** — 회귀 가드 8~10 케이스 추가
5. **backend-dev Green** — L1033~L1034 시정 (~5 줄 교체)
6. **tester Verify** — V1~V13 + V-AST + V-A3 (HIGH 케이스 + K-2 시정 confirm)
7. **sync-docs** — CLAUDE.md / HARNESS_CHANGELOG / src/engine/CLAUDE.md / refactor-review 카드 #5 완료 표기
8. **사용자 명시 commit + push 지시 대기**

## Push 시점 권고

| 항목 | 권고 |
|------|------|
| 오늘 (토) | sync-docs 까지 완료, **commit + push 보류** (HIGH 카드 = 사이클 60 §Q5 답습) |
| 일요일 (휴장) | 사용자 검수 후 commit + push 권장 시점 |
| 월요일 09:00~10:00 | tester 1h verify 의무 (사이클 63 인계 + 사이클 66 시정 결합 효과 측정) |

**근거**:
- HIGH 카드 + K stale watcher 영역 (사이클 60 §Q7 영구 hot path)
- KIS LMS/앱키 정지 chain 직접 영역 (005935 사고 패턴)
- 주말 push 의무 영속 (사이클 60~65 6 사이클 답습)

## 안전 가드 / 영속 정책

- **사이클 38 명문화 영속**: 본 시정은 *시세 구독* 영역 — 매도/손절/Trailing/익일청산/15:20 강제청산 영향 0
- **사이클 25-B HIGH/LOW 분리 영속**: positions/next_day_clear = HIGH+bypass=True, 그 외 = LOW+bypass=False — 본 시정은 *cap 적용 순서* 만 교체, 분리 정책 영속
- **사이클 29-R3 우선순위 분리 영속**: K stale watcher 본체와 동일 철학 (HIGH 절대 우선)
- **사이클 63 A3 답습**: 단일 함수 시정 (HIGH 영역) + 회귀 가드 K-2 갱신 + AST 정적 가드
- **사이클 64+65 회귀 가드 0 영속**: 가격/거래대금 필터는 stale watcher 무관, 본 시정 영향 0
