/**
 * cycle413 — `GET /api/history/journal` 응답 픽스처(명세 `_workspace/red/cycle413/journal_view_spec.md` 1-2).
 *
 * 키 정본 = `tests/fixtures/cycle413_journal_shape.json` (백엔드 라우트 테스트와 같은 파일로 비교한다 —
 * `src/components/__tests__/handlers.honesty.cycle413.test.ts`). 빈칸 이유 5종(na)이 모두 한 번 이상 나온다.
 *
 * 카드 3장 = ① 보유 중 고지로(시세 대기·손절 정지·손절선 기록 시작 전 진입·종가 조회 실패)
 *           ② 닫힌 추세 눌림목(BFB) — 명세 8-2 와이어 그대로(실시간 진입·익절·손절선 변화 5줄)
 *           ③ 닫힌 변동성돌파 당일 15:20 청산(평가 해당 없음·고정% 손절선 근사)
 */

export const JOURNAL_ANCHOR_OPEN = 'aaaaaaaa-0000-4000-8000-000000000003'
export const JOURNAL_ANCHOR_BFB = 'aaaaaaaa-0000-4000-8000-000000000001'
export const JOURNAL_ANCHOR_VB = 'aaaaaaaa-0000-4000-8000-000000000005'

const CARD_OPEN = {
  pair_key: 'kojiro:035720:K1',
  anchor_trade_id: JOURNAL_ANCHOR_OPEN,
  strategy: 'kojiro',
  ticker: '035720',
  ticker_name: '카카오',
  status: 'open',
  opened_at: '2026-10-05T10:00:00.000000+09:00',
  closed_at: null,
  held_days: 4,
  record_notice: 'before_stops',
  pnl: {
    gross_krw: null, gross_rate_pct: null, net_krw: null, net_rate_pct: null, unrealized: true,
    partial_gross_krw: null, partial_net_krw: null, gross_na: 'pending', net_na: 'pending',
  },
  entry: {
    avg_price: 50000,
    qty: 10,
    orders: [
      {
        side: 'BUY', order_no: 'K1', trade_ids: [JOURNAL_ANCHOR_OPEN], at: '2026-10-05T10:00:00.000000+09:00',
        price: 50000, qty: 10, division: null, division_na: 'unknown', source: 'log_harvest', source_na: null,
        path: 'accept', parent_order_no: null,
        judge: { price: 49950, upper: null, src: 'signal', na: null },
        slip_order: { ref_price: 49950, ref_src: 'trade', per_share_won: 50, bp: 10.0, total_won: 500, bound: 'exact' },
        slip_order_na: null, slip_judge: null,
      },
    ],
    reason: {
      code: 'ENTRY', sub: null, phrase: null, renamed_from: null,
      text: '스테이지2 신규 진입 · 이평 정배열 · ATR 1,500', src: 'live', signal_src: 'ring', na: null,
    },
    initial_stop: {
      price: null, kind: null, pct_from_entry: null, observed_at: null, delay_s: null, na: 'before_record',
      first_seen: { price: 47800, kind: 'effective', observed_at: '2026-10-07T09:05:00+09:00' },
    },
    target: {
      kind: 'none', price: null, hit: null, signal_price: null, arm_price: null, one_r_price: null, armed_at: null,
      text: '없음 — 샹들리에 트레일·스테이지3 청산', na: 'not_applicable',
    },
  },
  exits: [],
  stop_track: {
    na: null, first: 47800, last: 47500, ups: 0, downs: 1, paused: true, hidden_eod: 0,
    rows: [
      { at: '2026-10-07T09:05:00+09:00', event: 'first', price: 47800, kind: 'effective', delta_won: null,
        direction: null, cause: '첫 관측', target_price: null, target_hit: null, arm_price: null, snapshot_age_s: null },
      { at: '2026-10-07T11:00:00+09:00', event: 'paused', price: 47800, kind: 'effective', delta_won: 0,
        direction: 'flat', cause: '전략 꺼짐 — 손절 평가 정지', target_price: null, target_hit: null, arm_price: null,
        snapshot_age_s: null },
      { at: '2026-10-08T10:00:00+09:00', event: 'change', price: 47500, kind: 'effective', delta_won: -300,
        direction: 'down', cause: 'ATR 변화', target_price: null, target_hit: null, arm_price: null,
        snapshot_age_s: null },
    ],
  },
  costs: {
    na: null, entry_fee: 710, entry_status: 'estimated', entry_allocated: false, exits: [],
    fee_total: null, tax_total: null, paid_total: 710, expected_exit: null, expected_exit_na: 'pending',
    status: 'estimated', allocated: false,
  },
  excursion: {
    basis_price: 50000, mfe: null, mae: null, closes_k: 0, closes_n: 0, provisional_dates: [], lock_dates: [],
    na: 'lookup_failed',
  },
  note: null,
}

