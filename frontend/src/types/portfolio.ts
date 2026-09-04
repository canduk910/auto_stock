/**
 * 사이클 I (2026-08-03): 포트폴리오 리스크 관찰 타입.
 *
 * 백엔드 `src/engine/portfolio_risk.py` + `GET /api/portfolio/risk` 와 1:1.
 * 관찰 전용 — 매수 차단/배제 없음 (Phase 1, 사이클 H).
 */

export interface PortfolioRiskBucket {
  positions: number
  notional_won: number
  risk_won: number
}

export interface TopSector {
  sector: string
  risk_won: number
  risk_share_pct: number
}

/**
 * 사이클 251 (2026-09-05): 계좌 SOFT Σ상한 게이트 관측 (cycle239 후속 F).
 *
 * 백엔드 `src/engine/account_risk_watcher.py::get_gate_state()` 8키 + cycle250
 * `_eval_timeout_count()` 를 `GET /api/portfolio/risk` 의 `data.account_gate` 로
 * 그대로 노출한다. 백엔드 graceful 실패 시 키 자체가 부재하거나 null 일 수 있다
 * (optional — 부재/null 은 카드가 "게이트 정보 없음" 경로로 처리한다).
 */
export interface AccountGate {
  level: 'ok' | 'warn' | 'block' | 'error' | string
  reasons: string[]
  open_risk_pct: number | null
  evaluated_at: string | null
  age_secs: number | null
  stale: boolean
  stale_max_secs: number
  effective_gated: boolean
}

export interface PortfolioRisk {
  total_notional_won: number
  total_open_risk_won: number
  open_risk_pct_of_net: number
  concurrent_positions: number
  by_strategy: Record<string, PortfolioRiskBucket>
  by_sector: Record<string, PortfolioRiskBucket>
  top_sector: TopSector | null
  account_gate?: AccountGate | null
}
