# 사이클 7-C Red 명세 — REST 시세성 호출 풀 + scanner 분배 명시화

작성: 2026-05-17 (팀장)
선행: 사이클 7-A (multi-account 토큰 매니저) + 7-B (WebsocketPool)

## 목표

1. **scanner 분배 명시화** — `subscribe_filtered_stocks(priority_groups=...)` 가 priority 카테고리별로 `pool.subscribe(..., priority='HIGH'|'LOW')` 명시 전달
2. **scheduler 보조 세션 connect** — `_boot()` / `start()` 단계에서 풀의 보조 세션을 연결
3. **K stale watcher 보조 세션 지원** — 풀의 `resend_subscribe_for_ticker(tr_id, tr_key)` 사용, 강제 재등록 시도 분배 추적 활용
4. **REST 시세성 호출 풀** — `kis_request_quote(...)` 신규 함수 + `kis_get_quote/kis_post_quote` 래퍼. 보조 토큰 매니저 라운드로빈, 보조 0개 시 메인 fallback. 매매/잔고 경로는 절대 라우트 안 함 (path 가드 추가)

## 자금 안전 절대 원칙

- 매매(`place_order`/`cancel_order`) / 잔고(`get_balance`/`get_buyable`) / 체결조회(`get_daily_orders`) / 체결통보 → **영원히 메인 단일** (사이클 7-A/7-B 가드 그대로)
- 본 사이클 변경 범위: **REST 시세성 호출만** (`fetch_daily_candles`, `fetch_stock_detail`, `fetch_rising_stocks`, `is_market_open`, `next_trading_day`, `inquire_stock_basics`, `_fetch_fluctuation_rank`)

## 자율 결정

- **`kis_request_quote` 위치**: `src/api/base.py` 에 함수 추가 (별도 파일 분리 안 함). Rate Limit 세마포어/재시도/메트릭 로직 공유, 단일 진실의 원천 유지.
- **Per-label semaphore**: 보조 매니저 label 별 독립 `asyncio.Semaphore(18)` 풀 — 메인의 `_semaphore=20` 보다 보수적 (안전 여유).
- **Path 가드**: 시세 함수가 사용하는 6개 URL 화이트리스트 — 그 외 경로는 ValueError (defense-in-depth).
- **메트릭**: 별도 `_quote_request_metrics` dict 분리 — 시세 풀 호출은 메인 메트릭에 섞이지 않게 격리. 합집합 조회용 `get_request_metrics(combined=True)` 옵션은 본 사이클 보류.

## Red 회귀 (~35 신규)

### A. `tests/unit/api/test_quote_pool.py` (≥12)

A-1 보조 0개 시 메인 매니저 fallback — `_request_via_quote_pool` 가 `token_manager.get_token` 호출
A-2 보조 N개 시 라운드로빈 — 3회 호출에 label="quote-1"→"quote-2"→"quote-1" 분배 (2개 active)
A-3 보조 토큰 매니저 호출 → `get_token_manager("quote-1")` lazy 발급 확인
A-4 보조 매니저 예외(`ValueError`) graceful — 메인 fallback 정상 동작
A-5 path 가드 — `/order-cash` / `/inquire-balance` / `/inquire-daily-ccld` 등은 `ValueError` raise (시세 풀 거부)
A-6 path 화이트리스트 — `inquire-price`, `inquire-daily-itemchartprice`, `chk-holiday`, `search-stock-info`, `ranking/fluctuation` 모두 통과
A-7 `kis_get_quote` 위임 — `_request_via_quote_pool("GET", ...)` 호출
A-8 `kis_post_quote` 위임 — POST 도 동일 라우트
A-9 보조 매니저 토큰 만료 시 자동 재발급 (사이클 7-A `get_token` 사용)
A-10 보조 5xx 응답 → 재시도 3회 (메인과 동일 backoff)
A-11 보조 메트릭 격리 — `get_quote_request_metrics()` 가 별도 카운터 반환
A-12 `MAX_RETRIES=3` 보조 풀에서도 동일 적용

