# 사이클 144 영역 B — 카드 #27 graceful 가시화 강화 (LOW)

- **사용자 결정**: Q1=A 사이클 143 commit + push + 사이클 144 = D+1 운영 실측 (자동) + 영역 B 카드 #27
- **인계**: 사이클 129/132 카드 #27 영역 영구 영속
- **위험 등급**: LOW (logging 영역 한정, 매매 안전성 무영향)

## 영역 영구 영속 진단

### 현행 graceful 분기

`src/api/condition.py::inquire_stock_basics` (사이클 107 영속):
- CTPF1002R 호출 실패 → 전파 (호출자 보호 영구 영속)
- **FHKST01010100 호출 실패** → `try/except: logger.exception` + `price_data = {}` fallback (graceful) → CTPF만 raw merge → silent fail 영역 영구 영속

### 현행 silent fail 영역 영구 영속

`scanner.py::_stock_master_basics_refresh_once` summary:
- `total / updated / skipped / failed` (4 키 영속)
- **`graceful_failed` 부재 영역 영구 영속**: FHKST01010100 실패는 `inquire_stock_basics` 영역에서 silent 영속 → scanner 영역 영구 영속 가시화 불가 영역 영구 영속

## Step 1 — `condition.py` graceful_failed 카운터 신규

### 모듈 전역 dict 영역 영구 영속

```python
# 사이클 144 — graceful_failed 카운터 영역 영구 영속 (카드 #27 영속)
_graceful_failed_counter: dict[str, int] = {
    "fhkst01010100_failed": 0,  # FHKST01010100 호출 실패 영역 영구 영속
}
_graceful_failed_lock = asyncio.Lock()


async def _record_graceful_failed(reason: str) -> None:
    """graceful 분기 fail 카운터 영역 영구 영속 (모듈 전역 영역).

    Args:
        reason: fail 사유 ("fhkst01010100_failed" 등)
    """
    async with _graceful_failed_lock:
        if reason in _graceful_failed_counter:
            _graceful_failed_counter[reason] += 1


def get_graceful_failed_counts() -> dict[str, int]:
    """graceful_failed 카운터 영역 영구 영속 스냅샷 반환."""
    return dict(_graceful_failed_counter)


def reset_graceful_failed_counts() -> None:
    """graceful_failed 카운터 영역 영구 영속 reset (호출자 영역 영구 영속).

    scanner._stock_master_basics_refresh_once 시작 시 reset → 단일 task 영역
    영구 영속 측정.
    """
    for key in _graceful_failed_counter:
        _graceful_failed_counter[key] = 0
```

### inquire_stock_basics 영역 영구 영속 갱신

```python
# 사이클 107 영역 (기존)
try:
    price_data_raw = await kis_get_quote(...)
except Exception:
    logger.exception("[inquire_stock_basics] FHKST01010100 호출 실패 graceful pdno=%s", pdno)
    # 사이클 144 — graceful_failed 카운터 영역 영구 영속 (카드 #27 영속)
    await _record_graceful_failed("fhkst01010100_failed")
    price_data = {}
```

## Step 2 — `scanner.py` summary emit 영역 영구 영속 graceful_failed 필드 추가

### `_stock_master_basics_refresh_once` 시작 시 reset + 종료 시 collect

```python
# 시작 시 reset (단일 task 영역 영구 영속 측정)
from src.api.condition import reset_graceful_failed_counts, get_graceful_failed_counts
reset_graceful_failed_counts()

# ... for loop 영역 영구 영속 ...

# 종료 시 graceful_failed 카운터 영역 영구 영속 수집
graceful_failed_counts = get_graceful_failed_counts()
fhkst_failed = graceful_failed_counts.get("fhkst01010100_failed", 0)
summary["graceful_failed"] = {
    "fhkst01010100_failed": fhkst_failed,
}

# summary emit 영역 영구 영속 갱신
logger.info(
    "[stock_master_basics_refresh_summary] total=%d updated=%d "
    "skipped=%d failed=%d graceful_failed_fhkst=%d elapsed_ms=%d",
    summary["total"], summary["updated"],
    summary["skipped"], summary["failed"],
    fhkst_failed,
    summary["elapsed_ms"],
)
```

## Step 3 — 회귀 가드 (10 케이스)

### G-144-COUNTER — graceful_failed 카운터 영역 영구 영속 (4 케이스)

- G-144-COUNTER-1: `_graceful_failed_counter` 모듈 전역 dict 영속
- G-144-COUNTER-2: `_record_graceful_failed("fhkst01010100_failed")` 호출 → 카운터 증가
- G-144-COUNTER-3: `get_graceful_failed_counts()` 스냅샷 반환 영역 영구 영속
- G-144-COUNTER-4: `reset_graceful_failed_counts()` 초기화 영역 영구 영속

### G-144-INTEGRATION — inquire_stock_basics 영역 영구 영속 (3 케이스)

- G-144-INT-1: FHKST01010100 호출 실패 → `_record_graceful_failed` 호출 영속
- G-144-INT-2: CTPF1002R 정상 + FHKST01010100 실패 → `price_data = {}` fallback + 카운터 +1
- G-144-INT-3: 양쪽 정상 → 카운터 변경 0

### G-144-SUMMARY — scanner summary 영역 영구 영속 (2 케이스)

- G-144-SUMMARY-1: `summary["graceful_failed"]` 키 영속
- G-144-SUMMARY-2: summary emit 로그 영역 영구 영속 `graceful_failed_fhkst=N` 필드 영속

### G-144-AST — AST 영구 가드 (1 케이스)

- G-144-AST-1: `inquire_stock_basics` graceful 분기에 `_record_graceful_failed` 호출 영속

## 영속 의무 매트릭스

- 사이클 17 KIS LMS chain (변경 0)
- 사이클 38 명문화 (테스트 + logging 영역 한정)
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0)
- 사이클 88 G-REJECT graceful (영역 강화)
- 사이클 107 inquire_stock_basics merge 패턴 (영역 영구 영속 보존)
- 사이클 122/126/127/128/129/131/132/133/134/135/136/137/138/139/142/143 영속 (영향 0)

## 매매 안전성 영역 영구 영속

- 테스트 + logging 영역 한정 (logging 영역 보강만)
- `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0
- 매수 진입 hot path 영향 0
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속
