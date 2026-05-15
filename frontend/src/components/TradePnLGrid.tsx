import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { getTradePnL } from '../api/history'
import { getStrategyColor } from '../types/strategy'
import type { TradePair } from '../types/trading'

const STRATEGY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '20일 신고가 스윙',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: '변동성 수축 돌파',
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

const columns = [
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
]

export default function TradePnLGrid() {
  const [page, setPage] = useState(1)
  const size = 30
  const [strategyFilter, setStrategyFilter] = useState<string>('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tradePnL', page, strategyFilter],
    queryFn: () => getTradePnL({ page, size, strategy: strategyFilter || undefined }),
  })

  const pairs = data?.pairs ?? []

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
          </select>
        </div>
        <span className="text-xs text-gray-400">
          매수→매도 페어 {data?.total ?? 0}건 (보유 중: open 행)
        </span>
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
    </div>
  )
}
