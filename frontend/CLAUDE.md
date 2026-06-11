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

Dashboard 만 즉시 import. History/Recommendations/Logs/Settings/**StrategyFunnel** 는 `React.lazy()` + Suspense skeleton (초기 번들 819→656kB). `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환 보존.

## StrategyFunnel (`/strategy-funnel`, 사이클 34, 2026-05-21)

전략별 조건검색 단계별 후보/탈락 종목 추적 페이지. 전략 dropdown + 날짜 picker + 단계별 expand 가능한 테이블 + 수동 trigger 버튼 (`POST /api/strategy-funnel/snapshot`). 단계 클릭 시 `survived_tickers` 리스트 + `excluded_sample` 탈락 사유 표시. API: `getFunnel / getRecentFunnel / triggerFunnelSnapshot` (`frontend/src/api/strategy-funnel.ts`). queryKey `['strategy-funnel', strategy_id, target_date]`. **사이클 39 (2026-05-22)**: BFB/VCP/donchian `prepare()` 8단계 자동 hook + 09:30 일일 1회 자동 snapshot (사용자 수동 trigger 도 보존). **사이클 41 (2026-05-22)**: 단계명 옆 `조건` 툴팁 (`data-testid="funnel-step-conditions-..."` + `title`) + 통과/탈락 종목 ticker 옆 종목명 별도 표시 (`SurvivedItem` 타입 + dict/string 분기) + 탈락 사유 수치 포함 (예: `"음봉 비율 35% > 30%"` / `"마지막 폭 12% > 8%"`).

**사이클 39 (2026-05-22) — `ScanMonitor.tsx` VCP 키 매핑 시정**: VCP_STAGES 의 `trend_pass` → `trend_filter_pass` / `contraction_pass` → `pullback_pass` (백엔드 `_scan_stats` 키와 정합). 사용자 5/22 "EMA 0인데 base 9" 잘못된 표시 본질 원인.

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
- **사이클 21 (2026-05-20) 5 전략 깔때기 시각화 (`ScanFunnelBars` 컴포넌트)** — donchian SWING_STAGES 패턴을 5 전략에 동일 적용:
  - `vb-scan-funnel` (VB 8단계 / teal) — universe_candidates → price_filtered → mcap_pass → trade_amount_pass → universe_filtered → candle_fetch_ok → k_value_computed → final_prepared
  - `ltv-scan-funnel` (LTV 9단계 / teal) — VB + consecutive_limit_pass
  - `momentum-scan-funnel` (momentum 6단계 / emerald) — universe_candidates → rate_pass → mcap_pass → trade_amount_pass → limit_up_excluded → final_prepared
  - `bfb-scan-funnel` (BFB 8단계 / indigo) — universe_candidates → universe_filtered → candle_fetch_ok → pole_pass → flag_pass → volume_contraction_pass → atr_pass → final_prepared
  - `vcp-scan-funnel` (VCP 8단계 / indigo)
  - `scan_stats` 미반영 시 "아직 스캔 전" fallback. 옵셔널 타입 가드로 백엔드 미배포 환경 호환
- **사이클 21 인프라 영역 KisAccountPoolCard 로 이전** — `tick-coverage-badge` / `tick-coverage-progress` / `stale-context-label` / `stale-list-toggle` / 수동 재구독 버튼 / 끊김 종목 펼치기 모두 KisAccountPoolCard 로 통합. ScanMonitor 는 필터링 가시성에 집중 (`subscribed_count` 단순 카운트만 보존)
- **사이클 18 "돌파" 라벨 매매 컨텍스트** (`BREAKOUT_KEYS` 4종 모두): `curPrice >= targetPrice` 분기에서 활성 보드 ∩ 전략 `tradable_boards` 검사. 교집합 ∋ → 기존 빨강 "돌파". 교집합 ∅ → 회색 "돌파 (대기 — {보드라벨})" + `title` 툴팁 "이 전략은 X 에서만 매매". `tradable_boards` 미존재 (백엔드 미반영) → 빨강 "돌파" fallback (안전 회귀). 한화에어로스페이스(012450) 16:43 운영 결함 (VB POST_NXT 보드 가드 skip 정상이나 UI 불명확) 가시화 해소

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

`CashUsageRatioCard` 직하 신설. 4 토글 + 매수 가드 4 모드 영역:

**토글 4종** (`ConfirmModal` 이중 확인):
- `data-testid="toggle-dkstock-regime"`: 외부 매크로 서버 (dkstock.cloud) 활성. 활성화 후 3s `data-testid="fetch-progress-dkstock-regime"` 진행 표시 + marketRegime invalidate
- `data-testid="toggle-kis-mcp"`: 외부 백테스트 서버 활성 (자문 시점만 사용)
- `data-testid="toggle-auto-regime-adjust"`: 매크로 레짐 → cash_usage_ratio 자동 갱신
- **`data-testid="toggle-auto-apply"`** (사이클 23 P3-3): AI 자문 자동 적용. 기본 OFF. ON 시 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터 자동 적용. DB-only (`auto_apply_enabled` 키). API: `getAutoApply/setAutoApply` — `/api/integrations/auto-apply`
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

### `TradeAmountFilterCard` (사이클 65, 2026-06-06)

**거래대금 동행 필터** (사이클 62 갭상승 회피 효과 폐기 보강 — Q7-5 사이클 64 자문 인계). `PriceFilterCard` 옆 배치 (Settings 화면 "WebSocket 구독 대상 필터" 영역). 사이클 64 PriceFilterCard 패턴 100% 답습.

- **4 testid**: `trade-amount-filter-card` 카드 컨테이너 / `trade-amount-filter-min-slider` 단일 슬라이더 (0~100억원 = 0~10_000_000_000, step 1억원 = 100_000_000) / `trade-amount-filter-save-button` 저장 / `trade-amount-filter-save-toast` 성공 안내
- **권장값 마커 3 버튼**: "1억" (100_000_000) / "5억" (500_000_000) / "10억" (1_000_000_000) — 슬라이더 value 직접 갱신 (domain-expert Q1 자문)
- **즉시 반영** (사이클 64 답습): 저장 클릭 → `updateTradeAmountFilter()` PUT → 백엔드 `scanner.invalidate_trade_amount_filter_cache_scanner()` 즉시 호출 → 60s 캐시 도중 사용자 토글 즉시 반영. **Q7-1 자동 unsubscribe 0 발화** (다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단)
- API: `getTradeAmountFilter / updateTradeAmountFilter` (`frontend/src/api/trade-amount-filter.ts` 신규 35L + `frontend/src/types/trade-amount-filter.ts` 신규 20L). 백엔드 `/api/system/trade-amount-filter` GET/PUT, `ApiResponse<TradeAmountFilter>` 래퍼 → 프론트 `data.data` 추출 (사이클 64 답습). queryKey `['tradeAmountFilter']`. PUT body 에 extra key 전달 시 422 (`ConfigDict(extra="forbid")`) + 음수 → 400 (`ValueError`)
- **안내 배너 (Q6-1 명시 의무)**:
  - "**거래대금 동행 필터** — 임계 미만 종목은 WebSocket 구독 자체 차단"
  - "보유/익일청산 종목은 절대 제외 안 됨" (사이클 64 Q1 옵션 D 답습 + 사이클 32 R4 universe guard 보호 영속)
  - "**09:00 직후 거래대금 미반영 종목은 graceful 통과**" (Q6-1 시스템 매매 무용 차단)
- 회귀 가드 4 vitest 케이스 (`TradeAmountFilterCard.test.tsx`): F-FE-1 fetch 후 렌더 / F-FE-2 슬라이더 조작 + 저장 PUT body 검증 / F-FE-3 권장값 마커 갱신 / F-FE-4 안내 배너 보유/익일청산 + 09:00 graceful 텍스트
- **사이클 65 hotfix H1 (2026-06-06)** `useQuery({ retry: 1, ... })` 명시: 사이클 64 PriceFilterCard + 사이클 65 TradeAmountFilterCard 양쪽에 `retry: 1` 옵션 *명시 추가*. `main.tsx` 전역 `defaultOptions.queries.retry: 1` 와 일관 (3 중: 전역 + 카드 1 + 카드 2). 원인: 사이클 65 카드 추가로 카드 수 임계 초과 → e2e 환경 (백엔드 미실행) ECONNREFUSED 시 React Query 기본 retry 3회 누적 → settings.spec.ts 5.7s timeout 초과. **AST 영구 가드** (`frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts` 2 케이스): PriceFilterCard + TradeAmountFilterCard 의 useQuery `retry` 옵션 명시 의무 (정규식 기반 정적 검증). 향후 신규 카드 useQuery 추가 시 retry 누락 영구 차단.
- **사이클 80 hotfix 4 단계 통합 (2026-06-08) — Settings.tsx retry:1 + e2e Playwright LIFO 영구 가드 + AST G-AST4 영역 확장**: 사이클 79 1차 + 재실행 e2e fail (flaky 아닌 진짜 결함 확정) → 옵션 C 정밀 조사 결과 trace console warning `<PriceFilterCard> component error` 발견 → Playwright route LIFO 룰 발견 → 사이클 65 hotfix #2 가드 FIFO 가정 영구 시정. **hotfix #1 (`9d20012`)**: `frontend/src/pages/Settings.tsx` L43 useQuery (`queryKey: strategies`) + L692 useQuery (`queryKey: autoStart`) 양쪽 `retry: 1` 명시 (사이클 65 H1 답습) + `_ast_useQuery_retry_required.test.ts` 에 `TARGET_PAGES = ['Settings.tsx']` 신규 describe 추가 (사이클 75 G-AST4 영역 확장, 페이지 영역 useQuery 영구 가드). trace 에 `/api/strategies` 호출 발생 = retry 효과 부분 입증. **hotfix #2 (`c9c3b51`)**: `e2e/settings.spec.ts` toBeVisible 10s → 20s 상향 (사이클 65 hotfix #3 패턴 답습). 20s 도 fail = 단순 timeout 아닌 진짜 throw 확정. **hotfix #3 (`2f74673`) 근본 결함 시정**: `e2e/fixtures/api-mocks.ts` L291 wildcard `**/api/system/**` 함수 끝 등록 제거 + L190 wildcard 구체 라우트 *전* 등록 추가. **Playwright route 매칭 = LIFO** ("latest registered route wins") → 함수 끝 wildcard 가 가장 우선 매칭 → 구체 라우트 (L196 price-filter / L201 trade-amount-filter) 무효화 → envelope({}) 응답 → min_price undefined → React controlled input throw → Error Boundary 없음 → 전체 페이지 unmount → `상한가 모멘텀` 미렌더 → toBeVisible 20s timeout. e2e ✅ success. **hotfix #4 (`d65e3f2`)**: `tests/unit/e2e_mocks/test_api_mocks_routes_registered.py::test_e2e_api_mocks_specific_routes_registered_before_wildcard` 가 FIFO 가정 (`price_filter_pos < wildcard_pos`) 으로 작성됨 (사이클 65 hotfix #2 시점) → 사이클 80 hotfix #3 LIFO 시정과 충돌 → backend-test fail. 가드 함수명 `before_wildcard` → `after_wildcard` + assertion 방향 반전 + docstring Playwright LIFO 명시. 백엔드 2094 PASS 영속. **결함 chain 통찰**: 단일 근본 원인 (사이클 65 hotfix #2 가드 잘못된 FIFO 가정) 의 6 commit 진화 = 사이클 65 hotfix #2 가드 FIFO 가정으로 PASS (운) → 사이클 79+ Playwright cache/race 변화로 결함 노출 → hotfix #1~#4 chain 영구 차단. 백엔드 2094 PASS + 1 XFAIL + 2 skip / 프론트 188 PASS / 합계 2284 PASS / e2e ✅ 6/6 job. silent 결함 영구 차단 18 회 누적 (60/64/65#1/65#2/65#3/66/67/68/72/73/77/77#2/78/79/80/80#2/80#3/80#4). 19 사이클 연속 옵션 A 패턴 영속 (55 R-1 / 60 / 62~69 / 72~80). 운영 영향 0 (e2e + frontend retry + AST 가드 영역 한정). 사이클 65 hotfix #1/#2/#3 + 사이클 75 G-AST1~AST5 + 사이클 77 hotfix 2단 + 사이클 78/79 모두 영속 (변경 0)
- **사이클 75 (2026-06-08) — retry: 1 영역 확장 + e2e api-mocks 7 endpoint 추가**: 사이클 73 1차 + 사이클 74 1차 e2e fail (flaky 2회 누적) 영구 차단. team-leader Phase 1 분석 결과 **7 endpoint group 미등록 확정** (Settings 페이지 마운트 IntegrationToggleCard / CashUsageRatioCard / KisQuoteAccountsCard 호출 endpoint — `cash-usage-ratio` + integrations 4 토글 + buy-block + quote-accounts). `e2e/fixtures/api-mocks.ts` +53L 7 라우트 추가 (`**/api/strategies/system/cash-usage-ratio` + `**/api/integrations/{dkstock-regime,kis-mcp,auto-regime-adjust,auto-apply,buy-block,buy-block/thresholds}` + `**/api/integrations/quote-accounts**`). **3 컴포넌트 retry: 1 영역 확장** (사이클 65 H1 답습 Q4 채택): `CashUsageRatioCard.tsx:27` + `IntegrationToggleCard.tsx:190` (BuyBlockSection) + `:469` (ToggleRow) + `KisQuoteAccountsCard.tsx:87` — 5 위치 명시. `IntegrationToggleCard.test.tsx` I8-G `waitFor` timeout 1000→3000ms 보정 + `setupToggleStubs` auto-apply 핸들러 추가 (사이클 75 Q4 retry:1 직접 사이드이펙트). **AST 영구 가드 확장** (사이클 65 H3 답습): `_ast_api_mocks_coverage.test.ts` 신규 10 케이스 (`frontend/src/api/*.ts` literal endpoint vs `e2e/fixtures/api-mocks.ts` route glob 매칭 정적 검증 G-AST1~AST4) + `_ast_useQuery_retry_required.test.ts` 5 케이스 (사이클 65 H3 2 영속 + 사이클 75 3 신규 G-RT1~RT3) + `tests/unit/e2e_mocks/test_cycle75_api_mocks_routes_registered.py` pytest 2 케이스 (7 endpoint group 정규식 grep). 백엔드 2066 → 2068 PASS (+2 pytest AST) / 프론트 172 → 185 PASS (+13 vitest AST + I8-G timeout 보정 회귀 0) / 회귀 0 / flakiness 0 / 사이클 65 hotfix #1/#2/#3 영속 (변경 0). 운영 영향 0 (e2e + frontend retry 영역 한정)
- MSW handler (`handlers.ts` +14L): `GET /api/system/trade-amount-filter` → `{ min_amount: 0 }` + `PUT` 요청 body 반영

### `PriceFilterCard` (사이클 62 신설 → 사이클 64 단순화, 2026-06-06)

**WebSocket 구독 대상 필터** (사이클 64 사용자 의도 재정의 — 사이클 62 매수 신호 판단용 위치 폐기 + 단순화). `BuyBlockSection` 직하 (Settings 화면 위계). 사이클 38 명문화 답습 — 매도/익일청산/손절 영향 0.

- **7 testid** (사이클 62 9 → 사이클 64 7, mode-select 폐기): `price-filter-card` 카드 컨테이너 / `price-filter-min-slider` 최소가 슬라이더 (0~20,000원, step 1,000) / `price-filter-max-slider` 최대가 슬라이더 (0~2,000,000원, step 50,000) / `price-filter-save-button` 저장 / `price-filter-save-toast` 성공 안내 / `price-filter-validation-error` max<min 클라이언트 에러
- **모드 폐기** (사이클 64 Q4 자문 옵션 A — 단순 필터링만): 사이클 62 HARD/WARN/OFF 3 모드 → 사이클 64 단일 필터 (`min=0 or max=0` 비활성). `PriceFilterMode` 타입 + `mode` 필드 전부 제거
- **권장값 툴팁** (domain-expert 사이클 62 Q1 자문): 저 5,000원 / 고 1,000,000원. 디폴트 0/0 = 비활성
- **즉시 반영** (Q5 자문): 저장 클릭 → `updatePriceFilter()` PUT → 백엔드 `scanner.invalidate_price_filter_cache_scanner()` 즉시 호출 (사이클 62 `risk_manager.invalidate_price_filter_cache` 폐기) → 60s 캐시 도중 사용자 토글 즉시 반영. **Q7-1 자동 unsubscribe 0 발화** (다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단)
- **클라이언트 검증**: 음수 / `min_price > max_price` (단 둘 다 >0 일 때) → `price-filter-validation-error` 표시 + PUT 미발사
- API: `getPriceFilter / updatePriceFilter` (사이클 64 `PriceFilterUpdate` body 에서 mode 필드 제거). 백엔드 `/api/system/price-filter` GET/PUT, `ApiResponse<PriceFilter>` 래퍼 → 프론트 `data.data` 추출. queryKey `['system', 'price-filter']`. PUT body 에 mode 전달 시 422 (`ConfigDict(extra="forbid")`)
- **안내 배너 갱신** (사이클 64): "**WebSocket 구독 대상 필터** — 임계 외 종목은 시세 구독 자체 차단. 보유/익일청산 종목은 절대 제외 안 됨" (사이클 62 "매수 신호 차단" 표현 폐기 + 사이클 32 R4 universe guard 보호 영속 명시)
- 회귀 가드 4 vitest 케이스 (사이클 62 5 → 사이클 64 4, mode 토글 F-5 폐기): F-1 fetch 후 렌더 + mode select 미존재 검증 / F-2 슬라이더 변경 / F-3 저장 + toast (body 에 mode 미포함) / F-4 max<min 가드

## History (`/history`)

두 탭:
- 주문체결내역: `TradeHistoryGrid` (raw 행)
- 매매손익: `TradePnLGrid` (`/api/history/pnl` — 매수·매도 페어, closed/open 사이클). 12 컬럼 + 전략 뱃지. open 행은 매도 컬럼 "—" + "(미실현)" 라벨, emerald-50 배경. 시세 미수신 "(미실현 시세 대기)"

## Logs (`/logs`) — 통합 메뉴

탭 컨테이너 `pages/Logs.tsx` + URL 쿼리 `?tab=system|daily-report` (기본 `system`, 알 수 없는 값 fallback). 두 탭 모두 `data-testid="logs-tab-{key}"` + `role="tab"` + `aria-selected`.

- **시스템 로그** (`SystemLogsTab.tsx`): `from_date / to_date` 분리 date input (기본 KST 오늘) + 적용 + 레벨 토글 (전체/INFO/WARNING/ERROR/CRITICAL) + 페이징 (1-base, size 50). 자동 새로고침 3s 는 **오늘 + page=1 + 검색 모드 아닐 때** 만 활성. KST 강제 — `Intl.DateTimeFormat('en-CA', timeZone: 'Asia/Seoul')` 으로 today 계산. 클라이언트 `from_date>to_date` 가드 → `data-testid="system-logs-date-error"`. API `fetchLogs(filter)`
  - **사이클 6 통합 (2026-05-20) 검색 박스**: 필터 바 *위* 에 키워드 검색 (`data-testid="system-logs-search-input"` + Enter 키 지원 + `system-logs-search-button` + 검색 모드 진입 시 `system-logs-search-clear` 초기화 버튼). 검색 모드 동안 페이징/자동 새로고침 비활성 (`/api/logs/search` 단일 limit 200 응답). API `searchLogs({q, level, start, end, limit})` — 현재 입력된 level/from_date/to_date 함께 전송 (검색 범위 좁히기). 검색 결과 0건 → "검색 결과가 없습니다." (페이징 모드 "로그가 없습니다." 와 메시지 분리). `has_more=true` 시 `system-logs-search-has-more` amber 배너 "검색 결과가 200건을 초과합니다. 키워드를 좁혀주세요." 운영자가 OPSP0002/nxt_downgrade 등 특정 사고 추적 즉시 가능
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

Dashboard `MarketRegimeCard` 직하 신설 (시장 → 인프라 위계). WebsocketPool 세션 상태 + 슬롯 사용률 + 분배 모니터링 + **사이클 21 — 끊김 종목 통합**.

- `pool-refresh-button` 새로고침 → `invalidateQueries({queryKey:['realtime-subscriptions']})`
- 총 슬롯 패널 — `pool-used-slots / pool-total-slots` (41 × N) + `pool-usage-progress` 진행바 (80%+ amber) + fresh/stale/ACK 카운트
- 세션별 표 — `pool-session-row-{label}` (main / quote-1 ...) / label 배지 (main=blue + `(체결통보)`) / `pool-session-status-{label}` (connected=emerald / disconnected=red) / subscribed/limit + `pool-session-progress-{label}` 미니 진행바 / fresh / stale / reconnect_count
- 보조 0개: `pool-no-secondary-note` 안내
- **사이클 21 (2026-05-20) 끊김 영역 통합 (ScanMonitor 에서 이전)**:
  - `stale-context-label` (`stale_60s > 0` 시) — KRX 메인 (09:00~15:30) 빨강 "결함 가능" / PRE_NXT (08:00~09:00) 노랑 "거래량 적음" / 그 외 (NXT 애프터/시간 외) 회색 "한산 시 정상"
  - `pool-resubscribe-button` (`stale_60s > 0` 시) — `useMutation(resubscribeStale)` → `POST /api/realtime/resubscribe`. 성공 시 `invalidateQueries({queryKey:['realtime-subscriptions','trading-status']})` + "N종목 재구독 완료" 인라인 메시지
  - `pool-stale-list-toggle` + 종목별 `pool-stale-row-{ticker}` — `subscriptions.tickers.stale.length > 0` 시 노출. 종목별 마지막 tick 시각 `Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Seoul', hour12:false})` HH:MM:SS. `last_tick_map[ticker]=null` 이면 "—"
  - 공용 헬퍼 `frontend/src/utils/stale-context.ts` (`getKstMinutes / getStaleContextByKstMinutes / STALE_CONTEXT_META / formatLastTickKst`)
- API: `getSubscriptions()`, `/api/realtime/subscriptions` sessions 배열. queryKey `['realtime-subscriptions']`, `staleTime: 5_000`, `refetchInterval: 30_000` (Trading Status 5s 와 별개 큐로 부하 격리). 에러 시 `pool-error-message` graceful
- **사이클 35 (2026-05-21) — 세션별 종목 expand 토글**: `pool-session-expand-{label}` 클릭 시 종목 테이블 표시. 종목당 `pool-ticker-row-{label}-{ticker}` (ticker / 이름 / stale 배지 / WS tick 시각 / retries / 마지막 강제 재구독 시각). 응답 `sessions[*].tickers_detail` (cap 200, stale 우선 정렬) 활용
- **사이클 37 (2026-05-21) — "KIS 체결" / "KIS 거래량" 컬럼 추가**: 종목 expand 테이블에 KIS `inquire_ccnl` 캐시 데이터 (`last_cntg_hour` HH:MM:SS / `today_volume`) 노출. `formatCntgHour` / `isWsSubscriptionSuspect` 헬퍼 — WS tick 시각과 KIS 실제 체결시각 차이 5분(300초) 이상이면 amber "WS 의심" 배지 (`Intl.DateTimeFormat('en-GB', timeZone:'Asia/Seoul')` HHMMSS 파싱). 캐시 미스 → "—"
- **사이클 43 (2026-05-22) — 세션 라벨 통일**: 보조 세션 라벨 `quote-1/2/3` 1-based index → DB `kis_quote_accounts.label` (ISA/sub/gold 등 사용자 등록 라벨) 직접 사용. `pool-session-row-{label}` / `pool-session-expand-{label}` / `pool-ticker-row-{label}-{ticker}` 자동 적용 (백엔드 응답 라벨 변경). `sessionLabelBadge(label)` 는 main 외 모두 회색 (분기 변경 0). 사이클 42 `[ws_heartbeat] label=ISA` 와 일관

> 사이클 17 (2026-05-19) — 사이클 15-C-2 `StreamStatus` (`/stream`) 메뉴 + `getStreamStatus()` API + `GET /api/realtime/stream-status` 백엔드 엔드포인트 전체 롤백. 단순화 원칙(단일 데이터 경로 + 신규 모듈 추가 금지) 위반 + `_near_signal_loop` race 결함 대응.

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

## 사이클 106 (2026-06-11) — StockMaster.tsx 안내 배너 영역 영구 영속 갱신 + "KIS API 일시 결함" toast 정밀화

사용자 보고 (verbatim): "종목마스터 갱신작업 점검이 금일 내로 완료되어야 할 것 같아. 현재 종목마스터의 상단에 있는 메시지는 이제 무효한거 아닌가? 점검해서 UI에서 지우고 프론트와 백엔드 모두 현행화하길 바래." stock_master 191 ticker 영구 영속 결함 영역 4 영역 통합 시정 중 frontend-dev 영역 (영역 1+2+4).

### `StockMaster.tsx` 안내 배너 영역 영구 영속 갱신 (영역 1+4)

- **위치**: `frontend/src/pages/StockMaster.tsx:468~479` (`stock-master-info-banner` testid 영역 영구 영속)
- **변경 전 (사이클 94)**: "각 전략의 후보 종목은 매 사이클..." 영역 영구 영속 무효 메시지 영역 (사이클 95~101 영구 영속 후 무효)
- **변경 후 (사이클 106, 2026-06-11)**: "매일 20:00 KRX/KOSDAQ 전 종목 일괄 적재 + 보유 종목 + 매수 후보 종목 5분 주기 자동 갱신" 영역 영구 영속 신규 메시지 영속
- **사유**:
  - 사이클 94 영역 영구 영속 무효 메시지 영역 영구 제거 (사이클 95~101 영구 영속 후 무효 영역 영구 영속 정합)
  - 사이클 89 한글 친숙 용어 영속 답습 (영문 / 사이클 언급 0건 영속)
  - 사용자 가독성 영구 영속 정합

### `StockMaster.tsx` `refreshMutation.onError` 영역 영구 영속 정밀화 (영역 2)

- **위치**: `frontend/src/pages/StockMaster.tsx::refreshMutation.onError`
- **변경 전**: "적재 실패 — 잠시 후 재시도" 영역 영구 영속 일반 메시지
- **변경 후 (사이클 106, 2026-06-11)**: "KIS API 일시 결함 — 잠시 후 재시도" 영역 영구 영속 정밀화 영속
- **사유**:
  - 사이클 76 `[api_retry_recovered_summary]` graceful 영역 영구 영속 정합 (운영자 즉시 사이클 76 graceful retry 영역 영구 영속 확인 가능)
  - 사이클 65 H3 useQuery retry:1 영속 답습 (useMutation retry=false 영속 + 토스트 3종 영속)
  - 사이클 89 한글 친숙 용어 영속

### 영속 의무 매트릭스 (사이클 106 영구 확인 영역)

- 사이클 65 H3 useQuery retry:1 영속 (영역 1/2/4 UI 영역 영속)
- 사이클 68 KST 영속 (timestamp KST 영역 영속)
- 사이클 80 hotfix #3/#4 Playwright LIFO 영속 (영역 1/2/4 e2e 정합 영속)
- 사이클 89 한글 친숙 용어 영속 (영역 1/2/4 라벨 영속)
- 사이클 94 영역 영구 영속 무효 메시지 영구 제거 + 신규 메시지 영구 영속 (영역 1+4)
- 사이클 102 G-REJECT 영속 (양 agent 일치 영역)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

### 운영 효과 (push + EC2 자동 배포 후)

- 사용자 UI 종목마스터 메뉴 = 사이클 94 무효 메시지 영구 제거 + 신규 메시지 영구 영속 표시
- "지금 새로고침" 버튼 클릭 시 KIS API 일시 결함 영역 = "KIS API 일시 결함 — 잠시 후 재시도" 영구 영속 정밀화 토스트
- 사용자 가독성 영구 정합

## 사이클 103 (2026-06-11) — RealtimeHealth + Strategies 2 페이지 신규 + navItems 9개 영속

사이클 102.5 회고 결정적 사실 (코미코 STOP_LOSS 운영 가시화 부족) 즉시 시정 4 영역 통합 중 영역 0 + 영역 1 (frontend-dev 영역).

### `RealtimeHealth` (`/realtime-health`, 사이클 103 신규, 2026-06-11)

- 신규 4 파일:
  - `frontend/src/types/realtime-health.ts` (33L) — `RealtimeHealthSnapshot` interface (dispatch_drop_total + callback_exception_total + stale_force_retry_total + ws_auto_restart_total 4 카드 영역)
  - `frontend/src/api/realtime-health.ts` (84L) — `fetchRealtimeHealth()` 함수 (`/api/logs/search` 기존 영역 활용 4 prefix grep 통합 영역)
  - `frontend/src/pages/RealtimeHealth.tsx` (244L) — 4 카드 통합 영역
  - `frontend/src/test/handlers.ts` 갱신 (MSW handler) + `e2e/fixtures/api-mocks.ts` 갱신 (Playwright LIFO 정합, 사이클 80 hotfix #3 영속)
- 4 카드 영역:
  - `[dispatch_drop_summary]` (사이클 102 신규 prefix, dispatch silent drop 5분 주기 emit 영역)
  - `[callback_exception]` (사이클 102 신규 prefix, callback 예외 전수 가시화 영역)
  - `[stale_force_retry]` (사이클 102 임계 상향 영역, KIS LMS chain 안전 마진 2 배 확장)
  - `[ws_auto_restart]` (사이클 92 prefix, WebSocket 자동 재기동 영역)
- 영속 의무 매트릭스:
  - `useQuery({retry: 1, refetchInterval: 60_000})` 사이클 65 H3 영속 (AST G-AST-RT 영구 가드)
  - 한글 라벨 사이클 89 영속 (영문 prefix 인접 한글 친숙 용어 영속)
  - MSW + Playwright LIFO 정합 사이클 75 G-AST5 + 80 hotfix #3/#4 영속

### `Strategies` (`/strategies`, 사이클 103 신규, 2026-06-11)

- 신규 1 파일:
  - `frontend/src/pages/Strategies.tsx` (233L) — 6 전략 (momentum + volatility_breakout + long_tail_volatility + donchian_swing + bull_flag_breakout + vcp_breakout) 각 카드 영역 4 임계 영속
- 4 임계 영역 (영구 영속):
  - `stop_loss_rate` (손절 비율, 코미코 사례 단일 근본 원인 영역)
  - `daily_loss_limit` (일일 손실 한도)
  - `trailing_stop_rate` (Trailing Stop 비율)
  - `position_ratio` (종목당 매수 비중)
- 데이터 = 기존 `GET /api/strategies` 영구 영속 (`src/engine/strategy_registry.py:153 params: s.config.params`, 영역 변경 0 = 기존 API 활용)
- 사용자 오인 영역 영구 차단 (코미코 사례 단일 근본 원인 영역 시각화 — DB 운영 영역 `-2.4%` 영구 영속 가시화)
- 한글 라벨 영속 (사이클 89 답습) + graceful (`params={}` 시 "—")

### `App.tsx::navItems` 7→9 갱신 (사이클 81 햄버거 + 사이클 85 M-9 영속)

- 추가 메뉴 2:
  - 실시간 상태 (`/realtime-health`)
  - 전략 현황 (`/strategies`)
- PC 메뉴 (sm: ≥640px) 가로 + 모바일 (< sm) 햄버거 Drawer 9개 압축 (사이클 81 G-MOBILE-7 → G-MOBILE-9 갱신)
- `MobileMenuLabel` 헬퍼 (useLocation 현재 경로 한글 레이블) 영속

### 영속 의무 매트릭스 (사이클 103 영구 확인 영역)

- 사이클 41 StrategyFunnel 4 카드 패턴 답습 (RealtimeHealth 4 카드 영역)
- 사이클 65 H3 useQuery retry:1 영속 (G-AST-RT TARGET_PAGES 확장)
- 사이클 68 KST 영속 (timestamp KST 영역)
- 사이클 75 G-AST5 api-mocks 영속 (MSW handler + AST 가드 영역 확장)
- 사이클 80 hotfix #3/#4 Playwright LIFO 영속 (e2e 정합 영역)
- 사이클 85 G-AST-RT + G-AST-MOCK + M-9 영속 (PC 메뉴 + 모바일 햄버거 9개 영속)
- 사이클 89 한글 친숙 용어 영속 (영문 prefix 인접 한글 라벨 영속)
- 사이클 102 G-REJECT 영속 (양 agent 일치 영역)

### 운영 효과 (push + EC2 자동 배포 후)

- `/realtime-health` 페이지 = 4 카드 실시간 가시화 (사이클 102 신규 prefix 3 + 사이클 92 prefix 1) — 운영자 즉시 실시간 상태 확인 가능
- `/strategies` 페이지 = 6 전략 각 4 임계 실시간 가시화 (사용자 오인 영역 영구 차단 = 코미코 사례 단일 근본 원인 영역)
- 매매 안전성 무영향 (UI 가시화 영역 한정, 매매 hot path 무관)

## 사이클 104 (2026-06-11) — E2E spec 신규 (사이클 103 신규 페이지 검증) + silent 결함 2 영구 시정

### 신규 E2E spec

- `e2e/realtime-health.spec.ts` 신규 (8 케이스: H-RH1~H-RH4 HIGH 4 + M-RH5~M-RH6 MEDIUM 2 + L-NAV1 + L-MOB LOW 2)
- `e2e/strategies.spec.ts` 신규 (9 케이스: H-ST1~H-ST4 HIGH 4 + M-ST5~M-ST7 MEDIUM 3 + L-NAV2 + L-ST8 LOW 2)

### silent 결함 1 — `**/api/logs*` Playwright glob Vite 모듈 intercept

**근본 원인**: `e2e/fixtures/api-mocks.ts` 의 `**/api/logs*` Playwright glob 이 `http://localhost:3000/src/api/logs.ts` Vite 모듈 요청 (resourceType='script') 을 intercept → JSON 반환 → MIME 타입 불일치 → `logs.ts` 모듈 로딩 실패 → `realtime-health.ts` 로딩 실패 → `RealtimeHealth.tsx` 동적 import 실패 → realtime-health.spec.ts 7/8 FAIL.

