# 사이클 21 — UI 정리: 구독현황 이동 + 전략별 필터링 강화

## 배경 (사용자 요구, 2026-05-20)

> "조건검색현황 하단의 구독현황과 끊김 종목은 전략별로 흩어질 필요 없음. 조건검색에는 필터링 부분만 강조. 어떤 조건을 통해 필터링 되었는지 (모범사례: donchian-swing). 전략별 필터링 데이터를 자세하게 정리해서 반영하고 구독현황은 상단의 KIS 시세풀에 겹치는 부분을 제외하고 반영."

## 트레이더 관점 진단

ScanMonitor 가 두 책임을 동시에 가지고 있어 가시성이 흐려진 상태:
- **(1) 전략별 필터링 깔때기 가시화** — 운영자가 "왜 신호가 안 나오는지" 단계별 추적
- **(2) WS 구독 인프라 상태** — fresh/stale/ACK + 끊김 종목 + 수동 재구독

KisAccountPoolCard 는 이미 KIS 시세 풀의 세션별 fresh/stale 카운트를 노출하지만 **끊김 종목 목록과 수동 재구독은 ScanMonitor 에 갇혀** 있어 인프라 화면이 반쪽짜리.

donchian_swing 은 8단계 깔때기(universe_candidates → universe_filtered → candle_fetch_ok → donchian_pass → ema_uptrend_pass → volume_pass → atr_pass → final_prepared)를 노출하지만 VB/LTV/momentum 은 카운트 없이 로그만 → "왜 VB 신호 0건인지" 운영자 추적 불가.

## 4 영역 작업

### A. 백엔드 — VB/LTV/momentum `_scan_stats` 추가

donchian_swing 의 `_empty_scan_stats()` + `_scan_stats` 누적 + `get_scan_stats()` 패턴 재사용.

#### A-1. `src/engine/strategies/volatility_breakout.py`

`_empty_scan_stats()` 키:
```python
{
    "universe_candidates": 0,    # blng 0/1/3 합집합 (현재 ~41)
    "universe_filtered": 0,      # ETF 키워드 제외 + ticker 6자리 + 시총·거래대금 통과
    "price_filtered": 0,         # 가격>0 + listed>0 + prdy_vol>0 + prdy_close>0 (필수)
    "mcap_pass": 0,              # 시총 ≥ min_market_cap (1,000억) 통과 단독 카운트
    "trade_amount_pass": 0,      # 거래대금 ≥ min_trade_amount (200억) 통과 단독 카운트
    "candle_fetch_ok": 0,        # K값/Target 계산용 일봉 fetch 성공
    "k_value_computed": 0,       # noise_list 비공집합 + prev_range>0 + target_offset>0 → _targets 등록
    "final_prepared": 0,         # _scanned_tickers 최종 개수 (== k_value_computed)
    "last_run_at": None,         # KST ISO timestamp
}
```

구현 위치:
- `__init__`: `self._scan_stats = _empty_scan_stats()`
- `prepare()` 진입 시: `stats = _empty_scan_stats(); self._scan_stats = stats`
- `_scan_universe()` 내 카운트 갱신:
  - `universe_candidates`: BLNG_CODES 루프 종료 후 `len(rank_items)`
  - 루프 안 `price>0 and listed>0 and prdy_vol>0 and prdy_close>0` → `price_filtered += 1`
  - 그 이후 `mcap >= min_mcap` → `mcap_pass += 1` (단독)
  - 그 이후 `prdy_trade_amt >= min_trade` → `trade_amount_pass += 1` (단독)
  - 두 조건 모두 통과 → `universe_filtered += 1` (== filtered 길이)
- `prepare()` 내 `_fetch_one` gather 후: `candle_fetch_ok = sum(1 for _, c in fetched if c is not None)`
- `prepare()` 본문 loop 끝: `k_value_computed = prepared`
- `prepare()` 끝 `final_prepared = len(self._scanned_tickers); last_run_at = datetime.now(KST).isoformat()`

