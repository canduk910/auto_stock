/**
 * `JournalChartModal` 의 분리 청크 래퍼 — cycle457.
 *
 * `klinecharts` 의존을 거래일지 탭 초기 로딩에 싣지 않으려고 `React.lazy` 로 나눈다. 로딩 폴백·오류 경계는
 * 종목 차트(`LazyStockChartModal.tsx`)의 것을 그대로 쓴다(배포 직후 청크 이름이 바뀌어도 모달 자리에서 멈춘다).
 */

import { lazy, Suspense } from 'react'
import { ChunkErrorBoundary, ChunkLoadingFallback } from './LazyStockChartModal'
import type { JournalCard } from '../types/journal'

const JournalChartModal = lazy(() => import('./JournalChartModal'))

interface Props {
  card: JournalCard
  onClose: () => void
}

export default function LazyJournalChartModal({ card, onClose }: Props) {
  return (
    <ChunkErrorBoundary onClose={onClose}>
      <Suspense fallback={<ChunkLoadingFallback />}>
        <JournalChartModal card={card} onClose={onClose} />
      </Suspense>
    </ChunkErrorBoundary>
  )
}
