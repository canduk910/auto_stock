/**
 * cycle418-M Red — suites N2: ScanMonitor 「스캔 요약」 칸의 `?? 0`.
 *
 * `/api/trading/status` 가 아직 응답하지 않은 순간(최초 로딩)에도 `strategies[k]?.scanned_count
 * ?? 0`·`scan?.filtered_count ?? 0`·`scan?.subscribed_count ?? 0` 가 숫자 0 을 보여 "스캔해서
 * 0 건"으로 오독된다 — 데이터가 아직 없으면(`status===undefined`) 「—」.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import ScanMonitor from '../ScanMonitor'

describe('N2(suites) — 상태 로딩 전 요약칸은 「—」(「0」 이 아니다)', () => {
  it('/api/trading/status 가 아직 응답하지 않으면 필터링·구독 요약칸이 0 이 아니다', () => {
    server.use(
      http.get('/api/trading/status', async () => {
        await delay('infinite')
        return HttpResponse.json({ success: true, data: {}, message: '' })
      }),
    )
    render(
      <TestProviders>
        <TradingStatusProvider>
          <ScanMonitor selectedStrategy="all" />
        </TradingStatusProvider>
      </TestProviders>,
    )
    // "필터링"/"모멘텀 필터" 라벨 옆 큰 숫자 칸 — 로딩 중엔 0 이 아니라 placeholder.
    const grid = screen.getByText(/구독 중/).closest('div')?.parentElement
    expect(grid?.textContent).not.toMatch(/^.*\b0\b.*구독 중/)
  })
})
