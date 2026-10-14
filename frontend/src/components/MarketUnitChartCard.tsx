/**
 * cycle456 — 시장 유닛 결정 과정 카드(읽기 전용).
 *
 * 시장마다(코스피 종합 `0001` · 코스닥 종합 `1001`) 지수 종가·60일선 차트와, 오늘 배수가 정해지는 3단계
 * (① 종가 vs 60일선 → 위/아래 ② 60일선 vs 20봉 전 60일선 → 상승/하락 ③ 4칸 표 → 배수)를 보인다.
 * 데이터 = `GET /api/market-unit/chart`(판정은 서버가 운영 함수로 낸 값 — 화면은 다시 계산하지 않는다).
 * 차트 배경 띠 = 그 봉 기준 판정(다음 거래일 신규 진입에 쓰임). 아래 막대 = 봉별 배수.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchMarketUnitChart } from '../api/market-unit-chart'
import type { MarketKey, MarketUnitChartData, MarketUnitSnapshot } from '../types/market-unit-chart'
import type { MarketUnitState } from '../types/market-regime-label'
import { formatUnitM, UNIT_MODE_KO } from '../utils/marketRegimeLabel'
import { strategyLabel } from '../utils/strategyMeta'

const BOX = 'bg-white rounded-lg shadow p-4 mb-4'
const MARKETS: MarketKey[] = ['kospi', 'kosdaq']
const MARKET_KO: Record<MarketKey, string> = { kospi: '코스피', kosdaq: '코스닥' }

const STATE_ORDER: MarketUnitState[] = ['up_rising', 'up_falling', 'down_rising', 'down_falling']
const STATE_KO: Record<MarketUnitState, string> = {
  up_rising: '위 · 상승',
  up_falling: '위 · 하락',
  down_rising: '아래 · 상승',
  down_falling: '아래 · 하락',
}
/** 배경 띠·막대 색 — 진할수록 랏이 크다(0 = 신규 진입 없음). 색 정본은 index.css 토큰. */
const STATE_FILL: Record<MarketUnitState, string> = {
  up_rising: 'var(--color-sky-600)',
  up_falling: 'var(--color-sky-300)',
  down_rising: 'var(--color-beige-300)',
  down_falling: 'var(--color-red-300)',
}
const STATE_CHIP: Record<MarketUnitState, string> = {
  up_rising: 'bg-sky-600 text-white',
  up_falling: 'bg-sky-200 text-sky-900',
  down_rising: 'bg-beige-200 text-beige-900',
  down_falling: 'bg-red-200 text-red-900',
}
const REASON_KO: Record<string, string> = {
  ok: '정상',
  rows_short: '봉이 80개 미만',
  stale_head: '직전 영업일 봉 없음',
  bad_close: '종가 이상',
  exception: '계산 오류',
}

function fmt(v: number | null | undefined, digits = 2): string {
  return typeof v === 'number' && Number.isFinite(v)
    ? v.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : '—'
}

function pct(a: number | null | undefined, b: number | null | undefined): string {
  if (typeof a !== 'number' || typeof b !== 'number' || !Number.isFinite(a) || !Number.isFinite(b) || b === 0) return '—'
  const v = (a / b - 1) * 100
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

type Bar0 = MarketUnitChartData['markets'][MarketKey]['bars'][number]

/** 캔들의 세로 범위 = [저가, 고가]. OHLC 가 없는 봉은 종가 한 점. */
function candleRange(b: Bar0): [number, number] {
  const lo = b.low ?? Math.min(b.open ?? b.close, b.close)
  const hi = b.high ?? Math.max(b.open ?? b.close, b.close)
  return [lo, hi]
}

interface CandleProps {
  x?: number
  y?: number
  width?: number
  height?: number
  payload?: Bar0
}

/** recharts Bar 의 shape — 받은 사각형(저가~고가 픽셀)에서 시가·종가 위치를 비례로 찾는다. */
function CandleShape(props: CandleProps) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return null
  const [lo, hi] = candleRange(payload)
  const open = payload.open ?? payload.close
  const close = payload.close
  const span = hi - lo
  const toY = (v: number) => (span > 0 ? y + ((hi - v) / span) * height : y)
  // 시가를 모르면 오른 날인지 모른다 — 빨강으로 그리지 않고 회색(모름)으로 둔다.
  const known = payload.open != null
  const up = close >= open
  const color = !known ? 'var(--color-gray-400)' : up ? 'var(--color-red-500)' : 'var(--color-blue-500)'
  const cx = x + width / 2
  const bw = Math.max(1, width * 0.7)
  const top = toY(Math.max(open, close))
  const bodyH = Math.max(1, Math.abs(toY(open) - toY(close)))
  return (
    <g data-testid="mu-chart-candle" data-dir={!known ? 'unknown' : up ? 'up' : 'down'} data-color={color}>
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - bw / 2} y={top} width={bw} height={bodyH} fill={color} stroke={color} />
    </g>
  )
}

