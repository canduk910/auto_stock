/**
 * cycle416 — `GET /api/market/breadth` 응답 `data` 픽스처 (3영업일).
 *
 * 키 이름·모양은 명세 §5.4(`_workspace/red/cycle416/breadth_spec.md`) 그대로다 — 손으로 쓴 Red 픽스처.
 * 10-08 숫자는 메인 세션 실측(코스피 942행 · 코스닥 1,823행)을 재현한 백엔드 픽스처의 집계값,
 * 10-07·10-06 은 합성값이다(합계·비율·요약은 파이썬으로 검산함).
 * ⚠️ Green 뒤 백엔드 라우트를 실제로 태워 나온 JSON 으로 바꿔 넣는다(cycle266 「목은 실제 응답을 담는다」).
 */
import type { MarketBreadthData } from '../../types/market-breadth'

export const MARKET_BREADTH_FIXTURE: MarketBreadthData = {
  asof_kst: '2026-10-09T11:00:03+09:00',
  window: {
    from: '2026-10-06',
    to: '2026-10-08',
    n_days: 3,
    requested: 3,
    complete: true,
    lookback_from: '2026-08-30',
  },
  days: [
    {
      date: '2026-10-08',
      kospi: { rows: 942, traded: 927, up: 252, down: 625, flat: 50, limit_up: 3, limit_down: 0, no_trade: 15, out_of_band: 0, unparsed: 0, up_ratio: 0.2718 },
      kosdaq: { rows: 1823, traded: 1748, up: 618, down: 1031, flat: 99, limit_up: 13, limit_down: 1, no_trade: 75, out_of_band: 0, unparsed: 0, up_ratio: 0.3535 },
      total: { rows: 2765, traded: 2675, up: 870, down: 1656, flat: 149, limit_up: 16, limit_down: 1, no_trade: 90, out_of_band: 0, unparsed: 0, up_ratio: 0.3252 },
    },
    {
      date: '2026-10-07',
      kospi: { rows: 940, traded: 925, up: 500, down: 400, flat: 25, limit_up: 1, limit_down: 0, no_trade: 15, out_of_band: 0, unparsed: 0, up_ratio: 0.5405 },
      kosdaq: { rows: 1820, traded: 1745, up: 900, down: 780, flat: 65, limit_up: 4, limit_down: 2, no_trade: 75, out_of_band: 1, unparsed: 0, up_ratio: 0.5158 },
      total: { rows: 2760, traded: 2670, up: 1400, down: 1180, flat: 90, limit_up: 5, limit_down: 2, no_trade: 90, out_of_band: 1, unparsed: 0, up_ratio: 0.5243 },
    },
    {
      date: '2026-10-06',
      kospi: { rows: 941, traded: 926, up: 300, down: 580, flat: 46, limit_up: 0, limit_down: 1, no_trade: 15, out_of_band: 0, unparsed: 0, up_ratio: 0.324 },
      kosdaq: { rows: 1822, traded: 1747, up: 700, down: 950, flat: 97, limit_up: 6, limit_down: 0, no_trade: 75, out_of_band: 0, unparsed: 0, up_ratio: 0.4007 },
      total: { rows: 2763, traded: 2673, up: 1000, down: 1530, flat: 143, limit_up: 6, limit_down: 1, no_trade: 90, out_of_band: 0, unparsed: 0, up_ratio: 0.3741 },
    },
  ],
  summary: {
    kospi: { n_days: 3, up: 1052, down: 1605, flat: 121, limit_up: 4, limit_down: 1, no_trade: 45, up_ratio: 0.3787, adr: 65.5 },
    kosdaq: { n_days: 3, up: 2218, down: 2761, flat: 261, limit_up: 23, limit_down: 3, no_trade: 225, up_ratio: 0.4233, adr: 80.3 },
    total: { n_days: 3, up: 3270, down: 4366, flat: 382, limit_up: 27, limit_down: 4, no_trade: 270, up_ratio: 0.4078, adr: 74.9 },
  },
  adr_reference: { oversold: 75, overheated: 120 },
  source: 'KRX 공개 API 일별 매매정보(유가증권·코스닥)',
  missing_dates: [],
  empty_dates: [],
  pending_date: null,
}
