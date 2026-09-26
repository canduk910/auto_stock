# CLAUDE.md — frontend/ (React 대시보드)

> 이력: [`docs/history/frontend-CLAUDE.history.md`](../docs/history/frontend-CLAUDE.history.md)
>
> 이 문서는 **지금 화면이 지키는 계약만** 적는다. 바뀐 경위·실측 수치·결정 근거는 위 history 로,
> 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](../docs/HARNESS_CHANGELOG.md) 로 간다.

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
├── api/       # axios 호출 (client.ts: `baseURL: '/api'` + `withCredentials: true`, 401 인터셉터 없음)
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

Dashboard 만 즉시 import. 나머지 9 페이지(History · Recommendations · Logs · Settings · StrategyFunnel · StockMaster · RealtimeHealth · Strategies · MarketState)는 `React.lazy()` + Suspense skeleton. `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환 보존.

## AppShell 레이아웃 — 화면 폭 슬라이더

`App.tsx::AppShell` 이 콘텐츠 폭을 사용자 조정 가능하게 노출한다.

- **상태**: `useContentWidth()` 훅 — `autostock.contentWidth` localStorage 키(정수 level 0~100, **기본 100=전체폭**). lazy `useState` 초기화가 mount 시 localStorage 복원(vite CSR, SSR 없음). `setLevel` 이 state+localStorage 동기, try/catch graceful(프라이빗 모드).
- **슬라이더**: 나브 PC 행(`hidden sm:flex`) 우측 `ml-auto` 에 `<input type="range" min=0 max=100 step=5>` (`data-testid="content-width-slider"`, `aria-label="화면 폭 조정"`, 네이티브 range = 키보드 Arrow/Home/End 조작). **모바일 미노출**(소화면 조정 불요).
- **적용**: **`<main>` 만** 슬라이더 값에 반응한다 — `App.tsx` 의 `<main style={{ maxWidth: contentMaxWidth(level) }}>`. `contentMaxWidth(level) = max(1024px, {60 + level*0.4}%)` (level 100→전체폭 / level 0→`max(1024px, 60%)`). `max()` 는 **상한**이라 소화면 오버플로 없음(뷰포트 폭으로 자연 축소).
- 🔴 **나브는 기본폭 고정이다** — `NavBar.tsx` 의 `NAV_INNER_MAX_WIDTH`(= `contentMaxWidth(기본 level)`). **나브를 동적 폭으로 되돌리지 마라** — 슬라이더가 그 컨테이너 안에 있어서 드래그 중 컨테이너가 리사이즈되면 슬라이더 위치가 포인터와 어긋난다(cycle288).
- 회귀 가드 `src/__tests__/ContentWidthSlider.test.tsx` — 슬라이더 aria-label/role · 기본 전체폭 100% · 조정+localStorage 저장 · 복원 · AppShell 구조 + **T6**(나브 고정 ∧ main 반응을 한 케이스에서 함께 단언 — 나브만 얼리는 오시정도 잡는다) + **T7**(슬라이더가 `nav-inner` 안에 있음 = 깜박임의 구조적 원인 봉인). **프론트 전용, 백엔드/매매 무관**.

### 나브 2단 카테고리 구조

나브는 **`src/components/NavBar.tsx`** 다(`App.tsx` 에는 라우트·레이아웃·`useContentWidth` 소유만 남는다). 공유 상수·훅(`CONTENT_WIDTH_*`·`contentMaxWidth`·`useContentWidth`)은 **`src/utils/contentWidth.ts`** 가 단일 출처다.

메뉴는 leaf 11개를 **상위 8개**로 묶는다(사용자 지정 묶음·순서 — 바꾸지 마라):

| 상위 | 세부 | 경로 |
|---|---|---|
| 대시보드 | (단독) | `/` |
| 거래 내역 | (단독) | `/history` |
| 로그 | (단독) | `/logs` |
| **종목** | 조건검색 추적 · 종목마스터 | `/strategy-funnel` · `/stock-master` |
| **전략** | 전략 현황 · 전략수정 AI자문 | `/strategies` · `/recommendations` |
| 매크로 | (단독) | `/macro` |
| 설정 | (단독) | `/settings` |
| **운영상태** | 장운영상태 · 실시간 상태 | `/market-state` · `/realtime-health` |

- 자료구조 `NavEntry = leaf{to,label} | group{id,label,children}` — **드롭다운 유무가 데이터로 결정된다**(컴포넌트에 분기를 흩뿌리지 않는다). 단독 항목에 드롭다운을 만들지 않는다(하위가 하나뿐인 드롭다운은 클릭을 한 번 더 요구해 더 난잡해진다).
- **활성 표시**: 세부 경로에 있으면 상위 트리거도 활성(`bg-gray-100`). 현재 위치를 잃지 않는 것이 계약이다.
- **disclosure 패턴**(`aria-expanded` 만, `aria-haspopup` 없음) — `role=menu`/`menuitem` 을 두지 않았으므로 `aria-haspopup="true"` 로 메뉴를 약속하면 스크린리더에 거짓이 된다.
- 키보드: Enter/Space 열기 · ArrowDown/Up 이동 · Escape 로 닫고 트리거 포커스 복귀 · 항목 선택 후에도 트리거로 포커스 복원(패널 언마운트로 `<body>` 로 떨어지는 회귀 차단). 포커스 트랩은 두지 않는다.
- 닫힘 조건 3: 바깥 클릭 · 포커스 이탈(`onBlur`/focusout) · 라우트 이동(뒤로가기 포함). `openGroup` 단일 상태라 한 번에 하나만 열린다.
- 모바일 드로어는 **접지 않는다** — "그룹 제목(링크 아님) + 들여쓴 하위" 로 11개 leaf 를 항상 보여준다.
- 🔴 **경로 11/11 이 메뉴에서 도달 가능해야 한다.** 그룹 안에 묻혀 사라진 메뉴는 URL 을 직접 치지 않으면 영영 못 본다 — `AppShell.test.tsx` 가 href 11개 집합의 불변을 단언한다. (`/log-reports` 는 `/logs?tab=daily-report` 로 가는 **구 북마크 리다이렉트**라 메뉴 항목이 아니다.)
- 보존 testid 4: `nav-sticky-wrapper` · `content-width-slider` · `mobile-menu-button` · `mobile-menu-drawer`. 그룹용 = `nav-inner` · `nav-mobile-group-{id}` 등.
- ⚠️ e2e 에서 그룹 하위 라벨은 **접힌 상태에 DOM 에 없다.** 페이지 제목을 검증할 때 `getByText(...)` 를 쓰면 모바일 헤더의 숨은 현재-메뉴 span 을 집는다. 본문 제목은 `getByRole("heading", {name})` 로 고정하고, 그룹 트리거 클릭은 `getByRole("button", {name, exact: true})` 로 부분 일치를 막는다.

## 표 스크롤 — `ScrollPane` 단일 진실원

표는 **브라우저 창 크기에 맞춰** 가로·세로로 스크롤한다. 담당은 `components/ScrollPane.tsx` 하나다.

- **고치는 것** = 「가로 스크롤바를 보려면 세로로 끝까지 내려가야 하는」 결함이다. `overflow-x-auto` 래퍼에 **높이 상한이 없으면** 래퍼 높이가 표 전체 높이가 되고 브라우저는 가로 스크롤바를 래퍼 **바닥**에 붙인다 — 표가 길면 그 바닥은 화면 밖이다.
- **`maxHeight` = 창 높이 − 그 요소의 화면상 top − `bottomGutter`(24)**. 고정 픽셀도 고정 `vh` 도 아니라, 위에 무엇이 얼마나 쌓여 있든(나브·배너·필터·요약 바) 남은 공간을 정확히 쓴다. 하한 `minHeight`(220) 아래로는 줄지 않는다.
- 🔴 **`top` 은 화면 안(`0 ≤ top < viewport`)일 때만 뺀다.** 두 바깥 경우는 **창 전체**가 예산이다 — (a) `top < 0`(페이지가 스크롤돼 요소가 화면 위로 올라감)을 그대로 빼면 예산이 창보다 커져 pane 이 뷰포트를 넘고 **가로 스크롤바가 다시 화면 밖으로 밀린다**(실측: 창 800px 인데 pane 바닥 1420.5px) (b) `top >= viewport`(아직 화면 아래, 대시보드 하단 카드)를 그대로 빼면 음수라 `minHeight` 220px 로 떨어져 **스크롤해서 도달해도 220px 짜리 표만 보인다**(실측: 대시보드 잔고표 top=1387). ⚠️ 이 두 경우는 **스크롤 리스너로 풀지 않는다** — pane 이 커지며 아래 내용이 밀려 내려가는 점프가 생긴다.
- 🔴 **측정은 `resize` 와 `ResizeObserver(document.body)` 만 듣고 `scroll` 은 듣지 않는다** — 스크롤마다 재면 「pane 이 커짐 → 문서가 길어짐 → 다시 잼」 되먹임이 된다. 갱신에 `TOLERANCE_PX`(8) 문턱을 두어 1px 진동이 observer 를 다시 깨우는 무한 루프를 막는다(브라우저가 루프를 끊으면 콘솔에 `ResizeObserver loop` 만 남고 화면은 조용히 떤다).
- **측정 불가(jsdom·SSR·`ResizeObserver` 부재)는 `70vh` 폴백**이다 — **상한 없는 상태로 돌아가지 않는다**(그러면 고치려는 결함이 그대로 재현된다). `data-measured` 가 `px|vh` 로 어느 쪽인지 드러낸다.
- 머리글은 기본 고정(`stickyHeader`, Tailwind arbitrary variant `[&_thead_th]:sticky`)이라 표마다 `thead` 를 고쳐 다니지 않는다. 표가 아닌 콘텐츠는 `stickyHeader={false}`.
- 🔴 `{...rest}` 가 `data-testid` **뒤**에 온다 — 교체 자리가 이미 갖고 있던 `data-testid`(예: `stock-master-daily-table`)가 이겨야 그 자리의 기존 회귀 가드가 살아 있다.
- **적용 24곳** — 기존 `overflow-x-auto` 표 래퍼 21곳(`TradePnLGrid`·`TradeHistoryGrid`·`BalanceTable`·`StockMaster`×3·`OrderMonitor`×2·`ScanMonitor`×4·`KojiroMonitor`×2·`MarketState`×2·`BreakoutCandidateMonitor`·`KisAccountPoolCard`·`KisQuoteAccountsCard`·`MarketStateOps`·`Strategies`) + 래퍼가 없던 3곳(`StrategyFunnel`·`BacktestComparisonCard`·`PortfolioRiskCard`).
- ⚠️ **일부러 적용하지 않은 곳 2** — `pages/Recommendations.tsx` 파라미터 표는 **표 안에 `InfoTooltip`** 이 있고 그 툴팁이 `absolute bottom-full` 이라 overflow 컨테이너가 위로 나가는 부분을 **자른다**. `macro/components/MacroCycleSection.tsx` 는 30줄짜리 지표표라 이득이 없는데 클리핑 맥락만 새로 생긴다. 🔴 **표 안에 `InfoTooltip`(또는 다른 `absolute` 팝오버)이 있으면 `ScrollPane` 을 씌우기 전에 잘림을 먼저 확인한다** — 적용 24곳은 툴팁 0건임을 확인했다.
- 회귀 = `components/__tests__/ScrollPane.test.tsx`(14, **값 검사** — 실제 `maxHeight` 픽셀·floor·창 확대 추종·음수 top·화면 밖 top·vh 폴백·두 축 overflow). 돌연변이 실측 = 상한 제거 6 RED · `overflow-x-auto` 회귀 1 RED · floor 제거 1 RED · 화면 안 판정 제거 1 RED.
- **E2E `e2e/scroll-pane.spec.ts`(4)가 지키는 불변식 넷** = ① 상한이 반드시 걸린다 ② 상한이 **창 높이를 넘지 않는다** ③ 상한이 **`minHeight` 에 갇히지 않는다** ④ 화면 안 표는 바닥도 화면 안이다. ⚠️ **모든 pane 에 「바닥 ≤ 창높이」를 요구하면 안 된다** — 대시보드처럼 긴 페이지에서는 표가 화면 아래에 있는 것이 정상이다(spec 초판이 그렇게 틀렸고, 그 실패가 위 (b) 결함을 찾아냈다). ⚠️ 창 축소 검증은 **`max-height`** 로 한다 — 내용이 짧으면 실제 높이가 상한보다 작아 창을 줄여도 안 변한다. ⚠️ `/history` 탭은 `role="tab"` 이 아니라 평범한 `<button>` 이다.

## 시각적 컨벤션

- **DK Stock 디자인시스템 v2 — 가을 팔레트 + Gmarket Sans.** 브랜드명 "DK Stock"(로고타입은 `components/NavBar.tsx`, `font-brand`). 본문 서체 `font-sans` = Gmarket Sans(Light 100–300 / Medium 400–500 / Bold 600–900, `font-display: swap`, `public/fonts/GmarketSans{Light,Medium,Bold}.ttf`). `src/index.css` 의 Tailwind v4 `@theme` 가 `red/blue/gray` 를 가을 톤(rust/slate-blue/warm-gray)으로 재정의하고 `green→sky, amber/yellow→beige, purple/violet/indigo→navy, pink/orange→brown, emerald→blue, cyan→sky, slate→gray` 별칭을 매핑한다 — 기존 `bg-*-*` className 은 무수정으로 새 톤을 받고, 신규 이름 `navy/beige/brown/sky` 도 직접 사용 가능. 단일 진실원은 `src/index.css`(`@theme` 원본)와 `utils/pnlColor.ts`/`types/strategy.ts`(파생 hex) 뿐 — **다른 소스 파일에 색 hex 리터럴을 새로 두지 않는다**(회귀 가드 `src/__tests__/designSystem.v2.test.ts` 가 `#FF3333`/`#3366FF`/`#333333`/`#2563eb` 4종의 전수 부재를 잠근다).
- **손익색 (`utils/pnlColor.ts` 단일 진실원)**: 이익 `PROFIT_HEX '#c34a36'` (rust, red-500) / 손실 `LOSS_HEX '#3d73b7'` (slate-blue, blue-500) / 보합 `NEUTRAL_HEX '#41403b'` (gray-700). `pnlColorClass(value)` 는 하드코딩 임의값이 아니라 시맨틱 Tailwind 클래스 `text-pnl-profit` / `text-pnl-loss` / `text-pnl-flat` 를 반환하고, `@theme` 의 `--color-pnl-{profit,loss,flat}` 이 이 상수와 동일 값으로 정의된다(드리프트 시 `designSystem.v2.test.ts` 가 붉어진다). `pnlColorHex(value)` 는 style 인라인 color 용 hex 문자열(undefined/null/NaN → NEUTRAL). ⚠️ `text-red-600`/`text-blue-600` shade 계열(`TradePnLGrid`/`BreakoutCandidateMonitor`)은 별개 shade 라 이 상수에 편입하지 않는다(픽셀 변경 방지).
- **전략 식별 7색 (`types/strategy.ts::STRATEGY_COLORS`)**: momentum `#3d73b7`(blue) · volatility_breakout `#364c6d`(navy) · long_tail_volatility `#b39364`(beige) · donchian_swing `#488eb4`(sky) · bull_flag_breakout `#c34a36`(red) · vcp_breakout `#9d6644`(brown) · kojiro `#141c2b`(navy 900) · DEFAULT `#74716a`(gray). 각 `bg/text/badge` 는 위 팔레트 색 이름의 `@theme` 토큰을 가리킨다(별칭 정의도 인정).
- **⚠️ 별칭 재정의는 서로 다른 상태가 같은 실제 hex 로 겹칠 수 있다 — 새 배지 색을 고를 때 별칭표(위)를 먼저 대조하고 배경 sRGB/ΔE2000 거리로 검증한다.** 현행 배정 = `ScanMonitor` `BOARD_META` 5보드 blue/sky/navy/beige/brown · `IntegrationToggleCard` `ToggleRow` ON 배지 sky · `PortfolioRiskCard` `AccountGateBlock` '경고' 배지 `beige-200/800` · `TradeHistoryGrid` 체결상태 PARTIAL `brown-200/800`. 회귀 가드 = `ScanMonitor.boardColorAlias.test.tsx` / `IntegrationToggleCard.badgeAlias.test.tsx` / `badgeContrast.cycle261.test.tsx`.
- **자체 호스팅 서체 nginx 캐시**: `nginx.conf.template`/`nginx.tls.conf.template` 에 `location ^~ /fonts/ { expires 30d; add_header Cache-Control "public, max-age=2592000"; default_type font/ttf; }` — 정적자산 정규식에 `ttf` 가 없으면 `/fonts/*.ttf` 가 SPA fallback 으로 떨어져 `no-store` 를 받는다. 파일명에 해시가 없어 `immutable` 대신 유한 TTL. 회귀 가드 `tests/unit/ast/test_cycle261_font_cache_headers.py`.
- 금액: 천 단위 콤마 / 수익률: 소수 2자리 + %
- 환경 배너: 실전=빨강(`bg-red-600`) "실전 매매 환경" / 모의=`bg-sky-600` "모의투자 환경"
- 슬라이더 accent 색은 리터럴 hex 대신 `'var(--color-navy-600)'`(Tailwind v4 `@theme` 가 `:root` 에 노출하는 CSS 변수) 를 쓴다 — `components/NavBar.tsx`(폭 슬라이더) + `CashUsageRatioCard.tsx` + `TradeAmountFilterCard.tsx` + `PriceFilterCard.tsx`(최소/최대 2곳) 5곳 동일. 신규 슬라이더 추가 시도 같은 값으로 맞춘다.
- **시각 표시는 KST 강제** — 단일 진실원 `src/utils/kst.ts`: `formatKstHHMM(iso)`(HH:mm, `hour12:false`) · `formatKstDateTime(iso)`(`yyyy-MM-dd HH:mm:ss`, `formatToParts` 조립) · `kstTodayISO(now?)`. 잘못된 입력은 `'—'`. **새 KST 표기는 이 유틸에 위임한다** — 신규 `Intl.DateTimeFormat`/`toLocale*String` 생성 금지(`utils/__tests__/kst.test.ts` K4 텍스트 가드가 위임 대상 `DELEGATING_FILES`(`src/` 기준 상대 경로)로 잠근다). 위임 완료 = `PortfolioRiskCard` · `DailyReportTab` · `pages/Recommendations`(서식 `yyyy-MM-dd HH:mm:ss`, 빈 값 `'-'`). 나머지 사이트는 **사이트별 출력 스냅샷 승인 후 점진 이관**. `new Date(iso).getHours()/getFullYear()` 등 브라우저 로컬타임 추출 금지(도커 빌드 UTC / 다른 TZ 환경 어긋남). 백엔드 `_to_kst` 헬퍼와 동일 컨벤션.
- ⚠️ **타입 검사는 `npx tsc -b`** — 루트 `tsconfig.json` 이 `files: []` 솔루션 형식이라 `npx tsc --noEmit` 은 파일을 **0개** 검사한다. `GateLevel` 유니온 등 타입 계약은 `tsc -b`(= `npm run build` 1단계)만 잰다.

