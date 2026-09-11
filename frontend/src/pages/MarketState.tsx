/**
 * cycle282 (2026-09-11) — 장운영상태 화면.
 *
 * 사용자의 한 문장에서 나온 화면이다 — "현재 장운영상태와 함께 **어떤 호가유형을 쓸 수
 * 있는지** 알 수 있게 하자."
 *
 * ## 이 파일이 지키는 세 가지
 *
 * 1. **표와 커서는 한 응답에서 나온다.** 조회는 `useQuery` 하나뿐이다. 표를 따로, 커서를
 *    따로 부르면 자정·경계 순간에 둘이 갈라져 화면이 거짓말을 한다.
 * 2. **행·시각·코드를 하드코딩하지 않는다.** 이 파일에는 행 id도, 주문유형 코드도,
 *    거래소 이름도, 시각 문자열도 없다. 전부 응답 값을 보간해 그린다. 2026-09-14 에
 *    거래소 표가 실제로 바뀌는데, 화면이 값을 들고 있으면 그날부터 옛 표를 그린다.
 * 3. **커서는 서버가 판정한다.** 화면은 `rel`·`row_id`·`seconds_to_next` 를 받아 그릴 뿐,
 *    브라우저 로컬 시각으로 "지금 몇 번째 행인가" 를 재지 않는다(KST 강제 규약).
 *    클라이언트가 그리는 것은 **남은 시간 스톱워치** 하나뿐이고, 그마저 두 시각의
 *    *차이*(경과)만 쓴다 — 절대 시각은 다루지 않는다. 0 에 닿으면 다음 행을 스스로
 *    계산하지 않고 **재조회 1회**를 한다.
 *
 * ## 모르는 것은 숨기지 않는다
 *
 * 표에는 아직 확인하지 못한 칸이 있다(시가 단일가 시작 시각 · 넥스트레이드 정규장 시작 ·
 * 애프터 단일가의 주문유형 · 통합주문의 신규 코드 지원). 그 모름을 화면에서 지우면
 * "모른다" 가 "없다"/"된다" 로 바뀌어 전달된다. 그래서 확인 필요 배지와 3상태 셀
 * (지원 · 미확인 · 미지원)을 그대로 드러낸다.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchMarketState } from '../api/market-state'
import { formatKstDateTime } from '../utils/kst'
import type {
  MarketStateCursor,
  MarketStateData,
  MarketStateTableRow,
  OrderDivisionRow,
} from '../types/market-state'

// ── 표현 어휘 → 스타일 매핑 ────────────────────────────────────────────────
// 키는 응답 `vocab` 이 정의한 **표현 어휘**다. 표의 값(행 id·코드·시장명)과 달리
// 이 어휘는 화면이 알아도 되는 것들이다 — 색을 고르는 것이 화면의 일이기 때문이다.

const CONFIRMED = 'confirmed'
const REL_UNKNOWN = 'unknown'

const TONE_CLASS: Record<string, string> = {
  active: 'bg-sky-50 border-sky-300 text-sky-900',
  auction: 'bg-beige-100 border-beige-400 text-beige-900',
  fixed: 'bg-navy-50 border-navy-300 text-navy-900',
  break: 'bg-gray-100 border-gray-300 text-gray-600',
  closed: 'bg-gray-100 border-gray-300 text-gray-500',
  unknown: 'bg-gray-50 border-gray-200 text-gray-600',
}

const TONE_DOT_CLASS: Record<string, string> = {
  active: 'bg-sky-500',
  auction: 'bg-beige-500',
  fixed: 'bg-navy-500',
  break: 'bg-gray-400',
  closed: 'bg-gray-300',
  unknown: 'bg-gray-300',
}

/** 행 위치(지난/현재/동시/예정) → 표 행 스타일. 판정 자체는 서버가 한 것을 그대로 쓴다. */
const REL_ROW_CLASS: Record<string, string> = {
  past: 'opacity-50',
  current: 'bg-sky-50 border-l-4 border-l-sky-600 font-medium',
  concurrent: 'bg-beige-50 border-l-4 border-l-beige-500 border-dashed',
  upcoming: '',
  unknown: '',
}

