/**
 * 종목 차트 모달을 여는 공용 훅 — cycle387.
 *
 * 잔고·주문체결내역·매매손익 세 그리드가 똑같은 규칙으로 행 더블클릭을 처리한다:
 * 1. 버튼·링크·입력·라벨(및 그 자손) 위의 더블클릭은 무시한다 — 「매도」·「AI 자문」
 *    두 번 누름이 매도 확인창·AI 팝업과 차트 모달을 동시에 띄우면 안 된다.
 * 2. 더블클릭이 남긴 텍스트 선택 하이라이트를 지운다.
 * 3. 그 행의 종목코드·이름으로 모달을 연다(코드가 6자리 숫자가 아니어도 모달은 열되
 *    모달 안에서 `stock-chart-unsupported` 로 안내한다 — 요청은 나가지 않는다).
 *
 * 모달 자체(`klinecharts` 의존)는 `LazyStockChartModal.tsx` 가 `React.lazy` 로 분리 청크로
 * 감싼다 — 세 그리드의 초기 로딩에 싣지 않는다. 정본:
 * `_workspace/red/cycle387_stock_chart_spec.md` §2.2 · §2.4.
 */

import { useState, type MouseEvent, type ReactNode } from 'react'
import LazyStockChartModal from './LazyStockChartModal'
import { isInteractiveTarget } from '../utils/stockChart'

interface ChartTarget {
  ticker: string
  name: string
}

interface StockChartOpener {
  openChart: (e: MouseEvent, ticker: unknown, name: unknown) => void
  chartModal: ReactNode
}

export function useStockChartOpener(): StockChartOpener {
  const [target, setTarget] = useState<ChartTarget | null>(null)

  const openChart = (e: MouseEvent, ticker: unknown, name: unknown) => {
    if (isInteractiveTarget(e.target)) return
    window.getSelection?.()?.removeAllRanges()
    setTarget({ ticker: String(ticker ?? '').trim(), name: String(name ?? '').trim() })
  }

  const chartModal = target ? (
    <LazyStockChartModal ticker={target.ticker} name={target.name} onClose={() => setTarget(null)} />
  ) : null

  return { openChart, chartModal }
}
