/**
 * 사이클 434 — 대시보드 경고등(`AlertLight.tsx`).
 *
 * 요구 행위:
 * - AL-1: 기본(green) — 점 + "정상" 라벨
 * - AL-2: red 상태 — "위험" 라벨 + 패널에 범주별 건수/시각/최근 메시지
 * - AL-3: yellow 상태 — "주의" 라벨
 * - AL-4: unknown 상태(DB 조회 실패) — "모름" 라벨, count 는 "모름"으로 표시(0 과 구분)
 * - AL-5: 네트워크/서버 오류 — "조회 실패" 라벨
 * - AL-6: 패널에 /logs 로 가는 링크가 있다
 * - AL-7: 바깥 클릭·Escape 로 패널이 닫힌다
 */
import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import AlertLight from '../AlertLight'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function category(
  key: string,
  label: string,
  color: 'red' | 'yellow',
  overrides: Partial<Record<string, unknown>> = {},
) {
  return {
    key,
    label,
    color,
    count: 0,
    max_level: null,
    first_at: null,
    last_at: null,
    recent_messages: [],
    ...overrides,
  }
}

const greenPayload = {
  as_of: '2026-10-10T12:00:00+09:00',
  status: 'green',
  categories: [
    category('ledger_mismatch', '장부 불일치', 'red'),
    category('order_unknown_or_exit_failure', '주문 결과 모름 · 청산 실패', 'red'),
    category('daily_job_failure', '일일 작업 실패', 'yellow'),
  ],
}

const redPayload = {
  as_of: '2026-10-10T12:00:00+09:00',
  status: 'red',
  categories: [
    category('ledger_mismatch', '장부 불일치', 'red', {
      count: 2,
      max_level: 'CRITICAL',
      first_at: '2026-10-10T09:30:00+09:00',
      last_at: '2026-10-10T11:00:00+09:00',
      recent_messages: [
        { level: 'CRITICAL', message: '[holding_qty_unexplained] ticker=005930 ...', timestamp: '2026-10-10T11:00:00+09:00' },
      ],
    }),
    category('order_unknown_or_exit_failure', '주문 결과 모름 · 청산 실패', 'red'),
    category('daily_job_failure', '일일 작업 실패', 'yellow'),
  ],
}

const yellowPayload = {
  as_of: '2026-10-10T12:00:00+09:00',
  status: 'yellow',
  categories: [
    category('ledger_mismatch', '장부 불일치', 'red'),
    category('order_unknown_or_exit_failure', '주문 결과 모름 · 청산 실패', 'red'),
    category('daily_job_failure', '일일 작업 실패', 'yellow', { count: 1, max_level: 'WARNING' }),
  ],
}

const unknownPayload = {
  as_of: '2026-10-10T12:00:00+09:00',
  status: 'unknown',
  categories: [
    category('ledger_mismatch', '장부 불일치', 'red', { count: null }),
    category('order_unknown_or_exit_failure', '주문 결과 모름 · 청산 실패', 'red', { count: null }),
    category('daily_job_failure', '일일 작업 실패', 'yellow', { count: null }),
  ],
}

describe('AlertLight', () => {
  it('AL-1: 기본(green) — 점 + 정상 라벨', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(greenPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('alert-light')).toHaveAttribute('data-status', 'green')
    })
    expect(screen.getByTestId('alert-light-label')).toHaveTextContent('정상')
  })

  it('AL-2: red 상태 — 위험 라벨 + 패널 범주별 건수/시각/최근 메시지', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(redPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('alert-light')).toHaveAttribute('data-status', 'red')
    })
    expect(screen.getByTestId('alert-light-label')).toHaveTextContent('위험')

    fireEvent.click(screen.getByTestId('alert-light'))
    expect(screen.getByTestId('alert-light-panel')).toBeInTheDocument()
    const cat = screen.getByTestId('alert-light-category-ledger_mismatch')
    expect(cat).toHaveTextContent('2건')
    expect(cat).toHaveTextContent('CRITICAL')
    expect(cat).toHaveTextContent('holding_qty_unexplained')
  })

  it('AL-3: yellow 상태 — 주의 라벨', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(yellowPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('alert-light')).toHaveAttribute('data-status', 'yellow')
    })
    expect(screen.getByTestId('alert-light-label')).toHaveTextContent('주의')
  })

  it('AL-4: unknown 상태 — 모름 라벨 + count 는 0 이 아니라 모름으로 표시', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(unknownPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('alert-light')).toHaveAttribute('data-status', 'unknown')
    })
    expect(screen.getByTestId('alert-light-label')).toHaveTextContent('모름')

    fireEvent.click(screen.getByTestId('alert-light'))
    const cat = screen.getByTestId('alert-light-category-daily_job_failure')
    expect(cat).toHaveTextContent('모름')
    expect(cat).not.toHaveTextContent('0건')
  })

  it('AL-5: 서버 오류 — 조회 실패 라벨', async () => {
    server.use(
      http.get('/api/system/alerts', () => new HttpResponse(null, { status: 500 })),
    )
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(
      () => {
        expect(screen.getByTestId('alert-light-label')).toHaveTextContent('조회 실패')
      },
      { timeout: 3000 },
    )
  })

  it('AL-6: 패널에 /logs 로 가는 링크가 있다', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(redPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => screen.getByTestId('alert-light'))
    fireEvent.click(screen.getByTestId('alert-light'))
    const link = screen.getByTestId('alert-light-logs-link')
    expect(link).toHaveAttribute('href', expect.stringContaining('/logs'))
  })

  it('AL-7: Escape 로 패널이 닫힌다', async () => {
    server.use(http.get('/api/system/alerts', () => HttpResponse.json(wrap(redPayload))))
    render(
      <TestProviders>
        <AlertLight />
      </TestProviders>,
    )
    await waitFor(() => screen.getByTestId('alert-light'))
    fireEvent.click(screen.getByTestId('alert-light'))
    expect(screen.getByTestId('alert-light-panel')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByTestId('alert-light-panel')).not.toBeInTheDocument()
    })
  })
})