const REL_LABEL: Record<string, string> = {
  past: '지남',
  current: '현재',
  concurrent: '동시',
  upcoming: '예정',
  unknown: '—',
}

/** 거래소 지원 3상태 — 미지원(빈칸)과 미확인(?)은 다른 것이다. */
const SUPPORT_GLYPH: Record<string, string> = {
  yes: '●',
  unknown: '?',
  no: '',
}

const SUPPORT_CLASS: Record<string, string> = {
  yes: 'text-sky-700 font-semibold',
  unknown: 'text-brown-600 font-semibold',
  no: 'text-gray-300',
}

const TRADING_DAY_LABEL: Record<string, string> = {
  true: '개장일',
  false: '휴장일',
  unknown: '확인 불가',
}

const TRADING_DAY_CLASS: Record<string, string> = {
  true: 'bg-sky-100 text-sky-800 border-sky-300',
  false: 'bg-gray-100 text-gray-700 border-gray-300',
  unknown: 'bg-beige-100 text-brown-700 border-beige-400',
}

const BASE_ROW_CLASS = 'border-b border-gray-100 align-top'
const CHIP_CLASS =
  'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs bg-gray-100 text-gray-700'
const PENDING_CHIP_CLASS =
  'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs bg-beige-100 text-brown-700 border border-beige-300'
const EXPIRED_CHIP_CLASS =
  'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs bg-gray-50 text-gray-400 line-through'
const WARN_BADGE_CLASS =
  'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-beige-100 text-brown-700 border border-beige-400'

// ── 순수 헬퍼 ──────────────────────────────────────────────────────────────

function toneClass(tone: string): string {
  return TONE_CLASS[tone] ?? TONE_CLASS[REL_UNKNOWN]
}

function toneDotClass(tone: string): string {
  return TONE_DOT_CLASS[tone] ?? TONE_DOT_CLASS[REL_UNKNOWN]
}

function relRowClass(rel: string): string {
  return `${BASE_ROW_CLASS} ${REL_ROW_CLASS[rel] ?? ''}`.trimEnd()
}

/**
 * 실패를 **안내**와 **오류** 둘로 가른다.
 *
 * 라우트는 네 갈래를 구분해 보낸다 — 다른 날짜에 유효한 행이 0 이면 404, `on_date` 형식·
 * 범위 위반이면 422, 오늘 표가 비었거나 leaf 가 예외를 내면 500, 그리고 연결 자체가
 * 끊기면 응답이 없다. 화면이 넷을 빨간 박스 하나로 뭉개면 "그 날짜엔 원래 행이 없다" 가
 * "서버가 고장났다" 로 읽힌다. cycle266(종목마스터 일봉 탭)이 404 안내와 500 오류를 같은
 * 문구로 보여 진짜 장애를 3개월 은폐한 그 실패가 바로 이 뭉갬이다.
 *
 * 404 만 안내다. 422 는 **우리가 보낸 값**이 틀렸다는 뜻이라 조용히 넘기면 안 되고,
 * 500·네트워크는 말할 것도 없다.
 */
const NOTICE_STATUS = 404

function httpStatusOf(error: unknown): number | null {
  const response = (error as { response?: { status?: unknown } } | null | undefined)?.response
  const status = response?.status
  return typeof status === 'number' ? status : null
}

/** 서버가 붙여 보낸 사유 문자열(있으면). 없으면 비운다 — 지어내지 않는다. */
function serverDetailOf(error: unknown): string {
  const response = (error as { response?: { data?: unknown } } | null | undefined)?.response
  const detail = (response?.data as { detail?: unknown } | null | undefined)?.detail
  return typeof detail === 'string' ? detail : ''
}

/**
 * 남은 시간 = `seconds_to_next − 경과`.
 *
 * **두 시각의 차이만 쓴다.** 로컬 시계의 절대값을 읽지 않으므로 브라우저/컨테이너 TZ 와
 * 무관하다(스톱워치이지 시계가 아니다).
 */
function remainingSeconds(secondsToNext: number | null, since: number): number | null {
  if (secondsToNext === null) return null
  const elapsed = Math.floor((Date.now() - since) / 1000)
  return Math.max(0, secondsToNext - elapsed)
}

