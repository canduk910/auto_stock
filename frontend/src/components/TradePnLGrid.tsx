import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { getTradePnL } from '../api/history'
import {
  findLlmSummary,
  getLlmEvaluationSummaries,
  llmSummaryDatesFor,
} from '../api/llm-evaluations'
import { getStrategyColor } from '../types/strategy'
import type { TradePair } from '../types/trading'
import type { LlmEvaluationSummaryMap } from '../types/llm-evaluation'
import LlmEvaluationModal from './LlmEvaluationModal'
import LlmScoreBadge from './LlmScoreBadge'

const STRATEGY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '20일 신고가 스윙',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: '변동성 수축 돌파',
  kojiro: '고지로 대순환',
}

const columnHelper = createColumnHelper<TradePair>()

function fmtDate(d: string | null): string {
  if (!d) return '—'
  // YYYY-MM-DD → YY-MM-DD
  const [y, m, dd] = d.split('-')
  return y && m && dd ? `${y.slice(2)}-${m}-${dd}` : d
}

function fmtNum(n: number | null | undefined, suffix = ''): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return n.toLocaleString() + suffix
}

function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return 'text-gray-700'
  return v > 0 ? 'text-red-600 font-medium' : 'text-blue-600 font-medium'
}

/**
 * cycle276 — 열 정의를 모듈 상수에서 **팩토리**로 바꾼다.
 *
 * 손익 화면은 테이블이 아니라 `get_trade_pairs` 가 매번 계산하는 뷰다(명세 §8). 그래서
 * 행을 가리키는 키가 `pair_key`(= `전략:종목:첫 매수 order_no`)이고, 평가 조회 키는
 * **`buy_order_nos`(복수)** 다 — 운영 DB 전 기간 614행 중 9건이 매수 주문 2건 이상을
 * 품은 페어라 단수 필드로는 그 사이클의 평가를 다 못 가리킨다.
 */
