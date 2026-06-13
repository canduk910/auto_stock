# 사이클 127 — Red 명세: 종목마스터 3 작업 fire-and-forget + 진행 가시화 통일

**작성일**: 2026-06-13 (토)
**위급도**: HIGH (사용자 보고 = 클라이언트 timeout silent 결함)
**범위**: 백엔드 (state 모듈 신규 + 3 once 함수 진행 emit + 3 POST 라우트 fire-and-forget 전환 + GET /refresh-progress) + 프론트 (RefreshProgressBanner + types/api + StockMaster.tsx 통합)

---

## 1. 사용자 보고 + 결정

**사용자 보고**: 사이클 126 push 후 UI "기본정보 새로고침" 클릭 → 13분 39초 후 토스트 "KIS API 일시 결함 — 잠시 후 재시도". 운영 로그 = 백엔드 정상 완료 (updated=2697/2697, failed=0). 결함 = **axios 클라이언트 디폴트 타임아웃** = silent 결함 영구 차단 의무.

**사용자 결정**:
| 의제 | 결정 |
|------|------|
| Q1 폴링 방식 | **5초 주기 폴링** (경량) — fire-and-forget + GET /progress |
| Q2 UI 형태 | **상단 배너 + 상세 카운터** |
| Q3 확장 범위 | **3 작업 모두 통일** — refresh-universe(사이클 90) + basics/refresh(사이클 126) + daily/refresh(사이클 126) |

---

## 2. 배경 — 현재 패턴 (사이클 90/126)

3 POST 라우트 모두 동일 구조:
- `_refresh_*_lock = asyncio.Lock()` 모듈 전역
- `if _lock.locked(): 409 Conflict` 진입 가드
- `async with _lock:` 안에서 `await _*_once()` 동기 호출
- once 함수: 페이징 + KIS 호출 + Rate Limit 50ms sleep + summary dict 반환 (3~14분 소요)
- 클라이언트가 응답까지 대기 → axios 디폴트 timeout 초과 (브라우저 환경 따라 다름)

**진짜 결함**: 백엔드는 정상 완료하나 클라이언트가 응답을 못 받음 + 진행 가시화 0건.

---

## 3. 시정 영역 (백엔드 4 영역 + 프론트 3 영역 + AST 가드)

### 3.1 백엔드 — refresh_progress 모듈 신규

**파일 신규**: `src/engine/refresh_progress.py`

```python
"""사이클 127 — 종목마스터 3 작업 (universe/basics/daily) 진행 state 메모리 dict.

fire-and-forget POST 라우트 + 5초 폴링 GET 라우트 패턴.
3 작업 모두 동일 schema 영속 (Q3=A 통일).

매매 안전성 무영향: scanner 단계 매수 진입 *전* 영역만, hot path 무관.
"""

from __future__ import annotations

import threading
from typing import Literal

from src.db._kst import now_kst_iso

ProgressStatus = Literal["idle", "running", "completed", "failed"]
TaskKey = Literal["universe", "basics", "daily"]

# 3 작업별 in-memory state (process-local, uvicorn 단일 워커 영속 의무 - CLAUDE.md "절대 깨지 말 것")
_state_lock = threading.Lock()
_progress: dict[str, dict] = {
    "universe": {
        "status": "idle",
        "total": 0,
        "processed": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "started_at": None,
        "finished_at": None,
        "elapsed_ms": 0,
        "error_message": None,
    },
    "basics": {...같은 schema...},
    "daily": {...같은 schema...},
}


def start_progress(task_key: TaskKey, total: int) -> None:
    """작업 시작 시 호출. 기존 state 초기화 + status=running."""


def update_progress(task_key: TaskKey, **kwargs) -> None:
    """페이징/배치 중간 호출. processed/updated/skipped/failed 누적 갱신."""


def finish_progress(task_key: TaskKey, status: ProgressStatus, **kwargs) -> None:
    """완료/실패 시 호출. finished_at + elapsed_ms 자동 계산 + error_message 옵션."""


def get_progress(task_key: TaskKey) -> dict:
    """단일 작업 state 조회 (deep copy 반환)."""


def get_all_progress() -> dict[str, dict]:
    """3 작업 통합 state 조회 (GET /refresh-progress 응답)."""


def is_running(task_key: TaskKey) -> bool:
    """409 Conflict 판정용."""
```

