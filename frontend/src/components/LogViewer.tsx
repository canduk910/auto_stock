import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

interface LogEntry {
  id: number
  timestamp: string
  log_level: string
  message: string
}

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-green-600',
  WARNING: 'text-yellow-600',
  ERROR: 'text-red-500 font-medium',
  CRITICAL: 'text-red-700 font-bold',
}

async function fetchLogs(limit: number, level: string | null): Promise<LogEntry[]> {
  const params: Record<string, string | number> = { limit }
  if (level) params.level = level
  const { data } = await apiClient.get('/logs', { params })
  return data.data ?? []
}

export default function LogViewer() {
  const [filter, setFilter] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['systemLogs', filter],
    queryFn: () => fetchLogs(50, filter),
    refetchInterval: 3000,
  })

  const formatTime = (ts: string) => {
    const d = new Date(ts)
    return d.toLocaleTimeString('ko-KR', { hour12: false })
  }

  return (
    <div className="bg-gray-900 rounded-lg shadow">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-medium text-gray-200"
        >
          <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>
          시스템 로그
          <span className="text-xs text-gray-500">({logs.length}건)</span>
        </button>
        <div className="flex items-center gap-1">
          {[null, 'INFO', 'WARNING', 'ERROR'].map((lvl) => (
            <button
              key={lvl ?? 'ALL'}
              onClick={() => setFilter(lvl)}
              className={`px-2 py-0.5 text-xs rounded ${
                filter === lvl
                  ? 'bg-gray-600 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {lvl ?? '전체'}
            </button>
          ))}
        </div>
      </div>

      {/* 로그 본문 */}
      {expanded && (
        <div className="h-64 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
          {isLoading ? (
            <p className="text-gray-500">로딩 중...</p>
          ) : logs.length === 0 ? (
            <p className="text-gray-500">로그가 없습니다.</p>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="flex gap-2 leading-5">
                <span className="text-gray-500 shrink-0">{formatTime(log.timestamp)}</span>
                <span className={`shrink-0 w-16 ${LEVEL_STYLE[log.log_level] ?? 'text-gray-300'}`}>
                  {log.log_level}
                </span>
                <span className="text-gray-300 break-all">{log.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
