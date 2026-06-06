# 사이클 67 자문 회신 — `stale_manager.py` 1,099L sub-module 분해

**작성**: domain-expert (데이/스윙 트레이더 출신, KIS WS 운영 경험)
**일자**: 2026-06-06 (토, KRX/NXT 휴장)
**의뢰**: team-leader (사이클 67 = 카드 #14 MEDIUM)
**선행 자문**: 사이클 60 / 61 / 63 / 66 (8 사이클 연속 옵션 A 답습 패턴)
**산출**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

---

## 0. 핵심 결론 한 줄

**5 의제 모두 RECOMMEND (team-leader 1차 옵션 A 전수 채택과 100% 일치)** + **Q6+ 신규 발의 3 (Q6-1 hot path import 캐시 측정 + Q6-2 사이클 71+ 옵션 B 헬퍼 사전 설계 문서화 + Q6-3 사이클 65 후보 풀 폭축 회고와 시점 충돌 평가)** + **회귀 가드 G-1~G-15 청사진 채택 + 신규 G-16/G-17 2 가드 보강 권고**.

분해 자체는 사이클 60~66 8 사이클 누적의 자연스러운 종결 — *행위 보존* refactor 의 *증명 부담* 이 사이클 63 (HIGH hot path 이주) 보다 낮음. 그러나 K stale watcher 본체 (`stale_watcher_core`) 가 다른 sub-module (`stale_diagnostics`) 의 함수를 직접 호출 (Q4=B 영속) 하는 cross-module call 이 *유일한 새 위험* — Q1/Q2 결정이 본 자문의 핵심.

**가장 중요한 단일 권고**: **Q1 옵션 A (단방향 의존, facade 보존) + Q2 옵션 P1 (직접 import)** — 사이클 60~66 답습 패턴과 100% 일관 + 78 회귀 가드 patch 경로 영향 최소화 (대다수가 `patch("src.engine.scheduler.*")` 패턴이라 sub-module 분해 영향 0).

---

## 1. 사전 조사 결과 — 78 회귀 가드 patch 경로 실측

자문 작성 전 `tests/unit/engine/` 영역 grep 조사 결과 (사이클 60/61/63/66 누적 78 회귀 가드):

### 1.1 patch 경로 분포 (실측)

| patch 경로 패턴 | 건수 (추정) | 영향 |
|---------------|----------|------|
| `patch("src.engine.scheduler.kis_ws")` / `kis_ws_pool` / `write_log` / `datetime` | **압도적 다수** (사이클 61 + 63 회귀 가드의 ~80%) | **sub-module 분해 영향 0** — patch 대상 = scheduler 모듈 네임스페이스, sub-module 함수가 `sys.modules.get("src.engine.scheduler")` 패턴으로 동일 객체 참조 |
| `patch("src.engine.stale_manager.*")` 패턴 | **0건** (실측) | **분해 영향 0** — Q4 옵션 결정 무관 |
| caplog `set_level(..., logger="src.engine.scheduler")` | 다수 | **sub-module 분해 영향 0** — 4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` 영속 (Q3 옵션 A) |
| caplog `set_level(..., logger="src.engine.stale_manager")` | 1건 (사이클 66 K-10) | **사이클 66 시정 본체가 `stale_watcher_core` 로 이주** → logger binding 만 영속하면 호환 (Q3 옵션 A 채택 시) |
| `from src.engine import stale_manager` 모듈 import | 다수 (각 회귀 가드 첫 줄) | **facade 보존 (Q1 옵션 A) 채택 시 영향 0** — facade re-export 가 모든 함수/상수 노출 보장 |
| `from src.engine.stale_manager import X` 직접 import | 5 상수 + 일부 함수 | **facade re-export 가 직접 import 도 호환** (Python `from X import Y` 는 `X` 모듈 네임스페이스에서 `Y` 조회 — re-export 충분) |

### 1.2 결정적 함의

**Q4 결정이 사실상 옵션 B (facade patch 영속) 자연 채택** — 78 회귀 가드 중 `patch("src.engine.stale_manager.*")` 형태가 0건이므로 *patch 경로 갱신 의무 자체가 거의 없음*. 사이클 60 hotfix 패턴 답습 부담이 사이클 60/61/63 대비 *현저히 낮음*.

**Q1/Q5 결정도 옵션 A (facade 보존) 자연 채택** — scheduler.py 11 wrapper 가 모두 `from src.engine import stale_manager` 형태 (sub-module 직접 import 0) 이므로 facade re-export 가 wrapper 변경 0 보장.

→ **사이클 67 분해는 사이클 60~66 8 사이클 누적 답습 패턴의 *완벽한 자연 귀결*** — *새로운 결정 영역은 Q4=B 직접 호출의 cross-module import 방식 (Q2)* 1 건만.

---

## 2. Q1 (HIGH) — import 의존성 방향 결정

### 답변: **옵션 A 채택 RECOMMEND** (사이클 60~66 8 사이클 답습 + scheduler.py wrapper 변경 0)

### 근거 — 트레이더 시각 + 코드 결합도 평가

**시장 가설 (운영 위험 관점)**: K stale watcher 본체 (`stale_watcher_core`) = 360 회/일 hot path + KIS LMS chain 직접 영역. 외부 호출자 (scheduler.py 11 wrapper) 의 *시그너처 변경 0* 의무는 사이클 51 boot_manager 답습 패턴이 8 사이클 (51 → 60 → 61 → 63 → 66 + 본 67) 연속 검증된 안전 영역.

**실전 사례 인용 — 사이클 60 §Q5 영속 의무**:
사이클 60 응답서 §Q5 (push 시점) 가 명시한 *주말 push + 월요일 1h tester verify* 영속 의무는 "외부 인터페이스 변경 0 + 행위 보존" 전제. 옵션 C (scheduler.py 11 wrapper 모두 변경) 채택 시 외부 인터페이스 변경 11건 발생 → 사이클 60 §Q5 전제 위반 → 1h verify 부담 폭증.

**실측 데이터 (1.2 결정적 함의 인용)**:
scheduler.py 11 wrapper 모두 `from src.engine import stale_manager` 형태 — facade re-export 21 항목 (11 함수 + 10 상수) 영속이면 wrapper 변경 0 보장. 옵션 C 채택 시 *명백한 회귀 위험* (사이클 60~66 8 사이클 답습 패턴 위반).

**위험 시나리오 (옵션 B/C 채택 시)**:
- 옵션 B (`stale_helpers.py` 신설): 추가 모듈 1 (4 → 5) + 헬퍼 자체가 SoT 분산 위험 + 사이클 67 *행위 보존* 범위 *벗어남* (헬퍼 추출 = 별도 책임). team-leader 의뢰서 §Q1 권고 (옵션 B 는 사이클 71+ 별도 카드) 와 동의.
- 옵션 C (facade 없이 scheduler.py 가 4 sub-module 직접 import): wrapper 11 모두 변경 + 사이클 60 §Q5 push 시점 의무 위반 + 외부 인터페이스 변경 = 사이클 51 답습 패턴 깨짐.

### 트레이드오프
- 채택 시 비용: facade re-export 21 항목 영속 의무 — `stale_manager.py` ~30L `from src.engine.stale_diagnostics import (5 함수 + 4 상수)` + `from src.engine.stale_session_recovery import (3 함수 + 5 상수)` + `from src.engine.stale_universe_guard import (1 함수 + 1 상수)` + `from src.engine.stale_watcher_core import (2 함수)` = 21 항목 명시 re-export.
- 채택 효과: **scheduler.py 11 wrapper 변경 0 보장 (사이클 60~66 8 사이클 답습 패턴 100% 영속) + 78 회귀 가드 patch 경로 갱신 의무 사실상 0 (대다수 patch 가 `scheduler.*` 네임스페이스).**

### 구현 가이드 (backend-dev)

```python
# src/engine/stale_manager.py (재작성, ~30L facade)
"""Facade — 사이클 67 분해 후 4 sub-module 의 통합 진입점 (re-export only).

사이클 60 A1 → 사이클 61 A2 → 사이클 63 A3 → 사이클 66 시정 → 사이클 67 분해.
scheduler.py 11 wrapper 가 `from src.engine import stale_manager` 형태이므로
facade re-export 가 wrapper 변경 0 의무 보장.
"""
from __future__ import annotations

# 상수 re-export (10 상수) — `from src.engine.scheduler import X` re-export 호환 영속
from src.engine.stale_diagnostics import (
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    STALE_FRESHNESS_SECS,
    build_session_subscription_view,
    emit_stale_session_detail,
    refresh_stale_ccnl_cache,
    evict_expired_ccnl,
    prune_force_retry_history,
)
from src.engine.stale_session_recovery import (
    SILENT_INACTIVE_FRESH_RATIO_THRESHOLD,
    SILENT_INACTIVE_MIN_SUBSCRIBED,
    SILENT_INACTIVE_PERSIST_SECS,
    SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR,
    SILENT_INACTIVE_RECOVERY_WINDOW_SECS,
    detect_silent_inactive_sessions,
    force_reconnect_session,
    delta_unsubscribe_dropped,
)
from src.engine.stale_universe_guard import (
    UNIVERSE_LOW_VOLUME_THRESHOLD,
    evaluate_universe_guard,
)
from src.engine.stale_watcher_core import (
    check_and_resubscribe_stale,
    resubscribe_stale_priority,
)

__all__ = [
    # 상수 10
    "MAX_STALE_RETRIES",
    "STALE_FORCE_RETRY_AFTER_SECS",
    "STALE_FORCE_RETRY_HOURLY_CAP",
    "STALE_FRESHNESS_SECS",
    "UNIVERSE_LOW_VOLUME_THRESHOLD",
    "SILENT_INACTIVE_FRESH_RATIO_THRESHOLD",
    "SILENT_INACTIVE_MIN_SUBSCRIBED",
    "SILENT_INACTIVE_PERSIST_SECS",
    "SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR",
    "SILENT_INACTIVE_RECOVERY_WINDOW_SECS",
    # 함수 11
    "build_session_subscription_view",
    "emit_stale_session_detail",
    "refresh_stale_ccnl_cache",
    "evict_expired_ccnl",
    "prune_force_retry_history",
    "detect_silent_inactive_sessions",
    "force_reconnect_session",
    "delta_unsubscribe_dropped",
    "evaluate_universe_guard",
    "check_and_resubscribe_stale",
    "resubscribe_stale_priority",
]
```

### 위험 평가: **LOW**

facade 패턴 = 사이클 51 boot_manager 답습 + 사이클 60~66 누적 8 사이클 검증. 21 항목 re-export 의 누락만 회귀 가드 G-2 가 자동 검증.

---

## 3. Q2 (HIGH) — Q4=B 직접 호출 영속 방식 (sub-module 분해 후 cross-module)

### 답변: **옵션 P1 (직접 import) RECOMMEND** + **변형 권고 (모듈-레벨 import vs 함수-레벨 import)**

### 핵심 추가 권고 — 모듈-레벨 정적 import 채택

사이클 63 Q4=B 시점 `check_and_resubscribe_stale` 본체 마지막 줄:
```python
# Q4=B (사이클 60 답습하지 않는 유일 영역) — 직접 호출 (1 hop 단축, wrapper 우회)
emit_stale_session_detail(scheduler, stale_tickers, now)
```
은 *같은 파일 내 함수 호출* 이라 import 자체 불필요했음. 사이클 67 분해 후 `stale_watcher_core` 가 `stale_diagnostics.emit_stale_session_detail` 호출 = **cross-module call** 로 명시 import 필요.

### 근거 — 트레이더 시각 + 사이클 60/61/63 패턴 일관

**시장 가설**: hot path 360 회/일 (1 회/20초) 에서 *함수-레벨 lazy import* 는 Python 모듈 캐시 (`sys.modules`) 활용으로 latency 영향 0 (~0.5μs). 그러나 *코드 가독성* + *AST 정적 가드 G-5 (import 순환 0)* 검증 용이성 측면에서 **모듈-레벨 정적 import** 가 명백히 우수.

**실전 사례 인용**:
- 사이클 60 A1 `_refresh_stale_ccnl_cache` 본체가 `evict_expired_ccnl(scheduler, ...)` 직접 호출 — *같은 파일 내* 호출. import 자체 불요. = Q4=B 의 원형.
- 사이클 61 A2 `sys.modules.get("src.engine.scheduler")` 패턴 — 단방향 *scheduler 네임스페이스 우회 참조* 의도 (freezegun patch 호환). cross-module call 의 *모듈-레벨 정적 import* 와는 다른 영역.

**Q2 옵션 비교**:

| 옵션 | 패턴 | 장점 | 단점 |
|------|-----|------|------|
| **P1 모듈-레벨 정적 import (권장)** | `from src.engine.stale_diagnostics import emit_stale_session_detail` (파일 상단) | 가독성 + AST 가드 G-5 검증 명시적 + 패턴 일관 (`from src.engine.scanner import KST_TZ, TICK_TR_ID, ticker_last_tick` 답습) | 순환 import 위험 — 옵션 A 단방향 의존이 보장 (`stale_diagnostics` 가 `stale_watcher_core` import 0건 AST 가드) |
| P1' 함수-레벨 lazy import | `def check_and_resubscribe_stale(...): from src.engine.stale_diagnostics import emit_stale_session_detail` | 순환 위험 회피 (모듈 import 순서 무관) | hot path 360 회/일 부담 (모듈 캐시로 무시 가능) + 가독성 ↓ + AST 가드 검증 어려움 |
| P2 sys.modules.get 패턴 | `_diag_mod = sys.modules.get("src.engine.stale_diagnostics"); _diag_mod.emit_stale_session_detail(...)` | 사이클 61/63 freezegun patch 호환 패턴 일관 | cross-module call 의 freezegun 영역 무관 (시각 patch 만 영역) — 패턴 *오용* |
| P3 facade 경유 | `from src.engine.stale_manager import emit_stale_session_detail` | 단일 진입점 일관 | facade 경유 1 hop 추가 + 잠재 순환 (stale_manager → stale_watcher_core → stale_manager) |

### 트레이드오프
- **P1 (모듈-레벨 정적 import)** 채택 시 비용: AST 가드 G-5 (옵션 A 단방향 의존) 가 *반드시 통과* 의무 — `stale_diagnostics.py` 가 `stale_watcher_core` import 0건 AST 검증. 위반 시 순환 import 런타임 에러.
- 채택 효과: K stale watcher 본체 hot path 의 *명시적 import 일관* + AST 정적 가드 명시 검증 + 사이클 60/61/63 코드 패턴 답습 (`from src.engine.scanner import ...` 형태).

### 구현 가이드 (backend-dev)

```python
# src/engine/stale_watcher_core.py (신규)
"""K stale watcher 본체 + 5분 우선 재구독 (사이클 67 분해 후).

사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2442~L2789 이주.
사이클 66 (2026-06-06): cap=10 결함 시정 영속 (Q3 옵션 A WARNING 로그).
사이클 67 (2026-06-06): sub-module 분해 후 stale_diagnostics 직접 import (Q2 옵션 P1).

절대 깨지 말 것:
- WebSocket 4 중 안전망 행위 보존 (F1 + scan_loop + K stale watcher + resubscribe)
- 사이클 29 005935 사고 패턴 영구 차단 (HIGH 종목 cap 밖 잘림 0건)
- Q4=B 영속 (사이클 60 답습하지 않는 유일 영역) — `emit_stale_session_detail` 직접 호출
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

# 사이클 67 Q2 옵션 P1 — cross-module 모듈-레벨 정적 import
# (Q4=B 영속, hot path 360 회/일 라 가독성 + AST G-5 우선)
from src.engine.stale_diagnostics import (
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    STALE_FRESHNESS_SECS,
    emit_stale_session_detail,
)

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)


async def check_and_resubscribe_stale(scheduler: Any) -> None:
    """K stale watcher 본체 — 120s 주기 (사이클 17/28/29-R1/R3 영속)."""
    ...  # 기존 본체 그대로 (사이클 66 시정 영속 + Q4=B 직접 호출)
    emit_stale_session_detail(scheduler, stale_tickers, now)  # Q4=B 영속
```

### 위험 평가: **LOW**

cross-module 정적 import 는 Python 표준 패턴 + 옵션 A 단방향 의존이 순환 위험 사전 차단 + hot path 영향 0.

---

## 4. Q3 (HIGH) — 사이클 60/63/66 영구 가드 영속 의무

### 답변: **옵션 A 채택 RECOMMEND** (4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` 동일 영속)

### 근거 — 사이클 60 I1 hotfix 사례 영속

**실전 사례 인용 — 사이클 60 I1**:
사이클 60 A1 backend-dev Green 초기 구현이 `logger = logging.getLogger(__name__)` 사용 → caplog `set_level(logger="src.engine.scheduler")` 가드가 *silent 누락* → 운영 로그 `[stale_watcher_detail]` 도 누락 위험 발견 → I1 hotfix 도입 `logger = logging.getLogger("src.engine.scheduler")` 명시 binding.

**시장 가설 (운영 logging.yaml 영역)**:
운영 환경 `logging.yaml` (또는 logger 설정) 이 `src.engine.scheduler` 단일 logger 만 명시. sub-module 별 logger (옵션 B) 채택 시 `src.engine.stale_diagnostics` / `src.engine.stale_session_recovery` 등 추가 logger 명시 의무 → 운영 logging 설정 변경 의무 → *별개 배포 변경 영역 동행*.

**위험 시나리오 (옵션 B/C 채택 시)**:
- 옵션 B (sub-module 별 logger): 운영 logging.yaml 변경 4 항목 + caplog 78 회귀 가드 *전수* logger 인자 갱신 의무 (`set_level(logger="src.engine.stale_diagnostics")` 등) — sync-docs 부담 폭증
- 옵션 C (혼합): hot path 만 `src.engine.scheduler` logger, 나머지 sub-module 자체 logger → *일관성 깨짐* + 인지 부담 ↑

### 트레이드오프
- 채택 시 비용: 4 sub-module 모두 *동일* `logging.getLogger("src.engine.scheduler")` 영속 의무 — 회귀 가드 G-6 가 자동 검증
- 채택 효과: 사이클 60 I1 영속 + 78 회귀 가드 caplog 호환 100% 보장 + 운영 logging.yaml 변경 0건 + 운영 로그 prefix 일관 (`[stale_watcher_detail]` / `[stale_priority_resubscribe]` / `[stale_force_retry]` / `[universe_excluded]` / `[silent_inactive_recovery]` 등 모두 `src.engine.scheduler` logger 동일)

### 구현 가이드 (backend-dev)

```python
# 4 sub-module 파일 상단 *동일* (Q3 옵션 A 영속):
import logging
logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 의무
```

### AST 정적 가드 G-6 (신규)

```python
def test_G6_logger_binding_consistency():
    """G-6 (사이클 60 I1 영속): 4 sub-module 모두 logging.getLogger("src.engine.scheduler") 사용."""
    import ast
    from pathlib import Path
    submodules = [
        "src/engine/stale_diagnostics.py",
        "src/engine/stale_session_recovery.py",
        "src/engine/stale_universe_guard.py",
        "src/engine/stale_watcher_core.py",
    ]
    for path in submodules:
        source = Path(path).read_text()
        tree = ast.parse(source)
        # logger = logging.getLogger("src.engine.scheduler") 패턴 검색
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == "logger":
                    if isinstance(node.value, ast.Call):
                        if (
                            isinstance(node.value.func, ast.Attribute)
                            and node.value.func.attr == "getLogger"
                            and len(node.value.args) == 1
                            and isinstance(node.value.args[0], ast.Constant)
                            and node.value.args[0].value == "src.engine.scheduler"
                        ):
                            found = True
                            break
        assert found, f"{path}: logger = logging.getLogger('src.engine.scheduler') 누락 (사이클 60 I1 영속 위반)"
```

### 위험 평가: **HIGH (영속 위반 시 silent 결함, 사이클 60 I1 사례 답습)**

옵션 A 채택 시 위험 0 + G-6 AST 가드로 자동 검증. 옵션 B/C 채택 시 사이클 60 I1 hotfix 답습 부담 4 배 (4 sub-module 모두 검증 의무) + 운영 logging.yaml 변경 부담.

---

## 5. Q4 (MEDIUM) — 회귀 가드 78 케이스 patch 경로 갱신 전략

### 답변: **옵션 B (facade patch 영속) 채택 RECOMMEND** (실측 데이터 근거)

### 근거 — 1.2 결정적 함의 인용

**실측 데이터**:
- `patch("src.engine.stale_manager.*")` 형태 patch 가 78 회귀 가드에서 **0건** (실측)
- `patch("src.engine.scheduler.*")` 형태 (kis_ws/kis_ws_pool/datetime/write_log) 가 압도적 다수 — sub-module 분해 영향 0 (sub-module 함수가 `sys.modules.get("src.engine.scheduler")` 패턴으로 동일 객체 참조)
- caplog `set_level(logger="src.engine.scheduler")` 도 옵션 A (Q3 4 sub-module 동일 logger) 채택 시 영향 0

**Q4 옵션 비교 재평가**:

| 옵션 | 영향 영역 | 비용 |
|------|---------|------|
| **B (facade patch 영속, 권장)** | patch 경로 갱신 의무 거의 0 (실측 0건) | 0 |
| A (sub-module 직접 patch 갱신) | 0 → 다수 갱신 (예방 차원) | 신규 patch 경로 명시 필요 |
| C (양쪽 호환) | 복잡도 ↑ | 양쪽 export + 정합성 검증 부담 |

**team-leader 의뢰서 §Q4 권고 (옵션 A) 와의 차이**:
team-leader 의뢰서는 *명확성 + 사이클 60 hotfix 답습* 근거로 옵션 A 권고. 그러나 **실측 patch 0건** 이므로 옵션 A 채택 시 *새 patch 경로 작성 부담* 만 발생. **옵션 B 채택이 정합** (`patch("src.engine.stale_manager.*")` 가 0건이라 facade 보존 자체로 호환).

다만 *예외 영역* 1건: **사이클 66 K-10 회귀 가드** (`caplog set_level(..., logger="src.engine.stale_manager")` 1 case) — 사이클 66 시정 본체가 `stale_watcher_core` 로 이주하므로 logger binding 만 영속 (Q3 옵션 A) 하면 호환 — 하지만 **신중하게 caplog logger 인자도 갱신 권고** (1 case 만):
```python
# 사이클 66 K-10 (test_cycle66_resubscribe_cap_priority_fix.py L439)
# 분해 후 logger binding 명시 위치:
caplog.set_level("WARNING", logger="src.engine.scheduler")
# (사이클 67 분해 후 stale_watcher_core 의 logger = logging.getLogger("src.engine.scheduler") 영속)
```

### 트레이드오프
- 채택 시 비용: 사이클 66 K-10 caplog logger 인자 1 case 갱신 (`stale_manager` → `scheduler`, 단 Q3 옵션 A 영속이라 sub-module 분해 *전부터* `scheduler` 였어야 함 — 실은 *기존 결함 보강*)
- 채택 효과: 78 회귀 가드 patch 경로 갱신 의무 사실상 0 + 사이클 60 hotfix 부담 0 + flakiness 3 회 RE-RUN 부담 78 → 78 동일 (영향 0)

### Q4 silent 결함 영구 차단 가드 권고 (신규)

team-leader 의뢰서 §Q4 옵션 B 가 *facade reference 와 sub-module 정의 분리* 위험 인지. 본 답변은 옵션 B 채택이지만 *예외 영역 검증* 신규 가드 권고:

**신규 G-16 (옵션 B 안전선 가드)**: `patch("src.engine.stale_manager.X")` 가 *향후 누군가 추가* 할 때 silent 무효화 위험 차단.
```python
def test_G16_no_patch_via_stale_manager_facade():
    """G-16 (사이클 67 신규): `patch("src.engine.stale_manager.X")` 패턴 사용 0건 AST 검증.

    사용 시 facade reference 만 변경, sub-module 정의 미변경 → silent 결함.
    sub-module 직접 patch 강제 (옵션 A 채택자만, 옵션 B 채택 시는 이 가드 비활성).

    옵션 B 채택 시 본 가드는 *향후* `patch("src.engine.stale_manager.*")` 사용 차단 의무.
    """
    import ast
    from pathlib import Path
    test_root = Path("tests")
    violations = []
    for test_file in test_root.rglob("test_*.py"):
        source = test_file.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # patch("src.engine.stale_manager.X") 패턴 검색
                if (
                    isinstance(node.func, ast.Name) and node.func.id == "patch"
                    and len(node.args) >= 1
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value.startswith("src.engine.stale_manager.")
                    and not node.args[0].value.startswith("src.engine.stale_manager.")  # facade re-export 모듈 변수 제외
                ):
                    violations.append(f"{test_file}: {node.args[0].value}")
    assert not violations, (
        f"`patch('src.engine.stale_manager.X')` 패턴 발견 — "
        f"facade reference 만 변경, sub-module 정의 미변경 → silent 결함 위험. "
        f"sub-module 직접 patch 권고 (예: patch('src.engine.stale_diagnostics.X')). "
        f"위반: {violations}"
    )
```

### 위험 평가: **LOW**

실측 patch 0건 + G-16 신규 가드로 향후 silent 결함 영구 차단 + caplog 1 case 만 영향 (Q3 옵션 A 영속으로 자연 호환).

---

## 6. Q5 (MEDIUM) — scheduler.py wrapper lazy import 경로

### 답변: **옵션 A 채택 RECOMMEND** (facade 유지, scheduler.py 11 wrapper 변경 0)

### 근거 — Q1 옵션 A 자연 귀결

Q1 옵션 A 채택 시 facade re-export 21 항목 영속 → scheduler.py 11 wrapper 가 `from src.engine import stale_manager; await stale_manager.check_and_resubscribe_stale(self)` 형태 *그대로 작동* (변경 0).

**실측 데이터**:
scheduler.py 11 wrapper 모두 `from src.engine import stale_manager` 형태 (사이클 60 첫 도입부터 사이클 66 영속). 옵션 B/C 채택 시 wrapper 11 모두 변경 → 외부 인터페이스 변경 → 사이클 60 §Q5 영속 의무 위반.

### 트레이드오프
- 채택 시 비용: 0 (변경 0)
- 채택 효과: 사이클 60~66 8 사이클 답습 패턴 100% 영속 + scheduler.py 무변경 보장 + 회귀 가드 G-4 (wrapper lazy import 작동) RE-RUN PASS 자동

### 위험 평가: **LOW**

옵션 A 자연 채택 + G-4 회귀 가드 자동 검증.

---

## 7. Q6+ 신규 발의 (team-leader 가 놓친 위험 영역)

### Q6-1 (LOW) — hot path import 캐시 측정 권고

**답변**: **CONSIDER (별도 측정 + 가드 추가 권고)**

**근거 (트레이더 시각)**:
Q2 옵션 P1 (모듈-레벨 정적 import) 채택 시 `stale_watcher_core` 가 import 시점 `stale_diagnostics` 도 로드. *첫 호출* 시 두 모듈 모두 import 완료 → `sys.modules` 캐시 → 이후 호출 latency 영향 0. 그러나 *컨테이너 재시작 직후 첫 K stale watcher 사이클* (120s 후) 에 4 sub-module + scheduler.py 모두 import 발생 → cold start latency 측정 권고.

**구현 가이드 (tester)**:
```python
def test_Q6_1_cold_start_import_latency():
    """Q6-1 신규: 4 sub-module import latency 측정 (cold start 시점)."""
    import sys
    import time

    # sys.modules 에서 4 sub-module + facade 제거 (cold start 재현)
    for mod in [
        "src.engine.stale_manager",
        "src.engine.stale_diagnostics",
        "src.engine.stale_session_recovery",
        "src.engine.stale_universe_guard",
        "src.engine.stale_watcher_core",
    ]:
        sys.modules.pop(mod, None)

    start = time.perf_counter()
    from src.engine import stale_manager  # noqa
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 100ms 이하 권고 (운영 환경 _boot 영향 0)
    assert elapsed_ms < 100, f"4 sub-module import latency {elapsed_ms:.1f}ms — _boot 영향 평가 필요"
```

**위험 평가**: **LOW** — Python import 캐시는 안정적, 측정만 권고. cold start 외 운영 영향 0.

---

### Q6-2 (MEDIUM) — 사이클 71+ 옵션 B 헬퍼 사전 설계 문서화

**답변**: **RECOMMEND (별도 문서화 권고, 사이클 71+ 발의 청사진)**

**근거 (트레이더 시각)**:
team-leader 의뢰서 §Q1 옵션 B (`stale_helpers.py` 신설) 가 사이클 71+ 별도 카드 분리 권고. 그러나 사이클 67 분해 후 4 sub-module 의 *중복 패턴* 이 명확해지면 옵션 B 의 필요성이 명확해짐. 본 자문 시점에 **사전 설계 청사진** 문서화 권고.

**예상 헬퍼 영역** (3 항목):

1. **`_sched_mod_get()` 헬퍼**: `sys.modules.get("src.engine.scheduler")` 패턴 (사이클 61 A2 도입 → 사이클 63 A3 확장) = 현재 4 sub-module 중 `stale_session_recovery` / `stale_universe_guard` / `stale_watcher_core` 3 모듈에서 *동일 패턴 4회 중복*. `_get_sched_datetime()` / `_get_sched_kis_ws_pool()` 등 4~5 헬퍼로 통합 가능 (~50L).
2. **`_collect_high_tickers(scheduler)` 헬퍼**: `try/except 4중 가드` 패턴 (`registry.all() → positions.keys()` + `_pending_next_day_clear` 합집합) = `stale_watcher_core` 의 `check_and_resubscribe_stale` (L820-833) + `resubscribe_stale_priority` (L1030-1043) 양쪽 *동일 패턴*. ~15L 추출 가능.
3. **`_write_log_fire_and_forget(level, msg)` 헬퍼**: `try/except + write_log + logger.debug` 패턴 = 4 sub-module 모두 *동일 패턴* (~7L × 다수). ~10L 헬퍼화.

**구현 가이드 (refactor-expert)**:
- 사이클 71+ 카드 발의 시점: 사이클 67 push 후 1 주 운영 검증 통과 후
- 분리 대상 모듈: `src/engine/stale_helpers.py` (~75L)
- 의존 방향: `stale_helpers` 가 4 sub-module 어디서도 import 0건 (단순 유틸 함수만)
- 회귀 가드: 4 sub-module 모두 헬퍼 import 후 *행위 보존* 검증 (사이클 60 hotfix 답습)

**위험 평가**: **MEDIUM** — 사이클 71+ 발의 시 사이클 67 분해의 *2 차 검증 부담*. 단, 운영 검증 1 주 통과 후 발의면 안전.

---

### Q6-3 (HIGH) — 사이클 65 후보 풀 폭축 회고와 시점 충돌 평가

**답변**: **CONSIDER (회고 시점 분리 권고)**

**근거 (트레이더 시각)**:
사이클 65 (2026-06-06 가격 + 거래대금 동행 필터) 의 **2 주 회고** (카드 #16, MEDIUM) 가 사이클 68+ 발의 예정. 사이클 65 = scanner 단계 필터 폭축 (가격 + 거래대금 동시 적용) → 운영 데이터 측정 의무 (`_apply_price_filter` / `_apply_trade_amount_filter` 의 funnel snapshot step_no=97 + 98).

**시점 충돌 위험**:
- 사이클 67 분해 (2026-06-07 push 권장) → 사이클 68+ 카드 #16 발의 시점 = **사이클 65 운영 1~2 주 후 (2026-06-13 ~ 2026-06-20)**
- 그 시점에 사이클 67 분해 후 *2 주 운영 검증* 도 미완료 — *2 사이클 동시 검증* 부담

**구현 가이드**:
- 사이클 67 분해 후 *1 주 운영 검증* 통과 (2026-06-13 까지) 후 카드 #16 (사이클 65 회고) 발의 권고
- 만약 사이클 65 운영 결함 *조기 발견* (예: 우량주 회피율 50% 이상) → 카드 #16 우선 발의 + 사이클 67 *2 주 운영 검증* 후 카드 #14 (옵션 B 헬퍼) 발의
- **현재 권고**: 사이클 67 → (1 주 운영) → 사이클 68+ 카드 #16 → (1 주 운영) → 사이클 71+ 카드 #15 (Q6-2 옵션 B 헬퍼). 3 사이클 시간 분산으로 *각 사이클 운영 검증* 보장.

**위험 평가**: **MEDIUM** — 시점 분리 권고. 동시 진행 시 *bisect 어려움 + 회고 결과 해석 복잡도 ↑*.

---

## 8. 회귀 가드 G-1~G-15 청사진 (team-leader 의뢰서 §5.1 답습) + 신규 G-16/G-17

### 8.1 의무 가드 청사진 (G-1~G-15 team-leader 채택)

| # | 카테고리 | 가드 형태 | 신규/답습 |
|---|---------|---------|-----------|
| G-1 | 4 sub-module import sanity | `from src.engine.stale_diagnostics import (5 함수 + 4 상수)` 등 4 sub-module 전수 | 사이클 61 답습 |
| G-2 | facade re-export 보존 | `from src.engine.stale_manager import *` 후 11 함수 + 10 상수 전수 | 사이클 60/61/63 답습 |
| G-3 | scheduler.py wrapper 시그너처 0 변경 | AST 정적 가드: 11 wrapper signature hash 비교 | 사이클 60 G-3 답습 |
| G-4 | scheduler.py 위임 lazy import 작동 | `from src.engine import stale_manager` 후 모든 함수 `getattr` 성공 | 사이클 60/61/63 답습 |
| G-5 | import 순환 0 (AST) | `stale_diagnostics` 가 `stale_session_recovery` / `stale_universe_guard` / `stale_watcher_core` import 0건 (AST grep) | 신규 (옵션 A 단방향) |
| G-6 | logger binding 영속 | `logging.getLogger("src.engine.scheduler")` — 4 sub-module 모두 | 사이클 60 I1 영속 |
| G-7 | `sys.modules.get("src.engine.scheduler")` 패턴 영속 | `stale_watcher_core` / `stale_session_recovery` 가 freezegun patch 호환 | 사이클 61 D-2 답습 |
| G-8 | 사이클 60 18 회귀 가드 RE-RUN PASS | 분해 후 18/18 PASS (patch 경로 영향 0 실측) | 사이클 60 hotfix 답습 |
| G-9 | 사이클 61 20 회귀 가드 RE-RUN PASS | 분해 후 20/20 PASS | 사이클 60 hotfix 답습 |
| G-10 | 사이클 63 29 회귀 가드 RE-RUN PASS | 분해 후 29/29 PASS (Q4=B 영속 검증) | 사이클 60 hotfix 답습 |
| G-11 | 사이클 66 11 회귀 가드 RE-RUN PASS | `resubscribe_stale_priority` 이주 후 영속 + AST priority 분리 *후* cap | 사이클 66 영속 |
| G-12 | 4 sub-module 라인 cap | stale_diagnostics ≤ 400 / stale_session_recovery ≤ 320 / stale_universe_guard ≤ 200 / stale_watcher_core ≤ 380 | 신규 |
| G-13 | Q4=B 직접 호출 영속 | `check_and_resubscribe_stale` 본체 마지막 `emit_stale_session_detail(scheduler, ...)` 직접 호출 AST 검증 | 사이클 63 영속 |
| G-14 | 상수 SoT 분산 차단 | 10 상수 각각 정의 정확히 1 sub-module 만 (`grep MAX_STALE_RETRIES = ` count == 1) | 신규 |
| G-15 | scheduler.py L92 re-export 호환 | `from src.engine.stale_manager import (5 상수)` 영속 | 사이클 60 A1 영속 |

### 8.2 신규 G-16/G-17 (본 자문 권고)

| # | 카테고리 | 가드 형태 | 사유 |
|---|---------|---------|------|
| **G-16** | facade patch silent 결함 차단 | `patch("src.engine.stale_manager.X")` 패턴 *향후 사용* AST 0건 검증 (Q4 옵션 B 안전선) | Q4 옵션 B 채택 시 향후 silent 결함 영구 차단 |
| **G-17** | priority 분리 *후* cap 영속 AST (사이클 66 영속) | `resubscribe_stale_priority` 본체에서 `stale_tickers[:cap]` 패턴 0건 + `low_targets[:max(0, cap - len(high_targets))]` 패턴 1건 AST 검증 | 사이클 66 시정 본체가 `stale_watcher_core` 로 이주 후 AST 가드 위치 보존 |

### 8.3 카테고리 분리 측정 + flakiness 3 회

사이클 60 hotfix 패턴 답습 의무:
- pytest 카테고리 분리 측정 (`pytest --collect-only -q` 4 sub-module 별 회귀 가드 분포)
- flakiness 3 회 (동일 회귀 가드 3 회 RE-RUN 후 모두 PASS — order independence)
- **신규 측정 지표**: 4 sub-module 영역별 케이스 분포 — `stale_diagnostics` (~18 + G-1/G-2/G-6/G-7) / `stale_session_recovery` (~20 + G-1/G-6/G-7) / `stale_universe_guard` (~5 + G-1/G-6) / `stale_watcher_core` (~40 + G-1/G-6/G-7/G-13/G-17) 분포 균형 확인

---

## 9. 종합 권고 매트릭스 (team-leader 채택 결정 시 참조)

| 의제 | 본 자문 권고 | team-leader 1차 권고 | 일치/차이 | 위험 |
|------|----------|------------------|----------|------|
| **Q1** import 의존성 방향 | **옵션 A (facade 단방향)** | 옵션 A | 100% 일치 | LOW |
| **Q2** Q4=B cross-module import | **옵션 P1 (모듈-레벨 정적 import)** | 옵션 P1 | 100% 일치 + 변형 권고 (함수-레벨 lazy import 비채택) | LOW |
| **Q3** 영구 가드 영속 | **옵션 A (4 sub-module 동일 logger)** | 옵션 A | 100% 일치 + G-6 AST 가드 신규 | HIGH (영속 위반 시 silent) |
| **Q4** patch 경로 갱신 | **옵션 B (facade patch 영속)** | 옵션 A | **불일치 — 실측 데이터 근거 옵션 B 강력 권고** | LOW |
| **Q5** scheduler.py wrapper | **옵션 A (facade 유지, 변경 0)** | 옵션 A | 100% 일치 | LOW |
| **Q6-1** hot path import 캐시 | **CONSIDER (측정 권고)** | (신규 발의) | 신규 — cold start latency 측정 | LOW |
| **Q6-2** 사이클 71+ 옵션 B 헬퍼 | **RECOMMEND (사전 설계 청사진)** | (사이클 71+ 후속 카드) | 신규 — 3 헬퍼 영역 명시 | MEDIUM |
| **Q6-3** 사이클 65 회고 시점 충돌 | **CONSIDER (시점 분리 권고)** | (신규 발의) | 신규 — 1 주 운영 검증 후 카드 #16 발의 | MEDIUM |
| **G-1~G-15** 회귀 가드 청사진 | **채택 + G-16/G-17 신규 추가** | G-1~G-15 청사진 | 채택 + 2 신규 가드 | — |

### 9.1 핵심 메시지

본 자문 = **사이클 60~66 8 사이클 누적 패턴의 *완벽한 자연 귀결*** + **유일한 새 결정 영역 = Q4 patch 경로 (실측 데이터 근거 옵션 B 권고, team-leader 1차 옵션 A 와 차이)**.

K stale watcher 본체 영역 보존 평가:
- **사이클 29 005935 사고 영역** (`resubscribe_stale_priority` cap=10 결함) → 사이클 66 시정 본체가 `stale_watcher_core` 로 이주 후 *AST 가드 G-17 (priority 분리 *후* cap)* 로 영속 보장. 회귀 위험 0.
- **K stale watcher 360 회/일 hot path** → Q1 옵션 A + Q2 옵션 P1 + Q3 옵션 A 채택 시 *행위 변경 0 + 외부 인터페이스 변경 0* 보장. 회귀 위험 LOW.
- **Q4=B 직접 호출 영속** → Q2 옵션 P1 (모듈-레벨 정적 import) + G-13 AST 가드 (`emit_stale_session_detail(scheduler, ...)` 호출 검증) 로 영속 보장.

---

## 10. 우선순위 결정 (사용자 결정 요청)

다음 순서로 사용자에게 결정 요청 권고:

1. **최우선 (사용자 명시 결정 의무)**: **Q4 옵션 A vs B** — team-leader 1차 옵션 A (sub-module 직접 patch 갱신) vs 본 자문 옵션 B (facade patch 영속). **실측 patch 0건 근거 옵션 B 강력 권고** 이나 사용자가 *명시성 우선* 시 옵션 A 도 안전.
2. **차순위 (사용자 명시 결정 권고)**: **Q6-2 사이클 71+ 옵션 B 헬퍼 사전 설계 청사진** — 본 자문 응답서 §7 Q6-2 영역을 사이클 71+ 카드 발의 시점에 활용할지 결정.
3. **차차순위 (사용자 인지만)**: **Q6-3 사이클 65 회고 시점 분리** — 사이클 67 push → 1 주 운영 → 사이클 68+ 카드 #16 → 1 주 운영 → 사이클 71+ 카드 #15 (Q6-2 헬퍼). 시점 분리 권고.
4. **자동 진행 (사용자 결정 불요)**: Q1/Q2/Q3/Q5/G-1~G-15 + G-16/G-17 — 8 사이클 답습 + 신규 가드 자동 진행.

---

## 11. CLAUDE.md 절대 규칙 보호 체크리스트 (재확인)

본 자문 권고가 다음 절대 규칙을 *깨지 않음* 명시:

- [x] 체결통보 구독 (H0STCNI0/H0STCNI9) 영역 무관 (본 카드 외)
- [x] uvicorn 단일 워커 영향 0
- [x] **WebSocket 4 중 안전망** F1 + scan_loop + **K stale watcher (stale_watcher_core)** + **`resubscribe_stale_priority` (stale_watcher_core)** — 행위 보존 + 회귀 가드 15+2 케이스
- [x] **K stale watcher 우선순위 분리** (HIGH/LOW) — G-13 영속 + G-17 AST 가드 (사이클 66 시정 영속)
- [x] **stale watcher force_retry** (사이클 29-R1) — G-10 RE-RUN PASS (29/29)
- [x] **silent inactive 시간당 세션당 2회 cap** — G-9 RE-RUN PASS (20/20, sub-module 분리 후 cap dict 모듈 전역 → 동일 instance 영속)
- [x] **stale universe 가드** (보유/익일청산 절대 보호) — G-9 RE-RUN PASS (20/20)
- [x] `_reset_daily_state` 동행 reset — G-8/G-9/G-10 RE-RUN PASS
- [x] KST 강제 — `KST_TZ` import 영속 (4 sub-module 모두)

---

## 12. 후속 검증 권고 (tdd-engineer / tester / refactor-expert)

### tdd-engineer Red 발주 시
- 회귀 가드 G-1~G-17 (17 케이스) Red 작성
- **G-6 (logger binding) HIGH 우선** + G-17 (priority 분리 후 cap AST) HIGH + G-13 (Q4=B 영속) HIGH
- 78 회귀 가드 patch 경로 *영향 0* 실측 확인 (옵션 B 채택 시)

### tester Verify 시
- 백엔드 ~1984 → ~2001 PASS 목표 (+17)
- **flakiness 3 회 반복 의무** (사이클 58 V-2 / 60 / 61 / 63 / 66 답습)
- **월요일 (2026-06-08) 1h tester verify 시나리오 A/B/C/D 결합** 의무 (사이클 66 영속) — sub-module 분해 후 4 sub-module 모두 운영 환경 *행위 보존* 정량 측정 (HIGH 5분 우선 재구독 보장률 100% / WARNING 발화 빈도 / HIGH 회복 시간 ≤5분)
- **카테고리 분리 측정**: 4 sub-module 영역별 회귀 가드 분포 균형 확인 (`stale_watcher_core` 가 ~40 케이스로 가장 많음, 다른 3 sub-module 각각 ~10~20)

### refactor-expert 후속
- 사이클 67 분해 후 1 주 운영 검증 통과 시 **Q6-2 사이클 71+ 카드 #15 발의** (옵션 B 공통 헬퍼 `stale_helpers.py` ~75L)
- **Q6-3 사이클 68+ 카드 #16 발의 시점**: 사이클 67 push 후 1 주 운영 검증 + 사이클 65 운영 1~2 주 후 동시 만족 시점

### domain-expert 후속 자문 (필요 시)
- **Q4 옵션 A vs B 사용자 결정 시점**: 본 자문 §10 영역 결정. 사용자가 옵션 A 채택 시 patch 경로 *전수 갱신* 부담 + flakiness 3 회 RE-RUN 부담 정량 평가 권고
- **Q6-2 옵션 B 헬퍼 분리 시점**: 사이클 71+ 발의 시 *3 헬퍼 영역 합리성* 별도 자문 요청 권고

---

## 자문 종료

**자문 종료**. team-leader 가 사용자 채택 결정 후 tdd-engineer Red 발주 권고.

**산출물 경로**: `/Users/koscom/Projects/auto_stock/_workspace/cycle67_stale_manager_decomposition_domain_response.md`

**1줄 요약**: 5 의제 모두 RECOMMEND (Q1/Q2/Q3/Q5 옵션 A team-leader 일치, **Q4 옵션 B 실측 데이터 근거 권고 — team-leader 1차 와 차이**) + Q6+ 신규 발의 3 (Q6-1 import 캐시 측정, Q6-2 사이클 71+ 옵션 B 헬퍼 청사진, Q6-3 사이클 65 회고 시점 분리) + G-1~G-15 채택 + 신규 G-16/G-17 보강 권고. 사이클 60~66 8 사이클 답습 패턴의 완벽한 자연 귀결.
