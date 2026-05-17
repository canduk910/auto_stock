# CLAUDE.md — frontend/ (React 대시보드)

React + TypeScript + Vite 트레이딩 대시보드.

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
- `contexts/TradingStatusContext.tsx::TradingStatusProvider`가 `/api/trading/status`를 5초 폴링하는 단일 소스. 자식은 `useTradingStatus()` hook 공유 (이전 5개 컴포넌트 중복 폴링 → 분당 250KB→50KB)
- App.tsx 최상위 wrap
- QueryClient defaults: `staleTime: 3000`, `gcTime: 5*60*1000`, `retry: 1`, `refetchOnWindowFocus: false`

## 페이지 lazy 로딩
Dashboard만 즉시 import. History/Recommendations/Logs/Settings는 `React.lazy()` + Suspense skeleton (초기 번들 819→656kB). **사이클 6 (2026-05-17)** — `pages/LogReports.tsx` 는 삭제되고 `/logs` 메뉴 안의 "일일 로그 분석" 탭(`components/DailyReportTab.tsx`)으로 통합. `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환 보존

## 시각적 컨벤션
- 이익 `#FF3333` (빨강) / 손실 `#3366FF` (파랑) / 보합 `#333333`
- 금액: 천 단위 콤마 / 수익률: 소수 2자리 + %
- 환경 배너: 실전=빨강 "실전 매매 환경" / 모의=녹색 "모의투자 환경" (`/api/trading/status` 응답)
- **시각 표시는 한국시(KST, `Asia/Seoul`) 강제 (L3, 2026-05-12)** — `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ... })` 또는 `toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })` 사용. `new Date(iso).getHours()/getFullYear()` 등 브라우저 로컬타임 추출 금지(도커 빌드 UTC / 다른 TZ 환경에서 시각 어긋남). 적용 대상: `TradeHistoryGrid.formatDate/formatTime` (Intl.DateTimeFormat formatToParts) / `LogReports.formatDateTime` (toLocaleString + timeZone) / 모든 timestamp 필드. 백엔드 `_to_kst` 헬퍼와 동일 컨벤션. 2026-05-12 005930 보완 INSERT 사고 시각 일관성 점검 산물

## NXT/SOR UI

- **OrderMonitor**
  - `pos.is_next_day=true` 일 때만 "청산" 배지 노출. 백엔드 `Position.is_next_day` 프로퍼티가 `_MULTIDAY_STRATEGIES`(=`{donchian_swing}`) 분기로 항상 False 반환 (2026-05-12 I2) — donchian_swing 멀티데이 보유는 익일 배지 미표시. 다른 전략(momentum/volatility_breakout/long_tail_volatility)은 기존 동작 유지

