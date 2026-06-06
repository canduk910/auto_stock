# 사이클 66 설계 카드 v2 — `_resubscribe_stale_priority` cap=10 결함 시정

> **v2 갱신**: 2026-06-06 (토) · domain-expert 자문 응답 (Q1~Q6-6 옵션 A 전부 채택) 반영
> **v1**: 2026-06-06 (토) · team-leader 1차 설계
> **자문 응답**: `_workspace/cycle66_cap10_fix_domain_response.md`

## 메타

| 항목 | 값 |
|------|------|
| 사이클 | 66 |
| 시작일 | 2026-06-06 (토) |
| 카드 | refactor-review #5 (HIGH) — 사이클 63 §Q5-3 인계 |
| 영역 | `src/engine/stale_manager.py::resubscribe_stale_priority` |
| 위험 등급 | HIGH (KIS LMS chain 직접 영역 + 005935 사고 패턴 잔존 영역) |
| 변경 범위 | 단일 함수 본체 (~12 줄 교체) |
| DB 변경 | 0 |
| 매도/손절/익일청산 영향 | 0 (사이클 38 명문화 — 본 시정은 시세 구독 우선순위 영역) |
| 옵션 A 패턴 | 사이클 55 R-1 / 60 / 62 / 63 / 64 / 65 / 66 = **7 사이클 연속** |

## 결함 정확 위치

**파일**: `src/engine/stale_manager.py`
**함수**: `resubscribe_stale_priority(scheduler, cap=10)`
**라인**: L970~L1076 (전체 함수)
**결함 코드 라인**: **L1023~L1034**

```python
# L1023~L1031 — high_tickers 구성 (try/except 2건만)
high_tickers: set[str] = set()
for s in scheduler.registry.all():
    try:
        high_tickers.update(s.state.positions.keys())
    except Exception:
        pass
ndc_tickers = {t for (t, _sid) in scheduler._pending_next_day_clear}
high_tickers.update(ndc_tickers)

# L1033~L1034 — 결함: priority 분리 *전* cap 적용
# Q5-3 결함 영속 — priority 분리 *전* cap 적용 (사이클 64+ 카드 #5 별도 발의)
targets = stale_tickers[:cap]
```

## 시정 안 v2 — 자문 Q1~Q6-6 전부 반영 (~12L 교체)

```python
# 사이클 66 — 본체 패턴 통일 (try/except 4중 가드 + priority 분리 *후* cap 적용 + HIGH > cap WARNING)
# Q2 채택 — `_check_and_resubscribe_stale` 본체 패턴 답습 (scanner 헬퍼 재사용 거부)
try:
    from src.engine.strategy_registry import registry
    positions = set()
    for strategy in registry.all():
        positions.update(strategy.state.positions.keys())
except Exception:
    positions = set()
try:
    pending_ndc = {
        entry[0] for entry in scheduler._pending_next_day_clear
        if isinstance(entry, tuple)
    }
except Exception:
    pending_ndc = set()
high_tickers = positions | pending_ndc

# Q1 시정: priority 분리 *먼저*
high_targets = [t for t in stale_tickers if t in high_tickers]
low_targets = [t for t in stale_tickers if t not in high_tickers]

# Q3 시정: HIGH > cap = 모두 보장 + WARNING 로그 (운영 가시화)
if len(high_targets) > cap:
    try:
        from src.db.system_logs import write_log
        await write_log(
            "WARNING",
            f"[resubscribe_stale_priority] HIGH 종목 수 ({len(high_targets)}) > cap ({cap}) — "
            f"HIGH 모두 보장 (사이클 29 005935 사고 패턴 차단), cap 권고치 위반 허용"
        )
    except Exception:
        pass

# HIGH 먼저 보장 + LOW 잔여 cap (Q3 = HIGH > cap 시 LOW = 0)
targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
```

## 자문 응답 확정 (Q1~Q6-6)

