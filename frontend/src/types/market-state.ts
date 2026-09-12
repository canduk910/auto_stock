/**
 * cycle282 (2026-09-11) — 장운영상태 `GET /api/market-state` 응답 타입.
 *
 * 백엔드 `src/engine/market_state.py` 의 표(13행)·주문유형 카탈로그(28코드)를 라우트가
 * **한 응답**으로 내려 준다. 표와 커서를 따로 부르면 자정·경계 순간에 둘이 갈라져
 * 화면이 거짓말을 하므로(M9), 타입도 하나의 덩어리로 둔다.
 *
 * 골든 픽스처(`src/test/fixtures/marketState.fixture.ts`)가 같은 구조를 기계 생성으로
 * 갖고 있고, 그 픽스처가 MSW·Playwright·컴포넌트 목의 본문이다. 두 선언이 어긋나면
 * `tsc -b` 가 먼저 붉어진다.
 */

export interface MarketStateWindow {
  start: string
  end: string
}

export interface MarketStateDivisionsByRow {
  row_id: string
  codes: string[]
}

/**
 * `markets[<market>]` — **서버가 판정한 커서 1개**.
 *
 * 화면은 이 값을 그릴 뿐 브라우저 시각으로 다시 계산하지 않는다(루트 CLAUDE.md KST 강제).
 */
export interface MarketStateCursor {
  market: string
  market_label_ko: string
  /** 커서 행. 그 시각에 유효한 행이 없으면 `null`(장 종료). */
  row_id: string | null
  phase: string
  name_ko: string
  tone: string
  window: MarketStateWindow | null
  match_kind: string
  match_ko: string
  /** 장이 열려 있는가(phase 기반). */
  is_open: boolean
  /** 주문을 낼 수 있는가(주문유형 존재 기반). 둘은 다른 값일 수 있다 — 단일가 구간 참조. */
  can_order: boolean
  market_order_ok: boolean
  /** 동시에 살아 있는 행들의 **합집합**. 사용자 질문의 답은 커서 행 단독이 아니다. */
  order_divisions: string[]
  order_divisions_by_row: MarketStateDivisionsByRow[]
  concurrent_row_ids: string[]
  quote_channel: string | null
  quote_channel_evidence: string
  decided_by: string
  code_seen: string | null
  confidence: string
  confidence_notes: string[]
  /** 다음 경계까지 남은 초. 오늘 남은 경계가 없으면 `null`. */
  seconds_to_next: number | null
  next_boundary: string | null
  next_row_id: string | null
  next_phase: string | null
}

export interface MarketStateTableRow {
  row_id: string
  market: string
  start: string
  end: string
  phase: string
  name_ko: string
  tone: string
  match_kind: string
  match_ko: string
  order_divisions: string[]
  /** 선언에는 있으나 아직 시행 전인 코드 — 지우지 않고 배지로 드러낸다. */
  order_divisions_pending: string[]
  /** 선언에는 있으나 이미 폐지된 코드. */
  order_divisions_expired: string[]
  can_order: boolean
  market_order_ok: boolean
  quote_channel: string | null
  quote_channel_evidence: string
  overlap_ok: boolean
  priority: number
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
  /** 서버 판정 — 지난/현재/동시/예정/알수없음. 프론트가 시각으로 다시 재지 않는다. */
  rel: string
}

export interface OrderDivisionRow {
  code: string
  name_ko: string
  group_ko: string | null
  /** 거래소별 3상태 — 지원/미확인/미지원. "미지원"과 "미확인"은 다른 값이다. */
  exchange_support: Record<string, string>
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
}

export interface MarketPhaseSpec {
  id: string
  label_ko: string
  tone: string
}

/** 화면이 스타일 키로 쓰는 **표현 어휘**. 행 id·코드·시장명과 달리 이 값들은 화면이 알아도 된다. */
export interface MarketStateVocab {
  tones: string[]
  rels: string[]
  support_levels: string[]
  confidences: string[]
  division_confidences: string[]
}

export interface MarketStateData {
  table_version: string
  as_of_kst: string
  on_date: string
  preview: boolean
  cursor_disabled_reason: string | null
  /** `true` 개장 · `false` 휴장 · `null` **확인 불가**(임의 판단 금지). */
  is_trading_day: boolean | null
  trading_day_source: string
  /** 화면 렌더 순서 — 프론트가 시장명을 갖지 않도록 서버가 배열로 준다. */
  market_order: string[]
  /** 카탈로그 열 순서. */
  exchange_order: string[]
  /** 다른 날짜를 미리 보는 중이면 `null` — 커서는 "지금" 에만 의미가 있다. */
  markets: Record<string, MarketStateCursor> | null
  table: MarketStateTableRow[]
  order_divisions: OrderDivisionRow[]
  phases: MarketPhaseSpec[]
  vocab: MarketStateVocab
  findings: string[]
  board_note: string
  unconfirmed_note: string
}
