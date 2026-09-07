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
import React, { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import axios from 'axios'

import {
  fetchStats,
  fetchList,
  fetchScanPoolSummary,
  fetchDetail,
  fetchHistory,
  fetchDaily,
  refreshUniverseNow,
  refreshBasicsNow,
  refreshDailyNow,
  refreshMasterNow,  // 사이클 129 — KIS 종목 마스터 파일 적재 수동 trigger
} from '../api/stock-master'
import type {
  StockMasterListItem,
  StockMasterDetail,
  StockMasterHistoryItem,
  StockMasterDailyRow,
} from '../types/stock-master'
import { RefreshProgressBanner } from '../components/RefreshProgressBanner'

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
// 사이클 169 — migration 036 (사이클 150) trigger 가 'TTL_REFRESH' 미발화
// (`OLD.raw IS DISTINCT FROM NEW.raw` 조건) → INSERT/UPDATE/DELETE 3종만.
const CHANGE_TYPE_COLORS: Record<string, string> = {
  INSERT: 'bg-emerald-100 text-emerald-800',
  UPDATE: 'bg-blue-100 text-blue-800',
  DELETE: 'bg-red-100 text-red-800',
}

// ────────────────────────────────────────────────────────────────────────
// highlight 키 (Q11=B 기존 5 + 사이클 124 Q2=A 신규 6 = 11 키)
// ────────────────────────────────────────────────────────────────────────
const HIGHLIGHT_KEYS = [
  // 기존 5
  'bfdy_clpr', 'acml_vol', 'nxt_tradable', 'krx_halted', 'admin_item',
  // 사이클 124 Q2=A 신규 6
  'hts_avls', 'acml_tr_pbmn', 'lstn_stcn', 'prdy_vrss',
  // 사이클 129 — master_raw 1단계 차단 7건 (Q4=A 마스터 우선 영구 영속)
  'master_raw.trht_yn', 'master_raw.sltr_yn', 'master_raw.mang_issu_yn',
  'master_raw.ssts_hot_yn', 'master_raw.stange_runup_yn',
  'master_raw.mrkt_alrm_cls_code', 'master_raw.invt_alrm_yn',
  // 사이클 129 — master_raw 시총 (Q12 × 100 영역)
  'master_raw.prdy_avls_scal',
]

// ────────────────────────────────────────────────────────────────────────
// 카테고리 분류 (Q11=B 기존 5 + 사이클 124 Q2=A "시총/주식수" 신규 카테고리)
// ────────────────────────────────────────────────────────────────────────
const CATEGORY_KEYS: Record<string, string[]> = {
  '기본': ['ticker', 'name', 'excg_dvsn_cd'],
  '가격': ['bfdy_clpr', 'prdy_vrss', 'stck_prpr', 'stck_hgpr', 'stck_lwpr'],
  '시총/주식수': ['hts_avls', 'lstn_stcn'],
  '거래': ['acml_vol', 'acml_tr_pbmn'],
  '플래그': ['nxt_tradable', 'krx_halted', 'admin_item'],
  // 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 3 카테고리
  '마스터 진입 차단': [
    'master_raw.trht_yn', 'master_raw.sltr_yn', 'master_raw.mang_issu_yn',
    'master_raw.ssts_hot_yn', 'master_raw.stange_runup_yn',
    'master_raw.mrkt_alrm_cls_code', 'master_raw.invt_alrm_yn',
    'master_raw.short_over_cls_code', 'master_raw.mrkt_alrm_risk_adnt_yn',
    'master_raw.insn_pbnt_yn', 'master_raw.byps_lstn_yn', 'master_raw.flng_cls_code',
  ],
  '마스터 펀더멘털': [
    'master_raw.prdy_avls_scal', 'master_raw.lstn_stcn',
    'master_raw.roe', 'master_raw.sale_account', 'master_raw.bsop_prfi',
    'master_raw.op_prfi', 'master_raw.thtr_ntin', 'master_raw.cpfn',
    'master_raw.marg_rate', 'master_raw.crdt_able', 'master_raw.stck_fcam',
    'master_raw.po_prc', 'master_raw.stck_lstn_date', 'master_raw.prst_cls_code',
  ],
  '마스터 지수편입': [
    'master_raw.kospi200_apnt_cls_code', 'master_raw.kospi100_issu_yn',
    'master_raw.kospi50_issu_yn', 'master_raw.krx300_issu_yn',
    'master_raw.ksq150_nmix_yn', 'master_raw.kospi_issu_yn',
    'master_raw.krx_issu_yn', 'master_raw.vntr_issu_yn',
  ],
  '메타': ['refreshed_at', 'master_raw_updated_at'],
}

// ────────────────────────────────────────────────────────────────────────
// 필드 한글 레이블 (사이클 89 hotfix + 사이클 124 Q2=A 6 신규)
// ────────────────────────────────────────────────────────────────────────
const FIELD_LABELS: Record<string, string> = {
  ticker: '종목코드',
  name: '종목명',
  excg_dvsn_cd: '거래소',
  bfdy_clpr: '전일 종가',
  prdy_vrss: '전일 대비',
  stck_prpr: '현재가',
  stck_hgpr: '고가',
  stck_lwpr: '저가',
  acml_vol: '누적 거래량',
  acml_tr_pbmn: '누적 거래대금 (원)',
  nxt_tradable: 'NXT 거래가능',
  krx_halted: 'KRX 거래정지',
  admin_item: '관리종목',
  refreshed_at: '갱신시각',
  // 사이클 124 Q2=A 신규 6
  hts_avls: '시가총액 (억원)',
  lstn_stcn: '상장 주식수',
  // 사이클 129 — master_raw 영역 한글 라벨 (KIS 종목 마스터 파일 정본 영구 영속)
  // Q4=A 마스터 우선 영역 + Q12 시총 환산 × 100 영역
  master_raw_updated_at: '마스터 갱신시각',
  // 마스터 진입 차단 (1단계 7건 HIGH)
  'master_raw.trht_yn': '거래정지',
  'master_raw.sltr_yn': '정리매매',
  'master_raw.mang_issu_yn': '관리종목',
  'master_raw.ssts_hot_yn': '공매도과열',
  'master_raw.stange_runup_yn': '이상급등',
  'master_raw.mrkt_alrm_cls_code': '시장경고 (00:없음 01:주의 02:경고 03:위험)',
  'master_raw.invt_alrm_yn': '투자주의환기 (코스닥)',
  'master_raw.short_over_cls_code': '단기과열 (0:없음 1:예고 2:지정 3:연장)',
  'master_raw.mrkt_alrm_risk_adnt_yn': '시장경고 예고',
  'master_raw.insn_pbnt_yn': '불성실공시',
  'master_raw.byps_lstn_yn': '우회상장',
  'master_raw.flng_cls_code': '락구분 (00:없음 01:권리락 02:배당락)',
  // 마스터 펀더멘털 (재무/시총/상장)
  'master_raw.prdy_avls_scal': '전일 시가총액 (억)',
  'master_raw.lstn_stcn': '상장주수 (천주)',
  'master_raw.roe': 'ROE (%)',
  'master_raw.sale_account': '매출액',
  'master_raw.bsop_prfi': '영업이익',
  'master_raw.op_prfi': '경상이익',
  'master_raw.thtr_ntin': '당기순이익',
  'master_raw.cpfn': '자본금',
  'master_raw.marg_rate': '증거금비율 (%)',
  'master_raw.crdt_able': '신용가능',
  'master_raw.stck_fcam': '액면가',
  'master_raw.po_prc': '공모가',
  'master_raw.stck_lstn_date': '상장일자',
  'master_raw.prst_cls_code': '우선주구분 (0:보통 1:구형 2:신형)',
  // 마스터 지수편입
  'master_raw.kospi200_apnt_cls_code': 'KOSPI200 섹터',
  'master_raw.kospi100_issu_yn': 'KOSPI100',
  'master_raw.kospi50_issu_yn': 'KOSPI50',
  'master_raw.krx300_issu_yn': 'KRX300',
  'master_raw.ksq150_nmix_yn': 'KOSDAQ150',
  'master_raw.kospi_issu_yn': 'KOSPI',
  'master_raw.krx_issu_yn': 'KRX 종목',
  'master_raw.vntr_issu_yn': '벤처기업 (코스닥)',
}

// ────────────────────────────────────────────────────────────────────────
// 거래소 코드 → 한글 변환 (사이클 89 hotfix + 사이클 95 KIS CTPF1002R 정본 일치)
// ────────────────────────────────────────────────────────────────────────
function formatExchange(code: string | null | undefined): string {
  if (!code) return '—'
  const map: Record<string, string> = {
    '01': 'KOSPI',  // 사이클 89 hotfix 영속 — KIS LMS 코드
    '02': 'KOSPI',  // 사이클 95 — KIS CTPF1002R 정본
    '03': 'KOSDAQ', // 사이클 95 — KIS CTPF1002R 정본
    '04': 'ETF',
    '05': 'ELW',
    '06': 'ETN',
    'STK': 'KOSPI',  // 사이클 94 backward compat
    'KSQ': 'KOSDAQ', // 사이클 94 backward compat
    'KSP': 'KOSPI',
    'KDQ': 'KOSDAQ',
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

/**
 * 사이클 126 → 사이클 166 — 시가총액 표시 (억원 단위 정정).
 * stock_master.raw.hts_avls 는 KIS FHKST01010100 inquire_price "HTS 시가총액" = 억원 단위.
 * 운영 DB 실측 (2026-06-19): 실제시총(원) / hts_avls ≈ 10^8 → 1단위 = 1억원 확정.
 * 사이클 126 시점 "백만원" 가정은 silent 결함 (100배 표시 어긋남) → 억원으로 정정.
 * 10,000억 = 1조원.
 */
function formatMarketCap(v: unknown): string {
  const n = Number(v)
  if (isNaN(n) || n === 0) return '—'
  // 억원 단위 (정정) — 10,000억 = 1조원
  if (n >= 10_000) return (n / 10_000).toFixed(1) + '조원'
  return n.toLocaleString('ko-KR') + '억원'
}

/**
 * 사이클 126 — 거래대금 원 단위 → 억원 환산.
 * stock_master.raw.acml_tr_pbmn 는 KIS FHKST01010100 응답으로 원 단위.
 */
function formatTradeAmount(v: unknown): string {
  const n = Number(v)
  if (isNaN(n) || n === 0) return '—'
  if (n >= 1_000_000_000_000) return (n / 1_000_000_000_000).toFixed(1) + '조원'
  if (n >= 100_000_000) return Math.round(n / 100_000_000).toLocaleString('ko-KR') + '억원'
  return n.toLocaleString('ko-KR') + '원'
}

/**
 * 사이클 126 — 전일대비 금액 + 부호 색상 (red/blue/gray).
 * 양수 = 빨강 (상승), 음수 = 파랑 (하락), 0 = 회색.
 */
function formatPriceChange(v: unknown): { text: string; color: string } {
  const n = Number(v)
  if (isNaN(n)) return { text: '—', color: 'text-gray-400' }
  if (n > 0) return { text: '+' + n.toLocaleString('ko-KR'), color: 'text-red-600 font-medium' }
  if (n < 0) return { text: n.toLocaleString('ko-KR'), color: 'text-blue-600 font-medium' }
  return { text: '0', color: 'text-gray-500' }
}

// ────────────────────────────────────────────────────────────────────────
// 카테고리 아이콘 (사이클 89 hotfix + 사이클 124 "시총/주식수" 신규)
// ────────────────────────────────────────────────────────────────────────
const CATEGORY_ICONS: Record<string, string> = {
  '기본': '📋',
  '가격': '💰',
  '시총/주식수': '🏦',
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

  // 시가총액 (억원 단위 — 사이클 166 정정, 10,000억 = 1조원)
  if (key === 'hts_avls') {
    const n = Number(value)
    if (isNaN(n)) return <span className="text-gray-400">—</span>
    if (n >= 10_000) return <span className="font-mono">{(n / 10_000).toFixed(1) + '조원'}</span>
    return <span className="font-mono">{n.toLocaleString('ko-KR') + '억원'}</span>
  }

  // 상장 주식수
  if (key === 'lstn_stcn') {
    const n = Number(value)
    if (isNaN(n)) return <span className="text-gray-400">—</span>
    return <span className="font-mono">{n.toLocaleString('ko-KR') + '주'}</span>
  }

  // 전일 대비
  if (key === 'prdy_vrss') {
    const n = Number(value)
    if (isNaN(n)) return <span className="text-gray-400">—</span>
    if (n > 0) return <span className="font-mono text-red-600">+{n.toLocaleString('ko-KR')}원</span>
    if (n < 0) return <span className="font-mono text-blue-600">{n.toLocaleString('ko-KR')}원</span>
    return <span className="font-mono text-gray-500">0원</span>
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
// 일봉 탭 방어 변환 헬퍼 (cycle266 B-1)
//
// 계약: 백엔드 NUMERIC 컬럼(change_rate 등)이 asyncpg Decimal → pydantic v2
// JSON 모드에서 문자열로 직렬화되는 경우가 있다(운영 실측 "0.0000"). 아래
// 헬퍼는 문자열 숫자·number·null/undefined/NaN/비숫자 문자열을 전부 받아
// (a) 유효하면 number, (b) 그 외에는 null 을 돌려준다 — 렌더 쪽은 null 을
// '—'(em dash) 로만 표시하고 `toFixed`/`toLocaleString` 을 직접 호출하지
// 않는다(호출부는 항상 이 헬퍼가 돌려준 number 에만 건다).
// ────────────────────────────────────────────────────────────────────────

/** 문자열 숫자 → number, 그 외(NaN/null/undefined/빈 문자열/비숫자 문자열) → null. */
function toSafeNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** OHLCV 셀 — 변환 실패는 '—'. */
function formatSafeCount(value: unknown): string {
  const n = toSafeNumber(value)
  return n === null ? '—' : n.toLocaleString('ko-KR')
}

/** 등락률 셀 — 텍스트 + 색상 클래스를 함께 돌려준다(색상 분기는 변환 후 값 기준). */
function formatSafeChangeRate(value: unknown): { text: string; className: string } {
  const n = toSafeNumber(value)
  if (n === null) {
    return { text: '—', className: 'text-gray-500' }
  }
  const className = n > 0 ? 'text-red-600' : n < 0 ? 'text-blue-600' : 'text-gray-500'
  const text = `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
  return { text, className }
}

// ────────────────────────────────────────────────────────────────────────
// 일봉 탭 컴포넌트 (사이클 124 Q1=A, 사이클 266 B-1/B-3 방어 변환 + 404 분기)
// ────────────────────────────────────────────────────────────────────────
function DailyTab({ ticker }: { ticker: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['stock-master-daily', ticker],
    queryFn: () => fetchDaily(ticker, 30),
    retry: 1,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const rows: StockMasterDailyRow[] = Array.isArray(data) ? data : []

  // cycle266 B-3 — 404 는 "적재 대상 아님" 안내(회색), 그 외(500·네트워크)는 오류(빨강).
  // DetailModal 의 is404 판별(약 435행)과 동일 패턴.
  const is404 =
    isError && axios.isAxiosError(error) && error.response?.status === 404

  if (isLoading) return <p className="text-sm text-gray-400 animate-pulse py-4">로딩 중...</p>

  if (isError && !is404) {
    return (
      <p className="text-sm text-red-600 py-4" data-testid="stock-master-daily-error">
        일봉 데이터 조회 실패 — 잠시 후 다시 시도해 주세요.
      </p>
    )
  }

  // cycle266 D-1 — 404 는 '정상 미적재' 가 압도적이지만 **유일한 원인은 아니다**:
  // `src/db/stock_master_daily.py::get_recent_daily` 가 DB 예외를 자신이 삼키고
  // `[]` 를 돌려주므로(그 모듈은 6 전략 prepare 공유 = 이번 사이클 무접촉) 진짜
  // 장애도 여기로 온다. 안내가 원인을 **단정하지 않도록** 단서 한 절을 붙인다.
  // ⚠️ 이 단서를 지우지 말 것 — 가드 = StockMaster.dailyTab.cycle266.test.tsx D-1.
  if (is404 || rows.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4" data-testid="stock-master-daily-notice">
        일봉 미적재 — 일봉은 전 종목이 아니라 전략 유니버스 대상만 적재됩니다.
        단, 서버가 데이터를 가져오지 못한 경우에도 같은 안내가 나올 수 있으니,
        계속 보이면 시스템 로그에서 stock_master_daily 를 확인하세요.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto" data-testid="stock-master-daily-table">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th className="text-left py-2 pr-3 font-medium">기준일</th>
            <th className="text-right py-2 pr-3 font-medium">시가</th>
            <th className="text-right py-2 pr-3 font-medium">고가</th>
            <th className="text-right py-2 pr-3 font-medium">저가</th>
            <th className="text-right py-2 pr-3 font-medium">종가</th>
            <th className="text-right py-2 pr-3 font-medium">거래량</th>
            <th className="text-right py-2 font-medium">등락률</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row) => {
            const changeRate = formatSafeChangeRate(row.change_rate)
            return (
              <tr key={row.bas_dd} className="hover:bg-gray-50">
                <td className="py-1.5 pr-3 font-mono text-gray-700 text-xs">{row.bas_dd}</td>
                <td className="py-1.5 pr-3 font-mono text-right text-gray-700">{formatSafeCount(row.open_price)}</td>
                <td className="py-1.5 pr-3 font-mono text-right text-gray-700">{formatSafeCount(row.high_price)}</td>
                <td className="py-1.5 pr-3 font-mono text-right text-gray-700">{formatSafeCount(row.low_price)}</td>
                <td className="py-1.5 pr-3 font-mono text-right font-medium text-gray-900">{formatSafeCount(row.close_price)}</td>
                <td className="py-1.5 pr-3 font-mono text-right text-gray-600">{formatSafeCount(row.volume)}</td>
                <td className={`py-1.5 font-mono text-right ${changeRate.className}`}>
                  {changeRate.text}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────
// 상세 모달 컴포넌트 (사이클 124 Q1=A — 상세/일봉 탭 추가)
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
  // 사이클 124 Q1=A — 탭 상태: 'detail' | 'daily'
  const [activeTab, setActiveTab] = useState<'detail' | 'daily'>('detail')

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['stock-master-detail', ticker],
    queryFn: () => fetchDetail(ticker),
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
    // placeholderData 로 변경 — initialData 는 fresh로 간주되어 API 재호출을 막지만
    // placeholderData 는 항상 stale로 간주되어 fetchDetail 이 반드시 호출됨 (사이클 124)
    placeholderData: initialData,
  })

  const is404 =
    isError && axios.isAxiosError(error) && error.response?.status === 404

  // raw 필드의 카테고리별 항목 계산
  function getCategoryItems(
    detail: StockMasterDetail,
    category: string,
  ): [string, unknown][] {
    const topLevelKeys = ['ticker', 'name', 'excg_dvsn_cd', 'nxt_tradable', 'krx_halted', 'admin_item', 'refreshed_at']
    const keys = CATEGORY_KEYS[category] ?? []
    const rawKeys = keys.filter((k) => topLevelKeys.includes(k))
    const rawDataKeys = keys.filter((k) => !topLevelKeys.includes(k))

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
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
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

        {/* 탭 네비게이션 */}
        <div className="flex border-b border-gray-200 shrink-0 px-6" data-testid="stock-master-detail-tabs">
          <button
            data-testid="stock-master-tab-detail"
            onClick={() => setActiveTab('detail')}
            className={`text-sm px-4 py-2 font-medium border-b-2 transition-colors ${
              activeTab === 'detail'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            상세
          </button>
          <button
            data-testid="stock-master-tab-daily"
            onClick={() => setActiveTab('daily')}
            className={`text-sm px-4 py-2 font-medium border-b-2 transition-colors ${
              activeTab === 'daily'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            일봉 (30일)
          </button>
        </div>

        <div className="px-6 py-4 overflow-y-auto flex-1">
          {/* 일봉 탭 */}
          {activeTab === 'daily' && (
            <DailyTab ticker={ticker} />
          )}

          {/* 상세 탭 */}
          {activeTab === 'detail' && (
            <>
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
            </>
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
// ────────────────────────────────────────────────────────────────────────
// 사이클 128 — 종목목록 필터 4 컨트롤 + 400ms 디바운스
// 사이클 65 TradeAmountFilterCard 패턴 답습 + 사이클 64 PriceFilterCard
// ────────────────────────────────────────────────────────────────────────
const FILTER_DEBOUNCE_MS = 400

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(handle)
  }, [value, delay])
  return debounced
}

export default function StockMaster() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [offset, setOffset] = useState(() => {
    const o = parseInt(searchParams.get('offset') || '0', 10)
    return Number.isFinite(o) && o >= 0 ? o : 0
  })
  // 사이클 128 — 필터 4 state (URL query 초기화)
  const [marketFilter, setMarketFilter] = useState<'' | 'KOSPI' | 'KOSDAQ'>(() => {
    const m = searchParams.get('market')
    return m === 'KOSPI' || m === 'KOSDAQ' ? m : ''
  })
  const [minMarketCapEokInput, setMinMarketCapEokInput] = useState<string>(
    () => searchParams.get('minMarketCap') || '',
  )
  const [minTradeAmountEokInput, setMinTradeAmountEokInput] = useState<string>(
    () => searchParams.get('minTradeAmount') || '',
  )
  const [nameSubstrInput, setNameSubstrInput] = useState<string>(
    () => searchParams.get('name') || '',
  )
  // T-3 IME composition (한글 자모 입력 중 trigger 차단)
  const [isComposing, setIsComposing] = useState(false)

  // 디바운스된 필터 값 (400ms)
  const debouncedMinCap = useDebouncedValue(minMarketCapEokInput, FILTER_DEBOUNCE_MS)
  const debouncedMinAmt = useDebouncedValue(minTradeAmountEokInput, FILTER_DEBOUNCE_MS)
  // IME composition 중에는 nameSubstr 디바운스 대상에서 제외 (이전 값 유지)
  const debouncedName = useDebouncedValue(isComposing ? '' : nameSubstrInput, FILTER_DEBOUNCE_MS)

  // 필터 값 정규화
  const filterParams = useMemo(() => {
    const cap = parseInt(debouncedMinCap, 10)
    const amt = parseInt(debouncedMinAmt, 10)
    return {
      market: (marketFilter || null) as 'KOSPI' | 'KOSDAQ' | null,
      minMarketCapEok: Number.isFinite(cap) && cap > 0 ? cap : 0,
      minTradeAmountEok: Number.isFinite(amt) && amt > 0 ? amt : 0,
      nameSubstr: debouncedName.trim(),
    }
  }, [marketFilter, debouncedMinCap, debouncedMinAmt, debouncedName])

  // 필터 변경 시 offset reset + URL 동기화
  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    if (filterParams.market) next.set('market', filterParams.market)
    else next.delete('market')
    if (filterParams.minMarketCapEok > 0)
      next.set('minMarketCap', String(filterParams.minMarketCapEok))
    else next.delete('minMarketCap')
    if (filterParams.minTradeAmountEok > 0)
      next.set('minTradeAmount', String(filterParams.minTradeAmountEok))
    else next.delete('minTradeAmount')
    if (filterParams.nameSubstr) next.set('name', filterParams.nameSubstr)
    else next.delete('name')

    // 필터 변경 시 offset=0 reset (사용자 결정 Q2=A)
    next.delete('offset')
    setOffset(0)

    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filterParams.market,
    filterParams.minMarketCapEok,
    filterParams.minTradeAmountEok,
    filterParams.nameSubstr,
  ])

  // 필터 초기화 (T-1 영속 — 빈 필터 = 전체)
  const handleClearFilter = () => {
    setMarketFilter('')
    setMinMarketCapEokInput('')
    setMinTradeAmountEokInput('')
    setNameSubstrInput('')
  }

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [detailTicker, setDetailTicker] = useState<string | null>(null)
  const [detailInitialData, setDetailInitialData] = useState<StockMasterDetail | undefined>(undefined)
  // 사이클 90 — 토스트 상태 (react-hot-toast 미사용 환경 호환)
  const [refreshToast, setRefreshToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  // 사이클 126 — 신규 2 mutation toast state (basics/daily refresh)
  const [basicsToast, setBasicsToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [dailyToast, setDailyToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  // 사이클 129 — KIS 종목 마스터 파일 새로고침 toast state (master refresh)
  const [masterToast, setMasterToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const LIMIT = 100

  const queryClient = useQueryClient()

  // 사이클 127 — fire-and-forget 패턴 (사이클 90/126 동기 대기 → 비동기 trigger).
  // 백엔드 즉시 202 Accepted 반환 + 백그라운드 task. 진행 상황은 RefreshProgressBanner 5초 폴링.
  // onSuccess = trigger 성공 (작업 시작) / onError = 409 (이미 진행 중) 또는 네트워크 오류.
  // retry: false 의무 (중복 trigger 방지). axios timeout 결함 영구 차단.
  const refreshMutation = useMutation({
    mutationFn: refreshUniverseNow,
    retry: false,
    onSuccess: () => {
      setRefreshToast({
        type: 'success',
        message: '종목마스터 새로고침 시작 — 진행 상황은 상단 배너 참고',
      })
      queryClient.invalidateQueries({ queryKey: ['refresh-progress'] })
      setTimeout(() => setRefreshToast(null), 4000)
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setRefreshToast({
          type: 'error',
          message: '종목마스터 새로고침 이미 진행 중 — 상단 배너 참고',
        })
      } else {
        // 사이클 106 영역 2 — Q3=A 정밀화 (KIS API 일시 결함 영역 명시)
        setRefreshToast({
          type: 'error',
          message: 'KIS API 일시 결함 — 잠시 후 재시도',
        })
      }
      setTimeout(() => setRefreshToast(null), 4000)
    },
  })

  // 사이클 127 — basics fire-and-forget (사이클 126 동기 13분 timeout 결함 영구 시정).
  const basicsMutation = useMutation({
    mutationFn: refreshBasicsNow,
    retry: false,
    onSuccess: () => {
      setBasicsToast({
        type: 'success',
        message: '기본정보 새로고침 시작 (~13분 소요) — 진행 상황은 상단 배너 참고',
      })
      queryClient.invalidateQueries({ queryKey: ['refresh-progress'] })
      setTimeout(() => setBasicsToast(null), 6000)
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setBasicsToast({
          type: 'error',
          message: '기본정보 새로고침 이미 진행 중 — 상단 배너 참고',
        })
      } else {
        setBasicsToast({
          type: 'error',
          message: 'KIS API 일시 결함 — 잠시 후 재시도',
        })
      }
      setTimeout(() => setBasicsToast(null), 6000)
    },
  })

  // 사이클 127 — daily fire-and-forget.
  const dailyMutation = useMutation({
    mutationFn: refreshDailyNow,
    retry: false,
    onSuccess: () => {
      setDailyToast({
        type: 'success',
        message: '일봉 새로고침 시작 (~13분 소요) — 진행 상황은 상단 배너 참고',
      })
      queryClient.invalidateQueries({ queryKey: ['refresh-progress'] })
      setTimeout(() => setDailyToast(null), 6000)
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setDailyToast({
          type: 'error',
          message: '일봉 새로고침 이미 진행 중 — 상단 배너 참고',
        })
      } else {
        setDailyToast({
          type: 'error',
          message: 'KIS API 일시 결함 — 잠시 후 재시도',
        })
      }
      setTimeout(() => setDailyToast(null), 6000)
    },
  })

  // 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 수동 trigger.
  // Q4=A 마스터 우선 + Q6=C master_raw 별도 컬럼 (사이클 81 G-AST1 raw 분리 영속).
  // 사이클 127 fire-and-forget BackgroundTasks 패턴 100% 답습.
  const masterMutation = useMutation({
    mutationFn: refreshMasterNow,
    retry: false,
    onSuccess: () => {
      setMasterToast({
        type: 'success',
        message: '종목마스터 일일 갱신 시작 — 진행 상황은 상단 배너 참고',
      })
      queryClient.invalidateQueries({ queryKey: ['refresh-progress'] })
      setTimeout(() => setMasterToast(null), 6000)
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        setMasterToast({
          type: 'error',
          message: '종목마스터 갱신 이미 진행 중 — 상단 배너 참고',
        })
      } else {
        setMasterToast({
          type: 'error',
          message: 'KIS API 일시 결함 — 잠시 후 재시도',
        })
      }
      setTimeout(() => setMasterToast(null), 6000)
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

  // 3. 목록 테이블 (사이클 128 — 4 필터 + 페이징 + total 응답 schema)
  // queryFn 을 별도 함수로 추출 — AST 가드 정규식 (사이클 80 hotfix) 첫 `}` 매칭 회피.
  const listQueryFn = () =>
    fetchList({
      limit: LIMIT,
      offset,
      market: filterParams.market,
      minMarketCapEok: filterParams.minMarketCapEok,
      minTradeAmountEok: filterParams.minTradeAmountEok,
      nameSubstr: filterParams.nameSubstr,
    })
  const listQuery = useQuery({
    queryKey: ['stock-master-list', LIMIT, offset, filterParams.market, filterParams.minMarketCapEok, filterParams.minTradeAmountEok, filterParams.nameSubstr],
    queryFn: listQueryFn,
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

  // 사이클 128 — 응답 schema 변경 (list[dict] → {items, total, limit, offset})
  // fetchList 의 호환 layer 가 양쪽 응답을 envelope 로 정규화 → 직접 추출.
  const listData = listQuery.data
  const listItems: StockMasterListItem[] = listData?.items ?? []
  const listTotal: number = listData?.total ?? 0
  // 사이클 169 — migration 036 (사이클 150) 신 스키마. UPDATE 시 seq0/seq1
  // changed_at 이 동일(now())이라 changed_at 정렬만으론 순서 비결정 →
  // seq ASC (최신본 0 먼저 / 직전본 1 다음) 명시 정렬.
  const historyItems: StockMasterHistoryItem[] = (
    Array.isArray(historyQuery.data) ? [...historyQuery.data] : []
  ).sort((a, b) => a.seq - b.seq)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">종목마스터</h1>

      {/* 사이클 127 — 3 작업 진행 가시화 배너 (running 시 자동 표시, 5초 폴링) */}
      <RefreshProgressBanner />

      {/* 사이클 106 영역 1+4 — 안내 배너 갱신 (Q2=A 신규 메시지 추가) */}
      <div
        className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800"
        data-testid="stock-master-info-banner"
      >
        <p className="font-medium mb-1">종목 마스터 데이터</p>
        <p className="text-xs text-blue-700">
          한국투자증권 종목 기본정보 (전일종가, NXT 거래가능 여부, 관리종목 등) 영역의 적재 현황입니다.
          매일 20:00 KRX/KOSDAQ 전 종목 일괄 적재 영역 + 보유 종목 + 매수 후보 종목 영역 5분 주기 자동 갱신 영역입니다.
        </p>
      </div>

      {/* ── 카드 1: 상태 ── */}
      <div
        className="bg-white rounded-lg shadow p-6"
        data-testid={
          !statsQuery.isLoading && !scanPoolQuery.isLoading && statsQuery.data
            ? 'stock-master-stats-card'
            : 'stock-master-stats-card-loading'
        }
      >
        {/* 사이클 90 Q26=A — stats 카드 상단 우측 "지금 새로고침" 버튼 (+ 사이클 126 신규 2 버튼) */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-700">전체 현황</h2>
          <div className="flex items-center gap-2">
            <button
              data-testid="stock-master-refresh-universe-button"
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shrink-0"
            >
              {refreshMutation.isPending ? '적재 중...' : '지금 새로고침'}
            </button>
            {/* 사이클 126 — 기본정보 새로고침 (KIS CTPF1002R 매스 보강) */}
            <button
              data-testid="stock-master-refresh-basics-button"
              onClick={() => basicsMutation.mutate()}
              disabled={basicsMutation.isPending}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shrink-0"
              title="NXT/정지/관리종목 영역 KIS CTPF1002R 매스 보강 (~4.5분)"
            >
              {basicsMutation.isPending ? '보강 중...' : '기본정보 새로고침'}
            </button>
            {/* 사이클 126 — 일봉 새로고침 (사이클 122 일봉 task 즉시 trigger) */}
            <button
              data-testid="stock-master-refresh-daily-button"
              onClick={() => dailyMutation.mutate()}
              disabled={dailyMutation.isPending}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shrink-0"
              title="KIS 일봉 적재 즉시 trigger (~4.5분)"
            >
              {dailyMutation.isPending ? '적재 중...' : '일봉 새로고침'}
            </button>
            {/* 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 적재 (16:30 KST 자동 task 수동 trigger) */}
            <button
              data-testid="stock-master-refresh-master-button"
              onClick={() => masterMutation.mutate()}
              disabled={masterMutation.isPending}
              className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-violet-300 bg-violet-50 text-violet-700 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shrink-0"
              title="KIS 종목 마스터 파일 (KOSPI 70 / KOSDAQ 64 컬럼) 적재 즉시 trigger"
            >
              {masterMutation.isPending ? '적재 중...' : '마스터 새로고침'}
            </button>
          </div>
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

        {/* 사이클 126 — basics 토스트 */}
        {basicsToast && (
          <div
            data-testid="stock-master-refresh-basics-toast"
            className={`mb-4 px-4 py-2 rounded text-sm font-medium ${
              basicsToast.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {basicsToast.message}
          </div>
        )}

        {/* 사이클 126 — daily 토스트 */}
        {dailyToast && (
          <div
            data-testid="stock-master-refresh-daily-toast"
            className={`mb-4 px-4 py-2 rounded text-sm font-medium ${
              dailyToast.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {dailyToast.message}
          </div>
        )}

        {/* 사이클 129 — master 토스트 (KIS 종목 마스터 파일 새로고침) */}
        {masterToast && (
          <div
            data-testid="stock-master-refresh-master-toast"
            className={`mb-4 px-4 py-2 rounded text-sm font-medium ${
              masterToast.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {masterToast.message}
          </div>
        )}

        {statsQuery.isLoading || scanPoolQuery.isLoading ? (
          <p className="text-sm text-gray-400 animate-pulse">로딩 중...</p>
        ) : statsQuery.isError ? (
          <p className="text-sm text-red-600">통계 조회 실패</p>
        ) : (
          <>
            {/* 사이클 124 Q3=A — 4 → 8 카드 확장 */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4" data-testid="stock-master-stats-grid">
              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-500">전체 종목 수</p>
                <p className="text-2xl font-bold text-gray-900">
                  {statsQuery.data?.count_all ?? '—'}
                </p>
              </div>
              <div className="bg-amber-50 rounded p-3">
                <p className="text-xs text-gray-500">전일종가 적재</p>
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
              {/* 사이클 124 Q3=A 신규 4 카드 */}
              <div className="bg-violet-50 rounded p-3" data-testid="stock-master-stats-with-hts-avls">
                <p className="text-xs text-gray-500">시가총액 보유</p>
                <p className="text-2xl font-bold text-violet-700">
                  {statsQuery.data?.with_hts_avls ?? '—'}
                </p>
              </div>
              <div className="bg-indigo-50 rounded p-3" data-testid="stock-master-stats-with-acml-tr-pbmn">
                <p className="text-xs text-gray-500">거래대금 보유</p>
                <p className="text-2xl font-bold text-indigo-700">
                  {statsQuery.data?.with_acml_tr_pbmn ?? '—'}
                </p>
              </div>
              <div className="bg-sky-50 rounded p-3" data-testid="stock-master-stats-total-daily-rows">
                <p className="text-xs text-gray-500">일봉 총 행 수</p>
                <p className="text-2xl font-bold text-sky-700">
                  {statsQuery.data?.total_daily_rows?.toLocaleString('ko-KR') ?? '—'}
                </p>
              </div>
              <div className="bg-teal-50 rounded p-3" data-testid="stock-master-stats-last-daily-load-at">
                <p className="text-xs text-gray-500">마지막 일봉 적재</p>
                <p className="text-sm font-bold text-teal-700">
                  {statsQuery.data?.last_daily_load_at
                    ? formatKst(statsQuery.data.last_daily_load_at)
                    : <span className="text-gray-400 text-sm font-normal">미적재</span>}
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
          <h2 className="text-base font-semibold text-gray-700">
            종목 목록
            {listTotal > 0 && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                — 전체 {listTotal.toLocaleString('ko-KR')}건
              </span>
            )}
          </h2>
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
              {listItems.length > 0
                ? `${(offset + 1).toLocaleString('ko-KR')} – ${(offset + listItems.length).toLocaleString('ko-KR')}`
                : '0'}
              {listTotal > 0 && ` / ${listTotal.toLocaleString('ko-KR')}`}
            </span>
            <button
              data-testid="stock-master-list-next"
              disabled={offset + listItems.length >= listTotal}
              onClick={() => setOffset(offset + LIMIT)}
              className="text-sm px-3 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
            >
              다음
            </button>
          </div>
        </div>

        {/* 사이클 128 — 4 필터 컨트롤 (T-1 빈 필터 = 전체 영속 + T-2 단위 표기 + T-3 IME) */}
        <div
          className="mb-4 p-3 bg-gray-50 rounded border border-gray-200"
          data-testid="stock-master-filter-bar"
        >
          <div className="flex flex-wrap items-end gap-3">
            {/* 시장 select */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-600">시장</label>
              <select
                data-testid="stock-master-filter-market"
                value={marketFilter}
                onChange={(e) =>
                  setMarketFilter(e.target.value as '' | 'KOSPI' | 'KOSDAQ')
                }
                className="text-sm border border-gray-300 rounded px-2 py-1 bg-white"
              >
                <option value="">전체</option>
                <option value="KOSPI">KOSPI</option>
                <option value="KOSDAQ">KOSDAQ</option>
              </select>
            </div>

            {/* 시총 min input (억원 단위) */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-600">최소 시가총액 (억원)</label>
              <input
                data-testid="stock-master-filter-marketcap-min"
                type="number"
                min={0}
                inputMode="numeric"
                value={minMarketCapEokInput}
                onChange={(e) => setMinMarketCapEokInput(e.target.value)}
                placeholder="0 (예: 1000 = 1,000억)"
                className="text-sm border border-gray-300 rounded px-2 py-1 w-44"
              />
            </div>

            {/* 거래대금 min input (억원 단위) */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-600">최소 거래대금 (억원)</label>
              <input
                data-testid="stock-master-filter-tradeamount-min"
                type="number"
                min={0}
                inputMode="numeric"
                value={minTradeAmountEokInput}
                onChange={(e) => setMinTradeAmountEokInput(e.target.value)}
                placeholder="0 (예: 100 = 100억)"
                className="text-sm border border-gray-300 rounded px-2 py-1 w-44"
              />
            </div>

            {/* 종목명 검색 input (IME composition 가드) */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-600">종목명 검색</label>
              <input
                data-testid="stock-master-filter-name-substr"
                type="text"
                value={nameSubstrInput}
                onChange={(e) => setNameSubstrInput(e.target.value)}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={(e) => {
                  setIsComposing(false)
                  // composition 완료 후 최종 값 trigger (debounce 재계산)
                  setNameSubstrInput((e.target as HTMLInputElement).value)
                }}
                placeholder="예: 삼성"
                className="text-sm border border-gray-300 rounded px-2 py-1 w-48"
              />
            </div>

            {/* 초기화 버튼 */}
            <button
              data-testid="stock-master-filter-clear"
              onClick={handleClearFilter}
              type="button"
              className="text-sm px-3 py-1 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-100"
            >
              필터 초기화
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
                  <th className="text-right py-2 pr-3 font-medium">현재가</th>
                  <th className="text-right py-2 pr-3 font-medium hidden md:table-cell">전일대비</th>
                  <th className="text-right py-2 pr-3 font-medium hidden md:table-cell">시가총액</th>
                  <th className="text-right py-2 pr-3 font-medium hidden md:table-cell">거래대금</th>
                  <th className="text-right py-2 pr-3 font-medium">전일종가</th>
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
                      {formatExchange(item.excg_dvsn_cd)}
                    </td>
                    <td
                      className="py-2 pr-3 font-mono text-right text-gray-900"
                      data-testid={`stock-master-row-stck-prpr-${item.ticker}`}
                    >
                      {formatPrice(item.raw?.stck_prpr)}
                    </td>
                    <td
                      className={`py-2 pr-3 font-mono text-right hidden md:table-cell ${
                        formatPriceChange(item.raw?.prdy_vrss).color
                      }`}
                      data-testid={`stock-master-row-prdy-vrss-${item.ticker}`}
                    >
                      {formatPriceChange(item.raw?.prdy_vrss).text}
                    </td>
                    <td
                      className="py-2 pr-3 font-mono text-right text-gray-700 hidden md:table-cell"
                      data-testid={`stock-master-row-hts-avls-${item.ticker}`}
                    >
                      {formatMarketCap(item.raw?.hts_avls)}
                    </td>
                    <td
                      className="py-2 pr-3 font-mono text-right text-gray-700 hidden md:table-cell"
                      data-testid={`stock-master-row-acml-tr-pbmn-${item.ticker}`}
                    >
                      {formatTradeAmount(item.raw?.acml_tr_pbmn)}
                    </td>
                    <td className="py-2 pr-3 font-mono text-right text-gray-900">
                      {formatPrice(item.raw?.bfdy_clpr)}
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
                  <th className="text-left py-2 pr-3 font-medium">스냅샷</th>
                  <th className="text-left py-2 pr-3 font-medium">변경일시 (KST)</th>
                  <th className="text-left py-2 pr-3 font-medium">변경유형</th>
                  <th className="text-left py-2 font-medium">raw 스냅샷</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {/* 사이클 169 — seq0 최신본 / seq1 직전본 2 스냅샷 각각 표시 */}
                {historyItems.map((item) => (
                  <tr
                    key={`${item.ticker}-${item.seq}`}
                    className="hover:bg-gray-50"
                  >
                    <td className="py-2 pr-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          item.seq === 0
                            ? 'bg-indigo-100 text-indigo-800'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {item.seq === 0 ? '최신본' : '직전본'}
                      </span>
                    </td>
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
                    <td className="py-2">
                      <CollapsiblePre label="raw" data={item.raw} />
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
