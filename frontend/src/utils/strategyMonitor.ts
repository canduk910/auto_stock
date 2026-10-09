/**
 * cycle414 — 전략 진행상황 판정 순수 함수.
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §2.2(상태 배지) · §2.3(진입창) · §2.4(시장 유닛) ·
 * §2.5(병목) · §2.8(진입 기록 기준선 정규화).
 *
 * 🔴 엔진과 같게 **`=== true` 일 때만** 켜짐(`strategy_base.py` `_buy_paused_blocked`·`shadow_mode_on` 의
 * `is True`). `"true"`·`1` 은 「멈춤」·「섀도」가 아니라 설정 모양 오류다 — 엔진은 그 값을 꺼짐으로 읽는다.
 *
 * 시각 판정은 전부 `utils/kst.ts::kstMinutesOfDay` 에 위임한다(자체 Intl/로컬타임 getter 금지).
 */
import { kstMinutesOfDay } from './kst'
import type { StrategyInfo, MonitorMarketUnit } from '../types/trading'

export type { MonitorMarketUnit }
export type MonitorTone = 'red' | 'orange' | 'gray' | 'violet'

export interface StrategyStatusChip {
  kind:
    | 'off_with_holdings'
    | 'paused_shadow'
    | 'paused_config_invalid'
    | 'shadow_config_invalid'
    | 'zero_budget'
    | 'buy_disabled'
    | 'max_positions'
    | 'market_unit'
  label: string
  tone: MonitorTone
}

export interface StrategyStatusResult {
  primary: 'off' | 'paused' | 'shadow' | 'live'
  label: string
  chips: StrategyStatusChip[]
}