- **ScanMonitor**
  - phase 라벨(`PHASE_LABELS`): pre_nxt_wait / pre_nxt_trading / main_trading / krx_main_stopped / post_nxt_trading / post_nxt_stopped / recommending / log_analysis
  - 헤더 직하단 활성 보드 배지: KST 시각 → SessionTracker `_BOARD_SCHEDULE`과 동일 매핑(08:00/08:30/09:00/15:30/18:00/20:00). 장 외 시간이면 "장 외 (08:00~20:00 외)"
  - VB/LTV 탭 보드별 시가/타겟가: `BreakoutTarget.boards: Record<string, BoardTarget>` 활용. 활성 보드는 `font-semibold + ring`, 비활성은 톤다운. 정렬·돌파 판정·근접 % 모두 활성 보드 기준. `BOARD_META`로 한글 라벨/색상 매핑
  - **활성 보드 자동 결정 (PR-G P3, 2026-05-15)**: `activeBoardCode` 결정 로직 — (1) 백엔드 응답 boards keys 가 1개면 그 키를 자동 선택 (시각 매핑 무관, 백엔드 의도가 진실의 원천), (2) keys 가 여러 개면 KST 시각 매핑(main > post_nxt > pre_nxt 우선), (3) boards 빈 dict 면 KST 시각 fallback. 결함(KST 19:40 사용자 화면): 백엔드가 `{post_nxt}` 만 반환하는데 UI가 시각 매핑으로 main 시도 → main 데이터 없어 "시가 대기" 22종목 표시. 백엔드 응답 단일 키를 1순위로 삼아 자동 전환. POST_NXT 시간대처럼 백엔드가 활성 보드만 송신하는 케이스에서 UI 토글이 자동으로 그 보드 표시
  - "최근 매수 신호" 표에 `보드` + `타겟가` 컬럼 (`BuySignal.board?` / `target_price?` / `k?`)
  - donchian_swing 탭: 단계별 통과 카운트(`scan_stats`) 막대 + 후보 테이블에 갭률·진입 상태 컬럼 (`Asia/Seoul` `Intl.DateTimeFormat` 사용). 진입 상태: 보유 중/갭 스킵/장 시작 전/진입 시간 종료/진입 대기. "도움말 펼치기" 토글로 4섹션 안내, `gap_skip_threshold`는 백엔드 params 동적 반영
  - **stale 수동 재구독 버튼 (J2, 2026-05-12)**: tick_coverage 배지 우측 인라인 "재구독" 버튼 — `tcStale > 0` 일 때만 노출. 클릭 시 `useMutation(resubscribeStale)` (`api/realtime.ts::resubscribeStale` → `POST /api/realtime/resubscribe`). 성공 시 `invalidateQueries({queryKey:['trading-status']})` + 인라인 메시지 "N종목 재구독 완료" / 실패 시 인라인 에러 메시지. `isPending` 동안 `disabled`. 클래스 `text-xs px-2 py-0.5 rounded border border-amber-300 text-amber-800 hover:bg-amber-100 disabled:opacity-50`. ConfirmModal 없는 read-mostly action(주문 안전성 가드 불필요)
  - **tick_coverage 색상 배지 (G3, 2026-05-12)**: 기존 `구독 중: N개` 옆에 보조 정보 `정상 A종목 · 끊김 B종목 · 등록 C종목` 한글 라벨 노출 + 진행바 우측에 `total / 41` 카운트. `data-testid="tick-coverage-badge"` 의 클래스가 `tick_coverage_stale` 카운트로 분기 — 0=`bg-gray-50 text-gray-700` / 1~5=`bg-yellow-100 text-yellow-800` / 6+=`bg-red-100 text-red-800`. `data-testid="tick-coverage-progress"` 는 `tick_coverage_total / 41` 비율 진행바 — 80%+ 면 `bg-amber-500`, 그 외 `bg-emerald-500`. 라벨 의미: 정상=최근 60초 내 시세 수신(fresh) / 끊김=60초 미수신(stale) / 등록=KIS SUBSCRIBE SUCCESS 확인(acked). 백엔드 `ScanStatus.tick_coverage_*` (optional) 미반영 시점도 0 fallback 으로 무해

- **Settings — `ExchangeBoardRow`**
  - 전략별 `exchange`(KRX/NXT/SOR 라디오) + `tradable_boards`(5개 체크박스, post_nxt 선택 시 amber 강조). 0개 선택 차단
  - **환경 가드**: `useTradingStatus().env`로 모의(`!== 'real'`) 시 NXT/SOR 라디오 disabled + 회색 처리("(모의 불가)") + 저장 시 추가 검증
  - 어느 전략이든 `post_nxt` 활성이면 상단 amber 야간 매매 경고 배너 (사용자 부재 시간대 사고 위험)

- **PARAM_LABELS**: `k_value_krx_main / k_value_nxt_pre / k_value_nxt_post` (step 0.1) 자동 노출 + InfoTooltip
- **시간 문구**: ScanMonitor/Settings/strategyInfo/LogReports/Recommendations 통합 시간으로 갱신 (자동시작 07:45 / NXT 프리 08:00 / KRX 09:00:05 / KRX 마감 15:30 / NXT 종료 20:00 / 정산 20:10)
- **응답 호환성**: top-level `target_price`/`open_price` 유지 + `boards` dict 추가 → 화면 깨짐 0. OrderMonitor 보유 행은 매수가 중심이라 top-level만 사용
- **`updateStrategyParams`**: `params` 타입 `Record<string, StrategyParamValue>`(`number | string | string[] | null`) — tradable_boards/exchange/k_value_* 한 호출로 송신

