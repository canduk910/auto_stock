/**
 * cycle285 (2026-09-13) — 야간작업 현황 `GET /api/market-ops` 응답 타입.
 *
 * `market-state.ts`(cycle282)가 "지금 몇 시니까 어떤 상태여야 하는가" 를 코드 상수로만
 * 답하는 반면, 이 타입은 "실제로 무슨 일이 있었는가" 를 DB/메모리 산출물로 답하는 응답을
 * 담는다 — 별도 엔드포인트라 타입도 별도로 둔다(백엔드 `src/routes/market_ops.py` 참조).
 *
 * `evidence` 는 작업마다 모양이 다른 자유 사전이다(진행률 6키 / 산출물 행수 / 외부 루틴
 * provider·model 등) — 필드를 고정 타입으로 좁히면 다음 사이클이 evidence 키를 하나
 * 늘릴 때마다 이 파일도 갱신해야 하고, 갱신을 놓치면 화면이 새 키를 조용히 숨긴다.
 * 그래서 열린 `Record<string, unknown>` 으로 두고, 렌더 쪽(`MarketStateOps.tsx`)이
 * 알려진 키에는 한글 라벨을, 모르는 키에는 원문 그대로를 보여준다.
 */

/** 상태 어휘 10종 — 문서화 목적(실제 검사는 문자열 비교, 유니온으로 좁히지 않는다).
 *  `scheduled`|`running`|`done`|`failed`|`skipped_fresh`|`skipped_weekly`|`overwritten`|
 *  `not_fired`|`holiday`|`unknown` — 백엔드가 새 값을 추가해도 화면은 `unknown` 취급으로
 *  fail-open 해야 하므로 타입에서 강제하지 않는다(market-state.ts 의 `tone`/`rel` 과 같은 원칙). */
export type MarketOpsTaskStatus = string

export interface MarketOpsEngine {
  running: boolean
  phase: string
  /** `system_config` 60초 하트비트 마커. 마커가 아직 없으면 `null`. */
  heartbeat_at: string | null
}

export interface MarketOpsTask {
  id: string
  label_ko: string
  /** `scheduler.TIME_*`(또는 `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`)에서 읽은
   *  "HH:MM" 또는 "HH:MM:SS". 예정 시각 상수가 코드에 없는 작업(외부 크론)은 `null`. */
  scheduled_at: string | null
  status: MarketOpsTaskStatus
  last_success_at: string | null
  evidence: Record<string, unknown>
  note: string | null
}

export interface MarketOpsData {
  as_of_kst: string
  /** `true` 개장 · `false` 휴장 · `null` 확인 불가(임의 판단 금지, market-state.ts 와 동일 계약). */
  is_trading_day: boolean | null
  trading_day_source: string
  engine: MarketOpsEngine
  tasks: MarketOpsTask[]
  /** 이 응답을 만들며 실패한 데이터 소스 이름들 — 빈 배열이 정상. */
  evidence_errors: string[]
}