/** 터틀 4전략(시장 유닛 사이징 대상) — §2.4. */
const TURTLE_SIDS = new Set(['kojiro', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout'])

function isBool(v: unknown): v is boolean {
  return typeof v === 'boolean'
}

/**
 * 시장 유닛이 그 전략에서 뜻하는 것 — §2.4. 전략이 대상이 아니거나(터틀 4 + etf 가 아님) `mode==='off'`
 * 또는 스냅샷이 없으면 `null`(표시 안 함).
 */
export function marketUnitEffect(
  sid: string,
  mu: MonitorMarketUnit | null | undefined,
): { blocks: boolean; label: string } | null {
  if (!mu || mu.mode === 'off') return null
  const isEtf = sid === 'etf_trend'
  const isTurtle = TURTLE_SIDS.has(sid)
  if (!isEtf && !isTurtle) return null

  if (mu.mode === 'shadow') {
    if (!mu.ok) {
      return isEtf
        ? { blocks: true, label: '시장 유닛 미계산 — 결손이면 shadow 에서도 사지 않음' }
        : { blocks: false, label: '시장 유닛 미계산 — 관찰만(차단 아님)' }
    }
    const m = mu.m ?? 0
    if (isEtf && m <= 0) {
      return { blocks: true, label: `시장 유닛 m=${m} — 신규 진입 0배(사지 않음)` }
    }
    return { blocks: false, label: `시장 유닛 m=${m} (관찰만 · 랏 그대로)` }
  }

  if (mu.mode === 'enforce') {
    if (!mu.ok) {
      // 보완 1차(M1) — 엔진 `_market_unit_view` 는 오늘 스냅샷이 없거나(`not_computed`)
      // `ok=false` 면 터틀 4전략엔 `m=1.0`(차단 아님)을 돌려준다. etf_trend 만 `state==
      // "unavailable"` 을 직접 거른다(`etf_trend.py`) — 그래서 etf 는 여기서 그대로 차단.
      return isEtf
        ? { blocks: true, label: '시장 유닛 미계산 — 차단' }
        : { blocks: false, label: '시장 유닛 미계산 — m=1(차단 아님)' }
    }
    const m = mu.m ?? 0
    if (m <= 0) return { blocks: true, label: '시장 유닛 0배 — 신규 진입 0배(사지 않음)' }
    if (m < 1) return { blocks: false, label: `시장 유닛 랏 ×${m} 적용` }
    return { blocks: false, label: `시장 유닛 정상(m=${m})` }
  }

  return null
}

/**
 * 상태 배지 — §2.2. 주 배지 하나 + 보조 칩 여러 개.
 *
 * `info.params` 는 `/api/trading/status` `strategies.<id>.params`(운영 DB 값). `marketUnit` 은
 * 라우트 `/api/strategies/monitor` 의 `market_unit`(없으면 시장 유닛 칩을 만들지 않는다).
 */
export function strategyStatus(
  sid: string,
  info: StrategyInfo,
  marketUnit?: MonitorMarketUnit | null,
): StrategyStatusResult {
  const params = (info.params ?? {}) as Record<string, unknown>
  const buyPaused = params.buy_paused
  const shadowMode = params.shadow_mode
  const isPausedTrue = buyPaused === true
  const isShadowTrue = shadowMode === true
  const isOff = info.enabled === false

  let primary: StrategyStatusResult['primary']
  let label: string
  if (isOff) {
    primary = 'off'
    label = '꺼짐'
  } else if (isPausedTrue) {
    primary = 'paused'
    label = '신규 매수 멈춤 · 청산은 작동'
  } else if (isShadowTrue) {
    primary = 'shadow'
    label = '섀도 · 주문 없이 기록만'
  } else {
    primary = 'live'
    label = '실매매'
  }

  const chips: StrategyStatusChip[] = []
  const positions = info.positions ?? 0

  if (isOff && positions > 0) {
    chips.push({
      kind: 'off_with_holdings',
      label: `꺼짐 + 보유 ${positions} — 손절 정지`,
      tone: 'red',
    })
  }

  if (isPausedTrue && isShadowTrue) {
    chips.push({ kind: 'paused_shadow', label: '섀도 기록도 멈춤', tone: 'gray' })
  }

  if ('buy_paused' in params && !isBool(buyPaused)) {
    chips.push({
      kind: 'paused_config_invalid',
      label: '멈춤 설정 모양 오류 — 엔진은 「멈추지 않음」으로 읽음',
      tone: 'red',
    })
  }

  if ('shadow_mode' in params && !isBool(shadowMode)) {
    chips.push({
      kind: 'shadow_config_invalid',
      label: '섀도 설정 모양 오류 — 엔진은 「실매매」로 읽음',
      tone: 'red',
    })
  }

  if (!isOff && info.weight === 0 && !isShadowTrue) {
    chips.push({
      kind: 'zero_budget',
      label: '예산 0 — 신호가 「투자금 부족」으로 기록됨',
      tone: 'orange',
    })
  }

  if (info.buy_disabled === true) {
    chips.push({
      kind: 'buy_disabled',
      label: '매수 중단(일일 손실 한도 또는 19:50 이후)',
      tone: 'orange',
    })
  }

  const maxPositions = Number(params.max_positions)
  if (Number.isFinite(maxPositions) && maxPositions > 0 && positions >= maxPositions) {
    chips.push({
      kind: 'max_positions',
      label: `보유 한도 ${positions}/${maxPositions}`,
      tone: 'gray',
    })
  }

  const muEffect = marketUnitEffect(sid, marketUnit)
  if (muEffect) {
    chips.push({ kind: 'market_unit', label: muEffect.label, tone: 'violet' })
  }

  return { primary, label, chips }
}

/**
 * 시장 유닛이 그 종목의 상태 체인에서 「차단」으로 떨어질 때의 라벨(§2.4) — 차단 아니면 `null`.
 * `StrategyMonitor`(후보 상태 체인)·`StrategySummaryTable`(「왜 안 사나」 8단계)가 함께 쓴다.
 */
export function marketUnitBlockLabel(sid: string, mu: MonitorMarketUnit | null | undefined): string | null {
  const eff = marketUnitEffect(sid, mu)
  if (!eff || !eff.blocks) return null
  return mu && mu.ok === false ? '시장 유닛 미계산' : '시장 유닛 0배'
}

/**
 * 전략별 최종 단계 — step_no===99(명세 공통 계약) 우선, 없으면 그 목록의 최대 step_no(M7).
 * donchian·VCP·BFB·kojiro 실제 엔진 funnel 은 9단계(최종=9)라 고정 99 매칭은 늘 빈손이었다.
 */
export function finalFunnelStep<T extends { step_no: number }>(
  steps: T[] | null | undefined,
): T | null {
  if (!steps || steps.length === 0) return null
  const exact99 = steps.find((s) => s.step_no === 99)
  if (exact99) return exact99
  return steps.reduce((a, b) => (b.step_no > a.step_no ? b : a))
}

/** 처음 0 이 되는 단계의 `step_no`(정렬 = step_no 오름차순). 0 이 없거나 빈 목록이면 `null`. */
export function funnelBottleneck(
  steps: Array<{ step_no: number; survived_count: number }>,
): number | null {
  if (!steps || steps.length === 0) return null
  const sorted = [...steps].slice().sort((a, b) => a.step_no - b.step_no)
  for (const s of sorted) {
    if (s.survived_count === 0) return s.step_no
  }
  return null
}

/** 코드 고정 진입창(09:05~09:30) 전략 — `params` 무관. */
const FIXED_WINDOW_SIDS = new Set(['etf_trend', 'donchian_swing', 'kojiro'])
const FIXED_WINDOW_START = '09:05'
const FIXED_WINDOW_END = '09:30'

function hhmmToMinutes(hhmm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm)
  if (!m) return null
  const h = Number(m[1])
  const mi = Number(m[2])
  if (!Number.isFinite(h) || !Number.isFinite(mi)) return null
  return h * 60 + mi
}

/**
 * 진입창 상태 — §2.3. `now` 주입 seam(KST 로만 판정, 브라우저 로컬타임 무관).
 *
 * etf_trend·donchian_swing·kojiro 는 `params` 와 무관하게 09:05~09:30 코드 고정. VCP·BFB 는
 * `params.entry_start`~`entry_end` 가 없으면 `null`(추측하지 않는다). 그 밖 전략은 `null`.
 */
export function entryWindow(
  sid: string,
  params: Record<string, unknown> | undefined,
  now: Date,
): { state: 'before' | 'open' | 'after'; start: string; end: string; fixed: boolean } | null {
  let start: string
  let end: string
  let fixed: boolean
  if (FIXED_WINDOW_SIDS.has(sid)) {
    start = FIXED_WINDOW_START
    end = FIXED_WINDOW_END
    fixed = true
  } else {
    const s = params?.entry_start
    const e = params?.entry_end
    if (typeof s !== 'string' || typeof e !== 'string') return null
    start = s
    end = e
    fixed = false
  }
  const startMin = hhmmToMinutes(start)
  const endMin = hhmmToMinutes(end)
  if (startMin === null || endMin === null) return null
  // L14 — 시작 > 끝(뒤집힌 설정, 예: 오버나이트 창을 당일 창처럼 잘못 적은 값)은 당일 전용 비교
  // 식(`cur < start ? before : cur > end ? after : open`)으로 추측하지 않는다 — 추측하면 거의
  // 전 구간이 틀린 상태("닫힘"이어야 할 구간이 "열림")로 읽힌다. 모름으로 둔다.
  if (startMin > endMin) return null
  const cur = kstMinutesOfDay(now)
  const state: 'before' | 'open' | 'after' = cur < startMin ? 'before' : cur > endMin ? 'after' : 'open'
  return { state, start, end, fixed }
}

/** 진입 기록(⑥) 기준선 칸 키 — 전략마다 다른 매수선 키를 하나로 정규화(§2.8). */
const BASELINE_KEY: Record<string, string> = {
  etf_trend: 'line',
  donchian_swing: 'donchian_high',
  vcp_breakout: 'base_high',
  bull_flag_breakout: 'flag_high',
  volatility_breakout: 'target_price',
  long_tail_volatility: 'target_price',
}

/** `change_rate` 를 0 으로 채우는 전략(엔진이 전일 대비를 모른다) — 「+0%」 거짓 표기 금지. */
const ZERO_FILLED_CHANGE_RATE_SIDS = new Set([
  'etf_trend', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout', 'kojiro',
])

/**
 * 오늘 거르기 사유(⑤) 엔진 키 → 화면 문구 — §4.1(etf) · §4.2(donchian) · §4.3·4.4(VCP·BFB).
 * `StrategyMonitor`(⑤ 사유 칸)·`StrategySummaryTable`(「왜 안 사나」 10단계)가 함께 쓴다.
 */
export const SKIP_REASON_LABELS: Record<string, string> = {
  open_unknown: '시가 미확정',
  gap_up: '전일 대비 갭 과다',
  gap_over_line: '돌파선 위로 너무 떠서 시작',
  collapse: '시가 아래로 밀림',
  cluster_held: '같은 묶음 ETF 보유 중',
  market_unit_unavailable: '시장 유닛 미계산',
  zero_state: '시장 유닛 0배',
  no_budget: '예산 0',
  rounds_to_zero: '1주도 안 됨',
  sizing_mode_invalid: '사이징 설정 오류(터틀 아님)',
  kk_lot_zero: '설계 랏 0',
  daily_entry_cap: '하루 신규 상한',
  no_data: '거래량 미관측',
  reject_ext: '추격 상한',
  latch_armed: '래치 무장',
  setup_conflict: '셋업 충돌',
  seen: '돌파 관측',
  retreat: '후퇴(돌파선 아래로 복귀)',
}

/** `latch_released:<reason>` 접두 키(BFB·VCP `_release_latch` 사유) → 한글. */
const LATCH_RELEASED_LABELS: Record<string, string> = {
  level_moved: '레벨 이동(prepare 재실행으로 돌파선이 옮겨짐)',
  stop_line: '손절선 이탈(베이스 소멸)',
}

/**
 * 사유 키 → 화면 문구 — L3. `SKIP_REASON_LABELS` 정확 일치 우선, `latch_released:*` 접두는
 * 서브 사유를 번역해 합성한다. 모르는 키는 추측하지 않고 원문을 그대로 둔다.
 */
export function skipReasonLabel(reason: string): string {
  const exact = SKIP_REASON_LABELS[reason]
  if (exact) return exact
  if (reason.startsWith('latch_released:')) {
    const sub = reason.slice('latch_released:'.length)
    return `래치 해제 — ${LATCH_RELEASED_LABELS[sub] ?? sub}`
  }
  return reason
}

/** `skips.counts` 에서 가장 많은 사유 하나(0 은 제외). 비어 있으면 `null`. */
export function topSkipReason(
  counts: Record<string, number> | null | undefined,
): { reason: string; label: string; count: number } | null {
  if (!counts) return null
  let best: { reason: string; count: number } | null = null
  for (const [reason, count] of Object.entries(counts)) {
    if (!Number.isFinite(count) || count <= 0) continue
    if (!best || count > best.count) best = { reason, count }
  }
  if (!best) return null
  return { reason: best.reason, label: skipReasonLabel(best.reason), count: best.count }
}

/** 매수 신호(⑥) 한 건을 「기준선」·「기준선 대비 %」 계산용으로 정규화 — §2.8. */
export function signalBaseline(
  sid: string,
  sig: Record<string, unknown>,
): { baseline: number | null; changeRate: number | null } {
  const key = BASELINE_KEY[sid]
  let baseline: number | null = null
  if (key) {
    const v = sig[key]
    if (typeof v === 'number' && Number.isFinite(v)) baseline = v
  }
  let changeRate: number | null = null
  const cr = sig.change_rate
  if (typeof cr === 'number' && Number.isFinite(cr)) {
    changeRate = ZERO_FILLED_CHANGE_RATE_SIDS.has(sid) && cr === 0 ? null : cr
  }
  return { baseline, changeRate }
}

// ─────────────────────────────── 보완 5차(cycle418-M) — 잔여 LOW ───────────────────────────────

/**
 * donchian 15:20 시간청산 판정 상태 — L15. 엔진 `check_force_clear`(깡토식, cycle405)와 같은
 * 순서: (a) `daysHeld ≥ maxHoldBars−1` 이면 **R 과 무관하게** 그날 정리(`max_hold_due`) —
 * 화면이 이 조건을 안 보면 「+1R 넘음 — 시간청산 면제」로 잘못 단정한다. (b) `reachedR1` 이면
 * 면제(`exempt`). (c) `daysHeld`·`timeExitBars` 를 모르면 판정 불가(`unknown`). (d) 남은 날이
 * 있으면 `pending`(dueInDays), 없으면 오늘(`due_today`).
 */
export function donchianTimeExitState(args: {
  daysHeld: number | null
  timeExitBars: number | null
  maxHoldBars: number | null
  reachedR1: boolean
}): { kind: 'unknown' | 'max_hold_due' | 'exempt' | 'due_today' | 'pending'; dueInDays: number | null } {
  const { daysHeld, timeExitBars, maxHoldBars, reachedR1 } = args
  if (daysHeld !== null && maxHoldBars !== null && daysHeld >= maxHoldBars - 1) {
    return { kind: 'max_hold_due', dueInDays: null }
  }
  if (reachedR1) return { kind: 'exempt', dueInDays: null }
  if (daysHeld === null || timeExitBars === null) return { kind: 'unknown', dueInDays: null }
  const due = timeExitBars - 1 - daysHeld
  if (due <= 0) return { kind: 'due_today', dueInDays: null }
  return { kind: 'pending', dueInDays: due }
}

/**
 * 14일 추이 날짜 칸 라벨 — N4-1. 칸이 많아질수록(400px 폭에서 14칸 ≈22.6px) "MM-DD" 전체가
 * 잘려 날짜·값이 함께 안 보인다. 칸 수가 11 이상이면(실측 10칸=32.4px 는 안 잘림, 14칸은 잘림)
 * 일(DD)만 쓴다 — `title` 속성에는 여전히 전체 날짜가 남는다(호출부 책임).
 */
export function trendDateLabel(dateStr: string, totalCols: number): string {
  if (!dateStr || dateStr.length < 10) return dateStr || '—'
  if (totalCols >= 11) return dateStr.slice(8, 10)
  return dateStr.slice(5, 10)
}

/**
 * momentum 폴백 깔때기의 `limit_up_excluded` 단계 — N-E. 이 키는 "통과 수"가 아니라 "제외 수"
 * (`scanner.scan_filter_stats`, 상한가 종목을 뺀 건수)다. 그대로 늘어놓으면 숫자가 늘었다
 * 줄었다 하므로, 직전 단계 통과 수에서 제외 수를 뺀 값을 "통과"로 보여주고 제외 수는 따로 낸다.
 */
export function momentumExcludedStageText(
  prevSurvived: number | null,
  excluded: number | null,
): { survived: number | null; excluded: number | null } {
  if (prevSurvived === null || excluded === null) return { survived: null, excluded }
  return { survived: prevSurvived - excluded, excluded }
}

// ─────────────────────────── 보완 4차(N3-1) — 사다리 라벨 x 범위 ───────────────────────────
// `components/StrategyMonitor.tsx` 의 `Ladder`(SVG, §2.9)가 라벨 글자가 그림 폭 밖으로 잘리지
// 않게 x·textAnchor 를 고르는 순수 함수. jsdom 에는 실제 글자폭이 없어(getBBox=0) playwright
// 좌표 실측으로만 검증할 수 있고, 여기 둔 숫자 상수는 그 실측을 보정한 값이다.

/** fontSize=7 SVG text 한글자당 평균 폭(px) 근사치 — 한글·숫자·구두점 혼용 문자열(라벨+값, 보완
 * 3차 N3-1 실측 두 건: 36자→141.2px·23자→94.6px, 자당 3.92~4.11px)에 안전마진을 더한 값이다.
 * 실제 렌더 폭보다 넓게 잡아(과대추정) 잘림보다 과한 클램프 쪽으로 기운다. */
export const LADDER_LABEL_CHAR_WIDTH_PX = 4.3

/** 라벨 글자폭 근사치(px) — `text.length × 글자당 폭`. */
export function estimateLadderLabelWidth(text: string): number {
  return text.length * LADDER_LABEL_CHAR_WIDTH_PX
}

export interface LadderLabelLayout { x: number; anchor: 'start' | 'middle' | 'end' }

/** 라벨 중심 x 를 그림 폭 `[0, boardWidth]` 안으로 당긴다(N3-1) — `textAnchor="middle"` 기준으로
 * `[글자폭/2, boardWidth − 글자폭/2]` 범위로 클램프한다. 글자폭이 그림 폭 이상이면(기형적으로 긴
 * 합친 라벨) 왼쪽 경계(`x=0`, `anchor="start"`)에 붙여 **왼쪽 잘림만은** 항상 막는다(오른쪽은
 * 이 경우 불가피하게 넘칠 수 있다 — 더 줄일 글자가 없다). */
export function clampLadderLabelCenter(centerX: number, labelWidth: number, boardWidth: number): LadderLabelLayout {
  if (labelWidth >= boardWidth) return { x: 0, anchor: 'start' }
  const half = labelWidth / 2
  const x = Math.min(Math.max(centerX, half), boardWidth - half)
  return { x, anchor: 'middle' }
}

/** 같은 줄(위/아래 교대 배치)에 선 라벨끼리의 겹침을 없앤다 — 입력은 x 오름차순으로 정렬된
 * `{ center, width }` 목록(그림 폭 클램프까지 적용된 값)이다. 왼→오른쪽으로 한 번(왼쪽 라벨의
 * 오른쪽 가장자리를 다음 라벨이 넘지 않게 밀고), 그 결과를 오른→왼쪽으로 한 번 더(오른쪽 끝이
 * 그림 밖으로 밀려났으면 안쪽으로 되밀어) 보정해 그림 폭 경계를 우선 지킨다. 입력이 1개뿐이면
 * 그대로 돌려준다. */
export function resolveLadderRowOverlaps(
  items: Array<{ center: number; width: number }>,
  boardWidth: number,
  gapPx = 2,
): number[] {
  const n = items.length
  if (n === 0) return []
  const centers = items.map((it) => it.center)
  for (let i = 1; i < n; i++) {
    const prevRight = centers[i - 1] + items[i - 1].width / 2 + gapPx
    const curLeft = centers[i] - items[i].width / 2
    if (curLeft < prevRight) centers[i] = prevRight + items[i].width / 2
  }
  const lastIdx = n - 1
  const lastRight = centers[lastIdx] + items[lastIdx].width / 2
  if (lastRight > boardWidth) centers[lastIdx] = boardWidth - items[lastIdx].width / 2
  for (let i = n - 2; i >= 0; i--) {
    const nextLeft = centers[i + 1] - items[i + 1].width / 2 - gapPx
    const curRight = centers[i] + items[i].width / 2
    if (curRight > nextLeft) centers[i] = nextLeft - items[i].width / 2
  }
  if (centers[0] - items[0].width / 2 < 0) centers[0] = items[0].width / 2
  return centers
}
