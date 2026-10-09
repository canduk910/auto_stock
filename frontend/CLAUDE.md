# CLAUDE.md — frontend/ (React 대시보드)

> 이력: [`docs/history/frontend-CLAUDE.history.md`](../docs/history/frontend-CLAUDE.history.md) · 사이클 보고 원문: [`docs/HARNESS_CHANGELOG.md`](../docs/HARNESS_CHANGELOG.md)
>
> **지금 화면이 지키는 계약만** 적는다. 경위·실측·결정 근거는 history 로 간다.

React + TypeScript + Vite 트레이딩 대시보드.

## 실행

```bash
npm install
npm run dev    # http://localhost:3000 (vite.config.ts server.port)
npm run build  # tsc -b + vite build
npm run lint
npm test       # vitest run
```

dev 프록시(`vite.config.ts`)는 두 갈래다. `/api/macro` → `VITE_MACRO_API_URL`(기본 `http://localhost:8010`, `X-API-Key` 없음) ·
`/api` → `VITE_API_URL`(기본 `http://localhost:8001`). vite 는 첫 매치를 쓰므로 `/api/macro` 를 `/api` **앞**에 둔다.

## 디렉토리

```
src/
├── api/        # axios 호출 (client.ts: `baseURL: '/api'` + `withCredentials: true`, 401 인터셉터 없음)
├── components/
├── contexts/   # TradingStatusContext 등
├── macro/      # /macro 화면 (macro_lite 이식, 「Macro」 절)
├── pages/
├── test/       # MSW handlers · factories · 골든 픽스처 · 가짜 klinecharts
├── types/      # 백엔드 src/models/ pydantic 1:1 매핑
└── utils/      # kst.ts · pnlColor.ts · contentWidth.ts · stockChart.ts 등 단일 출처 유틸
```

## 핵심 라이브러리

TanStack Query (서버 상태) · TanStack Table (그리드) · Recharts (차트) · KLineChart (종목 차트 모달 전용 분리 청크 — 「종목 차트 모달」 절) · Tailwind v4 · React Router

## 단일 polling owner

- `contexts/TradingStatusContext.tsx::TradingStatusProvider`(App.tsx 최상위 wrap)가 `/api/trading/status` 를 5초 폴링하는 단일 소스다. 자식은 `useTradingStatus()` 를 공유한다(중복 폴링 차단)
- QueryClient defaults: `staleTime: 3000` / `gcTime: 5*60*1000` / `retry: 1` / `refetchOnWindowFocus: false`

## 페이지 lazy 로딩

Dashboard 만 즉시 import. 나머지 11 페이지(History · Recommendations · Logs · Settings · StrategyFunnel · StockMaster · RealtimeHealth · Strategies · MarketState · `macro/MacroPage` · Backtest)는 `React.lazy()` + Suspense skeleton. `/log-reports` 는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환.

## AppShell 레이아웃 — 화면 폭 슬라이더

- **상태**: `App.tsx::AppShell` 의 `useContentWidth()` — localStorage `autostock.contentWidth`(정수 level 0~100, **기본 100=전체폭**). mount 시 lazy `useState` 로 복원, `setLevel` 이 state·localStorage 를 함께 쓴다(저장 실패는 try/catch).
- **슬라이더**: 나브 PC 행(`hidden sm:flex`) 우측 `ml-auto` 의 `<input type="range" min=0 max=100 step=5>`(`data-testid="content-width-slider"`, `aria-label="화면 폭 조정"`, Arrow/Home/End). **모바일에는 없다**.
- **적용**: **`<main>` 만** 반응한다 — `<main style={{ maxWidth: contentMaxWidth(level) }}>`, `contentMaxWidth(level) = max(1024px, {60 + level*0.4}%)`(상한이라 소화면에서 넘치지 않는다).
- 🔴 **나브는 기본폭 고정**(`NavBar.tsx` `NAV_INNER_MAX_WIDTH` = `contentMaxWidth(기본 level)`). **동적 폭으로 되돌리지 않는다** — 슬라이더가 그 안에 있어 드래그 중 포인터와 어긋난다(cycle288).
- 가드 `src/__tests__/ContentWidthSlider.test.tsx` — **T6**(나브 고정 ∧ main 반응) · **T7**(슬라이더가 `nav-inner` 안) 포함.

### 나브 2단 카테고리 구조

나브 = **`src/components/NavBar.tsx`**(`App.tsx` 는 라우트·레이아웃·`useContentWidth` 소유만). 공유 상수·훅(`CONTENT_WIDTH_*`·`contentMaxWidth`·`useContentWidth`)의 단일 출처 = **`src/utils/contentWidth.ts`**.

leaf 12개를 **상위 9개**로 묶는다(사용자 지정 묶음·순서 — 바꾸지 않는다):

| 상위 | 세부 | 경로 |
|---|---|---|
| 대시보드 | (단독) | `/` |
| 거래 내역 | (단독) | `/history` |
| 로그 | (단독) | `/logs` |
| **종목** | 조건검색 추적 · 종목마스터 | `/strategy-funnel` · `/stock-master` |
| **전략** | 전략 현황 · 전략수정 AI자문 | `/strategies` · `/recommendations` |
| 매크로 | (단독) | `/macro` |
| 백테스팅 | (단독, 30년 전략 성적표 연구 보고서) | `/backtest` |
| 설정 | (단독) | `/settings` |
| **운영상태** | 장운영상태 · 실시간 상태 | `/market-state` · `/realtime-health` |

- `NavEntry = leaf{to,label} | group{id,label,children}` — **드롭다운 유무를 데이터가 정한다**(컴포넌트에 분기를 흩뿌리지 않는다). 단독 항목엔 드롭다운을 만들지 않는다.
- 세부 경로에 있으면 상위 트리거도 활성(`bg-gray-100`).
- 그룹 트리거 = **disclosure 패턴**(`aria-expanded` 만). `aria-haspopup` 을 두지 않는다 — `role=menu`/`menuitem` 이 없어 스크린리더에 거짓 약속이 된다.
- 키보드: Enter/Space 열기 · ArrowDown/Up 이동 · Escape 로 닫고 트리거 포커스 복귀 · 항목 선택 뒤에도 트리거로 복원(`<body>` 로 떨어지지 않게). 포커스 트랩 없음.
- 닫힘 3: 바깥 클릭 · 포커스 이탈(`onBlur`/focusout) · 라우트 이동(뒤로가기 포함). `openGroup` 단일 상태라 하나만 열린다.
- 모바일 드로어는 **접지 않는다** — 그룹 제목(링크 아님) + 들여쓴 하위로 leaf 12개를 늘 보인다.
- 🔴 **경로 12/12 이 메뉴에서 도달 가능해야 한다** — 묻힌 메뉴는 URL 을 직접 쳐야만 보인다. `AppShell.test.tsx` 가 href 12개 집합을 단언한다. `/log-reports` 는 구 북마크 리다이렉트라 메뉴가 아니다.
- 보존 testid 4: `nav-sticky-wrapper` · `content-width-slider` · `mobile-menu-button` · `mobile-menu-drawer`. 그룹용 = `nav-inner` · `nav-mobile-group-{id}` 등.
- ⚠️ e2e: 접힌 그룹의 하위 라벨은 DOM 에 없다. 본문 제목은 `getByRole("heading", {name})`(`getByText` 는 모바일 헤더의 숨은 span 을 집는다), 그룹 트리거는 `getByRole("button", {name, exact: true})`.

## 표 스크롤 — `ScrollPane` 단일 진실원

표는 **창 크기에 맞춰** 가로·세로로 스크롤한다. 담당 = `components/ScrollPane.tsx` 하나. 막는 결함 = 높이 상한 없는 `overflow-x-auto` 래퍼의 가로 스크롤바가 래퍼 **바닥**(화면 밖)에 붙는 것.

- **`maxHeight` = 창 높이 − 요소의 화면상 top − `bottomGutter`(24)**, 하한 `minHeight`(220).
- 🔴 **`top` 은 화면 안(`0 ≤ top < viewport`)일 때만 뺀다** — 밖이면 **창 전체**가 예산이다(`top < 0` 을 빼면 스크롤바가 다시 화면 밖, `top >= viewport` 를 빼면 220px 표). 이 두 경우를 **스크롤 리스너로 풀지 않는다**(pane 이 커지며 아래 내용이 점프한다).
- 🔴 **측정은 `resize` · `ResizeObserver(document.body)` 만 듣고 `scroll` 은 듣지 않는다**(되먹임 루프). 갱신 문턱 `TOLERANCE_PX`(8)가 1px 진동 무한 루프(`ResizeObserver loop`)를 막는다.
- **측정 불가(jsdom·SSR·`ResizeObserver` 부재) = `70vh` 폴백** — **상한 없는 상태로 돌아가지 않는다** — 상한이 없으면 고치려던 결함이 재현된다. `data-measured` = `px|vh`.
- 머리글 기본 고정(`stickyHeader`, `[&_thead_th]:sticky`). 표가 아니면 `stickyHeader={false}`.
- 🔴 `{...rest}` 는 `data-testid` **뒤** — 교체 자리의 기존 `data-testid`(예: `stock-master-daily-table`)가 이겨야 그 회귀 가드가 산다.
- **적용 = `<ScrollPane` 24곳**(`grep -rn '<ScrollPane' frontend/src`). 표가 있는 화면은 이것을 쓴다.
- ⚠️ **일부러 뺀 곳 2** — `pages/Recommendations.tsx` 파라미터 표(표 안 `InfoTooltip` 이 `absolute bottom-full` 이라 잘린다) · `macro/components/MacroCycleSection.tsx`(30줄 지표표). 🔴 **표 안에 `InfoTooltip`(또는 다른 `absolute` 팝오버)이 있으면 씌우기 전에 잘림부터 확인한다**.
- 회귀 = `components/__tests__/ScrollPane.test.tsx`(**값 검사** — 실제 `maxHeight` 픽셀) · **E2E `e2e/scroll-pane.spec.ts` 불변식 넷** = ① 상한이 걸린다 ② **창 높이를 넘지 않는다** ③ **`minHeight` 에 갇히지 않는다** ④ 화면 안 표는 바닥도 화면 안. ⚠️ 모든 pane 에 「바닥 ≤ 창높이」를 요구하지 않는다(긴 페이지의 표는 화면 아래가 정상) · 창 축소 검증은 **`max-height`** 로 · `/history` 탭은 `role="tab"` 이 아닌 평범한 `<button>`.

## 시각적 컨벤션

- **DK Stock 디자인시스템 v2 — 가을 팔레트 + Gmarket Sans.** 로고타입 `components/NavBar.tsx`(`font-brand`). 본문 `font-sans` = Gmarket Sans(Light 100–300 / Medium 400–500 / Bold 600–900, `font-display: swap`, `public/fonts/GmarketSans{Light,Medium,Bold}.ttf`).
- `src/index.css` Tailwind v4 `@theme` 가 `red/blue/gray` 를 가을 톤(rust/slate-blue/warm-gray)으로 재정의하고 별칭 `green→sky, amber/yellow→beige, purple/violet/indigo→navy, pink/orange→brown, emerald→blue, cyan→sky, slate→gray` 를 둔다(기존 `bg-*-*` 가 그대로 새 톤, `navy/beige/brown/sky` 직접 사용 가능).
- 🔴 색의 단일 진실원 = `src/index.css`(`@theme`) + `utils/pnlColor.ts`/`types/strategy.ts`(파생 hex). **다른 소스 파일에 색 hex 리터럴을 새로 두지 않는다**(가드 `src/__tests__/designSystem.v2.test.ts` — `#FF3333`/`#3366FF`/`#333333`/`#2563eb` 전수 부재).
- **손익색 (`utils/pnlColor.ts`)**: 이익 `PROFIT_HEX '#c34a36'`(rust, red-500) / 손실 `LOSS_HEX '#3d73b7'`(slate-blue, blue-500) / 보합 `NEUTRAL_HEX '#41403b'`(gray-700). `pnlColorClass(value)` → `text-pnl-profit`/`text-pnl-loss`/`text-pnl-flat`(`@theme` `--color-pnl-{profit,loss,flat}` 과 같은 값 — `designSystem.v2.test.ts` 가 대조). `pnlColorHex(value)` = 인라인 style 용(undefined/null/NaN → NEUTRAL). ⚠️ `TradePnLGrid`/`BreakoutCandidateMonitor` 의 `text-red-600`/`text-blue-600` 은 별개 shade 라 넣지 않는다.
- **전략 7색 (`types/strategy.ts::STRATEGY_COLORS`)**: momentum `#3d73b7`(blue) · volatility_breakout `#364c6d`(navy) · long_tail_volatility `#b39364`(beige) · donchian_swing `#488eb4`(sky) · bull_flag_breakout `#c34a36`(red) · vcp_breakout `#9d6644`(brown) · kojiro `#141c2b`(navy 900) · DEFAULT `#74716a`(gray). `bg/text/badge` 는 그 이름의 `@theme` 토큰(별칭 포함).
- **전략 한글 표시명의 단일 진실원 = `utils/strategyMeta.ts::strategyLabel(id, apiName?)`**(cycle395) — momentum=모멘텀 · volatility_breakout=변동성 돌파 · long_tail_volatility=롱테일 변동성 · donchian_swing=돈키언 추세 스윙 · bull_flag_breakout=추세 눌림목 돌파 · vcp_breakout=VCP 변동성 수축 · kojiro=고지로 대순환. 이 7 전략은 백엔드 API 가 주는 `name`(경로마다 표기가 다르다 — 예: params-schema 는 momentum 을 "상한가 모멘텀"으로 부른다)보다 이 표가 항상 우선한다. 화면에 전략 id 를 보일 때는 반드시 이 함수를 거친다 — id 리터럴 노출·화면별 로컬 이름 사본 금지.
- ⚠️ **별칭 때문에 다른 상태가 같은 hex 로 겹칠 수 있다** — 새 배지 색은 별칭표를 먼저 대조하고 배경 sRGB/ΔE2000 거리로 검증한다. 현행 = `ScanMonitor` `BOARD_META` 5보드 blue/sky/navy/beige/brown · `IntegrationToggleCard` `ToggleRow` ON 배지 sky · `PortfolioRiskCard` `AccountGateBlock` '경고' `beige-200/800` · `TradeHistoryGrid` PARTIAL `brown-200/800`. 가드 = `ScanMonitor.boardColorAlias.test.tsx` / `IntegrationToggleCard.badgeAlias.test.tsx` / `badgeContrast.cycle261.test.tsx`.
- **서체 nginx 캐시**: `nginx.conf.template`/`nginx.tls.conf.template` 의 `location ^~ /fonts/ { expires 30d; add_header Cache-Control "public, max-age=2592000"; default_type font/ttf; }` — 정적자산 정규식에 `ttf` 가 없어 이 블록이 없으면 `/fonts/*.ttf` 가 SPA fallback 의 `no-store` 를 받는다(파일명에 해시가 없어 `immutable` 대신 유한 TTL). 가드 `tests/unit/ast/test_cycle261_font_cache_headers.py`.
- 금액 천 단위 콤마 · 수익률 소수 2자리 + % · 환경 배너 실전=빨강(`bg-red-600`) "실전 매매 환경" / 모의=`bg-sky-600` "모의투자 환경"
- 슬라이더 accent = `'var(--color-navy-600)'`(리터럴 hex 대신) — `components/NavBar.tsx` · `CashUsageRatioCard.tsx` · `TradeAmountFilterCard.tsx` · `PriceFilterCard.tsx`(최소/최대) 5곳. 새 슬라이더도 같은 값.
- **시각 표시는 KST 강제** — 단일 진실원 `src/utils/kst.ts`: `formatKstHHMM(iso)`(HH:mm, `hour12:false`) · `formatKstDateTime(iso)`(`yyyy-MM-dd HH:mm:ss`) · `kstTodayISO(now?)` · `kstMinutesOfDay(now?)` · `isKrxMainSession(now?)`(상수 `KRX_MAIN_OPEN_MINUTE`·`KRX_MAIN_CLOSE_MINUTE`) · 차트용 `formatKstDateFromEpochMs(ms)`(`YYYY-MM-DD`) · `formatKstYearMonthFromEpochMs(ms)`(`YYYY-MM`) · `kstDateToEpochMs(ymd)`(`YYYY-MM-DD` → KST 자정 epoch ms, 형식이 다르면 `null`) · 상수 `KST_TIME_ZONE`. 잘못된 입력은 `'—'`.
  - 🔴 **새 KST 표기는 이 유틸에 위임한다** — 신규 `Intl.DateTimeFormat`/`toLocale*String` 생성 금지(`utils/__tests__/kst.test.ts` K4, `DELEGATING_FILES` = `src/` 기준 상대 경로). 위임 5파일 = `PortfolioRiskCard` · `DailyReportTab` · `pages/Recommendations`(서식 `yyyy-MM-dd HH:mm:ss`, 빈 값 `'-'`) · `components/StockChartModal` · `utils/stockChart` — `'Asia/Seoul'` 리터럴도 금지(K4-c, 차트 tz 는 `KST_TIME_ZONE`). 나머지는 **사이트별 출력 스냅샷 승인 후 점진 이관**한다.
  - `new Date(iso).getHours()/getFullYear()` 등 브라우저 로컬타임 추출 금지(도커 UTC·다른 TZ 에서 어긋난다).
