# 사이클 18 — ISA HTTP 500 결함 정리 + UI 끊김 표시 보강 + 돌파 라벨 매매 컨텍스트

> 작성: team-leader / 일자: 2026-05-19 / 사용자 명시: "나열한 기능 전부 묶어서"
> 검증 환경: VTS 1차 → 운영 검수 후 실전 / Push 별도 승인

## 0. 사이클 컨텍스트

2026-05-19 사이클 17 옵션 A (`_REJECT_KEYWORDS_UPPER` 가드 + OPSP backoff 300s + K stale watcher 즉시 재등록) 안정화 직후 운영 로그 진단에서 3 결함 노출:

1. **ISA HTTP 500 폭주** — `[quote_pool] HTTP 500 (attempt 1/3)` `label=ISA` 가 20분 18건 + 시간당 30+ 회. `inquire-price` / `inquire-daily-itemchartprice` 두 path. 메인 fallback 으로 결국 성공하나 **로그 폭주 + KIS 측 부담** + 응답 지연 (3회 재시도 backoff 누적)
2. **UI 끊김 표시 오해 유발** — 조건검색 현황의 "끊김 19종목" 표시가 *시스템 결함* 처럼 보임. 실제 NXT 애프터 시간대 거래량 부족 (자연 stale). 컨텍스트 부재로 운영자 오해
3. **"돌파" 라벨 매수 미실행** — 한화에어로스페이스(012450) 16:43 "돌파" 표시되나 매수 0건. VB `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main")` 보드 가드 skip (정상). UI 가 *매매 가능 여부* 표시 안 함 → "왜 안 사지?" 운영자 혼란

> 사용자 명시: **3 영역 묶음 사이클**. 백엔드 (A) + 프론트엔드 (B+C) 병렬 위임.

## 1. 안전 원칙 (절대 깨지 말 것)

- **사이클 17 보강 보존**: `_REJECT_KEYWORDS_UPPER` 의 `MAX SUBSCRIBE` / OPSP backoff 300s / K stale watcher 강제 재등록 즉시 분기
- **사이클 16 AES 키 격리 가드 보존** (멀티 매니저 토큰 분리)
- **사이클 15-A delta-only 보존** (변경 종목만 unsub/sub)
- **Codex `1350aa8`+`84372cb` 보존** — handler/websocket try/except 가드
- **자금 안전 절대 원칙 보존** — 매매/잔고/체결조회는 메인 단일, 시세 풀만 ISA 등 보조
- **VB DEFAULT_TRADABLE_BOARDS 변경 금지** — POST_NXT 추가 금지 (15:20 일괄매도 정책). 본 사이클의 UI 보강은 *프론트* 만 — 백엔드 매매 정책은 그대로
- **매매 코드 침범 0** — `risk.on_tick` / `order_engine` 무변경
- **단일 워커 / 단일 데이터 경로** (사이클 17 보강 원칙)
- TDD: tdd-engineer Red → backend-dev + frontend-dev Green → tester 검증
- 한글 커밋 메시지 (2026-05-17 이후 ba4175b 컨벤션)
- Push 별도 명시 승인 — 본 작업은 커밋까지만

---

## 2. 영역 A — ISA HTTP 500 결함 정리 (백엔드)

### A-1. 5xx 로그 dedupe (`src/api/base.py`)

**목표**: 동일 `(path, label, status)` 키 60s 윈도우 내 재발생 시 WARNING 억제 + 카운트만 누적. 60s 단위 1행 INFO summary 로 갈음 → 로그 폭주 해소.

**구현 명세**:

