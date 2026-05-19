# CLAUDE.md — frontend/ (React 대시보드)

React + TypeScript + Vite 트레이딩 대시보드.

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## 실행

```bash
npm install
npm run dev    # http://localhost:5173
npm run build  # 타입 체크 포함
npm run lint
```

## 디렉토리

```
src/
├── api/       # axios 호출 (client.ts: baseURL, 인터셉터)
├── components/
├── contexts/  # TradingStatusContext 등
├── pages/
└── types/     # 백엔드 src/models/ pydantic 1:1 매핑
```

## 핵심 라이브러리

TanStack Query (서버 상태) · TanStack Table (그리드) · Recharts (차트) · Tailwind v4 · React Router

## 단일 polling owner

- `contexts/TradingStatusContext.tsx::TradingStatusProvider` 가 `/api/trading/status` 를 5초 폴링하는 단일 소스. 자식은 `useTradingStatus()` hook 공유 (중복 폴링 차단)
- App.tsx 최상위 wrap
- QueryClient defaults: `staleTime: 3000` / `gcTime: 5*60*1000` / `retry: 1` / `refetchOnWindowFocus: false`

## 페이지 lazy 로딩

Dashboard 만 즉시 import. History/Recommendations/Logs/Settings 는 `React.lazy()` + Suspense skeleton (초기 번들 819→656kB). `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환 보존.

## 시각적 컨벤션

- 이익 `#FF3333` (빨강) / 손실 `#3366FF` (파랑) / 보합 `#333333`
- 금액: 천 단위 콤마 / 수익률: 소수 2자리 + %
- 환경 배너: 실전=빨강 "실전 매매 환경" / 모의=녹색 "모의투자 환경"
- **시각 표시는 KST 강제** — `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ... })` 또는 `toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })`. `new Date(iso).getHours()/getFullYear()` 등 브라우저 로컬타임 추출 금지 (도커 빌드 UTC / 다른 TZ 환경 어긋남). 적용: `TradeHistoryGrid.formatDate/formatTime` (Intl.DateTimeFormat formatToParts) / `DailyReportTab.formatDateTime` / 모든 timestamp 필드. 백엔드 `_to_kst` 헬퍼와 동일 컨벤션

## OrderMonitor

- `pos.is_next_day=true` 일 때만 "청산" 배지 노출. 백엔드 `Position.is_next_day` 가 `_MULTIDAY_STRATEGIES`(=`{donchian_swing, vcp_breakout}`) 분기로 멀티데이 전략은 항상 False. 다른 전략(momentum/VB/LTV/bull_flag) 기존 동작 유지

## ScanMonitor