- ⚠️ **타입 검사는 `npx tsc -b`** — 루트 `tsconfig.json` 이 `files: []` 솔루션 형식이라 `npx tsc --noEmit` 은 **0개** 검사한다(`GateLevel` 유니온 등은 `tsc -b` = `npm run build` 1단계만 잰다).

## 테스트 규약 (공통)

여기 한 번만 적는다. 신규 카드·페이지·목 전부 해당한다.

1. **모든 `useQuery` 에 `retry:` 를 명시한다**(전역 기본값이 있어도) — 백엔드 없는 e2e 에서 ECONNREFUSED 재시도가 spec timeout 을 낸다. 기본값은 `retry: 1` 이다. **예외 = 5초 폴링(`refetchInterval: 5000`) 쿼리는 `retry: 0`(또는 `false`)** — 다음 폴링이 재시도를 맡고, `retry: 1` 이면 실패마다 요청이 두 배가 된다(현재 `OrderMonitor` 의 `/api/costs/today` · `TradingStatusContext` 의 `/api/trading/status`). AST 가드 `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts`(카드 + `TARGET_PAGES` 전수)는 `retry:` 키가 있는지(값 `false`/`0`~`3`)만 본다.
2. **Playwright route 매칭은 LIFO**("latest registered route wins") — 구체 라우트는 wildcard **뒤**에 등록한다. 가드 `tests/unit/e2e_mocks/test_api_mocks_routes_registered.py`(`..._specific_routes_registered_after_wildcard`).
3. **`frontend/src/api/*.ts` 엔드포인트 ↔ `e2e/fixtures/api-mocks.ts` route glob 정합.** 가드 `_ast_api_mocks_coverage.test.ts`.
4. **glob 이 Vite 모듈 경로(`/src/api/*.ts`)와 겹치면 resourceType 가드 의무** — `**/api/logs*` 같은 glob 이 스크립트 요청까지 잡아 모듈 로딩을 깬다. 핸들러 첫 줄 `if (route.request().resourceType() === "script") return route.continue();`. `/api/strategies` e2e mock 은 **플랫 형식 하나만** 등록한다(내포 형식이 LIFO 로 이기면 `name = undefined`).
5. 🔴 **목은 *의도한 계약* 이 아니라 *실제 응답* 을 담는다** — 실제로 받은 응답(curl·운영 로그)을 **그 모양 그대로 리터럴로** 박고, 생성기로 합성하지 않는다. 대상 = `frontend/src/test/handlers.ts`(MSW) · `frontend/src/test/factories.ts` · `e2e/fixtures/api-mocks.ts`(LIFO 정합) + 백엔드 계약 테스트 DB 스텁(`tests/contract/`). 이유: PG NUMERIC 은 asyncpg `Decimal` → pydantic v2 JSON **문자열**이라, 숫자 목은 초록인 채 화면을 깨거나 **조용히 비운다**(사례 = [history](../docs/history/frontend-CLAUDE.history.md) 「테스트 규약 (공통)」 5 — 세 화면이 망가져 있던 경위). 수치 렌더는 **방어 변환을 거친 값에만** 건다(`toNum`/`toSafeNumber` 계열 — 숫자·숫자 문자열을 받고 진짜 결측만 `-`). `typeof v === 'number'` 단독 판정 · 미검증 값의 `toLocaleString`/`toFixed` 직접 호출 금지.
6. **골든 픽스처는 손으로 고치지 않는다** — `GET /api/strategies/params-schema` 목 2개(`frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts`)는 `src/engine/param_catalog.py` + 7 전략 `DEFAULT_PARAMS` 에서 **기계 생성**한다. 카탈로그나 `DEFAULT_PARAMS` 중 하나라도 바뀌면 생성기를 다시 돌린다:

   ```bash
   KIS_APP_KEY=x KIS_APP_SECRET=x KIS_ACCOUNT_NO=x SUPABASE_URL=http://x SUPABASE_KEY=x \
       python tools/test_fixtures/gen_param_schema_fixture.py
   ```

## OrderMonitor

- `pos.is_next_day=true` 일 때만 "청산" 배지. 백엔드 `Position.is_next_day`(`strategy_base.py`)는 `_MULTIDAY_STRATEGIES`(**코드 정본 = `{donchian_swing, vcp_breakout, kojiro}`**)면 항상 False, 나머지는 `buy_date < 오늘(KST)`
- 오늘 실현 순손익(추정, testid `order-monitor-net-pnl`) — `GET /api/costs/today?strategy=`(scheduler 무접촉). 전체 탭은 strategy 없이, 전략 탭은 `strategy=<id>` 로 조회해 `total.net_pnl` 을 정수 원으로 보인다. `cost_status` 가 `estimated`/`mixed` 면 「추정」 배지(머리줄 전체에서 「추정」 은 이 배지 한 번뿐이다). 쿼리 = `retry: 0` + `refetchInterval: 5000`(세전 실현 손익과 같은 주기, 위 「테스트 규약」 1 예외).
- 조회가 실패하면(`isError`) 마지막 성공값을 남기지 않는다 — `order-monitor-net-pnl` 에 「—」, 옆 `order-monitor-net-pnl-error` 에 「조회 실패」(「실현 손익」 이라는 말을 담지 않는다). 첫 조회부터 실패해도 같은 자리에 그린다. 기존 「실현 손익」(세전, 전략별 `daily_realized_pnl` 합산)은 그대로 보인다.
- 머리줄은 `flex-wrap gap-2` 이고 제목 「주문처리 현황」·「조회 실패」 는 `whitespace-nowrap` 이다 — 좁은 폭(400px)에서 배지 묶음이 다음 줄로 내려가고, 글자 단위로 꺾이지 않는다.

## 세후(net)/세전(gross) 토글 — 실적 화면 공통 (cycle411)

- 모든 실적 화면의 기본 표시는 **세후**(net, 실비용 = 수수료+세금 차감)다. 공유 훅 `utils/costBasis.ts::useCostBasis()` 가 localStorage 키 `autostock.costBasis`(`net`|`gross`)에 선택을 기억하고(read/write 모두 try/catch — 사생활 모드 등 예외에서도 화면은 그려진다), `window` 커스텀 이벤트로 같은 창에 동시에 떠 있는 다른 컴포넌트의 토글도 함께 바꾼다(Context Provider 불필요). 공유 버튼은 `components/CostBasisToggle.tsx`(testid `cost-basis-toggle`, 안의 `세후`/`세전` 버튼 `aria-pressed`). `PerformanceCard`·`ProfitChart` 가 이 토글을 쓴다. net 칸이 없거나(구 서버) `null` 이면(비용 조회 실패 = 「모름」) 세전 값으로 폴백하고, 폴백한 자리에 「세전」 을 밝힌다 — 빈 칸·NaN·「0원」 을 만들지 않는다. 세후 값이 있으면 「세전」 을 달지 않는다.
- `PerformanceCard` — 누적/일평균 수익률 카드는 `net_total_profit_rate`/`net_avg_daily_profit_rate`(세후, `/api/performance/summary`) 기본, 토글로 `total_profit_rate`/`avg_daily_profit_rate`(세전). 세후 모드인데 그 칸이 `null` 이면(`!= null` 로 거른다) 세전 값을 보이고 **그 카드**에만 「세전」 을 단다. 실현 성과 행(`realized-pnl-*`)도 `realized_net_sum_krw`(세후) 기본 / `realized_sum_krw`(세전) — 세후 칸이 `null` 이면 세전 합 + 「세전」. 승률 줄(`realized-winrate-*`)은 세전 모드에서 `win_rate_gross`·`win_gross`·`loss_gross` 를 쓰고(없으면 세후 값), 세후 모드에서 `win_rate`·`win`·`loss` 를 쓴다.
- `ProfitChart` — 차트 컨테이너 testid `profit-chart-daily`/`profit-chart-cumulative`(각 `data-series` 속성 = 그리는 dataKey, jsdom 에 SVG 가 안 그려져 테스트가 이 속성으로 확인한다). 세후는 `net_daily_profit_rate`/`net_cumulative_return_rate`, 세전은 `daily_profit_rate`/`cumulative_return_rate`. 세후 모드여도 한 행이라도 net 칸이 없거나 `null` 이면 그 차트 전체를 세전 시리즈로 그린다. 제목과 범례에 실제로 그린 기준(세후/세전)을 적는다 — net 이 빠져 세전으로 그렸으면 「세전」.

## ScanMonitor

- `phase` 라벨 = `PHASE_LABELS`(없는 phase 는 `idle` 라벨)
- 활성 보드 배지 = **프론트 자체 KST 시각 매핑**(`activeBoards`) — `pre_nxt` 08:00~09:00 · `krx_open` 08:30~09:00 · `main` 09:00~15:30 · `krx_after` 15:30~18:00 · `post_nxt` 15:30~20:00, 없으면 "장 외 (08:00~20:00 외)". ⚠️ 백엔드 `session.py::_BOARD_SCHEDULE`(3보드, `main` ~15:39:59 · `post_nxt` 15:40~)과 **다르다** — 정본 `src/engine/CLAUDE.md` 「session.py」 절
- VB/LTV 탭 보드별 시가/타겟가 `BreakoutTarget.boards: Record<string, BoardTarget>` — 활성 보드 `font-semibold + ring`, 비활성 톤다운. 정렬·돌파·근접 % 모두 활성 보드 기준. 라벨·색 `BOARD_META`
- **BREAKOUT_KEYS 4종** `volatility_breakout` / `long_tail_volatility` / `bull_flag_breakout` / `vcp_breakout`, `BREAKOUT_LABELS` = "변동성 돌파" / "롱테일 변동성" / "눌림목 돌파" / "VCP 변동성 수축". BFB/VCP 도 `isBreakout` 분기(MAIN 단일 보드)
- **활성 보드** (`activeBoardCode`): boards 키 1개면 그 키(시각 무관 — 백엔드 응답이 진실의 원천) / 여러 개면 KST 시각 매핑(main > post_nxt > pre_nxt) / 빈 dict 면 KST 시각 fallback
- "최근 매수 신호" 표 `보드` + `타겟가` 컬럼(`BuySignal.board?` / `target_price?` / `k?`)
- donchian_swing 탭: `scan_stats` 단계 막대 + 후보 갭률·진입 상태(보유 중/갭 스킵/장 시작 전/진입 시간 종료/진입 대기) + "도움말 펼치기". 갭 임계 = `params.gap_skip_threshold`(없으면 `SWING_GAP_SKIP_PCT` 3.0)
- **"돌파" 라벨** (`BREAKOUT_KEYS`): `curPrice >= targetPrice` 면 활성 보드 ∩ `tradable_boards` — ∋ 빨강 "돌파" / ∅ 회색 "돌파 (대기 — {보드라벨})" + `title` "이 전략은 X 에서만 매매" / `tradable_boards` 미존재 → 빨강 "돌파" fallback. BFB/VCP 는 전용 컴포넌트의 진입 게이트가 대신한다.
- 인프라 표시(구독 커버리지·재구독·끊김 종목)는 **`KisAccountPoolCard` 소관** — 여기는 `subscribed_count` 카운트만 둔다.

### STAGES 계약

`ScanFunnelBars` STAGES 는 **live 백엔드 키만** 참조한다 — VB 5키 · LTV 6 · momentum 6 · BFB 9 · VCP 9 · donchian(`SWING_STAGES`) 8. `scan_stats` 가 없으면 "아직 스캔 전"(옵셔널 타입 가드).

- VCP = `trend_filter_pass` / `base_pass` / `pullback_pass`(`_scan_stats` 키). "합집합" = `universe_union`. `universe_candidates` 는 **시총+거래대금 컷 통과** 후 숫자라 step1 라벨을 "원천 유니버스 후보"로 쓰지 않는다.
- VB·LTV `_empty_scan_stats` 의 미세팅 키(`price_filtered`/`mcap_pass`/`trade_amount_pass`)를 **`VB_STAGES`·`LTV_STAGES` 가 참조하지 않는다**(영원한 0 이 뜬다). momentum 의 `mcap_pass`·`trade_amount_pass` 는 `scanner.py` 가 세팅하는 live 키라 `MOMENTUM_STAGES` 가 쓴다.
- 가드 `ScanMonitor.cycle175.test.tsx` · `ScanMonitor.cycle178.test.tsx`.

