/**
 * 거래일지 차트 — 카드 내용을 그림 좌표로 바꾸는 순수 함수(cycle457).
 *
 * 🔴 **기술적 지표(이평선·ATR·MACD·돌파선·목표가)는 여기서 계산하지 않는다** — 사용자 지시(2026-10-15)
 * 「기술적지표 계산함수를 설마 새로 만든거야? … 명백히 소스 중복아닌가」. 지표는 백엔드
 * `GET /api/journal-chart` 가 그 전략이 매수·청산 판정에 쓰는 같은 함수(`chart_indicators`)로 계산해 보내고,
 * 화면은 받은 값을 그리기만 한다.
 *
 * 이 파일이 하는 일 = 카드(`JournalCard`)의 기록을 차트 위치로 옮기는 것뿐이다.
 * - `tradeMarks` — 매수 체결·매도 체결 → (날짜, 가격) 표시.
 * - `stopSteps` · `targetSteps` — 손절선 기록(`stop_track.rows`)·익절 목표 → 봉 날짜마다의 계단 값.
 *
 * 날짜는 전부 KST 이고 `utils/kst.ts` 에 위임한다(이 파일은 날짜 포맷터를 만들지 않는다).
 */

import { formatKstDateTime } from './kst'
import type { JournalCard } from '../types/journal'

/** ISO 시각 → KST 날짜 `YYYY-MM-DD`. 잘못된 입력 → null. */
export function kstDateOf(iso: string | null | undefined): string | null {
  const s = formatKstDateTime(iso)
  return s === '—' ? null : s.slice(0, 10)
}

export interface TradeMark {
  side: 'BUY' | 'SELL'
  date: string
  price: number
  qty: number
  label: string
}

/** 매수 체결(`entry.orders`)·매도 체결(`exits`) → 차트 표시. 날짜·가격이 없는 줄은 뺀다. */
export function tradeMarks(card: JournalCard): TradeMark[] {
  const out: TradeMark[] = []
  const push = (side: 'BUY' | 'SELL', at: string, price: number, qty: number) => {
    const date = kstDateOf(at)
    if (!date || !(price > 0)) return
    const word = side === 'BUY' ? '매수' : '매도'
    out.push({ side, date, price, qty, label: `${word} ${Math.round(price).toLocaleString('ko-KR')}×${qty}` })
  }
  for (const o of card.entry.orders) push('BUY', o.at, o.price, o.qty)
  for (const e of card.exits) push('SELL', e.at, e.price, e.qty)
  return out
}

/** 보유 구간 `[첫 매수일, 마지막 매도일 또는 null(보유 중)]`. */
export function holdRange(card: JournalCard): { from: string | null; to: string | null } {
  return { from: kstDateOf(card.opened_at), to: card.status === 'open' ? null : kstDateOf(card.closed_at) }
}

/**
 * 손절선 계단 — 봉 날짜마다 「그날 장 끝까지 기록된 마지막 손절선」. 보유 구간 밖은 null.
 * 기록(`stop_track.rows`)이 없으면 최초 손절(`entry.initial_stop.price`) 한 값으로 편다. 둘 다 없으면 전부 null.
 */
export function stopSteps(dates: string[], card: JournalCard): (number | null)[] {
  const { from, to } = holdRange(card)
  const events: { date: string; price: number }[] = []
  for (const r of card.stop_track.rows) {
    const d = kstDateOf(r.at)
    if (d && r.price !== null && r.price > 0) events.push({ date: d, price: r.price })
  }
  const initial = card.entry.initial_stop.price
  if (events.length === 0 && (initial === null || !(initial > 0))) return dates.map(() => null)
  return dates.map((d) => {
    if (!from || d < from || (to && d > to)) return null
    let v: number | null = initial !== null && initial > 0 ? initial : null
    for (const e of events) if (e.date <= d) v = e.price
    return v
  })
}

/** 익절 목표 — 보유 구간 안의 봉에만 `entry.target.price` 한 값. 목표가 없으면 전부 null. */
export function targetSteps(dates: string[], card: JournalCard): (number | null)[] {
  const t = card.entry.target.price
  const { from, to } = holdRange(card)
  return dates.map((d) => (t !== null && t > 0 && from && d >= from && (!to || d <= to) ? t : null))
}