| Q | 옵션 | 확정 사항 |
|---|------|----------|
| **Q1 (HIGH)** | A | 시정 안 그대로 채택 (사이클 29-R3 본체와 100% 일관) |
| **Q2 (HIGH)** | A + 추가 | try/except 4중 가드 통일 — 본체 `_check_and_resubscribe_stale` 패턴 답습, scanner 헬퍼 재사용 거부 |
| **Q3 (MEDIUM)** | A | HIGH 모두 보장 + cap=10 권고치 위반 허용 + **WARNING 로그 의무** (운영 가시화) |
| **Q4 (LOW)** | 확장 | 10 케이스 + AST 1 = 11건 (team-leader 8 + K-9 경계 + K-10 WARNING) |
| **Q5 (LOW)** | 채택 | **시나리오 D 신규** (HIGH 인위 stale 주입 보유 0) + 신규 측정 지표 3 |
| **Q6-1** | — | sorted 결정적 순서 영속 (cap 적용 변경 후에도 list comprehension 순서 보존) |
| **Q6-2** | — | HIGH > cap 운영 월 1~2 회 가능성 인지 (HIGH 12 stale 시) |
| **Q6-3** | — | list comprehension 성능 영향 0 (30μs 추가, stale 100 종목 기준) |
| **Q6-4** | 의무 | K-2 케이스 의미 전환 docstring 명시 의무 (사이클 63 결함 confirm → 사이클 66 시정 confirm) |
| **Q6-5** | — | monkey patch 영역 0 (try/except 4중 흡수, 테스트 patch 경로 호환) |
| **Q6-6** | 연기 | 자체 헬퍼 `_collect_high_tickers_for_stale_priority` 추출은 사이클 67+ Phase 2-A4 (본 사이클 외) |

## 회귀 가드 11 케이스 (10 + AST 1) — Q4 확장 반영

| 케이스 | 시나리오 | 위험 | 비고 |
|--------|---------|------|------|
| **K-2 갱신** | 사이클 63 K-2 (HIGH 1 사전순 마지막 + LOW 12 + cap=10) → 시정 confirm PASS 의미 전환 | HIGH | **Q6-4 docstring 의무** |
| **K-3 신규** | HIGH > cap 경계 (HIGH 12 + LOW 0 + cap=10 → HIGH 12 모두 통과) | HIGH | Q3 옵션 A 검증 |
| **K-4 신규** | HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) → HIGH 5 + LOW 5 | HIGH | 시나리오 B 재현 |
| K-5 신규 | HIGH 0 + LOW 20 + cap=10 (기존 동일) | LOW | 기존 행위 보존 |
| K-6 신규 | HIGH 5 + LOW 0 + cap=10 → targets = HIGH 5개만 | LOW | LOW 0 케이스 |
| K-7 신규 | stale_tickers 비어있음 (early return) | LOW | early return 영속 |
| **K-8 신규** | `high_tickers` 구성 사이클 25-B HIGH/LOW 분리 일관 (positions ∪ next_day_clear) | HIGH | Q2 try/except 4중 검증 |
| **K-9 신규 (Q4 도메인)** | HIGH 0 + LOW 0 (둘 다 비어있음 edge) → early return | LOW | stale_tickers 자체는 비어있음 케이스와 동일 |
| **K-10 신규 (Q4 도메인)** | HIGH > cap 시 WARNING 로그 발화 검증 (`[resubscribe_stale_priority] HIGH 종목 수 ...`) | MEDIUM | caplog + write_log mock |
| AST | priority 분리 *후* cap 적용 정적 가드 (`low_targets[: max(0, cap - len(high_targets))]` substring 의무) | MEDIUM | G AST 가드 답습 |

**합계 11 = HIGH 4 (36%) / MEDIUM 2 / LOW 4 + AST 1**

## Q5 시나리오 D 신규 (월요일 1h tester verify 결합)