function formatRemaining(total: number): string {
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours}시간`)
  if (hours > 0 || minutes > 0) parts.push(`${minutes}분`)
  parts.push(`${seconds}초`)
  return parts.join(' ')
}

function formatPeriod(from: string | null, to: string | null): string {
  if (from === null && to === null) return '상시'
  const left = from ?? '—'
  const right = to ?? '—'
  return `${left} ~ ${right}`
}

/** 응답 순서를 유지한 채 시장별 묶음으로 나눈다(표 행 순서 == 응답 순서 계약). */
function groupByMarket(
  rows: MarketStateTableRow[],
): { market: string; rows: MarketStateTableRow[] }[] {
  const groups: { market: string; rows: MarketStateTableRow[] }[] = []
  for (const row of rows) {
    const last = groups[groups.length - 1]
    if (last && last.market === row.market) last.rows.push(row)
    else groups.push({ market: row.market, rows: [row] })
  }
  return groups
}

// ── 조각 컴포넌트 ──────────────────────────────────────────────────────────

function DivisionChip({
  testId,
  code,
  name,
  className,
  suffix,
  title,
}: {
  testId: string
  code: string
  name: string
  className: string
  suffix?: string
  title?: string
}) {
  return (
    <span data-testid={testId} className={className} title={title}>
      <span className="font-mono">{code}</span>
      <span>{name}</span>
      {suffix ? <span className="text-[0.65rem] opacity-80">{suffix}</span> : null}
    </span>
  )
}

function Countdown({
  market,
  cursor,
  since,
}: {
  market: string
  cursor: MarketStateCursor
  since: number
}) {
  const remaining = remainingSeconds(cursor.seconds_to_next, since)
  if (remaining === null) {
    return <div className="text-sm font-medium text-gray-500">오늘 장 종료</div>
  }
  return (
    <div
      data-testid={`market-state-card-countdown-${market}`}
      data-seconds={String(remaining)}
      className="text-sm font-semibold text-gray-900"
    >
      {formatRemaining(remaining)} 남음
    </div>
  )
}

function MarketCard({
  market,
  cursor,
  data,
  since,
}: {
  market: string
  cursor: MarketStateCursor
  data: MarketStateData
  since: number
}) {
  const divisions = useMemo(() => {
    const map = new Map<string, OrderDivisionRow>()
    for (const division of data.order_divisions) map.set(division.code, division)
    return map
  }, [data.order_divisions])

  const phaseLabel =
    data.phases.find((phase) => phase.id === cursor.phase)?.label_ko ?? cursor.name_ko
  const nextRow = data.table.find((row) => row.row_id === cursor.next_row_id)
  const nextPhaseLabel = data.phases.find((phase) => phase.id === cursor.next_phase)?.label_ko
  const nextLabel = nextRow?.name_ko ?? nextPhaseLabel ?? '—'
  const rowsById = useMemo(() => {
    const map = new Map<string, MarketStateTableRow>()
    for (const row of data.table) map.set(row.row_id, row)
    return map
  }, [data.table])

  return (
    <section
      data-testid={`market-state-card-${market}`}
      data-phase={cursor.phase}
      data-tone={cursor.tone}
      className={`rounded-lg border p-4 shadow-sm ${toneClass(cursor.tone)}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium opacity-70">{cursor.market_label_ko}</div>
          <div
            data-testid={`market-state-card-name-${market}`}
            className="mt-0.5 flex items-center gap-2 text-xl font-bold"
          >
            <span className={`h-2.5 w-2.5 rounded-full ${toneDotClass(cursor.tone)}`} />
            {cursor.name_ko}
          </div>
          <div className="mt-1 text-xs opacity-75">
            {phaseLabel} · {cursor.match_ko}
          </div>
        </div>
        <div className="text-right">
          <Countdown market={market} cursor={cursor} since={since} />
          <div
            data-testid={`market-state-card-next-${market}`}
            className="mt-1 text-xs opacity-75"
          >
            다음 · {nextLabel}
            {cursor.next_boundary ? ` (${cursor.next_boundary})` : ''}
          </div>
        </div>
      </div>

      <div
        data-testid={`market-state-card-window-${market}`}
        className="mt-3 font-mono text-sm opacity-80"
      >
        {cursor.window ? `${cursor.window.start} ~ ${cursor.window.end}` : '—'}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span
          data-testid={`market-state-card-market-order-${market}`}
          data-ok={String(cursor.market_order_ok)}
          className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium border ${
            cursor.market_order_ok
              ? 'bg-sky-100 text-sky-800 border-sky-300'
              : 'bg-red-100 text-red-800 border-red-300'
          }`}
        >
          시장가 주문 {cursor.market_order_ok ? '가능' : '불가'}
        </span>
        <span
          data-testid={`market-state-card-can-order-${market}`}
          data-ok={String(cursor.can_order)}
          className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium border ${
            cursor.can_order
              ? 'bg-gray-100 text-gray-700 border-gray-300'
              : 'bg-beige-100 text-brown-700 border-beige-400'
          }`}
        >
          주문 접수 {cursor.can_order ? '가능' : cursor.is_open ? '유형 확인 필요' : '불가'}
        </span>
        {cursor.confidence !== CONFIRMED ? (
          <span
            data-testid={`market-state-card-confidence-${market}`}
            data-level={cursor.confidence}
            className={WARN_BADGE_CLASS}
            title={cursor.confidence_notes.join('\n')}
            aria-label={cursor.confidence_notes.join(' ')}
          >
            확인 필요
          </span>
        ) : null}
      </div>

      {cursor.confidence_notes.length > 0 ? (
        <ul className="mt-2 space-y-0.5 text-xs opacity-80">
          {cursor.confidence_notes.map((note) => (
            <li key={note}>· {note}</li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3">
        <div className="text-xs font-medium opacity-70">지금 쓸 수 있는 주문유형</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {cursor.order_divisions.length === 0 ? (
            <span className="text-xs opacity-60">없음</span>
          ) : (
            cursor.order_divisions.map((code) => (
              <DivisionChip
                key={code}
                testId={`market-state-card-division-${market}-${code}`}
                code={code}
                name={divisions.get(code)?.name_ko ?? ''}
                className={CHIP_CLASS}
                title={divisions.get(code)?.note || undefined}
              />
            ))
          )}
        </div>
      </div>

      {cursor.concurrent_row_ids.length > 0 ? (
        <div className="mt-3">
          <div className="text-xs font-medium opacity-70">동시에 열려 있는 창</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {cursor.concurrent_row_ids.map((rowId) => (
              <span
                key={rowId}
                data-testid={`market-state-card-concurrent-${market}-${rowId}`}
                className="inline-flex items-center gap-1 rounded border border-beige-400 bg-beige-50 px-1.5 py-0.5 text-xs text-brown-700"
              >
                <span className="font-mono">{rowId}</span>
                <span>{rowsById.get(rowId)?.name_ko ?? ''}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function TableRow({
  row,
  divisions,
}: {
  row: MarketStateTableRow
  divisions: Map<string, OrderDivisionRow>
}) {
  const nameOf = (code: string) => divisions.get(code)?.name_ko ?? ''
  return (
    <tr
      data-testid={`market-state-row-${row.row_id}`}
      data-rel={row.rel}
      data-market={row.market}
      data-confidence={row.confidence}
      className={relRowClass(row.rel)}
    >
      <td className="px-3 py-2 font-mono text-xs text-gray-500">{row.row_id}</td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-700">
        {row.start} ~ {row.end}
      </td>
      <td className="px-3 py-2 text-sm">
        <span className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 shrink-0 rounded-full ${toneDotClass(row.tone)}`} />
          <span className="font-medium text-gray-900">{row.name_ko}</span>
        </span>
        <span className="ml-2 text-[0.7rem] text-gray-400">{REL_LABEL[row.rel] ?? ''}</span>
      </td>
      <td className="px-3 py-2 text-xs text-gray-600">{row.match_ko}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {row.order_divisions.length === 0 && row.order_divisions_pending.length === 0 ? (
            <span className="text-xs text-gray-400">없음</span>
          ) : null}
          {row.order_divisions.map((code) => (
            <DivisionChip
              key={code}
              testId={`market-state-row-division-${row.row_id}-${code}`}
              code={code}
              name={nameOf(code)}
              className={CHIP_CLASS}
            />
          ))}
          {row.order_divisions_pending.map((code) => (
            <DivisionChip
              key={code}
              testId={`market-state-row-pending-${row.row_id}-${code}`}
              code={code}
              name={nameOf(code)}
              className={PENDING_CHIP_CLASS}
              suffix="(시행일부터)"
              title={divisions.get(code)?.note || undefined}
            />
          ))}
          {row.order_divisions_expired.map((code) => (
            <DivisionChip
              key={code}
              testId={`market-state-row-expired-${row.row_id}-${code}`}
              code={code}
              name={nameOf(code)}
              className={EXPIRED_CHIP_CLASS}
              suffix="(폐지)"
            />
          ))}
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-500">
        {formatPeriod(row.effective_from, row.effective_to)}
      </td>
      <td className="px-3 py-2">
        {row.confidence !== CONFIRMED ? (
          <span className={WARN_BADGE_CLASS} title={row.note}>
            확인 필요
          </span>
        ) : (
          <span className="text-xs text-gray-400">—</span>
        )}
        {row.note ? (
          <div
            data-testid={`market-state-row-note-${row.row_id}`}
            className="mt-1 max-w-[22rem] text-[0.7rem] leading-snug text-gray-500"
          >
            {row.note}
          </div>
        ) : null}
      </td>
    </tr>
  )
}

// ── 페이지 ─────────────────────────────────────────────────────────────────

export default function MarketState() {
  const { data, error, isLoading, isError, refetch, dataUpdatedAt, isFetching } = useQuery({
    queryKey: ['market-state'],
    queryFn: () => fetchMarketState(),
    refetchInterval: 30_000,
    retry: 1,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })

  // 1초 심장박동 — 남은 시간만 다시 그린다. 행 판정은 여기서 하지 않는다.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000)
    return () => window.clearInterval(id)
  }, [])

  const divisions = useMemo(() => {
    const map = new Map<string, OrderDivisionRow>()
    for (const division of data?.order_divisions ?? []) map.set(division.code, division)
    return map
  }, [data])

  // 가장 먼저 닿는 경계까지의 남은 초. 여러 시장이 각자 경계를 가지므로 최솟값으로 본다.
  const nearestSeconds = useMemo(() => {
    const markets = data?.markets
    if (!markets) return null
    const values = Object.values(markets)
      .map((cursor) => cursor.seconds_to_next)
      .filter((value): value is number => value !== null)
    return values.length > 0 ? Math.min(...values) : null
  }, [data])

  // `nearestSeconds > 0` 조건이 방어다 — 서버가 0 을 보내면(이론상 올림이라 없다) 재조회가
  // 곧바로 다시 0 을 받아 폭주한다. 그 경우는 30초 폴링이 데려간다.
  const boundaryReached =
    nearestSeconds !== null &&
    nearestSeconds > 0 &&
    remainingSeconds(nearestSeconds, dataUpdatedAt) === 0

  // 경계에 닿으면 **다음 행을 스스로 계산하지 않고** 서버에 다시 묻는다. 응답 1건당 딱 한 번
  // (그러지 않으면 1초 심장박동마다 재조회가 터진다).
  const refetchedForRef = useRef<number | null>(null)
  useEffect(() => {
    if (!boundaryReached) return
    if (refetchedForRef.current === dataUpdatedAt) return
    refetchedForRef.current = dataUpdatedAt
    void refetch()
  }, [boundaryReached, dataUpdatedAt, refetch])

  if (isLoading) {
    return (
      <div data-testid="market-state-loading" className="rounded-lg bg-white p-8 shadow">
        <div className="h-6 w-1/3 animate-pulse rounded bg-gray-200" />
        <div className="mt-4 space-y-2">
          <div className="h-4 animate-pulse rounded bg-gray-100" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-gray-100" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    const status = httpStatusOf(error)
    const detail = serverDetailOf(error)
    const notice = status === NOTICE_STATUS
    return (
      <div
        data-testid={notice ? 'market-state-notice' : 'market-state-error'}
        data-status={status === null ? '' : String(status)}
        className={
          notice
            ? 'rounded-lg border border-beige-400 bg-beige-50 p-6 text-brown-800'
            : 'rounded-lg border border-red-300 bg-red-50 p-6 text-red-800'
        }
      >
        <div className="font-semibold">
          {notice ? '표시할 행이 없다' : '장운영상태를 불러오지 못했다'}
        </div>
        <p className="mt-1 text-sm">
          {notice
            ? '요청한 날짜에는 유효한 장 운영 행이 없다. 서버 장애가 아니라 그 날짜에 해당 구간이 존재하지 않는다는 뜻이다.'
            : '서버 연결이 끊겼거나 표 데이터에 결함이 있다. 빈 화면으로 덮지 않고 그대로 알린다.'}
        </p>
        {detail ? (
          <p
            data-testid="market-state-failure-detail"
            className="mt-1 font-mono text-xs opacity-70"
          >
            {detail}
          </p>
        ) : null}
        <button
          type="button"
          data-testid="market-state-retry"
          onClick={() => void refetch()}
          className={
            notice
              ? 'mt-3 rounded border border-beige-500 bg-white px-3 py-1.5 text-sm font-medium text-brown-700 hover:bg-beige-100'
              : 'mt-3 rounded border border-red-400 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100'
          }
        >
          다시 시도
        </button>
      </div>
    )
  }

  const tradingDayKey = data.is_trading_day === null ? REL_UNKNOWN : String(data.is_trading_day)
  const groups = groupByMarket(data.table)

  return (
    <div data-testid="market-state-page" className="space-y-6">
      {/* 헤더 */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">장운영상태</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <span data-testid="market-state-asof" className="font-mono">
              {formatKstDateTime(data.as_of_kst)}
            </span>
            <span>·</span>
            <span className="font-mono">{data.on_date}</span>
            <span
              data-testid="market-state-trading-day-badge"
              data-value={tradingDayKey}
              className={`inline-flex items-center rounded border px-1.5 py-0.5 font-medium ${
                TRADING_DAY_CLASS[tradingDayKey] ?? TRADING_DAY_CLASS[REL_UNKNOWN]
              }`}
              title={data.trading_day_source}
            >
              {TRADING_DAY_LABEL[tradingDayKey] ?? TRADING_DAY_LABEL[REL_UNKNOWN]}
            </span>
            <span className="text-gray-400">표 {data.table_version}</span>
          </div>
        </div>
        <button
          type="button"
          data-testid="market-state-refresh"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          새로고침
        </button>
      </header>

      {/* 미리보기 배너 — 다른 날짜를 보는 중에는 "지금" 커서를 그리지 않는다 */}
      {data.preview ? (
        <div
          data-testid="market-state-preview-banner"
          className="rounded-lg border border-beige-400 bg-beige-50 p-3 text-sm text-brown-800"
        >
          <span className="font-semibold">미리보기</span> · 다른 날짜(
          <span className="font-mono">{data.on_date}</span>)의 표를 보는 중이라 현재 상태 카드는
          표시하지 않는다. 커서는 "지금" 에만 의미가 있다.
          {data.cursor_disabled_reason ? (
            <span className="ml-1 font-mono text-xs opacity-70">
              ({data.cursor_disabled_reason})
            </span>
          ) : null}
        </div>
      ) : null}

      {/* (1) 현재 상태 카드 */}
      {data.markets ? (
        <div className="grid gap-4 md:grid-cols-2">
          {data.market_order.map((market) => {
            const cursor = data.markets?.[market]
            if (!cursor) return null
            return (
              <MarketCard
                key={market}
                market={market}
                cursor={cursor}
                data={data}
                since={dataUpdatedAt}
              />
            )
          })}
        </div>
      ) : null}

      {/* (2) 커서 표 */}
      <section className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-semibold text-gray-900">장 운영 시간표</h2>
        <p className="mt-1 text-xs text-gray-500">
          그 날짜에 유효한 행만 보인다. 현재 행에 커서가 서고, 지난 행은 흐리게, 동시에 열린
          창은 점선으로 표시한다. 위치 판정은 서버가 한다.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table data-testid="market-state-table" className="min-w-full text-left">
            <thead>
              <tr className="border-b border-gray-200 text-xs font-medium text-gray-500">
                <th className="px-3 py-2">행</th>
                <th className="px-3 py-2">시간대</th>
                <th className="px-3 py-2">상태</th>
                <th className="px-3 py-2">체결</th>
                <th className="px-3 py-2">주문유형</th>
                <th className="px-3 py-2">유효기간</th>
                <th className="px-3 py-2">확신</th>
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.market}>
                <tr className="bg-gray-50">
                  <td
                    colSpan={7}
                    className="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-600"
                  >
                    {group.market}
                  </td>
                </tr>
                {group.rows.map((row) => (
                  <TableRow key={row.row_id} row={row} divisions={divisions} />
                ))}
              </tbody>
            ))}
          </table>
        </div>
      </section>

      {/* (3) 주문유형 카탈로그 */}
      <section className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-semibold text-gray-900">주문유형 카탈로그</h2>
        <p className="mt-1 text-xs text-gray-500">
          ● 지원 · ? 확인 필요 · 빈칸 미지원. 확인하지 못한 칸을 미지원으로 접지 않는다 —
          "모른다" 와 "안 된다" 는 다른 말이다.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table data-testid="market-state-catalog" className="min-w-full text-left">
            <thead>
              <tr className="border-b border-gray-200 text-xs font-medium text-gray-500">
                <th className="px-3 py-2">코드</th>
                <th className="px-3 py-2">이름</th>
                <th className="px-3 py-2">묶음</th>
                {data.exchange_order.map((exchange) => (
                  <th key={exchange} className="px-3 py-2 text-center">
                    {exchange}
                  </th>
                ))}
                <th className="px-3 py-2">유효기간</th>
                <th className="px-3 py-2">비고</th>
              </tr>
            </thead>
            <tbody>
              {data.order_divisions.map((division) => (
                <tr
                  key={division.code}
                  data-testid={`market-state-catalog-row-${division.code}`}
                  data-confidence={division.confidence}
                  className="border-b border-gray-100"
                >
                  <td className="px-3 py-1.5 font-mono text-xs text-gray-700">{division.code}</td>
                  <td className="px-3 py-1.5 text-sm text-gray-900">
                    {division.name_ko}
                    {division.confidence !== CONFIRMED ? (
                      <span className="ml-1 text-[0.7rem] text-brown-600">확인 필요</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-gray-500">{division.group_ko ?? '—'}</td>
                  {data.exchange_order.map((exchange) => {
                    const support = division.exchange_support[exchange]
                    return (
                      <td
                        key={exchange}
                        data-testid={`market-state-catalog-cell-${division.code}-${exchange}`}
                        data-support={support}
                        className={`px-3 py-1.5 text-center text-sm ${
                          SUPPORT_CLASS[support] ?? SUPPORT_CLASS[REL_UNKNOWN]
                        }`}
                      >
                        {SUPPORT_GLYPH[support] ?? ''}
                      </td>
                    )
                  })}
                  <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs text-gray-500">
                    {formatPeriod(division.effective_from, division.effective_to)}
                  </td>
                  <td className="px-3 py-1.5 text-[0.7rem] leading-snug text-gray-500">
                    {division.note}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 표가 드러낸 것 */}
        <div className="mt-4 space-y-2">
          {data.findings.map((finding, index) => (
            <div
              key={finding}
              data-testid={`market-state-finding-${index}`}
              className="rounded border-l-4 border-l-red-500 bg-red-50 px-3 py-2 text-sm text-red-900"
            >
              {finding}
            </div>
          ))}
        </div>
      </section>

      {/* (4) 바닥 — 보드와 장 상태는 다른 것이다 */}
      <footer className="space-y-2 text-xs leading-relaxed text-gray-500">
        <p data-testid="market-state-board-note" className="rounded bg-gray-50 px-3 py-2">
          {data.board_note}
        </p>
        <p data-testid="market-state-unconfirmed-note" className="rounded bg-beige-50 px-3 py-2">
          {data.unconfirmed_note}
        </p>
      </footer>
    </div>
  )
}
