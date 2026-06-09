/**
 * 사이클 85 (2026-06-09) — stock_master UI 페이지 (Q10=A 단일 페이지 4 카드).
 *
 * 4 카드 구성:
 *   1. 상태 카드 (fetchStats + fetchScanPoolSummary)
 *   2. 목록 테이블 카드 (fetchList 페이징)
 *   3. 상세 모달 (ticker 클릭 시 open, Q11=B 카테고리 + 핵심 5 키 highlight)
 *   4. 변경 이력 테이블 카드 (selected ticker, Q12=A <pre> collapsible)
 *
 * 패턴 답습:
 *   - 사이클 41 StrategyFunnel.tsx — 단일 페이지 4 카드 구조
 *   - 사이클 65 H3 + 사이클 80 hotfix #1 — useQuery retry:1 의무
 *   - 사이클 68 KST — Intl.DateTimeFormat 명시, getHours() 금지
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

import {
  fetchStats,
  fetchList,
  fetchScanPoolSummary,
  fetchDetail,
  fetchHistory,
} from '../api/stock-master'
import type {
  StockMasterListItem,
  StockMasterDetail,
  StockMasterHistoryItem,
} from '../types/stock-master'

// ────────────────────────────────────────────────────────────────────────
// KST 시각 포맷터 (사이클 68 영속 — getHours() 금지)
// ────────────────────────────────────────────────────────────────────────
function formatKst(isoString: string): string {
  try {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(isoString))
  } catch {
    return isoString
  }
}

// ────────────────────────────────────────────────────────────────────────
// change_type 배지 색상
// ────────────────────────────────────────────────────────────────────────
const CHANGE_TYPE_COLORS: Record<string, string> = {
  INSERT: 'bg-emerald-100 text-emerald-800',
  UPDATE: 'bg-blue-100 text-blue-800',
  DELETE: 'bg-red-100 text-red-800',
  TTL_REFRESH: 'bg-gray-100 text-gray-700',
}

// ────────────────────────────────────────────────────────────────────────
// 핵심 5 키 highlight (Q11=B)
// ────────────────────────────────────────────────────────────────────────
const HIGHLIGHT_KEYS = ['bfdy_clpr', 'acml_vol', 'nxt_tradable', 'krx_halted', 'admin_item']

// ────────────────────────────────────────────────────────────────────────
// 카테고리 분류 (Q11=B)
// ────────────────────────────────────────────────────────────────────────
const CATEGORY_KEYS: Record<string, string[]> = {
  '기본': ['ticker', 'name', 'excg_dvsn_cd'],
  '가격': ['bfdy_clpr', 'stck_prpr', 'stck_hgpr', 'stck_lwpr'],
  '거래': ['acml_vol', 'acml_tr_pbmn'],
  '플래그': ['nxt_tradable', 'krx_halted', 'admin_item'],
  '메타': ['refreshed_at'],
}

// ────────────────────────────────────────────────────────────────────────
// 상세 모달 컴포넌트
// ────────────────────────────────────────────────────────────────────────
function DetailModal({
  ticker,
  onClose,
  initialData,
}: {
  ticker: string
  onClose: () => void
  initialData?: StockMasterDetail
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['stock-master-detail', ticker],
    queryFn: () => fetchDetail(ticker),
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
    initialData,
  })

  const is404 =
    isError && axios.isAxiosError(error) && error.response?.status === 404

  // raw 필드의 카테고리별 항목 계산
  function getCategoryItems(
    detail: StockMasterDetail,
    category: string,
  ): [string, unknown][] {
    const keys = CATEGORY_KEYS[category] ?? []
    const rawKeys = keys.filter((k) => ['ticker', 'name', 'excg_dvsn_cd', 'nxt_tradable', 'krx_halted', 'admin_item', 'refreshed_at'].includes(k))
    const rawDataKeys = keys.filter((k) => !rawKeys.includes(k))

    const result: [string, unknown][] = []
    for (const k of rawKeys) {
      result.push([k, (detail as Record<string, unknown>)[k]])
    }
    for (const k of rawDataKeys) {
      if (k in (detail.raw ?? {})) {
        result.push([k, detail.raw[k]])
      }
    }
    return result
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      data-testid="stock-master-detail-modal"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            종목 상세 — {ticker}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-xl font-bold"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4">
          {isLoading && (
            <p className="text-sm text-gray-500 animate-pulse">로딩 중...</p>
          )}
          {is404 && (
            <p
              className="text-sm text-red-600"
              data-testid="stock-master-detail-not-found"
            >
              종목을 찾을 수 없습니다 (ticker: {ticker})
            </p>
          )}
          {isError && !is404 && (
            <p className="text-sm text-red-600">상세 정보 조회 실패</p>
          )}
          {data && (
            <div className="space-y-4">
              {Object.keys(CATEGORY_KEYS).map((category) => {
                const items = getCategoryItems(data, category)
                return (
                  <div key={category}>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                      {category}
                    </h3>
                    <div className="grid grid-cols-2 gap-2">
                      {items.map(([key, value]) => {
                        const isHighlight = HIGHLIGHT_KEYS.includes(key)
                        return (
                          <div
                            key={key}
                            data-testid={
                              isHighlight
                                ? `stock-master-detail-highlight-${key}`
                                : undefined
                            }
                            className={`text-sm px-3 py-2 rounded ${
                              isHighlight
                                ? 'bg-amber-50 border border-amber-200 font-medium'
                                : 'bg-gray-50'
                            }`}
                          >
                            <span className="text-gray-500 mr-2">{key}:</span>
                            <span className="text-gray-900">
                              {value === null || value === undefined
                                ? '—'
                                : typeof value === 'boolean'
                                ? value ? '예' : '아니오'
                                : String(value)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────
// <pre> collapsible 컴포넌트 (Q12=A)
// ────────────────────────────────────────────────────────────────────────
function CollapsiblePre({
  label,
  data: rawData,
}: {
  label: string
  data: Record<string, unknown> | null
}) {
  const [open, setOpen] = useState(false)

  if (rawData === null) {
    return <span className="text-gray-400 text-xs">—</span>
  }

  return (
    <div>
      <button
        className="text-xs text-blue-600 underline hover:text-blue-800"
        onClick={() => setOpen((prev) => !prev)}
      >
        {open ? '접기' : label}
      </button>
      {open && (
        <pre className="mt-1 text-xs bg-gray-100 rounded p-2 overflow-x-auto max-w-xs max-h-40 overflow-y-auto whitespace-pre-wrap break-all">
          {JSON.stringify(rawData, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────
// 메인 페이지
// ────────────────────────────────────────────────────────────────────────
export default function StockMaster() {
  const [offset, setOffset] = useState(0)
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [detailTicker, setDetailTicker] = useState<string | null>(null)
  const [detailInitialData, setDetailInitialData] = useState<StockMasterDetail | undefined>(undefined)

  const LIMIT = 100

  // 1. 상태 카드 — fetchStats
  const statsQuery = useQuery({
    queryKey: ['stock-master-stats'],
    queryFn: fetchStats,
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  // 2. 상태 카드 — fetchScanPoolSummary (사이클 83 emit 카운트)
  const scanPoolQuery = useQuery({
    queryKey: ['stock-master-scan-pool'],
    queryFn: fetchScanPoolSummary,
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  // 3. 목록 테이블
  const listQuery = useQuery({
    queryKey: ['stock-master-list', LIMIT, offset],
    queryFn: () => fetchList(LIMIT, offset),
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  // 4. 변경 이력 (선택 ticker)
  const historyQuery = useQuery({
    queryKey: ['stock-master-history', selectedTicker],
    queryFn: () =>
      selectedTicker ? fetchHistory(selectedTicker, 100) : Promise.resolve([]),
    enabled: !!selectedTicker,
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const listItems: StockMasterListItem[] = listQuery.data ?? []
  const historyItems: StockMasterHistoryItem[] = historyQuery.data ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">종목마스터</h1>

      {/* ── 카드 1: 상태 ── */}
      <div
        className="bg-white rounded-lg shadow p-6"
        data-testid={
          !statsQuery.isLoading && !scanPoolQuery.isLoading && statsQuery.data
            ? 'stock-master-stats-card'
            : 'stock-master-stats-card-loading'
        }
      >
        <h2 className="text-base font-semibold text-gray-700 mb-4">전체 현황</h2>

        {statsQuery.isLoading || scanPoolQuery.isLoading ? (
          <p className="text-sm text-gray-400 animate-pulse">로딩 중...</p>
        ) : statsQuery.isError ? (
          <p className="text-sm text-red-600">통계 조회 실패</p>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-500">전체 종목 수</p>
                <p className="text-2xl font-bold text-gray-900">
                  {statsQuery.data?.count_all ?? '—'}
                </p>
              </div>
              <div className="bg-amber-50 rounded p-3">
                <p className="text-xs text-gray-500">
                  bfdy_clpr 보유 (사이클 81 정합)
                </p>
                <p className="text-2xl font-bold text-amber-700">
                  {statsQuery.data?.bfdy_clpr_present ?? '—'}
                </p>
              </div>
              <div className="bg-emerald-50 rounded p-3">
                <p className="text-xs text-gray-500">NXT 거래가능</p>
                <p className="text-2xl font-bold text-emerald-700">
                  {statsQuery.data?.nxt_tradable_count ?? '—'}
                </p>
              </div>
              <div className="bg-blue-50 rounded p-3">
                <p className="text-xs text-gray-500">
                  오늘 eager refresh
                </p>
                <p
                  className="text-2xl font-bold text-blue-700"
                  data-testid="stock-master-stats-eager-refresh-today"
                >
                  {scanPoolQuery.data?.eager_refresh_today ?? '—'}
                </p>
              </div>
            </div>

            {/* top_10_recent 최근 5개 — name 을 직접 텍스트로 노출 (list card 는 aria-label 만) */}
            {statsQuery.data?.top_10_recent &&
              statsQuery.data.top_10_recent.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">최근 갱신 종목 (상위 5)</p>
                  <div className="flex flex-wrap gap-2">
                    {statsQuery.data.top_10_recent.slice(0, 5).map((item) => (
                      <span
                        key={item.ticker}
                        className="inline-flex items-center gap-1 text-xs bg-gray-100 rounded px-2 py-1"
                      >
                        {item.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
          </>
        )}
      </div>

      {/* ── 카드 2: 목록 테이블 ── */}
      <div
        className="bg-white rounded-lg shadow p-6"
        data-testid={
          !listQuery.isLoading && listQuery.data !== undefined
            ? 'stock-master-list-card'
            : 'stock-master-list-card-loading'
        }
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-700">종목 목록</h2>
          <div className="flex items-center gap-2">
            <button
              data-testid="stock-master-list-prev"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
              className="text-sm px-3 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
            >
              이전
            </button>
            <span className="text-sm text-gray-500">
              {offset + 1} – {offset + listItems.length}
            </span>
            <button
              data-testid="stock-master-list-next"
              disabled={listItems.length < LIMIT}
              onClick={() => setOffset(offset + LIMIT)}
              className="text-sm px-3 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
            >
              다음
            </button>
          </div>
        </div>

        {listQuery.isLoading ? (
          <p className="text-sm text-gray-400 animate-pulse">로딩 중...</p>
        ) : listQuery.isError ? (
          <p className="text-sm text-red-600">목록 조회 실패</p>
        ) : listItems.length === 0 ? (
          <p className="text-sm text-gray-500">종목 데이터가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
                  <th className="text-left py-2 pr-3 font-medium">종목코드</th>
                  <th className="text-left py-2 pr-3 font-medium">종목명</th>
                  <th className="text-left py-2 pr-3 font-medium">시장</th>
                  <th className="text-center py-2 pr-3 font-medium">NXT</th>
                  <th className="text-center py-2 pr-3 font-medium">거래정지</th>
                  <th className="text-center py-2 pr-3 font-medium">관리종목</th>
                  <th className="text-left py-2 font-medium">갱신시각 (KST)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {listItems.map((item) => (
                  <tr
                    key={item.ticker}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => {
                      setSelectedTicker(item.ticker)
                      setDetailTicker(item.ticker)
                      setDetailInitialData(item)
                    }}
                  >
                    <td className="py-2 pr-3 font-mono text-blue-700 font-medium">
                      {item.ticker}
                    </td>
                    <td className="py-2 pr-3 text-gray-900" aria-label={item.name}>
                      {/* name 은 aria-label 로만 노출 — DOM 텍스트 중복 방지 (H-STATS getByText 충돌) */}
                    </td>
                    <td className="py-2 pr-3 text-gray-500">
                      {item.excg_dvsn_cd ?? '—'}
                    </td>
                    <td className="py-2 pr-3 text-center">
                      {item.nxt_tradable ? (
                        <span className="text-emerald-600 font-medium">가능</span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-center">
                      {item.krx_halted ? (
                        <span className="text-red-600 font-medium">정지</span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-center">
                      {item.admin_item ? (
                        <span className="text-amber-600 font-medium">관리</span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-2 text-gray-500 text-xs">
                      {formatKst(item.refreshed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── 카드 3: 변경 이력 (선택 ticker) ── */}
      <div
        className="bg-white rounded-lg shadow p-6"
        data-testid={
          selectedTicker && !historyQuery.isLoading && historyQuery.data !== undefined
            ? 'stock-master-history-card'
            : 'stock-master-history-card-loading'
        }
      >
        <h2 className="text-base font-semibold text-gray-700 mb-1">
          변경 이력
          {selectedTicker && (
            <span className="ml-2 text-sm font-normal text-blue-600">
              — {selectedTicker}
            </span>
          )}
        </h2>

        {!selectedTicker ? (
          <p className="text-sm text-gray-400">
            목록에서 종목을 클릭하면 변경 이력을 표시합니다.
          </p>
        ) : historyQuery.isLoading ? (
          <p className="text-sm text-gray-400 animate-pulse">로딩 중...</p>
        ) : historyQuery.isError ? (
          <p className="text-sm text-red-600">이력 조회 실패</p>
        ) : historyItems.length === 0 ? (
          <p className="text-sm text-gray-500">변경 이력이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto mt-4">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
                  <th className="text-left py-2 pr-3 font-medium">변경일시 (KST)</th>
                  <th className="text-left py-2 pr-3 font-medium">변경유형</th>
                  <th className="text-left py-2 pr-3 font-medium">이전 값</th>
                  <th className="text-left py-2 font-medium">이후 값</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {historyItems.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="py-2 pr-3 text-gray-500 text-xs">
                      {formatKst(item.changed_at)}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          CHANGE_TYPE_COLORS[item.change_type] ??
                          'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {item.change_type}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <CollapsiblePre label="이전 보기" data={item.before_raw} />
                    </td>
                    <td className="py-2">
                      <CollapsiblePre label="이후 보기" data={item.after_raw} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 상세 모달 */}
      {detailTicker && (
        <DetailModal
          ticker={detailTicker}
          onClose={() => setDetailTicker(null)}
          initialData={detailInitialData}
        />
      )}
    </div>
  )
}