### B. `tests/unit/api/test_condition_quote_routing.py` (≥6)

B-1 `fetch_stock_detail(ticker)` → `kis_get_quote` 호출 (kis_get 가 아님)
B-2 `fetch_daily_candles(ticker, days)` → `kis_get_quote` 호출
B-3 `fetch_rising_stocks` → `_fetch_fluctuation_rank` 가 `kis_get_quote` 사용
B-4 `inquire_stock_basics(pdno)` → `kis_get_quote` 사용
B-5 `is_market_open` / `next_trading_day` → `kis_get_quote` 사용 (chk-holiday)
B-6 **`get_balance` / `get_buyable` / `place_order` / `get_daily_orders` / `cancel_order` 는 절대 `kis_request_quote` 호출 안 함** (mock 으로 kis_request_quote spy → 호출 0)

### C. `tests/unit/engine/test_scanner_priority_dispatch.py` (≥8)

C-1 `positions=['005930'] priority_groups` → `pool.subscribe(TICK_TR_ID, '005930', priority='HIGH')` 호출
C-2 `next_day_clear=['000660']` → priority='HIGH' 전달
C-3 `momentum=['012345']` → priority='LOW' 전달
C-4 `breakout=['234567']` → priority='LOW' 전달
C-5 `swing=['345678']` → priority='LOW' 전달
C-6 `priority_groups=None` (외부 호환) → 평탄 처리 (priority 키워드 미전달 또는 모두 LOW 기본)
C-7 HIGH 카테고리는 `bypass_limit=True` 와 함께 전달 (보유 시세 절대 보장)
C-8 중복 ticker — positions+momentum 양쪽에 있으면 HIGH 로만 1회 전달, LOW 단계에서 skip

### D. `tests/integration/test_stale_watcher_pool.py` (≥5)

D-1 보조 세션 없을 때 stale ticker → `pool.resend_subscribe_for_ticker` 1회 호출 (메인 fallback)
D-2 보조 세션에 분배된 ticker → `_ticker_to_session` 추적 활용, 해당 보조 세션 `_send_subscribe` 호출
D-3 retry > 3 강제 재등록 → `pool.unsubscribe_in_pool` + `pool.subscribe(priority=...)` 호출
D-4 retry > 6 skip — 호출 0
D-5 전체 fresh 회복 → `_stale_retry_count.clear()`

### E. `tests/integration/test_scheduler_boot_quote_sessions.py` (≥4)

E-1 보조 세션 0개 시 `_boot()` 정상 동작 — 메인만 연결 (회귀)
E-2 보조 세션 N개 등록 시 `_boot()` 가 `pool.start()` 호출 → 보조 세션 `connect` 발화
E-3 보조 세션 connect 실패 → 다른 세션 / 메인 정상 (graceful)
E-4 `_boot()` 가 메인 + 보조 연결 후 체결통보는 메인에서만 구독

## Green 변경 파일

### `src/api/base.py` (+~150 LOC)

- `_quote_semaphores: dict[str, asyncio.Semaphore]` per-label
- `_quote_request_metrics` dict (격리)
- `_quote_request_index: int` + `_quote_index_lock: asyncio.Lock`
- `_QUOTE_ALLOWED_PATHS: frozenset[str]` — 시세 함수 6개 URL 화이트리스트
- `class QuotePoolPathError(ValueError)` — 매매/잔고 경로 거부
- `async def _select_quote_label() -> Optional[str]` — DB `list_accounts(active_only=True)` 라운드로빈
- `async def _request_via_quote_pool(method, path, tr_id, ...)` — 라우팅 본체
- `async def kis_get_quote(path, tr_id, params, *, hashkey="")` / `kis_post_quote` — public API
- `def get_quote_request_metrics() -> dict` / `reset_quote_request_metrics() -> None`

### `src/api/condition.py` (~6 변경)

