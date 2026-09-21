/**
 * cycle285 (2026-09-13) — 장운영상태 화면 신규 섹션 B "오늘 야간작업".
 *
 * `GET /api/market-ops`(백엔드 `src/routes/market_ops.py`) 응답을 시각순 타임라인으로
 * 보여준다. 예정 시각은 전부 `scheduler.TIME_*`(+ 보조계좌 토큰은
 * `quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH`)에서 라우트가 읽어 보낸 문자열이다 —
 * **이 파일에는 시각 리터럴이 없다**(§4-1, cycle282 FE19 가드가 `components/MarketState*.tsx`
 * 이름 규약으로 이 파일도 함께 감시한다). 조회는 페이지가 하고 이 컴포넌트는 순수 표현이다.
 *
 * ## 상태 어휘 10종을 있는 그대로 보여준다
 *
 * 마커가 영구 결측인 작업(`quote_token_refresh`·`evening_funnel_capture`·
 * `stock_master_daily_purge`·`full_universe_load`)은 시각이 지나도 `failed` 가 아니라
 * `unknown` 이다 — 없는 증거를 실패로 위장하지 않는다(백엔드 계약, 라우트 docstring).
 * `overwritten` 은 20:05 metrics 1차 스냅샷을 21:30 정산 완전판이 정상적으로 덮어썼다는
 * 뜻이라 **결함이 아니다** — 그래서 `failed` 와 다른 색을 쓴다.
 */
import { formatKstDateTime } from '../utils/kst'
import type { MarketOpsData, MarketOpsTask } from '../types/market-ops'
import ScrollPane from './ScrollPane'

const STATUS_META: Record<string, { label: string; className: string }> = {
  scheduled: { label: '예정', className: 'bg-gray-200 text-gray-700 border-gray-300' },
  running: {
    label: '진행중',
    className: 'bg-sky-200 text-sky-900 border-sky-400 animate-pulse',
  },
  done: { label: '완료', className: 'bg-blue-100 text-blue-800 border-blue-300' },
  overwritten: {
    label: '완료(최종반영)',
    className: 'bg-blue-100 text-blue-800 border-blue-300',
  },
  failed: { label: '실패', className: 'bg-red-200 text-red-900 border-red-400' },
  skipped_fresh: {
    label: '건너뜀(신선)',
    className: 'bg-beige-200 text-brown-800 border-beige-400',
  },
  skipped_weekly: {
    label: '건너뜀(주1회)',
    className: 'bg-beige-200 text-brown-800 border-beige-400',
  },
  // cycle285 검증(honest #5) 시정 — brown-200 이 실패(red-200)와 sRGB 배경 거리
  // ≈16.3(리포 임계 25 미만)로 근접해 "미발화"·"실패" 가 나란히 있으면 점선 테두리와
  // 라벨 두 글자로만 갈렸다. 채도를 빼 gray 계열로 옮겨 거리를 크게 벌린다 —
  // 점선 테두리는 "증거 자체가 없다" 는 의미를 그대로 유지한다.
  not_fired: {
    label: '미발화',
    className: 'bg-gray-300 text-gray-800 border-gray-500 border-dashed',
  },
  // 정확히 '휴장' 한 단어는 cycle282 FE19 가 표의 행 이름으로 예약한 금지어라
  // '휴장일' 을 쓴다(같은 페이지의 개장일 배지가 이미 그 표기를 쓴다).
  holiday: { label: '휴장일', className: 'bg-gray-100 text-gray-500 border-gray-300' },
  // text-gray-400 on bg-gray-50 은 대비 2.56:1 로 WCAG AA(4.5:1) 미달이었다(honest
  // #5) — `quote_token_refresh`/`stock_master_daily_purge` 처럼 영구 표시되는
  // 라벨이라 text-gray-600 으로 올린다.
  unknown: { label: '확인 불가', className: 'bg-gray-50 text-gray-600 border-gray-300' },
}

