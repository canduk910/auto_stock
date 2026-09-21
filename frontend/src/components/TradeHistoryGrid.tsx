import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { getTradeHistory } from '../api/history'
import {
  findLlmSummary,
  getLlmEvaluationSummaries,
  llmSummaryDatesFor,
} from '../api/llm-evaluations'
import { getStrategyColor } from '../types/strategy'
import type { TradeRecord } from '../types/trading'
import type { LlmEvaluationSummaryMap } from '../types/llm-evaluation'
import LlmEvaluationModal from './LlmEvaluationModal'
import LlmScoreBadge from './LlmScoreBadge'

const columnHelper = createColumnHelper<TradeRecord>()

/**
 * 수치 열 방어 변환 — 숫자와 **숫자 문자열**을 모두 받는다.
 *
 * 백엔드 계약은 숫자(`TradeRecord.price: number`)이고 `src/routes/history.py` 가 그 계약을
 * 지킨다. 그런데 그 라우트는 `SELECT t.*` raw 행을 싣는 구조라, NUMERIC 컬럼이 늘거나
 * 사영이 빠지면 pydantic v2 가 Decimal 을 다시 문자열로 내보낸다. `typeof v === 'number'`
 * 단독 판정은 그때 값을 통째로 `-` 로 지워 **화면이 조용히 비고**, 그 침묵이 결함을
 * 2026-07-16 RDS 이전부터 덮었다. 여기서는 값을 살리고, 진짜 결측만 `-` 로 남긴다.
 */