## 테스트 규약 (공통)

화면별 절에 흩어 쓰지 않고 여기 한 번만 적는다. 신규 카드·페이지·목을 만들 때 전부 해당한다.

1. **모든 `useQuery` 에 `retry: 1` 을 명시한다.** 전역 기본값이 있어도 카드마다 쓴다 — 백엔드 미실행 e2e 에서 ECONNREFUSED 재시도가 누적되면 spec timeout 이 된다. AST 가드 `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts`(카드 + `TARGET_PAGES` 페이지 전수).
2. **Playwright route 매칭은 LIFO** — "latest registered route wins". 구체 라우트는 wildcard **뒤**에 등록해야 이긴다. 가드 `tests/unit/e2e_mocks/test_api_mocks_routes_registered.py`(`..._specific_routes_registered_after_wildcard`).
3. **`frontend/src/api/*.ts` 의 엔드포인트와 `e2e/fixtures/api-mocks.ts` 의 route glob 은 정합해야 한다.** 가드 `_ast_api_mocks_coverage.test.ts`.
4. **Playwright glob 이 Vite 모듈 경로(`/src/api/*.ts`)와 겹치면 resourceType 가드 의무.** `**/api/logs*` 같은 glob 은 스크립트 요청까지 intercept 해 MIME 불일치로 모듈 로딩을 깨뜨린다.

   ```javascript
   await page.route("**/api/logs*", (route) => {
     // Vite 모듈 요청(src/api/logs.ts 등) 통과 — MIME 타입 불일치 차단
     if (route.request().resourceType() === "script") return route.continue();
     return route.fulfill({ json: envelope([]) });
   });
   ```

   `/api/strategies` e2e mock 은 **플랫 형식 하나만** 등록한다(내포 형식을 함께 두면 LIFO 로 그쪽이 이겨 `name = undefined` 가 된다).
5. 🔴 **목은 *의도한 계약* 이 아니라 *실제 응답* 을 담는다.** 목을 만들 때는 응답을 한 번 실제로 받아(curl·운영 로그) **그 모양 그대로 리터럴로** 박는다 — 생성기로 "그럴듯한" 값을 합성하지 않는다. 목 동기화 대상은 `frontend/src/test/handlers.ts`(MSW) · `frontend/src/test/factories.ts` · `e2e/fixtures/api-mocks.ts`(LIFO 정합) 셋이고, **백엔드 계약 테스트의 DB 스텁도 같은 규칙을 받는다**(`tests/contract/`).

   같은 원인(PG NUMERIC → asyncpg `Decimal` → pydantic v2 가 JSON **문자열**로 직렬화)으로 세 화면이 각각 오래 망가져 있었고, 매번 **모든 층의 목이 숫자를 먹여** 전 스위트가 초록이었다: 종목마스터 일봉 탭(`change_rate`, 흰 화면) · 거래내역 '가격'·'매매손익'(전 행 `-`) · 대시보드 '최근 자산'(천단위 구분 소실). 뒤의 둘은 예외조차 나지 않아 **화면만 조용히 빈다** — 로그에 아무것도 안 남으므로 목이 유일한 방어선이다.

   그래서 수치 렌더는 **방어 변환을 거친 값에만** 건다(`toNum`/`toSafeNumber` 계열이 숫자와 숫자 문자열을 모두 받고 진짜 결측만 `-` 로 남긴다). `typeof v === 'number'` 단독 판정과 미검증 값에 `toLocaleString`/`toFixed` 직접 호출은 금지다.
6. **골든 픽스처는 손으로 고치지 않는다.** `GET /api/strategies/params-schema` 목 2개(`frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts`)는 `src/engine/param_catalog.py` 와 7 전략 `DEFAULT_PARAMS` 에서 **기계 생성**한다. 카탈로그나 `DEFAULT_PARAMS` 가 바뀌면 생성기를 다시 돌린다:

   ```bash
   KIS_APP_KEY=x KIS_APP_SECRET=x KIS_ACCOUNT_NO=x SUPABASE_URL=http://x SUPABASE_KEY=x \
       python tools/test_fixtures/gen_param_schema_fixture.py
   ```

## OrderMonitor

- `pos.is_next_day=true` 일 때만 "청산" 배지 노출. 백엔드 `Position.is_next_day` 가 `_MULTIDAY_STRATEGIES`(**코드 정본 = `{donchian_swing, vcp_breakout, kojiro}`**) 분기로 멀티데이 전략은 항상 False. 다른 전략(momentum/VB/LTV/bull_flag) 기존 동작 유지

## ScanMonitor

- `phase` 라벨 (`PHASE_LABELS`): pre_nxt_wait / pre_nxt_trading / main_trading / krx_main_stopped / post_nxt_trading / post_nxt_stopped / recommending / log_analysis
- 헤더 직하단 활성 보드 배지: KST 시각 → SessionTracker `_BOARD_SCHEDULE` 매핑. 장 외 시간 "장 외 (08:00~20:00 외)"
- VB/LTV 탭 보드별 시가/타겟가: `BreakoutTarget.boards: Record<string, BoardTarget>` 활용. 활성 보드는 `font-semibold + ring`, 비활성 톤다운. 정렬·돌파 판정·근접 % 모두 활성 보드 기준. `BOARD_META` 한글 라벨/색상 매핑
- **BREAKOUT_KEYS 4종**: `volatility_breakout` / `long_tail_volatility` / `bull_flag_breakout` / `vcp_breakout`. BREAKOUT_LABELS "변동성 돌파" / "롱테일 변동성 돌파" / "눌림목 돌파" / "VCP 변동성 수축". BFB/VCP 도 `isBreakout` 분기 + 타겟 가격 테이블 재사용 (MAIN only 단일 보드)
- **활성 보드 자동 결정** (`activeBoardCode`): (1) 백엔드 응답 boards keys 가 1개면 그 키 자동 선택 (시각 매핑 무관, 백엔드 의도 진실의 원천) / (2) keys 여러 개면 KST 시각 매핑 (main > post_nxt > pre_nxt 우선) / (3) boards 빈 dict → KST 시각 fallback
- "최근 매수 신호" 표: `보드` + `타겟가` 컬럼 (`BuySignal.board?` / `target_price?` / `k?`)
- donchian_swing 탭: 단계별 통과 카운트 (`scan_stats`) 막대 + 후보 테이블 갭률·진입 상태 컬럼. 진입 상태: 보유 중/갭 스킵/장 시작 전/진입 시간 종료/진입 대기. "도움말 펼치기" 토글, `gap_skip_threshold` 동적 반영
- **"돌파" 라벨의 매매 컨텍스트** (`BREAKOUT_KEYS` 4종): `curPrice >= targetPrice` 분기에서 활성 보드 ∩ 전략 `tradable_boards` 검사. 교집합 ∋ → 빨강 "돌파". 교집합 ∅ → 회색 "돌파 (대기 — {보드라벨})" + `title` 툴팁 "이 전략은 X 에서만 매매". `tradable_boards` 미존재(백엔드 미반영) → 빨강 "돌파" fallback(안전 회귀). BFB/VCP 는 전용 컴포넌트가 진입 게이트로 대체한다.
- 인프라 표시(구독 커버리지·재구독·끊김 종목)는 **`KisAccountPoolCard` 소관**이다. ScanMonitor 는 필터링 가시성에 집중하고 `subscribed_count` 단순 카운트만 보존한다.