```python
# src/api/base.py (신규 모듈 상수 / 메모리 카운터)
_QUOTE_5XX_DEDUPE_WINDOW = 60.0  # seconds
# key = (path, label, status) → (window_start_ts, count)
_quote_5xx_dedupe: dict[tuple[str, str, int], tuple[float, int]] = {}
_quote_5xx_dedupe_lock = asyncio.Lock()


async def _record_5xx_for_dedupe(path: str, label: str, status: int) -> bool:
    """기록 후 'should_emit_warning' 반환.
    - 첫 발생 또는 윈도우 만료(60s 경과) → True (WARNING 1행 + window reset count=1)
    - 윈도우 내 재발생 → False (카운트 +1, WARNING 억제)
    """
    now = asyncio.get_event_loop().time()
    async with _quote_5xx_dedupe_lock:
        key = (path, label, status)
        entry = _quote_5xx_dedupe.get(key)
        if entry is None or (now - entry[0]) > _QUOTE_5XX_DEDUPE_WINDOW:
            _quote_5xx_dedupe[key] = (now, 1)
            return True
        _quote_5xx_dedupe[key] = (entry[0], entry[1] + 1)
        return False


async def _emit_5xx_dedupe_summary() -> None:
    """60s 주기 task — 누적된 5xx dedupe 카운트 1행 INFO 후 reset.
    
    호출 주체: 별도 background task (main.py lifespan 또는 scheduler._boot).
    카운트 ≥ 2 인 (path,label,status) 만 출력. 카운트 1 은 첫 WARNING 으로 이미 표시됨.
    """
    now = asyncio.get_event_loop().time()
    items: list[tuple[tuple[str, str, int], int, float]] = []
    async with _quote_5xx_dedupe_lock:
        for key, (window_start, count) in list(_quote_5xx_dedupe.items()):
            if (now - window_start) > _QUOTE_5XX_DEDUPE_WINDOW:
                # 윈도우 만료 — count >= 2 면 summary 출력
                if count >= 2:
                    items.append((key, count, window_start))
                del _quote_5xx_dedupe[key]
    for (path, label, status), count, _ in items:
        logger.info(
            "[quote_pool_5xx_summary] path=%s label=%s status=%d count=%d within=%.0fs",
            path, label, status, count, _QUOTE_5XX_DEDUPE_WINDOW,
        )
```

**호출 지점** (`_request_via_quote_pool` 의 5xx 분기):

```python
# 기존 (현재 ~line 555)
logger.warning(
    "[quote_pool] HTTP %s (attempt %d/%d): %s label=%s",
    status, attempt, MAX_RETRIES, path, actual_label,
)

# 변경 (dedupe 적용)
should_emit = await _record_5xx_for_dedupe(path, actual_label, status)
if should_emit:
    logger.warning(
        "[quote_pool] HTTP %s (attempt %d/%d): %s label=%s",
        status, attempt, MAX_RETRIES, path, actual_label,
    )
```

**Background task 발화** (`src/main.py` lifespan 또는 `src/engine/scheduler.py::_boot`):

- 1분 주기 `asyncio.create_task` — 시스템 종료 시 task cancel 정리. 첫 발화는 `_boot()` 이후 60s 후
- 권장 위치: `src/engine/scheduler.py::_boot()` 끝에서 `asyncio.create_task(self._5xx_dedupe_summary_loop())` 1회. 메서드 본체:
  ```python
  async def _5xx_dedupe_summary_loop(self) -> None:
      from src.api.base import _emit_5xx_dedupe_summary
      while self.running:
          try:
              await asyncio.sleep(_QUOTE_5XX_DEDUPE_WINDOW)  # 60s
              await _emit_5xx_dedupe_summary()
          except asyncio.CancelledError:
              raise
          except Exception:
              logger.exception("[quote_pool_5xx_dedupe_summary] loop error")
              await asyncio.sleep(60)
  ```
- 운영 종료/재시작 시 가드: `_reset_daily_state()` 또는 `stop()` 분기에서 `_quote_5xx_dedupe.clear()`

**회귀 가드** (`tests/unit/api/test_quote_pool_5xx_dedupe.py`, 신규 5 케이스):

1. `test_first_5xx_emits_warning_and_resets_window` — 첫 발생 should_emit=True + count=1
2. `test_repeated_5xx_within_window_suppresses_warning` — 동일 키 5회 should_emit=False (1회 emit + 4 suppressed)
3. `test_5xx_after_window_expiry_emits_again` — `freezegun` 으로 61s 점프 후 should_emit=True + 카운트 리셋
4. `test_summary_emits_aggregate_for_repeated_5xx` — 5회 누적 후 `_emit_5xx_dedupe_summary` 호출 → INFO 1행 출력 + dedupe state clear (count>=2 만 출력)
5. `test_different_keys_tracked_independently` — `(path_A, label_X)` 와 `(path_B, label_X)` 별도 추적, 윈도우 분리