`get_scan_stats(self) -> dict` 메서드 추가 (donchian 동일 시그니처):
```python
def get_scan_stats(self) -> dict:
    return dict(self._scan_stats)
```

#### A-2. `src/engine/strategies/long_tail_volatility.py`

VB 와 거의 동일하되 **추가 단계**:
- `consecutive_limit_pass`: 연속상한가(N일 이상) 제외 통과 카운트 (`_is_consecutive_limit_up` False 인 종목)
- 본 키는 LTV 만 추가, 나머지는 VB 와 동일

```python
{
    "universe_candidates": 0,
    "universe_filtered": 0,
    "price_filtered": 0,
    "mcap_pass": 0,
    "trade_amount_pass": 0,
    "candle_fetch_ok": 0,
    "consecutive_limit_pass": 0,  # LTV 전용
    "k_value_computed": 0,
    "final_prepared": 0,
    "last_run_at": None,
}
```

구현 위치 VB 와 동일 + `_is_consecutive_limit_up` 분기에서 `if not consecutive: stats["consecutive_limit_pass"] += 1` 또는 더 명확히 통과/탈락 분리.

#### A-3. `src/engine/strategies/momentum.py`

momentum 은 prepare 단계가 없고 09:30 실시간 `scan_stocks()` 기반. 단, 09:30 직후 `_prev_prdy_rate` 등록 시점이 prepare 와 유사 — `scanner.scan_stocks()` 의 단계 출력 (`source_counts`) 를 momentum 의 `_scan_stats` 로 매핑.

`MomentumStrategy._scan_stats` (간소화 — momentum 은 prepare 가 비어 있어 실시간 scan 기준):
```python
{
    "universe_candidates": 0,    # 등락률 순위 API 전체 응답
    "rate_pass": 0,              # 등락률 컷 (전일대비 N% 이상)
    "mcap_pass": 0,              # 시총 컷
    "trade_amount_pass": 0,      # 거래대금 컷
    "limit_up_excluded": 0,      # +30% 상한가 제외 카운트
    "final_prepared": 0,         # 최종 후보 = scanner.scan_stocks() 결과
    "last_run_at": None,
}
```

**중요**: momentum 은 `scanner.scan_stocks()` 외부 함수를 사용. 직접 카운트 갱신 불가 → 두 가지 선택:
- **Option A (권장)**: `scanner.scan_stocks()` 반환에 `filter_stats` 추가 → `MomentumStrategy` 가 그것을 `self._scan_stats` 에 복사
- Option B: `MomentumStrategy.scan_stocks_wrapper()` 헬퍼 추가 — 거부 (스캐너 책임 분리 위반)

→ **Option A 채택**. backend-dev 가 `scanner.scan_stocks()` 시그니처 확장 + `MomentumStrategy._scan_stats` 매핑 구현.

`scan_stocks()` 가 dict 반환 변경 시 호출처(scheduler.py)도 영향. 신중히 — 또는 별도 `scan_stocks_with_stats()` 분기 추가.

**최소 변경 안 (Option A 변형)**: `scanner.scan_stocks()` 가 기존 `filtered_tickers` 리스트 반환 유지 + 모듈 내 `scan_filter_stats` 전역 dict 도입 → momentum 이 그것을 읽어 `self._scan_stats` 매핑. scheduler 영향 0.

```python
# scanner.py
scan_filter_stats: dict = {
    "universe_candidates": 0,
    "rate_pass": 0,
    "mcap_pass": 0,
    "trade_amount_pass": 0,
    "limit_up_excluded": 0,
    "final_prepared": 0,
    "last_run_at": None,
}

async def scan_stocks():
    ...
    scan_filter_stats["universe_candidates"] = len(items)
    ...
    return filtered_tickers
```

momentum 의 `get_scan_stats()`:
```python
def get_scan_stats(self) -> dict:
    from src.engine.scanner import scan_filter_stats
    return dict(scan_filter_stats)
```

#### A-4. `src/engine/strategy_registry.py::get_strategies_status()`