### STAGES 계약

`ScanFunnelBars` 가 그리는 전략별 STAGES 는 **live 백엔드 키만** 참조한다 — VB 5키 · LTV 6키 · momentum 6 · BFB 8 · VCP 8 · donchian 8. `scan_stats` 미반영 시 "아직 스캔 전" fallback(옵셔널 타입 가드로 백엔드 미배포 환경 호환).

- VCP 키는 `trend_filter_pass` / `pullback_pass` (백엔드 `_scan_stats` 키와 정합).
- "합집합" 단계 key 는 `universe_union`(진짜 union). `universe_candidates` 는 **시총+거래대금 컷 통과** 후 숫자이므로 step1 라벨을 "원천 유니버스 후보"로 쓰지 않는다.
- 백엔드 `_empty_scan_stats` 에 선언만 되고 세팅되지 않는 키(`price_filtered`/`mcap_pass`/`trade_amount_pass`)는 **프론트가 참조하지 않는다** — 참조하면 화면에 영원한 0 이 뜬다.
- 회귀 가드 `ScanMonitor.cycle175.test.tsx` · `ScanMonitor.cycle178.test.tsx`(정적 source 검증 — 죽은 키 0건 + step1 라벨 + VB 5키/LTV 6키 카운트).

### kojiro 탭 (`KojiroMonitor.tsx`)

`selectedStrategy === 'kojiro'` 분기가 전용 6패널을 렌더한다. 데이터 대부분이 `strategies.kojiro`(scan_stats/targets/buy_signals/positions_detail/params)에 이미 노출돼 있어 백엔드는 `get_targets_status` 에 `atr_ratio` 1키만 더한다.

① 상태 배너(`kojiro-darklaunch-banner`, **`kojiro.enabled` 조건부** — 활성=amber "실매매 진행" / 비활성=navy "관찰 모드", last_run_at) ② 대순환 사이클(`kojiro-stage-cycle`, 6스테이지 1→2→…→6↩1 + `targets.stage` 분포 `kojiro-stage-count-{s}`) ③ 유니버스 깔때기(`kojiro-scan-funnel` 9단계, `universe_union`→…→`final_prepared`, 0단계 rose) ④ 후보 그리드(`kojiro-candidate-{ticker}` — 종목명(`t.name || ticker`, 백엔드가 `_candidates[ticker]` 에 저장한 이름이라 **정산 후·주말에도 유지**) · stage 배지 · EMA 5/20/40 정배열 · ATR 밴드 게이지(`atr_ratio` or atr/prev_close, `params.atr_ratio_min~max`)) ⑤ 진입 이벤트(`kojiro-entry-feed`, buy_signals) ⑥ 보유 방어선(`kojiro-defense-{ticker}` — 4중 청산선 `buy−stop_atr×atr` / `high−trail_atr×atr` / `buy×(1+hard_stop_pct/100)` / stage3, **프론트 계산** targets.atr+positions+params, 활성 방어선 = 현재가 아래 max).

회귀 가드 `KojiroMonitor.test.tsx`(11) + `ScanMonitor.kojiro.test.tsx`(4).

### VCP/BFB 탭 (`BreakoutCandidateMonitor.tsx`)

`isBreakout` 을 `isVbLtv`/`isVcpOrBfb` 로 분기해 **VB/LTV 경로는 byte 동일 보존**하고 VCP/BFB 만 전용 컴포넌트로 간다. 패널 3:

- ⓪ **진입 게이트**(`breakout-entry-window`) — `params.entry_start~entry_end` KST 판정. VCP 09:05~14:30 / BFB 09:05~13:00 은 둘 다 MAIN 안이라 시간창 판정이 보드 판정을 포함한다.
- ① **구독 커버리지**(`breakout-subscription-coverage`) — `scan.subscribed_tickers` ∖ `scanned_tickers` 차집합. 미수신 종목은 `on_tick` 미발화 → `check_buy_signal` 자체가 호출되지 않는다(슬롯은 `BREAKOUT_LOW_CAP=25` 를 VB/LTV/BFB/VCP 4전략이 나눠 쓴다).
- ② **후보 그리드**(`breakout-candidate-row-{ticker}`) — 종목명/현재가/돌파선/거리%/손절선/측정목표(BFB)/거래량컷/상태. 돌파선 근접순 정렬, 미수신은 최하단. 상태 배지 `breakout-status-{ticker}` 우선순위 = 매수완료 > 쿨다운 D-n > 📵미구독 > ⏱m:ss 대기(BFB `breakout_seen_at`+`retention_minutes`) > 대기.

백엔드는 `get_targets_status` 에 키 **추가만** 한다(`name`/`prev_close`/`stop_line`/`measured_target`/`volume_threshold`/`bought_today`/`in_cooldown`/`cooldown_until`/`breakout_seen_at`/`retention_minutes`) — `strategy_registry` 가 덕타이핑 제네릭이라 registry·route 수정 0. ⚠️ **VB 호환 5키는 `scheduler._confirm_breakout_open_prices`(8영역) 소비라 제거 금지.** 회귀 가드 `BreakoutCandidateMonitor.test.tsx`(20).

## StrategyFunnel (`/strategy-funnel`)

전략별 조건검색 단계별 후보/탈락 종목 추적 페이지. 전략 dropdown + 날짜 picker + 단계별 expand 가능한 테이블 + 수동 trigger 버튼(`POST /api/strategy-funnel/snapshot`). 단계 클릭 시 `survived_tickers` 리스트 + `excluded_sample` 탈락 사유 표시. API `getFunnel / getRecentFunnel / triggerFunnelSnapshot`(`frontend/src/api/strategy-funnel.ts`). queryKey `['strategy-funnel', strategy_id, target_date]`.

- 단계명 옆 `조건` 툴팁(`data-testid="funnel-step-conditions-..."` + `title`) · 통과/탈락 종목 ticker 옆 종목명 병기(`SurvivedItem` 타입 + dict/string 분기) · 탈락 사유에 수치 포함(예: `"음봉 비율 35% > 30%"`).
- `FunnelSnapshot.is_provisional === true` 행은 단계명 옆 amber "잠정" 배지(`funnel-provisional-badge-{sid}-{step_no}`, title="21:00 저녁 잠정 캡처 — 익일 아침 마스터 델타 반영 전 (후보가 바뀔 수 있음)"). 운영자가 "밤에 본 후보 ≠ 아침 확정 후보" 를 인지하게 하는 것이 목적이다. 저녁 잠정 행은 **다음 거래일 날짜**로 저장되므로 날짜 picker 로 그 날짜를 골라야 보인다(기본 날짜는 오늘 그대로다). 회귀 가드 `StrategyFunnel.cycle171.test.tsx` · 문구 가드 `tests/unit/ast/test_cycle364_frontend_evening_wording.py`.
- **병목 강조 + 추이**: ① `funnel-bottleneck-banner` — 직전 단계 대비 **절대 감소 수** 최대 단계(⚠️ 감소'율'로 잡으면 막판 `7→0`(100%)이 `329→7`(97.9%)을 이겨 진짜 병목을 가린다. rows 는 DB `ORDER BY step_no` 보장) ② `funnel-bar-{sid}-{step_no}` 단계별 상대 막대 ③ `funnel-recent-trend` — `getRecentFunnel(strategy_id, 14)` 로 최종 단계 일자별 스파크라인 + 연속 0 배지. `target_date` 를 `Date()` 파싱 없이 slice 만 하므로 KST 규약 무관하게 안전. 로딩/에러/빈 데이터는 해당 섹션 안에서만 graceful(실패해도 단계별 테이블 정상). 회귀 가드 13.

## Settings

### 비중 슬라이더

- 하한선 = 보유 포지션 매수금액 비율. ⚠️ `min_weight` 는 **퍼센트 정수(0~100)** 다(`invested / total_asset × 100` 반올림) — 같은 응답의 `weight`(비율 0~1)와 **단위가 다르다**. 슬라이더 마커가 `left: {minW}%` 로 그대로 쓴다. 백엔드 라우트의 하한 검증은 별도로 비율끼리 비교한다
- `position_ratio` 는 "전략 내 종목당 비중" — 전략 할당 자금 기준 (순자산 전체 아님), 예상 매수 금액 헬퍼 표시
- **비중 단위 = 비율 `0.0~1.0`**: 로드는 `Math.round(s.weight * 100)` **단일 경로**다. 값 크기·합계로 단위를 추론하는 분기는 금지(금기와 이유는 루트 `CLAUDE.md` 「비중 단위 추론 변환 금지」). 저장은 퍼센트가 아니라 **비율 송신**(`weights[key] / totalWeight` 4dp + 잔차 `1 − Σ` 를 최대 항목에 흡수해 Σ=1.0 보장 → 백엔드 Σ≤1.0 가드 정합)
- **합계 경고 배너** `data-testid="weight-sum-warning"` — 판정 소스는 편집 중 퍼센트 합이 아니라 **서버 저장값 비율 합**(`strategies.reduce(s.weight)`). 편집 중 값을 쓰면 (a) 슬라이더를 내리는 정상 조작과 (b) 4dp→정수% 반올림 누적오차(전략 n개면 최대 ±n/2 %p)를 오염으로 오인한다. `|Σ−1| > 0.01` 이면 배너, **초과**면 비중 저장 버튼 `disabled` — 오염 상태에서 저장하면 overflow 재분배가 잘못된 비율을 보존한 채 Σ=1.0 으로 재정규화해 백엔드 `[weight_config_anomaly]` 탐지기를 **영구 침묵**시킨다. Σ<1 은 차단하지 않는다(운영자 고립 방지)
- **422 한글 노출** (`api/trading.ts::updateStrategyWeights`): 범위 위반은 axios 가 throw 하므로 2xx 본문 해석 경로가 못 잡는다 → `axios.isAxiosError && status===422` 분기가 `detail`(문자열 또는 배열 `[0].msg`)에서 메시지를 뽑고 pydantic 접두사(`Value error, ` / `Assertion failed, `)**만** 제거한다(`^[A-Za-z ]+, ` 같은 일반 패턴 금지 — 한글 본문이 잘린다). 미처리 시 "Request failed with status code 422" opaque. `!data.success` 가 던진 일반 Error 는 재포장 금지
- ⚠️ overflow 임계는 `serverWeightSum - 1 > 0.01` 형태로만 쓴다 — 동치인 `1.01` 리터럴은 AST 가드가 단위 추론 휴리스틱 부활로 간주해 금지한다. 가드 `_ast_weight_unit_guard.test.ts`(`1.01` 리터럴 0건 + `Math.round(s.weight)` 0건) / 회귀 `Settings.weightUnits.test.tsx` · `api/__tests__/trading.test.ts`

### `StrategyParamsEditor` — 파라미터 편집기 (카탈로그 기반, 유일한 구현)

`GET /api/strategies/params-schema` 응답만으로 렌더한다. **화면은 파라미터 키를 하나도 모른다** — 라벨·단위·범위·선택지·위험도를 전부 응답에서 읽는다. 키를 화면이 들고 있으면 백엔드가 키를 늘려도 화면은 모른다. 회귀 가드 `components/__tests__/_ast_param_key_hardcode.test.ts`(키 리터럴 0건).

- **포맷 분기는 키 이름이 아니라 `type`/`unit` 으로** 한다 — 접미사 `_pct` 가 퍼센트와 비율 두 규약에 모두 쓰이므로 이름 기반 추론은 폐기된 단위 추론 휴리스틱의 재현이다.
- **저장은 변경분만 보낸다.** 패널이 연 키 전체를 매번 보내면 그중 한 키의 범위 위반이 전략 전체 저장을 422 로 막는다.
- 배지 5종 = identity(리스크 정체성 상수) · autotune · deprecated · inactive · unbounded. 주요 testid = `strategy-params-editor` / `-row-{key}` / `-current-{key}` / `-default-{key}` / `-reset-{key}` / `-diff` / `-warnings` / `-save` / `-market-warning`(KRX 메인 시간 경고, `isKrxMainSession`).
- 스키마는 패널을 **열 때만** fetch 한다(`Settings.tsx` 의 `paramsStrategy` state, null = 닫힘).
- `updateStrategyParams(key, params)` 의 `params` 타입은 `Record<string, StrategyParamValue>`(`number | string | string[] | null`).