### A-2. health_monitor 자동 비활성 임계 강화

**배경**: 현재 임계 (5회 연속 || 5분 50%). ISA 의 경우 5xx 80%+ 비율 + 시간당 30+ 회로 5분 윈도우 50% 임계는 *충분히 빠름*. 다만 **5xx 80% 이상 1분 윈도우 + 10회 미만 즉시 발화** 추가 분기 시 ISA 같이 영구 결함 라벨 빠른 탈락.

**구현 명세** (`src/services/quote_session_health.py`):

신규 상수:
```python
FAST_WINDOW_SECS = 60        # 1분 fast window
FAST_MIN_CALLS = 10          # fast window 임계 평가 최소 호출 수
FAST_MAX_FAILURE_RATE = 0.8  # fast window 실패율 임계 (80%)
```

`_evaluate` / `_evaluate_rate_only` 분기에 fast window 추가 평가. fast window 는 별도 `_fast_window_*` 카운터 유지:

```python
# QuoteSessionHealthMonitor.__init__
self._fast_window_total: dict[str, int] = {}
self._fast_window_failures: dict[str, int] = {}
self._fast_window_start: dict[str, datetime] = {}

def _bump_window(self, label: str, *, failure: bool) -> None:
    # 기존 5분 윈도우 (보존)
    ...
    # 신규 1분 fast 윈도우
    now = datetime.now(_KST)
    fast_start = self._fast_window_start.get(label)
    if fast_start is None or (now - fast_start) > timedelta(seconds=FAST_WINDOW_SECS):
        self._fast_window_start[label] = now
        self._fast_window_total[label] = 1
        self._fast_window_failures[label] = 1 if failure else 0
        return
    self._fast_window_total[label] = self._fast_window_total.get(label, 0) + 1
    if failure:
        self._fast_window_failures[label] = self._fast_window_failures.get(label, 0) + 1

async def _evaluate(self, label: str, reason: str) -> None:
    # 기존 임계 (consecutive ≥ 5 || 5분 50%)
    ...
    
    # 신규: 1분 80% fast window (위 분기 hit 안 한 경우만 추가 평가)
    fast_total = self._fast_window_total.get(label, 0)
    fast_failures = self._fast_window_failures.get(label, 0)
    if fast_total >= FAST_MIN_CALLS:
        fast_rate = fast_failures / fast_total
        if fast_rate >= FAST_MAX_FAILURE_RATE:
            trigger_reason = (
                f"fast_window_failure_rate={fast_rate:.2f} threshold={FAST_MAX_FAILURE_RATE} "
                f"fast_window_total={fast_total} fast_window_failures={fast_failures} "
                f"last_reason={reason}"
            )
            await self._auto_disable(label, trigger_reason)
            return
```

`reset()` 메서드에도 fast window 키 추가 clear.

**회귀 가드** (`tests/unit/services/test_quote_session_health.py` 확장, 신규 3 케이스):

1. `test_fast_window_80pct_failure_in_1min_triggers_disable` — 1분 내 10회 호출, 8회 실패 → 자동 비활성 발화 (consecutive 5 미달, 5분 윈도우 50% 미달 상황에서 fast window 가 발화하는지 확인)
2. `test_fast_window_below_min_calls_does_not_trigger` — 1분 내 5회 호출 모두 실패 (rate=1.0 이지만 total<10) → 비활성 안 됨
3. `test_fast_window_resets_after_60s` — `freezegun` 61s 점프 후 fast window 리셋 + 임계 재평가

### A-3. 메인 fallback 우선 정책 (`_select_quote_label` 또는 `_request_via_quote_pool`)

**목표**: ISA 가 *최근 5xx 비율* 높으면 해당 호출 *즉시* 메인 fallback. 보조 라벨 3회 재시도 backoff 누적 회피 → 응답 지연 ms → s 단위 감소.