- `phase` 라벨 (`PHASE_LABELS`): pre_nxt_wait / pre_nxt_trading / main_trading / krx_main_stopped / post_nxt_trading / post_nxt_stopped / recommending / log_analysis
- 헤더 직하단 활성 보드 배지: KST 시각 → SessionTracker `_BOARD_SCHEDULE` 매핑 (08:00/08:30/09:00/15:30/18:00/20:00). 장 외 시간 "장 외 (08:00~20:00 외)"
- VB/LTV 탭 보드별 시가/타겟가: `BreakoutTarget.boards: Record<string, BoardTarget>` 활용. 활성 보드는 `font-semibold + ring`, 비활성 톤다운. 정렬·돌파 판정·근접 % 모두 활성 보드 기준. `BOARD_META` 한글 라벨/색상 매핑
- **BREAKOUT_KEYS 4종**: `volatility_breakout` / `long_tail_volatility` / `bull_flag_breakout` / `vcp_breakout`. BREAKOUT_LABELS "변동성 돌파" / "롱테일 변동성 돌파" / "눌림목 돌파" / "VCP 변동성 수축". BFB/VCP 도 `isBreakout` 분기 + 타겟 가격 테이블 재사용 (MAIN only 단일 보드)
- **활성 보드 자동 결정** (`activeBoardCode`): (1) 백엔드 응답 boards keys 가 1개면 그 키 자동 선택 (시각 매핑 무관, 백엔드 의도 진실의 원천) / (2) keys 여러 개면 KST 시각 매핑 (main > post_nxt > pre_nxt 우선) / (3) boards 빈 dict → KST 시각 fallback. POST_NXT 시간대처럼 백엔드가 활성 보드만 송신하는 케이스에서 UI 자동 전환
- "최근 매수 신호" 표: `보드` + `타겟가` 컬럼 (`BuySignal.board?` / `target_price?` / `k?`)
- donchian_swing 탭: 단계별 통과 카운트 (`scan_stats`) 막대 + 후보 테이블 갭률·진입 상태 컬럼. 진입 상태: 보유 중/갭 스킵/장 시작 전/진입 시간 종료/진입 대기. "도움말 펼치기" 토글, `gap_skip_threshold` 동적 반영
- **stale 수동 재구독 버튼**: `tick_coverage` 배지 우측 인라인 — `tcStale > 0` 시 노출. 클릭 `useMutation(resubscribeStale)` (`POST /api/realtime/resubscribe`). 성공 시 `invalidateQueries({queryKey:['trading-status']})` + "N종목 재구독 완료" / 실패 시 인라인 에러. `isPending` `disabled`. 클래스 `text-xs px-2 py-0.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-100 disabled:opacity-50`. ConfirmModal 없는 read-mostly action
- **tick_coverage 색상 배지**: `구독 중: N개` 옆 보조 `정상 A · 끊김 B · 등록 C` 한글 라벨 + 진행바 우측 `total / 41` 카운트. `data-testid="tick-coverage-badge"` 클래스 분기 — 0=`bg-gray-50 text-gray-700` / 1~5=`bg-yellow-100 text-yellow-800` / 6+=`bg-red-100 text-red-800`. `data-testid="tick-coverage-progress"` 80%+ amber / 그 외 emerald. 의미: 정상=60초 내 시세 (fresh) / 끊김=60초 미수신 (stale) / 등록=SUBSCRIBE SUCCESS (acked)

## Settings

### `ExchangeBoardRow`

- 전략별 `exchange` (KRX/NXT/SOR 라디오) + `tradable_boards` (5개 체크박스, post_nxt 선택 시 amber 강조). 0개 선택 차단
- **환경 가드**: `useTradingStatus().env` 로 모의(`!== 'real'`) 시 NXT/SOR 라디오 disabled + 회색 처리 ("(모의 불가)") + 저장 시 추가 검증
- 어느 전략이든 `post_nxt` 활성이면 상단 amber 야간 매매 경고 배너

### `PARAM_LABELS`

`k_value_krx_main / k_value_nxt_pre / k_value_nxt_post` (step 0.1) 자동 노출 + InfoTooltip.

### `updateStrategyParams`

`params` 타입 `Record<string, StrategyParamValue>` (`number | string | string[] | null`) — `tradable_boards`/`exchange`/`k_value_*` 한 호출로 송신.

### Settings — 비중 슬라이더

- 하한선 = 보유 포지션 매수금액 비율 (`min_weight`, `invested_amount`)
- 파라미터 편집은 PARAM_LABELS 정의된 number 키만
- `position_ratio` 는 "전략 내 종목당 비중" — 전략 할당 자금 기준 (순자산 전체 아님), 예상 매수 금액 헬퍼 표시

### `CashUsageRatioCard`

비중 슬라이더 하단. range 0~100, step 5 슬라이더 + `data-testid="cash-usage-ratio-percent"` % 표시. GET `/api/strategies/system/cash-usage-ratio` 초기 로드, 저장 버튼 클릭 시 PUT (debounce 없음 — 명시 commit). 응답 ratio(서버 5% 보정) 동기화. 안내 "다음 영업일부터 반영" (text-amber-700). queryKey `['cashUsageRatio']`.

### `KisQuoteAccountsCard`