**회귀 가드 영역** (`tests/unit/engine/test_cycle127_refresh_progress_state.py`):
- **G-STATE1**: 모듈 import + 3 작업 dict 초기 schema (10 키 정확) (3 sub)
- **G-STATE2**: start_progress() 호출 시 status="running" + started_at KST + total 갱신
- **G-STATE3**: update_progress() 누적 갱신 (processed/updated/skipped/failed)
- **G-STATE4**: finish_progress("completed") + finished_at KST + elapsed_ms ≥ 0
- **G-STATE5**: finish_progress("failed", error_message=str) 정합
- **G-STATE6**: is_running() True/False 정합
- **G-STATE7**: thread-safety (threading.Lock 영속, 동시 호출 race 차단)
- **G-STATE8**: get_progress() deep copy 반환 (외부 mutation 차단)

### 3.2 백엔드 — 3 once 함수 진행 state 통합

**파일**: `src/engine/scanner.py`

(1) `_full_universe_load_once(force: bool = False)` (L1579):
- 함수 시작 시 `start_progress("universe", total=0)` (total은 페이징 후 갱신)
- KRX 페이징 후 `update_progress("universe", total=N)`
- CTPF1002R 페이징 루프 (사이클 101) — 100건 batch 마다 `update_progress("universe", processed=k, updated=l, skipped=m, failed=n)` (기존 emit 영역 답습)
- 정상 완료: `finish_progress("universe", "completed", **summary)`
- 예외: try/except → `finish_progress("universe", "failed", error_message=str(exc))` + re-raise

(2) `_stock_master_basics_refresh_once(force: bool = False)` (L2208):
- 함수 시작: `start_progress("basics", total=N)` (universe 적재 후 즉시 알수 있음)
- 500건 batch emit 영역 (사이클 126) 에 `update_progress("basics", processed=k, updated=l, skipped=m, failed=n)` 추가
- 완료/실패 동일

(3) `_stock_master_daily_load_once(force: bool = False)` (L2049):
- 동일 패턴 (사이클 122 daily task)

**회귀 가드 영역** (`tests/unit/engine/test_cycle127_once_progress_integration.py`):
- **G-INT-U1**: `_full_universe_load_once` 호출 시 `start_progress("universe", ...)` 호출 (mock)
- **G-INT-U2**: 중간 emit 영역 에 `update_progress("universe", ...)` 호출 (mock)
- **G-INT-U3**: 정상 완료 시 `finish_progress("universe", "completed", ...)` 호출
- **G-INT-U4**: 예외 시 `finish_progress("universe", "failed", error_message=str(exc))` + re-raise
- **G-INT-B1~B4**: basics 동일 패턴
- **G-INT-D1~D4**: daily 동일 패턴

### 3.3 백엔드 — 3 POST 라우트 fire-and-forget 전환

**파일**: `src/routes/stock_master.py`

기존 (사이클 90/126) 동기 패턴:
```python
async with _refresh_universe_lock:
    summary = await _full_universe_load_once(force=force)
    return ApiResponse(success=True, data={...summary}, message=...)
```

신규 (사이클 127) fire-and-forget:
```python
from src.engine import refresh_progress as _rp

if _rp.is_running("universe"):
    raise HTTPException(status_code=409, detail="universe refresh 진행 중 — 잠시 후 재시도")

async def _background_task():
    try:
        await _full_universe_load_once(force=force)
        # finish_progress는 once 함수 내부에서 호출됨
    except Exception:
        logger.exception("[refresh_universe_now] 백그라운드 작업 실패")

asyncio.create_task(_background_task())

return ApiResponse(
    success=True,
    data={"status": "started", "task_key": "universe"},
    message="universe refresh 시작 — 진행 상황은 /refresh-progress 폴링",
)
```

**3 라우트 모두 동일 패턴**. `asyncio.Lock` 폐기 (state.is_running()이 lock 역할 영속).

### 3.4 백엔드 — GET /refresh-progress 신규 라우트

```python
@router.get("/refresh-progress")
async def get_refresh_progress():
    """사이클 127 — 3 작업 진행 state 통합 조회.

    5초 주기 폴링 영역 (Q1=A). 사이클 84 L-2 READ-ONLY GET 정합.
    """
    from src.engine import refresh_progress as _rp
    return ApiResponse(
        success=True,
        data=_rp.get_all_progress(),
        message="",
    )
```

