# 사이클 187 Red — Supabase connection 계열 retry 래퍼 (stock_master_daily read 4함수)

## 배경 (운영 진단 확정)
EC2 backend 컨테이너 traceback 직접 확인:
```
[ERROR] src.db.stock_master_daily — get_recent_daily 실패 graceful ticker=...
Traceback ...
httpx.RemoteProtocolError: Server disconnected
```
- **RemoteProtocolError 90건/24h** — 전부 read 경로(`get_recent_daily` 29 / `max_bas_dd` 6 / `count_all` 3 / 보조). **매매 hot path 쓰기 0건 영향**(EC2 grep 확정).
- 메커니즘: 16:00 일봉 task가 수백 종목 순회 → httpx pool의 stale keep-alive HTTP/2 연결 재사용 → 첫 요청에서 서버가 끊음. **DB 호출은 retry 부재**(KIS base.py는 3회, Supabase는 `to_thread` 단발) → 1회 실패 = graceful 빈값 → KIS 폴백(사이클 173 목적 부분 무력화 + 노이즈).
- 사용자 결정: **(범위) stock_master_daily read 4함수만** + **(멱등) SELECT만 retry** (쓰기 제외 — 멱등 우려).

## 목표
`src/db/supabase.py` 에 범용 `execute_with_retry` 헬퍼 추가 + stock_master_daily read 4함수가 경유. connection 계열 예외 1회 재시도(stale 연결 폐기 후 재연결). 기존 graceful except 보존(최종 실패 시 폴백).

## 구현 스펙

### 헬퍼 (`src/db/supabase.py`)
```python
import asyncio, logging, httpx
logger = logging.getLogger(__name__)

_RETRY_EXCEPTIONS = (
    httpx.RemoteProtocolError,   # Server disconnected (확정 주원인)
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
)
_RETRY_BACKOFF_SECS = 0.2

async def execute_with_retry(build, *, retries: int = 1, op: str = ""):
    """동기 Supabase 쿼리(build())를 to_thread 위임 + connection 계열 예외 retries회 재시도.
    build = .execute() 포함 무인자 callable. **멱등 SELECT 전용** (쓰기 미적용).
    재시도 소진 시 마지막 예외 raise → 호출자 graceful except 보존."""
    for attempt in range(retries + 1):
        try:
            return await asyncio.to_thread(build)
        except _RETRY_EXCEPTIONS as exc:
            if attempt >= retries:
                raise
            logger.warning("[supabase_retry] op=%s attempt=%d/%d exc=%s 재시도",
                           op or "?", attempt + 1, retries + 1, type(exc).__name__)
            await asyncio.sleep(_RETRY_BACKOFF_SECS)
```
- 비-retry 예외(`ValueError`/`postgrest.APIError` 등)는 **즉시 전파**(재시도 0).
- `logger.warning` 단독 — `write_log` 동시 호출 금지(사이클 72 이중 INSERT 차단).

### 적용 (`src/db/stock_master_daily.py`) — read 4함수만
`from src.db.supabase import supabase` → `from src.db.supabase import supabase, execute_with_retry`
각 함수의 `await asyncio.to_thread(lambda: supabase.table(...)...execute())` →
`await execute_with_retry(lambda: supabase.table(...)...execute(), op="<함수명>")`:
- `get_recent_daily` (L232) op="get_recent_daily"
- `count_all` (L325) op="count_all"
- `count_by_ticker` (L342) op="count_by_ticker"
- `max_bas_dd` (L373/L381 ticker None 분기 2곳 — build 를 if/else 로 구성 후 단일 `execute_with_retry`)
- 기존 `try/except Exception: logger.exception(...graceful)` + 폴백 반환값(`[]`/`0`/`None`) **전부 불변**.

### 미적용 (Q2 멱등 — 쓰기 제외)
`upsert_daily`(L148) / `upsert_batch`(L200) / `purge_old_rows`(L638) 는 **execute_with_retry 미경유**(직접 to_thread 유지).