**구현 명세**:

`QuoteSessionHealthMonitor` 에 신규 조회 API 추가:

```python
# src/services/quote_session_health.py

def get_recent_5xx_ratio(self, label: str) -> tuple[float, int]:
    """라벨의 fast window (1분) 실패율 + 총 호출 수 반환.
    
    Returns:
        (ratio, total) — total < FAST_MIN_CALLS 면 ratio=0.0 (평가 불가).
    """
    if label in self._disabled_labels:
        return (1.0, FAST_MIN_CALLS)  # 비활성된 라벨은 항상 메인 fallback 트리거
    total = self._fast_window_total.get(label, 0)
    failures = self._fast_window_failures.get(label, 0)
    if total < FAST_MIN_CALLS:
        return (0.0, total)
    return (failures / total, total)
```

`_request_via_quote_pool` 의 라벨 선택 직후 (현재 `manager = await get_token_manager(label)` 진입 전) 분기:

```python
# 신규 상수 (모듈 레벨)
_LABEL_FALLBACK_5XX_RATIO_THRESHOLD = 0.8  # 80%+ fast window 면 메인 fallback

# 변경: 라벨 선택 후 health 체크
label = await _select_quote_label()
if label is not None:
    try:
        from src.services.quote_session_health import health_monitor as _hm
        ratio, total = _hm.get_recent_5xx_ratio(label)
        if total >= FAST_MIN_CALLS and ratio >= _LABEL_FALLBACK_5XX_RATIO_THRESHOLD:
            logger.info(
                "[quote_pool] 보조 라벨 fast window 5xx %.0f%% (total=%d) — 메인 fallback (label=%s)",
                ratio * 100, total, label,
            )
            label = None  # 메인 fallback 강제
    except Exception:
        logger.debug("[quote_pool] health_monitor get_recent_5xx_ratio 호출 실패", exc_info=True)

# 기존 토큰 매니저 로직 진행
manager = None
if label is not None:
    ...
```

**회귀 가드** (`tests/unit/api/test_quote_pool_label_skip.py` 확장 또는 신규 5 케이스):

1. `test_label_5xx_80pct_skips_to_main_fallback` — fast window 10/12 실패 → label=None 으로 강제, actual_label="main" 결과
2. `test_label_5xx_below_threshold_uses_secondary` — 5xx 50% → 보조 라벨 그대로 사용 (기존 동작 보존)
3. `test_label_with_insufficient_calls_uses_secondary` — total<10 → 보조 사용 (premature decision 차단)
4. `test_disabled_label_always_skipped` — `_disabled_labels` 에 등록된 라벨 → 메인 fallback (sanity guard, 이미 `_select_quote_label` 에서 제외되지만 race 대비)
5. `test_label_skip_metric_recorded` — fallback 진입 시 별도 메트릭 카운터 1 증가 (예: `_quote_request_metrics["fast_fallback"]` 신규 키, 운영 가시화)

### A-4. (문서만) 운영자 안내 — `src/api/CLAUDE.md` 1행 추가

> "ISA 같이 5xx 빈발 보조 라벨은 Settings UI 에서 active=false 수동 비활성 권장. health_monitor 자동 비활성 임계 (FAST_WINDOW 1분 80% / 5분 50% / consecutive 5) 충족 전 운영자 개입 가능"

코드 변경 0.

---

## 3. 영역 B — UI 끊김 표시 보강 (프론트엔드)

### B-1. 백엔드 응답에 stale 종목별 `last_tick_at` 노출

**대상**: `GET /api/realtime/subscriptions` (`src/routes/realtime.py`)

기존 응답 `tickers.stale` 은 sorted ticker 리스트. 신규 필드 `last_tick_map: Record<ticker, ISO_KST_string | null>` 추가 — stale 종목별 마지막 tick 시각 (없으면 null).

```python
# src/routes/realtime.py::get_subscriptions 응답 data 에 추가
last_tick_map: dict[str, str | None] = {}
for ticker in sorted(stale_set):
    last_dt = ticker_last_tick.get(ticker)
    if last_dt is None or last_dt == _min_dt:
        last_tick_map[ticker] = None
    else:
        last_tick_map[ticker] = last_dt.isoformat()  # KST tz 포함

data = {
    ...
    "last_tick_map": last_tick_map,
    ...
}
```