### `ExchangeBoardRow`

- 전략별 `exchange` 라디오 + `tradable_boards` 체크박스 5개(`pre_nxt` / `krx_open` / `main` / `krx_after` / `post_nxt`, post_nxt 선택 시 amber 강조). 0개 선택 차단. 바뀐 키만 송신한다.
- **`exchange` 선택지는 KRX·NXT 둘뿐이다.** 09:00~15:30(정규장)·16:00~20:00(애프터)은 백엔드 시각 라우팅(`order_engine.py::_route_exchange_by_clock`)이 거래소를 정하므로, 이 선택지는 그 라우팅 밖 구간(프리장 08:00~09:00 등)에만 실제로 적용된다. **이미 `SOR` 로 저장된 전략은 값을 지우지 않고** 폐기 값임을 알리는 회색 안내로 보여준다(`isRetiredExchangeValue`) — 값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다.
- **환경 가드**: `useTradingStatus().env` 로 모의(`!== 'real'`) 시 NXT 라디오 disabled + 회색 처리 + 저장 시 추가 검증
- 어느 전략이든 `post_nxt` 활성이면 상단 amber 야간 매매 경고 배너

### `CashUsageRatioCard`

비중 슬라이더 하단. range **0~100**, step 5 슬라이더 + `data-testid="cash-usage-ratio-percent"` % 표시. 🔴 **하한 0 은 백엔드 수용 범위(`_CASH_USAGE_RATIO_MIN = 0.0`)와 맞춘 값이다** — 화면 하한이 백엔드보다 높으면 자동 조정이나 curl 이 저장한 값을 화면이 표현하지 못해 **UI 로 되돌릴 수 없는 상태**가 생긴다(레짐 defensive 가 만드는 0.25 가 그 사례). 0% 선택 시 `data-testid="cash-usage-ratio-zero-warning"` 인라인 경고 — 0% 는 신규 매수 전면 중단이라 실수와 의도를 구분해야 한다. GET `/api/strategies/system/cash-usage-ratio` 초기 로드, 저장 버튼 클릭 시 PUT (debounce 없음 — 명시 commit). 응답 ratio(서버 5% 보정) 동기화. 안내 "다음 영업일부터 반영" (text-amber-700). queryKey `['cashUsageRatio']`.

### `KisQuoteAccountsCard`

`IntegrationToggleCard` 직하. 보조 KIS 시세 계좌 등록/제거/활성화 토글:
- 표 컬럼: label / 환경 배지(`real`=red / `vts`=emerald) / app_key 마스킹 / app_secret_masked(`****1234`) / 등록일(KST) / `quote-account-toggle-{id}` active 토글 / `quote-account-delete-{id}` 삭제
- 빈 목록: `quote-accounts-empty` 안내 "등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 41 × (1 + N) 으로 확대"
- 등록 폼: `quote-account-input-label` / `quote-account-input-kis-env-real|vts` 라디오 / `quote-account-input-app-key` / `quote-account-input-app-secret` (**`type=password`** + `autocomplete=new-password`). 클라이언트 검증: 빈값 거부 + label 형식 `^[A-Za-z0-9\-]+$` 거부 → `quote-account-form-error` + POST 미발사
- `quote-account-submit` → `ConfirmModal` 이중 확인 (등록·active 토글·삭제 모두 안내 분기)
- **app_secret 평문 잔존 차단**: 등록 성공 시 `setForm` 빈 값으로 secret state 즉시 클리어. UI 는 `app_secret_masked` 만 참조
- 에러 메시지 분기: `axios.isAxiosError` status (`409: label 중복` / `422: 검증 실패` / 그 외)
- API: `frontend/src/api/kis-quote-accounts.ts` + `types/kis-quote-accounts.ts`. 백엔드 `/api/integrations/quote-accounts/*`. queryKey `['kis-quote-accounts']`, staleTime 30s

### `IntegrationToggleCard`

`CashUsageRatioCard` 직하. 4 토글 + 매수 가드 영역.

**토글 4종** (`ConfirmModal` 이중 확인):
- `data-testid="toggle-dkstock-regime"`: 매크로 레짐 활성(출처 = 자체 `macro` 컨테이너. testid·키는 DB 행과 짝이라 유지). 활성화 후 3s `data-testid="fetch-progress-dkstock-regime"` 진행 표시 + marketRegime invalidate
- `data-testid="toggle-kis-mcp"`: 외부 백테스트 서버 활성 (자문 시점만 사용)
- `data-testid="toggle-auto-regime-adjust"`: 매크로 레짐 → cash_usage_ratio 자동 갱신
- **`data-testid="toggle-auto-apply"`**: AI 자문 자동 적용. 기본 OFF. ON 시 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터 자동 적용. DB-only (`auto_apply_enabled` 키). API: `getAutoApply/setAutoApply` — `/api/integrations/auto-apply`
- `data-testid="source-badge-{key}"` 배지: source='db' 파란 `DB` / 'env' 회색 `env` (fallback 가시화)
- API 에러: `data-testid="toggle-error-{key}"` 빨간 박스 + "잠시 후 재시도하세요"

**`BuyBlockSection`** — 🔴 **표시·관찰 전용이다.** 레짐은 매수를 차단하거나 축소하지 않는다(매수 가드는 사이클 I 에서 제거됐고 `buy_block_mode` 는 표시용으로만 남았다). 화면의 "매수 차단 중" 문구는 관찰 판정일 뿐 실제 차단이 아니다.
- 모드 select `data-testid="buy-block-mode-select"` (OFF/WARN/SOFT/HARD). 변경 시 `ConfirmModal` 이중 확인
- 임계 슬라이더 3: `buy-block-vix-slider` (10~50, 기본 25) / `buy-block-fg-high-slider` (50~100, 기본 85) / `buy-block-fg-low-slider` (0~50, 기본 15)
- `buy-block-defensive-toggle` 체크박스 (regime=defensive, 기본 ON)
- `buy-block-thresholds-save` 저장 — 슬라이더+체크박스 한 번에 PUT (ConfirmModal 없이 즉시)
- `buy-block-reasons` 사유 리스트 (4건까지 list-disc + amber)
- **무력 배너 `buy-block-guard-inert`**: `data.guard_inert === true` 시 mode 행 직후·reasons 위에 red 배너(`bg-red-100 text-red-800 border-red-300`, amber 사유보다 강조). `BuyBlockState` 타입에 `data_available`/`guard_inert`. 매크로 데이터 미유입으로 가드가 설정만 되고 무력화된 상태(false sense of protection)를 가시화한다
- SOFT 모드: `buy-block-soft-multiplier` 안내 / GET 500: `buy-block-error` graceful
- API: `getBuyBlock / setBuyBlock`. 백엔드 `/api/integrations/buy-block` GET/PUT. queryKey `['integration', 'buy-block']`, staleTime 30s

### `PriceFilterCard`

**WebSocket 구독 대상 필터.** `BuyBlockSection` 직하. 매도/익일청산/손절 영향 0.

- **7 testid**: `price-filter-card` / `price-filter-min-slider`(0~20,000원, step 1,000) / `price-filter-max-slider`(0~2,000,000원, step 50,000) / `price-filter-save-button` / `price-filter-save-toast` / `price-filter-validation-error`
- 단일 필터다(`min=0 or max=0` 비활성). 모드 select 는 없다 — `PriceFilterMode` 타입·`mode` 필드를 되살리지 않는다
- 권장값 툴팁: 저 5,000원 / 고 1,000,000원. 디폴트 0/0 = 비활성
- **즉시 반영**: 저장 클릭 → `updatePriceFilter()` PUT → 백엔드 `scanner.invalidate_price_filter_cache_scanner()` 즉시 호출 → 60s 캐시 도중에도 반영. **자동 unsubscribe 0 발화**(다음 `_scan_loop` 5분 자연 delta, KIS LMS chain 차단)
- **클라이언트 검증**: 음수 / `min_price > max_price`(둘 다 >0 일 때) → `price-filter-validation-error` 표시 + PUT 미발사
- API: `getPriceFilter / updatePriceFilter`. 백엔드 `/api/system/price-filter` GET/PUT, `ApiResponse<PriceFilter>` 래퍼 → 프론트 `data.data` 추출. queryKey `['system', 'price-filter']`. PUT body 에 extra key 전달 시 422(`ConfigDict(extra="forbid")`)
- 안내 배너: "**WebSocket 구독 대상 필터** — 임계 외 종목은 시세 구독 자체 차단. **보유/익일청산 종목은 절대 제외 안 됨**"
- 회귀 가드 4 vitest (렌더 + mode select 미존재 / 슬라이더 / 저장+toast / max<min)

### `TradeAmountFilterCard`

**거래대금 동행 필터.** `PriceFilterCard` 옆(Settings "WebSocket 구독 대상 필터" 영역).

- **4 testid**: `trade-amount-filter-card` / `trade-amount-filter-min-slider`(0~100억원 = 0~10_000_000_000, step 1억원 = 100_000_000) / `trade-amount-filter-save-button` / `trade-amount-filter-save-toast`
- **권장값 마커 3 버튼**: "1억"(100_000_000) / "5억"(500_000_000) / "10억"(1_000_000_000) — 슬라이더 value 직접 갱신
- **즉시 반영**: 저장 → PUT → 백엔드 `scanner.invalidate_trade_amount_filter_cache_scanner()` 즉시 호출. 자동 unsubscribe 0 발화
- API: `getTradeAmountFilter / updateTradeAmountFilter`(`frontend/src/api/trade-amount-filter.ts` + `frontend/src/types/trade-amount-filter.ts`). 백엔드 `/api/system/trade-amount-filter` GET/PUT, `ApiResponse<TradeAmountFilter>` 래퍼. queryKey `['tradeAmountFilter']`. PUT body extra key → 422 / 음수 → 400
- **안내 배너 3문구 (명시 의무)**: "**거래대금 동행 필터** — 임계 미만 종목은 WebSocket 구독 자체 차단" / "보유/익일청산 종목은 절대 제외 안 됨" / "**09:00 직후 거래대금 미반영 종목은 graceful 통과**"
- MSW handler: `GET /api/system/trade-amount-filter` → `{ min_amount: 0 }` + `PUT` 요청 body 반영
- 회귀 가드 4 vitest (`TradeAmountFilterCard.test.tsx`): 렌더 / 슬라이더+저장 PUT body / 권장값 마커 / 안내 배너 문구

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

- 상단 인라인 4 컨트롤: 시장 select(전체/KOSPI/KOSDAQ) · 시총 min(억원, placeholder "0 = 전체") · 거래대금 min(억원) · 종목명 부분 검색(한글 IME composition 가드) + 초기화 버튼
- 400ms 디바운스(`useEffect` setTimeout) · URL `useSearchParams` 동기화(새로고침 후 필터 유지 + 공유 가능) · 필터 변경 시 offset=0 reset
- 컬럼(종목명·시장 다음, NXT/정지/관리 *전*): 현재가(`raw.stck_prpr`) / 전일대비(`raw.prdy_vrss`, 부호 색상) / 시가총액(`raw.hts_avls` 백만원 → 억원) / 거래대금(`raw.acml_tr_pbmn` 원 → 억원). 헬퍼 `formatPrice` / `formatMarketCap` / `formatTradeAmount`, 값 없음/0/null → "—"
- API/타입: `fetchList(params: StockMasterFilterParams): Promise<StockMasterListResponse>` · `StockMasterListResponse {items, total, limit, offset}` envelope · `StockMasterFilterParams {limit, offset, market?, min_market_cap?, min_trade_amount?, name_substr?}`. 페이지네이션은 `total` 기준

### (3) 새로고침 4 버튼 + `RefreshProgressBanner`

- 버튼 4: "지금 새로고침"(blue) / "기본정보 새로고침"(`stock-master-refresh-basics-button`, emerald) / "일봉 새로고침"(`stock-master-refresh-daily-button`, amber) / "마스터 새로고침"(`stock-master-refresh-master-button`, deep purple) — 각각 POST `/api/stock-master/{...}/refresh`, **fire-and-forget**
- `onSuccess`: "{작업} 새로고침 시작 — 진행 상황은 상단 배너 참고" + `invalidateQueries(['refresh-progress'])` 즉시 호출. `onError`: 409 → "{작업} 이미 진행 중 — 상단 배너 참고" / 그 외 → "KIS API 일시 결함 — 잠시 후 재시도". `retry: false`(중복 trigger 방지)
- `RefreshProgressBanner.tsx` — `useQuery({queryKey: ['refresh-progress'], queryFn: fetchRefreshProgress, retry: 1, refetchInterval: 동적})`, running 5초 / idle 60초. `TASK_ORDER = ['universe', 'basics', 'daily', 'master']`, `TASK_LABELS['master'] = '종목마스터 일일 갱신'`. status='running' 이거나 'completed/failed' 직후 3초 이내인 작업만 표시(자동 fadeout)하고, fadeout 시점에 `invalidateQueries(['stock-master-stats'])` + `['stock-master-list'])` 로 즉시 갱신한다
- testid: `refresh-progress-banner` / `refresh-progress-{row,status,bar,counter,error}-{taskKey}`
- 타입: `RefreshTaskKey = 'universe' | 'basics' | 'daily' | 'master'` · `RefreshStatus = 'idle' | 'running' | 'completed' | 'failed'` · `RefreshProgress`(10 키) + `AllRefreshProgress` + `RefreshStartedResponse { status: 'started', task_key }`

