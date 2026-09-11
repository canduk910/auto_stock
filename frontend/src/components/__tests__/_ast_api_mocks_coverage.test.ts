/**
 * 사이클 75 카드 #19' (HIGH) — e2e api-mocks.ts 7 endpoint 영구 가드.
 *
 * > **선례**:
 * > - 사이클 65 hotfix #2 (`tests/unit/e2e_mocks/test_api_mocks_routes_registered.py`)
 * >   api-mocks 신규 라우트 누락 영구 가드 패턴 답습.
 * > - 사이클 65 hotfix #3 (`_ast_useQuery_retry_required.test.ts`)
 * >   useQuery `retry:` 옵션 명시 의무 영구 가드 패턴 답습.
 * >
 * > **결함 배경**: 사이클 73/74 1차 fail = flaky 2회 누적 —
 * >   Settings 화면 진입 시 `IntegrationToggleCard` / `CashUsageRatioCard` /
 * >   `KisQuoteAccountsCard` 등 7 endpoint group 이 `e2e/fixtures/api-mocks.ts` 에
 * >   미등록 → vite proxy 호출 → 백엔드 미실행 환경 ECONNREFUSED →
 * >   React Query 기본 retry 누적 → settings.spec.ts timeout.
 *
 * 요구 행위:
 * - G-AST1: `frontend/src/api/integrations.ts` 의 literal endpoint
 *   (`/integrations/${key}` 4종 + `/integrations/buy-block`) → api-mocks 등록 확인
 * - G-AST2: `frontend/src/api/trading.ts` `/strategies/system/cash-usage-ratio` 등록 확인
 * - G-AST3: `frontend/src/api/kis-quote-accounts.ts` `/integrations/quote-accounts*` 등록 확인
 * - G-AST4: 3 컴포넌트 (IntegrationToggleCard / CashUsageRatioCard / KisQuoteAccountsCard)
 *   useQuery 호출에 `retry:` 옵션 명시 확인 (Q4 확장)
 *
 * 위험 등급 HIGH — e2e flaky 영구 차단 + 향후 신규 endpoint 추가 시 영구 누락 차단.
 *
 * 검증 방법:
 * - 소스 파일 텍스트 정적 파싱 (regex 기반).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

const REPO_ROOT = path.join(__dirname, '..', '..', '..', '..')
const API_MOCKS_PATH = path.join(REPO_ROOT, 'e2e', 'fixtures', 'api-mocks.ts')
const FRONTEND_API_DIR = path.join(REPO_ROOT, 'frontend', 'src', 'api')
const FRONTEND_COMPONENTS_DIR = path.join(REPO_ROOT, 'frontend', 'src', 'components')

function loadApiMocksSource(): string {
  return readFileSync(API_MOCKS_PATH, 'utf-8')
}

/**
 * api-mocks.ts 에 정규식/구체 경로 라우트가 등록되었는지 검증.
 * Playwright route 매칭은 `**` 와일드카드와 정규식을 모두 허용 —
 * 본 가드는 endpoint 경로 substring 만 검색 (`page.route("**\/api/...")` 형태).
 */
function isRouteRegistered(source: string, endpointPath: string): boolean {
  // endpointPath 예: "/api/integrations/dkstock-regime"
  // 검증: `**${endpointPath}` 또는 `**${endpointPath}*` 또는 정규식 형태
  // 단순화: page.route 호출 인자 안에 endpointPath substring 등장 확인.
  const escaped = endpointPath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // page.route("**/api/integrations/dkstock-regime" 또는
  // page.route("**/api/integrations/dkstock-regime*"
  const regex = new RegExp(`page\\.route\\(\\s*["'\`][^"'\`]*${escaped}[^"'\`]*["'\`]`, 'm')
  return regex.test(source)
}