이미 `hasattr(s, 'get_scan_stats')` 분기로 노출 중 (130~132 라인). VB/LTV/momentum 에 메서드 추가만으로 자동 노출. 별도 변경 없음.

### B. 프론트 — ScanMonitor 에서 구독 인프라 제거

#### B-1. 제거할 영역 (`ScanMonitor.tsx` 282~399 라인)

전체 제거:
- `tick-coverage-badge` — fresh/stale/ACK 카운트
- `tick-coverage-progress` — 진행바
- `stale-context-label` — 시간대 컨텍스트
- 인라인 재구독 버튼 (`resubMutation.mutate()`)
- `resubMsg` 인라인 메시지
- `stale-list-toggle` + 끊김 종목 표 (last_tick_at)

**보존 대상**: ScanMonitor 헤더 "구독 중 N개" 표시 — 가벼운 개요 (전체 가시성). 단순 카운트만 (fresh/stale 분리 안 함).

#### B-2. 보존할 영역

- 활성 보드 배지 (KST 시각 → SessionTracker)
- `phase` 라벨 (PHASE_LABELS)
- 전략 탭별 필터링 깔때기 (donchian 모범 → BFB/VCP 기존 + VB/LTV/momentum 신규)
- VB/LTV 보드별 시가/타겟가 테이블
- "돌파" 라벨 매매 컨텍스트 (사이클 18)
- donchian "도움말 펼치기" 토글

### C. 프론트 — KisAccountPoolCard 에 구독 인프라 통합

#### C-1. 추가할 영역 (`KisAccountPoolCard.tsx`)

세션별 표 *아래* 또는 총 슬롯 패널 *옆* 에 신규 영역:

**(1) 시간대 컨텍스트 라벨**:
- `stale_60s > 0` 시 `data-testid="stale-context-label"` 노출
- KRX 메인 (09:00~15:30) = "결함 가능" 빨강 / PRE_NXT (08:00~09:00) = "거래량 적음" 노랑 / 그 외 = "한산 시 정상" 회색
- `getStaleContextByKstMinutes(t)` 헬퍼 — ScanMonitor 에서 추출 → `utils/stale-context.ts` 신규 파일로 이동 (재사용)

**(2) 수동 재구독 버튼**:
- `stale_60s > 0` 시 `pool-resubscribe-button` 인라인 노출
- 클릭 `useMutation(resubscribeStale)` (기존 ScanMonitor 와 동일 API)
- 성공 시 `invalidateQueries({queryKey:['realtime-subscriptions']})` + "N종목 재구독 완료" 인라인 메시지

**(3) 끊김 종목 펼치기**:
- `pool-stale-list-toggle` 버튼 — `subscriptions.tickers?.stale?.length > 0` 시 노출
- 클릭 시 종목별 `data-testid="pool-stale-row-{ticker}"` + 마지막 tick 시각 (KST HH:MM:SS, `Intl.DateTimeFormat('en-GB', timeZone='Asia/Seoul')`)
- `last_tick_map[ticker]=null` → "—"
- max-h-32 + overflow-y-auto + border

#### C-2. ScanMonitor 와 데이터 소스 통일

KisAccountPoolCard 는 이미 `useQuery(['realtime-subscriptions'])` 사용. ScanMonitor 도 동일 큐 사용 중 → ScanMonitor 의 `subscriptions` 사용 제거하면 큐 1개로 통합 (부하 감소).

### D. 프론트 — VB/LTV/BFB/VCP/momentum 단계별 깔때기 시각화

#### D-1. ScanMonitor 의 SWING_STAGES 패턴 재사용

donchian_swing 의 단계별 막대 (667~ 라인 "조건 통과 단계별 후보 수")를 모든 전략에 동일 패턴 적용:

