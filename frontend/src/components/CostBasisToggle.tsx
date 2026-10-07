// 세후/세전 토글 — 실적 화면 공통 (cycle411). PerformanceCard·ProfitChart 등이 공유한다.
import type { CostBasis } from '../utils/costBasis'

interface Props {
  value: CostBasis
  onChange: (next: CostBasis) => void
}

export default function CostBasisToggle({ value, onChange }: Props) {
  return (
    <div
      data-testid="cost-basis-toggle"
      className="inline-flex rounded-md border border-gray-200 overflow-hidden text-xs shrink-0"
    >
      <button
        type="button"
        aria-pressed={value === 'net'}
        onClick={() => onChange('net')}
        className={`px-2 py-1 ${value === 'net' ? 'bg-gray-900 text-white' : 'bg-white text-gray-500'}`}
      >
        세후
      </button>
      <button
        type="button"
        aria-pressed={value === 'gross'}
        onClick={() => onChange('gross')}
        className={`px-2 py-1 ${value === 'gross' ? 'bg-gray-900 text-white' : 'bg-white text-gray-500'}`}
      >
        세전
      </button>
    </div>
  )
}