## 회귀 가드 (tdd-engineer)
### A. 헬퍼 단위 (`tests/unit/db/test_cycle187_execute_with_retry.py`)
- G-187-H1: RemoteProtocolError 1회 후 2차 정상 → 결과 반환(build 2회 호출). **Red 핵심**
- G-187-H2: retries=1 → 2회 연속 RemoteProtocolError → 마지막 예외 raise
- G-187-H3: ConnectError/ConnectTimeout/ReadError 도 재시도 대상
- G-187-H4: 비-retry 예외(ValueError) → 즉시 raise, build 1회만 호출(재시도 0)
- G-187-H5: 정상 1회 → 결과 반환, build 1회(재시도 0, sleep 0)
- G-187-H6: retries=0 → 재시도 없이 1회 시도 후 raise

### B. stock_master_daily 통합 (`tests/unit/db/test_cycle187_daily_read_retry.py`)
- G-187-I1: get_recent_daily — 1차 RemoteProtocolError 후 2차 성공 → rows 반환(graceful [] 안 빠짐). **Red 핵심**
- G-187-I2: get_recent_daily — 2회 실패 → graceful `[]` (기존 except 보존)
- G-187-I3: count_all — retry 후 성공 → count / 2회 실패 → graceful `0`
- G-187-I4: max_bas_dd(ticker) + max_bas_dd(None) — retry 후 성공 / 2회 실패 → graceful `None`

### C. AST 영구 가드 (`tests/unit/ast/test_cycle187_ast_read_retry.py`)
- G-187-A1: read 4함수 본체가 `execute_with_retry` 호출(직접 `asyncio.to_thread` 잔존 0건, read 한정)
- G-187-A2: 쓰기 함수(upsert_daily/upsert_batch/purge_old_rows)는 `execute_with_retry` 미경유(`asyncio.to_thread` 직접 유지) = Q2 멱등 제외 영구 보장
- G-187-A3: `execute_with_retry` 본체 `write_log` 호출 0건(사이클 72 이중 INSERT 차단)

## Red 유효성
현재 코드(retry 없음): G-187-H1/H2.../H6 전부 FAIL(헬퍼 미존재) + G-187-I1 FAIL(1회 실패 시 graceful [] 반환, retry 안 함) + G-187-A1 FAIL(현재 to_thread 직접). G-187-I2/A2(쓰기 제외)는 현재도 PASS(불변식).

