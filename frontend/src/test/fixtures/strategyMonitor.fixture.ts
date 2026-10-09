/**
 * cycle414 — 전략 진행상황 화면 고정 데이터(명세 §9 「MSW 고정 데이터 — 실제 키 목록」).
 *
 * 값은 합성이지만 **키 이름은 백엔드 그대로**다:
 *  - `/api/trading/status` `strategies.<id>` = `strategy_registry.get_strategies_status()` 의 키 +
 *    전략별 `get_targets_status()`·`get_scan_stats()`·`buy_signals[i]` 키(etf `line` · donchian `donchian_high` ·
 *    VCP `base_high` · BFB `flag_high` · kojiro `stage` · VB `target_price`).
 *  - `/api/strategies/monitor` = 명세 §3.2 모양(라우트 `src/routes/strategies.py::get_strategies_monitor`).
 *  - `/api/balance/exit-lines` = cycle412 G1 모양(item 14키).
 *
 * 기본 시각 = KST 2026-10-12(월) 09:12. 운영 상태를 흉내 낸다 — 8전략 중 5전략 신규 매수 멈춤(10-08~12) ·
 * VB 섀도(비중 0 + 켜짐) · LTV 꺼짐 · 모멘텀은 켜짐 비중 0.03(멈춤 아님 — 명세 C4, 화면은 데이터로만 판정).
 *
 * 테스트는 `makeStatus()`·`makeMonitor()` 를 깊은 복사로 받아 필요한 칸만 바꾼다.
 */

export const KST_0912 = new Date('2026-10-12T09:12:00+09:00')

export const ETF_A = '069500'
export const ETF_B = '229200'
export const ETF_HELD = '102110'
export const DC_CAND = '005930'
export const DC_HELD = '000660'
export const VCP_A = '006120'
export const BFB_A = '003160'
export const KJ_HELD = '000520'
export const VB_A = '010170'

type Dict = Record<string, unknown>

function baseStrategy(over: Dict): Dict {
  return {
    name: '',
    enabled: true,
    weight: 0.1,
    params: {},
    tradable_boards: ['main'],
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    total_investment: 1_000_000,
    daily_realized_pnl: 0,
    buy_disabled: false,
    buy_signals: [],
    positions_detail: {},
    pending_buy_tickers: [],
    scanned_tickers: [],
    scanned_count: 0,
    targets: {},
    scan_stats: null,
    invested_amount: 0,
    min_weight: 0,
    ...over,
  }
}

