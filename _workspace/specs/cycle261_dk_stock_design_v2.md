# cycle261 명세 — DK Stock 디자인시스템 v2(가을 팔레트 + Gmarket Sans) 프론트 적용

- 사용자 지시(09-05 19:xx): `dk-stock-design/handoff/README.md`·`CLAUDE_CODE_TASK.md` 절차대로 `frontend/` 에 적용. 디자인시스템 폴더는 리포 안 `dk-stock-design/`(git 미추적, `.git/info/exclude` 로 로컬 제외 — 리포에 커밋하지 않는다. 사용자가 원하면 별도 결정).
- 범위: `frontend/` 전용(백엔드 0줄, 8영역 무관). 배포 = frontend 모드(backend 무접촉). Tailwind v4(`@tailwindcss/vite`, `@theme`), 설정 파일 없음.
- 정본 입력: `dk-stock-design/handoff/frontend/src/index.css`(테마 — `@font-face` 3 + `@theme` 팔레트 재정의·별칭·`--color-pnl-*`·`--font-sans/--font-brand`), `…/utils/pnlColor.ts.txt`, `…/types/strategy.ts.txt`, `…/App.tsx.patch.md`(diff 5곳), 폰트 `dk-stock-design/assets/fonts/GmarketSans{Light,Medium,Bold}.ttf`(이미 `frontend/public/fonts/` 에 같은 이름으로 스테이징됨 — byte 동일 확인).

## 행위(사용자 가시 변경 — 지시로 승인됨)
1. 서체: 본문 `font-sans` = Gmarket Sans(Light 100–300 / Medium 400–500 / Bold 600–900, `font-display: swap`), 로고타입 `font-brand`.
2. 팔레트: `red/blue/gray` 가을 톤 재정의 + 별칭(`green→sky, amber/yellow→beige, purple/violet/indigo→navy, pink/orange→brown, emerald→blue, cyan→sky, slate→gray`) — 기존 className 무수정으로 새 톤. 새 이름 `navy/beige/brown/sky` 사용 가능.
3. 손익색(`utils/pnlColor.ts` 전체 교체): PROFIT `#c34a36` / LOSS `#3d73b7` / NEUTRAL `#41403b`, `pnlColorClass` → `text-pnl-profit|loss|flat`(@theme `--color-pnl-*` 와 동일 값). `text-red-600/text-blue-600` shade 계열(TradePnLGrid/BreakoutCandidateMonitor)은 **무접촉**(주석 계약).
4. 전략색(`types/strategy.ts` 전체 교체, `TeRrMetrics` 등 나머지 인터페이스 byte 동일 유지): momentum `#3d73b7` · VB `#364c6d` · LTV `#b39364` · donchian `#488eb4` · BFB `#c34a36` · VCP `#9d6644` · kojiro `#141c2b` · DEFAULT `#74716a`, bg/text/badge 는 navy/beige/sky/red/brown 계열.
5. `App.tsx` diff 5곳: 루트 `bg-gray-100`→`bg-beige-100`, EnvBanner `bg-green-600`→`bg-sky-600`, 로고 2곳 `AutoStock`→`DK Stock`(`font-brand font-bold tracking-tight`), 슬라이더 `accentColor '#2563eb'`→ navy-600. **슬라이더 accent 는 App.tsx 외 3파일 4곳(`TradeAmountFilterCard.tsx:155`, `CashUsageRatioCard.tsx:93`, `PriceFilterCard.tsx:165/201`)도 같이** — 값은 hex 리터럴 대신 `'var(--color-navy-600)'`(Tailwind v4 @theme 이 `:root` 에 노출하는 CSS 변수 — 단일 진실원, 5곳 동일). 테스트가 `accentColor` 문자열을 단언하면 함께 갱신.
6. 하드코딩 hex 소탕: `#FF3333 #3366FF #333333 #2563eb`(대소문자 무관) 를 `frontend/src` 전수 grep → 소스 0건(테스트의 기대값은 새 값으로). `BacktestComparisonCard.test.tsx` 의 D 케이스는 상수 import 또는 새 hex 로.
7. Recharts(`ProfitChart.tsx` 등): 색 직접 지정이 있으면 `getStrategyColor().hex`/`pnlColorHex` 로 — 사전 grep 결과 직접 hex 0건(확인만).
8. 선택 항목(README §4·§5 타이포)은 **하지 않는다**(카드 제목·tabular-nums 전면 변경은 별도 결정) — 단 §4 루트 배경은 patch.md 에 포함돼 있으므로 적용.

