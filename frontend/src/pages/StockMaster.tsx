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
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

import {
  fetchStats,
  fetchList,
  fetchScanPoolSummary,
  fetchDetail,
  fetchHistory,
  refreshUniverseNow,
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
// 필드 한글 레이블 (사이클 89 hotfix)
// ────────────────────────────────────────────────────────────────────────
const FIELD_LABELS: Record<string, string> = {
  ticker: '종목코드',
  name: '종목명',
  excg_dvsn_cd: '거래소',
  bfdy_clpr: '전일종가',
  stck_prpr: '현재가',
  stck_hgpr: '고가',
  stck_lwpr: '저가',
  acml_vol: '누적거래량',
  acml_tr_pbmn: '누적거래대금',
  nxt_tradable: 'NXT 거래가능',
  krx_halted: 'KRX 거래정지',
  admin_item: '관리종목',
  refreshed_at: '갱신시각',
}

// ────────────────────────────────────────────────────────────────────────
// 거래소 코드 → 한글 변환 (사이클 89 hotfix)
// ────────────────────────────────────────────────────────────────────────
function formatExchange(code: string | null | undefined): string {
  if (!code) return '—'
  const map: Record<string, string> = {
    '01': 'KOSPI', '02': 'KOSDAQ', '03': 'KOSDAQ', '04': 'ETF',
    '05': 'ELW', '06': 'ETN', 'KSP': 'KOSPI', 'KDQ': 'KOSDAQ',
  }
  return map[code] ?? code
}

// ────────────────────────────────────────────────────────────────────────
// 숫자 포맷 헬퍼 (사이클 89 hotfix)
// ────────────────────────────────────────────────────────────────────────
function formatPrice(v: unknown): string {
  const n = Number(v)
  if (isNaN(n)) return String(v ?? '—')
  return n.toLocaleString('ko-KR') + '원'
}

function formatVolume(v: unknown): string {
  const n = Number(v)
  if (isNaN(n)) return String(v ?? '—')
  return n.toLocaleString('ko-KR') + '주'
}

function formatAmount(v: unknown): string {
  const n = Number(v)
  if (isNaN(n)) return String(v ?? '—')
  if (n >= 1_000_000_000_000) return (n / 1_000_000_000_000).toFixed(1) + '조원'
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(0) + '억원'
  return n.toLocaleString('ko-KR') + '원'
}

// ────────────────────────────────────────────────────────────────────────
// 카테고리 아이콘 (사이클 89 hotfix)
// ────────────────────────────────────────────────────────────────────────
const CATEGORY_ICONS: Record<string, string> = {
  '기본': '📋',
  '가격': '💰',
  '거래': '📊',
  '플래그': '🚩',
  '메타': '⏱️',
}

// ────────────────────────────────────────────────────────────────────────
// 필드 값 포맷터 (사이클 89 hotfix)
// ────────────────────────────────────────────────────────────────────────
function formatFieldValue(key: string, value: unknown): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>

  // boolean 플래그 — 아이콘 + 색상
  if (typeof value === 'boolean') {
    const flagTrueKeys = ['nxt_tradable']
    const flagDangerKeys = ['krx_halted', 'admin_item']
    if (flagTrueKeys.includes(key)) {
      return value
        ? <span className="text-emerald-600 font-medium">✓ 가능</span>
        : <span className="text-gray-400">✗ 불가</span>
    }
    if (flagDangerKeys.includes(key)) {
      return value
        ? <span className="text-red-600 font-medium">✓ 해당</span>
        : <span className="text-gray-400">✗ 해당없음</span>
    }
    return value ? '예' : '아니오'
  }

  // 가격 필드
  if (['bfdy_clpr', 'stck_prpr', 'stck_hgpr', 'stck_lwpr'].includes(key)) {
    return <span className="font-mono text-right">{formatPrice(value)}</span>
  }

  // 거래량
  if (key === 'acml_vol') {
    return <span className="font-mono">{formatVolume(value)}</span>
  }

  // 거래대금
  if (key === 'acml_tr_pbmn') {
    return <span className="font-mono">{formatAmount(value)}</span>
  }

  // 종목코드
  if (key === 'ticker') {
    return <span className="font-mono text-blue-700 font-medium">{String(value)}</span>
  }

  // 거래소 코드
  if (key === 'excg_dvsn_cd') {
    return <span>{formatExchange(String(value))}</span>
  }

  // 시각 필드
  if (key === 'refreshed_at') {
    return <span className="text-xs">{formatKst(String(value))}</span>
  }

  return <span>{String(value)}</span>
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
      result.push([k, (detail as unknown as Record<string, unknown>)[k]])
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
            <div className="space-y-5">
              {Object.keys(CATEGORY_KEYS).map((category) => {
                const items = getCategoryItems(data, category)
                return (
                  <div key={category}>
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                      <span>{CATEGORY_ICONS[category]}</span>
                      <span>{category}</span>
                    </h3>
                    <div className="grid grid-cols-2 gap-2">
                      {items.map(([key, value]) => {
                        const isHighlight = HIGHLIGHT_KEYS.includes(key)
                        const isPriceKey = ['bfdy_clpr', 'stck_prpr', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'acml_tr_pbmn'].includes(key)
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
                            <div className="text-xs text-gray-500 mb-0.5">
                              {FIELD_LABELS[key] ?? key}
                            </div>
                            <div className={`text-gray-900 ${isPriceKey ? 'text-right' : ''}`}>
                              {formatFieldValue(key, value)}
                            </div>
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
  // 사이클 90 — 토스트 상태 (react-hot-toast 미사용 환경 호환)
  const [refreshToast, setRefreshToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const LIMIT = 100

  const queryClient = useQueryClient()

  // 사이클 90 Q26=A — "지금 새로고침" useMutation.
  // Q25=A: 409 Conflict 분기 처리. 네트워크 오류/서버 오류 시 즉시 onError.
  // 사이클 75 G-RT 영속: useQuery retry:1 패턴 — useMutation 은 즉시 실패 (재시도 없음).
  // 이유: refresh-universe 는 장시간 작업(~25초) — 재시도 시 중복 KIS 호출 위험.
  const refreshMutation = useMutation({
    mutationFn: refreshUniverseNow,
    retry: false,
    onSuccess: (data) => {
      setRefreshToast({
        type: 'success',
        message: `universe ${data.universe} ticker 즉시 적재 완료 (${data.elapsed_ms}ms)`,
      })
      queryClient.invalidateQueries({ queryKey: ['stock-master-stats'] })
      queryClient.invalidateQueries({ queryKey: ['stock-master-list'] })
      setTimeout(() => setRefreshToast(null), 4000)
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setRefreshToast({
          type: 'error',
          message: 'universe refresh 진행 중 — 잠시 후 재시도',
        })
      } else {
        setRefreshToast({
          type: 'error',
          message: '적재 실패 — 잠시 후 재시도',
        })
      }
      setTimeout(() => setRefreshToast(null), 4000)
    },
  })

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

  // Array.isArray 가드 — e2e mock 환경에서 api-mocks wildcard 라우트가
  // /list* 보다 우선 매칭되어 단일 객체 응답이 내려올 수 있음 (LIFO 경계).
  // 운영 환경에서 배열 응답이 보장되므로 행위 변경 0.
  const listItems: StockMasterListItem[] = Array.isArray(listQuery.data) ? listQuery.data : []
  const historyItems: StockMasterHistoryItem[] = Array.isArray(historyQuery.data) ? historyQuery.data : []

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
        {/* 사이클 90 Q26=A — stats 카드 상단 우측 "지금 새로고침" 버튼 */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-700">전체 현황</h2>
          <button
            data-testid="stock-master-refresh-universe-button"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shrink-0"
          >
            {refreshMutation.isPending ? '적재 중...' : '지금 새로고침'}
          </button>
        </div>

        {/* 사이클 90 토스트 영역 */}
        {refreshToast && (
          <div
            data-testid="stock-master-refresh-universe-toast"
            className={`mb-4 px-4 py-2 rounded text-sm font-medium ${
              refreshToast.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {refreshToast.message}
          </div>
        )}

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
                <p className="text-xs text-gray-500">전일종가 정상 적재</p>
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
                <p className="text-xs text-gray-500">오늘 자동 갱신 횟수</p>
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
                      {item.name}
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