const FALLBACK_META = { label: '알 수 없음', className: 'bg-gray-50 text-gray-600 border-gray-300' }

/** 아직 안 온 일(`scheduled`)은 흐리게 — 지난 일과 한눈에 구분한다. 시각을 직접 재는
 *  대신 백엔드가 이미 시간을 반영해 계산해 준 상태값에만 의존한다(FE20 — `new Date(`
 *  이 파일에 0건). */
const ROW_MUTED_STATUSES = new Set(['scheduled'])
const ROW_ACTIVE_STATUSES = new Set(['running'])

/** 자유 `evidence` 사전의 알려진 키에만 한글 라벨을 붙인다. 모르는 키는 원문 그대로 —
 *  백엔드가 evidence 키를 늘려도 화면이 그 값을 숨기지 않는다(열린 렌더). */
const EVIDENCE_LABELS: Record<string, string> = {
  total: '총계',
  processed: '처리',
  updated: '갱신',
  skipped: '건너뜀',
  failed: '실패',
  elapsed_ms: '소요(ms)',
  error_message: '오류',
  refreshed_at: '갱신시각',
  master_raw_updated_at: '마스터파일 갱신시각',
  retention_tail: '보관 시작일',
  snapshot_rows_today: '오늘 스냅샷 행수',
  recommendation_rows_today: '오늘 자문 행수',
  daily_head: '최신 봉 날짜',
  daily_rows_today: '오늘 봉 행수',
  daily_performance_rows_today: '오늘 정산 행수',
  model: '모델',
  has_api_metrics: 'API지표 포함',
  ext_provider: '외부 제공자',
  ext_model: '외부 모델',
}

function formatEvidenceValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  return String(value)
}

function EvidenceSummary({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence).filter(
    ([, value]) => value !== null && value !== undefined && value !== '',
  )
  if (entries.length === 0) {
    return <span className="text-xs text-gray-400">—</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 rounded bg-gray-50 px-1.5 py-0.5 text-[0.7rem] text-gray-600"
        >
          <span className="text-gray-400">{EVIDENCE_LABELS[key] ?? key}</span>
          <span className="font-mono text-gray-700">{formatEvidenceValue(value)}</span>
        </span>
      ))}
    </div>
  )
}

