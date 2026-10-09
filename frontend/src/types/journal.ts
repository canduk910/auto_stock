// cycle413 — 거래일지 화면(1b) 응답 타입.
//
// 정본 = `_workspace/red/cycle413/journal_view_spec.md` 1-2절(백엔드가 보내는 모양)
// + `tests/fixtures/cycle413_journal_shape.json`(키 집합 정본 — 백엔드 라우트 테스트와
// 프론트 handlers.honesty 테스트가 같은 파일로 대조한다). 키를 더하거나 빼면 그 쪽이
// 바로 붉어진다.

export type NaKind = 'unknown' | 'before_record' | 'not_applicable' | 'pending' | 'lookup_failed'
export type ValSrc = 'trade' | 'live' | 'restored' | 'restored_ai' | 'snapshot' | 'derived' | 'inferred' | 'computed'
export type CostStatus = 'settled' | 'estimated' | 'mixed'

export interface JournalResponse {
  record_start: {
    orders_restored: string | null
    orders_live: string | null
    stops: string | null
    order_price: string | null
  }
  filters: {
    from: string
    to: string
    strategy: string | null
    ticker: string | null
    status: 'all' | 'open' | 'closed'
    outcome: 'all' | 'win' | 'loss'
    basis: 'net' | 'gross'
    sort: 'recent' | 'pnl_asc' | 'pnl_desc'
  }
  counts: { total: number; open: number; closed: number }
  page: number
  size: number
  total: number
  total_pages: number
  cost_available: boolean
  cards: JournalCard[]
}

export interface JournalCard {
  pair_key: string | null
  anchor_trade_id: string
  strategy: string
  ticker: string
  ticker_name: string
  status: 'open' | 'closed'
  opened_at: string
  closed_at: string | null
  held_days: number
  record_notice: 'before_orders' | 'before_stops' | null
  pnl: {
    gross_krw: number | null
    gross_rate_pct: number | null
    net_krw: number | null
    net_rate_pct: number | null
    unrealized: boolean
    partial_gross_krw: number | null
    partial_net_krw: number | null
    gross_na: NaKind | null
    net_na: NaKind | null
  }
  entry: {
    avg_price: number
    qty: number
    orders: OrderLine[]
    reason: Reason
    initial_stop: StopPoint
    target: Target
  }
  exits: ExitLine[]
  exits_na: NaKind | null
  stop_track: StopTrack
  costs: Costs
  excursion: Excursion
  note: { body: string; updated_at: string } | null
}

export interface OrderLine {
  side: 'BUY' | 'SELL'
  order_no: string | null
  trade_ids: string[]
  at: string
  price: number
  qty: number
  division: string | null
  division_na: NaKind | null
  source: string | null
  source_na: NaKind | null
  path: 'accept' | 'fallback' | 'reorder' | 'manual' | null
  parent_order_no: string | null
  judge: { price: number | null; upper: number | null; src: 'signal' | 'log_price' | 'log_pct' | 'restored_ai' | null; na: NaKind | null }
  slip_order: Slip | null
  slip_order_na: NaKind | null
  slip_judge: Slip | null
}

export interface Slip {
  ref_price: number
  ref_src: ValSrc
  per_share_won: number
  bp: number
  total_won: number
  bound: 'exact' | 'upper'
}

export interface ExitLine extends OrderLine {
  reason: Reason
  realized_gross_krw: number | null
  fired_line: number | null
  fired_src: ValSrc | null
  effective_line: number | null
  snapshot_age_s: number | null
  line_role: 'fired' | 'reference' | 'target' | null
  line_na: NaKind | null
  stop_kind: string | null
}

export interface Reason {
  code: string | null
  sub: string | null
  phrase: string | null
  renamed_from: string | null
  text: string | null
  src: ValSrc | null
  signal_src: 'ring' | 'log_only' | 'none' | null
  na: NaKind | null
}

export interface StopPoint {
  price: number | null
  kind: string | null
  pct_from_entry: number | null
  observed_at: string | null
  delay_s: number | null
  na: NaKind | null
  first_seen: { price: number | null; kind: string | null; observed_at: string } | null
}

export interface Target {
  kind: 'measured_move' | 'none'
  price: number | null
  hit: boolean | null
  signal_price: number | null
  arm_price: number | null
  one_r_price: number | null
  armed_at: string | null
  text: string
  na: NaKind | null
}

export interface StopTrack {
  na: NaKind | null
  first: number | null
  last: number | null
  ups: number
  downs: number
  paused: boolean
  rows: StopRow[]
  hidden_eod: number
}

export interface StopRow {
  at: string
  event: 'first' | 'change' | 'boot' | 'eod' | 'paused' | 'exit'
  price: number | null
  kind: string | null
  delta_won: number | null
  direction: 'up' | 'down' | 'flat' | null
  cause: string
  target_price: number | null
  target_hit: boolean | null
  arm_price: number | null
  snapshot_age_s: number | null
}

export interface Costs {
  na: NaKind | null
  entry_fee: number | null
  entry_status: CostStatus | null
  entry_allocated: boolean
  exits: { order_no: string | null; at: string; fee: number | null; tax: number | null; status: CostStatus | null; allocated: boolean }[]
  fee_total: number | null
  tax_total: number | null
  paid_total: number | null
  expected_exit: number | null
  expected_exit_na: NaKind | null
  status: CostStatus | null
  allocated: boolean
}

export interface Excursion {
  basis_price: number
  mfe: ExPoint | null
  mae: ExPoint | null
  closes_k: number
  closes_n: number
  provisional_dates: string[]
  lock_dates: string[]
  na: NaKind | null
}

export interface ExPoint {
  pct: number
  krw: number
  date: string
  close: number
  qty: number
  provisional: boolean
}

export interface JournalNotePut {
  anchor_trade_id: string
  body: string
  created_at: string
  updated_at: string
}

export interface JournalQuery {
  from: string
  to: string
  strategy?: string
  ticker?: string
  status: 'all' | 'open' | 'closed'
  outcome: 'all' | 'win' | 'loss'
  basis: 'net' | 'gross'
  sort: 'recent' | 'pnl_asc' | 'pnl_desc'
  page: number
  size: number
}