### (4) detail 모달 — 상세 / 일봉 2 탭

- 상세 탭: `FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 카테고리 배치 + `HIGHLIGHT_KEYS` 핵심 키. `master_raw` ~30 키 한글 매핑(진입 차단 7 · 시총 · 재무 5 · 지수편입 6 · 시장 영역 4 · 기타 7) + 시세 6 키(`hts_avls`·`acml_tr_pbmn`·`bfdy_clpr`·`lstn_stcn`·`acml_vol`·`prdy_vrss`)
- 🔴 `DetailModal` 의 `useQuery` 는 **`placeholderData: initialData`** 다. `initialData` 로 주면 TanStack Query 가 fresh 로 판정해 `fetchDetail` 재호출이 막히고 신규 매핑 키가 통째로 누락된다
- 일봉 탭: `useQuery({queryKey: ['stock-master-daily', ticker], queryFn: () => fetchDaily(ticker, 30), enabled: !!ticker, retry: 1, refetchInterval: 60_000})`. 마지막 30 영업일 OHLCV = `bas_dd / open_price / high_price / low_price / close_price / volume / change_rate`
- 🔴 **방어 변환 3 헬퍼**(`StockMaster.tsx`) — `toSafeNumber(unknown): number | null`(숫자·숫자형 문자열 → 유한 number, `null`/`undefined`/**빈 문자열**/비숫자/`NaN`/무한대 → `null`. 빈 문자열 가드가 `Number("")===0` 오판을 막는다) · `formatSafeCount`(OHLCV 셀, 실패 시 `'—'`) · `formatSafeChangeRate`(색상 분기도 변환 **후** 값 기준, 클래스 `text-red-600`/`text-blue-600`/`text-gray-500`). **미검증 값에 `toFixed`/`toLocaleString` 직접 호출 금지** — 렌더는 항상 이 세 헬퍼가 돌려준 값에만 건다
- **404 vs 500 렌더 분기** — `axios.isAxiosError(error) && error.response?.status === 404`(`DetailModal.is404` 선례). 404 = "적재 대상 아님"(testid `stock-master-daily-notice`, 회색), 그 외 500·네트워크 = testid `stock-master-daily-error`(빨강). **일봉은 전 종목 적재가 아니다** — 정상 미적재를 오류로 보이게 하지 않는다
- 타입(`types/stock-master.ts::StockMasterDailyRow`) — `change_rate: number | string`, `prtt_rate?: number | string`(같은 `NUMERIC(8,4)` 계열이라 문자열로 올 수 있다). migration 033 컬럼 **14 필드 전수**를 타입에 명시한다(렌더는 8개만 쓰지만, 타입이 나머지를 숨기면 "응답에 없는 필드"로 오해돼 다음 사람이 또 목을 실제와 다르게 만든다). `bas_dd` 는 `DATE` 컬럼이라 직렬화가 `YYYY-MM-DD` 다
- ⚠️ `StockMaster` 전체에는 아직 `ErrorBoundary` 가 없다(일봉 탭 렌더만 방어). 같은 계열 결함이 다른 탭에 잠재한다 — 후속 B-4(`_workspace/00_URGENT_WORKLIST.md`)

### (5) 변경이력 탭

- 타입 `StockMasterHistoryItem`: `{ticker: string, seq: 0 | 1, change_type: 'INSERT' | 'UPDATE' | 'DELETE', raw: Record<string, unknown> | null, changed_at: string}`. `id`/`before_raw`/`after_raw`/`'TTL_REFRESH'` 는 스키마에 없다 — 되살리지 않는다
- 4 컬럼: 스냅샷(`seq===0 ? '최신본' : '직전본'` 배지, seq0=indigo / seq1=gray) / 변경일시(KST) / 변경유형(`CHANGE_TYPE_COLORS` 배지) / raw 스냅샷(`<CollapsiblePre label="raw" data={item.raw} />`, null 시 "—")
- **seq ASC 정렬**: `historyItems.sort((a, b) => a.seq - b.seq)` — UPDATE 시 seq0/seq1 의 `changed_at` 이 동일(`now()`)이라 changed_at DESC 만으론 순서가 비결정이다. row `key` = `${ticker}-${seq}`

### (6) 신규 데이터 추가 시 UI 동기화 절차 (영구 가드)

`stock_master` 컬럼 / `raw` JSONB 키 / `stock_master_daily` 컬럼 추가 시 **반드시** 동기화:

1. `frontend/src/types/stock-master.ts` interface 갱신
2. `frontend/src/api/stock-master.ts` 호출 영역 갱신
3. `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 추가
4. `CATEGORY_KEYS` 적정 카테고리 배치
5. 핵심 키면 `HIGHLIGHT_KEYS` 추가
6. 진단 영역이면 `get_stats()` 응답 + 카드 1개 추가
7. `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합
8. 회귀 가드 추가 (`StockMaster.test.tsx`)

⚠️ 이 8단계는 "신규 컬럼·키를 UI가 놓치지 않는다" 만 보장한다. **목이 실제 응답 타입을 흉내 내는지는 검사하지 않는다** — 「테스트 규약」 5를 함께 지킨다.

### (7) 회귀 가드

`StockMaster.test.tsx`(8 카드 · 신규 매핑 키 라벨 · highlight · stats 응답 정합 · 일봉 탭 · 변경이력 seq/raw · 가이드라인 영속) · `StockMaster.dailyTab.cycle266.test.tsx`(방어 변환 3 헬퍼 단위 + 404/500 렌더 분기) · `test_cycle266_daily_route_serialization.py`(백엔드, **직렬화된 JSON 본문**의 타입을 잰다) · `test_cycle266_mock_string_change_rate.py`(목 5행이 문자열·숫자 혼합 + `YYYY-MM-DD` 인지 정적 대조) · `e2e/stock-master.spec.ts::G-E2E-9`(실브라우저 일봉 탭 + 문자열 등락률 `+1.20%` 변환 + `NaN`/`—` 부재).

## History (`/history`)

두 탭:
- 주문체결내역: `TradeHistoryGrid` (raw 행)
- 매매손익: `TradePnLGrid` (`/api/history/pnl` — 매수·매도 페어, closed/open 사이클). 12 컬럼 + 전략 뱃지. open 행은 매도 컬럼 "—" + "(미실현)" 라벨, emerald-50 배경. 시세 미수신 "(미실현 시세 대기)". 전략 select 7종(kojiro `고지로 대순환` 포함). 그리드 상단 실현손익 요약 바(`pnl-summary`) — `data.summary`(슬라이스 전 전체 closed 페어 집계) 기반 실현 합계(`pnl-summary-realized`, 이익 red/손실 blue)·손익율·승/패/보합·승률·현재 전략 필터 라벨. summary 부재 시 0 graceful

### AI 매수평가 점수 배지 + 상세 팝업

두 그리드의 각 행 맨 오른쪽에 "AI 자문" 열이 붙고, **버튼 왼쪽에 점수 배지가 선다** — 점수는 팝업을 열지 않고 목록에서 바로 읽는다.

- **점수 배지** (`components/LlmScoreBadge.tsx`) — `resolveLlmScoreTone(summary)` 순수 함수가 `{tone, text}` 를 내고 배지가 그것을 `data-tone` 으로 노출한다. 🔴 **판정의 정본은 서버가 그때 기록한 `would_block` 이고 화면이 `score >= min_score` 를 다시 계산하지 않는다** — 임계(`min_score`)는 전략 파라미터라 나중에 바뀌고, 재계산하면 평가 당시엔 통과였던 기록이 오늘 임계로 재판정돼 **과거를 거짓으로** 말한다. `would_block` 이 `null`/부재인 옛 기록만 점수 비교로 폴백한다. 🔴 **세 결측 상태를 접지 않는다** — 기록 없음 `·`(`tone='none'`) / 평가 실패 `–`(`tone='failed'`, `result==='failed'` 또는 `score==null`) / 점수 있음(`pass`|`block`). "평가 안 함" 과 "평가 실패" 를 한 칸으로 접으면 migration 043 이 실패 행을 남기는 이유가 화면에서 사라진다. 🔴 **0점을 결측으로 접지 않는다**(`if (!score)` 로 짜면 0점 = 가장 나쁜 평가가 "기록 없음"이 된다). `title` 에 점수와 기준을 **둘 다** 담는다 — 하나만 담으면 맞바꿈이 드러나지 않는다. `matchedCount > 1` 이면 `+n` 과 "첫 매수 기준" 을 밝힌다(안 밝히면 운영자가 그 숫자를 페어 전체의 대표값으로 읽는다). **네트워크 호출 추가 0** — 이미 배치로 받아 둔 `summary` 를 렌더할 뿐이다.
- **파일 4** = `components/LlmScoreBadge.tsx`(점수 배지 + `resolveLlmScoreTone`) · `types/llm-evaluation.ts`(`LlmEvaluationSummary` 10키 → `LlmEvaluation` 이 extends 해 상세 53키 · `LlmEvaluationSummaryMap`) · `api/llm-evaluations.ts`(`getLlmEvaluationSummaries(orderNos, tradeDate?)` 배치 · `getLlmEvaluation(orderNo, tradeDate?)` 단건 — **try/catch 금지**: axios 오류를 React Query 로 흘려야 화면이 404(회색 안내)와 500·네트워크(빨강 오류)를 가른다) · `components/LlmEvaluationModal.tsx`(팝업, 신규 의존성 0 · `<pre>` 원문 · `dangerouslySetInnerHTML` 금지).
- **버튼 활성 판정은 배치 1요청**이다 — 행마다 개별 조회하면 페이지당 20~30 요청이 나간다. 요약 맵의 키는 **`"<trade_date>|<order_no>"` 복합 키**(라우트 `summary_key()` 와 같은 규약)이고 조회는 `findLlmSummary(summaries, tradeDate, orderNo)` 로 한다. 그 조합의 키가 있으면 활성, 없으면 비활성(회색) + 툴팁 — 사유는 `llmSummaryDatesFor(summaries, orderNo)` 로 갈린다("평가 기록 없음" vs "다른 날짜(…)의 평가 기록"). 기록 없는 조합은 응답에 **키 자체가 없다**(`null` 값 아님).
- 체결 그리드(`TradeHistoryGrid`)는 **BUY 행의 `order_no`** 기준, 손익 그리드(`TradePnLGrid`)는 **`buy_order_nos`** 기준(한 페어가 매수 주문 2건 이상이면 라벨에 `AI 자문 (n)`, 팝업이 주문별 목록으로 n개를 나란히 보여준다). `pair_key`(= `strategy:ticker:첫 매수 order_no`)가 버튼 testid 이고 `null` 이면 비활성.
- ⚠️ **KIS 주문번호(ODNO)는 하루 단위로만 유일하다** — 활성 근거는 **그 행의 매수일로 조회한 키가 있는가** 하나이고, 상세도 반드시 날짜와 함께 묻는다(빼면 라우트가 "가장 최근 1건" 을 골라 같은 번호가 재사용된 **다른 거래의 평가**를 띄운다 — 회귀 가드 F25b).
- 팝업 내용 = 점수/임계/차단여부(`would_block`) · 사유(rationale) · 핵심 위험 · 무효화 조건 · 지표 요약 · 주문 스냅샷(주문가·수량·목표가·보드) · 모델/토큰/비용/지연 · 원문 입력 payload(접기). **`result==='failed'` 기록은 오류가 아니라 정상 기록**이며 실패 사유를 크게 보여 준다(`llm-eval-failed`) — "평가 안 함" 과 "평가 실패" 를 구별하는 것이 목적이다.
- 계좌번호는 **마스킹된 값만**(`account_no_masked`, 앞 4자리 + `****`) 화면에 오르고 타입에 원문 키가 없다 — 이 표면은 리포터 키로도 읽힌다. 숫자는 전부 방어 변환(`toSafeNumber`), 시각은 전부 `timeZone:'Asia/Seoul'` 명시.
- 목 3곳 모두 배치 응답을 **복합 키**로 만든다 — 주문번호 단독 키로 만들면 목이 실제 응답 형태를 담지 않아 화면이 전부 비활성인데도 초록이 된다. 헬퍼 가드 = `src/components/__tests__/llmEvalKey.cycle276.test.ts`(키 형식·날짜별 구분·두 그리드의 직접 인덱싱 0건).

## Logs (`/logs`) — 통합 메뉴

탭 컨테이너 `pages/Logs.tsx` + URL 쿼리 `?tab=system|daily-report` (기본 `system`, 알 수 없는 값 fallback). 두 탭 모두 `data-testid="logs-tab-{key}"` + `role="tab"` + `aria-selected`. 로그 뷰어는 여기에만 있다(Dashboard 에는 없다).

### 시스템 로그 (`SystemLogsTab.tsx`)

`from_date / to_date` 분리 date input(기본 KST 오늘) + 적용 + 레벨 토글(전체/INFO/WARNING/ERROR/CRITICAL) + 페이징(1-base, size 50). 자동 새로고침 3s 는 **오늘 + page=1 + 검색 모드 아닐 때**만 활성. KST 강제 — `Intl.DateTimeFormat('en-CA', timeZone: 'Asia/Seoul')` 으로 today 계산. 클라이언트 `from_date>to_date` 가드 → `data-testid="system-logs-date-error"`. API `fetchLogs(filter)`.

- **검색 박스**(필터 바 *위*): `system-logs-search-input` + Enter 키 + `system-logs-search-button` + 검색 모드 진입 시 `system-logs-search-clear`. 검색 모드 동안 페이징/자동 새로고침 비활성(`/api/logs/search` 단일 limit 200 응답). API `searchLogs({q, level, start, end, limit})` — 현재 입력된 level/from_date/to_date 를 함께 보낸다. 결과 0건 → "검색 결과가 없습니다."(페이징 모드의 "로그가 없습니다." 와 분리). `has_more=true` → `system-logs-search-has-more` amber 배너

### 일일 로그 분석 (`DailyReportTab.tsx`)

좌측 영업일 리스트(최근 30일) / 우측 summary + findings 카드(severity + category 칩) + 원본 메트릭 접기. "지금 분석 실행" 버튼 → `POST /api/log-reports/run`(영업일당 1건 UNIQUE).

- **`ext_*` 6컬럼 표시**: `daily_log_reports.ext_provider/ext_model/ext_summary/ext_findings/ext_report_md/ext_created_at`(전부 NULL 허용)을 매일 20:20 KST Claude 루틴이 `POST /api/log-reports/{date}/external` 로 채운다. `GET /api/log-reports*` 는 SELECT * 라 이미 응답에 포함 — `LogReportItem` 타입에 6개 선택 필드로 1:1 추가(백엔드 필드명 = TS 속성명 원칙)
- **표시 규칙**: `ext_summary` 또는 `ext_findings`(비어있지 않음) 존재 시에만 `data-testid="ext-analysis-card"` 블록을 OpenAI 총평 블록 **위에** 렌더 — 헤더 "{target_date} Claude 분석" + 우측 "생성 {ext_created_at} · {ext_provider} · {ext_model}"(각 필드 null 은 그 조각만 생략) + 본문 `ext_summary`(`whitespace-pre-line`, `data-testid="ext-summary"`) + "개선 항목 (N건)" 을 기존 `FindingCard` 재사용으로 severity 정렬 렌더(key 접두 `ext-`) + `ext_report_md` 있으면 접이식 "상세 리포트"(`data-testid="ext-report-md-toggle"`) 안에 `<pre className="whitespace-pre-wrap text-xs …">` 원문 그대로
- 🔴 **마크다운 렌더 라이브러리 추가 금지**(의존성 0) — 운영 리포트는 신뢰 출처 고정 텍스트라 서식보다 원문이 감사에 유리하고, `<pre>` 는 XSS 표면(`dangerouslySetInnerHTML`)을 열지 않는다
- **파리티 계약**: ext 6필드가 전부 없는 행은 `hasExtAnalysis()` 가 `false` 라 블록 자체가 렌더 트리에 없다 — 기존 OpenAI 총평/findings/원본 메트릭 DOM 은 byte 동일. 좌측 날짜 목록은 `ext_summary` 있는 행에만 배지 "Claude"(`data-testid="ext-badge-{id}"`)
- **항목 내부 정규화**: `ExternalReportIn.findings`(백엔드)는 항목 내부를 검증하지 않는 `list[dict]` 라 `ext_findings` 는 임의 형태가 그대로 온다. `sortedExtFindings` 산출 시 `normalizeExtFinding`(같은 파일)이 severity ∉ `{high,medium,low}` → `medium`, category ∉ 9종 → `etc`, title/detail/suggestion 비문자열은 `JSON.stringify` 강제, title 또는 detail 이 빈 문자열이면 항목 **드롭**. 정규화 없이 객체를 자식으로 렌더하면 "Objects are not valid as a React child" 로 탭 전체가 빈 화면이 된다
- **레거시 `findings` 는 정규화 대상이 아니다**(백엔드 `log_analysis_engine._validate_report` 가 이미 검증) — 대신 `ReportCard` 를 `ReportCardBoundary`(같은 파일, class error boundary, `key={report.id}` 로 리포트 전환 시 에러 상태 리셋)로 감싸 예상 밖 예외가 나도 `data-testid="report-card-error"` 카드 하나만 대체되고 좌측 날짜 목록·탭은 살아남는다
- **휴장일 배지 (cycle366 P6)**: `report.metrics?.report_accuracy?.market_closed === true` 일 때만 총평 카드 헤더에 회색 배지(`data-testid="report-holiday-badge"`, "휴장일" + 툴팁 "거래·로그 0건은 결함이 아니라 정상")를 렌더한다 — 휴장일의 0건 통계를 결함처럼 보이지 않게 한다. `report_accuracy` 가 없는(구버전) 행·`trading_day: null`("모름")·`market_closed: false` 는 배지를 그리지 않는다. `LogReportMetrics.report_accuracy`(`types/log_reports.ts::LogReportAccuracy`)는 옵셔널이라 부재해도 크래시하지 않는다.
- 회귀 = `components/__tests__/DailyReportTab.ext.test.tsx`(파리티·렌더·토글·배지·타입 가드 + severity 정렬 뮤테이션 가드 + 정규화 3 + error boundary) + `DailyReportTab.holiday.test.tsx`(휴장일 배지 4케이스)

## Recommendations (`/recommendations`)

**카드 DOM 순서**: 자산 배정 → BacktestComparison → 분석 통계 → 추천 근거 → 로직 자문 → 파라미터.

- **자산 배정 카드** (`data-testid="weight-card-{id}"`, `recommended_weight != null` 시, **최상단**): 현재→추천 weight + 변경량 (%p, 이익색/손실색) + `weight-apply-checkbox-{id}` 체크박스. 체크 시 `applyMutation` body 에 `apply_weight: true`. 적용 후 `applied_weight` 표시 + amber 안내 "다음 영업일부터 반영"
- **`weight_reasoning` 영역** (`data-testid="weight-reasoning-{id}"`, weight-card 내부 `bg-amber-50 border-amber-200 max-h-32 overflow-y-auto whitespace-pre-wrap`): `rec.weight_reasoning` truthy 시만 렌더 (1000자 이내, 백엔드 truncate). 비중 변경 사유를 통합 `reasoning` 과 분리
- **로직/파라미터 자문 카드** (`data-testid="code-review-card-{id}"`, `code_review_notes != null` 시): 자유 텍스트 (whitespace-pre-wrap, max-h-64 + overflow-y-auto). 자동 적용 없음. 적용 버튼은 params 키 0개여도 weight 체크박스 ON 이면 활성 — 단독 weight 적용 가능
- **`BacktestComparisonCard`** (`backtest_summary != null` 시 자산 배정 카드 *위*): (a) 외부 MCP YAML DSL 지원 3종(momentum/VB/donchian)은 좌(현재)/우(추천) 메트릭 8종 비교 + 차이값 칩(이익색/손실색) + `data-testid="backtest-card-{strategy}"`. (b) 폴백 4종(LTV/bull_flag/vcp/kojiro)은 "외부 MCP YAML DSL 미지원 — 로컬 백테스트 어댑터 적용 대기" 안내. `status=running` 시 로딩 스피너. **`max_drawdown` 양수(절대값) 컨벤션**: `METRIC_SPECS.max_drawdown.diffSignInverted=true` — 양수 diff(추천 MDD 더 큼) = 손실 악화 → 손실색, 음수 diff = 손실 완화 → 이익색

## BalanceTable

**섹터 컬럼**: 헤더 순서 `종목명 → 섹터 → 거래시장 → (전략) → …`. `Holding.sector` 표시, 값 없으면 `-`(열 밀림 방지). `data-testid="sector-{ticker}"`. 데이터는 백엔드 `/api/balance` 가 **이미 조회한 stock_master basics 를 재사용**해 산출(추가 DB 호출 0) — `sector_naming` 단일 진실원(`bstp_kor_isnm` → `_kojiro_sector_key(master_raw)` → `미분류-{ticker}`). ⚠️ 컬럼 추가 시 빈 상태 행의 `colSpan`(현재 `isAll ? 11 : 10`) 동반 갱신 의무.

**손절가 · 목표가 컬럼 (cycle339)**: "현재가" 다음, "평가금액" 앞. 데이터는 `/api/balance` Holding 의 `stop_price`/`stop_source`/`target_price`/`target_source` — 백엔드 `position_exit_lines` 단일 진실원(추가 DB 호출 0). testid `stop-price-{ticker}` · `target-price-{ticker}`.

- 🔴 **`stop_source === 'engine_idle'` 는 `⏸` 로 그리고 툴팁이 「매매 엔진 정지 중 — 장 시작(07:45) 후 표시된다. 손절선이 없다는 뜻이 아니다」를 말한다.** 21:30~07:45 은 엔진이 메모리 포지션을 비운 구간이라 청산선을 알 길이 없다 — 「없음」과 같은 모양으로 그리면 운영자가 아침에 손절이 풀린 줄 안다.
- 🔴 **값이 없으면 `—` 다. 0 이 아니다.** 이 화면은 운영자가 "여기까지는 버틴다" 를 판단하는 곳이라 **틀린 손절가는 없는 것보다 나쁘다** — 판정 불가는 숫자를 지어내지 않는다.
- `stop_source === 'hard_pct'` 는 회색 + **「근사」** 꼬리표다(고정% 손절 전략의 `매입가 × (1 + 하드손절%)`). `'effective'` 는 그 전략이 실제로 쓰는 선이라 꼬리표가 없다 — **같은 칸에 정확도가 다른 두 값이 섞이는데 화면이 구분 못 하면 둘 다 못 믿는다.**
- 🔴 툴팁이 **「가격 무관 청산(15:20 일괄매도 · 스테이지 종료 · 익일청산)은 이 값에 담기지 않는다」**를 말한다. 안 밝히면 운영자가 그 가격까지 안 팔린다고 읽는다.
- **`stop_source === 'mode_dependent'`** 는 `—` + 회색 **「모드별」** 꼬리표다 — 롱테일은 보유 중 손절 기준이 당일/상한가 모드로 갈려 하나의 값으로 접으면 한쪽이 틀린다(−5 로 보이는데 실제 −3.5). 숫자를 지어내지 않는다.
- **`target_source === 'measured_move_hit'`** 은 **「도달」** 꼬리표 + 「이미 도달해 익절 신호가 나갔다」 툴팁이다 — 발화한 목표를 숫자만 보이면 「아직 안 닿았다」로 읽힌다.
- 🔴 손절가 툴팁은 「이 가격에 닿기 전에 팔리는 경로」를 **둘로 갈라** 말한다 — **보유일수만으로**(눌림목 돌파 5영업일 · 15:20 일괄매도 · 익일청산) / **다른 조건이 함께 붙는 것**(20일 신고가 스윙은 2영업일 뒤 **돌파고점 아래일 때만** · 대순환 스테이지 종료). ⚠️ **뭉뚱그려 「가격 무관」이라 적지 않는다** — donchian 의 2영업일 청산은 `days_held ≥ n ∧ current_price < breakout_high` 라 가격 조건부이고, 뭉치면 운영자가 위험을 과대평가한다.
- **목표가는 거의 다 `—` 가 정상이다** — 7전략 중 `bull_flag_breakout` 만 `measured_target`(깃대폭 + 깃발고점)을 갖고 그마저 **부분 익절 트리거**다. 툴팁이 "전량 청산선이 아니다" 를 밝힌다. ⚠️ **VB·LTV 의 `target_price` 를 이 칸에 넣지 않는다**(매수 트리거 가격이다).
- ⚠️ 컬럼 2개가 늘었으므로 빈 상태 행 `colSpan` 은 **`isAll ? 13 : 12`** 다. 회귀가 헤더 수와 대조한다.
- 회귀 = `components/__tests__/BalanceTable.exitLines.test.tsx`(15, **값 검사** — 두 칸 값 맞바꿈·결측 `—`·근사 꼬리표·툴팁 문구·colSpan↔헤더 수).

**거래시장 배지**: 보유 종목 헤더 "종목명" 옆 "거래시장" 컬럼. `Holding.nxt_tradable / krx_halted` 조합 5가지 배지 — `KRX+NXT`(emerald-100/800) / `NXT만`(amber-100/800) / `KRX`(gray-100/700) / `정지`(red-100/800) / `확인중`(gray-50/500). `data-testid="market-badge-{ticker}"`. 베이스 클래스 `inline-block px-1.5 py-0.5 rounded text-xs font-medium`

## KisAccountPoolCard

Dashboard `MarketRegimeCard` 직하(시장 → 인프라 위계). WebsocketPool 세션 상태 + 슬롯 사용률 + 분배 모니터링 + 끊김 종목.

- `pool-refresh-button` 새로고침 → `invalidateQueries({queryKey:['realtime-subscriptions']})`
- 총 슬롯 패널 — `pool-used-slots / pool-total-slots` (41 × N) + `pool-usage-progress` 진행바 (80%+ amber) + fresh/stale/ACK 카운트
- 세션별 표 — `pool-session-row-{label}` / label 배지(main=blue + `(체결통보)`) / `pool-session-status-{label}`(connected=emerald / disconnected=red) / subscribed/limit + `pool-session-progress-{label}` 미니 진행바 / fresh / stale / reconnect_count. **세션 라벨은 DB `kis_quote_accounts.label`** 을 그대로 쓴다(main 외 배지는 모두 회색)
- 보조 0개: `pool-no-secondary-note` 안내
- 끊김 영역(`stale_60s > 0` 시): `stale-context-label` — KRX 메인(09:00~15:30) 빨강 "결함 가능" / PRE_NXT(08:00~09:00) 노랑 "거래량 적음" / 그 외 회색 "한산 시 정상" · `pool-resubscribe-button` — `useMutation(resubscribeStale)` → `POST /api/realtime/resubscribe`, 성공 시 `invalidateQueries({queryKey:['realtime-subscriptions','trading-status']})` + "N종목 재구독 완료" · `pool-stale-list-toggle` + `pool-stale-row-{ticker}`(마지막 tick 시각 HH:MM:SS, `last_tick_map[ticker]=null` 이면 "—")
- 공용 헬퍼 `frontend/src/utils/stale-context.ts`(`getKstMinutes / getStaleContextByKstMinutes / STALE_CONTEXT_META / formatLastTickKst`)
- 세션별 종목 expand: `pool-session-expand-{label}` 클릭 시 `pool-ticker-row-{label}-{ticker}`(ticker / 이름 / stale 배지 / WS tick 시각 / retries / 마지막 강제 재구독 시각). 응답 `sessions[*].tickers_detail`(cap 200, stale 우선 정렬)
- KIS 체결/거래량 컬럼: `inquire_ccnl` 캐시(`last_cntg_hour` HH:MM:SS / `today_volume`). 헬퍼 `formatCntgHour` / `isWsSubscriptionSuspect` — WS tick 시각과 KIS 실제 체결시각 차이 **5분(300초) 이상**이면 amber "WS 의심" 배지. 캐시 미스 → "—"
- API: `getSubscriptions()`, `/api/realtime/subscriptions` sessions 배열. queryKey `['realtime-subscriptions']`, `staleTime: 5_000`, `refetchInterval: 30_000`(Trading Status 5s 와 별개 큐로 부하 격리). 에러 시 `pool-error-message` graceful

## MarketRegimeCard

Dashboard 환경 배너 직하, 전략 탭 위 (`<ControlPanel />` 직후).

- regime 배지 (defensive=red / neutral=gray / aggressive=blue / 비활성=gray-500) + VIX / Fear & Greed / Buffett / cycle 메트릭 grid + cash_usage_ratio + auto_regime_adjust 토글
- 🔴 **`buy_blocked` 는 백엔드에서 항상 false 다**(레짐은 매수에 개입하지 않는다). `block_reason` 존재 시 `data-testid="market-regime-block-banner"` amber **"레짐 경보"** 관찰 배너를 띄운다 — 관찰 사유만 적고 "매수 차단" 문구는 쓰지 않는다. ETF 스테이지 소섹션(`etf_kospi_stage`/`etf_kosdaq_stage`/`etf_defensive`, `etf_enabled=false` 시 "관찰 비활성")
- `auto-regime-toggle` ON/OFF — `ConfirmModal` 이중 확인 (ON: "다음 영업일부터 cash_min 기반 자동 갱신" / OFF: "운영자 수동값 보존")
- API: `getMarketRegimeCurrent()` (queryKey `['marketRegime']`, staleTime 60s) + `setAutoRegimeAdjust(boolean)` + `getMarketRegimeHistory(days)`
- `enabled=false` (DKSTOCK_REGIME_ENABLED=false) → "비활성" gray 배지 + 메트릭 "—"

## RealtimeHealth (`/realtime-health`)

`fetchRealtimeHealth()`(`frontend/src/api/realtime-health.ts`)가 `/api/logs/search` 로 4 prefix 를 grep 해 카드 4개를 만든다 — `[dispatch_drop_summary]` · `[callback_exception]` · `[stale_force_retry]` · `[ws_auto_restart]`. 타입 `RealtimeHealthSnapshot`(`types/realtime-health.ts`).

5번째 카드 `MarketOperationCard`(testid `realtime-health-card-market-operation`) — `fetchMarketOperationStatus()` → `GET /api/realtime/market-operation`(`data.data ?? fallback`). VI 활성 N / 거래정지 N / 종목상태 이상 N 배지(count 0=gray, >0=amber/red) + **서킷브레이커 배지**(`realtime-health-cb-badge`, `circuit_breaker.suspected` true→orange "추정" / false→gray "정상") + 종목별 detail + raw `MKOP_CLS_CODE`/거래정지 사유. 데이터 원천은 백엔드 `market_operation_monitor`(H0UNMKO0). 「종목상태 이상」 배지는 `iscd_stat_active_count` 이고, 백엔드가 **표시 집합** 51~54·58·59(관리·시장경고·거래정지·단기과열)로 센다 — 55(신용가능)·57(증거금100%)·00 은 세지 않는다. 「거래정지」 배지는 `TRHT_YN=="Y"` 또는 종목상태 `58` 인 종목만 센다. 범위가 달라서 두 배지 숫자가 달라도 정상이다. 종목별 행(testid `realtime-health-op-row-<ticker>`)은 세 배지를 쓴다 — VI(`vi_code`·`ovtm_vi_code` 중 하나라도 활성일 때만, 비활성 집합 `VI_INACTIVE_CODES` = 백엔드 `_INACTIVE_VALUES`) · 거래정지(`halt_yn` Y 또는 종목상태 `58`, 행당 1개) · 종목상태(51 관리종목·52 투자위험·53 투자경고·54 투자주의·59 단기과열만, 55·57·00 은 그리지 않는다). 정지 사유는 정확히 `(null)` 일 때만 숨긴다. 행 목록은 백엔드 `details`(VI ∪ 거래정지 ∪ 종목상태(51·52·53·54·59), cycle371)라 51·59 만인 종목도 행이 있다 — 58 은 이미 거래정지 TTL(600초)로 관리되므로 `details` 합집합에서 제외한다(별도 관리 시 TTL 만료 뒤에도 영구 잔존). 헤더 「종목상태 이상 N건」(51~54·58·59 6종)과 행 배지 수(51·52·53·54·59 5종 + 58 은 거래정지 배지로 흡수)는 보통 같지만 갈릴 수 있다 — 헤더는 마지막 이벤트 기준으로 58 을 계속 세고, 58 행은 거래정지 600초 수명이 지나면 빠진다. 상수는 `types/market-operation.ts`. 회귀 가드 `RealtimeHealth.cycle370.test.tsx`. **CB 는 휴리스틱**(사유 키워드 OR 전 시장 halt 비율)이다 — KIS H0UNMKO0 에 CB 전용 필드가 없다. **표시만(매수 가드 아님)**. 회귀 가드 `RealtimeHealth.cycle186.test.tsx`.

## Strategies (`/strategies`)

등록 전략(현재 7)마다 카드 하나 — 전략 목록을 화면이 들고 있지 않고 응답 그대로 그린다. 카드마다 4 임계 표시 — `stop_loss_rate`(손절 비율) · `daily_loss_limit`(일일 손실 한도) · `trailing_stop_rate`(Trailing Stop 비율) · `position_ratio`(종목당 매수 비중). 데이터는 기존 `GET /api/strategies`(`data?.strategies ?? data` 폴백 — 플랫/내포 양쪽 처리). `params={}` 면 "—".

### TE/RR 성과 섹션

전략 카드 4임계 그리드 *아래* "성과 (최근 3개월)" 섹션(`te-section-{key}`) 5행 — 서적 TE(예지치)/RR비율. 데이터 = `GET /api/strategies/te?months=3`(`getStrategyTeRr`, `frontend/src/api/strategies.ts`, `useQuery(['strategy-te',3], retry:1, staleTime:5분)`, 기존 `/api/strategies` 폴링과 독립). 타입 `TeRrMetrics`(`strategy.ts`, 백엔드 1:1 19필드).

- A: 배지(`te-verdict-{key}` 우위/열위/판정유보) + TE% 헤드라인(`te-value-{key}`) + 3개월 실현 ₩(`te-realized-{key}`)
- B: RR 컴팩트 게이지(`rr-gauge-{key}`/`rr-gauge-fill-{key}`/`rr-gauge-marker-{key}`) — 실제RR 채움 + 필요RR 세로 마커. 채움 ≥ 마커 = 우위(이익색) / 미만 = 열위(손실색). 색은 hex 리터럴이 아니라 시맨틱 클래스 `bg-pnl-profit`/`bg-pnl-loss`(+ `pnlColorClass`)를 쓴다
- C: 분해(`te-decomposition-{key}` 승률 W/L·평균수익·평균손실·N) / D: 구조태그(`te-structure-{key}`) / E: 표본캡션(`te-sample-caption-{key}`)
- **표본 게이트 3분기**: `sample_tier='insufficient'`(N<20) → TE·배지 회색 뮤트 + "판정 유보" + 게이지·구조 숨김 / `'low'`(20-49)+rr_available → amber "표본 적음" / `'low'`+!rr_available → 게이지 "RR 참고 불가" / `'normal'`(50+) → 정상(single_trade_dominant 시 "RR 과대 가능")
- **오독 방지**: verdict 와 structure_tag 는 독립이다(verdict=TE 부호 · structure_tag=사분면). **verdict 배지가 지배 색**이고 **structure_tag 는 중립 회색**(`text-gray-600`) + 형태 병기("견고형 (저승률·고RR)") — "견고형=우량" 오독 차단
- 페이지 하단 1회: 표 1-2 참조표(`te-reference-table` 승률 10~90% → 필요RR 9.00~0.11) + 교육 캡션(`te-education-caption`). TE 실패해도 4임계 카드 정상 렌더(격리). **관찰 전용, 매매 무관**. 회귀 가드 `StrategiesTeRr.test.tsx`

## MarketState (`/market-state`) — 장운영상태

거래소별 장 운영 시간표·주문유형 카탈로그와 그날의 매매 외 작업 현황을 한 화면에서 본다. 페이지가 조회를 소유하고 조각 컴포넌트는 순수 표현이다.

🔴 **이 페이지 계열(`pages/MarketState.tsx` · `components/MarketState*.tsx`)에는 시각 리터럴·행 id·주문유형 코드·거래소 이름을 두지 않는다.** 전부 응답 값을 보간해 그린다 — 화면이 값을 들고 있으면 거래소 표가 바뀌는 날부터 옛 표를 그린다. 커서(지금 몇 번째 행인가)도 서버가 판정한다. 클라이언트가 계산하는 것은 **남은 시간 스톱워치** 하나뿐이고 그마저 두 시각의 *차이*만 쓴다. 0 에 닿으면 다음 행을 스스로 계산하지 않고 **재조회 1회**를 한다. 이름 규약 가드 FE19/FE20 이 `components/MarketState*.tsx` 를 함께 감시한다.

- 조회 3: `fetchMarketState`(표·커서, 단일 `useQuery`) · `GET /api/realtime/market-operation`(RealtimeHealth 5번째 카드와 **같은 응답·같은 쿼리키** — 두 화면을 같이 열어도 캐시를 공유한다) · `GET /api/market-ops`(섹션 B 전용, 별도 실패 도메인이라 독립 쿼리)
- 헤더: `market-state-asof`(KST) · `on_date` · `market-state-trading-day-badge`(개장/휴장/확인 불가, title=`trading_day_source`) · 표 버전 · `market-state-refresh`
- `market-state-preview-banner` — 다른 날짜를 보는 중에는 "지금" 커서를 그리지 않는다
- (1) 현재 상태 카드 `market-state-card-{market}` — 시간대·시장가 가능 여부·주문 가능 여부·확신도·동시에 열린 창·`market-state-card-countdown-{market}`
- (1-A) **지금 시장은** (`MarketStateNow.tsx`, `market-state-now-section`) — 실시간 VI·거래정지·서킷브레이커(추정). 🔴 지켜야 할 셋: ① **관측 커버리지를 숨기지 않는다** — `H0UNMKO0` 는 대표 종목 + 보유·익일청산 종목만 구독하므로 "VI 0건" 을 "VI 없음" 으로 읽으면 없는 안전을 믿게 된다. 이벤트 수신 종목 수(`last_event_count`)를 **항상** 병기한다(`market-state-now-coverage-note`) ② **서킷브레이커는 추정이다** — "추정" 표기 + 판정 근거(halted/observed·사유 표본, `market-state-now-cb-basis`)를 평시에도 보여준다 ③ **세션 상태 4분기**(`market-state-now-session-badge`) = 관측 중 / 장 종료 — 마지막 관측값(엔진 phase `closing`·`settling`·`log_analysis` 는 값이 얼어붙는다) / 세션 종료 — 집계 없음(정산 `_reset_daily_state` 뒤의 0 은 "이상 없음" 이 아니라 "집계 자체가 없다") / 엔진 상태 확인 불가
- (1-B) **오늘 야간작업** (`MarketStateOps.tsx`, `market-state-ops-section`) — `GET /api/market-ops` 를 시각순 타임라인으로. 예정 시각은 전부 라우트가 `scheduler.TIME_*`(+ 보조계좌 토큰은 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`)에서 읽어 보낸 문자열이다. 상태 어휘 10종을 있는 그대로 보여준다 — `scheduled` / `running` / `done` / `overwritten`(20:05 metrics 1차 스냅샷을 21:30 정산 완전판이 정상적으로 덮어썼다는 뜻이라 **결함이 아니다**, `failed` 와 다른 색) / `failed` / `skipped_fresh` / `skipped_weekly` / `not_fired`(증거 자체가 없다 — 점선 테두리) / `holiday` / `unknown`(마커가 영구 결측인 작업. **없는 증거를 실패로 위장하지 않는다**). 배지 색은 실패(red)와 미발화(gray)를 sRGB 거리로 벌려 둔다 — 라벨 두 글자로만 갈리게 하지 않는다
- (2) 커서 표 `market-state-table` — 시장별 그룹, 행 `market-state-row-{row_id}`. 현재 행에 커서, 지난 행은 흐리게, 동시에 열린 창은 점선
- (3) 주문유형 카탈로그 `market-state-catalog` — 행 `market-state-catalog-row-{code}`(`data-confidence`), 거래소별 셀 `market-state-catalog-cell-{code}-{exchange}`(`data-support`). **● 지원 · ? 확인 필요 · 빈칸 미지원** 3상태다 — 🔴 **확인하지 못한 칸을 미지원으로 접지 않는다**("모른다" 와 "안 된다" 는 다른 말이다). `confidence !== 'confirmed'` 이면 이름 옆에 "확인 필요". 표가 드러낸 것은 `market-state-finding-{i}`
- (4) 바닥: `market-state-board-note`(보드와 장 상태는 다른 것이다) · `market-state-unconfirmed-note`
- 실패 분기: 404 → `market-state-notice`(안내) / 그 외 → `market-state-error` + `market-state-failure-detail` + `market-state-retry`