```typescript
// 전략별 STAGES 정의
const VB_STAGES = [
  { key: 'universe_candidates', label: '유니버스 후보 (blng 0/1/3 합집합)' },
  { key: 'price_filtered', label: '가격/상장주식수 필수값' },
  { key: 'mcap_pass', label: '시총 ≥ 1,000억' },
  { key: 'trade_amount_pass', label: '거래대금 ≥ 200억' },
  { key: 'universe_filtered', label: '유니버스 확정 (시총+거래대금 동시)' },
  { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
  { key: 'k_value_computed', label: 'K값/Target 계산 완료' },
  { key: 'final_prepared', label: '최종 prepared' },
] as const;

const LTV_STAGES = [
  ...VB_STAGES.slice(0, 5),
  { key: 'candle_fetch_ok', label: '일봉 fetch 성공' },
  { key: 'consecutive_limit_pass', label: '연속상한가 제외' },
  { key: 'k_value_computed', label: 'K값/Target 계산' },
  { key: 'final_prepared', label: '최종 prepared' },
] as const;

const MOMENTUM_STAGES = [
  { key: 'universe_candidates', label: '등락률 순위 응답' },
  { key: 'rate_pass', label: '등락률 컷' },
  { key: 'mcap_pass', label: '시총 컷' },
  { key: 'trade_amount_pass', label: '거래대금 컷' },
  { key: 'limit_up_excluded', label: '상한가(+30%) 제외' },
  { key: 'final_prepared', label: '최종 후보' },
] as const;
```

#### D-2. 렌더링

donchian 의 668~ 라인 막대 컴포넌트를 함수로 추출 → 5 전략(donchian/VB/LTV/momentum/BFB/VCP) 모두 재사용.

```typescript
function ScanFunnelBars({ stages, stats, theme }: { stages: ReadonlyArray<{key:string,label:string}>; stats: Record<string, unknown> | null | undefined; theme: 'emerald'|'teal'|'indigo' }) {
  ...
}
```

각 전략 탭에 배치:
- VB 탭 / LTV 탭: 보드별 시가/타겟가 테이블 *위* 깔때기
- momentum 탭: "종목 리스트 펼치기" *위* 깔때기
- BFB / VCP 탭: 기존 `universe_filtered / universe_candidates` 한 줄 요약을 깔때기 막대로 확장

#### D-3. 옵셔널 타입 가드

백엔드 `scan_stats` 가 아직 반영 안 된 시점 호환:
```typescript
const stats = strategyData?.scan_stats as Record<string, number | string | null> | null;
if (!stats) {
  return <div className="text-xs text-gray-400">아직 스캔 전</div>;
}
```

`scan_stats` 가 모든 필수 키를 갖지 않을 수 있음 → `(stats?.[key] as number ?? 0)`.

## 검증

### 백엔드 회귀

```bash
python -m pytest tests/unit/engine/test_volatility_breakout_scan_stats.py \
                 tests/unit/engine/test_long_tail_volatility_scan_stats.py \
                 tests/unit/engine/test_momentum_scan_stats.py -v
# 기대: 9 신규 케이스 pass

python -m pytest -q
# 기대: 회귀 0
```

### 프론트 회귀

```bash
cd frontend && npm test
# 기대: 회귀 0 + ScanMonitor 제거 검증 + KisAccountPoolCard 끊김 종목 추가
```

### 영향 인덱스

```bash
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
```

## 회귀 가드 (15+ 케이스)

### 백엔드 신규

**`tests/unit/engine/test_volatility_breakout_scan_stats.py`** (3 케이스):
1. `_empty_scan_stats()` 가 9 키 dict 반환 (universe_candidates 등) — 초기값 0/None
2. `prepare()` 후 각 단계 카운트가 fixture API mock 응답 기준 올바르게 누적
3. `get_scan_stats()` 가 `_scan_stats` 사본 반환 (외부 수정 격리)

**`tests/unit/engine/test_long_tail_volatility_scan_stats.py`** (3 케이스):
1. `_empty_scan_stats()` 가 10 키 dict (consecutive_limit_pass 포함)
2. `prepare()` 시 연속상한가 종목 → `consecutive_limit_pass` 미증가, `candle_fetch_ok` 는 증가
3. `get_scan_stats()` 사본 반환