- `from src.api.base import kis_get` → `from src.api.base import kis_get_quote, KisApiError`
- 6 함수 `kis_get → kis_get_quote` 치환:
  - `is_market_open`, `next_trading_day` (chk-holiday)
  - `_fetch_fluctuation_rank` (ranking/fluctuation)
  - `inquire_stock_basics` (search-stock-info)
  - `_fetch_stock_detail_and_cache` (inquire-price)
  - `_fetch_daily_candles_and_cache` (inquire-daily-itemchartprice)

### `src/api/order.py` / `src/api/balance.py` — **변경 0**

방어적으로 매매/잔고/체결조회 함수가 `kis_request_quote` 를 호출하지 않음을 단위 테스트로 강제 (B-6).

### `src/engine/scanner.py` (~25 LOC)

- `from src.realtime.websocket_pool import kis_ws_pool` 추가
- `subscribe_filtered_stocks` priority_groups 분기에서 `kis_ws.subscribe` → `kis_ws_pool.subscribe(..., priority='HIGH'|'LOW', bypass_limit=True/False)`
- 평탄 분기(`priority_groups=None`) 는 변경 없음 (외부 호환)

### `src/realtime/websocket_pool.py` (~80 LOC)

- `async def start(self) -> None` — DB 보조 세션 조회 + 각 보조 KisWebSocket 인스턴스 생성 + `_quotes` 추가. 메인 connect 는 호출자가 별도 처리 (scheduler 기존 흐름 보존)
- `async def connect_quotes(self, dispatch_message) -> None` — 보조 세션 동시 connect (graceful per-session try/except)
- `async def stop(self) -> None` — 메인 disconnect + 보조 disconnect (메인은 호출자 책임 유지)
- `async def unsubscribe_in_pool(self, tr_id, tr_key) -> None` — K stale watcher 헬퍼 (분배 추적 기반)
- 보조 세션 token: 사이클 7-A `get_token_manager(label)` 사용해 KisWebSocket 인스턴스에 자격증명 주입 — 신규 코드 필요 (KisWebSocket 가 메인 settings 만 참조하던 결함 분리)

### `src/realtime/websocket.py` — 최소 변경 (~10 LOC)

- `KisWebSocket.__init__(token_manager=None)` — 메인 token_manager 기본, 보조 세션은 주입 가능
- `connect(dispatch_message)` 에서 `await self._token_manager.get_approval_key()` 사용 — 기존 `token_manager.get_approval_key()` 직접 import 제거

### `src/engine/scheduler.py` (~20 LOC)

- `from src.realtime.websocket_pool import kis_ws_pool`
- `_boot()` 마지막 또는 `start()` 의 `kis_ws.connect` 호출 옆에 `await kis_ws_pool.start()` (보조 세션 생성/connect)
- `_check_and_resubscribe_stale` 가 `kis_ws._send_subscribe(...)` 대신 `kis_ws_pool.resend_subscribe_for_ticker(...)` 호출, 강제 재등록은 `pool.unsubscribe_in_pool` + `pool.subscribe(priority=HIGH, bypass_limit=True)` 사용 (보유 종목 우선순위 보장)

## 안전 진행 패턴

- 보조 세션 0개 시 메인 only 동작 (회귀 0)
- 매매/잔고/체결통보 함수 변경 0 — `kis_request_quote` 에 path 가드
- 외부 호출자 인터페이스 보존 — `fetch_daily_candles(ticker, days)` 등 시그니처 변경 0
- DB 보조 매니저 로드 실패 → graceful (메인 fallback)

## 문서 동기화 (Green 이후)

- `src/api/CLAUDE.md` — `kis_request_quote` 분리 + 매매/잔고 메인 가드 보강
- `src/engine/CLAUDE.md` — scanner priority 분배 + scheduler K 멀티 세션
- `src/realtime/CLAUDE.md` — 사이클 7-C 통합 (start/connect_quotes/unsubscribe_in_pool)
- `_workspace/00_leader_trading_rules.md` — 사이클 7-C 섹션
- `docs/HARNESS_CHANGELOG.md` — 사이클 7-C 1행