`IntegrationToggleCard` 직하 신설. 보조 KIS 시세 계좌 등록/제거/활성화 토글:
- 표 컬럼: label / 환경 배지(`real`=red / `vts`=emerald) / app_key 마스킹 / app_secret_masked(`****1234`) / 등록일(KST) / `quote-account-toggle-{id}` active 토글 / `quote-account-delete-{id}` 삭제
- 빈 목록: `quote-accounts-empty` 안내 "등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 41 × (1 + N) 으로 확대"
- 등록 폼: `quote-account-input-label` / `quote-account-input-kis-env-real|vts` 라디오 / `quote-account-input-app-key` / `quote-account-input-app-secret` (**`type=password`** + `autocomplete=new-password`). 클라이언트 검증: 빈값 거부 + label 형식 `^[A-Za-z0-9\-]+$` 거부 → `quote-account-form-error` + POST 미발사
- `quote-account-submit` → `ConfirmModal` 이중 확인 (등록·active 토글·삭제 모두 안내 분기)
- **app_secret 평문 잔존 차단**: 등록 성공 시 `setForm` 빈 값으로 secret state 즉시 클리어. UI 는 `app_secret_masked` 만 참조
- 에러 메시지 분기: `axios.isAxiosError` status (`409: label 중복` / `422: 검증 실패` / 그 외)
- API: `frontend/src/api/kis-quote-accounts.ts` + `types/kis-quote-accounts.ts`. 백엔드 `/api/integrations/quote-accounts/*`. queryKey `['kis-quote-accounts']`, staleTime 30s

### `IntegrationToggleCard`

`CashUsageRatioCard` 직하 신설. 3 토글 + 매수 가드 4 모드 영역:

**토글 3종** (`ConfirmModal` 이중 확인):
- `data-testid="toggle-dkstock-regime"`: 외부 매크로 서버 (dkstock.cloud) 활성. 활성화 후 3s `data-testid="fetch-progress-dkstock-regime"` 진행 표시 + marketRegime invalidate
- `data-testid="toggle-kis-mcp"`: 외부 백테스트 서버 활성 (자문 시점만 사용)
- `data-testid="toggle-auto-regime-adjust"`: 매크로 레짐 → cash_usage_ratio 자동 갱신
- `data-testid="source-badge-{key}"` 배지: source='db' 파란 `DB` / 'env' 회색 `env` (fallback 가시화)
- API 에러: `data-testid="toggle-error-{key}"` 빨간 박스 + "잠시 후 재시도하세요"

**`BuyBlockSection` 매수 가드 4 모드 + 4 임계값**:
- 모드 select `data-testid="buy-block-mode-select"` (OFF/WARN/SOFT/HARD, 기본 HARD). 변경 시 `ConfirmModal` 이중 확인 (각 모드별 안내)
- 4 슬라이더: `buy-block-vix-slider` (10~50, 기본 25) / `buy-block-fg-high-slider` (50~100, 기본 85) / `buy-block-fg-low-slider` (0~50, 기본 15)
- `buy-block-defensive-toggle` 체크박스 (regime=defensive 차단, 기본 ON)
- `buy-block-thresholds-save` 저장 — 4 슬라이더+체크박스 한 번에 PUT (ConfirmModal 없이 즉시 — 모드 변경보다 덜 위험)
- `buy-block-reasons` 사유 리스트 (4건까지 list-disc + amber). HARD + blocked=true 시 "매수 차단 중" 강조
- SOFT 모드: `buy-block-soft-multiplier` 안내 ("현재 multiplier: 0.50")
- GET 500: `buy-block-error` graceful
- API: `getBuyBlock / setBuyBlock`. 백엔드 `/api/integrations/buy-block` GET/PUT. queryKey `['integration', 'buy-block']`, staleTime 30s

## History (`/history`)

두 탭:
- 주문체결내역: `TradeHistoryGrid` (raw 행)
- 매매손익: `TradePnLGrid` (`/api/history/pnl` — 매수·매도 페어, closed/open 사이클). 12 컬럼 + 전략 뱃지. open 행은 매도 컬럼 "—" + "(미실현)" 라벨, emerald-50 배경. 시세 미수신 "(미실현 시세 대기)"

## Logs (`/logs`) — 통합 메뉴

탭 컨테이너 `pages/Logs.tsx` + URL 쿼리 `?tab=system|daily-report` (기본 `system`, 알 수 없는 값 fallback). 두 탭 모두 `data-testid="logs-tab-{key}"` + `role="tab"` + `aria-selected`.

