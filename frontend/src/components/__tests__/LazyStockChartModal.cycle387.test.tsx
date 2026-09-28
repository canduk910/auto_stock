/**
 * cycle387 — 차트 청크 로딩 실패가 화면 전체를 내리지 않는다 (C1).
 *
 * `LazyStockChartModal` 은 `React.lazy(() => import('./StockChartModal'))` 로 차트를 분리 청크로 싣는다.
 * 프론트를 다시 배포하면 청크 파일 이름이 바뀌어, 배포 전에 열어 둔 탭에서 처음 더블클릭할 때 그 동적
 * import 가 실패한다. 오류 경계가 없으면 그 오류가 루트까지 올라가 **그리드를 포함한 앱 전체가 내려간다**.
 *
 * 봉인하는 계약
 * - 청크 로딩 실패 → 모달 자리에 오류 안내 `stock-chart-chunk-error`(새로고침 안내) + 닫기 버튼
 *   `stock-chart-chunk-error-close`. 그리드(모달을 연 쪽)는 그대로 남는다.
 * - 닫기 → `onClose` → 오류 안내가 사라지고 그리드는 계속 남는다.
 *
 * 실패는 `vi.mock` 팩토리가 던지는 것으로 만든다 — 지연 로더의 동적 import 가 거부된다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { TestProviders } from '../../test/providers'
import { useStockChartOpener } from '../useStockChartOpener'

vi.mock('../StockChartModal', () => {
  throw new Error('Failed to fetch dynamically imported module: /assets/StockChartModal-old.js')
})

let consoleError: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  // React 가 잡힌 렌더 오류를 console.error 로 알린다 — 이 파일은 그 오류를 일부러 만든다.
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  consoleError.mockRestore()
})

function MiniGrid() {
  const { openChart, chartModal } = useStockChartOpener()
  return (
    <>
      <table>
        <tbody>
          <tr data-testid="mini-row" onDoubleClick={(e) => openChart(e, '005930', '삼성전자')}>
            <td>삼성전자</td>
          </tr>
        </tbody>
      </table>
      {chartModal}
    </>
  )
}

describe('C1: 차트 청크 로딩 실패', () => {
  it('C1-a: 오류 안내 + 닫기 — 그리드는 남는다', async () => {
    const user = userEvent.setup()
    render(
      <TestProviders>
        <MiniGrid />
      </TestProviders>,
    )

    await user.dblClick(screen.getByText('삼성전자'))

    const err = await screen.findByTestId('stock-chart-chunk-error', {}, { timeout: 5000 })
    expect(err.textContent).toContain('새로고침')
    expect(screen.getByTestId('mini-row')).toBeInTheDocument()
    expect(screen.queryByTestId('stock-chart-modal')).toBeNull()

    const close = screen.getByTestId('stock-chart-chunk-error-close')
    expect(close).toHaveAttribute('aria-label', '닫기')
    await user.click(close)

    await waitFor(() => expect(screen.queryByTestId('stock-chart-chunk-error')).toBeNull())
    expect(screen.getByTestId('mini-row')).toBeInTheDocument()
  }, 15000)
})
