// cycle413 — 거래일지 탭 (명세 `_workspace/red/cycle413/journal_view_spec.md` 8-1 필터줄).
//
// 세후/세전은 기존 `useCostBasis` 를 공유한다(다른 화면 토글과 함께 바뀐다). 일지 탭을
// 누르기 전엔 `History.tsx` 가 이 컴포넌트를 마운트하지 않으므로 `/api/history/journal`
// 을 부르지 않는다(J1).
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getJournal } from '../api/history'
import { useCostBasis } from '../utils/costBasis'
import CostBasisToggle from './CostBasisToggle'
import JournalCard from './JournalCard'
import { kstTodayISO } from '../utils/kst'
import { STRATEGY_DISPLAY_NAMES } from '../utils/strategyMeta'
import type { JournalQuery } from '../types/journal'

type StatusFilter = 'all' | 'open' | 'closed'
type OutcomeFilter = 'all' | 'win' | 'loss'
type SortFilter = 'recent' | 'pnl_asc' | 'pnl_desc'
type PeriodDays = 7 | 30 | 90

/** 명세 8-1 「기간(7일·30일·90일)」 — UTC 날짜 차로 `from` 을 구한다(테스트와 같은 산식). */
function subDaysISO(todayISO: string, days: number): string {
  const d = new Date(`${todayISO}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

export default function JournalTab() {
  const [basis, setBasis] = useCostBasis()
  const [periodDays, setPeriodDays] = useState<PeriodDays>(30)
  const [status, setStatus] = useState<StatusFilter>('all')
  const [outcome, setOutcome] = useState<OutcomeFilter>('all')
  const [sort, setSort] = useState<SortFilter>('recent')
  const [strategy, setStrategy] = useState('')
  const [ticker, setTicker] = useState('')

  const to = kstTodayISO()
  const from = subDaysISO(to, periodDays)

  const params: JournalQuery = {
    from,
    to,
    status,
    outcome,
    basis,
    sort,
    page: 1,
    size: 20,
    strategy: strategy || undefined,
    ticker: ticker || undefined,
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['journal', params],
    queryFn: () => getJournal(params),
  })

  const recordStart = data?.record_start

  const recordLine = useMemo(() => {
    if (!recordStart) return null
    if (!recordStart.orders_restored && !recordStart.orders_live && !recordStart.stops && !recordStart.order_price) {
      return '실시간 기록 대기'
    }
    const ordersFrom = recordStart.orders_restored ?? recordStart.orders_live
    const liveTail = recordStart.orders_restored && recordStart.orders_live
      ? `(${recordStart.orders_live} 전은 과거 로그 복원)`
      : ''
    return `이유 기록 ${ordersFrom ?? '—'}부터${liveTail} · 손절선 기록 ${recordStart.stops ?? '—'}부터`
  }, [recordStart])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500">거래일지</span>
        <CostBasisToggle value={basis} onChange={setBasis} />
      </div>

      <div data-testid="journal-record-start" className="text-xs text-gray-400">
        {recordLine ?? ' '}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          data-testid="journal-filter-period-7"
          onClick={() => setPeriodDays(7)}
          className={`px-2 py-1 border rounded ${periodDays === 7 ? 'bg-gray-900 text-white' : 'text-gray-600'}`}
        >
          7일
        </button>
        <button
          type="button"
          data-testid="journal-filter-period-30"
          onClick={() => setPeriodDays(30)}
          className={`px-2 py-1 border rounded ${periodDays === 30 ? 'bg-gray-900 text-white' : 'text-gray-600'}`}
        >
          30일
        </button>
        <button
          type="button"
          data-testid="journal-filter-period-90"
          onClick={() => setPeriodDays(90)}
          className={`px-2 py-1 border rounded ${periodDays === 90 ? 'bg-gray-900 text-white' : 'text-gray-600'}`}
        >
          90일
        </button>

        <select
          data-testid="journal-filter-status"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusFilter)}
          className="border border-gray-300 rounded px-1 py-1"
        >
          <option value="all">전체</option>
          <option value="open">보유중</option>
          <option value="closed">청산</option>
        </select>

        <select
          data-testid="journal-filter-outcome"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value as OutcomeFilter)}
          className="border border-gray-300 rounded px-1 py-1"
        >
          <option value="all">전체</option>
          <option value="win">이익</option>
          <option value="loss">손실</option>
        </select>

        <select
          data-testid="journal-filter-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortFilter)}
          className="border border-gray-300 rounded px-1 py-1"
        >
          <option value="recent">최근</option>
          <option value="pnl_asc">손실 큰 순</option>
          <option value="pnl_desc">이익 큰 순</option>
        </select>

        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="border border-gray-300 rounded px-1 py-1"
        >
          <option value="">전략 전체</option>
          {Object.entries(STRATEGY_DISPLAY_NAMES).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>

        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="종목코드"
          className="border border-gray-300 rounded px-1 py-1 w-20"
        />

        <button
          type="button"
          data-testid="journal-filter-toggle"
          className="px-2 py-1 border rounded text-gray-600 sm:hidden"
        >
          필터
        </button>

        {data && (
          <span data-testid="journal-counts" className="text-xs text-gray-400 ml-auto">
            총 {data.counts.total} · 보유 {data.counts.open} · 청산 {data.counts.closed}
          </span>
        )}
      </div>

      {isLoading && <div className="text-gray-400 text-sm py-6">거래일지를 불러오는 중...</div>}
      {isError && <div className="text-red-500 text-sm py-6">거래일지를 불러올 수 없습니다 — 서버 연결 끊김</div>}
      {!isLoading && !isError && data && data.cards.length === 0 && (
        <div className="text-gray-400 text-sm py-6">거래일지 데이터가 없습니다.</div>
      )}
      <div className="space-y-3">
        {!isLoading && !isError && data &&
          data.cards.map((card) => (
            <JournalCard key={card.anchor_trade_id} card={card} basis={basis} stopsRecordStart={data.record_start.stops} />
          ))}
      </div>
    </div>
  )
}