### kojiro 탭 (`KojiroMonitor.tsx`)

`selectedStrategy === 'kojiro'` 분기의 전용 6패널. 데이터는 `strategies.kojiro`(scan_stats/targets/buy_signals/positions_detail/params)에 있고, 백엔드는 `get_targets_status` 에 `atr_ratio` 1키**만** 더한다.

- ① 상태 배너(`kojiro-darklaunch-banner`, **`kojiro.enabled` 조건부** — 활성=amber "실매매 진행" / 비활성=navy "관찰 모드", last_run_at)
- ② 대순환 사이클(`kojiro-stage-cycle`, 6스테이지 1→2→…→6↩1 + `targets.stage` 분포 `kojiro-stage-count-{s}`)
- ③ 유니버스 깔때기(`kojiro-scan-funnel` 9단계, `universe_union`→…→`final_prepared`, 0단계 rose)
- ④ 후보 그리드(`kojiro-candidate-{ticker}`) — 종목명(`t.name || ticker`, `_candidates[ticker]` 저장값이라 **정산 후·주말에도 유지**) · stage 배지 · EMA 5/20/40 정배열 · ATR 밴드 게이지(`atr_ratio` 또는 atr/prev_close, `params.atr_ratio_min~max`)
- ⑤ 진입 이벤트(`kojiro-entry-feed`, buy_signals)
- ⑥ 보유 방어선(`kojiro-defense-{ticker}`) — 4중 청산선 `buy−stop_atr×atr` / `high−trail_atr×atr` / `buy×(1+hard_stop_pct/100)` / stage3. **프론트 계산**(targets.atr + positions + params), 활성 방어선 = 현재가 아래 max.

가드 `KojiroMonitor.test.tsx` + `ScanMonitor.kojiro.test.tsx`.

### VCP/BFB 탭 (`BreakoutCandidateMonitor.tsx`)

`isBreakout` 을 `isVbLtv`/`isVcpOrBfb` 로 갈라 **VB/LTV 경로는 byte 동일 보존**, VCP/BFB 만 전용 컴포넌트. 패널 3:

- ⓪ **진입 게이트**(`breakout-entry-window`) — `params.entry_start~entry_end` KST 판정(VCP 09:05~14:30 / BFB 09:05~13:00 은 MAIN 안이라 보드 판정을 포함한다).
- ① **구독 커버리지**(`breakout-subscription-coverage`) — `scan.subscribed_tickers` ∖ `scanned_tickers`. 미수신 종목은 `on_tick` 이 없어 `check_buy_signal` 이 불리지 않는다.
- ② **후보 그리드**(`breakout-candidate-row-{ticker}`) — 종목명/현재가/돌파선/거리%/손절선/측정목표(BFB)/거래량컷/상태. 돌파선 근접순, 미수신은 최하단. 상태 배지 `breakout-status-{ticker}` 우선순위 = 매수완료 > 쿨다운 D-n > 📵미구독 > ⏱m:ss 대기(BFB `breakout_seen_at`+`retention_minutes`) > 대기.

백엔드는 `get_targets_status` 에 키를 **추가만** 한다(`name`/`prev_close`/`stop_line`/`measured_target`/`volume_threshold`/`bought_today`/`in_cooldown`/`cooldown_until`/`breakout_seen_at`/`retention_minutes` — `strategy_registry` 가 덕타이핑 제네릭이라 registry·route 수정 0). ⚠️ **VB 호환 5키는 `scheduler._confirm_breakout_open_prices` 가 소비하므로 제거 금지**(`scheduler.py` 는 승인 대상 — 루트 「자율 진행과 승인 빈도」 절). 가드 `BreakoutCandidateMonitor.test.tsx`.

## StrategyFunnel (`/strategy-funnel`)

전략별 조건검색 단계별 후보/탈락 추적. 전략 dropdown + 날짜 picker + 단계별 expand 테이블(`survived_tickers` + `excluded_sample` 탈락 사유) + 수동 trigger(`POST /api/strategy-funnel/snapshot`). API `getFunnel / getRecentFunnel / triggerFunnelSnapshot`(`frontend/src/api/strategy-funnel.ts`). queryKey `['strategy-funnel', target_date, strategy_id]` · 추이 `['strategy-funnel-recent', strategy_id]`.

- 단계명 옆 `조건` 툴팁(`data-testid="funnel-step-conditions-..."` + `title`) · ticker 옆 종목명(`SurvivedItem` 타입 + dict/string 분기) · 탈락 사유에 수치(예: `"음봉 비율 35% > 30%"`).
- `FunnelSnapshot.is_provisional === true` 행은 amber "잠정" 배지(`funnel-provisional-badge-{sid}-{step_no}`, title="21:00 저녁 잠정 캡처 — 익일 아침 마스터 델타 반영 전 (후보가 바뀔 수 있음)"). 저녁 잠정 행은 **다음 거래일 날짜**로 저장돼 picker 로 그 날짜를 골라야 보인다(기본은 오늘). 가드 `StrategyFunnel.cycle171.test.tsx` · 문구 가드 `tests/unit/ast/test_cycle364_frontend_evening_wording.py`.
- **병목 강조 + 추이**: ① `funnel-bottleneck-banner` = 직전 단계 대비 **절대 감소 수** 최대 단계(⚠️ 감소'율'로 잡지 않는다 — 막판 소수 종목의 100% 감소가 진짜 병목을 가린다. 순서는 DB `ORDER BY step_no`) ② `funnel-bar-{sid}-{step_no}` 상대 막대 ③ `funnel-recent-trend` = `getRecentFunnel(strategy_id, 14)` 최종 단계 스파크라인 + 연속 0 배지(`target_date` 는 `Date()` 파싱 없이 slice). 로딩/에러/빈 데이터는 그 섹션 안에서만 처리한다. 가드 `StrategyFunnel.bottleneckTrend.test.tsx`.

## Settings

### 비중 슬라이더

- 하한선 = 보유 포지션 매수금액 비율. ⚠️ `min_weight` 는 **퍼센트 정수(0~100)**(`invested / total_asset × 100` 반올림)라 `weight`(비율 0~1)와 **단위가 다르다**(마커 `left: {minW}%`). 라우트 하한 검증은 비율끼리 비교한다
- `position_ratio` = 전략 내 종목당 비중(전략 할당 자금 기준, 순자산 전체 아님) + 예상 매수 금액 헬퍼
- **비중 단위 = 비율 `0.0~1.0`**: 로드는 `Math.round(s.weight * 100)` **단일 경로** — 값 크기·합계로 단위를 추론하는 분기 금지(루트 `CLAUDE.md` 「비중 단위 추론 변환 금지」). 저장은 **비율 송신**(`weights[key] / totalWeight` 4dp + 잔차 `1 − Σ` 를 최대 항목에 흡수해 Σ=1.0)
- **합계 경고 배너** `data-testid="weight-sum-warning"` — 판정 소스 = **서버 저장값 비율 합**(`strategies.reduce(s.weight)`)이지 편집 중 퍼센트 합이 아니다(정상 조작·반올림 오차를 오염으로 오인한다). `|Σ−1| > 0.01` 이면 배너, **초과**면 비중 저장 `disabled` — 오염째 저장하면 재정규화가 `[weight_config_anomaly]` 탐지기를 **영구 침묵**시킨다. Σ<1 은 막지 않는다(운영자 고립 방지)
- **422 한글 노출** (`api/trading.ts::updateStrategyWeights`): `axios.isAxiosError && status===422` 분기가 `detail`(문자열 또는 배열 `[0].msg`)에서 메시지를 뽑고 pydantic 접두사(`Value error, ` / `Assertion failed, `)**만** 지운다(`^[A-Za-z ]+, ` 같은 일반 패턴 금지 — 한글 본문이 잘린다). `!data.success` 가 던진 Error 는 재포장 금지
- ⚠️ overflow 임계는 `serverWeightSum - 1 > 0.01` 형태로만 쓴다 — `1.01` 리터럴은 AST 가드가 단위 추론 부활로 본다. 가드 `_ast_weight_unit_guard.test.ts`(`1.01` 0건 + `Math.round(s.weight)` 0건) / 회귀 `Settings.weightUnits.test.tsx` · `api/__tests__/trading.test.ts`

### `StrategyParamsEditor` — 파라미터 편집기 (카탈로그 기반, 유일한 구현)

`GET /api/strategies/params-schema` 응답만으로 그린다. **화면은 파라미터 키를 하나도 모른다** — 라벨·단위·범위·선택지·위험도를 전부 응답에서 읽는다. 화면이 키를 들면 백엔드가 키를 늘려도 모른다. 가드 `components/__tests__/_ast_param_key_hardcode.test.ts`(키 리터럴 0건).

- **포맷 분기는 키 이름이 아니라 `type`/`unit` 으로** — `_pct` 접미사가 퍼센트·비율 두 규약에 다 쓰여 이름 추론은 단위 추론 휴리스틱의 재현이다.
- **저장은 변경분만** — 연 키 전체를 보내면 한 키의 범위 위반이 전략 전체 저장을 422 로 막는다.
- 배지 5종 = identity(리스크 정체성 상수) · autotune · deprecated · inactive · unbounded. testid = `strategy-params-editor` / `-row-{key}` / `-current-{key}` / `-default-{key}` / `-reset-{key}` / `-diff` / `-warnings` / `-save` / `-market-warning`(KRX 메인 시간 경고, `isKrxMainSession`).
- 스키마는 패널을 **열 때만** fetch(`Settings.tsx` 의 `paramsStrategy` state, null = 닫힘).
- `updateStrategyParams(key, params)` 의 `params` = `Record<string, StrategyParamValue>`(`api/trading.ts` — `number | string | string[] | boolean | null`). bool 키(예: `buy_paused`)는 체크박스.

### `ExchangeBoardRow`

- 전략별 `exchange` 라디오 + `tradable_boards` 체크박스 5개(`pre_nxt` / `krx_open` / `main` / `krx_after` / `post_nxt`, post_nxt 선택 시 amber). 0개 선택 차단. 바뀐 키만 송신.
- **`exchange` 선택지는 KRX·NXT 둘뿐이다** — 09:00~15:30·16:00~20:00 은 `order_engine.py::_route_exchange_by_clock` 이 정하므로 이 값은 그 밖 구간(프리장 08:00~09:00 등)에만 쓰인다. **이미 `SOR` 로 저장된 전략은 값을 지우지 않고** 폐기 값 회색 안내로 보인다(`isRetiredExchangeValue`) — 매매가 안 바뀌는 입력란은 운영자를 속인다.
- **환경 가드**: `useTradingStatus().env` 가 모의(`!== 'real'`)면 NXT 라디오 disabled + 회색 + 저장 시 추가 검증
- 어느 전략이든 `post_nxt` 활성이면 상단 amber 야간 매매 경고 배너

### `CashUsageRatioCard`

비중 슬라이더 하단. range **0~100**, step 5 + `data-testid="cash-usage-ratio-percent"`. 🔴 **하한 0 = 백엔드 수용 범위(`_CASH_USAGE_RATIO_MIN = 0.0`)** — 화면 하한이 더 높으면 자동 조정·curl 이 저장한 값(예: 0.25)을 UI 로 되돌릴 수 없다. 0% 면 `data-testid="cash-usage-ratio-zero-warning"` 인라인 경고(신규 매수 전면 중단). GET `/api/strategies/system/cash-usage-ratio` 로 로드, 저장 버튼에서만 PUT(debounce 없음), 응답 ratio(서버 5% 보정)로 동기화. 안내 "다음 영업일부터 반영"(text-amber-700). queryKey `['cashUsageRatio']`.

### `KisQuoteAccountsCard`

`IntegrationToggleCard` 직하. 보조 KIS 시세 계좌 등록/제거/활성화:
- 표 컬럼: label / 환경 배지(`real`=red / `vts`=emerald) / app_key 마스킹 / app_secret_masked(`****1234`) / 등록일(KST) / `quote-account-toggle-{id}` active 토글 / `quote-account-delete-{id}` 삭제
- 빈 목록 `quote-accounts-empty` "등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 41 × (1 + N) 으로 확대"
- 등록 폼: `quote-account-input-label` / `quote-account-input-kis-env-real|vts` 라디오 / `quote-account-input-app-key` / `quote-account-input-app-secret`(**`type=password`** + `autocomplete=new-password`). 빈값·label 형식 `^[A-Za-z0-9\-]+$` 위반 → `quote-account-form-error` + POST 미발사
- `quote-account-submit` → `ConfirmModal` 이중 확인(등록·active 토글·삭제 모두)
- **app_secret 평문 잔존 차단**: 등록 성공 시 `setForm` 으로 secret state 즉시 클리어. UI 는 `app_secret_masked` 만 참조
- 에러: `axios.isAxiosError` status (`409: label 중복` / `422: 검증 실패` / 그 외)
- API `frontend/src/api/kis-quote-accounts.ts` + `types/kis-quote-accounts.ts` — 백엔드 `/api/integrations/quote-accounts/*`. queryKey `['kis-quote-accounts']`, staleTime 30s

### `IntegrationToggleCard`

`CashUsageRatioCard` 직하. 4 토글 + 매수 가드 영역.

**토글 4종** (`ConfirmModal` 이중 확인):
- `data-testid="toggle-dkstock-regime"`: 매크로 레짐 활성(출처 = 자체 `macro` 컨테이너, testid·키는 DB 행과 짝이라 유지). 활성화 후 3s `data-testid="fetch-progress-dkstock-regime"` + marketRegime invalidate
- `data-testid="toggle-kis-mcp"`: 외부 백테스트 서버(자문 시점만 사용)
- `data-testid="toggle-auto-regime-adjust"`: 매크로 레짐 → cash_usage_ratio 자동 갱신
- **`data-testid="toggle-auto-apply"`**: AI 자문 자동 적용, 기본 OFF. ON 이면 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터 자동 적용. DB-only(`auto_apply_enabled`). API `getAutoApply/setAutoApply` — `/api/integrations/auto-apply`
- `data-testid="source-badge-{key}"`: source='db' 파란 `DB` / 'env' 회색 `env`(fallback 가시화) · 에러 `data-testid="toggle-error-{key}"` 빨간 박스 + "잠시 후 재시도하세요"