function makeColumns(
  summaries: LlmEvaluationSummaryMap,
  summariesReady: boolean,
  onOpen: (orderNos: string[], tradeDate: string | undefined) => void,
) {
  return [
  columnHelper.accessor('buy_date', {
    header: '매수일',
    cell: (info) => fmtDate(info.getValue()),
  }),
  columnHelper.accessor('buy_time', {
    header: '매수체결시각',
    cell: (info) => info.getValue() ?? '—',
  }),
  columnHelper.accessor('sell_date', {
    header: '매도일',
    cell: (info) => fmtDate(info.getValue()),
  }),
  columnHelper.accessor('sell_time', {
    header: '매도체결시각',
    cell: (info) => info.getValue() ?? '—',
  }),
  columnHelper.accessor('ticker', {
    header: '종목코드',
    cell: (info) => info.getValue() ?? '-',
  }),
  columnHelper.accessor('ticker_name', {
    header: '종목명',
    cell: (info) => info.getValue() || '-',
  }),
  columnHelper.accessor('buy_price', {
    header: '매수체결가',
    cell: (info) => fmtNum(info.getValue(), '원'),
  }),
  columnHelper.accessor('buy_qty', {
    header: '매수체결수량',
    cell: (info) => fmtNum(info.getValue(), '주'),
  }),
  columnHelper.accessor('sell_price', {
    header: '매도체결가',
    cell: (info) => fmtNum(info.getValue(), '원'),
  }),
  columnHelper.accessor('sell_qty', {
    header: '매도체결수량',
    cell: (info) => fmtNum(info.getValue(), '주'),
  }),
  columnHelper.accessor('profit_loss', {
    header: '매매손익',
    cell: (info) => {
      const v = info.getValue()
      const status = info.row.original.status
      if (v === null || v === undefined || !Number.isFinite(v)) {
        return <span className="text-gray-400">{status === 'open' ? '(미실현 시세 대기)' : '—'}</span>
      }
      const sign = v > 0 ? '+' : ''
      const prefix = status === 'open' ? '(미실현) ' : ''
      return <span className={pnlClass(v)}>{prefix}{sign}{v.toLocaleString()}원</span>
    },
  }),
  columnHelper.accessor('profit_rate', {
    header: '손익율',
    cell: (info) => {
      const v = info.getValue()
      const status = info.row.original.status
      if (v === null || v === undefined || !Number.isFinite(v)) {
        return <span className="text-gray-400">—</span>
      }
      const sign = v > 0 ? '+' : ''
      const prefix = status === 'open' ? '(미실현) ' : ''
      return <span className={pnlClass(v)}>{prefix}{sign}{v.toFixed(2)}%</span>
    },
  }),
  columnHelper.accessor('strategy', {
    header: '전략',
    cell: (info) => {
      const v = String(info.getValue() ?? '')
      const color = getStrategyColor(v)
      const name = STRATEGY_NAMES[v] ?? v
      return <span className={`px-1.5 py-0.5 rounded text-xs ${color.badge}`}>{name}</span>
    },
  }),
  // cycle276 — AI 매수평가 팝업 버튼(맨 끝 열).
  // 활성 조건은 "이 페어를 만든 매수 주문 중 **하나라도** 평가 기록이 있는가" 다.
  // 주문번호가 없는 페어(수기 매매 등, 운영 DB 실측 9행)는 가리킬 대상이 없어 비활성이고,
  // 왜 못 누르는지를 title 로 알린다 — 침묵은 결함처럼 보인다.
  columnHelper.display({
    id: 'llmEval',
    header: 'AI 자문',
    cell: (info) => {
      const pair = info.row.original
      const buyOrderNos = (pair.buy_order_nos ?? [])
        .map((no) => String(no ?? '').trim())
        .filter((no) => no !== '')
      // 조회 대상인지(매수 주문번호가 있는가)는 요약 응답 없이 확정된다. 대상인데 아직
      // 답을 못 받은 구간에 "평가 기록 없음" 을 띄우면 거짓말이므로 별도 상태로 그린다.
      if (buyOrderNos.length > 0 && !summariesReady) {
        return (
          <button
            type="button"
            data-testid={`llm-eval-btn-pair-loading-${info.row.index}`}
            disabled
            title="평가 기록 조회 중..."
            className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-300 cursor-progress"
          >
            AI 자문{buyOrderNos.length > 1 ? ` (${buyOrderNos.length})` : ''}
          </button>
        )
      }
      // ⚠️ 배치 요약은 **날짜 없이** 묻고 상세는 `pair.buy_date` 와 **함께** 묻는다.
      // KIS 주문번호(ODNO)는 하루 단위로만 유일하므로, 같은 번호가 다른 날 재사용됐으면
      // "버튼은 활성인데 모달은 404" 조합이 생긴다. 그래서 배치 응답 맵의 키가
      // `날짜|주문번호` 복합 키이고, 이 셀은 페어의 **첫 매수일**로 조회한 주문만 활성
      // 근거로 센다 — 활성 ⇔ 상세 요청이 답을 받는다. 멀티데이 피라미딩의 둘째 매수
      // (다른 날 주문)는 이 행에서 열 수 없고 title 로 알린다.
      const buyDate = pair.buy_date ?? undefined
      const matchedOrderNos = buyOrderNos.filter(
        (no) => Boolean(findLlmSummary(summaries, buyDate, no)),
      )
      const hasEval = matchedOrderNos.length > 0
      const otherDateOnly =
        !hasEval && buyOrderNos.some((no) => llmSummaryDatesFor(summaries, no).length > 0)
      const pairKey = pair.pair_key
      const testId = pairKey
        ? `llm-eval-btn-pair-${pairKey}`
        : `llm-eval-btn-pair-none-${info.row.index}`
      const title =
        buyOrderNos.length === 0
          ? '매수 주문번호 없음 — 평가 기록 없음'
          : hasEval
            ? 'AI 매수평가 보기'
            : otherDateOnly
              ? '다른 날짜의 평가 기록 — 이 행에서 열 수 없음'
              : '평가 기록 없음'
      // cycle337 — 점수를 버튼 **왼쪽**에 그린다(추가 조회 0 — 이미 받은 요약이다).
      // 🔴 한 페어에 평가가 여럿이면 **첫 매수** 기준이다. 회고 정본
      // (`llm_retrospective.join_pairs_with_evaluations`)이 `buy_order_nos[0]` 의 평가를
      // `primary` 로 삼으므로 화면도 같은 것을 보여야 한다 — 다른 것을 고르면 화면과
      // 회고 통계가 조용히 갈린다. `matchedOrderNos` 는 `buyOrderNos` 순서(시간순)를
      // 보존한 filter 결과라 그 첫 원소가 곧 「가장 이른 평가」다.
      const primarySummary = hasEval
        ? findLlmSummary(summaries, buyDate, matchedOrderNos[0])
        : null
      return (
        <div className="flex items-center gap-1.5">
          <LlmScoreBadge
            summary={primarySummary}
            matchedCount={matchedOrderNos.length}
            testId={pairKey ? `llm-score-pair-${pairKey}` : `llm-score-pair-none-${info.row.index}`}
          />
          <button
            type="button"
            data-testid={testId}
            disabled={!hasEval}
            title={title}
            // 날짜(`buyDate`)를 **반드시** 함께 넘긴다 — 빼면 라우트가 "가장 최근 1건" 을
            // 골라 같은 번호가 재사용된 **다른 거래의 평가**를 띄운다(회귀 가드 F25b).
            onClick={() => onOpen(buyOrderNos, buyDate)}
            className={`px-2 py-1 text-xs rounded border ${
              hasEval
                ? 'border-blue-300 text-blue-700 hover:bg-blue-50'
                : 'border-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            AI 자문{buyOrderNos.length > 1 ? ` (${buyOrderNos.length})` : ''}
          </button>
        </div>
      )
    },
  }),
  ]
}

export default function TradePnLGrid() {
  const [page, setPage] = useState(1)
  const size = 30
  const [strategyFilter, setStrategyFilter] = useState<string>('')
  const [selected, setSelected] = useState<
    { orderNos: string[]; tradeDate?: string } | null
  >(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tradePnL', page, strategyFilter],
    retry: 1,
    queryFn: () => getTradePnL({ page, size, strategy: strategyFilter || undefined }),
  })

  const pairs = data?.pairs ?? []

  // cycle276 — 이 페이지의 모든 `buy_order_nos` 를 flat 하게 모아 **한 요청**으로 조회한다.
  // 페어마다 개별 조회하면 페이지당 30 요청이 나간다(명세 §10.3 · 뮤테이션 M19).
  const buyOrderNos = useMemo(
    () =>
      Array.from(
        new Set(
          pairs.flatMap((p) =>
            (p.buy_order_nos ?? []).map((no) => String(no ?? '').trim()).filter((no) => no !== ''),
          ),
        ),
      ),
    [pairs],
  )
  const orderNosKey = buyOrderNos.join(',')

  const { data: summaries, isFetched: summariesFetched } = useQuery({
    queryKey: ['llmEvalSummaries', 'pnl', page, strategyFilter, orderNosKey],
    retry: 1,
    enabled: buyOrderNos.length > 0,
    queryFn: () => getLlmEvaluationSummaries(buyOrderNos),
  })

  // 조회가 **끝났는가**(성공/실패 무관). 실패해도 손익 표를 막지 않는다.
  const summariesReady = buyOrderNos.length === 0 || summariesFetched

  const columns = useMemo(
    () =>
      makeColumns(summaries ?? {}, summariesReady, (orderNos, tradeDate) =>
        setSelected({ orderNos, tradeDate }),
      ),
    [summaries, summariesReady],
  )
  const summary = data?.summary ?? {
    realized_total_krw: 0,
    realized_rate_pct: 0,
    win_count: 0,
    loss_count: 0,
    even_count: 0,
    win_rate_pct: 0,
    closed_count: 0,
  }
  const strategyLabel = strategyFilter ? (STRATEGY_NAMES[strategyFilter] ?? strategyFilter) : '전체'

  const table = useReactTable({
    data: pairs,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (isLoading) return <div className="p-6 text-gray-500">매매손익 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">매매손익을 불러올 수 없습니다.</div>

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">전략</label>
          <select
            value={strategyFilter}
            onChange={(e) => {
              setStrategyFilter(e.target.value)
              setPage(1)
            }}
            className="text-sm border border-gray-300 rounded px-2 py-1"
          >
            <option value="">전체</option>
            <option value="momentum">모멘텀</option>
            <option value="volatility_breakout">변동성돌파</option>
            <option value="long_tail_volatility">롱테일 변동성</option>
            <option value="donchian_swing">20일 신고가 스윙</option>
            <option value="bull_flag_breakout">눌림목 돌파</option>
            <option value="vcp_breakout">변동성 수축 돌파</option>
            <option value="kojiro">고지로 대순환</option>
          </select>
        </div>
        <span className="text-xs text-gray-400">
          매수→매도 페어 {data?.total ?? 0}건 (보유 중: open 행)
        </span>
      </div>

      <div
        data-testid="pnl-summary"
        className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 border-b bg-gray-50/60 text-sm text-gray-600"
      >
        <span>
          실현 합계{' '}
          <span data-testid="pnl-summary-realized" className={pnlClass(summary.realized_total_krw)}>
            {summary.realized_total_krw.toLocaleString()}원
          </span>
        </span>
        <span>손익율 {summary.realized_rate_pct.toFixed(1)}%</span>
        <span>
          승 {summary.win_count}/패 {summary.loss_count}/보합 {summary.even_count}
        </span>
        <span>승률 {summary.win_rate_pct.toFixed(1)}%</span>
        <span className="text-gray-400">전략: {strategyLabel}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-3 py-3 text-left font-medium text-gray-600 whitespace-nowrap"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {pairs.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400">
                  매매손익 데이터가 없습니다.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const isOpen = row.original.status === 'open'
                return (
                  <tr
                    key={row.id}
                    className={`border-b hover:bg-gray-50 ${isOpen ? 'bg-emerald-50/40' : ''}`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2.5 text-gray-700 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between px-4 py-3 border-t">
        <span className="text-sm text-gray-500">
          총 {data?.total ?? 0}건 (페이지 {page}/{data?.total_pages ?? 1})
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50"
          >
            이전
          </button>
          <button
            onClick={() => setPage((p) => Math.min(data?.total_pages ?? 1, p + 1))}
            disabled={page >= (data?.total_pages ?? 1)}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50"
          >
            다음
          </button>
        </div>
      </div>

      {selected && (
        <LlmEvaluationModal
          orderNos={selected.orderNos}
          tradeDate={selected.tradeDate}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
