/**
 * 사이클 103 영역 0 — RealtimeHealth.tsx AST 영구 가드 (사이클 75 G-AST5 답습).
 *
 * 명세: _workspace/red/cycle103_area0_realtime_health_ui.md
 * 영속 의무: 사이클 75 G-AST5 / 80 hotfix #3 LIFO / 85 G-AST-MOCK
 *
 * HIGH-7: G-AST-RT TARGET_PAGES 확장 영역 (RealtimeHealth.tsx 영역 영속)
 * HIGH-8: G-AST-MOCK 4 endpoint api-mocks 등록 영구 가드
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import path from 'path'

describe('사이클 103 영역 0 — RealtimeHealth AST 영구 가드', () => {
  it('HIGH-7: TARGET_PAGES literal 영역에 RealtimeHealth.tsx 영구 추가', () => {
    const astFilepath = path.join(
      __dirname,
      '_ast_useQuery_retry_required.test.ts',
    )
    expect(existsSync(astFilepath)).toBe(true)

    const source = readFileSync(astFilepath, 'utf-8')

    // 사이클 103 영역 0 = TARGET_PAGES 영역에 RealtimeHealth.tsx 영구 추가 의무
    expect(
      source.includes("'RealtimeHealth.tsx'"),
      '[G-AST-RT 영역 확장 영속 실패] _ast_useQuery_retry_required.test.ts 의 ' +
        "TARGET_PAGES literal 영역에 'RealtimeHealth.tsx' 영구 영속 의무 영역 " +
        '(사이클 85 G-AST-RT StockMaster.tsx 영구 영속 패턴 답습).',
    ).toBe(true)
  })

  it('HIGH-8.1: RealtimeHealth.tsx 페이지 영역 영속', () => {
    const pageFilepath = path.join(
      __dirname,
      '..',
      '..',
      'pages',
      'RealtimeHealth.tsx',
    )

    expect(
      existsSync(pageFilepath),
      '[G-AST-MOCK 영역 영속 실패] RealtimeHealth.tsx 페이지 영구 영속 의무 영역 ' +
        '(사이클 103 영역 0 = 신규 페이지 신설 의무).',
    ).toBe(true)
  })

  it('HIGH-8.2: RealtimeHealth API 영역 영속 (4 카드 데이터 조회 영역)', () => {
    const apiFilepath = path.join(
      __dirname,
      '..',
      '..',
      'api',
      'realtime-health.ts',
    )

    expect(
      existsSync(apiFilepath),
      '[G-AST-MOCK API 영역 영속 실패] api/realtime-health.ts 영구 영속 의무 영역 ' +
        '(사이클 103 영역 0 = 4 카드 함수 영역 영속 = ' +
        'fetchDispatchDropLogs / fetchCallbackExceptionLogs / ' +
        'fetchStaleForceRetryLogs / fetchWsAutoRestartLogs).',
    ).toBe(true)
  })

  it('HIGH-8.3: e2e api-mocks 영역 RealtimeHealth 라우트 영속 (LIFO 정합)', () => {
    const apiMocksFilepath = path.join(
      __dirname,
      '..',
      '..',
      '..',
      '..',
      'e2e',
      'fixtures',
      'api-mocks.ts',
    )

    if (!existsSync(apiMocksFilepath)) {
      // e2e fixtures 영역 영속 의무 (사이클 80 hotfix #3 영속)
      throw new Error(
        '[G-AST-MOCK LIFO 영역 영속 실패] e2e/fixtures/api-mocks.ts 영역 영속 의무 영역.',
      )
    }

    const source = readFileSync(apiMocksFilepath, 'utf-8')

    // 사이클 103 영역 0 = 4 carddata 영역 endpoint group 등록 영구 영속
    // (실제 영역 = `/api/logs/search?q=[dispatch_drop_summary]` 영역 활용)
    const hasRealtimeHealthRoute =
      source.includes('dispatch_drop_summary') ||
      source.includes('realtime-health') ||
      source.includes('callback_exception')

    expect(
      hasRealtimeHealthRoute,
      '[G-AST-MOCK 영역 영속 실패] e2e/fixtures/api-mocks.ts 영역에 ' +
        '4 prefix endpoint group 영역 영속 의무 영역 (사이클 80 hotfix #3 LIFO 정합).',
    ).toBe(true)
  })
})