## 매매 안전성 (8영역 diff 0)
`git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = 0. supabase.py 헬퍼 추가 + stock_master_daily read 4함수 경유만. 쓰기/매매 hot path 불변. 사이클 173 prepare 어댑터(get_recent_daily_normalized → get_recent_daily 경유)는 retry 보호를 **간접 수혜**(동등성 보존, KIS 폴백 빈도 감소).

---

## 회귀 흡수 — freeze_time + retry sleep hang (사이클 187 Green 후 tester 발견, tdd-engineer 흡수)

### 증상
`tests/unit/engine/strategies/test_bull_flag_breakout.py::test_prepare_populates_candidates_on_valid_setup`
가 사이클 187 Green 직후 60s timeout(pyproject `timeout=60`) 으로 hang → 표준 실행
(`tests/unit/engine/strategies/`) CI red.

### 메커니즘 (확정)
1. 이 테스트는 `with freeze_time("2026-05-08 07:50:00")` 안에서 BFB `prepare()` 실행.
   `fetch_daily_candles` / `_scan_universe` 만 mock, **stock_master_daily DB 계층 미mock**.
2. `prepare()` → `get_recent_daily_normalized` → `get_recent_daily` 가 실 Supabase 연결 시도
   → `httpx.ConnectError`.
3. 사이클 187 이 `ConnectError` 를 `_RETRY_EXCEPTIONS` 에 추가 → `execute_with_retry` 가
   `await asyncio.sleep(_RETRY_BACKOFF_SECS=0.2)` 진입.
4. **freezegun 이 `time.monotonic` 동결 → asyncio 이벤트 루프가 sleep wake-up 시각에 영원히
   도달 못 함 → hang.** (pre-187: `get_recent_daily` 단발 `to_thread` → ConnectError graceful
   `[]` → KIS 폴백 → 0.19s PASS. 187 retry 도입이 유발.)
5. stash 교차검증 = pre-187 PASS / post-187 60s timeout → 187 유발 확정.
   운영 영향 0(freezegun 은 운영 비활성, sleep 정상). 테스트 결정성만 깨짐.

### 시정 (테스트 결정화 — production 코드 불변)
이 테스트 의도 = **BFB prepare candidate 생성 로직 검증**(DB graceful 검증 아님).
실연결 의존 제거 = `monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily",
AsyncMock(return_value=[]))` 1줄 추가(+ `from unittest.mock import AsyncMock`).
- patch 타겟 = **source 모듈**(`src.db.stock_master_daily.get_recent_daily`). BFB 가
  `get_recent_daily_normalized` 를 함수-레벨 로컬 import(`bull_flag_breakout.py:142`) 하므로
  BFB 모듈 네임스페이스엔 어댑터 심볼이 없음 → source 모듈 글로벌 바인딩을 패치해야 적중.
- `get_recent_daily` → `[]` 면 어댑터가 lock 게이트(`if db_rows and any(...)`)·신선도
  게이트(`if db_rows:` → `max_bas_dd` 미호출) 모두 건너뛰고 곧장 min_required 게이트 →
  **기존 KIS 폴백(`fetch_daily_candles` mock) 경로 그대로** = pre-187 동작 보존.
  retry 경로(`get_recent_daily` 내부 `execute_with_retry`) 미진입 → sleep·hang 차단.
- 대안(어댑터 `get_recent_daily_normalized` 자체 stub 으로 fake candle 직접 주입)은
  `fetch_daily_candles` mock 을 dead 로 만들고 KIS 폴백 경로 검증을 제거 → 더 큰 개입이라 미채택.

### 영구 방어 검토 (#2)
- 영향 범위 = **이 파일 1개 테스트만**. `tests/unit/engine/strategies/` 전수 grep =
  `freeze_time` ∩ `prepare()` 동시 보유 파일은 `test_bull_flag_breakout.py` 단 1개.
  다른 prepare() 호출 테스트(cycle173/163/158/148/143/50/48/39 등)는 freeze_time 없이
  prepare 하거나 DB read 를 자체 mock → 실연결·동결 sleep 미발생.
- 광역 autouse 픽스처(strategies conftest 에서 `get_recent_daily` 기본 `[]` stub 또는
  `asyncio.sleep` no-op) 는 **미적용 — 인계**. 사유: cycle173 동등성 / cycle123 donchian
  DB high / cycle125 VCP ATR DB / cycle158·163 retry-hook 테스트가 DB 어댑터·sleep 동작을
  *의도적으로* 검증 → 광역 stub 이 이들 의도를 가릴 위험("과하지 않은 선" 위반).
- **인계 가이드(미래 테스트 작성자)**: `freeze_time` 안에서 prepare()/stock_master_daily
  read 를 태우는 테스트는 반드시 (a) `get_recent_daily`(또는 `get_recent_daily_normalized`)
  를 mock 하거나 (b) freeze_time 밖에서 DB read 를 끝낼 것. retry 래퍼의 `asyncio.sleep`
  은 동결 monotonic 과 결합 시 무한 대기 = 동일 hang 재발.

### 검증
- `pytest tests/unit/engine/strategies/test_bull_flag_breakout.py -q` → hang 없이 PASS
  (해당 테스트 < 수 초).
- `pytest tests/unit/engine/strategies/ -q` → 0 fail.
- `pytest tests/unit/db/test_cycle187_execute_with_retry.py
  tests/unit/db/test_cycle187_daily_read_retry.py
  tests/unit/ast/test_cycle187_ast_read_retry.py -q` → 13 PASS 불변.
- `git diff --stat -- src/` = 0(테스트만 수정).