**회귀 가드 영역** (`tests/unit/routes/test_cycle127_progress_routes.py`):
- **G-ROUTE-U1**: POST /refresh-universe — 202 status (또는 200 + status=started) + task_key="universe"
- **G-ROUTE-U2**: POST /refresh-universe — running 시 409 Conflict
- **G-ROUTE-U3**: POST /refresh-universe — asyncio.create_task 호출 (mock)
- **G-ROUTE-U4**: POST /refresh-universe — 응답 즉시 반환 (long-running 차단 = pytest timeout 5초 내)
- **G-ROUTE-B1~B4**, **G-ROUTE-D1~D4**: 동일 패턴
- **G-ROUTE-GET1**: GET /refresh-progress — 3 작업 통합 응답 + 10 키 schema 정합
- **G-ROUTE-GET2**: GET /refresh-progress — graceful (state 빈 시 idle 디폴트)

### 3.5 AST 영구 가드

**파일** (`tests/unit/ast/test_cycle127_ast_progress_hooks.py`):
- **G-AST1**: `src/engine/scanner.py` — `_full_universe_load_once` 본체에 `start_progress("universe"` + `finish_progress("universe"` 호출 영구 검증
- **G-AST2**: 동일 — `_stock_master_basics_refresh_once` 본체에 `start_progress("basics"` + `finish_progress("basics"`
- **G-AST3**: 동일 — `_stock_master_daily_load_once` 본체에 `start_progress("daily"` + `finish_progress("daily"`
- **G-AST4**: `src/routes/stock_master.py` — `asyncio.create_task` 호출 3개 (universe/basics/daily 백그라운드)
- **G-AST5**: 동일 — `_refresh_universe_lock`, `_refresh_basics_lock`, `_refresh_daily_lock` 모듈 전역 변수 영구 폐기 (state 기반 전환 영속)
- **G-AST6**: 사이클 84 L-2 화이트리스트 (POST 3 + GET 1=refresh-progress 추가)

### 3.6 프론트 — types + API

**파일**: `frontend/src/types/stock-master.ts` (+):
```typescript
export type RefreshTaskKey = "universe" | "basics" | "daily";
export type RefreshStatus = "idle" | "running" | "completed" | "failed";

export interface RefreshProgress {
  status: RefreshStatus;
  total: number;
  processed: number;
  updated: number;
  skipped: number;
  failed: number;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number;
  error_message: string | null;
}

export interface AllRefreshProgress {
  universe: RefreshProgress;
  basics: RefreshProgress;
  daily: RefreshProgress;
}

// 사이클 127 — fire-and-forget 202 응답
export interface RefreshStartedResponse {
  status: "started";
  task_key: RefreshTaskKey;
}
```

**파일**: `frontend/src/api/stock-master.ts` (+):
- `fetchRefreshProgress(): Promise<AllRefreshProgress>` — GET /refresh-progress
- 기존 `refreshUniverseNow()` / `refreshBasicsNow()` / `refreshDailyNow()` 응답 schema 갱신 (RefreshStartedResponse)

### 3.7 프론트 — RefreshProgressBanner 컴포넌트

**파일 신규**: `frontend/src/components/RefreshProgressBanner.tsx`

- 폴링: `useQuery({ queryKey: ["refresh-progress"], queryFn: fetchRefreshProgress, refetchInterval: 5000, retry: 1 })` (사이클 65 H3 + 사이클 75 G-RT 영속)
- 3 작업 중 어느 하나라도 `status === "running"` 이면 배너 표시
- 한글 작업명: universe="종목마스터 새로고침" / basics="기본정보 새로고침" / daily="일봉 새로고침"
- 프로그레스바: `(processed / total) * 100%` (total=0 시 indeterminate)
- 상세 카운터: updated / skipped / failed / elapsed_ms (KST 시:분:초)
- 완료 시 (`status === "completed"`): 토스트 + 3초 후 fadeout + invalidateQueries(["stock-master-stats"], ["stock-master-list"])
- 실패 시 (`status === "failed"`): 토스트 + error_message 배너 표시 + 5초 후 fadeout

**파일**: `frontend/src/pages/StockMaster.tsx`
- RefreshProgressBanner import + 상단 mount
- 3 버튼 useMutation `onSuccess`: 토스트 "작업 시작" (기존 "완료" → "시작")
- 3 버튼 useMutation `onError`: 409 Conflict 시 "이미 진행 중" 토스트
- 기존 timeout 토스트 "KIS API 일시 결함 — 잠시 후 재시도" 영구 폐기 (progress polling 영역 분리)

