# 사이클 67 자문 의뢰서 — `stale_manager.py` 1,099L sub-module 분해

> **의뢰자**: team-leader
> **수신**: domain-expert (데이/스윙 트레이더 출신, 매매 행위 영향 평가 + KIS WS 운영 경험)
> **선행 문서**: `cycle67_stale_manager_decomposition_design_card.md`
> **작성일**: 2026-06-06 (토)
> **회신 요청일**: 2026-06-06 ~ 2026-06-07 오전 (일요일 push 목표)

---

## 0. 자문 배경

사이클 60/61/63/66 누적 18 사이클 + hotfix 4 영역 종결 후 **첫 refactor 사이클** (행위 보존). `stale_manager.py` 1,099L 단일 모듈 (11 함수 + 10 상수) 을 **4 sub-module 분해** (책임 영역 명확 분리).

위험 영역:
- **K stale watcher 본체 = HIGH hot path** (360 회/일 + KIS LMS chain)
- **누적 회귀 가드 78 케이스 영향** (사이클 60 18 + 61 20 + 63 29 + 66 11)
- **사이클 29 005935 사고 영역** (사이클 66 시정 영속 의무)
- **사이클 60 §Q7 영구 hot path 정책 영속 의무**

설계 카드 §2 4 sub-module 청사진 + §3 옵션 A/B/C + §4 위험 매트릭스 + §5 회귀 가드 청사진 (15 케이스) + §6 답습 매트릭스 작성 완료. 행위 보존 refactor 이지만 **회귀 가드 78 케이스 영향 + K stale watcher 본체 HIGH 영역** = 행위 영향 평가 의무.

---

## Q1 (HIGH) — sub-module 분해 후 import 의존성 방향 결정

### 옵션
- **옵션 A (권장)**: `stale_watcher_core` 단방향 의존 (watcher_core → diagnostics/recovery/universe_guard, 역방향 0)
  - facade (`stale_manager.py` ~30L re-export) 보존 — scheduler.py 11 wrapper 변경 0
- **옵션 B**: 공통 헬퍼 (`stale_helpers.py` ~50L) 신설 — `sys.modules.get("src.engine.scheduler")` 패턴 4회 중복 제거
  - 추가 모듈 1 개 (4 → 5) + 헬퍼 SoT 분산 위험
- **옵션 C**: facade 없이 scheduler.py 가 직접 4 sub-module import — wrapper 11개 lazy import 경로 모두 갱신 의무

### 자문 포인트
- **A 채택 시 facade re-export 항목 21개** (11 함수 + 10 상수) — 사이클 60 답습 영속 가능?
- **B 채택 시 헬퍼 추가 모듈 1개** — 사이클 71+ 별도 카드 분리 vs 사이클 67 내 동시 진행 트레이드오프?
- **C 채택 시 scheduler.py 11 wrapper 모두 변경** — 사이클 60/61/63 답습 패턴 (시그너처 변경 0) 위반 위험?

### 권고 안 (team-leader)
**옵션 A 채택** (사이클 60/61/63/66 8 사이클 연속 답습 + scheduler.py 변경 0 보장).
옵션 B 는 사이클 71+ 별도 카드 분리 권고.

---

## Q2 (HIGH) — Q4=B 직접 호출 (사이클 63 영속) sub-module 간 import 방식

### 현 상태 (사이클 63 영속)
`check_and_resubscribe_stale` 본체 마지막에 `emit_stale_session_detail(scheduler, stale_tickers, now)` **직접 호출** (1 hop 단축, scheduler.py wrapper 통하지 않음). 사이클 63 Q4=B 채택 영속.

### sub-module 분해 후 (옵션 A)
`stale_watcher_core.check_and_resubscribe_stale` 가 `stale_diagnostics.emit_stale_session_detail` 호출 — **cross-module call**.

### 자문 옵션
- **옵션 P1 (직접 import)**: `from src.engine.stale_diagnostics import emit_stale_session_detail` 상단 import
  - 장점: 간결 + python import 캐시 활용
  - 단점: AST 정적 가드 (G-5 import 순환 0) 검증 시 단방향 의존 확인 필수