- **시스템 로그** (`SystemLogsTab.tsx`): `from_date / to_date` 분리 date input (기본 KST 오늘) + 적용 + 레벨 토글 (전체/INFO/WARNING/ERROR/CRITICAL) + 페이징 (1-base, size 50). 자동 새로고침 3s 는 **오늘 + page=1** 일 때만 활성. KST 강제 — `Intl.DateTimeFormat('en-CA', timeZone: 'Asia/Seoul')` 으로 today 계산. 클라이언트 `from_date>to_date` 가드 → `data-testid="system-logs-date-error"`. API `fetchLogs(filter)`
- **일일 로그 분석** (`DailyReportTab.tsx`): 좌측 영업일 리스트 (최근 30일) / 우측 summary + findings 카드 (severity + category 칩) + 원본 메트릭 접기. "지금 분석 실행" 버튼 → `POST /api/log-reports/run` (영업일당 1건 UNIQUE)

Dashboard 의 `LogViewer` 는 제거 — 운영자가 매매 화면과 로그 검토 화면 분리.

## Recommendations (`/recommendations`)

자산 배정 + 로직 자문 카드 + weight_reasoning amber 영역:

**카드 DOM 순서**: 자산 배정 → BacktestComparison → 분석 통계 → 추천 근거 → 로직 자문 → 파라미터.

- **자산 배정 카드** (`data-testid="weight-card-{id}"`, `recommended_weight != null` 시, **최상단**): 현재→추천 weight + 변경량 (%p, 이익색/손실색) + `weight-apply-checkbox-{id}` 체크박스. 체크 시 `applyMutation` body 에 `apply_weight: true`. 적용 후 `applied_weight` 표시 + amber 안내 "다음 영업일부터 반영"
- **`weight_reasoning` 영역** (`data-testid="weight-reasoning-{id}"`, weight-card 내부 `bg-amber-50 border-amber-200 max-h-32 overflow-y-auto whitespace-pre-wrap`): `rec.weight_reasoning` truthy 시만 렌더 (1000자 이내, 백엔드 truncate). 비중 변경 사유를 통합 `reasoning` 과 분리
- **로직/파라미터 자문 카드** (`data-testid="code-review-card-{id}"`, `code_review_notes != null` 시): 자유 텍스트 (whitespace-pre-wrap, max-h-64 + overflow-y-auto). 자동 적용 없음. 적용 버튼은 params 키 0개여도 weight 체크박스 ON 이면 활성 — 단독 weight 적용 가능
- **`BacktestComparisonCard`** (`backtest_summary != null` 시 자산 배정 카드 *위*): (a) 외부 MCP YAML DSL 지원 3종 (momentum/VB/donchian) 은 좌(현재)/우(추천) 메트릭 8종 비교 + 차이값 칩 (이익색 빨강 / 손실색 파랑) + `data-testid="backtest-card-{strategy}"`. (b) 폴백 3종 (LTV/bull_flag/vcp) 은 "외부 백테스트 서버 미지원 (Phase 4-bis 대기)" 안내. `status=running` 시 로딩 스피너. **`max_drawdown` 양수(절대값) 컨벤션**: `METRIC_SPECS.max_drawdown.diffSignInverted=true`. 양수 diff (추천 MDD 더 큼) = 손실 악화 → 파랑, 음수 diff = 손실 완화 → 빨강

## BalanceTable

**거래시장 배지**: 보유 종목 헤더 "종목명" 옆 "거래시장" 컬럼. `Holding.nxt_tradable / krx_halted` 조합 5가지 배지 — `KRX+NXT`(emerald-100/800) / `NXT만`(amber-100/800) / `KRX`(gray-100/700) / `정지`(red-100/800) / `확인중`(gray-50/500). `data-testid="market-badge-{ticker}"`. 베이스 클래스 `inline-block px-1.5 py-0.5 rounded text-xs font-medium`

## KisAccountPoolCard

Dashboard `MarketRegimeCard` 직하 신설 (시장 → 인프라 위계). WebsocketPool 세션 상태 + 슬롯 사용률 + 분배 모니터링.