## 페이지 노트

- **History (`/history`)** — 두 탭
  - 주문체결내역: `TradeHistoryGrid` (raw 행)
  - 매매손익: `TradePnLGrid` (`/api/history/pnl` — 매수·매도 페어 1행, closed/open 사이클). 12 컬럼 + 전략 뱃지. open 행은 매도 컬럼 "—" + "(미실현)" 라벨, emerald-50 배경. 시세 미수신은 "(미실현 시세 대기)"

- **Logs (`/logs`) — 사이클 6 (2026-05-17) 통합 메뉴**:
  - 탭 컨테이너 `pages/Logs.tsx` + URL 쿼리 `?tab=system|daily-report` (기본 `system`, 알 수 없는 값은 system fallback). 두 탭 모두 `data-testid="logs-tab-{key}"` + `role="tab"` + `aria-selected` 명시
  - **시스템 로그 탭** (`components/SystemLogsTab.tsx`): `from_date / to_date` 분리 date input(기본 둘 다 KST 오늘) + 적용 버튼 + 레벨 토글(전체/INFO/WARNING/ERROR/CRITICAL) + 페이징(1-base, size 50). 자동 새로고침 3s 는 **오늘 + page=1** 일 때만 활성(과거 검색·페이징 중에는 비활성). KST 강제 — `Intl.DateTimeFormat('en-CA', timeZone: 'Asia/Seoul')` 으로 today 계산, `toLocaleString('ko-KR', timeZone: 'Asia/Seoul')` 으로 시각 표시. 클라이언트 `from_date>to_date` 가드 → `data-testid="system-logs-date-error"`. API `fetchLogs(filter)` (`api/logs.ts`)
  - **일일 로그 분석 탭** (`components/DailyReportTab.tsx`): 기존 `pages/LogReports.tsx` 본문 추출(JSX 동일). 좌측 영업일 리스트(최근 30일) / 우측 summary + findings 카드(severity + category 칩) + 원본 메트릭 접기. "지금 분석 실행" 버튼 → `POST /api/log-reports/run` (영업일당 1건 UNIQUE). `formatDateTime` export 유지 — L3 회귀 가드 `LogReports.formatDateTime.test.ts` 가 `../../components/DailyReportTab` 로 import 갱신
  - Dashboard 하단의 `LogViewer` 제거 — 운영자가 매매 현황 화면과 로그 검토 화면을 분리. `components/LogViewer.tsx` 파일은 보존(사용처 없음)

