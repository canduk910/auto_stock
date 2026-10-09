/**
 * cycle413 Red — 거래일지 한국어 표기 정본 `src/utils/journalLabels.ts` (명세 2절·5절 표).
 *
 * 서버는 코드만 보내고 화면이 이 한 곳에서 짧은 트레이더 말로 바꾼다(문장 = 이유·원인만 서버).
 * 계약 = `_workspace/red/cycle413/journal_view_contract.md` 4절.
 */
import { describe, expect, it } from 'vitest'

import * as L from '../journalLabels'

describe('cycle413 — journalLabels 표기표', () => {
  it('2-1 청산 사유 코드 → 배지', () => {
    const table: Array<[string | null, string]> = [
      ['ENTRY', '진입'], ['STOP_LOSS', '손절'], ['TRAILING_STOP', '트레일링'], ['TAKE_PROFIT', '익절'],
      ['TIME_EXIT', '시간 청산'], ['TREND_EXIT', '추세 종료'], ['FORCE_CLEAR', '15:20 청산'],
      ['NEXT_DAY_CLEAR', '익일 청산'], ['STATUS_EXIT', '종목상태 청산'], ['MANUAL', '수동 매도'], [null, '사유 없음'],
    ]
    for (const [code, label] of table) expect(L.reasonCodeLabel(code)).toBe(label)
  })

  it('2-2 세부 사유 — 모르는 값은 원문 그대로', () => {
    const table: Array<[string, string]> = [
      ['gap_below', '갭 미달'], ['krx_only', 'KRX 전용'], ['nxt_open_missing', 'NXT 시가 미수신'],
      ['managed', '관리종목'], ['overheat', '단기과열'], ['managed+overheat', '관리·과열'],
      ['something_new', 'something_new'],
    ]
    for (const [sub, label] of table) expect(L.reasonSubLabel(sub)).toBe(label)
    expect(L.reasonSubLabel(null)).toBeNull()
  })

  it('2-3 사유 줄 phrase 16종', () => {
    const table: Array<[string, string]> = [
      ['kojiro_hard_stop', '하드 손절'], ['kojiro_atr_stop', 'ATR 손절'], ['kojiro_trailing', '샹들리에 트레일'],
      ['kojiro_stage3_exit', '스테이지3 — 추세 종료'], ['bfb_turtle_stop', '터틀 손절(E−2N)'],
      ['bfb_turtle_backstop', '받침선 손절'], ['bfb_pullback_stop', '눌림목 손절'],
      ['bfb_measured_target', '측정 목표 도달'], ['bfb_time_exit', '보유 기한 초과'],
      ['ltv_intraday_stop', '당일 모드 손절'], ['ltv_limit_up_stop', '상한가 모드 손절'], ['vb_stop', '고정 손절'],
      ['momentum_stop', '고정 손절'], ['donchian_time_exit', '시간 청산'],
      ['donchian_time_exit_legacy', '시간 청산(옛 규칙)'], ['donchian_trailing_legacy', '트레일(옛 규칙)'],
    ]
    for (const [p, label] of table) expect(L.phraseLabel(p)).toBe(label)
    expect(L.phraseLabel(null)).toBeNull()
  })

  it('2-4 일지 행 출처 배지', () => {
    const table: Array<[string, string]> = [
      ['log_harvest', '기록'], ['log_restore', '복원'], ['fallback_inferred', '추정·폴백'],
      ['reorder_inferred', '추정·재주문'], ['manual_api', '수동'], ['external', '외부 주문'], ['unmatched', '매핑 없음'],
    ]
    for (const [s, label] of table) expect(L.sourceLabel(s)).toBe(label)
  })

  it('2-5 손절선 종류·사건', () => {
    expect(L.stopKindLabel('effective')).toBe('전략 손절선')
    expect(L.stopKindLabel('hard_pct')).toBe('고정% 손절선')
    expect(L.stopKindLabel('mode_dependent')).toBe('모드 의존')
    expect(L.stopKindLabel('engine_idle')).toBe('엔진 정지')
    expect(L.stopKindLabel(null)).toBe('—')
    const events: Array<[string, string]> = [
      ['first', '첫 관측'], ['change', '변경'], ['boot', '재시작'], ['eod', '장마감'], ['paused', '손절 정지'],
      ['exit', '청산 직전'],
    ]
    for (const [e, label] of events) expect(L.stopEventLabel(e)).toBe(label)
  })

  it('2-6 주문구분 · 판단가 출처 · 신호 출처 · 값 출처 · 비용 상태 · 보드', () => {
    const div: Array<[string, string]> = [
      ['01', '시장가'], ['00', '지정가'], ['27', '프리 GTP 지정가'], ['41', '애프터 지정가'], ['44', '애프터 최유리'],
      ['99', '코드 99'],
    ]
    for (const [c, label] of div) expect(L.divisionLabel(c)).toBe(label)
    expect(L.divisionLabel(null)).toBeNull()

    expect(L.judgeSrcLabel('signal')).toBe('신호 틱 가격')
    expect(L.judgeSrcLabel('log_price')).toBe('로그 현재가')
    expect(L.judgeSrcLabel('log_pct')).toContain('역산')
    expect(L.judgeSrcLabel('restored_ai')).toBe('복원(AI평가)')

    expect(L.signalSrcLabel('ring')).toBeNull() // 배지 없음
    expect(L.signalSrcLabel('log_only')).toBe('신호가만')
    expect(L.signalSrcLabel('none')).toBe('신호 기록 없음')

    expect(L.valSrcLabel('trade')).toBeNull() // 거래기록 원본엔 칩을 달지 않는다
    const vs: Array<[string, string]> = [
      ['live', '기록'], ['restored', '복원'], ['restored_ai', '복원(AI평가)'], ['snapshot', '스냅샷'],
      ['derived', '계산'], ['inferred', '추정'], ['computed', '계산'],
    ]
    for (const [s, label] of vs) expect(L.valSrcLabel(s)).toBe(label)

    expect(L.costStatusLabel('settled')).toBe('정산')
    expect(L.costStatusLabel('estimated')).toBe('추정')
    expect(L.costStatusLabel('mixed')).toBe('일부 추정')

    expect(L.boardLabel('main')).toBe('본장')
    expect(L.boardLabel('pre_nxt')).toBe('NXT 프리')
    expect(L.boardLabel('post_nxt')).toBe('NXT 애프터')
  })

  it('5절 빈칸 이유 5종 — 서로 다른 문구, 숫자 0 이 아니다', () => {
    const table: Array<[string, string]> = [
      ['before_record', '기록 전'], ['unknown', '—'], ['not_applicable', '해당 없음'], ['pending', '대기'],
      ['lookup_failed', '조회 실패'],
    ]
    for (const [na, label] of table) expect(L.naLabel(na as never)).toBe(label)
    const labels = table.map(([na]) => L.naLabel(na as never))
    expect(new Set(labels).size).toBe(5)
    for (const s of labels) expect(s).not.toMatch(/^0/)
  })
})
