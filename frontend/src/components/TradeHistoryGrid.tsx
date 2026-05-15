import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { getTradeHistory } from '../api/history'
import { getStrategyColor } from '../types/strategy'
import type { TradeRecord } from '../types/trading'

const columnHelper = createColumnHelper<TradeRecord>()

// KST(Asia/Seoul) 강제 — 백엔드 `_to_kst` 와 동일 컨벤션.
// 함수명만 KST 라고 붙이고 실제론 브라우저 로컬타임을 추출하던 결함 차단.
// `Intl.DateTimeFormat` 의 ko-KR 출력은 `2026. 05. 12.` / `08:05:47` 형태로 안정.
const KST_DATE_FMT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: '2-digit',
  month: '2-digit',
  day: '2-digit',
})
const KST_TIME_FMT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function parseTimestamp(timestamp: string): Date | null {
  if (!timestamp) return null
  const d = new Date(timestamp)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(timestamp: string): string {
  const d = parseTimestamp(timestamp)
  if (!d) return '-'
  // ko-KR: "26. 05. 12." → 정규식으로 yy/mm/dd 추출
  const parts = KST_DATE_FMT.formatToParts(d)
  const yy = parts.find((p) => p.type === 'year')?.value.padStart(2, '0') ?? '--'
  const mm = parts.find((p) => p.type === 'month')?.value.padStart(2, '0') ?? '--'
  const dd = parts.find((p) => p.type === 'day')?.value.padStart(2, '0') ?? '--'
  return `${yy}-${mm}-${dd}`
}

function formatTime(timestamp: string): string {
  const d = parseTimestamp(timestamp)
  if (!d) return '-'
  const parts = KST_TIME_FMT.formatToParts(d)
  const hh = parts.find((p) => p.type === 'hour')?.value.padStart(2, '0') ?? '--'
  const mi = parts.find((p) => p.type === 'minute')?.value.padStart(2, '0') ?? '--'
  const ss = parts.find((p) => p.type === 'second')?.value.padStart(2, '0') ?? '--'
  return `${hh}:${mi}:${ss}`
}

const STRATEGY_NAMES: Record<string, string> = {
  momentum: '모멘텀',
  volatility_breakout: '변동성돌파',
  long_tail_volatility: '롱테일 변동성',
  donchian_swing: '20일 신고가 스윙',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: '변동성 수축 돌파',
}

const columns = [
  columnHelper.accessor('timestamp', {
    id: 'date',
    header: '주문일',
    cell: (info) => formatDate(String(info.getValue() ?? '')),
  }),
  columnHelper.accessor('timestamp', {
    id: 'time',
    header: '주문시각',
    cell: (info) => formatTime(String(info.getValue() ?? '')),
  }),
  columnHelper.accessor('order_no', {
    header: '주문번호',
    cell: (info) => info.getValue() || '-',
  }),
  columnHelper.accessor('ticker', {
    header: '종목코드',
    cell: (info) => info.getValue() ?? '-',
  }),
  columnHelper.accessor('ticker_name', {
    header: '종목명',
    cell: (info) => info.getValue() || '-',
  }),
  columnHelper.accessor('trade_type', {
    header: '매수/매도',
    cell: (info) => {
      const v = String(info.getValue() ?? '')
      if (v === 'BUY') return <span className="text-red-600 font-medium">매수</span>
      if (v === 'SELL') return <span className="text-blue-600 font-medium">매도</span>
      return v
    },
  }),
  columnHelper.accessor('price', {
    header: '가격',
    cell: (info) => {
      const v = info.getValue()
      return typeof v === 'number' ? v.toLocaleString() + '원' : '-'
    },
  }),
  columnHelper.accessor('quantity', {
    header: '수량',
    cell: (info) => {
      const v = info.getValue()
      return typeof v === 'number' ? v.toLocaleString() + '주' : '-'
    },
  }),
  columnHelper.accessor('profit_loss', {
    header: '매매손익',
    cell: (info) => {
      const v = info.getValue()
      if (typeof v !== 'number' || v === 0) return '-'
      const cls = v > 0 ? 'text-red-600' : 'text-blue-600'
      const sign = v > 0 ? '+' : ''
      return <span className={cls}>{sign}{v.toLocaleString()}원</span>
    },
  }),
  columnHelper.accessor('status', {
    header: '상태',
    cell: (info) => {
      const v = String(info.getValue() ?? '')
      const map: Record<string, { label: string; cls: string }> = {
        COMPLETED: { label: '체결', cls: 'bg-green-100 text-green-700' },
        PENDING: { label: '대기', cls: 'bg-yellow-100 text-yellow-700' },
        PARTIAL: { label: '부분체결', cls: 'bg-orange-100 text-orange-700' },
        CANCELLED: { label: '취소', cls: 'bg-gray-100 text-gray-500' },
      }
      const m = map[v] ?? { label: v, cls: 'bg-gray-100 text-gray-500' }
      return <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${m.cls}`}>{m.label}</span>
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

export default function TradeHistoryGrid() {
  const [page, setPage] = useState(1)
  const size = 20

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tradeHistory', page],
    queryFn: () => getTradeHistory({ page, size }),
  })

  const trades = data?.trades ?? []

  const table = useReactTable({
    data: trades,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (isLoading) return <div className="p-6 text-gray-500">거래 내역 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">거래 내역을 불러올 수 없습니다.</div>

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
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
            {trades.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400">
                  거래 내역이 없습니다.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b hover:bg-gray-50">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2.5 text-gray-700 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
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
