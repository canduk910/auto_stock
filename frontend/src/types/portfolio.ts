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
 * 백엔드 `src/engine/account_risk_watcher.py::get_gate_state()` 8키를
 * `GET /api/portfolio/risk` 의 `data.account_gate` 로 그대로 노출한다. 백엔드
 * graceful 실패 시 키 자체가 부재하거나 null 일 수 있다(optional — 부재/null 은
 * 카드가 "게이트 정보 없음" 경로로 처리한다).
 *
 * 사이클 256 (리팩토링 카드 #10) — `level` 을 `GateLevel` 유니온으로 정정했다.
 * 종전 `| string` 은 TS 확장 규칙상 리터럴 유니온을 흡수해 사실상 `string` 과
 * 동치였다(오타 보호 무효). 백엔드가 미지 값을 보낼 가능성은 컴포넌트의
 * `isKnownLevel()` 런타임 가드가 흡수한다(현재 `else` 분기 = "정상" 배지 그대로).
 * `eval_timeouts_today` 는 백엔드 리포트 스냅샷에는 이미 있으나 이 라우트에는
 * 아직 없어 optional — 카드 #6 선반영.
 */
export type GateLevel = 'ok' | 'warn' | 'block' | 'error'

export interface AccountGate {
  level: GateLevel
  reasons: string[]
  open_risk_pct: number | null
  evaluated_at: string | null
  age_secs: number | null
  stale: boolean
  stale_max_secs: number
  effective_gated: boolean
  eval_timeouts_today?: number
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
