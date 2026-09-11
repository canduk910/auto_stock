/**
 * 사이클 65 hotfix H3 — useQuery `retry` 옵션 명시 의무 영구 가드.
 *
 * > **선례**: 사이클 60 hotfix G-3 / 사이클 64 hotfix G-3 AST 정적 가드 패턴 답습.
 * > **결함 배경**: 사이클 65 e2e (settings.spec.ts) FAIL —
 * >   PriceFilterCard / TradeAmountFilterCard 의 useQuery 에 `retry` 옵션 미설정 →
 * >   e2e 환경 ECONNREFUSED 시 React Query 기본 retry (3회 × exponential backoff) 누적 →
 * >   페이지 렌더 5s 초과 → settings.spec.ts FAIL.
 * >   QueryClient defaults `retry: 1` 이 있지만 컴포넌트 useQuery 옵션이 누락되어도
 * >   silent 결함화 (defaults 가 적용은 되지만, 명시적 retry 선언이 없으면
 * >   future 회귀 시 다시 누락될 수 있음 — 영구 명시 가드 의무).
 *
 * 요구 행위:
 * - PriceFilterCard.tsx + TradeAmountFilterCard.tsx 의 `useQuery({...})` 호출에
 *   `retry:` 옵션 명시 (값: false / 0 / 1 / 2 / 3 중 하나).
 *
 * 위험 등급 HIGH — e2e timeout 영구 차단 + 다른 외부 호출 카드 회귀 가드.
 *
 * 검증 방법:
 * - 소스 파일 텍스트 정적 파싱 (regex 기반 — TS AST 라이브러리 의존 회피).
 * - useQuery 호출 블록 추출 → `retry:` 키 존재 검증.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

const TARGET_FILES = [
  'PriceFilterCard.tsx',
  'TradeAmountFilterCard.tsx',
  // 사이클 75 Q4 확장 (HIGH) — IntegrationToggleCard/CashUsageRatioCard/
  // KisQuoteAccountsCard 영역 retry 명시 의무. 사이클 73/74 flaky 결함 영속 차단.
  'IntegrationToggleCard.tsx',
  'CashUsageRatioCard.tsx',
  'KisQuoteAccountsCard.tsx',
  // 사이클 127 (2026-06-13) — RefreshProgressBanner.tsx 추가.
  // fetchRefreshProgress useQuery retry:1 명시 의무 (5초/60초 동적 폴링 + ECONNREFUSED 영구 차단).
  'RefreshProgressBanner.tsx',
  // 사이클 I (2026-08-03) — PortfolioRiskCard.tsx 추가 (포트폴리오 리스크 관찰 카드,
  // Dashboard 마운트 시 발화, e2e ECONNREFUSED 영구 차단 의무).
  'PortfolioRiskCard.tsx',
  // 전략 성과 표시 정직화 — PerformanceCard.tsx 에 strategy-te useQuery 신규 추가
  // (Dashboard 마운트 시 발화, e2e ECONNREFUSED 영구 차단 의무).
  'PerformanceCard.tsx',
  // cycle276 (2026-09-11) — AI 매수평가 팝업. 거래기록 두 그리드가 배치 요약(`/api/llm-evaluations`)
  // 을, 팝업이 단건 상세(`/api/llm-evaluations/{order_no}`)를 부른다. 세 파일 모두 e2e
  // `history.spec.ts`(G-E2E-10) 진입 경로에 있어 retry 누락 시 ECONNREFUSED 누적 → timeout.
  // ⚠️ 이 가드는 **파일 단위**라 등재와 동시에 그 파일의 *기존* useQuery 도 `retry:` 명시
  //    의무를 진다(TradeHistoryGrid 의 tradeHistory · TradePnLGrid 의 tradePnL 조회 포함).
  'LlmEvaluationModal.tsx',
  'TradeHistoryGrid.tsx',
  'TradePnLGrid.tsx',
  // cycle278 (2026-09-11) — StrategyParamsEditor.tsx 추가.
  // 전략 파라미터 카탈로그 스키마(GET /api/strategies/params-schema) useQuery 는 패널을 열 때
  // 발화한다. retry 미명시 시 e2e/백엔드 미기동 환경에서 기본 retry(3회 backoff) 가 누적돼
  // 패널이 뜨지 않는다 — 사이클 65 H3 패턴 답습.
  'StrategyParamsEditor.tsx',
]

// 사이클 80 hotfix — Settings.tsx 본체 useQuery 도 retry:1 명시 의무 (사이클 79 e2e
// 1차 + 재실행 모두 fail 확정, 페이지 어셈블 timeout 영구 차단). 컴포넌트가 아닌 페이지
// 영역이라 별도 path 처리.
//
// 사이클 85 (2026-06-09) G-AST-RT — StockMaster.tsx 신규 페이지 추가.
// 5 useQuery (fetchStats / fetchList / fetchScanPoolSummary / fetchDetail / fetchHistory)
// 모두 retry:1 명시 의무 (e2e 환경 ECONNREFUSED 빠른 실패 + 사이클 65 H3 + 사이클 80
// hotfix #1 영속 패턴 답습).
//
// 사이클 103 영역 0 (2026-06-11) G-AST-RT — RealtimeHealth.tsx 신규 페이지 추가.
// 1 useQuery (fetchRealtimeHealth) retry:1 명시 의무 영구 가드 (사이클 85 패턴 답습).
// cycle278 (2026-09-11) — Strategies.tsx 추가. 전략 카드에서 파라미터 편집기를 여는
// 진입점 페이지이고 자체 useQuery 2건(strategies / strategy-te)을 가진다.
// cycle282 (2026-09-11) — MarketState.tsx 추가. 장운영상태는 30초 폴링 화면이라
// retry 미명시 시 e2e/백엔드 미기동 환경에서 기본 retry(3회 backoff)가 폴링마다 누적된다.
const TARGET_PAGES = [
  'Settings.tsx',
  'StockMaster.tsx',
  'RealtimeHealth.tsx',
  'Strategies.tsx',
  'MarketState.tsx',
]

describe('사이클 65 hotfix H3 + 사이클 75 Q4 확장 — useQuery retry 옵션 영구 가드', () => {
  it.each(TARGET_FILES)(
    '%s 의 useQuery 호출은 `retry:` 옵션 명시 의무 (e2e timeout 차단)',
    (filename) => {
      const filepath = path.join(__dirname, '..', filename)
      const source = readFileSync(filepath, 'utf-8')

      // useQuery({ ... }) 블록 추출 (multiline + generic 지원).
      // 단일 인자 객체 리터럴 형태만 검증 — useQuery(options) / useQuery<T>(options) 패턴.
      const useQueryRegex = /useQuery(?:<[^>]+>)?\(\s*\{([\s\S]*?)\}\s*\)/g
      const matches = [...source.matchAll(useQueryRegex)]

      expect(
        matches.length,
        `${filename}: useQuery 호출 0건 — 컴포넌트 fetch 누락 의심`,
      ).toBeGreaterThanOrEqual(1)

      const violations: string[] = []
      matches.forEach((match, idx) => {
        const optionsBlock = match[1]
        // `retry:` 키 존재 확인. 값은 false / 0 / 1 / 2 / 3 중 하나.
        if (!/\bretry\s*:\s*(false|0|1|2|3)\b/.test(optionsBlock)) {
          violations.push(
            `[#${idx + 1}] useQuery 옵션에 \`retry:\` 누락:\n${optionsBlock.slice(0, 200)}`,
          )
        }
      })

      expect(
        violations,
        `${filename} 의 useQuery 호출 ${violations.length}건 retry 옵션 누락 — ` +
          `사이클 65 hotfix H1 영구 가드 위반 (e2e ECONNREFUSED 시 페이지 렌더 timeout 위험):\n` +
          violations.join('\n---\n'),
      ).toEqual([])
    },
  )

  // 사이클 80 hotfix — Settings.tsx 페이지 useQuery retry:1 영구 가드
  it.each(TARGET_PAGES)(
    'pages/%s 의 useQuery 호출은 `retry:` 옵션 명시 의무 (사이클 80 hotfix, 사이클 79 e2e flaky 영구 차단)',
    (filename) => {
      const filepath = path.join(__dirname, '..', '..', 'pages', filename)
      const source = readFileSync(filepath, 'utf-8')

      const useQueryRegex = /useQuery(?:<[^>]+>)?\(\s*\{([\s\S]*?)\}\s*\)/g
      const matches = [...source.matchAll(useQueryRegex)]

      expect(
        matches.length,
        `pages/${filename}: useQuery 호출 0건`,
      ).toBeGreaterThanOrEqual(1)

      const violations: string[] = []
      matches.forEach((match, idx) => {
        const optionsBlock = match[1]
        if (!/\bretry\s*:\s*(false|0|1|2|3)\b/.test(optionsBlock)) {
          violations.push(
            `[#${idx + 1}] useQuery 옵션에 \`retry:\` 누락:\n${optionsBlock.slice(0, 200)}`,
          )
        }
      })

      expect(
        violations,
        `pages/${filename} 의 useQuery 호출 ${violations.length}건 retry 옵션 누락 — ` +
          `사이클 80 hotfix 영구 가드 위반 (사이클 79 e2e 1차 + 재실행 모두 fail 확정):\n` +
          violations.join('\n---\n'),
      ).toEqual([])
    },
  )
})