| 시나리오 | 내용 | 안전성 |
|---------|------|--------|
| A (기존) | 자연 monitoring (09:00~10:00 1h) | 보유 0 안전 |
| B (기존) | 인위 stale 주입 (보유 0 종목만, LOW 케이스) | 보유 0 안전 |
| C (기존) | KIS LMS chain 차단 monitoring | 보유 0 안전 |
| **D 신규** | HIGH 종목 인위 stale 주입 시뮬레이션 (`_stale_last_resubscribe_at` 강제 초기화) | **보유 종목 = 시뮬레이션만 (실 시세 누락 0)** |

**신규 측정 지표 3 (Q5 도메인 권고)**:
1. `[stale_priority_resubscribe] count=N tickers=[...]` HIGH/LOW 분포 (1h 누적)
2. `[resubscribe_stale_priority] HIGH 종목 수 > cap` WARNING 발화 카운트 (0건 기대)
3. 사이클 29 005935 사고 패턴 차단: HIGH 종목 5분 우선 재구독 누락 0건 확인

## 다음 단계 (순차)

1. **(현재 완료)** team-leader 설계 카드 v2 갱신 + Red 명세 신규 작성
2. **tdd-engineer Red** 발주 — 11 케이스 본체 작성 (`tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py`)
3. **backend-dev Green** — `src/engine/stale_manager.py::resubscribe_stale_priority` L1023~L1034 ~12L 교체
4. **tester Verify** — V1~V13 + V-AST + V-A3 (HIGH 케이스 + K-2 시정 confirm + K-3/K-4 신규 HIGH + K-10 WARNING)
5. **sync-docs** — CLAUDE.md / HARNESS_CHANGELOG / src/engine/CLAUDE.md / refactor-review 카드 #5 완료 표기 + 회고
6. **사용자 명시 commit + push 지시 대기** — HIGH 카드 + K stale watcher 본체 = 일요일 push 권장 (사이클 60 §Q5 답습)
7. **월요일 (2026-06-08) 09:00~10:00 tester 1h verify** — 사이클 63 인계 시나리오 A/B/C + 사이클 66 시나리오 D 결합 효과 측정

## Push 시점 권고 (사이클 60 §Q5 답습)

| 시점 | 권고 |
|------|------|
| 오늘 (토 = 2026-06-06) | sync-docs 까지 완료, **commit + push 보류** |
| 일요일 (휴장 = 2026-06-07) | 사용자 검수 후 commit + push 권장 시점 |
| 월요일 (장 시작 = 2026-06-08) 09:00~10:00 | tester 1h verify 의무 (시나리오 A/B/C/D 결합) |

**근거**:
- HIGH 카드 + K stale watcher 영역 (사이클 60 §Q7 영구 hot path)
- KIS LMS/앱키 정지 chain 직접 영역 (005935 사고 패턴)
- 사이클 60~66 7 사이클 주말 push 답습 영속

## 안전 가드 / 영속 정책

- **사이클 38 명문화 영속**: 본 시정은 *시세 구독* 영역 — 매도/손절/Trailing/익일청산/15:20 강제청산 영향 0
- **사이클 25-B HIGH/LOW 분리 영속**: positions/next_day_clear = HIGH+bypass=True, 그 외 = LOW+bypass=False — 본 시정은 *cap 적용 순서* 만 교체
- **사이클 29-R3 우선순위 분리 영속**: K stale watcher 본체와 동일 철학 (HIGH 절대 우선)
- **사이클 63 A3 답습**: 단일 함수 시정 (HIGH 영역) + 회귀 가드 K-2 갱신 + AST 정적 가드
- **사이클 64+65 회귀 가드 0 영속**: 가격/거래대금 필터는 stale watcher 무관, 본 시정 영향 0
- **사이클 60~66 7 사이클 옵션 A 답습**: 매번 자문 응답 전부 채택 패턴 영속