function toNum(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

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
// cycle276 — 평가 조회에 넘기는 **영업일**(`YYYY-MM-DD`). 4자리 연도가 필요해 위의
// 2자리 표시용 포맷터와 별도로 둔다. `formatToParts` 로 뽑으므로 로케일 출력 형태와 무관하다.
// ⚠️ `new Date(iso).getFullYear()` 같은 브라우저 로컬타임 추출 금지 — UTC 23:05 은 KST 로
//    **다음 날**이고, 그 하루 차이가 곧 조회 실패다(KIS 주문번호는 하루 단위로만 유일).
const KST_FULL_DATE_FMT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
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

/**
 * cycle276 — `YYYY-MM-DD`(KST). 파싱 실패는 `undefined` 이고, 그 행은 요약과 날짜를
 * 대조할 수 없으므로 버튼이 **열리지 않는다**(날짜 없이 조회하면 라우트가 "가장 최근
 * 1건" 을 골라 다른 거래의 평가를 띄울 수 있다 — 그 위험을 지느니 못 여는 편이 낫다).
 */
function toKstIsoDate(timestamp: string): string | undefined {
  const d = parseTimestamp(timestamp)
  if (!d) return undefined
  const parts = KST_FULL_DATE_FMT.formatToParts(d)
  const y = parts.find((p) => p.type === 'year')?.value
  const m = parts.find((p) => p.type === 'month')?.value
  const dd = parts.find((p) => p.type === 'day')?.value
  if (!y || !m || !dd) return undefined
  return `${y.padStart(4, '0')}-${m.padStart(2, '0')}-${dd.padStart(2, '0')}`
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

/**
 * cycle276 — 열 정의를 모듈 상수에서 **팩토리**로 바꾼다.
 *
 * "AI 자문" 셀이 (a) 배치 요약 결과와 (b) 팝업 열기 콜백을 둘 다 봐야 해서 모듈 레벨
 * 상수로는 만들 수 없다. 호출부가 `useMemo` 로 감싸 렌더마다 테이블이 재생성되는 것을
 * 막고, `colSpan` 도 같은 배열 길이를 참조한다.
 */
function makeColumns(
  summaries: LlmEvaluationSummaryMap,
  summariesReady: boolean,
  onOpen: (orderNo: string, tradeDate: string | undefined) => void,
) {
  return [
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
        const n = toNum(info.getValue())
        return n === null ? '-' : n.toLocaleString() + '원'
      },
    }),
    columnHelper.accessor('quantity', {
      header: '수량',
      cell: (info) => {
        const n = toNum(info.getValue())
        return n === null ? '-' : n.toLocaleString() + '주'
      },
    }),
    columnHelper.accessor('profit_loss', {
      header: '매매손익',
      cell: (info) => {
        const n = toNum(info.getValue())
        if (n === null || n === 0) return '-'
        const cls = n > 0 ? 'text-red-600' : 'text-blue-600'
        const sign = n > 0 ? '+' : ''
        return <span className={cls}>{sign}{n.toLocaleString()}원</span>
      },
    }),
    columnHelper.accessor('status', {
      header: '상태',
      cell: (info) => {
        const v = String(info.getValue() ?? '')
        const map: Record<string, { label: string; cls: string }> = {
          COMPLETED: { label: '체결', cls: 'bg-green-100 text-green-700' },
          PENDING: { label: '대기', cls: 'bg-yellow-100 text-yellow-700' },
          // cycle261 후속(적대 검토) — yellow/orange→beige/brown 별칭 이후 종전 orange-100 이
          // PENDING(beige-100)과 거의 같은 배경이 됐다(sRGB 거리 ≈15.9). brown-200 으로 구분 복원.
          PARTIAL: { label: '부분체결', cls: 'bg-brown-200 text-brown-800' },
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
    // cycle276 — AI 매수평가 팝업 버튼(맨 끝 열).
    // 평가는 **매수 주문**에만 붙는다. 매도 행에도 비활성 버튼을 렌더해 열 폭을 유지하고,
    // 왜 못 누르는지(`매수 주문만 평가 대상` / `평가 기록 없음`)를 title 로 알린다 —
    // 아무 표시 없이 칸만 비면 "버튼이 사라졌다"는 결함처럼 보인다.
    columnHelper.display({
      id: 'llmEval',
      header: 'AI 자문',
      cell: (info) => {
        const row = info.row.original
        const orderNo = String(row.order_no ?? '').trim()
        const isBuy = String(row.trade_type ?? '') === 'BUY'
        // 이 행이 **조회 대상인가**(매수 + 주문번호 존재)는 요약 응답 없이도 확정된다.
        // 조회 대상인데 아직 답을 못 받은 동안 "평가 기록 없음" 을 띄우면 그것은 **거짓말**이다
        // (기록이 있는 주문도 잠깐 없다고 말한다). 그래서 그 구간은 별도 상태로 그린다.
        const lookupPending = isBuy && orderNo !== '' && !summariesReady
        if (lookupPending) {
          return (
            <button
              type="button"
              data-testid={`llm-eval-btn-loading-${info.row.index}`}
              disabled
              title="평가 기록 조회 중..."
              className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-300 cursor-progress"
            >
              AI 자문
            </button>
          )
        }
        // ⚠️ 주문번호만으로 버튼을 켜면 화면이 거짓말을 한다. 배치 요약은 **날짜 없이**
        // 주문번호로 묻고(한 페이지가 여러 날짜에 걸치므로) 모달 상세는 **그 행의 날짜와
        // 함께** 묻는다. KIS 주문번호(ODNO)는 마이그레이션 043 주석대로 **하루 단위로만
        // 유일**해서, 09-08 에만 평가가 있는 번호를 09-11 체결 행이 조회하면 배치는 키를
        // 돌려주고(버튼 활성) 상세는 404 를 준다(회색 "평가 기록 없음") — 실 PG + 실
        // 라우트로 재현된 정상 경로다. 그래서 배치 응답 맵의 키가 `날짜|주문번호` 복합
        // 키이고, 이 셀은 **그 행의 KST 날짜와 함께** 조회한다.
        const rowKstDate = toKstIsoDate(String(row.timestamp ?? ''))
        const summary = findLlmSummary(summaries, rowKstDate, orderNo)
        // 기록이 아예 없는 것과 "다른 날짜에만 있는" 것은 다른 사실이다(title 이 갈린다).
        const otherDates = summary ? [] : llmSummaryDatesFor(summaries, orderNo)
        const enabled = isBuy && Boolean(summary)
        const testId = orderNo
          ? `llm-eval-btn-${orderNo}`
          : `llm-eval-btn-none-${info.row.index}`
        // 비활성 사유를 셋으로 갈라 준다 — "기록이 아예 없다" 와 "다른 날짜의 기록이다" 는
        // 다른 사실이고, 후자를 "평가 기록 없음" 이라고 말하면 반대 방향의 거짓말이 된다.
        const title = !isBuy
          ? '매수 주문만 평가 대상'
          : orderNo === ''
            ? '주문번호 없음 — 평가 기록 없음'
            : summary
              ? 'AI 매수평가 보기'
              : !rowKstDate
                ? '주문일을 읽을 수 없음 — 평가 기록 대조 불가'
                : otherDates.length > 0
                  ? `다른 날짜(${otherDates.join(', ')})의 평가 기록 — 이 행에서 열 수 없음`
                  : '평가 기록 없음'
        return (
          // cycle337 — 점수를 버튼 **왼쪽**에 함께 그린다. 팝업을 열지 않아도 행끼리
          // 비교할 수 있어야 한다는 것이 이 열의 요구다. 점수는 이미 `summary` 에
          // 실려 있으므로 추가 조회가 없다.
          <div className="flex items-center gap-1.5">
            <LlmScoreBadge
              summary={summary}
              testId={orderNo ? `llm-score-${orderNo}` : `llm-score-none-${info.row.index}`}
            />
            <button
              type="button"
              data-testid={testId}
              disabled={!enabled}
              title={title}
              onClick={() => onOpen(orderNo, rowKstDate)}
              className={`px-2 py-1 text-xs rounded border ${
                enabled
                  ? 'border-blue-300 text-blue-700 hover:bg-blue-50'
                  : 'border-gray-200 text-gray-400 cursor-not-allowed'
              }`}
            >
              AI 자문
            </button>
          </div>
        )
      },
    }),
  ]
}

export default function TradeHistoryGrid() {
  const [page, setPage] = useState(1)
  const size = 20
  const [selected, setSelected] = useState<
    { orderNos: string[]; tradeDate?: string } | null
  >(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tradeHistory', page],
    retry: 1,
    queryFn: () => getTradeHistory({ page, size }),
  })

  const trades = data?.trades ?? []

  // cycle276 — 이 페이지의 **매수** 주문번호를 한 번에 조회한다.
  // 행마다 개별 조회하면 페이지당 20~30 요청이 나간다(명세 §10.3 · 뮤테이션 M19).
  const buyOrderNos = useMemo(
    () =>
      Array.from(
        new Set(
          trades
            .filter((t) => String(t.trade_type ?? '') === 'BUY')
            .map((t) => String(t.order_no ?? '').trim())
            .filter((no) => no !== ''),
        ),
      ),
    [trades],
  )
  const orderNosKey = buyOrderNos.join(',')

  const { data: summaries, isFetched: summariesFetched } = useQuery({
    queryKey: ['llmEvalSummaries', 'history', page, orderNosKey],
    retry: 1,
    enabled: buyOrderNos.length > 0,
    queryFn: () => getLlmEvaluationSummaries(buyOrderNos),
  })

  // 조회가 **끝났는가**(성공/실패 무관). 실패해도 표를 막지 않는다 — 관측 계층 하나가
  // 죽었다고 거래 내역을 못 보게 하면 그게 더 큰 사고다.
  const summariesReady = buyOrderNos.length === 0 || summariesFetched

  const columns = useMemo(
    () =>
      makeColumns(summaries ?? {}, summariesReady, (orderNo, tradeDate) =>
        setSelected({ orderNos: [orderNo], tradeDate }),
      ),
    [summaries, summariesReady],
  )

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
