/**
 * RS·재무 관찰 — 전략 메뉴 세 번째 세부(2026-10-15 사용자 결정 「전략 밑에 두자」).
 *
 * 매일 아침 부팅 때 4전략(donchian·VCP·kojiro·etf_trend)의 후보·보유 종목마다 남기는 RS(상대강도)·재무·
 * 목표가 점수 기록(`candidate_score_snapshots`)을 날짜·전략별로 보인다. 데이터 = `GET /api/rs-observe`.
 *
 * 🔴 관찰 전용 — 매매에 쓰이지 않는다(상단 띠). 「모름」(null)은 0 이 아니라 `—` 다(`utils/rsObserve.ts`).
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRsObserve } from '../api/rs-observe'
import ScrollPane from '../components/ScrollPane'
import type { RsObserveRow } from '../types/rs-observe'
import { formatKstDateTime } from '../utils/kst'
import { pnlColorClass } from '../utils/pnlColor'
import {
  fmtBool,
  fmtInt,
  fmtPercent,
  fmtQuarter,
  fmtRatioPct,
  fmtSector,
  signOf,
  sortRows,
  toNum,
} from '../utils/rsObserve'
import { strategyLabel } from '../utils/strategyMeta'

const BOX = 'bg-white rounded-lg shadow p-4 mb-4'
const ALL = 'all'

type Tone = 'sign' | 'none'

interface Column {
  key: keyof RsObserveRow
  label: string
  title: string
  fmt: (v: unknown) => string
  tone: Tone
  group: 'rs' | 'target' | 'fin'
}

const COLUMNS: Column[] = [
  { key: 'rs_pct', label: 'RS 백분위', title: '전 종목 중 상대강도 순위(0~99, 높을수록 강함)', fmt: fmtInt, tone: 'none', group: 'rs' },
  { key: 'rs_raw', label: 'RS 수익', title: '3·6·9개월 수익률 가중합(0.4·0.3·0.3)', fmt: (v) => fmtRatioPct(v), tone: 'sign', group: 'rs' },
  { key: 'sector_key', label: '섹터', title: 'KIS 업종명(2026-10-16 기록부터). 그 전 기록은 업종 대분류 코드라 「옛 기준」 으로 표시', fmt: fmtSector, tone: 'none', group: 'rs' },
  { key: 'vs_sector', label: '섹터 대비', title: '같은 섹터 평균 RS 수익과의 차이', fmt: (v) => fmtRatioPct(v), tone: 'sign', group: 'rs' },
  { key: 'sector_pct', label: '섹터 백분위', title: '섹터 평균 RS 끼리 비교한 그 섹터의 백분위 (0~99, 99 = 가장 강한 섹터)', fmt: fmtInt, tone: 'none', group: 'rs' },
  { key: 'in_sector_pct', label: '섹터 내 백분위', title: '같은 섹터 안에서 이 종목의 백분위 (0~99, 99 = 섹터 1등)', fmt: fmtInt, tone: 'none', group: 'rs' },
  { key: 'revision_breadth', label: '목표가 상향 폭', title: '최근 60영업일 (상향 증권사 − 하향 증권사) ÷ 의견 낸 증권사', fmt: (v) => fmtRatioPct(v, 0), tone: 'sign', group: 'target' },
  { key: 'target_median_change', label: '목표가 중앙 변화', title: '증권사별 직전 대비 목표가 변화율의 중앙값', fmt: (v) => fmtRatioPct(v), tone: 'sign', group: 'target' },
  { key: 'opinion_brokers', label: '증권사 수', title: '최근 60영업일 안에 의견을 낸 증권사 수', fmt: fmtInt, tone: 'none', group: 'target' },
  { key: 'fin_quarter', label: '기준 분기', title: '그날 알 수 있던 가장 최근 분기(결산월)', fmt: fmtQuarter, tone: 'none', group: 'fin' },
  { key: 'op_turnaround', label: '영업이익 흑자전환', title: '1년 전 같은 분기 적자(≤0) → 이번 분기 흑자', fmt: fmtBool, tone: 'none', group: 'fin' },
  { key: 'op_yoy_growth', label: '영업이익 YoY', title: '1년 전 같은 분기 대비 영업이익 증가율(전년 흑자일 때만)', fmt: (v) => fmtRatioPct(v), tone: 'sign', group: 'fin' },
  { key: 'revenue_yoy_growth', label: '매출 YoY', title: '1년 전 같은 분기 대비 매출 증가율', fmt: (v) => fmtRatioPct(v), tone: 'sign', group: 'fin' },
  { key: 'net_turnaround', label: '순이익 흑자전환', title: '1년 전 같은 분기 적자 → 이번 분기 흑자', fmt: fmtBool, tone: 'none', group: 'fin' },
  { key: 'roe', label: 'ROE', title: '자기자본이익률(종목마스터 값)', fmt: (v) => fmtPercent(v), tone: 'none', group: 'fin' },
  { key: 'debt_ratio_latest', label: '부채비율', title: '가장 최근 연간 부채비율', fmt: (v) => fmtPercent(v, 0), tone: 'none', group: 'fin' },
  { key: 'debt_ratio_down_years', label: '부채비율 감소', title: '최근 3개 연도 중 부채비율이 줄어든 횟수', fmt: fmtInt, tone: 'none', group: 'fin' },
  { key: 'ttm_op_to_max_ratio', label: 'TTM 영업이익/최고', title: '최근 4분기 합 영업이익 ÷ 과거 최고 4분기 합', fmt: (v) => fmtRatioPct(v, 0), tone: 'none', group: 'fin' },
]

function cellClass(col: Column, value: unknown): string {
  if (col.tone !== 'sign') return 'text-gray-800'
  const n = signOf(value)
  return n === null ? 'text-gray-400' : pnlColorClass(n)
}

function StrategySection({ sid, rows }: { sid: string; rows: RsObserveRow[] }) {
  const sorted = useMemo(() => sortRows(rows), [rows])
  const held = rows.filter((r) => r.role === 'held').length
  const population = rows.map((r) => toNum(r.rs_population)).find((n) => n !== null) ?? null
  const computedAt = rows[0]?.computed_at ?? null
  return (
    <section className={BOX} data-testid={`rs-observe-section-${sid}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <h2 className="text-base font-semibold text-gray-900">{strategyLabel(sid)}</h2>
        <div className="text-xs text-gray-500" data-testid={`rs-observe-summary-${sid}`}>
          {`후보 ${rows.length - held} · 보유 ${held} · RS 모집단 ${population === null ? '—' : population.toLocaleString('ko-KR')}종목`}
          {computedAt ? ` · 계산 ${formatKstDateTime(computedAt)}` : ''}
        </div>
      </div>
      {sid === 'etf_trend' && (
        <p className="text-xs text-gray-500 mb-2" data-testid="rs-observe-etf-note">
          ETF 는 재무·목표가 칸이 없습니다(—). RS 는 전 종목과 같은 기준으로 매깁니다.
        </p>
      )}
      {rows.length === 0 ? (
        <p className="text-sm text-gray-500" data-testid={`rs-observe-section-empty-${sid}`}>
          이 날짜에 이 전략의 기록이 없습니다.
        </p>
      ) : (
        <ScrollPane data-testid={`rs-observe-table-${sid}`}>
          <table className="min-w-[1400px] w-full text-xs whitespace-nowrap">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-2 py-1 text-left" rowSpan={2}>종목</th>
                <th className="px-2 py-1 text-left" rowSpan={2}>구분</th>
                <th className="px-2 py-1 text-center border-l" colSpan={6}>상대강도(RS)</th>
                <th className="px-2 py-1 text-center border-l" colSpan={3}>증권사 목표가</th>
                <th className="px-2 py-1 text-center border-l" colSpan={9}>재무</th>
              </tr>
              <tr>
                {COLUMNS.map((c, i) => (
                  <th
                    key={c.key}
                    title={c.title}
                    className={`px-2 py-1 text-right font-medium ${i === 0 || COLUMNS[i - 1].group !== c.group ? 'border-l' : ''}`}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.ticker} className="border-t" data-testid={`rs-observe-row-${sid}-${r.ticker}`}>
                  <td className="px-2 py-1 text-left">
                    <span className="text-gray-900">{r.name || r.ticker}</span>
                    <span className="ml-1 text-gray-400">{r.ticker}</span>
                  </td>
                  <td className="px-2 py-1 text-left">
                    {r.role === 'held' ? (
                      <span className="px-1.5 py-0.5 rounded bg-navy-100 text-navy-800">보유</span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">후보</span>
                    )}
                  </td>
                  {COLUMNS.map((c, i) => (
                    <td
                      key={c.key}
                      data-key={c.key}
                      className={`px-2 py-1 text-right tabular-nums ${cellClass(c, r[c.key])} ${i === 0 || COLUMNS[i - 1].group !== c.group ? 'border-l' : ''}`}
                    >
                      {c.fmt(r[c.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollPane>
      )}
    </section>
  )
}

export default function RsObserve() {
  const [date, setDate] = useState<string | null>(null)
  const [strategy, setStrategy] = useState<string>(ALL)
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['rsObserve', date],
    queryFn: () => getRsObserve(date),
    staleTime: 60_000,
    retry: 1,
  })

  const header = (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-3">RS·재무 관찰</h1>
      <div
        className="mb-4 rounded border border-beige-300 bg-beige-50 px-3 py-2 text-sm text-beige-900"
        data-testid="rs-observe-banner"
      >
        관찰 전용 — 매매에 쓰이지 않습니다. 매일 아침 부팅 때 후보·보유 종목의 점수를 기록하고, 2027-04 사전 등록
        기준으로 쓸모를 판정할 예정입니다. 빈 칸(—)은 0 이 아니라 「모름」입니다.
      </div>
    </>
  )

  if (isLoading) {
    return (
      <div>
        {header}
        <div className="text-sm text-gray-500" data-testid="rs-observe-loading">불러오는 중...</div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div>
        {header}
        <div className="text-sm text-red-700" data-testid="rs-observe-error">
          RS·재무 관찰 기록을 불러오지 못했습니다.{' '}
          <button type="button" className="underline" onClick={() => refetch()} data-testid="rs-observe-retry">
            다시 시도
          </button>
        </div>
      </div>
    )
  }
  if (!data.success || !data.data) {
    return (
      <div>
        {header}
        <div className="text-sm text-red-700" data-testid="rs-observe-failed">
          {data.message || 'RS·재무 관찰 기록을 불러오지 못했습니다.'}
        </div>
      </div>
    )
  }

  const d = data.data
  if (!d.target_date) {
    return (
      <div>
        {header}
        <p className="text-sm text-gray-500" data-testid="rs-observe-empty">
          아직 기록이 없습니다 — 매일 아침 부팅 때 남깁니다.
        </p>
      </div>
    )
  }

  const byStrategy = new Map<string, RsObserveRow[]>(d.strategies.map((s) => [s, []]))
  for (const r of d.rows) {
    const list = byStrategy.get(r.strategy_id)
    if (list) list.push(r)
    else byStrategy.set(r.strategy_id, [r])
  }
  const shown = strategy === ALL ? [...byStrategy.keys()] : [strategy]
  const dateOptions = d.dates.includes(d.target_date) ? d.dates : [d.target_date, ...d.dates]

  return (
    <div>
      {header}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <label className="text-sm text-gray-700">
          기록일{' '}
          <select
            className="ml-1 border rounded px-2 py-1 text-sm"
            value={d.target_date}
            onChange={(e) => setDate(e.target.value)}
            data-testid="rs-observe-date"
          >
            {dateOptions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-1" role="tablist">
          {[ALL, ...byStrategy.keys()].map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={s === strategy}
              onClick={() => setStrategy(s)}
              data-testid={`rs-observe-strategy-${s}`}
              className={`px-2 py-1 rounded text-xs ${s === strategy ? 'bg-navy-600 text-white' : 'bg-gray-100 text-gray-700'}`}
            >
              {s === ALL ? `전체 (${d.rows.length})` : `${strategyLabel(s)} (${byStrategy.get(s)?.length ?? 0})`}
            </button>
          ))}
        </div>
      </div>

      {shown.map((s) => (
        <StrategySection key={s} sid={s} rows={byStrategy.get(s) ?? []} />
      ))}

      <p className="text-xs text-gray-500" data-testid="rs-observe-legend">
        칸 이름에 마우스를 올리면 뜻이 보입니다. 정렬 = 보유 먼저, 그다음 RS 백분위 높은 순. 재무는 그날 알 수 있던 값만
        씁니다(공시 지연 반영) · 목표가는 기록일 전날까지의 증권사 의견입니다. 섹터 = KIS 업종명(2026-10-16 기록부터 — 그 전은
        업종 대분류 코드라 섹터 비교 값이 「제조업 평균 대비」 에 가깝습니다).
      </p>
    </div>
  )
}