function TaskRow({ task }: { task: MarketOpsTask }) {
  const meta = STATUS_META[task.status] ?? FALLBACK_META
  const rowClass = ROW_ACTIVE_STATUSES.has(task.status)
    ? 'bg-sky-50 border-l-4 border-l-sky-500'
    : ROW_MUTED_STATUSES.has(task.status)
      ? 'opacity-60'
      : ''
  return (
    <tr
      data-testid={`market-state-ops-row-${task.id}`}
      data-status={task.status}
      className={`border-b border-gray-100 align-top ${rowClass}`}
    >
      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-500">
        {task.scheduled_at ?? '—'}
      </td>
      <td className="px-3 py-2 text-sm">
        <div className="font-medium text-gray-900">{task.label_ko}</div>
        {task.note ? (
          <div
            data-testid={`market-state-ops-note-${task.id}`}
            className="mt-0.5 max-w-[26rem] text-[0.7rem] leading-snug text-gray-500"
          >
            {task.note}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-2">
        <span
          data-testid={`market-state-ops-status-${task.id}`}
          data-status={task.status}
          className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${meta.className}`}
        >
          {meta.label}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-gray-500">
        {task.last_success_at ? formatKstDateTime(task.last_success_at) : '—'}
      </td>
      <td className="px-3 py-2">
        <EvidenceSummary evidence={task.evidence} />
      </td>
    </tr>
  )
}

// MarketStateNow.tsx 와 동일 관례 — 폴링 주기(30s)의 3배.
const STALE_AS_OF_SECS = 90

export function MarketStateOps({
  data,
  isLoading,
  isError,
}: {
  data: MarketOpsData | undefined
  isLoading: boolean
  isError: boolean
}) {
  // `Date.parse` 는 §4-1 가드가 세는 `new Date(` 패턴이 아니다 — 서버가 이미 KST
  // ISO(`+09:00`)로 보낸 값의 경과(초)만 재는 것이라 절대 시각 재구성이 아니다.
  const asOfAgoSecs = data?.as_of_kst
    ? Math.max(0, Math.floor((Date.now() - Date.parse(data.as_of_kst)) / 1000))
    : null
  const isStaleAsOf = asOfAgoSecs !== null && asOfAgoSecs > STALE_AS_OF_SECS

  return (
    <section data-testid="market-state-ops-section" className="rounded-lg bg-white p-4 shadow">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-gray-900">오늘 야간작업</h2>
        {asOfAgoSecs !== null ? (
          <span
            data-testid="market-state-ops-as-of-ago"
            data-stale={isStaleAsOf}
            className={`text-[0.65rem] ${isStaleAsOf ? 'font-medium text-brown-700' : 'text-gray-400'}`}
          >
            {isStaleAsOf
              ? `⚠️ ${asOfAgoSecs}초 전 값 — 갱신 지연 중`
              : `${asOfAgoSecs}초 전 갱신`}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-xs text-gray-500">
        매매 외 작업(적재·자문·정산·로그분석)의 오늘 진행 현황이다. 마커가 없는 작업은 산출물로
        판정하고, 그마저 없으면 "확인 불가" 로 남긴다 — 없는 증거를 실패로 보여주지 않는다.
        이 섹션은 관측 전용이며 여기서 재실행할 수 없다.
      </p>

      {isLoading ? (
        <div
          data-testid="market-state-ops-loading"
          className="mt-3 h-24 animate-pulse rounded bg-gray-100"
        />
      ) : isError || !data ? (
        <div
          data-testid="market-state-ops-error"
          className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
        >
          야간작업 현황 조회 실패 — 이 섹션만 비어 있다.
        </div>
      ) : (
        <>
          {data.is_trading_day === false ? (
            <div
              data-testid="market-state-ops-holiday-banner"
              className="mt-3 rounded border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-600"
            >
              오늘은 휴장일이다 — 야간작업이 발화하지 않는 것이 정상이다.
            </div>
          ) : null}

          {data.evidence_errors.length > 0 ? (
            <div
              data-testid="market-state-ops-evidence-errors"
              className="mt-3 rounded border border-beige-400 bg-beige-50 px-3 py-2 text-xs text-brown-700"
            >
              일부 데이터 소스 조회 실패({data.evidence_errors.join(', ')}) — 해당 작업의 값이
              비어 있을 수 있다.
            </div>
          ) : null}

          {data.tasks.length === 0 ? (
            <p className="mt-3 text-sm text-gray-400">표시할 작업이 없다.</p>
          ) : (
            <ScrollPane className="mt-3">
              <table data-testid="market-state-ops-table" className="min-w-full text-left">
                <thead>
                  <tr className="border-b border-gray-200 text-xs font-medium text-gray-500">
                    <th className="px-3 py-2">예정시각</th>
                    <th className="px-3 py-2">작업</th>
                    <th className="px-3 py-2">상태</th>
                    <th className="px-3 py-2">마지막성공</th>
                    <th className="px-3 py-2">요약수치</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tasks.map((task) => (
                    <TaskRow key={task.id} task={task} />
                  ))}
                </tbody>
              </table>
            </ScrollPane>
          )}

          <p
            data-testid="market-state-ops-heartbeat"
            className="mt-3 text-[0.7rem] text-gray-400"
          >
            엔진 하트비트{' '}
            {data.engine.heartbeat_at ? formatKstDateTime(data.engine.heartbeat_at) : '— (아직 없음)'}
          </p>
        </>
      )}
    </section>
  )
}

export default MarketStateOps
