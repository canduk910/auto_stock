import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { getTradeHistory } from '../api/history'
import type { TradeRecord } from '../types/trading'

const columnHelper = createColumnHelper<TradeRecord>()

export default function TradeHistoryGrid() {
  const [page, setPage] = useState(1)
  const size = 20

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tradeHistory', page],
    queryFn: () => getTradeHistory({ page, size }),
  })

  const trades = data?.trades ?? []

  const dynamicColumns = trades.length > 0
    ? Object.keys(trades[0]).map((key) =>
        columnHelper.accessor(key, {
          header: key,
          cell: (info) => {
            const val = info.getValue()
            if (val == null) return '-'
            if (typeof val === 'number') return val.toLocaleString('ko-KR')
            return String(val)
          },
        }),
      )
    : []

  const table = useReactTable({
    data: trades,
    columns: dynamicColumns,
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
                    className="px-4 py-3 text-left font-medium text-gray-600"
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
                <td colSpan={dynamicColumns.length || 1} className="px-4 py-8 text-center text-gray-400">
                  거래 내역이 없습니다.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b hover:bg-gray-50">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-gray-700">
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