const CARD_BFB = {
  pair_key: 'bull_flag_breakout:247540:B1',
  anchor_trade_id: JOURNAL_ANCHOR_BFB,
  strategy: 'bull_flag_breakout',
  ticker: '247540',
  ticker_name: '에코프로비엠',
  status: 'closed',
  opened_at: '2026-10-05T09:12:03.000000+09:00',
  closed_at: '2026-10-08T14:31:20.000000+09:00',
  held_days: 3,
  record_notice: null,
  pnl: {
    gross_krw: 44000, gross_rate_pct: 8.9069, net_krw: 41464, net_rate_pct: 8.3935, unrealized: false,
    partial_gross_krw: null, partial_net_krw: null, gross_na: null, net_na: null,
  },
  entry: {
    avg_price: 12350,
    qty: 40,
    orders: [
      {
        side: 'BUY', order_no: 'B1', trade_ids: [JOURNAL_ANCHOR_BFB], at: '2026-10-05T09:12:03.000000+09:00',
        price: 12350, qty: 40, division: '01', division_na: null, source: 'log_harvest', source_na: null,
        path: 'accept', parent_order_no: null,
        judge: { price: 12340, upper: null, src: 'signal', na: null },
        slip_order: { ref_price: 12340, ref_src: 'trade', per_share_won: 10, bp: 8.1, total_won: 400, bound: 'exact' },
        slip_order_na: null, slip_judge: null,
      },
    ],
    reason: {
      code: 'ENTRY', sub: null, phrase: null, renamed_from: null,
      text: '깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410', src: 'live', signal_src: 'ring', na: null,
    },
    initial_stop: {
      price: 11530, kind: 'effective', pct_from_entry: -6.64, observed_at: '2026-10-05T09:12:20+09:00',
      delay_s: 17, na: null, first_seen: null,
    },
    target: {
      kind: 'measured_move', price: 13450, hit: true, signal_price: 13450, arm_price: null, one_r_price: null,
      armed_at: null, text: '측정 목표 13,450 (+8.91%) — 도달', na: null,
    },
  },
  exits: [
    {
      side: 'SELL', order_no: 'S1', trade_ids: ['aaaaaaaa-0000-4000-8000-000000000002'],
      at: '2026-10-08T14:31:20.000000+09:00', price: 13450, qty: 40, division: '01', division_na: null,
      source: 'log_harvest', source_na: null, path: 'accept', parent_order_no: null,
      judge: { price: 13460, upper: null, src: 'log_price', na: null },
      slip_order: { ref_price: 13450, ref_src: 'trade', per_share_won: 0, bp: 0, total_won: 0, bound: 'exact' },
      slip_order_na: null,
      slip_judge: { ref_price: 13460, ref_src: 'live', per_share_won: 10, bp: 7.4, total_won: 400, bound: 'exact' },
      reason: {
        code: 'TAKE_PROFIT', sub: null, phrase: 'bfb_measured_target', renamed_from: null,
        text: '측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)', src: 'live', signal_src: null, na: null,
      },
      realized_gross_krw: 44000, fired_line: null, fired_src: null, effective_line: 12350, snapshot_age_s: 8,
      line_role: 'target', line_na: null,
    },
  ],
  stop_track: {
    na: null, first: 11530, last: 12350, ups: 2, downs: 1, paused: false, hidden_eod: 2,
    rows: [
      { at: '2026-10-05T09:12:20+09:00', event: 'first', price: 11530, kind: 'effective', delta_won: null,
        direction: null, cause: '첫 관측', target_price: 13450, target_hit: false, arm_price: null, snapshot_age_s: null },
      { at: '2026-10-06T15:31:00+09:00', event: 'eod', price: 11980, kind: 'effective', delta_won: 450,
        direction: 'up', cause: '고점 갱신', target_price: 13450, target_hit: false, arm_price: null, snapshot_age_s: null },
      { at: '2026-10-07T09:00:30+09:00', event: 'boot', price: 11900, kind: 'effective', delta_won: -80,
        direction: 'down', cause: '재시작 재계산', target_price: 13450, target_hit: false, arm_price: null,
        snapshot_age_s: null },
      { at: '2026-10-07T10:41:00+09:00', event: 'change', price: 12350, kind: 'effective', delta_won: 450,
        direction: 'up', cause: '본전 승격', target_price: 13450, target_hit: false, arm_price: null, snapshot_age_s: null },
      { at: '2026-10-08T14:31:20+09:00', event: 'exit', price: 12350, kind: 'effective', delta_won: 0,
        direction: 'flat', cause: '청산 직전 스냅샷 (8초 전) · 목표 도달', target_price: 13450, target_hit: true,
        arm_price: null, snapshot_age_s: 8 },
    ],
  },
  costs: {
    na: null, entry_fee: 701, entry_status: 'settled', entry_allocated: false,
    exits: [{ order_no: 'S1', at: '2026-10-08T14:31:20.000000+09:00', fee: 764, tax: 1071, status: 'settled',
              allocated: false }],
    fee_total: 1465, tax_total: 1071, paid_total: 2536, expected_exit: null, expected_exit_na: 'not_applicable',
    status: 'settled', allocated: false,
  },
  excursion: {
    basis_price: 12350,
    mfe: { pct: 6.23, krw: 30800, date: '2026-10-07', close: 13120, qty: 40, provisional: true },
    mae: { pct: 0.81, krw: 4000, date: '2026-10-05', close: 12450, qty: 40, provisional: false },
    closes_k: 3, closes_n: 3, provisional_dates: ['2026-10-07'], lock_dates: ['2026-10-06'], na: null,
  },
  note: { body: '목표 도달 — 계획대로', updated_at: '2026-10-08T15:05:00+09:00' },
}

