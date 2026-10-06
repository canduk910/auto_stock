/**
 * cycle410 — 장세 + 시장 유닛 카드.
 *
 * 왼쪽 = 6장세 라벨(관찰용 — 매매에 쓰지 않는다): 069500 일봉으로 매긴 오늘 장세 · 근거 두 값 ·
 * 시작일. 정의 정본 = `src/engine/market_regime_label.py`.
 * 오른쪽 = 시장 유닛(실제 매수 수량에 쓰임 — enforce 인 전략만): 운영 판정 그대로의 오늘 배수와
 * 근거, 축소 대상 전략별 모드. 정의 정본 = `src/engine/market_unit.py`.
 * 아래 = 최근 60거래일 띠 두 줄(장세 색 · m 값). 둘 다 직전 영업일 봉까지로 매긴다(`basis_date`).
 */
import { useQuery } from '@tanstack/react-query'
import { fetchMarketRegimeLabel } from '../api/market-regime-label'
import {
  REGIME_LABEL_COLOR,
  REGIME_LABEL_KO,
  UNIT_MODE_KO,
  formatSignedPct1,
  formatUnitM,
  unitColor,
} from '../utils/marketRegimeLabel'
import { strategyLabel } from '../utils/strategyMeta'

const BOX = 'bg-white rounded-lg shadow p-4 mb-4'

export default function MarketRegimeLabelCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['marketRegimeLabel'],
    queryFn: fetchMarketRegimeLabel,
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  })

  if (isLoading) {
    return (
      <div className={BOX} data-testid="regime-label-card">
        <div className="text-gray-500 text-sm">장세 라벨 로딩 중...</div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className={BOX} data-testid="regime-label-card">
        <div className="text-gray-500 text-sm">장세 라벨을 불러오지 못했습니다.</div>
      </div>
    )
  }
  if (!data.success || !data.data) {
    return (
      <div className={BOX} data-testid="regime-label-card">
        <h2 className="text-base font-semibold text-gray-900 mb-1">장세</h2>
        <div className="text-gray-500 text-sm">{data.message || '장세 라벨이 없습니다.'}</div>
      </div>
    )
  }

  const d = data.data
  const t = d.today
  const u = d.market_unit
  const modes = Object.entries(u.modes)
  const enforced = modes.filter(([, mode]) => mode === 'enforce').length
  return (
    <div className={BOX} data-testid="regime-label-card">
      <div className="grid gap-4 md:grid-cols-2">
        <section>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
            <h2 className="text-base font-semibold text-gray-900">장세</h2>
            <span
              data-testid="regime-label-badge"
              className={`inline-block px-2 py-1 rounded text-xs font-medium text-white ${REGIME_LABEL_COLOR[t.label]}`}
            >
              {REGIME_LABEL_KO[t.label]}
            </span>
          </div>
          <p className="text-xs text-gray-500 mb-2">관찰용 — 매매에 쓰지 않습니다</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-700">
            <span>{`60일선 20일 기울기 ${formatSignedPct1(t.slope_pct)}`}</span>
            <span>{`20일 변동성 ${Math.round(t.vol_pct)}%`}</span>
            <span data-testid="regime-label-since">
              {`${d.since}${d.since_truncated ? ' 이전부터' : '부터'}`}
            </span>
            <span className="text-gray-500" data-testid="regime-label-basis">
              {`기준 봉 ${t.basis_date}`}
            </span>
          </div>
        </section>
        <section>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
            <h2 className="text-base font-semibold text-gray-900">시장 유닛</h2>
            <span
              data-testid="regime-unit-m"
              className={`inline-block px-2 py-1 rounded text-xs font-medium ${u.m != null && u.m >= 0.75 ? 'text-white' : 'text-gray-800'} ${unitColor(u.m)}`}
            >
              {formatUnitM(u.m)}
            </span>
          </div>
          <p className="text-xs text-gray-500 mb-2">실제 매수 수량에 쓰임 — enforce 인 전략만</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-700">
            {u.above_sma60 != null && <span>{u.above_sma60 ? '종가 60일선 위' : '종가 60일선 아래'}</span>}
            {u.sma60_rising != null && <span>{u.sma60_rising ? '60일선 상승' : '60일선 하락'}</span>}
            <span className="text-gray-500" data-testid="regime-unit-basis">
              {`기준 봉 ${u.basis_date}`}
            </span>
            <span className="text-gray-400 text-xs" data-testid="regime-unit-source">
              운영 DB 종가로 다시 계산한 값
            </span>
          </div>
          <div className="flex flex-wrap gap-1 mt-2 text-xs" data-testid="regime-unit-modes">
            {modes.map(([sid, mode]) => (
              <span
                key={sid}
                data-testid={`regime-unit-mode-${sid}`}
                className={`px-1.5 py-0.5 rounded ${mode === 'enforce' ? 'bg-sky-100 text-sky-800' : 'bg-gray-100 text-gray-600'}`}
              >
                {`${strategyLabel(sid)} ${mode ? UNIT_MODE_KO[mode] : '모름'}`}
              </span>
            ))}
          </div>
          {enforced === 0 && <p className="text-xs text-gray-500 mt-1">지금 적용 중인 전략 없음</p>}
        </section>
      </div>
      <div className="mt-3 space-y-1">
        <div className="flex gap-px h-3" data-testid="regime-label-band" aria-label="최근 60거래일 장세">
          {d.history.map((h) => (
            <div
              key={h.date}
              data-testid="regime-label-band-cell"
              title={`${h.date} ${REGIME_LABEL_KO[h.label]}`}
              className={`flex-1 ${REGIME_LABEL_COLOR[h.label]}`}
            />
          ))}
        </div>
        <div className="flex gap-px h-3" data-testid="regime-unit-band" aria-label="최근 60거래일 시장 유닛 배수">
          {d.history.map((h) => (
            <div
              key={h.date}
              data-testid="regime-unit-band-cell"
              title={`${h.date} ${formatUnitM(h.m)}`}
              className={`flex-1 ${unitColor(h.m)}`}
            />
          ))}
        </div>
      </div>
      <div className="flex justify-between text-[11px] text-gray-400 mt-1">
        <span>{d.history[0]?.date}</span>
        <span>위 = 장세 · 아래 = 시장 유닛 배수</span>
        <span>{d.history[d.history.length - 1]?.date}</span>
      </div>
    </div>
  )
}