## Macro (`/macro`) — cycle303 매크로 분석

`stock-manager` 의 `macro_lite` 패키지(`packaging/macro_lite/`)를 이식했다 — 백엔드는 독립 `macro`
컨테이너(포트 미노출, nginx `/api/macro/` 프록시), 프론트는 `frontend/src/macro/` 아래 `.tsx` 로 이식했다.
🔴 cycle315 부터 `src/engine/market_regime.py` 가 이 컨테이너를 본다 — 그래도 레짐은 **관찰 지표**라 매수를 차단·축소하지 않는다.

- **5섹션**(원본 순서 고정): 경기사이클+투자체제(`MacroCycleSection`) → 장단기 금리차(`YieldCurveSection`)
  → 하이일드 스프레드(`CreditSpreadSection`) → 환율(`CurrencySection`) → 원자재(`CommoditySection`).
  각 섹션 루트에 `data-testid="macro-section-{cycle|yield-curve|credit-spread|currency|commodity}"`.
- **경기사이클 보존 7항목**(구조 재설계 금지) — 국면 4칸(`macro-cycle-phase-{phase}`) · 체제 4칸
  (`macro-cycle-regime-{regime}`, `RegimeDetail` 안 보조 스트립) · 두 카드가 `grid-cols-2` 로 나란히
  · 판단 근거 지표 카드 5종(`macro-cycle-indicator-{key}`) · `DivergenceNote`(국면·체제 엇갈릴 때만,
  `macro-cycle-divergence-note`) · 체제 상세(공포탐욕/버핏지수/VIX) · `InfoTooltip` 해설 2종.