**`tests/unit/engine/test_momentum_scan_stats.py`** (3 케이스):
1. `scan_filter_stats` 가 모듈 dict 로 7 키 초기화
2. `scan_stocks()` 호출 후 카운트 누적 (mock API 응답 기준)
3. `MomentumStrategy.get_scan_stats()` 가 모듈 dict 사본 반환

### 프론트 갱신/신규

**`ScanMonitor.test.tsx`** 갱신 (제거 + 신규):
- `tick-coverage-badge`/`stale-list-toggle`/`stale-context-label`/`tick-coverage-progress` 케이스 **삭제 또는 KisAccountPoolCard 로 이전**
- 신규: VB 탭 / LTV 탭 / momentum 탭 각각 깔때기 막대 렌더 케이스 (5+)
- 신규: `scan_stats` 미반영 시 fallback "아직 스캔 전" 표시

**`KisAccountPoolCard.test.tsx`** 갱신:
- `pool-resubscribe-button` stale > 0 노출 + 클릭 시 mutation 발사 (1)
- `pool-stale-list-toggle` 펼치기 → `pool-stale-row-{ticker}` 종목별 시각 표시 (1)
- `stale-context-label` 시간대 매핑 (KRX 메인=빨강 / PRE_NXT=노랑 / 그 외=회색) (3)

**사이클 18 테스트 이전**:
- `ScanMonitor.stale_context.test.tsx` → `KisAccountPoolCard.stale_context.test.tsx`
- `ScanMonitor.breakout_label.test.tsx` 는 ScanMonitor 유지 (BREAKOUT_KEYS 4종 매매 컨텍스트)

## sync-docs

- `src/engine/strategies/CLAUDE.md` — VB/LTV/momentum 의 `_scan_stats` 명세 추가 (공통 패턴 섹션)
- `src/engine/CLAUDE.md` — `get_strategies_status()` 응답 키 갱신 (이미 자동 노출)
- `src/engine/scanner.py` 의 `scan_filter_stats` 전역 dict 도입 (momentum용)
- `frontend/CLAUDE.md` — ScanMonitor / KisAccountPoolCard 변경 사항
  - ScanMonitor: tick-coverage 영역 제거 / scan_funnel 컴포넌트 추가
  - KisAccountPoolCard: 끊김 종목 펼치기 / 수동 재구독 / 시간대 컨텍스트 흡수
- `docs/HARNESS_CHANGELOG.md` — 사이클 21 1행

## 안전 원칙 (회귀 0)

- **매매 코드 변경 0** — `risk.on_tick` / `order_engine` 무관. `prepare()` 내 카운터 추가만
- **사이클 17/18/6/19/20 보존** — OPSP backoff (300s) / K stale watcher / 5xx dedupe / 토큰 직렬화 / `_selling` 가드
- **백엔드 응답 호환** — `scan_stats` 키 *추가* 만, 기존 키 제거 0
- **프론트 옵셔널 타입** — 백엔드 미반영 시점 호환 fallback ("아직 스캔 전")
- **TDD** — tdd-engineer Red → backend-dev + frontend-dev Green → tester 검증
- **한글 커밋 메시지**: `refactor(ui): 구독현황 KisAccountPoolCard 통합 + 전략별 필터링 단계 강화 (사이클 21)`
- **push 별도 명시 승인** — 사이클 20 (35ebe3a) 와 함께 익일 07:50 _boot 전 권장

## 우선순위

1. 백엔드 `_scan_stats` (3 전략 + scanner.scan_filter_stats) — 의존성 0, 안전
2. 프론트 KisAccountPoolCard 통합 — ScanMonitor 의 ResubMutation/StaleList 이전
3. 프론트 ScanMonitor 정리 — 인프라 영역 제거
4. 프론트 ScanMonitor 필터링 깔때기 강화 (5 전략 SCAN_FUNNEL)
5. 회귀 가드 (15+ 케이스)
6. sync-docs + 단일 커밋