- **Recommendations (`/recommendations`) — J4(2026-05-12) 자산 배정 + 로직 자문 카드 / 사이클 1(2026-05-17) 카드 순서 + weight_reasoning amber 영역**: 기존 params 적용 카드 위에 두 신규 카드를 조건부 노출. **자산 배정 카드** (`data-testid="weight-card-{id}"`, recommended_weight 가 null 아닐 때만, **최상단** — 사이클 1 에서 BacktestComparison 위로 이동): 현재→추천 weight + 변경량(%p, 빨강/파랑 컨벤션) + `data-testid="weight-apply-checkbox-{id}"` 체크박스. 체크 시 `applyMutation` body 에 `apply_weight: true` 포함. 적용 후 applied_weight 표시 + amber 안내 "다음 영업일부터 반영". **사이클 1 (2026-05-17) `weight_reasoning` 별도 영역** (`data-testid="weight-reasoning-{id}"`, weight-card 내부 `bg-amber-50 border-amber-200 max-h-32 overflow-y-auto whitespace-pre-wrap`): `rec.weight_reasoning` truthy 시에만 렌더 (1000자 이내, 백엔드 truncate). null 시 미렌더(weight-card 자체는 유지). 비중 변경 사유를 통합 `reasoning` 과 분리해 운영자 시야 집중. **로직/파라미터 자문 카드** (`data-testid="code-review-card-{id}"`, code_review_notes 가 null 아닐 때만): 자유 텍스트 (whitespace-pre-wrap, max-h-64 + overflow-y-auto). 자동 적용 없음 안내. 적용 버튼은 params 키 0개여도 weight 체크박스 ON 이면 활성화 — 단독 weight 적용 가능. **카드 DOM 순서 (사이클 1)**: 자산 배정 → BacktestComparison → 분석 통계 → 추천 근거 → 로직 자문 → 파라미터. 회귀 가드: `frontend/src/pages/__tests__/Recommendations.cardOrder.test.tsx` 2 케이스 + `Recommendations.weightReasoning.test.tsx` 5 케이스
  - **`BacktestComparisonCard` (Phase 4, 2026-05-15 / Phase 6.1 MDD 양수 컨벤션 확정 2026-05-17)**: 자산 배정 카드 *위* 에 `backtest_summary != null` 일 때만 노출. (a) 외부 MCP YAML DSL 지원 3종(momentum/VB/donchian)은 좌(현재)/우(추천) 메트릭 8종 비교 + 차이값 칩(이익색 빨강 / 손실색 파랑 컨벤션) + `data-testid="backtest-card-{strategy}"`. (b) 폴백 3종(LTV/bull_flag/vcp)은 "외부 백테스트 서버 미지원 (Phase 4-bis 대기)" 안내 라벨. `status=running` 분기 시 로딩 스피너. **`max_drawdown` 양수(절대값) 컨벤션 확정** — 외부 MCP 실측 (Phase 6 verify `max_drawdown=16.1`) 으로 양수 반환 검증, `METRIC_SPECS.max_drawdown.diffSignInverted=true` 적용. 양수 diff(추천 MDD 더 큼) = 손실 악화 → 파랑(`#3366FF`), 음수 diff = 손실 완화 → 빨강(`#FF3333`). 회귀 가드: `BacktestComparisonCard.test.tsx > H`. 운영 진단 절차는 `docs/backtest-monitoring.md`