- 🔴 **두 단계이동 스트립은 각자의 카드 안 같은 자리에 있다** — 국면·체제 카드 모두
  「제목 → 큰 배지 → 부제 → 4칸 스트립(`grid-cols-4 gap-1.5`) → 상세」 순서를 공유한다.
  한쪽만 옮기면 위치가 어긋나므로 순서를 바꿀 땐 두 카드를 같이 바꾼다. 국면 쪽 화살표(→)는
  두지 않는다(반쪽 폭 카드에서 60px 를 먹어 4칸 라벨이 찌그러진다). 가드 = `MacroPage.test.tsx`
  의 「각자의 카드 안 같은 자리」 케이스(두 스트립의 카드 내 자식 인덱스가 같은지까지 잰다).
- 🔴 **`confidence` 는 「1·2위 점수차」로 보여 준다 — 확률이 아니다.** 값은
  `cycle.py` 의 `(1위 총점 − 2위 총점) × 200` 이고 과거 적중률로 교정한 적이 없다.
  블록 `macro-cycle-gap` 이 지키는 것 넷: (a) 라벨에 「신뢰」를 쓰지 않는다 (b) 단위는 `%` 가
  아니라 `점` (c) 눈금은 **1위를 100% 로 잡은 상대 막대** — 0~1.00 공통 눈금 금지(국면별
  도달 가능 최대 총점이 회복기 0.61 · 확장기 0.60 · 과열기 0.45 · 수축기 0.97 로 달라
  1.00 은 거짓 분모다) (d) 2위 국면의 **이름은 응답에 없으므로**(`final_scores` 미반환)
  지어내지 않고 「이름 없음」으로 둔다. 구간 배지(팽팽/보통/뚜렷)는 고정 컷이 아니라
  `2 × 기여 > 격차`(한 지표가 1·2위를 갈아타면 격차가 기여의 2배만큼 움직인다)에서 끌어낸다.