interface TipProps {
  active?: boolean
  payload?: { payload?: Bar0 }[]
}

function CandleTooltip({ active, payload }: TipProps) {
  const b = active ? payload?.[0]?.payload : undefined
  if (!b) return null
  return (
    <div className="bg-white border border-gray-200 rounded shadow px-2 py-1 text-[11px] text-gray-700">
      <div className="font-semibold">{b.date}</div>
      <div>{`시가 ${fmt(b.open)} · 고가 ${fmt(b.high)} · 저가 ${fmt(b.low)} · 종가 ${fmt(b.close)}`}</div>
      <div>{`60일선 ${fmt(b.sma60)} · 20봉 전 60일선 ${fmt(b.sma60_prev)}`}</div>
      <div>{b.state ? `판정 ${STATE_KO[b.state]} → ${formatUnitM(b.m)} (다음 거래일 적용)` : '판정 전(80봉 미만)'}</div>
    </div>
  )
}

/** 같은 판정이 이어진 구간 — 차트 배경 띠. */
function stateRuns(bars: MarketUnitChartData['markets'][MarketKey]['bars']) {
  const runs: { x1: string; x2: string; state: MarketUnitState }[] = []
  for (const b of bars) {
    if (!b.state) continue
    const last = runs[runs.length - 1]
    if (last && last.state === b.state) last.x2 = b.date
    else {
      // 띠 사이 빈틈이 없게 앞 구간을 이 봉까지 늘린다.
      if (last) last.x2 = b.date
      runs.push({ x1: b.date, x2: b.date, state: b.state })
    }
  }
  return runs
}

