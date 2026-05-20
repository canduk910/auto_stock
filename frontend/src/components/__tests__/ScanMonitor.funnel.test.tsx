/**
 * 사이클 21 (2026-05-20) Red — ScanMonitor 전략별 깔때기 시각화.
 *
 * donchian_swing 의 SWING_STAGES 패턴을 VB/LTV/momentum 까지 확장.
 * `scan_stats` 가 백엔드에서 노출되면 ScanFunnelBars 컴포넌트로 동일 시각화.
 *
 * 요구 행위:
 * - C21-FA: VB 탭에서 scan_stats 가 있으면 `vb-scan-funnel` 컨테이너 노출
 * - C21-FB: VB 깔때기는 8단계 (universe_candidates → final_prepared) 표시
 * - C21-FC: LTV 깔때기는 9단계 (consecutive_limit_pass 포함)
 * - C21-FD: momentum 깔때기는 6단계 (rate_pass → limit_up_excluded → final_prepared)
 * - C21-FE: scan_stats 미반영 (null) → "아직 스캔 전" fallback 메시지
 * - C21-FF: BFB/VCP 도 scan_stats 8단계 깔때기 노출
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import ScanMonitor from '../ScanMonitor'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function makeStatusWithStrategy(sid: string, scan_stats: Record<string, unknown> | null) {
  return wrap({
    running: true,
    env: 'vts',
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    phase: 'main_trading',
    scan: {
      filtered_tickers: [],
      filtered_count: 0,
      subscribed_tickers: [],
      subscribed_count: 0,
      last_scan_time: '2026-05-20T09:30:00',
      ticker_names: {},
      ticker_prices: {},
      ticker_market_info: {},
      tick_coverage_total: 0,
      tick_coverage_acked: 0,
      tick_coverage_fresh: 0,
      tick_coverage_stale: 0,
    },
    positions_detail: {},
    orders: {
      pending_buy_tickers: [],
      pending_buy_orders: {},
      fills: {},
      pending_cancels: [],
    },
    strategy: {
      buy_disabled: false,
      daily_realized_pnl: 0,
      total_investment: 0,
      buy_signals: [],
    },
    strategies: {
      [sid]: {
        name: sid,
        enabled: true,
        weight: 0.3,
        params: {},
        tradable_boards: ['main'],
        positions: 0,
        pending_buys: 0,
        position_tickers: [],
        total_investment: 0,
        daily_realized_pnl: 0,
        buy_disabled: false,
        buy_signals: [],
        positions_detail: {},
        pending_buy_tickers: [],
        scanned_tickers: [],
        scanned_count: 0,
        targets: {},
        scan_stats,
        invested_amount: 0,
        min_weight: 0,
      },
    },
  })
}

async function renderWithStrategy(sid: string, scan_stats: Record<string, unknown> | null) {
  const status = makeStatusWithStrategy(sid, scan_stats)
  server.use(
    http.get('/api/trading/status', () => HttpResponse.json(status)),
  )
  render(
    <TestProviders>
      <TradingStatusProvider>
        <ScanMonitor selectedStrategy={sid} />
      </TradingStatusProvider>
    </TestProviders>,
  )
  await screen.findByText(/구독 중/)
}

describe('ScanMonitor — 사이클 21 전략별 깔때기', () => {
  it('C21-FA: VB 탭 + scan_stats → vb-scan-funnel 컨테이너 노출', async () => {
    const stats = {
      universe_candidates: 41,
      universe_filtered: 23,
      price_filtered: 35,
      mcap_pass: 30,
      trade_amount_pass: 28,
      candle_fetch_ok: 23,
      k_value_computed: 18,
      final_prepared: 18,
      last_run_at: '2026-05-20T08:00:00+09:00',
    }
    await renderWithStrategy('volatility_breakout', stats)

    const funnel = await screen.findByTestId('vb-scan-funnel')
    expect(funnel).toBeTruthy()
  })

  it('C21-FB: VB 깔때기 — 8단계 표시 (universe_candidates → final_prepared)', async () => {
    const stats = {
      universe_candidates: 41,
      universe_filtered: 23,
      price_filtered: 35,
      mcap_pass: 30,
      trade_amount_pass: 28,
      candle_fetch_ok: 23,
      k_value_computed: 18,
      final_prepared: 18,
      last_run_at: '2026-05-20T08:00:00+09:00',
    }
    await renderWithStrategy('volatility_breakout', stats)

    const funnel = await screen.findByTestId('vb-scan-funnel')
    // 각 단계 카운트 (텍스트 매칭)
    expect(funnel.textContent).toContain('41')
    expect(funnel.textContent).toContain('23')
    expect(funnel.textContent).toContain('18')
    // 단계 라벨 (예: 시총컷, 거래대금컷)
    expect(funnel.textContent).toMatch(/시총|거래대금|K값/)
  })

  it('C21-FC: LTV 깔때기 — 9단계 (consecutive_limit_pass 포함)', async () => {
    const stats = {
      universe_candidates: 30,
      universe_filtered: 15,
      price_filtered: 25,
      mcap_pass: 20,
      trade_amount_pass: 17,
      candle_fetch_ok: 15,
      consecutive_limit_pass: 13,
      k_value_computed: 10,
      final_prepared: 10,
      last_run_at: '2026-05-20T08:00:00+09:00',
    }
    await renderWithStrategy('long_tail_volatility', stats)

    const funnel = await screen.findByTestId('ltv-scan-funnel')
    expect(funnel).toBeTruthy()
    // 연속상한가 라벨 또는 단계 13 카운트
    expect(funnel.textContent).toMatch(/연속상한가|13/)
  })

  it('C21-FD: momentum 깔때기 — 6단계', async () => {
    const stats = {
      universe_candidates: 50,
      rate_pass: 30,
      mcap_pass: 25,
      trade_amount_pass: 20,
      limit_up_excluded: 2,
      final_prepared: 18,
      last_run_at: '2026-05-20T09:30:00+09:00',
    }
    await renderWithStrategy('momentum', stats)

    const funnel = await screen.findByTestId('momentum-scan-funnel')
    expect(funnel).toBeTruthy()
    expect(funnel.textContent).toContain('50')
    expect(funnel.textContent).toContain('18')
    expect(funnel.textContent).toMatch(/등락률|상한가|제외/)
  })

  it('C21-FE: scan_stats = null → fallback "아직 스캔 전"', async () => {
    await renderWithStrategy('volatility_breakout', null)

    // VB 탭 진입했으나 scan_stats 가 null
    await waitFor(() => {
      const all = screen.queryAllByText(/아직 스캔 전|N\/A|--/i)
      expect(all.length).toBeGreaterThan(0)
    })
  })

  it('C21-FF: bull_flag_breakout 깔때기 노출 (기존 universe 카운트 → 깔때기로 강화)', async () => {
    const stats = {
      universe_candidates: 35,
      universe_filtered: 20,
      candle_fetch_ok: 18,
      pole_pass: 12,
      flag_pass: 8,
      volume_contraction_pass: 6,
      atr_pass: 5,
      final_prepared: 5,
      last_run_at: '2026-05-20T08:00:00+09:00',
    }
    await renderWithStrategy('bull_flag_breakout', stats)

    const funnel = await screen.findByTestId('bfb-scan-funnel')
    expect(funnel).toBeTruthy()
  })
})