- **옵션 P2 (lazy import)**: 함수 내 `from src.engine.stale_diagnostics import emit_stale_session_detail` lazy
  - 장점: 순환 위험 회피 + 사이클 60/61/63 답습 패턴
  - 단점: 360 회/일 hot path 에서 import 오버헤드 (무시 가능 — Python import 캐시)
- **옵션 P3 (sys.modules.get 패턴)**: `_diag_mod = sys.modules.get("src.engine.stale_diagnostics")` + `_diag_mod.emit_stale_session_detail(...)` 패턴
  - 장점: 사이클 63 D-2 답습 일관성 (freezegun patch 호환과 동일 패턴)
  - 단점: 코드 verbose

### 자문 포인트
- **P1 vs P2 vs P3 선택 — 사이클 60/61/63 답습 일관성 vs 가독성 트레이드오프?**
- **AST 정적 가드 G-5 (import 순환 0) 가 P1 채택 시 충분?**

### 권고 안 (team-leader)
**옵션 P1 (직접 import)** — AST G-5 가드로 순환 0 보장 + import 캐시 활용. P3 sys.modules.get 패턴은 freezegun datetime patch 호환 영역만 한정 유지.

---

## Q3 (HIGH) — 사이클 60/63/66 영구 가드 영속 의무

### 영속 의무 가드
- **사이클 60 I1**: `logging.getLogger("src.engine.scheduler")` 명시 binding (caplog 호환) — 4 sub-module 모두 동일 영속?
- **사이클 60 G-3**: 폐기 메서드 0 AST 가드 (scheduler.py 에 폐기된 메서드 0)
- **사이클 63 D-1**: 의존성 역전 0 AST 가드 (`stale_manager` 가 `scheduler` import 0건)
- **사이클 66 AST**: priority 분리 *후* cap 적용 AST 가드 (`resubscribe_stale_priority` L1023-1057 영속)

### 자문 옵션
- **옵션 A (단순 답습)**: 4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` 동일 영속 + AST 가드 4 종 sub-module 별 RE-RUN
- **옵션 B (sub-module 별 logger)**: 각 sub-module 자체 logger (`logging.getLogger("src.engine.stale_diagnostics")` 등) — caplog 호환 깨짐 위험
- **옵션 C (혼합)**: hot path (watcher_core) 만 `src.engine.scheduler` logger, 나머지 sub-module 자체 logger

### 자문 포인트
- **옵션 A 채택 시 caplog 호환 보장** — 78 회귀 가드 중 logger 검증 영역 확인?
- **옵션 B/C 채택 시 사이클 60 I1 영속 의무 위반 위험?**

### 권고 안 (team-leader)
**옵션 A 채택** — 사이클 60 I1 + 사이클 63 D-1 영속 의무 + caplog 호환 보장.

---

## Q4 (MEDIUM) — 회귀 가드 78 케이스 patch 경로 갱신 전략

### 영향 영역
- 사이클 60 18 가드 → `patch("src.engine.stale_diagnostics.X")` 갱신
- 사이클 61 20 가드 → `patch("src.engine.stale_session_recovery.X")` + `patch("src.engine.stale_universe_guard.X")` 갱신
- 사이클 63 29 가드 → `patch("src.engine.stale_watcher_core.X")` 갱신
- 사이클 66 11 가드 → 동일 영역 (resubscribe_stale_priority)

총 15 `patch("src.engine.stale_manager.*")` 영역 → 4 sub-module 분산 갱신.

### 자문 옵션
- **옵션 A (sub-module 직접 patch)**: `patch("src.engine.stale_diagnostics.refresh_stale_ccnl_cache")` 등 sub-module 별 갱신
  - 장점: 명확 + sub-module 책임 영역 검증
  - 단점: 15 patch 경로 모두 갱신 (일관성 위험 — 사이클 60 hotfix 답습 의무)
- **옵션 B (facade patch 영속)**: `patch("src.engine.stale_manager.refresh_stale_ccnl_cache")` 영속 — facade re-export 영역 patch 가 sub-module 영역 까지 미치는가?
  - **위험**: facade re-export 는 `from src.engine.stale_diagnostics import X` 이므로 `patch("src.engine.stale_manager.X")` 는 facade 의 reference 만 변경, sub-module 의 정의는 변경 안 됨 → **silent 결함 위험**
- **옵션 C (혼합)**: 직접 호출 영역 (Q4=B) 은 sub-module patch, 외부 caller (scheduler.py wrapper) 는 facade patch

### 자문 포인트
- **옵션 A 채택 시 사이클 60 hotfix 답습 (patch 경로 누락 silent 결함) 위험 영역?**
- **옵션 B silent 결함 영구 차단 가드 추가 필요?**

### 권고 안 (team-leader)
**옵션 A 채택** — sub-module 직접 patch + 사이클 60 hotfix 답습 (15 patch 경로 일관성 + 카테고리 분리 측정 + flakiness 3 회).

---

## Q5 (MEDIUM) — scheduler.py wrapper lazy import 경로 변경 여부

### 현 상태
scheduler.py L2434~L2501 11 wrapper:
```python
async def _check_and_resubscribe_stale(self) -> None:
    from src.engine import stale_manager
    await stale_manager.check_and_resubscribe_stale(self)