const CARD_VB = {
  pair_key: 'volatility_breakout:000660:V1',
  anchor_trade_id: JOURNAL_ANCHOR_VB,
  strategy: 'volatility_breakout',
  ticker: '000660',
  ticker_name: 'SK하이닉스',
  status: 'closed',
  opened_at: '2026-10-06T09:05:00.000000+09:00',
  closed_at: '2026-10-06T15:20:05.000000+09:00',
  held_days: 0,
  record_notice: null,
  pnl: {
    gross_krw: -10000, gross_rate_pct: -2.0, net_krw: -11234, net_rate_pct: -2.2468, unrealized: false,
    partial_gross_krw: null, partial_net_krw: null, gross_na: null, net_na: null,
  },
  entry: {
    avg_price: 100000,
    qty: 5,
    orders: [
      {
        side: 'BUY', order_no: 'V1', trade_ids: [JOURNAL_ANCHOR_VB], at: '2026-10-06T09:05:00.000000+09:00',
        price: 100000, qty: 5, division: '01', division_na: null, source: 'log_harvest', source_na: null,
        path: 'accept', parent_order_no: null,
        judge: { price: 100000, upper: null, src: 'signal', na: null },
        slip_order: { ref_price: 100000, ref_src: 'trade', per_share_won: 0, bp: 0, total_won: 0, bound: 'exact' },
        slip_order_na: null, slip_judge: null,
      },
    ],
    reason: {
      code: 'ENTRY', sub: null, phrase: null, renamed_from: null,
      text: '본장 돌파선 99,800 돌파 · K 0.50 · 시가 대비 +1.2%', src: 'live', signal_src: 'ring', na: null,
    },
    initial_stop: {
      price: 97000, kind: 'hard_pct', pct_from_entry: -3.0, observed_at: '2026-10-06T09:05:20+09:00',
      delay_s: 20, na: null, first_seen: null,
    },
    target: {
      kind: 'none', price: null, hit: null, signal_price: null, arm_price: null, one_r_price: null, armed_at: null,
      text: '없음 — 15:20 당일 청산', na: 'not_applicable',
    },
  },
  exits: [
    {
      side: 'SELL', order_no: 'V2', trade_ids: ['aaaaaaaa-0000-4000-8000-000000000006'],
      at: '2026-10-06T15:20:05.000000+09:00', price: 98000, qty: 5, division: '01', division_na: null,
      source: 'log_harvest', source_na: null, path: 'accept', parent_order_no: null,
      judge: { price: null, upper: null, src: null, na: 'unknown' },
      slip_order: { ref_price: 98000, ref_src: 'trade', per_share_won: 0, bp: 0, total_won: 0, bound: 'exact' },
      slip_order_na: null, slip_judge: null,
      reason: {
        code: 'FORCE_CLEAR', sub: null, phrase: null, renamed_from: null, text: '15:20 강제청산', src: 'live',
        signal_src: null, na: null,
      },
      realized_gross_krw: -10000, fired_line: null, fired_src: null, effective_line: 97000, snapshot_age_s: 5,
      line_role: 'reference', line_na: null,
    },
  ],
  stop_track: {
    na: null, first: 97000, last: 97000, ups: 0, downs: 0, paused: false, hidden_eod: 0,
    rows: [
      { at: '2026-10-06T09:05:20+09:00', event: 'first', price: 97000, kind: 'hard_pct', delta_won: null,
        direction: null, cause: '첫 관측', target_price: null, target_hit: null, arm_price: null, snapshot_age_s: null },
      { at: '2026-10-06T15:20:05+09:00', event: 'exit', price: 97000, kind: 'hard_pct', delta_won: 0,
        direction: 'flat', cause: '청산 직전 스냅샷 (5초 전)', target_price: null, target_hit: null, arm_price: null,
        snapshot_age_s: 5 },
    ],
  },
  costs: {
    na: null, entry_fee: 710, entry_status: 'settled', entry_allocated: false,
    exits: [{ order_no: 'V2', at: '2026-10-06T15:20:05.000000+09:00', fee: 524, tax: 0, status: 'settled',
              allocated: false }],
    fee_total: 1234, tax_total: 0, paid_total: 1234, expected_exit: null, expected_exit_na: 'not_applicable',
    status: 'settled', allocated: false,
  },
  excursion: {
    basis_price: 100000, mfe: null, mae: null, closes_k: 0, closes_n: 0, provisional_dates: [], lock_dates: [],
    na: 'not_applicable',
  },
  note: null,
}

export const JOURNAL_FIXTURE = {
  record_start: {
    orders_restored: '2026-09-17', orders_live: '2026-10-01', stops: '2026-10-07', order_price: '2026-10-01',
  },
  filters: {
    from: '2026-09-09', to: '2026-10-09', strategy: null, ticker: null, status: 'all', outcome: 'all',
    basis: 'net', sort: 'recent',
  },
  counts: { total: 3, open: 1, closed: 2 },
  page: 1,
  size: 20,
  total: 3,
  total_pages: 1,
  cost_available: true,
  cards: [CARD_OPEN, CARD_BFB, CARD_VB],
}

/** 기록 시작일이 하나도 없는 세계(워커 가동 전) — 「실시간 기록 대기」. */
export const JOURNAL_FIXTURE_NO_RECORDS = {
  ...JOURNAL_FIXTURE,
  record_start: { orders_restored: null, orders_live: null, stops: null, order_price: null },
}