**`BuyBlockSection`** — 🔴 **표시·관찰 전용이다.** 레짐은 매수를 차단·축소하지 않고 `buy_block_mode` 는 표시용이다(루트 「외부 통합」 절). "매수 차단 중" 문구 · 모드 설명(`MODE_DESCRIPTIONS`) · 확인창 문구(`MODE_CONFIRM_MESSAGES` — HARD "모든 전략의 매수가 차단" · SOFT "수량이 절반으로 축소")는 **실제 동작이 아니다**.
- `buy-block-mode-select`(OFF/WARN/SOFT/HARD, 변경 시 `ConfirmModal`) · 임계 슬라이더 `buy-block-vix-slider`(10~50, 기본 25) / `buy-block-fg-high-slider`(50~100, 기본 85) / `buy-block-fg-low-slider`(0~50, 기본 15) · `buy-block-defensive-toggle`(regime=defensive, 기본 ON)
- `buy-block-thresholds-save` = 슬라이더+체크박스 한 번에 PUT(ConfirmModal 없이) · `buy-block-reasons`(4건까지 list-disc + amber)
- **무력 배너 `buy-block-guard-inert`**: `data.guard_inert === true` 면 mode 행 직후·reasons 위 red 배너(`bg-red-100 text-red-800 border-red-300`) — 매크로 데이터 미유입으로 가드가 무력한 상태(false sense of protection)를 드러낸다. `BuyBlockState` 에 `data_available`/`guard_inert`
- SOFT `buy-block-soft-multiplier` 안내 / GET 500 `buy-block-error` graceful. API `getBuyBlock / setBuyBlock` — `/api/integrations/buy-block` GET/PUT, queryKey `['integration', 'buy-block']`, staleTime 30s

### `PriceFilterCard`

**WebSocket 구독 대상 필터.** `BuyBlockSection` 직하. 매도/익일청산/손절 영향 0.

- **6 testid**: `price-filter-card` / `price-filter-min-slider`(0~20,000원, step 1,000) / `price-filter-max-slider`(0~2,000,000원, step 50,000) / `price-filter-save-button` / `price-filter-save-toast` / `price-filter-validation-error`
- 단일 필터(`min=0 or max=0` 비활성, 디폴트 0/0). 모드 select 는 없다 — `PriceFilterMode` 타입·`mode` 필드를 되살리지 않는다. 권장값 툴팁 저 5,000원 / 고 1,000,000원
- **즉시 반영**: 저장 → `updatePriceFilter()` PUT → `scanner.invalidate_price_filter_cache_scanner()` 즉시 호출(60s 캐시 중에도). **자동 unsubscribe 0 발화**(다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단)
- **클라이언트 검증**: 음수 / `min_price > max_price`(둘 다 >0) → `price-filter-validation-error` + PUT 미발사
- API `getPriceFilter / updatePriceFilter` — `/api/system/price-filter` GET/PUT, `ApiResponse<PriceFilter>` → `data.data`. queryKey `['priceFilter']`. PUT extra key → 422(`ConfigDict(extra="forbid")`)
- 안내 배너: "**WebSocket 구독 대상 필터** — 임계 외 종목은 시세 구독 자체 차단. **보유/익일청산 종목은 절대 제외 안 됨**"
- 가드 `PriceFilterCard.test.tsx`(mode select 미존재 포함)

### `TradeAmountFilterCard`

**거래대금 동행 필터.** `PriceFilterCard` 옆("WebSocket 구독 대상 필터" 영역).

- **4 testid**: `trade-amount-filter-card` / `trade-amount-filter-min-slider`(0~100억원 = 0~10_000_000_000, step 1억원 = 100_000_000) / `trade-amount-filter-save-button` / `trade-amount-filter-save-toast`
- **권장값 마커 3 버튼** "1억"(100_000_000) / "5억"(500_000_000) / "10억"(1_000_000_000) — 슬라이더 value 직접 갱신
- **즉시 반영**: 저장 → PUT → `scanner.invalidate_trade_amount_filter_cache_scanner()` 즉시 호출. 자동 unsubscribe 0 발화
- API `getTradeAmountFilter / updateTradeAmountFilter`(`frontend/src/api/trade-amount-filter.ts` + `frontend/src/types/trade-amount-filter.ts`) — `/api/system/trade-amount-filter` GET/PUT, `ApiResponse<TradeAmountFilter>`. queryKey `['tradeAmountFilter']`. extra key → 422 / 음수 → 400
- **안내 배너 3문구 (명시 의무)**: "**거래대금 동행 필터** — 임계 미만 종목은 WebSocket 구독 자체 차단" / "보유/익일청산 종목은 절대 제외 안 됨" / "**09:00 직후 거래대금 미반영 종목은 graceful 통과**"
- MSW `GET /api/system/trade-amount-filter` → `{ min_amount: 0 }` + `PUT` body 반영 · 가드 `TradeAmountFilterCard.test.tsx`(안내 배너 문구 포함)

## StockMaster (`/stock-master`)

### (1) 진단 카드 8

| 카드 | 출처 | 라벨 |
|------|------|------|
| count_all | stock_master | 전체 종목 |
| bfdy_clpr_present | stock_master.raw.bfdy_clpr | 전일종가 보유 |
| nxt_tradable_count | stock_master.nxt_tradable | NXT 거래가능 |
| eager_refresh_today | emit count | 오늘 자동 갱신 |
| with_hts_avls | stock_master.raw.hts_avls | 시가총액 보유 |
| with_acml_tr_pbmn | stock_master.raw.acml_tr_pbmn | 거래대금 보유 |
| total_daily_rows | stock_master_daily.count_all | 일봉 적재 누적 |
| last_daily_load_at | stock_master_daily.max_bas_dd | 마지막 일봉 적재일 (KST) |

안내 배너 `stock-master-info-banner` = 종목 기본정보 적재 현황 + "매일 20:00 전 종목 일괄 적재 + 보유·매수 후보 5분 주기 자동 갱신" 요지.

### (2) 종목목록 — 4 필터 + 4 시세 컬럼

- 4 컨트롤: 시장 select(전체/KOSPI/KOSDAQ) · 시총 min(억원, placeholder "0 = 전체") · 거래대금 min(억원) · 종목명 부분 검색(한글 IME composition 가드) + 초기화 버튼. 400ms 디바운스(`useEffect` setTimeout) · URL `useSearchParams` 동기화(새로고침·공유 시 유지) · 필터 변경 시 offset=0
- 컬럼(종목명·시장 다음, NXT/정지/관리 *전*): 현재가(`raw.stck_prpr`) / 전일대비(`raw.prdy_vrss`, 부호 색상) / 시가총액(`raw.hts_avls` — **이미 억원**, 1만억 이상 조원) / 거래대금(`raw.acml_tr_pbmn` 원 → 억원). 헬퍼 `formatPrice` / `formatMarketCap` / `formatTradeAmount`, 없음/0/null → "—"
- `fetchList(params: StockMasterFilterParams): Promise<StockMasterListResponse>` · `StockMasterListResponse {items, total, limit, offset}` · `StockMasterFilterParams {limit, offset, market?, min_market_cap?, min_trade_amount?, name_substr?}`. 페이지네이션은 `total` 기준

### (3) 새로고침 4 버튼 + `RefreshProgressBanner`

- 버튼 4: "지금 새로고침"(blue) / "기본정보 새로고침"(`stock-master-refresh-basics-button`, emerald) / "일봉 새로고침"(`stock-master-refresh-daily-button`, amber) / "마스터 새로고침"(`stock-master-refresh-master-button`, deep purple) — POST `/api/stock-master/{...}/refresh`, **fire-and-forget**, `retry: false`(중복 trigger 방지)
- `onSuccess`: "{작업} 새로고침 시작 — 진행 상황은 상단 배너 참고" + `invalidateQueries(['refresh-progress'])`. `onError`: 409 → "{작업} 이미 진행 중 — 상단 배너 참고" / 그 외 → "KIS API 일시 결함 — 잠시 후 재시도"
- `RefreshProgressBanner.tsx` — `useQuery({queryKey: ['refresh-progress'], queryFn: fetchRefreshProgress, retry: 1, refetchInterval: 동적})`(running 5초 / idle 60초). `TASK_ORDER = ['universe', 'basics', 'daily', 'master']`, `TASK_LABELS['master'] = '종목마스터 일일 갱신'`. running 이거나 'completed/failed' 직후 3초 이내만 표시(자동 fadeout), fadeout 때 `invalidateQueries(['stock-master-stats'])` + `['stock-master-list'])`
- testid `refresh-progress-banner` / `refresh-progress-{row,status,bar,counter,error}-{taskKey}` · 타입 `RefreshTaskKey = 'universe' | 'basics' | 'daily' | 'master'` · `RefreshStatus = 'idle' | 'running' | 'completed' | 'failed'` · `RefreshProgress`(10 키) + `AllRefreshProgress` + `RefreshStartedResponse { status: 'started', task_key }`

### (4) detail 모달 — 상세 / 일봉 2 탭