- 🔴 **지표 카드는 `score`(당선 국면 기여)만 쓰고 `score / weight`(지지율)는 쓰지 않는다** —
  지표마다 한 국면에 줄 수 있는 상한이 달라서(과열기 기준 금리차 0.80 · 나머지 넷 0.30)
  지지율을 나란히 세우면 거짓 비교가 된다. 기여는 같은 국면에 보탠 가중값이라 비교되고
  **다 더하면 그 국면 총점**이다. testid = `macro-cycle-contrib-{key}`.
- ⚠️ **새 testid 에 `macro-cycle-phase-` · `macro-cycle-indicator-` 접두사를 물려주지 않는다** —
  보존 가드가 그 두 접두사를 정규식으로 세어 「국면 4칸」·「지표 카드 5종」을 단언하므로,
  물려받는 순간 4칸이 11칸이 되고 5종이 10종이 된다(cycle306 실측).
- 확률 오독 복귀는 `MacroPage.test.tsx` 가 막는다 — 금지어 6종(신뢰·정확·확률·가능성·적중·맞을)
  검사 스코프는 **`macro-cycle-gap` 서브트리**다. 파일·섹션 단위로 넓히면 보존 대상인
  `REGIME_TOOLTIP`(「신규 매수 금지」)과 `DivergenceNote`(「매수 기회일 수 있습니다」)가 걸린다.
- **타입 계약 2가지**(`types/macro.ts`) — `MacroCycleResponse.cycle` 은 optional(`data.cycle || data`
  폴백), `RegimeData` 접근은 `regime?.regime` optional chaining. 응답 shape 계약 자체라 지우지 않는다.
- `api/macro.ts` 는 우리 `api/client.ts`(axios, `baseURL:'/api'`) 를 쓴다 — `X-API-Key` 는 붙이지 않는다
  (nginx 가 주입·치환). macro 콜드 캐시가 기본 10초 타임아웃보다 길어질 수 있어(yfinance 약 27건)
  요청마다 `{ timeout: 60000 }` 오버라이드를 준다.
- 이 5개 응답은 **우리 `ApiResponse<T>` 래퍼를 쓰지 않는다** — macro 서비스가 독립 FastAPI 프로세스라
  원본 계약(`{ <section>, updated_at, errors }`)을 그대로 반환한다.
- 훅은 TanStack Query 로 갈아엎지 않고 원본 `useAsyncState` 계열을 그대로 썼다(이식 사이클이라
  구조 변경 없음) — `retry:1` 테스트 규약은 `useQuery` 를 쓸 때만 해당해 이 화면엔 적용되지 않는다.
- `EventLabelsOverlay` 의 침체/약세장 음영 alpha 는 원본 소스 값(약세장 0.10 · 침체 0.18)을 그대로
  이식했다 — 색 hex 리터럴은 전부 `var(--color-...)` CSS 변수로 치환했다(신규 hex 금지).
- 회귀 가드 `frontend/src/macro/__tests__/MacroPage.test.tsx`.

## 주문 안전성

- 시작/정지/매도 등 주문 관련 버튼은 ConfirmModal 이중 확인 필수

## 인증

- **프로덕션은 nginx Basic Auth 뒤에 있다.** `frontend/nginx.conf.template`(구 `nginx.conf` 는 삭제 — 되살리면 인증 없는 구버전이 조용히 서빙되는 fail-open)이 server 레벨 `auth_basic` 으로 SPA·`/api/` 를 모두 덮고, `/api/` 프록시가 백엔드 키를 **서버 측에서** 주입한다 — 키는 번들·브라우저 어디에도 실리지 않는다. 🔴 `auth_basic off;` 는 이 파일에 절대 쓰지 않는다(한 줄로 Basic Auth 와 백엔드 인증이 동시에 열린다 — AST 가드가 금지). nginx·백엔드 쪽 계약의 정본은 루트 [`CLAUDE.md`](../CLAUDE.md) 「Docker / 배포」 절과 [`src/routes/CLAUDE.md`](../src/routes/CLAUDE.md) 다.
- **`client.ts` 는 `withCredentials: true` 다.** SPA 의 XHR 이 자격 없이 나가면 401 을 받아 브라우저가 로그인 다이얼로그를 **두 번** 띄운다. 동일 출처(`baseURL: '/api'`)라 CORS 파급 0. 회귀 가드 `tests/unit/ast/test_cycle246_nginx_template_no_key_leak.py::G-246-5`(주석을 걷어낸 뒤 검사 — 설명 주석이 같은 문자열을 담고 있어 순진한 검색은 실제 설정을 주석 처리해도 통과한다).
- **아이콘 경로는 `return 204;` 로 단락한다** — `/favicon.ico`·`/favicon.svg`·apple-touch 정규식(크기 변형 포함). Safari 의 네트워킹 프로세스가 아이콘을 페이지 자격 없이 따로 가져오고 그 401 의 `WWW-Authenticate` 가 두 번째 다이얼로그가 된다. `return` 은 rewrite 단계라 access 단계의 `auth_basic` 에 도달하지 않아 `auth_basic off` 없이 닫힌다. **블록엔 `return 204;` 외 지시자를 두지 않는다**(proxy_pass/root 가 들어오면 무자격 제공). 실제 아이콘은 `index.html` 이 **data URI** 로 품어 서버 요청 자체가 없다(`/favicon.svg` 서버 경로로 되돌리면 재발). 가드 `tests/unit/ast/test_cycle247_icon_probe_no_second_prompt.py` G-247-1~5.
- **dev 는 nginx 를 거치지 않는다.** `vite.config.ts` proxy 가 `X-API-Key`(= `process.env.API_AUTH_KEY`)와 `Origin: apiTarget` 을 함께 넣는다. Origin 정규화가 빠지면 `changeOrigin: true` 가 Host 만 바꾸는 탓에 백엔드 CSRF 검사가 **상태변경만** 401 로 막아 "화면은 멀쩡한데 버튼만 죽는" 형태가 된다.
- **알려진 한계 (후속 F4)** — `client.ts` 에 **401 인터셉터가 없다**. 자격 만료·키 교체 시 폴링(18곳, 최단 3초)이 재인증 유도 없이 조용히 실패한다.

## 백엔드 연동

- 모든 API 호출은 `api/client.ts` axios 인스턴스 경유
- 응답은 `types/common.ts::ApiResponse<T>` 로 파싱
- 백엔드 응답 필드명 = TypeScript 속성명 (1:1, 변경 시 동기화)
- 페이징 응답에 `total`/`total_pages` 필드 필수