```

### sub-module 분해 후
- **옵션 A (facade 유지)**: scheduler.py wrapper 변경 0 (facade re-export 활용) — 사이클 60/61/63 답습
- **옵션 B (lazy import 경로 갱신)**: `from src.engine import stale_watcher_core` 등 sub-module 별 lazy import — wrapper 11개 모두 변경
- **옵션 C (직접 호출)**: scheduler.py 가 4 sub-module 직접 import (lazy 제거) — wrapper 자체 제거?

### 자문 포인트
- **옵션 A 채택 시 facade re-export 21 항목 (11 함수 + 10 상수) 영속 의무**
- **옵션 B/C 채택 시 사이클 60 §Q5 답습 패턴 위반 위험?**
- **wrapper 11개 시그너처 변경 0 의무 — 다른 모듈 (tests / scheduler 자체) 에서 wrapper 직접 사용 영역 확인?**

### 권고 안 (team-leader)
**옵션 A 채택** — facade 유지 + scheduler.py wrapper 변경 0 (사이클 60/61/63/66 8 사이클 연속 답습).

---

## Q6+ (자유 발의) — domain-expert 발의 영역

### 예상 발의 영역
- **Q6**: 사이클 67 분해 후 사이클 68+ 카드 #16 (사이클 65 후보 풀 폭축 2주 회고) 와의 의존 — 분해된 4 sub-module 영역과 카드 #16 영향 영역 겹침?
- **Q7**: 사이클 71+ 옵션 B 공통 헬퍼 (`stale_helpers.py`) 분리 사전 설계 — `sys.modules.get` 패턴 4회 중복 제거 + `logging.getLogger("src.engine.scheduler")` 헬퍼화
- **Q8**: K stale watcher 본체 hot path (360 회/일) 분해 후 import 캐시 행위 영향 — 첫 호출 시 4 sub-module 모두 import 부담?
- **Q9**: 사이클 29 005935 사고 영역 (사이클 66 시정 영속) 영구 가드 — sub-module 분해 후 검증 영역 확인 (AST priority 분리 *후* cap 영속)

---

## 회신 형식

domain-expert 회신 시 다음 형식 권고 (사이클 60/61/63/66 답습):

```markdown
# 사이클 67 domain-expert 자문 회신

## Q1 회신: 옵션 A/B/C 채택 + 사유
## Q2 회신: 옵션 P1/P2/P3 채택 + 사유
## Q3 회신: 옵션 A/B/C 채택 + 사유
## Q4 회신: 옵션 A/B/C 채택 + 사유 + silent 결함 영구 차단 가드 안
## Q5 회신: 옵션 A/B/C 채택 + 사유
## Q6+ 회신: 자유 발의 + 사이클 68+ 카드 의존 영향
## 종합 권고: 회귀 가드 추가 또는 변경 의견
```

회신 후 사용자에게 보고 → 사용자 결정 → tdd-engineer Red → backend-dev Green → tester Verify → sync-docs → **일요일 (2026-06-07) commit + push** 진행.