export function makeStatusStrategies(): Record<string, Dict> {
  return {
    etf_trend: baseStrategy({
      name: 'ETF 추세',
      weight: 0.12,
      total_investment: 600_000,
      invested_amount: 300_000,
      params: {
        buy_paused: true, shadow_mode: false, market_unit_mode: 'shadow', max_positions: 4,
        gap_skip_threshold: 3.0, gap_over_line_pct: 4.0, atr_ratio_min: 0.01, atr_ratio_max: 0.06,
        breakout_fail_min_bars: 2, breakout_fail_price_max_age_secs: 180, turtle_backstop_pct: -9.0,
        stop_atr: 2.0, breakeven_promote_atr: 1.5, atr_trail_mult: 1.8, cluster_corr_threshold: 0.9,
        sizing_mode: 'turtle', risk_pct: 0.01, position_ratio: 0.25,
      },
      positions: 1,
      position_tickers: [ETF_HELD],
      positions_detail: {
        [ETF_HELD]: { name: 'KODEX 반도체', buy_price: 10_000, quantity: 30, high_since_buy: 10_800,
          buy_date: '2026-10-07', is_next_day: false },
      },
      scanned_tickers: [ETF_A, ETF_B],
      scanned_count: 2,
      targets: {
        [ETF_A]: { prev_close: 10_000, target_price: 9_950 },
        [ETF_B]: { prev_close: 20_000, target_price: 19_800 },
      },
      scan_stats: { universe: 41, candidates: 2, clusters: 1, last_run_at: '2026-10-12T07:46:02+09:00' },
      buy_signals: [],
    }),
    donchian_swing: baseStrategy({
      name: '돈키언 추세 스윙',
      weight: 0.2,
      total_investment: 1_000_000,
      invested_amount: 500_000,
      params: {
        buy_paused: true, shadow_mode: false, market_unit_mode: 'shadow', max_positions: 6,
        gap_skip_threshold: 3.0, max_breakout_extension_pct: 3.0, kk_r_floor_pct: 8.0, kk_r_atr_mult: 1.5,
        kk_breakeven_r: 3.0, kk_time_exit_bars: 20, kk_time_exit_min_r: 1.0, kk_max_hold_bars: 250,
        max_daily_entries: 3, channel_exit_period: 10, sizing_mode: 'turtle',
      },
      positions: 1,
      position_tickers: [DC_HELD],
      positions_detail: {
        [DC_HELD]: { name: 'SK하이닉스', buy_price: 100_000, quantity: 5, high_since_buy: 104_000,
          buy_date: '2026-09-14', is_next_day: false },
      },
      scanned_tickers: [DC_CAND],
      scanned_count: 1,
      targets: {
        [DC_CAND]: { prev_close: 50_000, atr: 1_500, ema60: 45_000, donchian_high: 49_500, k: 0,
          target_price: 49_500, open_price: 0, target_offset: 0, open_confirmed: true },
      },
      scan_stats: {
        universe_union: 400, universe_candidates: 380, universe_filtered: 300, candle_fetch_ok: 290,
        donchian_pass: 12, ema_uptrend_pass: 6, volume_pass: 3, atr_pass: 3, final_prepared: 3,
        last_run_at: '2026-10-12T07:46:30+09:00',
      },
    }),
    vcp_breakout: baseStrategy({
      name: 'VCP 변동성 수축',
      weight: 0.1,
      params: {
        buy_paused: false, shadow_mode: false, market_unit_mode: 'shadow', max_positions: 5,
        entry_start: '09:05', entry_end: '14:30', max_breakout_extension_pct: 7.5, breakout_volume_mult: 1.5,
      },
      scanned_tickers: [VCP_A],
      scanned_count: 1,
      targets: {
        [VCP_A]: { base_high: 10_000, base_low: 9_300, atr14: 300, ema50: 9_100, name: '한미반도체',
          prev_close: 9_900, stop_line: 9_300, volume_threshold: 100_000, bought_today: false,
          in_cooldown: false, cooldown_until: null, k: 0, target_price: 10_000, open_price: 0,
          target_offset: 0, open_confirmed: true },
      },
      scan_stats: {
        universe_union: 2000, universe_candidates: 900, universe_filtered: 850, candle_fetch_ok: 800,
        mcap_pass: 800, trend_filter_pass: 40, base_pass: 9, pullback_pass: 8, volume_contraction_pass: 8,
        final_prepared: 8, vol_gate_pass: 0, vol_gate_reject_ext: 0, vol_gate_no_data: 0, latch_armed_count: 1,
        last_run_at: '2026-10-12T07:47:00+09:00',
      },
    }),
    bull_flag_breakout: baseStrategy({
      name: '추세 눌림목 돌파',
      weight: 0.1,
      params: {
        buy_paused: false, shadow_mode: false, market_unit_mode: 'shadow', max_positions: 5,
        entry_start: '09:05', entry_end: '13:00', max_breakout_extension_pct: 5.0,
        breakout_retention_minutes: 0, breakout_volume_mult: 2.0,
      },
      scanned_tickers: [BFB_A],
      scanned_count: 1,
      targets: {
        [BFB_A]: { pole_start: 9_000, pole_high: 10_400, flag_high: 10_200, flag_low: 9_400, atr14: 300,
          name: 'CJ씨푸드', prev_close: 10_000, stop_line: 9_400, measured_target: 11_600, volume_threshold: 100_000,
          bought_today: false, in_cooldown: false, cooldown_until: null, breakout_seen_at: null,
          retention_minutes: 0, k: 0, target_price: 10_200, open_price: 0, target_offset: 0, open_confirmed: true },
      },
      scan_stats: {
        universe_union: 2000, universe_candidates: 900, universe_filtered: 850, candle_fetch_ok: 800,
        pole_pass: 30, flag_pass: 6, volume_contraction_pass: 4, atr_pass: 4, final_prepared: 4,
        breakout_seen_count: 0, breakout_retreat_count: 0, last_run_at: '2026-10-12T07:47:10+09:00',
      },
    }),
    kojiro: baseStrategy({
      name: '고지로 대순환',
      weight: 0.3,
      params: {
        buy_paused: true, shadow_mode: false, market_unit_mode: 'shadow', max_positions: 5,
        stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0, breakeven_promote_atr: 1.5,
        atr_ratio_min: 0.01, atr_ratio_max: 0.06, stage1_freshness: 5, gap_up_skip_pct: 5.0, gap_down_skip_pct: -4.0,
      },
      positions: 1,
      position_tickers: [KJ_HELD],
      positions_detail: {
        [KJ_HELD]: { name: '대원제약', buy_price: 10_000, quantity: 3, high_since_buy: 10_500,
          buy_date: '2026-10-06', is_next_day: false },
      },
      targets: {},
      scan_stats: {
        universe_union: 348, universe_candidates: 95, universe_filtered: 90, candle_fetch_ok: 88, band_pass: 40,
        stage_valid_pass: 38, stage1_uptrend_pass: 6, strict_entry_pass: 0, final_prepared: 0,
        last_run_at: '2026-10-12T07:47:30+09:00',
      },
    }),
    volatility_breakout: baseStrategy({
      name: '변동성 돌파',
      weight: 0,
      total_investment: 0,
      params: { buy_paused: false, shadow_mode: true, max_positions: 3 },
      scanned_tickers: [VB_A],
      scanned_count: 31,
      targets: {
        [VB_A]: { k: 0.5, target_price: 10_500, open_price: 10_000, target_offset: 500,
          boards: { main: { open_price: 10_000, target_price: 10_500, target_offset: 500, confirmed: true } },
          open_confirmed: { main: true } },
      },
      scan_stats: {
        universe_candidates: 60, universe_filtered: 55, candle_fetch_ok: 50, k_value_computed: 31, final_prepared: 31,
        last_run_at: '2026-10-12T07:48:00+09:00',
      },
    }),
    momentum: baseStrategy({
      name: '모멘텀',
      weight: 0.03,
      params: { max_positions: 4 },
    }),
    long_tail_volatility: baseStrategy({
      name: '롱테일 변동성',
      enabled: false,
      weight: 0,
      total_investment: 0,
      params: { buy_paused: false, shadow_mode: false, max_positions: 3 },
    }),
  }
}