function DecisionSteps({ snap, mult }: { snap: MarketUnitSnapshot | null; mult: Record<MarketUnitState, number> }) {
  if (!snap) {
    return <p className="text-sm text-gray-500" data-testid="mu-chart-steps-unknown">오늘 판정을 계산하지 못했습니다(모름).</p>
  }
  if (!snap.ok) {
    return (
      <p className="text-sm text-gray-700" data-testid="mu-chart-steps-unavailable">
        {`판정 불가 — ${REASON_KO[snap.reason ?? ''] ?? snap.reason ?? '모름'}. 이때 그 시장은 배수를 줄이지 않습니다(×1, 다른 시장 값이 있으면 그 값).`}
      </p>
    )
  }
  const cur = snap.state as MarketUnitState
  return (
    <div className="space-y-2 text-sm" data-testid="mu-chart-steps">
      <div data-testid="mu-chart-step-position">
        <span className="font-medium">① 위치</span>
        {` — 기준 봉(${snap.bar_date ?? '—'}) 종가 ${fmt(snap.close)} vs 60일선 ${fmt(snap.sma60)} (${pct(snap.close, snap.sma60)}) → `}
        <span className="font-semibold">{snap.above ? '60일선 위' : '60일선 아래'}</span>
      </div>
      <div data-testid="mu-chart-step-slope">
        <span className="font-medium">② 기울기</span>
        {` — 60일선 ${fmt(snap.sma60)} vs 20봉 전 60일선 ${fmt(snap.sma60_prev)} (${pct(snap.sma60, snap.sma60_prev)}) → `}
        <span className="font-semibold">{snap.rising ? '상승' : '하락'}</span>
      </div>
      <div>
        <span className="font-medium">③ 배수</span>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mt-1" data-testid="mu-chart-step-table">
          {STATE_ORDER.map((s) => (
            <div
              key={s}
              data-testid={`mu-chart-state-${s}`}
              data-active={s === cur ? 'true' : 'false'}
              className={`rounded px-2 py-1 text-center text-xs ${s === cur ? `${STATE_CHIP[s]} ring-2 ring-navy-600 font-semibold` : 'bg-gray-50 text-gray-500'}`}
            >
              <div>{STATE_KO[s]}</div>
              <div>{formatUnitM(mult[s])}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function MarketUnitChartCard() {
  const [market, setMarket] = useState<MarketKey>('kospi')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['marketUnitChart'],
    queryFn: fetchMarketUnitChart,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className={BOX} data-testid="mu-chart-card">
        <div className="text-gray-500 text-sm">시장 유닛 차트 로딩 중...</div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className={BOX} data-testid="mu-chart-card">
        <div className="text-gray-500 text-sm">시장 유닛 차트를 불러오지 못했습니다.</div>
      </div>
    )
  }
  if (!data.success || !data.data) {
    return (
      <div className={BOX} data-testid="mu-chart-card">
        <h2 className="text-base font-semibold text-gray-900 mb-1">시장 유닛 결정 과정</h2>
        <div className="text-gray-500 text-sm">{data.message || '시장 유닛 차트가 없습니다.'}</div>
      </div>
    )
  }

  const d = data.data
  const mk = d.markets[market]
  const eff = mk.effective
  const engineKnown = eff.fallback !== 'not_computed'
  const shownM = engineKnown ? eff.m : mk.decision?.ok ? mk.decision.m : mk.decision ? 1 : null
  const runs = stateRuns(mk.bars)
  const closes = mk.bars.flatMap((b) => [b.close, b.sma60 ?? b.close, b.low ?? b.close, b.high ?? b.close])
  const lo = closes.length ? Math.min(...closes) : 0
  const hi = closes.length ? Math.max(...closes) : 1
  const pad = (hi - lo) * 0.05 || 1
  const modes = Object.entries(d.modes)
  const mismatch =
    engineKnown && mk.decision?.ok && mk.engine?.ok && mk.engine.state !== mk.decision.state

  return (
    <div className={BOX} data-testid="mu-chart-card">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h2 className="text-base font-semibold text-gray-900">시장 유닛 결정 과정</h2>
        <div className="flex gap-1" role="tablist">
          {MARKETS.map((m) => (
            <button
              key={m}
              type="button"
              data-testid={`mu-chart-tab-${m}`}
              aria-pressed={m === market}
              onClick={() => setMarket(m)}
              className={`px-2 py-1 rounded text-xs ${m === market ? 'bg-navy-600 text-white' : 'bg-gray-100 text-gray-700'}`}
            >
              {`${MARKET_KO[m]} (${d.markets[m].index_code})`}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        {`터틀 4전략의 신규 진입 랏을 그 종목이 속한 시장의 종합지수로 줄입니다(${mk.name}). enforce 인 전략만 실제 수량에 반영됩니다.`}
      </p>

      <div className="grid gap-4 md:grid-cols-3 mb-3">
        <section className="md:col-span-1">
          <div className="text-xs text-gray-500">오늘 적용 배수</div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900" data-testid="mu-chart-today-m">
              {formatUnitM(shownM)}
            </span>
            {mk.decision?.ok && mk.decision.state && mk.decision.state !== 'unavailable' && (
              <span className={`px-1.5 py-0.5 rounded text-xs ${STATE_CHIP[mk.decision.state]}`}>
                {STATE_KO[mk.decision.state]}
              </span>
            )}
          </div>
          <div className="text-xs text-gray-600 mt-1" data-testid="mu-chart-source">
            {!engineKnown
              ? '엔진이 아직 계산하지 않았습니다 — 운영 함수로 다시 낸 값'
              : eff.fallback === 'other_market'
                ? `이 시장 지수를 판정하지 못해 ${MARKET_KO[eff.from_market as MarketKey]} 배수를 대신 씁니다`
                : eff.fallback === 'none'
                  ? '두 시장 모두 판정 불가 — 배수를 줄이지 않습니다(×1)'
                  : '엔진 메모리 값'}
          </div>
          {mismatch && (
            <div className="text-xs text-amber-700 mt-1" data-testid="mu-chart-mismatch">
              엔진 값과 지금 다시 계산한 값이 다릅니다(엔진은 부팅 때 계산 — 그 뒤 지수가 갱신됐을 수 있음).
            </div>
          )}
          <div className="flex flex-wrap gap-1 mt-2 text-xs" data-testid="mu-chart-modes">
            {modes.map(([sid, mode]) => (
              <span
                key={sid}
                data-testid={`mu-chart-mode-${sid}`}
                className={`px-1.5 py-0.5 rounded ${mode === 'enforce' ? 'bg-sky-100 text-sky-800' : 'bg-gray-100 text-gray-600'}`}
              >
                {`${strategyLabel(sid)} ${mode ? UNIT_MODE_KO[mode] : '모름'}`}
              </span>
            ))}
          </div>
        </section>
        <section className="md:col-span-2">
          <DecisionSteps snap={mk.decision} mult={d.rules.multipliers} />
        </section>
      </div>

      {mk.bars.length === 0 ? (
        <p className="text-sm text-gray-500" data-testid="mu-chart-empty">
          지수 일봉이 아직 적재되지 않았습니다(부팅·20:30 적재 뒤 표시).
        </p>
      ) : (
        <>
          <div className="h-64" data-testid="mu-chart-price" data-bars={mk.bars.length}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={mk.bars} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                {runs.map((r) => (
                  <ReferenceArea
                    key={`${r.x1}-${r.state}`}
                    x1={r.x1}
                    x2={r.x2}
                    fill={STATE_FILL[r.state]}
                    fillOpacity={0.18}
                    strokeOpacity={0}
                    ifOverflow="extendDomain"
                  />
                ))}
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-gray-200)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} minTickGap={24} />
                <YAxis
                  domain={[lo - pad, hi + pad]}
                  tick={{ fontSize: 10 }}
                  width={56}
                  tickFormatter={(v: number) => v.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}
                />
                <Tooltip content={<CandleTooltip />} />
                {/* 가격 = 캔들(고가~저가 꼬리 + 시가~종가 몸통). 상승 빨강 · 하락 파랑(한국 관례) */}
                <Bar dataKey={candleRange} name="가격" shape={CandleShape} isAnimationActive={false} />
                <Line type="monotone" dataKey="sma60" name="60일선" stroke="var(--color-navy-600)" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={false} />
                <Line type="monotone" dataKey="sma60_prev" name="20봉 전 60일선" stroke="var(--color-navy-300)" strokeDasharray="4 3" dot={false} strokeWidth={1} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="h-16" data-testid="mu-chart-multiplier">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={mk.bars} margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
                <XAxis dataKey="date" hide />
                <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tick={{ fontSize: 9 }} width={56} />
                <Tooltip formatter={(v) => [formatUnitM(typeof v === 'number' ? v : null), '배수']} labelFormatter={(l) => String(l)} />
                {/* ×0 인 날도 보이게 최소 높이 2px(판정 없는 봉 = null 이라 그리지 않는다) */}
                <Bar dataKey="m" isAnimationActive={false} minPointSize={2}>
                  {mk.bars.map((b) => (
                    <Cell key={b.date} fill={b.state ? STATE_FILL[b.state] : 'var(--color-gray-200)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-500 mt-1" data-testid="mu-chart-legend">
            <span>캔들 = 가격(빨강 상승 · 파랑 하락) · ━ 60일선(남색) · ┅ 20봉 전 60일선</span>
            <span>배경·아래 막대 = 그 봉 기준 판정(다음 거래일 진입에 쓰임)</span>
            {STATE_ORDER.map((s) => (
              <span key={s} className={`px-1 rounded ${STATE_CHIP[s]}`}>{`${STATE_KO[s]} ${formatUnitM(d.rules.multipliers[s])}`}</span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
