/**
 * VCP(vcp_breakout)/BFB(bull_flag_breakout) 전용 후보 진단 그리드 회귀 가드 (2026-08-06).
 *
 * 배경: VCP 후보 0 (추세필터 97.9% 탈락) / BFB 후보 18 중 6종목(33%) WebSocket 미구독
 * — 기존 VB 재사용 타겟표는 "K값 0.000 · 시가 -" 만 보여줘 "왜 안 사는가"에 답하지 못했다.
 *
 * 검증: 구독 커버리지 배너(정상/경고) / 거리% 부호·색상 / 돌파선 근접순 정렬 /
 * 상태 배지 우선순위(매수완료>쿨다운>미구독>retention대기>대기) / BFB 측정목표 컬럼
 * (VCP 미렌더) / 후보 0 안내 / 종목명 폴백.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import BreakoutCandidateMonitor, { EntryWindowBadge } from '../BreakoutCandidateMonitor'
import type { BreakoutDiagTarget, StrategyInfo, TickerPrice } from '../../types/trading'

function makeStrategy(
  strategyId: 'vcp_breakout' | 'bull_flag_breakout',
  targets: Record<string, Partial<BreakoutDiagTarget>>,
): Record<string, StrategyInfo> {
  const filled: Record<string, BreakoutDiagTarget> = {}
  for (const [ticker, t] of Object.entries(targets)) {
    filled[ticker] = {
      prev_close: 0,
      atr14: 0,
      stop_line: 0,
      volume_threshold: 0,
      bought_today: false,
      in_cooldown: false,
      target_price: 0,
      ...t,
    }
  }
  const base: StrategyInfo = {
    name: strategyId === 'bull_flag_breakout' ? '눌림목 돌파' : 'VCP 변동성 수축',
    enabled: true,
    weight: 0.1,
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    total_investment: 1_000_000,
    daily_realized_pnl: 0,
    buy_disabled: false,
    buy_signals: [],
    positions_detail: {},
    pending_buy_tickers: [],
    scanned_count: Object.keys(filled).length,
    scanned_tickers: Object.keys(filled),
    targets: filled,
    scan_stats: {},
    params: {},
  }
  return { [strategyId]: base }
}

function price(p: number): TickerPrice {
  return { current_price: p, open_price: p, change_rate: 0, prdy_ctrt: 0 }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('BreakoutCandidateMonitor — 구독 커버리지 배너', () => {
  it('전량 구독 시 emerald 정상 톤', () => {
    const strategies = makeStrategy('bull_flag_breakout', {
      '005930': { target_price: 80000 },
      '000660': { target_price: 150000 },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={strategies}
        subscribedTickers={['005930', '000660']}
      />,
    )
    const banner = screen.getByTestId('breakout-subscription-coverage')
    expect(banner.textContent).toContain('후보 2종목 중 2종목 구독 · 0종목 시세 미수신')
    expect(banner.className).toMatch(/emerald/)
  })

  it('미구독 존재 시 amber 경고 + 안내문', () => {
    const strategies = makeStrategy('bull_flag_breakout', {
      '005930': { target_price: 80000 },
      '000660': { target_price: 150000 },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={strategies}
        subscribedTickers={['005930']}
      />,
    )
    const banner = screen.getByTestId('breakout-subscription-coverage')
    expect(banner.textContent).toContain('후보 2종목 중 1종목 구독 · 1종목 시세 미수신')
    expect(banner.className).toMatch(/amber/)
    expect(banner.textContent).toContain('매수 신호 평가 자체가 일어나지 않습니다')
  })
})

describe('BreakoutCandidateMonitor — 거리% 부호·색상 + 정렬', () => {
  it('양수 red / 음수 blue', () => {
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000 }, // 현재가 82000 → +2.50%
      '000660': { target_price: 150000 }, // 현재가 145000 → -3.33%
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="vcp_breakout"
        strategies={strategies}
        tickerPrices={{ '005930': price(82000), '000660': price(145000) }}
        subscribedTickers={['005930', '000660']}
      />,
    )
    const row1 = screen.getByTestId('breakout-candidate-row-005930')
    const row2 = screen.getByTestId('breakout-candidate-row-000660')
    const cell1 = within(row1).getByText('+2.50%')
    const cell2 = within(row2).getByText('-3.33%')
    expect(cell1.className).toMatch(/red/)
    expect(cell2.className).toMatch(/blue/)
  })

  it('현재가 미수신(0) → "-" 표시 + 정렬 최하단', () => {
    const strategies = makeStrategy('vcp_breakout', {
      no_price: { target_price: 80000 },
      near: { target_price: 100000 },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="vcp_breakout"
        strategies={strategies}
        tickerPrices={{ near: price(99000) }}
        subscribedTickers={['no_price', 'near']}
      />,
    )
    const rows = screen.getAllByTestId(/breakout-candidate-row-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'breakout-candidate-row-near',
      'breakout-candidate-row-no_price',
    ])
    // 거리% 컬럼(4번째 <td>) — 현재가 없으므로 distPct=null → "-"
    const cells = screen.getByTestId('breakout-candidate-row-no_price').querySelectorAll('td')
    expect(cells[3].textContent).toBe('-')
  })

  it('돌파선 근접순(거리% 내림차순) 정렬 — 이미 돌파 > 근접 > 멀리 이탈', () => {
    const strategies = makeStrategy('vcp_breakout', {
      far: { target_price: 100000 }, // 80000 → -20.00%
      near: { target_price: 100000 }, // 98000 → -2.00%
      above: { target_price: 100000 }, // 101000 → +1.00%
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="vcp_breakout"
        strategies={strategies}
        tickerPrices={{ far: price(80000), near: price(98000), above: price(101000) }}
        subscribedTickers={['far', 'near', 'above']}
      />,
    )
    const rows = screen.getAllByTestId(/breakout-candidate-row-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'breakout-candidate-row-above',
      'breakout-candidate-row-near',
      'breakout-candidate-row-far',
    ])
  })
})

describe('BreakoutCandidateMonitor — 상태 배지 우선순위', () => {
  it('매수완료가 최우선 (쿨다운/미구독 무관)', () => {
    const strategies = makeStrategy('bull_flag_breakout', {
      '005930': { target_price: 80000, bought_today: true, in_cooldown: true },
    })
    render(
      <BreakoutCandidateMonitor strategyId="bull_flag_breakout" strategies={strategies} subscribedTickers={[]} />,
    )
    expect(screen.getByTestId('breakout-status-005930').textContent).toBe('매수완료')
  })

  it('쿨다운 D-n 표시 (매수완료 아닐 때)', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-05T15:00:00Z')) // KST 2026-08-06 00:00
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000, in_cooldown: true, cooldown_until: '2026-08-09' },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="vcp_breakout"
        strategies={strategies}
        subscribedTickers={['005930']}
      />,
    )
    expect(screen.getByTestId('breakout-status-005930').textContent).toBe('쿨다운 D-3')
  })

  it('미구독 배지 (쿨다운 아닐 때)', () => {
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000 },
    })
    render(<BreakoutCandidateMonitor strategyId="vcp_breakout" strategies={strategies} subscribedTickers={[]} />)
    expect(screen.getByTestId('breakout-status-005930').textContent).toContain('미구독')
  })

  it('BFB retention 대기 — breakout_seen_at 경과 후 잔여 m:ss', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-06T00:16:30Z')) // seen 후 90초 경과
    const strategies = makeStrategy('bull_flag_breakout', {
      '005930': {
        target_price: 80000,
        breakout_seen_at: '2026-08-06T00:15:00Z',
        retention_minutes: 3,
      },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={strategies}
        subscribedTickers={['005930']}
      />,
    )
    // 총 180초 - 경과 90초 = 잔여 90초 = 1:30
    expect(screen.getByTestId('breakout-status-005930').textContent).toContain('1:30')
  })

  it('VCP 는 breakout_seen_at 무관 — retention 대기 배지 없음', () => {
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000 },
    })
    render(
      <BreakoutCandidateMonitor strategyId="vcp_breakout" strategies={strategies} subscribedTickers={['005930']} />,
    )
    expect(screen.getByTestId('breakout-status-005930').textContent).toBe('대기')
  })
})

describe('BreakoutCandidateMonitor — 측정목표 컬럼 (BFB 전용)', () => {
  it('BFB 는 측정목표 컬럼 렌더', () => {
    const strategies = makeStrategy('bull_flag_breakout', {
      '005930': { target_price: 80000, measured_target: 90000 },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="bull_flag_breakout"
        strategies={strategies}
        subscribedTickers={['005930']}
      />,
    )
    expect(screen.getByText('측정목표')).toBeInTheDocument()
    expect(screen.getByText('90,000')).toBeInTheDocument()
  })

  it('VCP 는 측정목표 컬럼 미렌더', () => {
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000 },
    })
    render(
      <BreakoutCandidateMonitor strategyId="vcp_breakout" strategies={strategies} subscribedTickers={['005930']} />,
    )
    expect(screen.queryByText('측정목표')).toBeNull()
  })
})

describe('BreakoutCandidateMonitor — 후보 0 / 종목명 폴백 / 빈 상태', () => {
  it('후보 0종목 → 안내 문구', () => {
    const strategies = makeStrategy('vcp_breakout', {})
    render(<BreakoutCandidateMonitor strategyId="vcp_breakout" strategies={strategies} subscribedTickers={[]} />)
    const grid = screen.getByTestId('breakout-candidate-grid')
    expect(grid.textContent).toMatch(/후보 0종목/)
    expect(grid.textContent).toMatch(/깔때기 화면에서 병목 단계를 확인/)
  })

  it('종목명 폴백 — name 미제공/빈문자 → ticker, 제공 시 종목명', () => {
    const strategies = makeStrategy('vcp_breakout', {
      '005930': { target_price: 80000 },
      '000660': { name: '', target_price: 150000 },
      '035420': { name: '네이버', target_price: 200000 },
    })
    render(
      <BreakoutCandidateMonitor
        strategyId="vcp_breakout"
        strategies={strategies}
        subscribedTickers={['005930', '000660', '035420']}
      />,
    )
    expect(screen.getByTestId('breakout-candidate-row-005930').querySelector('td')?.textContent).toBe('005930')
    expect(screen.getByTestId('breakout-candidate-row-000660').querySelector('td')?.textContent).toBe('000660')
    expect(screen.getByTestId('breakout-candidate-row-035420').querySelector('td')?.textContent).toBe('네이버')
  })

  it('전략 데이터 없음 → 빈 상태 안내 (장 외 시간에도 렌더 — 보드/시가 의존 없음)', () => {
    render(<BreakoutCandidateMonitor strategyId="vcp_breakout" strategies={{}} />)
    expect(screen.getByTestId('breakout-candidate-monitor-empty')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 진입 게이트 — 사이클 18 보드 불일치 라벨 대체 (2026-08-06)
//
// 후보가 아무리 좋아도 `entry_start ~ entry_end` 밖이면 `check_buy_signal` 이
// `Signal.NONE` 을 돌려준다. 체결 0건 진단에서 가장 먼저 배제해야 할 사유라
// 후보 그리드보다 **위**에 둔다.
// ---------------------------------------------------------------------------
describe('EntryWindowBadge', () => {
  const at = (hhmm: string) => new Date(`2026-08-06T${hhmm}:00+09:00`)

  it('시간창 안이면 진입 가능으로 표시한다', () => {
    render(<EntryWindowBadge params={{ entry_start: '09:05', entry_end: '13:00' }} now={at('10:30')} />)
    expect(screen.getByTestId('breakout-entry-window')).toHaveTextContent('진입 가능')
  })

  it('시간창 밖이면 매수 신호가 안 난다고 명시한다', () => {
    render(<EntryWindowBadge params={{ entry_start: '09:05', entry_end: '13:00' }} now={at('15:40')} />)
    expect(screen.getByTestId('breakout-entry-window')).toHaveTextContent('시간창 밖')
  })

  it('경계 시각은 포함(inclusive)이다', () => {
    const { rerender } = render(
      <EntryWindowBadge params={{ entry_start: '09:05', entry_end: '13:00' }} now={at('09:05')} />,
    )
    expect(screen.getByTestId('breakout-entry-window')).toHaveTextContent('진입 가능')
    rerender(<EntryWindowBadge params={{ entry_start: '09:05', entry_end: '13:00' }} now={at('13:00')} />)
    expect(screen.getByTestId('breakout-entry-window')).toHaveTextContent('진입 가능')
  })

  it('KST 로 판정한다 — 브라우저 로컬타임에 흔들리지 않는다', () => {
    // 2026-08-06 01:30 UTC = 10:30 KST → 진입창 안
    render(
      <EntryWindowBadge
        params={{ entry_start: '09:05', entry_end: '13:00' }}
        now={new Date('2026-08-06T01:30:00Z')}
      />,
    )
    expect(screen.getByTestId('breakout-entry-window')).toHaveTextContent('10:30')
  })

  it('파라미터가 없으면 추측하지 않고 렌더하지 않는다', () => {
    const { container } = render(<EntryWindowBadge params={{}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