- `pool-refresh-button` 새로고침 → `invalidateQueries({queryKey:['realtime-subscriptions']})`
- 총 슬롯 패널 — `pool-used-slots / pool-total-slots` (41 × N) + `pool-usage-progress` 진행바 (80%+ amber) + fresh/stale/ACK 카운트
- 세션별 표 — `pool-session-row-{label}` (main / quote-1 ...) / label 배지 (main=blue + `(체결통보)`) / `pool-session-status-{label}` (connected=emerald / disconnected=red) / subscribed/limit + `pool-session-progress-{label}` 미니 진행바 / fresh / stale / reconnect_count
- 보조 0개: `pool-no-secondary-note` 안내
- API: `getSubscriptions()`, `/api/realtime/subscriptions` sessions 배열. queryKey `['realtime-subscriptions']`, `staleTime: 5_000`, `refetchInterval: 30_000` (Trading Status 5s 와 별개 큐로 부하 격리). 에러 시 `pool-error-message` graceful

## StreamStatus (`/stream`)

사이클 15-C-2 (2026-05-19) 신규 메뉴. REST+WS 혼합 풀 매니저 상태 모니터링 페이지.

- 3 탭 (`data-testid="stream-tab-{rest|ws|dropped}"`):
  - REST 관찰: REST 폴링 중인 종목 (임박 후보 검사 대상)
  - WS 활성: WS 풀에 활성 구독 중 + `min_hold_remaining_secs` 컬럼
  - 탈락 (cooldown): 강등 후 재승격 제한 중 + `cooldown_remaining_secs` 컬럼
- 탭 라벨에 카운트 표기 — `(N)` 형태
- 컬럼: 종목 / 전략 (한글 라벨 매핑) / 사유 / 등록 후 경과 / (옵션) 남은시간
- 빈 카테고리 → `stream-empty-{tab}` 안내
- `stream-refresh` 새로고침 버튼 → `invalidateQueries`
- API: `getStreamStatus()` (`frontend/src/api/realtime.ts`), `/api/realtime/stream-status`. queryKey `['stream-status']`, `staleTime: 5_000`, `refetchInterval: 30_000`. 에러 시 `stream-error` graceful
- 회귀 가드: `frontend/src/pages/__tests__/StreamStatus.test.tsx` 7 케이스 (기본 ws 탭 / REST 탭 / 탈락 탭 cooldown 컬럼 / 빈 카테고리 / 탭 카운트 / 새로고침 / 500 에러)

## MarketRegimeCard

Dashboard 환경 배너 직하, 전략 탭 위 (`<ControlPanel />` 직후).

- regime 배지 (defensive=red / neutral=gray / aggressive=blue / 비활성=gray-500) + VIX / Fear & Greed / Buffett / cycle 메트릭 grid + cash_usage_ratio + auto_regime_adjust 토글
- `buy_blocked=true` 시 `data-testid="market-regime-block-banner"` amber 배너 + block_reason + "보유 종목 청산은 정상 작동. 매수만 차단"
- `auto-regime-toggle` ON/OFF — `ConfirmModal` 이중 확인 (ON: "다음 영업일부터 cash_min 기반 자동 갱신" / OFF: "운영자 수동값 보존")
- API: `getMarketRegimeCurrent()` (queryKey `['marketRegime']`, staleTime 60s) + `setAutoRegimeAdjust(boolean)` + `getMarketRegimeHistory(days)`
- `enabled=false` (DKSTOCK_REGIME_ENABLED=false) → "비활성" gray 배지 + 메트릭 "—". 매수 가드 비활성

## 주문 안전성

- 시작/정지/매도 등 주문 관련 버튼은 ConfirmModal 이중 확인 필수

## 백엔드 연동

- 모든 API 호출은 `api/client.ts` axios 인스턴스 경유
- 응답은 `types/common.ts::ApiResponse<T>` 로 파싱
- 백엔드 응답 필드명 = TypeScript 속성명 (1:1, 변경 시 동기화)
- 페이징 응답에 `total`/`total_pages` 필드 필수
