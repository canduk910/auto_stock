/**
 * cycle387 — `GET /api/stock-chart/candles` Playwright 목(일봉·주봉·월봉 각 5봉).
 *
 * `frontend/src/test/fixtures/stockChart.fixture.ts`(MSW) 와 **같은 리터럴**이다 — 한쪽을 바꾸면
 * 다른 쪽도 같이 바꾼다. 만든 법(명세 `_workspace/red/cycle387_stock_chart_spec.md` §3.2 🅵):
 * 라우터만 실은 독립 앱에 문자열 모양의 KIS 목(output1 · output2)을 물려 라우트를 실제로 태우고
 * 나온 JSON 을 그대로 옮겼다(시각 고정 2026-09-28 16:55:02 KST). 가격·거래량은 합성값 —
 * 배포 뒤 실제 응답 1건으로 교체한다(명세 §10).
 */

export type StockChartPeriodKey = "D" | "W" | "M";

export const STOCK_CHART_RESPONSES: Record<StockChartPeriodKey, Record<string, unknown>> = {
  D: {
    success: true,
    message: "일봉 5개",
    data: {
      ticker: "005930",
      name: "삼성전자",
      period: "D",
      years: 5,
      adjusted: true,
      market: "J",
      start_date: "2021-09-28",
      end_date: "2026-09-28",
      bars: [
        { date: "2026-09-18", open: 71800, high: 72000, low: 70700, close: 70900, volume: 13200981, amount: 935949552900 },
        { date: "2026-09-21", open: 70900, high: 71100, low: 70100, close: 70400, volume: 12011345, amount: 845598688000 },
        { date: "2026-09-22", open: 70500, high: 71400, low: 70300, close: 71200, volume: 10522871, amount: 749228415200 },
        { date: "2026-09-23", open: 71200, high: 71900, low: 70800, close: 71600, volume: 9934120, amount: 711282992000 },
        { date: "2026-09-28", open: 71700, high: 72400, low: 71300, close: 72100, volume: 11834522, amount: 853269036200 },
      ],
      complete: true,
      incomplete_reason: null,
      last_bar_provisional: true,
      dropped_bars: 0,
      kis_calls: 1,
      cached: false,
      fetched_at: "2026-09-28T16:55:02+09:00",
    },
  },
  W: {
    success: true,
    message: "주봉 5개",
    data: {
      ticker: "005930",
      name: "삼성전자",
      period: "W",
      years: 5,
      adjusted: true,
      market: "J",
      start_date: "2021-09-27",
      end_date: "2026-09-28",
      bars: [
        { date: "2026-09-04", open: 67200, high: 68900, low: 66800, close: 68400, volume: 55310988, amount: 3783271579200 },
        { date: "2026-09-11", open: 68500, high: 70200, low: 68100, close: 69700, volume: 58877102, amount: 4103734009400 },
        { date: "2026-09-18", open: 69800, high: 72300, low: 69500, close: 70900, volume: 61233410, amount: 4341448769000 },
        { date: "2026-09-23", open: 70900, high: 71900, low: 70100, close: 71600, volume: 32468336, amount: 2324732857600 },
        { date: "2026-09-28", open: 71700, high: 72400, low: 71300, close: 72100, volume: 11834522, amount: 853269036200 },
      ],
      complete: true,
      incomplete_reason: null,
      last_bar_provisional: true,
      dropped_bars: 0,
      kis_calls: 1,
      cached: false,
      fetched_at: "2026-09-28T16:55:02+09:00",
    },
  },
  M: {
    success: true,
    message: "월봉 5개",
    data: {
      ticker: "005930",
      name: "삼성전자",
      period: "M",
      years: 5,
      adjusted: true,
      market: "J",
      start_date: "2021-09-01",
      end_date: "2026-09-28",
      bars: [
        { date: "2026-05-29", open: 60200, high: 63100, low: 59400, close: 61700, volume: 266509014, amount: 16443606163800 },
        { date: "2026-06-30", open: 61800, high: 64700, low: 60900, close: 63200, volume: 251332087, amount: 15884187898400 },
        { date: "2026-07-31", open: 63300, high: 66900, low: 62800, close: 65000, volume: 238874511, amount: 15526843215000 },
        { date: "2026-08-31", open: 65100, high: 68800, low: 64200, close: 67800, volume: 245118732, amount: 16619050029600 },
        { date: "2026-09-28", open: 67900, high: 72400, low: 66500, close: 72100, volume: 219724358, amount: 15842126211800 },
      ],
      complete: true,
      incomplete_reason: null,
      last_bar_provisional: true,
      dropped_bars: 0,
      kis_calls: 1,
      cached: false,
      fetched_at: "2026-09-28T16:55:02+09:00",
    },
  },
};