- 상세 탭: `FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키. `master_raw` ~30 키(진입 차단 7 · 시총 · 재무 5 · 지수편입 6 · 시장 영역 4 · 기타 7) + 시세 6 키(`hts_avls`·`acml_tr_pbmn`·`bfdy_clpr`·`lstn_stcn`·`acml_vol`·`prdy_vrss`)
- 🔴 `DetailModal` 의 `useQuery` 는 **`placeholderData: initialData`** — `initialData` 면 fresh 판정으로 `fetchDetail` 재호출이 막혀 신규 매핑 키가 빠진다
- 일봉 탭: `useQuery({queryKey: ['stock-master-daily', ticker], queryFn: () => fetchDaily(ticker, 30), enabled: !!ticker, retry: 1, refetchInterval: 60_000})` — 마지막 30 영업일 `bas_dd / open_price / high_price / low_price / close_price / volume / change_rate`
- 🔴 **방어 변환 3 헬퍼**(`StockMaster.tsx`) — `toSafeNumber(unknown): number | null`(숫자·숫자형 문자열 → 유한 number, `null`/`undefined`/**빈 문자열**/비숫자/`NaN`/무한대 → `null` — 빈 문자열 가드가 `Number("")===0` 오판을 막는다) · `formatSafeCount`(OHLCV, 실패 `'—'`) · `formatSafeChangeRate`(색도 변환 **후** 값 기준, `text-red-600`/`text-blue-600`/`text-gray-500`). **렌더는 이 세 헬퍼의 반환값에만 건다**
- **404 vs 500** — `axios.isAxiosError(error) && error.response?.status === 404`(`DetailModal.is404` 선례). 404 = "적재 대상 아님"(`stock-master-daily-notice`, 회색) / 그 외 = `stock-master-daily-error`(빨강). **일봉은 전 종목 적재가 아니다** — 정상 미적재를 오류로 보이지 않는다
- `types/stock-master.ts::StockMasterDailyRow` — `change_rate: number | string`, `prtt_rate?: number | string`(`NUMERIC(8,4)` 계열이라 문자열 가능). migration 033 컬럼 **14 필드 전수**를 명시한다(렌더는 8개 — 숨기면 목이 실제와 또 갈라진다). `bas_dd` 는 `DATE` 라 `YYYY-MM-DD`
- ⚠️ `StockMaster` 전체엔 아직 `ErrorBoundary` 가 없다(일봉 탭 렌더만 방어) — 후속 B-4(`_workspace/00_URGENT_WORKLIST.md`)

### (5) 변경이력 탭

- `StockMasterHistoryItem`: `{ticker: string, seq: 0 | 1, change_type: 'INSERT' | 'UPDATE' | 'DELETE', raw: Record<string, unknown> | null, changed_at: string}`. `id`/`before_raw`/`after_raw`/`'TTL_REFRESH'` 는 스키마에 없다 — 되살리지 않는다
- 4 컬럼: 스냅샷(`seq===0 ? '최신본' : '직전본'`, seq0=indigo / seq1=gray) / 변경일시(KST) / 변경유형(`CHANGE_TYPE_COLORS`) / raw(`<CollapsiblePre label="raw" data={item.raw} />`, null → "—")
- **seq ASC 정렬** `historyItems.sort((a, b) => a.seq - b.seq)` — UPDATE 의 seq0/seq1 `changed_at` 이 같아(`now()`) DESC 만으론 비결정이다. row `key` = `${ticker}-${seq}`

### (6) 신규 데이터 추가 시 UI 동기화 절차 (영구 가드)

`stock_master` 컬럼 / `raw` JSONB 키 / `stock_master_daily` 컬럼 추가 시 **반드시** 동기화한다. 전략이 종목마스터 데이터를 참고하는 시점부터, 새로 수집한 데이터는 UI 에 노출할 의무가 있다.

1. `frontend/src/types/stock-master.ts` interface 갱신
2. `frontend/src/api/stock-master.ts` 호출 영역 갱신
3. `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 추가
4. `CATEGORY_KEYS` 적정 카테고리 배치
5. 핵심 키면 `HIGHLIGHT_KEYS` 추가
6. 진단 영역이면 `get_stats()`(`GET /api/stock-master/stats`) 응답에 진단 카운트 + 카드 1개 추가
7. `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합
8. 회귀 가드 추가 (`StockMaster.test.tsx`)

⚠️ 이 8단계는 "신규 컬럼·키를 UI가 놓치지 않는다" 만 보장한다. **목이 실제 응답 타입을 흉내 내는지는 검사하지 않는다** — 「테스트 규약」 5를 함께 지킨다.

### (7) 회귀 가드

`StockMaster.test.tsx` · `StockMaster.dailyTab.cycle266.test.tsx`(방어 변환 3 헬퍼 + 404/500) · `test_cycle266_daily_route_serialization.py`(백엔드, **직렬화된 JSON 본문**의 타입) · `test_cycle266_mock_string_change_rate.py`(목 5행 문자열·숫자 혼합 + `YYYY-MM-DD` 정적 대조) · `e2e/stock-master.spec.ts::G-E2E-9`(실브라우저 일봉 탭 + 문자열 등락률 `+1.20%` + `NaN`/`—` 부재).

## History (`/history`)

두 탭(행 더블클릭 → 종목 차트, 「종목 차트 모달」 절):
- 주문체결내역: `TradeHistoryGrid`(raw 행). SELL 행만 `순손익`(`net_profit_loss`, 정수 원. `cost_status` 가 `estimated`/`mixed` 면 「추정」 배지) 칸을 보이고 BUY 행과 값이 없는 행은 `-`. 기존 `매매손익`(세전) 칸은 그대로.
- 매매손익: `TradePnLGrid`(`/api/history/pnl` — 매수·매도 페어, closed/open 사이클). 12 컬럼 + 전략 뱃지, 그 뒤로 실비용 6컬럼(수수료·세금·순손익·순손익율·비용률·슬리피지, cycle411) + 전략·AI 자문. open 행은 매도 컬럼 "—" + "(미실현)", emerald-50 배경, 시세 미수신 "(미실현 시세 대기)". 전략 select 7종(kojiro `고지로 대순환` 포함). 상단 실현손익 요약 바 `pnl-summary` — `data.summary`(슬라이스 전 전체 closed 페어 집계)의 실현 합계(`pnl-summary-realized`, 이익 red/손실 blue)·손익율·승/패/보합·승률·전략 필터 라벨 + (summary 에 net 칸이 있으면) 순손익 합(`pnl-summary-net`)·비용 합(`pnl-summary-cost`)·슬리피지 덮인 건수(`pnl-summary-slippage`, `N건`). summary 부재 시 0. summary 의 비용 칸이 `null`(비용 조회 실패 = 「모름」)이면 `pnl-summary-net`·`pnl-summary-cost`·`pnl-summary-slippage` 는 `—` 다(「0원」·「0건」 금지). 원 단위 칸(수수료·세금·순손익·슬리피지·`pnl-summary-cost`)은 정수 원(반올림), 비용률은 소수 1자리 `NN.Nbp`. 행 단위 `cost_status="estimated"/"mixed"` 는 「추정」, `allocated=true` 는 「배분」 배지(`cost-badge-<rowIndex>`) — 정산을 그 페어 혼자 받은 행은 둘 다 없다. `allocated` 는 그 페어 체결이 받은 정산 행이 **페어 밖** 체결에도 나뉘었을 때만 true 다(같은 날 사고 판 단일 페어는 false — 판정 = `src/engine/CLAUDE.md` 의 `cost_overlay.py` 항목). 새 칸이 없는(구 서버) 페어나 `null` 칸은 `—`(NaN·undefined 금지).

### AI 매수평가 점수 배지 + 상세 팝업

두 그리드 각 행 맨 오른쪽 "AI 자문" 열, **버튼 왼쪽에 점수 배지**(팝업 없이 목록에서 읽는다).

- **점수 배지** (`components/LlmScoreBadge.tsx`) — 순수 함수 `resolveLlmScoreTone(summary)` → `{tone, text}`, 배지가 `data-tone` 으로 노출. 배치로 받은 `summary` 만 그린다(**네트워크 호출 추가 0**).
  - 🔴 **판정의 정본은 서버가 기록한 `would_block` 이다. 화면이 `score >= min_score` 를 다시 계산하지 않는다** — 나중에 바뀐 `min_score` 로 재판정하면 **과거를 거짓으로** 말한다. `would_block` 이 `null`/부재인 옛 기록만 점수 비교로 폴백한다.
  - 🔴 **세 결측 상태를 접지 않는다** — 기록 없음 `·`(`tone='none'`) / 평가 실패 `–`(`tone='failed'`, `result==='failed'` 또는 `score==null`) / 점수 있음(`pass`|`block`) — 접으면 migration 043 이 실패 행을 남기는 이유가 사라진다. 🔴 **0점을 결측으로 접지 않는다**(`if (!score)` 금지 — 최악의 평가가 "기록 없음"이 된다).
  - `title` 에 점수와 기준을 **둘 다** 담는다. `matchedCount > 1` 이면 `+n` 과 "첫 매수 기준" 을 밝힌다.
- **파일 4** = `components/LlmScoreBadge.tsx` · `types/llm-evaluation.ts`(`LlmEvaluationSummary` 10키 → `LlmEvaluation` 이 extends 해 상세 53키 · `LlmEvaluationSummaryMap`) · `api/llm-evaluations.ts`(배치 `getLlmEvaluationSummaries(orderNos, tradeDate?)` · 단건 `getLlmEvaluation(orderNo, tradeDate?)` · 키 헬퍼 `llmEvalKey`·`findLlmSummary`·`llmSummaryDatesFor`. **try/catch 금지** — axios 오류가 React Query 로 가야 404(회색 안내)와 500·네트워크(빨강)가 갈린다) · `components/LlmEvaluationModal.tsx`(신규 의존성 0 · `<pre>` 원문 · `dangerouslySetInnerHTML` 금지).
- **버튼 활성 판정은 배치 1요청**(행마다 조회 금지). 요약 맵 키 = **`"<trade_date>|<order_no>"` 복합 키**(라우트 `summary_key()` 규약), 조회 = `findLlmSummary(summaries, tradeDate, orderNo)`. 키가 있으면 활성, 없으면 비활성(회색) + 툴팁 — 사유는 `llmSummaryDatesFor(summaries, orderNo)` 가 가른다("평가 기록 없음" vs "다른 날짜(…)의 평가 기록"). 기록 없는 조합은 응답에 **키가 없다**(`null` 아님).
- 체결 그리드(`TradeHistoryGrid`)는 **BUY 행 `order_no`**, 손익 그리드(`TradePnLGrid`)는 **`buy_order_nos`** 기준(2건 이상이면 `AI 자문 (n)`, 팝업이 주문별 n개를 나란히). `pair_key`(= `strategy:ticker:첫 매수 order_no`)가 버튼 testid, `null` 이면 비활성.
- ⚠️ **KIS 주문번호(ODNO)는 하루 단위로만 유일하다** — 활성 근거는 **그 행의 매수일로 조회한 키**뿐, 상세도 반드시 날짜와 함께 묻는다(빼면 같은 번호의 **다른 거래 평가**가 뜬다 — 가드 F25b).
- 팝업 = 점수/임계/차단여부(`would_block`) · 사유(rationale) · 핵심 위험 · 무효화 조건 · 지표 요약 · 주문 스냅샷(주문가·수량·목표가·보드) · 모델/토큰/비용/지연 · 원문 입력 payload(접기). **`result==='failed'` 는 정상 기록**이라 실패 사유를 크게 보인다(`llm-eval-failed` — "평가 안 함" ≠ "평가 실패").
- 계좌번호는 **마스킹 값만**(`account_no_masked`, 앞 4자리 + `****`, 타입에 원문 키 없음 — 리포터 키로도 읽힌다). 숫자는 **전부** `toSafeNumber`, 시각은 **전부** `timeZone:'Asia/Seoul'` 명시.
- 목 3곳 모두 배치 응답을 **복합 키**로 만든다(단독 키면 전부 비활성인데 초록). 가드 `src/components/__tests__/llmEvalKey.cycle276.test.ts`(키 형식·날짜별 구분·두 그리드의 요약 맵 직접 인덱싱 0건).

## 종목 차트 모달 — 행 더블클릭 (cycle387)

잔고(`BalanceTable`) · 주문체결내역(`TradeHistoryGrid`) · 매매손익(`TradePnLGrid`) 행 **더블클릭** → 그 종목의 최근 5년 캔들(일봉/주봉/월봉) 모달. 백엔드 = `GET /api/stock-chart/candles`(`src/routes/CLAUDE.md`).

- **여는 규칙** — 공용 훅 `components/useStockChartOpener.tsx`, 행 `onDoubleClick={(e) => openChart(e, ticker, name)}` + `title="더블클릭 — 종목 차트"`. 행 testid = `balance-row-{ticker}` · `trade-row-{index}` · `pnl-row-{index}`.
  - 🔴 버튼·링크·입력·라벨(`button, a, input, select, textarea, label`)과 그 자손 위 더블클릭은 **무시한다**(`utils/stockChart.ts::isInteractiveTarget`) — 「매도」·「AI 자문」 두 번 누름이 차트까지 띄우면 안 된다
  - 더블클릭이 남긴 텍스트 선택을 지운다 · 6자리 숫자 코드가 아니면(`isChartableTicker`) 모달만 열고 `stock-chart-unsupported`, **요청은 보내지 않는다**
- **분리 청크** — `components/LazyStockChartModal.tsx` = `React.lazy(() => import('./StockChartModal'))`(`klinecharts` 를 그리드 첫 로딩에서 뺀다. 훅과 다른 파일인 이유 = Fast Refresh 가드 `react-refresh/only-export-components`). 폴백 `stock-chart-chunk-loading`. 바깥 `ChunkErrorBoundary` — 재배포 뒤 옛 탭의 청크 import 가 실패해도 앱이 살고 `stock-chart-chunk-error`(새로고침 안내) + `stock-chart-chunk-error-close`
- **라이브러리** — `klinecharts` `10.0.3`(`^` 없이 고정, 타입 동봉). 가져오는 것은 `init` · `dispose` · `registerLocale` · 타입 `Chart` **뿐**이다. 기간 `chart.setPeriod({ type, span: 1 })`(`PERIOD_TO_KLINE` D→`day` · W→`week` · M→`month`) · 데이터 `chart.setDataLoader({ getBars })` · 로케일 `ko-KR` 은 모듈 최상위에서 1회 등록. 캔들·거래량·MACD 막대 색 = `utils/pnlColor.ts` `PROFIT_HEX`·`LOSS_HEX`·`NEUTRAL_HEX`(`init` 의 `styles.candle.bar` · `styles.indicator.bars`, 새 hex 0). 닫히면 `dispose`
- **지표 배치 (cycle388)** — EMA 는 가격 축에 겹쳐야 읽혀 캔들 패널에, 아래 패널엔 가격 축이 아닌 지표만 둔다.
  - 캔들 = `createIndicator({ name: 'EMA', paneId: CANDLE_PANE_ID, calcParams: [5, 20, 60, 120] }, true)` — `CANDLE_PANE_ID = 'candle_pane'`(= `PaneIdConstants.CANDLE`), `true`(`isStack`)는 기존 것을 지우지 않고 겹친다
  - 아래 패널은 위에서부터 거래량 · RSI · MACD 이고 `createIndicator` 를 이 순서로 부른다(가드 C388-2c) — `VOL_PANE = { id: 'stock_chart_vol', height: 64 }` · `RSI_PANE = { id: 'stock_chart_rsi', height: 80 }` · `MACD_PANE = { id: 'stock_chart_macd', height: 90 }`, 높이는 `chart.setPaneOptions({ id, height })`(안 주면 셋 다 100px 라 캔들이 눌린다). 캔들 패널 높이는 주지 않는다. 차트 자리 = `h-[72vh] min-h-[460px]`
  - 거래량 `{ name: 'VOL', calcParams: [] }` — 막대만(기본 `calcParams` 5·10·20 은 이동평균선 셋이 EMA 처럼 보인다) · RSI `{ name: 'RSI', calcParams: [14], precision: 2, figures: [{ key: 'rsi1', title: 'RSI14: ', type: 'line' }] }`(기본 툴팁 제목이 순번 `RSI1: `) · MACD `{ name: 'MACD', calcParams: [12, 26, 9], precision: 2 }`(`precision: 2` 가 없으면 4자리)
  - 🔴 이동평균 계열(`EMA`·`MA`·`SMA`·`BOLL`)은 캔들 패널에만 둔다
- **조회** — `api/stock-chart.ts::getStockChart(ticker, period, years = 5)`. 본문 `success:false` → `Error(message)`. axios 오류(422·네트워크)는 **잡지 않고** 흘려 모달이 422 `detail` 을 보인다. `STOCK_CHART_TIMEOUT_MS = 60_000`(= nginx `location /api/` 기본 `proxy_read_timeout`, 120초는 `/api/macro/` 전용. 백엔드 `_QUEUE_WAIT_SECS`+`_FETCH_TIME_BUDGET_SECS` 를 덮는 값 — `src/api/CLAUDE.md` 「period_chart.py」). `useQuery` 키 `['stockChart', ticker, period, 5]`, `retry: 1`, `staleTime` = 부분 결과(`complete=false`) 1분 · 그 밖 10분(서버 캐시와 같은 값 — 「1분 뒤 다시 열면 다시 받습니다」 안내의 전제)
- **날짜** — 봉 날짜 `YYYY-MM-DD` → `kstDateToEpochMs` → 축·툴팁 `formatKstDateFromEpochMs`, 월봉 x축만 `formatKstYearMonthFromEpochMs`. `init({ timezone: KST_TIME_ZONE })`. `StockChartModal.tsx`·`utils/stockChart.ts` 는 K4 위임 대상
- **봉 변환** `toKLineData(bars)` — 숫자는 방어 변환(숫자 문자열 허용), 날짜·OHLC·거래량·거래대금 중 하나라도 실패한 봉은 버린다. 항상 오름차순, `turnover` = `amount`
- **상태는 전부 따로 보인다 — 값을 고치거나 숨기지 않는다.** `stock-chart-loading` · `stock-chart-error`(+ `stock-chart-retry`) · `stock-chart-empty` · 부분 `stock-chart-partial`(`complete=false`) · 잠정 봉 `stock-chart-provisional`(`last_bar_provisional=true` — 일봉은 날짜, 주·월봉은 「이번 주」/「이번 달」) · `stock-chart-unsupported`. 메타 `stock-chart-meta` = 요청 구간(`start_date ~ end_date`) · 봉 수 · 수정주가 · KRX
- **셸** — `LlmEvaluationModal` 관용구. 루트 `stock-chart-modal`, 패널 `role="dialog" aria-modal aria-labelledby`, × · ESC · 바깥 클릭으로 닫고 연 요소로 포커스 복귀. 기간 버튼 `stock-chart-period-{D|W|M}`(`aria-pressed`)
- **목** — MSW `test/handlers.ts` 와 e2e `fixtures/api-mocks.ts`(`**/api/stock-chart/candles*`, 경로 가드 + resourceType 가드)가 같은 리터럴(`test/fixtures/stockChart.fixture.ts` · `e2e/fixtures/stock-chart.fixture.ts`)을 기간별로 주고, 6자리 숫자가 아니면 422. 단위 테스트는 jsdom 에 canvas 가 없어 `vi.mock('klinecharts', …)` 로 `test/fakeKlinecharts.ts`(호출 기록용)를 쓴다 — 실제 라이브러리는 e2e 만
- **실제 라이브러리의 지표 거부는 e2e F32 가 본다** — klinecharts 는 거부를 개발 모드(`process.env.NODE_ENV === 'development'`)의 `console.log` 로만 남기므로 F32 는 콘솔 타입이 아니라 문구 `/klinecharts (warning|error)/i` 로 모아 `[]` 를 단언한다(e2e 는 `npm run dev`)
- 회귀 = `components/__tests__/StockChartModal.cycle387.test.tsx` · `StockChartModal.cycle388.test.tsx`(지표 배치) · `stockChartOpen.cycle387.test.tsx`(세 그리드 배선) · `LazyStockChartModal.cycle387.test.tsx`(청크 로딩 실패) · `utils/__tests__/stockChart.cycle387.test.ts` · `utils/__tests__/kst.test.ts`(K6~K9) · `e2e/history.spec.ts`(F32·F33)

## Logs (`/logs`) — 통합 메뉴

탭 컨테이너 `pages/Logs.tsx` + URL 쿼리 `?tab=system|daily-report`(기본 `system`, 모르는 값 fallback). 탭 `data-testid="logs-tab-{key}"` + `role="tab"` + `aria-selected`. 로그 뷰어는 여기에만 있다(Dashboard 에는 없다).

### 시스템 로그 (`SystemLogsTab.tsx`)

`from_date / to_date` date input(기본 KST 오늘, `Intl.DateTimeFormat('en-CA', timeZone: 'Asia/Seoul')`) + 적용 + 레벨 토글(전체/INFO/WARNING/ERROR/CRITICAL) + 페이징(1-base, size 50). 자동 새로고침 3s 는 **오늘 + page=1 + 검색 모드 아닐 때**만. `from_date>to_date` → `data-testid="system-logs-date-error"`. API `fetchLogs(filter)`.

- **검색 박스**(필터 바 *위*): `system-logs-search-input` + Enter + `system-logs-search-button` + 검색 모드 중 `system-logs-search-clear`. 검색 모드 동안 페이징·자동 새로고침 비활성(`/api/logs/search` 단일 limit 200). `searchLogs({q, level, start, end, limit})` — 입력된 level/from_date/to_date 를 함께 보낸다. 0건 → "검색 결과가 없습니다."(페이징 "로그가 없습니다." 와 분리). `has_more=true` → `system-logs-search-has-more` amber 배너

### 일일 로그 분석 (`DailyReportTab.tsx`)

좌측 영업일 리스트(최근 30일) / 우측 summary + findings 카드(severity + category 칩) + 원본 메트릭 접기. "지금 분석 실행" → `POST /api/log-reports/run`(영업일당 1건 UNIQUE).

- **`ext_*` 6컬럼** `daily_log_reports.ext_provider/ext_model/ext_summary/ext_findings/ext_report_md/ext_created_at`(전부 NULL 허용) — 20:20 KST 클라우드 루틴이 `POST /api/log-reports/{date}/external` 로 채우고, `GET /api/log-reports*`(SELECT *) 응답을 `LogReportItem` 6개 선택 필드가 1:1 매핑한다.
- **표시 규칙**: `ext_summary` 또는 비어 있지 않은 `ext_findings` 가 있을 때만 `data-testid="ext-analysis-card"` 를 OpenAI 총평 **위에** — 헤더 "{target_date} Claude 분석" + "생성 {ext_created_at} · {ext_provider} · {ext_model}"(null 조각만 생략) + `ext_summary`(`whitespace-pre-line`, `data-testid="ext-summary"`) + "개선 항목 (N건)"(`FindingCard` 재사용, severity 정렬, key 접두 `ext-`) + `ext_report_md` 가 있으면 접이식 "상세 리포트"(`data-testid="ext-report-md-toggle"`) 안 `<pre className="whitespace-pre-wrap text-xs …">` 원문.
- 🔴 **마크다운 렌더 라이브러리 추가 금지**(의존성 0) — `<pre>` 원문은 감사에 유리하고 XSS 표면(`dangerouslySetInnerHTML`)을 열지 않는다.
- **파리티 계약**: ext 6필드가 전부 없으면 `hasExtAnalysis()` 가 `false` 라 블록이 트리에 없다(기존 OpenAI 총평/findings/원본 메트릭 DOM byte 동일). 좌측 목록은 `ext_summary` 있는 행만 배지 "Claude"(`data-testid="ext-badge-{id}"`).
- **항목 내부 정규화**: `ExternalReportIn.findings` 는 항목 내부를 검증하지 않는 `list[dict]` 라, `sortedExtFindings` 에서 `normalizeExtFinding`(같은 파일)이 severity ∉ `{high,medium,low}` → `medium`, category ∉ 9종 → `etc`, title/detail/suggestion 비문자열 → `JSON.stringify`, title·detail 빈 문자열 → 항목 **드롭**한다(없으면 "Objects are not valid as a React child" 로 탭이 빈다).
- **레거시 `findings` 는 정규화하지 않는다**(`log_analysis_engine._validate_report` 가 검증). 대신 `ReportCard` 를 `ReportCardBoundary`(같은 파일, class error boundary, `key={report.id}` 로 전환 시 리셋)로 감싸 예외가 나도 `data-testid="report-card-error"` 카드 하나만 대체된다.
- **휴장일 배지 (cycle366)**: `report.metrics?.report_accuracy?.market_closed === true` 일 때만 총평 헤더에 회색 배지(`data-testid="report-holiday-badge"`, "휴장일" + 툴팁 "거래·로그 0건은 결함이 아니라 정상"). `report_accuracy` 없는 옛 행·`trading_day: null`("모름")·`market_closed: false` 는 안 그린다. `LogReportMetrics.report_accuracy`(`types/log_reports.ts::LogReportAccuracy`)는 옵셔널.
- 회귀 = `components/__tests__/DailyReportTab.ext.test.tsx`(파리티·정규화·error boundary 포함) + `DailyReportTab.holiday.test.tsx`
- **「원본 메트릭 → 거래 통계」 실현손익 라벨 = 「실현손익(세전)」 (cycle411)** — 이 숫자는 그날 저장된 스냅샷(`metrics.trades.realized_pnl`)이라 비용을 빼지 않고 그대로 보이고, 라벨만 세전임을 밝힌다(다른 실적 화면의 net 기본과 다르다).

## Recommendations (`/recommendations`)

**카드 DOM 순서**: 자산 배정 → BacktestComparison → 분석 통계 → 추천 근거 → 로직 자문 → 파라미터.

- **자산 배정 카드**(`data-testid="weight-card-{id}"`, `recommended_weight != null` 시, **최상단**): 현재→추천 weight + 변경량(%p, 이익색/손실색) + `weight-apply-checkbox-{id}`(체크 시 `applyMutation` body `apply_weight: true`). 적용 후 `applied_weight` + amber "다음 영업일부터 반영"
- **`weight_reasoning`**(`data-testid="weight-reasoning-{id}"`, weight-card 안 `bg-amber-50 border-amber-200 max-h-32 overflow-y-auto whitespace-pre-wrap`): `rec.weight_reasoning` truthy 시만(1000자 이내, 백엔드 truncate). 통합 `reasoning` 과 분리
- **로직/파라미터 자문 카드**(`data-testid="code-review-card-{id}"`, `code_review_notes != null` 시): 자유 텍스트(whitespace-pre-wrap, max-h-64 + overflow-y-auto), 자동 적용 없음. 적용 버튼은 params 키 0개여도 weight 체크박스 ON 이면 활성
- **`BacktestComparisonCard`**(자산 배정 *아래*, 항상 렌더, `data-testid="backtest-comparison-card-{strategy_id}"`) — (A) `backtest_summary` null → "백테스트 미실행 — 진행중이거나 외부 MCP 비활성" (B) 자기 전략 current·recommended 둘 다 null → "외부 MCP YAML DSL 미지원 — 로컬 백테스트 어댑터 적용 대기"(외부 제출 대상 = `backtest_orchestration.py` 의 momentum·volatility_breakout·donchian_swing) (C) 그 밖 → 현재/추천 메트릭 8종(`metric-{current|recommended|diff}-{key}`) + 차이값 칩 + 접이식 다른 전략 요약 `backtest-peer-{strategy_id}`. **`max_drawdown` 은 양수(절대값)**: `METRIC_SPECS.max_drawdown.diffSignInverted=true` — 양수 diff(추천 MDD 더 큼) = 손실색, 음수 = 이익색

## BalanceTable

**행 더블클릭 → 종목 차트**(「종목 차트 모달」 절). 행 testid `balance-row-{ticker}`.

**섹터 컬럼**: 헤더 순서 `종목명 → 섹터 → 거래시장 → (전략) → …`. `Holding.sector`, 없으면 `-`. `data-testid="sector-{ticker}"`. `/api/balance` 가 **이미 조회한 stock_master basics 를 재사용**한다(추가 DB 호출 0) — `sector_naming` 단일 진실원(`bstp_kor_isnm` → `_kojiro_sector_key(master_raw)` → `미분류-{ticker}`).

⚠️ **컬럼을 늘리면 빈 상태 행 `colSpan` 도 고친다** — 지금 `isAll ? 16 : 15`, 회귀가 헤더 수와 대조한다.

**예상 매도비용 · 순 평가손익 (cycle411)**: "수익률" 다음. 백엔드가 보유 종목마다 `sell_cost_rate`(수수료율+세율, ETF 는 수수료율만)·`cost_status="estimated"` 를 싣고, 화면이 (WS 실시간 시세로 덮인) 평가금액에 곱한다 — 예상 매도비용 = `round(평가금액 × sell_cost_rate)`, 순 평가손익 = `round(평가손익 − 예상 매도비용 − buy_fee_paid)`(이미 낸 매수 수수료 — 매매손익 표의 페어 net 과 같은 정의). testid `sell-cost-{ticker}`(「추정」 꼬리표 포함) · `net-pl-{ticker}`. `sell_cost_rate` 가 없으면(구 서버) 둘 다 `—`(숫자를 지어내지 않는다). `buy_fee_paid` 가 `null` 이면(비용 조회 실패 = 「모름」) `net-pl-{ticker}` 는 `—` 다(`?? 0` 금지). `buy_fee_paid` 칸 자체가 없는 응답(구 서버)은 매수 수수료를 빼지 않는다. 기존 "평가손익"(세전) 칸은 그대로. 표 루트 `<table>` 에 `whitespace-nowrap` 을 둔다 — `white-space` 는 상속되므로 모든 칸이 줄바꿈하지 않고, 넘치는 폭은 `ScrollPane` 가로 스크롤이 받는다(1280px 에서 한 자씩 꺾여 행이 높아지던 결함 방지).

**손절가 · 목표가 컬럼 (cycle339)**: "현재가" 다음, "평가금액" 앞. 데이터 = Holding 의 `stop_price`/`stop_source`/`target_price`/`target_source`(백엔드 `position_exit_lines` 단일 진실원, 추가 DB 호출 0). testid `stop-price-{ticker}` · `target-price-{ticker}`.

- 🔴 **`stop_source === 'engine_idle'` 는 `⏸` + 툴팁 「매매 엔진 정지 중 — 장 시작(07:45) 후 표시된다. 손절선이 없다는 뜻이 아니다」** — 21:30~07:45 은 엔진이 메모리 포지션을 비워 청산선을 모른다(「없음」 모양이면 손절이 풀린 줄 안다).
- 🔴 **값이 없으면 `—` 다. 0 이 아니다** — 틀린 손절가는 없는 것보다 나쁘다. 판정 불가는 숫자를 지어내지 않는다.
- `stop_source === 'hard_pct'` = 회색 + **「근사」** 꼬리표(고정% 손절 전략의 `매입가 × (1 + 하드손절%)`). `'effective'` 는 실제 쓰는 선이라 꼬리표 없음.
- 🔴 툴팁이 **「가격 무관 청산(15:20 일괄매도 · 스테이지 종료 · 익일청산)은 이 값에 담기지 않는다」**를 말한다.
- **`stop_source === 'mode_dependent'`** = `—` + 회색 **「모드별」**(롱테일 손절 기준이 당일/상한가 모드로 갈려 한 값이면 한쪽이 틀린다). **`target_source === 'measured_move_hit'`** = **「도달」** + 「이미 도달해 익절 신호가 나갔다」 툴팁.
- 🔴 손절가 툴팁은 「이 가격 전에 팔리는 경로」를 **둘로 갈라** 말한다 — **보유일수만으로**(눌림목 돌파 5영업일 · 15:20 일괄매도 · 익일청산) / **다른 조건이 함께 붙는 것**(20일 신고가 스윙은 2영업일 뒤 **돌파고점 아래일 때만** · 대순환 스테이지 종료). ⚠️ **뭉뚱그려 「가격 무관」이라 적지 않는다** — donchian 2영업일 청산은 `days_held ≥ n ∧ current_price < breakout_high` 라 가격 조건부다.
- **목표가는 거의 다 `—` 가 정상** — `bull_flag_breakout` 만 `measured_target`(깃대폭 + 깃발고점)을 갖고 그마저 **부분 익절 트리거**라 툴팁이 "전량 청산선이 아니다" 를 밝힌다. ⚠️ **VB·LTV 의 `target_price` 를 이 칸에 넣지 않는다**(매수 트리거 가격이다).
- 회귀 = `components/__tests__/BalanceTable.exitLines.test.tsx`(**값 검사**).

**거래시장 배지**("종목명" 옆 "거래시장" 컬럼, `data-testid="market-badge-{ticker}"`) — `Holding.nxt_tradable / krx_halted` 조합 5가지: `KRX+NXT`(nxt ∧ ¬halted, emerald-100/800) / `NXT만`(nxt ∧ halted = **KRX 거래정지라 NXT 에서만 거래 가능** — NXT 전용 상장이 아니다, amber-100/800) / `KRX`(¬nxt ∧ ¬halted, gray-100/700) / `정지`(¬nxt ∧ halted, red-100/800) / `확인중`(둘 다 미캐시, gray-50/500). 베이스 `inline-block px-1.5 py-0.5 rounded text-xs font-medium`

## KisAccountPoolCard

Dashboard `MarketRegimeCard` 직하(시장 → 인프라 위계). WebsocketPool 세션 상태 + 슬롯 사용률 + 분배 + 끊김 종목.

- `pool-refresh-button` → `invalidateQueries({queryKey:['realtime-subscriptions']})` · 총 슬롯 `pool-used-slots / pool-total-slots`(41 × N) + `pool-usage-progress`(80%+ amber) + fresh/stale/ACK 카운트
- 세션별 표 `pool-session-row-{label}` — label 배지(main=blue + `(체결통보)`, 그 외 회색) / `pool-session-status-{label}`(connected=emerald / disconnected=red) / subscribed/limit + `pool-session-progress-{label}` / fresh / stale / reconnect_count. **세션 라벨 = DB `kis_quote_accounts.label`**. 보조 0개면 `pool-no-secondary-note`
- 끊김 영역(`stale_60s > 0`): `stale-context-label` — KRX 메인(09:00~15:30) 빨강 "결함 가능" / PRE_NXT(08:00~09:00) 노랑 "거래량 적음" / 그 외 회색 "한산 시 정상" · `pool-resubscribe-button` — `useMutation(resubscribeStale)` → `POST /api/realtime/resubscribe`, 성공 시 `invalidateQueries({queryKey:['realtime-subscriptions','trading-status']})` + "N종목 재구독 완료" · `pool-stale-list-toggle` + `pool-stale-row-{ticker}`(마지막 tick HH:MM:SS, `last_tick_map[ticker]=null` → "—")
- 공용 헬퍼 `frontend/src/utils/stale-context.ts`(`getKstMinutes / getStaleContextByKstMinutes / STALE_CONTEXT_META / formatLastTickKst`)
- 세션별 종목 expand `pool-session-expand-{label}` → `pool-ticker-row-{label}-{ticker}`(ticker / 이름 / stale 배지 / WS tick 시각 / retries / 마지막 강제 재구독 시각). 응답 `sessions[*].tickers_detail`(cap 200, stale 우선)
- KIS 체결/거래량: `inquire_ccnl` 캐시(`last_cntg_hour` HH:MM:SS / `today_volume`). `formatCntgHour` / `isWsSubscriptionSuspect` — KIS 체결시각이 WS tick 시각보다 **300초 이상 더 최신이면** amber "WS 의심"(`pool-ws-suspect-{label}-{ticker}`). 캐시 미스 → "—"
- API `getSubscriptions()` — `/api/realtime/subscriptions` sessions 배열. queryKey `['realtime-subscriptions']`, `staleTime: 5_000`, `refetchInterval: 30_000`(Trading Status 5s 와 별개 큐). 에러 시 `pool-error-message` graceful

## MarketRegimeCard

Dashboard 환경 배너 직하, 전략 탭 위(`<ControlPanel />` 직후).

- regime 배지(defensive=red / neutral=gray / aggressive=blue / 비활성=gray-500) + VIX / Fear & Greed / Buffett / cycle 메트릭 grid + cash_usage_ratio + auto_regime_adjust 토글
- 🔴 **`GET /api/market-regime/current` 의 `buy_blocked` 는 항상 false 다**(레짐은 매수에 개입하지 않는다). `block_reason` 이 있으면 `data-testid="market-regime-block-banner"` amber **"레짐 경보"** 관찰 배너 — "매수 차단" 문구는 쓰지 않는다. ETF 스테이지 소섹션(`etf_kospi_stage`/`etf_kosdaq_stage`/`etf_defensive`, `etf_enabled=false` 시 "관찰 비활성")
- `auto-regime-toggle` — `ConfirmModal`(ON: "다음 영업일부터 cash_min 기반 자동 갱신" / OFF: "운영자 수동값 보존")
- API `getMarketRegimeCurrent()`(queryKey `['marketRegime']`, staleTime 60s) + `setAutoRegimeAdjust(boolean)`. `getMarketRegimeHistory(days)` 는 호출자가 없다
- `enabled=false`(DKSTOCK_REGIME_ENABLED=false) → "비활성" gray 배지 + 메트릭 "—"

## MarketRegimeLabelCard

Dashboard `MarketRegimeCard` 바로 아래. 장세와 시장 유닛을 한 카드에 나란히 둔다(cycle410). `fetchMarketRegimeLabel()` → `GET /api/market-regime-label`(래퍼째 받는다 — `success=false` 면 서버 사유를 그대로 보인다 · 네트워크 오류 = 「장세 라벨을 불러오지 못했습니다.」), queryKey `['marketRegimeLabel']`.

- 왼쪽 「장세」 = 「관찰용 — 매매에 쓰지 않습니다」. 배지 `regime-label-badge` = 한글 6종(`utils/marketRegimeLabel.ts::REGIME_LABEL_KO`) · 근거 「60일선 20일 기울기 ±x.x%」·「20일 변동성 xx%」 · `regime-label-since`(`since_truncated` 면 「… 이전부터」) · `regime-label-basis`
- 오른쪽 「시장 유닛」 = 「실제 매수 수량에 쓰임 — enforce 인 전략만」. `regime-unit-m`(×1/×0.75/×0.5/×0, 못 매기면 —) · 근거 「종가 60일선 위/아래」·「60일선 상승/하락」 · `regime-unit-basis` · `regime-unit-source`(「운영 DB 종가로 다시 계산한 값」 — 엔진 메모리 값이 아니다) · 전략별 모드 `regime-unit-mode-{sid}`(적용/기록만/꺼짐/모름) · 적용 0개면 「지금 적용 중인 전략 없음」
- 띠 두 줄(최근 60거래일) — `regime-label-band`(장세 색) · `regime-unit-band`(m 값). 칸 title = 날짜 + 값. 날짜는 서버 `YYYY-MM-DD` 문자열을 그대로 쓴다(`Date` 변환 없음)
- 정의 = `src/engine/CLAUDE.md` 모듈 맵 `market_regime_label.py`·`market_unit.py` · 회귀 = `components/__tests__/MarketRegimeLabelCard.test.tsx`

## RealtimeHealth (`/realtime-health`)

`fetchRealtimeHealth()`(`frontend/src/api/realtime-health.ts`)가 `/api/logs/search` 로 4 prefix 를 grep 해 카드 4개 — `[dispatch_drop_summary]` · `[callback_exception]` · `[stale_force_retry]` · `[ws_auto_restart]`. 타입 `RealtimeHealthSnapshot`(`types/realtime-health.ts`).

5번째 카드 `MarketOperationCard`(`realtime-health-card-market-operation`) — `fetchMarketOperationStatus()` → `GET /api/realtime/market-operation`(`data.data ?? fallback`), 원천 = 백엔드 `market_operation_monitor`(H0UNMKO0). **표시만 한다(매수 가드 아님)**. 상수 `types/market-operation.ts`.

- 헤더 배지 = VI 활성 N / 거래정지 N / 종목상태 이상 N(0=gray, >0=amber/red) + **서킷브레이커 배지**(`realtime-health-cb-badge`, `circuit_breaker.suspected` true→orange "추정" / false→gray "정상") + 종목별 detail + raw `MKOP_CLS_CODE`/거래정지 사유.
- 「종목상태 이상」 = `iscd_stat_active_count` — **표시 집합** 51~54·58·59(관리·시장경고·거래정지·단기과열)로 센다(55·57·00 제외). 「거래정지」 = `TRHT_YN=="Y"` 또는 종목상태 `58`. 범위가 달라 두 숫자가 달라도 정상이다.
- 행(`realtime-health-op-row-<ticker>`) 배지 셋 — VI(`vi_code`·`ovtm_vi_code` 중 하나라도 활성일 때만, 비활성 집합 `VI_INACTIVE_CODES` = 백엔드 `src/api/market_operation.py::_INACTIVE_VALUES`) · 거래정지(`halt_yn` Y 또는 `58`, 행당 1개) · 종목상태(51 관리종목·52 투자위험·53 투자경고·54 투자주의·59 단기과열만, 55·57·00 은 안 그린다). 정지 사유는 정확히 `(null)` 일 때만 숨긴다.
- 행 목록 = 백엔드 `details`(VI ∪ 거래정지 ∪ 종목상태(51·52·53·54·59), cycle371). 58 은 거래정지 TTL(600초)이 관리하므로 합집합에서 뺀다(넣으면 TTL 만료 뒤에도 영구 잔존).
- 헤더 「종목상태 이상 N건」(58 포함 6종)과 행 배지 수(5종 + 58 은 거래정지 배지)는 갈릴 수 있다(헤더는 마지막 이벤트 기준으로 58 을 세고, 58 행은 600초 뒤 빠진다). 가드 `RealtimeHealth.cycle370.test.tsx`.
- **CB 는 휴리스틱**(사유 키워드 OR 전 시장 halt 비율) — H0UNMKO0 에 CB 전용 필드가 없다. 가드 `RealtimeHealth.cycle186.test.tsx`.

## Strategies (`/strategies`)

등록 전략(현재 7)마다 카드 하나 — 목록을 화면이 들지 않고 응답 그대로 그린다. 4 임계 — `stop_loss_rate`(손절 비율) · `daily_loss_limit`(일일 손실 한도) · `trailing_stop_rate`(Trailing Stop 비율) · `position_ratio`(종목당 매수 비중). 데이터 `GET /api/strategies`(`data?.strategies ?? data` — 플랫/내포 양쪽). `params={}` 면 "—".

### TE/RR 성과 섹션

4임계 *아래* "성과 (최근 3개월)"(`te-section-{key}`) 5행 — 서적 TE(예지치)/RR비율. 데이터 `GET /api/strategies/te?months=3`(`getStrategyTeRr`, `frontend/src/api/strategies.ts`, `useQuery(['strategy-te',3], retry:1, staleTime:5분)`, `/api/strategies` 폴링과 독립). 타입 `TeRrMetrics`(`strategy.ts`, 백엔드 1:1 29필드 = 기본 19 + 실비용 선택 칸 10).

- A: 배지(`te-verdict-{key}` 우위/열위/판정유보) + TE%(`te-value-{key}`) + 3개월 실현 ₩(`te-realized-{key}`, cycle411 — `realized_net_sum_krw`(세후) 기본 + 「세후」 라벨. 그 칸이 없거나 `null` 이면(구 서버·비용 조회 실패) `realized_sum_krw`(세전) + 「세전」 라벨). 판정 지표(TE%·RR·승률·배지)는 **net(세후) 기준**이지만 비용을 못 얹으면 백엔드가 세전으로 계산한다 — 그래서 `realized_net_sum_krw` 가 `null`/없음이면 배지 옆에 `te-pretax-{key}` 「세전」 을 단다(세후 값이 있으면 달지 않는다). 세전 값은 비교용 `*_gross`(`te_pct_gross`/`te_krw_avg_gross`/`win_rate_gross`/`rr_gross`/`verdict_gross`) 로 따로 실리고, 이 섹션은 그것을 그리지 않는다.
- B: RR 게이지(`rr-gauge-{key}`/`rr-gauge-fill-{key}`/`rr-gauge-marker-{key}`) — 실제RR 채움 + 필요RR 세로 마커. 채움 ≥ 마커 = 우위(이익색) / 미만 = 열위(손실색). 색은 시맨틱 클래스 `bg-pnl-profit`/`bg-pnl-loss`(+ `pnlColorClass`)
- C: 분해(`te-decomposition-{key}` 승률 W/L·평균수익·평균손실·N) / D: 구조태그(`te-structure-{key}`) / E: 표본캡션(`te-sample-caption-{key}`)
- **표본 게이트 3분기**: `sample_tier='insufficient'`(N<20) → TE·배지 회색 + "판정 유보" + 게이지·구조 숨김 / `'low'`(20-49)+rr_available → amber "표본 적음" / `'low'`+!rr_available → 게이지 "RR 참고 불가" / `'normal'`(50+) → 정상(single_trade_dominant 시 "RR 과대 가능")
- **오독 방지**: verdict(TE 부호)와 structure_tag(사분면)는 독립 — **verdict 배지가 지배 색**, structure_tag 는 중립 회색(`text-gray-600`) + 형태 병기("견고형 (저승률·고RR)")
- 하단 1회: 참조표(`te-reference-table` 승률 10~90% → 필요RR 9.00~0.11) + 교육 캡션(`te-education-caption`). TE 실패해도 4임계 카드 정상(격리). **관찰 전용, 매매 무관**. 가드 `StrategiesTeRr.test.tsx`

## MarketState (`/market-state`) — 장운영상태

거래소별 장 운영 시간표·주문유형 카탈로그 + 그날의 매매 외 작업 현황. 페이지가 조회를 소유하고 조각 컴포넌트는 순수 표현이다.

🔴 **이 계열(`pages/MarketState.tsx` · `components/MarketState*.tsx`)에는 시각 리터럴·행 id·주문유형 코드·거래소 이름을 두지 않는다** — 전부 응답 값을 보간한다(화면이 값을 들면 표가 바뀐 날부터 옛 표를 그린다). 커서도 서버가 판정한다. 클라이언트 계산은 **남은 시간 스톱워치**(두 시각의 *차이*) 하나, 0 에 닿으면 **재조회 1회**(다음 행을 스스로 계산하지 않는다). 이름 규약 가드 FE19/FE20 이 `components/MarketState*.tsx` 도 감시한다.

- 조회 3: `fetchMarketState`(표·커서, 단일 `useQuery`) · `GET /api/realtime/market-operation`(RealtimeHealth 5번째 카드와 **같은 응답·같은 쿼리키**) · `GET /api/market-ops`(섹션 B 전용, 독립 쿼리)
- 헤더 `market-state-asof`(KST) · `on_date` · `market-state-trading-day-badge`(개장/휴장/확인 불가, title=`trading_day_source`) · 표 버전 · `market-state-refresh`. `market-state-preview-banner` = 다른 날짜를 볼 때는 "지금" 커서를 그리지 않는다
- (1) 현재 상태 카드 `market-state-card-{market}` — 시간대·시장가 가능 여부·주문 가능 여부·확신도·동시에 열린 창·`market-state-card-countdown-{market}`
- (1-A) **지금 시장은**(`MarketStateNow.tsx`, `market-state-now-section`) — 실시간 VI·거래정지·서킷브레이커(추정). 🔴 지킬 셋:
  - ① **관측 커버리지를 숨기지 않는다** — `H0UNMKO0` 는 대표 종목 + 보유·익일청산 종목만 구독해 "VI 0건" ≠ "VI 없음". 수신 종목 수(`last_event_count`)를 **항상** 병기(`market-state-now-coverage-note`)
  - ② **서킷브레이커는 추정이다** — "추정" + 판정 근거(halted/observed·사유 표본, `market-state-now-cb-basis`)를 평시에도 보인다
  - ③ **세션 상태 4분기**(`market-state-now-session-badge`) = 관측 중 / 장 종료 — 마지막 관측값(엔진 phase `closing`·`settling`·`log_analysis` 는 값이 얼어붙는다) / 세션 종료 — 집계 없음(정산 `_reset_daily_state` 뒤의 0 ≠ "이상 없음") / 엔진 상태 확인 불가
- (1-B) **오늘 야간작업**(`MarketStateOps.tsx`, `market-state-ops-section`) — `GET /api/market-ops` 시각순 타임라인. 예정 시각 = 라우트가 `scheduler.TIME_*`(+ `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`)에서 읽은 문자열. 상태 어휘 10종을 그대로 보인다 — `scheduled` / `running` / `done` / `overwritten`(20:05 metrics 1차 스냅샷을 21:30 정산 완전판이 덮은 정상 — **결함 아님**, `failed` 와 다른 색) / `failed` / `skipped_fresh` / `skipped_weekly` / `not_fired`(증거 없음, 점선 테두리) / `holiday` / `unknown`(마커 영구 결측 — **없는 증거를 실패로 위장하지 않는다**). 실패(red)·미발화(gray) 배지는 sRGB 거리로 벌린다
- (2) 커서 표 `market-state-table` — 시장별 그룹, 행 `market-state-row-{row_id}`. 현재 행 커서 · 지난 행 흐리게 · 동시에 열린 창 점선
- (3) 주문유형 카탈로그 `market-state-catalog` — 행 `market-state-catalog-row-{code}`(`data-confidence`), 셀 `market-state-catalog-cell-{code}-{exchange}`(`data-support`). **● 지원 · ? 확인 필요 · 빈칸 미지원** — 🔴 **확인하지 못한 칸을 미지원으로 접지 않는다**("모른다" ≠ "안 된다"). `confidence !== 'confirmed'` 면 "확인 필요". 표가 드러낸 것 = `market-state-finding-{i}`
- (4) 바닥 `market-state-board-note`(보드 ≠ 장 상태) · `market-state-unconfirmed-note` · 실패: 404 → `market-state-notice` / 그 외 → `market-state-error` + `market-state-failure-detail` + `market-state-retry`

## Macro (`/macro`) — cycle303 매크로 분석

`stock-manager` 의 `macro_lite` 패키지(`packaging/macro_lite/`) 이식 — 백엔드 = 독립 `macro` 컨테이너(포트 미노출, nginx `/api/macro/` 프록시), 프론트 = `frontend/src/macro/` 아래 `.tsx`. 🔴 `src/engine/market_regime.py` 도 이 컨테이너를 본다(cycle315). 그래도 레짐은 **관찰 지표**라 매수를 차단·축소하지 않는다.

- **5섹션**(원본 순서 고정): 경기사이클+투자체제(`MacroCycleSection`) → 장단기 금리차(`YieldCurveSection`) → 하이일드 스프레드(`CreditSpreadSection`) → 환율(`CurrencySection`) → 원자재(`CommoditySection`). 루트 `data-testid="macro-section-{cycle|yield-curve|credit-spread|currency|commodity}"`. 6번째 「시장 등락 통계」 는 그 뒤에 붙고 출처가 다르다(아래 「시장 등락 통계」 항목).
- **경기사이클 보존 7항목**(구조 재설계 금지) — 국면 4칸(`macro-cycle-phase-{phase}`) · 체제 4칸(`macro-cycle-regime-{regime}`, `RegimeDetail` 안 보조 스트립) · 두 카드 `grid-cols-2` 나란히 · 지표 카드 5종(`macro-cycle-indicator-{key}`) · `DivergenceNote`(국면·체제 엇갈릴 때만, `macro-cycle-divergence-note`) · 체제 상세(공포탐욕/버핏지수/VIX) · `InfoTooltip` 해설 2종.
- 🔴 **두 단계이동 스트립은 각자의 카드 안 같은 자리에 있다** — 두 카드가 「제목 → 큰 배지 → 부제 → 4칸 스트립(`grid-cols-4 gap-1.5`) → 상세」 순서를 공유하므로 바꿀 땐 둘을 같이 바꾼다. 국면 쪽 화살표(→)는 두지 않는다 — 반쪽 폭 카드에서 60px 를 먹어 4칸 라벨이 찌그러진다. 가드 `MacroPage.test.tsx` 「각자의 카드 안 같은 자리」(카드 내 자식 인덱스까지).
- 🔴 **`confidence` 는 「1·2위 점수차」로 보여 준다 — 확률이 아니다.** 값 = `cycle.py` 의 `(1위 총점 − 2위 총점) × 200`(적중률 교정 없음). `macro-cycle-gap` 이 지키는 넷: (a) 라벨에 「신뢰」 금지 (b) 단위는 `%` 가 아니라 `점` (c) 눈금은 **1위를 100% 로 잡은 상대 막대** — 0~1.00 공통 눈금 금지(국면별 도달 가능 최대 총점이 달라 1.00 은 거짓 분모) (d) 2위 국면 **이름은 응답에 없으니**(`final_scores` 미반환) 「이름 없음」. 구간 배지(팽팽/보통/뚜렷)는 고정 컷이 아니라 `2 × 기여 > 격차` 에서 끌어낸다.
- 🔴 **지표 카드는 `score`(당선 국면 기여)만 쓰고 `score / weight`(지지율)는 쓰지 않는다** — 지표마다 상한이 달라 지지율 비교는 거짓이다(기여는 **다 더하면 그 국면 총점**). testid `macro-cycle-contrib-{key}`.
- ⚠️ **새 testid 에 `macro-cycle-phase-` · `macro-cycle-indicator-` 접두사를 물려주지 않는다** — 보존 가드가 그 접두사를 정규식으로 세어 「국면 4칸」·「지표 카드 5종」을 단언한다.
- 확률 오독 복귀는 `MacroPage.test.tsx` 가 막는다 — 금지어 6종(신뢰·정확·확률·가능성·적중·맞을) 스코프 = **`macro-cycle-gap` 서브트리**(넓히면 보존 대상 `REGIME_TOOLTIP`(「신규 매수 금지」)·`DivergenceNote`(「매수 기회일 수 있습니다」)가 걸린다).
- **타입 계약 2가지**(`types/macro.ts`) — `MacroCycleResponse.cycle` optional(`data.cycle || data` 폴백), `RegimeData` 는 `regime?.regime` optional chaining. 응답 shape 계약이라 지우지 않는다.
- `api/macro.ts` 는 `api/client.ts`(axios, `baseURL:'/api'`)를 쓰고 `X-API-Key` 를 붙이지 않는다(nginx 가 주입·치환). 요청마다 `{ timeout: 60000 }` 오버라이드(콜드 캐시가 기본 10초를 넘는다).
- 5개 응답은 **`ApiResponse<T>` 래퍼를 쓰지 않는다** — 원본 계약 `{ <section>, updated_at, errors }` 그대로.
- 훅은 원본 `useAsyncState` 계열이라 「테스트 규약」 1(`useQuery` `retry:1`)이 적용되지 않는다.
- `EventLabelsOverlay` 음영 alpha 는 원본 값(약세장 0.10 · 침체 0.18) 그대로, 색 hex 리터럴은 전부 `var(--color-...)` CSS 변수로 치환(신규 hex 금지).
- 회귀 가드 `frontend/src/macro/__tests__/MacroPage.test.tsx`.
- **6번째 섹션 「시장 등락 통계」(cycle416)** — 원자재 뒤에 붙는다. 이 섹션만 `macro` 컨테이너가 아니라 **우리 backend** 의 `GET /api/market/breadth` 에서 온다(라우트 계약 = `src/routes/CLAUDE.md` 엔드포인트 목록). 그래서 위 5섹션 규약과 다른 점이 넷이다:
  - 응답은 `ApiResponse<MarketBreadthData>` 래퍼다(`types/market-breadth.ts`).
  - 🔴 경로는 `/market/breadth` 다 — `/macro/` 밑에 두지 않는다. 그 접두사는 nginx·vite 가 `macro` 컨테이너로 보낸다(가드 FG4).
  - 훅은 `hooks/useMarketBreadth.ts`(`useAsyncState` 기반, `days` 기본 20)다. 원본 이식 파일 `useMacro.ts` 는 건드리지 않는다(FG3).
  - 섹션 래퍼 `macro-section-market-breadth` 는 로딩·실패·정상 모든 상태에서 보인다. 조회가 최대 45초라 로딩 문구(「최근 N영업일 전 종목 시세를 받는 중...」)로 무엇을 기다리는지 알린다. 다른 섹션은 이 섹션을 기다리지 않고, `macro` 컨테이너가 죽어도 이 섹션은 뜬다.
- 시장 등락 조회 = `api/market-breadth.ts::getMarketBreadth(days = 20)`. `MARKET_BREADTH_TIMEOUT_MS = 60_000`(= nginx `location /api/` 기본 `proxy_read_timeout`, 백엔드 시한 45초를 덮는다). 본문 `success:false` → 서버 문장 그대로 `Error(message)` · HTTP·네트워크 오류 → 「시장 등락 통계를 불러오지 못했습니다」 한 문장.
- 시장 등락 화면 구성 — 시장 토글 `breadth-market-{kospi|kosdaq|total}`(기본 합계, `aria-pressed`) · 칩 6 `breadth-chip-{adr|up|down|limit-up|limit-down|up-ratio}`(채운 날이 요청보다 적으면 ADR 라벨이 `ADR(n일)`) · 차트 `breadth-chart`(recharts `ComposedChart` — 상승 막대는 위·하락 막대는 아래인 대칭 축, 상·하한가 수는 막대 끝 라벨(0 이면 생략), 오른쪽 축 상승 비율 선 0~100% + 50% 점선, 커스텀 툴팁) · 날짜별 표 `breadth-table`(가로 스크롤 상자 · 행 `breadth-row-{date}` + 합계 `breadth-row-total` · 칸 `breadth-cell-{key}`) · 상태 줄 `breadth-missing`(빠진 날, 차트 위 노란 상자) · `breadth-short`(빠진 날 없이 요청 일수 미달) · `breadth-pending`(아직 KRX 미게시) · 각주 `breadth-footnote`(ADR 산식·기준선·용어 정의).
- 🔴 시장 등락은 **한국 관례 색**이다 — 상승·상한가 빨강 · 하락·하한가 파랑. 막대 색은 `var(--color-red-500)`·`var(--color-blue-500)` CSS 변수이고 hex 리터럴은 0 이다(FG2).
- 시장 등락 날짜는 서버가 준 KST `YYYY-MM-DD` 문자열을 자르기만 한다(`marketBreadthChart.ts::mmdd`). 이 섹션과 차트 계산 파일에 `new Date(`·`Intl.DateTimeFormat` 을 쓰지 않는다(FG1). 기준 시각은 `utils/kst.ts::formatKstDateTime` 으로 보인다.
- 차트 값은 순수 함수 `marketBreadthChart.ts` 로 잰다(jsdom 은 recharts SVG 를 그리지 않는다) — `buildBreadthChartRows`(최신 먼저인 응답을 뒤집되 입력 배열은 바꾸지 않는다) · `breadthAxisMax`(계단 1·1.2·1.5·2·2.5·3·4·5·6·8·10 × 10ⁿ 으로 올림).
- ⚠️ 빠진 날은 차트 x축에서 칸 없이 이어 붙는다(프론트가 영업일 달력을 다시 계산하지 않는다). 어느 날이 빠졌는지는 `breadth-missing` 이 알린다.
- 시장 등락 회귀 = `macro/__tests__/MarketBreadthSection.test.tsx` · `marketBreadthChart.test.ts` · `_ast_market_breadth_guards.test.ts`(FG1~FG5) · `api/__tests__/market-breadth.test.ts` · `MacroPage.test.tsx`(6번째 자리·독립 로딩). MSW = `test/handlers.ts` + `test/fixtures/marketBreadth.fixture.ts` · E2E 목 = `e2e/fixtures/api-mocks.ts`(FG5 — 없으면 `/macro` 마운트가 ECONNREFUSED).

## Backtest (`/backtest`) — 2026-10-06 30년 전략 성적표

연구 보고서(`_workspace/reports/*_scoreboard_30y.html`)를 게시한 독립 HTML(`frontend/public/backtest/scoreboard_30y.html`)을 iframe 으로 감싼다. **실제 매매 설정과 무관** — 이 페이지는 틀만 제공하고 숫자·판정은 보고서가 정본이다.

- `pages/Backtest.tsx` — 안내문 + 생성 시각(보고서 본문의 `"generated_kst"` 를 fetch 로 뽑아 표시, 못 찾으면 생략) + `<iframe src="/backtest/scoreboard_30y.html">`(화면 높이 가득) + "새 창에서 열기" 링크. 상태 3종 = `backtest-loading` / `backtest-error`("서버 연결 끊김") / `backtest-empty`.
- **게시 절차** — 보고서가 갱신되면 `python3 tools/replay/scoreboard_page/publish_to_frontend.py <보고서 경로>` 한 번만 돌린다. 이 스크립트가 (a) cdnjs Chart.js `<script>` 를 `frontend/node_modules/chart.js/dist/chart.umd.js` 복사본(`public/backtest/chart.umd.js`)으로 바꿔 외부 CDN 의존을 없애고 (b) 보고서가 `<!doctype>`/`<html>`/`<body>` 없는 조각(fragment)이면 독립 페이지로 감싼다. 내용·숫자는 건드리지 않는다.
- `chart.js` 는 `frontend/package.json` 의존성(`^4.4.1`) — UMD 비압축 번들(`chart.umd.js`, 이 버전엔 min 빌드가 없다)을 그대로 게시한다.
- nginx — `location /backtest/` 정적 파일은 `try_files $uri` 로 그대로 서빙(SPA fallback 에 먹히지 않음, 템플릿 미수정).

## 주문 안전성

- 시작/정지/매도 등 주문 관련 버튼은 ConfirmModal 이중 확인 필수

## 인증

- **프로덕션은 nginx Basic Auth 뒤에 있다** — `frontend/nginx.conf.template` 이 SPA·`/api/` 를 덮고 `/api/` 프록시가 백엔드 키를 **서버 측에서** 주입한다(번들·브라우저에 키 없음). 🔴 `auth_basic off;` 금지 · 옛 `frontend/nginx.conf` 부활 금지 · TLS 템플릿 `map` 중복 정의 금지 등 nginx·백엔드 계약 정본 = 루트 [`CLAUDE.md`](../CLAUDE.md) 「Docker / 배포」 절 · [`src/routes/CLAUDE.md`](../src/routes/CLAUDE.md).
- **`client.ts` 는 `withCredentials: true` 다** — 자격 없는 XHR 의 401 이 로그인 다이얼로그를 **두 번** 띄운다. 동일 출처(`baseURL: '/api'`)라 CORS 파급 0. 가드 `tests/unit/ast/test_cycle246_nginx_template_no_key_leak.py::G-246-5`(주석을 걷어낸 뒤 검사).
- **아이콘 경로는 `return 204;` 로 단락한다** — `/favicon.ico`·`/favicon.svg`·apple-touch 정규식(크기 변형 포함). Safari 가 아이콘을 자격 없이 따로 가져와 그 401 의 `WWW-Authenticate` 가 두 번째 다이얼로그가 된다. `return` 은 rewrite 단계라 `auth_basic` 에 닿지 않는다(`auth_basic off` 불필요). **블록엔 `return 204;` 외 지시자를 두지 않는다**(proxy_pass/root 가 들어오면 무자격 제공). 실제 아이콘은 `index.html` 의 **data URI**(`/favicon.svg` 서버 경로로 되돌리면 재발). 가드 `tests/unit/ast/test_cycle247_icon_probe_no_second_prompt.py` G-247-1~5.
- **dev 는 nginx 를 거치지 않는다** — `vite.config.ts` proxy 가 `X-API-Key`(= `process.env.API_AUTH_KEY`)와 `Origin: apiTarget` 을 함께 넣는다. Origin 을 빼면 `changeOrigin: true` 가 Host 만 바꿔 백엔드 CSRF 검사가 **상태변경만** 401 로 막는다.
- **알려진 한계 (워크리스트 cycle243 후속 F4)** — `client.ts` 에 **401 인터셉터가 없다**. 자격 만료·키 교체 시 폴링(최단 3초)이 재인증 유도 없이 조용히 실패한다.

## 백엔드 연동

- 모든 API 호출은 `api/client.ts` axios 인스턴스 경유(기본 `timeout` 10초 — 더 긴 호출은 요청마다 오버라이드)
- 모든 API 응답 타입은 `src/types/` 정의. 응답은 `types/common.ts::ApiResponse<T>` 로 파싱(예외 = macro 5개 응답, 「Macro」 절)
- 백엔드 응답 필드명 = TypeScript 속성명 (1:1, 변경 시 동기화)
- 페이징 응답에 `total`/`total_pages` 필드 필수
