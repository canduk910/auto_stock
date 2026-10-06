/**
 * 2026-10-06 — Backtest(`/backtest`) 페이지 + 나브 메뉴 회귀 가드.
 *
 * 30년 전략 성적표 연구 보고서(frontend/public/backtest/scoreboard_30y.html)를
 * iframe 으로 감싸는 신규 화면. 명세 = 팀장 지시(사용자 승인 10-06).
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import Backtest from '../Backtest'
import { server } from '../../test/server'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SAMPLE_REPORT_HTML =
  '<!doctype html><html lang="ko"><head><title>30년 전략 성적표</title></head>' +
  '<body><script>const DATA = {"generated_kst":"2026-10-06 11:41","rows":[]};</script></body></html>'

describe('Backtest 페이지 — /backtest', () => {
  beforeEach(() => {
    server.use(
      http.get('/backtest/scoreboard_30y.html', () =>
        HttpResponse.text(SAMPLE_REPORT_HTML, { headers: { 'Content-Type': 'text/html' } }),
      ),
    )
  })

  afterEach(() => {
    server.resetHandlers()
  })

  it('로딩 중에는 스켈레톤을 보인다', () => {
    render(withProviders(<Backtest />))
    expect(screen.getByTestId('backtest-loading')).toBeDefined()
  })

  it('정상 응답이면 iframe 이 보고서 경로를 가리키고 생성 시각이 보인다', async () => {
    render(withProviders(<Backtest />))
    const iframe = await screen.findByTestId<HTMLIFrameElement>('backtest-iframe')
    expect(iframe.getAttribute('src')).toBe('/backtest/scoreboard_30y.html')
    await waitFor(() => {
      expect(screen.getByText(/생성 2026-10-06/)).toBeDefined()
    })
    // 실제 매매 설정과 무관하다는 안내 문구
    expect(screen.getByText(/실제 매매 설정과 무관합니다/)).toBeDefined()
    // 새 창에서 열기 링크
    const link = screen.getByText('새 창에서 열기 ↗') as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('/backtest/scoreboard_30y.html')
    expect(link.getAttribute('target')).toBe('_blank')
  })

  it('fetch 실패(네트워크/서버 오류) 시 서버 연결 끊김 메시지를 보인다', async () => {
    server.use(http.get('/backtest/scoreboard_30y.html', () => HttpResponse.error()))
    render(withProviders(<Backtest />))
    const err = await screen.findByTestId('backtest-error')
    expect(err.textContent).toMatch(/서버 연결 끊김/)
  })

  it('404 등 비정상 상태코드도 에러로 처리한다', async () => {
    server.use(http.get('/backtest/scoreboard_30y.html', () => new HttpResponse(null, { status: 404 })))
    render(withProviders(<Backtest />))
    const err = await screen.findByTestId('backtest-error')
    expect(err.textContent).toMatch(/서버 연결 끊김/)
  })

  it('빈 응답이면 안내 문구를 보인다', async () => {
    server.use(http.get('/backtest/scoreboard_30y.html', () => HttpResponse.text('')))
    render(withProviders(<Backtest />))
    const empty = await screen.findByTestId('backtest-empty')
    expect(empty.textContent).toMatch(/없습니다/)
  })

  it('generated_kst 를 못 찾아도 iframe 은 정상 렌더된다', async () => {
    server.use(
      http.get('/backtest/scoreboard_30y.html', () =>
        HttpResponse.text('<html><body>no generated_kst here</body></html>'),
      ),
    )
    render(withProviders(<Backtest />))
    const iframe = await screen.findByTestId('backtest-iframe')
    expect(iframe).toBeDefined()
    expect(screen.queryByText(/생성 /)).toBeNull()
  })
})
