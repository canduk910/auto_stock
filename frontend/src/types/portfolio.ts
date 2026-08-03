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

export interface PortfolioRisk {
  total_notional_won: number
  total_open_risk_won: number
  open_risk_pct_of_net: number
  concurrent_positions: number
  by_strategy: Record<string, PortfolioRiskBucket>
  by_sector: Record<string, PortfolioRiskBucket>
  top_sector: TopSector | null
}