**시정 (`e2e/fixtures/api-mocks.ts`)**: `**/api/logs*` 핸들러에 resourceType guard 추가.

```javascript
await page.route("**/api/logs*", (route) => {
  // Vite 모듈 요청(src/api/logs.ts 등) 통과 — MIME 타입 불일치 차단
  if (route.request().resourceType() === "script") return route.continue();
  return route.fulfill({ json: envelope([]) });
});
```

**미래 동일 패턴 영구 차단**: Playwright glob 이 Vite 모듈 경로와 충돌하는 경우 resourceType guard 의무 (신규 page.route 추가 시 동일 패턴 적용 의무).

### silent 결함 2 — settings.spec.ts 회귀 (사이클 103 내포 형식 핸들러 LIFO 우선)

**근본 원인**: 사이클 103 api-mocks 에 추가된 `/api/strategies` GET 내포 형식 핸들러 (`{strategies: {momentum: ...}}`) 가 LIFO 우선으로 Settings.tsx 의 `getStrategies()` 에 잘못된 응답 → `name = undefined` → "상한가 모멘텀" 미렌더 → settings.spec.ts 1/13 FAIL.

**시정**:
1. 사이클 103 내포 형식 핸들러 제거 (`e2e/fixtures/api-mocks.ts`)
2. 기존 L103 플랫 형식 핸들러에 4 임계 params 추가 (`stop_loss_rate: -7.5` 등)
3. `frontend/src/pages/Strategies.tsx` 에 `data?.strategies ?? data` fallback 추가 (백엔드 플랫 형식 + 내포 형식 양쪽 처리)

### 검증 결과

- e2e/realtime-health.spec.ts: 8/8 PASS × 3회 반복
- e2e/strategies.spec.ts: 9/9 PASS × 3회 반복
- 전체 e2e 30/30 PASS × 3회 반복 (flakiness 0)
- 기존 spec (settings/dashboard) 회귀 0
- 사이클 80 hotfix #3/#4 Playwright LIFO 영속
- 사이클 89 한글 친숙 용어 영속
- 사이클 81 G-MOBILE-9 영속 (9개 메뉴)