### 3.8 프론트 — 회귀 가드

**파일**: `frontend/src/components/__tests__/RefreshProgressBanner.test.tsx` (신규):
- **G-BANNER1**: idle 시 배너 미표시
- **G-BANNER2**: running 시 배너 + 프로그레스바 + 한글 작업명 표시
- **G-BANNER3**: 5초 폴링 (vi.useFakeTimers + refetchInterval 검증)
- **G-BANNER4**: completed 시 토스트 + fadeout + invalidateQueries
- **G-BANNER5**: failed 시 토스트 + error_message 표시
- **G-BANNER6**: 다중 작업 running 시 모두 표시 (3 작업 동시 running 시나리오)
- **G-BANNER7**: useQuery retry:1 명시 (사이클 65 H3)

**파일**: `frontend/src/pages/__tests__/StockMaster.test.tsx` (갱신):
- 3 버튼 onSuccess 토스트 "시작" 메시지
- 3 버튼 onError 409 "이미 진행 중" 토스트
- RefreshProgressBanner 컴포넌트 mount

### 3.9 MSW + Playwright LIFO

**MSW** (`frontend/src/test/handlers.ts`): GET /refresh-progress mock 핸들러
**Playwright** (`e2e/fixtures/api-mocks.ts`): /refresh-progress wildcard *전* 등록 (사이클 80 hotfix #3 G-AST-LIFO 답습)

---

## 4. 영속 의무 매트릭스

| 사이클 | 영역 | 영속 의무 |
|--------|------|-----------|
| 17 | OPSP0002 backoff | once 함수 변경 0 (50ms sleep 영속) |
| 38 | scanner 단계 매수 진입 전 | 매매 hot path 무관 영속 |
| 65 H3 | useQuery retry:1 | RefreshProgressBanner 영속 |
| 75 G-RT | retry 영역 확장 | 영속 |
| 80 hotfix #3 | Playwright LIFO | 영속 |
| 84 L-2 | POST 화이트리스트 | refresh-progress GET 추가 + POST 3 영속 |
| 90 | refresh_universe_now | fire-and-forget 전환 |
| 106 | lifecycle race 차단 | scheduler 변경 0 영속 |
| 122 | daily task | task loop 변경 0 영속 |
| 124 | UI 동기화 의무 | 영속 |
| 126 | 4 영역 통합 | 3 POST 라우트 fire-and-forget 전환 |

---

## 5. 매매 안전성 무영향 확정

- scanner 단계 매수 진입 *전* 영역만 변경
- `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (체결통보/uvicorn 단일 워커/주문번호 매핑/`_reset_daily_state`/NXT 좀비 차단/WebSocket 4중 안전망/KIS 거부 응답/KST 강제)

---

## 6. 검증 매트릭스

- 백엔드 사이클 127 격리 (G-STATE 8 + G-INT 12 + G-ROUTE 14 + G-AST 6 = 40 PASS)
- 프론트 사이클 127 격리 (G-BANNER 7 + StockMaster.tsx 갱신 = 11 PASS)
- 풀 회귀 0
- flakiness 0 × 3회 반복
- e2e Playwright LIFO 정합
- 사이클 90 / 122 / 124 / 126 영속 확인

---

## 7. 운영 효과 (push + EC2 자동 배포 후)

- (a) UI "기본정보 새로고침" 클릭 → 즉시 202 응답 + 토스트 "작업 시작"
- (b) 5초 주기 폴링 → 상단 배너 + 프로그레스바 + 카운터 실시간 갱신
- (c) 13분 작업 완료 → 토스트 + 배너 자동 fadeout + 데이터 갱신
- (d) 실패 시 → 토스트 + error_message 가시화
- (e) timeout silent 결함 영구 차단
- (f) 운영자 가시화 — KIS Rate Limit 안전 + 사이클 17 LMS chain 영속

---

## 8. 사이클 128+ 후속 카드

- D+1 운영 실측 (2026-06-15 월 09:00~10:00)
- 배너 mobile responsive 검증 (사이클 81 G-MOBILE-9 영속)
- 폴링 idle 시 60초 backoff (현재 5초 영속 시 무용 부담)
