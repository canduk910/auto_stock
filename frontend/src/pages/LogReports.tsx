import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listLogReports, runLogReport } from '../api/log_reports'
import type {
  Finding,
  FindingCategory,
  LogReportItem,
  Severity,
} from '../types/log_reports'

const SEVERITY_LABEL: Record<Severity, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
}

const SEVERITY_BADGE: Record<Severity, string> = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
}

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 }

const CATEGORY_LABEL: Record<FindingCategory, string> = {
  trading: '매매',
  order: '주문',
  websocket: 'WebSocket',
  scan: '스캔',
  balance: '잔고',
  settlement: '정산',
  data_quality: '데이터 품질',
  infra: '인프라',
  etc: '기타',
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('ko-KR', { hour12: false })
  } catch {
    return iso
  }
}

function formatNumber(n: number | undefined | null): string {
  if (n === undefined || n === null || !Number.isFinite(n)) return '-'
  return n.toLocaleString()
}

function formatPnL(n: number | undefined | null): string {
  if (n === undefined || n === null || !Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toLocaleString()}원`
}

function pnlColor(n: number | undefined | null): string {
  if (!n || !Number.isFinite(n)) return '#333333'
  if (n > 0) return '#FF3333'
  if (n < 0) return '#3366FF'
  return '#333333'
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <div className="bg-white rounded-lg shadow border border-gray-100 p-4">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span
          className={`px-2 py-0.5 text-xs font-medium border rounded ${SEVERITY_BADGE[finding.severity]}`}
        >
          {SEVERITY_LABEL[finding.severity]}
        </span>
        <span className="px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100 rounded">
          {CATEGORY_LABEL[finding.category] ?? finding.category}
        </span>
        <h4 className="text-sm font-semibold text-gray-900">{finding.title}</h4>
      </div>
      <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed mb-2">
        {finding.detail}
      </p>
      {finding.suggestion && (
        <div className="bg-gray-50 border-l-4 border-blue-400 px-3 py-2 rounded">
          <span className="text-xs font-medium text-gray-500 mr-1">권고</span>
          <span className="text-sm text-gray-800 whitespace-pre-line">{finding.suggestion}</span>
        </div>
      )}
    </div>
  )
}

function ReportCard({ report }: { report: LogReportItem }) {
  const [showMetrics, setShowMetrics] = useState(false)

  const sortedFindings = useMemo(() => {
    return [...(report.findings ?? [])].sort(
      (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
    )
  }, [report.findings])

  const logs = report.metrics?.logs
  const trades = report.metrics?.trades

  return (
    <div className="space-y-6">
      {/* 총평 */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">{report.target_date} 총평</h2>
          <span className="text-xs text-gray-400">
            생성 {formatDateTime(report.created_at)}
            {report.model && ` · ${report.model}`}
          </span>
        </div>
        <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed">
          {report.summary || '요약이 없습니다.'}
        </p>
      </div>

      {/* findings */}
      <div>
        <h3 className="text-base font-semibold text-gray-800 mb-3">
          개선 항목 ({sortedFindings.length}건)
        </h3>
        {sortedFindings.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-6 text-sm text-gray-500 text-center">
            특이사항이 없습니다.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {sortedFindings.map((f, idx) => (
              <FindingCard key={`${report.id}-${idx}`} finding={f} />
            ))}
          </div>
        )}
      </div>

      {/* metrics */}
      <div className="bg-white rounded-lg shadow">
        <button
          onClick={() => setShowMetrics((v) => !v)}
          className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-50"
        >
          <span className="text-sm font-medium text-gray-700">원본 메트릭</span>
          <span className="text-xs text-gray-400">{showMetrics ? '접기' : '펼치기'}</span>
        </button>
        {showMetrics && (logs || trades) && (
          <div className="border-t border-gray-100 p-4 space-y-4">
            {/* 레벨별 카운트 */}
            {logs && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 mb-2">로그 레벨별 카운트</h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {['INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((lvl) => (
                    <div
                      key={lvl}
                      className="bg-gray-50 rounded px-3 py-2 flex justify-between items-center"
                    >
                      <span className="text-xs text-gray-500">{lvl}</span>
                      <span className="text-sm font-mono font-medium text-gray-900">
                        {formatNumber(logs.level_counts?.[lvl] ?? 0)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 거래 통계 */}
            {trades && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 mb-2">거래 통계</h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div className="bg-gray-50 rounded px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">거래</span>
                    <span className="text-sm font-mono font-medium">
                      {formatNumber(trades.trades_total)}
                    </span>
                  </div>
                  <div className="bg-gray-50 rounded px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">매수</span>
                    <span className="text-sm font-mono font-medium">
                      {formatNumber(trades.buy_count)}
                    </span>
                  </div>
                  <div className="bg-gray-50 rounded px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">매도</span>
                    <span className="text-sm font-mono font-medium">
                      {formatNumber(trades.sell_count)}
                    </span>
                  </div>
                  <div className="bg-gray-50 rounded px-3 py-2 flex justify-between items-center">
                    <span className="text-xs text-gray-500">실현손익</span>
                    <span
                      className="text-sm font-mono font-medium"
                      style={{ color: pnlColor(trades.realized_pnl) }}
                    >
                      {formatPnL(trades.realized_pnl)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* 상위 WARNING/ERROR 패턴 */}
            {logs?.top_patterns && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 mb-2">상위 WARNING/ERROR 패턴</h4>
                {(['ERROR', 'WARNING', 'CRITICAL'] as const).map((lvl) => {
                  const arr = logs.top_patterns?.[lvl] ?? []
                  if (arr.length === 0) return null
                  return (
                    <div key={lvl} className="mb-3 last:mb-0">
                      <div className="text-xs font-medium text-gray-600 mb-1">{lvl}</div>
                      <ul className="text-xs text-gray-700 space-y-1">
                        {arr.slice(0, 8).map((p, i) => (
                          <li key={i} className="flex gap-2 items-baseline">
                            <span className="font-mono text-gray-400 w-10 shrink-0 text-right">
                              ×{p.count}
                            </span>
                            <span className="font-mono break-all">{p.pattern}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function LogReports() {
  const queryClient = useQueryClient()
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const { data: reports, isLoading, isError } = useQuery({
    queryKey: ['logReports'],
    queryFn: () => listLogReports(30),
  })

  // 첫 로드 시 가장 최근 날짜 자동 선택
  useEffect(() => {
    if (!selectedDate && reports && reports.length > 0) {
      setSelectedDate(reports[0].target_date)
    }
  }, [reports, selectedDate])

  const runMutation = useMutation({
    mutationFn: runLogReport,
    onSuccess: (result) => {
      if (!result.success) {
        setError(result.message || '분석 실행에 실패했습니다.')
        setInfo(null)
        return
      }
      setError(null)
      setInfo('분석 완료 — 리포트가 생성되었습니다.')
      if (result.data?.target_date) {
        setSelectedDate(result.data.target_date)
      }
      queryClient.invalidateQueries({ queryKey: ['logReports'] })
    },
    onError: (err: Error) => {
      setError(err.message || '분석 실행 중 오류가 발생했습니다.')
      setInfo(null)
    },
  })

  const selectedReport = useMemo(() => {
    if (!reports || !selectedDate) return null
    return reports.find((r) => r.target_date === selectedDate) ?? null
  }, [reports, selectedDate])

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">일일 로그 분석 리포트</h1>
        <div className="p-6 text-gray-500">리포트를 불러오는 중...</div>
      </div>
    )
  }

  if (isError) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">일일 로그 분석 리포트</h1>
        <div className="p-6 text-red-500">리포트를 불러올 수 없습니다.</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">일일 로그 분석 리포트</h1>
        <button
          onClick={() => {
            setError(null)
            setInfo(null)
            runMutation.mutate()
          }}
          disabled={runMutation.isPending}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {runMutation.isPending ? '분석 중...' : '지금 분석 실행'}
        </button>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <p className="text-sm text-blue-800">
          매일 정산(16:10) 직후 OpenAI가 당일 시스템 로그와 거래 내역을 분석해 운영 개선 리포트를 자동 생성합니다.
          {' '}
          오늘 리포트가 아직 없다면 우상단 버튼으로 즉시 실행할 수 있습니다(영업일당 1건).
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 mb-4 text-sm text-red-700">
          {error}
        </div>
      )}
      {info && (
        <div className="bg-green-50 border border-green-200 rounded p-3 mb-4 text-sm text-green-700">
          {info}
        </div>
      )}

      {(reports?.length ?? 0) === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          저장된 리포트가 없습니다.
          <br />
          <span className="text-sm">매일 정산(16:10) 후 자동 생성되거나 위 버튼으로 즉시 실행 가능합니다.</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-6">
          {/* 좌측: 날짜 리스트 */}
          <aside className="bg-white rounded-lg shadow p-2 h-fit">
            <ul className="space-y-1">
              {reports?.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => setSelectedDate(r.target_date)}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm ${
                      r.target_date === selectedDate
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <div>{r.target_date}</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      개선 {(r.findings ?? []).length}건
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {/* 우측: 상세 */}
          <div>
            {selectedReport ? (
              <ReportCard report={selectedReport} />
            ) : (
              <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                좌측에서 영업일을 선택하세요.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