## 테스트(tdd-engineer — vitest, TZ/ICU 무관)
- `utils/__tests__/pnlColor.test.ts` 기대값 갱신(새 hex 3 + `text-pnl-*` 3 + undefined/null/NaN → NEUTRAL).
- 신규 `src/__tests__/designSystem.v2.test.ts`(텍스트 계약): (a) `src/index.css` 에 `@font-face` 3개, `url('/fonts/GmarketSans{Light,Medium,Bold}.ttf')`, `@theme` 안 `--font-sans` 첫 패밀리 'Gmarket Sans', `--color-pnl-profit/loss/flat` 가 `pnlColor.ts` 의 PROFIT/LOSS/NEUTRAL 과 **동일 값**(두 정본 드리프트 방지) (b) `public/fonts/` 에 그 3파일 존재·크기 > 1MB (c) `frontend/src/**/*.{ts,tsx}` 전수에 구 hex 4종 0건(대소문자 무관, 테스트 파일 포함 — 기대값도 새 값이어야 하므로) (d) `STRATEGY_COLORS` 7키 + hex 가 명세 값과 일치, 각 `bg/text/badge` 의 색 이름이 `index.css` @theme 에 정의된 `--color-<name>-<shade>` 를 가리킴(`bg-navy-50` → `--color-navy-50` 존재) — 별칭으로 정의된 것도 인정 (e) `App.tsx` 텍스트에 `AutoStock` 0건·`DK Stock` 2건·`bg-beige-100` 1건·`accentColor` 값이 `var(--color-navy-600)`.
- 렌더: 기존 `App`/레이아웃 테스트가 "AutoStock" 을 찾으면 "DK Stock" 으로 갱신. `BacktestComparisonCard.test.tsx` D 케이스 갱신.
- 가드 유지: `utils/__tests__/kst.test.ts` K4, `components/__tests__/_ast_weight_unit_guard.test.ts` 무수정 통과. 백엔드 `grep -rl 'frontend/' tests/unit` 가드 전부 실행(프론트 전용 사이클 규칙).
- 게이트: `npm run lint` · `npm test` · `npm run build`(=`tsc -b && vite build`) · 빌드 산출물 검사(`dist/fonts/GmarketSans*.ttf` 3개, `dist/assets/*.css` 에 `Gmarket Sans`·`pnl-profit`·`--color-beige-100` 존재) · e2e `npx playwright test --config=e2e/playwright.config.ts`(MSW 목 기반, 통과해야 함) · 스크린샷(대시보드·설정 페이지) `scratchpad/design/*.png` 로 저장(사용자 확인용).

## 문서
- `frontend/CLAUDE.md` "시각적 컨벤션"(손익색 hex·클래스명·전략색·서체·브랜드명 "DK Stock")과 관련 문단 갱신. 루트 `CLAUDE.md` 하네스 표 1행(15행 유지) + `docs/HARNESS_CHANGELOG.md` append + 워크리스트 한 줄.
- 리포에 `dk-stock-design/` 은 넣지 않는다(15MB, 생성 번들 포함). `frontend/public/fonts` 의 TTF 3개(약 7.3MB)는 커밋한다(정적 자산).

## 결과 (2026-09-05, 실측)

명세대로 적용 완료 — `index.css` 별칭 재정의만으로 기존 className 무수정, `pnlColor.ts`/`types/strategy.ts`/`App.tsx` 5곳 diff, Gmarket Sans 3 weight 반영. 게이트 전부 예상대로 통과(`tsc -b` 0 · `npm run build` 성공 · 백엔드 `frontend/` 참조 가드 227 PASS). Red 였던 `PerformanceCard.test.tsx`(9)·`StrategiesTeRr.test.tsx`(11)는 명세가 예상한 대로 `pnlColorClass` 위임만으로 추가 수정 없이 자동 Green 전환.

예상 밖으로 tester 적대 검토가 별칭 재정의(`green≡teal≡sky` 등)의 실제 hex 충돌 부작용 4건(ScanMonitor 보드 배지·IntegrationToggleCard ON 배지·PortfolioRiskCard 경고 배지·TradeHistoryGrid 부분체결 배지 — 서로 다른 상태가 같은 hex)과, 명세에 없던 nginx `/fonts/` 캐시 결손(TTF 가 정적자산 정규식 밖이라 SPA no-store 폴백을 받아 새로고침마다 재다운로드)을 발견해 4건 모두 회귀 가드 동반 시정(신규 backend pytest 8케이스 + frontend 3파일 5케이스). e2e 33 PASS·스크린샷 12장은 tester 산출물로 확보(명세의 "사용자 확인용" 요건 충족), 메인 세션은 재실행하지 않음.

최종 상태 = `npm test` 76파일/557케이스 PASS(회귀 0), 백엔드 235 PASS(회귀 0). **배포 대기**(frontend 모드 — cycle248 판정 규칙상 nginx 템플릿 변경도 frontend 전용, backend 무접촉).
