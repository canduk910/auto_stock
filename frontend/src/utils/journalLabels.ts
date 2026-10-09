// cycle413 — 거래일지 한국어 표기 정본.
//
// 서버는 코드만 보내고 화면이 이 한 곳에서 짧은 트레이더 말로 바꾼다(문장 = 이유·원인만
// 서버가 만든다). 계약 = `_workspace/red/cycle413/journal_view_contract.md` 4절 ·
// 명세 = `_workspace/red/cycle413/journal_view_spec.md` 2절·5절.
//
// 전략 이름은 기존 `utils/strategyMeta.ts::strategyLabel()` 을 쓴다 — 이 파일에 사본을 두지 않는다.
import type { CostStatus, NaKind } from '../types/journal'

const REASON_CODE_LABELS: Record<string, string> = {
  ENTRY: '진입',
  STOP_LOSS: '손절',
  TRAILING_STOP: '트레일링',
  TAKE_PROFIT: '익절',
  TIME_EXIT: '시간 청산',
  TREND_EXIT: '추세 종료',
  FORCE_CLEAR: '15:20 청산',
  NEXT_DAY_CLEAR: '익일 청산',
  STATUS_EXIT: '종목상태 청산',
  MANUAL: '수동 매도',
}

/** 2-1. 청산 사유 코드 → 짧은 배지. */
export function reasonCodeLabel(code: string | null): string {
  if (code === null) return '사유 없음'
  return REASON_CODE_LABELS[code] ?? code
}

const REASON_SUB_LABELS: Record<string, string> = {
  gap_below: '갭 미달',
  krx_only: 'KRX 전용',
  nxt_open_missing: 'NXT 시가 미수신',
  managed: '관리종목',
  overheat: '단기과열',
  'managed+overheat': '관리·과열',
}

/** 2-2. `reason_sub` — 모르는 값은 원문 그대로. */
export function reasonSubLabel(sub: string | null): string | null {
  if (sub === null) return null
  return REASON_SUB_LABELS[sub] ?? sub
}

const PHRASE_LABELS: Record<string, string> = {
  kojiro_hard_stop: '하드 손절',
  kojiro_atr_stop: 'ATR 손절',
  kojiro_trailing: '샹들리에 트레일',
  kojiro_stage3_exit: '스테이지3 — 추세 종료',
  bfb_turtle_stop: '터틀 손절(E−2N)',
  bfb_turtle_backstop: '받침선 손절',
  bfb_pullback_stop: '눌림목 손절',
  bfb_measured_target: '측정 목표 도달',
  bfb_time_exit: '보유 기한 초과',
  ltv_intraday_stop: '당일 모드 손절',
  ltv_limit_up_stop: '상한가 모드 손절',
  vb_stop: '고정 손절',
  momentum_stop: '고정 손절',
  donchian_time_exit: '시간 청산',
  donchian_time_exit_legacy: '시간 청산(옛 규칙)',
  donchian_trailing_legacy: '트레일(옛 규칙)',
}

/** 2-3. 사유 줄 `phrase` (툴팁·세부). */
export function phraseLabel(phrase: string | null): string | null {
  if (phrase === null) return null
  return PHRASE_LABELS[phrase] ?? phrase
}

const SOURCE_LABELS: Record<string, string> = {
  log_harvest: '기록',
  log_restore: '복원',
  fallback_inferred: '추정·폴백',
  reorder_inferred: '추정·재주문',
  manual_api: '수동',
  external: '외부 주문',
  unmatched: '매핑 없음',
}

/** 2-4. 일지 행 출처 `source` 배지. */
export function sourceLabel(source: string | null): string | null {
  if (source === null) return null
  return SOURCE_LABELS[source] ?? source
}

const STOP_KIND_LABELS: Record<string, string> = {
  effective: '전략 손절선',
  hard_pct: '고정% 손절선',
  mode_dependent: '모드 의존',
  engine_idle: '엔진 정지',
}

/** 2-5. 손절선 종류 `stop_kind`. */
export function stopKindLabel(kind: string | null): string {
  if (kind === null) return '—'
  return STOP_KIND_LABELS[kind] ?? kind
}

const STOP_EVENT_LABELS: Record<string, string> = {
  first: '첫 관측',
  change: '변경',
  boot: '재시작',
  eod: '장마감',
  paused: '손절 정지',
  exit: '청산 직전',
}

/** 2-5. 손절선 사건 `event`. */
export function stopEventLabel(event: string): string {
  return STOP_EVENT_LABELS[event] ?? event
}

const DIVISION_LABELS: Record<string, string> = {
  '01': '시장가',
  '00': '지정가',
  '27': '프리 GTP 지정가',
  '41': '애프터 지정가',
  '44': '애프터 최유리',
}

/** 2-6. 주문구분 `division`. */
export function divisionLabel(code: string | null): string | null {
  if (code === null) return null
  return DIVISION_LABELS[code] ?? `코드 ${code}`
}

/** 2-6. 판단가 출처 `judge.src`. */
export function judgeSrcLabel(src: string | null): string | null {
  switch (src) {
    case 'signal':
      return '신호 틱 가격'
    case 'log_price':
      return '로그 현재가'
    case 'log_pct':
      return '역산(±0.05%p)'
    case 'restored_ai':
      return '복원(AI평가)'
    default:
      return null
  }
}

/** 2-6. 매수 `signal_src` — `ring` 은 배지 없음(null). */
export function signalSrcLabel(src: string | null): string | null {
  switch (src) {
    case 'log_only':
      return '신호가만'
    case 'none':
      return '신호 기록 없음'
    default:
      return null
  }
}

const VAL_SRC_LABELS: Record<string, string> = {
  live: '기록',
  restored: '복원',
  restored_ai: '복원(AI평가)',
  snapshot: '스냅샷',
  derived: '계산',
  inferred: '추정',
  computed: '계산',
}

/** 2-6. 값 출처 `ValSrc` — `trade`(거래기록 원본)는 칩을 달지 않는다(null). */
export function valSrcLabel(src: string | null): string | null {
  if (src === null || src === 'trade') return null
  return VAL_SRC_LABELS[src] ?? src
}

const COST_STATUS_LABELS: Record<CostStatus, string> = {
  settled: '정산',
  estimated: '추정',
  mixed: '일부 추정',
}

/** 2-6. 비용 상태 `CostStatus`. */
export function costStatusLabel(status: CostStatus): string {
  return COST_STATUS_LABELS[status] ?? status
}

const BOARD_LABELS: Record<string, string> = {
  main: '본장',
  pre_nxt: 'NXT 프리',
  post_nxt: 'NXT 애프터',
}

/** 2-6. VB·LTV `board`. */
export function boardLabel(board: string): string {
  return BOARD_LABELS[board] ?? board
}

const NA_LABELS: Record<NaKind, string> = {
  before_record: '기록 전',
  unknown: '—',
  not_applicable: '해당 없음',
  pending: '대기',
  lookup_failed: '조회 실패',
}

/** 5절. 빈칸 이유 5종 — 서로 다른 문구, 숫자 0 을 쓰지 않는다. */
export function naLabel(na: NaKind): string {
  return NA_LABELS[na]
}