**프론트 타입 동기화** (`frontend/src/types/realtime.ts` 또는 상응):

```typescript
export interface RealtimeSubscriptionsData {
  total: number
  acked: number
  fresh_60s: number
  stale_60s: number
  limit: number
  tickers: { subscribed: string[]; acked: string[]; fresh: string[]; stale: string[] }
  last_tick_map: Record<string, string | null>  // 신규 — stale ticker → ISO KST
  reconnect_count: number
  ws_connected: boolean
  sessions: SessionStatus[]
}
```

### B-2. 활성 보드 시간대 컨텍스트 (`ScanMonitor.tsx`)

시간대 분류 함수 추가:

```tsx
type StaleContext = 'normal_quiet' | 'pre_open' | 'main_critical' | 'unknown'

function getStaleContextByKstMinutes(t: number): StaleContext {
  // t = h*60 + m, KST
  if (t >= 9 * 60 && t < 15 * 60 + 30) return 'main_critical'   // KRX 메인 - stale = 결함
  if (t >= 8 * 60 && t < 9 * 60) return 'pre_open'              // PRE_NXT - 거래량 적음, 경계
  if ((t >= 15 * 60 + 30 && t < 20 * 60) || t < 8 * 60 || t >= 20 * 60) return 'normal_quiet'
  return 'unknown'
}

const STALE_CONTEXT_META: Record<StaleContext, { label: string; color: string; tone: 'red'|'yellow'|'gray' }> = {
  main_critical: { label: 'KRX 메인 — stale 결함 가능', color: 'text-red-700 bg-red-50', tone: 'red' },
  pre_open: { label: 'NXT 프리 — 거래량 적음, 관찰', color: 'text-yellow-700 bg-yellow-50', tone: 'yellow' },
  normal_quiet: { label: '시간 외 거래 한산 시 정상', color: 'text-gray-600 bg-gray-50', tone: 'gray' },
  unknown: { label: '', color: '', tone: 'gray' },
}
```

`tick_coverage_stale > 0` 진단 영역에 컨텍스트 안내 문구 추가 — 끊김 배지 옆 (또는 아래) 시간대별 톤 분기. 진단 배지 색상은 기존 stale 수 기반 유지 (red/yellow/gray) 하되, "끊김 N종목" 텍스트 옆에 추가 라벨 (시간대):

```tsx
{tcStale > 0 && (
  <span className="text-[10px] text-gray-500 ml-1">
    ({STALE_CONTEXT_META[getStaleContextByKstMinutes(getKstMinutes())].label})
  </span>
)}
```

활성 보드 배지 옆 안내 텍스트:

```tsx
{/* 기존 활성 보드 배지 라인에 추가 */}
<span className="text-[10px] text-gray-400 ml-1">
  (시간 외 거래 한산 종목은 정상)
</span>
```

### B-3. stale 종목 행에 마지막 tick 시각 표시 (펼치기 옵션)

현재 ScanMonitor 에 stale 종목 개별 리스트 펼치기 없음. 신규 토글 추가:

```tsx
const [staleListOpen, setStaleListOpen] = useState(false)

// tcStale > 0 + 끊김 배지 아래
{tcStale > 0 && (
  <button onClick={() => setStaleListOpen(!staleListOpen)} className="text-xs text-amber-600 hover:underline">
    {staleListOpen ? '끊김 종목 접기' : `끊김 종목 보기 (${tcStale}개)`}
  </button>
)}
{staleListOpen && subscriptions?.last_tick_map && (
  <div className="mt-1 text-xs text-gray-600 max-h-32 overflow-y-auto">
    {subscriptions.tickers.stale.map((ticker) => {
      const lastTick = subscriptions.last_tick_map[ticker]
      const lastTickLabel = lastTick
        ? new Date(lastTick).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
        : '—'
      return (
        <div key={ticker} className="flex justify-between py-0.5 border-b border-gray-50 last:border-0">
          <span className="font-mono">{ticker}</span>
          <span className="text-gray-500">마지막: {lastTickLabel}</span>
        </div>
      )
    })}
  </div>
)}
```