- **Settings**: 비중 슬라이더 하한선 = 보유 포지션 매수금액 비율(`min_weight`, `invested_amount`). 파라미터 편집은 PARAM_LABELS 정의된 number 키만. `position_ratio`는 "전략 내 종목당 비중" — 전략 할당 자금 기준 (순자산 전체 아님), 예상 매수 금액 헬퍼 표시. `getStrategies` 매퍼는 `total_investment`/`invested_amount`/`min_weight` 필수
  - **`CashUsageRatioCard` (J3, 2026-05-12)**: 비중 슬라이더 하단 신설 카드. range 50~100, step 5 슬라이더 + 우측 `data-testid="cash-usage-ratio-percent"` % 표시. GET `/api/strategies/system/cash-usage-ratio` 초기 로드, 저장 버튼 클릭 시 PUT 호출 (debounce 없음 — 명시 commit). 응답 ratio(서버 5% 보정) 로 슬라이더 동기화. 안내 문구 "다음 영업일부터 반영"(text-amber-700). `netAsset` prop(strategies.total_investment 합산 추정) 주어지면 예상 가용액 표시. `useTradingStatus` 의존 안 함 → 단독 렌더 가능. queryKey `['cashUsageRatio']`
  - **`KisQuoteAccountsCard` (사이클 7-D, 2026-05-18)**: `IntegrationToggleCard` 직하 신설 카드. 보조 KIS 시세 계좌 등록/제거/활성화 토글 UI.
    - 표 컬럼: label / 환경 배지(`real`=red / `vts`=emerald) / app_key 마스킹(마지막 4자리만) / app_secret_masked(`****1234`) / 등록일(KST `Intl.DateTimeFormat`) / `quote-account-toggle-{id}` active 토글 / `quote-account-delete-{id}` 삭제 버튼.
    - 빈 목록 시 `quote-accounts-empty` 안내 "등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 41 × (1 + N) 으로 확대".
    - 등록 폼: `quote-account-input-label` / `quote-account-input-kis-env-real|vts` 라디오 / `quote-account-input-app-key` / `quote-account-input-app-secret`(**`type=password`** + `autocomplete=new-password`). 클라이언트 검증: 빈값 거부 + label 형식 `^[A-Za-z0-9\-]+$` 거부 → `quote-account-form-error` 노출 + POST 미발사.
    - `quote-account-submit` 클릭 → `ConfirmModal` 이중 확인 — 등록·active 토글·삭제 모두 안내 메시지 분기.
    - **app_secret 평문 잔존 차단**: 등록 성공 시 `setForm` 빈 값으로 secret state 즉시 클리어 (회귀 가드 `7D-I`). UI 는 `app_secret_masked` 만 참조 (회귀 가드 `7D-H`).
    - 에러 메시지 분기: `axios.isAxiosError` status 코드 별 한글 메시지 (`409: label 중복` / `422: 검증 실패` / 그 외).
    - API: `frontend/src/api/kis-quote-accounts.ts`(`listAccounts/createAccount/updateAccount/deleteAccount`) + `frontend/src/types/kis-quote-accounts.ts`. 백엔드 사이클 7-A 라우트 `/api/integrations/quote-accounts/*` 4종 활용 (변경 0). queryKey `['kis-quote-accounts']`, staleTime 30s. 회귀 가드: `frontend/src/components/__tests__/KisQuoteAccountsCard.test.tsx` 10 케이스 (A 빈목록 / B 1개행+마스킹 / C 폼+POST / D 409 / E 빈값 / F 토글 / G 삭제 / H 평문 부재 / I 폼 클리어 / J password type).
  - **`IntegrationToggleCard` (사이클 5, 2026-05-17)**: `CashUsageRatioCard` 직하 신설 카드. 3 토글 통합(단일 카드 + 분리 행 구조):
    - `data-testid="toggle-dkstock-regime"`: 외부 매크로 서버(dkstock.cloud) 활성. 활성화 후 3s 동안 `data-testid="fetch-progress-dkstock-regime"` 인라인 진행 표시 + marketRegime queryKey invalidate.
    - `data-testid="toggle-kis-mcp"`: 외부 백테스트 서버 활성. 즉시 fetch 없음 (자문 시점에만 사용).
    - `data-testid="toggle-auto-regime-adjust"`: 매크로 레짐 → cash_usage_ratio 자동 갱신 (사이클 2 키 통합 위치).
    - 각 토글에 `data-testid="source-badge-{key}"` 배지: source='db' 면 파란 `DB` / source='env' 면 회색 `env` (DB 미설정 → 환경변수 fallback 가시화).
    - 각 토글 클릭 → `ConfirmModal` 이중 확인 (`매크로 레짐 활성화` heading + 안내 메시지). 활성화 / 비활성화 분기 별 안내 분리.
    - API: `getDkstockRegime / setDkstockRegime` (`frontend/src/api/integrations.ts`) + 동일 패턴 2종. queryKey `['integration', '{key}']`, staleTime 30s, `refetchOnWindowFocus: false`. mutation onSuccess 에서 invalidate.
    - API 에러 graceful: `data-testid="toggle-error-{key}"` 빨간 박스 + "잠시 후 재시도하세요".
    - DB 우선 / .env fallback — 운영자가 DB 토글 후에도 환경변수 그대로 두면 안전망 (Phase 1 / 사이클 2 운영자 영향 0). 회귀 가드: `frontend/src/components/__tests__/IntegrationToggleCard.test.tsx` 6 케이스

## BalanceTable
- **거래시장 배지 (J1, 2026-05-11)**: 보유 종목 헤더 "종목명" 옆 "거래시장" 컬럼. `Holding.nxt_tradable / krx_halted` 조합으로 5가지 배지 노출 — `KRX+NXT`(emerald-100/800) / `NXT만`(amber-100/800) / `KRX`(gray-100/700) / `정지`(red-100/800) / `확인중`(gray-50/500, 모든 필드 null/undefined). `data-testid="market-badge-{ticker}"`. 배지 클래스 베이스 `inline-block px-1.5 py-0.5 rounded text-xs font-medium`(전략 배지 패턴 재사용)

