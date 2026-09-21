export interface Holding {
  ticker: string
  name: string
  quantity: number
  sellable_quantity: number
  avg_price: number
  purchase_amount: number
  current_price: number
  eval_amount: number
  eval_profit_loss: number
  eval_profit_rate: number
  // J1 (2026-05-11) — stock_master 캐시 조인 결과.
  // 미캐시/조회 예외 시 null/undefined — UI 는 "확인중" 표시.
  nxt_tradable?: boolean | null
  krx_halted?: boolean | null
  excg_dvsn_cd?: string | null
  // 2026-08-04 — 업종 한글명(bstp_kor_isnm) 우선 → KRX 산업지수 플래그/업종코드
  // 폴백 → `미분류-{ticker}`. 백엔드 `sector_naming` 단일 진실원.
  sector?: string | null
  // cycle339 — 그 종목을 보유한 전략의 청산선. 백엔드 `position_exit_lines` 단일 진실원.
  // 🔴 판정 불가는 전부 null 이고 화면은 `—` 를 그린다 — 숫자를 지어내지 않는다.
  strategy_id?: string | null
  stop_price?: number | null
  /** `effective` = 전략 실효 손절선(check_exit 와 동일 산식) / `hard_pct` = 고정%손절 근사. */
  /** `engine_idle` = 매매 엔진 정지 중(21:30~07:45) — 「손절선 없음」이 아니라 「지금은 모름」. */
  /** `mode_dependent` = 보유 중 모드가 갈려 하나의 고정%로 접을 수 없다(롱테일 상한가 모드). */
  stop_source?: 'effective' | 'hard_pct' | 'engine_idle' | 'mode_dependent' | null
  target_price?: number | null
  /** `measured_move` = 측정 목표(부분 익절 트리거) · `measured_move_hit` = **이미 도달**. */
  target_source?: 'measured_move' | 'measured_move_hit' | null
}

export interface BalanceSummary {
  deposit: number
  stock_eval_amount: number
  total_eval_amount: number
  net_asset: number
  purchase_total: number
  eval_total: number
  profit_loss_total: number
}

export interface BalanceData {
  holdings: Holding[]
  summary: BalanceSummary
}
