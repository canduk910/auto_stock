/**
 * `StockChartModal` 의 분리 청크 래퍼 — cycle387.
 *
 * `klinecharts` 의존(ESM 약 675KB, min 약 234KB)을 세 그리드의 초기 로딩에 싣지 않으려고
 * `React.lazy` 로 분리한다. 이 파일을 따로 둔 이유는 순수 배치 문제다 — 훅
 * (`useStockChartOpener.tsx`)이 이 컴포넌트 정의를 직접 담으면 그 파일이 "컴포넌트 아닌
 * export(훅) + 모듈 스코프 컴포넌트(지연 로더·로딩 폴백)" 를 함께 갖게 되어 Fast Refresh
 * 가드(`react-refresh/only-export-components`)가 깨진다 — 파일을 가르면 이 파일은
 * **컴포넌트만** export 한다.
 *
 * 오류 경계 — 프론트를 다시 배포하면 청크 파일 이름이 바뀌어, 배포 전에 열어 둔 탭의 첫
 * 더블클릭에서 동적 import 가 실패한다. 경계가 없으면 그 오류가 루트까지 올라가 그리드를
 * 포함한 앱 전체가 내려간다. `ChunkErrorBoundary` 가 모달 자리에서 멈추고 닫기 버튼을 준다
 * (React 는 함수 컴포넌트 오류 경계를 지원하지 않아 클래스다 — `DailyReportTab` 선례).
 */

import { Component, lazy, Suspense, type ReactNode } from 'react'

const StockChartModal = lazy(() => import('./StockChartModal'))

function ChunkLoadingFallback() {
  return (
    <div
      data-testid="stock-chart-chunk-loading"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="bg-white rounded-lg shadow-xl px-6 py-4 text-sm text-gray-500">
        차트 모듈 불러오는 중…
      </div>
    </div>
  )
}

interface BoundaryProps {
  onClose: () => void
  children: ReactNode
}

class ChunkErrorBoundary extends Component<BoundaryProps, { hasError: boolean }> {
  constructor(props: BoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.error('[StockChartModal] 차트 모듈 로딩·표시 실패', error)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div
        data-testid="stock-chart-chunk-error"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2"
      >
        <div
          role="alert"
          className="bg-white rounded-lg shadow-xl px-6 py-4 text-sm text-red-700 flex items-start gap-3 max-w-md"
        >
          <span className="break-words">
            차트를 열지 못했습니다 — 새 버전 배포 직후라면 화면을 새로고침한 뒤 다시 여세요.
          </span>
          <button
            type="button"
            data-testid="stock-chart-chunk-error-close"
            onClick={this.props.onClose}
            aria-label="닫기"
            className="text-gray-500 hover:text-gray-700 text-xl font-bold shrink-0"
          >
            ×
          </button>
        </div>
      </div>
    )
  }
}

interface Props {
  ticker: string
  name?: string
  onClose: () => void
}

export default function LazyStockChartModal({ ticker, name, onClose }: Props) {
  return (
    <ChunkErrorBoundary onClose={onClose}>
      <Suspense fallback={<ChunkLoadingFallback />}>
        <StockChartModal ticker={ticker} name={name} onClose={onClose} />
      </Suspense>
    </ChunkErrorBoundary>
  )
}