`useTradingStatus` 외에 `getSubscriptions` 호출이 필요하므로 `useQuery({queryKey:['realtime-subscriptions']})` 활용 (KisAccountPoolCard 와 동일 큐, staleTime 5s — 동일 캐시 공유).

### B-4. 회귀 가드 (`frontend/src/components/__tests__/ScanMonitor.stale-context.test.tsx`, 신규 5 케이스)

1. `KRX 메인 시간 + stale=5 → "stale 결함 가능" 빨강 라벨 노출`
2. `NXT 애프터 시간 + stale=19 → "한산 시 정상" 회색 라벨 노출`
3. `PRE_NXT 시간 + stale=3 → "관찰" 노랑 라벨 노출`
4. `stale=0 → 컨텍스트 라벨 미노출`
5. `펼치기 토글 + last_tick_map 으로 ticker 별 마지막 tick 시각 (HH:MM:SS) 표시`

---

## 4. 영역 C — "돌파" 라벨 매매 가능 컨텍스트 (프론트엔드)

### C-1. 백엔드 응답에 전략별 `tradable_boards` 노출

**대상**: `GET /api/trading/status` 의 `strategies[*]` 에 `tradable_boards: string[]` 추가.

`StrategyInfo` 모델에 필드 추가:

```python
# src/models/response.py (또는 trading.py)
class StrategyInfo(BaseModel):
    ...
    tradable_boards: list[str]  # 신규 — DEFAULT_TRADABLE_BOARDS 또는 strategy_config.params.tradable_boards
```

`src/engine/scheduler.py::get_trading_status()` 또는 `StrategyRegistry.get_status_payload()` 에서 각 전략 직렬화 분기에 `tradable_boards` 포함:

```python
# StrategyBase 또는 registry 측 directory hint
strat_payload["tradable_boards"] = (
    list(strategy.config.params.get("tradable_boards") 
         or strategy.DEFAULT_TRADABLE_BOARDS)
)
```

이미 `params` 에 포함되어 있을 가능성 — 그 경우 *별도 최상위 키* 로도 노출해서 프론트 단순화.

### C-2. "돌파" 라벨 분기 (`ScanMonitor.tsx`)

기존 분기 (line ~951):
```tsx
if (curPrice >= targetPrice && targetPrice > 0) {
  return <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 font-medium">돌파</span>
}
```

변경:
```tsx
if (curPrice >= targetPrice && targetPrice > 0) {
  // 활성 보드 ∩ 전략 tradable_boards = 매매 가능 보드
  const strat = strategies[selectedStrategy]
  const stratBoards: string[] = (strat?.tradable_boards ?? []) as string[]
  const activeBoardCodes = activeBoards.map((b) => b.code)
  const tradableNow = stratBoards.filter((b) => activeBoardCodes.includes(b))
  
  if (tradableNow.length > 0) {
    // 매매 가능 시간대 — 기존 빨강 라벨
    return <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 font-medium">돌파</span>
  }
  
  // 매매 불가 시간대 — 회색 톤 + 매매 가능 보드 안내
  const tradableLabels = stratBoards
    .map((b) => BOARD_META[b]?.label ?? b)
    .join('/')
  return (
    <span 
      className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-medium"
      title={`이 전략은 ${tradableLabels} 에서만 매매. 현재 활성 보드 ∩ 전략 보드 = 없음`}
    >
      돌파 (대기 — {tradableLabels})
    </span>
  )
}
```

### C-3. 회귀 가드 (`frontend/src/components/__tests__/ScanMonitor.breakout-label.test.tsx`, 신규 5 케이스)

