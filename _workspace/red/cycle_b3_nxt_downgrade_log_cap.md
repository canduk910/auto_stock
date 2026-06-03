# 사이클 54 (카드 B-3) Red — `[nxt_downgrade]` 로그 emit cap

**작성**: tdd-engineer / 2026-06-03
**테스트 파일**: `tests/unit/engine/test_b3_nxt_downgrade_log_cap.py`
**Green 대상 모듈**: `src/engine/order_engine.py`

## 배경 (운영 실측, 2026-06-01)

분석 메모는 stock_master 사후 보강 누락 가설을 제시했지만, **반증 확인**:
- 064400 row `refreshed_at=2026-05-31T23:19:59` + `nxt_tradable=False` 정상 저장
- 사이클 32 NXT 사전 차단 메커니즘 (다운그레이드 결정) 자체는 정상

**실질 결함**: B-1 매도 좀비 폭주 (`execute_sell` 100+회 재진입) 부작용으로 동일 시점 발생한 `_strategy_exchange_async` 가 매번 `[nxt_downgrade] WARNING` 1행 발화 → 115건 로그 폭주. *반환값* 은 정확하나 *로그 cap* 부재.

## 사이클 의도

`_nxt_downgrade_logged_today: set[str]` 도입으로 ticker별 일일 1회 cap. 사이클 31 R6 (`_risk_silent_skip_logged_today`) / 사이클 52 (`_market_closed_blocked_logged_today`) 동형 패턴.

## 4 시나리오 매트릭스

| # | 시나리오 | Red 결과 | Green 후 기대 |
|---|---------|---------|---------------|
| S1 | 동일 ticker 100회 호출 (`nxt_tradable=False`) | FAIL — 100회 발화 | PASS — 1회 발화 + 100회 모두 KRX 반환 |
| S2 | ticker별 격리 (A 100 + B 100) | FAIL — 200회 발화 | PASS — 2회 발화 (각 1회) |
| S3 | `reset_daily_state()` 후 재발화 | FAIL — 1회차에서 100회 발화 | PASS — reset 후 cap 비워짐, 총 2회 |
| S4 | 회귀 가드 (`nxt_tradable=True`) | PASS — 기존 분기로 다운그레이드 안 함 | PASS 유지 — SOR 반환 + 발화 0 + cap 미등록 |

## Red 실행 로그

```
$ python -m pytest tests/unit/engine/test_b3_nxt_downgrade_log_cap.py -v
...
FAILED test_s1_when_same_ticker_called_100_times_then_log_emitted_only_once
  AssertionError: `[nxt_downgrade]` emit cap 위반: 100회 발화 (기대 1회).
FAILED test_s2_when_two_tickers_each_called_100_times_then_log_emitted_per_ticker
  AssertionError: ticker별 격리 위반: 총 발화 200회 (기대 2회).
FAILED test_s3_when_reset_daily_state_then_log_re_emits_for_same_ticker
  AssertionError: 1회차 cap 위반: 100회 (기대 1회).
PASSED test_s4_when_nxt_tradable_true_then_no_downgrade_and_no_log
=========================== 3 failed, 1 passed in 0.20s ============================
```

Red 의도대로 — S1/S2/S3 FAIL (cap 부재 결함 노출), S4 PASS (회귀 가드 사전 확보).

## Green 인터페이스 메모 (backend-dev 가 구현)

### 변경 위치 1 — `OrderEngine.__init__` (line ~87 근처)

```python
# 사이클 52 _market_closed_blocked_logged_today 바로 옆 배치
self._market_closed_blocked_logged_today: set[str] = set()
# 사이클 B-3 (2026-06-03) — [nxt_downgrade] WARNING ticker별 일일 1회 cap.
# 사이클 31 R6 / 사이클 52 동형 패턴.
self._nxt_downgrade_logged_today: set[str] = set()
```

### 변경 위치 2 — `_strategy_exchange_async` (line ~160 근처, `nxt_tradable=False` 분기)

**현재 코드** (src/engine/order_engine.py:157-169):
```python
if basics.nxt_tradable:
    return base

# nxt_tradable=False — KRX 강제 다운그레이드
try:
    await write_log(
        "WARNING",
        f"[nxt_downgrade] {ticker} strategy={strategy_id} "
        f"from={base} to=KRX reason=nxt_not_tradable",
    )
except Exception:
    pass  # 로그 실패는 본 흐름 보존
return "KRX"
```

**Green 명세**:
```python
if basics.nxt_tradable:
    return base

# nxt_tradable=False — KRX 강제 다운그레이드
# 사이클 B-3: ticker별 일일 1회 cap (반환값 결정은 cap 검사 *밖*)
if ticker not in self._nxt_downgrade_logged_today:
    try:
        await write_log(
            "WARNING",
            f"[nxt_downgrade] {ticker} strategy={strategy_id} "
            f"from={base} to=KRX reason=nxt_not_tradable",
        )
        self._nxt_downgrade_logged_today.add(ticker)
    except Exception:
        pass  # 로그 실패는 본 흐름 보존 (set 등록도 skip — 다음 호출에서 재시도)
return "KRX"
```

**주의 — set.add 위치**:
- write_log 성공 후 `add` (try 안) → 실패 시 다음 호출에서 재시도 가능
- 또는 write_log 호출 *직전* `add` → 실패 시 영구 누락 (보수적이지만 1회 누락 허용 시)
- **권고: try 안에서 add** — 사이클 52 패턴과 일관성 + 1회 발화 보장 우선

### 변경 위치 3 — `OrderEngine.reset_daily_state()` (사이클 52 도입)

`_market_closed_blocked.clear()` / `_market_closed_blocked_logged_today.clear()` 옆에:

```python
self._nxt_downgrade_logged_today.clear()
```

## 결정 점 (Green 진행 시 점검)

1. **반환값 결정 vs 로그 발화 분리**: 100회 호출 모두 KRX 반환은 cap 무관 — 위 코드처럼 `return "KRX"` 가 cap 분기 *밖* 위치 보장.
2. **write_log 예외 시**: 사이클 52 `_market_closed_blocked_logged_today` 는 set.add 를 write_log 이후 별도 줄에 배치 — 동일 패턴 권고.
3. **set 크기 폭주 방지**: 일일 reset 가드로 충분 (`reset_daily_state` 위임 `scheduler._reset_daily_state` 호출). 종목 수 ~5000 상한.
4. **회귀 영향 0**: 사이클 32 다운그레이드 결정 무변경, 사이클 52 reset 헬퍼 시그니처 무변경.

## 산출물

1. `tests/unit/engine/test_b3_nxt_downgrade_log_cap.py` — 4 시나리오, 200줄
2. 본 Red 메모 — `_workspace/red/cycle_b3_nxt_downgrade_log_cap.md`
3. backend-dev 인계 — Green 구현 (3개 변경 위치, ~5줄 추가)
