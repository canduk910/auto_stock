/**
 * cycle457 — 거래일지 차트 순수 함수(`utils/journalChart.ts`) — 카드 기록을 그림 위치로 옮기는 것만.
 *
 * - J0: 이 파일은 기술적 지표를 계산하지 않는다(지표 = 백엔드 `chart_indicators`, 사용자 지시 「소스 중복」)
 * - J4: 매수·매도 표시 — KST 날짜 · 가격 0 이하 제외
 * - J5: 손절선 계단 · 익절 목표 — 보유 구간 안에만
 */
import { describe, expect, it } from 'vitest'

import { readFileSync } from 'fs'
import path from 'path'

import * as journalChart from '../journalChart'
import { kstDateOf, stopSteps, targetSteps, tradeMarks } from '../journalChart'
import { JOURNAL_FIXTURE } from '../../test/fixtures/journal.fixture'
import type { JournalCard } from '../../types/journal'

const [CARD_OPEN, CARD_BFB] = JOURNAL_FIXTURE.cards as unknown as JournalCard[]

describe('J0 지표 계산 없음', () => {
  it('공개 함수는 카드 → 표시 변환뿐이다', () => {
    expect(Object.keys(journalChart).sort()).toEqual(
      ['holdRange', 'kstDateOf', 'stopSteps', 'targetSteps', 'tradeMarks'],
    )
  })

  it('거래일지 차트 화면·유틸 소스에 EMA·ATR·MACD 계산식이 없다', () => {
    const root = path.join(__dirname, '..', '..')
    for (const rel of ['utils/journalChart.ts', 'components/JournalChartModal.tsx']) {
      const src = readFileSync(path.join(root, rel), 'utf-8')
      expect(src, rel).not.toMatch(/2\s*\/\s*\(\s*\w+\s*\+\s*1\s*\)/) // EMA 평활계수 2/(n+1)
      expect(src, rel).not.toMatch(/Math\.max\([^)]*Math\.abs/) // True Range
    }
  })
})

describe('J4 tradeMarks', () => {
  it('매수·매도 체결을 KST 날짜와 가격으로', () => {
    const m = tradeMarks(CARD_BFB)
    expect(m.filter((x) => x.side === 'BUY')).toEqual([
      expect.objectContaining({ date: '2026-10-05', price: 12350, qty: 40, label: '매수 12,350×40' }),
    ])
    expect(m.filter((x) => x.side === 'SELL').length).toBe(CARD_BFB.exits.length)
  })

  it('UTC 로 적힌 시각도 KST 날짜로 · 가격 0 이하는 뺀다', () => {
    expect(kstDateOf('2026-10-05T16:00:00Z')).toBe('2026-10-06')
    const card = JSON.parse(JSON.stringify(CARD_OPEN)) as JournalCard
    card.entry.orders[0].price = 0
    expect(tradeMarks(card)).toEqual([])
  })
})

describe('J5 손절선 계단 · 익절 목표', () => {
  const dates = ['2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-12']

  it('보유 중 카드 — 기록 첫날부터 그날 마지막 값, 매수 전은 null', () => {
    // 최초 손절 가격이 없고(기록 시작 전) 기록은 10-07 47,800 → 10-08 47,500
    expect(stopSteps(dates, CARD_OPEN)).toEqual([null, null, null, 47800, 47500, 47500, 47500])
  })

  it('닫힌 카드 — 매수일~매도일만, 기록 전 날은 최초 손절', () => {
    const s = stopSteps(dates, CARD_BFB)
    expect(s[0]).toBeNull()
    expect(s[1]).not.toBeNull()
    expect(s[5]).toBeNull() // 10-08 청산 뒤
    const t = targetSteps(dates, CARD_BFB)
    const target = CARD_BFB.entry.target.price
    expect(t.slice(1, 5)).toEqual([target, target, target, target])
    expect(t[0]).toBeNull()
    expect(t[5]).toBeNull()
  })

  it('목표·손절 기록이 없으면 전부 null', () => {
    expect(targetSteps(dates, CARD_OPEN).every((v) => v === null)).toBe(true)
    const card = JSON.parse(JSON.stringify(CARD_OPEN)) as JournalCard
    card.stop_track.rows = []
    expect(stopSteps(dates, card).every((v) => v === null)).toBe(true)
  })
})