1. `VB + PRE_NXT 시간 + curPrice >= target → 빨강 "돌파" (활성 보드 = pre_nxt, tradable = [pre_nxt, main] → 교집합 ∋)`
2. `VB + POST_NXT 시간 + curPrice >= target → 회색 "돌파 (대기 — 프리/메인)" (활성 = post_nxt, tradable = [pre_nxt, main] → 교집합 = ∅)`
3. `LTV + KRX 메인 시간 + curPrice >= target → 빨강 "돌파" (활성 = main, tradable = [pre_nxt, main] → 교집합 ∋)`
4. `BFB + POST_NXT 시간 + curPrice >= target → 회색 "돌파 (대기 — 메인)" (BFB tradable=[main])`
5. `tradable_boards 미존재 (백엔드 응답 호환 시점) → 기존 빨강 "돌파" fallback (안전 회귀)`

### C-4. TypeScript 타입 동기화 (`frontend/src/types/trading.ts`)

```typescript
export interface StrategyInfo {
  ...
  tradable_boards?: string[]  // 신규 — DEFAULT_TRADABLE_BOARDS 또는 params 의 tradable_boards
}
```

`?` 옵셔널 — 백엔드 미반영 시점 호환 (안전 fallback).

---

## 5. 검증 (tester 위임)

### 백엔드 회귀
```bash
python -m pytest tests/unit/api/test_quote_pool_5xx_dedupe.py \
                 tests/unit/services/test_quote_session_health.py \
                 tests/unit/api/test_quote_pool_label_skip.py -v

# 전체 회귀 — 기대 0
python -m pytest -q
```

### 프론트 회귀
```bash
cd frontend
npm test  # 신규 vitest 10 케이스 + 전체 회귀 0
```

### 영향 인덱스 재생성
```bash
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
```

### 운영 시나리오 검증
1. **ISA 5xx 80%+ → 즉시 메인 fallback** (mock 5xx 응답 12회/1분 → 다음 호출 actual_label="main" 확인)
2. **5xx dedupe** — 동일 ISA 100회 5xx → WARNING 1회 + 60s 후 INFO summary 1회 (총 2행)
3. **fast window 자동 비활성** — 1분 10회 호출 9회 실패 → `_disabled_labels` 등록 + `[quote_session_disabled]` 영구 로그
4. **UI 끊김 컨텍스트** — KRX 메인 시간 stale=5 빨강 / NXT 애프터 stale=19 회색
5. **돌파 (대기)** — POST_NXT 시간 VB 돌파 종목 → "돌파 (대기 — 프리/메인)" 회색

---

## 6. 문서 동기화 (sync-docs)

| 파일 | 변경 |
|------|------|
| `src/api/CLAUDE.md` | 5xx dedupe 60s 윈도우 + summary task / 메인 fallback 우선 정책 / health_monitor 임계 강화 (FAST_WINDOW) / ISA 운영자 안내 1행 |
| `src/services/CLAUDE.md` (있다면) | quote_session_health FAST_WINDOW 임계 + `get_recent_5xx_ratio` API |
| `src/routes/CLAUDE.md` | `/api/realtime/subscriptions` 응답에 `last_tick_map` 추가 |
| `frontend/CLAUDE.md` | ScanMonitor stale 컨텍스트 분기 + "돌파 (대기)" 라벨 + StrategyInfo.tradable_boards |
| `docs/HARNESS_CHANGELOG.md` | 사이클 18 1행 |

---

## 7. 커밋 단위

가능하면 단일 커밋:
```
사이클18: ISA 500 폭주 정리 + UI 끊김/돌파 컨텍스트
```

부득이 분리 시:
1. `feat(api/services): ISA 5xx dedupe + fast window 임계 + 메인 fallback 우선`
2. `feat(frontend): 끊김 시간대 컨텍스트 + 돌파 대기 라벨 + tradable_boards 노출`
3. `docs: 사이클 18 동기화` (위 둘에 포함하지 않은 경우)

## 8. 보고 (tester 검증 후)

1. 변경 파일 N개 + LOC 변화
2. 신규 회귀 가드 케이스 수 (백엔드 ~13 / 프론트 ~10) + pass 결과
3. 백엔드/프론트 회귀 카운트 변화
4. 커밋 해시
5. sync-docs 결과
6. push 보류 사유 + 권장 push 시점 (KRX 메인 마감 후 NXT 애프터 시작 전 권장 19:30 또는 익일 07:50 _boot 전)