export function makeStatus(strategies: Record<string, Dict> = makeStatusStrategies()): Dict {
  return {
    running: true,
    is_running: true,
    env: 'real',
    board: 'main',
    phase: 'main_trading',
    positions: 3,
    pending_buys: 0,
    position_tickers: [ETF_HELD, DC_HELD, KJ_HELD],
    scan: {
      filtered_tickers: [], filtered_count: 0,
      subscribed_tickers: [ETF_A, ETF_B, ETF_HELD, DC_CAND, DC_HELD, VCP_A, BFB_A, KJ_HELD, VB_A],
      subscribed_count: 9, last_scan_time: '09:10:00',
      ticker_names: { [ETF_A]: 'KODEX 200', [ETF_B]: 'TIGER 반도체', [ETF_HELD]: 'KODEX 반도체', [DC_CAND]: '삼성전자',
        [DC_HELD]: 'SK하이닉스', [VCP_A]: '한미반도체', [BFB_A]: 'CJ씨푸드', [KJ_HELD]: '대원제약', [VB_A]: '대한광통신' },
      ticker_prices: {
        [ETF_A]: { current_price: 10_350, open_price: 10_299, change_rate: 3.5, prdy_ctrt: 3.5 },
        [ETF_B]: { current_price: 20_100, open_price: 20_050, change_rate: 0.5, prdy_ctrt: 0.5 },
        [ETF_HELD]: { current_price: 10_700, open_price: 10_650, change_rate: 1.0, prdy_ctrt: 1.0 },
        [DC_CAND]: { current_price: 50_500, open_price: 50_200, change_rate: 1.0, prdy_ctrt: 1.0 },
        [DC_HELD]: { current_price: 103_000, open_price: 102_000, change_rate: 0.5, prdy_ctrt: 0.5 },
        [VCP_A]: { current_price: 10_200, open_price: 9_950, change_rate: 3.0, prdy_ctrt: 3.0 },
        [BFB_A]: { current_price: 10_100, open_price: 10_050, change_rate: 1.0, prdy_ctrt: 1.0 },
        [KJ_HELD]: { current_price: 10_300, open_price: 10_250, change_rate: 0.3, prdy_ctrt: 0.3 },
      },
      ticker_market_info: {},
    },
    positions_detail: {},
    orders: { pending_buy_tickers: [], pending_buy_orders: {}, fills: {}, pending_cancels: [] },
    strategy: { buy_disabled: false, daily_realized_pnl: 0, total_investment: 0, buy_signals: [] },
    strategies,
  }
}

function funnelRows(names: Array<[number, string, number]>) {
  return names.map(([step_no, step_name, survived_count]) => ({
    step_no, step_name, step_conditions: `조건-${step_no}`, survived_count, excluded_count: 0,
  }))
}