## KisAccountPoolCard (사이클 7-D, 2026-05-18)
- **Dashboard `MarketRegimeCard` 직하** 신설 카드 (시장 상태 → 인프라 상태 위계). WebsocketPool 세션 상태 + 슬롯 사용률 + 분배 모니터링.
- 노출 정보:
  - 우측 상단 `pool-refresh-button` 새로고침 버튼 (`invalidateQueries({queryKey:['realtime-subscriptions']})`)
  - 총 슬롯 사용률 패널 — `pool-used-slots / pool-total-slots` (41 × N) + `pool-usage-progress` 진행바 (80%+ amber / 미만 emerald) + fresh/stale/ACK 카운트 인라인
  - 세션별 표 — `pool-session-row-{label}` (main / quote-1 / quote-2 ...) / label 배지(main=blue 강조 + `(체결통보)` 표기) / `pool-session-status-{label}` 연결 배지(connected=emerald / disconnected=red) / subscribed/limit + `pool-session-progress-{label}` 미니 진행바 / fresh / stale / reconnect_count
- 보조 0개 시 `pool-no-secondary-note` 안내 "보조 세션 없음 (메인 only). Settings > 보조 KIS 시세 계좌에서 등록하면 다음 _boot(07:50) 부터 슬롯이 41 × (1 + N) 으로 확장"
- API: `getSubscriptions()` (`frontend/src/api/realtime.ts`), 사이클 7-B `/api/realtime/subscriptions` sessions 배열 활용. queryKey `['realtime-subscriptions']`, `staleTime: 5_000`, `refetchInterval: 30_000` (자동 30s 폴링 — Trading Status 5s 와 별개 queryKey 로 부하 격리). 에러 시 `pool-error-message` graceful
- 회귀 가드: `frontend/src/components/__tests__/KisAccountPoolCard.test.tsx` 6 케이스 (PA 메인 only + 안내 / PB 메인+보조 2 3행 / PC disconnect red 배지 / PD 슬롯 100% / PE 500 graceful / PF 새로고침 즉시 재조회)

## MarketRegimeCard (사이클 2, 2026-05-17)
- **Dashboard 환경 배너 직하, 전략 탭 위** 신설 카드 (`frontend/src/pages/Dashboard.tsx` `<ControlPanel />` 직후 `<MarketRegimeCard />` 삽입).
- 노출 정보: regime 배지(defensive=red-100/800 / neutral=gray-100/800 / aggressive=blue-100/800 / 비활성=gray-100/500) + VIX/Fear&Greed/Buffett/cycle 메트릭 grid + cash_usage_ratio + auto_regime_adjust 토글
- 매수 가드 활성 시(`buy_blocked=true`) `data-testid="market-regime-block-banner"` amber 배너 + block_reason + "보유 종목 청산은 정상 작동합니다. 매수만 차단됩니다." 안내
- `auto_regime_adjust` 토글 (`data-testid="auto-regime-toggle"`) ON/OFF 클릭 시 ConfirmModal 이중 확인 — ON: "다음 영업일부터 cash_min 기반 자동 갱신" / OFF: "운영자 수동값 보존" 안내
- API: `getMarketRegimeCurrent()` (queryKey `['marketRegime']`, staleTime 60s) + `setAutoRegimeAdjust(boolean)` + `getMarketRegimeHistory(days)`
- `enabled=false` (DKSTOCK_REGIME_ENABLED=false) 시 "비활성" gray 배지 + 메트릭은 "—" 표시. 매수 가드 비활성, 토글 변경 의미 없음
- 회귀 가드: `frontend/src/components/__tests__/MarketRegimeCard.test.tsx` 7 케이스 (defensive 배지 + 배너 / aggressive 배지 / 메트릭 grid / 토글 ConfirmModal / PUT API 호출 / API 에러 graceful / enabled=false 비활성 배지)

## 주문 안전성
- 시작/정지/매도 등 주문 관련 버튼은 ConfirmModal 이중 확인 필수

## 백엔드 연동
- 모든 API 호출은 `api/client.ts` axios 인스턴스 경유
- 응답은 `types/common.ts::ApiResponse<T>`로 파싱
- 백엔드 응답 필드명 = TypeScript 속성명 (1:1, 변경 시 동기화)
- 페이징 응답에 `total`/`total_pages` 필드 필수
