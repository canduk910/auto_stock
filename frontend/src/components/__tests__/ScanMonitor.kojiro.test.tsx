/**
 * 고지로(kojiro) 대시보드 시각화 배선 가드.
 *
 * - 통합: ScanMonitor kojiro 탭 → KojiroMonitor 6패널 렌더 (isKojiro 분기).
 * - 정적: StrategyFunnel STRATEGY_OPTIONS kojiro / STRATEGY_INFO kojiro / STRATEGY_COLORS kojiro.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import ScanMonitor from '../ScanMonitor'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const __dirname = dirname(fileURLToPath(import.meta.url))

function kojiroStatus() {
  return wrap({
    running: true, env: 'vts', positions: 0, pending_buys: 0, position_tickers: [],
    phase: 'main_trading',
    scan: {
      filtered_tickers: [], filtered_count: 0, subscribed_tickers: [], subscribed_count: 0,
      last_scan_time: '2026-07-17T21:00:00', ticker_names: {}, ticker_prices: {},
      ticker_market_info: {}, tick_coverage_total: 0, tick_coverage_acked: 0,
      tick_coverage_fresh: 0, tick_coverage_stale: 0,
    },
    positions_detail: {}, orders: { pending_buy_tickers: [], pending_buy_orders: {}, fills: {}, pending_cancels: [] },
    strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
    strategies: {
      kojiro: {
        name: '고지로 대순환', enabled: false, weight: 0,
        positions: 0, pending_buys: 0, position_tickers: [], total_investment: 0,
        daily_realized_pnl: 0, buy_disabled: false, buy_signals: [], positions_detail: {},
        pending_buy_tickers: [], scanned_count: 3, scanned_tickers: [],
        targets: {
          '005930': { prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 },
        },
        scan_stats: {
          universe_union: 348, universe_candidates: 95, universe_filtered: 90, candle_fetch_ok: 88,
          band_pass: 40, stage_valid_pass: 38, stage1_uptrend_pass: 6, strict_entry_pass: 3,
          final_prepared: 3, last_run_at: '2026-07-17T21:00:00+09:00',
        },
        params: { stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0, atr_ratio_min: 0.01, atr_ratio_max: 0.045 },
        invested_amount: 0, min_weight: 0, tradable_boards: ['main'],
      },
    },
  })
}

describe('ScanMonitor — kojiro 탭 통합', () => {
  it('kojiro 탭 → KojiroMonitor 6패널 렌더', async () => {
    server.use(http.get('/api/trading/status', () => HttpResponse.json(kojiroStatus())))
    render(
      <TestProviders>
        <TradingStatusProvider>
          <ScanMonitor selectedStrategy="kojiro" />
        </TradingStatusProvider>
      </TestProviders>,
    )
    expect(await screen.findByTestId('kojiro-monitor')).toBeTruthy()
    expect(screen.getByTestId('kojiro-darklaunch-banner')).toBeTruthy()
    expect(screen.getByTestId('kojiro-stage-cycle')).toBeTruthy()
    expect(screen.getByTestId('kojiro-scan-funnel')).toBeTruthy()
    expect(screen.getByTestId('kojiro-candidate-grid')).toBeTruthy()
    expect(screen.getByTestId('kojiro-entry-feed')).toBeTruthy()
    expect(screen.getByTestId('kojiro-defense-panel')).toBeTruthy()
    // 상단 요약 라벨 = 대순환 최종 후보
    expect(screen.getByText(/대순환 최종 후보/)).toBeTruthy()
  })
})

describe('kojiro 시각화 정적 배선 가드', () => {
  it('StrategyFunnel STRATEGY_OPTIONS 에 kojiro', () => {
    const src = readFileSync(resolve(__dirname, '..', '..', 'pages', 'StrategyFunnel.tsx'), 'utf-8')
    expect(src).toMatch(/id:\s*'kojiro'/)
    expect(src).toContain('고지로 대순환')
  })

  it('STRATEGY_INFO 에 kojiro 엔트리 (대순환 개념 + 다크런치 명시)', () => {
    const src = readFileSync(resolve(__dirname, '..', '..', 'utils', 'strategyInfo.ts'), 'utf-8')
    expect(src).toMatch(/kojiro:\s*{/)
    expect(src).toMatch(/대순환/)
    expect(src).toMatch(/다크런치|관찰/)
  })

  it('STRATEGY_COLORS 에 kojiro 색상', () => {
    const src = readFileSync(resolve(__dirname, '..', '..', 'types', 'strategy.ts'), 'utf-8')
    expect(src).toMatch(/kojiro:\s*{/)
  })
})