const PREPARE_OK = {
  as_of: '2026-10-12', phase: 'boot', started_at: '2026-10-12T07:45:10+09:00',
  finished_at: '2026-10-12T07:46:02+09:00', ok: true,
}

const tick = (t: string) => ({ last_tick_at: `2026-10-12T09:11:5${t}+09:00`, acml_vol: null as number | null })

export function makeMonitorEntries(): Record<string, Dict> {
  return {
    etf_trend: {
      prepare: PREPARE_OK,
      funnel: funnelRows([
        [1, 'ETF 전체 → 국내주식형·1배 → 투자유의 제외 → 시총 통과', 41], [2, '일봉 품질 통과', 38],
        [3, '유동성·ATR 밴드 통과', 20], [4, '20일 신고가 돌파', 3], [5, 'EMA60 우상향 통과', 2],
        [6, '거래대금 확대 통과', 2], [99, '최종 후보', 2],
      ]),
      market_unit: { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling', bar_date: '2026-10-08' },
      skips: { known: true, day: '2026-10-12', counts: {}, by_ticker: {} },
      paused_skips: [ETF_A],
      shadow_buys: [],
      ticks: { [ETF_A]: tick('0'), [ETF_B]: tick('1'), [ETF_HELD]: tick('2') },
      candidates: {
        [ETF_A]: { line: 9_950, prev_close: 10_000, n: 150, atr20: 160, tv20: 5_000_000_000, ema60: 9_500,
          design_qty: 250, cluster_partners: [], cluster_blocked: false },
        [ETF_B]: { line: 19_800, prev_close: 20_000, n: 300, atr20: 310, tv20: 3_000_000_000, ema60: 19_000,
          design_qty: 0, cluster_partners: [ETF_HELD], cluster_blocked: true },
      },
      holdings: {
        [ETF_HELD]: {
          entry_n: 200, hsb_closed: 10_600, bars_since_buy: 2,
          lines: { hard: 9_600, breakeven: 10_000, trail: 10_240, channel: 10_100 },
          breakout_fail: { line: 9_900, active: true },
          effective_stop: 10_240,
        },
      },
      extra: {},
    },
    donchian_swing: {
      prepare: PREPARE_OK,
      funnel: funnelRows([
        [1, '코스피200+코스닥150 합집합', 400], [2, '시총+거래대금 컷 통과', 380], [3, '진입 차단 13건 통과', 300],
        [4, '일봉 fetch + 전일종가>0', 290], [5, '20일 신고가 돌파', 12], [6, '60일 EMA 우상향', 6],
        [7, '거래대금 확대', 3], [8, 'ATR(14) > 0', 3], [99, '최종 후보', 3],
      ]),
      market_unit: { mode: 'shadow', ok: false, reason: 'not_computed' },
      skips: { known: true, day: '2026-10-12', counts: {}, by_ticker: {} },
      paused_skips: [],
      shadow_buys: [],
      ticks: { [DC_CAND]: tick('3'), [DC_HELD]: tick('4') },
      candidates: { [DC_CAND]: { r_won: 4_000, r_pct: 8.0, design_lot: 2 } },
      holdings: {
        [DC_HELD]: {
          r_won: 8_000, stop: 92_000, armed: false, channel: null, arm_price: 124_000,
          target_1r: 108_000, reached_1r: false, days_held: 16, days_fallback: false,
          time_exit_bars: 20, max_hold_bars: 250,
        },
      },
      extra: { daily_entries: { count: 0, cap: 3 } },
    },
    vcp_breakout: {
      prepare: PREPARE_OK,
      funnel: funnelRows([
        [1, '전체 상장 유니버스', 2000], [2, '시총·거래대금 컷 통과', 900], [3, '유니버스 확정', 850],
        [4, '일봉 fetch', 800], [5, '단기/중기/장기 EMA 정렬', 40], [6, '베이스 자동 검출', 9],
        [7, 'Pullback 점진 수축', 8], [8, '거래량 수축', 8], [99, '최종 후보', 8],
      ]),
      market_unit: { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling', bar_date: '2026-10-08' },
      skips: { known: true, day: '2026-10-12', counts: {}, by_ticker: {} },
      paused_skips: [],
      shadow_buys: [],
      ticks: { [VCP_A]: { last_tick_at: '2026-10-12T09:11:58+09:00', acml_vol: 150_000 } },
      candidates: { [VCP_A]: { latch_armed_at: null, first_cross_at: null, max: null } },
      holdings: {},
      extra: {},
    },
    bull_flag_breakout: {
      prepare: PREPARE_OK,
      funnel: funnelRows([[1, '전체 상장 유니버스', 2000], [5, '폴 자동 검출', 30], [99, '최종 후보', 4]]),
      market_unit: { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling', bar_date: '2026-10-08' },
      skips: { known: true, day: '2026-10-12', counts: {}, by_ticker: {} },
      paused_skips: [],
      shadow_buys: [],
      ticks: { [BFB_A]: { last_tick_at: '2026-10-12T09:11:58+09:00', acml_vol: 120_000 } },
      candidates: { [BFB_A]: { latch_armed_at: null } },
      holdings: {},
      extra: {},
    },
    kojiro: {
      prepare: PREPARE_OK,
      funnel: funnelRows([
        [1, '전체 상장 유니버스', 348], [5, 'ATR/종가 변동성 밴드', 40], [8, '6→1 전환 인접', 0], [99, '최종 후보', 0],
      ]),
      market_unit: { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling', bar_date: '2026-10-08' },
      skips: { known: false },
      paused_skips: [],
      shadow_buys: [],
      ticks: { [KJ_HELD]: tick('5') },
      candidates: {},
      holdings: {},
      extra: {},
    },
    volatility_breakout: {
      prepare: PREPARE_OK,
      funnel: funnelRows([[1, '시총+거래대금 컷 통과', 60], [99, '최종 후보', 31]]),
      market_unit: null,
      skips: { known: false },
      paused_skips: [],
      shadow_buys: [VB_A, '000250'],
      ticks: {},
      candidates: {},
      holdings: {},
      extra: {},
    },
    momentum: {
      prepare: null, funnel: [], market_unit: null, skips: { known: false }, paused_skips: [],
      shadow_buys: [], ticks: {}, candidates: {}, holdings: {}, extra: {},
    },
    long_tail_volatility: {
      prepare: null, funnel: [], market_unit: null, skips: { known: false }, paused_skips: [],
      shadow_buys: [], ticks: {}, candidates: {}, holdings: {}, extra: {},
    },
  }
}

export function makeMonitor(entries: Record<string, Dict> = makeMonitorEntries()): Dict {
  return { as_of: '2026-10-12T09:12:03+09:00', running: true, strategies: entries }
}

export function makeExitLines(): Dict {
  const item = (strategy_id: string, ticker: string, o: Dict) => ({
    strategy_id, ticker, stop_price: null, stop_source: 'effective', target_price: null, target_source: null,
    buy_price: 10_000, quantity: 1, high_since_buy: 10_000, buy_date: '2026-10-06', order_no: `O-${ticker}`,
    entry_atr: null, kk_armed: null, kk_arm_price: null, ...o,
  })
  return {
    running: true,
    as_of: '2026-10-12T09:12:03+09:00',
    items: [
      item('etf_trend', ETF_HELD, { stop_price: 10_240, buy_price: 10_000, quantity: 30, high_since_buy: 10_800,
        buy_date: '2026-10-07', entry_atr: 200 }),
      item('donchian_swing', DC_HELD, { stop_price: 92_000, buy_price: 100_000, quantity: 5, high_since_buy: 104_000,
        buy_date: '2026-09-14', entry_atr: 3_000, kk_armed: false, kk_arm_price: 124_000 }),
      item('kojiro', KJ_HELD, { stop_price: 9_600, buy_price: 10_000, quantity: 3, high_since_buy: 10_500,
        entry_atr: 400 }),
    ],
  }
}

/** `/api/strategy-funnel/recent` — 최종(step_no=99) 생존 수 14일. 마지막 이틀 0(0 연속 2일). */
export function makeFunnelRecent(strategyId: string): Dict {
  const counts = [3, 2, 2, 4, 1, 0, 2, 3, 2, 1, 2, 3, 0, 0]
  const days = ['09-21', '09-22', '09-23', '09-26', '09-29', '09-30', '10-01', '10-02', '10-06', '10-07', '10-08',
    '10-10', '10-11', '10-12']
  return {
    strategy_id: strategyId,
    days: 14,
    snapshots: counts.map((c, i) => ({
      id: `${strategyId}-${i}`, target_date: `2026-${days[i]}`, strategy_id: strategyId, step_no: 99,
      step_name: '최종 후보', step_conditions: null, survived_count: c, excluded_count: 0,
      survived_tickers: null, excluded_sample: null, is_provisional: false,
    })),
  }
}

export function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}