describe('사이클 75 카드 #19\' — e2e api-mocks 7 endpoint group 영구 가드', () => {
  describe('G-AST1: frontend/src/api/integrations.ts literal endpoint 등록', () => {
    const REQUIRED_INTEGRATION_ENDPOINTS = [
      '/api/integrations/dkstock-regime',
      '/api/integrations/kis-mcp',
      '/api/integrations/auto-regime-adjust',
      '/api/integrations/auto-apply',
      '/api/integrations/buy-block',
      // 사이클 I (2026-08-03) — 지수ETF 레짐(관찰) 계산 토글 (5번째 토글)
      '/api/integrations/etf-regime',
    ]

    it.each(REQUIRED_INTEGRATION_ENDPOINTS)(
      'api-mocks.ts 에 %s 라우트 등록 의무 (vite proxy 호출 차단)',
      (endpoint) => {
        const source = loadApiMocksSource()
        // integrations.ts 가 실제로 해당 키를 호출하는지도 1차 확인 (방어).
        const integrationsSource = readFileSync(
          path.join(FRONTEND_API_DIR, 'integrations.ts'),
          'utf-8',
        )
        const apiPath = endpoint.replace('/api', '') // /integrations/...
        const literalUsed =
          integrationsSource.includes(`'${apiPath}'`) ||
          integrationsSource.includes(`"${apiPath}"`) ||
          integrationsSource.includes(`\`${apiPath}\``) ||
          // dkstock-regime / kis-mcp / auto-regime-adjust / auto-apply 는 getToggle(key) 동적 호출
          integrationsSource.includes('getToggle(') ||
          integrationsSource.includes('setToggle(')
        expect(
          literalUsed,
          `방어 가드: integrations.ts 가 ${apiPath} 를 더 이상 호출하지 않음 — ` +
            `본 케이스 무효 가능 (api 호출 제거 시 본 가드 갱신 의무)`,
        ).toBe(true)

        expect(
          isRouteRegistered(source, endpoint),
          `e2e api-mocks.ts 에 ${endpoint} 라우트 누락 — ` +
            `사이클 73/74 flaky 결함 영속 (vite proxy → ECONNREFUSED → ` +
            `React Query retry 누적 → settings.spec.ts timeout). ` +
            `사이클 65 hotfix #2 패턴 답습 의무.`,
        ).toBe(true)
      },
    )
  })

  describe('G-AST2: frontend/src/api/trading.ts cash-usage-ratio 등록', () => {
    it('api-mocks.ts 에 /api/strategies/system/cash-usage-ratio 라우트 등록 의무', () => {
      const tradingSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'trading.ts'),
        'utf-8',
      )
      expect(
        tradingSource.includes('/strategies/system/cash-usage-ratio'),
        '방어 가드: trading.ts 가 cash-usage-ratio endpoint 를 더 이상 호출하지 않음',
      ).toBe(true)

      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/strategies/system/cash-usage-ratio'),
        'e2e api-mocks.ts 에 /api/strategies/system/cash-usage-ratio 라우트 누락 — ' +
          'CashUsageRatioCard 마운트 시 ECONNREFUSED. 사이클 73 fail 로그 확인 영역.',
      ).toBe(true)
    })
  })

  describe('G-AST3: frontend/src/api/kis-quote-accounts.ts quote-accounts 등록', () => {
    it('api-mocks.ts 에 /api/integrations/quote-accounts 라우트 등록 의무', () => {
      const accountsSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'kis-quote-accounts.ts'),
        'utf-8',
      )
      expect(
        accountsSource.includes('/integrations/quote-accounts'),
        '방어 가드: kis-quote-accounts.ts 가 quote-accounts endpoint 를 더 이상 호출하지 않음',
      ).toBe(true)

      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/integrations/quote-accounts'),
        'e2e api-mocks.ts 에 /api/integrations/quote-accounts 라우트 누락 — ' +
          'KisQuoteAccountsCard 마운트 시 ECONNREFUSED. ' +
          'POST/PUT/DELETE 도 동일 prefix 라우트 단일 등록으로 커버 가능.',
      ).toBe(true)
    })
  })

  describe('G-AST5 (사이클 77 hotfix): Dashboard 영역 endpoint 등록 (settings.spec.ts react-router prefetch 차단)', () => {
    // 사이클 76 CI fail 발견 — settings.spec.ts 진입 시 react-router prefetch /
    // lazy import 로 MarketRegimeCard / ScanMonitor (Dashboard 컴포넌트) useQuery 발화 →
    // /api/market-regime/current + /api/realtime/subscriptions ECONNREFUSED.
    // 사이클 75 G-AST1~AST3 (Settings 한정) 영역 한계 노출 → 사이클 77 = Dashboard 영역 확장.
    const REQUIRED_DASHBOARD_ENDPOINTS = [
      '/api/market-regime/current',
      '/api/realtime/subscriptions',
    ]

    it.each(REQUIRED_DASHBOARD_ENDPOINTS)(
      'api-mocks.ts 에 %s 라우트 등록 의무 (Dashboard 컴포넌트 prefetch 차단)',
      (endpoint) => {
        const source = loadApiMocksSource()
        expect(
          isRouteRegistered(source, endpoint),
          `e2e api-mocks.ts 에 ${endpoint} 라우트 누락 — ` +
            `사이클 76 CI fail 결함 영속 (vite proxy → ECONNREFUSED → settings.spec.ts fail). ` +
            `사이클 75 hotfix Settings 영역 한정 한계 노출, 사이클 77 = Dashboard 영역 확장 의무.`,
        ).toBe(true)
      },
    )
  })

  // 사이클 85 G-AST-MOCK (2026-06-09) — Stock Master 영역 5 endpoint 확장.
  // StockMaster.tsx 신규 페이지 마운트 시 5 useQuery (fetchStats / fetchList /
  // fetchScanPoolSummary / fetchDetail / fetchHistory) 호출. 사이클 75 G-AST5
  // (Dashboard 영역 확장) 패턴 100% 답습.
  describe('G-AST6 (사이클 85): Stock Master 영역 endpoint 등록', () => {
    const REQUIRED_STOCK_MASTER_ENDPOINTS = [
      '/api/stock-master/stats',
      '/api/stock-master/list',
      '/api/stock-master/scan-pool/summary',
      // detail / history 는 dynamic path (`/{ticker}`) — wildcard `/api/stock-master/*` 형태 등록
      '/api/stock-master/',
    ]

    it.each(REQUIRED_STOCK_MASTER_ENDPOINTS)(
      'api-mocks.ts 에 %s 라우트 등록 의무 (StockMaster.tsx 마운트 차단 방지)',
      (endpoint) => {
        const source = loadApiMocksSource()
        expect(
          isRouteRegistered(source, endpoint),
          `e2e api-mocks.ts 에 ${endpoint} 라우트 누락 — ` +
            `사이클 85 StockMaster 페이지 진입 시 ECONNREFUSED 위험. ` +
            `사이클 75 G-AST5 (Dashboard 영역 확장) 패턴 답습 의무.`,
        ).toBe(true)
      },
    )
  })

  // 사이클 90 M-5 (MEDIUM, 2026-06-09) — POST refresh-universe 영구 가드.
  // StockMaster 페이지 "지금 새로고침" 버튼 클릭 시 POST refresh-universe 발화.
  // 사이클 75 G-AST5 + 사이클 85 G-AST6 패턴 100% 답습.
  describe('G-AST7 (사이클 90): POST refresh-universe endpoint 등록', () => {
    it('api-mocks.ts 에 /api/stock-master/refresh-universe 라우트 등록 의무 (Q24=B + Q26=A)', () => {
      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/stock-master/refresh-universe'),
        'e2e api-mocks.ts 에 /api/stock-master/refresh-universe 라우트 누락 — ' +
          '사이클 90 H-6 "지금 새로고침" 버튼 클릭 시 ECONNREFUSED 위험. ' +
          '사이클 80 hotfix #3 LIFO 정합 의무 (wildcard `**/api/stock-master/**` *후* 등록).',
      ).toBe(true)
    })

    it('refreshUniverseNow 가 frontend/src/api/stock-master.ts 에서 호출 의무 (방어 가드)', () => {
      const apiSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'stock-master.ts'),
        'utf-8',
      )
      expect(
        apiSource.includes('refresh-universe'),
        '방어 가드: stock-master.ts 가 refresh-universe endpoint 를 더 이상 호출하지 않음 — ' +
          '본 가드 갱신 의무 (사이클 90 영역 변경 시).',
      ).toBe(true)
      expect(
        apiSource.includes('refreshUniverseNow'),
        '방어 가드: stock-master.ts 에 refreshUniverseNow export 누락 — ' +
          '사이클 90 H-5 위반.',
      ).toBe(true)
    })
  })

  // 사이클 127 (2026-06-13) — fire-and-forget + 5초 폴링 진행 가시화 영구 가드.
  // POST 3 라우트 + GET refresh-progress 모두 등록 의무.
  // 백엔드 13분 작업 axios timeout 영구 차단 패턴.
  describe('G-AST8 (사이클 127): refresh fire-and-forget 4 endpoint 등록', () => {
    const CYCLE127_ENDPOINTS = [
      '/api/stock-master/refresh-universe',  // POST 202
      '/api/stock-master/basics/refresh',    // POST 202
      '/api/stock-master/daily/refresh',     // POST 202
      '/api/stock-master/refresh-progress',  // GET 5초 폴링
    ]

    it.each(CYCLE127_ENDPOINTS)(
      'api-mocks.ts 에 %s 라우트 등록 의무',
      (endpoint) => {
        const source = loadApiMocksSource()
        expect(
          isRouteRegistered(source, endpoint),
          `e2e api-mocks.ts 에 ${endpoint} 라우트 누락 — 사이클 127 fire-and-forget 위반. ` +
            '사이클 80 hotfix #3 LIFO 정합 의무 (wildcard `**/api/stock-master/**` *후* 등록).',
        ).toBe(true)
      },
    )

    it('fetchRefreshProgress + 3 refresh 함수 모두 stock-master.ts export 의무', () => {
      const apiSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'stock-master.ts'),
        'utf-8',
      )
      const REQUIRED = [
        'fetchRefreshProgress',
        'refreshUniverseNow',
        'refreshBasicsNow',
        'refreshDailyNow',
      ]
      REQUIRED.forEach((fn) => {
        expect(
          apiSource.includes(fn),
          `방어 가드: stock-master.ts 에 ${fn} export 누락 — 사이클 127 fire-and-forget 위반.`,
        ).toBe(true)
      })
    })
  })

  // 사이클 I (2026-08-03) — 포트폴리오 리스크 관찰 카드 (PortfolioRiskCard, Phase 1).
  // Dashboard 마운트 시 GET /api/portfolio/risk 발화 — 사이클 77 G-AST5 (Dashboard 영역
  // 확장) 패턴 답습.
  describe('G-AST9 (사이클 I): 포트폴리오 리스크 관찰 endpoint 등록', () => {
    it('api-mocks.ts 에 /api/portfolio/risk 라우트 등록 의무 (PortfolioRiskCard Dashboard 마운트 차단 방지)', () => {
      const portfolioApiSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'portfolio.ts'),
        'utf-8',
      )
      expect(
        portfolioApiSource.includes('/portfolio/risk'),
        '방어 가드: portfolio.ts 가 /portfolio/risk endpoint 를 더 이상 호출하지 않음',
      ).toBe(true)

      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/portfolio/risk'),
        'e2e api-mocks.ts 에 /api/portfolio/risk 라우트 누락 — ' +
          '사이클 I PortfolioRiskCard Dashboard 마운트 시 ECONNREFUSED 위험. ' +
          '사이클 77 G-AST5 (Dashboard 영역 확장) 패턴 답습 의무.',
      ).toBe(true)
    })
  })

  // cycle276 (2026-09-11) — AI 매수평가(LLM shadow) 기록 조회 2 endpoint.
  // 거래기록 화면(`/history`)의 두 그리드가 배치 요약을, 팝업이 단건 상세를 부른다.
  // e2e `history.spec.ts`(G-E2E-10) 가 이 경로를 실브라우저로 밟으므로 목 누락 =
  // vite proxy → ECONNREFUSED → React Query retry 누적 → spec timeout.
  // ⚠️ Playwright 는 **LIFO** — 배치 fallback(`**\/api/llm-evaluations*`)을 먼저,
  //    단건(`**\/api/llm-evaluations/*`)을 나중에 등록해야 단건이 이긴다.
  describe('G-AST10 (cycle276): AI 매수평가 endpoint 등록', () => {
    it('api-mocks.ts 에 /api/llm-evaluations 라우트 등록 의무', () => {
      const apiSource = readFileSync(
        path.join(FRONTEND_API_DIR, 'llm-evaluations.ts'),
        'utf-8',
      )
      // 방어 가드 — 클라이언트가 그 리터럴을 더 이상 부르지 않으면 본 케이스는 무효다.
      expect(
        apiSource.includes("'/llm-evaluations'"),
        '방어 가드: api/llm-evaluations.ts 가 배치 요약 endpoint 를 더 이상 호출하지 않음 — ' +
          '본 가드 갱신 의무.',
      ).toBe(true)
      expect(
        apiSource.includes('`/llm-evaluations/${orderNo}`'),
        '방어 가드: api/llm-evaluations.ts 가 단건 상세 endpoint 를 더 이상 호출하지 않음 — ' +
          '본 가드 갱신 의무.',
      ).toBe(true)

      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/llm-evaluations'),
        'e2e api-mocks.ts 에 /api/llm-evaluations 라우트 누락 — ' +
          'cycle276 거래기록 "AI 자문" 버튼이 마운트되는 순간 ECONNREFUSED. ' +
          '사이클 77 G-AST5 (영역 확장) 패턴 답습 의무.',
      ).toBe(true)
    })

    it('두 그리드와 팝업이 배치/단건 클라이언트를 실제로 쓴다 (방어 가드)', () => {
      const pairs: Array<[string, string]> = [
        ['TradeHistoryGrid.tsx', 'getLlmEvaluationSummaries'],
        ['TradePnLGrid.tsx', 'getLlmEvaluationSummaries'],
        ['LlmEvaluationModal.tsx', 'getLlmEvaluation'],
      ]
      pairs.forEach(([filename, fn]) => {
        const source = readFileSync(
          path.join(FRONTEND_COMPONENTS_DIR, filename),
          'utf-8',
        )
        expect(
          source.includes(fn),
          `방어 가드: ${filename} 가 ${fn} 를 더 이상 호출하지 않음 — cycle276 영역 변경 시 본 가드 갱신 의무.`,
        ).toBe(true)
      })
    })
  })

  // cycle278 (2026-09-11) — 전략 파라미터 카탈로그 스키마 endpoint.
  // 편집기가 이 한 응답으로 렌더하므로 미등록이면 Strategies 화면의 "파라미터" 버튼이
  // 영영 로딩 상태로 남는다(vite proxy → ECONNREFUSED → retry 누적). 사이클 85 G-AST6 패턴 답습.
  describe('G-AST11 (cycle278): 파라미터 카탈로그 스키마 endpoint 등록', () => {
    it('api-mocks.ts 에 /api/strategies/params-schema 라우트 등록 의무', () => {
      const source = loadApiMocksSource()
      expect(
        isRouteRegistered(source, '/api/strategies/params-schema'),
        'e2e api-mocks.ts 에 /api/strategies/params-schema 라우트 누락 — ' +
          'StrategyParamsEditor 마운트 시 ECONNREFUSED. ' +
          '사이클 80 hotfix #3 LIFO 정합 의무 (`**/api/strategies/*/params` 보다 *후* 등록).',
      ).toBe(true)
    })

    it('frontend/src/api/strategies.ts 가 params-schema 를 호출한다 (방어 가드)', () => {
      const apiSource = readFileSync(path.join(FRONTEND_API_DIR, 'strategies.ts'), 'utf-8')
      expect(
        apiSource.includes('/strategies/params-schema'),
        '방어 가드: 스키마 fetch 가 api/strategies.ts 에 없다 — ' +
          '편집기가 키를 하드코딩하거나 다른 경로로 새고 있다는 뜻이다 (cycle278 C35 위반 신호).',
      ).toBe(true)
    })
  })

  describe('G-AST4: 3 컴포넌트 useQuery `retry:` 옵션 명시 (Q4 확장)', () => {
    const TARGET_COMPONENTS = [
      'IntegrationToggleCard.tsx',
      'CashUsageRatioCard.tsx',
      'KisQuoteAccountsCard.tsx',
    ]

    it.each(TARGET_COMPONENTS)(
      '%s 의 모든 useQuery 호출에 `retry:` 옵션 명시 의무 (Q4)',
      (filename) => {
        const filepath = path.join(FRONTEND_COMPONENTS_DIR, filename)
        const source = readFileSync(filepath, 'utf-8')

        // useQuery({...}) 와 useQuery<Type>({...}) 모두 매칭.
        const useQueryRegex = /useQuery(?:<[^>]+>)?\(\s*\{([\s\S]*?)\}\s*\)/g
        const matches = [...source.matchAll(useQueryRegex)]

        expect(
          matches.length,
          `${filename}: useQuery 호출 0건 — 컴포넌트 fetch 누락 의심 ` +
            `(grep 결과 명시 의무 영역)`,
        ).toBeGreaterThanOrEqual(1)

        const violations: string[] = []
        matches.forEach((match, idx) => {
          const optionsBlock = match[1]
          if (!/\bretry\s*:\s*(false|0|1|2|3)\b/.test(optionsBlock)) {
            violations.push(
              `[#${idx + 1}] useQuery 옵션에 \`retry:\` 누락:\n` +
                `${optionsBlock.slice(0, 200)}`,
            )
          }
        })

        expect(
          violations,
          `${filename} 의 useQuery 호출 ${violations.length}건 retry 옵션 누락 — ` +
            `사이클 75 Q4 확장 위반 (e2e ECONNREFUSED 시 React Query 기본 retry 누적 ` +
            `→ settings.spec.ts timeout 위험). 사이클 65 hotfix H3 패턴 답습.\n` +
            violations.join('\n---\n'),
        ).toEqual([])
      },
    )
  })
})
